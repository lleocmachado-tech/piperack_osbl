import json,os,hashlib,io
from pathlib import Path
from fastapi import FastAPI,UploadFile,File,Form,Request,Depends,HTTPException
from fastapi.responses import FileResponse,Response,JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import update
from . import db
from .config import ROOT,ORIGINALS,MAX_FILE_BYTES
from .service import Store,Conflict
from .ingestion import ingest
from .measurement import summary
from .rendering import render
from .exporting import export_bundle
from .backup import backup,restore

db.migrate();store=Store();app=FastAPI(title='COMBIO · Avanço PipeRack OSBL',version='0.1.0')
USERS=json.loads(os.environ.get('PIPERACK_USERS','{}'))
MULTIUSER=bool(USERS)

def identity(request:Request):
    if not MULTIUSER: return {'name':'operador-local','role':'local','projects':'*'}
    token=request.headers.get('authorization','').removeprefix('Bearer ')
    user=USERS.get(token)
    if not user: raise HTTPException(401,'Token ausente ou inválido.')
    if user.get('role') not in {'reader','editor','reviewer'}:raise HTTPException(403,'Papel inválido.')
    return user
def access(pid,user,edit=False,review=False):
    if user.get('projects')!='*' and pid not in user.get('projects',[]): raise HTTPException(403,'Projeto fora do seu escopo.')
    if edit and user['role']=='reader':raise HTTPException(403,'Perfil leitor não pode alterar dados.')
    if review and user['role'] not in {'reviewer','local'}:raise HTTPException(403,'Ação exige revisor.')

@app.exception_handler(Conflict)
async def conflict(_,error):return JSONResponse({'detail':str(error)},status_code=409)
@app.exception_handler(ValueError)
async def invalid(_,error):return JSONResponse({'detail':str(error)},status_code=422)
@app.exception_handler(KeyError)
async def missing(_,error):return JSONResponse({'detail':'Campo obrigatório ausente: '+str(error)},status_code=422)
@app.exception_handler(__import__('sqlalchemy').exc.IntegrityError)
async def integrity(_,error):return JSONResponse({'detail':'Referência, código, revisão ou chave duplicada. Atualize os dados antes de repetir.'},status_code=409)

@app.get('/api/health')
def health():return {'status':'ok','multiuser':MULTIUSER,'schema':1,'auto_approval':False}
@app.get('/api/me')
def me(user=Depends(identity)):return user
@app.get('/api/projects')
def projects(user=Depends(identity)):
    with db.engine.connect() as c:
        all=[dict(r) for r in c.execute(db.projects.select()).mappings()]
        return [p for p in all if user.get('projects')=='*' or p['id'] in user.get('projects',[])]
@app.post('/api/projects')
def create_project(payload:dict,user=Depends(identity)):
    if user['role']=='reader':raise HTTPException(403,'Leitor não cria projetos.')
    if MULTIUSER and user.get('projects')!='*':raise HTTPException(403,'Criação de projeto requer escopo global.')
    return store.create_project(payload.get('name',''),user['name'])
@app.get('/api/projects/{pid}/state')
def state(pid:str,user=Depends(identity)):
    access(pid,user);return store.read(pid)
@app.get('/api/projects/{pid}/summary')
def totals(pid:str,stage_id:str,cutoff:str|None=None,user=Depends(identity)):
    access(pid,user);return summary(store.read(pid),stage_id,cutoff)
@app.post('/api/projects/{pid}/entities/{kind}')
def save(pid:str,kind:str,payload:dict,user=Depends(identity)):
    access(pid,user,edit=True)
    return store.save(pid,kind,payload['entity'],payload['expected_version'],payload['request_key'],user['name'],user['role'])
@app.post('/api/projects/{pid}/progress')
def progress(pid:str,payload:dict,user=Depends(identity)):
    access(pid,user,edit=True);return store.progress(pid,payload['event'],payload['expected_version'],payload['request_key'],user['name'])
@app.post('/api/projects/{pid}/field-mark')
def field_mark(pid:str,payload:dict,user=Depends(identity)):
    from .field import mark
    access(pid,user,edit=True,review=True)
    return mark(store,pid,payload['mark'],payload['expected_version'],payload['request_key'],user['name'],user['role'])
@app.post('/api/projects/{pid}/reverse')
def reverse(pid:str,payload:dict,user=Depends(identity)):
    access(pid,user,edit=True);return store.reverse(pid,payload['event'],payload['expected_version'],payload['request_key'],user['name'])
@app.post('/api/projects/{pid}/snapshots')
def snapshot(pid:str,payload:dict,user=Depends(identity)):
    access(pid,user,edit=True);return store.snapshot(pid,payload['snapshot'],payload['expected_version'],payload['request_key'],user['name'])
@app.get('/api/projects/{pid}/snapshots/{sid}/export')
def export(pid:str,sid:str,user=Depends(identity)):
    access(pid,user)
    with db.engine.connect() as c:snapshot=db.get(c,'snapshots',sid,pid)
    return Response(export_bundle(snapshot),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="combio-{sid}.zip"'})
@app.get('/api/projects/{pid}/snapshots/{sid}/backup')
def json_backup(pid:str,sid:str,user=Depends(identity)):
    access(pid,user)
    with db.engine.connect() as c:snapshot=db.get(c,'snapshots',sid,pid)
    return Response(json.dumps(backup(snapshot),ensure_ascii=False),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="backup-{sid}.json"'})
@app.post('/api/restore')
def import_backup(payload:dict,user=Depends(identity)):
    if user['role'] not in {'reviewer','local'} or user.get('projects')!='*':raise HTTPException(403,'Restauração exige revisor com escopo global.')
    return restore(store,payload,user['name'])
@app.post('/api/projects/{pid}/drawings')
async def upload(pid:str,file:UploadFile=File(...),technical_number:str=Form(...),revision:str=Form(...),
                 expected_version:int=Form(...),request_key:str=Form(...),previous_id:str|None=Form(None),user=Depends(identity)):
    access(pid,user,edit=True);content=await file.read(MAX_FILE_BYTES+1)
    return ingest(store,pid,content,file.filename or 'desenho.pdf',technical_number,revision,expected_version,request_key,user['name'],previous_id)
@app.get('/api/projects/{pid}/drawings/{did}/original')
def original(pid:str,did:str,user=Depends(identity)):
    access(pid,user)
    with db.engine.connect() as c:drawing=db.get(c,'drawings',did,pid)
    path=ORIGINALS/(drawing['sha256']+'.pdf')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=drawing['sha256']:raise ValueError('Hash do original divergente.')
    return FileResponse(path,media_type='application/pdf',filename=drawing['filename'])
@app.get('/api/projects/{pid}/pages/{page_id}/image')
def image(pid:str,page_id:str,dpi:int=40,rotation:int=0,user=Depends(identity)):
    access(pid,user)
    with db.engine.connect() as c:
        page=db.get(c,'pages',page_id,pid);drawing=db.get(c,'drawings',page['drawing_id'],pid)
    return FileResponse(render(drawing['sha256'],page['number'],dpi,rotation),media_type='image/png')
@app.get('/api/projects/{pid}/pages/{page_id}/primitives')
def primitives(pid:str,page_id:str,user=Depends(identity)):
    import pdfplumber
    access(pid,user)
    with db.engine.connect() as c:
        page=db.get(c,'pages',page_id,pid);drawing=db.get(c,'drawings',page['drawing_id'],pid)
    if page['data']['rotation']!=0:raise ValueError('Seleção de primitivas indisponível em PDF originalmente rotacionado. Use polígono ou linha.')
    with pdfplumber.open(ORIGINALS/(drawing['sha256']+'.pdf')) as pdf:
        p=pdf.pages[page['number']-1]
        segments=[{'id':index,'paths':[[[e['x0'],p.height-e['top']],[e['x1'],p.height-e['bottom']]]],'class':'unclassified-vector-edge'} for index,e in enumerate(p.edges[:30000]) if abs(e['x1']-e['x0'])+abs(e['bottom']-e['top'])>.1]
    return {'segments':segments,'candidate_only':True,'limitation':'Classe não validada. Selecione explicitamente as linhas; cotas e texto também podem aparecer.'}

@app.post('/api/projects/{pid}/views/{vid}/ocr')
def queue_ocr(pid:str,vid:str,payload:dict,user=Depends(identity)):
    access(pid,user,edit=True)
    def callback(c):
        view=db.get(c,'views',vid,pid);page=db.get(c,'pages',view['page_id'],pid)
        existing=c.execute(db.jobs.select().where(db.jobs.c.drawing_id==page['drawing_id'],db.jobs.c.kind=='ocr:'+vid)).mappings().first()
        if existing:raise ValueError('OCR desta vista já enfileirado. Retente o job existente se necessário; edições manuais permanecem protegidas.')
        return db.insert(c,'jobs',pid,{'drawing_id':page['drawing_id'],'kind':'ocr:'+vid,'status':'queued','attempts':0,'cancel_requested':0,'data':{'view_id':vid,'message':'OCR experimental; apenas candidatos revisáveis'}})
    return store.mutate(pid,payload['expected_version'],payload['request_key'],user['name'],'queue:ocr',{'view_id':vid},callback)

@app.post('/api/projects/{pid}/occurrences/{oid}/propose')
def propose(pid:str,oid:str,payload:dict,user=Depends(identity)):
    from .recognition import propose_identity
    access(pid,user,edit=True)
    def callback(c):
        o=db.get(c,'occurrences',oid,pid);v=db.get(c,'views',o['view_id'],pid);p=db.get(c,'piece_types',o['type_id'],pid)
        if o['role']!='installation':raise ValueError('Detalhe típico/referência não recebe identidade física proposta.')
        candidates=[{**i['data'],'id':i['id'],'code':p['code']} for i in db.rows(c,'instances',pid) if i['type_id']==p['id'] and i['state']=='identified']
        proposal=propose_identity(p['code'],candidates,{**v['data'],'reading_confidence':o['data'].get('reading_confidence')})
        return db.insert(c,'proposals',pid,{'occurrence_id':oid,'state':proposal['state'],'data':proposal})
    return store.mutate(pid,payload['expected_version'],payload['request_key'],user['name'],'propose:identity',{'occurrence_id':oid},callback)
@app.post('/api/projects/{pid}/jobs/{jid}/{operation}')
def control_job(pid:str,jid:str,operation:str,payload:dict,user=Depends(identity)):
    access(pid,user,edit=True)
    def callback(c):
        job=db.get(c,'jobs',jid,pid)
        if operation=='cancel':values={'cancel_requested':1,'status':'cancelled' if job['status']=='queued' else job['status']}
        elif operation=='retry':
            if job['status'] not in {'failed','cancelled'}:raise ValueError('Somente jobs falhos/cancelados podem ser repetidos.')
            values={'status':'queued','cancel_requested':0,'attempts':0}
        else:raise ValueError('Ação de job inválida.')
        c.execute(update(db.jobs).where(db.jobs.c.id==jid).values(**values));return db.get(c,'jobs',jid,pid)
    return store.mutate(pid,payload['expected_version'],payload['request_key'],user['name'],'job:'+operation,{'id':jid},callback)
@app.post('/api/projects/{pid}/geometries/{gid}/clip')
def clip(pid:str,gid:str,payload:dict,user=Depends(identity)):
    from shapely.geometry import Polygon,LineString,box
    access(pid,user,edit=True)
    with db.engine.connect() as c:g=db.get(c,'geometries',gid,pid)
    region=box(*payload['box']);paths=[];kind=g['data']['kind']
    for p in g['data']['paths']:
        shape=Polygon(p) if kind in {'polygon','multipolygon'} else LineString(p)
        cut=shape.intersection(region)
        for part in (list(cut.geoms) if hasattr(cut,'geoms') else [cut]):
            if part.is_empty:continue
            if part.geom_type=='Polygon':paths.append([list(x) for x in part.exterior.coords][:-1])
            elif part.geom_type=='LineString':paths.append([list(x) for x in part.coords])
    if not paths:raise ValueError('Recorte não intercepta a geometria.')
    entity={**g,'data':{**g['data'],'paths':paths}}
    return store.save(pid,'geometries',entity,payload['expected_version'],payload['request_key'],user['name'],user['role'])

@app.get('/api/diagnostic')
def diagnostic(user=Depends(identity)):
    if MULTIUSER and user.get('projects')!='*':raise HTTPException(403,'Diagnóstico do corpus exige escopo global.')
    path=ROOT/'reports'/'diagnostico-combio.html'
    if not path.exists():raise HTTPException(404,'Relatório ainda não gerado.')
    return FileResponse(path,media_type='text/html')

FRONTEND=ROOT/'frontend'/'dist'
if FRONTEND.exists():
    app.mount('/assets',StaticFiles(directory=FRONTEND/'assets'),name='assets')
    @app.get('/')
    def index():return FileResponse(FRONTEND/'index.html')
