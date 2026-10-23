"""O TRANSPORTE DO CNIB — a API das Serventias do ONR.

A Central Nacional de Indisponibilidade de Bens é onde o juiz publica a ordem
que torna os bens de alguém indisponíveis, e onde a serventia publica o que
registrou sobre eles. Este módulo **fala com ela**: pede o token, manda o
pedido e devolve a resposta.

O QUE ELE NÃO É, e a lista é curta de propósito: **não decide, não grava e não
substitui o espelho** (`ri_cnib_ordens`). Quem decide se uma ordem vira
averbação é o oficial — `ri_cnib.py` já faz isso e não mudou. Quem grava é o
atualizador, na forma de sempre. Aqui só entra o que fala com a rede.

POR QUE ELE NÃO MORA DENTRO DE `onr_api.py` — e isto foi medido, não escolhido.
O `onr_api.py` é o transporte do **Registro de Imóveis** do ONR
(`api.registrodeimoveis.org.br`), e ele não tem uma única função de CNIB. O
CNIB é **outra Central, com outra credencial e outro provedor de identidade**:
o par que autentica nela tem `client_id` **`cns-000000`** — que não está em
`onr.cred` — e o token sai de `auth.id.onr.org.br` com o escopo
`cnib-serventia-api`, enquanto o do RI sai de `api.registrodeimoveis.org.br`.
São dois cadastros, dois endereços e dois escopos. Ver `centrais_cred.CNIB`.


AS MEDIÇÕES QUE GOVERNam ESTE ARQUIVO — 18/09/2026, contra a produção

Elas estão aqui porque cada uma custou uma ida à rede, e porque o que se lê do
contrato **não** é o que a Central responde.

1. **O CONTRATO NÃO DECLARA ENDEREÇO.** O
   `FONTES_EXTERNAS/onr_serventias/swagger_v1.json` é OpenAPI 3.0.1
   (`SERVENTIAS API vv1`), traz **7 caminhos, todos POST**, e vem com
   `servers: null`. O endereço de produção foi medido em DNS —
   `serventia-api.onr.org.br` (2.18.20.134) —, e **as variantes de homologação
   não resolvem**: `serventia-api-hml`, `-homolog`, `-teste` e `.sandbox` não
   existem. Por isso esta Central tem **um ambiente só**, e não é escolha: é o
   que existe.

2. **O CONTRATO DECLARA OS CAMPOS CERTOS DE MANDA, E NOMES ERRADOS DE LÊ.**
   `ViewOrderRequestNew` declara obrigatórios `cpf_usuario`, `pagina_inicial`,
   `proxima_pagina` e `tamanho_pagina` — e é exatamente o que a casa manda.
   Mas a **resposta** ele descreve em `CustomVisualizationResponse`, com
   `paginação` **com til** e um `VisualizationPaging` de oito campos
   (`pageIndex`, `totalRows`, `pageSize`, `pageForward`…) **nenhum dos quais
   aparece na resposta de verdade**. Quem ler o contrato para saber o nome do
   campo do total não acha. Ver `PAGINACAO_REAL`, abaixo.

3. **HÁ TRÊS FORMAS DE RESPOSTA, e elas foram lidas nos 26 brutos.**
   (a) a normal, `data.ordens` mais `data.paginacao`, em 15 deles; (b) a
   vazia, **embrulhada duas vezes** em camelCase, `data.data.orders` mais
   `data.data.totalCount`, com uma frase em `data.message`, em 6; e (c) a da
   consulta por documento, `data.protocolos`, em 3. Nenhuma das três é o
   objeto do contrato.

4. **`ordens_visualizadas` É A FLAG QUE DECIDE O DESENHO, e as duas metades
   foram medidas.** Com `False` a leitura **CONSOME A FILA**: 341.697 ordens
   ficaram 341.497 numa página de 200. Com `True` ela **NÃO consome**: 341.496
   antes e 341.496 depois. O padrão deste módulo é `True` — e o padrão é a
   decisão que protege a casa, porque conferir, testar a conexão e clicar duas
   vezes não podem tirar ordem da fila de ninguém.

5. **A JANELA FILTRA PELA DATA DA ATIVIDADE, e não pela data do pedido.** Uma
   janela de junho/2026 devolveu ordem com `datapedido` de 2012 — porque o
   `cancelamentodata` era de junho/2026. É isto que faz a janela servir para
   receber o **cancelamento de ordem antiga**, que é o caso que o atualizador
   mais precisa pegar.

6. **AS PÁGINAS NÃO SÃO DISJUNTAS.** Numa varredura de 3.000 ordens vieram
   2.996 distintas — quatro repetiram entre páginas. Quem grava **tem** de
   fazer UPSERT pela chave, e não confiar em página como se fosse lote.

7. **O ZERO DA CENTRAL NÃO É PROVA DE AUSÊNCIA.** A mesma forma vazia,
   com a mesma frase — «Não há ordens para os critérios informados.» —, veio
   para dias que **tinham** ordens, e horas depois as ordens apareceram. O
   dado **não distingue** «não há» de «ainda não me chegou», e é por isso que
   este módulo **devolve a frase e não conclui nada**: quem decide o que fazer
   com o zero é o atualizador, com janela sobreposta. Ver
   `ordens_na_janela`, campo `vazio`.

O QUE ESTE MÓDULO **NÃO** TENTA EXPLICAR, e fica dito em vez de adivinhado:
`cancelamentotipo` traz `1` e `2` e **não há enum nenhum no contrato** — 2.591
ordens com `1` e 61 com `2`, no mesmo `ordemstatus` «CONCLUÍDO». Não se inventa
o significado de um código que a norma não publicou: os dois valores são
guardados, e quem os interpreta é quem tem o processo na mão.
"""
from __future__ import annotations

import json
import time
import unicodedata
import urllib.parse
from typing import Any

import centrais_cred as CRED
import centrais_http as HTTP

# O CONTRATO MORA NA CASA, e não viaja no `.cgu` (a decisão é de
# `atribuicoes.py`, para as fontes externas). Ele não é lido em execução: o
# que se lê dele se transcreveu para cá, com a data e o que se mediu.
CONTRATO_NO_PROJETO = "FONTES_EXTERNAS/onr_serventias/swagger_v1.json"

# **O ENDEREÇO NÃO VEM DO CONTRATO** — ele declara `servers: null`. Este foi
# medido em DNS (2.18.20.134). Sem os dois pontos: o `partes()` de baixo
# completa a porta.
BASE_POR_AMBIENTE: dict[str, str] = {
    CRED.PRODUCAO: "https://serventia-api.onr.org.br",
}

# O TOKEN. Está no contrato, em `securitySchemes.oauth2.flows.clientCredentials`
# — e é a única coisa de endereço que ele declara.
AUTENTICACAO = "https://auth.id.onr.org.br/connect/token"
ESCOPO = "cnib-serventia-api"

PRAZO_PADRAO = 60
TENTATIVAS_DE_REDE = 2

# QUANTO ANTES DE VENCER SE PEDE TOKEN NOVO. O `expires_in` medido é 3.600;
# a margem evita que a chamada seguinte saia com um token que vence no caminho.
MARGEM_DO_TOKEN = 60

CABECALHO_DO_TOKEN = "Authorization"
PREFIXO_DO_TOKEN = "Bearer "
TIPO_DO_FORMULARIO = "application/x-www-form-urlencoded"
TIPO_DO_JSON = "application/json"
GRANT_DA_CASA = "client_credentials"

# **500 NÃO É DO CONTRATO.** O contrato declara `tamanho_pagina` como inteiro
# sem máximo nenhum. 500 é o que esta casa mandou e o que voltou —
# `total_ordens_retornadas_por_pagina: 500` —; acima disso **não se mediu**, e
# por isso não se manda. Subir este número sem medir seria pedir à Central o
# que ela não prometeu.
TAMANHO_DA_PAGINA = 500

# O FREIO DO LAÇO. Sem ele, uma Central que devolvesse `tem_proxima_pagina:
# true` para sempre faria o servidor da serventia varrer o país. O teto é
# alto e declarado: 200 × 500 = 100.000 ordens, muito acima de qualquer janela
# desta casa — e quando ele é alcançado a resposta **diz que parou nele**.
MAXIMO_DE_PAGINAS = 200


class CnibError(RuntimeError):
    """Não deu para falar com o CNIB. Mensagem pronta para o balcão."""


class CnibRecusou(CnibError, ValueError):
    """A Central respondeu, e recusou o que se pediu.

    **É `ValueError` porque é erro de regra**, e a regra da casa é esta: erro de
    regra não vira HTTP 500, vira `flash(..., 'danger')` com o que fazer. Os
    dois erros deste módulo são coisas diferentes e pedem providências
    diferentes — `CnibError` é «não chegou lá» (rede, credencial), e
    `CnibRecusou` é «chegou, e ela disse não» (dado, parâmetro) —, e por isso
    são duas classes; mas quem só quiser tratar tudo apanha `CnibError` e
    apanha as duas.
    """


# ------------------------------------------------------------------ os nomes
#
# O QUE A CENTRAL MANDA, e o que o contrato declara de cada um. Medido nos
# 6.218 registros de 26 brutos: **16 campos, todos snake_case, zero camelCase**.
#
#   `OrderResponse` declara **11** deles, e a casa recebe os 11:
#   `protocoloindisponibilidade`, `status`, `datapedido`, `numeroprocesso`,
#   `telefone`, `nomeinstituicao`, `forumvara`, `usuario`, `email`,
#   `ordemstatus` e `partes`.
#
#   **E recebe 5 que ninguém declarou** — `ordemprioritaria`,
#   `segredodejustica`, `cancelamentodeindisponibilidade`, `cancelamentotipo` e
#   `cancelamentodata`. São os mesmos fatos que `VisualizationOrder` nomeia em
#   camelCase (`isPriorityOrder`, `isSecretJustice`, `cancellationProtocol`,
#   `cancellationType`, `cancellationCreatedOn`) — **e nenhum desses 26 nomes
#   aparece na resposta real**. É por isso que este dicionário existe: quem for
#   ler a ordem lê daqui, e não do contrato.
CAMPOS_DA_ORDEM: dict[str, str] = {
    "status": "INDISPONIBILIDADE quando a ordem pede, CANCELAMENTO quando ela desfaz",
    "protocoloindisponibilidade": "o protocolo DA ORDEM — e também o que o cancelamento cita como alvo",
    "numeroprocesso": "o processo judicial",
    "usuario": "quem pediu, na Central",
    "ordemstatus": "o andamento. **Três grafias medidas para o mesmo estado**",
    "forumvara": "o juízo",
    "nomeinstituicao": "a hierarquia da instituição, com `>` entre os níveis",
    "email": "contato de quem pediu",
    "telefone": "contato de quem pediu",
    "datapedido": "`dd/mm/aaaa hh:mm:ss` — **não é ISO**, e é o que mais se erra",
    "ordemprioritaria": "booleano, e vem `None` em 2.198 ordens antigas",
    "segredodejustica": "booleano, e vem `None` em 2.198 ordens antigas",
    "partes": "a lista — **40% das ordens têm mais de uma**",
    "cancelamentodeindisponibilidade": "o protocolo DO CANCELAMENTO, não o da ordem cancelada",
    "cancelamentotipo": "`1` ou `2`. **Sem enum no contrato — não se interpreta aqui**",
    "cancelamentodata": "`dd/mm/aaaa hh:mm:ss`. É por esta data que a janela filtra",
}

# A PAGINAÇÃO DE VERDADE. **Zero nomes em comum com o contrato.**
PAGINACAO_REAL: dict[str, str] = {
    "pagina_atual": "a página que voltou",
    "total_ordens_encontradas": "o total da janela — **só vem na primeira página**, e não é confiável a ponto de se guardar",
    "total_ordens_retornadas_por_pagina": "o tamanho que a Central aplicou",
    "ordens_restantes": "quantas faltam depois desta",
    "tem_proxima_pagina": "booleano — **é ele que o laço lê**, e não o `proxima_pagina` do pedido",
}


# ------------------------------------------------------------- os caminhos
#
# **OS SETE ESTÃO AQUI**, inclusive os que este módulo não liga: caminho que
# some da lista é caminho que alguém reinventa. Os medidos e usados pela casa
# são o `visualizar_v2` e o `consultar`; os outros cinco estão declarados e
# **não ligados**, e o `_bater` recusa quem não estiver em `CAMINHOS_LIGADOS`.
CAMINHO: dict[str, str] = {
    "visualizar_v2": "/api/v2/ordem/visualizar",
    "consultar": "/api/ordem/consultar",
    # --- medidos no contrato e NUNCA usados por esta casa
    "visualizar_v1": "/api/ordem/visualizar",
    "responder": "/api/ordem/responder",
    "responder_lista": "/api/ordem/responder/lista",
    "documentos_tipos": "/api/documentos/tipos",
    "teste_log": "/api/Operation/testeLogInformationLogError",
}

METODO_DO_CAMINHO: dict[str, str] = {nome: "POST" for nome in CAMINHO}

CAMINHOS_LIGADOS: frozenset[str] = frozenset({"visualizar_v2", "consultar"})


# ============================================================ a credencial


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def base_do_ambiente(ambiente: Any = None) -> str:
    """O endereço daquele ambiente. **Aqui há um só, e ele foi medido.**"""
    onde = CRED._ambiente(ambiente) if ambiente else ambiente_da_casa()
    if onde not in BASE_POR_AMBIENTE:
        raise CnibError(
            f"O CNIB não tem ambiente «{ambiente}». Ele tem um só — "
            f"{CRED.PRODUCAO} —, porque o contrato não declara endereço de "
            f"homologação e as variantes medidas não existem em DNS.")
    return BASE_POR_AMBIENTE[onde]


def ambiente_da_casa() -> str:
    """Em que ambiente esta casa fala com o CNIB. **É o de produção, e é o único.**"""
    return CRED.ambientes_de(CRED.CNIB)[0]


def tem_credencial(ambiente: Any = None, *, pasta=None) -> bool:
    """A tela pergunta isto antes de oferecer botão. **Não devolve o segredo.**"""
    return CRED.tem(CRED.CNIB, ambiente or ambiente_da_casa(), pasta)


def credencial(ambiente: Any = None, *, pasta=None) -> tuple[str, str]:
    """`(client_id, client_secret)`. **Lida do disco a cada renovação.**

    O `client_secret` **nunca** entra em memória guardada nem no banco: o banco
    viaja no backup, e o backup já saiu da serventia. O que se guarda é o
    **token**, que é derivado e vence sozinho — a mesma razão do selador, da
    CRA e do ONR.

    **E ele não se lê do acervo.** O par que esta casa usou nas medições veio
    de `tbCNIB_Propriedades` (colunas `Cliente_ID` e `Secret_Code`), que é
    acervo morto do E-Ofício: serve para saber **qual é** o par, e não para
    continuar lendo de lá. Quem guarda hoje é `centrais_cred`, no
    `%PROGRAMDATA%`.
    """
    return CRED.credencial(CRED.CNIB, ambiente or ambiente_da_casa(), pasta)


# O TOKEN VIVE NA MEMÓRIA DO PROCESSO, por ambiente. Reiniciar o servidor o
# perde, e isso é certo: ele se pede de novo em milissegundos.
_TOKENS: dict[str, dict] = {}


def esquecer_o_token(ambiente: Any = None) -> None:
    """Joga fora o token guardado. A tela chama isto ao trocar a credencial.

    **Sem esta linha o conserto não pega**: quem corrigisse o `client_secret`
    continuaria falando pelo token velho — que dura uma hora — e concluiria
    que a correção não funcionou. É a mesma armadilha medida no ONR.
    """
    if ambiente is None:
        _TOKENS.clear()
    else:
        _TOKENS.pop(CRED._ambiente(ambiente), None)


def token(ambiente: Any = None, *, pasta=None, agora: float | None = None) -> str:
    """O token de acesso, pedido ao CNIB e guardado até perto de vencer.

    **`expires_in` vem na resposta** — 3.600, medido —, e é ele que manda:
    pedir token novo a cada chamada seria uma viagem a mais em cada leitura, e
    guardá-lo para sempre faria a casa mandar token vencido depois da primeira
    hora.
    """
    onde = CRED._ambiente(ambiente or ambiente_da_casa())
    quando = time.time() if agora is None else agora
    guardado = _TOKENS.get(onde)
    if guardado and guardado["vence_em"] - MARGEM_DO_TOKEN > quando:
        return guardado["token"]

    ident, segredo = credencial(onde, pasta=pasta)
    corpo = urllib.parse.urlencode({
        "client_id": ident, "client_secret": segredo,
        "grant_type": GRANT_DA_CASA, "scope": ESCOPO}).encode("utf-8")
    # **`url_absoluta=True`, E ELE FALTAVA — 20/09/2026.** Relato do oficial ao
    # tentar a primeira leitura de verdade: «fui tentar baixar a 09/2026 da
    # cnib e deu: A base do CNIB tem de ser https, e veio «»».
    #
    #   `AUTENTICACAO` é um endereço INTEIRO, de OUTRO host — o provedor de
    #   identidade, e não a API. Sem esta palavra, `_bater_cru` caía no ramo
    #   relativo e chamava `partes(base or "")` com a base vazia: **nenhum
    #   token jamais saiu daqui**, e com ele nenhuma leitura da Central.
    #
    #   O PARÂMETRO EXISTIA, DOCUMENTADO, PARA ESTA ÚNICA CHAMADA — e nenhuma
    #   chamada o passava. É o defeito mais repetido deste projeto, na forma
    #   mais difícil de ver: não é função sem chamador, é **argumento sem quem
    #   o passe**, e por isso varredor nenhum o acusa.
    #
    #   E OS 35 TESTES PASSAVAM: eles trocam `token` justamente para a primeira
    #   chamada não sair pela rede, de modo que o único caminho que a troca
    #   escondia era o que estava quebrado. Agora há teste que o exercita sem
    #   rede — ver `test_o_token_vai_para_o_host_do_provedor_de_identidade`.
    r = _bater_cru("POST", AUTENTICACAO, corpo=corpo, tipo=TIPO_DO_FORMULARIO,
                   url_absoluta=True)
    if r["status"] not in (200, 201):
        raise CnibError(
            f"O CNIB recusou a credencial da serventia (HTTP {r['status']}): "
            f"{_detalhe(r) or 'sem explicação'}. Confira o client_id e o "
            f"client secret em Administrativo → Configurações, na seção "
            f"«Centrais — credenciais das APIs».")
    dados = r["json"] if isinstance(r["json"], dict) else {}
    # **A FORMA MEDIDA É PLANA** — `{access_token, expires_in, token_type}`,
    # sem embrulho. A tolerância ao `data` fica porque é o que o transporte
    # irmão (`onr_api.token`) faz com o mesmo provedor de identidade, e custa
    # três linhas; **não é invenção: é o que se aceita a mais.**
    if "access_token" not in dados and isinstance(dados.get("data"), dict):
        dados = dados["data"]
    novo = _texto(dados.get("access_token"))
    if not novo:
        # SÓ OS NOMES DOS CAMPOS, NUNCA O CORPO (LX14; M11 do LS03). Os 200
        # caracteres do corpo iam para a mensagem e dela para a auditoria, e
        # uma resposta de autenticação pode trazer o `refresh_token`, o
        # `id_token` ou o eco do `client_secret`. O nome do campo basta para
        # saber o que veio no lugar do token.
        campos = ", ".join(sorted(str(k) for k in dados)) if dados else ""
        raise CnibError(
            "O CNIB respondeu à autenticação sem `access_token`. "
            + (f"Vieram os campos: {campos}." if campos else
               f"A resposta não era JSON (HTTP {r.get('status')}, "
               f"{len(_texto(r.get('texto')))} caracteres)."))
    try:
        dura = int(dados.get("expires_in") or 0)
    except (TypeError, ValueError):
        dura = 0
    # **SEM `expires_in` NÃO SE GUARDA.** Guardar «para sempre» faria a casa
    # mandar token vencido sem saber; pedir de novo custa uma viagem.
    if dura > 0:
        _TOKENS[onde] = {"token": novo, "vence_em": quando + dura}
    else:
        _TOKENS.pop(onde, None)
    return novo


# ------------------------------------------------------------ o transporte


def partes(base: str) -> tuple[str, int, str]:
    """Parte o endereço, **forçando https**.

    Aqui viaja o `client_secret` e viaja o que a serventia publica sobre os
    bens de alguém. Forçar o transporte é decisão da casa desde o selador, e a
    razão é sempre a mesma: **quando a rede é o meio, quem decide o transporte
    é a casa** — e não o arquivo de configuração de quem publica o contrato
    (foi assim que o WSDL de homologação da CRA declarou `http://`).
    """
    p = urllib.parse.urlsplit(base)
    if p.scheme != "https":
        raise CnibError(f"A base do CNIB tem de ser https, e veio «{base}».")
    return p.hostname or "", p.port or 443, (p.path or "").rstrip("/")


def _bater_cru(metodo: str, caminho: str, *, base: str | None = None,
               corpo: bytes | None = None, tipo: str = TIPO_DO_JSON,
               cabecas: dict | None = None, prazo: int = PRAZO_PADRAO,
               url_absoluta: bool = False) -> dict:
    """Uma requisição. Devolve `{status, json, texto}` — nunca estoura por 4xx.

    `url_absoluta` existe para o endereço do token, que é **outro host** (o
    provedor de identidade), e não o da API. É a diferença que o `onr_api` não
    tem: lá o token sai do mesmo host do resto.

    Transporte via `centrais_http` (marco a). **Retentativa alinhada à base
    comum:** só `GET`/`HEAD`/`OPTIONS` retentam. O laço antigo retentava
    qualquer método; ao migrar, não se inventa retentativa de escrita (o POST
    do token, em particular, não se repete sozinho).

    `Accept-Encoding: identity` continua pedido — `centrais_http` não
    descomprime gzip; o pedido de identidade evita corpo comprimido (nos 26
    brutos medidos, nenhum veio gzip). Gunzip mínimo do adaptador antigo
    não foi refeito aqui de propósito.
    """
    if url_absoluta:
        hospedeiro, porta, _prefixo = partes(caminho)
        url = caminho  # URL completa (token em outro host)
        rotulo = hospedeiro
    else:
        hospedeiro, porta, prefixo = partes(base or "")
        autoridade = hospedeiro if porta == 443 else f"{hospedeiro}:{porta}"
        url = f"https://{autoridade}{prefixo}{caminho}"
        rotulo = hospedeiro
    cabecalhos = {
        "Accept": TIPO_DO_JSON,
        "Accept-Encoding": "identity",
    }
    cabecalhos.update(cabecas or {})
    if corpo is not None:
        cabecalhos["Content-Type"] = tipo
    verbo = str(metodo or "GET").strip().upper()
    # Alinhado à base comum: só leitura retenta (divergência documentada
    # vs. o laço antigo que retentava qualquer método).
    e_leitura = verbo in HTTP.METODOS_QUE_SO_LEEM
    try:
        return HTTP.requisitar(
            verbo, url, corpo=corpo, cabecalhos=cabecalhos,
            prazo=prazo,
            tentativas=TENTATIVAS_DE_REDE if e_leitura else 0,
            retentar_escrita=False,
            user_agent=HTTP.USER_AGENT_PADRAO,
        ).como_dict()
    except HTTP.CentralHttpError as erro:
        raise CnibError(
            f"Não consegui falar com o CNIB em {rotulo}: "
            f"{erro.causa or erro}. Confira a internet da serventia e tente "
            f"de novo."
        ) from None


def _detalhe(r: dict) -> str:
    """A frase da Central, se ela mandou uma."""
    corpo = r.get("json")
    if isinstance(corpo, dict):
        for chave in ("message", "mensagem", "descricao", "error"):
            if corpo.get(chave):
                return _texto(corpo[chave])[:600]
        # **A FORMA VAZIA EMBRULHA DUAS VEZES** — a frase está em `data.message`.
        dentro = corpo.get("data")
        if isinstance(dentro, dict) and dentro.get("message"):
            return _texto(dentro["message"])[:600]
    return _texto(r.get("texto"))[:400]


def _resposta_ou_erro(r: dict, o_que: str) -> Any:
    """Traduz o código da Central numa resposta ou numa frase de balcão."""
    if r["status"] in (200, 201, 202, 204):
        return r["json"] if r["json"] is not None else r["texto"]
    if r["status"] in (401, 403):
        raise CnibError(
            f"O CNIB recusou a credencial ao {o_que}. O token pode ter vencido "
            f"ou a credencial ter mudado: confira em Administrativo → "
            f"Configurações, na seção «Centrais — credenciais das APIs».")
    if r["status"] == 400:
        # **400 É A RECUSA QUE DIZ O QUE ESTÁ ERRADO**, e é a que mais aparece
        # numa integração nova: campo obrigatório que faltou. Vai inteira.
        raise CnibRecusou(f"O CNIB recusou os dados ao {o_que}: {_detalhe(r)}")
    if r["status"] in (404, 422):
        raise CnibRecusou(f"O CNIB não atendeu o {o_que}: {_detalhe(r)}")
    raise CnibRecusou(
        f"O CNIB respondeu {r['status']} ao {o_que}: {_detalhe(r)}")


def _bater(qual: str, *, corpo: dict | None = None, ambiente: Any = None,
           prazo: int = PRAZO_PADRAO, pasta=None) -> dict:
    """Uma requisição autenticada. Recusa caminho que este módulo não liga."""
    if qual not in CAMINHOS_LIGADOS:
        raise CnibError(
            f"O caminho «{qual}» está medido e não está ligado — ver o "
            f"cabeçalho de `cnib_api`.")
    onde = CRED._ambiente(ambiente or ambiente_da_casa())
    cabecas = {CABECALHO_DO_TOKEN: PREFIXO_DO_TOKEN + token(onde, pasta=pasta)}
    bruto = (json.dumps(corpo, ensure_ascii=False).encode("utf-8")
             if corpo is not None else None)
    return _bater_cru(METODO_DO_CAMINHO[qual], CAMINHO[qual],
                      base=base_do_ambiente(onde), corpo=bruto, prazo=prazo,
                      cabecas=cabecas)


# ------------------------------------------------------ a leitura da resposta


def ordens_da_resposta(resposta: Any) -> list[dict]:
    """As ordens de dentro, **nas três formas que a Central usa**.

    Medido nos 26 brutos: a normal traz `data.ordens`, a vazia traz
    `data.data.orders`, e a da consulta por documento não traz ordens — traz
    `data.protocolos`, que é outra pergunta.

    **Não se inventa uma quarta forma.** O que não casar com estas três volta
    como lista vazia, e quem chamou tem como saber que não casou — ver
    `forma_da_resposta`.
    """
    if not isinstance(resposta, dict):
        return []
    dado = resposta.get("data")
    if not isinstance(dado, dict):
        return []
    for chave in ("ordens", "orders"):
        if isinstance(dado.get(chave), list):
            return dado[chave]
    fundo = dado.get("data")
    if isinstance(fundo, dict):
        for chave in ("ordens", "orders"):
            if isinstance(fundo.get(chave), list):
                return fundo[chave]
    return []


def paginacao_da_resposta(resposta: Any) -> dict:
    """O `paginacao` de dentro, com os nomes **dela** — ver `PAGINACAO_REAL`."""
    if not isinstance(resposta, dict):
        return {}
    dado = resposta.get("data")
    if not isinstance(dado, dict):
        return {}
    p = dado.get("paginacao")
    return p if isinstance(p, dict) else {}


def forma_da_resposta(resposta: Any) -> str:
    """Qual das três formas veio: `ordens`, `vazia`, `documento` ou `outra`.

    **Serve para a tela poder dizer o que aconteceu sem adivinhar** — e para o
    teste que guarda as três formas ficar vermelho no dia em que a Central
    inventar a quarta.
    """
    if not isinstance(resposta, dict):
        return "outra"
    dado = resposta.get("data")
    if not isinstance(dado, dict):
        return "outra"
    if isinstance(dado.get("ordens"), list):
        return "ordens"
    if isinstance(dado.get("protocolos"), list):
        return "documento"
    fundo = dado.get("data")
    if isinstance(fundo, dict) and isinstance(fundo.get("orders"), list):
        return "vazia"
    return "outra"


def mensagem_da_resposta(resposta: Any) -> str:
    """A frase da Central. **É ela que diz «não há ordens», e não o zero.**"""
    if not isinstance(resposta, dict):
        return ""
    dado = resposta.get("data")
    if isinstance(dado, dict):
        if dado.get("message"):
            return _texto(dado["message"])
        fundo = dado.get("data")
        if isinstance(fundo, dict) and fundo.get("message"):
            return _texto(fundo["message"])
    return ""


# ================================================================ as leituras


def _corpo_da_janela(de: str, ate: str, *, cpf_usuario: str,
                     visualizadas: bool, pagina: int,
                     tamanho: int) -> dict:
    """O corpo do pedido, **na forma exata que a casa já usou nove vezes**.

    Os quatro obrigatórios do contrato estão todos aqui: `cpf_usuario`,
    `pagina_inicial`, `proxima_pagina` e `tamanho_pagina`. `data_inicial` e
    `data_final` são **opcionais para o contrato** — e é justamente por isso
    que uma requisição sem eles devolve a fila inteira: a casa sempre os manda.

    **`proxima_pagina` vai `False` sempre, e isso é medido, não descuido.** O
    laço desta casa anda por `pagina_inicial` e para em `tem_proxima_pagina` —
    que é o booleano **da resposta**. Nenhuma das medições usou o
    `proxima_pagina` do pedido com `true`, e mandar `true` sem saber o que a
    Central faz com ele seria inventar. Ele vai presente e falso, que é o que
    funcionou.
    """
    return {
        "cpf_usuario": cpf_usuario,
        "ordens_visualizadas": bool(visualizadas),
        "data_inicial": de,
        "data_final": ate,
        "pagina_inicial": int(pagina),
        "tamanho_pagina": int(tamanho),
        "proxima_pagina": False,
    }


def uma_pagina(de: str, ate: str, *, cpf_usuario: str,
               visualizadas: bool = True, pagina: int = 1,
               tamanho: int = TAMANHO_DA_PAGINA, ambiente: Any = None,
               pasta=None) -> dict:
    """**Uma** página da janela, crua. É o tijolo do `ordens_na_janela`.

    Devolve `{ordens, paginacao, forma, mensagem, status}` — sem interpretar
    nada. Quem quiser só conferir a ligação usa esta, com `tamanho=1`: assim o
    teste de conexão **não puxa quinhentas ordens** para dizer que está de pé.
    """
    if not cpf_usuario:
        raise CnibError(
            "O CNIB exige o CPF de quem consulta (`cpf_usuario`): é por ele "
            "que a Central registra quem pediu a lista. Informe em "
            "Administrativo → Configurações, na seção do CNIB.")
    corpo = _corpo_da_janela(de, ate, cpf_usuario=cpf_usuario,
                             visualizadas=visualizadas, pagina=pagina,
                             tamanho=tamanho)
    r = _bater("visualizar_v2", corpo=corpo, ambiente=ambiente, pasta=pasta)
    resposta = _resposta_ou_erro(
        r, f"consultar as ordens de {de} a {ate}"
           + (" (sem consumir a fila)" if visualizadas else " (CONSUMINDO a fila)"))
    return {
        "ordens": ordens_da_resposta(resposta),
        "paginacao": paginacao_da_resposta(resposta),
        "forma": forma_da_resposta(resposta),
        "mensagem": mensagem_da_resposta(resposta),
        "status": r["status"],
    }


def ordens_na_janela(de: str, ate: str, *, cpf_usuario: str,
                     visualizadas: bool = True,
                     tamanho: int = TAMANHO_DA_PAGINA,
                     maximo_de_paginas: int = MAXIMO_DE_PAGINAS,
                     ambiente: Any = None, pasta=None) -> dict:
    """Todas as ordens da janela, andando de página até a Central dizer que parou.

    Devolve:

    | campo | o que é |
    |---|---|
    | `ordens` | a lista inteira, na ordem em que veio |
    | `lidas` | quantas vieram — **e não quantas distintas** |
    | `total` | o `total_ordens_encontradas` da **primeira** página, ou `None` |
    | `paginas` | quantas páginas foram pedidas |
    | `forma` | `ordens`, `vazia` ou `outra` — a da **primeira** página |
    | `mensagem` | a frase da Central, quando ela mandou uma |
    | `vazio` | `True` quando a Central respondeu a forma vazia |
    | `forma_estranha` | `True` quando a resposta **não é nenhuma das três medidas** |
    | `parou_no_teto` | `True` quando as páginas acabaram no freio, e não na Central |

    **`lidas` não é `distintas`.** Numa varredura de 3.000 ordens vieram 2.996
    distintas: quatro repetiram entre páginas. Quem grava faz UPSERT pela
    chave, e não confia em página como se fosse lote.

    **E `vazio=True` NÃO QUER DIZER «não existem ordens».** Medido em
    18/09/2026: a mesma resposta vazia, com a mesma frase, veio para dias que
    tinham ordens — e horas depois as ordens apareceram. O dado **não
    distingue** «não há» de «ainda não me chegou». É por isso que este campo
    existe com este nome, e não `sem_ordens`: quem decide é o atualizador,
    com janela sobreposta. **Não se confia num zero da Central.**

    **`vazio` E `forma_estranha` SÃO COISAS OPOSTAS, E CONFUNDI-LAS É O PIOR
    DEFEITO QUE ESTE MÓDULO PODERIA TER.** `vazio` é a Central dizendo «não há
    nada nesta janela agora»; `forma_estranha` é **eu** não ter entendido a
    resposta. Os dois devolvem `lidas == 0`, e um atualizador que olhasse só o
    número concluiria «nada mudou» nos dois casos — no segundo, sobre uma
    resposta que ele não sabe ler. Quem grava tem de **recusar** quando
    `forma_estranha` for `True`, e dizer que não entendeu.
    """
    pagina = 1
    todas: list[dict] = []
    primeira: dict = {}
    total_lido: Any = None
    paginas = 0
    parou_no_teto = False

    while True:
        p = uma_pagina(de, ate, cpf_usuario=cpf_usuario,
                       visualizadas=visualizadas, pagina=pagina,
                       tamanho=tamanho, ambiente=ambiente, pasta=pasta)
        if paginas == 0:
            primeira = p
            total_lido = p["paginacao"].get("total_ordens_encontradas")
        paginas += 1
        todas.extend(p["ordens"])

        # **O LAÇO PARA EM `tem_proxima_pagina`, QUE É DA RESPOSTA.** O
        # `proxima_pagina` do pedido nunca foi usado com `true` pela casa, e
        # não é ele que diz se há mais.
        #
        # **E a página estranha para o laço no mesmo passo**: sem isto, uma
        # resposta que não se entende faria o `tem_proxima_pagina` ausente ser
        # lido como «não há mais» — que é a conclusão certa por acidente, e
        # não por leitura.
        if p["forma"] == "outra":
            break
        if not p["paginacao"].get("tem_proxima_pagina"):
            break
        if paginas >= maximo_de_paginas:
            parou_no_teto = True
            break
        pagina += 1

    return {
        "ordens": todas,
        "lidas": len(todas),
        "total": total_lido,
        "paginas": paginas,
        "forma": primeira.get("forma", "outra"),
        "mensagem": primeira.get("mensagem", ""),
        "vazio": primeira.get("forma") == "vazia" and not todas,
        "forma_estranha": primeira.get("forma") == "outra",
        "parou_no_teto": parou_no_teto,
    }


def consultar_por_documento(documento: str, *, cpf_usuario: str,
                            ambiente: Any = None, pasta=None) -> dict:
    """A outra pergunta: **o que pesa sobre este documento, agora.**

    É a leitura que o balcão usa quando o cliente está na frente — e ela é
    **diferente** da janela em três coisas, todas medidas:

    1. o caminho é outro (`/api/ordem/consultar`, e não o `visualizar`);
    2. a resposta é outra forma — `data.documento`, `data.nomeRazao`,
       `data.indisponivel`, `data.qtdOrdens` e `data.protocolos` —, e **não
       tem lista de ordens**;
    3. ela **não tem janela de data**: é o retrato de agora.

    **Aqui o zero é resposta**, e é o oposto da janela: `indisponivel: false` na
    consulta direta de um documento é a Central afirmando que não há ordem
    sobre ele. O que se recusa a confiar, na janela, é o zero **por período**
    — que pode ser defasagem. São dois zeros diferentes, e o nome do campo diz
    qual dos dois se está lendo.
    """
    if not documento:
        raise CnibError("Informe o documento para consultar o CNIB.")
    corpo = {"cpf_usuario": cpf_usuario, "documento": documento}
    r = _bater("consultar", corpo=corpo, ambiente=ambiente, pasta=pasta)
    resposta = _resposta_ou_erro(r, f"consultar o documento {documento}")
    dado = resposta.get("data") if isinstance(resposta, dict) else None
    if not isinstance(dado, dict):
        dado = {}
    return {
        "documento": _texto(dado.get("documento")) or documento,
        "nome": _texto(dado.get("nomeRazao")),
        "indisponivel": bool(dado.get("indisponivel")),
        "quantas": dado.get("qtdOrdens"),
        "protocolos": dado.get("protocolos") or [],
        "forma": forma_da_resposta(resposta),
    }


# --------------------------------------------------------------- os rótulos
#
# O `ordemstatus` VEM COM TRÊS GRAFIAS DO MESMO ESTADO, e isso foi medido em
# 6.218 ordens, uma a uma: `CONCLUÍDO` em 6.213, `Concluído` em 2 e
# `Cancelamento total - Concluido` em 3 — e as três aparecem em ordens de
# cancelamento (2.647, 2 e 3 delas). **Não se corrige o dado da Central**:
# guarda-se como veio, e a régua abaixo é só para COMPARAR.
#
# **E A RÉGUA ESTAVA ERRADA, nesta mesma passada.** Eu havia escrito
# `startswith("concluido")`, com o comentário afirmando que as três grafias
# eram o mesmo estado — e a terceira **não começa** com a palavra: as três
# ordens com `Cancelamento total - Concluido` seriam lidas como **não
# concluídas**, contra o que o próprio comentário dizia. Quem apontou foi o
# teste que transcreve as três, e não a releitura.
#
# **A régua certa é o vocabulário medido, e não um pedaço da palavra.** A
# tentação é `endswith`, e ela tem uma armadilha pior: `NÃO CONCLUÍDO`
# normalizado é `nao concluido`, que **termina** com a palavra e passaria como
# concluída. Igualdade contra o que se mediu; o que estiver fora **não se
# adivinha** — é a régua da palavra fora do vocabulário, que a lista de
# problemas já paga desde 17/09/2026.
#
# **E ESTA FUNÇÃO NÃO É PORTÃO.** Ela rotula o que veio; não decide se a ordem
# entra no banco. Ordem com palavra que a casa não conhece **se guarda do
# mesmo jeito**, com o texto como veio — quem for ler a ficha meses depois
# precisa poder ver o que a Central escreveu.
def sem_acento(v: Any) -> str:
    """A forma comparável: minúscula, sem acento. **Não se grava isto.**"""
    t = unicodedata.normalize("NFKD", _texto(v).lower())
    return "".join(c for c in t if not unicodedata.combining(c))


CONCLUIDO = "concluido"

# As grafias que a casa MEDIU. Palavra nova que a Central inventar fica fora —
# e fica fora **de propósito**: entrar aqui por semelhança faria o sistema
# tratar como terminado o que ninguém conferiu.
GRAFIAS_DE_CONCLUIDA: frozenset[str] = frozenset({
    CONCLUIDO,                          # CONCLUÍDO — 6.213
    "cancelamento total - concluido",   # Cancelamento total - Concluido — 3
})


def e_concluida(ordem: dict) -> bool:
    """A ordem está terminada, **em qualquer das grafias medidas** — ver acima."""
    return sem_acento(ordem.get("ordemstatus")) in GRAFIAS_DE_CONCLUIDA


def e_cancelamento(ordem: dict) -> bool:
    """Esta ordem **desfaz** outra, em vez de pedir indisponibilidade."""
    return sem_acento(ordem.get("status")) == "cancelamento"


def protocolo_da_ordem(ordem: dict) -> str:
    """A chave da ordem. **É esta que casa com a que o cancelamento cita.**"""
    return _texto(ordem.get("protocoloindisponibilidade"))


def protocolo_cancelado(ordem: dict) -> str:
    """**Qual ordem esta linha cancela.**

    É a peça que faz o atualizador conseguir desativar sem adivinhar: na linha
    de `CANCELAMENTO`, `protocoloindisponibilidade` **é o da ordem cancelada** e
    `cancelamentodeindisponibilidade` é o protocolo do próprio cancelamento.
    Medido cruzando as duas contra o espelho — a ponte é exata.

    Devolve `""` quando a linha não é cancelamento: **perguntar qual é o alvo
    de quem não cancela nada não tem resposta**, e devolver a própria chave ali
    faria o atualizador desativar a ordem errada.
    """
    if not e_cancelamento(ordem):
        return ""
    return _texto(ordem.get("protocoloindisponibilidade"))


def protocolo_do_cancelamento(ordem: dict) -> str:
    """O protocolo do ato de cancelar, para guardar no lugar dele."""
    return _texto(ordem.get("cancelamentodeindisponibilidade"))
