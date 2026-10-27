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
import logging
import socket
import ssl
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import selador
import selador_config as SC
from bd_nativo import banco
import identidade_do_robo as IDR

# Prazo curto de proposito: quem espera e o balcao, com a parte na frente.
PRAZO_PADRAO = 20          # segundos
PRAZO_DO_TOKEN = 30

# Quantas vezes repetir quando a falha e de REDE. Nunca quando e recusa: 400
# repetido dez vezes continua 400, e cada tentativa e uma chance de gerar selo.
TENTATIVAS_DE_REDE = 2

# O pedido LEGITIMO mais longo ao aparelho, contado em `selar`/`_despachar`:
# o token (prazo proprio) e o pedido com a repeticao de rede — e, se o token
# venceu no caminho (401), os dois de novo, uma vez. 2 × (30 + 2 × 20) = 140 s.
PEDIDO_MAIS_LONGO = 2 * (PRAZO_DO_TOKEN + TENTATIVAS_DE_REDE * PRAZO_PADRAO)

# Quanto um pedido espera pela trava do SID que outro pedido do MESMO ato
# segura. Esperar sem prazo era deixar o balcao parado atras de uma trava
# presa (LX21a #3). MAS O PRAZO TEM DE PASSAR DO PEDIDO MAIS LONGO (LX25,
# revisao do LX24): com 30 s, o segundo balcao recebia «ja esta sendo pedido»
# enquanto o primeiro ainda esperava o aparelho de forma legitima.
ESPERA_PELO_SID = PEDIDO_MAIS_LONGO + 10    # segundos
INTERVALO_DA_ESPERA = 0.2

_LOG = logging.getLogger(__name__)


class SeladorIndisponivel(RuntimeError):
    """Nao deu para falar com o selador. Mensagem pronta para a tela."""


class CertificadoNaoConfere(SeladorIndisponivel):
    """O certificado apresentado nao e o que esta fixado."""


class SeloJaGravado(SeladorIndisponivel):
    """O numero que chegou ja esta no razao, de OUTRO dono. Mensagem pronta.

    Filha de `SeladorIndisponivel` para cair onde a recusa do aparelho ja cai
    — frase de balcao, e nao traceback. Ver `conferir_o_repetido`.
    """


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


def fixar_certificado(con, base: str, *, sha256: str,
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
    banco(con).escrever(
        """UPDATE sd_config SET certificado_sha256 = %s, certificado_assunto = %s,
               certificado_valido_ate = %s, certificado_fixado_em = %s,
               certificado_fixado_por = %s WHERE id=1""",
        (visto.sha256, visto.assunto, visto.valido_ate, agora, usuario))
    return visto


def certificado_fixado(con) -> str | None:
    linha = banco(con).um(
        "SELECT certificado_sha256 FROM sd_config WHERE id=1")
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


def obter_token(con, pasta_de_dados: Any, *,
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
            f"nem do sistema antigo —, e quem a cria, troca ou desbloqueia é quem "
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


def _prender_o_sid(bd, assunto: str) -> None:
    """Pega a trava de SESSAO do SID, esperando no maximo `ESPERA_PELO_SID`.

    `pg_advisory_lock` esperava sem prazo nenhum (LX21a #3): se a trava
    ficasse presa numa conexao viva do reservatorio, todo pedido do mesmo
    ato parava o balcao para sempre. Aqui se tenta, e se tenta de novo, ate o
    prazo — que cobre um pedido inteiro ao aparelho, com a repeticao de rede.
    Passou o prazo, o outro pedido ainda esta em voo, ou a trava ficou presa:
    nos dois casos o balcao recebe a frase, e nao uma tela parada.
    """
    limite = time.monotonic() + ESPERA_PELO_SID
    while not bd.valor("SELECT pg_try_advisory_lock(hashtext(%s)) AS ok",
                       (assunto,)):
        if time.monotonic() >= limite:
            raise SeladorIndisponivel(
                "O selo deste ato já está sendo pedido ao selador por outro "
                "balcão ou outra aba, e o pedido não terminou a tempo. Espere "
                "um pouco e peça de novo: o segundo pedido devolve o selo do "
                "primeiro, e não compra outro.")
        time.sleep(INTERVALO_DA_ESPERA)


def _soltar_o_sid(con, bd, assunto: str, *, saindo_por_erro: bool) -> None:
    """Solta a trava de SESSAO do SID — e, se nao der, diz no log.

    A trava de sessao NAO sai com o `rollback` nem com o `close()` da ponte:
    a conexao volta ao reservatorio com ela. E transacao abortada recusa ate
    o `pg_advisory_unlock` («current transaction is aborted»), que antes era
    engolido por um `except: pass` — a trava ficava presa ate a conexao
    morrer (LX21a #3).

    SO SE DESFAZ A TRANSACAO QUANDO O `selar` JA ESTA SAINDO POR ERRO (LX25,
    revisao do LX24). Ai ela ja esta perdida — o PostgreSQL nao deixa gravar
    mais nada nela, e quem chamou vai desfaze-la de qualquer jeito —, entao
    desfaz PRIMEIRO e solta de novo; o erro que sobe continua sendo o de
    dentro do `selar`. NO SUCESSO, NUNCA: a transacao e de quem chamou e
    pode levar a reserva da cobertura e o debito no deposito. Desfaze-la por
    um unlock que falhou devolvia o selo pago (e gravado no razao logo
    abaixo) sem a reserva e sem o debito. No sucesso se tenta soltar de novo
    e, se ainda falhar, fica o log.
    """
    try:
        bd.ler("SELECT pg_advisory_unlock(hashtext(%s)) AS ok", (assunto,))
        return
    except Exception:                                          # noqa: BLE001
        if saindo_por_erro:
            _LOG.warning("A trava %s não soltou na transação de quem selou "
                         "(abortada?); desfaço a transação e solto de novo.",
                         assunto, exc_info=True)
        else:
            _LOG.warning("A trava %s não soltou depois do selo obtido; a "
                         "transação de quem selou fica, e solto de novo.",
                         assunto, exc_info=True)
    try:
        if saindo_por_erro:
            con.rollback()
        bd.ler("SELECT pg_advisory_unlock(hashtext(%s)) AS ok", (assunto,))
    except Exception:                                          # noqa: BLE001
        _LOG.error("A trava %s ficou presa nesta conexão: o próximo pedido "
                   "do mesmo ato espera %s s e recebe a frase de balcão.",
                   assunto, ESPERA_PELO_SID, exc_info=True)


def selar(con, pasta_de_dados: Any, caminho: str,
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

    bd = banco(con)
    chave = selador.sid(cns, atribuicao, referencia, tentativa)
    assunto = f"sd_selos.sid:{chave}"
    # A TRAVA VEM ANTES DE OLHAR O RAZAO: sem ela, dois pedidos do mesmo ato
    # ao mesmo tempo nao achariam nada e os dois iriam ao selador.
    #
    # E E DA SESSAO, E NAO DA TRANSACAO, ENQUANTO A REDE RESPONDE (LX21a,
    # 20/10/2026). `travar` abre a escrita, e com a ponte a escrita pega a
    # trava unica do banco: os 20 segundos do aparelho parariam todo balcao.
    # A da sessao prende so este SID, e nada mais. Para gravar, a trava passa
    # a ser a da transacao (a mesma chave), e fica ate o `commit` de quem
    # chamou — como era antes. Pegar e soltar moram em `_prender_o_sid` e
    # `_soltar_o_sid` (LX24): a espera tem prazo, e a soltura nao falha calada.
    _prender_o_sid(bd, assunto)
    saindo_por_erro = False
    try:
        ja = bd.ler(
            "SELECT * FROM sd_selos WHERE sid = %s AND cancelado_em IS NULL "
            "ORDER BY id",
            (chave,))
        if ja:
            # O selo deste ato ja foi obtido. Devolver o que existe e o ponto
            # do SID; pedir de novo compraria o segundo.
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
        bd.travar(assunto)
    except BaseException:
        # Um `finally` cego nao sabe se o selo saiu: a soltura precisa
        # saber, porque so na saida por erro ela pode desfazer a transacao.
        saindo_por_erro = True
        raise
    finally:
        _soltar_o_sid(con, bd, assunto, saindo_por_erro=saindo_por_erro)
    # O NUMERO QUE O RAZAO JA TINHA NAO SOME MAIS CALADO (LD14, 21/10/2026).
    # Era o «ignorar se ja existe» do SQLite, e na migracao `ON CONFLICT DO
    # NOTHING`: o aparelho devolvia um numero ja gravado para OUTRO ato, a
    # linha nova nao entrava, nada ia para o log, e o selo seguia para o
    # vinculo como se fosse deste ato — o que o aparelho disse se perdia.
    # Agora o conflito e conferido: o mesmo selo do mesmo pedido fica
    # registrado, e o de outro dono e recusado. Ver `conferir_o_repetido`.
    for selo in resposta.selos:
        novo = bd.escrever(
            """INSERT INTO sd_selos(numero, texto, sid, caminho,
                   atribuicao, referencia, data_geracao, saldo_remanescente,
                   ambiente, obtido_em, obtido_por)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (numero) DO NOTHING RETURNING id""",
            (selo.numero, selo.texto, chave, caminho, atribuicao,
             str(referencia), selo.data_geracao, selo.saldo_remanescente,
             estado["ambiente"], agora, usuario))
        if not novo:
            # A resposta INTEIRA vai junto: a recusa desfaz a transacao, e os
            # outros selos do mesmo pedido sairiam do razao sem rastro.
            conferir_o_repetido(
                bd, selo.numero, origem=DO_APARELHO,
                iguais={"sid": chave, "caminho": caminho,
                        "atribuicao": atribuicao,
                        "referencia": str(referencia)},
                chegou={"texto": selo.texto,
                        "data_geracao": selo.data_geracao,
                        "saldo_remanescente": selo.saldo_remanescente,
                        "numeros_da_resposta": [s.numero
                                                for s in resposta.selos]},
                agora=agora, usuario=usuario)
    _anotar_a_resposta(pasta_de_dados, caminho, chave, resposta.corpo, agora)
    return resposta.selos


def _anotar_a_resposta(pasta_de_dados: Any, caminho: str, sid: str,
                       corpo: Any, agora: str) -> None:
    """A resposta INTEIRA do aparelho, uma linha por pedido — 23/10/2026. Nunca
    estoura: anotar não pode derrubar um selo que já saiu e já está no razão.

    O CÓDIGO DE VALIDAÇÃO SE PERDIA AQUI: o leitor guardava quatro campos e o
    resto da resposta morria nesta função. A linha leva SID, caminho e o corpo
    como veio, para se saber o que o aparelho disse mesmo quando o contrato
    não diz."""
    try:
        from pathlib import Path as _Path
        alvo = _Path(str(pasta_de_dados)) / "selador_respostas.jsonl"
        with open(alvo, "a", encoding="utf-8") as f:
            f.write(json.dumps({"em": agora, "sid": sid, "caminho": caminho,
                                "corpo": corpo}, ensure_ascii=False,
                               default=str) + "\n")
    except Exception:                                          # noqa: BLE001
        _LOG.exception("Nao anotei a resposta do selador (sid %s)", sid)


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


# De onde veio o numero que o razao ja tinha: vai na auditoria e muda a frase.
DO_APARELHO = "APARELHO"
A_MAO = "A_MAO"

# O que a auditoria guarda da linha que ja estava gravada — o bastante para
# a correicao achar o ato dono do selo sem abrir o banco.
_CAMPOS_DO_RASTRO = ("id", "tabela", "ato_id", "referencia", "sid", "caminho",
                     "atribuicao", "ambiente", "obtido_em", "obtido_por",
                     "usado_em", "cancelado_em")


def conferir_o_repetido(con, numero: str, *, iguais: dict, origem: str,
                        agora: str, usuario: str | None = None,
                        chegou: dict | None = None) -> dict:
    """O numero que o INSERT achou ja gravado: o mesmo selo, ou outro dono?
    ESCREVE (auditoria).

    EXISTE PORQUE O RAZAO DESCARTAVA EM SILENCIO (LD14, achado da IA do
    servidor no ensaio de 21/10/2026). `numero` e UNIQUE em `sd_selos`, e o
    INSERT de `selar` ignorava o conflito, calado: o aparelho podia
    devolver um numero ja gravado para outro ato que o sistema o amarrava a
    este, sem linha nova e sem rastro do que o aparelho disse.

    `iguais` sao os campos que dizem DE QUEM e o selo — quem chama escolhe,
    porque o selo do aparelho se reconhece pelo pedido (SID, caminho,
    referencia) e o digitado a mao pelo ato. Todos batem com a linha gravada:
      - e o MESMO selo chegando de novo. Nao duplica — a linha que esta la e a
        que vale —, mas registra: log e auditoria «SELO_REPETIDO», na
        transacao de quem chama. Devolve a linha gravada.
    Algum nao bate:
      - e selo de OUTRO dono. Recusa com `SeloJaGravado`, dizendo onde ele
        esta, e a linha gravada nao e tocada. A auditoria
        «SELO_REPETIDO_RECUSADO» leva o que estava gravado, o que chegou e a
        diferenca — e e gravada POR FORA (`_auditar_por_fora`), porque a
        recusa desfaz a transacao de quem chama e levaria a linha junto.

    A LINHA E LIDA PRESA (`FOR UPDATE`): quem compara e decide nao pode ver
    o selo ser vinculado ou cancelado no meio. `numero` e unico, e o
    `ORDER BY` so diz qual seria a primeira se nao fosse.
    """
    bd = banco(con)
    bd._escrita()
    gravado = bd.um(
        """SELECT * FROM sd_selos WHERE numero = %s
            ORDER BY id LIMIT 1 FOR UPDATE""", (numero,))
    if gravado is None:
        # O conflito existiu: so some se alguem APAGOU a linha no meio.
        raise SeladorIndisponivel(
            f"O selo {numero} sumiu do razão no meio da conferência. Tente "
            f"de novo — e, se repetir, avise o oficial.")
    diferencas = {campo: {"gravado": gravado.get(campo), "chegou": valor}
                  for campo, valor in iguais.items()
                  if gravado.get(campo) != valor}
    detalhes = {"numero": numero, "origem": origem,
                "gravado": {c: gravado.get(c) for c in _CAMPOS_DO_RASTRO},
                "chegou": {**iguais, **(chegou or {})}}
    if not diferencas:
        _LOG.warning("Selo %s chegou de novo (%s) com os mesmos dados: nao "
                     "duplica, fica a linha %s.", numero, origem, gravado["id"])
        if bd.tem_tabela("audit_logs"):
            _auditar(bd, acao="SELO_REPETIDO", usuario=usuario,
                     entidade_id=gravado["id"], detalhes=detalhes, agora=agora)
        return gravado
    detalhes["diferencas"] = diferencas
    _LOG.error("Selo %s recusado (%s): ja esta gravado com outros dados: %s",
               numero, origem, diferencas)
    auditado = _auditar_por_fora(bd, acao="SELO_REPETIDO_RECUSADO",
                                 usuario=usuario, entidade_id=gravado["id"],
                                 detalhes=detalhes, agora=agora)
    raise SeloJaGravado(_recado_do_repetido(numero, gravado, origem=origem,
                                            auditado=auditado))


def _recado_do_repetido(numero: str, gravado: dict, *, origem: str,
                        auditado: bool) -> str:
    """A frase da recusa: onde o selo ja esta, e que nada ali foi mexido."""
    onde = (f"no ato {gravado['ato_id']} de {gravado['tabela']}"
            if gravado.get("tabela") else "no razão, ainda sem ato")
    if gravado.get("cancelado_em"):
        onde += f", cancelado em {gravado['cancelado_em']}"
    quem = (f"O selador devolveu o selo {numero}, que já está gravado"
            if origem == DO_APARELHO else f"O selo {numero} já está gravado")
    rastro = ("a recusa ficou na auditoria" if auditado
              else "a recusa ficou no log do sistema")
    return (f"{quem} {onde}. Um selo serve a um ato só — usá-lo duas vezes "
            f"é o que a inspeção aponta. O que estava gravado ficou como "
            f"estava, e {rastro}.")


def _auditar(bd, *, acao: str, usuario: Any, entidade_id: Any,
             detalhes: dict, agora: str) -> None:
    # Quem grava é o selador da casa, a mando de quem pediu o selo (o
    # `usuario`); sem ele, o responsável pelas rotinas (26/10/2026).
    IDR.registrar(bd, ts=agora, user_id=None, username=usuario, action=acao,
                  entity_type="SD_SELO", entity_id=entidade_id,
                  details=json.dumps(detalhes, ensure_ascii=False, default=str),
                  agente="selador do sistema (conferência do selo repetido)",
                  a_mando_de=usuario or IDR.PELO_RESPONSAVEL)


def _auditar_por_fora(bd, *, acao: str, usuario: Any, entidade_id: Any,
                      detalhes: dict, agora: str) -> bool:
    """A auditoria da RECUSA, numa conexao a parte que confirma sozinha.
    Nunca estoura: devolve se gravou.

    POR QUE POR FORA: a recusa sobe como excecao, e quem chamou desfaz a
    transacao — a linha escrita nela iria junto, e a recusa ficaria sem
    rastro, que e o defeito que `conferir_o_repetido` fecha. E POR QUE NAO
    `Database.log`, a transacao propria da casa: pela ponte ela pede a trava
    unica do banco, que a transacao de quem chamou esta segurando —
    esperaria e desistiria. Esta conexao e do psycopg, sem a ponte, no mesmo
    schema: grava so a linha e confirma, sem trava nenhuma da casa.
    """
    try:
        import psycopg
        from psycopg import sql

        import banco_pg
        schema = bd.valor("SELECT current_schema() AS s")
        with psycopg.connect(banco_pg.dsn(), autocommit=True) as pg:
            pg.execute("SET lock_timeout = '2s'")
            pg.execute(sql.SQL("SET search_path TO {}, public").format(
                sql.Identifier(schema)))
            outro = banco(pg)
            if not outro.tem_tabela("audit_logs"):
                return False
            _auditar(outro, acao=acao, usuario=usuario,
                     entidade_id=entidade_id, detalhes=detalhes, agora=agora)
        return True
    except Exception:                                          # noqa: BLE001
        _LOG.exception("A auditoria %s do selo %s nao foi gravada; fica este "
                       "log: %s", acao, detalhes.get("numero"), detalhes)
        return False


def vincular(con, numero: str, *, tabela: str,
             ato_id: int, agora: str) -> None:
    """Diz que o selo foi USADO por este ato. ESCREVE.

    Chamado quando o ato fica pronto, e nao quando o selo chega. Enquanto nao
    for chamado, o selo aparece como obtido e nao usado — que e a verdade.
    """
    banco(con).escrever(
        """UPDATE sd_selos SET tabela = %s, ato_id = %s, usado_em = %s
            WHERE numero = %s AND usado_em IS NULL""",
        (tabela, int(ato_id), agora, numero))


def orfaos(con, limite: int = 200) -> list[dict]:
    """Selos obtidos, nao usados e nao cancelados. So LE.

    E a tela que faltava no E-Oficio. La havia 1.304 destes, 5% de tudo, e
    ninguem sabia — porque nao havia onde olhar.
    """
    return banco(con).ler(
        """SELECT * FROM sd_selos
            WHERE usado_em IS NULL AND cancelado_em IS NULL
            ORDER BY obtido_em DESC, id LIMIT %s""", (limite,))


def registrar_cancelamento(con, numero: str, *,
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
    banco(con).escrever(
        """UPDATE sd_selos SET cancelado_em = %s, cancelado_por = %s,
               motivo_cancelamento = %s WHERE numero = %s""",
        (agora, usuario, razao, numero))


# ------------------------------------------------------------- o teste


def testar(con, pasta_de_dados: Any, *, agora: str,
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
