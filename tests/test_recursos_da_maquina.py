"""A RESERVA DE MAQUINA DO SERVIDOR — medida em 24/09/2026.

O QUE ESTES TESTES GUARDAM

    **Que o servidor nao volte a nascer ABAIXO DO NORMAL.** Era assim que ele
    estava, e ninguem tinha escolhido: o instalador registrava a tarefa sem
    `-Priority`, e o padrao do Agendador de Tarefas do Windows e 7, que o
    Windows traduz para BelowNormal. Com a maquina ocupada, o pior
    atendimento do `/saude` passava de 10 segundos; com a prioridade certa,
    0,23 s. E um defeito invisivel — nada quebra, tudo so demora — e por isso
    precisa de guarda escrita.

    **Que a reserva NUNCA derrube o arranque.** Ela roda antes de montar a
    aplicacao. Servidor que nao sobe porque o Windows negou uma preferencia
    de desempenho e pior do que servidor lento.

    **Que as duas reguas continuem dizendo a mesma coisa.** A tarefa do
    instalador e a reserva do proprio processo apontam as duas para ACIMA DO
    NORMAL. Se alguem mudar uma e esquecer a outra, o teste conta.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import recursos_da_maquina as REC                                # noqa: E402

so_no_windows = pytest.mark.skipif(os.name != "nt",
                                reason="a reserva de maquina so existe no Windows")


def test_a_reserva_NUNCA_levanta():
    """Ela roda antes de o servidor existir; falhar ali e ficar sem balcao."""
    quadro = REC.reservar()
    assert isinstance(quadro, dict)
    assert "aplicado" in quadro and "falhas" in quadro


def test_a_linha_do_arranque_diz_o_que_NAO_conseguiu():
    """«Reserva aplicada» sem dizer o que faltou e carimbo que mente."""
    texto = REC.linha_do_arranque(
        {"aplicado": ["prioridade de CPU acima do normal"],
         "falhas": ["piso de 192 MB: o Windows recusou (erro 1453)"]})
    assert "acima do normal" in texto
    assert "NAO CONSEGUI" in texto and "1453" in texto

    limpo = REC.linha_do_arranque({"aplicado": ["prioridade"], "falhas": []})
    assert "NAO CONSEGUI" not in limpo


def test_a_classe_escolhida_e_ACIMA_DO_NORMAL_e_nao_ALTA():
    """**Alta disputa com o proprio Windows** e ja travou teclado e mouse em
    maquina de atendimento. Acima do normal ganha de tudo que importa."""
    fonte = (RAIZ / "recursos_da_maquina.py").read_text(encoding="utf-8")
    # **O TESTE NAO OLHA O NOME DA VARIAVEL**: ele ja ficou vermelho uma vez
    # so porque o argumento passou de `eu` para `alvo`, sem a regra ter
    # mudado. O que importa e QUAL CLASSE se pede.
    assert "ABOVE_NORMAL_PRIORITY_CLASS)" in fonte
    assert "SetPriorityClass" in fonte
    for demais in ("HIGH_PRIORITY_CLASS)", "REALTIME_PRIORITY_CLASS)"):
        assert f"SetPriorityClass(alvo, {demais}" not in fonte
        assert f"SetPriorityClass(eu, {demais}" not in fonte


def test_a_tarefa_do_instalador_NAO_fica_no_padrao_do_Windows():
    """**O defeito que originou tudo isto.** Sem `-Priority`, o Agendador usa
    7 = BelowNormal. Medido em 24/09/2026: 3 -> AboveNormal, 4 e 5 -> Normal,
    7 -> BelowNormal."""
    fonte = (RAIZ / "installer" / "instalar_servidor.ps1").read_text(
        encoding="utf-8", errors="replace")
    registros = [linha for linha in fonte.splitlines()
                 if "New-ScheduledTaskSettingsSet" in linha
                 and not linha.strip().startswith("#")]
    assert registros, "ninguem registra mais a tarefa do servidor?"
    for linha in registros:
        assert "-Priority 3" in linha, (
            "a tarefa do servidor voltou ao padrao do Windows (7 = abaixo do "
            f"normal): {linha.strip()}")


def test_o_teto_do_conjunto_de_trabalho_fica_SOLTO():
    """Limitar o teto faria o Windows despejar paginas justamente enquanto o
    servidor monta um PDF grande — o contrario do que se quer."""
    fonte = (RAIZ / "recursos_da_maquina.py").read_text(encoding="utf-8")
    assert "QUOTA_LIMITS_HARDWS_MAX_DISABLE" in fonte
    assert "QUOTA_LIMITS_HARDWS_MAX_ENABLE" not in fonte


def test_o_servidor_reserva_ANTES_de_montar_a_aplicacao():
    """O arranque custa 7,8 s so para montar o app (medido). Reservar depois
    seria atravessar o pedaco mais caro ja rebaixado."""
    fonte = (RAIZ / "app.py").read_text(encoding="utf-8")
    corpo = fonte[fonte.index("def main():"):]
    assert "recursos_da_maquina" in corpo, "ninguem chama a reserva"
    assert (corpo.index("recursos_da_maquina.reservar()")
            < corpo.index("app = create_app()"))


def test_maquina_pequena_NAO_tem_memoria_presa():
    """O sistema tambem roda em maquina de balcao pequena, e prender 192 MB
    la tiraria do resto o que o resto precisa."""
    assert REC.RAM_MINIMA_DA_MAQUINA_MB > REC.RESIDENTE_GARANTIDO_MB


@so_no_windows
def test_a_situacao_le_o_que_a_reserva_escreveu():
    """Sem leitura, «reservei» e so uma frase — e frase nao se confere."""
    REC.reservar()
    agora = REC.situacao()
    assert agora["classe"] == REC.ABOVE_NORMAL_PRIORITY_CLASS
    assert agora["classe_por_extenso"] == "acima do normal"
    assert agora["prioridade_da_memoria"] == REC.MEMORY_PRIORITY_NORMAL
    assert agora["freio_de_eficiencia"] is False
    assert agora["piso_mb"] == REC.RESIDENTE_GARANTIDO_MB
    assert agora["piso_e_duro"] is True


@so_no_windows
def test_reservar_processo_INEXISTENTE_nao_levanta_e_diz_por_que():
    """Quem roda isto e o oficial, com o servidor no ar. Estourar na cara dele
    seria trocar um problema de desempenho por um erro de programa."""
    quadro = REC.reservar_processo(999_999_999)
    assert quadro["aplicado"] == []
    assert quadro["falhas"], "recusou e nao disse por que"
    assert "999999999" in " ".join(quadro["falhas"])


def test_o_acesso_negado_DIZ_que_e_preciso_administrador():
    """**O caso real desta casa.** O servidor roda como SYSTEM, e sem
    privilegio o Windows recusa ate abrir o processo — erro 5, que sozinho nao
    diz nada a quem esta no balcao."""
    fonte = (RAIZ / "recursos_da_maquina.py").read_text(encoding="utf-8")
    assert "codigo == 5" in fonte
    assert "administrador" in fonte


def test_as_duas_reservas_tem_UM_CORPO_SO():
    """Duas copias divergiriam no primeiro conserto, e a que ficasse para tras
    seria justamente a que o oficial roda a mao quando algo esta errado."""
    fonte = (RAIZ / "recursos_da_maquina.py").read_text(encoding="utf-8")
    assert fonte.count("SetPriorityClass(") == 1, (
        "ha mais de um lugar decidindo a prioridade do servidor")
    assert fonte.count("SetProcessWorkingSetSizeEx(") == 1


def test_o_script_do_balcao_conserta_a_TAREFA_e_o_PROCESSO():
    """**Uma sem a outra deixa um buraco que nao avisa.** So a tarefa nao
    ajuda hoje; so o processo se perde no proximo reinicio."""
    fonte = (RAIZ / "tools" / "reservar_a_maquina_do_balcao.ps1").read_text(
        encoding="utf-8", errors="replace")
    assert "Settings.Priority = 3" in fonte, "nao conserta a tarefa"
    assert "reservar_processo(" in fonte, "nao reserva o processo de pe"
    assert "-Conferir" in fonte, "nao tem modo que so mede"
    for perigo in ("Stop-ScheduledTask", "Restart-", "Stop-Process"):
        assert perigo not in fonte, (
            f"o script derruba o balcao ({perigo}); ele existe justamente "
            f"para nao precisar disso")


@so_no_windows
def test_a_medicao_do_processo_NAO_volta_zerada():
    """**O buraco que comeu a primeira medicao deste trabalho.** O
    pseudo-handle do processo e -1, e sem declarar os tipos o ctypes o corta
    ao meio: todos os degraus davam 0 MB."""
    agora = REC.situacao()
    assert agora["residente_mb"] > 0
    assert agora["commit_mb"] > 0
    assert agora["ram_da_maquina_mb"] > 0
