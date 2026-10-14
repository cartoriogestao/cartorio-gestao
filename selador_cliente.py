"""
O cliente do selador — a unica parte do sistema que fala com o Tribunal.

O QUE JA ESTAVA PRONTO, E O QUE FALTAVA
    `selador.py` tem o contrato: 181 endpoints, 115 schemas, o SID e a leitura
    da resposta e do erro. `selador_config.py` tem onde selar e com que
    credencial. Faltava o transporte — e e so ele que esta aqui.

    Por isso este modulo e pequeno e os outros dois sao grandes. O que decide
    um selo e o contrato e a configuracao; o transporte so leva.

SEM DEPENDENCIA NOVA
    `http.client` e `ssl`, da biblioteca padrao. O sistema roda em maquina de
    serventia, instalado por `.cmd`, e uma dependencia a mais e um jeito a mais
    de a instalacao falhar num sabado. Nao vale a comodidade.

O CERTIFICADO: FIXAR, E NAO DESLIGAR
    O selador desta casa e `https://192.168.0.200:443` — maquina da rede local.
    Maquina de rede local nao tem certificado assinado por autoridade; tem
    certificado proprio. Validar pela cadeia falha sempre.

    O caminho facil seria `verify=False`, e ele e ruim: qualquer maquina da
    rede passaria a poder se passar pelo selador e receber a senha da
    serventia. O caminho certo e FIXAR o certificado — na primeira conexao o
    sistema mostra a impressao digital, o oficial confirma, e dali em diante so
    aquele certificado serve. Isso e mais forte que validar cadeia, e nao
    menos: nem uma autoridade comprometida abriria a porta.

    Sem certificado fixado, este modulo RECUSA conectar e diz como fixar.

O QUE ELE PROTEGE, ALEM DO SELO
    O balcao. Toda chamada tem prazo curto, e prazo esgotado devolve mensagem
    de balcao — nao trava a tela esperando um aparelho que nao responde.

    E o dinheiro. Todo selo obtido entra no razao `sd_selos` ANTES de o ato
    ficar pronto. No acervo do E-Oficio ha 1.304 selos orfaos, 5% do total, e
    so cinco deles foram cancelados: e o rastro de quem obteve selo e perdeu o
    ato no meio. Aqui o selo aparece na tela de selo nao usado, em vez de sumir.

FUNDAMENTO
    Lei 8.935/1994, art. 30, XIV (fiscalizacao do selo).
    Codigo de Normas do Foro Extrajudicial do Maranhao — Provimento TJMA n. 28,
        de 23/04/2026, Secao do Selo de Fiscalizacao Eletronico.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import socket
import sqlite3
import ssl
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import selador
import selador_config as SC

# Prazo curto de proposito: quem espera e o balcao, com a parte na frente.
PRAZO_PADRAO = 20          # segundos
PRAZO_DO_TOKEN = 30

# Quantas vezes repetir quando a falha e de REDE. Nunca quando e recusa: 400
# repetido dez vezes continua 400, e cada tentativa e uma chance de gerar selo.
TENTATIVAS_DE_REDE = 2


class SeladorIndisponivel(RuntimeError):
    """Nao deu para falar com o selador. Mensagem pronta para a tela."""


class CertificadoNaoConfere(SeladorIndisponivel):
    """O certificado apresentado nao e o que esta fixado."""


# ------------------------------------------------------------- o certificado


@dataclass(frozen=True)
class Certificado:
    sha256: str
    assunto: str
    emissor: str
    valido_ate: str | None

    @property
    def legivel(self) -> str:
        """`AB:CD:EF:...` — o jeito como impressao digital se confere a olho."""
        return ":".join(self.sha256[i:i + 2]
                        for i in range(0, len(self.sha256), 2)).upper()

    @property
    def vencido(self) -> bool:
        """Se a validade ja passou. Pode ser None quando nao deu para ler."""
        if not self.valido_ate:
            return False
        try:
            fim = datetime.fromisoformat(self.valido_ate)
        except ValueError:
            return False
        agora = datetime.now(fim.tzinfo) if fim.tzinfo else datetime.now()
        return fim < agora

    @property
    def proprio(self) -> bool:
        """Auto-assinado — emissor igual ao assunto."""
        return bool(self.assunto) and self.assunto == self.emissor

    def aviso_de_validade(self) -> str:
        """A frase sobre a validade, ou vazio quando nao ha o que dizer.

        CERTIFICADO VENCIDO NAO IMPEDE DE FIXAR, e isto e deliberado.
        Fixar e dizer «e esta maquina, eu conferi». A data de validade serve
        para quem confia numa autoridade certificadora decidir por conta
        propria; quem fixou ja decidiu, e a data nao muda quem a maquina e.

        Recusar por vencimento pararia a serventia inteira por uma formalidade
        que ela nao tem como resolver sozinha — o certificado e do fabricante
        do aparelho, nao dela.
        """
        if not self.vencido:
            return ""
        return (f"O certificado venceu em {(self.valido_ate or '')[:10]}. Isso "
                f"não impede de fixá-lo: fixar é dizer «é esta máquina, eu "
                f"conferi», e a data não muda quem a máquina é. Mas vale "
                f"pedir a renovação a quem mantém o selador — e, quando ela "
                f"vier, o certificado muda e será preciso conferir e fixar o "
                f"novo.")


def _descrever(der: bytes) -> tuple[str, str, str | None]:
    """Assunto, emissor e validade do certificado — se der para ler.

    `getpeercert()` devolve dicionario VAZIO quando a validacao esta desligada,
    e ela precisa estar desligada aqui: o certificado do selador e proprio, e
    quem o valida e a impressao digital fixada, nao a cadeia. Entao o assunto
    sai do DER.

    Isso usa `cryptography`, que vem com o pip da maquina mas nao esta nos
    requisitos do sistema — e por isso e OPCIONAL. Faltando, o certificado
    aparece so pela impressao digital, que e o que de fato o identifica; o
    assunto e comodidade para o oficial reconhecer a maquina, nao seguranca.
    """
    try:
        from cryptography import x509
    except ImportError:
        return ("", "", None)
    try:
        c = x509.load_der_x509_certificate(der)
        assunto = ", ".join(f"{a.oid._name}={a.value}" for a in c.subject)
        emissor = ", ".join(f"{a.oid._name}={a.value}" for a in c.issuer)
        return (assunto, emissor, c.not_valid_after_utc.isoformat())
    except Exception:                                          # noqa: BLE001
        return ("", "", None)


def _endereco(base: str) -> tuple[str, int]:
    partes = urllib.parse.urlsplit(base)
    if partes.scheme != "https":
        raise SeladorIndisponivel(
            f"O endereço do selador tem de ser https — veio «{base}».")
    if not partes.hostname:
        raise SeladorIndisponivel(f"Endereço do selador inválido: «{base}».")
    return partes.hostname, (partes.port or 443)


def espiar_certificado(base: str, prazo: int = PRAZO_PADRAO) -> Certificado:
    """Busca o certificado do selador SEM validar, so para mostrar. So LE.

    E o unico lugar que conecta sem certificado fixado, e ele nao manda dado
    nenhum: abre, olha o certificado e fecha. E assim que o oficial ve a
    impressao digital para poder confirmar.
    """
    hospedeiro, porta = _endereco(base)
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((hospedeiro, porta), timeout=prazo) as cru:
            with contexto.wrap_socket(cru, server_hostname=hospedeiro) as tls:
                bruto = tls.getpeercert(binary_form=True)
    except (OSError, ssl.SSLError) as erro:
        raise SeladorIndisponivel(_falha_de_rede(base, erro)) from erro
    if not bruto:
        raise SeladorIndisponivel(
            f"O selador em {base} respondeu sem apresentar certificado.")
    assunto, emissor, ate = _descrever(bruto)
    return Certificado(sha256=hashlib.sha256(bruto).hexdigest(),
                       assunto=assunto, emissor=emissor, valido_ate=ate)


def _falha_de_rede(base: str, erro: Exception) -> str:
    """A mensagem que o balcao entende, e nao o traceback."""
    texto = str(erro)
    if isinstance(erro, socket.timeout) or "timed out" in texto:
        return (f"O selador em {base} não respondeu no prazo. Se ele é uma "
                f"máquina da rede local, confira se ela está ligada e se este "
                f"computador está na mesma rede.")
    if isinstance(erro, ConnectionRefusedError) or "refused" in texto.lower():
        return (f"O selador em {base} recusou a conexão — a máquina responde, "
                f"mas nada está escutando nessa porta.")
    if isinstance(erro, socket.gaierror) or "getaddrinfo" in texto:
        return f"Não achei a máquina do selador em {base}."
    return f"Não consegui falar com o selador em {base}: {texto}"


def fixar_certificado(con: sqlite3.Connection, base: str, *, sha256: str,
                      agora: str, usuario: str | None = None,
                      prazo: int = PRAZO_PADRAO) -> Certificado:
    """Confirma e grava a impressao digital do selador. ESCREVE.

    Recusa fixar impressao diferente da que a maquina apresenta AGORA: fixar de
    ouvido, com um valor digitado errado, deixaria o sistema recusando o
    selador de verdade para sempre.
    """
    visto = espiar_certificado(base, prazo)
    limpo = "".join(c for c in str(sha256 or "") if c.isalnum()).lower()
    if limpo != visto.sha256:
        raise CertificadoNaoConfere(
            f"A impressão digital informada não é a que o selador em {base} "
            f"apresenta agora. Ele apresenta {visto.legivel}.")
    con.execute(
        """UPDATE sd_config SET certificado_sha256=?, certificado_assunto=?,
               certificado_valido_ate=?, certificado_fixado_em=?,
               certificado_fixado_por=? WHERE id=1""",
        (visto.sha256, visto.assunto, visto.valido_ate, agora, usuario))
    return visto


def certificado_fixado(con: sqlite3.Connection) -> str | None:
    linha = con.execute(
        "SELECT certificado_sha256 FROM sd_config WHERE id=1").fetchone()
    return (linha["certificado_sha256"] if linha else None) or None


# ------------------------------------------------------------- o transporte


@dataclass
class Resposta:
    """O que voltou, ja separado em bom e ruim."""

    status: int
    corpo: Any
    ok: bool
    erro: selador.ErroDoSelador | None = None
    selos: list[selador.SeloGerado] = field(default_factory=list)


def _bater(base: str, metodo: str, caminho: str, *, cabecalhos: dict,
           corpo: bytes | None, sha256: str, prazo: int) -> tuple[int, bytes]:
    """Uma requisicao, conferindo a impressao digital do certificado.

    A conferencia acontece DEPOIS do aperto de mao e ANTES de mandar o corpo —
    porque o corpo leva o token, e token nao se manda para maquina que nao e a
    que se espera.
    """
    hospedeiro, porta = _endereco(base)
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    conexao = http.client.HTTPSConnection(hospedeiro, porta, timeout=prazo,
                                          context=contexto)
    try:
        conexao.connect()
        apresentado = conexao.sock.getpeercert(binary_form=True)
        visto = hashlib.sha256(apresentado or b"").hexdigest()
        if visto != sha256:
            raise CertificadoNaoConfere(
                f"A máquina em {base} apresentou um certificado diferente do "
                f"que está fixado nesta serventia. Nada foi enviado. Se o "
                f"certificado do selador foi trocado de propósito, fixe o novo "
                f"na tela do selador; se não foi, alguém está no meio do "
                f"caminho.")
        conexao.request(metodo, caminho, body=corpo, headers=cabecalhos)
        resposta = conexao.getresponse()
        return resposta.status, resposta.read()
    except (OSError, ssl.SSLError, http.client.HTTPException) as erro:
        raise SeladorIndisponivel(_falha_de_rede(base, erro)) from erro
    finally:
        conexao.close()


def _json(bruto: bytes) -> Any:
    if not bruto:
        return None
    try:
        return json.loads(bruto.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return bruto.decode("utf-8", errors="replace")[:600]


# ----------------------------------------------------------------- o token
#
# Guardado so em memoria, e so enquanto vale. Token em disco e senha em disco
# com outro nome.

_TOKENS: dict[str, tuple[str, datetime]] = {}


def esquecer_tokens() -> None:
    """Descarta os tokens em memoria. Chamado ao trocar configuracao."""
    _TOKENS.clear()


def obter_token(con: sqlite3.Connection, pasta_de_dados: Any, *,
                agora: datetime | None = None, prazo: int = PRAZO_DO_TOKEN,
                forcar: bool = False) -> str:
    """O token do selador, do cache ou do Keycloak.

    A senha entra aqui e nao sai: nao vai para log, nao vai para auditoria e
    nao volta na mensagem de erro.
    """
    agora = agora or datetime.now()
    credencial = SC.credencial_para_autenticar(con, pasta_de_dados)
    chave = f"{credencial['base']}|{credencial['usuario']}"
    if not forcar:
        guardado = _TOKENS.get(chave)
        if guardado and guardado[1] > agora:
            return guardado[0]

    pedido = selador.montar_autenticacao(credencial["usuario"],
                                         credencial["senha"],
                                         url=credencial["auth"])
    alvo = urllib.parse.urlsplit(pedido["url"])
    base_auth = f"{alvo.scheme}://{alvo.netloc}"
    caminho = alvo.path or "/"
    corpo = urllib.parse.urlencode(pedido["formulario"]).encode("utf-8")
    fixado = certificado_fixado(con)
    if not fixado:
        raise SeladorIndisponivel(_sem_certificado(credencial["base"]))
    try:
        status, bruto = _bater(base_auth, "POST", caminho,
                               cabecalhos=pedido["cabecalhos"], corpo=corpo,
                               sha256=fixado, prazo=prazo)
    except CertificadoNaoConfere:
        raise
    except SeladorIndisponivel as erro:
        raise SeladorIndisponivel(f"Não consegui autenticar: {erro}") from erro

    dados = _json(bruto)
    if status != 200 or not isinstance(dados, dict) or not dados.get("access_token"):
        # A CREDENCIAL E DO APARELHO, E NAO DESTA CASA — medido em 27/08/2026,
        # quando o oficial perguntou de quem era o usuario do selador.
        #
        #   O usuario guardado em `tbSeladorConfiguracao` NAO aparece em
        #   nenhuma das tres tabelas de usuario do E-Oficio (`tbUsuario`, com
        #   14 pessoas, `tbServico_Usuario` e `SessaoUsuario`). E a
        #   documentacao da FPFTech mostra o token de exemplo: e um Keycloak,
        #   com realm `selador-ca…`, `client_id` fixo `selador` e uma conta
        #   POR SERVENTIA (no exemplo, `cartorio1`).
        #
        #   A mensagem antiga mandava conferir "a credencial do E-Oficio", e
        #   isso poria o oficial a procurar num cadastro que nao tem o que ele
        #   procura. Quem cria, troca e desbloqueia essa conta e quem provisiona
        #   o aparelho.
        raise SeladorIndisponivel(
            f"O selador recusou o usuário e a senha (HTTP {status}). Esta "
            f"credencial é do próprio aparelho — não é usuário deste sistema "
            f"nem do E-Ofício —, e quem a cria, troca ou desbloqueia é quem "
            f"instalou o selador (FPFTech / TJMA). Se ela acabou de ser "
            f"importada do E-Ofício, pode ter sido trocada no aparelho depois.")
    validade = int(dados.get("expires_in") or 60)
    # Uma folga de dez segundos: token que vence entre o pedido e a chegada
    # devolve 401 no meio do atendimento.
    _TOKENS[chave] = (dados["access_token"],
                      agora + timedelta(seconds=max(10, validade - 10)))
    return dados["access_token"]


def _sem_certificado(base: str) -> str:
    return (f"O certificado do selador em {base} ainda não foi conferido. "
            f"Abra a tela do selador, veja a impressão digital que a máquina "
            f"apresenta e confirme que é a dela. Enquanto isso não for feito, "
            f"o sistema não manda a senha da serventia para lá.")


# ------------------------------------------------------------------- selar


def selar(con: sqlite3.Connection, pasta_de_dados: Any, caminho: str,
          dados: dict, *, referencia: Any, atribuicao: str, agora: str,
          cns: Any, tentativa: int = 1, usuario: str | None = None,
          prazo: int = PRAZO_PADRAO) -> list[selador.SeloGerado]:
    """Pede o selo e GRAVA no razao antes de devolver. ESCREVE.

    A ordem importa e nao e a obvia: o selo entra em `sd_selos` assim que
    chega, ANTES de quem chamou terminar o ato. Se o ato falhar depois, o selo
    aparece na tela de selo nao usado — que e exatamente o que faltou no
    E-Oficio, onde 1.304 selos ficaram orfaos sem ninguem saber.

    `referencia` tem de ser a mesma entre tentativas do MESMO ato: e dela que
    sai o SID, e e o SID que faz o selador devolver o selo que ja existe em vez
    de vender outro.
    """
    estado = SC.situacao(con, pasta_de_dados)
    if not estado["pronto"]:
        raise SeladorIndisponivel(" ".join(estado["faltas"]))
    fixado = certificado_fixado(con)
    if not fixado:
        raise SeladorIndisponivel(_sem_certificado(estado["base_em_uso"]))

    chave = selador.sid(cns, atribuicao, referencia, tentativa)
    ja = con.execute(
        "SELECT * FROM sd_selos WHERE sid=? AND cancelado_em IS NULL",
        (chave,)).fetchall()
    if ja:
        # O selo deste ato ja foi obtido. Devolver o que existe e o ponto do
        # SID; pedir de novo compraria o segundo.
        return [selador.SeloGerado(
            numero=r["numero"], texto=r["texto"] or "",
            data_geracao=r["data_geracao"],
            saldo_remanescente=r["saldo_remanescente"]) for r in ja]

    pedido = selador.montar_pedido(caminho, dados, sid_do_ato=chave,
                                   base=estado["base_em_uso"])
    token = obter_token(con, pasta_de_dados)
    resposta = _despachar(con, pasta_de_dados, pedido, token, fixado, prazo)
    if not resposta.ok:
        raise SeladorIndisponivel(str(resposta.erro or
                                      f"O selador recusou (HTTP {resposta.status})."))
    for selo in resposta.selos:
        con.execute(
            """INSERT OR IGNORE INTO sd_selos(numero, texto, sid, caminho,
                   atribuicao, referencia, data_geracao, saldo_remanescente,
                   ambiente, obtido_em, obtido_por)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (selo.numero, selo.texto, chave, caminho, atribuicao,
             str(referencia), selo.data_geracao, selo.saldo_remanescente,
             estado["ambiente"], agora, usuario))
    return resposta.selos


def _despachar(con, pasta_de_dados, pedido: dict, token: str, sha256: str,
               prazo: int) -> Resposta:
    """Manda o pedido, com uma re-autenticacao se o token tiver vencido."""
    alvo = urllib.parse.urlsplit(pedido["url"])
    base = f"{alvo.scheme}://{alvo.netloc}"
    caminho = alvo.path
    if pedido.get("query"):
        caminho += "?" + urllib.parse.urlencode(pedido["query"])
    corpo = json.dumps(pedido["corpo"], ensure_ascii=False).encode("utf-8")

    for volta in range(2):
        cabecalhos = dict(pedido["cabecalhos"], Authorization=f"Bearer {token}")
        ultimo = None
        for _ in range(TENTATIVAS_DE_REDE):
            try:
                status, bruto = _bater(base, pedido["metodo"], caminho,
                                       cabecalhos=cabecalhos, corpo=corpo,
                                       sha256=sha256, prazo=prazo)
                break
            except CertificadoNaoConfere:
                raise
            except SeladorIndisponivel as erro:
                # Repetir e SEGURO aqui: o SID vai na query, e o selador
                # devolve o mesmo selo em vez de gerar outro.
                ultimo = erro
        else:
            raise ultimo or SeladorIndisponivel("O selador não respondeu.")

        if status == 401 and volta == 0:
            token = obter_token(con, pasta_de_dados, forcar=True)
            continue
        dados = _json(bruto)
        if 200 <= status < 300:
            return Resposta(status=status, corpo=dados, ok=True,
                            selos=selador.ler_resposta(dados))
        return Resposta(status=status, corpo=dados, ok=False,
                        erro=selador.ler_erro(dados))
    raise SeladorIndisponivel("O selador devolveu 401 mesmo com token novo.")


# ------------------------------------------------------------ o razao


def vincular(con: sqlite3.Connection, numero: str, *, tabela: str,
             ato_id: int, agora: str) -> None:
    """Diz que o selo foi USADO por este ato. ESCREVE.

    Chamado quando o ato fica pronto, e nao quando o selo chega. Enquanto nao
    for chamado, o selo aparece como obtido e nao usado — que e a verdade.
    """
    con.execute(
        """UPDATE sd_selos SET tabela=?, ato_id=?, usado_em=?
            WHERE numero=? AND usado_em IS NULL""",
        (tabela, int(ato_id), agora, numero))


def orfaos(con: sqlite3.Connection, limite: int = 200) -> list[dict]:
    """Selos obtidos, nao usados e nao cancelados. So LE.

    E a tela que faltava no E-Oficio. La havia 1.304 destes, 5% de tudo, e
    ninguem sabia — porque nao havia onde olhar.
    """
    return [dict(r) for r in con.execute(
        """SELECT * FROM sd_selos
            WHERE usado_em IS NULL AND cancelado_em IS NULL
            ORDER BY obtido_em DESC LIMIT ?""", (limite,))]


def registrar_cancelamento(con: sqlite3.Connection, numero: str, *,
                           motivo: str, agora: str,
                           usuario: str | None = None) -> None:
    """Marca o selo como cancelado no razao. ESCREVE.

    Nao cancela no Tribunal — isso e chamada propria, com endpoint proprio.
    Aqui se registra que foi cancelado, com o motivo por escrito: dos 79 selos
    cancelados no acervo do E-Oficio, NENHUM tem motivo gravado.
    """
    razao = (motivo or "").strip()
    if len(razao) < 10:
        raise SeladorIndisponivel(
            "Escreva o motivo do cancelamento do selo com pelo menos dez "
            "letras — no acervo antigo nenhum dos 79 cancelamentos tem motivo, "
            "e é por isso que hoje ninguém sabe explicá-los.")
    con.execute(
        """UPDATE sd_selos SET cancelado_em=?, cancelado_por=?,
               motivo_cancelamento=? WHERE numero=?""",
        (agora, usuario, razao, numero))


# ------------------------------------------------------------- o teste


def testar(con: sqlite3.Connection, pasta_de_dados: Any, *, agora: str,
           prazo: int = PRAZO_PADRAO) -> dict:
    """Confere o caminho todo sem selar nada: rede, certificado e credencial.

    E o botao que responde "por que não está selando?" antes de o balcao
    descobrir isso com a parte na frente.
    """
    estado = SC.situacao(con, pasta_de_dados)
    passos: list[dict] = []

    def passo(nome, ok, detalhe=""):
        passos.append({"passo": nome, "ok": ok, "detalhe": detalhe})
        return ok

    if not passo("configuração", estado["pronto"], " ".join(estado["faltas"])):
        SC.registrar_teste(con, ok=False, mensagem=" ".join(estado["faltas"]),
                           agora=agora)
        return {"ok": False, "passos": passos, "estado": estado}

    base = estado["base_em_uso"]
    try:
        visto = espiar_certificado(base, prazo)
    except SeladorIndisponivel as erro:
        passo("rede", False, str(erro))
        SC.registrar_teste(con, ok=False, mensagem=str(erro), agora=agora)
        return {"ok": False, "passos": passos, "estado": estado}
    passo("rede", True, f"{base} respondeu")

    fixado = certificado_fixado(con)
    if not fixado:
        passo("certificado", False,
              f"ainda não conferido — a máquina apresenta {visto.legivel}")
        SC.registrar_teste(con, ok=False, mensagem=_sem_certificado(base),
                           agora=agora)
        return {"ok": False, "passos": passos, "estado": estado,
                "certificado_visto": visto}
    if fixado != visto.sha256:
        detalhe = (f"o certificado mudou — fixado {fixado[:16]}…, "
                   f"apresentado {visto.sha256[:16]}…")
        passo("certificado", False, detalhe)
        SC.registrar_teste(con, ok=False, mensagem=detalhe, agora=agora)
        return {"ok": False, "passos": passos, "estado": estado,
                "certificado_visto": visto}
    passo("certificado", True,
          visto.legivel + (" — " + visto.aviso_de_validade()
                           if visto.vencido else ""))

    try:
        obter_token(con, pasta_de_dados, forcar=True, prazo=prazo)
    except (SeladorIndisponivel, SC.ConfigError) as erro:
        passo("credencial", False, str(erro))
        SC.registrar_teste(con, ok=False, mensagem=str(erro), agora=agora)
        return {"ok": False, "passos": passos, "estado": estado,
                "certificado_visto": visto}
    passo("credencial", True, "o selador aceitou o usuário e a senha")
    SC.registrar_teste(con, ok=True, mensagem="rede, certificado e credencial",
                       agora=agora)
    return {"ok": True, "passos": passos, "estado": estado,
            "certificado_visto": visto}
