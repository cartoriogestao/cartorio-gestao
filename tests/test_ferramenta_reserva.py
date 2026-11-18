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


# ------------------------------------------------------------------ a situação (18/11/2026)
# De 16 a 18/11/2026 o principal ficou inalcançável na porta do banco, e o sincronia.log dizia
# «última notícia há 30 s … EM DIA»: o PostgreSQL renova `last_msg_receipt_time` a cada vez
# que o worker sobe para tentar de novo. A medida agora exige `received_lsn` (só existe com
# ligação de verdade) e conta a falta de ligação desde a última vez em que a viu.

from datetime import datetime, timedelta, timezone  # noqa: E402

AGORA = datetime(2026, 11, 18, 22, 45, tzinfo=timezone.utc)


class _Cursor:
    """Devolve, em ordem, o que as consultas de `ler_situacao` devolveriam."""

    def __init__(self, *linhas):
        self.linhas = list(linhas)
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append(str(sql))
        return self

    def fetchone(self):
        return self.linhas.pop(0)


def _medir(**dado):
    base = dict(ligada=True, copiando=0, tabelas=351, erros=58, com_ligacao=True,
                atraso_com_ligacao_s=4.0, ligada_ate=None, agora=AGORA)
    base.update(dado)
    return R.medir(**base)


def test_com_ligacao_e_mensagem_recente_esta_em_dia():
    s = _medir()
    assert s.em_dia and s.atraso_s == 4.0
    assert s.ligada_ate == AGORA - timedelta(seconds=4)


def test_sem_ligacao_nao_esta_em_dia_mesmo_com_a_hora_do_worker_fresca():
    # o caso de 16 a 18/11: a assinatura ligada, todas as tabelas prontas, sem received_lsn
    s = _medir(com_ligacao=False, atraso_com_ligacao_s=None,
               ligada_ate=AGORA - timedelta(days=2, hours=4))
    assert not s.em_dia
    assert s.atraso_s == pytest.approx(timedelta(days=2, hours=4).total_seconds())
    frase = R.frase_da_situacao(s)
    assert "SEM LIGAÇÃO com o principal desde" in frase and "(há 2 d 4 h)" in frase
    assert "351 de 351 tabelas copiadas" in frase


def test_sem_ligacao_e_sem_estado_fica_atrasada_sem_inventar_a_hora():
    s = _medir(com_ligacao=False, atraso_com_ligacao_s=None, ligada_ate=None)
    assert not s.em_dia and s.atraso_s is None
    assert "desde quando, não sei" in R.frase_da_situacao(s)


def test_queda_curta_ainda_cabe_na_tolerancia():
    # o PostgreSQL de um dos lados reiniciou agora: a ligação volta em segundos
    s = _medir(com_ligacao=False, atraso_com_ligacao_s=None, ligada_ate=AGORA - timedelta(seconds=90))
    assert s.em_dia


def test_com_ligacao_mas_mensagem_velha_fica_atrasada():
    assert not _medir(atraso_com_ligacao_s=R.ATRASO_TOLERADO_S + 1).em_dia


def test_assinatura_desligada_ou_copiando_nao_esta_em_dia():
    assert not _medir(ligada=False).em_dia
    assert not _medir(copiando=3).em_dia


def test_ler_situacao_usa_o_received_lsn():
    c = _Cursor((True, 0, 351), (False, None), (58,))
    s = R.ler_situacao(c, AGORA - timedelta(hours=3), agora=AGORA)
    assert "received_lsn IS NOT NULL" in c.sql[1]
    assert not s.com_ligacao and not s.em_dia and s.erros == 58
    assert s.atraso_s == pytest.approx(3 * 3600)


def test_o_estado_guarda_e_le_a_ultima_ligacao(tmp_path):
    estado = tmp_path / "replica-ligada.txt"
    assert R.ler_ligada_ate(estado) is None                 # ainda não existe
    R.gravar_ligada_ate(estado, AGORA)
    assert R.ler_ligada_ate(estado) == AGORA
    estado.write_text("lixo")
    assert R.ler_ligada_ate(estado) is None                 # arquivo estragado não derruba
    assert R.ler_ligada_ate(None) is None


def test_situacao_sai_1_sem_ligacao_e_grava_so_com_ligacao(monkeypatch, tmp_path, capsys):
    estado = tmp_path / "replica-ligada.txt"
    R.gravar_ligada_ate(estado, AGORA - timedelta(days=2))

    respostas = []

    class _Banco:
        """`with _abrir(dsn) as pg, pg.cursor() as c` — o cursor é o próximo da fila."""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self):
            return _Contexto(respostas.pop(0))

    class _Contexto:
        def __init__(self, cur):
            self.cur = cur

        def __enter__(self):
            return self.cur

        def __exit__(self, *a):
            return False

    def abrir(_dsn):
        return _Banco()

    monkeypatch.setattr(R, "_abrir", abrir)
    # sem ligação: sai 1, diz desde quando, mostra o dado mais novo, não mexe no estado
    respostas.append(_Cursor((True, 0, 351), (False, None), (58,), ("2026-11-16T18:39:46",)))
    assert R.situacao("dsn", estado, "producao") == 1
    saida = capsys.readouterr().out
    assert "SEM LIGAÇÃO" in saida and saida.strip().endswith("ATRASADA")
    assert "audit_logs de 2026-11-16T18:39:46" in saida
    assert R.ler_ligada_ate(estado) == AGORA - timedelta(days=2)
    # a ligação voltou: sai 0 e o estado anda
    respostas.append(_Cursor((True, 0, 351), (True, 3.0), (58,)))
    assert R.situacao("dsn", estado, "producao") == 0
    assert capsys.readouterr().out.strip().endswith("EM DIA")
    assert R.ler_ligada_ate(estado) > AGORA


def test_sincronizar_devolve_o_codigo_da_situacao():
    texto = (Path(__file__).resolve().parent.parent / "installer" / "macos" / "sincronizar.sh").read_text()
    assert 'situacao --estado "$PASTA/replica-ligada.txt"' in texto
    assert texto.rstrip().endswith('exit "$CODIGO_DA_SITUACAO"')
