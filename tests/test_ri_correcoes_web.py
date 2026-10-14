"""
As telas das tres correcoes, percorridas como o escrevente percorre.

POR QUE TESTE DE ROTA, E NAO SO DE MODULO
    As regras estao em `ri_correcoes.py` e `ri_expurgo.py`, e tem teste
    proprio. Estes testes protegem o CAMINHO: a matricula nova nascendo com o
    numero da serventia, o papel da parte corrigido pela ficha, o expurgo
    exigindo a palavra escrita, e — o que mais importou em 18/08/2026 — a
    CERTIDAO saindo sem marcacao de ODT no meio do texto certificado.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


# ------------------------------------------------- o aparelho desta bancada
#
# SEM SELADOR NAO SE LAVRA NADA desde 16/09/2026 — relato #77 mais o item 1
# («se falhar o selo, sempre suspender o ato»). Esta bancada fala de outra
# coisa; o selador esta aqui para o ato chegar a existir. Ver
# `tests/selador_de_bancada.py`.


@pytest.fixture(autouse=True)
def _o_selador_desta_bancada(cg_casa):
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(cg_casa) as aparelho:
        yield aparelho


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


def tela(s, caminho):
    return s["c"].get(caminho).get_data(as_text=True)


def postar(s, caminho, dados, origem=None):
    """Posta e devolve o HTML final.

    Decodifica tolerando byte invalido: a emissao de certidao redireciona para
    o download do .odt, que e binario — e o teste quer o texto do que der.
    """
    html = tela(s, origem or caminho)
    dados = dict(dados)
    dados["csrf_token"] = _token(html)
    r = s["c"].post(caminho, data=dados, follow_redirects=True)
    return r.get_data().decode("utf-8", errors="replace")


def banco(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def numeracao_do_sistema(s, livro="2"):
    """A bancada abre matricula no intervalo do SISTEMA, como a producao.

    **«Numeros menores que 4.015 sao acervo»** — regra informada pela
    serventia em 17/09/2026. Num banco vazio o primeiro numero e 1, e a ficha
    nasceria de acervo: o ato e recusado pedindo o numero «conforme o livro
    fisico», e nenhum destes testes fala de acervo. Nesta casa o proximo e
    4019.

    Nao mexe em quem ja semeou a numeracao — `semear_volumes` tem os numeros
    dele, que sao os do caso de 18/08/2026.
    """
    from ri_schema import PRIMEIRA_MATRICULA_DO_SISTEMA as PRIMEIRA
    con = banco(s)
    with con:
        if not con.execute("SELECT 1 FROM ri_numeracao WHERE livro=?",
                           (livro,)).fetchone():
            con.execute(
                """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso,
                       fixado_em)
                   VALUES (?,?,?,'2026-09-17')""",
                (livro, PRIMEIRA, PRIMEIRA - 1))
    con.close()


def abrir_matricula(s, livro="2", **campos) -> int:
    numeracao_do_sistema(s, livro)
    dados = {"livro": livro, "cidade": "Cidade Exemplo", "uf": "MA",
             "area_unidade": "ha"} | campos
    postar(s, "/registro-imoveis/nova", dados)
    con = banco(s)
    mid = con.execute("SELECT MAX(id) i FROM ri_matriculas").fetchone()["i"]
    con.close()
    return int(mid)


def lavrar(s, matricula_id, tipo="R", teor="TEOR DO ATO", **campos) -> int:
    # A NATUREZA E EXIGIDA ANTES DE O ATO NASCER — 15/09/2026. Sem ela a
    # rota recusa e nada se lavra; e por isso que estes testes ficaram
    # vermelhos naquela data, e nao por defeito do que eles medem.
    dados = {"tipo": tipo, "teor": teor, "data_ato": "2026-08-18",
             "natureza_titulo": "Compra e venda",
             "codigo_tj": "16.3"} | campos
    postar(s, f"/registro-imoveis/{matricula_id}/atos", dados,
           origem=f"/registro-imoveis/{matricula_id}")
    con = banco(s)
    aid = con.execute("SELECT MAX(id) i FROM ri_atos").fetchone()["i"]
    con.close()
    return int(aid)


def semear_volumes(s):
    """Reproduz o acervo: volume 2 em 4010 e volume 2S em 4013."""
    con = banco(s)
    for numero, livro in ((4010, "2"), (4013, "2S")):
        con.execute(
            """INSERT INTO ri_matriculas
               (numero, complemento, livro, livro_norm, tipo_ficha, situacao, conferido,
                origem, criado_em, teor_formato)
               VALUES (?,'',?,?,'ESTRUTURADA','ATIVA',0,'EOFICIO','2026-07-31','texto')""",
            (str(numero), livro, livro))
        con.execute("""INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso, fixado_em)
                       VALUES (?,?,?,'2026-08-13')""", (livro, numero + 1, numero))
    con.commit()
    con.close()


# ------------------------------------------------- numeracao pela serventia


def test_a_matricula_nova_pega_o_numero_da_serventia(s):
    """O caso de 18/08/2026: o volume 2 daria 4011, mas a serventia esta em 4013."""
    semear_volumes(s)
    mid = abrir_matricula(s, "2")
    con = banco(s)
    numero = con.execute("SELECT numero FROM ri_matriculas WHERE id=?", (mid,)).fetchone()["numero"]
    con.close()
    assert numero == "4014", "contar por volume daria 4011, numero que a serventia ja usou"


def test_a_tela_de_numeracao_mostra_a_serie_e_aponta_o_desalinhado(s):
    semear_volumes(s)
    html = tela(s, "/registro-imoveis/numeracao")
    assert "Próximo da série" in html
    assert "único na serventia" in html
    assert "desalinhado" in html, "o volume 2, parado em 4011, tem de aparecer marcado"


def test_fixar_numero_abaixo_do_maior_da_serie_e_recusado(s):
    semear_volumes(s)
    html = postar(s, "/registro-imoveis/numeracao",
                  {"livro": "2", "proximo_numero": "4011", "observacao": "tentativa"})
    assert "já usa o número 4013" in html
    assert "único na serventia, não no volume" in html


# ------------------------------------------------------------- renumeracao


def test_renumerar_pela_ficha_refaz_a_cadeia(s):
    # OS NUMEROS SAO DO INTERVALO DO SISTEMA — 17/09/2026. Eles eram 4011 e
    # 4014, que sao ACERVO pela regra da serventia («menores que 4.015»), e
    # ali o ato nao se lavra sem o numero do livro fisico. O que este teste
    # mede nao mudou: a corrente de hash se refaz e os dois numeros ficam na
    # auditoria.
    semear_volumes(s)
    mid = abrir_matricula(s, "2")
    con = banco(s)
    # A FICHA NASCEU 4011 — `semear_volumes` semeia o volume 2 ali —, e 4011 e
    # acervo. Levada para o intervalo do sistema, ela e ESTRUTURADA: a marca
    # acompanha o numero, como acompanharia na producao.
    con.execute("UPDATE ri_matriculas SET numero='4016', "
                "tipo_ficha='ESTRUTURADA' WHERE id=?", (mid,))
    con.commit()
    con.close()
    lavrar(s, mid, "R", "R-01/4016 TITULO DE DOMINIO")

    html = tela(s, f"/registro-imoveis/{mid}")
    assert "Hash divergente" not in html, "antes de renumerar a cadeia confere com 4016"

    html = postar(s, f"/registro-imoveis/{mid}/renumerar",
                  {"novo_numero": "4017", "motivo": "Número digitado errado na abertura"},
                  origem=f"/registro-imoveis/{mid}")
    assert "passou a ser a 4017" in html
    assert "Hash divergente" not in html, "depois de renumerar a cadeia tem de voltar a conferir"

    con = banco(s)
    assert con.execute("SELECT numero FROM ri_matriculas WHERE id=?",
                       (mid,)).fetchone()["numero"] == "4017"
    evento = con.execute("""SELECT details FROM audit_logs
                            WHERE action='RI_MATRICULA_RENUMERADA'""").fetchone()
    con.close()
    assert '"de": "4016"' in evento["details"] and '"para": "4017"' in evento["details"]
    assert "hash_antigo" in evento["details"], "os dois hashes ficam na auditoria"


def test_renumerar_para_numero_ocupado_e_recusado_na_tela(s):
    semear_volumes(s)
    mid = abrir_matricula(s, "2")
    html = postar(s, f"/registro-imoveis/{mid}/renumerar",
                  {"novo_numero": "4013", "motivo": "Tentativa indevida de renumerar"},
                  origem=f"/registro-imoveis/{mid}")
    assert "já é da matrícula" in html


# ------------------------------------------------------------------ partes


def test_corrigir_o_papel_faz_a_parte_virar_titular(s):
    mid = abrir_matricula(s, "2")
    lavrar(s, mid, "R", "R-01 TITULO",
           parte_nome="MARIA REGO SILVA PEREIRA",
           parte_documento="000.000.029-92", parte_papel="")
    con = banco(s)
    parte = con.execute("SELECT * FROM ri_partes WHERE matricula_id=?", (mid,)).fetchone()
    con.close()
    assert parte["proprietario_ativo"] == 0, "sem papel, ninguem e titular"

    html = postar(s, f"/registro-imoveis/partes/{parte['id']}/corrigir",
                  {"nome": parte["nome"], "documento": parte["documento_numero"],
                   "papel": "proprietário", "qualificacao": "", "titular": "papel",
                   "motivo": "Adquirente do título de domínio, titular atual"},
                  origem=f"/registro-imoveis/{mid}")
    assert "corrigido(s)" in html
    con = banco(s)
    depois = con.execute("SELECT * FROM ri_partes WHERE id=?", (parte["id"],)).fetchone()
    evento = con.execute("""SELECT details FROM audit_logs
                            WHERE action='RI_PARTE_CORRIGIDA'""").fetchone()
    con.close()
    assert depois["papel"] == "proprietário"
    assert depois["proprietario_ativo"] == 1
    assert '"papel"' in evento["details"], "o de-para do papel fica na auditoria"


def test_a_ficha_avisa_a_parte_sem_papel(s):
    mid = abrir_matricula(s, "2")
    lavrar(s, mid, "R", "R-01", parte_nome="ALGUEM", parte_papel="")
    assert "sem papel" in tela(s, f"/registro-imoveis/{mid}")


# ------------------------------------------------------------------ expurgo


def test_o_expurgo_exige_a_palavra_escrita(s):
    mid = abrir_matricula(s, "2")
    aid = lavrar(s, mid, "AV", "AV-01 ATO DE TESTE")
    html = postar(s, f"/registro-imoveis/atos/{aid}/expurgar",
                  {"motivo": "Ato lavrado em teste de implantação do sistema",
                   "confirmacao": "sim"},
                  origem=f"/registro-imoveis/atos/{aid}/expurgar")
    assert "escreva EXPURGAR" in html
    con = banco(s)
    assert con.execute("SELECT COUNT(*) c FROM ri_atos WHERE id=?",
                       (aid,)).fetchone()["c"] == 1, "nada pode ter saido"
    con.close()


def test_o_expurgo_remove_o_ato_e_lavra_a_ata(s):
    mid = abrir_matricula(s, "2")
    lavrar(s, mid, "R", "R-01 REGISTRO QUE FICA")
    aid = lavrar(s, mid, "AV", "AV-02 FLORESTA PUBLICA TIPO B",
                 selo_texto="AVESVD000000FGG3MHVL8PU1JW52",
                 emolumentos="Total R$ 134,43")
    html = postar(s, f"/registro-imoveis/atos/{aid}/expurgar",
                  {"motivo": "Ato lavrado em teste; selo cancelado no TJMA",
                   "selo_cancelado": "AVESVD000000FGG3MHVL8PU1JW52",
                   "confirmacao": "expurgar"},
                  origem=f"/registro-imoveis/atos/{aid}/expurgar")
    assert "expurgado" in html
    assert "ata de ocorrência" in html

    con = banco(s)
    assert con.execute("SELECT COUNT(*) c FROM ri_atos WHERE id=?",
                       (aid,)).fetchone()["c"] == 0
    assert con.execute("SELECT COUNT(*) c FROM ri_atos WHERE matricula_id=?",
                       (mid,)).fetchone()["c"] == 1, "o R-01 continua na ficha"
    ata = con.execute("SELECT * FROM ri_expurgos ORDER BY id DESC LIMIT 1").fetchone()
    evento = con.execute("""SELECT details FROM audit_logs
                            WHERE action='RI_ATO_EXPURGADO'""").fetchone()
    con.close()
    assert "FLORESTA PUBLICA TIPO B" in ata["ato_teor"]
    assert ata["selo_cancelado"] == "AVESVD000000FGG3MHVL8PU1JW52"
    assert "tabeliao" == ata["expurgado_por"], "a ata diz quem ordenou"
    assert "AVESVD000000FGG3MHVL8PU1JW52" in evento["details"]

    assert "AVESVD000000FGG3MHVL8PU1JW52" in tela(s, "/registro-imoveis/expurgos")
    r = s["c"].get(f"/registro-imoveis/expurgos/{ata['id']}/ata.odt")
    assert r.status_code == 200 and r.data[:2] == b"PK", "a ata baixa como .odt"


def test_ato_do_meio_nao_oferece_expurgo_na_ficha(s):
    mid = abrir_matricula(s, "2")
    primeiro = lavrar(s, mid, "R", "R-01")
    lavrar(s, mid, "AV", "AV-02")
    html = tela(s, f"/registro-imoveis/{mid}")
    assert f"/atos/{primeiro}/expurgar" not in html, \
        "so o ultimo ato pode ser expurgado, e a ficha nao deve oferecer o do meio"


def test_a_tela_de_expurgo_mostra_o_impedimento_e_esconde_o_botao(s):
    mid = abrir_matricula(s, "2")
    primeiro = lavrar(s, mid, "R", "R-01")
    lavrar(s, mid, "AV", "AV-02")
    html = tela(s, f"/registro-imoveis/atos/{primeiro}/expurgar")
    assert "Não é possível expurgar" in html
    assert "não é o último ato" in html
    assert "Escreva <strong>EXPURGAR</strong>" not in html


# ------------------------------------------- a certidao, o defeito de 18/08


def test_a_certidao_nao_leva_marcacao_de_odt_no_corpo(s):
    """O defeito real: `<text:p text:style-name="P-just">` no texto certificado."""
    mid = abrir_matricula(s, "2")
    lavrar(s, mid, "R", "R-01 TITULO DE DOMINIO SOB CONDICAO RESOLUTIVA",
           selo_texto="REGAVD000000OD1Q8BV5TOOZE492")
    postar(s, f"/registro-imoveis/{mid}/certidao",
           {"tipo": "INTEIRO_TEOR", "requerente": "MARIA REGO SILVA PEREIRA"},
           origem=f"/registro-imoveis/{mid}")
    con = banco(s)
    c = con.execute("SELECT * FROM ri_certidoes ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    corpo = c["corpo"]
    assert "text:p" not in corpo, "corpo de certidao nao pode ter marcacao de ODF"
    assert "text:style-name" not in corpo
    assert "draw:frame" not in corpo
    assert "@@ODF" not in corpo, "nem a marca do fragmento pode ser gravada"
    assert "TITULO DE DOMINIO SOB CONDICAO RESOLUTIVA" in corpo, "o teor tem de estar la"
    assert "<p>" in corpo, "o teor tem de sair em paragrafo HTML"
    # O selo do ATO nao entra no corpo da certidao: o modelo padrao transcreve
    # o teor, e o selo que a certidao carrega e o DELA, acrescentado na
    # impressao. No acervo do E-Oficio os selos aparecem porque estao escritos
    # dentro do proprio teor importado.
    assert "REGAVD000000OD1Q8BV5TOOZE492" not in corpo


def test_a_certidao_de_ficha_de_acervo_tambem_sai_limpa(s):
    mid = abrir_matricula(s, "2", teor="TEOR CORRIDO DO ACERVO\n\nSEGUNDA LINHA")
    con = banco(s)
    con.execute("UPDATE ri_matriculas SET tipo_ficha='ACERVO' WHERE id=?", (mid,))
    con.commit()
    con.close()
    postar(s, f"/registro-imoveis/{mid}/certidao",
           {"tipo": "INTEIRO_TEOR", "requerente": "ALGUEM"},
           origem=f"/registro-imoveis/{mid}")
    con = banco(s)
    corpo = con.execute("SELECT corpo FROM ri_certidoes ORDER BY id DESC LIMIT 1").fetchone()["corpo"]
    con.close()
    assert "text:p" not in corpo
    assert "TEOR CORRIDO DO ACERVO" in corpo


def test_a_ficha_em_odt_continua_saindo_com_odf(s):
    """A correcao da certidao nao pode ter estragado a ficha impressa.

    **O `.odt` PASSOU A PEDIR `?formato=odt`** — 01/09/2026, quando o botao
    passou a entregar PDF a pedido do oficial. O arquivo continua o mesmo zip
    `PK`; o que mudou foi qual formato o botao usa por padrao.
    """
    mid = abrir_matricula(s, "2")
    lavrar(s, mid, "R", "R-01 ATO DA FICHA")
    r = s["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    assert len(r.data) > 2000, "o .odt tem de ter conteudo"
