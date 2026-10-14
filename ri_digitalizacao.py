"""Digitalizacao oficial da matricula do RI — arquivo atual e certidao por reproducao.

O QUE ISTO E
    A serventia guarda, por matricula, UM arquivo oficial de digitalizacao
    (PDF ou imagem multipagina). O balcao atualiza esse arquivo na ficha.
    Na certidao de inteiro teor, quem emite escolhe:

      - DIGITALIZACAO: reproducao pagina a pagina + selo de certidao ao final;
      - TEXTO: o modelo RI_CERTIDAO com o teor extraido (livros antigos /
        manuscritos grandes), como ja era.

    O arquivo tambem fica marcado como pendente de envio ao ONR. Este modulo
    NAO transmite nada: so prepara a fila local ate a integracao existir.

POR QUE NAO REUSAR so `ri_imagens`
    `ri_imagens` e o acervo importado do E-Oficio (paginas soltas no disco).
    A digitalizacao OFICIAL e o arquivo que o balcao confirma hoje — pode ser
    uma nova varredura completa. Sao fontes diferentes; misturar os dois
    faria a certidao sair com pagina antiga sem ninguem perceber.
"""
from __future__ import annotations

import io
import shutil
from datetime import datetime
from pathlib import Path

from storage import hash_file, safe_component, unique_path

EXTENSOES_OK = {".pdf", ".tif", ".tiff", ".png", ".jpg", ".jpeg"}


def pasta_da_matricula(raiz_arquivos: Path, matricula_id: int) -> Path:
    """Onde mora a digitalizacao desta matricula (e o historico)."""
    return Path(raiz_arquivos) / "ri" / "digitalizacoes" / str(int(matricula_id))


def pasta_snapshot_certidao(raiz_arquivos: Path, certidao_id: int) -> Path:
    """Copia congelada usada na impressao da certidao ja emitida."""
    return Path(raiz_arquivos) / "ri" / "certidoes" / str(int(certidao_id))


def raiz_arquivos(db) -> Path:
    """Mesma regra dos documentos de prenotacao: archive_root ou ao lado do DB."""
    configurada = (db.get_setting("archive_root", "") or "").strip()
    if configurada:
        return Path(configurada)
    return Path(db.db_path).parent / "arquivos"



def _gravar_arquivo_estavel(pasta: Path, ext: str, arquivo) -> Path:
    """Grava o upload em tual{ext}, tolerando trava WinError 32.

    HOTFIX-2026-10-06-01. Ordem:
      1) grava em tmp na mesma pasta;
      2) tenta apagar o atual e renomear o tmp (caminho preferido);
      3) se o atual estiver travado para delete, sobrescreve o conteudo (wb);
      4) se nem isso der, aponta para um nome novo com carimbo.
    """
    import time as _time
    estavel = pasta / f"atual{ext}"
    tmp = unique_path(pasta, f".upload-tmp{ext}")
    arquivo.save(tmp)
    if not estavel.exists():
        tmp.replace(estavel)
        return estavel
    for i in range(5):
        try:
            estavel.unlink()
            tmp.replace(estavel)
            return estavel
        except PermissionError:
            _time.sleep(0.2 * (i + 1))
    try:
        with open(estavel, "wb") as saida, open(tmp, "rb") as entrada:
            shutil.copyfileobj(entrada, saida)
        try:
            tmp.unlink()
        except OSError:
            pass
        return estavel
    except PermissionError:
        pass
    novo = unique_path(
        pasta, f"atual-{datetime.now().strftime('%Y%m%d-%H%M%S')}{ext}")
    try:
        tmp.replace(novo)
    except OSError:
        shutil.copy2(tmp, novo)
        try:
            tmp.unlink()
        except OSError:
            pass
    return novo


def gravar_upload(db, *, matricula_id: int, arquivo, usuario: str) -> dict:
    """Substitui a digitalizacao oficial e marca envio ONR pendente. ESCREVE.

    O arquivo anterior nao some: vai para `historico/` com carimbo de tempo,
    para auditoria se a nova varredura estiver errada.
    """
    if arquivo is None or not getattr(arquivo, "filename", None):
        raise ValueError("Envie o arquivo da digitalizacao (PDF ou imagem).")
    nome = Path(arquivo.filename or "digitalizacao").name
    ext = Path(nome).suffix.lower()
    if ext not in EXTENSOES_OK:
        raise ValueError(
            "Formato nao aceito. Use PDF, TIFF, PNG ou JPEG.")

    pasta = pasta_da_matricula(raiz_arquivos(db), matricula_id)
    pasta.mkdir(parents=True, exist_ok=True)
    historico = pasta / "historico"
    historico.mkdir(exist_ok=True)

    # Move a atual para o historico antes de gravar a nova.
    with db.connect() as con:
        row = con.execute(
            "SELECT digi_path, digi_nome FROM ri_matriculas WHERE id=?",
            (matricula_id,)).fetchone()
    if row and row[0]:
        antigo = Path(row[0])
        if antigo.is_file():
            carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
            destino = unique_path(
                historico, f"{carimbo}_{safe_component(row[1] or antigo.name)}")
            shutil.copy2(antigo, destino)

    destino = unique_path(pasta, f"atual{ext}")
    # Se ja existe atual.*, unique_path cria atual (2).pdf — queremos substituir
    # o nome estavel `atual` + extensao.
    # HOTFIX-2026-10-06-01: no Windows o PDF pode estar travado pelo
    # proprio servidor (pypdfium2.PdfDocument sem close na miniatura/paginas).
    # unlink falha com WinError 32; sobrescrever o conteudo (wb) ainda funciona.
    # Medido na matricula 4016 (id 5378), beatriz, 06/10/2026 12:42.
    estavel = _gravar_arquivo_estavel(pasta, ext, arquivo)
    sha = hash_file(estavel)
    agora = db.now()

    with db.transaction() as con:
        con.execute(
            """UPDATE ri_matriculas
                  SET digi_path=?, digi_nome=?, digi_sha256=?,
                      digi_em=?, digi_por=?,
                      digi_onr_pendente=1, digi_onr_em=?
                WHERE id=?""",
            (str(estavel.resolve()), nome, sha, agora, usuario, agora,
             matricula_id))

    return {
        "path": str(estavel.resolve()),
        "nome": nome,
        "sha256": sha,
        "em": agora,
        "por": usuario,
        "onr_pendente": True,
    }


def atual_da_matricula(con, matricula_id: int) -> dict | None:
    """Dados da digitalizacao oficial, ou None. So le."""
    row = con.execute(
        """SELECT digi_path, digi_nome, digi_sha256, digi_em, digi_por,
                  digi_onr_pendente, digi_onr_em
             FROM ri_matriculas WHERE id=?""",
        (matricula_id,)).fetchone()
    if not row:
        return None
    path = row["digi_path"] if hasattr(row, "keys") else row[0]
    if not path:
        return None
    keys = ("digi_path", "digi_nome", "digi_sha256", "digi_em", "digi_por",
            "digi_onr_pendente", "digi_onr_em")
    if hasattr(row, "keys"):
        return {k: row[k] for k in keys}
    return dict(zip(keys, row))


def congelar_para_certidao(db, *, certidao_id: int, origem: Path) -> dict:
    """Copia o arquivo atual para a pasta da certidao (nao muda se a ficha mudar)."""
    if not origem.is_file():
        raise ValueError(
            "Nao ha digitalizacao oficial nesta matricula. "
            "Envie o arquivo na ficha antes de emitir por reproducao.")
    pasta = pasta_snapshot_certidao(raiz_arquivos(db), certidao_id)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"digitalizacao{origem.suffix.lower()}"
    if destino.exists():
        destino.unlink()
    shutil.copy2(origem, destino)
    return {
        "path": str(destino.resolve()),
        "sha256": hash_file(destino),
        "nome": origem.name,
    }


def paginas_png(caminho: Path, *, dpi: int = 150) -> list[bytes]:
    """Cada pagina do PDF/TIFF/imagem como PNG. Levanta ValueError se vazio."""
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ValueError(f"Arquivo da digitalizacao nao encontrado: {caminho}")
    ext = caminho.suffix.lower()
    saida: list[bytes] = []

    if ext == ".pdf":
        try:
            import pypdfium2
        except ImportError as exc:
            raise ValueError(
                "Falta o pacote pypdfium2 para ler o PDF da digitalizacao. "
                "Instale no runtime do Cartorio Gestao."
            ) from exc
        doc = pypdfium2.PdfDocument(str(caminho))
        try:
            if len(doc) == 0:
                raise ValueError("O PDF da digitalizacao nao tem paginas.")
            for i in range(len(doc)):
                pil = doc[i].render(scale=dpi / 72).to_pil()
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                saida.append(buf.getvalue())
        finally:
            # HOTFIX-2026-10-06-01: sem close o Windows trava atual.pdf (WinError 32).
            doc.close()
        return saida

    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError(
            "Falta o Pillow para ler a imagem da digitalizacao."
        ) from exc

    with Image.open(caminho) as im:
        n = getattr(im, "n_frames", 1) or 1
        for i in range(n):
            if n > 1:
                im.seek(i)
            frame = im.convert("RGB") if im.mode not in ("RGB", "L") else im.copy()
            if frame.mode == "L":
                frame = frame.convert("RGB")
            buf = io.BytesIO()
            frame.save(buf, format="PNG")
            saida.append(buf.getvalue())
    if not saida:
        raise ValueError("A digitalizacao nao tem paginas legiveis.")
    return saida


def miniatura_png(caminho: Path, *, largura: int = 420) -> bytes:
    """Primeira pagina da digitalizacao em PNG, sem renderizar o arquivo todo.

    A ficha usa isto apenas como miniatura. Chamar ``paginas_png`` aqui seria
    caro e silencioso: um PDF de muitas paginas seria convertido por inteiro
    para mostrar somente a capa na tela inicial.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ValueError(f"Arquivo da digitalizacao nao encontrado: {caminho}")
    largura = max(120, min(int(largura or 420), 1200))
    ext = caminho.suffix.lower()

    if ext == ".pdf":
        try:
            import pypdfium2
        except ImportError as exc:
            raise ValueError(
                "Falta o pacote pypdfium2 para ler o PDF da digitalizacao."
            ) from exc
        doc = pypdfium2.PdfDocument(str(caminho))
        try:
            if len(doc) == 0:
                raise ValueError("O PDF da digitalizacao nao tem paginas.")
            pagina = doc[0]
            # Renderiza perto da largura final: a miniatura nao precisa pagar a
            # memoria de uma pagina de impressao para depois encolher.
            largura_pdf, _ = pagina.get_size()
            escala = max(0.25, largura / max(float(largura_pdf), 1.0))
            imagem = pagina.render(scale=escala).to_pil()
        finally:
            # HOTFIX-2026-10-06-01: sem close o Windows trava atual.pdf (WinError 32).
            doc.close()
    else:
        try:
            from PIL import Image
        except ImportError as exc:
            raise ValueError(
                "Falta o Pillow para ler a imagem da digitalizacao."
            ) from exc
        with Image.open(caminho) as original:
            original.seek(0)
            imagem = original.convert("RGB")

    if imagem.width > largura:
        nova_altura = max(1, round(imagem.height * largura / imagem.width))
        try:
            from PIL import Image
            filtro = Image.Resampling.LANCZOS
        except (ImportError, AttributeError):
            filtro = 1
        imagem = imagem.resize((largura, nova_altura), filtro)
    buf = io.BytesIO()
    imagem.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


TITULO_CERTIDAO_REPROGRAFICA = "CERTIDÃO DE INTEIRO TEOR REPROGRÁFICA"


def corpo_resumo_digitalizacao(*, matricula: str, paginas: int, sha256: str) -> str:
    """Texto curto congelado no livro da certidao (o papel visual e o ODT).

    Inclui o titulo do tipo («certidão de inteiro teor reprográfica») e o
    fecho «Era o que nela continha.» — a clausula de protocolo em aberto e
    a validade entram no emitidor (`ri_web`), como na via por texto corrido.
    """
    return (
        f'<p align="center"><b>{TITULO_CERTIDAO_REPROGRAFICA}</b></p>'
        f"<p>Certidão de inteiro teor da matrícula <strong>{matricula}</strong> "
        f"por reprodução da digitalização oficial "
        f"({paginas} página(s); sha256={sha256}).</p>"
        f"<p>O documento impresso reproduz as páginas digitalizadas e traz "
        f"o selo de certidão ao final.</p>"
        f"<p>Era o que nela continha.</p>"
    )


def _escala_ficha_na_folha(pw: int, ph: int, *,
                              area_w_cm: float, area_h_cm: float) -> tuple[float, float]:
    """Largura/altura em cm da imagem, cabendo na area util sem esticar."""
    if pw <= 0 or ph <= 0:
        return round(area_w_cm, 2), round(area_h_cm, 2)
    ratio = ph / pw
    w_uso = float(area_w_cm)
    alt = w_uso * ratio
    if alt > area_h_cm:
        alt = float(area_h_cm)
        w_uso = alt / ratio
    return round(w_uso, 2), round(alt, 2)


def _fecho_html_para_papel(corpo_html: str) -> str:
    """Miolo do fecho no papel: tira titulo (ja na capa), sha256 e frase tecnica.

    O livro guarda o resumo completo (auditoria). No ODT fica o padrao da casa:
    «Era o que nela continha.» + CERTIFICO ainda (protocolo) + VALIDADE, quando
    houver — espelho da via por texto corrido (Lei 6.015 + Prov. CNJ 149/2023
    + art. 53 CGJ/TJMA).
    """
    import re as _re
    html = (corpo_html or "").strip()
    if not html:
        return ""
    # Titulo do tipo (capa).
    html = _re.sub(
        r"(?is)^\s*<p[^>]*>\s*(?:<b>)?\s*CERTID[ÃA]O DE INTEIRO TEOR "
        r"REPROGR[ÁA]FICA\s*(?:</b>)?\s*</p>\s*",
        "",
        html,
        count=1,
    )
    # Paragrafo tecnico com sha256 (auditoria do livro, nao do papel).
    # Aceita tags internas (<strong>, etc.) — o corpo real traz matrícula em <strong>.
    html = _re.sub(
        r"(?is)<p[^>]*>.*?sha256\s*=.*?</p>\s*",
        "",
        html,
    )
    # Frase redundante («O documento impresso reproduz…»).
    html = _re.sub(
        r"(?is)<p[^>]*>\s*O documento impresso reproduz[^<]*</p>\s*",
        "",
        html,
    )
    return html.strip()


def odt_da_digitalizacao(
        caminho: Path, *,
        selo_texto: str | None,
        selo_qr: bytes | None = None,
        selo_qr_mime: str | None = None,
        nome: str = "certidao",
        rotulo_selo: str = "SELO DA CERTIDAO",
        assinatura_odf: str | None = None,
        corpo_html: str | None = None,
        titulo: str | None = None) -> bytes:
    """ODT reprografico: capa tipografica, fichas centralizadas, fecho + selo.

    Padrao da casa (HOTFIX-2026-09-29-07 / layout):
      1) capa com titulo do tipo («CERTIDÃO DE INTEIRO TEOR REPROGRÁFICA»);
      2) uma ficha digitalizada por folha, centralizada e escalada na area util;
      3) fecho (protocolo em aberto / validade) + carimbo do selo + quem expediu.

    Folha A4 (21×29,7 cm) — mesma proporcao das fichas digitalizadas e do
    padrao CNJ/Codigo de Normas usado nas certidoes da serventia. Margem
    unica coerente; a imagem NUNCA ultrapassa a area util (antes estourava
    a altura e saia cortada/sobreposta). Sem traco de assinatura a mao.
    """
    import re as _re
    from ri_odt import ESTILOS_EXTRA, carimbo_do_selo_odf, gerar_odt, html_para_odf

    paginas = paginas_png(caminho)
    imagens: dict[str, tuple[bytes, str]] = {}
    partes: list[str] = []

    # A4 — padrao das certidoes / anexos CNJ; casas as fichas digitalizadas.
    w_cm, h_cm = 21.0, 29.7
    margem_cm = 0.9
    # Respiro interno para o frame nao encostar na margem da impressora.
    pad_cm = 0.15
    area_w = max(1.0, w_cm - 2 * margem_cm - 2 * pad_cm)
    area_h = max(1.0, h_cm - 2 * margem_cm - 2 * pad_cm)

    ESTILOS_EXTRA.setdefault(
        "P-digi-titulo",
        '<style:style style:name="P-digi-titulo" style:family="paragraph">'
        '<style:paragraph-properties fo:text-align="center" '
        'fo:margin-top="2.4cm" fo:margin-bottom="0.6cm" '
        'fo:line-height="130%"/>'
        '<style:text-properties fo:font-size="14pt" fo:font-weight="bold"/>'
        "</style:style>")
    ESTILOS_EXTRA.setdefault(
        "P-digi-capa-sub",
        '<style:style style:name="P-digi-capa-sub" style:family="paragraph">'
        '<style:paragraph-properties fo:text-align="center" '
        'fo:margin-top="0.3cm" fo:margin-bottom="0.2cm" '
        'fo:line-height="120%"/>'
        '<style:text-properties fo:font-size="11pt"/>'
        "</style:style>")
    ESTILOS_EXTRA.setdefault(
        "P-digi-capa-nota",
        '<style:style style:name="P-digi-capa-nota" style:family="paragraph">'
        '<style:paragraph-properties fo:text-align="center" '
        'fo:margin-top="1.2cm" fo:margin-bottom="0.2cm" '
        'fo:line-height="120%"/>'
        '<style:text-properties fo:font-size="10pt"/>'
        "</style:style>")
    ESTILOS_EXTRA.setdefault(
        "P-digi-pagina",
        '<style:style style:name="P-digi-pagina" style:family="paragraph">'
        '<style:paragraph-properties fo:text-align="center" '
        'fo:margin-top="0cm" fo:margin-bottom="0cm"/>'
        "</style:style>")
    ESTILOS_EXTRA.setdefault(
        "P-digi-pagina-quebra",
        '<style:style style:name="P-digi-pagina-quebra" style:family="paragraph">'
        '<style:paragraph-properties fo:break-before="page" '
        'fo:text-align="center" fo:margin-top="0cm" fo:margin-bottom="0cm"/>'
        "</style:style>")
    ESTILOS_EXTRA.setdefault(
        "P-digi-fecho-quebra",
        '<style:style style:name="P-digi-fecho-quebra" style:family="paragraph">'
        '<style:paragraph-properties fo:break-before="page" '
        'fo:text-align="justify" fo:margin-top="0.4cm" '
        'fo:margin-bottom="0.2cm" fo:line-height="120%"/>'
        "</style:style>")

    # --- Capa tipografica -------------------------------------------------
    titulo_txt = (titulo or TITULO_CERTIDAO_REPROGRAFICA).strip() or TITULO_CERTIDAO_REPROGRAFICA
    partes.append(
        f'<text:p text:style-name="P-digi-titulo">'
        f'{_re.sub(r"[<>&]", lambda m: {"<": "&lt;", ">": "&gt;", "&": "&amp;"}[m.group(0)], titulo_txt)}'
        f"</text:p>"
    )
    n_pag = len(paginas)
    partes.append(
        f'<text:p text:style-name="P-digi-capa-sub">'
        f"Reprodução fiel da matrícula digitalizada "
        f"({n_pag} página{'s' if n_pag != 1 else ''})."
        f"</text:p>"
    )
    partes.append(
        '<text:p text:style-name="P-digi-capa-nota">'
        "As folhas seguintes reproduzem as fichas oficiais. "
        "Ao final constam o fecho (protocolo em aberto), o selo digital "
        "e a identificação de quem expediu."
        "</text:p>"
    )

    # --- Fichas digitalizadas (1 por folha, centralizadas) ----------------
    for i, png in enumerate(paginas):
        img_name = f"digi{i + 1}.png"
        imagens[img_name] = (png, "image/png")
        try:
            from PIL import Image
            with Image.open(io.BytesIO(png)) as im:
                pw, ph = im.size
                w_uso, alt = _escala_ficha_na_folha(
                    pw, ph, area_w_cm=area_w, area_h_cm=area_h)
        except Exception:
            w_uso, alt = round(area_w, 2), round(area_h, 2)
        partes.append(
            f'<text:p text:style-name="P-digi-pagina-quebra">'
            f'<draw:frame draw:name="{img_name}" text:anchor-type="as-char" '
            f'svg:width="{w_uso}cm" svg:height="{alt}cm" '
            f'style:rel-width="scale" style:rel-height="scale">'
            f'<draw:image xlink:href="Pictures/{img_name}" '
            f'xlink:type="simple" xlink:show="embed" '
            f'xlink:actuate="onLoad"/>'
            f"</draw:frame></text:p>"
        )

    # --- Fecho + selo + quem expediu --------------------------------------
    img_selo = None
    if selo_qr:
        img_selo = "selo_cert.png"
        mime = selo_qr_mime or "image/png"
        imagens[img_selo] = (selo_qr, mime)
    partes.append('<text:p text:style-name="P-digi-fecho-quebra"></text:p>')

    html_fecho = _fecho_html_para_papel(str(corpo_html or ""))
    if html_fecho:
        partes.append(html_para_odf(html_fecho, compacto=True))

    # Carimbo da CERTIDAO (nao do ato) — largura inteira.
    partes.append(carimbo_do_selo_odf(
        selo_texto, img_selo, rotulo=rotulo_selo,
        feitio="certidao", por_fileira=1))

    # Nome de quem lavrou (1x), sem traco de assinatura a mao.
    if assinatura_odf:
        partes.append(assinatura_odf)

    return gerar_odt(
        "\n".join(partes),
        titulo=nome,
        imagens=imagens,
        cabecalho_altura_min="0cm",
        cabecalho_borda=False,
        pagina_largura_cm=w_cm,
        pagina_altura_cm=h_cm,
        margem_cm=margem_cm,
    )



def pendentes_onr(con, *, limite: int = 200) -> list:
    """Matriculas com digitalizacao nova ainda nao enviada ao ONR. So le."""
    return list(con.execute(
        """SELECT id, numero, digi_nome, digi_sha256, digi_em, digi_por, digi_path
             FROM ri_matriculas
            WHERE digi_onr_pendente=1 AND digi_path IS NOT NULL
            ORDER BY digi_em DESC
            LIMIT ?""",
        (limite,)).fetchall())


def marcar_onr_enviada(con, matricula_id: int) -> None:
    """Baixa o pendente depois que o envio manual/integracao confirmar."""
    con.execute(
        "UPDATE ri_matriculas SET digi_onr_pendente=0 WHERE id=?",
        (matricula_id,))
