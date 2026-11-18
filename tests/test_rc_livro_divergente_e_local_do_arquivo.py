# -*- coding: utf-8 -*-
"""O livro que a matrícula contradiz, e o local de nascimento do formato ARQUIVO.

Auditoria dos nascimentos dos livros A-1 a A-5, 18/11/2026:

  · a certidão imprime o livro do cadastro (`livro_volume`) e a CRC recebe a
    matrícula, que traz outro livro dentro — e nada comparava os dois. Houve
    nascimento com «B-3» no cadastro, gravado pela importação sem conferir;
  · o lote do acervo transcrito (origem ARQUIVO) guarda o lugar do parto em
    `dados_json.local_nascimento`, que a certidão não lia: saía «NÃO CONSTA».

O QUE ESTES TESTES GUARDAM
    `rc_certidao.livro_divergente` acusa letra e número que não batem, e cala
    quando batem ou quando não há livro no cadastro. A frase chega à lista do
    que arrumar da CRC e à ficha do assento. A importação recusa livro de
    outra espécie. O local do pacote ARQUIVO sai na certidão, sem a nota de
    quem transcreveu, e a coluna — que a tela corrige — continua mandando.

Nomes, lugares e matrículas fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from banco_de_teste import conexao_de_teste          # noqa: E402
from bd_nativo import banco                          # noqa: E402
from ibge_schema import init_ibge_schema             # noqa: E402
from nucleo_schema import init_nucleo_schema         # noqa: E402
from rc_schema import init_rc_schema                 # noqa: E402
import crc_carga as CRC                              # noqa: E402
import importar_padrao as IMP                        # noqa: E402
import rc_campos_do_acervo as CAMPOS                 # noqa: E402
import rc_certidao as CERT                           # noqa: E402

AGORA = "2026-11-18T09:00:00"


def _matricula(*, tipo="1", livro=5, folha=36, termo=695, ano=1976) -> str:
    """32 dígitos na forma do Anexo IV; CNS fictício, DV não importa aqui."""
    return (f"000000" "01" "55" f"{ano:04d}" f"{tipo}" f"{livro:05d}"
            f"{folha:03d}" f"{termo:07d}" "00")


# ------------------------------------------------ a régua do livro divergente


def test_numero_do_livro_diferente_da_matricula_e_acusado():
    frase = CERT.livro_divergente({
        "especie": "NASCIMENTO", "livro_volume": "A-5",
        "matricula": _matricula(livro=6)})
    assert "«A-5»" in frase
    assert "Livro A-6" in frase


def test_letra_de_outra_especie_e_acusada_mesmo_com_o_numero_certo():
    """«B-3» num nascimento: a matrícula diz A-3, e a certidão diria B-3."""
    frase = CERT.livro_divergente({
        "especie": "NASCIMENTO", "livro_volume": "B-3",
        "matricula": _matricula(livro=3)})
    assert "«B-3»" in frase and "Livro A-3" in frase


def test_sem_matricula_a_letra_e_conferida_pela_especie():
    frase = CERT.livro_divergente({
        "especie": "NASCIMENTO", "livro_volume": "C-5", "matricula": None})
    assert "Livro A" in frase


@pytest.mark.parametrize("assento", [
    {"especie": "NASCIMENTO", "livro_volume": "A-5",
     "matricula": _matricula(livro=5)},
    {"especie": "NASCIMENTO", "livro_volume": "Livro A 5",
     "matricula": _matricula(livro=5)},
    # O E-Ofício grava só o número no casamento: número certo, nada a dizer.
    {"especie": "CASAMENTO", "livro_volume": "5",
     "matricula": _matricula(tipo="2", livro=5)},
    {"especie": "CASAMENTO_RELIGIOSO", "livro_volume": "BA-2",
     "matricula": _matricula(tipo="3", livro=2)},
    # Sem livro no cadastro a certidão já usa a matrícula.
    {"especie": "NASCIMENTO", "livro_volume": "",
     "matricula": _matricula(livro=9)},
    {"especie": "NASCIMENTO", "livro_volume": "A-5", "matricula": None},
])
def test_livro_que_bate_nao_gera_aviso(assento):
    assert CERT.livro_divergente(assento) == ""


def test_a_frase_entra_na_lista_do_que_arrumar_da_crc():
    """A CRC recebe a matrícula; a lista avisa, e não retém."""
    assento = {"especie": "NASCIMENTO", "livro_volume": "A-1",
               "matricula": _matricula(livro=14), "nome": "ANA EXEMPLO"}
    pessoas = {"MAE": {"nome": "MARIA EXEMPLO", "sexo": "F"}}
    arrumar = CRC.o_que_arrumar(None, assento, pessoas)
    assert arrumar and "«A-1»" in arrumar[0] and "Livro A-14" in arrumar[0]
    certo = dict(assento, livro_volume="A-14")
    assert not any("livro do cadastro" in f
                   for f in CRC.o_que_arrumar(None, certo, pessoas))


# ------------------------------------ a importação recusa livro de outra espécie


@pytest.fixture()
def con(cg_db, cg_db_path):
    c = sqlite3.connect(str(cg_db_path))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _arquivo(registros) -> str:
    return json.dumps({"formato": IMP.FORMATO, "versao": IMP.VERSAO,
                       "especie": "RCPN_ASSENTO",
                       "de_onde_veio": "Acervo fictício",
                       "registros": registros}, ensure_ascii=False)


def _registro(chave, livro, especie="NASCIMENTO") -> dict:
    return {"chave": chave, "serie": "RC_A", "especie": especie,
            "nome": "AUGUSTO EXEMPLO", "numero": "695",
            "data_ato": "1976-07-22", "livro_volume": livro}


def test_importacao_recusa_livro_de_casamento_num_nascimento(con):
    quadro = IMP.conferir(con, _arquivo([
        _registro("x-1", "B-3"), _registro("x-2", "A-3"),
        _registro("x-3", "3"), _registro("x-4", "c-5")]))
    entram = {e["chave"] for e in quadro["entram"]}
    recusados = {r["chave"]: r["porque"] for r in quadro["recusados"]}
    assert entram == {"x-2", "x-3"}
    assert set(recusados) == {"x-1", "x-4"}
    assert "Livro A" in recusados["x-1"]


def test_importacao_aceita_a_letra_certa_de_cada_especie(con):
    quadro = IMP.conferir(con, _arquivo([
        _registro("c-1", "B-2", especie="CASAMENTO"),
        _registro("o-1", "C-4", especie="OBITO")]))
    assert quadro["recusados"] == []


# --------------------------------------- o local de nascimento do formato ARQUIVO


def test_o_local_do_pacote_perde_so_a_nota_de_coluna():
    f = CAMPOS.local_nascimento_do_arquivo
    assert f({"local_nascimento": "Cidade Exemplo-UF (o teor não cita "
                                  "estabelecimento; coluna_exemplo deixado "
                                  "NULL)"}) == "Cidade Exemplo-UF"
    assert (f({"local_nascimento": "Povoado Riacho Fundo (domicílio)"})
            == "Povoado Riacho Fundo (domicílio)")
    assert f({"local_nascimento": {"nome": "objeto"}}) == ""
    assert f({}) == "" and f(None) == ""


def _con_rc() -> sqlite3.Connection:
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    init_nucleo_schema(c)
    init_rc_schema(c)
    init_ibge_schema(c)
    return c


def _assento_arquivo(c, **extras) -> dict:
    campos = {
        "serie": "RC_A", "especie": "NASCIMENTO", "numero": 1730,
        "nome": "ANA EXEMPLO", "data_ato": "1965-11-29",
        "data_fato": "1965-02-11", "situacao": "ATIVO",
        "origem": "ARQUIVO", "origem_chave": "papel:1", "criado_em": AGORA,
        "livro_volume": "A-5",
        "matricula": _matricula(livro=5, folha=85, termo=1730, ano=1965),
        "dados_json": json.dumps({"local_nascimento":
                                  "Hospital Exemplo, Cidade Exemplo-UF"}),
    }
    campos.update(extras)
    cols = list(campos)
    aid = banco(c).valor(
        f"INSERT INTO rc_assentos ({', '.join(cols)}) VALUES ("
        + ", ".join("%s" for _ in cols) + ") RETURNING id",
        tuple(campos[k] for k in cols))
    return dict(banco(c).um("SELECT * FROM rc_assentos WHERE id=%s", (aid,)))


def _teor(assento) -> str:
    return CERT.montar_teor(assento=assento, pessoas_do_assento=[], atos=[],
                            sv={}, hoje="2026-11-18")


def test_o_local_do_pacote_arquivo_sai_na_certidao():
    c = _con_rc()
    teor = _teor(_assento_arquivo(c))
    assert "LOCAL DE NASCIMENTO\nHospital Exemplo, Cidade Exemplo-UF" in teor


def test_a_coluna_corrigida_na_tela_vence_o_pacote():
    c = _con_rc()
    teor = _teor(_assento_arquivo(c, local_fato_nome="Domicílio, Riacho Fundo"))
    assert "LOCAL DE NASCIMENTO\nDomicílio, Riacho Fundo" in teor
    assert "Hospital Exemplo" not in teor


def test_a_crc_deduz_o_tipo_do_local_pelo_pacote_sem_gravar():
    """LOCALNASCIMENTO sai do tipo (hospital = unidade de saúde)."""
    c = _con_rc()
    a = _assento_arquivo(c)
    completo, _ = CAMPOS.completar(a, {})
    assert completo["ibge_local_nascimento"] == 1
    assert a.get("ibge_local_nascimento") is None
    assert completo.get("local_fato_nome") in (None, "")


# ------------------------------------------------------------ o aviso, na ficha


def test_a_ficha_avisa_o_livro_que_diverge_da_matricula(cg_casa_logada):
    casa = cg_casa_logada
    c = sqlite3.connect(str(casa["banco"]))
    c.row_factory = sqlite3.Row
    with c:
        for numero, livro in ((695, "B-3"), (696, "A-5")):
            c.execute(
                """INSERT INTO rc_assentos(serie, especie, numero, matricula,
                       nome, livro_volume, data_ato, dados_json, situacao,
                       origem, criado_em)
                   VALUES ('RC_A','NASCIMENTO',?,?,'ANA EXEMPLO',?,
                           '1976-07-22','{}','ATIVO','IMPORTACAO',?)""",
                (numero, _matricula(livro=5, termo=numero), livro, AGORA))
        ids = {r["numero"]: r["id"] for r in c.execute(
            "SELECT id, numero FROM rc_assentos WHERE numero IN (695, 696)")}
    c.close()
    errado = casa["c"].get(f"/rcpn/{ids[695]}").get_data(as_text=True)
    assert "diverge da matrícula" in errado
    assert "«B-3»" in errado and "Livro A-5" in errado
    assert "Confira o livro antes de assinar" in errado
    certo = casa["c"].get(f"/rcpn/{ids[696]}").get_data(as_text=True)
    assert "diverge da matrícula" not in certo
