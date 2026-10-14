"""O CLIENTE HTTP COMUM DAS CENTRAIS — o transporte, e só ele.

Construído em 05/10/2026, marco (a) da base comum das integrações. **Dono:
RCPN/Protesto**, que cria e mantém; **Notas e Registro de Imóveis consomem**
(e depois migram `onr_api`/`cnib_api` para cá). O contrato público está em
`DOCUMENTACAO/CENTRAIS_BASE_COMUM.md`.

**POR QUE EXISTE.** Cada `*_api.py` desta casa monta o próprio
`http.client.HTTPSConnection` + `ssl.create_default_context()` + laço de
retentativa — `cenprot_api._bater`, `cra21_api._bater`, `onrtdpj_api._bater`
e outros, todos parecidos e nenhum igual. É a lição da `normalizar_nome`: o
mesmo pedaço escrito cinco vezes diverge no primeiro conserto. **Este módulo
NÃO migra os existentes agora** — ele oferece a API limpa, e quem for tocado
na próxima etapa (b: CENPROT/CRA21) passa a usá-lo.

**AS REGRAS QUE ELE CARREGA, e que os `_bater` já carregavam um a um:**

  - **HTTPS não é opcional.** Credencial e token viajam nesta conexão. A única
    exceção é `http://` para `127.0.0.1`/`localhost` com `permitir_http_local`
    — os simuladores locais (`:8912` da Resolve, por exemplo).
  - **A validação de TLS é a NORMAL** (cadeia do sistema, TLS 1.2 no mínimo),
    e não certificado fixado: fixar faria o sistema parar no dia em que a
    Central renovasse o certificado. Quem fixa é o selador, que é aparelho da
    rede local — outro caso.
  - **Retentar só o que não chegou.** Falha de transporte num `GET` se tenta
    de novo; num `POST` não, a menos que quem chama diga
    `retentar_escrita=True` (operação idempotente declarada pelo contrato).
    Aprovar a mesma anuência duas vezes é um ato a mais na Central.
  - **4xx/5xx não estoura.** A resposta volta com o `status`, e quem decide o
    que fazer com um 404 é quem chamou. Só a falha de TRANSPORTE estoura
    (`CentralHttpError`), com a frase pronta para o balcão.
  - **Nada de CNS, CNPJ, nome ou IP da serventia escrito aqui.** O
    `User-Agent` leva só o nome do sistema; quem quiser identificar a
    serventia passa o valor lido da configuração (`settings`).
  - **A chamada nunca acontece dentro de `db.transaction()`** — por isso
    nenhuma função daqui recebe `con`. O log em banco é de `centrais_log`,
    depois da chamada, em transação curta própria.

**O GANCHO DO CERTIFICADO CLIENTE** (mTLS) é `CertificadoCliente`: arquivo PEM
do certificado e da chave (A1 exportado), com senha opcional. **Certificado
A3 (token/cartão) não se carrega por aqui** — a chave não sai do aparelho;
para esse caso a casa tem `crc_a3`/`assinatura_digital`. A senha do PEM, se
houver, vem do cofre (`centrais_cred`) ou do `%PROGRAMDATA%`, nunca do repo.
"""
from __future__ import annotations

import http.client
import json
import socket
import ssl
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable

import centrais_trava_sandbox as TRAVA

# O QUE VALE QUANDO QUEM CHAMA NÃO DIZ. Números da casa: o `cenprot_api` usa
# 60 s porque pagina 1.000 por vez; aqui o padrão é 30, e quem pagina pede
# mais.
PRAZO_PADRAO = 30            # segundos, por tentativa
TENTATIVAS_PADRAO = 2        # retentativas ALÉM da primeira
ESPERA_BASE = 1.0            # segundos; espera = base * (n + 1)
LIMITE_DO_CORPO_NO_TEXTO = 2_000_000   # bytes decodificados em `texto`

# OS MÉTODOS QUE NÃO MUDAM NADA NA CENTRAL — os únicos que se retentam
# sozinhos. RFC 9110, «safe methods».
METODOS_QUE_SO_LEEM: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})

# STATUS QUE DIZEM «TENTE DE NOVO» — gateway e indisponibilidade. Só se
# retentam nos métodos de leitura (ou com `retentar_escrita`).
STATUS_TRANSITORIOS: frozenset[int] = frozenset({502, 503, 504})

# O NOME DO SISTEMA, e nada da serventia. Ver o cabeçalho.
USER_AGENT_PADRAO = "CartorioGestao"

HOSTS_LOCAIS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})


class CentralHttpError(RuntimeError):
    """Falha de TRANSPORTE (não chegou, TLS recusou, prazo estourou).

    A mensagem é a frase para o balcão. `tentativas` diz quantas se fizeram, e
    `causa` guarda o erro original para o log.
    """

    def __init__(self, mensagem: str, *, tentativas: int = 0,
                 causa: BaseException | None = None):
        super().__init__(mensagem)
        self.tentativas = tentativas
        self.causa = causa


@dataclass(frozen=True)
class CertificadoCliente:
    """O gancho do mTLS: certificado e chave em PEM, senha opcional.

    Só guarda os caminhos — quem carrega é `contexto_tls`. A senha não se
    escreve no código: lê-se do cofre na hora de montar.
    """
    arquivo_certificado: str
    arquivo_chave: str | None = None
    senha: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Resposta:
    """O que a Central respondeu. **Nunca estoura por 4xx/5xx.**"""
    status: int
    cabecalhos: dict
    corpo: bytes = field(repr=False)
    texto: str = field(repr=False)
    json: Any = field(repr=False)
    tentativas: int = 1
    duracao_ms: int = 0
    url: str = ""
    metodo: str = "GET"

    @property
    def ok(self) -> bool:
        """2xx. Só calcula."""
        return 200 <= self.status < 300

    def como_dict(self) -> dict:
        """O ADAPTADOR PARA O LEGADO: `{status, json, texto}`.

        É exatamente o que `cenprot_api._bater`, `cra21_api._bater` e
        `onrtdpj_api._bater` devolvem hoje — quem migrar troca o transporte
        sem mexer em `_resposta_ou_erro`.
        """
        return {"status": self.status, "json": self.json, "texto": self.texto}


def configuracao() -> dict:
    """Os números deste cliente, para o painel mostrar. Só calcula; sem segredo."""
    return {
        "prazo_padrao_s": PRAZO_PADRAO,
        "tentativas_padrao": TENTATIVAS_PADRAO,
        "espera_base_s": ESPERA_BASE,
        "tls_minimo": "TLS 1.2",
        "validacao": "cadeia do sistema (sem certificado fixado)",
        "retenta_sozinho": sorted(METODOS_QUE_SO_LEEM),
        "status_transitorios": sorted(STATUS_TRANSITORIOS),
        "openssl": ssl.OPENSSL_VERSION,
    }


def contexto_tls(certificado: CertificadoCliente | None = None, *,
                 arquivo_ca: str | None = None) -> ssl.SSLContext:
    """O contexto TLS da casa: cadeia normal, TLS 1.2+, mTLS opcional.

    `arquivo_ca` existe para os testes e para Central com AC própria
    declarada no contrato — **não** para desligar a validação. Não há
    parâmetro que desligue a validação, de propósito.
    """
    contexto = ssl.create_default_context(cafile=arquivo_ca)
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2
    if certificado is not None:
        try:
            contexto.load_cert_chain(certificado.arquivo_certificado,
                                     certificado.arquivo_chave,
                                     certificado.senha)
        except (OSError, ssl.SSLError) as erro:
            raise CentralHttpError(
                "Não consegui carregar o certificado cliente "
                f"«{certificado.arquivo_certificado}»: {erro}. Confira o "
                "arquivo e a senha; certificado A3 (token/cartão) não se "
                "carrega por aqui.", causa=erro) from erro
    return contexto


def _partes(url: str, permitir_http_local: bool) -> tuple[str, str, int, str]:
    """(esquema, host, porta, caminho+query). Recusa http fora do local."""
    p = urllib.parse.urlsplit(str(url or ""))
    host = p.hostname or ""
    if not host:
        raise CentralHttpError(f"Endereço sem host: «{url}».")
    if p.scheme == "https":
        porta = p.port or 443
    elif p.scheme == "http" and permitir_http_local and host in HOSTS_LOCAIS:
        porta = p.port or 80
    else:
        raise CentralHttpError(
            f"O endereço da Central tem de ser https, e veio «{url}». "
            "Credencial e token viajam nesta conexão.")
    caminho = (p.path or "/") + (f"?{p.query}" if p.query else "")
    return p.scheme, host, porta, caminho


def _abrir_conexao(esquema: str, host: str, porta: int, prazo: float,
                   contexto: ssl.SSLContext | None):
    """A conexão crua. Separada para os testes trocarem por uma falsa."""
    if esquema == "http":
        return http.client.HTTPConnection(host, porta, timeout=prazo)
    return http.client.HTTPSConnection(host, porta, timeout=prazo,
                                       context=contexto)


# O RELÓGIO DE ESPERA, trocável nos testes (sem dormir de verdade).
_dormir: Callable[[float], None] = time.sleep


def requisitar(metodo: str, url: str, *, corpo: bytes | str | None = None,
               cabecalhos: dict | None = None, json_corpo: Any = None,
               prazo: float = PRAZO_PADRAO,
               tentativas: int = TENTATIVAS_PADRAO,
               retentar_escrita: bool = False,
               certificado: CertificadoCliente | None = None,
               contexto: ssl.SSLContext | None = None,
               permitir_http_local: bool = False,
               user_agent: str = USER_AGENT_PADRAO) -> Resposta:
    """Uma requisição a uma Central, com TLS, prazo e retentativa básica.

    Devolve `Resposta` para QUALQUER status HTTP; estoura `CentralHttpError`
    só quando a resposta não chegou (depois das retentativas permitidas).

    `json_corpo` serializa em UTF-8 e põe `Content-Type: application/json`.
    `tentativas` é quantas vezes MAIS se tenta, além da primeira — e só vale
    para método de leitura, ou com `retentar_escrita=True`.
    """
    verbo = str(metodo or "GET").strip().upper()
    # Trava sandbox (05/10/2026): SIRC/CRC/ON-RCPN/Resolve nunca batem em producao.
    try:
        url = TRAVA.proteger_url(url)
    except TRAVA.SandboxTravaRecusou as erro:
        raise CentralHttpError(str(erro), causa=erro) from erro
    esquema, host, porta, caminho = _partes(url, permitir_http_local)
    cabecas = {"Accept": "application/json", "User-Agent": user_agent}
    if json_corpo is not None:
        corpo = json.dumps(json_corpo, ensure_ascii=False).encode("utf-8")
        cabecas["Content-Type"] = "application/json; charset=utf-8"
    elif isinstance(corpo, str):
        corpo = corpo.encode("utf-8")
    cabecas.update(cabecalhos or {})
    if esquema == "https" and contexto is None:
        contexto = contexto_tls(certificado)

    pode_retentar = verbo in METODOS_QUE_SO_LEEM or retentar_escrita
    limite = max(0, int(tentativas)) if pode_retentar else 0
    inicio = time.monotonic()
    ultimo: BaseException | None = None
    feitas = 0
    for n in range(limite + 1):
        feitas = n + 1
        conexao = None
        try:
            conexao = _abrir_conexao(esquema, host, porta, prazo, contexto)
            conexao.request(verbo, caminho, body=corpo, headers=cabecas)
            r = conexao.getresponse()
            bruto = r.read()
            status = int(r.status)
            if status in STATUS_TRANSITORIOS and n < limite:
                ultimo = None
                _dormir(ESPERA_BASE * (n + 1))
                continue
            # **O JSON SE LÊ DO CORPO INTEIRO; só o `texto` é cortado**
            # (marco b, 05/10/2026). Lido do texto cortado, um JSON grande —
            # os PDFs em base64 de `/anuencia/arquivos` da CENPROT — virava
            # `None` calado, e a tela diria «sem arquivo».
            inteiro = bruto.decode("utf-8", errors="replace")
            texto = inteiro[:LIMITE_DO_CORPO_NO_TEXTO]
            try:
                como_json = json.loads(inteiro) if inteiro.strip() else None
            except ValueError:
                como_json = None
            return Resposta(
                status=status,
                cabecalhos={k.lower(): v for k, v in r.getheaders()},
                corpo=bruto, texto=texto, json=como_json, tentativas=feitas,
                duracao_ms=int((time.monotonic() - inicio) * 1000),
                url=f"{esquema}://{host}:{porta}{caminho.split('?')[0]}",
                metodo=verbo)
        except (OSError, socket.timeout, ssl.SSLError,
                http.client.HTTPException) as erro:
            ultimo = erro
            if n >= limite:
                break
            _dormir(ESPERA_BASE * (n + 1))
        finally:
            if conexao is not None:
                try:
                    conexao.close()
                except Exception:  # fechar não pode esconder o erro de cima
                    pass
    nada = ("nada foi enviado" if verbo in METODOS_QUE_SO_LEEM
            else "confira na Central se o pedido chegou antes de repetir")
    raise CentralHttpError(
        f"Não consegui falar com {host}: {ultimo}. Confira a internet da "
        f"serventia e tente de novo; {nada}.", tentativas=feitas, causa=ultimo)
