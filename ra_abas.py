"""As abas da ficha do registro do Livro 3: o que a régua mostra e o que espera ação. SÓ LÊ.

CATORZE QUADROS NUMA PÁGINA SÓ — projeto do novo layout, 30/10/2026. O formulário de lançar ficava no meio
da leitura, e o teor da cédula, com até 29 mil caracteres, empurrava o resto para baixo. Os quadros
continuam os mesmos, nas mesmas rotas e com os mesmos formulários. O que muda é quais aparecem juntos.

ABAS, E NÃO FASES. O registro é vivo, como a matrícula (`ri_abas`): a cédula fica anos no livro,
recebendo averbações, e ninguém «termina» as partes. Por isso a régua não numera nem trava.

ELA ABRE NO RESUMO, E O RESUMO COMEÇA PELO QUE ESPERA AÇÃO. Só aparece o que o balcão lavrou e o que
ainda dá para fazer: alarme que soa sempre é alarme que ninguém ouve. O ato do acervo sem selo fica de
fora, e o botão de selar continua na aba Atos. A numeração fora do lugar também só conta enquanto
renumerar cabe, porque ato com selo não se renumera (`ra_correcoes.renumerar`).
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

RESUMO = "resumo"
ATOS = "atos"
TEOR = "teor"
PARTES = "partes"
MINUTAS = "minutas"
REVISAR = "revisar"
CERTIDOES = "certidoes"
CORRIGIR = "corrigir"
LANCAR = "lancar"

ATIVO = "ATIVO"
A_REVISAR = "A_REVISAR"
ABERTA = "ABERTA"


def _do_balcao(linha: Mapping[str, Any]) -> bool:
    return linha.get("origem") == "MANUAL"


def sem_selo(atos: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Os atos lavrados por este sistema que ficaram sem selo. O acervo não entra."""
    return [a for a in atos if _do_balcao(a) and not a.get("selo")]


def minutas_a_revisar(minutas: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [m for m in minutas if m.get("situacao") == A_REVISAR]


def revisoes_abertas(revisoes: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [r for r in revisoes if r.get("situacao") == ABERTA]


def faltam_partes(*, partes: Sequence = (), atos: Sequence = (), minutas: Sequence = ()) -> bool:
    """Sem partes o selo não sai. Só cobra quando há o que selar: fora disso, nenhum ato espera por elas."""
    return not partes and bool(sem_selo(atos) or minutas_a_revisar(minutas))


def numeracao_a_corrigir(numeracao: Sequence[Mapping[str, Any]], atos: Sequence[Mapping[str, Any]]) -> list:
    """Os atos do balcão fora do lugar, enquanto renumerar cabe. Um só com selo faz a rota recusar todos."""
    fora = [x for x in numeracao if x.get("fora_do_lugar")]
    if any(x.get("selo") for x in fora):
        return []
    do_balcao = {a.get("id") for a in atos if _do_balcao(a)}
    return [x for x in fora if x.get("id") in do_balcao]


def o_que_espera(*, atos: Sequence = (), partes: Sequence = (), minutas: Sequence = (), revisoes: Sequence = (),
                 numeracao: Sequence = (), pode_corrigir: bool = False) -> list[dict]:
    """O que a ficha pede agora, na ordem em que custa mais. Vazia, o quadro não sai."""
    itens = []
    if faltam_partes(partes=partes, atos=atos, minutas=minutas):
        itens.append({"texto": "Este registro não tem partes, e sem elas o selo não sai",
                      "ir": PARTES, "botao": "Informar"})
    itens += [{"texto": f'{a["tipo"]}-{a["numero"]} lavrado e sem selo', "ir": f'selar-ato-{a["id"]}', "botao": "Selar"}
              for a in sem_selo(atos)]
    if minutas_a_revisar(minutas):
        itens.append({"texto": f"{len(minutas_a_revisar(minutas))} minuta(s) a revisar e lavrar",
                      "ir": MINUTAS, "botao": "Abrir"})
    if revisoes_abertas(revisoes):
        itens.append({"texto": f"{len(revisoes_abertas(revisoes))} ponto(s) a revisar antes de selar",
                      "ir": REVISAR, "botao": "Ver"})
    # A correção mora num quadro que só o oficial vê, e ao balcão o aviso não daria saída.
    if pode_corrigir and numeracao_a_corrigir(numeracao, atos):
        itens.append({"texto": f"{len(numeracao_a_corrigir(numeracao, atos))} ato(s) com a numeração fora do lugar",
                      "ir": CORRIGIR, "botao": "Ver"})
    return itens


def abas_do_registro(registro: Mapping[str, Any], *, atos: Sequence = (), partes: Sequence = (),
                     minutas: Sequence = (), revisoes: Sequence = (), numeracao: Sequence = (),
                     certidoes: Sequence = (), expurgos: Sequence = (), rascunho: Any = None,
                     pode_corrigir: bool = False) -> dict:
    """A régua da ficha. Só calcula. A forma é a de `notas_fases`: `_fases.html` desenha as duas.

    Aba de lista vazia não aparece. Revisar fica: «nada a revisar» é uma resposta, e o formulário de
    anotar mora lá. Partes e Certidões também, porque é nelas que se cria a primeira. E Atos fica
    enquanto houver ata de ocorrência: a ata é o papel do ato que saiu.
    """
    apoio = [{"chave": RESUMO, "rotulo": "Resumo", "contagem": 0, "alerta": 0}]
    if atos or expurgos:
        apoio.append({"chave": ATOS, "rotulo": "Atos", "contagem": len(atos), "alerta": len(sem_selo(atos))})
    apoio.append({"chave": TEOR, "rotulo": "Teor e imagem", "contagem": 0, "alerta": 0})
    apoio.append({"chave": PARTES, "rotulo": "Partes", "contagem": len(partes),
                  "alerta": 1 if faltam_partes(partes=partes, atos=atos, minutas=minutas) else 0})
    if minutas or rascunho:
        apoio.append({"chave": MINUTAS, "rotulo": "Minutas", "contagem": len(minutas),
                      "alerta": len(minutas_a_revisar(minutas))})
    apoio.append({"chave": REVISAR, "rotulo": "Revisar", "contagem": 0, "alerta": len(revisoes_abertas(revisoes))})
    apoio.append({"chave": CERTIDOES, "rotulo": "Certidões", "contagem": len(certidoes), "alerta": 0})
    if pode_corrigir:
        apoio.append({"chave": CORRIGIR, "rotulo": "Corrigir", "contagem": 0,
                      "alerta": len(numeracao_a_corrigir(numeracao, atos))})
    if registro.get("situacao") == ATIVO:
        apoio.append({"chave": LANCAR, "rotulo": "Lançar", "contagem": 0, "alerta": 0, "principal": True})
    return {"fases": [], "apoio": apoio, "foco": TEOR, "inicial": RESUMO,
            "espera": o_que_espera(atos=atos, partes=partes, minutas=minutas, revisoes=revisoes,
                                   numeracao=numeracao, pode_corrigir=pode_corrigir)}
