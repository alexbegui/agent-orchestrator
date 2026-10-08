import os
import sys
import webbrowser
import threading
import time

# Garante que HTTPS_PROXY herde HTTP_PROXY no Windows se necessário
if os.environ.get("HTTP_PROXY") and not os.environ.get("HTTPS_PROXY"):
    os.environ["HTTPS_PROXY"] = os.environ["HTTP_PROXY"]

# Adiciona backend ao PYTHONPATH
backend_dir = os.path.join(os.path.dirname(__file__), "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


def open_browser():
    time.sleep(1.2)
    print("\n[Orchestrator] Abrindo painel no navegador: http://localhost:8000 ...")
    webbrowser.open("http://localhost:8000")


if __name__ == "__main__":
    import uvicorn
    from app.main import app

    threading.Thread(target=open_browser, daemon=True).start()
    print("=======================================================")
    print("        🚀 AGENT ORCHESTRATOR — SERVIDOR ATIVO")
    print("        Painel Web Local: http://localhost:8000")
    print("        Documentação API: http://localhost:8000/docs")
    print("=======================================================\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
