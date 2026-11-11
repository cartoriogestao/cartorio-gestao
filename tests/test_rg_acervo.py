"""Lançamento manual de registro de acervo no RCPJ e no RTD.

O livro físico já tem número, folha, data, protocolo e selo. Este caminho
grava isso e não chama o núcleo: não gasta sequência, não abre folha, não
sela e não cobra. A lista de presença dos arts. 410, 412 e 413 não trava.

Nomes e CNPJ são fictícios.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import atrib_certidao as CE  # noqa: E402
import ato_selado as AS  # noqa: E402
import rg_registro as RG  # noqa: E402
from bd_nativo import banco as bd  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from rg_schema import init_rg_schema  # noqa: E402

AGORA = "2026-11-11T10:00:00"
EXTENSO = "onze dias do mês de novembro de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}
CNPJ = "00000043000177"
TEOR = ("Estatuto de exemplo, trasladado do livro físico, sem dado de "
        "pessoa real.")


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    con.execute("CREATE TABLE IF NOT EXISTS cx_protocolos (id INTEGER PRIMARY KEY)")
    init_rg_schema(con)
    return con


def _lancar(con, **extra):
    dados = dict(
        serie="PJ_A", volume="5", numero_ordem="342",
        folha_inicial="25V", folha_final="30",
        data_registro="2021-03-15", protocolo="2021.05.88",
        natureza="Estatuto de associação",
        requerente_nome="SINDICATO DE EXEMPLO DE CIDADE EXEMPLO",
        requerente_documento=CNPJ, teor=TEOR,
        selos_antigos="SELO-ANTIGO-EXEMPLO-2021",
        agora=AGORA, usuario="escrevente.exemplo",
    )
    dados.update(extra)
    return RG.lancar_registro_de_acervo(con, **dados)


def test_lanca_com_o_numero_do_papel_e_sem_sequencia_nem_selo():
    con = banco()
    r = _lancar(con)
    assert r["numero_ordem"] == 342
    assert r["livro"] == "A-5"
    assert r["rotulo"] == "25V a 30"
    assert bd(con).valor("SELECT COUNT(*) n FROM nu_lugares") == 0
    assert bd(con).valor("SELECT COUNT(*) n FROM nu_numeracao") == 0
    assert bd(con).valor("SELECT COUNT(*) n FROM rg_titulos") == 0
    reg = RG.registro(con, r["registro_id"])
    assert reg["origem"] == "ACERVO"
    assert reg["numero"] == 342
    assert reg["volume"] == "5"
    assert reg["protocolo_original"] == "2021.05.88"
    assert reg["atribuicao"] == 3
    assert reg["criado_por"] == "escrevente.exemplo"
    ato = bd(con).um("SELECT * FROM rg_atos WHERE id=%s", (r["ato_id"],))
    assert ato["tipo"] == "REGISTRO"
    assert ato["selo"] in (None, "")
    assert ato["protocolo_id"] is None
    assert ato["livro_id"] is None
    assert ato["folha"] == 25 and ato["verso"] == 1
    assert ato["folha_final"] == 30 and ato["verso_final"] == 0
    assert ato["data_ato"] == "2021-03-15"
    assert ato["origem"] == "ACERVO"
    assert ato["selos_antigos"] == "SELO-ANTIGO-EXEMPLO-2021"
    # o próximo ato novo continua no 1: o acervo não andou o contador
    novo = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                             data_extenso=EXTENSO, natureza="Ato de hoje")
    assert novo["numero_ordem"] == 1
    assert novo["folha"] == 1


def test_o_rtd_entra_do_mesmo_jeito():
    con = banco()
    r = _lancar(con, serie="TD_B", volume="A-7", numero_ordem="88",
                folha_inicial="4", folha_final="4",
                natureza="Contrato particular de exemplo",
                requerente_nome="EMPRESA DE EXEMPLO LTDA",
                requerente_documento=None, selos_antigos=None, teor=None)
    reg = RG.registro(con, r["registro_id"])
    assert reg["atribuicao"] == 4
    assert reg["volume"] == "7"
    assert r["livro"] == "B-7"
    assert r["rotulo"] == "4"
    assert bd(con).valor("SELECT selo FROM rg_atos WHERE id=%s",
                         (r["ato_id"],)) in (None, "")


def test_o_mesmo_livro_e_o_mesmo_numero_nao_entram_duas_vezes():
    con = banco()
    _lancar(con)
    with pytest.raises(RG.RgError, match="Já existe o nº 342 no Livro A-5"):
        _lancar(con, volume="05", requerente_nome="OUTRA ENTIDADE DE EXEMPLO")
    assert bd(con).valor(
        "SELECT COUNT(*) n FROM rg_registros WHERE numero=342") == 1
    # volume diferente é outro livro
    outro = _lancar(con, volume="6", numero_ordem="342")
    assert outro["livro"] == "A-6"
    assert bd(con).valor("SELECT COUNT(*) n FROM rg_registros") == 2


def test_o_numero_que_o_eoficio_ja_trouxe_tambem_bloqueia():
    con = banco()
    bd(con).escrever(
        """INSERT INTO rg_registros(atribuicao, serie, numero, volume,
               natureza, requerente_nome, situacao, origem, origem_chave,
               criado_em)
           VALUES (3,'PJ_A',342,'05','Estatuto','ENTIDADE JA IMPORTADA',
                   'ATIVO','EOFICIO','tbRegistroTD:1',%s)""", (AGORA,))
    with pytest.raises(RG.RgError, match="Nada foi lançado"):
        _lancar(con)
    assert bd(con).valor("SELECT COUNT(*) n FROM rg_atos") == 0


def test_a_lista_de_presenca_nao_trava_e_a_referencia_fica_na_consulta():
    con = banco()
    sem = _lancar(con)
    assert RG.bloco_da_lista_presenca(
        bd(con).valor("SELECT declaracoes FROM rg_atos WHERE id=%s",
                      (sem["ato_id"],))) is None
    assert sem["ato_id"] not in {
        int(a["id"]) for a in RG.atos_sem_declaracao_de_lista(con)}
    com = _lancar(con, numero_ordem="343",
                  lista_presenca_livro="folha 12 do livro")
    bruto = bd(con).valor("SELECT declaracoes FROM rg_atos WHERE id=%s",
                          (com["ato_id"],))
    assert "folha 12 do livro" in RG.texto_da_lista_presenca(bruto)


def test_depois_do_acervo_a_averbacao_e_o_breve_relato_seguem():
    con = banco()
    r = _lancar(con)
    av = RG.lancar_averbacao(
        con, r["registro_id"],
        teor="Averbação posterior de exemplo, lavrada hoje.",
        sv=SV, agora=AGORA, data_extenso=EXTENSO, usuario="escrevente.exemplo")
    assert av["numero_ordem"] == 1
    assert RG.registro(con, r["registro_id"])["numero"] == 342
    RG.gravar_dados_da_pj(
        con, r["registro_id"], sede="Rua de Exemplo, 10, Cidade Exemplo/MA",
        objeto="Representar a categoria de exemplo.", capital=None,
        socios=None, diretoria="Presidência de exemplo.",
        denominacao="SINDICATO DE EXEMPLO DE CIDADE EXEMPLO",
        agora=AGORA, usuario="escrevente.exemplo")
    dados = CE.registro(con, "RCPJ_RTD", r["registro_id"])
    teor = CE.montar_teor("RCPJ_RTD", dados)
    assert 'no Livro "A-5"' in teor
    assert "fls. 25V a 30" in teor
    assert "ATO n. 342" in teor
    assert "15/03/2021" in teor
    breve = CE.teor_do_breve_relato(dados)
    assert "SINDICATO DE EXEMPLO DE CIDADE EXEMPLO" in breve


def test_o_acervo_nao_entra_na_lista_de_ato_sem_selo():
    con = banco()
    r = _lancar(con)
    RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                      data_extenso=EXTENSO)
    ids = [int(a["id"]) for a in AS.atos_sem_selo(con, "rg_atos")]
    assert r["ato_id"] not in ids
    assert ids, "o ato novo, sem selo, continua na lista"


def test_folha_so_de_zeros_nao_entra_e_nao_regride():
    con = banco()
    with pytest.raises(RG.RgError, match="Folha inválida"):
        _lancar(con, folha_inicial="0" * 8000)
    assert bd(con).valor("SELECT COUNT(*) n FROM rg_registros") == 0


def test_folha_invertida_e_cnpj_ruim_nao_gravam():
    con = banco()
    with pytest.raises(RG.RgError, match="folha final"):
        _lancar(con, folha_inicial="30", folha_final="25V")
    with pytest.raises(RG.RgError, match="CNPJ"):
        _lancar(con, requerente_documento="11.111.111/1111-11")
    assert bd(con).valor("SELECT COUNT(*) n FROM rg_registros") == 0
