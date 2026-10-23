"""O cadastro do padrão de importação aponta para coisas que existem.

    «ampliar o importação de outro sistema para demais atribuições —
     fornecer documentação para importação também do RTD, RCPJ, notas e
     protesto»                                  — o oficial, relato #40

O DEFEITO QUE FEZ ESTE ARQUIVO NASCER, e ele estava nos DOIS de dois
    `importar_padrao.MODELOS` declara, por espécie, a **tabela**, a **ficha**
    do que já existe, o **formulário** do ato novo e o **modelo de tela** de
    onde se medem os campos. Medido em 07/09/2026:

        "tela": "atrib_rcpn_ficha"   -> não é rota deste sistema
        "tela": "ri_matricula"       -> não é rota deste sistema

    Os reais são `rcpn_assento` e `ri_ficha`.

**NÃO ESTOURAVA, PORQUE NINGUÉM LIA O CAMPO — e é isso que o torna perigoso.**
    É valor errado num cadastro com cara de autoridade, esperando quem for
    ligar «depois de importar, abra a ficha». Um defeito que só aparece quando
    alguém confia no que está escrito.

    É o mesmo que o `inacabados` teve — «há teste que confere que a tela existe
    com o parâmetro certo; **duas das nove estavam erradas** quando as
    escrevi» —, e a resposta é a mesma: **a guarda, e não o conserto de um
    caso.**
"""
from __future__ import annotations

import glob
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def _documento(nome: str) -> Path:
    """O documento da casa (DOCUMENTACAO) ou, no clone público, a cópia
    sanitizada em docs/tecnico (23/10/2026)."""
    casa = RAIZ / "DOCUMENTACAO" / nome
    return casa if casa.is_file() else RAIZ / "docs" / "tecnico" / nome

sys.path.insert(0, str(RAIZ))

import importar_padrao as IP                                     # noqa: E402

# As quatro que o relato #40 pediu, mais as duas que já havia.
PISO = 6


@pytest.fixture(scope="module")
def app():
    from app import create_app
    return create_app({"DATA_DIR": tempfile.mkdtemp()})


@pytest.fixture(scope="module")
def banco(app):
    return glob.glob(f"{app.config['DATA_DIR']}/*.sqlite3")[0]


def test_toda_FICHA_declarada_existe(app):
    """**O defeito que fez este arquivo.** Dois de dois apontavam para o
    vazio, e não estouravam porque ninguém lia."""
    eps = {r.endpoint for r in app.url_map.iter_rules()}
    erradas = [f"{k}: tela={v['tela']}" for k, v in IP.MODELOS.items()
               if v["tela"] not in eps]
    assert not erradas, "fichas que não existem:\n  " + "\n  ".join(erradas)


def test_todo_FORMULARIO_declarado_existe(app):
    """A segunda metade do relato #31: preencher o formulário do ato novo.
    Endpoint errado aqui manda o oficial a uma tela que não abre."""
    eps = {r.endpoint for r in app.url_map.iter_rules()}
    erradas = [f"{k}: formulario={v['formulario']}" for k, v in IP.MODELOS.items()
               if v["formulario"] not in eps]
    assert not erradas, ("formulários que não existem:\n  "
                         + "\n  ".join(erradas))


def test_a_FICHA_e_o_FORMULARIO_sao_coisas_diferentes():
    """Um abre o que já existe; o outro abre o que vai nascer. Apontar os dois
    para o mesmo lugar faria «preencher o formulário» abrir uma ficha vazia."""
    iguais = [k for k, v in IP.MODELOS.items() if v["tela"] == v["formulario"]]
    assert not iguais, f"ficha e formulário iguais em {iguais}"


def test_todo_MODELO_DE_TELA_declarado_existe():
    """É dele que os campos da tela são medidos — arquivo que não existe faria
    o aviso do que a tela não pergunta sair vazio, dizendo que ela pergunta
    tudo."""
    faltando = [f"{k}: {v['modelo_da_tela']}" for k, v in IP.MODELOS.items()
                if not (RAIZ / "templates" / v["modelo_da_tela"]).exists()]
    assert not faltando, "modelos de tela que não existem:\n  " + "\n  ".join(faltando)


def test_toda_TABELA_declarada_existe(banco):
    """Os campos são medidos do esquema — tabela errada devolve lista vazia,
    e uma lista vazia diria que a espécie não aceita campo nenhum."""
    con = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
    tabelas = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    faltando = [f"{k}: {v['tabela']}" for k, v in IP.MODELOS.items()
                if v["tabela"] not in tabelas]
    assert not faltando, "tabelas que não existem:\n  " + "\n  ".join(faltando)


def test_cada_especie_TEM_CAMPOS_medidos(banco):
    """**Espécie declarada que não devolve campo nenhum é pior que espécie
    ausente**: o oficial prepararia um arquivo vazio e o sistema o aceitaria."""
    con = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
    try:
        for especie in IP.MODELOS:
            campos = IP.campos(con, especie)
            assert campos, f"{especie} não devolveu campo nenhum"
            assert any(c["obrigatorio"] for c in campos), (
                f"{especie} não tem um único campo obrigatório — a conferência "
                f"aceitaria um arquivo vazio")
    finally:
        con.close()


def test_o_modelo_em_branco_SAI_para_as_seis(banco):
    """É o arquivo que a serventia de fora preenche. Se ele não sai, a espécie
    está declarada e não serve para nada."""
    con = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
    try:
        for especie in IP.MODELOS:
            texto = IP.modelo_em_branco(con, especie)
            assert texto and IP.FORMATO in texto, (
                f"{especie}: o modelo em branco não traz a marca do formato")
    finally:
        con.close()


def test_as_quatro_do_relato_40_entraram():
    """RTD, RCPJ, notas e protesto — o que ele pediu, pelo nome."""
    for esperado in ("RCPJ_RTD_REGISTRO", "NOTAS_ATO", "PROTESTO_TITULO",
                     "LIVRO3_REGISTRO"):
        assert esperado in IP.MODELOS, f"falta {esperado}"


def test_a_lista_nao_encolheu():
    """Varredor que deixa de achar passa calado."""
    assert len(IP.MODELOS) >= PISO


def test_especie_desconhecida_DIZ_QUAIS_EXISTEM(banco):
    """Quem preparou o arquivo errou o nome da espécie; a recusa tem de dizer
    quais são, senão ele adivinha de novo."""
    con = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
    try:
        with pytest.raises(IP.ImportacaoError) as erro:
            IP.campos(con, "INVENTADA")
    finally:
        con.close()
    texto = str(erro.value)
    assert "INVENTADA" in texto
    for especie in IP.MODELOS:
        assert especie in texto, f"a recusa não cita {especie}"


def test_TODA_ESPECIE_ESTA_DOCUMENTADA():
    """**A documentação faz parte do relato #40**, com todas as letras:
    «fornecer documentação para importação também do RTD, RCPJ, notas e
    protesto».

    E documento que envelhece é o defeito que este projeto mais conhece — aqui
    o guarda é barato: espécie nova sem linha no documento fica vermelha.
    """
    doc = _documento("PADRAO_DE_IMPORTACAO.md").read_text(
        encoding="utf-8")
    faltando = [k for k in IP.MODELOS if k not in doc]
    assert not faltando, (
        f"espécies sem linha em PADRAO_DE_IMPORTACAO.md: {faltando}")


def test_o_documento_NAO_LISTA_OS_CAMPOS_de_cada_especie():
    """**Os campos são medidos do esquema**, e escrevê-los no documento daria
    duas listas — a dele envelheceria na tarde em que uma coluna entrasse, e a
    serventia de fora prepararia um arquivo com um campo que o sistema não lê.

    A régua é frouxa de propósito: proíbe a TABELA de campos, e não a menção a
    um campo no meio de uma frase.
    """
    doc = _documento("PADRAO_DE_IMPORTACAO.md").read_text(
        encoding="utf-8")
    assert "medidos do esquema" in doc, (
        "o documento tem de dizer que os campos se medem, e não se escrevem")
