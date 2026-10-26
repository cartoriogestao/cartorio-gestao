"""
Testes das TELAS da certidao do Registro Civil.

POR QUE TELA, E NAO SO DOMINIO
    "Buraco de tela nao aparece em teste de dominio" e a licao que se repetiu
    quatro vezes nesta revisao: funcao pronta e testada que nenhuma tela
    chama. Estes testes abrem a ficha, emitem pelo POST e conferem o papel.

O QUE ELES CONFEREM
      - a ficha MOSTRA a filiacao e a avoenga, e o assento sem elas diz o que
        fazer em vez de so ficar vazio;
      - EMITIR sai da ficha, e a certidao aparece com a filiacao no teor;
      - o assento sem filiacao e RECUSADO pela rota, e a recusa volta como
        aviso vermelho — nao como HTTP 500;
      - o `.odt` sai, e traz o cabecalho da serventia e o corpo;
      - a BUSCA da tela acha por nome sem acento;
      - CANCELAR também pode ser feito pelo escrevente, exige a declaração do
        selo no TJMA e mantém o teor na tela;
      - ABRIR A FICHA NAO GRAVA NADA: tela de leitura que escreve fica presa
        no `busy_timeout` enquanto outro balcao lavra;
      - OS PAIS ENTRAM NA CONFERENCIA DE FRAUDE. Registro de nascimento falso
        se faz com a filiacao de outra pessoa, e ate 26/08/2026 so o nome do
        registrado era conferido.
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
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _avisos(html: str) -> list[str]:
    """Mensagens de regra, para a falha dizer o motivo em vez de despejar HTML."""
    return [re.sub(r"<[^>]+>", "", aviso).strip() for aviso in re.findall(
        r'<div class="flash[^\"]*">(.*?)</div>', html, flags=re.DOTALL)]


def _resumo_da_pagina(html: str) -> dict[str, list[str]]:
    def textos(tag: str) -> list[str]:
        return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip()
                for x in re.findall(fr"<{tag}[^>]*>(.*?)</{tag}>", html,
                                    flags=re.DOTALL | re.IGNORECASE)]
    return {"title": textos("title"), "h1": textos("h1"),
            "h2": textos("h2"), "avisos": _avisos(html)}


def _diagnostico_emissao(s, resposta) -> dict:
    con = _con(s)
    quantidade = con.execute("SELECT COUNT(*) FROM rc_certidoes").fetchone()[0]
    ultima = con.execute(
        "SELECT selo, cancelada_em, cancelada_motivo FROM rc_certidoes "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    con.close()
    return {
        "pagina": _resumo_da_pagina(resposta.get_data(as_text=True)),
        "status": resposta.status_code,
        "redirecionamentos": [r.headers.get("Location") for r in resposta.history],
        "certidoes_gravadas": quantidade,
        "ultima_certidao": dict(ultima) if ultima else None,
    }


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, papel)
    # A `_sessao` NAO MEXE NA TRAVA DO SELO PAGO (revisao de seguranca de
    # 26/10/2026, achado MEDIO do PR #24). Ela e importada por outros arquivos
    # — `test_certidao_eletronica_crc_selo` e, com o PR #16,
    # `test_rc_materializacao_selo` — que medem justamente a trava com o
    # aparelho «sem protocolo pago»; desligada aqui, aqueles testes deixavam de
    # guardar a trava sem ninguem ver. Quem desliga e o fixture `s` deste
    # arquivo, a vista, por `_sem_a_trava`.
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


def _sem_a_trava(cg_casa) -> None:
    """A TRAVA DO SELO PAGO (3.7.0) desliga aqui, a vista: os testes DESTE
    arquivo medem a certidao e o selo digitado no razao, e nao a trava, que tem
    teste proprio (`test_selo_e_caixa`). So para quem chama — nunca dentro da
    `_sessao`, que outros arquivos importam."""
    cg_casa['db'].set_settings({"selo_trava_caixa": "DESLIGADA"})


@pytest.fixture()
def s(cg_casa):
    _sem_a_trava(cg_casa)
    return _sessao(cg_casa)


@pytest.fixture(autouse=True)
def _o_selador_desta_bancada(cg_casa):
    """Certidao so existe se o selo sair; a bancada fornece o aparelho real TLS."""
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(cg_casa) as aparelho:
        yield aparelho


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _semear(s, com_filiacao: bool = True, nome: str = "JOÃO DA SILVA") -> int:
    """Um assento de nascimento, com ou sem os pais."""
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, matricula, nome,
                   data_ato, data_fato, dados_json, situacao, origem,
                   criado_em)
               VALUES ('RC_A','NASCIMENTO',19552,
                       '000000015519971000111270010385 01',?,
                       '2020-01-20','2020-01-15','{"strSexo": "Masculino"}',
                       'ATIVO','EOFICIO','2026-08-26T09:00:00')""", (nome,))
        assento_id = con.execute(
            "SELECT id FROM rc_assentos").fetchone()["id"]
        con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem,
                   rotulo, data_ato, origem, criado_em)
               VALUES (?,'REGISTRO',127,19552,'127','2020-01-20','EOFICIO',
                       '2026-08-26T09:00:00')""", (assento_id,))
        if com_filiacao:
            for papel, quem, ordem in (
                    ("PAI", "JOSÉ DA SILVA", 1),
                    ("MAE", "MARIA DAS GRAÇAS SILVA", 2),
                    ("AVO_PATERNO", "ANTÔNIO DA SILVA", 3),
                    ("AVO_MATERNA", "RITA GOMES", 6)):
                con.execute(
                    """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem,
                           origem, criado_em)
                       VALUES (?,?,?,?,'EOFICIO','2026-08-26T09:00:00')""",
                    (assento_id, papel, quem, ordem))
    con.close()
    return assento_id


def _semear_folha(s) -> str:
    """Uma folha EM BRANCO no estoque.

    **A GUARDA DE PRODUÇÃO DE 09/09/2026 (`FOLHA_SEGURANCA_OBRIGATORIA_CERT`)
    ALCANÇA TODO ASSENTO QUE `_semear` CRIA.** Ela recusa emitir certidão de
    2ª via sem folha escolhida, porque sem folha o ato ficava gravado SEM SELO
    (incidente Marcos Dione / cert. 16), e a régua dela é: assento IMPORTADO
    (`origem='EOFICIO'`) cujo ato de REGISTRO não tem selo **não é primeira
    via** — presume-se segunda, decisão do oficial no mesmo dia.

    `_semear` cria exatamente isso: `origem='EOFICIO'` e um ato de REGISTRO
    sem selo. Logo **toda emissão destes testes cai na guarda**, e sem a folha
    eles ficavam vermelhos por um motivo que não é o que cada um mede —
    treze de uma vez. O conserto é o **ensaio**, e não a guarda: ela protege
    o balcão de gravar ato sem selo.

    O mesmo ajudante existe em `test_rc_certidao_impressao.py`, que passou
    por isto em 09/09.
    """
    con = _con(s)
    codigo = "9999999"
    with con:
        ja = con.execute("SELECT 1 FROM pp_folhas WHERE codigo=?",
                         (codigo,)).fetchone()
        if not ja:
            con.execute(
                """INSERT INTO pp_remessas(fornecedor, codigo_de, codigo_ate,
                       quantas, recebida_em)
                   VALUES ('TESTE', ?, ?, 1, '2026-09-09T00:00:00')""",
                (codigo, codigo))
            rid = con.execute(
                "SELECT id FROM pp_remessas ORDER BY id DESC LIMIT 1"
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO pp_folhas(codigo, remessa_id, situacao, criada_em)"
                " VALUES (?,?,'EM BRANCO','2026-09-09T00:00:00')",
                (codigo, rid))
    con.close()
    return codigo


def _emitir(s, assento_id: int, **campos):
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    campos.setdefault("folha_seguranca", _semear_folha(s))
    return s["c"].post(f"/rcpn/{assento_id}/certidao",
                       data={"csrf_token": _token(html), **campos},
                       follow_redirects=True)


# ------------------------------------------------------------- a ficha


def test_a_ficha_mostra_a_filiacao_e_a_avoenga(s):
    assento_id = _semear(s)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert "Filiação e avoenga" in html
    assert "JOSÉ DA SILVA" in html
    assert "MARIA DAS GRAÇAS SILVA" in html


def test_assento_sem_filiacao_diz_o_que_fazer(s):
    """Bloco vazio faz o escrevente achar que a tela quebrou."""
    assento_id = _semear(s, com_filiacao=False)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert "está sem filiação" in html
    # O caminho da carga do E-Ofício saiu em 17/10/2026; fica o de lançar à mão.
    assert "lançar os nomes" in html
    assert 'href="/atribuicoes/importar"' not in html


def test_a_ficha_oferece_emitir_certidao(s):
    assento_id = _semear(s)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert "Emitir certidão" in html


def test_a_ficha_avisa_que_nao_ha_receita_medida_do_civil(s):
    """Sugerir item de custa inventado seria pior que nao sugerir nenhum.

    O E-Oficio selou 1.238 atos do civil e mandou o `codigoAto` VAZIO em
    todos: nao ha o que medir, e a tela diz isso em vez de mostrar um quadro
    de cobranca vazio.
    """
    assento_id = _semear(s)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert "cobrança do civil se lança pelo caixa" in html


def test_abrir_a_ficha_nao_grava_nada(s):
    """GET nao abre transacao de escrita."""
    assento_id = _semear(s)
    s["c"].get(f"/rcpn/{assento_id}")
    s["c"].get(f"/rcpn/{assento_id}")
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) c FROM rc_certidoes").fetchone()["c"] == 0
    con.close()


# ------------------------------------------------------------ emitir


def test_emitir_pela_ficha_produz_a_certidao(s):
    assento_id = _semear(s)
    resposta = _emitir(s, assento_id, requerente="A MÃE", finalidade="INSS")
    html = resposta.get_data(as_text=True)
    assert "emitida" in html
    diagnostico = _diagnostico_emissao(s, resposta)
    assert "JOSÉ DA SILVA e MARIA DAS GRAÇAS SILVA" in html, diagnostico["ultima_certidao"]


def test_a_certidao_traz_o_livro_e_a_folha_do_ATO(s):
    """O lugar mora no ato de REGISTRO, e nao no assento — e errar isso e
    calado: sairia `ND` no lugar do livro, sem erro nenhum."""
    assento_id = _semear(s)
    resposta = _emitir(s, assento_id)
    html = resposta.get_data(as_text=True)
    assert "TERMO" in html, _diagnostico_emissao(s, resposta)
    assert "19552" in html


def test_emitir_sem_filiacao_volta_como_aviso_e_nao_como_500(s):
    """Erro de regra nao e HTTP 500."""
    assento_id = _semear(s, com_filiacao=False)
    resposta = _emitir(s, assento_id)
    assert resposta.status_code == 200
    assert "sem filiação" in resposta.get_data(as_text=True)


def test_a_tela_da_certidao_mostra_quantos_atos_o_assento_tinha(s):
    assento_id = _semear(s)
    _emitir(s, assento_id)
    con = _con(s)
    cid = con.execute("SELECT id FROM rc_certidoes").fetchone()["id"]
    con.close()
    html = s["c"].get(f"/rcpn/certidoes/{cid}").get_data(as_text=True)
    assert "Atos no assento" in html
    assert "congelado" in html


def test_a_certidao_sai_em_odt(s):
    """**O `.odt` PASSOU A PEDIR `?formato=odt`** — 01/09/2026, quando o
    oficial mandou o botao entregar PDF. O caminho continua o mesmo; o que
    mudou foi o padrao, e o editavel esta a um parametro.

    Este teste ficou vermelho na hora certa: ele guardava a resposta antiga,
    e e assim que se descobre que o contrato de uma rota mudou.
    """
    assento_id = _semear(s)
    _emitir(s, assento_id)
    con = _con(s)
    cid = con.execute("SELECT id FROM rc_certidoes").fetchone()["id"]
    con.close()
    resposta = s["c"].get(f"/rcpn/certidoes/{cid}/odt?formato=odt")
    assert resposta.status_code == 200
    assert "opendocument" in resposta.headers["Content-Type"]
    assert len(resposta.get_data()) > 1000
    assert "attachment" in resposta.headers["Content-Disposition"]


def test_o_botao_de_imprimir_nao_entrega_odt(s):
    """O pedido do oficial, do lado de quem clica: *«a ferramenta de impressão
    está baixando um arquivo, preciso que gere o pdf»*.

    **Sem LibreOffice na maquina a rota volta para a ficha com a frase** — e
    isso tambem e o certo: nunca entregar calado um formato diferente do que
    se pediu. Os dois desfechos passam por aqui; o que nao pode e sair `.odt`
    com cara de impressao.
    """
    assento_id = _semear(s)
    _emitir(s, assento_id)
    con = _con(s)
    cid = con.execute("SELECT id FROM rc_certidoes").fetchone()["id"]
    con.close()
    r = s["c"].get(f"/rcpn/certidoes/{cid}/imprimir")
    if r.status_code == 302:            # sem conversor: volta e avisa
        assert "/rcpn/certidoes" in r.headers["Location"]
        return
    assert r.status_code == 200
    assert "opendocument" not in r.headers["Content-Type"]
    assert r.headers["Content-Type"].startswith("application/pdf")
    assert "inline" in r.headers["Content-Disposition"]
    assert r.get_data()[:5] == b"%PDF-"


def test_a_ficha_lista_a_certidao_emitida(s):
    assento_id = _semear(s)
    _emitir(s, assento_id, requerente="A MÃE")
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert "A MÃE" in html
    assert "1/" in html


# --------------------------------------------------------------- o selo


# OS SELOS SAO OS DA CASA, com o CNS 000000 — a conferencia recusa selo de
# outra serventia, e recusa o mesmo selo duas vezes. Sao dois porque um ato so
# nao mostra duas grafias no razao.
SELO_DA_CERTIDAO = "AVESVD000000NARRKWVNJCRSVO21"
SELO_DA_AVERBACAO = "AVESVD000000NARRKWVNJCRSVO22"


def _selo_da_casa() -> str:
    return SELO_DA_CERTIDAO


def test_a_certidao_sela_pela_ficha(s):
    """O SELO E OPCIONAL, mas quando vem tem de entrar no razao — e com a
    atribuicao escrita como o resto da casa a escreve.

    Eu havia passado `"rcpn"` minusculo onde as outras nove chamadas passam
    `"RCPN"`. O razao `sd_selos` ficaria com duas grafias da mesma atribuicao,
    e quem filtrasse por ela veria metade dos selos. Nenhum dos outros testes
    de tela via, porque todos emitiam sem selo.
    """
    assento_id = _semear(s)
    _emitir(s, assento_id, selo=_selo_da_casa())
    con = _con(s)
    linha = con.execute(
        "SELECT atribuicao, tabela FROM sd_selos ORDER BY id DESC LIMIT 1"
    ).fetchone()
    con.close()
    assert linha is not None, "o selo digitado nao entrou no razao"
    assert linha["tabela"] == "rc_certidoes"
    assert linha["atribuicao"] == "RCPN"


def test_a_atribuicao_do_selo_e_a_mesma_do_ato_do_assento(s):
    """A certidao e o ato do assento tem de gravar a MESMA palavra.

    Aqui a igualdade se CONSTROI, e nao se supoe: o teste compara as duas
    grafias que o banco recebeu, em vez de conferir cada uma contra uma
    constante escrita no proprio teste.
    """
    assento_id = _semear(s)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    s["c"].post(f"/rcpn/{assento_id}/lancar",
                data={"csrf_token": _token(html), "tipo": "AVERBACAO",
                      "teor": "Averbado o casamento, conforme o Livro B.",
                      "selo": SELO_DA_AVERBACAO},
                follow_redirects=True)
    _emitir(s, assento_id, selo=_selo_da_casa())
    con = _con(s)
    grafias = {r["atribuicao"] for r in con.execute(
        "SELECT atribuicao FROM sd_selos WHERE atribuicao IS NOT NULL")}
    con.close()
    assert len(grafias) == 1, f"o razao ficou com duas grafias: {grafias}"


# ------------------------------------------------------------- a busca


def test_a_busca_da_tela_acha_sem_acento(s):
    """`UPPER()` do SQLite e ASCII, e no civil quase todo nome tem acento."""
    _semear(s, nome="JOÃO ANTÔNIO DA CONCEIÇÃO")
    html = s["c"].get("/rcpn/certidoes?q=joao+antonio+da+conceicao"
                      ).get_data(as_text=True)
    assert "JOÃO ANTÔNIO DA CONCEIÇÃO" in html


def test_a_busca_sem_achado_diz_onde_pode_estar(s):
    """Lista vazia que so mostra nada faz o operador achar que quebrou."""
    _semear(s)
    html = s["c"].get("/rcpn/certidoes?q=ninguem").get_data(as_text=True)
    assert "Nenhum assento" in html
    assert "acervo" in html


def test_a_tela_de_certidoes_abre_vazia(s):
    html = s["c"].get("/rcpn/certidoes").get_data(as_text=True)
    assert "Nenhuma certidão emitida ainda" in html


# --------------------------------------------------------- o cancelamento


def test_cancelar_pede_motivo_e_o_teor_fica(s):
    assento_id = _semear(s)
    _emitir(s, assento_id)
    con = _con(s)
    cid = con.execute("SELECT id FROM rc_certidoes").fetchone()["id"]
    con.close()
    html = s["c"].get(f"/rcpn/certidoes/{cid}").get_data(as_text=True)
    resposta = s["c"].post(
        f"/rcpn/certidoes/{cid}/cancelar",
        data={"csrf_token": _token(html),
              "motivo": "Erro no nome da mãe, conferido no livro.",
              "selo_cancelado_tjma": "1"},
        follow_redirects=True)
    texto = resposta.get_data(as_text=True)
    assert "Certidão cancelada" in texto
    assert "JOSÉ DA SILVA e MARIA DAS GRAÇAS SILVA" in texto


def test_cancelar_recupera_a_folha_de_seguranca_sem_escolha_manual(s):
    import papel_seguranca as PP

    assento_id = _semear(s)
    _emitir(s, assento_id)
    con = _con(s)
    cid = con.execute("SELECT id FROM rc_certidoes").fetchone()["id"]
    with con:
        PP.receber_remessa(
            con, fornecedor="ARPENBRASIL", codigo_de="900001",
            codigo_ate="900002", agora="2026-09-10T08:00:00")
        PP.usar(con, "900001", tabela="rc_certidoes", ato_id=cid,
                agora="2026-09-10T08:05:00", usuario="MARIO")
    con.close()

    html = s["c"].get(f"/rcpn/certidoes/{cid}").get_data(as_text=True)
    resposta = s["c"].post(
        f"/rcpn/certidoes/{cid}/cancelar",
        data={"csrf_token": _token(html),
              "motivo": "Certidão impressa com dado incorreto.",
              "selo_cancelado_tjma": "1"},
        follow_redirects=True)

    texto = resposta.get_data(as_text=True)
    assert "900001" in texto and "devolvida" in texto
    con = _con(s)
    assert PP.ler(con, "900001")["situacao"] == "EM BRANCO"
    assert PP.proxima_folha(con)["codigo"] == "900001"
    assert PP.movimentos_da_folha(con, "900001")[-1]["ato_id"] == cid
    con.close()


def test_cancelar_com_motivo_curto_e_recusado(s):
    assento_id = _semear(s)
    _emitir(s, assento_id)
    con = _con(s)
    cid = con.execute("SELECT id FROM rc_certidoes").fetchone()["id"]
    html = s["c"].get(f"/rcpn/certidoes/{cid}").get_data(as_text=True)
    s["c"].post(f"/rcpn/certidoes/{cid}/cancelar",
                data={"csrf_token": _token(html), "motivo": "erro",
                      "selo_cancelado_tjma": "1"},
                follow_redirects=True)
    assert con.execute(
        "SELECT cancelada_em FROM rc_certidoes").fetchone()[0] is None
    con.close()


def test_escrevente_pode_cancelar_certidao_com_declaracao(cg_casa):
    """Quem emitiu no balcão consegue corrigir o erro sem chamar o admin."""
    _sem_a_trava(cg_casa)
    s = _sessao(cg_casa, papel="USER")
    assento_id = _semear(s)
    _emitir(s, assento_id)
    con = _con(s)
    cid = con.execute("SELECT id FROM rc_certidoes").fetchone()["id"]
    con.close()
    html = s["c"].get(f"/rcpn/certidoes/{cid}").get_data(as_text=True)
    assert "Cancelar esta certidão" in html
    assert "portal do Selo Eletrônico do TJMA" in html
    resposta = s["c"].post(f"/rcpn/certidoes/{cid}/cancelar",
                           data={"csrf_token": _token(html),
                                 "motivo": "Motivo qualquer, bem escrito.",
                                 "selo_cancelado_tjma": "1"},
                           follow_redirects=True)
    assert "Certidão cancelada" in resposta.get_data(as_text=True)
    con = _con(s)
    linha = con.execute("SELECT * FROM rc_certidoes WHERE id=?", (cid,)).fetchone()
    assert linha["cancelada_em"]
    assert linha["declaracao_selo_tjma_por"] == "MARIO EXEMPLO DOS SANTOS"
    con.close()


def test_cancelar_sem_declaracao_do_selo_e_recusado(s):
    assento_id = _semear(s)
    _emitir(s, assento_id)
    con = _con(s)
    cid = con.execute("SELECT id FROM rc_certidoes").fetchone()["id"]
    html = s["c"].get(f"/rcpn/certidoes/{cid}").get_data(as_text=True)
    resposta = s["c"].post(
        f"/rcpn/certidoes/{cid}/cancelar",
        data={"csrf_token": _token(html),
              "motivo": "Motivo suficiente para cancelar."},
        follow_redirects=True)
    assert "Confirme a declaração" in resposta.get_data(as_text=True)
    assert con.execute(
        "SELECT cancelada_em FROM rc_certidoes WHERE id=?", (cid,)
    ).fetchone()[0] is None
    con.close()


# --------------------------------------------------- a fraude e a filiacao


def test_o_nome_da_MAE_dispara_o_alerta_de_fraude(s):
    """REGISTRO DE NASCIMENTO FALSO SE FAZ COM A FILIACAO DE OUTRA PESSOA.

    Ate 26/08/2026 a ficha do assento so conferia o nome do REGISTRADO — e o
    comentario dizia que os demais nomes moravam em `dados_json` e entrariam
    "quando a tela pedisse". Eles nunca estiveram la: estavam no acervo, em
    `tbFiliacao`, e a carga nao a abria.
    """
    assento_id = _semear(s)
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO fr_alertas(papel, nome, nome_norm, origem,
                   situacao, criado_em)
               VALUES ('ENVOLVIDO','MARIA DAS GRAÇAS SILVA',
                       'maria das gracas silva',
                       'Comunicação CGJ 44/2026, de 10/08/2026','ATIVO',
                       '2026-08-26T09:00:00')""")
    con.close()
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert "MARIA DAS GRAÇAS SILVA" in html
    assert "fraude" in html.lower()


# ----------------------------------------- o livro por confirmar, na ficha


MARCA = ("O E-Ofício guardou este casamento num grupo separado, com "
         "numeração própria. Antes de emitir certidão deste assento, confira "
         "na folha do livro de papel se o livro é o B ou o B-Auxiliar.")


def _marcar_livro(s, assento_id: int) -> None:
    """Poe a marca do livro por confirmar, como a carga a poe.

    O TEXTO VAI EM `?`. Eu o havia escrito em dois pedacos colados dentro da
    string SQL, contando com a juncao do Python — mas quem le aquilo e o
    SQLite, que ve dois literais lado a lado e recusa.
    """
    con = _con(s)
    with con:
        con.execute(
            """UPDATE rc_assentos SET livro_volume='1', livro_a_confirmar=?
                WHERE id=?""", (MARCA, assento_id))
    con.close()


def test_a_ficha_avisa_que_o_livro_esta_por_confirmar(s):
    """O AVISO MORA ONDE A CONSULTA ACONTECE, e nao numa aba.

    Foi o que o oficial pediu em 26/08/2026: pendente de confirmacao QUANDO
    FOREM CONSULTADOS EFETIVAMENTE.
    """
    assento_id = _semear(s)
    _marcar_livro(s, assento_id)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert "por confirmar" in html
    assert "livro de papel" in html


def test_a_ficha_avisa_ANTES_de_emitir_a_certidao(s):
    """Errar o livro so sai caro quando vira papel assinado."""
    assento_id = _semear(s)
    _marcar_livro(s, assento_id)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert "Confira o livro antes de assinar" in html


def test_assento_sem_duvida_nao_mostra_o_aviso(s):
    """O par do teste de cima: o aviso so aparece quando ha duvida."""
    assento_id = _semear(s)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert "por confirmar" not in html


def test_quem_conferiu_na_estante_tem_onde_dizer(s):
    """AVISO SEM SAIDA E AVISO QUE FICA PARA SEMPRE.

    Se quem foi ate a estante nao tem onde registrar o que viu, o proximo abre
    a ficha e ve o mesmo aviso — e na terceira vez ninguem le mais.
    """
    assento_id = _semear(s)
    _marcar_livro(s, assento_id)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    resposta = s["c"].post(
        f"/rcpn/{assento_id}/confirmar-livro",
        data={"csrf_token": _token(html), "livro_volume": "B-Auxiliar 1"},
        follow_redirects=True)
    texto = resposta.get_data(as_text=True)
    assert "Livro confirmado como B-Auxiliar 1" in texto
    assert "por confirmar" not in texto


def test_o_livro_confirmado_sai_na_certidao(s):
    """Confirmar sem que a certidao mude seria confirmar para nada."""
    assento_id = _semear(s)
    _marcar_livro(s, assento_id)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    s["c"].post(f"/rcpn/{assento_id}/confirmar-livro",
                data={"csrf_token": _token(html),
                      "livro_volume": "B-Auxiliar 1"},
                follow_redirects=True)
    teor = _emitir(s, assento_id).get_data(as_text=True)
    assert "B-Auxiliar 1" in teor


def test_confirmar_sem_dizer_o_livro_e_recusado(s):
    """Campo vazio apagaria o volume e deixaria a certidao sem livro."""
    assento_id = _semear(s)
    _marcar_livro(s, assento_id)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    s["c"].post(f"/rcpn/{assento_id}/confirmar-livro",
                data={"csrf_token": _token(html), "livro_volume": "   "},
                follow_redirects=True)
    con = _con(s)
    linha = con.execute(
        "SELECT livro_volume, livro_a_confirmar FROM rc_assentos WHERE id=?",
        (assento_id,)).fetchone()
    con.close()
    assert linha["livro_volume"] == "1"
    assert linha["livro_a_confirmar"] is not None


def test_a_confirmacao_fica_na_auditoria(s):
    """E correcao de dado de livro: quem conferiu e o que mudou ficam."""
    assento_id = _semear(s)
    _marcar_livro(s, assento_id)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    s["c"].post(f"/rcpn/{assento_id}/confirmar-livro",
                data={"csrf_token": _token(html), "livro_volume": "B-1"},
                follow_redirects=True)
    con = _con(s)
    linha = con.execute(
        "SELECT * FROM audit_logs WHERE action='RCPN_LIVRO_CONFERIDO'"
    ).fetchone()
    con.close()
    assert linha is not None


def test_a_sessao_compartilhada_nao_desliga_a_trava_do_selo(cg_casa):
    """Revisao de seguranca de 26/10/2026, achado MEDIO do PR #24: a `_sessao`
    deste arquivo e importada por testes que MEDEM a trava do selo pago
    (`test_certidao_eletronica_crc_selo` e, com o PR #16, o do 14.5.1). Se ela
    voltar a desligar a trava, esses testes passam sem guardar nada — e e
    este que fica vermelho."""
    import ato_selado as AS
    _sessao(cg_casa)
    valor = cg_casa["db"].get_setting(AS.CHAVE_DA_TRAVA, "")
    assert str(valor or "").strip().upper() != AS.TRAVA_DESLIGADA
