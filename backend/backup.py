import base64,hashlib,json
from sqlalchemy import update
from . import db
from .ingestion import save_original
from .config import ORIGINALS
from .service import Store

def backup(snapshot):
    return {'format':'combio-piperack-backup','schema_version':1,'snapshot':snapshot,
        'originals':{d['sha256']:base64.b64encode((ORIGINALS/(d['sha256']+'.pdf')).read_bytes()).decode() for d in snapshot['data']['state']['drawings']}}

def restore(store,content,author='local'):
    if content.get('format')!='combio-piperack-backup' or content.get('schema_version')!=1: raise ValueError('Backup incompatível. Versão esperada: 1.')
    state=content['snapshot']['data']['state']
    for drawing in state['drawings']:
        original=content.get('originals',{}).get(drawing['sha256'])
        if original:
            if save_original(base64.b64decode(original,validate=True))!=drawing['sha256']: raise ValueError('Hash do original divergente.')
        elif not (ORIGINALS/(drawing['sha256']+'.pdf')).exists(): raise ValueError('PDF original ausente no backup/armazenamento.')
    old_ids=[state['project']['id']]+[r['id'] for name,records in state.items() if name!='project' for r in records]
    if len(set(old_ids))!=len(old_ids):raise ValueError('IDs duplicados no backup.')
    mapping={id:db.uid() for id in old_ids};pid=mapping[state['project']['id']]
    def replace(value):
        if isinstance(value,str):return mapping.get(value,value)
        if isinstance(value,list):return [replace(x) for x in value]
        if isinstance(value,dict):return {k:replace(v) for k,v in value.items()}
        return value
    order=['stages','drawings','pages','views','piece_types','bom_entries','instances','labels','geometries','occurrences','proposals','decisions','progress_events','overlays','audit','jobs']
    with store.engine.begin() as c:
        p=replace(state['project']);p['name']+=' · restaurado';p['settings']={**p['settings'],'restored_from':state['project']['id'],'auto_approval':False};p['version']=1
        c.execute(db.projects.insert().values(**p))
        for name in order:
            pending=list(state.get(name,[]))
            # Topological insertion for revisions and reversed events.
            inserted=set()
            while pending:
                batch=[r for r in pending if not r.get('previous_id') and not r.get('reverted_event_id') or (r.get('previous_id') or r.get('reverted_event_id')) in inserted]
                if not batch:raise ValueError('Ciclo/referência ausente no backup.')
                for row in batch:
                    record=replace(row)
                    if name=='jobs' and record['status'] in {'running','queued'}:record['status']='cancelled'
                    c.execute(db.tables[name].insert().values(**record));inserted.add(row['id']);pending.remove(row)
        # Re-run reference/quantity/geometry rules before committing imported approvals.
        for name in ['piece_types','instances','views','labels','geometries','occurrences','overlays','stages','bom_entries']:
            for row in db.rows(c,name,pid): store.validate(c,pid,name,row,row,'local')
        store.validate_balances(db.rows(c,'progress_events',pid),{p['id']:p for p in db.rows(c,'piece_types',pid)})
        db.insert(c,'audit',pid,{'action':'restore','author':author,'data':{'snapshot_id':content['snapshot']['id'],'original_project_id':state['project']['id'],'id_mapping':mapping}})
    return {'project_id':pid,'id_mapping':mapping}
