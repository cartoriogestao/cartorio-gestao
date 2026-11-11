"""`tools/reserva.py` — as partes que não precisam de dois bancos. O caminho inteiro (montar, a
versão nova, assumir) foi ensaiado com dois PostgreSQL 18 em 07/11/2026; o roteiro está em
`docs/SERVIDOR_RESERVA_MACOS.md`."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import reserva as R  # noqa: E402


def test_o_sql_do_principal_e_idempotente_e_tem_as_travas():
    sql = R.sql_do_principal("producao", "cg")
    assert "wal_level = 'logical'" in sql
    assert f"max_slot_wal_keep_size = '{R.TETO_DO_LOG}'" in sql   # o disco do principal
    assert "pg_reload_conf()" in sql                              # o teto vale sem reiniciar
    assert "REPLICA IDENTITY FULL" in sql                          # tabela sem chave
    assert "WHERE NOT EXISTS (SELECT 1 FROM pg_publication" in sql
    assert "PASSWORD :'senha'" in sql and "senha=" not in sql.split("\n", 3)[3]
    assert "SUPERUSER" not in sql.upper()
    assert "publish = 'insert, update, delete'" in sql
    assert "truncate" not in sql.lower()


@pytest.mark.parametrize("schema, dono", [("producao; drop", "cg"), ("producao", "cg x")])
def test_nome_estranho_e_recusado(schema, dono):
    with pytest.raises(ValueError):
        R.sql_do_principal(schema, dono)


def test_a_diferenca_de_esquema_so_ve_o_que_falta():
    principal = {"a": {"id": "bigint", "nova": "text"}, "b": {"id": "bigint"}}
    reserva = {"a": {"id": "bigint", "velha": "text"}}
    faltam, colunas = R.diferenca_de_esquema(principal, reserva)
    assert faltam == ["b"]
    assert colunas == [("a", "nova", "text")]


def test_senha_na_conexao_e_recusada(monkeypatch):
    monkeypatch.setenv("CG_RESERVA_LOCAL_DSN", "host=x user=cg password=segredo")
    with pytest.raises(SystemExit, match="pgpass"):
        R.main(["situacao"])


def test_assumir_sem_a_frase_nao_faz_nada(monkeypatch, capsys):
    monkeypatch.setenv("CG_RESERVA_LOCAL_DSN", "host=127.0.0.1 port=1 user=cg dbname=nada")
    assert R.main(["assumir"]) == 2          # nem conecta
    assert "DESLIGADO" in capsys.readouterr().out


# ------------------------------------------------------------------ as chaves (os segredos)

import os  # noqa: E402
import stat  # noqa: E402

import reserva_chaves as RCH  # noqa: E402


@pytest.fixture
def par(tmp_path):
    privada = tmp_path / "mac" / "reserva-chave.privada"
    return privada, RCH.gerar_par(privada)


def test_o_par_nasce_uma_vez_e_a_privada_fica_so_para_o_dono(par):
    privada, publica = par
    assert stat.S_IMODE(privada.stat().st_mode) == 0o600
    assert RCH.publica_valida(publica)
    assert RCH.gerar_par(privada) == publica          # rodar de novo não troca a chave


def test_o_pacote_so_abre_com_a_privada_da_reserva(par, tmp_path):
    privada, publica = par
    segredos = {"secret.key": b"abc\n", "cofre.key": b"k" * 44, "portal.cred": os.urandom(80)}
    pacote = RCH.cifrar(segredos, publica)
    assert b"abc" not in pacote.encode() and "portal" not in pacote
    assert RCH.decifrar(pacote, privada) == segredos
    outra = tmp_path / "outra.privada"
    RCH.gerar_par(outra)
    with pytest.raises(ValueError):
        RCH.decifrar(pacote, outra)                    # outra reserva não abre
    import base64
    bruto = bytearray(base64.b64decode(pacote))
    bruto[-1] ^= 1
    with pytest.raises(ValueError):
        RCH.decifrar(base64.b64encode(bytes(bruto)).decode(), privada)   # alterado não abre


@pytest.mark.parametrize("nome, vai", [
    ("secret.key", True), ("cofre.key", True), ("robos.cred", True), ("whatsapp.cred", True),
    ("pgpass.conf", False), ("certificado.pfx", False), ("reserva-chave.privada", False),
    ("../secret.key", False), ("sub/x.cred", False), (".x.cred", False), ("", False),
    ("cartorio_gestao.sqlite3", False),
])
def test_quais_arquivos_sao_segredo(nome, vai):
    assert RCH.e_segredo(nome) is vai


def test_juntar_e_gravar_levam_so_os_segredos(tmp_path):
    dados = tmp_path / "principal"
    dados.mkdir()
    (dados / "secret.key").write_text("s")
    (dados / "robos.cred").write_bytes(b"\x01\x02")
    (dados / "pgpass.conf").write_text("127.0.0.1:5434:cartorio:cg:senha")
    (dados / "notas.txt").write_text("x")
    (dados / "sub").mkdir()
    (dados / "sub" / "outro.cred").write_text("y")
    achados = RCH.juntar(dados)
    assert sorted(achados) == ["robos.cred", "secret.key"]
    mac = tmp_path / "mac"
    assert RCH.gravar(mac, {**achados, "../fora.key": b"x"}) == ["robos.cred", "secret.key"]
    assert not (tmp_path / "fora.key").exists()
    assert stat.S_IMODE((mac / "robos.cred").stat().st_mode) == 0o600


def test_a_impressao_muda_com_o_arquivo_e_com_a_chave(par):
    _, publica = par
    a = RCH.impressao({"secret.key": b"1"}, publica)
    assert a == RCH.impressao({"secret.key": b"1"}, publica)
    assert a != RCH.impressao({"secret.key": b"2"}, publica)
    assert a != RCH.impressao({"secret.key": b"1"}, "B" * 43 + "=")


def test_o_sql_do_principal_leva_so_a_publica(par):
    privada, publica = par
    sql = R.sql_do_principal("producao", "cg", publica)
    assert f"'{RCH.CHAVE_PUBLICA}', '{publica}'" in sql
    assert privada.read_text().strip() not in sql
    assert "os segredos da pasta de dados NÃO vão" in R.sql_do_principal("producao", "cg")
    with pytest.raises(ValueError):
        R.sql_do_principal("producao", "cg", "x'); DROP TABLE settings; --")


def test_o_principal_publica_so_quando_muda_e_a_reserva_abre(cg_casa, par, tmp_path):
    db = cg_casa["db"]
    privada, publica = par
    dados = tmp_path / "principal"
    dados.mkdir()
    (dados / "secret.key").write_text("primeira")
    assert RCH.publicar(db, dados) == "sem reserva"
    db.set_settings({RCH.CHAVE_PUBLICA: publica})
    assert RCH.publicar(db, dados) == "publicado"
    assert RCH.publicar(db, dados) == "em dia"
    (dados / "secret.key").write_text("segunda")
    assert RCH.publicar(db, dados) == "publicado"
    with db.connect() as con:
        pacote = con.execute(f"SELECT pacote FROM {RCH.TABELA} WHERE id = 1").fetchone()[0]
    assert "segunda" not in pacote
    assert RCH.decifrar(pacote, privada) == {"secret.key": b"segunda"}


# ------------------------------------------------------------------ as pastas fora dos arquivos

def test_pastas_fora_da_pasta_de_arquivos():
    config = {"ri_pasta_matriculas_doc": r"D:\Matriculas\Docs",
              "nt_pasta_firmas": r"c:\cartorio\ARQUIVOS\eoficio\Firmas",
              "gratuidade_pasta": "",
              "pastas_de_importacao": "C:\\Importa\\A\n\nE:\\Scanner"}
    assert R.pastas_fora(config, r"C:\Cartorio\Arquivos") == [
        ("ri_pasta_matriculas_doc", r"D:\Matriculas\Docs"),
        ("pastas_de_importacao", r"C:\Importa\A"),
        ("pastas_de_importacao", r"E:\Scanner")]


def test_o_mapa_e_a_raiz_mais_longa_ganham():
    mapa = R.ler_mapa(r"D:\=//u@ip/d; D:\Matriculas=//u@ip/matriculas;lixo;C:\X=")
    assert mapa == [(r"D:\Matriculas", "//u@ip/matriculas"), ("D:\\", "//u@ip/d")]
    assert R.raiz_que_cobre(r"d:\matriculas\docs", mapa)[1] == "//u@ip/matriculas"
    assert R.raiz_que_cobre(r"D:\Matriculas2", mapa)[1] == "//u@ip/d"
    assert R.raiz_que_cobre(r"E:\Y", mapa) is None
    assert R.destino_de(r"D:\Matriculas", Path("/b")) == Path("/b/D_Matriculas")
