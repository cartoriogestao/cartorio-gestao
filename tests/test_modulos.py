"""Os modulos e as cores — relato #32 do oficial.

    «cada modulo deve ter uma cor no layout, cada submodulo deve ter uma
     derivacao diferente dessa cor»

O QUE ESTES TESTES GUARDAM

    **Que a regra nova e a MESMA do menu**, e nao uma parecida. Ela e comparada
    com a do `base.html` em **todas** as rotas do sistema: se divergirem numa
    so, o menu abriria um grupo e a tela se pintaria de outro — e quem estivesse
    no balcao veria duas respostas para a mesma pergunta.

    **Que as cores se distinguem e se leem.** O contraste de cada uma contra o
    branco e medido pela conta da WCAG, e nao julgado a olho: cor bonita que
    ninguem le e pior que cor feia, porque quem esta com o cliente na frente nao
    para para diminuir o brilho da tela.

    **Que a cor do Protesto nao e a do erro.** Vermelho ja quer dizer «erro»
    nesta casa, e um modulo inteiro pintado de erro faz ler alarme onde nao ha.

    **Que a derivacao da secao e CALCULADA.** Escrita a mao, seria uma segunda
    paleta a manter, e a secao que nascesse amanha sairia sem cor.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modulos as M                                              # noqa: E402

# ------------------------------------------------- a regra e a mesma


def _modulo_pelo_template(endpoint: str, atribuicao: str = "") -> str:
    """A regra do `base.html`, transcrita **do template de hoje**.

    Transcrever parece duplicar, e e o contrario: e o unico jeito de PROVAR que
    as duas concordam. Se alguem mudar o template sem mudar `modulos.py`, esta
    transcricao continua igual ao template antigo e o teste seguinte — que le o
    template de verdade — acusa.
    """
    aqui = endpoint or ""
    if not aqui or aqui == "dashboard":
        return ""
    certidao_do_livro3 = (aqui.startswith("atribuicoes_certid")
                          and atribuicao == "LIVRO3")
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
    if (aqui.startswith("nucleo_") or aqui.startswith("implantacao")
            or aqui in ("atribuicoes_importar", "importar_padrao_tela",
                        "importar_padrao_manual", "importar_padrao_preencher")):
        return "LIVROS"
    return "ADM"


def test_a_regra_concorda_com_a_do_menu_em_TODAS_as_rotas(tmp_path):
    """**Se divergirem numa só**, o menu abre um grupo e a tela se pinta de
    outro — duas respostas para a mesma pergunta, na cara de quem atende."""
    from app import create_app

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    divergem = []
    for regra in app.url_map.iter_rules():
        nome = regra.endpoint
        for atrib in ("", "LIVRO3"):
            a = M.modulo_da_tela(nome, atrib)
            b = _modulo_pelo_template(nome, atrib)
            if a != b:
                divergem.append(f"{nome} (atribuição={atrib!r}): "
                                f"módulo={a} menu={b}")
    assert not divergem, "\n".join(divergem)


def test_toda_rota_do_sistema_cai_em_algum_modulo(tmp_path):
    """Rota sem módulo é tela sem cor e sem grupo — ela existe e ninguém a
    acha."""
    from app import create_app

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    sem = []
    for regra in app.url_map.iter_rules():
        nome = regra.endpoint
        if nome in ("static", "dashboard") or nome.startswith("static"):
            continue
        if not M.modulo_da_tela(nome):
            sem.append(nome)
    assert not sem, "estas rotas não caem em módulo nenhum: " + ", ".join(sem)


def test_o_painel_nao_tem_cor_de_modulo():
    """**Ele é a tela de todos.** Pintá-lo com a cor de um faria parecer que
    pertence àquele."""
    assert M.modulo_da_tela("dashboard") == M.SEM_MODULO
    assert M.contexto("dashboard")["modulo_cor"] == ""


# ------------------------------------------------- as cores


def test_toda_cor_se_le_com_texto_branco_por_cima():
    """Medido pela conta da WCAG, e não julgado a olho.

    4,5:1 é o mínimo da norma para texto normal. Cor bonita que ninguém lê é
    pior que cor feia.
    """
    fracas = [f"{m['nome']} ({m['cor']}): {M.contraste(m['cor'], '#ffffff'):.1f}:1"
              for m in M.MODULOS if M.contraste(m["cor"], "#ffffff") < 4.5]
    assert not fracas, "estas cores não sustentam texto branco: " + "; ".join(fracas)


def test_as_cores_se_distinguem_entre_si():
    """Duas cores parecidas fazem o operador achar que está no mesmo módulo."""
    iguais = []
    for i, a in enumerate(M.MODULOS):
        for b in M.MODULOS[i + 1:]:
            if a["cor"] == b["cor"]:
                iguais.append(f"{a['nome']} e {b['nome']}")
    assert not iguais, "módulos com a mesma cor: " + "; ".join(iguais)
    assert len({m["cor"] for m in M.MODULOS}) == len(M.MODULOS)


def _matiz(cor: str) -> float:
    """O matiz da cor, em graus. É a medida certa para «parecem a mesma cor?»."""
    import colorsys

    r, g, b = (v / 255 for v in M._rgb(cor))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def _saturacao(cor: str) -> float:
    import colorsys

    r, g, b = (v / 255 for v in M._rgb(cor))
    return colorsys.rgb_to_hsv(r, g, b)[1]


def _distancia_de_matiz(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


# QUANTO BASTA PARA DUAS CORES NAO SE CONFUNDIREM. **Medido, e nao arbitrado**:
# a paleta declarada em `modulos.py` separa os seis modulos coloridos por 40
# graus ou mais, e das reservadas por 30 ou mais. Estes numeros sao esses.
GRAUS_ENTRE_MODULOS = 35
GRAUS_DAS_RESERVADAS = 28
# Abaixo disto a cor e neutra: cinza e sepia nao disputam matiz com ninguem.
SATURACAO_DE_COR = 0.30


@pytest.mark.parametrize("quer_dizer", sorted(M.MATIZES_RESERVADOS))
def test_nenhum_modulo_usa_a_cor_que_ja_quer_dizer_outra_coisa(quer_dizer):
    """**Um módulo inteiro pintado de erro faz ler alarme onde não há.**

    E este teste **pegou a primeira paleta**, que eu tinha escolhido a olho: o
    «Livros e acervo» saiu com matiz 22 — **exatamente** o de «atenção» — e o
    Registro de Imóveis a 21 de «feito».

    > A primeira versão deste teste media **contraste** para julgar semelhança,
    > e contraste mede luminância, não cor: verde e vermelho escuros têm
    > contraste baixo entre si sendo cores opostas. Ele reprovava seis dos oito
    > módulos, todos por engano. **A medida de «parecem a mesma cor?» é o
    > matiz.**
    """
    reservado = M.MATIZES_RESERVADOS[quer_dizer]
    perto = []
    for m in M.MODULOS:
        if _saturacao(m["cor"]) < SATURACAO_DE_COR:
            continue                      # neutro não disputa matiz
        d = _distancia_de_matiz(_matiz(m["cor"]), reservado)
        if d < GRAUS_DAS_RESERVADAS:
            perto.append(f"{m['nome']} ({d:.0f}°)")
    assert not perto, (
        f"estes módulos têm matiz perto do de «{quer_dizer}» ({reservado}°): "
        + ", ".join(perto))


def test_os_modulos_coloridos_se_separam_no_circulo_das_cores():
    """Duas cores vizinhas fazem o operador achar que está no mesmo módulo."""
    coloridos = [m for m in M.MODULOS
                 if _saturacao(m["cor"]) >= SATURACAO_DE_COR]
    juntos = []
    for i, a in enumerate(coloridos):
        for b in coloridos[i + 1:]:
            d = _distancia_de_matiz(_matiz(a["cor"]), _matiz(b["cor"]))
            if d < GRAUS_ENTRE_MODULOS:
                juntos.append(f"{a['nome']} x {b['nome']} ({d:.0f}°)")
    assert not juntos, "módulos com cores vizinhas demais: " + "; ".join(juntos)


def test_os_neutros_sao_neutros_de_verdade():
    """**Sépia e cinza não disputam matiz com quem lavra ato** — e é por isso
    que eles podem ficar perto de um matiz reservado sem confundir."""
    neutros = {m["chave"] for m in M.MODULOS
               if _saturacao(m["cor"]) < SATURACAO_DE_COR}
    assert "ADM" in neutros, "o Administrativo tinha de ser neutro"


def test_a_cor_nao_esta_escrita_a_mao_no_modulo():
    """**O matiz se escolhe; a cor se calcula.**

    Escrever o `#rrggbb` traria de volta o problema que a medição achou: alguém
    escolhe por gosto, o contraste cai, e ninguém mede.
    """
    codigo = (RAIZ / "modulos.py").read_text(encoding="utf-8")
    declarados = codigo[codigo.index("_DECLARADOS"):
                        codigo.index("MODULOS: tuple[dict, ...] = tuple(")]
    assert "#" not in declarados.replace("# ", ""), (
        "há cor escrita à mão na declaração dos módulos — ela sai de "
        "`cor_do_matiz`")


def test_a_derivacao_da_secao_e_calculada_e_anda_na_ordem():
    """Escrita à mão seria uma segunda paleta; a terceira seção nasceria sem."""
    cor = "#1f5e8c"
    tons = [M.cor_da_secao(cor, i) for i in range(5)]
    assert tons[0] == cor, "a primeira seção é a própria cor do módulo"
    assert len(set(tons)) == len(tons), "duas seções saíram com a mesma cor"
    # e ela clareia sempre, nunca escurece
    lums = [M.luminancia(t) for t in tons]
    assert lums == sorted(lums), "a derivação não anda numa direção só"


def test_a_derivacao_nao_foge_do_modulo():
    """**A seção é DO módulo.** Uma derivação muito distante faria parecer
    outro."""
    cor = "#15803d"
    assert M.contraste(cor, M.cor_da_secao(cor, 9)) < 4.5, \
        "a seção ficou tão clara que já não se lê como o mesmo módulo"


# ------------------------------------------------- a folha de estilo


def test_a_folha_traz_todos_os_modulos():
    """**Gerada, e não escrita no CSS.** Módulo novo entraria no menu e ficaria
    sem cor — ou com a de outro, porque alguém copiaria a linha vizinha."""
    css = M.folha_de_estilo()
    for m in M.MODULOS:
        chave = m["chave"].lower().replace("_", "-")
        assert f"--mod-{chave}:{m['cor']}" in css
        assert f"--mod-{chave}-clara:" in css
        assert f"--mod-{chave}-escura:" in css


def test_a_folha_nao_tem_cor_escrita_a_mao_no_css():
    """Se alguém escrever `--mod-` no arquivo CSS, passam a existir duas
    fontes — e elas divergem no primeiro conserto."""
    css = (RAIZ / "static" / "app.css").read_text(encoding="utf-8")
    escritas = re.findall(r"--mod-[a-z-]+\s*:\s*#", css)
    assert not escritas, (
        "há cor de módulo escrita à mão no app.css: " + ", ".join(escritas)
        + " — ela sai de `modulos.folha_de_estilo()`")


def test_nenhuma_secao_repete_no_maior_grupo_do_menu():
    """**O oficial pediu derivação DIFERENTE, e a primeira versão repetia.**

    Com passo 0,12 e teto 0,45, a quinta seção em diante saía igual — e o maior
    grupo do menu tem sete. O Registro Civil mostrava «Assento já lavrado» e
    «Comunicações e remessas» com o mesmo tom.

    Este teste mede **quantas seções o menu de verdade tem** e exige que todas
    saiam distintas: se alguém acrescentar a oitava, ele avisa antes de ela
    nascer igual à sétima.
    """
    import re

    html = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
    nav = html[html.find("<nav>"):html.find("</nav>")]
    maior = max(pedaco.count("nav-secao")
                for pedaco in nav.split('<details class="nav-modulo"')[1:])
    assert maior >= 5, "o varredor deixou de achar as seções do menu"

    for m in M.MODULOS:
        tons = [M.cor_da_secao(m["cor"], i) for i in range(maior)]
        assert len(set(tons)) == maior, (
            f"em {m['nome']}, {maior - len(set(tons))} das {maior} seções "
            f"sairiam com o mesmo tom")


def test_a_secao_mais_clara_ainda_pertence_ao_modulo():
    """A outra metade da regra: **derivação muito distante faria parecer outro
    módulo**."""
    import re

    html = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
    nav = html[html.find("<nav>"):html.find("</nav>")]
    maior = max(pedaco.count("nav-secao")
                for pedaco in nav.split('<details class="nav-modulo"')[1:])
    for m in M.MODULOS:
        ultima = M.cor_da_secao(m["cor"], maior - 1)
        assert M.contraste(m["cor"], ultima) < 4.5, (
            f"a última seção de {m['nome']} ficou tão clara que já não se lê "
            f"como o mesmo módulo")
