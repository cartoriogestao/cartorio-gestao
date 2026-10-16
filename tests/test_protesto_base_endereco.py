"""A base nacional de endereços da CENPROT, a partir do aviso — 15/10/2026.

O QUE ESTES TESTES GUARDAM
  - o transporte é o do contrato: consultar é POST com o documento na query,
    e 404 quer dizer «ninguém com esse documento», e não erro; cadastrar é
    PUT com os doze campos, e os seis essenciais não vão vazios;
  - só se cadastra o endereço em que o aviso FOI ENTREGUE, e uma vez só;
  - a consulta fica guardada, e cada endereço achado diz se é NOVO;
  - a tela pergunta e mostra; nada sai sem clique.
"""
from __future__ import annotations

import json

import pytest

import cenprot_api as CAPI
import protesto_base_endereco as PBE

from test_protesto_aviso_web import (_con, _token, aviso_id, emitir,  # noqa: F401
                                     registrar, s, titulo_apontado)

ACHADO_NOVO = {"nm_usuario": "JOSE DA SILVA", "nm_endereco": "AV CENTRAL",
               "nm_nr_endereco": "200", "nm_bairro": "NOVA", "nm_nr_cep": "65900000",
               "nm_cidade": "IMPERATRIZ", "nm_uf": "MA", "nm_nr_celular":
               "(99) 90000-0000", "origem": "CENPROT", "data_cadastro": "01/01/2026 12:00"}


# ---------------------------------------------------------- o transporte


def test_consultar_e_post_com_o_documento_na_query(monkeypatch):
    vistos = []

    def bater(amb, metodo, caminho, **k):
        vistos.append((metodo, caminho, k.get("corpo")))
        return {"status": 200, "json": {"usuario": [ACHADO_NOVO]}, "texto": ""}

    monkeypatch.setattr(CAPI, "_bater", bater)
    achados = CAPI.consultar_endereco("047.855.123-88")
    assert achados[0]["nm_cidade"] == "IMPERATRIZ"
    assert vistos == [("POST", "/base-endereco?documento=04785512388", None)]


def test_consultar_404_e_lista_vazia(monkeypatch):
    monkeypatch.setattr(CAPI, "_bater", lambda *a, **k: {
        "status": 404, "json": {"message": "Usuário não encontrado"}, "texto": ""})
    assert CAPI.consultar_endereco("04785512388") == []


def test_consultar_recusa_documento_torto_sem_rede(monkeypatch):
    monkeypatch.setattr(CAPI, "_bater", lambda *a, **k: pytest.fail("rede"))
    with pytest.raises(CAPI.CenprotError, match="CPF"):
        CAPI.consultar_endereco("123")


def test_cadastrar_e_put_com_os_doze_campos(monkeypatch):
    vistos = []

    def bater(amb, metodo, caminho, **k):
        vistos.append((metodo, caminho, json.loads(k["corpo"])))
        return {"status": 200, "json": {"message": "Dados cadastrados com sucesso."},
                "texto": ""}

    monkeypatch.setattr(CAPI, "_bater", bater)
    dados = {"nm_usuario": "JOSE", "nm_nr_cpfcnpj": "047.855.123-88",
             "nm_nr_cep": "65936-000", "nm_endereco": "RUA GRANDE",
             "nm_cidade": "CIDADE EXEMPLO", "sg_uf": "MA"}
    CAPI.cadastrar_endereco(dados)
    metodo, caminho, corpo = vistos[0]
    assert (metodo, caminho) == ("PUT", "/base-endereco")
    assert tuple(corpo) == CAPI.CAMPOS_DO_CADASTRO_DE_ENDERECO
    assert corpo["nm_email"] == ""                       # presente e vazio


def test_cadastrar_sem_cep_recusa_dizendo_o_que_falta(monkeypatch):
    monkeypatch.setattr(CAPI, "_bater", lambda *a, **k: pytest.fail("rede"))
    with pytest.raises(CAPI.CenprotError, match="o CEP"):
        CAPI.cadastrar_endereco({"nm_usuario": "J", "nm_nr_cpfcnpj": "1",
                                 "nm_endereco": "R", "nm_cidade": "C",
                                 "sg_uf": "MA"})


# ------------------------------------------------------------ o domínio


def test_o_numero_sai_do_fim_do_endereco():
    assert PBE._partir_numero("RUA GRANDE, 10") == ("RUA GRANDE", "10")
    assert PBE._partir_numero("POVOADO CENTRO") == ("POVOADO CENTRO", "sn")


def test_o_cadastro_so_sai_do_aviso_entregue():
    av = {"situacao": "NAO_ENTREGUE", "devedor_documento": "04785512388"}
    with pytest.raises(PBE.BaseEnderecoError, match="ENTREGUE"):
        PBE.corpo_do_cadastro(av)
    av.update(situacao="ENTREGUE", devedor_nome="JOSÉ DA SILVA",
              endereco="RUA GRANDE, 10", cep="65936000", cidade="CIDADE EXEMPLO",
              uf="ma", bairro="CENTRO")
    corpo = PBE.corpo_do_cadastro(av)
    assert corpo["nm_nr_cpfcnpj"] == "047.855.123-88"
    assert corpo["nm_nr_cep"] == "65936-000" and corpo["sg_uf"] == "MA"
    assert corpo["nm_endereco"] == "RUA GRANDE" and corpo["nm_nr_endereco"] == "10"


# ------------------------------------------------------------- a tela


def _nao_entregue(s) -> int:
    tid = titulo_apontado(s)
    emitir(s, tid)
    registrar(s, aviso_id(s), entregue="0", motivo="11")
    return aviso_id(s)


def _postar(s, caminho):
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    return s["c"].post(caminho, data={"csrf_token": _token(tela)},
                       follow_redirects=True).get_data(as_text=True)


def test_procurar_guarda_e_mostra_o_endereco_novo(s, monkeypatch):
    monkeypatch.setattr(CAPI, "consultar_endereco",
                        lambda doc, ambiente=None, **k: [ACHADO_NOVO])
    aid = _nao_entregue(s)
    html = _postar(s, f"/protesto/avisos/{aid}/base-cenprot/consultar")
    assert "1 endereço(s)" in html and "1 diferente(s) do aviso" in html
    assert "AV CENTRAL" in html and "(99) 90000-0000" in html
    linha = _con(s).execute("SELECT * FROM pt_base_endereco").fetchone()
    assert linha["acao"] == "CONSULTA" and linha["achados"] == 1
    assert linha["documento"] == "04785512388"


def test_a_base_vazia_diz_que_nao_achou(s, monkeypatch):
    monkeypatch.setattr(CAPI, "consultar_endereco", lambda doc, **k: [])
    aid = _nao_entregue(s)
    assert "não tem endereço" in _postar(
        s, f"/protesto/avisos/{aid}/base-cenprot/consultar")


def test_o_entregue_se_cadastra_uma_vez_so(s, monkeypatch):
    mandados = []
    monkeypatch.setattr(CAPI, "cadastrar_endereco",
                        lambda corpo, **k: mandados.append(corpo) or {"message": "ok"})
    tid = titulo_apontado(s)
    emitir(s, tid)
    registrar(s, aviso_id(s), entregue="1", quando="2026-10-14",
              recebido_por="JOSÉ DA SILVA")
    aid = aviso_id(s)
    html = _postar(s, f"/protesto/avisos/{aid}/base-cenprot/cadastrar")
    assert "cadastrado na base nacional" in html
    assert "na base da CENPROT desde" in html
    html = _postar(s, f"/protesto/avisos/{aid}/base-cenprot/cadastrar")
    assert "já foi cadastrado" in html
    assert len(mandados) == 1
    assert mandados[0]["nm_usuario"]


def test_o_nao_entregue_nao_se_cadastra(s, monkeypatch):
    monkeypatch.setattr(CAPI, "cadastrar_endereco",
                        lambda *a, **k: pytest.fail("não devia mandar"))
    aid = _nao_entregue(s)
    assert "FOI ENTREGUE" in _postar(
        s, f"/protesto/avisos/{aid}/base-cenprot/cadastrar")
