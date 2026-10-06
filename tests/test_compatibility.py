import os,uuid
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql,sqlite
import pytest
from backend import db
from backend.service import Store

@pytest.mark.parametrize('dialect',[postgresql.dialect(),sqlite.dialect()])
def test_schema_compiles_for_both_databases(dialect):
    for table in db.metadata.sorted_tables:
        ddl=str(CreateTable(table).compile(dialect=dialect));assert 'CREATE TABLE' in ddl

@pytest.mark.skipif(not os.environ.get('TEST_DATABASE_URL'),reason='Instância PostgreSQL não fornecida; execução não homologada.')
def test_postgres_transaction_and_idempotency():
    engine=db.make_engine(os.environ['TEST_DATABASE_URL']);db.migrate(engine);store=Store(engine);project=store.create_project('Validação PostgreSQL '+uuid.uuid4().hex)
    payload={'code':'212-F','quantity':9,'validation':'APPROVED','category':'structure','data':{'reason':'teste de compatibilidade'}};key=db.uid()
    a=store.save(project['id'],'piece_types',payload,1,key,'test','local');b=store.save(project['id'],'piece_types',payload,1,key,'test','local')
    assert a==b and len(store.read(project['id'])['piece_types'])==1
