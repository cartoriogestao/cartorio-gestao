# -*- coding: utf-8 -*-
#
# RESERVA A MAQUINA PARA O BALCAO — nesta maquina, agora, sem derrubar nada.
#
# POR QUE ISTO EXISTE
#
#     Medido em 24/09/2026: o servidor desta casa rodava em prioridade ABAIXO
#     DO NORMAL, de CPU e de memoria, e ninguem tinha escolhido isso — e o
#     padrao do Agendador de Tarefas do Windows, herdado pela tarefa, pelo
#     cmd, pelo python e pelas doze linhas do waitress.
#
#     Com a maquina ocupada, o pior atendimento passava de DEZ SEGUNDOS; com a
#     prioridade certa, 0,23 s. Ver `recursos_da_maquina.py` para a medicao.
#
# ELE FAZ DUAS COISAS, E AS DUAS PRECISAM SER FEITAS
#
#     1. CONSERTA A TAREFA (`-Priority 3`), que vale do proximo reinicio em
#        diante. Sozinha, ela nao ajuda hoje.
#     2. RESERVA O PROCESSO QUE JA ESTA DE PE, que vale ate o proximo
#        reinicio. Sozinha, ela se perde quando a maquina religa.
#
#     Uma sem a outra deixa um buraco, e o buraco nao avisa: o balcao volta a
#     ficar lento num dia qualquer, sem ninguem ligar uma coisa a outra.
#
# ELE PRECISA DE ADMINISTRADOR, e a razao e medida: o servidor roda como
# SYSTEM, e sem privilegio o Windows recusa ate ABRIR o processo (erro 5).
#
# ELE NAO REINICIA O SERVIDOR, NAO PARA A TAREFA E NAO TOCA EM BANCO NENHUM.
# Rodar no meio do expediente e seguro — foi para isso que ele foi escrito.
#
#     powershell -ExecutionPolicy Bypass -File reservar_a_maquina_do_balcao.ps1
#
# Com `-Conferir` ele so MEDE e nao altera nada.

[CmdletBinding()]
param(
    [string]$Tarefa = "CartorioGestaoServidor",
    [switch]$Conferir
)

$ErrorActionPreference = "Continue"
$AQUI = Split-Path -Parent $MyInvocation.MyCommand.Path
$SISTEMA = Split-Path -Parent $AQUI
$PYTHON = Join-Path $env:ProgramData "CartorioGestao\runtime\Scripts\python.exe"

function Sou-Administrador {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# QUEM E O SERVIDOR: nao se adivinha pelo nome do processo — ha varios python
# nesta maquina. Quem responde e QUEM ESCUTA A PORTA do sistema.
function Pid-Do-Servidor([int]$Porta) {
    $linha = Get-NetTCPConnection -State Listen -LocalPort $Porta -ErrorAction SilentlyContinue |
             Select-Object -First 1
    if ($null -eq $linha) { return 0 }
    return [int]$linha.OwningProcess
}

function Porta-Do-Sistema {
    # A porta mora no banco (`settings.network_port`), e ler o banco daqui
    # seria abrir o banco do balcao por fora. 8765 e o padrao da instalacao;
    # quem mudou a porta passa `-Porta`.
    return 8765
}

"=== RESERVA DA MAQUINA DO BALCAO ==="
""

$porta = Porta-Do-Sistema
$pidServidor = Pid-Do-Servidor $porta
if ($pidServidor -eq 0) {
    "  O servidor nao esta escutando a porta $porta."
    "  Nada foi reservado no processo; a tarefa ainda pode ser corrigida."
} else {
    "  Servidor na porta $porta = processo $pidServidor"
}
""

# ---------------------------------------------------------- 1. a SITUACAO
if (Test-Path $PYTHON) {
    "--- como esta agora ---"
    if ($pidServidor -ne 0) {
        try {
            $c = (Get-Process -Id $pidServidor -ErrorAction Stop).PriorityClass
            "  prioridade de CPU do servidor : $c"
        } catch {
            "  prioridade de CPU do servidor : sem acesso (rode como administrador)"
        }
    }
    & $PYTHON (Join-Path $SISTEMA "recursos_da_maquina.py")
} else {
    "  AVISO: nao achei o Python do servidor em $PYTHON"
}
""

if ($Conferir) {
    "Modo -Conferir: nada foi alterado."
    return
}

if (-not (Sou-Administrador)) {
    "PRECISA DE ADMINISTRADOR."
    "  O servidor roda como SYSTEM, e sem privilegio o Windows recusa ate abrir"
    "  o processo dele. Abra o PowerShell com 'Executar como administrador' e"
    "  rode este mesmo arquivo de novo. NADA FOI ALTERADO."
    return
}

# ------------------------------------------------- 2. a TAREFA (do proximo
#    reinicio em diante). Priority 3 = AboveNormal, MEDIDO em 24/09/2026.
"--- a tarefa de inicializacao ---"
try {
    $t = Get-ScheduledTask -TaskName $Tarefa -ErrorAction Stop
    $antes = $t.Settings.Priority
    if ($antes -eq 3) {
        "  ja estava em Priority 3 (acima do normal); nada a fazer"
    } else {
        $t.Settings.Priority = 3
        Set-ScheduledTask -InputObject $t -ErrorAction Stop | Out-Null
        $depois = (Get-ScheduledTask -TaskName $Tarefa).Settings.Priority
        "  Priority $antes -> $depois   (3 = acima do normal)"
        if ($depois -ne 3) { "  ATENCAO: a mudanca NAO pegou." }
    }
} catch {
    "  NAO CONSEGUI mexer na tarefa '$Tarefa': " + $_.Exception.Message
    "  (se o nome da tarefa for outro nesta maquina, passe -Tarefa <nome>)"
}
""

# ---------------------------------- 3. o PROCESSO QUE JA ESTA DE PE (vale ate
#    o proximo reinicio). E a metade que conserta o expediente de HOJE.
"--- o servidor que ja esta rodando ---"
if ($pidServidor -eq 0) {
    "  nao ha processo para reservar"
} elseif (-not (Test-Path $PYTHON)) {
    "  nao achei o Python do servidor; o processo ficou como estava"
} else {
    $codigo = "import sys; sys.path.insert(0, r'$SISTEMA'); " +
              "import recursos_da_maquina as R; " +
              "q = R.reservar_processo($pidServidor); " +
              "print(R.linha_do_arranque(q))"
    & $PYTHON -c $codigo
}
""

"--- como ficou ---"
if ($pidServidor -ne 0) {
    try {
        $c = (Get-Process -Id $pidServidor -ErrorAction Stop).PriorityClass
        "  prioridade de CPU do servidor : $c"
    } catch {
        "  prioridade de CPU do servidor : nao consegui ler"
    }
}
""
"Pronto. O servidor NAO foi reiniciado e nenhum atendimento foi interrompido."
"A tarefa vale do proximo reinicio; a reserva do processo vale ate ele."
