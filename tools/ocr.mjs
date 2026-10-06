import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const require=createRequire(import.meta.url);
let tesseract;
try{tesseract=require('tesseract.js')}catch{tesseract=require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/tesseract.js'))}
const [inputPath,outputPath]=process.argv.slice(2);const config=JSON.parse(fs.readFileSync(inputPath,'utf8'));
const worker=await tesseract.createWorker('eng',1,{cachePath:config.cache_path,logger:()=>{}});
const results=[];
try{
 for(const sample of config.samples){
  await worker.setParameters({tessedit_pageseg_mode:String(sample.psm??11),preserve_interword_spaces:'1'});
  const started=performance.now();const {data}=await worker.recognize(sample.image,{}, {text:true,blocks:true});
  const words=(data.blocks||[]).flatMap(b=>(b.paragraphs||[]).flatMap(p=>(p.lines||[]).flatMap(l=>l.words||[]))).map(w=>({text:w.text,confidence:w.confidence,box:w.bbox}));
  results.push({id:sample.id,psm:sample.psm??11,text:data.text,confidence:data.confidence,words,seconds:(performance.now()-started)/1000,rss_mb:process.memoryUsage().rss/1024**2,engine:'tesseract.js-7-eng-OEM1'});
 }
 fs.writeFileSync(outputPath,JSON.stringify(results,null,2));
}finally{await worker.terminate()}
