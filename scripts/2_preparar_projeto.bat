@echo off
rem ============================================================================
rem  Financas - 2/2: prepara o projeto (venv do backend, dependencias, contrato
rem  e testes). Pode ser executado quantas vezes quiser (idempotente).
rem  Pre-requisito: scripts\1_instalar_ferramentas.bat e um terminal reaberto.
rem ============================================================================
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0.."

echo.
echo === [1/6] Rust: toolchain stable ===
where rustup >nul 2>&1
if errorlevel 1 (
  echo [ERRO] rustup não encontrado. Rode 1_instalar_ferramentas.bat e reabra o terminal.
  goto :falha
)
rustup default stable || goto :falha

echo.
echo === [2/6] Python: ambiente virtual do backend ===
if not exist "backend\.venv\Scripts\python.exe" (
  call :achar_python || goto :falha
  echo Criando backend\.venv com %PYTHON%...
  %PYTHON% -m venv backend\.venv || goto :falha
) else (
  echo backend\.venv já existe.
)
backend\.venv\Scripts\python.exe -m pip install --upgrade pip -q || goto :falha
backend\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]" -q || goto :falha

echo.
echo === [3/6] Node: dependências ===
call npm install --no-fund --no-audit || goto :falha

echo.
echo === [4/6] Contrato OpenAPI e tipos TypeScript ===
call npm run contrato || goto :falha

echo.
echo === [5/6] Testes do backend ===
pushd backend
.venv\Scripts\python.exe -m pytest -q
set "RESULTADO=%errorlevel%"
popd
if not "%RESULTADO%"=="0" goto :falha

echo.
echo === [6/6] Testes do frontend ===
call npm test || goto :falha

echo.
echo ============================================================================
echo  Projeto pronto. Para abrir o app em modo desenvolvimento:
echo    npm run dev
echo  ^(a primeira compilação do Rust leva alguns minutos^)
echo ============================================================================
pause
exit /b 0

:achar_python
for %%v in (3.13 3.12 3.11) do (
  py -%%v --version >nul 2>&1 && (
    set "PYTHON=py -%%v"
    exit /b 0
  )
)
echo [ERRO] Python 3.11 ou superior não encontrado ^(comando "py"^). Rode 1_instalar_ferramentas.bat.
exit /b 1

:falha
echo.
echo [ERRO] A preparação parou. Leia a mensagem acima, corrija e rode o script de novo.
pause
exit /b 1
