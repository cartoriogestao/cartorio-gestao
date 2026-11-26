"""O gestor confere o backup que sai no Mac pelo recibo que ele deixa (26/11/2026).

Desde 15/11/2026 o backup do banco (todo dia, 18h) e o completo (uma vez por
semana) saem no Mac da casa. O servidor não lê a pasta do Mac pela rede (régua
M3 de 22/10/2026), e a regra acusava «Nenhum backup encontrado» com o backup em
dia. Ordem do oficial: «B» — o Mac deixa um recibo na pasta do servidor, e a
regra só acusa o que passou do prazo da frequência.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gestor_conferencia as GC                                  # noqa: E402

HOJE = date(2026, 11, 26)


def D(dias_atras: int) -> date:
    return HOJE - timedelta(days=dias_atras)


def _recibo(pasta: Path, *, banco: date | None = None, completo: date | None = None,
            texto: str | None = None) -> Path:
    alvo = pasta / GC.PASTA_DO_RECIBO / GC.NOME_DO_RECIBO
    alvo.parent.mkdir(parents=True, exist_ok=True)
    if texto is None:
        corpo = {"gerado_em": f"{HOJE.isoformat()}T18:02:20-03:00"}
        if banco:
            corpo["banco"] = {"arquivo": f"backup_banco_{banco.isoformat()}.zip",
                              "terminou": f"{banco.isoformat()}T18:02:13-03:00",
                              "bytes": 167542244, "sha256": "a" * 64}
        if completo:
            corpo["completo"] = {"arquivo": f"backup_completo_{completo.isoformat()}.zip",
                                 "terminou": f"{completo.isoformat()}T18:11:00-03:00",
                                 "bytes": 31855520816, "sha256": "b" * 64}
        texto = json.dumps(corpo)
    alvo.write_text(texto, encoding="utf-8")
    return alvo


def _conferir(tmp_path, monkeypatch, montar) -> list[dict]:
    from banco_de_teste import conexao_de_teste
    monkeypatch.delenv("CARTORIO_GESTAO_COPIAS", raising=False)
    pasta = tmp_path / "Copias" / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    montar(pasta)
    con = conexao_de_teste()
    try:
        con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT INTO settings VALUES ('backup_dir', ?)", (str(pasta),))
        return GC.regra_backup(con, HOJE, tmp_path)
    finally:
        con.close()


def test_o_caso_de_26_11_recibo_em_dia_e_sem_pacote_local_nao_acusa(tmp_path, monkeypatch):
    """Banco de ontem às 18h e completo de 4 dias, só no Mac: nada a acusar."""
    assert _conferir(tmp_path, monkeypatch,
                     lambda p: _recibo(p, banco=D(1), completo=D(4))) == []


def test_sem_recibo_e_sem_pacote_continua_nenhum_backup_e_diz_onde_procurou(tmp_path, monkeypatch):
    achados = _conferir(tmp_path, monkeypatch, lambda p: None)
    assert [a["titulo"] for a in achados] == ["Nenhum backup encontrado"]
    assert "recibo do Mac (mac/RECIBO_DO_BACKUP.json)" in achados[0]["detalhe"]


def test_banco_do_recibo_com_dois_dias_acusa_o_diario(tmp_path, monkeypatch):
    achados = _conferir(tmp_path, monkeypatch,
                        lambda p: _recibo(p, banco=D(2), completo=D(4)))
    assert [(a["chave"], a["titulo"]) for a in achados] == [
        ("BACKUP:diario", f"Último backup do banco é de {D(2):%d/%m/%Y}")]
    assert achados[0]["gravidade"] == "CRITICO"


def test_completo_do_recibo_com_oito_dias_acusa_o_completo(tmp_path, monkeypatch):
    achados = _conferir(tmp_path, monkeypatch,
                        lambda p: _recibo(p, banco=D(1), completo=D(8)))
    assert [(a["chave"], a["titulo"]) for a in achados] == [
        ("BACKUP:completo", f"Último backup completo é de {D(8):%d/%m/%Y}")]


def test_completo_de_sete_dias_ainda_esta_no_prazo(tmp_path, monkeypatch):
    assert _conferir(tmp_path, monkeypatch,
                     lambda p: _recibo(p, banco=D(1), completo=D(7))) == []


def test_recibo_sem_completo_acusa_so_o_completo(tmp_path, monkeypatch):
    achados = _conferir(tmp_path, monkeypatch, lambda p: _recibo(p, banco=D(0)))
    assert [(a["chave"], a["titulo"]) for a in achados] == [
        ("BACKUP:completo", "Nenhum backup completo encontrado")]


def test_vale_o_mais_novo_entre_o_recibo_e_o_pacote_local(tmp_path, monkeypatch):
    import os
    import time

    def montar(pasta):
        _recibo(pasta, banco=D(3), completo=D(4))
        local = pasta / f"backup_banco_{D(1).isoformat()}.zip"
        local.write_bytes(b"PK")
        momento = time.mktime(D(1).timetuple()) + 18 * 3600
        os.utime(local, (momento, momento))

    assert _conferir(tmp_path, monkeypatch, montar) == []


def test_recibo_ilegivel_nao_conta_e_aparece_no_detalhe(tmp_path, monkeypatch):
    achados = _conferir(tmp_path, monkeypatch, lambda p: _recibo(p, texto="{quebrado"))
    assert [a["titulo"] for a in achados] == ["Nenhum backup encontrado"]
    assert "não se leu (JSONDecodeError)" in achados[0]["detalhe"]


def test_data_adiante_de_hoje_no_recibo_nao_faz_o_backup_parecer_em_dia(tmp_path, monkeypatch):
    amanha = HOJE + timedelta(days=1)
    achados = _conferir(tmp_path, monkeypatch,
                        lambda p: _recibo(p, banco=amanha, completo=amanha))
    assert [a["titulo"] for a in achados] == ["Nenhum backup encontrado"]
    assert "data adiante de hoje" in achados[0]["detalhe"]
