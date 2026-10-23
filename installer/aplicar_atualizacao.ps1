param(
  [Parameter(Mandatory=$true)][string]$InstallDir,
  [Parameter(Mandatory=$true)][string]$StageDir,
  [Parameter(Mandatory=$true)][string]$DataDir,
  [Parameter(Mandatory=$true)][string]$TaskName,
  [Parameter(Mandatory=$true)][int]$ParentPid,
  [int]$Port=8765
)
$ErrorActionPreference='Stop'
$updates=Join-Path $DataDir 'updates'
$log=Join-Path $updates 'update.log'
$result=Join-Path $updates 'last_result.json'
New-Item -ItemType Directory -Force -Path $updates | Out-Null
function Log($t){ Add-Content -Path $log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $t" -Encoding UTF8 }
function WriteUtf8($path,$content){
  [IO.File]::WriteAllText($path,[string]$content,(New-Object Text.UTF8Encoding($false)))
}
function Result($status,$message,$version=''){
  WriteUtf8 $result (@{status=$status;message=$message;version=$version;at=(Get-Date).ToString('s')} | ConvertTo-Json)
}
function SafeTarget($root,$relative){
  $rel=[string]$relative
  if([string]::IsNullOrWhiteSpace($rel) -or [IO.Path]::IsPathRooted($rel) -or $rel.Contains(':')){
    throw "Caminho inseguro no pacote: $rel"
  }
  $rootFull=[IO.Path]::GetFullPath($root).TrimEnd('\') + '\'
  $targetFull=[IO.Path]::GetFullPath((Join-Path $root $rel))
  if(-not $targetFull.StartsWith($rootFull,[StringComparison]::OrdinalIgnoreCase)){
    throw "Caminho tentou sair da pasta autorizada: $rel"
  }
  return $targetFull
}
function Rodar([string]$descricao,[string]$exe,[string[]]$argumentos){
  #   PROGRAMA DE FORA QUE ESCREVE NO ERRO NAO DERRUBA O SCRIPT — e isso foi medido.
  #     Com `$ErrorActionPreference='Stop'`, o stderr do `robocopy` vira excecao, e a
  #     mensagem que chega ao `last_result.json` e o texto cru dele: o log desta casa
  #     tem «ERRO: Acesso negado.» e nada mais — treze caracteres sem dizer qual pasta,
  #     qual copia, nem o que fazer. O que interessa nao e o que ele gritou: e o CODIGO
  #     DE SAIDA, que e quem decide se a copia deu certo. Aqui se le o codigo, se
  #     escreve a frase no log, e quem chama decide pelo numero.
  $anterior=$ErrorActionPreference
  $ErrorActionPreference='Continue'
  try { & $exe @argumentos 2>&1 | Out-Null } finally { $ErrorActionPreference=$anterior }
  $codigo=$LASTEXITCODE
  Log "$descricao (codigo $codigo)"
  return $codigo
}
function ReiniciarServico([string]$acao,[string]$versaoEsperada=''){
  #   UMA ROTINA SO PARA PARAR E SUBIR O SERVICO, E AS DUAS PORTAS DE ATUALIZACAO
  #   A USAM — 15/09/2026.
  #     Medido nesta instalacao: as duas portas paravam o servico de um jeito que NAO
  #     PARAVA. O `schtasks /End` do .cmd mata o cmd.exe da tarefa e deixa os netos
  #     vivos; e o `Stop-Process -Id $ParentPid` que estava aqui matava SO o lancador
  #     do venv, que nao e quem tem o socket — quem atende a porta e o filho dele.
  #     O resultado medido foi o pior possivel: o servico velho continuou no ar, a
  #     tarefa terminou com erro, e o `/saude` respondeu 200 com a versao ANTIGA. As
  #     duas portas diziam "atualizado" sem ter atualizado: o carimbo que mente, na
  #     versao mais cara dele.
  #     Quem sabe parar de verdade e quem sabe dizer em que versao esta: por isso a
  #     parada e a subida passaram a ser uma rotina so, em
  #     installer\reiniciar_servidor.ps1, e esta funcao so a chama e devolve o codigo.
  #   O COMPONENTE VEM DO PROPRIO PACOTE quando a instalacao ainda nao o tem — e o
  #   caso desta primeira vez, em que ele viaja. Depois, o da instalacao manda.
  $componente=Join-Path $InstallDir 'installer\reiniciar_servidor.ps1'
  if(-not (Test-Path -LiteralPath $componente)){
    $doPacote=Join-Path (Join-Path $StageDir 'payload') 'installer\reiniciar_servidor.ps1'
    if(Test-Path -LiteralPath $doPacote){ $componente=$doPacote }
  }
  if(-not (Test-Path -LiteralPath $componente)){
    throw "Nao encontrei o componente que para e sobe o servico (installer\reiniciar_servidor.ps1). NADA FOI ALTERADO."
  }
  $argumentos=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$componente+'"'),'-Acao',$acao,
                '-InstallDir',('"'+$InstallDir+'"'),'-DataDir',('"'+$DataDir+'"'),'-TaskName',$TaskName,'-Port',"$Port")
  if($ParentPid -gt 0){ $argumentos+=@('-ParentPid',"$ParentPid") }
  if(-not [string]::IsNullOrWhiteSpace($versaoEsperada)){ $argumentos+=@('-VersaoEsperada',('"'+$versaoEsperada+'"')) }
  $saidaTxt=Join-Path $updates ("reinicio_" + $acao.ToLower() + ".out.txt")
  $saidaErr=Join-Path $updates ("reinicio_" + $acao.ToLower() + ".err.txt")
  Remove-Item -LiteralPath $saidaTxt,$saidaErr -Force -ErrorAction SilentlyContinue
  $p=Start-Process -FilePath 'powershell.exe' -ArgumentList $argumentos -Wait -PassThru -NoNewWindow `
       -RedirectStandardOutput $saidaTxt -RedirectStandardError $saidaErr
  #   A SAIDA DO COMPONENTE ENTRA NO LOG DA ATUALIZACAO: quem for ler depois encontra
  #   UMA fita, e nao dois rastros soltos em pastas diferentes.
  foreach($linha in @(Get-Content -LiteralPath $saidaTxt -ErrorAction SilentlyContinue)){ Log "  [reinicio] $linha" }
  foreach($linha in @(Get-Content -LiteralPath $saidaErr -ErrorAction SilentlyContinue)){ Log "  [reinicio-erro] $linha" }
  Remove-Item -LiteralPath $saidaTxt,$saidaErr -Force -ErrorAction SilentlyContinue
  $codigoDele=[int]$p.ExitCode
  Log "Reinicio do servico: acao=$acao codigo=$codigoDele"
  return $codigoDele
}
$metaPath=Join-Path $StageDir '_update_meta.json'
$meta=$null
$version=''
$rollback=$null
$installChanged=$false
function MetaState($state,$message=''){
  if($null -eq $script:meta){return}
  $script:meta | Add-Member -NotePropertyName state -NotePropertyValue $state -Force
  $script:meta | Add-Member -NotePropertyName state_at -NotePropertyValue (Get-Date).ToString('s') -Force
  if(-not [string]::IsNullOrWhiteSpace($message)){
    $script:meta | Add-Member -NotePropertyName state_message -NotePropertyValue $message -Force
  }
  WriteUtf8 $script:metaPath ($script:meta | ConvertTo-Json -Depth 12)
}
try {
  $meta=Get-Content $metaPath -Raw | ConvertFrom-Json
  $version=[string]$meta.manifest.version
  if([string]$meta.state -ne 'APPROVED'){
    throw 'A atualizacao nao possui aprovacao final registrada.'
  }
  if([string]::IsNullOrWhiteSpace([string]$meta.approved_by)){
    throw 'A aprovacao nao identifica o administrador responsavel.'
  }
  if(-not (Test-Path -LiteralPath ([string]$meta.backup) -PathType Leaf)){
    throw 'O backup previo obrigatorio nao foi localizado.'
  }
  $packagePath=[string]$meta.package_path
  if(-not (Test-Path -LiteralPath $packagePath -PathType Leaf)){
    throw 'O pacote original nao foi localizado para a conferencia final.'
  }
  if((Get-FileHash -LiteralPath $packagePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne [string]$meta.package_sha256){
    throw 'O pacote original mudou depois da aprovacao.'
  }
  $payload=Join-Path $StageDir 'payload'
  $declarados=@{}
  foreach($item in $meta.checked_files){
    $source=SafeTarget $payload ([string]$item.path)
    if(-not (Test-Path -LiteralPath $source -PathType Leaf)){
      throw "Arquivo preparado ausente: $($item.path)"
    }
    if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne [string]$item.sha256){
      throw "Arquivo preparado alterado depois da aprovacao: $($item.path)"
    }
    $declarados[$source.ToLowerInvariant()]=$true
  }
  #   NADA ENTRA QUE O MANIFESTO NAO DECLARE (revisao de seguranca de 22/10/2026, C1).
  #     O robocopy /E copia a pasta preparada INTEIRA, e a conferencia de cima so olha
  #     os arquivos listados: um `.pth` ou um `.py` plantado na preparacao iria para a
  #     instalacao sem ter passado por hash nenhum. Arquivo a mais e recusa, com o
  #     servico ainda no ar — NADA FOI ALTERADO.
  foreach($f in (Get-ChildItem -LiteralPath $payload -File -Recurse -Force)){
    if(-not $declarados.ContainsKey($f.FullName.ToLowerInvariant())){
      throw "A preparacao contem arquivo que o manifesto nao declara: $($f.FullName). NADA FOI ALTERADO."
    }
  }

  #   A PERGUNTA QUE DECIDE SE O BALCAO CAI, E ELA VEM ANTES DE TUDO QUE MEXE.
  #     Medido em 15/09/2026: o `robocopy` era o primeiro a falhar, e falhava DEPOIS de
  #     o servico ter sido parado — o balcao caia para descobrir que nao dava. A prova
  #     e a unica que nao mente: criar um arquivo e apagar. Nao se pergunta ao sistema
  #     de arquivos o que ele acha; escreve-se.
  $pista=Join-Path $InstallDir ('.teste_de_escrita_' + [Guid]::NewGuid().ToString('N') + '.tmp')
  $podeEscrever=$true
  try { [IO.File]::WriteAllText($pista,'teste') } catch { $podeEscrever=$false }
  if($podeEscrever){ Remove-Item -LiteralPath $pista -Force -ErrorAction SilentlyContinue }
  if(-not $podeEscrever){
    throw ("Esta conta nao pode gravar em $InstallDir, que e onde o programa esta instalado. A atualizacao automatica precisa ser aplicada por quem tem permissao nessa pasta — use o ATUALIZAR_SISTEMA.cmd, que pede a permissao ao Windows, ou aplique pelo sistema do servidor, que roda como servico. NADA FOI ALTERADO e o sistema continua no ar.")
  }

  MetaState 'APPLYING'
  Log "Aplicando atualizacao para $version."
  $rollback=Join-Path $updates ("rollback\" + (Get-Date -Format 'yyyyMMdd_HHmmss') + "_v$version")
  New-Item -ItemType Directory -Force -Path $rollback | Out-Null
  $codigo=Rodar "Copia de seguranca para rollback" 'robocopy.exe' @($InstallDir,$rollback,'/E','/R:1','/W:1','/NFL','/NDL','/NJH','/NJS','/NP')
  if ($codigo -ge 8) { throw "Falha ao criar copia de rollback ($codigo)." }

  #   PARAR E MEDIDO, E ANTES DE COPIAR QUALQUER ARQUIVO — 15/09/2026.
  #     Se o servidor antigo nao sai do ar, copiar por baixo dele deixa as telas do
  #     balcao mostrando a versao velha ENQUANTO o disco ja tem a nova — e a pior
  #     parte disso e que a atualizacao se declararia concluida. Parar aqui, com o
  #     servico no ar e dizendo NADA FOI ALTERADO, deixa a casa num estado que se
  #     explica sozinho.
  $parada=ReiniciarServico 'Parar'
  if($parada -ne 0){
    throw ("Nao consegui parar o servidor que esta no ar (codigo $parada). NADA FOI ALTERADO. Copiar a versao nova por baixo de um servidor velho faria as telas mostrarem a versao antiga se dizendo atualizadas. O log de quem tentou parar esta em $DataDir\logs\reinicio_do_servidor.log")
  }

  $installChanged=$true
  $codigo=Rodar "Copia da nova versao para a instalacao" 'robocopy.exe' @($payload,$InstallDir,'/E','/R:2','/W:1','/NFL','/NDL','/NJH','/NJS','/NP')
  if ($codigo -ge 8) { throw "Falha ao copiar a nova versao ($codigo)." }
  foreach($rel in $meta.delete){
    $target=SafeTarget $InstallDir ([string]$rel)
    if(Test-Path -LiteralPath $target){ Remove-Item -LiteralPath $target -Recurse -Force }
  }
  Get-ChildItem $InstallDir -Filter '__pycache__' -Directory -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

  if($meta.manifest.run_pip -eq $true){
    $runtimePython=Join-Path $DataDir 'runtime\Scripts\python.exe'
    if(-not (Test-Path $runtimePython)){throw 'Runtime Python da instalacao nao foi encontrado.'}
    Log 'Atualizacao solicita sincronizacao de dependencias Python.'
    $codigo=Rodar "pip install -r requirements.txt" $runtimePython @('-m','pip','install','-r',(Join-Path $InstallDir 'requirements.txt'))
    if($codigo -ne 0){throw 'Falha ao instalar dependencias exigidas pela atualizacao.'}
  }

  #   A SUBIDA CONFERE A VERSAO QUE RESPONDE, E NAO SO O `HTTP 200` — 15/09/2026.
  #     Era aqui que as duas portas mentiam: quem respondia 200 podia ser o processo
  #     VELHO, que nunca morreu, e o sistema carimbava "atualizado" sobre o codigo
  #     antigo. Agora o componente compara a versao que esta no ar com a que esta
  #     instalada, e o codigo de saida diz qual dos casos foi.
  $subida=ReiniciarServico 'Subir' $version
  if($subida -ne 0){
    switch($subida){
      2 { throw "A porta $Port continuou ocupada depois da copia: ha um servidor antigo no ar. Veja $DataDir\logs\reinicio_do_servidor.log" }
      3 { throw 'A nova versao nao respondeu ao teste de saude.' }
      4 { throw "Quem respondeu na porta $Port nao e a versao instalada ($version): o servidor antigo continuou no ar e o novo nao chegou a atender." }
      default { throw "Nao consegui subir o servidor (codigo $subida)." }
    }
  }
  try { Set-ItemProperty -Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CartorioGestao' -Name DisplayVersion -Value $version -ErrorAction SilentlyContinue } catch {}
  try {
    $installInfoPath=Join-Path $DataDir 'install.json'
    if(Test-Path $installInfoPath){$ii=Get-Content $installInfoPath -Raw | ConvertFrom-Json}else{$ii=[pscustomobject]@{}}
    $ii | Add-Member -NotePropertyName version -NotePropertyValue $version -Force
    $ii | Add-Member -NotePropertyName updated_at -NotePropertyValue (Get-Date).ToString('s') -Force
    WriteUtf8 $installInfoPath ($ii | ConvertTo-Json)
  } catch {}
  MetaState 'APPLIED'
  Log "Atualizacao $version concluida."
  Result 'SUCCESS' 'Atualizacao aplicada com sucesso.' $version
} catch {
  $failure=[string]$_.Exception.Message
  Log "ERRO: $failure"
  if($installChanged -and $null -ne $rollback -and (Test-Path -LiteralPath $rollback -PathType Container)){
    Log 'Falha depois do inicio da troca. Iniciando rollback automatico.'
    try {
      #   A VOLTA PARA O SERVICO PELA MESMA ROTINA — 15/09/2026.
      #     Aqui estavam `Disable-ScheduledTask` e `Stop-ScheduledTask`, que tem
      #     EXATAMENTE o defeito que esta rotina veio consertar: elas param o
      #     cmd.exe da tarefa e deixam os netos vivos. O `robocopy /MIR` seguinte
      #     restaurava os arquivos por baixo de um servidor vivo — e quem lesse o
      #     estado depois veria "ROLLED_BACK" com a versao NOVA no ar.
      #     Se a parada nao conseguir liberar a porta, o rollback CONTINUA (os
      #     arquivos quebrados nao podem ficar ali) e o aviso fica no log: e a
      #     unica ordem em que o balcao nao termina com o codigo pela metade.
      try {
        $paradaRollback=ReiniciarServico 'Parar'
        if($paradaRollback -ne 0){ Log "Atencao: nao consegui parar o servico antes de restaurar (codigo $paradaRollback). A restauracao segue, mas o processo no ar pode continuar com o codigo anterior em memoria." }
      } catch {
        Log "Atencao: a rotina de parada falhou ($($_.Exception.Message)); restaurando assim mesmo."
      }
      $codigo=Rodar "Restaurando os arquivos anteriores" 'robocopy.exe' @($rollback,$InstallDir,'/MIR','/R:2','/W:1','/NFL','/NDL','/NJH','/NJS','/NP')
      if($codigo -ge 8){throw "Falha ao restaurar os arquivos ($codigo)."}
      #   A VOLTA USA A MESMA ROTINA DE SUBIR — 15/09/2026. Aqui o servico estava
      #   parado por inteiro, e o `Start-ScheduledTask` cru podia nao subir nada (a
      #   porta ocupada por um resto de processo, por exemplo) sem que ninguem
      #   soubesse: o sistema ficaria fora do ar DEPOIS de restaurar os arquivos, que
      #   e a pior ordem possivel. O erro dela NAO derruba o rollback — os arquivos ja
      #   estao restaurados, e isso e verdade que precisa ser dita.
      try {
        $volta=ReiniciarServico 'Reiniciar'
        if($volta -ne 0){ Log "Atencao: o servico voltou com codigo $volta depois de restaurar os arquivos." }
      } catch {
        Log "Atencao: nao consegui subir o servico pela rotina de reinicio ($($_.Exception.Message)); tentando pelo agendador."
        try { Enable-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null; Start-ScheduledTask -TaskName $TaskName } catch {}
      }
      MetaState 'ROLLED_BACK' $failure
      Result 'ROLLBACK' "A atualizacao falhou e os arquivos anteriores foram restaurados: $failure" $version
      exit 2
    } catch {
      $rollbackFailure=[string]$_.Exception.Message
      Log "ERRO NO ROLLBACK: $rollbackFailure"
      MetaState 'ROLLBACK_FAILED' "$failure | $rollbackFailure"
      Result 'ERROR' "A atualizacao e o rollback falharam. Acione o suporte: $rollbackFailure" $version
      exit 1
    }
  }
  #   A RECUPERACAO FINAL TAMBEM PASSA PELA ROTINA — 15/09/2026. Aqui estavam
  #   `Enable-ScheduledTask` e `Start-ScheduledTask` crus, que nao conferem se
  #   quem subiu responde nem em que versao. E o unico caminho que sobra quando a
  #   falha aconteceu ANTES de a troca comecar (sem rollback a fazer): se ele
  #   tambem falhar em silencio, o balcao fica fora do ar sem rastro.
  try {
    $subidaFinal=ReiniciarServico 'Subir' $version
    if($subidaFinal -ne 0){ Log "Atencao: o servico nao voltou como esperado (codigo $subidaFinal). Veja $DataDir\logs\reinicio_do_servidor.log" }
  } catch {
    Log "Atencao: nao consegui subir o servico ($($_.Exception.Message))."
    try { Enable-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null; Start-ScheduledTask -TaskName $TaskName } catch {}
  }
  MetaState 'ERROR' $failure
  Result 'ERROR' $failure $version
  exit 1
}
