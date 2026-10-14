"""A notificacao do usucapiao — relatos #30 e #21 do oficial.

O QUE ESTES TESTES GUARDAM

    **Que a regra e IMPORTADA da retificacao, e nao recopiada.** O art. 754
    manda aplicar, na notificacao de confrontante, «no que couber, o
    procedimento de retificacao de registro» — e este sistema ja leu esses
    artigos. Copiar produziria duas listas para divergirem no primeiro
    conserto: e a `normalizar_nome` pela quinta vez neste projeto.

    **Que a procedencia de cada prazo fica marcada.** MEDIDO e o que se leu no
    PDF que esta na casa; CITADO vem da Lei de Registros Publicos, cujo texto
    nao foi lido aqui dentro. Prazo errado numa notificacao nao aparece como
    erro — aparece como impugnacao perdida meses depois.

    **Que o edital e o ultimo, e a ordem e da norma.** «Caso frustradas as
    tentativas anteriores» (art. 598). Oferecer o edital de saida faria a
    serventia publicar sem ter tentado, e o edital custa e demora.

    **Que o papel recusa ANTES de imprimir.** Notificacao com buraco e papel
    que alguem assina sem ver, e o buraco so aparece quando o notificado disser
    que nao entendeu do que foi notificado.

    **Que o recibo vai no MESMO papel.** O que prova a notificacao e o
    comprovante que volta assinado; recibo em folha separada e o que se perde.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rt_tjma as RT                                             # noqa: E402
import us_notificacao as UN                                      # noqa: E402


PROCESSO = {
    "numero": "3", "ano": 2026, "modalidade": "ORDINARIA",
    "modalidade_rotulo": "Ordinária",
    "requerente_nome": "JOÃO BATISTA DE SOUSA",
    "imovel_descricao": "Um terreno urbano medindo 12m de frente por 30m de "
                        "fundo, na Rua das Flores",
    "imovel_endereco": "Rua das Flores, s/n", "imovel_municipio": "Cidade Exemplo",
    "imovel_uf": "MA", "imovel_area": "360,00 m²",
    "posse_tempo_alegado": "há mais de quinze anos",
}
SERVENTIA = {"oficial": "MARIO EXEMPLO DOS SANTOS", "cargo": "Oficial",
             "nome": "Serventia Extrajudicial de Cidade Exemplo/MA"}
NOTIFICACAO = {
    "destinatario": "MARIA DAS DORES SOUSA",
    "destinatario_papel": "Confrontante ao norte",
    "endereco": "Rua do Comércio, 45, Centro, Cidade Exemplo/MA",
    "forma": "PESSOAL", "prazo_dias": 15, "prazo_chave": "CONFRONTANTE",
}


# ------------------------------------------- a regra vem da retificacao


def test_as_formas_sao_as_MESMAS_da_retificacao_e_nao_uma_copia():
    """**Art. 754 manda aplicar a retificacao**, e copiar faria as duas
    divergirem no primeiro conserto."""
    assert UN.FORMAS is RT.COMO_NOTIFICAR, \
        "as formas foram copiadas em vez de importadas"
    assert UN.ONDE is RT.ONDE_NOTIFICAR


def test_a_remissao_ao_artigo_que_a_autoriza_esta_escrita():
    """Regra importada sem dizer de onde vem é regra que ninguém confere."""
    assert "754" in UN.BASE_DA_REMISSAO["artigo"]
    assert "retifica" in UN.BASE_DA_REMISSAO["o_que"].lower()


# ------------------------------------------------------ os prazos


def test_cada_prazo_diz_de_onde_veio():
    """MEDIDO é o que se leu no PDF da casa; CITADO é da lei não lida aqui."""
    for p in UN.PRAZOS:
        assert p["procedencia"] in (UN.MEDIDO, UN.CITADO), p
        assert p["base"], f"o prazo {p['chave']} não diz o artigo"


def test_o_prazo_do_titular_tabular_e_declarado_como_CITADO():
    """**Ele vem da LRP, cujo texto não foi lido dentro da casa.**

    Marcá-lo como medido seria dar ao número uma procedência que ele não tem —
    e quem fosse conferir procuraria no Código de Normas um artigo que está na
    Lei de Registros Públicos.
    """
    p = UN.prazo("TITULAR_TABULAR")
    assert p["procedencia"] == UN.CITADO
    assert "216-A" in p["base"]


def test_os_prazos_do_confrontante_saem_do_codigo_lido():
    p = UN.prazo("CONFRONTANTE")
    assert p["procedencia"] == UN.MEDIDO
    assert "599" in p["base"] and "754" in p["base"]
    assert p["dias"] == 15 and p["uteis"] is True


def test_o_prazo_e_contado_individualmente_e_o_texto_diz_isso():
    """Contar de um marco comum encurta o prazo de quem recebeu depois."""
    assert "individualmente" in UN.prazo("CONFRONTANTE")["o_que"].lower()


def test_prazo_que_nao_existe_diz_os_que_existem():
    with pytest.raises(UN.NotificacaoError) as e:
        UN.prazo("QUANDO_DER")
    assert "CONFRONTANTE" in str(e.value)


def test_a_consequencia_do_silencio_fica_junto_do_prazo():
    """**O silêncio é concordância**, e o prazo errado para menos produz
    anuência de quem ainda podia impugnar."""
    assert "concord" in UN.SILENCIO_CONCORDA["o_que"].lower()
    assert UN.SILENCIO_CONCORDA["procedencia"] == UN.CITADO


# ------------------------------------------------------ a ordem das formas


def test_o_edital_e_o_ultimo():
    assert UN.ORDEM_DAS_FORMAS[-1] == UN.FORMA_DE_ULTIMO_RECURSO == "EDITAL"


def test_a_forma_seguinte_respeita_a_ordem_da_norma():
    """«Caso frustradas as tentativas anteriores» — art. 598."""
    assert UN.forma_seguinte([]) == "PESSOAL"
    assert UN.forma_seguinte(["PESSOAL"]) == "RTD"
    assert UN.forma_seguinte(["PESSOAL", "RTD"]) == "CORREIO"
    assert UN.forma_seguinte(["PESSOAL", "RTD", "CORREIO"]) == "EDITAL"


def test_esgotadas_as_formas_nao_se_inventa_uma_quinta():
    """Devolve `None`: aí não é a vez de escolher forma, é a vez de decidir."""
    assert UN.forma_seguinte(list(UN.ORDEM_DAS_FORMAS)) is None


# ------------------------------------------------------ o papel


def test_o_papel_recusa_antes_de_imprimir():
    """Notificação com buraco é papel que alguém assina sem ver."""
    sem_endereco = dict(NOTIFICACAO, endereco="")
    with pytest.raises(UN.NotificacaoError) as e:
        UN.montar(processo=PROCESSO, notificacao=sem_endereco,
                  serventia=SERVENTIA)
    assert "Endereço" in str(e.value)


def test_forma_que_nao_e_da_norma_e_recusada():
    with pytest.raises(UN.NotificacaoError) as e:
        UN.montar(processo=PROCESSO,
                  notificacao=dict(NOTIFICACAO, forma="WHATSAPP"),
                  serventia=SERVENTIA)
    assert "PESSOAL" in str(e.value)


def test_o_papel_traz_o_que_a_notificacao_tem_de_dizer():
    papel = UN.montar(processo=PROCESSO, notificacao=NOTIFICACAO,
                      serventia=SERVENTIA, hoje_extenso="Cidade Exemplo/MA, 30 de "
                                                        "agosto de 2026")
    for pedaco in ("MARIA DAS DORES SOUSA", "Confrontante ao norte",
                   "Rua do Comércio, 45", "USUCAPIÃO EXTRAJUDICIAL",
                   "216-A", "quinze", "JOÃO BATISTA DE SOUSA",
                   "Rua das Flores", "360,00 m²"):
        assert pedaco in papel, f"faltou «{pedaco}» no papel"


def test_o_recibo_vai_no_mesmo_papel():
    """**O que prova a notificação é o comprovante que volta assinado.**"""
    papel = UN.montar(processo=PROCESSO, notificacao=NOTIFICACAO,
                      serventia=SERVENTIA)
    assert "RECIBO" in papel
    assert "Assinatura" in papel
    assert "Nome de quem recebe" in papel


def test_o_papel_avisa_que_o_silencio_e_concordancia():
    """Quem recebe precisa saber o que acontece se não responder."""
    papel = UN.montar(processo=PROCESSO, notificacao=NOTIFICACAO,
                      serventia=SERVENTIA)
    assert "SILÊNCIO SERÁ INTERPRETADO COMO CONCORDÂNCIA" in papel


def test_o_que_nao_se_sabe_nao_se_afirma_no_papel():
    """**A posse alegada só entra se estiver no processo.**

    Uma frase genérica sobre posse num papel que a serventia assina é afirmação
    sobre fato que ninguém mediu.
    """
    sem_posse = {k: v for k, v in PROCESSO.items()
                 if k not in ("posse_tempo_alegado", "posse_inicio")}
    papel = UN.montar(processo=sem_posse, notificacao=NOTIFICACAO,
                      serventia=SERVENTIA)
    assert "alega posse" not in papel
    # e com posse, entra
    com = UN.montar(processo=PROCESSO, notificacao=NOTIFICACAO,
                    serventia=SERVENTIA)
    assert "alega posse há mais de quinze anos" in com


def test_o_papel_diz_por_qual_forma_foi_notificado():
    papel = UN.montar(processo=PROCESSO, notificacao=NOTIFICACAO,
                      serventia=SERVENTIA)
    assert "Pessoalmente" in papel and "598" in papel


# ------------------------------------------------------ o manual


def test_o_manual_tem_passo_a_passo_e_cada_um_diz_a_base():
    assert len(UN.MANUAL) >= 8
    for p in UN.MANUAL:
        assert p["o_que"] and p["como"], p
        assert "base" in p, f"o passo {p['passo']} não diz a base"


def test_o_manual_manda_notificar_o_credor_com_onus():
    """Art. 617 e 759: o ônus não impede, mas notificar é condição."""
    texto = " ".join(p["como"] for p in UN.MANUAL)
    assert "credores reais" in texto or "credores" in texto
    assert "759" in " ".join(str(p.get("base")) for p in UN.MANUAL)


def test_o_manual_diz_que_quem_assinou_a_planta_nao_se_notifica():
    """Notificar quem já anuiu é trabalho e custo que a norma não pede."""
    texto = " ".join(p["como"] for p in UN.MANUAL)
    assert "assinou a planta" in texto


def test_o_manual_traz_o_caso_da_ata_notarial():
    """Art. 595: sem conseguir identificar todos, o caminho é outro — e ele
    começa por uma ata notarial, não por um edital."""
    texto = " ".join(p["como"] for p in UN.MANUAL)
    assert "ATA NOTARIAL" in texto.upper()


# ------------------------------------------------------ os guardas


def test_o_modulo_nao_expede_nem_da_por_notificado():
    """**Ele monta o papel e diz o que falta.** Quem entrega é a serventia, e o
    que prova a entrega é o comprovante que volta."""
    codigo = (RAIZ / "us_notificacao.py").read_text(encoding="utf-8")
    for proibido in ("def expedir", "def entregar", "def dar_por_notificado",
                     "INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert proibido not in codigo, f"o módulo faz «{proibido}»"
