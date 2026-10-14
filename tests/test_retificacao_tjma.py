"""A retificação de área e o georreferenciamento, lidos no Código de Normas.

O PEDIDO DO OFICIAL, 29/08/2026:

    «vamos criar o módulo de processos de retificação de área e
     georreferenciamento»
    «para o módulo do processo de georreferenciamento, leve em conta o código de
     normas do tjma que esta na pasta downloads»

O QUE ESTES TESTES GUARDAM
    Que a **leitura fecha**. `fora_das_secoes()` acha qualquer artigo que eu
    tenha citado de outra parte do Código achando que era daqui — que é o engano
    que eu quase cometi no usucapião, onde escrevi que a Seção XIV terminava no
    760 quando o 761 é dela.

    Ali o que me salvou foi ir ler o cabeçalho da seção seguinte. Aqui a
    conferência é automática, e roda em toda suíte.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rt_tjma as RT                                             # noqa: E402


# ------------------------------------------------ a leitura fecha


def test_as_tres_secoes_sao_as_do_indice_do_codigo():
    """As faixas saem do índice do próprio Código, e ele confere consigo mesmo:
    a Seção VIII começa no 621, o que fecha a VII em 620."""
    assert [(s["secao"], s["do"], s["ao"]) for s in RT.SECOES] == [
        ("V", 587, 605), ("VI", 606, 609), ("VII", 610, 620)]


def test_nenhum_artigo_citado_cai_fora_das_secoes():
    """O CONFERIDOR DA MINHA PRÓPRIA LEITURA, e é o teste mais importante deste
    arquivo. Artigo citado de outra parte do Código aparece aqui."""
    fora = RT.fora_das_secoes()
    assert not fora, f"artigos citados fora das seções medidas: {fora}"


def test_as_faixas_nao_se_sobrepoem_nem_deixam_buraco():
    """Seção que termina onde a seguinte começa — ou uma das duas está errada."""
    for anterior, seguinte in zip(RT.SECOES, RT.SECOES[1:]):
        assert anterior["ao"] + 1 == seguinte["do"], (
            f"a Seção {anterior['secao']} termina em {anterior['ao']} e a "
            f"{seguinte['secao']} começa em {seguinte['do']}")


# ------------------------------------------------ o que a norma exige


def test_o_art_592_tem_os_nove_incisos():
    assert len(RT.DOCUMENTOS_DO_ART_592) == 9
    assert [x["inciso"] for x in RT.DOCUMENTOS_DO_ART_592] == [
        "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"]


def test_sao_duas_plantas_e_nao_uma():
    """Os incisos II e III: a da área como fica e a da área como está na
    matrícula. Quem levar só a primeira volta com nota devolutiva."""
    ii = RT.DOCUMENTOS_DO_ART_592[1]
    iii = RT.DOCUMENTOS_DO_ART_592[2]
    assert "ÁREA RETIFICADA" in ii["o_que"]
    assert "COMO ESTÁ NA MATRÍCULA" in iii["o_que"]


def test_a_planta_pede_utm_sirgas_2000():
    """É o mesmo sistema de coordenadas que o usucapião exige, e por isso os
    dois módulos falam a mesma língua com o profissional."""
    texto = " ".join(x["detalhe"] for x in RT.DOCUMENTOS_DO_ART_592)
    assert "SIRGAS 2000" in texto


def test_o_checklist_do_rural_traz_ccir_itr_car_e_sigef():
    itens = RT.checklist(georreferenciada=False, rural=True)
    texto = " ".join(x["o_que"] for x in itens)
    for exigido in ("CCIR", "ITR", "CAR", "SIGEF"):
        assert exigido in texto


def test_o_checklist_do_urbano_nao_pede_ccir():
    """Exigência que não se aplica é exigência que o cliente cumpre à toa — e
    pedir CCIR de apartamento é o caso."""
    itens = RT.checklist(georreferenciada=False, rural=False)
    texto = " ".join(x["o_que"] for x in itens)
    assert "CCIR" not in texto
    assert "cadastro imobiliário" in texto      # o inciso IX, que é do urbano


def test_cada_imovel_perde_exatamente_um_inciso():
    """O VII é do rural e o IX é do urbano: um dos dois sempre sai."""
    rural = {x["inciso"] for x in RT.checklist(georreferenciada=False,
                                               rural=True)}
    urbano = {x["inciso"] for x in RT.checklist(georreferenciada=False,
                                                rural=False)}
    assert "VII" in rural and "IX" not in rural
    assert "IX" in urbano and "VII" not in urbano
    assert len(rural) == len(urbano) == 8


def test_o_georreferenciamento_acrescenta_a_certificacao_do_incra():
    itens = RT.checklist(georreferenciada=True, rural=True)
    texto = " ".join(x["o_que"] for x in itens)
    assert "certificados pelo INCRA" in texto
    assert len(itens) == 8 + len(RT.DOCUMENTOS_DO_GEORREFERENCIAMENTO)


# ------------------------------------------------ os prazos


def test_todos_os_prazos_sao_em_dias_uteis_menos_o_do_sigef():
    """O art. 620 § 2º escreve «30 (trinta) dias», sem qualificar. Inventar
    «úteis» ali daria à serventia mais prazo do que a norma deu."""
    corridos = [p["chave"] for p in RT.PRAZOS if not p["uteis"]]
    assert corridos == ["SIGEF"]


def test_o_prazo_do_sigef_e_da_serventia_e_de_trinta_dias():
    """É a obrigação que nasce DEPOIS do ato, quando o cliente já foi embora —
    e é o tipo de prazo que se perde."""
    p = RT.prazo("SIGEF")
    assert p["dias"] == 30
    assert p["de_quem"] == "A_SERVENTIA"
    assert p["artigo"] == "art. 620, § 2º"


def test_o_prazo_de_impugnacao_conta_para_cada_notificado():
    """Contar um prazo só para todos faria a averbação sair antes de o último
    notificado ter tido os seus quinze dias."""
    assert "INDIVIDUALMENTE" in RT.prazo("IMPUGNAR")["o_que"]


def test_prazo_que_nao_existe_e_recusado_com_a_lista():
    with pytest.raises(KeyError) as erro:
        RT.prazo("PRAZO_INVENTADO")
    assert "SIGEF" in str(erro.value)


def test_o_modulo_nao_calcula_data():
    """Contar dia útil é do núcleo, que já conhece os feriados desta comarca.
    Uma segunda contagem divergiria da prenotação e da do edital do usucapião —
    e num prazo, divergir por um dia é recomeçar o prazo."""
    codigo = (RAIZ / "rt_tjma.py").read_text(encoding="utf-8")
    for proibido in ("timedelta", "date.today", "datetime.now"):
        assert proibido not in codigo, f"o módulo calcula data com {proibido}"


# ------------------------------------------------ as duas regras opostas


def test_o_silencio_vale_anuencia():
    assert RT.SILENCIO_VALE_ANUENCIA["artigo"] == "art. 599, § 1º"
    assert "presumida a anuência" in RT.SILENCIO_VALE_ANUENCIA["o_que"]


def test_mas_a_impugnacao_atrasada_ainda_entra_ate_a_averbacao():
    """AS DUAS PUXAM PARA LADOS OPOSTOS, e é isso que o módulo tem de guardar.
    Um sistema que trate «prazo vencido» como «acabou» erraria — e erraria
    contra quem não foi ouvido."""
    assert RT.IMPUGNACAO_ATRASADA_ENTRA["artigo"] == "art. 599, § 3º"
    assert "ANTES DA AVERBAÇÃO" in RT.IMPUGNACAO_ATRASADA_ENTRA["o_que"]


# ------------------------------------------------ o que contraria a intuição


def test_nao_ha_limite_de_aumento_nem_de_reducao_de_area():
    """É o oposto do que a intuição diz, e é regra expressa — art. 589 § 2º."""
    assert "NÃO HÁ LIMITE" in RT.SEM_LIMITE_DE_AREA["o_que"]
    assert RT.SEM_LIMITE_DE_AREA["artigo"] == "art. 589, § 2º"


def test_o_requerimento_nao_gera_prioridade():
    """Ao contrário da prenotação, que existe justamente para dar prioridade."""
    assert "NÃO gera" in RT.NAO_GERA_PRIORIDADE["o_que"]


def test_ha_lista_do_que_a_norma_DISPENSA():
    """Ela evita o balcão inseguro exigir o que a norma dispensa — mesmo motivo
    da lista do «o que não impede» do usucapião."""
    assert len(RT.DISPENSAS) >= 6
    texto = " ".join(x["o_que"] for x in RT.DISPENSAS)
    assert "Dispensada a anuência prévia do credor real" in texto


# ------------------------------------------------ a notificação


def test_o_edital_e_o_ultimo_da_ordem():
    """O art. 598 diz «caso frustradas as tentativas anteriores» — é uma ordem,
    e não uma lista de opções."""
    formas = [x["forma"] for x in RT.COMO_NOTIFICAR]
    assert formas[0] == "PESSOAL"
    assert formas[-1] == "EDITAL"
    assert "frustradas as tentativas anteriores" in RT.COMO_NOTIFICAR[-1]["o_que"]


def test_so_contam_os_confrontantes_das_divisas_afetadas():
    texto = " ".join(x["o_que"] for x in RT.QUEM_E_CONFRONTANTE)
    assert "divisas AFETADAS" in texto


# ------------------------------------------------ o desfecho


def test_os_dois_ritos_terminam_com_matricula_nova_e_a_velha_encerrada():
    """É a maior operação registral que este sistema vai encostar."""
    for desfecho in (RT.DESFECHO_DA_RETIFICACAO,
                     RT.DESFECHO_DO_GEORREFERENCIAMENTO):
        texto = " ".join(x["o_que"] for x in desfecho)
        assert "NOVA matrícula" in texto
        assert "ENCERRA" in texto or "Encerra-se" in texto


def test_o_desfecho_do_georreferenciamento_termina_no_sigef():
    ultimo = RT.DESFECHO_DO_GEORREFERENCIAMENTO[-1]
    assert "SIGEF" in ultimo["o_que"]
    assert ultimo["artigo"] == "art. 620, § 2º"


# ------------------------------------------------ o módulo não decide


def test_o_modulo_nao_decide_nem_guarda_nada():
    """Ele é a NORMA, e não o processo. Quem decide é o delegatário e quem lavra
    é a tela do RI — que tem a corrente de hash, o selo e os emolumentos."""
    codigo = (RAIZ / "rt_tjma.py").read_text(encoding="utf-8")
    for comando in ("INSERT ", "UPDATE ", "DELETE ", "sqlite3"):
        assert comando not in codigo, f"o módulo faz {comando.strip()}"
    publicos = [n for n in dir(RT) if not n.startswith("_")]
    for nome in publicos:
        for proibido in ("averbar", "lavrar", "decidir", "julgar", "registrar"):
            assert proibido not in nome.lower(), f"`{nome}` decide, e não devia"


# ------------------------------------------------ as duas espécies são da casa


def test_as_duas_especies_sao_as_que_esta_casa_ja_escreveu():
    """Medido nas 1.508 fichas com teor: a casa já escreveu «AVERBAÇÃO DE
    RETIFICAÇÃO DE ÁREA GEORREFERENCIADA» e «… NÃO GEORREFERENCIADA». **A
    distinção é dela, e não minha.**"""
    assert set(RT.NOME_DA_ESPECIE) == {RT.GEORREFERENCIADA,
                                       RT.NAO_GEORREFERENCIADA}


def test_os_dois_fundamentos_do_art_213_sao_distintos():
    """Deixar o balcão escolher seria deixar corrigir de ofício o que precisa da
    anuência do vizinho — e o vizinho descobre quando vai vender."""
    assert set(RT.NOME_DO_FUNDAMENTO) == {RT.DE_OFICIO, RT.A_REQUERIMENTO}
    assert "de ofício" in RT.NOME_DO_FUNDAMENTO[RT.DE_OFICIO]
    assert "requerimento" in RT.NOME_DO_FUNDAMENTO[RT.A_REQUERIMENTO]
