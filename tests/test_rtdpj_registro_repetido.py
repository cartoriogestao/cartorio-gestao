"""O REGISTRO DO RTD/PJ QUE VEIO DUAS VEZES DO ACERVO (T021, 26/11/2026).

O E-Ofício gravou a mesma linha duas vezes, com a folha escrita de dois jeitos
(«12» numa e «012» na outra, nestes testes), e a carga trouxe as duas fichas.
Nenhuma tela tirava a cópia: a correção do acervo não muda a situação, e o
cancelamento lavra ato novo, com selo e custas.

O QUE ESTES TESTES GUARDAM
    - a fila de correções de ofício tira a cópia: o oficial aprova com a
      afirmação expressa, o servidor executa, e a cópia fica CANCELADO por
      duplicidade do acervo — sem ato novo, sem selo e sem custas, com o antes
      e o depois na auditoria, e nada apagado;
    - a pré-condição: a mesma série, volume, número, folha e data, e a cópia
      solta (sem selo, anexo, certidão, protocolo, título nem parte além do
      requerente);
    - o tipo inverso devolve a ficha a ATIVO, e não alcança o registro
      cancelado por ato;
    - a cópia cancelada sai das listas ativas, dos livros, dos índices e da
      busca da certidão, e o alerta do gestor só conta o ATIVO, por volume;
    - a carga do acervo avisa e não grava a segunda linha como ativa.

DADOS INVENTADOS: série TD_B, volume 3, número 4321, folha 12, ato de
15/03/2019, requerente «APRESENTANTE EXEMPLO». Nada do registro real.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import correcoes_de_oficio as CDO  # noqa: E402
import gestor_rtdpj as GRT  # noqa: E402
import rg_livros as RGL  # noqa: E402
import rg_registro as RG  # noqa: E402
from bd_nativo import banco  # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-11-26T15:00:00"
HOJE = date(2026, 11, 26)
MOTIVO = ("A mesma linha do sistema antigo veio duas vezes na carga do acervo; o "
          "livro tem o registro uma vez só.")
AFIRMACAO = ("Afirmo, sob minha responsabilidade, que conferi o livro e que a ficha "
             "repetida deve sair como proposto.")
URL = "/administrativo/correcoes-de-oficio"
TIPO = "RG_REGISTRO_REPETIDO"
INVERSO = "RG_REGISTRO_REPETIDO_DESFEITO"


# ------------------------------------------------------------- a casa


def _pessoas(db) -> dict:
    ids = {
        "mario": db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN"),
        "carla": db.create_user("carla", "CARLA EXEMPLO", SENHA, "USER"),
    }
    return {nome: db.get_user(uid) for nome, uid in ids.items()}


def _ficha(db, chave: str, *, numero: int = 4321, volume: str = "3", folha: int = 12,
           data: str = "2019-03-15", serie: str = "TD_B", situacao: str = "ATIVO",
           requerente: str = "APRESENTANTE EXEMPLO", selo: str | None = None) -> int:
    """Uma ficha do acervo com o ato de registro, como a carga a grava."""
    with db.transaction() as con:
        bd = banco(con)
        rid = int(bd.escrever(
            """INSERT INTO rg_registros (atribuicao, serie, numero, volume,
                   requerente_nome, situacao, origem, origem_chave, criado_em)
               VALUES (4, %s, %s, %s, %s, %s, 'EOFICIO', %s, %s) RETURNING id""",
            (serie, numero, volume, requerente, situacao, f"teste:{chave}",
             AGORA))[0]["id"])
        bd.escrever(
            """INSERT INTO rg_atos (registro_id, tipo, folha, numero_ordem, data_ato,
                   selo, origem, origem_chave, criado_em)
               VALUES (%s, 'REGISTRO', %s, %s, %s, %s, 'EOFICIO', %s, %s)""",
            (rid, folha, numero, data, selo, f"teste:{chave}:REGISTRO", AGORA))
    return rid


def _par(db) -> tuple[int, int]:
    """As duas fichas iguais: a que fica e a cópia."""
    return _ficha(db, "1"), _ficha(db, "2")


def _um(db, sql: str, args=()) -> dict | None:
    with db.connect() as con:
        return banco(con).um(sql, args)


def _ler(db, sql: str, args=()) -> list[dict]:
    with db.connect() as con:
        return banco(con).ler(sql, args)


def _foto(db) -> str:
    """O RTD/PJ inteiro, para provar o que mudou e o que não mudou."""
    return json.dumps([_ler(db, f"SELECT * FROM {t} ORDER BY id")
                       for t in ("rg_registros", "rg_atos", "rg_partes", "rg_titulos")],
                      default=str, sort_keys=True)


def _propor(db, quem: dict, tipo: str, parametros: dict) -> dict:
    with db.transaction() as con:
        return CDO.propor(con, tipo=tipo, parametros=parametros, motivo=MOTIVO,
                          quem=quem, agora=AGORA)


def _aprovar(db, quem: dict, correcao_id: int) -> dict:
    with db.transaction() as con:
        return CDO.aprovar(con, correcao_id, aprovador=quem, afirmo=True,
                           afirmacao=AFIRMACAO, agora=AGORA)


def _tirar(db, p: dict, fica: int, sai: int) -> dict:
    feita = _propor(db, p["carla"], TIPO, {"registro_que_fica": fica,
                                            "registro_que_sai": sai})
    assert feita["ok"], feita["recusas"]
    r = _aprovar(db, p["mario"], feita["id"])
    assert r["ok"], r
    return feita


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe o csrf_token"
    return achado.group(1)


# --------------------------------------------------- a correção pela fila


def test_a_copia_sai_sem_ato_selo_nem_custas_e_com_a_auditoria(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    fica, sai = _par(db)
    antes = _foto(db)
    feita = _propor(db, p["carla"], TIPO, {"registro_que_fica": fica,
                                            "registro_que_sai": sai})
    assert feita["ok"], feita["recusas"]
    assert _foto(db) == antes, "propor mexeu no RTD/PJ"
    linha = _um(db, "SELECT * FROM correcoes_de_oficio WHERE id = %s", (feita["id"],))
    assert (linha["atribuicao"], linha["tipo"], linha["alvo_tabela"]) == (
        CDO.ATRIBUICAO_RTDPJ, TIPO, "rg_registros")
    assert json.loads(linha["alvo_ids"]) == [sai]
    assert any("não lança custas" in a for a in feita["avisos"])

    atos_antes = _um(db, "SELECT count(*) AS n FROM rg_atos")["n"]
    r = _aprovar(db, p["mario"], feita["id"])
    assert r["ok"] and r["situacao"] == CDO.APROVADA_EXECUTADA, r
    copia = _um(db, "SELECT * FROM rg_registros WHERE id = %s", (sai,))
    assert copia["situacao"] == "CANCELADO" and int(copia["duplicata_de"]) == fica
    assert "DUPLICIDADE DO ACERVO" in copia["duplicata_motivo"]
    assert f"nº {feita['id']}" in copia["duplicata_motivo"]
    assert _um(db, "SELECT situacao FROM rg_registros WHERE id = %s",
               (fica,))["situacao"] == "ATIVO"
    # sem ato novo, sem selo, sem custas — e nada apagado
    assert _um(db, "SELECT count(*) AS n FROM rg_atos")["n"] == atos_antes
    assert _um(db, "SELECT count(*) AS n FROM rg_registros")["n"] == 2
    assert all(a["selo"] is None for a in _ler(db, "SELECT selo FROM rg_atos"))
    assert _ler(db, "SELECT * FROM rg_atos WHERE tipo = 'CANCELAMENTO'") == []
    # o antes e o depois na auditoria, e a afirmação do oficial
    [auditada] = _ler(db, "SELECT * FROM audit_logs WHERE action = %s",
                      (CDO.ACAO_EXECUTADA,))
    assert (auditada["entity_type"], int(auditada["entity_id"])) == ("rg_registros", sai)
    detalhe = json.loads(auditada["details"])
    assert detalhe["antes"] == {"situacao": "ATIVO", "duplicata_de": None,
                                "duplicata_motivo": None}
    assert detalhe["depois"]["situacao"] == "CANCELADO"
    assert detalhe["depois"]["duplicata_de"] == fica
    assert len(_ler(db, "SELECT * FROM audit_logs WHERE action = %s",
                    (CDO.ACAO_DA_AFIRMACAO,))) == 1


def test_a_copia_cancelada_sai_das_listas_dos_livros_e_dos_indices(cg_casa):
    import atrib_certidao as AC
    db = cg_casa["db"]
    p = _pessoas(db)
    fica, sai = _par(db)
    with db.connect() as con:
        assert len(GRT.regra_registro_repetido(con, HOJE)) == 1
        assert len(RGL.atos_do_livro(con, "TD_B")["linhas"]) == 2
    _tirar(db, p, fica, sai)
    with db.connect() as con:
        # o alerta do gestor apaga
        assert GRT.regra_registro_repetido(con, HOJE) == []
        # o Livro B tem o número uma vez, e a contagem da aba também
        livro = RGL.atos_do_livro(con, "TD_B")
        assert [x["registro_id"] for x in livro["linhas"]] == [fica]
        assert livro["total"] == 1
        assert [x["registro_id"] for x in RGL.atos_do_livro(con, "TD_B", busca="4321")
                ["linhas"]] == [fica]
        assert RGL.quantos_no_livro(con, {"tipo": RGL.ATOS, "serie": "TD_B"}, 4) == 1
        # o indicador pessoal tem a pessoa uma vez
        pessoas = RGL.indicador_pessoal(con, atribuicao=4, busca="APRESENTANTE EXEMPLO")
        assert [x["registro_id"] for x in pessoas] == [fica]
        # a busca da certidão acha o registro uma vez
        achados = AC.consta_em_nome_de(con, atribuicao=4, nome="APRESENTANTE EXEMPLO")
        assert [int(x["id"]) for x in achados] == [fica]
    # a lista das ativas não a mostra; a de todas a guarda, CANCELADO
    from conftest import cg_login
    c = cg_casa["app"].test_client()
    cg_login(c, "mario", SENHA)
    ativas = c.get("/rcpj-rtd?situacao=ATIVO").get_data(as_text=True)
    assert f"/rcpj-rtd/{fica}" in ativas and f"/rcpj-rtd/{sai}\"" not in ativas
    ficha = c.get(f"/rcpj-rtd/{sai}").get_data(as_text=True)
    assert "Cancelado por duplicidade do acervo" in ficha
    assert f"/rcpj-rtd/{fica}" in ficha


def test_a_ficha_da_proposta_aponta_a_ficha_do_registro(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    fica, sai = _par(db)
    from conftest import cg_login
    carla = cg_casa["app"].test_client()
    cg_login(carla, "carla", SENHA)
    tela = carla.get(f"{URL}/nova?tipo={TIPO}").get_data(as_text=True)
    assert "registro_que_fica" in tela and "registro_que_sai" in tela
    r = carla.post(f"{URL}/propor", data={
        "csrf_token": _token(tela), "tipo": TIPO, "registro_que_fica": str(fica),
        "registro_que_sai": str(sai), "motivo": MOTIVO, "acao": "propor"})
    assert r.status_code == 302, r.get_data(as_text=True)[:500]
    correcao_id = int(r.headers["Location"].rstrip("/").rsplit("/", 1)[1])
    mario = cg_casa["app"].test_client()
    cg_login(mario, "mario", SENHA)
    ficha = mario.get(f"{URL}/{correcao_id}").get_data(as_text=True)
    assert "RTD/PJ" in ficha and f"/rcpj-rtd/{sai}" in ficha
    assert "Aprovar e executar" in ficha
    assert mario.get(f"{URL}?atribuicao=RTDPJ").status_code == 200
    r = mario.post(f"{URL}/{correcao_id}/aprovar",
                   data={"csrf_token": _token(ficha), "afirmo": "1", "afirmacao": AFIRMACAO})
    assert r.status_code == 302
    assert _um(db, "SELECT situacao FROM rg_registros WHERE id = %s",
               (sai,))["situacao"] == "CANCELADO"
    assert p["mario"]["role"] == "ADMIN"


# ------------------------------------------------------- a pré-condição


@pytest.mark.parametrize("campo, valor, frase", [
    ("folha", 13, "folha"),
    ("data", "2019-03-16", "data do ato de registro"),
    ("volume", "4", "volume"),
    ("numero", 4322, "número"),
])
def test_so_a_mesma_linha_do_livro(cg_casa, campo, valor, frase):
    db = cg_casa["db"]
    p = _pessoas(db)
    fica = _ficha(db, "1")
    outra = _ficha(db, "2", **{campo: valor})
    r = _propor(db, p["carla"], TIPO, {"registro_que_fica": fica, "registro_que_sai": outra})
    assert not r["ok"]
    assert any("não são a mesma linha" in x and frase in x for x in r["recusas"]), r["recusas"]


def test_o_volume_e_a_folha_escritos_com_zero_sao_os_mesmos(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    fica = _ficha(db, "1", volume="3")
    sai = _ficha(db, "2", volume="03")
    r = _propor(db, p["carla"], TIPO, {"registro_que_fica": fica, "registro_que_sai": sai})
    assert r["ok"], r["recusas"]


def _vincular(db, sai: int, como: str) -> None:
    with db.transaction() as con:
        bd = banco(con)
        ato = int(bd.valor("SELECT id FROM rg_atos WHERE registro_id = %s", (sai,)))
        if como == "selo":
            bd.escrever("UPDATE rg_atos SET selo = %s WHERE id = %s",
                        ("SELO-EXEMPLO-0001", ato))
        elif como == "protocolo":
            bd.escrever("UPDATE rg_atos SET protocolo_id = 1 WHERE id = %s", (ato,))
        elif como == "anexo":
            bd.escrever(
                """INSERT INTO attachments (entity_type, entity_id, original_name,
                       stored_name, stored_path, sha256, size_bytes, uploaded_at)
                   VALUES ('RG_ATO', %s, 'copia.pdf', 'x.pdf', '/nao/existe/x.pdf',
                           'ab', 1, %s)""", (ato, AGORA))
        elif como == "certidao":
            bd.escrever(
                """INSERT INTO at_certidoes (atribuicao, numero, ano, tabela,
                       registro_id, teor, emitida_em)
                   VALUES ('RCPJ_RTD', 1, 2026, 'rg_registros', %s, 'teor', %s)""",
                (sai, AGORA))
        elif como == "titulo":
            bd.escrever(
                """INSERT INTO rg_titulos (atribuicao, numero, data_apresentacao,
                       situacao, registro_id, origem, criado_em)
                   VALUES (4, 1, '2019-03-15', 'REGISTRADO', %s, 'MANUAL', %s)""",
                (sai, AGORA))
        elif como == "parte":
            bd.escrever(
                """INSERT INTO rg_partes (registro_id, nome, nome_norm, origem, criado_em)
                   VALUES (%s, 'OUTRA PESSOA EXEMPLO', 'outra pessoa exemplo',
                           'MANUAL', %s)""", (sai, AGORA))
        elif como == "averbacao":
            bd.escrever(
                """INSERT INTO rg_atos (registro_id, tipo, data_ato, origem, criado_em)
                   VALUES (%s, 'AVERBACAO', '2020-01-10', 'MANUAL', %s)""", (sai, AGORA))


@pytest.mark.parametrize("como, frase", [
    ("selo", "selo"), ("protocolo", "protocolo"), ("anexo", "anexo"),
    ("certidao", "certidão"), ("titulo", "título do Livro de Protocolo"),
    ("parte", "além do requerente"), ("averbacao", "mais que o ato de registro"),
])
def test_a_copia_amarrada_a_qualquer_coisa_e_recusada(cg_casa, como, frase):
    db = cg_casa["db"]
    p = _pessoas(db)
    fica, sai = _par(db)
    _vincular(db, sai, como)
    antes = _foto(db)
    r = _propor(db, p["carla"], TIPO, {"registro_que_fica": fica, "registro_que_sai": sai})
    assert not r["ok"]
    assert any(frase in x for x in r["recusas"]), r["recusas"]
    assert _foto(db) == antes
    assert _um(db, "SELECT count(*) AS n FROM correcoes_de_oficio")["n"] == 0


def test_a_parte_que_e_o_proprio_requerente_nao_impede(cg_casa):
    from pt_schema import normalizar_nome
    db = cg_casa["db"]
    p = _pessoas(db)
    fica, sai = _par(db)
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO rg_partes (registro_id, nome, nome_norm, origem, criado_em)
               VALUES (%s, 'APRESENTANTE EXEMPLO', %s, 'MANUAL', %s)""",
            (sai, normalizar_nome("APRESENTANTE EXEMPLO"), AGORA))
    r = _propor(db, p["carla"], TIPO, {"registro_que_fica": fica, "registro_que_sai": sai})
    assert r["ok"], r["recusas"]


def test_o_pedido_mal_feito_e_a_ficha_nao_ativa(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    fica, sai = _par(db)
    r = _propor(db, p["carla"], TIPO, {"registro_que_fica": fica, "registro_que_sai": fica})
    assert any("são a mesma" in x for x in r["recusas"])
    r = _propor(db, p["carla"], TIPO, {"registro_que_fica": fica, "registro_que_sai": 99999})
    assert any("não existe" in x for x in r["recusas"])
    cancelada = _ficha(db, "3", situacao="CANCELADO")
    r = _propor(db, p["carla"], TIPO, {"registro_que_fica": fica,
                                        "registro_que_sai": cancelada})
    assert any("está CANCELADO" in x for x in r["recusas"])
    # a que sai é a mais antiga: entra, com o aviso
    r = _propor(db, p["carla"], TIPO, {"registro_que_fica": sai, "registro_que_sai": fica})
    assert r["ok"] and any("mais antiga" in a for a in r["avisos"])


def test_o_antes_alterado_antes_da_aprovacao_da_falhou(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    fica, sai = _par(db)
    feita = _propor(db, p["carla"], TIPO, {"registro_que_fica": fica,
                                            "registro_que_sai": sai})
    assert feita["ok"]
    _vincular(db, sai, "selo")
    r = _aprovar(db, p["mario"], feita["id"])
    assert not r["ok"] and r["situacao"] == CDO.FALHOU
    assert "mudou" in r["falha"]
    assert _um(db, "SELECT situacao FROM rg_registros WHERE id = %s",
               (sai,))["situacao"] == "ATIVO"


# ------------------------------------------------------- o caminho de volta


def test_o_inverso_devolve_a_ficha_a_ativo(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    fica, sai = _par(db)
    _tirar(db, p, fica, sai)
    volta = _propor(db, p["carla"], INVERSO, {"registro_id": sai})
    assert volta["ok"], volta["recusas"]
    assert _aprovar(db, p["mario"], volta["id"])["ok"]
    r = _um(db, "SELECT * FROM rg_registros WHERE id = %s", (sai,))
    assert (r["situacao"], r["duplicata_de"], r["duplicata_motivo"]) == ("ATIVO", None, None)
    auditadas = _ler(db, "SELECT * FROM audit_logs WHERE action = %s ORDER BY id",
                     (CDO.ACAO_EXECUTADA,))
    assert len(auditadas) == 2
    detalhe = json.loads(auditadas[-1]["details"])
    assert detalhe["antes"]["duplicata_de"] == fica and detalhe["depois"]["situacao"] == "ATIVO"
    with db.connect() as con:
        assert len(GRT.regra_registro_repetido(con, HOJE)) == 1


def test_o_inverso_nao_alcanca_o_registro_cancelado_por_ato(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    cancelado = _ficha(db, "1", situacao="CANCELADO")
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO rg_atos (registro_id, tipo, data_ato, motivo_cancelamento,
                   origem, criado_em)
               VALUES (%s, 'CANCELAMENTO', '2020-05-01', 'cancelado a pedido', 'MANUAL', %s)""",
            (cancelado, AGORA))
    r = _propor(db, p["carla"], INVERSO, {"registro_id": cancelado})
    assert not r["ok"] and any("não foi cancelada por duplicidade" in x for x in r["recusas"])
    ativo = _ficha(db, "2")
    r = _propor(db, p["carla"], INVERSO, {"registro_id": ativo})
    assert not r["ok"]


# ------------------------------------------------------------ o alerta


def test_o_alerta_conta_so_o_ativo_e_separa_o_volume(cg_casa):
    db = cg_casa["db"]
    _ficha(db, "1", volume="3")
    _ficha(db, "2", volume="4")                   # outro volume: outro lugar
    with db.connect() as con:
        assert GRT.regra_registro_repetido(con, HOJE) == []
    _ficha(db, "3", volume="3", situacao="CANCELADO")   # cancelado não repete
    with db.connect() as con:
        assert GRT.regra_registro_repetido(con, HOJE) == []
    _ficha(db, "4", volume="3")
    with db.connect() as con:
        [achado] = GRT.regra_registro_repetido(con, HOJE)
    # a chave é a de sempre: o número só se repete num volume
    assert achado["chave"] == "RTDPJ_REPETIDO:TD_B:4321"
    assert "vol. 3" in achado["titulo"] and "2 vezes" in achado["titulo"]
    assert "Correções de ofício" in achado["detalhe"]
    _ficha(db, "5", volume="4")
    with db.connect() as con:
        chaves = sorted(a["chave"] for a in GRT.regra_registro_repetido(con, HOJE))
    assert chaves == ["RTDPJ_REPETIDO:TD_B:4321:3", "RTDPJ_REPETIDO:TD_B:4321:4"]


# ------------------------------------------------------- a carga do acervo


def _acervo_com_a_linha_repetida(folha_da_segunda: str = "012",
                                 data_da_segunda: str = "2019-03-15 00:00:00"
                                 ) -> sqlite3.Connection:
    from test_acervo_carga import acervo_falso
    acervo = acervo_falso()
    acervo.execute("DELETE FROM tbRegistroTD")
    for chave, folha, data in ((11, "12", "2019-03-15 00:00:00"),
                               (12, folha_da_segunda, data_da_segunda)):
        acervo.execute(
            """INSERT INTO tbRegistroTD(intChave, strTipoRegistro, intNumeroRegistro,
                   strLivro, strApresentante, dtmData, strFolha_DE, intProtocolo)
               VALUES (?, 'TD', 4321, '3', 'Apresentante', ?, ?, 77)""",
            (chave, data, folha))
    acervo.commit()
    return acervo


def test_a_carga_avisa_e_nao_grava_a_segunda_como_ativa():
    import acervo_carga as ACG
    from test_acervo_carga import banco as banco_da_carga
    con, acervo = banco_da_carga(), _acervo_com_a_linha_repetida()
    carga = ACG.carregar_rcpj_rtd(con, acervo, agora=AGORA)
    assert carga.inseridos == 2
    linhas = [dict(r) for r in con.execute(
        "SELECT id, situacao, duplicata_de, duplicata_motivo, origem_chave "
        "FROM rg_registros ORDER BY id")]
    primeira, segunda = linhas
    assert primeira["situacao"] == "ATIVO" and primeira["duplicata_de"] is None
    assert segunda["situacao"] == "CANCELADO"
    assert segunda["duplicata_de"] == primeira["id"]
    assert "DUPLICIDADE DO ACERVO" in segunda["duplicata_motivo"]
    assert [a["chave"] for a in carga.avisos] == [12]
    assert "CANCELADO por duplicidade" in carga.avisos[0]["motivo"]
    # o ato de registro da cópia fica guardado, e o livro mostra uma linha só
    assert con.execute("SELECT count(*) FROM rg_atos").fetchone()[0] == 2
    assert [x["registro_id"] for x in RGL.atos_do_livro(con, "TD_B")["linhas"]] == [
        primeira["id"]]
    assert GRT.regra_registro_repetido(con, HOJE) == []
    # rodar de novo não duplica nem avisa outra vez
    de_novo = ACG.carregar_rcpj_rtd(con, acervo, agora=AGORA)
    assert (de_novo.inseridos, de_novo.repetidos, de_novo.avisos) == (0, 2, [])
    # o protocolo antigo fica só na primeira
    livros = ACG.carregar_rcpj_rtd_livros(con, acervo, agora=AGORA)
    assert [r["registro_id"] for r in con.execute(
        "SELECT registro_id FROM rg_titulos ORDER BY id")] == [primeira["id"]]
    assert any("repetido no acervo" in k for k in livros.contagens)


def test_a_carga_grava_as_duas_quando_a_linha_e_outra():
    import acervo_carga as ACG
    from test_acervo_carga import banco as banco_da_carga
    con = banco_da_carga()
    acervo = _acervo_com_a_linha_repetida(data_da_segunda="2019-03-16 00:00:00")
    carga = ACG.carregar_rcpj_rtd(con, acervo, agora=AGORA)
    assert carga.inseridos == 2 and carga.avisos == []
    assert [r[0] for r in con.execute("SELECT situacao FROM rg_registros")] == [
        "ATIVO", "ATIVO"]
