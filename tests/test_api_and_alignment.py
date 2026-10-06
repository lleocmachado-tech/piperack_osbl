import io,hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter,PdfReader
from pypdf.generic import RectangleObject,NameObject,NumberObject
import pypdfium2 as pdfium
from backend import db
from backend.service import Store
from backend.ingestion import save_original
from backend.exporting import technical_pdf
from backend.geometry import matrix,transform

@pytest.fixture
def client(tmp_path,monkeypatch):
    import backend.main as main
    engine=db.make_engine('sqlite:///'+str(tmp_path/'api.db'));db.migrate(engine);monkeypatch.setattr(db,'engine',engine);monkeypatch.setattr(main,'store',Store(engine));monkeypatch.setattr(main,'MULTIUSER',False)
    with TestClient(main.app) as client:yield client

def test_http_upload_invalid_duplicate_and_concurrent_edit(client):
    project=client.post('/api/projects',json={'name':'Teste HTTP isolado'}).json();pid=project['id']
    response=client.post(f'/api/projects/{pid}/drawings',files={'file':('bad.pdf',b'not PDF','application/pdf')},data={'technical_number':'677-208M','revision':'0','expected_version':1,'request_key':db.uid()})
    assert response.status_code==422 and 'inválido' in response.json()['detail']
    real=(Path(__file__).resolve().parents[1]/'Desenhos/677-208M.pdf').read_bytes()
    data={'technical_number':'677-208M','revision':'0','expected_version':1,'request_key':db.uid()}
    first=client.post(f'/api/projects/{pid}/drawings',files={'file':('677-208M.pdf',real,'application/pdf')},data=data)
    assert first.status_code==200
    data['expected_version']=2;data['request_key']=db.uid()
    second=client.post(f'/api/projects/{pid}/drawings',files={'file':('renamed.pdf',real,'application/pdf')},data=data)
    assert second.status_code==200 and second.json()['result']['duplicate']
    assert len(client.get(f'/api/projects/{pid}/state').json()['drawings'])==1
    stale=client.post(f'/api/projects/{pid}/entities/piece_types',json={'entity':{'code':'212-F','quantity':9,'validation':'DRAFT','category':'structure','data':{}},'expected_version':1,'request_key':db.uid()})
    assert stale.status_code==409
    missing=client.post(f'/api/projects/{pid}/progress',json={});assert missing.status_code==422

def test_http_roles_and_project_isolation(client,monkeypatch):
    import backend.main as main
    p=client.post('/api/projects',json={'name':'Papéis'}).json();pid=p['id'];monkeypatch.setattr(main,'MULTIUSER',True)
    monkeypatch.setattr(main,'USERS',{'read':{'name':'leitor','role':'reader','projects':[pid]},'edit':{'name':'editor','role':'editor','projects':[pid]},'other':{'name':'outro','role':'reader','projects':[]}})
    assert client.get(f'/api/projects/{pid}/state').status_code==401
    assert client.get(f'/api/projects/{pid}/state',headers={'Authorization':'Bearer other'}).status_code==403
    assert client.get(f'/api/projects/{pid}/state',headers={'Authorization':'Bearer read'}).status_code==200
    payload={'entity':{'code':'212-F','quantity':9,'validation':'APPROVED','category':'structure','data':{'reason':'tentativa'}},'expected_version':1,'request_key':db.uid()}
    assert client.post(f'/api/projects/{pid}/entities/piece_types',json=payload,headers={'Authorization':'Bearer read'}).status_code==403
    assert client.post(f'/api/projects/{pid}/entities/piece_types',json=payload,headers={'Authorization':'Bearer edit'}).status_code==422

@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_export_alignment_raw_pdf_crop_rotation(rotation):
    # Synthetic isolates transform math; real pages are tested elsewhere.
    writer=PdfWriter();page=writer.add_blank_page(600,400);page.mediabox=RectangleObject([10,20,610,420]);page.cropbox=RectangleObject([40,60,580,400]);page[NameObject('/Rotate')]=NumberObject(rotation)
    buf=io.BytesIO();writer.write(buf);content=buf.getvalue();digest=save_original(content)
    points=[[200,160],[300,160],[300,220],[200,220]]
    drawing={'id':'drawing','sha256':digest,'technical_number':'TESTE','revision':'0'}
    state={'project':{'name':'Teste geométrico isolado','settings':{},'created_at':db.now()},'drawings':[drawing],
        'pages':[{'id':'page','drawing_id':'drawing','number':1}],
        'views':[{'id':'view','page_id':'page'}],
        'geometries':[{'id':'geometry','data':{'kind':'polygon','paths':[points],'width':2}}],
        'occurrences':[{'view_id':'view','type_id':'piece','instance_id':'unit','geometry_id':'geometry','role':'installation','association':'APROVADA'}],
        'progress_events':[{'type_id':'piece','stage_id':'stage','instance_id':'unit','delta':1,'effective_at':'2026-01-01'}],
        'stages':[{'id':'stage','name':'Montagem','token':'sucesso'}],'overlays':[]}
    snapshot={'id':db.uid(),'cutoff':'2026-01-01','stage_id':'stage','created_at':db.now(),'data':{'state':state,'summary':{'scope_categories':['structure'],'denominator':1,'completed':1}}}
    exported=technical_pdf(snapshot,drawing)
    original=PdfReader(io.BytesIO(content));result=PdfReader(io.BytesIO(exported))
    assert list(result.pages[0].mediabox)==list(original.pages[0].mediabox)
    assert list(result.pages[0].cropbox)==list(original.pages[0].cropbox)
    assert result.pages[0].get('/Rotate',0)==rotation
    with pdfium.PdfDocument(exported) as pdf:
        bmp=pdf[0].render(scale=2);image=bmp.to_pil().convert('RGB');bmp.close()
    expected=transform([250,190],matrix([40,60,580,400],rotation,2));pixel=image.getpixel(tuple(round(v) for v in expected))
    assert pixel[1]>pixel[0]+10 and pixel[1]>pixel[2]+5
    import numpy as np
    pixels=np.array(image).astype(int);mask=(pixels[:,:,1]>pixels[:,:,0]+10)&(pixels[:,:,1]>pixels[:,:,2]+5);ys,xs=np.where(mask)
    corners=[transform(p,matrix([40,60,580,400],rotation,2)) for p in points]
    expected_bbox=[min(p[0] for p in corners)-2,min(p[1] for p in corners)-2,max(p[0] for p in corners)+2,max(p[1] for p in corners)+2]
    assert [int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1]==pytest.approx(expected_bbox,abs=1)
    # Outside the polygon is untouched white (content fidelity on blank test page).
    outside=transform([120,100],matrix([40,60,580,400],rotation,2))
    assert min(image.getpixel(tuple(round(v) for v in outside)))>245
