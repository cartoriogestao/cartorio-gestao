"""Os acertos do protesto de 30/10/2026, medidos no envio do XML P à CENPROT.

O QUE ESTES TESTES GUARDAM
  - o cedente do título H vai com o CEP e a UF da serventia, sem documento;
    sem os dois na configuração, o título espera com o motivo;
  - dois atos com a mesma chave não entram como dois títulos: fundem se têm a
    mesma data, folha e instrumento; divergindo, o par espera, e os outros seguem;
  - o devedor do protocolo com dois títulos é o do próprio título, e nunca o da
    primeira linha do protocolo;
  - arquivo recusado devolve os atos, e arquivo que subiu sem alguns atos devolve
    só esses, sempre com motivo;
  - o retido com aceite da CRA é informação, e o retido sem resposta é pendência;
  - edital do E-Ofício não cobra comprovante;
  - o pagamento de correção do título liquidado no portal não vai ao D;
  - o arquivo de emolumentos leva uma linha por chave;
  - a ocorrência da Central vale em qualquer dos dois campos;
  - número no lugar do nome do apresentante não é nome.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import cenprot_conferencia as C
import centrais_cred as CRED
import protesto as PT
import protesto_arquivo as PA
import protesto_aviso as AV
import protesto_cenprot as PC
import protesto_cenprot_xml as X
import protesto_retorno as PRE
import protesto_roteiro as RT
from banco_de_teste import conexao_de_teste

from test_cenprot_conferencia import banco as banco_da_conferencia
from test_cenprot_conferencia import titulo as titulo_da_conferencia
from test_protesto_aviso_web import _con, _token, s, titulo_apontado  # noqa: F401
from test_protesto_cenprot_xml import _titulo
from test_protesto_cenprot_xml_tela import CHAVE, pronto  # noqa: F401
from test_protesto_instrumento_assinado import chave_e_cert  # noqa: F401
from test_protesto_roteiro import (HOJE, ONTEM, _anexo, _ato, _obrigacao,  # noqa: F401
                                   _titulo as titulo_do_roteiro, casa)
from test_retorno_protocolo_ja_informado import (aceitar_os_dois, apontar_e_intimar,
                                                 ato_id)
from test_retorno_protocolo_ja_informado import banco as banco_do_retorno
from test_retorno_protocolo_ja_informado import (desfazer, gerar, mesmo_protocolo,
                                                 novo_ato, protestar)
from test_retorno_protocolo_ja_informado import titulo as titulo_do_retorno

AGORA = "2026-10-30T10:00:00"
MOTIVO = "O portal recusou na validação do esquema."


def _gerar(con, dia="2026-10-30"):
    with con:
        return X.gerar(con, "P", uf="MA", comarca="2199999", cartorio="01",
                       dia=dia, agora=AGORA)


# ------------------------------------------------------ 1. o cedente do H


def test_o_cedente_do_titulo_h_leva_so_o_cep_e_a_uf_da_serventia(pronto, s):
    con = _con(s)
    r = _gerar(con)
    raiz = ET.fromstring(bytes(X.arquivo(con, r["id"])["conteudo"]))
    cedente = raiz.find(".//titulo/cedente")
    endereco = cedente.find("enderecos/endereco")
    assert {e.tag: (e.text or "") for e in endereco} == {
        "endereco": "", "complemento": "", "cep": "65000000", "bairro": "",
        "cidade": "", "uf": "MA"}
    assert cedente.find("CNPJ") is None and cedente.find("CPF") is None
    # O XSD da CENPROT não está no repositório: confere-se o que ele recusou.
    assert raiz.find(".//titulo/endosso").text == "H"
    for e in raiz.iter("cep"):
        assert (e.text or "").strip()
    for e in raiz.iter("uf"):
        assert (e.text or "").strip()


@pytest.mark.parametrize("chave", ["serventia_cep", "ri_uf"])
def test_sem_cep_ou_uf_da_serventia_o_titulo_h_espera_com_o_motivo(pronto, s, chave):
    con = _con(s)
    with con:
        con.execute("DELETE FROM settings WHERE key = ?", (chave,))
    lista = X.pendentes(con, "P")
    assert not lista["entram"]
    assert "CEP e a UF da serventia" in lista["fora"][0]["motivo"]


def test_o_cedente_que_e_o_sacador_continua_com_o_endereco_do_arquivo():
    cedente, sacador, endosso = X._cedente_e_sacador({
        "cedente_nome": "LOJA", "cedente_nome_2": "LOJA", "cedente_cep": "65000000",
        "cedente_uf": "MA", "cedente_documento": "00000001000055"})
    assert endosso == "G" and cedente["endereco"]["cep"] == "65000000"
    assert cedente["documento"] == sacador["documento"]


# --------------------------------------------- 2. a mesma chave, dois atos


def _item(ato, titulo_id, **do_titulo) -> dict:
    return {"ato_id": ato, "tipo": "PROTESTO", "data_ato": "2026-10-23",
            "titulo_id": titulo_id, "protocolo": "2610070011", "chave": CHAVE,
            "letra": "P", "titulo": _titulo(id=CHAVE, **do_titulo),
            "apresentante": {"codigo": "901", "nome": "PROCURADORIA EXEMPLO",
                             "documento": "00000001000055",
                             "tipo_apresentante": "0"}}


def _dois_devedores() -> tuple[list, list]:
    return ([{"nome": "PRIMEIRO EXEMPLO", "documento": "00000000191",
              "intimado": True, "edital": False, "endereco": {}}],
            [{"nome": "SEGUNDA EXEMPLO LTDA", "documento": "00000001000055",
              "intimado": False, "edital": True, "endereco": {}}])


def test_mesma_data_folha_e_instrumento_fundem_num_titulo_com_dois_devedores():
    um, dois = _dois_devedores()
    r = X._uma_chave_um_titulo(
        [_item(1, 10, devedores=um), _item(2, 11, devedores=dois)], [])
    assert not r["fora"]
    [so] = r["entram"]
    assert so["atos_ids"] == [1, 2]
    assert [d["nome"] for d in so["titulo"]["devedores"]] == [
        "PRIMEIRO EXEMPLO", "SEGUNDA EXEMPLO LTDA"]
    assert [d["edital"] for d in so["titulo"]["devedores"]] == [False, True]


@pytest.mark.parametrize("campo,valor", [("data_ocorrencia", "2026-10-28"),
                                         ("num_folha", "200"),
                                         ("instrumento", b"0\x82OUTRO")])
def test_divergindo_o_par_espera_com_o_motivo_e_os_outros_seguem(campo, valor):
    um, dois = _dois_devedores()
    outro = _item(3, 12)
    outro["titulo"]["id"] = "21999990141243301260418"
    r = X._uma_chave_um_titulo(
        [_item(1, 10, devedores=um), _item(2, 11, devedores=dois, **{campo: valor}),
         outro], [])
    assert [i["ato_id"] for i in r["entram"]] == [3]
    assert sorted(i["ato_id"] for i in r["fora"]) == [1, 2]
    assert all("decisão do oficial" in i["motivo"] for i in r["fora"])


def test_com_um_do_par_ja_esperando_o_outro_nao_sai_sozinho():
    um, _ = _dois_devedores()
    esperando = {"ato_id": 2, "tipo": "PROTESTO", "data_ato": "2026-10-23",
                 "titulo_id": 11, "protocolo": "2610070011", "chave": CHAVE,
                 "motivo": "o instrumento do protesto ainda não foi assinado"}
    r = X._uma_chave_um_titulo([_item(1, 10, devedores=um)], [esperando])
    assert not r["entram"]
    assert sorted(i["ato_id"] for i in r["fora"]) == [1, 2]


def test_o_titulos_total_bate_com_os_titulos_do_arquivo():
    um, dois = _dois_devedores()
    a = _titulo(id=CHAVE, devedores=um + dois)
    b = _titulo(id="21999990141243301260418")
    raiz = ET.fromstring(X.escrever(
        letra="P", uf="MA", comarca="2199999", cartorio="01",
        apresentantes=[{"codigo": "901", "nome": "PROCURADORIA EXEMPLO",
                        "documento": "00000001000055", "tipo_apresentante": "0",
                        "titulos": [a, b]}]))
    for ap in raiz.iter("apresentante"):
        titulos = ap.find("titulos")
        assert int(titulos.get("total")) == len(titulos.findall("titulo"))
    ids = [t.get("id") for t in raiz.iter("titulo")]
    assert len(ids) == len(set(ids))
    assert raiz.find(".//titulo/devedores").get("total") == "2"


def test_gerar_marca_os_dois_atos_do_titulo_fundido(s, monkeypatch):
    tid = titulo_apontado(s)
    con = _con(s)
    with con:
        atos = [con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, criado_em)
               VALUES (?, 'PROTESTO', '2026-10-28', '2026-10-28')""",
            (tid,)).lastrowid for _ in range(2)]
    fundido = dict(_item(atos[0], tid), atos_ids=atos)
    monkeypatch.setattr(X, "pendentes", lambda *a, **k: {"entram": [fundido],
                                                         "fora": []})
    r = _gerar(con)
    assert r["titulos"] == 1
    assert {x[0] for x in con.execute(
        "SELECT cenprot_xml_id FROM pt_atos WHERE id IN (?, ?)", tuple(atos))} == {
            r["id"]}


# ------------------------------------- 3. o devedor do protocolo com dois títulos


def _segundo_titulo_no_protocolo(con, tid: int) -> None:
    con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, situacao, origem,
               origem_chave, protocolo, apresentante_codigo, criado_em)
           SELECT especie, numero_titulo, 'PROTESTADO', origem, 'outro:1',
                  protocolo, apresentante_codigo, criado_em
             FROM pt_titulos WHERE id = ?""", (tid,))


def _devedor_gravado(con, tid: int, *, cep="65000000") -> None:
    con.execute(
        """UPDATE pt_devedores SET nome='DEVEDOR DESTE TITULO', documento_numero=?,
               cep=?, uf='MA', endereco='RUA EXEMPLO, 1', cidade='CIDADE EXEMPLO'
            WHERE titulo_id=?""", ("00000000191", cep, tid))


def test_com_dois_titulos_no_protocolo_o_devedor_e_o_do_proprio_titulo(pronto, s):
    """O `REGISTRO` do `pronto` traz outro devedor: é a primeira linha do
    protocolo, e ela não é deste título."""
    con = _con(s)
    with con:
        _segundo_titulo_no_protocolo(con, pronto)
        _devedor_gravado(con, pronto)
    [item] = X.pendentes(con, "P")["entram"]
    [devedor] = item["titulo"]["devedores"]
    assert devedor["nome"] == "DEVEDOR DESTE TITULO"
    assert devedor["documento"] == "00000000191"


def test_com_um_titulo_so_o_devedor_continua_vindo_do_arquivo(pronto, s):
    con = _con(s)
    with con:
        _devedor_gravado(con, pronto)
    [item] = X.pendentes(con, "P")["entram"]
    assert item["titulo"]["devedores"][0]["nome"] == "JOSÉ DA SILVA"


def test_o_devedor_da_ficha_sem_cep_espera_em_vez_de_derrubar_o_arquivo(pronto, s):
    con = _con(s)
    with con:
        _segundo_titulo_no_protocolo(con, pronto)
        _devedor_gravado(con, pronto, cep="")
    lista = X.pendentes(con, "P")
    assert not lista["entram"] and "sem CEP ou UF" in lista["fora"][0]["motivo"]


def _acervo_com_dois_devedores(protocolo: str):
    nomes = [c.nome for c in PA.TITULO_NA_REMESSA[:30]]
    campos = {n: f"Campo{i:02d}" for i, n in enumerate(nomes, start=1)}
    ac = conexao_de_teste()
    ac.execute(
        "CREATE TABLE tbSDT (intChave REAL, intProtocolo REAL, "
        + ", ".join(f"{c} TEXT" for c in campos.values()) + ", Campo39 TEXT)")
    linhas = [(1, "PRIMEIRA PESSOA", "2", "00000000000272"),
              (2, "SEGUNDA PESSOA", "2", "00000000000191")]
    for chave, nome, tipo, doc in linhas:
        ac.execute(
            f"""INSERT INTO tbSDT (intChave, intProtocolo, {campos['devedor_nome']},
                    {campos['devedor_tipo_de_documento']},
                    {campos['devedor_documento']})
                VALUES (?, ?, ?, ?, ?)""", (chave, int(protocolo), nome, tipo, doc))
    return ac


def test_com_duas_linhas_vale_a_linha_que_casa_com_o_devedor_do_titulo(pronto, s):
    con = _con(s)
    with con:
        _devedor_gravado(con, pronto)
    titulo = dict(con.execute("SELECT * FROM pt_titulos WHERE id = ?",
                              (pronto,)).fetchone())
    ac = _acervo_com_dois_devedores(titulo["protocolo"])
    primeira = X.registro_da_cra(con, dict(titulo, origem_chave="tbSDT:1"), ac)
    assert primeira["devedor_nome"] == "PRIMEIRA PESSOA"
    reg = X._registro_do_devedor(con, titulo, primeira, ac)
    assert reg["devedor_nome"] == "SEGUNDA PESSOA"


# ------------------------------------------------- 4. os atos que voltam à fila


def test_o_arquivo_recusado_devolve_os_atos_e_fica_como_foi(pronto, s):
    con = _con(s)
    r = _gerar(con)
    antes = bytes(X.arquivo(con, r["id"])["conteudo"])
    with con:
        feito = X.recusar_arquivo(con, r["id"], motivo=MOTIVO, agora=AGORA,
                                  usuario="OFICIAL")
    assert len(feito["atos"]) == 1
    arq = X.arquivo(con, r["id"])
    assert bytes(arq["conteudo"]) == antes
    assert arq["recusado_motivo"] == MOTIVO and arq["recusado_por"] == "OFICIAL"
    assert len(X.pendentes(con, "P")["entram"]) == 1
    # O sequencial conta o recusado: o nome não se repete.
    assert _gerar(con)["nome"].endswith("-02.xml")
    with pytest.raises(X.CenprotXmlError, match="já está marcado"):
        X.recusar_arquivo(con, r["id"], motivo=MOTIVO, agora=AGORA, usuario="OFICIAL")


def test_a_recusa_exige_motivo(pronto, s):
    con = _con(s)
    r = _gerar(con)
    with pytest.raises(X.CenprotXmlError, match="motivo"):
        X.recusar_arquivo(con, r["id"], motivo="curto", agora=AGORA, usuario="O")
    assert X.pendentes(con, "P")["entram"] == []


def test_arquivo_com_comprovante_nao_se_recusa_e_o_recusado_nao_pede_mais(
        pronto, s, tmp_path):
    con = _con(s)
    com = _gerar(con)
    with con:
        X.guardar_comprovante_do_envio(
            con, com["id"], nome="c.pdf", conteudo=b"%PDF-1.4 teste",
            pasta_de_arquivos=tmp_path, agora=AGORA)
    with pytest.raises(X.CenprotXmlError, match="comprovante"):
        X.recusar_arquivo(con, com["id"], motivo=MOTIVO, agora=AGORA, usuario="O")
    with con:
        con.execute("DELETE FROM attachments WHERE entity_id = ?", (com["id"],))
        X.recusar_arquivo(con, com["id"], motivo=MOTIVO, agora=AGORA, usuario="O")
    with pytest.raises(X.CenprotXmlError, match="recusado"):
        X.guardar_comprovante_do_envio(
            con, com["id"], nome="c.pdf", conteudo=b"%PDF-1.4 teste",
            pasta_de_arquivos=tmp_path, agora=AGORA)
    cobrado = _obrigacao(RT.cobrar_o_dia(con, agora="2026-10-30T16:00:00"),
                         "xml_sem_comprovante")
    assert cobrado["situacao"] == RT.FEITO


def test_a_devolucao_parcial_solta_so_os_escolhidos(pronto, s):
    con = _con(s)
    r = _gerar(con)
    with con:
        outro = con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, criado_em,
                   cenprot_xml_id)
               VALUES (?, 'PROTESTO', '2026-10-28', '2026-10-28', ?)""",
            (pronto, r["id"])).lastrowid
    ficam = [a["id"] for a in X.atos_do_arquivo(con, r["id"]) if a["id"] != outro]
    with pytest.raises(X.CenprotXmlError, match="Marque"):
        X.devolver_atos_escolhidos(con, r["id"], [], motivo=MOTIVO, agora=AGORA,
                                   usuario="O")
    with pytest.raises(X.CenprotXmlError, match="não está"):
        X.devolver_atos_escolhidos(con, r["id"], [outro, 999999], motivo=MOTIVO,
                                   agora=AGORA, usuario="O")
    with pytest.raises(X.CenprotXmlError, match="todos os atos"):
        X.devolver_atos_escolhidos(con, r["id"], [outro, *ficam], motivo=MOTIVO,
                                   agora=AGORA, usuario="O")
    with pytest.raises(X.CenprotXmlError, match="motivo"):
        X.devolver_atos_escolhidos(con, r["id"], [outro], motivo="", agora=AGORA,
                                   usuario="O")
    with con:
        feito = X.devolver_atos_escolhidos(con, r["id"], [str(outro)], motivo=MOTIVO,
                                           agora=AGORA, usuario="O")
    assert feito["atos"] == [outro] and feito["ficaram"] == len(ficam)
    assert [a["id"] for a in X.atos_do_arquivo(con, r["id"])] == ficam
    arq = X.arquivo(con, r["id"])
    assert X.devolucoes_do_arquivo(arq)[0]["atos"] == [outro]
    assert not arq["recusado_em"]


def test_as_duas_acoes_sao_so_do_oficial_e_do_gerente_e_vao_a_auditoria(pronto, s):
    con = _con(s)
    r = _gerar(con)
    c = s["c"]
    pagina = c.get("/protesto/cenprot-xml").get_data(as_text=True)
    assert "A CENPROT recusou este arquivo: devolver os atos à fila" in pagina
    rota = f"/protesto/cenprot-xml/{r['id']}/recusado"
    sem = c.post(rota, data={"csrf_token": _token(pagina), "motivo": ""},
                 follow_redirects=True).get_data(as_text=True)
    assert "Escreva o motivo" in sem
    feita = c.post(rota, data={"csrf_token": _token(pagina), "motivo": MOTIVO},
                   follow_redirects=True).get_data(as_text=True)
    assert "recusado pela CENPROT" in feita
    con = _con(s)
    [linha] = con.execute(
        "SELECT details FROM audit_logs WHERE action='PROTESTO_CENPROT_XML_RECUSADO'"
    ).fetchall()
    assert MOTIVO in linha["details"]
    codigo = (Path(__file__).resolve().parents[1] / "atribuicoes_web.py").read_text(
        encoding="utf-8")
    for nome in ("protesto_cenprot_xml_recusado",
                 "protesto_cenprot_xml_devolver_atos"):
        antes = codigo[codigo.index(f"def {nome}(") - 60:codigo.index(f"def {nome}(")]
        assert '@roles_required("ADMIN", "MANAGER")' in antes, nome


# --------------------------------------------- 5. conduta 1: o retido certo


def _gancho_do_repetido(con) -> dict:
    g = next(x for x in RT.GANCHOS if x["chave"] == "protocolo_repetido")
    return RT._rodar_gancho(con, RT._contexto(con, AGORA), g)


def _dois_titulos_um_protocolo(con) -> tuple[int, int]:
    a = titulo_do_retorno(con, chave="1")
    b = titulo_do_retorno(con, chave="2", cpf="00000000272")
    apontar_e_intimar(con, a)
    apontar_e_intimar(con, b)
    mesmo_protocolo(con, a, b)
    return a, b


def test_o_retido_com_aceite_da_cra_e_informacao_e_nao_pendencia():
    con = banco_do_retorno()
    a, b = _dois_titulos_um_protocolo(con)
    protestar(con, a)
    protestar(con, b)
    r = gerar(con)
    aceitar_os_dois(con, r)
    desfazer(con, ato_id(con, b, "PROTESTO"))
    refeito = novo_ato(con, b, "PROTESTO", "2026-10-28T14:31:00")
    [linha] = [l for l in PRE.protocolos_repetidos_na_fila(con)
               if int(l["ato_id"]) == refeito]
    assert linha["situacao"] == "RETIDO" and linha["retido_por"] == "ACEITE"
    assert linha["so_informacao"] is True
    o = _gancho_do_repetido(con)
    assert o["situacao"] == RT.FEITO and o["faltam"] == 0
    assert "já aceitou" in o["nota"] and "não é pendência" in o["nota"]
    assert RT.pendencias_para_encerrar(
        [{"n": 1, "titulo": "x", "obrigacoes": [o]}]) == []


def test_o_retido_por_arquivo_sem_resposta_continua_pendente():
    con = banco_do_retorno()
    a, b = _dois_titulos_um_protocolo(con)
    protestar(con, a)
    gerar(con)
    protestar(con, b)
    o = _gancho_do_repetido(con)
    assert o["situacao"] == RT.PENDENTE and o["faltam"] == 1
    assert not o["nota"]
    [linha] = PRE.protocolos_repetidos_na_fila(con)
    assert linha["retido_por"] == "SEM_RESPOSTA" and not linha["so_informacao"]


# ------------------------------------------------ 6. conduta 5: edital antigo


def _edital(con, tid, numero, *, origem=None) -> int:
    aviso = con.execute(
        """INSERT INTO pt_avisos(titulo_id, numero, ano, situacao, emitido_em,
               criado_em) VALUES (?, ?, 2026, 'EDITAL', ?, ?)""",
        (tid, numero, ONTEM, ONTEM)).lastrowid
    return con.execute(
        """INSERT INTO pt_editais(numero, ano, aviso_id, titulo_id, publicado_em,
               teor, criado_em, origem)
           VALUES (?, 2026, ?, ?, ?, 'teor', ?, ?)""",
        (numero, aviso, tid, ONTEM, ONTEM, origem)).lastrowid


def test_edital_do_eoficio_fica_visivel_e_nao_e_cobrado(casa):
    tid = titulo_do_roteiro(casa)
    _edital(casa, tid, 1, origem="EOFICIO")
    casa.commit()
    o = _obrigacao(RT.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"),
                   "editais_sem_comprovante")
    assert o["situacao"] == RT.FEITO and o["atrasados"] == 0
    assert "do E-Ofício" in o["nota"]
    [d] = AV.envios_do_edital(casa, HOJE)
    assert d["do_eoficio"] == 1 and d["completo"]


def test_no_dia_misto_so_o_edital_deste_sistema_e_cobrado(casa):
    tid = titulo_do_roteiro(casa)
    _edital(casa, tid, 1, origem="EOFICIO")
    novo = _edital(casa, tid, 2)
    casa.commit()
    o = _obrigacao(RT.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"),
                   "editais_sem_comprovante")
    assert o["situacao"] == RT.ATRASADO and o["faltam"] == 1
    assert "0 de 1 edital(is)" in o["lista"][0]["texto"]
    _anexo(casa, "PT_EDITAL_CENPROT", novo)
    assert _obrigacao(RT.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"),
                      "editais_sem_comprovante")["situacao"] == RT.FEITO


# ---------------------------------------- 7. conduta 8: o pago da liquidação


def _pago_por_correcao(con) -> tuple[int, int]:
    tid = titulo_do_roteiro(con, situacao="PAGO")
    ato = _ato(con, tid, "PAGAMENTO", ONTEM + "T09:00:00", origem="CORRECAO")
    return tid, ato


def _liquidacao(con, tid, *, anulada=None) -> None:
    con.execute(
        """INSERT INTO cn_liquidacoes_portal(pedido, titulo_id, liquidada_em,
               afirmacao, registrada_em, registrada_por, anulada_em)
           VALUES ('9900001', ?, ?, 'afirmacao de teste', ?, 'OFICIAL', ?)""",
        (tid, ONTEM, ONTEM, anulada))
    con.commit()


def _na_fila_do_d(con, ato) -> bool:
    lista = X.pendentes(con, "D")
    return ato in {i["ato_id"] for i in lista["entram"] + lista["fora"]}


def test_o_pagamento_de_correcao_do_titulo_liquidado_nao_vai_ao_d(casa):
    tid, ato = _pago_por_correcao(casa)
    assert _na_fila_do_d(casa, ato), "sem liquidação ele vai ao D"
    _liquidacao(casa, tid)
    assert not _na_fila_do_d(casa, ato)
    o = _obrigacao(RT.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"), "atos_sem_xml")
    assert o["situacao"] == RT.FEITO


def test_liquidacao_anulada_devolve_o_pagamento_ao_d(casa):
    tid, ato = _pago_por_correcao(casa)
    _liquidacao(casa, tid, anulada=HOJE)
    assert _na_fila_do_d(casa, ato)


def test_o_pagamento_comum_do_titulo_liquidado_continua_no_d(casa):
    tid = titulo_do_roteiro(casa, situacao="PAGO")
    ato = _ato(casa, tid, "PAGAMENTO", ONTEM + "T09:00:00")
    _liquidacao(casa, tid)
    assert _na_fila_do_d(casa, ato)


# ---------------------------------------- 8. conduta 9: a ocorrência manda


@pytest.mark.parametrize("ocorrencia,nome,estado", [
    ("2", "Protestado", C.PROTESTADO),
    ("1", "Pago", C.PAGO),
    ("A", "Protesto Cancelado", C.CANCELADO),
    ("0", "Apontamento", C.EM_ANDAMENTO),
])
def test_a_ocorrencia_vale_como_a_api_a_devolve(ocorrencia, nome, estado):
    assert C.estado_da_central("Apontado / em andamento", ocorrencia, nome) == estado


def test_o_status_que_tira_do_protesto_continua_ganhando():
    assert C.estado_da_central("Pago", "2", "Protestado") == C.PAGO


def _conferencia_guardada(con, tid, ocorrencia, nome) -> None:
    """Como está na produção: o estado gravado é o da leitura antiga."""
    con.execute(
        """INSERT INTO cn_conferencias(titulo_id, ambiente, pedido, resultado,
               consultada_em, central_estado, central_status, central_ocorrencia,
               central_codigo)
           VALUES (?, ?, '9900001', 'ACHOU', ?, 'EM_ANDAMENTO',
                   'Apontado / em andamento', ?, ?)""",
        (tid, CRED.PRODUCAO, AGORA, ocorrencia, nome))
    con.commit()


@pytest.mark.parametrize("situacao,ocorrencia,nome", [
    ("PROTESTADO", "2", "Protestado"),
    ("CANCELADO", "A", "Protesto Cancelado"),
])
def test_a_conferencia_guardada_confere_sem_nova_consulta(situacao, ocorrencia, nome):
    con = banco_da_conferencia()
    tid = titulo_da_conferencia(con, situacao=situacao,
                                origem_chave="CENPROT-PEDIDO:9900001")
    _conferencia_guardada(con, tid, ocorrencia, nome)
    linha = C.da_ficha(con, tid)
    assert linha["conferencia"]["central_estado"] != C.EM_ANDAMENTO
    assert [a["regra"] for a in linha["achados"]] == []


def test_protestado_aqui_e_em_andamento_la_continua_a_conferir():
    con = banco_da_conferencia()
    tid = titulo_da_conferencia(con, situacao="PROTESTADO",
                                origem_chave="CENPROT-PEDIDO:9900001")
    _conferencia_guardada(con, tid, "0", "Apontamento")
    assert "PROTESTO_QUE_A_CENTRAL_NAO_VIU" in [
        a["regra"] for a in C.da_ficha(con, tid)["achados"]]


# ------------------------------------------- 9. número não é nome de apresentante


def test_numero_nao_e_nome_de_apresentante():
    assert PA.nome_de_apresentante("000000009000002") == ""
    assert PA.nome_de_apresentante("  BANCO EXEMPLO ") == "BANCO EXEMPLO"
    assert PA.nome_de_apresentante(None) == ""


def test_a_leitura_guarda_a_identificacao_no_lugar_dela():
    dados = PA.para_apontamento({"codigo_do_apresentante": "748",
                                 "identificacao_do_apresentante": "000000009000002"})
    assert dados["apresentante_nome"] is None
    assert dados["cra_identificacao"] == "000000009000002"


def _titulo_da_remessa(s, *, nome="000000009000002") -> int:
    tid = titulo_apontado(s)
    con = _con(s)
    with con:
        con.execute("UPDATE pt_titulos SET apresentante_nome=? WHERE id=?", (nome, tid))
        X.gravar_apresentante(con, codigo="001", nome="BANCO DO CADASTRO SA",
                              documento="00000001000055", tipo_apresentante="0",
                              agora=AGORA)
    con.close()
    return tid


def test_a_ficha_prefere_o_cadastro_quando_o_nome_e_numero(s):
    tid = _titulo_da_remessa(s)
    con = _con(s)
    t = dict(con.execute("SELECT * FROM pt_titulos WHERE id=?", (tid,)).fetchone())
    assert PT.apresentante_do_titulo(con, t)["nome"] == "BANCO DO CADASTRO SA"
    linhas = [{"apresentante_nome": t["apresentante_nome"],
               "apresentante_codigo": "001"}]
    X.nomes_do_cadastro_no_lugar_de_numero(con, linhas)
    assert linhas[0]["apresentante_nome"] == "BANCO DO CADASTRO SA"


def test_o_nome_de_verdade_do_titulo_continua_valendo(s):
    tid = _titulo_da_remessa(s, nome="LOJA QUE TROUXE O TITULO")
    con = _con(s)
    t = dict(con.execute("SELECT * FROM pt_titulos WHERE id=?", (tid,)).fetchone())
    assert PT.apresentante_do_titulo(con, t)["nome"] == "LOJA QUE TROUXE O TITULO"


def test_o_tab_com_numero_no_nome_espera_e_nao_cai_no_cadastro(pronto, s):
    con = _con(s)
    with con:
        con.execute("""UPDATE pt_titulos SET apresentante_codigo='TAB',
                         apresentante_nome='000000009000002',
                         apresentante_documento='00000010000127',
                         apresentante_tipo='4' WHERE id=?""", (pronto,))
    lista = X.pendentes(con, "P")
    assert not lista["entram"] and "o nome" in lista["fora"][0]["motivo"]


# -------------------------------------------- 10. emolumentos: uma linha por chave


def _emolumentos(monkeypatch, titulos: list[dict], precos: dict) -> dict:
    monkeypatch.setattr(PC.custas, "vigencia_do_dia", lambda con, data: {"codigo": 1})
    monkeypatch.setattr(PC, "constantes", lambda con, v: {"faltando": False})
    monkeypatch.setattr(PC, "titulos_do_arquivo", lambda con: titulos)
    monkeypatch.setattr(PC, "precos_do_titulo",
                        lambda con, valor, vigencia: precos[valor])
    return PC.gerar_emolumentos(None, comarca="2198765", cartorio="01", uf="MA",
                                data="2026-08-31")


def _protestado(tid, chave, valor) -> dict:
    return {"id": tid, "chave_cenprot": chave, "valor_centavos": valor,
            "numero_titulo": "T", "protocolo": "2610070011"}


PRECO = {"retirada": 9654, "cancelamento": 24826}
OUTRO_PRECO = {"retirada": 10000, "cancelamento": 25000}
SEM_FAIXA = {"retirada": None, "cancelamento": None}


def test_a_chave_de_dois_titulos_sai_numa_linha_so(monkeypatch):
    r = _emolumentos(monkeypatch,
                     [_protestado(1, CHAVE, 100), _protestado(2, CHAVE, 100),
                      _protestado(3, "21999990141243301260418", 100)], {100: PRECO})
    assert r["linhas"] == 2 and r["fora"] == []
    corpo = r["conteudo"].split("\r\n")[1:-1]
    assert corpo[0] == f"{CHAVE}|96.54|248.26|2198765|01|20260831"
    assert len({l.split("|")[0] for l in corpo}) == 2


def test_precos_divergentes_na_mesma_chave_ficam_fora_com_o_motivo(monkeypatch):
    r = _emolumentos(monkeypatch,
                     [_protestado(1, CHAVE, 100), _protestado(2, CHAVE, 200)],
                     {100: PRECO, 200: OUTRO_PRECO})
    assert r["linhas"] == 0 and CHAVE not in r["conteudo"]
    assert sorted(t["id"] for t in r["fora"]) == [1, 2]
    assert all("precos diferentes" in t["motivo"] for t in r["fora"])
    assert "#1" in PC.frase_do_que_ficou_fora(r)


def test_um_do_par_sem_faixa_leva_a_chave_para_fora(monkeypatch):
    r = _emolumentos(monkeypatch,
                     [_protestado(1, CHAVE, 100), _protestado(2, CHAVE, 200)],
                     {100: PRECO, 200: SEM_FAIXA})
    assert r["linhas"] == 0 and sorted(t["id"] for t in r["fora"]) == [1, 2]
    assert "nao cai em nenhuma faixa" in r["fora"][1]["motivo"]


def test_o_retorno_continua_levando_a_identificacao_da_remessa():
    """É o que a CRA espera de volta nas posições 005/019."""
    con = banco_do_retorno()
    tid = PT.cadastrar_titulo(con, {
        "apresentante_codigo": "901", "apresentante_nome": "BANCO DO CABECALHO",
        "cra_identificacao": "000000009000002", "especie": "DMI",
        "numero_titulo": "77/1", "nosso_numero": "77/1",
        "data_emissao": "2026-01-05", "data_vencimento": "2026-02-05",
        "valor": "100,00", "saldo": "100,00", "praca_protesto": "CIDADE EXEMPLO",
        "motivo_protesto": "1",
        "cedente": {"nome": "LOJA EXEMPLO", "documento": "00000001000055"},
        "devedores": [{"nome": "DEVEDOR EXEMPLO", "CPF": "00000000191",
                       "enderecos": [{"endereco": "RUA EXEMPLO, 1", "uf": "MA",
                                      "cidade": "Cidade Exemplo"}]}]},
        origem="CRA", origem_chave="lote:901:1", agora=AGORA)
    apontar_e_intimar(con, tid)
    protestar(con, tid)
    feito = PRE.montar(con, apresentante_codigo="901", dia="2026-10-30", marca="A")
    [t] = PA.ler(feito["conteudo"]).titulos
    assert t["identificacao_do_apresentante"] == "000000009000002"
