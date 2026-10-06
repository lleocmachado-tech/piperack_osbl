import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);let chromium;
try{({chromium}=require('playwright'))}catch{({chromium}=require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')))}
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');const out=path.join(root,'reports/qa');fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1600,height:1000}});const page=await context.newPage();const problems=[];const stats={};
page.on('pageerror',e=>problems.push(e.message));
try{
 const started=performance.now();await page.goto('http://127.0.0.1:8765',{waitUntil:'networkidle'});await page.waitForSelector('canvas');await page.locator('.canvas-status[data-ready="true"]').waitFor({timeout:120000});stats.navigation_complete_pdf_ms=performance.now()-started;
 await page.screenshot({path:path.join(out,'aplicacao-desktop.png'),fullPage:true});
 await page.getByRole('button',{name:'Gestão e revisão',exact:true}).click();await page.getByRole('textbox',{name:'Buscar código ou prefixo'}).fill('212-F');await page.getByRole('button',{name:/212-F · VIGA/}).click();await page.getByRole('button',{name:'Revisar código / quantidade / peso'}).click();await page.getByLabel('Quantidade prevista (vazio = desconhecida)').fill('9');await page.screenshot({path:path.join(out,'revisao-catalogo.png'),fullPage:true});await page.getByRole('button',{name:'Cancelar',exact:true}).click();await page.getByRole('button',{name:'← Voltar à montagem',exact:true}).click();
 await page.setViewportSize({width:375,height:900});await page.screenshot({path:path.join(out,'aplicacao-mobile.png'),fullPage:true});stats.app_mobile_overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 for(const name of ['diagnostico-combio','avanco-inicial-combio']){
  const local=pathToFileURL(path.join(root,'reports',name+'.html')).href;await page.goto(local,{waitUntil:'load'});await page.evaluate(()=>document.fonts.ready);
  stats[name]={mobile_overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),fonts:await page.evaluate(()=>({title:document.fonts.check('700 24px Kodchasan'),body:document.fonts.check('400 14px "Open Sans"')}))};
  await page.screenshot({path:path.join(out,name+'-mobile.png'),fullPage:false});
  await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:path.join(out,name+'-desktop.png'),fullPage:false});
  await page.emulateMedia({media:'print'});await page.pdf({path:path.join(out,name+'-a4.pdf'),format:'A4',printBackground:true,preferCSSPageSize:true});
  const printStyles=await page.evaluate(()=>({header:getComputedStyle(document.querySelector('header')).position,controls:getComputedStyle(document.querySelector('.controls')).display,rows:getComputedStyle(document.querySelector('tbody tr')).breakInside}));stats[name].print_styles=printStyles;
  await context.setOffline(true);await page.reload({waitUntil:'load'});stats[name].offline_fonts=await page.evaluate(async()=>{await document.fonts.ready;return document.fonts.check('700 24px Kodchasan')&&document.fonts.check('400 14px "Open Sans"')});
  await context.setOffline(false);await page.emulateMedia({media:'screen'});await page.setViewportSize({width:375,height:900});
 }
 stats.page_errors=problems;fs.writeFileSync(path.join(out,'browser-validation.json'),JSON.stringify(stats,null,2));
 if(problems.length||stats.app_mobile_overflow||Object.entries(stats).some(([k,v])=>k.includes('combio')&&(v.mobile_overflow||!v.offline_fonts)))throw Error('Falha em verificação visual/funcional: '+JSON.stringify(stats));
 console.log(JSON.stringify(stats,null,2));
}finally{await browser.close()}
