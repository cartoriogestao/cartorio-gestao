"""
Testes do menu por módulo.

O QUE ELES DEFENDEM
    Que nenhuma tela fique órfã — que o menu abra o módulo da página aberta,
    qualquer que seja a página.

    A primeira versão do menu listava as rotas de cada módulo à mão, e estes
    testes pegaram a lista errada no mesmo dia: nove nomes supostos que não
    existiam e vinte e três rotas reais de fora. Agora o módulo sai do PREFIXO
    da rota, e o teste percorre TODAS as rotas do sistema para garantir que
    cada uma cai em exatamente um módulo.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.lento  # abre todas as rotas; fica na suite completa

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

BASE_HTML = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")

# Rotas que não são tela de menu: download, POST de formulário, arquivo. Não
# precisam abrir módulo nenhum, e várias nem respondem a GET.
NAO_SAO_TELA = ("static", "login", "logout", "saude", "health")


# O APP E O DO `conftest` (`cg_app`, um por modulo) — 26/10/2026. Este arquivo
# montava o proprio, numa pasta temporaria de nome fixo: com o banco de teste no
# PostgreSQL esse banco nao passava pelo registro da ponte, a tela de login nao
# vinha com o `csrf_token`, e os 28 testes estouravam no setup.
@pytest.fixture(scope="module")
def app(cg_app):
    return cg_app


@pytest.fixture(scope="module")
def cliente(app):
    d = app.extensions["db"]
    try:
        # NOME DE GENTE (27/10/2026): «Operador» sozinho é rótulo de máquina
        # (`nome_humano.eh_rotulo_de_maquina`), e conta de robô não pode ser
        # ADMIN — o `create_user` recusava, o `except` engolia, ninguém logava
        # e a tela de login virava /setup, sem `csrf_token`. Era essa a causa
        # dos 28 testes estourando no setup.
        d.create_user("menu", "Operador Exemplo", "Senha#12345", "ADMIN")
    except Exception:                                          # noqa: BLE001
        pass
    c = app.test_client()
    pega = lambda h: re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h).group(1)
    c.post("/login", data={"username": "menu", "password": "Senha#12345",
                           "csrf_token": pega(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def modulos_abertos(html: str) -> list[str]:
    """Os grupos do menu que vieram abertos.

    **O PADRAO E TOLERANTE A ATRIBUTOS, e isso foi correcao de 30/08/2026.** A
    primeira versao exigia `<details class="nav-modulo" open>` — com o `>`
    colado no `open` —, e quebrou no dia em que cada grupo ganhou a cor do
    modulo (`style="--cor-do-grupo:..."`, relato #32): **os 23 casos ficaram
    vermelhos com o menu funcionando igual**.

    O que este teste quer saber e se o grupo ABRE, e nao em que ordem os
    atributos foram escritos. Regex que fixa a ordem dos atributos reprova
    acrescimo legitimo — e faz perder tempo procurando um defeito que nao
    existe.
    """
    nav = html[html.find("<nav>"):html.find("</nav>")]
    return [a.strip() for a in re.findall(
        r'<details[^>]*class="nav-modulo"[^>]*\sopen[^>]*>\s*<summary>([^<\n]*)',
        nav)]


# ------------------------------------------------------------ os módulos

def test_cada_atribuicao_tem_o_seu_proprio_lugar():
    """Pedido do oficial em 27/08/2026.

    Ate aqui, quatro atribuicoes moravam dentro de um item chamado «Demais
    atribuicoes» — o Registro Civil desta casa aparecia como «demais». O
    balcao do civil abria um menu que nao tinha o nome do que ele faz.
    """
    for nome in ("Tabelionato de Notas", "Registro de Imóveis", "Protesto",
                 # OS NOMES SÃO OS DAS ATRIBUIÇÕES, e não apelidos — pedido do
                 # oficial em 28/08/2026: «módulo de registro civil deveria se
                 # chamar Registro Civil das Pessoas Naturais; temos outra
                 # competência de registro civil, que é o RCPJ, e pode
                 # confundir». As duas vivem lado a lado neste menu, e
                 # «Registro Civil» sozinho não diz qual das duas é.
                 # 13/10/2026: o RCPJ/RTD passou ao nome legal (3.6.286 o deixara pela metade).
                 "Registro Civil das Pessoas Naturais", "RCPJ e RTD — Pessoas Jurídicas, Títulos e Documentos", "Livros e acervo",
                 # «Malote» virou «Processos e malote» em 12/10/2026: o oficial
                 # mandou unir tarefas e expedientes num módulo de Processos.
                 "Processos e malote",
                 "Administrativo"):
        assert re.search(r"<summary>\s*" + re.escape(nome), BASE_HTML), nome
    # E o nome antigo nao volta pela porta dos fundos.
    assert "Demais atribuições" not in BASE_HTML


def test_o_livro_3_mora_no_registro_de_imoveis():
    """Ele e o Registro Auxiliar DO RI, e o numero dele ja vinha de
    `ri_numeracao`. Estava fora do modulo de que faz parte."""
    ri = BASE_HTML.split("<summary>Registro de Imóveis</summary>", 1)[1]
    ri = ri.split("</details>", 1)[0]
    assert "livro3_registros" in ri


def test_o_modulo_vem_do_prefixo_e_nao_de_lista():
    # É o que impede a lista de envelhecer. Se alguém voltar a listar rota por
    # rota, este teste cai e a conversa recomeça.
    assert "aqui.startswith('ri_')" in BASE_HTML
    assert "aqui.startswith('notas_')" in BASE_HTML
    assert "aqui.startswith('protesto')" in BASE_HTML
    assert "aqui.startswith('rcpn')" in BASE_HTML


def test_toda_rota_cai_em_exatamente_um_modulo(app):
    # Percorre TODAS as rotas do sistema, e não uma lista escrita à mão.
    def classifica(e: str) -> list[str]:
        m = []
        if e.startswith("ri_") or e.startswith("usucapiao") or e.startswith("livro3"):
            m.append("ri")
        if e.startswith("notas_"):
            m.append("notas")
        if e.startswith("protesto"):
            m.append("protesto")
        if e.startswith("rcpn"):
            m.append("rcpn")
        if e.startswith("rcpj_rtd") or e.startswith("atribuicoes_certid"):
            m.append("rcpj_rtd")
        if e.startswith("nucleo_") or e.startswith("implantacao")                 or e == "atribuicoes_importar":
            m.append("livros")
        if e.split("_")[0] in ("expediente", "expedientes", "task", "tasks",
                               "inspection", "inspections"):
            m.append("malote")
        if not m and e != "dashboard":
            m.append("adm")
        return m

    for regra in app.url_map.iter_rules():
        e = regra.endpoint
        if e in NAO_SAO_TELA or e == "dashboard":
            continue
        assert len(classifica(e)) == 1, f"{e} caiu em {classifica(e)}"


# ------------------------------------------- abre o módulo da página atual

@pytest.mark.parametrize("url,modulo", [
    ("/notas", "Tabelionato de Notas"),
    ("/notas/remessas", "Tabelionato de Notas"),
    ("/notas/escrituras/pendentes", "Tabelionato de Notas"),
    ("/notas/cartoes", "Tabelionato de Notas"),
    ("/registro-imoveis", "Registro de Imóveis"),
    ("/registro-imoveis/doi", "Registro de Imóveis"),
    ("/registro-imoveis/ctp", "Registro de Imóveis"),
    ("/registro-imoveis/imagens/resolver", "Registro de Imóveis"),
    ("/registro-imoveis/certidoes", "Registro de Imóveis"),
    # O PROTESTO SAIU DESTA LISTA EM 01/09/2026 — ordem do oficial:
    # «desabilitar o modulo de protesto para os usuarios, protesto vai ficar
    # para um futuro». Desligado, o grupo nao esta no menu e a rota nem abre,
    # de modo que nao ha «modulo aberto» a conferir aqui.
    #
    # Quem guarda o Protesto agora e `test_modulo_alcance.py`, e ele guarda
    # os DOIS lados: desligado nao abre, e RELIGADO volta ao menu com o grupo
    # aberto — que e este mesmo teste, aplicado quando ele voltar.
    ("/rcpn", "Registro Civil das Pessoas Naturais"),
    ("/rcpn/certidoes", "Registro Civil das Pessoas Naturais"),
    ("/rcpj-rtd", "RCPJ e RTD — Pessoas Jurídicas, Títulos e Documentos"),
    ("/livro3", "Registro de Imóveis"),
    ("/nucleo/livros", "Livros e acervo"),
    ("/implantacao", "Livros e acervo"),
    ("/expedientes", "Processos e malote"),
    ("/tarefas", "Processos e malote"),
    ("/inspecoes", "Processos e malote"),
    ("/processos", "Processos e malote"),
    ("/caixa", "Administrativo"),
    ("/configuracoes", "Administrativo"),
    ("/relatorios", "Administrativo"),
])
def test_o_modulo_da_pagina_vem_aberto(cliente, url, modulo):
    r = cliente.get(url)
    if r.status_code == 404:
        pytest.skip(f"{url} não existe nesta instalação")
    assert r.status_code == 200, f"{url} respondeu {r.status_code}"
    abertos = modulos_abertos(r.get_data(as_text=True))
    assert abertos == [modulo], f"{url} abriu {abertos}, esperava [{modulo}]"


def test_o_painel_nao_abre_modulo_nenhum(cliente):
    assert modulos_abertos(cliente.get("/").get_data(as_text=True)) == []


def test_nenhuma_tela_abre_dois_modulos(cliente, app):
    # Dois módulos abertos ao mesmo tempo é o menu deixando de dizer onde a
    # pessoa está.
    vistas = 0
    for regra in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
        if regra.endpoint in NAO_SAO_TELA or "<" in str(regra) \
                or "GET" not in (regra.methods or set()):
            continue
        r = cliente.get(str(regra))
        # Rota que devolve arquivo — PNG da ficha, ODT do traslado, zip do
        # backup — não é tela e nem sequer decodifica como texto.
        if r.status_code != 200 or not r.mimetype.startswith("text/html"):
            continue
        html = r.get_data(as_text=True)
        if "<nav>" not in html:
            continue
        abertos = modulos_abertos(html)
        assert len(abertos) <= 1, f"{regra} abriu {abertos}"
        vistas += 1
    assert vistas > 15, f"conferi só {vistas} telas — o teste não está vendo o sistema"


# ----------------------------------------------------------------- o resto

def test_o_menu_nao_depende_de_javascript():
    # <details> é do próprio HTML. O sistema roda em rede local, às vezes sem
    # internet, e menu que precisa de script é menu que some.
    nav = BASE_HTML[BASE_HTML.find("<nav>"):BASE_HTML.find("</nav>")]
    assert "<script" not in nav and "onclick" not in nav


def test_o_estilo_do_modulo_existe():
    css = (RAIZ / "static" / "app.css").read_text(encoding="utf-8")
    assert ".nav-modulo" in css
    assert ".nav-modulo>summary" in css.replace(" ", "")


def test_todo_link_do_menu_aponta_para_rota_existente(app):
    reais = {r.endpoint for r in app.url_map.iter_rules()}
    nav = BASE_HTML[BASE_HTML.find("<nav>"):BASE_HTML.find("</nav>")]
    for e in set(re.findall(r"url_for\('([a-z_]+)'\)", nav)):
        assert e in reais, f"o menu aponta para {e}, que não existe"


# ---------------------------------------------------------------------------
# AS SECOES DENTRO DE UM MODULO
#
# «Preciso que deixe em ordem os itens dentro dos modulos, nao tem uma logica
# para encontrar» — o oficial, em 27/08/2026. Os itens estavam na ordem em que
# as telas foram escritas, e o Administrativo tinha vinte e sete deles.
#
# A regra: modulo com mais de seis itens ganha secoes; abaixo disso, secao e
# ruido. E a ordem de dentro e a do dia — o que o balcao faz o dia inteiro
# primeiro, consulta e acervo depois, e por ultimo o que so o oficial mexe.

# **A REGRA É «MAIS DE SEIS ITENS GANHA SEÇÃO»**, e por isso ela se MEDE, e não
# se escreve. A lista à mão que estava aqui — Notas, RI, Protesto,
# Administrativo — envelheceu do mesmo jeito que o menu envelhecia: em 30/08/2026
# o Registro Civil chegou a **dezesseis itens em coluna única** e este teste não
# acusou, porque o nome dele não estava na lista.
#
# **É a lição do menu, um nível acima**: lista escrita à mão noutro arquivo
# envelhece na tarde em que se escreve — e aqui o arquivo era o do teste que
# deveria guardar a regra.
# **E A RÉGUA TEM UMA FAIXA EM QUE ELA NÃO DECIDE, e isso se declara.**
# Acima de seis itens a seção é necessária; até quatro ela é ruído — separa um
# item do outro sem nada a separar. **Entre cinco e seis quem decide é quem monta
# o menu**, porque o que importa ali não é a conta: é se os grupos existem de
# verdade. O Protesto tem exatamente seis itens e duas seções — «O balcão» e «O
# dia da CRA» —, e elas separam coisas que são mesmo diferentes.
#
# Fingir que a conta decide essa faixa produziria uma das duas coisas ruins:
# tirar seção que ajuda, ou pôr seção que atrapalha.
EXIGE_SECAO_ACIMA_DE = 6
SECAO_E_RUIDO_ATE = 4


def _quantos_itens(corpo: str) -> int:
    return len(re.findall(r"<a ", corpo))


def _modulos_grandes(html: str) -> list[str]:
    """Os módulos que passaram de seis itens. **Medidos, e não escritos.**"""
    return [nome for nome, corpo in _grupos(html).items()
            if _quantos_itens(corpo) > EXIGE_SECAO_ACIMA_DE]


def _grupos(html: str) -> dict[str, str]:
    """Cada `<details>` do menu, do `<summary>` ao `</details>`."""
    nav = html[html.find("<nav>"):html.find("</nav>")]
    return {m.group(1).strip(): m.group(2) for m in
            re.finditer(r"<summary>([^<]*)</summary>(.*?)</details>", nav,
                        re.S)}


def _secoes_do_grupo(corpo: str) -> list[tuple[str, str]]:
    """Cada título de seção com o que vem até o próximo (ou o fim do grupo)."""
    marcas = list(re.finditer(r'<div class="nav-secao"[^>]*>([^<]*)</div>', corpo))
    saida = []
    for k, m in enumerate(marcas):
        fim = marcas[k + 1].start() if k + 1 < len(marcas) else len(corpo)
        saida.append((m.group(1).strip(), corpo[m.end():fim]))
    return saida


def test_nenhuma_secao_fica_vazia(cliente):
    """Título com nada embaixo faz a pessoa procurar o que não está ali.

    O caso vivo é a **Ajuda**: ela depende de `ajuda_liberada`, que mora no
    banco. Para quem não a tem liberada e não é gerente, o título ficaria
    sozinho. Por isso ele carrega a mesma condição dos links.
    """
    html = cliente.get("/").get_data(as_text=True)
    vazias = [f"{grupo} → {titulo}"
              for grupo, corpo in _grupos(html).items()
              for titulo, dentro in _secoes_do_grupo(corpo)
              if "<a " not in dentro]
    assert not vazias, ("Estas seções do menu não têm link nenhum embaixo: "
                        + ", ".join(vazias))


def test_os_modulos_grandes_tem_secao(cliente):
    """Módulo grande sem seção volta a ser a lista que não se procura.

    **QUEM ENTRA NESTA CONTA É MEDIDO**: todo módulo com mais de seis itens, e
    não uma lista de nomes. Um módulo que cresça amanhã fica vermelho aqui no
    mesmo dia — que é o que não aconteceu com o Registro Civil, e ele chegou a
    dezesseis.
    """
    html = cliente.get("/").get_data(as_text=True)
    grupos = _grupos(html)
    sem_secao = [f"{nome} ({_quantos_itens(grupos[nome])} itens)"
                 for nome in _modulos_grandes(html)
                 if not _secoes_do_grupo(grupos[nome])]
    assert not sem_secao, (
        "Estes módulos passaram de seis itens e não têm seção nenhuma: "
        + ", ".join(sem_secao)
        + ". Foi assim que o Administrativo chegou a vinte e sete links em "
          "coluna única, e o Registro Civil a dezesseis.")


def test_modulo_pequeno_nao_ganha_secao(cliente):
    """Seção num módulo de três itens é enfeite, e enfeite atrapalha.

    **SÓ ACUSA ATÉ QUATRO ITENS.** Entre cinco e seis a conta não decide — ver o
    comentário de `SECAO_E_RUIDO_ATE`: ali o que importa é se os grupos existem
    de verdade, e quem sabe isso é quem monta o menu.
    """
    grupos = _grupos(cliente.get("/").get_data(as_text=True))
    for nome, corpo in grupos.items():
        if _quantos_itens(corpo) > SECAO_E_RUIDO_ATE:
            continue
        assert not _secoes_do_grupo(corpo), (
            f"O módulo «{nome}» tem {_quantos_itens(corpo)} itens e ganhou "
            f"seção. Até {SECAO_E_RUIDO_ATE} itens a seção não ajuda a achar: "
            f"só afasta um item do outro.")


def test_a_secao_nao_e_link(cliente):
    """Quem clica num título de seção não deve esperar que algo aconteça."""
    html = cliente.get("/").get_data(as_text=True)
    nav = html[html.find("<nav>"):html.find("</nav>")]
    assert '<a class="nav-secao"' not in nav
    assert "nav-secao" in nav


# ------------------------------------- os filtros que o menu leva na URL
#
# ACRESCENTADO EM 30/08/2026, com o menu reorganizado por ato. As tres etapas
# do casamento sao tres links para a MESMA lista, filtrada por situacao. Se a
# chave da situacao tiver um erro de digitacao, a lista volta **vazia** — e
# lista vazia le-se como «nada a fazer nesta fase», que e a mentira mais cara
# que uma tela de prazo pode contar.


def test_as_situacoes_que_o_menu_filtra_existem_de_verdade():
    """Cada `situacao=` no menu tem de estar em `hc_schema.SITUACOES`."""
    import re
    import hc_schema as HC
    pedidas = set(re.findall(r"situacao='([A-Z_]+)'", BASE_HTML))
    assert pedidas, "o menu deixou de filtrar por situacao — o teste envelheceu"
    desconhecidas = pedidas - set(HC.SITUACOES)
    assert not desconhecidas, (
        f"o menu filtra por situacoes que nao existem: {sorted(desconhecidas)}. "
        f"As que existem: {sorted(HC.SITUACOES)}. Link assim devolve lista "
        f"vazia, e lista vazia le-se como «nada a fazer».")


def test_as_tres_etapas_do_casamento_estao_no_menu_e_numeradas():
    """A ordem e a que a lei impoe (arts. 67 a 69 da Lei 6.015/1973), e um
    casamento registrado sem o edital ter corrido e nulo de origem. Os numeros
    no rotulo sao o que faz a ordem aparecer sem ninguem explicar."""
    for n in ("1 ·", "2 ·", "3 ·"):
        assert n in BASE_HTML, f"faltou a etapa «{n}» do casamento no menu"


def test_o_menu_do_rcpn_tem_secao_por_ato():
    """**REORGANIZADO POR ORDEM DO OFICIAL EM 30/08/2026**, depois dos prints
    do E-Oficio: la o menu e por ATO, e o nosso era por fase do trabalho."""
    i = BASE_HTML.find("Registro Civil das Pessoas Naturais")
    j = BASE_HTML.find("RCPJ e RTD", i)
    bloco = BASE_HTML[i:j]
    for secao in ("Nascimento", "Casamento", "Óbito"):
        # O PADRAO ACEITA ATRIBUTOS — 30/08/2026. Cada secao ganhou a sua
        # cor derivada (`style="--cor-da-secao:..."`, relato #32), e o padrao
        # que exigia o `>` colado no `nav-secao"` passou a nao achar nada.
        assert re.search(rf'nav-secao"[^>]*>{re.escape(secao)}<', bloco), (
            f"o RCPN perdeu a secao «{secao}» — o menu voltou a ser por fase")
