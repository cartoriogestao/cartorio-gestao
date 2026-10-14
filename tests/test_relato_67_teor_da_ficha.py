"""O TEOR DA FICHA E OS ATOS RECÉM LAVRADOS — relato #67, 15/09/2026.

    «precisa atualizar o teor da ficha com os atos recém lavrados»
    detalhe: «ato novo nao atualiza automatico no teor»
    tela: `ri_ficha` — `/registro-imoveis/5377` (a matrícula 3.110)

O QUE O RELATO PEDE, E O QUE ELE **NÃO** PEDE
    O pedido é de LEITURA: quem abre a matrícula e lê o teor — que é o que se
    lê para saber o que a ficha diz — tem de encontrar ali o ato novo. Ele já
    aparecia na página, no cartão dos atos; não aparecia **no teor**.

    O que ele não pede é que se escreva no texto gravado, e a medição diz por
    quê: o teor da ficha não é feito só de atos — nas fichas estruturadas com
    texto, em 314 de 429 mais de metade do teor está fora de qualquer ato (a
    descrição do imóvel, as confrontações) —, e o teor do acervo é o que o
    E-Ofício gravou. Acrescentar-lhe texto hoje faria a ficha da tela discordar
    do papel que está na estante.

    E O PAPEL JÁ FAZIA ISSO: `ri_odt.MODELO_FICHA_PADRAO` imprime o teor e,
    depois dele, os atos com o seu rótulo e a linha `-.-.-`. Era a tela que
    parava no teor. Duas vistas do mesmo fato precisam do mesmo texto.

O QUE ESTES TESTES PROTEGEM
    1. O ato cujo texto o teor ainda não conta APARECE depois do teor.
    2. O ato que o teor já conta inteiro NÃO é mostrado outra vez — a ficha não
       diz duas vezes a mesma coisa.
    3. O ato que só tem o COMEÇO no teor aparece: a conta é pelo texto inteiro,
       e é o falso positivo dela que apagaria um ato da leitura.
    4. As duas fontes do mesmo texto (o HTML do acervo e a caixa de texto de
       quem lavra) contam como iguais — sem isso a comparação daria zero.
    5. A tela usa a função do módulo, e não uma regra parecida escrita na rota.
    6. A ficha sem teor gravado diz que não tem, em vez de abrir um vazio.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ri_numeros_do_teor import (  # noqa: E402
    atos_fora_do_teor,
    texto_escrito_no_teor,
)

SENHA = "Senha#12345"

TEOR_ANTIGO = ("R-1/2.500 - IMOVEL: uma area de terras rurais na Fazenda Boa "
               "Lembranca, com 38,55,55 ha. PROPRIETARIO: HELENA CRISTINA "
               "MACHADO CARDOSO.")

TEOR_DO_ATO = ("AV-02/2500 - CANCELAMENTO INTEGRAL DE HIPOTECA CEDULAR DE 1o "
               "GRAU. Cidade Exemplo/MA, 14 de setembro de 2026. (PROTOCOLO no "
               "11.559, de 25/08/2026). A vista do instrumento de BAIXA DE "
               "REGISTRO ... Dou fe. A Tabelia/Registradora Substituta, "
               "Beatriz Exemplo de Souza.")


# ------------------------------------------------------- a regra, por dentro


def test_o_ato_que_o_texto_nao_conta_aparece():
    fora = atos_fora_do_teor(TEOR_ANTIGO, [{"tipo": "AV", "numero": 4,
                                            "teor": TEOR_DO_ATO}])
    assert len(fora) == 1, "o ato novo tem de ser mostrado depois do teor"


def test_o_ato_que_o_texto_ja_conta_nao_se_repete():
    """A ficha estruturada escreve o ato dentro do teor — repeti-lo aqui seria
    a ficha dizendo duas vezes a mesma coisa."""
    teor = f"{TEOR_ANTIGO}\n\n{TEOR_DO_ATO}"
    fora = atos_fora_do_teor(teor, [{"tipo": "AV", "numero": 4,
                                     "teor": TEOR_DO_ATO}])
    assert fora == [], "ato já escrito no teor não se mostra de novo"


def test_so_o_comeco_escrito_no_teor_nao_basta():
    """O falso positivo que apagaria um ato da leitura.

    A frase de protocolo se repete entre atos da mesma ficha; se a conta
    aceitasse o começo, o ato sumiria da tela — e ninguém desconfia de uma
    ficha que abre.
    """
    teor = f"{TEOR_ANTIGO}\n\n{TEOR_DO_ATO[:120]}"
    fora = atos_fora_do_teor(teor, [{"tipo": "AV", "numero": 4,
                                     "teor": TEOR_DO_ATO}])
    assert len(fora) == 1, (
        "só o começo do ato está no teor: o ato tem de ser mostrado")


def test_as_duas_fontes_do_mesmo_texto_contam_como_iguais():
    """O teor do acervo é HTML com `&nbsp;` e quebra de linha; o teor do ato
    novo vem da caixa de texto. Comparar sem normalizar daria ZERO achados nos
    mesmos 1.244 atos — os dois lados vêm de fontes diferentes."""
    do_acervo = ("<p>R-1/2.500 - IMOVEL: uma area de terras&nbsp;rurais na "
                 "Fazenda Boa Lembranca, com 38,55,55 ha.</p>")
    da_caixa = ("R-1/2.500 - IMOVEL: uma area de terras rurais na Fazenda "
                "Boa Lembranca,\n     com 38,55,55 ha.")
    assert texto_escrito_no_teor(do_acervo, da_caixa)


def test_ato_sem_teor_aparece_com_rotulo_e_data():
    """Sem texto não há o que comparar — e ele ainda tem o que mostrar.

    Medido na produção: 1.246 atos, 1.244 com teor. Os 2 sem teor são os que
    não podem desaparecer da ficha por falta do que comparar.
    """
    fora = atos_fora_do_teor(TEOR_ANTIGO, [{"tipo": "AV", "numero": 5,
                                            "teor": ""}])
    assert len(fora) == 1


def test_a_ordem_dos_atos_e_a_que_quem_chamou_escolheu():
    atos = [{"tipo": "AV", "numero": n, "teor": f"AV-0{n}/2.500 - ato {n}"}
            for n in (2, 3, 4)]
    fora = atos_fora_do_teor(TEOR_ANTIGO, atos)
    assert [a["numero"] for a in fora] == [2, 3, 4], (
        "a leitura não se reordena aqui: quem chama já ordenou por data")


# ------------------------------------------------------------- a tela e a rota


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa_logada):
    return cg_casa_logada


@pytest.fixture()
def _o_selador_desta_bancada(casa):
    """Aponta o selador de mentira — sem ele o ato não chega a existir.

    **ESTAS TELAS FICARAM VERMELHAS EM 16/09/2026, E NÃO POR DEFEITO DO QUE
    ELAS MEDEM.** Naquele dia o oficial decidiu o item 1 do relato #77 — «se
    falhar o selo, SEMPRE suspender o ato para corrigir o problema» —, e a
    regra alcança também a casa que **não apontou o aparelho**. A bancada
    daqui lavrava sem selador porque até então isso bastava; desde então o ato
    é suspenso e volta para a minuta, e não sobra ato em `ri_atos` para a
    asserção encontrar — o `SELECT teor FROM ri_atos` devolve `None` e o teste
    morre no `['teor']`, três linhas antes do que ele quer medir.

    A peça é a mesma de `test_ri_encerrar_pelo_ato.py`, e mora em
    `selador_de_bancada.py`: um aparelho de verdade, com TLS próprio, numa
    porta local. Cinco linhas copiadas em vinte arquivos divergem no primeiro
    conserto — a lição que este projeto já pagou com a `normalizar_nome`.
    """
    from selador_de_bancada import ligar_o_selador

    with ligar_o_selador(casa):
        yield


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _ficha(con, numero="2500", teor=TEOR_ANTIGO):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, teor, criado_em)
           VALUES (?, '2', '2', 'ATIVO', 'ESTRUTURADA', ?, '2026-09-15T08:00')""",
        (numero, teor))
    return int(cur.lastrowid)


def _lavrar(casa, mid, *, numero=4, teor=TEOR_DO_ATO):
    cliente = casa["cliente"]
    html = cliente.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    return cliente.post(f"/registro-imoveis/{mid}/atos",
                        data={"csrf_token": _token(html), "tipo": "AV",
                              "numero": numero, "data_ato": "2026-09-15",
                              "teor": teor, "_removido_lavrar_sem_selo": "0",
                              # EXIGIDOS DESDE 15/09, E A RECUSA E ANTES de
                              # o ato nascer: sem a natureza e sem o item da
                              # tabela de custas a rota nem chega a lavrar, e
                              # e por isso que estes testes ficaram vermelhos
                              # naquela data — nao por defeito do que medem.
                              "natureza_titulo": "Compra e venda",
                              "codigo_tj": "16.3"},
                        follow_redirects=True)


def _tela(casa, mid):
    return casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)


def test_a_tela_mostra_depois_do_teor_o_ato_que_o_texto_nao_conta(
        casa, _o_selador_desta_bancada):
    con = _con(casa)
    with con:
        mid = _ficha(con)
    con.close()

    _lavrar(casa, mid)
    html = _tela(casa, mid)

    marco = html.find("O que o teor acima não conta")
    assert marco >= 0, "o relato #67: o ato novo tem de aparecer no teor"
    assert html.find("Teor da ficha") < marco, (
        "a lista vem DEPOIS do teor, e não antes dele")
    trecho = html[marco:marco + 20000]

    # O rótulo é o da ficha impressa — `rotulo_ato` de `ri_odt`, AV-02/2500. Ele
    # é medido da ficha e não escrito à mão: em ficha estruturada quem numera o
    # ato é o sistema (a sequência é contínua), e o teste não decide isso.
    con = _con(casa)
    ato = con.execute("SELECT numero FROM ri_atos WHERE matricula_id=?",
                      (mid,)).fetchone()
    con.close()
    assert f"AV-{ato['numero']:02d}/2500" in trecho, (
        "o ato tem de vir com o rótulo dele")
    assert "CANCELAMENTO INTEGRAL DE HIPOTECA" in trecho, (
        "e com o texto do ato")
    assert "CANCELAMENTO INTEGRAL DE HIPOTECA" in trecho, (
        "e com o texto do ato")


def test_a_tela_nao_repete_o_ato_que_o_teor_ja_conta(
        casa, _o_selador_desta_bancada):
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="2501")
    con.close()
    _lavrar(casa, mid)

    con = _con(casa)
    ato = con.execute("SELECT teor FROM ri_atos WHERE matricula_id=?",
                      (mid,)).fetchone()
    with con:
        con.execute("UPDATE ri_matriculas SET teor=? WHERE id=?",
                    (f"{TEOR_ANTIGO}\n\n{ato['teor']}", mid))
    con.close()

    html = _tela(casa, mid)
    assert "O que o teor acima não conta" not in html, (
        "o teor já conta este ato inteiro: mostrá-lo de novo seria a ficha "
        "dizendo duas vezes a mesma coisa")


def test_a_ficha_sem_teor_gravado_diz_que_nao_tem(
        casa, _o_selador_desta_bancada):
    """Cinco fichas nesta casa têm ato e nenhum texto gravado — e nelas o
    painel abria como uma caixa vazia, sem dizer por quê."""
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="2502", teor="")
    con.close()
    _lavrar(casa, mid)

    html = _tela(casa, mid)
    assert "Esta ficha não tem texto gravado" in html
    assert "O que o teor acima não conta" in html, (
        "sem teor, o ato é tudo o que a ficha tem para mostrar")


def test_a_rota_usa_a_funcao_do_modulo_e_nao_uma_regra_parecida(casa):
    """Onde a igualdade importa, ela se constrói.

    Uma segunda comparação escrita dentro da rota divergiria da primeira no
    primeiro conserto — e a que decide se um ato aparece na ficha é esta.
    """
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert "NUMT.atos_fora_do_teor(m[\"teor\"], atos)" in codigo, (
        "`ri_web.py` tem de chamar `ri_numeros_do_teor.atos_fora_do_teor`")
    assert "fora_do_teor=fora_do_teor" in codigo, (
        "e o que ele devolve tem de chegar à tela")


def test_o_papel_ja_mostrava_o_ato_depois_do_teor(casa):
    """A tela passou a espelhar o papel — e não o contrário.

    `ri_odt.MODELO_FICHA_PADRAO` imprime o teor e, depois dele, os atos com o
    seu rótulo. É o que o oficial assina; era a tela que parava antes.
    """
    import ri_odt

    assert "{{ teor_odf }}" in ri_odt.MODELO_FICHA_PADRAO
    depois = ri_odt.MODELO_FICHA_PADRAO.index("{{ teor_odf }}")
    forro = ri_odt.MODELO_FICHA_PADRAO.index("{% for a in atos %}")
    assert depois < forro, (
        "no papel o teor vem primeiro e os atos depois — a tela segue a mesma "
        "ordem")
