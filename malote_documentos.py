"""PDFs do Malote ligados aos alertas existentes, sem expediente ou tarefa.

Recebe somente PDF com capa do Malote. O código de rastreabilidade precisa
constar na procedência dos alertas. O cliente não escolhe caminho no servidor.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import tempfile
from pathlib import Path

from bd_nativo import banco

LIMITE = 16 * 1024 * 1024
TIPO = "MALOTE_FRAUDE"
_CODIGO = re.compile(r"\d{14}\Z")


class DocumentoMaloteError(ValueError):
    """Recusa de documento com explicação para a tela."""


def examinar(con, conteudo: bytes, grupo: str) -> dict:
    """Valida o original e identifica os alertas da mesma comunicação. Só lê."""
    from pypdf import PdfReader
    from malote_agente import ler_capa
    if not _CODIGO.fullmatch(grupo or ""):
        raise DocumentoMaloteError("Informe os 14 dígitos do código principal do Malote.")
    if not conteudo or len(conteudo) > LIMITE or not conteudo.startswith(b"%PDF-"):
        raise DocumentoMaloteError("Envie um PDF de até 16 MB, como foi recebido do Malote.")
    try:
        pdf = PdfReader(io.BytesIO(conteudo))
        if pdf.is_encrypted or not pdf.pages:
            raise ValueError("PDF protegido ou vazio")
        capa = ler_capa(pdf.pages[0].extract_text() or "") or {}
    except Exception as erro:
        raise DocumentoMaloteError("O PDF não abre ou sua capa não pode ser lida.") from erro
    codigo = str(capa.get("codigo") or "")
    if not _CODIGO.fullmatch(codigo):
        raise DocumentoMaloteError("Não foi encontrada uma capa válida do Malote neste PDF.")
    # Não basta conter um pedaço do número. Principal E anexo devem estar na
    # procedência da mesma comunicação; não se liga um PDF a outro caso.
    linhas = banco(con).ler("SELECT id, origem FROM fr_alertas WHERE origem LIKE %s", ("%" + grupo + "%",))
    alertas = [int(r["id"]) for r in linhas
               if grupo in re.findall(r"(?<!\d)\d{14}(?!\d)", r["origem"] or "")
               and codigo in re.findall(r"(?<!\d)\d{14}(?!\d)", r["origem"] or "")]
    if not alertas:
        raise DocumentoMaloteError("O código do PDF não consta na origem dos alertas desta comunicação. Confira a referência.")
    return {"codigo": codigo, "grupo": grupo, "sha256": hashlib.sha256(conteudo).hexdigest(),
            "size_bytes": len(conteudo), "alertas": alertas, "paginas": len(pdf.pages)}


def vincular(con, info: dict, *, usuario_id: int, agora: str) -> list[int]:
    """Liga o mesmo arquivo aos alertas, uma vez por hash. Transação do chamador."""
    bd = banco(con)
    bd.travar("malote.anexos." + info["sha256"])
    ids = []
    for aid in info["alertas"]:
        existe = bd.um("SELECT id FROM attachments WHERE entity_type=%s AND entity_id=%s AND sha256=%s",
                       (TIPO, aid, info["sha256"]))
        if existe:
            ids.append(int(existe["id"]))
            continue
        novo = bd.escrever(
            "INSERT INTO attachments (entity_type,entity_id,original_name,stored_name,stored_path,sha256,"
            "size_bytes,description,uploaded_by,uploaded_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (TIPO, aid, info["original_name"], info["stored_name"], info["stored_path"], info["sha256"],
             info["size_bytes"], "Comunicação recebida pelo Malote " + info["codigo"], usuario_id, agora))
        ids.append(int(novo[0]["id"]))
    return ids


def receber(con, conteudo: bytes, grupo: str, *, raiz: Path, usuario_id: int, agora: str) -> dict:
    """Arquiva o original e junta aos alertas existentes. Não inclui pessoas."""
    bd = banco(con)
    bd.travar("malote.documentos." + str(grupo))
    info = examinar(con, conteudo, grupo)
    pasta = Path(raiz) / "malote" / "fraudes" / grupo
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / (info["sha256"] + ".pdf")
    if alvo.exists():
        if hashlib.sha256(alvo.read_bytes()).hexdigest() != info["sha256"]:
            raise DocumentoMaloteError("O arquivo guardado diverge do hash. Peça conferência antes de repetir.")
    else:
        fd, nome = tempfile.mkstemp(prefix=".recebendo-", dir=pasta)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(conteudo)
                f.flush()
                os.fsync(f.fileno())
            os.replace(nome, alvo)
        finally:
            Path(nome).unlink(missing_ok=True)
    info.update(original_name="MALOTE_" + info["codigo"] + ".pdf", stored_name=alvo.name, stored_path=str(alvo))
    ids = vincular(con, info, usuario_id=usuario_id, agora=agora)
    # Arquivo por conteúdo: numa falha de banco ele fica para a retomada,
    # nunca se apaga um PDF que outra inclusão já possa estar usando.
    return {"codigo": info["codigo"], "grupo": grupo, "sha256": info["sha256"],
            "size_bytes": len(conteudo), "alertas": len(info["alertas"]), "anexos": ids}


def anexos_da_lista(con, alerta_ids: list[int]) -> dict[int, list[dict]]:
    """Os PDFs oferecidos pela própria lista, numa consulta só. Só lê."""
    if not alerta_ids:
        return {}
    rows = banco(con).ler("SELECT id,entity_id,original_name,sha256 FROM attachments "
                         "WHERE entity_type=%s AND entity_id=ANY(%s) ORDER BY id", (TIPO, alerta_ids))
    saida = {}
    for r in rows:
        saida.setdefault(int(r["entity_id"]), []).append(r)
    return saida
