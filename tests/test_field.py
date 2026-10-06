import pytest
from backend import db
from backend.service import Store, Conflict
from backend.field import mark
from backend.measurement import summary


@pytest.fixture
def field(tmp_path):
    engine=db.make_engine('sqlite:///'+str(tmp_path/'field.db'));db.migrate(engine)
    store=Store(engine);pid=store.create_project('Teste isolado de campo')['id']
    with engine.begin() as c:
        drawing=db.insert(c,'drawings',pid,{'technical_number':'TEST-201','revision':'0','sha256':'test','filename':'test.pdf','data':{}})
        page=db.insert(c,'pages',pid,{'drawing_id':drawing['id'],'number':1,'data':{'cropbox':[0,0,600,400]}})
        piece=db.insert(c,'piece_types',pid,{'code':'212-F','quantity':9,'validation':'DRAFT','category':'structure','data':{}})
    stage=next(s for s in store.read(pid)['stages'] if s['name']=='Montagem')
    payload={'type_id':piece['id'],'stage_id':stage['id'],'page_id':page['id'],
             'geometry':{'kind':'polygon','paths':[[[100,100],[200,100],[200,140],[100,140]]],'width':6},
             'location':'Rack 2 eixo B/4','reason':'Vistoria fictícia de teste','value':1,
             'effective_at':'2026-01-01','quantity':9,'approve_quantity':True,'approve_stage':True,'confirm_installation':True}
    return store,pid,payload


def apply(field, **changes):
    store,pid,payload=field
    return mark(store,pid,{**payload,**changes},store.read(pid)['project']['version'],db.uid(),'test','local')


def test_field_atomic_manual_approval_and_idempotency(field):
    store,pid,payload=field;key=db.uid();version=store.read(pid)['project']['version']
    result=mark(store,pid,payload,version,key,'test','local')
    assert result==mark(store,pid,payload,version,key,'test','local')
    state=store.read(pid)
    assert state['project']['version']==version+1
    assert len(state['audit'])==len(state['instances'])==len(state['occurrences'])==len(state['geometries'])==len(state['decisions'])==1
    assert state['piece_types'][0]['validation']=='APPROVED'
    assert summary(state,payload['stage_id'])['completed']==1
    assert summary(state,payload['stage_id'])['denominator']==9
    assert state['occurrences'][0]['instance_id']==result['result']['instance_id']
    with pytest.raises(Conflict):mark(store,pid,{**payload,'location':'outra'},version,key,'test','local')


@pytest.mark.parametrize('changes',[
    {'approve_quantity':False}, {'approve_stage':False}, {'confirm_installation':False},
    {'quantity':0}, {'location':''}, {'value':3}, {'effective_at':'2999-01-01','value':0},
    {'geometry':{'kind':'polygon','paths':[[[-1,0],[20,0],[20,20]]],'width':6}},
])
def test_field_failure_rolls_back_everything(field,changes):
    store,pid,_=field;before=store.read(pid)
    with pytest.raises(ValueError):apply(field,**changes)
    assert store.read(pid)==before


def test_same_unit_in_two_views_does_not_double_count(field):
    store,pid,payload=field;first=apply(field)['result']
    second=apply(field,instance_id=first['instance_id'],geometry={'kind':'polygon','paths':[[[220,100],[260,100],[260,140],[220,140]]],'width':6})
    state=store.read(pid)
    assert len(state['occurrences'])==2 and len(state['instances'])==1 and len(state['progress_events'])==1
    assert first['instance_id']==second['result']['instance_id']
    assert summary(state,payload['stage_id'])['completed']==1
    with pytest.raises(ValueError,match='já existe'):apply(field)


def test_field_allocation_preserves_existing_total(field):
    store,pid,payload=field;first=apply(field,value=0)['result'];state=store.read(pid)
    store.progress(pid,{'type_id':payload['type_id'],'stage_id':payload['stage_id'],'mode':'aggregate','quantity':3,'reason':'fixture','effective_at':'2026-01-01'},state['project']['version'],db.uid())
    apply(field,instance_id=first['instance_id'],allocate=True)
    state=store.read(pid);result=summary(state,payload['stage_id'])
    assert result['completed']==3 and result['rows'][0]['aggregate']==2


def test_field_rejects_typical_region_and_unauthorized_approval(field):
    store,pid,payload=field
    with pytest.raises(ValueError):mark(store,pid,payload,1,db.uid(),'editor','editor')
    with store.engine.begin() as c:
        db.insert(c,'views',pid,{'page_id':payload['page_id'],'name':'Detalhe típico','kind':'typical','data':{'polygon':[[0,0],[400,0],[400,300],[0,300]]}})
    before=store.read(pid)
    with pytest.raises(ValueError,match='detalhe'):apply(field)
    assert store.read(pid)==before


def test_field_checks_dependencies_and_project_scope(field):
    store,pid,payload=field
    with store.engine.begin() as c:
        stage=db.get(c,'stages',payload['stage_id'],pid)
        dependency=next(s for s in db.rows(c,'stages',pid) if s['id']!=stage['id'])
        c.execute(db.stages.update().where(db.stages.c.id==stage['id']).values(data={**stage['data'],'dependencies':[dependency['id']]}))
    before=store.read(pid)
    with pytest.raises(ValueError,match='Dependência'):apply(field)
    assert store.read(pid)==before
    other=store.create_project('Outro projeto')['id']
    with pytest.raises(ValueError):mark(store,other,payload,1,db.uid(),'test','local')
