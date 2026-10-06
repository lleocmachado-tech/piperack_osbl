import sys,zipfile,io,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.runtime/python'))
from backend import db
from backend.service import Store,effective_today
from backend.exporting import export_bundle
store=Store()
with db.engine.connect() as c:p=dict(c.execute(db.projects.select()).mappings().first())
s=store.read(p['id'])
if len(s['pages'])!=14:raise RuntimeError('Corpus ainda não terminou a inspeção; repetir após o worker.')
snapshot=store.snapshot(p['id'],{'stage_id':s['stages'][2]['id'],'cutoff':effective_today()},s['project']['version'],db.uid(),'exportação inicial do corpus, sem homologação')['result']
content=export_bundle(snapshot);target=ROOT/'reports'/'exemplo-exportacao.zip';target.write_bytes(content)
with zipfile.ZipFile(io.BytesIO(content)) as archive:
    (ROOT/'reports'/'avanco-inicial-combio.html').write_bytes(archive.read('relatorio-avanco.html'))
    (ROOT/'reports'/'snapshot-inicial.json').write_bytes(archive.read('snapshot.json'))
print('Snapshot',snapshot['id'],'sem medição homologada',len(content),'bytes')
