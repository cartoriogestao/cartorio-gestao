"""
Caminho de rede que morreu não pode derrubar nada.

O QUE ACONTECEU
    Na primeira rodada de verdade do COPIAR_ARQUIVOS_EOFICIO, seis pastas
    foram copiadas — inclusive as 3.644 assinaturas — e então
    `\\\\server\\SISDFERJ\\Correio` levantou

        OSError: [WinError 64] O nome da rede especificado não está mais
        disponível

    e matou o script. As duas últimas pastas da lista, o malote do SISDFERJ e
    as fichas do Registro de Imóveis, nem chegaram a ser tentadas.

POR QUE O `is_dir()` DO PYTHON NÃO BASTA
    Ele engole `WinError 21`, `123` e `1921` e devolve False. `WinError 64`
    não está na lista e escapa. Quer dizer: `Path.is_dir()` é seguro para
    caminho que não existe, e NÃO é seguro para caminho de rede que caiu.

    A diferença importa exatamente agora, porque desligar o servidor antigo é
    o objetivo do trabalho. Depois disso, todo `\\\\servidor\\...` gravado no
    banco vira um caminho que cai — e um deles estava no meio de uma consulta
    que monta a tela de assinaturas.

O QUE ESTES TESTES PROTEGEM
    Pasta que não responde é informação a relatar. Nunca motivo para parar.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_imagens as RIMG          # noqa: E402


def carregar_copiador():
    """O script das FERRAMENTAS, que não é módulo instalado."""
    caminho = RAIZ.parent.parent / "FERRAMENTAS" / "copiar_arquivos_eoficio.py"
    if not caminho.is_file():
        pytest.skip("copiar_arquivos_eoficio.py não está ao lado")
    spec = importlib.util.spec_from_file_location("copiador", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CaminhoQueCaiu(Path):
    """Um `Path` que se comporta como compartilhamento fora do ar."""

    _flavour = getattr(Path(), "_flavour", None)

    def is_dir(self, *a, **k):
        raise OSError(64, "O nome da rede especificado não está mais disponível")

    def is_file(self, *a, **k):
        raise OSError(64, "O nome da rede especificado não está mais disponível")


# ------------------------------------------------------- os dois guardiões

def test_e_pasta_devolve_falso_em_vez_de_levantar():
    assert RIMG.e_pasta(CaminhoQueCaiu("/nao/importa")) is False


def test_e_pasta_continua_dizendo_a_verdade(tmp_path):
    assert RIMG.e_pasta(tmp_path) is True
    assert RIMG.e_pasta(tmp_path / "nao_existe") is False


def test_diagnostico_nao_explode_com_raiz_de_rede_morta():
    # É a tela que o usuário abre justamente quando nada está funcionando.
    r = RIMG.diagnostico(["RF210703-1.JPG"], CaminhoQueCaiu("/caiu"))
    assert r["raiz_existe"] is False
    assert r["perdidas"] == 1


# ------------------------------------ a lição que custou duas pastas
# --------------------------------------- não copiadas

def test_uma_pasta_morta_nao_impede_as_seguintes(tmp_path, monkeypatch, capsys):
    copiador = carregar_copiador()

    boa = tmp_path / "origem_boa"
    boa.mkdir()
    (boa / "ficha.jpg").write_bytes(b"conteudo")
    dados = tmp_path / "dados" / "CartorioGestao"
    dados.mkdir(parents=True)

    monkeypatch.setattr(copiador, "dados", lambda: dados)
    monkeypatch.setattr(copiador, "caminhos_no_acervo", lambda _b: set())
    monkeypatch.setattr(copiador, "PASTAS", [
        ("\\\\server\\morta\\Correio", "Morta", "a que caiu"),
        (str(boa), "Boa", "a que vem depois"),
    ])

    original = copiador.resolver

    def resolver(origem):
        # Pelo prefixo, e não por "morta" em qualquer lugar: o tmp_path do
        # pytest carrega o nome do teste, e a pasta boa casava também.
        if origem.startswith("\\\\"):
            raise OSError(64, "O nome da rede especificado não está mais disponível")
        return original(origem)

    monkeypatch.setattr(copiador, "resolver", resolver)

    codigo = copiador.main()
    saida = capsys.readouterr().out

    # A pasta seguinte foi copiada, apesar da anterior ter falhado.
    assert (dados / "arquivos" / "eoficio" / "Boa" / "ficha.jpg").is_file()
    # E a falha aparece no relatório, em vez de sumir.
    assert "Morta" in saida or "morta" in saida
    # E o script se recusa a dizer que terminou bem.
    assert codigo == 2
    assert "NAO DESLIGUE O E-OFICIO" in saida


def test_resolver_devolve_none_quando_a_rede_caiu(monkeypatch):
    copiador = carregar_copiador()
    monkeypatch.setattr(copiador, "e_pasta", lambda p: False)
    assert copiador.resolver(r"\\servidor\SISDFERJ\Correio") is None


def test_o_manifesto_e_gravado_mesmo_com_falha(tmp_path, monkeypatch):
    # O que já veio precisa contar: rodar de novo não pode recopiar 356 MB.
    copiador = carregar_copiador()
    boa = tmp_path / "origem"
    boa.mkdir()
    (boa / "a.jpg").write_bytes(b"x")
    dados = tmp_path / "dados" / "CartorioGestao"
    dados.mkdir(parents=True)
    monkeypatch.setattr(copiador, "dados", lambda: dados)
    monkeypatch.setattr(copiador, "caminhos_no_acervo", lambda _b: set())
    monkeypatch.setattr(copiador, "PASTAS", [
        (str(boa), "Boa", "veio"),
        ("\\\\server\\morta\\x", "Morta", "não veio"),
    ])
    copiador.main()
    manifesto = dados / "arquivos" / "eoficio" / "MANIFESTO.json"
    assert manifesto.is_file()
    assert "a.jpg" in manifesto.read_text(encoding="utf-8")
