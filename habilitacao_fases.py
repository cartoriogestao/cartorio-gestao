"""As fases da habilitação de casamento: o que a régua mostra e onde a ficha abre. SÓ LÊ.

UM RITO DE SEMANAS, COM TODOS OS QUADROS NA MESMA PÁGINA — projeto do novo layout, 30/10/2026.
Os quadros continuam os mesmos, nas mesmas rotas. O que muda é quais aparecem juntos. As fases
têm os nomes do menu, porque quem vem de «3 · Prontas para casar» tem de achar a mesma palavra
na ficha.

AQUI HÁ TRAVA, AO CONTRÁRIO DA PRENOTAÇÃO, e ela não inventa regra. Cada uma é uma recusa que
`habilitacao.habilitar` já faz, ou um quadro que ainda não existe naquela situação: sem ela, a
fase seria uma aba em branco. Quem recusa continua sendo o servidor.

O EDITAL NÃO TRAVA COM DOCUMENTO FALTANDO. O botão de publicar continua lá, desligado e dizendo
quantos faltam, e o impedimento se registra mesmo com o processo em análise
(`habilitacao.registrar_oposicao`). Travar a fase esconderia essa porta.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

HABILITACAO = "habilitacao"
EDITAL = "edital"
PRONTAS = "prontas"
REGISTRO = "registro"
ANDAMENTO = "andamento"

FEITA = "feita"
LIBERADA = "liberada"
TRAVADA = "travada"

_ARQUIVADO = {
    "titulo": "Processo arquivado",
    "texto": "Este processo foi arquivado, e esta fase não anda mais. O motivo está no andamento.",
    "ir": ANDAMENTO, "ir_rotulo": "Andamento"}


def _fase(chave: str, rotulo: str, numero: int, estado: str, pendencias: int = 0,
          aviso: str = "", trava: dict | None = None) -> dict:
    return {"chave": chave, "rotulo": rotulo, "numero": numero, "estado": estado,
            "pendencias": pendencias, "aviso": aviso, "trava": trava}


def _fase_habilitacao(em_curso: bool, documentos: int, sem_uniao: bool) -> dict:
    aviso = ""
    if em_curso and documentos:
        aviso = f"Faltam {documentos} documento(s): sem eles, o edital não sai."
    elif em_curso and sem_uniao:
        aviso = "Falta dizer que união estável se converte: sem ela, o selo não sai."
    return _fase(HABILITACAO, "Habilitação", 1,
                 LIBERADA if documentos or sem_uniao else FEITA,
                 documentos + int(sem_uniao) if em_curso else 0, aviso)


def _fase_edital(h: Mapping[str, Any], situacao: str, em_curso: bool, documentos: int,
                 publicado: bool, na_central: bool) -> dict:
    if situacao == "ARQUIVADO" and not publicado and not h.get("oposicao_em"):
        return _fase(EDITAL, "Edital", 2, TRAVADA, trava=_ARQUIVADO)
    pendencias, aviso = 0, ""
    if situacao == "COM_OPOSICAO":
        pendencias, aviso = 1, "Há impedimento a decidir: o processo fica parado até a decisão."
    elif situacao == "EM_ANALISE":
        if documentos:
            aviso = "O edital não sai com documento faltando."
        else:
            pendencias = 1
    elif em_curso and publicado and not na_central:
        pendencias, aviso = 1, "O prazo já está correndo, e falta publicar na Central."
    feita = publicado and na_central and situacao != "COM_OPOSICAO"
    return _fase(EDITAL, "Edital", 2, FEITA if feita else LIBERADA, pendencias, aviso)


def _fase_prontas(situacao: str, falta_papel: bool, sem_selo: bool, vencida: bool) -> dict:
    rotulo = "Prontas para casar"
    if situacao == "EM_ANALISE":
        return _fase(PRONTAS, rotulo, 3, TRAVADA, trava={
            "titulo": "Antes, o edital de proclamas",
            "texto": "A certidão só sai depois do edital: habilitar sem ele tira de terceiro o "
                     "direito de opor impedimento.",
            "ir": EDITAL, "ir_rotulo": "Edital"})
    if situacao == "COM_OPOSICAO":
        return _fase(PRONTAS, rotulo, 3, TRAVADA, trava={
            "titulo": "Há impedimento a decidir",
            "texto": "A certidão não sai por cima do impedimento: decida antes, com o fundamento "
                     "escrito.",
            "ir": EDITAL, "ir_rotulo": "Edital"})
    if situacao == "ARQUIVADO":
        return _fase(PRONTAS, rotulo, 3, TRAVADA, trava=_ARQUIVADO)
    if situacao == "EDITAL_PUBLICADO":
        if falta_papel:
            return _fase(PRONTAS, rotulo, 3, LIBERADA,
                         aviso="Antes de expedir, resolva o que falta em Habilitação.")
        return _fase(PRONTAS, rotulo, 3, LIBERADA, 1)
    if situacao == "HABILITADO" and vencida:
        return _fase(PRONTAS, rotulo, 3, LIBERADA, 1,
                     "A habilitação venceu: o processo precisa ser refeito (CC art. 1.532).")
    if situacao == "HABILITADO" and sem_selo:
        return _fase(PRONTAS, rotulo, 3, LIBERADA, 1,
                     "Falta o selo: ele vale pela habilitação e pelo assento.")
    return _fase(PRONTAS, rotulo, 3, FEITA)


def _fase_registro(situacao: str, vencida: bool) -> dict:
    if situacao == "CELEBRADO":
        return _fase(REGISTRO, "Registro", 4, FEITA)
    if situacao == "ARQUIVADO":
        return _fase(REGISTRO, "Registro", 4, TRAVADA, trava=_ARQUIVADO)
    if situacao == "HABILITADO" and vencida:
        return _fase(REGISTRO, "Registro", 4, TRAVADA, trava={
            "titulo": "A habilitação venceu",
            "texto": "Passado o prazo da certidão, o processo precisa ser refeito "
                     "(CC art. 1.532).",
            "ir": PRONTAS, "ir_rotulo": "Prontas para casar"})
    if situacao == "HABILITADO":
        return _fase(REGISTRO, "Registro", 4, LIBERADA, 1,
                     "Lavre o assento, e depois registre a celebração aqui.")
    expedir = situacao == "EDITAL_PUBLICADO"
    return _fase(REGISTRO, "Registro", 4, TRAVADA, trava={
        "titulo": "Antes, a certidão de habilitação",
        "texto": "O casamento se registra com a certidão de habilitação já expedida.",
        "ir": PRONTAS if expedir else EDITAL,
        "ir_rotulo": "Prontas para casar" if expedir else "Edital"})


def _fase_inicial(situacao: str, falta_papel: bool, na_central: bool, sem_selo: bool,
                  vencida: bool) -> str:
    """Abre no que espera ação. A ordem é a de `habilitacao.proximos_passos`."""
    if situacao == "COM_OPOSICAO":
        return EDITAL
    if situacao == "EM_ANALISE":
        return HABILITACAO if falta_papel else EDITAL
    if situacao == "EDITAL_PUBLICADO":
        if not na_central:
            return EDITAL
        return HABILITACAO if falta_papel else PRONTAS
    if situacao == "HABILITADO":
        return PRONTAS if vencida or sem_selo else REGISTRO
    if situacao == "CELEBRADO":
        return REGISTRO
    return HABILITACAO


def fases_da_habilitacao(h: Mapping[str, Any], *, falta: Sequence = (), andamento: Sequence = (),
                         vencida: bool = False, uniao_estavel: str | None = None) -> dict:
    """A régua da ficha. A forma é a de `notas_fases`: `_fases.html` desenha as duas."""
    situacao = h.get("situacao") or ""
    em_curso = situacao not in ("CELEBRADO", "ARQUIVADO")
    publicado = bool(h.get("edital_em"))
    na_central = bool((h.get("eproclamas_protocolo") or "").strip())
    sem_selo = not (h.get("selo") or "").strip()
    sem_uniao = h.get("tipo") == "CONVERSAO" and not (uniao_estavel or "").strip()
    documentos = len(falta)
    falta_papel = bool(documentos or sem_uniao)
    fases = [
        _fase_habilitacao(em_curso, documentos, sem_uniao),
        _fase_edital(h, situacao, em_curso, documentos, publicado, na_central),
        _fase_prontas(situacao, falta_papel, sem_selo, vencida),
        _fase_registro(situacao, vencida),
    ]
    for i, fase in enumerate(fases):
        fase["voltar"] = {k: fases[i - 1][k] for k in ("chave", "rotulo")} if i else None
        fase["avancar"] = {k: fases[i + 1][k] for k in ("chave", "rotulo")} if i < len(fases) - 1 else None
    apoio = [{"chave": ANDAMENTO, "rotulo": "Andamento", "contagem": len(andamento), "alerta": 0}]
    return {"fases": fases, "apoio": apoio, "foco": "",
            "inicial": _fase_inicial(situacao, falta_papel, na_central, sem_selo, vencida)}
