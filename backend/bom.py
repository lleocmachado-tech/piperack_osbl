"""Position-based extraction; extracted rows remain unapproved candidates."""
import re
from decimal import Decimal, InvalidOperation
from .recognition import CODE,normalize_code

def number_br(value):
    if value is None or value=='': return None
    if isinstance(value,(float,int)): return float(value)
    text=str(value).strip().replace('kg','').replace(' ','')
    if ',' in text: text=text.replace('.','').replace(',','.')
    elif re.fullmatch(r'\d{1,3}(\.\d{3})+',text):text=text.replace('.','')
    try: return float(Decimal(text))
    except InvalidOperation: return None

def extract_blocks(page):
    words=page.extract_words(x_tolerance=1,y_tolerance=1)
    anchors=[w for w in words if CODE.fullmatch(normalize_code(w['text']))]
    # Column starts are clustered; exclude diagram index (677-200M has a digit suffix).
    clusters=[]
    for word in sorted(anchors,key=lambda w:w['x0']):
        cluster=next((c for c in clusters if abs(c[0]['x0']-word['x0'])<8),None)
        if cluster is None: clusters.append([word])
        else: cluster.append(word)
    starts=sorted(c[0]['x0'] for c in clusters if len(c)>8)
    result=[]
    for column,start in enumerate(starts):
        end=next((x for x in starts if x>start+8),page.width-50)
        for anchor in anchors:
            if abs(anchor['x0']-start)>8: continue
            line=[w for w in words if start-1<=w['x0']<end-2 and abs(w['top']-anchor['top'])<3]
            line.sort(key=lambda w:w['x0'])
            tokens=[w['text'] for w in line]
            # Expected fields at known table column locations in each separate block.
            if len(tokens)<6: continue
            qty=number_br(tokens[-2]);weight=number_br(tokens[-1])
            if qty is None or qty!=int(qty) or weight is None: continue
            result.append({'code':normalize_code(anchor['text']),'raw_code':anchor['text'],
                'description':' '.join(tokens[1:-4]),'profile':tokens[-4],'material':tokens[-3],
                'quantity':int(qty),'weight':weight,'weight_semantics':'unvalidated',
                'block':column+1,'raw_text':' '.join(tokens),
                'box_pdf':[min(w['x0'] for w in line),page.height-max(w['bottom'] for w in line),max(w['x1'] for w in line),page.height-min(w['top'] for w in line)],
                'column_boxes':[{'text':w['text'],'box_pdf':[w['x0'],page.height-w['bottom'],w['x1'],page.height-w['top']]} for w in line],
                'method':'native-column-cluster-1','reading_confidence':None,'approval':'DRAFT'})
    return result
