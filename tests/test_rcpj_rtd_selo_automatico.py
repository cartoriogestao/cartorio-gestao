"""Emissão automática de selo na averbação RCPJ/RTD.

Pedido do oficial (11/09/2026): depois de lavrar a averbação, o próprio
sistema emite o selo — como nos outros atos (`_selar_o_ato`), e não só o
campo opcional digitado à mão.

O QUE ESTES TESTES PROTEGEM
    1. Ao lançar averbação COM item a selar, a tela tenta `_selar_o_ato`
       (máquina mockada via `selar_o_ato_lavrado`).
    2. Se a máquina falhar / não existir, o ato continua de pé SEM selo
       inventado.
    3. O caminho da averbação distingue série PJ vs TD.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from navegador_de_teste import postar_e_seguir  # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, "ADMIN")
    cg_casa['db'].set_settings({
        # A TRAVA DO SELO PAGO (3.7.0, achado A9) desliga aqui, à vista: estes
        # testes medem o selo do ato do RCPJ/RTD (o pedido, o digitado, a prévia),
        # e não a cobertura, que tem teste próprio (`test_selo_e_caixa`). Sem
        # isso o selo digitado da abertura esperava protocolo pago e o registro
        # não nascia.
        "selo_trava_caixa": "DESLIGADA",
        "selo_tabela_custas_em": "20260101",
        "ri_cns": "000000",
    })
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    bancada = {"app": app, "c": c, "banco": banco, "dados": dados,
               "db": cg_casa["db"]}
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(bancada) as aparelho:
        bancada["selador"] = aparelho
        yield bancada


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _abrir_registro(s, *, serie="TD_B") -> int:
    html = s["c"].get("/rcpj-rtd/novo").get_data(as_text=True)
    quantos = _con(s).execute("SELECT COUNT(*) FROM rg_registros").fetchone()[0]
    selo_abertura = f"AVESVD000000NARRKWVNJCRSVO{22 + int(quantos):02d}"
    dados = {"csrf_token": _token(html), "serie": serie,
             "natureza": "CONTRATO SOCIAL",
             "requerente_nome": "EMPRESA X LTDA",
             "requerente_documento": "12345678000199",
             "teor": "Registro de contrato social da empresa X.",
             # A abertura não é o objeto destes testes. Ela chega já com um
             # selo válido para a averbação ser o único ato sob medição.
             "selo": selo_abertura}
    if serie in ("PJ_A", "PJ_B"):
        # contrato social com fins econômicos: fora dos arts. 410, 412 e 413
        dados["enquadramento_cnma"] = "NAO_SE_APLICA"
        dados["justificativa_cnma"] = (
            "Contrato social com fins econômicos, fora dos arts. 410, 412 e 413.")
    s["c"].post("/rcpj-rtd/novo", data=dados, follow_redirects=True)
    return int(_con(s).execute(
        "SELECT id FROM rg_registros ORDER BY id DESC LIMIT 1").fetchone()[0])


def _com_servico(s, codigo=91001, codigo_tj="15.7.1", total="53,58") -> int:
    con = _con(s)
    with con:
        con.execute(
            "INSERT OR IGNORE INTO cx_vigencias(codigo, vigente) VALUES (1,1)")
        con.execute(
            """INSERT OR IGNORE INTO cx_servicos(codigo, codigo_tj, descricao)
               VALUES (?,?, 'Serviço RTDPJ de teste')""",
            (codigo, codigo_tj))
        con.execute(
            """INSERT INTO cx_servico_valores(servico, vigencia,
                   emolumentos, ferc, femp, fadep, ferrfis, total)
               VALUES (?,1,?, '0,00','0,00','0,00','0,00', ?)""",
            (codigo, total, total))
    con.close()
    return codigo


def _abrir_caixa(s) -> int:
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO cx_caixas(data, operador_nome, aberto_em, situacao)
               VALUES ('2026-09-11','MARIO EXEMPLO DOS SANTOS',
                       '2026-09-11T08:00:00','ABERTO')""")
        cid = con.execute("SELECT id FROM cx_caixas").fetchone()[0]
    con.close()
    return int(cid)


def _lancar_averbacao(s, registro_id: int, **extra) -> str:
    html = s["c"].get(f"/rcpj-rtd/{registro_id}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "tipo": "AVERBACAO",
             "teor": "Averbação de alteração do endereço da sede da empresa."}
    dados.update(extra)
    serie = _con(s).execute(
        "SELECT serie FROM rg_registros WHERE id=?", (registro_id,)).fetchone()
    if serie and serie["serie"] in ("PJ_A", "PJ_B") and "enquadramento_cnma" not in dados:
        dados["enquadramento_cnma"] = "NAO_SE_APLICA"
        dados["justificativa_cnma"] = (
            "Averbação fora dos arts. 410, 412 e 413 do CN-MA.")
    # Com selo, a averbação leva à etiqueta por 307 (`navegador_de_teste`).
    return postar_e_seguir(
        s["c"], f"/rcpj-rtd/{registro_id}/lancar", dados).get_data(as_text=True)


def test_caminho_averbacao_pj_vs_td():
    import ato_selado as AS
    assert AS.caminho_do_rtdpj("AVERBACAO", "PJ_A") == (
        "/selo/rtdpj/pessoa-juridica/averbacao")
    assert AS.caminho_do_rtdpj("AVERBACAO", "TD_B") == (
        "/selo/rtdpj/ato-declarado/averbacao/integral/sem-valor")
    assert AS.caminho_do_rtdpj("REGISTRO", "PJ_A") == (
        "/selo/rtdpj/atos-em-geral")
    assert AS.caminho_do_ato("rg_atos", "AVERBACAO", especie="PJ_B") == (
        "/selo/rtdpj/pessoa-juridica/averbacao")


def test_envelope_atos_em_geral_sem_protocolo():
    import ato_selado as AS
    env = AS.envelope_do_rtdpj(
        caminho=AS.CAMINHO_RTDPJ_GERAL, codigo_tj="15.7.1",
        escrevente="TESTE", versao_tabela="0420260101",
        partes=[{"nome": "EMPRESA X", "documento": "123"}])
    assert env["ato"]["codigo"] == "15.7.1"
    assert "selo" not in env


def test_envelope_averbacao_exige_protocolo():
    import ato_selado as AS
    with pytest.raises(AS.AtoError, match="protocolo"):
        AS.envelope_do_rtdpj(
            caminho=AS.CAMINHO_AVERBACAO_TD, codigo_tj="15.7.1",
            escrevente="TESTE", versao_tabela="0420260101",
            livro="7", registro_averbacao="28",
            partes=[{"nome": "X"}])


def test_apos_averbar_tenta_selar_o_ato(s):
    """Com item a selar, lavrar chama selar_o_ato_lavrado (padrão _selar_o_ato)."""
    import ato_selado as AS

    rid = _abrir_registro(s, serie="TD_B")
    servico = _com_servico(s)
    _abrir_caixa(s)
    chamadas = []

    def _spy(db, pasta, **kw):
        chamadas.append({k: kw.get(k) for k in (
            "tabela", "ato_id", "tipo", "atribuicao", "especie", "caminho")})
        numero = "AUTENT000000TESTE0000000001"
        # Espelha o vínculo que a função real faria — o teste confere o ato.
        with db.transaction() as con:
            AS.vincular_ao_ato(con, numero, tabela=kw["tabela"],
                               ato_id=kw["ato_id"], agora=kw["agora"])
        return {"selado": True, "numero": numero, "numeros": [numero],
                "caminho": kw.get("caminho") or "/selo/rtdpj/atos-em-geral"}

    with patch.object(AS, "selar_o_ato_lavrado", side_effect=_spy):
        html = _lancar_averbacao(s, rid, cobrar=str(servico), pagador="EMPRESA X")

    assert chamadas, (
        "depois de averbar com item a selar, deveria ter tentado "
        "selar_o_ato_lavrado (padrão _selar_o_ato)")
    assert chamadas[0]["tabela"] == "rg_atos"
    assert chamadas[0]["tipo"] == "AVERBACAO"
    assert chamadas[0]["especie"] == "TD_B"
    assert "AUTENT000000TESTE0000000001" in html

    ato = _con(s).execute(
        """SELECT * FROM rg_atos WHERE registro_id=? AND tipo='AVERBACAO'
            ORDER BY id DESC LIMIT 1""", (rid,)).fetchone()
    assert ato is not None
    assert ato["selo"] == "AUTENT000000TESTE0000000001"


def test_quantidade_maior_que_um_pede_um_selo_com_mais_folhas(s):
    """Correção do oficial (11/09/2026): «quando colocamos um item com maior

    quantidade, é maior quantidade de folhas naquele selo — não é pra gerar
    10 selos». `15.9.1` com quantidade 3 no protocolo pede UM selo só, com
    `quantidade=3` no envelope (a única exceção é a autenticação de cópia,
    ver o teste seguinte).
    """
    import ato_selado as AS

    rid = _abrir_registro(s, serie="TD_B")
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO cx_protocolos(numero, data_abertura, atribuicao,
                   interessado, situacao, criado_em)
               VALUES ('2026.09.002','2026-09-11','RTD','EMPRESA X','ABERTO',
                       '2026-09-11T09:00:00')""")
        pid = con.execute(  # o que acabou de entrar: abrir o registro já cria o protocolo dele
            "SELECT id FROM cx_protocolos ORDER BY id DESC LIMIT 1").fetchone()[0]
        con.execute(
            """INSERT INTO cx_protocolo_atos(protocolo_id, codigo_ato, quantidade)
               VALUES (?, '15.9.1', 3)""", (pid,))
    con.close()
    _abrir_caixa(s)

    chamadas = []

    def _spy(db, pasta, **kw):
        chamadas.append(kw)
        numero = f"AUTENT000000{len(chamadas):020d}"
        with db.transaction() as con:
            AS.vincular_ao_ato(con, numero, tabela=kw["tabela"],
                               ato_id=kw["ato_id"], agora=kw["agora"])
        return {"selado": True, "numero": numero, "numeros": [numero],
                "caminho": kw.get("caminho") or "/selo/rtdpj/atos-em-geral"}

    with patch.object(AS, "selar_o_ato_lavrado", side_effect=_spy):
        _lancar_averbacao(s, rid, protocolo_id=str(pid))

    assert len(chamadas) == 1, (
        "quantidade maior é UM selo com mais folhas, e não vários selos")
    assert chamadas[0]["dados"]["quantidade"] == 3, (
        "a quantidade do item tem de ir no campo 'quantidade' do envelope "
        "— é ele que diz ao aparelho quantas folhas tem o selo")


def test_autenticacao_de_copia_e_a_unica_excecao_por_unidade(s):
    """«ÚNICA exceção é a autenticação de cópia. Nela, 10 no item significa

    10 selos diferentes» — o oficial, 11/09/2026. O código TJ da
    autenticação de cópia é `13.18` (`/selo/notas/autenticacao`); com
    quantidade 4 no protocolo, saem 4 selos, cada um com referência própria.
    """
    import ato_selado as AS

    rid = _abrir_registro(s, serie="TD_B")
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO cx_protocolos(numero, data_abertura, atribuicao,
                   interessado, situacao, criado_em)
               VALUES ('2026.09.003','2026-09-11','RTD','EMPRESA X','ABERTO',
                       '2026-09-11T09:00:00')""")
        pid = con.execute(  # o que acabou de entrar: abrir o registro já cria o protocolo dele
            "SELECT id FROM cx_protocolos ORDER BY id DESC LIMIT 1").fetchone()[0]
        con.execute(
            """INSERT INTO cx_protocolo_atos(protocolo_id, codigo_ato, quantidade)
               VALUES (?, '13.18', 4)""", (pid,))
    con.close()
    _abrir_caixa(s)

    referencias = []

    def _spy(db, pasta, **kw):
        referencias.append(kw["referencia"])
        numero = f"AUTENT000000{len(referencias):020d}"
        with db.transaction() as con:
            AS.vincular_ao_ato(con, numero, tabela=kw["tabela"],
                               ato_id=kw["ato_id"], agora=kw["agora"])
        return {"selado": True, "numero": numero, "numeros": [numero],
                "caminho": kw.get("caminho") or "/selo/rtdpj/atos-em-geral"}

    with patch.object(AS, "selar_o_ato_lavrado", side_effect=_spy):
        _lancar_averbacao(s, rid, protocolo_id=str(pid))

    assert len(referencias) == 4, "autenticação de cópia: 4 no item são 4 selos"
    assert len(set(referencias)) == 4, (
        "cada cópia autenticada precisa de referência ÚNICA — referência "
        "repetida faz o aparelho devolver o mesmo selo em vez de vender um "
        "por cópia")


def test_apos_averbar_pj_usa_caminho_pessoa_juridica(s):
    import ato_selado as AS

    rid = _abrir_registro(s, serie="PJ_A")
    servico = _com_servico(s, codigo=91003)
    _abrir_caixa(s)
    caminhos = []

    def _spy(db, pasta, **kw):
        caminhos.append(kw.get("caminho") or AS.caminho_do_ato(
            kw["tabela"], kw["tipo"], kw.get("especie")))
        return {"selado": False, "motivo": "mock recusou",
                "caminho": caminhos[-1]}

    with patch.object(AS, "selar_o_ato_lavrado", side_effect=_spy):
        _lancar_averbacao(s, rid, cobrar=str(servico), pagador="EMPRESA X")

    assert caminhos, "deveria ter tentado selar"
    # Sem protocolo no formulário, cai em atos-em-geral (não inventa protocolo).
    assert caminhos[0] == "/selo/rtdpj/atos-em-geral"


def test_sem_maquina_averba_sem_inventar_selo(s):
    """Máquina ausente: a averbação é bloqueada e nenhum selo é inventado."""
    rid = _abrir_registro(s, serie="PJ_A")
    servico = _com_servico(s, codigo=91002)
    _abrir_caixa(s)
    s["selador"].recusar_com = (503, {"message": "aparelho indisponível"})

    html = _lancar_averbacao(s, rid, cobrar=str(servico), pagador="EMPRESA X")
    assert "Ato NÃO lançado" in html
    assert "Motivo:" in html

    ato = _con(s).execute(
        """SELECT * FROM rg_atos WHERE registro_id=? AND tipo='AVERBACAO'
            ORDER BY id DESC LIMIT 1""", (rid,)).fetchone()
    assert ato is not None
    assert "Selo não emitido" in (ato["motivo_cancelamento"] or "")


def test_selo_digitado_a_mao_impede_pedido_automatico(s):
    import ato_selado as AS

    rid = _abrir_registro(s, serie="TD_B")
    SELO = "AVESVD000000NARRKWVNJCRSVO21"
    chamadas = []

    def _spy(*a, **kw):
        chamadas.append(kw)
        return {"selado": True, "numero": "NAO_DEVERIA",
                "numeros": ["NAO_DEVERIA"], "caminho": "/x"}

    with patch.object(AS, "selar_o_ato_lavrado", side_effect=_spy):
        _lancar_averbacao(s, rid, selo=SELO)

    assert not chamadas, "com selo à mão não se pede outro ao aparelho"
    ato = _con(s).execute(
        """SELECT selo FROM rg_atos WHERE registro_id=? AND tipo='AVERBACAO'
            ORDER BY id DESC LIMIT 1""", (rid,)).fetchone()
    assert ato["selo"] == SELO


def test_averbacao_ganha_seu_selo_e_o_de_arquivamento_na_primeira(s):
    """Pedido do oficial (11/09/2026): um selo de averbação por averbação,

    mais um de arquivamento na primeira do pacote — e um não pode
    sobrescrever o outro na mesma coluna (registro 361/Santa Isabel: só o de
    arquivamento sobrou em `selo`, e o da própria averbação sumiu).
    """
    import ato_selado as AS

    rid = _abrir_registro(s, serie="TD_B")
    servico_av = _com_servico(s, codigo=91011, codigo_tj="15.9.1")
    servico_arq = _com_servico(s, codigo=91012, codigo_tj="15.22")
    _abrir_caixa(s)

    def _spy(db, pasta, **kw):
        referencia = str(kw.get("referencia") or "")
        if ":15.22:" in referencia:
            numero = "ARQUIV000000TESTEARQUIVAMENTO1"
        else:
            numero = "AVERBA000000TESTEAVERBACAO01"
        with db.transaction() as con:
            AS.vincular_ao_ato(con, numero, tabela=kw["tabela"],
                               ato_id=kw["ato_id"], agora=kw["agora"])
        return {"selado": True, "numero": numero, "numeros": [numero],
                "caminho": kw.get("caminho") or "/selo/rtdpj/atos-em-geral"}

    with patch.object(AS, "selar_o_ato_lavrado", side_effect=_spy):
        _lancar_averbacao(
            s, rid, cobrar=[str(servico_av), str(servico_arq)],
            pagador="EMPRESA X")

    ato = _con(s).execute(
        """SELECT selo, selo_arquivamento FROM rg_atos
            WHERE registro_id=? AND tipo='AVERBACAO'
            ORDER BY id DESC LIMIT 1""", (rid,)).fetchone()
    assert ato["selo"] == "AVERBA000000TESTEAVERBACAO01", (
        "o selo da própria averbação não pode sumir da coluna")
    assert ato["selo_arquivamento"] == "ARQUIV000000TESTEARQUIVAMENTO1"


def test_averbar_com_selo_leva_direto_a_etiqueta_do_titulo(s):
    """«gerar também uma etiqueta para colar no título original, que será

    devolvido» — pedido do oficial em 11/09/2026: depois de averbar com selo,
    a tela seguinte é a etiqueta pronta para imprimir e colar, não a ficha.
    """
    import ato_selado as AS

    rid = _abrir_registro(s, serie="TD_B")
    servico = _com_servico(s)
    _abrir_caixa(s)

    def _spy(db, pasta, **kw):
        numero = "AVERBA000000ETIQUETATESTE0001"
        with db.transaction() as con:
            AS.vincular_ao_ato(con, numero, tabela=kw["tabela"],
                               ato_id=kw["ato_id"], agora=kw["agora"])
        return {"selado": True, "numero": numero, "numeros": [numero],
                "caminho": kw.get("caminho") or "/selo/rtdpj/atos-em-geral"}

    with patch.object(AS, "selar_o_ato_lavrado", side_effect=_spy):
        html = _lancar_averbacao(s, rid, cobrar=str(servico), pagador="EMPRESA X")

    assert "Assim vai sair na tira" in html, (
        "com selo, deveria abrir direto a tela da etiqueta do título")
    assert "AVERBA000000ETIQUETATESTE0001" in html


def _abrir_protocolo(s, *, com_arquivamento: bool) -> int:
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO cx_protocolos(numero, data_abertura, atribuicao,
                   interessado, situacao, criado_em)
               VALUES ('2026.09.001','2026-09-11','RCPJ','EMPRESA X','ABERTO',
                       '2026-09-11T09:00:00')""")
        pid = con.execute(  # o que acabou de entrar: abrir o registro já cria o protocolo dele
            "SELECT id FROM cx_protocolos ORDER BY id DESC LIMIT 1").fetchone()[0]
        con.execute(
            """INSERT INTO cx_protocolo_atos(protocolo_id, codigo_ato, quantidade)
               VALUES (?, '15.9.1', 1)""", (pid,))
        if com_arquivamento:
            con.execute(
                """INSERT INTO cx_protocolo_atos(protocolo_id, codigo_ato, quantidade)
                   VALUES (?, '15.22', 1)""", (pid,))
    con.close()
    return int(pid)


def _anexo_real(s, registro_id: int, tmp_path) -> None:
    arquivo = tmp_path / "edital.pdf"
    arquivo.write_bytes(b"%PDF-1.4 conteudo de teste")
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO attachments(entity_type, entity_id, original_name,
                   stored_name, stored_path, sha256, size_bytes,
                   uploaded_by, uploaded_at)
               VALUES ('RG_REGISTRO', ?, 'edital.pdf', 'edital.pdf', ?,
                       'abc', ?, 1, '2026-09-11T09:00:00')""",
            (registro_id, str(arquivo), arquivo.stat().st_size))
    con.close()


def test_previa_reserva_arquivamento_quando_o_protocolo_tem_o_item(s, tmp_path):
    """Relato do oficial (11/09/2026): «tira aquele campo de incluir espaço

    para arquivamento, não faz sentido. O registro precisa ir com todos os
    selos do protocolo». Sem caixinha nenhuma: com o protocolo escolhido, a
    prévia reserva a faixa de arquivamento quando ELE tiver o item 15.22.
    """
    import rg_teor_rtdpj as TEOR

    rid = _abrir_registro(s, serie="TD_B")
    pid = _abrir_protocolo(s, com_arquivamento=True)
    _anexo_real(s, rid, tmp_path)

    html = s["c"].get(f"/rcpj-rtd/{rid}").get_data(as_text=True)
    tok = _token(html)
    chamou = {}

    def _spy(**kw):
        chamou.update(kw)
        return b"%PDF-teste"

    with patch.object(TEOR, "gerar_pdf", side_effect=_spy):
        s["c"].post(
            f"/rcpj-rtd/{rid}/teor-averbacao/previa",
            data={"csrf_token": tok, "tipo": "AVERBACAO",
                  "protocolo_id": str(pid)})
    assert chamou.get("com_arquivamento") is True


def test_previa_nao_reserva_arquivamento_quando_o_protocolo_nao_tem_o_item(s, tmp_path):
    import rg_teor_rtdpj as TEOR

    rid = _abrir_registro(s, serie="TD_B")
    pid = _abrir_protocolo(s, com_arquivamento=False)
    _anexo_real(s, rid, tmp_path)
    con = _con(s)
    with con:
        # já há uma averbação antes — sem protocolo, cairia em "1ª
        # averbação" e reservaria mesmo assim; o protocolo tem de mandar.
        con.execute(
            """INSERT INTO rg_atos(registro_id, tipo, data_ato, criado_em)
               VALUES (?, 'AVERBACAO', '2026-09-10', '2026-09-10T10:00:00')""",
            (rid,))
    con.close()

    html = s["c"].get(f"/rcpj-rtd/{rid}").get_data(as_text=True)
    tok = _token(html)
    chamou = {}

    def _spy(**kw):
        chamou.update(kw)
        return b"%PDF-teste"

    with patch.object(TEOR, "gerar_pdf", side_effect=_spy):
        s["c"].post(
            f"/rcpj-rtd/{rid}/teor-averbacao/previa",
            data={"csrf_token": tok, "tipo": "AVERBACAO",
                  "protocolo_id": str(pid)})
    assert chamou.get("com_arquivamento") is False


def test_previa_sem_protocolo_nao_reserva_arquivamento(s, tmp_path):
    """Correção do oficial (11/09/2026): «não tem nada que ligue 1 averbação

    a arquivamento, foi algo que o projeto entendeu errado». Sem protocolo
    não há como saber se este ato leva o item 15.22 — não se supõe mais que
    "é a 1ª averbação, logo leva arquivamento".
    """
    import rg_teor_rtdpj as TEOR

    rid = _abrir_registro(s, serie="TD_B")
    _anexo_real(s, rid, tmp_path)

    html = s["c"].get(f"/rcpj-rtd/{rid}").get_data(as_text=True)
    tok = _token(html)
    chamou = {}

    def _spy(**kw):
        chamou.update(kw)
        return b"%PDF-teste"

    with patch.object(TEOR, "gerar_pdf", side_effect=_spy):
        s["c"].post(
            f"/rcpj-rtd/{rid}/teor-averbacao/previa",
            data={"csrf_token": tok, "tipo": "AVERBACAO"})
    assert chamou.get("com_arquivamento") is False, (
        "sem protocolo não há como saber — não se supõe mais nada")


def test_a_previa_nao_pergunta_mais_com_checkbox(s):
    """O campo manual «incluir espaço de arquivamento» saiu da tela."""
    rid = _abrir_registro(s, serie="TD_B")
    html = s["c"].get(f"/rcpj-rtd/{rid}").get_data(as_text=True)
    assert 'name="com_arquivamento"' not in html
    assert "incluir espaço de arquivamento" not in html


def test_averbar_sem_item_nao_conclui_e_fica_na_ficha(s):
    """Sem item não há selo; o ato fica bloqueado e volta para a ficha."""
    rid = _abrir_registro(s, serie="TD_B")
    _abrir_caixa(s)
    html = _lancar_averbacao(s, rid)
    assert "Assim vai sair na tira" not in html
    assert "Ato NÃO lançado" in html
    ato = _con(s).execute(
        "SELECT motivo_cancelamento FROM rg_atos WHERE registro_id=? "
        "AND tipo='AVERBACAO' ORDER BY id DESC LIMIT 1", (rid,)).fetchone()
    assert ato and "Selo não emitido" in (ato[0] or "")


def test_a_ficha_nao_afirma_mais_regra_de_primeira_averbacao(s):
    """Correção do oficial (11/09/2026): «não tem nada que ligue 1 averbação

    a arquivamento, foi algo que o projeto entendeu errado». O aviso
    "esta será a 1ª averbação... marque também o 15.22" afirmava exatamente
    essa regra inexistente — e saiu da ficha. Arquivamento é só mais um item
    do protocolo, marcado (ou não) pelo operador em cada ato, sem depender
    de qual averbação é a primeira do pacote.
    """
    rid = _abrir_registro(s, serie="TD_B")
    html = s["c"].get(f"/rcpj-rtd/{rid}").get_data(as_text=True)
    assert "1ª averbação deste registro" not in html


def test_o_checklist_de_anexo_nao_esta_duplicado_na_ficha(s):
    """Relato do oficial (11/09/2026): «ficou duplicado o campo de seleção

    de arquivos para gerar teor de averbação e simulação do pdf». Os dois
    formulários (lançar e prévia) mostravam a mesma lista de anexos, cada um
    com a sua caixa de marcar — a prévia agora usa os mesmos anexos marcados
    no formulário de lançar, sem repetir a lista visível.
    """
    rid = _abrir_registro(s, serie="TD_B")
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO attachments(entity_type, entity_id, original_name,
                   stored_name, stored_path, sha256, size_bytes,
                   uploaded_by, uploaded_at)
               VALUES ('RG_REGISTRO', ?, 'edital.pdf', 'x.pdf', 'x.pdf',
                       'abc', 100, 1, '2026-09-11T09:00:00')""", (rid,))
    con.close()

    html = s["c"].get(f"/rcpj-rtd/{rid}").get_data(as_text=True)
    # Antes, "Imagens/PDF a vincular..." (no form de lançar) e "Folhas a
    # incluir..." (na prévia) eram a MESMA lista de anexos, duas vezes —
    # cada uma com a sua caixa de marcar. A prévia não tem mais checklist
    # próprio: usa o que estiver marcado no de lançar.
    assert html.count("a vincular a esta averbação") == 1
    assert "Folhas a incluir" not in html
    assert "Usa os mesmos anexos" in html
    assert 'id="form-previa-averbacao"' in html


def test_ficha_continua_sem_aviso_de_primeira_averbacao_depois_de_lancar(s):
    """A ausência do aviso (removido por não ter base — ver acima) continua

    valendo depois de já haver uma averbação lavrada no registro.
    """
    import ato_selado as AS

    rid = _abrir_registro(s, serie="TD_B")
    servico = _com_servico(s)
    _abrir_caixa(s)

    def _spy(db, pasta, **kw):
        numero = "AVERBA000000PRIMEIRAAVERBA001"
        with db.transaction() as con:
            AS.vincular_ao_ato(con, numero, tabela=kw["tabela"],
                               ato_id=kw["ato_id"], agora=kw["agora"])
        return {"selado": True, "numero": numero, "numeros": [numero],
                "caminho": kw.get("caminho") or "/selo/rtdpj/atos-em-geral"}

    with patch.object(AS, "selar_o_ato_lavrado", side_effect=_spy):
        _lancar_averbacao(s, rid, cobrar=str(servico), pagador="EMPRESA X")

    html = s["c"].get(f"/rcpj-rtd/{rid}").get_data(as_text=True)
    assert "1ª averbação deste registro" not in html


def test_item_marcado_do_protocolo_fica_indisponivel_para_o_proximo_ato(s):
    """Pedido do oficial (11/09/2026): «ligar todos os serviços ao protocolo

    e, cada vez que praticamos um ato, indicar o protocolo (...) e dai
    selecionamos quais queremos apontar com o ato a ser praticado». Um
    protocolo serve o trabalho INTEIRO do cliente — várias averbações — e o
    item marcado para UMA averbação não pode voltar a ser oferecido (e
    selado de novo) na PRÓXIMA averbação do mesmo protocolo.
    """
    import ato_selado as AS

    rid = _abrir_registro(s, serie="TD_B")
    pid = _abrir_protocolo(s, com_arquivamento=True)
    _abrir_caixa(s)
    con = _con(s)
    linhas = con.execute(
        """SELECT id, codigo_ato FROM cx_protocolo_atos
            WHERE protocolo_id=? ORDER BY id""", (pid,)).fetchall()
    con.close()
    assert [l[1] for l in linhas] == ["15.9.1", "15.22"]
    id_averbacao, id_arquivamento = linhas[0][0], linhas[1][0]

    referencias = []

    def _spy(db, pasta, **kw):
        referencias.append(kw["referencia"])
        numero = f"AVERBA0000000000000000000{len(referencias):03d}"
        with db.transaction() as con:
            AS.vincular_ao_ato(con, numero, tabela=kw["tabela"],
                               ato_id=kw["ato_id"], agora=kw["agora"])
        return {"selado": True, "numero": numero, "numeros": [numero],
                "caminho": kw.get("caminho") or "/selo/rtdpj/atos-em-geral"}

    # 1ª averbação: marca só o item da própria averbação (15.9.1), não o de
    # arquivamento — simula o operador desmarcando o que não é deste ato.
    with patch.object(AS, "selar_o_ato_lavrado", side_effect=_spy):
        _lancar_averbacao(s, rid, protocolo_id=str(pid),
                           protocolo_item_id=str(id_averbacao))
    assert len(referencias) == 1, "só o item marcado devia pedir selo"

    con = _con(s)
    consumido = con.execute(
        "SELECT usado_em, usado_por_ato_id FROM cx_protocolo_atos WHERE id=?",
        (id_averbacao,)).fetchone()
    ainda_livre = con.execute(
        "SELECT usado_em FROM cx_protocolo_atos WHERE id=?",
        (id_arquivamento,)).fetchone()
    con.close()
    assert consumido[0], "o item marcado tinha de ficar consumido"
    assert consumido[1], "o item consumido tem de apontar para o ato que o usou"
    assert not ainda_livre[0], (
        "o item NÃO marcado (arquivamento) tem de continuar disponível")

    # 2ª averbação do MESMO protocolo, sem marcar nada explicitamente: cai no
    # comportamento de pegar todos os itens AINDA não usados — e não deve
    # pedir selo de novo para o item já consumido pela 1ª.
    referencias.clear()
    with patch.object(AS, "selar_o_ato_lavrado", side_effect=_spy):
        _lancar_averbacao(s, rid, protocolo_id=str(pid))
    assert len(referencias) == 1, (
        "a 2ª averbação só devia pedir selo do item que sobrou (arquivamento)")
    assert referencias[0].endswith(":15.22:1")


def test_anexar_arquivo_novo_direto_no_form_de_lancar(s):
    """Pedido do oficial (11/09/2026): «não tem campo para juntar os

    arquivos que serão averbados». Antes só dava para marcar anexo já
    subido antes, numa seção separada da ficha. Agora um campo de arquivo
    no próprio formulário de lançar sobe o arquivo (RG_REGISTRO) e já liga
    ao ato (RG_ATO) que acabou de nascer — sem precisar ir a outra tela.
    """
    import io

    rid = _abrir_registro(s, serie="TD_B")
    _abrir_caixa(s)

    html = s["c"].get(f"/rcpj-rtd/{rid}").get_data(as_text=True)
    tok = _token(html)
    resp = postar_e_seguir(
        s["c"], f"/rcpj-rtd/{rid}/lancar",
        {
            "csrf_token": tok, "tipo": "AVERBACAO",
            "teor": "Averbação de alteração do endereço da sede da empresa.",
            "selo": "AVESVD000000NARRKWVNJCRSVO21",
            "novo_arquivo": (io.BytesIO(b"%PDF-1.4 conteudo"), "estatuto.pdf"),
        },
        content_type="multipart/form-data")
    resp_html = resp.get_data(as_text=True)
    assert resp.status_code == 200

    con = _con(s)
    ato = con.execute(
        """SELECT id FROM rg_atos WHERE registro_id=? AND tipo='AVERBACAO'
            ORDER BY id DESC LIMIT 1""", (rid,)).fetchone()
    assert ato is not None
    no_registro = con.execute(
        "SELECT COUNT(*) FROM attachments WHERE entity_type='RG_REGISTRO' "
        "AND entity_id=?", (rid,)).fetchone()[0]
    no_ato = con.execute(
        "SELECT COUNT(*) FROM attachments WHERE entity_type='RG_ATO' "
        "AND entity_id=?", (ato[0],)).fetchone()[0]
    con.close()
    assert no_registro == 1, "o arquivo enviado tem de virar anexo do registro"
    assert no_ato == 1, "e já ligado ao ato que acabou de ser lançado"
    assert "Assim vai sair na tira" in resp_html


def test_cobrar_protocolo_item_lanca_no_caixa(s):
    """Pedido do oficial (11/09/2026): «quero um jeito de marcar cobrança

    nesta tela do RCPJ/RTD». Como não há receita de cobrança MEDIDA para a
    maioria dos caminhos de averbação (o quadro de sempre não aparece), o
    item do PRÓPRIO protocolo — que já sabe o `servico_codigo` — pode ser
    marcado para cobrar, sem depender daquela medição.
    """
    import ato_selado as AS

    rid = _abrir_registro(s, serie="TD_B")
    servico = _com_servico(s, codigo=91050, codigo_tj="15.9.1", total="102,15")
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO cx_protocolos(numero, data_abertura, atribuicao,
                   interessado, situacao, criado_em)
               VALUES ('2026.09.005','2026-09-11','RCPJ','EMPRESA X','ABERTO',
                       '2026-09-11T09:00:00')""")
        pid = con.execute(  # o que acabou de entrar: abrir o registro já cria o protocolo dele
            "SELECT id FROM cx_protocolos ORDER BY id DESC LIMIT 1").fetchone()[0]
        con.execute(
            """INSERT INTO cx_protocolo_atos(protocolo_id, codigo_ato,
                   quantidade, servico_codigo, descricao)
               VALUES (?, '15.9.1', 1, ?, 'Averbação — 1ª folha')""",
            (pid, servico))
        item_id = con.execute(
            "SELECT id FROM cx_protocolo_atos WHERE protocolo_id=?",
            (pid,)).fetchone()[0]
    con.close()
    _abrir_caixa(s)

    def _spy(db, pasta, **kw):
        numero = "AVERBA000000COBRARTESTE00001"
        with db.transaction() as con:
            con.execute(
                """INSERT INTO sd_selos(numero, texto, obtido_em, obtido_por)
                   VALUES (?, 'teste', ?, 'teste')""", (numero, kw["agora"]))
            AS.vincular_ao_ato(con, numero, tabela=kw["tabela"],
                               ato_id=kw["ato_id"], agora=kw["agora"])
        return {"selado": True, "numero": numero, "numeros": [numero],
                "caminho": kw.get("caminho") or "/selo/rtdpj/atos-em-geral"}

    with patch.object(AS, "selar_o_ato_lavrado", side_effect=_spy):
        # Sai selado, e por isso a tela seguinte é a etiqueta — não a ficha
        # com a mensagem de "lançado no caixa" (que fica pelo caminho, como
        # em qualquer averbação selada). O que importa aqui é o lançamento.
        _lancar_averbacao(s, rid, protocolo_id=str(pid),
                          cobrar_protocolo_item=str(item_id))

    con = _con(s)
    lanc = con.execute(
        "SELECT valor FROM cx_lancamentos WHERE origem='ATO'").fetchone()
    con.close()
    assert lanc is not None, "o item marcado para cobrar tinha de lançar no caixa"
    assert lanc[0] == "102,15"


def test_selos_do_ato_traz_todos_nao_so_os_dois_da_coluna(s):
    """Achado do oficial (11/09/2026): «não foram todos os selos que eu

    selecionei» — `rg_atos` só guarda dois números (selo e selo de
    arquivamento), mas o ato pode ter mais itens selados que isso.
    `AS.selos_do_ato` é a fonte completa, direto de `sd_selos`.
    """
    import ato_selado as AS

    rid = _abrir_registro(s, serie="TD_B")
    pid = _abrir_protocolo(s, com_arquivamento=False)
    _abrir_caixa(s)
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO cx_protocolo_atos(protocolo_id, codigo_ato, quantidade)
               VALUES (?, '15.1', 1)""", (pid,))
    con.close()

    numeros = iter(["PRENOT0000000000000000000A", "AVERBA0000000000000000000B"])

    def _spy(db, pasta, **kw):
        numero = next(numeros)
        with db.transaction() as con:
            con.execute(
                """INSERT INTO sd_selos(numero, texto, obtido_em, obtido_por)
                   VALUES (?, 'teste', ?, 'teste')""", (numero, kw["agora"]))
            AS.vincular_ao_ato(con, numero, tabela=kw["tabela"],
                               ato_id=kw["ato_id"], agora=kw["agora"])
        return {"selado": True, "numero": numero, "numeros": [numero],
                "caminho": kw.get("caminho") or "/selo/rtdpj/atos-em-geral"}

    with patch.object(AS, "selar_o_ato_lavrado", side_effect=_spy):
        _lancar_averbacao(s, rid, protocolo_id=str(pid))

    con = _con(s)
    ato_id = con.execute(
        """SELECT id FROM rg_atos WHERE registro_id=? AND tipo='AVERBACAO'
            ORDER BY id DESC LIMIT 1""", (rid,)).fetchone()[0]
    todos = AS.selos_do_ato(con, "rg_atos", ato_id)
    con.close()
    assert len(todos) == 2, (
        "os dois itens (15.1 e 15.9.1) deviam ter, cada um, o seu selo — "
        "e AS.selos_do_ato tem de trazer os dois")
