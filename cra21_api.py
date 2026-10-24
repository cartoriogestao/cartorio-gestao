"""A API DA CRA/CRA21 — o transporte SOAP, e só ele.

Ordem do oficial em 02/09/2026: *«vamos integrar a api da cra21»*.

**O CONTRATO SE MEDIU NO PRÓPRIO WSDL**, que está público e respondeu HTTP 200
sem credencial nenhuma — os dois arquivos estão em `FONTES_EXTERNAS/cra21/`.
São **21 operações**, todos os parâmetros `string` e toda resposta um `return`
`string`.

**O QUE A API ACRESCENTA NÃO É O FORMATO: É O TRANSPORTE.** `protesto_arquivo`
já lê **e escreve** os cinco layouts da CRA, medido em 697 arquivos reais com
ida e volta byte a byte. O que o escrevente faz hoje à mão — entrar no site,
baixar, subir — é o que esta API faz sozinha. **Nada aqui interpreta arquivo**:
o que volta vai para os módulos que já sabem lê-lo.

**HTTPS SE FORÇA; NÃO SE LÊ DO WSDL.** Medido em 02/09/2026: os dois WSDL são
idênticos nas 21 operações, e a única diferença real é o endereço —

    produção     https://crama.crabr.com.br:443/crama/xml/protestos_cartorio.php
    homologação  http://crama.cra21.com.br/crama/xml/protestos_cartorio.php

**O de homologação declara `http://`, sem o S**, e o manual diz que HTTPS é
obrigatório. Quem montar o cliente lendo o WSDL — que é o normal — falaria em
**texto puro** com a Central, e a autenticação desta API é **HTTP Basic**: a
senha do cartório viajaria legível na rede. É a mesma decisão do selador, onde
o certificado se **fixa** em vez de se ignorar: **quando a rede é o meio, quem
decide o transporte é a casa.**

**E O NAMESPACE MUDA COM O AMBIENTE** — `urn:crama.crabr.com.br` na produção e
`urn:crama.cra21.com.br` na homologação. Num cliente que monta o envelope à
mão, isso não é detalhe: com o namespace errado a Central não reconhece a
operação, e a recusa não diz por quê. Os dois estão medidos aqui, um por
ambiente.

**A CREDENCIAL É HTTP BASIC, E NENHUMA OPERAÇÃO RECEBE USUÁRIO.** Conferido nas
21: não há parâmetro de login, senha nem código de cartório — quem identifica a
serventia é a credencial HTTP. Ela vem de `centrais_cred`, **fora do banco**.

**O QUE NÃO SE MEDIU FICA DECLARADO, E NÃO ADIVINHADO.** O manual não descreve
o que vai em `userDados`, e o exemplo em PHP passa **um argumento só**
(`$client->Confirmacao('C0013110.141')`). A hipótese razoável é o conteúdo do
arquivo — e **hipótese não se escreve em código que fala com a Central**. Por
isso este módulo tem funções nomeadas **só para as operações cujo sentido está
medido**, e uma porta genérica, `chamar()`, para as demais: ela confere os
nomes dos parâmetros contra o contrato e manda o que lhe derem, **sem inventar
conteúdo**. Isso se resolve com uma chamada em homologação, que é justamente o
que a P21 ofereceu liberar.
"""
from __future__ import annotations

import base64
from datetime import date as _date
import re
import urllib.parse
from typing import Any
from xml.sax import saxutils

import centrais_cred as CRED
import centrais_http as HTTP
import centrais_log as LOG

# OS DOIS AMBIENTES, medidos no `soap:address` de cada WSDL — **com o `https`
# forçado no de homologação**, que o arquivo declara sem o S.
ENDERECO_DO_AMBIENTE: dict[str, str] = {
    CRED.PRODUCAO:
        "https://crama.crabr.com.br/crama/xml/protestos_cartorio.php",
    CRED.HOMOLOGACAO:
        "https://crama.cra21.com.br/crama/xml/protestos_cartorio.php",
}

# O NAMESPACE DE CADA UM, medido no `targetNamespace` e no `soapAction`.
NAMESPACE_DO_AMBIENTE: dict[str, str] = {
    CRED.PRODUCAO: "urn:crama.crabr.com.br",
    CRED.HOMOLOGACAO: "urn:crama.cra21.com.br",
}

# **O `crama` É O MARANHÃO** — o padrão do manual é `craUF`. Fica escrito
# porque quem ler `crama` sem saber disso pode achar que é nome de produto.
UF_DA_CENTRAL = "MA"

# AS 21 OPERAÇÕES, com os parâmetros **na ordem do WSDL**. A ordem importa:
# em SOAP `rpc/encoded` os parâmetros são posicionais dentro do elemento da
# operação, e trocá-los manda a data no lugar do protocolo — sem erro nenhum.
OPERACOES: dict[str, tuple[str, ...]] = {
    "Remessa": ("userArq", "downloadImagem"),
    "RemessaPendente": ("userArq", "downloadImagem"),
    "Confirmacao": ("userArq", "userDados"),
    "Retorno": ("userArq", "userDados"),
    "Desistencia": ("userArq",),
    "Cancelamento": ("userArq", "downloadImagem"),
    "Autorizacao": ("userArq", "downloadImagem"),
    "BuscarApresentante": (),
    "Imagem": ("userArq", "userDados"),
    "ConsultaSlip": ("protocolo", "dataProtocolo"),
    "ConsultaAutorizacao": ("userArq", "protocolo", "dataProtocolo",
                            "marcarBaixado"),
    "ConsultaImagem": ("nossoNumero", "numeroTitulo", "documentoDevedor",
                       "saldoTitulo", "vencimento", "remessa"),
    "Intimacao": ("userArq", "userDados"),
    "ConsultaIntimacao": ("userDados",),
    "AvisoAutorizacao": ("userArq", "userDados"),
    "ConsultaAvisoAutorizacao": ("userDados",),
    "CustasTitulo": ("userArq", "userDados"),
    "TituloComplemento": ("userArq", "userDados"),
    "AutorizacoesEfetivadas": ("userDados",),
    "ConsultaAutorizacoesPeriodo": ("dataInicioSolicitacao",
                                    "dataFimSolicitacao",
                                    "dataInicioRemessa", "dataFimRemessa"),
    "OrdemCancelamento": ("userArq",),
}

# **AS QUE PODEM MUDAR O ESTADO NA CENTRAL.** Inclusive downloads que podem
# marcar um arquivo como baixado. Nunca repeti-las após uma falha incerta.
OPERACOES_QUE_ESCREVEM: frozenset[str] = frozenset({
    "Confirmacao", "Retorno", "Imagem", "Intimacao", "AvisoAutorizacao",
    "Remessa", "RemessaPendente", "Desistencia", "Cancelamento",
    "Autorizacao", "OrdemCancelamento"})

# **AS QUE AINDA NÃO TÊM SENTIDO MEDIDO**, porque dependem de `userDados` — e
# o manual não o descreve. Elas **existem** e se alcançam por `chamar()`; o que
# não existe é uma função nomeada que finja saber o que mandar.
OPERACOES_SEM_SENTIDO_MEDIDO: frozenset[str] = frozenset({
    "Imagem", "Intimacao", "ConsultaIntimacao", "AvisoAutorizacao",
    "ConsultaAvisoAutorizacao", "CustasTitulo", "TituloComplemento",
    "AutorizacoesEfetivadas"})

# O QUE `downloadImagem` ACEITA, medido no manual: **1** baixa a imagem e
# **2** só confere se ela existe.
BAIXAR_A_IMAGEM = "1"
SO_CONFERIR_A_IMAGEM = "2"

# Limites do servidor, do manual: 100 MB por arquivo e 30 minutos de tempo
# limite. O prazo daqui é menor de propósito — o balcão não espera meia hora,
# e prazo de meia hora numa tela é a tela que parece travada.
PRAZO_PADRAO = 180
TENTATIVAS_DE_REDE = 2

# O NOME DESTA CENTRAL NO LOG E NA FILA COMUNS — o mesmo de `centrais_cred`.
CENTRAL_NO_LOG = CRED.CRA

# **OS CÓDIGOS DO `<relatorio><codigo>`, MEDIDOS CONTRA A HOMOLOGAÇÃO EM
# 12/09/2026** — o manual não descreve o que volta no `return`; isto é o que
# a própria Central respondeu, com nomes de arquivo reais desta serventia
# (achados nas pastas de remessa, retorno e desistência da serventia):
#   0002 — nome do arquivo inválido (a FORMA está errada: sem o
#          apresentante+dia+mês+extensão de 3 dígitos, ou em branco)
#   0003 — não existe remessa na data informada (a forma está CERTA; não há
#          arquivo com esse nome/data do lado de lá)
#   0006 — não existe desistência na data informada (o mesmo, para
#          `Desistencia`)
#   10000 — "1.5 ARQUIVO XML CORROMPIDO": apareceu com nomes inventados que
#          pareciam válidos e não eram (ex.: `C0013110.141`, do exemplo do
#          manual) — não se sabe ainda se é "nome bem-formado mas
#          inexistente" tratado diferente do 0003, ou outra coisa; fica
#          A CONFERIR.
CODIGOS_MEDIDOS: dict[str, str] = {
    "0002": "Nome do arquivo inválido (forma errada, ou em branco).",
    "0003": "Não existe remessa na data informada.",
    "0006": "Não existe desistência na data informada.",
    "10000": "1.5 ARQUIVO XML CORROMPIDO — A CONFERIR.",
}


class CraError(RuntimeError):
    """Falha de transporte ou de credencial, com a frase para o balcão."""


class CraRecusou(CraError):
    """A Central respondeu, e respondeu não. O motivo dela vem junto.

    `bruto` é a resposta INTEIRA da Central, quando há uma — à parte da frase.
    A frase vai à tela (e o `flash` mora no cookie da sessão, que não leva
    XML de vários KB); o bruto vai só para o campo de erro do arquivo
    (`pt_retornos.cra_envio_erro`), que é onde se confere depois (LH08)."""

    def __init__(self, mensagem: str = "", *, bruto: str = "") -> None:
        super().__init__(mensagem)
        self.bruto = str(bruto or "")


# O PADRÃO É PRODUÇÃO DESDE 14/10/2026 — ordem do oficial no primeiro dia do
# protesto no sistema: «tire a opção de funcionar na homologação, agora é tudo
# produção». Até 13/10 o ambiente vazio ou desconhecido caía na homologação.
# O endereço de homologação continua declarado acima, para o teste
# automatizado que o pede pelo nome; nenhuma tela o oferece mais.


def endereco_do_ambiente(ambiente: Any) -> str:
    nome = str(ambiente or "").strip().upper()
    return ENDERECO_DO_AMBIENTE.get(nome,
                                    ENDERECO_DO_AMBIENTE[CRED.PRODUCAO])


def namespace_do_ambiente(ambiente: Any) -> str:
    nome = str(ambiente or "").strip().upper()
    return NAMESPACE_DO_AMBIENTE.get(nome,
                                     NAMESPACE_DO_AMBIENTE[CRED.PRODUCAO])


def _partes(endereco: str) -> tuple[str, int, str]:
    p = urllib.parse.urlsplit(endereco)
    if p.scheme != "https":
        # **HTTPS NÃO É OPCIONAL AQUI**, e este guarda existe por causa de um
        # achado: o WSDL de homologação declara `http://`. A credencial é HTTP
        # Basic — em texto puro, quem estiver na rede a lê.
        raise CraError(
            f"O endereço da CRA tem de ser https, e veio «{endereco}». O WSDL "
            f"de homologação declara http:// sem o S, e a senha do cartório "
            f"viajaria legível — o sistema recusa de propósito.")
    return p.hostname or "", p.port or 443, p.path or "/"


def envelope(operacao: str, valores: dict, namespace: str) -> bytes:
    """O envelope SOAP 1.1 `rpc/encoded` daquela operação.

    **A ORDEM DOS PARÂMETROS É A DO CONTRATO**, e não a do dicionário: em
    `rpc/encoded` eles são posicionais, e trocá-los manda a data no lugar do
    protocolo **sem erro nenhum** — a Central aceitaria e responderia outra
    coisa.

    E **todo valor vai escapado**: nome de arquivo com `&` não é comum, mas
    conteúdo de arquivo é — e um `&` solto quebra o XML do lado de lá.
    """
    if operacao not in OPERACOES:
        raise CraError(
            f"«{operacao}» não é operação da CRA. Isso é engano de "
            f"programação, e não do balcão.")
    sobrando = set(valores) - set(OPERACOES[operacao])
    if sobrando:
        raise CraError(
            f"A operação {operacao} não conhece {sorted(sobrando)}. Os "
            f"parâmetros dela são {list(OPERACOES[operacao])}.")
    corpo = "".join(
        f"<{nome}>{saxutils.escape(str(valores.get(nome, '')))}</{nome}>"
        for nome in OPERACOES[operacao])
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<SOAP-ENV:Envelope '
        'xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xmlns:ns1="{namespace}">'
        '<SOAP-ENV:Body>'
        f'<ns1:{operacao} SOAP-ENV:encodingStyle='
        '"http://schemas.xmlsoap.org/soap/encoding/">'
        f'{corpo}'
        f'</ns1:{operacao}>'
        '</SOAP-ENV:Body></SOAP-ENV:Envelope>'
    ).encode()


_RETORNO = re.compile(r"<return[^>]*>(.*?)</return>", re.DOTALL)
_FALHA = re.compile(r"<faultstring[^>]*>(.*?)</faultstring>", re.DOTALL)
_ERRO_NO_RETURN = re.compile(
    r"<erro\b[^>]*>.*?<mensagem[^>]*>(.*?)</mensagem>.*?<codigo[^>]*>"
    r"(.*?)</codigo>",
    re.DOTALL | re.IGNORECASE)
_RELATORIO_NO_RETURN = re.compile(
    r"<relatorio\b[^>]*>.*?<codigo[^>]*>(.*?)</codigo>.*?<ocorrencia[^>]*>"
    r"(.*?)</ocorrencia>",
    re.DOTALL | re.IGNORECASE)


def _desfaz_aspas_escapadas_cra(texto: str) -> str:
    """Aspas de delimitador XML que a CRA devolve como ``&quot;`` após o SOAP.

    Medido na homologação: o ``<return>`` traz remessa XML cujos delimitadores
    ainda aparecem escapados depois de ``saxutils.unescape``. Só este escape
    é desfeito aqui; ``&amp;`` dentro de valores continua para o parser XML.
    """
    if "&quot;" in texto[:120]:
        texto = texto.replace("&quot;", '"')
    return texto


def _recusa_de_relatorio(texto: str) -> str | None:
    """XML ``<relatorio>`` — medido na homologação (RemessaPendente / Remessa)."""
    if "<relatorio" not in texto.lower():
        return None
    achado = _RELATORIO_NO_RETURN.search(texto)
    if achado is None:
        return "A CRA devolveu um relatório sem código legível."
    cod = achado.group(1).strip()
    msg = saxutils.unescape(achado.group(2).strip())
    base = f"{msg} (código {cod})" if cod else msg
    extra = CODIGOS_MEDIDOS.get(cod)
    if extra:
        return f"{base} — {extra}"
    return base


def recusa_no_return(texto: str) -> str | None:
    """Recusa legível dentro do ``<return>`` — medido na homologação real.

    A CRA devolve falha de autenticação (código 1) com HTTP 200 e corpo SOAP
    normal, **sem** ``faultstring`` nem HTTP 401 — tag ``<erro>``. Nas operações
    de arquivo, devolve ``<relatorio><codigo>0002|0003|…</codigo>`` com
    ``<ocorrencia>``. Quem contar só caracteres do ``return`` confunde isso
    com remessa ou com a lista de apresentantes.
    """
    if "<erro" in texto.lower():
        achado = _ERRO_NO_RETURN.search(texto)
        if achado is None:
            return "A CRA devolveu um erro no conteúdo da resposta."
        msg = saxutils.unescape(achado.group(1).strip())
        cod = achado.group(2).strip()
        return f"{msg} (código {cod})" if cod else msg
    return _recusa_de_relatorio(texto)


def ler_resposta(texto: str, o_que: str) -> str:
    """O `return` da resposta, ou a frase do balcão. Não interpreta o conteúdo.

    **A FALHA SOAP VEM COM HTTP 500**, e não com 200 — quem olhar só o código
    da resposta chamaria de erro de rede o que é recusa da Central, com motivo
    escrito dentro.
    """
    falha = _FALHA.search(texto)
    if falha:
        raise CraRecusou(
            f"A CRA recusou ao {o_que}: {saxutils.unescape(falha.group(1))}")
    achado = _RETORNO.search(texto)
    if achado is None:
        raise CraRecusou(
            f"A CRA respondeu ao {o_que} sem o conteúdo esperado. "
            f"Resposta: {texto[:300]}")
    return _desfaz_aspas_escapadas_cra(saxutils.unescape(achado.group(1)))


def _bater(ambiente: str, operacao: str, valores: dict, *,
           prazo: int = PRAZO_PADRAO, pasta=None) -> str:
    """Uma chamada SOAP. Devolve o texto cru da resposta.

    **O TRANSPORTE É O COMUM DAS CENTRAIS** desde 05/10/2026, marco (b):
    `centrais_http.requisitar(...).como_dict()`. SOAP é sempre `POST`, e por
    isso a regra de «retentar só o que não chegou» se diz aqui por operação:
    só as que **não** estão em `OPERACOES_QUE_ESCREVEM` se repetem sozinhas
    (`retentar_escrita`), exatamente como antes. O `User-Agent` deixou de
    levar o CNS da serventia. **Cada chamada fica no log das Centrais**, só
    com o status, a duração e o nome da operação — nunca a credencial Basic.

    **O TEXTO VEM DO CORPO INTEIRO, e não do `texto` do adaptador**: o
    cliente comum corta `texto` em 2 MB, e uma remessa com imagem passa
    disso (o servidor da CRA aceita 100 MB). Cortar ali entregaria a
    `protesto_arquivo` meia remessa, calada.
    """
    usuario, senha = CRED.credencial(CRED.CRA, ambiente, pasta)
    endereco = endereco_do_ambiente(ambiente)
    hospedeiro, _porta, _caminho = _partes(endereco)   # recusa o que não é https
    namespace = namespace_do_ambiente(ambiente)
    corpo = envelope(operacao, valores, namespace)
    credencial = base64.b64encode(
        f"{usuario}:{senha}".encode()).decode("ascii")
    cabecas = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f'"{namespace}#{operacao}"',
        "Authorization": f"Basic {credencial}",
        "Content-Length": str(len(corpo)),
    }
    escreve = operacao in OPERACOES_QUE_ESCREVEM
    qual = str(ambiente or "").strip().upper() or CRED.PRODUCAO
    try:
        # **RETENTAR SÓ O QUE NÃO CHEGOU.** Uma confirmação que a Central
        # pode ter recebido não se repete sozinha — o arquivo entraria duas
        # vezes lá dentro.
        resposta = HTTP.requisitar(
            "POST", endereco, corpo=corpo, cabecalhos=cabecas, prazo=prazo,
            tentativas=TENTATIVAS_DE_REDE, retentar_escrita=not escreve)
    except HTTP.CentralHttpError as erro:
        LOG.anotar_resposta(CENTRAL_NO_LOG, operacao, erro, ambiente=qual)
        ultimo = erro.causa or erro
        if escreve:
            raise CraError(
                f"Falha de comunicação com a CRA em {hospedeiro}: {ultimo}. "
                "Não é possível saber se a Central recebeu esta operação ou "
                "marcou o arquivo como baixado. Não repita automaticamente; "
                "confira a situação na CRA antes de tentar de novo.") from erro
        raise CraError(
            f"Não consegui falar com a CRA em {hospedeiro}: {ultimo}. Confira "
            "a internet da serventia antes de tentar de novo.") from erro
    LOG.anotar_resposta(CENTRAL_NO_LOG, operacao, resposta, ambiente=qual)
    r = resposta.como_dict()
    if r["status"] == 401:
        raise CraError(
            "A CRA recusou a credencial. Confira o usuário e a senha "
            "em Administrativo → Configurações → Centrais de "
            "Protesto; eles são os do cartório na CRA, e o Tabelião "
            "ou o Substituto é quem os cadastra.")
    try:
        return resposta.corpo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return resposta.corpo.decode("iso-8859-1")


def chamar(operacao: str, ambiente: Any = CRED.PRODUCAO, *,
           o_que: str = "", pasta=None, **valores) -> str:
    """A porta genérica: qualquer das 21, com os nomes conferidos.

    **ELA EXISTE POR CAUSA DO QUE NÃO SE MEDIU.** Dez das 21 operações
    dependem de `userDados`, e o manual não diz o que vai nele — escrever dez
    funções nomeadas com um conteúdo suposto seria pôr no código uma hipótese
    com cara de contrato. Aqui o chamador informa o que quer mandar, e o
    módulo confere **os nomes** contra o WSDL, que é o que ele sabe.
    """
    qual = str(operacao or "").strip()
    if qual not in OPERACOES:
        raise CraError(
            f"«{operacao}» não é operação da CRA. As que existem são "
            f"{', '.join(sorted(OPERACOES))}.")
    onde = str(ambiente or "").strip().upper() or CRED.PRODUCAO
    texto = _bater(onde, qual, valores, pasta=pasta)
    return ler_resposta(texto, o_que or f"chamar {qual}")


# ------------------------------------------------- o que se BAIXA da CRA
#
# **NADA AQUI INTERPRETA ARQUIVO.** O que volta vai para `protesto_arquivo`,
# `protesto_remessa` e `protesto_desistencia`, que já leem os cinco layouts.


def apresentantes(ambiente: Any = CRED.PRODUCAO, *, pasta=None) -> str:
    """A lista de apresentantes. **É a única operação SEM PARÂMETRO NENHUM**,
    e por isso é ela que serve de teste de conexão."""
    return chamar("BuscarApresentante", ambiente,
                  o_que="buscar os apresentantes", pasta=pasta)


def _remessa_ou_aviso(texto: str) -> str:
    """A CRA também responde com relatório/erro em HTTP 200, sem títulos.

    Esse aviso deve chegar à tela antes do conferidor XML: um relatório
    não é uma remessa malformada. Não repete a chamada nem recebe títulos.
    """
    aviso = recusa_no_return(texto)
    if aviso:
        raise CraRecusou(f"A CRA informou: {aviso}")
    return texto


def remessa(nome_do_arquivo: str, ambiente: Any = CRED.PRODUCAO, *,
            com_imagem: bool = False, pasta=None) -> str:
    """A remessa do dia, **mais as pendentes de datas anteriores**.

    **`userArq` É O NOME DO ARQUIVO, E NÃO O CONTEÚDO** — medido na página
    *Download e Consulta* do manual («Nome do arquivo no formato FEBRABAN») e
    confirmado pelo exemplo em PHP. Mandar o conteúdo aqui seria mandar
    megabytes onde a Central espera onze caracteres.
    """
    texto = chamar("Remessa", ambiente, o_que="baixar a remessa", pasta=pasta,
                  userArq=_nome(nome_do_arquivo),
                  downloadImagem=(BAIXAR_A_IMAGEM if com_imagem
                                  else SO_CONFERIR_A_IMAGEM))
    return _remessa_ou_aviso(texto)


def remessas_pendentes(nome_do_arquivo: str = "",
                       ambiente: Any = CRED.PRODUCAO, *,
                       com_imagem: bool = False, pasta=None) -> str:
    """Todas as pendentes, de qualquer data e apresentante.

    A CRA exige um nome FEBRABAN válido mesmo nesta operação, que não filtra
    por data nem apresentante. Geramos esse nome técnico quando não informado.
    Contrato: manual.p21website.com.br/docs/cartorio/cartorios-webservice/
    download-e-consulta/ (exemplo oficial com apresentante 000).
    """
    nome = str(nome_do_arquivo or "").strip()
    if not nome:
        nome = f"B000{_date.today():%d%m.%y}1"
    texto = chamar("RemessaPendente", ambiente,
                  o_que="baixar as remessas pendentes", pasta=pasta,
                  userArq=_nome(nome),
                  downloadImagem=(BAIXAR_A_IMAGEM if com_imagem
                                  else SO_CONFERIR_A_IMAGEM))
    return _remessa_ou_aviso(texto)


def desistencias(nome_do_arquivo: str, ambiente: Any = CRED.PRODUCAO, *,
                 pasta=None) -> str:
    """As desistências do dia e as pendentes.

    O nome do arquivo de desistência começa com **`DP`** — medido no manual.
    """
    return chamar("Desistencia", ambiente, o_que="baixar as desistências",
                  pasta=pasta, userArq=_nome(nome_do_arquivo))


def cancelamentos(nome_do_arquivo: str, ambiente: Any = CRED.PRODUCAO, *,
                  com_imagem: bool = False, pasta=None) -> str:
    """Os cancelamentos do dia e os pendentes."""
    return chamar("Cancelamento", ambiente, o_que="baixar os cancelamentos",
                  pasta=pasta, userArq=_nome(nome_do_arquivo),
                  downloadImagem=(BAIXAR_A_IMAGEM if com_imagem
                                  else SO_CONFERIR_A_IMAGEM))


def autorizacoes(nome_do_arquivo: str, ambiente: Any = CRED.PRODUCAO, *,
                 com_imagem: bool = False, pasta=None) -> str:
    """As autorizações — **de retirada e de cancelamento**.

    O nome começa com **`AC`** ou **`AD`**, e o atributo `t07` diz o tipo:
    **`C`** cancelamento, **`S`** retirada. **O que a letra `S` abrevia não
    está medido** — o manual só dá as letras, e supor «sustação» seria dar
    nome jurídico a uma letra.
    """
    return chamar("Autorizacao", ambiente, o_que="baixar as autorizações",
                  pasta=pasta, userArq=_nome(nome_do_arquivo),
                  downloadImagem=(BAIXAR_A_IMAGEM if com_imagem
                                  else SO_CONFERIR_A_IMAGEM))


def ordem_de_cancelamento(nome_do_arquivo: str,
                          ambiente: Any = CRED.PRODUCAO, *,
                          pasta=None) -> str:
    """A ordem de cancelamento."""
    return chamar("OrdemCancelamento", ambiente,
                  o_que="baixar a ordem de cancelamento", pasta=pasta,
                  userArq=_nome(nome_do_arquivo))


def enviar_confirmacao(nome_do_arquivo: str, conteudo: str,
                       ambiente: Any = CRED.PRODUCAO, *, pasta=None) -> str:
    """Envia a confirmação do recebimento.

    **Medido em homologação (30/09/2026):** ``userArq`` é o nome FEBRABAN e
    ``userDados`` é o arquivo inteiro — o mesmo que ``protesto_remessa`` já
    grava em ``pt_retornos``.
    """
    if not str(conteudo or "").strip():
        raise CraError(
            "A confirmação está vazia — gere de novo a partir da remessa "
            "recebida antes de enviar à CRA.")
    return chamar("Confirmacao", ambiente, o_que="enviar a confirmação",
                  pasta=pasta, userArq=_nome(nome_do_arquivo),
                  userDados=str(conteudo))


def enviar_retorno(nome_do_arquivo: str, conteudo: str,
                   ambiente: Any = CRED.PRODUCAO, *, pasta=None) -> str:
    """Envia retorno ou andamento (operacao SOAP ``Retorno``).

    **Medido em homologação (30/09/2026):** mesmo contrato da confirmação —
    nome em ``userArq``, conteúdo em ``userDados``.
    """
    if not str(conteudo or "").strip():
        raise CraError(
            "O retorno está vazio — gere o arquivo antes de enviar à CRA.")
    return chamar("Retorno", ambiente, o_que="enviar o retorno",
                  pasta=pasta, userArq=_nome(nome_do_arquivo),
                  userDados=str(conteudo))


def consultar_slip(protocolo: str, data_do_protocolo: str,
                   ambiente: Any = CRED.PRODUCAO, *, pasta=None) -> str:
    """O slip de um protocolo."""
    if not (str(protocolo or "").strip()
            and str(data_do_protocolo or "").strip()):
        raise CraError("Informe o protocolo e a data do protocolo.")
    return chamar("ConsultaSlip", ambiente, o_que="consultar o slip",
                  pasta=pasta, protocolo=str(protocolo).strip(),
                  dataProtocolo=str(data_do_protocolo).strip())


def consultar_autorizacao(nome_do_arquivo: str, protocolo: str,
                          data_do_protocolo: str,
                          ambiente: Any = CRED.PRODUCAO, *,
                          marcar_baixado: bool = False, pasta=None) -> str:
    """Uma autorização.

    **CONSULTAR MARCA COMO BAIXADA, SALVO SE SE DISSER QUE NÃO** — medido no
    manual. Por isso o padrão aqui é **não marcar**: uma consulta que muda o
    estado do lado de lá não pode ser o comportamento silencioso de um botão
    de olhar. Quem quiser marcar, marca de propósito.
    """
    return chamar("ConsultaAutorizacao", ambiente,
                  o_que="consultar a autorização", pasta=pasta,
                  userArq=str(nome_do_arquivo or "").strip(),
                  protocolo=str(protocolo or "").strip(),
                  dataProtocolo=str(data_do_protocolo or "").strip(),
                  marcarBaixado=("1" if marcar_baixado else "0"))


def consultar_imagem(*, nosso_numero: str = "", numero_titulo: str = "",
                     documento_devedor: str = "", saldo: str = "",
                     vencimento: str = "", remessa_: str = "",
                     ambiente: Any = CRED.PRODUCAO, pasta=None) -> str:
    """A imagem de um título, achada pelos seis campos do contrato."""
    return chamar("ConsultaImagem", ambiente, o_que="consultar a imagem",
                  pasta=pasta, nossoNumero=str(nosso_numero or "").strip(),
                  numeroTitulo=str(numero_titulo or "").strip(),
                  documentoDevedor=str(documento_devedor or "").strip(),
                  saldoTitulo=str(saldo or "").strip(),
                  vencimento=str(vencimento or "").strip(),
                  remessa=str(remessa_ or "").strip())


def autorizacoes_do_periodo(*, solicitacao_de: str = "",
                            solicitacao_ate: str = "", remessa_de: str = "",
                            remessa_ate: str = "",
                            ambiente: Any = CRED.PRODUCAO,
                            pasta=None) -> str:
    """As autorizações por período — de solicitação e de remessa."""
    return chamar("ConsultaAutorizacoesPeriodo", ambiente,
                  o_que="consultar as autorizações do período", pasta=pasta,
                  dataInicioSolicitacao=str(solicitacao_de or "").strip(),
                  dataFimSolicitacao=str(solicitacao_ate or "").strip(),
                  dataInicioRemessa=str(remessa_de or "").strip(),
                  dataFimRemessa=str(remessa_ate or "").strip())


def _nome(valor: Any) -> str:
    """O nome do arquivo, conferido — **é nome, e não conteúdo**.

    Um `userArq` de mil caracteres é quase certamente alguém tendo mandado o
    arquivo inteiro, e a recusa aqui custa menos que a viagem até a Central.
    """
    nome = str(valor or "").strip()
    if not nome:
        raise CraError(
            "Informe o NOME do arquivo, no formato FEBRABAN — por exemplo "
            "«C0013110.141». A CRA espera o nome, e não o conteúdo.")
    if len(nome) > 60 or "\n" in nome:
        raise CraError(
            f"«{nome[:40]}…» não parece nome de arquivo. A CRA espera o NOME "
            f"no formato FEBRABAN, e não o conteúdo dele.")
    return nome


def diagnostico(ambiente: Any = CRED.PRODUCAO, *, pasta=None) -> dict:
    """Tenta falar com a CRA e diz o que aconteceu. **Não baixa nem envia.**

    **USA `BuscarApresentante`, que é a única operação sem parâmetro nenhum** —
    e por isso a única que testa a conexão e a credencial sem afirmar nada
    sobre arquivo. Um teste que pedisse uma remessa marcaria a remessa como
    baixada do lado de lá.
    """
    qual = str(ambiente or "").strip().upper() or CRED.PRODUCAO
    if not CRED.tem(CRED.CRA, qual, pasta):
        return {"ok": False, "ambiente": qual,
                "motivo": (
                    "A credencial da CRA ainda não foi informada"
                    + (" para a PRODUÇÃO — é a única que o sistema usa desde "
                       "14/10/2026. Informe-a em Administrativo → "
                       "Configurações → Centrais." if qual == CRED.PRODUCAO
                       else "."))}
    try:
        resposta = apresentantes(qual, pasta=pasta)
    except CraError as erro:
        return {"ok": False, "ambiente": qual, "motivo": str(erro)}
    recusa = recusa_no_return(resposta)
    if recusa:
        return {"ok": False, "ambiente": qual,
                "motivo": (
                    "A CRA recusou ao buscar os apresentantes: "
                    f"{recusa} Confira o usuário e a senha de "
                    f"{'produção' if qual == CRED.PRODUCAO else qual.lower()} "
                    "em Administrativo → Configurações → Centrais de Protesto.")}
    return {"ok": True, "ambiente": qual,
            "endereco": endereco_do_ambiente(qual),
            "tamanho": len(resposta),
            "motivo": (f"Falou com a CRA e recebeu a lista de apresentantes "
                       f"({len(resposta)} caracteres).")}
