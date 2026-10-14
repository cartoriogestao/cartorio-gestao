"""Os módulos da casa, e a cor de cada um — relato #32 do oficial, 30/08/2026.

    «cada módulo deve ter uma cor no layout, cada submódulo deve ter uma
     derivação diferente dessa cor, e precisa reorganizar, unir o que é
     semelhante e colocar tudo em ordem»

POR QUE A REGRA SAIU DO TEMPLATE
    Qual módulo é a tela em que estou já se decidia — mas dentro do
    `base.html`, em dez linhas de `{% set %}`. Ali ela servia a **uma** coisa:
    abrir o grupo certo do menu.

    Agora ela serve a **três** — o grupo do menu, a cor da tela e o rótulo do
    cabeçalho —, e regra que serve três lugares não pode morar em um template:
    a segunda cópia divergiria da primeira no dia em que alguém criasse uma
    rota nova. É a `normalizar_nome` pela sexta vez.

    **E ela é a MESMA regra, não uma parecida.** Há teste que roda as duas —
    esta e a do template — contra **todas** as rotas do sistema e exige que
    concordem em cada uma. Onde a igualdade importa, ela se constrói.

A COR É IDENTIDADE, E NÃO ENFEITE
    Ela existe para que quem está no balcão saiba **em que atribuição está**
    antes de ler o título — e para que perceba quando entrou na errada. Por
    isso ela aparece em três lugares, e não em um: a marca do grupo no menu, a
    faixa do alto da tela e o rótulo ao lado do título.

    **A derivação do submódulo é calculada, e não escolhida.** Escolhida à mão,
    ela seria uma segunda paleta para manter — e a terceira seção de um módulo
    nasceria sem cor, ou com a cor de outro.

O QUE ESTE MÓDULO NÃO FAZ
    **Não decide o que aparece no menu.** Ele diz de quem é a tela e qual é a
    cor; o que cada grupo lista continua no `base.html`, que é onde se lê.
"""
from __future__ import annotations

from typing import Any

# ----------------------------------------------- as conversões
#
# Elas vêm ANTES de tudo porque a paleta se **calcula na importação**: as
# cores dos módulos saem de `cor_do_matiz`, que mede contraste, que lê RGB.


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _rgb(cor: str) -> tuple[int, int, int]:
    c = _texto(cor).lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _hex(r: int, g: int, b: int) -> str:
    return "#%02x%02x%02x" % (max(0, min(255, r)), max(0, min(255, g)),
                              max(0, min(255, b)))


# --------------------------------------------------------- o contraste


def luminancia(cor: str) -> float:
    """A luminância relativa da cor, pela definição da WCAG. Só calcula."""
    def canal(v: int) -> float:
        x = v / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(v) for v in _rgb(cor))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(cor_a: str, cor_b: str) -> float:
    """A razão de contraste entre duas cores, de 1 a 21. Só calcula.

    **Existe para ser MEDIDA, e não julgada a olho.** Cor bonita que ninguém lê
    é pior que cor feia: quem está no balcão com o cliente na frente não pede
    para diminuir o brilho da tela.
    """
    a, b = luminancia(cor_a), luminancia(cor_b)
    claro, escuro = max(a, b), min(a, b)
    return (claro + 0.05) / (escuro + 0.05)



# AS CORES: O MATIZ SE ESCOLHE, A COR SE CALCULA.
#
#   **A primeira paleta foi escolhida a olho, e a medicao a desmentiu.** O
#   «Livros e acervo» tinha **exatamente o mesmo matiz** de «atencao» (22 graus)
#   e o Registro de Imoveis ficava a 21 de «feito» — dois modulos inteiros
#   pintados com a cor que nesta casa quer dizer outra coisa. Cor de modulo que
#   parece alarme faz o operador ler alarme onde nao ha.
#
#   Entao o que se escreve aqui e o **matiz** — a decisao humana, de quanto
#   cada modulo se afasta dos vizinhos e das cores reservadas —, e a cor sai de
#   uma conta que **garante o contraste por construcao**: `_cor_do_matiz` baixa
#   o brilho ate a cor sustentar texto branco a 5:1.
#
#   **Escrever o `#rrggbb` a mao traria o problema de volta**: alguem
#   escolheria por gosto, o contraste cairia, e ninguem mediria — foi o que eu
#   fiz na primeira versao.
#
# OS MATIZES RESERVADOS, que nenhum modulo pode chegar perto:
#   4 graus  = erro (`--danger`)
#   22 graus = atencao (`--warning`)
#   155 graus = feito (`--ok`)
#
# Os seis modulos coloridos ficam a **40 graus ou mais** uns dos outros e a 30
# ou mais das reservadas. Os dois ultimos sao neutros de proposito: «Livros e
# acervo» e sepia, que e a cor de arquivo, e «Administrativo» e cinza — os dois
# com saturacao baixa, para nao disputarem matiz com quem lavra ato.
MATIZES_RESERVADOS: dict[str, int] = {"erro": 4, "atencao": 22, "feito": 155}

# O teto do brilho, para que as oito saiam sobrias e parecidas entre si: sem
# ele, o azul do Malote saia com 11,7:1 de contraste — vibrante, e destoando
# das outras sete num sistema de cartorio.
TETO_DO_BRILHO = 0.56
CONTRASTE_MINIMO = 5.0


def _de_hsv(matiz: float, saturacao: float, brilho: float) -> str:
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(matiz / 360, saturacao, brilho)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def cor_do_matiz(matiz: float, saturacao: float = 0.72) -> str:
    """A cor daquele matiz, escura o bastante para levar texto branco. So calcula.

    **O CONTRASTE E GARANTIDO POR CONSTRUCAO**, e nao conferido depois: o
    brilho baixa ate a cor atingir `CONTRASTE_MINIMO` contra o branco. Amarelo e
    verde precisam de muito mais escurecimento que azul e roxo, e uma paleta
    escrita a mao erra justamente ai — foi o que aconteceu na primeira versao,
    onde o amarelo saiu com 3,6:1.
    """
    brilho = TETO_DO_BRILHO
    while brilho > 0.12:
        cor = _de_hsv(matiz, saturacao, brilho)
        if contraste(cor, "#ffffff") >= CONTRASTE_MINIMO:
            return cor
        brilho -= 0.01
    return _de_hsv(matiz, saturacao, 0.12)


# (chave, nome, matiz, saturacao)
_DECLARADOS: tuple[tuple[str, str, int, float], ...] = (
    ("NOTAS", "Tabelionato de Notas", 60, 0.72),
    ("RI", "Registro de Imóveis", 100, 0.72),
    ("RCPN", "Registro Civil das Pessoas Naturais", 195, 0.72),
    ("MALOTE", "Processos e malote", 240, 0.72),
    ("RCPJ_RTD", "RCPJ e RTD", 285, 0.72),
    ("PROTESTO", "Protesto", 330, 0.72),
    # OS DOIS NEUTROS. Sepia para o acervo, cinza para o administrativo: eles
    # nao lavram ato, e por isso nao disputam matiz com quem lavra.
    # **A SATURACAO DAQUI E BAIXA DE PROPOSITO, e a medicao mandou.** Sepia e
    # intrinsecamente da faixa do laranja (matiz 28), que fica a **6 graus** do
    # matiz de «atencao» — e com saturacao alta ele seria lido como alarme. Com
    # 0,25 ele vira marrom-acinzentado: continua sendo a cor de arquivo, e para
    # de disputar matiz. O primeiro valor era 0,55, e o teste o reprovou.
    ("LIVROS", "Livros e acervo", 28, 0.25),
    ("ADM", "Administrativo", 225, 0.12),
)

MODULOS: tuple[dict, ...] = tuple(
    {"chave": chave, "nome": nome, "matiz": matiz, "saturacao": sat,
     "cor": cor_do_matiz(matiz, sat)}
    for chave, nome, matiz, sat in _DECLARADOS)

POR_CHAVE = {m["chave"]: m for m in MODULOS}

# O PAINEL NÃO É DE MÓDULO NENHUM, e por isso não tem cor de módulo: ele é a
# tela de todos. Pintá-lo com a cor de um faria parecer que pertence àquele.
SEM_MODULO = ""


def modulo_da_tela(endpoint: Any, atribuicao: Any = "") -> str:
    """De qual módulo é aquela tela. Só calcula.

    **É A REGRA DO MENU, palavra por palavra** — e há teste que compara as duas
    contra todas as rotas do sistema.

    `atribuicao` é o filtro da tela de certidão, que serve três atribuições: é
    ele que decide de quem ela é naquele momento.
    """
    aqui = _texto(endpoint)
    if not aqui or aqui == "dashboard":
        return SEM_MODULO

    # O LIVRO 3 É DO REGISTRO DE IMÓVEIS — ele é o Registro Auxiliar *do* RI, e
    # a numeração dele já saía de `ri_numeracao`.
    certidao_do_livro3 = (aqui.startswith("atribuicoes_certid")
                          and _texto(atribuicao).upper() == "LIVRO3")
    if (aqui.startswith("ri_") or aqui.startswith("usucapiao")
            or aqui.startswith("livro3") or certidao_do_livro3):
        return "RI"
    if aqui.startswith("notas_"):
        return "NOTAS"
    if aqui.split("_")[0] in ("expediente", "expedientes", "task", "tasks",
                              "inspection", "inspections", "processos", "processo"):
        return "MALOTE"
    if aqui.startswith("protesto"):
        return "PROTESTO"
    if aqui.startswith("rcpn"):
        return "RCPN"
    if aqui.startswith("rcpj_rtd") or aqui.startswith("atribuicoes_certid"):
        return "RCPJ_RTD"
    # O NÚCLEO E A CARGA SERVEM AS SEIS, e por isso não moram dentro de nenhuma.
    if (aqui.startswith("nucleo_") or aqui.startswith("implantacao")
            or aqui in ("atribuicoes_importar", "importar_padrao_tela",
                        "importar_padrao_manual", "importar_padrao_preencher")):
        return "LIVROS"
    return "ADM"


# ------------------------------------------------------- as derivações


def clarear(cor: str, quanto: float) -> str:
    """A cor puxada para o branco. Só calcula. `quanto` de 0 a 1."""
    r, g, b = _rgb(cor)
    return _hex(*(round(v + (255 - v) * quanto) for v in (r, g, b)))


def escurecer(cor: str, quanto: float) -> str:
    """A cor puxada para o preto. Só calcula."""
    r, g, b = _rgb(cor)
    return _hex(*(round(v * (1 - quanto)) for v in (r, g, b)))


def cor_da_secao(cor_do_modulo: str, indice: int) -> str:
    """A cor de uma seção, **derivada** da do módulo. Só calcula.

    **CALCULADA, E NÃO ESCOLHIDA.** Uma segunda paleta escrita à mão seria uma
    lista a manter, e a seção que nascesse amanhã sairia sem cor — ou com a de
    outro módulo. Aqui ela nasce com a derivação certa no dia em que existe.

    O passo é pequeno de propósito: a seção é **do** módulo, e uma derivação
    muito distante faria parecer outro módulo.

    **E O PASSO FOI MEDIDO, depois de o primeiro repetir.** Com 0,12 e teto
    0,45, a quinta seção em diante saía **igual** — e o maior grupo do menu tem
    **sete**: o Registro Civil mostrava «Assento já lavrado» e «Comunicações e
    remessas» com o mesmo tom, e o oficial pediu derivação **diferente**.

    Com 0,07 e teto 0,56 as sete saem distintas, e a última continua abaixo
    de 4,5:1 contra a cor do módulo — ou seja, **ainda é lida como parte do
    mesmo módulo**, que é a outra metade da regra.
    """
    return clarear(cor_do_modulo, min(0.56, 0.07 * max(0, int(indice))))


# ----------------------------------------------------- o que a tela usa


def contexto(endpoint: Any, atribuicao: Any = "") -> dict:
    """O que toda tela precisa saber sobre o próprio módulo. Só calcula."""
    chave = modulo_da_tela(endpoint, atribuicao)
    m = POR_CHAVE.get(chave)
    if m is None:
        return {"modulo": SEM_MODULO, "modulo_nome": "", "modulo_cor": "",
                "modulo_cor_clara": "", "modulo_cor_escura": ""}
    return {"modulo": chave, "modulo_nome": m["nome"], "modulo_cor": m["cor"],
            "modulo_cor_clara": clarear(m["cor"], 0.88),
            "modulo_cor_escura": escurecer(m["cor"], 0.25)}


def folha_de_estilo() -> str:
    """As variáveis de cor de todos os módulos, para o `<style>` da página.

    **GERADA, E NÃO ESCRITA NO CSS.** Escrita lá, ela seria a segunda lista a
    manter: módulo novo entraria no menu e ficaria sem cor, ou — pior — com a
    cor de outro, porque alguém copiaria a linha vizinha.
    """
    linhas = [":root{"]
    for m in MODULOS:
        c = m["chave"].lower().replace("_", "-")
        linhas.append(f"--mod-{c}:{m['cor']};")
        linhas.append(f"--mod-{c}-clara:{clarear(m['cor'], 0.88)};")
        linhas.append(f"--mod-{c}-escura:{escurecer(m['cor'], 0.25)};")
    linhas.append("}")
    return "".join(linhas)
