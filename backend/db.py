"""Relational schema shared by SQLite and PostgreSQL; JSON keeps evidence verbatim."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (create_engine, MetaData, Table, Column, String, Integer,
                        Float, JSON, ForeignKey, UniqueConstraint, CheckConstraint, event)
from .config import DATABASE_URL

metadata = MetaData()
def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc).isoformat()

projects = Table('projects', metadata, Column('id',String,primary_key=True),
    Column('name',String,nullable=False),Column('version',Integer,nullable=False,default=1),
    Column('settings',JSON,nullable=False),Column('created_at',String,nullable=False))
tables = {'projects':projects}
def entity(name,*columns,constraints=()):
    table=Table(name,metadata,Column('id',String,primary_key=True),
        Column('project_id',String,ForeignKey('projects.id'),nullable=False,index=True),
        Column('version',Integer,nullable=False,default=1),Column('created_at',String,nullable=False),
        *columns,Column('data',JSON,nullable=False),*constraints)
    tables[name]=table
    return table
def ref(name,target,nullable=True): return Column(name,String,ForeignKey(target+'.id'),nullable=nullable)

stages=entity('stages',Column('name',String,nullable=False),Column('token',String,nullable=False))
drawings=entity('drawings',Column('technical_number',String,nullable=False),Column('revision',String,nullable=False),
    Column('sha256',String,nullable=False),Column('filename',String,nullable=False),ref('previous_id','drawings'),
    constraints=(UniqueConstraint('project_id','sha256'),UniqueConstraint('project_id','technical_number','revision')))
pages=entity('pages',ref('drawing_id','drawings',False),Column('number',Integer,nullable=False),
    constraints=(UniqueConstraint('drawing_id','number'),))
views=entity('views',ref('page_id','pages',False),Column('name',String,nullable=False),Column('kind',String,nullable=False))
piece_types=entity('piece_types',Column('code',String,nullable=False),Column('quantity',Integer),
    Column('validation',String,nullable=False),Column('category',String,nullable=False),
    constraints=(UniqueConstraint('project_id','code'),CheckConstraint('quantity IS NULL OR quantity >= 0')))
bom_entries=entity('bom_entries',ref('page_id','pages',False),ref('type_id','piece_types'),Column('approval',String,nullable=False))
instances=entity('instances',ref('type_id','piece_types',False),Column('state',String,nullable=False))
labels=entity('labels',ref('page_id','pages',False),Column('text',String,nullable=False),Column('method',String,nullable=False))
geometries=entity('geometries',ref('page_id','pages',False),Column('origin',String,nullable=False))
occurrences=entity('occurrences',ref('view_id','views',False),ref('type_id','piece_types',False),
    ref('instance_id','instances'),ref('label_id','labels'),ref('geometry_id','geometries',False),
    Column('role',String,nullable=False),Column('association',String,nullable=False))
proposals=entity('proposals',ref('occurrence_id','occurrences'),Column('state',String,nullable=False))
decisions=entity('decisions',ref('proposal_id','proposals'),ref('occurrence_id','occurrences'),Column('author',String,nullable=False))
progress_events=entity('progress_events',ref('type_id','piece_types',False),ref('instance_id','instances'),
    ref('stage_id','stages',False),Column('delta',Float,nullable=False),Column('effective_at',String,nullable=False),
    Column('author',String,nullable=False),Column('reason',String,nullable=False),Column('group_id',String,nullable=False),
    ref('reverted_event_id','progress_events'),constraints=(UniqueConstraint('project_id','reverted_event_id'),))
overlays=entity('overlays',ref('page_id','pages',False),ref('geometry_id','geometries',False),
    Column('scope',String,nullable=False),ref('occurrence_id','occurrences'),ref('instance_id','instances'),
    ref('type_id','piece_types'),Column('author',String,nullable=False),Column('reason',String,nullable=False))
audit=entity('audit',Column('action',String,nullable=False),Column('author',String,nullable=False),
    Column('request_key',String),constraints=(UniqueConstraint('project_id','request_key'),))
snapshots=entity('snapshots',Column('cutoff',String,nullable=False),ref('stage_id','stages',False))
jobs=entity('jobs',ref('drawing_id','drawings',False),Column('kind',String,nullable=False),
    Column('status',String,nullable=False),Column('attempts',Integer,nullable=False,default=0),
    Column('heartbeat',String),Column('cancel_requested',Integer,nullable=False,default=0),
    constraints=(UniqueConstraint('drawing_id','kind'),))

def make_engine(url=DATABASE_URL):
    engine=create_engine(url,connect_args={'check_same_thread':False,'timeout':30} if url.startswith('sqlite') else {},pool_pre_ping=True)
    if url.startswith('sqlite'):
        @event.listens_for(engine,'connect')
        def pragma(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
    return engine
engine=make_engine()

def migrate(target=engine):
    # Explicit ordered version, also exercised through Alembic's initial revision.
    from sqlalchemy import text
    with target.begin() as conn:
        conn.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at VARCHAR NOT NULL)'))
        versions={r[0] for r in conn.execute(text('SELECT version FROM schema_migrations'))}
        if 1 not in versions:
            metadata.create_all(conn)
            conn.execute(text('INSERT INTO schema_migrations(version,applied_at) VALUES(1,:at)'),{'at':now()})

def rows(conn,name,project_id):
    table=tables[name]
    return [dict(r) for r in conn.execute(table.select().where(table.c.project_id==project_id)).mappings()]
def get(conn,name,id,project_id):
    table=tables[name]
    row=conn.execute(table.select().where(table.c.id==id,table.c.project_id==project_id)).mappings().first()
    if row is None: raise ValueError(f'Referência inexistente neste projeto: {name}/{id}')
    return dict(row)
def insert(conn,name,project_id,values):
    record={'id':uid(),'project_id':project_id,'version':1,'created_at':now(),'data':{},**values}
    conn.execute(tables[name].insert().values(**record))
    return record
