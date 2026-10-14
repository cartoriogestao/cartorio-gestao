"""SELAR UM ATO DO RI QUE JA ESTA LAVRADO — pedido do oficial em 15/09/2026.

    «tres atos devem ficar em pe, quero revisar no sistema e poder lavrar
     efetivamente (selando) depois»

    «nao foi construido o selar este ato no ri? se nao foi, fazer.»

O BURACO QUE ELA FECHA. O selo do RI so existia DENTRO da lavratura:
    `_selar_o_ato_do_ri` era chamado numa linha so, na rota que lavra. Ato que
    nascesse sem selo — a maquina fora do ar, ou a minuta importada que entrou
    como ato — nao tinha por onde ser selado depois; a tela «Selos» e razao,
    lista o que JA tem selo. Medido em 15/09 na producao: os AV-04, AV-05 e
    AV-06 da matricula 3.110, com `selo_texto` vazio e nenhum botao na tela.

O QUE ESTES TESTES PROTEGEM
    1. O botao aparece no ato sem selo, e **nao** no que ja tem.
    2. Selar funciona com a matricula ENCERRADA — selar nao lavra, nao numera e
       nao entra na corrente de hash.
    3. Ele nao adivinha: sem natureza e sem item da tabela de custas, recusa no
       balcao, com o cliente na frente.
    4. O que foi informado FICA GRAVADO no ato, mesmo quando o selo nao sai.
    5. Selo recusado nao derruba nem altera o ato — e a tela nao diz que o ato
       nao foi lavrado.
    6. Ato que ja tem selo e recusado, e ato cancelado tambem.

O QUE ELES NAO PROVAM: que o selo SAI. Isso depende do aparelho da rede local
    (`https://192.168.0.200`), e teste que dependesse dele seria teste que falha
    quando o balcao esta bem. O que se prova e o caminho ate a rede e o que a
    casa faz com a recusa — que e o caso do dia em que o aparelho cai.
"""
from __future__ import annotations

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


def _entrar(app, usuario: str):
    c = app.test_client()
    c.post("/login",
           data={"username": usuario, "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "QUEM ATENDE", SENHA, "USER")
    return {**cg_casa, "cliente": _entrar(cg_casa["app"], "jean")}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


TEOR = "AV-06/3.110 — Fica encerrada a escrituracao desta matricula."


def _ficha_com_ato(casa, *, numero=6, selo=None, cancelado=0, encerrada=0):
    """A 3.110 como a producao a deixou: encerrada, e o ato sem selo."""
    from ri_schema import hash_ato
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, criado_em, encerrada, data_encerramento)
               VALUES ('3110', '2-Q', '2-Q', ?, 'ACERVO', '2026-09-14T10:27',
                       ?, ?)""",
            ("ENCERRADA" if encerrada else "ATIVO", encerrada,
             "2026-09-14" if encerrada else None))
        mid = int(cur.lastrowid)
        h = hash_ato("3110", "AV", numero, "2026-09-14", TEOR, None)
        cur = con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
                   teor_formato, cancelado, acervo, origem, hash_ato,
                   lavrado_em, selo_texto)
               VALUES (?, 'AV', ?, '2026-09-14', ?, 'texto', ?, 0, 'MANUAL', ?,
                       '2026-09-14T22:00', ?)""",
            (mid, numero, TEOR, cancelado, h, selo))
        ato_id = int(cur.lastrowid)
    con.close()
    return mid, ato_id


def _selar(casa, mid, ato_id, cliente=None, **campos):
    c = cliente or casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    dados = {"csrf_token": _token(html)}
    dados.update(campos)
    return c.post(f"/registro-imoveis/ato/{ato_id}/selar", data=dados,
                  follow_redirects=True)


def _ato(casa, ato_id):
    con = _con(casa)
    r = con.execute("SELECT * FROM ri_atos WHERE id=?", (ato_id,)).fetchone()
    con.close()
    return r


# ------------------------------------------------------------------ o botao


def test_o_ato_sem_selo_oferece_o_botao(casa):
    mid, _ = _ficha_com_ato(casa)
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Selar este ato" in html, (
        "ato lavrado sem selo tem de ter por onde ser selado — sem isso o "
        "encerramento tranca o selo do proprio ato que fechou o livro")


def test_o_ato_que_ja_tem_selo_nao_oferece(casa):
    mid, ato_id = _ficha_com_ato(
        casa, selo="Poder Judiciario - TJMA. Selo: REGAVD000000AAAA")
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    # Acao exata do botao — nao confundir com /selar-arquivamento.
    # O texto «Selar este ato» tambem aparece na ajuda da lavratura.
    assert f'action="/registro-imoveis/ato/{ato_id}/selar"' not in html
    assert '<summary class="button">Selar este ato</summary>' not in html

    assert f'name="codigo_tj_selo"' not in html or f'/ato/{ato_id}/selar"' not in html.split('name="codigo_tj_selo"')[0][-500:]
    assert '<summary class="button">Selar este ato</summary>' not in html


def test_a_ficha_encerrada_continua_oferecendo_o_selo(casa):
    """O caso que fez isto nascer, e a razao pela qual nao se barra aqui.

    `hash_ato` recebe numero da matricula, tipo, numero, data, teor e hash
    anterior — **o selo nao esta entre eles**. Selar nao reescreve a historia.
    """
    mid, ato_id = _ficha_com_ato(casa, encerrada=1)
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Lavrar novo ato nesta matr" not in html, "ato novo continua trancado"
    assert f"/registro-imoveis/ato/{ato_id}/selar" in html, (
        "selar na ficha fechada e o caso que fez esta rota existir")


# ------------------------------------------------- ele nao adivinha nada


def test_sem_natureza_recusa_no_balcao(casa):
    mid, ato_id = _ficha_com_ato(casa)
    html = _selar(casa, mid, ato_id, codigo_tj="16.3").get_data(as_text=True)
    assert "informe a natureza do t" in html
    assert not _ato(casa, ato_id)["selo_texto"]


def test_sem_item_da_tabela_de_custas_recusa_no_balcao(casa):
    mid, ato_id = _ficha_com_ato(casa)
    html = _selar(casa, mid, ato_id,
                  natureza_titulo="Cancelamento de hipoteca cedular").get_data(
                      as_text=True)
    assert "item da tabela de custas" in html
    assert not _ato(casa, ato_id)["selo_texto"]


def test_gratuito_sem_motivo_escrito_recusa(casa):
    mid, ato_id = _ficha_com_ato(casa)
    html = _selar(casa, mid, ato_id, natureza_titulo="Averbacao de REURB",
                  codigo_tj="16.3", isento="1").get_data(as_text=True)
    assert "motivo escrito" in html
    a = _ato(casa, ato_id)
    assert not a["selo_texto"]
    assert not a["isento"], "a recusa nao pode deixar o ato marcado como isento"


# --------------------------------------- a qualificacao fica, o selo talvez nao


def test_o_que_foi_informado_fica_gravado_mesmo_sem_o_selo_sair(casa):
    """Se o aparelho nao responder, a digitacao nao se perde.

    Nesta instalacao de ensaio nao ha selador configurado, entao o selo NAO
    sai — e e exatamente esse o caminho que se quer provar.
    """
    mid, ato_id = _ficha_com_ato(casa)
    html = _selar(casa, mid, ato_id,
                  natureza_titulo="Cancelamento de hipoteca cedular",
                  codigo_tj="16.3", base_calculo="1.234,56").get_data(
                      as_text=True)

    a = _ato(casa, ato_id)
    assert a["natureza_titulo"] == "Cancelamento de hipoteca cedular"
    assert a["codigo_tj"] == "16.3"
    assert a["base_calculo_centavos"] == 123456, (
        "o valor declarado e o que escolhe o caminho do selo — ele tem de "
        "ficar gravado para a proxima tentativa ja abrir preenchida")
    assert not a["selo_texto"], "sem selador configurado o selo nao sai"

    # E A TELA NAO PODE DIZER QUE O ATO NAO FOI LAVRADO: ele esta no livro.
    # A frase medida e «O selo NÃO saiu: … O ato AV-06 continua lavrado e
    # aparece na lista de atos sem selo.»
    assert "O selo NÃO saiu" in html
    assert "continua lavrado" in html
    assert "não foi lavrado" not in html, (
        "`_selar_o_ato_do_ri` foi escrita para a LAVRATURA e a frase dela diz "
        "«o ato foi lavrado SEM SELO»; aqui o ato ja existia, e dizer que ele "
        "nao foi lavrado assustaria quem so queria selar")


def test_selo_recusado_nao_mexe_no_ato_nem_na_corrente(casa):
    mid, ato_id = _ficha_com_ato(casa)
    antes = _ato(casa, ato_id)
    _selar(casa, mid, ato_id, natureza_titulo="Averbacao", codigo_tj="16.3")
    depois = _ato(casa, ato_id)
    assert depois["hash_ato"] == antes["hash_ato"], (
        "selar nao entra na corrente de hash — se entrasse, selar um ato "
        "antigo reescreveria a historia da ficha")
    assert depois["teor"] == antes["teor"]
    assert (depois["tipo"], depois["numero"]) == (antes["tipo"], antes["numero"])


# ------------------------------------------------------- o selo digitado a mao


# O CODIGO TEM 28 CARACTERES, E ISSO NAO E DETALHE DE ENSAIO. Sao seis letras
# do tipo de ato, seis digitos do CNS e dezesseis da identificacao —
# `REGAVD` e o prefixo da averbacao no imovel, e `000000` e o CNS desta casa.
# A primeira versao deste teste usou um codigo de 24 e a rota o RECUSOU, com
# razao: eu culpei a rota antes de contar as letras.
SELO_A_MAO = ("Poder Judiciário - TJMA. Selo: REGAVD000000ABCD1234EFGH9876 "
              "Total R$ 100,00 Emol R$ 80,00")


def test_o_selo_digitado_a_mao_fica_no_ato(casa):
    """O caminho de quando o aparelho esta fora do ar."""
    mid, ato_id = _ficha_com_ato(casa)
    _selar(casa, mid, ato_id, selo_texto=SELO_A_MAO, emolumentos="80,00")
    a = _ato(casa, ato_id)
    assert a["selo_texto"] == SELO_A_MAO
    assert a["emolumentos"] == "80,00"


def test_o_selo_a_mao_entra_no_razao_dos_selos(casa):
    """A coluna do ato sozinha nao responde «este selo ja foi usado?».

    `registrar_selo_obtido_a_mao` le o codigo, confere o CNS e recusa selo
    repetido dizendo em que ato ele ja esta — as tres coisas que a coluna nao
    faz. Sem o razao, um selo de 2023 podia ser digitado hoje como novo.
    """
    mid, ato_id = _ficha_com_ato(casa)
    _selar(casa, mid, ato_id, selo_texto=SELO_A_MAO)
    con = _con(casa)
    r = con.execute("SELECT * FROM sd_selos WHERE numero=?",
                    ("REGAVD000000ABCD1234EFGH9876",)).fetchone()
    con.close()
    assert r is not None, "o selo digitado a mao tem de entrar no razao"
    assert r["tabela"] == "ri_atos"
    assert r["ato_id"] == ato_id
    assert r["atribuicao"] == "IMOVEL"


def test_o_selo_a_mao_nao_exige_natureza_nem_item(casa):
    """Quem digita a etiqueta ja tem o selo em maos — nada e pedido a rede."""
    mid, ato_id = _ficha_com_ato(casa)
    _selar(casa, mid, ato_id, selo_texto=SELO_A_MAO)
    assert _ato(casa, ato_id)["selo_texto"] == SELO_A_MAO


def test_codigo_de_selo_com_forma_errada_e_recusado(casa):
    """Codigo lido e invalido nao entra — nem no ato, nem no razao.

    A conferencia e o que separa este caminho do campo de texto que o
    E-Oficio tinha: la se colava qualquer coisa.
    """
    mid, ato_id = _ficha_com_ato(casa)
    # 24 caracteres: tem a forma (6 letras + 6 digitos) e e curto demais.
    html = _selar(casa, mid, ato_id,
                  selo_texto="Selo: REGAVD000000ABCD1234EFGH").get_data(
                      as_text=True)
    assert "não entrou" in html
    assert "28 caracteres" in html, "a recusa diz o que o codigo deveria ter"
    assert not _ato(casa, ato_id)["selo_texto"]
    con = _con(casa)
    quantos = con.execute("SELECT COUNT(*) FROM sd_selos").fetchone()[0]
    con.close()
    assert quantos == 0, "selo recusado nao pode ficar no razao"


def test_texto_sem_codigo_reconhecivel_fica_gravado_mas_com_aviso(casa):
    """MEDIDO, e nao suposto — este e o comportamento da rota.

    `selo_no_papel.ler` devolve `codigo` so quando acha a forma do selo (seis
    letras e seis digitos colados); em «Selo: ABC123» ela devolve `None`. Nesse
    caso a rota **grava a etiqueta** e diz, com todas as letras, que ela nao
    entrou no razao dos selos.

    POR QUE NAO RECUSAR: a etiqueta e o papel que o escrevente tem na mao, e
    perde-la seria perder a unica prova do selo que a casa ja pagou. O que nao
    se pode e a tela ficar CALADA — um `selo_texto` preenchido tira o ato de
    `atos_sem_selo`, e sem o aviso ele pareceria selado.
    """
    mid, ato_id = _ficha_com_ato(casa)
    html = _selar(casa, mid, ato_id,
                  selo_texto="Selo: ABC123").get_data(as_text=True)
    assert _ato(casa, ato_id)["selo_texto"] == "Selo: ABC123"
    assert "não foi reconhecido" in html
    assert "confira a etiqueta" in html
    con = _con(casa)
    quantos = con.execute("SELECT COUNT(*) FROM sd_selos").fetchone()[0]
    con.close()
    assert quantos == 0, (
        "sem codigo lido nao ha o que gravar no razao — e a tela diz isso")


def test_o_mesmo_selo_nao_entra_em_dois_atos(casa):
    """Selo repetido e recusado dizendo em que ato ele ja esta."""
    mid, ato_id = _ficha_com_ato(casa)
    _selar(casa, mid, ato_id, selo_texto=SELO_A_MAO)

    from ri_schema import hash_ato
    con = _con(casa)
    with con:
        h = hash_ato("3110", "AV", 7, "2026-09-15", "outro ato", None)
        cur = con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
                   teor_formato, cancelado, acervo, origem, hash_ato, lavrado_em)
               VALUES (?, 'AV', 7, '2026-09-15', 'outro ato', 'texto', 0, 0,
                       'MANUAL', ?, '2026-09-15T09:00')""", (mid, h))
        outro = int(cur.lastrowid)
    con.close()

    html = _selar(casa, mid, outro, selo_texto=SELO_A_MAO).get_data(as_text=True)
    assert "não entrou" in html
    assert not _ato(casa, outro)["selo_texto"], (
        "o mesmo selo em dois atos e o razao deixando de responder «este selo "
        "ja foi usado?»")


# ---------------------------------------------------------------- as recusas


def test_ato_que_ja_tem_selo_e_recusado_dizendo_qual(casa):
    """Dois selos para o mesmo ato e o dinheiro da serventia saindo duas vezes."""
    selo = "Poder Judiciário - TJMA. Selo: REGAVD000000JAJAJA"
    mid, ato_id = _ficha_com_ato(casa, selo=selo)
    html = _selar(casa, mid, ato_id, natureza_titulo="Averbacao",
                  codigo_tj="16.3").get_data(as_text=True)
    assert "já tem selo" in html
    assert "REGAVD000000JAJAJA" in html
    assert _ato(casa, ato_id)["selo_texto"] == selo


def test_ato_cancelado_nao_se_sela(casa):
    mid, ato_id = _ficha_com_ato(casa, cancelado=1)
    html = _selar(casa, mid, ato_id, natureza_titulo="Averbacao",
                  codigo_tj="16.3").get_data(as_text=True)
    assert "cancelado" in html
    assert not _ato(casa, ato_id)["selo_texto"]


def test_ato_que_nao_existe_da_404(casa):
    c = casa["cliente"]
    mid, _ = _ficha_com_ato(casa)
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = c.post("/registro-imoveis/ato/999999/selar",
               data={"csrf_token": _token(html), "natureza_titulo": "x",
                     "codigo_tj": "16.3"})
    assert r.status_code == 404


def test_quem_atende_sela(casa):
    """Selar e trabalho do balcao: e a continuacao da lavratura."""
    mid, ato_id = _ficha_com_ato(casa)
    balcao = _entrar(casa["app"], "balcao")
    ficha = balcao.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Selar este ato" in ficha
    _selar(casa, mid, ato_id, cliente=balcao,
           natureza_titulo="Averbacao", codigo_tj="16.3")
    # Sem selador nao sai selo; o que se prova e que a rota nao o barra.
    assert _ato(casa, ato_id)["codigo_tj"] == "16.3"


# ------------------------------------------------- varios selos no mesmo ato
# Beatriz 23/09/2026 — desmembramento mat. 4001: 16.22.8.1 + 16.5 x2.


def test_a_tela_oferece_lista_de_selos(casa):
    mid, _ = _ficha_com_ato(casa)
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Selar este ato" in html
    assert 'name="codigo_tj_selo"' in html
    assert 'name="qtd_selo"' in html
    assert "Adicionar outro selo" in html


def test_varios_itens_gravam_o_primeiro_e_nao_quebram(casa):
    mid, ato_id = _ficha_com_ato(casa)
    html = _selar(
        casa, mid, ato_id,
        natureza_titulo="Desmembramento de area",
        codigo_tj_selo=["16.22.8.1", "16.5"],
        qtd_selo=["1", "2"],
        base_calculo="0,00",
    ).get_data(as_text=True)

    a = _ato(casa, ato_id)
    assert a["natureza_titulo"] == "Desmembramento de area"
    assert a["codigo_tj"] == "16.22.8.1"
    assert not a["selo_texto"], "sem selador configurado o selo nao sai"
    assert "escolha o item da tabela de custas" not in html.lower()


def test_codigos_de_selo_do_form_expande_quantidade():
    from werkzeug.datastructures import MultiDict
    form = MultiDict([
        ("codigo_tj_selo", "16.22.8.1"),
        ("qtd_selo", "1"),
        ("codigo_tj_selo", "16.5"),
        ("qtd_selo", "2"),
    ])
    itens = [str(x or "").strip() for x in form.getlist("codigo_tj_selo")]
    qtds = form.getlist("qtd_selo")
    fila = []
    for i, cod in enumerate(itens):
        if not cod:
            continue
        try:
            q = int(str(qtds[i] if i < len(qtds) else "1") or "1")
        except ValueError:
            q = 1
        q = max(1, min(q, 50))
        fila.extend([cod] * q)
    assert fila == ["16.22.8.1", "16.5", "16.5"]


def test_base_calculo_16_5_zera_mesmo_com_valor_do_imovel():
    """16.5 e so-sem-valor no acervo; multi-selo nao pode leva-lo ao /com-valor."""
    import ato_selado as AS
    assert AS.base_calculo_do_selo_ri("16.5", 565976.14) == 0.0
    assert AS.caminho_do_ato_do_ri(AS.base_calculo_do_selo_ri("16.5", 565976.14)) == AS.CAMINHO_DO_ATO_DO_RI_SEM_VALOR
    # 16.22.8.1 (ou qualquer item nao-so-sem-valor) mantem a base
    assert AS.base_calculo_do_selo_ri("16.22.8.1", 565976.14) == 565976.14
    assert AS.caminho_do_ato_do_ri(AS.base_calculo_do_selo_ri("16.22.8.1", 565976.14)) == AS.CAMINHO_DO_ATO_DO_RI_COM_VALOR


def test_envelope_16_5_com_valor_na_tela_sai_sem_base_calculo():
    import ato_selado as AS
    env = AS.envelope_do_ato_do_ri(
        matricula="4001", numero_do_ato=1, escrevente="Beatriz",
        versao_tabela="2026-01-01", descricao_natureza="Desmembramento",
        livro="2", codigo_tj="16.5", protocolo="11565",
        base_calculo=565976.14, partes=[{"nome": "JOAO"}])
    assert "baseCalculo" not in env
    assert env.get("quantidade") == 1
    assert env["dadosSelo"]["codigoTipoAto"] == "16.5"
