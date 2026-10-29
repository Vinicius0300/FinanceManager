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
| 2 | Modelos e banco (SQLite + SQLAlchemy + Alembic com backup prévio), registry de tipos de ativo, services de cálculo com `Decimal` (posição, caixa por instituição, eventos, câmbio, renda fixa, poupança, alocação, série de patrimônio, resumo mensal), estrutura de `analytics/` e testes. **Sem endpoints novos** | **Entregue (aguardando validação)** |
| 3 | *Proposta:* providers de cotação (registry), jobs de atualização, estado defasado, eventos em tempo real (SSE) | A definir pelo dono |
| 4 | *Proposta:* telas funcionais (Dashboard, Carteira, Movimentações, Receitas e Despesas, Configurações), gráficos, backup/restauração | A definir pelo dono |
| 5 | Visual final a partir das imagens de referência; empacotamento do backend (PyInstaller) e instalador | A definir pelo dono |

> O conteúdo das Partes 3 e 4 é uma proposta inicial e pode ser reordenado pelo dono. Os endpoints REST dos services da Parte 2 (CRUD e consultas) ainda não têm parte definida.

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
  lib/                        cliente da API (openapi-fetch), formatação, utils
  theme/                      tokens (index.css) e preferência de tema (Zustand)
backend/
  entrypoint.py               ponto de entrada do sidecar
  alembic.ini, migrations/    Alembic (env.py + versions/); rodam sozinhas na inicialização
  app/api                     rotas (só validam/orquestram/serializam)
  app/core                    config, paths, logs, segurança, erros, watchdog,
                              banco (engine/pragmas/sessão), backup, migracoes
  app/domain                  regras puras: numeros, calendario, posicao, montante,
                              renda_fixa, poupanca, conta_corrente, metricas, carteira,
                              serie_patrimonio, lancamentos, indicadores, precos, erros
  app/asset_types             base (contrato), registry, catalogo (registro único), 6 handlers
  app/repositories            modelos (SQLAlchemy), tipos (DecimalTexto, DataHoraUTC), repositórios
  app/services                cadastros, mercado, caixa, transacoes, posicoes, carteira,
                              patrimonio, financeiro
  app/analytics               protocolos (Protocol) e registry de modelos (sem modelos)
  app/{providers,jobs}        reservados para a Parte 3
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

## 9. Pendências conhecidas
- Build de release ainda não inclui o backend empacotado (Parte 5): `tauri build` gera o app, mas ele mostrará "Executável do serviço interno não encontrado".
- Atualização por cima, assinatura de código e SmartScreen: Parte 5.
- Empacotamento (Parte 5): incluir a pasta `backend/migrations` e os dados do `tzdata` no executável do PyInstaller (`core/migracoes.PASTA_MIGRACOES` aponta para ela).
- Os services da Parte 2 ainda não têm endpoints; o aviso de saldo insuficiente (`ResultadoTransacao.aviso`) precisará de um fluxo de confirmação na API/UI.
- Restauração de backup pela UI (com backup de segurança e confirmação): Parte 4. Hoje só existe `core/backup.restaurar_backup`, usada pela migração.
