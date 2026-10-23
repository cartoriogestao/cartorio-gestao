"""O CAIXA QUE NÃO FECHA — o aviso grande, vermelho e insistente.

    «crie um aviso grande, vermelho e insistente para obrigar o encerramento
     de caixa após o expediente diário» — o oficial, 06/10/2026

O QUE SE MEDIU ANTES DE ESCREVER
    Desde 15/08/2026, **43 dos 51** caixas fechados foram fechados NO DIA
    SEGUINTE, quase todos às 8h; e o caixa de 14/09 de uma escrevente ficou
    aberto até 06/10 com os usos dos depósitos de setembro dentro. Caixa que
    atravessa a noite mistura o dinheiro de dois dias, e a conferência do
    oficial deixa de saber o que entrou em cada um.

OS DOIS DEGRAUS
    1. **Depois do fim do expediente, com o caixa DE HOJE aberto:** faixa
       vermelha no alto de toda tela e uma janela por cima do conteúdo, que se
       fecha com «Entendi» — e volta na tela seguinte. É o «insistente».
    2. **Caixa de UM DIA ANTERIOR ainda aberto:** a janela NÃO fecha. Só a tela
       do caixa fica livre, porque é nela que se fecha. É o «obrigar»: ninguém
       começa o dia novo sem fechar o de ontem.

    O ADMIN nunca é bloqueado (é quem desfaz), e vê a lista dos caixas de
    outros dias que continuam abertos, de qualquer operador.

O FIM DO EXPEDIENTE É CONFIGURAÇÃO, e não constante: o acervo não guarda o
horário da casa (procurado em 06/10/2026 — `tbSetupBoleto.strHorarioAtendimento`
existe e está vazio). **14h é o horário dito pelo oficial em 06/10/2026**:
«expediente termina 14h, funcionarios vao embora 14h15. avisas 14h pra fechar
o caixa». Eu havia posto 17h pelo movimento medido (lançamentos até 16h–17h) —
o movimento depois das 14h é trabalho interno, e o caixa fecha com o
expediente. Muda-se em `settings.caixa_fim_do_expediente`, sem versão nova.

O MÓDULO SÓ LÊ. Não fecha caixa nenhum — fechar exige contar o dinheiro, e
isso é de quem está com a gaveta.
"""
from __future__ import annotations

import re
from datetime import datetime

from bd_nativo import banco

CHAVE_FIM = "caixa_fim_do_expediente"
FIM_PADRAO = "14:00"

#: Os caixas da carga do E-Ofício (operador «BEATRIZ», datas de 2020 a 2022)
#: entraram como linha de acervo; o aviso é do caixa que este sistema abriu.
INICIO_DO_SISTEMA = "2026-08-01"


def fim_do_expediente(texto: str | None) -> tuple[int, int]:
    """«14:00» → (14, 0). O que não for hora válida volta ao padrão."""
    m = re.fullmatch(r"\s*(\d{1,2})[:h](\d{2})?\s*", texto or "")
    if m and 0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2) or 0) <= 59:
        return int(m.group(1)), int(m.group(2) or 0)
    h, mi = FIM_PADRAO.split(":")
    return int(h), int(mi)


def situacao(con, operador_nome: str, agora: datetime,
             fim: str | None = None, *, e_admin: bool = False) -> dict | None:
    """O que o aviso diz a esta pessoa agora, ou None quando não há o que dizer."""
    hoje = agora.date().isoformat()
    bd = banco(con)
    meus = bd.ler(
        """SELECT id, data, aberto_em FROM cx_caixas
            WHERE operador_nome = %s AND situacao = 'ABERTO' AND data >= %s
            ORDER BY data, id""", (operador_nome or "", INICIO_DO_SISTEMA))
    de_outros_dias = [m for m in meus if m["data"] < hoje]
    hora, minuto = fim_do_expediente(fim)
    passou = (agora.hour, agora.minute) >= (hora, minuto)
    outros = []
    if e_admin:
        outros = [{"operador": r["operador_nome"], "data": r["data"]} for r in bd.ler(
            """SELECT operador_nome, data FROM cx_caixas
                WHERE situacao = 'ABERTO' AND data >= %s AND data < %s
                  AND operador_nome <> %s ORDER BY data, id""",
            (INICIO_DO_SISTEMA, hoje, operador_nome or ""))]
    if de_outros_dias:
        nivel = "BLOQUEIO" if not e_admin else "VENCIDO"
        dias = [m["data"] for m in de_outros_dias]
    elif passou and any(m["data"] == hoje for m in meus):
        nivel, dias = "FIM_DO_EXPEDIENTE", [hoje]
    elif outros:
        nivel, dias = "OUTROS", []
    else:
        return None
    return {"nivel": nivel, "dias": dias, "fim": f"{hora:02d}:{minuto:02d}",
            "outros": outros}
