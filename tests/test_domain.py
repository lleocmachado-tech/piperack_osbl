import json,os,uuid,hashlib,io,zipfile
from pathlib import Path
import pytest
from sqlalchemy import select,update
from backend import db
from backend.service import Store,Conflict
from backend.geometry import matrix,inverse,transform,validate_geometry
from backend.recognition import classify,normalize_code
from backend.measurement import summary
from backend.bom import number_br,extract_blocks
from backend.ingestion import ingest,inspect_header
from backend.exporting import export_bundle,technical_pdf,geometry_visuals
from backend.backup import backup,restore

@pytest.fixture
def system(tmp_path):
    engine=db.make_engine('sqlite:///'+str(tmp_path/'test.db'));db.migrate(engine);store=Store(engine);p=store.create_project('Teste isolado, sem medição real');return store,p['id']
def save(system,kind,entity):
    store,pid=system;s=store.read(pid)
    return store.save(pid,kind,entity,s['project']['version'],db.uid(),'test','local')['result']
def setup_piece(system,code='212-F',quantity=9):
    piece=save(system,'piece_types',{'code':code,'quantity':quantity,'validation':'APPROVED','category':'structure','data':{'reason':'fixture de regra, não homologação real'}})
    store,pid=system;s=store.read(pid);stage=s['stages'][2];stage=save(system,'stages',{**stage,'data':{'approved':True,'dependencies':[]}})
    return piece,stage
def event(system,piece,stage,**values):
    store,pid=system;s=store.read(pid)
    data={'type_id':piece['id'],'stage_id':stage['id'],'reason':'teste','effective_at':'2026-01-01',**values}
    return store.progress(pid,data,s['project']['version'],db.uid(),'test')
def unit(system,piece,index):
    return save(system,'instances',{'type_id':piece['id'],'state':'identified','data':{'location':f'eixo {index}','evidence':'fixture'}})

def test_aggregate_allocation_preserves_total_and_does_not_select_positions(system):
    store,pid=system;piece,stage=setup_piece(system);units=[unit(system,piece,i) for i in range(9)]
    event(system,piece,stage,mode='aggregate',quantity=3)
    s=store.read(pid);assert len(s['progress_events'])==1 and s['progress_events'][0]['instance_id'] is None
    assert summary(s,stage['id'])['completed']==3
    event(system,piece,stage,mode='allocate',instance_ids=[u['id'] for u in units[:3]])
    stat=summary(store.read(pid),stage['id']);assert stat['completed']==3 and stat['rows'][0]['aggregate']==0
    assert len([e for e in store.read(pid)['progress_events'] if e['instance_id']])==3
    with pytest.raises(ValueError):event(system,piece,stage,mode='allocate',instance_ids=[units[0]['id']])
    with pytest.raises(ValueError):event(system,piece,stage,mode='aggregate',quantity=7)

def test_one_of_nine_and_duplicate_views_count_once(system):
    store,pid=system;piece,stage=setup_piece(system);units=[unit(system,piece,i) for i in range(9)]
    event(system,piece,stage,mode='units',instance_ids=[units[0]['id']],value=1)
    stat=summary(store.read(pid),stage['id']);assert stat['completed']==1 and stat['denominator']==9
    assert len(store.read(pid)['progress_events'])==1
    with pytest.raises(ValueError):event(system,piece,stage,mode='units',instance_ids=[units[0]['id'],units[0]['id']],value=1)

def test_208_x_selection_does_not_complete_type(system):
    store,pid=system;p,s=setup_piece(system,'208-X',3);u=unit(system,p,1)
    event(system,p,s,mode='units',instance_ids=[u['id']],value=1)
    assert summary(store.read(pid),s['id'])['completed']==1
    with pytest.raises(ValueError):event(system,p,s,mode='all',confirm_all=False,preview_quantity=3)

def test_idempotency_and_optimistic_conflict(system):
    store,pid=system;p,s=setup_piece(system);before=store.read(pid)['project']['version'];key=db.uid()
    payload={'type_id':p['id'],'stage_id':s['id'],'mode':'aggregate','quantity':3,'reason':'teste','effective_at':'2026-01-01'}
    first=store.progress(pid,payload,before,key,'test');second=store.progress(pid,payload,before,key,'test')
    assert first==second and len(store.read(pid)['progress_events'])==1
    with pytest.raises(Conflict):store.progress(pid,{**payload,'quantity':4},before,db.uid(),'test')
    with pytest.raises(Conflict):store.progress(pid,{**payload,'quantity':4},first['version'],key,'test')

def test_backdated_events_nonnegative_at_every_cutoff(system):
    p,s=setup_piece(system);event(system,p,s,mode='aggregate',quantity=3,effective_at='2026-02-01')
    with pytest.raises(ValueError):event(system,p,s,mode='aggregate',quantity=0,effective_at='2026-01-01')

def test_reversal_of_allocation_atomic_and_audited(system):
    store,pid=system;p,s=setup_piece(system);u=unit(system,p,1);event(system,p,s,mode='aggregate',quantity=3)
    allocated=event(system,p,s,mode='allocate',instance_ids=[u['id']])['result']['events'][0]
    before=store.read(pid)['project']['version'];r=store.reverse(pid,{'event_id':allocated['id'],'reason':'correção','effective_at':'2026-01-01'},before,db.uid(),'test')
    assert len(r['result'])==2
    stat=summary(store.read(pid),s['id']);assert stat['completed']==3 and stat['rows'][0]['aggregate']==3
    with pytest.raises(ValueError):store.reverse(pid,{'event_id':allocated['id'],'reason':'duplo'},r['version'],db.uid(),'test')

@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('scale',[.25,1,3])
def test_coordinate_roundtrip_nonzero_crop(rotation,scale):
    box=[30,40,630,440];m=matrix(box,rotation,scale)
    for p in [(30,40),(630,440),(120.3,260.2)]:
        back=transform(transform(p,m),inverse(m));assert back==pytest.approx(p,abs=1e-8)

@pytest.mark.parametrize('raw',['3-A','3-B','B-B','C-C','+562.800','1234-A','677-200M','200-1'])
def test_annotations_not_codes(raw):assert classify(raw)['kind']=='annotation'
def test_suffix_and_no_ocr_substitution():
    assert normalize_code('208 – ab')=='208-AB';assert classify('208-A')['normalized']!=classify('208-AA')['normalized']
    assert classify('2O8-A')['kind']=='annotation' and classify('2O8-A')['hypotheses']==[]

def test_quantity_approval_and_scope_correction_protect_history(system):
    store,pid=system;p,s=setup_piece(system);event(system,p,s,mode='aggregate',quantity=3)
    with pytest.raises(ValueError):save(system,'piece_types',{**p,'quantity':2,'data':{'reason':'redução'}})
    current=store.read(pid)['piece_types'][0];save(system,'piece_types',{**current,'quantity':10,'data':{'reason':'alteração de escopo aprovada'}})
    assert len(store.read(pid)['progress_events'])==1

def test_provisional_has_no_presumed_location(system):
    p,s=setup_piece(system)
    with pytest.raises(ValueError):save(system,'instances',{'type_id':p['id'],'state':'provisional','data':{'location':'inventada'}})
def test_invalid_geometry_and_leakage():
    with pytest.raises(ValueError):validate_geometry({'kind':'polygon','paths':[[[0,0],[5,5],[0,5],[5,0]]]},[0,0,10,10])
    with pytest.raises(ValueError):validate_geometry({'kind':'line','paths':[[[0,0],[15,0]]]},[0,0,10,10])
def test_unknown_denominator_and_numbers(system):
    store,pid=system;stage=store.read(pid)['stages'][0];stats=summary(store.read(pid),stage['id']);assert stats['percent'] is None
    assert number_br('71.492,30')==71492.3 and number_br('1.090')==1090
    assert number_br('1.090,00')==1090 and number_br('abc') is None

def test_real_bom_candidates_and_conflict_visible():
    import pdfplumber
    root=Path(__file__).resolve().parents[1]
    with pdfplumber.open(root/'Desenhos/677-200M.pdf') as pdf:entries=extract_blocks(pdf.pages[0])
    assert len(entries)==403 and sum(e['quantity'] for e in entries)==859
    assert sum(e['weight'] for e in entries)==69560
    expected={'212-F':9,'208-X':3,'210-F':14,'210-N':1,'224-H':107,'208-AB':5}
    for code,qty in expected.items():assert next(e for e in entries if e['code']==code)['quantity']==qty
    assert 71492.3-sum(e['weight'] for e in entries)==pytest.approx(1932.3)
    assert all(e['approval']=='DRAFT' and e['box_pdf'] for e in entries)

def test_pdf_invalid_and_protected():
    with pytest.raises(ValueError):inspect_header(b'not PDF')
    from pypdf import PdfWriter
    w=PdfWriter();w.add_blank_page(600,400);w.encrypt('secret');out=io.BytesIO();w.write(out)
    with pytest.raises(ValueError,match='protegido'):inspect_header(out.getvalue())

def test_real_pdf_export_original_dimensions_and_snapshot_restore(system):
    store,pid=system;p,s=setup_piece(system);root=Path(__file__).resolve().parents[1]
    content=(root/'Desenhos/677-213M.pdf').read_bytes();before=store.read(pid)['project']['version']
    d=ingest(store,pid,content,'677-213M.pdf','677-213M','0',before,db.uid(),'test')['result']['drawing']
    from backend.worker import inspect_file,commit
    class Output:
        def put(self,value):self.value=value
    output=Output();inspect_file(d['sha256'],output)
    job=store.read(pid)['jobs'][0];commit(store.engine,job,output.value)
    page=store.read(pid)['pages'][0];box=page['data']['cropbox'];x0,y0,x1,y1=box
    view=save(system,'views',{'page_id':page['id'],'name':'Detalhe típico','kind':'typical','data':{'polygon':[[x0,y0],[x1,y0],[x1,y1],[x0,y1]]}})
    geometry=save(system,'geometries',{'page_id':page['id'],'origin':'manual','data':{'kind':'polygon','paths':[[[200,1000],[400,1000],[400,1100],[200,1100]]],'width':2}})
    u=unit(system,p,1)
    with pytest.raises(ValueError,match='(?i)detalhe'):save(system,'occurrences',{'view_id':view['id'],'type_id':p['id'],'geometry_id':geometry['id'],'instance_id':u['id'],'role':'typical','association':'APROVADA','data':{'reason':'fixture'}})
    occ=save(system,'occurrences',{'view_id':view['id'],'type_id':p['id'],'geometry_id':geometry['id'],'role':'typical','association':'APROVADA','data':{'reason':'fixture'}})
    event(system,p,s,mode='aggregate',quantity=3)
    before=store.read(pid)['project']['version'];snap=store.snapshot(pid,{'stage_id':s['id'],'cutoff':'2026-01-01'},before,db.uid(),'test')['result']
    assert geometry_visuals(snap,page['id'])[0]['fill'] is False
    exported=technical_pdf(snap,d)
    from pypdf import PdfReader
    reader=PdfReader(io.BytesIO(exported));original=PdfReader(io.BytesIO(content))
    assert list(reader.pages[0].mediabox)==list(original.pages[0].mediabox) and len(reader.pages)==2
    bundle=zipfile.ZipFile(io.BytesIO(export_bundle(snap)));assert snap['id'].encode() in bundle.read('catalogo.csv')
    html=bundle.read('relatorio-avanco.html').decode();assert 'data:image/png;base64,' in html and '/api/' not in html
    result=restore(store,backup(snap));restored=store.read(result['project_id'])
    assert summary(restored,result['id_mapping'][s['id']])['completed']==3
    assert restored['geometries'][0]['data']==geometry['data']
    assert restored['occurrences'][0]['association']=='APROVADA'
    assert len(restored['progress_events'])==1

def test_dependencies_block_unlocated_progress(system):
    p,s=setup_piece(system);store,pid=system;first=store.read(pid)['stages'][0];s=save(system,'stages',{**s,'data':{'approved':True,'dependencies':[first['id']]}})
    with pytest.raises(ValueError,match='dependências'):event(system,p,s,mode='aggregate',quantity=2)

def test_project_isolation(system):
    store,pid=system;p,s=setup_piece(system);other=store.create_project('Outro')
    with store.engine.connect() as c:
        with pytest.raises(ValueError):db.get(c,'piece_types',p['id'],other['id'])
