import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
// This script can only read the live app; all modifying API requests are blocked.
await context.route('**/api/**',route=>['GET','HEAD','OPTIONS'].includes(route.request().method())?route.continue():route.abort());
const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto('http://127.0.0.1:8765',{waitUntil:'networkidle'});
 await page.locator('.canvas-status[data-ready="true"]').waitFor({timeout:120000});
 const count=await page.locator('#field-drawing option').count();if(count!==14)throw Error('Esperadas 14 pranchas originais.');
 await page.screenshot({path:'reports/qa/montagem-campo-projeto-real.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.waitForFunction(()=>document.querySelector('.canvas-status')?.getAttribute('data-ready')==='true'&&document.querySelector('.pdf-surface').getBoundingClientRect().width<=document.querySelector('.pdf-scroll').clientWidth,null,{timeout:120000});
 await page.screenshot({path:'reports/qa/montagem-campo-projeto-real-mobile.png',fullPage:true});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 const result={read_only:true,pages:count,mobile_overflow:overflow,page_errors:errors};
 fs.writeFileSync('reports/qa/montagem-campo-readonly-validation.json',JSON.stringify(result,null,2));
 if(errors.length||overflow)throw Error(JSON.stringify(result));console.log(JSON.stringify(result,null,2));
}finally{await browser.close()}
