"""Nenhuma cópia nasce ao lado do banco — ordem do oficial em 11/10/2026.

O QUE ESTES TESTES GUARDAM
    Em 11/10/2026 o banco foi apagado no meio de 69 cópias de nome parecido,
    que 16 scripts de conserto e duas telas deixavam ao lado dele. Aqui:

    - a cópia «antes de mexer» vai para uma pasta só de cópias, e a pasta
      não cresce para sempre;
    - o backup segue `settings.backup_dir`, e sem ele não cai ao lado do banco;
    - nenhum script de `tools/` que tira cópia ficou sem passar pela regra;
    - a conferência do gestor acusa o que sobra ao lado do banco, e acha o
      backup onde ele mora agora.
"""
from __future__ import annotations

import ast
import os
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import pasta_das_copias as PC  # noqa: E402


def test_a_copia_antes_de_mexer_nao_fica_ao_lado_do_banco(tmp_path, monkeypatch):
    monkeypatch.delenv("CARTORIO_GESTAO_COPIAS", raising=False)
    banco = tmp_path / "cartorio_gestao.sqlite3"
    destino = PC.destino_da_copia(banco.with_suffix(".antes-de-x-1.sqlite3"), banco)
    assert destino.parent == tmp_path / "copias" / "antes_de_mexer"
    assert destino.name == "cartorio_gestao.antes-de-x-1.sqlite3", "o nome é o que o script escolheu"
    assert destino.parent.is_dir()


def test_o_ambiente_troca_a_raiz(tmp_path, monkeypatch):
    monkeypatch.setenv("CARTORIO_GESTAO_COPIAS", str(tmp_path / "fora"))
    assert PC.raiz_das_copias(tmp_path) == tmp_path / "fora"


def test_a_producao_vai_para_a_pasta_que_o_oficial_escolheu(tmp_path, monkeypatch):
    monkeypatch.delenv("CARTORIO_GESTAO_COPIAS", raising=False)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    dados = tmp_path / "CartorioGestao"
    dados.mkdir()
    assert PC.raiz_das_copias(dados) == PC.RAIZ_DA_PRODUCAO


def test_a_pasta_das_copias_guarda_so_as_mais_novas(tmp_path, monkeypatch):
    monkeypatch.setenv("CARTORIO_GESTAO_COPIAS", str(tmp_path / "c"))
    pasta = tmp_path / "c" / "antes_de_mexer"
    pasta.mkdir(parents=True)
    for i in range(20):
        p = pasta / f"x{i:02d}.sqlite3"
        p.write_bytes(b"x")
        os.utime(p, (time.time() - 1000 + i, time.time() - 1000 + i))
    (pasta / "LEIA-ME.txt").write_text("fica")
    PC.pasta_antes_de_mexer(tmp_path / "b.sqlite3", guardar=5)
    sobram = sorted(p.name for p in pasta.glob("*.sqlite3"))
    assert sobram == ["x16.sqlite3", "x17.sqlite3", "x18.sqlite3", "x19.sqlite3"], \
        "guarda 4 para dar lugar à quinta, a que vai nascer"
    assert (pasta / "LEIA-ME.txt").exists(), "a poda só mexe em cópia de banco"


def test_o_backup_segue_a_configuracao_e_sem_ela_nao_cai_ao_lado_do_banco(tmp_path, monkeypatch):
    monkeypatch.delenv("CARTORIO_GESTAO_COPIAS", raising=False)
    assert PC.pasta_de_backups(tmp_path, str(tmp_path / "meu")) == tmp_path / "meu"
    assert PC.pasta_de_backups(tmp_path, "") == tmp_path / "copias" / "backups"
    assert not (tmp_path / "backups").exists()


def test_todo_script_que_tira_copia_passa_pela_regra():
    """Script novo que faça `VACUUM INTO` sem a regra fica vermelho aqui."""
    faltam = []
    for arq in sorted((RAIZ / "tools").glob("*.py")):
        cru = arq.read_bytes()
        if b"VACUUM INTO" in cru and b"destino_da_copia" not in cru:
            faltam.append(arq.name)
    assert not faltam, f"tiram cópia ao lado do banco: {faltam}"


def test_as_telas_nao_gravam_copia_ao_lado_do_banco():
    """Procura `<algo> / "backups"` no código (e não a palavra solta: `ri_web`
    tem «backups» numa lista de pastas que a busca de arquivos PULA)."""
    for nome in ("caixa_web.py", "ri_web.py", "app.py"):
        arvore = ast.parse((RAIZ / nome).read_text(encoding="utf-8"))
        montagens = [n for n in ast.walk(arvore)
                     if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)
                     and isinstance(n.right, ast.Constant) and n.right.value == "backups"]
        assert not montagens, f"{nome} ainda monta a pasta «backups» ao lado do banco"


def test_o_que_sobra_ao_lado_do_banco_e_acusado(tmp_path):
    for nome in ("cartorio_gestao.sqlite3", "secret.key", "selador.cred",
                 "cartorio_gestao.antes-de-x.sqlite3", "tmp_fix.py"):
        (tmp_path / nome).write_bytes(b"x")
    (tmp_path / "arquivos").mkdir()
    (tmp_path / "backups").mkdir()                      # vazia: a versão antiga a recria
    (tmp_path / "tmp_lixo").mkdir()
    (tmp_path / "tmp_lixo" / "a.txt").write_text("x")
    assert [p.name for p in PC.estranhos_na_pasta_do_banco(tmp_path)] == [
        "cartorio_gestao.antes-de-x.sqlite3", "tmp_fix.py", "tmp_lixo"]


def test_a_conferencia_acusa_e_acha_o_backup_onde_ele_mora(tmp_path, monkeypatch):
    import gestor_conferencia as GC
    monkeypatch.delenv("CARTORIO_GESTAO_COPIAS", raising=False)
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    fora = tmp_path / "Copias" / "backups"
    fora.mkdir(parents=True)
    con.execute("INSERT INTO settings VALUES ('backup_dir', ?)", (str(fora),))
    (fora / "backup_completo_20261011_010000.zip").write_bytes(b"x")
    assert GC.regra_backup(con, date.today(), tmp_path) == [], \
        "o backup está na pasta configurada, e a regra não pode acusar «nenhum backup»"
    (tmp_path / "cartorio_gestao.antes-de-x.sqlite3").write_bytes(b"x")
    achados = GC.regra_pasta_do_banco(con, date.today(), tmp_path)
    assert [a["regra"] for a in achados] == ["PASTA_DO_BANCO"]
    assert "cartorio_gestao.antes-de-x.sqlite3" in achados[0]["detalhe"]
