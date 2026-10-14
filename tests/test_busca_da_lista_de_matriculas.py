"""
A busca da lista de matriculas — o relato #55, decidido em 15/09/2026.

O QUE O BALCAO RELATOU
    «verificar porque pesquisando a matricula 3110 encontrou a 3602 somente»
    (14/09/2026). A 3602 aparecia porque quatro daqueles digitos — 3110 — estao
    dentro do CPF de uma parte dela, 00000001406.

O QUE SE MEDIU NA PRODUCAO, ANTES DA CORRECAO
    A caixa era UMA e procurava em cinco campos ao mesmo tempo, sempre por
    «contem»: o numero, o CNM, o endereco, o nome e o CPF das partes. Uma busca
    por «1» devolvia 1.198 fichas — 782 pelo numero, 877 pelo CNM e 460 por
    dentro de um CPF. E o nome era comparado CRU: «rubens dantas machado»
    achava ZERO, porque o acervo grava «RUBENS DANTAS MACHADO», com acento.

O QUE MUDOU, POR DECISAO DO OFICIAL
    numero, CNM e documento: EXATOS. Endereco e nome: por TRECHO, e o nome pelo
    normalizado. Medido depois, na producao: «3110» cai de 2 fichas para 1,
    «314» de 7 para 1, «1» de 1.198 para 3, e o nome em minusculas passa a achar.

POR QUE TESTE DE TELA, E NAO SO DA FUNCAO
    Foi a tela que respondeu errado ao balcao, e e ela que ele usa. Os testes
    aqui perguntam a ela — pelos ids que a pagina devolve —, e nao ao SQL.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_web  # noqa: E402
from ri_schema import normalizar_busca  # noqa: E402


# --------------------------------------------------------------- a tela


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def tela(s, caminho: str) -> str:
    return s["c"].get(caminho).get_data(as_text=True)


def achadas(s, termo: str, caminho: str = "/registro-imoveis") -> list[int]:
    """Os ids das fichas que a tela devolveu, na ordem em que apareceram.

    O id sai do proprio link da linha — e a unica coisa da pagina que diz
    *qual* ficha entrou, sem depender de o numero aparecer no texto.
    """
    html = tela(s, f"{caminho}?busca={quote(termo)}")
    return [int(x) for x in re.findall(r'"/registro-imoveis/(\d+)"', html)]


def banco(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


# --------------------------------------------------------------- o acervo


def _ficha(s, numero, *, cnm=None, partes=(), livro="2") -> int:
    """Uma ficha como o acervo a guarda — e as partes dela.

    `nome_norm` entra pela MESMA funcao da casa, como o importador faz: o que
    se esta medindo aqui e a busca, e nao a derivacao da coluna.
    """
    con = banco(s)
    con.execute(
        """INSERT INTO ri_matriculas
           (numero, complemento, livro, livro_norm, tipo_ficha, situacao,
            conferido, origem, criado_em, teor_formato, cnm)
           VALUES (?,'',?,?,'ESTRUTURADA','ATIVA',0,'EOFICIO','2026-07-31','texto',?)""",
        (str(numero), livro, livro, cnm))
    mid = con.execute("SELECT MAX(id) i FROM ri_matriculas").fetchone()["i"]
    for nome, doc, papel in partes:
        digitos = "".join(c for c in (doc or "") if c.isdigit())
        con.execute(
            """INSERT INTO ri_partes
               (matricula_id, nome, nome_norm, documento_tipo, documento_numero,
                documento_valido, papel, proprietario, proprietario_ativo, origem)
               VALUES (?,?,?,?,?,?,?,?,?,'EOFICIO')""",
            (mid, nome, normalizar_busca(nome),
             "CPF" if len(digitos) == 11 else ("CNPJ" if len(digitos) == 14 else None),
             digitos or None, 1, papel, 0, 0))
    con.commit()
    con.close()
    return int(mid)


# OS NOMES SÃO OS DO RELATO, e os vizinhos são os que decidem a regra: a 3140
# existe para provar que «314» não a traz, e a 3236 é a do CNM com máscara.
ADELAIDE = "RUBENS DANTAS MACHADO"
RAIMUNDA = "RAIMUNDA DA CONCEIÇÃO TORRES"
CPF_DA_RAIMUNDA = "00000001406"
CNM_MASCARADO = "000000.2.0003236-22"


def acervo(s) -> dict[str, int]:
    return {
        # a 3110 e a 3602 do relato: quem tem o CPF com «3110» dentro é a 3602
        "3110": _ficha(s, 3110, partes=[("JOSE DA SILVA", "11122233344", "proprietário")]),
        "3602": _ficha(s, 3602, partes=[(RAIMUNDA, CPF_DA_RAIMUNDA, "proprietário")]),
        # o numero exato, contra o vizinho que comeca igual
        "314": _ficha(s, 314),
        "3140": _ficha(s, 3140),
        # o nome acentuado, e o CNM que se grava com mascara
        "977": _ficha(s, 977, partes=[(ADELAIDE, None, "proprietário")]),
        "3236": _ficha(s, 3236, cnm=CNM_MASCARADO, partes=[("MARIA SOUZA", None, "")]),
        # a ficha 2 existe para o guarda do «2Q»: procurar livro nao pode devolve-la
        "2": _ficha(s, 2, livro="2Q"),
    }


# ------------------------------------------------------- o relato #55


def test_a_busca_por_3110_nao_traz_a_ficha_do_cpf_alheio(cg_casa_logada):
    """O relato inteiro: «pesquisando a matricula 3110 encontrou a 3602»."""
    ids = acervo(cg_casa_logada)
    assert achadas(cg_casa_logada, "3110") == [ids["3110"]], (
        "a 3602 entra pelo CPF de uma parte dela, 00000001406, e nao pode mais")


def test_o_cpf_completo_acha_a_ficha_da_parte(cg_casa_logada):
    """A outra metade: quem digita o documento inteiro continua achando."""
    ids = acervo(cg_casa_logada)
    assert ids["3602"] in achadas(cg_casa_logada, CPF_DA_RAIMUNDA)


def test_o_cpf_com_mascara_tambem_acha(cg_casa_logada):
    """O documento se guarda so com digitos; quem digita com ponto e traco acha.

    Medido no acervo: nenhum dos 1.173 documentos das partes tem ponto, barra
    ou traco. Exigir do balcao a mesma pontuacao seria esconder a ficha — a
    busca antiga (por «contem», no texto cru) achava ZERO com a mascara.
    """
    ids = acervo(cg_casa_logada)
    assert ids["3602"] in achadas(cg_casa_logada, "000.000.014-06")


def test_o_numero_da_matricula_e_exato(cg_casa_logada):
    """Numero nao tem «parecido»: «314» acha a 314, e nao a 3140."""
    ids = acervo(cg_casa_logada)
    assert achadas(cg_casa_logada, "314") == [ids["314"]]
    assert achadas(cg_casa_logada, "3140") == [ids["3140"]]


def test_o_cnm_se_acha_com_e_sem_mascara(cg_casa_logada):
    """O CNM se grava como `000000.2.0003236-22` — as duas formas chegam nele."""
    ids = acervo(cg_casa_logada)
    assert achadas(cg_casa_logada, CNM_MASCARADO) == [ids["3236"]]
    assert achadas(cg_casa_logada, "0000002000323622") == [ids["3236"]]


def test_o_nome_acha_em_minusculas_e_sem_acento(cg_casa_logada):
    """As tres formas do mesmo nome — e a que o balcao digita e a de baixo."""
    ids = acervo(cg_casa_logada)
    for termo in (ADELAIDE, "rubens dantas machado", "rubens dantas machado",
                  "RUBENS DANTAS MACHADO"):
        assert achadas(cg_casa_logada, termo) == [ids["977"]], termo


def test_o_nome_continua_sendo_procurado_por_trecho(cg_casa_logada):
    """«SILVA» tem de achar «JOSE DA SILVA» — o nome nao virou exato."""
    ids = acervo(cg_casa_logada)
    assert ids["3110"] in achadas(cg_casa_logada, "da silva")


def test_procurar_por_livro_nao_vira_busca_por_numero(cg_casa_logada):
    """O guarda do `_numero_digitado`: «2Q» NAO pode virar «2».

    Sem ele, tirar as letras da busca por livro devolveria a ficha 2 — e quem
    procura o livro 2Q leria a ficha de outro imovel como resposta.
    """
    ids = acervo(cg_casa_logada)
    assert achadas(cg_casa_logada, "2Q") == []
    assert achadas(cg_casa_logada, "2") == [ids["2"]]


# -------------------------------------------- a parte que o balcao cadastra


def _matricula_do_sistema(s, livro="2") -> int:
    """Abre UMA matricula no intervalo do sistema e devolve o id.

    **A FICHA DESTA BANCADA NASCIA DE ACERVO, E ISSO A TORNAVA OUTRA PERGUNTA.**
    Medido em 18/09/2026: com o banco do zero a serie comeca em 1, e a regra da
    serventia de 17/09/2026 — «numeros menores que 4.015 sao acervo» — faz a
    ficha nascer `ACERVO`. Ali o ato e recusado pedindo o numero «conforme o
    livro fisico», e nenhum destes testes fala de acervo: o que se mede aqui e a
    parte que o BALCAO cadastra, que e ficha nova.

    E o ato so fica de pe com o aparelho da bancada ligado
    (`selador_de_bancada`), porque desde 16/09/2026 o selo que nao sai suspende
    o ato — os tres numeros que decidem isto estao medidos no teste abaixo.
    """
    from ri_schema import PRIMEIRA_MATRICULA_DO_SISTEMA as PRIMEIRA
    con = banco(s)
    with con:
        if not con.execute("SELECT 1 FROM ri_numeracao WHERE livro=?", (livro,)).fetchone():
            con.execute(
                """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso,
                       fixado_em)
                   VALUES (?,?,?,'2026-09-18')""",
                (livro, PRIMEIRA, PRIMEIRA - 1))
    con.close()
    html = tela(s, "/registro-imoveis/nova")
    s["c"].post("/registro-imoveis/nova",
                data={"livro": livro, "cidade": "Cidade Exemplo", "uf": "MA",
                      "area_unidade": "ha", "csrf_token": _token(html)},
                follow_redirects=True)
    con = banco(s)
    mid = con.execute("SELECT MAX(id) i FROM ri_matriculas").fetchone()["i"]
    con.close()
    return int(mid)


def test_a_parte_cadastrada_pelo_balcao_ja_nasce_pesquisavel(cg_casa_logada):
    """`nome_norm` e DERIVADO ao gravar — e nao so na subida do sistema.

    Este era um buraco proprio: o importador derivava a coluna, e o caminho que
    o balcao usa para cadastrar a parte ao lavrar o ato NAO derivava. A parte
    ficava invisivel para a busca por nome ate o proximo reinicio do sistema —
    e e a busca por nome o unico caminho ate a ficha de quem nao tem documento
    (2.820 das 3.992 partes do acervo).

    **E ESTE TESTE ESTAVA VERMELHO, E A CULPA NAO ERA DA PARTE — medido em
    18/09/2026, com o POST dele rodado contra a rota e o aviso lido.** Ele
    montava a ficha numero 1 (acervo, regra de 17/09), o POST nao trazia
    `natureza_titulo` nem `codigo_tj` (exigidos desde 15-17/09, porque o selo os
    pede) e a bancada nao tinha selador — tres contratos vizinhos, e em todos
    eles o que acontecia era **o ato nao ser lavrado**: zero linhas em
    `ri_atos` e zero em `ri_partes`. A mensagem «a parte nao foi gravada» dizia
    o efeito e escondia a causa, que e outra. Agora a bancada cumpre o contrato
    e ele volta a medir o que diz medir.
    """
    from selador_de_bancada import ligar_o_selador

    s = cg_casa_logada
    mid = _matricula_do_sistema(s)

    nome = "José Antônio de Santana Neto"
    with ligar_o_selador(s):
        html = tela(s, f"/registro-imoveis/{mid}")
        s["c"].post(f"/registro-imoveis/{mid}/atos",
                    data={"tipo": "R", "teor": "R-01 TITULO DE DOMINIO",
                          "data_ato": "2026-08-18",
                          "natureza_titulo": "Compra e venda",
                          "codigo_tj": "16.3",
                          "parte_nome": nome,
                          "parte_papel": "proprietário", "csrf_token": _token(html)},
                    follow_redirects=True)

    con = banco(s)
    parte = con.execute("SELECT nome, nome_norm FROM ri_partes WHERE matricula_id=?",
                        (mid,)).fetchone()
    con.close()
    assert parte is not None, "a parte nao foi gravada"
    assert parte["nome"] == nome
    assert parte["nome_norm"] == normalizar_busca(nome), (
        "a coluna de busca tem de sair da MESMA funcao da casa, e nao ficar vazia")
    assert mid in achadas(s, "jose antonio de santana neto")


# ------------------------------------------------ o indicador pessoal


def test_o_documento_do_indicador_pessoal_tambem_e_exato(cg_casa_logada):
    """A mesma regua na tela vizinha: o nome por trecho, o documento inteiro.

    Duas reguas para a mesma pergunta, em duas telas da mesma atribuicao, e o
    defeito que este projeto ja pagou caro varias vezes.
    """
    ids = acervo(cg_casa_logada)
    caminho = "/registro-imoveis/indicador-pessoal"
    assert ids["3602"] in achadas(cg_casa_logada, CPF_DA_RAIMUNDA, caminho)
    assert achadas(cg_casa_logada, "3110", caminho) == [], (
        "quatro digitos soltos do CPF nao podem trazer a pessoa")
    assert ids["3602"] in achadas(cg_casa_logada, "raimunda", caminho)


# ------------------------------------------------------ a regua, miuda


def test_a_regua_do_numero_so_le_numero():
    """O que passa e o que nao passa pela porta do «exato»."""
    assert ri_web._numero_digitado("3.110") == "3110"
    assert ri_web._numero_digitado(" 3110 ") == "3110"
    assert ri_web._numero_digitado("000.000.014-06") == "00000001406"
    assert ri_web._numero_digitado("000000.2.0003236-22") == "0000002000323622"
    # o guarda: livro, tipo de ato e nome nao sao numeros
    assert ri_web._numero_digitado("2Q") is None
    assert ri_web._numero_digitado("R-01") is None
    assert ri_web._numero_digitado("MARIA") is None
    assert ri_web._numero_digitado("") is None
    assert ri_web._numero_digitado("AV-28/1.490") is None


def test_o_cnm_se_reconstroi_pela_mascara_da_casa():
    """6+1+7+2, a forma dos 1.659 CNMs do acervo — e o pedaco nao vira mascara."""
    assert ri_web._cnm_da_casa("0000002000323622") == "000000.2.0003236-22"
    assert ri_web._cnm_da_casa("0003236") == "0003236"
