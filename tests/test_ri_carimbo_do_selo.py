"""O CARIMBO DO SELO NA FICHA DO RI — correcao de 15/09/2026.

    «preciso que revise a averbacao da 3110, o teor foi com espacamento no
     meio, nao foi o carimbo do selo e o relatorio de emolumentos deve ir
     junto com o carimbo do selo e qr code»

SAO TRES DEFEITOS, E O OFICIAL OS VIU COMO UM PAPEL TORTO.

1. **O TEOR GUARDAVA O MARCADOR DO SELO.**
   `versao_final_para_lavrar` compunha «teor + relacao de emolumentos + espaco
   reservado para o selo», e o espaco reservado e um desenho tipografico com
   `[ selo / verificacao ]` e **vinte espacos** no meio. O desenho previa que o
   carimbo de verdade entraria depois; so que **o teor congela na corrente de
   hash**. Medido no ato 3737: dez linhas gravadas, e nove nao eram do ato — a
   minuta de onde ele saiu tem uma.

2. **O CARIMBO LIA A COLUNA DO ATO, QUE GUARDA O NUMERO.**
   `ri_atos.selo_texto` recebe `str(numero)` de `ato_selado.vincular_ao_ato` —
   28 caracteres, sem valor nenhum dentro. A etiqueta inteira, com todos os
   fundos, mora em `sd_selos.texto`. Por isso
   `valores_para_o_carimbo(selo_texto)` devolvia **vazio**, e o carimbo nunca
   mostrava os emolumentos. **Isso valia para todo ato do RI selado
   automaticamente.**

3. **O QR NAO SAIA.** O campo de colar QR saiu da tela em 14/09 (medido:
   em 1.245 atos, zero tinham QR colado), e nada passou a preencher `selo_qr`.

E O CONSERTO DOS DOIS PRIMEIROS CRIOU UM QUARTO. Com a etiqueta inteira
chegando ao carimbo, a conta passou a sair **em triplicata**: uma dentro da
etiqueta, uma no resumo curto do ato (`ri_atos.emolumentos`) e uma na relacao
rotulada «Emolumentos:».

    **Some a do meio, e so ela.** O resumo curto e literalmente os mesmos dois
    valores que a etiqueta ja traz, sem rotulo e sem os fundos — e quem o
    passava era o meu proprio chamador.

    **As outras duas ficam, e a decisao nao e minha.** Eu suprimi a relacao
    rotulada invocando «sem repeticoes» (a regra da certidao do RCPN, 01/09) e
    **derrubei o teste de quem a construiu** — ela existe de proposito, porque
    na etiqueta os valores vem no meio de uma frase corrida e ali vem
    legiveis, que e o «relatorio de emolumentos» que o oficial pediu. Recuei:
    **escolha de papel e de quem assina**, e ficou declarada no roteiro.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import notas_selo as NSELO
import ri_odt
from ri_lavrar_teor import (
    MARCA_EMOLUMENTOS,
    MARCA_SELO,
    sem_fecho_antigo,
    valores_para_o_carimbo,
    versao_final_para_lavrar,
)

# A etiqueta como o aparelho da rede local a entrega — copiada do selo real do
# ato 3737 (AV-04/3.110), com o numero trocado.
ETIQUETA = (
    "Poder Judiciário – TJMA. Selo: AVESVD000000IFWIQRMJW7CGUA95, "
    "15/09/2026 17:34:08, Ato: 16.22.2, Parte(s): BANCO DO BRASIL S.A, "
    "IRENE ANDRADE MACHADO CARDOSO, Total R$ 134,43 Emol R$ 120,03 "
    "FERC R$ 3,60 FADEP R$ 4,80 FEMP R$ 4,80 FERRFIS R$ 1,20 "
    "Consulte em https://selo.tjma.jus.br")
CODIGO = "AVESVD000000IFWIQRMJW7CGUA95"
TEOR = ("AV-04/3.110 - CANCELAMENTO INTEGRAL DE HIPOTECA CEDULAR DE 1o GRAU. "
        "Fundamento: art. 251, I, da Lei no 6.015/1973. Dou fé.")
ITENS = [{"codigo": "16.22.2", "descricao": "De ato sem valor declarado",
          "emolumentos": "120,03", "ferc": "3,60", "fadep": "4,80",
          "femp": "4,80", "ferrfis": "1,20", "total": "134,43"}]


def _visivel(odf: str) -> str:
    """O texto que sai no papel, sem as marcas do ODF."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", odf)).strip()


# ------------------------------------------- 1. o teor guarda o ato, e so


def test_o_teor_lavrado_nao_leva_o_marcador_do_selo():
    """O `[ selo / verificacao ]` com vinte espacos foi o que ele viu."""
    saida = versao_final_para_lavrar(
        TEOR, ITENS, com_emolumentos=False, com_espaco_selo=False)
    assert MARCA_SELO not in saida
    assert MARCA_EMOLUMENTOS not in saida
    assert "[ selo / verificacao ]" not in saida
    assert "  " not in saida.replace(TEOR, ""), (
        "nao pode sobrar espacamento de desenho no teor gravado")
    assert saida.strip() == TEOR.strip(), (
        "o teor gravado e o ato, e nada alem dele")


def test_a_rota_de_lavrar_desliga_as_duas_composicoes():
    """A guarda e no CHAMADOR, e nao numa reescrita do modulo de outrem.

    Os dois parametros sao da propria API de `ri_lavrar_teor` — consertar o
    chamador nao e mexer no modulo de outra passada.
    """
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    chamada = re.search(
        r"versao_final_para_lavrar\(\s*teor,\s*itens_calc,([^)]*)\)", codigo)
    assert chamada, "a rota de lavrar deixou de compor o teor final"
    argumentos = chamada.group(1)
    assert "com_emolumentos=False" in argumentos
    assert "com_espaco_selo=False" in argumentos


def test_o_fecho_manual_da_minuta_continua_sendo_tirado():
    """`sem_fecho_antigo` e o que interessa da composicao, e ele fica.

    A minuta importada traz «Emolumentos: R$ ______ (...) Selo de Fiscalizacao
    Digital no ______», que nao pode conviver com o selo que o aparelho emite.
    """
    com_marcador = TEOR + "\n\n" + MARCA_EMOLUMENTOS + "\nSoma: Total R$ 1,00"
    assert sem_fecho_antigo(com_marcador).strip() == TEOR.strip()


# ------------------------------- 2. o carimbo le a etiqueta, e nao o numero


def test_o_numero_do_selo_nao_tem_valores_dentro():
    """A medicao que explica por que o carimbo saia sem emolumentos."""
    assert valores_para_o_carimbo(CODIGO) == "", (
        "um codigo de 28 caracteres nao declara valor nenhum — era isto que "
        "chegava ao carimbo enquanto ele lia `ri_atos.selo_texto`")
    assert "Total R$ 134,43" in valores_para_o_carimbo(ETIQUETA)


def test_o_carimbo_com_a_etiqueta_traz_todos_os_fundos():
    papel = _visivel(ri_odt.bloco_selo_odf(ETIQUETA, [None, None], None))
    for sigla in ("Total R$ 134,43", "Emol R$ 120,03", "FERC R$ 3,60",
                  "FADEP R$ 4,80", "FEMP R$ 4,80", "FERRFIS R$ 1,20"):
        assert sigla in papel, f"o carimbo saiu sem {sigla}"


def test_o_carimbo_nao_traz_o_resumo_curto_do_ato():
    """A conta saia TRES vezes, e uma delas era do meu chamador.

    Uma dentro da etiqueta, uma no resumo curto (`ri_atos.emolumentos`, colado
    no fim da linha do selo) e uma na relacao rotulada «Emolumentos:». **A do
    meio some**: ela e literalmente os mesmos dois valores que a etiqueta ja
    traz, sem rotulo e sem os fundos.

    AS OUTRAS DUAS FICAM, E A DECISAO NAO E MINHA. A relacao rotulada e o
    «relatorio de emolumentos» que o oficial pediu em 15/09 — ela repete os
    valores da etiqueta de proposito, porque na etiqueta eles vem no meio de
    uma frase corrida e ali vem legiveis. Eu havia suprimido a segunda por
    «sem repeticoes» (a regra da certidao do RCPN, 01/09) e isso derrubou o
    teste de quem a construiu: **e escolha de papel, e quem decide e quem
    assina.** Ficou declarada no roteiro para ele decidir.
    """
    papel = _visivel(ri_odt.bloco_selo_odf(ETIQUETA, [None, None], None))
    assert papel.count("Total R$ 134,43") == 2, (
        "a etiqueta e a relacao rotulada — e NAO o resumo curto do ato")
    com_resumo = _visivel(ri_odt.bloco_selo_odf(
        ETIQUETA, [None, None], "Total R$ 134,43 Emol R$ 120,03"))
    assert com_resumo.count("Total R$ 134,43") == 3, (
        "se o chamador passar o resumo curto, a conta sai tres vezes — e por "
        "isso `emolumentos_do_carimbo` nao o passa quando a etiqueta ja diz")


def test_a_conta_nao_tem_por_onde_sair_duas_vezes():
    """O resumo curto nao e passado, porque nao ha mais parametro para ele.

    ATE 16/09 HAVIA UMA GUARDA NO CHAMADOR: duas funcoes de quinze linhas
    decidiam se `ri_atos.emolumentos` acompanhava a etiqueta, para a conta nao
    sair duas vezes na mesma linha. **Medido ao reescrever o carimbo: o
    parametro chegava preenchido e NUNCA ERA LIDO** — desde 15/09, quando o
    desenho passou a imprimir os valores da propria etiqueta.

    Peca pronta que ninguem usa, na forma de argumento: nenhum varredor a via,
    porque a funcao tinha chamador e o parametro chegava cheio. A guarda que
    fica e mais forte que a de ontem — **nao ha por onde passar o resumo**.
    """
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert "def selo_convertido(selo_texto, rotulo=None):" in codigo, (
        "`selo_convertido` mudou de assinatura — se ela voltar a receber "
        "emolumentos, a conta pode sair duas vezes na mesma linha")
    assert "def emolumentos_do_carimbo" not in codigo
    assert "def emolumentos_da_abertura" not in codigo


def test_o_selo_a_mao_sem_valores_ainda_ganha_a_relacao():
    """A linha continua util no caso que a fez nascer.

    Selo digitado a mao so com o codigo: a etiqueta nao declara valor nenhum,
    e o resumo curto do ato e a UNICA fonte — entao ele passa.
    """
    papel = _visivel(ri_odt.bloco_selo_odf(
        CODIGO, [None, None], "Total R$ 134,43 Emol R$ 120,03"))
    assert "Total R$ 134,43" in papel
    assert papel.count("Total R$ 134,43") == 1


# --------------------------------------------------------------- 3. o QR


def test_o_qr_sai_do_numero_quando_nao_ha_token():
    """Sem token vale o modelo padrao, que ao menos abre o portal certo."""
    endereco = NSELO.conteudo(NSELO.MODELO_PADRAO, CODIGO, "")
    assert endereco.endswith(CODIGO)
    assert endereco.startswith("https://selo.tjma.jus.br")


def test_o_qr_vira_png_para_o_odt():
    """O `.odt` embute bitmap; `svg()` nao serve ao pacote de imagens."""
    bruto = NSELO.png(NSELO.conteudo(NSELO.MODELO_PADRAO, CODIGO, ""),
                      tamanho_mm=12.5)
    if not bruto:
        import pytest
        pytest.skip("segno não instalado — o carimbo sai sem QR, de propósito")
    assert bruto[:8] == b"\x89PNG\r\n\x1a\n", "tem de ser PNG de verdade"


def test_o_quadro_so_desenha_a_imagem_quando_ela_existe():
    """Nome sem bytes abriria a ficha com um quadro quebrado no lugar do QR."""
    com = ri_odt.bloco_selo_odf(ETIQUETA, ["qr9-1.png", None], None)
    sem = ri_odt.bloco_selo_odf(ETIQUETA, [None, None], None)
    assert "Pictures/qr9-1.png" in com
    assert "Pictures/" not in sem


def test_a_ficha_liga_o_carimbo_ao_razao_e_leva_o_qr():
    """Varre a tela: o carimbo le o razao, e o livro leva o QR.

    A METADE DE CIMA E DE 15/09 e continua valendo: `ri_atos.selo_texto`
    guarda o NUMERO de 28 caracteres, e a etiqueta com os valores mora em
    `sd_selos` — ler a coluna do ato era o defeito que ele relatou. **Este
    guarda procurava o texto `etiqueta_do_ato(a)`**, e a ficha passou a ler o
    razao numa consulta so, para todos os atos; a propriedade ficou, o
    literal nao. Desde 24/09/2026 ele cobra a PROPRIEDADE: a consulta usa a
    chave inteira, e o razao e perguntado ANTES da coluna do ato.

    **A METADE DE BAIXO VIROU AO CONTRARIO DUAS VEZES.** Ate 16/09 exigia o
    QR; de 16/09 a 24/09 proibia (ordem do oficial: «nao faz sentido qr code
    de selo e link de acesso a consulta de selo no livro»); e desde 24/09 o
    exige outra vez — ordem da CORREGEDORIA, trazida por ele: «qr code em
    todos os selos». O QR agora nasce DENTRO de `carimbo_compacto_*`, e o que
    este guarda recusa e uma segunda geracao dele na ficha: dois lugares
    gerando o mesmo QR divergem no primeiro conserto.
    """
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    ficha = codigo[codigo.index("def contexto_ficha"):
                   codigo.index("def ri_ficha_odt")]

    # SAO DOIS DESENHOS, e cada um le o razao na sua consulta: a TELA da
    # matricula (`ri_ficha` -> `carimbo_da_tela`) e o PAPEL da ficha
    # (`contexto_ficha` -> `etiquetas_do_ato`). A regra se cobra nos dois.
    i = codigo.index("def carimbo_da_tela(")
    tela = codigo[i:codigo.index("def carimbo_da_abertura(", i)]
    j = ficha.index("def etiquetas_do_ato(")
    papel = ficha[j:j + 1200]
    for onde, pedaco, leitura in (
            ("tela", codigo[codigo.index("def ri_ficha("):i], tela),
            ("papel", ficha, papel)):
        # A etiqueta vem do razao, pela chave inteira — `tabela` MAIS `ato_id`.
        assert "FROM sd_selos" in pedaco, (
            f"o carimbo da {onde} deixou de ler o razao dos selos")
        assert "tabela='ri_atos' AND ato_id" in pedaco, (
            f"na {onde}, a chave do selo tem de ser `tabela` MAIS `ato_id` — "
            f"por `ato_id` sozinho vem selo de outra atribuicao")
        # E o razao e perguntado ANTES do numero cru que o ato guarda.
        assert "selo_do_ato.get(" in leitura, (
            f"o carimbo da {onde} deixou de perguntar ao razao")
        assert (leitura.index("selo_do_ato.get(")
                < leitura.index('a["selo_texto"]')), (
            f"o carimbo da {onde} voltou a receber `a['selo_texto']` primeiro "
            f"— ele guarda o NUMERO, e a etiqueta com os valores mora no razao")

    # O QR vem de dentro do carimbo, e de um lugar so.
    for morto in ("qr_do_ato", "qr_por_ato", "qr_gerado", "qr_da_abertura",
                  "qr_abertura_gerado", "qr-abertura-1.png"):
        assert morto not in ficha, (
            f"`{morto}` voltou: a ficha passou a gerar QR por conta propria, "
            f"ao lado do que `carimbo_compacto_*` ja gera")
    assert "carimbo_compacto_odf" in codigo and "carimbo_compacto_html" in codigo, (
        "a ficha deixou o carimbo que leva o QR")
    assert "imagens=imagens_selo" in codigo, (
        "o papel da ficha deixou de entregar os PNG do QR ao pacote — o link "
        "sairia escrito e a imagem faltando")
