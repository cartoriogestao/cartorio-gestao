"""A crítica do controle diário (`produtividade_agente`) — temas de 20/10/2026.

O item veio do sandbox sem teste (LH03). Os lançamentos do controle diário
caíam em «outros» ou num tema errado: a ida à escola do filho contava como
hora de trabalho sem tema, a qualificação do RI não tinha tema, «cumprindo
tarefa #117» virava tarefa «sem dizer quais», e «ajudando <colega>» nunca
casava, porque os nomes dos colegas eram lidos de uma chave (`full_name`) que
`pessoas()` não devolve. Os nomes aqui são FICTÍCIOS.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import produtividade_agente as PA  # noqa: E402
from bd_nativo import banco  # noqa: E402

SENHA = "Senha#12345"


@pytest.mark.parametrize("frase", [
    "indo arrumar meu filho pra escola",
    "levando o filho ao médico",
    "buscar na escola",
])
def test_o_filho_e_a_escola_sao_pausa_e_nao_hora_sem_tema(frase):
    assert PA.tema_de(frase) == "pausa"


@pytest.mark.parametrize("frase", [
    "qualificação do título de domínio",
    "conferindo a escritura de compra e venda",
    "geo da matrícula 9.001",
    "georreferenciamento do imóvel",
    "nota devolutiva",
    "baixa de cédula rural",
    "cédula de crédito bancário",
    "notificações do usucapião",
    "mandato translativo",
    "depósito prévio do título",
])
def test_a_qualificacao_do_ri_tem_tema_proprio(frase):
    assert PA.tema_de(frase) == "RI: qualificação / títulos"


def test_o_inicio_do_expediente_tem_tema_mas_o_conteudo_ganha_dele():
    assert PA.tema_de("iniciando o expediente") == "início do expediente"
    assert PA.tema_de("Iniciando trabalhos") == "início do expediente"
    assert PA.tema_de("iniciado o trabalho") == "início do expediente"
    # o que vem depois da abertura diz o que foi feito
    assert (PA.tema_de("iniciando trabalhos, verificando notificações do usucapião")
            == "RI: qualificação / títulos")
    # só no começo: «trabalhos» no meio continua tarefa sem dizer quais
    assert PA.tema_de("conferindo trabalhos") == "tarefas / pendências (sem dizer quais)"


def test_a_tarefa_com_numero_diz_qual_e():
    assert PA.tema_de("cumprindo tarefa #117") == "tarefas numeradas (#)"
    assert PA.tema_de("Tarefa # 12 do RCPN") == "tarefas numeradas (#)"
    assert PA.tema_de("vendo as tarefas pendentes") == "tarefas / pendências (sem dizer quais)"
    assert PA.tema_de("tarefa #sem número") == "tarefas / pendências (sem dizer quais)"


def test_ajudar_as_meninas_ou_a_equipe_e_ajudar_colega():
    assert PA.tema_de("ajudando as meninas no balcão") == "ajudar colega"
    assert PA.tema_de("ajudei a equipe") == "ajudar colega"
    assert PA.tema_de("ajudando colega") == "ajudar colega"
    assert PA.tema_de("ajudando a colega") == "ajudar colega"
    # sem o nome do colega na lista, o nome não casa
    assert PA.tema_de("ajudando Beatriz no balcão") == "balcão (sem dizer o quê)"
    assert PA.tema_de("ajudando Beatriz no balcão", ("BEATRIZ",)) == "ajudar colega"


def test_a_critica_le_os_nomes_dos_colegas_do_cadastro(cg_casa_logada):
    # Até 20/10/2026 a tupla dos colegas saía vazia: «ajudando Beatriz» caía no
    # balcão. O nome vem do cadastro (`users.full_name`, que `pessoas()` devolve
    # como `nome`), e não do código (portão anti-vazamento).
    db = cg_casa_logada["db"]
    db.create_user("beatriz", "BEATRIZ EXEMPLO DE SOUZA", SENHA, "USER")
    with db.transaction() as con:
        bd = banco(con)
        mario = int(bd.valor("SELECT id FROM users WHERE username = %s", ("mario",)))
        for tarefa, inicio, fim in (("ajudando Beatriz no balcão", "09:00", "09:40"),
                                    ("indo arrumar meu filho pra escola", "10:00", "10:30"),
                                    ("cumprindo tarefa #117", "11:00", "11:20")):
            bd.escrever(
                "INSERT INTO prod_registros (data_registro, responsavel_user_id, "
                "responsavel_nome, categoria, tarefa, prioridade, status, hora_inicio, "
                "hora_fim, pausas_min, criado_em) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s)",
                ("2026-10-20", mario, "MARIO EXEMPLO DOS SANTOS", "Atendimento",
                 tarefa, "Média", "Concluída", inicio, fim, "2026-10-20T12:00:00"))
    with db.connect() as con:
        assert "BEATRIZ" in {p["nome"].split()[0] for p in PA.pessoas(con)}
        temas = PA.medir(con, "2026-10-01", "2026-10-31")["por"]["mario"]["temas"]
    assert dict(temas) == {"ajudar colega": 40, "pausa": 30, "tarefas numeradas (#)": 20}
