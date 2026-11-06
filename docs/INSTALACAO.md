# Instalar e desinstalar o Finanças (Windows)

Guia para usar o app no modo desktop, sem ambiente de desenvolvimento. Para gerar o instalador a partir do código, veja o [`README.md`](../README.md#gerar-o-instalador-e-versões-novas).

## Resumo rápido
| Quero... | Faça |
|---|---|
| Instalar | dois cliques em `Financas_<versão>_x64-setup.exe` → **Mais informações** → **Executar assim mesmo** → Instalar |
| Atualizar | rode o instalador da versão nova por cima (os dados ficam) |
| Desinstalar mantendo os dados | Configurações do Windows → Aplicativos → **Financas** → Desinstalar |
| Remover tudo, inclusive os dados | desinstale e apague a pasta `%APPDATA%\Financas` |

## Requisitos
- Windows 10 (atualizado) ou Windows 11, 64 bits.
- **Não** precisa de administrador: o app é instalado só para o seu usuário.
- WebView2 Runtime: já vem no Windows 11 e no Windows 10 atualizado. Se faltar, o instalador baixa sozinho (precisa de internet nesse momento).
- Internet só para as cotações; sem internet o app abre e usa os últimos valores salvos (marcados como defasados).

## Onde conseguir o instalador
O arquivo se chama `Financas_<versão>_x64-setup.exe` (cerca de 37 MB). Quem gera o build encontra em:
```
apps\desktop\src-tauri\target\release\bundle\nsis\
```
Para instalar em outro computador, copie só esse arquivo (pendrive, nuvem, e-mail).

## Instalar
1. **Feche o Finanças**, se uma versão anterior estiver aberta.
2. Dê dois cliques em `Financas_<versão>_x64-setup.exe`.
3. **Aviso do SmartScreen** ("O Windows protegeu o computador"): aparece porque o instalador não tem assinatura de código. Clique em **Mais informações** → **Executar assim mesmo**.
4. Siga o instalador (em português) e clique em **Instalar**. Não aparece pedido de administrador.
5. No fim, deixe marcado **Executar Financas** ou abra pelo atalho criado no **menu Iniciar** e na **área de trabalho**.

O que o instalador faz:
| Item | Local |
|---|---|
| Programa (`financas.exe`, serviço interno `financas-backend\`, `uninstall.exe`) | `%LOCALAPPDATA%\Financas\` |
| Atalhos | menu Iniciar e área de trabalho |
| Registro para desinstalar | Configurações → Aplicativos (nome **Financas**) |

### Primeira abertura
Logo depois de instalar ou atualizar, o antivírus do Windows verifica os arquivos do serviço interno e a tela **"Iniciando o serviço interno…"** pode ficar **até uns 30 segundos**. É normal e só acontece na primeira vez; nas aberturas seguintes leva poucos segundos.

Na primeira abertura o banco é criado vazio em `%APPDATA%\Financas\`. Para trazer dados de outro computador, veja [Levar os dados para outro computador](#levar-os-dados-para-outro-computador).

### Conferir se deu certo
- O app abre na janela própria (não no navegador).
- **Configurações → Sobre** mostra a mesma versão para o app e para o serviço interno, sem aviso.

### Instalação silenciosa (opcional)
Para instalar sem telas, pelo Prompt de Comando:
```bat
Financas_1.0.0_x64-setup.exe /S
```

## Atualizar para uma versão nova
1. Feche o app.
2. Rode o instalador da versão nova, do mesmo jeito da instalação. Não precisa desinstalar antes.
3. Banco, backups, logs, tema e tamanho da janela são mantidos. Se a versão nova mudar o banco, o app faz um backup automático antes (em `%APPDATA%\Financas\backups\`, com `pre-migracao` no nome).
4. A primeira abertura depois de atualizar pode levar até uns 30 s (mesmo motivo da instalação).
5. Confira em **Configurações → Sobre** que as duas versões mostram o número novo.

> Não instale uma versão **mais antiga** por cima de uma mais nova se o banco já foi atualizado: o app recusa abrir um banco de versão mais nova (para não estragar os dados). Nesse caso, reinstale a versão mais nova ou restaure um backup feito na versão antiga.

## Desinstalar
**Antes:** se quiser guardar uma cópia dos dados fora deste computador, faça **Configurações → Backup e restauração → Fazer backup agora** e copie o `.db` de `%APPDATA%\Financas\backups\` para outro lugar.

1. **Feche o Finanças** (se ficar aberto, o desinstalador pede para fechar).
2. Abra **Configurações do Windows → Aplicativos → Aplicativos instalados** (no Windows 10: **Aplicativos e recursos**).
3. Procure **Financas**, clique em **⋯** (ou no nome) → **Desinstalar** e confirme.
   - Alternativas: **Painel de Controle → Programas e Recursos → Financas**, ou dois cliques em `%LOCALAPPDATA%\Financas\uninstall.exe`.
4. O desinstalador mostra uma caixa para **apagar os dados do aplicativo**. Ela remove **só** o tamanho/posição da janela e o cache do WebView2. **Seus dados financeiros não são apagados, marcando ou não.**

O que sai e o que fica:
| Some na desinstalação | Continua no computador |
|---|---|
| `%LOCALAPPDATA%\Financas\` (programa) | `%APPDATA%\Financas\` (banco, backups, logs) |
| atalhos do menu Iniciar e da área de trabalho | |
| entrada em Configurações → Aplicativos | |
| com a caixa marcada: `%APPDATA%\br.com.financas.desktop\` e `%LOCALAPPDATA%\br.com.financas.desktop\` | |

Por isso, **reinstalar depois abre com os mesmos dados**.

Desinstalação silenciosa (opcional):
```bat
"%LOCALAPPDATA%\Financas\uninstall.exe" /S
```

### Remover tudo (começar do zero)
Só faça isto se não precisa mais dos dados, ou depois de copiar um backup para fora:
1. Desinstale como acima.
2. No Explorador de Arquivos, digite `%APPDATA%` na barra de endereço e apague a pasta **Financas** (banco, backups e logs).
3. Opcional: apague também `%APPDATA%\br.com.financas.desktop` e `%LOCALAPPDATA%\br.com.financas.desktop`, se existirem.

> Apagar `%APPDATA%\Financas` **não tem volta**: os backups automáticos ficam dentro dessa pasta.

## Onde ficam os dados
| Pasta | Conteúdo |
|---|---|
| `%APPDATA%\Financas\financas.db` | banco com carteira, caixa, lançamentos e configurações |
| `%APPDATA%\Financas\backups\` | backups manuais e automáticos (antes de migrar e antes de restaurar; mantém os 10 mais recentes de cada) |
| `%APPDATA%\Financas\logs\` | `backend.log` (rotativo), `backend-stderr.log` e `backend-stderr.anterior.log` (erros na abertura), `backend-pronto.txt` |
| `%APPDATA%\br.com.financas.desktop\` | tamanho e posição da janela |

Nada é gravado na pasta de instalação: atualizar ou desinstalar não mexe nos seus dados.

## Levar os dados para outro computador
1. No computador antigo: **Configurações → Backup e restauração → Fazer backup agora** e copie o `.db` gerado (em `%APPDATA%\Financas\backups\`).
2. No novo: instale o app, abra uma vez e use **Configurações → Backup e restauração → Restaurar de um arquivo…** com o backup copiado. O app valida o arquivo e guarda um backup de segurança do banco atual antes de restaurar.

Não copie o `financas.db` com o app aberto: use sempre o backup do próprio app.

## Problemas comuns
| Sintoma | O que fazer |
|---|---|
| "O Windows protegeu o computador" | **Mais informações** → **Executar assim mesmo** (falta de assinatura de código, não é vírus) |
| Antivírus bloqueia ou apaga `financas-backend.exe` | falso positivo comum em executáveis do PyInstaller: libere o arquivo/pasta `%LOCALAPPDATA%\Financas` no antivírus e reinstale |
| Instalação para pedindo internet | é o download do WebView2. Conecte, ou instale antes o "WebView2 Evergreen Standalone Installer" (baixado da Microsoft em outro computador) |
| "Iniciando o serviço interno…" demora na 1ª abertura | aguarde até ~30 s; se aparecer erro, clique em **Tentar novamente** |
| Erro ao iniciar o serviço interno | clique em **Tentar novamente**. Persistindo, veja `%APPDATA%\Financas\logs\backend-stderr.log` e `backend.log` e reinstale por cima |
| Mensagem pedindo para reinstalar | a pasta `financas-backend` sumiu (antivírus ou exclusão): rode o instalador de novo |
| Aviso em Sobre: versões diferentes | a instalação ficou pela metade: feche o app e rode o instalador de novo |
| Abrir de novo só traz a janela para frente | é o esperado: o app roda uma instância só |
| Sobrou processo depois de fechar | não deveria; se o Gerenciador de Tarefas mostrar `financas-backend.exe` sem o `financas.exe`, finalize-o e avise o desenvolvedor com o `backend.log` |
| Cotações com aviso "defasado" | sem internet ou fonte fora do ar: o app usa o último valor salvo e tenta de novo sozinho; force em **Atualizar cotações** |
