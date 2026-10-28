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
| 1 | Fundação: monorepo, Tauri + React + sidecar FastAPI, `/health` e rota protegida, encerramento limpo, instância única, estado da janela, contrato OpenAPI → TS, docs | **Entregue (aguardando validação)** |
| 2 | *Proposta:* modelo de dados (SQLite + SQLAlchemy + Alembic com backup prévio), domínio de carteira e lançamentos com `Decimal`, API CRUD | A definir pelo dono |
| 3 | *Proposta:* providers de cotação (registry), jobs de atualização, estado defasado, eventos em tempo real (SSE) | A definir pelo dono |
| 4 | *Proposta:* telas funcionais (Dashboard, Carteira, Movimentações, Receitas e Despesas, Configurações), gráficos, backup/restauração | A definir pelo dono |
| 5 | Visual final a partir das imagens de referência; empacotamento do backend (PyInstaller) e instalador | A definir pelo dono |

> O conteúdo das Partes 2 a 4 é uma proposta inicial e pode ser reordenado pelo dono.

## 3. Decisões de arquitetura (definitivas)
- **Desktop:** Tauri 2 (WebView2). Rust mínimo: inicialização, ciclo de vida do backend, plugins (dialog, single-instance, window-state) e configuração.
- **Frontend:** React 18 + TypeScript strict + Vite, Tailwind CSS 4 + shadcn/ui, React Router, TanStack Query, Zustand.
- **Backend:** Python 3.11+ com FastAPI, rodando como sidecar local (uvicorn).
- **Banco (a partir da Parte 2):** SQLite (WAL) + SQLAlchemy 2.0 + Alembic em `%APPDATA%\Financas\`.
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
  app/api                     rotas (só validam/orquestram/serializam)
  app/core                    config, paths, logs, segurança, erros, watchdog
  app/{domain,services,repositories,providers,asset_types,jobs,analytics}
                              camadas reservadas (só __init__ com a responsabilidade)
  tests/
docs/                         CONTEXTO.md, openapi.json
scripts/                      contrato.py, 1_instalar_ferramentas.bat, 2_preparar_projeto.bat
```
`backend/migrations/` será criado na Parte 2, junto com o primeiro modelo.

## 6. Convenções
- Idioma: pt-BR em mensagens ao usuário, docs e comentários; identificadores de domínio em português.
- **Erros da API:** sempre `{"codigo", "mensagem", "detalhes"?}` em pt-BR (`app/core/errors.py`); sem stack trace para o cliente. Exceção de aplicação: `AplicacaoError(status, codigo, mensagem)`.
- **operation_id** = nome da função da rota (nomes estáveis no cliente TS).
- **Dados do usuário:** só via `app/core/paths.py` (`%APPDATA%\Financas\`, sobrescrevível por `FINANCAS_DATA_DIR` nos testes).
- **Logs:** `%APPDATA%\Financas\logs\backend.log`, rotativo (1 MB × 5). No modo reload, o supervisor loga só no console.
- **Front:** sem cores fixas em componentes (tokens em `theme/index.css`, incluindo `sucesso`, `aviso`, `perigo`); toda tela com carregando/vazio/erro; falhas viram texto via `mensagemDeErro`.
- **Tema:** **escuro por padrão**; só dois modos (escuro e claro), alternados por um switch no topo (`components/SeletorTema.tsx`, ligado = escuro). A escolha fica no `localStorage` da janela (`financas-tema`, Zustand persist). O `index.html` já nasce com `class="dark"` para não piscar claro na abertura. Não há modo "igual ao sistema" (decisão do dono, Parte 1).
- **Cliente da API:** `openapi-fetch` tipado por `schema.ts`; obtido com `useClienteApi()` (só existe depois que o portão liberou a UI).
- **Testes:** nenhum depende da internet; backend com `TestClient` e pasta de dados temporária; front com Vitest + Testing Library e `fetch` falso.

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

## 8. Pendências conhecidas
- Build de release ainda não inclui o backend empacotado (Parte 5): `tauri build` gera o app, mas ele mostrará "Executável do serviço interno não encontrado".
- Atualização por cima, assinatura de código e SmartScreen: Parte 5.
