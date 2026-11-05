# Finanças: contexto do projeto

Documento vivo. Leia antes de qualquer tarefa e atualize ao tomar decisões novas.

## 1. Visão do produto
App desktop instalável para Windows (ícone e janela próprios, sem navegador externo nem servidor remoto) para:
- acompanhar a carteira de investimentos (ações BR e US, fundos, renda fixa, cripto, poupança) com valores quase em tempo real;
- registrar receitas e despesas mensais (cadastro manual) e mostrar o saldo do mês;
- no futuro, previsão e sugestão de investimentos (arquitetura preparada em `analytics/`, nada de IA por enquanto).

Uso single-user. Dados 100% locais: sem login, nuvem ou sincronização.

Telas previstas: Dashboard, Carteira, Movimentações, Receitas e Despesas, Configurações.
A paleta de cores é definitiva desde a Parte 4 (seção 8.3); o visual final (layout fino, tipografia, ícones, animações) foi feito na Parte 5A a partir de `docs/referencias-visuais/` (seção 8.5).

## 2. Roadmap (cada parte validada pelo dono antes da próxima)
| Parte | Conteúdo | Situação |
|---|---|---|
| 1 | Fundação: monorepo, Tauri + React + sidecar FastAPI, `/health` e rota protegida, encerramento limpo, instância única, estado da janela, contrato OpenAPI → TS, docs | **Validada** |
| 2 | Modelos e banco (SQLite + SQLAlchemy + Alembic com backup prévio), registry de tipos de ativo, services de cálculo com `Decimal` (posição, caixa por instituição, eventos, câmbio, renda fixa, poupança, alocação, série de patrimônio, resumo mensal), estrutura de `analytics/` e testes, com o code review aplicado | **Validada** |
| 3 | Providers de cotação (Yahoo, CoinGecko, SGS, Tesouro Transparente, CVM) em registry; tipo Tesouro Direto; um preço por dia e histórico de 1 ano; atualização em segundo plano (asyncio) com estado por alvo; services de edição; API REST completa (OpenAPI) com 409 de saldo insuficiente; backup/restauração pela API; SSE; cliente TS e hook de exemplo | **Validada** |
| 4 | Frontend funcional com a paleta definitiva: Dashboard, Carteira, Movimentações (Histórico com filtros, resumo e Excel; Eventos; Caixa), Receitas e Despesas, Configurações (indicadores, backup); gráficos; consumo do SSE; backend do histórico | **Validada** |
| 4.1 | Ajuste de fluxo da Parte 4: formulário único de movimentação (o ativo é cadastrado junto com a compra/aporte), deduplicação por tipo, listas oficiais de tickers (B3 e NASDAQ) para busca e identificação do tipo, tipos `fundo_listado`, `etf_br` e `etf_us` | **Validada** |
| 5A | Visual final a partir das referências (tokens de superfície, componentes, gráficos, layout responsivo, ícone do app) e blocos que só usam dados existentes: altas e baixas do dia, próximos vencimentos (rota de leitura nova), chip de status das cotações, sparkline do patrimônio, carteira por instituição com subtotais; regra das 6 cores por presença | **Entregue (aguardando validação)** |
| 5B | Empacotamento do backend (PyInstaller), instalador, script único de build, portabilidade, versão 1.0.0 e bloco 2 do code review | Etapa 1 (bloco 2 do review) **validada**; etapa 2 (empacotamento, 1.0.0) **entregue (aguardando validação)** |
| 6 | Análises e Proventos: tela Proventos (por mês, yield on cost, últimos recebidos), cartão "Proventos 12 meses", evolução empilhada por tipo/instituição e modo "%", "Rentabilidade 12 meses vs. CDI", "Últimos 12 meses" e "Categorias vs. média de 3 meses" em Receitas e Despesas, "Taxa de poupança", mapa da carteira (treemap) | A fazer |

## 3. Decisões de arquitetura (definitivas)
- **Desktop:** Tauri 2 (WebView2). Rust mínimo: inicialização, ciclo de vida do backend, plugins (dialog, single-instance, window-state) e configuração.
- **Frontend:** React 18 + TypeScript strict + Vite, Tailwind CSS 4 + shadcn/ui, React Router, TanStack Query, Zustand.
- **Backend:** Python 3.11+ com FastAPI, rodando como sidecar local (uvicorn).
- **Banco:** SQLite (WAL) + SQLAlchemy 2.0 + Alembic em `%APPDATA%\Financas\financas.db`; pandas para séries.
- **Contrato:** OpenAPI do FastAPI → `docs/openapi.json` → tipos TS em `apps/web/src/api/schema.ts`.
- **Dinheiro:** sempre `Decimal` no backend; no front só formatação (sem aritmética em `number`).

## 4. Integração Tauri + sidecar (como funciona)
1. No `setup`, o Rust (`apps/desktop/src-tauri/src/backend.rs`) reserva uma porta livre em `127.0.0.1`, gera um token aleatório (32 bytes, hex) e inicia o backend com as variáveis `FINANCAS_PORTA`, `FINANCAS_TOKEN`, `FINANCAS_PID_PAI` (e `FINANCAS_DEV=1` em desenvolvimento). O token vai por variável de ambiente, nunca por argumento, para não aparecer na lista de processos.
2. Uma thread consulta `GET /health` a cada 150 ms por até **120 s** na primeira abertura de cada executável (depois de instalar ou atualizar) e em desenvolvimento, e por até **30 s** nas aberturas seguintes do mesmo executável (ver 8.6). Se o processo morrer ou o tempo acabar, o estado vira "falhou" com mensagem em pt-BR.
3. O React chama `invoke("conexao_backend")`, que aguarda o estado e devolve `{ urlBase, token }` ou rejeita com a mensagem. Enquanto isso a UI mostra "Iniciando o serviço interno…"; em erro mostra a mensagem e o botão **Tentar novamente** (`invoke("reiniciar_backend")`).
4. Todas as chamadas usam `Authorization: Bearer <token>`; só `/health` é aberto.
5. **Encerramento:** no `RunEvent::Exit`, o Rust chama `POST /api/sistema/encerrar` (protegido, fora do contrato público), espera até 3 s o processo sair e então força (`TerminateJobObject` + `kill`).
6. **Sem órfãos:** o processo do backend é associado a um **Job Object** com `KILL_ON_JOB_CLOSE` (se o app for finalizado à força, o Windows encerra o backend e os filhos dele) e o Python tem um **watchdog** que espera o PID do app terminar e chama `os._exit`.
7. **Instância única:** plugin single-instance (registrado primeiro); a segunda abertura só foca a janela existente e não inicia outro backend.
8. **Janela:** plugin window-state salva tamanho, posição e maximizado (arquivo do plugin em `%APPDATA%\br.com.financas.desktop\`).
9. **Desenvolvimento:** em build debug o Rust usa `backend\.venv\Scripts\python.exe entrypoint.py --reload` (uvicorn com reload, sem empacotar). Em release usa `financas-backend\financas-backend.exe` na pasta de recursos do app (`resource_dir()`, a pasta de instalação), empacotado com o PyInstaller `onedir` (Parte 5B, seção 8.6), com o stderr em `%APPDATA%\Financas\logs\backend-stderr.log`.

### Segurança
- API só em `127.0.0.1`; porta e token dinâmicos por sessão; comparação do token com `secrets.compare_digest`.
- CORS: `http://tauri.localhost` (sempre) e `http://localhost:5173` / `http://127.0.0.1:5173` (só com `FINANCAS_DEV=1`).
- CSP do Tauri: `connect-src 'self' ipc: http://ipc.localhost http://127.0.0.1:*` (o `devCsp` acrescenta o Vite).
- Capabilities: `capabilities/main.json` só com `dialog:allow-open` e `dialog:allow-save` (Parte 4: escolher o backup a restaurar e onde salvar a planilha) e `core:app:allow-version` (Parte 5B: versão do app em Configurações → Sobre). O front não lê nem grava arquivos: entrega o caminho e o backend faz o resto. Acrescente permissões somente quando uma tela precisar.
- `/docs` (Swagger) só existe em modo dev.

## 5. Estrutura
```
apps/desktop/                 package.json (CLI do Tauri), icone.svg (fonte dos ícones)
apps/desktop/src-tauri/       Rust: lib.rs (plugins/comandos), backend.rs (sidecar), job.rs (Job Object),
                              locais.rs (backend instalado, pasta de dados e backend-stderr.log);
                              tauri.instalador.conf.json (backend como recurso, só no build do instalador)
apps/web/src/
  app/                        App, rotas, layout (navegação lateral), barra superior (chip de
                              status das cotações, Atualizar cotações, tema), navegação, erro global
  features/                   uma pasta por tela: dashboard, carteira, movimentacoes
                              (historico, eventos, caixa, transacao), receitas-despesas,
                              configuracoes; status-backend (portão da Parte 1); tempo-real (SSE)
  components/                 compartilhados: CartaoMetrica, TabelaDados (agrupamento com
                              subtotais), Campo, Estados, DialogoConfirmacao, IndicadorDefasado,
                              SeletorAnalise, Segmentos, Marca, ValorFinanceiro, graficos/
                              (ECharts, Lightweight Charts, Sparkline, estiloGrafico); ui/ (shadcn)
  api/schema.ts               GERADO pelo openapi-typescript (não editar)
  lib/                        api (exigir/invalidar), decimal (BigInt), formatacao, datas,
                              formularios (Zod pt-BR), fatias (cores por categoria),
                              consultas-comuns, dialogos-nativos, eventos.ts (SSE)
  theme/                      tokens (index.css), cores.ts (tokens para os gráficos), tema
  test/                       API falsa para testes de tela e o schema real dos tipos de ativo
backend/
  entrypoint.py               ponto de entrada do sidecar
  financas-backend.spec       spec do PyInstaller (onedir)
  alembic.ini, migrations/    Alembic (env.py + versions/); rodam sozinhas na inicialização
  app/api                     rotas por recurso (só validam/orquestram/serializam):
                              instituicoes (e caixa), ativos, transacoes (e eventos),
                              movimentacoes (cadastro + transação), simbolos (listas), precos, indicadores, portfolio, financeiro, configuracoes,
                              backup, eventos (SSE); dependencias.py e schemas.py comuns
  app/core                    config, paths, logs, segurança, erros, watchdog,
                              banco (engine/pragmas/sessão), backup, migracoes, contrato
  app/domain                  regras puras: numeros, calendario, posicao, montante, historico,
                              renda_fixa, poupanca, conta_corrente, metricas, carteira,
                              serie_patrimonio, lancamentos, indicadores, precos, agenda, erros,
                              textos (texto opcional/obrigatório),
                              listas (classificação oficial dos tickers)
  app/asset_types             base (contrato), registry, catalogo (registro único), 10 handlers
  app/repositories            modelos (SQLAlchemy), tipos (DecimalTexto, DataHoraUTC), repositórios
  app/services                cadastros, ativos, mercado, caixa, transacoes, posicoes, carteira,
                              patrimonio, portfolio, financeiro, configuracoes, coleta,
                              status_cotacoes, backup, historico, exportacao (Excel),
                              movimentacoes (ativo + transação), simbolos (listas e busca)
  app/providers               base (contrato), http (retry/rate limit/cache), registry, catalogo,
                              yahoo, coingecko, sgs, tesouro, cvm, listas_b3, listas_nasdaq
  app/jobs                    agendador (asyncio) e eventos (canal + gerador SSE)
  app/analytics               protocolos (Protocol) e registry de modelos (sem modelos)
  tests/                      fabricas.py (dados sintéticos) + testes por camada
docs/                         CONTEXTO.md, CALCULOS.md, TIPOS_DE_ATIVO.md, ANALYTICS.md, openapi.json
scripts/                      contrato.py, versao.py (versão com fonte única), empacotar_backend.py,
                              smoke_backend.py, 1_instalar_ferramentas.bat, 2_preparar_projeto.bat,
                              3_gerar_instalador.bat
```

## 6. Convenções
- Idioma: pt-BR em mensagens ao usuário, docs e comentários; identificadores de domínio em português.
- **Erros da API:** sempre `{"codigo", "mensagem", "detalhes"?}` em pt-BR (`app/core/errors.py`); sem stack trace para o cliente. Exceção de aplicação: `AplicacaoError(status, codigo, mensagem)`.
- **operation_id** = nome da função da rota (nomes estáveis no cliente TS).
- **Dados do usuário:** só via `app/core/paths.py` (`%APPDATA%\Financas\`, sobrescrevível por `FINANCAS_DATA_DIR` nos testes).
- **Logs:** `%APPDATA%\Financas\logs\backend.log`, rotativo (1 MB × 5). No modo reload, o supervisor loga só no console.
- **Front:** sem cores fixas em componentes (tokens em `theme/index.css`, ver 8.3); toda tela com carregando/vazio/erro; falhas viram texto via `mensagemDeErro`. Respostas da API passam por `lib/api.exigir` (lança `FalhaApi` com os `detalhes` por campo, que `aplicarErrosDaApi` coloca nos campos do formulário). Depois de qualquer gravação, `invalidarDados` marca as consultas como desatualizadas (só as visíveis são refeitas).
- **Tema:** **escuro por padrão**; só dois modos (escuro e claro), alternados por um switch no topo (`components/SeletorTema.tsx`, ligado = escuro). A escolha fica no `localStorage` da janela (`financas-tema`, Zustand persist). O `index.html` já nasce com `class="dark"` para não piscar claro na abertura. Não há modo "igual ao sistema" (decisão do dono, Parte 1).
- **Cliente da API:** `openapi-fetch` tipado por `schema.ts`; obtido com `useClienteApi()` (só existe depois que o portão liberou a UI).
- **Testes:** nenhum depende da internet nem do relógio real (datas injetadas); backend com `TestClient`, pasta de dados temporária e SQLite temporário (fixtures `engine`/`sessao`); dados sintéticos em `tests/fabricas.py`; front com Vitest + Testing Library e `fetch` falso.
- **Camadas do backend:** `domain` não acessa banco nem rede; `repositories` não fazem `commit` nem regra de negócio; `services` recebem a `Session` e também não fazem `commit` (a unidade de trabalho é de quem chama: `core.banco.sessao_transacional` ou, quando houver API, a dependência de sessão).
- **Erros de domínio:** `app/domain/erros.py` (`DominioError` e subclasses, mensagens pt-BR, sem HTTP). A API converte: `NaoEncontradoError` → 404, `ConflitoError` → 409, demais → 422, com `detalhes` por campo.
- **Dinheiro no banco:** colunas `DecimalTexto` (TEXT exato) e `DataHoraUTC` (UTC com fuso); CHECKs usam `CAST(col AS NUMERIC)`. Buscas por nome usam a função SQL `casefold` registrada em cada conexão (o `lower()` do SQLite não trata acentos).
- **Mudou um model?** Crie a migração (`alembic revision --autogenerate`), revise à mão e rode os testes: `test_models_e_migracao_estao_sincronizados` falha se model e migração divergirem.

## 7. Decisões tomadas na Parte 1
- **Gerador do cliente:** `openapi-typescript` (tipos) + `openapi-fetch` (cliente fino tipado). Mais leve que orval e sem código gerado de runtime.
- **Monorepo:** npm workspaces (`apps/web`, `apps/desktop`) com um único `package-lock.json`; scripts do dia a dia na raiz.
- **Python:** `pyproject.toml` + venv em `backend/.venv`, instalado com `pip install -e ".[dev]"`. `httpx2` é usado pelo `TestClient` do Starlette.
- **TypeScript 5.9** (o typescript-eslint e o openapi-typescript ainda não suportam o TS 7).
- **Health check do Rust** com HTTP/1.1 mínimo sobre `TcpStream` (sem cliente HTTP extra no binário).
- **Encerramento gracioso:** rota interna `POST /api/sistema/encerrar` (token exigido, fora do OpenAPI). Em release, sinaliza `uvicorn.Server.should_exit`; no modo reload (dev), `SIGINT` no worker e o Rust encerra o supervisor pelo Job Object assim que o `/health` para de responder.
- **Ícone provisório** em `apps/desktop/icone.svg` (`npx tauri icon icone.svg -o src-tauri/icons`). Ícones de Android/iOS não são versionados.
- **productName** `Financas` (ASCII, evita problemas no instalador); o título da janela é "Finanças".
- **Tema:** padrão escuro e switch claro/escuro, sem modo "sistema" (pedido do dono após a primeira entrega).
- **Node:** recomendada a versão LTS (24). Com Node 25 a instalação funciona, mas o npm avisa que o jsdom não suporta oficialmente versões ímpares.

## 8. Decisões tomadas na Parte 2
Regras de cálculo completas e exemplos em `docs/CALCULOS.md`.
- **Custo:** preço médio ponderado. Taxas de compra entram no custo; taxas de venda reduzem o lucro realizado. Venda maior que a posição é erro.
- **Proventos (opção A):** não alteram PM nem o valor da posição; vão para a conta corrente da instituição (valor **líquido**, com imposto retido em campo próprio). Métricas: valorização (só preço) e rentabilidade total = (valor − custo restante + lucro realizado + proventos + rendimentos de bonificação) / total investido.
- **Bonificação (opção A):** custo unitário informado pela empresa soma ao custo (regra da Receita); sem informação, zero. O custo atribuído também conta como rendimento na rentabilidade total (decisão técnica derivada, para não subestimar o resultado: *conferir na validação*).
- **Eventos:** proporção `de:para`, na data "ex", antes das transações do mesmo dia, valendo para todas as instituições; frações de grupamento ficam na posição (o leilão é registrado como venda).
- **Instituições e caixa:** toda transação informa a instituição; posição calculada por (ativo, instituição), com **Análise Geral** (consolidada) e **Análise por Instituição**. Cada instituição tem uma conta corrente por moeda: depósito/saque manuais; compra/aporte debitam, venda/resgate e proventos creditam automaticamente. Saldo nunca negativo (checado no fim de cada dia, inclusive retroativamente): compra além do saldo devolve aviso e, se aceita, gera `ajuste_saldo`. Caixa entra no patrimônio e na alocação (fatia `caixa`) e não rende.
- **Multimoeda:** câmbio da data guardado em cada transação (ou buscado nos indicadores, até 7 dias); conta em USD fica em USD.
- **Renda fixa:** accrual em 252 dias úteis com feriados nacionais embutidos, valor bruto (sem IR/IOF), origem `calculado`; resgate proporcional ao saldo; renda fixa e poupança só em BRL e sem taxas.
- **Poupança simplificada:** aniversário mensal, 0,5% ou 70% da Selic, TR = 0, resgate proporcional.
- **Ativo sem cotação:** vale o custo (origem `calculado`, defasado, com aviso). Defasado: preço mais antigo que 4 dias (cripto: 1).
- **Arredondamento:** contexto de 28 dígitos e `ROUND_HALF_EVEN`; arredonda só na apresentação (2 casas moeda, 8 quantidade).
- **Proventos não entram em Receitas e Despesas.**
- **Tipo de ativo:** texto livre validado pelo registry (sem CHECK), para um tipo novo não exigir migração. Registro único em `asset_types/catalogo.py`; exemplo do 7º tipo em `docs/TIPOS_DE_ATIVO.md`.
- **Migrações:** rodam na inicialização; backup validado (`backups\financas-AAAAMMDD-HHMMSS-pre-migracao.db`, 10 mais recentes) só quando há banco com dados e migração pendente; falha restaura o backup (ou apaga o banco novo incompleto); banco de versão mais nova do app é recusado. A migração não importa tipos do app (usa String/DateTime equivalentes).
- **Fuso:** instantes em UTC; a data de um preço é a data local de Brasília (`tzdata` incluído para o Windows).
- **Analytics:** só Protocols e registry versionado; tabelas `previsoes` e `sugestoes` apenas planejadas (`docs/ANALYTICS.md`); ML fica em extra opcional, importado dentro das fábricas.
- **Novas dependências:** `sqlalchemy`, `alembic`, `pandas`, `tzdata`; dev: `pandas-stubs`, `pytest-cov`.

## 8.1 Correções do code review (Parte 2, bloco 1)
Revisão de código feita antes da Parte 3. Correções aprovadas pelo dono (detalhes e exemplos em `docs/CALCULOS.md`):
- **Casas decimais na entrada:** dinheiro 2, quantidade 8, preço unitário 8, câmbio 6. Valores com mais casas são **recusados** (não arredondados), com mensagem em pt-BR (`domain/numeros.exigir_casas`), em todos os services de entrada.
- **Caixa em centavos:** o movimento automático de compra/venda é arredondado a 2 casas (como no extrato); o custo da posição mantém a precisão cheia. Compra a preço zero sem taxas não gera movimento (antes violava o CHECK `valor > 0`).
- **Resgate:** a fração resgatada nunca passa de 1 (antes um resgate entre o saldo real e o exibido deixava principal e custo negativos).
- **Câmbio defasado na avaliação:** câmbio com mais de 4 dias continua sendo usado, mas marca a posição/conta como defasada, com aviso (`domain/indicadores.TOLERANCIA_DEFASAGEM_CAMBIO`). `SaldoCaixa` ganhou `defasado` e `aviso`.
- **Câmbio gravado no evento corporativo** (migração `0002_cambio_eventos`, com preenchimento dos eventos existentes pela regra dos 7 dias). `NovoEvento.cambio` é opcional; `estado_cotas`/`operacoes_cotas` não recebem mais moeda nem indicadores. A busca de câmbio de transações e eventos ficou em `services/posicoes.resolver_cambio`.
- **Série de patrimônio:** o plano B entende posições em cotas (valor aplicado em BRL) e há aviso quando um ativo estrangeiro não tem câmbio algum.
- **Para a Parte 3:** providers devem arredondar cotações (até 8 casas) e câmbio (até 6) antes de gravar, porque `registrar_preco`/`registrar_indicador` recusam valores com mais casas.
- **Bloco 2 do review (limpeza)** ficou para depois e foi feito na Parte 5B (ver 8.6).

## 8.2 Decisões tomadas na Parte 3
Dúvidas resolvidas com o dono antes do código (registradas no `Prompt 3.md`):
- **Yahoo por chamada direta** ao endpoint de gráfico (`query1.finance.yahoo.com/v8/finance/chart`), **sem** a biblioteca `yfinance` (que somaria ~30–40 MB ao executável e quebra com frequência). O slug do provider continua `yfinance`. As casas da fonte (`priceHint`) eliminam o ruído de float (58.68000030517578 → 58.68). O `close` histórico do Yahoo vem ajustado por desdobramentos: o ajuste é **desfeito** com os eventos de split da própria resposta, porque as posições já aplicam os eventos na data "ex" (ex.: 1:2 em 10/03, close ajustado de 20,00 em 09/03 → 40,00).
- **CoinGecko com id automático:** tabela embutida das principais moedas e, para as demais, a pesquisa da CoinGecko, escolhendo o resultado de maior valor de mercado; o id fica em `simbolo_externo` (editável). Plano público, sem chave; histórico limitado a 365 dias.
- **Fundos (CVM):** histórico de 1 ano como os demais. ZIP mensal (~12 MB) baixado para um temporário, lido em streaming e descartado; mês corrente ainda não publicado (404) usa o anterior. Formato antigo e da Resolução 175; classe com subclasses exige o `ID_SUBCLASSE` em `simbolo_externo` (sem ele, não chuta qual cota é a do usuário).
- **Séries do SGS:** 4389 (CDI anualizado base 252, % a.a.), 432 (Selic meta, % a.a., só datas ≤ hoje, porque a série lista o período até a próxima reunião), 433 (IPCA % no mês), 1 (PTAX venda). Paginação em janelas de 5 anos (a API recusa mais de 10). Câmbio só em USD pelo SGS; outras moedas usam o Yahoo.
- **Tesouro Transparente:** CSV único com todo o histórico (`PrecoTaxaTesouroDireto.csv`), coluna **PU Venda Manhã**, baixado uma vez por ciclo (cache de 30 min).

Decisões técnicas desta parte:
- **HTTP:** `httpx2` (já usado pelo `TestClient`) passa a ser dependência de runtime; nenhuma dependência nova. Cliente comum com timeout (20 s; downloads 180 s), retry com backoff exponencial (1 s, 2 s...) em rede/5xx/429 (respeita `Retry-After`), intervalo mínimo por fonte (CoinGecko 4 s) e cache curto. Erros viram mensagens em pt-BR por alvo.
- **Arredondamento na fonte:** cotação até 8 casas e câmbio até 6, com `ROUND_HALF_EVEN` e sem zeros à direita; floats passam por `str()` antes do `Decimal`.
- **Um preço por dia:** migração `0003_precos_diarios_estado_coleta` acrescenta `precos.data` (data de Brasília calculada em Python, por causa do horário de verão antigo) com unicidade por (ativo, data), deduplicando os registros existentes pelo último de cada dia. Manual > automático no mesmo dia; fechamentos do histórico corrigem automáticos de dias passados e recebem o instante 18h de Brasília. Preço manual só para ativos cotados; o service recusa origem `calculado`.
- **Precedência de indicadores:** manual (inclusive o editado) nunca é sobrescrito; entre fontes automáticas, `bcb_sgs` (PTAX) substitui `yfinance` na mesma data, nunca o contrário; a mesma fonte atualiza o próprio valor (dólar ao longo do dia). Lançamento manual grava `fonte = "manual"`.
- **Estado da coleta** em `estados_coleta` (chave `ativo:<id>`, `indicador:<tipo>:<moeda>` e `indicador:cambio_intradiario:<moeda>`): última tentativa, último sucesso, último erro, provider e `historico_desde`. É a base das regras de agenda e do status por ativo.
- **Agenda** (`domain/agenda.py`, regras puras): ações e cripto pelo intervalo (1–15 min, padrão 5, com 30 s de folga); fora do pregão, ação só coleta se o último sucesso foi antes do último fechamento, considerado **30 min depois** do horário oficial (B3 17h → 17h30; EUA 16h → 16h30 de Nova York). B3 respeita os feriados nacionais; feriados americanos não (só geram coletas extras sem efeito). Diárias: se o último sucesso não foi hoje. Cada handler declara a sua `agenda` (`ClassVar`).
- **Histórico:** primeira carga de até 1 ano (ou desde a primeira compra, se mais recente); se uma compra anterior ao início já baixado aparecer, baixa de novo desde ela; depois disso só completa lacunas (app fechado por alguns dias) a partir do último preço. Indicadores: carga desde a data mais antiga necessária (margem de 7 dias; IPCA 2 meses antes do mês) e recoleta diária dos últimos 10 dias (IPCA 100 dias) para pegar publicações atrasadas.
- **Câmbio das transações:** o informado pelo usuário prevalece; sem ele, o indicador de câmbio da data (PTAX, com o Yahoo como reserva), regra dos 7 dias da Parte 2.
- **Defasagem de renda fixa e poupança:** continuam `calculado`, mas ficam defasadas (com aviso) se o CDI/Selic usado tiver mais de 4 dias ou o IPCA mais de 2 meses de atraso, até a data de referência (a renda fixa para no vencimento: `referencia_indicadores`).
- **Ciclo de coleta** (`services/coleta.py`): plano numa transação curta, rede **sem sessão aberta**, gravação numa transação por alvo; ativo excluído no meio do ciclo é ignorado; erro inesperado vira `ultimo_erro` com log. Ao cadastrar (ou editar) um ativo cotado, a API dispara uma coleta só dele depois da resposta.
- **Agendador** (`jobs/agendador.py`): `asyncio` + `to_thread`; um ciclo ao abrir e um a cada intervalo, relendo a configuração a cada volta (mudar o intervalo acorda o laço). `asyncio.Lock` impede ciclos simultâneos: a atualização forçada responde **409** `atualizacao_em_andamento` se já houver uma rodando; a restauração de backup usa o mesmo lock. No encerramento, o coletor é cancelado entre alvos. `FINANCAS_SEM_ATUALIZACAO=1` desliga a atualização automática (testes e diagnóstico).
- **Edições:** transação e evento são **substituídos no mesmo registro** (o id não muda) e o ativo é reprocessado; o ativo não pode ser trocado; trocar a instituição confere o saldo da conta antiga. A edição de transação refaz os movimentos automáticos e o ajuste de saldo e passa pelo aviso de saldo insuficiente. Ativo: só nome, símbolo externo e campos específicos; mudar a identificação na fonte (`campos_identificacao`, ex.: CNPJ) apaga os preços automáticos e o estado da coleta. Instituição: exclusão só sem transações e movimentos (contas vazias saem junto). Categoria: só o nome muda.
- **API:** uma rota por recurso, `operation_id` = nome da função; sessão como dependência com `scope="function"` (commit **antes** da resposta). Decimais trafegam como **texto** nos dois sentidos; float JSON é recusado com mensagem em pt-BR. Mensagens de validação do Pydantic traduzidas (`core/errors.mensagem_validacao`). Saída arredondada na apresentação: dinheiro 2 casas; preço, quantidade e razões 8. Paginação `limite`/`deslocamento` (máx. 500) em transações, extrato, lançamentos e histórico de preços.
- **409 de saldo insuficiente:** `codigo = saldo_insuficiente`, mensagem com instituição, moeda, data e valor; `detalhes` com `instituicao_id`, `instituicao`, `moeda`, `data` e `valor_faltante` (formato padrão campo/mensagem). Reenviar com `aceitar_ajuste=true` grava a transação e o `ajuste_saldo`.
- **Backup/restauração pela API** (`services/backup.py`): backup manual validado (retenção 10); restauração de um backup da pasta (por nome, sem caminhos relativos) ou de um arquivo (caminho absoluto), com validação (SQLite íntegro, tabelas do Finanças, revisão conhecida), backup de segurança `pre-restauracao`, conexões fechadas, cópia pela API de backup e migrações; falha volta o backup de segurança.
- **Tempo real:** SSE em `GET /api/eventos` consumido por `fetch` com `Authorization: Bearer` (o `EventSource` nativo não envia headers e o token não pode ir na URL; WebSocket exigiria mudar a CSP para `ws://`). Eventos `conectado`, `preco_atualizado`, `indicador_atualizado`, `erro_provider`, `fim_ciclo` e `heartbeat` (15 s). Fila por cliente limitada (200; descarta os mais antigos de quem não consome). No front: `lib/eventos.ts` (`lerEventosSse`, `conectarEventos` com reconexão e `useEventosTempoReal`).
- **Contrato:** `tests/test_contrato.py` falha se `docs/openapi.json` diferir do gerado (`core/contrato.texto_openapi`, compartilhado com `scripts/contrato.py`); `npm run contrato:verificar` segue cobrindo o `schema.ts`.
- **Tesouro Direto** como 7º tipo (`tesouro_direto`): cotado pelo PU de venda, BRL, sem taxas (`aceita_taxas = False`), provento só para títulos com juros semestrais, compra recusada a partir do vencimento. `renda_fixa` segue para CDB, LCI, LCA e afins.

## 8.3 Decisões tomadas na Parte 4
Dúvidas resolvidas com o dono antes do código (registradas no `Prompt 4.md`):
- **Paleta definitiva** (prévia `docs/referencias-visuais/previa-paleta.html`): violeta principal, azul-marinho nas superfícies escuras, cinzas arroxeados. Tokens do shadcn mais `lateral*`, `positivo`/`negativo`, `sucesso`/`perigo`/`aviso`/`aviso-texto`/`info` e `grafico-1..6`/`grafico-caixa`, em oklch nos dois temas e expostos ao Tailwind (`bg-lateral`, `text-positivo`...). `theme/tokens.test.ts` garante cada token em `:root` e `.dark`. Ganho/perda sempre com sinal e seta (`ValorFinanceiro`); zero em `--muted-foreground`.
- **Situação do ativo nas duas visões:** com filtro de instituição, vale a situação da posição; sem filtro, a do ativo somando as instituições. A tabela do histórico tem a visão **Por ativo** (linha agregada que se abre por instituição).
- **Taxas × imposto (opção A):** "Taxas pagas" só soma taxas; o IR retido dos proventos é `impostos_retidos` (cartão de proventos, coluna auxiliar Imposto e detalhe). Não há estimativa de IR sobre ganho de capital.
- **Exportação em Excel (.xlsx)** pelo backend (`openpyxl`, nova dependência, puro Python), com todos os filtros e a ordem da tela; números como número e datas `AAAA-MM-DD`. O caminho vem do diálogo nativo de salvar (`POST /api/transacoes/exportar`); o arquivo é gravado num temporário e trocado (planilha aberta no Excel vira mensagem em pt-BR).
- **Lightweight Charts** no detalhe do ativo da Carteira (preço de 1 ano, área com degradê do `--grafico-1`).

Decisões técnicas desta parte:
- **Backend do histórico:** `GET /api/transacoes` ganhou `tipos` (lista), `tipo_ativo`, `moeda`, `busca` (símbolo/nome, com `casefold`), `situacao`, `apenas_prejuizo`, `apenas_com_custos`, `ordem` e `direcao` (ordenação na API, coerente com a paginação; vazios no fim). Cada transação traz `valor_total(_brl)`, `taxas_brl`, `imposto_retido_brl`, `resultado(_brl)` e `situacao`, também nas respostas de cadastro e edição. `GET /api/transacoes/resumo` devolve os totais, `total_sem_filtros` (o "M" de "N de M"), a série mensal e `por_ativo`. Os ativos do filtro são reprocessados com **todas** as transações; posição que não fecha mais vai para o log e fica sem resultado (não derruba a consulta). Regras em `docs/CALCULOS.md` §12.
- **Bibliotecas:** TanStack Table **v8** (a v9, recém-lançada, mudou a API), React Hook Form + Zod 4 (`@hookform/resolvers`), ECharts 6 (import modular: pizza, barras e linha), Lightweight Charts 5, date-fns 4, `@tauri-apps/plugin-dialog`, Radix Dialog/AlertDialog/Tabs. Os seletores são `<select>` nativos estilizados (acessíveis e simples de testar), não o Select do Radix.
- **Componentes de formulário com `forwardRef`:** o React 18 não passa `ref` como prop e, sem isso, o React Hook Form não preenche os valores iniciais. Formulários com listas vindas da API só aparecem depois que as listas carregam (senão o `<select>` perde o valor inicial).
- **Dinheiro no front:** o texto decimal vai direto ao `Intl.NumberFormat` (sem `number`). `lib/decimal.ts` faz sinal, comparação, soma exata (`BigInt`, usada só no "Outros" dos gráficos e no bruto do provento) e normaliza o que o usuário digita ("1.234,56" → "1234.56"). Casas a mais são recusadas, não arredondadas (dinheiro 2, quantidade e preço 8, câmbio 6). Razões da API (rentabilidade, participação, variação) viram percentual movendo a vírgula. `paraGrafico` converte para `number` só para desenhar.
- **Cores dos gráficos:** lidas das variáveis CSS e convertidas para `rgb()` pelo próprio navegador (1 pixel de canvas), porque ECharts e Lightweight Charts não entendem `oklch`; guardadas por tema. A classe `dark` muda junto com o estado do tema (store), antes de o React redesenhar, para os gráficos lerem o tema novo. Ordem fixa por categoria (`lib/fatias.ts`): tipos de ativo em `ORDEM_TIPOS_ATIVO` (ação BR, renda fixa, fundo, ação US, Tesouro, cripto, poupança); instituições e categorias pela ordem de criação. Categoria sem posição fixa usa a primeira cor livre; acima de 6, "Outros" com a cor de caixa.
- **Estado de UI:** filtros, ordem, página e visão do histórico ficam na URL (`?tipo_ativo=…&ops=venda,resgate&periodo=ano…`, sem os valores padrão); a aba de Movimentações em `?aba=`; o seletor Análise Geral/por Instituição é compartilhado entre Dashboard e Carteira (Zustand, só na sessão). Busca com espera de 300 ms. Períodos em meses de calendário ("últimos 12 meses" = dia 1º de 11 meses atrás até hoje).
- **Tempo real:** o layout assina o SSE; `preco_atualizado`, `indicador_atualizado`, `erro_provider` e `fim_ciclo` invalidam as consultas de cotação, agrupadas numa janela de 800 ms; o topo mostra a hora do último ciclo e as falhas.
- **Indicadores na tela:** último valor de cada série nos últimos 120 dias; lançamento manual (IPCA no dia 1º) e edição do último valor (que passa a ser manual).
- **Testes do front:** `src/test/api-falsa.tsx` (rotas falsas que conferem o token e registram as chamadas) com o schema real dos tipos de ativo (10 desde a Parte 4.1) (`src/test/dados/tipos-ativo.json`, exportado do registry). Os gráficos viram marcadores no `setup.tsx` e os invólucros têm testes próprios.
- `.prettierignore` ignora `docs/referencias-visuais` (prévias do dono, não são código do app).

## 8.4 Decisões tomadas na Parte 4.1
Dúvidas resolvidas com o dono antes do código (registradas no `Prompt 4.1.md`):
- **Sem passo separado de cadastro:** a entidade `ativos` continua (cotações, eventos, coleta e posições dependem dela), mas o ativo é criado na própria movimentação. Só **compra e aporte** criam ativo; venda, resgate e provento usam um ativo existente. A Carteira perdeu "Novo ativo" (ganhou "Nova movimentação"); a edição do ativo continua no detalhe.
- **Tipo pelo cadastro oficial, nunca pelo texto do ticker** (o final 11 é unit, FII ou ETF). Conferido no `InstrumentsConsolidatedFile` da B3 de 30/10/2026 (2.916 papéis classificados):
  - mercado à vista (`CASH`/`EQUITY-CASH`): `SHARES` ON → ação ON; PN, PNA, PNB, PNC, PND, PRA, PRB, PNV → ação PN; `UNIT` → ação (unit); `BDR` → ação (BDR; BDR de ETF continua BDR); `ETF EQUITIES`/`ETF FOREIGN INDEX` → `etf_br`; `FUNDS` → `fundo_listado`;
  - ETF de renda fixa: `FORWARD` + `FIXED INCOME TRADABLE INSTRUMENT T1` **e** linha `ETF PRIMARY MARKET` do mesmo `Asst` (76 no arquivo; nenhum papel da categoria ficou sem o mercado primário);
  - fora da lista: `SHARES`/`DIA` (taxas de financiamento do termo), `SHARES`/`REC`, recibos, direitos, warrants e índices;
  - **não mapeado** (fica fora e vai para o log, nunca vira "ação"): qualquer categoria nova e as especificações `CPA`/`TPR` (7 papéis no arquivo);
  - EUA: diretório da NASDAQ, coluna `ETF` (Y → `etf_us`, N → `acao_us`); emissões de teste e símbolos com sufixo especial (preferenciais `$`, warrants, direitos, units) ficam fora; `BRK.B` vira `BRK-B`. O cabeçalho real do `nasdaqlisted.txt` foi conferido em 04/11/2026 pelo smoke test da Parte 5B (lista dos EUA importada com 12.863 tickers); o parser continua exigindo a coluna `ETF`.
- **FII, Fiagro e FI-Infra num tipo só** (`fundo_listado`, "Fundo listado (FII, Fiagro, FI-Infra)"): a B3 põe todos em `FUNDS` e o CFI não os separa (HGLG11 e RZAG11 têm o mesmo `CICIRU`). É diferente de `fundo` (fundo aberto da CVM, pelo CNPJ, sem ticker).
- **ETFs com tipo próprio:** `etf_br` (BRL, agenda B3) e `etf_us` (USD, agenda EUA). Ação (Brasil) perdeu a opção "ETF" do tipo de papel; a migração tira esse campo dos ativos que o tinham, **sem reclassificar** o tipo.
- **Ticker fora das listas:** a busca baixa a lista do dia em segundo plano (no máximo uma vez por dia e por bolsa) e, enquanto isso, a pesquisa do Yahoo só **sugere o nome** (tipo "não identificado"). O cadastro manual é permitido, com o aviso "a cotação pode falhar".
- **Renda fixa repetida: perguntar e somar.** Mesmos emissor (sem acento/maiúsculas), indexador, taxa e vencimento de um título existente → 409 `ativo_semelhante`; "Somar ao existente" grava aporte nele, "Criar título separado" cadastra outro.
- **Trava de venda mantida:** vender/resgatar além da posição continua bloqueado no backend; o formulário mostra "Disponível: N" (posição na instituição e na data) e avisa antes de enviar.

Decisões técnicas desta parte:
- **Deduplicação no handler** (`mesma_identidade`/`semelhante`, `normalizar_simbolo`, `simbolo_externo_padrao`; ver `docs/TIPOS_DE_ATIVO.md`), aplicada em `services/cadastros` (o cadastro avulso também recusa duplicado) e em `services/movimentacoes`. Ticker repetido no mesmo tipo com outra identificação (ex.: duas criptos "BTC" com ids diferentes) é recusado com 409, em vez de estourar a constraint.
- **Papéis da B3 gravam o símbolo na fonte** (`HGLG11.SA`) no cadastro; ações BR antigas sem ele continuam funcionando (o Yahoo acrescenta `.SA` para `acao_br`). A edição compara o símbolo efetivo, então não reinicia a coleta à toa.
- **`POST /api/movimentacoes` atômica:** `ativo_id` **ou** `novo_ativo` + dados da transação, `usar_ativo_id`/`confirmar_novo` (resposta ao `ativo_semelhante`) e `aceitar_ajuste`. Qualquer erro, inclusive os 409, desfaz tudo: o ativo novo nunca fica órfão. A edição continua em `PUT /api/transacoes/{id}`.
- **Listas em tabelas próprias** (migração `0004_listas_simbolos`): `simbolos_listados` (bolsa, ticker, nome, tipo, tipo de papel, bolsa americana, categoria original, símbolo no Yahoo) e `listas_simbolos` (situação por bolsa: tentativa, sucesso, quantidade, status e data do arquivo, erro). Preferido a `estados_coleta` porque guarda status, data do arquivo e quantidade.
- **Fontes de lista** em `providers/` (`listas_b3.py`: token + download em dois passos, CSV latin-1 lido em streaming de um temporário, volta até 7 dias quando não há arquivo; `listas_nasdaq.py`); classificação pura em `domain/listas.py`; registro em `RegistroProviders.registrar_lista`.
- **Importação** (`services/simbolos.ImportadorListas`): rede sem sessão aberta, troca da lista inteira numa transação (falha mantém a anterior), eventos SSE `lista_atualizada`/`erro_lista`. O agendador importa na abertura as bolsas sem lista e atende "Atualizar lista" e a busca, sempre **com o mesmo lock** da coleta e da restauração de backup. Com `FINANCAS_SEM_ATUALIZACAO=1`, só o botão importa.
- **Pesquisa por texto** (`BuscaYahoo`, `BuscaCoinGecko`, registradas com `registrar_busca`): clientes próprios com uma tentativa e timeout de 5 s (a busca responde enquanto o usuário digita). Fora do ar, a busca devolve o que tem, com aviso.
- **Rotas novas:** `GET /api/simbolos/busca?tipo=&q=`, `GET /api/simbolos/listas`, `POST /api/simbolos/atualizar` (202; 409 se já houver uma), `POST /api/movimentacoes`. `TipoAtivoSaida` ganhou `busca_por_ticker` e `lista_simbolos`.
- **Front:** `DialogoTransacao` virou o formulário único (tipo → operação → data/instituição → ativo → dados). Compra/aporte: combobox `BuscaAtivo` nos tipos com ticker (↑/↓/Enter/Esc; carteira, lista e pesquisa; cadastro manual só depois que a busca respondeu) ou lista do tipo + "Novo" (fundo, renda fixa, Tesouro, poupança). Venda/resgate: posições de `/api/portfolio/posicoes` na instituição e na data. A data de aplicação de um título novo é a data da operação (campo escondido). Diálogos de confirmação para saldo insuficiente e título semelhante. `DialogoAtivo` ficou só de edição. Configurações ganhou "Lista de tickers". O evento `lista_atualizada` invalida as consultas `["simbolos", ...]`.
- Os 3 tipos novos entram no **fim** de `ORDEM_TIPOS_ATIVO` (as cores dos existentes não mudam).

## 8.5 Decisões tomadas na Parte 5A (visual final)
Dúvidas resolvidas com o dono antes do código (registradas no `Prompt 5.md`). A Parte 5 foi dividida em **5A** (visual) e **5B** (empacotamento); os blocos das sugestões que exigem cálculo novo ficaram para a **Parte 6**.
- **Paleta mantida** (8.3). Só tipografia, espaçamentos, raios, sombras, ícones, densidade e estilo dos gráficos mudaram.
- **Fonte Segoe UI do sistema** (`"Segoe UI", system-ui, sans-serif`), sem fonte externa (a CSP só permite `font-src 'self' data:`); valores com algarismos tabulares.
- **Tokens novos** (em `:root` e `.dark`, cobertos por `theme/tokens.test.ts`): `--sombra-cartao` e `--sombra-elevada` (quase nulas no escuro, onde a borda separa as superfícies; expostas como `shadow-cartao`/`shadow-elevada`) e `--subtotal` (fundo da linha de subtotal, `bg-subtotal`). `--radius` foi de 0,625 rem para 0,75 rem.
- **Regra das 6 cores por presença** (`lib/fatias.ts`): as 6 maiores fatias presentes ganham cor (comparação decimal; empate pela ordem fixa e depois pela chegada) e as demais somam em "Outros"; cada uma das 6 primeiras categorias da ordem fixa mantém a sua cor sempre que aparece; categoria sem cor própria no top 6 usa a primeira cor livre (de um tipo ausente ou que caiu em "Outros"); caixa continua com `--grafico-caixa`; fatias da maior para a menor. Na ordem fixa a 6ª cor é a de **cripto** (poupança é a 7ª e não tem cor própria); o exemplo do prompt citava a poupança como 6ª cor, e os testes seguem a ordem real.
- **Ícone do app** (proposta própria aceita): quadrado violeta (#5B3DF5) com três barras brancas crescentes e linha de tendência (`apps/desktop/icone.svg`, ícones regenerados com `npx tauri icon`). A mesma marca aparece na navegação (`components/Marca.tsx`, cores por token). Os ícones de Android/iOS gerados pelo comando são apagados (não versionados).
- **Sparkline** só no cartão Patrimônio total, com os pontos de `/portfolio/evolucao` da mesma janela do gráfico (consulta compartilhada). `CartaoMetrica` ganhou `grafico` opcional e não reserva espaço sem série.
- **Carteira por instituição com subtotais (opção A):** segmento "Lista | Por instituição" em Posições. Subtotal de Valor = `patrimonio_brl` de `/portfolio/instituicoes` (já com o caixa, mostrado numa linha "Caixa" do grupo); subtotal de Resultado = soma exata no front (`lib/decimal.somar`, BigInt) do `metricas_brl.resultado_total` das posições do grupo; posição sem resultado deixa o subtotal "—". Busca e filtro de tipo só na Lista (filtrar quebraria o significado do subtotal). Sem mudança na API; uma consulta de posições por instituição.
- **Chip de status das cotações** no topo global: ativos com posição aberta (Análise Geral), cada um numa só categoria, prioridade erro > defasado > em dia; categorias zeradas omitidas (tudo zero: "0 em dia").
- **Próximos vencimentos:** rota de leitura `GET /api/portfolio/vencimentos` (`limite` padrão 5, `instituicao_id`, `data`). O handler informa a data em `vencimento(metadados)` (padrão `None`; renda fixa e Tesouro Direto sobrescrevem; um tipo novo com prazo só sobrescreve o método). Seleção e ordem no service (`services/portfolio.listar_vencimentos`): posições abertas com vencimento a partir da data de referência (inclusive), por data e depois pelo nome.
- **Altas e baixas do dia:** a partir de `/portfolio/variacao-dia` (respeita o seletor); até 3 de cada lado pela razão decimal (`features/dashboard/variacoes.ts`); variação zero fica de fora; o símbolo vem do cadastro de ativos.
- **Receitas e Despesas:** só o visual novo; "Taxa de poupança" e as comparações com meses anteriores ficaram para a Parte 6.
- **Atualizar cotações** saiu do cabeçalho da Carteira para o topo global (`app/BarraSuperior.tsx`), com o mesmo comportamento.
- **Seletor de análise em segmentos** ("Análise Geral | Por Instituição"); em "Por Instituição" aparece a lista e a primeira instituição já vem escolhida. O componente `Segmentos` (botões com `aria-pressed`; setas, Home e End movem e escolhem) também é usado nos períodos da evolução e na visão da Carteira.
- **Gráficos:** estilo comum em `components/graficos/estiloGrafico.ts` (tooltip em cartão, eixos sem marcações, grade só horizontal tracejada, legenda com marcadores redondos, degradê do token, opções equivalentes no Lightweight Charts). Roscas (alocação e categorias) com tamanho fixo à esquerda e legenda "nome / valor (percentual)" à direita, que serve de resumo textual.
- **Layout e responsividade:** lateral de 13 rem a partir de 1024 px e só ícones abaixo disso (nome em `title` e `sr-only`); grades que empilham; tabelas rolam dentro do próprio contêiner e números não quebram linha. Conferido de 960×600 a 1440×900 sem rolagem horizontal da página.
- **Animações** sutis (abrir diálogo, trocar aba, hover), desligadas por `prefers-reduced-motion` (regra global em `theme/index.css`).
- **Contraste** dos pares novos (WCAG): texto no subtotal 15,8:1 (claro) e 14,2:1 (escuro); texto suave no subtotal 5,7:1 e 6,7:1; segmento ativo 8,4:1 e 9,9:1; inativo 5,7:1 e 6,3:1; barras brancas da marca sobre o violeta 6,1:1 (o contorno violeta da marca sobre a lateral azul-marinho do tema claro fica em 2,8:1, mas o desenho é reconhecido pelas barras brancas e é decorativo).

## 8.6 Decisões tomadas na Parte 5B (empacotamento e 1.0.0)
Dúvidas resolvidas com o dono antes do código (registradas no `Prompt 6.md`). Entrega em duas etapas: (1) bloco 2 do code review da Parte 2, validado antes de (2) empacotamento.

**Etapa 1: bloco 2 do code review** (sem mudar resultado de cálculo; os testes existentes passam sem ajuste de valores esperados):
- **Helper único de texto** em `domain/textos.py`: `limpar_texto` (pontas sem espaço; vazio ou só espaços → `None`), `texto_opcional(valor, campo, tamanho, rotulo=None)` e `texto_obrigatorio(..., mensagem_vazio=None)`. O tamanho é contado depois da limpeza; acima do limite é recusado (nunca cortado). Com `rotulo`, a mensagem principal ganha o prefixo ("O símbolo: Use no máximo 30 caracteres."); o detalhe do campo é sempre "Use no máximo N caracteres.". Usado em `cadastros`/`ativos` (nome, símbolo, símbolo externo), `caixa` (descrição), `financeiro` (nome da categoria, descrição e observação) e `transacoes` (observação da transação e do evento). **Bug corrigido:** a observação do evento corporativo só com espaços era gravada como `""`; agora vira `None`. As mensagens ao usuário não mudaram.
- **Normalização de metadados separada da validação:** `HandlerTipoAtivo.normalizar_metadados(metadados)` (padrão identidade) roda depois da normalização de cada campo e antes de `regras_adicionais`, devolvendo um dicionário novo. O fundo grava o CNPJ só com dígitos ali; `regras_adicionais` do fundo só valida. Os outros tipos não mudaram (`docs/TIPOS_DE_ATIVO.md` atualizado).
- **Fator de renda fixa criado uma vez:** `posicoes.estado_montante(transacoes, fator)` recebe o fator pronto. A carteira cria um por posição (antes eram dois); reprocessamento, histórico e série de patrimônio criam um por ativo, reaproveitado entre as instituições.
- **`mensagemDeErro` (front):** só a falha de rede do `fetch` (`TypeError` com "Failed to fetch", "network error", "NetworkError…" ou "Load failed", `ehFalhaDeRede`) vira "Não foi possível conectar ao serviço interno"; outro `TypeError` (bug de código) mostra "Ocorreu um erro inesperado." e vai para o console uma vez por erro.
- **Reinício do backend:** `useReiniciarBackend` cancela todas as consultas ao começar e, ao terminar, **reseta todas** (porta e token mudam; nada do backend anterior fica em cache). O SSE já reconecta com a conexão nova porque o efeito depende do objeto `conexao` (teste novo cobre isso).

**Etapa 2: empacotamento e release 1.0.0**
- **Versão com fonte única (1.0.0):** só o `"version"` do `package.json` da raiz é editado à mão. `scripts/versao.py` grava o número em `apps/web` e `apps/desktop` (`package.json`), `package-lock.json` (raiz e os três pacotes), `Cargo.toml`/`Cargo.lock` (pacote `financas`), `backend/app/__init__.py` (`__version__`, gerado: vai no executável, no `/health`, no `/api/ping` e no OpenAPI) e `docs/openapi.json` (`info.version`). `tauri.conf.json` usa `"version": "../../../package.json"` e o `pyproject.toml` usa `dynamic = ["version"]` lendo `app.__version__`. O modo `--verificar` falha se algo divergir (inclusive se o Tauri ou o pyproject voltarem a ter número próprio). A edição é textual (não muda a formatação) e não usa o `npm version`: assim não depende do Node e os testes (`tests/test_versao.py`) rodam o script de verdade numa cópia dos arquivos. **Release nova:** mude a versão no `package.json` da raiz e rode `npm run instalador`.
- **Sobre (Configurações):** a seção "Serviço interno" virou "Sobre", com a versão do app (`getVersion()` do Tauri; capability `core:app:allow-version`, a única acrescentada) e a do serviço interno (`/health`). Se divergirem, aparece um aviso pedindo para reinstalar.
- **PyInstaller `onedir`** (spec versionado em `backend/financas-backend.spec`; extra opcional `build` no `pyproject.toml`, instalado pelo `2_preparar_projeto.bat`). Executável de console (o Rust usa `CREATE_NO_WINDOW`). Entram: `migrations/` como dados na raiz do bundle (`_internal/migrations`, para onde `core/migracoes.PASTA_MIGRACOES` aponta), `collect_submodules("uvicorn")`, os módulos do Alembic e os que o `env.py` importa, o dialeto SQLite, os dados do `tzdata`, `openpyxl` e o `truststore`. Ficam fora: `watchfiles`, pytest, mypy, ruff, `certifi`, `httpcore`/`httpx` antigos e qualquer ML.
- **Medição `onefile` × `onedir`** (`scripts/smoke_backend.py --repeticoes`, do início do processo até o `/health` responder; banco vazio com migrações; Windows 11, Python 3.13, PyInstaller 6.22, 04/11/2026):

  | Cenário | onedir | onefile |
  |---|---|---|
  | 1ª execução de um binário recém-gerado (o Defender varre os arquivos novos; também é o caso da 1ª abertura depois de instalar ou atualizar) | **29,2 s** (2 builds) e **30,9 s** (app instalado, 1ª abertura após atualizar para a 1.0.1) | **40,9 s** |
  | Cópia nova dos mesmos arquivos (hash já conhecido pelo Defender), 1 execução | 3,9 s | 5,7 s |
  | Quente, N = 5 (mín / mediana / máx) | 2,36 / 2,38 / 2,41 s | 4,86 / 6,57 / 8,82 s |
  | App instalado aberto pelo atalho (aberturas seguintes) | 3,6 a 5,4 s | — |
  | Tamanho do backend | 85 MB em pasta | 42 MB num arquivo |
  | Instalador final (NSIS, LZMA) | **36,6 MB** (38.367.003 bytes) | 44,9 MB (47.116.353 bytes) |

  O instalador `onefile` sai maior porque o executável já vem comprimido (zlib) e o LZMA do NSIS não consegue comprimi-lo de novo. O frio de verdade (logo após reiniciar o Windows) não foi medido nesta sessão e fica no roteiro de validação. **Recomendação e decisão: `onedir`.** Inicia 2 a 3 vezes mais rápido nas aberturas normais e com tempo estável. Também gera o instalador menor, não extrai nada para o `%TEMP%` (não sobra `_MEIxxxx` quando o Job Object mata o processo) e tende a ter menos falso positivo de antivírus. O `onefile` continua no spec (`FINANCAS_EMPACOTAMENTO=onefile`) só para repetir a medição.
- **`TIMEOUT_INICIO` do Rust: 30 s → 120 s** (decisão técnica desta parte, **aprovada pelo dono** em 04/11/2026). A 1ª abertura depois de instalar ou atualizar ficou em 29–31 s nas três medições (varredura do Defender nos ~85 MB do backend), ou seja, com 30 s o usuário veria "não respondeu em 30 segundos" na primeira vez. Se o processo morre, a falha continua aparecendo na hora (o Rust confere o processo a cada 150 ms); o limite longo só vale para um backend travado. O smoke test usa o mesmo limite.
  - **Ajuste da revisão de código (04/11/2026):** os 120 s só valem quando o executável ainda não iniciou neste computador. Ao responder ao `/health`, o Rust grava em `logs\backend-pronto.txt` a assinatura do executável (tamanho e data de modificação, que mudam a cada instalação ou atualização). Se a assinatura gravada bate com a do executável atual, o limite é **30 s** (aberturas normais levam 2–5 s), e assim um backend travado não prende o usuário 2 minutos em toda abertura. Se os 30 s estouram, o Rust apaga a marca e o "Tentar novamente" volta a esperar 120 s (ex.: o antivírus varreu o executável de novo). Em desenvolvimento, sempre 120 s.
- **Como o Rust acha o backend:** o `tauri.instalador.conf.json` (passado com `--config` só no build do instalador, para o `cargo check` e o `npm run dev` não exigirem a pasta) inclui `binaries/financas-backend/` como recurso `financas-backend/`. Em release o `backend.rs` usa `app.path().resource_dir()` (no Windows, a pasta de instalação) + `financas-backend\financas-backend.exe` (`locais.rs`, com testes). Sem a pasta ou o arquivo, a mensagem pede para reinstalar.
- **stderr do backend** em `%APPDATA%\Financas\logs\backend-stderr.log` (ou `FINANCAS_DATA_DIR`), novo a cada abertura, com a pasta criada pelo Rust. Assim fica registrado o que acontece antes do `backend.log` (import faltando, erro de configuração com código 2). Se o processo morre antes do `/health`, a mensagem cita esse arquivo e o `backend.log` **da mesma pasta** (respeita `FINANCAS_DATA_DIR`). O stdout continua descartado. Ajustes da revisão de código (04/11/2026):
  - o arquivo da abertura anterior é preservado como `backend-stderr.anterior.log` (uma geração), para o "Tentar novamente" não apagar o erro que a mensagem mandou ler;
  - no app instalado, depois de configurar o logging, o `entrypoint.py` troca o `sys.stderr` por `StderrParaLog` (`core/logs.py`) e liga `logging.captureWarnings`: avisos, exceções não tratadas em threads e `print` de bibliotecas vão para o `backend.log` (rotativo), em vez de crescer sem limite no `backend-stderr.log`. O descritor 2 continua no arquivo, então falhas fatais do interpretador ainda ficam lá;
  - o `locais.rs` repete a regra de `core/paths` (pasta de dados, `FINANCAS_DATA_DIR`, `logs`, `backend.log`) porque o Rust precisa da pasta antes de o Python existir; `backend/tests/test_paths.py` confere que as duas continuam iguais.
- **Smoke test do executável** (`scripts/smoke_backend.py`, rodado pelo build): pasta de dados temporária, token de teste, `FINANCAS_SEM_ATUALIZACAO=1`, espera o `/health`, confere a versão do `package.json`, o `/api/ping` com token e a revisão `head` num banco vazio, e encerra pela rota interna conferindo que o processo saiu (no `onefile`, também que não sobrou `_MEIxxxx`). Com `--https` (padrão no build; `--sem-https` para máquinas sem internet), baixa as listas de tickers e confere a dos EUA: prova que o `truststore` funciona no executável.
- **Instalador NSIS** em pt-BR (`PortugueseBR`), `installMode: currentUser` (sem pedir administrador; instala em `%LOCALAPPDATA%\Financas`), ícone do app, atalhos no menu Iniciar e na área de trabalho, WebView2 por `embedBootstrapper` (≈ +1,8 MB; ainda precisa de internet quando o runtime falta). Sem assinatura de código.
- **Desinstalar nunca apaga `%APPDATA%\Financas`.** A caixa "apagar dados do app" do desinstalador remove só `%APPDATA%\br.com.financas.desktop` e `%LOCALAPPDATA%\br.com.financas.desktop` (estado da janela e cache do WebView2).
- **Script único** `scripts/3_gerar_instalador.bat` (`npm run instalador` = `--sem-pausa`), na ordem: versão (sincroniza e confere), backend (pytest, ruff check, ruff format --check, mypy), contrato, frontend (testes, lint, typecheck, prettier), Rust (`cargo check`, `cargo test`; `clippy` não está configurado), PyInstaller (`scripts/empacotar_backend.py`), smoke test e `tauri build`. Para no primeiro erro e no fim mostra o caminho, o tamanho e a versão do instalador.
- **Validação feita nesta sessão** (04/11/2026, Windows 11; o terminal rodava dentro do pacote MSIX do app Claude, então a instalação ficou virtualizada em `...\Packages\Claude_...\LocalCache\Local\Financas` e os testes usaram `FINANCAS_DATA_DIR` numa pasta temporária, sem tocar no banco do dono):
  - instalação silenciosa (`/S`) da 1.0.0: pasta de instalação com `financas.exe`, `uninstall.exe` e `financas-backend\` (com `_internal\migrations`), atalhos no menu Iniciar e na área de trabalho e registro de desinstalação (`Financas`, 1.0.0, editor "Finanças");
  - abertura pelo atalho do menu Iniciar: backend achado na pasta de recursos, `/health` com a versão 1.0.0, migrações no `head` em banco novo, `backend-stderr.log` criado (vazio) e a UI fazendo requisições;
  - fechamento normal (backend encerra de forma graciosa) e fechamento à força do `financas.exe`: nenhum processo restante (Job Object); sem pasta `_MEI` (onedir);
  - encerramento durante um download (listas de tickers): o processo saiu em 1,66 s (abaixo dos 3 s em que o Tauri força);
  - atualização por cima (1.0.1 sobre 1.0.0): versão 1.0.1 no registro e no `/health`, dados preservados; desinstalação: pasta, atalhos e registro removidos, `%APPDATA%\Financas` intacto (mesmo hash do banco, 9 backups); reinstalação da 1.0.0 abre com os mesmos dados;
  - backup e restauração entre duas pastas de dados independentes com o backend instalado: dados criados na A (instituição, depósito, CDB, categoria, lançamento, intervalo de 10 min), backup manual, restauração na B vazia (com backup de segurança) e 8 rotas comparadas (instituições, contas, configurações, categorias, transações, lançamentos, resumo, ativos) idênticas.
- **Checklist da máquina limpa** (VM com Windows 10 e 11; uma delas **sem WebView2** e com internet), a fazer pelo dono:
  1. instalar com dois cliques: SmartScreen ("Mais informações" → "Executar assim mesmo"); instalador em português; sem pedir administrador; na VM sem WebView2, o bootstrapper baixa e instala o runtime;
  2. abrir pelo atalho da área de trabalho e pelo menu Iniciar; a 1ª abertura pode levar até ~30 s ("Iniciando o serviço interno…"), as seguintes poucos segundos;
  3. Configurações → Sobre: versão do app e do serviço interno 1.0.0, sem aviso;
  4. criar uma instituição, um depósito, uma compra de ação e uma despesa; esperar a primeira carga do histórico (a UI continua respondendo);
  5. fechar pela janela e conferir no Gerenciador de Tarefas que não sobrou `financas-backend.exe`; abrir de novo e fechar à força o `financas.exe` pelo Gerenciador: o backend some junto;
  6. instalar a 1.0.1 por cima: dados mantidos, Sobre mostra 1.0.1;
  7. desinstalar (com e sem a caixa "apagar dados do app"): `%APPDATA%\Financas` continua lá; reinstalar e conferir os dados;
  8. backup na VM A, restaurar na VM B e conferir carteira, caixa, lançamentos e configurações.
- **Evolução futura (fora da 1.0.0):** módulo de IA em `analytics/` como extra opcional, fora do executável (instalado à parte, sem inflar o instalador); auto-update opcional pelo plugin updater do Tauri, que exige assinar as atualizações (chave própria) e um lugar para publicar os arquivos; assinatura de código (resolve o SmartScreen e reduz falso positivo de antivírus); Parte 6 (Análises e Proventos).

## 9. Pendências conhecidas
- Sem assinatura de código: o Windows mostra o aviso do SmartScreen e antivírus podem acusar falso positivo (README explica como contornar). Assinatura e auto-update (plugin updater do Tauri, que exige assinar as atualizações) ficam para depois da 1.0.0.
- Validação em máquina limpa (VM com Windows 10 e 11, uma sem WebView2) e backup/restauração entre duas instalações distintas: checklist em 8.6, a fazer pelo dono (esta sessão validou numa instalação só).
- Tempo de abertura com cache frio (logo após reiniciar o Windows) não medido nesta sessão; comando no roteiro de 8.6.
- Os backups (pré-migração, pré-restauração e manuais) deixam arquivos `-shm`/`-wal` vazios ao lado do `.db` (já acontecia desde a Parte 2; não afeta a restauração, que usa só o `.db`).
- A importação da lista da B3 respondeu "B3 recusou a consulta (erro 400)" nos testes de 04/11/2026 de madrugada (a dos EUA funcionou). Acontece igual pelo venv, então não é do executável; em 30/10 importava normalmente. Conferir se é temporário da B3 ou mudança na API (fora do escopo da 5B).
- Fundos com subclasses (Resolução CVM 175) precisam do `ID_SUBCLASSE` em `simbolo_externo` (a tela de cadastro explica isso).
- Parte 6 (Análises e Proventos): blocos das sugestões do dono que exigem cálculo ou agregação nova (ver roadmap), deixados fora da 5A de propósito; entre eles as sparklines de Variação do dia, Rentabilidade e Saldo do mês (não há série).
- Papéis da B3 com especificação `CPA`/`TPR` ficam fora da lista (não mapeados); só entram por cadastro manual.
- A lista de lançamentos mostra até 500 por mês (máximo da API por página).
- Feriados da bolsa americana não são considerados na agenda (só geram coletas extras sem efeito).
- O ciclo de coleta roda numa thread: no encerramento ele para entre alvos, mas um download em andamento (ex.: ZIP da CVM) pode segurar o processo até o timeout; o Tauri força o fim após 3 s (Job Object).
