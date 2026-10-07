import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync,existsSync} from 'node:fs';
import {getDocument,OPS} from 'pdfjs-dist/legacy/build/pdf.mjs';
import {extractPieces,pieceAt,piecesIn,inPoly} from '../src/pieces.ts';

const dir=['../Desenhos/','public/dev/'].find(d=>existsSync(d)&&readdirSync(d).some(f=>/^677-.*\.pdf$/.test(f)));
const files=dir?readdirSync(dir).filter(f=>/^677-.*\.pdf$/.test(f)).sort():[];
const skip=!files.length&&'PDFs de obra não disponíveis';

async function pieces(f){
 const doc=await getDocument({data:new Uint8Array(readFileSync(dir+f)),verbosity:0}).promise;
 const page=await doc.getPage(1);
 return extractPieces(page,await doc.getOptionalContentConfig(),OPS);
}

test('todos os desenhos têm peças detectadas, sem peça do tamanho da folha',{skip,timeout:120000},async()=>{
 for(const f of files){
  const ps=await pieces(f);
  assert.ok(ps.length>=5,`${f}: só ${ps.length} peças`);
  const big=Math.max(...ps.map(p=>p.area));
  assert.ok(big<2383*1683*.05,`${f}: peça gigante (${Math.round(big)} pt²), provável vazamento de outra camada`);
  console.log(f,ps.length,'peças; maior',Math.round(big),'pt²');
 }
});

test('clique escolhe a menor peça; caixa inteira x caixa que toca',{skip,timeout:60000},async()=>{
 const ps=await pieces(files.includes('677-206M.pdf')?'677-206M.pdf':files[0]);
 const p=ps[0],c=[(p.bbox[0]+p.bbox[2])/2,(p.bbox[1]+p.bbox[3])/2];
 if(inPoly(p.poly,c))assert.ok(pieceAt(ps,c).area<=p.area);
 const all=piecesIn(ps,[0,0,1e5,1e5],true);assert.equal(all.length,ps.length);
 const tiny=[p.bbox[0]+1,p.bbox[1]+1,p.bbox[0]+2,p.bbox[1]+2];
 assert.equal(piecesIn(ps,tiny,true).length,0);
 assert.ok(piecesIn(ps,tiny,false).includes(p));
});
