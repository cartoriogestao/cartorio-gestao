"""Comprovante do aceite de um arquivo pelo portal da CRA, sem novo envio."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import afirmacoes_expressas as AFX
from bd_nativo import banco
from protesto_aviso import ASSINATURA_DO_COMPROVANTE, LIMITE_DO_COMPROVANTE

ENTIDADE = "PT_CRA_ENVIO_MANUAL"


class EnvioManualError(ValueError):
    """O comprovante ou o estado do arquivo não permite registrar o aceite."""


def dados_do_envio(arquivo: dict) -> dict | None:
    """Identifica o registro manual sem confundi-lo com uma resposta da API."""
    try:
        dados = json.loads(arquivo.get("cra_envio_resumo") or "null")
    except (TypeError, ValueError):
        return None
    return dados if isinstance(dados, dict) and dados.get("meio") == "PORTAL" else None


def registrar(con, retorno_id: int, *, nome: str, conteudo: bytes,
              pasta_de_arquivos, agora: str, usuario: str,
              usuario_id: int, afirmo: bool, afirmacao: str, robo: bool = False) -> dict:
    """Guarda prova e autoria do aceite. Não faz conexão com a CRA.

    O retorno e o andamento são comprovados separadamente. Um arquivo antigo
    cujos atos voltaram à fila, ou que contém ato desfeito, não pode ser dado
    por informado. A declaração do aceite é de quem conferiu o portal.
    """
    texto = AFX.validar(afirmo, afirmacao, robo=robo,
                        por_que="Confirme que a CRA aceitou este arquivo no portal.")
    bd = banco(con)
    linha = bd.um("SELECT * FROM pt_retornos WHERE id=%s FOR UPDATE", (int(retorno_id),))
    if not linha:
        raise EnvioManualError("O arquivo não existe.")
    if linha.get("cra_enviado_em"):
        raise EnvioManualError("Este arquivo já tem envio registrado; confira o registro existente.")
    ambiente = str(linha.get("cra_enviado_ambiente") or "PRODUCAO")
    if ambiente != "PRODUCAO":
        raise EnvioManualError("Só um arquivo de produção pode receber este comprovante.")
    if linha["tipo"] not in {"SDTBFOCRT", "SDTBFORTP", "SDTBFOAND"}:
        raise EnvioManualError("Este tipo de arquivo não tem registro de aceite na CRA.")
    if linha["tipo"] != "SDTBFOCRT":
        atos = bd.ler("SELECT cancelado FROM pt_atos WHERE retorno_id=%s", (retorno_id,))
        if not atos or any(a["cancelado"] for a in atos):
            raise EnvioManualError("Os atos deste arquivo foram devolvidos à fila ou desfeitos; confira o retorno.")
    nome_limpo = Path(str(nome or "").replace("\\", "/")).name
    ext = Path(nome_limpo).suffix.lower()
    conteudo = bytes(conteudo or b"")
    assinatura = ASSINATURA_DO_COMPROVANTE.get(ext)
    if not assinatura or not conteudo.startswith(assinatura):
        raise EnvioManualError("Anexe o comprovante do aceite em PDF, PNG ou JPG de verdade.")
    if len(conteudo) > LIMITE_DO_COMPROVANTE:
        raise EnvioManualError("O comprovante excede o tamanho permitido.")
    sha = hashlib.sha256(conteudo).hexdigest()
    extensao = ".pdf" if conteudo.startswith(b"%PDF") else (
        ".png" if conteudo.startswith(b"\x89PNG") else ".jpg")
    pasta = Path(pasta_de_arquivos) / "Protesto" / "Cra" / "Comprovantes"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / (uuid4().hex + extensao)
    arquivo.write_bytes(conteudo)
    try:
        anexo = bd.escrever(
            """INSERT INTO attachments(entity_type,entity_id,original_name,stored_name,
                   stored_path,sha256,size_bytes,description,uploaded_by,uploaded_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (ENTIDADE, int(retorno_id), nome_limpo, arquivo.name, str(arquivo), sha,
             len(conteudo), "Comprovante do aceite no portal da CRA", usuario_id, agora))[0]["id"]
        resumo = {"meio": "PORTAL", "anexo_id": anexo, "afirmacao": texto,
                  "sha256_comprovante": sha,
                  "recusa_anterior": {"em": linha.get("cra_recusado_em"),
                                      "codigo": linha.get("cra_recusa_codigo"),
                                      "motivo": linha.get("cra_recusa_motivo")}}
        bd.escrever(
            """UPDATE pt_retornos SET cra_enviado_em=%s,cra_enviado_por=%s,
                   cra_enviado_ambiente='PRODUCAO',cra_envio_resumo=%s,
                   cra_envio_erro=NULL,cra_recusado_em=NULL,cra_recusa_codigo=NULL,
                   cra_recusa_motivo=NULL WHERE id=%s""",
            (agora, usuario, json.dumps(resumo, ensure_ascii=False), int(retorno_id)))
    except BaseException:
        arquivo.unlink(missing_ok=True)
        raise
    return {"retorno_id": int(retorno_id), "anexo_id": int(anexo),
            "nome_arquivo": linha["nome_arquivo"], "afirmacao": texto}
