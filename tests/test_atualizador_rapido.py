"""O ATUALIZADOR NÃO PAGA PELO QUE SÓ CONFERE — 15/09/2026.

    «ta muito lento esse atualizador» — o oficial

O QUE FOI MEDIDO NESTA MÁQUINA, antes de mexer numa linha:

    | passo | custava |
    |---|---|
    | copiar os 868 arquivos (o trabalho de verdade) | **0,96 s** |
    | `import flask,waitress,PIL,pypdfium2,segno` (só conferir) | **6,65 s** |
    | um arranque de `powershell.exe` | **3,19 s**, e havia quatro |

    **O passo que só CONFERIA custava sete vezes o passo que FAZIA.**
    `import PIL, pypdfium2` carrega as bibliotecas inteiras para responder uma
    pergunta de sim ou não; `importlib.util.find_spec` procura o módulo sem
    executá-lo, em **0,58 s**, e dá a mesma resposta.

O QUE ESTES TESTES GUARDAM
    Não o tempo — cronômetro em teste dá número diferente em cada máquina e
    fica vermelho quando ela está ocupada. Eles guardam a **forma** que produz
    o tempo: procurar em vez de importar, `net session` em vez de PowerShell, e
    o carimbo da versão pelo runtime que já está instalado.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ.parent / "ATUALIZAR_SISTEMA.cmd"


def _texto() -> str:
    if not SCRIPT.is_file():
        pytest.skip(f"{SCRIPT.name} não está nesta árvore")
    return SCRIPT.read_text(encoding="utf-8", errors="replace")


def _sem_comentario(texto: str) -> str:
    """O script sem as linhas `rem`.

    **VARREDOR NÃO PODE LER PROSA** — os comentários deste script citam
    `import flask,waitress,...` justamente para explicar que aquilo saiu.
    """
    return "\n".join(ln for ln in texto.split("\n")
                     if not ln.lstrip().lower().startswith("rem"))


def test_as_dependencias_se_procuram_em_vez_de_importar():
    codigo = _sem_comentario(_texto())
    assert "find_spec" in codigo, (
        "o atualizador voltou a importar as bibliotecas só para conferir — "
        "são 6,65 s contra 0,58 s, medidos")
    assert "-c \"import flask,waitress,PIL,pypdfium2,segno\"" not in codigo


def test_o_teste_de_administrador_nao_arranca_powershell():
    codigo = _sem_comentario(_texto())
    assert "net session" in codigo, (
        "o teste de administrador voltou ao PowerShell — 3,19 s contra 0,86 s")
    assert "WindowsBuiltInRole" not in codigo


def test_o_carimbo_da_versao_vai_pelo_runtime():
    codigo = _sem_comentario(_texto())
    assert "carimbar_versao.py" in codigo
    assert "ConvertFrom-Json" not in codigo, (
        "o carimbo voltou ao PowerShell")


def test_sobrou_powershell_so_onde_ele_e_necessario():
    """Elevar pelo UAC e o script de reinício — os dois não têm substituto."""
    codigo = _sem_comentario(_texto())
    assert codigo.count('"%PS%"') == 2, (
        f'{codigo.count(chr(34) + "%PS%" + chr(34))} chamadas de PowerShell; '
        f"são duas: `Start-Process -Verb RunAs` (o UAC) e o script de "
        f"reinício. Cada uma a mais custa ~3 s")


def test_o_script_do_carimbo_existe_e_funciona(tmp_path):
    """Ele grava as mesmas chaves, e arquivo ilegível não derruba nada."""
    ferramenta = RAIZ / "installer" / "carimbar_versao.py"
    assert ferramenta.is_file()

    versao = tmp_path / "VERSAO.txt"
    versao.write_text("3.6.135", encoding="utf-8")
    destino = tmp_path / "install.json"
    destino.write_text(json.dumps({"data_dir": "C:/x", "task_name": "T"}),
                       encoding="utf-8")

    r = subprocess.run([sys.executable, str(ferramenta), str(versao),
                        str(destino)], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    dados = json.loads(destino.read_text(encoding="utf-8"))
    assert dados["version"] == "3.6.135"
    assert dados["updated_at"]
    assert dados["data_dir"] == "C:/x", "o que já estava lá não se perde"
    assert dados["task_name"] == "T"


def test_json_ilegivel_nao_derruba_a_atualizacao(tmp_path):
    """O carimbo é informação: ele não pode impedir a atualização de terminar.

    Mas **diz o que houve** — carimbo que falha em silêncio é o que faz alguém
    ler a versão errada depois.
    """
    ferramenta = RAIZ / "installer" / "carimbar_versao.py"
    versao = tmp_path / "VERSAO.txt"
    versao.write_text("3.6.135", encoding="utf-8")
    destino = tmp_path / "install.json"
    destino.write_text("isto nao e json", encoding="utf-8")

    r = subprocess.run([sys.executable, str(ferramenta), str(versao),
                        str(destino)], capture_output=True, text=True, check=False)
    assert r.returncode == 0
    assert json.loads(destino.read_text(encoding="utf-8"))["version"] == "3.6.135"


def test_o_find_spec_responde_o_mesmo_que_o_import():
    """A troca só vale se as duas disserem a mesma coisa."""
    import importlib.util as u
    for modulo in ("json", "sqlite3"):
        assert u.find_spec(modulo) is not None
    assert u.find_spec("modulo_que_nao_existe_nenhum") is None


def test_a_origem_e_conferida_antes_de_parar_o_balcao():
    """Erro de fonte se descobre com o servidor ainda atendendo."""
    codigo = _sem_comentario(_texto())
    conferir = codigo.find('"%PYRT%" "%FONTE%\\tools\\conferir_antes_de_atualizar.py"')
    parar = codigo.find("call :REINICIAR Parar")
    copiar = codigo.find('robocopy "%FONTE%" "%PROG%"')
    assert conferir >= 0
    assert conferir < parar < copiar
    trecho = codigo[conferir:parar]
    assert "NADA FOI ALTERADO" in trecho
    assert "if errorlevel 1" in trecho
    assert "--fingerprint-out" in trecho


def test_divergencia_depois_da_copia_interrompe_a_atualizacao():
    """A conferencia nao pode ser decorativa nem deixar o balcao parado."""
    codigo = _sem_comentario(_texto())
    inicio = codigo.find('"%PROG%\\tools\\conferir_atualizacao.py"')
    fim = codigo.find("Atualizador da tela de atualizacoes atualizado.")
    assert inicio >= 0
    trecho = codigo[inicio:fim]
    assert "if errorlevel 1" in trecho
    assert "call :REINICIAR Subir" in trecho
    assert "exit /b 4" in trecho


def test_a_copia_ainda_e_a_mesma_arvore_que_passou_na_pre_conferencia():
    codigo = _sem_comentario(_texto())
    copiar = codigo.find('robocopy "%FONTE%" "%PROG%"')
    conferir_copia = codigo.find('"%PROG%\\tools\\conferir_atualizacao.py"')
    conferir_impressao = codigo.find("--expect-fingerprint")
    subir = codigo.find("call :REINICIAR Subir", conferir_impressao)
    assert copiar < conferir_copia < conferir_impressao < subir
    trecho = codigo[conferir_impressao:subir]
    assert "if errorlevel 1" in trecho
    assert "origem mudou" in trecho
