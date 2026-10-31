"""As fases da ficha do título do RCPJ e do RTD: o que a régua mostra e onde a ficha abre. SÓ LÊ.

NOVE QUADROS NA MESMA PÁGINA — projeto do novo layout, 30/10/2026. Os quadros continuam os mesmos, nas
mesmas rotas. O que muda é quais aparecem juntos: quem qualifica não precisa do quadro da Central, e
quem registra não precisa do cadastro do apresentante.

FASES, E NÃO ABAS, PORQUE HÁ ORDEM: o título entra, é lido, é qualificado e sai (`rg_titulo`). A Central
e o encerramento correm fora do rito, como apoio.

O DOCUMENTO MORA NA QUALIFICAÇÃO, ao lado da decisão, que é o que o molde sempre pediu: quem qualifica
tem o papel na mão e a decisão em branco na frente.

A TRAVA NÃO INVENTA REGRA. O registro trava onde `rg_titulo.registrar` recusa, e para quem a rota
recusa. A qualificação nunca trava: requalificar é linha nova, e o título com exigência volta a ela.

A RÉGUA SÓ COBRA DE QUEM PODE FAZER. Para o balcão a qualificação é ato do oficial, e um número na fase
seria alarme sem saída. O título com exigência também não marca: quem age agora é o apresentante.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

APRESENTACAO = "apresentacao"
QUALIFICACAO = "qualificacao"
REGISTRO = "registro"
CENTRAL = "central"
ENCERRAR = "encerrar"

FEITA = "feita"
LIBERADA = "liberada"
TRAVADA = "travada"

APRESENTADO = "APRESENTADO"
QUALIFICADO = "QUALIFICADO"
EXIGENCIA = "EXIGENCIA"
REGISTRADO = "REGISTRADO"
DEVOLVIDO = "DEVOLVIDO"
CANCELADO = "CANCELADO"
SITUACOES_TERMINAIS = (REGISTRADO, DEVOLVIDO, CANCELADO)

_TRAVA_SEM_QUALIFICACAO = {
    "titulo": "Antes, a qualificação positiva",
    "texto": "Só se registra título com qualificação positiva: registrar antes gastaria número do livro "
             "num título que ainda pode voltar.",
    "ir": QUALIFICACAO, "ir_rotulo": "Qualificação"}
_TRAVA_DO_OFICIAL = {
    "titulo": "O registro é ato do oficial",
    "texto": "Este título tem qualificação positiva. Quem lavra o registro é quem responde pela serventia.",
    "ir": QUALIFICACAO, "ir_rotulo": "Qualificação"}
_TRAVA_SAIU_SEM_REGISTRO = {
    "titulo": "Este título saiu sem registro",
    "texto": "Ele foi devolvido ou cancelado, e título encerrado não recebe mais decisão. O motivo está "
             "na apresentação.",
    "ir": APRESENTACAO, "ir_rotulo": "Apresentação"}


def _fase(chave: str, rotulo: str, numero: int, estado: str, pendencias: int = 0, aviso: str = "",
          trava: dict | None = None) -> dict:
    return {"chave": chave, "rotulo": rotulo, "numero": numero, "estado": estado, "pendencias": pendencias,
            "aviso": aviso, "trava": trava}


def _qualificacao(situacao: str, qualificacoes: Sequence, pode_decidir: bool) -> dict:
    if situacao == APRESENTADO and pode_decidir:
        return _fase(QUALIFICACAO, "Qualificação", 2, LIBERADA, 1, "Leia o título e registre a qualificação.")
    if situacao == APRESENTADO:
        return _fase(QUALIFICACAO, "Qualificação", 2, LIBERADA, aviso="A qualificação é ato do oficial.")
    if situacao == EXIGENCIA:
        return _fase(QUALIFICACAO, "Qualificação", 2, LIBERADA,
                     aviso="Com exigência: quando for cumprida, o título se qualifica de novo.")
    # Título que saiu sem nunca ter sido qualificado não diz que foi.
    if situacao in (QUALIFICADO, REGISTRADO) or qualificacoes:
        return _fase(QUALIFICACAO, "Qualificação", 2, FEITA)
    return _fase(QUALIFICACAO, "Qualificação", 2, LIBERADA)


def _registro(situacao: str, tem_registro: bool, pode_decidir: bool) -> dict:
    if tem_registro or situacao == REGISTRADO:
        return _fase(REGISTRO, "Registro", 3, FEITA)
    if situacao == QUALIFICADO and pode_decidir:
        return _fase(REGISTRO, "Registro", 3, LIBERADA, 1,
                     "Lavre o registro, ou conclua pelo ato que já atendeu o título.")
    if situacao == QUALIFICADO:
        return _fase(REGISTRO, "Registro", 3, TRAVADA, trava=_TRAVA_DO_OFICIAL)
    if situacao in (DEVOLVIDO, CANCELADO):
        return _fase(REGISTRO, "Registro", 3, TRAVADA, trava=_TRAVA_SAIU_SEM_REGISTRO)
    return _fase(REGISTRO, "Registro", 3, TRAVADA, trava=_TRAVA_SEM_QUALIFICACAO)


def _fase_inicial(situacao: str, registro: Mapping[str, Any]) -> str:
    """Abre no que espera ação. Título que saiu sem registro abre onde está o motivo."""
    if situacao in (DEVOLVIDO, CANCELADO):
        return APRESENTACAO
    return QUALIFICACAO if registro["estado"] == TRAVADA else REGISTRO


def fases_do_titulo(titulo: Mapping[str, Any], *, qualificacoes: Sequence = (), encaminhamentos: Sequence = (),
                    tem_registro: bool = False, pode_decidir: bool = False, central_falhou: bool = False) -> dict:
    """A régua da ficha. A forma é a de `notas_fases`: `_fases.html` desenha as duas."""
    situacao = str(titulo.get("situacao") or "")
    registro = _registro(situacao, tem_registro, pode_decidir)
    fases = [_fase(APRESENTACAO, "Apresentação", 1, FEITA), _qualificacao(situacao, qualificacoes, pode_decidir),
             registro]
    for i, fase in enumerate(fases):
        fase["voltar"] = {k: fases[i - 1][k] for k in ("chave", "rotulo")} if i else None
        fase["avancar"] = {k: fases[i + 1][k] for k in ("chave", "rotulo")} if i < len(fases) - 1 else None

    # A Central fora do ar não diz «não há nota», e por isso a falha marca a aba em vez de ficar calada nela.
    apoio = [{"chave": CENTRAL, "rotulo": "Central", "contagem": len(encaminhamentos),
              "alerta": 1 if central_falhou else 0}]
    if pode_decidir and situacao not in SITUACOES_TERMINAIS:
        apoio.append({"chave": ENCERRAR, "rotulo": "Encerrar", "contagem": 0, "alerta": 0})
    return {"fases": fases, "apoio": apoio, "foco": QUALIFICACAO, "inicial": _fase_inicial(situacao, registro)}
