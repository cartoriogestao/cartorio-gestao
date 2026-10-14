"""
O QR do selo de fiscalizacao, para a etiqueta de reconhecimento de firma.

PARA QUE SERVE
    O selo do TJMA tem 28 caracteres — `RECFIR000000D0XB4FK298AWP401`. Quem
    recebe o documento e quer conferir se o reconhecimento existe precisa
    digitar os 28 no portal do tribunal, sem errar um. Na pratica ninguem
    confere. Com o QR, aponta a camera e pronto.

ONDE SE CONFERE, E COMO EU SEI
    https://selo.tjma.jus.br/ — o Portal do Selo Eletronico do TJMA.

    Confirmei em duas fontes independentes: a pagina do proprio tribunal
    (Selo de Fiscalizacao -> "Para conferir a autenticidade do SELO DE
    FISCALIZACAO ELETRONICO, click no banner abaixo" -> selo.tjma.jus.br), e o
    rodape das certidoes ja emitidas por esta serventia, que traz impresso
    "Consulte em https://selo.tjma.jus.br".

O ENDERECO QUE ABRE A CONSULTA — MEDIDO NO PORTAL EM 24/09/2026
    Ordem do oficial no mesmo dia: «um qr code que leve direto a consulta do
    selo, nao apenas ao site do tribunal».

    O que funciona e a ROTA DE HASH, e nao a query:

        https://selo.tjma.jus.br/#/resumo/<SELO>    abre a consulta PRONTA
        https://selo.tjma.jus.br/?selo=<SELO>       abre a tela VAZIA

    E o porque esta no proprio portal: ele e uma aplicacao AngularJS que
    declara `html5Mode(false)` com `hashPrefix("")` — as rotas sao de hash, e
    sao quatro (`#/resumo/:selo`, `#/agregador/:selo/`, `#/invalido/:selo`,
    `#/tabela-custas`). O controlador `ResumoSeloValidadoCtrl` le
    `$routeParams.selo` e consulta; query fora do hash a aplicacao DESCARTA.

    CONFERIDO EM DOIS SELOS REAIS DESTA CASA, de duas atribuicoes: a certidao
    de casamento `CERTID000000MLF3KFMARL4M5E98` (RCPN, 24/09 as 14h04) e a
    matricula `MATRIC000000FQ2IF3MJ7KUI7600` (RI, 14h55). As duas abrem com o
    item da tabela, o cartorio, o delegatario, as partes e os valores.

    O CONTEUDO CONTINUA CONFIGURAVEL (tela Ajustar etiqueta): se a
    corregedoria mudar o portal, e um campo — e nao uma atualizacao do
    sistema.

POR QUE O NUMERO CONTINUA IMPRESSO AO LADO DO QR
    QR borrado na termica, etiqueta amassada no bolso, camera de celular
    velho. O numero legivel e o que sobra quando o QR falha — e num documento
    que vale por decadas, redundancia nao e desperdicio.

POR QUE SVG, E NAO IMAGEM
    A termica imprime em 203 ou 300 pontos por polegada. Imagem pronta tem uma
    resolucao so e sai serrilhada numa das duas; o SVG e desenho vetorial e sai
    exato nas duas. E cabe dentro do proprio HTML, sem arquivo nenhum no disco.
"""
from __future__ import annotations

PORTAL_TJMA = "https://selo.tjma.jus.br/"

# A ROTA DA CONSULTA, medida no portal em 24/09/2026 — ver o cabecalho.
# O portal e AngularJS com `html5Mode(false)`: o que ele le e o hash.
ROTA_DA_CONSULTA = "#/resumo/{selo}"

# O que o QR carrega. `{selo}` e `{codigo}` sao trocados pelos valores do ato.
#
#   **ERA `?selo={selo}` ATE 24/09/2026**, e era palpite declarado como tal —
#   «o tribunal nao publica o formato do link direto». Medido agora: aquela
#   forma abre a tela de digitar, VAZIA; esta abre a consulta pronta.
MODELO_PADRAO = PORTAL_TJMA + ROTA_DA_CONSULTA

# A forma antiga, que fica NOMEADA para o sistema reconhecer a configuracao
# velha e nao para ser usada: quem tiver `etiqueta_qr_url` gravada com ela
# esta com o QR levando a tela vazia.
MODELO_ANTIGO_DA_QUERY = PORTAL_TJMA + "?selo={selo}"


def conteudo(modelo: str, selo: str, codigo: str = "") -> str:
    """O texto que vai dentro do QR.

    Modelo vazio devolve o proprio numero do selo: um leitor de QR qualquer
    mostra os 28 caracteres na tela, o que ja poupa a digitacao mesmo sem
    internet. E o comportamento que nunca depende de o portal existir.
    """
    selo = (selo or "").strip()
    if not selo:
        return ""
    modelo = (modelo or "").strip()
    if not modelo:
        return selo
    return (modelo.replace("{selo}", selo)
                  .replace("{codigo}", (codigo or "").strip()))


def svg(texto: str, tamanho_mm: float = 16.0) -> str:
    """O QR como SVG, pronto para entrar no HTML. Vazio se nao der.

    SEM O `segno` INSTALADO, DEVOLVE VAZIO — e a etiqueta sai com o numero do
    selo do mesmo jeito. Biblioteca que falta nao pode impedir o balcao de
    imprimir: o selo impresso ja vale por si, o QR e conveniencia.

    CORRECAO DE ERRO EM 'M' (15%), e nao no minimo.
        Termica borra, o rolo tem poeira e a etiqueta e colada em papel que
        dobra. Em 'L' o QR fica menor mas para de ler com pouca sujeira; em 'Q'
        cresce demais para 16 mm. 'M' e o meio que aguenta balcao.

    SEM BORDA BRANCA (`border=0`), porque o espaco em volta ja e o respiro do
    proprio leiaute — e cada milimetro de uma tira de 30 mm esta contado.
    """
    texto = (texto or "").strip()
    if not texto:
        return ""
    try:
        import segno
    except ImportError:
        return ""
    try:
        import io
        qr = segno.make(texto, error="m")
        modulos = qr.symbol_size(border=0)[0]
        buf = io.BytesIO()                    # o segno escreve bytes, nao texto
        qr.save(buf, kind="svg", border=0, xmldecl=False, svgns=True,
                unit="mm", scale=tamanho_mm / modulos)
        return buf.getvalue().decode("utf-8")
    except Exception:                                          # noqa: BLE001
        # QR e conveniencia; nunca motivo para a etiqueta nao sair.
        return ""


def png(texto: str, *, tamanho_mm: float = 16.0, dpi: int = 150) -> bytes:
    """O QR como PNG (bitmap), para colar dentro de um PDF desenhado em pixel.

    Mesma razao de existir do `svg()` — QR e conveniencia, nunca motivo para o
    papel nao sair —, so que para o teor RTDPJ, que e montado com Pillow (uma
    imagem por folha) e nao tem HTML para receber um SVG. `dpi` casa com a
    escala em que a folha do teor e desenhada (150, como o A4 de
    `rg_teor_rtdpj`).

    SEM O `segno` INSTALADO, DEVOLVE VAZIO — o carimbo sai so com o numero e
    a linha de valores, sem QR, do mesmo jeito que a etiqueta de firma faz.
    """
    texto = (texto or "").strip()
    if not texto:
        return b""
    try:
        import segno
    except ImportError:
        return b""
    try:
        import io
        qr = segno.make(texto, error="m")
        modulos = qr.symbol_size(border=0)[0]
        tamanho_px = max(1, round(tamanho_mm / 25.4 * dpi))
        escala = max(1, round(tamanho_px / modulos))
        buf = io.BytesIO()
        qr.save(buf, kind="png", border=0, scale=escala)
        return buf.getvalue()
    except Exception:                                          # noqa: BLE001
        return b""


def disponivel() -> bool:
    """Se da para gerar QR nesta instalacao. A tela usa isto para explicar."""
    try:
        import segno                                           # noqa: F401
    except ImportError:
        return False
    return True


# **`token_do_qr` FOI APAGADA EM 24/09/2026, e a medição que a trouxe fica.**
#
#   O QR do E-Oficio carrega um token de 24 caracteres — decodificado a mao de
#   uma das 4.392 imagens do acervo, `MDGaPtZuqUKD4FtmC82CK5al`, e igual ao
#   `strvalorQRCode` em 25.642 dos 26.130 selos. Isso e verdade.
#
#   **O QUE NAO SE SUSTENTOU FOI A CONCLUSAO**: «o portal procura pelo token».
#   Medido no portal em 24/09, ele procura pelo NUMERO —
#   `#/resumo/<SELO>` abre a consulta pronta, conferido em dois selos reais
#   desta casa. E token cru dentro de um QR nao e link: a camera le vinte e
#   quatro caracteres e nao tem o que abrir.
#
#   A COLUNA `sd_selos.qr_token` FICA — dado do acervo e dado, e nao se joga
#   fora. O que saiu foi o caminho que a punha dentro do QR.


def marca_do_selo(selo: str, *,
                  modelo: str = MODELO_PADRAO, codigo: str = '',
                  tamanho_mm: float = 16.0) -> dict:
    """Número + SVG do QR para o papel. Sem selo, sem QR.

    **O QR LEVA O ENDEREÇO DA CONSULTA DAQUELE SELO** — `#/resumo/<número>`,
    medido no portal em 24/09/2026. Selo vazio devolve SVG vazio: um QR que
    abre consulta vazia parece conferível e não é.

    **O TOKEN DO APARELHO SAIU DAQUI, E A MEDIÇÃO QUE O TROUXE CONTINUA DE
    PÉ.** O QR do E-Ofício carregava um token de 24 caracteres
    (`MDGaPtZuqUKD4FtmC82CK5al`, em 25.642 dos 26.130 selos do acervo) — isso
    foi decodificado à mão e é verdade. O que não se sustentou foi a conclusão
    de que «o portal procura pelo token»: ele procura pelo número, e a prova
    está no cabeçalho deste arquivo.

    E há o argumento que nem depende do portal: **token cru dentro de um QR
    não é link**. A câmera lê vinte e quatro caracteres e não tem o que abrir.
    """
    selo = (selo or '').strip()
    if not selo:
        return {'selo': '', 'qr': '', 'qr_texto': '',
                'qr_possivel': disponivel()}
    qr_texto = conteudo(modelo, selo, codigo)
    return {
        'selo': selo,
        'qr': svg(qr_texto, float(tamanho_mm)),
        'qr_texto': qr_texto,
        'qr_possivel': disponivel(),
    }

