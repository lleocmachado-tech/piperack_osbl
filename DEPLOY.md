# Publicação da interface no Netlify

Este repositório contém a interface React, a API Python e o worker. **A interface no Netlify precisa de uma API online para abrir os desenhos e salvar as marcações.** Desenhos, relatórios, medições e banco local não são enviados ao repositório público.

## 1. Hospedar o servidor do app

Use um servidor com Python 3.12+, armazenamento persistente e HTTPS. Na raiz do repositório:

```sh
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Inicie `python tools/run.py worker` como um segundo processo permanente, no mesmo ambiente e com o mesmo armazenamento da API. A hospedagem deve encaminhar HTTPS para a porta do servidor. Se o provedor fornecer uma porta dinâmica, use-a no lugar de `8000`.

Configure no servidor:

| Variável | Uso |
| --- | --- |
| `PIPERACK_DATA` | Caminho de um volume persistente, por exemplo `/var/lib/piperack`. Guarda SQLite, PDFs originais e cache. |
| `PIPERACK_USERS` | JSON de usuários e tokens; obrigatório para operação online autenticada. Guarde como segredo da hospedagem. |
| `DATABASE_URL` | Opcional: PostgreSQL. Se omitida, usa SQLite no volume persistente. |

Estrutura de `PIPERACK_USERS` (substitua o marcador por um token forte, gerado fora do repositório):

```json
{"<TOKEN_FORTE>":{"name":"responsavel","role":"reviewer","projects":"*"}}
```

API e worker precisam acessar os mesmos originais mesmo quando se usa PostgreSQL. Não use disco temporário para `PIPERACK_DATA`.

Para transferir o projeto existente, exporte um backup JSON no app local e restaure-o no servidor autenticado. Também é possível criar um projeto e importar os PDFs pela interface. Essa transferência ocorre entre você e o servidor, sem publicar os documentos no GitHub.

Verifique `https://SEU-SERVIDOR/api/health`: deve retornar `status: ok` e `multiuser: true`. OCR é opcional e requer também Node, as dependências de `tools/package.json` e o modelo descrito no README.

## 2. Conectar o GitHub ao Netlify

Importe o repositório `lleocmachado-tech/piperack_osbl` e selecione a branch `main`. O arquivo `netlify.toml` já define:

| Campo | Valor |
| --- | --- |
| Base directory | `frontend` |
| Build command | `npm run build:netlify` |
| Publish directory | `frontend/dist` a partir da raiz, ou `dist` relativo à base |
| Node | `22` |

Em **Environment variables**, crie `API_ORIGIN` no escopo de build com a origem HTTPS da API, por exemplo `https://api.sua-obra.com`, sem `/api` no final. Depois execute o deploy.

O build gera as regras de proxy `/api/*` antes da regra da aplicação React. O navegador acessa tudo no domínio do Netlify, incluindo PDFs e exportações. Tokens não são incluídos no build; cada usuário entra em **Gestão e revisão → Acesso** e informa seu token de sessão.

Sem `API_ORIGIN`, o build específico do Netlify termina com uma instrução de configuração. O comando local `npm run build` continua funcionando sem essa variável.

## 3. Conferir a publicação

Abra o site e teste login, carregamento de uma prancha, zoom, marcação, atualização da montagem e reabertura. Confira também uma exportação com os desenhos reais. Uploads e exportações passam pelo proxy do Netlify e precisam caber nos limites de tempo e tamanho da hospedagem; operações maiores podem exigir acesso direto à API ou uma adaptação do fluxo.

Fontes oficiais usadas para a configuração: [netlify.toml](https://docs.netlify.com/build/configure-builds/file-based-configuration/) e [rewrites e proxies](https://docs.netlify.com/manage/routing/redirects/rewrites-proxies/).
