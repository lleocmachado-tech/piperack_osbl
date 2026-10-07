import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {PointerEvent as RPointerEvent} from 'react';
import * as pdfjs from 'pdfjs-dist';
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker&inline';
import {backend,FileRow,Legend,Mark} from './store';
import {extractPieces,inPoly,keyOf,pieceAt,piecesIn,Piece,Pt} from './pieces';
import {exportPdf} from './export';
import logo from './assets/combio-branco.png';
pdfjs.GlobalWorkerOptions.workerPort=new PdfWorker(); // worker embutido: funciona também em file://

type Tool='move'|'paint'|'box'|'erase';
const TOOLS:[Tool,string,string,string][]=[
 ['move','✋','Mover','Arraste a página para movê-la, sem pintar.'],
 ['paint','🖌','Pintar','Clique ou arraste sobre as peças. Só a peça sob o cursor é pintada, nunca o fundo.'],
 ['box','▭','Área','Arraste uma caixa. Da esquerda para a direita pinta só as peças inteiras dentro dela; da direita para a esquerda pinta também as que ela toca.'],
 ['erase','⌫','Apagar','Clique ou arraste sobre o que quer limpar.'],
];
const MAX_ZOOM=4; // acima disso o canvas passa de 60 milhões de pixels
const COARSE=typeof matchMedia==='function'&&matchMedia('(pointer:coarse)').matches; // celular/tablet: dedo no lugar do mouse
const MAX_PIXELS=COARSE?1.2e7:4e7; // o canvas é desenhado fora da tela antes de trocar, então a memória dobra: no celular o teto é menor
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
 // Zoom com Ctrl + roda (ancorado no cursor) e mover a página com o mouse (botão do meio ou Espaço + arrastar).
 const sheet=useRef<HTMLDivElement>(null),vpRef=useRef<any>(null),scaleRef=useRef(0),anchor=useRef<{pdf:Pt;x:number;y:number}|null>(null);
 const spaceRef=useRef(false),[grab,setGrab]=useState(false),pan=useRef<{x:number;y:number;l:number;t:number;px:number;py:number;pt:number;vx:number;vy:number}|null>(null);
 // Toque: dedos na tela (dois dedos = pinça para zoom + mover) e a pinça em andamento.
 const ptrs=useRef(new Map<number,{x:number;y:number}>()),pinch=useRef<{d:number;mx:number;my:number;cx:number;cy:number;scale:number;ratio:number;pdf:Pt}|null>(null),fling=useRef(0);
 const [tip,setTip]=useState(COARSE),[online,setOnline]=useState(navigator.onLine),pending=useRef(0);
 vpRef.current=vp;
 const applyZoom=(z:number)=>{scaleRef.current=z;setZoom(z)};

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
 useEffect(()=>{ // sem internet as marcas ficam na fila e saem quando voltar; ao voltar, confere o que os outros fizeram
  const on=()=>{setOnline(true);queue.current=queue.current.then(()=>backend.marks(fileId)).then(l=>{if(!pending.current)update(()=>l)}).catch(()=>{})};
  const off=()=>setOnline(false),leave=(e:BeforeUnloadEvent)=>{if(pending.current)e.preventDefault()};
  addEventListener('online',on);addEventListener('offline',off);addEventListener('beforeunload',leave);
  return()=>{removeEventListener('online',on);removeEventListener('offline',off);removeEventListener('beforeunload',leave)};
 },[fileId]);
 useEffect(()=>{if(!tip)return;const t=setTimeout(()=>setTip(false),7000);return()=>clearTimeout(t)},[tip]);
 useEffect(()=>{ // Espaço segurado = modo mover em qualquer ferramenta
  const typing=(e:KeyboardEvent)=>['INPUT','TEXTAREA','SELECT','BUTTON'].includes((e.target as HTMLElement).tagName);
  const down=(e:KeyboardEvent)=>{if(e.code!=='Space'||typing(e))return;e.preventDefault();spaceRef.current=true;setGrab(true)};
  const up=(e:KeyboardEvent)=>{if(e.code!=='Space')return;spaceRef.current=false;setGrab(false)};
  window.addEventListener('keydown',down);window.addEventListener('keyup',up);
  return()=>{window.removeEventListener('keydown',down);window.removeEventListener('keyup',up)};
 },[]);
 useEffect(()=>{ // Ctrl + roda: zoom no ponto sob o cursor (listener não passivo para segurar o zoom do navegador)
  const el=scroll.current;if(!el)return;
  const wheel=(e:WheelEvent)=>{
   if(!(e.ctrlKey||e.metaKey))return;
   e.preventDefault();
   const v=vpRef.current,s=sheet.current;if(!v||!s)return;
   const r=s.getBoundingClientRect(),dy=e.deltaMode===1?e.deltaY*33:e.deltaY;
   anchor.current={pdf:v.convertToPdfPoint(e.clientX-r.left,e.clientY-r.top) as Pt,x:e.clientX,y:e.clientY};
   applyZoom(Math.max(.1,Math.min(MAX_ZOOM,(scaleRef.current||v.scale)*Math.exp(-dy*.002))));
  };
  el.addEventListener('wheel',wheel,{passive:false});return()=>el.removeEventListener('wheel',wheel);
 },[]);
 useLayoutEffect(()=>{ // depois de redesenhar, rola para o ponto do PDF continuar sob o cursor
  const a=anchor.current,s=sheet.current,el=scroll.current;if(!vp||!s||!el)return;
  if(!pinch.current)s.style.transform=''; // a prévia da pinça sai junto com a troca da imagem, sem piscar
  if(!a)return;
  anchor.current=null;
  const q=vp.convertToViewportPoint(a.pdf[0],a.pdf[1]),r=s.getBoundingClientRect();
  el.scrollLeft+=r.left+q[0]-a.x;el.scrollTop+=r.top+q[1]-a.y;
 },[vp]);

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
   const v=p.getViewport({scale:s}),dpr=Math.min(window.devicePixelRatio||1,2,Math.sqrt(MAX_PIXELS/(v.width*v.height))),cv=canvas.current!,off=document.createElement('canvas');
   off.width=Math.round(v.width*dpr);off.height=Math.round(v.height*dpr);
   task=p.render({canvas:off,canvasContext:off.getContext('2d')!,viewport:v,transform:dpr===1?undefined:[dpr,0,0,dpr,0,0]});
   await task.promise;if(stop)return;
   // troca de uma vez só (imagem + camada de pintura), então o zoom não pisca em branco
   cv.width=off.width;cv.height=off.height;cv.style.width=v.width+'px';cv.style.height=v.height+'px';cv.getContext('2d')!.drawImage(off,0,0);setVp(v);
  })().catch(e=>{if(e?.name!=='RenderingCancelledException')fail(e)});
  return()=>{stop=true;task?.cancel()};
 },[doc,pageNum,zoom,boxWidth]);

 // Sinal fraco no campo: tenta de novo (e espera a internet voltar) antes de desistir e recarregar as marcas do servidor.
 async function retry(job:()=>Promise<unknown>){
  for(let i=0;;i++){
   try{return await job()}catch(e){
    if(!navigator.onLine)await new Promise(r=>addEventListener('online',r,{once:true}));
    else if(i>=4)throw e;else await new Promise(r=>setTimeout(r,1500*2**i));
   }
  }
 }
 // Salva sozinho: cada gesto vai para o servidor em ordem (fila), então "Desfazer" nunca passa na frente do salvar.
 function sync(removeIds:string[],add:Mark[]){
  pending.current++;
  queue.current=queue.current
   .then(()=>retry(async()=>{await backend.removeMarks(removeIds);await backend.addMarks(add)}))
   .catch(e=>{fail(e);return backend.marks(fileId).then(l=>update(()=>l))})
   .finally(()=>{pending.current--});
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
 function abortGesture(){ // dois dedos na tela: o primeiro dedo era o começo da pinça, não uma pintura
  const g=gesture.current;gesture.current=null;setRect(null);
  if(!g)return;
  const gone=new Set(g.added.map(s=>s.id));
  update(l=>[...l.filter(s=>!gone.has(s.id)),...g.removed]);
 }
 const down=(e:RPointerEvent)=>{
  if(!vp||!pieces||e.button!==0||spaceRef.current)return; // botão do meio e Espaço são para mover a página
  if(e.pointerType==='touch'&&ptrs.current.size)return; // segundo dedo: é pinça
  try{e.currentTarget.setPointerCapture(e.pointerId)}catch{}
  if(tool==='box'){const [x,y]=rel(e);setRect({x0:x,y0:y,x1:x,y1:y});return}
  gesture.current={added:[],removed:[]};touch(at(e),gesture.current);
 };
 const move=(e:RPointerEvent)=>{
  if(!vp||!pieces)return;
  if(rect){const [x,y]=rel(e);setRect({...rect,x1:x,y1:y});return}
  if(gesture.current)touch(at(e),gesture.current);
  else if(tool==='paint'&&e.pointerType!=='touch')setHover(pieceAt(pieces,at(e))||null);
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

 // Mover a página: ferramenta Mover, botão do meio ou Espaço + arrastar (mouse); um dedo na ferramenta Mover ou dois dedos em qualquer ferramenta (toque).
 const startPan=(e:RPointerEvent<HTMLDivElement>)=>{
  pan.current={x:e.clientX,y:e.clientY,l:e.currentTarget.scrollLeft,t:e.currentTarget.scrollTop,px:e.clientX,py:e.clientY,pt:performance.now(),vx:0,vy:0};setGrab(true);
 };
 const startPinch=()=>{
  const v=vpRef.current,s=sheet.current;if(!v||!s)return;
  abortGesture();pan.current=null;
  const [a,b]=[...ptrs.current.values()],mx=(a.x+b.x)/2,my=(a.y+b.y)/2,r=s.getBoundingClientRect();
  pinch.current={d:Math.hypot(a.x-b.x,a.y-b.y)||1,mx,my,cx:mx,cy:my,scale:scaleRef.current||v.scale,ratio:1,pdf:v.convertToPdfPoint(mx-r.left,my-r.top) as Pt};
  s.style.transformOrigin=`${mx-r.left}px ${my-r.top}px`;
 };
 const endPinch=()=>{ // a prévia (transform) fica até a nova imagem ficar pronta; o layout effect a remove
  const p=pinch.current,s=sheet.current,el=scroll.current,v=vpRef.current;pinch.current=null;
  if(!p||!s||!el||!v)return;
  const next=Math.max(.1,Math.min(MAX_ZOOM,p.scale*p.ratio));
  if(Math.abs(next/v.scale-1)<.01){s.style.transform='';el.scrollLeft-=p.cx-p.mx;el.scrollTop-=p.cy-p.my;return} // só arrastou com dois dedos
  anchor.current={pdf:p.pdf,x:p.cx,y:p.cy};applyZoom(next);
 };
 const panDown=(e:RPointerEvent<HTMLDivElement>)=>{
  cancelAnimationFrame(fling.current);
  if(e.pointerType==='touch'){
   ptrs.current.set(e.pointerId,{x:e.clientX,y:e.clientY});
   if(ptrs.current.size===2)startPinch();
   else if(ptrs.current.size===1&&tool==='move')startPan(e);
   return;
  }
  if(!(e.button===1||(e.button===0&&(tool==='move'||spaceRef.current))))return;
  e.preventDefault();try{e.currentTarget.setPointerCapture(e.pointerId)}catch{} // sem captura o arrasto ainda funciona dentro da área
  startPan(e);
 };
 const panMove=(e:RPointerEvent<HTMLDivElement>)=>{
  const t=ptrs.current.get(e.pointerId);if(t){t.x=e.clientX;t.y=e.clientY}
  const p=pinch.current;
  if(p&&sheet.current){
   const [a,b]=[...ptrs.current.values()];if(!b)return;
   p.cx=(a.x+b.x)/2;p.cy=(a.y+b.y)/2;p.ratio=Math.max(.1/p.scale,Math.min(MAX_ZOOM/p.scale,Math.hypot(a.x-b.x,a.y-b.y)/p.d));
   sheet.current.style.transform=`translate(${p.cx-p.mx}px,${p.cy-p.my}px) scale(${p.ratio})`;return;
  }
  const g=pan.current;if(!g)return;
  e.currentTarget.scrollLeft=g.l-(e.clientX-g.x);e.currentTarget.scrollTop=g.t-(e.clientY-g.y);
  const now=performance.now(),dt=Math.max(1,now-g.pt);g.vx=.7*(g.px-e.clientX)/dt+.3*g.vx;g.vy=.7*(g.py-e.clientY)/dt+.3*g.vy;g.px=e.clientX;g.py=e.clientY;g.pt=now;
 };
 const panUp=(e:RPointerEvent<HTMLDivElement>)=>{
  ptrs.current.delete(e.pointerId);
  if(pinch.current&&ptrs.current.size<2)endPinch();
  const g=pan.current;pan.current=null;setGrab(spaceRef.current);
  if(g&&e.pointerType==='touch'&&performance.now()-g.pt<80){ // arrasto solto em movimento: continua deslizando e desacelera
   const el=e.currentTarget;let {vx,vy}=g,last=performance.now();
   const step=(now:number)=>{
    const dt=now-last;last=now;el.scrollLeft+=vx*dt;el.scrollTop+=vy*dt;vx*=.95**(dt/16);vy*=.95**(dt/16);
    if(Math.hypot(vx,vy)>.02)fling.current=requestAnimationFrame(step);
   };
   if(Math.hypot(vx,vy)>.1)fling.current=requestAnimationFrame(step);
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
 const zoomBy=(f:number)=>applyZoom(Math.max(.1,Math.min(MAX_ZOOM,(scaleRef.current||vp?.scale||1)*f)));
 const path=(pts:Pt[])=>pts.map((p,i)=>{const q=vp.convertToViewportPoint(p[0],p[1]);return `${i?'L':'M'}${q[0]},${q[1]}`}).join(' ')+'Z';

 const info=TOOLS.find(t=>t[0]===tool)![3];
 const entry=legend.find(l=>l.color===color);
 return <div className="app">
  <header className="bar">
   <button aria-label="Voltar para os arquivos" onClick={()=>onBack(file?.folder_id??null)}>←<span className="d"> Arquivos</span></button>
   <img className="logo" src={logo} alt="COMBIO"/>
   <b className="title">{file?.name||'Abrindo…'}</b>
   {doc&&<>
    <span className="group"><button aria-label="Página anterior" disabled={pageNum<=1} onClick={()=>setPage(pageNum-1)}>◀</button><span><span className="d">pág. </span>{pageNum}/{doc.numPages}</span><button aria-label="Próxima página" disabled={pageNum>=doc.numPages} onClick={()=>setPage(pageNum+1)}>▶</button></span>
    <span className="group zoom"><button aria-label="Diminuir o zoom" onClick={()=>zoomBy(.8)}>−</button><button aria-label="Ajustar à tela" onClick={()=>applyZoom(0)}><span className="d">Ajustar</span><span className="m">⤢</span></button><button aria-label="Aumentar o zoom" onClick={()=>zoomBy(1.25)}>+</button></span>
    <button aria-label="Copiar link" onClick={copyLink}>🔗<span className="d"> Copiar link</span></button>
    <button className="primary" aria-label="Baixar PDF colorido" disabled={busy} onClick={save}>⬇<span className="d"> Baixar PDF colorido</span></button>
   </>}
  </header>
  {!online&&<div className="offline" role="status">Sem internet: o que você pintar fica na fila e é enviado quando a conexão voltar. Não feche esta página.</div>}
  {doc&&<div className="dock">
   <div className="tools">{TOOLS.map(([id,icon,label])=><button key={id} className={'tool'+(tool===id?' on':'')} aria-pressed={tool===id} onClick={()=>{setTool(id);setHover(null)}}><span className="ico">{icon}</span><span>{label}</span></button>)}
    <button className="tool" disabled={!hist.current.length} onClick={undo}><span className="ico">↶</span><span>Desfazer</span></button></div>
   <div className="colors">
    <label className="picker" title="Escolher a cor de pintura"><input type="color" aria-label="Cor de pintura" value={color} onChange={e=>setColor(e.target.value)}/></label>
    {legend.map((l,i)=><button key={i} aria-label={'Usar a cor '+(l.label||'sem nome')} title={l.label} aria-pressed={color===l.color} className={'sw'+(color===l.color?' on':'')} style={{background:l.color}} onClick={()=>setColor(l.color)}/>)}
    <small className="cur">{entry?.label||'sem legenda'}</small>
    <button aria-expanded={legendOpen} onClick={()=>setLegendOpen(!legendOpen)}>Legenda{legend.length?` (${legend.length})`:''} {legendOpen?'▾':'▴'}</button>
   </div>
   <small className="hint d">{pieces?`${pieces.length} peças detectadas. `:'Lendo as peças do desenho… '}{info} Zoom: Ctrl + roda do mouse. Mover: botão do meio ou Espaço + arrastar.</small>
  </div>}
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
  {tip&&doc&&<div className="tip" onClick={()=>setTip(false)}>Dois dedos: mover e ampliar a página</div>}
  <div className={'scroll'+(grab||tool==='move'?' grab':'')} ref={scroll} onPointerDown={panDown} onPointerMove={panMove} onPointerUp={panUp} onPointerCancel={panUp} onMouseDown={e=>{if(e.button===1)e.preventDefault()}}>
   {!doc&&!msg&&<p className="center">Abrindo o arquivo…</p>}
   {doc&&!pieces&&<span className="chip">Lendo as peças…</span>}
   <div className="sheet" ref={sheet} style={{display:doc?'block':'none'}}>
    <canvas ref={canvas}/>
    {doc&&vp&&<svg width={vp.width} height={vp.height} style={{pointerEvents:tool==='move'?'none':'auto',touchAction:tool==='move'?'auto':'none',cursor:grab?'grab':tool==='move'?'default':!pieces?'wait':tool==='erase'?'pointer':'crosshair'}} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={abortGesture}>
     <g pointerEvents="none">{list.filter(s=>s.page===pageNum).map(s=><path key={s.id} d={path(s.points)} fill={s.color} fillOpacity=".4" stroke={s.color} strokeOpacity=".8"/>)}</g>
     {hover&&tool==='paint'&&<path d={path(hover.poly)} fill={color} fillOpacity=".2" stroke={color} strokeWidth="2" strokeDasharray="4 3" pointerEvents="none"/>}
     {rect&&<rect x={Math.min(rect.x0,rect.x1)} y={Math.min(rect.y0,rect.y1)} width={Math.abs(rect.x1-rect.x0)} height={Math.abs(rect.y1-rect.y0)} fill={rect.x1>=rect.x0?'#1E88E5':'#2E7D32'} fillOpacity=".12" stroke={rect.x1>=rect.x0?'#1E88E5':'#2E7D32'} strokeWidth="1.5" strokeDasharray={rect.x1>=rect.x0?undefined:'6 4'} pointerEvents="none"/>}
    </svg>}
   </div>
  </div>
 </div>;
}
