"""Seed only an isolated visual-test database; no project measurements are changed."""
import os, sys, json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'.runtime/python'),str(root)]
if not os.environ.get('PIPERACK_DATA') or Path(os.environ['PIPERACK_DATA']).resolve().parent != (root/'tmp').resolve():
    raise RuntimeError('PIPERACK_DATA must name an isolated directory directly under project tmp.')
from backend import db
from backend.service import Store
from backend.ingestion import save_original
from pypdf import PdfReader
db.migrate();store=Store();pid=store.create_project('Teste visual isolado — marcação de campo')['id']
source=root/'Desenhos/677-208M.pdf';digest=save_original(source.read_bytes());raw=PdfReader(source).pages[0]
with db.engine.begin() as c:
    d=db.insert(c,'drawings',pid,{'technical_number':'TESTE-208M','revision':'0','sha256':digest,'filename':source.name,'data':{}})
    db.insert(c,'pages',pid,{'drawing_id':d['id'],'number':1,'data':{'cropbox':list(map(float,raw.cropbox)),'mediabox':list(map(float,raw.mediabox)),'rotation':0,'width':float(raw.mediabox.width),'height':float(raw.mediabox.height),'characters':0}})
    db.insert(c,'piece_types',pid,{'code':'212-F','quantity':9,'validation':'DRAFT','category':'structure','data':{'description':'VIGA · fixture de teste, sem homologação real'}})
print(json.dumps({'project_id':pid,'isolated_data':os.environ['PIPERACK_DATA']}))
