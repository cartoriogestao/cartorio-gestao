# -*- coding: utf-8 -*-
"""A API DA INTIMAÇÃO DIGITAL (Resolve/CENPROT) — o transporte, e só ele.

    «a api da cenprot tbm cobre intimacoes pela resolve?»
    «veja aqui: https://docs.resolve.cenprot.org.br/v1110/resolve»
                                        — o oficial, 03/09/2026

**NÃO, E SÃO DUAS APIS DIFERENTES — foi a pergunta dele que separou as duas.**
A «API Cenprot Cartório» (`cenprot_api`) trata anuência, certidão,
cancelamento, renegociação, endereço, pedidos de protesto e custas; medido no
`swagger.yaml` v2.1.0, ela **não tem uma única menção a intimação** — zero
ocorrências de «intima», «14.711» ou «notifica».

A intimação eletrônica é outro produto, com contrato próprio: **«Resolve — API
para gerenciar intimações e apontamentos», OpenAPI 3.1.1, versão 1.11.0**,
guardado em `FONTES_EXTERNAS/cra21/resolve_intimacao_openapi_v1.11.0.json`.

**O COMUNICADO DE 2024 PREVIA ISTO, e por isso ele quase se perdeu.** Ele dizia
que «outros serviços serão disponibilizados nessa API futuramente, conforme os
serviços da Lei 14.711 forem sendo implementados (intimação eletrônica...)» —
e quem lesse só aquele parágrafo concluiria que ainda não existe. Existe, em
outro endereço, e quem o trouxe foi o oficial.

O QUE ISTO VALE PARA ESTA CASA
    Medido no acervo: **1.115 títulos intimados por edital contra 61 em mãos**,
    e 1.068 das 1.139 não-entregas dizem «Ausente». O edital aqui é a rotina, e
    é o caso que a intimação eletrônica ataca.

TRÊS AMBIENTES, E NÃO DOIS
    O contrato declara `servers` com testes, homologação e produção — e os três
    responderam **HTTP 200 «OK»** no `/api/status` em 03/09/2026, com
    certificado válido. É a primeira Central desta casa com um ambiente de
    testes declarado, e `centrais_cred.TESTES` nasceu por causa dela.

A CHAVE É `x-api-key`, E NÃO UM PAR
    O contrato declara três esquemas de segurança (`basicAuth`, `bearerAuth`,
    `apiKeyAuth`) e **as operações usam o terceiro**: todas trazem `x-api-key`
    como cabeçalho obrigatório. Os outros dois estão declarados e não são
    aplicados a operação nenhuma. **Não há `/token` aqui** — ao contrário da
    CENPROT, não se troca senha por token: a chave vai em toda requisição.

    Ela mora em `resolve.cred`, fora do banco, como as outras cinco.

**ESTE MÓDULO NÃO INTIMA NINGUÉM, E NÃO LAVRA NADA.** Ele fala com a Central:
manda o lote, pergunta o estado, traz o PDF. Quem decide **quais títulos vão**,
quem lê o resultado e quem lavra a intimação no livro é o módulo de domínio e,
no fim, o oficial — a regra do CNIB pela sexta vez neste projeto.

**E O QUE SAI DAQUI SAI PORQUE ALGUÉM MANDOU.** Nenhuma função é chamada por
relógio ou por efeito colateral de tela de consulta.

A VALIDAÇÃO DE TLS É A NORMAL, como na CENPROT e ao contrário do selador:
serviço público nacional com certificado de autoridade, medido válido nos três
ambientes. Fixar aqui pararia a casa no dia da renovação.

**A CHAMADA NUNCA ACONTECE DENTRO DE `db.transaction()`** — nenhuma função
daqui recebe `con`. É a regra que existe desde o selador.
"""
from __future__ import annotations

import http.client

import centrais_trava_sandbox as TRAVA
import json
import ssl
import time
import urllib.parse
from typing import Any

import centrais_cred as CRED


class ResolveError(RuntimeError):
    """Não deu para falar com a Resolve, ou ela recusou."""


class ResolveRecusou(ResolveError):
    """A Central respondeu, e a resposta é uma recusa dela."""


# OS TRÊS AMBIENTES, transcritos do `servers` do contrato.
BASE_DO_AMBIENTE: dict[str, str] = {
    CRED.TESTES: "https://api-testes.resolve.cenprot.org.br/intimacao",
    CRED.HOMOLOGACAO: "https://api-homolog.resolve.cenprot.org.br/intimacao",
    CRED.PRODUCAO: "https://api.resolve.cenprot.org.br/intimacao",
}

# OS 16 CAMINHOS. Transcritos do contrato, e há teste que os compara com ele.
CAMINHO: dict[str, str] = {
    # --- o lote: é por aqui que os títulos vão
    "lote_criar": "/api/batches/json",
    "lote_cancelar": "/api/batches/{id}",
    "lote_pdfs": "/api/batches/{id}/pdf-links",
    # --- as intimações
    "intimacoes": "/api/intimations",
    "historico_de_todas": "/api/intimations/status-history",
    "historico_de_uma": "/api/intimations/{id}/status-history",
    "intimacao": "/api/intimations/{id}",
    "por_identificador": "/api/intimations/identificador/{identificador}",
    "marcar_paga": "/api/intimations/{id}/status/paid",
    "marcar_intimada": "/api/intimations/{id}/status/intimated",
    "marcar_cancelada": "/api/intimations/{id}/status/cancel",
    # **ESTES DOIS ESTÃO DECLARADOS E NÃO TÊM FUNÇÃO, de propósito.**
    #
    #   `lote_cancelar` desfaz um lote INTEIRO — e o que o balcão precisa é
    #   cancelar uma intimação, que é `marcar_cancelada`. Um botão que
    #   cancelasse tudo de uma vez faria um clique valer por duas mil.
    #
    #   `link_de_pagamento` só serve a quem tem link próprio habilitado na
    #   conta — o contrato diz «obrigatório quando a configuração do
    #   usuário solicita link próprio». Esta casa não tem essa
    #   configuração, e construir para ela seria construir no escuro.
    #
    #   Ficam declarados para **ninguém os reinventar achando que sumiram**
    #   — é o que se fez com os legados da CENPROT.
    "link_de_pagamento": "/api/intimations/invoice/link/{id}",
    "pdf_da_intimacao": "/api/intimations/{id}/pdf-link",
    # --- o resto
    "relatorio": "/api/reports",
    "simular_webhook": "/api/simulate/message-webhook",
    "status": "/api/status",
}

# O QUE MUDA COISA DO LADO DE LÁ. Há teste que exige que toda função que os use
# passe por `_escrever`, e que `_escrever` nunca seja chamado por passada
# automática — a mesma guarda de `cenprot_api`.
CAMINHOS_QUE_ESCREVEM: frozenset[str] = frozenset({
    "lote_criar", "lote_cancelar", "marcar_paga", "marcar_intimada",
    "marcar_cancelada", "link_de_pagamento", "simular_webhook",
})

# OS DOZE ESTADOS DE UMA INTIMAÇÃO, do `enum` do contrato.
#
#   **Eles são da CENTRAL, e não desta casa.** `INTIMADO` aqui quer dizer que a
#   plataforma considerou o devedor cientificado — e o que faz a intimação
#   valer no livro é o ato que o oficial lavra, não este campo.
ESTADOS: tuple[str, ...] = (
    "PENDENTE", "ENRIQUECENDO", "ENRIQUECIDO", "NAO_ENRIQUECIDO", "ENVIADO",
    "INTIMADO", "SEM_RESPOSTA", "ENTREGUE", "AGUARDANDO_PAGAMENTO", "PAGO",
    "REJEITADO", "CANCELADO",
)

# OS LIMITES SÃO DO CONTRATO, e não precauções minhas.
MINIMO_DO_LOTE = 1
MAXIMO_DO_LOTE = 2000           # `maxItems` do `POST /api/batches/json`
MAXIMO_POR_PAGINA = 100         # `length`, máximo declarado
PAGINA_PADRAO, TAMANHO_PADRAO = 1, 10

# O QUE A CENTRAL EXIGE DE CADA INTIMAÇÃO DO LOTE — os `required` do schema,
# um a um. **Conferir aqui é o que impede o 400 mudo**: a resposta de erro do
# contrato diz só «Dados inválidos. Verifique o payload enviado», sem dizer
# qual item nem qual campo.
OBRIGATORIOS_DA_INTIMACAO: tuple[str, ...] = ("credor", "devedor", "titulo")
OBRIGATORIOS_DO_DEVEDOR: tuple[tuple[str, str], ...] = (
    ("nome", "o nome do devedor"),
    ("documento", "o documento do devedor"),
    # **O ENDEREÇO É OBRIGATÓRIO NO DEVEDOR, E SÓ NELE.** Credor, cedente e
    # apresentante exigem nome e documento; o devedor exige `enderecos`
    # também — o que faz sentido: é a ele que a intimação vai.
    ("enderecos", "ao menos um endereço do devedor"),
)
OBRIGATORIOS_DO_TITULO: tuple[tuple[str, str], ...] = (
    ("valorDivida", "o valor da dívida"),
    ("valorTitulo", "o valor do título"),
    ("valorAPagar", "o valor a pagar"),
    ("numeroTitulo", "o número do título"),
    ("especieTitulo", "a espécie do título"),
    ("dataVencimento", "a data de vencimento"),
    ("nrChave", "a chave única do título na CENPROT"),
)

# A CHAVE ÚNICA TEM 23 CARACTERES, e o contrato diz isso com todas as letras:
# «Obrigatória em produção e deve conter 23 caracteres».
TAMANHO_DA_CHAVE = 23

PRAZO_PADRAO = 30
TENTATIVAS_DE_REDE = 2


# --------------------------------------------------------------- o básico


def base_do_ambiente(ambiente: Any) -> str:
    """O endereço daquele ambiente. Só calcula."""
    qual = _ambiente(ambiente)
    if qual not in BASE_DO_AMBIENTE:
        raise ResolveError(
            f"Não conheço o ambiente «{qual}» da Resolve. Os que o contrato "
            f"declara: " + ", ".join(BASE_DO_AMBIENTE) + ".")
    return BASE_DO_AMBIENTE[qual]


def _ambiente(qual: Any) -> str:
    """**O padrão é homologação** — é onde a casa valida antes da produção.

    O contrato também declara `TESTES`; quem passar esse valor explicitamente
    (simulador, ensaio) continua sendo atendido. Omitir o ambiente **não** cai
    mais em testes: a Configurações não expõe essa linha, e o padrão antigo
    fazia «Testar conexão» ler um slot vazio enquanto homologação já estava
    informada."""
    nome = str(qual or "").strip().upper()
    if not nome:
        return CRED.HOMOLOGACAO
    if nome in BASE_DO_AMBIENTE:
        return nome
    return CRED.HOMOLOGACAO


def _partes(base: str) -> tuple[str, int, str]:
    p = urllib.parse.urlsplit(base)
    if p.scheme != "https":
        # A CHAVE VIAJA NESTA CONEXÃO. Em texto puro, quem estiver na rede a lê
        # — e com ela manda intimação em nome desta serventia.
        raise ResolveError(
            f"A base da Resolve tem de ser https, e veio «{base}».")
    return p.hostname or "", p.port or 443, (p.path or "").rstrip("/")


def chave(ambiente: Any = None, *, pasta=None) -> str:
    """A `x-api-key` daquele ambiente. **É o único lugar que a devolve.**

    **A PORTA AQUI ESTAVA ERRADA, E ELA FECHAVA O MÓDULO INTEIRO** — medido em
    18/09/2026. A função chamava `CRED.credencial`, que é a porta do **par**
    usuário/senha; este depósito guarda **token** (`FORMA_DA_CENTRAL[RESOLVE]
    == TOKEN`), e `credencial` **recusa quem guarda token**, de propósito. As
    duas coisas juntas davam uma recusa **em toda chamada, com a chave já
    gravada**: nenhuma intimação subiria nunca, e a frase que apareceria na
    tela seria a do par («não usa usuário e senha»), que não diz o que fazer.

    É a mesma família de `notas_web` gravar `nt_atos.selo` enquanto a coluna é
    `selo_abertura`: **a peça certa lida pela porta errada.** Aqui a porta é
    `token_guardado`, e é a que as outras duas Centrais de token já usavam
    (`onrcpn_api.token`, `onrtdpj_api.token`) — há teste que confere as três.
    """
    qual = _ambiente(ambiente)
    if not CRED.tem(CRED.RESOLVE, qual, pasta):
        raise ResolveError(
            "A chave da Resolve ainda não foi informada para o ambiente "
            f"{qual}. Ela é a `x-api-key` que a plataforma entrega depois da "
            "adesão à Intimação Digital, e se cadastra em Administrativo → "
            "Configurações, na tabela das Centrais.")
    return CRED.token_guardado(CRED.RESOLVE, qual, pasta)


# ------------------------------------------------------------- o transporte


def _bater(ambiente: str, metodo: str, caminho: str, *,
           corpo: bytes | None = None, cabecalhos: dict | None = None,
           prazo: int = PRAZO_PADRAO, com_chave: bool = True,
           pasta=None) -> dict:
    """Uma requisição. Devolve `{status, json, texto}` — não estoura por 4xx.

    **Quem decide o que fazer com um 404 é quem chamou.** Intimação que não
    existe mais é caso normal numa Central que trabalha o dia inteiro.
    """
    base = base_do_ambiente(ambiente)
    hospedeiro, porta, prefixo = _partes(base)
    # Trava sandbox: Resolve so no simulador :8912 (ou recusa).
    hospedeiro, porta = TRAVA.destino_seguro(hospedeiro, porta)
    cabecas = {"Accept": "application/json",
               # O contrato pede `User-Agent` (opcional) e diz que é a
               # «identificação do cliente HTTP». Dizer quem somos é o que
               # permite a Central nos achar num suporte.
               "User-Agent": "CartorioGestao"}
    cabecas.update(cabecalhos or {})
    if com_chave:
        cabecas["x-api-key"] = chave(ambiente, pasta=pasta)

    contexto = ssl.create_default_context()
    ultimo = None
    for tentativa in range(TENTATIVAS_DE_REDE + 1):
        conexao = None
        try:
            conexao = http.client.HTTPSConnection(
                hospedeiro, porta, timeout=prazo, context=contexto)
            conexao.request(metodo, prefixo + caminho, body=corpo,
                            headers=cabecas)
            r = conexao.getresponse()
            bruto = r.read()
            texto = bruto.decode("utf-8", errors="replace")
            try:
                como_json = json.loads(texto) if texto.strip() else None
            except ValueError:
                como_json = None
            return {"status": r.status, "json": como_json, "texto": texto}
        except (OSError, ssl.SSLError, http.client.HTTPException) as erro:
            ultimo = erro
            # **SÓ O QUE NÃO CHEGOU SE REPETE.** Um `POST` que a Central pode
            # ter recebido não se manda de novo sozinho: um lote repetido é
            # intimação dobrada, e intimação é papel que chega na casa de
            # alguém.
            if metodo != "GET":
                break
            if tentativa >= TENTATIVAS_DE_REDE:
                break
            time.sleep(1 + tentativa)
        finally:
            if conexao is not None:
                conexao.close()
    raise ResolveError(
        f"Não consegui falar com a Resolve em {hospedeiro}: {ultimo}. "
        f"Confira a internet da serventia e tente de novo; nada foi enviado.")


def _resposta_ou_erro(r: dict, o_que: str) -> Any:
    """A resposta, ou a recusa da Central com a frase que ela deu."""
    if 200 <= int(r.get("status") or 0) < 300:
        return r.get("json")
    corpo = r.get("json")
    dela = ""
    if isinstance(corpo, dict):
        dela = str(corpo.get("message") or corpo.get("error")
                   or corpo.get("mensagem") or "").strip()
    if not dela:
        dela = (r.get("texto") or "").strip()[:300]
    # **O 400 DIZ QUAL CAMPO, EM `errors`** — medido na homologação em
    # 13/10/2026: `{"message": "Body inválido", "errors": [{"target":
    # {"itemIndex": 0, …}, "property": "credor.tipoDocumento", "constraints":
    # {…: "A propriedade tipoDocumento não é permitida."}}]}`. Mostrar só o
    # `message` deixava o balcão com «Body inválido» e mais nada.
    if isinstance(corpo, dict) and isinstance(corpo.get("errors"), list):
        partes = []
        for erro in corpo["errors"][:5]:
            if not isinstance(erro, dict):
                continue
            alvo = erro.get("target") if isinstance(erro.get("target"), dict) else {}
            regras = erro.get("constraints") if isinstance(erro.get("constraints"), dict) else {}
            onde = (f"intimação {int(alvo['itemIndex']) + 1}, "
                    if str(alvo.get("itemIndex", "")).isdigit() else "")
            partes.append(f"{onde}{erro.get('property') or '?'}: "
                          + "; ".join(str(v) for v in regras.values()))
        if partes:
            dela = f"{dela} — " + " | ".join(partes)
    status = r.get("status")
    if status == 401:
        dela = dela or "chave de API inválida ou ausente"
    elif status == 403:
        dela = dela or "esta chave não tem permissão para isso"
    motivo = dela or "sem motivo informado"
    raise ResolveRecusou(
        f"A Resolve recusou {o_que} (HTTP {status}): {motivo}.")


def _preencher(chave_do_caminho: str, **partes) -> str:
    caminho = CAMINHO[chave_do_caminho]
    for nome, valor in partes.items():
        alvo = "{" + nome + "}"
        if alvo not in caminho:
            continue
        pedaco = urllib.parse.quote(str(valor or "").strip(), safe="")
        if not pedaco:
            raise ResolveError(
                f"Falta «{nome}» para montar o endereço {caminho}.")
        caminho = caminho.replace(alvo, pedaco)
    if "{" in caminho:
        raise ResolveError(f"Endereço incompleto: {caminho}.")
    return caminho


def _listar(ambiente: str, chave_do_caminho: str, o_que: str, *,
            parametros: dict | None = None, pasta=None, **partes) -> Any:
    caminho = _preencher(chave_do_caminho, **partes)
    if parametros:
        limpos = {k: v for k, v in parametros.items() if v not in (None, "")}
        if limpos:
            caminho += "?" + urllib.parse.urlencode(limpos)
    return _resposta_ou_erro(
        _bater(ambiente, "GET", caminho, pasta=pasta), o_que)


def _escrever(ambiente: str, chave_do_caminho: str, o_que: str, *,
              metodo: str = "POST", corpo: Any = None, pasta=None,
              **partes) -> Any:
    if chave_do_caminho not in CAMINHOS_QUE_ESCREVEM:
        raise ResolveError(
            f"«{chave_do_caminho}» não está declarado como caminho que muda "
            f"coisa na Central. Isso é engano de programação, e não do balcão.")
    caminho = _preencher(chave_do_caminho, **partes)
    dados = None
    cabecas = {}
    if corpo is not None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        cabecas["Content-Type"] = "application/json"
    return _resposta_ou_erro(
        _bater(ambiente, metodo, caminho, corpo=dados, cabecalhos=cabecas,
               pasta=pasta), o_que)


# ------------------------------------------------------------------ o lote


def conferir_lote(intimacoes: Any) -> list[dict]:
    """O que a Central exige, conferido AQUI. Só calcula — não manda nada.

    **A resposta de erro dela é muda**: o contrato declara, para o 400, a frase
    «Dados inválidos. Verifique o payload enviado» — sem dizer qual das duas
    mil intimações nem qual campo. Conferir antes é o que dá ao balcão uma
    frase com o número do item.
    """
    lote = list(intimacoes or [])
    if len(lote) < MINIMO_DO_LOTE:
        raise ResolveError("Não há intimação nenhuma para enviar.")
    if len(lote) > MAXIMO_DO_LOTE:
        raise ResolveError(
            f"A Resolve aceita no máximo {MAXIMO_DO_LOTE} intimações por "
            f"envio, e são {len(lote)}. Mande em partes.")

    for i, item in enumerate(lote, 1):
        item = item or {}
        for campo in OBRIGATORIOS_DA_INTIMACAO:
            if not item.get(campo):
                raise ResolveError(
                    f"A intimação {i} do lote está sem «{campo}», que a "
                    f"Central exige.")
        # Credor, cedente e apresentante, QUANDO VÃO, vão com nome e
        # documento — o contrato exige os dois, e a Central responde só «Body
        # inválido», sem dizer qual (medido na homologação em 13/10/2026).
        for papel in ("credor", "cedente", "apresentante"):
            pessoa = item.get(papel)
            if pessoa is None and papel != "credor":
                continue
            for campo in ("nome", "documento"):
                if not (pessoa or {}).get(campo):
                    raise ResolveError(
                        f"A intimação {i} do lote está com o {papel} sem "
                        f"«{campo}», que a Central exige quando ele vai.")
        devedor = item.get("devedor") or {}
        for campo, o_que in OBRIGATORIOS_DO_DEVEDOR:
            if not devedor.get(campo):
                raise ResolveError(
                    f"A intimação {i} do lote está sem {o_que} («{campo}»).")
        titulo = item.get("titulo") or {}
        for campo, o_que in OBRIGATORIOS_DO_TITULO:
            valor = titulo.get(campo)
            if valor in (None, "") or (isinstance(valor, str)
                                       and not valor.strip()):
                raise ResolveError(
                    f"A intimação {i} do lote está sem {o_que} («{campo}»).")
        nr = str(titulo.get("nrChave") or "").strip()
        if len(nr) != TAMANHO_DA_CHAVE:
            # **A CHAVE DE 23 DÍGITOS É A DO CENPROT**, a mesma que este
            # projeto explicou em 01/09 e que `pt_titulos.chave_cenprot`
            # guarda. Mandar outra coisa aqui faria a Central intimar sobre um
            # título que ela não sabe qual é.
            raise ResolveError(
                f"A chave única da intimação {i} tem {len(nr)} caracteres, e a "
                f"Central exige {TAMANHO_DA_CHAVE}. Ela é a chave do CENPROT "
                f"do título — a que vem no XML diário, e que a tela «Chave do "
                f"CENPROT» grava.")
    return lote


def criar_lote(intimacoes: Any, ambiente: Any = None, *, pasta=None) -> Any:
    """Manda o lote de intimações. **ESCREVE NA CENTRAL, e o devedor recebe.**

    Devolve `{message, id, intimacoes:[{_id, identificador, externalId}]}` —
    e **o `id` é o do LOTE**, que é por onde se cancela e se pegam os PDFs.
    """
    lote = conferir_lote(intimacoes)
    return _escrever(_ambiente(ambiente), "lote_criar",
                     "criar o lote de intimações", corpo=lote, pasta=pasta)


def pdfs_do_lote(lote_id: Any, ambiente: Any = None, *, pasta=None) -> Any:
    """As URLs dos PDFs das intimações do lote. SÓ LÊ."""
    return _listar(_ambiente(ambiente), "lote_pdfs",
                   "buscar os PDFs do lote", pasta=pasta, id=lote_id)


# ------------------------------------------------------------ as intimações


def intimacoes(ambiente: Any = None, *, estado: str = "",
               pagina: int | None = None, quantas: int | None = None,
               inicio: str = "", fim: str = "",
               atualizadas_de: str = "", atualizadas_ate: str = "",
               pasta=None) -> Any:
    """A lista, com os filtros do contrato. SÓ LÊ.

    **São DOIS pares de data, e eles respondem perguntas diferentes**:
    `dataInicio`/`dataFim` filtram por criação, e
    `dataAtualizacaoInicio`/`dataAtualizacaoFim` por última mudança. Quem quer
    saber «o que andou desde ontem» precisa do segundo par; usar o primeiro
    devolveria as criadas ontem, e não as que mudaram.
    """
    qual = str(estado or "").strip().upper()
    if qual and qual not in ESTADOS:
        raise ResolveError(
            f"Não conheço o estado «{qual}». Os que a Central declara: "
            + ", ".join(ESTADOS) + ".")
    quantos = int(quantas or TAMANHO_PADRAO)
    if quantos > MAXIMO_POR_PAGINA:
        raise ResolveError(
            f"A Central devolve no máximo {MAXIMO_POR_PAGINA} por página, e "
            f"foram pedidas {quantos}.")
    return _listar(
        _ambiente(ambiente), "intimacoes", "listar as intimações", pasta=pasta,
        parametros={"status": qual, "page": pagina, "length": quantas,
                    "dataInicio": inicio, "dataFim": fim,
                    "dataAtualizacaoInicio": atualizadas_de,
                    "dataAtualizacaoFim": atualizadas_ate})


def intimacao(qual: Any, ambiente: Any = None, *, pasta=None) -> Any:
    """Uma intimação por `id`, `shortId` **ou** identificador. SÓ LÊ."""
    return _listar(_ambiente(ambiente), "intimacao", "buscar a intimação",
                   pasta=pasta, id=qual)


def por_identificador(identificador: Any, ambiente: Any = None, *,
                      pasta=None) -> Any:
    """Todas as intimações com aquele identificador da casa. SÓ LÊ.

    **São várias de propósito**: o mesmo título pode ser intimado mais de uma
    vez, e a Central devolve `total` com a lista.
    """
    return _listar(_ambiente(ambiente), "por_identificador",
                   "buscar pelo identificador da casa", pasta=pasta,
                   identificador=identificador)


def historico(inicio: str, fim: str, ambiente: Any = None, *,
              estado: str = "", pasta=None) -> Any:
    """O histórico de estados do período. SÓ LÊ.

    **As duas datas são obrigatórias**, e o contrato as marca assim — sem elas
    a Central responde 400. E o filtro de estado é sobre o **histórico**, e não
    sobre o estado atual: quem procura «o que foi entregue em setembro» acha
    aqui, e não na lista.
    """
    if not str(inicio or "").strip() or not str(fim or "").strip():
        raise ResolveError(
            "O histórico da Resolve exige a data inicial e a final — a "
            "Central recusa sem as duas.")
    return _listar(
        _ambiente(ambiente), "historico_de_todas",
        "buscar o histórico das intimações", pasta=pasta,
        parametros={"startDate": inicio, "endDate": fim,
                    "status": str(estado or "").strip().upper()})


def historico_de(qual: Any, ambiente: Any = None, *, completo: bool = False,
                 pasta=None) -> Any:
    """O histórico de uma intimação. SÓ LÊ.

    **`completo` troca o que se vê**: sem ele vem o histórico do CARTÓRIO; com
    ele, o do sistema inteiro. O do cartório é o que o balcão precisa ler.
    """
    return _listar(_ambiente(ambiente), "historico_de_uma",
                   "buscar o histórico da intimação", pasta=pasta, id=qual,
                   parametros={"fullHistory": "true" if completo else None})


def pdf_da_intimacao(qual: Any, ambiente: Any = None, *, pasta=None) -> Any:
    """A URL do PDF daquela intimação. SÓ LÊ."""
    return _listar(_ambiente(ambiente), "pdf_da_intimacao",
                   "gerar o link do PDF da intimação", pasta=pasta, id=qual)


def relatorio(inicio: str, fim: str, ambiente: Any = None, *,
              pasta=None) -> Any:
    """O relatório de pagamentos do período. SÓ LÊ. As duas datas obrigatórias."""
    if not str(inicio or "").strip() or not str(fim or "").strip():
        raise ResolveError(
            "O relatório da Resolve exige a data inicial e a final.")
    return _listar(_ambiente(ambiente), "relatorio",
                   "buscar o relatório de pagamentos", pasta=pasta,
                   parametros={"startDate": inicio, "endDate": fim})


# ------------------------------------------------- o que muda o estado lá


def marcar_paga(qual: Any, ambiente: Any = None, *, pasta=None) -> Any:
    """Diz à Central que o título foi PAGO. **ESCREVE.**

    **Quem recebe o dinheiro é a serventia**, e é ela que sabe. Sem esta
    chamada a plataforma continuaria cobrando quem já pagou.
    """
    return _escrever(_ambiente(ambiente), "marcar_paga",
                     "marcar a intimação como paga", metodo="PATCH",
                     pasta=pasta, id=qual)


def marcar_intimada(qual: Any, ambiente: Any = None, *, pasta=None) -> Any:
    """Diz à Central que o devedor foi INTIMADO. **ESCREVE.**

    **É o caso da intimação que aconteceu FORA dela** — em mãos, ou por
    edital. Sem isto a plataforma seguiria mandando mensagem a quem já foi
    intimado pelo caminho de papel.
    """
    return _escrever(_ambiente(ambiente), "marcar_intimada",
                     "marcar a intimação como cumprida", metodo="PATCH",
                     pasta=pasta, id=qual)


def cancelar_intimacao(qual: Any, ambiente: Any = None, *, pasta=None) -> Any:
    """Tira a intimação da fila de envio. **ESCREVE.**

    É o que se faz quando o título é retirado, pago no balcão ou sustado — e a
    sustação judicial é o caso que mais importa: `protesto` já recusa os três
    atos, e deixar a mensageria correndo mandaria cobrança de título que o juiz
    mandou parar.
    """
    return _escrever(_ambiente(ambiente), "marcar_cancelada",
                     "cancelar a intimação", metodo="PATCH", pasta=pasta,
                     id=qual)


# ------------------------------------------------------------ o diagnóstico


def status(ambiente: Any = None, *, pasta=None) -> dict:
    """Pergunta se a Central está de pé. **NÃO precisa de chave.**

    É o único caminho do contrato sem `x-api-key`, e por isso é o que responde
    «a internet e o endereço estão bons» **antes** de o oficial ter credencial
    nenhuma. Medido em 03/09/2026: os três ambientes devolveram `200 OK`.
    """
    qual = _ambiente(ambiente)
    r = _bater(qual, "GET", CAMINHO["status"], com_chave=False, prazo=15,
               pasta=pasta)
    de_pe = 200 <= int(r.get("status") or 0) < 300
    return {"ok": de_pe, "ambiente": qual, "base": base_do_ambiente(qual),
            "status": r.get("status"),
            "resposta": (r.get("texto") or "").strip()[:120],
            "motivo": ("a Central respondeu" if de_pe
                       else "a Central não respondeu como esperado")}


def diagnostico(ambiente: Any = None, *, pasta=None) -> dict:
    """Tenta uma leitura com a chave e diz o que aconteceu. **Não manda nada.**

    É o botão «testar a conexão». **Usa a listagem com uma página de um item**,
    e não o `/api/status`: aquele responde sem chave, e passaria mesmo com a
    credencial errada — o teste que sempre passa não testa nada.
    """
    qual = _ambiente(ambiente)
    if not CRED.tem(CRED.RESOLVE, qual, pasta):
        return {"ok": False, "ambiente": qual,
                "motivo": "A chave da Resolve ainda não foi informada para "
                          "este ambiente."}
    try:
        intimacoes(qual, pagina=1, quantas=1, pasta=pasta)
    except ResolveError as erro:
        return {"ok": False, "ambiente": qual, "motivo": str(erro)}
    return {"ok": True, "ambiente": qual, "base": base_do_ambiente(qual),
            "motivo": "Autenticou na Resolve e a listagem respondeu."}
