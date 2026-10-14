"""Serviço do editor — rascunho, publicar, seed, chave, validação, diff."""
from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_da_casa as CASA
import modelos_elementos as ELEM
import modelos_elementos_schema as ESQ
import modelos_moldes as MOLDES
import ri_schema
import modelos_editor as ED
from modelos_editor_schema import (
    AREA_RCPN, PARTE_CORPO, PARTE_MOLDE,
    STATUS_PUBLICADA, STATUS_RASCUNHO, init_modelos_editor_schema,
)

AGORA = "2026-10-05T15:00:00"


@pytest.fixture()
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "t.sqlite3")
    c.row_factory = sqlite3.Row
    ri_schema.init_ri_schema(c)
    ESQ.init_modelos_elementos_schema(c)
    MOLDES.init_modelos_moldes_schema(c)
    init_modelos_editor_schema(c)
    # settings mínima para a chave
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.commit()
    yield c
    c.close()


def _settings_gen():
    """Fixture genérica — SEM literais da casa real."""
    return {
        "unit_name": "OFICIO DE EXEMPLO",
        "serventia_titular": "Fulano de Tal",
        "serventia_titulo": "Oficial",
        "ri_substituta": "Beltrana",
        "serventia_cnpj": "00.000.010/0001-27",
        "ri_cns": "000000",
        "serventia_telefone": "(00) 0000-0000",
        "serventia_endereco": "Rua Exemplo, 1",
        "serventia_cep": "00.000-000",
        "ri_cidade": "Cidade Exemplo",
        "ri_uf": "EX",
        "serventia_email": "exemplo@example.com",
        "serventia_brasao": "",
    }


def test_rascunho_diferente_de_publicada(con):
    ED.semear_v1(con, template_id="RC_TERMO_NASCIMENTO", agora=AGORA)
    pub = ED.carregar(con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
                      parte=PARTE_CORPO, qual="publicada")
    ED.salvar_rascunho(
        con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
        parte=PARTE_CORPO, conteudo=(pub["conteudo"] or "") + "\n<!--rascunho-->",
        autor="teste", agora=AGORA)
    rasc = ED.carregar(con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
                       parte=PARTE_CORPO, qual="rascunho")
    assert rasc["status"] == STATUS_RASCUNHO
    assert pub["status"] == STATUS_PUBLICADA
    assert rasc["sha256"] != pub["sha256"]
    assert "<!--rascunho-->" in (rasc["conteudo"] or "")
    assert "<!--rascunho-->" not in (pub["conteudo"] or "")


def test_user_nao_publica(con):
    ED.salvar_rascunho(
        con, area=AREA_RCPN, template_id="RC_TERMO_CASAMENTO",
        parte=PARTE_CORPO, conteudo=CASA.padrao_de("RC_TERMO_CASAMENTO"),
        autor="user", agora=AGORA)
    with pytest.raises(ED.EditorError, match="ADMIN|MANAGER"):
        ED.publicar(
            con, area=AREA_RCPN, template_id="RC_TERMO_CASAMENTO",
            parte=PARTE_CORPO, autor="user", agora=AGORA,
            papel_usuario="USER", get_settings=_settings_gen)


def test_admin_publica(con):
    texto = CASA.padrao_de("RC_TERMO_OBITO")
    ED.salvar_rascunho(
        con, area=AREA_RCPN, template_id="RC_TERMO_OBITO",
        parte=PARTE_CORPO, conteudo=texto, autor="admin", agora=AGORA)
    pub = ED.publicar(
        con, area=AREA_RCPN, template_id="RC_TERMO_OBITO",
        parte=PARTE_CORPO, autor="admin", agora=AGORA,
        papel_usuario="ADMIN", get_settings=_settings_gen)
    assert pub["status"] == STATUS_PUBLICADA
    assert pub["conteudo"] == texto


def test_restaurar_como_rascunho(con):
    ED.semear_v1(con, template_id="RC_TERMO_LIVRO_E", agora=AGORA)
    pub = ED.carregar(con, area=AREA_RCPN, template_id="RC_TERMO_LIVRO_E",
                      qual="publicada")
    ED.salvar_rascunho(
        con, area=AREA_RCPN, template_id="RC_TERMO_LIVRO_E",
        parte=PARTE_CORPO, conteudo="alterado", autor="x", agora=AGORA)
    novo = ED.restaurar_como_rascunho(
        con, pub["id"], autor="x", agora=AGORA)
    assert novo["status"] == STATUS_RASCUNHO
    assert novo["conteudo"] == pub["conteudo"]


def test_diff_textual(con):
    ED.salvar_rascunho(
        con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
        parte=PARTE_CORPO, conteudo="linha A\n", autor="a", agora=AGORA)
    r1 = ED.carregar(con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
                     qual="rascunho")
    ED.salvar_rascunho(
        con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
        parte=PARTE_CORPO, conteudo="linha B\n", autor="a", agora=AGORA)
    r2 = ED.carregar(con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
                     qual="rascunho")
    # r1 foi arquivado; buscar pelo id
    d = ED.diff_versoes(con, r1["id"], r2["id"])
    assert d["iguais"] is False
    assert "linha" in d["diff"]


def test_semente_byte_a_byte_termos(con):
    feitos = ED.semear_v1(con, agora=AGORA)
    termos = [f for f in feitos if f["template_id"].startswith("RC_TERMO")
              and f["parte"] == PARTE_CORPO]
    assert len(termos) == 4
    for f in termos:
        vig = ED.conteudo_vigente(con, f["template_id"], PARTE_CORPO)
        pub = ED.carregar(con, area=AREA_RCPN, template_id=f["template_id"],
                          parte=PARTE_CORPO, qual="publicada")
        assert pub["conteudo"] == vig["conteudo"]
        assert pub["sha256"] == vig["sha256"]
        assert hashlib.sha256(
            (pub["conteudo"] or "").encode("utf-8")).hexdigest() == pub["sha256"]


def test_semente_byte_a_byte_moldes(con):
    # Requer ODTs do pacote em modelos/
    for chave in ED.MOLDES_RCPN:
        feitos = ED.semear_v1(con, template_id=chave, agora=AGORA)
        assert feitos and feitos[0]["acao"] in ("semeada", "ja_existia")
        vig = ED.conteudo_vigente(con, chave, PARTE_MOLDE)
        pub = ED.carregar(con, area=AREA_RCPN, template_id=chave,
                          parte=PARTE_MOLDE, qual="publicada")
        assert pub["conteudo_blob"] == vig["conteudo_blob"]
        assert pub["sha256"] == vig["sha256"]


def test_chave_desligada_nao_muda_nada(con):
    ED.semear_v1(con, template_id="RC_TERMO_NASCIMENTO", agora=AGORA)
    # chave desligada por padrão
    assert ED.chave_ligada(con, AREA_RCPN) is False
    assert ED.conteudo_publicado_se_ligado(
        con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO") is None
    # vigência continua igual
    assert (ED.conteudo_vigente(con, "RC_TERMO_NASCIMENTO")["conteudo"]
            == CASA.padrao_de("RC_TERMO_NASCIMENTO"))


def test_chave_ligada_devolve_publicada(con):
    ED.semear_v1(con, template_id="RC_TERMO_NASCIMENTO", agora=AGORA)
    ED.definir_chave(con, AREA_RCPN, True)
    con.commit()
    assert ED.chave_ligada(con, AREA_RCPN) is True
    pub = ED.conteudo_publicado_se_ligado(
        con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO")
    assert pub is not None
    assert pub["status"] == STATUS_PUBLICADA
    assert pub["conteudo"] == CASA.padrao_de("RC_TERMO_NASCIMENTO")


def test_validacao_placeholder_desconhecido(con):
    texto = CASA.padrao_de("RC_TERMO_NASCIMENTO") + "\n{{campo_que_nao_existe_xyz}}"
    val = ED.validar(
        con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
        parte=PARTE_CORPO, conteudo=texto, get_settings=_settings_gen)
    assert val["ok"] is False
    assert any(e["codigo"] == "placeholder_desconhecido" for e in val["erros"])


def test_validacao_bloqueado_adulterado(con):
    texto = "{{#bloqueado art1}}texto errado{{/bloqueado}}"
    val = ED.validar(
        con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
        parte=PARTE_CORPO, conteudo=texto, get_settings=_settings_gen,
        trechos_bloqueados=[{"id": "art1", "texto": "texto certo",
                             "base_legal": "art. 1"}])
    assert val["ok"] is False
    assert any(e["codigo"] == "bloqueado_adulterado" for e in val["erros"])


def test_validacao_literal_serventia(con):
    settings = _settings_gen()
    # Monta o literal A PARTIR da fixture (única exceção permitida)
    literal = settings["ri_cns"]
    texto = CASA.padrao_de("RC_TERMO_NASCIMENTO") + f"\nCNS {literal}"
    val = ED.validar(
        con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
        parte=PARTE_CORPO, conteudo=texto, get_settings=lambda: settings)
    assert val["ok"] is False
    assert any(e["codigo"] == "literal_serventia" for e in val["erros"])


def test_publicar_recusado_com_erro(con):
    ED.salvar_rascunho(
        con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
        parte=PARTE_CORPO,
        conteudo=CASA.padrao_de("RC_TERMO_NASCIMENTO") + "\n{{zzz_desconhecido}}",
        autor="a", agora=AGORA)
    with pytest.raises(ED.EditorError, match="recusada|desconhecido"):
        ED.publicar(
            con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
            parte=PARTE_CORPO, autor="a", agora=AGORA,
            papel_usuario="ADMIN", get_settings=_settings_gen)
