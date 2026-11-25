"""A TROCA PELA CHAVE QUE A CENTRAL JA USA (PR006): so nos pares dados, e so
se todos passam.

O QUE ELES CONFEREM
      - a troca grava a chave da Central nos titulos da lista, e so neles;
      - a lista velha (a chave gravada mudou depois da conferencia) nao grava
        nada, nem os pares bons;
      - chave de outra comarca ou cartorio, chave ja de outro titulo, titulo
        repetido e irmao do protocolo fora da lista sao recusados;
      - o titulo sem chave tambem recebe a da Central;
      - a ferramenta le o CSV e simula sem gravar.

Dados ficticios: IBGE e serventia de exemplo, nenhum nome de verdade.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_protesto_chaves_que_faltam import _chave, _configurar, _titulo, con  # noqa: E402,F401

import protesto_cenprot as CP  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import trocar_chave_pela_da_central as FERRAMENTA  # noqa: E402


def _k(seq, data="2026-01-05", ibge="1234567", cartorio="03"):
    return CP.compor_chave(ibge=ibge, sequencial=seq, cartorio=cartorio, data=data)


def _par(tid, antiga, nova):
    return {"titulo_id": tid, "chave_atual": antiga or "", "chave_central": nova}


def test_troca_so_nos_pares_dados(con):
    _configurar(con)
    a = _titulo(con, chave_origem="LOTE:1", chave=_k(500101), protocolo="2601050001")
    b = _titulo(con, chave_origem="LOTE:2", chave=_k(500102), protocolo="2601050002")
    trocados = CP.trocar_pela_chave_da_central(con, [_par(a, _k(500101), _k(700))])
    assert [t["titulo_id"] for t in trocados] == [a]
    assert _chave(con, a) == _k(700)
    assert _chave(con, b) == _k(500102)


def test_titulo_sem_chave_recebe_a_da_central(con):
    _configurar(con)
    a = _titulo(con, chave_origem="LOTE:3", protocolo="2601060003")
    CP.trocar_pela_chave_da_central(con, [_par(a, "", _k(710, data="2026-01-06"))])
    assert _chave(con, a) == _k(710, data="2026-01-06")


def test_lista_velha_nao_grava_nenhum(con):
    _configurar(con)
    a = _titulo(con, chave_origem="LOTE:4", chave=_k(500101), protocolo="2601050001")
    b = _titulo(con, chave_origem="LOTE:5", chave=_k(500102), protocolo="2601050002")
    with pytest.raises(CP.CenprotError, match="lista"):
        CP.trocar_pela_chave_da_central(con, [_par(a, _k(500101), _k(700)),
                                              _par(b, _k(999), _k(701))])
    assert _chave(con, a) == _k(500101)
    assert _chave(con, b) == _k(500102)


@pytest.mark.parametrize("nova", [_k(700, ibge="7654321"), _k(700, cartorio="01"),
                                  "123"])
def test_recusa_chave_que_nao_e_desta_casa(con, nova):
    _configurar(con)
    a = _titulo(con, chave_origem="LOTE:6", chave=_k(500101), protocolo="2601050001")
    with pytest.raises(CP.CenprotError):
        CP.trocar_pela_chave_da_central(con, [_par(a, _k(500101), nova)])
    assert _chave(con, a) == _k(500101)


def test_recusa_chave_que_ja_e_de_outro_titulo(con):
    _configurar(con)
    a = _titulo(con, chave_origem="LOTE:7", chave=_k(500101), protocolo="2601050001")
    _titulo(con, chave_origem="LOTE:8", chave=_k(700), protocolo="2601050009")
    with pytest.raises(CP.CenprotError, match="ja e do titulo"):
        CP.trocar_pela_chave_da_central(con, [_par(a, _k(500101), _k(700))])
    assert _chave(con, a) == _k(500101)


def test_recusa_irmao_do_protocolo_fora_da_lista(con):
    _configurar(con)
    a = _titulo(con, chave_origem="LOTE:9", chave=_k(500101), protocolo="2601050001")
    _titulo(con, chave_origem="LOTE:10", chave=_k(500101), protocolo="2601050001")
    with pytest.raises(CP.CenprotError, match="mesma chave antiga"):
        CP.trocar_pela_chave_da_central(con, [_par(a, _k(500101), _k(700))])


def test_recusa_repetidos_e_lista_vazia(con):
    _configurar(con)
    a = _titulo(con, chave_origem="LOTE:11", chave=_k(500101), protocolo="2601050001")
    b = _titulo(con, chave_origem="LOTE:12", chave=_k(500102), protocolo="2601050002")
    with pytest.raises(CP.CenprotError, match="mais de um"):
        CP.trocar_pela_chave_da_central(con, [_par(a, _k(500101), _k(700)),
                                              _par(b, _k(500102), _k(700))])
    with pytest.raises(CP.CenprotError):
        CP.trocar_pela_chave_da_central(con, [])


def test_ferramenta_le_o_csv(tmp_path):
    arquivo = tmp_path / "lista.csv"
    arquivo.write_text("titulo_id;protocolo;chave_atual;chave_central\n"
                       "9;2601050001;111;222\n;;;\n", encoding="utf-8")
    assert FERRAMENTA.ler_pares(arquivo) == [
        {"titulo_id": "9", "chave_atual": "111", "chave_central": "222"}]
    ruim = tmp_path / "ruim.csv"
    ruim.write_text("id;chave\n1;2\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        FERRAMENTA.ler_pares(ruim)


def _copia_de_mentira(db_path, destino) -> Path:
    """No lugar do pg_dump: o teste e da troca, e nao da copia."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(b"copia de teste")
    return destino


def test_ferramenta_simula_e_depois_grava_com_auditoria(
        cg_db, cg_db_path, monkeypatch, tmp_path):
    import banco_pg
    monkeypatch.setenv("CARTORIO_GESTAO_COPIAS", str(tmp_path / "copias"))
    monkeypatch.setattr(banco_pg, "copiar_para_arquivo", _copia_de_mentira)
    login = "operador.exemplo"
    cg_db.create_user(login, "Operador Exemplo", "senha-de-teste-1")
    with cg_db.connect() as c:
        _configurar(c)
        tid = _titulo(c, chave_origem="LOTE:FERRAMENTA", chave=_k(500101),
                      protocolo="2601050001")
        c.commit()
    lista = tmp_path / "lista.csv"
    lista.write_text("titulo_id;chave_atual;chave_central\n"
                     f"{tid};{_k(500101)};{_k(700)}\n", encoding="utf-8")
    base = ["--banco", str(cg_db_path), "--arquivo", str(lista)]

    assert FERRAMENTA.main(base) == 0
    with cg_db.connect() as c:
        assert _chave(c, tid) == _k(500101)

    with pytest.raises(SystemExit):
        FERRAMENTA.main(base + ["--gravar"])

    assert FERRAMENTA.main(base + ["--gravar", "--usuario", login,
                                   "--a-mando-de", "oficial.exemplo"]) == 0
    with cg_db.connect() as c:
        assert _chave(c, tid) == _k(700)
        rastro = c.execute(
            "SELECT details, agente, a_mando_de FROM audit_logs "
            "WHERE action='PROTESTO_CHAVE_DA_CENTRAL' AND entity_id=?", (tid,)).fetchall()
    assert len(rastro) == 1
    assert _k(500101) in rastro[0][0] and _k(700) in rastro[0][0]
    assert rastro[0][2] == "oficial.exemplo"
