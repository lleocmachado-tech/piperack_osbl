"""Discovery on original PDFs; no BOM or association approval is implied."""
import hashlib, json, time, sys
from pathlib import Path
import pdfplumber, pypdfium2 as pdfium
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports' / 'evidence'
OUT.mkdir(parents=True, exist_ok=True)
results = []
for number in range(200, 214):
    path = ROOT / 'Desenhos' / f'677-{number}M.pdf'
    if not path.exists():
        results.append({'file': path.name, 'missing': True}); continue
    started = time.perf_counter()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    reader = PdfReader(path)
    document = pdfium.PdfDocument(path)
    item = {'file':path.name, 'sha256':digest, 'bytes':path.stat().st_size,
            'pages':[], 'method':'pypdf + pdfplumber (native positions/objects) + PDFium render',
            'inspection':'native/objects and rendered image; technical classification awaits visual review'}
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages):
            raw = reader.pages[index]
            text = page.extract_text() or ''
            (OUT / f'{number}-{index+1}.txt').write_text(text, encoding='utf-8')
            words = page.extract_words()
            (OUT / f'{number}-{index+1}-words.json').write_text(json.dumps(words,ensure_ascii=False),encoding='utf-8')
            native = []
            for char in page.chars:
                native.append({k:char.get(k) for k in ['text','x0','x1','top','bottom','upright','matrix']})
            (OUT / f'{number}-{index+1}-chars.json').write_text(json.dumps(native,ensure_ascii=False),encoding='utf-8')
            render_start = time.perf_counter()
            bitmap = document[index].render(scale=.55)
            image = bitmap.to_pil()
            image.save(OUT / f'{number}-{index+1}.png')
            high = document[index].render(scale=1.5).to_pil()
            high.save(OUT / f'{number}-{index+1}-detail.png')
            entry = {'page':index+1,'mediabox':list(map(float,raw.mediabox)),
                     'cropbox':list(map(float,raw.cropbox)), 'rotation':int(raw.get('/Rotate',0)),
                     'characters':len(page.chars),'words':len(words),'images':len(page.images),
                     'objects':{k:len(v) for k,v in page.objects.items()},
                     'text_sample':text[:2400], 'render_seconds':round(time.perf_counter()-render_start,3),
                     'thumbnail':f'{number}-{index+1}.png',
                     'native_code_tokens':sorted(set(__import__('re').findall(r'(?<!\d)\d{3}-[A-Z]{1,}(?![A-Z])',text))),
                     'coverage':'insufficient for code recognition' if len(page.chars)<100 else 'partial native coverage; code coverage requires review'}
            item['pages'].append(entry)
    item['inspection_seconds'] = round(time.perf_counter()-started,3)
    try:
        import psutil
        item['process_rss_mb'] = round(psutil.Process().memory_info().rss/1024**2,1)
    except ImportError: pass
    results.append(item)
    print(path.name, len(item['pages']), item['pages'][0]['characters'], flush=True)
    (OUT / 'inventory.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved', OUT, flush=True)
