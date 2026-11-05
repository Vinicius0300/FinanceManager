@echo off
rem ============================================================================
rem  Financas - 3: gera o instalador do zero (Windows, NSIS).
rem  Antes do build confere versão, testes, lint, contrato e Rust; para no
rem  primeiro erro. Idempotente e com caminhos relativos à pasta do projeto.
rem
rem  Uso:  scripts\3_gerar_instalador.bat [--sem-pausa] [--sem-https]
rem        npm run instalador   (= --sem-pausa)
rem    --sem-pausa  não espera uma tecla no fim (chamado pelo npm/CI)
rem    --sem-https  pula o download HTTPS real do smoke test (sem internet)
rem
rem  Nova versão (ex.: 1.0.1): mude só o "version" do package.json da raiz e
rem  rode este script; a versão é sincronizada nos demais arquivos.
rem ============================================================================
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0.."
set "PYTHONUTF8=1"

set "SEM_PAUSA="
set "HTTPS=--https"
:argumentos
if "%~1"=="" goto :inicio
if /i "%~1"=="--sem-pausa" set "SEM_PAUSA=1"
if /i "%~1"=="--sem-https" set "HTTPS="
shift
goto :argumentos

:inicio
set "PY=backend\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERRO] Ambiente do backend não encontrado. Rode scripts\2_preparar_projeto.bat.
  goto :falha
)

echo.
echo === [1/8] Versão: sincronizar a partir do package.json e conferir ===
"%PY%" scripts\versao.py || goto :falha

echo.
echo === [2/8] Backend: testes, ruff e mypy ===
pushd backend
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider || goto :falha_pop
.venv\Scripts\ruff check . || goto :falha_pop
.venv\Scripts\ruff format --check . || goto :falha_pop
.venv\Scripts\mypy app entrypoint.py tests || goto :falha_pop
popd

echo.
echo === [3/8] Contrato OpenAPI e tipos TypeScript ===
call npm run contrato:verificar || goto :falha

echo.
echo === [4/8] Frontend: testes, lint, tipos e formatação ===
call npm test || goto :falha
call npm run lint || goto :falha
call npm run typecheck || goto :falha
call npm run format:check || goto :falha

echo.
echo === [5/8] Rust: cargo check e cargo test ===
pushd apps\desktop\src-tauri
cargo check || goto :falha_pop
cargo test || goto :falha_pop
popd

echo.
echo === [6/8] Backend empacotado (PyInstaller) ===
"%PY%" scripts\empacotar_backend.py || goto :falha

echo.
echo === [7/8] Smoke test do executável do backend ===
"%PY%" scripts\smoke_backend.py apps\desktop\src-tauri\binaries\financas-backend\financas-backend.exe %HTTPS% || goto :falha

echo.
echo === [8/8] Instalador (tauri build) ===
call npm run tauri -- build --config src-tauri/tauri.instalador.conf.json || goto :falha

set "VERSAO="
for /f "usebackq delims=" %%v in (`"%PY%" scripts\versao.py --imprimir`) do set "VERSAO=%%v"
if not defined VERSAO (
  echo [ERRO] Não foi possível ler a versão do package.json.
  goto :falha
)
set "INSTALADOR=apps\desktop\src-tauri\target\release\bundle\nsis\Financas_%VERSAO%_x64-setup.exe"
if not exist "%INSTALADOR%" (
  echo [ERRO] Instalador não encontrado em %INSTALADOR%.
  goto :falha
)
for %%f in ("%INSTALADOR%") do set "TAMANHO=%%~zf"
set /a TAMANHO_MB=%TAMANHO% / 1048576

echo.
echo ============================================================================
echo  Instalador gerado:
echo    %CD%\%INSTALADOR%
echo    Versão %VERSAO%, %TAMANHO_MB% MB ^(%TAMANHO% bytes^)
echo ============================================================================
if not defined SEM_PAUSA pause
exit /b 0

:falha_pop
popd

:falha
echo.
echo [ERRO] A geração do instalador parou. Leia a mensagem acima, corrija e rode de novo.
if not defined SEM_PAUSA pause
exit /b 1
