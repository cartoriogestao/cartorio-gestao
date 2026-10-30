"""Assinar pelo REPOSITÓRIO DE CERTIFICADOS DO WINDOWS — o caminho dos sites.

Medido em 15/10/2026, nesta casa: o driver PKCS#11 do SafeSign
(`aetpkss1.dll`) falha ao listar os leitores (código 6) — e o mesmo token
funciona nos sites, porque o navegador não usa o PKCS#11: usa o repositório
do Windows (o provedor «SafeSign IC Standard Windows Cryptographic Service
Provider»). Assinando por ele, o ensaio do dia saiu certo na primeira vez:
PKCS#7 com o PDF DENTRO, SHA-256, hora da assinatura — o formato dos 44
instrumentos que esta casa mandou à CENPROT —, e `assinatura_digital.conferir`
disse que o pacote embrulha, byte a byte, o PDF de teste.

**A JANELA DE PIN É A DO PRÓPRIO TOKEN.** O sistema não vê, não recebe e não
guarda o PIN: quem o digita é o titular, na janela do SafeSign. Por isso isto
só funciona NA SESSÃO DO WINDOWS DO TITULAR — e é por isso que roda dentro do
serviço local A3 (`a3_servico_local`), que ele abre na sessão dele, e não no
servidor do sistema, que roda numa sessão sem tela.

**E A SESSÃO REMOTA PRECISA REPASSAR O TOKEN.** Medido no mesmo dia: pela
Área de Trabalho Remota sem «Cartões inteligentes» marcado em Recursos
locais, o Windows responde «erro inesperado de cartão» e nenhuma chave se
acha. Com a opção marcada, assinou.

**A ASSINATURA ACONTECE NUM PROCESSO À PARTE** (PowerShell com o .NET
`SignedCms`): o driver do token já derrubou processo nesta casa, e nada do que
ele faz pode alcançar quem o chamou.

**NO LOTE É UM PROCESSO SÓ** (`assinar_pdfs`, 30/10/2026). Queixa do oficial:
«Mais horrível ainda ter que colocar 20 vezes o PIN do certificado.» Cada
`assinar_pdf` abre um PowerShell novo, e a leitura é que a sessão do token com o
PIN vale enquanto o contexto do provedor está aberto: processo novo, PIN de
novo. Por isso o lote assina N papéis num PowerShell só, com o MESMO objeto de
certificado e a chave aberta do começo ao fim. **ISSO É HIPÓTESE, E NÃO
MEDIÇÃO**: não se assina com o token nos testes, e quem prova é a primeira
assinatura real. Quem manda na janela do PIN é o driver do token.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


class A3WindowsError(ValueError):
    """Erro de regra da assinatura pelo Windows, com a frase do balcão."""


PRAZO_SEGUNDOS = 180     # o titular digita o PIN na janela do token
PRAZO_POR_PDF_SEGUNDOS = 20   # o lote cresce com o tamanho (`prazo_do_lote`)

# O PowerShell que assina. Escrito num arquivo temporário a cada chamada: o
# conteúdo é fixo e o que varia (caminhos e certificado) vai por parâmetro —
# nada de montar comando com texto de fora.
_SCRIPT = r"""
param([string]$Pdf, [string]$Saida, [string]$Thumb)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$agora = Get-Date
$certs = Get-ChildItem Cert:\CurrentUser\My | Where-Object {
    $_.HasPrivateKey -and $_.NotAfter -gt $agora -and
    $_.Subject -match 'O=ICP-Brasil' -and
    ($Thumb -eq '' -or $_.Thumbprint -like "$Thumb*") } |
    Sort-Object NotAfter -Descending
if (-not $certs) { Write-Output 'SEM_CERTIFICADO'; exit 3 }
$bytes = [System.IO.File]::ReadAllBytes($Pdf)
$falhas = @()
foreach ($cert in $certs) {
  try {
    $ci = New-Object System.Security.Cryptography.Pkcs.ContentInfo (,$bytes)
    $cms = New-Object System.Security.Cryptography.Pkcs.SignedCms ($ci, $false)
    $s = New-Object System.Security.Cryptography.Pkcs.CmsSigner ($cert)
    $s.DigestAlgorithm = New-Object System.Security.Cryptography.Oid ('2.16.840.1.101.3.4.2.1')
    $s.IncludeOption = [System.Security.Cryptography.X509Certificates.X509IncludeOption]::ExcludeRoot
    [void]$s.SignedAttributes.Add((New-Object System.Security.Cryptography.Pkcs.Pkcs9SigningTime))
    $cms.ComputeSignature($s, $false)
    [System.IO.File]::WriteAllBytes($Saida, $cms.Encode())
    Write-Output ('OK|' + $cert.Thumbprint)
    exit 0
  } catch {
    $falhas += ($cert.Thumbprint.Remove(8) + ': ' + $_.Exception.InnerException.Message + $_.Exception.Message)
  }
}
Write-Output ('FALHOU|' + ($falhas -join ' ; '))
exit 4
"""

# O POWERSHELL DO LOTE. O formato de cada assinatura é o de `_SCRIPT`: PKCS#7 com
# o PDF dentro, SHA-256, hora da assinatura, `ExcludeRoot`, só `O=ICP-Brasil`.
#
#   - A LISTA VAI POR ARQUIVO (`-Lista`, uma linha por PDF: entrada, TAB, saída):
#     só caminhos, e nada de conteúdo nem de segredo em argv.
#   - `$cert` E `$chave` VIVEM ATÉ O FIM DO PROCESSO. `$chave` nunca é usada: ela
#     só mantém aberto o contexto do provedor entre um `ComputeSignature` e outro.
#     `PrivateKey` falha em chave CNG, e sem ela o lote segue como o de um papel.
#   - O RESULTADO SE ANOTA ITEM A ITEM (`-Resultado`), depois de o `.p7s` estar no
#     disco: se o processo morrer no meio, o que já foi assinado fica valendo.
#   - O SEGUINTE SÓ SE TENTA QUANDO A CHAVE NÃO ESTÁ NO TOKEN CONECTADO, a falha
#     medida que não pede PIN. Palavra desconhecida PARA, e PIN recusado também:
#     PIN errado em sequência bloqueia o A3, e parar é o erro que não custa o token.
#   - Depois do primeiro assinado, QUALQUER falha para o lote.
_SCRIPT_LOTE = r"""
param([string]$Lista, [string]$Resultado, [string]$Thumb)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$utf8 = New-Object System.Text.UTF8Encoding ($false)
$pediuPin = '\bpin\b|senha|cancel|bloque|block'
function Anotar([string]$Linha) {
  [System.IO.File]::AppendAllText($Resultado, ($Linha + "`n"), $utf8)
}
function Mensagem($Erro) {
  $t = [string]$Erro.Exception.InnerException.Message + ' ' + $Erro.Exception.Message
  return ($t -replace '\s+', ' ').Trim()
}
function Chave-Fora-Daqui([string]$Texto) {
  if ($Texto -match $pediuPin) { return $false }
  return ($Texto -match '\bchaves?\b|\bkey\b|keyset|cart.o|\bcard\b|smart ?card')
}
function Abrir-Chave($Cert) {
  try { return $Cert.PrivateKey }
  catch {
    if ((Mensagem $_) -match $pediuPin) { throw }
    return $null
  }
}
function Assinar-Um($Cert, [string]$Entrada, [string]$Saida) {
  $bytes = [System.IO.File]::ReadAllBytes($Entrada)
  $ci = New-Object System.Security.Cryptography.Pkcs.ContentInfo (,$bytes)
  $cms = New-Object System.Security.Cryptography.Pkcs.SignedCms ($ci, $false)
  $s = New-Object System.Security.Cryptography.Pkcs.CmsSigner ($Cert)
  $s.DigestAlgorithm = New-Object System.Security.Cryptography.Oid ('2.16.840.1.101.3.4.2.1')
  $s.IncludeOption = [System.Security.Cryptography.X509Certificates.X509IncludeOption]::ExcludeRoot
  [void]$s.SignedAttributes.Add((New-Object System.Security.Cryptography.Pkcs.Pkcs9SigningTime))
  $cms.ComputeSignature($s, $false)
  [System.IO.File]::WriteAllBytes($Saida, $cms.Encode())
}
$agora = Get-Date
$certs = @(Get-ChildItem Cert:\CurrentUser\My | Where-Object {
    $_.HasPrivateKey -and $_.NotAfter -gt $agora -and
    $_.Subject -match 'O=ICP-Brasil' -and
    ($Thumb -eq '' -or $_.Thumbprint -like "$Thumb*") } |
    Sort-Object NotAfter -Descending)
if ($certs.Count -eq 0) { Anotar 'SEM_CERTIFICADO'; exit 3 }
$itens = [System.IO.File]::ReadAllLines($Lista, $utf8)
$usado = $null
$chave = $null
for ($i = 0; $i -lt $itens.Count; $i++) {
  $par = $itens[$i].Split("`t")
  if ($null -eq $usado) {
    $falhas = @()
    foreach ($cert in $certs) {
      try {
        $chave = Abrir-Chave $cert
        Assinar-Um $cert $par[0] $par[1]
        $usado = $cert
        break
      } catch {
        $t = Mensagem $_
        $falhas += ($cert.Thumbprint.Remove(8) + ': ' + $t)
        if (-not (Chave-Fora-Daqui $t)) { break }
      }
    }
    if ($null -eq $usado) {
      Anotar ("FALHOU`t$i`t" + ($falhas -join ' ; '))
      exit 4
    }
  } else {
    try { Assinar-Um $usado $par[0] $par[1] }
    catch {
      Anotar ("FALHOU`t$i`t" + $usado.Thumbprint.Remove(8) + ': ' + (Mensagem $_))
      exit 4
    }
  }
  Anotar ("OK`t$i`t" + $usado.Thumbprint)
}
exit 0
"""


_SEM_RESPOSTA = ("A janela do token ficou sem resposta — assine de novo e digite "
                 "o PIN quando ela aparecer.")


def _frase(saida: str) -> str:
    texto = saida.lower()
    if "conjunto de chaves" in texto or "keyset" in texto:
        return ("o token conectado não tem a chave de nenhum certificado "
                "válido. Confira se o token está plugado NESTA máquina — pela "
                "Área de Trabalho Remota, marque «Cartões inteligentes» em "
                "Recursos locais e conecte de novo.")
    if "cancel" in texto:
        return "a assinatura foi cancelada na janela do token."
    if "pin" in texto and ("incorret" in texto or "wrong" in texto
                           or "errad" in texto):
        return "o PIN não foi aceito pelo token."
    return "o Windows não conseguiu assinar: " + saida.strip()[:300]


def assinar_pdf(pdf: bytes, thumbprint: str = "") -> dict:
    """Assina o PDF pelo repositório do Windows. Devolve `{p7s, thumbprint}`.

    Sem `thumbprint`, tenta os certificados válidos com chave, do de validade
    mais longa ao mais curto: o que não está no token conectado falha na hora,
    sem pedir PIN (medido), e o seguinte é tentado.

    **SÓ CERTIFICADO ICP-BRASIL** (`O=ICP-Brasil` no titular). Medido nesta
    máquina: o repositório tem também um certificado técnico do Windows, sem
    nome de pessoa e com chave em software — sem o filtro, a tentativa
    automática assinaria com ele um papel que a serventia entrega como
    assinado pelo tabelião.
    """
    if not pdf:
        raise A3WindowsError("PDF vazio — nada para assinar.")
    thumb = "".join(c for c in str(thumbprint or "") if c.isalnum()).upper()
    with tempfile.TemporaryDirectory(prefix="cg_a3w_") as pasta:
        p = Path(pasta)
        (p / "assinar.ps1").write_text(_SCRIPT, encoding="utf-8-sig")
        (p / "doc.pdf").write_bytes(bytes(pdf))
        try:
            feito = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-File", str(p / "assinar.ps1"),
                 "-Pdf", str(p / "doc.pdf"), "-Saida", str(p / "doc.p7s"),
                 "-Thumb", thumb],
                capture_output=True, timeout=PRAZO_SEGUNDOS,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as erro:
            raise A3WindowsError(_SEM_RESPOSTA) from erro
        saida = (feito.stdout or b"").decode("utf-8", "replace") + \
            (feito.stderr or b"").decode("utf-8", "replace")
        if "SEM_CERTIFICADO" in saida:
            raise A3WindowsError(
                "Nenhum certificado válido com chave no Windows desta sessão.")
        assinado = p / "doc.p7s"
        if feito.returncode != 0 or not assinado.exists():
            raise A3WindowsError(_frase(saida))
        usado = saida.split("OK|", 1)[-1].strip().split()[0] if "OK|" in saida \
            else ""
        return {"p7s": assinado.read_bytes(), "thumbprint": usado}


def prazo_do_lote(quantos: int) -> int:
    """Quantos segundos o lote de `quantos` PDFs tem. Só calcula."""
    return PRAZO_SEGUNDOS + PRAZO_POR_PDF_SEGUNDOS * max(int(quantos), 0)


def _ler_resultado(pasta: Path, quantos: int) -> tuple[list[dict], str, bool]:
    """O que o PowerShell anotou: os assinados, o texto da falha, e se faltou
    certificado. Só vale o item com a linha `OK` E o `.p7s` no disco."""
    assinados: list[dict] = []
    falha, sem_certificado = "", False
    arquivo = pasta / "resultado.txt"
    if not arquivo.exists():
        return assinados, falha, sem_certificado
    for linha in arquivo.read_text(encoding="utf-8", errors="replace").splitlines():
        partes = linha.split("\t", 2)
        if partes[0] == "SEM_CERTIFICADO":
            sem_certificado = True
        elif partes[0] == "FALHOU" and len(partes) == 3:
            falha = partes[2]
        elif partes[0] == "OK" and len(partes) == 3 and partes[1].isdigit():
            indice = int(partes[1])
            p7s = pasta / f"{indice:03d}.p7s"
            if indice < quantos and p7s.exists() and p7s.stat().st_size:
                assinados.append({"indice": indice, "p7s": p7s.read_bytes(),
                                  "thumbprint": partes[2].strip()})
    return assinados, falha, sem_certificado


def assinar_pdfs(lista: list[bytes], thumbprint: str = "") -> dict:
    """Assina VÁRIOS PDFs num único PowerShell, com o certificado aberto uma vez.
    Devolve `{"assinados": [{indice, p7s, thumbprint}], "falha": frase ou None}`.

    **A PRIMEIRA FALHA DO TOKEN PARA O LOTE** (ver `_SCRIPT_LOTE`), e isso não é
    exceção: os que já foram assinados ficam valendo e voltam em `assinados`, em
    ordem, e `falha` diz o que houve. Exceção é só o erro de quem chamou (lista
    vazia, PDF vazio), que nem chega ao token.

    O PIN continua fora do sistema: quem o pede é a janela do token.
    """
    pdfs = [bytes(x or b"") for x in (lista or ())]
    if not pdfs or not all(pdfs):
        raise A3WindowsError("PDF vazio — nada para assinar.")
    thumb = "".join(c for c in str(thumbprint or "") if c.isalnum()).upper()
    with tempfile.TemporaryDirectory(prefix="cg_a3w_") as pasta:
        p = Path(pasta)
        (p / "assinar_lote.ps1").write_text(_SCRIPT_LOTE, encoding="utf-8-sig")
        linhas = []
        for i, pdf in enumerate(pdfs):
            (p / f"{i:03d}.pdf").write_bytes(pdf)
            linhas.append(f"{p / f'{i:03d}.pdf'}\t{p / f'{i:03d}.p7s'}")
        (p / "lista.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
        saida, sem_resposta = "", False
        try:
            feito = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass",
                 "-File", str(p / "assinar_lote.ps1"),
                 "-Lista", str(p / "lista.txt"),
                 "-Resultado", str(p / "resultado.txt"),
                 "-Thumb", thumb],
                capture_output=True, timeout=prazo_do_lote(len(pdfs)),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            saida = (feito.stdout or b"").decode("utf-8", "replace") + \
                (feito.stderr or b"").decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            sem_resposta = True
        assinados, falha, sem_certificado = _ler_resultado(p, len(pdfs))
    if sem_resposta:
        frase = _SEM_RESPOSTA
    elif sem_certificado:
        frase = "Nenhum certificado válido com chave no Windows desta sessão."
    elif falha:
        frase = _frase(falha)
    elif len(assinados) < len(pdfs):
        frase = _frase(saida)
    else:
        frase = None
    return {"assinados": assinados, "falha": frase}


def certificados() -> list[dict]:
    """Os certificados com chave do Windows desta sessão. Só LÊ — sem PIN."""
    cmd = ("Get-ChildItem Cert:\\CurrentUser\\My | Where-Object HasPrivateKey | "
           "ForEach-Object { [pscustomobject]@{ assunto=$_.Subject; "
           "emissor=$_.Issuer; validade=$_.NotAfter.ToString('yyyy-MM-dd'); "
           "thumbprint=$_.Thumbprint } } | ConvertTo-Json -Compress")
    feito = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                            "-Command", cmd], capture_output=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    texto = (feito.stdout or b"").decode("utf-8", "replace").strip()
    if not texto:
        return []
    dados = json.loads(texto)
    return dados if isinstance(dados, list) else [dados]
