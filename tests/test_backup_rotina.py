"""A rodada do backup automático (`backup_rotina`) — sem banco, só a pasta.

O QUE ESTES TESTES PROVAM (26/10/2026)
    - o pacote do dia sai UMA vez: quem chega depois (a automação ou o primeiro
      acesso) acha pronto e não gera outro;
    - o completo sai no dia agendado, o perdido sai no dia seguinte, e a agenda
      não anda para a frente por causa disso;
    - a trava impede duas rodadas juntas, e a trava velha (de rodada que
      morreu) se retoma;
    - a falha de um pacote não impede o outro, e vira item de `falhas`;
    - a retenção é de 5 dias e NUNCA apaga o completo-base do pacote mais novo,
      nem o próprio mais novo, nem arquivo que não seja pacote da casa
      (decisões do oficial de 26/10/2026: «salva os últimos 5 dias, apaga os
      mais antigos» e «completo uma vez por semana»);
    - a conferência do gestor cobra o completo na semana e o pacote do dia.

ESCRITOS E NÃO EXECUTADOS NESTA MÁQUINA (26/10/2026, sobrecarga — ordem do
oficial): a suíte roda na máquina do merge.
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
    k.setdefault("retencao_dias", 30)
    return ROT.rodada(pasta, gerar, hoje=hoje, completo_dia=dia,
                      agora=datetime.combine(hoje, datetime.min.time()), **k)


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
    r = ROT.rodada(tmp_path, GeradorFalso(), hoje=SEGUNDA, completo_dia=6, retencao_dias=30)
    assert r["feitos"]
    assert not velha.exists()


# ------------------------------------------------------------- a retenção de 5 dias


def D(n: int) -> date:
    """O «dia n» dos cenários do oficial (1 a 10 de novembro de 2026)."""
    return date(2026, 11, n)


def _pacote(pasta: Path, tipo: str, dia: date) -> Path:
    p = pasta / f"backup_{tipo}_{dia.isoformat()}.zip"
    p.write_bytes(b"PK " + p.name.encode())
    _datar(p, dia)
    return p


def _restam(pasta: Path) -> list[str]:
    return sorted(p.name for p in pasta.iterdir())


def test_dez_dias_com_completo_no_dia_1_e_no_dia_8(tmp_path):
    """O cenário que o oficial aprovou: some o completo do dia 1, fica o do dia 8."""
    for n in range(1, 11):
        _pacote(tmp_path, "banco", D(n))
    _pacote(tmp_path, "completo", D(1))
    _pacote(tmp_path, "completo", D(8))
    r = ROT.aplicar_retencao(tmp_path, D(10), 5)
    assert _restam(tmp_path) == sorted(
        [f"backup_banco_{D(n).isoformat()}.zip" for n in range(6, 11)]
        + [f"backup_completo_{D(8).isoformat()}.zip"])
    # os diários 8, 9 e 10 são «dele»; os 6 e 7 ficam por estarem na janela
    assert sorted(a["arquivo"] for a in r["apagados"]) == sorted(
        [f"backup_banco_{D(n).isoformat()}.zip" for n in range(1, 6)]
        + [f"backup_completo_{D(1).isoformat()}.zip"])
    assert "completo-base" in r["mantidos"][f"backup_completo_{D(8).isoformat()}.zip"]
    assert r["falhas"] == [] and r["sem_registro"] == []


def test_o_completo_base_com_mais_de_5_dias_nao_sai(tmp_path):
    for n in range(1, 11):
        _pacote(tmp_path, "banco", D(n))
    base = _pacote(tmp_path, "completo", D(1))
    r = ROT.aplicar_retencao(tmp_path, D(10), 5)
    assert base.exists(), "sem o completo-base o pacote mais novo não devolve a casa inteira"
    assert "fica assim mesmo" in r["mantidos"][base.name]
    assert _restam(tmp_path) == sorted(
        [base.name] + [f"backup_banco_{D(n).isoformat()}.zip" for n in range(6, 11)])


def test_com_o_backup_parado_o_mais_novo_e_a_base_ficam(tmp_path):
    """Tudo passou da janela (o backup parou): a retenção não pode zerar a pasta."""
    _pacote(tmp_path, "completo", D(1))
    for n in range(1, 4):
        _pacote(tmp_path, "banco", D(n))
    r = ROT.aplicar_retencao(tmp_path, date(2026, 11, 30), 5)
    assert _restam(tmp_path) == [f"backup_banco_{D(3).isoformat()}.zip",
                                 f"backup_completo_{D(1).isoformat()}.zip"]
    assert r["mantidos"][f"backup_banco_{D(3).isoformat()}.zip"] == "o pacote mais novo"


def test_a_retencao_so_apaga_pacote_da_casa_na_propria_pasta(tmp_path):
    for n in range(1, 11):
        _pacote(tmp_path, "banco", D(n))
    _pacote(tmp_path, "completo", D(8))
    estranhos = [tmp_path / "backup_manual_20261101_120000.zip",       # backup feito à mão
                 tmp_path / "backup_completo_20261011_010000.zip",     # o de fora do sistema
                 tmp_path / "backup_automatico_2026.zip",              # o formato antigo
                 tmp_path / f"backup_banco_{D(2).isoformat()}.zip.parcial",
                 tmp_path / "backup_banco_2026-02-31.zip",             # casa o padrão, não é data
                 tmp_path / "leia-me.txt"]
    for p in estranhos:
        p.write_bytes(b"x")
        _datar(p, D(1))
    sub = tmp_path / "espelho"
    sub.mkdir()
    dentro = _pacote(sub, "banco", D(1))                                # subpasta não é a pasta
    ROT.aplicar_retencao(tmp_path, D(10), 5)
    assert all(p.exists() for p in estranhos) and dentro.exists()
    assert not (tmp_path / f"backup_banco_{D(1).isoformat()}.zip").exists()


def test_com_registro_o_pacote_recente_que_nao_esta_nele_fica(tmp_path):
    """`bk_pacotes` nasceu em 26/10/2026: depois disso, só se apaga o que está lá."""
    for n in range(1, 11):
        _pacote(tmp_path, "banco", D(n))
    _pacote(tmp_path, "completo", D(8))
    antigo = _pacote(tmp_path, "banco", date(2026, 10, 1))             # antes do registro
    registrados = {f"backup_banco_{D(n).isoformat()}.zip" for n in (1, 2, 3)}
    r = ROT.aplicar_retencao(tmp_path, D(10), 5, registrados)
    assert not antigo.exists(), "de antes do registro, o nome basta"
    assert sorted(a["arquivo"] for a in r["apagados"]) == sorted(
        [antigo.name] + sorted(registrados))
    assert r["sem_registro"] == [f"backup_banco_{D(n).isoformat()}.zip" for n in (4, 5)]
    assert (tmp_path / f"backup_banco_{D(4).isoformat()}.zip").exists()
    # e a rodada transforma isso em aviso, para alguém conferir
    rr = ROT.rodada(tmp_path, GeradorFalso(), hoje=D(10), completo_dia=D(8).weekday(),
                    retencao_dias=5, registrados=registrados,
                    agora=datetime.combine(D(10), datetime.min.time()))
    assert any("bk_pacotes" in a for a in rr["avisos"])
    assert rr["retencao"]["sem_registro"]


def test_a_rodada_aplica_a_retencao_de_5_dias(tmp_path):
    for n in range(1, 10):
        _pacote(tmp_path, "banco", D(n))
    _pacote(tmp_path, "completo", D(1))
    _pacote(tmp_path, "completo", D(8))
    r = ROT.rodada(tmp_path, GeradorFalso(), hoje=D(10), completo_dia=D(8).weekday(),
                   retencao_dias=5, agora=datetime.combine(D(10), datetime.min.time()))
    assert [f["arquivo"] for f in r["feitos"]] == [f"backup_banco_{D(10).isoformat()}.zip"]
    assert f"backup_completo_{D(1).isoformat()}.zip" in r["expurgados"]
    assert f"backup_completo_{D(8).isoformat()}.zip" not in r["expurgados"]
    assert len(r["expurgados"]) == 6                     # os diários 1 a 5 e o completo 1


def test_os_parametros_da_casa_tem_piso_e_padrao():
    p = ROT.parametros_da_casa(lambda chave, padrao: padrao)
    assert p == {"completo_dia": 6, "retencao_dias": 5}, "o padrão de fábrica é 5 dias"
    lidos = {"backup_completo_dia": "x", "backup_retencao_dias": "1",
             # as chaves antigas (contavam pacotes) não governam mais nada
             "backup_retention": "30", "backup_completo_retencao": "8"}
    p = ROT.parametros_da_casa(lambda chave, padrao: lidos.get(chave, padrao))
    assert p == {"completo_dia": 6, "retencao_dias": ROT.RETENCAO_DIAS_MINIMA}


# ------------------------------------------------------------- a conferência do gestor


def _conferir_backup(tmp_path, monkeypatch, hoje, pacotes):
    import gestor_conferencia as GC
    from banco_de_teste import conexao_de_teste
    monkeypatch.delenv("CARTORIO_GESTAO_COPIAS", raising=False)
    pasta = tmp_path / "Copias" / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    for tipo, dia in pacotes:
        _pacote(pasta, tipo, dia)
    con = conexao_de_teste()
    try:
        con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT INTO settings VALUES ('backup_dir', ?)", (str(pasta),))
        return GC.regra_backup(con, hoje, tmp_path)
    finally:
        con.close()


def test_o_gestor_cobra_o_completo_na_semana_e_o_pacote_do_dia(tmp_path, monkeypatch):
    """«Completo uma vez por semana» (oficial, 26/10/2026): a regra deixou de cobrar
    o completo com a folga de um dia, que acusava seis dias em sete."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    hoje = D(10)
    # completo de 7 dias e o diário de ontem (a conferência roda de manhã; o
    # backup, às 18h): nada a acusar
    assert _conferir_backup(tmp_path / "a", monkeypatch, hoje,
                            [("completo", D(3)), ("banco", D(9))]) == []
    # completo de 8 dias: acusa o completo, e só ele
    achados = _conferir_backup(tmp_path / "b", monkeypatch, hoje,
                               [("completo", D(2)), ("banco", D(10))])
    assert [a["chave"] for a in achados] == ["BACKUP:completo"]
    # diário de anteontem: acusa o pacote do dia
    achados = _conferir_backup(tmp_path / "c", monkeypatch, hoje,
                               [("completo", D(5)), ("banco", D(8))])
    assert [a["chave"] for a in achados] == ["BACKUP:diario"]
    assert all(a["regra"] == "BACKUP" and a["gravidade"] == "CRITICO" for a in achados)
    # o completo do dia também vale como pacote do dia (ele leva o banco)
    assert _conferir_backup(tmp_path / "d", monkeypatch, hoje, [("completo", D(10))]) == []
    # nada na pasta: um achado só
    achados = _conferir_backup(tmp_path / "e", monkeypatch, hoje, [])
    assert [a["titulo"] for a in achados] == ["Nenhum backup encontrado"]


def test_o_ultimo_pacote_e_o_mais_novo_dos_automaticos(tmp_path):
    assert ROT.ultimo_pacote(tmp_path) is None
    velho = tmp_path / "backup_completo_2026-10-18.zip"
    novo = tmp_path / "backup_banco_2026-10-26.zip"
    manual = tmp_path / "backup_manual_20261026_120000.zip"
    for p, dia in ((velho, date(2026, 10, 18)), (novo, SEGUNDA), (manual, SEGUNDA + timedelta(days=1))):
        p.write_bytes(b"PK")
        _datar(p, dia)
    assert ROT.ultimo_pacote(tmp_path) == novo
