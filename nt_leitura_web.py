"""As telas da leitura de documentos do balcão das Notas — `nt_leitura_documentos`.

O balcão anexa o RG, a CIN, a CNH, o CRV, o ATPV ou o CRLV; a IA lê; e a tela
de onde o botão saiu — o cartão de autógrafo, o reconhecimento de firma de
veículo, a comunicação de venda — volta PREENCHIDA, como rascunho, com o que
ficou em dúvida destacado e a caixa «conferi com o original» para marcar. É o
caminho do Registro Civil (`rc_leitura_web`), com o mesmo motor e o mesmo
registro de uso; nenhuma destas rotas abre cartão, reconhece firma ou sela.

«autorizo ia sem mascara. trabalharemos com o prazo de retencao de 30 dias da
 api» — o oficial, 26/10/2026. A tela repete isso ao lado do botão de ler.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import leitura_ia as LIA
import nt_leitura_documentos as NTL

#: QUEM LÊ: quem atende no balcão das Notas. O AUDITOR não pratica ato, e a
#: leitura traz documento inteiro de cliente.
QUEM_LE = ("ADMIN", "MANAGER", "USER")
#: Quem vê a leitura de OUTRA pessoa: quem responde pela casa.
QUEM_VE_TODAS = ("ADMIN", "MANAGER")

FINALIDADE = "nt_leitura"


def leitura_pedida(app, db, destino: str) -> dict | None:
    """A leitura que o endereço ou o formulário pedem (`leitura_id`), se é
    deste destino e quem está na tela pode vê-la. SÓ LÊ. É o que as telas do
    cartão, do reconhecimento e da comunicação chamam para se preencher."""
    from flask import request
    numero = request.values.get("leitura_id")
    if not numero:
        return None
    with db.connect() as con:
        return NTL.para_a_tela(con, numero, destino=destino,
                               user_id=app.extensions["usuario_id"](),
                               ve_todas=app.extensions["usuario_papel"]() in QUEM_VE_TODAS)


def recusa_da_conferencia(app, db, destino: str) -> str | None:
    """Antes de gravar: o formulário veio da leitura e a caixa da conferência
    não foi marcada? Então a frase da recusa. SÓ LÊ. Leitura que não é de
    quem grava também é recusada — o número no formulário veio de fora."""
    from flask import request
    numero = (request.form.get("leitura_id") or "").strip()
    if not numero:
        return None
    if leitura_pedida(app, db, destino) is None:
        return (f"A leitura nº {numero} não é desta tela ou não é sua — apague o "
                "número e preencha à mão, ou leia o documento de novo.")
    return NTL.recusa_sem_conferencia(numero, request.form.get("conferi_leitura"))


def marcar_usada(app, db, audit, destino: str, *, tabela: str, ato_id: int) -> None:
    """Depois de gravar: a leitura conferida entrou neste ato. ESCREVE só a
    marca na leitura, e a auditoria diz quem conferiu."""
    leitura = leitura_pedida(app, db, destino)
    if leitura is None:
        return
    quem = app.extensions["usuario_nome"]()
    with db.transaction() as con:
        NTL.marcar_usada(con, leitura["id"], tabela=tabela, ato_id=int(ato_id),
                         agora=db.now(), por=quem)
    audit("NT_LEITURA_CONFERIDA_E_USADA", "nt_leituras", leitura["id"],
          {"destino": destino, "tabela": tabela, "ato_id": int(ato_id),
           "conferida_por": quem})


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    """Pendura as telas da leitura de documentos das Notas no app já construído."""
    from flask import abort, flash, redirect, render_template, request, url_for

    from storage import save_upload

    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]
    usuario_id = app.extensions["usuario_id"]

    def pasta_de_dados() -> Path:
        return Path(app.config["DATA_DIR"])

    def _tela(destino: str, leitura: dict | None = None, **extra: Any) -> str:
        """O endereço da tela de onde a leitura saiu, preenchida por ela."""
        campos = ((leitura or {}).get("sugestao") or {}).get("campos") or {}
        lid = {"leitura_id": leitura["id"]} if leitura else {}
        if destino == "CARTAO":
            busca = {"busca": campos["nome"]} if campos.get("nome") else {}
            return url_for("notas_cartoes", **busca, **lid)
        if destino == "RECONHECIMENTO":
            busca = {"busca": campos["busca"]} if campos.get("busca") else {}
            return url_for("notas_reconhecimento", **busca, **lid)
        return url_for("notas_veiculos", **lid, **extra)

    @app.route("/notas/leitura/ler", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LE)
    def notas_leitura_ler():
        """O botão «Ler documento por IA» das três telas: guarda os anexos,
        manda ler e volta à tela de onde saiu, preenchida. ESCREVE só a
        leitura e os anexos — não abre cartão, não reconhece, não sela."""
        import agente_provedores as AP
        import ia_uso as USO
        destino = (request.form.get("destino") or "").upper()
        extra = {}
        if (request.form.get("reconhecimento_id") or "").strip().isdigit():
            extra["reconhecimento_id"] = request.form["reconhecimento_id"].strip()
        if destino not in NTL.DESTINOS:
            abort(400)
        enviados = [f for f in request.files.getlist("arquivos") if f and f.filename]
        if not enviados:
            flash("Anexe o documento — o PDF digitalizado ou as fotos.", "danger")
            return redirect(_tela(destino, **extra))
        if not AP.tem_chave(pasta_de_dados(), LIA.PROVEDOR):
            flash("A chave da API da Claude não está configurada — a leitura não tem "
                  "com quem falar. Ela se configura em Ajuda → configurar.", "danger")
            return redirect(_tela(destino, **extra))
        with db.connect() as con:
            passou = USO.passou_do_teto(con, FINALIDADE)
            em_uso = LIA.modelos(con)
        if passou:
            flash(passou, "danger")
            return redirect(_tela(destino, **extra))
        with db.transaction() as con:
            leitura_id = NTL.abrir(con, destino=destino, agora=db.now(),
                                   por=usuario_nome(), por_id=usuario_id())
        pasta_arquivos = (app.extensions["archive_root"]() / "notas" / "leituras"
                          / f"leitura_{leitura_id}")
        arquivos = []
        for f in enviados:
            info = save_upload(f, pasta_arquivos)
            anexo_id = db.add_attachment("NT_LEITURA", leitura_id, info, usuario_id(),
                                         "documento anexado para a leitura por IA")
            arquivos.append({"caminho": info["stored_path"], "nome": info["original_name"],
                             "attachment_id": anexo_id, "sha256": info["sha256"]})
        lido, erro = None, ""
        try:
            # A REDE, FORA DE TRANSAÇÃO, e o REGISTRO DE USO preso ao transporte
            # (LF01): finalidade, módulo, quem, a leitura — e que subiu SEM
            # máscara, por decisão do oficial em 26/10/2026.
            conversar = functools.partial(
                AP.conversar, modulo="nt_leitura_web", finalidade="nt_leitura",
                usuario=usuario_nome(), atribuicao="NOTAS",
                referencia=f"nt_leituras:{leitura_id}", mascarado=False)
            lido = NTL.ler(conversar, pasta_de_dados(), em_uso, arquivos, destino=destino)
        except LIA.LeituraError as recusa:
            erro = str(recusa)
        except AP.AgenteError as falha:
            erro = f"A IA não respondeu: {falha}"
        except (OSError, ValueError) as falha:
            # Arquivo que não abre como imagem (o PIL levanta
            # `UnidentifiedImageError`, que é `OSError`) — 27/10/2026: subia cru,
            # a tela dava HTTP 500 e a leitura ficava «LENDO» para sempre.
            erro = (f"Um dos arquivos não pôde ser aberto ({type(falha).__name__}). "
                    f"Confira se é uma foto ou um PDF legível.")
        with db.transaction() as con:
            NTL.concluir(con, leitura_id, arquivos=arquivos, lido=lido, erro=erro)
            leitura = NTL.uma(con, leitura_id)
        audit("NT_LEITURA_DE_DOCUMENTOS", "nt_leituras", leitura_id,
              {"destino": destino, "arquivos": [a["nome"] for a in arquivos],
               "sem_mascara": True, "retencao_dias": LIA.RETENCAO_DIAS,
               "custo_estimado": leitura.get("custo_estimado"),
               "erro": leitura.get("erro") or None})
        if leitura.get("erro"):
            flash(f"A leitura nº {leitura_id} não terminou: {leitura['erro']} Os anexos "
                  "ficaram guardados nela; preencha à mão.", "danger")
            return redirect(_tela(destino, **extra))
        flash(f"Os campos foram preenchidos pela leitura nº {leitura_id}. Confira cada um "
              "com o documento original antes de gravar — a leitura adiantou a "
              "digitação, e não decidiu nada.", "warning")
        return redirect(_tela(destino, leitura, **extra))

    def _pode_ver(leitura: dict) -> bool:
        return (usuario_papel() in QUEM_VE_TODAS
                or NTL.e_de(leitura, user_id=usuario_id()))

    @app.route("/notas/leituras")
    @login_required
    @roles_required(*QUEM_LE)
    def notas_leituras():
        """As leituras feitas — o registro do que saiu da casa. SÓ LÊ. O balcão
        vê as suas; quem responde pela casa vê todas."""
        with db.connect() as con:
            leituras = NTL.lista(con, so_de=None if usuario_papel() in QUEM_VE_TODAS
                                 else usuario_id())
        return render_template("notas_leituras.html", leituras=leituras,
                               destinos=NTL.DESTINOS, aviso=NTL.AVISO_DA_RETENCAO,
                               decisao=NTL.DECISAO_DO_OFICIAL)

    @app.route("/notas/leitura/<int:leitura_id>")
    @login_required
    @roles_required(*QUEM_LE)
    def notas_leitura_ficha(leitura_id: int):
        """O que foi lido, documento por documento, o que não fecha, e o que
        saiu da casa. A de outra pessoa responde como a que não existe."""
        with db.connect() as con:
            leitura = NTL.uma(con, leitura_id)
        if leitura is None or not _pode_ver(leitura):
            flash(f"Não há leitura nº {leitura_id}.", "danger")
            return redirect(url_for("notas_leituras"))
        voltar = _tela(leitura["destino"], leitura) if leitura["situacao"] == "LIDA" else None
        return render_template("notas_leitura_ficha.html", leitura=leitura,
                               tipos=NTL.TIPOS, destinos=NTL.DESTINOS, voltar=voltar,
                               base_legal=NTL.BASE_LEGAL, o_que_sai=NTL.O_QUE_SAI,
                               aviso=NTL.AVISO_DA_RETENCAO, zdr=LIA.ZERO_DATA_RETENTION,
                               decisao=NTL.DECISAO_DO_OFICIAL)

    # O que os modelos de tela das três telas precisam para desenhar o botão de
    # ler e o quadro da conferência (`_leitura_notas.html`).
    @app.context_processor
    def _leitura_notas_no_contexto():
        return {"nt_leitura_aviso": NTL.AVISO_DA_RETENCAO,
                "nt_leitura_decisao": NTL.DECISAO_DO_OFICIAL,
                "nt_leitura_frase": NTL.FRASE_DA_CONFERENCIA,
                "nt_leitura_teto": LIA.MAXIMO_DE_PAGINAS}
