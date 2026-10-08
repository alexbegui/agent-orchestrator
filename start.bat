@echo off
title Agent Orchestrator
chcp 65001 >nul
echo =======================================================
echo          AGENT ORCHESTRATOR — INICIALIZADOR
echo =======================================================
echo.

if not exist "backend\venv\Scripts\python.exe" (
    echo [1/3] Criando ambiente virtual Python...
    py -3 -m venv backend\venv
)

echo [2/3] Verificando dependencias...
if defined HTTP_PROXY (
    if not defined HTTPS_PROXY (
        set HTTPS_PROXY=%HTTP_PROXY%
    )
)

backend\venv\Scripts\pip.exe install -q -r backend\requirements.txt

echo [3/3] Iniciando aplicacao...
backend\venv\Scripts\python.exe run.py
pause
