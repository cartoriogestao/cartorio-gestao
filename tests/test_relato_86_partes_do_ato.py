"""AS PARTES DO ATO NÃO TÊM TETO, E CADA UMA NUM BLOCO — relato #86, 18/09/2026.

    «a parte de partes que participam do ato precisa ser revista, precisa ser
     possivel incluir tantas quantas as partes do ato»
    «precisa organizar melhor para separar dados de cada parte» — o oficial.

AS DUAS METADES DO RELATO, e o lado que se guarda aqui é o do SERVIDOR:

  1. **SEM TETO.** O teto de três era do DESENHO; o `getlist` da rota sempre leu
     quantas partes viessem. Medido na produção antes de escrever a primeira
     linha: **44 atos desta casa têm mais de três partes** — o maior tem **22**
     (R-1 da matrícula 3.757, de 1984) — e **251 fichas** têm mais de três. O
     que se prova aqui é que **cinco partes num POST entram cinco, na ordem em
     que a tela as mandou** — e que o bloco em branco não vira parte.

  2. **POR PARTE.** O agrupamento é do desenho, e o desenho tem os seus testes
     em `test_ri_minuta_devolve_as_partes.py` (o bloco, o molde, o botão). O
     que se guarda AQUI é a metade que agrupar torna **frágil**: os dois campos
     que a tela não edita e devolve escondidos (`parte_qualificacao` e
     `parte_documento_tipo`) viajam por POSIÇÃO dentro do formulário. Lista
     torta faria a qualificação de uma parte cair no nome da vizinha — calada,
     num registro público, porque `getlist` casa as listas por índice.

E A REVISÃO DA MINUTA TAMBÉM LEVA AS PARTES — o `formaction` que separa
«guardar» de «lavrar» usa o MESMO formulário, e até 18/09/2026 a rota de guardar
gravava teor, número, natureza, protocolo e prenotação, e deixava os blocos de
parte de fora: quem acrescentasse a quarta parte e clicasse em **Guardar
revisão** perdia o que digitou. E o contrário também, que é pior: um POST que
trouxesse só o teor **apagaria** as partes guardadas, porque `[]` e `None` não
são a mesma coisa em `ri_minuta.atualizar`.

> **O ATO SUSPENSO PASSA POR AQUI, e é a razão de os dois lados do campo
> escondido existirem.** `voltar_do_ato` copia a qualificação de `ri_partes`
> para a minuta; a ficha a devolve no bloco invisível; e a lavratura tem de
> gravá-la de volta — senão re-lavrar um ato suspenso apaga a qualificação que
> ele tinha, e ela é o que o modelo do ato escreve ao lado do nome.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_minuta as RIMIN  # noqa: E402
from ri_schema import normalizar_busca  # noqa: E402

# Cinco partes — o ato que a tela não deixava escrever até 18/09/2026.
PARTES = (
    ("JOSÉ ANTÔNIO DE SANTANA NETO", "111.222.333-44", "proprietário"),
    ("MARIA DA SILVA", "000.000.048-55", "adquirente"),
    ("BANCO DO BRASIL S/A", "00.000.010/0001-27", "credor"),
    ("IRENE ANDRADE MACHADO CARDOSO", "", "anuente"),
    ("ESPÓLIO DE JOÃO PEREIRA", "", "proprietário"),
)

TEOR = ("AV-04/3.201 - DESTAQUE DE AREA E ABERTURA DE MATRICULA, conforme o "
        "titulo apresentado nesta serventia.")


def _so_digitos(t: str) -> str:
    return re.sub(r"\D", "", t or "")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _tela(casa, endereco):
    r = casa["c"].get(endereco)
    assert r.status_code == 200, f"a tela {endereco} nao abriu: {r.status_code}"
    return r.get_data(as_text=True)


def _matricula_do_sistema(casa, livro="2") -> int:
    """Abre UMA matrícula no intervalo do sistema e devolve o id.

    **A FICHA DE ACERVO É OUTRA PERGUNTA**, e é o que faz este ajudante existir:
    com o banco do zero a série começa em 1, e a regra da serventia de 17/09/2026
    — «números menores que 4.015 são acervo» — faz a ficha nascer `ACERVO`, onde
    o ato é recusado pedindo o número «conforme o livro físico». Nada aqui fala
    de acervo: o que se mede é o ato que o BALCÃO lava, em ficha nova.
    """
    from ri_schema import PRIMEIRA_MATRICULA_DO_SISTEMA as PRIMEIRA

    con = _con(casa)
    with con:
        if not con.execute("SELECT 1 FROM ri_numeracao WHERE livro=?",
                           (livro,)).fetchone():
            con.execute(
                """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso,
                       fixado_em)
                   VALUES (?,?,?,'2026-09-18')""",
                (livro, PRIMEIRA, PRIMEIRA - 1))
    con.close()

    html = _tela(casa, "/registro-imoveis/nova")
    casa["c"].post("/registro-imoveis/nova",
                   data={"livro": livro, "cidade": "Cidade Exemplo", "uf": "MA",
                         "area_unidade": "ha", "csrf_token": _token(html)},
                   follow_redirects=True)
    con = _con(casa)
    mid = con.execute("SELECT MAX(id) i FROM ri_matriculas").fetchone()["i"]
    con.close()
    return int(mid)


def _minuta(casa) -> tuple[int, int]:
    """Uma minuta A_REVISAR numa ficha NOVA — não se lavra nada aqui.

    A ficha vem da rota (`_matricula_do_sistema`), e não de um `INSERT` meu, por
    dois motivos medidos: ela nasce no intervalo do sistema (senão a regra de
    17/09 — «abaixo de 4.015 é acervo» — faria a lavratura exigir o número do
    livro físico) e vem com o `tipo_ficha` e a `situacao` que a casa escreve.
    Ficha inventada no teste mede um mundo que não existe.
    """
    mid = _matricula_do_sistema(casa)
    con = _con(casa)
    with con:
        minuta_id = RIMIN.criar(
            con, matricula_id=mid, tipo="AV", teor=TEOR, numero_pretendido=4,
            natureza_titulo="Cancelamento de hipoteca cedular",
            agora="2026-09-18T09:10")
    con.close()
    return int(mid), int(minuta_id)


def _lavrar(casa, mid, **campos) -> str:
    """POST na rota de lavrar com o contrato de 15-17/09 cumprido.

    A bancada precisa do aparelho ligado (`ligar_o_selador`): desde 16/09/2026
    **o selo que não sai suspende o ato**, e sem ele o POST não grava parte
    nenhuma — o que se mediu, no dia em que este arquivo nasceu, foi `ri_atos`
    em zero e o ato de volta à fila de minutas.
    """
    from selador_de_bancada import ligar_o_selador

    with ligar_o_selador(casa):
        html = _tela(casa, f"/registro-imoveis/{mid}")
        # O ITEM 16.3 EXIGE O VALOR DECLARADO desde a 3.6.185 (23/09/2026,
        # R-01/4019 recusado pelo TJ): sem `base_calculo` a rota recusa antes
        # de o ato nascer, e nenhuma parte era gravada.
        dados = {"tipo": "AV", "teor": TEOR, "data_ato": "2026-08-18",
                 "natureza_titulo": "Compra e venda", "codigo_tj": "16.3",
                 "base_calculo": "100.000,00",
                 "csrf_token": _token(html)}
        dados.update(campos)
        r = casa["c"].post(f"/registro-imoveis/{mid}/atos", data=dados,
                           follow_redirects=True)
    return r.get_data(as_text=True)


def _partes_gravadas(casa, mid) -> list[dict]:
    con = _con(casa)
    linhas = [dict(x) for x in con.execute(
        """SELECT nome, nome_norm, documento_tipo, documento_numero, papel,
                  qualificacao, proprietario, proprietario_ativo
             FROM ri_partes WHERE matricula_id=? ORDER BY id""", (mid,))]
    con.close()
    return linhas


def _blocos(nomes, docs, papeis, quails=(), tipos=()):
    """O formulário como a tela o monta: uma lista por campo, na mesma ordem."""
    return {"parte_nome": list(nomes), "parte_documento": list(docs),
            "parte_papel": list(papeis), "parte_qualificacao": list(quails),
            "parte_documento_tipo": list(tipos)}


@pytest.fixture()
def casa(cg_casa_logada):
    return cg_casa_logada


# ------------------------------------------- 1. sem teto, e na ordem da tela


def test_o_ato_guarda_as_cinco_partes_na_ordem_que_a_tela_mandou(casa):
    """«tantas quantas as partes do ato» — o teto de três era do desenho.

    O maior ato desta casa tem **22 partes** (R-1 da matrícula 3.757, de 1984) e
    44 atos passam de três. Aqui são cinco, que é o que basta para provar que não
    há corte em três — e a ORDEM é conferida porque é ela que a tela desenha: a
    primeira parte é a que o escrevente ditou primeiro.
    """
    mid = _matricula_do_sistema(casa)
    _lavrar(casa, mid, **_blocos(
        [p[0] for p in PARTES], [p[1] for p in PARTES], [p[2] for p in PARTES]))

    partes = _partes_gravadas(casa, mid)
    assert len(partes) == 5, (
        f"a tela oferece quantas partes forem, e entraram {len(partes)}")
    assert [p["nome"] for p in partes] == [p[0] for p in PARTES]
    assert [p["papel"] for p in partes] == [p[2] for p in PARTES]

    for gravada, (nome, doc, _papel) in zip(partes, PARTES):
        assert gravada["nome_norm"] == normalizar_busca(nome), (
            "o nome_norm sai da MESMA funcao da casa — e e por ele que a busca "
            "por nome acha quem nao tem documento")
        assert gravada["documento_numero"] == (_so_digitos(doc) or None)
        if len(_so_digitos(doc)) == 11:
            assert gravada["documento_tipo"] == "CPF"
        elif len(_so_digitos(doc)) == 14:
            assert gravada["documento_tipo"] == "CNPJ"
        else:
            assert gravada["documento_tipo"] is None


def test_so_o_proprietario_fica_como_titular_atual(casa):
    """O papel decide o titular — e é ele que assina a certidão.

    Cinco partes com dois `proprietário` no meio: quem for titular é quem o
    papel diz, e não a primeira linha da lista. Este é o campo que, errado,
    troca o dono do imóvel no papel que a casa emite.
    """
    mid = _matricula_do_sistema(casa)
    _lavrar(casa, mid, **_blocos(
        [p[0] for p in PARTES], [p[1] for p in PARTES], [p[2] for p in PARTES]))

    partes = _partes_gravadas(casa, mid)
    ativos = [p["nome"] for p in partes if p["proprietario_ativo"]]
    assert ativos == ["JOSÉ ANTÔNIO DE SANTANA NETO", "ESPÓLIO DE JOÃO PEREIRA"]
    assert [p["proprietario"] for p in partes if p["papel"] == "credor"] == [0]


def test_o_bloco_em_branco_da_tela_nao_vira_parte(casa):
    """A tela manda sempre um bloco a mais, e ele é a linha livre.

    Bloco sem nome não é parte — é o espaço de quem ainda vai digitar a sexta.
    Gravado, ele poria uma pessoa sem nome no registro, e a certidão do titular
    sairia com uma linha em branco no lugar do nome.
    """
    mid = _matricula_do_sistema(casa)
    _lavrar(casa, mid, **_blocos(
        [p[0] for p in PARTES] + [""], [p[1] for p in PARTES] + [""],
        [p[2] for p in PARTES] + [""]))

    assert len(_partes_gravadas(casa, mid)) == 5


def test_o_formulario_nao_conta_as_partes_e_nao_corta_a_lapis(casa):
    """Sem teto no servidor também: vinte partes entram vinte.

    O pedido é «tantas quantas as partes do ato», e um teto escondido aqui — 5,
    10, 22 — seria eu escolhendo por quem lavra, no único lugar onde ninguém vê.
    Vinte e duas é o maior ato desta casa, de 1984, na matrícula 3.757.
    """
    quantas = 22
    nomes = [f"PARTE NUMERO {i:02d}" for i in range(1, quantas + 1)]
    mid = _matricula_do_sistema(casa)
    _lavrar(casa, mid, **_blocos(nomes, [""] * quantas, ["credor"] * quantas))

    partes = _partes_gravadas(casa, mid)
    assert [p["nome"] for p in partes] == nomes


# --------------------------- 2. o campo escondido não escorrega para a vizinha


def test_a_qualificacao_do_bloco_escondido_volta_para_a_parte_certa(casa):
    """Ela viaja por POSIÇÃO no formulário, e é o que `getlist` casa por índice.

    A tela não edita a qualificação — quem a escreveu foi o ato, ou o acervo —,
    mas ela volta escondida e tem de chegar à MESMA pessoa. Na lista torta, a
    qualificação do segundo cairia no nome do terceiro, calada, num registro
    público.
    """
    mid = _matricula_do_sistema(casa)
    _lavrar(casa, mid, **_blocos(
        ["JOSÉ ANTÔNIO DE SANTANA NETO", "MARIA DA SILVA", "BANCO DO BRASIL S/A"],
        ["", "", ""],
        ["proprietário", "adquirente", "credor"],
        quails=["brasileiro, casado, comerciante", "brasileira, solteira", ""],
        tipos=["", "", ""]))

    partes = _partes_gravadas(casa, mid)
    assert partes[0]["qualificacao"] == "brasileiro, casado, comerciante"
    assert partes[1]["qualificacao"] == "brasileira, solteira"
    assert partes[2]["qualificacao"] is None, (
        "a qualificacao do vizinho caiu na terceira parte")


def test_lista_torta_nao_escorrega_e_nao_derruba_a_tela(casa):
    """Menos qualificações do que blocos: o valor é declarado ausente.

    Lista torta é entrada possível — cliente que manda menos campos, script,
    formulário de outra versão. O que não pode acontecer é a qualificação de uma
    parte ir para o nome de outra, nem a rota estourar com o cliente na frente.
    """
    mid = _matricula_do_sistema(casa)
    _lavrar(casa, mid, **_blocos(
        ["JOSÉ ANTÔNIO DE SANTANA NETO", "MARIA DA SILVA", "ESPÓLIO DE JOÃO PEREIRA"],
        ["", "", ""],
        ["proprietário", "adquirente", "proprietário"],
        quails=["brasileiro, casado", "brasileira, solteira"],
        tipos=["CPF", "CPF"]))

    partes = _partes_gravadas(casa, mid)
    assert len(partes) == 3, "a tela nao pode perder parte por lista torta"
    assert [p["qualificacao"] for p in partes] == [None, None, None], (
        "lista de dois valores para tres blocos: o valor e declarado ausente, "
        "e nao adivinhado")


def test_o_tipo_gravado_no_acervo_nao_se_perde_quando_falta_o_numero(casa):
    """O tipo sai do tamanho do documento — e, quando ele não decide, do que veio.

    A linha do acervo pode ter o tipo e não ter o número: derivar do tamanho
    devolveria `None` e o tipo gravado sumiria. O informado entra só nesse caso,
    porque quem decide o tipo do que o balcão digita é o documento.
    """
    mid = _matricula_do_sistema(casa)
    _lavrar(casa, mid, **_blocos(
        ["ESPÓLIO DE JOÃO PEREIRA"], [""], ["proprietário"],
        quails=["inventariado"], tipos=["CPF"]))

    parte = _partes_gravadas(casa, mid)[0]
    assert parte["documento_tipo"] == "CPF"
    assert parte["documento_numero"] is None
    assert parte["qualificacao"] == "inventariado"


# --------------------------- 3. a revisão da minuta guarda — e não apaga


def _guardar(casa, mid, minuta_id, **campos) -> str:
    dados = {"teor": TEOR, "tipo": "AV", "natureza_titulo":
             "Cancelamento de hipoteca cedular", "numero": "4",
             "csrf_token": _token(_tela(casa, f"/registro-imoveis/{mid}"))}
    dados.update(campos)
    r = casa["c"].post(
        f"/registro-imoveis/minuta/{minuta_id}/guardar", data=dados,
        follow_redirects=True)
    return r.get_data(as_text=True)


def _partes_da_minuta(casa, minuta_id) -> list[dict]:
    con = _con(casa)
    linhas = RIMIN.partes(con, minuta_id)
    con.close()
    return linhas


def test_guardar_a_revisao_guarda_as_partes_do_bloco(casa):
    """Quem acrescenta a quarta parte e clica em Guardar revisão não pode perdê-la.

    A minuta é o que sobrevive quando o selo não sai — e o que salvou a AV-05 da
    3.110 em 15/09 foi ter as partes guardadas. Guardar a revisão sem elas é
    deixar o trabalho pela metade na única tela que existe para não perdê-lo.
    """
    mid, minuta_id = _minuta(casa)
    _guardar(casa, mid, minuta_id, **_blocos(
        ["BANCO DO BRASIL S.A", "IRENE ANDRADE MACHADO CARDOSO",
         "MARIA DA SILVA", "ESPÓLIO DE JOÃO PEREIRA"],
        ["00.000.010/0001-27", "000.000.043-40", "", ""],
        ["credor", "proprietario", "anuente", "proprietario"],
        quails=["", "", "", ""], tipos=["", "", "", ""]))

    partes = _partes_da_minuta(casa, minuta_id)
    assert [p["nome"] for p in partes] == [
        "BANCO DO BRASIL S.A", "IRENE ANDRADE MACHADO CARDOSO",
        "MARIA DA SILVA", "ESPÓLIO DE JOÃO PEREIRA"]
    assert partes[1]["papel"] == "proprietario"
    # A MINUTA GUARDA O QUE A TELA MANDOU, COM A MÁSCARA — e não é descuido: é
    # um RASCUNHO, e o campo volta para o operador como ele o digitou. Quem tira
    # os pontos é a lavratura (`so_digitos`, no `INSERT` de `ri_partes`), que é
    # quem grava o documento no registro. Normalizar aqui mostraria
    # `00000010000127` a quem escreveu `00.000.010/0001-27`.
    assert partes[0]["documento_numero"] == "00.000.010/0001-27"


def test_guardar_de_novo_substitui_e_nao_soma(casa):
    """Guardar a revisão é dizer «é isto», e não «mais isto».

    Duas listas somadas poriam nomes repetidos num registro público — e o
    operador que tirou uma parte da tela a veria voltar depois de guardar.
    """
    mid, minuta_id = _minuta(casa)
    _guardar(casa, mid, minuta_id, **_blocos(
        ["BANCO DO BRASIL S.A", "IRENE ANDRADE MACHADO CARDOSO"],
        ["", ""], ["credor", "proprietario"]))
    _guardar(casa, mid, minuta_id, **_blocos(
        ["BANCO DO BRASIL S.A"], [""], ["credor"]))

    assert [p["nome"] for p in _partes_da_minuta(casa, minuta_id)] == \
        ["BANCO DO BRASIL S.A"]


def test_guardar_so_o_teor_nao_apaga_as_partes_que_estavam_la(casa):
    """`[]` e `None` não são a mesma coisa — e é aqui que eles se separam.

    `ri_minuta.atualizar` diz que `partes=None` quer dizer «a tela não mexeu
    nisto». Mas `_partes_da_tela` devolve **lista sempre**, e por isso um POST
    sem campo de parte nenhum (script, teste, outra tela) apagaria as partes da
    minuta sem ter tocado nelas — e a minuta voltaria vazia para a fila, que é o
    defeito de 15/09 pela porta do meio.
    """
    mid, minuta_id = _minuta(casa)
    _guardar(casa, mid, minuta_id, **_blocos(
        ["BANCO DO BRASIL S.A", "IRENE ANDRADE MACHADO CARDOSO"],
        ["", ""], ["credor", "proprietario"]))

    _guardar(casa, mid, minuta_id, teor=TEOR)  # nenhum campo `parte_*`

    assert [p["nome"] for p in _partes_da_minuta(casa, minuta_id)] == \
        ["BANCO DO BRASIL S.A", "IRENE ANDRADE MACHADO CARDOSO"], (
        "o POST sem campos de parte apagou as partes guardadas")


def test_a_minuta_lavrada_guarda_a_qualificacao_de_volta_no_ato(casa):
    """O ato suspenso volta inteiro — inclusive a qualificação que ele tinha.

    A corrente é esta: `voltar_do_ato` copia a qualificação de `ri_partes` para
    a minuta, a ficha a devolve no bloco invisível, e a LAVRATURA tem de gravá-la
    de volta. Até 18/09/2026 o último elo não existia: a leitura trazia a
    qualificação e o `INSERT` em `ri_partes` a descartava, de modo que re-lavrar
    um ato suspenso apagava a qualificação — que é o que o modelo do ato escreve
    ao lado do nome do transmitente. Some sem erro em lugar nenhum.
    """
    mid, minuta_id = _minuta(casa)
    _guardar(casa, mid, minuta_id, **_blocos(
        ["JOSÉ ANTÔNIO DE SANTANA NETO"], [""], ["proprietário"],
        quails=["brasileiro, casado, comerciante"], tipos=["CPF"]))

    # A minuta manda para a ficha, e é ela que o escrevente relavra — o mesmo
    # caminho de quem volta de um ato suspenso pelo selo.
    html = _tela(casa, f"/registro-imoveis/{mid}?minuta={minuta_id}")
    assert 'value="brasileiro, casado, comerciante"' in html, (
        "a qualificacao guardada na minuta tem de voltar ao formulario")

    _lavrar(casa, mid, minuta_id=minuta_id, **_blocos(
        ["JOSÉ ANTÔNIO DE SANTANA NETO"], [""], ["proprietário"],
        quails=["brasileiro, casado, comerciante"], tipos=["CPF"]))

    parte = _partes_gravadas(casa, mid)[0]
    assert parte["qualificacao"] == "brasileiro, casado, comerciante", (
        "re-lavrar perdeu a qualificacao que o ato tinha")
