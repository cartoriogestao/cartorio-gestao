"""Duas portas para a mesma sala — relato #32, e a licao do #12.

    «precisa reorganizar, unir o que e semelhante e colocar tudo em ordem»
                                                              — relato #32

    «reconhecimento e reconhecer firma estao injustificadamente separados»
                                                              — relato #12

O QUE ESTE VARREDOR GUARDA
    **Que nao ha dois itens de menu levando ao MESMO endereco.** O oficial ja
    relatou esse defeito uma vez, com outras palavras: duas entradas com nomes
    quase iguais, e ele escolhendo no escuro.

    Medido em 30/08/2026: **112 links, 111 destinos** — havia **um** par
    repetido, `/modelos`, que aparecia como «Modelos de documento» no Registro
    de Imoveis e «Modelos dos documentos» no Administrativo.

    **O conserto nao foi apagar um.** Quem esta no RI e quer o modelo da
    certidao do RI nao deve ter de sair do modulo; o catalogo ja sabia de qual
    atribuicao e cada modelo, e nenhuma tela usava esse campo. Agora o link do
    RI vai filtrado.

    **E que rotulo repetido, quando for de proposito, esteja DECLARADO com o
    motivo** — 15/09/2026. Antes o caso legitimo passava por um `continue`
    calado, e a mesma fresta aprovava o ilegitimo: foi assim que dois «Selos
    emitidos» conviveram no menu. A lista e `ROTULOS_DECLARADOS`, na forma de
    `FORA_DA_VARREDURA` — e o segundo teste confere que ela nao envelheceu.

POR QUE O ENDERECO, E NAO A ROTA
    Tres itens do Registro Civil levam a `rcpn_formulario` e tres a
    `rcpn_habilitacoes` — e **estao certos**: cada um leva a um filtro diferente
    da mesma tela, e sao passos distintos do mesmo trabalho. Comparar pela ROTA
    acusaria os seis; comparar pelo ENDERECO acusa so quem leva ao mesmo lugar.
"""
from __future__ import annotations

import glob
import re
import sys
from collections import defaultdict
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"

# O QUE FOI MEDIDO EM 30/08/2026, para o varredor nao deixar de achar em
# silencio: **varredor que encolhe passa calado**.
LINKS_NO_MENU_ENTAO = 112


# OS RÓTULOS QUE SE REPETEM DE PROPÓSITO, E O MOTIVO DE CADA UM.
#
# **Esta lista não existia, e é a correção de 15/09/2026.** O teste fazia
# `continue` em rótulo repetido com endereço diferente — o caso legítimo —, e
# com isso **aprovava também o ilegítimo**: foi por essa fresta que dois «Selos
# emitidos» conviveram no menu, apontando para telas que discordavam em 7.762
# selos sobre o que é «não usado», e nenhum teste disse uma palavra. O defeito
# do relato #12, dentro do arquivo que existe para guardá-lo.
#
# Medido em 15/09/2026: **152 links, 3 rótulos repetidos** — e são os três
# abaixo. Nenhum deles leva ao MESMO endereço; esse caso continua sendo recusado
# sem declaração, porque duas portas para a mesma sala continuam sendo duas
# portas.
ROTULOS_DECLARADOS: dict[str, str] = {
    "certidões":
        "Uma por atribuição — a certidão do RI não é a do Protesto, e não é a "
        "do Registro Civil: o que se certifica e em que livro muda por "
        "completo. O grupo do menu já diz de qual atribuição é cada uma, e "
        "cada uma abre a lista daquela atribuição.",
    "matrículas":
        "**A mesma palavra querendo dizer duas coisas.** No Registro de "
        "Imóveis é a ficha do imóvel (/registro-imoveis); no Registro Civil é "
        "a matrícula de 32 dígitos do assento (/rcpn/matriculas). Endereços "
        "diferentes, módulos diferentes, e nada em comum além do nome — "
        "unificar seria o erro que o projeto já pagou caro: a mesma palavra em "
        "dois lugares não quer dizer a mesma coisa.",
    "modelos dos documentos":
        "**Um armazém, seis portas** — e as seis são de propósito, por decisão "
        "do oficial em 07/09/2026. O catálogo geral (Administrativo) responde "
        "«onde eu mudo isto?» quando não se sabe de qual atribuição é o papel; "
        "o submódulo de cada atribuição responde a mesma pergunta quando se "
        "sabe, e é ali que se ajusta o que vale «em toda a atribuição». Os "
        "seis GRAVAM NO MESMO LUGAR — são duas vistas de um armazém, e não "
        "duas fontes. Se algum dia dois deles apontarem para o mesmo "
        "endereço, aí é o defeito de 30/08 outra vez.",
}


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return achado.group(1) if achado else ""


@pytest.fixture(scope="module")
def menu(tmp_path_factory) -> list[tuple[str, str]]:
    from app import create_app
    from database import Database

    dados = tmp_path_factory.mktemp("dados")
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA,
                                "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    html = c.get("/").get_data(as_text=True)
    nav = html[html.find("<nav>"):html.find("</nav>")]
    return [(href, re.sub(r"\s+", " ", rotulo).strip())
            for href, rotulo in
            re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', nav)]


def test_nenhum_endereco_aparece_duas_vezes_no_menu(menu):
    """**Duas portas para a mesma sala fazem o operador escolher no escuro.**"""
    por_destino: dict[str, list[str]] = defaultdict(list)
    for href, rotulo in menu:
        por_destino[href].append(rotulo)
    repetidos = {h: r for h, r in por_destino.items() if len(r) > 1}
    assert not repetidos, "estes endereços têm mais de um item de menu:\n" + \
        "\n".join(f"  {h}: " + " | ".join(r) for h, r in repetidos.items())


def test_o_varredor_continua_alcancando_o_menu_inteiro(menu):
    """**Varredor que deixa de achar passa calado.**

    Se o menu encolher de repente, é mais provável que o padrão tenha parado de
    casar do que a casa ter perdido metade das telas.
    """
    assert len(menu) >= LINKS_NO_MENU_ENTAO - 5, (
        f"o varredor achou {len(menu)} links e eram {LINKS_NO_MENU_ENTAO} em "
        f"30/08/2026 — confira se o padrão ainda casa com o menu")


def test_nenhum_item_de_menu_tem_rotulo_repetido(menu):
    """Dois nomes iguais em lugares diferentes são o mesmo escuro, por outro
    caminho — foi assim que «Reconhecimentos» e «Reconhecer firma» conviveram.

    Rótulos iguais **em módulos diferentes** são legítimos: «Certidões» no
    Protesto e «Certidões» no RI são coisas diferentes, e o grupo já diz qual é.
    Este teste olha o rótulo junto do endereço.

    **E ELE NÃO DESISTE MAIS CALADO — 15/09/2026.** Até aqui, rótulo repetido
    com endereço diferente caía num `continue`, e passava sem que ninguém
    soubesse que era repetido. Foi por essa fresta que **dois «Selos emitidos»**
    conviveram no menu, com réguas diferentes para a mesma palavra, e nenhum
    teste reclamou — o defeito do relato #12, de novo, no mesmo arquivo que
    existe para guardá-lo.

    O caso legítimo continua passando, e passa **DECLARADO**: a lista abaixo
    diz qual é e **por quê**. Declaração sem motivo seria a mesma desistência
    com outro nome.
    """
    mesmo_endereco, em_enderecos_diferentes = _rotulos_repetidos(menu)
    sem_declaracao = {r: hs for r, hs in em_enderecos_diferentes.items()
                      if r not in ROTULOS_DECLARADOS}
    assert not sem_declaracao, (
        "estes rótulos se repetem no menu e não estão declarados:\n"
        + "\n".join(f"  {r}: " + " | ".join(hs) for r, hs in sem_declaracao.items())
        + "\n\nSe for de propósito, acrescente em ROTULOS_DECLARADOS com o "
          "motivo. Se não for, é o operador escolhendo no escuro — relato #12.")
    assert not mesmo_endereco, "itens repetidos: " + ", ".join(mesmo_endereco)


def _rotulos_repetidos(menu):
    """Os rótulos repetidos, separados em duas espécies.

    Devolve `(repetidos_no_mesmo_endereco, repetidos_em_enderecos_diferentes)`.
    A primeira espécie não tem declaração que sirva — duas portas para a mesma
    sala continuam sendo duas portas, e quem a acusa é o teste de endereço. A
    segunda é a que pode ser de propósito, e é a que exige motivo escrito.
    """
    por_rotulo: dict[str, list[str]] = defaultdict(list)
    for href, rotulo in menu:
        por_rotulo[rotulo.lower()].append(href)

    mesmo_endereco: list[str] = []
    em_enderecos_diferentes: dict[str, list[str]] = {}
    for chave, hrefs in por_rotulo.items():
        if len(hrefs) < 2:
            continue
        if len(set(hrefs)) < len(hrefs):
            mesmo_endereco.append(f"{chave} ({hrefs[0]})")
        if len(set(hrefs)) > 1:
            em_enderecos_diferentes[chave] = sorted(set(hrefs))
    return mesmo_endereco, em_enderecos_diferentes


def test_a_lista_de_rotulos_declarados_nao_envelhece(menu):
    """**Declaração que ninguém revisa vira licença permanente.**

    Se o rótulo deixou de se repetir, a linha tem de sair: ela foi escrita para
    dispensar um motivo, e manter o motivo de um caso que não existe mais é o
    «teto que mente» na forma de exceção concedida.

    E o motivo tem de estar escrito: `"ok"` libera qualquer repetição futura
    daquele nome, que é exatamente o que esta lista existe para impedir.
    """
    _, em_enderecos_diferentes = _rotulos_repetidos(menu)
    sobrando = [r for r in ROTULOS_DECLARADOS if r not in em_enderecos_diferentes]
    assert not sobrando, (
        "estes rótulos estão declarados e NÃO se repetem mais — a declaração "
        "saiu de validade:\n" + "\n".join(f"  {r}" for r in sobrando))

    curtos = [r for r, motivo in ROTULOS_DECLARADOS.items() if len(motivo) < 40]
    assert not curtos, (
        "estes rótulos estão declarados sem o motivo escrito — declaração sem "
        "motivo é a desistência calada de antes, com outro nome:\n"
        + "\n".join(f"  {r}" for r in curtos))

    # Piso medido: 3 rótulos repetidos em 15/09/2026. Varredor que encolhe
    # passa calado, e aqui ele encolheria junto com o menu.
    assert len(ROTULOS_DECLARADOS) >= 3, (
        f"a lista tem {len(ROTULOS_DECLARADOS)} declarações e eram 3 em "
        f"15/09/2026 — confira se o menu ainda é lido inteiro")


def test_os_modelos_do_RI_levam_ao_filtro_do_RI(menu):
    """O conserto de 30/08: o link do RI deixou de ser `/modelos` puro."""
    do_ri = [h for h, r in menu if "Modelos de documento" in r]
    assert do_ri, "o link dos modelos sumiu do Registro de Imóveis"
    assert "atribuicao=" in do_ri[0], (
        "o link do RI voltou a ser o `/modelos` geral — e volta a ser a segunda "
        "porta para a mesma sala")
