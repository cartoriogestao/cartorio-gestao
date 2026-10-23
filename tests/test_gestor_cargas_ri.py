"""O agente de cargas do RI ao ONR — imagens, Indicador Pessoal e Indicador Real.

O QUE ESTES TESTES GUARDAM
    **Que a matrícula volta à fila quando o livro muda.** Até 09/10/2026, depois
    de ENVIADO o indicador real nunca mais era olhado, por mais atos que a ficha
    recebesse: o corpo de hoje se compara com o `corpo_hash` do que subiu, e o
    que divergiu vai pelo PATCH, sem queimar o identificador.

    **Que recusado sem conserto não se reenvia.** Mandar de novo o mesmo corpo
    daria a mesma recusa, todo dia, para sempre.

    **Que sem credencial, ou com o interruptor desligado, nada sai** — e a
    conferência diz por quê, ao oficial, sem virar tarefa de ninguém.

    **Que o arquivo do Indicador Pessoal é achado depois pelo sha** em
    `Processados` (o precedente do E-Ofício), e só então o incremental começa.

    **Que a imagem vai para a pasta do CSL2 no formato do ONR e a marca
    `digi_onr_pendente` baixa** — ela nunca baixava.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import gestor_cargas_ri as G                                       # noqa: E402
import gestor_conferencia as GC                                    # noqa: E402
import gestor_rotina as GR                                         # noqa: E402
import onr_api as API                                              # noqa: E402

AGORA = "2026-10-09T08:00:00"
HOJE = date(2026, 10, 9)


@pytest.fixture()
def casa(cg_casa, tmp_path):
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    for chave, valor in (("ri_cns", "000000"),
                         ("onr_csl2_pasta", str(tmp_path / "IMAGENS_DIGITALIZACOES")),
                         ("onr_ips_pasta", str(tmp_path / "INDICADORES")),
                         ("onr_carga_inicial_pasta", str(tmp_path / "CARGA_INICIAL"))):
        con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)", (chave, valor))
    con.commit()
    yield {"con": con, "banco": Path(cg_casa["banco"]), "tmp": tmp_path}
    con.close()


@pytest.fixture()
def com_credencial(monkeypatch):
    monkeypatch.setattr(API, "tem_credencial", lambda *a, **k: True)
    monkeypatch.setattr(API, "fila", lambda **k: [])
    enviados, atualizados = [], []

    def enviar(corpo, **k):
        enviados.append(corpo)
        return {"hash": f"H{len(enviados)}", "corpo": corpo, "bruto": {"ok": 1}}

    def atualizar(ident, corpo, **k):
        atualizados.append((ident, corpo))
        return {"ok": 1}

    monkeypatch.setattr(API, "enviar_indicador", enviar)
    monkeypatch.setattr(API, "atualizar_indicador", atualizar)
    return {"enviados": enviados, "atualizados": atualizados}


@pytest.fixture()
def sem_credencial(monkeypatch):
    monkeypatch.setattr(API, "tem_credencial", lambda *a, **k: False)


def _matricula(con, **campos) -> int:
    base = {"numero": "4030", "livro": "2", "livro_norm": "2",
            "tipo_ficha": "ESTRUTURADA", "tipo_imovel": "Casa",
            "rural_urbano": "Urbano", "logradouro": "Rua das Flores",
            "numero_predial": "100", "bairro": "Centro",
            "cidade": "Cidade Exemplo", "uf": "MA", "cep": "65926-000",
            "area_valor": "360", "criado_em": AGORA}
    base.update(campos)
    cur = con.execute(f"INSERT INTO ri_matriculas({', '.join(base)}) "
                      f"VALUES({', '.join('?' * len(base))})", tuple(base.values()))
    con.commit()
    return int(cur.lastrowid)


def _ato(con, mid, *, numero=1, natureza="Compra e Venda", lavrado_em=AGORA) -> int:
    cur = con.execute(
        "INSERT INTO ri_atos(matricula_id, tipo, numero, natureza_titulo, data_ato, "
        "teor, hash_ato, lavrado_em) VALUES(?,?,?,?,?,?,?,?)",
        (mid, "R", numero, natureza, lavrado_em[:10], "Vendeu.",
         f"hash-{mid}-{numero}", lavrado_em))
    con.commit()
    return int(cur.lastrowid)


def _parte(con, mid, nome, *, ato_id=None, documento="22105769039", ativo=1):
    con.execute("INSERT INTO ri_partes(matricula_id, ato_id, nome, documento_numero, "
                "proprietario, proprietario_ativo) VALUES(?,?,?,?,?,?)",
                (mid, ato_id, nome, documento, 1, ativo))
    con.commit()


# ---------------------------------------------------------- o indicador real

def test_matricula_completa_e_nova_vai_para_a_fila(casa):
    mid = _matricula(casa["con"])
    _parte(casa["con"], mid, "FULANO DE TAL")
    pend = G.indicadores_pendentes(casa["con"])
    assert [n["matricula_id"] for n in pend["novos"]] == [mid]
    assert pend["incompletos"] == []


def test_ficha_incompleta_diz_o_que_falta(casa):
    mid = _matricula(casa["con"], cep="", tipo_imovel="")
    pend = G.indicadores_pendentes(casa["con"])
    assert pend["novos"] == []
    (i,) = pend["incompletos"]
    assert i["matricula_id"] == mid
    assert any("CEP" in m for m in i["impedem"])


def test_acervo_nao_entra_na_fila_e_vira_decisao(casa, sem_credencial):
    _matricula(casa["con"], tipo_ficha="ACERVO", numero="100")
    assert G.indicadores_pendentes(casa["con"])["novos"] == []
    achados = G.conferir(casa["con"], HOJE)
    (a,) = [x for x in achados if x["regra"] == "ONR_ACERVO_DECISAO"]
    assert a["setor"] == "GESTAO"
    assert "3 matrículas" in a["detalhe"]


def test_sem_credencial_nada_sai_e_o_oficial_e_avisado(casa, sem_credencial, monkeypatch):
    monkeypatch.setattr(API, "enviar_indicador",
                        lambda *a, **k: pytest.fail("mandou sem credencial"))
    _matricula(casa["con"])
    r = G.cuidar_do_real(casa["con"], casa["banco"])
    assert "sem credencial" in r["parado"]
    achados = G.conferir(casa["con"], HOJE)
    (a,) = [x for x in achados if x["regra"] == "ONR_CREDENCIAL"]
    assert a["setor"] == "GESTAO" and "1 matrícula" in a["detalhe"]
    assert "ONR_CREDENCIAL" in GR.REGRAS_SEM_TAREFA


def test_interruptor_desligado_segura_o_envio(casa, com_credencial):
    casa["con"].execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                        (G.CHAVE_ENVIO, "DESLIGADO"))
    casa["con"].commit()
    _matricula(casa["con"])
    r = G.cuidar_do_real(casa["con"], casa["banco"])
    assert r["parado"] and com_credencial["enviados"] == []
    assert any(x["regra"] == "ONR_ENVIO_DESLIGADO" for x in G.conferir(casa["con"], HOJE))


def test_manda_o_novo_e_grava_o_que_mandou(casa, com_credencial):
    mid = _matricula(casa["con"])
    _parte(casa["con"], mid, "FULANO DE TAL")
    r = G.cuidar_do_real(casa["con"], casa["banco"])
    assert r["enviados"] == 1 and len(com_credencial["enviados"]) == 1
    envio = casa["con"].execute(
        "SELECT * FROM ri_onr_envios WHERE matricula_id=?", (mid,)).fetchone()
    assert envio["identificador"] == "H1" and envio["enviado_por"] == G.QUEM
    # na rodada seguinte, nada a fazer
    r2 = G.cuidar_do_real(casa["con"], casa["banco"])
    assert r2["enviados"] == 0 and r2["atualizados"] == 0


def test_ato_novo_faz_o_indicador_voltar_pelo_patch(casa, com_credencial):
    """O defeito que este agente fecha: depois de ENVIADO, a matrícula nunca
    voltava à lista. O ato novo muda o corpo, e o corpo novo vai pelo PATCH.

    O que muda o corpo é o DONO NOVO: desde 10/10/2026 o ato sem data do título
    e valor declarado não vai ao ONR (o manual exige os dois), e sozinho não
    mudaria nada."""
    mid = _matricula(casa["con"])
    _parte(casa["con"], mid, "FULANO DE TAL")
    G.cuidar_do_real(casa["con"], casa["banco"])
    ato = _ato(casa["con"], mid, numero=2, natureza="Compra e Venda")
    _parte(casa["con"], mid, "BELTRANO DE TAL", ato_id=ato, documento="52998224725")
    pend = G.indicadores_pendentes(casa["con"])
    assert [m["matricula_id"] for m in pend["mudaram"]] == [mid]
    r = G.cuidar_do_real(casa["con"], casa["banco"])
    assert r["atualizados"] == 1 and r["enviados"] == 0
    ident, _ = com_credencial["atualizados"][0]
    assert ident == "H1"                         # o identificador não se queima
    assert G.indicadores_pendentes(casa["con"])["mudaram"] == []


def test_recusado_sem_conserto_nao_se_reenvia(casa, com_credencial):
    mid = _matricula(casa["con"])
    G.cuidar_do_real(casa["con"], casa["banco"])
    casa["con"].execute("UPDATE ri_onr_envios SET situacao='RECUSADO', "
                        "fila_situacao='Erro de validação'")
    casa["con"].commit()
    r = G.cuidar_do_real(casa["con"], casa["banco"])
    assert r["enviados"] == 0
    (a,) = [x for x in G.conferir(casa["con"], HOJE)
            if x["regra"] == "ONR_INDICADOR_RECUSADO"]
    assert a["gravidade"] == "CRITICO" and a["setor"] == "RI"
    # corrigida a ficha, o corpo muda e ele volta a subir
    casa["con"].execute("UPDATE ri_matriculas SET numero_predial='200' WHERE id=?", (mid,))
    casa["con"].commit()
    assert G.cuidar_do_real(casa["con"], casa["banco"])["enviados"] == 1


def test_enviado_ha_dias_sem_resposta_da_fila(casa, com_credencial):
    mid = _matricula(casa["con"])
    G.cuidar_do_real(casa["con"], casa["banco"])
    velho = (date.today() - timedelta(days=G.FILA_DIAS_TOLERADOS + 2)).isoformat()
    casa["con"].execute("UPDATE ri_onr_envios SET enviado_em=? WHERE matricula_id=?",
                        (velho + "T08:00:00", mid))
    casa["con"].commit()
    assert any(x["regra"] == "ONR_FILA_PARADA" for x in G.conferir(casa["con"], HOJE))


# ---------------------------------------------------- o indicador pessoal

def test_carga_inicial_fica_pronta_e_so_se_regrava_quando_muda(casa):
    mid = _matricula(casa["con"])
    _parte(casa["con"], mid, "FULANO DE TAL")
    r1 = G.cuidar_do_pessoal(casa["con"], HOJE)
    assert r1["acao"] == "carga completa regravada"
    arq = Path(r1["arquivo"])
    assert arq.exists() and arq.parent == casa["tmp"] / "CARGA_INICIAL"
    assert b"<BANCOLIGHT>" in arq.read_bytes()
    assert G.cuidar_do_pessoal(casa["con"], HOJE)["acao"] == "sem mudança"
    _parte(casa["con"], mid, "BELTRANO DE TAL")
    r3 = G.cuidar_do_pessoal(casa["con"], HOJE + timedelta(days=1))
    assert r3["acao"] == "carga completa regravada"
    assert not arq.exists()                       # a de ontem saiu: só há uma pronta
    assert any(x["regra"] == "ONR_CARGA_INICIAL" for x in G.conferir(casa["con"], HOJE))


def test_depois_que_o_ips_leva_a_carga_vem_o_incremental(casa):
    con = casa["con"]
    mid = _matricula(con)
    _parte(con, mid, "FULANO DE TAL")
    arq = Path(G.cuidar_do_pessoal(con, HOJE)["arquivo"])
    processados = casa["tmp"] / "INDICADORES" / "Processados"
    processados.mkdir(parents=True)
    (processados / arq.name).write_bytes(arq.read_bytes())   # o IPS levou
    r = G.cuidar_do_pessoal(con, HOJE)
    assert r["levados"] == 1 and r["fase"] == "INCREMENTAL" and r["acao"] == "nada novo"
    ato = _ato(con, mid, numero=2, lavrado_em="2030-01-01T09:00:00")
    _parte(con, mid, "CICRANO COMPRADOR", ato_id=ato, documento="52998224725")
    r2 = G.cuidar_do_pessoal(con, date(2030, 1, 1))
    assert r2["acao"] == "arquivo gerado" and r2["vinculos"] == 1
    novo = Path(r2["arquivo"])
    assert novo.parent == casa["tmp"] / "INDICADORES"
    assert novo.name.startswith("IndicadorPessoal_") and novo.name.endswith("_01012030.XML")
    assert b"CICRANO COMPRADOR" in novo.read_bytes()
    assert b"FULANO DE TAL" not in novo.read_bytes()
    # passados os dias tolerados sem o IPS levar, vira achado do RI
    con.execute("UPDATE ge_onr_cargas SET gerado_em='2030-01-01T09:00:00' "
                "WHERE tipo='INCREMENTAL'")
    con.commit()
    (a,) = [x for x in G.conferir(con, date(2030, 1, 10))
            if x["regra"] == "ONR_IPS_NAO_LEVOU"]
    assert a["setor"] == "RI"


# -------------------------------------------------------------- as imagens

def _pdf(caminho: Path, paginas: int = 2) -> str:
    import pymupdf
    doc = pymupdf.open()
    for i in range(paginas):
        doc.new_page().insert_text((72, 72), f"MATRICULA pagina {i + 1}")
    doc.save(caminho)
    doc.close()
    return G._sha_arquivo(caminho)


def test_imagem_vai_para_a_pasta_do_csl2_e_a_marca_baixa(casa):
    pdf = casa["tmp"] / "atual.pdf"
    sha = _pdf(pdf)
    mid = _matricula(casa["con"], numero="4030", digi_path=str(pdf), digi_sha256=sha,
                     digi_onr_pendente=1)
    destino = G.pastas(casa["con"])["csl2"]
    r = G.exportar_imagens(casa["con"], destino)
    assert r["convertidas"] == 1 and r["paginas"] == 2 and r["problemas"] == []
    assert (destino / "00000004" / "00004030.0001").exists()
    assert (destino / "00000004" / "00004030.0002").exists()
    marca = casa["con"].execute("SELECT digi_onr_pendente FROM ri_matriculas WHERE id=?",
                                (mid,)).fetchone()[0]
    assert marca == 0
    # o formato é o que onr_carga confere
    import onr_carga
    conf = onr_carga.conferir_imagens(destino, amostra=10)
    assert conf.get("fora_do_padrao", []) in ([], 0) or not conf.get("fora_do_padrao")
    # nada muda, nada se refaz
    assert G.exportar_imagens(casa["con"], destino)["convertidas"] == 0


def test_sem_o_csl2_instalado_a_rodada_nao_baixa_a_marca(casa, sem_credencial):
    """Estar na pasta não é estar no ONR enquanto o CSL2 não lê a pasta."""
    pdf = casa["tmp"] / "atual.pdf"
    sha = _pdf(pdf, paginas=1)
    mid = _matricula(casa["con"], numero="4032", digi_path=str(pdf), digi_sha256=sha,
                     digi_onr_pendente=1)
    G.rodada(casa["con"], casa["banco"], HOJE, escrever=lambda *_: None)
    marca = lambda: casa["con"].execute(                          # noqa: E731
        "SELECT digi_onr_pendente FROM ri_matriculas WHERE id=?", (mid,)).fetchone()[0]
    assert (G.pastas(casa["con"])["csl2"] / "00000004" / "00004032.0001").exists()
    assert marca() == 1
    casa["con"].execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                        (G.CHAVE_CSL2_DESDE, "2026-10-20"))
    casa["con"].commit()
    G.rodada(casa["con"], casa["banco"], HOJE, escrever=lambda *_: None)
    assert marca() == 0


def test_digitalizacao_sem_arquivo_vira_achado(casa):
    _matricula(casa["con"], numero="4031", digi_path=str(casa["tmp"] / "sumiu.pdf"),
               digi_sha256="x", digi_onr_pendente=1)
    G.pastas(casa["con"])["csl2"].mkdir(parents=True)
    r = G.exportar_imagens(casa["con"], G.pastas(casa["con"])["csl2"])
    assert r["convertidas"] == 0 and len(r["problemas"]) == 1
    assert any(x["regra"] == "ONR_IMAGEM_PROBLEMA" and "4031" in x["titulo"]
               for x in G.conferir(casa["con"], HOJE))


# ---------------------------------------------------------- a rodada e o gestor

def test_rodada_grava_o_livro_e_sem_ela_o_agente_e_cobrado(casa, sem_credencial):
    achados = G.conferir(casa["con"], HOJE)
    assert {x["chave"] for x in achados if x["regra"] == "ONR_AGENTE_PARADO"} == {
        "ONR_AGENTE:IMAGENS", "ONR_AGENTE:PESSOAL", "ONR_AGENTE:REAL"}
    G.pastas(casa["con"])["csl2"].mkdir(parents=True)
    linhas = []
    G.rodada(casa["con"], casa["banco"], HOJE, escrever=linhas.append)
    n = casa["con"].execute("SELECT COUNT(*) FROM ge_onr_cargas WHERE tipo='RODADA' "
                            "AND situacao='OK'").fetchone()[0]
    assert n == 3 and len(linhas) == 3
    assert not any(x["regra"] == "ONR_AGENTE_PARADO" for x in G.conferir(casa["con"], HOJE))


def test_o_gestor_conhece_o_agente_de_cargas():
    assert ("ONR_CARGAS", GC.regra_onr_cargas) in GC.REGRAS
    for regra in G.ROTULOS:
        assert GR.ROTULOS[regra] == G.ROTULOS[regra]
    assert G.REGRAS_DE_DECISAO <= GR.REGRAS_SEM_TAREFA
    # 13/10/2026: era «o que é trabalho do RI vira tarefa». As cargas ao ONR
    # saíram das tarefas por ordem do oficial — o envio é dos agentes, e o aviso
    # consolidado vai ao despacho dele.
    assert "ONR_INDICADOR_INCOMPLETO" in GR.REGRAS_SEM_TAREFA
    assert "rodada(con, banco, hoje" in Path(GR.__file__).read_text(encoding="utf-8")


# ------------------------------------------------- fora do servidor (L030R)

@pytest.fixture()
def sem_desvio(monkeypatch):
    """O processo do CLI: ninguém criou `Database`, e o `sqlite3.connect` é o de
    fábrica — o desvio para o PostgreSQL só existe no servidor e na suíte."""
    import banco_pg
    monkeypatch.setattr(sqlite3, "connect", banco_pg._CONNECT_ORIGINAL)


def test_o_envio_ao_onr_abre_o_postgresql_mesmo_sem_o_desvio(casa, com_credencial,
                                                             sem_desvio):
    """O `db` que vai ao `ri_onr_central` abria `sqlite3.connect`, e o módulo
    nativo o recusava: o envio quebrava calado, como erro da rodada."""
    mid = _matricula(casa["con"])
    _parte(casa["con"], mid, "FULANO DE TAL")
    r = G.cuidar_do_real(casa["con"], casa["banco"])
    assert r["erros"] == [] and r["enviados"] == 1


def test_o_cli_do_agente_roda_e_mede_fora_do_servidor(casa, sem_credencial, sem_desvio,
                                                     capsys):
    assert G.main(["--banco", str(casa["banco"]), "--hoje", HOJE.isoformat(),
                   "--sem-imagens"]) == 0
    assert casa["con"].execute("SELECT COUNT(*) FROM ge_onr_cargas WHERE tipo='RODADA' "
                               "AND situacao='OK'").fetchone()[0] == 2
    assert G.main(["--banco", str(casa["banco"]), "--so-medir"]) == 0
    assert '"real"' in capsys.readouterr().out


def test_o_agente_nao_lavra_nem_sela():
    nomes = [n for n in dir(G) if not n.startswith("_")]
    for proibido in ("lavrar", "selar", "cobrar", "obter_selo"):
        assert not any(proibido in n for n in nomes), proibido
    fonte = Path(G.__file__).read_text(encoding="utf-8")
    assert "INSERT INTO ri_atos" not in fonte and "UPDATE ri_atos" not in fonte
