"""A cópia em TIFF para o ONR nasce na hora do envio da digitalização.

    «nao existe outra forma que o sistema processe e crie a copia em tiff?»
                                                      — o oficial, 10/10/2026

O QUE ESTES TESTES GUARDAM
    **Que a cópia nasce logo depois do envio, numa linha à parte**, e a ficha
    diz em que pé ela está — pronta, convertendo, não saiu (e por quê).

    **Que o erro não vira erro na tela de quem enviou**: a digitalização já foi
    gravada; a falha fica na situação da matrícula e a rodada das 07:30 refaz.

    **Que dois escritores não apagam um ao outro** — a rodada das 07:30 e a
    conversão do balcão gravam no mesmo controle, e a linha mais nova ganha.

    **Que o ensaio não escreve na pasta da produção.** Sem pasta configurada, o
    padrão sai da árvore de arquivos DO BANCO — e não do caminho escrito no
    código, que é o que o CSL2 da produção lê.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import gestor_cargas_ri as G                                       # noqa: E402

AGORA = "2026-10-10T08:00:00"


def _pdf(caminho: Path, paginas: int = 2) -> str:
    import pymupdf
    doc = pymupdf.open()
    for i in range(paginas):
        doc.new_page().insert_text((72, 72), f"MATRICULA pagina {i + 1}")
    doc.save(caminho)
    doc.close()
    return G._sha_arquivo(caminho)


class _Db:
    """O `db` da casa no que a conversão usa: `connect` e `db_path`."""

    def __init__(self, caminho: Path):
        self.db_path = Path(caminho)

    def connect(self):
        c = sqlite3.connect(str(self.db_path), timeout=15)
        c.row_factory = sqlite3.Row
        return c


@pytest.fixture()
def casa(cg_casa, tmp_path):
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)",
                ("onr_csl2_pasta", str(tmp_path / "livro2")))
    con.commit()
    yield {"con": con, "db": _Db(cg_casa["banco"]), "tmp": tmp_path,
           "destino": tmp_path / "livro2"}
    con.close()


def _matricula(con, numero: str, pdf: Path | None, sha: str = "") -> int:
    cur = con.execute(
        "INSERT INTO ri_matriculas(numero, livro, livro_norm, tipo_ficha, criado_em, "
        "digi_path, digi_sha256, digi_onr_pendente) VALUES(?,?,?,?,?,?,?,?)",
        (numero, "2", "2", "ESTRUTURADA", AGORA, str(pdf) if pdf else None, sha or None,
         1 if pdf else 0))
    con.commit()
    return int(cur.lastrowid)


def test_a_copia_nasce_numa_linha_a_parte_e_a_ficha_diz_que_esta_pronta(casa):
    pdf = casa["tmp"] / "atual.pdf"
    mid = _matricula(casa["con"], "4040", pdf, _pdf(pdf))
    assert G.situacao_da_imagem(casa["con"], mid)["estado"] == "AGUARDANDO"
    linha = G.converter_em_segundo_plano(casa["db"], mid)
    assert linha is not None
    linha.join(30)
    assert (casa["destino"] / "00000004" / "00004040.0001").exists()
    assert (casa["destino"] / "00000004" / "00004040.0002").exists()
    s = G.situacao_da_imagem(casa["con"], mid)
    assert s["estado"] == "NA_PASTA" and s["paginas"] == 2
    # o «convertendo» não sobra
    assert "4040" not in G.ler_situacao(casa["destino"])


def test_enquanto_converte_a_ficha_diz_convertendo(casa):
    pdf = casa["tmp"] / "atual.pdf"
    mid = _matricula(casa["con"], "4041", pdf, _pdf(pdf, 1))
    casa["destino"].mkdir(parents=True)
    with G._trava_da_pasta(casa["destino"]):
        G._marcar_situacao(casa["destino"], 4041, {"situacao": "CONVERTENDO",
                                                   "em": G._agora()})
    assert G.situacao_da_imagem(casa["con"], mid)["estado"] == "CONVERTENDO"
    # «convertendo» de servidor que caiu no meio não fica para sempre
    with G._trava_da_pasta(casa["destino"]):
        G._marcar_situacao(casa["destino"], 4041, {"situacao": "CONVERTENDO",
                                                   "em": "2026-01-01T00:00:00"})
    assert G.situacao_da_imagem(casa["con"], mid)["estado"] == "AGUARDANDO"


def test_o_erro_fica_na_ficha_e_some_quando_a_conversao_sai(casa):
    pdf = casa["tmp"] / "atual.pdf"
    sha = _pdf(pdf, 1)
    mid = _matricula(casa["con"], "4042", pdf, sha)
    pdf.rename(casa["tmp"] / "guardado.pdf")
    linha = G.converter_em_segundo_plano(casa["db"], mid)
    linha.join(30)
    s = G.situacao_da_imagem(casa["con"], mid)
    assert s["estado"] == "ERRO" and "não encontrado" in s["motivo"]
    (casa["tmp"] / "guardado.pdf").rename(pdf)
    G.converter_em_segundo_plano(casa["db"], mid).join(30)
    assert G.situacao_da_imagem(casa["con"], mid)["estado"] == "NA_PASTA"
    assert "4042" not in G.ler_situacao(casa["destino"])


def test_converter_em_segundo_plano_nunca_estoura(casa, monkeypatch):
    pdf = casa["tmp"] / "atual.pdf"
    mid = _matricula(casa["con"], "4043", pdf, _pdf(pdf, 1))

    def quebra(*a, **k):
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(G, "_converter_uma", quebra)
    G.converter_em_segundo_plano(casa["db"], mid).join(30)
    s = G.situacao_da_imagem(casa["con"], mid)
    assert s["estado"] == "ERRO" and "disco cheio" in s["motivo"]
    # matrícula que não existe: não estoura, só não começa
    assert G.converter_em_segundo_plano(casa["db"], 999999) is None


def test_ficha_arquivada_nao_vai_ao_onr(casa):
    pdf = casa["tmp"] / "atual.pdf"
    mid = _matricula(casa["con"], "904012", pdf, _pdf(pdf, 1))
    assert G.situacao_da_imagem(casa["con"], mid)["estado"] == "FORA"
    assert G.converter_em_segundo_plano(casa["db"], mid) is None
    sem = _matricula(casa["con"], "4044", None)
    assert G.situacao_da_imagem(casa["con"], sem)["estado"] == "SEM_DIGITALIZACAO"


def test_dois_escritores_a_linha_mais_nova_ganha(tmp_path):
    destino = tmp_path / "livro2"
    novo = {"sha": "B", "paginas": 3, "matricula_id": 1, "em": "2026-10-10T10:00:05"}
    velho = {"sha": "A", "paginas": 2, "matricula_id": 1, "em": "2026-10-10T10:00:01"}
    outra = {"sha": "C", "paginas": 1, "matricula_id": 2, "em": "2026-10-10T09:00:00"}
    with G._trava_da_pasta(destino):
        G._juntar_ao_controle(destino, {"4030": novo})
    with G._trava_da_pasta(destino):
        # a rodada que converteu antes grava depois: não apaga o do balcão,
        # e não apaga a matrícula que só ela fez
        G._juntar_ao_controle(destino, {"4030": velho, "4031": outra})
    feito = G.ler_controle(destino)
    assert feito["4030"]["sha"] == "B" and feito["4031"]["sha"] == "C"


def test_trava_de_processo_que_morreu_nao_segura_a_casa(tmp_path):
    destino = tmp_path / "livro2"
    trava = G.caminho_do_controle(destino).with_name("_controle.trava")
    trava.parent.mkdir(parents=True)
    trava.write_text("1234 ontem")
    velho = time.time() - G.TRAVA_VELHA_SEGUNDOS - 60
    os.utime(trava, (velho, velho))
    with G._trava_da_pasta(destino):
        assert trava.exists()
    assert not trava.exists()


def test_sem_pasta_configurada_o_ensaio_nao_escreve_na_producao(cg_casa):
    """O padrão sai da árvore de arquivos do banco, e não do caminho escrito."""
    con = sqlite3.connect(cg_casa["banco"])
    try:
        p = G.pastas(con, cg_casa["banco"])
    finally:
        con.close()
    esperado = Path(cg_casa["banco"]).parent / "arquivos" / "ri" / "onr"
    assert p["csl2"] == esperado / "livro2"
    assert p["ips"] == esperado / "ips"
    assert p["carga_inicial"] == esperado / "carga_inicial"
    assert str(p["csl2"]) != G.PASTA_CSL2_PADRAO


def test_quem_converte_e_a_mesma_funcao_da_rodada():
    """Duas casas para o formato do ONR divergiriam no primeiro conserto."""
    fonte = Path(G.__file__).read_text(encoding="utf-8")
    corpo = fonte.split("def converter_matricula", 1)[1].split("\ndef ", 1)[0]
    assert "exportar_imagens(" in corpo
    assert fonte.count("pagina_em_tiff(pagina, pasta") == 1


# ------------------------------------------------------------------ as telas

def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def test_enviar_a_varredura_dispara_a_copia_e_a_ficha_mostra(cg_casa_logada, monkeypatch,
                                                              tmp_path):
    casa = cg_casa_logada
    c = casa["c"]
    con = sqlite3.connect(casa["banco"])
    con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)",
                ("onr_csl2_pasta", str(tmp_path / "livro2")))
    con.commit()
    mid = _matricula(con, "4050", None)
    con.close()
    pedidos = []
    monkeypatch.setattr(G, "converter_em_segundo_plano",
                        lambda db, m: pedidos.append(m) or None)
    ficha = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    pdf = tmp_path / "varredura.pdf"
    _pdf(pdf, 1)
    with open(pdf, "rb") as f:
        r = c.post(f"/registro-imoveis/{mid}/digitalizacao",
                   data={"csrf_token": _token(ficha), "arquivo": (f, "varredura.pdf")},
                   content_type="multipart/form-data")
    assert r.status_code == 302 and pedidos == [mid]
    ficha = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "ainda não foi feita" in ficha and "Converter agora" in ficha
    assert f"/registro-imoveis/{mid}/digitalizacao/onr" in ficha
    # o botão está DENTRO do formulário do envio: sem `formnovalidate` o campo
    # de arquivo obrigatório impediria o clique
    assert re.search(r"formnovalidate\s+formaction=\"[^\"]*/digitalizacao/onr\"", ficha)


def test_o_botao_converter_agora_comeca_a_conversao(cg_casa_logada, monkeypatch, tmp_path):
    casa = cg_casa_logada
    c = casa["c"]
    con = sqlite3.connect(casa["banco"])
    pdf = tmp_path / "atual.pdf"
    mid = _matricula(con, "4051", pdf, _pdf(pdf, 1))
    con.close()
    pedidos = []
    monkeypatch.setattr(G, "converter_em_segundo_plano",
                        lambda db, m: pedidos.append(m) or object())
    ficha = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = c.post(f"/registro-imoveis/{mid}/digitalizacao/onr",
               data={"csrf_token": _token(ficha)})
    assert r.status_code == 302 and pedidos == [mid]
    log = sqlite3.connect(casa["banco"]).execute(
        "SELECT details FROM audit_logs WHERE action='RI_DIGITALIZACAO_ONR_CONVERTER'"
    ).fetchone()
    assert log and json.loads(log[0])["numero"] == "4051"
