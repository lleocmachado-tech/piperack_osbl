import {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {demo,session} from './store';
import Editor from './Editor';
import Library from './Library';
import logo from './assets/combio-verde.png';
import './fonts.css';
import './style.css';

// Rotas pelo hash, para o endereço de um arquivo poder ser compartilhado: #/f/<arquivo> e #/p/<pasta>.
const go=(hash:string)=>{location.hash=hash};

function Login({onDone}:{onDone:()=>void}){
 const [password,setPassword]=useState(''),[msg,setMsg]=useState(''),[busy,setBusy]=useState(false);
 return <form className="login" onSubmit={e=>{e.preventDefault();setBusy(true);setMsg('');session.login(password).then(onDone,e=>{setMsg(e.message);setBusy(false)})}}>
  <img src={logo} alt="COMBIO"/>
  <h1>Marcador de avanço</h1>
  <input type="password" required autoFocus placeholder="Senha da equipe" value={password} onChange={e=>setPassword(e.target.value)}/>
  <button disabled={busy}>Entrar</button>{msg&&<p className="err">{msg}</p>}
 </form>;
}

function Root(){
 const [authed,setAuthed]=useState(()=>session.restore()),[hash,setHash]=useState(location.hash);
 useEffect(()=>{const h=()=>setHash(location.hash);addEventListener('hashchange',h);return()=>removeEventListener('hashchange',h)},[]);
 const file=hash.match(/^#\/f\/([\w-]+)$/)?.[1],folder=hash.match(/^#\/p\/([\w-]+)$/)?.[1]??null;
 return <>
  {authed&&demo&&<div className="demo">Modo de teste: esta versão foi gerada sem a URL e a chave do Supabase (VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY), então nada é salvo online nem aparece para os outros, e tudo se perde ao recarregar.</div>}
  {!authed?<Login onDone={()=>setAuthed(true)}/>
   :file?<Editor key={file} fileId={file} onBack={f=>go(f?'#/p/'+f:'#/')}/>
   :<Library folderId={folder} onOpen={id=>go('#/f/'+id)} onFolder={id=>go(id?'#/p/'+id:'#/')} onSignOut={()=>{session.logout();setAuthed(false)}}/>}
 </>;
}
createRoot(document.getElementById('root')!).render(<Root/>);
