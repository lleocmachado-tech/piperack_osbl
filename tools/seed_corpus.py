"""Ingest the real corpus, but never approve BOM, locations or measurement."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import db
from backend.service import Store
from backend.ingestion import ingest
from backend.config import ROOT
db.migrate();store=Store()
with db.engine.connect() as c:
    existing=c.execute(db.projects.select()).mappings().first()
project=dict(existing) if existing else store.create_project('Obra 677 · PipeRack OSBL · Rhodia Paulínia')
for n in range(200,214):
    path=ROOT/'Desenhos'/f'677-{n}M.pdf'
    if not path.exists():continue
    state=store.read(project['id'])
    if any(d['sha256']==__import__('hashlib').sha256(path.read_bytes()).hexdigest() for d in state['drawings']):continue
    ingest(store,project['id'],path.read_bytes(),path.name,f'677-{n}M','0',state['project']['version'],f'corpus-677-{n}-v1','inspeção visual do carimbo')
    print('Enfileirado',path.name,flush=True)
print(project['id'])
