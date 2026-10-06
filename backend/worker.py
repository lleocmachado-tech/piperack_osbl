"""Separate durable worker; lease, cancellation, bounded child process, retry, idempotent commit."""
import time,traceback,multiprocessing,queue
import psutil
from datetime import datetime,timezone,timedelta
import pdfplumber
from pypdf import PdfReader
from sqlalchemy import select,update
from . import db
from .config import ORIGINALS,PROCESS_VERSION
from .geometry import matrix
from .bom import extract_blocks
from .recognition import classify
from .rendering import render

def inspect_file(digest,output):
    try:
        reader=PdfReader(ORIGINALS/(digest+'.pdf'));result=[]
        with pdfplumber.open(ORIGINALS/(digest+'.pdf')) as document:
            for number,p in enumerate(document.pages,1):
                raw=reader.pages[number-1];box=list(map(float,raw.cropbox));rotation=int(raw.get('/Rotate',0))%360
                labels=[]
                for word in p.extract_words():
                    classification=classify(word['text'])
                    if classification['kind']=='piece_candidate':
                        labels.append({'text':classification['normalized'],'method':'native','data':{**classification,'box_pdf':[word['x0'],p.height-word['bottom'],word['x1'],p.height-word['top']],'reading_confidence':None,'orientation':0,'requires_review':True}})
                render(digest,number,40)
                result.append({'number':number,'data':{'cropbox':box,'mediabox':list(map(float,raw.mediabox)),
                    'rotation':rotation,'width':float(raw.mediabox.width),'height':float(raw.mediabox.height),
                    'pdf_to_raster_72dpi':matrix(box,rotation),'coordinate_system':'raw PDF points, bottom-left',
                    'characters':len(p.chars),'objects':{k:len(v) for k,v in p.objects.items()},'images':len(p.images),
                    'native_coverage':'partial' if p.chars else 'none','code_coverage_validated':False,'processing_version':PROCESS_VERSION},
                    'labels':labels,'bom':extract_blocks(p) if len(p.chars)>1000 else []})
        output.put({'ok':True,'pages':result})
    except Exception as error: output.put({'ok':False,'error':str(error)[:1500]})

def ocr_file(digest,number,view,output):
    try:
        from .ocr import recognize_region
        output.put({'ok':True,'observations':recognize_region(digest,number,view['data']['polygon']),'view_id':view['id']})
    except Exception as error:output.put({'ok':False,'error':str(error)[:1500]})

def claim(engine):
    with engine.begin() as c:
        stale=(datetime.now(timezone.utc)-timedelta(minutes=3)).isoformat()
        for expired in c.execute(db.jobs.select().where(db.jobs.c.status=='running',db.jobs.c.heartbeat<stale)).mappings():
            c.execute(update(db.jobs).where(db.jobs.c.id==expired['id'],db.jobs.c.status=='running').values(status='queued',data={**expired['data'],'message':'Lease expirada; retomada segura'}))
        job=c.execute(db.jobs.select().where(db.jobs.c.status=='queued',db.jobs.c.attempts<3).order_by(db.jobs.c.created_at).limit(1)).mappings().first()
        if not job: return None
        changed=c.execute(update(db.jobs).where(db.jobs.c.id==job['id'],db.jobs.c.status=='queued').values(status='running',attempts=job['attempts']+1,heartbeat=db.now())).rowcount
        return dict(job) if changed else None

def commit(engine,job,result):
    pid=job['project_id']
    with engine.begin() as c:
        c.execute(update(db.projects).where(db.projects.c.id==pid).values(version=db.projects.c.version+1))
        fresh=db.get(c,'jobs',job['id'],pid)
        if fresh['cancel_requested']:
            c.execute(update(db.jobs).where(db.jobs.c.id==job['id']).values(status='cancelled'));return
        if not result['ok']:
            c.execute(update(db.jobs).where(db.jobs.c.id==job['id']).values(status='failed',data={**fresh['data'],'message':result['error'],'benchmark':result.get('benchmark')}));return
        if 'observations' in result:
            view=db.get(c,'views',result['view_id'],pid)
            known={p['code']:p for p in db.rows(c,'piece_types',pid)}
            existing=db.rows(c,'labels',pid)
            for obs in result['observations']:
                if any(l['text']==obs['normalized'] and l['page_id']==view['page_id'] and l['data'].get('polygon')==obs['polygon'] for l in existing):continue
                label=db.insert(c,'labels',pid,{'page_id':view['page_id'],'text':obs['normalized'],'method':'ocr','data':{**obs,'reading_confidence':obs['confidence'],'requires_review':True}})
                db.insert(c,'proposals',pid,{'state':'NÃO ASSOCIADA','data':{'kind':'label_review','label_id':label['id'],'view_id':view['id'],'type_id':known.get(obs['normalized'],{}).get('id'),
                    'reading_score':obs['confidence'],'geometry_score':None,'identity_score':None,
                    'blocking':['Geometria e identidade ainda não delimitadas'] if obs['normalized'] in known else ['Código desconhecido no catálogo'],
                    'candidates':[],'algorithm':obs['engine'],'origin':obs}})
        for page in result.get('pages',[]):
            old=c.execute(db.pages.select().where(db.pages.c.drawing_id==job['drawing_id'],db.pages.c.number==page['number'])).mappings().first()
            if old: continue # Manual corrections and existing native observations remain protected.
            row=db.insert(c,'pages',pid,{'drawing_id':job['drawing_id'],'number':page['number'],'data':page['data']})
            for label in page['labels']: db.insert(c,'labels',pid,{'page_id':row['id'],**label})
            for entry in page['bom']:
                old_type=c.execute(db.piece_types.select().where(db.piece_types.c.project_id==pid,db.piece_types.c.code==entry['code'])).mappings().first()
                piece=dict(old_type) if old_type else db.insert(c,'piece_types',pid,{'code':entry['code'],'quantity':entry['quantity'],'validation':'DRAFT','category':'structure',
                    'data':{'description':entry['description'],'profile':entry['profile'],'material':entry['material'],'raw_codes':[entry['raw_code']],'weight':entry['weight'],'weight_validated':False,'source':'positional BOM candidate'}})
                conflict=bool(old_type and (piece['quantity']!=entry['quantity'] or piece['data'].get('weight')!=entry['weight']))
                db.insert(c,'bom_entries',pid,{'page_id':row['id'],'type_id':piece['id'],'approval':'CONFLICT' if conflict else 'DRAFT','data':entry})
        c.execute(update(db.jobs).where(db.jobs.c.id==job['id']).values(status='done',heartbeat=db.now(),data={**fresh['data'],'progress':100,'message':'Processamento concluído. Catálogo e associações exigem revisão.','benchmark':result.get('benchmark')}))
        db.insert(c,'audit',pid,{'action':'worker:'+job['kind'],'author':'worker','data':{'job_id':job['id'],'algorithm':PROCESS_VERSION,'no_automatic_approval':True}})

def run_once(engine=db.engine):
    job=claim(engine)
    if not job: return False
    with engine.begin() as c: drawing=db.get(c,'drawings',job['drawing_id'],job['project_id'])
    ctx=multiprocessing.get_context('spawn');output=ctx.Queue()
    if job['kind'].startswith('ocr:'):
        with engine.connect() as c:
            view=db.get(c,'views',job['data']['view_id'],job['project_id']);page=db.get(c,'pages',view['page_id'],job['project_id'])
        child=ctx.Process(target=ocr_file,args=(drawing['sha256'],page['number'],view,output))
    else:child=ctx.Process(target=inspect_file,args=(drawing['sha256'],output))
    child.start()
    started=time.monotonic();result=None;peak_mb=0
    while time.monotonic()-started<120:
        try:
            process=psutil.Process(child.pid);memory=process.memory_info().rss+sum(p.memory_info().rss for p in process.children(recursive=True));peak_mb=max(peak_mb,memory/1024**2)
            if peak_mb>1024:result={'ok':False,'error':'Limite de 1 GB de memória do processamento atingido.'};break
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        with engine.begin() as c:
            fresh=db.get(c,'jobs',job['id'],job['project_id'])
            c.execute(update(db.jobs).where(db.jobs.c.id==job['id']).values(heartbeat=db.now()))
        if fresh['cancel_requested']:
            result={'ok':False,'error':'Cancelado pelo usuário'};break
        try: result=output.get(timeout=1);break
        except queue.Empty:
            if not child.is_alive(): result={'ok':False,'error':'Processo de inspeção interrompido'};break
    if result is None: result={'ok':False,'error':'Tempo limite de 120 s atingido'}
    result['benchmark']={'elapsed_seconds':round(time.monotonic()-started,3),'peak_rss_sampled_mb':round(peak_mb,1),'rss_sample_interval_seconds':1,'limit_mb':1024}
    if child.is_alive():
        try:
            for p in psutil.Process(child.pid).children(recursive=True):p.terminate()
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    child.join(timeout=3)
    if child.is_alive(): child.terminate();child.join(timeout=3)
    output.close();commit(engine,job,result)
    return True

def main():
    db.migrate()
    import os
    print('COMBIO worker pronto · PID',os.getpid(),flush=True)
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    if args.once: run_once();return
    while True:
        if not run_once(): time.sleep(1)
if __name__=='__main__': main()
