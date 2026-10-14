"""
Testes do acervo morto do E-Ofício.

O QUE ELES DEFENDEM
    Que a cópia seja fiel — porque é para isso que ela existe. O E-Ofício vai
    ser desligado, e depois disso não haverá com o que comparar.

    Por isso a carga confere contra o manifesto tabela a tabela, e por isso o
    banco só ganha o nome definitivo depois de aberto e conferido.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — referencia acervo_eoficio ou sqlite de producao
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import acervo_eoficio as AC          # noqa: E402


def exportacao(tmp_path: Path, tabelas: dict[str, list[dict]],
               manifesto: dict[str, int] | None = None,
               com_esquema: bool = True) -> Path:
    pasta = tmp_path / "EXPORT_TUDO_EOFICIO"
    pasta.mkdir(parents=True, exist_ok=True)
    esquema = []
    for tabela, linhas in tabelas.items():
        with (pasta / f"{tabela}.jsonl").open("w", encoding="utf-8") as fh:
            for linha in linhas:
                fh.write(json.dumps(linha, ensure_ascii=False) + "\n")
        if linhas:
            for i, (col, val) in enumerate(linhas[0].items(), 1):
                tipo = "int" if isinstance(val, int) else "nvarchar"
                esquema.append({"tabela": tabela, "ordem": i, "coluna": col,
                                "tipo": tipo})
    if com_esquema:
        with (pasta / "ESQUEMA.jsonl").open("w", encoding="utf-8") as fh:
            for e in esquema:
                fh.write(json.dumps(e) + "\n")
    contagem = manifesto if manifesto is not None else \
        {t: len(l) for t, l in tabelas.items()}
    with (pasta / "MANIFESTO.jsonl").open("w", encoding="utf-8") as fh:
        for t, n in contagem.items():
            fh.write(json.dumps({"tabela": t, "linhas": n}) + "\n")
    return pasta


@pytest.fixture()
def cenario(tmp_path):
    pasta = exportacao(tmp_path, {
        "tbRegistroESC": [{"id": 1, "strProtocolo": "2020.06.20"},
                          {"id": 2, "strProtocolo": "2020.06.58"}],
        "tbLivroApontamento": [{"id": i, "strTexto": f"protesto {i}"}
                               for i in range(1, 21)],
        "tbFirmaIMG": [{"id": 1, "strPath": "\\\\servidor\\C11\\Firmas\\"}],
    })
    return pasta, tmp_path / "acervo_eoficio.sqlite3"


# --------------------------------------------------------------- a cópia

def test_carrega_tudo_e_confere(cenario):
    pasta, destino = cenario
    r = AC.carregar(pasta, destino)
    assert r["tabelas"] == 3
    assert r["linhas"] == 23
    assert r["divergentes"] == []
    assert AC.conferir(destino) is None


def test_o_dado_chega_igual(cenario):
    pasta, destino = cenario
    AC.carregar(pasta, destino)
    con = sqlite3.connect(destino)
    linhas = con.execute("SELECT id, strProtocolo FROM tbRegistroESC ORDER BY id").fetchall()
    assert linhas == [(1, "2020.06.20"), (2, "2020.06.58")]
    # Inclusive o que a serventia não pratica: protesto veio junto.
    assert con.execute("SELECT COUNT(*) FROM tbLivroApontamento").fetchone()[0] == 20
    con.close()


def test_o_caminho_unc_e_guardado_como_veio(cenario):
    # Nada é interpretado: o valor sai do E-Ofício e chega igual.
    pasta, destino = cenario
    AC.carregar(pasta, destino)
    con = sqlite3.connect(destino)
    assert con.execute("SELECT strPath FROM tbFirmaIMG").fetchone()[0] \
        == "\\\\servidor\\C11\\Firmas\\"
    con.close()


def test_recarregar_da_o_mesmo_resultado(cenario):
    # O acervo é cópia de um banco que não muda mais: recarregar tem de ser
    # idempotente, e a forma barata de garantir isso é refazer do zero.
    pasta, destino = cenario
    primeira = AC.carregar(pasta, destino)
    segunda = AC.carregar(pasta, destino)
    assert primeira["linhas"] == segunda["linhas"] == 23
    assert primeira["tabelas"] == segunda["tabelas"] == 3


# ------------------------------------------------- a carga não pode mentir

def test_tabela_com_menos_linhas_do_que_saiu_e_denunciada(tmp_path):
    # O manifesto diz que saíram 50; o arquivo tem 2. Carga que não bate com a
    # origem é carga que mentiu, e neste projeto já houve contador relatando
    # 4.060 cartões numa rodada que inseriu zero.
    pasta = exportacao(tmp_path, {"tbX": [{"id": 1}, {"id": 2}]},
                       manifesto={"tbX": 50})
    r = AC.carregar(pasta, tmp_path / "a.sqlite3")
    assert r["divergentes"] == [{"tabela": "tbX", "na_origem": 50, "carregou": 2}]


def test_sem_esquema_as_colunas_saem_do_proprio_arquivo(tmp_path):
    pasta = exportacao(tmp_path, {"tbY": [{"a": 1, "b": "x"}]}, com_esquema=False)
    r = AC.carregar(pasta, tmp_path / "a.sqlite3")
    assert "tbY" in r["sem_esquema"]
    con = sqlite3.connect(tmp_path / "a.sqlite3")
    assert con.execute("SELECT a, b FROM tbY").fetchone() == (1, "x")
    con.close()


def test_pasta_inexistente_falha_dizendo(tmp_path):
    with pytest.raises(FileNotFoundError):
        AC.carregar(tmp_path / "nao_existe", tmp_path / "a.sqlite3")


def test_pasta_sem_tabela_falha_dizendo(tmp_path):
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    with pytest.raises(FileNotFoundError):
        AC.carregar(vazia, tmp_path / "a.sqlite3")


def test_o_nome_definitivo_so_aparece_depois_de_conferido(cenario, monkeypatch):
    # Mesma regra do backup: interrompido ou reprovado, fica o `.parcial`.
    pasta, destino = cenario
    monkeypatch.setattr(AC, "conferir", lambda p: "reprovado de propósito")
    with pytest.raises(RuntimeError):
        AC.carregar(pasta, destino)
    assert not destino.exists()
    assert destino.with_suffix(destino.suffix + ".parcial").is_file()


# --------------------------------------------------------- a conferência

def test_conferir_acusa_arquivo_que_nao_e_banco(tmp_path):
    ruim = tmp_path / "ruim.sqlite3"
    ruim.write_bytes(b"isto nao e um banco")
    assert AC.conferir(ruim) is not None


def test_conferir_acusa_acervo_sem_tabela(tmp_path):
    vazio = tmp_path / "vazio.sqlite3"
    con = sqlite3.connect(vazio)
    con.execute("CREATE TABLE _acervo_info (chave TEXT, valor TEXT)")
    con.commit(); con.close()
    assert "nenhuma tabela" in AC.conferir(vazio)


def test_o_resumo_lista_as_maiores(cenario):
    pasta, destino = cenario
    AC.carregar(pasta, destino)
    r = AC.resumo(destino)
    assert r["problema"] is None
    assert r["tabelas"] == 3 and r["linhas"] == 23
    assert r["maiores"][0]["tabela"] == "tbLivroApontamento"
    assert r["info"]["linhas"] == "23"
