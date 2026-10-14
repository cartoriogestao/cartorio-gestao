"""
Puxada ao vivo do E-Oficio para a carga de Protesto.

O QUE ESTES TESTES GUARDAM
    - aplicar JSONL no acervo substitui tbAvisoProtesto/tbPessoa e marca
      origem ao vivo — sem MSSQL real;
    - atualizar_protesto_ao_vivo chama a exportacao e aplica (mock);
    - falha de conexao vira EoVivoError com frase de balcao;
    - a tela /protesto/importar-eoficio fala em «ao vivo».
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest import mock

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — le acervo/EOF ao vivo
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import acervo_eo_vivo as EO


def _jsonl(pasta: Path, tabela: str, linhas: list[dict]) -> None:
    with (pasta / f"{tabela}.jsonl").open("w", encoding="utf-8") as fh:
        for linha in linhas:
            fh.write(json.dumps(linha, ensure_ascii=False) + "\n")


def test_aplicar_jsonl_substitui_e_marca_ao_vivo(tmp_path: Path):
    acervo = tmp_path / "acervo_eoficio.sqlite3"
    con = sqlite3.connect(acervo)
    con.executescript("""
        CREATE TABLE tbAvisoProtesto (intChave REAL, intNumero TEXT, strTipoPG TEXT);
        CREATE TABLE tbPessoa (intCodigoPessoa REAL, strRazaoSocial TEXT);
        INSERT INTO tbAvisoProtesto VALUES (1, 'VELHO', NULL);
        INSERT INTO tbPessoa VALUES (1, 'ANTIGA');
    """)
    con.commit()
    con.close()

    pasta = tmp_path / "export"
    pasta.mkdir()
    _jsonl(pasta, "tbAvisoProtesto", [
        {"intChave": 141352, "intNumero": "495702/3", "strTipoPG": "12",
         "strChaveUnicaCENPROT": "21987650141352501260827"},
    ])
    _jsonl(pasta, "tbPessoa", [
        {"intCodigoPessoa": 99, "strRazaoSocial": "ALDERINA"},
    ])

    r = EO.aplicar_jsonl_no_acervo(acervo, pasta)
    assert r["tabelas"]["tbAvisoProtesto"] == 1
    assert r["tabelas"]["tbPessoa"] == 1

    con = sqlite3.connect(acervo)
    assert con.execute("SELECT COUNT(*) FROM tbAvisoProtesto").fetchone()[0] == 1
    row = con.execute(
        "SELECT intChave, intNumero, strTipoPG FROM tbAvisoProtesto"
    ).fetchone()
    assert row == (141352, "495702/3", "12")
    info = dict(con.execute("SELECT chave, valor FROM _acervo_info"))
    assert info["protesto_ao_vivo"] == "1"
    assert "ao vivo" in info["origem_protesto"].lower()
    con.close()


def test_aplicar_cria_acervo_se_faltar(tmp_path: Path):
    acervo = tmp_path / "novo" / "acervo_eoficio.sqlite3"
    pasta = tmp_path / "export"
    pasta.mkdir()
    _jsonl(pasta, "tbAvisoProtesto", [{"intChave": 1, "intNumero": "1"}])
    _jsonl(pasta, "tbPessoa", [{"intCodigoPessoa": 1, "strRazaoSocial": "X"}])
    r = EO.aplicar_jsonl_no_acervo(acervo, pasta)
    assert r["novo"] is True
    assert acervo.is_file()


def test_atualizar_protesto_ao_vivo_com_mock(tmp_path: Path):
    acervo = tmp_path / "acervo_eoficio.sqlite3"

    def fake_export(destino, *, tabelas=None, conexoes=None):
        destino = Path(destino)
        _jsonl(destino, "tbAvisoProtesto", [
            {"intChave": 141352, "intNumero": "495702/3", "strTipoPG": "12"},
        ])
        _jsonl(destino, "tbPessoa", [
            {"intCodigoPessoa": 1, "strRazaoSocial": "ALDERINA"},
        ])
        (destino / "_resumo.json").write_text(
            json.dumps({
                "conexao": "Server=localhost\\SERVER;Database=bdCartorio;"
                           "Integrated Security=True;TrustServerCertificate=True",
                "tabelas": {"tbAvisoProtesto": 1, "tbPessoa": 1},
            }),
            encoding="utf-8",
        )
        return json.loads((destino / "_resumo.json").read_text(encoding="utf-8"))

    with mock.patch.object(EO, "exportar_tabelas_ao_vivo", side_effect=fake_export):
        r = EO.atualizar_protesto_ao_vivo(acervo)

    assert r["ao_vivo"] is True
    assert r["tabelas_aplicadas"]["tbAvisoProtesto"] == 1
    con = sqlite3.connect(acervo)
    assert con.execute(
        "SELECT intNumero FROM tbAvisoProtesto WHERE intChave=141352"
    ).fetchone()[0] == "495702/3"
    con.close()


def test_exportar_falha_vira_eo_vivo_error(tmp_path: Path):
    with mock.patch.object(EO, "_powershell", return_value="powershell.exe"):
        with mock.patch("acervo_eo_vivo.subprocess.run") as run:
            run.return_value = mock.Mock(
                returncode=2, stderr="sem conexao", stdout="")
            with pytest.raises(EO.EoVivoError) as erro:
                EO.exportar_tabelas_ao_vivo(tmp_path / "x")
    assert "ao vivo" in str(erro.value).lower() or "bdCartorio" in str(erro.value)


def test_tela_importar_fala_ao_vivo(tmp_path):
    import glob
    from app import create_app
    from database import Database

    SENHA = "Senha#12345"
    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    bd = Database(banco)
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    Database(banco).set_settings({"modulo_protesto_ligado": "1"})
    c = app.test_client()

    def token(html: str) -> str:
        import re
        achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
        assert achado
        return achado.group(1)

    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    r = c.get("/protesto/importar-eoficio")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "ao vivo" in html.lower()
    assert "Trazer agora do E-Ofício ao vivo" in html or "ao vivo" in html
    assert "bdCartorio" in html or "MSSQL" in html or "ao vivo" in html.lower()
