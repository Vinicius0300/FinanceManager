# Finanças

App desktop local (Windows) de finanças pessoais: carteira de investimentos quase em tempo real e receitas/despesas mensais. Dados 100% locais em `%APPDATA%\Financas\`.

Stack: Tauri 2 (Rust mínimo) + React/TypeScript (Vite, Tailwind, shadcn/ui) + backend Python FastAPI como sidecar. Detalhes e decisões em [`docs/CONTEXTO.md`](docs/CONTEXTO.md).

## Pré-requisitos (Windows 10/11)
| Ferramenta | Versão | Observação |
|---|---|---|
| Rust (rustup) | stable | toolchain `x86_64-pc-windows-msvc` |
| Visual Studio Build Tools | 2022 ou mais novo | workload "Desenvolvimento para desktop com C++" (MSVC + Windows SDK) |
| Node.js | LTS (24) | versões ímpares funcionam, mas geram avisos |
| Python | 3.11 ou superior | acessível pelo comando `py` |
| WebView2 Runtime | atual | já vem no Windows 11 |
| Git | atual | |

### Instalação automática (recomendado)
1. Abra o **Prompt de Comando como administrador** na pasta do projeto e rode:
   ```bat
   scripts\1_instalar_ferramentas.bat
   ```
   Ele instala pelo `winget` só o que estiver faltando.
2. **Feche e abra um novo terminal** (para o PATH atualizar), sem precisar ser administrador:
   ```bat
   scripts\2_preparar_projeto.bat
   ```
   Cria `backend\.venv`, instala dependências Python e Node, gera o contrato e roda os testes.

### Instalação manual do Rust (se preferir)
1. `winget install --id Rustlang.Rustup -e` (ou o instalador de https://rustup.rs).
2. Reabra o terminal e rode `rustup default stable`.
3. Confira com `rustc --version` e `cargo --version`.

## Dia a dia
| Tarefa | Comando (na raiz) |
|---|---|
| Abrir o app em desenvolvimento (Vite + Tauri + backend com reload) | `npm run dev` |
| Só o front no navegador (sem backend; mostra a tela de erro) | `npm run web:dev` |
| Testes do backend | `cd backend; .venv\Scripts\python -m pytest` |
| Lint/tipos do backend | `cd backend; .venv\Scripts\ruff check .; .venv\Scripts\ruff format --check .; .venv\Scripts\mypy app entrypoint.py tests` |
| Testes do frontend | `npm test` |
| Lint, tipos e formatação do frontend | `npm run lint`, `npm run typecheck`, `npm run format:check` |
| Gerar contrato OpenAPI + tipos TS | `npm run contrato` |
| Conferir se o contrato está atualizado | `npm run contrato:verificar` |
| Checar o Rust sem abrir o app | `cd apps\desktop\src-tauri; cargo check` |

A primeira execução de `npm run dev` compila o Rust e leva alguns minutos; as seguintes são rápidas. Alterações no front recarregam na hora; alterações em `backend/app` reiniciam o backend automaticamente.

### Rodar o backend sozinho (depuração)
```powershell
cd backend
$env:FINANCAS_TOKEN = "<64 caracteres quaisquer>"; $env:FINANCAS_DEV = "1"
.venv\Scripts\python entrypoint.py --porta 8765 --reload
```
Swagger em http://127.0.0.1:8765/docs (use **Authorize** com o mesmo token).

## Onde ficam os dados
- `%APPDATA%\Financas\` : banco (a partir da Parte 2), `logs\backend.log`, `backups\`, `models\`.
- Nada é gravado na pasta de instalação.

## Contrato da API
`docs/openapi.json` e `apps/web/src/api/schema.ts` são **gerados**: nunca edite à mão. Mudou a API? Rode `npm run contrato` e commite os dois arquivos junto com a mudança.
