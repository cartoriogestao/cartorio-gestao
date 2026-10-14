"""O ATO VOLTA PARA A MINUTA DE ONDE SAIU — 15/09/2026.

    «devolva o av-05 pra minuta, ele esta sem selo, mas como lavrado»
                                                            — o oficial

A AV-05 da 3.110 tinha nascido de uma minuta: `ri_minutas.id=2`, marcada
`LAVRADA` e apontando para o ato 3738. Desfazer o ato **criando outra minuta**
deixaria a ficha com **duas minutas para a mesma AV-05** — uma `LAVRADA` sem
ato e outra `A_REVISAR` —, e quem abrisse não saberia qual revisar.

E A UNIDADE DO PROTOCOLO TINHA DE VOLTAR JUNTO. O item 32476 do protocolo
    2026.09.23 é «De ato sem valor declarado», quantidade 5, e marcava
    `quantidade_usada=2`: uma da AV-04 e uma da AV-05. Sem devolver, o cliente
    teria pago cinco averbações e o sistema só ofereceria três.

O QUE ESTES TESTES GUARDAM, e o que NÃO guardam. Eles guardam a **forma**: a
    minuta de origem volta em vez de duplicar, e a unidade volta quando a conta
    fecha. **E guardam a recusa**, que é a parte que mais importa — o banco não
    guarda quem gastou cada unidade, e onde a conta não fecha a ferramenta não
    devolve nada e diz por quê. Devolver no chute daria ao balcão uma unidade
    que o cliente não pagou.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_minuta as RIMIN

FERRAMENTA = RAIZ / "tools" / "atos_para_minutas_do_ri.py"


# SEM SELADOR NAO SE LAVRA NADA desde 16/09/2026 — relato #77 mais o item 1
# («se falhar o selo, sempre suspender o ato»). Esta bancada fala de outra
# coisa; o selador esta aqui para o ato chegar a existir. Ver
# `tests/selador_de_bancada.py`.
#
# E ELE FALTAVA AQUI, e a falta nao era do teste: o ultimo caso deste arquivo
# foi escrito em 15/09, **antes** de o selo passar a suspender o ato, e
# passava porque a casa sem selador lavrava e mandava o ato para a lista de
# atos sem selo. No dia seguinte isso deixou de ser verdade, e a bancada
# ficou vermelha dizendo que «o item marcado na tela nao chegou a rota» —
# que e o defeito que ela existe para pegar, e nao o que ela estava vendo.
# Achado em 17/09/2026 ao mexer no modulo do caixa (relato #50), medindo as
# vermelhas desta arvore contra o que elas afirmam.

@pytest.fixture(autouse=True)
def _o_selador_desta_bancada(cg_casa):
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(cg_casa) as aparelho:
        yield aparelho


def _modulo():
    """Carrega a ferramenta como módulo — ela não é pacote."""
    if not FERRAMENTA.is_file():
        pytest.skip("a ferramenta não está nesta árvore")
    spec = importlib.util.spec_from_file_location("_atos_minutas", FERRAMENTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TEOR = ("AV-05/3.110 - CANCELAMENTO INTEGRAL DE HIPOTECA CEDULAR DE 2o GRAU, "
        "conforme o titulo apresentado nesta serventia.")


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _ficha(con, numero="3110"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em)
           VALUES (?, '2-Q', '2-Q', 'ATIVO', 'ACERVO', '2026-09-14T10:27')""",
        (numero,))
    return int(cur.lastrowid)


def _ato(con, matricula_id, *, numero=5, protocolo="11571",
         codigo_tj="16.22.2"):
    cur = con.execute(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
               protocolo, codigo_tj, hash_ato, origem, lavrado_em)
           VALUES (?, 'AV', ?, '2026-09-14', ?, ?, ?, ?, 'MANUAL',
                   '2026-09-14T22:43:07')""",
        (matricula_id, numero, TEOR, protocolo, codigo_tj,
         f"hash-de-mentira-{numero}"))
    return int(cur.lastrowid)


def _protocolo_com_item(con, *, prenotacao="11571", quantidade=5, usadas=2,
                        codigo="16.22.2", primeiro_ato=None):
    """Um protocolo do balcão amarrado a uma prenotação, com um item."""
    cur = con.execute(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao,
               situacao, origem, criado_em)
           VALUES (?, '1A', '2026-09-14', 'ABERTO', 'MANUAL',
                   '2026-09-14T09:00')""", (int(prenotacao),))
    ri_id = int(cur.lastrowid)
    cur = con.execute(
        """INSERT INTO cx_protocolos (numero, data_abertura, situacao,
               finalizado, gratuito, deposito_previo, origem, criado_em,
               tipo, ri_protocolo_id)
           VALUES ('2026.09.23', '2026-09-14', 'A_PAGAR', 0, 0, '0,00',
                   'MANUAL', '2026-09-14T09:00', 'IMOVEL', ?)""", (ri_id,))
    prot_id = int(cur.lastrowid)
    cur = con.execute(
        """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato,
               quantidade, quantidade_usada, usado_em, usado_por_ato_id,
               usado_por_tabela)
           VALUES (?, 'De ato sem valor declarado', ?, ?, ?,
                   '2026-09-15T17:34:08', ?, 'ri_atos')""",
        (prot_id, codigo, quantidade, usadas, primeiro_ato))
    return int(cur.lastrowid)


# ------------------------------------------- a minuta de origem volta, e uma só


def test_o_ato_volta_para_a_minuta_de_onde_saiu(cg_casa):
    """Ela vira A_REVISAR de novo — e nenhuma segunda minuta nasce."""
    mod = _modulo()
    con = _con(cg_casa)
    with con:
        mid = _ficha(con)
        minuta_id = RIMIN.criar(
            con, matricula_id=mid, tipo="AV", numero_pretendido=5, teor=TEOR,
            agora="2026-09-15T08:00", origem=RIMIN.IMPORTACAO,
            origem_chave="minutas para finalizar/AV-05.docx")
        ato_id = _ato(con, mid)
        RIMIN.marcar_lavrada(con, minuta_id, ato_id=ato_id,
                             agora="2026-09-15T09:00")

    antes = list(con.execute("SELECT id FROM ri_minutas WHERE matricula_id=?",
                             (mid,)))
    assert len(antes) == 1

    ato = con.execute("SELECT * FROM ri_atos WHERE id=?", (ato_id,)).fetchone()
    with con:
        de_onde = con.execute("SELECT id FROM ri_minutas WHERE ato_id=?",
                              (ato_id,)).fetchone()
        assert de_onde is not None, (
            "o ato nasceu de uma minuta e ela tem de apontar para ele")
        con.execute(
            """UPDATE ri_minutas SET situacao='A_REVISAR', ato_id=NULL
                WHERE id=?""", (int(de_onde["id"]),))
        mod._limpar_o_que_ficou_do_ato(con, ato, "2026-09-15T21:48", [])

    depois = list(con.execute(
        "SELECT id, situacao, ato_id FROM ri_minutas WHERE matricula_id=?",
        (mid,)))
    assert len(depois) == 1, (
        f"nasceu uma segunda minuta para a mesma AV-05: {[dict(d) for d in depois]}")
    assert depois[0]["id"] == minuta_id
    assert depois[0]["situacao"] == RIMIN.A_REVISAR
    assert depois[0]["ato_id"] is None
    assert not list(con.execute("SELECT 1 FROM ri_atos WHERE id=?", (ato_id,)))
    con.close()


# ------------------------------------------------ a unidade do protocolo volta


def test_a_unidade_do_protocolo_volta_quando_a_conta_fecha(cg_casa):
    """Dois atos vivos e duas unidades gastas: tirar um devolve uma."""
    mod = _modulo()
    con = _con(cg_casa)
    with con:
        mid = _ficha(con)
        av4 = _ato(con, mid, numero=4)
        av5 = _ato(con, mid, numero=5)
        item = _protocolo_com_item(con, usadas=2, primeiro_ato=av4)

    ato = con.execute("SELECT * FROM ri_atos WHERE id=?", (av5,)).fetchone()
    devolvidas: list[str] = []
    with con:
        mod._limpar_o_que_ficou_do_ato(con, ato, "2026-09-15T21:48", devolvidas)

    r = con.execute("""SELECT quantidade_usada, usado_por_ato_id
                         FROM cx_protocolo_atos WHERE id=?""", (item,)).fetchone()
    assert r["quantidade_usada"] == 1, "a unidade da AV-05 não voltou"
    assert r["usado_por_ato_id"] == av4, (
        "o rastro de quem ABRIU o consumo não se apaga — a AV-04 continua viva "
        "e continua sendo quem gastou a primeira")
    assert devolvidas and "saldo 4" in devolvidas[0], devolvidas
    con.close()


def test_o_ultimo_a_sair_apaga_o_rastro(cg_casa):
    """Com o consumo zerado, o item volta a ser um item que ninguém usou."""
    mod = _modulo()
    con = _con(cg_casa)
    with con:
        mid = _ficha(con)
        av5 = _ato(con, mid, numero=5)
        item = _protocolo_com_item(con, usadas=1, primeiro_ato=av5)

    ato = con.execute("SELECT * FROM ri_atos WHERE id=?", (av5,)).fetchone()
    with con:
        mod._limpar_o_que_ficou_do_ato(con, ato, "2026-09-15T21:48", [])

    r = con.execute("""SELECT quantidade_usada, usado_em, usado_por_ato_id
                         FROM cx_protocolo_atos WHERE id=?""", (item,)).fetchone()
    assert r["quantidade_usada"] == 0
    assert r["usado_em"] is None, (
        "item sem unidade gasta com `usado_em` preenchido é o carimbo que "
        "mente — e `_usadas` o leria como uma unidade gasta")
    assert r["usado_por_ato_id"] is None


# --------------------------------------------------- e ela RECUSA de propósito


def test_a_conta_que_nao_fecha_nao_devolve_nada(cg_casa):
    """Três unidades gastas e dois atos vivos: não dá para saber. Recusa.

    O banco **não guarda quem gastou cada unidade** — `usado_por_ato_id` é só
    o primeiro. Devolver uma no chute daria ao balcão uma averbação que o
    cliente não pagou, e o erro só apareceria no caixa.
    """
    mod = _modulo()
    con = _con(cg_casa)
    with con:
        mid = _ficha(con)
        av4 = _ato(con, mid, numero=4)
        av5 = _ato(con, mid, numero=5)
        item = _protocolo_com_item(con, usadas=3, primeiro_ato=av4)

    ato = con.execute("SELECT * FROM ri_atos WHERE id=?", (av5,)).fetchone()
    devolvidas: list[str] = []
    with con:
        mod._limpar_o_que_ficou_do_ato(con, ato, "2026-09-15T21:48", devolvidas)

    r = con.execute("SELECT quantidade_usada FROM cx_protocolo_atos WHERE id=?",
                    (item,)).fetchone()
    assert r["quantidade_usada"] == 3, "devolveu no chute"
    assert devolvidas and "ATENÇÃO" in devolvidas[0], (
        "recusar em silêncio é pior: quem lê conclui que a conta foi acertada")
    assert "não fecha" in devolvidas[0]
    con.close()


def test_ato_sem_protocolo_nao_mexe_em_item_nenhum(cg_casa):
    mod = _modulo()
    con = _con(cg_casa)
    with con:
        mid = _ficha(con)
        av5 = _ato(con, mid, numero=5, protocolo="", codigo_tj="")
        item = _protocolo_com_item(con, usadas=2, primeiro_ato=None)

    ato = con.execute("SELECT * FROM ri_atos WHERE id=?", (av5,)).fetchone()
    devolvidas: list[str] = []
    with con:
        mod._limpar_o_que_ficou_do_ato(con, ato, "2026-09-15T21:48", devolvidas)

    assert con.execute("SELECT quantidade_usada FROM cx_protocolo_atos "
                       "WHERE id=?", (item,)).fetchone()[0] == 2
    assert devolvidas == []
    con.close()


# ------------------------------------------- o que ficaria apontando para o ato


def test_a_revisao_da_ficha_nao_se_perde_nem_derruba_a_apagada(cg_casa):
    """`ato_id=NULL` é nota da matrícula — e FK apontando para ato apagado
    estoura, como estourou na 1.197 em 15/09/2026."""
    mod = _modulo()
    con = _con(cg_casa)
    with con:
        mid = _ficha(con)
        av5 = _ato(con, mid, numero=5)
        con.execute(
            """INSERT INTO ri_revisoes (matricula_id, ato_id, assunto, nota,
                   origem, situacao, anotada_em)
               VALUES (?, ?, 'area', 'conferir a area com o memorial',
                       'IMPORTACAO', 'ABERTA', '2026-09-15T08:00')""",
            (mid, av5))

    ato = con.execute("SELECT * FROM ri_atos WHERE id=?", (av5,)).fetchone()
    with con:
        mod._limpar_o_que_ficou_do_ato(con, ato, "2026-09-15T21:48", [])

    r = con.execute("SELECT ato_id, nota FROM ri_revisoes "
                    "WHERE matricula_id=?", (mid,)).fetchone()
    assert r is not None, "a nota que o importador anotou sumiu"
    assert r["ato_id"] is None
    con.close()


def test_a_ferramenta_continua_so_medindo_por_padrao():
    """Sem `--confirmar` ela não grava — e isto é o que a torna defensável."""
    codigo = FERRAMENTA.read_text(encoding="utf-8") if FERRAMENTA.is_file() else ""
    if not codigo:
        pytest.skip("a ferramenta não está nesta árvore")
    assert "--confirmar" in codigo
    assert "VACUUM INTO" in codigo, (
        "a cópia do banco é o desfazer deste passo — o projeto não tem git")


# --------------------------------- o item com saldo tem de CHEGAR a rota

def _token(html: str) -> str:
    import re
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    return achado.group(1) if achado else ""


def test_o_item_ja_comecado_continua_valendo_para_o_proximo_ato(cg_casa_logada):
    """O item de cinco averbacoes serve as cinco — e a rota tem de ve-lo.

    RELATO DO OFICIAL EM 15/09/2026, a SEGUNDA vez no mesmo dia: «preenchi
    tudo, escolhi o ato sem valor declarado (tinha 5) e deu isso».

    `ri_lavrar_ato` filtrava os itens marcados por `AND usado_em IS NULL` — a
    **terceira copia** da condicao que eu havia consertado de manha em
    `caixa_protocolo` e em `ri_lavrar_teor`. O item 32476 daquele protocolo
    tem `usado_em` preenchido desde que a AV-04 gastou a primeira unidade:
    a consulta devolvia zero linhas, e o item que ele marcou na tela **nao
    chegava a rota**. Ele entao batia na recusa do item da tabela.

    Este teste poe o item no estado da producao — `usado_em` preenchido, saldo
    de sobra — e exige que o ato seja lavrado com o codigo daquele item.
    """
    cg_casa = cg_casa_logada
    c = cg_casa["c"]

    con = _con(cg_casa)
    with con:
        mid = _ficha(con, numero="3110")
        item = _protocolo_com_item(con, usadas=1, primeiro_ato=None)
        prot = con.execute("""SELECT protocolo_id FROM cx_protocolo_atos
                               WHERE id=?""", (item,)).fetchone()["protocolo_id"]
    # O ESTADO DA PRODUCAO: uma unidade gasta, `usado_em` preenchido, saldo 4.
    marcado = con.execute("""SELECT usado_em, quantidade, quantidade_usada
                               FROM cx_protocolo_atos WHERE id=?""",
                          (item,)).fetchone()
    assert marcado["usado_em"], "o caso so existe com `usado_em` preenchido"
    assert marcado["quantidade"] - marcado["quantidade_usada"] == 4
    con.close()

    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert 'name="natureza_titulo"' in html, (
        "a rota exige a natureza — a tela tem de oferecer o campo")

    c.post(f"/registro-imoveis/{mid}/atos",
           data={"csrf_token": _token(html), "tipo": "AV", "numero": 5,
                 "data_ato": "2026-09-14",
                 "teor": TEOR,
                 "natureza_titulo": "Anuencia para baixa de hipoteca cedular",
                 "protocolo_id": prot,
                 "protocolo_item_id": item},
           follow_redirects=True)

    con = _con(cg_casa)
    ato = con.execute("SELECT * FROM ri_atos WHERE matricula_id=?",
                      (mid,)).fetchone()
    con.close()
    assert ato is not None, (
        "o ato nao foi lavrado: o item marcado na tela nao chegou a rota — "
        "e a condicao `usado_em IS NULL` esta de volta")
    assert ato["codigo_tj"] == "16.22.2", (
        f"o item do protocolo nao virou o item de custa do ato: "
        f"{ato['codigo_tj']!r}")


def test_a_rota_de_lavrar_nao_le_item_por_usado_em(cg_casa):
    """A regra do saldo mora num lugar so, e e `caixa_protocolo`.

    **VARREDOR LE CODIGO, E NAO PROSA** — o comentario que explica o conserto
    cita a condicao antiga de proposito, e por isso a leitura e por `ast`,
    sobre os literais que nao sao docstring.
    """
    import ast

    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    arvore = ast.parse(codigo)
    docstrings = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                           ast.ClassDef)) and no.body:
            primeiro = no.body[0]
            if isinstance(primeiro, ast.Expr) and \
                    isinstance(primeiro.value, ast.Constant) and \
                    isinstance(primeiro.value.value, str):
                docstrings.add(id(primeiro.value))

    achados = [n.value for n in ast.walk(arvore)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and id(n) not in docstrings
               and "usado_em IS NULL" in n.value]
    assert not achados, (
        "`ri_lavrar_ato` voltou a escolher o item do protocolo por "
        "`usado_em IS NULL` — o item de cinco averbacoes some depois da "
        "primeira. Quem responde por isso e `caixa_protocolo.itens_disponiveis`")


# ------------------------- o que recarrega a tela vem ANTES do que se digita

def test_o_protocolo_vem_antes_dos_campos_que_se_digitam():
    """Escolher o protocolo recarrega a tela e apaga o que estava escrito.

    RELATO DO OFICIAL EM 15/09/2026: «quando clica em protocolo ele zera a
    natureza do titulo que veio antes. faz mais sentido o protocolo e
    prenotacao ser em cima pra nao ocorrer de apagar parte ja preenchida».

    A CAIXA DO PROTOCOLO NAVEGA, e nao ha como ela nao navegar: e o GET que
    traz os ITENS daquele protocolo para a tabela de baixo. O navegador monta
    o formulario de novo, e o que estava digitado se perde **calado** — foi
    assim que a natureza do titulo sumiu e a rota recusou por falta de um
    campo que ele tinha preenchido.

    A ORDEM E O CONSERTO QUE NAO DEPENDE DE NINGUEM LEMBRAR. Repor valor por
    valor tambem se faz, e protege so os campos de que alguem se lembrou; a
    ordem protege **o campo que nascer amanha nesta tela**.

    Este teste guarda a ordem dentro do formulario de lavrar: tudo o que
    navega vem antes de tudo o que se escreve.
    """
    html = (RAIZ / "templates" / "ri_ficha.html").read_text(encoding="utf-8")

    inicio = html.index("url_for('ri_lavrar_ato'")
    fim = html.index("</form>", inicio)
    formulario = html[inicio:fim]

    quem_navega = formulario.index('id="protocolo-unificado-ri"')
    assert "location.href" in formulario[quem_navega:quem_navega + 4000], (
        "o bloco do protocolo deixou de navegar — se isso e deliberado, este "
        "teste e o lugar de dizer, porque a ordem existia por causa disso")

    for campo in ('name="natureza_titulo"', 'name="teor"',
                  'name="base_calculo"'):
        assert campo in formulario, f"{campo} saiu do formulario de lavrar"
        assert quem_navega < formulario.index(campo), (
            f"{campo} ficou ANTES do bloco do protocolo — escolher o "
            f"protocolo recarrega a tela, e o que estiver acima dele se "
            f"perde sem avisar")


# ------------------------------ a tela mostra o que SOBRA, e nao o que se comprou

def test_a_tela_mostra_o_saldo_do_item_e_nao_a_quantidade_comprada(cg_casa_logada):
    """Item de 5 com 3 gastas tem de aparecer como 2, e nao como 5.

    RELATO DO OFICIAL EM 15/09/2026: «selei o ato, mas o numero de atos sem
    valor declarado no protocolo permanece em 5».

    ELE ESTAVA CERTO, E O BANCO TAMBEM. Medido na producao no minuto do
    relato: o item 32476 tinha `quantidade` 5 e `quantidade_usada` 3 — saldo
    **2**, e o consumo estava sendo registrado direito. A coluna «Qtd» da
    tabela imprimia `i.quantidade`, que e a quantidade CONTRATADA e nunca
    muda: a tela dizia «5» depois da primeira averbacao e diria «5» depois da
    quinta.

    **Numero que nao se mexe numa coluna que deveria diminuir e o carimbo que
    mente** — quem le conclui que o consumo nao foi registrado, e vai
    procurar defeito onde nao ha. E o inverso tambem custa caro: no dia em que
    o saldo chegasse a zero, a tela continuaria oferecendo cinco.

    `caixa_protocolo.itens_disponiveis` ja devolvia `saldo`; era a tela que
    nao o usava.
    """
    cg_casa = cg_casa_logada
    c = cg_casa["c"]

    con = _con(cg_casa)
    with con:
        mid = _ficha(con, numero="3110")
        item = _protocolo_com_item(con, quantidade=5, usadas=3,
                                   primeiro_ato=None)
        prot = con.execute("""SELECT protocolo_id FROM cx_protocolo_atos
                               WHERE id=?""", (item,)).fetchone()["protocolo_id"]
    con.close()

    html = c.get(f"/registro-imoveis/{mid}?lavrar=1&protocolo_id={prot}"
                 ).get_data(as_text=True)

    # A LINHA DO ITEM, e nao a pagina inteira: «5» aparece em muitos lugares.
    inicio = html.find("De ato sem valor declarado")
    assert inicio > 0, ("o item nao apareceu na tela — se ele sumiu por ter "
                        "`usado_em` preenchido, o defeito de 15/09 voltou")
    linha = html[max(0, inicio - 400):inicio + 400]

    assert ">2<" in linha or ">2 " in linha or "<strong>2</strong>" in linha, (
        f"a tela nao mostra o saldo 2 do item. Trecho: {linha!r}")
    assert "de 5" in linha, (
        "o contratado deixou de aparecer ao lado — quem confere a conta do "
        "cliente precisa dos dois numeros")
