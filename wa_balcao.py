"""Dominio do Balcao WhatsApp — classificar, rascunhar, gravar entrada, enviar.

A ROTA SO LIGA OS FIOS. O webhook local (teste ou reenvio da caixa-postal)
chama `aplicar_entrada`. A tela le o que ja esta no SQLite.

Envio a Cloud API e no botao do escrevente — e, desde 26/10/2026, tambem pelo
atendente com IA (`wa_atendente`), so nos quatro casos que o oficial liberou e
so com o interruptor geral ligado (ele nasce desligado). O resto continua
rascunho conferido por pessoa.
Nunca logar access_token, app_secret nem caixa_segredo — e, desde o LX14, eles
nem moram no banco: `ler_config`/`gravar_config` os mandam ao cofre
(`whatsapp.cred`, ver `wa_schema.SEGREDOS` e `cofre_cred`).

Idempotencia: a mesma `meta_id` nao cria segunda mensagem.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Callable
from unicodedata import normalize

from bd_nativo import banco

import cofre_cred as COFRE
import serventia as SERV
import wa_fila as FILA
import wa_schema as WA
import wa_textos as TEXTOS

DIR_IN = "in"
DIR_OUT = "out"
DIR_RASCUNHO = "rascunho"

_ISO = "%Y-%m-%dT%H:%M:%S"
GRAPH_VER = "v21.0"
TIMEOUT_ENVIO = 8


class EnvioErro(Exception):
    """A Graph recusou ou nao respondeu. Nao inventa envio."""


def agora_iso() -> str:
    return datetime.now().replace(microsecond=0).strftime(_ISO)


def _sem_acento(texto: str) -> str:
    n = normalize("NFD", texto or "")
    return "".join(c for c in n if not (0x300 <= ord(c) <= 0x36F)).lower()


def classificar(texto: str) -> str:
    """Etiqueta por palavra-chave em portugues. Sem modelo pago."""
    t = _sem_acento(texto)
    if not t.strip():
        return "outros"
    if any(p in t for p in ("protesto", "titulo", "edital")):
        return "protesto"
    if any(p in t for p in (
        "certidao", "certidoes", "nascimento", "casamento", "obito",
    )):
        return "certidao"
    if any(p in t for p in ("firma", "reconhecer", "reconhecimento")):
        return "firma"
    if "preciso levar" in t or "documentos" in t or "documento" in t:
        return "documentos"
    if any(p in t for p in ("horario", "abre", "fecha", "expediente", "funcionamento")):
        return "horario"
    if any(p in t for p in ("endereco", "onde fica", "onde voc", "localizacao")):
        return "endereco"
    return "outros"


def rascunhar(texto: str, etiqueta: str | None, serventia: Any = None,
              con: Any = None) -> str:
    """Rascunho curto no tom de cartorio. Nao envia. Nao inventa horario.

    Com `con`, o texto e o ajuste da casa no papel CAIXA_WHATSAPP (LF06F);
    sem ele, o padrao da base.
    """
    et = (etiqueta or "outros").strip().lower() or "outros"
    if et not in TEXTOS.POR_ETIQUETA:
        et = "outros"
    fn = TEXTOS.POR_ETIQUETA[et]
    return fn(serventia, con=con)


def ler_config(con: Any, chave: str) -> str:
    if chave in WA.SEGREDOS:
        return COFRE.ler_segredo(con, COFRE.WHATSAPP, chave).strip()
    linha = banco(con).um(
        "SELECT valor FROM wa_config WHERE chave=%s", (chave,)
    )
    if not linha:
        return ""
    return (linha["valor"] or "").strip()


def gravar_config(con: Any, chave: str, valor: str) -> None:
    """Grava uma configuracao. O segredo vai ao cofre, e nao ao banco."""
    if chave in WA.SEGREDOS:
        COFRE.gravar_segredo(con, COFRE.WHATSAPP, chave, valor)
        return
    banco(con).escrever(
        "INSERT INTO wa_config(chave, valor) VALUES (%s, %s) "
        "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
        (chave, valor or ""),
    )


def verify_token_salvo(con: Any) -> str:
    """O token que o GET do webhook confere. Vazio vira o de desenvolvimento."""
    t = ler_config(con, WA.CHAVE_VERIFY)
    return t or WA.VERIFY_TOKEN_DEV


def mascarar_segredo(valor: str) -> str:
    """Mostra so os ultimos 4. Nunca o token inteiro."""
    t = (valor or "").strip()
    if not t:
        return ""
    if len(t) <= 4:
        return "****"
    return "••••" + t[-4:]


def pode_enviar_meta(con: Any) -> bool:
    return bool(ler_config(con, WA.CHAVE_TOKEN) and ler_config(con, WA.CHAVE_PHONE))


def config_para_tela(con: Any) -> dict:
    """O que a tela mostra. DE SEGREDO, SO «CONFIGURADO» (LX14; B1 do LS03).

    O `verify_token` ia inteiro no `value=` do campo, e os outros com os
    ultimos quatro — para qualquer login, porque ver a tela e de todos. Agora
    nenhum pedaco de segredo chega ao HTML: so se ele esta gravado.
    """
    guardado = COFRE.ler(COFRE.pasta_do_banco(con), COFRE.WHATSAPP)
    return {
        "tem_verify_token": bool(guardado.get(WA.CHAVE_VERIFY)),
        "phone_number_id": ler_config(con, WA.CHAVE_PHONE),
        "tem_access_token": bool(guardado.get(WA.CHAVE_TOKEN)),
        "tem_app_secret": bool(guardado.get(WA.CHAVE_APP_SECRET)),
        "caixa_url": ler_config(con, WA.CHAVE_CAIXA_URL),
        "tem_caixa_segredo": bool(guardado.get(WA.CHAVE_CAIXA_SEGREDO)),
        "modo_teste": modo_teste_ligado(con),
        "pode_enviar": pode_enviar_meta(con),
        "caixa_url_documentada": WA.CAIXA_URL_DOCUMENTADA,
        "webhook_publico": WA.WEBHOOK_PUBLICO_DOCUMENTADO,
    }


def gravar_tela_config(con: Any, form: dict) -> None:
    """Grava o que a tela mandou. Campo de segredo vazio = nao altera.

    O `verify_token` tambem passou a obedecer a isso (LX14): a tela nao o
    mostra mais, e o campo vazio que antes o apagava apagaria sempre, a cada
    «guardar». Voltar ao de desenvolvimento e a caixa «apagar_verify_token».
    """
    verify = (form.get("verify_token") or "").strip()
    if verify:
        gravar_config(con, WA.CHAVE_VERIFY, verify)
    elif form.get("apagar_verify_token"):
        gravar_config(con, WA.CHAVE_VERIFY, "")
    gravar_config(con, WA.CHAVE_PHONE,
                  (form.get("phone_number_id") or "").strip())
    token = (form.get("access_token") or "").strip()
    if token:
        gravar_config(con, WA.CHAVE_TOKEN, token)
    secret = (form.get("app_secret") or "").strip()
    if secret:
        gravar_config(con, WA.CHAVE_APP_SECRET, secret)
    gravar_config(con, WA.CHAVE_CAIXA_URL,
                  (form.get("caixa_url") or "").strip())
    caixa_seg = (form.get("caixa_segredo") or "").strip()
    if caixa_seg:
        gravar_config(con, WA.CHAVE_CAIXA_SEGREDO, caixa_seg)
    gravar_config(con, WA.CHAVE_MODO_TESTE,
                  "1" if form.get("modo_teste") == "1" else "")


def assinatura_hub(app_secret: str, corpo: bytes, header: str) -> bool:
    """X-Hub-Signature-256 da Meta: sha256=<hex do HMAC do corpo cru>."""
    if not (app_secret or "").strip() or corpo is None:
        return False
    h = (header or "").strip()
    prefixo = "sha256="
    if not h.lower().startswith(prefixo):
        return False
    recebido = h.split("=", 1)[1].strip()
    esperado = hmac.new(
        app_secret.encode("utf-8"), corpo, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(esperado.lower(), recebido.lower())


def modo_teste_ligado(con: Any) -> bool:
    return ler_config(con, WA.CHAVE_MODO_TESTE) == "1"


def post_de_teste_liberado(con: Any, header_teste: str = "") -> bool:
    """POST local de desenvolvimento: header X-Wa-Test: 1 COM O MODO LIGADO.

    O MODO DE TESTE É UMA CHAVE DA CONFIGURAÇÃO, E NASCE DESLIGADO (M6 do
    LS01, lote LX11). Antes bastava não ter `app_secret` gravado — e é o de
    fábrica, porque a entrada de verdade vem pela caixa-postal: o cabeçalho
    sozinho punha conversa forjada na fila do balcão. O LS02 já o restringiu
    à própria máquina (`wa_web`); agora ele vale só com o ADMIN tendo ligado
    o modo, de propósito, na tela de configuração.

    Com app_secret gravado, so entra quem trouxer HMAC valido (reenvio da
    caixa-postal no host XMPP, ou teste que assina o corpo), ligado ou não o
    modo. O tunel no SERVIDOR do Cartorio Gestao e proibido: este endpoint
    nao deve ser publico.
    """
    if ler_config(con, WA.CHAVE_APP_SECRET) or not modo_teste_ligado(con):
        return False
    return str(header_teste or "").strip() == "1"


def post_permitido(con: Any, header_teste: str = "",
                   corpo: bytes = b"", signature_header: str = "") -> bool:
    """Este POST entra na fila?

    - Com `app_secret` gravado: exige HMAC SHA256 `X-Hub-Signature-256` valido.
    - Sem secret: so `X-Wa-Test: 1`, e so com o modo de teste LIGADO.
    - Sem secret e sem o modo: RECUSA. Nao abre o webhook para o mundo.
    Producao inbound nao chega direto neste Flask: chega na caixa-postal
    (host XMPP) e o Cartorio Gestao puxa.
    """
    secret = ler_config(con, WA.CHAVE_APP_SECRET)
    if secret:
        return assinatura_hub(secret, corpo or b"", signature_header)
    return post_de_teste_liberado(con, header_teste)


# OS TIPOS DE MENSAGEM QUE TRAZEM MIDIA (26/10/2026). O `_texto_da_mensagem`
# so lia texto, e o audio do cliente entrava como mensagem vazia — o balcao via
# uma linha em branco e ninguem sabia que havia um audio ali. Agora o tipo e o
# id da midia ficam gravados; quem baixa e transcreve e o atendente
# (`wa_atendente`), fora da transacao, se a transcricao estiver ligada.
TIPOS_COM_MIDIA = ("audio", "voice", "image", "document", "video", "sticker")


def tipo_e_midia(msg: dict) -> tuple[str, str]:
    """(tipo, id da midia) da mensagem da Meta. Texto devolve ("text", "")."""
    if not isinstance(msg, dict):
        return "text", ""
    tipo = str(msg.get("type") or "").strip().lower()
    for chave in TIPOS_COM_MIDIA:
        bloco = msg.get(chave)
        if isinstance(bloco, dict) and bloco.get("id"):
            return ("audio" if chave == "voice" else chave), str(bloco["id"])
    return (tipo or "text"), ""


def _texto_da_mensagem(msg: dict) -> str:
    if not isinstance(msg, dict):
        return ""
    for chave in TIPOS_COM_MIDIA:
        bloco = msg.get(chave)
        if isinstance(bloco, dict) and bloco.get("caption"):
            return str(bloco.get("caption") or "").strip()
    texto = msg.get("text")
    if isinstance(texto, dict):
        return str(texto.get("body") or "").strip()
    if isinstance(texto, str):
        return texto.strip()
    for k in ("body", "texto", "message"):
        if msg.get(k):
            return str(msg.get(k)).strip()
    return ""


def _mensagens_do_payload(payload: Any) -> list[tuple[dict, dict]]:
    """Aceita o envelope da Meta e um JSON curto de teste."""
    saida: list[tuple[dict, dict]] = []
    if not isinstance(payload, dict):
        return saida
    if payload.get("entry"):
        for entry in payload.get("entry") or []:
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes") or []:
                if not isinstance(change, dict):
                    continue
                value = change.get("value") or {}
                nomes = {}
                for c in value.get("contacts") or []:
                    if not isinstance(c, dict):
                        continue
                    nomes[str(c.get("wa_id") or "")] = (
                        (c.get("profile") or {}).get("name") or ""
                    )
                for m in value.get("messages") or []:
                    if isinstance(m, dict):
                        saida.append((m, nomes))
        return saida
    if payload.get("messages"):
        for m in payload.get("messages") or []:
            if isinstance(m, dict):
                saida.append((m, {}))
        return saida
    if payload.get("from") or payload.get("wa_id") or payload.get("text"):
        saida.append((payload, {}))
    return saida


def _ja_tem_meta(con: Any, meta_id: str) -> bool:
    if not meta_id:
        return False
    linha = banco(con).um(
        "SELECT id FROM wa_mensagem WHERE meta_id=%s", (meta_id,)
    )
    return bool(linha)


def _conversa_por_wa(con: Any, wa_id: str) -> dict | None:
    return banco(con).um(
        "SELECT * FROM wa_conversa WHERE wa_id=%s", (wa_id,)
    )


def aplicar_entrada(con: Any, payload_meta: Any,
                    serventia: Any = None, agora: str | None = None) -> dict:
    """Grava conversa+mensagem, classifica e rascunha. Idempotente por meta_id.

    Nao envia nada a Meta. auto_ok permanece 0.
    """
    bd = banco(con)
    quando = agora or agora_iso()
    if serventia is None:
        serventia = SERV.PADRAO
    criadas = 0
    repetidas = 0
    ids: list[int] = []
    for msg, nomes in _mensagens_do_payload(payload_meta):
        meta_id = str(msg.get("id") or msg.get("meta_id") or "").strip()
        # "Ja chegou?" e "ja tem conversa deste numero?" valem ate o INSERT.
        # O BEGIN IMMEDIATE do SQLite punha duas entradas iguais em fila;
        # sem a trava, as duas passam e a segunda bate no indice unico.
        bd.travar("wa_mensagem.meta_id")
        if meta_id and _ja_tem_meta(con, meta_id):
            repetidas += 1
            continue
        wa_id = str(msg.get("from") or msg.get("wa_id") or "").strip()
        if not wa_id:
            continue
        texto = _texto_da_mensagem(msg)
        tipo, midia_id = tipo_e_midia(msg)
        nome = str(nomes.get(wa_id) or msg.get("nome") or "").strip()
        etiqueta = classificar(texto)
        rascunho = rascunhar(texto, etiqueta, serventia, con=con)
        bruto = json.dumps(msg, ensure_ascii=False)
        existente = _conversa_por_wa(con, wa_id)
        # A RESOLVIDA QUE VOLTA (27/10/2026): nada se apaga; a tela retoma pela
        # mensagem nova, e o responsável segue a regra dos 7 dias
        # (`FILA.retomar`, a mesma do «Reativar conversa»).
        voltou = bool(existente) and existente.get("status") == WA.RESOLVIDA
        if existente:
            cid = int(existente["id"])
            # A CONVERSA RESOLVIDA QUE VOLTA, VOLTA PARA A IA (26/10/2026): a
            # passagem para pessoa vale para aquele assunto; resolvido ele, a
            # proxima pergunta comeca do atendimento de sempre. O setor fica.
            bd.escrever(
                """UPDATE wa_conversa
                      SET nome=COALESCE(NULLIF(%s, ''), nome),
                          etiqueta=%s, rascunho=%s, status=%s,
                          modo=CASE WHEN status=%s THEN NULL ELSE modo END,
                          auto_ok=0, atualizado_em=%s
                    WHERE id=%s""",
                (nome, etiqueta, rascunho, WA.ABERTA, WA.RESOLVIDA, quando,
                 cid),
            )
        else:
            cid = int(bd.escrever(
                """INSERT INTO wa_conversa
                       (wa_id, nome, etiqueta, status, rascunho,
                        auto_ok, atualizado_em)
                   VALUES (%s, %s, %s, %s, %s, 0, %s)
                   RETURNING id""",
                (wa_id, nome, etiqueta, WA.ABERTA, rascunho, quando),
            )[0]["id"])
        mid = int(bd.escrever(
            """INSERT INTO wa_mensagem
                   (conversa_id, direcao, texto, bruto_json, criado_em, meta_id,
                    tipo, midia_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (cid, DIR_IN, texto, bruto, quando, meta_id or None, tipo,
             midia_id or None),
        )[0]["id"])
        if voltou:
            FILA.retomar(con, existente, desde_id=mid, quando=quando,
                         por="mensagem do cliente",
                         motivo="o cliente escreveu de novo")
        # A PALAVRA DEFINE O SETOR (27/10/2026): na conversa sem setor, e na
        # resolvida que volta (outro atendimento). As etiquetas automaticas
        # (`wa_etiqueta`) nao nascem mais: repetiam o setor, e nenhum
        # relatorio as lia. A `etiqueta` da conversa (o assunto do rascunho)
        # continua acima, como era.
        FILA.definir_setor_pelo_assunto(con, cid, texto, quando=quando,
                                        na_retomada=voltou)
        criadas += 1
        ids.append(cid)
    return {"criadas": criadas, "repetidas": repetidas, "conversa_ids": ids}


def conversa(con: Any, conversa_id: int) -> dict | None:
    bd = banco(con)
    row = bd.um(
        "SELECT * FROM wa_conversa WHERE id=%s", (int(conversa_id),)
    )
    if not row:
        return None
    msgs = bd.ler(
        """SELECT * FROM wa_mensagem
            WHERE conversa_id=%s
            ORDER BY id ASC""",
        (int(conversa_id),),
    )
    d = dict(row)
    d["mensagens"] = [dict(m) for m in msgs]
    return d


def salvar_rascunho(con: Any, conversa_id: int, texto: str,
                    agora: str | None = None) -> None:
    quando = agora or agora_iso()
    banco(con).escrever(
        """UPDATE wa_conversa
              SET rascunho=%s, atualizado_em=%s
            WHERE id=%s""",
        (texto, quando, int(conversa_id)),
    )


def resolver(con: Any, conversa_id: int,
             agora: str | None = None) -> None:
    quando = agora or agora_iso()
    banco(con).escrever(
        """UPDATE wa_conversa
              SET status=%s, modo=NULL, passagem_motivo=NULL, atualizado_em=%s,
                  resolvida_em=%s
            WHERE id=%s""",
        (WA.RESOLVIDA, quando, quando, int(conversa_id)),
    )


def _id_da_graph(bruto: str) -> str:
    try:
        d = json.loads(bruto or "{}")
    except json.JSONDecodeError:
        return ""
    msgs = d.get("messages") or []
    if msgs and isinstance(msgs[0], dict):
        return str(msgs[0].get("id") or "").strip()
    return ""


def _mensagem_erro_graph(bruto: str, status: int) -> str:
    try:
        d = json.loads(bruto or "{}")
        err = d.get("error") or {}
        msg = err.get("message") or err.get("error_user_msg")
        if msg:
            # O CODIGO DA META VAI JUNTO (27/10/2026): e por ele que a tela
            # reconhece a recusa por janela de 24 h vencida (131047) e oferece
            # o modelo de retomar, em vez de so dizer que falhou.
            codigo = err.get("code")
            if codigo:
                return f"A Graph recusou ({status}, código {codigo}): {msg}"
            return f"A Graph recusou ({status}): {msg}"
    except json.JSONDecodeError:
        pass
    trecho = (bruto or "").strip().replace("\n", " ")[:180]
    return f"A Graph recusou ({status}). {trecho}".strip()


def _http_post_json(url: str, corpo: dict, headers: dict,
                    timeout: float = TIMEOUT_ENVIO) -> tuple[int, str]:
    """POST JSON. Isolado para o teste mockar urllib. Nao loga cabecalho."""
    data = json.dumps(corpo).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        corpo_e = e.read().decode("utf-8", errors="replace")
        return int(e.code), corpo_e
    except Exception as e:
        raise EnvioErro(
            f"Nao consegui falar com a Graph: {e}. Nada foi enviado."
        ) from e


# O ENVIO EM TRES PEDACOS (26/10/2026): montar (le o banco), postar (fala com a
# rede) e gravar (escreve). A rota e o atendente fazem os tres em ordem, com a
# rede FORA de `db.transaction()` — a regra da casa: um POST de oito segundos
# segurando a trava de escrita poria todo outro balcao no `lock_timeout`.
# O antigo `enviar_rascunho`, que fazia os tres dentro da transacao da rota,
# saiu; a listagem antiga (`listar_conversas`) tambem — quem lista e `wa_fila`.


def montar_envio(con: Any, wa_id: str, texto: str) -> dict:
    """O pedido pronto para a Graph: url, corpo e cabecalhos. So le."""
    texto = (texto or "").strip()
    if not texto:
        raise EnvioErro("Nao ha texto para enviar.")
    token = ler_config(con, WA.CHAVE_TOKEN)
    phone = ler_config(con, WA.CHAVE_PHONE)
    if not token or not phone:
        raise EnvioErro("Falta access_token ou phone_number_id na configuracao.")
    return {
        "url": f"https://graph.facebook.com/{GRAPH_VER}/{phone}/messages",
        "payload": {
            "messaging_product": "whatsapp",
            "to": str(wa_id),
            "type": "text",
            "text": {"body": texto},
        },
        "headers": {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    }


def postar_envio(pedido: dict, http_post: Callable | None = None) -> str | None:
    """FALA COM A REDE. Devolve o id que a Graph deu, ou levanta EnvioErro."""
    fn = http_post or _http_post_json
    status, bruto = fn(pedido["url"], pedido["payload"], pedido["headers"])
    if status < 200 or status >= 300:
        raise EnvioErro(_mensagem_erro_graph(bruto, status))
    return _id_da_graph(bruto) or None


def gravar_saida(con: Any, conversa_id: int, texto: str, meta_id: str | None,
                 *, autor: str = "", agora: str | None = None,
                 tipo: str = "text") -> int:
    """Grava a mensagem que saiu e poe a conversa em AGUARDANDO. ESCREVE.

    `autor` e o nome de quem apertou o botao, ou `ia` para a resposta
    automatica — e o que separa, no painel, o tempo de resposta da pessoa do
    da IA. `tipo` e `modelo` quando saiu um modelo da Meta (`wa_modelos`): a
    conversa mostra que aquilo foi o modelo, e nao texto escrito por alguem."""
    quando = agora or agora_iso()
    bd = banco(con)
    mid = int(bd.escrever(
        """INSERT INTO wa_mensagem
               (conversa_id, direcao, texto, bruto_json, criado_em, meta_id,
                tipo, autor)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (int(conversa_id), DIR_OUT, texto, None, quando, meta_id,
         (tipo or "text")[:20], (autor or "")[:80] or None),
    )[0]["id"])
    bd.escrever(
        """UPDATE wa_conversa
              SET status=%s, atualizado_em=%s
            WHERE id=%s""",
        (WA.AGUARDANDO, quando, int(conversa_id)),
    )
    return mid
