---
name: build-instalador-windows
description: Gera ou regera o instalador do app Finanças para Windows (.exe NSIS via Tauri, backend empacotado com PyInstaller como sidecar), decide a versão, roda o build com todas as checagens, corrige falhas comuns, valida o app instalado e prepara a Release do GitHub; também mantém os scripts de build e de migração para outro computador. Use sempre que o usuário pedir para gerar/atualizar/refazer o executável ou o instalador, falar em build, release, nova versão, empacotar, PyInstaller, sidecar, SmartScreen, máquina limpa, migrar de computador ou scripts .bat de preparação do ambiente.
---

# Build do instalador (Windows)

Tudo já está automatizado em `scripts\3_gerar_instalador.bat` (`npm run instalador` = `--sem-pausa`).
A skill existe para **não redescobrir** o caminho: siga a rotina, consulte "Falhas conhecidas" se algo
parar, e acrescente aqui qualquer falha nova que aparecer (sintoma → causa → correção).

## Rotina: regerar o executável

### 1. Antes de começar (1 minuto)
- `git status` limpo (ou o usuário sabe o que vai entrar no build). O build usa o working tree, não o último commit.
- Feche o Finanças instalado e qualquer `financas-backend.exe` (`tasklist | findstr /i financas`):
  com eles abertos a etapa 8 não consegue apagar a cópia antiga do backend.
- Memória: com menos de ~3 GB de commit livre (`Get-CimInstance Win32_OperatingSystem` → `FreeVirtualMemory`)
  o vitest e o PyInstaller podem cair por falta de memória; avise o dono antes (fechar navegador ajuda).
- Veja a versão atual (`"version"` do `package.json` da raiz), as tags (`git tag`) e o instalador
  anterior em `apps\desktop\src-tauri\target\release\bundle\nsis\`.

### 2. Versão (pergunte ao dono, com recomendação)
- Fonte única: só o `"version"` do `package.json` da raiz é editado à mão; a etapa 1 do script propaga
  (workspaces, `package-lock.json`, Cargo, `backend/app/__init__.py`, `docs/openapi.json`).
- Sugestão semver: funcionalidade nova desde o último instalador → sobe o **meio** (1.0.0 → 1.1.0);
  só correções → sobe o **último** (1.1.0 → 1.1.1); manter o número só se nada foi publicado com ele.
- **Nunca reaproveite** um número que já virou Release no GitHub (`git tag` / página de Releases).
- Mudar a versão **não** muda o schema: o banco do usuário só migra se houver migração Alembic nova.

### 3. Rodar o build (≈ 6 min com cache do Rust; +3 min na 1ª vez; em segundo plano)
Pela ferramenta PowerShell, em background, com log no scratchpad. **O redirecionamento tem de ser
feito pelo `cmd`, dentro das aspas** (com `*>` do PowerShell 5.1 o host estoura com
`System.OutOfMemoryException` na etapa 4, durante o vitest):
```powershell
$log="<scratchpad>\build.log"; cmd /c "scripts\3_gerar_instalador.bat --sem-pausa > `"$log`" 2>&1"; "EXIT=$LASTEXITCODE"
```
- Sem internet: acrescente `--sem-https` (pula o download real do smoke test).
- Etapas (o log marca `=== [n/8] ... ===`): 1 versão · 2 backend (pytest, ruff, ruff format, mypy) ·
  3 contrato OpenAPI · 4 front (vitest, eslint, tsc, prettier) · 5 Rust (`cargo check`/`test`) ·
  6 PyInstaller (`onedir`) · 7 smoke test do `.exe` do backend · 8 `tauri build` (NSIS).
- Para descobrir onde parou: `grep -n "=== \[\|\[ERRO\]" build.log` e leia as ~40 linhas antes do erro.
- Ao corrigir, prefira rodar **só a checagem que falhou** (comandos na tabela do `CLAUDE.md`) e depois o
  script inteiro de novo (ele é idempotente).

### 4. Conferir o resultado
- Fim do log: caminho, versão e tamanho. Saída: `apps\desktop\src-tauri\target\release\bundle\nsis\Financas_<versão>_x64-setup.exe`
  (cópia do gerado em `%LOCALAPPDATA%\FinancasBuild\target\release\bundle\nsis\`).
- Tamanho esperado ≈ 36–40 MB (1.1.0: 36,8 MB; 1.0.0: 38,5 MB). Contagens de referência na 1.1.0:
  668 testes backend, 452 front, 12 Rust — número bem menor indica testes não coletados.
  O aviso do Vite sobre `chunkSizeWarningLimit` na etapa 8 é esperado. Muito maior → alguma dependência pesada (ML) entrou no PyInstaller; muito
  menor → backend não foi incluído como recurso.
- O smoke test (etapa 7) já provou: o `.exe` do backend sobe, responde `/health` com a versão nova,
  `/api/ping` com token, migrações até `head` num banco vazio, HTTPS (`truststore`) e encerra limpo.

### 5. Validação do app instalado
- **O terminal do Claude desktop roda dentro de um pacote MSIX:** instalar daqui grava a pasta de
  instalação num `AppData` virtualizado. Não instale o app "de verdade" por aqui; se precisar testar,
  use `FINANCAS_DATA_DIR` numa pasta temporária (nunca toque no `%APPDATA%\Financas` do dono) e
  desinstale a cópia de teste no fim.
- Entregue ao dono o roteiro curto para ele rodar fora do terminal:
  1. Feche o Finanças; rode o `.exe` novo por cima (SmartScreen: **Mais informações → Executar assim mesmo**).
  2. Abra pelo atalho; a 1ª abertura após atualizar pode levar até ~30 s (Defender varrendo o backend).
  3. **Configurações → Sobre**: versão nova nas duas linhas (app e serviço interno).
  4. Carteira, movimentações e lançamentos continuam lá; se houve migração, há backup novo em `%APPDATA%\Financas\backups\`.
  5. Feche o app e confira que não sobrou `financas-backend.exe` no Gerenciador de Tarefas.

### 6. Depois do build
- Commite os arquivos que a sincronização de versão alterou (`package.json`, `package-lock.json`,
  `apps/*/package.json`, `Cargo.toml`, `Cargo.lock`, `backend/app/__init__.py`, `docs/openapi.json`) —
  só quando o dono pedir. O `.exe` **nunca** vai para o git (`target/` é ignorado).
- Atualize `docs/CONTEXTO.md` (linha "Versão atual") e, se algo novo foi decidido ou corrigido no build,
  uma entrada em `docs/HISTORICO.md` e uma linha em "Falhas conhecidas" abaixo.
- Publicação: Release manual no GitHub, tag `vX.Y.Z`, só o `.exe` anexado. Passo a passo em
  `README.md` → "Publicar uma versão no GitHub". Publicar é ação externa: só com o "sim" do dono.

## Falhas conhecidas
| Sintoma | Causa | Correção |
|---|---|---|
| `System.OutOfMemoryException` em `cmd.exe`, EXIT=-1, log parado no vitest (etapa 4) | Saída capturada pelo PowerShell 5.1 (`*>`/pipe) | Redirecionar dentro do `cmd /c "... > log 2>&1"` (ver passo 3) |
| Etapa 4: vitest com `JavaScript heap out of memory` / `Worker exited unexpectedly` (exit 134, 3) | Pouca memória de commit livre (Chrome etc.) e um worker com jsdom por núcleo | O script já roda `npm test -- --maxWorkers=4`; se persistir, baixe para 2 ou peça ao dono para fechar programas pesados. Confira antes: `Get-CimInstance Win32_OperatingSystem` (`FreeVirtualMemory`) |
| Etapa 8: `Acesso negado. (os error 5)` copiando `financas-backend` | OneDrive segura arquivos recém-gravados no `target` do projeto | Já resolvido: etapa 8 usa `CARGO_TARGET_DIR=%LOCALAPPDATA%\FinancasBuild\target`. Se voltar, confira se a variável não foi sobrescrita |
| Etapa 8: "Não foi possível apagar ...\financas-backend" | App ou `financas-backend.exe` aberto | Fechar o app / `taskkill /im financas-backend.exe /f` e rodar de novo |
| Etapa 1: versão divergente | Alguém editou número fora do `package.json` da raiz (ou `tauri.conf.json`/`pyproject.toml` ganharam número próprio) | Voltar a usar só o `package.json` da raiz; `npm run versao` |
| Etapa 3: contrato desatualizado | API mudou sem `npm run contrato` | `npm run contrato`, revisar o diff de `docs/openapi.json` e `apps/web/src/api` |
| Etapa 4: `format:check` falha | Arquivo sem prettier | `npm run format` e conferir o diff |
| Etapa 7: falha no HTTPS | Sem internet ou fonte fora do ar | Rodar com `--sem-https` e registrar; não é defeito do executável se o resto passou |
| 1ª compilação Rust em release lenta (~3 min) | Cache novo em `%LOCALAPPDATA%\FinancasBuild` | Normal; as seguintes usam o cache |

## Referência (decisões já tomadas; detalhes em `docs/HISTORICO.md`)
- PyInstaller **`onedir`** (spec `backend/financas-backend.spec`), sidecar como recurso `financas-backend/`
  pelo `tauri.instalador.conf.json` (passado com `--config` só no build do instalador). `onefile` só para
  medir (`FINANCAS_EMPACOTAMENTO=onefile`). Dependências de ML ficam fora.
- NSIS pt-BR, `installMode: currentUser` (sem admin, instala em `%LOCALAPPDATA%\Financas`), atalhos no
  menu Iniciar e na área de trabalho, WebView2 por `embedBootstrapper`, sem assinatura (SmartScreen).
- Desinstalar/atualizar **nunca** apaga `%APPDATA%\Financas` (banco, logs, backups).
- `TIMEOUT_INICIO` do Rust 120 s (1ª abertura após instalar ≈ 30 s).

## Scripts de migração para outro PC
- `scripts/1_instalar_ferramentas.bat` (administrador): winget para Git, Node LTS, Python 3.11, Rustup,
  WebView2 Runtime e VS Build Tools (C++). `scripts/2_preparar_projeto.bat`: `rustup default stable`,
  venv, dependências Python e Node, cliente TS, testes. Reabrir o terminal entre um e outro.
- Todo `.bat`: idempotente, caminhos relativos à raiz (`cd /d "%~dp0.."`), mensagens em pt-BR, para no
  primeiro erro. `.gitignore` nunca versiona `*.db`, backups, `node_modules`, `target`, `.venv`, `dist`.
- Validação em máquina limpa (VM) e backup/restauração entre duas instalações: roteiro em
  `docs/INSTALACAO.md` e `README.md` ("Migrar para outro computador").
