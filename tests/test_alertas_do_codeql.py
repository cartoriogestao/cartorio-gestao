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


# ------------------------------------- as expressões do PR #80 (28/10/2026)
# As réguas antigas, para comparar: as novas têm de dar exatamente o mesmo.

import random  # noqa: E402
import re  # noqa: E402

import contato_do_cliente as CC  # noqa: E402
import rc_modelos_do_livro as RML  # noqa: E402

_EMAIL_ANTIGO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _limpar_antigo(texto):
    texto = re.sub(r"\s*\n\s*", " ", texto)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    texto = re.sub(r"\s+([,.;:])", r"\1", texto)
    return texto.strip()


def _sorteados(letras, quantos=4000, semente=80):
    sorte = random.Random(semente)
    for _ in range(quantos):
        yield "".join(sorte.choice(letras) for _ in range(sorte.randint(0, 14)))


@pytest.mark.parametrize("texto", [
    "a@b.c", "nome@provedor.com.br", "a@.c", "a@b.", "a@bc", "@b.c", "a@@b.c",
    "a@b@c.d", "a b@c.d", "a@b .c", "a@b.c\t", "ä@ç.ö", "a@b..c", "a@b.c.",
])
def test_o_email_aceita_e_recusa_como_antes(texto):
    assert CC._email_completo(texto) == bool(_EMAIL_ANTIGO.match(texto))


def test_o_email_sorteado_bate_com_a_regua_antiga():
    for texto in _sorteados("a.@ b\t"):
        if texto == texto.strip():
            assert CC._email_completo(texto) == bool(_EMAIL_ANTIGO.match(texto)), texto


def test_o_limpar_do_livro_sorteado_bate_com_o_antigo():
    for texto in _sorteados("a \n\t,.;:\r"):
        assert RML.limpar(texto) == _limpar_antigo(texto), repr(texto)


def test_brancos_longos_nao_travam():
    inicio = time.monotonic()
    RML.limpar("a" + " " * 50_000 + "b")
    CC._email_completo("a@" + "." * 50_000 + "@")
    assert time.monotonic() - inicio < 1.0


# ------------------------------------- os três alertas que ficaram (29/10/2026)

import rc_anotacao_crc as CRC  # noqa: E402
from seguranca_web import destino_interno  # noqa: E402

# A forma de antes, para comparar: o CodeQL acusou o `.+?` contra o
# `\s{2,}` e o `^\s*` que atravessa linha em branco (alerta #189).
_TITULO_ANTIGO = re.compile(
    r"^\s*(Comunica[cç][aã]o\s+de\s+.+?)(?:\s{2,}|\n|$)", re.I | re.M)


def _titulo_antigo(texto):
    m = _TITULO_ANTIGO.search(texto)
    return (m.group(1), m.end()) if m else None


def test_o_titulo_da_crc_sorteado_bate_com_a_expressao_antiga():
    pecas = ["Comunicação de", "comunicacao de", "COMUNICAÇÃO DE", " ", "  ",
             "\n", "\n\n", "\t", "\r\n", "<", "<b>", "X", "Nascimento",
             "\xa0", "a b"]
    sorteio = random.Random(189)
    for _ in range(20_000):
        texto = "".join(sorteio.choice(pecas)
                        for _ in range(sorteio.randint(0, 12)))
        assert CRC._titulo_no_inicio_da_linha(texto) == _titulo_antigo(texto), \
            repr(texto)


def test_o_titulo_da_crc_nao_trava_em_linhas_em_branco():
    # Medido em 29/10/2026: a expressão antiga levava 9,5 s neste texto.
    inicio = time.monotonic()
    CRC._titulo_no_inicio_da_linha("\n" * 20_000 + "x")
    CRC._titulo_no_inicio_da_linha("comunicacao de " + " " * 20_000 + "\n")
    assert time.monotonic() - inicio < 1.0


@pytest.mark.parametrize("pedido,vai", [
    ("/ajuda", "/ajuda"), ("/ajuda?vista=todos#problema-8",
                           "/ajuda?vista=todos#problema-8"),
    ("//fora.exemplo", "P"), ("/\fora.exemplo", "P"), ("/\t/fora", "P"),
    ("http://fora.exemplo", "P"), ("javascript:alert(1)", "P"),
    ("ajuda", "P"), ("", "P"), (None, "P"), ("/a\x7fb", "P"),
])
def test_o_volte_para_continua_so_dentro_da_casa(pedido, vai):
    assert destino_interno(pedido, "P") == vai


# --------------------------- o código da comunicação da CRC (#274, 29/10/2026)

_CODIGO_ANTIGO = re.compile(r"C[oó]digo\s+da\s+comunica[cç][aã]o\s*:?\s*(\d+)",
                            re.I | re.S)
_CODIGO_NOVO = re.compile(r"C[oó]digo\s+da\s+comunica[cç][aã]o\s*(?::\s*)?(\d+)",
                          re.I | re.S)


def test_o_codigo_da_comunicacao_casa_como_antes():
    sorte = random.Random(274)
    pedacos = ["Código da comunicação", "codigo da comunicacao", " ", "\n", ":",
               "12345", "x", "  :  ", "\t"]
    for _ in range(4000):
        texto = "".join(sorte.choice(pedacos) for _ in range(sorte.randint(0, 8)))
        a, b = _CODIGO_ANTIGO.search(texto), _CODIGO_NOVO.search(texto)
        assert (a and (a.span(), a.group(1))) == (b and (b.span(), b.group(1))), repr(texto)
        assert _CODIGO_ANTIGO.split(texto, maxsplit=1) == \
            _CODIGO_NOVO.split(texto, maxsplit=1), repr(texto)


def test_brancos_depois_do_codigo_nao_travam():
    import rc_anotacao_crc as CRC
    inicio = time.monotonic()
    CRC._pegar(_CODIGO_NOVO.pattern, "codigo da comunicacao" + " " * 50_000 + "x")
    assert time.monotonic() - inicio < 1.0
