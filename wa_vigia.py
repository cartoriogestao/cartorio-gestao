"""O vigia do WhatsApp: a mensagem do cliente chega à tela em segundos.

    «preciso que atualize em tempo real (se nao possivel com frequencia de 30s
     (se abrir uma janela ou aviso no windows)» — o oficial, 29/10/2026

POR QUE EXISTE
    A mensagem só saía da caixa-postal da VPS pela automação, de 2 em 2
    minutos, das 6h às 22h — e só com o processo ligado (ele nasce desligado).
    O atendente com IA nem isso: não estava ligado a rodada nenhuma, e só
    respondia quando alguém clicava. Na prática o cliente esperava minutos pela
    primeira resposta, e à noite até as 6h.

O QUE ELE FAZ, A CADA VOLTA (`um_ciclo`)
    1. busca na caixa-postal, aplica na fila e confirma (`wa_puxar`) — os três
       passos de sempre, com a rede fora da transação;
    2. baixa os arquivos que os clientes mandaram (`wa_midia`);
    3. roda o atendente com IA, se ligado (`wa_atendente.rodada`);
    4. manda o aviso de fora do horário, se ligado (`wa_rotina`);
    5. de hora em hora, resolve a conversa parada (`wa_rotina.encerrar_paradas`).

    A volta é de `vigia_segundos` em `vigia_segundos` (padrão 20 s, na tela do
    atendente; «0» desliga). Sem `caixa_url` gravada, ele só espera.

ONDE ELE RODA
    Numa linha de execução do PRÓPRIO SERVIDOR (`app.main`, depois de montar a
    aplicação), e não em `create_app` — a suíte monta milhares de aplicações e
    nenhuma deve ficar buscando. A automação de 2 em 2 minutos continua valendo
    como reserva: as duas podem rodar juntas sem dobrar nada — a mensagem é
    única pelo `meta_id`, a IA marca o que pegou antes de responder
    (`ia_situacao`), o arquivo também (`midia_situacao`), e o aviso de fora do
    horário também (`fora_horario_avisado_em`).

FALHA NÃO DERRUBA O SERVIDOR
    Tudo o que a volta faz está num `try`: o erro vai ao log, a volta seguinte
    espera um minuto, e o servidor segue atendendo o balcão. Uma caixa-postal
    fora do ar não pode tirar o sistema do ar.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

LOG = logging.getLogger(__name__)

ESPERA_SEM_CONFIGURACAO_S = 60
ESPERA_DEPOIS_DE_ERRO_S = 60
ENCERRAR_A_CADA_S = 3600

_linha: threading.Thread | None = None
_parar = threading.Event()
_trava = threading.Lock()
_ultimo_encerramento = 0.0


def _agora(db: Any) -> str:
    try:
        return str(db.now())[:19]
    except Exception:                                   # noqa: BLE001
        return datetime.now().replace(microsecond=0).isoformat()


def um_ciclo(db: Any, *, pasta_dados: Path, pasta_arquivos: Path,
             agora: str | None = None, http_get: Callable | None = None,
             http_post: Callable | None = None, https: Callable | None = None,
             conversar: Callable | None = None, encerrar: bool = False,
             serventia: Any = None) -> dict:
    """Uma volta do vigia. **FALA COM A REDE**, sempre fora de transação.

    Devolve o que cada passo fez. Um passo que falha não impede os outros: a
    mensagem que chegou é aplicada mesmo que o arquivo dela não baixe, e a IA
    responde mesmo que o aviso de fora do horário falhe."""
    import serventia as SERV
    import wa_atendente as ATENDENTE
    import wa_midia as MIDIA
    import wa_puxar as PUXAR
    import wa_rotina as ROTINA
    quando = agora or _agora(db)
    r: dict = {"quando": quando, "aplicadas": 0, "repetidas": 0, "entregas": 0,
               "arquivos": 0, "ia": 0, "avisos": 0, "encerradas": 0, "erros": []}
    with db.connect() as con:
        achado = (PUXAR.buscar_pendentes(con, http_get=http_get) if http_get
                  else PUXAR.buscar_pendentes(con))
    if achado.get("ok"):
        if serventia is None:
            try:
                serventia = SERV.dados(db.get_settings)
            except Exception:                           # noqa: BLE001 — o padrão serve
                serventia = None
        with db.transaction() as con:
            aplicado = PUXAR.aplicar_itens(con, achado["itens"], serventia=serventia,
                                           agora=quando)
        with db.connect() as con:
            if http_post:
                PUXAR.confirmar(con, aplicado.get("ids"), http_post=http_post)
            else:
                PUXAR.confirmar(con, aplicado.get("ids"))
        r["aplicadas"] = int(aplicado.get("aplicadas") or 0)
        r["repetidas"] = int(aplicado.get("repetidas") or 0)
        r["entregas"] = int(aplicado.get("entregas") or 0)
        if r["aplicadas"]:
            try:
                import identidade_do_robo as IDR
                db.log(None, "automação", "wa_puxar", "wa_conversa", None,
                       {"ok": True, "aplicadas": r["aplicadas"], "repetidas": r["repetidas"],
                        "pelo": "vigia"},
                       agente="vigia do WhatsApp (servidor)",
                       a_mando_de=IDR.PELO_RESPONSAVEL)
            except Exception:                           # noqa: BLE001
                LOG.exception("a mensagem foi aplicada, e a auditoria do vigia falhou")
    else:
        r["caixa"] = achado.get("motivo")
    passos = (
        ("arquivos", lambda: MIDIA.baixar_pendentes(
            db, pasta_arquivos=pasta_arquivos, agora=quando, https=https)["baixados"]),
        ("ia", lambda: len(ATENDENTE.rodada(
            db, agora=quando, pasta_de_dados=pasta_dados, conversar=conversar,
            http_post=http_post, https=https).get("conversas") or [])),
        ("avisos", lambda: ROTINA.avisar_fora_do_horario(db, agora=quando,
                                                          http_post=http_post)),
    )
    if encerrar:
        passos += (("encerradas", lambda: ROTINA.encerrar_paradas(db, agora=quando)),)
    for nome, passo in passos:
        try:
            r[nome] = int(passo() or 0)
        except Exception as falha:                      # noqa: BLE001
            LOG.exception("vigia do WhatsApp: o passo «%s» falhou", nome)
            r["erros"].append(f"{nome}: {type(falha).__name__}")
    return r


def segundos_da_volta(db: Any) -> int | None:
    """De quantos em quantos segundos buscar; None = não buscar agora (sem
    caixa-postal configurada, ou vigia desligado na tela)."""
    import wa_balcao as BALCAO
    import wa_rotina as ROTINA
    import wa_schema as WA
    with db.connect() as con:
        if not BALCAO.ler_config(con, WA.CHAVE_CAIXA_URL):
            return None
        segundos = ROTINA.config(con)["vigia_segundos"]
    if not segundos:
        return None
    return max(ROTINA.VIGIA_MINIMO_S, min(ROTINA.VIGIA_MAXIMO_S, int(segundos)))


def _laco(db: Any, pasta_dados: Path, pasta_arquivos: Callable[[], Path]) -> None:
    global _ultimo_encerramento
    LOG.info("vigia do WhatsApp ligado")
    while not _parar.is_set():
        espera = ESPERA_SEM_CONFIGURACAO_S
        try:
            segundos = segundos_da_volta(db)
            if segundos:
                espera = segundos
                encerrar = time.monotonic() - _ultimo_encerramento >= ENCERRAR_A_CADA_S
                r = um_ciclo(db, pasta_dados=pasta_dados, pasta_arquivos=pasta_arquivos(),
                             encerrar=encerrar)
                if encerrar:
                    _ultimo_encerramento = time.monotonic()
                if r["erros"]:
                    espera = max(espera, ESPERA_DEPOIS_DE_ERRO_S)
        except Exception:                               # noqa: BLE001
            LOG.exception("vigia do WhatsApp: a volta falhou; tento de novo em 1 minuto")
            espera = ESPERA_DEPOIS_DE_ERRO_S
        _parar.wait(espera)
    LOG.info("vigia do WhatsApp parado")


def iniciar(db: Any, *, pasta_dados: Path, pasta_arquivos: Callable[[], Path]) -> bool:
    """Liga o vigia numa linha de execução do servidor. Uma só por processo.
    `pasta_arquivos` é a função da casa (`archive_root`): a pasta é lida a cada
    volta, e mudar a configuração não exige reiniciar."""
    global _linha
    with _trava:
        if _linha is not None and _linha.is_alive():
            return False
        _parar.clear()
        _linha = threading.Thread(target=_laco, args=(db, Path(pasta_dados), pasta_arquivos),
                                  name="whatsapp-vigia", daemon=True)
        _linha.start()
        return True


def parar() -> None:
    _parar.set()


def pasta_de_arquivos(db: Any, pasta_dados: Path) -> Path:
    """A pasta dos arquivos da casa fora do Flask (a automação): a mesma régua
    de `app.archive_root` — a configurada, ou `<dados>/arquivos`."""
    try:
        configurada = (db.get_setting("archive_root", "") or "").strip()
    except Exception:                                   # noqa: BLE001
        configurada = ""
    raiz = Path(configurada).expanduser() if configurada else Path(pasta_dados) / "arquivos"
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz
