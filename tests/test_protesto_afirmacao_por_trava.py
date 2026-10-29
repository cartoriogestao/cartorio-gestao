"""UMA AFIRMAÇÃO EXPRESSA POR TRAVA — a integração do Protesto, 29/10/2026.

A ordem do oficial («se insistir em algo que é erro, precisa afirmar
expressamente e deixar log») virou, nos PRs #105 a #119, uma dúzia de travas.
Na integração apareceu o que nenhum PR via sozinho: no formulário do
protesto UMA caixa só (`afirmo` + `afirmacao`) vencia ao mesmo tempo a prova
da intimação (#106), o item do selo (#109), o irmão (#113) e a CENPROT (#105),
e cada trava gravava a sua linha com o MESMO texto. E a régua da afirmação
tinha seis cópias, três delas contando a frase de abertura nas 30 letras.

O QUE ESTES TESTES GUARDAM
  - a régua é uma só (`afirmacoes_expressas`): 30 letras ALÉM da frase de
    abertura — inclusive escrita sem as vírgulas —, e robô não afirma;
  - as cópias que sobraram chamam a régua (o selo, a CENPROT, os irmãos);
  - `uma_por_trava`: a caixa comum vence uma trava; com duas, recusa e diz
    quais; o mesmo texto em duas regras é recusado;
  - `vencer_todas` (a entrega e o comprovante do aviso): o mesmo, regra a regra;
  - os códigos das regras que a tela dos avisos desenha são os do domínio;
  - a ficha desenha um campo por trava quando a prova e o irmão pedem juntos,
    a rota recusa a caixa comum e o texto repetido, e grava uma linha por
    regra, cada uma com o seu texto;
  - os ganchos do roteiro ligados na integração (#116, #119) e a conduta 10
    lendo a lista do #118.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import afirmacoes_expressas as AFX  # noqa: E402
import protesto_prova as PROVA  # noqa: E402
import protesto_roteiro as PR  # noqa: E402
import protesto_selo_previo as PSELO  # noqa: E402
import protesto_titulos_irmaos as IRM  # noqa: E402
from test_protesto_titulos_irmaos import (AFIRMACAO_BOA, MOTIVO,  # noqa: E402,F401
                                          _con_tela, _lancar,
                                          _parcelas_na_tela, s)

FRASE = AFX.MODELO
OUTRA = (f"{FRASE} o canhoto do edital está na pasta do dia e será "
         f"escaneado e anexado amanhã cedo")
SELO_DIGITADO = "AVESVD000000NARRKWVNJCRSVO21"


# ----------------------------------------------------------- a régua, uma só

def test_a_frase_de_abertura_nao_conta_nas_trinta_letras():
    assert AFX.letras_alem_da_frase(FRASE) == 0
    # sem as vírgulas é a mesma frase — pela grafia, as 33 letras dela contariam
    assert AFX.letras_alem_da_frase("Afirmo sob minha responsabilidade que") == 0
    assert AFX.texto_valido(FRASE + ".") is None
    assert AFX.texto_valido(OUTRA) == OUTRA
    # quem escreve só o resto afirmou a frase toda
    resto = "o devedor declarou no balcão que pagava a parcela de junho"
    assert AFX.texto_valido(resto) == f"{FRASE} {resto}"


def test_robo_nao_afirma_e_a_caixa_e_obrigatoria():
    with pytest.raises(AFX.AfirmacaoError, match="robô"):
        AFX.validar(True, OUTRA, robo=True)
    with pytest.raises(AFX.AfirmacaoError, match="Afirmo"):
        AFX.validar(False, OUTRA)
    assert AFX.validar(True, OUTRA) == OUTRA


def test_as_copias_que_sobraram_chamam_a_regua():
    """A frase sozinha passava no selo (a cópia dele contava a frase)."""
    with pytest.raises(PSELO.SituacaoError):
        PSELO.validar_afirmacao(True, FRASE + " que sim.")
    assert PSELO.validar_afirmacao(True, OUTRA) == OUTRA
    with pytest.raises(PSELO.SituacaoError, match="robô"):
        PSELO.validar_afirmacao(True, OUTRA, robo=True)
    assert PROVA.afirmacao_valida(OUTRA) == AFX.texto_valido(OUTRA)
    assert IRM._letras(OUTRA) == AFX.letras_alem_da_frase(OUTRA)
    assert PROVA.PISO_DA_AFIRMACAO == PSELO.MINIMO_DE_LETRAS_DA_AFIRMACAO == \
        IRM.MINIMO_DE_LETRAS == AFX.MINIMO_DE_LETRAS


def test_nenhum_modulo_do_protesto_conta_letras_da_afirmacao_por_conta_propria():
    """A régua mora num lugar só. Quem precisar dela chama
    `afirmacoes_expressas`; uma sétima cópia divergiria no primeiro conserto."""
    for nome in ("protesto_prova.py", "cenprot_conferencia.py",
                 "protesto_selo_previo.py", "protesto_titulos_irmaos.py",
                 "config_de_cobranca.py", "protesto_roteiro.py",
                 "protesto_retorno.py"):
        texto = (RAIZ / nome).read_text(encoding="utf-8")
        assert '"Afirmo, sob minha responsabilidade, que"' not in texto, nome
        assert not re.search(r"(MINIMO_DE_LETRAS\w*|PISO_DA_AFIRMACAO)\s*=\s*30\b",
                             texto), nome


# ----------------------------------------------------------- uma por trava

def _vencida(trava, regra, texto, comum):
    return {"trava": trava, "regra": regra, "afirmacao": texto,
            "o_que_faltava": f"falta de {trava}", "campo_comum": comum}


def test_a_caixa_comum_vence_uma_trava_so():
    AFX.uma_por_trava([_vencida("prova", "R1", OUTRA, True)])
    with pytest.raises(AFX.AfirmacoesSeparadasError) as erro:
        AFX.uma_por_trava([_vencida("prova", "R1", OUTRA, True),
                           _vencida("irmaos", "R2", OUTRA, True)])
    assert [t["trava"] for t in erro.value.travas] == ["prova", "irmaos"]
    assert "cada uma pede a SUA" in str(erro.value)


def test_o_mesmo_texto_em_duas_regras_e_recusado():
    with pytest.raises(AFX.AfirmacoesSeparadasError, match="mesmo texto"):
        AFX.uma_por_trava([_vencida("prova", "R1", OUTRA, False),
                           # pontuação e caixa não fazem de um texto colado um novo
                           _vencida("selo", "R2", OUTRA.upper() + "!!", False)])
    AFX.uma_por_trava([_vencida("prova", "R1", OUTRA, False),
                       _vencida("irmaos", "R2", AFIRMACAO_BOA, False)])


def test_vencer_todas_pede_uma_afirmacao_por_regra():
    faltas = [(PROVA.REGRA_ENTREGA, "falta o nome de quem recebeu"),
              (PROVA.REGRA_OUTRO_AVISO, "o arquivo é o de outro aviso")]
    # a caixa comum não vale para as duas
    with pytest.raises(PROVA.ProvaError, match="caixa comum"):
        PROVA.vencer_todas(faltas, OUTRA, abertura="A entrega não se registra")
    # o mesmo texto nos dois campos também não
    with pytest.raises(PROVA.ProvaError, match="mesmo texto"):
        PROVA.vencer_todas(faltas, {PROVA.REGRA_ENTREGA: OUTRA,
                                    PROVA.REGRA_OUTRO_AVISO: OUTRA},
                           abertura="A entrega não se registra")
    feitas = PROVA.vencer_todas(
        faltas, {PROVA.REGRA_ENTREGA: OUTRA,
                 PROVA.REGRA_OUTRO_AVISO: AFIRMACAO_BOA},
        abertura="A entrega não se registra")
    assert [(f["regra"], f["afirmacao"]) for f in feitas] == [
        (PROVA.REGRA_ENTREGA, OUTRA), (PROVA.REGRA_OUTRO_AVISO, AFIRMACAO_BOA)]
    # uma regra só: a caixa comum serve, como sempre serviu
    [uma] = PROVA.vencer_todas(faltas[:1], OUTRA, abertura="A entrega")
    assert uma["afirmacao"] == OUTRA


def test_a_tela_dos_avisos_desenha_os_codigos_do_dominio():
    macro = (RAIZ / "templates" / "_protesto_afirmacao.html").read_text(
        encoding="utf-8")
    trecho = macro.split("macro afirmacao_por_regra", 1)[1]
    codigos = re.findall(r"\('([A-Z_]+)',", trecho.split("<details", 1)[0])
    assert tuple(codigos) == PROVA.REGRAS_DO_AVISO


# ----------------------------------------------------------- a ficha e a rota

def _intimar_sem_prova_e_pagar(s, *, intimado: int, pago: int) -> None:
    """O irmão posterior PAGO (trava do #113) e o intimado por edital SEM o
    comprovante do envio (trava do #106): as duas pedem afirmação no mesmo
    protesto."""
    con = _con_tela(s)
    with con:
        con.execute("UPDATE pt_titulos SET situacao='INTIMADO' WHERE id=?",
                    (intimado,))
        con.execute("UPDATE pt_titulos SET situacao='PAGO' WHERE id=?", (pago,))
        for tipo, data, detalhe in (("APONTAMENTO", "2026-08-18", "{}"),
                                    ("INTIMACAO", "2026-08-20",
                                     '{"modo": "EDITAL"}')):
            con.execute(
                """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                       origem, criado_em) VALUES (?,?,?,?,'MANUAL',?)""",
                (intimado, tipo, data, detalhe, "2026-10-29T10:00:00"))
    con.close()


def _protestos(s) -> int:
    con = _con_tela(s)
    n = con.execute("SELECT COUNT(*) FROM pt_atos WHERE tipo='PROTESTO'"
                    ).fetchone()[0]
    con.close()
    return n


def test_a_prova_e_o_irmao_no_mesmo_protesto_pedem_uma_afirmacao_cada(s):
    p1, p2 = _parcelas_na_tela(s)
    _intimar_sem_prova_e_pagar(s, intimado=p1, pago=p2)
    ficha = s["c"].get(f"/protesto/{p1}").get_data(as_text=True)
    assert 'name="afirmo_prova"' in ficha and 'name="afirmo_irmaos"' in ficha
    assert "data-afirmacao-por-trava" in ficha

    # a caixa comum não vence as duas travas
    html = _lancar(s, p1, ato="PROTESTO", motivo_atraso=MOTIVO, afirmo="1",
                   afirmacao=OUTRA, selo=SELO_DIGITADO)
    assert "cada uma pede a SUA" in html
    assert _protestos(s) == 0

    # o mesmo texto nos dois campos também não
    html = _lancar(s, p1, ato="PROTESTO", motivo_atraso=MOTIVO,
                   afirmo_prova="1", afirmacao_prova=OUTRA,
                   afirmo_irmaos="1", afirmacao_irmaos=OUTRA,
                   selo=SELO_DIGITADO)
    assert "mesmo texto" in html
    assert _protestos(s) == 0

    # cada uma com a sua: lavra, e cada regra fica na auditoria com o seu texto
    _lancar(s, p1, ato="PROTESTO", motivo_atraso=MOTIVO,
            afirmo_prova="1", afirmacao_prova=OUTRA,
            afirmo_irmaos="1", afirmacao_irmaos=AFIRMACAO_BOA,
            selo=SELO_DIGITADO)
    assert _protestos(s) == 1
    con = _con_tela(s)
    linhas = con.execute(
        "SELECT details FROM audit_logs WHERE action='AFIRMACAO_EXPRESSA'"
    ).fetchall()
    con.close()
    por_regra = {json.loads(r["details"])["regra"]:
                 json.loads(r["details"])["afirmacao"] for r in linhas}
    assert por_regra[PROVA.REGRA_PROTESTO] == OUTRA
    assert por_regra[IRM.REGRA_PROTESTO] == AFIRMACAO_BOA


# ----------------------------------------------------------- o roteiro

def test_os_ganchos_ligados_na_integracao():
    por_funcao = {(g["modulo"], g["funcao"]): g for g in PR.GANCHOS}
    cra = por_funcao[("protesto_desistencia", "pendencias_da_cra")]
    assert not cra.get("nome_a_confirmar")
    pix = por_funcao[("protesto_pix", "pendencias_do_pix")]
    assert pix["conduta"] == "repasse"
    assert pix.get("com_o_dia") and pix.get("prazo_da_peca")
    assert ("cenprot_conferencia", "quantos_divergem") in por_funcao
    # a lista do repasse NÃO é gancho: as etapas sem guia apareceriam duas vezes
    assert ("protesto_repasse", "pendencias_do_repasse") not in por_funcao
    fonte = (RAIZ / "protesto_roteiro.py").read_text(encoding="utf-8")
    corpo = fonte.split("def _cobrar_repasse", 1)[1].split("\ndef ", 1)[0]
    assert "pendencias_do_repasse(" in corpo and "REP.pendentes(" not in corpo


def test_o_gancho_com_prazo_da_peca_respeita_o_atrasado(monkeypatch):
    import types
    modulo = types.ModuleType("peca_com_prazo")
    vistos = {}

    def pendencias(con, *, hoje=None, feriados=None):
        vistos["hoje"] = hoje
        return [{"titulo_id": 7, "explicacao": "crédito sem pagamento",
                 "atrasado": True},
                {"titulo_id": 8, "explicacao": "PIX de hoje", "atrasado": False}]
    modulo.pendencias = pendencias
    monkeypatch.setitem(sys.modules, "peca_com_prazo", modulo)
    g = {"chave": "peca_com_prazo", "conduta": "repasse", "rotulo": "teste",
         "modulo": "peca_com_prazo", "funcao": "pendencias", "de_onde": "teste",
         "com_o_dia": True, "prazo_da_peca": True}
    from datetime import date, datetime
    ctx = {"agora": datetime(2026, 10, 29, 10), "hoje": date(2026, 10, 29),
           "dia": "2026-10-29", "ate": "2026-10-29~", "feriados": set(),
           "dia_util": True}
    o = PR._rodar_gancho(None, ctx, g)
    assert vistos["hoje"] == "2026-10-29"
    assert o["situacao"] == PR.ATRASADO and o["atrasados"] == 1
