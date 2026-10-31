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

import ri_frases
import tetos_de_entrada as TETO
from bd_nativo import banco
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
        row = banco(con).um(
            "SELECT digi_path, digi_nome FROM ri_matriculas WHERE id=%s",
            (matricula_id,))
    if row and row["digi_path"]:
        antigo = Path(row["digi_path"])
        if antigo.is_file():
            carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
            # Sem aspas aninhadas na f-string: a producao roda Python 3.11.
            nome = safe_component(row["digi_nome"] or antigo.name)
            destino = unique_path(historico, f"{carimbo}_{nome}")
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
        banco(con).escrever(
            """UPDATE ri_matriculas
                  SET digi_path=%s, digi_nome=%s, digi_sha256=%s,
                      digi_em=%s, digi_por=%s,
                      digi_onr_pendente=1, digi_onr_em=%s
                WHERE id=%s""",
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
    row = banco(con).um(
        """SELECT digi_path, digi_nome, digi_sha256, digi_em, digi_por,
                  digi_onr_pendente, digi_onr_em
             FROM ri_matriculas WHERE id=%s""",
        (matricula_id,))
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


def _conferir_area(largura: int, altura: int) -> None:
    """Recusa o quadro cujo bitmap passa do teto de pixels (LX12, LS02 M3)."""
    teto = TETO.valor("pixels_por_pagina")
    if int(largura) * int(altura) > teto:
        raise TETO.TetoExcedido(
            f"A imagem tem {largura} x {altura} pixels, acima do teto de "
            f"{teto:,} pixels por pagina. Digitalize de novo em resolucao "
            f"normal (CG_TETO_PIXELS_POR_PAGINA ajusta).".replace(",", "."))


def paginas_png(caminho: Path, *, dpi: int = 150) -> list[bytes]:
    """Cada pagina do PDF/TIFF/imagem como PNG. Levanta ValueError se vazio.

    COM TETO DE PAGINAS E DE AREA (LX12, LS02 M3, 19/10/2026): o arquivo vem
    do balcao, e um PDF de MediaBox gigante ou um TIFF de milhares de quadros
    virava bitmap de gigabytes num processo so. A recusa e `TetoExcedido`,
    que e `ValueError` — o mesmo erro que as rotas ja apanham daqui.
    """
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
            TETO.conferir_paginas(len(doc), "o PDF da digitalizacao")
            for i in range(len(doc)):
                largura_pt, altura_pt = doc[i].get_size()
                escala = TETO.escala_que_cabe(largura_pt, altura_pt, dpi / 72)
                pil = doc[i].render(scale=escala).to_pil()
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
        TETO.conferir_paginas(n, "a digitalizacao")
        for i in range(n):
            if n > 1:
                im.seek(i)
            _conferir_area(*im.size)
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
            largura_pdf, altura_pdf = pagina.get_size()
            escala = max(0.25, largura / max(float(largura_pdf), 1.0))
            # A ESCALA MINIMA DE 0,25 NAO SEGURAVA A ALTURA (LX12, LS02 M3):
            # pagina estreita e altissima virava bitmap de gigabytes. Encolhe
            # ate caber no teto de pixels — a miniatura nao precisa de mais.
            escala = TETO.escala_que_cabe(largura_pdf, altura_pdf, escala)
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
            _conferir_area(*original.size)
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


# O TÍTULO FICA NO CÓDIGO — LF06B: é o nome do tipo, e `_fecho_html_para_papel`
# o tira do corpo congelado pela redação literal (o papel traz o título dele,
# hoje o do modelo da casa). Editável na tela, ele sairia duas vezes no papel
# no dia em que a casa o mudasse.
TITULO_CERTIDAO_REPROGRAFICA = "CERTIDÃO DE INTEIRO TEOR REPROGRÁFICA"


def corpo_resumo_digitalizacao(*, matricula: str, paginas: int, sha256: str,
                               con=None) -> str:
    """Texto curto congelado no livro da certidao (o papel visual e o ODT).

    Inclui o titulo do tipo («certidão de inteiro teor reprográfica») e o
    fecho «Era o que nela continha.» — a clausula de protocolo em aberto e
    a validade entram no emitidor (`ri_web`), como na via por texto corrido.

    O TEXTO DO FECHO SAIU DAQUI — LF06B: é o papel `RI_REPROGRAFICA_FECHO`
    (`ri_frases`), o único pedaço deste corpo que chega ao papel. O título e
    os dois parágrafos técnicos (sha256, «O documento impresso…») ficam:
    `_fecho_html_para_papel` os acha pela redação, e redação editada na tela
    poria o sha256 no papel do cliente. Sem `con`, o padrão da base.
    """
    return (
        f'<p align="center"><b>{TITULO_CERTIDAO_REPROGRAFICA}</b></p>'
        f"<p>Certidão de inteiro teor da matrícula <strong>{matricula}</strong> "
        f"por reprodução da digitalização oficial "
        f"({paginas} página(s); sha256={sha256}).</p>"
        f"<p>O documento impresso reproduz as páginas digitalizadas e traz "
        f"o selo de certidão ao final.</p>"
        + ri_frases.frase("RI_REPROGRAFICA_FECHO", con)
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
    + art. 553 CGJ/TJMA). No modelo da casa (20/10/2026) quem chama é
    `_fecho_extra_do_modelo`, que tira também o fecho do livro: o papel tem o
    dele.
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


# ---------------------------------------------------------------------------
# O MODELO DA CASA DA CERTIDÃO REPROGRÁFICA — pedido da substituta, 20/10/2026
# (HOTFIX-2026-10-20-02; na produção desde a 3.6.293.4, 21/10/2026):
#   «As certidões reprográficas estão saindo num modelo muito inadequado.
#    Elaborei este modelo e gostaria que você integrasse ao modelo de
#    certidão (...) e que todas saiam neste modelo.»
# O papel é o do modelo dela (docx «CERTIDÃO REPROGRÁFICA»), com as medidas
# dele. O TEOR CONGELADO NÃO MUDA: o modelo é só o papel. O livro da certidão
# guarda o resumo (com o sha256) e o fecho de protocolo/validade; daqui se
# aproveitam o «CERTIFICO ainda» e a validade, e nada é reescrito no banco —
# por isso as já emitidas também saem no modelo, na próxima impressão.
#
# DUAS DIFERENÇAS DO SERVIDOR NESTA BRANCH (LH02, 21/10/2026):
#   - QUEM RESPONDE PELA CASA VEM DO CADASTRO DA SERVENTIA (`serventia.dados`),
#     como no cabeçalho completo de `ri_odt`: no servidor, o nome do oficial e
#     o da substituta estavam escritos aqui, e o papel de amanhã traria quem
#     já não responde pela casa. O nome da serventia e a cidade da data também.
#   - O TEXTO DO MODELO MORA NA BASE, como o das outras frases do RI (LF06B,
#     «não deveríamos ter modelos no código»): o CERTIFICO e a ressalva da
#     folha 1 são o papel `RI_REPROGRAFICA_CAPA` — era a frase da capa antiga,
#     que o modelo substituiu —, e o fecho depois da última folha é o
#     `RI_REPROGRAFICA_FECHO_DO_PAPEL`. Aqui ficam o título (o nome do tipo,
#     como `TITULO_CERTIDAO_REPROGRAFICA`) e as REGRAS: a identificação do
#     documento, as páginas por extenso, a qualificação de quem assina.
# ---------------------------------------------------------------------------
MODELO_REPRO_TITULO = "CERTIDÃO REPROGRÁFICA"
# Função gravada na certidão -> qualificação por extenso do modelo. A do
# oficial e a da substituta são também as do cabeçalho.
QUALIFICACAO_DO_SIGNATARIO = {
    "substituta": "Tabeliã e Registradora Substituta",
    "substituto": "Tabelião e Registrador Substituto",
    "oficial": "Tabelião e Registrador Oficial",
    "titular": "Tabelião e Registrador Oficial",
}
_MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro")
_NUMEROS_EXTENSO = ("zero", "uma", "duas", "três", "quatro", "cinco", "seis",
                    "sete", "oito", "nove", "dez", "onze", "doze", "treze",
                    "catorze", "quinze", "dezesseis", "dezessete", "dezoito",
                    "dezenove", "vinte")


def _esc(txt) -> str:
    from xml.sax.saxutils import escape
    return escape(str(txt or ""))


def data_por_extenso_repro(valor) -> str:
    """«2026-10-20» -> «20 de outubro de 2026». Vazio se não entender."""
    s = str(valor or "").strip()[:10]
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return ""
    return f"{d.day:02d} de {_MESES[d.month - 1]} de {d.year}"


def qualificacao_do_signatario(funcao: str | None) -> str:
    f = str(funcao or "").strip()
    return QUALIFICACAO_DO_SIGNATARIO.get(f.casefold(), f)


def _paginas_por_extenso(n: int) -> str:
    nome = _NUMEROS_EXTENSO[n] if 0 <= n < len(_NUMEROS_EXTENSO) else str(n)
    return f"{n} ({nome}) página{'s' if n != 1 else ''}"


def _numeros_dos_selos(selo_texto: str | None) -> list[str]:
    """Todos os números de selo da etiqueta (a certidão do RI leva dois)."""
    import re as _re
    s = str(selo_texto or "")
    vistos: list[str] = []
    for n in _re.findall(r"\b[A-Z]{6}\d{6}[A-Z0-9]{8,20}\b", s):
        if n not in vistos:
            vistos.append(n)
    if not vistos and s.strip():
        vistos.append(s.strip().split()[0])
    return vistos


def identificacao_da_matricula(numero, livro=None, folha=None, cnm=None) -> str:
    """«Matrícula nº 9.003 do Livro nº 2-S – Registro Geral, fl. 12, CNM ...»."""
    dig = "".join(ch for ch in str(numero or "") if ch.isdigit())
    if not dig:
        return ""
    txt = f"Matrícula nº {int(dig):,}".replace(",", ".")
    lv = str(livro or "").strip()
    if lv:
        if len(lv) >= 2 and lv[0].isdigit() and lv[1:].isalpha():
            lv = f"{lv[0]}-{lv[1:]}"
        txt += f" do Livro nº {lv} – Registro Geral"
    fl = str(folha or "").strip()
    if fl and fl.lower() not in ("none", "fichas"):
        txt += f", fl. {fl}"
    if str(cnm or "").strip():
        txt += f", CNM {str(cnm).strip()}"
    return txt


def _identificacao_do_corpo(corpo_html: str | None) -> str:
    """Matrícula citada no resumo congelado («... da matrícula <b>9003</b>»)."""
    import re as _re
    m = _re.search(r"(?is)matr[íi]cula\s*(?:<[^>]+>\s*)*([\d.]+)",
                   str(corpo_html or ""))
    if not m:
        return ""
    dig = m.group(1).replace(".", "")
    if not dig.isdigit():
        return ""
    return f"Matrícula nº {int(dig):,}".replace(",", ".")


def _data_do_corpo(corpo_html: str | None) -> str:
    import re as _re
    m = _re.search(r"(?is)Certid[ãa]o emitida em\s+([^.<]+?)\s*\.",
                   str(corpo_html or ""))
    return m.group(1).strip() if m else ""


def cabecalho_do_modelo_repro(serventia: dict | None) -> list[tuple[str, str]]:
    """As linhas do alto da folha 1, `(texto, estilo)`. Só calcula.

    República e Estado são do papel. A serventia, o oficial e a substituta são
    do CADASTRO (`serventia.dados` — o titular também pela chave antiga
    `ri_registrador`, que `dados` já unifica): campo sem valor não sai, e
    nunca há um nome escrito aqui. Sem o cadastro (montador puro, teste), o
    cabeçalho fica com as linhas que não dependem dele.
    """
    s = serventia or {}

    def v(*chaves: str) -> str:
        for k in chaves:
            t = str(s.get(k) or "").strip()
            if t:
                return t
        return ""

    linhas = [("REPÚBLICA FEDERATIVA DO BRASIL", "P-repro-cab1"),
              ("ESTADO DO MARANHÃO", "P-repro-cab1")]
    unidade = v("unit_name", "nome").upper()
    if unidade:
        if not unidade.startswith("SERVENTIA"):
            unidade = f"SERVENTIA EXTRAJUDICIAL DO {unidade}"
        linhas.append((unidade, "P-repro-cab2"))
    titular = v("serventia_titular", "ri_registrador", "titular")
    if titular:
        linhas.append((f"{titular} — {QUALIFICACAO_DO_SIGNATARIO['oficial']}",
                       "P-repro-cab3"))
    substituta = v("ri_substituta", "substituta")
    if substituta:
        linhas.append(
            (f"{substituta} — {QUALIFICACAO_DO_SIGNATARIO['substituta']}",
             "P-repro-cab3"))
    return linhas


def _lugar_do_modelo(serventia: dict | None) -> str:
    """«Cidade/UF» da linha da data, do cadastro da serventia."""
    s = serventia or {}
    return "/".join(p for p in (str(s.get("ri_cidade") or s.get("cidade") or "").strip(),
                                str(s.get("ri_uf") or s.get("uf") or "").strip())
                    if p)


def _fecho_extra_do_modelo(corpo_html: str | None, con=None) -> str:
    """Do resumo congelado, só o que o modelo não diz: CERTIFICO ainda e validade.

    Sai o fecho do livro (o modelo tem o dele, `RI_REPROGRAFICA_FECHO_DO_PAPEL`)
    e, da validade, a frase «Certidão emitida em ... Dou fé.» — a data vai na
    linha do lugar. O fecho do livro sai pela redação de antes do LF06B
    («Era o que nela continha.») e pela que vale hoje (`RI_REPROGRAFICA_FECHO`,
    com o ajuste da casa): a certidão emitida depois de um ajuste traz o texto
    ajustado no corpo, e ele não pode sair no papel ao lado do fecho do modelo.
    """
    import re as _re
    html = _fecho_html_para_papel(str(corpo_html or ""))
    html = _re.sub(r"(?is)<p[^>]*>\s*Era o que nela continha\.?\s*</p>\s*", "",
                   html)
    fecho_do_livro = ri_frases.frase("RI_REPROGRAFICA_FECHO", con).strip()
    if fecho_do_livro:
        html = html.replace(fecho_do_livro, "")
    html = _re.sub(r"(?is)\s*Certid[ãa]o emitida em\s+[^.<]+?\.\s*(?:Dou f[ée]\.)?",
                   "", html)
    return html.strip()


def _odf_da_frase(html: str, estilo: str) -> str:
    """A frase da base (HTML) em parágrafos do modelo: o estilo de cada um
    passa a ser `estilo`; o itálico e o negrito que ela pedir continuam."""
    import re as _re
    from ri_odt import html_para_odf
    odf = html_para_odf(html, compacto=True)
    return _re.sub(r'(<text:p\b[^>]*?)text:style-name="[^"]*"',
                   lambda m: f'{m.group(1)}text:style-name="{estilo}"', odf)


def _estilos_do_modelo_repro() -> None:
    from ri_odt import ESTILOS_EXTRA
    fonte = "fo:font-family=\"'Times New Roman'\" style:font-family-generic=\"roman\""

    def par(nome, alinha, antes, depois, tam, negrito=False, italico=False,
            extra=""):
        peso = ' fo:font-weight="bold"' if negrito else ' fo:font-weight="normal"'
        ital = ' fo:font-style="italic"' if italico else ""
        ESTILOS_EXTRA[nome] = (
            f'<style:style style:name="{nome}" style:family="paragraph">'
            f'<style:paragraph-properties fo:text-align="{alinha}" '
            f'fo:margin-top="{antes}" fo:margin-bottom="{depois}" '
            f'fo:line-height="115%"{extra}/>'
            f'<style:text-properties {fonte} fo:font-size="{tam}"{peso}{ital}/>'
            "</style:style>")

    # MEDIDAS DO DOCX DO MODELO (20/10/2026, conferido no XML): estilo Normal
    # Times New Roman 12 pt, entrelinha 1,15, 8 pt depois do parágrafo;
    # cabeçalho 10/10/11/9/9 pt com 3 pt depois; título 12 pt negrito com
    # 15 pt antes e 8 depois; a reprodução com 25 pt antes.
    DEPOIS = "0.282cm"   # 8 pt
    par("P-repro-brasao", "center", "0cm", "0cm", "10pt")
    par("P-repro-cab1", "center", "0cm", "0.106cm", "10pt", True)
    par("P-repro-cab2", "center", "0cm", "0.106cm", "11pt", True)
    par("P-repro-cab3", "center", "0cm", "0.106cm", "9pt")
    par("P-repro-titulo", "center", "0.529cm", DEPOIS, "12pt", True)
    par("P-repro-texto", "justify", "0cm", DEPOIS, "12pt")
    par("P-repro-centro", "center", "0cm", DEPOIS, "12pt")
    par("P-repro-assina", "center", "0.776cm", DEPOIS, "12pt")
    # O fecho anda junto até o carimbo: não se parte entre duas folhas.
    junto = ' fo:keep-with-next="always"'
    par("P-repro-fecho", "justify", "0cm", DEPOIS, "12pt", extra=junto)
    par("P-repro-fecho-centro", "center", "0cm", DEPOIS, "12pt", extra=junto)
    par("P-repro-fecho-assina", "center", "0.776cm", DEPOIS, "12pt", extra=junto)
    par("P-repro-img", "center", "0.882cm", DEPOIS, "12pt")
    par("P-repro-img-quebra", "center", "0cm", "0cm", "12pt",
        extra=' fo:break-before="page"')
    # O brasão do cabeçalho de página: sem respiro, para não empurrar o texto.
    ESTILOS_EXTRA["P-repro-cabpag"] = (
        '<style:style style:name="P-repro-cabpag" style:family="paragraph">'
        '<style:paragraph-properties fo:text-align="center" fo:margin-top="0cm" '
        'fo:margin-bottom="0cm" fo:line-height="100%"/></style:style>')


def _brasao_do_modelo() -> tuple[bytes, str] | None:
    """O brasão do modelo (preto e branco); sem ele, o brasão da casa."""
    base = Path(__file__).resolve().parent / "static"
    for nome, mime in (("brasao_certidao_reprografica.png", "image/png"),
                       ("brasao.jpg", "image/jpeg")):
        p = base / nome
        if p.is_file():
            return p.read_bytes(), mime
    return None


def odt_da_digitalizacao(
        caminho: Path, *,
        selo_texto: str | None,
        selo_qr: bytes | None = None,
        selo_qr_mime: str | None = None,
        nome: str = "certidao",
        rotulo_selo: str = "SELO DA CERTIDAO",
        assinatura_odf: str | None = None,
        corpo_html: str | None = None,
        titulo: str | None = None,
        identificacao: str | None = None,
        data_emissao: str | None = None,
        signatario: tuple[str, str] | None = None,
        serventia: dict | None = None,
        con=None) -> bytes:
    """ODT da certidão reprográfica no MODELO DA CASA (20/10/2026).

    Folha 1: brasão, República/Estado/serventia/oficial/substituta (do
    cadastro, `serventia`), «CERTIDÃO REPROGRÁFICA», o CERTIFICO com a
    identificação do documento e a ressalva de legibilidade (o papel
    `RI_REPROGRAFICA_CAPA`). TODA PÁGINA SAI NA LARGURA CHEIA DA ÁREA, e o
    texto é que cede lugar (of-0151, 31/10/2026: reduzidas para caber ao lado
    do texto, a 1ª e a última página de uma ficha A4 ficavam ilegíveis). A 1ª
    página fica na folha 1 só se couber assim; senão, vai para a folha
    seguinte. Demais páginas: uma por folha, centralizadas, sem esticar. Depois
    da última: o fecho do modelo (`RI_REPROGRAFICA_FECHO_DO_PAPEL`), o
    CERTIFICO ainda/validade do resumo congelado, lugar e data, nome e
    qualificação de quem expediu, «Selo digital: <número>» e o carimbo com QR
    e emolumentos (o mesmo das outras certidões). O selo só se IMPRIME: este
    papel não sela nada.

    `identificacao`, `data_emissao` (AAAA-MM-DD) e `signatario` (nome,
    função) vêm de quem chama; faltando, saem do resumo congelado
    (`corpo_html`) e de `assinatura_odf`. `titulo` é aceito por
    compatibilidade e ignorado: o título é o do modelo. Com `con`, as frases
    saem com o ajuste da casa; sem ele, o padrão da base.
    """
    import html as _html
    import re as _re
    from ri_odt import carimbo_do_selo_odf, gerar_odt

    paginas = paginas_png(caminho)
    n_pag = len(paginas)
    _estilos_do_modelo_repro()
    imagens: dict[str, tuple[bytes, str]] = {}
    partes: list[str] = []

    # PÁGINA DO MODELO (docx): o brasão é CABEÇALHO DE PÁGINA, a 0,51 cm do
    # alto, em TODAS as folhas; o texto começa logo abaixo dele; margem de
    # baixo 2,0 cm; sem rodapé nem número de página. O modelo é Carta
    # (21,59 cm) com 2,5 cm dos lados = 16,59 cm de linha; no A4 (21 cm) as
    # laterais de 2,2 cm dão a MESMA largura de linha, e as quebras de linha
    # saem iguais às do modelo.
    w_cm, h_cm = 21.0, 29.7
    margem_cm = 2.2
    MARGEM_TOPO_CM, MARGEM_BAIXO_CM = 0.51, 2.0
    BRASAO_ALT_CM = 2.06
    area_w = w_cm - 2 * margem_cm
    area_h = (h_cm - MARGEM_TOPO_CM - BRASAO_ALT_CM - 0.15 - MARGEM_BAIXO_CM
              - 0.6)
    # O que a folha 1 gasta antes da reprodução (cabeçalho em texto + título
    # + CERTIFICO + ressalva + 25 pt), medido na prévia: ~8,6 cm.
    area_h_folha1 = area_h - 9.0

    # --- Cabeçalho do modelo --------------------------------------------
    brasao = _brasao_do_modelo()
    cabecalho_pagina = ""
    if brasao:
        ext = "png" if brasao[1] == "image/png" else "jpg"
        imagens[f"brasao_repro.{ext}"] = brasao
        cabecalho_pagina = (
            '<text:p text:style-name="P-repro-cabpag">'
            '<draw:frame draw:name="brasao_repro" text:anchor-type="as-char" '
            f'svg:width="2.03cm" svg:height="{BRASAO_ALT_CM}cm">'
            f'<draw:image xlink:href="Pictures/brasao_repro.{ext}" '
            'xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/>'
            '</draw:frame></text:p>')
    for texto, estilo in cabecalho_do_modelo_repro(serventia):
        partes.append(f'<text:p text:style-name="{estilo}">{_esc(texto)}</text:p>')
    partes.append(f'<text:p text:style-name="P-repro-titulo">'
                  f'{_esc(MODELO_REPRO_TITULO)}</text:p>')

    # O CERTIFICO E A RESSALVA SÃO O PAPEL `RI_REPROGRAFICA_CAPA`: a regra
    # (qual documento, quantas páginas, por extenso) fica aqui e chega ao
    # claro já escapada para HTML, porque a frase é HTML.
    ident = (identificacao or "").strip() or _identificacao_do_corpo(corpo_html)
    if ident:
        ident_txt = f"{ident}, em {_paginas_por_extenso(n_pag)}."
    else:
        ident_txt = (f"indicada na digitalização oficial arquivada nesta "
                     f"Serventia, em {_paginas_por_extenso(n_pag)}.")
    partes.append(_odf_da_frase(
        ri_frases.frase("RI_REPROGRAFICA_CAPA", con,
                        identificacao=_html.escape(ident_txt, quote=False)),
        "P-repro-texto"))

    # --- A reprodução ------------------------------------------------------
    for i, png in enumerate(paginas):
        img_name = f"digi{i + 1}.png"
        imagens[img_name] = (png, "image/png")
        # of-0151: a medida é a mesma em toda página, e nenhuma encolhe por
        # causa do texto. A 1ª só divide a folha com o CERTIFICO se couber
        # inteira; o fecho, que anda junto (`keep-with-next`), fica depois da
        # última se couber ou passa inteiro para a folha seguinte.
        estilo = "P-repro-img-quebra"
        try:
            from PIL import Image
            with Image.open(io.BytesIO(png)) as im:
                pw, ph = im.size
            w_uso, alt = _escala_ficha_na_folha(
                pw, ph, area_w_cm=area_w, area_h_cm=area_h)
            if i == 0 and alt <= area_h_folha1:
                estilo = "P-repro-img"
        except Exception:
            w_uso, alt = round(area_w, 2), round(area_h, 2)
        partes.append(
            f'<text:p text:style-name="{estilo}">'
            f'<draw:frame draw:name="{img_name}" text:anchor-type="as-char" '
            f'svg:width="{w_uso}cm" svg:height="{alt}cm">'
            f'<draw:image xlink:href="Pictures/{img_name}" '
            f'xlink:type="simple" xlink:show="embed" '
            f'xlink:actuate="onLoad"/>'
            f"</draw:frame></text:p>")

    # --- Fecho do modelo ---------------------------------------------------
    partes.append(_odf_da_frase(
        ri_frases.frase("RI_REPROGRAFICA_FECHO_DO_PAPEL", con), "P-repro-fecho"))
    extra = _fecho_extra_do_modelo(corpo_html, con)
    if extra:
        # o texto do resumo no corpo do modelo (Times 12, justificado)
        partes.append(_odf_da_frase(extra, "P-repro-fecho"))

    lugar = _lugar_do_modelo(serventia)
    data_txt = (data_por_extenso_repro(data_emissao)
                or _data_do_corpo(corpo_html)
                or "____ de __________________ de ______")
    partes.append(f'<text:p text:style-name="P-repro-fecho-centro">'
                  f'{_esc(", ".join(p for p in (lugar, data_txt) if p))}.</text:p>')

    # SEM O TRACO DA CANETA: ordem do oficial de 22/09/2026 («so na ficha»)
    # e 23/09 (a certidao diz quem a expediu: nome e titulo). O modelo da
    # casa traz a linha; fica so o nome, com o respiro de onde ela estava.
    nome_sig, func_sig = (signatario or ("", ""))
    if not (nome_sig or "").strip() and assinatura_odf:
        linhas = [_re.sub(r"<[^>]+>", "", x).strip() for x in
                  _re.findall(r"(?s)<text:p[^>]*>(.*?)</text:p>", assinatura_odf)]
        linhas = [x for x in linhas if x]
        if linhas:
            nome_sig = linhas[0]
            func_sig = linhas[1] if len(linhas) > 1 else ""
    if (nome_sig or "").strip():
        quali = qualificacao_do_signatario(func_sig)
        partes.append(f'<text:p text:style-name="P-repro-fecho-assina">'
                      f'{_esc(nome_sig.strip())}'
                      f'{" — " + _esc(quali) if quali else ""}</text:p>')

    numeros = _numeros_dos_selos(selo_texto)
    if numeros:
        rot = "Selo digital" if len(numeros) == 1 else "Selos digitais"
        partes.append(f'<text:p text:style-name="P-repro-fecho-centro">'
                      f'{rot}: {_esc(" e ".join(numeros))}</text:p>')
    # Um QR por selo, na ordem da etiqueta. O QR é DERIVADO do número (a casa
    # não guarda QR); o recebido de quem chama vale para o selo que ele lê.
    img_selos: list[str | None] = []
    try:
        from ri_odt import png_do_qr_do_selo as _qr
    except ImportError:
        _qr = None
    for k, numero in enumerate(numeros or [""]):
        png = None
        if _qr and numero:
            try:
                png = _qr(numero)
            except Exception:                                # noqa: BLE001
                png = None
        if not png and k == 0 and selo_qr:
            png = selo_qr
        if png:
            nome_qr = f"selo_cert_{k + 1}.png"
            imagens[nome_qr] = (png, selo_qr_mime if png is selo_qr and
                                selo_qr_mime else "image/png")
            img_selos.append(nome_qr)
        else:
            img_selos.append(None)
    partes.append(carimbo_do_selo_odf(
        selo_texto, img_selos, rotulo=rotulo_selo,
        feitio="certidao", por_fileira=1))

    odt = gerar_odt(
        "\n".join(partes),
        titulo=nome,
        cabecalho_odf=cabecalho_pagina,
        imagens=imagens,
        cabecalho_altura_min=f"{BRASAO_ALT_CM}cm",
        cabecalho_margem_baixo="0cm",
        cabecalho_borda=False,
        pagina_largura_cm=w_cm,
        pagina_altura_cm=h_cm,
        margem_cm=margem_cm,
    )
    return _margens_do_modelo(odt, topo_cm=MARGEM_TOPO_CM,
                              baixo_cm=MARGEM_BAIXO_CM)


def _margens_do_modelo(odt: bytes, *, topo_cm: float, baixo_cm: float) -> bytes:
    """Topo e pé da página do modelo. `gerar_odt` só sabe uma margem para os
    quatro lados; aqui se trocam as duas no `<style:page-layout-properties>`
    (só nele — ver a nota de 09/09/2026 em `ri_odt.gerar_odt`)."""
    import re as _re
    import zipfile
    src = zipfile.ZipFile(io.BytesIO(odt))
    estilos = src.read("styles.xml").decode("utf-8")

    def _pagina(m):
        bloco = m.group(0)
        bloco = _re.sub(r'fo:margin-top="[^"]+"', f'fo:margin-top="{topo_cm:g}cm"', bloco)
        bloco = _re.sub(r'fo:margin-bottom="[^"]+"', f'fo:margin-bottom="{baixo_cm:g}cm"', bloco)
        return bloco
    estilos, n = _re.subn(r'<style:page-layout-properties\b[^>]*>', _pagina,
                          estilos, count=1)
    if not n:
        return odt
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for info in src.infolist():
            dados = estilos.encode("utf-8") if info.filename == "styles.xml" else src.read(info.filename)
            if info.filename == "mimetype":
                z.writestr(zipfile.ZipInfo("mimetype"), dados, compress_type=zipfile.ZIP_STORED)
            else:
                z.writestr(info.filename, dados)
    return buf.getvalue()


def pendentes_onr(con, *, limite: int = 200) -> list:
    """Matriculas com digitalizacao nova ainda nao enviada ao ONR. So le."""
    return banco(con).ler(
        """SELECT id, numero, digi_nome, digi_sha256, digi_em, digi_por, digi_path
             FROM ri_matriculas
            WHERE digi_onr_pendente=1 AND digi_path IS NOT NULL
            ORDER BY digi_em DESC, id
            LIMIT %s""",
        (limite,))


def marcar_onr_enviada(con, matricula_id: int) -> None:
    """Baixa o pendente depois que o envio manual/integracao confirmar."""
    banco(con).escrever(
        "UPDATE ri_matriculas SET digi_onr_pendente=0 WHERE id=%s",
        (matricula_id,))
