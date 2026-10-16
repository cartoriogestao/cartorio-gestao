"""O comprovante da gratuidade — aviso ao USUÁRIO, e não trava no ato.

    «vamos construir no sistema essa trava nos atos gratuitos, mas que seja um
     aviso de usuário, não de ato. pratica o ato e o usuário fica com aviso
     insistente até terminar de subir a comprovação da gratuidade»
                                                    — o oficial, 11/10/2026

POR QUÊ: o Portal do Selo analisa cada gratuidade e pede o comprovante; em
outubro de 2026 a casa teve de ir atrás de todos de uma vez (duas escreventes,
~5 h numa semana), porque não foram guardados na hora.

COMO SE SABE QUE O ATO É GRATUITO: pelo selo. O aparelho escreve «Selo Isento»
no texto do selo (medido em 11/10/2026: 179 selos isentos desde 08/09, 157 deles
averbações do RCPN). É a mesma régua do carimbo (`selo_no_papel`).

DE QUEM É O AVISO: de quem obteve o selo (`sd_selos.obtido_por`, que o sistema
grava com o nome da pessoa). O aviso some quando o comprovante está guardado
(`attachments`, entidade `SELO_GRATUIDADE`, amarrado ao selo).

DESDE QUANDO: `settings.gratuidade_comprovante_desde`; sem ela, 13/10/2026 —
o primeiro dia útil depois da ordem. O passado (o que já foi recolhido no
Proton) não vira aviso sozinho: retroagir é decisão do oficial, na configuração.

O PROTON AJUDA: arquivo da pasta «21-GRATUÍTOS» cujo NOME traz o código do selo
(a equipe já salva assim: «AVERBA000000XA66PB40MVB00E35.pdf») é oferecido para
trazer com um clique — e só com o clique: quem confere é a pessoa.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

ENTIDADE = "SELO_GRATUIDADE"
DESDE_PADRAO = "2026-10-13"
MARCA_DO_SELO_ISENTO = "%Selo Isento%"
#: O nome da pasta de gratuidades no Proton. O caminho inteiro não se escreve
#: aqui (traz o nome da conta e da casa): vem de `settings.gratuidade_pasta_proton`
#: ou é achado sob a pasta do Proton Drive do usuário (`pasta_proton_padrao`).
NOME_DA_PASTA_NO_PROTON = "21-GRATUÍTOS"
EXTENSOES = (".pdf", ".jpg", ".jpeg", ".png")
#: Código do selo: 6 letras, o CNS (6 dígitos) e 10 a 16 caracteres (`selo.py`).
_CODIGO_DO_SELO = re.compile(r"[A-Z]{6}\d{6}[A-Z0-9]{10,16}")


class ComprovanteError(ValueError):
    """Recusa com frase de balcão."""


def _norm(s: Any) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or ""))
                   if unicodedata.category(c) != "Mn").strip().lower()


def desde(con: sqlite3.Connection) -> str:
    try:
        row = con.execute("SELECT value FROM settings WHERE key='gratuidade_comprovante_desde'").fetchone()
    except sqlite3.OperationalError:
        row = None
    valor = (row[0] if row else "") or ""
    return valor[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", valor) else DESDE_PADRAO


def incluidos(con: sqlite3.Connection) -> list[int]:
    """HOTFIX-2026-10-13-04 (escrevente, 13/10/2026, mat. 4019 -> FERJ): selos de
    antes do «desde» que o oficial manda pôr na lista, um a um, por
    `settings.gratuidade_comprovante_incluir` («26461,26463»). Retroagir só o
    que foi pedido, sem ligar o passado inteiro."""
    try:
        row = con.execute("SELECT value FROM settings WHERE key='gratuidade_comprovante_incluir'").fetchone()
    except sqlite3.OperationalError:
        row = None
    return [int(x) for x in re.findall(r"\d+", (row[0] if row else "") or "")]


def pendentes(con: sqlite3.Connection, *, nome: str, username: str = "") -> list[dict]:
    """Os selos isentos desta pessoa ainda sem comprovante guardado."""
    alvos = {_norm(nome), _norm(username)} - {""}
    if not alvos:
        return []
    rows = con.execute(
        "SELECT s.id, s.numero, s.tabela, s.ato_id, s.atribuicao, s.obtido_em, s.obtido_por "
        "FROM sd_selos s WHERE s.texto LIKE ? AND (s.obtido_em >= ? OR s.id IN ("
        + (",".join("?" * len(incluidos(con))) or "NULL") + ")) AND s.cancelado_em IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM attachments a WHERE a.entity_type=? AND a.entity_id=s.id) "
        "ORDER BY s.obtido_em",
        (MARCA_DO_SELO_ISENTO, desde(con), *incluidos(con), ENTIDADE)).fetchall()
    saida = []
    for r in rows:
        if _norm(r[6]) in alvos:
            saida.append({"id": r[0], "numero": r[1], "tabela": r[2], "ato_id": r[3],
                          "atribuicao": r[4], "obtido_em": r[5], "obtido_por": r[6],
                          "rotulo": rotulo(con, r[2], r[3])})
    return saida


def comprovados(con: sqlite3.Connection, *, nome: str, username: str = "",
                limite: int = 300) -> list[dict]:
    """HOTFIX-2026-10-13-07: os selos isentos desta pessoa que JA tem
    comprovante, com a lista de anexos - para ver e acrescentar mais."""
    alvos = {_norm(nome), _norm(username)} - {""}
    if not alvos:
        return []
    rows = con.execute(
        "SELECT s.id, s.numero, s.tabela, s.ato_id, s.atribuicao, s.obtido_em, s.obtido_por "
        "FROM sd_selos s WHERE s.texto LIKE ? AND s.cancelado_em IS NULL "
        "AND EXISTS (SELECT 1 FROM attachments a WHERE a.entity_type=? AND a.entity_id=s.id) "
        "ORDER BY s.obtido_em DESC LIMIT ?",
        (MARCA_DO_SELO_ISENTO, ENTIDADE, int(limite))).fetchall()
    saida = []
    for r in rows:
        if _norm(r[6]) in alvos:
            saida.append({"id": r[0], "numero": r[1], "tabela": r[2], "ato_id": r[3],
                          "atribuicao": r[4], "obtido_em": r[5], "obtido_por": r[6],
                          "rotulo": rotulo(con, r[2], r[3]),
                          "anexos": anexos(con, r[0])})
    return saida


def anexos(con: sqlite3.Connection, selo_id: int) -> list[dict]:
    """HOTFIX-2026-10-13-07: todos os comprovantes de um selo (nunca apaga)."""
    return [{"id": a[0], "nome": a[1], "em": a[2]} for a in con.execute(
        "SELECT id, original_name, uploaded_at FROM attachments WHERE entity_type=? "
        "AND entity_id=? ORDER BY id", (ENTIDADE, int(selo_id))).fetchall()]


def rotulo(con: sqlite3.Connection, tabela: Any, ato_id: Any) -> str:
    """HOTFIX-2026-10-13-08: «Mat. 4019 – R-01» em vez de «ri atos 3751». So le."""
    try:
        if tabela == "ri_atos" and ato_id:
            r = con.execute("SELECT m.numero, a.tipo, a.numero FROM ri_atos a "
                            "JOIN ri_matriculas m ON m.id=a.matricula_id WHERE a.id=?",
                            (int(ato_id),)).fetchone()
            if r:
                n = str(r[2] or "")
                return f"Mat. {r[0]} – {r[1] or ''}-{n.zfill(2) if n.isdigit() else n}"
        if tabela == "ri_matriculas" and ato_id:
            r = con.execute("SELECT numero FROM ri_matriculas WHERE id=?", (int(ato_id),)).fetchone()
            if r:
                return f"Mat. {r[0]} – abertura"
    except (sqlite3.Error, ValueError, TypeError):
        pass
    return ""


def quantos_pendentes(con: sqlite3.Connection, *, nome: str, username: str = "") -> int:
    return len(pendentes(con, nome=nome, username=username))


def _selo(con, selo_id: int) -> dict:
    r = con.execute("SELECT id, numero, texto, obtido_por FROM sd_selos WHERE id=?",
                    (int(selo_id),)).fetchone()
    if not r:
        raise ComprovanteError("Selo não encontrado.")
    if "selo isento" not in (r[2] or "").lower():
        raise ComprovanteError("Este selo não é de ato gratuito.")
    return {"id": r[0], "numero": r[1], "obtido_por": r[3]}


def guardar(con: sqlite3.Connection, selo_id: int, *, nome_arquivo: str, conteudo: bytes,
            pasta: Path, usuario_id: int | None, agora: str, origem: str = "upload") -> int:
    """Guarda o comprovante amarrado ao selo. O aviso daquele ato some."""
    selo = _selo(con, selo_id)
    nome_arquivo = Path(nome_arquivo or "").name
    if not nome_arquivo.lower().endswith(EXTENSOES):
        raise ComprovanteError("Comprovante em PDF ou imagem (JPG, PNG).")
    if not conteudo:
        raise ComprovanteError("O arquivo veio vazio.")
    sha = hashlib.sha256(conteudo).hexdigest()
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{selo['numero']}_{sha[:10]}{Path(nome_arquivo).suffix.lower()}"
    destino.write_bytes(conteudo)
    cur = con.execute(
        "INSERT INTO attachments(entity_type, entity_id, original_name, stored_name, stored_path, "
        "sha256, size_bytes, description, uploaded_by, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (ENTIDADE, int(selo_id), nome_arquivo, destino.name, str(destino), sha, len(conteudo),
         f"Comprovante da gratuidade do selo {selo['numero']} ({origem})", usuario_id, agora))
    return int(cur.lastrowid)


def pasta_proton_padrao() -> Path | None:
    """A primeira pasta «21-GRATUÍTOS» sob o Proton Drive deste usuário."""
    base = Path.home() / "Proton Drive"
    if not base.is_dir():
        return None
    for nivel in ("*", "*/*", "*/*/*", "*/*/*/*"):
        for p in base.glob(f"{nivel}/{NOME_DA_PASTA_NO_PROTON}"):
            if p.is_dir():
                return p
    return None


def no_proton(codigos: list[str], pasta: Path | None = None) -> dict[str, Path]:
    """Arquivos da pasta de gratuidades cujo nome traz o código do selo."""
    pasta = pasta or pasta_proton_padrao()
    if not codigos or not pasta or not Path(pasta).is_dir():
        return {}
    procurados = {c.upper() for c in codigos if c}
    achados: dict[str, Path] = {}
    for arq in Path(pasta).rglob("*"):
        if not arq.is_file() or arq.suffix.lower() not in EXTENSOES:
            continue
        for codigo in _CODIGO_DO_SELO.findall(arq.name.upper()):
            if codigo in procurados and codigo not in achados:
                achados[codigo] = arq
    return achados
