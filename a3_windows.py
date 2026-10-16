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
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


class A3WindowsError(ValueError):
    """Erro de regra da assinatura pelo Windows, com a frase do balcão."""


PRAZO_SEGUNDOS = 180     # o titular digita o PIN na janela do token

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


def _frase(saida: str) -> str:
    texto = saida.lower()
    if "conjunto de chaves" in texto or "keyset" in texto:
        return ("o token conectado não tem a chave de nenhum certificado "
                "válido. Confira se o token está plugado NESTA máquina — pela "
                "Área de Trabalho Remota, marque «Cartões inteligentes» em "
                "Recursos locais e conecte de novo.")
    if "cancel" in texto:
        return "a assinatura foi cancelada na janela do token."
    if "pin" in texto and ("incorret" in texto or "wrong" in texto):
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
            raise A3WindowsError(
                "A janela do token ficou sem resposta — assine de novo e "
                "digite o PIN quando ela aparecer.") from erro
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
