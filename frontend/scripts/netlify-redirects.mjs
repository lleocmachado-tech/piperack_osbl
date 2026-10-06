import {writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';

export function netlifyRedirects(value) {
  if (!value?.trim()) throw new Error('Configure API_ORIGIN no Netlify com a URL HTTPS do servidor Python. Veja DEPLOY.md.');
  const url = new URL(value.trim());
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('API_ORIGIN deve ser uma origem HTTPS, sem /api, caminho, credenciais ou parâmetros.');
  }
  if (['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) throw new Error('API_ORIGIN precisa apontar para o servidor online, não para localhost.');
  return `/api/* ${url.origin}/api/:splat 200!\n/* /index.html 200\n`;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  // Validate before generating routes, so a deployment cannot silently turn API calls into HTML.
  writeFileSync(new URL('../dist/_redirects', import.meta.url), netlifyRedirects(process.env.API_ORIGIN));
  console.log('Rotas Netlify geradas: API externa + aplicação React.');
}
