import json,math,subprocess,os
from pathlib import Path
import pypdfium2 as pdfium
from PIL import Image
from .config import ROOT,CACHE,ORIGINALS,MAX_RENDER_PIXELS
from .geometry import matrix,transform,inverse
from .recognition import classify,deduplicate

class TesseractEngine:
    name='tesseract.js-7-eng-OEM1-PSM11-experimental'
    def read(self,image_path,orientation=0):
        path=Path(image_path);input_path=path.with_suffix('.input.json');output_path=path.with_suffix('.ocr.json')
        languages=ROOT/'.runtime'/'languages';languages.mkdir(parents=True,exist_ok=True)
        if not (languages/'eng.traineddata').exists() and not (languages/'eng.traineddata.gz').exists():raise ValueError('Modelo OCR ausente. Execute a preparação/benchmark OCR; o worker não baixa modelos automaticamente.')
        input_path.write_text(json.dumps({'cache_path':str(languages),'samples':[{'id':'region','image':str(path),'psm':11}]}),encoding='utf-8')
        process=subprocess.run([os.environ.get('PIPERACK_NODE','node'),str(ROOT/'tools'/'ocr.mjs'),str(input_path),str(output_path)],capture_output=True,timeout=70)
        if process.returncode:raise ValueError('Falha do OCR: '+process.stderr.decode(errors='replace')[-600:])
        return json.loads(output_path.read_text(encoding='utf-8'))[0]['words']

def crop(digest,number,polygon,scale=3):
    with pdfium.PdfDocument(ORIGINALS/(digest+'.pdf')) as doc:
        p=doc[number-1];box=list(p.get_cropbox());rotation=p.get_rotation();m=matrix(box,rotation,1)
        points=[transform(x,m) for x in polygon];x0=min(x[0] for x in points);y0=min(x[1] for x in points);x1=max(x[0] for x in points);y1=max(x[1] for x in points);w,h=p.get_size()
        if (x1-x0)*(y1-y0)*scale**2>MAX_RENDER_PIXELS:raise ValueError('Vista grande demais para OCR. Delimite regiões menores (até 24 milhões de pixels).')
        bitmap=p.render(scale=scale,crop=(x0,h-y1,w-x1,y0));image=bitmap.to_pil().copy();bitmap.close();p.close()
        raster=matrix(box,rotation,scale);raster[4]-=x0*scale;raster[5]-=y0*scale
        return image,raster

def recognize_region(digest,number,polygon):
    engine=TesseractEngine();image,m=crop(digest,number,polygon);all=[]
    # Persistent job is bounded; each tile overlaps 120 pixels and keeps an explicit inverse matrix.
    width,height=image.size
    for top in range(0,height,1480):
        for left in range(0,width,1480):
            tile=image.crop((left,top,min(width,left+1600),min(height,top+1600)))
            for rotation in [0,90,180,270]:
                rotated=tile.rotate(-rotation,expand=True)
                path=CACHE/f'ocr-{digest[:12]}-{number}-{left}-{top}-{rotation}.png';rotated.save(path)
                words=engine.read(path,rotation)
                tw,th=tile.size
                def unrotate(x,y):
                    if rotation==0:return [x+left,y+top]
                    if rotation==90:return [y+left,th-x+top]
                    if rotation==180:return [tw-x+left,th-y+top]
                    return [tw-y+left,x+top]
                for word in words:
                    normalized=classify(word['text'])
                    if normalized['kind']!='piece_candidate':continue
                    b=word['box'];corners=[[b['x0'],b['y0']],[b['x1'],b['y0']],[b['x1'],b['y1']],[b['x0'],b['y1']]]
                    polygon_pdf=[transform(unrotate(*p),inverse(m)) for p in corners]
                    all.append({**normalized,'polygon':polygon_pdf,'confidence':word['confidence']/100,'orientation':rotation,'engine':engine.name,'pdf_to_raster':m,'tile_origin':[left,top],'method':'ocr'})
    return deduplicate(all,tolerance=6)
