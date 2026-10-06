import test from 'node:test';
import assert from 'node:assert/strict';
import {netlifyRedirects} from '../scripts/netlify-redirects.mjs';

test('API proxy precedes the SPA fallback and preserves the /api prefix',()=>{
  assert.equal(netlifyRedirects(' https://api.example.com/ '),'/api/* https://api.example.com/api/:splat 200!\n/* /index.html 200\n');
});

test('an unconfigured deployment fails with the required setting',()=>{
  assert.throws(()=>netlifyRedirects(''),/API_ORIGIN/);
  assert.throws(()=>netlifyRedirects(undefined),/API_ORIGIN/);
});

test('rejects credentials, local addresses, paths and query strings',()=>{
  for(const value of ['http://api.example.com','https://user:secret@api.example.com','https://localhost','https://127.0.0.1','https://[::1]','https://api.example.com/api','https://api.example.com/?key=secret','https://api.example.com/#fragment']) {
    assert.throws(()=>netlifyRedirects(value));
  }
});
