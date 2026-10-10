@echo off
title Agent Orchestrator
chcp 65001 >nul
echo =======================================================
echo          AGENT ORCHESTRATOR — INICIALIZADOR
echo =======================================================
echo.

if not exist "backend\venv\Scripts\python.exe" (
    echo [1/4] Criando ambiente virtual Python...
    py -3 -m venv backend\venv
)

echo [2/4] Verificando dependencias...
if defined HTTP_PROXY (
    if not defined HTTPS_PROXY (
        set HTTPS_PROXY=%HTTP_PROXY%
    )
)

backend\venv\Scripts\pip.exe install -q -r backend\requirements.txt

echo [3/4] Verificando frontend...
set REBUILD=0
if /i "%~1"=="rebuild" set REBUILD=1

where npm >nul 2>nul
if errorlevel 1 (
    echo [Aviso] npm nao encontrado no PATH. O painel web nao sera compilado.
    echo [Aviso] Instale o Node.js para ver a interface; a API continua disponivel.
    goto :iniciar
)

if not exist "frontend\node_modules" (
    echo       Instalando dependencias do frontend...
    pushd frontend
    call npm install
    popd
)

if "%REBUILD%"=="1" (
    echo       Recompilando frontend por solicitacao...
) else (
    if exist "frontend\dist" goto :iniciar
    echo       Compilando frontend pela primeira vez nesta maquina...
)

pushd frontend
call npm run build
popd

:iniciar
echo [4/4] Iniciando aplicacao...
backend\venv\Scripts\python.exe run.py
pause
