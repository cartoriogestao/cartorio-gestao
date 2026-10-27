"""O RETRATO DO PAINEL QUE SAI DA CASA — assinado, datado, e EMPURRADO (26/10/2026).

    «acesso de fora: NÃO exponha o servidor» — pedido de 26/10/2026

O DESENHO, E POR QUE É ESTE
    O servidor fica na rede local, e continua assim: nada aqui abre porta, nada
    aqui instala túnel. Quem quer ver os números de fora vê uma CÓPIA deles,
    que o servidor EMPURRA para a VPS por uma conexão de SAÍDA — o mesmo
    sentido da caixa-postal do WhatsApp (`wa_puxar`), só que ao contrário: lá
    o servidor puxa o que chegou; aqui ele leva o que mediu.

    Na VPS mora a página mínima (`vps/painel/painel_vps.py`), com login
    próprio. Se a VPS cair, ou for tomada, o que se perde é um retrato de
    contagens — nunca o banco, nunca o balcão.

O QUE VAI, E O QUE A FUNÇÃO RECUSA MANDAR
    Vai o dicionário de `painel_numeros.montar` — contagens, somas, datas e
    rótulos fixos. `conferir_que_e_so_agregado` anda por ele inteiro antes de
    assinar: todo texto que não for data nem um rótulo conhecido derruba o
    envio. A guarda é sobre a FORMA, e não sobre a origem: no dia em que
    alguém acrescentar um campo com nome de cliente ao painel, o retrato para
    de sair, em vez de levar o nome para a internet.

A ASSINATURA, E POR QUE Ed25519 E NÃO UM SEGREDO DIVIDIDO
    Com HMAC a VPS precisaria do mesmo segredo que assina — e quem tomasse a
    VPS forjaria retrato «do cartório». Com Ed25519 a VPS guarda só a chave
    PÚBLICA. A privada mora no cofre da pasta de dados (`painel.cred`), fora do
    banco e fora do repositório, como as outras credenciais da casa. É o mesmo
    algoritmo que já assina as atualizações (`assinatura_da_atualizacao`).

    O retrato leva um número que só cresce (`seq`) e a hora UTC em que saiu:
    a VPS recusa o que é mais velho que o último aceito e o que passou de
    quinze minutos. Um retrato copiado no caminho não volta a valer depois.

O QUE NÃO ESTÁ AQUI, DE PROPÓSITO
    Quem chama `empurrar` de tempos em tempos. A rota do titular manda um agora,
    e `tools/painel_empurrar.py` é o que o Agendador do Windows chamaria — mas
    agendar é decisão do oficial, e nada aqui agenda.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import cofre_cred as COFRE
import painel_numeros as PN

FORMATO_DO_ENVELOPE = "cg-painel-retrato-1"

# Configuração que NÃO é segredo — mora em `settings`, como a `caixa_url`.
CHAVE_URL = "painel_vps_url"
CHAVE_LIGADO = "painel_vps_ligado"
CHAVE_ULTIMO_ENVIO = "painel_vps_ultimo_envio"
# QUEM É O TITULAR DO PAINEL — o id de UM usuário ADMIN. Decisão do oficial
# em 26/10/2026, «apenas eu»: o painel e o retrato são só do oficial titular.
# Não é papel que se distribui: é UM nome, guardado aqui.
CHAVE_TITULAR = "painel_titular_id"

# No cofre (`painel.cred`): a chave privada, em base64 dos 32 bytes crus.
SEGREDO_DA_CHAVE = "chave_privada_ed25519"

TIMEOUT_EMPURRAR = 8
#: Teto do corpo — o retrato tem poucos KB; a VPS recusa acima disto.
TETO_DO_RETRATO = 64 * 1024


class RetratoError(ValueError):
    """Regra do retrato, com a frase pronta para a tela."""


# ------------------------------------------------------------- o titular
#
# «APENAS EU» — o oficial, 26/10/2026. O painel do celular, o retrato que
# sai para a VPS e a tela que os configura são de UMA pessoa: o oficial
# titular. Nem outro ADMIN, nem o gerente, nem o auditor. O sistema guarda o
# id dele em `settings` (`CHAVE_TITULAR`) e confere, a cada pedido, que ele
# continua ATIVO, ADMIN e pessoa (robô nunca é titular).
#
# QUEM ESCOLHE: enquanto não há titular válido, qualquer ADMIN o escolhe na
# tela /painel/retrato (o primeiro uso). Depois disso, SÓ O PRÓPRIO TITULAR
# passa o painel a outro ADMIN — sem essa trava, «só ele» valeria até o
# primeiro outro ADMIN abrir a tela e se escolher. Se o titular for
# desativado ou deixar de ser ADMIN, a escolha volta a qualquer ADMIN: a
# casa não fica sem saída por um cadastro desligado.


def _usuario_valido_para_titular(usuario) -> bool:
    if not usuario:
        return False
    try:
        robo = int(usuario["eh_robo"] or 0) == 1
    except (KeyError, IndexError, TypeError, ValueError):
        robo = False
    return (bool(usuario["active"]) and str(usuario["role"] or "").upper() == "ADMIN"
            and not robo)


def titular(db) -> dict | None:
    """O titular do painel, se o gravado ainda é ADMIN ativo e pessoa. Só lê."""
    bruto = str(db.get_setting(CHAVE_TITULAR, "") or "").strip()
    if not bruto.isdigit():
        return None
    usuario = db.get_user(int(bruto))
    return usuario if _usuario_valido_para_titular(usuario) else None


def e_o_titular(db, usuario) -> bool:
    """Este usuário é o titular do painel? Só lê."""
    dono = titular(db)
    return bool(dono and usuario and int(dono["id"]) == int(usuario["id"])
                and _usuario_valido_para_titular(usuario))


def definir_titular(db, *, novo_id: int, quem) -> dict:
    """Grava QUEM é o titular do painel. ESCREVE em `settings`.

    `quem` é o usuário logado que escolhe. Recusa (com a frase para a tela):
    quem escolhe não é ADMIN ativo; o escolhido não é ADMIN ativo e pessoa;
    e, havendo titular válido, quem escolhe não é ele. Quem audita é a rota.
    """
    if not _usuario_valido_para_titular(quem):
        raise RetratoError("Só um ADMIN ativo escolhe o titular do painel.")
    atual = titular(db)
    if atual is not None and int(atual["id"]) != int(quem["id"]):
        raise RetratoError(
            f"O painel é de {atual['full_name']}, o titular. Só ele passa o "
            "painel a outro ADMIN.")
    novo = db.get_user(int(novo_id))
    if not _usuario_valido_para_titular(novo):
        raise RetratoError(
            "O titular do painel tem de ser um usuário ADMIN ativo, e pessoa "
            "(conta de robô não).")
    db.set_settings({CHAVE_TITULAR: str(int(novo["id"]))})
    return novo


def candidatos_a_titular(db) -> list[dict]:
    """Os ADMIN ativos e pessoas — os únicos que a tela oferece. Só lê."""
    return [u for u in db.list_users(active_only=True)
            if _usuario_valido_para_titular(u)]


# ------------------------------------------------------------- a chave


def _privada(pasta: Any):
    from cryptography.hazmat.primitives.asymmetric import ed25519
    bruto = COFRE.ler(Path(pasta), COFRE.PAINEL).get(SEGREDO_DA_CHAVE, "")
    if not bruto:
        return None
    try:
        return ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(bruto))
    except (ValueError, TypeError):
        return None


def chave_publica(pasta: Any) -> str | None:
    """A pública, em base64 dos 32 bytes — é ela que se cola na VPS."""
    from cryptography.hazmat.primitives import serialization
    privada = _privada(pasta)
    if privada is None:
        return None
    crus = privada.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(crus).decode("ascii")


def impressao(publica_b64: str | None) -> str:
    """Dezesseis letras do sha256 da pública — para conferir de olho que a
    chave colada na VPS é a desta casa. Só calcula."""
    if not publica_b64:
        return ""
    return hashlib.sha256(base64.b64decode(publica_b64)).hexdigest()[:16]


def gerar_chave(pasta: Any, *, trocar: bool = False) -> str:
    """Cria o par e guarda a privada no cofre. ESCREVE EM DISCO.

    Trocar é escolha deliberada: a VPS passa a recusar tudo até receber a
    pública nova, e por isso a função não troca sem que se peça.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    if _privada(pasta) is not None and not trocar:
        raise RetratoError(
            "Já existe uma chave do painel. Trocá-la faz a VPS recusar os "
            "retratos até você colar lá a chave pública nova — marque «trocar» "
            "se é isso que você quer.")
    privada = ed25519.Ed25519PrivateKey.generate()
    crus = privada.private_bytes(serialization.Encoding.Raw,
                                 serialization.PrivateFormat.Raw,
                                 serialization.NoEncryption())
    COFRE.gravar(Path(pasta), COFRE.PAINEL,
                 {SEGREDO_DA_CHAVE: base64.b64encode(crus).decode("ascii")})
    return chave_publica(pasta) or ""


# ------------------------------------------------------------- a guarda


_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?$")


def _rotulos_permitidos() -> frozenset[str]:
    return frozenset({PN.FORMATO, *PN.ROTULO_DO_PERIODO.values(),
                      "selos", "receita", "atendimento", "protocolos",
                      "prenotacoes", "tarefas", "atendimento_agora", "alertas"})


def conferir_que_e_so_agregado(retrato: Any, onde: str = "retrato") -> None:
    """Recusa o retrato que leve texto que não seja data nem rótulo fixo.

    Número, booleano e vazio passam; texto só passa se for data ISO ou um
    dos rótulos que o próprio painel escreve. As CHAVES dos dicionários são
    escritas pelo código — e mesmo assim são conferidas pela forma: palavra
    curta, sem dígito de documento.
    """
    permitidos = _rotulos_permitidos()
    if isinstance(retrato, dict):
        for k, v in retrato.items():
            if not isinstance(k, str) or not re.fullmatch(r"[A-Za-z_/]{1,40}", k):
                raise RetratoError(f"O retrato tem uma chave fora da forma em {onde}.")
            conferir_que_e_so_agregado(v, f"{onde}.{k}")
        return
    if isinstance(retrato, list):
        for i, v in enumerate(retrato):
            conferir_que_e_so_agregado(v, f"{onde}[{i}]")
        return
    if retrato is None or isinstance(retrato, (bool, int, float)):
        return
    if isinstance(retrato, str) and (_DATA.match(retrato) or retrato in permitidos):
        return
    raise RetratoError(
        f"O retrato não saiu: em {onde} há um texto que não é número, data nem "
        "rótulo do painel. O painel que sai da casa leva só agregados — "
        "confira o que foi acrescentado a `painel_numeros`.")


# ------------------------------------------------------------- o envelope


def canonico(retrato: dict) -> str:
    """O texto exato que se assina: chaves em ordem, sem espaço, ASCII."""
    return json.dumps(retrato, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def envelope(retrato: dict, pasta: Any, *, agora_utc: datetime | None = None) -> dict:
    """Carimba, confere e assina. Não manda nada."""
    privada = _privada(pasta)
    if privada is None:
        raise RetratoError(
            "Ainda não há chave do painel. Gere a chave na tela do retrato e "
            "cole a chave pública na VPS antes de enviar.")
    conferir_que_e_so_agregado(retrato)
    agora_utc = agora_utc or datetime.now(timezone.utc)
    carimbado = dict(retrato)
    carimbado["selo"] = {
        # Só cresce: milissegundos desde 1970. A VPS recusa o que não for
        # maior que o último aceito.
        "seq": int(agora_utc.timestamp() * 1000),
        "emitido_utc": int(agora_utc.timestamp()),
    }
    texto = canonico(carimbado)
    if len(texto.encode("ascii")) > TETO_DO_RETRATO:
        raise RetratoError("O retrato passou do teto de 64 KB — não é agregado.")
    assinatura = privada.sign(texto.encode("ascii"))
    return {
        "formato": FORMATO_DO_ENVELOPE,
        "retrato": texto,
        "assinatura": base64.b64encode(assinatura).decode("ascii"),
        "chave": impressao(chave_publica(pasta)),
    }


# ------------------------------------------------------------- o envio


def _http_post(url: str, corpo: bytes, timeout: float = TIMEOUT_EMPURRAR) -> tuple[int, str]:
    req = urllib.request.Request(url, data=corpo, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read(400).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return int(e.code), e.read(400).decode("utf-8", errors="replace")
    except Exception as e:                                 # noqa: BLE001
        return 0, type(e).__name__


def configuracao(db) -> dict:
    """O que a tela mostra: endereço, ligado, último envio. Nada de segredo."""
    try:
        ultimo = json.loads(db.get_setting(CHAVE_ULTIMO_ENVIO, "") or "{}")
    except ValueError:
        ultimo = {}
    return {"url": db.get_setting(CHAVE_URL, "") or "",
            "ligado": db.get_setting(CHAVE_LIGADO, "0") == "1",
            "ultimo": ultimo}


def salvar_configuracao(db, *, url: str, ligado: bool) -> None:
    """Grava endereço e interruptor. O endereço só é aceito em https."""
    url = (url or "").strip()
    if url and not url.lower().startswith("https://"):
        raise RetratoError(
            "O endereço da VPS precisa começar com https://: o retrato e a "
            "assinatura iriam em claro pela rede.")
    if ligado and not url:
        raise RetratoError("Para ligar o envio, informe o endereço da VPS.")
    db.set_settings({CHAVE_URL: url, CHAVE_LIGADO: "1" if ligado else "0"})


def empurrar(db, pasta: Any, *, http_post: Callable | None = None,
             agora: datetime | None = None, forcar: bool = False) -> dict:
    """Monta, assina e EMPURRA o retrato para a VPS. Uma conexão de saída.

    `forcar` é o botão «enviar agora» do ADMIN: manda mesmo com o envio
    automático desligado, mas nunca sem endereço https e nunca sem chave.
    O resultado fica em `settings` — status, hora e o tamanho, nunca o corpo.
    """
    conf = configuracao(db)
    # SEM TITULAR, NADA SAI (26/10/2026, «apenas eu»): o retrato é do
    # oficial titular, e um painel sem dono escolhido não tem para quem ir.
    if titular(db) is None:
        return {"ok": False,
                "motivo": "o painel não tem titular escolhido (tela /painel/retrato)"}
    if not conf["ligado"] and not forcar:
        return {"ok": False, "motivo": "o envio do painel está desligado"}
    url = conf["url"]
    if not url.lower().startswith("https://"):
        return {"ok": False, "motivo": "endereço da VPS vazio ou sem https"}
    try:
        env = envelope(PN.montar(db, agora=agora), pasta)
    except RetratoError as erro:
        resultado = {"ok": False, "motivo": str(erro)}
    else:
        corpo = json.dumps(env).encode("ascii")
        status, resposta = (http_post or _http_post)(url, corpo)
        resultado = {"ok": 200 <= status < 300, "status": status,
                     "bytes": len(corpo),
                     "motivo": "" if 200 <= status < 300 else
                     f"a VPS respondeu {status or 'sem conexão'}: {resposta[:120]}"}
    registro = {"em": (agora or datetime.now()).isoformat(timespec="seconds"),
                **{k: v for k, v in resultado.items() if k != "motivo"},
                "motivo": str(resultado.get("motivo") or "")[:200]}
    db.set_settings({CHAVE_ULTIMO_ENVIO: json.dumps(registro, ensure_ascii=False)})
    return resultado
