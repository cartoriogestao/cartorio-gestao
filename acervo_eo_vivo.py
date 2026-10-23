"""
Ler o E-Oficio ao vivo — MSSQL `bdCartorio` — para a carga de Protesto.

POR QUE ISTO EXISTE
    O `acervo_eoficio.sqlite3` e arquivo morto: titulo novo (ex.: chave 141352)
    so existe no SQL Server. A tela `/protesto/importar-eoficio` precisa do
    E-Oficio **ao vivo**, nao do snapshot.

ESPELHO DO QUE A CASA JA FAZ
    Os scripts `MIGRACAO/EXPORTAR_*.ps1` abrem o `bdCartorio` com
    `System.Data.SqlClient`, Integrated Security, so leitura — a mesma string
    que `EXPORTAR_TUDO.ps1` usa (`Server=localhost` / `localhost/SERVER`,
    `Database=bdCartorio`, `TrustServerCertificate=True`). Aqui e o mesmo
    caminho, focado nas duas tabelas que `carregar_protesto` le:
    `tbAvisoProtesto` e `tbPessoa`.

O FLUXO
    1. Abre o MSSQL ao vivo (tenta os candidatos da casa).
    2. Exporta as duas tabelas em JSONL (igual ao exportador).
    3. Substitui essas tabelas no `acervo_eoficio.sqlite3` (ou cria o arquivo
       se ainda nao existir, so com o que o Protesto precisa).
    4. A carga dirigida (`acervo_carga.carregar_protesto`) segue igual.

O QUE NAO FAZ
    Nao interpreta campo. Nao altera o E-Oficio. Nao rebuilda as 229 tabelas.
    Nao inventa protocolo. PAGO continua vindo de `strTipoPG`, como a carga
    ja mapeia.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

import banco_pg

NOME_ACERVO = "acervo_eoficio.sqlite3"

# Mesma disciplina do EXPORTAR_TUDO.ps1: Integrated Security, so leitura.
# Instancia medida: SERVIDOR\SERVER (servico MSSQL$SERVER). localhost e
# localhost\SERVER resolvem para monte (sysadmin). O CartorioGestao em producao
# roda como SYSTEM via tarefa CartorioGestaoServidor — essa conta precisa de
# usuario no bdCartorio (db_datareader), senao todas as strings falham.
CANDIDATOS_CONEXAO: tuple[str, ...] = (
    r"Server=localhost\SERVER;Database=bdCartorio;Integrated Security=True;TrustServerCertificate=True",
    r"Server=.\SERVER;Database=bdCartorio;Integrated Security=True;TrustServerCertificate=True",
    r"Server=SERVIDOR\SERVER;Database=bdCartorio;Integrated Security=True;TrustServerCertificate=True",
    r"Server=(local)\SERVER;Database=bdCartorio;Integrated Security=True;TrustServerCertificate=True",
    "Server=localhost;Database=bdCartorio;Integrated Security=True;TrustServerCertificate=True",
)

TABELAS_PROTESTO: tuple[str, ...] = ("tbAvisoProtesto", "tbPessoa")


class EoVivoError(ValueError):
    """Impedimento ao falar com o E-Oficio ao vivo — frase pronta para a tela."""


def _powershell() -> str:
    """powershell.exe do sistema. Sem ele nao ha como espelhar o EXPORTAR_*."""
    for base in (
        os.environ.get("SystemRoot", r"C:\Windows"),
        r"C:\Windows",
    ):
        candidato = (
            Path(base) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        )
        if candidato.is_file():
            return str(candidato)
    return "powershell.exe"


_PS_EXPORTAR = r"""
$ErrorActionPreference = 'Stop'
$Destino = $env:CG_EO_DESTINO
$Tabelas = $env:CG_EO_TABELAS -split ';'
$Candidatos = $env:CG_EO_CONN -split '\|\|'
New-Item -ItemType Directory -Force -Path $Destino | Out-Null
$conn = $null
$usado = $null
$falhas = New-Object System.Collections.Generic.List[string]
$conta = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
foreach ($cs in $Candidatos) {
  if (-not $cs) { continue }
  try {
    $c = New-Object System.Data.SqlClient.SqlConnection $cs
    $c.Open()
    $conn = $c
    $usado = $cs
    break
  } catch {
    $msg = $_.Exception.Message
    [void]$falhas.Add("$cs => $msg")
  }
}
if (-not $conn) {
  if ($falhas.Count) { $detalhe = ($falhas -join ' || ') } else { $detalhe = 'nenhum candidato tentado' }
  Write-Error "Nao consegui abrir o bdCartorio no SQL Server (Integrated Security). Conta Windows: $conta. Tentativas: $detalhe. Se a conta for SISTEMA/SYSTEM, o Admin precisa conceder leitura ao bdCartorio (CREATE USER + db_datareader) para AUTORIDADE NT\SISTEMA - a instancia SERVER pode estar no ar e mesmo assim a conta do servico nao enxerga o banco."
  exit 2
}
function ExportarTabela([string]$tabela) {
  $cmd = $conn.CreateCommand()
  $cmd.CommandText = ('SELECT * FROM [{0}]' -f $tabela)
  $cmd.CommandTimeout = 1800
  $rd = $cmd.ExecuteReader()
  $caminho = Join-Path $Destino ($tabela + '.jsonl')
  $sw = New-Object System.IO.StreamWriter($caminho, $false, [System.Text.UTF8Encoding]::new($false))
  $n = 0
  try {
    while ($rd.Read()) {
      $l = [ordered]@{}
      for ($i = 0; $i -lt $rd.FieldCount; $i++) {
        $v = $rd.GetValue($i)
        if ($v -is [System.DBNull]) { $v = $null }
        elseif ($v -is [string]) { $v = $v.TrimEnd() }
        elseif ($v -is [datetime]) { $v = $v.ToString('yyyy-MM-dd HH:mm:ss') }
        elseif ($v -is [byte[]]) { $v = $null }
        elseif ($v -is [bool]) { $v = [int]$v }
        $l[$rd.GetName($i)] = $v
      }
      $sw.WriteLine(($l | ConvertTo-Json -Compress -Depth 4))
      $n++
    }
  } finally { $sw.Close(); $rd.Close() }
  return $n
}
$resumo = [ordered]@{ conexao = $usado; tabelas = [ordered]@{} }
foreach ($t in $Tabelas) {
  if (-not $t) { continue }
  $resumo.tabelas[$t] = [int](ExportarTabela $t)
}
$conn.Close()
$resumo | ConvertTo-Json -Compress -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $Destino '_resumo.json')
"""


def _ler_jsonl(caminho: Path) -> list[dict]:
    saida: list[dict] = []
    if not caminho.is_file():
        return saida
    with caminho.open(encoding="utf-8-sig", errors="replace") as fh:
        for linha in fh:
            linha = linha.strip()
            if not linha:
                continue
            saida.append(json.loads(linha))
    return saida


def exportar_tabelas_ao_vivo(
    destino: str | Path,
    *,
    tabelas: Iterable[str] = TABELAS_PROTESTO,
    conexoes: Iterable[str] = CANDIDATOS_CONEXAO,
) -> dict:
    """Puxa as tabelas do MSSQL ao vivo para `destino` (JSONL). So leitura.

    Devolve `{conexao, tabelas: {nome: linhas}}`. Levanta `EoVivoError` se
    nenhum candidato de conexao abrir.
    """
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CG_EO_DESTINO"] = str(destino)
    env["CG_EO_TABELAS"] = ";".join(tabelas)
    env["CG_EO_CONN"] = "||".join(conexoes)
    with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".ps1", delete=False) as fh:
        fh.write(_PS_EXPORTAR)
        script = fh.name
    try:
        proc = subprocess.run(
            [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", script],
            capture_output=True, text=True, env=env, timeout=1800,
        )
    finally:
        Path(script).unlink(missing_ok=True)
    if proc.returncode != 0:
        detalhe = (proc.stderr or proc.stdout or "").strip()
        raise EoVivoError(
            "Não consegui ler o E-Ofício ao vivo (MSSQL bdCartorio). "
            "A carga de protesto precisa do banco ao vivo, não do snapshot. "
            + (detalhe[:1800] if detalhe else
               "Confira a instância SERVER e a conta do serviço "
               "(CartorioGestao roda como SYSTEM)."))
    resumo_path = destino / "_resumo.json"
    if not resumo_path.is_file():
        raise EoVivoError(
            "O E-Ofício ao vivo respondeu, mas o resumo da exportação não "
            "apareceu. Nada foi gravado no acervo.")
    return json.loads(resumo_path.read_text(encoding="utf-8-sig"))


def _valor_para_sqlite(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


def _criar_tabela_se_faltar(con: sqlite3.Connection, nome: str,
                            colunas: list[str]) -> None:
    """Cria a tabela sem tipos — mesma disciplina do acervo_eoficio."""
    existe = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (nome,)).fetchone()
    if existe:
        return
    corpo = ", ".join(f'"{c}"' for c in colunas)
    con.execute(f'CREATE TABLE "{nome}" ({corpo})')


def _substituir_tabela(con: sqlite3.Connection, nome: str,
                       linhas: list[dict]) -> int:
    """Apaga o conteudo e reinsere. Conserva o esquema se a tabela ja existe."""
    if not linhas:
        if con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (nome,)).fetchone():
            con.execute(f'DELETE FROM "{nome}"')
        return 0
    colunas_origem = list(linhas[0].keys())
    _criar_tabela_se_faltar(con, nome, colunas_origem)
    cols_sqlite = {r[1] for r in con.execute(f'PRAGMA table_info("{nome}")')}
    cols = [c for c in colunas_origem if c in cols_sqlite]
    if not cols:
        raise EoVivoError(
            f"A tabela `{nome}` do acervo não tem coluna em comum com o "
            f"E-Ofício ao vivo.")
    con.execute(f'DELETE FROM "{nome}"')
    marcas = ",".join("?" * len(cols))
    col_sql = ",".join(f'"{c}"' for c in cols)
    lote = [
        tuple(_valor_para_sqlite(linha.get(c)) for c in cols)
        for linha in linhas
    ]
    con.executemany(
        f'INSERT INTO "{nome}" ({col_sql}) VALUES ({marcas})', lote)
    return len(lote)


def aplicar_jsonl_no_acervo(
    caminho_acervo: str | Path,
    pasta_jsonl: str | Path,
    *,
    tabelas: Iterable[str] = TABELAS_PROTESTO,
) -> dict:
    """Substitui no sqlite as tabelas puxadas ao vivo. Cria o arquivo se faltar."""
    caminho_acervo = Path(caminho_acervo)
    if caminho_acervo.is_dir():
        caminho_acervo = caminho_acervo / NOME_ACERVO
    pasta_jsonl = Path(pasta_jsonl)
    caminho_acervo.parent.mkdir(parents=True, exist_ok=True)
    novo = not caminho_acervo.exists()
    # SQLITE DE VERDADE (LH09): pela porta do SQLite, e nao pelo desvio do
    # `sqlite3.connect`, que decide pelo nome do arquivo. Aqui se ESCREVE: e a
    # atualizacao do acervo, no lugar.
    con = banco_pg.conectar_sqlite(caminho_acervo, so_leitura=False)
    try:
        contagens: dict[str, int] = {}
        for nome in tabelas:
            linhas = _ler_jsonl(pasta_jsonl / f"{nome}.jsonl")
            contagens[nome] = _substituir_tabela(con, nome, linhas)
        con.execute("""CREATE TABLE IF NOT EXISTS _acervo_info (
                         chave TEXT PRIMARY KEY, valor TEXT)""")
        con.execute(
            "INSERT OR REPLACE INTO _acervo_info(chave, valor) VALUES (?,?)",
            ("protesto_ao_vivo", "1"))
        con.execute(
            "INSERT OR REPLACE INTO _acervo_info(chave, valor) VALUES (?,?)",
            ("origem_protesto", "MSSQL bdCartorio ao vivo"))
        if novo:
            con.execute(
                "INSERT OR REPLACE INTO _acervo_info(chave, valor) VALUES (?,?)",
                ("origem", "criado pela puxada ao vivo do protesto"))
        con.commit()
    finally:
        con.close()
    return {"arquivo": str(caminho_acervo), "novo": novo, "tabelas": contagens}


def atualizar_protesto_ao_vivo(
    caminho_acervo: str | Path,
    *,
    conexoes: Iterable[str] | None = None,
) -> dict:
    """Puxa tbAvisoProtesto + tbPessoa do EO ao vivo e grava no acervo sqlite.

    E o unico caminho que `/protesto/importar-eoficio` deve usar antes da carga.
    """
    caminho_acervo = Path(caminho_acervo)
    if caminho_acervo.is_dir():
        caminho_acervo = caminho_acervo / NOME_ACERVO
    with tempfile.TemporaryDirectory(prefix="cg_eo_vivo_") as tmp:
        pasta = Path(tmp)
        resumo = exportar_tabelas_ao_vivo(
            pasta,
            tabelas=TABELAS_PROTESTO,
            conexoes=conexoes or CANDIDATOS_CONEXAO,
        )
        aplicado = aplicar_jsonl_no_acervo(
            caminho_acervo, pasta, tabelas=TABELAS_PROTESTO)
    return {
        "conexao": resumo.get("conexao"),
        "tabelas_exportadas": resumo.get("tabelas") or {},
        "tabelas_aplicadas": aplicado["tabelas"],
        "arquivo": aplicado["arquivo"],
        "acervo_criado": aplicado["novo"],
        "ao_vivo": True,
    }
