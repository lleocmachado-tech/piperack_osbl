# PipeRack OSBL · montagem em campo

Aplicação para marcar peças sobre desenhos PDF e registrar o avanço físico da montagem. A tela principal prioriza o desenho, com zoom, área ampliada e controles compactos.

- Marcação por retângulo ou contorno, identificação do código e localização física.
- Cor da etapa concluída e posição sem conclusão registrada.
- Uma unidade em várias vistas sem duplicar a quantidade medida.
- Catálogo revisável, histórico de alterações, correções e exportação dos desenhos coloridos.
- API FastAPI, interface React/TypeScript com PDF.js, worker separado e SQLite local ou PostgreSQL.

## Publicação no Netlify

O arquivo `netlify.toml` configura o build da interface. A API Python precisa ser hospedada separadamente, com armazenamento persistente. Defina `API_ORIGIN` no Netlify com a origem HTTPS dessa API.

Consulte [DEPLOY.md](DEPLOY.md) para configurar o servidor, autenticação, armazenamento e publicação. O build específico do Netlify exige `API_ORIGIN`; o build local funciona sem essa variável.

## Dados da obra

O repositório público contém o código. **Desenhos, relatórios, banco, backups e medições da obra não são distribuídos pelo Git.** Importe seus PDFs em **Gestão e revisão → Importar PDF**, ou restaure um backup pelo aplicativo autenticado. Nada é medido ou aprovado automaticamente ao importar.

## Executar localmente

Requisitos: Python 3.12+ e Node 22.12+.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
```

No Windows, execute `tools/abrir-app.cmd`. Ele inicia a API e o worker em segundo plano e abre `http://127.0.0.1:8765`. O atalho `.lnk` do ambiente original é local e não integra o repositório.

Alternativamente, use dois terminais:

```sh
python tools/run.py api
python tools/run.py worker
```

Ative a `.venv` antes desses comandos, ou use o executável Python dela. Para desenvolvimento da interface, execute `npm --prefix frontend run dev` com a API em execução.

## Registrar montagem

1. Escolha o desenho. Ajuste o zoom usando **− / +**, o percentual ou **Ajustar à tela**.
2. Use **Marcar área** ou **Contornar peça** e clique em **Continuar**.
3. Informe código, posição, estado da montagem, data e referência da verificação em campo. Confirme a quantidade prevista no primeiro registro do código.
4. Salve a marcação. Selecione uma área existente para consultar ou corrigir a montagem.

Ao representar a mesma peça em outra vista, selecione a posição já cadastrada. Quantidades registradas sem localização podem ser alocadas às posições sem aumentar o total. Áreas, identidades e medição são gravadas em uma transação.

**Peças** abre o painel lateral. **Ampliar desenho** ocupa a janela; **Esc** volta à visualização normal. **Gestão e revisão** reúne cadastros, demais etapas, OCR assistido, auditoria e ferramentas técnicas.

## Armazenamento e acesso

- `PIPERACK_DATA`: diretório persistente para SQLite, originais e cache; padrão `data/`.
- `DATABASE_URL`: PostgreSQL opcional. API e worker precisam compartilhar os originais.
- `PIPERACK_USERS`: usuários e tokens da API. Configure antes de disponibilizar o servidor online; veja [DEPLOY.md](DEPLOY.md).

Originais são preservados por hash. Exportações usam um snapshot comum para PDF, relatório, CSV e JSON. O backup JSON incorpora os originais para restauração em um projeto separado.

OCR é opcional: requer Node, `npm --prefix tools install` e o modelo de reconhecimento. O worker mantém candidatos sujeitos a revisão; decisões manuais permanecem protegidas.

## Verificação

```sh
npm --prefix frontend test
npm --prefix frontend run build
python tools/run.py test
```

Parte dos testes de integração e dos scripts de diagnóstico usa os PDFs privados do projeto original em `Desenhos/` e evidências locais em `reports/`. Para executar essa parte da suíte, forneça esses arquivos no ambiente autorizado. Os testes de configuração Netlify e a compilação da interface não dependem deles. A execução de testes PostgreSQL requer `TEST_DATABASE_URL`.

As fontes incorporadas usam as licenças em `assets/licenses/`.
