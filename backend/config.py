import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('PIPERACK_DATA', ROOT / 'data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
ORIGINALS = DATA / 'originals'
CACHE = DATA / 'cache'
ORIGINALS.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)
DATABASE_URL = os.environ.get('DATABASE_URL', f'sqlite:///{DATA / "piperack.db"}')
MAX_FILE_BYTES = 40 * 1024 * 1024
MAX_PAGES = 50
MAX_PAGE_POINTS = 14400
MAX_RENDER_PIXELS = 24_000_000
PROCESS_VERSION = 'manual-1.0'
TIMEZONE = 'America/Sao_Paulo'
