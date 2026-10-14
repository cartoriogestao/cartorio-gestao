"""O TRANSPORTE DO SIRC — o caminho por usuário e senha, sem A3.

Construído em 14/09/2026, depois do envelope (`sirc_remessa.py`) e da
correção do que este projeto acreditava sobre a API — ver
`sirc_api_nao_exige_a3` na memória: há DOIS Web Services, e só um deles
(`/SircWs/MovimentoCertificadoDigital`) exige certificado A3. Este módulo
fala com o outro, `/SircWs/Movimento`, cujo WSDL é **público** e foi lido
sem credencial nenhuma (`FONTES_EXTERNAS/sirc/Movimento.wsdl`).

**O CONTRATO É SOAP 1.2, DOCUMENT/LITERAL — NÃO É O `rpc/encoded` DA CRA.**
Cada operação recebe um elemento único, nomeado como ela mesma
(`enviarMovimentoObito`, por exemplo), com os campos **por nome** — e não
posicionais como no `rpc/encoded` da CRA21. Isso tira uma classe inteira de
erro (trocar a ordem dos parâmetros), mas não dispensa nada do resto.

**SÃO NOVE OPERAÇÕES, MEDIDAS NO PRÓPRIO WSDL — não oito, não dez:**

    enviarMovimentoNascimento / validarMovimentoNascimento
    enviarMovimentoCasamento  / validarMovimentoCasamento
    enviarMovimentoObito      / validarMovimentoObito
    enviarMovimentoCancelamento / validarMovimentoCancelamento
    declararInexistenciaMovimento

**NÃO HÁ OPERAÇÃO PRÓPRIA DE NATIMORTO.** Medido no WSDL: só nascimento,
casamento, óbito e cancelamento têm par enviar/validar. Isso não é lacuna
deste módulo — o manual (seção 5.4) diz por quê: um natimorto se manda
pela MESMA operação do óbito, com o `tipoLivro` valendo `"5"` dentro do
XML, e não por uma operação com nome próprio. `sirc_remessa.py` monta o
mesmo `registroObitoInclusao` para as duas espécies (ver
`PAPEL_PRINCIPAL_DO_OBITO`), e este módulo despacha as duas para
`enviarMovimentoObito`/`validarMovimentoObito`.

**TODA OPERAÇÃO RECEBE `{cns, usuario, senha, conteudo}`, E NÃO HTTP
BASIC.** É a diferença que separa este cliente do da CRA21: lá a senha vai
no cabeçalho HTTP; aqui ela vai **dentro do corpo XML**, como qualquer
outro campo. Por isso forçar HTTPS aqui pesa ainda mais — em texto puro, a
senha viajaria dentro do próprio envelope, legível por qualquer um na rede.

**O WSDL DECLARA `http://`, SEM O S — e o sistema recusa, como na CRA21.**
`<soap12:address location="http://sirc.dataprev.gov.br:80/SircWs/Movimento"/>`
é o que o contrato diz; o host responde em `https://` também (medido em
14/09/2026), e é isso que este módulo usa, sempre.

**O QUE VOLTA É `<resultado>`, EM TODAS AS NOVE** — as respostas são
`{operacao}Response` com um campo `resultado` só, string. O manual não
descreve o VOCABULÁRIO desse texto (não há enum nem exemplo de sucesso ou
recusa no contrato) — por isso este módulo **não interpreta** o conteúdo de
`resultado`: devolve-o cru, para quem chamar decidir o que fazer com ele.
Interpretar sem ter medido seria inventar significado.

**A FALHA SOAP NÃO TEM CAMPO PRÓPRIO** — `SircWebServiceFault` é um
`xsd:sequence` **vazio**: o motivo da recusa vem só no
`soap:Fault/soap:Reason/soap:Text` do envelope, no formato padrão do SOAP
1.2, e não num campo custom que este módulo pudesse ler.

**ESTE MÓDULO NÃO MONTA O ENVELOPE DA REMESSA** — quem faz isso é
`sirc_remessa.montar()`; aqui só se transporta o que já saiu de lá
(`conteudo`, o XML de um lote inteiro).

**O TRANSPORTE É O COMUM DAS CENTRAIS desde 05/10/2026, marco (c)** —
`centrais_http.requisitar(...)`, como a CENPROT e a CRA21 no marco (b). As
regras deste módulo continuam as mesmas: https forçado, certificado
conferido (só as cifras antigas liberadas, ver `_contexto_tls`), envio que
**não se repete sozinho** (POST, sem `retentar_escrita`), o minuto entre
envios e as mesmas frases para o balcão. O `User-Agent` deixou de levar o
CNS da serventia (o CNS vai no corpo, como o contrato manda). **Cada
chamada fica no log das Centrais** (`centrais_log.anotar_resposta`), só com
a operação, o status, a duração e as tentativas — nunca a senha, que viaja
DENTRO do corpo, nem o lote.

**NÃO HÁ FILA NEM TESTE DE CONEXÃO EM HOMOLOGAÇÃO PARA O SIRC** — e não é
esquecimento: a Central tem um ambiente só, o de produção
(`centrais_cred.AMBIENTES_DA_CENTRAL[SIRC]`). Até um `validarMovimento*` é
uma chamada real à Dataprev com a senha da serventia. A fila comum
(`protesto_centrais_fila`) só aceita homologação, e por isso o SIRC fica
fora dela: o botão da tela continua sendo o único caminho, clicado por
quem decide.
"""
from __future__ import annotations

import http.client  # noqa: F401 — os testes antigos trocam a conexão por aqui
import re
import ssl
import time
import urllib.parse
from typing import Any
from xml.sax import saxutils

import centrais_cred as CRED
import centrais_http as HTTP
import centrais_log as LOG
import sirc_remessa as SIRC

# O NOME DA CENTRAL NO LOG das Centrais (`centrais_log`) — o mesmo do cofre.
CENTRAL_NO_LOG = CRED.SIRC

NAMESPACE = "http://dataprev.gov.br/sirc"

# **O ENDEREÇO É UM SÓ, E É O QUE O WSDL DECLARA — com o `https` forçado.**
# Não há um segundo endereço de homologação: `centrais_cred.AMBIENTES_DA_
# CENTRAL[SIRC]` já declara que só existe `PRODUCAO`, e é esse o único
# ambiente que este módulo aceita.
ENDERECO = "https://sirc.dataprev.gov.br/SircWs/Movimento"

# AS NOVE OPERAÇÕES, medidas no WSDL público. Todas recebem os MESMOS quatro
# campos — não há parâmetro que varie por operação, ao contrário da CRA21.
OPERACOES: tuple[str, ...] = (
    "enviarMovimentoNascimento", "validarMovimentoNascimento",
    "enviarMovimentoCasamento", "validarMovimentoCasamento",
    "enviarMovimentoObito", "validarMovimentoObito",
    "enviarMovimentoCancelamento", "validarMovimentoCancelamento",
    "declararInexistenciaMovimento",
)

# **A ESPÉCIE DECIDE A OPERAÇÃO, NA MESMA CHAVE QUE `sirc_remessa` JÁ USA.**
# Não há operação PRÓPRIA de NATIMORTO no WSDL — só nascimento, casamento e
# óbito —, e o manual (seção 5.4) diz por quê: um natimorto se manda pela
# MESMA operação do óbito, com `tipoLivro="5"` dentro do XML — não é
# lacuna deste cliente, é o que a Central realmente oferece.
OPERACAO_DE_ENVIO_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "enviarMovimentoNascimento",
    "CASAMENTO": "enviarMovimentoCasamento",
    "CASAMENTO_RELIGIOSO": "enviarMovimentoCasamento",
    "OBITO": "enviarMovimentoObito",
    "NATIMORTO": "enviarMovimentoObito",
}
OPERACAO_DE_VALIDACAO_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "validarMovimentoNascimento",
    "CASAMENTO": "validarMovimentoCasamento",
    "CASAMENTO_RELIGIOSO": "validarMovimentoCasamento",
    "OBITO": "validarMovimentoObito",
    "NATIMORTO": "validarMovimentoObito",
}

PRAZO_PADRAO = 120

# **«NO MÍNIMO 1 MINUTO ENTRE ENVIOS»** — o manual (seção 3) declara isso
# para o arquivo baixado à mão, e `sirc_remessa.INTERVALO_MINIMO_SEGUNDOS`
# já existia como constante — mas **nunca foi imposto em lugar nenhum**.
# Enquanto só havia botão de BAIXAR, o próprio ritmo humano de subir no
# SIRC-Web garantia o intervalo; desde que este módulo manda de verdade, um
# clique duplo ou dois lotes seguidos poderiam furar o minuto sem que
# ninguém percebesse — e a Central pune a informação inexata, não é
# provável que ela ignore ritmo demais. Reaproveita a constante de
# `sirc_remessa` em vez de duplicá-la — duas constantes do mesmo número
# divergem no primeiro conserto. `_ULTIMO_ENVIO` é por PROCESSO (reinicia
# com o servidor, e está certo assim: não há envio anterior para lembrar
# de um processo que acabou de subir).
_ULTIMO_ENVIO: float | None = None


class SircClienteError(RuntimeError):
    """Falha de transporte ou de credencial, com a frase para o balcão."""


class SircRecusou(SircClienteError):
    """A Central respondeu, e respondeu não. O motivo dela vem junto."""


def _partes_https(endereco: str) -> tuple[str, int, str]:
    p = urllib.parse.urlsplit(endereco)
    if p.scheme != "https":
        # **O WSDL DECLARA `http://`, SEM O S** — a mesma armadilha que a
        # CRA21 já tinha. Aqui pesa mais: a senha viaja DENTRO do corpo XML,
        # e não num cabeçalho HTTP Basic — em texto puro, ela ficaria
        # legível para qualquer um na rede.
        raise SircClienteError(
            f"O endereço do SIRC tem de ser https, e veio «{endereco}». O "
            f"WSDL declara http:// sem o S, e a senha do cartório viaja "
            f"dentro do próprio envelope — o sistema recusa de propósito.")
    return p.hostname or "", p.port or 443, p.path or "/"


def envelope(operacao: str, *, cns: str, usuario: str, senha: str,
            conteudo: str) -> bytes:
    """O envelope SOAP 1.2 document/literal daquela operação.

    **OS CAMPOS SÃO POR NOME, NÃO POSICIONAIS** — a diferença que separa
    este contrato do `rpc/encoded` da CRA21. E **todo valor vai escapado**:
    `conteudo` é o XML do lote inteiro, cheio de `<` e `&` de sobra, e um
    escape que faltasse quebraria o envelope externo.
    """
    if operacao not in OPERACOES:
        raise SircClienteError(
            f"«{operacao}» não é operação do SIRC. As que existem são "
            f"{', '.join(OPERACOES)}.")
    corpo = (
        f"<cns>{saxutils.escape(str(cns))}</cns>"
        f"<usuario>{saxutils.escape(str(usuario))}</usuario>"
        f"<senha>{saxutils.escape(str(senha))}</senha>"
        f"<conteudo>{saxutils.escape(str(conteudo))}</conteudo>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">'
        '<soap:Body>'
        f'<{operacao} xmlns="{NAMESPACE}">{corpo}</{operacao}>'
        '</soap:Body></soap:Envelope>'
    ).encode()


_RESULTADO = re.compile(r"<(?:\w+:)?resultado[^>]*>(.*?)</(?:\w+:)?resultado>",
                        re.DOTALL)
# **SOAP 1.2, E NÃO `<faultstring>` DO 1.1** — a mensagem mora em
# `soap:Reason/soap:Text`, e `SircWebServiceFault` (o tipo que o WSDL
# declara para a falha) é um `xsd:sequence` VAZIO: não há campo próprio
# nenhum para ler.
_FALHA = re.compile(r"<(?:\w+:)?Text[^>]*>(.*?)</(?:\w+:)?Text>", re.DOTALL)


def ler_resposta(texto: str, o_que: str) -> str:
    """O `<resultado>` da resposta, ou a frase do balcão. Não interpreta o
    conteúdo — o manual não descreve o vocabulário dele."""
    falha = _FALHA.search(texto)
    if falha:
        raise SircRecusou(
            f"O SIRC recusou ao {o_que}: {saxutils.unescape(falha.group(1))}")
    achado = _RESULTADO.search(texto)
    if achado is None:
        raise SircRecusou(
            f"O SIRC respondeu ao {o_que} sem o «resultado» esperado. "
            f"Resposta: {texto[:300]}")
    return saxutils.unescape(achado.group(1))


def _contexto_tls() -> ssl.SSLContext:
    """O contexto TLS da casa (`centrais_http.contexto_tls`), com as cifras
    antigas que o servidor do SIRC entende.

    **O SERVIDOR DO SIRC É ANTIGO** (Oracle HTTP Server/Web Cache 11g,
    de ~2011, medido no cabeçalho `Server` da resposta em 14/09/2026) —
    o handshake TLS falha com `SSLZeroReturnError` (EOF) contra o
    `SECLEVEL` padrão do OpenSSL 1.1.1+ desta máquina, mesmo com o
    certificado válido (`*.dataprev.gov.br`, real, dentro da validade).
    **NÃO É DESLIGAR VERIFICAÇÃO** — o certificado continua conferido
    (`check_hostname`/`verify_mode` seguem o padrão, e o TLS mínimo continua
    1.2, como já era no `create_default_context()` do Python 3.11); só a
    lista de cifras aceita as mais antigas que este servidor entende.
    Medido: sem isto, `curl` (que usa o schannel do Windows, não o OpenSSL)
    fala com o servidor normalmente — a diferença é só da biblioteca TLS,
    não da rede nem da Central.
    """
    contexto = HTTP.contexto_tls()
    contexto.set_ciphers("DEFAULT@SECLEVEL=1")
    return contexto


def _bater(operacao: str, *, cns: str, conteudo: str,
          prazo: int = PRAZO_PADRAO, pasta: Any = None) -> str:
    """Uma chamada SOAP pelo transporte comum. Devolve o texto cru da resposta.

    **A CREDENCIAL VAI NO CORPO, NÃO NO CABEÇALHO HTTP** — por isso ela sai
    daqui, e nunca aparece em mensagem de erro nem em log: um erro que
    ecoasse o corpo da REQUISIÇÃO vazaria a senha junto.

    **RECUSA ANTES DE ABRIR CONEXÃO SE O MINUTO NÃO PASSOU** — o manual
    exige o intervalo entre envios, e esta é a única barreira que impede
    dois lotes seguidos (ou um clique duplo) de furá-lo. **Vem DEPOIS da
    credencial**, de propósito: sem credencial não há chamada real de
    qualquer forma, e é a credencial que a tela precisa apontar primeiro.
    """
    usuario, senha = CRED.credencial(CRED.SIRC, CRED.PRODUCAO, pasta)
    global _ULTIMO_ENVIO
    minimo = SIRC.INTERVALO_MINIMO_SEGUNDOS
    if _ULTIMO_ENVIO is not None:
        passado = time.monotonic() - _ULTIMO_ENVIO
        if passado < minimo:
            faltam = int(minimo - passado) + 1
            raise SircClienteError(
                f"O manual do SIRC exige pelo menos {minimo} segundos "
                f"entre um envio e outro. Espere mais {faltam} "
                f"segundo(s) e tente de novo; nada foi enviado agora.")
    hospedeiro, _porta, _caminho = _partes_https(ENDERECO)
    corpo = envelope(operacao, cns=cns, usuario=usuario, senha=senha,
                     conteudo=conteudo)
    cabecas = {
        # SOAP 1.2 leva a `action` dentro do Content-Type, e não num
        # cabeçalho `SOAPAction` à parte — e o WSDL declara `soapAction=""`
        # nas nove operações. O `Content-Length` quem põe é o `http.client`;
        # o `User-Agent` é o do transporte comum, SEM o CNS da serventia
        # (marco c, 05/10/2026: dado da casa não se escreve no código, e o
        # CNS já vai dentro do envelope, onde o contrato pede).
        "Content-Type": 'application/soap+xml; charset=utf-8; action=""',
        "Accept": "application/soap+xml, text/xml",
    }
    # **O RELÓGIO CONTA DAQUI, E NÃO DO SUCESSO** — mesmo uma chamada que
    # falhe na rede já ocupou a conexão da Central; deixar só o sucesso
    # marcar o relógio deixaria um erro seguido de retentativa imediata
    # furar o intervalo.
    _ULTIMO_ENVIO = time.monotonic()
    try:
        # **O TRANSPORTE COMUM DAS CENTRAIS** (marco c, 05/10/2026). POST e
        # `tentativas=0`: enviar lote ao INSS NÃO se repete sozinho — uma
        # repetição cega, depois de um envio que chegou mas cuja resposta
        # se perdeu, mandaria o mesmo lote duas vezes.
        resposta = HTTP.requisitar(
            "POST", ENDERECO, corpo=corpo, cabecalhos=cabecas, prazo=prazo,
            tentativas=0, contexto=_contexto_tls())
    except HTTP.CentralHttpError as erro:
        LOG.anotar_resposta(CENTRAL_NO_LOG, operacao, erro,
                            ambiente=CRED.PRODUCAO)
        raise SircClienteError(
            f"Não consegui falar com o SIRC em {hospedeiro}: "
            f"{erro.causa or erro}. Confira a internet da serventia e tente "
            f"de novo; nada foi considerado enviado.") from erro
    # O log leva só operação, status, duração e tentativas — a senha mora
    # no CORPO da requisição, e o corpo não entra no log de jeito nenhum.
    LOG.anotar_resposta(CENTRAL_NO_LOG, operacao, resposta,
                        ambiente=CRED.PRODUCAO)
    texto = resposta.como_dict()["texto"]
    if len(texto) >= HTTP.LIMITE_DO_CORPO_NO_TEXTO:
        # `texto` do transporte comum é cortado em 2 MB; a resposta do SIRC
        # é pequena, mas `ler_resposta` precisa do envelope INTEIRO para
        # achar o `</resultado>` — sem corte calado.
        texto = resposta.corpo.decode("utf-8", errors="replace")
    return texto


def enviar(especie: str, conteudo: str, *, cns: str,
          prazo: int = PRAZO_PADRAO, pasta: Any = None) -> str:
    """Manda o lote (o XML de `sirc_remessa.montar()`) para a operação
    `enviarMovimento<Espécie>` certa. Devolve o `<resultado>` cru."""
    tipo = str(especie or "").strip().upper()
    operacao = OPERACAO_DE_ENVIO_DA_ESPECIE.get(tipo)
    if operacao is None:
        raise SircClienteError(
            f"O SIRC não tem operação de envio para «{especie}». As que "
            f"existem são {', '.join(sorted(OPERACAO_DE_ENVIO_DA_ESPECIE))}.")
    texto = _bater(operacao, cns=cns, conteudo=conteudo, prazo=prazo,
                   pasta=pasta)
    return ler_resposta(texto, f"enviar o lote de {tipo.lower()}")


def validar(especie: str, conteudo: str, *, cns: str,
           prazo: int = PRAZO_PADRAO, pasta: Any = None) -> str:
    """Confere o lote sem enviá-lo de verdade — `validarMovimento<Espécie>`,
    a operação irmã de `enviar()`. Mesma credencial, mesma forma."""
    tipo = str(especie or "").strip().upper()
    operacao = OPERACAO_DE_VALIDACAO_DA_ESPECIE.get(tipo)
    if operacao is None:
        raise SircClienteError(
            f"O SIRC não tem operação de validação para «{especie}». As "
            f"que existem são "
            f"{', '.join(sorted(OPERACAO_DE_VALIDACAO_DA_ESPECIE))}.")
    texto = _bater(operacao, cns=cns, conteudo=conteudo, prazo=prazo,
                   pasta=pasta)
    return ler_resposta(texto, f"validar o lote de {tipo.lower()}")


def declarar_inexistencia(conteudo: str, *, cns: str,
                          prazo: int = PRAZO_PADRAO, pasta: Any = None) -> str:
    """Manda a declaração de mês sem movimento (`sirc_remessa.
    declaracao_de_inexistencia()`) pela operação `declararInexistenciaMovimento`."""
    texto = _bater("declararInexistenciaMovimento", cns=cns,
                   conteudo=conteudo, prazo=prazo, pasta=pasta)
    return ler_resposta(texto, "declarar a inexistência de movimento")


def enviar_cancelamento(conteudo: str, *, cns: str,
                        prazo: int = PRAZO_PADRAO, pasta: Any = None) -> str:
    """Manda o `movimentoCancelamentoTO` (`sirc_remessa.
    montar_cancelamento()`) pela operação `enviarMovimentoCancelamento`.

    **NÃO É UM `enviar()` DE ESPÉCIE** — cancelamento de termo não é uma
    das sete coisas do art. 225, e por isso não passa por
    `OPERACAO_DE_ENVIO_DA_ESPECIE`: tem operação e envelope PRÓPRIOS
    (`movimentoCancelamentoTO`, versão "1.1"), mesma credencial e mesmo
    transporte SOAP das outras oito."""
    texto = _bater("enviarMovimentoCancelamento", cns=cns, conteudo=conteudo,
                   prazo=prazo, pasta=pasta)
    return ler_resposta(texto, "enviar o cancelamento de termo")


def validar_cancelamento(conteudo: str, *, cns: str,
                        prazo: int = PRAZO_PADRAO, pasta: Any = None) -> str:
    """A operação irmã de `enviar_cancelamento()` — confere sem enviar."""
    texto = _bater("validarMovimentoCancelamento", cns=cns, conteudo=conteudo,
                   prazo=prazo, pasta=pasta)
    return ler_resposta(texto, "validar o cancelamento de termo")
