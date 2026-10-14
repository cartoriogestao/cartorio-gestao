"""AS PESSOAS DENTRO DO REGISTRO — a ampliacao de 12/09/2026.

POR QUE ELA EXISTE
    Ate aqui o padrao gravava **uma tabela so**, e o assento entrava sem as
    pessoas. Medido ao construir a importacao do acervo em `.docx`: a CRC le o
    **sexo** e o **municipio de nascimento** do REGISTRADO, e a filiacao e o
    PAI e a MAE de `rc_pessoas` — nenhum dos tres mora em `rc_assentos`. Sem
    elas, todo registro importado cairia em `crc_carga.o_que_falta`, que
    **retem** o registro na Central.

    O oficial escolheu este caminho — ampliar o padrao — em vez de um segundo
    arquivo carregado depois.

O QUE ESTES TESTES GUARDAM

    **Que o papel sai da regua de `rc_assento`, e nao de uma copia aqui.** Uma
    segunda lista deixaria gravar um NUBENTE num assento de obito, e o defeito
    so apareceria na certidao, meses depois.

    **Que `nome_norm` e preenchido com A MESMA funcao da casa.** Ele e a coluna
    que a busca por nome consulta, e pessoa importada sem ele **existe e nao e
    achada** — falha calada, que e a pior deste projeto.

    **Que a chave de origem e DA PESSOA.** Com a chave do assento, os dois
    nubentes colidiriam no `UNIQUE(origem, origem_chave)` e o segundo nao
    entraria, com o contador dizendo que entrou — foi o que ja aconteceu na
    carga do acervo.

    **Que pessoa ruim recusa o REGISTRO INTEIRO**, ao contrario do resto do
    modulo. Assento gravado sem a filiacao que o arquivo trazia fica com cara
    de completo, e ninguem volta para conferir.

    **Que a ordem nao vem do arquivo**: ela ja esta dita pela posicao na lista,
    e duas fontes para o mesmo fato divergem.
"""
from __future__ import annotations

import glob
import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import importar_padrao as IMP                                    # noqa: E402

AGORA = "2026-09-12T10:00"


@pytest.fixture()
def con(cg_db, cg_db_path):
    c = sqlite3.connect(str(cg_db_path))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _arquivo(registros) -> str:
    return json.dumps({"formato": IMP.FORMATO, "versao": IMP.VERSAO,
                       "especie": "RCPN_ASSENTO",
                       "de_onde_veio": "Acervo em .docx desta serventia",
                       "registros": registros}, ensure_ascii=False)


def _assento(chave="1998-A-12-11309", **extra) -> dict:
    r = {"chave": chave, "serie": "RC_A", "especie": "NASCIMENTO",
         "nome": "AUGUSTO SILVA LIMA", "numero": "11309",
         "data_ato": "1998-11-17"}
    r.update(extra)
    return r


PAI_E_MAE = [
    {"papel": "PAI", "nome": "JOSÉ DE SOUSA LIMA", "sexo": "M"},
    {"papel": "MAE", "nome": "MARIA DA LUZ DA CONCEIÇÃO SILVA", "sexo": "F"},
]


# --------------------------------------------- os campos da pessoa, medidos


def test_os_campos_da_pessoa_saem_do_esquema(con):
    """A mesma regra do registro: medidos, e nao escritos a mao."""
    nomes = {c["nome"] for c in IMP.campos_da_pessoa(con, "RCPN_ASSENTO")}
    assert {"papel", "nome", "sexo", "naturalidade_cidade"} <= nomes
    # O que a maquina controla nunca entra pelo arquivo.
    assert "assento_id" not in nomes          # a chave estrangeira
    assert "ordem" not in nomes               # e posicional
    assert "nome_norm" not in nomes           # e derivado
    assert "origem_chave" not in nomes


def test_especie_sem_pessoas_devolve_lista_vazia(con):
    """O RI nao recebe pessoas por aqui, e dizer isso e melhor que estourar."""
    assert IMP.campos_da_pessoa(con, "RI_MATRICULA") == []


def test_o_modelo_em_branco_MOSTRA_as_pessoas(con):
    """O que nao aparece no exemplo nao e mandado por quem prepara o arquivo."""
    modelo = json.loads(IMP.modelo_em_branco(con, "RCPN_ASSENTO"))
    pessoas = modelo["registros"][0]["pessoas"]
    assert isinstance(pessoas, list) and pessoas
    assert "papel" in pessoas[0] and "nome" in pessoas[0]


# ------------------------------------------------------- o papel, da regua


def test_o_papel_vem_da_regua_de_rc_assento_e_nao_de_uma_copia():
    """**A MESMA regua, e nao uma parecida** — ha uma so lista de papeis."""
    import rc_assento

    for especie, papeis in rc_assento.PAPEIS_DA_ESPECIE.items():
        assert IMP.papeis_aceitos(especie) == papeis


def test_papel_que_a_especie_nao_admite_recusa_o_registro(con):
    """NUBENTE num nascimento e o erro que so apareceria na certidao."""
    arquivo = _arquivo([_assento(pessoas=[
        {"papel": "NUBENTE1", "nome": "FULANO DE TAL"}])])
    quadro = IMP.conferir(con, arquivo)
    assert quadro["entram"] == []
    assert "NUBENTE1" in quadro["recusados"][0]["porque"]


def test_pessoa_sem_nome_recusa_o_registro_inteiro(con):
    """**Pessoa ruim nao deixa o assento entrar pela metade.** Assento gravado
    sem a filiacao que o arquivo trazia fica com cara de completo."""
    arquivo = _arquivo([_assento(pessoas=[{"papel": "PAI", "nome": ""}])])
    quadro = IMP.conferir(con, arquivo)
    assert quadro["entram"] == []
    assert "nome" in quadro["recusados"][0]["porque"]


def test_campo_desconhecido_na_pessoa_nao_passa_calado(con):
    arquivo = _arquivo([_assento(pessoas=[
        {"papel": "PAI", "nome": "JOSÉ DE SOUSA LIMA", "profisao": "lavrador"}
    ])])
    quadro = IMP.conferir(con, arquivo)
    assert quadro["entram"] == []
    assert "profisao" in quadro["recusados"][0]["porque"]


# ------------------------------------------------------------- a gravacao


def test_as_pessoas_entram_amarradas_ao_assento(con):
    quadro = IMP.importar(con, _arquivo([_assento(pessoas=PAI_E_MAE)]),
                          agora=AGORA)
    assert quadro["entraram"] == 1
    assert quadro["pessoas_entraram"] == 2

    assento = con.execute(
        "SELECT id FROM rc_assentos WHERE origem_chave=?",
        ("1998-A-12-11309",)).fetchone()
    linhas = con.execute(
        "SELECT papel, nome, ordem, nome_norm, origem_chave FROM rc_pessoas "
        "WHERE assento_id=? ORDER BY ordem", (assento["id"],)).fetchall()
    assert [r["papel"] for r in linhas] == ["PAI", "MAE"]
    assert [r["ordem"] for r in linhas] == [1, 2]


def test_nome_norm_e_o_da_casa_e_nao_fica_vazio(con):
    """**A coluna que a busca consulta.** Vazia, a pessoa existe e nao e
    achada por nome — e ninguem desconfia de uma busca que volta vazia."""
    from pt_schema import normalizar_nome

    IMP.importar(con, _arquivo([_assento(pessoas=PAI_E_MAE)]), agora=AGORA)
    linha = con.execute(
        "SELECT nome, nome_norm FROM rc_pessoas WHERE papel='MAE'").fetchone()
    assert linha["nome_norm"]
    assert linha["nome_norm"] == normalizar_nome(linha["nome"])


def test_a_chave_de_origem_e_DA_PESSOA_e_dois_nubentes_nao_colidem(con):
    """Com a chave do assento, o segundo nao entraria — e o contador diria que
    entrou. Foi o que aconteceu na carga do acervo."""
    registro = {"chave": "1957-B-01-39", "serie": "RC_B",
                "especie": "CASAMENTO", "nome": "JOÃO E MARIA",
                "numero": "39", "data_ato": "1957-05-04",
                "pessoas": [
                    {"papel": "NUBENTE1", "nome": "JOÃO DA SILVA"},
                    {"papel": "NUBENTE2", "nome": "MARIA DAS DORES"}]}
    quadro = IMP.importar(con, _arquivo([registro]), agora=AGORA)
    assert quadro["pessoas_entraram"] == 2
    chaves = {r[0] for r in con.execute(
        "SELECT origem_chave FROM rc_pessoas WHERE origem=?",
        (IMP.MARCA_DA_ORIGEM,))}
    assert len(chaves) == 2


def test_registro_sem_pessoas_continua_entrando(con):
    """A ampliacao nao passou a exigir pessoas: o arquivo antigo continua bom."""
    quadro = IMP.importar(con, _arquivo([_assento()]), agora=AGORA)
    assert quadro["entraram"] == 1
    assert quadro["pessoas_entraram"] == 0


def test_conferir_com_pessoas_nao_grava(con):
    """Conferir e importar continuam sendo dois passos."""
    IMP.conferir(con, _arquivo([_assento(pessoas=PAI_E_MAE)]))
    assert con.execute("SELECT COUNT(*) FROM rc_pessoas").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0] == 0


def test_o_que_a_CRC_EXIGE_chega_pela_importacao(con):
    """**A razao de tudo isto.** O sexo e o municipio de nascimento do
    registrado sao faltas que RETEM o registro na Central, e nenhum dos dois
    mora em `rc_assentos`."""
    import crc_carga

    registro = _assento(pessoas=[
        {"papel": "REGISTRADO", "nome": "AUGUSTO SILVA LIMA", "sexo": "M",
         "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "MA"},
    ] + PAI_E_MAE)
    IMP.importar(con, _arquivo([registro]), agora=AGORA)

    assento = dict(con.execute(
        "SELECT * FROM rc_assentos WHERE origem_chave=?",
        ("1998-A-12-11309",)).fetchone())
    pessoas = {r["papel"]: dict(r) for r in con.execute(
        "SELECT * FROM rc_pessoas WHERE assento_id=?", (assento["id"],))}

    faltas = crc_carga.o_que_falta(con, assento, pessoas)
    assert not any("sexo do registrado" in f for f in faltas), faltas
    assert not any("município de nascimento" in f for f in faltas), faltas
