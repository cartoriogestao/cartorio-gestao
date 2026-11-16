"""O arquivo que o cliente mandou pelo WhatsApp vai para a tarefa ou para o protocolo.

O escrevente do WhatsApp diz ao cliente que recebeu o documento e que o
escrevente vai conferir. Até 15/11/2026 o arquivo ficava só na conversa
(`wa_midia`, `<arquivos>/whatsapp/AAAA-MM/`): quem abria a tarefa ou o protocolo
não o via, e baixava e subia de novo à mão.

QUEM ANEXA É A PESSOA, NA TELA
    A IA não lê o arquivo nem decide onde ele vai. O escrevente escolhe, na
    conversa, o arquivo e o destino: a tarefa do pedido, ou o protocolo do Caixa
    que ele ligou ao pedido (`wa_pedido.vincular_protocolo`).

SEMPRE CÓPIA
    O arquivo é copiado para a pasta do destino — a mesma que o anexo feito à mão
    usaria. Apagar o anexo não toca a mensagem, e o original da conversa não muda.

A RÉGUA DO PROTOCOLO VALE AQUI
    No protocolo só entra PDF, JPG ou PNG, conferido pelo começo do arquivo, como
    no anexo feito na tela do Caixa (`protocolo_documentos.conferir_arquivo`). A
    casa não tem antivírus: o arquivo não é aberto nem convertido.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from bd_nativo import banco

import wa_midia as MIDIA
import wa_pedido as PEDIDO

TAREFA = "tarefa"
PROTOCOLO = "protocolo"
DESTINOS = (TAREFA, PROTOCOLO)
_TIPOS_COM_ARQUIVO = ("image", "document", "video", "audio", "voice", "sticker")


class AnexoErro(ValueError):
    """Anexo recusado. Mensagem pronta para a tela."""


def da_conversa(con: Any, conversa_id: int, *, limite: int = 20) -> list[dict]:
    """Os arquivos que o cliente mandou nesta conversa e estão guardados. SÓ LÊ."""
    return [dict(m) for m in banco(con).ler(
        """SELECT id, tipo, arquivo_nome, arquivo_mime, arquivo_bytes, criado_em
             FROM wa_mensagem
            WHERE conversa_id=%s AND direcao='in' AND arquivo_caminho IS NOT NULL
            ORDER BY id DESC LIMIT %s""", (int(conversa_id), int(limite)))]


def _nome(m: dict) -> str:
    nome = str(m.get("arquivo_nome") or "").strip()
    nome = re.sub(r"[^\w.\- ]", "_", Path(nome).name)[:120].strip(" .")
    if not nome:
        nome = f"whatsapp-{int(m['id'])}{Path(str(m.get('arquivo_caminho') or '')).suffix}"
    return nome


def _ler(con: Any, mensagem_id: int, pedido_id: int) -> tuple[dict, dict, bytes]:
    bd = banco(con)
    pedido = bd.um("SELECT * FROM wa_pedido WHERE id=%s", (int(pedido_id),))
    if not pedido:
        raise AnexoErro("Esse pedido não existe.")
    m = bd.um("SELECT * FROM wa_mensagem WHERE id=%s", (int(mensagem_id),))
    if (not m or int(m["conversa_id"]) != int(pedido["conversa_id"])
            or m.get("direcao") != "in" or (m.get("tipo") or "") not in _TIPOS_COM_ARQUIVO):
        raise AnexoErro("Esse arquivo não é desta conversa.")
    guardado = MIDIA.bytes_guardados(dict(m))
    if not guardado:
        raise AnexoErro("O arquivo não está guardado (ou mudou desde que chegou). Peça "
                        "ao cliente para mandar de novo.")
    return dict(pedido), dict(m), guardado[0]


def _copiar(dados: bytes, nome: str, pasta: Path) -> dict:
    from storage import unique_path
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = unique_path(pasta, nome)
    caminho.write_bytes(dados)
    return {"original_name": nome, "stored_name": caminho.name,
            "stored_path": str(caminho.resolve()),
            "sha256": hashlib.sha256(dados).hexdigest(), "size_bytes": len(dados)}


def anexar(db: Any, mensagem_id: int, pedido_id: int, *, destino: str, usuario_id: int,
           raiz: Any, agora: str, descricao: str = "") -> dict:
    """Copia o arquivo da conversa para a tarefa ou o protocolo do pedido. ESCREVE.

    Devolve {"destino", "anexo_id", "nome"}. Não fala com a rede."""
    if destino not in DESTINOS:
        raise AnexoErro("Escolha anexar à tarefa ou ao protocolo.")
    with db.connect() as con:
        pedido, m, dados = _ler(con, mensagem_id, pedido_id)
        tarefa = banco(con).um(
            "SELECT id, sector FROM tasks WHERE source_ref=%s ORDER BY id DESC LIMIT 1",
            (f"wa_pedido:{int(pedido['id'])}",))
        protocolo = (banco(con).um("SELECT id, numero FROM cx_protocolos WHERE id=%s",
                                   (int(pedido["protocolo_id"]),))
                     if pedido.get("protocolo_id") else None)
    nome = _nome(m)
    texto = (" ".join(str(descricao or "").split())[:200]
             or f"Recebido pelo WhatsApp do cliente (conversa nº {int(pedido['conversa_id'])})")
    if destino == TAREFA:
        if not tarefa:
            raise AnexoErro("Este pedido não tem tarefa aberta.")
        from storage import safe_component
        pasta = (Path(raiz) / "Evidencias" / safe_component(tarefa.get("sector") or "Geral")
                 / f"Tarefa-{int(tarefa['id']):05d}")
        info = _copiar(dados, nome, pasta)
        anexo = db.add_attachment("TASK", int(tarefa["id"]), info, int(usuario_id), texto)
        db.add_task_note(int(tarefa["id"]), int(usuario_id),
                         f"Arquivo do WhatsApp anexado: {nome} (SHA-256 {info['sha256']})")
        return {"destino": TAREFA, "anexo_id": int(anexo), "nome": nome}
    import protocolo_documentos as PDOC
    if not protocolo:
        raise AnexoErro("Ligue o pedido ao protocolo do Caixa antes de anexar a ele.")
    try:
        PDOC.conferir_arquivo(nome, dados[:16], len(dados))
    except PDOC.DocumentoError as erro:
        raise AnexoErro(str(erro)) from erro
    info = _copiar(dados, nome, PDOC.pasta_de_qualificacao(raiz, protocolo["numero"]))
    try:
        with db.transaction() as con:
            anexo = PDOC.registrar(con, int(protocolo["id"]), info, tipo="OUTRO",
                                   descricao=texto, usuario_id=usuario_id, agora=agora)
    except PDOC.DocumentoError as erro:
        Path(info["stored_path"]).unlink(missing_ok=True)     # a cópia que não entrou sai
        raise AnexoErro(str(erro)) from erro
    except Exception:
        Path(info["stored_path"]).unlink(missing_ok=True)
        raise
    return {"destino": PROTOCOLO, "anexo_id": int(anexo), "nome": nome,
            "protocolo": protocolo["numero"]}
