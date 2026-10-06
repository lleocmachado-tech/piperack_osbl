import sys,json,base64,platform,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.exporting import shell,esc,fmt,dt
from backend.db import now
E=ROOT/'reports/evidence'
inventory=json.loads((E/'inventory.json').read_text(encoding='utf-8'))
bom=json.loads((E/'bom-candidates.json').read_text(encoding='utf-8'))
classifications={
200:'Isométrica geral dos racks existentes, índice e cinco blocos de materiais; tabela de parafusos e insumos no canto inferior esquerdo.',
201:'Três plantas EL. 562,800: eixos 3-1 a 3-28. Chamadas de perfis, cotas, níveis e contraventamentos; títulos observados na imagem.',
202:'Continuação da planta EL. 562,800 (3-28 a 3-36) e plantas elevadas EL. 564,022 (trechos 3-3 a 3-29). 210-N visível no trecho inferior.',
203:'Cinco elevações longitudinais do eixo 3-A, trechos 3-1 a 3-36; níveis EL. 561,450 / 562,800 / 564,022.',
204:'Cinco elevações longitudinais do eixo 3-B, trechos 3-1 a 3-36; chamadas e diagonais não equivalem a identidade física aprovada.',
205:'Cortes B-B dos trechos 3-3 a 3-29 e cortes C-C a H-H. 210-N visível no corte do trecho 3-28/3-29.',
206:'Vistas transversais por eixos 3-1 a 3-15; 212-F é visível no eixo 3-15.',
207:'Vistas transversais por eixos 3-16 a 3-27; 212-F é visível nos eixos 3-16, 3-18 e 3-23.',
208:'Vistas transversais por eixos 3-28 a 3-36; 212-F é visível nos eixos 3-32 a 3-36.',
209:'Inspeção adicional direta: vistas frontais e cortes A-A/B-B/C-C de chumbadores; posições 209-B a 209-H, 210-A/B/C e 211-A/B; detalhes de bandejas para vigas/colunas e notas de instalação.',
210:'Inspeção adicional direta: planta EL. 554,181 (referência) e EL. 565,000 (T.V.), cortes A-A, B-B, C-C, N-N, L-L e M-M, detalhes de chumbadores e eixos 1 a 3 do rack 2.',
211:'Inspeção adicional direta: cortes D-D a K-K, elementos metálicos existentes e concreto; títulos, eixos e níveis observados na imagem, não extraídos do índice.',
212:'Inspeção adicional direta: planta superior do Pipe Rack 4 (eixos 1-1 a 1-4) e cortes A-A a L-L, apoios, contraventamentos e referências de detalhes.',
213:'Detalhes típicos dos racks 3 e 4: vistas frontais, cortes A-A a D-D e chumbadores. 224-G e 240-C estão visíveis; não gerar unidades físicas a partir desses detalhes.'}
relations=[
 {'code':'212-F','quantity_candidate':9,'drawings':['677-206M','677-207M','677-208M'],'locations_hypothesis':['3-15','3-16','3-18','3-23','3-32','3-33','3-34','3-35','3-36'],'status':'hipótese visual; identidade, lado e nível exigem revisão','physical_instances_approved':0},
 {'code':'210-N','quantity_candidate':1,'drawings':['677-202M','677-205M'],'locations_hypothesis':['trecho 3-28/3-29'],'status':'duas representações candidatas de uma unidade; vínculo não aprovado','physical_instances_approved':0},
 {'code':'224-G / 240-C','drawings':['677-213M'],'status':'detalhes típicos; somente contexto de tipo, sem nova contagem','physical_instances_approved':0},
 {'code':'208-X / 210-F / 224-H','quantity_candidate':[3,14,107],'drawings':['677-200M'],'status':'tipo não equivale a unidade; linhas não homologadas','physical_instances_approved':0}]
(E/'sample-relations.json').write_text(json.dumps(relations,ensure_ascii=False,indent=2),encoding='utf-8')
ocr_summary=None
if (E/'ocr/results.json').exists():
    corpus=json.loads((E/'ocr/corpus.json').read_text(encoding='utf-8'));runs=json.loads((E/'ocr/results.json').read_text(encoding='utf-8'))
    metrics=[]
    # Negative blank crop is explicitly excluded from quality claims.
    corpus=[s for s in corpus if not s['id'].startswith('cut-BB')]
    for psm in [7,11]:
        for split in ['calibration','evaluation']:
            samples=[s for s in corpus if s['split']==split];tp=fp=fn=0;exact=0;direct_exact=0;orientations=0
            for sample in samples:
                found=set()
                for run in runs:
                    if run['id'].split(':')[0]!=sample['id'] or run['psm']!=psm:continue
                    raw=run['text'].upper();raw=re.sub('[\u00ad‐‑‒–—−]','-',raw)
                    codes=set(re.findall(r'(?<![\dA-Z])\d{3}\s*-\s*[A-Z]+(?![A-Z])',raw));codes={re.sub(r'\s+','',c) for c in codes}
                    direct_exact+=int(codes==set(sample['expected']));orientations+=1;found.update(codes)
                expected=set(sample['expected']);tp+=len(found&expected);fp+=len(found-expected);fn+=len(expected-found);exact+=int(found==expected)
            metrics.append({'psm':psm,'split':split,'samples':len(samples),'strategy':'union of four orientation readings of the same source crop','true_positive':tp,'false_positive':fp,'false_negative':fn,'exact_crops':exact,'direct_orientation_exact':direct_exact,'direct_orientation_cases':orientations,'precision':tp/(tp+fp) if tp+fp else None,'coverage':tp/(tp+fn) if tp+fn else None})
    ocr_summary={'engine':'tesseract.js 7 / eng OEM1','configurations':metrics,'selected_psm':11,'selection':'PSM7 e PSM11 empatam nos dois recortes de calibração; PSM11 escolhido para regiões com texto esparso. Parâmetro experimental.',
                 'calibration_drawings':['677-200M'],'evaluation_drawings':['677-208M','677-213M'],
                 'exclusions':['cut-BB-205: recorte vazio observado visualmente; excluído de métricas'],
                 'limitations':'Amostra pequena, rótulos iniciais por leitura visual. Rotações são variantes do mesmo recorte, não exemplos independentes. Não há avaliação de associação/segmentação nem garantia de texto originalmente rotacionado. Associação automática permanece bloqueada.',
                 'latency_seconds_total':sum(r['seconds'] for r in runs),'rss_mb_max_observed':max(r['rss_mb'] for r in runs),'cases_executed':len(runs)}
    (E/'ocr/metrics.json').write_text(json.dumps(ocr_summary,ensure_ascii=False,indent=2),encoding='utf-8')
snapshot={'schema_version':1,'generated_at':now(),'data_updated_at':now(),'corpus_complete':len(inventory)==14 and not any(x.get('missing') for x in inventory),'measurement_cutoff':None,'inventory':inventory,'bom_preliminary':{'codes':len(bom),'units':sum(x['quantity'] for x in bom),'weight_sum_kg':sum(x['weight'] for x in bom),'drawing_structure_subtotal_kg':71492.30,'difference_kg':71492.30-sum(x['weight'] for x in bom),'approved_rows':0},'sample_relations':relations,'ocr':ocr_summary,'reference_machine':{'system':platform.platform(),'processor':platform.processor()},'missing_documents':['analise-tecnica.md'],'method':'Direct inspection of all 14 rendered sheets; native extraction with positions and objects; sample crop OCR benchmark.'}
(E/'diagnostic-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
body='<div class="notice"><b>Corpus completo disponível: 200M–213M, 14 PDFs / 14 páginas.</b><br>O documento analise-tecnica.md não foi encontrado no projeto nem na busca pelo nome na pasta de projetos. Premissas do texto anexado foram confrontadas com os PDFs reais. Nenhuma linha da BOM, unidade física ou associação foi homologada por esta inspeção. Data de corte: não aplicável ao diagnóstico.</div>'
cards=[('Desenhos inspecionados','14 / 14','209M–212M incluídos por inspeção direta'),('Códigos / unidades candidatos','403 / 859','0 linhas homologadas'),('Texto nativo ausente','11 folhas','201M–208M e 210M–212M'),('Peso','Pendente de validação','Diferença preliminar: 1.932,30 kg')]
body+='<section class="kpis">'+''.join(f'<div class="card"><label>{esc(a)}</label><strong>{esc(b)}</strong><small>{esc(c)}</small></div>' for a,b,c in cards)+'</section>'
body+='<div class="controls"><input id="filter" placeholder="Filtrar desenho" aria-label="Filtrar desenho"><button onclick="window.print()">Imprimir diagnóstico A4</button></div><h2>Inventário e leitura por arquivo</h2><div class="table-scroll"><table id="inventory"><thead><tr><th>Arquivo / método</th><th class="num">Páginas / caracteres</th><th>Caixas PDF / rotação</th><th>Objetos / imagens</th><th class="num">Inspeção / render</th><th>SHA-256</th></tr></thead><tbody>'
for item in inventory:
    if item.get('missing'):body+=f'<tr><td>{esc(item["file"])}</td><td colspan="5">Ausente</td></tr>';continue
    p=item['pages'][0]
    body+=f'<tr><td><b>{esc(item["file"])}</b><br>pypdf / pdfplumber / PDFium</td><td class="num">{len(item["pages"])} / {fmt(p["characters"],0)}</td><td>MediaBox {esc([round(x,2) for x in p["mediabox"]])}<br>CropBox {esc([round(x,2) for x in p["cropbox"]])}<br>{p["rotation"]}°</td><td>{esc(p["objects"])}<br>{p["images"]} imagens raster</td><td class="num">{fmt(item["inspection_seconds"])} s / {fmt(p["render_seconds"])} s<br>RSS observado: {fmt(item.get("process_rss_mb"),1)} MB</td><td class="hash">{esc(item["sha256"])}</td></tr>'
body+='</tbody></table></div><p class="muted">Tempos incluem extração e duas renderizações (.55 e 1,5 pixel/pt), no runtime desta máquina. RSS é a amostra no fim de cada arquivo, não pico isolado. Cache e sistema operacional afetam a latência. Evidências estruturadas acompanham o HTML.</p>'
body+='<h2>Catálogo preliminar e reconciliação</h2><div class="panel"><p>403 linhas / códigos e 859 unidades candidatos foram extraídos de cinco blocos posicionais de 200M. Texto linear intercala blocos diferentes; cada linha conserva caixa e caixas de campos. Sufixos de duas letras, como 208-AB, foram preservados.</p><p><b>Soma dos pesos extraídos: 69.560 kg. Subtotal estrutural impresso: 71.492,30 kg. Diferença: 1.932,30 kg.</b> Nenhum dos valores é denominador homologado. Subtotais impressos separados: insumos 1.072,40 kg, parafusos 591,90 kg, total 73.156,60 kg. A semântica do peso de linha precisa de aprovação; não multiplicar o peso total pela quantidade.</p><p>Questões abertas: conferir todas as linhas e todos os blocos; explicar a divergência; definir escopo de estrutura/insumos/parafusos, etapas e dependências; confirmar localização e identidade entre vistas. Fabricação, recebimento e montagem não se somam sem pesos aprovados.</p></div>'
body+='<h2>Relações amostrais: hipóteses para revisão</h2><div class="table-scroll"><table><thead><tr><th>Código</th><th>Fontes</th><th>Localização / quantidade</th><th>Estado</th></tr></thead><tbody>'
for r in relations:body+=f'<tr><td>{esc(r["code"])}</td><td>{esc(", ".join(r["drawings"]))}</td><td>{esc(r.get("locations_hypothesis",r.get("quantity_candidate","não aplicável")))}</td><td>{esc(r["status"])}</td></tr>'
body+='</tbody></table></div>'
if ocr_summary:
    body+='<h2>Benchmark inicial de OCR: leitura, não identidade</h2><div class="notice">'+esc(ocr_summary['selection'])+'<br>'+esc(ocr_summary['limitations'])+'</div><div class="table-scroll"><table><thead><tr><th>Configuração / partição</th><th>Recortes</th><th>TP / FP / FN</th><th>Recortes exatos (4 orientações)</th><th>Leitura direta por orientação</th></tr></thead><tbody>'
    for r in ocr_summary['configurations']:body+=f'<tr><td>PSM {r["psm"]} · {esc(r["split"])}</td><td>{r["samples"]}</td><td>{r["true_positive"]} / {r["false_positive"]} / {r["false_negative"]}</td><td>{r["exact_crops"]} / {r["samples"]}</td><td>{r["direct_orientation_exact"]} / {r["direct_orientation_cases"]}</td></tr>'
    body+='</tbody></table></div><p>'+str(ocr_summary['cases_executed'])+' execuções; soma de latências OCR '+fmt(ocr_summary['latency_seconds_total'])+' s; máximo RSS observado '+fmt(ocr_summary['rss_mb_max_observed'],1)+' MB. Os dois recortes de calibração pertencem à BOM; avaliação contém 212-F em 208M, 224-G em 213M e eixo 3-A. Sem estimativa validada de risco.</p><div class="drawing-grid">'
    for sample in json.loads((E/'ocr/corpus.json').read_text(encoding='utf-8')):
        if sample['id'].startswith('cut-BB'):continue
        im=(E/'ocr'/f'{sample["id"]}.png').read_bytes()
        body+=f'<figure><img src="data:image/png;base64,{base64.b64encode(im).decode()}" alt="{esc(sample["id"])}"><figcaption>{esc(sample["id"])} · {esc(sample["split"])} · rótulo inicial {esc(sample["expected"])} · fonte 677-{sample["drawing"]}M revisão 0 / página 1</figcaption></figure>'
    body+='</div>'
body+='<h2>Inspeção visual das 14 pranchas</h2><div class="drawing-grid">'
for item in inventory:
    if item.get('missing'):continue
    n=int(item['file'][4:7]);encoded=base64.b64encode((E/item['pages'][0]['thumbnail']).read_bytes()).decode()
    body+=f'<figure><img src="data:image/png;base64,{encoded}" alt="Prancha {esc(item["file"])}"><figcaption><b>{esc(item["file"])} · revisão 0 observada no carimbo · página 1</b><br>{esc(classifications[n])}</figcaption></figure>'
body+='</div><h2>Portas de qualidade e limites de entrega</h2><div class="panel"><p>Cadastro manual funciona com OCR falho. Reconhecimento é experimental e gera observações/propostas; não aprova vínculos nem inventa unidades. Não existe segmentação automática homologada, aprovação automática ou avanço por peso liberado. Geometrias, ocorrências e identidade entre vistas exigem revisão operacional.</p><p>Orçamento inicial para esta máquina: inspeção de cada PDF em até 120 s / renderização limitada a 24 milhões de pixels; a aceitação de regressões deve comparar este corpus e método. Latência de navegação e pico de memória de processamento precisam continuar sendo aferidos em produção. Os limites são técnicos iniciais, não SLA homologado.</p><p>Configuração PostgreSQL e papéis disponíveis; testes de execução PostgreSQL exigem uma instância configurada. O ambiente atual valida SQLite. A ausência de analise-tecnica.md e a reconciliação de pesos continuam abertas.</p></div>'
script='document.getElementById("filter").addEventListener("input",function(){const q=this.value.toUpperCase();document.querySelectorAll("#inventory tbody tr").forEach(r=>r.hidden=!r.textContent.toUpperCase().includes(q));});'
target=ROOT/'reports/diagnostico-combio.html';target.write_text(shell('Diagnóstico técnico · estruturas metálicas',body,'Obra 677 · PipeRack OSBL · Rhodia Paulínia',snapshot['data_updated_at'],snapshot['generated_at'],script),encoding='utf-8')
md=['# Diagnóstico técnico · Obra 677','', 'Corpus: 14 PDFs reais, 200M–213M. Revisão 0 observada nos carimbos. `analise-tecnica.md` ausente. Nenhuma aprovação automática.', '',f'Extração preliminar: {len(bom)} códigos; {sum(x["quantity"] for x in bom)} unidades; 69.560 kg. Subtotal impresso estrutural 71.492,30 kg; diferença 1.932,30 kg. Não homologado.','']
for n,description in classifications.items():md.append(f'- **677-{n}M:** {description}')
md+=['','Evidências: inventory.json, arquivos de palavras/caracteres com posições, imagens, bom-candidates.json, sample-relations.json e corpus/results/metrics de OCR. HTML offline incorpora fontes e imagens.','', 'Ver README.md e VALIDACAO.md para instalação, testes e limitações operacionais.']
(ROOT/'analise-tecnica.md').write_text('\n'.join(md),encoding='utf-8')
print(target)
