@echo off
rem ============================================================================
rem  Financas - 1/2: instala as ferramentas de desenvolvimento (Windows).
rem  Execute COMO ADMINISTRADOR. Idempotente: o que ja estiver instalado e pulado.
rem  Depois de terminar, FECHE e reabra o terminal e rode 2_preparar_projeto.bat.
rem ============================================================================
setlocal EnableExtensions
chcp 65001 >nul

net session >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Execute este script como administrador ^(botão direito ^> Executar como administrador^).
  goto :falha
)
where winget >nul 2>&1
if errorlevel 1 (
  echo [ERRO] winget não encontrado. Instale o "Instalador de Aplicativo" pela Microsoft Store.
  goto :falha
)

echo.
echo === [1/6] Git ===
where git >nul 2>&1 && (echo Já instalado.) || call :winget Git.Git || goto :falha

echo.
echo === [2/6] Node.js LTS ===
where node >nul 2>&1 && (
  for /f %%v in ('node --version') do echo Já instalado: %%v. Recomendado: versão LTS ^(par, ex.: v24^).
) || call :winget OpenJS.NodeJS.LTS || goto :falha

echo.
echo === [3/6] Python 3.11+ ===
call :tem_python && (echo Já instalado.) || call :winget Python.Python.3.13 || goto :falha

echo.
echo === [4/6] Rust ^(rustup^) ===
where rustup >nul 2>&1 && (echo Já instalado.) || (
  if exist "%USERPROFILE%\.cargo\bin\rustup.exe" (echo Já instalado ^(reabra o terminal para o PATH^).) else (call :winget Rustlang.Rustup || goto :falha)
)

echo.
echo === [5/6] WebView2 Runtime ===
reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1 && (echo Já instalado.) || call :winget Microsoft.EdgeWebView2Runtime || goto :falha

echo.
echo === [6/6] Visual Studio Build Tools ^(C++ / MSVC^) ===
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set "TEM_MSVC="
if exist "%VSWHERE%" (
  for /f "usebackq delims=" %%i in (`"%VSWHERE%" -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "TEM_MSVC=1"
)
if defined TEM_MSVC (
  echo Já instalado.
) else (
  echo Instalando ^(pode levar vários minutos^)...
  winget install --id Microsoft.VisualStudio.2022.BuildTools -e --accept-package-agreements --accept-source-agreements --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
  if errorlevel 1 goto :falha
)

echo.
echo ============================================================================
echo  Ferramentas prontas. FECHE este terminal, abra um novo e rode:
echo    scripts\2_preparar_projeto.bat
echo ============================================================================
pause
exit /b 0

:winget
echo Instalando %1...
winget install --id %1 -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo [ERRO] Falha ao instalar %1 pelo winget.
  exit /b 1
)
exit /b 0

:tem_python
for %%v in (3.13 3.12 3.11) do (
  py -%%v --version >nul 2>&1 && exit /b 0
)
exit /b 1

:falha
echo.
echo [ERRO] A instalação parou. Leia a mensagem acima, corrija e rode o script de novo.
pause
exit /b 1
