import {useEffect,useRef,useState} from 'react';
import type {PointerEvent as RPointerEvent} from 'react';
import * as pdfjs from 'pdfjs-dist';
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker&inline';
import {backend,FileRow,Legend,Mark} from './store';
import {extractPieces,inPoly,keyOf,pieceAt,piecesIn,Piece,Pt} from './pieces';
import {exportPdf} from './export';
pdfjs.GlobalWorkerOptions.workerPort=new PdfWorker(); // worker embutido: funciona também em file://

type Tool='move'|'paint'|'box'|'erase';
const TOOLS:[Tool,string,string][]=[
 ['move','✋ Mover','Rola e arrasta a página sem pintar.'],
 ['paint','🖌 Pintar peça','Clique ou arraste sobre as peças. Só a peça sob o cursor é pintada, nunca o fundo.'],
 ['box','▭ Selecionar área','Arraste uma caixa. Da esquerda para a direita pinta só as peças inteiras dentro dela; da direita para a esquerda pinta também as que ela toca.'],
 ['erase','⌫ Apagar','Clique ou arraste sobre o que quer limpar.'],
];
type Gesture={added:Mark[];removed:Mark[]};
type Rect={x0:number;y0:number;x1:number;y1:number};

export default function Editor({fileId,onBack}:{fileId:string;onBack:(folderId:string|null)=>void}){
 const [file,setFile]=useState<FileRow|null>(null),[doc,setDoc]=useState<any>(null),bytes=useRef<Uint8Array|undefined>(undefined);
 const [pageNum,setPage]=useState(1),[zoom,setZoom]=useState(0),[vp,setVp]=useState<any>(null);
 const [list,setList]=useState<Mark[]>([]);
 const [pieces,setPieces]=useState<Piece[]|null>(null);
 const [tool,setTool]=useState<Tool>('paint'),[color,setColor]=useState('#2e7d32');
 const [legend,setLegend]=useState<Legend>([]),[legendOpen,setLegendOpen]=useState(false);
 const [hover,setHover]=useState<Piece|null>(null),[rect,setRect]=useState<Rect|null>(null);
 const [msg,setMsg]=useState(''),[busy,setBusy]=useState(false);
 const canvas=useRef<HTMLCanvasElement>(null),scroll=useRef<HTMLDivElement>(null);
 const [boxWidth,setBoxWidth]=useState(900);
 const listRef=useRef<Mark[]>([]),hist=useRef<Gesture[]>([]),gesture=useRef<Gesture|null>(null);
 const legendRef=useRef<Legend>([]),dirty=useRef(false),timer=useRef<number|undefined>(undefined),queue=useRef<Promise<unknown>>(Promise.resolve());
 const fail=(e:any)=>setMsg(e?.message||String(e));
 const update=(fn:(l:Mark[])=>Mark[])=>{listRef.current=fn(listRef.current);setList(listRef.current)};

 useEffect(()=>{ // abre o arquivo: PDF, marcas e legenda; depois acompanha as mudanças dos outros
  let stop=false,unwatch=()=>{};
  (async()=>{
   const f=await backend.file(fileId);
   const [pdf,marks]=await Promise.all([backend.pdf(fileId),backend.marks(fileId)]);
   const d=await pdfjs.getDocument({data:pdf.slice(0)}).promise; // cópia: o PDF.js consome o buffer
   if(stop)return;
   bytes.current=pdf;legendRef.current=f.legend;setLegend(f.legend);update(()=>marks);setFile(f);setDoc(d);
   unwatch=backend.watch(fileId,{
    onAdd:m=>update(l=>l.some(x=>x.id===m.id)?l:[...l,m]),
    onDel:id=>update(l=>l.filter(x=>x.id!==id)),
    onLegend:l=>{if(!dirty.current&&JSON.stringify(l)!==JSON.stringify(legendRef.current)){legendRef.current=l;setLegend(l)}},
   });
  })().catch(e=>{if(!stop)fail(e)});
  return()=>{stop=true;unwatch();clearTimeout(timer.current);flushLegend()};
 },[fileId]);
 useEffect(()=>{
  const el=scroll.current;if(!el)return;
  const ro=new ResizeObserver(([e])=>setBoxWidth(Math.round(e.contentRect.width)));ro.observe(el);return()=>ro.disconnect();
 },[]);
 useEffect(()=>{
  const key=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key==='z'&&!(e.target instanceof HTMLInputElement)){e.preventDefault();undo()}};
  window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
 });

 useEffect(()=>{ // peças da página: leitura da camada "Peça" do PDF
  if(!doc)return;let stop=false;setPieces(null);setHover(null);
  (async()=>{
   const [p,oc]=await Promise.all([doc.getPage(pageNum),doc.getOptionalContentConfig()]);
   const found=await extractPieces(p,oc as any,pdfjs.OPS);
   if(stop)return;
   setPieces(found);
   if(!found.length)setMsg('Este desenho não tem a camada "Peça", então não há o que pintar.');
  })().catch(e=>{if(!stop)fail(e)});
  return()=>{stop=true};
 },[doc,pageNum]);

 useEffect(()=>{
  if(!doc)return;let stop=false,task:any;
  (async()=>{
   const p=await doc.getPage(pageNum);if(stop)return;
   const s=zoom||Math.max(.1,(boxWidth-24)/p.getViewport({scale:1}).width);
   const v=p.getViewport({scale:s}),dpr=Math.min(window.devicePixelRatio||1,2),cv=canvas.current!;
   cv.width=Math.round(v.width*dpr);cv.height=Math.round(v.height*dpr);cv.style.width=v.width+'px';cv.style.height=v.height+'px';
   setVp(v);
   task=p.render({canvas:cv,canvasContext:cv.getContext('2d')!,viewport:v,transform:dpr===1?undefined:[dpr,0,0,dpr,0,0]});
   await task.promise;
  })().catch(e=>{if(e?.name!=='RenderingCancelledException')fail(e)});
  return()=>{stop=true;task?.cancel()};
 },[doc,pageNum,zoom,boxWidth]);

 // Salva sozinho: cada gesto vai para o servidor em ordem (fila), então "Desfazer" nunca passa na frente do salvar.
 function sync(removeIds:string[],add:Mark[]){
  queue.current=queue.current
   .then(()=>backend.removeMarks(removeIds)).then(()=>backend.addMarks(add))
   .catch(e=>{fail(e);return backend.marks(fileId).then(l=>update(()=>l))});
 }
 function commit(g:Gesture){
  if(!g.added.length&&!g.removed.length)return;
  hist.current.push(g);sync(g.removed.map(s=>s.id),g.added);
 }
 function undo(){
  const g=hist.current.pop();if(!g)return;
  const gone=new Set(g.added.map(s=>s.id));
  update(l=>[...l.filter(s=>!gone.has(s.id)),...g.removed]);sync([...gone],g.removed);
 }
 function flushLegend(){
  if(!dirty.current)return;dirty.current=false;
  backend.saveLegend(fileId,legendRef.current).catch(fail);
 }
 const setLegendSaved=(l:Legend)=>{legendRef.current=l;setLegend(l);dirty.current=true;clearTimeout(timer.current);timer.current=window.setTimeout(flushLegend,600)};

 function paintPieces(ps:Piece[],g:Gesture){
  const have=new Map(listRef.current.filter(s=>s.page===pageNum).map(s=>[keyOf(s.points),s]));
  const add:Mark[]=[],drop:Mark[]=[];
  for(const p of ps){
   const points=p.poly.map(([x,y])=>[+x.toFixed(2),+y.toFixed(2)] as Pt),k=keyOf(points),old=have.get(k);
   if(old?.color===color)continue;
   if(old)drop.push(old);
   const m:Mark={id:crypto.randomUUID(),file_id:fileId,page:pageNum,color,points};
   have.set(k,m);add.push(m);
  }
  if(!add.length&&!drop.length)return;
  const gone=new Set(drop.map(s=>s.id));
  update(l=>[...l.filter(s=>!gone.has(s.id)),...add]);
  g.added.push(...add);g.removed.push(...drop);
 }
 function eraseAt(p:Pt,g:Gesture){
  const hit=listRef.current.filter(s=>s.page===pageNum&&inPoly(s.points,p));
  if(!hit.length)return;
  const gone=new Set(hit.map(s=>s.id));
  update(l=>l.filter(s=>!gone.has(s.id)));g.removed.push(...hit);
 }
 const touch=(p:Pt,g:Gesture)=>{
  if(tool==='erase')eraseAt(p,g);
  else{const q=pieceAt(pieces!,p);if(q)paintPieces([q],g)}
 };

 const at=(e:RPointerEvent):Pt=>{const r=e.currentTarget.getBoundingClientRect();return vp.convertToPdfPoint(e.clientX-r.left,e.clientY-r.top) as Pt};
 const rel=(e:RPointerEvent)=>{const r=e.currentTarget.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top]};
 const down=(e:RPointerEvent)=>{
  if(!vp||!pieces)return;e.currentTarget.setPointerCapture(e.pointerId);
  if(tool==='box'){const [x,y]=rel(e);setRect({x0:x,y0:y,x1:x,y1:y});return}
  gesture.current={added:[],removed:[]};touch(at(e),gesture.current);
 };
 const move=(e:RPointerEvent)=>{
  if(!vp||!pieces)return;
  if(rect){const [x,y]=rel(e);setRect({...rect,x1:x,y1:y});return}
  if(gesture.current)touch(at(e),gesture.current);
  else if(tool==='paint')setHover(pieceAt(pieces,at(e))||null);
 };
 const up=()=>{
  if(gesture.current){commit(gesture.current);gesture.current=null}
  if(rect&&vp&&pieces){
   const g:Gesture={added:[],removed:[]},tiny=Math.hypot(rect.x1-rect.x0,rect.y1-rect.y0)<4;
   const a=vp.convertToPdfPoint(rect.x0,rect.y0) as Pt,b=vp.convertToPdfPoint(rect.x1,rect.y1) as Pt;
   if(tiny){const q=pieceAt(pieces,a);if(q)paintPieces([q],g)}
   else paintPieces(piecesIn(pieces,[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])],rect.x1>=rect.x0),g);
   commit(g);setRect(null);
  }
 };

 async function save(){
  setBusy(true);
  try{
   const out=await exportPdf(bytes.current!,list,legend,file!.name),a=document.createElement('a');
   a.href=URL.createObjectURL(new Blob([out as BlobPart],{type:'application/pdf'}));
   a.download=file!.name.replace(/[\\/:*?"<>|]+/g,'_')+'-avanco.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),10000);
  }catch(e){fail(e)}finally{setBusy(false)}
 }
 const copyLink=()=>navigator.clipboard.writeText(location.href).then(()=>setMsg('Link copiado. Quem tiver a senha da equipe abre este arquivo.'),()=>setMsg('Copie o endereço da barra do navegador.'));
 const zoomBy=(f:number)=>setZoom(Math.max(.1,Math.min(6,(vp?.scale||1)*f)));
 const path=(pts:Pt[])=>pts.map((p,i)=>{const q=vp.convertToViewportPoint(p[0],p[1]);return `${i?'L':'M'}${q[0]},${q[1]}`}).join(' ')+'Z';

 const info=TOOLS.find(t=>t[0]===tool)![2];
 const entry=legend.find(l=>l.color===color);
 return <div className="app">
  <div className="bar">
   <button onClick={()=>onBack(file?.folder_id??null)}>← Arquivos</button>
   <b className="title">{file?.name||'Abrindo…'}</b>
   {doc&&<>
    <span className="group"><button disabled={pageNum<=1} onClick={()=>setPage(pageNum-1)}>◀</button><span>pág. {pageNum}/{doc.numPages}</span><button disabled={pageNum>=doc.numPages} onClick={()=>setPage(pageNum+1)}>▶</button></span>
    <span className="group">{TOOLS.map(([id,label])=><button key={id} aria-pressed={tool===id} className={tool===id?'on':''} onClick={()=>{setTool(id);setHover(null)}}>{label}</button>)}</span>
    <span className="group"><label className="picker" title="Escolher a cor de pintura">Cor <input type="color" value={color} onChange={e=>setColor(e.target.value)}/></label>
     <small>{entry?.label||'sem legenda'}</small>
     <button aria-expanded={legendOpen} onClick={()=>setLegendOpen(!legendOpen)}>Legenda{legend.length?` (${legend.length})`:''} {legendOpen?'▴':'▾'}</button></span>
    <span className="group"><button onClick={()=>zoomBy(.8)}>−</button><button onClick={()=>setZoom(0)}>Ajustar</button><button onClick={()=>zoomBy(1.25)}>+</button></span>
    <button disabled={!hist.current.length} onClick={undo}>↶ Desfazer</button>
    <button onClick={copyLink}>🔗 Copiar link</button>
    <button className="primary" disabled={busy} onClick={save}>Baixar PDF colorido</button>
    <small className="hint">{pieces?`${pieces.length} peças detectadas. `:'Lendo as peças do desenho… '}{info}</small>
   </>}
  </div>
  {doc&&legendOpen&&<div className="legend">
   <b>Legenda</b>
   {legend.map((l,i)=><div className="entry" key={i}>
    <button aria-label="Usar esta cor" title="Usar esta cor" aria-pressed={color===l.color} className={'sw'+(color===l.color?' on':'')} style={{background:l.color}} onClick={()=>setColor(l.color)}/>
    <input value={l.label} placeholder="O que esta cor significa? (ex.: Montado)" onChange={e=>setLegendSaved(legend.map((x,j)=>j===i?{...x,label:e.target.value}:x))}/>
    <button aria-label="Remover da legenda" title="Remover da legenda" onClick={()=>setLegendSaved(legend.filter((_,j)=>j!==i))}>×</button>
   </div>)}
   <button disabled={!!entry} onClick={()=>setLegendSaved([...legend,{color,label:''}])}>{entry?'A cor atual já está na legenda':'+ Adicionar a cor atual'}</button>
   <small>A legenda é deste arquivo e sai numa página extra no fim do PDF baixado (só as cores com nome).</small>
  </div>}
  {msg&&<div className="msg" role="alert">{msg}<button onClick={()=>setMsg('')}>×</button></div>}
  <div className="scroll" ref={scroll}>
   {!doc&&!msg&&<p className="center">Abrindo o arquivo…</p>}
   <div className="sheet" style={{display:doc?'block':'none'}}>
    <canvas ref={canvas}/>
    {doc&&vp&&<svg width={vp.width} height={vp.height} style={{pointerEvents:tool==='move'?'none':'auto',touchAction:tool==='move'?'auto':'none',cursor:tool==='move'?'default':!pieces?'wait':tool==='erase'?'pointer':'crosshair'}} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={()=>{gesture.current=null;setRect(null)}}>
     <g pointerEvents="none">{list.filter(s=>s.page===pageNum).map(s=><path key={s.id} d={path(s.points)} fill={s.color} fillOpacity=".4" stroke={s.color} strokeOpacity=".8"/>)}</g>
     {hover&&tool==='paint'&&<path d={path(hover.poly)} fill={color} fillOpacity=".2" stroke={color} strokeWidth="2" strokeDasharray="4 3" pointerEvents="none"/>}
     {rect&&<rect x={Math.min(rect.x0,rect.x1)} y={Math.min(rect.y0,rect.y1)} width={Math.abs(rect.x1-rect.x0)} height={Math.abs(rect.y1-rect.y0)} fill={rect.x1>=rect.x0?'#1E88E5':'#2E7D32'} fillOpacity=".12" stroke={rect.x1>=rect.x0?'#1E88E5':'#2E7D32'} strokeWidth="1.5" strokeDasharray={rect.x1>=rect.x0?undefined:'6 4'} pointerEvents="none"/>}
    </svg>}
   </div>
  </div>
 </div>;
}
