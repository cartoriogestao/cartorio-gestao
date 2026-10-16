"""O TEXTO DO ATO SAI UMA VEZ SÓ NA FICHA — relato #71, 18/09/2026.

    «mostra duas vezes as 3 averbaçoes feitas»
    tela: `ri_ficha` — `/registro-imoveis/5377` (a matrícula 3.110)
    quem: Carla Exemplo Lima, em 16/09

O QUE ACONTECEU, MEDIDO
    O relato #67 (15/09) pôs os atos que o teor ainda não conta DEPOIS do teor,
    para quem lê a ficha os encontrar — que é a ordem do papel: a ficha
    impressa (`ri_odt.MODELO_FICHA_PADRAO`) e a certidão de inteiro teor sempre
    imprimiram cada ato uma vez.

    A seção nova nasceu, e o painel do alto continuou mostrando o texto de cada
    ato: as duas vistas passaram a dizer o mesmo. Medido no HTML que o balcão
    recebe na 3.110, em 16/09: os três textos saíam duas vezes cada. Na casa
    inteira, medido em 18/09 com `tmp/ver_71_os_numeros.py`: **1.248 atos**,
    **1.246 com teor**, e o texto de cada um saía duas vezes — em **715** deles
    a segunda cópia era a seção do #67, em **290 fichas**; os outros **531**
    têm o texto escrito dentro do teor, e ali a segunda cópia era o cartão do
    próprio painel.

O DESENHO ESCOLHIDO PELO OFICIAL EM 18/09 — opção A
    O painel do alto passa a ser o ÍNDICE — rótulo, data, distintivos, o
    carimbo do selo e os botões (cancelar, selar, expurgar) —, e o TEXTO
    aparece uma vez só, na sequência do teor. Os botões ficam no alto de
    propósito: é no índice que se age sobre o ato, e mandá-los para baixo de um
    teor de 60 mil caracteres seria escondê-los.

O QUE ESTES TESTES PROTEGEM
    1. O texto do ato aparece UMA vez — é o defeito relatado.
    2. O índice diz onde ler, e o link leva a alguma coisa: âncora que não
       existe manda o leitor para o nada, e ninguém desconfia de um link.
    3. O ato que o teor já conta DIZ isso, e não ganha link — não há cartão de
       texto para onde apontar.
    4. O índice não perdeu o que ele existe para fazer: os botões.
    5. O ato sem texto gravado diz que não tem, em vez de virar cartão vazio.
    6. Nenhum cartão de texto sobra no índice (`class="teor"`): é a forma do
       defeito — o mesmo texto em dois lugares da página.

O QUE ELES **NÃO** PROTEGEM
    O carimbo do selo no índice. Ele precisa de um selo gravado em `sd_selos`,
    e o que se prova aqui é a divisão entre o índice e a sequência; do carimbo
    cuidam `test_ri_carimbo_do_selo.py` e
    `test_certidao_do_ri_carimbo_e_assinatura.py`.

    Nada disto é do PAPEL: o `.odt` sempre levou cada ato uma vez, e há
    `test_relato_79_teor_na_certidao.py` guardando o outro lado.
"""
from __future__ import annotations

import re
import sqlite3

import pytest

TEOR_DA_FICHA = ("R-1/2.500 - IMOVEL: uma area de terras rurais na Fazenda Boa "
                 "Lembranca, com 38,55,55 ha. PROPRIETARIO: BEATRIZ EXEMPLO "
                 "DE SOUZA.")

TEOR_DO_ATO = ("AV-02/2500 - CANCELAMENTO INTEGRAL DE HIPOTECA CEDULAR DE 1o "
               "GRAU. Cidade Exemplo/MA, 14 de setembro de 2026. (PROTOCOLO no "
               "11.559, de 25/08/2026). A vista do instrumento de BAIXA DE "
               "REGISTRO emitido pela Caixa, dou fe.")

# A frase que só existe no ato — é ela que se conta. Se estivesse também no
# teor da ficha, contar 1 na página não provaria nada, e é por isso que todo
# teste que conta começa conferindo que ela não está lá.
FRASE_DO_ATO = "A vista do instrumento de BAIXA DE REGISTRO"


@pytest.fixture()
def casa(cg_casa_logada):
    return cg_casa_logada


# ------------------------------------------------- o aparelho desta bancada
#
# SEM SELADOR NÃO SE LAVRA NADA desde 16/09/2026 — relato #77 mais o item 1
# («se falhar o selo, sempre suspender o ato»). Esta bancada fala de outra
# coisa: o que a FICHA mostra. O ato precisa existir para haver o que medir, e
# o aparelho de mentira é o mesmo que as outras bancadas do RI usam — uma peça
# só na casa, como manda `tests/selador_de_bancada.py`.

@pytest.fixture(autouse=True)
def _o_selador_desta_bancada(cg_casa_logada):
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(cg_casa_logada) as aparelho:
        yield aparelho


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _ficha(con, numero="4100", teor=TEOR_DA_FICHA, tipo_ficha="ESTRUTURADA"):
    """Abre uma ficha no intervalo que esta casa produz (o próximo é 4019).

    O `tipo_ficha` é parâmetro porque ele decide O SELO: em ficha de ACERVO o
    item da tabela de custas é dispensado (decisão do oficial de 16/09 — «ato
    de acerto fica sem item de custa»), e é o único caminho desta casa para um
    ato ficar lavrado SEM SELO sem a rede cair.
    """
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, teor, criado_em)
           VALUES (?, '2', '2', 'ATIVO', ?, ?, '2026-09-16T08:00')""",
        (numero, tipo_ficha, teor))
    return int(cur.lastrowid)


def _lavrar(casa, mid, *, numero=4, teor=TEOR_DO_ATO, codigo_tj="16.3"):
    """Lavra pela ROTA — o caminho que o balcão usa.

    A natureza do título é exigida desde 15/09, e a recusa é ANTES de o ato
    nascer: sem ela a rota nem chega a lavrar. O ITEM DA TABELA DE CUSTAS é
    dispensado nas fichas de ACERVO (decisão do oficial de 16/09 — «ato de
    acerto fica sem item de custa»), e é por isso que ele se pode omitir aqui:
    o ato fica lavrado e SEM SELO, que é o que ele é no papel há anos.
    """
    cliente = casa["cliente"]
    html = cliente.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    return cliente.post(f"/registro-imoveis/{mid}/atos",
                        data={"csrf_token": _token(html), "tipo": "AV",
                              "numero": numero, "data_ato": "2026-09-16",
                              "teor": teor,
                              "natureza_titulo": "Compra e venda",
                              "codigo_tj": codigo_tj,
                              # O item 16.3 EXIGE o valor declarado desde
                              # 23/09/2026 (o TJ recusava o selo sem ele,
                              # R-01/4019), e a recusa é ANTES de o ato
                              # nascer — sem ele não há ato para medir.
                              "base_calculo": "1000,00" if codigo_tj else ""},
                        follow_redirects=True)


def _tela(casa, matricula_id):
    r = casa["cliente"].get(f"/registro-imoveis/{matricula_id}")
    assert r.status_code == 200, (
        f"a ficha respondeu HTTP {r.status_code} — não há o que medir")
    return r.get_data(as_text=True)


def _indice(html: str) -> str:
    """O que está no painel do alto, entre o título dele e o teor.

    O corte é medido na própria página, e a ordem é conferida: se o teor
    aparecesse antes do índice, o recorte devolveria vazio e os testes passariam
    a não medir nada.
    """
    inicio = html.index("Atos (")
    fim = html.index("Teor da ficha")
    assert inicio < fim, "o índice dos atos vem antes do teor"
    return html[inicio:fim]


def _ato_id(casa, mid) -> int:
    con = _con(casa)
    linha = con.execute("SELECT id FROM ri_atos WHERE matricula_id=? ORDER BY id",
                        (mid,)).fetchone()
    con.close()
    assert linha, "o ato não foi lavrado — sem ele não há o que medir"
    return int(linha["id"])


def test_o_texto_do_ato_sai_UMA_vez_na_ficha(casa):
    """O relato #71 — o defeito, medido no HTML que o balcão recebe."""
    assert FRASE_DO_ATO not in TEOR_DA_FICHA, (
        "a frase de prova tem de existir só no ato: se estivesse também no teor, "
        "contar 1 na página não provaria nada")
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="4100")
    con.close()

    _lavrar(casa, mid)
    html = _tela(casa, mid)

    quantas = html.count(FRASE_DO_ATO)
    assert quantas == 1, (
        f"o texto do ato saiu {quantas} vezes na ficha — relato #71: era o "
        "painel do alto e a sequência do teor dizendo a mesma coisa")

    assert "O que o teor acima não conta" in html, (
        "o ato que o teor não conta continua aparecendo depois dele — o pedido "
        "do relato #67 não se desfaz para atender o #71")
    assert 'class="teor"' not in _indice(html), (
        "sobrou cartão de texto no índice: é a forma do defeito — o mesmo texto "
        "em dois lugares da página")


def test_o_indice_diz_onde_ler_e_o_link_leva_ate_o_texto(casa):
    """O texto saiu do alto: quem lê precisa saber ONDE ele está.

    E o link tem de levar a alguma coisa. Âncora que não existe é pior que link
    nenhum: o endereço estar escrito parece a conferência feita.
    """
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="4101")
    con.close()
    _lavrar(casa, mid)
    ato_id = _ato_id(casa, mid)

    html = _tela(casa, mid)
    indice = _indice(html)
    alvo = f"texto-do-ato-{ato_id}"

    assert f'href="#{alvo}"' in indice, (
        "o índice tem de dizer onde o texto está — e o texto não está mais nele")
    assert f'id="{alvo}"' in html, (
        "a âncora do link não existe: o navegador não leva a lugar nenhum")
    assert html.index(f'id="{alvo}"') > html.index("Teor da ficha"), (
        "a âncora tem de estar na sequência, depois do teor — é lá que o texto "
        "do ato sai")


def test_o_ato_que_o_teor_ja_conta_diz_isso_e_nao_ganha_link(casa):
    """O ato escrito dentro do teor não tem cartão — e o índice não pode
    prometer o que não existe.

    É o caso de **531 atos** desta casa: o E-Ofício escrevia o ato dentro do
    texto da matrícula, e ali o teor JÁ o conta. Nesses não há cartão abaixo, e
    link para o vazio mandaria o leitor para o nada.
    """
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="4102")
    con.close()
    _lavrar(casa, mid)

    # o teor passa a contar o ato, como nas fichas do acervo
    con = _con(casa)
    teor_do_ato = con.execute("SELECT teor FROM ri_atos WHERE matricula_id=?",
                              (mid,)).fetchone()["teor"]
    with con:
        con.execute("UPDATE ri_matriculas SET teor=? WHERE id=?",
                    (f"{TEOR_DA_FICHA}\n\n{teor_do_ato}", mid))
    con.close()

    html = _tela(casa, mid)
    assert html.count(FRASE_DO_ATO) == 1, (
        "o teor já conta este ato: mostrá-lo de novo seria a ficha dizendo duas "
        "vezes a mesma coisa")

    indice = _indice(html)
    assert "O texto deste ato está dentro do teor" in indice, (
        "o índice tem de dizer que o texto está no teor — senão o leitor "
        "procura abaixo o que está acima")
    assert "texto-do-ato-" not in indice, (
        "não há cartão de texto para onde apontar: link para o nada é pior que "
        "link nenhum")


def test_o_indice_nao_perdeu_os_botoes_do_ato(casa):
    """O texto saiu do alto; a AÇÃO fica lá.

    «Cancelar», «Selar» e «Expurgar» são o que faz o ato andar, e mandá-los
    para depois de um teor de 60 mil caracteres seria escondê-los — que é o
    outro lado da decisão do oficial em 18/09.

    O ato lavrado aqui é o de ACERVO sem item de custa: ele fica **sem selo**
    (o oficial dispensou o item em 16/09), e por isso é ele que prova os TRÊS
    botões — inclusive o de selar depois, que só existe onde falta selo. É a
    única bancada deste arquivo que abre ficha de acervo, e ela o faz porque
    sem isso não haveria ato sem selo: o selador da bancada responde.
    """
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="2603", tipo_ficha="ACERVO")
    con.close()
    _lavrar(casa, mid, codigo_tj="")

    conferir = _con(casa)
    selo = conferir.execute("SELECT selo_texto FROM ri_atos WHERE matricula_id=?",
                            (mid,)).fetchone()["selo_texto"]
    conferir.close()
    assert not (selo or "").strip(), (
        "o ensaio precisa de um ato SEM selo para o botão de selar aparecer")

    indice = _indice(_tela(casa, mid))
    assert "Cancelar este ato" in indice, (
        "o formulário de cancelar tem de continuar no ato, no índice")
    assert "Selar este ato" in indice, (
        "ato lavrado sem selo (item de custa ausente, ou máquina fora do ar) "
        "precisa do botão de selar depois, e ele mora no índice")
    assert "Expurgar este ato" in indice, (
        "o expurgo do ato lavrado em teste é do ADMIN, e também vive no índice")


def test_o_ato_sem_texto_gravado_diz_isso_no_indice(casa):
    """Dois atos nesta casa não têm texto nenhum — e cartão vazio se lê como
    tela quebrada.

    Este não vem pela rota: `ri_lavrar_ato` recusa teor em branco («O teor do
    ato não pode ficar em branco»), e é a regra certa — quem lavra escreve. Os
    dois que existem entraram pela importação, e é assim que este teste os
    representa.
    """
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="4104")
        from ri_schema import hash_ato
        con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
                   hash_ato, lavrado_em)
               VALUES (?, 'AV', 7, '2026-09-16', '',
                       ?, '2026-09-16T08:00')""",
            (mid, hash_ato("4104", "AV", 7, "2026-09-16", "", None)))
    con.close()

    html = _tela(casa, mid)
    assert "Este ato não tem texto gravado." in _indice(html), (
        "o ato sem texto tem de dizer que não tem, em vez de abrir vazio")
    assert "texto-do-ato-" not in _indice(html), (
        "não há texto para ler: o índice não pode oferecer um link para ele")
    assert "O que o teor acima não conta" in html, (
        "sem texto do ato não há o que comparar com o teor — e ele continua "
        "aparecendo na sequência, com o rótulo e a data que tem")
