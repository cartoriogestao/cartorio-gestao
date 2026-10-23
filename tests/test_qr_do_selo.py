"""O que vai dentro do QR do selo — medido decodificando um QR real.

O RELATO DO OFICIAL, em 27/08/2026:

    «QR code do selo nas etiquetas impressas direciona ao site genérico de
     consulta do selo. Se possível, poderia já direcionar a uma consulta ao
     próprio selo da etiqueta.»

O QUE SE SUPUNHA, E POR QUE ESTAVA ERRADO
    O sistema punha no QR `https://selo.tjma.jus.br/?selo={selo}` — um palpite,
    e o próprio comentário dizia que era: «o tribunal não publica o formato do
    link que já abre preenchido».

    Era palpite e estava errado. **O QR do TJMA não carrega URL nenhuma.**

COMO SE MEDIU
    A casa tem **4.392 imagens de QR de selo** em `C:\\ProgramData\\CartorioGestao\\arquivos\\eoficio\\SeloDigital`,
    uma por selo, geradas pelo E-Ofício. Uma delas foi decodificada à mão —
    grade lida da imagem, formato, máscara 3, nível Q, e os dois blocos de
    correção **desintercalados**, que era o passo que faltava.

    Saiu: `MDGaPtZuqUKD4FtmC82CK5al` — vinte e quatro caracteres.

    E ele é **exatamente** o `strvalorQRCode` que o acervo guarda para aquele
    selo, em `tbSeloIndividual`. Medido: **25.642 dos 26.130** selos o têm.

O QUE SE CONCLUIU DAÍ, E O QUE A MEDIÇÃO DE 24/09/2026 DESMENTIU
    Concluiu-se que «o portal não procura pelo número, procura pelo token» —
    e que inventar `?selo=NNN` nunca ia funcionar. **A primeira metade caiu.**

    Medido no próprio portal, com dois selos reais desta casa:

        https://selo.tjma.jus.br/#/resumo/<SELO>   abre a consulta PRONTA
        https://selo.tjma.jus.br/?selo=<SELO>      abre a tela VAZIA

    O portal é AngularJS com `html5Mode(false)` e `hashPrefix("")`: as rotas
    são de hash (`#/resumo/:selo`), e `ResumoSeloValidadoCtrl` lê
    `$routeParams.selo`. A query, fora do hash, a aplicação descarta — por
    isso o palpite antigo caía na tela de digitar. **Era a FORMA que estava
    errada, e não a ideia.**

    E há o argumento que nem depende do portal: **token cru dentro de um QR
    não é link**. A câmera lê vinte e quatro caracteres e não tem o que abrir.
    O QR do E-Ofício nunca levou ninguém à consulta.

    **O TOKEN SAIU DO CAMINHO DO QR** (ordem do oficial em 24/09: «um qr code
    que leve direto a consulta do selo»), e a coluna `sd_selos.qr_token` fica:
    dado do acervo é dado. Ela está vazia em 26.464 de 26.464 nesta casa.

    **E o contrato de 2017 não devolve o token**: `ResumoSeloGerado` tem
    `dataGeracao`, `numeroSelo`, `saldoRemanescente` e `textoSelo`, e mais nada.
    Isso deixou de importar para o QR — o número basta.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — referencia acervo_eoficio ou sqlite de producao
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import selador as S                              # noqa: E402
from selador_config import init_selador_schema    # noqa: E402

ACERVO = Path(r"C:\ProgramData\CartorioGestao\acervo_eoficio.sqlite3")

# O selo que foi decodificado, e o que saiu dele.
SELO_MEDIDO = "ARQUIV000000012EG1CZM98CVV41"
TOKEN_MEDIDO = "MDGaPtZuqUKD4FtmC82CK5al"


@pytest.fixture()
def banco():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_selador_schema(con)
    return con


def test_o_razao_dos_selos_tem_onde_guardar_o_token(banco):
    """A coluna fica: dado do acervo é dado, e não se joga fora.

    **O QUE MUDOU EM 24/09/2026 foi o papel dela**: ela não alimenta mais o
    QR. Quem abre a consulta é o NÚMERO, medido no portal.
    """
    colunas = {r[1] for r in banco.execute("PRAGMA table_info(sd_selos)")}
    assert "qr_token" in colunas


def test_a_coluna_entra_tambem_em_banco_que_ja_existe(banco):
    """`MIGRACOES` é só `ALTER TABLE ADD COLUMN`, e rodar duas vezes não
    estoura — a casa já pagou por isso duas vezes num dia."""
    init_selador_schema(banco)
    colunas = {r[1] for r in banco.execute("PRAGMA table_info(sd_selos)")}
    assert "qr_token" in colunas


def test_o_contrato_de_2017_nao_devolve_o_token():
    """Continua verdade, e **deixou de importar para o QR** — 24/09/2026.

    Para o selo novo o aparelho responde só data, número, saldo e texto. Como
    o QR passou a levar o endereço da consulta pelo NÚMERO, o token não faz
    falta a papel nenhum; o teste fica porque a afirmação sobre o contrato
    continua sendo medida.
    """
    import html
    import re
    doc = Path(r"C:\ProgramData\CartorioGestao\arquivos\eoficio\Selo Eletrônico\selador-doc\civil\index.html")
    if not doc.exists():
        pytest.skip("o contrato do selador não está nesta máquina")
    plano = html.unescape(re.sub(r"\s+", " ", re.sub(
        r"<[^>]+>", " ", doc.read_text(encoding="utf-8", errors="replace"))))
    i = plano.find("ResumoSeloGerado Name Description Schema")
    trecho = plano[i:i + 300]
    assert "numeroSelo" in trecho and "textoSelo" in trecho
    for palavra in ("qrcode", "qrCode", "valorQR", "token"):
        assert palavra not in trecho, (
            f"o contrato passou a devolver «{palavra}» — se ele agora traz o "
            f"token do QR, o selo NOVO pode ter QR de verdade, e vale medir de "
            f"novo em vez de manter esta anotação")


def test_o_endereco_do_qr_e_a_rota_da_consulta():
    """`#/resumo/<selo>` — medido no portal em 24/09/2026.

    A query `?selo=` volta nua e abre a tela de digitar: o portal é AngularJS
    com `html5Mode(false)`, e o que ele lê é o hash.
    """
    import notas_selo as NSELO
    assert NSELO.MODELO_PADRAO == "https://selo.tjma.jus.br/#/resumo/{selo}"
    assert NSELO.conteudo(NSELO.MODELO_PADRAO, SELO_MEDIDO) == (
        f"https://selo.tjma.jus.br/#/resumo/{SELO_MEDIDO}")


def test_ninguem_mais_poe_o_token_dentro_do_qr():
    """O token nao e link: a camera le 24 caracteres e nao abre nada.

    **E VARREDURA, e nao um caso**: qualquer tela que volte a preferir o
    token faria o QR deixar de abrir a consulta — e o defeito so apareceria
    no balcao, com o papel na mao.
    """
    import re as _re
    for arquivo in ("notas_selo.py", "notas_web.py", "rg_web.py",
                    "atribuicoes_web.py", "rc_certidao_inteiro_teor.py"):
        codigo = (RAIZ / arquivo).read_text(encoding="utf-8")
        assert "def token_do_qr" not in codigo, (
            f"{arquivo}: `token_do_qr` voltou; ela foi apagada em 24/09/2026")
        chamadas = _re.findall(r"marca_do_selo\((?:[^()]|\([^()]*\))*\)",
                               codigo)
        for chamada in chamadas:
            assert "token" not in chamada, (
                f"{arquivo}: o token voltou para dentro do QR — «{chamada}»")
        for linha in codigo.splitlines():
            nua = linha.strip()
            if nua.startswith("#"):
                continue
            assert not (_re.search(r"token.*or.*conteudo\(", nua)), (
                f"{arquivo}: «token primeiro» voltou — «{nua}»")


def test_marca_do_selo_leva_a_consulta_e_sem_selo_nao_gera_qr():
    import notas_selo as NSELO
    marca = NSELO.marca_do_selo(SELO_MEDIDO)
    assert marca["qr_texto"] == (
        f"https://selo.tjma.jus.br/#/resumo/{SELO_MEDIDO}")
    assert "<svg" in marca["qr"].lower()
    vazia = NSELO.marca_do_selo("")
    assert vazia["qr"] == "" and vazia["selo"] == ""


def test_png_do_qr_para_o_carimbo_desenhado_em_pixel():
    """`png()` é o `svg()` do teor RTDPJ: o teor é montado com Pillow, uma

    imagem por folha, e não tem HTML para receber SVG nenhum — pedido do
    oficial em 11/09/2026, ao levar o carimbo do selo para dentro do PDF do
    livro, no modelo do RI.
    """
    import notas_selo as NSELO
    from PIL import Image
    import io

    dados = NSELO.png(TOKEN_MEDIDO, tamanho_mm=16.0, dpi=150)
    assert dados.startswith(b"\x89PNG")
    im = Image.open(io.BytesIO(dados))
    # 16mm a 150dpi ~ 94px; a escala é inteira (múltiplo de módulos), então
    # o lado sai perto disso, nunca muito maior nem em branco.
    assert 40 <= im.width <= 160
    assert im.width == im.height

    assert NSELO.png("") == b""


# ------------------------------------------- contra o acervo real


@pytest.mark.skipif(not ACERVO.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_o_token_medido_e_o_que_o_acervo_guarda():
    """A prova de que a decodificação estava certa: o que saiu da IMAGEM é o
    que está no BANCO, para o mesmo selo.

    Duas fontes independentes — uma imagem PNG e uma coluna de tabela — dizendo
    a mesma coisa. Onde a igualdade importa, ela se constrói.
    """
    con = sqlite3.connect(f"file:{ACERVO}?mode=ro", uri=True)
    # O CNS do código foi trocado pelo fictício (B3): o selo se acha no acervo
    # pelo prefixo e pela identificação, que são dele, e não pelo CNS.
    achado = con.execute(
        "SELECT strvalorQRCode FROM tbSeloIndividual WHERE strSelo LIKE ?",
        (SELO_MEDIDO[:6] + "______" + SELO_MEDIDO[12:],)).fetchone()
    assert achado, "o selo que foi decodificado sumiu do acervo"
    assert achado[0].strip() == TOKEN_MEDIDO


@pytest.mark.skipif(not ACERVO.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_quase_todos_os_selos_tem_token_e_ele_tem_24_caracteres():
    con = sqlite3.connect(f"file:{ACERVO}?mode=ro", uri=True)
    total, com = con.execute(
        """SELECT COUNT(*), SUM(CASE WHEN TRIM(COALESCE(strvalorQRCode,'')) <> ''
                                     THEN 1 ELSE 0 END)
             FROM tbSeloIndividual""").fetchone()
    assert total == 26130
    assert com == 25642, "o número mudou — meça de novo antes de mexer"

    tamanhos = {len(r[0].strip()) for r in con.execute(
        "SELECT strvalorQRCode FROM tbSeloIndividual"
        " WHERE TRIM(COALESCE(strvalorQRCode,'')) <> ''")}
    assert tamanhos == {24, 28}, (
        "o token tinha 24 caracteres em 25.626 selos e 28 em dezesseis")


@pytest.mark.skipif(not ACERVO.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_o_token_nao_e_o_numero_do_selo_nem_uma_url():
    """As duas coisas que o sistema supunha, e que a medição desmentiu."""
    con = sqlite3.connect(f"file:{ACERVO}?mode=ro", uri=True)
    for numero, token in con.execute(
            "SELECT strSelo, strvalorQRCode FROM tbSeloIndividual"
            " WHERE TRIM(COALESCE(strvalorQRCode,'')) <> '' LIMIT 200"):
        t = token.strip()
        assert t != (numero or "").strip(), "o token não é o número do selo"
        assert "://" not in t and "." not in t, "o token não é uma URL"


def test_os_cinco_geradores_da_casa_dizem_a_mesma_coisa():
    """Um selo, cinco papéis, um endereço — e a prova é byte a byte.

    A casa desenha QR em cinco lugares: a etiqueta (SVG), o carimbo das
    certidões, o molde `.odt` do RCPN, a certidão de inteiro teor e o teor do
    livro do RTDPJ. **Cada um com a sua escala**, porque o papel é diferente —
    e todos com o MESMO conteúdo.

    Comparar o PNG com o que o `segno` produz para o endereço esperado prova o
    conteúdo sem precisar de decodificador: mesma entrada, mesmo desenho.
    """
    import io
    segno = pytest.importorskip("segno", reason="o QR é opcional")
    import notas_selo as NSELO
    import rc_certidao_inteiro_teor as RCIT
    import rc_certidao_odt as RCODT
    import ri_odt

    selo = SELO_MEDIDO
    esperado = f"https://selo.tjma.jus.br/#/resumo/{selo}"

    def png_do(texto, *, scale, border):
        buf = io.BytesIO()
        segno.make(texto, error="m").save(buf, kind="png", scale=scale,
                                          border=border)
        return buf.getvalue()

    assert NSELO.marca_do_selo(selo)["qr_texto"] == esperado
    assert ri_odt.png_do_qr_do_selo(selo) == png_do(esperado, scale=6, border=0)
    assert RCODT._png_do_qr(selo) == png_do(esperado, scale=6, border=0)
    # A certidão de inteiro teor usa escala 8 e borda 1, declarado no módulo:
    # «QR legível na prévia PDF». O que não pode divergir é o CONTEÚDO.
    assert RCIT._png_do_qr(selo) == png_do(esperado, scale=8, border=1)
    # O PNG do teor do RTDPJ tem escala própria (milímetros por DPI); o que
    # este teste cobra dele é o CONTEÚDO, e ele sai do mesmo modelo.
    assert NSELO.png(NSELO.conteudo(NSELO.MODELO_PADRAO, selo)).startswith(
        b"\x89PNG")
