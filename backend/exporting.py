import base64,csv,html,io,json,re,zipfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor
from pypdf import PdfReader,PdfWriter,Transformation
import pypdfium2 as pdfium
from .config import ORIGINALS,TIMEZONE
from .measurement import states

CSS_PATH=Path(__file__).with_name('combio.css')
def stylesheet():
    css=CSS_PATH.read_text(encoding='utf-8').split('\n',1)[1]
    fonts=CSS_PATH.with_name('fonts.css').read_text(encoding='utf-8') if CSS_PATH.with_name('fonts.css').exists() else ''
    return fonts+'\n'+css
def tokens(): return dict(re.findall(r'--([\w-]+):\s*(#[0-9A-Fa-f]+)',stylesheet()))
def esc(value): return html.escape(str(value if value is not None else 'Desconhecido'))
def fmt(value,digits=2):
    if value is None: return 'Desconhecido'
    return f'{value:,.{digits}f}'.replace(',','X').replace('.',',').replace('X','.')
def dt(value):
    if not value: return 'Não informada'
    try:
        d=datetime.fromisoformat(value)
        if d.tzinfo: d=d.astimezone(ZoneInfo(TIMEZONE))
        return d.strftime('%d/%m/%Y %H:%M') if 'T' in value else d.strftime('%d/%m/%Y')
    except ValueError: return esc(value)
def header(title,project,updated):
    return f'<header><div><div class="brand">COMBIO</div><h1>{esc(title)}</h1><p>{esc(project)}</p></div><div class="stamp">Última atualização dos dados<br>{dt(updated)}</div></header>'
def shell(title,body,project,updated,generated,script=''):
    return f'<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>COMBIO · {esc(title)}</title><style>{stylesheet()}</style></head><body>{header(title,project,updated)}<main>{body}</main><footer>COMBIO · Avanço PipeRack OSBL · gerado em {dt(generated)} · Entrega offline: fontes e imagens incorporadas; sem servidor ou CDN.</footer><script>{script}</script></body></html>'

def geometry_visuals(snapshot,page_id):
    state=snapshot['data']['state'];stage_id=snapshot['stage_id'];balance=states(state['progress_events'],snapshot['cutoff'])
    geometry={g['id']:g for g in state['geometries']};views={v['id']:v for v in state['views']};stage=next(s for s in state['stages'] if s['id']==stage_id)
    result=[]
    for o in state['occurrences']:
        if views[o['view_id']]['page_id']!=page_id: continue
        g=geometry[o['geometry_id']]
        if g['data'].get('deleted'): continue
        status='pending';token='atencao';fill=False
        if o['association']=='APROVADA':
            if o['instance_id'] and balance.get((o['type_id'],stage_id,o['instance_id']),0)>=1:
                status='completed';token=stage['token'];fill=True
            elif not o['instance_id'] and balance.get((o['type_id'],stage_id,None),0)>0 and o['role']=='installation':
                status='aggregate';token='info'
            else: status='unmeasured';token='texto-sec'
        result.append({'geometry':g['data'],'token':token,'fill':fill,'status':status,'label':o['association']})
    for override in state['overlays']:
        if override['page_id']!=page_id or not override['data'].get('active',True): continue
        if override['data'].get('valid_until') and override['data']['valid_until']<snapshot['cutoff']:continue
        g=geometry[override['geometry_id']]
        if g['data'].get('deleted'):continue
        result.append({'geometry':g['data'],'token':override['data'].get('token','info'),'fill':False,'status':'override','label':'ANOTAÇÃO / OVERRIDE'})
    return result

def technical_pdf(snapshot,drawing):
    reader=PdfReader(ORIGINALS/(drawing['sha256']+'.pdf'));writer=PdfWriter();state=snapshot['data']['state'];palette=tokens()
    for index,page in enumerate(reader.pages,1):
        record=next(p for p in state['pages'] if p['drawing_id']==drawing['id'] and p['number']==index)
        stream=io.BytesIO();w=float(page.mediabox.width);h=float(page.mediabox.height)
        canvas=Canvas(stream,pagesize=(w,h));canvas.translate(-float(page.mediabox.left),-float(page.mediabox.bottom))
        for item in geometry_visuals(snapshot,record['id']):
            g=item['geometry'];color=HexColor(palette[item['token']]);canvas.saveState()
            canvas.setStrokeColor(color);canvas.setFillColor(color)
            canvas.setLineWidth(g.get('width',2));canvas.setStrokeAlpha(.85);canvas.setFillAlpha(.27)
            if item['status'] in {'pending','aggregate','override'}:canvas.setDash(6,4)
            for points in g['paths']:
                path=canvas.beginPath();path.moveTo(*points[0])
                for point in points[1:]:path.lineTo(*point)
                closed=g['kind'] in {'polygon','multipolygon'}
                if closed:path.close()
                canvas.drawPath(path,stroke=1,fill=int(item['fill'] and closed))
            canvas.restoreState()
        canvas.save();overlay=PdfReader(io.BytesIO(stream.getvalue())).pages[0]
        writer.add_page(page)
        writer.pages[-1].merge_transformed_page(overlay,Transformation().translate(float(page.mediabox.left),float(page.mediabox.bottom)),expand=False)
    legend=io.BytesIO();c=Canvas(legend,pagesize=(595.28,841.89));c.setFillColor(HexColor(palette['combio']));c.rect(0,760,595.28,82,fill=1,stroke=0);c.setFillColor(HexColor(palette['superficie']));c.setFont('Helvetica-Bold',18);c.drawString(32,798,'COMBIO | Avanço PipeRack OSBL')
    c.setFillColor(HexColor(palette['texto']));c.setFont('Helvetica',11)
    stage=next(s for s in state['stages'] if s['id']==snapshot['stage_id'])
    lines=[state['project']['name'],f"Desenho: {drawing['technical_number']} | Revisão: {drawing['revision']}",f"Etapa: {stage['name']} | Corte: {dt(snapshot['cutoff'])}",f"Snapshot: {snapshot['id']}",f"Dados: {dt(state['project']['created_at'])} | Geração: {dt(snapshot['created_at'])}",
        'Escopo: '+', '.join(snapshot['data']['summary']['scope_categories']),
        'Preenchimento: conclusão de unidade localizada e vínculo aprovado.',
        'Tracejado: pendência, saldo agregado sem localização ou anotação/override.',
        'Saldo agregado não escolhe nem confirma posições físicas.',
        'Detalhes típicos não confirmam instalação individual.',
        'Anotações livres e overrides não constituem medição.',
        'Pranchas originais preservadas; esta legenda é uma página adicional A4.',
        'Peso: pendente de validação e reconciliação.',
        f"Previsto validado: {snapshot['data']['summary']['denominator']} unidades.",
        f"Concluído nesta etapa: {fmt(snapshot['data']['summary']['completed'])} unidades."]
    for row,line in enumerate(lines): c.drawString(32,730-row*26,line[:110])
    c.save();writer.add_page(PdfReader(io.BytesIO(legend.getvalue())).pages[0]);writer.add_metadata({'/Title':f"COMBIO {drawing['technical_number']} {snapshot['id']}",'/Subject':f"Snapshot {snapshot['id']} | {snapshot['cutoff']}"})
    out=io.BytesIO();writer.write(out);return out.getvalue()

def progress_html(snapshot,pdfs):
    state=snapshot['data']['state'];stats=snapshot['data']['summary'];stage=next(s for s in state['stages'] if s['id']==snapshot['stage_id'])
    updated=max([state['project']['created_at']]+[e['created_at'] for e in state['audit']])
    body=f'<div class="notice"><b>Etapa: {esc(stage["name"])} · Data de corte: {dt(snapshot["cutoff"])}</b><br>Snapshot {esc(snapshot["id"])} · Versão {state["project"]["version"]} · Escopo: {esc(", ".join(stats["scope_categories"]))}. {stats["unvalidated_types"]} códigos fora do denominador por falta de validação. Última atualização e geração são datas distintas do corte.</div>'
    amount=f'{fmt(stats["denominator"],0)} / {fmt(stats["completed"],0)}' if stats['denominator'] or not stats['unvalidated_types'] else 'Não homologado'
    cards=[('Avanço da etapa',fmt(stats['percent'])+'%' if stats['percent'] is not None else 'Desconhecido','Conclusão / denominador validado'),('Unidades previstas / concluídas',amount,'Somente escopo validado'),('Mapeamento aprovado',fmt(stats['mapping_percent'])+'%' if stats['mapping_percent'] is not None else 'Desconhecido',f'{stats["mapped"]} unidades localizadas, sem duplicar vistas'),('Pendências',str(stats['pending']),'Peso: Pendente de validação')]
    body+='<section class="kpis">'+''.join(f'<div class="card"><label>{esc(label)}</label><strong>{esc(value)}</strong><small>{esc(note)}</small></div>' for label,value,note in cards)+'</section>'
    body+='<h2>Avanço por código</h2><div class="controls"><input id="search" aria-label="Buscar código" placeholder="Buscar código ou descrição"><button onclick="window.print()">Imprimir A4</button></div><div class="table-scroll"><table id="catalog"><thead><tr><th>Código</th><th>Descrição</th><th class="num">Previsto</th><th class="num">Concluído</th><th class="num">Avanço</th><th>Localização / saldo</th><th>Catálogo / associação</th></tr></thead><tbody>'
    for piece in sorted(stats['rows'],key=lambda p:p['code']):
        units=[i for i in state['instances'] if i['type_id']==piece['id']]
        locations='; '.join(i['data'].get('location','Provisória sem localização') for i in units)
        if piece['aggregate']>0: locations+=f' | Saldo agregado: {fmt(piece["aggregate"],0)} sem localização'
        body+=f'<tr><td><b>{esc(piece["code"])}</b></td><td>{esc(piece["data"].get("description",""))}</td><td class="num">{fmt(piece["quantity"],0)}</td><td class="num">{fmt(piece["completed"],0)}</td><td class="num">{fmt(piece["percent"])}{ "%" if piece["percent"] is not None else ""}</td><td>{esc(locations or "Sem localização")}</td><td>{"Validado" if piece["validated"] else "Pendente de validação"}<br>{piece["mapped"]} unidades com mapeamento aprovado</td></tr>'
    body+='</tbody></table></div><h2>Pendências e overrides</h2><div class="panel"><p>Valores preliminares da BOM não são homologados. Códigos sem aprovação não integram o denominador. Pesos exigem validação da semântica e reconciliação documental.</p>'
    for override in state['overlays']:body+=f'<p>ANOTAÇÃO / OVERRIDE · {esc(override["scope"])} · {esc(override["reason"])} · autor {esc(override["author"])} · {"ativo" if override["data"].get("active",True) else "inativo"} · validade {esc(override["data"].get("valid_until","sem prazo"))}</p>'
    for proposal in state['proposals']:body+=f'<p>{esc(proposal["state"])} · {esc(proposal["data"].get("blocking",[]))}</p>'
    body+='</div><h2>Desenhos e sobreposições</h2><div class="legend"><span>Preenchido: unidade concluída e aprovada</span><span>Tracejado: pendência / agregado sem localização / override</span><span>Detalhe típico: contexto de tipo, sem contagem individual</span></div><div class="drawing-grid">'
    for drawing_id,content in pdfs.items():
        drawing=next(d for d in state['drawings'] if d['id']==drawing_id)
        with pdfium.PdfDocument(content) as doc:
            for index in range(len(doc)-1):
                bitmap=doc[index].render(scale=.4);image=bitmap.to_pil();buf=io.BytesIO();image.save(buf,format='PNG');bitmap.close()
                encoded=base64.b64encode(buf.getvalue()).decode()
                views=[v for v in state['views'] if v['page_id']==next(p['id'] for p in state['pages'] if p['drawing_id']==drawing_id and p['number']==index+1)]
                context='; '.join(f"{v['name']} / eixos {v['data'].get('axes','não informados')} / nível {v['data'].get('level','não informado')}" for v in views)
                body+=f'<figure><img alt="{esc(drawing["technical_number"])} com sobreposições" src="data:image/png;base64,{encoded}"><figcaption>{esc(drawing["technical_number"])} · Rev. {esc(drawing["revision"])} · página {index+1} · {esc(context)} · {"Revisão histórica" if drawing["data"].get("superseded") else "Revisão atual"}</figcaption></figure>'
    body+='</div>'
    safe_json=json.dumps({'snapshot_id':snapshot['id'],'stage':stage,'summary':stats},ensure_ascii=False).replace('<','\\u003c')
    script='document.getElementById("search").addEventListener("input",function(){const q=this.value.toUpperCase();document.querySelectorAll("#catalog tbody tr").forEach(r=>r.hidden=!r.textContent.toUpperCase().includes(q));});const SNAPSHOT='+safe_json+';'
    return shell('Acompanhamento de avanço físico',body,state['project']['name'],updated,snapshot['created_at'],script)

def csv_bytes(records,fields,snapshot_id):
    out=io.StringIO(newline='');writer=csv.writer(out,delimiter=';');writer.writerow(['snapshot_id']+fields)
    for record in records:
        values=[]
        for field in fields:
            v=record.get(field)
            if isinstance(v,(dict,list)):v=json.dumps(v,ensure_ascii=False)
            if isinstance(v,float):v=str(v).replace('.',',')
            if isinstance(v,str) and v[:1] in '=+-@':v="'"+v
            values.append('' if v is None else v)
        writer.writerow([snapshot_id]+values)
    return ('\ufeff'+out.getvalue()).encode('utf-8')

def export_bundle(snapshot):
    state=snapshot['data']['state'];pdfs={}
    processed={p['drawing_id'] for p in state['pages']}
    for drawing in state['drawings']:
        if drawing['id'] in processed:pdfs[drawing['id']]=technical_pdf(snapshot,drawing)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('relatorio-avanco.html',progress_html(snapshot,pdfs))
        archive.writestr('snapshot.json',json.dumps(snapshot,ensure_ascii=False,indent=2))
        archive.writestr('catalogo.csv',csv_bytes(snapshot['data']['summary']['rows'],['code','quantity','completed','aggregate','percent','validation','data'],snapshot['id']))
        archive.writestr('unidades.csv',csv_bytes(state['instances'],['id','type_id','state','data'],snapshot['id']))
        archive.writestr('avanco.csv',csv_bytes([e for e in state['progress_events'] if e['effective_at'][:10]<=snapshot['cutoff']],['id','type_id','instance_id','stage_id','delta','effective_at','author','reason','reverted_event_id'],snapshot['id']))
        archive.writestr('pendencias.csv',csv_bytes([p for p in state['piece_types'] if p['validation']!='APPROVED']+[o for o in state['occurrences'] if o['association']!='APROVADA'],['id','code','validation','association','data'],snapshot['id']))
        for id,content in pdfs.items():
            drawing=next(d for d in state['drawings'] if d['id']==id)
            safe=re.sub(r'[^\w.-]','_',drawing['technical_number'])
            archive.writestr(f'tecnicos/{safe}-{id[:8]}.pdf',content)
        for d in state['drawings']:
            archive.write(ORIGINALS/(d['sha256']+'.pdf'),f'originais/{d["sha256"]}.pdf')
        archive.writestr('LEIA-ME.txt','Todos os resultados derivam do snapshot '+snapshot['id']+'. Originais por hash incluídos para recuperação. snapshot.json contém histórico integral; CSV de avanço observa a data de corte. HTML abre offline sem backend; fontes Kodchasan e Open Sans incorporadas sob OFL. PDFs técnicos mantêm o tamanho das pranchas e adicionam legenda A4. Não existe aprovação automática.')
    return out.getvalue()
