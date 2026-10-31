"""As abas da ficha do assento do Registro Civil: o que a régua mostra e o que espera ação. SÓ LÊ.

O ASSENTO ERA UMA PÁGINA SÓ — projeto do novo layout, 30/10/2026. O formulário da certidão ficava
no meio da leitura do assento, e quem vinha só emitir rolava por tudo. Os quadros continuam os
mesmos, nas mesmas rotas e com os mesmos formulários. O que muda é quais aparecem juntos.

ABAS, E NÃO FASES. O assento já está lavrado, e não há ordem a seguir: ninguém «termina» as
averbações. Por isso a régua não numera nem trava, como a da matrícula (`ri_abas`).

A DIVISÃO TRIPARTITE FICA DE PÉ. A inspeção de 12/08/2026 cobra um campo para cada coisa, e cada
bloco continua no seu quadro: averbação, anotação e retificação são atos diferentes.

O QUE ESPERA AÇÃO SÓ FALA DO QUE O BALCÃO LAVROU. O ato do acervo sem selo, e o assento antigo sem
CPF, são a regra daqueles livros: alarme que soa sempre é alarme que ninguém ouve. O CPF fica de
fora também nos atos novos, porque averbá-lo é oportunidade, e não atraso (art. 347). O botão
continua na aba Averbações. E o livro por confirmar continua sendo o aviso da aba Assento.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

ASSENTO = "assento"
FILIACAO = "filiacao"
AVERBACOES = "averbacoes"
ANOTACOES = "anotacoes"
RETIFICACOES = "retificacoes"
CERTIDOES = "certidoes"
TERMO = "termo"
DOCUMENTOS = "documentos"

# As mesmas espécies do botão «Selar registro» da ficha. O casamento fica de fora de propósito:
# o selo dele é o da habilitação, e o assento só o espelha.
ESPECIES_QUE_SELAM_O_REGISTRO = ("NASCIMENTO", "OBITO", "NATIMORTO")


def _do_balcao(linha: Mapping[str, Any]) -> bool:
    return str(linha.get("origem") or "MANUAL").strip().upper() == "MANUAL"


def _ativo(assento: Mapping[str, Any]) -> bool:
    return str(assento.get("situacao") or "").strip().upper() != "CANCELADO"


def registros_sem_selo(assento: Mapping[str, Any], blocos: Mapping[str, Sequence]) -> list:
    """O registro lavrado aqui que ficou sem selo. O acervo não entra."""
    if not _ativo(assento) or str(assento.get("especie") or "").upper() not in ESPECIES_QUE_SELAM_O_REGISTRO:
        return []
    return [a for a in blocos.get("REGISTRO") or () if not a.get("selo") and _do_balcao(a)]


def averbacoes_sem_selo(assento: Mapping[str, Any], blocos: Mapping[str, Sequence]) -> list:
    """A averbação lavrada aqui que ficou sem selo. O acervo não entra."""
    if not _ativo(assento):
        return []
    return [a for a in blocos.get("AVERBACAO") or () if not a.get("selo") and _do_balcao(a)]


def paternidade_a_remeter(paternidade: Mapping[str, Any] | None) -> bool:
    """O termo de alegação vai ao juiz em 30 dias (Lei 8.560/1992, art. 2º)."""
    return bool(paternidade and paternidade.get("tipo") == "ALEGACAO" and not paternidade.get("remetido_em"))


def termo_a_digitalizar(digi: Mapping[str, Any] | None) -> bool:
    return bool(digi and digi.get("pendente"))


def o_que_espera(assento: Mapping[str, Any], *, blocos: Mapping[str, Sequence],
                 paternidade: Mapping[str, Any] | None = None,
                 habilitacao: Mapping[str, Any] | None = None,
                 digi: Mapping[str, Any] | None = None) -> list[dict]:
    """O que a ficha pede agora, na ordem em que custa mais. Vazia, o quadro não sai."""
    itens = [{"texto": "Registro lavrado e sem selo", "ir": f'selar-registro-{a["id"]}', "botao": "Selar"}
             for a in registros_sem_selo(assento, blocos)]
    itens += [{"texto": "Averbação lavrada e sem selo", "ir": f'selar-averbacao-{a["id"]}', "botao": "Selar"}
              for a in averbacoes_sem_selo(assento, blocos)]
    if paternidade_a_remeter(paternidade):
        itens.append({"texto": "Termo de alegação de paternidade ainda não remetido ao juiz",
                      "ir": "paternidade", "botao": "Ver"})
    if termo_a_digitalizar(digi):
        itens.append({"texto": ("Termo assinado com o prazo de digitalização vencido" if digi.get("vencida")
                                else "Termo assinado ainda não digitalizado"),
                      "ir": "termo-digitalizado", "botao": "Enviar"})
    if habilitacao and habilitacao.get("situacao") == "HABILITADO":
        itens.append({"texto": "Falta amarrar este assento na habilitação",
                      "ir": "habilitacao-do-assento", "botao": "Ver"})
    return itens


def abas_do_assento(assento: Mapping[str, Any], *, blocos: Mapping[str, Sequence],
                    pessoas: Sequence = (), certidoes: Sequence = (), cpf_pendentes: Sequence = (),
                    anexos: Sequence = (), paternidade: Mapping[str, Any] | None = None,
                    habilitacao: Mapping[str, Any] | None = None,
                    digi: Mapping[str, Any] | None = None) -> dict:
    """A régua da ficha. Só calcula. A forma é a de `notas_fases`: `_fases.html` desenha as duas.

    Aba de lista vazia não aparece. Averbações fica também quando há CPF a averbar, porque o
    formulário mora lá. Lançar uma averbação, anotação ou retificação não depende dessas abas:
    o quadro «Lançar no assento» está na aba Assento, e vale até para quem não tem nenhuma.
    """
    apoio = [{"chave": ASSENTO, "rotulo": "Assento", "contagem": 0, "alerta": 0},
             {"chave": FILIACAO, "rotulo": "Filiação e dados", "contagem": len(pessoas), "alerta": 0}]
    averbacoes = blocos.get("AVERBACAO") or ()
    if averbacoes or cpf_pendentes:
        apoio.append({"chave": AVERBACOES, "rotulo": "Averbações", "contagem": len(averbacoes),
                      "alerta": len(averbacoes_sem_selo(assento, blocos))})
    if blocos.get("ANOTACAO"):
        apoio.append({"chave": ANOTACOES, "rotulo": "Anotações", "contagem": len(blocos["ANOTACAO"]), "alerta": 0})
    if blocos.get("RETIFICACAO"):
        apoio.append({"chave": RETIFICACOES, "rotulo": "Retificações", "contagem": len(blocos["RETIFICACAO"]),
                      "alerta": 0})
    apoio.append({"chave": CERTIDOES, "rotulo": "Certidões", "contagem": len(certidoes), "alerta": 0,
                  "principal": True})
    apoio.append({"chave": TERMO, "rotulo": "Termo do livro", "contagem": 0,
                  "alerta": 1 if termo_a_digitalizar(digi) else 0})
    if anexos or paternidade:
        apoio.append({"chave": DOCUMENTOS, "rotulo": "Documentos", "contagem": len(anexos),
                      "alerta": 1 if paternidade_a_remeter(paternidade) else 0})
    return {"fases": [], "apoio": apoio, "foco": "", "inicial": ASSENTO,
            "espera": o_que_espera(assento, blocos=blocos, paternidade=paternidade,
                                   habilitacao=habilitacao, digi=digi)}
