"""A transcrição neste servidor: o que recusa, o que guarda e o trabalhador.

O QUE ELES DEFENDEM
    Que ninguém liga o modelo grande sem a conferência, porque na máquina de 29/10/2026 ele
    nem carregou. Que o texto do áudio de teste não vai ao banco. E que o trabalhador não
    carrega nada do sistema: ele existe para morrer sozinho sem levar o balcão junto.

    Nada aqui abre o sistema nem tem o programa de verdade: o trabalhador roda contra um
    `faster_whisper` falso. A escolha na tela está em `tests/test_wa_transcricao_local_web.py`.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import wa_transcricao as TRANSC  # noqa: E402
import wa_transcricao_local as LOCAL  # noqa: E402
import wa_transcricao_trabalhador as TRAB  # noqa: E402


@pytest.fixture()
def casa(tmp_path, monkeypatch):
    """Um servidor em que tudo existe e cabe; cada teste tira o que quer provar."""
    usos = []
    monkeypatch.setattr(LOCAL, "programa_instalado", lambda: True)
    monkeypatch.setattr(LOCAL.RM, "memoria_livre_mb", lambda: 12000)
    monkeypatch.setattr(LOCAL.USO, "registrar", lambda pasta, **k: usos.append(k) or True)
    pasta = LOCAL.pasta_do_modelo(tmp_path)
    pasta.mkdir(parents=True)
    (pasta / LOCAL.ARQUIVO_DO_MODELO).write_bytes(b"x")
    (tmp_path / LOCAL.PASTA / LOCAL.ARQUIVO_DE_ESTADO).write_text(
        json.dumps({"situacao": TRAB.PRONTO}), encoding="utf-8")
    return SimpleNamespace(pasta=tmp_path, usos=usos, monkeypatch=monkeypatch)


def _responde(casa, texto="qual o horário de vocês", segundos=4.0):
    def processo(comando, prazo):
        Path(comando[-1]).write_text(json.dumps({"texto": texto, "segundos": segundos}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr=b"")
    casa.monkeypatch.setattr(LOCAL, "_processo", processo)


def _restos(pasta) -> list[str]:
    onde = Path(pasta) / LOCAL.PASTA / "em_andamento"
    return [p.name for p in onde.iterdir()] if onde.exists() else []


# ------------------------------------------------------------- a conferência

def test_a_conferencia_aprovada_diz_o_tempo_e_o_texto(casa):
    _responde(casa)
    r = LOCAL.conferir(casa.pasta, b"audio", "audio/ogg", agora="2026-12-20T10:00:00", por="Mario")
    assert r["ok"] is True
    assert r["segundos"] == 4.0
    assert "qual o horário de vocês" in LOCAL.recado_da_conferencia(r)
    assert _restos(casa.pasta) == [], "o áudio de teste não fica no disco"


def test_o_texto_do_audio_de_teste_nao_vai_ao_banco(casa):
    """Ele pode trazer dado de cliente: aparece uma vez na tela, e só."""
    _responde(casa, texto="meu CPF é tal")
    guardado = LOCAL.para_guardar(LOCAL.conferir(casa.pasta, b"audio", "audio/ogg"))
    assert "CPF" not in guardado
    assert json.loads(guardado)["ok"] is True


def test_sem_o_programa_recusa_dizendo_o_que_falta(casa):
    casa.monkeypatch.setattr(LOCAL, "programa_instalado", lambda: False)
    r = LOCAL.conferir(casa.pasta, b"audio", "audio/ogg")
    assert r["ok"] is False and "faster-whisper" in r["motivo"]


def test_sem_o_modelo_recusa(casa):
    (LOCAL.pasta_do_modelo(casa.pasta) / LOCAL.ARQUIVO_DO_MODELO).unlink()
    r = LOCAL.conferir(casa.pasta, b"audio", "audio/ogg")
    assert r["ok"] is False and "Baixe o modelo" in r["motivo"]


def test_download_pela_metade_nao_conta_como_baixado(casa):
    (casa.pasta / LOCAL.PASTA / LOCAL.ARQUIVO_DE_ESTADO).write_text(
        json.dumps({"situacao": TRAB.BAIXANDO}), encoding="utf-8")
    assert LOCAL.modelo_baixado(casa.pasta) is False


def test_pouca_memoria_recusa_sem_nem_tentar(casa):
    """É o caso medido: em 3,1 GB livres o large-v3 estourou mkl_malloc."""
    casa.monkeypatch.setattr(LOCAL.RM, "memoria_livre_mb", lambda: 3100)
    casa.monkeypatch.setattr(LOCAL, "_processo", lambda *a: pytest.fail("não era para rodar"))
    r = LOCAL.conferir(casa.pasta, b"audio", "audio/ogg")
    assert r["ok"] is False and "3100 MB" in r["motivo"]


def test_audio_sem_fala_nao_aprova(casa):
    _responde(casa, texto="")
    r = LOCAL.conferir(casa.pasta, b"audio", "audio/ogg")
    assert r["ok"] is False and "fala" in r["motivo"]


def test_lento_demais_recusa_dizendo_o_tempo(casa):
    _responde(casa, segundos=4.0)
    tempos = iter([0.0, 200.0])
    casa.monkeypatch.setattr(LOCAL.time, "monotonic", lambda: next(tempos))
    r = LOCAL.conferir(casa.pasta, b"audio", "audio/ogg")
    assert r["ok"] is False and "200 s" in r["motivo"]


def test_audio_longo_pode_levar_mais(casa):
    _responde(casa, segundos=60.0)
    tempos = iter([0.0, 200.0])
    casa.monkeypatch.setattr(LOCAL.time, "monotonic", lambda: next(tempos))
    assert LOCAL.conferir(casa.pasta, b"audio", "audio/ogg")["ok"] is True


# ------------------------------------------------------------- a transcrição de cada dia

def test_transcreve_sem_custo_e_conta_no_teto(casa):
    _responde(casa)
    r = LOCAL.transcrever(casa.pasta, b"audio", "audio/ogg; codecs=opus", modulo="wa_atendente",
                          finalidade="wa_audio", referencia="wa_mensagem:1")
    assert r["texto"] and r["custo_usd"] == 0.0 and r["provedor"] == LOCAL.PROVEDOR
    assert casa.usos[0]["finalidade"] == "wa_audio", "é esta linha que conta o teto do dia"
    assert _restos(casa.pasta) == []


def _falha_com(casa, *, erro=None, codigo=0):
    def processo(comando, prazo):
        if erro:
            raise erro
        return SimpleNamespace(returncode=codigo, stderr=b"mkl_malloc: failed to allocate memory")
    casa.monkeypatch.setattr(LOCAL, "_processo", processo)


@pytest.mark.parametrize("como", [
    {"erro": subprocess.TimeoutExpired("x", 180)},
    {"erro": OSError("sem python")},
    {"codigo": 1},
], ids=["passou do prazo", "não iniciou", "morreu sem memória"])
def test_quem_falha_levanta_o_mesmo_erro_e_o_audio_vai_para_uma_pessoa(casa, como):
    """`transcrever_pendentes` só conhece `TranscricaoErro`: outro erro derrubaria a rodada."""
    _falha_com(casa, **como)
    with pytest.raises(TRANSC.TranscricaoErro, match="quem atende ouvir"):
        LOCAL.transcrever(casa.pasta, b"audio", "audio/ogg")
    assert casa.usos[0]["resultado"] == LOCAL.USO.ERRO
    assert _restos(casa.pasta) == [], "áudio de cliente não fica para trás"


def test_resposta_ilegivel_tambem_e_o_mesmo_erro(casa):
    def processo(comando, prazo):
        Path(comando[-1]).write_text("{meio json", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr=b"")
    casa.monkeypatch.setattr(LOCAL, "_processo", processo)
    with pytest.raises(TRANSC.TranscricaoErro, match="formato"):
        LOCAL.transcrever(casa.pasta, b"audio", "audio/ogg")
    assert _restos(casa.pasta) == []


def test_audio_acima_do_teto_nem_vai_ao_trabalhador(casa):
    casa.monkeypatch.setattr(LOCAL, "_processo", lambda *a: pytest.fail("não era para rodar"))
    with pytest.raises(TRANSC.TranscricaoErro, match="16 MB"):
        LOCAL.transcrever(casa.pasta, b"x" * (LOCAL.TETO_DE_BYTES + 1), "audio/ogg")


# ------------------------------------------------------------- o download

def _sem_modelo(casa):
    (LOCAL.pasta_do_modelo(casa.pasta) / LOCAL.ARQUIVO_DO_MODELO).unlink()
    (casa.pasta / LOCAL.PASTA / LOCAL.ARQUIVO_DE_ESTADO).unlink()


def test_o_download_solta_o_trabalhador_e_marca_o_estado(casa):
    _sem_modelo(casa)
    soltos = []
    casa.monkeypatch.setattr(LOCAL, "_soltar", soltos.append)
    LOCAL.iniciar_download(casa.pasta)
    assert soltos[0][-4] == "baixar"
    assert LOCAL.estado_do_download(casa.pasta)["situacao"] == TRAB.BAIXANDO


def test_o_download_nao_repete_o_que_ja_existe_nem_o_que_esta_em_curso(casa):
    casa.monkeypatch.setattr(LOCAL, "_soltar", lambda c: pytest.fail("não era para soltar"))
    with pytest.raises(LOCAL.TranscricaoLocalErro, match="Não se baixa de novo"):
        LOCAL.iniciar_download(casa.pasta)
    _sem_modelo(casa)
    LOCAL._gravar_estado(casa.pasta, situacao=TRAB.BAIXANDO, inicio=LOCAL._agora())
    with pytest.raises(LOCAL.TranscricaoLocalErro, match="em andamento"):
        LOCAL.iniciar_download(casa.pasta)


def test_download_que_morreu_pode_recomecar(casa):
    """Sem isto, um servidor reiniciado no meio deixaria «baixando» para sempre."""
    _sem_modelo(casa)
    LOCAL._gravar_estado(casa.pasta, situacao=TRAB.BAIXANDO, inicio="2020-01-01 08:00")
    soltos = []
    casa.monkeypatch.setattr(LOCAL, "_soltar", soltos.append)
    LOCAL.iniciar_download(casa.pasta)
    assert soltos


def test_sem_o_programa_o_download_diz_o_que_falta(casa):
    casa.monkeypatch.setattr(LOCAL, "programa_instalado", lambda: False)
    with pytest.raises(LOCAL.TranscricaoLocalErro, match="faster-whisper"):
        LOCAL.iniciar_download(casa.pasta)


def test_disco_cheio_recusa_antes_de_baixar(casa):
    _sem_modelo(casa)
    casa.monkeypatch.setattr(LOCAL.shutil, "disk_usage",
                             lambda p: SimpleNamespace(free=1024 ** 3))
    with pytest.raises(LOCAL.TranscricaoLocalErro, match="1.0 GB livres"):
        LOCAL.iniciar_download(casa.pasta)


# ------------------------------------------------------------- pode ligar?

def test_so_liga_com_a_conferencia_aprovada(casa):
    assert "conferência" in LOCAL.pode_ligar(casa.pasta, {})
    assert "conferência" in LOCAL.pode_ligar(casa.pasta, {"ok": False})
    assert LOCAL.pode_ligar(casa.pasta, {"ok": True}) == ""


def test_conferencia_guardada_ilegivel_nao_derruba_a_tela():
    assert LOCAL.conferencia_guardada("") == {}
    assert LOCAL.conferencia_guardada("{meio") == {}
    assert LOCAL.conferencia_guardada("[1]") == {}


# ------------------------------------------------------------- o trabalhador

FALSO = """
class _S:
    def __init__(self, text): self.text = text
class _I:
    duration = 3.7
class WhisperModel:
    def __init__(self, caminho, device, compute_type):
        assert device == "cpu" and compute_type == "int8"
    def transcribe(self, entrada, language, beam_size, vad_filter):
        assert language == "pt" and beam_size == 5
        return iter([_S(" bom dia "), _S(" qual o horário ")]), _I()
def download_model(modelo, output_dir):
    if modelo == "falha":
        raise RuntimeError("sem rede")
"""


def _rodar_trabalhador(tmp_path, *argumentos) -> int:
    (tmp_path / "faster_whisper.py").write_text(FALSO, encoding="utf-8")
    ambiente = {**os.environ, "PYTHONPATH": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-B", str(RAIZ / "wa_transcricao_trabalhador.py"), *argumentos],
                          env=ambiente, capture_output=True, timeout=60, cwd=str(tmp_path)).returncode


def test_o_trabalhador_transcreve_e_deixa_o_json(tmp_path):
    saida = tmp_path / "saida.json"
    assert _rodar_trabalhador(tmp_path, "transcrever", str(tmp_path), "a.ogg", str(saida)) == 0
    assert json.loads(saida.read_text(encoding="utf-8")) == {"texto": "bom dia qual o horário", "segundos": 3.7}


def test_o_trabalhador_marca_pronto_ou_erro_no_download(tmp_path):
    estado = tmp_path / "estado.json"
    assert _rodar_trabalhador(tmp_path, "baixar", str(tmp_path), str(estado), "large-v3") == 0
    assert json.loads(estado.read_text(encoding="utf-8"))["situacao"] == TRAB.PRONTO
    assert _rodar_trabalhador(tmp_path, "baixar", str(tmp_path), str(estado), "falha") == 1
    dados = json.loads(estado.read_text(encoding="utf-8"))
    assert dados["situacao"] == TRAB.ERRO and "sem rede" in dados["erro"]


def test_o_trabalhador_nao_carrega_nada_do_sistema():
    """Ele não abre banco nem Flask: é o que faz a falta de memória morrer sozinha."""
    arvore = ast.parse((RAIZ / "wa_transcricao_trabalhador.py").read_text(encoding="utf-8"))
    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados |= {a.name.split(".")[0] for a in no.names}
        elif isinstance(no, ast.ImportFrom):
            importados.add((no.module or "").split(".")[0])
    assert importados <= {"__future__", "json", "os", "sys", "datetime", "pathlib", "faster_whisper"}, importados


def test_o_programa_e_o_modelo_nao_viajam_no_pacote():
    """Três gigas num `.cgu` iriam para toda atualização: nenhum requisito pede o programa."""
    for nome in ("requirements.txt", "requirements.lock"):
        arquivo = RAIZ / nome
        if arquivo.exists():
            assert "faster-whisper" not in arquivo.read_text(encoding="utf-8", errors="ignore").lower()
