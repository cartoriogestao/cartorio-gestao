"""O Serviço de Pendências do e-Protocolo na casa — a regra, sem tela e sem rota.

    «vamos integrar esse modulo: eventos.registrocivil.org.br/reference»
                                                    — o oficial, 31/10/2026

O CAMINHO DE UM PEDIDO
    1. O robô (`rodada`) esvazia a fila de notificações e GRAVA antes de tudo.
    2. Consulta o protocolo pelo hash, porque a notificação só traz o evento, e
       traz o arquivo estruturado quando há.
    3. A casa vê o pedido na tela «e-Protocolo — pendências».
    4. Nascimento e óbito com arquivo estruturado viram RASCUNHO da tela de assento
       novo, pela mesma fila de pré-cadastros da leitura de documentos.
    5. Quem lavra é a tela do assento. Ligado o assento ao protocolo, cumpre-se.

ESTE MÓDULO NÃO LAVRA, NÃO NUMERA, NÃO SELA E NÃO COBRA — a régua do CNIB. E o
CUMPRIMENTO NÃO É DO ROBÔ: ele exige o token do IdRC de um cartorário, que nasce de
login com segundo fator. É clique de gente, com o nome de gente na auditoria.

A ORDEM DOS EVENTOS NÃO É FORMALIZADA, diz o manual. Por isso a situação da casa não
se deduz da sequência: vem do `status` que o detalhe do protocolo devolve.

«NÃO MEDIU» NÃO É «ZERO»: a rodada que não falou com o serviço devolve ERRO, e a
credencial que falta é AVISO, como em toda a automação.
"""
from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from bd_nativo import banco
import eprotocolo_api as API


class EProtocoloRegra(ValueError):
    """Recusa de regra, com a frase pronta para o balcão."""


# O QUE CADA EVENTO QUER DIZER, E O QUE A CASA FAZ. Transcrito do quadro «Eventos e
# ações esperadas» do manual, mais os que só o enum da referência técnica traz.
# Evento desconhecido não some: a tela mostra a palavra como ela veio.
EVENTOS: dict[str, tuple[str, str, str]] = {
    "request_received": ("Entrada", "Requerimento recebido", "Iniciar o atendimento"),
    "waiting_for_signature": ("Assinatura", "Aguardando assinatura", "Aguardar a assinatura"),
    "signature_completed": ("Assinatura", "Documento assinado pelo cidadão", "Atualizar o andamento"),
    "waiting_for_response_requirement_note": ("Exigência", "Nota de exigência enviada",
                                              "Aguardar a resposta do solicitante"),
    "waiting_for_response_requirement_note_api": ("Exigência", "Nota de exigência enviada por API",
                                                  "Aguardar a resposta do solicitante"),
    "requirement_note_answered": ("Exigência", "Nota de exigência respondida", "Analisar a resposta"),
    "requirement_note_finished": ("Exigência", "Nota de exigência finalizada", "Retomar o atendimento"),
    "forwarding_for_external_manifestation": ("Exigência", "Encaminhado para manifestação externa",
                                              "Aguardar a manifestação"),
    "send_for_budget": ("Orçamento", "Enviado para orçamento", "Atualizar o andamento"),
    "budget_response": ("Orçamento", "Orçamento aguardando aprovação", "Aguardar a decisão do solicitante"),
    "waiting_approval_for_additional_services": ("Orçamento", "Serviços adicionais aguardando aprovação",
                                                 "Aguardar a decisão do solicitante"),
    "waiting_for_payment": ("Pagamento", "Aguardando pagamento", "Aguardar o pagamento"),
    "payment_made": ("Pagamento", "Pagamento realizado", "Executar o serviço e preparar o cumprimento"),
    "devolved": ("Devolução", "Protocolo devolvido", "Analisar o motivo"),
    "accepted_devolution": ("Devolução", "Devolução aceita", "Atualizar o andamento"),
    "rejected_devolution": ("Devolução", "Devolução recusada", "Analisar o motivo"),
    "transferred_to_another_notary": ("Encerramento", "Transferido para outra serventia",
                                      "Encerrar aqui e registrar o destino"),
    "canceled": ("Encerramento", "Cancelado", "Encerrar aqui"),
    "canceled_waiting_for_payment": ("Encerramento", "Cancelado por falta de pagamento", "Encerrar aqui"),
    "completed": ("Encerramento", "Protocolo cumprido", "Confirmar a conclusão"),
}

#: O que espera alguém da casa. É o que vem primeiro na tela e na contagem do robô.
ESPERAM_A_CASA: frozenset[str] = frozenset({
    "request_received", "signature_completed", "requirement_note_answered",
    "requirement_note_finished", "payment_made", "devolved", "rejected_devolution"})
#: O protocolo acabou: nada mais se faz nele por aqui.
ENCERRADOS: frozenset[str] = frozenset({
    "transferred_to_another_notary", "canceled", "canceled_waiting_for_payment", "completed"})

AMBIENTE_PADRAO = API.HOMOLOGACAO
CHAVE_DO_AMBIENTE = "eprotocolo_ambiente"
#: Quanto a reconciliação olha para trás. O serviço quer UTC.
JANELA_DA_RECONCILIACAO_H = 48
PLATAFORMA_ESPECIE = {("unidade_interligada", "nascimento"): "NASCIMENTO",
                      ("e-obito", "obito"): "OBITO"}
USUARIO_DA_AUDITORIA = "automação — e-Protocolo"


def rotulo_do_evento(status: Any) -> str:
    """O nome do evento em português; o desconhecido sai como veio."""
    item = EVENTOS.get(str(status or ""))
    return item[1] if item else (str(status or "") or "sem situação")


def acao_do_evento(status: Any) -> str:
    item = EVENTOS.get(str(status or ""))
    return item[2] if item else "Evento que a casa não conhece: confira no e-Protocolo"


# ----------------------------------------------------------- a fila, gravada

def guardar_notificacao(con, ambiente: str, n: dict, *, agora: str,
                        origem: str = "FILA") -> bool:
    """Uma notificação, e o protocolo dela. ESCREVE. True se era nova.

    Repetida não é erro: a reconciliação passa pelas mesmas de propósito. Sem hash
    ou sem status não há o que guardar, e isso sobe para virar ERRO da rodada:
    notificação lida da fila não volta.
    """
    bd = banco(con)
    hash_ = str(n.get("hash") or "").strip()
    status = str(n.get("status") or "").strip()
    if not hash_ or not status:
        raise EProtocoloRegra("Notificação sem hash ou sem status.")
    ocorrida = str(n.get("createdAt") or agora)
    conteudo = n.get("content") if isinstance(n.get("content"), dict) else {}
    entrou = bd.escrever(
        """INSERT INTO ep_notificacoes (ambiente, hash, status, requirement_id, cns,
               conteudo_json, ocorrida_em, recebida_em, origem)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT DO NOTHING RETURNING id""",
        (ambiente, hash_, status, n.get("requirement_id"), str(n.get("cns") or ""),
         json.dumps(conteudo, ensure_ascii=False), ocorrida, agora, origem))
    if not entrou:
        return False
    # O STATUS DA NOTIFICAÇÃO SÓ VALE ATÉ A CONSULTA: é o detalhe quem manda, e por
    # isso `consultado_em` volta a vazio, para a rodada olhar de novo.
    bd.escrever(
        """INSERT INTO ep_protocolos (ambiente, hash, requirement_id, status,
               primeiro_evento_em, ultimo_evento_em, novo_destino_cns)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (ambiente, hash) DO UPDATE SET
               ultimo_evento_em = GREATEST(ep_protocolos.ultimo_evento_em,
                                           EXCLUDED.ultimo_evento_em),
               status = CASE WHEN EXCLUDED.ultimo_evento_em >= ep_protocolos.ultimo_evento_em
                             THEN EXCLUDED.status ELSE ep_protocolos.status END,
               consultado_em = NULL,
               novo_destino_cns = COALESCE(EXCLUDED.novo_destino_cns,
                                           ep_protocolos.novo_destino_cns)""",
        (ambiente, hash_, n.get("requirement_id"), status, ocorrida, ocorrida,
         str(conteudo.get("new_notary_cns") or "") or None))
    return True


def a_consultar(con, ambiente: str, limite: int = 200) -> list[dict]:
    """Os protocolos cujo detalhe está atrasado em relação à última notificação."""
    return banco(con).ler(
        """SELECT id, hash FROM ep_protocolos WHERE ambiente=%s AND consultado_em IS NULL
            ORDER BY ultimo_evento_em LIMIT %s""", (ambiente, limite))


def _titular_do_estruturado(e: dict | None) -> str:
    registro = (e or {}).get("registro") or {}
    pessoa = registro.get("registrado") or registro.get("falecido") or {}
    return str(pessoa.get("nome") or "").strip()


def guardar_detalhe(con, protocolo_id: int, detalhe: dict,
                    estruturado: dict | None, *, agora: str) -> None:
    """O detalhe e o arquivo estruturado, congelados como vieram. ESCREVE."""
    solicitacao = (estruturado or {}).get("solicitacao") or {}
    banco(con).escrever(
        """UPDATE ep_protocolos SET numero=%s, status=%s, pagamento=%s, servico=%s,
               plataforma=COALESCE(%s, plataforma), tipo_registro=COALESCE(%s, tipo_registro),
               titular=COALESCE(%s, titular), detalhe_json=%s,
               estruturado_json=COALESCE(%s, estruturado_json), tem_estruturado=%s,
               consulta_erro=NULL, consultado_em=%s WHERE id=%s""",
        (str(detalhe.get("protocol") or "") or None, str(detalhe.get("status") or "") or None,
         str(detalhe.get("paymentStatus") or "") or None,
         str(detalhe.get("serviceType") or "") or None,
         str(solicitacao.get("plataformaId") or "") or None,
         str(solicitacao.get("tipo_registro") or "") or None,
         _titular_do_estruturado(estruturado) or None,
         json.dumps(detalhe, ensure_ascii=False),
         json.dumps(estruturado, ensure_ascii=False) if estruturado else None,
         1 if detalhe.get("hasStructuredFile") else 0, agora, protocolo_id))


def _marcar_erro_de_consulta(con, protocolo_id: int, motivo: str, *,
                             definitivo_em: str | None = None) -> None:
    """Guarda o motivo. `definitivo_em` tira da fila de consulta: 403 e 404 não
    melhoram sozinhos, e sem isso o mesmo erro voltaria a cada 5 minutos."""
    banco(con).escrever(
        "UPDATE ep_protocolos SET consulta_erro=%s, consultado_em=COALESCE(%s, consultado_em) "
        "WHERE id=%s", (str(motivo)[:400], definitivo_em, protocolo_id))


def consultar(db, sessao, protocolo_id: int, *, agora: str) -> dict:
    """Traz o detalhe de um protocolo. A rede fica fora da transação."""
    with db.connect() as con:
        p = um(con, protocolo_id)
    if p is None:
        raise EProtocoloRegra(f"Não há protocolo nº {protocolo_id}.")
    detalhe = sessao.protocolo(p["hash"])
    estruturado = sessao.arquivo_estruturado(p["hash"]) if detalhe.get("hasStructuredFile") else None
    with db.transaction() as con:
        guardar_detalhe(con, protocolo_id, detalhe, estruturado, agora=agora)
    return detalhe


# --------------------------------------------------------------- leitura

def _abrir(linha: dict) -> dict:
    d = dict(linha)
    for campo in ("detalhe", "estruturado", "cumprimento"):
        texto = d.get(f"{campo}_json")
        d[campo] = json.loads(texto) if texto else None
    d["rotulo"] = rotulo_do_evento(d.get("status"))
    d["acao"] = acao_do_evento(d.get("status"))
    d["encerrado"] = d.get("status") in ENCERRADOS
    d["espera_a_casa"] = (d.get("status") in ESPERAM_A_CASA and not d.get("dispensado_em")
                          and not d.get("cumprido_em"))
    return d


def um(con, protocolo_id: int) -> dict | None:
    linha = banco(con).um("SELECT * FROM ep_protocolos WHERE id=%s", (protocolo_id,))
    return _abrir(linha) if linha else None


def lista(con, ambiente: str, *, limite: int = 500) -> list[dict]:
    """Os protocolos do ambiente: o que espera a casa primeiro, depois o resto."""
    linhas = [_abrir(x) for x in banco(con).ler(
        """SELECT * FROM ep_protocolos WHERE ambiente=%s
            ORDER BY ultimo_evento_em DESC LIMIT %s""", (ambiente, limite))]
    return sorted(linhas, key=lambda p: (not p["espera_a_casa"], p["encerrado"]))


def eventos_do_protocolo(con, ambiente: str, hash_: str) -> list[dict]:
    linhas = banco(con).ler(
        """SELECT status, conteudo_json, ocorrida_em, origem FROM ep_notificacoes
            WHERE ambiente=%s AND hash=%s ORDER BY ocorrida_em DESC, id DESC""", (ambiente, hash_))
    saida = []
    for x in linhas:
        d = dict(x)
        d["rotulo"] = rotulo_do_evento(d["status"])
        d["conteudo"] = json.loads(d.get("conteudo_json") or "{}")
        saida.append(d)
    return saida


def contar(con, ambiente: str) -> dict:
    """Quantos esperam a casa e quantos sem consulta. SÓ LÊ."""
    linhas = lista(con, ambiente, limite=5000)
    return {"esperam": sum(1 for p in linhas if p["espera_a_casa"]),
            "sem_detalhe": sum(1 for p in linhas if not p.get("consultado_em")),
            "total": len(linhas)}


# ----------------------------------------------- arquivo estruturado → assento

def _limpo(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def _sem_vazios(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in ("", None)}


def _endereco_da_pessoa(e: dict | None) -> dict:
    """O endereço no vocabulário de `rc_pessoas`. A UF por extenso não passa."""
    import rc_leitura_documentos as LEIT
    e = e or {}
    uf = _limpo(e.get("uf")).upper()
    return _sem_vazios({"endereco": LEIT._endereco(e.get("logradouro"), e.get("numero")),
                        "bairro": _limpo(e.get("bairro")), "cidade": _limpo(e.get("cidade")),
                        "uf": uf if len(uf) == 2 else ""})


def _uf_de_duas_letras(v: Any) -> str:
    t = _limpo(v).upper()
    return t if len(t) == 2 else ""


def _documento_da_pessoa(p: dict, doc: dict | None = None) -> dict:
    """CPF primeiro, como em toda a casa; sem ele, o documento que vier."""
    from leitura_ia import so_digitos
    cpf = so_digitos(p.get("cpf") or p.get("CPF"))
    if len(cpf) == 11:
        return {"documento_tipo": "CPF", "documento_numero": cpf}
    doc = doc or p.get("documento_identificacao")
    if isinstance(doc, dict) and _limpo(doc.get("numero")):
        return _sem_vazios({"documento_tipo": _limpo(doc.get("tipo")).upper(),
                            "documento_numero": _limpo(doc.get("numero")),
                            "documento_orgao": _limpo(doc.get("orgao_emissor"))})
    return {}


def _nascimento(e: dict, avisos: list) -> dict:
    import rc_leitura_documentos as LEIT
    from leitura_ia import data_iso
    r = e.get("registro") or {}
    dados, crianca = r.get("dados_nascimento") or {}, r.get("registrado") or {}
    local = dados.get("local_nascimento") or {}
    end = local.get("endereco") or {}
    sexo = LEIT._sexo(crianca.get("sexo"))
    nat = crianca.get("naturalidade") or {}
    data_fato = data_iso(crianca.get("data_nascimento"))
    valores = {
        "especie": "NASCIMENTO", "nome": _limpo(crianca.get("nome")), "data_fato": data_fato,
        "hora_fato": _limpo(crianca.get("hora_nascimento")),
        "dnv": _limpo(dados.get("numero_dnv")),
        "local_fato_nome": _limpo(local.get("nome_local_nascimento")),
        "local_fato_endereco": ", ".join(x for x in (
            LEIT._endereco(end.get("logradouro"), end.get("numero")), _limpo(end.get("bairro")),
            "/".join(y for y in (_limpo(end.get("cidade")), _uf_de_duas_letras(end.get("uf"))) if y)
        ) if x),
        "ibge_local_nascimento": LEIT._local_nascimento(local.get("tipo_local_nascimento")),
        "ibge_gemeo": "2" if crianca.get("gemelar") else "1",
    }
    pessoas = [_sem_vazios({"papel": "REGISTRADO", "nome": valores["nome"], "sexo": sexo,
                            "data_nascimento": data_fato,
                            "naturalidade_cidade": _limpo(nat.get("municipio")),
                            "naturalidade_uf": _uf_de_duas_letras(nat.get("uf"))})]
    if crianca.get("gemelar"):
        avisos.append(("CONFERIR", "Nascimento gemelar: a ordem veio como "
                       f"«{_limpo(crianca.get('ordem_nascimento'))}». Cada gêmeo é um registro."))
    papeis = {"MAE": ("MAE", "AVO_MATERNO", "AVO_MATERNA", "F"),
              "PAI": ("PAI", "AVO_PATERNO", "AVO_PATERNA", "M")}
    for f in r.get("filiacao") or []:
        chave = LEIT._sem_acento(_limpo(f.get("tipo")))
        if chave not in papeis:
            avisos.append(("CONFERIR", f"Filiação com tipo desconhecido: «{_limpo(f.get('tipo'))}»."))
            continue
        papel, avo1, avo2, sx = papeis[chave]
        nome = _limpo(f.get("nome"))
        if not nome:
            continue
        pessoas.append(_sem_vazios({
            "papel": papel, "nome": nome, "sexo": sx,
            "data_nascimento": data_iso(f.get("data_nascimento")),
            "estado_civil": LEIT._estado_civil(f.get("estado_civil"), sx),
            "profissao": _limpo(f.get("profissao")).lower(),
            "naturalidade_cidade": _limpo(f.get("naturalidade")),
            "naturalidade_uf": _uf_de_duas_letras(f.get("naturalidade_uf")),
            **_documento_da_pessoa(f), **_endereco_da_pessoa(f.get("endereco"))}))
        # A ORDEM DOS ASCENDENTES NÃO DIZ QUEM É AVÔ E QUEM É AVÓ: o arquivo traz só
        # os nomes. Entra pela posição, com aviso, para o balcão confirmar.
        for avo, papel_avo in zip(f.get("ascendentes") or [], (avo1, avo2)):
            if _limpo(avo.get("nome")):
                pessoas.append({"papel": papel_avo, "nome": _limpo(avo.get("nome"))})
        if f.get("ascendentes"):
            avisos.append(("CONFERIR", f"Avós de «{nome}»: o arquivo não diz quem é avô e quem é "
                           "avó; a ordem foi a da lista."))
    declarante = r.get("declarante") or {}
    if _limpo(declarante.get("nome")):
        pessoas.append(_sem_vazios({
            "papel": "DECLARANTE", "nome": _limpo(declarante.get("nome")),
            "profissao": _limpo(declarante.get("profissao")).lower(),
            **_documento_da_pessoa(declarante), **_endereco_da_pessoa(declarante.get("endereco"))}))
    if nat:
        avisos.append(("CONFERIR", "A naturalidade é escolha do declarante (Lei 6.015/1973, art. "
                       "54, § 4º): confirme a que veio no arquivo."))
    return {"valores": valores, "pessoas": pessoas}


def _obito(e: dict, avisos: list) -> dict:
    import rc_leitura_documentos as LEIT
    from leitura_ia import data_iso
    r = e.get("registro") or {}
    falecido, dados = r.get("falecido") or {}, r.get("dados_falecimento") or {}
    local = dados.get("local_falecimento") or {}
    end = local.get("endereco_local_falecimento") or {}
    sep = dados.get("local_sepultamento") or {}
    sexo = LEIT._sexo(falecido.get("sexo"))
    # AS CHAVES DA CAUSA VÊM COM CAIXA DIFERENTE no próprio exemplo do serviço
    # (`causa_morte_A` e `causa_morte_d`), e a parte da causa importa na ordem.
    causas = []
    for item in dados.get("causa_morte") or []:
        for k, v in (item.items() if isinstance(item, dict) else ()):
            if str(k).lower().startswith("causa_morte") and _limpo(v):
                causas.append((str(k).lower(), _limpo(v)))
    medicos = dados.get("medicos") or []
    primeiro = medicos[0] if medicos else {}
    if len(medicos) > 1:
        avisos.append(("CONFERIR", f"Vieram {len(medicos)} médicos; o assento leva o primeiro. "
                       "Confira na DO quem atestou."))
    crm = " ".join(x for x in ("CRM" if _limpo(primeiro.get("crm")) else "", _limpo(primeiro.get("crm")),
                               _limpo(primeiro.get("crm_uf"))) if x)
    valores = {
        "especie": "OBITO", "nome": _limpo(falecido.get("nome")),
        "data_fato": "" if dados.get("data_falecimento_ignorada") else data_iso(dados.get("data_falecimento")),
        "hora_fato": "" if dados.get("hora_falecimento_ignorado") else _limpo(dados.get("hora_falecimento")),
        "numero_do": _limpo(dados.get("do")),
        "cor_raca": LEIT._cor(falecido.get("cor")),
        "local_fato_nome": _limpo(local.get("Nome_local_falecimento") or local.get("nome_local_falecimento")),
        "local_fato_endereco": ", ".join(x for x in (
            LEIT._endereco(end.get("logradouro"), end.get("numero")), _limpo(end.get("bairro")),
            "/".join(y for y in (_limpo(end.get("cidade")), _uf_de_duas_letras(end.get("uf"))) if y)
        ) if x),
        "causa_morte": "; ".join(v for _, v in sorted(causas)),
        "atestante": _limpo(primeiro.get("nome")), "atestante_documento": crm,
        "local_sepultamento": ", ".join(x for x in (
            _limpo(sep.get("nome_local_sepultamento")),
            "/".join(y for y in (_limpo(sep.get("cidade_local_sepultamento")),
                                 _uf_de_duas_letras(sep.get("uf_local_sepultamento"))) if y)) if x),
        "ibge_local_obito": LEIT._local_obito(local.get("tipo_local_falecimento")),
    }
    pessoas = [_sem_vazios({
        "papel": "FALECIDO", "nome": valores["nome"], "sexo": sexo,
        "data_nascimento": "" if falecido.get("data_nascimento_ignorada") else data_iso(falecido.get("data_nascimento")),
        "idade_no_fato": _limpo(falecido.get("idade")) if _limpo(falecido.get("tipo_idade")).lower() == "anos" else "",
        "estado_civil": LEIT._estado_civil(falecido.get("estado_civil"), sexo),
        "profissao": _limpo(falecido.get("profissao")).lower(),
        "naturalidade_cidade": _limpo(falecido.get("naturalidade")),
        "naturalidade_uf": _uf_de_duas_letras(falecido.get("naturalidade_uf")),
        **_documento_da_pessoa(falecido),
        **_endereco_da_pessoa(falecido.get("endereco_residencia_falecido"))})]
    if _limpo(falecido.get("tipo_idade")) and _limpo(falecido.get("tipo_idade")).lower() != "anos":
        avisos.append(("CONFERIR", f"A idade veio em «{_limpo(falecido.get('tipo_idade'))}»: "
                       "digite-a na tela."))
    # A FILIAÇÃO DO ÓBITO SÓ DIZ O SEXO, e com caixa variável: o sexo decide o papel.
    for f in falecido.get("filiacao") or []:
        sx = LEIT._sexo(f.get("sexo"))
        papel = {"M": "PAI", "F": "MAE"}.get(sx)
        if not _limpo(f.get("nome")):
            continue
        if not papel:
            avisos.append(("CONFERIR", f"Filiação sem sexo: «{_limpo(f.get('nome'))}» ficou fora."))
            continue
        pessoas.append({"papel": papel, "nome": _limpo(f.get("nome")), "sexo": sx})
    declarante = r.get("declarante") or {}
    if _limpo(declarante.get("nome")):
        pessoas.append(_sem_vazios({
            "papel": "DECLARANTE", "nome": _limpo(declarante.get("nome")),
            "profissao": _limpo(declarante.get("profissao")).lower(),
            **_documento_da_pessoa(declarante),
            **_endereco_da_pessoa(declarante.get("endereco_residencia_declarante"))}))
    if _limpo((falecido.get("conjuge") or {}).get("nome")):
        avisos.append(("CONFERIR", "Cônjuge informado: «" + _limpo(falecido["conjuge"].get("nome"))
                       + "». Confira se ele vai no teor do assento."))
    avisos.append(("CONFERIR", "O arquivo não traz a natureza da morte para o IBGE: escolha na tela."))
    if r.get("deixou_filhos"):
        avisos.append(("CONFERIR", f"Deixou {len(r.get('filhos') or [])} filho(s) informado(s), além "
                       "de bens, testamento e eleitor: confira no detalhe do protocolo e leve ao teor."))
    return {"valores": valores, "pessoas": pessoas}


def especie_do_estruturado(e: dict | None) -> str:
    """NASCIMENTO ou OBITO, pelo par que o manual manda ler. Outro par: vazio."""
    s = (e or {}).get("solicitacao") or {}
    return PLATAFORMA_ESPECIE.get((_limpo(s.get("plataformaId")).lower(),
                                   _limpo(s.get("tipo_registro")).lower()), "")


def montar_registro(e: dict, *, cns_da_casa: str = "") -> tuple[dict, list[tuple[str, str]]]:
    """O arquivo estruturado no vocabulário da leitura de documentos. SÓ CALCULA.

    O destino que não é esta casa recusa: lavrar assento de outra serventia é o
    defeito que não se desfaz com um clique.
    """
    especie = especie_do_estruturado(e)
    if not especie:
        raise EProtocoloRegra("O arquivo estruturado não é de nascimento nem de óbito.")
    destino = re.sub(r"\D", "", _limpo((e.get("solicitacao") or {}).get("cartorio_destino_cns")))
    casa = re.sub(r"\D", "", _limpo(cns_da_casa))
    avisos: list[tuple[str, str]] = []
    if destino and casa and destino != casa:
        raise EProtocoloRegra(f"O arquivo é para o CNS {destino}, e esta casa é {casa}.")
    junto = _nascimento(e, avisos) if especie == "NASCIMENTO" else _obito(e, avisos)
    if not junto["valores"]["nome"]:
        raise EProtocoloRegra("O arquivo estruturado veio sem o nome de quem se registra.")
    avisos.append(("CONFERIR", "Confronte os dados com os documentos anexados ao protocolo antes de "
                   "lavrar: o arquivo adianta a digitação, e não decide nada."))
    return junto, avisos


def para_rascunho(con, protocolo_id: int, *, cns_da_casa: str, agora: str, por: str) -> dict:
    """O protocolo vira RASCUNHO da tela de assento novo. ESCREVE só o rascunho.

    Mesma fila da leitura de documentos: o arquivo que veio de fora não tem caminho
    mais curto até o livro que qualquer outro.
    """
    import importar_padrao as IMPP
    import rc_leitura_documentos as LEIT
    p = um(con, protocolo_id)
    if p is None:
        raise EProtocoloRegra(f"Não há protocolo nº {protocolo_id}.")
    if p["rascunho_id"]:
        return {"rascunho_id": int(p["rascunho_id"]), "especie": especie_do_estruturado(p["estruturado"]),
                "avisos": [], "ja_havia": True}
    if p["encerrado"]:
        raise EProtocoloRegra(f"O protocolo está encerrado: {p['rotulo'].lower()}.")
    if not p["estruturado"]:
        raise EProtocoloRegra("Este protocolo não tem arquivo estruturado: o registro segue pelo "
                              "fluxo habitual, com os dados e anexos dele.")
    junto, avisos = montar_registro(p["estruturado"], cns_da_casa=cns_da_casa)
    especie = junto["valores"]["especie"]
    # `registro_padrao` recebe o número e escreve «leitura-N» na chave; aqui a chave
    # é do protocolo, e por isso o arquivo se monta com o prefixo próprio.
    texto = json.dumps({
        "formato": IMPP.FORMATO, "versao": IMPP.VERSAO, "especie": "RCPN_ASSENTO",
        "origem": f"e-Protocolo nº {p.get('numero') or protocolo_id}",
        "registros": [{IMPP.CAMPO_DA_CHAVE: f"eprotocolo-{p['ambiente'].lower()}-{p['hash']}",
                       **{k: v for k, v in junto["valores"].items() if LEIT._valor(v)},
                       "pessoas": [{k: v for k, v in x.items() if LEIT._valor(v)}
                                   for x in junto["pessoas"]]}]}, ensure_ascii=False)
    feito = IMPP.para_rascunhos(con, texto, agora=agora, por=por)
    criados = feito.get("criados") or []
    if not criados:
        motivo = "; ".join(str(r.get("motivo") or r) for r in feito.get("recusados") or [])
        raise EProtocoloRegra("A fila de pré-cadastros não aceitou o registro"
                              + (f": {motivo}." if motivo else " (ele já foi recebido)."))
    rascunho_id = int(criados[0]["rascunho_id"])
    banco(con).escrever(
        "UPDATE ep_protocolos SET rascunho_id=%s, rascunho_em=%s, rascunho_por=%s WHERE id=%s",
        (rascunho_id, agora, por, protocolo_id))
    return {"rascunho_id": rascunho_id, "especie": especie, "avisos": avisos, "ja_havia": False,
            "travas": criados[0].get("travas") or []}


def ligar_assento(con, protocolo_id: int, assento_id: int, *, agora: str, por: str) -> None:
    """Diz qual assento saiu deste protocolo. Não lavra: quem lavrou foi a tela dele."""
    bd = banco(con)
    if um(con, protocolo_id) is None:
        raise EProtocoloRegra(f"Não há protocolo nº {protocolo_id}.")
    if not bd.um("SELECT id FROM rc_assentos WHERE id=%s", (assento_id,)):
        raise EProtocoloRegra(f"Não há assento nº {assento_id}.")
    bd.escrever("UPDATE ep_protocolos SET assento_id=%s, assento_em=%s, assento_por=%s WHERE id=%s",
                (assento_id, agora, por, protocolo_id))


def dispensar(con, protocolo_id: int, *, motivo: str, agora: str, por: str) -> None:
    """Tira da lista do balcão o que não é desta casa. Na Central, nada muda."""
    motivo = _limpo(motivo)
    if len(motivo) < 10:
        raise EProtocoloRegra("Diga o motivo (dez letras ou mais): é o que se lê depois.")
    if um(con, protocolo_id) is None:
        raise EProtocoloRegra(f"Não há protocolo nº {protocolo_id}.")
    banco(con).escrever(
        "UPDATE ep_protocolos SET dispensado_em=%s, dispensado_por=%s, dispensado_motivo=%s WHERE id=%s",
        (agora, por, motivo, protocolo_id))


# ------------------------------------------------------------ o cumprimento

def titulares_do_assento(con, assento_id: Any) -> list[dict]:
    """O titular do cumprimento, do assento ligado. SÓ LÊ. Opcional na Central."""
    if not assento_id:
        return []
    a = banco(con).um("SELECT nome, matricula, especie FROM rc_assentos WHERE id=%s", (assento_id,))
    if not a:
        return []
    tipo = {"NASCIMENTO": "Nascimento", "OBITO": "Óbito"}.get(a["especie"], a["especie"])
    return [{"name": a["nome"], "registration": a["matricula"] or "", "registerType": tipo}]


def cumprir(db, sessao, protocolo_id: int, *, certidao: dict, responsavel: dict,
            token_idrc: str, agora: str, por: str, recibo: dict | None = None) -> dict:
    """Cumpre na Central. ESCREVE LÁ. O clique é de gente; o token não se guarda.

    CONSULTA ANTES DE AGIR, como manda o manual: se já está cumprido, a casa só anota
    e não manda de novo. A tentativa fica gravada antes da rede, para a queda no meio
    do caminho não virar um segundo cumprimento às cegas.
    """
    with db.connect() as con:
        p = um(con, protocolo_id)
        if p is None:
            raise EProtocoloRegra(f"Não há protocolo nº {protocolo_id}.")
        titulares = titulares_do_assento(con, p["assento_id"])
    if p["cumprido_em"]:
        raise EProtocoloRegra(f"Este protocolo já foi cumprido em {p['cumprido_em']}.")
    # Confere o corpo ANTES de gastar uma chamada: erro de digitação não vai à rede.
    API.campos_do_cumprimento(certidao, responsavel, titulares)
    detalhe = sessao.protocolo(p["hash"])
    estado = str(detalhe.get("status") or "")
    if estado == "completed":
        with db.transaction() as con:
            guardar_detalhe(con, protocolo_id, detalhe, None, agora=agora)
            banco(con).escrever(
                "UPDATE ep_protocolos SET cumprido_em=%s, cumprido_por=%s WHERE id=%s",
                (agora, f"{por} (já estava cumprido na Central)", protocolo_id))
        return {"ja_estava": True}
    if estado in ENCERRADOS:
        with db.transaction() as con:
            guardar_detalhe(con, protocolo_id, detalhe, None, agora=agora)
        raise EProtocoloRegra(f"O protocolo está encerrado: {rotulo_do_evento(estado).lower()}.")
    with db.transaction() as con:
        banco(con).escrever(
            "UPDATE ep_protocolos SET cumprimento_tentado_em=%s, cumprimento_tentado_por=%s WHERE id=%s",
            (agora, por, protocolo_id))
    resposta = sessao.cumprir(p["hash"], certidao=certidao, responsavel=responsavel,
                              token_idrc=token_idrc, titulares=titulares, recibo=recibo)
    # O QUE FICA É O QUE A CASA DISSE, SEM O TOKEN E COM O CPF SÓ NO FINAL.
    cpf = re.sub(r"\D", "", str(responsavel.get("cpf") or ""))
    guardado = {"certidao": certidao, "responsavel": {"nome": responsavel.get("name"),
                                                      "cpf_final": cpf[-2:]},
                "titulares": len(titulares), "recibo": (recibo or {}).get("nome"),
                "resposta": resposta}
    with db.transaction() as con:
        banco(con).escrever(
            "UPDATE ep_protocolos SET cumprido_em=%s, cumprido_por=%s, cumprimento_json=%s, "
            "status=%s, consultado_em=NULL WHERE id=%s",
            (agora, por, json.dumps(guardado, ensure_ascii=False), "completed", protocolo_id))
    return {"ja_estava": False}


# ------------------------------------------------------------------ o robô

#: Processo da automação (`automacao_processos.MODULOS_COM_PROCESSOS`). Nasce
#: DESLIGADO. A rodada lê e guarda: não altera protocolo, por isso não usa «pode agir».
CATALOGO = (
    {"codigo": "RCPN_EPROTOCOLO", "nome": "e-Protocolo — Unidade Interligada e e-Óbito",
     "setor": "RCPN", "funcao": "eprotocolo.rodada", "timeout_s": 600,
     "agenda": {"dias": [0, 1, 2, 3, 4, 5, 6], "intervalo_min": 5, "janela": ["00:00", "23:59"]},
     "descricao": "A cada 5 minutos, todos os dias: traz as notificações do e-Protocolo, grava e "
                  "consulta cada protocolo. Registro Civil → e-Protocolo — pendências mostra o que "
                  "espera a casa. Uma vez por dia confere o histórico, para recuperar o que se "
                  "perdeu. Nunca lavra nem cumpre: o cumprimento é clique de gente, com o token do "
                  "IdRC."},
)
ESTADO_DA_RECONCILIACAO = "reconciliado_em"


def ambiente_em_uso(leitor) -> str:
    """O ambiente escolhido em configuração. Sem escolha, a homologação: o manual
    manda validar lá antes de produção. `leitor` é `get_setting` ou `ctx.setting`."""
    valor = str(leitor(CHAVE_DO_AMBIENTE, AMBIENTE_PADRAO) or AMBIENTE_PADRAO).strip().upper()
    return valor if valor in (API.HOMOLOGACAO, API.PRODUCAO) else AMBIENTE_PADRAO


def esvaziar_a_fila(db, sessao, ambiente: str, *, agora: str, pausa: float = API.PAUSA_ENTRE_CHAMADAS_S) -> dict:
    """Busca e GRAVA, lote a lote. Grava ANTES de pedir o próximo."""
    novas = lidas = 0
    restam = 0
    for volta in range(API.VOLTAS_POR_RODADA):
        if volta:
            time.sleep(pausa)
        lote, restam = sessao.notificacoes_novas()
        lidas += len(lote)
        # UMA TRANSAÇÃO POR LOTE, e a falha de uma linha não leva as outras: o lote já
        # saiu da fila, e o que não se grava só volta pela reconciliação.
        ruins = 0
        with db.transaction() as con:
            for n in lote:
                try:
                    novas += 1 if guardar_notificacao(con, ambiente, n, agora=agora) else 0
                except EProtocoloRegra:
                    ruins += 1
        if ruins:
            raise EProtocoloRegra(f"{ruins} notificação(ões) sem hash ou status não se gravaram; "
                                  "a reconciliação as procura de novo.")
        if not lote or not restam:
            break
    return {"lidas": lidas, "novas": novas, "restam": restam}


def reconciliar(db, sessao, ambiente: str, *, de: str, ate: str, agora: str,
                pausa: float = API.PAUSA_ENTRE_CHAMADAS_S) -> int:
    """O histórico do período, para recuperar o que não chegou. Só as novas contam."""
    novas, pagina = 0, 1
    while True:
        r = sessao.notificacoes_do_periodo(de, ate, pagina)
        with db.transaction() as con:
            for n in r.get("items") or r.get("data") or []:
                if isinstance(n, dict) and n.get("hash") and n.get("status"):
                    novas += 1 if guardar_notificacao(con, ambiente, n, agora=agora,
                                                      origem="RECONCILIACAO") else 0
        ultima = int(r.get("lastPage") or (r.get("meta") or {}).get("lastPage") or 1)
        if pagina >= ultima:
            return novas
        pagina += 1
        time.sleep(pausa)


def rodada(ctx) -> dict:
    """O processo RCPN_EPROTOCOLO. Não lavra e não cumpre."""
    import automacao_processos as PROC
    import automacao_schema as SCH
    import centrais_cred as CRED
    ambiente = ambiente_em_uso(ctx.setting)
    if not CRED.tem(CRED.EPROTOCOLO, ambiente, ctx.pasta_dados):
        return PROC._sem_credencial(f"e-Protocolo ({ambiente.lower()})",
                                    "Administrativo → Configurações")
    agora = ctx.agora.replace(microsecond=0).isoformat()
    sessao = API.Sessao(ambiente, pasta=ctx.pasta_dados)
    falhas: list[str] = []
    try:
        fila = esvaziar_a_fila(ctx.db, sessao, ambiente, agora=agora)
    except (API.EProtocoloError, EProtocoloRegra, CRED.CredencialError) as erro:
        return PROC._nao_mediu("a fila de notificações do e-Protocolo", erro)
    acoes: list[dict] = [{"acao": "trouxe do e-Protocolo", **fila}]
    # A RECONCILIAÇÃO É DIÁRIA, e a falha dela não apaga o que a fila já trouxe.
    # O estado é do despachante, e por isso a marca volta em `estado`.
    novo_estado = None
    if str(ctx.estado.get(ESTADO_DA_RECONCILIACAO) or "")[:10] != ctx.hoje.isoformat():
        ate = datetime.now(UTC)
        de = ate - timedelta(hours=JANELA_DA_RECONCILIACAO_H)
        try:
            achadas = reconciliar(ctx.db, sessao, ambiente, de=de.strftime("%Y-%m-%dT%H:%M:%S"),
                                  ate=ate.strftime("%Y-%m-%dT%H:%M:%S"), agora=agora)
            # `estado` substitui o guardado inteiro: vai o que já havia, mais a marca.
            novo_estado = {**ctx.estado, ESTADO_DA_RECONCILIACAO: agora}
            if achadas:
                acoes.append({"acao": "recuperou pela reconciliação", "novas": achadas})
        except API.EProtocoloError as erro:
            falhas.append(f"reconciliação: {erro}")
    with ctx.db.connect() as con:
        pendentes = a_consultar(con, ambiente)
    consultados = 0
    for i, p in enumerate(pendentes):
        if i:
            time.sleep(1)
        try:
            consultar(ctx.db, sessao, p["id"], agora=agora)
            consultados += 1
        except API.EProtocoloCheio as erro:
            falhas.append(str(erro))
            break
        except API.EProtocoloError as erro:
            # O que não veio por rede volta na próxima; 403 e 404 ficam na ficha.
            definitivo = isinstance(erro, API.EProtocoloRecusou) and erro.status in (403, 404)
            with ctx.db.transaction() as con:
                _marcar_erro_de_consulta(con, p["id"], str(erro),
                                         definitivo_em=agora if definitivo else None)
            falhas.append(f"protocolo {p['id']}: {erro}")
    with ctx.db.connect() as con:
        n = contar(con, ambiente)
    relato = (f"e-Protocolo ({ambiente.lower()}): {fila['novas']} notificação(ões) nova(s), "
              f"{consultados} protocolo(s) consultado(s), {n['esperam']} esperando a casa."
              + (" Falhas: " + " | ".join(falhas) if falhas else ""))
    achados = [{"esperam": n["esperam"], "sem_detalhe": n["sem_detalhe"], "total": n["total"]}]
    situacao = SCH.ERRO if falhas else (SCH.AVISO if fila["novas"] and n["esperam"] else SCH.OK)
    extra = {"estado": novo_estado} if novo_estado else {}
    return PROC.resultado(situacao, relato[:1500], achados, acoes, **extra)
