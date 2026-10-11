"""
Resolução do binário do `agy`.

O instalador do agy põe o executável em %LOCALAPPDATA%\\agy\\bin, mas só
acrescenta essa pasta ao PATH do usuário — processos abertos ANTES disso
seguem com um PATH velho e o `shutil.which` devolve None. Sem o fallback por
caminho absoluto, o orchestrator quebra com WinError 2 numa máquina onde o
agy está perfeitamente instalado.
"""
import os
from unittest.mock import patch

from app.core.cli_paths import find_agy


def test_prefere_o_path_quando_o_which_resolve():
    with patch("shutil.which", side_effect=lambda n: "C:/path/agy.exe" if n in ("agy", "agy.exe") else None):
        assert find_agy() == "C:/path/agy.exe"


def test_cai_no_localappdata_quando_o_path_nao_tem_a_entrada(tmp_path):
    """O caso real: agy instalado, PATH do processo desatualizado."""
    bin_dir = tmp_path / "agy" / "bin"
    bin_dir.mkdir(parents=True)
    agy = bin_dir / "agy.exe"
    agy.write_text("")

    with patch("shutil.which", return_value=None), \
         patch.dict(os.environ, {"LOCALAPPDATA": str(tmp_path)}):
        assert find_agy() == os.path.join(str(tmp_path), "agy", "bin", "agy.exe")


def test_devolve_none_quando_nao_esta_instalado(tmp_path):
    """Caminho inexistente não pode ser devolvido: encurta a cascata de fallback."""
    with patch("shutil.which", return_value=None), \
         patch.dict(os.environ, {"LOCALAPPDATA": str(tmp_path)}), \
         patch("os.path.expanduser", return_value=str(tmp_path / "nada")):
        assert find_agy() is None


def test_honra_agy_path_absoluto_das_settings(tmp_path):
    """AGY_PATH existe na config; precisa valer de verdade como override."""
    custom = tmp_path / "meu-agy.exe"
    custom.write_text("")

    with patch("shutil.which", return_value=None), \
         patch("app.core.cli_paths.settings") as s:
        s.AGY_PATH = str(custom)
        assert find_agy() == str(custom)


def test_ignora_agy_path_absoluto_inexistente(tmp_path):
    """Um override apontando para o vazio não pode mascarar a instalação real."""
    bin_dir = tmp_path / "agy" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "agy.exe").write_text("")

    with patch("shutil.which", return_value=None), \
         patch.dict(os.environ, {"LOCALAPPDATA": str(tmp_path)}), \
         patch("app.core.cli_paths.settings") as s:
        s.AGY_PATH = str(tmp_path / "fantasma.exe")
        assert find_agy() == os.path.join(str(tmp_path), "agy", "bin", "agy.exe")
