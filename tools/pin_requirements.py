import sys,importlib.metadata as m
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'.runtime/python'))
names=['fastapi','uvicorn','SQLAlchemy','alembic','python-multipart','pypdfium2','pdfplumber','pypdf','shapely','reportlab','psutil','psycopg','pytest','httpx']
lines=[f'{name+"[binary]" if name=="psycopg" else name}=={m.version(name)}' for name in names]
(ROOT/'requirements.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8');print('\n'.join(lines))
