# Finanças

App desktop local (Windows) de finanças pessoais: carteira de investimentos quase em tempo real e receitas/despesas mensais. Dados 100% locais em `%APPDATA%\Financas\`.

Stack: Tauri 2 (Rust mínimo) + React/TypeScript (Vite, Tailwind, shadcn/ui) + backend Python FastAPI como sidecar. Detalhes e decisões em [`docs/CONTEXTO.md`](docs/CONTEXTO.md).

## Baixar o app (só para usar)
**[⬇ Baixar a versão mais recente](https://github.com/Vinicius0300/FinanceManager/releases/latest)**: na página, em **Assets**, baixe o `Financas_<versão>_x64-setup.exe` (~38 MB).

- Não precisa clonar o repositório nem instalar Python, Node ou Rust: tudo vai dentro do instalador. Instalado, o app ocupa cerca de 90 MB.
- Windows 10/11 64 bits, sem administrador. No aviso do SmartScreen: **Mais informações** → **Executar assim mesmo** (o instalador não tem assinatura de código).
- Para atualizar, baixe o instalador novo pelo mesmo link e instale por cima: os dados ficam.
- Passo a passo completo em [`docs/INSTALACAO.md`](docs/INSTALACAO.md).

As seções abaixo são para quem vai **desenvolver** o app.

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
| Testes do backend com cobertura | `cd backend; .venv\Scripts\python -m pytest --cov` |
| Aplicar migrações do banco à mão (o app já faz isso ao abrir) | `cd backend; .venv\Scripts\alembic upgrade head` |
| Criar migração depois de mudar um model | `cd backend; .venv\Scripts\alembic revision --autogenerate -m "descricao"` (revise o arquivo gerado) |
| Lint/tipos do backend | `cd backend; .venv\Scripts\ruff check .; .venv\Scripts\ruff format --check .; .venv\Scripts\mypy app entrypoint.py tests` |
| Testes do frontend | `npm test` |
| Lint, tipos e formatação do frontend | `npm run lint`, `npm run typecheck`, `npm run format:check` |
| Gerar contrato OpenAPI + tipos TS | `npm run contrato` |
| Conferir se o contrato está atualizado | `npm run contrato:verificar` |
| Checar o Rust sem abrir o app | `cd apps\desktop\src-tauri; cargo check` (testes: `cargo test`) |
| Gerar o instalador (com todas as checagens) | `npm run instalador` (ou dê dois cliques em `scripts\3_gerar_instalador.bat`) |
| Sincronizar / conferir a versão | `npm run versao` / `npm run versao:verificar` |

A primeira execução de `npm run dev` compila o Rust e leva alguns minutos; as seguintes são rápidas. Alterações no front recarregam na hora; alterações em `backend/app` reiniciam o backend automaticamente.

### Rodar o backend sozinho (depuração)
```powershell
cd backend
$env:FINANCAS_TOKEN = "<64 caracteres quaisquer>"; $env:FINANCAS_DEV = "1"
.venv\Scripts\python entrypoint.py --porta 8765 --reload
```
Swagger em http://127.0.0.1:8765/docs (use **Authorize** com o mesmo token).
A atualização automática de cotações começa ao abrir; para depurar sem acessar a internet, defina também `$env:FINANCAS_SEM_ATUALIZACAO = "1"` (a atualização forçada pela API continua funcionando).

### Atualização de cotações
- Ações e cripto: a cada 1 a 15 min (padrão 5; `PUT /api/configuracoes`). Fora do pregão, ações só até pegar o fechamento.
- Selic, CDI, IPCA, PTAX, Tesouro Direto e fundos: uma vez por dia.
- Forçar agora: botão **Atualizar cotações** no topo do app (em qualquer tela) ou `POST /api/cotacoes/atualizar`. Status por ativo: `GET /api/cotacoes/status` (resumido no chip "N em dia · N defasadas · N com erro" do topo). Eventos em tempo real: `GET /api/eventos` (SSE).
- Na primeira vez são baixados os fechamentos de até 1 ano (fundos: até 12 arquivos de ~12 MB da CVM, processados e descartados).

### Receitas, despesas e transferências
- Todo lançamento de **Receitas e Despesas** pertence a uma instituição e movimenta o caixa dela. Lance primeiro as receitas do mês e depois as despesas: o caixa nunca fica negativo, e uma despesa sem saldo pede um ajuste de saldo.
- **Salário é receita; dinheiro passado entre bancos é transferência** (Movimentações → Caixa → Transferência). Depósito e saque ficam para o saldo inicial e acertos com o extrato. Cartão de crédito: lance a despesa na data da cobrança, na instituição que pagou.

### Rebalanceamento
- Aba **Rebalanceamento** no menu: defina metas por classe (somando 100%) e, se quiser, pesos para os ativos de uma classe. A tela mostra o desvio de cada classe, as que estão fora da banda (tolerância de 5 p.p., ajustável) e como dividir o aporte (pré-preenchido com o caixa). O modo **Completo (com vendas)** mostra também o que vender, com lucro estimado; o app não calcula IR e nunca executa ordens.

### Glossário
- Aba **Glossário** no menu: grafo de termos de finanças e investimentos. Clique numa bolinha, busque pelo nome ou use a lista para abrir a explicação, com exemplo numérico e termos relacionados.
- O conteúdo é fixo e vem dentro do app (um arquivo por termo em `apps/web/src/features/glossario/conteudo/*.md`); não é editável pela tela. Para acrescentar um termo, crie o `.md` no modelo dos outros, ligue com `[[slug]]` e rode `npm test` (a validação aponta link quebrado, seção faltando ou tamanho fora do modelo). Detalhes em `docs/HISTORICO.md` (Parte 7).

## Instalar e usar o app (sem ambiente de desenvolvimento)
Passo a passo de instalação, atualização, desinstalação e problemas comuns em [`docs/INSTALACAO.md`](docs/INSTALACAO.md). Em resumo:
- **Baixar:** [página da versão mais recente](https://github.com/Vinicius0300/FinanceManager/releases/latest), em **Assets**.
- **Instalar:** rode `Financas_<versão>_x64-setup.exe` (sem administrador; no aviso do SmartScreen, **Mais informações** → **Executar assim mesmo**). A 1ª abertura pode levar até ~30 s.
- **Atualizar:** rode o instalador novo por cima; os dados ficam.
- **Desinstalar:** Configurações do Windows → Aplicativos → **Financas**. Os dados em `%APPDATA%\Financas\` **nunca** são apagados pelo desinstalador.

## Gerar o instalador e versões novas
- `npm run instalador` (ou `scripts\3_gerar_instalador.bat`, que espera uma tecla no fim) gera o instalador do zero. Antes do build ele sincroniza e confere a versão e roda os testes e lints do backend e do front, o contrato, o `cargo check`/`cargo test`, o PyInstaller e um smoke test do executável (inclui um download HTTPS real; sem internet, use `scripts\3_gerar_instalador.bat --sem-https`). Para no primeiro erro, com a mensagem.
- Resultado: `apps\desktop\src-tauri\target\release\bundle\nsis\Financas_<versão>_x64-setup.exe` (caminho, tamanho e versão aparecem no fim). O build final do Tauri roda em `%LOCALAPPDATA%\FinancasBuild\target`, fora do OneDrive (a sincronização bloqueava a cópia do backend com "Acesso negado"); o script copia o instalador de volta para esse caminho.
- **Versão nova (ex.: 1.0.1):** mude só o `"version"` do `package.json` da raiz e rode `npm run instalador`. Os demais arquivos (workspaces, `package-lock.json`, Cargo, `__version__` do backend e `docs/openapi.json`) são atualizados pelo `npm run versao`, que o script já roda. Commite os arquivos alterados.

### Publicar uma versão no GitHub (para o link de download)
Feito à mão no site, só quando houver versão nova (não há build automático no GitHub: o instalador publicado é o gerado e testado aqui).
1. Mude o `"version"` do `package.json` da raiz (ex.: `1.0.0` → `1.1.0`), rode `npm run instalador` e confira o app instalado (roteiro curto: instalar por cima, abrir, **Configurações → Sobre** com a versão nova nas duas linhas, dados preservados).
2. Commite e envie (`git push`) os arquivos alterados.
3. No GitHub: **Releases → Draft a new release** (ou `https://github.com/Vinicius0300/FinanceManager/releases/new`).
   - **Choose a tag:** digite `v1.1.0` (mesmo número do `package.json`, com `v` na frente) → **Create new tag** sobre a branch `main`.
   - **Release title:** `Finanças 1.1.0`.
   - **Descrição:** o que mudou para quem usa (novidades, correções e, se houver, "o banco é atualizado sozinho, com backup antes").
   - **Attach binaries:** arraste `apps\desktop\src-tauri\target\release\bundle\nsis\Financas_1.1.0_x64-setup.exe`. Só esse arquivo; o GitHub acrescenta sozinho os `.zip`/`.tar.gz` do código.
   - Deixe marcado **Set as the latest release** e clique em **Publish release**.
4. Confira: abra o link [releases/latest](https://github.com/Vinicius0300/FinanceManager/releases/latest) numa janela anônima; deve mostrar a versão nova com o `.exe` em **Assets**.

Errou algo? Edite a release (trocar o `.exe`: apague o anexo e envie de novo). Para retirar uma versão com problema, apague a release e a tag (**Tags** → tag → **Delete**); o link passa a apontar para a anterior. Nunca reaproveite o número de uma versão já publicada: gere a próxima (ex.: `1.1.1`).

## Onde ficam os dados
- `%APPDATA%\Financas\` : banco `financas.db`, `logs\backend.log`, `logs\backend-stderr.log` (erros do serviço interno antes de o log existir, novo a cada abertura; o da abertura anterior fica em `logs\backend-stderr.anterior.log`), `logs\backend-pronto.txt` (marca de que o executável instalado já iniciou, para usar o limite de espera curto), `backups\` (cópia automática antes de cada migração e antes de restaurar, além dos backups manuais) e `models\`.
- Nada é gravado na pasta de instalação.
- **Apagar os dados à mão** (depois de desinstalar, para começar do zero): feche o app e apague a pasta `%APPDATA%\Financas` (digite `%APPDATA%` na barra do Explorador). Isso apaga o banco e os backups: copie antes um backup para outro lugar se quiser guardar algo.
- Para testar com um banco descartável, defina `FINANCAS_DATA_DIR` com outra pasta antes de rodar o backend ou o `alembic`.

## Migrar para outro computador
**A) Só usar o app**
1. No computador antigo: **Configurações → Backup e restauração → Fazer backup agora** e copie o arquivo `.db` gerado (fica em `%APPDATA%\Financas\backups\`) para um pendrive ou nuvem.
2. No novo: instale o app (seção acima), abra-o uma vez e, em **Configurações → Backup e restauração → Restaurar de um arquivo…**, escolha o backup copiado. O app valida o arquivo, guarda um backup de segurança do banco atual e restaura carteira, caixa, lançamentos e configurações.

**B) Continuar desenvolvendo**
1. Instale o Git e clone o repositório.
2. Rode `scripts\1_instalar_ferramentas.bat` **como administrador**.
3. **Feche e reabra o terminal** e rode `scripts\2_preparar_projeto.bat` (venv, dependências, contrato e testes).
4. `npm run dev` para desenvolver; `npm run instalador` para gerar o instalador. Para levar os dados, use o caminho A (backup e restauração).

## Documentação
- [`docs/CONTEXTO.md`](docs/CONTEXTO.md): visão, roadmap e regras vigentes (resumo).
- [`docs/HISTORICO.md`](docs/HISTORICO.md): decisões por parte, com motivos, medições e validações.
- [`docs/INSTALACAO.md`](docs/INSTALACAO.md): instalar, atualizar e desinstalar o app.
- [`docs/CALCULOS.md`](docs/CALCULOS.md): regras de cálculo (preço médio, caixa, renda fixa, poupança...).
- [`docs/TIPOS_DE_ATIVO.md`](docs/TIPOS_DE_ATIVO.md): registry de tipos de ativo, providers de cotação e como criar um tipo novo.
- [`docs/ANALYTICS.md`](docs/ANALYTICS.md): plano da futura camada de previsão e sugestões.

## Contrato da API
`docs/openapi.json` e `apps/web/src/api/schema.ts` são **gerados**: nunca edite à mão. Mudou a API? Rode `npm run contrato` e commite os dois arquivos junto com a mudança. Os testes do backend falham se o `docs/openapi.json` estiver desatualizado (`tests/test_contrato.py`).
