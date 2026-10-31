"""
Testes das telas das quatro atribuicoes novas.

O QUE ELES CONFEREM
    Que a tela ABRE, que ela MOSTRA o que o banco tem, e que ela nao oferece o
    que ainda nao existe:

      - as quatro listas abrem, com e sem dado;
      - a lista vazia diz onde trazer o acervo, em vez de so mostrar nada;
      - a ficha abre e traz os atos;
      - a divisao tripartite do RCPN aparece em blocos proprios, que e o que a
        inspecao de 12/08/2026 cobra;
      - a tela de carga roda a carga e mostra os numeros;
      - a carga e so de ADMIN;
      - ficha de registro que nao existe nao estoura: avisa e volta.
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
from prova_de_intimacao import juntar_prova  # noqa: E402
from navegador_de_teste import postar_e_seguir  # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(tmp_path, papel: str = "ADMIN"):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(banco)
    db.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    # O PROTESTO ESTA DESLIGADO DE FABRICA desde 01/09/2026 — ordem do
    # oficial. Estes testes exercitam as TELAS dele, e por isso o LIGAM
    # aqui, de proposito e a vista: eles provam que o modulo funciona
    # quando ele voltar, que e o que «fica para um futuro» quer dizer.
    db.set_settings({"modulo_protesto_ligado": "1"})
    # A TRAVA DO SELO PAGO (3.7.0, 22/10/2026) TAMBEM SE DESLIGA AQUI, a vista:
    # sem protocolo 'em atendimento' nenhum selo sai, e estes testes medem as
    # TELAS das atribuicoes (selo digitado amarrado ao ato, certidao, averbacao),
    # e nao a trava, que tem teste proprio em `test_selo_e_caixa`.
    db.set_settings({"selo_trava_caixa": "DESLIGADA"})
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "dados": dados, "db": db}


@pytest.fixture()
def s(tmp_path):
    sessao = _sessao(tmp_path)
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(sessao):
        yield sessao


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _semear(s) -> dict:
    """Um registro em cada atribuicao, gravado direto — a tela so consulta."""
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
                   protocolo,
                   valor_centavos, saldo_centavos, situacao, origem,
                   origem_chave, criado_em)
               VALUES ('DMI','84713/1','00200000991','2608240001',148278,148278,
                       'PROTESTADO','CRA','t:1','2026-08-24T09:00:00')""")
        titulo_id = con.execute("SELECT id FROM pt_titulos").fetchone()["id"]
        con.execute(
            """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
                   documento_numero, cidade, uf)
               VALUES (?,'DEVEDOR TESTE','CNPJ','00000019000138',
                       'CIDADE EXEMPLO','MA')""", (titulo_id,))
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, folha, numero_ordem,
                   data_ato, origem, criado_em)
               VALUES (?,'APONTAMENTO',3,912,'2026-08-24','EOFICIO',
                       '2026-08-24T09:00:00')""", (titulo_id,))
        con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, nome, data_fato,
                   dados_json, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',19552,'JOÃO DA SILVA','2020-01-15',
                       '{"strSexo": "M"}','ATIVO','EOFICIO',
                       '2026-08-24T09:00:00')""")
        assento_id = con.execute("SELECT id FROM rc_assentos").fetchone()["id"]
        for tipo, teor in (("REGISTRO", "Assento de nascimento."),
                           ("AVERBACAO", "Averbação de casamento."),
                           ("ANOTACAO", "Anotação remissiva ao Livro B."),
                           ("RETIFICACAO", "Corrige grafia do nome.")):
            con.execute(
                """INSERT INTO rc_atos(assento_id, tipo, data_ato, teor,
                       origem, criado_em)
                   VALUES (?,?,'2026-08-24',?, 'MANUAL','2026-08-24T09:00:00')""",
                (assento_id, tipo, teor))
        con.execute(
            """INSERT INTO rg_registros(atribuicao, serie, numero,
                   requerente_nome, situacao, origem, criado_em)
               VALUES (4,'TD_B',1508,'EMPRESA X','ATIVO','EOFICIO',
                       '2026-08-24T09:00:00')""")
        registro_rg = con.execute("SELECT id FROM rg_registros").fetchone()["id"]
        con.execute(
            """INSERT INTO rg_atos(registro_id, tipo, data_ato, origem,
                   criado_em)
               VALUES (?, 'REGISTRO', '2026-08-24', 'EOFICIO',
                       '2026-08-24T09:00:00')""", (registro_rg,))
        con.execute(
            """INSERT INTO ra_registros(numero, livro, natureza, titulo_tipo,
                   titulo_numero, valor_centavos, situacao, origem, criado_em)
               VALUES (1549,'3','CEDULA_CREDITO_RURAL',
                       'CÉDULA RURAL PIGNORATICIA','40/01800-8',29980950,
                       'ATIVO','EOFICIO','2026-08-24T09:00:00')""")
        registro_ra = con.execute("SELECT id FROM ra_registros").fetchone()["id"]
        con.execute(
            """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato, origem,
                   criado_em)
               VALUES (?,'R',1,'2026-08-24','EOFICIO','2026-08-24T09:00:00')""",
            (registro_ra,))
    ids = {
        "titulo": titulo_id,
        "assento": assento_id,
        "registro": con.execute("SELECT id FROM rg_registros").fetchone()["id"],
        "livro3": registro_ra,
    }
    con.close()
    return ids


# --------------------------------------------------------------- as listas


@pytest.mark.parametrize("rota", ["/protesto", "/rcpn", "/rcpj-rtd", "/livro3"])
def test_as_quatro_listas_abrem_vazias_e_dizem_onde_trazer_o_acervo(s, rota):
    # Lista vazia que so mostra nada faz o operador achar que quebrou. Esta
    # dizia onde estava o botao da carga do E-Oficio. Desde 17/10/2026 a
    # importacao terminou e o botao saiu: a lista vazia diz «Nada aqui» e nao
    # aponta mais para a carga.
    html = s["c"].get(rota).get_data(as_text=True)
    assert "Nada aqui" in html
    assert "/atribuicoes/importar" not in html
    assert "Trazer das atribuições" not in html


@pytest.mark.parametrize("rota,esperado", [
    # A LISTA DO PROTESTO ABRE NOS PENDENTES desde 14/10/2026 (pedido do
    # oficial), e o titulo semeado aqui esta PROTESTADO — por isso a vista
    # «todos». O que este teste guarda continua o mesmo: a lista mostra o
    # que o banco tem.
    ("/protesto?vista=todos", "84713/1"),
    ("/rcpn", "JOÃO DA SILVA"),
    ("/rcpj-rtd", "EMPRESA X"),
    ("/livro3", "40/01800-8"),
])
def test_as_quatro_listas_mostram_o_que_o_banco_tem(s, rota, esperado):
    _semear(s)
    html = s["c"].get(rota).get_data(as_text=True)
    assert esperado in html


def test_a_lista_filtra_pelo_termo(s):
    _semear(s)
    c = s["c"]
    assert "84713/1" in c.get("/protesto?q=84713").get_data(as_text=True)
    assert "Nada aqui" in c.get("/protesto?q=zzzznada").get_data(as_text=True)


def test_a_lista_do_protesto_acha_pelo_nome_e_pelo_documento_do_devedor(s):
    # A PERGUNTA DO GUICHE E "fulano tem protesto?", e nao "onde esta o titulo
    # 84713/1". O devedor mora em `pt_devedores`, e procurar so nas colunas de
    # `pt_titulos` deixaria a pergunta do balcao sem resposta.
    _semear(s)
    c = s["c"]
    assert "84713/1" in c.get("/protesto?q=DEVEDOR").get_data(as_text=True)
    assert "84713/1" in c.get("/protesto?q=00000019000138").get_data(as_text=True)
    assert "Nada aqui" in c.get("/protesto?q=NINGUEM").get_data(as_text=True)


def test_a_lista_do_protesto_mostra_quem_e_o_devedor(s):
    _semear(s)
    # O titulo semeado esta PROTESTADO; a lista abre nos pendentes (14/10/2026).
    assert "DEVEDOR TESTE" in s["c"].get("/protesto?vista=todos").get_data(as_text=True)


def test_a_lista_filtra_pela_situacao(s):
    _semear(s)
    c = s["c"]
    assert "84713/1" in c.get("/protesto?situacao=PROTESTADO").get_data(as_text=True)
    assert "Nada aqui" in c.get("/protesto?situacao=PAGO").get_data(as_text=True)


def test_a_lista_manda_abrir_a_ficha_para_lancar(s):
    # A lista consulta; quem lanca e a ficha, onde o dominio sabe o que cabe.
    html = s["c"].get("/protesto").get_data(as_text=True)
    assert "abra a ficha" in html.lower()


# --------------------------------------------------------------- as fichas


def test_a_ficha_do_titulo_traz_devedor_e_atos(s):
    ids = _semear(s)
    html = s["c"].get(f"/protesto/{ids['titulo']}").get_data(as_text=True)
    assert "DEVEDOR TESTE" in html
    assert "APONTAMENTO" in html
    assert "912" in html                    # o numero de ordem do acervo


def test_a_ficha_do_assento_mostra_a_divisao_tripartite_em_blocos(s):
    # E o que a inspecao de 12/08/2026 cobra: campo proprio para nota,
    # averbacao e retificacao — e nao tres paragrafos de um campo so.
    ids = _semear(s)
    html = s["c"].get(f"/rcpn/{ids['assento']}").get_data(as_text=True)
    for rotulo in ("Averbações", "Anotações", "Retificações"):
        assert rotulo in html
    assert "Averbação de casamento." in html
    assert "Corrige grafia do nome." in html


def test_a_ficha_do_assento_sem_matricula_diz_como_ela_se_compoe(s):
    """Desde o #152 (03/09/2026) a matrícula de 32 dígitos se gera ao lavrar;
    o assento sem ela veio do acervo, ou faltou um dado na lavratura."""
    ids = _semear(s)
    html = s["c"].get(f"/rcpn/{ids['assento']}").get_data(as_text=True)
    assert "Ao lavrar, o sistema a compõe com o CNS" in html


def test_a_ficha_do_rtd_diz_que_a_averbacao_consome_protocolo(s):
    ids = _semear(s)
    html = s["c"].get(f"/rcpj-rtd/{ids['registro']}").get_data(as_text=True)
    assert "consome protocolo" in html


def test_a_ficha_do_rcpj_rtd_lista_anexos_do_registro(s):
    """Anexos entity_type RG_REGISTRO aparecem na ficha; upload opcional."""
    from io import BytesIO
    ids = _semear(s)
    rid = ids["registro"]
    # um anexo ja no banco, como os do acervo (folha + pacote)
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO attachments(entity_type, entity_id, original_name,
                   stored_name, stored_path, sha256, size_bytes, description,
                   uploaded_by, uploaded_at)
               VALUES ('RG_REGISTRO', ?, 'folha_067.jpg', 'folha_067.jpg',
                       'x', 'abc', 100, 'Folha 067', NULL,
                       '2026-09-11T12:00:00')""", (rid,))
    con.close()
    html = s["c"].get(f"/rcpj-rtd/{rid}").get_data(as_text=True)
    assert "Imagens / anexos do livro" in html
    assert "folha_067.jpg" in html
    assert "Folha 067" in html
    assert "/arquivo/" in html and "/ver" in html
    assert "Baixar" in html
    # upload opcional
    token = _token(html)
    r = s["c"].post(
        f"/rcpj-rtd/{rid}/arquivo",
        data={"csrf_token": token, "descricao": "Pacote PDF",
              "arquivo": (BytesIO(b"%PDF-1.4 teste"), "pacote.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True)
    assert r.status_code == 200
    html2 = r.get_data(as_text=True)
    assert "pacote.pdf" in html2
    assert "Arquivo anexado" in html2 or "Pacote PDF" in html2



def test_a_ficha_do_livro_3_traz_o_titulo_e_o_ato(s):
    ids = _semear(s)
    html = s["c"].get(f"/livro3/{ids['livro3']}").get_data(as_text=True)
    assert "CÉDULA RURAL PIGNORATICIA" in html
    assert "R-1" in html


@pytest.mark.parametrize("rota", ["/protesto/9999", "/rcpn/9999",
                                  "/rcpj-rtd/9999", "/livro3/9999"])
def test_ficha_que_nao_existe_avisa_e_volta(s, rota):
    r = s["c"].get(rota, follow_redirects=True)
    assert r.status_code == 200
    assert "não encontrad" in r.get_data(as_text=True)


# ---------------------------------------------------------------- a carga


def test_a_tela_de_carga_abre_e_conta_o_que_ja_ha(s):
    _semear(s)
    html = s["c"].get("/atribuicoes/importar").get_data(as_text=True)
    assert "Trazer do E-Ofício" in html
    assert "Protesto" in html


def test_a_tela_de_carga_avisa_quando_o_acervo_nao_esta_no_lugar(s):
    # O acervo nao existe na pasta de dados do teste.
    html = s["c"].get("/atribuicoes/importar").get_data(as_text=True)
    assert "acervo não está no lugar" in html


def test_a_carga_e_so_de_admin(tmp_path):
    sessao = _sessao(tmp_path, papel="USER")
    assert sessao["c"].get("/atribuicoes/importar").status_code == 403


def test_o_balcao_ve_as_listas_mesmo_sem_ser_admin(tmp_path):
    sessao = _sessao(tmp_path, papel="USER")
    for rota in ("/protesto", "/rcpn", "/rcpj-rtd", "/livro3"):
        assert sessao["c"].get(rota).status_code == 200


# ------------------------------------------------------- lançar o ato
#
# O que estes conferem nao e "o botao existe": e que a tela SO OFERECE o que
# cabe, que o dominio recusa o que nao cabe mesmo se a tela oferecer por
# engano, e que o selo e opcional — porque o selador e maquina da rede local e
# cai, e balcao parado e pior que ato sem selo.

SELO_BOM = "AVESVD000000NARRKWVNJCRSVO21"


def _post(s, rota: str, **campos) -> str:
    c = s["c"]
    origem = rota.rsplit("/lancar", 1)[0]
    token = _token(c.get(origem).get_data(as_text=True))
    return postar_e_seguir(c, rota, {"csrf_token": token, **campos}
                           ).get_data(as_text=True)


def test_a_ficha_so_oferece_os_atos_que_cabem_na_situacao(s):
    ids = _semear(s)                      # título nasce PROTESTADO
    html = s["c"].get(f"/protesto/{ids['titulo']}").get_data(as_text=True)
    # Protestado: cabe cancelar; não cabe intimar nem protestar de novo. E,
    # desde 21/10/2026 (LH13), não cabe mais PAGAR — «protesto nao pode ser
    # pago na serventia depois de lavrar», o oficial. O nome do campo entra
    # na conferência: `value="PAGAMENTO"` sozinho acha a hipótese de
    # cancelamento do mesmo nome, e este teste passaria pelo motivo errado.
    assert 'name="ato" value="CANCELAMENTO"' in html
    assert 'name="ato" value="PAGAMENTO"' not in html
    assert 'value="INTIMACAO"' not in html
    assert 'value="PROTESTO"' not in html


def test_lanca_cancelamento_de_protesto_com_hipotese_do_catalogo(s):
    # COM O ITEM MARCADO, como o balcão lança (LT04, 20/10/2026). Sem item o
    # selo não sai e o ato se anula — e este teste passava assim mesmo, porque
    # «Ato NÃO lançado» também diz «lançado» e o título ficava CANCELADO por
    # um ato que não existiu. Desde o LT04 o título volta a PROTESTADO.
    ids = _semear(s)
    servico = _com_servico(s)
    _abrir_caixa(s)
    html = _post(s, f"/protesto/{ids['titulo']}/lancar", ato="CANCELAMENTO",
                 hipotese="PAGAMENTO",
                 fundamento="Título quitado, com prova de pagamento.",
                 cobrar=str(servico))
    assert "Cancelamento lançado" in html
    con = _con(s)
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (ids["titulo"],)).fetchone()[0] == "CANCELADO"


def test_o_dominio_recusa_o_ato_que_nao_cabe_e_a_tela_avisa(s):
    # A tela nao oferece INTIMACAO num titulo protestado — mas se o pedido
    # chegar assim mesmo, quem recusa e o dominio, com frase de balcao.
    ids = _semear(s)
    html = _post(s, f"/protesto/{ids['titulo']}/lancar", ato="INTIMACAO",
                 modo="PESSOAL")
    assert "só se intima título já apontado" in html


def test_cancelamento_sem_fundamento_proprio_e_recusado_na_tela(s):
    ids = _semear(s)
    html = _post(s, f"/protesto/{ids['titulo']}/lancar", ato="CANCELAMENTO",
                 hipotese="PAGAMENTO", fundamento="ok")
    assert "dez letras" in html


def test_sem_item_o_lancamento_e_recusado_antes_de_o_ato_existir(s):
    """Campo vazio não autoriza ato sem selo: falta o item que define o pedido.

    ATÉ 29/10/2026 ISTO SE DESCOBRIA DEPOIS: o ato era lavrado, o selo não
    saía, e ele ficava no livro marcado `cancelado=1` — foi assim com o 1353
    (28/10, o cancelamento desfeito foi à CRA) e o 9614 (21/10, PAGO sem
    pagamento). Ordem do oficial do mesmo dia: a recusa vem ANTES, o ato não
    chega a existir, e o formulário volta preenchido."""
    ids = _semear(s)
    html = _post(s, f"/protesto/{ids['titulo']}/lancar", ato="CANCELAMENTO",
                 hipotese="PAGAMENTO", fundamento="Título quitado, com prova.",
                 selo="")
    assert "Ato NÃO lançado, e nada foi gravado" in html
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo='CANCELAMENTO'").fetchone()[0] == 0
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (ids["titulo"],)).fetchone()[0] == "PROTESTADO"
    # Não houve ato a desfazer — a auditoria do desfeito não aparece.
    assert con.execute(
        "SELECT COUNT(*) FROM audit_logs "
        "WHERE action='PROTESTO_ATO_NAO_LAVRADO_SELO_FALHOU'").fetchone()[0] == 0
    # O FORMULÁRIO VOLTA PREENCHIDO: falta só marcar o item e lançar de novo.
    assert 'value="Título quitado, com prova."' in html
    assert '<option value="PAGAMENTO" selected>' in html


def test_sem_item_o_pagamento_recusado_nao_consome_o_numero_do_livro(s):
    """A recusa desfaz a transação inteira: o lugar no Livro de Pagamentos que
    o domínio reservou volta, e o pagamento lançado depois toma o número que
    o recusado teria tomado."""
    _post_novo(s, "/protesto/novo", **TITULO, **DEVEDOR)
    con = _con(s)
    titulo_id = con.execute("SELECT id FROM pt_titulos").fetchone()["id"]
    _post(s, f"/protesto/{titulo_id}/lancar", ato="APONTAMENTO")
    # PIX SÓ COM O CRÉDITO CONFERIDO (29/10/2026): a forma aqui é incidental, e
    # PIX não se lavra mais direto (`protesto_pix`) — o teste usa espécie.
    recusado = _post(s, f"/protesto/{titulo_id}/lancar", ato="PAGAMENTO",
                     forma_pagamento="ESPECIE", valor_pago="1.482,78")
    assert "Ato NÃO lançado, e nada foi gravado" in recusado
    assert 'value="1.482,78"' in recusado
    assert '<option value="ESPECIE" selected>' in recusado
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo='PAGAMENTO'").fetchone()[0] == 0
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (titulo_id,)).fetchone()[0] == "APONTADO"
    # Com o selo digitado à mão o selo não depende de item, e o ato entra.
    html = _post(s, f"/protesto/{titulo_id}/lancar", ato="PAGAMENTO",
                 forma_pagamento="ESPECIE", valor_pago="1.482,78", selo=SELO_BOM)
    assert "Pagamento lançado" in html and "NÃO lançado" not in html
    con = _con(s)
    ato = con.execute("SELECT * FROM pt_atos WHERE tipo='PAGAMENTO'").fetchone()
    assert int(ato["cancelado"] or 0) == 0
    assert ato["numero_ordem"] == 1        # o recusado não gastou o número 1


def test_a_certidao_sem_item_e_recusada_antes_de_tomar_numero(s):
    """A certidão sela sempre: sem item e sem selo digitado, ela não chega a
    existir — e o número do exercício não se gasta."""
    html = _emitir(s, nome="MARIA DAS DORES", anos="5", tipo="NEGATIVA",
                   selo="")
    assert "Certidão NÃO emitida, e nada foi gravado" in html
    assert _con(s).execute("SELECT COUNT(*) FROM pt_certidoes").fetchone()[0] == 0
    _emitir(s, nome="MARIA DAS DORES", anos="5", tipo="NEGATIVA")
    assert _con(s).execute(
        "SELECT numero FROM pt_certidoes").fetchone()["numero"] == 1


def test_o_selo_digitado_entra_amarrado_ao_ato(s):
    ids = _semear(s)
    html = _post(s, f"/protesto/{ids['titulo']}/lancar", ato="CANCELAMENTO",
                 hipotese="PAGAMENTO", fundamento="Título quitado, com prova.",
                 selo=SELO_BOM)
    assert SELO_BOM in html
    con = _con(s)
    linha = con.execute("SELECT * FROM sd_selos WHERE numero=?",
                        (SELO_BOM,)).fetchone()
    assert linha["tabela"] == "pt_atos"


def test_selo_de_outra_serventia_derruba_o_lancamento_inteiro(s):
    # A transacao volta atras: nao pode sobrar ato lavrado com selo recusado.
    ids = _semear(s)
    html = _post(s, f"/protesto/{ids['titulo']}/lancar", ato="CANCELAMENTO",
                 hipotese="PAGAMENTO", fundamento="Título quitado, com prova.",
                 selo="AVESVD999999NARRKWVNJCRSVO21")
    assert "não é desta serventia" in html
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo='CANCELAMENTO'").fetchone()[0] == 0
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (ids["titulo"],)).fetchone()[0] == "PROTESTADO"


def _com_servico(s, codigo=1, codigo_tj="17.5.1", total="53,58"):
    """Um serviço com preço no banco da sessão, para a cobrança ter o que cobrar."""
    con = _con(s)
    with con:
        con.execute("INSERT OR IGNORE INTO cx_vigencias(codigo, vigente) VALUES (1,1)")
        con.execute("""INSERT OR IGNORE INTO cx_servicos(codigo, codigo_tj, descricao)
                       VALUES (?,?, 'Serviço de teste')""", (codigo, codigo_tj))
        con.execute("""INSERT INTO cx_servico_valores(servico, vigencia,
                           emolumentos, ferc, femp, fadep, ferrfis, total)
                       VALUES (?,1,?, '0,00','0,00','0,00','0,00', ?)""",
                    (codigo, total, total))
    con.close()
    return codigo


def _abrir_caixa(s) -> int:
    """O caixa do operador, aberto — sem ele não se cobra."""
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO cx_caixas(data, operador_nome, aberto_em, situacao)
               VALUES ('2026-08-24','MARIO EXEMPLO DOS SANTOS',
                       '2026-08-24T08:00:00','ABERTO')""")
        cid = con.execute("SELECT id FROM cx_caixas").fetchone()[0]
    con.close()
    return cid


def test_lancar_ato_marcando_item_cobra_no_caixa(s):
    # Fecha o ciclo: o ato lavra E entra no caixa, na mesma transação.
    ids = _semear(s)
    servico = _com_servico(s)
    caixa_id = _abrir_caixa(s)
    html = _post(s, f"/protesto/{ids['titulo']}/lancar", ato="CANCELAMENTO",
                 hipotese="PAGAMENTO", fundamento="Título quitado, com prova.",
                 cobrar=str(servico), pagador="MARIA")
    assert "Lançado no caixa" in html
    con = _con(s)
    linha = con.execute(
        "SELECT * FROM cx_lancamentos WHERE origem='ATO'").fetchone()
    assert linha["valor"] == "53,58"
    assert linha["pagador"] == "MARIA"
    assert linha["natureza"] == "RECEBIMENTO"
    # E CAI NO CAIXA DO OPERADOR: lançamento sem caixa não aparece na
    # conferência do dia, e a diferença apareceria no fechamento sem ter de
    # onde vir.
    assert linha["caixa_id"] == caixa_id


def test_sem_caixa_aberto_nao_se_cobra_e_o_ato_nao_entra(s):
    # É a regra do balcão de verdade: não se recebe com a gaveta fechada. E a
    # transação volta atrás inteira — não pode sobrar ato lavrado.
    ids = _semear(s)
    servico = _com_servico(s)
    html = _post(s, f"/protesto/{ids['titulo']}/lancar", ato="CANCELAMENTO",
                 hipotese="PAGAMENTO", fundamento="Título quitado, com prova.",
                 cobrar=str(servico))
    assert "não tem caixa aberto" in html
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo='CANCELAMENTO'").fetchone()[0] == 0
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (ids["titulo"],)).fetchone()[0] == "PROTESTADO"


def test_a_cobranca_amarra_ao_protocolo_quando_escolhido(s):
    ids = _semear(s)
    servico = _com_servico(s)
    _abrir_caixa(s)
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO cx_protocolos(numero, data_abertura, atribuicao,
                   interessado, situacao, criado_em)
               VALUES ('11534', '2026-08-24','PROTESTO','CICERO','ABERTO',
                       '2026-08-24T09:00:00')""")
        prot = con.execute("SELECT id FROM cx_protocolos").fetchone()[0]
    con.close()
    _post(s, f"/protesto/{ids['titulo']}/lancar", ato="CANCELAMENTO",
          hipotese="PAGAMENTO", fundamento="Título quitado, com prova.",
          cobrar=str(servico), protocolo_id=str(prot))
    con = _con(s)
    assert con.execute(
        "SELECT protocolo_id FROM cx_lancamentos WHERE origem='ATO'"
    ).fetchone()[0] == prot


def test_a_ficha_mostra_o_cobrado_e_oferece_o_recibo(s):
    # O recibo NÃO se emite aqui: a ficha aponta para o Caixa, que já tem
    # numeração por exercício, teor congelado e hash.
    ids = _semear(s)
    servico = _com_servico(s)
    _abrir_caixa(s)
    _post(s, f"/protesto/{ids['titulo']}/lancar", ato="CANCELAMENTO",
          hipotese="PAGAMENTO", fundamento="Título quitado, com prova.",
          cobrar=str(servico))
    texto = " ".join(s["c"].get(f"/protesto/{ids['titulo']}")
                     .get_data(as_text=True).split())
    assert "53,58" in texto
    assert "emitir recibo" in texto
    assert "/caixa/recibo/" in texto


@pytest.mark.parametrize("rota,chave", [
    ("/rcpn/{}", "assento"),
    ("/rcpj-rtd/{}", "registro"),
    ("/livro3/{}", "livro3"),
])
def test_as_outras_tres_fichas_tambem_cobram(s, rota, chave):
    # A macro é a mesma nas quatro; o que faltava era passar os protocolos e a
    # coluna do cobrado. Consistência aqui não é estética: é o operador achar
    # a mesma coisa no mesmo lugar em qualquer atribuição.
    ids = _semear(s)
    _com_servico(s, codigo_tj="14.5.1")     # item que o RCPN/RI usa
    _abrir_caixa(s)
    texto = " ".join(s["c"].get(rota.format(ids[chave]))
                     .get_data(as_text=True).split())
    assert "Cobrado" in texto                # a coluna
    assert "não cobrado" in texto            # e o aviso de que ninguém cobrou


def test_ato_nao_cobrado_aparece_como_nao_cobrado(s):
    # Ato lavrado e não cobrado é receita que some sem ninguém ver — a ficha
    # diz, em vez de deixar em branco.
    ids = _semear(s)
    texto = " ".join(s["c"].get(f"/protesto/{ids['titulo']}")
                     .get_data(as_text=True).split())
    assert "não cobrado" in texto


def test_sem_caixa_a_ficha_avisa_e_desabilita_a_marcacao(s):
    ids = _semear(s)
    _com_servico(s)
    texto = " ".join(s["c"].get(f"/protesto/{ids['titulo']}")
                     .get_data(as_text=True).split())
    assert "Você não tem caixa aberto" in texto
    assert "disabled" in texto


def test_nada_marcado_nada_lancado(s):
    # A cobrança é ESCOLHIDA: a receita medida é média, e quem lavra decide o
    # que cabe no caso.
    ids = _semear(s)
    _com_servico(s)
    _post(s, f"/protesto/{ids['titulo']}/lancar", ato="CANCELAMENTO",
          hipotese="PAGAMENTO", fundamento="Título quitado, com prova.")
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) FROM cx_lancamentos WHERE origem='ATO'").fetchone()[0] == 0


def test_cobranca_recusada_derruba_o_lancamento_inteiro(s):
    # Mesma regra do selo: não pode sobrar ato lavrado com cobrança que falhou.
    ids = _semear(s)
    _abrir_caixa(s)
    html = _post(s, f"/protesto/{ids['titulo']}/lancar", ato="CANCELAMENTO",
                 hipotese="PAGAMENTO", fundamento="Título quitado, com prova.",
                 cobrar="999999")          # serviço que não existe na tabela
    assert "não achei" in html.lower() or "tabela" in html.lower()
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo='CANCELAMENTO'").fetchone()[0] == 0
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (ids["titulo"],)).fetchone()[0] == "PROTESTADO"


def test_a_ficha_oferece_marcar_o_que_cobrar(s):
    ids = _semear(s)
    _com_servico(s)
    _abrir_caixa(s)
    html = s["c"].get(f"/protesto/{ids['titulo']}").get_data(as_text=True)
    # O HTML quebra linha onde o template quebrou; o navegador junta, o teste
    # tem de juntar também — senão ele falha por formatação e não por defeito.
    texto = " ".join(html.split())
    assert "Cobrar no caixa" in texto
    assert "Nada marcado, nada lançado" in texto
    assert 'name="cobrar"' in texto            # e há o que marcar


def test_averba_no_assento_do_rcpn(s):
    ids = _semear(s)
    html = _post(s, f"/rcpn/{ids['assento']}/lancar", tipo="AVERBACAO",
                 teor="Averbação de casamento, conforme certidão.",
                 selo="AVESVD000000NARRKWVNJCRSVO21")
    assert "lançada" in html
    con = _con(s)
    assert con.execute(
        """SELECT COUNT(*) FROM rc_atos WHERE assento_id=? AND tipo='AVERBACAO'""",
        (ids["assento"],)).fetchone()[0] == 2      # a semeada + esta


def test_a_averbacao_tem_lista_e_tela_proprias(s):
    ids = _semear(s)
    lista = s["c"].get("/rcpn/averbacoes").get_data(as_text=True)
    assert "Averbações — localizar assento" in lista
    assert f'/rcpn/{ids["assento"]}/averbar' in lista

    html = s["c"].get(
        f'/rcpn/{ids["assento"]}/averbar').get_data(as_text=True)
    assert 'name="tipo" value="AVERBACAO"' in html
    assert 'name="teor"' in html
    assert 'name="data_fato"' not in html
    assert 'name="dnv"' not in html
    assert 'value="ANOTACAO"' not in html
    assert 'value="RETIFICACAO"' not in html
    assert '<select' in html
    assert 'name="natureza_averbacao"' in html
    assert 'Inclusão de CPF (art. 347)' in html
    assert 'Alteração / inclusão de prenome ou sobrenome' in html


def test_a_ficha_leva_a_tres_lancamentos_sem_misturar_formularios(s):
    ids = _semear(s)
    html = s["c"].get(
        f'/rcpn/{ids["assento"]}').get_data(as_text=True)
    assert f'/rcpn/{ids["assento"]}/averbar' in html
    assert f'/rcpn/{ids["assento"]}/anotar' in html
    assert f'/rcpn/{ids["assento"]}/retificar' in html
    assert 'name="tipo"' not in html


def test_a_retificacao_do_rcpn_exige_fundamento_na_tela(s):
    ids = _semear(s)
    html = _post(s, f"/rcpn/{ids['assento']}/lancar", tipo="RETIFICACAO",
                 teor="Corrige a grafia do nome da genitora.", fundamento="")
    assert "exige o fundamento" in html


def test_o_lancamento_do_rcpn_nao_ocupa_folha_nova(s):
    # Se ocupasse, o Livro A encheria em um ano.
    ids = _semear(s)
    _post(s, f"/rcpn/{ids['assento']}/lancar", tipo="ANOTACAO",
          teor="Anotação remissiva ao Livro B, fl. 40.")
    con = _con(s)
    ato = con.execute(
        """SELECT * FROM rc_atos WHERE assento_id=? AND tipo='ANOTACAO'
            ORDER BY id DESC LIMIT 1""", (ids["assento"],)).fetchone()
    assert ato["livro_id"] is None and ato["numero_ordem"] is None


def test_averba_no_livro_3_e_a_numeracao_do_ato_e_continua(s):
    ids = _semear(s)
    html = _post(s, f"/livro3/{ids['livro3']}/lancar", tipo="AVERBACAO",
                 teor="Averbação de prorrogação do vencimento.")
    assert "AV-2" in html


def test_cancelar_no_livro_3_e_uma_averbacao_e_o_registro_fica(s):
    ids = _semear(s)
    _post(s, f"/livro3/{ids['livro3']}/lancar", tipo="CANCELAMENTO",
          motivo="Liquidação integral da cédula.")
    con = _con(s)
    assert con.execute("SELECT situacao FROM ra_registros WHERE id=?",
                       (ids["livro3"],)).fetchone()[0] == "CANCELADO"
    # o registro continua na ficha
    assert s["c"].get(f"/livro3/{ids['livro3']}").status_code == 200


def test_averba_no_rcpj_rtd_e_ocupa_folha_nova(s):
    # Aqui e o oposto do RCPN: cada ato e escritura a parte.
    ids = _semear(s)
    html = _post(s, f"/rcpj-rtd/{ids['registro']}/lancar", tipo="AVERBACAO",
                 teor="Averbação de alteração do endereço da sede.",
                 selo="AVESVD000000NARRKWVNJCRSVO21")
    assert "Assim vai sair na tira" in html
    con = _con(s)
    ato = con.execute(
        """SELECT * FROM rg_atos WHERE registro_id=? AND tipo='AVERBACAO'""",
        (ids["registro"],)).fetchone()
    assert ato["numero_ordem"] is not None
    assert ato["folha"] is not None


def test_tipo_de_lancamento_desconhecido_e_recusado(s):
    ids = _semear(s)
    html = _post(s, f"/rcpn/{ids['assento']}/lancar", tipo="INVENTADO",
                 teor="Qualquer coisa aqui.")
    assert "desconhecido" in html


def test_a_ficha_do_cancelado_nao_oferece_mais_lancamento(s):
    ids = _semear(s)
    _post(s, f"/livro3/{ids['livro3']}/lancar", tipo="CANCELAMENTO",
          motivo="Liquidação integral da cédula.")
    html = s["c"].get(f"/livro3/{ids['livro3']}").get_data(as_text=True)
    assert 'value="AVERBACAO"' not in html


def test_a_carga_roda_de_verdade_e_mostra_os_numeros(s, tmp_path):
    # Um acervo de mentira, com as colunas que a carga le. O que se confere e
    # que a tela mostra o que a carga fez — e que ela distingue rejeitado de
    # avisado, porque somar os dois faz o numero mentir.
    import acervo_carga as AC
    destino = Path(s["app"].config["DATA_DIR"]) / AC.NOME_ACERVO
    falso = sqlite3.connect(destino)
    falso.executescript("""
        CREATE TABLE tbAvisoProtesto (
            intChave REAL, intNumero TEXT, strEspecie TEXT,
            strNossoNumero TEXT, dtmEmissao TEXT, dtmVencimento TEXT,
            curValorRealTitulo REAL, curValor REAL, strPracaPgto TEXT,
            strEndosso TEXT, intMotivoProtesto TEXT, canal_entrada TEXT,
            snCanceladoProtesto INTEGER, strTipoPG TEXT, snProtestado INTEGER,
            intNumeroApontamento REAL, intFolhaApontamento REAL,
            intLivroApontamento REAL, strSelo_Apontamento TEXT,
            dtmE_Cartorio TEXT, intProtestoLivro REAL, intProtestoFolha REAL,
            dtmOcorrencia TEXT, intCodigoOcorrencia TEXT,
            dtmCancelaProtesto TEXT, strSelo_Cancelamento TEXT,
            memObsCancelamento TEXT);
        INSERT INTO tbAvisoProtesto(intChave, intNumero, strEspecie, curValor,
            curValorRealTitulo, snProtestado, intNumeroApontamento,
            intFolhaApontamento, canal_entrada, intProtestoLivro,
            intProtestoFolha, dtmOcorrencia, intCodigoOcorrencia)
          VALUES (1,'99999/1','DMI',500.0,500.0,1,7,1,'CRA',
                  4,10,'2024-03-10 00:00:00','C');
    """)
    falso.commit()
    falso.close()

    c = s["c"]
    token = _token(c.get("/atribuicoes/importar").get_data(as_text=True))
    # A tela hoje atualiza o snapshot com o MSSQL antes da carga. Este teste
    # mede o importador contra o arquivo mínimo acima; deixar a sincronização
    # real rodar substituiria a bancada pelo acervo da serventia.
    from unittest.mock import patch
    import acervo_eo_vivo as EO_VIVO
    with patch.object(EO_VIVO, "atualizar_protesto_ao_vivo"):
        html = c.post("/atribuicoes/importar",
                      data={"csrf_token": token, "quais": ["protesto"]},
                      follow_redirects=True).get_data(as_text=True)
    assert "Carga concluída" in html
    assert "Rejeitado não entrou" in html      # os dois contadores, separados
    linhas = [tuple(x) for x in _con(s).execute(
        "SELECT numero_titulo, situacao, origem FROM pt_titulos").fetchall()]
    assert any(x[0] == "99999/1" for x in linhas), linhas
    # O titulo da carga esta PROTESTADO, e a lista abre nos pendentes desde
    # 14/10/2026 — a vista «todos» e a que o mostra.
    pagina = c.get("/protesto?vista=todos").get_data(as_text=True)
    titulos = re.findall(r"<title>(.*?)</title>|<h1[^>]*>(.*?)</h1>",
                         pagina, re.S | re.I)
    assert "99999/1" in pagina, f"banco={linhas!r}; pagina={titulos!r}"


# ------------------------------------------------- abrir registro NOVO
#
# Ate 25/08/2026 as quatro telas so lancavam ato em registro que JA EXISTIA:
# titulo, assento e registro novos so entravam pela carga do acervo. Uma
# serventia que nao consegue abrir registro novo nao atende ninguem.

DEVEDOR = {
    "devedor_nome": "JOSÉ DA SILVA",
    "devedor_documento_tipo": "CPF",
    "devedor_documento": "04785512388",
    "devedor_endereco": "RUA GRANDE, 10",
    "devedor_bairro": "CENTRO",
    "devedor_cidade": "Cidade Exemplo",
    "devedor_uf": "MA",
}
TITULO = {
    "especie": "DMI", "numero_titulo": "9911/1",
    "data_emissao": "2026-08-01", "data_vencimento": "2026-08-20",
    "valor": "1.200,00", "saldo": "1.310,45",
    "praca_protesto": "CIDADE EXEMPLO", "motivo_protesto": "1",
}


def _post_novo(s, rota: str, **campos) -> str:
    c = s["c"]
    token = _token(c.get(rota).get_data(as_text=True))
    if rota.startswith("/rcpn/novo"):
        con = _con(s)
        codigo = "9999999"
        with con:
            con.execute(
                """INSERT INTO pp_remessas(fornecedor, codigo_de, codigo_ate,
                       quantas, recebida_em)
                   VALUES ('TESTE', ?, ?, 1, '2026-08-25T00:00:00')""",
                (codigo, codigo))
            rid = con.execute(
                "SELECT id FROM pp_remessas ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
            con.execute(
                """INSERT INTO pp_folhas(codigo, remessa_id, situacao, criada_em)
                   VALUES (?,?,'EM BRANCO','2026-08-25T00:00:00')""",
                (codigo, rid))
        con.close()
        campos.setdefault("acao", "lavrar")
        campos.setdefault("folha_seguranca", codigo)
    if rota.startswith("/rcpj-rtd/novo"):
        campos.setdefault("selo", "AVESVD000000NARRKWVNJCRSVO21")
    return postar_e_seguir(c, rota, {"csrf_token": token, **campos}
                           ).get_data(as_text=True)


def test_o_lancamento_recusado_volta_com_o_teor(s):
    """«Corrija o problema e lance de novo» levava à ficha, e o teor se perdia (31/10/2026)."""
    assento = _semear(s)["assento"]
    c = s["c"]
    token = _token(c.get(f"/rcpn/{assento}/retificar").get_data(as_text=True))
    # retificação sem fundamento: o domínio recusa, e a tela volta com o teor digitado
    html = postar_e_seguir(c, f"/rcpn/{assento}/lancar",
                           {"csrf_token": token, "tipo": "RETIFICACAO", "teor": "O teor inteiro da retificação digitada.", "fundamento": ""}
                           ).get_data(as_text=True)
    assert "A retificação exige o fundamento" in html
    assert "O teor inteiro da retificação digitada.</textarea>" in html


@pytest.mark.parametrize("rota", ["/protesto/novo", "/rcpn/novo",
                                  "/rcpj-rtd/novo", "/livro3/novo"])
def test_as_quatro_telas_de_registro_novo_abrem(s, rota):
    assert s["c"].get(rota).status_code == 200


@pytest.mark.parametrize("lista,diz", [
    ("/protesto", "Título novo"), ("/rcpn", "Assento novo"),
    ("/rcpj-rtd", "Registro novo"), ("/livro3", "Registro novo"),
])
def test_a_lista_leva_para_abrir_registro_novo(s, lista, diz):
    assert diz in s["c"].get(lista).get_data(as_text=True)


def test_titulo_novo_nasce_recebido_com_o_devedor_junto(s):
    html = _post_novo(s, "/protesto/novo", **TITULO, **DEVEDOR)
    assert "cadastrado" in html
    con = _con(s)
    t = con.execute("SELECT * FROM pt_titulos WHERE numero_titulo='9911/1'").fetchone()
    assert t["situacao"] == "RECEBIDO"     # cadastrar nao e apontar
    assert t["origem"] == "MANUAL"
    # O SALDO NAO E COPIADO DO VALOR: sao dois numeros, e o saldo traz juros.
    assert t["valor_centavos"] == 120000
    assert t["saldo_centavos"] == 131045
    d = con.execute("SELECT * FROM pt_devedores WHERE titulo_id=?",
                    (t["id"],)).fetchone()
    assert d["nome"] == "JOSÉ DA SILVA"
    assert d["documento_tipo"] == "CPF"


def test_o_titulo_cadastrado_no_balcao_pode_ser_apontado_pela_ficha(s):
    # O APONTAMENTO E O PRIMEIRO ATO DA VIDA DO TITULO — art. 3o da Lei
    # 9.492/1997 —, e ate 25/08/2026 nenhuma tela o oferecia: titulo
    # cadastrado no balcao nascia RECEBIDO e nao tinha por onde andar.
    _post_novo(s, "/protesto/novo", **TITULO, **DEVEDOR)
    con = _con(s)
    titulo_id = con.execute("SELECT id FROM pt_titulos").fetchone()["id"]
    ficha = s["c"].get(f"/protesto/{titulo_id}").get_data(as_text=True)
    assert 'value="APONTAMENTO"' in ficha

    # COM O ITEM MARCADO, como o balcão lança (LT04, 20/10/2026). Desde
    # 21/10/2026 o apontamento NÃO pede selo (ordem do oficial, LH06): a
    # cobrança marcada entra no caixa, e o ato fica de pé. «NÃO lançado»
    # também contém «lançado» — foi assim que este teste passou com o
    # apontamento saindo CANCELADO (900001/1).
    servico = _com_servico(s, codigo_tj="17.1")
    _abrir_caixa(s)
    html = _post(s, f"/protesto/{titulo_id}/lancar", ato="APONTAMENTO",
                 cobrar=str(servico))
    assert "Apontamento lançado" in html and "NÃO lançado" not in html
    con = _con(s)
    ato = con.execute(
        "SELECT * FROM pt_atos WHERE tipo='APONTAMENTO'").fetchone()
    assert int(ato["cancelado"] or 0) == 0   # apontamento não tem selo próprio
    assert ato["selo"] is None
    assert ato["numero_ordem"] == 1        # banco do teste nasce vazio
    assert ato["livro_id"] is not None     # e o lugar sai do nucleo
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (titulo_id,)).fetchone()[0] == "APONTADO"
    # E nao se aponta duas vezes: um titulo tem um apontamento, nao dois.
    de_novo = _post(s, f"/protesto/{titulo_id}/lancar", ato="APONTAMENTO")
    assert "não se aponta de novo" in de_novo


def test_o_apontamento_sem_item_nao_pede_selo_e_fica_lancado(s):
    """P-B, 21/10/2026 — ordem do oficial. Dos 1.409 apontamentos do E-Ofício,
    1.161 não têm selo; pedir selo aqui fazia o 900001/1 sair lavrado no livro
    e marcado cancelado, com o título já APONTADO."""
    _post_novo(s, "/protesto/novo", **TITULO, **DEVEDOR)
    con = _con(s)
    titulo_id = con.execute("SELECT id FROM pt_titulos").fetchone()["id"]
    html = _post(s, f"/protesto/{titulo_id}/lancar", ato="APONTAMENTO")
    assert "Apontamento lançado" in html and "NÃO lançado" not in html
    assert "SEM SELO" not in html
    con = _con(s)
    ato = con.execute(
        "SELECT * FROM pt_atos WHERE tipo='APONTAMENTO'").fetchone()
    assert int(ato["cancelado"] or 0) == 0 and ato["motivo_cancelamento"] is None
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (titulo_id,)).fetchone()[0] == "APONTADO"
    assert con.execute(
        "SELECT COUNT(*) FROM sd_selos WHERE tabela='pt_atos' AND ato_id=?",
        (ato["id"],)).fetchone()[0] == 0
    assert con.execute(
        "SELECT COUNT(*) FROM audit_logs "
        "WHERE action='PROTESTO_ATO_NAO_LAVRADO_SELO_FALHOU'").fetchone()[0] == 0


def _auditoria_da_falha(s) -> dict:
    con = _con(s)
    linha = con.execute(
        "SELECT details FROM audit_logs "
        "WHERE action='PROTESTO_ATO_NAO_LAVRADO_SELO_FALHOU' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert linha, "a falha do selo não foi auditada"
    import json
    return json.loads(linha["details"])


def _o_selo_falha_depois_de_lavrar(monkeypatch, antes_de_falhar=None):
    """A falha que NÃO se sabe antes — a do pedido ao aparelho. Desde
    29/10/2026 a falta de item é recusada antes de lavrar
    (`protesto_selo_previo`), e o caminho do desfeito só se exercita com o
    item marcado e o selo falhando depois."""
    import ato_selado as AS

    def falha(**_kw):
        if antes_de_falhar:
            antes_de_falhar()
        raise AS.AtoError("o aparelho não respondeu (ensaio).")

    monkeypatch.setattr(AS, "envelope_do_protesto", falha)


def test_ato_cancelado_por_falta_de_selo_devolve_a_situacao_do_titulo(s, monkeypatch):
    """O caminho do erro (P-B, 900001/1): o ato sai cancelado e o título volta
    à situação de antes, com `situacao_restaurada` na auditoria. Com o item
    marcado — sem ele, a recusa vem antes (29/10/2026) — e o selo falhando
    depois de o ato estar lavrado."""
    titulo_id = _titulo_apontado(s)
    servico = _com_servico(s, codigo_tj="17.4")
    _abrir_caixa(s)
    _o_selo_falha_depois_de_lavrar(monkeypatch)
    html = _post(s, f"/protesto/{titulo_id}/lancar", ato="DESISTENCIA",
                 motivo="Credor desistiu antes do protesto", cobrar=str(servico))
    assert "NÃO lançado" in html
    assert "ato a refazer" in html
    con = _con(s)
    ato = con.execute("SELECT * FROM pt_atos WHERE tipo='DESISTENCIA'").fetchone()
    assert int(ato["cancelado"]) == 1
    assert "Selo não emitido" in ato["motivo_cancelamento"]
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (titulo_id,)).fetchone()[0] == "APONTADO"
    detalhe = _auditoria_da_falha(s)
    assert detalhe["ato"] == "DESISTENCIA"
    assert detalhe["situacao_restaurada"] == "APONTADO"
    # E a ficha deixa lançar de novo — o que o 900001/1 não deixava. E A
    # FALHA VIROU OBRIGAÇÃO (29/10/2026): o ato a refazer, na ficha e no painel.
    ficha = " ".join(s["c"].get(f"/protesto/{titulo_id}").get_data(as_text=True).split())
    assert 'value="DESISTENCIA"' in ficha
    assert "data-pendencias-do-selo" in ficha
    assert "Refazer a desistência" in ficha
    assert 'href="#lancar-DESISTENCIA"' in ficha
    painel = s["c"].get("/protesto").get_data(as_text=True)
    assert "data-pendencias-do-selo" in painel
    assert f'href="/protesto/{titulo_id}"' in painel


def _titulo_apontado(s) -> int:
    """O título do balcão, apontado: o protocolo dele nasce aqui, e o selo do
    Protesto não sai sem ele."""
    _post_novo(s, "/protesto/novo", **TITULO, **DEVEDOR)
    con = _con(s)
    titulo_id = con.execute("SELECT id FROM pt_titulos").fetchone()["id"]
    con.close()
    html = _post(s, f"/protesto/{titulo_id}/lancar", ato="APONTAMENTO")
    assert "Apontamento lançado" in html
    return titulo_id


def test_a_volta_da_situacao_nao_passa_por_cima_de_outro_balcao(s, monkeypatch):
    """Entre o ato e a volta há o pedido do selo, fora da transação. Se outro
    balcão mexeu no título nesse meio-tempo, a volta não o desfaz — e a
    auditoria diz que não voltou (None), em vez de afirmar uma volta que não
    houve."""
    titulo_id = _titulo_apontado(s)
    servico = _com_servico(s, codigo_tj="17.4")
    _abrir_caixa(s)

    def outro_balcao_mexe_antes():
        de_fora = _con(s)
        with de_fora:
            de_fora.execute("UPDATE pt_titulos SET situacao='INTIMADO' WHERE id=?",
                            (titulo_id,))
        de_fora.close()

    _o_selo_falha_depois_de_lavrar(monkeypatch, outro_balcao_mexe_antes)
    html = _post(s, f"/protesto/{titulo_id}/lancar", ato="DESISTENCIA",
                 motivo="Credor desistiu antes do protesto", cobrar=str(servico))
    assert "NÃO lançado" in html
    con = _con(s)
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (titulo_id,)).fetchone()[0] == "INTIMADO"
    assert _auditoria_da_falha(s)["situacao_restaurada"] is None


def test_a_ficha_e_a_lista_mostram_a_situacao_sem_o_ato_que_a_sustente(s):
    """O 9614 da produção (29/10/2026): PAGO, com o pagamento desfeito pelo
    selo. A conferência só MOSTRA — na ficha e na lista —, e não corrige."""
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO pt_titulos(especie, numero_titulo, protocolo,
                   valor_centavos, saldo_centavos, situacao, origem,
                   origem_chave, criado_em)
               VALUES ('DMI','9614/T','2610210001',10000,10000,'PAGO','CRA',
                       't:9614','2026-10-21T08:00:00')""")
        tid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem,
                   cancelado, motivo_cancelamento, criado_em)
               VALUES (?,'PAGAMENTO','2026-10-21','MANUAL',1,
                       'Selo não emitido: sem item.','2026-10-21T08:19:38')""",
            (tid,))
    con.close()
    ficha = " ".join(s["c"].get(f"/protesto/{tid}").get_data(as_text=True).split())
    assert "data-situacao-sem-ato" in ficha
    assert "A situação PAGO não tem o ato que a sustente" in ficha
    assert "foi desfeito" in ficha and "21/10/2026" in ficha
    lista = s["c"].get("/protesto").get_data(as_text=True)
    assert "data-situacao-sem-ato" in lista
    assert f'href="/protesto/{tid}"' in lista
    # SÓ MOSTRA: a situação continua a mesma depois de olhar.
    assert _con(s).execute("SELECT situacao FROM pt_titulos WHERE id=?",
                           (tid,)).fetchone()[0] == "PAGO"


def test_titulo_em_ordem_nao_aparece_na_conferencia(s):
    """Alarme que soa sempre é alarme que ninguém ouve: a lista sem nada fora
    do lugar não mostra o quadro."""
    html = s["c"].get("/protesto").get_data(as_text=True)
    assert "data-situacao-sem-ato" not in html
    assert "data-pendencias-do-selo" not in html


AFIRMACAO_BOA = ("Afirmo, sob minha responsabilidade, que este item serve "
                 "para este ato, conforme a tabela do Tribunal.")


def test_o_4127_e_recusado_antes_e_a_afirmacao_vence(s):
    """O ato 4127 (título 1353, 29/10/2026 às 08h43): o cancelamento saiu com
    a faixa 17.4.5, que o aparelho não conhece, e foi desfeito. Agora a ficha
    recusa ANTES, diz quais itens servem e abre a afirmação expressa; com ela,
    o ato entra, e a afirmação fica no ato e na auditoria."""
    ids = _semear(s)
    servico = _com_servico(s, codigo=2, codigo_tj="17.4.5")
    _abrir_caixa(s)
    campos = dict(ato="CANCELAMENTO", hipotese="PAGAMENTO",
                  fundamento="Título quitado, com prova.", cobrar=str(servico))
    html = _post(s, f"/protesto/{ids['titulo']}/lancar", **campos)
    texto = " ".join(html.split())
    assert "Ato NÃO lançado, e nada foi gravado" in texto
    assert "17.4.5" in texto and "17.2" in texto       # o que serve
    assert "data-afirmacao-expressa" in html           # a caixa se abriu
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo='CANCELAMENTO'").fetchone()[0] == 0
    assert con.execute(
        "SELECT COUNT(*) FROM cx_lancamentos WHERE origem='ATO'").fetchone()[0] == 0
    # A AFIRMAÇÃO PELA METADE CONTINUA SENDO A TRAVA.
    meia = _post(s, f"/protesto/{ids['titulo']}/lancar", afirmo="1",
                 afirmacao="Afirmo que serve.", **campos)
    assert "afirmação expressa está incompleta" in meia
    # COM ELA, o ato entra.
    feito = _post(s, f"/protesto/{ids['titulo']}/lancar", afirmo="1",
                  afirmacao=AFIRMACAO_BOA, **campos)
    assert "Cancelamento lançado" in feito
    con = _con(s)
    ato = con.execute("SELECT * FROM pt_atos WHERE tipo='CANCELAMENTO'").fetchone()
    import json
    [afirmada] = json.loads(ato["detalhe_json"])["afirmacoes_expressas"]
    assert afirmada["regra"] == "SELO_ITEM_FORA_DO_CAMINHO"
    assert afirmada["afirmacao"] == AFIRMACAO_BOA
    linha = con.execute(
        "SELECT entity_type, entity_id, details FROM audit_logs "
        "WHERE action='AFIRMACAO_EXPRESSA' ORDER BY id DESC LIMIT 1").fetchone()
    assert (linha["entity_type"], int(linha["entity_id"])) == ("pt_atos", ato["id"])
    detalhes = json.loads(linha["details"])
    assert set(detalhes) >= {"regra", "afirmacao", "o_que_faltava"}
    assert "17.4.5" in detalhes["o_que_faltava"]


def test_a_faixa_do_pagamento_sai_pelo_item_do_tribunal(s):
    """O pagamento pago pela faixa 17.4.5 sela pelo 17.4 — o que o E-Ofício
    mandou em 141 selos de pagamento, e o que o aparelho conhece."""
    titulo_id = _titulo_apontado(s)
    servico = _com_servico(s, codigo=2, codigo_tj="17.4.5")
    _abrir_caixa(s)
    # A forma é incidental (PIX só com o crédito conferido, 29/10/2026).
    html = _post(s, f"/protesto/{titulo_id}/lancar", ato="PAGAMENTO",
                 forma_pagamento="ESPECIE", valor_pago="1.310,45", cobrar=str(servico))
    assert "Pagamento lançado" in html and "NÃO lançado" not in html
    con = _con(s)
    ato = con.execute("SELECT id FROM pt_atos WHERE tipo='PAGAMENTO'").fetchone()
    referencias = [r[0] for r in con.execute(
        "SELECT referencia FROM sd_selos WHERE tabela='pt_atos' AND ato_id=?",
        (ato["id"],)).fetchall()]
    assert referencias and all(":17.4:" in r for r in referencias), referencias


def test_o_titulo_sem_protocolo_e_recusado_antes(s):
    """O protocolo do título nasce no apontamento, e o envelope do selo do
    Protesto o exige: a desistência do título ainda RECEBIDO não sai."""
    _post_novo(s, "/protesto/novo", **TITULO, **DEVEDOR)
    con = _con(s)
    titulo_id = con.execute("SELECT id FROM pt_titulos").fetchone()["id"]
    servico = _com_servico(s, codigo_tj="17.4")
    _abrir_caixa(s)
    html = _post(s, f"/protesto/{titulo_id}/lancar", ato="DESISTENCIA",
                 motivo="Credor desistiu antes do protesto", cobrar=str(servico))
    assert "aponte o título antes" in " ".join(html.split())
    assert 'value="Credor desistiu antes do protesto"' in html
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo='DESISTENCIA'").fetchone()[0] == 0


def test_o_item_do_protocolo_nao_pago_e_recusado_antes(s):
    """A trava do selo pago (3.7.0): com o protocolo escolhido e o item dele
    não quitado, sem depósito prévio, o selo não sai — e a ficha diz antes."""
    s["db"].set_settings({"selo_trava_caixa": "LIGADA"})
    ids = _semear(s)
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO cx_protocolos(numero, data_abertura, atribuicao,
                   interessado, situacao, criado_em)
               VALUES ('2026.10.900', '2026-10-29','PROTESTO','CICERO','ABERTO',
                       '2026-10-29T09:00:00')""")
        prot = con.execute("SELECT id FROM cx_protocolos").fetchone()[0]
        con.execute(
            """INSERT INTO cx_protocolo_atos(protocolo_id, descricao, codigo_ato,
                   quantidade, valor_total)
               VALUES (?, 'Cancelamento', '17.3', 1, '40,00')""", (prot,))
    con.close()
    html = _post(s, f"/protesto/{ids['titulo']}/lancar", ato="CANCELAMENTO",
                 hipotese="PAGAMENTO", fundamento="Título quitado, com prova.",
                 protocolo_id=str(prot))
    texto = " ".join(html.split())
    assert "o selo pago só sai com o item pago" in texto
    assert "2026.10.900" in texto and "17.3" in texto
    assert _con(s).execute(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo='CANCELAMENTO'").fetchone()[0] == 0


def test_a_correcao_de_oficio_pela_ficha(s):
    """O 9614: PAGO com o pagamento desfeito. A ficha mostra o caminho — a
    correção de ofício, com afirmação expressa — e ela volta o título à
    situação que os atos válidos sustentam, deixando o rastro."""
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO pt_titulos(especie, numero_titulo, protocolo,
                   valor_centavos, saldo_centavos, situacao, origem,
                   origem_chave, criado_em)
               VALUES ('DMI','9614/T','2610210001',10000,10000,'PAGO','CRA',
                       't:9614','2026-10-21T08:00:00')""")
        tid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem, criado_em)
               VALUES (?,'APONTAMENTO','2026-10-13','EOFICIO',
                       '2026-10-14T08:13:17')""", (tid,))
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem,
                   cancelado, motivo_cancelamento, criado_em, criado_por)
               VALUES (?,'PAGAMENTO','2026-10-21','MANUAL',1,
                       'Selo não emitido: sem item.','2026-10-21T08:19:38',
                       'MARIO EXEMPLO DOS SANTOS')""", (tid,))
    con.close()
    bruto = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    ficha = " ".join(bruto.split())
    assert "Propor a correção de ofício" in ficha
    assert "os atos válidos sustentam a situação <strong>APONTADO</strong>" in ficha
    assert "Refazer o pagamento" in ficha                 # e o ato a refazer
    rota = f"/protesto/{tid}/situacao/corrigir"

    def corrigir(**campos) -> str:
        return postar_e_seguir(s["c"], rota, {"csrf_token": _token(bruto), **campos}
                               ).get_data(as_text=True)

    sem = corrigir(motivo="")
    assert "Escreva o motivo" in sem
    # O BOTÃO SÓ PROPÕE (decisão do oficial, 30/10/2026): a situação não muda.
    feito = corrigir(motivo=("O pagamento não aconteceu: o selo falhou e o título "
                             "não voltou à situação de antes."))
    assert "a situação não mudou" in feito
    con = _con(s)
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "PAGO"
    proposta = con.execute(
        "SELECT id, tipo, situacao FROM correcoes_de_oficio ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert (proposta[1], proposta[2]) == ("PT_SITUACAO_SUSTENTADA", "PROPOSTA")
    proposta_id = int(proposta[0])
    assert con.execute("SELECT COUNT(*) FROM audit_logs "
                       "WHERE action='AFIRMACAO_EXPRESSA'").fetchone()[0] == 0
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "data-propostas-de-oficio" in ficha
    # O OFICIAL APROVA, com a afirmação expressa, e o servidor executa: só
    # então o título volta a APONTADO. Com ele PAGO, o pagamento novo seria
    # recusado (`recusar_pagamento_na_situacao`).
    postar_e_seguir(
        s["c"], f"/administrativo/correcoes-de-oficio/{proposta_id}/aprovar",
        {"csrf_token": _token(ficha), "afirmo": "1",
         "afirmacao": ("Afirmo, sob minha responsabilidade, que o pagamento do "
                       "título não aconteceu: o selo falhou e ele ficou PAGO.")})
    con = _con(s)
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "APONTADO"
    con.close()
    # E O PAGAMENTO SE LANÇA DE NOVO; a obrigação some sozinha. (Em espécie:
    # PIX só com o crédito conferido, 29/10/2026.)
    lancado = _post(s, f"/protesto/{tid}/lancar", ato="PAGAMENTO",
                    forma_pagamento="ESPECIE", selo=SELO_BOM)
    assert "Pagamento lançado" in lancado
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "data-pendencias-do-selo" not in ficha
    assert "data-situacao-sem-ato" not in ficha


def test_a_correcao_de_oficio_nao_e_do_balcao(tmp_path):
    """Corrigir a situação é decisão de quem responde: o escrevente vê o aviso
    e a quem pedir, e a rota recusa."""
    s = _sessao(tmp_path, papel="USER")
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO pt_titulos(especie, numero_titulo, protocolo,
                   valor_centavos, saldo_centavos, situacao, origem,
                   origem_chave, criado_em)
               VALUES ('DMI','9614/U','2610210002',10000,10000,'PAGO','CRA',
                       't:9614u','2026-10-21T08:00:00')""")
        tid = int(cur.lastrowid)
    con.close()
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "data-situacao-sem-ato" in ficha
    assert "Propor a correção de ofício" not in ficha
    assert "é do oficial ou do" in " ".join(ficha.split())
    # O token vem de uma tela do balcão: a ficha do título PAGO não tem
    # formulário para quem não pode corrigir.
    token = _token(s["c"].get("/protesto/novo").get_data(as_text=True))
    r = s["c"].post(f"/protesto/{tid}/situacao/corrigir",
                    data={"csrf_token": token, "motivo": AFIRMACAO_BOA})
    assert r.status_code in (302, 403)
    assert _con(s).execute("SELECT situacao FROM pt_titulos WHERE id=?",
                           (tid,)).fetchone()[0] == "PAGO"


def test_ninguem_procura_na_auditoria_o_nome_antigo_da_volta_do_titulo():
    """Revisão do LH06 (conferida no LH08): a volta do título se audita como
    `situacao_restaurada`, o nome da produção e do sandbox. O nome antigo só
    existiu na branch, do LT04 (20/10/2026) ao LH06, e nunca foi ao servidor
    — não há linha gravada com ele. Por isso nenhuma tela, relatório ou
    módulo pode procurá-lo: acharia sempre vazio.

    O nome antigo se escreve em duas metades para que este arquivo não seja,
    ele mesmo, o achado; e a varredura prova que leu o que importa (o módulo
    que grava o nome novo), senão passaria sem ler nada."""
    antigo = "situacao_" + "restabelecida"
    arquivos = [p for padrao in ("*.py", "templates/**/*.html", "static/**/*.js",
                                 "tools/**/*.py", "tests/**/*.py", "docs/**/*.md")
                for p in RAIZ.glob(padrao) if p.is_file()]
    lidos = {p.relative_to(RAIZ).as_posix():
             p.read_text(encoding="utf-8", errors="replace") for p in arquivos}
    assert '"situacao_restaurada": situacao_restaurada' in lidos["atribuicoes_web.py"]
    assert len(lidos) > 500, len(lidos)
    assert [nome for nome, texto in lidos.items() if antigo in texto] == []


def test_titulo_sem_devedor_e_recusado_pelo_contrato_da_cra(s):
    # Quem recusa e `protesto_cra.conferir_titulo`, e nao a rota: repetir a
    # lista de campos obrigatorios na tela daria duas versoes dela.
    html = _post_novo(s, "/protesto/novo", **TITULO)
    assert "ao menos um devedor" in html
    assert _con(s).execute("SELECT COUNT(*) FROM pt_titulos").fetchone()[0] == 0


def test_o_titulo_recusado_volta_com_o_devedor_inteiro(s):
    """Na recusa só o nome do devedor voltava: documento, tipo, endereço, bairro, CEP, cidade e UF sumiam (31/10/2026)."""
    html = _post_novo(s, "/protesto/novo", **TITULO, **{**DEVEDOR, "devedor_documento_tipo": "CNPJ", "devedor_cep": "65000000", "devedor_uf": "PI"},
                      apresentante_documento="123")
    assert "CPF/CNPJ do apresentante" in html
    for trecho in ('value="JOSÉ DA SILVA"', 'value="04785512388"', 'value="RUA GRANDE, 10"', 'value="CENTRO"', 'value="65000000"',
                   'value="Cidade Exemplo"', '<option value="CNPJ" selected>', '<option value="PI" selected>'):
        assert trecho in html, trecho
    assert _con(s).execute("SELECT COUNT(*) FROM pt_titulos").fetchone()[0] == 0


def test_devedor_sem_endereco_e_recusado_dizendo_o_que_acontece(s):
    sem_endereco = {k: v for k, v in DEVEDOR.items()
                    if k not in ("devedor_endereco", "devedor_bairro",
                                 "devedor_cidade", "devedor_uf")}
    html = _post_novo(s, "/protesto/novo", **TITULO, **sem_endereco)
    assert "sem ele não há como intimar" in html


def test_assento_novo_vai_para_o_livro_da_especie_e_nao_para_o_escolhido(s):
    # A ESPECIE MANDA NA SERIE. Deixar o balcao escolher o livro e deixar
    # lancar obito em livro de nascimento — e a tela nem pergunta.
    html = _post_novo(s, "/rcpn/novo", especie="OBITO",
                      nome="MARIA DAS DORES", data_fato="2026-08-01",
                      pessoa_nome="MARIA DAS DORES",
                      local_fato_nome="Hospital Municipal",
                      numero_do="98765",
                      filiacao1_nome="IGNORADO", filiacao2_nome="IGNORADO",
                      declarante_nome="FULANO",
                      # relato #130: a CRC exige «deixou bens»
                      obito_possui_bens="NAO")
    assert "Assento lavrado" in html
    a = _con(s).execute("SELECT * FROM rc_assentos").fetchone()
    assert a["serie"] == "RC_C"            # obito, e nao RC_A
    assert a["situacao"] == "ATIVO"
    ato = _con(s).execute("SELECT * FROM rc_atos").fetchone()
    assert ato["tipo"] == "REGISTRO"
    assert ato["numero_ordem"] == 1


def test_assento_de_especie_desconhecida_e_recusado_com_frase_de_balcao(s):
    html = _post_novo(s, "/rcpn/novo", especie="BATIZADO", nome="X")
    assert "Espécie de assento desconhecida" in html
    assert _con(s).execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0] == 0


def test_registro_novo_de_rtd_tira_a_atribuicao_da_serie(s):
    # A atribuicao NAO e campo do formulario: vem de `livro_nucleo.SERIES`.
    # Dois lugares nao podem discordar de a qual atribuicao uma serie pertence.
    html = _post_novo(s, "/rcpj-rtd/novo", serie="TD_B",
                      natureza="Contrato de locação",
                      requerente_nome="EMPRESA Y")
    assert "Assim vai sair na tira" in html
    r = _con(s).execute("SELECT * FROM rg_registros").fetchone()
    assert r["serie"] == "TD_B"
    assert r["atribuicao"] == 4            # RTD, dito pela serie


def test_registro_de_serie_que_nao_e_rcpj_nem_rtd_e_recusado(s):
    html = _post_novo(s, "/rcpj-rtd/novo", serie="RC_A", requerente_nome="X")
    assert "não é de RCPJ nem de RTD" in html
    assert _con(s).execute("SELECT COUNT(*) FROM rg_registros").fetchone()[0] == 0


def test_registro_novo_do_livro_3_nasce_como_R_1_com_as_partes(s):
    html = _post_novo(s, "/livro3/novo", natureza="CEDULA_CREDITO_RURAL",
                      titulo_tipo="CÉDULA RURAL PIGNORATÍCIA",
                      titulo_numero="55/2026", valor="10.000,00",
                      parte_nome="BANCO DO NORDESTE",
                      parte_documento_tipo="CNPJ",
                      parte_documento="00000017000149",
                      parte_papel="credor")
    assert "Livro 3 lavrado" in html
    con = _con(s)
    r = con.execute("SELECT * FROM ra_registros").fetchone()
    assert r["livro"] == "3"
    assert r["valor_centavos"] == 1000000
    ato = con.execute("SELECT * FROM ra_atos").fetchone()
    assert ato["tipo"] == "R" and ato["numero"] == 1
    parte = con.execute("SELECT * FROM ra_partes").fetchone()
    assert parte["nome"] == "BANCO DO NORDESTE"
    assert parte["papel"] == "CREDOR", "o papel entra como código do catálogo (19/10/2026)"


def test_registro_do_livro_3_com_natureza_de_fora_do_catalogo_e_recusado(s):
    html = _post_novo(s, "/livro3/novo", natureza="COMPRA_E_VENDA")
    assert "não é do Livro 3" in html
    assert _con(s).execute("SELECT COUNT(*) FROM ra_registros").fetchone()[0] == 0


def test_abrir_registro_novo_com_selo_de_outra_serventia_nao_deixa_registro(s):
    # Mesma regra do lancamento de ato: selo RECUSADO derruba tudo, e nao
    # sobra registro lavrado com selo que o sistema nao aceitou.
    html = _post_novo(s, "/rcpn/novo", especie="NASCIMENTO", nome="ANA",
                      pessoa_nome="ANA", pessoa_sexo="F",
                      data_fato="2026-08-20",
                      local_fato_nome="Hospital Municipal",
                      ibge_local="1",       # relato #130: o SIRC exige
                      filiacao1_nome="MARIA", filiacao2_nome="IGNORADO",
                      declarante_nome="MARIA",
                      paternidade_tipo="NEGATIVO",   # termo (23/10/2026)
                      selo="AVESVD999999NARRKWVNJCRSVO21")
    assert "não é desta serventia" in html
    assert _con(s).execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0] == 0


# ------------------- a mãe não compareceu: a terceira saída (27/10/2026)


def test_a_tela_do_nascimento_oferece_a_mae_ausente_com_o_motivo(s):
    html = s["c"].get("/rcpn/novo/nascimento").get_data(as_text=True)
    assert 'value="MAE_AUSENTE"' in html
    assert 'name="motivo_ausencia_mae"' in html


def test_ao_voltar_para_editar_a_mae_ausente_e_o_motivo_continuam(s):
    c = s["c"]
    token = _token(c.get("/rcpn/novo/nascimento").get_data(as_text=True))
    html = c.post("/rcpn/novo/nascimento", data={
        "csrf_token": token, "acao": "voltar_editar",
        "pessoa_nome": "ANA", "paternidade_tipo": "MAE_AUSENTE",
        "motivo_ausencia_mae": "registro tardio pelo próprio registrado",
    }).get_data(as_text=True)
    assert re.search(r'<option value="MAE_AUSENTE"\s+selected', html)
    assert 'value="registro tardio pelo próprio registrado"' in html


def _com_mae_ausente(s) -> int:
    assento_id = _semear(s)["assento"]
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO rc_termos_paternidade(assento_id, tipo,
                   registrado_nome, mae_nome, motivo_ausencia_mae, teor,
                   hash_teor, criado_em)
               VALUES (?, 'MAE_AUSENTE', 'JOÃO DA SILVA', 'MARIA DA SILVA',
                       'mãe falecida', 'Texto de exemplo da anotação.', 'abc',
                       '2026-10-27T09:00:00')""", (assento_id,))
    con.close()
    return assento_id


def test_a_ficha_mostra_a_anotacao_e_nao_oferece_termo_nem_remessa(s):
    assento_id = _com_mae_ausente(s)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert "mãe não compareceu — averiguação não iniciada: mãe falecida" in html
    assert "Imprimir o termo (.odt)" not in html
    assert "Registrar a remessa" not in html


def test_o_odt_do_termo_nao_sai_para_a_mae_ausente(s):
    assento_id = _com_mae_ausente(s)
    r = s["c"].get(f"/rcpn/{assento_id}/paternidade/termo",
                   follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "não há termo de paternidade para imprimir" in html
    assert r.mimetype != "application/vnd.oasis.opendocument.text"


def test_abrir_registro_novo_cobra_no_caixa_o_que_foi_marcado(s):
    servico = _com_servico(s)
    caixa_id = _abrir_caixa(s)
    html = _post_novo(s, "/livro3/novo", natureza="PACTO_ANTENUPCIAL",
                      cobrar=str(servico), pagador="JOÃO")
    assert "Lançado no caixa" in html
    linha = _con(s).execute(
        "SELECT * FROM cx_lancamentos WHERE origem='ATO'").fetchone()
    assert linha["caixa_id"] == caixa_id
    assert linha["pagador"] == "JOÃO"

# ------------------------------------------------- a certidão de protesto
#
# E o que o balcao mais pede, e por muito tempo nao teve resposta: a carga do
# acervo trazia os 1.366 titulos e NENHUM devedor.


def _com_protesto(s, nome="JOSÉ DA SILVA", documento="04785512388",
                  numero="7777/1", data="2024-03-10", cancelamento=None) -> int:
    """Um titulo protestado, com devedor pesquisavel."""
    from pt_schema import normalizar_nome
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO pt_titulos(especie, numero_titulo, valor_centavos,
                   saldo_centavos, cedente_nome, situacao, origem, criado_em)
               VALUES ('DMI',?,148278,148278,'BANCO DO NORDESTE','PROTESTADO',
                       'MANUAL','2026-08-25T09:00:00')""", (numero,))
        titulo_id = int(cur.lastrowid)
        con.execute(
            """INSERT INTO pt_devedores(titulo_id, nome, nome_norm,
                   documento_tipo, documento_numero, cidade, uf)
               VALUES (?,?,?,'CPF',?,'Cidade Exemplo','MA')""",
            (titulo_id, nome, normalizar_nome(nome), documento))
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, folha, data_ato,
                   detalhe_json, origem, criado_em)
               VALUES (?,'PROTESTO',120,?,'{"livro_do_acervo": 5}','MANUAL',
                       '2026-08-25T09:00:00')""", (titulo_id, data))
        if cancelamento:
            con.execute(
                """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem,
                       criado_em)
                   VALUES (?,'CANCELAMENTO',?,'MANUAL','2026-08-25T09:00:00')""",
                (titulo_id, cancelamento))
    con.close()
    return titulo_id


def _emitir(s, **campos) -> str:
    c = s["c"]
    token = _token(c.get("/protesto/certidoes").get_data(as_text=True))
    # Estes testes medem busca, teor e caixa. O selo automático por item tem
    # ensaio próprio; aqui a certidão leva um selo válido já informado.
    campos.setdefault("selo", "AVESVD000000NARRKWVNJCRSVO21")
    # O CPF/CNPJ é obrigatório desde 14/10/2026 (CN-MA art. 906).
    campos.setdefault("documento", "04785512388")
    return c.post("/protesto/certidoes/emitir",
                  data={"csrf_token": token, **campos},
                  follow_redirects=True).get_data(as_text=True)


def test_a_tela_da_certidao_abre_e_procura_por_nome_ou_documento(s):
    html = s["c"].get("/protesto/certidoes").get_data(as_text=True)
    assert "Certidão de protesto" in html
    assert "CPF ou CNPJ" in html
    assert "Período de busca" in html


def test_a_busca_sem_achar_diz_que_cabe_a_negativa(s):
    html = s["c"].get(
        "/protesto/certidoes?nome=NINGUEM").get_data(as_text=True)
    assert "Nenhum protesto" in html
    assert "NEGATIVA" in html


def test_a_busca_acha_e_diz_qual_certidao_cabe(s):
    _com_protesto(s)
    html = s["c"].get(
        "/protesto/certidoes?nome=silva&anos=20").get_data(as_text=True)
    assert "1 protesto(s)" in html
    assert "POSITIVA" in html
    assert "Livro 5, fl. 120" in html


def test_apontamento_nao_aparece_na_busca_da_certidao(s):
    # `_semear` cria titulo PROTESTADO com apontamento e SEM ato de protesto.
    # Apontamento nao e protesto: certidao que o mostrasse mentiria contra a
    # pessoa.
    _semear(s)
    html = s["c"].get(
        "/protesto/certidoes?nome=DEVEDOR&anos=20").get_data(as_text=True)
    assert "Nenhum protesto" in html


def test_emitir_negativa_grava_e_leva_para_a_certidao(s):
    html = _emitir(s, nome="MARIA DAS DORES", documento="04785512388",
                   anos="5", tipo="NEGATIVA")
    assert "emitida" in html
    assert "NÃO ENCONTREI protesto contra MARIA DAS DORES" in html
    linha = _con(s).execute("SELECT * FROM pt_certidoes").fetchone()
    assert linha["numero"] == 1
    assert linha["tipo"] == "NEGATIVA"
    assert linha["emitida_por"] == "MARIO EXEMPLO DOS SANTOS"
    assert len(linha["hash_certidao"]) == 64


def test_a_tela_recusa_negativa_sobre_quem_tem_protesto(s):
    # A REGRA QUE MAIS IMPORTA, e quem a aplica e o dominio: negativa errada e
    # a certidao que faz o banco emprestar para quem nao devia.
    _com_protesto(s)
    html = _emitir(s, nome="JOSÉ DA SILVA", documento="04785512388",
                   anos="20", tipo="NEGATIVA")
    assert "achou 1 protesto" in html
    assert _con(s).execute(
        "SELECT COUNT(*) FROM pt_certidoes").fetchone()[0] == 0


def test_a_busca_roda_de_novo_na_emissao(s):
    # Entre procurar e emitir alguem pode ter lavrado protesto. A rota nao
    # confia no que veio da tela: busca outra vez, e o dominio recusa.
    s["c"].get("/protesto/certidoes?nome=JOSÉ DA SILVA&anos=20")
    _com_protesto(s)                     # o protesto entra DEPOIS da busca
    html = _emitir(s, nome="JOSÉ DA SILVA", anos="20", tipo="NEGATIVA")
    assert "achou 1 protesto" in html


def test_a_positiva_sai_com_o_livro_a_folha_e_a_data(s):
    _com_protesto(s)
    html = _emitir(s, nome="JOSÉ DA SILVA", documento="04785512388",
                   anos="20", tipo="POSITIVA", requerente="BANCO DO BRASIL")
    assert "Título n. 7777/1" in html
    assert "Livro 5, fl. 120" in html
    assert "protestado em 10/03/2024" in html
    assert "a requerimento de BANCO DO BRASIL" in html


def test_a_ficha_da_certidao_mostra_o_teor_e_a_autenticidade(s):
    _emitir(s, nome="MARIA", anos="5")
    cid = _con(s).execute("SELECT id FROM pt_certidoes").fetchone()[0]
    html = s["c"].get(f"/protesto/certidoes/{cid}").get_data(as_text=True)
    assert "congelado na emissão" in html
    assert "Autenticidade" in html
    assert "Baixar em .odt" in html


def test_certidao_que_nao_existe_avisa_e_volta(s):
    r = s["c"].get("/protesto/certidoes/9999", follow_redirects=True)
    assert r.status_code == 200
    assert "não encontrada" in r.get_data(as_text=True)


def test_a_certidao_sai_em_odt_para_o_cliente_levar(s):
    # Papel que o cliente leva para casa sai em arquivo, e nao em tela — a
    # mesma forma do recibo do caixa e dos termos dos livros.
    _emitir(s, nome="MARIA", anos="5")
    cid = _con(s).execute("SELECT id FROM pt_certidoes").fetchone()[0]
    # **O `.odt` PASSOU A PEDIR `?formato=odt`** — 01/09/2026, quando o oficial
    # mandou o botao entregar PDF. Este teste confere o CONTEUDO do papel, e
    # para isso precisa do zip; o que o BOTAO entrega esta guardado em
    # `tests/test_impressao_pdf.py`.
    r = s["c"].get(f"/protesto/certidoes/{cid}/odt?formato=odt")
    assert r.status_code == 200
    assert "opendocument" in r.headers["Content-Type"]
    assert f"certidao-protesto-1-{_con(s).execute('SELECT ano FROM pt_certidoes').fetchone()[0]}.odt" \
        in r.headers["Content-Disposition"]
    assert r.data[:2] == b"PK"


def test_cancelar_a_certidao_guarda_o_teor_que_saiu(s):
    _emitir(s, nome="MARIA", anos="5")
    cid = _con(s).execute("SELECT id FROM pt_certidoes").fetchone()[0]
    c = s["c"]
    token = _token(c.get(f"/protesto/certidoes/{cid}").get_data(as_text=True))
    html = c.post(f"/protesto/certidoes/{cid}/cancelar",
                  data={"csrf_token": token, "motivo": "erro",
                        "selo_cancelado_tjma": "1"},
                  follow_redirects=True).get_data(as_text=True)
    assert "dez letras" in html
    html = c.post(f"/protesto/certidoes/{cid}/cancelar",
                  data={"csrf_token": token,
                        "motivo": "emitida com o nome errado",
                        "selo_cancelado_tjma": "1"},
                  follow_redirects=True).get_data(as_text=True)
    assert "Certidão cancelada" in html
    assert "foi cancelada" in html
    linha = _con(s).execute("SELECT * FROM pt_certidoes").fetchone()
    assert int(linha["cancelada"]) == 1
    assert "NÃO ENCONTREI" in linha["teor"]      # o teor fica, como saiu


def test_emitir_certidao_marcando_item_cobra_no_caixa(s):
    servico = _com_servico(s, codigo=2, codigo_tj="17.5.1", total="53,58")
    caixa_id = _abrir_caixa(s)
    html = _emitir(s, nome="MARIA", anos="5", cobrar=str(servico),
                   pagador="MARIA")
    assert "Lançado no caixa" in html
    linha = _con(s).execute(
        "SELECT * FROM cx_lancamentos WHERE origem='ATO'").fetchone()
    assert linha["caixa_id"] == caixa_id
    assert linha["valor"] == "53,58"
    assert _con(s).execute(
        "SELECT lancamento_id FROM pt_certidoes").fetchone()[0] == linha["id"]


def test_selo_de_outra_serventia_derruba_a_emissao_inteira(s):
    # Mesma regra do lancamento de ato: selo recusado desfaz tudo, e nao sobra
    # certidao numerada com selo que o sistema nao aceitou.
    html = _emitir(s, nome="MARIA", anos="5",
                   selo="AVESVD999999NARRKWVNJCRSVO21")
    assert "não é desta serventia" in html
    assert _con(s).execute(
        "SELECT COUNT(*) FROM pt_certidoes").fetchone()[0] == 0


def test_o_menu_e_a_lista_levam_a_certidao(s):
    # O ROTULO MUDOU EM 27/08/2026, e o endereco nao: cada atribuicao ganhou o
    # seu grupo no menu, e dentro de «Protesto» o link virou so «Certidoes».
    html = s["c"].get("/protesto").get_data(as_text=True)
    assert "/protesto/certidoes" in html         # o menu
    assert "Certidão de protesto" in html        # o botão da lista


# ------------------------- a certidão de inteiro teor do RCPJ/RTD e do Livro 3
#
# Emitir e na FICHA do registro, e nao numa tela a parte: e ali que o
# escrevente esta quando o cliente pede, e e ali que ele acabou de ver o que o
# livro diz.

TEOR_DO_LIVRO = ("Aos 26 dias do mês de novembro de dois mil e vinte e um, "
                 "reuniram-se em Assembleia Geral os associados.")


def _com_teor(s, ids) -> None:
    """Poe teor e lugar nos dois registros que `_semear` criou."""
    con = _con(s)
    with con:
        con.execute("UPDATE rg_registros SET teor=?, volume='7' WHERE id=?",
                    (TEOR_DO_LIVRO, ids["registro"]))
        con.execute("""UPDATE rg_atos SET folha=79, data_ato='2022-12-15'
                        WHERE registro_id=?""", (ids["registro"],))
        con.execute("UPDATE ra_registros SET teor=? WHERE id=?",
                    (TEOR_DO_LIVRO, ids["livro3"]))
    con.close()


def _emitir_certidao(s, atribuicao: str, registro_id: int, **campos) -> str:
    c = s["c"]
    ficha = ("/rcpj-rtd/" if atribuicao == "RCPJ_RTD" else "/livro3/")
    token = _token(c.get(f"{ficha}{registro_id}").get_data(as_text=True))
    return c.post(f"/atribuicoes/certidoes/{atribuicao}/{registro_id}",
                  data={"csrf_token": token, **campos},
                  follow_redirects=True).get_data(as_text=True)


def test_a_ficha_diz_quando_o_registro_veio_sem_teor(s):
    # 24 dos 72 do RCPJ/RTD estao assim. O registro consta do livro, e a copia
    # se tira do livro fisico.
    ids = _semear(s)
    html = s["c"].get(f"/rcpj-rtd/{ids['registro']}").get_data(as_text=True)
    assert "veio do acervo sem o teor" in html
    assert "Emitir certidão de inteiro teor" not in html


def test_a_ficha_oferece_a_certidao_quando_ha_teor(s):
    ids = _semear(s)
    _com_teor(s, ids)
    html = s["c"].get(f"/rcpj-rtd/{ids['registro']}").get_data(as_text=True)
    assert "Emitir certidão de inteiro teor" in html
    assert "reproduz o que está no livro" in html


def test_emitir_pela_ficha_leva_para_a_certidao(s):
    ids = _semear(s)
    _com_teor(s, ids)
    html = _emitir_certidao(s, "RCPJ_RTD", ids["registro"],
                            requerente="BANCO DO BRASIL", finalidade="prova")
    assert "emitida" in html
    assert "CERTIFICO E DOU FÉ" in html
    # As aspas do livro saem escapadas no HTML (`&#34;B-7&#34;`); o que se
    # confere aqui e o texto, e nao a forma como o navegador o recebe.
    assert "B-7" in html
    assert "de Registro de Títulos e Documentos" in html
    assert TEOR_DO_LIVRO in html
    linha = _con(s).execute("SELECT * FROM at_certidoes").fetchone()
    assert linha["atribuicao"] == "RCPJ_RTD"
    assert linha["numero"] == 1
    assert linha["requerente"] == "BANCO DO BRASIL"
    assert linha["emitida_por"] == "MARIO EXEMPLO DOS SANTOS"


def test_emitir_do_livro_3_usa_a_frase_da_casa(s):
    ids = _semear(s)
    _com_teor(s, ids)
    html = _emitir_certidao(s, "LIVRO3", ids["livro3"])
    assert "Livro 3 Auxiliar de Registro Geral de Imóveis" in html


def test_a_tela_recusa_certidao_de_registro_sem_teor(s):
    # Quem recusa e o dominio, e nao a rota — a tela so esconde o botao.
    ids = _semear(s)
    html = _emitir_certidao(s, "RCPJ_RTD", ids["registro"])
    assert "livro físico" in html
    assert _con(s).execute(
        "SELECT COUNT(*) FROM at_certidoes").fetchone()[0] == 0


def test_a_lista_de_certidoes_abre_e_mostra_as_emitidas(s):
    ids = _semear(s)
    _com_teor(s, ids)
    _emitir_certidao(s, "RCPJ_RTD", ids["registro"])
    html = s["c"].get("/atribuicoes/certidoes").get_data(as_text=True)
    assert "Certidões — RCPJ, RTD e Livro 3" in html
    assert "1/" in html
    vazia = s["c"].get(
        "/atribuicoes/certidoes?atribuicao=LIVRO3").get_data(as_text=True)
    assert "Nenhuma certidão emitida ainda" in vazia


def test_a_certidao_sai_em_odt(s):
    ids = _semear(s)
    _com_teor(s, ids)
    _emitir_certidao(s, "LIVRO3", ids["livro3"])
    cid = _con(s).execute("SELECT id FROM at_certidoes").fetchone()[0]
    # Idem: o conteudo se confere no `.odt`, e o botao entrega PDF.
    r = s["c"].get(f"/atribuicoes/certidoes/{cid}/odt?formato=odt")
    assert r.status_code == 200
    assert "opendocument" in r.headers["Content-Type"]
    assert "certidao-livro3-1-" in r.headers["Content-Disposition"]
    assert r.data[:2] == b"PK"


def test_certidao_de_atribuicao_que_nao_existe_avisa_e_volta(s):
    r = s["c"].get("/atribuicoes/certidoes/9999", follow_redirects=True)
    assert r.status_code == 200
    assert "não encontrada" in r.get_data(as_text=True)


def test_cancelar_a_certidao_guarda_o_teor(s):
    ids = _semear(s)
    _com_teor(s, ids)
    _emitir_certidao(s, "RCPJ_RTD", ids["registro"])
    cid = _con(s).execute("SELECT id FROM at_certidoes").fetchone()[0]
    c = s["c"]
    token = _token(c.get(f"/atribuicoes/certidoes/{cid}").get_data(as_text=True))
    html = c.post(f"/atribuicoes/certidoes/{cid}/cancelar",
                  data={"csrf_token": token, "motivo": "registro errado, sim",
                        "selo_cancelado_tjma": "1"},
                  follow_redirects=True).get_data(as_text=True)
    assert "Certidão cancelada" in html
    linha = _con(s).execute("SELECT * FROM at_certidoes").fetchone()
    assert int(linha["cancelada"]) == 1
    assert TEOR_DO_LIVRO in linha["teor"]


def test_emitir_certidao_de_atribuicao_marcando_item_cobra_no_caixa(s):
    ids = _semear(s)
    _com_teor(s, ids)
    servico = _com_servico(s, codigo=3, codigo_tj="17.5.2", total="41,20")
    caixa_id = _abrir_caixa(s)
    html = _emitir_certidao(s, "RCPJ_RTD", ids["registro"],
                            cobrar=str(servico), pagador="MARIA")
    assert "Lançado no caixa" in html
    linha = _con(s).execute(
        "SELECT * FROM cx_lancamentos WHERE origem='ATO'").fetchone()
    assert linha["caixa_id"] == caixa_id
    assert _con(s).execute(
        "SELECT lancamento_id FROM at_certidoes").fetchone()[0] == linha["id"]


def test_selo_de_outra_serventia_derruba_a_certidao_inteira(s):
    ids = _semear(s)
    _com_teor(s, ids)
    html = _emitir_certidao(s, "RCPJ_RTD", ids["registro"],
                            selo="AVESVD999999NARRKWVNJCRSVO21")
    assert "não é desta serventia" in html
    assert _con(s).execute(
        "SELECT COUNT(*) FROM at_certidoes").fetchone()[0] == 0


def test_o_menu_leva_as_certidoes_das_atribuicoes(s):
    """A certidao das tres mora no grupo de RCPJ e RTD desde 27/08/2026.

    Ela serve tres atribuicoes, e quem a abre e o grupo de quem mais a
    procura — 72 registros contra 14 do Livro 3. O link continua no menu de
    quem esta no Livro 3; o que mudou foi de que gaveta ele sai.
    """
    html = s["c"].get("/livro3").get_data(as_text=True)
    assert "/atribuicoes/certidoes" in html
    assert "Certidões de inteiro teor" in html


# ------------------------------------------------------ o retorno à CRA
#
# 93% dos titulos desta casa entram pela CRA. Sem o retorno eles entram e
# nunca voltam.


def _titulo_da_cra(s, numero="8888/1", apresentante="001") -> int:
    """Um titulo vindo da CRA, apontado e protestado — pronto para o retorno."""
    import protesto as PT
    con = _con(s)
    sv = {"unit_name": "SERVENTIA", "serventia_titular": "MARIO",
          "serventia_titulo": "Tabelião", "ri_cns": "000000",
          "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
    agora = "2026-08-25T10:00:00"
    with con:
        tid = PT.cadastrar_titulo(con, {
            "apresentante_codigo": apresentante,
            "apresentante_nome": "BANCO DO BRASIL",
            "especie": "DMI", "numero_titulo": numero,
            "nosso_numero": f"NN{numero}",
            "data_emissao": "2026-01-05", "data_vencimento": "2026-02-05",
            "valor": "1.200,00", "saldo": "1.310,45",
            "praca_protesto": "CIDADE EXEMPLO",
            # O motivo vem da remessa da CRA (posição 297); desde 14/10/2026
            # o termo do protesto recusa sem ele (inspeção, tarefa #49).
            "motivo_protesto": "1",
            "cedente": {"nome": "LOJA CENTRAL LTDA"},
            "devedores": [{"nome": "JOSÉ DA SILVA", "CPF": "04785512388",
                           "enderecos": [{"endereco": "RUA GRANDE, 10",
                                          "cidade": "Cidade Exemplo",
                                          "uf": "MA"}]}],
        }, origem="CRA", origem_chave=f"lote:{numero}", agora=agora)
        PT.lancar_apontamento(con, tid, sv=sv, agora=agora, data_extenso="x")
        PT.lancar_intimacao(con, tid, modo="PESSOAL", agora=agora)
        juntar_prova(con, tid)   # a prova da intimação (29/10/2026)
        PT.lancar_protesto(con, tid, sv=sv, agora=agora, data_extenso="x")
    con.close()
    return tid


def test_a_tela_do_retorno_abre_e_diz_quando_nao_ha_nada(s):
    html = s["c"].get("/protesto/retornos").get_data(as_text=True)
    assert "Retorno à CRA" in html
    assert "Nada a informar" in html


def test_a_tela_mostra_quem_espera_retorno(s):
    _titulo_da_cra(s)
    html = s["c"].get("/protesto/retornos").get_data(as_text=True)
    assert "8888/1" in html
    assert "PROTESTO" in html
    assert "2608250001" in html          # o protocolo, na forma medida


def test_gerar_produz_o_par_e_some_dos_pendentes(s):
    # "SEMPRE QUE GERAR RETORNO (FINAL), GERAR ANDAMENTO" — o roteiro do
    # protesto que o oficial trouxe.
    _titulo_da_cra(s)
    c = s["c"]
    token = _token(c.get("/protesto/retornos").get_data(as_text=True))
    html = c.post("/protesto/retornos/gerar",
                  data={"csrf_token": token, "apresentante_codigo": "001",
                        "dia": "2026-08-25", "numero_da_remessa": "1",
                        "marca": "A"},
                  follow_redirects=True).get_data(as_text=True)
    assert "Retorno e andamento gerados" in html
    assert "R0012508.261" in html      # nome FEBRABAN desde 13/10/2026
    assert "M0012508.261" in html
    assert "Nada a informar" in html      # não sai duas vezes
    linhas = _con(s).execute(
        "SELECT tipo, titulos FROM pt_retornos ORDER BY id").fetchall()
    assert [x["tipo"] for x in linhas] == ["SDTBFORTP", "SDTBFOAND"]
    assert [x["titulos"] for x in linhas] == [1, 1]


def test_o_arquivo_baixa_em_600_posicoes_e_sem_utf8(s):
    # O arquivo de 600 posicoes nunca foi UTF-8: acento em dois bytes
    # empurraria todos os campos da linha para a direita.
    _titulo_da_cra(s)
    c = s["c"]
    token = _token(c.get("/protesto/retornos").get_data(as_text=True))
    c.post("/protesto/retornos/gerar",
           data={"csrf_token": token, "apresentante_codigo": "001",
                 "dia": "2026-08-25", "marca": "A"}, follow_redirects=True)
    rid = _con(s).execute(
        "SELECT id FROM pt_retornos WHERE tipo='SDTBFORTP'").fetchone()[0]
    r = c.get(f"/protesto/retornos/{rid}/arquivo")
    assert r.status_code == 200
    assert "ISO-8859-1" in r.headers["Content-Type"]
    # Nome FEBRABAN desde 13/10/2026: a CRA recusa o nome interno (código 0002).
    assert "R0012508.261" in r.headers["Content-Disposition"]
    linhas = r.data.decode("latin-1").splitlines()
    assert {len(x) for x in linhas} == {600}
    assert linhas[1][457] == "C"          # a ocorrência medida do protesto


def _retorno_recusado_pela_cra(s) -> int:
    """Gera o retorno pela tela e o marca RECUSADO como `protesto_cra_envio`
    marca (28/10/2026): `cra_recusado_em`, o código e o motivo da Central,
    e `cra_enviado_em` vazio. A rede não roda aqui."""
    _titulo_da_cra(s)
    c = s["c"]
    token = _token(c.get("/protesto/retornos").get_data(as_text=True))
    c.post("/protesto/retornos/gerar",
           data={"csrf_token": token, "apresentante_codigo": "001",
                 "dia": "2026-08-25", "marca": "A"}, follow_redirects=True)
    con = _con(s)
    with con:
        rid = con.execute(
            "SELECT id FROM pt_retornos WHERE tipo='SDTBFORTP'").fetchone()[0]
        con.execute(
            """UPDATE pt_retornos SET cra_recusado_em='2026-08-25T14:32:41',
                   cra_recusa_codigo='2161',
                   cra_recusa_motivo='NENHUM REGISTRO FOI GRAVADO',
                   cra_envio_erro='A CRA recusou (código 2161)',
                   cra_enviado_ambiente='PRODUCAO'
               WHERE id=?""", (rid,))
    return int(rid)


def test_o_retorno_recusado_aparece_recusado_com_o_motivo_e_nao_enviado(s):
    """A TELA DIZIA «ENVIADO» SOBRE SEIS RECUSADOS — 28/10/2026."""
    _retorno_recusado_pela_cra(s)
    html = s["c"].get("/protesto/retornos").get_data(as_text=True)
    assert "recusado pela CRA" in html
    assert "código 2161" in html
    assert "NENHUM REGISTRO FOI GRAVADO" in html
    assert "não foram informados" in html
    assert "Devolver os atos à fila" in html
    assert "<strong>enviado</strong>" not in html


def test_devolver_os_atos_do_recusado_pela_tela(s):
    rid = _retorno_recusado_pela_cra(s)
    c = s["c"]
    token = _token(c.get("/protesto/retornos").get_data(as_text=True))
    html = c.post(f"/protesto/retornos/{rid}/devolver-atos",
                  data={"csrf_token": token},
                  follow_redirects=True).get_data(as_text=True)
    assert "voltaram a «Esperando retorno»" in html
    assert "8888/1" in html                 # o protesto voltou à fila
    assert _con(s).execute(
        "SELECT COUNT(*) FROM pt_atos WHERE retorno_id=?",
        (rid,)).fetchone()[0] == 0


def test_apresentante_sem_historico_pergunta_a_letra(s):
    # Nos arquivos medidos o empate e exato: 74 «A» e 74 «P». Chutar seria
    # inventar.
    _titulo_da_cra(s, numero="7777/1", apresentante="ZZZ")
    c = s["c"]
    token = _token(c.get("/protesto/retornos").get_data(as_text=True))
    html = c.post("/protesto/retornos/gerar",
                  data={"csrf_token": token, "apresentante_codigo": "ZZZ",
                        "dia": "2026-08-25"},
                  follow_redirects=True).get_data(as_text=True)
    assert "posição 566" in html
    assert _con(s).execute("SELECT COUNT(*) FROM pt_retornos").fetchone()[0] == 0


def test_arquivo_que_nao_existe_da_404(s):
    assert s["c"].get("/protesto/retornos/9999/arquivo").status_code == 404


def test_o_menu_leva_ao_retorno(s):
    """Dentro do grupo «Protesto», o link e «Retorno a CRA»."""
    html = s["c"].get("/protesto").get_data(as_text=True)
    assert "/protesto/retornos" in html
    assert "Retorno à CRA" in html


# ------------------------- cada atribuicao com a sua lista (27/08/2026)


def test_o_rcpj_e_o_rtd_tem_cada_um_a_sua_lista(s):
    """Pedido do oficial: cada atribuicao no seu proprio lugar.

    A TABELA CONTINUA SENDO UMA — o acervo do E-Oficio ja guardava as duas
    juntas, e o livro tem a mesma forma nas duas. O que se separou foi o que o
    balcao ve: quem procura um contrato de aluguel nao quer sociedade civil no
    meio da lista.
    """
    _semear(s)          # semeia um registro de RTD (atribuicao 4)

    rtd = s["c"].get("/rcpj-rtd?atribuicao=4").get_data(as_text=True)
    assert "EMPRESA X" in rtd
    assert "títulos e documentos" in rtd          # o titulo da tela mudou

    rcpj = s["c"].get("/rcpj-rtd?atribuicao=3").get_data(as_text=True)
    assert "EMPRESA X" not in rcpj                # o RTD nao aparece no RCPJ
    # O titulo passou a ser o NOME DA ATRIBUICAO, «RCPJ — Registro Civil das
    # Pessoas Jurídicas», com maiusculas (a regra do nome, de 28/08/2026);
    # a pergunta continua sendo «e a lista do RCPJ?» — 14/10/2026.
    assert "pessoas jurídicas" in rcpj.lower()

    # E sem filtro nenhum, as duas continuam juntas — com a coluna que diz
    # de qual atribuicao e cada linha.
    juntas = s["c"].get("/rcpj-rtd").get_data(as_text=True)
    assert "EMPRESA X" in juntas
    assert "Atribuição" in juntas


def test_o_filtro_da_atribuicao_nao_se_perde_ao_procurar(s):
    """Sem isto, procurar dentro do RTD devolvia a lista das duas."""
    _semear(s)
    html = s["c"].get("/rcpj-rtd?atribuicao=4").get_data(as_text=True)
    assert 'name="atribuicao" value="4"' in html


def test_a_contagem_por_situacao_e_a_da_lista_que_se_esta_vendo(s):
    """Contar as duas atribuicoes embaixo de uma lista que mostra so uma seria
    a tela dizendo um numero que nao e o dela."""
    _semear(s)
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO rg_registros(atribuicao, serie, numero,
                   requerente_nome, situacao, origem, criado_em)
               VALUES (3,'PJ_A',77,'ASSOCIAÇÃO Y','CANCELADO','EOFICIO',
                       '2026-08-24T09:00:00')""")
    con.close()
    rtd = s["c"].get("/rcpj-rtd?atribuicao=4").get_data(as_text=True)
    assert "ASSOCIAÇÃO Y" not in rtd
    assert "CANCELADO" not in rtd.split("Procurar", 1)[0]


# ------------- o teor do REGISTRO PRIMÁRIO do Livro 3, como o Livro 2 mostra
#
# Pedido do oficial em 22/09/2026: «acrescente o campo de teor do registro
# primário do livro 3, assim como temos no livro 2».
#
# **O TEXTO ESTAVA GRAVADO E A TELA NUNCA O MOSTROU.** Medido antes de
# escrever: `ra_registros.teor` está preenchido em **14 dos 16** registros
# desta casa, de 2.500 a 29.140 caracteres — e a ficha só desenhava o teor da
# MINUTA e o dos ATOS. Quem quisesse ler o do registro tinha de abrir o banco.


def _teor_no_livro3(s, registro_id, teor, formato="texto"):
    con = _con(s)
    with con:
        con.execute("UPDATE ra_registros SET teor=?, teor_formato=? WHERE id=?",
                    (teor, formato, registro_id))
    con.close()
    return s["c"].get(f"/livro3/{registro_id}").get_data(as_text=True)


def test_a_ficha_do_livro_3_mostra_o_teor_do_registro(s):
    """**O conserto.** O teor do registro primário aparece na ficha."""
    ids = _semear(s)
    html = _teor_no_livro3(
        s, ids["livro3"],
        "REPÚBLICA FEDERATIVA DO BRASIL — cédula rural pignoratícia lavrada "
        "nesta serventia, com as cláusulas que seguem.")
    assert "Teor do registro" in html
    assert "cédula rural pignoratícia lavrada" in html


def test_registro_sem_teor_diz_que_nao_tem(s):
    """Painel vazio se lê como tela quebrada — a mesma frase do Livro 2."""
    ids = _semear(s)
    html = s["c"].get(f"/livro3/{ids['livro3']}").get_data(as_text=True)
    assert "Teor do registro" in html
    assert "não tem texto gravado" in html


def test_o_teor_do_livro_3_sai_escapado(s):
    """**O teor é texto colado de fora, e nunca executa.**

    Os 14 desta casa estão gravados como `texto`, mas a coluna aceita `html` —
    e o pior desfecho aqui tem de ser o operador ver as marcas escritas, e não
    o navegador executá-las.
    """
    ids = _semear(s)
    html = _teor_no_livro3(
        s, ids["livro3"],
        "antes <script>alert('x')</script> depois", formato="html")
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "Este teor está gravado" in html, (
        "quem topar com um teor html precisa saber por que vê as marcas")


def test_o_teor_do_registro_nao_se_confunde_com_o_dos_atos(s):
    """Os dois aparecem na mesma ficha, e são coisas diferentes: um é o
    título, o outro é a averbação lançada depois."""
    ids = _semear(s)
    con = _con(s)
    with con:
        con.execute("UPDATE ra_atos SET teor=? WHERE registro_id=?",
                    ("TEXTO DO ATO R-1", ids["livro3"]))
    con.close()
    html = _teor_no_livro3(s, ids["livro3"], "TEXTO DO REGISTRO PRIMARIO")
    assert "TEXTO DO REGISTRO PRIMARIO" in html
    assert "TEXTO DO ATO R-1" in html
    assert html.index("TEXTO DO REGISTRO PRIMARIO") < html.index("TEXTO DO ATO R-1"), (
        "o teor do registro vem antes dos atos, como no Livro 2")
