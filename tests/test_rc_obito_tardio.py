"""Obito fora do prazo — a regra que avisa.

O QUE ESTES TESTES GUARDAM
    **Que o sistema DIZ e nao LAVRA.** Excedido o prazo, o assento de obito so
    sai por determinacao judicial (art. 258). Um modulo que lavrasse aqui
    faria nascer assento sem competencia.

    **Que nao ha procedimento neste sistema.** Cheguei a montar um — fases,
    exigencias, acompanhamento em juizo — e o oficial mandou tirar. Quem
    instrui, inquire e decide e o juizo, ouvido o Ministerio Publico. Tela que
    finge acompanhar processo que corre no forum envelhece mentindo.

    **Que a exigencia da DO esta marcada como regra DA CASA.** O art. 254
    admitiria duas pessoas qualificadas onde nao houvesse medico; o oficial
    decidiu exigir a DO sempre. Quem ler daqui a dois anos precisa saber qual
    das duas coisas esta lendo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_obito_tardio as OT                                   # noqa: E402


def test_dentro_do_prazo_nao_avisa_nada():
    r = OT.situacao("2026-08-20", "2026-08-30")
    assert r["fora_do_prazo"] is False
    assert r["aviso"] == ""
    assert r["dias"] == 10


def test_fora_do_prazo_manda_ao_juizo():
    """**A frase e a razao de este arquivo existir.**"""
    r = OT.situacao("2026-06-01", "2026-08-30")
    assert r["fora_do_prazo"] is True
    assert "determinação judicial" in r["aviso"]
    assert "258" in r["artigo"]


def test_o_limite_e_o_do_dia_seguinte_e_nao_o_do_proprio_dia():
    """Quinze dias e quinze: no decimo quinto ainda da, no decimo sexto nao."""
    assert OT.esta_fora_do_prazo("2026-08-01", "2026-08-16") is False
    assert OT.esta_fora_do_prazo("2026-08-01", "2026-08-17") is True


def test_o_lugar_distante_tem_prazo_maior_e_nao_se_adivinha():
    """O art. 50 trata o lugar a mais de trinta quilometros da sede com prazo
    maior. **Quem sabe se o lugar e distante e quem esta atendendo** — por
    isso e parametro, e nao deducao do sistema."""
    assert OT.esta_fora_do_prazo("2026-06-01", "2026-08-30") is True
    assert OT.esta_fora_do_prazo("2026-06-01", "2026-08-30",
                                 distante=True) is False


def test_os_dias_sao_corridos():
    """O art. 78 nao qualifica o prazo, e prazo que a norma nao qualifica se
    conta corrido — a mesma leitura do art. 253, § 2º da FUNAI."""
    assert OT.dias_desde("2026-08-01", "2026-08-31") == 30


def test_o_aviso_diz_o_que_o_pedido_leva():
    """Avisar «vai a juizo» sem dizer o que o pedido leva deixa o balcao com o
    problema e sem o caminho."""
    r = OT.situacao("2026-01-01", "2026-08-30")
    assert "duas testemunhas" in r["o_que_o_pedido_leva"]
    assert "255" in r["o_que_o_pedido_leva"]
    assert "Ministério Público" in r["o_que_o_pedido_leva"]


def test_a_DO_sempre_esta_marcada_como_regra_da_casa():
    """Marcar o que e lei e o que e escolha nossa e o que impede a escolha de
    virar lei por repeticao."""
    assert OT.DECLARACAO_DE_OBITO_SEMPRE is True
    assert "desta casa" in OT.SOBRE_A_DO
    assert "254" in OT.SOBRE_A_DO


def test_data_ruim_recusa_em_portugues():
    for ruim in ("", None, "ontem", "31/08/2026"):
        with pytest.raises(OT.ObitoTardioError) as e:
            OT.dias_desde(ruim, "2026-08-30")
        assert "aaaa-mm-dd" in str(e.value)


def test_o_modulo_nao_lavra_nem_guarda_procedimento():
    """**Nao ha tabela, nao ha fase, nao ha acompanhamento.** O procedimento
    corre no juizo, e o oficial mandou tirar daqui."""
    codigo = (RAIZ / "rc_obito_tardio.py").read_text(encoding="utf-8")
    for proibido in ("INSERT INTO", "UPDATE ", "DELETE FROM", "CREATE TABLE",
                     "sqlite3"):
        assert proibido not in codigo, f"o módulo usa «{proibido}»"
    for palavra in ("FASES", "PROTOCOLADO", "DEFERIDO"):
        assert palavra not in codigo, (
            f"«{palavra}» é do procedimento que foi retirado — ele corre no "
            f"juízo, e não aqui")


def test_diz_que_nao_se_parece_com_o_nascimento_tardio():
    """A diferenca e o ponto principal: o nascimento tardio o oficial lavra
    (art. 249); o obito tardio, nao."""
    doc = OT.__doc__ or ""
    assert "249" in doc and "258" in doc
