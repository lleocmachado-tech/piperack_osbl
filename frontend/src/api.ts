export type Row={id:string;version:number;data:any;[key:string]:any};
export type State={project:Row;[key:string]:any};
export const key=()=>crypto.randomUUID();
export function token(){return sessionStorage.getItem('combio-token')||'';}
export async function api(path:string,options:RequestInit={}){
 const headers:any={...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...(token()?{Authorization:`Bearer ${token()}`}:{})};
 const response=await fetch('/api'+path,{...options,headers:{...headers,...options.headers}});
 if(!response.ok){let error;try{error=await response.json()}catch{error={detail:response.statusText}}throw Error(error.detail||'Erro na operação');}
 return response.status===204?null:response.json();
}
export async function download(path:string,name:string){const r=await fetch('/api'+path,{headers:token()?{Authorization:`Bearer ${token()}`}:{}});if(!r.ok)throw Error((await r.json()).detail);const u=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),10000);}
