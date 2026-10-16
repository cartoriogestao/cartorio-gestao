"""A MINUTA DO ATO DO RI — pedido do oficial em 15/09/2026.

    «aquela av 4, 5 e 6 nao podem ficar como atos prontos, precisam ficar
     como atos para serem revistos e lavrados. Crie um mecanismo para
     compatibilizar isso»

    «deixe tudo pronto para comecar, revisar e encerrar qualquer ato no ri»

O QUE FEZ ISTO NASCER. A importacao das minutas em `.docx` entrou LAVRANDO: os
    AV-04, AV-05 e AV-06 da matricula 3.110 nasceram como ato definitivo —
    tomaram numero, entraram na corrente de hash e encerraram a ficha — e
    ficaram sem selo. O que ele esperava era o contrario: texto pronto
    esperando revisao, e a lavratura depois, pela tela de sempre.

O QUE ESTES TESTES PROTEGEM
    1. A minuta NAO e ato: nao aparece na ficha como ato, nao toma numero, nao
       entra na corrente de hash e nao tem selo.
    2. «Revisar e lavrar» abre o formulario de sempre com o texto dentro — e
       quem lavra e `ri_lavrar_ato`, a mesma rota. Nao ha segunda porta.
    3. Lavrada, a minuta sai da fila e **fica** amarrada ao ato que saiu dela.
    4. Ato que nao entra deixa a minuta onde estava.
    5. Descartar exige motivo escrito, e a minuta nao some.
    6. Este modulo nao lavra, nao numera, nao sela e nao cobra — varrido nos
       nomes publicos, como o das fraudes e o do CNIB.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_minuta as RIMIN

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
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "QUEM ATENDE", SENHA, "USER")
    return {**cg_casa, "cliente": _entrar(cg_casa["app"], "mario")}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


TEOR = ("AV-04/3.110 — Procede-se a esta averbacao para constar a alteracao "
        "de denominacao do imovel, conforme o titulo apresentado.")


def _ficha(con, numero="3110", tipo_ficha="ACERVO"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em)
           VALUES (?, '2-Q', '2-Q', 'ATIVO', ?, '2026-09-14T10:27')""",
        (numero, tipo_ficha))
    return int(cur.lastrowid)


def _minuta(con, matricula_id, **kw):
    campos = {"matricula_id": matricula_id, "tipo": "AV", "teor": TEOR,
              "numero_pretendido": 4, "agora": "2026-09-15T08:00",
              "origem": RIMIN.IMPORTACAO,
              "origem_chave": "minutas para finalizar/AV-04.docx",
              "natureza_titulo": "Alteracao de denominacao"}
    campos.update(kw)
    return RIMIN.criar(con, **campos)


def _casa_com_minuta(casa, **kw):
    con = _con(casa)
    with con:
        mid = _ficha(con)
        minuta_id = _minuta(con, mid, **kw)
    con.close()
    return mid, minuta_id


# ---------------------------------------------------------- ela nao e ato


def test_a_minuta_nao_e_ato_e_a_ficha_diz_isso(casa):
    """O que o oficial pediu: em pe, e NAO como ato pronto."""
    mid, _ = _casa_com_minuta(casa)
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    assert "Minutas a revisar e lavrar" in html
    assert "ainda não lavrado" in html or "ainda não lavrado" in html

    con = _con(casa)
    atos = con.execute("SELECT COUNT(*) FROM ri_atos WHERE matricula_id=?",
                       (mid,)).fetchone()[0]
    mi = con.execute("SELECT * FROM ri_minutas").fetchone()
    con.close()
    assert atos == 0, "minuta nao lavra ato"
    assert mi["situacao"] == RIMIN.A_REVISAR
    assert mi["ato_id"] is None
    # Nem numero tomado, nem corrente, nem selo: a tabela nao tem onde guardar
    # nada disso — e e essa ausencia que a separa de `ri_atos`.
    # `in` numa `sqlite3.Row` NAO olha chave — olha valor. A lista de colunas
    # sai de `.keys()`, e por isso ela vira variavel aqui.
    colunas = list(mi.keys())
    assert "hash_ato" not in colunas
    assert "selo_texto" not in colunas


def test_minuta_sem_teor_nao_entra(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con)
        with pytest.raises(RIMIN.MinutaError) as e:
            _minuta(con, mid, teor="   ")
    con.close()
    assert "teor" in str(e.value).lower()


def test_tipo_que_nao_e_ato_do_ri_nao_entra(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con)
        with pytest.raises(RIMIN.MinutaError):
            _minuta(con, mid, tipo="X")
    con.close()


# ------------------------------------------------- revisar abre o de sempre


def test_revisar_abre_o_formulario_de_lavrar_com_o_texto_dentro(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    html = casa["cliente"].get(
        f"/registro-imoveis/{mid}?minuta={minuta_id}").get_data(as_text=True)

    assert "Revisando a minuta AV-04" in html
    assert "Procede-se a esta averbacao" in html, (
        "o teor da minuta tem de vir dentro da caixa de lavrar — sem isso "
        "«revisar» e so um aviso, e o escrevente redigita o que ja existe")
    assert f'name="minuta_id" value="{minuta_id}"' in html
    assert 'value="Alteracao de denominacao"' in html
    assert 'name="numero" min="1" required\n                 value="4"' in html \
        or 'value="4"' in html
    # E a porta de lavrar continua sendo UMA: a de sempre.
    assert f'action="/registro-imoveis/{mid}/atos"' in html


def test_minuta_de_outra_ficha_nao_abre(casa):
    _, minuta_id = _casa_com_minuta(casa)
    con = _con(casa)
    with con:
        outra = _ficha(con, numero="4016")
    con.close()
    html = casa["cliente"].get(
        f"/registro-imoveis/{outra}?minuta={minuta_id}").get_data(as_text=True)
    assert "Revisando a minuta" not in html


# --------------------------------------------------------- lavrar de verdade


def _lavrar(casa, mid, minuta_id, *, numero=4, teor=None, cliente=None):
    c = cliente or casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}?minuta={minuta_id}").get_data(
        as_text=True)
    return c.post(f"/registro-imoveis/{mid}/atos",
                  data={"csrf_token": _token(html), "tipo": "AV",
                        "numero": numero, "data_ato": "2026-09-14",
                        "natureza_titulo": "Anuencia para baixa de hipoteca cedular",
                        "codigo_tj": "16.22.2",
                        "teor": teor if teor is not None else TEOR,
                        "minuta_id": minuta_id},
                  follow_redirects=True)


def test_lavrar_a_minuta_faz_o_ato_e_tira_ela_da_fila(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    html = _lavrar(casa, mid, minuta_id).get_data(as_text=True)

    con = _con(casa)
    ato = con.execute("SELECT * FROM ri_atos WHERE matricula_id=?",
                      (mid,)).fetchone()
    mi = con.execute("SELECT * FROM ri_minutas WHERE id=?",
                     (minuta_id,)).fetchone()
    con.close()

    assert ato is not None
    assert (ato["tipo"], ato["numero"]) == ("AV", 4)
    assert ato["hash_ato"], "o ato lavrado entra na corrente de hash"
    assert "Procede-se" in ato["teor"]

    # A MINUTA NAO SE APAGA AO VIRAR ATO: ela e a procedencia do teor.
    assert mi["situacao"] == RIMIN.LAVRADA
    assert mi["ato_id"] == ato["id"]
    assert mi["atualizado_em"]
    assert "Minutas a revisar e lavrar" not in html, (
        "lavrada, ela sai da fila da ficha")


def test_ato_que_nao_entra_deixa_a_minuta_onde_estava(casa):
    """A marca e na MESMA transacao do ato — e isto prova."""
    mid, minuta_id = _casa_com_minuta(casa)
    con = _con(casa)
    with con:
        # Alguem lavrou o AV-04 antes: o numero pretendido nao e reserva.
        from ri_schema import hash_ato
        con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
                   teor_formato, cancelado, acervo, origem, hash_ato, lavrado_em)
               VALUES (?, 'AV', 4, '2026-09-14', 'outro ato', 'texto', 0, 0,
                       'MANUAL', ?, '2026-09-14T22:00')""",
            (mid, hash_ato("3110", "AV", 4, "2026-09-14", "outro ato", None)))
    con.close()

    html = _lavrar(casa, mid, minuta_id).get_data(as_text=True)
    assert "já está ocupado" in html or "ja esta ocupado" in html

    con = _con(casa)
    mi = con.execute("SELECT situacao, ato_id FROM ri_minutas WHERE id=?",
                     (minuta_id,)).fetchone()
    con.close()
    assert mi["situacao"] == RIMIN.A_REVISAR, (
        "ato recusado nao pode tirar a minuta da fila — ela e o trabalho que "
        "ainda falta fazer")
    assert mi["ato_id"] is None


def test_a_mesma_minuta_nao_lavra_dois_atos(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    _lavrar(casa, mid, minuta_id, numero=4)
    resposta = _lavrar(casa, mid, minuta_id, numero=5).get_data(as_text=True)

    assert "já saiu da fila de revisão" in resposta

    con = _con(casa)
    quantos = con.execute("SELECT COUNT(*) FROM ri_atos WHERE matricula_id=?",
                          (mid,)).fetchone()[0]
    con.close()
    assert quantos == 1, "a minuta lavrada nao pode virar um segundo ato"


def test_lavrar_sem_minuta_continua_funcionando(casa):
    """O caminho normal nao muda: ato novo sem minuta nenhuma."""
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="4017")
    con.close()
    c = casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    c.post(f"/registro-imoveis/{mid}/atos",
           data={"csrf_token": _token(html), "tipo": "R", "numero": 1,
                 "data_ato": "2026-09-15", "teor": "R-01/4.017 — registro.",
                 "natureza_titulo": "Titulo de dominio",
                 "codigo_tj": "16.2"},
           follow_redirects=True)
    con = _con(casa)
    quantos = con.execute("SELECT COUNT(*) FROM ri_atos WHERE matricula_id=?",
                          (mid,)).fetchone()[0]
    con.close()
    assert quantos == 1


# ---------------------------------------------------------------- descartar


def _descartar(casa, mid, minuta_id, motivo, cliente=None):
    c = cliente or casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    return c.post(f"/registro-imoveis/minuta/{minuta_id}/descartar",
                  data={"csrf_token": _token(html), "motivo": motivo},
                  follow_redirects=True)


def test_descartar_exige_motivo_escrito(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    html = _descartar(casa, mid, minuta_id, "nao serve").get_data(as_text=True)
    assert "dez letras" in html

    con = _con(casa)
    mi = con.execute("SELECT situacao FROM ri_minutas WHERE id=?",
                     (minuta_id,)).fetchone()
    con.close()
    assert mi["situacao"] == RIMIN.A_REVISAR


def test_descartada_sai_da_fila_e_nao_some(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    html = _descartar(casa, mid, minuta_id,
                      "o titulo foi devolvido ao apresentante").get_data(
                          as_text=True)
    assert "Minutas a revisar e lavrar" not in html

    con = _con(casa)
    mi = con.execute("SELECT * FROM ri_minutas WHERE id=?",
                     (minuta_id,)).fetchone()
    con.close()
    assert mi["situacao"] == RIMIN.DESCARTADA
    assert "devolvido ao apresentante" in (mi["observacao"] or ""), (
        "o motivo fica escrito — a pergunta que aparece meses depois e «e "
        "aquela averbacao que estava para sair?»")
    assert mi["teor"], "descartar nao apaga o texto"


def test_minuta_lavrada_nao_se_descarta(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    _lavrar(casa, mid, minuta_id)
    html = _descartar(casa, mid, minuta_id,
                      "queria desfazer este ato por aqui").get_data(as_text=True)
    assert "já virou ato" in html


def test_quem_atende_nao_descarta(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    balcao = _entrar(casa["app"], "balcao")
    ficha = balcao.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    resposta = balcao.post(f"/registro-imoveis/minuta/{minuta_id}/descartar",
                           data={"csrf_token": _token(ficha),
                                 "motivo": "quero tirar esta minuta daqui"},
                           follow_redirects=False)
    assert resposta.status_code in (302, 403)
    assert "Descartar minuta" not in ficha, (
        "quem nao pode descartar tambem nao ve o botao")
    # Mas ele REVISA E LAVRA — isso e o trabalho do balcao.
    assert "Revisar e lavrar" in ficha

    con = _con(casa)
    mi = con.execute("SELECT situacao FROM ri_minutas WHERE id=?",
                     (minuta_id,)).fetchone()
    con.close()
    assert mi["situacao"] == RIMIN.A_REVISAR


def test_quem_atende_lavra_a_minuta(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    _lavrar(casa, mid, minuta_id, cliente=_entrar(casa["app"], "balcao"))
    con = _con(casa)
    mi = con.execute("SELECT situacao FROM ri_minutas WHERE id=?",
                     (minuta_id,)).fetchone()
    con.close()
    assert mi["situacao"] == RIMIN.LAVRADA


# ----------------------------------------------- a ficha encerrada e a conta


def test_ficha_encerrada_mostra_a_minuta_e_manda_reabrir(casa):
    """O caso da 3.110: fechada pela AV-06, com trabalho parado dentro."""
    mid, minuta_id = _casa_com_minuta(casa)
    con = _con(casa)
    with con:
        con.execute(
            """UPDATE ri_matriculas SET encerrada=1, situacao='ENCERRADA',
                   data_encerramento='2026-09-14' WHERE id=?""", (mid,))
    con.close()
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    assert "Minutas a revisar e lavrar" in html, (
        "minuta que a ficha encerrada esconde e trabalho que ninguem ve")
    assert "reabra para lavrar" in html
    # O QUE SE PROCURA E O LINK, E NAO A PALAVRA. A propria explicacao do
    # painel escreve «Revisar e lavrar» entre aspas — procurar a frase na
    # pagina acusaria a prosa, que e o defeito que este projeto ja apanhou
    # onze vezes em varredor.
    assert f"?minuta={minuta_id}" not in html, (
        "ficha encerrada nao oferece o caminho de lavrar — ele levaria a um "
        "formulario que a rota recusa")
    # E a frase que dizia que nem selar era possivel deixou de mentir.
    assert "Selar os que ficaram sem selo" in html


def test_a_conta_das_que_esperam(casa):
    mid, _ = _casa_com_minuta(casa)
    con = _con(casa)
    with con:
        _minuta(con, mid, numero_pretendido=5, teor=TEOR.replace("04", "05"))
        _minuta(con, mid, numero_pretendido=6, teor=TEOR.replace("04", "06"))
        outra = _ficha(con, numero="4016")
        _minuta(con, outra, numero_pretendido=1, teor=TEOR)
        assert RIMIN.quantas_a_revisar(con, mid) == 3
        assert RIMIN.quantas_a_revisar(con) == 4
    con.close()


# ------------------------------------- o modulo nao lavra, nao sela, nao cobra


def test_este_modulo_nao_lavra_nao_numera_nao_sela_e_nao_cobra():
    """A mesma regua das fraudes, do CNIB e do usucapiao.

    Duas portas para lavrar seriam duas versoes da regra que numera e sela, e
    elas divergiriam no primeiro conserto.
    """
    proibidas = ("lavrar", "selar", "numerar", "cobrar", "obter_selo",
                 "emitir", "encerrar_matricula")
    publicos = [n for n in dir(RIMIN) if not n.startswith("_")]
    achados = [n for n in publicos
               if any(p in n.lower() for p in proibidas)]
    assert not achados, (
        f"nomes publicos que parecem lavrar/selar/cobrar em ri_minuta: "
        f"{achados}. Quem lavra e `ri_lavrar_ato`.")


def test_so_a_rota_de_lavrar_aceita_minuta():
    """Nao ha segunda porta para transformar minuta em ato.

    O QUE SE VARRE E O `minuta_id`, e nao o INSERT. Eu tinha escrito o
    contrario — teto de dois INSERT em `ri_atos` — e a medicao me desmentiu:
    **sao tres**, e os tres estao certos. Lavrar ato novo, a averbacao de
    CANCELAMENTO de ato e a averbacao de ENCERRAMENTO da matricula sao tres
    atos diferentes, cada um com o seu teor e a sua natureza; obrigar os tres a
    passar por uma funcao so seria juntar o que a lei separa.

    O que a minuta nao pode ter e **duas portas para virar ato** — e essa e a
    pergunta que este varredor faz.

    E A REGUA MUDOU EM 15/09/2026, PORQUE ELA MEDIA UM NUMERO QUE SE MEXE.
        Ela contava as OCORRENCIAS de `request.form[...minuta_id]` com teto
        dois, e ficou vermelha quando a mesma rota passou a ler o campo **tres
        vezes**: uma para guardar quem volta a corrigir (`minuta_pedida`, que
        nasceu com a recusa de selo do mesmo dia), e duas no bloco que carrega
        a minuta. **Tres leituras dentro de UMA rota nao sao tres portas.**

        Agora ela conta as FUNCOES que leem o campo, que e a propriedade que
        importa: subir o teto de dois para tres teria deixado o varredor
        passando e medindo a coisa errada — e o proximo conserto o deixaria
        vermelho de novo sem que nada tivesse piorado.
    """
    import ast

    arvore = ast.parse((RAIZ / "ri_web.py").read_text(encoding="utf-8"))

    def _le_do_formulario(no) -> bool:
        """Este pedaco de arvore le `minuta_id` de `request.form`?"""
        for filho in ast.walk(no):
            if not isinstance(filho, ast.Constant) or filho.value != "minuta_id":
                continue
            return True
        return False

    rotas = [f.name for f in ast.walk(arvore)
             if isinstance(f, ast.FunctionDef) and _le_do_formulario(f)
             # so as folhas: `registrar_rotas` contem todas as rotas dentro
             and not any(isinstance(n, ast.FunctionDef) and n is not f
                         and _le_do_formulario(n) for n in ast.walk(f))]

    assert rotas, "a rota de lavrar deixou de ler a minuta"
    assert len(rotas) == 1, (
        f"{len(rotas)} rotas leem `minuta_id` de formulario ({rotas}) — cada "
        f"uma a mais e uma versao da regra que numera, entra na corrente de "
        f"hash e sela, e elas divergem no primeiro conserto")
    assert rotas[0] == "ri_lavrar_ato", (
        f"quem lavra a minuta passou a ser `{rotas[0]}` — se a mudanca e "
        f"deliberada, este teste e o lugar de dizer por que")
def test_os_tres_lugares_que_lavram_no_ri_estao_medidos():
    """Teto MEDIDO, e nao suposto: quatro seria um a explicar.

    Medido em 15/09/2026: `ri_web.py` insere em `ri_atos` em **tres** lugares —
    `ri_lavrar_ato`, `ri_cancelar_ato` (averbacao de cancelamento) e
    `ri_encerrar_matricula` (averbacao de encerramento). Nenhum outro modulo de
    tela lavra ato do RI.
    """
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert len(re.findall(r"INSERT INTO ri_atos", codigo)) == 3, (
        "o numero de lugares que lavram ato no RI mudou. Se o quarto for "
        "legitimo, mede-se e escreve-se aqui com o nome dele; se nao for, e "
        "uma segunda versao da regra que numera e entra na corrente de hash.")
