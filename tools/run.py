"""Launcher supports a normal venv or the Codex workspace runtime."""
import os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
local=root/'.runtime'/'python'
if local.exists():sys.path.insert(0,str(local))
sys.path.insert(0,str(root))
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('command',choices=['api','worker','seed','test','diagnostic']);args=p.parse_args()
    if args.command=='api':
        import uvicorn
        uvicorn.run('backend.main:app',host='127.0.0.1',port=int(os.environ.get('PIPERACK_PORT','8765')))
    elif args.command=='worker':
        from backend.worker import main
        sys.argv=[sys.argv[0]];main()
    elif args.command=='test':
        import pytest
        import uuid
        (root/'tmp').mkdir(exist_ok=True)
        raise SystemExit(pytest.main(['tests','-q','--tb=short','--basetemp',str(root/'tmp'/('pytest-'+uuid.uuid4().hex))]))
    elif args.command=='seed':__import__('runpy').run_path(str(root/'tools'/'seed_corpus.py'),run_name='__main__')
    else:__import__('runpy').run_path(str(root/'tools'/'build_diagnostic.py'),run_name='__main__')
