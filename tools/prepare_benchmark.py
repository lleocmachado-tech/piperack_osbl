import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports'/'evidence'/'ocr';OUT.mkdir(parents=True,exist_ok=True)
entries=json.loads((ROOT/'reports/evidence/bom-candidates.json').read_text(encoding='utf-8'))
samples=[]
for code in ['208-AB','212-F']:
    e=next(e for e in entries if e['code']==code);b=e['column_boxes'][0]['box_pdf'];height=1683.7795
    samples.append({'id':'bom-'+code,'drawing':200,'box_pdf':[b[0]-3,b[1]-3,b[2]+3,b[3]+3],'expected':[code],'split':'calibration'})
# These bounding crops are based on direct visual reading of the rendered drawings.
for id,drawing,pixel_box,expected in [
    ('view-212F-208',208,[596,84,638,113],['212-F']),
    ('typical-224G-213',213,[194,432,239,454],['224-G']),
    ('axis-3A-208',208,[658,54,704,78],[]),
    ('cut-BB-205',205,[370,234,448,251],[])]:
    # Thumbnail scale .55, raw PDF origin bottom-left. Actual page height comes from inventory.
    inventory=json.loads((ROOT/'reports/evidence/inventory.json').read_text(encoding='utf-8'))
    h=next(x for x in inventory if x['file']==f'677-{drawing}M.pdf')['pages'][0]['mediabox'][3]
    x0,y0,x1,y1=pixel_box;samples.append({'id':id,'drawing':drawing,'box_pdf':[x0/.55,h-y1/.55,x1/.55,h-y0/.55],'expected':expected,'split':'evaluation'})
import pypdfium2 as pdfium
jobs=[]
for sample in samples:
    path=ROOT/'Desenhos'/f'677-{sample["drawing"]}M.pdf';sample['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();sample['page']=1;sample['review_state']='initial visual label, calibration not homologation'
    with pdfium.PdfDocument(path) as doc:
        p=doc[0];w,h=p.get_size();x0,y0,x1,y1=sample['box_pdf'];bmp=p.render(scale=4,crop=(x0,y0,w-x1,h-y1));im=bmp.to_pil().copy();bmp.close();p.close()
    im.save(OUT/(sample['id']+'.png'))
    for rotation in [0,90,180,270]:
        rotated=im.rotate(-rotation,expand=True);image_path=OUT/f'{sample["id"]}-{rotation}.png';rotated.save(image_path)
        for psm in [7,11]:jobs.append({'id':f'{sample["id"]}:{rotation}','image':str(image_path),'psm':psm})
languages=ROOT/'.runtime/languages';languages.mkdir(parents=True,exist_ok=True)
(OUT/'corpus.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'input.json').write_text(json.dumps({'cache_path':str(languages),'samples':jobs},ensure_ascii=False),encoding='utf-8')
print('Prepared',len(jobs),'OCR runs')
