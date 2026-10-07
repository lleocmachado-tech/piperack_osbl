import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {PDFDocument} from 'pdf-lib';
import {exportPdf} from '../src/export.ts';

const src=['../Desenhos/677-206M.pdf','public/dev/677-206M.pdf'].find(existsSync);
const poly=(x,y,color='#2e7d32')=>({id:'a'+x,pdf:'x.pdf',page:1,color,points:[[x,y],[x+100,y],[x+100,y+50],[x,y+50]]});

test('exporta as peças pintadas sobre o PDF e acrescenta a página de legenda',{skip:!src&&'PDF de obra não disponível'},async()=>{
 const bytes=readFileSync(src);
 const legend=[{color:'#2e7d32',label:'Montado — ok ✓'},{color:'#ff0000',label:''}];
 const out=await exportPdf(bytes,[poly(300,300),poly(600,300,'#ff0000')],legend,'677-206M.pdf');
 const a=await PDFDocument.load(bytes),b=await PDFDocument.load(out);
 assert.equal(b.getPageCount(),a.getPageCount()+1,'legenda vira uma página extra');
 assert.ok(out.length>bytes.length,'o PDF exportado deve conter as marcas');
 if(process.env.EXPORT_OUT)writeFileSync(process.env.EXPORT_OUT,out);
});

test('sem legenda com nome, não acrescenta página',{skip:!src&&'PDF de obra não disponível'},async()=>{
 const bytes=readFileSync(src);
 const out=await exportPdf(bytes,[poly(300,300)],[{color:'#2e7d32',label:'  '}]);
 assert.equal((await PDFDocument.load(out)).getPageCount(),(await PDFDocument.load(bytes)).getPageCount());
});
