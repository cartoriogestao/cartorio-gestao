# -*- coding: utf-8 -*-
"""O pacote do E-Ofício passa para a coluna que a certidão e a CRC leem.

Não inventa, não reescreve coluna preenchida, não separa avô de avó.
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
from ibge_schema import init_ibge_schema             # noqa: E402
from nucleo_schema import init_nucleo_schema         # noqa: E402
from rc_schema import init_rc_schema                 # noqa: E402
import crc_carga as CRC                              # noqa: E402
import rc_campos_do_acervo as CAMPOS                 # noqa: E402
import rc_certidao as CERT                           # noqa: E402

AGORA = "2026-08-20T09:00:00"
M32 = "00000001552026100002269100086802"
CPF = "52998224725"


def _con() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    init_nucleo_schema(con)
    init_rc_schema(con)
    init_ibge_schema(con)
    return con


def _assento(con, **extras) -> int:
    campos = {
        "serie": "RC_A", "especie": "NASCIMENTO", "numero": 1,
        "nome": "ANA EXEMPLO", "data_ato": "2026-08-20",
        "data_fato": "2026-08-18", "situacao": "ATIVO",
        "origem": "EOFICIO", "origem_chave": "tb:1",
        "criado_em": AGORA, "matricula": M32, "dados_json": "{}",
    }
    campos.update(extras)
    cols = list(campos)
    return int(banco(con).valor(
        f"INSERT INTO rc_assentos ({', '.join(cols)}) VALUES ("
        + ", ".join("%s" for _ in cols) + ") RETURNING id",
        tuple(campos[c] for c in cols)))


def _pessoa(con, aid, papel, nome, **extras) -> int:
    campos = {"assento_id": aid, "papel": papel, "nome": nome,
              "nome_norm": nome.lower(), "origem": "EOFICIO",
              "origem_chave": f"tb:{aid}:{papel}", "criado_em": AGORA}
    campos.update(extras)
    cols = list(campos)
    return int(banco(con).valor(
        f"INSERT INTO rc_pessoas ({', '.join(cols)}) VALUES ("
        + ", ".join("%s" for _ in cols) + ") RETURNING id",
        tuple(campos[c] for c in cols)))


def _linha(con, aid):
    return dict(banco(con).um("SELECT * FROM rc_assentos WHERE id=%s", (aid,)))


def test_o_nascimento_importado_ganha_as_colunas_e_a_pessoa():
    con = _con()
    pacote = {
        "strHoraNascimento": "2:18",
        "strNomeLocal": "Hospital Municipal",
        "strMunicipioNascimento": "Cidade do Parto",
        "strSexo": "Masculino",
        "strCidade": "IMPERATRIZ/MA.",
        "strUF": "MA",
        "strCPF": CPF,
        "strDeclaracaoNascidoVivo": "12345678901",
        "bitGemeos": 0,
    }
    aid = _assento(con, dados_json=json.dumps(pacote), origem_chave="nasc:1")
    _pessoa(con, aid, "REGISTRADO", "ANA EXEMPLO")
    feito = CAMPOS.gravar(con, agora=AGORA)
    assert feito["erros"] == 0
    assert feito["assentos"] == 1
    assert feito["pessoas_novas"] == 0
    assert feito["pessoas_atualizadas"] == 1
    a = _linha(con, aid)
    assert a["hora_fato"] == "02:18"
    assert a["local_fato_nome"] == "Hospital Municipal"
    assert a["local_fato_municipio"] == "Cidade do Parto"
    assert a["dnv"] == "12345678901"
    assert a["cpf_registrado"] == CPF
    assert a["ibge_gemeo"] == 1
    assert json.loads(a["dados_json"])["strSexo"] == "Masculino"
    p = dict(banco(con).um(
        "SELECT * FROM rc_pessoas WHERE assento_id=%s AND papel='REGISTRADO'",
        (aid,)))
    assert p["sexo"] == "M"
    assert p["naturalidade_cidade"] == "IMPERATRIZ/MA."
    assert p["naturalidade_uf"] == "MA"
    assert p["documento_tipo"] == "CPF"
    assert p["documento_numero"] == CPF
    assert p["nome"] == "ANA EXEMPLO"
    de_novo = CAMPOS.gravar(con, agora=AGORA)
    assert de_novo == {"assentos": 0, "pessoas_atualizadas": 0,
                       "pessoas_novas": 0, "erros": 0}


def test_coluna_preenchida_nao_e_trocada_pelo_pacote():
    con = _con()
    aid = _assento(
        con, hora_fato="08:00", origem_chave="nasc:2",
        dados_json=json.dumps({"strHoraNascimento": "16:12", "strSexo": "M"}))
    _pessoa(con, aid, "REGISTRADO", "ANA EXEMPLO", sexo="F")
    CAMPOS.gravar(con, agora=AGORA)
    a = _linha(con, aid)
    p = banco(con).um(
        "SELECT sexo FROM rc_pessoas WHERE assento_id=%s", (aid,))
    assert a["hora_fato"] == "08:00"
    assert p["sexo"] == "F"


def test_a_carga_da_crc_le_o_pacote_sem_gravar():
    con = _con()
    aid = _assento(
        con, origem_chave="nasc:3",
        dados_json=json.dumps({
            "strHoraNascimento": "2:18", "strSexo": "Masculino",
            "strDeclaracaoNascidoVivo": "12345678901", "bitGemeos": 0,
        }))
    _pessoa(con, aid, "REGISTRADO", "ANA EXEMPLO")
    montado = CRC.montar(con, [aid], cns="000000")
    assert montado["retidos"] == [], montado["retidos"]
    xml = montado["xml"]
    assert "<HORANASCIMENTO>02:18</HORANASCIMENTO>" in xml
    assert "<SEXO>M</SEXO>" in xml
    assert "<DNV>12345678901</DNV>" in xml
    assert _linha(con, aid)["hora_fato"] in (None, "")


def test_o_obito_deixa_de_ficar_retido_e_a_certidao_diz_a_marca():
    con = _con()
    pacote = {
        "strHoraObito": "19:05", "strCausaMorte": "parada cardiaca",
        "strRacaCor": "Parda", "bitPossuiBens": 1, "bitEleitor": 0.0,
        "strAtestantePrimario": "DRA. EXEMPLO",
        "strTipoLocalObito": "Hospital", "strTipoMorte": "Natural",
        "strNumeroDeclaracaoObito": "998877",
    }
    aid = _assento(
        con, especie="OBITO", serie="RC_C", numero=2, nome="JOSE EXEMPLO",
        origem_chave="obito:1", dados_json=json.dumps(pacote))
    montado = CRC.montar(con, [aid], cns="000000")
    assert montado["retidos"] == [], montado["retidos"]
    xml = montado["xml"]
    assert "<POSSUIBENS>S</POSSUIBENS>" in xml
    assert "<ELEITOR>N</ELEITOR>" in xml
    assert "<HORAOBITO>19:05</HORAOBITO>" in xml
    assert "parada cardiaca" in xml
    assert "<CORPELE>PARDA</CORPELE>" in xml
    assert "<TIPOLOCALOBITO>HOSPITAL</TIPOLOCALOBITO>" in xml
    assert "<TIPOMORTE>NATURAL</TIPOMORTE>" in xml
    assert "<NUMDECLARACAOOBITO>998877</NUMDECLARACAOOBITO>" in xml
    teor = CERT.montar_teor(
        assento=_linha(con, aid), pessoas_do_assento=[], atos=[],
        sv={}, hoje="2026-08-20")
    assert "ERA ELEITOR\nNÃO" in teor
    assert "DEIXOU BENS\nSIM" in teor
    assert "DRA. EXEMPLO" in teor
    assert "parada cardiaca" in teor


def test_json_invalido_nao_atrapalha_o_outro_assento():
    con = _con()
    ruim = _assento(con, origem_chave="ruim", dados_json="{nao e json",
                    nome="RUIM")
    bom = _assento(con, origem_chave="bom", numero=3,
                   dados_json=json.dumps({"strNomeLocal": "Domicilio"}))
    feito = CAMPOS.gravar(con, agora=AGORA)
    assert feito["erros"] == 1
    assert _linha(con, ruim)["local_fato_nome"] in (None, "")
    assert _linha(con, bom)["local_fato_nome"] == "Domicilio"


def test_texto_de_avos_nao_vira_pessoa_nem_coluna():
    con = _con()
    aid = _assento(con, origem_chave="transcrito", dados_json=json.dumps({
        "acervo_transcrito": {
            "hora_fato": "9:05",
            "duvidas": "Conferir uma rubrica.",
            "avos_paternos": "JOÃO EXEMPLO e MARIA EXEMPLO",
        },
    }))
    CAMPOS.gravar(con, agora=AGORA)
    a = _linha(con, aid)
    assert a["hora_fato"] == "09:05"
    assert "duvidas" not in a or not a.get("duvidas")
    papeis = [r["papel"] for r in banco(con).ler(
        "SELECT papel FROM rc_pessoas WHERE assento_id=%s", (aid,))]
    assert "AVO_PATERNO" not in papeis
    assert "AVO_PATERNA" not in papeis
    assert papeis == ["REGISTRADO"]
