"""A API DA CENPROT NACIONAL — o transporte, e só ele.

Ordem do oficial em 02/09/2026: *«vamos integrar a api da cra21»* e, no mesmo
dia, *«também juntei a errata com a API da cenprot, pra complementar»*.

**O CONTRATO É O `swagger.yaml`, E NÃO O PDF — e a diferença é de dois anos.**
O comunicado que o oficial trouxe aponta para um manual em PDF na **versão
1.0, de 29/02/2024**, com cinco caminhos. A especificação viva, baixada em
02/09/2026 de
`https://wspub.cenprotnacional.org.br/ieptb-cenprot-api-cartorio/swagger.yaml`,
é **OpenAPI 3.0 na versão 2.1.0**, com **21 caminhos** — e traz coisas que o
PDF não menciona: cancelamento, decisão judicial, renegociações, custas e
endereço. Construir pelo PDF seria construir contra um contrato de dois anos
atrás. Os dois ficam em `FONTES_EXTERNAS/cra21/`, e o que manda é o YAML.

**ESTE MÓDULO NÃO DECIDE NADA, E NÃO LAVRA NADA.** Ele fala com a Central: pega
token, baixa pendência, manda o que lhe derem para mandar. Quem aprova uma
anuência, quem orça uma certidão e quem cancela um protesto é o módulo de
domínio e, no fim, o oficial — é a regra do CNIB («avisar e preparar, ficando
pendente o okay») e a da IA auxiliar, pela terceira vez neste projeto.

**E O QUE SAI DAQUI SAI PORQUE ALGUÉM MANDOU.** Os `GET` só leem; os `POST`
**escrevem na Central**: aprovam anuência, orçam certidão, cancelam protesto.
Nenhum deles é chamado por relógio, por passada automática ou por efeito
colateral de tela de consulta. Quem os chama é uma rota que o operador clicou.

**A VALIDAÇÃO DE TLS AQUI É A NORMAL, e é o CONTRÁRIO do selador.** Lá o
certificado se **fixa**, porque o aparelho é da rede local, veio de fábrica e
está vencido desde 10/11/2025 — fixar é dizer «é esta máquina, eu conferi».
Aqui é serviço público nacional com certificado de autoridade: medido em
02/09/2026, a cadeia valida sozinha (CN `api.cenprotnacional.org.br`, válido
até **04/11/2026**). **Fixar aqui seria pior**: no dia em que a CENPROT
renovar — e ela renova em novembro — o sistema pararia de falar com a Central
sem que nada tivesse acontecido de errado.

**A CREDENCIAL VEM DE `centrais_cred`, e não do banco.** O banco viaja no
backup, e o backup já saiu da serventia.

**E O TOKEN NÃO SE GRAVA EM LUGAR NENHUM.** Ele é JWT, vale por um tempo e
vale para esta máquina; guardá-lo em disco ou no banco seria criar um segundo
segredo para vazar, com a validade correndo. Fica na memória do processo, e o
processo morre com ele.

**A CHAMADA NUNCA ACONTECE DENTRO DE `db.transaction()`.** É a regra que existe
desde o selador: um `BEGIN IMMEDIATE` segurado por trinta segundos de rede põe
todo outro balcão no `busy_timeout`. Por isso nenhuma função daqui recebe
`con`.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
from typing import Any

import centrais_cred as CRED
import centrais_http as HTTP
import centrais_log as LOG

# AS DUAS BASES, medidas na seção `servers` do `swagger.yaml`.
#
# **A DE HOMOLOGAÇÃO TEM A BARRA NO FIM NO CONTRATO**, e ela é retirada aqui:
# juntar `.../cartorio-homolog/` com `/token` daria `//token`, e barra dobrada
# é o tipo de erro que devolve 404 sem dizer por quê.
BASE_DO_AMBIENTE: dict[str, str] = {
    CRED.PRODUCAO:
        "https://wspub.cenprotnacional.org.br/ieptb-cenprot-api-cartorio",
    CRED.HOMOLOGACAO:
        "https://wspub.cenprotnacional.org.br/ieptb-cenprot-api-cartorio-homolog",
}

# OS CAMINHOS. Os `v2` são os recomendados pelo próprio contrato — eles paginam
# (1.000 por página) e aceitam lote. Os antigos ficam **declarados** porque a
# Central ainda os serve, e porque saber que existem é o que impede alguém de
# os reinventar achando que sumiram.
CAMINHO: dict[str, str] = {
    "token": "/token",
    # --- anuências
    "anuencias": "/v2/anuencias",
    "anuencias_legado": "/anuencias",
    "anuencia_processar": "/v2/anuencia/processar",
    "anuencia_processar_legado": "/anuencia/processar",
    "anuencia_arquivos": "/anuencia/arquivos",
    # --- certidões
    "certidoes": "/v2/certidoes",
    "certidoes_legado": "/certidoes",
    "certidao_processar": "/v2/certidao/processar",
    "certidao_processar_legado": "/certidao/processar",
    # --- cancelamento
    "cancelamento_pedidos": "/cancelamento/pedidos",
    "cancelar_protesto": "/cancelamento/cancelar-protesto",
    # --- os que a versão 2.1.0 trouxe e o PDF não conhece
    "renegociacoes": "/renegociacoes",
    "renegociacoes_processar": "/renegociacoes/processar",
    "decisao_judicial": "/decisao-judicial/pendentes",
    "decisao_judicial_processar": "/decisao-judicial/processar/{nm_chave}",
    "pedidos_consulta": "/pedidos/consulta",
    "pedidos_protocolar": "/pedidos/protocolar",
    "endereco_consultar": "/base-endereco",
    "custas_arquivo": "/custas/arquivo",
}

# OS CAMINHOS QUE ESCREVEM NA CENTRAL. Estão nomeados de propósito: há teste
# que exige que toda função que os use passe por `_escrever`, e que `_escrever`
# nunca seja chamado por passada automática.
CAMINHOS_QUE_ESCREVEM: frozenset[str] = frozenset({
    "anuencia_processar", "anuencia_processar_legado",
    "certidao_processar", "certidao_processar_legado",
    "cancelar_protesto", "renegociacoes_processar",
    "decisao_judicial_processar", "pedidos_protocolar",
    "endereco_consultar", "custas_arquivo",
})

# QUANTOS PEDIDOS CABEM NUM PROTOCOLAR, e o número é do contrato: «Limite
# máximo: **50 itens por requisição**». Os `processar` aceitam 1.000; este,
# 50 — **e o teto não é o mesmo em toda a API**, o que é mais um jeito de o
# mesmo engano sair calado.
LIMITE_DO_LOTE_PROTOCOLAR = 50

# O TAMANHO DA CHAVE ÚNICA, declarado `minLength: 23, maxLength: 23`. Bate com
# a chave que este projeto mediu em 175 de 175 arquivos desta casa —
# `2198765 · 01412433 · 01 · 260417`, que são IBGE(7) + CENPROT(8) +
# cartório(2) + data AAMMDD(6) = **23 dígitos**.
#
# **E O EXEMPLO DO PRÓPRIO CONTRATO NÃO OBEDECE À RESTRIÇÃO DELE**:
# `SP12345678900000000000123` tem **25** caracteres e começa com letras. É o
# segundo erro de digitação do arquivo (o outro é o `'base64_arquivo  '` das
# custas). **Vale a restrição, que bate com o dado real** — não o exemplo.
DIGITOS_DA_CHAVE_UNICA = 23

PRAZO_PADRAO = 60          # segundos; a Central pagina 1.000 por vez
PRAZO_DO_TOKEN = 30
TENTATIVAS_DE_REDE = 2
TIPO_DO_FORMULARIO = "application/x-www-form-urlencoded"

# QUANTO O TOKEN VALE PARA ESTE PROCESSO.
#
# **O contrato não diz a validade** — ele devolve `access_token` e mais nada. O
# JWT a carrega dentro, mas ler o miolo de um token para decidir quando ele
# vence é confiar num campo que ninguém prometeu. Aqui se guarda por um tempo
# curto e conservador, e **o 401 é tratado renovando uma vez**: quem manda na
# validade é a Central, e não a nossa conta.
SEGUNDOS_DO_TOKEN = 10 * 60

# O NOME DESTA CENTRAL NO LOG E NA FILA COMUNS (`centrais_log`/`centrais_fila`)
# — o mesmo de `centrais_cred`, para o painel juntar credencial, fila e log.
CENTRAL_NO_LOG = CRED.CENPROT


class CenprotError(RuntimeError):
    """Falha de transporte ou de credencial, com a frase para o balcão."""


class CenprotRecusou(CenprotError):
    """A Central respondeu, e respondeu não. O motivo dela vem junto."""


def base_do_ambiente(ambiente: Any) -> str:
    """A base daquele ambiente. Só calcula."""
    nome = str(ambiente or "").strip().upper()
    return BASE_DO_AMBIENTE.get(nome, BASE_DO_AMBIENTE[CRED.HOMOLOGACAO])


def _partes(base: str) -> tuple[str, int, str]:
    p = urllib.parse.urlsplit(base)
    if p.scheme != "https":
        # **HTTPS NÃO É OPCIONAL AQUI.** A credencial e o token viajam nesta
        # conexão; em texto puro, quem estiver na rede os lê.
        raise CenprotError(
            f"A base da CENPROT tem de ser https, e veio «{base}».")
    return p.hostname or "", p.port or 443, (p.path or "").rstrip("/")


# ---------------------------------------------------------------- o token
#
# UM POR PROCESSO, na memória, com trava. O waitress atende em várias linhas de
# execução; sem a trava, duas telas ao mesmo tempo pediriam dois tokens e a
# Central veria duas autenticações para nada.

_TOKENS: dict[str, tuple[str, float]] = {}
_TRAVA = threading.Lock()


def esquecer_token(ambiente: Any = None) -> None:
    """Joga fora o token guardado. Usado quando a Central devolve 401."""
    with _TRAVA:
        if ambiente is None:
            _TOKENS.clear()
        else:
            _TOKENS.pop(str(ambiente or "").strip().upper(), None)


def _pedir_token(ambiente: str, *, pasta=None) -> str:
    """Autentica e devolve o JWT. É o único lugar que usa a senha."""
    usuario, senha = CRED.credencial(CRED.CENPROT, ambiente, pasta)
    # O contrato exige `application/x-www-form-urlencoded` com `usuario` e
    # `senha` — não JSON, e não `client_id`/`client_secret` do ONR. Mandar de
    # outro jeito devolve 400 `credencial_ausente` com a credencial no disco.
    corpo = urllib.parse.urlencode(
        {"usuario": usuario, "senha": senha}).encode("utf-8")
    resposta = _bater(
        ambiente, "POST", CAMINHO["token"],
        corpo=corpo,
        cabecalhos={"Content-Type": TIPO_DO_FORMULARIO},
        prazo=PRAZO_DO_TOKEN, com_token=False)
    if resposta["status"] == 401:
        raise CenprotError(
            "A CENPROT recusou a credencial. Confira o usuário e a senha em "
            "Administrativo → Configurações → Centrais de Protesto; o usuário "
            "é o número do cartório com o código IBGE, e a senha é a que você "
            "cadastrou em Cadastro → Cadastro do Cartório.")
    if resposta["status"] == 400:
        detalhe = str(resposta.get("texto") or "")
        if isinstance(resposta["json"], dict):
            detalhe = str(resposta["json"].get("message")
                          or resposta["json"].get("erro")
                          or resposta["json"].get("error")
                          or detalhe)
        if "credencial_ausente" in detalhe:
            raise CenprotError(
                "A CENPROT recusou o pedido de token porque o usuário e a senha "
                "não chegaram no formulário que ela espera (campos «usuario» e "
                "«senha»). Confira em Administrativo → Configurações → Centrais "
                "de Protesto; se o sistema acabou de ser atualizado, teste a "
                "conexão de novo.")
    dados = resposta["json"] or {}
    # O CONTRATO DIZ `access_token`, E A PRODUÇÃO DEVOLVE `token` — medido em
    # 13/10/2026: `{"token": "…", "message": "Sucesso"}`, HTTP 200, com a
    # credencial certa. Lendo só o nome do contrato, a autenticação que deu
    # certo virava «sem devolver o token». Os dois nomes valem.
    token = str(dados.get("access_token") or dados.get("token") or "").strip()
    if not token:
        # A resposta NÃO vai na mensagem: ela vai para a tela e para o log, e
        # foi assim que um token de produção apareceu escrito (13/10/2026).
        chaves = ", ".join(sorted(dados)) if isinstance(dados, dict) else "nenhuma"
        raise CenprotError(
            f"A CENPROT respondeu {resposta['status']} sem devolver o token "
            f"(campos da resposta: {chaves}).")
    return token


def token(ambiente: Any = CRED.HOMOLOGACAO, *, pasta=None,
          renovar: bool = False) -> str:
    """O token deste processo, pedindo um novo quando preciso. Só LÊ disco."""
    qual = str(ambiente or "").strip().upper() or CRED.HOMOLOGACAO
    agora = time.time()
    with _TRAVA:
        guardado = _TOKENS.get(qual)
        if guardado and not renovar and guardado[1] > agora:
            return guardado[0]
    novo = _pedir_token(qual, pasta=pasta)
    with _TRAVA:
        _TOKENS[qual] = (novo, agora + SEGUNDOS_DO_TOKEN)
    return novo


# ------------------------------------------------------------- o transporte


def _operacao_do_caminho(caminho: str) -> str:
    """O nome da operação no log (`anuencias`, `token`…). Só calcula.

    **O log grava o NOME, e não o caminho com a query**: `nr_pedido`,
    `data_pedido` e a chave do protesto viajam na query, e log não é lugar
    de dado de título.
    """
    puro = str(caminho or "").split("?", 1)[0]
    for nome, modelo in CAMINHO.items():
        if "{" in modelo:
            if puro.startswith(modelo.split("{", 1)[0]):
                return nome
        elif puro == modelo:
            return nome
    return puro or "?"


def _bater(ambiente: str, metodo: str, caminho: str, *, corpo: bytes | None = None,
           cabecalhos: dict | None = None, prazo: int = PRAZO_PADRAO,
           com_token: bool = True, pasta=None) -> dict:
    """Uma requisição. Devolve `{status, json, texto}` — nunca estoura por 4xx.

    **Quem decide o que fazer com um 404 é quem chamou**, e não este módulo:
    pendência que não existe mais é caso normal numa Central que trabalha o dia
    inteiro.

    **O TRANSPORTE É O COMUM DAS CENTRAIS** desde 05/10/2026, marco (b):
    `centrais_http.requisitar(...).como_dict()`. As regras são as mesmas que
    este `_bater` já tinha — https obrigatório, cadeia TLS normal (sem fixar),
    `GET` repete o que não chegou e `POST` **não** se repete sozinho — e agora
    moram num lugar só. O `User-Agent` deixou de levar o CNS da serventia
    (dado da casa não se escreve no código). **Cada chamada fica no log das
    Centrais** (`centrais_log`), só com o status, a duração e o nome da
    operação — nunca o token, a senha ou o corpo.
    """
    base = base_do_ambiente(ambiente)
    hospedeiro, _porta, _prefixo = _partes(base)   # recusa o que não é https
    cabecas = dict(cabecalhos or {})
    if com_token:
        cabecas["Authorization"] = f"Bearer {token(ambiente, pasta=pasta)}"
    operacao = _operacao_do_caminho(caminho)
    qual = _ambiente_ok(ambiente)
    try:
        # A CADEIA NORMAL, e não certificado fixado — ver o cabeçalho do módulo.
        resposta = HTTP.requisitar(
            metodo, base.rstrip("/") + caminho, corpo=corpo,
            cabecalhos=cabecas, prazo=prazo, tentativas=TENTATIVAS_DE_REDE)
    except HTTP.CentralHttpError as erro:
        LOG.anotar_resposta(CENTRAL_NO_LOG, operacao, erro, ambiente=qual)
        raise CenprotError(
            f"Não consegui falar com a CENPROT em {hospedeiro}: "
            f"{erro.causa or erro}. Confira a internet da serventia e tente "
            f"de novo; nada foi enviado.") from erro
    LOG.anotar_resposta(CENTRAL_NO_LOG, operacao, resposta, ambiente=qual)
    return resposta.como_dict()


def _resposta_ou_erro(r: dict, o_que: str) -> Any:
    """Traduz o código da Central numa resposta ou numa frase de balcão."""
    if r["status"] == 200:
        return r["json"]
    if r["status"] == 401:
        raise CenprotError(
            f"A CENPROT recusou a autenticação ao {o_que}. A senha pode ter "
            f"sido trocada no cadastro do cartório — informe-a de novo em "
            f"Administrativo → Configurações → Centrais de Protesto.")
    if r["status"] == 404:
        raise CenprotRecusou(
            f"A CENPROT não encontrou o que se pediu ao {o_que}. Isso é normal "
            f"quando o pedido já foi tratado por lá ou por outra pessoa.")
    detalhe = ""
    if isinstance(r["json"], dict):
        detalhe = str(r["json"].get("message") or r["json"].get("erro") or "")
    raise CenprotRecusou(
        f"A CENPROT respondeu {r['status']} ao {o_que}"
        + (f": {detalhe}" if detalhe else f". Resposta: {r['texto'][:200]}"))


def _com_renovacao(ambiente: str, chamar) -> dict:
    """Chama; se vier 401, renova o token UMA vez e chama de novo.

    **Uma vez, e não em laço**: credencial errada devolve 401 sempre, e um
    laço faria o sistema martelar a Central com senha inválida até ela barrar
    a serventia.
    """
    r = chamar()
    if r["status"] == 401:
        esquecer_token(ambiente)
        r = chamar()
    return r


# ------------------------------------------------------------- o que se LÊ


def _ambiente_ok(qual: Any) -> str:
    """O ambiente em maiúsculas, com o padrão da casa. Só calcula."""
    return str(qual or "").strip().upper() or CRED.HOMOLOGACAO


def _listar(ambiente: str, chave: str, o_que: str, *, parametros: dict | None = None,
            pasta=None) -> Any:
    caminho = CAMINHO[chave]
    if parametros:
        limpos = {k: v for k, v in parametros.items() if v not in (None, "")}
        if limpos:
            caminho += "?" + urllib.parse.urlencode(limpos)
    r = _com_renovacao(
        ambiente, lambda: _bater(ambiente, "GET", caminho, pasta=pasta))
    if r["status"] == 404 and chave in LISTAS_QUE_RESPONDEM_404_QUANDO_VAZIAS:
        return []
    return _resposta_ou_erro(r, o_que)


# **NAS LISTAS, 404 QUER DIZER «NADA PENDENTE», E NÃO ERRO** — medido na
# produção em 13/10/2026: certidões, cancelamentos e renegociações voltaram
# 404, e o contrato descreve esse 404 como «Nenhuma certidão encontrada»,
# «Nenhum pedido encontrado», «Nenhuma renegociação encontrada». Tratado como
# recusa, o balcão via um erro onde a verdade era «não há nada para fazer».
# Fica de fora o que pede UM item (`anuencia_arquivos`): ali 404 é que o item
# pedido não existe, e isso continua sendo dito.
LISTAS_QUE_RESPONDEM_404_QUANDO_VAZIAS = frozenset({
    "anuencias", "certidoes", "cancelamento_pedidos", "renegociacoes",
    "decisao_judicial", "pedidos_consulta",
})


# **A MESMA API USA TRÊS CONVENÇÕES DE DATA E DUAS DE PAGINAÇÃO**, e isso está
# medido no `swagger.yaml`, e não suposto:
#
#     /v2/anuencias e /v2/certidoes    data_inicio · data_fim · pagina
#     /cancelamento/pedidos            dt_inicio · dt_fim  (OBRIGATÓRIOS)
#     /decisao-judicial/pendentes      dt_ocorrencia_de · dt_ocorrencia_ate
#                                      page · per_page
#
# **Eu escrevi as três iguais na primeira versão, e errei nas três.** O estrago
# seria calado: parâmetro que a Central não conhece ela ignora — a tela pediria
# «só as de setembro» e receberia o período inteiro, sem erro em lugar nenhum.
# É a lição da «mesma palavra em dois lugares», agora dentro de uma API só.

def anuencias(ambiente: Any = CRED.HOMOLOGACAO, *, pagina: int | None = None,
              inicio: str = "", fim: str = "", pasta=None) -> Any:
    """As anuências pendentes. SÓ LÊ — não aprova nem recusa nada.

    **AS DATAS SÃO OBRIGATÓRIAS NA PRODUÇÃO**, embora o contrato as chame de
    opcionais — medido em 13/10/2026: sem elas a Central responde 422 «Os
    parâmetros data_inicio e data_fim são obrigatórios». A recusa é aqui, no
    balcão, como a do cancelamento.
    """
    if not (str(inicio or "").strip() and str(fim or "").strip()):
        raise CenprotError(
            "Informe o período (data inicial e final) — a CENPROT exige as "
            "duas datas para listar as anuências.")
    return _listar(ambiente, "anuencias", "baixar as anuências", pasta=pasta,
                   parametros={"pagina": pagina, "data_inicio": inicio,
                               "data_fim": fim})


def certidoes(ambiente: Any = CRED.HOMOLOGACAO, *, pagina: int | None = None,
              inicio: str = "", fim: str = "", pasta=None) -> Any:
    """Os pedidos de certidão pendentes. SÓ LÊ."""
    return _listar(ambiente, "certidoes", "baixar os pedidos de certidão",
                   pasta=pasta,
                   parametros={"pagina": pagina, "data_inicio": inicio,
                               "data_fim": fim})


def pedidos_de_cancelamento(ambiente: Any = CRED.HOMOLOGACAO, *,
                            inicio: str, fim: str, pasta=None) -> Any:
    """Os pedidos de cancelamento do período. SÓ LÊ.

    **Este é um dos passos que o roteiro das Centrais declara em falta** — o
    sistema cobre 8 dos 16, e o recebimento de cancelamento pela CENPROT é um
    dos oito que faltam.
    """
    if not (str(inicio or "").strip() and str(fim or "").strip()):
        raise CenprotError(
            "Informe o período (data inicial e final) — a CENPROT exige as "
            "duas datas para listar os pedidos de cancelamento.")
    return _listar(ambiente, "cancelamento_pedidos",
                   "baixar os pedidos de cancelamento", pasta=pasta,
                   parametros={"dt_inicio": inicio, "dt_fim": fim})


# **A RENEGOCIAÇÃO É O CORAÇÃO DA RESOLVE, e era o caminho sem função.**
#
#   O comunicado que criou esta API diz que ela existe para que a Resolve
#   «aumente a base de títulos que podem ser cobrados junto aos devedores» —
#   e a renegociação é justamente a proposta que o devedor faz para quitar e
#   cancelar o protesto. Os caminhos estavam declarados aqui desde 02/09/2026
#   e **nenhuma função os chamava**: o balcão não via proposta nenhuma.
#
#   **A PAGINAÇÃO É A DO `v2`, e não a do `/decisao-judicial`.** Medido no
#   `swagger.yaml` v2.1.0: aqui são `data_inicio`, `data_fim` e `pagina`, com
#   1.000 por página — os mesmos nomes de `/v2/anuencias`, e **não** o
#   `page`/`per_page` da decisão judicial. Escrever os nomes errados não
#   estoura: a Central ignora o que não conhece, e a tela pediria «só as de
#   setembro» recebendo o período inteiro, sem erro em lugar nenhum.
def renegociacoes(ambiente: Any = CRED.HOMOLOGACAO, *,
                  pagina: int | None = None, inicio: str = "", fim: str = "",
                  pasta=None) -> Any:
    """As propostas de renegociação de dívida. SÓ LÊ — não aceita nem recusa.

    A resposta traz, por proposta, o código, as datas de cadastro e de
    vencimento, o valor proposto, a custa de cancelamento que a Central tem
    hoje, o status, e dois blocos aninhados: `dados_usuario` (quem propôs) e
    `dados_titulo` (devedor, protocolo e valores).
    """
    return _listar(_ambiente_ok(ambiente), "renegociacoes",
                   "baixar as renegociações", pasta=pasta,
                   parametros={"data_inicio": inicio, "data_fim": fim,
                               "pagina": pagina})


# O TETO DO LOTE É DO CONTRATO, e não uma precaução minha: o
# `/renegociacoes/processar` declara `maxItems: 1000`.
MAXIMO_DE_RENEGOCIACOES_POR_LOTE = 1000

# O QUE A CENTRAL EXIGE DE CADA RENEGOCIAÇÃO — os dois `required` do schema.
CAMPOS_OBRIGATORIOS_DA_RENEGOCIACAO: tuple[tuple[str, str], ...] = (
    ("cd_renegociacao_divida", "o código da renegociação"),
    ("vl_custa", "o valor da custa de cancelamento"),
)


def processar_renegociacoes(corpos: Any, ambiente: Any = CRED.HOMOLOGACAO, *,
                            pasta=None) -> Any:
    """Atribui a custa de cancelamento a um lote de renegociações. **ESCREVE.**

    **O CORPO É UM ARRAY, e o contrato diz isso com todas as letras**: «o
    payload deve ser obrigatoriamente um array». Mandar um objeto só faria a
    Central recusar o lote inteiro.

    **A CONFERÊNCIA É AQUI, e não na Central.** Ela responde com um
    `status_http` por item dentro de um 200 — de modo que um lote com metade
    recusada volta como sucesso. Conferir antes é o que impede o balcão de
    achar que mandou o que não mandou.
    """
    lote = list(corpos or [])
    if not lote:
        raise CenprotError(
            "Não há renegociação nenhuma para enviar.")
    if len(lote) > MAXIMO_DE_RENEGOCIACOES_POR_LOTE:
        raise CenprotError(
            f"A Central aceita no máximo "
            f"{MAXIMO_DE_RENEGOCIACOES_POR_LOTE} renegociações por envio, e "
            f"são {len(lote)}. Mande em partes.")

    for i, corpo in enumerate(lote, 1):
        for campo, o_que in CAMPOS_OBRIGATORIOS_DA_RENEGOCIACAO:
            if str((corpo or {}).get(campo, "")).strip() in ("", "None"):
                raise CenprotError(
                    f"A renegociação {i} do lote está sem {o_que} "
                    f"(«{campo}»). A Central recusa item a item dentro de uma "
                    f"resposta de sucesso, e o balcão não veria a recusa.")
    return _escrever(_ambiente_ok(ambiente), "renegociacoes_processar", lote,
                     "enviar as custas das renegociações", pasta=pasta)


def decisoes_judiciais(ambiente: Any = CRED.HOMOLOGACAO, *,
                       pagina: int | None = None, por_pagina: int | None = None,
                       chave: str = "", de: str = "", ate: str = "",
                       pasta=None) -> Any:
    """Os títulos com decisão judicial pendente. SÓ LÊ.

    **Isto conversa direto com a sustação do art. 17**, construída em
    01/09/2026: ordem que chega antes do protesto impede o ato. Aqui ela chega
    pela Central em vez de pelo balcão — e continua sendo o oficial quem
    registra, porque o sistema não julga ordem judicial.
    """
    return _listar(ambiente, "decisao_judicial",
                   "baixar as decisões judiciais pendentes", pasta=pasta,
                   parametros={"page": pagina, "per_page": por_pagina,
                               "nm_chave": chave,
                               "dt_ocorrencia_de": de,
                               "dt_ocorrencia_ate": ate})


def pedidos_de_protesto(ambiente=CRED.HOMOLOGACAO, *, numero: str = "",
                        data: str = "", pasta=None):
    """A REMESSA que chega pela CENPROT — o passo 1 do roteiro. SÓ LÊ.

    **É o passo que não tinha tela nenhuma**, e o roteiro o marcava como «no
    site da CENPROT». Devolve o pedido inteiro: título, devedor(es),
    codevedor(es), cedente, sacador e solicitante.

    **Um dos dois filtros é obrigatório** — o contrato diz «informe `nr_pedido`
    ou `data_pedido` (ao menos um)». Sem nenhum, a Central responde erro; a
    recusa daqui diz o que informar.
    """
    if not (str(numero or "").strip() or str(data or "").strip()):
        raise CenprotError(
            "Informe o número do pedido ou a data — a CENPROT exige ao menos "
            "um dos dois para consultar os pedidos de protesto.")
    return _listar(ambiente, "pedidos_consulta",
                   "consultar os pedidos de protesto", pasta=pasta,
                   parametros={"nr_pedido": numero, "data_pedido": data})


# **`renegociacoes()` EXISTIU AQUI, E FOI APAGADA — não desligada.**
#
# Eu a escrevi porque o caminho está no contrato, e **nenhuma tela a chamava**:
# é o defeito mais repetido deste projeto, seis vezes contadas, e a arma que
# alguém religa depois sem saber por que ela existia. As renegociações da
# plataforma RESOLVE **não estão no roteiro das Centrais** que o oficial
# trouxe, e construir tela para o que ele não pediu é inventar trabalho.
#
# **O CAMINHO FICA DECLARADO em `CAMINHO`**, e é de propósito: saber que ele
# existe é o que impede alguém de o reinventar achando que sumiu — a mesma
# razão dos caminhos legados. No dia em que a renegociação virar assunto da
# casa, a função volta em quatro linhas, com a tela junto.


def arquivos_da_anuencia(cd_anuencia: Any, ambiente: Any = CRED.HOMOLOGACAO,
                         *, pasta=None) -> Any:
    """Os PDFs da anuência, em base64. SÓ LÊ.

    **Pede-se pelo `cd_anuencia`, e não pela chave do protesto** — medido no
    contrato. Eu havia escrito `nm_chave` aqui, e a Central ou recusaria, ou —
    pior — ignoraria o parâmetro desconhecido e devolveria outra coisa.

    A anuência vem **assinada com e-CPF da ICP-Brasil**, no formato que
    `assinatura_digital` já lê dos instrumentos desta casa.
    """
    try:
        numero = int(str(cd_anuencia).strip())
    except (TypeError, ValueError) as erro:
        raise CenprotError(
            f"O código da anuência é um número, e veio «{cd_anuencia}»."
        ) from erro
    return _listar(ambiente, "anuencia_arquivos", "baixar o PDF da anuência",
                   pasta=pasta, parametros={"cd_anuencia": numero})


# ----------------------------------------------------------- o que ESCREVE
#
# **TUDO ABAIXO MUDA COISA NA CENTRAL.** Nenhuma destas funções é chamada por
# relógio nem por tela de consulta: quem as chama é uma rota que o operador
# clicou, depois de decidir. É a regra do CNIB.


def _escrever(ambiente: str, chave: str, corpo: Any, o_que: str, *,
              caminho_pronto: str | None = None, pasta=None) -> Any:
    if chave not in CAMINHOS_QUE_ESCREVEM:
        raise CenprotError(
            f"«{chave}» não está declarado como caminho que escreve na "
            f"Central. Isso é engano de programação, e não do balcão.")
    caminho = caminho_pronto or CAMINHO[chave]
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    r = _com_renovacao(ambiente, lambda: _bater(
        ambiente, "POST", caminho, corpo=dados,
        cabecalhos={"Content-Type": "application/json"}, pasta=pasta))
    return _resposta_ou_erro(r, o_que)


# O QUE A CENTRAL EXIGE DE CADA ANUÊNCIA, medido em DUAS fontes do mesmo
# contrato — porque o schema do `v2` lista as propriedades e **não** declara
# quais são obrigatórias:
#
#   · a descrição do `/v2/anuencia/processar` diz «Campos obrigatórios:
#     cd_anuencia, ic_aprovado, **dados do protocolo e devedor**»;
#   · o gêmeo legado `/anuencia/processar` marca `required: true` em **doze**
#     parâmetros, e são exatamente esses.
#
# **EU CONFERIA DOIS DE DOZE.** A conferência existe porque «a Central responde
# 500 sem dizer qual item faltou» — conferindo dois, o balcão continuaria
# levando o 500 mudo pelos outros dez.
CAMPOS_OBRIGATORIOS_DA_ANUENCIA: tuple[tuple[str, str], ...] = (
    ("cd_anuencia", "o código da anuência"),
    ("nm_chave", "a chave do protesto"),
    ("nm_nr_protocolo", "o número do protocolo"),
    ("dt_protocolo", "a data do protocolo"),
    ("nm_nr_titulo", "o número do título"),
    ("dt_emissao", "a data de emissão do título"),
    ("vl_protesto", "o valor do protesto"),
    ("nm_devedor", "o nome do devedor"),
    ("nm_nr_documento_devedor", "o documento do devedor"),
    ("nm_nr_documento_credor", "o documento do credor"),
    ("dt_solicitacao_anuencia", "a data da solicitação da anuência"),
)

# E ELES VÊM DA PRÓPRIA CENTRAL: o `GET /v2/anuencias` devolve «dados completos
# incluindo devedor, credor, solicitante, cartório e assinaturas». O domínio
# devolve o que baixou, acrescentando a decisão do oficial.


def _falta(item: dict, campo: str) -> bool:
    """O campo não veio? **ZERO E `False` VIERAM.**

    `str(v or "").strip()` trata `0` e `False` como ausência, e este projeto já
    pagou por isso duas vezes — o `or` que religou a fonte que o oficial tinha
    desligado, e o `str(v or "")` que comia o zero da declaração de mês vazio do
    SIRC. **Aqui custaria caro:** `vl_custas` **zero é anuência gratuita**, e
    esta casa lavra ato gratuito (o valor que ele teria é o que a serventia
    compensa junto ao fundo).
    """
    if campo not in item:
        return True
    valor = item[campo]
    if valor is None:
        return True
    return isinstance(valor, str) and not valor.strip()


def processar_anuencia(decisoes: list[dict],
                       ambiente: Any = CRED.HOMOLOGACAO, *, pasta=None) -> Any:
    """Aprova ou recusa anuências. **ESCREVE NA CENTRAL.**

    Cada item tem de trazer `ic_aprovado`; com `True` o `vl_custas` é
    obrigatório, e com `False` o `motivo_recusa`. **A conferência é aqui, e não
    lá**: a Central responde 500 sem dizer qual item faltou, e quem está no
    balcão precisa saber qual.
    """
    if not decisoes:
        raise CenprotError("Não há anuência marcada para enviar.")
    for i, d in enumerate(decisoes, start=1):
        for campo, rotulo in CAMPOS_OBRIGATORIOS_DA_ANUENCIA:
            if _falta(d, campo):
                raise CenprotError(
                    f"A anuência {i} está sem {rotulo} (`{campo}`), que a "
                    f"CENPROT exige. Esse dado vem da própria Central, no "
                    f"«baixar as anuências» — refaça a baixa antes de enviar.")
        aprovado = d.get("ic_aprovado")
        if aprovado is None:
            raise CenprotError(
                f"A anuência {i} não diz se foi aprovada ou recusada.")
        if aprovado and _falta(d, "vl_custas"):
            raise CenprotError(
                f"A anuência {i} foi aprovada e está sem o valor das custas — "
                f"a CENPROT exige o valor quando se aprova.")
        if not aprovado and _falta(d, "motivo_recusa"):
            raise CenprotError(
                f"A anuência {i} foi recusada e está sem o motivo — a CENPROT "
                f"exige o motivo quando se recusa, e quem lê é quem pediu.")
    return _escrever(ambiente, "anuencia_processar", decisoes,
                     "enviar as anuências", pasta=pasta)


def processar_certidao(pedidos: list[dict],
                       ambiente: Any = CRED.HOMOLOGACAO, *, pasta=None) -> Any:
    """Manda o orçamento — e a certidão, quando pronta. **ESCREVE NA CENTRAL.**

    **O CONTRATO DECLARA TRÊS OBRIGATÓRIOS, E EU CONFERIA UM.** O schema traz
    `required: [cd_pedido, vl_orcamento, arquivo_certidao]`, e o `vl_orcamento`
    é **dinheiro**: pedido sem ele é a Central recusando calada, ou o balcão
    orçando o que não disse.

    **E O TERCEIRO SE CONTRADIZ DENTRO DO PRÓPRIO CONTRATO**, o que fica
    declarado em vez de resolvido por palpite: a lista `required` põe
    `arquivo_certidao` como sempre obrigatório, e a descrição, duas linhas
    acima, diz «**se o status for 'aguardando certidão'**, necessário enviar o
    arquivo». **Exigi-lo sempre travaria o orçamento**, que é o primeiro passo
    — e nele a certidão ainda não existe. Fica exigido o que as duas fontes
    afirmam junto; o arquivo é do domínio, que sabe o status.
    """
    if not pedidos:
        raise CenprotError("Não há pedido de certidão marcado para enviar.")
    for i, p in enumerate(pedidos, start=1):
        if _falta(p, "cd_pedido"):
            raise CenprotError(
                f"O pedido {i} está sem o número do pedido (`cd_pedido`). Ele "
                f"vem do próprio «baixar os pedidos de certidão».")
        if _falta(p, "vl_orcamento"):
            raise CenprotError(
                f"O pedido {i} está sem o valor do orçamento (`vl_orcamento`), "
                f"que a CENPROT exige. É o que a casa vai cobrar pela "
                f"certidão, e é o número que o solicitante vê.")
    return _escrever(ambiente, "certidao_processar", pedidos,
                     "enviar os pedidos de certidão", pasta=pasta)


def cancelar_protesto(cd_pedido: Any, ambiente: Any = CRED.HOMOLOGACAO, *,
                      certidao_b64: str = "", pasta=None) -> Any:
    """Informa à Central o cancelamento. **ESCREVE NA CENTRAL.**

    **E NÃO CANCELA NADA NESTA CASA.** O ato de cancelamento se lavra na ficha
    do título, com hipótese do catálogo e fundamento escrito — é a regra do
    módulo desde 24/08/2026. Esta função apenas comunica o que já foi lavrado.
    """
    try:
        numero = int(str(cd_pedido).strip())
    except (TypeError, ValueError) as erro:
        raise CenprotError(
            f"O código do pedido é um número, e veio «{cd_pedido}». Ele vem "
            f"do próprio GET /cancelamento/pedidos."
        ) from erro
    corpo: dict = {"cd_pedido": numero}
    if str(certidao_b64 or "").strip():
        # O contrato aceita SÓ PDF aqui, e em base64.
        corpo["certidao_cancelamento_b64"] = str(certidao_b64).strip()
    return _escrever(ambiente, "cancelar_protesto", corpo,
                     "informar o cancelamento", pasta=pasta)


# OS CINCO CAMPOS DO PROTOCOLAR, e o contrato é taxativo: «**todos** os campos
# do protocolar são obrigatórios em qualquer modo de envio».
CAMPOS_DO_PROTOCOLAR: tuple[tuple[str, str], ...] = (
    ("cd_pedido_protesto", "o número do pedido de protesto"),
    ("cd_chave_unica", "a chave única de 23 dígitos"),
    ("nm_nr_protocolo", "o número do protocolo desta casa"),
    ("dt_protocolo", "a data do protocolo"),
    ("vl_retirada", "o valor da retirada"),
)


def protocolar_pedidos(itens: list[dict], ambiente=CRED.HOMOLOGACAO, *,
                       pasta=None):
    """Devolve à Central o protocolo desta casa. **ESCREVE NA CENTRAL.**

    É a outra metade do passo 1: a Central manda o pedido, a casa aponta, e
    **devolve o número do protocolo e a chave única** para os dois lados
    falarem do mesmo título.

    **O CORPO VAI EMBRULHADO AQUI — E SÓ AQUI.** Este é o schema que declara
    `type: object` com um array `pedidos` dentro; os dois `processar` declaram
    `type: array` na raiz e o corpo **É** a lista. Escrever os três iguais
    quebraria dois deles.

    Vale lembrar por quê: **a correção mais cara deste projeto** foi
    exatamente o contrário — eu embrulhava o pedido de selo em
    `{"dadosSelo": …}` porque a documentação nomeava o parâmetro de corpo, e
    com o embrulho **nenhum selo automático sairia, em atribuição nenhuma**.
    A lição não é «nunca embrulhe»: é **leia o schema de cada caminho**.

    **A CHAVE ÚNICA NÃO SE INVENTA, E O `GET` NÃO A DEVOLVE.** Medido: o
    `/pedidos/consulta` não tem `cd_chave_unica` em campo nenhum da resposta, e
    o `protocolar` a exige. Ela vem do **XML diário** que a Central publica —
    que é o que `protesto_cenprot` já lê, casando a chave com o nosso protocolo
    em 175 de 175. Sem ela gravada em `pt_titulos.chave_cenprot`, o título não
    entra aqui, e a frase diz onde consegui-la.
    """
    if not itens:
        raise CenprotError("Não há pedido marcado para protocolar.")
    if len(itens) > LIMITE_DO_LOTE_PROTOCOLAR:
        raise CenprotError(
            f"São {len(itens)} pedidos, e a CENPROT aceita no máximo "
            f"{LIMITE_DO_LOTE_PROTOCOLAR} por vez. Mande em partes.")
    for i, item in enumerate(itens, start=1):
        for campo, rotulo in CAMPOS_DO_PROTOCOLAR:
            if _falta(item, campo):
                raise CenprotError(
                    f"O pedido {i} está sem {rotulo} (`{campo}`), e a CENPROT "
                    f"exige os cinco campos do protocolar.")
        chave = str(item["cd_chave_unica"]).strip()
        if len(chave) != DIGITOS_DA_CHAVE_UNICA:
            raise CenprotError(
                f"A chave única do pedido {i} tem {len(chave)} caracteres, e a "
                f"CENPROT exige {DIGITOS_DA_CHAVE_UNICA}. Ela vem do XML "
                f"diário da Central — carregue-o em «Protesto → O dia da CRA → "
                f"Chave do CENPROT» antes de protocolar.")
    return _escrever(ambiente, "pedidos_protocolar", {"pedidos": list(itens)},
                     "devolver os protocolos à CENPROT", pasta=pasta)


def enviar_custas(nome_arquivo: str, arquivo_b64: str,
                  ambiente: Any = CRED.HOMOLOGACAO, *, pasta=None) -> Any:
    """Manda o arquivo de custas em base64. **ESCREVE NA CENTRAL.**

    O formato do arquivo é o que `protesto_cenprot` já monta — medido no
    exemplar que o oficial gerou pelo E-Ofício, com a receita fechando em 166
    de 173 no centavo.
    """
    if not str(arquivo_b64 or "").strip():
        raise CenprotError("Não há arquivo de custas para enviar.")
    if not str(nome_arquivo or "").strip():
        # **O NOME FAZ PARTE DO CONTRATO**, e tem forma:
        # `UF-CODIGOIBGE-NUMEROCARTORIO-E-YYYYMMDD-SS.txt`. Mandar sem nome
        # seria mandar um arquivo que a Central não sabe de quem é.
        raise CenprotError(
            "Informe o nome do arquivo de custas — a CENPROT o exige, no "
            "formato UF-CODIGOIBGE-NUMEROCARTORIO-E-AAAAMMDD-SS.txt.")
    # **O CONTRATO TEM UM ERRO DE DIGITAÇÃO AQUI, e ele é uma armadilha.** A
    # lista `required` escreve `'base64_arquivo  '` — entre aspas e com DOIS
    # espaços no fim —, enquanto a propriedade, logo abaixo, se chama
    # `base64_arquivo`. Quem copiar o nome da lista manda um campo que a
    # Central não conhece. Vale o nome da PROPRIEDADE, que é o do exemplo.
    return _escrever(ambiente, "custas_arquivo",
                     {"nome_arquivo": str(nome_arquivo).strip(),
                      "base64_arquivo": str(arquivo_b64).strip()},
                     "enviar o arquivo de custas", pasta=pasta)


def diagnostico(ambiente: Any = CRED.HOMOLOGACAO, *, pasta=None) -> dict:
    """Tenta autenticar e diz o que aconteceu. **Não baixa nem envia nada.**

    É o que a tela chama no botão «testar a conexão»: sem isto, a primeira
    notícia de credencial errada seria no meio de um download.
    """
    qual = str(ambiente or "").strip().upper() or CRED.HOMOLOGACAO
    if not CRED.tem(CRED.CENPROT, qual, pasta):
        return {"ok": False, "ambiente": qual,
                "motivo": "A credencial da CENPROT ainda não foi informada."}
    try:
        esquecer_token(qual)
        token(qual, pasta=pasta)
    except CenprotError as erro:
        return {"ok": False, "ambiente": qual, "motivo": str(erro)}
    return {"ok": True, "ambiente": qual,
            "base": base_do_ambiente(qual),
            "motivo": "Autenticou na CENPROT e recebeu o token."}
