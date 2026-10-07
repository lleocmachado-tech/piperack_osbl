// Camada de dados. Segue o padrão da Interface OSBL: a senha da equipe é conferida pela Netlify Function
// verify-password, que devolve a URL e a anon key do Supabase compartilhado. Sem a função (dev local ou arquivo
// aberto do disco) cai num modo de teste em memória: tudo funciona, mas nada é guardado ao recarregar.
import {createClient} from '@supabase/supabase-js';

export type Pt=[number,number];
// Legenda: o que significa cada cor. Cada arquivo tem a sua.
export type Legend={color:string;label:string}[];
export type Folder={id:string;name:string};
export type FileRow={id:string;folder_id:string|null;name:string;pdf_name:string;legend:Legend};
// Uma marca = o polígono de uma peça (coordenadas de ponto do PDF) pintado com uma cor.
export type Mark={id:string;file_id:string;page:number;color:string;points:Pt[]};
export type Watch={onAdd:(m:Mark)=>void;onDel:(id:string)=>void;onLegend:(l:Legend)=>void};

export interface Backend{
 list():Promise<{folders:Folder[];files:FileRow[]}>;
 file(id:string):Promise<FileRow>;
 createFolder(name:string):Promise<void>;
 renameFolder(id:string,name:string):Promise<void>;
 deleteFolder(id:string):Promise<void>; // só pasta vazia
 createFile(name:string,folderId:string|null,pdfName:string,pdf:Uint8Array,legend:Legend):Promise<FileRow>;
 renameFile(id:string,name:string):Promise<void>;
 moveFile(id:string,folderId:string|null):Promise<void>;
 deleteFile(id:string):Promise<void>;
 saveLegend(id:string,legend:Legend):Promise<void>;
 pdf(id:string):Promise<Uint8Array>;
 marks(fileId:string):Promise<Mark[]>;
 addMarks(list:Mark[]):Promise<void>;
 removeMarks(ids:string[]):Promise<void>;
 watch(fileId:string,w:Watch):()=>void;
 watchList(cb:()=>void):()=>void;
}

const fail=(e:{message:string}|null)=>{if(e)throw Error(e.message)};
const chunks=<T,>(a:T[],n:number)=>Array.from({length:Math.ceil(a.length/n)},(_,i)=>a.slice(i*n,i*n+n));
const clean=(name:string)=>{const n=name.trim();if(!n||n.length>120)throw Error('Informe um nome de até 120 caracteres.');return n};

// Tabelas e bucket com prefixo marcador, porque o banco é compartilhado com outros apps da Interface OSBL.
const T={folders:'marcador_folders',files:'marcador_files',marks:'marcador_marks',bucket:'marcador-pdfs'};
const FILE_COLS='id,folder_id,name,pdf_name,legend';

function supabase(url:string,key:string):Backend{
 const sb=createClient(url,key,{auth:{persistSession:false}});
 const bucket=()=>sb.storage.from(T.bucket);
 return {
  async list(){
   const [f,x]=await Promise.all([sb.from(T.folders).select('id,name').order('name'),sb.from(T.files).select(FILE_COLS).order('name')]);
   fail(f.error);fail(x.error);
   return {folders:f.data as Folder[],files:x.data as FileRow[]};
  },
  async file(id){const {data,error}=await sb.from(T.files).select(FILE_COLS).eq('id',id).single();fail(error);return data as FileRow},
  async createFolder(name){fail((await sb.from(T.folders).insert({name:clean(name)})).error)},
  async renameFolder(id,name){fail((await sb.from(T.folders).update({name:clean(name)}).eq('id',id)).error)},
  async deleteFolder(id){fail((await sb.from(T.folders).delete().eq('id',id)).error)},
  async createFile(name,folderId,pdfName,pdf,legend){
   const id=crypto.randomUUID();
   fail((await bucket().upload(id+'.pdf',pdf,{contentType:'application/pdf'})).error);
   const {data,error}=await sb.from(T.files).insert({id,name:clean(name),folder_id:folderId,pdf_name:pdfName,legend}).select(FILE_COLS).single();
   if(error){await bucket().remove([id+'.pdf']);throw Error(error.message)}
   return data as FileRow;
  },
  async renameFile(id,name){fail((await sb.from(T.files).update({name:clean(name)}).eq('id',id)).error)},
  async moveFile(id,folderId){fail((await sb.from(T.files).update({folder_id:folderId}).eq('id',id)).error)},
  async deleteFile(id){fail((await sb.from(T.files).delete().eq('id',id)).error);await bucket().remove([id+'.pdf'])}, // marcas saem em cascata
  async saveLegend(id,legend){fail((await sb.from(T.files).update({legend}).eq('id',id)).error)},
  async pdf(id){const {data,error}=await bucket().download(id+'.pdf');fail(error);return new Uint8Array(await data!.arrayBuffer())},
  async marks(fileId){
   const all:Mark[]=[];
   for(let from=0;;from+=1000){ // o Supabase devolve no máximo 1000 linhas por consulta
    const {data,error}=await sb.from(T.marks).select('id,file_id,page,color,points').eq('file_id',fileId).order('created_at').order('id').range(from,from+999);
    fail(error);all.push(...(data as Mark[]));
    if(data!.length<1000)return all;
   }
  },
  async addMarks(list){for(const c of chunks(list,500))fail((await sb.from(T.marks).insert(c)).error)},
  async removeMarks(ids){for(const c of chunks(ids,100))fail((await sb.from(T.marks).delete().in('id',c)).error)},
  watch(fileId,w){
   const ch=sb.channel('marcador-file-'+fileId)
    .on('postgres_changes',{event:'INSERT',schema:'public',table:T.marks,filter:'file_id=eq.'+fileId},p=>w.onAdd(p.new as Mark))
    .on('postgres_changes',{event:'DELETE',schema:'public',table:T.marks},p=>w.onDel((p.old as {id:string}).id)) // DELETE não aceita filtro
    .on('postgres_changes',{event:'UPDATE',schema:'public',table:T.files,filter:'id=eq.'+fileId},p=>w.onLegend((p.new as FileRow).legend))
    .subscribe();
   return()=>{void sb.removeChannel(ch)};
  },
  watchList(cb){
   const ch=sb.channel('marcador-library-'+crypto.randomUUID())
    .on('postgres_changes',{event:'*',schema:'public',table:T.folders},cb)
    .on('postgres_changes',{event:'*',schema:'public',table:T.files},cb)
    .subscribe();
   return()=>{void sb.removeChannel(ch)};
  },
 };
}

function memory():Backend{
 let folders:Folder[]=[],files:FileRow[]=[],marks:Mark[]=[];
 const pdfs=new Map<string,Uint8Array>();
 const sorted=<X extends {name:string}>(a:X[])=>[...a].sort((x,y)=>x.name.localeCompare(y.name));
 return {
  async list(){return {folders:sorted(folders),files:sorted(files)}},
  async file(id){const f=files.find(x=>x.id===id);if(!f)throw Error('Arquivo não encontrado.');return f},
  async createFolder(name){folders.push({id:crypto.randomUUID(),name:clean(name)})},
  async renameFolder(id,name){folders=folders.map(f=>f.id===id?{...f,name:clean(name)}:f)},
  async deleteFolder(id){if(files.some(f=>f.folder_id===id))throw Error('A pasta não está vazia.');folders=folders.filter(f=>f.id!==id)},
  async createFile(name,folderId,pdfName,pdf,legend){
   const f:FileRow={id:crypto.randomUUID(),name:clean(name),folder_id:folderId,pdf_name:pdfName,legend};
   files.push(f);pdfs.set(f.id,pdf);return f;
  },
  async renameFile(id,name){files=files.map(f=>f.id===id?{...f,name:clean(name)}:f)},
  async moveFile(id,folderId){files=files.map(f=>f.id===id?{...f,folder_id:folderId}:f)},
  async deleteFile(id){files=files.filter(f=>f.id!==id);marks=marks.filter(m=>m.file_id!==id);pdfs.delete(id)},
  async saveLegend(id,legend){files=files.map(f=>f.id===id?{...f,legend}:f)},
  async pdf(id){return pdfs.get(id)!.slice(0)},
  async marks(fileId){return marks.filter(m=>m.file_id===fileId)},
  async addMarks(list){marks.push(...list)},
  async removeMarks(ids){const gone=new Set(ids);marks=marks.filter(m=>!gone.has(m.id))},
  watch:()=>()=>{},
  watchList:()=>()=>{},
 };
}

// Senha da equipe fixa no código, a pedido. Ela só esconde a tela: quem lê o HTML vê a senha e a chave pública do
// Supabase, e a chave é o que de fato dá acesso aos dados (ver o aviso nas migrations).
const PASSWORD='007';
const SB_URL=import.meta.env.VITE_SUPABASE_URL as string|undefined;
const SB_KEY=import.meta.env.VITE_SUPABASE_ANON_KEY as string|undefined;
const OK='marcador:ok'; // lembra o login só nesta aba

// `backend` é trocado no login (binding exportado: quem importa vê o valor atual).
// Sem URL/chave embutidas no build cai no modo de teste em memória.
export let backend:Backend=memory();
export let demo=true;
const open=()=>{if(SB_URL&&SB_KEY){backend=supabase(SB_URL,SB_KEY);demo=false}else{backend=memory();demo=true}};

export const session={
 restore():boolean{if(sessionStorage.getItem(OK)!=='1')return false;open();return true},
 async login(password:string){
  if(password!==PASSWORD)throw Error('Senha incorreta.');
  sessionStorage.setItem(OK,'1');open();
 },
 logout(){sessionStorage.removeItem(OK);backend=memory();demo=true},
};
