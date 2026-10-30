"""Serviço local de assinatura A3 — só 127.0.0.1 (marco A3-0/A3-1).

Sobe um HTTP mínimo em 127.0.0.1:8766 (porta aprovada pela Consultoria).
NUNCA faz bind em 0.0.0.0. NUNCA carrega PKCS#11 neste processo: delega
sempre a `a3_assinador_filho.py` (subprocess + arquivo temp).

Rotas:
  GET  /saude          → {"ok": true, "driver", "candidatos":[...], ...}
  GET  /certificados   → lista de TODOS os drivers (pode estar vazia sem token)
  POST /assinar/pdf    → JSON {pdf_b64, pin, thumbprint?} → CAdES-BES anexado
  POST /assinar/cades  → JSON {payload_utf8|payload_b64, pin, thumbprint?,
                         anexado?} → {x_signature_b64, ...}  (13/10/2026, CCN)
  POST /assinar/pdf-windows   → JSON {pdf_b64, thumbprint?} → {cms_b64, ...}
  POST /assinar/pdfs-windows  → JSON {pdfs_b64: [...], thumbprint?} →
                         {itens: [{indice, cms_b64, thumbprint}], falha}

Página da internet não fala com este serviço (ver `origem_recusada`).

PIN: só no corpo do POST; vai ao filho por arquivo temp; apagado no finally.
Nunca loga PIN, nunca grava em .cred/banco/argv.

Dois tokens nesta casa (oficial, 05/10/2026): SafeID (SafeSign/aetpkss1.dll)
e A3 SafeNet/Gemalto (eTPKCS11.dll / IDPrimePKCS1164.dll).

Driver (override, nesta ordem):
  1. --driver CAMINHO_OU_NOME
  2. env CG_A3_DRIVER
  3. arquivo a3_local.json / %PROGRAMDATA%/CartorioGestao/a3_local.json
     {"driver": "C:/Windows/System32/aetpkss1.dll"}
  4. auto-detecção pelos nomes conhecidos (só olha o disco; NÃO carrega)

Uso:
  py -3 a3_servico_local.py
  py -3 a3_servico_local.py --porta 8766
  py -3 a3_servico_local.py --driver aetpkss1.dll
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Nomes medidos / candidatos nesta casa (05/10/2026).
# SafeID → SafeSign IC (aetpkss1.dll); A3 → SafeNet / Gemalto IDPrime.
# WDPKCS*.dll NÃO encontrado no SERVIDOR (Watchdata ausente) — mantido na
# lista só como candidato teórico; o status reporta o que existir de fato.
DRIVERS_CONHECIDOS: tuple[str, ...] = (
    "aetpkss1.dll",          # SafeSign IC / SafeID (medido System32+SysWOW64)
    "aetpkss1_64.dll",
    "eTPKCS11.dll",          # SafeNet Authentication Client
    "IDPrimePKCS1164.dll",   # Gemalto IDGo 800
    "IDPrimePKCS11.dll",
    "WDPKCS64.dll",          # Watchdata (ausente neste servidor)
    "WDPKCS.dll",
    "wdpkcs.dll",
)

_PASTAS_EXTRA: tuple[str, ...] = (
    "SafeNet", "Watchdata", "SafeID", "SafeSign", "Gemalto",
    "Athena", "A.E.T. Europe", "AET", "Charismathics",
)

HOST_PADRAO = "127.0.0.1"
PORTA_PADRAO = 8766
PRAZO_FILHO_SEGUNDOS = 45
ENV_DRIVER = "CG_A3_DRIVER"
NOME_CONFIG = "a3_local.json"

_ASSINADOR = Path(__file__).with_name("a3_assinador_filho.py")

log = logging.getLogger("a3_servico_local")

# Override resolvido no boot (main) — None = auto.
_DRIVER_FORCADO: str | None = None


class ServicoA3Error(ValueError):
    """Erro com frase pronta para o balcão / cliente."""


def _windir() -> Path:
    return Path(Path(sys.prefix).anchor) / "Windows"


def _program_files() -> list[Path]:
    raiz = Path(Path(sys.prefix).anchor)
    out: list[Path] = []
    for nome in ("Program Files", "Program Files (x86)"):
        pasta = raiz / nome
        if pasta.is_dir():
            out.append(pasta)
    return out


def driver_disponivel(nome: str) -> Path | None:
    """Onde o driver está no Windows — só olha o arquivo, NÃO carrega.

    Aceita nome solto (procura System32/SysWOW64) ou caminho absoluto.
    """
    p = Path(nome)
    if p.is_file():
        return p.resolve()
    windir = _windir()
    for pasta in ("System32", "SysWOW64"):
        candidato = windir / pasta / nome
        if candidato.is_file():
            return candidato
    return None


def _listar_em_pasta(pasta: Path, nomes: tuple[str, ...],
                     *, recursivo: bool = False) -> list[Path]:
    """Lista DLLs candidatas. recursivo=True desce no máx. 2 níveis (rápido)."""
    achados: list[Path] = []
    if not pasta.is_dir():
        return achados
    nomes_l = {x.lower() for x in nomes}

    def _serve(c: Path) -> bool:
        if not c.is_file() or c.suffix.lower() != ".dll":
            return False
        n = c.name.lower()
        return n in nomes_l or "pkcs" in n

    # nível 0
    try:
        for nome in nomes:
            c = pasta / nome
            if c.is_file():
                achados.append(c)
        for c in pasta.iterdir():
            if _serve(c):
                achados.append(c)
    except OSError:
        return achados

    if not recursivo:
        return achados

    # níveis 1 e 2 apenas (evita rglob profundo em Program Files)
    try:
        subdirs = [d for d in pasta.iterdir() if d.is_dir()]
    except OSError:
        return achados
    for d1 in subdirs:
        try:
            for c in d1.iterdir():
                if _serve(c):
                    achados.append(c)
                elif c.is_dir():
                    try:
                        for c2 in c.iterdir():
                            if _serve(c2):
                                achados.append(c2)
                    except OSError:
                        pass
        except OSError:
            continue
        if len(achados) > 80:
            break
    return achados


def listar_candidatos_no_disco() -> list[dict[str, str]]:
    """Lista DLLs PKCS#11 candidatas no disco — SEM carregar nenhuma."""
    vistos: set[str] = set()
    saida: list[dict[str, str]] = []

    def _add(caminho: Path, origem: str) -> None:
        try:
            chave = str(caminho.resolve()).lower()
        except OSError:
            chave = str(caminho).lower()
        if chave in vistos:
            return
        vistos.add(chave)
        saida.append({
            "nome": caminho.name,
            "caminho": str(caminho),
            "origem": origem,
        })

    windir = _windir()
    for pasta_nome in ("System32", "SysWOW64"):
        pasta = windir / pasta_nome
        for c in _listar_em_pasta(pasta, DRIVERS_CONHECIDOS, recursivo=False):
            _add(c, pasta_nome)

    for pf in _program_files():
        for sub in _PASTAS_EXTRA:
            pasta = pf / sub
            if not pasta.is_dir():
                continue
            for c in _listar_em_pasta(pasta, DRIVERS_CONHECIDOS, recursivo=True):
                _add(c, f"{pf.name}/{sub}")

    prioridade = {n.lower(): i for i, n in enumerate(DRIVERS_CONHECIDOS)}

    def _chave(item: dict[str, str]) -> tuple[int, str]:
        return (prioridade.get(item["nome"].lower(), 999), item["caminho"].lower())

    saida.sort(key=_chave)
    return saida


def _ler_config_json() -> str | None:
    candidatos = [
        Path(__file__).with_name(NOME_CONFIG),
        Path(os.environ.get("PROGRAMDATA") or r"C:\ProgramData")
        / "CartorioGestao" / NOME_CONFIG,
    ]
    for caminho in candidatos:
        if not caminho.is_file():
            continue
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        driver = str(dados.get("driver") or "").strip()
        if driver:
            return driver
    return None


def resolver_driver(*, forcar: str | None = None) -> Path:
    """Resolve o driver: override → env → JSON → auto-detecção."""
    pedido = (forcar or _DRIVER_FORCADO or os.environ.get(ENV_DRIVER)
              or _ler_config_json() or "").strip()
    if pedido:
        achado = driver_disponivel(pedido)
        if achado is None:
            raise ServicoA3Error(
                f"driver configurado não encontrado no disco: {pedido}. "
                f"Candidatos: ver GET /saude → campo 'candidatos'")
        return achado

    for nome in DRIVERS_CONHECIDOS:
        achado = driver_disponivel(nome)
        if achado is not None:
            return achado

    candidatos = listar_candidatos_no_disco()
    if candidatos:
        nomes = ", ".join(c["nome"] for c in candidatos[:8])
        raise ServicoA3Error(
            "nenhum driver da lista preferida foi escolhido automaticamente, "
            f"mas há candidatos no disco ({nomes}). Configure com "
            f"--driver, env {ENV_DRIVER} ou {NOME_CONFIG}")
    raise ServicoA3Error(
        "nenhum driver PKCS#11 candidato foi encontrado "
        "(aetpkss1.dll / eTPKCS11.dll / IDPrimePKCS1164.dll / WDPKCS*). "
        "Instale o middleware do token (SafeSign/SafeID, SafeNet ou Gemalto) "
        "ou informe --driver")


def detectar_driver() -> Path:
    return resolver_driver()


def _chamar_filho(pedido: dict[str, Any]) -> dict[str, Any]:
    if not _ASSINADOR.exists():
        raise ServicoA3Error(
            f"assinador isolado não encontrado: {_ASSINADOR.name}")

    with tempfile.TemporaryDirectory(prefix="cg_a3_svc_") as pasta:
        area = Path(pasta)
        entrada = area / "entrada.json"
        saida = area / "saida.json"
        entrada.write_text(
            json.dumps(pedido, ensure_ascii=False), encoding="utf-8")
        try:
            subprocess.run(
                [sys.executable, str(_ASSINADOR), str(entrada), str(saida)],
                capture_output=True, timeout=PRAZO_FILHO_SEGUNDOS, check=False)
        except (subprocess.TimeoutExpired, OSError):
            pass
        finally:
            entrada.unlink(missing_ok=True)

        erro_path = area / "saida.json.erro"
        if erro_path.exists():
            detalhe = json.loads(erro_path.read_text(encoding="utf-8"))
            raise ServicoA3Error(
                f"o assinador A3 não conseguiu: {detalhe.get('erro')}")

        if not saida.exists() or saida.stat().st_size == 0:
            raise ServicoA3Error(
                "o processo do assinador A3 não devolveu nada — se o token "
                "não estiver conectado ou o driver tiver travado, é isto "
                "que acontece. O serviço local continua de pé")

        return json.loads(saida.read_text(encoding="utf-8"))


def _driver_configurado() -> bool:
    return bool(_DRIVER_FORCADO or os.environ.get(ENV_DRIVER) or _ler_config_json())


def _drivers_a_tentar() -> list[Path]:
    """O preferido primeiro, depois os outros candidatos do disco.

    13/10/2026: há DOIS tokens nesta casa (SafeID e A3 SafeNet/Gemalto), e o
    preferido da lista — `aetpkss1.dll` — respondeu `C_GetSlotList` com erro
    0x06 na sonda deste dia. Escolher pelo nome da DLL assinaria com o driver
    errado; quem decide é o driver que ENXERGA o certificado. Com driver
    configurado (--driver, env ou json), só ele.
    """
    primeiro = detectar_driver()
    if _driver_configurado():
        return [primeiro]
    vistos = {str(primeiro).lower()}
    lista = [primeiro]
    for c in listar_candidatos_no_disco():
        if c["caminho"].lower() not in vistos:
            vistos.add(c["caminho"].lower())
            lista.append(Path(c["caminho"]))
    return lista


#: thumbprint -> driver que o enxergou (vale enquanto o serviço estiver de pé).
_DRIVER_DO_CERTIFICADO: dict[str, str] = {}


def listar_certificados() -> dict[str, Any]:
    """Os certificados de TODOS os drivers candidatos, cada um no seu filho."""
    certs: list[dict[str, Any]] = []
    erros: list[str] = []
    algum_respondeu = False
    for driver in _drivers_a_tentar():
        try:
            r = _chamar_filho({"op": "listar", "driver": str(driver)})
        except ServicoA3Error as exc:
            erros.append(str(exc))
            continue
        algum_respondeu = True
        for c in r.get("certificados") or []:
            c = dict(c, driver=str(driver))
            certs.append(c)
            if c.get("thumbprint"):
                _DRIVER_DO_CERTIFICADO[str(c["thumbprint"]).upper()] = str(driver)
    if not algum_respondeu:
        raise ServicoA3Error(erros[0] if erros else "nenhum driver respondeu")
    return {"certificados": certs,
            "driver": certs[0]["driver"] if certs else None,
            "aviso": None if certs else "nenhum token conectado nesta máquina",
            "falhas": erros}


def _driver_para(thumbprint: str | None) -> Path:
    """O driver que tem o certificado pedido (ou o primeiro que tiver algum)."""
    if _driver_configurado():
        return detectar_driver()
    alvo = (thumbprint or "").strip().upper().replace(":", "").replace(" ", "")
    if alvo and alvo in _DRIVER_DO_CERTIFICADO:
        return Path(_DRIVER_DO_CERTIFICADO[alvo])
    try:
        certs = listar_certificados()["certificados"]
    except ServicoA3Error:
        certs = []
    achado = next((c for c in certs
                   if not alvo or str(c.get("thumbprint")).upper() == alvo), None)
    # Sem certificado visível, o preferido: o filho dirá «nenhum token» com a
    # frase dele, que é melhor que uma minha adivinhando o motivo.
    return Path(achado["driver"]) if achado else detectar_driver()


def assinar_pdf(pdf: bytes, pin: str, *,
                thumbprint: str | None = None) -> dict[str, Any]:
    if not pin:
        raise ServicoA3Error(
            "digite o PIN do certificado antes de assinar — ele não fica "
            "guardado em lugar nenhum, e é pedido a cada assinatura")
    if not pdf:
        raise ServicoA3Error("PDF vazio — nada para assinar")
    if not pdf[:5].startswith(b"%PDF"):
        raise ServicoA3Error(
            "o arquivo não parece PDF (faltou o cabeçalho %PDF)")

    driver = _driver_para(thumbprint)
    pedido: dict[str, Any] = {
        "op": "assinar_pdf",
        "driver": str(driver),
        "pin": pin,
        "pdf_b64": base64.b64encode(pdf).decode("ascii"),
    }
    if thumbprint:
        pedido["thumbprint"] = thumbprint
    return _chamar_filho(pedido)


#: O que o CCN assina no `X-Signature` é um JSON curto; 64 KB sobra.
LIMITE_CADES = 64 * 1024

#: O lote pelo Windows: quem decide o tamanho é quem chama, e este é o teto do
#: serviço. O corpo leva todos os PDFs, e por isso tem limite próprio.
LIMITE_DE_PDFS_NO_LOTE = 50
LIMITE_DO_CORPO_DO_LOTE = 200 * 1024 * 1024


def assinar_cades(payload: bytes, pin: str, *, thumbprint: str | None = None,
                  anexado: bool = True) -> dict[str, Any]:
    """CAdES-BES do `payload` (13/10/2026). O envelope volta conferido do filho."""
    if not pin:
        raise ServicoA3Error(
            "digite o PIN do certificado antes de assinar — ele não fica "
            "guardado em lugar nenhum, e é pedido a cada assinatura")
    if not payload:
        raise ServicoA3Error("nada para assinar")
    if len(payload) > LIMITE_CADES:
        raise ServicoA3Error("conteúdo grande demais para esta rota (64 KB); "
                             "documento se assina por /assinar/pdf")
    pedido: dict[str, Any] = {
        "op": "assinar_cades",
        "driver": str(_driver_para(thumbprint)),
        "pin": pin,
        "payload_b64": base64.b64encode(payload).decode("ascii"),
        "anexado": bool(anexado),
    }
    if thumbprint:
        pedido["thumbprint"] = thumbprint
    return _chamar_filho(pedido)


ORIGENS_DE_EXTENSAO = ("chrome-extension://", "moz-extension://")


def origem_recusada(origem: str | None, tipo_conteudo: str | None,
                    metodo: str) -> str | None:
    """Recusa pedido que veio de PÁGINA DA INTERNET — 13/10/2026.

    O serviço escuta só em 127.0.0.1, e isso não basta: qualquer site aberto no
    navegador desta máquina consegue mandar um POST para 127.0.0.1:8766. Ele não
    sabe o PIN, mas PINs errados em sequência BLOQUEIAM o token do delegatário.
    Passam: quem não manda `Origin` (o Cartório Gestão, a linha de comando) e as
    extensões. E POST só com `application/json`, que obriga o navegador a
    perguntar antes (preflight) — pergunta que este serviço não responde.
    """
    if origem and not origem.startswith(ORIGENS_DE_EXTENSAO):
        return ("pedido recusado: veio de uma página da internet "
                f"({origem}). O assinador só atende o Cartório Gestão e a "
                "extensão CG CCN Assistente")
    if metodo == "POST" and "application/json" not in (tipo_conteudo or "").lower():
        return "pedido recusado: o corpo tem de ser JSON (Content-Type: application/json)"
    return None


def status_payload() -> dict[str, Any]:
    candidatos = listar_candidatos_no_disco()
    driver = None
    erro_driver = None
    try:
        driver = str(detectar_driver())
    except ServicoA3Error as exc:
        erro_driver = str(exc)
    return {
        "ok": True,
        "servico": "a3-local",
        "host": HOST_PADRAO,
        "porta": PORTA_PADRAO,
        "driver": driver,
        "erro_driver": erro_driver,
        "candidatos": candidatos,
        "drivers_conhecidos": list(DRIVERS_CONHECIDOS),
        "override": {
            "arg_ou_boot": _DRIVER_FORCADO,
            "env": os.environ.get(ENV_DRIVER),
            "config_json": _ler_config_json(),
        },
        "ccn": False,
        "cades": True,
        "rotas": ["GET /saude", "GET /certificados", "POST /assinar/pdf",
                  "POST /assinar/pdf-windows",
                  "POST /assinar/pdfs-windows",
                  "POST /assinar/cades"],
        "aviso": "este serviço só assina — não fala com e-Notariado/CCN; "
                 "dois tokens: SafeID (aetpkss1) e A3 SafeNet/Gemalto",
    }


def _json_resposta(handler: BaseHTTPRequestHandler, codigo: int,
                   corpo: dict[str, Any]) -> None:
    bruto = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    handler.send_response(codigo)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(bruto)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(bruto)


def _ler_json(handler: BaseHTTPRequestHandler, *,
              limite: int = 30 * 1024 * 1024) -> dict[str, Any]:
    tamanho = int(handler.headers.get("Content-Length") or "0")
    if tamanho <= 0:
        return {}
    if tamanho > limite:
        raise ServicoA3Error(
            f"corpo grande demais (limite {limite // (1024 * 1024)} MB)")
    bruto = handler.rfile.read(tamanho)
    try:
        return json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServicoA3Error(f"JSON inválido: {exc}") from exc


class Manipulador(BaseHTTPRequestHandler):
    server_version = "A3ServicoLocal/1.0"

    def log_message(self, fmt: str, *args) -> None:
        try:
            caminho = urlparse(self.path).path
        except Exception:
            caminho = "?"
        log.info("%s %s", self.command, caminho)

    def do_OPTIONS(self) -> None:  # noqa: N802
        # Preflight de página da internet: não se responde que pode.
        _json_resposta(self, 403, {"ok": False, "erro": "sem CORS neste serviço"})

    def do_GET(self) -> None:  # noqa: N802
        caminho = urlparse(self.path).path.rstrip("/") or "/"
        recusa = origem_recusada(self.headers.get("Origin"), None, "GET")
        if recusa:
            _json_resposta(self, 403, {"ok": False, "erro": recusa})
            return
        try:
            if caminho in ("/saude", "/health"):
                corpo = status_payload()
                corpo["porta"] = self.server.server_address[1]
                _json_resposta(self, 200, corpo)
                return
            if caminho == "/certificados":
                resultado = listar_certificados()
                _json_resposta(self, 200, {
                    "ok": True,
                    "certificados": resultado.get("certificados") or [],
                    "driver": resultado.get("driver"),
                    "aviso": resultado.get("aviso"),
                    "falhas": resultado.get("falhas") or [],
                })
                return
            _json_resposta(self, 404, {
                "ok": False,
                "erro": f"rota desconhecida: {caminho}",
            })
        except ServicoA3Error as exc:
            _json_resposta(self, 400, {"ok": False, "erro": str(exc)})
        except Exception as exc:  # noqa: BLE001
            log.exception("erro inesperado em GET")
            _json_resposta(self, 500, {
                "ok": False,
                "erro": f"erro interno do serviço A3: {exc}",
            })

    def do_POST(self) -> None:  # noqa: N802
        caminho = urlparse(self.path).path.rstrip("/") or "/"
        recusa = origem_recusada(self.headers.get("Origin"),
                                 self.headers.get("Content-Type"), "POST")
        if recusa:
            _json_resposta(self, 403, {"ok": False, "erro": recusa})
            return
        try:
            if caminho == "/assinar/cades":
                corpo = _ler_json(self)
                if corpo.get("payload_b64"):
                    payload = base64.b64decode(corpo["payload_b64"])
                else:
                    payload = str(corpo.get("payload_utf8") or "").encode("utf-8")
                thumb = corpo.get("thumbprint")
                resultado = assinar_cades(
                    payload, str(corpo.get("pin") or ""),
                    thumbprint=str(thumb) if thumb else None,
                    anexado=corpo.get("anexado", True) is not False)
                corpo["pin"] = ""
                _json_resposta(self, 200, {
                    "ok": True,
                    "formato": resultado.get("formato"),
                    "x_signature_b64": resultado.get("x_signature_b64"),
                    "cms_b64": resultado.get("cms_b64"),
                    "certificado_b64": resultado.get("certificado_b64"),
                    "subject": resultado.get("subject"),
                    "thumbprint": resultado.get("thumbprint"),
                    "mecanismo": resultado.get("mecanismo"),
                })
                return
            if caminho == "/assinar/pdf-windows":
                # ACRÉSCIMO DE 15/10/2026 (sessão do protesto): assina pelo
                # REPOSITÓRIO DO WINDOWS, o caminho que os sites usam — o
                # PKCS#11 do SafeSign falha nesta casa (código 6) e o mesmo
                # token assina por aqui. O PIN NÃO passa por este serviço: é a
                # janela do próprio token que o pede ao titular. Ver
                # `a3_windows`. As rotas antigas não mudaram.
                import a3_windows
                corpo = _ler_json(self)
                pdf_b64 = corpo.get("pdf_b64") or ""
                if not pdf_b64:
                    raise ServicoA3Error("informe pdf_b64 no corpo JSON")
                try:
                    feito = a3_windows.assinar_pdf(
                        base64.b64decode(pdf_b64),
                        thumbprint=str(corpo.get("thumbprint") or ""))
                except a3_windows.A3WindowsError as exc:
                    raise ServicoA3Error(str(exc)) from exc
                _json_resposta(self, 200, {
                    "ok": True, "formato": "pkcs7-anexado-windows",
                    "cms_b64": base64.b64encode(feito["p7s"]).decode("ascii"),
                    "thumbprint": feito["thumbprint"],
                    "mecanismo": "windows-cryptoapi"})
                return
            if caminho == "/assinar/pdfs-windows":
                # O LOTE PELO WINDOWS (30/10/2026): todos os PDFs num PowerShell
                # só, para o token não pedir o PIN a cada um (`a3_windows.
                # assinar_pdfs`). A guarda de origem, lá em cima, vale igual, e
                # o PIN continua sem passar por aqui. A falha do token volta em
                # `falha`, com HTTP 200: os que já foram assinados vêm junto.
                import a3_windows
                corpo = _ler_json(self, limite=LIMITE_DO_CORPO_DO_LOTE)
                lista = corpo.get("pdfs_b64")
                if not isinstance(lista, list) or not lista:
                    raise ServicoA3Error("informe pdfs_b64 no corpo JSON")
                if len(lista) > LIMITE_DE_PDFS_NO_LOTE:
                    raise ServicoA3Error(
                        f"são {len(lista)} PDFs, e o serviço assina até "
                        f"{LIMITE_DE_PDFS_NO_LOTE} de cada vez")
                try:
                    feito = a3_windows.assinar_pdfs(
                        [base64.b64decode(x) for x in lista],
                        thumbprint=str(corpo.get("thumbprint") or ""))
                except a3_windows.A3WindowsError as exc:
                    raise ServicoA3Error(str(exc)) from exc
                _json_resposta(self, 200, {
                    "ok": True, "formato": "pkcs7-anexado-windows",
                    "mecanismo": "windows-cryptoapi",
                    "falha": feito["falha"],
                    "itens": [{
                        "indice": item["indice"],
                        "cms_b64": base64.b64encode(item["p7s"]).decode("ascii"),
                        "thumbprint": item["thumbprint"],
                    } for item in feito["assinados"]]})
                return
            if caminho != "/assinar/pdf":
                _json_resposta(self, 404, {
                    "ok": False,
                    "erro": f"rota desconhecida: {caminho}",
                })
                return
            corpo = _ler_json(self)
            pin = str(corpo.get("pin") or "")
            thumb = corpo.get("thumbprint")
            pdf_b64 = corpo.get("pdf_b64") or ""
            if not pdf_b64:
                raise ServicoA3Error("informe pdf_b64 no corpo JSON")
            pdf = base64.b64decode(pdf_b64)
            resultado = assinar_pdf(
                pdf, pin,
                thumbprint=str(thumb) if thumb else None)
            pin = ""
            _json_resposta(self, 200, {
                "ok": True,
                "formato": resultado.get("formato"),
                "cms_b64": resultado.get("cms_b64"),
                "assinatura_b64": resultado.get("assinatura_b64"),
                "certificado_b64": resultado.get("certificado_b64"),
                "mecanismo": resultado.get("mecanismo"),
                "subject": resultado.get("subject"),
                "thumbprint": resultado.get("thumbprint"),
                "aviso_cms": resultado.get("aviso_cms"),
            })
        except ServicoA3Error as exc:
            _json_resposta(self, 400, {"ok": False, "erro": str(exc)})
        except Exception as exc:  # noqa: BLE001
            log.exception("erro inesperado em POST")
            _json_resposta(self, 500, {
                "ok": False,
                "erro": f"erro interno do serviço A3: {exc}",
            })


def validar_bind(host: str) -> str:
    h = (host or "").strip().lower()
    if h in ("0.0.0.0", "::", "[::]", "*"):
        raise SystemExit(
            "RECUSADO: o serviço A3 só escuta em 127.0.0.1 "
            "(não faz bind em 0.0.0.0 / ::). Porta aprovada: 8766.")
    if h not in ("127.0.0.1", "localhost"):
        raise SystemExit(
            f"RECUSADO: host '{host}' não permitido. Use 127.0.0.1.")
    return "127.0.0.1"


def main(argv: list[str] | None = None) -> int:
    global _DRIVER_FORCADO

    parser = argparse.ArgumentParser(
        description="Serviço local A3 (só 127.0.0.1)")
    parser.add_argument("--host", default=HOST_PADRAO)
    parser.add_argument("--porta", type=int, default=PORTA_PADRAO)
    parser.add_argument(
        "--driver", default=None,
        help="DLL PKCS#11 (nome ou caminho). Sobrescreve env/JSON/auto.")
    args = parser.parse_args(argv)

    host = validar_bind(args.host)
    porta = int(args.porta)
    if porta <= 0 or porta > 65535:
        raise SystemExit("porta inválida")

    _DRIVER_FORCADO = (args.driver or None)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    candidatos = listar_candidatos_no_disco()
    log.info("candidatos PKCS#11 no disco (%d) — sem carregar:", len(candidatos))
    for c in candidatos:
        log.info("  %s  (%s)", c["caminho"], c["origem"])

    try:
        driver = detectar_driver()
        log.info("driver em uso: %s", driver)
    except ServicoA3Error as exc:
        log.warning("%s — /certificados e /assinar/pdf falharão até configurar",
                    exc)

    servidor = ThreadingHTTPServer((host, porta), Manipulador)
    log.info("A3 serviço local em http://%s:%s  (Ctrl+C para parar)",
             host, porta)
    log.info("rotas: GET /saude  GET /certificados  POST /assinar/pdf  POST /assinar/cades")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        log.info("encerrado")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
