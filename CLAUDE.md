# Finanças: app desktop local de finanças pessoais (Windows)

App instalável (Tauri 2) para acompanhar carteira de investimentos quase em tempo real e registrar receitas e despesas mensais. Uso single-user, dados 100% locais (sem login, nuvem ou sincronização).
Visão completa, decisões e roadmap: **`docs/CONTEXTO.md`**. Leia-o antes de qualquer tarefa e atualize-o ao tomar decisões novas.

## Como trabalhar neste repositório
- O projeto avança em partes sequenciais validadas pelo dono. **Não adiante etapas** de partes futuras (ver roadmap em `docs/CONTEXTO.md`).
- Se algo for ambíguo (método de custo, tratamento de proventos, escopo), **pergunte antes de implementar**.
- Ao concluir uma entrega: código completo, comandos para rodar/testar, o que conferir e um roteiro curto de validação manual. Atualize `docs/CONTEXTO.md`.
- Responda e documente em **português (pt-BR)**: mensagens de erro ao usuário, docs, comentários explicativos. Identificadores de código seguem o padrão já existente no repositório (tabelas e domínio em português, ex.: `ativos`, `transacoes`, `lancamentos`).

## Stack (decisões definitivas)
- **Desktop:** Tauri 2 (WebView2). Rust mínimo: inicialização, ciclo de vida do sidecar, plugins (dialog, single-instance, window-state), configuração.
- **Frontend:** React 18 + TypeScript (strict) + Vite, Tailwind + shadcn/ui, React Router, TanStack Query/Table, Zustand, React Hook Form + Zod, ECharts (alocação, evolução, categorias), Lightweight Charts (séries de preço), Intl + date-fns, Vitest + Testing Library.
- **Backend:** Python 3.11+, FastAPI como sidecar local, SQLAlchemy 2.0 + Alembic, SQLite (WAL), pandas para séries, Pydantic v2, pytest, ruff, mypy.
- **Contrato:** OpenAPI do FastAPI gera `docs/openapi.json` e o cliente/tipos TypeScript em `apps/web/src/api`. Nunca editar o cliente gerado à mão.

## Estrutura
```
apps/desktop/src-tauri/   Rust, tauri.conf.json, capabilities, ícones
apps/web/src/{app,features,components,api,lib,theme}
backend/app/{api,domain,services,repositories,providers,asset_types,jobs,analytics,core}
backend/{migrations,tests,entrypoint.py}
docs/  scripts/
```

## Regras inegociáveis
**Dinheiro**
- Sempre `Decimal` no backend, nunca `float`. Arredondamento explícito e documentado.
- No front, valores monetários chegam como string/decimal e **não** sofrem aritmética em `number`; só formatação (pt-BR, Intl).

**Arquitetura**
- Regra de negócio só em `services/` e `domain/` (funções puras e testáveis). `repositories/` só acessam o banco, sem regra de negócio. `api/` só valida, orquestra e serializa.
- Tipos de ativo extensíveis via registry de handlers em `asset_types/`; novo tipo **não** pode exigir alterar os existentes.
- Fontes de cotação são classes separadas, com interface comum, registradas em registry (`providers/`).
- Dados do usuário ficam em `%APPDATA%\Financas\` (banco, logs, backups, models), centralizados em `core/paths`. Nunca na pasta de instalação.
- IA/previsão: só estrutura em `analytics/` (Protocols e registry). Dependências pesadas de ML permanecem **opcionais**; não inflar o executável.

**Segurança e robustez**
- API só em `127.0.0.1`, porta e token de sessão dinâmicos (gerados pelo Tauri). Token exigido em todas as rotas, exceto `/health`.
- CORS restrito a `http://tauri.localhost` e ao dev server. CSP com `connect-src` limitado a 127.0.0.1. Capabilities do Tauri no mínimo necessário.
- Nunca fixar URL base ou token no front: obter via `invoke`.
- Falhas de rede, de provider ou do backend **nunca derrubam o app**: log em arquivo (rotativo), estado de erro por ativo, demais atualizações continuam, mensagem compreensível em pt-BR.
- Encerramento limpo: sem processos órfãos (shutdown gracioso, depois kill; Job Object e/ou watchdog).
- Migrações Alembic rodam na inicialização, com backup prévio. Backup/restauração via API de backup do SQLite (nunca copiar arquivo aberto), com validação e backup de segurança antes de restaurar.
- Cotação indisponível: usar o último valor salvo e marcar como **defasado**. Origem do preço: `automatico`, `manual` ou `calculado`.

**Frontend**
- Nenhuma cor ou estilo fixo em componentes: tudo via tokens (CSS variables em `theme/`), com tema claro e escuro funcionando.
- Toda tela tem estados de carregamento, vazio e erro; a UI nunca trava durante atualização.
- Formulários com React Hook Form + Zod, mensagens em pt-BR, confirmação antes de exclusões e restauração.
- Acessibilidade: foco visível, labels, contraste dos tokens.

## Comandos principais
> Confirme os nomes exatos em `README.md`/`package.json` e ajuste esta seção se mudarem.

| Tarefa | Comando |
|---|---|
| Dev (front + Tauri + backend com reload) | `npm run tauri dev` (em `apps/desktop` ou na raiz, conforme o README) |
| Testes backend | `cd backend && pytest` |
| Lint/tipos backend | `cd backend && ruff check . && ruff format --check . && mypy app` |
| Testes frontend | `cd apps/web && npm run test` |
| Lint/format frontend | `cd apps/web && npm run lint && npm run format:check` |
| Migrações | `cd backend && alembic upgrade head` |
| Gerar contrato OpenAPI + cliente TS | script em `scripts/` (ver README); o build falha se estiver desatualizado |
| Build do instalador | script único em `scripts/` (checa contrato e testes antes) |
| Preparar nova máquina | `scripts/1_instalar_ferramentas.bat` (admin), reabrir o terminal, `scripts/2_preparar_projeto.bat` |

## Definição de pronto (qualquer mudança)
1. Testes relevantes passando (nenhum teste depende da internet: mocks de rede).
2. `ruff`, `mypy`, `eslint` e `prettier` limpos.
3. Se a API mudou: `docs/openapi.json` e o cliente TS regenerados e commitados.
4. Se houve mudança de schema: migração Alembic criada e testada.
5. `docs/CONTEXTO.md` atualizado com decisões novas; `README.md` se mudou algo do dia a dia.

## Git
- Nunca versionar: `*.db`, backups, `node_modules`, `target`, `.venv`, `dist`, logs.
- Scripts `.bat` devem ser idempotentes e usar caminhos relativos à pasta do projeto.

## Skills do projeto (`.claude/skills/`)
Procedimentos recorrentes estão em skills; use-as quando a tarefa casar: `entrega-por-partes`, `novo-tipo-de-ativo`, `novo-provider-cotacao`, `novo-endpoint-api`, `nova-migracao-alembic`, `nova-feature-frontend`, `contrato-openapi`, `calculo-financeiro-decimal`, `build-instalador-windows`.
