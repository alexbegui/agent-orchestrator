import os
import sys
import webbrowser
import threading
import time

# Garante que HTTPS_PROXY herde HTTP_PROXY no Windows se necessário
if os.environ.get("HTTP_PROXY") and not os.environ.get("HTTPS_PROXY"):
    os.environ["HTTPS_PROXY"] = os.environ["HTTP_PROXY"]

# Garante que localhost e 127.0.0.1 não passem pelo proxy corporativo
no_proxy = os.environ.get("NO_PROXY", "")
missing_hosts = [h for h in ["localhost", "127.0.0.1"] if h not in no_proxy.split(",")]
if missing_hosts:
    os.environ["NO_PROXY"] = ",".join(missing_hosts) + ("," + no_proxy if no_proxy else "")

# Adiciona backend ao PYTHONPATH
backend_dir = os.path.join(os.path.dirname(__file__), "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


# Configura codificação UTF-8 segura no Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def open_browser():
    time.sleep(1.2)
    print("\n[Orchestrator] Abrindo painel no navegador: http://127.0.0.1:8000 ...")
    webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    import uvicorn
    from app.main import app

    threading.Thread(target=open_browser, daemon=True).start()
    print("=======================================================")
    print("        [ORCHESTRATOR] SERVIDOR ATIVO")
    print("        Painel Web Local: http://localhost:8000")
    print("        Documentacao API: http://localhost:8000/docs")
    print("=======================================================\n")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")

