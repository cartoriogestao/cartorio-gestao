# -*- coding: utf-8 -*-
"""O local de nascimento presumido dos livros A-1 a A-5 (19/11/2026).

A naturalidade do registrado manda; na dúvida, a sede da serventia. Não
toca assento com local, livro fora de 1 a 5, cancelado nem lavratura nova.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from banco_de_teste import conexao_de_teste          # noqa: E402
from bd_nativo import banco                          # noqa: E402
from ibge_schema import init_ibge_schema, normalizar_nome  # noqa: E402
from nucleo_schema import init_nucleo_schema         # noqa: E402
from rc_schema import init_rc_schema                 # noqa: E402
import crc_carga as CRC                              # noqa: E402
import rc_certidao as CERT                           # noqa: E402
import rc_local_presumido as LP                      # noqa: E402
import rc_matricula as MAT                           # noqa: E402

AGORA = "2026-11-19T09:00:00"
CNS = "000001"
SEDE, OUTRA = 2198765, 2198766


def _con() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    init_nucleo_schema(con)
    init_rc_schema(con)
    init_ibge_schema(con)
    bd = banco(con)
    bd.escrever("CREATE TABLE IF NOT EXISTS settings "
                "(key TEXT PRIMARY KEY, value TEXT)")
    for k, v in (("ri_cidade", "Cidade Exemplo"), ("ri_uf", "MA"),
                 ("ri_cns", CNS)):
        bd.escrever("INSERT INTO settings(key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                    (k, v))
    for nome, codigo in (("Cidade Exemplo", SEDE), ("Riacho Fundo", OUTRA)):
        bd.escrever(
            """INSERT INTO ib_municipios (codigo_ibge, codigo_uf, codigo_mun,
                   uf, nome, nome_norm, origem, criado_em)
               VALUES (%s, %s, %s, 'MA', %s, %s, 'TESTE', %s)""",
            (codigo, int(str(codigo)[:2]), str(codigo)[2:], nome,
             normalizar_nome(nome), AGORA))
    return con


def _matricula(livro=3, folha=10, termo=100, ano="1980"):
    return MAT.compor(cns=CNS, ano=ano, livro_tipo="1", livro=livro,
                      folha=folha, termo=termo)


def _assento(con, chave, **extras) -> int:
    campos = {
        "serie": "RC_A", "especie": "NASCIMENTO", "numero": 100,
        "nome": "ANA EXEMPLO", "data_ato": "1980-05-02",
        "data_fato": "1980-04-30", "situacao": "ATIVO",
        "origem": "IMPORTACAO", "origem_chave": chave,
        "criado_em": AGORA, "matricula": _matricula(), "dados_json": "{}",
    }
    campos.update(extras)
    cols = list(campos)
    return int(banco(con).valor(
        f"INSERT INTO rc_assentos ({', '.join(cols)}) VALUES ("
        + ", ".join("%s" for _ in cols) + ") RETURNING id",
        tuple(campos[c] for c in cols)))


def _registrado(con, aid, **extras) -> int:
    campos = {"assento_id": aid, "papel": "REGISTRADO", "nome": "ANA EXEMPLO",
              "nome_norm": "ana exemplo", "sexo": "F", "origem": "IMPORTACAO",
              "origem_chave": f"p:{aid}", "criado_em": AGORA}
    campos.update(extras)
    cols = list(campos)
    return int(banco(con).valor(
        f"INSERT INTO rc_pessoas ({', '.join(cols)}) VALUES ("
        + ", ".join("%s" for _ in cols) + ") RETURNING id",
        tuple(campos[c] for c in cols)))


def _linha(con, aid) -> dict:
    return dict(banco(con).um("SELECT * FROM rc_assentos WHERE id=%s", (aid,)))


def _pessoa(con, aid) -> dict:
    return dict(banco(con).um(
        "SELECT * FROM rc_pessoas WHERE assento_id=%s AND papel='REGISTRADO'",
        (aid,)))


def test_naturalidade_de_outra_cidade_vira_o_local_e_nao_a_sede():
    con = _con()
    aid = _assento(con, "outra")
    _registrado(con, aid, naturalidade_cidade="Riacho Fundo",
                naturalidade_uf="MA")
    r = LP.gravar(con, agora=AGORA)
    a = _linha(con, aid)
    assert r["pela_naturalidade"] == 1 and r["pela_sede"] == 0
    assert a["local_fato_nome"] == "Riacho Fundo/MA"
    assert a["local_fato_municipio"] == "Riacho Fundo"
    dados = json.loads(a["dados_json"])
    assert "NÃO foi transcrito do livro" in dados["local_nascimento_presumido"]
    assert dados["historico"][-1]["registro"] == "AUTO-LOCAL-PRESUMIDO"


def test_sem_naturalidade_vale_a_sede_e_a_crc_ganha_o_codigo():
    con = _con()
    aid = _assento(con, "sede")
    _registrado(con, aid)
    assert any("município de nascimento" in f
               for f in CRC.o_que_falta(con, _linha(con, aid),
                                        CRC._pessoas_do_assento(con, aid)))
    r = LP.gravar(con, agora=AGORA)
    assert r["pela_sede"] == 1 and r["naturalidade_da_sede"] == 1
    assert _linha(con, aid)["local_fato_nome"] == "Cidade Exemplo/MA"
    assert _pessoa(con, aid)["naturalidade_cidade"] == "Cidade Exemplo"
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert f"<CODIGOIBGEMUNNASCIMENTO>{SEDE}</CODIGOIBGEMUNNASCIMENTO>" in xml


def test_a_certidao_deixa_de_dizer_nao_consta():
    con = _con()
    aid = _assento(con, "cert")
    _registrado(con, aid, naturalidade_cidade="Cidade Exemplo",
                naturalidade_uf="MA")
    LP.gravar(con, agora=AGORA)
    a = _linha(con, aid)
    pessoas = CERT.pessoas(con, aid)
    teor = CERT.montar_teor(assento=a, pessoas_do_assento=pessoas, atos=[],
                            sv={}, hoje="2026-11-19",
                            lugar=CERT.lugar_do_assento(con, aid))
    linhas = teor.splitlines()
    i = linhas.index("LOCAL DE NASCIMENTO")
    assert linhas[i + 1] == "Cidade Exemplo/MA"


def test_nao_toca_quem_tem_local_livro_novo_cancelado_ou_lavratura():
    con = _con()
    com_local = _assento(con, "loc", local_fato_nome="HOSPITAL EXEMPLO")
    no_pacote = _assento(con, "pac", dados_json=json.dumps(
        {"local_nascimento": "Povoado Exemplo"}))
    livro_novo = _assento(con, "novo", matricula=_matricula(livro=9))
    outra_letra = _assento(con, "letra", livro_volume="B-3")
    cancelado = _assento(con, "canc", situacao="CANCELADO")
    lavratura = _assento(con, "lav", origem="MANUAL")
    for aid in (com_local, no_pacote, livro_novo, outra_letra, cancelado,
                lavratura):
        _registrado(con, aid)
    r = LP.gravar(con, agora=AGORA)
    assert r == {"pela_naturalidade": 0, "pela_sede": 0,
                 "naturalidade_da_sede": 0, "matriculas": 0}
    assert _linha(con, com_local)["local_fato_nome"] == "HOSPITAL EXEMPLO"
    assert not _linha(con, no_pacote)["local_fato_nome"]


def test_pessoa_com_naturalidade_que_o_ibge_nao_confirma_fica_como_esta():
    """O local vai pela sede, mas a naturalidade escrita não é apagada."""
    con = _con()
    aid = _assento(con, "povoado")
    _registrado(con, aid, naturalidade_cidade="Povoado Sem Cadastro")
    r = LP.gravar(con, agora=AGORA)
    assert r["pela_sede"] == 1 and r["naturalidade_da_sede"] == 0
    assert _pessoa(con, aid)["naturalidade_cidade"] == "Povoado Sem Cadastro"


def test_a_matricula_vazia_se_calcula_e_a_crc_deixa_de_reter():
    con = _con()
    aid = _assento(con, "mat", matricula=None, livro_volume="A-3",
                   numero=4466, data_ato="1982-11-11",
                   dados_json=json.dumps({"folha": "295", "termo": "4466"}))
    _registrado(con, aid, naturalidade_cidade="Cidade Exemplo",
                naturalidade_uf="MA")
    r = LP.gravar(con, agora=AGORA)
    a = _linha(con, aid)
    assert r["matriculas"] == 1
    esperado = MAT.compor(cns=CNS, ano="1982", livro_tipo="1", livro=3,
                          folha=295, termo=4466)
    assert a["matricula"] == esperado
    assert CRC.o_que_falta(con, a, CRC._pessoas_do_assento(con, aid),
                           cns=CNS) == []
    assert json.loads(a["dados_json"])["historico"][-1]["registro"] == \
        "AUTO-MATRICULA"


def test_matricula_sem_folha_nao_se_inventa():
    con = _con()
    aid = _assento(con, "semfolha", matricula=None, livro_volume="A-3")
    _registrado(con, aid)
    assert LP.gravar(con, agora=AGORA)["matriculas"] == 0
    assert not _linha(con, aid)["matricula"]


def test_o_livro_se_le_do_volume_com_a_folha_junto_e_nao_de_outra_letra():
    assert LP.livro_antigo({"livro_volume": "A-02, FLS 180"}) == 2
    assert LP.livro_antigo({"livro_volume": "A-5"}) == 5
    assert LP.livro_antigo({"livro_volume": "A-23"}) is None
    assert LP.livro_antigo({"livro_volume": "B-3",
                            "matricula": _matricula(livro=3)}) is None
    assert LP.livro_antigo({"matricula": _matricula(livro=4)}) == 4
    assert LP.livro_antigo({"matricula": _matricula(livro=14)}) is None


def test_segunda_rodada_nao_muda_nada():
    con = _con()
    aid = _assento(con, "duas")
    _registrado(con, aid)
    LP.gravar(con, agora=AGORA)
    antes = _linha(con, aid)
    r = LP.gravar(con, agora="2026-11-20T09:00:00")
    assert r == {"pela_naturalidade": 0, "pela_sede": 0,
                 "naturalidade_da_sede": 0, "matriculas": 0}
    assert _linha(con, aid) == antes
