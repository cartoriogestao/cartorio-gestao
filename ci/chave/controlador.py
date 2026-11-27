#!/usr/bin/python3
# A CHAVE DA SUÍTE (27/11/2026) — reparte o servidor reserva entre a suíte e a IA local.
#
# A suíte roda numa máquina virtual (Colima) que reserva até 12 GB e usa 14 núcleos.
# A IA local (Ollama) precisa dessa memória. A chave tem duas posições:
#
#   «suite»  a máquina virtual e o executor do GitHub ficam ligados (como sempre foi);
#   «ia»     o executor espera a suíte em andamento terminar, sai do ar e a máquina
#            virtual desliga — a memória volta toda para o Mac. As suítes pedidas nesse
#            meio-tempo esperam na fila do GitHub e rodam quando a chave voltar.
#
# Quem escolhe a posição é o pedido (pedido.json), que o app da barra de menus grava:
#   - «auto»: segue a agenda (as janelas da IA); fora delas, suíte;
#   - «suite» ou «ia»: fixo, até mudar (ou até `ate`, quando o pedido tem prazo).
#
# Este programa roda como root (LaunchDaemon br.cartoriogestao.ci-chave), porque os
# serviços da suíte são do sistema. Por isso ele NÃO executa nada do pedido: só lê três
# campos, confere cada um e recusa o resto. O arquivo do pedido precisa ser do dono da
# pasta dele, e a pasta não pode ser gravável por outros.
#
# Roda com o python3 do macOS (3.9): nada de sintaxe mais nova.
from __future__ import annotations

import datetime as dt
import json
import os
import stat
import subprocess
import sys
import time
from typing import List, Optional, Tuple

PEDIDO = "/Users/Shared/CartorioGestao/chave-da-suite/pedido.json"
PASTA_ESTADO = "/Library/Application Support/CartorioGestao/chave-da-suite"
ESTADO = PASTA_ESTADO + "/estado.json"

USUARIO_CI = "ci-runner"
CASA_CI = "/Users/ci-runner"
COLIMA = "/opt/homebrew/bin/colima"
SERVICO_VM = "br.cartoriogestao.ci-colima"
SERVICO_EXECUTOR = "br.cartoriogestao.ci-executor"
PLIST = "/Library/LaunchDaemons/{}.plist"

# Sem pedido (ou com pedido estragado): a IA no expediente, a suíte no resto.
AGENDA_PADRAO = [{"dias": [0, 1, 2, 3, 4], "inicio": "08:00", "fim": "18:00"}]
MODOS = ("auto", "suite", "ia")
TAMANHO_MAXIMO = 16 * 1024
NOMES_DOS_DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


# ---------------------------------------------------------------------------
# O pedido: só dado, conferido campo a campo.
# ---------------------------------------------------------------------------
class Pedido:
    def __init__(self, modo: str = "auto", ate: Optional[float] = None,
                 agenda: Optional[list] = None, aviso: str = ""):
        self.modo = modo
        self.ate = ate
        self.agenda = agenda if agenda is not None else [dict(j) for j in AGENDA_PADRAO]
        self.aviso = aviso


def _hora(texto) -> Optional[int]:
    """«08:30» -> minutos do dia; qualquer outra coisa -> None."""
    if not isinstance(texto, str) or len(texto) != 5 or texto[2] != ":":
        return None
    h, m = texto[:2], texto[3:]
    if not (h.isdigit() and m.isdigit()):
        return None
    h, m = int(h), int(m)
    if h > 23 or m > 59:
        return None
    return h * 60 + m


def _janela(bruta) -> Optional[dict]:
    if not isinstance(bruta, dict):
        return None
    dias = bruta.get("dias")
    if not isinstance(dias, list) or not dias or len(dias) > 7:
        return None
    if not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in dias):
        return None
    inicio, fim = _hora(bruta.get("inicio")), _hora(bruta.get("fim"))
    if inicio is None or fim is None or inicio == fim:
        return None
    return {"dias": sorted(set(dias)), "inicio": bruta["inicio"], "fim": bruta["fim"]}


def ler_pedido(texto: Optional[str]) -> Pedido:
    """O pedido conferido. Sem arquivo -> o padrão; o que não confere -> o padrão, com aviso."""
    if texto is None:
        return Pedido()
    try:
        bruto = json.loads(texto)
    except ValueError:
        return Pedido(aviso="o pedido não é JSON; vale o automático")
    if not isinstance(bruto, dict):
        return Pedido(aviso="o pedido não é um objeto; vale o automático")
    modo = bruto.get("modo", "auto")
    if modo not in MODOS:
        return Pedido(aviso="modo desconhecido no pedido; vale o automático")
    ate = bruto.get("ate")
    if ate is not None and (isinstance(ate, bool) or not isinstance(ate, (int, float))):
        ate = None
    agenda_bruta = bruto.get("agenda", AGENDA_PADRAO)
    if not isinstance(agenda_bruta, list) or len(agenda_bruta) > 20:
        return Pedido(modo=modo, ate=ate, aviso="agenda inválida; vale a agenda padrão")
    agenda = [j for j in (_janela(b) for b in agenda_bruta) if j]
    aviso = "" if len(agenda) == len(agenda_bruta) else "uma janela da agenda não confere e foi ignorada"
    return Pedido(modo=modo, ate=ate, agenda=agenda, aviso=aviso)


def ler_arquivo_do_pedido(caminho: str = PEDIDO) -> Optional[str]:
    """Lê o pedido sem seguir link, e só se ele for do dono da pasta, numa pasta fechada."""
    pasta = os.path.dirname(caminho)
    try:
        sp = os.lstat(pasta)
        if not stat.S_ISDIR(sp.st_mode) or sp.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            return None
        fd = os.open(caminho, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        sf = os.fstat(fd)
        if not stat.S_ISREG(sf.st_mode) or sf.st_uid != sp.st_uid or sf.st_size > TAMANHO_MAXIMO:
            return None
        return os.read(fd, TAMANHO_MAXIMO).decode("utf-8", "replace")
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# A decisão: pura, sem relógio nem sistema (os testes a exercitam).
# ---------------------------------------------------------------------------
def na_janela_da_ia(agenda: List[dict], agora: dt.datetime) -> bool:
    minuto = agora.hour * 60 + agora.minute
    hoje, ontem = agora.weekday(), (agora.weekday() - 1) % 7
    for j in agenda:
        ini, fim = _hora(j["inicio"]), _hora(j["fim"])
        if ini < fim:
            if hoje in j["dias"] and ini <= minuto < fim:
                return True
        else:  # atravessa a meia-noite: o dia é o do começo
            if (hoje in j["dias"] and minuto >= ini) or (ontem in j["dias"] and minuto < fim):
                return True
    return False


def posicao_desejada(pedido: Pedido, agora: dt.datetime) -> Tuple[str, str]:
    """('suite' | 'ia', por quê)."""
    if pedido.modo in ("suite", "ia"):
        if pedido.ate is None:
            return pedido.modo, "fixo pelo app"
        if agora.timestamp() < pedido.ate:
            fim = dt.datetime.fromtimestamp(pedido.ate).strftime("%H:%M")
            return pedido.modo, "pelo app até " + fim
    if na_janela_da_ia(pedido.agenda, agora):
        return "ia", "agenda: janela da IA"
    return "suite", "agenda: fora da janela da IA"


def proxima_troca(pedido: Pedido, agora: dt.datetime) -> Optional[dt.datetime]:
    """Quando a posição desejada muda de novo (procura de minuto em minuto, até 8 dias)."""
    atual = posicao_desejada(pedido, agora)[0]
    t = agora.replace(second=0, microsecond=0)
    for _ in range(8 * 24 * 60):
        t += dt.timedelta(minutes=1)
        if posicao_desejada(pedido, t)[0] != atual:
            return t
    return None


class Situacao:
    def __init__(self, vm_ligada: bool, executor_ligado: bool, suite_rodando: bool):
        self.vm_ligada = vm_ligada
        self.executor_ligado = executor_ligado
        self.suite_rodando = suite_rodando


def decidir(desejada: str, s: Situacao) -> Tuple[List[str], str]:
    """As ações que levam a situação à posição desejada, e o rótulo do momento.

    Nunca derruba uma suíte em andamento: quem quer interromper cancela a rodada no
    GitHub (o app faz isso e a põe de novo na fila); o executor fica livre e a chave segue.
    """
    if desejada == "suite":
        if not s.vm_ligada:
            return ["ligar_vm", "ligar_executor"], "ligando"
        if not s.executor_ligado:
            return ["ligar_executor"], "ligando"
        return [], "suite"
    if s.suite_rodando:
        return [], "esperando"
    acoes = []
    if s.executor_ligado:
        acoes.append("desligar_executor")
    if s.vm_ligada:
        acoes.append("desligar_vm")
    return acoes, ("desligando" if acoes else "ia")


# ---------------------------------------------------------------------------
# O sistema: o que se vê e o que se faz (só como root).
# ---------------------------------------------------------------------------
def _rodar(*cmd: str, tempo: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True, timeout=tempo)


def _processos_do_ci() -> List[Tuple[int, str]]:
    r = _rodar("/bin/ps", "-U", USUARIO_CI, "-o", "rss=,command=")
    linhas = []
    for linha in r.stdout.splitlines():
        partes = linha.strip().split(None, 1)
        if len(partes) == 2 and partes[0].isdigit():
            linhas.append((int(partes[0]), partes[1]))
    return linhas


def _servico_carregado(rotulo: str) -> bool:
    return _rodar("/bin/launchctl", "print", "system/" + rotulo).returncode == 0


def observar() -> Tuple[Situacao, float]:
    procs = _processos_do_ci()
    vm = [rss for rss, cmd in procs if "Virtualization.VirtualMachine" in cmd]
    rodando = any("Runner.Worker" in cmd for _, cmd in procs)
    s = Situacao(vm_ligada=_servico_carregado(SERVICO_VM) or bool(vm),
                 executor_ligado=_servico_carregado(SERVICO_EXECUTOR),
                 suite_rodando=rodando)
    return s, round(sum(vm) / 1048576, 1)


def _ligar(rotulo: str) -> None:
    _rodar("/bin/launchctl", "enable", "system/" + rotulo)
    if not _servico_carregado(rotulo):
        _rodar("/bin/launchctl", "bootstrap", "system", PLIST.format(rotulo))


def _desligar(rotulo: str) -> None:
    # `disable` vale também depois de reiniciar o Mac: o serviço não volta sozinho.
    _rodar("/bin/launchctl", "disable", "system/" + rotulo)
    if _servico_carregado(rotulo):
        _rodar("/bin/launchctl", "bootout", "system/" + rotulo, tempo=180)


def _colima(*args: str, tempo: int = 60) -> subprocess.CompletedProcess:
    return _rodar("/usr/bin/sudo", "-u", USUARIO_CI, "-H", "/usr/bin/env", "HOME=" + CASA_CI,
                  "PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                  COLIMA, *args, "--profile", "ci", tempo=tempo)


def agir(acao: str, registrar) -> None:
    if acao == "ligar_vm":
        _ligar(SERVICO_VM)
        for _ in range(60):  # até 5 min: o executor só sobe com o Docker da VM pronto
            if _colima("status").returncode == 0:
                return
            time.sleep(5)
        registrar("a VM não respondeu em 5 min; o executor sobe mesmo assim")
    elif acao == "ligar_executor":
        _ligar(SERVICO_EXECUTOR)
    elif acao == "desligar_executor":
        _desligar(SERVICO_EXECUTOR)
    elif acao == "desligar_vm":
        _desligar(SERVICO_VM)  # o colima em primeiro plano para a VM ao receber o SIGTERM
        for _ in range(24):
            if not any("Virtualization.VirtualMachine" in c for _, c in _processos_do_ci()):
                return
            time.sleep(5)
        registrar("a VM não parou em 2 min; colima stop --force")
        _colima("stop", "--force", tempo=120)


def gravar_estado(estado: dict) -> None:
    os.makedirs(PASTA_ESTADO, mode=0o755, exist_ok=True)
    tmp = ESTADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o644)
    os.replace(tmp, ESTADO)


def registrar(msg: str) -> None:
    print(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def descrever_agenda(agenda: List[dict]) -> str:
    if not agenda:
        return "sem janela da IA"
    partes = []
    for j in agenda:
        dias = ",".join(NOMES_DOS_DIAS[d] for d in j["dias"])
        partes.append("{} {}–{}".format(dias, j["inicio"], j["fim"]))
    return "; ".join(partes)


def um_passo(simular: bool = False) -> str:
    agora = dt.datetime.now()
    pedido = ler_pedido(ler_arquivo_do_pedido())
    desejada, motivo = posicao_desejada(pedido, agora)
    s, vm_gb = observar()
    acoes, momento = decidir(desejada, s)
    troca = proxima_troca(pedido, agora)
    estado = {
        "atualizado": agora.isoformat(timespec="seconds"),
        "modo": pedido.modo, "ate": pedido.ate, "agenda": pedido.agenda,
        "agenda_texto": descrever_agenda(pedido.agenda),
        "desejada": desejada, "motivo": motivo, "momento": momento,
        "vm_ligada": s.vm_ligada, "executor_ligado": s.executor_ligado,
        "suite_rodando": s.suite_rodando, "vm_gb": vm_gb,
        "proxima_troca": troca.isoformat(timespec="minutes") if troca else None,
        "aviso": pedido.aviso, "acoes": acoes,
    }
    if simular:
        print(json.dumps(estado, ensure_ascii=False, indent=1))
        return momento
    gravar_estado(estado)
    for acao in acoes:
        registrar("{} ({}; {})".format(acao, desejada, motivo))
        agir(acao, registrar)
    if acoes:  # o estado já com o resultado, para o app não mostrar o passo anterior
        s, vm_gb = observar()
        estado.update(vm_ligada=s.vm_ligada, executor_ligado=s.executor_ligado,
                      suite_rodando=s.suite_rodando, vm_gb=vm_gb, acoes=[],
                      momento=decidir(desejada, s)[1])
        gravar_estado(estado)
    return estado["momento"]


def main(argv: List[str]) -> int:
    if "--simular" in argv:  # mostra o que faria, sem fazer nada (não precisa de root)
        um_passo(simular=True)
        return 0
    if os.geteuid() != 0:
        print("O controlador da chave roda como root (LaunchDaemon). Para ver a decisão: --simular")
        return 1
    registrar("chave da suíte no ar")
    while True:
        try:
            momento = um_passo()
        except Exception as e:  # um tropeço não derruba a chave; o launchd a reergueria
            registrar("erro: {!r}".format(e))
            momento = "erro"
        # Esperando a suíte acabar, olha de 2 em 2 s: o executor sai do ar antes de
        # o GitHub entregar a rodada seguinte (que leva uns 10 s para chegar).
        time.sleep(2 if momento == "esperando" else 5)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
