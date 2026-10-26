"""A rodada do backup automático (`backup_rotina`) — sem banco, só a pasta.

O QUE ESTES TESTES PROVAM (26/10/2026)
    - o pacote do dia sai UMA vez: quem chega depois (a automação ou o primeiro
      acesso) acha pronto e não gera outro;
    - o completo sai no dia agendado, o perdido sai no dia seguinte, e a agenda
      não anda para a frente por causa disso;
    - a trava impede duas rodadas juntas, e a trava velha (de rodada que
      morreu) se retoma;
    - a falha de um pacote não impede o outro, e vira item de `falhas`;
    - a retenção apaga só o excedente de cada tipo.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backup_rotina as ROT  # noqa: E402

DOMINGO = date(2026, 10, 25)
SEGUNDA = date(2026, 10, 26)


class GeradorFalso:
    """O `gerar(destino, com_arquivos)` da rodada: grava bytes e conta as chamadas."""

    def __init__(self, quebrar: set[str] | None = None):
        self.chamadas: list[tuple[str, bool]] = []
        self.quebrar = quebrar or set()

    def __call__(self, destino: Path, com_arquivos: bool) -> Path:
        self.chamadas.append((destino.name, com_arquivos))
        if ("completo" if com_arquivos else "banco") in self.quebrar:
            raise OSError("disco cheio, por exemplo")
        destino.write_bytes(b"PK pacote de mentira " + destino.name.encode())
        return destino


def _rodar(pasta, gerar, hoje, dia=6, **k):
    return ROT.rodada(pasta, gerar, hoje=hoje, completo_dia=dia, retencao_banco=30,
                      retencao_completo=8, agora=datetime.combine(hoje, datetime.min.time()), **k)


def _datar(p: Path, dia: date) -> None:
    t = datetime.combine(dia, datetime.min.time()).timestamp() + 3600
    os.utime(p, (t, t))


def test_o_pacote_do_dia_sai_uma_vez_so(tmp_path):
    gerar = GeradorFalso()
    r1 = _rodar(tmp_path, gerar, SEGUNDA)
    assert [f["arquivo"] for f in r1["feitos"]] == ["backup_banco_2026-10-26.zip",
                                                     "backup_completo_2026-10-26.zip"]
    assert len(r1["feitos"][0]["sha256"]) == 64
    for p in tmp_path.glob("backup_completo_*.zip"):
        _datar(p, SEGUNDA)
    r2 = _rodar(tmp_path, gerar, SEGUNDA)
    assert r2["feitos"] == []
    assert [j["arquivo"] for j in r2["ja_existiam"]] == ["backup_banco_2026-10-26.zip"]
    assert len(gerar.chamadas) == 2
    assert not (tmp_path / ROT.NOME_DA_TRAVA).exists()


def test_o_completo_sai_no_dia_agendado_e_o_perdido_no_dia_seguinte(tmp_path):
    gerar = GeradorFalso()
    antigo = tmp_path / "backup_completo_2026-10-18.zip"
    antigo.write_bytes(b"PK")
    _datar(antigo, date(2026, 10, 18))                       # o domingo anterior
    # sábado: o último domingo agendado é o dia 18, e há completo dele — não é devido
    assert not ROT.completo_devido(tmp_path, date(2026, 10, 24), 6)
    # o domingo 25 passou sem rodada (máquina desligada): na segunda ele sai
    assert ROT.completo_devido(tmp_path, SEGUNDA, 6)
    r = _rodar(tmp_path, gerar, SEGUNDA)
    assert any(f["tipo"] == "completo" for f in r["feitos"])
    _datar(tmp_path / "backup_completo_2026-10-26.zip", SEGUNDA)
    # e a agenda não andou: terça a sábado nada; o domingo seguinte é o dia dele
    for n in range(1, 6):
        assert not ROT.completo_devido(tmp_path, SEGUNDA + timedelta(days=n), 6)
    assert ROT.completo_devido(tmp_path, date(2026, 11, 1), 6)


def test_a_falha_de_um_pacote_nao_impede_o_outro(tmp_path):
    r = _rodar(tmp_path, GeradorFalso(quebrar={"banco"}), DOMINGO)
    assert [f["tipo"] for f in r["falhas"]] == ["banco"]
    assert "disco cheio" in r["falhas"][0]["erro"]
    assert [f["tipo"] for f in r["feitos"]] == ["completo"]
    assert not (tmp_path / "backup_banco_2026-10-25.zip").exists()


def test_duas_rodadas_juntas_nao_andam(tmp_path):
    gerar = GeradorFalso()
    with ROT.trava(tmp_path):
        with pytest.raises(ROT.RodadaOcupada):
            _rodar(tmp_path, gerar, SEGUNDA)
    assert gerar.chamadas == []


def test_a_trava_de_rodada_que_morreu_se_retoma(tmp_path):
    velha = tmp_path / ROT.NOME_DA_TRAVA
    velha.write_text("pid=1\n", encoding="utf-8")
    t = datetime.now().timestamp() - (ROT.TRAVA_VENCIDA_H + 1) * 3600
    os.utime(velha, (t, t))
    r = ROT.rodada(tmp_path, GeradorFalso(), hoje=SEGUNDA, completo_dia=6, retencao_banco=30,
                   retencao_completo=8)
    assert r["feitos"]
    assert not velha.exists()


def test_a_retencao_apaga_so_o_excedente_de_cada_tipo(tmp_path):
    for n in range(5):
        dia = SEGUNDA - timedelta(days=n + 1)
        p = tmp_path / f"backup_banco_{dia.isoformat()}.zip"
        p.write_bytes(b"PK")
        _datar(p, dia)
    r = ROT.rodada(tmp_path, GeradorFalso(), hoje=SEGUNDA, completo_dia=SEGUNDA.weekday(),
                   retencao_banco=3, retencao_completo=8)
    restam = sorted(p.name for p in tmp_path.glob("backup_banco_*.zip"))
    assert len(restam) == 3 and "backup_banco_2026-10-26.zip" in restam
    assert len(r["expurgados"]) == 3
    assert list(tmp_path.glob("backup_completo_*.zip"))


def test_os_parametros_da_casa_tem_piso_e_padrao():
    lidos = {"backup_completo_dia": "x", "backup_retention": "1", "backup_completo_retencao": ""}
    p = ROT.parametros_da_casa(lambda chave, padrao: lidos.get(chave, padrao))
    assert p == {"completo_dia": 6, "retencao_banco": 3, "retencao_completo": 8}


def test_o_ultimo_pacote_e_o_mais_novo_dos_automaticos(tmp_path):
    assert ROT.ultimo_pacote(tmp_path) is None
    velho = tmp_path / "backup_completo_2026-10-18.zip"
    novo = tmp_path / "backup_banco_2026-10-26.zip"
    manual = tmp_path / "backup_manual_20261026_120000.zip"
    for p, dia in ((velho, date(2026, 10, 18)), (novo, SEGUNDA), (manual, SEGUNDA + timedelta(days=1))):
        p.write_bytes(b"PK")
        _datar(p, dia)
    assert ROT.ultimo_pacote(tmp_path) == novo
