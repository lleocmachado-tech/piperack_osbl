// Acha as peças no PDF. O desenho vem do Tekla com uma camada "Peça" e cada bloco dessa camada é uma peça
// (o mesmo código aparece em várias vistas). Só o que está nessa camada pode ser pintado: fundo, cotas,
// textos, grelha e parafusos ficam de fora. A área de cada peça é o interior fechado pelas próprias linhas
// dela, não o vão entre peças vizinhas.
export type Pt=[number,number];
export type Piece={poly:Pt[];bbox:[number,number,number,number];area:number};

const flat=(s:string)=>s.normalize('NFD').replace(/[̀-ͯ]/g,'').trim().toLowerCase();
const mul=(m:number[],c:number[])=>[m[0]*c[0]+m[1]*c[2],m[0]*c[1]+m[1]*c[3],m[2]*c[0]+m[3]*c[2],m[2]*c[1]+m[3]*c[3],m[4]*c[0]+m[5]*c[2]+c[4],m[4]*c[1]+m[5]*c[3]+c[5]];
const bboxOf=(pts:Pt[]):[number,number,number,number]=>{let a=1/0,b=1/0,c=-1/0,d=-1/0;for(const [x,y] of pts){if(x<a)a=x;if(x>c)c=x;if(y<b)b=y;if(y>d)d=y}return [a,b,c,d]};
const areaOf=(h:Pt[])=>Math.abs(h.reduce((s,[x,y],i)=>{const [a,b]=h[(i+1)%h.length];return s+x*b-a*y},0))/2;

function hullOf(points:Pt[]):Pt[]{ // envoltória convexa (monotone chain)
 const p=[...points].sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
 if(p.length<3)return p;
 const cross=(o:Pt,a:Pt,b:Pt)=>(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]);
 const half=(src:Pt[])=>{const h:Pt[]=[];for(const q of src){while(h.length>=2&&cross(h[h.length-2],h[h.length-1],q)<=0)h.pop();h.push(q)}h.pop();return h};
 return half(p).concat(half([...p].reverse()));
}

// Contorno externo exato de uma região de pixels (segue as arestas, região sempre à direita).
function outline(inR:(x:number,y:number)=>boolean,x0:number,y0:number):Pt[]{
 const DX=[1,0,-1,0],DY=[0,1,0,-1]; // E,S,W,N
 const pts:Pt[]=[[x0,y0]];let vx=x0,vy=y0,d=0;
 for(;;){
  const [l,r]=[[inR(vx,vy-1),inR(vx,vy)],[inR(vx,vy),inR(vx-1,vy)],[inR(vx-1,vy),inR(vx-1,vy-1)],[inR(vx-1,vy-1),inR(vx,vy-1)]][d];
  const nd=l?(d+3)%4:r?d:(d+1)%4;
  if(nd!==d)pts.push([vx,vy]);
  d=nd;vx+=DX[d];vy+=DY[d];
  if(vx===x0&&vy===y0&&d===3)return pts;
 }
}
// Douglas-Peucker em polígono fechado: divide no ponto mais distante do primeiro.
export function simplify(pts:Pt[],eps:number):Pt[]{
 if(pts.length<4)return pts;
 const dist=(p:Pt,a:Pt,b:Pt)=>{const dx=b[0]-a[0],dy=b[1]-a[1],l=dx*dx+dy*dy;
  const t=l?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/l)):0;
  return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)};
 const rec=(s:Pt[],a:number,b:number,out:Pt[])=>{
  let max=0,at=-1;for(let i=a+1;i<b;i++){const v=dist(s[i],s[a],s[b]);if(v>max){max=v;at=i}}
  if(max>eps){rec(s,a,at,out);out.push(s[at]);rec(s,at,b,out)}
 };
 let far=1,fd=0;for(let i=1;i<pts.length;i++){const v=Math.hypot(pts[i][0]-pts[0][0],pts[i][1]-pts[0][1]);if(v>fd){fd=v;far=i}}
 const out:Pt[]=[pts[0]],back=pts.slice(far).concat([pts[0]]);
 rec(pts,0,far,out);out.push(pts[far]);rec(back,0,back.length-1,out);
 return out;
}

// Interiores fechados pelas linhas de um grupo de polilinhas: rasteriza só esse recorte (linhas de 3 px),
// rotula as regiões livres e descarta a que encosta na borda (o fundo). Devolve polígonos em coordenadas do PDF.
function facesOf(lines:Pt[][],bb:[number,number,number,number]):Pt[][]{
 const PAD=4,w=bb[2]-bb[0],h=bb[3]-bb[1];
 const s=Math.min(8,Math.sqrt(1.5e6/Math.max(w*h,1)),3000/Math.max(w,h,1e-6)); // 8 px/pt no máximo: orçamento de ~1,5 M pixels por grupo
 const W=Math.ceil(w*s)+2*PAD+1,H=Math.ceil(h*s)+2*PAD+1,mask=new Uint8Array(W*H);
 const px=(x:number)=>Math.round((x-bb[0])*s)+PAD,py=(y:number)=>Math.round((bb[3]-y)*s)+PAD;
 for(const line of lines)for(let i=1;i<line.length;i++){
  let x0=px(line[i-1][0]),y0=py(line[i-1][1]);const x1=px(line[i][0]),y1=py(line[i][1]);
  const dx=Math.abs(x1-x0),dy=-Math.abs(y1-y0),sx=x0<x1?1:-1,sy=y0<y1?1:-1;let err=dx+dy;
  for(;;){
   for(let a=-1;a<=1;a++)for(let b=-1;b<=1;b++){const X=x0+a,Y=y0+b;if(X>=0&&Y>=0&&X<W&&Y<H)mask[Y*W+X]=1}
   if(x0===x1&&y0===y1)break;
   const e2=2*err;if(e2>=dy){err+=dy;x0+=sx}if(e2<=dx){err+=dx;y0+=sy}
  }
 }
 const label=new Int32Array(W*H),stack=new Int32Array(W*H),out:Pt[][]=[];let id=0;
 for(let start=0;start<W*H;start++){
  if(mask[start]||label[start])continue;
  id++;let sp=0,count=0,border=false;stack[sp++]=start;label[start]=id;
  while(sp){
   const i=stack[--sp],x=i%W,y=(i-x)/W;count++;
   if(x===0||y===0||x===W-1||y===H-1)border=true;
   if(x>0&&!mask[i-1]&&!label[i-1]){label[i-1]=id;stack[sp++]=i-1}
   if(x<W-1&&!mask[i+1]&&!label[i+1]){label[i+1]=id;stack[sp++]=i+1}
   if(y>0&&!mask[i-W]&&!label[i-W]){label[i-W]=id;stack[sp++]=i-W}
   if(y<H-1&&!mask[i+W]&&!label[i+W]){label[i+W]=id;stack[sp++]=i+W}
  }
  if(border||count<12)continue;
  const sx=start%W,sy=(start-sx)/W,me=id;
  const poly=simplify(outline((x,y)=>x>=0&&y>=0&&x<W&&y<H&&label[y*W+x]===me,sx,sy),.8);
  out.push(poly.map(([x,y])=>[bb[0]+(x-PAD)/s,bb[3]-(y-PAD)/s] as Pt));
 }
 return out;
}

// Agrupa polilinhas que se tocam (caixas expandidas 0,5 pt se cruzam) para rasterizar cada grupo separado.
function groups(lines:Pt[][]):Pt[][][]{
 const E=.5,bb=lines.map(l=>bboxOf(l)),order=lines.map((_,i)=>i).sort((a,b)=>bb[a][0]-bb[b][0]);
 const parent=lines.map((_,i)=>i),find=(i:number):number=>parent[i]===i?i:(parent[i]=find(parent[i]));
 for(let a=0;a<order.length;a++)for(let b=a+1;b<order.length;b++){
  const i=order[a],j=order[b];if(bb[j][0]>bb[i][2]+E)break;
  if(bb[j][1]<=bb[i][3]+E&&bb[j][3]>=bb[i][1]-E&&bb[j][2]>=bb[i][0]-E)parent[find(j)]=find(i);
 }
 const by=new Map<number,Pt[][]>();lines.forEach((l,i)=>{const r=find(i);(by.get(r)||by.set(r,[]).get(r)!).push(l)});
 return [...by.values()];
}

// `OPS` é o enum do pdfjs-dist (passado de fora para o mesmo código rodar no navegador e no Node).
export async function extractPieces(page:any,oc:Iterable<[string,{name?:string}]>|null,OPS:any):Promise<Piece[]>{
 const layer=new Map<string,string>();for(const [id,g] of oc||[])layer.set(id,flat(g.name||''));
 const ol=await page.getOperatorList();
 let ctm=[1,0,0,1,0,0];const saved:number[][]=[];
 const marks:number[]=[]; // por bloco aberto: índice do bloco Peça, -1 = outra camada, -2 = conteúdo marcado sem camada
 const blocks:Pt[][][]=[];
 for(let i=0;i<ol.fnArray.length;i++){
  const fn=ol.fnArray[i],a=ol.argsArray[i];
  if(fn===OPS.save)saved.push(ctm);
  else if(fn===OPS.restore)ctm=saved.pop()||ctm;
  else if(fn===OPS.transform)ctm=mul(a,ctm);
  else if(fn===OPS.paintFormXObjectBegin){saved.push(ctm);if(a[0])ctm=mul(a[0],ctm)}
  else if(fn===OPS.paintFormXObjectEnd)ctm=saved.pop()||ctm;
  else if(fn===OPS.beginMarkedContentProps){
   const l=a[0]==='OC'?layer.get(a[1]?.id):undefined;
   if(l==='peca'){blocks.push([]);marks.push(blocks.length-1)}else marks.push(l===undefined?-2:-1);
  }
  else if(fn===OPS.beginMarkedContent)marks.push(-2);
  else if(fn===OPS.endMarkedContent)marks.pop();
  else if(fn===OPS.constructPath&&a[0]!==OPS.endPath){
   let at=-1;for(let k=marks.length-1;k>=0;k--)if(marks[k]!==-2){at=marks[k];break}
   if(at<0)continue;
   // pdf.js 5: a[1][0] = [comando, x, y, ...] com 0=moveTo 1=lineTo 2=curveTo(3 pontos) 3=closePath
   const d=a[1]?.[0];if(!d)continue;
   let line:Pt[]=[];
   const put=(x:number,y:number)=>line.push([ctm[0]*x+ctm[2]*y+ctm[4],ctm[1]*x+ctm[3]*y+ctm[5]]);
   const flush=()=>{if(line.length>1)blocks[at].push(line);line=[]};
   for(let j=0;j<d.length;){const c=d[j++];
    if(c===0){flush();put(d[j],d[j+1]);j+=2}
    else if(c===1){put(d[j],d[j+1]);j+=2}
    else if(c===2){put(d[j],d[j+1]);put(d[j+2],d[j+3]);put(d[j+4],d[j+5]);j+=6}
    else if(c===3){if(line.length)line.push(line[0])}
    else break}
   flush();
  }
 }
 const out:Piece[]=[];
 for(const lines of blocks)for(const g of groups(lines)){
  const all=g.flat(),bb=bboxOf(all);
  if(Math.max(bb[2]-bb[0],bb[3]-bb[1])<.3)continue;
  let polys=facesOf(g,bb).filter(p=>areaOf(p)>=2);
  // peças abertas (duas linhas paralelas sem fechamento) não têm interior fechado: usa a envoltória, só em grupos simples
  if(!polys.length&&g.length<=12){const h=hullOf(all);if(h.length>=3&&areaOf(h)>=2)polys=[h]}
  for(const poly of polys)out.push({poly,area:areaOf(poly),bbox:bboxOf(poly)});
 }
 return out;
}

export function inPoly(poly:Pt[],[x,y]:Pt):boolean{
 let inside=false;
 for(let i=0,j=poly.length-1;i<poly.length;j=i++){
  const [xi,yi]=poly[i],[xj,yj]=poly[j];
  if((yi>y)!==(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)inside=!inside;
 }
 return inside;
}
// Em sobreposição (placa sobre viga) vale a menor, que é a de cima.
export function pieceAt<T extends {poly:Pt[];bbox:number[];area:number}>(pieces:T[],p:Pt):T|undefined{
 let best:T|undefined;
 for(const q of pieces)if(q.bbox[0]<=p[0]&&p[0]<=q.bbox[2]&&q.bbox[1]<=p[1]&&p[1]<=q.bbox[3]&&inPoly(q.poly,p)&&(!best||q.area<best.area))best=q;
 return best;
}
// inside=true: só peças inteiras dentro da caixa; false: também as que a caixa toca.
export function piecesIn(pieces:Piece[],box:[number,number,number,number],inside:boolean):Piece[]{
 return pieces.filter(({bbox:b})=>inside
  ?b[0]>=box[0]&&b[2]<=box[2]&&b[1]>=box[1]&&b[3]<=box[3]
  :b[0]<=box[2]&&b[2]>=box[0]&&b[1]<=box[3]&&b[3]>=box[1]);
}
export const keyOf=(points:Pt[])=>points.map(p=>p[0].toFixed(2)+','+p[1].toFixed(2)).join(';');
