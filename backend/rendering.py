import hashlib,json,io
import pypdfium2 as pdfium
from PIL import Image
from .config import ORIGINALS,CACHE,MAX_RENDER_PIXELS,PROCESS_VERSION
from .geometry import matrix

def render(digest,page_number,dpi=96,rotation=0):
    if dpi not in {40,72,96,144,216}: raise ValueError('Resolução não autorizada.')
    if rotation not in {0,90,180,270}: raise ValueError('Rotação inválida.')
    key=hashlib.sha256(f'{digest}:{page_number}:{dpi}:{rotation}:{PROCESS_VERSION}'.encode()).hexdigest()
    target=CACHE/(key+'.png')
    if not target.exists():
        with pdfium.PdfDocument(ORIGINALS/(digest+'.pdf')) as document:
            page=document[page_number-1];w,h=page.get_size()
            if w*h*(dpi/72)**2>MAX_RENDER_PIXELS: raise ValueError('Renderização excede 24 milhões de pixels. Use resolução menor ou recorte.')
            bitmap=page.render(scale=dpi/72,rotation=rotation)
            image=bitmap.to_pil();image.save(target)
            bitmap.close();page.close()
    return target
