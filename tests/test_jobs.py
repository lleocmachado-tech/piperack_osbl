from sqlalchemy import update
from backend import db
from backend.service import Store
from backend.worker import commit,claim

def test_failed_ocr_retry_preserves_region_and_does_not_touch_manual_edit(tmp_path):
    engine=db.make_engine('sqlite:///'+str(tmp_path/'jobs.db'));db.migrate(engine);store=Store(engine);p=store.create_project('Teste de job')
    with engine.begin() as c:
        drawing=db.insert(c,'drawings',p['id'],{'technical_number':'TEST','revision':'0','sha256':'test-hash','filename':'test.pdf','data':{}})
        job=db.insert(c,'jobs',p['id'],{'drawing_id':drawing['id'],'kind':'ocr:view-id','status':'running','attempts':1,'heartbeat':'2020-01-01','cancel_requested':0,'data':{'view_id':'view-id','message':'processando'}})
    claimed=claim(engine);assert claimed['data']['view_id']=='view-id'
    commit(engine,claimed,{'ok':False,'error':'modelo ausente'})
    with engine.connect() as c:row=db.get(c,'jobs',job['id'],p['id'])
    assert row['status']=='failed' and row['data']['view_id']=='view-id'
