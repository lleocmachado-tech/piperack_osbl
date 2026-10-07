# Marcador de avanço em PDF

Guarde desenhos PDF online, pinte as peças para marcar o avanço e veja as marcas dos colegas ao vivo. Baixe o PDF com as peças coloridas por cima.

## Como usa

- **Entrar:** senha única da equipe (007).
- **Arquivos e pastas:** cada desenho é um **arquivo com nome**. Dá para criar **pastas** (ex.: `TR01` com 3 desenhos dentro) e mover os arquivos entre elas. **+ Novo arquivo** pede o PDF, o nome e a pasta.
- **Ao vivo:** cada peça pintada é salva na hora e aparece para os outros em segundos. **🔗 Copiar link** copia o endereço do arquivo (quem tiver a senha abre direto nele).
- **Só peça é pintada, o fundo nunca.** O app lê a camada **"Peça"** do PDF (os desenhos do Tekla têm essa camada) e só o interior das próprias peças pode receber cor. Cotas, textos, grelha, parafusos e o vão entre peças não são pintáveis.
- **Pintar peça**: clique numa peça, ou arraste por cima de várias. O contorno tracejado mostra qual será pintada.
- **Selecionar área**: arraste uma caixa. Da esquerda para a direita pinta só as peças inteiras dentro dela; da direita para a esquerda pinta também as que a caixa toca.
- **Apagar** e **Desfazer** (`Ctrl+Z` desfaz o último gesto). **Mover** rola a página sem pintar.
- **Cor livre + legenda:** escolha a cor no seletor **Cor**. **Legenda** → **+ Adicionar a cor atual** cria a entrada e você escreve o significado (ex.: "Montado"). A legenda é de cada arquivo (um arquivo novo herda a do último arquivo da mesma pasta) e sai numa página extra no fim do PDF baixado (só as cores com nome; a fonte do PDF aceita acentos, mas não símbolos como ✓).
- **Baixar PDF colorido**: gera `<nome>-avanco.pdf` no navegador, em vetor.

### Limites conhecidos
- Precisa da camada "Peça". Um PDF sem ela abre, mas avisa que não há o que pintar.
- A peça é a área fechada pelas próprias linhas. Peças só com linhas abertas (como as colunas do 677-213M) só são detectadas quando o grupo é simples; partes com linhas muito finas ou muito grossas podem não ter área pintável.
- A senha esconde o app, mas não fecha o banco: quem tiver a chave pública do Supabase consegue ler e escrever nas tabelas `marcador_*`. Aqui a senha fica no próprio HTML, então protege ainda menos que nos outros apps da Interface OSBL, que a conferem num servidor.

## Backend: projeto Supabase da Interface OSBL

Usa o Supabase único da Interface OSBL, com tabelas e bucket prefixados `marcador` para não colidir com os outros apps:

| Objeto | Para que serve |
| --- | --- |
| `marcador_folders` | pastas |
| `marcador_files` | um desenho por linha: nome, pasta, nome do PDF e legenda |
| `marcador_marks` | cada peça pintada (polígono em pontos do PDF + cor) |
| bucket `marcador-pdfs` | o PDF de cada arquivo (`{id}.pdf`), privado |

As migrations estão em `Interface-OSBL/supabase/migrations/`:
`20261007150000_create_marcador_tables.sql` e `20261007150100_create_marcador_pdfs_bucket.sql`.

As migrations já foram aplicadas no projeto (2026-10-07). Para repetir num projeto novo: rode as duas, na ordem, no **SQL Editor**, e acrescente o conteúdo ao `db/schema_unificado.sql` da Interface (bloco 5), como pede o checklist de lá.

### Senha e chave
A senha da equipe (`007`) está fixa em `src/store.ts` (constante `PASSWORD`), a pedido. A URL e a chave pública do Supabase entram no HTML **na hora do build**, a partir do `.env` (copie o `.env.example`, que fica fora do Git). Quem abrir o HTML consegue ver a senha e a chave, e é a chave que dá acesso às tabelas `marcador_*`: a senha só esconde a tela.

### Modo de teste
Sem `VITE_SUPABASE_URL` e `VITE_SUPABASE_ANON_KEY` no build, o app entra em **modo de teste**: guarda tudo só na memória, sem gravar nada no Supabase, com um aviso amarelo.

## Rodar e testar

```sh
npm install
cp .env.example .env   # e preencha URL e chave; sem isso, modo de teste
npm run dev            # http://127.0.0.1:5173
npm test               # detecção de peças nos PDFs da obra e exportação
npm run build          # gera dist/index.html (arquivo único, abre com duplo clique)
```

Depois do build, `dist/index.html` funciona aberto do disco. O projeto mantém uma cópia na raiz, `Marcador.html` (fora do Git).

### Publicar no Netlify
O `netlify.toml` da **raiz do repositório** já aponta para esta pasta (`base = "marcador-pdf"`, build `npm run build`, publicação em `dist`), e vale mais que a tela do Netlify. Só falta cadastrar, em *Site configuration → Environment variables*, `VITE_SUPABASE_URL` e `VITE_SUPABASE_ANON_KEY` (os mesmos do `.env`): o build precisa deles, e sem eles o site abre em modo de teste (memória, nada é gravado).

## Estrutura

- `src/main.tsx`: login e rotas (`#/p/<pasta>`, `#/f/<arquivo>`)
- `src/Library.tsx`: arquivos e pastas
- `src/Editor.tsx`: PDF, pintura, legenda e salvamento ao vivo
- `src/pieces.ts`: acha as peças na camada "Peça" (linhas → áreas fechadas → polígonos)
- `src/export.ts`: desenha as marcas e a legenda no PDF com `pdf-lib`
- `src/store.ts`: senha, Supabase (projeto da Interface OSBL) ou modo de teste em memória
