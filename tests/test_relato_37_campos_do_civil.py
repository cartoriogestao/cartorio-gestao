"""
O RELATO #37 — «necessidade de amadurecer os campos do registro civil».

Oito itens, escritos pelo oficial em 31/08/2026 na tela de lavrar nascimento.
Cada teste abaixo guarda UM deles, **com a frase que ele escreveu**, porque e a
frase que diz o que ele esperava.

E o pedido termina com «aplicar essa logica, quando cabivel, para os demais
atos do RCPN»: a tela e uma so, com `{% if %}` por especie, entao os itens de
forma valem para as treze — e ha teste que abre outra especie para conferir.
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

import rc_assento as RC                       # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def c(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, "ADMIN")
    cliente = app.test_client()
    cliente.post("/login",
                 data={"username": "tabeliao", "password": SENHA,
                       "csrf_token": _token(
                           cliente.get("/login").get_data(as_text=True))},
                 follow_redirects=True)
    return cliente


@pytest.fixture(autouse=True)
def _selador_da_bancada(cg_casa):
    """Os campos do civil são exercitados com o aparelho TLS disponível."""
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(cg_casa):
        yield


def nascimento(c) -> str:
    return c.get("/rcpn/novo/nascimento").get_data(as_text=True)


# ------------------------------------------------------------- item 1


def test_o_livro_nao_baixa_a_caixa():
    """«no aviso de cima (...) o livro a deve ser escrito com A maiusculo».

    `NOME_DA_ESPECIE` guarda um rotulo COMPOSTO — "Nascimento — Livro A" — e a
    tela escrevia `| lower` sobre ele inteiro para caber no meio de uma frase.
    O `A` e o nome do livro, o mesmo que vai no termo, na certidao e na
    matricula de 32 digitos, e livro nao tem minuscula.
    """
    nome, livro = RC.nome_e_livro("NASCIMENTO")
    assert nome == "Nascimento"
    assert livro == "Livro A"
    # A frase da tela baixa a caixa da ESPECIE, e o livro nao vai junto.
    assert "livro" not in nome.lower()


def test_nenhuma_das_treze_especies_escreve_livro_minusculo():
    """O `OUTRO` era o unico rotulo sem o travessao, e por isso escapava.

    Ele dizia «Outro registro do Livro E» — sem separador —, entao a frase
    inteira baixava a caixa e saia «livro e». A excecao e que era o problema:
    as treze seguem a mesma forma agora.
    """
    ruins = [e for e in RC.NOME_DA_ESPECIE
             if "livro" in RC.nome_e_livro(e)[0].lower()]
    assert ruins == [], f"estas escreveriam «livro» minusculo: {ruins}"


def test_a_tela_escreve_o_livro_com_maiuscula(c):
    """E A COMPARACAO E NO HTML CRU.

    A primeira versao deste teste fazia `html.lower()` e depois procurava
    «livro a» dentro — ou seja, **baixava a caixa da pagina inteira e
    reclamava de achar minuscula**. Ele reprovava a tela por um defeito que
    ele mesmo tinha acabado de criar.
    """
    html = nascimento(c)
    assert "Livro A" in html
    assert "livro a" not in html


# ------------------------------------------------------------- item 2


def test_a_tela_diz_que_o_selo_sai_sozinho(c):
    """«registro civil precisa ganhar o selo pelo sistema».

    MEDIDO ANTES DE MEXER, e o pedido nao era o que parecia: o selo automatico
    do civil esta ligado desde 27/08/2026, o selador respondeu naquele dia (4
    selos das Notas) e ha folha em branco no estoque. O que nunca aconteceu foi
    LAVRAR um assento por este sistema — sao zero fora do acervo.

    Entao nao havia defeito de selo: havia uma tela que mostrava «Selo
    (opcional)» com um codigo de exemplo dentro, e quem le aquilo entende que
    selo e coisa de digitar.
    """
    html = nascimento(c)
    assert "Você não precisa digitar selo" in html
    assert "o selo sai sozinho ao lavrar" in html


def test_a_tela_diz_que_isencao_nao_dispensa_o_selo(c):
    """Isencao e gratuidade, e nao ausencia de ato."""
    assert "isento" in nascimento(c)


def test_a_tela_diz_o_que_acontece_se_o_aparelho_cair(c):
    """A tela não promete mais lavrar um ato sem selo silenciosamente."""
    html = nascimento(c)
    assert "o selo sai sozinho ao lavrar" in html
    assert "Selo (opcional)" not in html


# ------------------------------------------------------------- item 3


def test_naturalidade_e_local_do_parto_sao_duas_coisas(c):
    """«o registrado pode nascer em um local e ser natural de outro».

    A mae mora em Cidade Exemplo e tem o filho no hospital de Imperatriz: o parto
    foi em Imperatriz e a naturalidade e Cidade Exemplo. Escrever uma no lugar da
    outra sai na certidao da pessoa para o resto da vida.
    """
    html = nascimento(c)
    assert "Não é o lugar do parto" in html
    # Os dois campos existem na tela, e em blocos diferentes.
    assert 'name="pessoa_naturalidade_cidade"' in html
    assert 'name="local_fato_nome"' in html


# ------------------------------------------------------------- item 4


def test_o_registrado_nao_tem_campo_de_pais(c):
    """«ocultar referencia a nascimento fora do brasil».

    O registrado nasceu aqui: e o nascimento que esta serventia esta lavrando.
    Nascimento no exterior se registra em reparticao consular.
    """
    assert 'name="pessoa_naturalidade_pais"' not in nascimento(c)


def test_a_filiacao_CONTINUA_com_campo_de_pais(c):
    """E a diferenca nao e descuido: pai e mae PODEM ter nascido fora, e a
    naturalidade deles e o que vai escrito no termo. Esconder ali faria a tela
    deixar de perguntar o que o livro pede."""
    assert 'name="filiacao1_naturalidade_pais"' in nascimento(c)


# ------------------------------------------------------------- item 5


def test_a_data_do_parto_e_exigida(c):
    """«data de nascimento da mae e data do parto sao itens obrigatorios»."""
    html = nascimento(c)
    bloco = html.split('name="data_fato"', 1)[1][:200]
    assert "required" in bloco


def test_a_data_de_nascimento_da_mae_e_exigida(c):
    """A filiacao 1 e a MAE — `PREFIXO_DO_PAPEL` mapeia `filiacao1` para
    `MAE` —, e e dela que sai a idade na ocasiao do parto."""
    assert RC.PREFIXO_DO_PAPEL["MAE"] == "filiacao1"
    html = nascimento(c)
    bloco = html.split('name="filiacao1_data_nascimento"', 1)[1][:220]
    assert "required" in bloco


def test_a_idade_desconta_o_aniversario():
    """«calcular automaticamente a idade da mae na ocasiao do parto».

    E ela DESCONTA O ANIVERSARIO. O E-Oficio fazia `ano − ano` e mandava ao
    IBGE a idade de 3 dos 11 falecidos com um ano a mais — este projeto ja
    pagou esse erro uma vez.
    """
    assert RC.idade_na_data("1995-03-15", "2026-08-31") == 31
    assert RC.idade_na_data("1995-09-01", "2026-08-31") == 30   # nao fez ainda
    assert RC.idade_na_data("1995-08-31", "2026-08-31") == 31   # faz hoje


def test_a_idade_nao_sai_negativa_nem_com_data_faltando():
    """Data do fato anterior ao nascimento e dado errado; devolver um numero
    negativo o esconderia dentro de um papel assinado."""
    assert RC.idade_na_data("2026-09-01", "2026-08-31") is None
    assert RC.idade_na_data("", "2026-08-31") is None
    assert RC.idade_na_data("1995-03-15", "") is None
    assert RC.idade_na_data("nao e data", "2026-08-31") is None


def test_a_tela_diz_que_a_idade_e_calculada_e_que_o_digitado_manda(c):
    """A correcao fica visivel: ate 31/08/2026 esta idade NAO se calculava, e
    o comentario dizia por que. A objecao era sobre o campo faltar."""
    html = nascimento(c)
    assert "Calculada" in html
    # UM PEDACO DE UMA LINHA SO. A frase do template quebra entre «e o» e
    # «que voce digitar», e asserção que atravessa a quebra reprova texto que
    # esta certo — este projeto ja pagou isso antes.
    assert "que você digitar aqui manda" in html


# ------------------------------------------------------------- item 6


def test_as_gavetas_fecham_umas_as_outras(c):
    """«quando abrir um campo, como filiacao 2, guardar os outros (...) para a
    tela nao ficar muito comprida»."""
    html = nascimento(c)
    assert "data-gavetas" in html
    assert "gavetas.js" in html


def test_a_gaveta_com_dado_dentro_nao_se_fecha():
    """O acordeao de fabrica do navegador fecharia a gaveta aberta mesmo com
    campo preenchido dentro — e aqui isso esconderia dado digitado no meio de
    um formulario longo. E o motivo de o arquivo existir."""
    js = (RAIZ / "static" / "gavetas.js").read_text(encoding="utf-8")
    assert "temAlgoEscrito" in js
    assert "!temAlgoEscrito(outra)" in js


# ------------------------------------------------------------- item 7


def test_os_progenitores_de_cada_filiacao_ficam_na_mesma_gaveta(c):
    """«progenitor 1 e 2 de cada filiacao poderiam estar na mesma aba».

    Eram QUATRO paineis para quatro nomes de avos. Sao dois agora, e cada um
    diz de quem sao os avos — `PREFIXO_DO_PAPEL` decide isso, e escrever so
    «filiacao 1» faria o balcao guardar a correspondencia de cabeca.
    """
    html = nascimento(c)
    # 13/10/2026 — a gaveta dos avós passou a ser a do próprio genitor
    # («separar os campos de forma racional, por facilidade para o operador»):
    # os dois avós de cada lado continuam juntos, agora com quem eles são pais.
    assert "Mãe — filiação 1 e avós maternos" in html
    assert "Pai — filiação 2 e avós paternos" in html
    assert "Progenitor 1 da filiação 1" not in html
    mae = html.index("Mãe — filiação 1 e avós maternos")
    pai = html.index("Pai — filiação 2 e avós paternos")
    assert mae < html.index('name="prog1f1_nome"') < html.index('name="prog2f1_nome"') < pai
    assert pai < html.index('name="prog1f2_nome"') < html.index('name="prog2f2_nome"')
    # Os quatro campos continuam existindo, com os nomes que a rota le.
    for campo in ("prog1f1_nome", "prog2f1_nome", "prog1f2_nome",
                  "prog2f2_nome"):
        assert f'name="{campo}"' in html


def test_os_papeis_dos_progenitores_continuam_os_do_dominio():
    """A gaveta muda a TELA, e nao o papel: a filiacao 1 e a mae, entao os
    progenitores dela sao os avos maternos."""
    assert RC.PREFIXO_DO_PAPEL["AVO_MATERNO"] == "prog1f1"
    assert RC.PREFIXO_DO_PAPEL["AVO_MATERNA"] == "prog2f1"
    assert RC.PREFIXO_DO_PAPEL["AVO_PATERNO"] == "prog1f2"
    assert RC.PREFIXO_DO_PAPEL["AVO_PATERNA"] == "prog2f2"


# ------------------------------------------------------------- item 8


def test_o_fato_vem_antes_das_pessoas(c):
    """«dados do nascimento deve aparecer como primeiro campo apos dados do
    registro. dados para remessa do IBGE tambem».

    A ordem antiga era a de quem ESCREVEU a tela — oito gavetas de pessoas
    primeiro, e o fato la embaixo. Quem preenche chega do balcao com a DNV na
    mao e o parto na cabeca.
    """
    html = nascimento(c)
    # 13/10/2026 — os campos do IBGE foram para dentro do bloco do fato, ao
    # lado do campo de que nascem (estão na DNV), e o termo/matrícula foram
    # para o fim («separar por facilidade para o operador»). O que este
    # teste guarda continua: o fato vem antes das pessoas.
    fato = html.index("Dados do nascimento")
    registrado = html.index("Dados do registrado")
    assert fato < html.index('name="dnv"') < registrado
    assert fato < html.index('name="ibge_local"') < registrado
    assert registrado < html.index('name="teor"')


# ------------------- «aplicar (...) para os demais atos do RCPN»


def test_a_logica_vale_para_as_outras_especies(c):
    """A tela e uma so, com `{% if %}` por especie: o que e de forma vale para
    as treze. Aqui se confere no obito, que tem pessoa principal e filiacao."""
    html = c.get("/rcpn/novo/obito").get_data(as_text=True)
    assert "Livro C" in html
    assert "data-gavetas" in html
    assert "Dados do óbito" in html
    # O ITEM 4 NAO VALE PARA O OBITO, e isto e regra e nao esquecimento: a
    # pessoa principal ali e o FALECIDO, que pode muito bem ter nascido fora
    # do Brasil — e a naturalidade dele vai escrita no termo. Quem nasceu aqui
    # por construcao e o registrado do nascimento.
    assert 'name="pessoa_naturalidade_pais"' in html


def test_no_obito_a_data_do_fato_NAO_e_exigida(c):
    """O item 5 e do nascimento, e nao das treze — exigir o que nao se sabe
    faria o balcao inventar. No obito a data vem da declaracao."""
    html = c.get("/rcpn/novo/obito").get_data(as_text=True)
    bloco = html.split('name="data_fato"', 1)[1][:200]
    assert "required" not in bloco

# ------------- 01/09/2026 — CPF do registrado nao se pede no nascimento


def test_o_registrado_do_nascimento_nao_pede_documento(c):
    """No nascimento o registrado ainda nao tem documento: numero e CPF se
    geram no fim, o CPF na CRC. Pedir CPF na gaveta faz o balcao inventar."""
    html = nascimento(c)
    assert 'name="pessoa_documento_numero"' not in html
    assert 'name="pessoa_documento_tipo"' not in html
    assert 'name="pessoa_documento_orgao"' not in html
    assert "O CPF se gera na CRC" in html


def test_a_mae_CONTINUA_com_documento(c):
    """A CRC precisa do CPF da filiacao. Esconder o documento da mae junto
    com o do registrado deixaria a carga sem o que a Central pede."""
    html = nascimento(c)
    assert 'name="filiacao1_documento_numero"' in html
    assert 'name="filiacao1_documento_tipo"' in html
    assert 'name="filiacao2_documento_numero"' in html
    assert 'name="declarante_documento_numero"' in html
    assert 'name="testemunha_documento_numero"' in html


def test_o_natimorto_usa_a_mesma_gaveta_sem_documento(c):
    """A gaveta do registrado e a mesma do nascimento: perfil registrado."""
    html = c.get("/rcpn/novo/natimorto").get_data(as_text=True)
    assert 'name="pessoa_documento_numero"' not in html
    assert 'name="filiacao1_documento_numero"' in html


def test_o_falecido_CONTINUA_com_documento(c):
    """O obito nao e nascimento: o falecido ja viveu com RG/CPF."""
    html = c.get("/rcpn/novo/obito").get_data(as_text=True)
    assert 'name="pessoa_documento_numero"' in html
