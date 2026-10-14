"""As nove comunicações do Registro Civil, num painel só.

O QUE ESTES TESTES GUARDAM
    **Que o nove é somado, e não escrito.** Escrevendo a soma eu me corrigi: o
    cabeçalho dizia sete linhas e são seis. Número escrito à mão envelhece na
    tarde em que se escreve.

    **Que o painel não engole erro.** `ajuda_projeto` chamava função que não
    existia e um `except` largo virava «zero pendências», quando eram nove.

    **Que o trimestre que vence não é o trimestre que se reporta.** O dia 8 de
    outubro entrega julho, agosto e setembro — e o IBGE é o único destino com
    multa em dinheiro.
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_obrigacoes as OB                                       # noqa: E402

SENHA = "Senha#12345"


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------ o nove se conta


def test_sao_nove_destinos_e_o_numero_e_somado():
    """A linha do art. 226 vale por quatro. **O nove não está escrito em lugar
    nenhum do módulo**: é a soma dos destinos de cada linha."""
    assert OB.quantos_destinos() == 9
    assert len(OB.OBRIGACOES) == 6


def test_a_linha_do_art_226_vale_por_quatro():
    """Juiz eleitoral, Economia, Receita e Instituto de Identificação — as quatro
    saem no mesmo movimento e com o mesmo prazo, e cada uma tem o seu filtro."""
    linha = [x for x in OB.OBRIGACOES if x["chave"] == "OBITO_MENSAL"][0]
    assert linha["destinos"] == 4
    assert "art. 226" in linha["artigo"]


def test_cada_linha_tem_artigo_prazo_e_tela():
    """Exigência sem endereço é exigência que ninguém confere."""
    for o in OB.OBRIGACOES:
        assert o["artigo"], f"{o['chave']} sem artigo"
        assert o["prazo"], f"{o['chave']} sem prazo"
        assert o["tela"], f"{o['chave']} sem tela"
        assert o["modulo"], f"{o['chave']} sem módulo"


def test_a_junta_militar_esta_marcada_como_fora_do_codigo():
    """Ela é da Lei 4.375/1964, e por isso quase se perdeu: quem lê só o Código
    de Normas não a encontra."""
    assert "JUNTA_MILITAR" in OB.FORA_DO_CODIGO_DE_NORMAS
    linha = [x for x in OB.OBRIGACOES if x["chave"] == "JUNTA_MILITAR"][0]
    assert "4.375" in linha["artigo"]


def test_a_ordem_e_a_do_aperto():
    """É nessa ordem que se decide o que fazer agora, e não na ordem em que os
    módulos foram escritos."""
    ordem = [x["chave"] for x in OB.por_aperto()]
    assert ordem[0] == "SIRC"       # 1 dia útil
    assert ordem[-1] == "IBGE"      # trimestral
    assert [x["aperto"] for x in OB.por_aperto()] == sorted(
        x["aperto"] for x in OB.OBRIGACOES)


def test_so_o_sirc_e_o_ibge_tem_sancao_escrita():
    """Onde a sanção existe, ela aparece; onde não existe, não se inventa."""
    com = {x["chave"] for x in OB.OBRIGACOES if x["sancao"]}
    assert com == {"SIRC", "OBITO_MENSAL", "IBGE"}


# ------------------------------------------------ o prazo do IBGE


def test_o_ibge_vence_dia_oito_de_quatro_meses():
    """Art. 224, e é o único destino com **multa em dinheiro** — de 1 a 5
    salários mínimos, «sem prejuízo da ação penal»."""
    assert OB.IBGE_DIA == 8
    assert OB.IBGE_MESES == (1, 4, 7, 10)


def test_o_trimestre_que_vence_nao_e_o_que_se_reporta():
    """O dia 8 de outubro entrega julho, agosto e setembro. Rotular o vencimento
    com o trimestre em que ele cai poria o arquivo com o período errado numa
    obrigação que tem multa."""
    r = OB.ibge_vence_em("2026-08-29")
    assert r["vence_em"] == "2026-10-08"
    assert r["trimestre_reportado"] == 3
    assert r["meses_reportados"] == (7, 8, 9)


def test_o_vencimento_de_janeiro_reporta_o_ano_anterior():
    r = OB.ibge_vence_em("2027-01-05")
    assert r["vence_em"] == "2027-01-08"
    assert r["trimestre_reportado"] == 4
    assert r["ano_reportado"] == 2026
    assert r["meses_reportados"] == (10, 11, 12)


def test_o_dia_do_vencimento_ainda_conta_como_dentro_do_prazo():
    """No dia 8 ainda dá para mandar — faltam zero dias, e não passou."""
    r = OB.ibge_vence_em("2026-10-08")
    assert r["vence_em"] == "2026-10-08"
    assert r["faltam"] == 0


def test_data_impossivel_recusa_com_frase_de_balcao():
    with pytest.raises(OB.ObrigacoesError):
        OB.ibge_vence_em("2026-02-30")
    with pytest.raises(OB.ObrigacoesError):
        OB.ibge_vence_em("ontem")


# ------------------------------------------------ o painel mede


def test_o_painel_traz_as_seis_linhas(casa):
    linhas = OB.painel(_con(casa))
    assert len(linhas) == 6
    assert [x["chave"] for x in linhas][0] == "SIRC"


def test_casa_vazia_da_zero_nas_que_se_contam(casa):
    for linha in OB.painel(_con(casa)):
        assert linha["erro"] == "", f"{linha['chave']}: {linha['erro']}"
        if linha.get("mede") != "PRAZO":
            assert linha["quantas"] == 0


def test_o_ibge_mostra_prazo_E_contagem(casa):
    """**ATÉ 30/08/2026 ELA SÓ MOSTRAVA O PRAZO**, e declarava o buraco: o
    sistema montava o mapa e não guardava o que saiu. `ib_entregas` fechou isso.

    As duas respondem perguntas diferentes — quantos trimestres estão em atraso,
    e quando vence o próximo —, e num prazo trimestral saber que faltam zero hoje
    não diz quando começar a montar o de amanhã.
    """
    linha = [x for x in OB.painel(_con(casa), hoje="2026-08-29")
             if x["chave"] == "IBGE"][0]
    assert linha["quantas"] == 0          # casa vazia, nada em atraso
    assert linha["erro"] == ""
    assert linha["vence_em"] == "2026-10-08"


def test_o_buraco_do_ibge_foi_fechado_e_saiu_da_declaracao():
    """**BURACO FECHADO QUE CONTINUA DECLARADO É O CARIMBO QUE MENTE OUTRA
    VEZ**: ele responde, e responde errado — quem lesse planejaria trabalho já
    feito."""
    linha = [x for x in OB.OBRIGACOES if x["chave"] == "IBGE"][0]
    assert not linha.get("buraco")


def test_so_o_ibge_se_mede_por_prazo():
    """Se outra linha virasse «PRAZO», ela deixaria de contar o que espera — e
    isso tem de ser escolha visível, não descuido."""
    assert [x["chave"] for x in OB.OBRIGACOES
            if x.get("mede") == "PRAZO"] == ["IBGE"]


def test_nenhuma_linha_declara_buraco_ja_fechado():
    """A regra continua valendo — buraco declarado é buraco que alguém pode
    fechar —, mas a declaração tem de sair no dia em que ele se fecha. Hoje não
    há nenhum: se voltar a haver, ele entra em `buraco` e a tela o mostra."""
    for o in OB.OBRIGACOES:
        if o.get("buraco"):
            assert len(o["buraco"]) > 20,                 f"{o['chave']} declara buraco sem dizer qual"


def test_o_painel_conta_o_que_espera(casa):
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',1,'MARIA','2026-08-20','2026-08-18',
                       'ATIVO','SISTEMA','2026-08-20T09:00')""")
    por_chave = {x["chave"]: x for x in OB.painel(con)}
    assert por_chave["SIRC"]["quantas"] == 1


def test_modulo_que_nao_responde_nao_vira_zero():
    """ZERO MEDIDO E ZERO POR ENGANO SÃO A MESMA TELA E COISAS DIFERENTES. Um
    `except Exception: return []` transformou, em `ajuda_projeto`, uma função
    inexistente em «zero pendências» — quando eram nove."""
    r = OB._quantas("modulo_que_nao_existe_mesmo", None)
    assert r["quantas"] is None
    assert "não carregou" in r["erro"]


def test_modulo_sem_por_onde_contar_diz_isso():
    r = OB._quantas("json", None)
    assert r["quantas"] is None
    assert "não tem por onde contar" in r["erro"]


# ------------------------------------------------ o painel não comunica


def test_o_painel_nao_faz_comunicacao_nenhuma():
    """Ele pergunta a cada módulo quantas esperam e mostra as seis lado a lado.
    Quem manda é a tela de cada uma."""
    publicos = [n for n in dir(OB)
                if not n.startswith("_") and callable(getattr(OB, n))]
    for nome in publicos:
        for proibido in ("enviar", "montar", "registrar_envio", "gerar"):
            assert proibido not in nome.lower(), f"`{nome}` faz o que não deve"


def test_o_painel_nao_marca_nada_como_resolvido(casa):
    """Resolver é o clique de quem fez."""
    codigo = (RAIZ / "rc_obrigacoes.py").read_text(encoding="utf-8")
    for proibido in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert proibido not in codigo, f"o painel escreve com «{proibido}»"
