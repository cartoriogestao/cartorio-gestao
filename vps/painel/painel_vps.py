"""A PÁGINA DO PAINEL NA VPS — recebe o retrato assinado e o mostra, com login.

    «uma página mínima para a VPS, com login próprio forte — sem deploy»
                                                    — pedido de 26/10/2026

O QUE ELA É
    Um arquivo só, WSGI, que roda ATRÁS do servidor web da VPS (o mesmo do
    WhatsApp e do portal), em 127.0.0.1. Faz três coisas:

      POST <prefixo>/retrato   recebe o retrato que o servidor da casa EMPURRA;
                               confere a assinatura Ed25519, a ordem e a idade;
                               guarda só o último
      GET  <prefixo>/          o painel, depois do login
      POST <prefixo>/entrar    login: usuário + senha + código do aplicativo
                               autenticador (TOTP) — os três, sempre
      POST <prefixo>/sair

    Ela NÃO fala com o servidor da casa. Não tem como: não sabe o endereço
    dele, e ele não aceita conexão de fora. Se esta VPS for tomada, quem a
    tomou tem um retrato de contagens e uma chave PÚBLICA — não forja retrato,
    não alcança o banco.

O LOGIN, E POR QUE ELE É ASSIM
    * A senha guarda-se em scrypt (n=2^15), e o usuário que não existe gasta o
      mesmo scrypt: o tempo não diz quem é cadastrado.
    * O segundo fator é obrigatório. Senha forte vazada por outro caminho não
      basta sozinha.
    * Cinco erros em quinze minutos põem o usuário E o endereço em espera de
      quinze minutos — nem a senha certa entra enquanto isso.
    * A sessão é um número aleatório de 256 bits num cookie HttpOnly, Secure,
      SameSite=Strict; no disco fica só o sha256 dele. Cai com 30 minutos
      parada e com 12 horas de vida, o que vier primeiro.
    * O formulário leva um token contra CSRF, e toda resposta leva os
      cabeçalhos que o navegador obedece (CSP sem script, sem moldura).

O QUE SE FAZ NA VPS (ninguém fez ainda — não houve deploy)
    1. Copiar esta pasta para fora da raiz pública do site, num usuário próprio.
    2. `pip install cryptography` (é a única dependência fora da biblioteca
       padrão do Python).
    3. Escolher a pasta de dados, fora da raiz pública:
           export PAINEL_VPS_DADOS=/caminho/para/dados_do_painel
    4. Colar a chave pública que a tela /painel/retrato do sistema mostra:
           python painel_vps.py chave-publica <a chave em base64>
    5. Criar quem pode entrar (pede a senha duas vezes, sem eco, e mostra o
       endereço otpauth:// para o aplicativo autenticador):
           python painel_vps.py criar-usuario <nome>
    6. Rodar atrás do servidor web, só em 127.0.0.1 (o próprio arquivo serve
       para teste com `python painel_vps.py servir --porta 8790`; em produção,
       mod_wsgi ou gunicorn apontando para `painel_vps:application`), com
       HTTPS no servidor web. Atrás de proxy, PAINEL_VPS_CONFIA_PROXY=1 faz a
       espera do login contar pelo X-Forwarded-For.
    7. Na tela /painel/retrato do sistema, gravar o endereço
       https://<a vps>/<prefixo>/retrato e enviar um retrato de teste.
"""
from __future__ import annotations

import base64
import contextlib
import getpass
import hashlib
import hmac
import html
import json
import os
import secrets
import struct
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable

FORMATO_DO_ENVELOPE = "cg-painel-retrato-1"
TETO_DO_CORPO = 64 * 1024
IDADE_MAXIMA_S = 15 * 60          # retrato com mais de 15 min não entra
ADIANTADO_MAXIMO_S = 5 * 60       # relógio da casa até 5 min à frente
SESSAO_PARADA_S = 30 * 60
SESSAO_VIDA_S = 12 * 3600
ERROS_ATE_ESPERAR = 5
JANELA_DOS_ERROS_S = 15 * 60
ESPERA_S = 15 * 60
SENHA_MINIMA = 14
COOKIE_SESSAO = "painel_sessao"
COOKIE_CSRF = "painel_csrf"
PERIODOS = (("dia", "Hoje"), ("semana", "Semana"), ("mes", "Mês"))
ATRIBUICOES = ("RI", "RCPN", "Notas", "Protesto", "RTD/PJ", "Outras")


# ================================================================ o disco


def pasta_de_dados() -> Path:
    p = Path(os.environ.get("PAINEL_VPS_DADOS") or (Path(__file__).resolve().parent / "dados"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def prefixo() -> str:
    return "/" + (os.environ.get("PAINEL_VPS_PREFIXO") or "painel").strip("/")


@contextlib.contextmanager
def trava(nome: str = "painel"):
    """Uma escrita por vez nos arquivos de estado (vários processos WSGI)."""
    caminho = pasta_de_dados() / f".{nome}.trava"
    with open(caminho, "a+b") as f:
        try:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX)
        except ImportError:                       # Windows, só nos testes
            pass
        yield


def ler_json(nome: str, padrao: Any) -> Any:
    try:
        return json.loads((pasta_de_dados() / nome).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def gravar_json(nome: str, dados: Any) -> None:
    alvo = pasta_de_dados() / nome
    provisorio = alvo.with_suffix(alvo.suffix + ".tmp")
    provisorio.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(provisorio, 0o600)
    except OSError:
        pass
    os.replace(provisorio, alvo)


def configuracao() -> dict:
    return ler_json("config.json", {})


# ================================================================ a senha


def hash_da_senha(senha: str, sal: bytes | None = None) -> str:
    sal = sal or secrets.token_bytes(16)
    feito = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=2 ** 15, r=8, p=1,
                           dklen=32, maxmem=64 * 1024 * 1024)
    return "scrypt$32768$8$1$" + base64.b64encode(sal).decode() + "$" + base64.b64encode(feito).decode()


_HASH_FALSO = "scrypt$32768$8$1$" + base64.b64encode(b"\0" * 16).decode() + "$" + base64.b64encode(b"\0" * 32).decode()


def senha_confere(senha: str, guardado: str | None) -> bool:
    """Gasta o mesmo scrypt para quem não existe."""
    alvo = guardado or _HASH_FALSO
    try:
        _, n, r, p, sal, esperado = alvo.split("$")
        feito = hashlib.scrypt(senha.encode("utf-8"), salt=base64.b64decode(sal),
                               n=int(n), r=int(r), p=int(p), dklen=32,
                               maxmem=64 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(feito, base64.b64decode(esperado)) and guardado is not None


# ================================================================ o TOTP (RFC 6238)


def totp(segredo_b32: str, passo: int) -> str:
    chave = base64.b32decode(segredo_b32.upper() + "=" * (-len(segredo_b32) % 8))
    mac = hmac.new(chave, struct.pack(">Q", passo), hashlib.sha1).digest()
    i = mac[-1] & 0x0F
    numero = (struct.unpack(">I", mac[i:i + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{numero:06d}"


def codigo_confere(usuario: str, segredo_b32: str | None, codigo: str,
                   agora: float | None = None) -> bool:
    """Aceita o passo atual e o vizinho de cada lado; o mesmo código não
    vale duas vezes (o passo usado fica guardado)."""
    if not segredo_b32 or not codigo or not codigo.isdigit() or len(codigo) != 6:
        return False
    agora = time.time() if agora is None else agora
    passo_agora = int(agora // 30)
    usados = ler_json("totp.json", {})
    ultimo = int(usados.get(usuario, -1))
    for passo in (passo_agora - 1, passo_agora, passo_agora + 1):
        if passo > ultimo and hmac.compare_digest(totp(segredo_b32, passo), codigo):
            usados[usuario] = passo
            gravar_json("totp.json", usados)
            return True
    return False


# ================================================================ a espera do login


def _chaves_da_espera(usuario: str, ip: str) -> list[str]:
    return ["u:" + hashlib.sha256(usuario.lower().encode()).hexdigest()[:24],
            "ip:" + ip]


def em_espera(usuario: str, ip: str, agora: float) -> bool:
    erros = ler_json("tentativas.json", {})
    for chave in _chaves_da_espera(usuario, ip):
        recentes = [t for t in erros.get(chave, []) if agora - t < JANELA_DOS_ERROS_S + ESPERA_S]
        janela = [t for t in recentes if agora - t < JANELA_DOS_ERROS_S]
        if len(janela) >= ERROS_ATE_ESPERAR or (
                len(recentes) >= ERROS_ATE_ESPERAR and agora - max(recentes) < ESPERA_S):
            return True
    return False


def anotar_erro(usuario: str, ip: str, agora: float) -> None:
    erros = ler_json("tentativas.json", {})
    for chave in _chaves_da_espera(usuario, ip):
        lista = [t for t in erros.get(chave, []) if agora - t < JANELA_DOS_ERROS_S + ESPERA_S]
        erros[chave] = (lista + [agora])[-20:]
    gravar_json("tentativas.json", erros)


def zerar_erros(usuario: str, ip: str) -> None:
    erros = ler_json("tentativas.json", {})
    for chave in _chaves_da_espera(usuario, ip):
        erros.pop(chave, None)
    gravar_json("tentativas.json", erros)


# ================================================================ a sessão


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def abrir_sessao(usuario: str, agora: float) -> str:
    token = secrets.token_urlsafe(32)
    sessoes = {k: v for k, v in ler_json("sessoes.json", {}).items()
               if agora - v["inicio"] < SESSAO_VIDA_S}
    sessoes[_h(token)] = {"usuario": usuario, "inicio": agora, "ultimo": agora}
    gravar_json("sessoes.json", sessoes)
    return token


def sessao_valida(token: str | None, agora: float) -> str | None:
    if not token:
        return None
    sessoes = ler_json("sessoes.json", {})
    s = sessoes.get(_h(token))
    if not s:
        return None
    if agora - s["inicio"] > SESSAO_VIDA_S or agora - s["ultimo"] > SESSAO_PARADA_S:
        sessoes.pop(_h(token), None)
        gravar_json("sessoes.json", sessoes)
        return None
    if s["usuario"] not in (configuracao().get("usuarios") or {}):
        return None
    s["ultimo"] = agora
    gravar_json("sessoes.json", sessoes)
    return s["usuario"]


def fechar_sessao(token: str | None) -> None:
    if token:
        sessoes = ler_json("sessoes.json", {})
        sessoes.pop(_h(token), None)
        gravar_json("sessoes.json", sessoes)


# ================================================================ o retrato


class Recusa(Exception):
    def __init__(self, status: str, motivo: str):
        super().__init__(motivo)
        self.status = status
        self.motivo = motivo


def receber_retrato(corpo: bytes, agora: float | None = None) -> dict:
    """Confere e guarda. Levanta `Recusa` com o status HTTP do porquê."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519
    agora = time.time() if agora is None else agora
    if len(corpo) > TETO_DO_CORPO:
        raise Recusa("413 Payload Too Large", "retrato grande demais")
    publica = configuracao().get("chave_publica")
    if not publica:
        raise Recusa("503 Service Unavailable", "a VPS ainda não tem a chave pública")
    try:
        env = json.loads(corpo.decode("ascii"))
        texto = env["retrato"]
        assinatura = base64.b64decode(env["assinatura"], validate=True)
        if env.get("formato") != FORMATO_DO_ENVELOPE or not isinstance(texto, str):
            raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        raise Recusa("400 Bad Request", "envelope fora do formato") from None
    try:
        ed25519.Ed25519PublicKey.from_public_bytes(base64.b64decode(publica)).verify(
            assinatura, texto.encode("ascii"))
    except (InvalidSignature, ValueError, UnicodeEncodeError):
        raise Recusa("403 Forbidden", "assinatura não confere") from None
    retrato = json.loads(texto)
    selo = retrato.get("selo") or {}
    seq, emitido = int(selo.get("seq") or 0), int(selo.get("emitido_utc") or 0)
    if emitido < agora - IDADE_MAXIMA_S or emitido > agora + ADIANTADO_MAXIMO_S:
        raise Recusa("409 Conflict", "retrato fora da janela de tempo")
    with trava("retrato"):
        estado = ler_json("estado.json", {})
        if seq <= int(estado.get("ultimo_seq") or 0):
            raise Recusa("409 Conflict", "retrato repetido ou mais velho que o último")
        estado["ultimo_seq"] = seq
        gravar_json("retrato.json", retrato)
        gravar_json("estado.json", estado)
    return retrato


# ================================================================ a página


_CSS = """:root{--f:#f4f5f7;--c:#fff;--t:#1d2330;--a:#5d6677;--l:#e2e5ea;--d:#1f5fa8;--r:#a3261f}
@media (prefers-color-scheme:dark){:root{--f:#14171c;--c:#1e232b;--t:#e8ebf0;--a:#9aa3b2;--l:#2e3440;--d:#7fb0ef;--r:#f08a83}}
*{box-sizing:border-box}body{margin:0;background:var(--f);color:var(--t);font:16px/1.4 system-ui,sans-serif}
main{max-width:560px;margin:0 auto;padding:14px 16px 24px}h1{font-size:1.15rem;margin:0}
.q{color:var(--a);font-size:.85rem;margin:2px 0 10px}nav{display:flex;gap:6px;margin:0 0 12px}
nav a{flex:1;text-align:center;padding:10px 0;border-radius:10px;background:var(--c);border:1px solid var(--l);color:var(--t);text-decoration:none;font-weight:600}
nav a.at{background:var(--d);border-color:var(--d);color:#fff}
section{background:var(--c);border:1px solid var(--l);border-radius:12px;padding:12px 14px;margin:0 0 12px}
h2{font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;color:var(--a);margin:0 0 8px}
.g{font-size:1.8rem;font-weight:700}dl{display:grid;grid-template-columns:1fr auto;gap:6px 12px;margin:6px 0 0}
dt{color:var(--a)}dd{margin:0;text-align:right;font-weight:600}.r{color:var(--r)}
label{display:block;margin:0 0 10px}input{width:100%;font:inherit;padding:10px;border:1px solid var(--l);border-radius:8px;background:var(--c);color:var(--t)}
button{font:inherit;padding:10px 16px;border:0;border-radius:8px;background:var(--d);color:#fff}
.s{background:none;color:var(--d);padding:6px 0;text-decoration:underline}"""


def _e(v: Any) -> str:
    return html.escape("—" if v is None else str(v))


def _reais(centavos: Any) -> str:
    if centavos is None:
        return "—"
    v = int(centavos) / 100
    return "R$ " + f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _pagina(titulo: str, corpo: str) -> bytes:
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex"><title>{_e(titulo)}</title>'
            f"<style>{_CSS}</style></head><body><main>{corpo}</main></body></html>").encode("utf-8")


def pagina_de_login(csrf: str, recado: str = "") -> bytes:
    aviso = f'<section><p class="r">{_e(recado)}</p></section>' if recado else ""
    return _pagina("Painel — entrar", (
        f"<h1>Painel da casa</h1><p class='q'>Números agregados. Entre com usuário, senha e o código do aplicativo autenticador.</p>{aviso}"
        f"<section><form method='post' action='{prefixo()}/entrar'>"
        f"<input type='hidden' name='csrf' value='{_e(csrf)}'>"
        "<label>Usuário<input name='usuario' autocomplete='username' required></label>"
        "<label>Senha<input name='senha' type='password' autocomplete='current-password' required></label>"
        "<label>Código de 6 dígitos<input name='codigo' inputmode='numeric' autocomplete='one-time-code' pattern='[0-9]{6}' required></label>"
        "<button type='submit'>Entrar</button></form></section>"))


def pagina_do_painel(retrato: dict | None, periodo: str, csrf: str, agora: float) -> bytes:
    sair = (f"<form method='post' action='{prefixo()}/sair'><input type='hidden' name='csrf' value='{_e(csrf)}'>"
            "<button class='s' type='submit'>Sair</button></form>")
    if not retrato:
        return _pagina("Painel", "<h1>Painel da casa</h1><section><p>Ainda não chegou nenhum retrato do servidor.</p></section>" + sair)
    p = (retrato.get("periodos") or {}).get(periodo) or {}
    ag = retrato.get("agora") or {}
    emitido = int((retrato.get("selo") or {}).get("emitido_utc") or 0)
    velho = agora - emitido > 2 * IDADE_MAXIMA_S
    g = str(retrato.get("gerado_em") or "")
    partes = [f"<h1>Painel da casa</h1><p class='q'>Retrato de {_e(g[8:10])}/{_e(g[5:7])} às {_e(g[11:16])}"
              + (" — <span class='r'>o servidor não manda retrato novo há mais de meia hora</span>" if velho else "") + "</p>"]
    partes.append("<nav>" + "".join(
        f"<a class='{'at' if q == periodo else ''}' href='{prefixo()}/?p={q}'>{r}</a>" for q, r in PERIODOS) + "</nav>")
    if retrato.get("nao_mediu"):
        partes.append(f"<section><p class='r'>Não deu para medir: {_e(', '.join(retrato['nao_mediu']))}.</p></section>")
    partes.append(f"<section><h2>Receita do caixa</h2><div class='g'>{_e(_reais(p.get('receita_centavos')))}</div>"
                  f"<p class='q'>{_e(p.get('lancamentos'))} recebimentos · {_e(p.get('gratuidades'))} gratuidades</p></section>")
    atos = p.get("atos_por_atribuicao") or {}
    linhas = "".join(f"<dt>{_e(a)}</dt><dd>{_e(atos.get(a))}</dd>" for a in ATRIBUICOES if a in atos)
    partes.append(f"<section><h2>Atos praticados (selos usados)</h2><div class='g'>{_e(p.get('selos_usados'))}</div>"
                  f"<dl>{linhas}<dt>Selos cancelados</dt><dd>{_e(p.get('selos_cancelados'))}</dd></dl></section>")
    espera = p.get("espera_media_min")
    partes.append("<section><h2>Balcão</h2><dl>"
                  f"<dt>Protocolos abertos</dt><dd>{_e(p.get('protocolos_abertos'))}</dd>"
                  f"<dt>Senhas emitidas</dt><dd>{_e(p.get('senhas'))}</dd>"
                  f"<dt>Espera média</dt><dd>{_e(None if espera is None else f'{espera} min')}</dd></dl></section>")

    def bloco(titulo: str, dados: dict | None, campos: list[tuple[str, str]]) -> str:
        if not dados:
            return f"<section><h2>{_e(titulo)}</h2><p class='q'>—</p></section>"
        return (f"<section><h2>{_e(titulo)}</h2><dl>"
                + "".join(f"<dt>{_e(r)}</dt><dd>{_e(dados.get(c))}</dd>" for c, r in campos)
                + "</dl></section>")

    partes.append(bloco("Agora — atendimento", ag.get("atendimento"),
                        [("aguardando", "Esperando"), ("em_atendimento", "Em atendimento"),
                         ("finalizados", "Atendidos hoje")]))
    partes.append(bloco("Agora — protocolos", ag.get("protocolos"),
                        [("em_andamento", "Em andamento"), ("atrasados", "Atrasados"),
                         ("sem_item", "Sem item (a encerrar)")]))
    partes.append(bloco("Agora — prenotações", ag.get("prenotacoes"),
                        [("abertas", "Abertas"), ("vencidas", "Vencidas"),
                         ("a_vencer", "Vencendo"), ("prazo_suspenso", "Prazo suspenso")]))
    partes.append(bloco("Agora — tarefas", ag.get("tarefas"),
                        [("atrasadas", "Atrasadas"), ("vencendo", "Vencendo"), ("abertas", "Abertas"),
                         ("aguardando_terceiro", "Aguardando terceiro"),
                         ("expedientes_ativos", "Expedientes ativos")]))
    partes.append(bloco("Alertas da casa", ag.get("alertas"),
                        [("achados_abertos", "Achados abertos do gestor"),
                         ("gestor_ultima_rodada", "Última rodada do gestor"),
                         ("disputas_de_escrita", "Disputas de escrita")]))
    partes.append(sair)
    return _pagina("Painel", "".join(partes))


# ================================================================ o WSGI


_CABECALHOS = [
    ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; "
                                "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Cache-Control", "no-store"),
    ("Strict-Transport-Security", "max-age=31536000"),
]


def _cookies(environ) -> dict[str, str]:
    saida = {}
    for pedaco in (environ.get("HTTP_COOKIE") or "").split(";"):
        if "=" in pedaco:
            k, v = pedaco.strip().split("=", 1)
            saida[k] = v
    return saida


def _cookie(nome: str, valor: str, apagar: bool = False) -> tuple[str, str]:
    extra = "; Max-Age=0" if apagar else ""
    return ("Set-Cookie", f"{nome}={valor}; Path={prefixo()}; HttpOnly; Secure; SameSite=Strict{extra}")


def _ip(environ) -> str:
    if os.environ.get("PAINEL_VPS_CONFIA_PROXY") == "1" and environ.get("HTTP_X_FORWARDED_FOR"):
        return environ["HTTP_X_FORWARDED_FOR"].split(",")[0].strip()
    return environ.get("REMOTE_ADDR") or "?"


def _corpo(environ, teto: int) -> bytes:
    try:
        tamanho = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        tamanho = 0
    if tamanho > teto:
        raise Recusa("413 Payload Too Large", "corpo grande demais")
    return environ["wsgi.input"].read(tamanho) if tamanho else b""


def application(environ, start_response: Callable):
    agora = time.time()
    metodo = environ.get("REQUEST_METHOD", "GET")
    caminho = environ.get("PATH_INFO") or "/"
    base = prefixo()
    cookies = _cookies(environ)

    def responder(status: str, corpo: bytes, extra: list | None = None,
                  tipo: str = "text/html; charset=utf-8"):
        start_response(status, [("Content-Type", tipo), *_CABECALHOS, *(extra or [])])
        return [corpo]

    try:
        if caminho == base + "/retrato" and metodo == "POST":
            receber_retrato(_corpo(environ, TETO_DO_CORPO), agora)
            return responder("204 No Content", b"", tipo="text/plain")

        csrf = cookies.get(COOKIE_CSRF) or ""
        novo_csrf = []
        if not csrf:
            csrf = secrets.token_urlsafe(24)
            novo_csrf = [_cookie(COOKIE_CSRF, csrf)]

        if metodo == "POST" and caminho in (base + "/entrar", base + "/sair"):
            form = urllib.parse.parse_qs(_corpo(environ, 8 * 1024).decode("utf-8", "replace"))
            enviado = (form.get("csrf") or [""])[0]
            if not cookies.get(COOKIE_CSRF) or not hmac.compare_digest(enviado, cookies[COOKIE_CSRF]):
                return responder("400 Bad Request", _pagina("Painel", "<p>Formulário vencido. Volte e tente de novo.</p>"))
            if caminho == base + "/sair":
                fechar_sessao(cookies.get(COOKIE_SESSAO))
                return responder("303 See Other", b"", [("Location", base + "/"),
                                                         _cookie(COOKIE_SESSAO, "", apagar=True)])
            usuario = (form.get("usuario") or [""])[0].strip()[:64]
            senha = (form.get("senha") or [""])[0]
            codigo = (form.get("codigo") or [""])[0].strip()
            ip = _ip(environ)
            with trava("login"):
                if em_espera(usuario, ip, agora):
                    return responder("429 Too Many Requests", pagina_de_login(
                        csrf, "Muitas tentativas erradas. Espere quinze minutos."))
                cadastro = (configuracao().get("usuarios") or {}).get(usuario) or {}
                ok_senha = senha_confere(senha, cadastro.get("senha"))
                ok = ok_senha and codigo_confere(usuario, cadastro.get("totp"), codigo, agora)
                if not ok:
                    anotar_erro(usuario, ip, agora)
                    return responder("401 Unauthorized", pagina_de_login(
                        csrf, "Usuário, senha ou código não conferem."))
                zerar_erros(usuario, ip)
                token = abrir_sessao(usuario, agora)
            return responder("303 See Other", b"", [("Location", base + "/"),
                                                     _cookie(COOKIE_SESSAO, token)])

        if metodo == "GET" and caminho in (base, base + "/"):
            with trava("login"):
                quem = sessao_valida(cookies.get(COOKIE_SESSAO), agora)
            if not quem:
                return responder("200 OK", pagina_de_login(csrf), novo_csrf)
            periodo = urllib.parse.parse_qs(environ.get("QUERY_STRING") or "").get("p", ["dia"])[0]
            periodo = periodo if periodo in dict(PERIODOS) else "dia"
            return responder("200 OK", pagina_do_painel(ler_json("retrato.json", None),
                                                        periodo, csrf, agora), novo_csrf)
        return responder("404 Not Found", _pagina("Painel", "<p>Não encontrado.</p>"))
    except Recusa as r:
        return responder(r.status, r.motivo.encode("utf-8"), tipo="text/plain; charset=utf-8")


# ================================================================ a linha de comando


def _criar_usuario(nome: str) -> int:
    senha = getpass.getpass("Senha (14 caracteres ou mais): ")
    if len(senha) < SENHA_MINIMA:
        print(f"A senha precisa ter {SENHA_MINIMA} caracteres ou mais.")
        return 1
    if senha != getpass.getpass("Repita a senha: "):
        print("As duas não conferem.")
        return 1
    segredo = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    with trava("login"):
        conf = configuracao()
        conf.setdefault("usuarios", {})[nome] = {"senha": hash_da_senha(senha), "totp": segredo}
        gravar_json("config.json", conf)
    rotulo = urllib.parse.quote(f"Painel:{nome}")
    print("Cadastre no aplicativo autenticador (ou digite o segredo à mão):")
    print(f"  otpauth://totp/{rotulo}?secret={segredo}&issuer=Painel&digits=6&period=30")
    print("Guarde este segredo só no aplicativo: ele não aparece de novo.")
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="A página do painel na VPS.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("criar-usuario").add_argument("nome")
    sub.add_parser("remover-usuario").add_argument("nome")
    sub.add_parser("chave-publica").add_argument("chave")
    s = sub.add_parser("servir")
    s.add_argument("--porta", type=int, default=8790)
    a = ap.parse_args(argv)
    if a.cmd == "criar-usuario":
        return _criar_usuario(a.nome)
    if a.cmd == "remover-usuario":
        with trava("login"):
            conf = configuracao()
            (conf.get("usuarios") or {}).pop(a.nome, None)
            gravar_json("config.json", conf)
        return 0
    if a.cmd == "chave-publica":
        if len(base64.b64decode(a.chave)) != 32:
            print("A chave pública Ed25519 tem 32 bytes em base64.")
            return 1
        with trava("login"):
            conf = configuracao()
            conf["chave_publica"] = a.chave.strip()
            gravar_json("config.json", conf)
        print("Chave guardada. Impressão:", hashlib.sha256(base64.b64decode(a.chave)).hexdigest()[:16])
        return 0
    from wsgiref.simple_server import make_server
    print(f"Servindo em http://127.0.0.1:{a.porta}{prefixo()}/ (só para teste; em produção, atrás do servidor web com HTTPS)")
    make_server("127.0.0.1", a.porta, application).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
