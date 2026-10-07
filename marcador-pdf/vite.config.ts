import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {viteSingleFile} from 'vite-plugin-singlefile';
// Gera um único dist/index.html (JS, CSS e worker do PDF.js embutidos): abre com duplo clique, sem servidor.
export default defineConfig({plugins:[react(),viteSingleFile()],build:{outDir:'dist'}});
