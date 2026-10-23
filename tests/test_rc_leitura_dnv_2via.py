"""A DNV «2ª via – Cartório» triada como IDENTIDADE — 21/10/2026.

Nas leituras 5, 6 e 7 da produção, um PDF com o RG da mãe e a DNV 2ª via
(formulário MS/SINASC) teve as duas páginas triadas como IDENTIDADE, e o
nascimento recusava «não há uma DNV». Aqui a IA é de mentira e os dados são
FICTÍCIOS (os mesmos de `test_rc_leitura_documentos`). Nada fala com a rede.

Veio do sandbox (LH03): os oito primeiros são os de lá; o último passa pela
tela, porque o conserto só vale se a rota disser a espécie ao `ler`.
"""
from __future__ import annotations

import json
from io import BytesIO

import pytest

import rc_leitura_documentos as LEIT
from test_rc_leitura_documentos import DNV, IDENTIDADES, _doc, _png, _token

EM_USO = {"triagem": "T", "manuscrito": "FORTE", "impresso": "MEDIO"}

# o que o molde de IDENTIDADE tirou da DNV 2ª via (como na leitura 7, fictício)
DNV_LIDA_COMO_IDENTIDADE = {"pessoas": [
    {"tipo_documento": "OUTRO", "nome": "MARIA EXEMPLO DA SILVA",
     "data_nascimento": "02/03/2026", "filiacao_mae": "ANA EXEMPLA DA SILVA",
     "outros_campos": {"documento": "Declaração de Nascido Vivo - 2ª via - Cartório",
                       "numero": "30-12345678-9", "orgao": "Ministério da Saúde",
                       "Parturiente - nome": "ANA EXEMPLA DA SILVA"}}]}
RG_SO = {"pessoas": [IDENTIDADES["pessoas"][0]]}


class IA:
    """A triagem diz `tipos`; cada leitura responde pelo arquivo e pelo molde.

    O `**_registro` é o que o transporte da tela acrescenta (finalidade,
    usuário, referência — LF01) e a IA de mentira não usa."""

    def __init__(self, tipos, dnv_relida=DNV):
        self.tipos, self.dnv_relida = tipos, dnv_relida
        self.pedidos = []

    def __call__(self, pasta, *, provedor, sistema, conversa, ferramentas, modelo,
                 maximo_de_saida, **_registro):
        pedido = json.dumps(conversa, ensure_ascii=False, default=str)
        arquivo = "dnv.png" if "dnv.png" in pedido else "rg.png"
        if sistema == LEIT.INSTRUCAO_TRIAGEM:
            molde, corpo = "TRIAGEM", {"paginas": [{"n": i, "tipo": t}
                                                   for i, t in enumerate(self.tipos, 1)]}
        elif "Nascido Vivo" in sistema:
            molde, corpo = "DNV", self.dnv_relida
        else:
            molde = "IDENTIDADE"
            corpo = DNV_LIDA_COMO_IDENTIDADE if arquivo == "dnv.png" else RG_SO
        self.pedidos.append((molde, arquivo if molde != "TRIAGEM" else "*"))
        return {"texto": json.dumps(corpo), "entrada": 1000, "saida": 200, "modelo": modelo}


def _arquivos(tmp_path):
    return [{"caminho": str(_png(tmp_path / n)), "nome": n} for n in ("rg.png", "dnv.png")]


def test_a_triagem_instrui_que_a_dnv_2via_e_sempre_dnv():
    t = LEIT.INSTRUCAO_TRIAGEM
    assert "SEMPRE DNV, NUNCA IDENTIDADE" in t
    assert "2ª via" in t and "SINASC" in t and "NN-NNNNNNNN-N" in t


def test_sinais_de_dnv():
    assert "número no formato NN-NNNNNNNN-N" in LEIT.sinais_de_dnv(DNV_LIDA_COMO_IDENTIDADE)
    assert "«Declaração de Nascido Vivo»" in LEIT.sinais_de_dnv(DNV_LIDA_COMO_IDENTIDADE)
    assert LEIT.sinais_de_dnv(RG_SO) == []
    assert LEIT.sinais_de_dnv({"x": "Parturiente"}) == []        # sozinho não basta
    assert LEIT.sinais_de_dnv({"x": "NASCIDO VIVO"})               # sem acento, maiúsculo
    assert LEIT.sinais_de_dnv({"n": "123-12345678-9"}) == []       # não é o formato


def test_a_triagem_erra_e_a_rede_de_seguranca_rele_como_dnv(tmp_path):
    ia = IA(["IDENTIDADE", "IDENTIDADE"])
    lido = LEIT.ler(ia, tmp_path, EM_USO, _arquivos(tmp_path), especie="NASCIMENTO")
    assert [p["tipo"] for p in lido["paginas"]] == ["IDENTIDADE", "DNV"]
    dnv = lido["documentos"][1]
    assert dnv["tipo"] == "DNV" and dnv["dados"] == DNV and dnv["triada_como"] == "IDENTIDADE"
    assert dnv["relida_como_dnv_por"]
    # só a página suspeita foi relida, uma vez, pelo molde da DNV
    assert ia.pedidos.count(("DNV", "dnv.png")) == 1 and ("DNV", "rg.png") not in ia.pedidos
    assert [e["etapa"] for e in lido["envios"]].count("releitura_dnv") == 1
    junto = LEIT.juntar_nascimento(lido["documentos"])
    assert junto["valores"]["nome"] == "Maria Exemplo da Silva"
    textos = " | ".join(a["texto"] for a in junto["conferencia"])
    assert "relida como DNV" in textos and "A triagem disse IDENTIDADE" in textos


def test_sem_especie_ou_noutra_especie_nao_ha_releitura(tmp_path):
    for especie in (None, "OBITO"):
        ia = IA(["IDENTIDADE", "IDENTIDADE"])
        lido = LEIT.ler(ia, tmp_path, EM_USO, _arquivos(tmp_path), especie=especie)
        assert [d["tipo"] for d in lido["documentos"]] == ["IDENTIDADE", "IDENTIDADE"]
        assert not [m for m, _ in ia.pedidos if m == "DNV"]


def test_dnv_normal_sem_regressao(tmp_path):
    ia = IA(["IDENTIDADE", "DNV"])
    lido = LEIT.ler(ia, tmp_path, EM_USO, _arquivos(tmp_path), especie="NASCIMENTO")
    assert [p["tipo"] for p in lido["paginas"]] == ["IDENTIDADE", "DNV"]
    assert "triada_como" not in lido["documentos"][1]
    assert ia.pedidos.count(("DNV", "dnv.png")) == 1          # a leitura normal, só
    assert "releitura_dnv" not in [e["etapa"] for e in lido["envios"]]
    assert len(lido["envios"]) == 3
    junto = LEIT.juntar_nascimento(lido["documentos"])
    assert junto["valores"]["nome"] == "Maria Exemplo da Silva"
    assert "relida como DNV" not in " | ".join(a["texto"] for a in junto["conferencia"])


def test_sem_dnv_de_verdade_a_mensagem_e_clara(tmp_path):
    # Só RG: nenhum sinal, nenhuma releitura, a recusa de sempre.
    ia = IA(["IDENTIDADE"])
    arquivos = [{"caminho": str(_png(tmp_path / "rg.png")), "nome": "rg.png"}]
    lido = LEIT.ler(ia, tmp_path, EM_USO, arquivos, especie="NASCIMENTO")
    assert not [m for m, _ in ia.pedidos if m == "DNV"]
    with pytest.raises(LEIT.LeituraError, match="não há uma DNV — sem ela") as e:
        LEIT.juntar_nascimento(lido["documentos"])
    assert "parece ser a DNV" not in str(e.value)


def test_a_releitura_falha_e_a_mensagem_diz_qual_pagina_parece_a_dnv(tmp_path):
    ia = IA(["IDENTIDADE", "IDENTIDADE"], dnv_relida={})     # a releitura não trouxe nada
    lido = LEIT.ler(ia, tmp_path, EM_USO, _arquivos(tmp_path), especie="NASCIMENTO")
    assert [d["tipo"] for d in lido["documentos"]] == ["IDENTIDADE", "IDENTIDADE"]
    with pytest.raises(LEIT.LeituraError, match="não há uma DNV") as e:
        LEIT.juntar_nascimento(lido["documentos"])
    msg = str(e.value)
    assert "página 1 de «dnv.png» parece ser a DNV" in msg
    assert "NN-NNNNNNNN-N" in msg and "rg.png" not in msg


def test_a_mensagem_vale_tambem_para_leitura_ja_guardada():
    # documentos de uma leitura antiga (sem a rede): a recusa aponta a página
    with pytest.raises(LEIT.LeituraError, match="não há uma DNV") as e:
        LEIT.juntar_nascimento([_doc("IDENTIDADE", RG_SO, 1),
                                _doc("IDENTIDADE", DNV_LIDA_COMO_IDENTIDADE, 2)])
    assert "página 2 de «docs.pdf» parece ser a DNV" in str(e.value)


def test_pela_tela_o_nascimento_com_a_dnv_triada_errado_fica_lido_e_avisa(cg_casa_logada,
                                                                         monkeypatch):
    # A tela é quem sabe a espécie: sem ela chegar ao `ler`, a rede não age e a
    # leitura FALHA com «não há uma DNV», como nas leituras 5, 6 e 7.
    import agente_provedores as AP
    from PIL import Image
    from bd_nativo import banco
    casa = cg_casa_logada
    c = casa["c"]
    r = c.get("/rcpn/leitura")
    assert r.status_code == 200
    ia = IA(["IDENTIDADE", "IDENTIDADE"])
    monkeypatch.setattr(AP, "conversar", ia)
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    arquivos = []
    for nome in ("rg.png", "dnv.png"):
        b = BytesIO()
        Image.new("RGB", (60, 80), "white").save(b, format="PNG")
        b.seek(0)
        arquivos.append((b, nome))
    r = c.post("/rcpn/leitura", data={"csrf_token": _token(r.get_data(as_text=True)),
                                      "especie": "NASCIMENTO", "arquivos": arquivos},
               content_type="multipart/form-data")
    assert r.status_code == 302 and "/rcpn/leitura/" in r.headers["Location"]
    with casa["db"].connect() as con:
        leitura = banco(con).um(
            "SELECT situacao, erro, documentos_json FROM rc_leituras ORDER BY id DESC LIMIT 1")
    assert leitura["situacao"] == "LIDA", leitura["erro"]
    documentos = json.loads(leitura["documentos_json"])
    assert [d["tipo"] for d in documentos] == ["IDENTIDADE", "DNV"]
    assert documentos[1]["triada_como"] == "IDENTIDADE"
    assert ia.pedidos.count(("DNV", "dnv.png")) == 1
    html = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "relida como DNV" in html and "Maria Exemplo da Silva" in html
