"""
A busca em texto livre no acervo do RI e o resumo da situacao juridica.

O PEDIDO (o oficial, 26/10/2026)
    1. procurar no TEOR de todas as fichas — nome, CPF, lugar, frase —, com o
       trecho destacado e o link para a ficha; busca sensivel, registrada
       na auditoria — e, por decisao do oficial no mesmo dia («todos podem
       usar»), aberta a todo usuario humano logado: ADMIN, MANAGER, USER e
       AUDITOR (ler e o papel do auditor). O robo continua vedado;
    2. na ficha, o resumo da situacao juridica em um clique — proprietarios,
       onus, cadeia dominial, CNIB, prenotacoes, notas devolutivas e os atos
       do teor —, sem IA, com a marca «Não é certidão» bem visivel, e sem
       nunca dizer «livre» quando o sistema so nao tem onus lavrado.

POR QUE TESTE DE TELA
    O que o balcao usa e a tela. Os testes de dominio provam a regra (o termo
    vira expressao regular, o trecho sai escapado); os de tela provam que a
    rota recusa o robo e aceita os quatro papeis humanos, nao poe o termo no
    endereco, grava a auditoria sem o termo em claro (impressao com a chave do
    servidor e o CPF mascarado), e que a marca e a frase do onus chegam ao HTML.

Testes escritos e NAO executados na maquina de desenvolvimento (sobrecarga),
por ordem do oficial em 26/10/2026; a suite completa roda na maquina do merge.

Os nomes e documentos sao ficticios (mario, beatriz, carla; CPF de teste).
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_busca_acervo as BUSCA  # noqa: E402
import ri_situacao_juridica as SITJ  # noqa: E402
import ri_numeros_do_teor as NUMT  # noqa: E402
from conftest import cg_login  # noqa: E402

CPF = "00000000191"
CPF_COM_MASCARA = "000.000.001-91"


# ------------------------------------------------------------ o dominio

def test_o_termo_ignora_acento_caixa_e_a_marca_do_html():
    p = BUSCA.padrao_do_termo("joao da conceicao")
    teor = "<p>OUTORGANTE: JOÃO DA <em>CONCEIÇÃO</em></p>"
    assert re.search(p.regex_python, teor)
    assert p.tipo == "TEXTO"


def test_o_cpf_acha_as_grafias_do_acervo_e_so_inteiro():
    for digitado in (CPF, CPF_COM_MASCARA):
        p = BUSCA.padrao_do_termo(digitado)
        assert p.tipo == "DOCUMENTO"
        for grafia in ("CPF 000.000.001-91,", "CPF 00000000191.", "CPF 000000001-91 ",
                       "CPF 000.000.001.91;"):
            assert re.search(p.regex_python, grafia), (digitado, grafia)
        # o CPF dentro de um numero maior nao e o CPF
        assert not re.search(p.regex_python, "protocolo 9000000001919")


def test_o_numero_nao_acha_os_digitos_dentro_de_outro_numero():
    """A regra do relato #55: «3110» nao acha o CPF que tem 3110 dentro."""
    p = BUSCA.padrao_do_termo("3110")
    assert re.search(p.regex_python, "matrícula 3.110 do livro")
    assert re.search(p.regex_python, "matrícula 3110.")
    assert not re.search(p.regex_python, "CPF 31102233344")
    assert not re.search(p.regex_python, "matrícula 13110")


def test_termo_curto_e_recusado_com_frase_para_o_balcao():
    for curto in ("da", "12", "  "):
        try:
            BUSCA.padrao_do_termo(curto)
        except BUSCA.BuscaError as e:
            assert str(e)
        else:
            raise AssertionError(f"aceitou {curto!r}")


def test_o_trecho_escapa_o_teor_e_marca_so_o_achado():
    teor = "<p>VENDEDOR: <script>alert(1)</script> MARIO EXEMPLO, CPF 000.000.001-91</p>"
    trechos, n = BUSCA.trechos_destacados(teor, [BUSCA.padrao_do_termo("mario exemplo")])
    assert n == 1
    assert "<mark>MARIO EXEMPLO</mark>" in trechos[0]
    assert "<script" not in trechos[0]


def test_a_impressao_e_a_mesma_para_o_mesmo_termo_e_nao_e_o_termo():
    a = BUSCA.impressao_da_busca("Mário  Exemplo")
    assert a == BUSCA.impressao_da_busca("MARIO EXEMPLO")
    assert "MARIO" not in a.upper()


def test_paragrafos_do_teor_partem_nos_rotulos_desta_matricula():
    teor = ("<p>IMÓVEL: lote 7.</p><p>R-1/1.234 - COMPRA E VENDA.</p><p>segue o R-1</p>"
            "<p>R-2/1.234 - HIPOTECA em favor de banco.</p>"
            "<p>Transcrita sob R-5/999 de outra ficha.</p>")
    ps = NUMT.paragrafos_dos_atos_no_teor("1234", teor)
    assert [p["rotulo"] for p in ps] == ["R-1", "R-2"]
    assert "segue o R-1" in ps[0]["texto"]


# --------------------------------------------------------------- o acervo

def _banco(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _ficha(s, numero, teor, *, tipo="ACERVO") -> int:
    con = _banco(s)
    con.execute(
        """INSERT INTO ri_matriculas
           (numero, complemento, livro, livro_norm, tipo_ficha, situacao,
            conferido, origem, criado_em, teor, teor_formato)
           VALUES (?,'','2','2',?,'ATIVA',0,'EOFICIO','2026-07-31',?,'html')""",
        (str(numero), tipo, teor))
    mid = con.execute("SELECT MAX(id) i FROM ri_matriculas").fetchone()["i"]
    con.commit()
    con.close()
    return int(mid)


TEOR_COM_HIPOTECA = (
    "<p>IMÓVEL: um lote urbano.</p>"
    "<p>R-1/1.234 - COMPRA E VENDA. Adquirente: BEATRIZ EXEMPLO DA CONCEIÇÃO, "
    f"CPF {CPF_COM_MASCARA}.</p>"
    "<p>R-2/1.234 - HIPOTECA em favor de banco ficticio.</p>")


def _buscar(s, termo, modo="FRASE"):
    c = s["c"]
    html = c.get("/registro-imoveis/busca-no-acervo").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    return c.post("/registro-imoveis/busca-no-acervo",
                  data={"termo": termo, "modo": modo, "csrf_token": token})


# ------------------------------------------------------------- a busca

def test_a_busca_acha_pelo_teor_destaca_e_leva_a_ficha(cg_casa_logada):
    s = cg_casa_logada
    mid = _ficha(s, 1234, TEOR_COM_HIPOTECA)
    _ficha(s, 1235, "<p>IMÓVEL: outra coisa, de carla.</p>")
    r = _buscar(s, "beatriz exemplo da conceicao")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert f'"/registro-imoveis/{mid}"' in html
    assert "<mark>BEATRIZ EXEMPLO DA CONCEIÇÃO</mark>" in html
    assert '"/registro-imoveis/' + str(mid + 1) + '"' not in html


def test_o_cpf_com_e_sem_mascara_acha_a_mesma_ficha(cg_casa_logada):
    s = cg_casa_logada
    mid = _ficha(s, 1234, TEOR_COM_HIPOTECA)
    for termo in (CPF, CPF_COM_MASCARA):
        html = _buscar(s, termo).get_data(as_text=True)
        assert f'"/registro-imoveis/{mid}"' in html, termo


def test_o_termo_nao_vai_no_endereco_e_o_get_nao_procura(cg_casa_logada):
    s = cg_casa_logada
    _ficha(s, 1234, TEOR_COM_HIPOTECA)
    html = s["c"].get(f"/registro-imoveis/busca-no-acervo?termo={CPF}").get_data(as_text=True)
    assert "<mark>" not in html
    assert 'method="post"' in html


def test_a_busca_vai_a_auditoria_sem_o_termo_em_claro(cg_casa_logada):
    s = cg_casa_logada
    mid = _ficha(s, 1234, TEOR_COM_HIPOTECA)
    _buscar(s, CPF_COM_MASCARA)
    con = _banco(s)
    linha = con.execute(
        "SELECT * FROM audit_logs WHERE action='RI_BUSCA_NO_ACERVO' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    con.close()
    assert linha is not None
    detalhes = str(linha["details"])
    assert CPF not in detalhes and CPF_COM_MASCARA not in detalhes
    dados = json.loads(detalhes)
    # a impressao leva a chave do servidor: o sha256 puro de um CPF se desfaz
    # percorrendo os CPFs possiveis (conferencia de 26/10/2026)
    chave = s["app"].secret_key
    assert dados["impressao"] == BUSCA.impressao_da_busca(CPF_COM_MASCARA, chave=chave)
    assert dados["impressao"] != BUSCA.impressao_da_busca(CPF_COM_MASCARA)
    assert dados["documentos_mascarados"] == ["*********91"]
    assert dados["fichas"] == 1 and dados["ids"] == [mid]
    assert dados["tipos"] == ["DOCUMENTO"]
    assert dados["agente"] and dados["a_mando_de"]


@pytest.mark.parametrize("papel", ["AUDITOR", "MANAGER", "USER"])
def test_todo_usuario_humano_procura_no_acervo(cg_casa, papel):
    """«todos podem usar» — o oficial, 26/10/2026. A primeira versao recusava
    o AUDITOR; ler o acervo e justamente o papel dele."""
    s = cg_casa
    s["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    mid = _ficha(s, 1234, TEOR_COM_HIPOTECA)
    s["db"].create_user("carla", "CARLA EXEMPLO DE SOUSA", "Senha#12345", papel)
    cg_login(s["c"], "carla", "Senha#12345")
    assert s["c"].get("/registro-imoveis/busca-no-acervo").status_code == 200
    r = _buscar(s, CPF_COM_MASCARA)
    assert r.status_code == 200
    assert f'"/registro-imoveis/{mid}"' in r.get_data(as_text=True)
    con = _banco(s)
    linha = con.execute("SELECT username_snapshot FROM audit_logs "
                        "WHERE action='RI_BUSCA_NO_ACERVO' ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert linha is not None and linha["username_snapshot"] == "carla"
    # o resumo da situacao juridica tambem e de todos
    assert s["c"].get(f"/registro-imoveis/{mid}/situacao-juridica").status_code == 200
    # e o botao «Procurar no teor» aparece na lista para qualquer papel
    html = s["c"].get("/registro-imoveis").get_data(as_text=True)
    assert "Procurar no teor" in html


def test_a_impressao_com_chave_nao_e_a_do_sha256_puro():
    sem = BUSCA.impressao_da_busca(CPF)
    com = BUSCA.impressao_da_busca(CPF, chave="segredo-de-teste")
    assert com != sem and len(com) == 16
    assert com == BUSCA.impressao_da_busca(CPF, chave=b"segredo-de-teste")
    assert BUSCA.documento_mascarado(CPF_COM_MASCARA) == "*********91"
    assert BUSCA.documento_mascarado("11.111.111/1111-11") == "************11"


def test_o_robo_nao_varre_o_acervo(cg_casa):
    """Revisão de segurança de 26/10/2026 (PR #30): a conta de robô com papel
    USER — que a busca aceitaria pelo papel — recebe 403 no GET e no POST, e o
    POST com um CPF não chega à auditoria (nada foi procurado)."""
    import selo_robo as SR
    s = cg_casa
    assert SR.rota_vedada_ao_robo("ri_busca_no_acervo")
    s["db"].create_user("robo_ri", "Robo de Exemplo RI", "Senha#12345", "USER",
                        eh_robo=1)
    cg_login(s["c"], "robo_ri", "Senha#12345")
    assert s["c"].get("/registro-imoveis/busca-no-acervo").status_code == 403
    html = s["c"].get("/").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    r = s["c"].post("/registro-imoveis/busca-no-acervo",
                   data={"csrf_token": token, "termo": CPF_COM_MASCARA})
    assert r.status_code == 403
    con = _banco(s)
    linha = con.execute("SELECT id FROM audit_logs "
                        "WHERE action='RI_BUSCA_NO_ACERVO'").fetchone()
    con.close()
    assert linha is None
    # a ficha, que o robô já lia, continua com a guarda de sempre — o que se
    # fecha é a varredura barata do acervo por pessoa
    assert not SR.rota_vedada_ao_robo("ri_ficha")


def test_o_indice_de_trigramas_do_teor_existe(cg_casa_logada):
    con = _banco(cg_casa_logada)
    linha = con.execute(
        "SELECT indexdef FROM pg_indexes WHERE indexname='ix_ri_mat_teor_trgm' "
        "AND schemaname=current_schema()").fetchone()
    con.close()
    assert linha is not None and "gin_trgm_ops" in linha["indexdef"]


# ------------------------------------------------- a situacao juridica

def _secao(html, de, ate):
    return html.split(de, 1)[1].split(ate, 1)[0]


def test_a_situacao_traz_a_marca_e_o_onus_do_teor(cg_casa_logada):
    s = cg_casa_logada
    mid = _ficha(s, 1234, TEOR_COM_HIPOTECA)
    r = s["c"].get(f"/registro-imoveis/{mid}/situacao-juridica")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert html.count(SITJ.MARCA_NAO_E_CERTIDAO) == 2
    onus = _secao(html, "Ônus e gravames", "Cadeia dominial")
    assert "Possíveis ônus escritos no teor" in onus
    assert "R-02/1234" in onus
    assert "livre" not in onus.lower() and "nada consta" not in onus.lower()
    assert "Ficha do ACERVO" in html


def test_sem_onus_a_tela_nao_diz_livre(cg_casa_logada):
    s = cg_casa_logada
    mid = _ficha(s, 1236, "<p>IMÓVEL: lote sem nada.</p>")
    html = s["c"].get(f"/registro-imoveis/{mid}/situacao-juridica").get_data(as_text=True)
    onus = _secao(html, "Ônus e gravames", "Cadeia dominial")
    assert SITJ.FRASE_SEM_ONUS in onus
    assert "livre" not in onus.lower() and "nada consta" not in onus.lower()


def test_o_onus_lavrado_no_sistema_e_o_cancelado_nao(cg_casa_logada):
    s = cg_casa_logada
    mid = _ficha(s, 1237, "<p>IMÓVEL: lote.</p>")
    con = _banco(s)
    for numero, natureza, cancelado in ((1, "Hipoteca", 0), (2, "Penhora", 1)):
        con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, natureza_titulo,
                   teor, cancelado, origem, hash_ato, lavrado_em)
               VALUES (?, 'R', ?, '2026-01-02', ?, 'texto', ?, 'MANUAL', 'h', '2026-01-02')""",
            (mid, numero, natureza, cancelado))
    con.commit()
    con.close()
    html = s["c"].get(f"/registro-imoveis/{mid}/situacao-juridica").get_data(as_text=True)
    onus = _secao(html, "Ônus e gravames", "Cadeia dominial")
    assert "R-01/1237" in onus and "Hipoteca" in onus
    assert "Penhora" not in onus
    assert SITJ.FRASE_SEM_ONUS not in onus


def test_prenotacao_e_nota_aberta_aparecem_mesmo_amarradas_so_pelo_numero(cg_casa_logada):
    s = cg_casa_logada
    mid = _ficha(s, 1238, "<p>IMÓVEL: lote.</p>")
    con = _banco(s)
    con.execute(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao, natureza_titulo,
               matricula_numero, data_limite, situacao, criado_em)
           VALUES (90001, '1A', '2026-10-20', 'Compra e venda', '1.238', '2099-12-31',
                   'DEVOLVIDO', '2026-10-20')""")
    pid = con.execute("SELECT MAX(id) i FROM ri_protocolos").fetchone()["i"]
    con.execute(
        """INSERT INTO ri_notas_devolutivas (protocolo_id, numero, data_nota, exigencias,
               situacao, emitida_em)
           VALUES (?, 7, '2026-10-21', 'Apresentar a certidão de casamento.', 'ABERTA',
                   '2026-10-21')""", (pid,))
    con.commit()
    con.close()
    html = s["c"].get(f"/registro-imoveis/{mid}/situacao-juridica").get_data(as_text=True)
    assert "Protocolo <strong>90001</strong>" in html
    assert "amarrada só pelo número digitado" in html
    assert "Apresentar a certidão de casamento." in html


def test_a_situacao_nao_grava_nada_alem_da_auditoria(cg_casa_logada):
    s = cg_casa_logada
    mid = _ficha(s, 1234, TEOR_COM_HIPOTECA)
    con = _banco(s)
    antes = [con.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
             for t in ("ri_atos", "ri_partes", "ri_protocolos", "ri_cnib_decisoes")]
    con.close()
    s["c"].get(f"/registro-imoveis/{mid}/situacao-juridica")
    con = _banco(s)
    depois = [con.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
              for t in ("ri_atos", "ri_partes", "ri_protocolos", "ri_cnib_decisoes")]
    audit = con.execute(
        "SELECT COUNT(*) n FROM audit_logs WHERE action='RI_SITUACAO_JURIDICA_CONSULTADA'"
    ).fetchone()["n"]
    con.close()
    assert antes == depois
    assert audit == 1


def test_a_ficha_oferece_o_resumo(cg_casa_logada):
    s = cg_casa_logada
    mid = _ficha(s, 1234, TEOR_COM_HIPOTECA)
    html = s["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert f"/registro-imoveis/{mid}/situacao-juridica" in html
