---
name: build-instalador-windows
description: Empacota o app Finanças para Windows (backend com PyInstaller como sidecar, instalador NSIS/MSI via Tauri), valida o app instalado e mantém os scripts de build e de migração para outro computador. Use sempre que o usuário falar em build, instalador, release, empacotar, PyInstaller, sidecar, SmartScreen, máquina limpa, migrar de computador ou scripts .bat de preparação do ambiente.
---

# Build do instalador e portabilidade (Windows)

## Backend com PyInstaller
1. Compare `onefile` (extrai a cada abertura, inicia mais devagar) e `onedir` (inicia mais rápido, entra como resource do Tauri). **Meça** o tempo até `/health` responder, várias execuções, com e sem cache frio, e registre os números em `docs/CONTEXTO.md` junto com a recomendação.
2. O binário do sidecar segue a convenção de nome por **target triple** do Tauri (ex.: `...-x86_64-pc-windows-msvc.exe`).
3. Inclua no spec do PyInstaller as migrações Alembic e demais arquivos de dados; dependências pesadas de ML ficam **fora** (opcionais).

## Instalador (Tauri)
- NSIS ou MSI com ícone, **atalho na área de trabalho** e **bootstrapper do WebView2** quando ausente.
- Sem assinatura de código o Windows mostra o aviso do **SmartScreen**: documente no README como contornar ("Mais informações" → "Executar assim mesmo") e que a assinatura de código é o caminho definitivo.

## O app instalado precisa
- Abrir pelo ícone; usar `%APPDATA%\Financas\` para banco e logs; rodar migrações no primeiro uso (com backup prévio); **preservar dados** ao atualizar/reinstalar (o instalador nunca toca em `%APPDATA%`); não deixar processos órfãos ao fechar (inclusive fechamento abrupto).

## Script único de build (`scripts/`)
Gera o instalador do zero e, **antes**, executa: checagem do contrato OpenAPI (`contrato-openapi`, modo de checagem), testes do backend e do front, lint. Falhou algo → aborta com mensagem clara. Caminhos relativos à raiz do projeto.

## Scripts de migração para outro PC
- `scripts/1_instalar_ferramentas.bat` (como administrador): winget para Git, Node LTS, Python 3.11, Rustup, WebView2 Runtime e VS Build Tools (workload C++), com mensagens claras e tratamento de erro por etapa.
- `scripts/2_preparar_projeto.bat`: `rustup default stable`, venv do backend, dependências Python e Node, geração do cliente TS, testes.
- **Idempotentes** (rodar duas vezes não quebra), caminhos relativos, e reabrir o terminal entre um e outro para o PATH atualizar.
- `.gitignore` nunca versiona `*.db`, backups, `node_modules`, `target`, `.venv`, `dist`.

## Validação
- Checklist de teste em **máquina limpa** (VM): instalar, abrir, criar dados, fechar (conferir processos), atualizar por cima (dados preservados), desinstalar/reinstalar.
- **Backup e restauração entre duas instalações distintas**: gerar backup na A, restaurar na B, conferir carteira e lançamentos. Documente o resultado.
- Atualize `README.md` (seção "Migrar para outro computador": caminho A só usar o app; caminho B continuar desenvolvendo) e `docs/CONTEXTO.md` (build, releases, evolução futura: módulo de IA em `analytics/`, auto-update opcional).
