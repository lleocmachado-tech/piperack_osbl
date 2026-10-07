// Desenha as peças pintadas por cima do PDF original, em vetor; as pranchas não são alteradas.
// Se houver legenda, entra como uma página A4 extra no fim.
import {PDFDocument,StandardFonts,rgb} from 'pdf-lib';
import type {Legend,Mark} from './store';

const color=(hex:string)=>rgb(...([1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255) as [number,number,number]));
const ascii=(s:string)=>s.replace(/[^\x20-\xFF]/g,'?'); // a fonte padrão do PDF só tem Latin-1

export async function exportPdf(bytes:Uint8Array,list:Mark[],legend:Legend=[],title=''):Promise<Uint8Array>{
 const doc=await PDFDocument.load(bytes,{ignoreEncryption:true});
 const pages=doc.getPages();
 for(const s of list){
  const page=pages[s.page-1];if(!page||s.points.length<3)continue;
  const c=color(s.color);
  // drawSvgPath usa y para baixo a partir de (x,y): com y=0, passar -Y devolve Y no espaço do PDF.
  const d=s.points.map(([x,y],i)=>`${i?'L':'M'}${x},${-y}`).join(' ')+' Z';
  page.drawSvgPath(d,{x:0,y:0,color:c,opacity:.4,borderColor:c,borderWidth:.5,borderOpacity:.8});
 }
 const named=legend.filter(l=>l.label.trim());
 if(named.length){
  const page=doc.addPage([595.28,841.89]),font=await doc.embedFont(StandardFonts.Helvetica),bold=await doc.embedFont(StandardFonts.HelveticaBold);
  page.drawText('Legenda',{x:40,y:790,size:20,font:bold});
  if(title)page.drawText(ascii(title),{x:40,y:768,size:10,font,color:rgb(.4,.4,.4)});
  named.slice(0,40).forEach((l,i)=>{
   const y=730-i*28;
   page.drawRectangle({x:40,y,width:28,height:16,color:color(l.color),opacity:.4,borderColor:color(l.color),borderWidth:1});
   page.drawText(ascii(l.label.trim()).slice(0,80),{x:80,y:y+3,size:12,font});
  });
 }
 return doc.save();
}
