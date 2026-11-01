"""O transporte do Serviço de Pendências do e-Protocolo 2.0 — Unidade Interligada
e e-Óbito.

Referência técnica: `https://eventos.registrocivil.org.br/reference` (OpenAPI
1.0) e o manual `public/docs/integracao-unidade-interligada.pdf`, lidos em
31/10/2026. Em divergência, o manual manda seguir a referência técnica.

**SÃO DOIS SERVIÇOS E UM TOKEN SÓ.** `Eventos` autentica e entrega as
notificações; `Protocolo` consulta, baixa e cumpre. O Bearer vale 10 minutos, e
qualquer 401 se resolve autenticando de novo e repetindo uma vez.

**LER A FILA GASTA A FILA.** `GET /requirements-notifications` marca como lido o
que devolve (RN01-Notificações). Por isso esta função só devolve o lote: quem
chamou grava antes de fazer qualquer outra coisa, e a reconciliação por
`/requirements-notifications/all` recupera a resposta que se perdeu no caminho.

**O CUMPRIMENTO É A ÚNICA ROTA QUE ALTERA O PROTOCOLO**, e ela leva dois tokens:
o Bearer do cartório e, em `access-token`, o do cartorário no IdRC. Este vale 5
minutos e nasce de um login com segundo fator — não se minera nem se guarda.
Como toda escrita da casa, o `POST` não se repete sozinho.

**A MEDIR NA HOMOLOGAÇÃO, E NÃO DEDUZIDO:** a referência descreve `certificate`
e `responsibleUser` como objetos dentro de um `multipart/form-data` sem dizer
como eles se escrevem. O sistema manda a forma com colchetes
(`certificate[type]`), que é a usual desses servidores; se a homologação recusar
com 422, a troca é em `campos_do_cumprimento`, num lugar só.

Este módulo não sabe de banco. As mensagens não trazem dado pessoal nem token.
"""
from __future__ import annotations

import http.client
import json
import re
import ssl
import time
import urllib.parse
import uuid
from typing import Any

import centrais_cred as CRED
import centrais_trava_sandbox as TRAVA

HOMOLOGACAO, PRODUCAO = CRED.HOMOLOGACAO, CRED.PRODUCAO

EVENTOS = {HOMOLOGACAO: "https://eventosh.registrocivil.org.br",
           PRODUCAO: "https://eventos.registrocivil.org.br"}
PROTOCOLO = {HOMOLOGACAO: "https://protocoloh.registrocivil.org.br",
             PRODUCAO: "https://protocolo.registrocivil.org.br"}
PREFIXO_DO_PROTOCOLO = "/api/v1.0/notifications-system"

#: O intervalo que o manual pede entre chamadas seguidas da fila.
PAUSA_ENTRE_CHAMADAS_S = 5
#: Teto de voltas por rodada: 200 notificações por volta. O que sobrar fica para
#: a próxima rodada; a fila não se perde por esperar.
VOLTAS_POR_RODADA = 20
PRAZO_PADRAO = 60
PRAZO_DO_ARQUIVO = 180
TENTATIVAS_DE_REDE = 2
TIPOS_DO_RECIBO = {"pdf": "application/pdf", "png": "image/png",
                   "jpg": "image/jpeg", "jpeg": "image/jpeg"}
CERTIDAO_ELETRONICA, CERTIDAO_FISICA = "electronic", "physical"
TETO_DA_URL = 1000


class EProtocoloError(RuntimeError):
    """Não deu para falar com o serviço, ou ele recusou. A frase vai à tela."""


class EProtocoloRecusou(EProtocoloError):
    """O serviço respondeu e disse não. `status` é o código HTTP."""

    def __init__(self, mensagem: str, status: int = 0):
        super().__init__(mensagem)
        self.status = status


class EProtocoloCheio(EProtocoloError):
    """429: chamadas demais. A rodada para e a próxima continua de onde parou."""


def _partes(base: str) -> tuple[str, int]:
    """Hospedeiro e porta, sempre em https: dado pessoal não trafega aberto."""
    p = urllib.parse.urlsplit(base)
    if p.scheme != "https" or not p.hostname:
        raise EProtocoloError(f"Endereço do e-Protocolo inválido: {base}.")
    return p.hostname, p.port or 443


def bater(metodo: str, base: str, caminho: str, *, token: str = "",
          corpo: bytes | None = None, tipo: str = "application/json",
          cabecas: dict | None = None, prazo: int = PRAZO_PADRAO) -> dict:
    """Uma requisição. Devolve `{status, json, bytes, cabecas}` — 4xx não estoura.

    Só `GET` se repete quando a rede falha: um cumprimento que o serviço pode ter
    recebido não se manda de novo sozinho.
    """
    hospedeiro, porta = _partes(base)
    try:
        hospedeiro, porta = TRAVA.destino_seguro(hospedeiro, porta)
    except TRAVA.SandboxTravaRecusou as recusa:
        raise EProtocoloError(str(recusa)) from recusa
    enviar = {"Accept": "application/json", "User-Agent": "CartorioGestao",
              **(cabecas or {})}
    if token:
        enviar["Authorization"] = f"Bearer {token}"
    if corpo is not None:
        enviar["Content-Type"] = tipo
    contexto = ssl.create_default_context()
    ultimo: Exception | None = None
    for tentativa in range(TENTATIVAS_DE_REDE + 1):
        conexao = None
        try:
            conexao = http.client.HTTPSConnection(hospedeiro, porta, timeout=prazo,
                                                  context=contexto)
            conexao.request(metodo, caminho, body=corpo, headers=enviar)
            r = conexao.getresponse()
            dados = r.read()
            try:
                como_json = json.loads(dados.decode("utf-8")) if dados.strip() else None
            except ValueError:
                como_json = None
            return {"status": r.status, "json": como_json, "bytes": dados,
                    "cabecas": {k.lower(): v for k, v in r.getheaders()}}
        except (OSError, ssl.SSLError, http.client.HTTPException) as erro:
            ultimo = erro
            if metodo != "GET" or tentativa >= TENTATIVAS_DE_REDE:
                break
            time.sleep(1 + tentativa)
        finally:
            if conexao is not None:
                conexao.close()
    # O NOME DA EXCEÇÃO, E NÃO O TEXTO: mensagem de biblioteca pode citar cabeçalho.
    raise EProtocoloError(
        f"Não consegui falar com o e-Protocolo em {hospedeiro} "
        f"({type(ultimo).__name__}). Confira a internet da serventia."
        + (" O cumprimento pode ter chegado: consulte o protocolo antes de repetir."
           if metodo != "GET" else ""))


def motivo_da_resposta(r: dict) -> str:
    """O texto que o serviço escreveu, curto. Nunca o corpo inteiro."""
    j = r.get("json")
    texto = ""
    if isinstance(j, dict):
        texto = str(j.get("message") or j.get("error") or "")
    return re.sub(r"\s+", " ", texto)[:300] or f"HTTP {r.get('status')}"


class Sessao:
    """Uma conversa com o serviço: guarda o Bearer na memória, e só nela."""

    def __init__(self, ambiente: str, *, pasta: Any = None, transporte: Any = None):
        self.ambiente = CRED.ambiente_de_uso(CRED.EPROTOCOLO, ambiente)
        self.pasta = pasta
        self._bater = transporte or bater
        self._token = ""

    # ---------------------------------------------------------- autenticação

    def entrar(self) -> None:
        """`POST /auth/signin`, com o par gerado pelo oficial no e-Protocolo."""
        usuario, senha = CRED.credencial(CRED.EPROTOCOLO, self.ambiente, self.pasta)
        corpo = json.dumps({"username": usuario, "password": senha}).encode("utf-8")
        r = self._bater("POST", EVENTOS[self.ambiente], "/auth/signin", corpo=corpo)
        token = (r.get("json") or {}).get("accessToken") if isinstance(r.get("json"), dict) else ""
        if r["status"] == 401:
            raise EProtocoloRecusou(
                "O e-Protocolo recusou o usuário e a senha. Gere a credencial de novo no "
                "botão «Serviço de pendências» do e-Protocolo e informe em Administrativo → "
                "Configurações.", 401)
        if r["status"] >= 300 or not token:
            raise EProtocoloRecusou(f"O e-Protocolo não autenticou: {motivo_da_resposta(r)}.",
                                    r["status"])
        self._token = token

    def conferir(self) -> bool:
        """Autentica e pergunta `GET /auth` se o token vale. O botão «testar»."""
        self.entrar()
        return self._bater("GET", EVENTOS[self.ambiente], "/auth",
                           token=self._token)["status"] == 204

    def _chamar(self, metodo: str, base: dict, caminho: str, **k) -> dict:
        """Com o Bearer. 401 autentica de novo e repete uma vez; 429 para."""
        if not self._token:
            self.entrar()
        r = self._bater(metodo, base[self.ambiente], caminho, token=self._token, **k)
        if r["status"] == 401:
            self.entrar()
            r = self._bater(metodo, base[self.ambiente], caminho, token=self._token, **k)
        if r["status"] == 429:
            raise EProtocoloCheio(
                "O e-Protocolo pediu para esperar (chamadas demais). A próxima rodada "
                "continua de onde parou.")
        return r

    # ---------------------------------------------------------- notificações

    def notificacoes_novas(self) -> tuple[list[dict], int]:
        """`GET /requirements-notifications`: (lote, quantas ainda faltam).

        GASTA A FILA: o que volta aqui não volta de novo.
        """
        r = self._chamar("GET", EVENTOS, "/requirements-notifications")
        if r["status"] != 200 or not isinstance(r.get("json"), dict):
            raise EProtocoloRecusou(
                f"A fila de notificações não respondeu: {motivo_da_resposta(r)}.", r["status"])
        return (list(r["json"].get("notifications") or []),
                int(r["json"].get("remainingUnread") or 0))

    def notificacoes_do_periodo(self, de: str, ate: str, pagina: int = 1) -> dict:
        """`GET /requirements-notifications/all`: o histórico, em UTC. Só lê."""
        consulta = urllib.parse.urlencode({"page": pagina, "from": de, "to": ate})
        r = self._chamar("GET", EVENTOS, f"/requirements-notifications/all?{consulta}")
        if r["status"] != 200 or not isinstance(r.get("json"), dict):
            raise EProtocoloRecusou(
                f"O histórico de notificações não respondeu: {motivo_da_resposta(r)}.",
                r["status"])
        return r["json"]

    # -------------------------------------------------------------- protocolo

    def _caminho(self, sufixo: str) -> str:
        return PREFIXO_DO_PROTOCOLO + sufixo

    @staticmethod
    def _hash(valor: Any) -> str:
        """O hash vai para a URL: só o que um identificador pode ter."""
        texto = str(valor or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9-]{1,100}", texto):
            raise EProtocoloError("O identificador do protocolo é inválido.")
        return texto

    def protocolo(self, hash_: Any) -> dict:
        """O detalhe do protocolo. A referência declara 201 nesta rota; vale 2xx."""
        r = self._chamar("GET", PROTOCOLO, self._caminho(f"/requirements/{self._hash(hash_)}"))
        if not 200 <= r["status"] < 300 or not isinstance(r.get("json"), dict):
            raise EProtocoloRecusou(
                f"O protocolo não veio: {motivo_da_resposta(r)}.", r["status"])
        return r["json"].get("data") or r["json"]

    def arquivo_estruturado(self, hash_: Any) -> dict | None:
        """O JSON do registro. 404 é resposta de verdade: este não tem arquivo."""
        r = self._chamar("GET", PROTOCOLO,
                         self._caminho(f"/requirements/{self._hash(hash_)}/structured-file"))
        if r["status"] == 404:
            return None
        if r["status"] != 200 or not isinstance(r.get("json"), dict):
            raise EProtocoloRecusou(
                f"O arquivo estruturado não veio: {motivo_da_resposta(r)}.", r["status"])
        corpo = r["json"]
        return corpo.get("data") if isinstance(corpo.get("data"), dict) else corpo

    def anexo(self, anexo_id: Any) -> dict:
        """Os bytes de um anexo. Não ficam no banco: busca-se quando se precisa."""
        numero = str(anexo_id or "").strip()
        if not numero.isdigit():
            raise EProtocoloError("O identificador do anexo é inválido.")
        r = self._chamar("GET", PROTOCOLO, self._caminho(f"/requirements/file/{numero}"),
                         prazo=PRAZO_DO_ARQUIVO)
        if r["status"] != 200:
            raise EProtocoloRecusou(f"O anexo não veio: {motivo_da_resposta(r)}.", r["status"])
        return {"bytes": r["bytes"], "tipo": r["cabecas"].get("content-type", "")}

    def historico(self, hash_: Any) -> Any:
        """As atividades do protocolo, para a ficha."""
        r = self._chamar("GET", PROTOCOLO,
                         self._caminho(f"/requirement/{self._hash(hash_)}/historic"))
        if r["status"] != 200 or not isinstance(r.get("json"), dict):
            raise EProtocoloRecusou(f"O histórico não veio: {motivo_da_resposta(r)}.", r["status"])
        return r["json"].get("data", r["json"])

    def cumprir(self, hash_: Any, *, certidao: dict, responsavel: dict,
                token_idrc: str, titulares: list[dict] | None = None,
                recibo: dict | None = None) -> dict:
        """`POST .../fulfillment`. ESCREVE NA CENTRAL. Não se repete sozinho."""
        token_idrc = str(token_idrc or "").strip()
        if not token_idrc:
            raise EProtocoloError("Sem o token do IdRC do cartorário não há cumprimento.")
        campos = campos_do_cumprimento(certidao, responsavel, titulares)
        corpo, tipo = multipart(campos, recibo)
        r = self._chamar("POST", PROTOCOLO,
                         self._caminho(f"/requirements/{self._hash(hash_)}/fulfillment"),
                         corpo=corpo, tipo=tipo, cabecas={"access-token": token_idrc})
        if not 200 <= r["status"] < 300:
            raise EProtocoloRecusou(
                f"O e-Protocolo recusou o cumprimento: {motivo_da_resposta(r)}.", r["status"])
        return r.get("json") or {}


def campos_do_cumprimento(certidao: dict, responsavel: dict,
                          titulares: list[dict] | None = None) -> list[tuple[str, str]]:
    """O corpo do cumprimento, em pares do formulário. SÓ CALCULA.

    É aqui que a forma dos objetos se decide — ver o cabeçalho do módulo. O que a
    referência limita, recusa-se antes de ir, com o cliente ainda na frente.
    """
    tipo = str(certidao.get("type") or "").strip()
    url = str(certidao.get("url") or "").strip()
    if tipo not in (CERTIDAO_ELETRONICA, CERTIDAO_FISICA):
        raise EProtocoloError("Diga se a certidão é eletrônica ou física.")
    if tipo == CERTIDAO_ELETRONICA:
        if not re.match(r"^https://\S+$", url) or len(url) > TETO_DA_URL:
            raise EProtocoloError("Certidão eletrônica exige o link dela (https, até 1.000 "
                                  "caracteres).")
    elif url:
        raise EProtocoloError("Certidão física não leva link.")
    cpf = re.sub(r"\D", "", str(responsavel.get("cpf") or ""))
    cns = re.sub(r"\D", "", str(responsavel.get("cns") or ""))
    nome = str(responsavel.get("name") or "").strip()
    email = str(responsavel.get("email") or "").strip()
    if len(cpf) != 11:
        raise EProtocoloError("O CPF do cartorário responsável precisa de 11 dígitos.")
    if not cns:
        raise EProtocoloError("Falta o CNS do cartório em Administrativo → Configurações.")
    if not nome:
        raise EProtocoloError("Falta o nome do cartorário responsável.")
    # `nome@dominio.tld` sem expressão regular, como `contato_do_cliente`
    # (CodeQL py/polynomial-redos): um só `@`, nenhum branco, e no domínio um
    # ponto com algo dos dois lados.
    usuario, arroba, dominio = email.partition("@")
    if not (usuario and arroba and "@" not in dominio
            and not any(c.isspace() for c in email) and "." in dominio[1:-1]):
        raise EProtocoloError("O e-mail do cartorário responsável é inválido.")
    campos = [("certificate[type]", tipo)]
    if url:
        campos.append(("certificate[url]", url))
    campos += [("responsibleUser[cpf]", cpf), ("responsibleUser[cns]", cns),
               ("responsibleUser[name]", nome), ("responsibleUser[email]", email)]
    for i, t in enumerate(titulares or []):
        for de, para, teto in (("name", "name", 255), ("cpf", "cpf", 11),
                               ("registration", "registration", 50),
                               ("registerType", "registerType", 100)):
            valor = str(t.get(de) or "").strip()
            if de == "cpf":
                valor = re.sub(r"\D", "", valor)
            if valor:
                campos.append((f"subjects[{i}][{para}]", valor[:teto]))
    return campos


def multipart(campos: list[tuple[str, str]], recibo: dict | None = None) -> tuple[bytes, str]:
    """O corpo `multipart/form-data`. O recibo, quando há: `{nome, bytes}`."""
    limite = f"----CartorioGestao{uuid.uuid4().hex}"
    pedacos: list[bytes] = []
    for nome, valor in campos:
        pedacos.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n'
            .encode("utf-8"))
    if recibo:
        arquivo = re.sub(r'[\r\n"\\/]', "_", str(recibo.get("nome") or "recibo"))
        extensao = arquivo.rsplit(".", 1)[-1].lower() if "." in arquivo else ""
        if extensao not in TIPOS_DO_RECIBO:
            raise EProtocoloError("O recibo precisa ser .pdf, .png, .jpg ou .jpeg.")
        pedacos.append(
            f'--{limite}\r\nContent-Disposition: form-data; name="file"; filename="{arquivo}"\r\n'
            f"Content-Type: {TIPOS_DO_RECIBO[extensao]}\r\n\r\n".encode("utf-8")
            + bytes(recibo["bytes"]) + b"\r\n")
    pedacos.append(f"--{limite}--\r\n".encode("ascii"))
    return b"".join(pedacos), f"multipart/form-data; boundary={limite}"
