import {useEffect,useRef,useState} from 'react';
import * as pdfjs from 'pdfjs-dist';
import worker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import {api,Row,State,token} from './api';
pdfjs.GlobalWorkerOptions.workerSrc=worker;
type Point=[number,number];
type Props={state:State;page:Row;stage:string;piece?:Row;selected:string;tool:string;zoom:number;rotation:number;opacity:number;layers:boolean;typical:boolean;evidenceBox:number[]|null;simple?:boolean;onScaleChange?:(scale:number)=>void;onSelect:(id:string)=>void;onDraft:(data:any)=>void;onEdit:(id:string,data:any)=>void;onError:(error:Error)=>void};
export default function PdfCanvas(props:Props){
 const {state,page,tool,zoom,rotation}=props;const canvas=useRef<HTMLCanvasElement>(null);const wrap=useRef<HTMLDivElement>(null);
 const [viewport,setViewport]=useState<any>(null);const [paths,setPaths]=useState<Point[][]>([]);const [points,setPoints]=useState<Point[]>([]);const [drawing,setDrawing]=useState(false);const [drag,setDrag]=useState<{path:number;index:number}|null>(null);const [draftEdit,setDraftEdit]=useState<any>(null);
 const [primitives,setPrimitives]=useState<any[]>([]);const [chosen,setChosen]=useState<any[]>([]);const [latency,setLatency]=useState(0);const [loading,setLoading]=useState(true);
 const scroll=useRef<HTMLDivElement>(null);const [size,setSize]=useState({width:800,height:600});
 useEffect(()=>{if(!scroll.current)return;const observer=new ResizeObserver(([entry])=>setSize({width:entry.contentRect.width,height:entry.contentRect.height}));observer.observe(scroll.current);return()=>observer.disconnect()},[]);
 const scale=viewport?.scale||(zoom>0?zoom:.42);
 const previousView=useRef<{pageId:string;viewport:any}|null>(null);
 useEffect(()=>{if(viewport)props.onScaleChange?.(viewport.scale)},[viewport?.scale,props.onScaleChange]);
 const pid=state.project.id;const doc=state.drawings.find((d:Row)=>d.id===page.drawing_id);
 useEffect(()=>{setPaths([]);setPoints([]);setChosen([]);setDraftEdit(null)},[tool,page.id]);
 useEffect(()=>{
  const old=previousView.current,scroller=scroll.current,surface=wrap.current;
  const anchor=old?.pageId===page.id&&scroller&&surface&&zoom>0?old.viewport.convertToPdfPoint(scroller.getBoundingClientRect().left+scroller.clientLeft+scroller.clientWidth/2-surface.getBoundingClientRect().left,scroller.getBoundingClientRect().top+scroller.clientTop+scroller.clientHeight/2-surface.getBoundingClientRect().top):null;
  let stopped=false;let document:any;let renderTask:any;const task=pdfjs.getDocument({url:`/api/projects/${pid}/drawings/${doc.id}/original`,httpHeaders:token()?{Authorization:`Bearer ${token()}`}:{}});setLoading(true);
  const started=performance.now();
  (async()=>{try{document=await task.promise;const p=await document.getPage(page.number);if(stopped)return;
    const native=p.getViewport({scale:1,rotation:(p.rotate+rotation)%360});const fitWidth=Math.max(.03,(size.width-24)/native.width);const fit=Math.max(.03,Math.min(fitWidth,(size.height-24)/native.height));
    const v=p.getViewport({scale:zoom>0?zoom:zoom===-1?fitWidth:fit,rotation:(p.rotate+rotation)%360});const ratio=Math.min(window.devicePixelRatio||1,Math.sqrt(24000000/(v.width*v.height)));const cv=canvas.current!;cv.width=Math.round(v.width*ratio);cv.height=Math.round(v.height*ratio);cv.style.width=v.width+'px';cv.style.height=v.height+'px';
    setViewport(v);previousView.current={pageId:page.id,viewport:v};
    requestAnimationFrame(()=>{if(stopped||!scroller||!surface)return;if(!anchor){scroller.scrollTo(0,0);return}const q=v.convertToViewportPoint(...anchor);scroller.scrollLeft+=surface.getBoundingClientRect().left+q[0]-scroller.getBoundingClientRect().left-scroller.clientLeft-scroller.clientWidth/2;scroller.scrollTop+=surface.getBoundingClientRect().top+q[1]-scroller.getBoundingClientRect().top-scroller.clientTop-scroller.clientHeight/2});
    renderTask=p.render({canvas:cv,canvasContext:cv.getContext('2d')!,viewport:v,transform:ratio===1?undefined:[ratio,0,0,ratio,0,0]});await renderTask.promise;if(!stopped){setLatency(performance.now()-started);setLoading(false)}
  }catch(e){if(!stopped)props.onError(e as Error)}})();return()=>{stopped=true;renderTask?.cancel();void task.destroy()};
 },[page.id,zoom,rotation,pid,doc.id,zoom>0?0:size.width,zoom>0?0:size.height]);
 useEffect(()=>{if(tool==='primitives')api(`/projects/${pid}/pages/${page.id}/primitives`).then(r=>setPrimitives(r.segments)).catch(props.onError)},[tool,page.id,pid]);
 const local=(e:React.PointerEvent):Point=>{const box=wrap.current!.getBoundingClientRect();return viewport.convertToPdfPoint(e.clientX-box.left,e.clientY-box.top) as Point};
 const pathD=(path:Point[],close:boolean)=>path.map((p,i)=>{const q=viewport.convertToViewportPoint(...p);return `${i?'L':'M'}${q[0]},${q[1]}`}).join(' ')+(close?' Z':'');
 function finish(){let all=[...paths];if(points.length>=(tool==='polygon'||tool==='multipolygon'||tool==='view'?3:2))all.push(points);if(tool==='primitives')all=chosen.map(p=>p.paths[0]);if(!all.length)return;
  props.onDraft({kind:tool==='rectangle'||tool==='view'||tool==='polygon'?'polygon':tool==='multipolygon'?'multipolygon':tool==='line'?'line':'freehand',paths:all,width:tool==='primitives'?2:6,primitive_ids:chosen.map(p=>p.id)});setPaths([]);setPoints([]);setChosen([]);
 }
 function addComponent(){if(points.length>=3){setPaths([...paths,points]);setPoints([])}}
 function pointerDown(e:React.PointerEvent){
  if(!viewport||loading||drag)return;const p=local(e);
  if(tool==='polygon'||tool==='multipolygon'||tool==='view'){if(!points.length||Math.hypot(points.at(-1)![0]-p[0],points.at(-1)![1]-p[1])>1/scale)setPoints([...points,p]);return}
  if(['rectangle','line','freehand','clip'].includes(tool)){e.currentTarget.setPointerCapture(e.pointerId);setDrawing(true);setPoints([p]);return}
  if(tool==='primitives'){
   let nearest:any;let min=8/scale;
   for(const primitive of primitives){const [a,b]=primitive.paths[0];const dx=b[0]-a[0],dy=b[1]-a[1];const l=dx*dx+dy*dy;const t=Math.max(0,Math.min(1,l?((p[0]-a[0])*dx+(p[1]-a[1])*dy)/l:0));const d=Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);if(d<min){min=d;nearest=primitive}}
   if(nearest)setChosen(chosen.some(c=>c.id===nearest.id)?chosen.filter(c=>c.id!==nearest.id):[...chosen,nearest]);
  }
 }
 function pointerMove(e:React.PointerEvent){
  if(!viewport)return;const p=local(e);
  if(drag&&draftEdit){const copy=structuredClone(draftEdit);copy.paths[drag.path][drag.index]=p;setDraftEdit(copy);return}
  if(!drawing)return;
  if(tool==='freehand'){if(Math.hypot(points.at(-1)![0]-p[0],points.at(-1)![1]-p[1])>2/scale)setPoints([...points,p])}
  else setPoints([points[0],p]);
 }
 function pointerUp(){
  if(drag){if(draftEdit)props.onEdit(props.selected,draftEdit);setDrag(null);setDraftEdit(null);return}
  if(!drawing)return;setDrawing(false);
  if((tool==='rectangle'||tool==='clip')&&points.length===2){const [a,b]=points;const polygon:Point[]=[a,[b[0],a[1]],b,[a[0],b[1]]];if(tool==='clip'){props.onDraft({kind:'clip',box:[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])]});setPoints([])}else setPoints(polygon)}
 }
 const balance=(type:string,unit:string|null)=>state.progress_events.filter((e:Row)=>e.type_id===type&&e.stage_id===props.stage&&e.instance_id===unit).reduce((a:number,e:Row)=>a+e.delta,0);
 const stage=state.stages.find((s:Row)=>s.id===props.stage);
 const pageViews=state.views.filter((v:Row)=>v.page_id===page.id);const occurrences=state.occurrences.filter((o:Row)=>pageViews.some((v:Row)=>v.id===o.view_id));
 const visible=state.geometries.filter((g:Row)=>g.page_id===page.id&&!g.data.deleted);
 const selectedGeometry=visible.find((g:Row)=>g.id===props.selected);
 return <><div className="canvas-status" data-ready={!loading}><span>{loading?'Carregando desenho…':props.simple?(tool==='rectangle'?'Arraste sobre a peça e clique em Continuar.':tool==='polygon'?'Clique nos cantos da peça e depois em Continuar.':'Selecione uma marca para consultar ou atualizar a montagem.'):`PDF.js · ${(latency/1000).toFixed(2)} s · coordenadas em pontos PDF`}</span>{!props.simple&&<span>{points.length+paths.reduce((a,p)=>a+p.length,0)} vértices em rascunho</span>}</div>
  <div className="pdf-scroll" ref={scroll}><div ref={wrap} className="pdf-surface" data-scale={viewport?.scale} style={viewport?{width:viewport.width,height:viewport.height}:{}}>
   <canvas ref={canvas}/>{viewport&&<svg className="pdf-overlay" width={viewport.width} height={viewport.height} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onDoubleClick={e=>{e.preventDefault();if(['polygon','view','multipolygon'].includes(tool))finish()}}>
    <defs><pattern id="pending" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M0 8L8 0" stroke="var(--atencao)" strokeWidth="1"/></pattern><pattern id="aggregate" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M0 4H8" stroke="var(--info)" strokeWidth="1"/></pattern></defs>
    {props.layers&&!props.simple&&pageViews.map((v:Row)=><path key={v.id} d={pathD(v.data.polygon,true)} fill="none" stroke="var(--borda)" strokeDasharray="3 6" pointerEvents="none"><title>{v.name} · {v.kind}</title></path>)}
    {props.layers&&visible.map((g:Row)=>{
     const o=occurrences.find((o:Row)=>o.geometry_id===g.id);const annotation=state.overlays.find((a:Row)=>a.geometry_id===g.id&&a.data.active!==false);
     const complete=o?.association==='APROVADA'&&o.instance_id&&balance(o.type_id,o.instance_id)>=1;
     const aggregate=o?.association==='APROVADA'&&!o.instance_id&&balance(o.type_id,null)>0&&(o.role==='installation'||props.typical);
     const pending=o&&o.association!=='APROVADA';const selected=g.id===props.selected;const match=o&&props.piece?.id===o.type_id;
     const color=annotation?`var(--${annotation.data.token||'info'})`:complete?`var(--${stage?.token||'sucesso'})`:aggregate?'var(--info)':pending?'var(--atencao)':!props.simple&&match?'var(--combio)':'var(--texto-sec)';
     const geom=selected&&draftEdit?draftEdit:g.data;
     return <g key={g.id} opacity={props.opacity} onPointerDown={e=>{if(['select','edit','erase'].includes(tool)){e.stopPropagation();props.onSelect(g.id)}}} style={{cursor:'pointer'}}>
      {geom.paths.map((p:Point[],index:number)=><path key={index} pointerEvents="all" d={pathD(p,geom.kind==='polygon'||geom.kind==='multipolygon')} fill={complete?color:aggregate?'url(#aggregate)':pending?'url(#pending)':'none'} fillOpacity={complete?.32:1} stroke={color} strokeWidth={(selected?3:Math.max(1,geom.width*scale))} strokeDasharray={annotation||pending||aggregate?'6 4':undefined}><title>{o?`${state.piece_types.find((t:Row)=>t.id===o.type_id)?.code} · ${complete?'Montagem concluída':pending?'Vínculo a revisar':'Sem conclusão registrada'}`:'Anotação'}</title></path>)}
      {selected&&tool==='edit'&&geom.paths.flatMap((p:Point[],pi:number)=>p.map((point:Point,i:number)=>{const q=viewport.convertToViewportPoint(...point);return <circle key={`${pi}-${i}`} cx={q[0]} cy={q[1]} r="5" fill="var(--superficie)" stroke="var(--combio)" onPointerDown={e=>{e.stopPropagation();e.currentTarget.setPointerCapture(e.pointerId);setDrag({path:pi,index:i});setDraftEdit(structuredClone(geom))}}/>}))}
     </g>})}
    {props.evidenceBox&&<path d={pathD([[props.evidenceBox[0],props.evidenceBox[1]],[props.evidenceBox[2],props.evidenceBox[1]],[props.evidenceBox[2],props.evidenceBox[3]],[props.evidenceBox[0],props.evidenceBox[3]]],true)} fill="none" stroke="var(--info)" strokeWidth="3" pointerEvents="none"/>}
    {[...paths,...(points.length?[points]:[])].map((p,i)=><path key={`draft${i}`} d={pathD(p,['rectangle','polygon','view','multipolygon'].includes(tool))} fill="none" stroke="var(--combio)" strokeWidth="2" strokeDasharray="4 3" pointerEvents="none"/>)}
    {chosen.map(p=><path key={'prim'+p.id} d={pathD(p.paths[0],false)} fill="none" stroke="var(--info)" strokeWidth="3" pointerEvents="none"/>)}
   </svg>}
  </div></div>
  {!['select','edit','erase','clip'].includes(tool)&&<div className="draft-bar">{!props.simple&&<span>{tool==='primitives'?'Selecione explicitamente as linhas. Textos e cotas podem estar entre as primitivas.':'Clique para desenhar. Finalize para revisar o vínculo; desenhar não registra avanço.'}</span>}{tool==='multipolygon'&&<button onClick={addComponent}>Novo componente</button>}{(!props.simple||tool==='polygon')&&<button onClick={()=>{setPoints(points.slice(0,-1));setChosen(chosen.slice(0,-1))}} className="secondary">Desfazer ponto</button>}<button disabled={props.simple&&points.length<3} onClick={finish}>{props.simple?'Continuar →':'Finalizar área'}</button><button className="secondary" onClick={()=>{setPoints([]);setPaths([]);setChosen([])}}>Limpar marca</button></div>}
  {tool==='edit'&&!selectedGeometry&&<div className="notice">Selecione uma área para editar os vértices.</div>}
 </>;
}
