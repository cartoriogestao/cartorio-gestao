"""O CONVITE DA PESQUISA CHEGA AO CLIENTE — o e-mail da automação e a página na VPS.

    «aceito a proposta, faça o PR curto» — o oficial, 26/10/2026.

O QUE FALTAVA
    A pesquisa de satisfação (`satisfacao`) põe o convite numa fila
    (`ou_satisfacao_convites`, um por canal, com o telefone ou o e-mail do
    próprio protocolo) e NADA enviava; e o link, se saísse, só abriria na rede
    da casa. Este módulo liga as duas pontas, sem inventar canal nem servidor:

    1. O E-MAIL sai pelo MESMO envio dos avisos de andamento ao cliente — o
       SMTP da automação (`automacao_avisos.configuracao_de_email`,
       `automacao_avisos.ENVIO["email"]`, a senha em `avisos.cred`). O WhatsApp
       continua na fila, com a mesma frase dos avisos de andamento
       (`andamento_avisos.SEM_MODELO_DA_META`): sem modelo aprovado pela Meta,
       nada sai sozinho por ele.
    2. A PÁGINA mora na VPS, ao lado do portal do cliente
       (`vps/pesquisa/pesquisa_vps.py`), e o servidor da casa continua fora da
       internet: ele EMPURRA o convite para lá e PUXA as respostas de volta —
       o desenho do portal (`portal_cliente`) e da caixa-postal do WhatsApp
       (`wa_puxar`). A conexão é sempre de SAÍDA, em HTTPS, com o token do
       portal (`portal.cred`), que nunca entra no banco.

O QUE VAI À VPS — E O QUE NÃO VAI
    Vai, por convite: a CHAVE (sha256 de um código de 32 caracteres), a
    atribuição e o dia do convite, mais a data em que ele vence. NÃO vai:
    nome, telefone, e-mail, número do protocolo, atendente. A VPS devolve só a
    chave, a nota, o comentário e o dia da resposta.

    O CÓDIGO NÃO SE GUARDA EM LUGAR NENHUM. Ele é um HMAC do número interno do
    protocolo com o segredo da instalação (`secret.key`), recalculado na hora
    de mandar o e-mail — a regra da pesquisa («um link guardado no banco seria
    um voto pronto para quem lesse a tabela») vale aqui também. O banco da
    casa e o da VPS guardam só o hash; o HMAC usa um sal próprio, e por isso o
    hash não se cruza com a `protocolo_chave` das avaliações.

    UM CÓDIGO POR PROTOCOLO, e não por canal: no dia em que o WhatsApp tiver
    modelo, os dois convites levam o mesmo link, e a mesma ida ao balcão
    continua valendo uma avaliação (o índice único de `ou_satisfacao`).

A RODADA (`rodar`, o processo SATISFACAO_CONVITES da automação, DESLIGADO)
    a. EMPURRA à VPS os convites por e-mail que estão na fila e ainda não
       foram — antes do e-mail: link que chega antes do convite é página que
       diz «não achei».
    b. MANDA os e-mails, até `max_por_rodada` por rodada (teto), cada um com
       até `max_tentativas` tentativas, uma por rodada. Convite vencido (30
       dias, `satisfacao.DIAS_DO_CONVITE`) não sai.
    c. PUXA as respostas e as grava pela mesma `satisfacao.registrar` da
       página da casa — com o atendente e a atribuição do convite, e a chave
       do protocolo que impede a segunda avaliação —, e então CONFIRMA à VPS o
       que gravou, para ela apagar.
    O que falta (o e-mail da automação ou o portal ainda não instalados, o
    endereço ou o token em branco) NÃO QUEBRA a rodada: o convite fica na
    fila com o motivo escrito, e sai na rodada em que o motivo acabar.

    A REDE FICA FORA DE TODA TRANSAÇÃO, como nos avisos de andamento: o SMTP e
    o HTTPS têm prazo de dezenas de segundos, e isso dentro de
    `db.transaction()` seguraria a casa inteira.

QUEM FAZ, E A MANDO DE QUEM (regra da casa desde 26/10/2026)
    Cada envio e cada resposta gravada vão à auditoria sem usuário, e por
    isso com `agente` (o robô do processo, ou «automacao:<código>») e
    `a_mando_de` (quem ligou o processo na central) no detalhe — a função de
    auditoria deste ramo (`Database.log`) não tem colunas para os dois. O
    e-mail do cliente e o código NUNCA vão à auditoria.

PostgreSQL nativo, pelo `bd_nativo`. Data calculada no Python.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import satisfacao as SAT
from bd_nativo import banco

_LOG = logging.getLogger("cartorio.satisfacao_envio")

CODIGO_DO_PROCESSO = "SATISFACAO_CONVITES"
#: O endereço público da página da pesquisa na VPS (ex.: https://<host>/pesquisa).
#: Configuração, e não código: o host não se escreve em lugar nenhum.
CHAVE_URL = "satisfacao_vps_url"

#: O teto de e-mails por rodada. Uma rodada que encontrasse mil convites na
#: fila (um ajuste de configuração esquecido por semanas) mandaria mil
#: e-mails de uma vez pelo SMTP da casa — que o provedor trata como spam.
MAX_POR_RODADA_PADRAO = 30
MAX_POR_RODADA_LIMITES = (1, 200)
#: Quantas vezes um e-mail que falhou é tentado, uma por rodada.
MAX_TENTATIVAS_PADRAO = 3
MAX_TENTATIVAS_LIMITES = (1, 10)
#: Convites por chamada à VPS (a VPS recusa mais que `CONVITES_POR_CHAMADA`).
LOTE_DO_EMPURRAO = 100
TIMEOUT = 30

CAMINHO_CONVITES = "/api/convites"
CAMINHO_RESPOSTAS = "/api/respostas"
CAMINHO_CONFIRMAR = "/api/respostas/confirmar"
#: O sal do código do convite. Diferente do de `chave_do_protocolo`, de
#: propósito: a chave que vai à VPS não se cruza com a da avaliação gravada.
SAL_DO_CODIGO = "cg-satisfacao-vps"
RE_CHAVE = re.compile(r"^[0-9a-f]{64}$")
#: A atribuição que NÃO vai à VPS, nem como palavra: o protesto tem sigilo
#: próprio (a regra dos avisos de andamento). O convite vai em branco, e a
#: resposta volta para a atribuição certa — quem sabe é a fila daqui.
ATRIBUICOES_SEM_NOME_NA_VPS = frozenset({"PROTESTO"})

#: As frases do motivo — a fila e o relato mostram exatamente estas.
SEM_EMAIL_DA_AUTOMACAO = ("e-mail da automação não instalado (o envio é o dos avisos de "
                          "andamento: entra com a central da automação)")
SEM_PORTAL = "portal não instalado (a página da pesquisa mora na VPS, ao lado do portal do cliente)"
SEM_URL = ("endereço da pesquisa na VPS não configurado (Administrativo → Pesquisa de "
           "satisfação)")
SEM_TOKEN = "token da VPS não gravado (é o mesmo do portal do cliente)"
SEM_SEGREDO = "segredo da instalação (secret.key) não encontrado na pasta de dados"
SEM_SMTP = "o e-mail não está configurado (Administrativo → Automação → Configuração)"
VENCIDO = "o convite venceu antes de sair — convite vencido não se manda"
try:                                    # a MESMA frase dos avisos de andamento (PR #26)
    from andamento_avisos import SEM_MODELO_DA_META
except ImportError:                     # sem os avisos de andamento instalados
    SEM_MODELO_DA_META = ("WhatsApp sem modelo aprovado pela Meta: o envio automático fica "
                          "desligado até a casa ter o modelo (texto livre fora da janela de 24 h "
                          "a Meta recusa).")


def _iso(quando: datetime) -> str:
    return quando.replace(microsecond=0).isoformat()


def _faixa(valor: Any, padrao: int, limites: tuple[int, int]) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return padrao
    return max(limites[0], min(limites[1], n))


# ------------------------------------------------------------------ o código do convite


def segredo_da_instalacao(pasta_dados: Any) -> str:
    """O `secret.key` da pasta de dados — o mesmo com que o servidor assina o
    convite e calcula a chave do protocolo. Vazio quando não há. Só lê."""
    try:
        return (Path(pasta_dados or ".") / "secret.key").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def codigo_do_convite(segredo: str, protocolo_id: int) -> str:
    """O código do link: 32 caracteres (A-Z, 2-7). Recalculado, NUNCA guardado."""
    bruto = hmac.new(str(segredo).encode("utf-8"),
                     f"{SAL_DO_CODIGO}:{int(protocolo_id)}".encode("ascii"),
                     hashlib.sha256).digest()[:20]
    return base64.b32encode(bruto).decode("ascii")


def chave_na_vps(codigo: str) -> str:
    """O que a VPS guarda do código: o sha256. É o mesmo cálculo da VPS."""
    return hashlib.sha256(str(codigo or "").strip().upper().encode("ascii", "replace")).hexdigest()


def link_do_convite(url: str, codigo: str) -> str:
    return f"{str(url).rstrip('/')}/r/{codigo}"


def vence_em(criado_em: Any) -> date | None:
    """O último dia em que o convite vale. Só calcula."""
    try:
        dia = date.fromisoformat(str(criado_em or "")[:10])
    except ValueError:
        return None
    return dia + timedelta(days=SAT.DIAS_DO_CONVITE)


def texto_do_convite(serventia: str, link: str, validade: date) -> tuple[str, str]:
    """O assunto e o corpo do e-mail. SÓ o convite e o link: sem CPF, sem nome
    de ninguém, sem valor, sem número de protocolo. Só calcula."""
    nome = str(serventia or "").strip() or "A serventia"
    assunto = f"Pesquisa de satisfação — {nome}"
    corpo = (f"Olá!\n\n"
             f"Você foi atendido(a) recentemente por {nome}. Queremos saber como foi o "
             f"atendimento: é uma nota de 1 a 5 e, se quiser, um comentário. A resposta é "
             f"anônima e leva menos de um minuto.\n\n"
             f"Responda por este endereço:\n{link}\n\n"
             f"O convite vale até {validade.strftime('%d/%m/%Y')} e pode ser respondido uma "
             f"vez.\n\n"
             f"Esta mensagem foi enviada automaticamente; não é preciso respondê-la. A "
             f"serventia não pede pagamento, senha nem dados pessoais por este canal.\n\n"
             f"{nome}\n")
    return assunto, corpo


# ------------------------------------------------------------------ as outras pontas, guardadas


def email_da_automacao():
    """O módulo de e-mail da automação (PR #11), ou None se não instalado."""
    try:
        import automacao_avisos as AV
    except ImportError:
        return None
    return AV


def portal():
    """O módulo do portal do cliente (PR #29), ou None se não instalado."""
    try:
        import cofre_cred as COFRE
        import portal_cliente as PORTAL
    except ImportError:
        return None
    if not hasattr(COFRE, "PORTAL"):
        return None
    return PORTAL


def _token_da_vps(con) -> str:
    import cofre_cred as COFRE
    PORTAL = portal()
    if PORTAL is None:
        return ""
    try:
        return COFRE.ler_segredo(con, COFRE.PORTAL, PORTAL.CHAVE_TOKEN) or ""
    except Exception:                                   # noqa: BLE001 — sem token
        return ""


def _setting(con, chave: str) -> str:
    linha = banco(con).um("SELECT value FROM settings WHERE key = %s", (chave,))
    return str(linha["value"]).strip() if linha and linha["value"] is not None else ""


def endereco_da_vps(con) -> str:
    """O endereço configurado, conferido pela régua do portal (HTTPS, sem «?»,
    «#» nem usuário). Levanta `ValueError` com a frase pronta. Só lê."""
    url = _setting(con, CHAVE_URL)
    PORTAL = portal()
    if PORTAL is None or not url:
        return url
    return PORTAL.endereco_valido(url)


def gravar_endereco(con, url: Any) -> str:
    """Grava o endereço da página da pesquisa na VPS. ESCREVE. Vazio apaga.

    Com o portal instalado, a régua é a dele (`portal_cliente.endereco_valido`);
    sem ele, a mesma exigência mínima: https://."""
    texto = str(url or "").strip().rstrip("/")
    PORTAL = portal()
    if texto:
        if PORTAL is not None:
            texto = PORTAL.endereco_valido(texto)
        elif not texto.startswith("https://") or "?" in texto or "#" in texto:
            raise SAT.SatisfacaoError("O endereço da pesquisa tem de começar com https:// e "
                                      "não leva «?» nem «#».")
    banco(con).escrever(
        """INSERT INTO settings(key, value) VALUES (%s, %s)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""", (CHAVE_URL, texto))
    return texto


# ------------------------------------------------------------------ o transporte


def _http(metodo: str, url: str, token: str, corpo: bytes | None = None,
          timeout: float = TIMEOUT) -> tuple[int, str]:
    req = urllib.request.Request(url, data=corpo, method=metodo)
    if corpo is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read(4 * 1024 * 1024).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return int(e.code), e.read(4096).decode("utf-8", "replace")
    except Exception as e:                              # noqa: BLE001 — vira motivo
        return 0, str(e)


#: Quem fala com a VPS. O teste troca por um falso.
HTTP: dict[str, Callable] = {"chamar": _http}


# ------------------------------------------------------------------ a auditoria


def quem_faz(processo: dict | None) -> tuple[str, str]:
    """(agente, a_mando_de) desta rodada. Só calcula."""
    p = processo or {}
    agente = str(p.get("robo_oficial") or "").strip() or \
        f"automacao:{p.get('codigo') or CODIGO_DO_PROCESSO}"
    mando = (str(p.get("alterado_por") or p.get("criado_por") or "").strip()
             or "oficial (processo ligado na central da automação)")
    return agente, mando


def _auditar(db, acao: str, entidade: str, entidade_id: Any, detalhe: dict, *,
             agente: str, a_mando_de: str) -> None:
    """Uma linha de auditoria sem usuário, com `agente` e `a_mando_de` no
    detalhe. Auditoria que falha não derruba o envio (vai ao log)."""
    log = getattr(db, "log", None)
    if not callable(log):
        return
    try:
        log(None, agente[:80], acao, entidade, entidade_id,
            {"agente": agente, "a_mando_de": a_mando_de, **detalhe})
    except Exception as erro:                          # noqa: BLE001
        _LOG.warning("auditoria da pesquisa não gravou (%s): %s", acao, erro)


# ------------------------------------------------------------------ a fila


def _por_email_na_fila(con, max_tentativas: int) -> list[dict]:
    return [dict(x) for x in banco(con).ler(
        """SELECT id, protocolo_id, destino, atendente_id, atribuicao, situacao, criado_em,
                  erro, tentativas, chave_vps, na_vps_em
             FROM ou_satisfacao_convites
            WHERE canal = 'EMAIL' AND situacao = 'NA_FILA' AND tentativas < %s
            ORDER BY id""", (int(max_tentativas),))]


def a_empurrar(con, *, hoje: date, segredo: str, max_tentativas: int) -> list[dict]:
    """Os convites que a VPS ainda não tem, um por protocolo, já no formato
    dela. SÓ LÊ. Só os que vão sair por e-mail e ainda valem."""
    vistos: dict[int, dict] = {}
    for x in _por_email_na_fila(con, max_tentativas):
        validade = vence_em(x["criado_em"])
        if x["na_vps_em"] or validade is None or validade < hoje:
            continue
        pid = int(x["protocolo_id"])
        if pid in vistos:
            continue
        atribuicao = str(x["atribuicao"] or "").strip()[:20]
        if atribuicao.upper() in ATRIBUICOES_SEM_NOME_NA_VPS:
            atribuicao = ""
        vistos[pid] = {"protocolo_id": pid,
                       "pacote": {"chave": chave_na_vps(codigo_do_convite(segredo, pid)),
                                  "atribuicao": atribuicao,
                                  "dia": str(x["criado_em"])[:10],
                                  "expira_em": validade.isoformat()}}
    return list(vistos.values())


def _gravar(db, convite_id: int, **campos) -> None:
    with db.transaction() as con:
        sets = ", ".join(f"{k} = %s" for k in campos)
        banco(con).escrever(f"UPDATE ou_satisfacao_convites SET {sets} WHERE id = %s",
                            (*campos.values(), int(convite_id)))


def _motivo(db, x: dict, motivo: str) -> None:
    """Deixa o convite na fila com o motivo — sem gastar tentativa."""
    if x.get("erro") != motivo:
        _gravar(db, x["id"], erro=motivo)
        x["erro"] = motivo


# ------------------------------------------------------------------ as três partes da rodada


def empurrar(db, *, url: str, token: str, segredo: str, hoje: date, agora: datetime,
             max_tentativas: int) -> dict:
    """Leva à VPS os convites novos. ESCREVE (a marca de que foram)."""
    with db.connect() as con:
        itens = a_empurrar(con, hoje=hoje, segredo=segredo, max_tentativas=max_tentativas)
    conta = {"empurrados": 0, "motivo": ""}
    for inicio in range(0, len(itens), LOTE_DO_EMPURRAO):
        lote = itens[inicio:inicio + LOTE_DO_EMPURRAO]
        corpo = json.dumps({"convites": [i["pacote"] for i in lote]},
                           ensure_ascii=False).encode("utf-8")
        status, resposta = HTTP["chamar"]("POST", url + CAMINHO_CONVITES, token, corpo)
        if not 200 <= status < 300:
            conta["motivo"] = f"a VPS respondeu HTTP {status} ao receber os convites: {resposta[:200]}"
            return conta
        with db.transaction() as con:
            bd = banco(con)
            for i in lote:
                bd.escrever("""UPDATE ou_satisfacao_convites SET chave_vps = %s, na_vps_em = %s
                                WHERE protocolo_id = %s""",
                            (i["pacote"]["chave"], _iso(agora), i["protocolo_id"]))
        conta["empurrados"] += len(lote)
    return conta


def enviar(db, *, url: str | None, segredo: str, hoje: date, agora: datetime,
           pasta_dados: Any, bloqueio: str, max_por_rodada: int, max_tentativas: int,
           agente: str, a_mando_de: str) -> dict:
    """Manda os e-mails da fila. **A rede fica fora de toda transação.**

    `bloqueio` é o motivo por que a página na VPS não está pronta («portal não
    instalado», endereço ou token em branco, a VPS fora): com ele, o convite
    que ainda não chegou à VPS não sai — um link que não abre é pior que
    convite nenhum."""
    conta = {"enviados": 0, "falhas": 0, "desistidos": 0, "vencidos": 0, "esperando": 0,
             "fora_do_teto": 0, "motivo_da_espera": ""}
    AV = email_da_automacao()
    with db.connect() as con:
        fila = _por_email_na_fila(con, max_tentativas)
        cfg = AV.configuracao_de_email(con) if AV is not None else None
    serventia = ""
    try:
        import serventia as SERV
        serventia = str(SERV.dados(db.get_settings).get("unit_name") or "")
    except Exception:                                   # noqa: BLE001 — nome genérico
        serventia = ""
    senha: list[str] = []
    tentados = 0
    for x in fila:
        validade = vence_em(x["criado_em"])
        if validade is None or validade < hoje:
            _gravar(db, x["id"], situacao="FALHOU", erro=VENCIDO)
            conta["vencidos"] += 1
            continue
        # O convite que JÁ está na VPS sai mesmo se o empurrão desta rodada
        # falhou: o link dele abre. O que não está, espera o motivo acabar.
        pronto_na_vps = bool(x["na_vps_em"] and url and segredo)
        espera = (SEM_EMAIL_DA_AUTOMACAO if AV is None
                  else SEM_SMTP if not (cfg or {}).get("host")
                  else "" if pronto_na_vps
                  else bloqueio or "o convite ainda não chegou à página da VPS")
        if espera:
            _motivo(db, x, espera)
            conta["esperando"] += 1
            conta["motivo_da_espera"] = conta["motivo_da_espera"] or espera
            continue
        if tentados >= max_por_rodada:
            conta["fora_do_teto"] += 1
            continue
        tentados += 1
        pid = int(x["protocolo_id"])
        assunto, corpo = texto_do_convite(
            serventia, link_do_convite(url or "", codigo_do_convite(segredo, pid)), validade)
        tentativa = int(x["tentativas"] or 0) + 1
        try:
            if not senha:
                # A senha do SMTP é a da automação (`avisos.cred`) — a mesma
                # chamada que os avisos de andamento fazem.
                senha.append(AV._senha_do_smtp(pasta_dados, cfg))
            AV.ENVIO["email"](dict(cfg, destinos=[x["destino"]]), senha[0],
                              assunto=assunto, corpo=corpo)
        except Exception as erro:                      # noqa: BLE001 — registra e segue
            desiste = tentativa >= max_tentativas
            _gravar(db, x["id"], situacao="FALHOU" if desiste else "NA_FILA",
                    erro=f"{type(erro).__name__}: {erro}"[:500], tentativas=tentativa,
                    tentado_em=_iso(agora))
            conta["desistidos" if desiste else "falhas"] += 1
            _auditar(db, "SATISFACAO_CONVITE_FALHOU", "ou_satisfacao_convites", x["id"],
                     {"canal": "EMAIL", "protocolo_id": pid, "tentativa": tentativa,
                      "desistiu": desiste, "erro": type(erro).__name__},
                     agente=agente, a_mando_de=a_mando_de)
            continue
        _gravar(db, x["id"], situacao="ENVIADO", erro=None, tentativas=tentativa,
                tentado_em=_iso(agora), enviado_em=_iso(agora))
        conta["enviados"] += 1
        # Sem o e-mail do cliente e sem o link: o protocolo e o canal bastam.
        _auditar(db, "SATISFACAO_CONVITE_ENVIADO", "ou_satisfacao_convites", x["id"],
                 {"canal": "EMAIL", "protocolo_id": pid, "tentativa": tentativa,
                  "vale_ate": validade.isoformat()},
                 agente=agente, a_mando_de=a_mando_de)
    return conta


def marcar_whatsapp(db) -> int:
    """O WhatsApp fica na fila com a frase da Meta. ESCREVE só a frase. Devolve quantos."""
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever("""UPDATE ou_satisfacao_convites SET erro = %s
                        WHERE canal = 'WHATSAPP' AND situacao = 'NA_FILA'
                          AND (erro IS NULL OR erro <> %s)""",
                    (SEM_MODELO_DA_META, SEM_MODELO_DA_META))
        return int(bd.valor("""SELECT COUNT(*) FROM ou_satisfacao_convites
                                WHERE canal = 'WHATSAPP' AND situacao = 'NA_FILA'""") or 0)


def _dia_da_resposta(texto: Any, hoje: date) -> date:
    try:
        dia = date.fromisoformat(str(texto or "")[:10])
    except ValueError:
        return hoje
    return dia if dia <= hoje else hoje


def puxar(db, *, url: str, token: str, segredo: str, hoje: date, agente: str,
          a_mando_de: str) -> dict:
    """Traz as respostas da VPS, grava cada uma e confirma o que gravou. ESCREVE."""
    conta = {"registradas": 0, "repetidas": 0, "recusadas": 0, "sem_convite": 0,
             "motivo": ""}
    status, bruto = HTTP["chamar"]("GET", url + CAMINHO_RESPOSTAS, token, None)
    if not 200 <= status < 300:
        conta["motivo"] = f"a VPS respondeu HTTP {status} ao entregar as respostas: {bruto[:200]}"
        return conta
    try:
        respostas = json.loads(bruto).get("respostas")
    except (ValueError, AttributeError):
        respostas = None
    if not isinstance(respostas, list):
        conta["motivo"] = "a VPS devolveu respostas fora do formato"
        return conta
    confirmar: list[str] = []
    for r in respostas:
        chave = str((r or {}).get("chave") or "") if isinstance(r, dict) else ""
        if not RE_CHAVE.match(chave):
            conta["recusadas"] += 1
            continue
        with db.connect() as con:
            convite = banco(con).um(
                """SELECT protocolo_id, atendente_id, atribuicao FROM ou_satisfacao_convites
                    WHERE chave_vps = %s ORDER BY id LIMIT 1""", (chave,))
        if not convite:
            # Não se confirma: a VPS guarda até vencer, e quem conferir acha.
            conta["sem_convite"] += 1
            continue
        pid = int(convite["protocolo_id"])
        try:
            with db.transaction() as con:
                novo = SAT.registrar(
                    con, nota=r.get("nota"), comentario=r.get("comentario") or "",
                    dia=_dia_da_resposta(r.get("dia"), hoje),
                    convite={"atendente_id": convite["atendente_id"],
                             "atribuicao": convite["atribuicao"]},
                    protocolo_chave=SAT.chave_do_protocolo(segredo, pid))
        except SAT.SatisfacaoError as erro:
            # Já avaliado (pela página da casa, ou repetida) ou nota inválida:
            # a VPS pode apagar — gravar de novo nunca vai dar certo.
            conta["repetidas" if "já foi avaliado" in str(erro) else "recusadas"] += 1
            confirmar.append(chave)
            continue
        except Exception as erro:                      # noqa: BLE001 — tenta na próxima
            _LOG.warning("resposta da pesquisa não gravou: %s", erro)
            continue
        conta["registradas"] += 1
        confirmar.append(chave)
        # Sem a nota e sem o comentário: a avaliação está na tabela dela.
        _auditar(db, "SATISFACAO_RESPOSTA_DA_VPS", "ou_satisfacao", novo,
                 {"origem": "VPS", "protocolo_id": pid}, agente=agente, a_mando_de=a_mando_de)
    if confirmar:
        corpo = json.dumps({"chaves": confirmar}).encode("utf-8")
        status, bruto = HTTP["chamar"]("POST", url + CAMINHO_CONFIRMAR, token, corpo)
        if not 200 <= status < 300:
            # Gravado aqui e não apagado lá: na próxima rodada volta como
            # «repetida» e é confirmado de novo. Nada se perde nem dobra.
            conta["motivo"] = f"a VPS respondeu HTTP {status} à confirmação: {bruto[:200]}"
    return conta


# ------------------------------------------------------------------ o processo da automação


def _resultado(situacao: str, relato: str, achados: list, acoes: list) -> dict:
    try:
        import automacao_processos as PROC
    except ImportError:
        return {"situacao": situacao, "relato": relato, "achados": achados, "acoes": acoes}
    return PROC.resultado(situacao, relato, achados, acoes)


def rodar(ctx) -> dict:
    """O processo SATISFACAO_CONVITES: empurra, manda e puxa. Relato em números."""
    with ctx.db.transaction() as con:
        SAT.init_satisfacao_schema(con)
    p = dict(getattr(ctx, "parametros", None) or {})
    teto = _faixa(p.get("max_por_rodada"), MAX_POR_RODADA_PADRAO, MAX_POR_RODADA_LIMITES)
    tentativas = _faixa(p.get("max_tentativas"), MAX_TENTATIVAS_PADRAO, MAX_TENTATIVAS_LIMITES)
    agente, mando = quem_faz(getattr(ctx, "processo", None))
    hoje, agora = ctx.hoje, ctx.agora
    segredo = segredo_da_instalacao(ctx.pasta_dados)

    # O que impede a página da VPS de estar pronta — o motivo, ou vazio.
    bloqueio, url, token = "", "", ""
    if portal() is None:
        bloqueio = SEM_PORTAL
    else:
        with ctx.db.connect() as con:
            try:
                url = endereco_da_vps(con)
            except ValueError as erro:
                bloqueio = str(erro)
            token = _token_da_vps(con)
        if not bloqueio:
            bloqueio = SEM_URL if not url else SEM_TOKEN if not token else ""
    if not bloqueio and not segredo:
        bloqueio = SEM_SEGREDO

    empurrao = {"empurrados": 0, "motivo": ""}
    if not bloqueio:
        empurrao = empurrar(ctx.db, url=url, token=token, segredo=segredo, hoje=hoje,
                            agora=agora, max_tentativas=tentativas)
    envio = enviar(ctx.db, url=url, segredo=segredo, hoje=hoje, agora=agora,
                   pasta_dados=ctx.pasta_dados, bloqueio=bloqueio or empurrao["motivo"],
                   max_por_rodada=teto, max_tentativas=tentativas, agente=agente,
                   a_mando_de=mando)
    whats = marcar_whatsapp(ctx.db)
    volta = {"registradas": 0, "repetidas": 0, "recusadas": 0, "sem_convite": 0, "motivo": ""}
    if not bloqueio:
        volta = puxar(ctx.db, url=url, token=token, segredo=segredo, hoje=hoje,
                      agente=agente, a_mando_de=mando)

    relato = (f"Convites por e-mail nesta rodada: {envio['enviados']} enviado(s), "
              f"{envio['falhas']} falha(s) que voltam a ser tentadas, {envio['desistidos']} "
              f"desistido(s) após {tentativas} tentativa(s), {envio['vencidos']} vencido(s) "
              f"sem sair, {envio['fora_do_teto']} para a próxima rodada (teto de {teto}). "
              f"Esperando: {envio['esperando']}"
              + (f" — {envio['motivo_da_espera']}" if envio["motivo_da_espera"] else "")
              + f". Convites levados à VPS: {empurrao['empurrados']}. Respostas trazidas: "
              f"{volta['registradas']} gravada(s), {volta['repetidas']} já avaliada(s), "
              f"{volta['recusadas']} recusada(s), {volta['sem_convite']} sem convite aqui. "
              f"WhatsApp na fila: {whats} (sem modelo aprovado pela Meta).")
    problemas = [m for m in (empurrao["motivo"], volta["motivo"]) if m]
    if problemas:
        relato += " Problema com a VPS: " + "; ".join(problemas) + "."
    achados = [{"enviados": envio["enviados"], "falhas": envio["falhas"],
                "desistidos": envio["desistidos"], "vencidos": envio["vencidos"],
                "esperando": envio["esperando"], "fora_do_teto": envio["fora_do_teto"],
                "na_vps": empurrao["empurrados"], "respostas": volta["registradas"],
                "repetidas": volta["repetidas"], "whatsapp_sem_modelo": whats,
                "bloqueio": bloqueio}]
    acoes = ([{"acao": "mandou convites da pesquisa por e-mail", "quantos": envio["enviados"]}]
             if envio["enviados"] else [])
    if volta["registradas"]:
        acoes.append({"acao": "gravou respostas da pesquisa vindas da VPS",
                      "quantos": volta["registradas"]})
    if problemas or envio["falhas"] or envio["desistidos"] or envio["esperando"]:
        return _resultado("AVISO", relato, achados, acoes)
    return _resultado("OK", relato, achados, acoes)


_UTEIS = [0, 1, 2, 3, 4]

#: O processo que este módulo traz para a central da automação
#: (`automacao_processos.MODULOS_COM_PROCESSOS` — a máquina do merge acrescenta
#: «satisfacao_envio» à tupla, ver o PR). Nasce DESLIGADO, como todos.
CATALOGO = (
    {"codigo": CODIGO_DO_PROCESSO, "nome": "Convites da pesquisa de satisfação",
     # O nome sai da própria função: renomeá-la não deixa o catálogo apontando
     # para o vazio (e é por aqui que o varredor de função órfã a alcança).
     "setor": "GESTAO", "funcao": f"satisfacao_envio.{rodar.__name__}", "timeout_s": 600,
     "agenda": {"dias": _UTEIS, "intervalo_min": 30, "janela": ["08:00", "18:00"]},
     "parametros": {"max_por_rodada": MAX_POR_RODADA_PADRAO,
                    "max_tentativas": MAX_TENTATIVAS_PADRAO},
     "descricao": "De 30 em 30 minutos, em dia útil: leva à página da pesquisa na VPS os "
                  "convites novos (só a chave, a atribuição e a data), manda o convite por "
                  "e-mail pelo SMTP da automação (até 30 por rodada, 3 tentativas) e traz as "
                  "respostas para o relatório da pesquisa. Sem CPF, nome nem valor. "
                  "WhatsApp fica na fila até haver modelo aprovado pela Meta."},
)
