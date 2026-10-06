import {useEffect,useState} from 'react';
import PdfCanvas from './PdfCanvas';
import {Row, State} from './api';

type Props = {
 state:State;page?:Row;stage:string;piece?:Row;selected:string;tool:string;
 zoom:number;rotation:number;opacity:number;layers:boolean;evidenceBox:number[]|null;
 onPage:(id:string)=>void;onPiece:(id:string)=>void;onTool:(tool:string)=>void;
 onZoom:(zoom:number)=>void;onRotate:()=>void;onLayers:(value:boolean)=>void;
 onOpacity:(value:number)=>void;onSelect:(id:string)=>void;onDraft:(data:any)=>void;
 onEdit:(id:string,data:any)=>void;onError:(error:Error)=>void;
 onManage:()=>void;onExport:()=>void;onProgress:(value:number)=>void;
};
const number=(n:number)=>n.toLocaleString('pt-BR',{maximumFractionDigits:1});
export default function FieldWorkspace(p:Props){
 const [search,setSearch]=useState(''),[options,setOptions]=useState(false);
 const [panelOpen,setPanelOpen]=useState(false),[expanded,setExpanded]=useState(false),[renderedScale,setRenderedScale]=useState(.42);
 useEffect(()=>{if(p.selected)setPanelOpen(true)},[p.selected]);
 useEffect(()=>{if(!expanded)return;const escape=(event:KeyboardEvent)=>{if(event.key==='Escape')setExpanded(false)};window.addEventListener('keydown',escape);return()=>window.removeEventListener('keydown',escape)},[expanded]);
 const chooseTool=(tool:string)=>{p.onTool(tool);if(tool!=='select')setPanelOpen(false)};
 const currentScale=p.zoom>0?p.zoom:renderedScale;
 const stepZoom=(direction:number)=>p.onZoom(Math.max(.1,Math.min(2,Math.round(currentScale*(direction>0?1.25:1/1.25)*1000)/1000)));
 const zoomLevels=[.1,.2,.32,.42,.55,.75,1,1.5,2];
 const s=p.state, stage=s.stages.find((x:Row)=>x.id===p.stage);
 const occurrence=s.occurrences.find((o:Row)=>o.geometry_id===p.selected);
 const unit=s.instances.find((u:Row)=>u.id===occurrence?.instance_id);
 const balance=(type:string,unit?:string)=>s.progress_events.filter((e:Row)=>e.stage_id===p.stage&&e.type_id===type&&(unit===undefined||e.instance_id===unit)).reduce((n:number,e:Row)=>n+e.delta,0);
 const approved=s.piece_types.filter((x:Row)=>x.category==='structure'&&x.validation==='APPROVED');
 const total=approved.reduce((n:number,x:Row)=>n+(x.quantity||0),0),done=approved.reduce((n:number,x:Row)=>n+balance(x.id),0);
 const pageViews=s.views.filter((v:Row)=>v.page_id===p.page?.id);
 const areas=s.occurrences.filter((o:Row)=>pageViews.some((v:Row)=>v.id===o.view_id)&&!s.geometries.find((g:Row)=>g.id===o.geometry_id)?.data.deleted);
 const matches=s.piece_types.filter((x:Row)=>x.category==='structure'&&(x.code.toLowerCase().includes(search.toLowerCase())||x.data.description?.toLowerCase().includes(search.toLowerCase())));
 const selectedDone=unit&&occurrence?.association==='APROVADA'&&balance(unit.type_id,unit.id)>=1;
 const selectedMeasured=unit&&occurrence?.association==='APROVADA';
 const color=`var(--${stage?.token||'sucesso'})`;
 const label=stage?.name==='Montagem'?'Montagem':stage?.name||'Montagem';
 return <main className={'field-workspace'+(expanded?' is-expanded':'')}>
  <div className="field-topline"><div className="drawing-picker"><label htmlFor="field-drawing">Desenho</label><select id="field-drawing" value={p.page?.id||''} onChange={e=>p.onPage(e.target.value)}>{s.pages.filter((page:Row)=>!s.drawings.find((d:Row)=>d.id===page.drawing_id)?.data.superseded).map((page:Row)=>{const drawing=s.drawings.find((d:Row)=>d.id===page.drawing_id);return <option value={page.id} key={page.id}>{drawing?.technical_number} · rev. {drawing?.revision}{s.pages.filter((x:Row)=>x.drawing_id===page.drawing_id).length>1?` · pág. ${page.number}`:''}</option>})}</select></div>
   <div className="field-summary" title={total?`${number(done)} de ${number(total)} peças no escopo confirmado`:'Confirme os códigos ao marcar as primeiras peças'}><span>{label} <strong>{total?`${number(done*100/total)}%`:'—'}</strong></span>{total>0&&<small>{number(done)}/{number(total)} peças no escopo confirmado</small>}</div>
   <button className="secondary" onClick={p.onExport}>Exportar desenho</button>
  </div>
  <div className={'field-layout'+(panelOpen?' with-panel':'')}><section className="field-drawing" aria-label="Desenho de montagem">
   <div className="field-toolbar" role="toolbar" aria-label="Marcação de campo">
    <div className="tool-group">{[['select','Selecionar'],['rectangle','Marcar área'],['polygon','Contornar peça']].map(([id,label])=><button key={id} aria-pressed={p.tool===id} className={'secondary '+(p.tool===id?'active':'')} onClick={()=>chooseTool(id)}>{label}</button>)}</div>
    <div className="pdf-zoom-controls" role="group" aria-label="Zoom do desenho"><span>Zoom</span><button className="secondary zoom-step" aria-label="Diminuir zoom" title="Diminuir zoom" disabled={currentScale<=.1} onClick={()=>stepZoom(-1)}>−</button><select aria-label="Zoom" value={p.zoom} onChange={e=>p.onZoom(Number(e.target.value))}><option value={-1}>Largura · {number(renderedScale*100)}%</option><option value={0}>Página · {number(renderedScale*100)}%</option>{p.zoom>0&&!zoomLevels.includes(p.zoom)&&<option value={p.zoom}>{number(p.zoom*100)}%</option>}{zoomLevels.map(value=><option key={value} value={value}>{number(value*100)}%</option>)}</select><button className="secondary zoom-step" aria-label="Aumentar zoom" title="Aumentar zoom" disabled={currentScale>=2} onClick={()=>stepZoom(1)}>+</button><button className="secondary fit-page" onClick={()=>p.onZoom(0)}>Ajustar à tela</button></div>
    <div className="tool-group drawing-options"><button className="secondary" aria-expanded={panelOpen} aria-controls="field-piece-panel" onClick={()=>setPanelOpen(!panelOpen)}>{panelOpen?'Ocultar peças':'Peças'}</button><button className="secondary" aria-pressed={expanded} onClick={()=>setExpanded(!expanded)}>{expanded?'Sair da tela ampliada':'Ampliar desenho'}</button><button className="secondary" aria-expanded={options} onClick={()=>setOptions(!options)}>Visualização</button></div>
   </div>
   {options&&<div className="field-view-options"><button className="secondary small" onClick={p.onRotate}>Girar 90°</button><label><input type="checkbox" checked={p.layers} onChange={e=>p.onLayers(e.target.checked)}/> Mostrar cores</label><label>Intensidade <input aria-label="Intensidade das cores" type="range" min=".2" max="1" step=".05" value={p.opacity} onChange={e=>p.onOpacity(Number(e.target.value))}/></label></div>}
   {p.page?<PdfCanvas state={s} page={p.page} stage={p.stage} piece={p.piece} selected={p.selected} tool={p.tool} zoom={p.zoom} rotation={p.rotation} opacity={p.opacity} layers={p.layers} typical={false} evidenceBox={p.evidenceBox} onSelect={id=>{p.onSelect(id);setPanelOpen(true)}} onDraft={p.onDraft} onEdit={p.onEdit} onError={p.onError} onScaleChange={setRenderedScale} simple/>:<div className="empty"><h2>Adicione o primeiro desenho</h2><button onClick={p.onManage}>Importar PDF</button></div>}
   <div className="field-legend" aria-label="Legenda das cores"><span><i style={{background:color}}/>{label} concluída</span><span><i className="unmeasured"/>Sem {label.toLowerCase()} registrada</span>{areas.some((o:Row)=>o.association!=='APROVADA')&&<span><i className="review-color"/>Vínculo a revisar</span>}{areas.some((o:Row)=>!o.instance_id)&&<span><i className="aggregate-color"/>Sem posição confirmada</span>}</div>
  </section>
  {panelOpen&&<aside id="field-piece-panel" className="field-panel" aria-label="Peça e montagem"><button className="text-button panel-close" onClick={()=>setPanelOpen(false)}>Fechar painel ×</button><div className="field-panel-heading"><span className="eyebrow">MONTAGEM EM CAMPO</span><h2>{p.piece?p.piece.code:'Marque o que foi montado'}</h2></div>
   {!p.piece?<><p className="field-help">Marque a peça no desenho e informe o código e a posição na obra.</p><button className="field-primary" disabled={!p.page} onClick={()=>chooseTool('rectangle')}>+ Marcar peça</button><div className="search-section"><label htmlFor="field-search">Ou encontre pelo código</label><input id="field-search" placeholder="Ex.: 212-F" value={search} onChange={e=>setSearch(e.target.value)}/>{search.trim()&&<div className="field-results">{matches.slice(0,12).map((x:Row)=><button className="secondary" key={x.id} onClick={()=>{p.onPiece(x.id);setSearch('')}}><b>{x.code}</b><small>{x.data.description||'Peça estrutural'}</small></button>)}{matches.length===0&&<p>Nenhum código encontrado. Cadastre-o em Gestão e revisão.</p>}{matches.length>12&&<small>Digite mais caracteres para refinar.</small>}</div>}</div><div className="field-steps"><span><b>1</b> Marque a peça</span><span><b>2</b> Identifique a posição</span><span><b>3</b> Confirme a montagem</span></div></>:<>
    <p className="field-help">{p.piece.data.description||'Peça estrutural'}{p.piece.data.profile?` · ${p.piece.data.profile}`:''}</p>
    <div className="field-piece-total"><strong>{number(balance(p.piece.id))}</strong><span>de {p.piece.validation==='APPROVED'?p.piece.quantity:'—'} peças com {label.toLowerCase()} registrada</span></div>
    {unit?<div className="field-selection"><small>POSIÇÃO SELECIONADA</small><b>{unit.data.location}</b><span className="field-state"><i style={{background:selectedDone?color:'var(--texto-sec)'}}/>{selectedDone?`${label} concluída`:selectedMeasured?'Sem conclusão registrada':'Vínculo a revisar'}</span>{selectedMeasured?<button disabled={!stage?.data.approved} onClick={()=>p.onProgress(selectedDone?0:1)}>{selectedDone?'Corrigir montagem':'Confirmar montagem'}</button>:<button className="secondary" onClick={p.onManage}>Revisar vínculo</button>}</div>:<p className="field-help">Marque a posição desta peça no desenho para registrar a montagem.</p>}
    <button className={unit?'secondary field-primary':'field-primary'} disabled={!p.page} onClick={()=>chooseTool('rectangle')}>+ Marcar outra posição</button><button className="text-button" onClick={()=>p.onPiece('')}>Trocar código</button>
    {areas.some((o:Row)=>o.type_id===p.piece?.id)&&<div className="field-position-list"><h3>Posições neste desenho</h3>{areas.filter((o:Row)=>o.type_id===p.piece?.id).map((o:Row)=>{const u=s.instances.find((u:Row)=>u.id===o.instance_id);return <button className={'secondary '+(o.geometry_id===p.selected?'active':'')} key={o.id} onClick={()=>{p.onTool('select');p.onSelect(o.geometry_id)}}><i style={{background:o.association==='APROVADA'&&u&&balance(o.type_id,u.id)>=1?color:'var(--texto-sec)'}}/>{u?.data.location||'Posição a identificar'}</button>})}</div>}
   </>}
   <button className="field-manage text-button" onClick={p.onManage}>Gestão e revisão →</button>
  </aside>}</div>
 </main>;
}
