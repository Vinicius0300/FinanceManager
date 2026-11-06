# Finanças: contexto do projeto

Documento vivo e **resumido**: o que o app é, onde o projeto está e as regras que valem hoje. Leia antes de qualquer tarefa e atualize ao tomar decisões novas.

O motivo e o detalhe de cada decisão (dúvidas resolvidas com o dono, medições, validações) ficam em [`HISTORICO.md`](HISTORICO.md), por parte. Ao registrar uma decisão nova: uma linha aqui, o detalhe lá.

| Documento | Para quê |
|---|---|
| [`HISTORICO.md`](HISTORICO.md) | decisões por parte, com motivos, medições e validações |
| [`CALCULOS.md`](CALCULOS.md) | regras de cálculo com exemplos (preço médio, caixa, renda fixa, poupança, histórico) |
| [`TIPOS_DE_ATIVO.md`](TIPOS_DE_ATIVO.md) | registry de tipos de ativo e providers; como criar um tipo novo |
| [`ANALYTICS.md`](ANALYTICS.md) | plano da futura camada de previsão e sugestões |
| [`INSTALACAO.md`](INSTALACAO.md) | guia do usuário: instalar, atualizar e desinstalar o app |
| [`../README.md`](../README.md) | ambiente de desenvolvimento e comandos do dia a dia |

## 1. Visão do produto
App desktop instalável para Windows (ícone e janela próprios, sem navegador nem servidor remoto) para:
- acompanhar a carteira de investimentos (ações BR e US, ETFs, fundos, renda fixa, Tesouro Direto, cripto, poupança) com valores quase em tempo real;
- registrar receitas e despesas mensais (cadastro manual) e mostrar o saldo do mês;
- no futuro, previsão e sugestão de investimentos (só a estrutura em `analytics/`, nada de IA por enquanto).

Uso single-user. Dados 100% locais: sem login, nuvem ou sincronização.
Telas: Dashboard, Carteira, Movimentações, Receitas e Despesas, Glossário, Configurações.

## 2. Roadmap (cada parte validada pelo dono antes da próxima)
| Parte | Conteúdo | Situação |
|---|---|---|
| 1 | Fundação: monorepo, Tauri + React + sidecar FastAPI, `/health` e rota protegida, encerramento limpo, instância única, estado da janela, contrato OpenAPI → TS | **Validada** |
| 2 | Modelos e banco (SQLite + Alembic com backup prévio), registry de tipos de ativo, cálculos com `Decimal`, estrutura de `analytics/` | **Validada** |
| 3 | Providers de cotação em registry, Tesouro Direto, histórico de 1 ano, atualização em segundo plano, API REST completa, backup/restauração, SSE | **Validada** |
| 4 | Frontend funcional com a paleta definitiva: todas as telas, gráficos, SSE, backend do histórico | **Validada** |
| 4.1 | Formulário único de movimentação, deduplicação, listas oficiais de tickers (B3 e NASDAQ), tipos `fundo_listado`, `etf_br`, `etf_us` | **Validada** |
| 5A | Visual final, altas e baixas do dia, próximos vencimentos, chip de status das cotações, sparkline, carteira por instituição | **Entregue (aguardando validação)** |
| 5B | Bloco 2 do code review; empacotamento (PyInstaller + NSIS), script único de build, versão 1.0.0 | Bloco 2 **validado**; empacotamento **entregue (aguardando validação)** |
| 6 | Análises e Proventos: tela Proventos, "Proventos 12 meses", evolução empilhada e modo "%", rentabilidade vs. CDI, comparações em Receitas e Despesas, taxa de poupança, treemap da carteira | A fazer |
| 7 | Glossário: grafo de termos (estilo Obsidian), conteúdo fixo em Markdown, busca, filtro, verbetes com exemplo. Só frontend | **Validada** (61 termos) |

**Versão atual:** 1.0.0 (fonte única: `"version"` do `package.json` da raiz).

## 3. Arquitetura
- **Desktop:** Tauri 2 (WebView2). Rust mínimo: inicialização, ciclo de vida do backend, plugins (dialog, single-instance, window-state).
- **Frontend:** React 18 + TypeScript strict + Vite, Tailwind CSS 4 + shadcn/ui, React Router, TanStack Query/Table v8, Zustand, React Hook Form + Zod 4, ECharts 6, Lightweight Charts 5, date-fns 4.
- **Backend:** Python 3.11+ com FastAPI (uvicorn) como sidecar; SQLite (WAL) + SQLAlchemy 2.0 + Alembic em `%APPDATA%\Financas\financas.db`; pandas para séries; `httpx2` para HTTP; `openpyxl` para Excel.
- **Contrato:** OpenAPI → `docs/openapi.json` → `apps/web/src/api/schema.ts` (`openapi-typescript`) + `openapi-fetch`. Gerados, nunca editados à mão.
- **Monorepo:** npm workspaces (`apps/web`, `apps/desktop`); venv em `backend/.venv` (`pip install -e ".[dev]"`).

### Como o app sobe e desce
1. O Rust (`src-tauri/src/backend.rs`) reserva uma porta livre em `127.0.0.1`, gera um token (32 bytes, hex) e inicia o backend com `FINANCAS_PORTA`, `FINANCAS_TOKEN`, `FINANCAS_PID_PAI` (e `FINANCAS_DEV=1` em dev), por variável de ambiente, nunca por argumento.
2. Consulta `GET /health` a cada 150 ms: até **120 s** na primeira abertura de cada executável e em dev; **30 s** nas seguintes (marca em `logs\backend-pronto.txt` com tamanho e data do executável).
3. O React chama `invoke("conexao_backend")` → `{ urlBase, token }`. Enquanto espera: "Iniciando o serviço interno…"; em erro, mensagem e **Tentar novamente** (`invoke("reiniciar_backend")`).
4. Todas as rotas exigem `Authorization: Bearer <token>`, exceto `/health`.
5. **Encerramento:** `POST /api/sistema/encerrar` (interna, fora do OpenAPI), espera 3 s e força. **Sem órfãos:** Job Object com `KILL_ON_JOB_CLOSE` + watchdog no Python que observa o PID do app.
6. **Instância única** (plugin registrado primeiro) e **estado da janela** (window-state, em `%APPDATA%\br.com.financas.desktop\`).
7. **Dev:** `backend\.venv\Scripts\python.exe entrypoint.py --reload`. **Release:** `financas-backend\financas-backend.exe` (PyInstaller `onedir`) na pasta de instalação (`resource_dir()`); stderr em `%APPDATA%\Financas\logs\backend-stderr.log` (a abertura anterior fica em `backend-stderr.anterior.log`).

### Segurança
- API só em `127.0.0.1`; porta e token por sessão; token comparado com `secrets.compare_digest`.
- CORS: `http://tauri.localhost`; `localhost:5173`/`127.0.0.1:5173` só com `FINANCAS_DEV=1`.
- CSP: `connect-src 'self' ipc: http://ipc.localhost http://127.0.0.1:*`; fontes só `'self' data:`.
- Capabilities (`capabilities/main.json`): só `dialog:allow-open`, `dialog:allow-save` e `core:app:allow-version`. O front não lê nem grava arquivos: passa o caminho e o backend faz o resto. Acrescente permissão só quando uma tela precisar.
- `/docs` (Swagger) só em dev.

## 4. Estrutura
```
apps/desktop/                 CLI do Tauri, icone.svg (fonte dos ícones)
apps/desktop/src-tauri/       lib.rs (plugins/comandos), backend.rs (sidecar), job.rs (Job Object),
                              locais.rs (backend instalado e pasta de dados); tauri.instalador.conf.json
apps/web/src/
  app/                        rotas, layout, barra superior (status das cotações, Atualizar, ocultar valores, tema)
  features/                   uma pasta por tela: dashboard, carteira, movimentacoes, receitas-despesas,
                              configuracoes, glossario; status-backend (portão); tempo-real (SSE)
  components/                 compartilhados (CartaoMetrica, TabelaDados, Estados, ValorFinanceiro,
                              Segmentos, graficos/...); ui/ (shadcn)
  api/schema.ts               GERADO (não editar)
  lib/                        api, decimal (BigInt), formatacao, datas, formularios, fatias, eventos (SSE)
  theme/                      tokens (index.css), cores.ts, tema
  test/                       API falsa e schema real dos tipos de ativo
backend/
  entrypoint.py, financas-backend.spec, alembic.ini, migrations/
  app/api                     rotas por recurso (validar, orquestrar, serializar)
  app/core                    config, paths, logs, segurança, erros, watchdog, banco, backup, migracoes, contrato
  app/domain                  regras puras (sem banco nem rede)
  app/asset_types             base, registry, catalogo (registro único), 10 handlers
  app/repositories            modelos SQLAlchemy, tipos (DecimalTexto, DataHoraUTC), repositórios
  app/services                regras de negócio que usam o banco
  app/providers               base, http (retry/rate limit/cache), registry, catalogo, fontes
  app/jobs                    agendador (asyncio) e eventos SSE
  app/analytics               Protocols e registry (sem modelos)
  tests/                      fabricas.py + testes por camada
scripts/                      contrato.py, versao.py, empacotar_backend.py, smoke_backend.py, 1_/2_/3_*.bat
```

## 5. Convenções
- **Idioma:** pt-BR em mensagens, docs e comentários; identificadores de domínio em português.
- **Camadas:** `domain` sem banco nem rede; `repositories` sem `commit` e sem regra; `services` recebem a `Session` e não fazem `commit` (quem chama controla a transação: `core.banco.sessao_transacional` ou a dependência de sessão da API).
- **Erros:** domínio em `domain/erros.py` (`NaoEncontradoError` → 404, `ConflitoError` → 409, demais → 422); resposta sempre `{"codigo", "mensagem", "detalhes"?}` em pt-BR, sem stack trace. `AplicacaoError(status, codigo, mensagem)` para erros da aplicação.
- **API:** `operation_id` = nome da função; decimais trafegam como **texto** (float JSON recusado); saída arredondada só na apresentação (dinheiro 2 casas; preço, quantidade e razões 8); paginação `limite`/`deslocamento` (máx. 500).
- **Dinheiro no banco:** `DecimalTexto` (TEXT exato) e `DataHoraUTC`; CHECKs com `CAST(col AS NUMERIC)`; buscas por nome com a função SQL `casefold`.
- **Entrada de valores:** casas a mais são **recusadas**, nunca arredondadas (dinheiro 2, quantidade e preço 8, câmbio 6). Textos pelo helper `domain/textos.py` (limpa pontas; vazio vira `None`; tamanho acima do limite é recusado).
- **Dados do usuário:** só via `core/paths.py` (`%APPDATA%\Financas\`, ou `FINANCAS_DATA_DIR`). `locais.rs` repete a regra e `tests/test_paths.py` confere.
- **Logs:** `logs\backend.log` rotativo (1 MB × 5); no app instalado o `stderr` do Python é redirecionado para ele.
- **Mudou um model?** Migração Alembic revisada à mão; `test_models_e_migracao_estao_sincronizados` falha se divergirem.
- **Testes:** nada depende da internet nem do relógio real; backend com `TestClient` e SQLite temporário; dados em `tests/fabricas.py`; front com Vitest + Testing Library e `src/test/api-falsa.tsx`.
- **Front:**
  - sem cores fixas: tokens em `theme/index.css` (claro e escuro; `theme/tokens.test.ts` confere todos);
  - cliente da API por `useClienteApi()` (só existe depois que o portão liberou a UI);
  - toda tela com carregando/vazio/erro; erros viram texto por `mensagemDeErro`; respostas passam por `lib/api.exigir` (os `detalhes` por campo vão ao formulário por `aplicarErrosDaApi`); depois de gravar, `invalidarDados`;
  - dinheiro só formatado (texto direto ao `Intl`); soma exata só por `lib/decimal` (BigInt); `paraGrafico` converte para `number` só para desenhar;
  - componentes de formulário com `forwardRef`; seletores são `<select>` nativos estilizados;
  - filtros, ordem e página na URL; seletor Análise Geral/por Instituição compartilhado (Zustand, só na sessão);
  - **tema:** escuro por padrão, só escuro e claro (sem "igual ao sistema"), salvo em `localStorage` (`financas-tema`);
  - **modo privacidade:** botão de olho oculta dinheiro e quantidades do usuário (percentuais, cotações e indicadores continuam visíveis), salvo em `financas-valores-ocultos`. Cada `Tela*` assina `useValoresOcultos()`; formatador novo de valor do usuário ou tela fora das `Tela*` precisa seguir esse padrão;
  - cores dos gráficos lidas das variáveis CSS; **regra das 6 cores por presença** em `lib/fatias.ts` (ordem fixa por tipo; acima de 6, "Outros"); tipos novos entram no fim de `ORDEM_TIPOS_ATIVO`.

## 6. Decisões vigentes por tema
Detalhes e motivos em `HISTORICO.md` (parte indicada) e `CALCULOS.md`.

**Cálculos** (Parte 2)
- Custo por preço médio ponderado; taxas de compra no custo, taxas de venda reduzem o lucro; vender além da posição é erro.
- Proventos não alteram PM nem posição: vão **líquidos** para a conta corrente da instituição (IR retido em campo próprio) e **não** entram em Receitas e Despesas.
- Bonificação: custo informado soma ao custo (sem informação, zero) e conta como rendimento na rentabilidade total.
- Eventos `de:para` na data "ex", antes das transações do dia, para todas as instituições.
- Posição por (ativo, instituição); cada instituição tem conta corrente por moeda; saldo nunca negativo (compra sem saldo gera aviso 409 `saldo_insuficiente` e, se aceita, `ajuste_saldo`). Caixa entra no patrimônio e não rende.
- Câmbio da data guardado em transações e eventos (ou buscado até 7 dias antes); câmbio com mais de 4 dias marca defasado.
- Renda fixa: accrual em 252 dias úteis, valor bruto, origem `calculado`. Poupança simplificada (aniversário mensal, TR = 0).
- Ativo sem cotação vale o custo (defasado). Defasado: preço com mais de 4 dias (cripto: 1).
- `Decimal` com 28 dígitos e `ROUND_HALF_EVEN`; arredonda só na apresentação.

**Tipos de ativo** (Partes 2, 3 e 4.1)
- Tipo é texto validado pelo registry (sem CHECK); registro único em `asset_types/catalogo.py`. 10 tipos hoje, incluindo `tesouro_direto`, `fundo_listado` (FII, Fiagro, FI-Infra), `etf_br`, `etf_us`.
- Tipo identificado pela **lista oficial** (B3 `InstrumentsConsolidatedFile`, NASDAQ), nunca pelo texto do ticker; categoria não mapeada fica fora e vai para o log.
- Deduplicação no handler (`mesma_identidade`/`semelhante`); renda fixa igual a uma existente → 409 `ativo_semelhante` (somar ou criar separado).
- O ativo nasce na própria movimentação (`POST /api/movimentacoes`, atômica): só compra e aporte criam ativo.
- Vencimento pelo handler (`vencimento(metadados)`), usado em "Próximos vencimentos".

**Cotações e coleta** (Partes 3 e 4.1)
- Fontes: Yahoo (chamada direta, sem `yfinance`; desfaz o ajuste de splits), CoinGecko (id automático em `simbolo_externo`), SGS do Banco Central (CDI 4389, Selic 432, IPCA 433, PTAX 1), Tesouro Transparente (PU venda manhã), CVM (ZIP mensal em streaming; subclasse exige `ID_SUBCLASSE`).
- HTTP com timeout, retry com backoff, rate limit por fonte e cache curto; cotação arredondada a 8 casas e câmbio a 6 na fonte.
- Um preço por dia por ativo; manual vence automático; indicador manual nunca é sobrescrito; PTAX vence Yahoo.
- Agenda pura em `domain/agenda.py`: ações e cripto a cada 1–15 min (padrão 5); fora do pregão só até pegar o fechamento (+30 min); diárias uma vez por dia.
- Histórico inicial de até 1 ano; depois só completa lacunas.
- Ciclo: rede sem sessão aberta, gravação por alvo; um `asyncio.Lock` único para coleta, listas e restauração (atualização simultânea → 409). `FINANCAS_SEM_ATUALIZACAO=1` desliga a automática.
- Tempo real por SSE em `GET /api/eventos` lido com `fetch` (o token não vai na URL).

**Backup e migrações** (Partes 2 e 3)
- Migrações na inicialização, com backup validado antes (só se há dados e migração pendente; mantém 10); falha restaura; banco de versão mais nova é recusado.
- Backup manual e restauração pela API de backup do SQLite, com validação e backup de segurança `pre-restauracao`.

**Empacotamento** (Parte 5B)
- PyInstaller **`onedir`** (inicia 2–3× mais rápido e gera instalador menor que `onefile`); spec em `backend/financas-backend.spec`.
- NSIS em pt-BR, `currentUser` (sem administrador, em `%LOCALAPPDATA%\Financas`), atalhos no menu Iniciar e na área de trabalho, WebView2 por `embedBootstrapper`, sem assinatura de código.
- **Desinstalar nunca apaga `%APPDATA%\Financas`.** A caixa "apagar dados" só remove estado da janela e cache do WebView2.
- Versão com fonte única: `scripts/versao.py` propaga o número; `--verificar` falha se divergir. Release nova: mudar o `package.json` da raiz e rodar `npm run instalador`.
- `scripts/3_gerar_instalador.bat` roda versão, testes, lints, contrato, Rust, PyInstaller, smoke test e `tauri build`, parando no primeiro erro.

**Glossário** (Parte 7)
- Conteúdo fixo e só leitura: um `.md` por termo em `features/glossario/conteudo/`, sem backend nem contrato. Termo novo pela skill `novo-termo-glossario`.
- Modelo do verbete com quatro seções fixas; ligações pelos links `[[slug]]`; validação do conteúdo é teste.
- Grafo do ECharts com `layout: "none"` e posições calculadas por função pura determinística (`dominio/layout.ts`); carregado sob demanda.

## 7. Pendências conhecidas
- Sem assinatura de código: aviso do SmartScreen e possível falso positivo de antivírus. Assinatura e auto-update ficam para depois da 1.0.0.
- Validação em máquina limpa (Windows 10 e 11, uma sem WebView2) e backup/restauração entre duas instalações: checklist em `HISTORICO.md` (Parte 5B), a fazer pelo dono.
- Tempo de abertura com cache frio (logo após reiniciar o Windows) não medido.
- Backups deixam `-shm`/`-wal` vazios ao lado do `.db` (não afeta a restauração).
- Lista da B3 respondeu erro 400 em 04/11/2026 (a dos EUA funcionou); conferir se é temporário ou mudança na API.
- Papéis da B3 `CPA`/`TPR` ficam fora da lista (só cadastro manual).
- Lista de lançamentos mostra até 500 por mês (máximo por página).
- Feriados americanos não entram na agenda (só geram coletas extras sem efeito).
- Download em andamento pode segurar o encerramento; o Tauri força após 3 s.
- Glossário: revisar os verbetes de impostos (e `revisado_em`) quando a lei mudar.
- Parte 6: blocos que exigem cálculo novo (inclui sparklines de Variação do dia, Rentabilidade e Saldo do mês).

## 8. Evolução futura (fora da 1.0.0)
Módulo de IA em `analytics/` como extra opcional fora do executável; auto-update pelo plugin updater do Tauri (exige assinar as atualizações e um lugar para publicar); assinatura de código; no glossário, ícones "ⓘ" nas telas e bloco "Na sua carteira".
