"""Os quatro alertas do CodeQL que seguravam o PR #65 (27/10/2026).

- `despesas.centavos_da_tela` lia o valor do formulário com uma expressão
  regular que recuava em polinômio numa fila de zeros (py/polynomial-redos).
  Agora lê sem expressão regular, e aceita e recusa exatamente o mesmo.
- `banco_pg.copiar_para_arquivo` punha o destino na linha de comando do
  pg_dump, e a ponte tirava esse destino do texto do SQL
  (`VACUUM INTO 'x'`) — py/command-line-injection. O destino agora não vai
  ao pg_dump (a saída padrão vai para o arquivo), e a ponte só aceita
  `VACUUM INTO ?`, com o destino dentro da pasta das cópias do banco
  (a regra da casa; sem ela, o CodeQL acusava o caminho sem controle).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import banco_pg  # noqa: E402
import despesas as DP  # noqa: E402
from bd_nativo import banco  # noqa: E402
from banco_de_teste import conexao_de_teste  # noqa: E402

so_no_postgres = pytest.mark.skipif(
    not banco_pg.ativo(), reason="a cópia é um pg_dump (CG_PG_DSN)")


# ------------------------------------------------------- o valor do formulário


@pytest.mark.parametrize("texto,centavos", [
    ("1.234,56", 123456), ("R$ 1.234,56", 123456), ("1234,5", 123450),
    ("1234.56", 123456), ("1.234", 123400), ("12.345.678", 1234567800),
    ("0,01", 1), ("7", 700), ("", 0), ("  ", 0),
])
def test_o_valor_da_tela_continua_lido_como_antes(texto, centavos):
    assert DP.centavos_da_tela(texto) == centavos


@pytest.mark.parametrize("texto", [
    "1.234.56", "1234.567.89", ",5", "5,", "1,234", "1..2", "-1", "a1", "1 234",
    "１２",                       # dígito que não é ASCII não é dinheiro
])
def test_o_que_nao_e_dinheiro_continua_recusado(texto):
    with pytest.raises(DP.DespesaError, match="Valor ilegível"):
        DP.centavos_da_tela(texto)


def test_uma_fila_de_zeros_e_recusada_na_hora():
    inicio = time.monotonic()
    with pytest.raises(DP.DespesaError):
        DP.centavos_da_tela("0" * 200_000 + "x")
    assert time.monotonic() - inicio < 1.0


# ---------------------------------------------------------- a cópia do banco


@so_no_postgres
def test_vacuum_into_com_o_caminho_no_texto_e_recusado_e_nao_finge_copia(tmp_path):
    con = conexao_de_teste()
    destino = tmp_path / "copia.dump"
    try:
        with pytest.raises(Exception, match="VACUUM INTO só com o destino em parâmetro"):
            con.execute(f"VACUUM INTO '{destino}'")
    finally:
        con.close()
    assert not destino.exists()


@so_no_postgres
def test_vacuum_into_com_parametro_continua_copiando_para_a_pasta_das_copias():
    from pasta_das_copias import destino_da_copia
    con = conexao_de_teste()
    con.execute("CREATE TABLE t_copia (x INTEGER)")
    con.commit()
    destino = destino_da_copia(Path("antes_do_teste.sqlite3"),
                               Path(banco(con)._ponte.db_path))
    try:
        con.execute("VACUUM INTO ?", (str(destino),))
    finally:
        con.close()
    # o formato próprio do pg_dump (-Fc) começa por «PGDMP»
    assert destino.read_bytes()[:5] == b"PGDMP"


@so_no_postgres
@pytest.mark.parametrize("fora", ["fora.dump", "../fora.dump"])
def test_vacuum_into_fora_da_pasta_das_copias_e_recusado(tmp_path, fora):
    from pasta_das_copias import raiz_das_copias
    con = conexao_de_teste()
    raiz = raiz_das_copias(Path(banco(con)._ponte.db_path).parent)
    destino = (tmp_path / fora) if fora == "fora.dump" else (raiz / fora)
    try:
        with pytest.raises(Exception, match="só grava na pasta das cópias"):
            con.execute("VACUUM INTO ?", (str(destino),))
    finally:
        con.close()
    assert not Path(destino).exists()


@so_no_postgres
def test_o_destino_nao_vai_na_linha_de_comando_e_a_copia_que_falha_some(tmp_path, monkeypatch):
    import subprocess
    chamadas = []
    original = subprocess.run

    def falhar(comando, **kw):
        chamadas.append(list(comando))
        kw["stdout"].write(b"PGDMP pela metade")
        return original([sys.executable, "-c", "import sys; sys.exit(3)"], **kw)
    monkeypatch.setattr(subprocess, "run", falhar)
    con = conexao_de_teste()
    destino = tmp_path / "-f.dump"           # um nome que parece opção
    try:
        with pytest.raises(Exception, match="pg_dump falhou"):
            banco_pg.copiar_para_arquivo(banco(con)._ponte.db_path, destino)
    finally:
        con.close()
    assert chamadas and all(str(destino) not in parte for parte in chamadas[0])
    assert "-f" not in chamadas[0]
    assert not destino.exists()
