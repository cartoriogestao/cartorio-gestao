# -*- coding: utf-8 -*-
"""A RESERVA DE MAQUINA DO SERVIDOR — o balcao nao disputa com o resto.

POR QUE ISTO EXISTE, e o que foi MEDIDO em 24/09/2026 nesta maquina

    O oficial disse que o sistema "tem ficado muito lento". A medicao achou a
    causa, e ela nao era falta de maquina: era **a prioridade em que o
    servidor roda**.

    O processo do servidor estava em `ABAIXO DO NORMAL`, com prioridade de
    memoria 2 (baixa). Isso quer dizer duas coisas, as duas ruins:

      · **de CPU**: qualquer processo comum da maquina — o navegador, o
        backup, o antivirus, um editor — passa na frente do balcao;
      · **de memoria**: as paginas do servidor sao as PRIMEIRAS que o Windows
        joga fora quando a RAM aperta. Medido: o processo da producao tinha
        pico de 95 MB residentes e estava reduzido a 29 MB, com 299.000
        falhas de pagina em duas horas — cada uma delas uma ida ao disco para
        buscar de volta codigo que ja tinha sido carregado.

    DE ONDE VEIO: nao foi ninguem que escolheu. O instalador registrava a
    tarefa do servidor com `New-ScheduledTaskSettingsSet` sem `-Priority`, e
    o padrao do Agendador de Tarefas do Windows e `7` = ABAIXO DO NORMAL. A
    classe se herda de pai para filho, entao a tarefa, o `cmd`, o `python` e
    todas as doze linhas do waitress nasciam rebaixados.

O QUANTO ISSO CUSTAVA, medido no `/saude` com 4 atendimentos ao mesmo tempo

        maquina vazia        abaixo do normal   240 ms   p95   311 ms   15,6/s
                             acima do normal    211 ms   p95   244 ms   19,0/s

        maquina CHEIA        abaixo do normal   551 ms   p95  7.719 ms    1,3/s
        (12 processos em     acima do normal    177 ms   p95   213 ms   22,4/s
         prioridade normal)

    **Com a maquina cheia, o pior atendimento caia de 233 ms para 10,2
    segundos.** E o que o oficial sentia. Com a reserva, o balcao com a
    maquina cheia responde IGUAL ao balcao com a maquina vazia — que e
    exatamente o que ele pediu: nao voltar a ficar lento quando outros
    processos estiverem rodando.

O QUE ESTA RESERVA FAZ, E O QUE ELA NAO FAZ

    FAZ quatro coisas, todas sobre o proprio processo:

      1. **classe ACIMA DO NORMAL** — o balcao passa na frente do que e
         comum. Nao `ALTA`: alta disputa com o proprio Windows e ja travou
         teclado e mouse em maquina de atendimento. Acima do normal ganha de
         tudo que importa e nao briga com nada que importa.
      2. **prioridade de memoria 5** — as paginas do servidor deixam de ser
         as primeiras da fila de despejo.
      3. **piso de residencia** — o Windows fica proibido de encolher o
         processo abaixo do piso. E o remedio das 299.000 falhas de pagina.
      4. **sem freio de eficiencia** — nesta maquina (i5-1235U) ha nucleos P
         e nucleos E. O EcoQoS empurra processo "de fundo" para os nucleos E
         e corta o relogio. Servidor de balcao nao e processo de fundo.

    **NAO FAZ milagre, e isto precisa ficar escrito.** O piso de residencia
    NAO carrega paginas: ele proibe o despejo. Medido — logo depois de pedir
    160 MB de piso, o processo continuava com 18 MB residentes, e foi subindo
    conforme atendeu. O ganho aparece ao longo do expediente, e nao no
    segundo seguinte.

    E ela NAO conserta a vazao do servidor. Medido no mesmo dia: o `/saude`
    custa 44 ms sozinho, e a vazao fica presa em ~20 pedidos por segundo
    independente de quantas linhas atendem — 1, 4 ou 12 dao o mesmo numero, e
    so a espera cresce. Isso e serializacao DENTRO do servidor, e tem dono
    proprio: cada pedido abre uma conexao nova e roda `PRAGMA
    journal_mode=WAL` nela (`database.py`), o que pede trava exclusiva. Esta
    reserva nao mexe nisso e nao finge ter mexido.

QUANTO SE RESERVA, e por que este numero

    Medido degrau a degrau, carregando o sistema de verdade:

        python vazio                                     14 MB
        + os modulos do sistema importados               44 MB
        + o app montado (Flask, rotas, esquema)          66 MB
        + uma conexao ao banco e uma consulta            67 MB
        + as doze conexoes das doze linhas do waitress   79 MB
        + cache de SQLite grande nas doze                84 MB

        pico real da producao em duas horas de balcao    95 MB

    `RESIDENTE_GARANTIDO_MB = 192` e o pico medido com o dobro de folga, para
    caber a geracao de certidao, de ODT e de imagem, que a medicao acima nao
    exercitou. Em 16 GB de RAM isso e 1,2% da maquina — barato demais para
    economizar em cima do balcao.

    **O MAXIMO FICA SOLTO, de proposito.** Limitar o teto faria o Windows
    despejar paginas justamente na hora em que o servidor esta montando um
    PDF grande — o oposto do que se quer.

ONDE ISTO E CHAMADO

    Em `app.main()`, uma vez, no arranque. Nao e rota, nao e tela, e nao tem
    botao: e condicao de funcionamento, como abrir a porta.

    O instalador tambem passou a registrar a tarefa com `-Priority 3`
    (`installer/instalar_servidor.ps1`) — numero MEDIDO em 24/09/2026, e nao
    consultado: tarefa com 3 produz processo AboveNormal, com 4 e 5 Normal, e
    com 7 (o padrao do Windows) BelowNormal. As duas coisas juntas de
    proposito: a tarefa conserta instalacao nova, e esta chamada conserta as
    maquinas onde a tarefa ja existe rebaixada.

    E ha a terceira, que e para AGORA: `reservar_processo(pid)`, chamada por
    `tools/reservar_a_maquina_do_balcao.ps1`, arruma o servidor que ja esta de
    pe **sem reiniciar o balcao** — porque a maquina desta casa nao pode
    esperar o proximo arranque no meio do expediente.
"""
from __future__ import annotations

import ctypes
import os
import sys

# ------------------------------------------------------------------ medidas
#
# O piso de residencia, em MB. Ver o cabecalho para a medicao degrau a degrau
# que produziu este numero.
RESIDENTE_GARANTIDO_MB = 192

# ABAIXO DISTO NAO SE TRAVA MEMORIA NENHUMA. Numa maquina pequena, prender
# 192 MB a forca tira do resto o que o resto precisa — e o sistema roda em
# maquina de balcao, que nem sempre e a de 16 GB onde isto foi medido.
RAM_MINIMA_DA_MAQUINA_MB = 4096

# ---------------------------------------------------------- nomes do Windows
#
# Constantes do `processthreadsapi.h` e do `winnt.h`. Escritas com o nome que
# o Windows lhes da, para quem for conferir na documentacao achar.
ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
NORMAL_PRIORITY_CLASS = 0x00000020
HIGH_PRIORITY_CLASS = 0x00000080
IDLE_PRIORITY_CLASS = 0x00000040
REALTIME_PRIORITY_CLASS = 0x00000100

PROCESS_SET_INFORMATION = 0x0200
PROCESS_SET_QUOTA = 0x0100
PROCESS_QUERY_INFORMATION = 0x0400

ProcessMemoryPriority = 0
ProcessPowerThrottling = 4

MEMORY_PRIORITY_NORMAL = 5

QUOTA_LIMITS_HARDWS_MIN_ENABLE = 0x00000001
QUOTA_LIMITS_HARDWS_MAX_DISABLE = 0x00000008

PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1

SE_PRIVILEGE_ENABLED = 0x00000002
TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY = 0x0008

# O nome que o Windows da a cada classe, para a mensagem sair legivel no log
# do arranque e na tela de diagnostico.
NOME_DA_CLASSE = {
    REALTIME_PRIORITY_CLASS: "tempo real",
    HIGH_PRIORITY_CLASS: "alta",
    ABOVE_NORMAL_PRIORITY_CLASS: "acima do normal",
    NORMAL_PRIORITY_CLASS: "normal",
    BELOW_NORMAL_PRIORITY_CLASS: "abaixo do normal",
    IDLE_PRIORITY_CLASS: "ociosa",
}

E_WINDOWS = os.name == "nt"


class _MEMORY_PRIORITY_INFORMATION(ctypes.Structure):
    _fields_ = [("MemoryPriority", ctypes.c_ulong)]


class _PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    _fields_ = [("Version", ctypes.c_ulong),
                ("ControlMask", ctypes.c_ulong),
                ("StateMask", ctypes.c_ulong)]


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", ctypes.c_ulong), ("HighPart", ctypes.c_long)]


class _LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", _LUID), ("Attributes", ctypes.c_ulong)]


class _TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [("PrivilegeCount", ctypes.c_ulong),
                ("Privileges", _LUID_AND_ATTRIBUTES * 1)]


class _PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


def _kernel32():
    """**O PSEUDO-HANDLE DO PROCESSO E -1, E O CTYPES O CORTA AO MEIO.**

    Sem declarar o tipo de retorno, o ctypes devolve `GetCurrentProcess()`
    como `int` de 32 bits, e toda medicao volta zerada — foi assim que a
    primeira medicao deste trabalho deu 0 MB em todos os degraus.

    **E DECLARADO O RETORNO, TEM DE SE DECLARAR TAMBEM CADA ENTRADA**, senao
    o handle agora grande estoura na passagem («int too long to convert»).
    As duas metades andam juntas, e e por isso que estao no mesmo lugar.
    """
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    h, u32, ul = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_ulong

    k32.GetCurrentProcess.restype = h
    k32.GetCurrentProcessId.restype = ul

    k32.GetPriorityClass.argtypes = [h]
    k32.GetPriorityClass.restype = ul
    k32.SetPriorityClass.argtypes = [h, ul]

    k32.GetProcessInformation.argtypes = [h, u32, ctypes.c_void_p, ul]
    k32.SetProcessInformation.argtypes = [h, u32, ctypes.c_void_p, ul]

    k32.GetProcessWorkingSetSizeEx.argtypes = [h, ctypes.c_void_p,
                                               ctypes.c_void_p,
                                               ctypes.c_void_p]
    k32.SetProcessWorkingSetSizeEx.argtypes = [h, ctypes.c_size_t,
                                               ctypes.c_size_t, ul]
    k32.GlobalMemoryStatusEx.argtypes = [ctypes.c_void_p]
    return k32


def _ram_da_maquina_mb() -> int:
    """A RAM fisica total, em MB. Zero quando nao se conseguiu ler."""
    if not E_WINDOWS:
        return 0

    class _MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    estado = _MEMORYSTATUSEX()
    estado.dwLength = ctypes.sizeof(estado)
    if not _kernel32().GlobalMemoryStatusEx(ctypes.byref(estado)):
        return 0
    return int(estado.ullTotalPhys // (1024 * 1024))


def _ligar_privilegio(nome: str) -> bool:
    """O piso DURO de residencia exige `SeIncreaseWorkingSetPrivilege`.

    O Windows da esse privilegio ao usuario comum, mas o entrega DESLIGADO no
    token — quem nao o liga recebe «acesso negado» sem entender por que, ja
    que nada ali pede administrador.
    """
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                     ctypes.c_void_p]
    adv.LookupPrivilegeValueW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                                          ctypes.c_void_p]
    adv.AdjustTokenPrivileges.argtypes = [ctypes.c_void_p, ctypes.c_bool,
                                          ctypes.c_void_p, ctypes.c_ulong,
                                          ctypes.c_void_p, ctypes.c_void_p]
    k32 = _kernel32()
    token = ctypes.c_void_p()
    if not adv.OpenProcessToken(k32.GetCurrentProcess(),
                                TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
                                ctypes.byref(token)):
        return False
    luid = _LUID()
    if not adv.LookupPrivilegeValueW(None, nome, ctypes.byref(luid)):
        return False
    privilegios = _TOKEN_PRIVILEGES()
    privilegios.PrivilegeCount = 1
    privilegios.Privileges[0].Luid = luid
    privilegios.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
    ctypes.set_last_error(0)
    adv.AdjustTokenPrivileges(token, False, ctypes.byref(privilegios),
                              0, None, None)
    return ctypes.get_last_error() == 0


def situacao() -> dict:
    """COMO O PROCESSO ESTA AGORA — leitura pura, nada e alterado.

    Serve ao diagnostico: e por aqui que se ve, sem adivinhar, se a reserva
    pegou ou se alguem religou a maquina com a tarefa antiga.
    """
    if not E_WINDOWS:
        return {"windows": False}

    k32 = _kernel32()
    eu = k32.GetCurrentProcess()
    quadro: dict = {"windows": True, "pid": int(k32.GetCurrentProcessId()),
                    "ram_da_maquina_mb": _ram_da_maquina_mb()}

    classe = int(k32.GetPriorityClass(eu))
    quadro["classe"] = classe
    quadro["classe_por_extenso"] = NOME_DA_CLASSE.get(classe, str(classe))

    memoria = _MEMORY_PRIORITY_INFORMATION()
    if k32.GetProcessInformation(eu, ProcessMemoryPriority,
                                 ctypes.byref(memoria),
                                 ctypes.sizeof(memoria)):
        quadro["prioridade_da_memoria"] = int(memoria.MemoryPriority)

    # **A VERSAO VAI PREENCHIDA ANTES DA LEITURA.** Sem ela o Windows
    # devolve ERROR_INVALID_PARAMETER e a sonda diz "nao lido" sem motivo
    # aparente — foi o que aconteceu na primeira medicao deste trabalho.
    freio = _PROCESS_POWER_THROTTLING_STATE()
    freio.Version = PROCESS_POWER_THROTTLING_CURRENT_VERSION
    if k32.GetProcessInformation(eu, ProcessPowerThrottling,
                                 ctypes.byref(freio), ctypes.sizeof(freio)):
        quadro["freio_de_eficiencia"] = bool(
            freio.StateMask & PROCESS_POWER_THROTTLING_EXECUTION_SPEED)

    minimo, maximo = ctypes.c_size_t(), ctypes.c_size_t()
    marcas = ctypes.c_ulong()
    if k32.GetProcessWorkingSetSizeEx(eu, ctypes.byref(minimo),
                                      ctypes.byref(maximo),
                                      ctypes.byref(marcas)):
        quadro["piso_mb"] = int(minimo.value // (1024 * 1024))
        quadro["piso_e_duro"] = bool(
            marcas.value & QUOTA_LIMITS_HARDWS_MIN_ENABLE)

    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_ulong]
    contas = _PROCESS_MEMORY_COUNTERS_EX()
    contas.cb = ctypes.sizeof(contas)
    if psapi.GetProcessMemoryInfo(eu, ctypes.byref(contas), contas.cb):
        quadro["residente_mb"] = int(contas.WorkingSetSize // (1024 * 1024))
        quadro["residente_pico_mb"] = int(
            contas.PeakWorkingSetSize // (1024 * 1024))
        quadro["commit_mb"] = int(contas.PrivateUsage // (1024 * 1024))
        quadro["falhas_de_pagina"] = int(contas.PageFaultCount)
    return quadro


def reservar(residente_mb: int = RESIDENTE_GARANTIDO_MB) -> dict:
    """RESERVA A MAQUINA PARA O BALCAO. Devolve o que conseguiu, item a item.

    **NUNCA LEVANTA.** Isto roda no arranque do servidor, e servidor que nao
    sobe porque o Windows negou uma preferencia de desempenho e pior do que
    servidor lento. O que falhar volta escrito em `falhas`, para aparecer no
    log e alguem olhar quando sobrar tempo — e nao no meio do expediente.
    """
    feito: dict = {"aplicado": [], "falhas": []}
    if not E_WINDOWS:
        feito["falhas"].append(
            "a reserva de maquina so existe no Windows; aqui nada foi feito")
        return feito
    try:
        eu = _kernel32().GetCurrentProcess()
    except Exception as erro:  # noqa: BLE001
        feito["falhas"].append(f"nao consegui falar com o Windows: {erro}")
        return feito
    return _reservar_no_processo(eu, residente_mb, feito)


def reservar_processo(pid: int,
                      residente_mb: int = RESIDENTE_GARANTIDO_MB) -> dict:
    """A MESMA RESERVA, NUM SERVIDOR QUE JA ESTA DE PE.

    **ISTO EXISTE PARA NAO DERRUBAR O BALCAO.** A maquina desta casa ja tem a
    tarefa do servidor registrada com a prioridade antiga, e o processo dela
    nasceu rebaixado; esperar o proximo arranque para consertar seria pedir ao
    oficial que fechasse o atendimento no meio do expediente. Quem chama e
    `tools/reservar_a_maquina_do_balcao.ps1`, com privilegio de
    administrador — o servidor roda como SYSTEM, e sem isso o Windows nem
    deixa abrir o processo.

    **E ELA NAO SUBSTITUI A CORRECAO NA TAREFA.** Isto vale ate o proximo
    reinicio; quem conserta para sempre e o `-Priority 3` do instalador e a
    chamada de `app.main`.
    """
    feito: dict = {"aplicado": [], "falhas": [], "pid": int(pid)}
    if not E_WINDOWS:
        feito["falhas"].append(
            "a reserva de maquina so existe no Windows; aqui nada foi feito")
        return feito
    try:
        k32 = _kernel32()
        k32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool,
                                    ctypes.c_ulong]
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        ctypes.set_last_error(0)
        alvo = k32.OpenProcess(
            PROCESS_SET_INFORMATION | PROCESS_SET_QUOTA
            | PROCESS_QUERY_INFORMATION, False, int(pid))
    except Exception as erro:  # noqa: BLE001
        feito["falhas"].append(f"nao consegui falar com o Windows: {erro}")
        return feito
    if not alvo:
        codigo = ctypes.get_last_error()
        feito["falhas"].append(
            f"nao consegui abrir o processo {pid}: o Windows recusou "
            f"(erro {codigo})"
            + ("; o servidor roda como SYSTEM, e isto precisa ser executado "
               "como administrador" if codigo == 5 else ""))
        return feito
    try:
        return _reservar_no_processo(alvo, residente_mb, feito)
    finally:
        k32.CloseHandle(alvo)


def _reservar_no_processo(alvo, residente_mb: int, feito: dict) -> dict:
    """As quatro reservas, sobre um processo ja aberto.

    **UM CORPO SO PARA OS DOIS CHAMADORES, de proposito.** Duas copias — uma
    para o proprio processo e outra para o de fora — divergiriam no primeiro
    conserto, e a que ficasse para tras seria justamente a que o oficial roda
    a mao quando algo esta errado.
    """
    k32 = _kernel32()

    def _erro() -> str:
        codigo = ctypes.get_last_error()
        return f"o Windows recusou (erro {codigo})"

    # 1. A CLASSE. E a que mais pesa: medida em 24/09/2026, ela sozinha leva
    #    o pior atendimento de 10,2 s para 0,23 s com a maquina cheia.
    ctypes.set_last_error(0)
    if k32.SetPriorityClass(alvo, ABOVE_NORMAL_PRIORITY_CLASS):
        feito["aplicado"].append("prioridade de CPU acima do normal")
    else:
        feito["falhas"].append(f"prioridade de CPU: {_erro()}")

    # 2. A PRIORIDADE DA MEMORIA. Sem ela o piso de residencia trabalha
    #    contra a mare: o Windows continua elegendo estas paginas primeiro.
    memoria = _MEMORY_PRIORITY_INFORMATION(MEMORY_PRIORITY_NORMAL)
    ctypes.set_last_error(0)
    if k32.SetProcessInformation(alvo, ProcessMemoryPriority,
                                 ctypes.byref(memoria),
                                 ctypes.sizeof(memoria)):
        feito["aplicado"].append("prioridade de memoria normal")
    else:
        feito["falhas"].append(f"prioridade de memoria: {_erro()}")

    # 3. O FREIO DE EFICIENCIA. `ControlMask` liga o controle e `StateMask`
    #    zerado diz "nao freie" — as duas mascaras juntas sao o desligamento.
    freio = _PROCESS_POWER_THROTTLING_STATE(
        PROCESS_POWER_THROTTLING_CURRENT_VERSION,
        PROCESS_POWER_THROTTLING_EXECUTION_SPEED, 0)
    ctypes.set_last_error(0)
    if k32.SetProcessInformation(alvo, ProcessPowerThrottling,
                                 ctypes.byref(freio), ctypes.sizeof(freio)):
        feito["aplicado"].append("sem freio de eficiencia")
    else:
        feito["falhas"].append(f"freio de eficiencia: {_erro()}")

    # 4. O PISO DE RESIDENCIA — so em maquina que tem de sobra.
    ram = _ram_da_maquina_mb()
    feito["ram_da_maquina_mb"] = ram
    if ram and ram < RAM_MINIMA_DA_MAQUINA_MB:
        feito["falhas"].append(
            f"nao prendi memoria: a maquina tem {ram} MB, e abaixo de "
            f"{RAM_MINIMA_DA_MAQUINA_MB} MB prender {residente_mb} MB tiraria "
            f"do resto o que o resto precisa")
        return feito

    if not _ligar_privilegio("SeIncreaseWorkingSetPrivilege"):
        feito["falhas"].append(
            "nao consegui ligar SeIncreaseWorkingSetPrivilege; o piso de "
            "memoria vai ser tentado assim mesmo")

    piso = residente_mb * 1024 * 1024
    ctypes.set_last_error(0)
    if k32.SetProcessWorkingSetSizeEx(
            alvo, ctypes.c_size_t(piso), ctypes.c_size_t(piso * 4),
            QUOTA_LIMITS_HARDWS_MIN_ENABLE | QUOTA_LIMITS_HARDWS_MAX_DISABLE):
        feito["aplicado"].append(f"{residente_mb} MB residentes garantidos")
        feito["piso_mb"] = residente_mb
    else:
        feito["falhas"].append(f"piso de {residente_mb} MB: {_erro()}")
    return feito


def linha_do_arranque(feito: dict) -> str:
    """UMA LINHA para o console do servidor. Quem le e o oficial, nao o
    programador: diz o que ficou reservado, e o que nao ficou."""
    if feito.get("aplicado"):
        texto = "Reserva de maquina: " + ", ".join(feito["aplicado"]) + "."
    else:
        texto = "Reserva de maquina: nada foi reservado."
    if feito.get("falhas"):
        texto += " NAO CONSEGUI: " + "; ".join(feito["falhas"]) + "."
    return texto


if __name__ == "__main__":
    # `python recursos_da_maquina.py` mostra a situacao; com `--reservar`,
    # reserva e mostra de novo. Serve para conferir no balcao sem abrir tela.
    print("antes :", situacao())
    if "--reservar" in sys.argv:
        quadro = reservar()
        print(linha_do_arranque(quadro))
        print("depois:", situacao())
