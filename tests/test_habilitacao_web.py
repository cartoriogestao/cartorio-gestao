"""A habilitação de casamento, pelas telas.

POR QUE TESTE DE ROTA, E NÃO SÓ DE MÓDULO
    As regras estão em `habilitacao.py` e têm teste próprio. O que ESTES
    protegem é o caminho que o escrevente percorre: abrir, receber documento,
    publicar, esperar, habilitar, celebrar — e o que a tela mostra em cada
    ponto.

    E protegem uma coisa a mais: que a tela **não deixe** fazer fora de ordem.
    O domínio recusa por dever; a tela desabilita por educação. As duas coisas
    se conferem aqui.
"""
from __future__ import annotations

import glob
import io
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
TEOR = ("Faço saber que pretendem casar-se FULANO DE TAL e BELTRANA DE TAL, e "
        "que apresentaram os documentos exigidos por lei. Quem souber de "
        "impedimento, oponha-o.")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    c = cg_casa["cliente"]
    cg_casa["db"].create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(cg_casa) as aparelho:
        cg_casa["selador"] = aparelho
        yield cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _abrir(casa, **extra) -> int:
    html = casa["cliente"].get(
        "/rcpn/habilitacoes/nova").get_data(as_text=True)
    dados = {"csrf_token": _token(html),
             "nubente1_nome": "FULANO DE TAL",
             "nubente1_estado_civil": "SOLTEIRO",
             "nubente2_nome": "BELTRANA DE TAL",
             "nubente2_estado_civil": "SOLTEIRA",
             "tipo": "CIVIL", "regime": "COMUNHAO_PARCIAL"}
    dados.update(extra)
    casa["cliente"].post("/rcpn/habilitacoes/nova", data=dados,
                         follow_redirects=True)
    return int(_con(casa).execute(
        "SELECT MAX(id) FROM hc_habilitacoes").fetchone()[0])


def _ficha(casa, hid: int) -> str:
    return casa["cliente"].get(
        f"/rcpn/habilitacoes/{hid}").get_data(as_text=True)


def _post(casa, hid: int, **dados):
    html = _ficha(casa, hid)
    dados["csrf_token"] = _token(html)
    return casa["cliente"].post(f"/rcpn/habilitacoes/{hid}", data=dados,
                                follow_redirects=True)


def _entregar_tudo(casa, hid: int) -> None:
    con = _con(casa)
    for d in con.execute(
            "SELECT id FROM hc_documentos WHERE habilitacao_id=?",
            (hid,)).fetchall():
        _post(casa, hid, acao="documento", documento_id=d["id"], apresentado=1)


def _mandar_prazo_para_tras(casa, hid: int) -> None:
    """Faz o prazo do edital já ter vencido, sem esperar o prazo legal inteiro.

    Mexer na data GRAVADA é honesto aqui: o que se testa é o comportamento
    depois do prazo, e não o relógio.
    """
    con = _con(casa)
    with con:
        con.execute("""UPDATE hc_habilitacoes
                       SET edital_em='2020-01-01', edital_prazo_ate='2020-01-05'
                       WHERE id=?""", (hid,))
    _ligar_o_proclamas(casa, hid)


def _ligar_o_proclamas(casa, hid: int) -> None:
    """O registro no Livro D, com livro/folha/termo, amarrado à habilitação.

    HOTFIX-2026-10-07-05: o Tribunal recusa o selo da habilitação sem
    `dadosSelo.livro/folha/termo`, e eles saem do assento de proclamas. Sem
    ele a casa nem pede o selo — e a habilitação, por ordem de 16/09, não sai.
    """
    con = _con(casa)
    with con:
        aid = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   situacao, origem, criado_em, livro_volume, dados_json)
               VALUES ('RC_D','PROCLAMAS',?,'FULANO E BELTRANA','2020-01-01',
                       'ATIVO','MANUAL','2020-01-01T10:00:00','D-1',
                       '{"folha": "12"}')""", (1000 + hid,)).lastrowid
        con.execute("UPDATE hc_habilitacoes SET proclamas_assento_id=? "
                    "WHERE id=?", (aid, hid))


# ------------------------------------------------------------- abrir


def test_abrir_monta_o_checklist_e_leva_para_a_ficha(casa):
    hid = _abrir(casa)
    html = _ficha(casa, hid)
    assert "art. 1.525" in html
    assert "FULANO DE TAL" in html and "BELTRANA DE TAL" in html
    # Oito itens: quatro incisos × dois nubentes (solteiros não têm o V).
    assert _con(casa).execute(
        "SELECT COUNT(*) n FROM hc_documentos WHERE habilitacao_id=?",
        (hid,)).fetchone()["n"] == 8


def test_a_ficha_diz_o_que_fazer_agora(casa):
    """Num rito de semanas, «e agora?» é a pergunta que mais se repete."""
    hid = _abrir(casa)
    assert "Receber" in _ficha(casa, hid)


def test_a_lista_traz_os_proximos_passos_de_cada_uma(casa):
    _abrir(casa)
    html = casa["cliente"].get("/rcpn/habilitacoes").get_data(as_text=True)
    assert "Receber" in html


# ----------------------------------------------------------- o edital


def test_o_botao_de_publicar_vem_desabilitado_com_documento_faltando(casa):
    """A tela desabilita por educação; o domínio recusa por dever."""
    hid = _abrir(casa)
    html = _ficha(casa, hid)
    assert re.search(r"<button[^>]*disabled[^>]*>Publicar edital", html)


def test_e_o_dominio_recusa_mesmo_se_alguem_forcar_o_post(casa):
    """Botão desabilitado não impede POST forjado — quem recusa é a regra."""
    hid = _abrir(casa)
    html = _post(casa, hid, acao="edital", teor=TEOR).get_data(as_text=True)
    assert "Faltam" in html
    assert _con(casa).execute(
        "SELECT situacao FROM hc_habilitacoes WHERE id=?",
        (hid,)).fetchone()["situacao"] == "EM_ANALISE"


def test_com_tudo_entregue_o_edital_publica_e_abre_o_prazo(casa):
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    html = _post(casa, hid, acao="edital", teor=TEOR).get_data(as_text=True)
    assert "Edital publicado" in html
    linha = _con(casa).execute(
        "SELECT * FROM hc_habilitacoes WHERE id=?", (hid,)).fetchone()
    assert linha["situacao"] == "EDITAL_PUBLICADO"
    assert linha["edital_hash"]


def test_o_modelo_do_edital_ja_vem_preenchido_com_os_nomes(casa):
    """Campo em branco num edital é o que produz edital genérico."""
    hid = _abrir(casa)
    html = _ficha(casa, hid)
    assert "pretendem casar-se FULANO DE TAL e BELTRANA DE TAL" in html


def test_o_edital_sai_em_odt_com_o_teor_QUE_FOI_PUBLICADO(casa):
    """Remontar faria o papel afixado e o reimpresso divergirem."""
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor="TEOR ESPECIAL QUE O ESCREVENTE "
                                         "ESCREVEU À MÃO NAQUELE DIA")
    r = casa["cliente"].get(f"/rcpn/habilitacoes/{hid}/edital")
    assert r.mimetype == "application/vnd.oasis.opendocument.text"
    with zipfile.ZipFile(io.BytesIO(r.get_data())) as z:
        texto = re.sub(r"<[^>]+>", " ", z.read("content.xml").decode("utf-8"))
    assert "TEOR ESPECIAL QUE O ESCREVENTE" in texto
    assert "EDITAL DE PROCLAMAS" in texto


def test_sem_edital_publicado_nao_ha_o_que_imprimir(casa):
    hid = _abrir(casa)
    html = casa["cliente"].get(f"/rcpn/habilitacoes/{hid}/edital",
                               follow_redirects=True).get_data(as_text=True)
    assert "ainda não foi publicado" in html


# --------------------------------------------------------- habilitar


def test_o_botao_de_habilitar_vem_ativo_dentro_do_prazo(casa):
    """HOTFIX-2026-10-07-04: a casa expede assim que o edital está publicado;
    o prazo de oposição fica na tela como informação, e não tranca o botão."""
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor=TEOR)
    html = _ficha(casa, hid)
    assert re.search(r"<button[^>]*>Habilitar", html)
    assert not re.search(r"<button[^>]*disabled[^>]*>Habilitar", html)


def test_vencido_o_prazo_a_habilitacao_sai(casa):
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor=TEOR)
    _mandar_prazo_para_tras(casa, hid)
    html = _post(casa, hid, acao="habilitar").get_data(as_text=True)
    assert "expedida" in html
    linha = _con(casa).execute(
        "SELECT * FROM hc_habilitacoes WHERE id=?", (hid,)).fetchone()
    assert linha["situacao"] == "HABILITADO"
    assert linha["certidao_numero"] == 1


def test_a_certidao_diz_ate_quando_vale(casa):
    """Sem a data-limite impressa, quem celebra não sabe se ainda pode."""
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor=TEOR)
    _mandar_prazo_para_tras(casa, hid)
    _post(casa, hid, acao="habilitar")
    r = casa["cliente"].get(f"/rcpn/habilitacoes/{hid}/certidao")
    with zipfile.ZipFile(io.BytesIO(r.get_data())) as z:
        texto = re.sub(r"<[^>]+>", " ", z.read("content.xml").decode("utf-8"))
    assert "CERTIDÃO DE HABILITAÇÃO PARA CASAMENTO" in texto
    assert "válida até" in texto
    assert "artigo 1.532" in texto


def test_sem_habilitacao_expedida_nao_ha_certidao(casa):
    hid = _abrir(casa)
    html = casa["cliente"].get(f"/rcpn/habilitacoes/{hid}/certidao",
                               follow_redirects=True).get_data(as_text=True)
    assert "ainda não foi expedida" in html


# ---------------------------------------------------------- oposição


def test_a_oposicao_para_o_processo_e_a_tela_pede_decisao(casa):
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor=TEOR)
    _post(casa, hid, acao="oposicao", quem="MARIA VIZINHA",
          teor="ele já é casado em outra comarca")
    html = _ficha(casa, hid)
    assert "Impedimento oposto" in html
    assert "MARIA VIZINHA" in html
    assert "Decidir" in html
    # E o botão de habilitar sumiu.
    assert ">Habilitar<" not in html


def test_a_decisao_exige_fundamento_e_a_tela_mostra_o_erro(casa):
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor=TEOR)
    _post(casa, hid, acao="oposicao", quem="MARIA", teor="ele já é casado")
    html = _post(casa, hid, acao="decidir", decisao="REJEITADA",
                 fundamento="não").get_data(as_text=True)
    assert "fundamento" in html


# ---------------------------------------------------------- celebração


def test_o_ciclo_inteiro_termina_no_assento(casa):
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor=TEOR)
    _mandar_prazo_para_tras(casa, hid)
    _post(casa, hid, acao="habilitar")
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   situacao, origem, criado_em)
               VALUES ('RC_B','CASAMENTO',40,'FULANO E BELTRANA','2026-09-20',
                       'ATIVO','MANUAL','2026-09-20T10:00:00')""")
        assento = int(cur.lastrowid)
    _post(casa, hid, acao="celebrado", assento_id=assento)
    linha = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?",
                        (hid,)).fetchone()
    assert linha["situacao"] == "CELEBRADO"
    assert linha["casamento_assento_id"] == assento
    assert "Nada a fazer" in _ficha(casa, hid)


def test_assento_que_nao_existe_e_recusado_com_frase_de_balcao(casa):
    """A lição do usucapião: sem conferir, virava HTTP 500 no fim de meses."""
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor=TEOR)
    _mandar_prazo_para_tras(casa, hid)
    _post(casa, hid, acao="habilitar")
    r = _post(casa, hid, acao="celebrado", assento_id=99999)
    assert r.status_code == 200
    assert "não existe" in r.get_data(as_text=True)


def _habilitar_para_casamento(casa, hid):
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor=TEOR)
    _mandar_prazo_para_tras(casa, hid)
    _post(casa, hid, acao="habilitar")


def test_habilitada_oferece_registrar_casamento(casa):
    hid = _abrir(casa)
    _habilitar_para_casamento(casa, hid)
    html = _ficha(casa, hid)
    assert "Registrar casamento" in html
    assert f"habilitacao_id={hid}" in html


def test_novo_casamento_prefill_via_habilitacao_id(casa):
    hid = _abrir(casa)
    _habilitar_para_casamento(casa, hid)
    html = casa["cliente"].get(
        f"/rcpn/novo/casamento?habilitacao_id={hid}").get_data(as_text=True)
    assert "FULANO DE TAL" in html
    assert "BELTRANA DE TAL" in html
    assert 'name="habilitacao_id"' in html
    assert "habilitação" in html.lower()


def test_ficha_assento_aponta_hc_pendente(casa):
    hid = _abrir(casa)
    _habilitar_para_casamento(casa, hid)
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   situacao, origem, dados_json, criado_em)
               VALUES ('RC_B','CASAMENTO',41,'FULANO E BELTRANA','2026-09-20',
                       'ATIVO','MANUAL',?, '2026-09-20T10:00:00')""",
            (f'{{"habilitacao_id": {hid}}}',))
        assento = int(cur.lastrowid)
    html = casa["cliente"].get(f"/rcpn/{assento}").get_data(as_text=True)
    assert "Habilitação de casamento" in html
    assert str(assento) in html
    assert f"/rcpn/habilitacoes/{hid}" in html


# ------------------------------------------------------------- geral


def test_habilitacao_que_nao_existe_da_404(casa):
    assert casa["cliente"].get("/rcpn/habilitacoes/99999").status_code == 404


def test_a_tela_cai_no_modulo_do_registro_civil(casa):
    """O módulo do menu sai do PREFIXO da rota, e não de uma lista."""
    html = casa["cliente"].get("/rcpn/habilitacoes").get_data(as_text=True)
    nav = html[html.find("<nav>"):html.find("</nav>")]
    # O PADRAO E TOLERANTE A ATRIBUTOS — correcao de 30/08/2026. A primeira
    # versao exigia `<details class="nav-modulo" open>`, com o `>` colado no
    # `open`, e quebrou no dia em que cada grupo ganhou a cor do modulo
    # (relato #32). O que este teste quer saber e se o grupo ABRE, e nao em que
    # ordem os atributos foram escritos.
    achado = re.search(
        r'<details[^>]*class="nav-modulo"[^>]*\sopen[^>]*>\s*<summary>([^<\n]*)',
        nav)
    assert achado and "Registro Civil" in achado.group(1)


# ---------------------------------------------------------------------------
# O SELO DA HABILITAÇÃO E O e-PROCLAMAS
#
# Duas decisões do oficial em 28/08/2026, quando perguntei o que não dava para
# medir:
#
#   «Dois selos, um na habilitação e outro no assento.» — e o contrato confirma
#   o desenho: o selo do ASSENTO tem `seloReferencia`, que existe para citar o
#   selo do ato de habilitação. Um selo só não teria o que referenciar.
#
#   «É publicado digitalmente no e-Proclamas pela CRC.» — não é afixação no
#   lugar de costume nem publicação na imprensa, que eram as duas hipóteses que
#   eu tinha.


def _ate_habilitar(casa) -> int:
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor=TEOR)
    _mandar_prazo_para_tras(casa, hid)
    _post(casa, hid, acao="habilitar")
    return hid


def test_a_falha_do_selador_nao_expede_a_habilitacao(casa):
    """A falha cancela só a certidão; documentos, edital e prazo ficam."""
    casa["selador"].recusar_com = (400, {"message": "aparelho recusou"})
    hid = _ate_habilitar(casa)
    linha = _con(casa).execute(
        "SELECT * FROM hc_habilitacoes WHERE id=?", (hid,)).fetchone()
    assert linha["situacao"] == "EDITAL_PUBLICADO"
    assert linha["certidao_numero"] is None
    assert linha["edital_em"] == "2020-01-01"
    assert _con(casa).execute(
        "SELECT COUNT(*) n FROM hc_documentos WHERE habilitacao_id=? "
        "AND apresentado_em IS NOT NULL", (hid,)).fetchone()["n"] == 8


def test_a_tela_diz_que_nao_expediu_e_da_o_motivo(casa):
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor=TEOR)
    _mandar_prazo_para_tras(casa, hid)
    casa["selador"].recusar_com = (400, {"message": "motivo da bancada"})
    html = _post(casa, hid, acao="habilitar").get_data(as_text=True)
    assert "NÃO expedida" in html
    assert "motivo da bancada" in html


def test_corrigida_a_falha_o_mesmo_processo_pode_ser_habilitado(casa):
    casa["selador"].recusar_com = (400, {"message": "falha temporária"})
    hid = _ate_habilitar(casa)
    casa["selador"].recusar_com = None
    html = _post(casa, hid, acao="habilitar").get_data(as_text=True)
    linha = _con(casa).execute(
        "SELECT situacao, certidao_numero, selo FROM hc_habilitacoes WHERE id=?",
        (hid,)).fetchone()
    assert linha["situacao"] == "HABILITADO"
    assert linha["certidao_numero"] == 1
    assert linha["selo"]
    assert "expedida" in html


def test_a_ficha_pede_o_protocolo_do_eproclamas(casa):
    """Quem esquecer de publicar só descobre quando alguém perguntar."""
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor=TEOR)
    html = _ficha(casa, hid)
    assert "e-Proclamas" in html
    assert "Falta publicar" in html
    assert 'name="protocolo"' in html


def test_anotado_o_protocolo_o_aviso_some(casa):
    hid = _abrir(casa)
    _entregar_tudo(casa, hid)
    _post(casa, hid, acao="edital", teor=TEOR)
    _post(casa, hid, acao="eproclamas", protocolo="CRC-2026-00123")
    html = _ficha(casa, hid)
    assert "Falta publicar" not in html
    assert "CRC-2026-00123" in html
    assert _con(casa).execute(
        "SELECT eproclamas_protocolo p FROM hc_habilitacoes WHERE id=?",
        (hid,)).fetchone()["p"] == "CRC-2026-00123"

# OS TESTES DO ENVELOPE MORAM EM `test_selo_do_casamento.py`, e não aqui: lá
# eles são conferidos contra o contrato lido do `selador-doc`, e não contra uma
# lista de campos que eu escreveria duas vezes. Aqui fica o que é de TELA.


# --------------------------------------- a conversão de união estável
#
# O CONTRATO EXIGE O PROCESSO DA UNIÃO, e não o desta habilitação. Sem campo
# para ele, a conversão sairia sem selo — e o escrevente não teria como saber
# por quê, porque a recusa viria da rede.


def test_a_conversao_pede_a_uniao_estavel_na_ficha(casa):
    hid = _abrir(casa, tipo="CONVERSAO")
    html = _ficha(casa, hid)
    assert "união estável" in html
    assert "Falta dizer que união estável" in html
    assert 'value="uniao_estavel"' in html


def test_o_casamento_civil_comum_nao_pede_uniao_estavel(casa):
    """Perguntar isso a quem casa pela primeira vez é campo que confunde."""
    hid = _abrir(casa)
    assert "Falta dizer que união estável" not in _ficha(casa, hid)


def test_anotada_a_uniao_o_aviso_some(casa):
    hid = _abrir(casa, tipo="CONVERSAO")
    _post(casa, hid, acao="uniao_estavel",
          processo="ESCRITURA 123, LIVRO 40, FL. 12")
    html = _ficha(casa, hid)
    assert "Falta dizer que união estável" not in html
    assert "ESCRITURA 123, LIVRO 40, FL. 12" in html


def test_o_dominio_recusa_uniao_estavel_em_casamento_comum(casa):
    """Botão escondido não impede POST forjado — quem recusa é a regra."""
    hid = _abrir(casa)
    html = _post(casa, hid, acao="uniao_estavel",
                 processo="ESCRITURA 1").get_data(as_text=True)
    assert "Só a conversão" in html


# ------------------------------------------------------ UM SELO SÓ, pela tela
#
# «O selo é emitido uma vez apenas. Ele é reaproveitado apenas no assento, mas
#  já foi emitido na habilitação.» — o oficial, 28/08/2026.


def _assento_com_registro(casa) -> tuple[int, int]:
    """Um assento de casamento já lavrado, como o RCPN o deixa."""
    con = _con(casa)
    with con:
        a = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   situacao, origem, criado_em)
               VALUES ('RC_B','CASAMENTO',40,'FULANO E BELTRANA','2026-09-20',
                       'ATIVO','MANUAL','2026-09-20T10:00:00')""").lastrowid
        ato = con.execute(
            """INSERT INTO rc_atos (assento_id, tipo, data_ato, criado_em)
               VALUES (?,'REGISTRO','2026-09-20','2026-09-20T10:00:00')""",
            (a,)).lastrowid
    return int(a), int(ato)


def test_amarrar_o_casamento_leva_o_selo_para_o_assento(casa):
    hid = _ate_habilitar(casa)
    con = _con(casa)
    with con:
        con.execute("UPDATE hc_habilitacoes SET selo='UMSELOSO' WHERE id=?",
                    (hid,))
    assento, ato = _assento_com_registro(casa)
    _post(casa, hid, acao="celebrado", assento_id=assento)
    assert _con(casa).execute("SELECT selo FROM rc_atos WHERE id=?",
                              (ato,)).fetchone()["selo"] == "UMSELOSO"


def test_o_andamento_conta_que_o_selo_foi_para_o_assento(casa):
    """Quem abrir a ficha daqui a dois anos precisa saber que é um selo só."""
    hid = _ate_habilitar(casa)
    con = _con(casa)
    with con:
        con.execute("UPDATE hc_habilitacoes SET selo='UMSELOSO' WHERE id=?",
                    (hid,))
    assento, _ = _assento_com_registro(casa)
    _post(casa, hid, acao="celebrado", assento_id=assento)
    html = _ficha(casa, hid)
    assert "UMSELOSO" in html
