"""Serviço do editor de modelos — RCPN termos e moldes (Marco 1).

Responsabilidades: listar, carregar, rascunho, publicar, histórico, diff,
restaurar, semear v1, validar, chave por área, leitura da versão publicada.

NÃO liga a emissão neste marco se isso exigir editar módulos do motor.
A função `conteudo_publicado_se_ligado` fica pronta, testada e documentada.
"""
from __future__ import annotations

import hashlib
import io
import re
import sqlite3
import zipfile
from typing import Any, Callable

import modelos_da_casa as CASA
import modelos_elementos as ELEM
import modelos_moldes as MOLDES
from modelos_elementos_schema import (
    CORPO,
    ENCERRAMENTO,
    PARTES,
    RODAPE,
    RCPN,
)
from modelos_editor_schema import (
    AREA_RCPN,
    PARTE_CORPO,
    PARTE_ENCERRAMENTO,
    PARTE_MOLDE,
    PARTE_RODAPE,
    PARTES_TEXTO,
    STATUS_ARQUIVADA,
    STATUS_PUBLICADA,
    STATUS_RASCUNHO,
    chave_da_area,
    init_modelos_editor_schema,
)
from modelos_editor_serventia import literais_proibidos

# Escopo Marco 1 — só RCPN termos + moldes ODT
TERMOS_RCPN: tuple[str, ...] = (
    "RC_TERMO_NASCIMENTO",
    "RC_TERMO_CASAMENTO",
    "RC_TERMO_OBITO",
    "RC_TERMO_LIVRO_E",
)
MOLDES_RCPN: tuple[str, ...] = tuple(m["chave"] for m in MOLDES.MOLDES)

TEMPLATES_RCPN: tuple[str, ...] = TERMOS_RCPN + MOLDES_RCPN

RE_PLACEHOLDER_DUPLO = re.compile(r"\{\{\s*([^{}#/][^{}]*?)\s*\}\}")
RE_PLACEHOLDER_SIMPLES = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")
RE_PLACEHOLDER_ARROBA = re.compile(r"@[A-Za-z_0-9]+")
RE_BLOQUEADO = re.compile(
    r"\{\{#bloqueado\s+([A-Za-z0-9_\-]+)\}\}(.*?)\{\{/bloqueado\}\}",
    re.DOTALL,
)


class EditorError(ValueError):
    """Erro de regra do editor, mensagem pronta para a tela."""


class VersaoNaoEncontrada(EditorError):
    """O id pedido não existe — a API responde 404, não 400."""


def garantir_schema(con: sqlite3.Connection) -> None:
    init_modelos_editor_schema(con)


def _sha_texto(texto: str | bytes) -> str:
    if isinstance(texto, str):
        texto = texto.encode("utf-8")
    return hashlib.sha256(texto).hexdigest()


def _eh_molde(template_id: str) -> bool:
    return (template_id or "").upper() in MOLDES.POR_CHAVE


def _area_ok(area: str) -> str:
    a = (area or "").strip().upper()
    if a != AREA_RCPN:
        raise EditorError(
            f"Área «{area}» fora do escopo do Marco 1 (só RCPN).")
    return a


def _tpl_ok(template_id: str) -> str:
    t = (template_id or "").strip().upper()
    if t not in TEMPLATES_RCPN:
        raise EditorError(
            f"«{template_id}» não é termo/molde RCPN do Marco 1.")
    return t


def _parte_ok(template_id: str, parte: str) -> str:
    p = (parte or PARTE_CORPO).strip().upper()
    if _eh_molde(template_id):
        if p != PARTE_MOLDE:
            p = PARTE_MOLDE
        return p
    if p not in PARTES_TEXTO:
        raise EditorError(f"Parte «{parte}» inválida.")
    return p


# ============================================================ catálogo

def listar_modelos_rcpn(con: sqlite3.Connection) -> list[dict]:
    """Lista os 4 termos + 3 moldes do RCPN com status de versão."""
    garantir_schema(con)
    saida: list[dict] = []
    for chave in TERMOS_RCPN:
        cat = CASA.POR_CHAVE.get(chave, {})
        pub = _versao_status(con, AREA_RCPN, chave, PARTE_CORPO, STATUS_PUBLICADA)
        rasc = _versao_status(con, AREA_RCPN, chave, PARTE_CORPO, STATUS_RASCUNHO)
        saida.append({
            "template_id": chave,
            "nome": cat.get("nome") or chave,
            "explica": cat.get("explica") or "",
            "tipo": "termo",
            "partes": list(PARTES_TEXTO),
            "tem_publicada": pub is not None,
            "tem_rascunho": rasc is not None,
            "publicada_id": pub["id"] if pub else None,
            "rascunho_id": rasc["id"] if rasc else None,
        })
    for chave in MOLDES_RCPN:
        cat = MOLDES.POR_CHAVE.get(chave, {})
        pub = _versao_status(con, AREA_RCPN, chave, PARTE_MOLDE, STATUS_PUBLICADA)
        rasc = _versao_status(con, AREA_RCPN, chave, PARTE_MOLDE, STATUS_RASCUNHO)
        saida.append({
            "template_id": chave,
            "nome": cat.get("nome") or chave,
            "explica": cat.get("explica") or "",
            "tipo": "molde",
            "partes": [PARTE_MOLDE],
            "tem_publicada": pub is not None,
            "tem_rascunho": rasc is not None,
            "publicada_id": pub["id"] if pub else None,
            "rascunho_id": rasc["id"] if rasc else None,
        })
    return saida


def _versao_status(con, area, template_id, parte, status):
    con.row_factory = sqlite3.Row
    return con.execute(
        """SELECT id, sha256, autor, criado_em, nota, status
             FROM mo_versoes
            WHERE area=? AND template_id=? AND parte=? AND status=?
            ORDER BY id DESC LIMIT 1""",
        (area, template_id, parte, status)).fetchone()


# ============================================================ vigente (hoje)

def conteudo_vigente(con: sqlite3.Connection, template_id: str,
                     parte: str = PARTE_CORPO) -> dict:
    """O que a emissão usa HOJE (mo_elementos / mo_moldes / pacote)."""
    t = _tpl_ok(template_id)
    p = _parte_ok(t, parte)
    if p == PARTE_MOLDE:
        blob = MOLDES.arquivo_que_vale(con, t)
        return {
            "template_id": t,
            "parte": p,
            "conteudo": None,
            "conteudo_blob": blob,
            "sha256": _sha_texto(blob),
            "origem": "vigente",
            "binario": True,
        }
    atrib = ELEM.atribuicao_do_ato(t)
    e = ELEM.elemento(con, atribuicao=atrib, ato=t, parte=p)
    texto = e["texto"] if isinstance(e["texto"], str) else str(e["texto"] or "")
    return {
        "template_id": t,
        "parte": p,
        "conteudo": texto,
        "conteudo_blob": None,
        "sha256": _sha_texto(texto),
        "origem": e.get("de_onde") or "vigente",
        "binario": False,
    }


def carregar(con: sqlite3.Connection, *, area: str, template_id: str,
             parte: str = PARTE_CORPO,
             qual: str = "auto",
             marcar_para_edicao: bool = False) -> dict:
    """Carrega publicada, rascunho ou vigente.

    qual: 'publicada' | 'rascunho' | 'vigente' | 'auto'
    auto = rascunho se houver, senão publicada, senão vigente.

    `marcar_para_edicao=True` (Marco 2b): aplica `marcar_bloqueados` do motor
    **só na cópia em memória** para a tela. NÃO altera `mo_versoes` nem a
    semente publicada (promessa byte a byte do Marco 1).
    """
    a = _area_ok(area)
    t = _tpl_ok(template_id)
    p = _parte_ok(t, parte)
    garantir_schema(con)
    ordem = {
        "rascunho": (STATUS_RASCUNHO,),
        "publicada": (STATUS_PUBLICADA,),
        "auto": (STATUS_RASCUNHO, STATUS_PUBLICADA),
        "vigente": (),
    }.get((qual or "auto").lower(), (STATUS_RASCUNHO, STATUS_PUBLICADA))

    out = None
    for st in ordem:
        row = _versao_status(con, a, t, p, st)
        if row:
            full = con.execute(
                "SELECT * FROM mo_versoes WHERE id=?", (row["id"],)).fetchone()
            out = _row_para_dict(full, origem=st)
            break
    if out is None:
        vig = conteudo_vigente(con, t, p)
        vig["area"] = a
        vig["status"] = None
        vig["id"] = None
        out = vig

    out.setdefault("avisos_marcacao", [])
    if marcar_para_edicao and not out.get("binario") and isinstance(out.get("conteudo"), str):
        import modelos_editor_motor as MOTOR_CLI
        avisos: list = []
        marcado, avisos = MOTOR_CLI.marcar_bloqueados(
            a, t, out["conteudo"], avisos=avisos)
        if marcado != out["conteudo"]:
            out["conteudo_armazenado"] = out["conteudo"]
            out["conteudo"] = marcado
            out["marcado_so_exibicao"] = True
        out["avisos_marcacao"] = avisos
    return out


def _row_para_dict(row, origem: str = "") -> dict:
    blob = row["conteudo_blob"]
    if blob is not None:
        blob = bytes(blob)
    return {
        "id": row["id"],
        "area": row["area"],
        "template_id": row["template_id"],
        "parte": row["parte"],
        "conteudo": row["conteudo"],
        "conteudo_blob": blob,
        "sha256": row["sha256"],
        "status": row["status"],
        "autor": row["autor"],
        "criado_em": row["criado_em"],
        "nota": row["nota"],
        "origem": origem or row["status"],
        "binario": blob is not None and row["parte"] == PARTE_MOLDE,
    }


# ============================================================ chave por área

def chave_ligada(con_ou_settings, area: str = AREA_RCPN) -> bool:
    """True se a emissão deve ler a versão publicada desta área."""
    a = (area or AREA_RCPN).strip().upper()
    chave = chave_da_area(a)
    if hasattr(con_ou_settings, "execute"):
        try:
            row = con_ou_settings.execute(
                "SELECT value FROM settings WHERE key=?", (chave,)).fetchone()
            if row is None:
                return False
            val = row[0] if not isinstance(row, sqlite3.Row) else row["value"]
            return str(val or "0").strip() == "1"
        except sqlite3.OperationalError:
            return False
    if callable(con_ou_settings):
        s = con_ou_settings()
        return str((s or {}).get(chave) or "0").strip() == "1"
    if isinstance(con_ou_settings, dict):
        return str(con_ou_settings.get(chave) or "0").strip() == "1"
    return False


def definir_chave(con: sqlite3.Connection, area: str, ligada: bool,
                  *, via_db_set=None) -> None:
    """Liga/desliga a chave. Preferir db.set_settings no app; aqui grava direto."""
    chave = chave_da_area(area)
    val = "1" if ligada else "0"
    if via_db_set:
        via_db_set({chave: val})
        return
    con.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (chave, val))


def conteudo_publicado_se_ligado(
        con: sqlite3.Connection, *, area: str, template_id: str,
        parte: str = PARTE_CORPO) -> dict | None:
    """Ponto ÚNICO de leitura da versão publicada, respeitando a chave.

    Se a chave da área estiver DESLIGADA → None (emissão fica como hoje).
    Se ligada e houver publicada → dict com conteudo/blob.
    Se ligada sem publicada → None (emissão cai no vigente).

    O motor de emissão deve chamar esta função no lugar de corpo_de /
    arquivo_que_vale quando for plugar (NÃO feito neste marco nos módulos
    do motor). Ver MARCO1_RELATORIO.md.
    """
    a = (area or "").strip().upper()
    if not chave_ligada(con, a):
        return None
    garantir_schema(con)
    t = (template_id or "").strip().upper()
    p = _parte_ok(t, parte) if t in TEMPLATES_RCPN else (parte or PARTE_CORPO).upper()
    row = _versao_status(con, a, t, p, STATUS_PUBLICADA)
    if not row:
        return None
    full = con.execute(
        "SELECT * FROM mo_versoes WHERE id=?", (row["id"],)).fetchone()
    return _row_para_dict(full, origem=STATUS_PUBLICADA)


# ============================================================ validação

def _placeholders_no_texto(texto: str) -> set[str]:
    achados: set[str] = set()
    for m in RE_PLACEHOLDER_DUPLO.finditer(texto or ""):
        achados.add(m.group(1).strip())
    for m in RE_PLACEHOLDER_SIMPLES.finditer(texto or ""):
        achados.add(m.group(1).strip())
    for m in RE_PLACEHOLDER_ARROBA.finditer(texto or ""):
        achados.add(m.group(0))
    return achados


def _vocabulario_conhecido(template_id: str, texto: str = "") -> set[str]:
    conhecidos: set[str] = set()
    from modelos_editor_serventia import placeholders_serventia, mapa_aliases
    for ph in placeholders_serventia():
        conhecidos.add(ph)
        conhecidos.add("{{" + ph + "}}")
    for alias in mapa_aliases():
        conhecidos.add(f"serventia.{alias}")

    if _eh_molde(template_id):
        try:
            import rc_certidao_odt as ODT
            conhecidos.update(ODT.valores({}, {}, {}))
        except Exception:
            pass
        especie = MOLDES.POR_CHAVE.get(template_id, {}).get("especie", "")
        mat = MOLDES.MATRICULA_DA_ESPECIE.get(especie)
        if mat:
            conhecidos.add(mat)
        return conhecidos

    try:
        for m in ELEM.legenda_do_ato(template_id, texto or CASA.padrao_de(template_id)):
            cod = m.get("codigo") or ""
            conhecidos.add(cod)
            conhecidos.add(cod.strip("{} ").strip())
            conhecidos.add(m.get("rotulo") or "")
            conhecidos.add(m.get("nome") or "")
    except Exception:
        pass
    # Aceitar qualquer placeholder que já exista no texto vigente/padrão
    try:
        padrao = CASA.padrao_de(template_id)
        conhecidos |= _placeholders_no_texto(padrao)
    except Exception:
        pass
    return {c for c in conhecidos if c}


def validar(con: sqlite3.Connection, *, area: str, template_id: str,
            parte: str, conteudo: str | None = None,
            conteudo_blob: bytes | None = None,
            get_settings: Callable | dict | None = None,
            trechos_bloqueados: list[dict] | None = None) -> dict:
    """Valida placeholder desconhecido, bloqueado adulterado, literal serventia.

    Publicar é recusado quando houver erro (erros não vazios).
    """
    t = _tpl_ok(template_id)
    p = _parte_ok(t, parte)
    erros: list[dict] = []
    avisos: list[str] = []

    texto = conteudo if conteudo is not None else ""
    if conteudo_blob and p == PARTE_MOLDE:
        try:
            with zipfile.ZipFile(io.BytesIO(conteudo_blob)) as z:
                texto = z.read("content.xml").decode("utf-8", errors="replace")
        except Exception as err:
            erros.append({
                "linha": 0, "coluna": 0, "codigo": "odt_invalido",
                "msg": f"ODT inválido: {err}",
            })
            return {"ok": False, "erros": erros, "avisos": avisos,
                    "placeholders_usados": [], "placeholders_desconhecidos": []}
        # Conferência do molde existente
        msg = MOLDES.conferir(t, conteudo_blob)
        if msg:
            erros.append({
                "linha": 0, "coluna": 0, "codigo": "molde_recusado",
                "msg": msg,
            })

    usados = sorted(_placeholders_no_texto(texto))
    conhecidos = _vocabulario_conhecido(t, texto)
    desconhecidos: list[str] = []
    for ph in usados:
        # Normalizar para comparação
        candidatos = {ph, ph.strip("@"), "{" + ph + "}", "{{" + ph + "}}",
                      "{{ " + ph + " }}", "@" + ph.lstrip("@")}
        if not (candidatos & conhecidos) and ph not in conhecidos:
            # Placeholders do próprio texto vigente são aceitos (semente)
            desconhecidos.append(ph)

    # Na semente byte-a-byte, desconhecidos do padrão vigente NÃO são erro
    # Se o placeholder está no vigente atual, aceitar
    try:
        vig = conteudo_vigente(con, t, p)
        vig_txt = vig.get("conteudo") or ""
        if vig.get("conteudo_blob"):
            try:
                with zipfile.ZipFile(io.BytesIO(vig["conteudo_blob"])) as z:
                    vig_txt = z.read("content.xml").decode("utf-8", errors="replace")
            except Exception:
                vig_txt = ""
        vig_ph = _placeholders_no_texto(vig_txt)
        desconhecidos = [d for d in desconhecidos if d not in vig_ph]
    except Exception:
        pass

    for d in desconhecidos:
        erros.append({
            "linha": 0, "coluna": 0, "codigo": "placeholder_desconhecido",
            "msg": f"Placeholder desconhecido: {d}",
        })

    # Bloqueados: compara miolos marcados com a lista do motor
    bloqueados = list(trechos_bloqueados or [])
    if not bloqueados:
        try:
            import modelos_editor_motor as MOTOR_CLI
            resp_blk = MOTOR_CLI.trechos_bloqueados(area=area, tipo=t)
            bloqueados = list(resp_blk.get("trechos") or [])
            if resp_blk.get("fonte") == "fallback" or not bloqueados:
                avisos.append(
                    "nenhum trecho bloqueado devolvido pelo motor para este modelo")
        except Exception:
            avisos.append(
                "nenhum trecho bloqueado disponível (motor ausente)")

    por_id = {str(b.get("id") or ""): b for b in bloqueados if b.get("id")}
    presentes = {m.group(1): m.group(2) for m in RE_BLOQUEADO.finditer(texto)}
    for bid, miolo in presentes.items():
        if bid not in por_id:
            erros.append({
                "linha": 0, "coluna": 0, "codigo": "bloqueado_desconhecido",
                "msg": f"Bloco bloqueado «{bid}» não está na lista do motor.",
            })
            continue
        esperado = str(por_id[bid].get("texto") or "")
        if esperado and miolo != esperado:
            erros.append({
                "linha": 0, "coluna": 0, "codigo": "bloqueado_adulterado",
                "msg": f"Trecho bloqueado «{bid}» foi alterado.",
            })

    # Literais de serventia
    if get_settings is not None:
        for lit in literais_proibidos(get_settings):
            literal = lit["literal"]
            if literal and literal in texto:
                # Se a variável correspondente já está no texto, ainda assim
                # o literal é proibido (duplicata perigosa)
                erros.append({
                    "linha": 0, "coluna": 0, "codigo": "literal_serventia",
                    "msg": (
                        f"Literal de serventia encontrado («…{literal[:40]}…»). "
                        f"Use {lit['placeholder']}."
                    ),
                })

    return {
        "ok": not erros,
        "erros": erros,
        "avisos": avisos,
        "placeholders_usados": usados,
        "placeholders_desconhecidos": desconhecidos,
    }


# ============================================================ gravar

def salvar_rascunho(con: sqlite3.Connection, *, area: str, template_id: str,
                    parte: str = PARTE_CORPO, conteudo: str | None = None,
                    conteudo_blob: bytes | None = None,
                    autor: str = "", agora: str = "",
                    nota: str = "",
                    get_settings=None,
                    trechos_bloqueados: list | None = None,
                    validar_ao_salvar: bool = True) -> dict:
    """Salva (ou substitui) o rascunho daquela parte. USER pode."""
    a = _area_ok(area)
    t = _tpl_ok(template_id)
    p = _parte_ok(t, parte)
    garantir_schema(con)

    if p == PARTE_MOLDE:
        if not conteudo_blob:
            raise EditorError("Envie o arquivo .odt do molde.")
        sha = _sha_texto(conteudo_blob)
        texto = None
        blob = conteudo_blob
    else:
        if conteudo is None:
            raise EditorError("Conteúdo texto obrigatório.")
        texto = conteudo
        blob = None
        sha = _sha_texto(texto)

    if validar_ao_salvar and p != PARTE_MOLDE:
        val = validar(
            con, area=a, template_id=t, parte=p,
            conteudo=texto, conteudo_blob=blob,
            get_settings=get_settings,
            trechos_bloqueados=trechos_bloqueados)
        # Ao salvar rascunho, só bloqueados adulterados / desconhecidos e literais
        # impedem; placeholder desconhecido vira aviso (ainda rascunho).
        graves = [e for e in val["erros"]
                  if e.get("codigo") in (
                      "bloqueado_adulterado", "bloqueado_desconhecido",
                      "literal_serventia", "odt_invalido", "molde_recusado")]
        if graves:
            raise EditorError(
                "Gravação recusada: "
                + "; ".join(e["msg"] for e in graves[:5]))

    # Arquiva rascunho anterior (histórico preserva)
    ant = _versao_status(con, a, t, p, STATUS_RASCUNHO)
    if ant:
        con.execute(
            "UPDATE mo_versoes SET status=? WHERE id=?",
            (STATUS_ARQUIVADA, ant["id"]))

    cur = con.execute(
        """INSERT INTO mo_versoes
           (area, template_id, parte, conteudo, conteudo_blob, sha256,
            status, autor, criado_em, nota)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (a, t, p, texto, blob, sha, STATUS_RASCUNHO,
         autor or None, agora or "", nota or None))
    return carregar(con, area=a, template_id=t, parte=p, qual="rascunho")


def pode_publicar(papel: str) -> bool:
    return (papel or "").upper() in ("ADMIN", "MANAGER")


def publicar(con: sqlite3.Connection, *, area: str, template_id: str,
             parte: str = PARTE_CORPO, autor: str = "", agora: str = "",
             nota: str = "", papel_usuario: str = "",
             get_settings: Callable | dict | None = None,
             trechos_bloqueados: list[dict] | None = None,
             conteudo: str | None = None,
             conteudo_blob: bytes | None = None) -> dict:
    """Publica o rascunho (ou conteúdo passado). Só ADMIN/MANAGER.

    Recusa se validação tiver erros.
    """
    if not pode_publicar(papel_usuario):
        raise EditorError(
            "Somente ADMIN ou MANAGER podem publicar uma versão.")

    a = _area_ok(area)
    t = _tpl_ok(template_id)
    p = _parte_ok(t, parte)
    garantir_schema(con)

    # Fonte: argumento explícito ou rascunho atual
    if conteudo is None and conteudo_blob is None:
        rasc = carregar(con, area=a, template_id=t, parte=p, qual="rascunho")
        if rasc.get("status") != STATUS_RASCUNHO:
            raise EditorError("Não há rascunho para publicar. Salve um antes.")
        conteudo = rasc.get("conteudo")
        conteudo_blob = rasc.get("conteudo_blob")

    val = validar(
        con, area=a, template_id=t, parte=p,
        conteudo=conteudo, conteudo_blob=conteudo_blob,
        get_settings=get_settings,
        trechos_bloqueados=trechos_bloqueados)
    if not val["ok"]:
        raise EditorError(
            "Publicação recusada: "
            + "; ".join(e["msg"] for e in val["erros"][:5]))

    if p == PARTE_MOLDE:
        sha = _sha_texto(conteudo_blob or b"")
        texto, blob = None, conteudo_blob
    else:
        texto, blob = conteudo if conteudo is not None else "", None
        sha = _sha_texto(texto)

    # Arquiva publicada anterior
    ant = _versao_status(con, a, t, p, STATUS_PUBLICADA)
    if ant:
        con.execute(
            "UPDATE mo_versoes SET status=? WHERE id=?",
            (STATUS_ARQUIVADA, ant["id"]))

    # Arquiva rascunho correspondente (vira o histórico da publicação)
    rasc = _versao_status(con, a, t, p, STATUS_RASCUNHO)
    if rasc:
        con.execute(
            "UPDATE mo_versoes SET status=? WHERE id=?",
            (STATUS_ARQUIVADA, rasc["id"]))

    con.execute(
        """INSERT INTO mo_versoes
           (area, template_id, parte, conteudo, conteudo_blob, sha256,
            status, autor, criado_em, nota)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (a, t, p, texto, blob, sha, STATUS_PUBLICADA,
         autor or None, agora or "", nota or "publicada"))
    return carregar(con, area=a, template_id=t, parte=p, qual="publicada")


def historico(con: sqlite3.Connection, *, area: str, template_id: str,
              parte: str = PARTE_CORPO, limite: int = 50) -> list[dict]:
    a = _area_ok(area)
    t = _tpl_ok(template_id)
    p = _parte_ok(t, parte)
    garantir_schema(con)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT id, area, template_id, parte, sha256, status, autor,
                  criado_em, nota, length(conteudo) AS tam_texto,
                  length(conteudo_blob) AS tam_blob
             FROM mo_versoes
            WHERE area=? AND template_id=? AND parte=?
            ORDER BY id DESC LIMIT ?""",
        (a, t, p, limite)).fetchall()
    return [dict(r) for r in rows]


def _content_xml(blob: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        return z.read("content.xml").decode("utf-8", errors="replace")


def diff_versoes(con: sqlite3.Connection, id_a: int, id_b: int) -> dict:
    """Diff textual entre duas versões. Para ODT: diff do content.xml + sha."""
    garantir_schema(con)
    con.row_factory = sqlite3.Row
    a = con.execute("SELECT * FROM mo_versoes WHERE id=?", (id_a,)).fetchone()
    b = con.execute("SELECT * FROM mo_versoes WHERE id=?", (id_b,)).fetchone()
    if not a or not b:
        raise VersaoNaoEncontrada("Versão não encontrada para diff.")

    def _texto(row):
        if row["conteudo_blob"] is not None and row["parte"] == PARTE_MOLDE:
            try:
                return _content_xml(bytes(row["conteudo_blob"]))
            except Exception as err:
                return f"[ODT ilegível: {err}]"
        return row["conteudo"] or ""

    ta, tb = _texto(a), _texto(b)
    import difflib
    linhas = list(difflib.unified_diff(
        ta.splitlines(), tb.splitlines(),
        fromfile=f"v{id_a}", tofile=f"v{id_b}", lineterm=""))
    return {
        "id_a": id_a,
        "id_b": id_b,
        "sha_a": a["sha256"],
        "sha_b": b["sha256"],
        "iguais": a["sha256"] == b["sha256"],
        "diff": "\n".join(linhas),
        "parte": a["parte"],
        "template_id": a["template_id"],
    }


# A API SEM PARAMETRO NAO RECUSA MAIS — 06/10/2026. `/api/historico` sem
# modelo e `/api/diff` sem `a`/`b` davam HTTP 400; o ensaio contra a copia da
# producao abriu as duas assim. Agora o que falta tem um padrao util: o
# historico geral da area, e as duas versoes mais recentes.

def historico_geral(con: sqlite3.Connection, *, area: str,
                    limite: int = 50) -> list[dict]:
    """Últimas versões de todos os modelos da área (sem filtrar por modelo)."""
    a = _area_ok(area)
    garantir_schema(con)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT id, area, template_id, parte, sha256, status, autor,
                  criado_em, nota, length(conteudo) AS tam_texto,
                  length(conteudo_blob) AS tam_blob
             FROM mo_versoes
            WHERE area=?
            ORDER BY id DESC LIMIT ?""",
        (a, limite)).fetchall()
    return [dict(r) for r in rows]


def par_para_diff(con: sqlite3.Connection, *, id_a: int = 0, id_b: int = 0,
                  area: str = AREA_RCPN, template_id: str = "",
                  parte: str = "") -> tuple[int, int] | None:
    """Escolhe o par (mais antiga, mais nova) quando faltam `a`/`b`.

    - `a` e `b`: o par informado;
    - só um deles: ele contra a versão anterior do mesmo modelo e parte;
    - nenhum: as duas mais recentes do modelo informado ou, sem modelo, do
      último modelo mexido na área.
    Devolve None quando ainda não há duas versões para comparar.
    """
    if id_a and id_b:
        return id_a, id_b
    garantir_schema(con)
    con.row_factory = sqlite3.Row
    um = id_b or id_a
    if um:
        row = con.execute(
            "SELECT id, area, template_id, parte FROM mo_versoes WHERE id=?",
            (um,)).fetchone()
        if not row:
            raise VersaoNaoEncontrada("Versão não encontrada para diff.")
        ant = con.execute(
            """SELECT id FROM mo_versoes
                WHERE area=? AND template_id=? AND parte=? AND id<?
                ORDER BY id DESC LIMIT 1""",
            (row["area"], row["template_id"], row["parte"], um)).fetchone()
        return (int(ant["id"]), um) if ant else None
    a = _area_ok(area)
    if template_id:
        t = _tpl_ok(template_id)
        p = _parte_ok(t, parte)
    else:
        ultima = con.execute(
            """SELECT template_id, parte FROM mo_versoes WHERE area=?
                ORDER BY id DESC LIMIT 1""", (a,)).fetchone()
        if not ultima:
            return None
        t, p = ultima["template_id"], ultima["parte"]
    duas = con.execute(
        """SELECT id FROM mo_versoes
            WHERE area=? AND template_id=? AND parte=?
            ORDER BY id DESC LIMIT 2""", (a, t, p)).fetchall()
    if len(duas) < 2:
        return None
    return int(duas[1]["id"]), int(duas[0]["id"])


def restaurar_como_rascunho(con: sqlite3.Connection, versao_id: int, *,
                            autor: str = "", agora: str = "") -> dict:
    """Copia uma versão antiga como novo rascunho."""
    garantir_schema(con)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM mo_versoes WHERE id=?", (versao_id,)).fetchone()
    if not row:
        raise EditorError("Versão não encontrada.")
    return salvar_rascunho(
        con, area=row["area"], template_id=row["template_id"],
        parte=row["parte"],
        conteudo=row["conteudo"],
        conteudo_blob=bytes(row["conteudo_blob"]) if row["conteudo_blob"] else None,
        autor=autor, agora=agora,
        nota=f"restaurada da versão {versao_id}")


def semear_v1(con: sqlite3.Connection, *, area: str = AREA_RCPN,
              template_id: str | None = None,
              autor: str = "sistema", agora: str = "",
              forcar: bool = False) -> list[dict]:
    """Semeia a primeira versão publicada a partir do conteúdo vigente.

    Byte a byte igual ao que sai hoje. Se já houver publicada e forcar=False,
    pula. Retorna lista do que foi semeado.

    Marco 2b: a semente **não** grava marcadores `{{#bloqueado}}` — a
    marcação é aplicada só na exibição (`carregar(..., marcar_para_edicao=True)`),
    para não quebrar a promessa byte a byte nem alterar publicadas.
    """
    a = _area_ok(area)
    garantir_schema(con)
    alvos = [_tpl_ok(template_id)] if template_id else list(TEMPLATES_RCPN)
    feitos: list[dict] = []
    for t in alvos:
        partes = [PARTE_MOLDE] if _eh_molde(t) else list(PARTES_TEXTO)
        for p in partes:
            # Encerramento/rodapé vazios no vigente: ainda assim semeamos o corpo;
            # para enc/rod só semeia se houver texto
            vig = conteudo_vigente(con, t, p)
            if p != PARTE_CORPO and p != PARTE_MOLDE:
                if not (vig.get("conteudo") or "").strip():
                    continue
            ant = _versao_status(con, a, t, p, STATUS_PUBLICADA)
            if ant and not forcar:
                feitos.append({
                    "template_id": t, "parte": p, "acao": "ja_existia",
                    "id": ant["id"], "sha256": ant["sha256"],
                })
                continue
            if ant and forcar:
                con.execute(
                    "UPDATE mo_versoes SET status=? WHERE id=?",
                    (STATUS_ARQUIVADA, ant["id"]))
            sha = vig["sha256"]
            # Conferência byte a byte
            if p == PARTE_MOLDE:
                assert _sha_texto(vig["conteudo_blob"]) == sha
            else:
                assert _sha_texto(vig["conteudo"] or "") == sha
            cur = con.execute(
                """INSERT INTO mo_versoes
                   (area, template_id, parte, conteudo, conteudo_blob, sha256,
                    status, autor, criado_em, nota)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (a, t, p, vig.get("conteudo"), vig.get("conteudo_blob"),
                 sha, STATUS_PUBLICADA, autor, agora or "",
                 "semente v1 = vigente"))
            vid = cur.lastrowid
            # Validar igualdade
            row = con.execute(
                "SELECT * FROM mo_versoes WHERE id=?", (vid,)).fetchone()
            if p == PARTE_MOLDE:
                assert bytes(row["conteudo_blob"]) == vig["conteudo_blob"]
            else:
                assert (row["conteudo"] or "") == (vig.get("conteudo") or "")
            feitos.append({
                "template_id": t, "parte": p, "acao": "semeada",
                "id": vid, "sha256": sha,
            })
    return feitos
