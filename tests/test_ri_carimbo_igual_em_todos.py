"""O CARIMBO DO SELO É O MESMO NA TELA E NO PAPEL — 15/09/2026.

    «preze por esse modelo tanto no html como no odt e pdf, exatamente assim
     em todos» — o oficial, depois de aprovar o modelo compacto

SÃO DOIS DESENHOS, E NÃO TRÊS. O `.odt` e o HTML se desenham cada um do seu
    jeito — tabela de ODF lá, `grid` aqui —, e **o PDF nasce do `.odt`**: quem
    o converte é o LibreOffice. Logo, garantir dois basta.

O QUE NÃO PODE DIVERGIR É O QUE ESTÁ ESCRITO, e por isso ele mora num lugar
    só: `ri_odt.partes_do_carimbo`. Se cada desenho montasse as suas linhas,
    elas divergiriam no primeiro conserto — a tela mostraria um carimbo e o
    papel imprimiria outro, e é o papel que a serventia assina. É a
    `normalizar_nome` pela quinta vez.

QR EM TODOS OS SELOS, DESDE 24/09/2026 — ordem da corregedoria.

    «a nova ordem eh qr code em todos os selos, pedido da corregedoria. o
     pedido da substituta ta tudo certo, temos que ter o carimbo do selo
     completo com qr code» — o oficial

    | onde | quem desenha | tem QR? |
    |---|---|---|
    | o LIVRO (ficha da matrícula), tela e papel | `carimbo_compacto_*` | **sim** |
    | certidão do RI, do RCPN, traslado das Notas | `carimbo_do_selo_odf` | sim |

    **DE 16/09 A 24/09 O LIVRO SAIU SEM QR E NUMA LINHA SÓ** — ordem do
    oficial então: «não faz sentido qr code de selo e link de acesso a
    consulta de selo no livro». A substituta pediu a volta em 22/09, o papel
    voltou, a tela ficou com a linha de 16/09 — e os dois desenhos passaram a
    dizer coisas diferentes do mesmo selo. Foi isso que estes testes pegaram.

O QUE ESTES TESTES PROTEGEM
    1. As mesmas linhas, na mesma ordem, nos dois desenhos do livro.
    2. A mesma grade do carimbo grande: dois por fileira, o terceiro desce.
    3. O QR do papel que sai — o conteúdo, não o formato.
    4. Nenhum desenho remonta o texto por conta própria.
    5. **O carimbo do livro TEM QR e link** — a ordem da corregedoria.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_odt

ETIQUETA = (
    "Poder Judiciário – TJMA. Selo: AVESVD000000IFWIQRMJW7CGUA95, "
    "15/09/2026 17:34:08, Ato: 16.22.2, Parte(s): BANCO DO BRASIL S.A, "
    "IRENE ANDRADE MACHADO CARDOSO, Total R$ 134,43 Emol R$ 120,03 "
    "FERC R$ 3,60 FADEP R$ 4,80 FEMP R$ 4,80 FERRFIS R$ 1,20 "
    "Consulte em https://selo.tjma.jus.br")
SEGUNDO = ETIQUETA.replace("AVESVD000000IFWIQRMJW7CGUA95",
                           "ARQUIV000000ZZZZYYYYXXXXWW11")
TERCEIRO = ETIQUETA.replace("AVESVD000000IFWIQRMJW7CGUA95",
                            "PRENOT000000AAAABBBBCCCCDD22")


def _linhas_visiveis(marcado: str) -> list[str]:
    """O texto que a pessoa lê, sem as marcas e sem o QR."""
    sem_qr = re.sub(r"<svg.*?</svg>", " ", marcado, flags=re.DOTALL)
    bruto = re.sub(r"<[^>]+>", "\n", sem_qr)
    return [ln.strip() for ln in bruto.split("\n") if ln.strip()]


# ---------------------------------------------- o que se diz é um só


def test_a_tela_e_o_papel_do_livro_dizem_exatamente_o_mesmo():
    odf = ri_odt.carimbo_compacto_odf(ETIQUETA, rotulo="SELO DE AVERBAÇÃO")
    html = ri_odt.carimbo_compacto_html(ETIQUETA, rotulo="SELO DE AVERBAÇÃO")
    assert _linhas_visiveis(odf) == _linhas_visiveis(html), (
        "o carimbo da tela e o do livro divergiram — o conteúdo tem de sair "
        "de `partes_do_carimbo`, e não ser remontado em cada desenho")


def test_com_dois_selos_tambem():
    dois = ETIQUETA + " " + SEGUNDO
    assert (_linhas_visiveis(ri_odt.carimbo_compacto_odf(dois))
            == _linhas_visiveis(ri_odt.carimbo_compacto_html(dois)))


def test_as_linhas_sao_as_quatro_combinadas():
    """Rótulo, número, ato·data e valores — nessa ordem, e nada mais."""
    p = ri_odt.partes_do_carimbo(ETIQUETA, "SELO DE AVERBAÇÃO")
    assert p["rotulo"] == "SELO DE AVERBAÇÃO"
    assert p["numero"] == "AVESVD000000IFWIQRMJW7CGUA95"
    assert p["linhas"][0] == "AVESVD000000IFWIQRMJW7CGUA95"
    assert p["linhas"][1] == "Ato: 16.22.2 · 15/09/2026 17:34:08"
    assert p["linhas"][2].startswith("Total R$ 134,43 Emol R$ 120,03")
    assert "FERRFIS R$ 1,20" in p["linhas"][2]
    assert "linha" not in p, (
        "a linha única de 16/09 voltou — ela era o que fazia a tela desenhar "
        "um carimbo diferente do papel")
    assert len(p["linhas"]) == 3, (
        "a frase corrida do aparelho não volta ao carimbo — ela é o que o "
        "oficial mandou tirar")


def test_a_conta_aparece_uma_vez_em_cada_um():
    for marcado in (ri_odt.carimbo_do_selo_odf(ETIQUETA, ["q.png"]),
                    ri_odt.carimbo_compacto_odf(ETIQUETA),
                    ri_odt.carimbo_compacto_html(ETIQUETA)):
        texto = " ".join(_linhas_visiveis(marcado))
        assert texto.count("Total R$ 134,43") == 1


# --------------------------------------------------- a mesma grade


def test_dois_por_fileira_e_o_terceiro_desce_no_papel():
    def fileiras(marcado):
        # Cada carimbo traz uma tabela interna de uma linha; as fileiras da
        # grade de fora são o total menos uma por carimbo.
        return (marcado.count("<table:table-row>")
                - marcado.count("SeloInterno"))
    assert fileiras(ri_odt.carimbo_do_selo_odf(ETIQUETA, ["a.png"])) == 1
    assert fileiras(ri_odt.carimbo_do_selo_odf(
        ETIQUETA + " " + SEGUNDO, ["a.png", "b.png"])) == 1
    assert fileiras(ri_odt.carimbo_do_selo_odf(
        ETIQUETA + " " + SEGUNDO + " " + TERCEIRO,
        ["a.png", "b.png", "c.png"])) == 2, (
        "o terceiro carimbo tem de descer para a fileira de baixo")


def test_a_tela_do_livro_desenha_a_linha_e_deixa_ela_quebrar():
    """E não corta: esconder um fundo cobrado para caber é pior que duas linhas."""
    css = (RAIZ / "static" / "app.css").read_text(encoding="utf-8")
    assert ".carimbo-linha {" in css, "a tela do livro ficou sem estilo"
    i = css.index(".carimbo-linha {")
    regra = css[i:css.index("}", i)]
    assert "nowrap" not in regra, (
        "com `nowrap` a etiqueta maior que a caixa seria cortada, e o que "
        "sai do fim da linha é justamente a conta")
    assert "word-break" in regra
    # E o desenho antigo saiu inteiro: classe sem quem a emita é CSS morta.
    for morta in (".carimbos-do-ato", ".carimbo-selo", ".carimbo-qr"):
        assert morta not in css, (
            f"{morta} ficou na folha de estilo sem ninguém emitir")


def test_a_meia_fileira_que_sobra_sai_sem_borda():
    """Caixa vazia ao lado pareceria um segundo selo que faltou colar."""
    um = ri_odt.carimbo_do_selo_odf(ETIQUETA, ["a.png"])
    assert um.count('table:style-name="Cel-selo-compacto"') == 1
    assert 'table:style-name="Cel-selo-interna"' in um


# ------------------------------------------------------------ o QR


def test_o_qr_continua_no_papel_que_sai_da_casa():
    """A certidão e o traslado guardam o QR: quem confere está do lado de fora."""
    p = ri_odt.partes_do_carimbo(ETIQUETA)
    assert p["qr_texto"].endswith("AVESVD000000IFWIQRMJW7CGUA95")
    assert p["qr_texto"].startswith("https://selo.tjma.jus.br")
    odf = ri_odt.carimbo_do_selo_odf(ETIQUETA, ["qr9-1.png"])
    assert "Pictures/qr9-1.png" in odf, "no papel ele é o PNG do pacote"


def test_o_carimbo_do_livro_tem_qr_e_link():
    """Ordem da corregedoria, 24/09/2026: «qr code em todos os selos».

    ATÉ 24/09 ESTE TESTE AFIRMAVA O CONTRÁRIO — «o carimbo do livro não tem
    QR nem link», ordem do oficial de 16/09. A ordem mudou; o teste muda de
    contrato, e o nome antigo fica aqui para quem o procurar.

    O QR E O LINK SÃO A MESMA COISA DE DOIS JEITOS: a câmera lê um, quem não
    tem câmera digita o outro. Por isso os dois se cobram juntos, nos dois
    desenhos — e o endereço é o da CONSULTA daquele selo, e não o portal seco.
    """
    numero = "AVESVD000000IFWIQRMJW7CGUA95"
    consulta = f"https://selo.tjma.jus.br/#/resumo/{numero}"

    imagens: dict = {}
    papel = ri_odt.carimbo_compacto_odf(ETIQUETA, "SELO DE REGISTRO",
                                        imagens=imagens)
    assert imagens, "o papel do livro não gravou o PNG do QR no pacote"
    assert "draw:image" in papel and "Pictures/" in papel, (
        "o QR sumiu do carimbo do livro no papel")
    assert f"Confira em {consulta}" in papel

    tela = ri_odt.carimbo_compacto_html(ETIQUETA, "SELO DE REGISTRO")
    assert "data:image/png;base64," in tela, (
        "o QR sumiu do carimbo do livro na tela")
    assert f"Confira em {consulta}" in tela
    assert numero in tela, "e o número continua lá, para quem digita"


def test_a_etiqueta_do_aparelho_nao_leva_o_link_para_dentro_da_linha():
    """A frase do aparelho traz «Consulte em https://…» — e ela não entra.

    O link que o carimbo escreve é o NOSSO, o da consulta daquele selo, e ele
    vem de `qr_texto`; o do aparelho é o portal seco. Os dois juntos seriam
    dois endereços para a mesma conferência.
    """
    p = ri_odt.partes_do_carimbo(ETIQUETA)
    for linha in p["linhas"]:
        assert "Consulte" not in linha
        assert "http" not in linha


# --------------------------------- ninguém remonta o texto por conta própria


def test_os_dois_desenhos_leem_a_fonte_unica():
    """E são TRÊS desenhos desde 17/09/2026 — o molde do RCPN entrou.

    A montagem das linhas desceu um andar, para
    `selo_no_papel.linhas_do_carimbo`, porque o molde `.odt` que o oficial
    desenha pede cada linha pelo nome e não podia chamar `ri_odt`. **A régua
    aqui deixou de contar uma linha de código e passou a cobrar a
    propriedade**: `ri_odt` não remonta nada por conta própria.
    """
    codigo = (RAIZ / "ri_odt.py").read_text(encoding="utf-8")
    for funcao in ("def carimbo_do_selo_odf(", "def carimbo_compacto_odf(",
                   "def carimbo_compacto_html("):
        i = codigo.index(funcao)
        corpo = codigo[i:i + 2200]
        assert "carimbos_do_ato(" in corpo, (
            f"{funcao} deixou de ler `carimbos_do_ato` — é assim que a tela "
            f"e o papel voltam a divergir")

    # E O QUE SE ESCREVE TAMBÉM TEM UM LUGAR SÓ — 24/09/2026. A tela e o
    # papel do livro divergiram exatamente aí: cada um decidia as suas
    # linhas e o seu link.
    i = codigo.index("def carimbo_compacto_html(")
    assert "linhas_desenhadas(" in codigo[i:i + 3000], (
        "a tela voltou a decidir sozinha o que o carimbo escreve")
    i = codigo.index("def _uma_celula_de_carimbo(")
    assert "linhas_desenhadas(" in codigo[i:i + 3000], (
        "o papel voltou a decidir sozinho o que o carimbo escreve")

    # A MONTAGEM MORA EM `selo_no_papel`, e `ri_odt` só a pede.
    i = codigo.index("def partes_do_carimbo(")
    corpo = codigo[i:codigo.index("def carimbos_do_ato(", i)]
    assert "SNP.linhas_do_carimbo(" in corpo, (
        "`partes_do_carimbo` deixou de pedir as linhas a `selo_no_papel` — e "
        "o molde do RCPN pede a ela: é assim que dois papéis assinados passam "
        "a dizer coisas diferentes do mesmo selo")
    for remontagem in ('"Ato: "', "f\"Ato: {", "Requerente:",
                       "linhas.append(valores)"):
        assert remontagem not in corpo, (
            f"`ri_odt` voltou a montar linha por conta própria ({remontagem})")

    # E o molde do RCPN pede as mesmas linhas, pelo NOME de cada uma.
    molde = (RAIZ / "rc_certidao_odt.py").read_text(encoding="utf-8")
    for pedaco in ("SNP.ato_e_data(", "SNP.requerente(",
                   "SNP.valores_com_marcas(", "SNP.link_de_consulta("):
        assert pedaco in molde, (
            f"o molde do RCPN deixou de pedir {pedaco} — e volta a montar a "
            f"caixa do selo por conta própria")


def test_o_pdf_nao_e_um_terceiro_desenho():
    """Ele nasce do `.odt`; garantir os dois desenhos basta.

    Se um dia o PDF passar a ser montado por fora, este teste fica vermelho e
    obriga quem o fizer a incluir o terceiro desenho na comparação.
    """
    codigo = (RAIZ / "impressao_pdf.py").read_text(encoding="utf-8")
    assert "carimbo_do_selo" not in codigo, (
        "o PDF passou a desenhar o carimbo sozinho — ele vinha do `.odt`, e "
        "agora são três desenhos para manter iguais")
