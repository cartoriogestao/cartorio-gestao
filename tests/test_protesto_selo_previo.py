"""
O selo do Protesto conferido ANTES de lavrar, as obrigações que ele deixa, e
a situação que pede um ato.

Ordem do oficial, 29/10/2026: «precisamos revisar os processos para nao
permitir que a mao de obra erre», e a revisão do mesmo dia: «garantir que
todos os processos sejam concluídos todos os dias; não deixar margem para a
escrevente esquecer ou fazer errado». Medido na produção no mesmo dia (só
leitura): cinco atos do Protesto desfeitos por «Selo não emitido» — quatro sem
item, e o 4127 com as faixas 17.1.7 e 17.4.5, que o aparelho não conhece —, e o
título 9614 PAGO sem pagamento válido.

O QUE ELES CONFEREM
    - tudo o que se sabe antes recusa antes, com frase de balcão e sendo
      `ValueError` (regra da casa): o caminho e a data da tabela, o protocolo
      do título, o item, o caixa, o item fora do caminho;
    - o item fora do caminho é a única trava que a afirmação expressa vence, e
      a afirmação pela metade continua sendo a trava;
    - a régua do item é a receita medida MAIS o que o aparelho já aceitou — a
      receita sozinha teria recusado o 4106, que saiu;
    - a faixa vira o item do Tribunal só onde o caminho conhece o item;
    - o ato desfeito pelo selo é obrigação até ser lançado de novo, e o do
      robô sem selo também;
    - a situação sustentada pelos atos válidos, e a correção de ofício que
      volta a ela só com afirmação;
    - só duas funções escrevem; o resto lê.

Documentos fictícios só, de `tests/fixtures/anti_vazamento/`.
"""
from __future__ import annotations

import ast
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import ato_selado as AS                          # noqa: E402
import atribuicoes as ATR                        # noqa: E402
import protesto_selo_previo as PSELO             # noqa: E402
from bd_nativo import banco as nativo            # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402
from selador_config import init_selador_schema   # noqa: E402

AGORA = "2026-10-29T09:00:00"
ATOS_QUE_SELAM = ("INTIMACAO", "PROTESTO", "PAGAMENTO", "DESISTENCIA",
                  "CANCELAMENTO")
AFIRMACAO_BOA = ("Afirmo, sob minha responsabilidade, que este item serve "
                 "para este ato, conforme a tabela do Tribunal.")


def _da_receita(ato: str, tabela: str = "pt_atos") -> str:
    """Um código que o caminho do ato conhece pela receita medida."""
    return next(iter(ATR.itens_de_custa_do_ato(AS.caminho_do_ato(tabela, ato))))


# ------------------------------------------------- a recusa antes de lavrar


@pytest.mark.parametrize("ato", ATOS_QUE_SELAM)
def test_sem_item_o_ato_que_sela_e_recusado_antes(ato):
    with pytest.raises(PSELO.SeloSemItemError) as erro:
        PSELO.conferir_antes_de_lavrar(ato, [])
    texto = str(erro.value)
    assert "nada foi gravado" in texto
    assert PSELO.O_ATO[ato] in texto
    assert "Cobrar no caixa" in texto        # diz o que fazer
    assert erro.value.regra == PSELO.REGRA_SEM_ITEM
    assert not erro.value.vencivel
    # REGRA DA CASA: erro de regra é ValueError, com mensagem pronta — e é da
    # família que as rotas do Protesto já tratam como recusa.
    assert isinstance(erro.value, ValueError)
    assert isinstance(erro.value, AS.AtoError)


@pytest.mark.parametrize("ato", ATOS_QUE_SELAM)
def test_com_item_da_receita_o_ato_passa(ato):
    codigo = _da_receita(ato)
    assert PSELO.conferir_antes_de_lavrar(ato, [codigo]) is None
    assert PSELO.conferir_antes_de_lavrar(ato, lambda: [codigo]) is None


@pytest.mark.parametrize("ato", sorted(PSELO.ATOS_SEM_SELO_PROPRIO))
def test_o_ato_sem_selo_proprio_nao_e_conferido(ato):
    assert PSELO.conferir_antes_de_lavrar(ato, []) is None


def test_o_selo_digitado_e_o_robo_nao_sao_conferidos():
    """É o espelho da rota: o selo digitado à mão dispensa o pedido, e o robô
    não pede selo (o ato dele fica pendente, e vira obrigação)."""
    PSELO.conferir_antes_de_lavrar("PAGAMENTO", [], selo_digitado=True)
    PSELO.conferir_antes_de_lavrar("PAGAMENTO", [], selo_automatico=False)


def test_a_lista_de_itens_so_se_pede_quando_o_ato_sela():
    perguntas = []

    def itens():
        perguntas.append(1)
        return []

    PSELO.conferir_antes_de_lavrar("APONTAMENTO", itens)
    PSELO.conferir_antes_de_lavrar("PAGAMENTO", itens, selo_digitado=True)
    assert perguntas == []
    with pytest.raises(PSELO.SeloSemItemError):
        PSELO.conferir_antes_de_lavrar("PAGAMENTO", itens)
    assert perguntas == [1]


@pytest.mark.parametrize("tipo", ["NEGATIVA", "POSITIVA"])
def test_a_certidao_sela_sempre_e_tem_a_frase_dela(tipo):
    with pytest.raises(PSELO.SeloSemItemError) as erro:
        PSELO.conferir_antes_de_lavrar(tipo, [], tabela="pt_certidoes")
    assert str(erro.value).startswith("Certidão NÃO emitida, e nada foi gravado")
    assert PSELO.conferir_antes_de_lavrar(
        tipo, [_da_receita(tipo, "pt_certidoes")], tabela="pt_certidoes") is None


def test_o_protocolo_escolhido_sem_item_livre_diz_isso():
    """Quem escolheu o protocolo e não marcou item precisa saber que o
    protocolo é que está vazio — senão marca de novo o mesmo protocolo."""
    with pytest.raises(PSELO.SeloSemItemError) as erro:
        PSELO.conferir_antes_de_lavrar("CANCELAMENTO", [],
                                       protocolo_escolhido=True)
    assert "protocolo escolhido não tem item livre" in str(erro.value)
    with pytest.raises(PSELO.SeloSemItemError) as erro:
        PSELO.conferir_antes_de_lavrar("CANCELAMENTO", [])
    assert "protocolo escolhido" not in str(erro.value)


def test_sem_caminho_de_selo_recusa():
    """A retirada não tem caminho próprio no lançamento: sem caminho o selo
    não se monta, e afirmar não resolve."""
    assert AS.caminho_do_ato("pt_atos", "RETIRADA") is None
    with pytest.raises(PSELO.SeloNaoVaiSairError) as erro:
        PSELO.conferir_antes_de_lavrar("RETIRADA", ["17.4"])
    assert erro.value.regra == PSELO.REGRA_SEM_CAMINHO
    assert not erro.value.vencivel


def test_sem_a_data_da_tabela_recusa_e_diz_onde_informar():
    with pytest.raises(PSELO.SeloNaoVaiSairError) as erro:
        PSELO.conferir_antes_de_lavrar("PAGAMENTO", ["17.2"], data_da_tabela="")
    assert erro.value.regra == PSELO.REGRA_SEM_DATA_DA_TABELA
    assert "Administrativo → Selador" in str(erro.value)
    # O que não veio não se confere; a data boa passa.
    PSELO.conferir_antes_de_lavrar("PAGAMENTO", ["17.2"], data_da_tabela=None)
    PSELO.conferir_antes_de_lavrar("PAGAMENTO", ["17.2"],
                                   data_da_tabela="2026-01-01")


def test_o_titulo_sem_protocolo_recusa_e_a_certidao_nao_pede():
    """O envelope do Protesto exige o protocolo do título — que nasce no
    apontamento. A certidão não tem título: leva o protocolo «0» medido."""
    with pytest.raises(PSELO.SeloNaoVaiSairError) as erro:
        PSELO.conferir_antes_de_lavrar("DESISTENCIA", ["17.2"],
                                       titulo={"protocolo": None})
    assert erro.value.regra == PSELO.REGRA_SEM_PROTOCOLO_DO_TITULO
    assert "aponte o título" in str(erro.value)
    PSELO.conferir_antes_de_lavrar("DESISTENCIA", ["17.2"],
                                   titulo={"protocolo": "2610290001"})
    PSELO.conferir_antes_de_lavrar("NEGATIVA", ["17.5.1"], tabela="pt_certidoes",
                                   titulo={"protocolo": None})


def test_o_caixa_fechado_recusa_quando_o_item_vai_ser_cobrado():
    with pytest.raises(PSELO.SeloNaoVaiSairError) as erro:
        PSELO.conferir_antes_de_lavrar("CANCELAMENTO", ["17.2"],
                                       vai_cobrar_no_caixa=True,
                                       caixa_aberto=False)
    assert erro.value.regra == PSELO.REGRA_CAIXA_FECHADO
    assert "não tem caixa aberto" in str(erro.value)
    # Sem cobrança no caixa (o item do protocolo, o diferido), o caixa fechado
    # não impede o selo.
    PSELO.conferir_antes_de_lavrar("CANCELAMENTO", ["17.2"],
                                   vai_cobrar_no_caixa=False, caixa_aberto=False)


def test_o_4127_e_recusado_antes_dizendo_quais_itens_servem():
    """O ato 4127 (título 1353, 29/10/2026 às 08h43): o cancelamento com os
    itens 17.1.7 e 17.4.5 do protocolo — faixas que o aparelho não conhece.
    Agora a recusa é antes, e diz quais servem."""
    with pytest.raises(PSELO.SeloNaoVaiSairError) as erro:
        PSELO.conferir_antes_de_lavrar("CANCELAMENTO", ["17.1.7", "17.4.5"])
    texto = str(erro.value)
    assert erro.value.regra == PSELO.REGRA_ITEM_FORA_DO_CAMINHO
    assert erro.value.vencivel
    assert "17.1.7" in texto and "17.4.5" in texto
    for serve in ATR.itens_de_custa_do_ato("/selo/protesto/baixa-cancelamento"):
        assert serve in texto
    assert "Afirmo" in texto


def test_a_afirmacao_expressa_vence_o_item_fora_do_caminho():
    aceita = PSELO.conferir_antes_de_lavrar(
        "CANCELAMENTO", ["17.8"], afirmo=True, afirmacao=AFIRMACAO_BOA)
    assert aceita["regra"] == PSELO.REGRA_ITEM_FORA_DO_CAMINHO
    assert aceita["afirmacao"] == AFIRMACAO_BOA
    assert "17.8" in aceita["o_que_faltava"]


@pytest.mark.parametrize("afirmo,texto", [
    (True, "Afirmo que serve."),                     # poucas letras
    (False, AFIRMACAO_BOA),                          # sem a caixa
    (True, "Afirmo ......... ......... ........."),  # pontuação não conta
])
def test_a_afirmacao_pela_metade_continua_sendo_a_trava(afirmo, texto):
    with pytest.raises(PSELO.SeloNaoVaiSairError) as erro:
        PSELO.conferir_antes_de_lavrar("CANCELAMENTO", ["17.8"],
                                       afirmo=afirmo, afirmacao=texto)
    assert erro.value.vencivel
    assert "afirmação expressa está incompleta" in str(erro.value)


def test_a_afirmacao_nao_vence_as_travas_que_o_aparelho_nao_perdoa():
    """Sem item, sem data, sem protocolo do título, sem caixa: o selo não sai
    de jeito nenhum, e afirmar não muda o que o aparelho precisa receber."""
    for chamada in (
            dict(itens=[]),
            dict(itens=["17.2"], data_da_tabela=""),
            dict(itens=["17.2"], titulo={"protocolo": ""}),
            dict(itens=["17.2"], vai_cobrar_no_caixa=True, caixa_aberto=False)):
        itens = chamada.pop("itens")
        with pytest.raises(PSELO.SeloNaoVaiSairError) as erro:
            PSELO.conferir_antes_de_lavrar("CANCELAMENTO", itens, afirmo=True,
                                           afirmacao=AFIRMACAO_BOA, **chamada)
        assert not erro.value.vencivel


def test_a_faixa_vira_o_item_so_onde_o_caminho_conhece_o_item():
    """O E-Ofício mandou 17.4 em 190 selos de pagamento e retirada, e 17.1 em
    70 de protesto; o aparelho recusou o 17.4.5 e o 17.1.7. No cancelamento o
    17.4 não é item do caminho — e lá a faixa fica como está, para a
    conferência recusá-la."""
    assert PSELO.codigo_para_o_selo("17.4.5", "/selo/protesto/pagamento") == "17.4"
    assert PSELO.codigo_para_o_selo("17.4.5", "/selo/protesto/retirada") == "17.4"
    assert PSELO.codigo_para_o_selo("17.1.7", "/selo/protesto/titulo") == "17.1"
    assert PSELO.codigo_para_o_selo(
        "17.4.5", "/selo/protesto/baixa-cancelamento") == "17.4.5"
    assert PSELO.codigo_para_o_selo("17.10.1", "/selo/protesto/pagamento") == "17.10.1"
    assert PSELO.codigo_para_o_selo(" 17.2 ", "/selo/protesto/pagamento") == "17.2"
    # E a faixa mapeada passa na conferência do pagamento.
    PSELO.conferir_antes_de_lavrar(
        "PAGAMENTO", [PSELO.codigo_para_o_selo("17.4.5", "/selo/protesto/pagamento")])


def test_a_rota_le_a_mesma_lista_e_a_mesma_regua_do_selo():
    """Duas réguas para «há item?» divergiriam no primeiro conserto: a recusa
    diria uma coisa e o selo faria outra."""
    fonte = (RAIZ / "atribuicoes_web.py").read_text(encoding="utf-8")
    assert "atos_sem_selo_proprio = PSELO.ATOS_SEM_SELO_PROPRIO" in fonte
    # o selo (depois), o ato e a certidão (antes): a mesma função
    assert fonte.count("_itens_do_selo_do_protesto(con,") >= 3
    assert fonte.count("PSELO.conferir_antes_de_lavrar(") == 2
    # o desfeito grava o motivo pela mesma constante que a pendência lê
    assert "f\"{PSELO.PREFIXO_DO_DESFEITO}: {motivo_selo}\"" in fonte


def test_o_espelho_da_trava_do_selo_pago_usa_as_mesmas_pecas():
    """`_nao_pagos` não escreve, e por isso não chama `cobrir_o_selo`: espelha
    o passo do protocolo com as MESMAS peças. Se a trava trocar de peça, este
    teste obriga a olhar o espelho."""
    fonte_trava = (RAIZ / "ato_selado.py").read_text(encoding="utf-8")
    for peca in ("CXP.itens_para_o_selo", "CXP.item_gratuito", "CXP.item_pago",
                 "CXP.item_diferido", "DEP.pagar_item"):
        assert peca in fonte_trava, peca
    fonte = (RAIZ / "protesto_selo_previo.py").read_text(encoding="utf-8")
    for peca in ("CXP.itens_para_o_selo", "CXP.item_gratuito", "CXP.item_pago",
                 "CXP.item_diferido", "DEP.do_protocolo"):
        assert peca in fonte, peca


# --------------------------------------------------------------- o banco


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_pt_schema(con)
    init_selador_schema(con)
    return con


def _titulo(con, situacao: str, *, chave: str, numero: str) -> int:
    return int(nativo(con).escrever(
        """INSERT INTO pt_titulos(especie, numero_titulo, protocolo,
               valor_centavos, saldo_centavos, situacao, origem, origem_chave,
               criado_em)
           VALUES ('DMI', %s, %s, 10000, 10000, %s, 'CRA', %s, %s)
           RETURNING id""",
        (numero, "2610290001", situacao, chave, AGORA))[0]["id"])


def _ato(con, titulo_id: int, tipo: str, *, cancelado: bool = False,
         motivo: str | None = None, por: str = "MARIO EXEMPLO DOS SANTOS",
         origem: str = "MANUAL", selo: str | None = None,
         quando: str = AGORA) -> int:
    return int(nativo(con).escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json, origem,
               cancelado, motivo_cancelamento, criado_em, criado_por, selo)
           VALUES (%s, %s, %s, '{}', %s, %s, %s, %s, %s, %s) RETURNING id""",
        (titulo_id, tipo, quando[:10], origem, 1 if cancelado else 0, motivo,
         quando, por, selo))[0]["id"])


def test_a_regua_do_item_e_a_receita_mais_o_que_o_aparelho_aceitou():
    """O 4106 (28/10/2026) saiu pelo caminho do cancelamento com 17.7, 17.9 e
    17.10.1 — nenhum na receita medida do E-Ofício. A receita sozinha teria
    recusado um ato que o aparelho aceitou."""
    con = banco()
    caminho = "/selo/protesto/baixa-cancelamento"
    assert "17.9" not in ATR.itens_de_custa_do_ato(caminho)
    with pytest.raises(PSELO.SeloNaoVaiSairError):
        PSELO.conferir_antes_de_lavrar("CANCELAMENTO", ["17.9"], con=con)
    nativo(con).escrever(
        """INSERT INTO sd_selos(numero, obtido_em, caminho, tabela, ato_id,
               referencia, atribuicao)
           VALUES ('AVESVD000000NARRKWVNJCRSVO21', %s, %s, 'pt_atos', 9,
                   'pt_atos:9:17.9:1', 'PROTESTO')""", (AGORA, caminho))
    assert PSELO.conferir_antes_de_lavrar("CANCELAMENTO", ["17.9"], con=con) is None


@pytest.fixture()
def casa():
    con = banco()
    ids = {}
    # O 9614: o pagamento foi desfeito pelo selo, e o título ficou PAGO.
    ids["desfeito"] = t = _titulo(con, "PAGO", chave="t:desfeito", numero="T1")
    _ato(con, t, "APONTAMENTO")
    ids["ato_desfeito"] = _ato(con, t, "PAGAMENTO", cancelado=True,
                               motivo="Selo não emitido: sem item.")
    # Os quatro do acervo: a carga trouxe PAGO sem o ato de pagamento.
    ids["acervo"] = t = _titulo(con, "PAGO", chave="tbAvisoProtesto:7",
                                numero="T2")
    _ato(con, t, "APONTAMENTO", origem="EOFICIO")
    # Protestado sem protesto nenhum, e não é do acervo.
    ids["sem_ato"] = _titulo(con, "PROTESTADO", chave="t:sem", numero="T3")
    # OS QUE ESTÃO EM ORDEM, e não podem aparecer:
    ids["refeito"] = t = _titulo(con, "CANCELADO", chave="t:refeito", numero="T4")
    _ato(con, t, "CANCELAMENTO", cancelado=True, motivo="Selo não emitido: x")
    _ato(con, t, "CANCELAMENTO", cancelado=True, motivo="Selo não emitido: y")
    _ato(con, t, "CANCELAMENTO")                    # lançado de novo, válido
    t = _titulo(con, "DESISTIDO", chave="t:retirada", numero="T5")
    _ato(con, t, "RETIRADA", origem="EOFICIO")      # a retirada sustenta
    _titulo(con, "RECEBIDO", chave="t:recebido", numero="T6")  # não pede ato
    t = _titulo(con, "PAGO", chave="t:pago", numero="T7")
    _ato(con, t, "PAGAMENTO")
    ids["em_ordem"] = t
    # O 1353 antes do conserto: três tentativas desfeitas, nenhuma de pé.
    ids["tres"] = t = _titulo(con, "PROTESTADO", chave="t:tres", numero="T8")
    _ato(con, t, "APONTAMENTO", origem="EOFICIO")
    _ato(con, t, "PROTESTO", origem="EOFICIO")
    _ato(con, t, "INTIMACAO", origem="EOFICIO")    # gravada depois, no acervo
    for i in range(3):
        _ato(con, t, "CANCELAMENTO", cancelado=True,
             motivo=f"Selo não emitido: tentativa {i + 1}.",
             quando=f"2026-10-29T08:4{i}:00")
    # O robô: protesto válido e sem selo. E um de gente sem selo (o lote).
    ids["robo"] = t = _titulo(con, "PROTESTADO", chave="t:robo", numero="T9")
    _ato(con, t, "APONTAMENTO")
    _ato(con, t, "INTIMACAO", por="MARIO EXEMPLO DOS SANTOS", selo="AVESVD1")
    ids["ato_do_robo"] = _ato(con, t, "PROTESTO", por="Robô do Protesto")
    t = _titulo(con, "PROTESTADO", chave="t:lote", numero="T10")
    _ato(con, t, "PROTESTO", por="MARIO EXEMPLO DOS SANTOS")
    return con, ids


def test_a_conferencia_acha_a_situacao_sem_ato_e_diz_por_que(casa):
    con, ids = casa
    achados = {x["titulo_id"]: x for x in PSELO.titulos_sem_ato_que_sustente(con)}
    assert set(achados) == {ids["desfeito"], ids["acervo"], ids["sem_ato"]}

    desfeito = achados[ids["desfeito"]]
    assert desfeito["origem"] == "DESFEITO"
    assert desfeito["desfeito_id"] == ids["ato_desfeito"]
    assert desfeito["ato_esperado"] == "pagamento"
    assert "Selo não emitido: sem item" in desfeito["explicacao"]
    assert "continuou PAGO" in desfeito["explicacao"]
    assert desfeito["situacao_sustentada"] == "APONTADO"

    assert achados[ids["acervo"]]["origem"] == "ACERVO"
    assert "carga do E-Ofício" in achados[ids["acervo"]]["explicacao"]
    assert achados[ids["sem_ato"]]["origem"] == "SEM_ATO"
    assert achados[ids["sem_ato"]]["ato_esperado"] == "protesto"
    assert achados[ids["sem_ato"]]["situacao_sustentada"] == "RECEBIDO"


def test_a_conferencia_de_um_titulo_so_serve_a_ficha(casa):
    con, ids = casa
    assert PSELO.situacao_sem_ato(con, ids["desfeito"])["origem"] == "DESFEITO"
    assert PSELO.situacao_sem_ato(con, ids["em_ordem"]) is None


def test_a_conferencia_tem_teto(casa):
    con, _ids = casa
    assert len(PSELO.titulos_sem_ato_que_sustente(con, limite=1)) == 1


def test_a_situacao_sustentada_nao_segue_a_ordem_dos_ids_do_acervo(casa):
    """O 1353 tem a intimação gravada DEPOIS do protesto (a carga do acervo):
    pela ordem dos ids ele estaria INTIMADO, e está PROTESTADO."""
    con, ids = casa
    assert PSELO.situacao_sustentada(con, ids["tres"]) == "PROTESTADO"
    assert PSELO.situacao_sustentada(con, ids["refeito"]) == "CANCELADO"
    assert PSELO.situacao_sustentada(con, ids["sem_ato"]) == "RECEBIDO"


def test_o_ato_desfeito_pelo_selo_e_obrigacao_ate_ser_lancado(casa):
    con, ids = casa
    pend = PSELO.pendencias_do_selo(con)
    refazer = {(p["titulo_id"], p["tipo"]): p for p in pend
               if p["especie"] == PSELO.ESPECIE_REFAZER}
    # o 9614 e o 1353-de-antes; o refeito saiu sozinho, porque é calculado
    assert set(refazer) == {(ids["desfeito"], "PAGAMENTO"),
                            (ids["tres"], "CANCELAMENTO")}
    tres = refazer[(ids["tres"], "CANCELAMENTO")]
    assert tres["tentativas"] == 3
    assert tres["motivo"] == "tentativa 3"
    assert tres["quem_tentou"] == "MARIO EXEMPLO DOS SANTOS"
    assert tres["quando_br"] == "29/10/2026"
    # E SOME SOZINHA quando o ato é lançado de novo, depois.
    _ato(con, ids["tres"], "CANCELAMENTO")
    assert (ids["tres"], "CANCELAMENTO") not in {
        (p["titulo_id"], p["tipo"]) for p in PSELO.pendencias_do_selo(con)}
    # por título, para a ficha
    assert [p["tipo"] for p in PSELO.pendencias_do_selo(
        con, titulo_id=ids["desfeito"])] == ["PAGAMENTO"]


def test_o_contrato_do_roteiro(casa):
    """O roteiro do dia (#104, `protesto_roteiro.GANCHOS`) lê as duas listas
    por nome e mostra `numero_titulo`, `protocolo` e `explicacao` de cada
    linha, com o link pelo `titulo_id`. Linha sem eles vira um JSON cru na tela
    da escrevente."""
    import protesto_roteiro as ROT
    nomes = {(g["modulo"], g["funcao"]) for g in ROT.GANCHOS}
    assert ("protesto_selo_previo", "pendencias_do_selo") in nomes
    assert ("protesto_selo_previo", "titulos_sem_ato_que_sustente") in nomes
    con, ids = casa
    pend = PSELO.pendencias_do_selo(con)
    sem = PSELO.titulos_sem_ato_que_sustente(con)
    assert pend and sem
    for linha in pend + sem:
        assert {"titulo_id", "numero_titulo", "protocolo", "explicacao"} <= set(linha)
        assert linha["numero_titulo"] and linha["protocolo"] == "2610290001"
        assert linha["explicacao"].strip()
    [tres] = [p for p in pend if p["titulo_id"] == ids["tres"]]
    assert tres["numero_titulo"] == "T8"
    assert "3 tentativas" in tres["explicacao"]
    assert "sai da lista quando o ato for lançado" in tres["explicacao"].lower()


def test_o_ato_do_robo_sem_selo_e_obrigacao_e_o_de_gente_nao(casa):
    """O robô não pede selo (regra de 05/10/2026): o ato dele fica para o
    escrevente selar. O de gente sem selo (o lote, que não sela) e o do
    acervo não entram — esta lista é a do robô."""
    con, ids = casa
    selar = [p for p in PSELO.pendencias_do_selo(con)
             if p["especie"] == PSELO.ESPECIE_SELAR]
    assert [p["ato_id"] for p in selar] == [ids["ato_do_robo"]]
    assert "robô" in selar[0]["motivo"]


def test_a_correcao_de_oficio_exige_afirmacao_e_volta_ao_que_os_atos_sustentam(casa):
    con, ids = casa
    with pytest.raises(PSELO.SituacaoError):
        PSELO.corrigir_situacao_de_oficio(con, ids["desfeito"], afirmo=False,
                                          afirmacao="")
    with pytest.raises(PSELO.SituacaoError) as erro:
        PSELO.corrigir_situacao_de_oficio(con, ids["desfeito"], afirmo=True,
                                          afirmacao="Afirmo que sim.")
    assert "30 letras" in str(erro.value)
    feito = PSELO.corrigir_situacao_de_oficio(
        con, ids["desfeito"], afirmo=True,
        afirmacao=("Afirmo, sob minha responsabilidade, que o pagamento deste "
                   "título não aconteceu: o selo falhou e ele não voltou."))
    assert feito["regra"] == PSELO.REGRA_SITUACAO_SEM_ATO
    assert (feito["situacao_antes"], feito["situacao_nova"]) == ("PAGO", "APONTADO")
    assert "pagamento" in feito["o_que_faltava"]
    assert nativo(con).valor("SELECT situacao FROM pt_titulos WHERE id = %s",
                             (ids["desfeito"],)) == "APONTADO"
    assert PSELO.situacao_sem_ato(con, ids["desfeito"]) is None
    # e nada a corrigir onde a situação está em ordem
    with pytest.raises(PSELO.SituacaoError):
        PSELO.corrigir_situacao_de_oficio(con, ids["em_ordem"], afirmo=True,
                                          afirmacao=AFIRMACAO_BOA)


def test_a_afirmacao_vai_para_o_detalhe_do_ato(casa):
    con, ids = casa
    afirmacao = {"regra": PSELO.REGRA_ITEM_FORA_DO_CAMINHO,
                 "afirmacao": AFIRMACAO_BOA, "o_que_faltava": "o item 17.8"}
    PSELO.anotar_afirmacao_no_ato(con, ids["ato_desfeito"], afirmacao,
                                  quem="MARIO EXEMPLO DOS SANTOS", agora=AGORA)
    import json
    detalhe = json.loads(nativo(con).valor(
        "SELECT detalhe_json FROM pt_atos WHERE id = %s", (ids["ato_desfeito"],)))
    [gravada] = detalhe[PSELO.CHAVE_NO_DETALHE]
    assert gravada["regra"] == PSELO.REGRA_ITEM_FORA_DO_CAMINHO
    assert gravada["por"] == "MARIO EXEMPLO DOS SANTOS"


def test_toda_situacao_que_pede_ato_e_conferida():
    """A régua não pode esquecer uma situação: as finais e as do caminho.
    RECEBIDO é a única que não pede ato — é o título antes de qualquer um."""
    import protesto as PT
    pedem = set(PT.SITUACOES_TITULO) - {"RECEBIDO"}
    assert set(PSELO.ATO_QUE_SUSTENTA) == pedem
    for tipos in PSELO.ATO_QUE_SUSTENTA.values():
        assert set(tipos) <= set(PT.TIPOS_ATO)
    assert set(PSELO.SITUACAO_DO_ATO.values()) == pedem


def _literais_por_funcao(caminho: Path) -> dict[str, list[str]]:
    """Os literais de texto de cada função de topo, sem docstring."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    saida: dict[str, list[str]] = {}
    for f in arvore.body:
        if not isinstance(f, ast.FunctionDef):
            continue
        doc = (f.body[0].value if f.body and isinstance(f.body[0], ast.Expr)
               and isinstance(f.body[0].value, ast.Constant) else None)
        saida[f.name] = [n.value for n in ast.walk(f)
                         if isinstance(n, ast.Constant) and isinstance(n.value, str)
                         and n is not doc]
    return saida


def test_so_duas_funcoes_escrevem():
    """«Não corrija dado da produção; só mostre» — a conferência só lê. Quem
    escreve é a anotação da afirmação (dentro da transação do ato que ela
    permitiu) e a correção de ofício (com afirmação, pela rota do oficial)."""
    quem_escreve = set()
    for nome, textos in _literais_por_funcao(RAIZ / "protesto_selo_previo.py").items():
        for texto in textos:
            alto = texto.upper()
            if any(c in alto for c in ("INSERT ", "UPDATE ", "DELETE ",
                                       "ALTER ", "DROP ")):
                quem_escreve.add(nome)
    assert quem_escreve == {"anotar_afirmacao_no_ato",
                            "corrigir_situacao_de_oficio"}


def test_o_sql_novo_nao_aumenta_o_acoplamento():
    """Módulo novo entra com zero — a regra de `tests/test_portabilidade.py`."""
    for textos in _literais_por_funcao(RAIZ / "protesto_selo_previo.py").values():
        for texto in textos:
            baixo = texto.lower()
            for proibido in ("substr(", "||", "strftime(", "julianday(",
                             "pragma"):
                assert proibido not in baixo, (proibido, texto[:60])
