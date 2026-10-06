import hashlib, io, os, tempfile
from pathlib import Path
from pypdf import PdfReader
from sqlalchemy import update
from . import db
from .config import ORIGINALS,MAX_FILE_BYTES,MAX_PAGES,MAX_PAGE_POINTS

def inspect_header(content):
    if len(content)>MAX_FILE_BYTES: raise ValueError('Limite de 40 MB por PDF.')
    if not content.startswith(b'%PDF-'): raise ValueError('Arquivo inválido: cabeçalho PDF ausente.')
    try:
        reader=PdfReader(io.BytesIO(content),strict=True)
        if reader.is_encrypted: raise ValueError('PDF protegido: envie uma cópia autorizada sem senha.')
        if not 0<len(reader.pages)<=MAX_PAGES: raise ValueError('PDF excede limite de 50 páginas ou está vazio.')
        for p in reader.pages:
            if any(abs(float(x))>MAX_PAGE_POINTS for x in p.mediabox): raise ValueError('Dimensões do PDF excedem limite de recursos.')
            if int(p.get('/UserUnit',1))!=1: raise ValueError('PDF com UserUnit diferente de 1 não suportado neste MVP.')
    except ValueError: raise
    except Exception as error: raise ValueError('PDF inválido ou corrompido: '+type(error).__name__)
    return hashlib.sha256(content).hexdigest()

def save_original(content):
    digest=inspect_header(content)
    target=ORIGINALS/(digest+'.pdf')
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest()!=digest: raise ValueError('Integridade do armazenamento original violada.')
    else:
        with tempfile.NamedTemporaryFile(dir=ORIGINALS,delete=False) as f:
            f.write(content);temporary=f.name
        try:
            # Exclusive creation prevents accidental replacement even across simultaneous uploads.
            with target.open('xb') as output: output.write(Path(temporary).read_bytes())
        except FileExistsError: pass
        finally: Path(temporary).unlink(missing_ok=True)
    return digest

def ingest(store,pid,content,filename,technical_number,revision,expected,key,author,previous_id=None):
    if not technical_number.strip() or not revision.strip(): raise ValueError('Número técnico e revisão são obrigatórios; o nome de arquivo não basta.')
    digest=save_original(content)
    payload={'sha256':digest,'filename':Path(filename).name,'technical_number':technical_number,'revision':revision,'previous_id':previous_id}
    def operation(c):
        same=c.execute(db.drawings.select().where(db.drawings.c.project_id==pid,db.drawings.c.sha256==digest)).mappings().first()
        if same: return {'drawing':dict(same),'duplicate':True}
        if previous_id:
            previous=db.get(c,'drawings',previous_id,pid)
            if previous['technical_number']!=technical_number: raise ValueError('Revisão anterior tem número técnico diferente.')
            c.execute(update(db.drawings).where(db.drawings.c.id==previous_id).values(data={**previous['data'],'superseded':True},version=previous['version']+1))
        drawing=db.insert(c,'drawings',pid,{**payload,'data':{'original_immutable':True,'migration_pending':bool(previous_id),'identity_source':'user-declared','superseded':False}})
        job=db.insert(c,'jobs',pid,{'drawing_id':drawing['id'],'kind':'inspect','status':'queued','attempts':0,'cancel_requested':0,'data':{'progress':0,'message':'Aguardando worker'}})
        if previous_id:
            db.insert(c,'proposals',pid,{'state':'AMBÍGUA','data':{'kind':'revision_migration','drawing_id':drawing['id'],'previous_id':previous_id,'blocking':['Nova revisão exige revalidação. Não transportar geometria por coordenadas.'],'candidates':[],'algorithm':'revision-review-1'}})
        return {'drawing':drawing,'job':job,'duplicate':False}
    return store.mutate(pid,expected,key,author,'upload',payload,operation)
