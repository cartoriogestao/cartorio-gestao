"""O rascunho em todas as telas de lavrar — relato #36 do oficial.

    «em todos os atos do cartório, durante o preenchimento, é preciso ter um
     campo para salvar o progresso e continuar depois»    — 30/08/2026

O QUE ESTAVA FEITO, E O QUE NÃO
    O mecanismo existia inteiro — `rascunho_de_tela.py`, a rota
    `/rascunhos/salvar`, a tela de rascunhos e a macro `_rascunho.html` —, e
    **estava ligado em UMA tela**: o assento novo do Registro Civil. Medido em
    07/09/2026: **1 de 11**.

    É o defeito de costume deste projeto pelo outro lado — não «função pronta
    que nenhuma tela chama», mas **função pronta que uma tela chama e dez
    não**.

A MACRO, E NÃO DEZ CÓPIAS
    Escrever o bloco em cada tela daria dez versões divergindo no primeiro
    conserto. É a lição de `_cobrar.html` e de `_fraude.html`: o que não pode
    divergir é o pedaço que guarda o trabalho de quem está preenchendo.

E AS VOLTAS SÃO MEDIDAS NO `url_map`
    As funções internas destas telas chamam-se todas `tela`, e adivinhar o
    endpoint pelo nome do arquivo daria `url_for` que estoura. **Quatro das dez
    não casavam pelo nome** — `atrib_livro3_novo.html` é desenhado por
    `livro3_registro_novo`, e `ri_nova.html` por `ri_nova_matricula`.

    **E a décima tem TRÊS rotas**: averbar, anotar e retificar desenham a mesma
    tela do Registro Civil. Uma volta fixa levaria o oficial a abrir uma
    averbação quando ele estava anotando.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"

# As telas em que se LAVRA — cada uma tem de guardar o preenchimento.
#
# **A LISTA É ESCRITA À MÃO, E ISSO SE DECLARA.** «Qual tela é de lavrar ato»
# não se mede: não há coluna nem decorador que o diga, e um varredor que
# chutasse por nome («*_novo») pegaria telas de cadastro que não lavram nada.
# O que a impede de envelhecer é o piso abaixo e o teste que exige a macro.
TELAS_DE_LAVRAR = {
    "livro3_registro_novo": "Livro 3",
    "protesto_titulo_novo": "Protesto",
    "rcpj_rtd_registro_novo": "RCPJ/RTD — registro",
    "rcpj_rtd_titulo_novo": "RCPJ/RTD — título",
    "notas_ato_novo": "Notas",
    "rcpn_assento_novo": "Registro Civil — assento",
    "rcpn_habilitacao_nova": "Registro Civil — habilitação",
    "rcpn_retificacao_nova": "Registro Civil — retificação",
    "rcpn_averbar": "Registro Civil — averbação",
    "rcpn_anotar": "Registro Civil — anotação",
    "rcpn_retificar": "Registro Civil — retificação do assento",
    "ri_nova_matricula": "Registro de Imóveis — matrícula",
    "ri_retificacao_nova": "Registro de Imóveis — retificação",
}
PISO = 13


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    c = cg_casa["c"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, "ADMIN")
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get("/login").get_data(as_text=True)).group(1)
    c.post("/login", data={"username": "tabeliao", "password": SENHA,
                           "csrf_token": token}, follow_redirects=True)
    return cg_casa

def _assento(casa) -> int:
    """Um assento ativo — as três telas de lançamento do civil precisam de um."""
    con = sqlite3.connect(casa["banco"])
    cols = {r[1] for r in con.execute("PRAGMA table_info(rc_assentos)")}
    obrig = [r[1] for r in con.execute("PRAGMA table_info(rc_assentos)")
             if r[3] and r[4] is None and not r[5]]
    dados = {"especie": "NASCIMENTO", "nome": "FULANO DE TAL",
             "situacao": "ATIVO", "criado_em": "2026-09-07",
             "serie": "RC_A", "numero": "1", "data_ato": "2026-09-07"}
    usar = {k: v for k, v in dados.items() if k in cols}
    for nome in obrig:
        usar.setdefault(nome, "1")
    con.execute(f"INSERT INTO rc_assentos ({','.join(usar)}) "
                f"VALUES ({','.join('?' * len(usar))})", list(usar.values()))
    con.commit()
    aid = int(con.execute("SELECT id FROM rc_assentos").fetchone()[0])
    con.close()
    return aid


# O que cada parâmetro de rota precisa valer para a tela ABRIR o formulário.
# Medido, e não adivinhado: `RCPN_SLUG_DA_ESPECIE` diz que a de nascimento é
# «nascimento», e sem espécie a rota abre o SELETOR, que não é o formulário.
VALOR_DO_PARAMETRO = {"especie_url": "nascimento"}


def _url(casa, endpoint: str, assento_id: int) -> str | None:
    """O endereço da tela, montado com EXATAMENTE os parâmetros da regra.

    **TRÊS CORREÇÕES MINHAS AQUI, e todas o mesmo engano: eu adivinhava o
    endereço em vez de perguntar.**

      1. trocava só `<int:assento_id>` no texto — e a tela do assento pede
         `especie_url`, então o marcador ia junto e dava 404;
      2. passei a trocar os dois, e `rcpn_assento_novo` tem DUAS regras: a sem
         parâmetro abre o seletor de espécie, e não o formulário;
      3. tentei `url_for` com parâmetros a mais — **e ele não recusa**: põe o
         que sobra na query, devolvendo `/rcpn/novo?assento_id=1`, que é o
         seletor outra vez.

    **Régua que erra o endereço acusa quem está certo**, e as três versões
    acusaram justamente a única tela que já tinha o rascunho. Agora a regra
    diz quais argumentos tem, e se preenche só esses — escolhendo, quando há
    mais de uma, a que pede mais.
    """
    from flask import url_for
    regras = [r for r in casa["app"].url_map.iter_rules()
              if r.endpoint == endpoint]
    if not regras:
        return None
    regra = max(regras, key=lambda r: len(r.arguments))
    valores = {}
    for arg in regra.arguments:
        valores[arg] = (assento_id if arg.endswith("_id")
                        else VALOR_DO_PARAMETRO.get(arg, "1"))
    with casa["app"].test_request_context():
        return url_for(endpoint, **valores)


def test_TODA_TELA_DE_LAVRAR_oferece_o_rascunho(casa):
    """**O relato inteiro, num teste.**

    Não basta a macro existir: a tela tem de desenhar o botão, o formulário do
    ato tem de ter o `id` que o script procura, e o script tem de ir junto —
    sem qualquer um dos três o botão não guarda nada, e o operador descobre
    isso depois de preencher a tela toda.
    """
    aid = _assento(casa)
    faltando = []
    for endpoint, rotulo in sorted(TELAS_DE_LAVRAR.items()):
        url = _url(casa, endpoint, aid)
        if url is None:
            faltando.append(f"{rotulo} ({endpoint}): a rota não existe")
            continue
        html = casa["c"].get(url).get_data(as_text=True)
        falta = [q for q, tem in (
            ("o botão", "Salvar rascunho e continuar depois" in html),
            ("o id do formulário", 'id="form-do-ato"' in html),
            ("o script", "rascunho.js" in html)) if not tem]
        if falta:
            faltando.append(f"{rotulo} ({endpoint}): falta {', '.join(falta)}")
    assert not faltando, "telas de lavrar sem rascunho:\n  " + "\n  ".join(faltando)


def test_a_lista_de_telas_nao_encolheu(casa):
    """**Lista escrita à mão envelhece**, e esta é escrita à mão de propósito:
    «qual tela é de lavrar» não se mede. O piso é o que a impede de sumir."""
    assert len(TELAS_DE_LAVRAR) >= PISO


def test_NENHUMA_TELA_ESCREVE_O_BLOCO_A_MAO(casa):
    """**A macro, e não dez cópias.** Uma tela que escrevesse o formulário do
    rascunho por conta própria divergiria no primeiro conserto — e o que ela
    guardasse deixaria de ser o que a tela de rascunhos lê."""
    escrevem = []
    for p in (RAIZ / "templates").glob("*.html"):
        if p.name == "_rascunho.html":
            continue
        h = p.read_text(encoding="utf-8", errors="replace")
        # O ATRIBUTO DA MACRO, E NAO O PEDACO DE TEXTO — 13/10/2026. O teste
        # procurava «data-rascunho» solto, e o HOTFIX-2026-10-13-01 pôs na ficha
        # do RI um `data-rascunho-chave` (guarda no navegador o que se digitou no
        # formulario de lavrar, para a recusa da revisao nao apagar) — outra
        # coisa, que nao e o bloco «salvar rascunho». Varredor que procura palavra
        # solta acusa quem esta certo; o da macro e o atributo sozinho.
        if (re.search(r"\bdata-rascunho(?![-\w])", h)
                and "salvar_rascunho" not in h):
            escrevem.append(p.name)
    assert not escrevem, (
        f"estas telas escrevem o bloco à mão em vez de chamar a macro: "
        f"{escrevem}")


def test_o_lancamento_do_civil_VOLTA_PARA_O_TIPO_CERTO(casa):
    """**Três rotas desenham a mesma tela**: averbar, anotar e retificar. Uma
    volta fixa abriria uma averbação para quem estava anotando."""
    aid = _assento(casa)
    for endpoint, esperado in (("rcpn_averbar", "averbar"),
                               ("rcpn_anotar", "anotar"),
                               ("rcpn_retificar", "retificar")):
        html = casa["c"].get(_url(casa, endpoint, aid)).get_data(as_text=True)
        volta = re.search(r'name="_volta"\s+value="([^"]+)"', html)
        assert volta, f"{endpoint}: a tela não diz para onde voltar"
        assert volta.group(1).endswith(f"/{esperado}"), (
            f"{endpoint} volta para {volta.group(1)}, e devia terminar em "
            f"/{esperado}")


def test_o_rascunho_NAO_LAVRA_e_a_tela_diz_isso(casa):
    """Rascunho não toma número, não ocupa folha, não sela e não cobra — e a
    tela precisa dizer, senão alguém acha que salvou o ato."""
    aid = _assento(casa)
    html = casa["c"].get(_url(casa, "notas_ato_novo", aid)).get_data(as_text=True)
    assert "não lavra" in html
    assert "não toma número" in html
