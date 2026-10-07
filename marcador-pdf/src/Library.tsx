import {useEffect,useState} from 'react';
import {backend,FileRow,Folder} from './store';
import logo from './assets/combio-branco.png';

// Pastas de um nível (ex.: "TR01" com os desenhos dentro) e arquivos soltos na raiz.
export default function Library({folderId,onOpen,onFolder,onSignOut}:{folderId:string|null;onOpen:(id:string)=>void;onFolder:(id:string|null)=>void;onSignOut:()=>void}){
 const [data,setData]=useState<{folders:Folder[];files:FileRow[]}|null>(null);
 const [creating,setCreating]=useState(false),[msg,setMsg]=useState(''),[busy,setBusy]=useState(false);
 const [form,setForm]=useState<{name:string;folder:string;pdfName:string;pdf:Uint8Array|null}>({name:'',folder:'',pdfName:'',pdf:null});
 const fail=(e:any)=>setMsg(e?.message||String(e));
 const load=()=>backend.list().then(setData).catch(fail);
 useEffect(()=>{void load();return backend.watchList(()=>void load())},[]);
 const run=(job:()=>Promise<unknown>)=>job().then(load).catch(fail);

 if(!data)return <p className="center">{msg||'Carregando…'}</p>;
 const folder=data.folders.find(f=>f.id===folderId);
 const files=data.files.filter(f=>f.folder_id===folderId);
 const ask=(label:string,def='')=>(window.prompt(label,def)||'').trim();

 async function create(e:React.FormEvent){
  e.preventDefault();if(!form.pdf)return;setBusy(true);
  try{
   const inherit=data!.files.filter(f=>f.folder_id===(form.folder||null)&&f.legend.length).at(-1)?.legend||[]; // legenda do último arquivo da pasta
   const f=await backend.createFile(form.name,form.folder||null,form.pdfName,form.pdf,inherit);
   setCreating(false);onOpen(f.id);
  }catch(err){fail(err)}finally{setBusy(false)}
 }

 return <div className="lib">
  <header className="bar">
   <img className="logo" src={logo} alt="COMBIO"/>
   <b className="title">Marcador de avanço</b>
   <button onClick={onSignOut}>Sair</button>
  </header>
  {msg&&<div className="msg" role="alert">{msg}<button onClick={()=>setMsg('')}>×</button></div>}
  <div className="list">
   <div className="actions-top">
    <button className="primary" onClick={()=>{setForm({name:'',folder:folderId||'',pdfName:'',pdf:null});setCreating(true)}}>+ Novo arquivo</button>
    {!folderId&&<button onClick={()=>{const n=ask('Nome da pasta (ex.: TR01)');if(n)void run(()=>backend.createFolder(n))}}>+ Nova pasta</button>}
   </div>
   <nav className="crumbs"><button onClick={()=>onFolder(null)} disabled={!folderId}>Todos os arquivos</button>{folder&&<> / <b>{folder.name}</b>
    <button onClick={()=>{const n=ask('Novo nome da pasta',folder.name);if(n)void run(()=>backend.renameFolder(folder.id,n))}}>Renomear</button>
    <button disabled={!!files.length} title={files.length?'Esvazie a pasta para excluir':''} onClick={()=>{if(confirm(`Excluir a pasta "${folder.name}"?`))void run(()=>backend.deleteFolder(folder.id).then(()=>onFolder(null)))}}>Excluir pasta</button></>}</nav>
   {!folderId&&data.folders.map(f=><div className="item" key={f.id}>
    <button className="name" onClick={()=>onFolder(f.id)}>📁 {f.name} <small>({data.files.filter(x=>x.folder_id===f.id).length})</small></button>
   </div>)}
   {files.map(f=><div className="item" key={f.id}>
    <button className="name" onClick={()=>onOpen(f.id)}>📄 {f.name}</button>
    <select aria-label="Pasta" value={f.folder_id||''} onChange={e=>void run(()=>backend.moveFile(f.id,e.target.value||null))}><option value="">Sem pasta</option>{data.folders.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select>
    <button onClick={()=>{const n=ask('Novo nome do arquivo',f.name);if(n)void run(()=>backend.renameFile(f.id,n))}}>Renomear</button>
    <button onClick={()=>{if(confirm(`Excluir "${f.name}" e todas as marcas dele? Não dá para desfazer.`))void run(()=>backend.deleteFile(f.id))}}>Excluir</button>
   </div>)}
   {!files.length&&!(folderId===null&&data.folders.length)&&<p className="empty">{folder?'Esta pasta está vazia.':'Nenhum arquivo ainda. Clique em "+ Novo arquivo" e escolha um PDF.'}</p>}
  </div>
  {creating&&<div className="backdrop"><form className="modal" onSubmit={create}>
   <h2>Novo arquivo</h2>
   <label>PDF do desenho<input required type="file" accept="application/pdf" onChange={async e=>{const f=e.target.files?.[0];if(!f)return;const bytes=new Uint8Array(await f.arrayBuffer());setForm(x=>({...x,pdf:bytes,pdfName:f.name,name:x.name||f.name.replace(/\.pdf$/i,'')}))}}/></label>
   <label>Nome do arquivo<input required maxLength={120} value={form.name} onChange={e=>setForm({...form,name:e.target.value})} placeholder="ex.: TR01 - Elevação A"/></label>
   <label>Pasta<select value={form.folder} onChange={e=>setForm({...form,folder:e.target.value})}><option value="">Sem pasta</option>{data.folders.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
   <div className="actions"><button type="button" onClick={()=>setCreating(false)}>Cancelar</button><button className="primary" disabled={busy||!form.pdf}>{busy?'Enviando…':'Criar'}</button></div>
  </form></div>}
 </div>;
}
