"""A chave de atualização é da INSTALAÇÃO, e não do código público — 27/10/2026.

Até a 3.7.5 a chave pública de uma serventia vinha escrita em
`assinatura_da_atualizacao.CHAVES_CONFIAVEIS`, e quem baixasse o projeto herdava
uma instalação que só aceitava pacote assinado por ela. Agora a lista sai de
`chaves_de_atualizacao.json`, ao lado do código instalado.

O QUE ESTES TESTES GUARDAM
      - o código público não traz chave nenhuma;
      - sem arquivo, a lista é vazia (modo de transição, como antes);
      - a chave gravada pela ferramenta é a que a conferência aceita;
      - **arquivo que existe e não se lê recusa TODO pacote** — nunca cai no
        modo de transição;
      - id que não é o da chave é recusado;
      - o arquivo não vai para o git.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import assinatura_da_atualizacao as ASS  # noqa: E402

ed25519 = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")


def _par():
    privada = ed25519.Ed25519PrivateKey.generate()
    crua = ASS.publica_crua(privada)
    return privada, ASS.id_da_chave(crua), base64.b64encode(crua).decode("ascii")


def test_o_codigo_publico_nao_traz_chave_de_serventia_nenhuma():
    fonte = (RAIZ / "assinatura_da_atualizacao.py").read_text(encoding="utf-8")
    assert "CHAVES_CONFIAVEIS: dict[str, str] = {}" in fonte
    assert "atbBkN9HNd7Ud8QZWtpcMJ8SuefqOMoGnAdEig2cTHc=" not in fonte


def test_sem_arquivo_a_lista_e_vazia(tmp_path):
    assert ASS.carregar_chaves_da_instalacao(tmp_path / "nao_existe.json") == ({}, "")


def test_a_chave_gravada_e_a_que_a_conferencia_aceita(tmp_path):
    privada, chave_id, publica = _par()
    arquivo = ASS.gravar_chave_na_instalacao(chave_id, publica,
                                             tmp_path / "chaves_de_atualizacao.json")
    chaves, motivo = ASS.carregar_chaves_da_instalacao(arquivo)
    assert motivo == "" and chaves == {chave_id: publica}
    manifesto = b'{"version": "9.9.9"}'
    assinatura = json.dumps(ASS.assinar(manifesto, privada)).encode("utf-8")
    assert ASS.conferir(manifesto, assinatura, chaves)["situacao"] == "ASSINADO"
    with pytest.raises(ASS.AssinaturaRecusada):
        ASS.conferir(manifesto, None, chaves)


def test_gravar_de_novo_acrescenta_e_nao_apaga(tmp_path):
    arquivo = tmp_path / "chaves_de_atualizacao.json"
    _, id1, pub1 = _par()
    _, id2, pub2 = _par()
    ASS.gravar_chave_na_instalacao(id1, pub1, arquivo)
    ASS.gravar_chave_na_instalacao(id2, pub2, arquivo)
    assert ASS.carregar_chaves_da_instalacao(arquivo)[0] == {id1: pub1, id2: pub2}


def test_arquivo_ilegivel_recusa_todo_pacote(tmp_path, monkeypatch):
    arquivo = tmp_path / "chaves_de_atualizacao.json"
    arquivo.write_text("{estragado", encoding="utf-8")
    chaves, motivo = ASS.carregar_chaves_da_instalacao(arquivo)
    assert chaves == {} and motivo
    monkeypatch.setattr(ASS, "CHAVES_CONFIAVEIS", {})
    monkeypatch.setattr(ASS, "CHAVES_ILEGIVEIS", motivo)
    with pytest.raises(ASS.AssinaturaRecusada, match="não se lê"):
        ASS.conferir(b"{}", None)
    with pytest.raises(ASS.AssinaturaRecusada):
        ASS.gravar_chave_na_instalacao(*_par()[1:], arquivo)


def test_id_que_nao_e_o_da_chave_e_recusado(tmp_path):
    _, _, publica = _par()
    arquivo = tmp_path / "chaves_de_atualizacao.json"
    arquivo.write_text(json.dumps({"chaves": {"0000000000000000": publica}}),
                       encoding="utf-8")
    chaves, motivo = ASS.carregar_chaves_da_instalacao(arquivo)
    assert chaves == {} and "não é o da chave" in motivo


def test_o_arquivo_nao_vai_para_o_git():
    assert "chaves_de_atualizacao.json" in (RAIZ / ".gitignore").read_text(encoding="utf-8")
