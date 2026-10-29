# Finanças: contexto do projeto

Documento vivo. Leia antes de qualquer tarefa e atualize ao tomar decisões novas.

## 1. Visão do produto
App desktop instalável para Windows (ícone e janela próprios, sem navegador externo nem servidor remoto) para:
- acompanhar a carteira de investimentos (ações BR e US, fundos, renda fixa, cripto, poupança) com valores quase em tempo real;
- registrar receitas e despesas mensais (cadastro manual) e mostrar o saldo do mês;
- no futuro, previsão e sugestão de investimentos (arquitetura preparada em `analytics/`, nada de IA por enquanto).

Uso single-user. Dados 100% locais: sem login, nuvem ou sincronização.

Telas previstas: Dashboard, Carteira, Movimentações, Receitas e Despesas, Configurações.
O visual final segue imagens de referência que o dono enviará na Parte 5; até lá a paleta é provisória e neutra.

## 2. Roadmap (5 partes, cada uma validada pelo dono antes da próxima)
| Parte | Conteúdo | Situação |
|---|---|---|
| 1 | Fundação: monorepo, Tauri + React + sidecar FastAPI, `/health` e rota protegida, encerramento limpo, instância única, estado da janela, contrato OpenAPI → TS, docs | **Validada** |
| 2 | Modelos e banco (SQLite + SQLAlchemy + Alembic com backup prévio), registry de tipos de ativo, services de cálculo com `Decimal` (posição, caixa por instituição, eventos, câmbio, renda fixa, poupança, alocação, série de patrimônio, resumo mensal), estrutura de `analytics/` e testes, com o code review aplicado | **Validada** |
| 3 | Providers de cotação (Yahoo, CoinGecko, SGS, Tesouro Transparente, CVM) em registry; tipo Tesouro Direto; um preço por dia e histórico de 1 ano; atualização em segundo plano (asyncio) com estado por alvo; services de edição; API REST completa (OpenAPI) com 409 de saldo insuficiente; backup/restauração pela API; SSE; cliente TS e hook de exemplo | **Entregue (aguardando validação)** |
| 4 | Frontend funcional com visual neutro: Dashboard, Carteira, Movimentações (com aba Caixa), Receitas e Despesas, Configurações (indicadores, backup); gráficos; consumo do SSE | A fazer |
| 5 | Visual final a partir das imagens de referência; empacotamento do backend (PyInstaller) e instalador; script único de build | A fazer |

## 3. Decisões de arquitetura (definitivas)
- **Desktop:** Tauri 2 (WebView2). Rust mínimo: inicialização, ciclo de vida do backend, plugins (dialog, single-instance, window-state) e configuração.
- **Frontend:** React 18 + TypeScript strict + Vite, Tailwind CSS 4 + shadcn/ui, React Router, TanStack Query, Zustand.
- **Backend:** Python 3.11+ com FastAPI, rodando como sidecar local (uvicorn).
- **Banco:** SQLite (WAL) + SQLAlchemy 2.0 + Alembic em `%APPDATA%\Financas\financas.db`; pandas para séries.
- **Contrato:** OpenAPI do FastAPI → `docs/openapi.json` → tipos TS em `apps/web/src/api/schema.ts`.
- **Dinheiro:** sempre `Decimal` no backend; no front só formatação (sem aritmética em `number`).

## 4. Integração Tauri + sidecar (como funciona)
1. No `setup`, o Rust (`apps/desktop/src-tauri/src/backend.rs`) reserva uma porta livre em `127.0.0.1`, gera um token aleatório (32 bytes, hex) e inicia o backend com as variáveis `FINANCAS_PORTA`, `FINANCAS_TOKEN`, `FINANCAS_PID_PAI` (e `FINANCAS_DEV=1` em desenvolvimento). O token vai por variável de ambiente, nunca por argumento, para não aparecer na lista de processos.
2. Uma thread consulta `GET /health` a cada 150 ms por até **30 s**. Se o processo morrer ou o tempo acabar, o estado vira "falhou" com mensagem em pt-BR.
3. O React chama `invoke("conexao_backend")`, que aguarda o estado e devolve `{ urlBase, token }` ou rejeita com a mensagem. Enquanto isso a UI mostra "Iniciando o serviço interno…"; em erro mostra a mensagem e o botão **Tentar novamente** (`invoke("reiniciar_backend")`).
4. Todas as chamadas usam `Authorization: Bearer <token>`; só `/health` é aberto.
5. **Encerramento:** no `RunEvent::Exit`, o Rust chama `POST /api/sistema/encerrar` (protegido, fora do contrato público), espera até 3 s o processo sair e então força (`TerminateJobObject` + `kill`).
6. **Sem órfãos:** o processo do backend é associado a um **Job Object** com `KILL_ON_JOB_CLOSE` (se o app for finalizado à força, o Windows encerra o backend e os filhos dele) e o Python tem um **watchdog** que espera o PID do app terminar e chama `os._exit`.
7. **Instância única:** plugin single-instance (registrado primeiro); a segunda abertura só foca a janela existente e não inicia outro backend.
8. **Janela:** plugin window-state salva tamanho, posição e maximizado (arquivo do plugin em `%APPDATA%\br.com.financas.desktop\`).
9. **Desenvolvimento:** em build debug o Rust usa `backend\.venv\Scripts\python.exe entrypoint.py --reload` (uvicorn com reload, sem empacotar). Em release usa `financas-backend.exe` ao lado do executável (empacotamento na Parte 5).

### Segurança
- API só em `127.0.0.1`; porta e token dinâmicos por sessão; comparação do token com `secrets.compare_digest`.
- CORS: `http://tauri.localhost` (sempre) e `http://localhost:5173` / `http://127.0.0.1:5173` (só com `FINANCAS_DEV=1`).
- CSP do Tauri: `connect-src 'self' ipc: http://ipc.localhost http://127.0.0.1:*` (o `devCsp` acrescenta o Vite).
- Capabilities: `capabilities/main.json` sem permissões; o front só usa `invoke` de comandos do próprio app. Acrescente permissões somente quando uma tela precisar.
- `/docs` (Swagger) só existe em modo dev.

## 5. Estrutura
```
apps/desktop/                 package.json (CLI do Tauri), icone.svg (fonte dos ícones)
apps/desktop/src-tauri/       Rust: lib.rs (plugins/comandos), backend.rs (sidecar), job.rs (Job Object)
apps/web/src/
  app/                        App, roteador, layout
  features/status-backend/    portão de inicialização + tela de status (Parte 1)
  components/ (ui/)           componentes compartilhados e shadcn/ui
  api/schema.ts               GERADO pelo openapi-typescript (não editar)
  lib/                        cliente da API (openapi-fetch), formatação, utils,
                              eventos.ts (stream SSE via fetch + hook de exemplo)
  theme/                      tokens (index.css) e preferência de tema (Zustand)
backend/
  entrypoint.py               ponto de entrada do sidecar
  alembic.ini, migrations/    Alembic (env.py + versions/); rodam sozinhas na inicialização
  app/api                     rotas por recurso (só validam/orquestram/serializam):
                              instituicoes (e caixa), ativos, transacoes (e eventos),
                              precos, indicadores, portfolio, financeiro, configuracoes,
                              backup, eventos (SSE); dependencias.py e schemas.py comuns
  app/core                    config, paths, logs, segurança, erros, watchdog,
                              banco (engine/pragmas/sessão), backup, migracoes, contrato
  app/domain                  regras puras: numeros, calendario, posicao, montante,
                              renda_fixa, poupanca, conta_corrente, metricas, carteira,
                              serie_patrimonio, lancamentos, indicadores, precos, agenda, erros
  app/asset_types             base (contrato), registry, catalogo (registro único), 7 handlers
  app/repositories            modelos (SQLAlchemy), tipos (DecimalTexto, DataHoraUTC), repositórios
  app/services                cadastros, ativos, mercado, caixa, transacoes, posicoes, carteira,
                              patrimonio, portfolio, financeiro, configuracoes, coleta,
                              status_cotacoes, backup
  app/providers               base (contrato), http (retry/rate limit/cache), registry, catalogo,
                              yahoo, coingecko, sgs, tesouro, cvm
  app/jobs                    agendador (asyncio) e eventos (canal + gerador SSE)
  app/analytics               protocolos (Protocol) e registry de modelos (sem modelos)
  tests/                      fabricas.py (dados sintéticos) + testes por camada
docs/                         CONTEXTO.md, CALCULOS.md, TIPOS_DE_ATIVO.md, ANALYTICS.md, openapi.json
scripts/                      contrato.py, 1_instalar_ferramentas.bat, 2_preparar_projeto.bat
```

## 6. Convenções
- Idioma: pt-BR em mensagens ao usuário, docs e comentários; identificadores de domínio em português.
- **Erros da API:** sempre `{"codigo", "mensagem", "detalhes"?}` em pt-BR (`app/core/errors.py`); sem stack trace para o cliente. Exceção de aplicação: `AplicacaoError(status, codigo, mensagem)`.
- **operation_id** = nome da função da rota (nomes estáveis no cliente TS).
- **Dados do usuário:** só via `app/core/paths.py` (`%APPDATA%\Financas\`, sobrescrevível por `FINANCAS_DATA_DIR` nos testes).
- **Logs:** `%APPDATA%\Financas\logs\backend.log`, rotativo (1 MB × 5). No modo reload, o supervisor loga só no console.
- **Front:** sem cores fixas em componentes (tokens em `theme/index.css`, incluindo `sucesso`, `aviso`, `perigo`); toda tela com carregando/vazio/erro; falhas viram texto via `mensagemDeErro`.
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
- **Bloco 2 do review (limpeza)** ficou para depois: helper único de texto opcional, normalização de metadados separada da validação (CNPJ), fator de renda fixa criado uma vez só, `mensagemDeErro` sem mascarar `TypeError`, reset das consultas ao reiniciar o backend.

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

## 9. Pendências conhecidas
- Build de release ainda não inclui o backend empacotado (Parte 5): `tauri build` gera o app, mas ele mostrará "Executável do serviço interno não encontrado".
- Atualização por cima, assinatura de código e SmartScreen: Parte 5.
- Empacotamento (Parte 5): incluir a pasta `backend/migrations` e os dados do `tzdata` no executável do PyInstaller (`core/migracoes.PASTA_MIGRACOES` aponta para ela).
- Telas (Parte 4): diálogo do 409 de saldo insuficiente, restauração com confirmação e diálogo nativo do Tauri (a API já existe), consumo do SSE para atualizar preços sem recarregar.
- Fundos com subclasses (Resolução CVM 175) precisam do `ID_SUBCLASSE` em `simbolo_externo`; a tela de cadastro deve explicar isso.
- Feriados da bolsa americana não são considerados na agenda (só geram coletas extras sem efeito).
- O ciclo de coleta roda numa thread: no encerramento ele para entre alvos, mas um download em andamento (ex.: ZIP da CVM) pode segurar o processo até o timeout; o Tauri força o fim após 3 s (Job Object).
- Bloco 2 do code review da Parte 2 (limpeza) continua pendente (ver 8.1).
