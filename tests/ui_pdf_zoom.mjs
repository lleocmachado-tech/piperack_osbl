import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const blocked=[];
await context.route('**/api/**',route=>{
 if(['GET','HEAD','OPTIONS'].includes(route.request().method()))return route.continue();
 blocked.push(route.request().method()+' '+route.request().url());return route.abort();
});
const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
const report={read_only:true};
async function ready(expected=null){await page.waitForFunction(expected=>{
 const status=document.querySelector('.canvas-status'),surface=document.querySelector('.pdf-surface');
 return status?.getAttribute('data-ready')==='true'&&surface&&(expected===null||Math.abs(Number(surface.dataset.scale)-expected)<.0001);
},expected,{timeout:120000});}
const scale=()=>page.locator('.pdf-surface').evaluate(el=>Number(el.dataset.scale));
async function fit(){await page.getByRole('button',{name:'Ajustar à tela',exact:true}).click();await page.waitForFunction(()=>{
 const surface=document.querySelector('.pdf-surface'),scroll=document.querySelector('.pdf-scroll');
 return document.querySelector('.canvas-status')?.getAttribute('data-ready')==='true'&&surface.getBoundingClientRect().width<=scroll.clientWidth&&surface.getBoundingClientRect().height<=scroll.clientHeight;
});}
try{
 await page.goto('http://127.0.0.1:8765',{waitUntil:'networkidle'});await ready();
 report.initial_pdf_width=await page.locator('.pdf-surface').evaluate(el=>el.getBoundingClientRect().width);
 report.initial_viewer_width=await page.locator('.field-drawing').evaluate(el=>el.getBoundingClientRect().width);
 report.header_height=await page.locator('.drawing-header').evaluate(el=>el.getBoundingClientRect().height);
 report.pdf_top=await page.locator('.pdf-scroll').evaluate(el=>el.getBoundingClientRect().top);
 report.pdf_visible_height=await page.locator('.pdf-scroll').evaluate(el=>el.getBoundingClientRect().height);
 if(report.initial_viewer_width<1400||report.initial_pdf_width<1300)throw Error('O desenho não está usando a largura disponível.');
 if(await page.locator('.field-panel').count())throw Error('Painel deveria iniciar recolhido.');
 await page.screenshot({path:'reports/qa/pdf-zoom-area-ampliada.png',fullPage:true});
 await page.getByRole('button',{name:'Gestão e revisão',exact:true}).click();
 report.management_card_heights=await page.locator('.app-kpis>div').evaluateAll(elements=>elements.map(el=>el.getBoundingClientRect().height));
 await page.screenshot({path:'reports/qa/indicadores-compactos.png',fullPage:true});
 await page.getByRole('button',{name:'← Voltar à montagem',exact:true}).click();await ready();
 let before=await scale();await page.getByRole('button',{name:'Aumentar zoom',exact:true}).click();await ready(Math.min(2,Math.round(before*1.25*1000)/1000));
 const increased=await scale();if(increased<=before)throw Error('Zoom + não aumentou o PDF.');
 await page.getByRole('button',{name:'Diminuir zoom',exact:true}).click();await ready(Math.max(.1,Math.round(increased/1.25*1000)/1000));
 if(await scale()>=increased)throw Error('Zoom − não diminuiu o PDF.');
 report.zoom_buttons=true;
 await page.getByRole('combobox',{name:'Zoom',exact:true}).selectOption('0.75');await ready(.75);
 await page.locator('.pdf-scroll').evaluate(el=>{el.scrollLeft=350;el.scrollTop=450;});
 const center=()=>page.locator('.pdf-scroll').evaluate(el=>{const surface=el.querySelector('.pdf-surface'),a=el.getBoundingClientRect(),b=surface.getBoundingClientRect(),scale=Number(surface.dataset.scale);return [(a.left+el.clientLeft+el.clientWidth/2-b.left)/scale,(a.top+el.clientTop+el.clientHeight/2-b.top)/scale];});
 const oldCenter=await center();await page.getByRole('button',{name:'Aumentar zoom',exact:true}).click();await ready(.938);
 const newCenter=await center();report.center_drift_pdf_points=Math.max(...oldCenter.map((v,i)=>Math.abs(v-newCenter[i])));
 if(report.center_drift_pdf_points>2)throw Error('Zoom perdeu a região que estava no centro.');
 await fit();report.fit_page=true;
 await page.getByRole('button',{name:'Peças',exact:true}).click();await page.locator('.field-panel').waitFor();
 await page.getByRole('button',{name:'Fechar painel ×',exact:true}).click();await page.locator('.field-panel').waitFor({state:'hidden'});
 report.panel_toggle=true;
 await page.getByRole('button',{name:'Ampliar desenho',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.field-workspace')?.getBoundingClientRect().top===0);
 await fit();
 report.expanded_height=await page.locator('.field-drawing').evaluate(el=>el.getBoundingClientRect().height);
 if(report.expanded_height<975)throw Error('Modo ampliado não ocupa a janela.');
 await page.screenshot({path:'reports/qa/pdf-zoom-tela-ampliada.png',fullPage:true});
 await page.keyboard.press('Escape');await page.locator('.field-workspace.is-expanded').waitFor({state:'hidden'});
 report.escape_restores_view=true;
 await page.getByRole('button',{name:'Marcar área',exact:true}).click();await ready();
 const b=await page.locator('.pdf-overlay').boundingBox();await page.mouse.move(b.x+100,b.y+100);await page.mouse.down();await page.mouse.move(b.x+170,b.y+125,{steps:5});await page.mouse.up();
 await page.getByRole('button',{name:'Continuar →',exact:true}).click();await page.getByRole('dialog',{name:'Registrar peça no desenho'}).waitFor();await page.getByRole('button',{name:'Cancelar',exact:true}).click();
 report.mark_draft_still_works=true;
 await page.getByRole('button',{name:'Selecionar',exact:true}).click();
 await page.setViewportSize({width:390,height:844});await fit();
 report.mobile_overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 for(const name of ['Aumentar zoom','Diminuir zoom','Ajustar à tela','Ampliar desenho'])if(!await page.getByRole('button',{name,exact:true}).isVisible())throw Error('Controle indisponível no celular: '+name);
 await page.screenshot({path:'reports/qa/pdf-zoom-mobile.png',fullPage:true});
 report.page_errors=errors;report.blocked_writes=blocked;
 if(errors.length||blocked.length||report.mobile_overflow)throw Error(JSON.stringify(report));
 fs.writeFileSync('reports/qa/pdf-zoom-validation.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
}catch(error){await page.screenshot({path:'reports/qa/pdf-zoom-falha.png',fullPage:true});throw error}finally{await browser.close()}
