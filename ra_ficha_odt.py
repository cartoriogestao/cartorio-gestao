"""A FICHA DO REGISTRO DO LIVRO 3, em papel.

O último item da fila: o Livro 2 imprime a própria ficha (`ri_ficha_odt`) e o
Livro 3 **só emitia certidão**. São papéis diferentes e a diferença importa: a
certidão vai para fora e afirma; **a ficha é o livro**, e serve para ler, levar
à estante e conferir.

**O MODELO VAI AO CATÁLOGO DA CASA** (`RI_LIVRO3_FICHA`), como o da certidão do
Livro 3 — é o relato #28, «preciso ter controle geral sobre os modelos». Sem
linha gravada, o papel sai do padrão daqui; ajustado, sai como o oficial
escreveu, e «voltar ao padrão» é apagar a linha.

**O FORMATO É `CHAVES`, e não Jinja** — a mesma decisão da certidão do Livro 3
e dos termos do civil: o texto se monta de frases inteiras que já vêm prontas,
e quem escreve um papel de cartório não deveria precisar de `{% if %}` para
dizer que um registro não tem averbação.

**ELE NÃO AFIRMA NADA QUE A FICHA NÃO DIGA.** Não há fecho de certidão, não há
«confere com o original» e não há assinatura de oficial — é a ficha impressa, e
um papel que se pareça com certidão sem ser uma é o pior tipo de papel que esta
casa pode pôr no mundo.

**MAS CADA ATO DIZ QUEM O PRATICOU — LH13, 21/10/2026.** O oficial respondeu
«15 a»: o Livro 3 como o Livro 2. O CN-MA art. 458 manda todo registro e
averbação ser «datado e subscrito», e a ficha do Livro 2 fecha cada ato com
«Cidade/UF, data. Dou fé. A Escrevente Autorizada (NOME).». Aqui é o mesmo
fecho, pela mesma regra e o mesmo modelo (`ri_web.fecho_de_quem_praticou`,
`RI_FECHO_DO_ATO`), com o nome e a função gravados no ato na lavratura
(`ra_atos.lavrado_*`). Não é fecho de certidão: é o que o livro diz do ato. O
ato lavrado antes disso sai sem ele — não se deduz quem foi.
"""
from __future__ import annotations

from typing import Any

# `MODELO_FICHA_LIVRO3_PADRAO` — o texto de fábrica do papel RI_LIVRO3_FICHA — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/ri/RI_LIVRO3_FICHA.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _reais(centavos: Any) -> str:
    try:
        return f"R$ {int(centavos) / 100:,.2f}".replace(",", "X") \
            .replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"



def _natureza_no_papel(valor: Any) -> str:
    """A natureza como o papel a escreve — LT03, 20/10/2026.

    A tela do Livro 3 grava a CHAVE do catálogo (`ra_registro.NATUREZAS`), e o
    papel saía com «PACTO_ANTENUPCIAL» e «CEDULA_CREDITO_RURAL». Chave
    conhecida vira o nome dela, em maiúsculas como o papel sempre escreveu
    («HIPOTECA» continua «HIPOTECA»); o que não é chave (o acervo, que veio
    com o nome por extenso) sai como está.
    """
    texto = _texto(valor)
    import ra_registro as RA
    return RA.NATUREZAS[texto].upper() if texto in RA.NATUREZAS else texto


def _data_no_papel(valor: Any) -> str:
    """Data ISO (`2026-10-01`, `2026-10-20T20:37:36`) vira `01/10/2026` — LT03.

    A tela grava ISO e o papel a imprimia crua; a que já vem na forma do
    papel (o acervo) sai como está.
    """
    texto = _texto(valor)
    import re
    achado = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ][\d:.]+)?$", texto)
    return f"{achado.group(3)}/{achado.group(2)}/{achado.group(1)}" if achado else texto


def _textos_selo(numeros, con=None) -> dict:
    """Etiqueta inteira de sd_selos (so le). Sem texto, fica o numero.

    O carimbo precisa do texto do aparelho para emolumentos. O QR sai do
    numero de qualquer forma (`png_do_qr_do_selo`). Nao reseala e nao grava.

    COM `con`, LÊ O BANCO DE QUEM CHAMA — LT03, 20/10/2026. Sem ele, abre o
    arquivo da pasta padrão da instalação (`CARTORIO_GESTAO_DATA` ou
    `C:\\ProgramData\\CartorioGestao`), que é o caminho de antes: fora dessa
    pasta (outra pasta de dados, o ensaio, os testes) a etiqueta não era
    achada e o carimbo do termo saía sem os emolumentos.
    """
    wanted = []
    visto = set()
    for n in numeros:
        n = _texto(n)
        if n and n not in visto:
            visto.add(n)
            wanted.append(n)
    fora = {n: n for n in wanted}
    if not wanted:
        return fora
    if con is not None:
        from bd_nativo import banco
        bd = banco(con)
        for n in wanted:
            row = bd.um(
                "SELECT texto FROM sd_selos WHERE numero=%s "
                "ORDER BY obtido_em DESC, id DESC LIMIT 1",
                (n,))
            if row and str(row["texto"] or "").strip():
                fora[n] = str(row["texto"]).strip()
        return fora
    try:
        import os
        import banco_pg
        from bd_nativo import banco
        pasta = os.environ.get("CARTORIO_GESTAO_DATA") or r"C:\ProgramData\CartorioGestao"
        caminho = os.path.join(pasta, "cartorio_gestao.sqlite3")
        # `mode=ro`, como antes: no PostgreSQL o servidor recusa a escrita, e
        # no SQLite um arquivo que não existe não nasce vazio.
        uri = "file:" + caminho.replace("\\", "/") + "?mode=ro"
        con = banco_pg.conectar(uri, uri=True)
        try:
            bd = banco(con)
            for n in wanted:
                row = bd.um(
                    "SELECT texto FROM sd_selos WHERE numero=%s "
                    "ORDER BY obtido_em DESC, id DESC LIMIT 1",
                    (n,))
                if row and str(row["texto"] or "").strip():
                    fora[n] = str(row["texto"]).strip()
        finally:
            con.close()
    except Exception:                                          # noqa: BLE001
        return fora
    return fora


def _carimbos_odf_do_ato(a, textos: dict, imagens: dict) -> str:
    """Carimbos do ato (registro/averbacao + arquivamento), com QR.

    Mesmo desenho da ficha do Livro 2 (`carimbo_compacto_odf`): numero,
    emolumentos e QR. A cabeca em texto do ato permanece; isto entra logo
    abaixo, como carimbo, e nao no lugar dela.
    """
    from ri_odt import carimbo_compacto_odf

    pedacos = []
    ato_id = _texto(a.get("id")) or "ato"
    tipo = _texto(a.get("tipo")).upper()
    et_num = _texto(a.get("selo"))
    if et_num:
        rot = ("SELO DE REGISTRO" if tipo == "R"
               else "SELO DE AVERBACAO" if tipo == "AV"
               else "SELO DO ATO")
        pedacos.append(carimbo_compacto_odf(
            textos.get(et_num) or et_num, rotulo=rot, imagens=imagens,
            prefixo_qr=f"qr-l3-{ato_id}"))
    arq_num = _texto(a.get("selo_arquivamento"))
    if arq_num:
        folhas = _texto(a.get("folhas_arquivamento"))
        rot_arq = "SELO DE ARQUIVAMENTO" + (f" ({folhas} fl.)" if folhas else "")
        pedacos.append(carimbo_compacto_odf(
            textos.get(arq_num) or arq_num, rotulo=rot_arq, imagens=imagens,
            prefixo_qr=f"qr-l3-arq-{ato_id}"))
    return "".join(pedacos)


def fecho_do_ato(ato: dict, *, cidade: str, uf: str,
                 lido: dict | None = None) -> str:
    """O fecho do ato na ficha: «Cidade/UF, data. Dou fé. A Escrevente
    Autorizada (NOME).» Só monta.

    A REGRA É A DO LIVRO 2 (`ri_web.fecho_de_quem_praticou`), e não uma cópia:
    sem a data ou sem o nome gravado não há fecho, e o teor que já diz «dou
    fé» não o repete. O nome, a função e o artigo são os CONGELADOS no ato na
    lavratura (`lavrado_*`, LH13) — o ato antigo, sem eles, sai sem fecho.
    A data é a do ato, só o dia: o Livro 3 grava a hora junto (`db.now()`).
    `lido`: as duas frases lidas uma vez pela ficha (ajuste da casa → padrão).
    """
    from ri_web import fecho_de_quem_praticou
    return fecho_de_quem_praticou(
        cidade, uf, _texto(ato.get("data_ato"))[:10] or None, ato.get("teor"),
        _texto(ato.get("lavrado_nome")) or None,
        _texto(ato.get("lavrado_titulo")) or None,
        _texto(ato.get("lavrado_tratamento")) or None, lido=lido)


def contexto(*, registro: dict, atos: list, partes: list, serventia: dict,
             impresso_em: str, con=None) -> dict:
    """Os claros do modelo, já em texto. **Só monta — não grava.** Com `con`,
    lê dele a etiqueta do selo e as frases do fecho (o ajuste da casa).

    **CLARO SEM DADO SAI COMO TRAÇO, e não em branco**: o branco no papel se lê
    como «o registro não diz», e o traço se lê como «não há». A diferença
    aparece quando alguém confere a ficha contra o livro de papel.

    **CADA ATO FECHA COM QUEM O PRATICOU** (LH13, `fecho_do_ato`), depois do
    corpo — como na ficha do Livro 2, em que o fecho vem ao fim do teor.
    """
    cidade = (_texto(serventia.get("ri_cidade"))
              or _texto(serventia.get("cidade")) or "—")
    uf = (_texto(serventia.get("ri_uf"))
          or _texto(serventia.get("uf")) or "—")
    lido = None
    if con is not None:
        import ri_frases
        lido = ri_frases.ler(con, "RI_FECHO_DO_ATO", "RI_FECHO_DO_ATO_SEM_TITULO")
    linhas_partes = [
        f"  {_texto(p.get('nome'))} — {_texto(p.get('papel')) or 'parte'}"
        + (f" ({_texto(p.get('documento_numero'))})"
           if _texto(p.get("documento_numero")) else "")
        for p in partes]
    teor_registro = _texto(registro.get("teor"))
    linhas_atos = []
    imagens_selo: dict = {}
    carimbos_odf: dict = {}
    textos_selo = _textos_selo(
        [a.get("selo") for a in atos]
        + [a.get("selo_arquivamento") for a in atos], con=con)
    for a in atos:
        cabeca = (f"  {_texto(a.get('tipo'))}-{_texto(a.get('numero'))}"
                  f" – {_data_no_papel(a.get('data_ato')) or 'sem data'}"
                  f" – {'selo ' + _texto(a.get('selo')) if _texto(a.get('selo')) else 'SEM SELO'}")
        if _texto(a.get("selo_arquivamento")):
            cabeca += (f" – arquivamento 16.39: "
                       f"{_texto(a.get('selo_arquivamento'))} "
                       f"({_texto(a.get('folhas_arquivamento'))} folha(s))")
        corpo = _texto(a.get("teor")) or _texto(a.get("motivo_cancelamento"))
        # O ato R (registro primario) nao repete o corpo sob ATOS: o bloco
        # TEOR: ja traz ra_registros.teor. Mesma ideia da certidao L3
        # (_bloco_atos_certidao_livro3 pula tipo R). Se o registro ainda nao
        # tiver teor, o corpo do ato R permanece (unica fonte).
        if _texto(a.get("tipo")).upper() == "R" and teor_registro:
            corpo = ""
        frag = _carimbos_odf_do_ato(a, textos_selo, imagens_selo)
        extra = ""
        if frag:
            chave = f"@@CARIMBO_L3_{_texto(a.get('id')) or len(carimbos_odf)}@@"
            carimbos_odf[chave] = frag
            extra = "\n" + chave
        fecho = fecho_do_ato(a, cidade=cidade, uf=uf, lido=lido)
        linhas_atos.append(cabeca + extra + ("\n  " + corpo if corpo else "")
                           + ("\n  " + fecho if fecho else ""))

    folha_bruta = _texto(registro.get("folha"))
    return {
        "cidade": cidade,
        "uf": uf,
        "livro": _texto(registro.get("livro")) or "3",
        "numero": _texto(registro.get("numero")),
        "folha": (f", FLS. {folha_bruta}" if folha_bruta else ""),
        "folha_sozinha": folha_bruta or "—",
        "situacao": _texto(registro.get("situacao")) or "—",
        "natureza": _natureza_no_papel(registro.get("natureza")) or "—",
        "titulo_tipo": _texto(registro.get("titulo_tipo")) or "—",
        "titulo_numero": _texto(registro.get("titulo_numero")) or "—",
        "data_titulo": _data_no_papel(registro.get("data_titulo")) or "—",
        "valor": (_reais(registro.get("valor_centavos"))
                  if registro.get("valor_centavos") else "—"),
        "parcelas": _texto(registro.get("parcelas")) or "—",
        "vencimento_inicial": _data_no_papel(registro.get("vencimento_inicial")) or "—",
        "vencimento": _data_no_papel(registro.get("vencimento_final")) or "—",
        "juros": _texto(registro.get("juros")) or "—",
        "prenotacao": _texto(registro.get("prenotacao")) or "—",
        "cnm": _texto(registro.get("cnm")) or "—",
        "partes": "\n".join(linhas_partes) or "  (nenhuma parte informada)",
        "teor": teor_registro or "  (sem teor)",
        "garantia": _texto(registro.get("garantia")) or "  —",
        "condicoes": _texto(registro.get("condicoes")) or "  —",
        "atos": "\n\n".join(linhas_atos) or "  (nenhum ato lavrado)",
        "impresso_em": impresso_em,
        "_carimbos_odf": carimbos_odf,
        "_imagens_selo": imagens_selo,
    }


def cabecalho_ficha_livro3_odf(sv: dict | None, claros: dict,
                             usuario: str = "") -> tuple[str, dict]:
    """Cabeçalho da ficha impressa — **o mesmo desenho da ficha do Livro 2**.

    Brasão e serventia no topo de cada folha; abaixo, a grade com registro,
    livro auxiliar, folha e usuário. O corpo do modelo (`RI_LIVRO3_FICHA`) não
    repete a serventia — quem imprime vê o cartório no cabeçalho, como na
    matrícula.
    """
    from xml.sax.saxutils import escape

    from ri_odt import cabecalho_certidao_compacto_odf, html_para_odf

    topo_odf, imagens = cabecalho_certidao_compacto_odf(sv)
    s = sv or {}
    cidade = escape(str(claros.get("cidade") or s.get("ri_cidade") or ""))
    uf = escape(str(claros.get("uf") or s.get("ri_uf") or ""))
    registrador = escape(str(
        s.get("serventia_titular") or s.get("registrador") or "")).upper()
    substituta = escape(str(
        s.get("ri_substituta") or s.get("substituta") or "")).upper()
    titulo_reg = escape(str(s.get("serventia_titulo") or "Oficial Registrador(a)"))
    titulo_sub = escape(str(s.get("ri_titulo_substituta")
                            or s.get("titulo_substituta") or ""))
    numero = escape(str(claros.get("numero") or ""))
    livro = escape(str(claros.get("livro") or "3"))
    folha = escape(str(claros.get("folha_sozinha") or ""))
    cnm = escape(str(claros.get("cnm") or ""))
    user = escape(usuario or "—")
    cnm_linha = (f"<br>CNM Nº {cnm}"
                 if cnm and cnm not in ("—", "") else "")
    # HOTFIX-FOLHAS-FV: folha numerica segue a face em cada pagina
    # (12, 12v, 13…) — a pagina-mestre de `gerar_odt` troca a marca.
    if folha.isdigit():
        folha_cel = "<b>FLS. #FOLHA_PAGINA#</b>"
    else:
        folha_cel = (f"<b>FLS. {folha}</b>"
                     if folha and folha not in ("—", "") else "<b>FLS. —</b>")
    substituta_bloco = (
        f"<b>{substituta}</b><br>{titulo_sub}" if substituta else "")
    html = f"""<table border="1" cols="6.5cm,5.8cm,3.7cm">
<tr>
  <td rowspan="2"><b>REGISTRO DE IMÓVEIS</b><br>
    <b>SERVENTIA EXTRAJUDICIAL DO</b><br>
    <b>OFÍCIO ÚNICO DE {cidade}/{uf}</b><br>
    <b>{registrador}</b><br>
    {titulo_reg}<br>
    {substituta_bloco}</td>
  <td class="matricula-destaque"><b>REGISTRO Nº {numero}</b>{cnm_linha}</td>
  <td><b>LIVRO Nº {livro}</b><br>- REGISTRO AUXILIAR</td>
</tr>
<tr>
  <td>{folha_cel}</td>
  <td>USUÁRIO<br>{user}</td>
</tr>
</table>"""
    return topo_odf + html_para_odf(html, compacto=True), imagens


def montar_odt(*, texto_corpo: str, sv: dict | None, claros: dict,
               usuario: str = "", titulo: str = "") -> bytes:
    """Monta o `.odt` da ficha: cabeçalho da casa + corpo em texto."""
    from ri_odt import gerar_odt, texto_para_odf

    cab_odf, imagens = cabecalho_ficha_livro3_odf(sv, claros, usuario)
    imagens = dict(imagens or {})
    corpo_odf = texto_para_odf(texto_corpo)
    # Marcador sozinho no paragrafo vira a tabela do carimbo (nao pode
    # ficar DENTRO de text:p — tabela aninhada o LibreOffice descarta).
    for chave, frag in ((claros or {}).get("_carimbos_odf") or {}).items():
        alvo = f'<text:p text:style-name="P-just">{chave}</text:p>'
        if alvo not in corpo_odf:
            raise RuntimeError(f"carimbo sem paragrafo: {chave}")
        corpo_odf = corpo_odf.replace(alvo, frag)
    for nome, val in ((claros or {}).get("_imagens_selo") or {}).items():
        imagens[nome] = val
    _folha = str((claros or {}).get("folha_sozinha") or "").strip()
    return gerar_odt(corpo_odf, titulo=titulo, cabecalho_odf=cab_odf,
                     imagens=imagens or None,
                     # HOTFIX-FOLHAS-FV: rotulo da face por pagina.
                     folha_livro_inicio=int(_folha) if _folha.isdigit() else None)


def __getattr__(nome: str):
    """Os nomes antigos do texto de fábrica, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06A (19/10/2026) e mora em `modelos_padrao/`.
    Quem ainda importa o nome antigo recebe o padrão da base — o MESMO que o
    papel imprime, e não uma cópia que ficou para trás. Nome que não é de papel
    continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
