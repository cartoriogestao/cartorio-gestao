"""As fases da ficha do ato de Notas: o que a régua mostra e onde a ficha abre. SÓ LÊ.

A FICHA TINHA 5.237 PX NUMA PÁGINA SÓ — pedido do oficial, 30/10/2026: «cada tela aparece
apenas o que é importante naquele momento do ato», com o campo da DOI como exemplo. Os
quadros continuam os mesmos, nas mesmas rotas e com os mesmos formulários. O que muda é
quais deles aparecem juntos.

TRAVA DE TELA NÃO É REGRA. A trava só orienta quem está na tela. Quem recusa continua sendo
o servidor, com as mesmas verificações de antes: nada se torna permitido ou proibido por
causa de uma aba, e sem JavaScript a página sai inteira.

O QUE SE PREENCHE ANTES DE LANÇAR NÃO MORA NA ENTREGA. O desenho punha o ato anterior, a
comunicação à origem e o tipo do testamento na Entrega, que só abre depois do lançamento.
Mas é em lavratura que eles se preenchem: sem o ato anterior, a anotação à margem não sai.
Por isso eles moram em Preparar enquanto o ato está em lavratura (`lugar_dos_quadros`).

`com_imovel` NÃO DIZ «AINDA NÃO DECIDI». A coluna nasce 0, e o 0 de quem marcou «sem imóvel»
é igual ao de quem nunca abriu o quadro. O desenho tirava a DOI da régua ao marcar, e isso
esconderia a DOI de toda escritura nova. Quem tira é o MODELO que não transmite imóvel; e na
hora de lançar a tela diz que a escritura está sem imóvel, com o caminho para corrigir.

O ACERVO NÃO VIRA PENDÊNCIA. Só 1 dos 263 atos antigos tem o selo anotado. Cobrar selo de
ato que o sistema não lançou seria o alarme que soa sempre: `lancado_em` separa os dois.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

EM_LAVRATURA = "EM_LAVRATURA"
TIPOS_COM_EVIDENCIAS = ("ATA", "ATA_USUCAPIAO")
SITUACOES_QUE_ENTREGAM = ("LAVRADO", "SUSPENSO_SELO")

FEITA = "feita"
LIBERADA = "liberada"
TRAVADA = "travada"

# O que a tela diz no lugar da fase travada: título, explicação e para onde levar.
TRAVAS: dict[str, tuple[str, str, str]] = {
    "doi": ("A DOI abre quando a minuta estiver pronta",
            "O imóvel e a operação se conferem com o teor, e falta escrever o teor. "
            "A obrigação continua de pé: ela vence no fim do mês seguinte ao ato.", "teor"),
    "lancar": ("O lançamento abre com o teor escrito",
               "Sem teor não há o que levar ao livro.", "teor"),
    "entrega": ("A entrega abre depois do lançamento",
                "Traslado, selo e anotações à margem dependem do livro e da folha.", "lancar"),
}


def lugar_dos_quadros(ato: Mapping[str, Any]) -> dict[str, str]:
    """Em que fase mora cada quadro que muda de lugar com a situação do ato."""
    em_lavratura = (ato["situacao"] or "") == EM_LAVRATURA
    return {"antes_de_lancar": "preparar" if em_lavratura else "entrega",
            "selo": "lancar" if em_lavratura else "entrega"}


def _item(texto: str, feito: bool, ir: str = "") -> dict:
    return {"texto": texto, "feito": feito, "ir": ir}


def _fase_da_trava(texto: str) -> str:
    """Para onde levar quem lê a trava do servidor. A frase é dele: só a endereço."""
    baixo = texto.lower()
    if "quadro «partes»" in baixo or "cadastro" in baixo or "parte" in baixo:
        return "partes"
    if "teor" in baixo or "texto" in baixo:
        return "teor"
    return ""


def _para_lancar(a: dict, partes: Sequence, pendencias: Sequence[str],
                 falta_qualificar: Sequence[str], travas: Sequence[str],
                 arquivamento: Mapping | None, doi_na_regua: bool) -> list[dict]:
    """O que falta para lançar. As frases de `travas` são as que o servidor recusaria."""
    itens = []
    if not partes:
        itens.append(_item("Incluir as partes", False, "partes"))
    elif falta_qualificar:
        itens.append(_item(f"Completar a qualificação: {falta_qualificar[0]}", False, "partes"))
    else:
        itens.append(_item("Partes qualificadas", True, "partes"))
    if not (a.get("teor") or "").strip():
        itens.append(_item("Escrever o teor", False, "teor"))
    elif pendencias:
        itens.append(_item(f"Preencher {len(pendencias)} campo(s) em branco do teor", False, "teor"))
    else:
        itens.append(_item("Teor sem campos em branco", True, "teor"))
    if arquivamento and arquivamento.get("obrigatorio"):
        if not (arquivamento.get("contagem") or {}).get("anexos"):
            itens.append(_item("Anexar o documento arquivado: o número de folhas do "
                               "selo 13.30 sai dele", False, "documentos"))
        elif not arquivamento.get("confirmado"):
            itens.append(_item("Confirmar as folhas do arquivamento (13.30)", False))
        else:
            itens.append(_item("Folhas do arquivamento confirmadas", True))
    if doi_na_regua and not a.get("com_imovel"):
        itens.append(_item("Marcada como sem imóvel: não entra na DOI. Confira se é isso "
                           "mesmo antes de lançar", True, "doi"))
    for trava in travas:
        if trava.startswith(("o texto tem campo em branco", "cadastro incompleto")):
            continue                      # já ditas nas duas linhas de cima
        itens.append(_item(trava, False, _fase_da_trava(trava)))
    return itens


def _para_entregar(a: dict, arquivamento: Mapping | None, comunicacao: Mapping | None,
                   comunicacao_devida: bool) -> list[dict]:
    """O que ainda falta num ato lançado por este sistema."""
    itens = []
    if a.get("situacao") not in SITUACOES_QUE_ENTREGAM:
        return itens
    if a.get("lancado_em"):
        if not a.get("selo"):
            itens.append(_item("Pedir o selo do ato", False, "selo-do-ato"))
        elif (arquivamento and arquivamento.get("obrigatorio")
              and not a.get("selo_arquivamento")):
            itens.append(_item("Pedir o selo de arquivamento (13.30)", False, "selo-do-ato"))
    if comunicacao:
        if comunicacao.get("aberta"):
            itens.append(_item("Registrar a comunicação à serventia de origem", False,
                               "comunicacao-origem"))
        elif comunicacao.get("falta_comprovante"):
            itens.append(_item("Juntar o comprovante da comunicação", False,
                               "comunicacao-origem"))
    elif comunicacao_devida:
        itens.append(_item("Lançar a obrigação de comunicar a serventia de origem", False,
                           "comunicacao-origem"))
    return itens


def _doi_completa(a: dict) -> bool:
    """O mínimo que `notas_doi.declaracao_da_escritura` exige do que se digita nesta fase."""
    return bool(str(a.get("doi_transacao") or "").strip()
                and str(a.get("doi_matricula") or "").strip()
                and a.get("valor_transacao"))


def fases_do_ato(ato: Mapping[str, Any], *, partes: Sequence = (), anexos: Sequence = (),
                 pendencias: Sequence[str] = (), falta_qualificar: Sequence[str] = (),
                 travas: Sequence[str] = (), arquivamento: Mapping | None = None,
                 comunicacao: Mapping | None = None, comunicacao_devida: bool = False,
                 depositos: Sequence = (), modelo_com_imovel: bool | None = None,
                 foco: str = "") -> dict:
    """A régua da ficha: as fases, o apoio, onde abrir e o que falta. Só calcula.

    `modelo_com_imovel` é o que o modelo do ato declara, ou None sem modelo.
    """
    a = dict(ato)
    tipo = (a.get("tipo") or "").upper()
    em_lavratura = (a.get("situacao") or "") == EM_LAVRATURA
    tem_teor = bool((a.get("teor") or "").strip())
    evidencias = tipo in TIPOS_COM_EVIDENCIAS
    escritura = tipo == "ESCRITURA"
    marcada = bool(a.get("com_imovel"))
    doi_na_regua = escritura and (marcada or modelo_com_imovel is not False)
    doi_pendente = doi_na_regua and (
        (marcada and not _doi_completa(a)) or (em_lavratura and not marcada and bool(modelo_com_imovel)))
    partes_prontas = bool(partes) and not falta_qualificar
    teor_pronto = tem_teor and not pendencias

    para_lancar = (_para_lancar(a, partes, pendencias, falta_qualificar, travas, arquivamento,
                                doi_na_regua) if em_lavratura else [])
    para_entregar = _para_entregar(a, arquivamento, comunicacao, comunicacao_devida)

    fases = [{"chave": "preparar", "rotulo": "Preparar", "pendencias": 0,
              "estado": LIBERADA if em_lavratura and not partes and not tem_teor else FEITA,
              "aviso": "Nada aqui é obrigatório: é preparação." if em_lavratura else ""},
             {"chave": "partes", "rotulo": "Partes",
              "pendencias": len(falta_qualificar) if em_lavratura else 0,
              "estado": FEITA if partes_prontas or not em_lavratura else LIBERADA,
              "aviso": (f"Falta qualificar {falta_qualificar[0]}."
                        if em_lavratura and falta_qualificar else "")}]
    if evidencias:
        fases.append({"chave": "documentos", "rotulo": "Evidências", "pendencias": 0,
                      "estado": FEITA if anexos or not em_lavratura else LIBERADA,
                      "aviso": "A descrição de cada evidência é obrigatória."})
    fases.append({"chave": "teor", "rotulo": "Teor",
                  "pendencias": len(pendencias) if em_lavratura else 0,
                  "estado": FEITA if teor_pronto or not em_lavratura else LIBERADA,
                  "aviso": (f"{len(pendencias)} campo(s) em branco: "
                            + ", ".join(pendencias[:3]) + "."
                            if em_lavratura and pendencias else "")})
    if doi_na_regua:
        travada = (em_lavratura and not tem_teor and not marcada
                   and a.get("doi_transacao") is None)
        fases.append({"chave": "doi", "rotulo": "DOI",
                      "pendencias": 1 if doi_pendente and not travada else 0,
                      "estado": (TRAVADA if travada
                                 else FEITA if (marcada and not doi_pendente) or not em_lavratura
                                 and not doi_pendente else LIBERADA),
                      "aviso": "Enquanto faltar, a conferência da DOI continua cobrando."
                      if doi_pendente else ""})
    pendentes_de_lancar = sum(1 for i in para_lancar if not i["feito"])
    fases.append({"chave": "lancar", "rotulo": "Lançar",
                  "pendencias": pendentes_de_lancar if tem_teor else 0,
                  "estado": (FEITA if not em_lavratura
                             else LIBERADA if tem_teor else TRAVADA),
                  "aviso": ("O lançamento reserva folha e termo: depois disso o papel "
                            "está escrito." if em_lavratura else "")})
    fases.append({"chave": "entrega", "rotulo": "Entrega", "pendencias": len(para_entregar),
                  "estado": (TRAVADA if em_lavratura
                             else LIBERADA if para_entregar else FEITA),
                  "aviso": ""})

    for numero, fase in enumerate(fases, start=1):
        fase["numero"] = numero
        trava = TRAVAS.get(fase["chave"])
        fase["trava"] = ({"titulo": trava[0], "texto": trava[1], "ir": trava[2],
                          "ir_rotulo": next(x["rotulo"] for x in fases if x["chave"] == trava[2])}
                         if trava and fase["estado"] == TRAVADA else None)
        fase["voltar"] = fases[numero - 2] if numero > 1 else None
        fase["avancar"] = fases[numero] if numero < len(fases) else None
        if fase["chave"] == "lancar" and em_lavratura:
            fase["avancar"] = None        # o botão de lançar é o último do formulário
    # A barra só precisa do nome: sem isto a fase vizinha viria junto com a vizinha dela.
    for fase in fases:
        for lado in ("voltar", "avancar"):
            if fase[lado]:
                fase[lado] = {"chave": fase[lado]["chave"], "rotulo": fase[lado]["rotulo"]}

    apoio = []
    if not evidencias:
        apoio.append({"chave": "documentos", "rotulo": "Documentos", "contagem": len(anexos)})
    apoio.append({"chave": "financeiro", "rotulo": "Financeiro", "contagem": len(depositos)})
    if escritura and not doi_na_regua:
        # O modelo diz que não há imóvel, mas o quadro continua ao alcance de quem discordar.
        apoio.append({"chave": "doi", "rotulo": "DOI", "contagem": 0})

    chaves = {f["chave"] for f in fases} | {x["chave"] for x in apoio}
    return {"fases": fases, "apoio": apoio, "foco": "teor",
            "inicial": foco if foco in chaves else _onde_abrir(
                fases, em_lavratura, bool(partes), tem_teor, partes_prontas, teor_pronto,
                doi_pendente),
            "para_lancar": para_lancar, "para_entregar": para_entregar}


def _onde_abrir(fases: list[dict], em_lavratura: bool, tem_partes: bool, tem_teor: bool,
                partes_prontas: bool, teor_pronto: bool, doi_pendente: bool) -> str:
    """A ficha abre na primeira fase pendente: o que espera ação vem primeiro."""
    if not em_lavratura:
        return "entrega"
    if not tem_partes and not tem_teor:
        return "preparar"
    if not partes_prontas:
        return "partes"
    if not teor_pronto:
        return "teor"
    tem_doi = any(f["chave"] == "doi" for f in fases)
    return "doi" if tem_doi and doi_pendente else "lancar"
