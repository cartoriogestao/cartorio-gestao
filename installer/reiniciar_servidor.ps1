<#
  reiniciar_servidor.ps1 - parar e subir o servico, MEDINDO o que aconteceu.

  POR QUE ESTE ARQUIVO EXISTE, e o defeito que ele conserta - 15/09/2026.

  As duas portas de atualizacao (o ATUALIZAR_SISTEMA.cmd e o .cgu da tela)
  paravam o servico assim:

      schtasks /End /TN CartorioGestaoServidor     (no .cmd)
      Stop-Process -Id $ParentPid -Force           (no .cgu)

  E NENHUMA DAS DUAS PARAVA O SERVIDOR DE VERDADE. Medido nesta instalacao
  em 15/09/2026, com a arvore de processos na mao:

      PID 36120  o python que atende a porta 8765   <- vivo, com o codigo velho
      pai 31844  runtime\Scripts\python.exe         <- o lancador do venv
      avo  1244  cmd.exe da tarefa agendada         <- MORTO

  O `runtime` e um venv: o `Scripts\python.exe` dele e um LANCADOR, que cria
  um filho (o interpretador de verdade) e espera. Quem carrega o codigo e
  segura o socket e o FILHO.

  O `schtasks /End` mata o que a tarefa iniciou - o cmd.exe - e deixa os netos
  vivos. O resultado medido foi o pior possivel: o servico continuou no ar com
  a versao antiga, o `/Run` seguinte tentou subir um segundo e nao conseguiu
  (a porta estava ocupada), a tarefa terminou com codigo 1, e as telas do
  balcao seguiram mostrando 3.6.134 enquanto o disco tinha 3.6.135.

  E O PIOR NAO ERA O SERVIDOR ANTIGO: era o AVISO. As duas portas conferiam
  `HTTP 200` no /saude para dizer "atualizado". QUEM RESPONDIA 200 ERA O
  PROCESSO VELHO. O sistema dizia que atualizou, e nao atualizou - o carimbo
  que mente, na versao mais cara dele.

  Agora a parada e por QUEM TEM A PORTA, e a subida so se declara boa quando a
  versao que responde e a versao que esta instalada.

  AS ACOES E O QUE CADA UMA GARANTE:

    Parar      desabilita a tarefa, mata quem tem a porta (e a arvore de quem
               a tem), e ESPERA a porta liberar de verdade. Se nao liberar,
               diz quem ficou e o caminho de cada um.
    Subir      habilita e inicia a tarefa, e espera o /saude responder com a
               versao instalada.
    Reiniciar  as duas, nessa ordem - e nao sobe nada se a porta nao liberar.

  O QUE ESTE SCRIPT NAO MATA, e por que - 15/09/2026.

  Ele e chamado DE DENTRO da rotina que atualiza, e nas duas portas quem tem a
  porta e um ANCESTRAL dele:

      .cmd   cmd.exe do ATUALIZAR_SISTEMA.cmd  ->  eu
      .cgu   servidor (tem a porta) -> aplicar_atualizacao.ps1 -> eu

  O PAI e quem ainda vai copiar os arquivos e me chamar de volta: mata-lo
  abortaria a atualizacao entre a parada e a copia. E um `taskkill /T` em
  QUALQUER ancestral mataria a minha arvore junto - este script incluido, com
  os arquivos pela metade. Por isso o pai e eu nunca morremos, e ancestral se
  mata SOZINHO, sem `/T`.

  CODIGOS DE SAIDA (quem chama decide pelo numero, como manda a casa):

    0  tudo certo
    1  erro inesperado, ou o agendador recusou a tarefa
    2  a porta nao liberou (o servidor antigo continua no ar)
    3  a porta liberou, mas o sistema nao respondeu
    4  respondeu, e a versao que esta no ar NAO e a instalada

  Sem acentos, de proposito: este arquivo roda no console do servidor, que nao
  e UTF-8, e as duas portas ja seguem essa convencao.
#>
param(
  [ValidateSet('Parar','Subir','Reiniciar')][string]$Acao = 'Reiniciar',
  [string]$InstallDir = 'C:\Program Files\CartorioGestao',
  [string]$DataDir = '',
  [string]$TaskName = 'CartorioGestaoServidor',
  [int]$Port = 8765,
  [int]$ParentPid = 0,
  [string]$VersaoEsperada = '',
  [int]$EsperaSegundos = 180,
  [int]$EsperaParaLiberar = 30
)

$ErrorActionPreference = 'Continue'
if ([string]::IsNullOrWhiteSpace($DataDir)) { $DataDir = Join-Path $env:PROGRAMDATA 'CartorioGestao' }

#   O RASTRO VAI PARA ARQUIVO PROPRIO, e nao so para a tela. Na atualizacao
#   pelo .cgu nao existe tela nenhuma: se o reinicio nao deixasse rastro, a
#   pergunta "por que o sistema ficou na versao antiga?" nao teria onde ser
#   respondida depois que a janela fechasse.
$logDir = Join-Path $DataDir 'logs'
if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$logPath = Join-Path $logDir 'reinicio_do_servidor.log'

function Dizer([string]$texto) {
  $linha = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $texto"
  try { Add-Content -LiteralPath $logPath -Value $linha -Encoding UTF8 } catch {}
  Write-Host $texto
}

function VersaoDaInstalacao {
  #   A VERSAO E A DO DISCO, e nao a de uma constante escrita aqui: quem copia
  #   os arquivos carimba o VERSAO.txt, e e ele que diz o que acabou de chegar.
  $v = ''
  $arquivo = Join-Path $InstallDir 'VERSAO.txt'
  if (Test-Path -LiteralPath $arquivo) { $v = [string](Get-Content -LiteralPath $arquivo -Raw) }
  if ([string]::IsNullOrWhiteSpace($v)) {
    $app = Join-Path $InstallDir 'app.py'
    if (Test-Path -LiteralPath $app) {
      $m = [regex]::Match([string](Get-Content -LiteralPath $app -Raw), '(?m)^VERSION\s*=\s*"([^"]+)"')
      if ($m.Success) { $v = $m.Groups[1].Value }
    }
  }
  return $v.Trim()
}

function PidsNaPorta {
  #   A PORTA SE LE POR DUAS FONTES SOMADAS, E NAO POR UMA COM PLANO B — corrigido
  #   em 15/09/2026, no proprio dia em que este arquivo nasceu.
  #
  #     O `Get-NetTCPConnection` NAO ESTOURA numa sessao sem elevacao: devolve
  #     LISTA VAZIA. Sem excecao, o `catch` nunca rodava, o netstat nunca era
  #     consultado, e a funcao respondia "porta livre" com o servidor antigo
  #     VIVO no ar. Medido na mao, minutos depois do primeiro reinicio que deu
  #     certo: o `netstat` mostrava `LISTENING 19380` e a funcao dizia zero.
  #
  #     E ESTE E O LADO PERIGOSO DO ENGANO. Porta declarada livre nao gera aviso:
  #     ela deixa a copia comecar EM CIMA do servidor vivo — que e exatamente o
  #     defeito que este arquivo existe para impedir. **Zero medido e zero por
  #     engano sao a mesma tela e coisas diferentes**, regra desta casa, quebrada
  #     aqui por mim na mesma tarde.
  #
  #     Agora as duas fontes SOMAM: o modulo, quando responde, e o netstat, que
  #     responde sempre. A coluna do PID no netstat e a ultima da linha.
  $achados = @()
  try {
    $achados += @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
                  Select-Object -ExpandProperty OwningProcess)
  } catch {}
  try {
    foreach ($l in @(& netstat.exe -ano 2>$null)) {
      $t = @(($l -split '\s+') | Where-Object { $_ -ne '' })
      if ($t.Count -ge 5 -and $t[1] -match ":$Port$" -and $t[3] -eq 'LISTENING') { $achados += [int]$t[4] }
    }
  } catch {}
  return @($achados | Where-Object { $_ -and [int]$_ -gt 0 } | Select-Object -Unique)
}

function Arvore([int]$raiz, [int]$profundidade = 4) {
  $todos = @()
  $fila = @($raiz)
  $nivel = 0
  while ($fila.Count -gt 0 -and $nivel -lt $profundidade) {
    $filhos = @()
    foreach ($p in $fila) {
      try {
        $filhos += @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$p" -ErrorAction Stop |
                     Select-Object -ExpandProperty ProcessId)
      } catch {}
    }
    $filhos = @($filhos | Where-Object { $_ } | Select-Object -Unique)
    $todos += $filhos
    $fila = $filhos
    $nivel++
  }
  return @($todos)
}

function Pai([int]$alvo) {
  try { return [int](Get-CimInstance Win32_Process -Filter "ProcessId=$alvo" -ErrorAction Stop).ParentProcessId } catch { return 0 }
}

function Vivo([int]$alvo) {
  try { $null = Get-Process -Id $alvo -ErrorAction Stop; return $true } catch { return $false }
}

function Matar([int]$alvo) {
  #   NAO SE MATA A SI MESMO: este script costuma ser chamado de dentro de um
  #   dos processos que ele para.
  if ($alvo -le 0) { return $true }
  if ($alvo -eq $PID) { Dizer "  (o PID $alvo sou eu; nao paro)"; return $true }
  if ($NuncaMatar -contains $alvo) { Dizer "  (o PID $alvo e a rotina que me chamou; nao paro)"; return $true }

  #   A MORTE E CONFERIDA, E NAO SUPOSTA — corrigido no mesmo dia em que este
  #   arquivo nasceu. A primeira versao dizia "parei o PID" logo depois do
  #   `taskkill`, sem olhar o codigo de saida e sem ver se o processo sumiu.
  #   Medido minutos depois: o processo estava VIVO e a mensagem que tinha sido
  #   engolida era "Acesso negado". **`rowcount` e resposta; "deu certo" e
  #   suposicao** — regra desta casa, quebrada aqui por mim na primeira versao.
  $motivo = ''
  try { Stop-Process -Id $alvo -Force -ErrorAction Stop } catch { $motivo = $_.Exception.Message }
  if (-not (Vivo $alvo)) { Dizer "  parei o PID $alvo"; return $true }

  #   O `/T` MATA A ARVORE, E A MINHA E DESCENDENTE DE ALGUNS DESTES — 15/09/2026.
  #     Nas duas portas de atualizacao quem tem a porta e ANCESTRAL deste script:
  #     no .cgu, o servidor antigo e o avo (ele lancou o aplicar_atualizacao.ps1, que
  #     me lancou); no .cmd, a corrente e a mesma pela tarefa agendada. Um `/T` num
  #     ancestral mataria a arvore inteira — este script, o aplicador e a atualizacao
  #     no meio do caminho, deixando os arquivos trocados pela metade. Ancestral se
  #     mata SOZINHO, que e o que basta para soltar a porta.
  $comArvore = -not ($MeusAncestrais -contains $alvo)
  $argumentos = @('/F', '/PID', "$alvo")
  if ($comArvore) { $argumentos += '/T' }
  $saida = (@(& taskkill.exe @argumentos 2>&1) -join ' ').Trim()
  if (-not (Vivo $alvo)) { Dizer "  parei o PID $alvo (por taskkill)"; return $true }

  if ([string]::IsNullOrWhiteSpace($saida)) { $saida = $motivo }
  Dizer "  NAO consegui parar o PID $alvo : $saida"
  return $false
}

#   QUEM NAO PODE MORRER, E QUEM NAO PODE LEVAR JUNTO — 15/09/2026.
#     Este script e chamado DE DENTRO da rotina que atualiza, e isso muda o que se
#     pode matar:
#
#       .cmd   cmd.exe do ATUALIZAR_SISTEMA.cmd  ->  eu
#       .cgu   servidor (tem a porta) -> aplicar_atualizacao.ps1 -> eu
#
#     O PAI e quem ainda vai copiar os arquivos e me chamar de volta: mata-lo
#     abortaria a atualizacao entre a parada e a copia — a pior ordem possivel,
#     porque o sistema ficaria parado sem que ninguem trocasse nada.
#     E QUALQUER ANCESTRAL, morto com `/T`, leva a minha arvore junto.
$MeusAncestrais = @()
$subindo = Pai $PID
while ($subindo -gt 0 -and $MeusAncestrais.Count -lt 8) {
  $MeusAncestrais += [int]$subindo
  $subindo = Pai $subindo
}
$NuncaMatar = @([int]$PID)
if ($MeusAncestrais.Count -gt 0) { $NuncaMatar += [int]$MeusAncestrais[0] }

function Parar {
  Dizer "Parando o servico do Cartorio Gestao..."
  #   A TAREFA PRIMEIRO, DESABILITADA: com ela habilitada e sem processo, o
  #   proprio Windows pode subir o servico no meio da copia dos arquivos.
  try { & schtasks.exe /Change /TN $TaskName /DISABLE 2>$null | Out-Null } catch {}
  try { & schtasks.exe /End /TN $TaskName 2>$null | Out-Null } catch {}
  Start-Sleep -Milliseconds 500

  #   AGORA O QUE O AGENDADOR NAO ALCANCA: quem tem a porta. O `schtasks /End`
  #   para o cmd.exe da tarefa e deixa os netos vivos - medido em 15/09/2026.
  $alvos = @()
  $naPorta = PidsNaPorta
  $alvos += $naPorta
  foreach ($p in $naPorta) {
    #   A ARVORE DE QUEM TEM A PORTA, para cima e para baixo: o lancador do venv
    #   fica vivo quando o filho morre, e o filho fica vivo quando o cmd morre.
    $pai = Pai $p
    if ($pai -gt 0) { $alvos += $pai; $alvos += Arvore $pai }
    $alvos += Arvore $p
  }
  if ($ParentPid -gt 0) { $alvos += [int]$ParentPid; $alvos += Arvore $ParentPid }
  $alvos = @($alvos | Where-Object { $_ -and [int]$_ -gt 0 } | Select-Object -Unique)
  $naoPararam = @()
  foreach ($p in $alvos) { if (-not (Matar ([int]$p))) { $naoPararam += [int]$p } }

  #   A ESPERA E MEDIDA, E NAO UM `timeout /t 3` QUE TORCE. E o numero que
  #   importa: a porta tem de estar livre ANTES de a copia comecar, porque o
  #   defeito de hoje foi exatamente um processo velho segurando o socket.
  for ($i = 0; $i -lt $EsperaParaLiberar; $i++) {
    $restam = PidsNaPorta
    if ($restam.Count -eq 0) { Dizer "Porta $Port livre."; return 0 }
    Start-Sleep -Seconds 1
  }
  $restam = PidsNaPorta
  Dizer "A porta $Port continua ocupada. Quem a esta segurando:"
  foreach ($p in $restam) {
    #   A LINHA TEM DE SERVIR PARA ALGUEM IR ACHAR O PROCESSO. `CommandLine`
    #   volta VAZIO para processo de outra elevacao - medido no primeiro ensaio,
    #   onde saiu so "PID 36120 : python.exe" e mais nada. O caminho do executavel
    #   vem pelo Get-Process, que nao depende disso, e e ele que diz de que
    #   instalacao e o processo.
    $nome = '?'; $cmd = ''
    try { $q = Get-CimInstance Win32_Process -Filter "ProcessId=$p" -ErrorAction Stop; $nome = $q.Name; $cmd = [string]$q.CommandLine } catch {}
    if ([string]::IsNullOrWhiteSpace($cmd)) {
      try { $cmd = [string](Get-Process -Id $p -ErrorAction Stop).Path } catch {}
    }
    Dizer "  PID $p : $nome`n      $cmd"
  }
  #   A PISTA QUE FALTAVA - 15/09/2026. Numa sessao SEM ELEVACAO o `taskkill`
  #   responde "Acesso negado" e o processo fica: quem le a lista acima ve um
  #   python vivo e conclui que o sistema esta travado, quando o que faltou foi
  #   permissao para mata-lo. Isto aparece aqui porque foi exatamente o que
  #   aconteceu no primeiro ensaio deste script.
  if ($naoPararam.Count -gt 0) {
    Dizer "Nao consegui parar: $($naoPararam -join ', '). Se a mensagem acima falou em Acesso negado,"
    Dizer "esta sessao nao esta elevada - execute como administrador (o ATUALIZAR_SISTEMA.cmd ja pede)."
  }
  return 2
}

function Subir {
  $esperada = $VersaoEsperada
  if ([string]::IsNullOrWhiteSpace($esperada)) { $esperada = VersaoDaInstalacao }
  Dizer "Subindo o servico do Cartorio Gestao (versao instalada: $esperada)..."

  try { & schtasks.exe /Change /TN $TaskName /ENABLE 2>$null | Out-Null } catch {}
  $saida = & schtasks.exe /Run /TN $TaskName 2>&1
  $codigo = $LASTEXITCODE
  if ($codigo -ne 0) {
    Dizer "O agendador nao conseguiu iniciar a tarefa $TaskName : $($saida -join ' ')"
    return 1
  }

  #   AQUI ESTA O CONSERTO DO CARIMBO QUE MENTE: nao basta responder 200.
  #   Quem pode estar respondendo 200 e o processo velho, e era isso que fazia
  #   as duas portas dizerem "atualizado" com o codigo antigo no ar.
  $respondeu = $false
  $noAr = ''
  #   A ESPERA E EM SEGUNDOS, E CUMPRE O QUE O NOME DELA PROMETE — corrigido em
  #   15/09/2026, no mesmo dia. Aqui havia `for ($i = 0; $i -lt $EsperaSegundos;
  #   $i++)`, que conta ITERACOES e nao segundos: cada volta leva `Start-Sleep 1`
  #   MAIS o tempo da tentativa de conexao. Quando o servico ainda nao subiu a
  #   conexao e recusada depressa (~1 s por volta); quando ele esta subindo e nao
  #   aceita ainda, quem responde e o prazo do `-TimeoutSec 2`. O mesmo numero
  #   valia 60 s ou 180 s conforme o humor da maquina.
  #
  #     E o engano cai para o lado ruim: numa maquina rapida em recusar, a espera
  #     acabaria ANTES de o servico ficar pronto, e a atualizacao diria "nao
  #     respondeu" com o servidor subindo — o carimbo que mente ao contrario.
  #     Medido nesta instalacao: da criacao do processo ate o `/saude` responder
  #     com a versao certa foram cerca de **90 segundos** (21:00:28 -> 21:02:00),
  #     que e o tempo de o waitress carregar a aplicacao inteira. E por isso o
  #     padrao e 180: o dobro do medido, e nao um numero escrito a olho.
  $limite = (Get-Date).AddSeconds($EsperaSegundos)
  while ((Get-Date) -lt $limite) {
    Start-Sleep -Seconds 1
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/saude" -TimeoutSec 2
      if ($r.StatusCode -eq 200) {
        $respondeu = $true
        try { $noAr = [string](($r.Content | ConvertFrom-Json).version) } catch {}
        if ([string]::IsNullOrWhiteSpace($esperada)) { break }
        if ($noAr -eq $esperada) { break }
      }
    } catch {}
  }

  if (-not $respondeu) {
    Dizer "A porta $Port liberou, mas o sistema nao respondeu em $EsperaSegundos segundos."
    Dizer "Confira o log do servidor: $(Join-Path $logDir 'servidor.log')"
    return 3
  }
  if (-not [string]::IsNullOrWhiteSpace($esperada) -and $noAr -ne $esperada) {
    Dizer "ATENCAO: quem respondeu esta na versao $noAr, e a instalada e $esperada."
    Dizer "Isso quer dizer que o servidor antigo continuou no ar. O codigo novo esta em disco"
    Dizer "e entra no proximo reinicio - pare o servidor por inteiro antes."
    return 4
  }
  Dizer "No ar: versao $noAr."
  return 0
}

$final = 1
try {
  if ($Acao -eq 'Parar') {
    $final = Parar
  } elseif ($Acao -eq 'Subir') {
    $final = Subir
  } else {
    $parada = Parar
    if ($parada -ne 0) { $final = $parada } else { $final = Subir }
  }
} catch {
  Dizer "ERRO inesperado: $($_.Exception.Message)"
  $final = 1
}

switch ($final) {
  0 { Dizer "RESULTADO: OK" }
  2 { Dizer "RESULTADO: A PORTA NAO LIBEROU (o servidor antigo continua no ar)" }
  3 { Dizer "RESULTADO: O SISTEMA NAO RESPONDEU" }
  4 { Dizer "RESULTADO: A VERSAO NO AR NAO E A INSTALADA" }
  default { Dizer "RESULTADO: ERRO" }
}
exit ([int]$final)
