"""
Envoltório do agente desacoplado.

Um processo desacoplado não é filho do servidor, então o orquestrador não
consegue colher o código de saída depois que ele termina — o sistema já
descartou essa informação. Em vez de adivinhar, quem termina registra:
este envoltório executa o agente e grava o resultado no run.json.

Rodado como:
    python -m app.services.run_wrapper <run.json> [--stdin <arquivo>] -- <comando...>

O `--stdin` existe porque o Claude Code é despachado por `claude.cmd`, e
arquivo batch tem o argumento cortado na primeira quebra de linha pelo cmd.exe
— o agente recebia só o começo do prompt. O texto vai por aqui, que não passa
pelo interpretador de linha de comando.
"""
import json
import os
import subprocess
import sys
import time


def _gravar_conclusao(run_json: str, returncode: int) -> None:
    try:
        with open(run_json, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        dados = {}

    dados["finished_at"] = time.time()
    dados["returncode"] = returncode

    try:
        with open(run_json, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2)
    except OSError:
        pass


def main(argv: list) -> int:
    if "--" not in argv:
        print("[run_wrapper] uso: <run.json> -- <comando...>", file=sys.stderr)
        return 2

    corte = argv.index("--")
    run_json = argv[0]
    antes = argv[1:corte]
    comando = argv[corte + 1:]
    if not comando:
        print("[run_wrapper] nenhum comando informado", file=sys.stderr)
        return 2

    arquivo_stdin = None
    if "--stdin" in antes:
        i = antes.index("--stdin")
        if i + 1 < len(antes):
            arquivo_stdin = antes[i + 1]

    try:
        if arquivo_stdin:
            # Em bytes, não em texto: o prompt é UTF-8 e o console do Windows
            # não é. Deixar o Python recodificar aqui corromperia acento, que
            # é metade do texto num projeto que escreve em português.
            with open(arquivo_stdin, "rb") as entrada:
                proc = subprocess.run(comando, cwd=os.getcwd(), stdin=entrada)
        else:
            proc = subprocess.run(comando, cwd=os.getcwd())
        rc = proc.returncode
    except FileNotFoundError:
        print(f"[run_wrapper] executável não encontrado: {comando[0]}", file=sys.stderr)
        rc = 127
    except Exception as e:
        print(f"[run_wrapper] falha ao executar: {e}", file=sys.stderr)
        rc = 1

    _gravar_conclusao(run_json, rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
