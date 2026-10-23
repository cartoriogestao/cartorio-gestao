# -*- coding: utf-8 -*-
"""As ferramentas de `tools/` do lote L021 abrem o banco PELA PORTA (`banco_pg.conectar`).

O QUE A REVISÃO DO L021 ACHOU (17/10/2026)

    `tools/importar_ficha_de_abertura.py` não rodava: o `from bd_nativo import
    banco` do topo ficava escondido pela variável `banco` (o caminho do
    arquivo) dentro de `main`, e `banco(con)` virava `PosixPath(...)(con)` —
    TypeError antes de ler a primeira linha.

    E as ferramentas do lote abriam o banco com `sqlite3.connect` e o passavam
    a módulo que já é nativo. Dentro do sistema isso funciona por acaso:
    `Database()` instala o desvio que manda o `sqlite3.connect` do banco da casa
    ao PostgreSQL. Fora dele — o Agendador, a linha de comando — ninguém o
    instala, e o acesso nativo recusa o `sqlite3` cru (`BancoNaoEPostgres`).
    O fixture `fora_do_sistema` devolve o `sqlite3.connect` de fábrica para
    medir exatamente isso.

    `tools/encerrar_cronometros_esquecidos.py` perdera o `BEGIN IMMEDIATE` sem
    ganhar trava: ler os cronômetros abertos e fechá-los deixava de ser um
    passo só, e duas execuções ao mesmo tempo fechariam o mesmo registro duas
    vezes.

Os dados são fictícios: nomes «DE TAL EXEMPLO» e CPFs da lista de fictícios
(`tests/fixtures/anti_vazamento/documentos_ficticios.txt`).
"""
from __future__ import annotations

import sqlite3
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import banco_pg  # noqa: E402
import produtividade as PR  # noqa: E402
from bd_nativo import banco  # noqa: E402
from tools import analisar_remessa_cra_homologacao as ANALISAR  # noqa: E402
from tools import encerrar_cronometros_esquecidos as ENCERRAR  # noqa: E402
from tools import importar_ficha_de_abertura as FICHA  # noqa: E402

pytestmark = pytest.mark.skipif(
    not banco_pg.ativo(),
    reason="ferramenta nativa: só roda com o PostgreSQL ligado (CG_PG_DSN)")

SENHA = "Senha#12345"


@pytest.fixture()
def fora_do_sistema(monkeypatch):
    """O processo do Agendador e da linha de comando: ninguém montou
    `Database()`, e o `sqlite3.connect` é o de fábrica. Conferido em 17/10/2026:
    importar `produtividade` ou `tarefa_processo` não instala o desvio."""
    monkeypatch.setattr(sqlite3, "connect", banco_pg._CONNECT_ORIGINAL)


def _assunto_livre(chave: str) -> bool:
    """Outra conexão consegue a trava do assunto agora? Não espera por ela."""
    import psycopg
    with psycopg.connect(banco_pg.dsn(), autocommit=True) as outra:
        return bool(outra.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext(%s))", (chave,)).fetchone()[0])


# ------------------------------------------------- a ficha de abertura (.docx)

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

CORPO_DA_FICHA = (
    "DENOMINAÇÃO: Sítio Exemplo. LOCALIZAÇÃO: zona rural de Cidade Exemplo/MA. "
    "IMÓVEL: um terreno rural com área de 12,5000 ha, no lugar Exemplo. "
    "DESCRIÇÃO PERIMÉTRICA: começa no marco M-01 e volta a ele, fechando o "
    "polígono. SISTEMA GEODÉSICO: SIRGAS 2000. "
    "PROPRIETÁRIO: FULANO DE TAL EXEMPLO, brasileiro, casado, lavrador, inscrito "
    "no CPF 000.000.001-91, e sua esposa BELTRANA DE TAL EXEMPLO, brasileira, "
    "casada, do lar, inscrita no CPF 000.000.002-72, residentes e domiciliados "
    "em Cidade Exemplo/MA. TÍTULO DE ORIGEM: escritura pública de exemplo. "
    "REGISTRO ANTERIOR: Matrícula n° 9.900, Livro 2-X. "
    "ABERTURA/TRANSPORTE: aberta em 02/01/2026. PROTOCOLO: 99.999. "
    "EMOLUMENTOS E SELO: R$ 10,00, selo de exemplo.")


def _docx(caminho: Path, paragrafos: list[str]) -> Path:
    corpo = "".join(f"<w:p><w:r><w:t>{escape(p)}</w:t></w:r></w:p>" for p in paragrafos)
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("word/document.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   f'<w:document xmlns:w="{_W}"><w:body>{corpo}</w:body></w:document>')
    return caminho


def test_a_ficha_de_abertura_entra_pela_ferramenta(
        cg_db, cg_db_path, fora_do_sistema, monkeypatch, tmp_path):
    with cg_db.transaction() as con:
        mid = int(banco(con).escrever(
            "INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,"
            " tipo_ficha, teor, criado_em)"
            " VALUES (%s, '2-X', '2-X', 'ATIVO', 'ACERVO', %s, %s) RETURNING id",
            ("9901", "Teor de exemplo da ficha.", "2026-10-17T10:00:00"))[0]["id"])
    docx = _docx(tmp_path / "MATRICULA_9901_FICHA_ABERTURA.docx", [
        "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
        "MATRÍCULA N° 9.901",
        CORPO_DA_FICHA,
    ])
    monkeypatch.setenv("CARTORIO_GESTAO_COPIAS", str(tmp_path / "copias"))
    monkeypatch.setattr(sys, "argv", [
        "importar_ficha_de_abertura.py", str(cg_db_path),
        "--docx", str(docx), "--matricula", "9901", "--confirmar"])

    assert FICHA.main() == 0

    with cg_db.connect() as con:
        bd = banco(con)
        partes = bd.ler(
            "SELECT nome, documento_numero, proprietario_ativo, origem_chave"
            " FROM ri_partes WHERE matricula_id=%s ORDER BY id", (mid,))
        ficha = bd.um("SELECT * FROM ri_matriculas WHERE id=%s", (mid,))
        auditoria = bd.valor(
            "SELECT count(*) AS n FROM audit_logs"
            " WHERE action='RI_ABERTURA_IMPORTADA' AND entity_id=%s", (mid,))
    assert [(p["nome"], p["documento_numero"], p["proprietario_ativo"]) for p in partes] == [
        ("FULANO DE TAL EXEMPLO", "00000000191", 1),
        ("BELTRANA DE TAL EXEMPLO", "00000000272", 0),
    ]
    assert {p["origem_chave"] for p in partes} == {docx.name}
    assert (ficha["area_valor"], ficha["area_unidade"]) == ("12,5000", "ha")
    assert ficha["rural_urbano"] == "R"
    assert ficha["registro_anterior"].startswith("Matrícula n° 9.900")
    assert ficha["teor"] == "Teor de exemplo da ficha.", "o teor não se toca"
    assert int(auditoria) == 1
    copias = list((tmp_path / "copias").rglob("*.antes-da-abertura-*"))
    assert len(copias) == 1, "a cópia do banco não foi tirada antes de gravar"


# --------------------------------------------------- os cronômetros esquecidos

def test_o_cronometro_esquecido_fecha_pelo_script_e_com_o_assunto_travado(
        cg_db, cg_db_path, fora_do_sistema, monkeypatch, capsys):
    cg_db.create_user("beatriz", "BEATRIZ EXEMPLO DE SOUZA", SENHA, "USER")
    inicio = (datetime.now() - timedelta(days=3)).replace(
        hour=13, minute=26, second=0, microsecond=0)
    with cg_db.transaction() as con:
        uid = int(banco(con).valor(
            "SELECT id FROM users WHERE username=%s ORDER BY id LIMIT 1", ("beatriz",)))
        rid = PR.iniciar_cronometro(
            con, responsavel_user_id=uid, responsavel_nome="BEATRIZ EXEMPLO DE SOUZA",
            categoria=PR.CATEGORIA_PADRAO, tarefa="REGISTRO DE ÓBITO", agora=inicio)

    livre_durante_a_leitura = []
    original = PR.encerrar_esquecidos

    def espiao(con, **kw):
        livre_durante_a_leitura.append(_assunto_livre("prod_registros.cronometro"))
        return original(con, **kw)

    monkeypatch.setattr(PR, "encerrar_esquecidos", espiao)

    assert ENCERRAR.main(["--banco", str(cg_db_path), "--confirmar"]) == 0

    assert livre_durante_a_leitura == [False], (
        "o script leu os cronômetros abertos sem a trava do assunto: outra "
        "execução ao mesmo tempo fecharia o mesmo registro duas vezes")
    with cg_db.connect() as con:
        r = banco(con).um(
            "SELECT status, hora_fim, observacoes FROM prod_registros WHERE id=%s", (rid,))
    assert r["status"] == PR.STATUS_CONCLUIDA and r["hora_fim"] == "14:15"
    assert r["observacoes"].count(PR.MARCA_ENCERRAMENTO_AUTOMATICO) == 1
    assert "1 cronômetro(s) encerrado(s)." in capsys.readouterr().out


def test_sem_confirmar_o_script_nao_fecha_e_solta_a_trava(
        cg_db, cg_db_path, fora_do_sistema, capsys):
    cg_db.create_user("beatriz", "BEATRIZ EXEMPLO DE SOUZA", SENHA, "USER")
    inicio = (datetime.now() - timedelta(days=3)).replace(
        hour=13, minute=26, second=0, microsecond=0)
    with cg_db.transaction() as con:
        uid = int(banco(con).valor(
            "SELECT id FROM users WHERE username=%s ORDER BY id LIMIT 1", ("beatriz",)))
        rid = PR.iniciar_cronometro(
            con, responsavel_user_id=uid, responsavel_nome="BEATRIZ EXEMPLO DE SOUZA",
            categoria=PR.CATEGORIA_PADRAO, tarefa="REGISTRO DE ÓBITO", agora=inicio)

    assert ENCERRAR.main(["--banco", str(cg_db_path)]) == 0

    assert "1 seriam encerrados" in capsys.readouterr().out
    assert _assunto_livre("prod_registros.cronometro"), "a trava sobrou depois do script"
    with cg_db.connect() as con:
        r = banco(con).um("SELECT status, hora_fim FROM prod_registros WHERE id=%s", (rid,))
    assert r["status"] == PR.STATUS_EM_ANDAMENTO and not r["hora_fim"]


# ------------------------------------------------ a resposta da CRA (homologação)

def _resposta_da_cra(caminho: Path) -> Path:
    """A remessa de exemplo dos testes do protesto, no XML que a CRA devolve:
    cada linha de 600 posições vira um elemento com um atributo por campo."""
    linhas = (RAIZ / "tests" / "cra_remessa_exemplo.txt").read_bytes().decode(
        "latin-1").splitlines()
    tipo = {"0": ("hd", "h"), "1": ("tr", "t"), "9": ("tl", "t")}
    elementos = []
    for linha in linhas:
        tag, prefixo = tipo[linha[0]]
        pos, atributos = 0, []
        for i, largura in enumerate(ANALISAR.LARGURAS[tag], 1):
            atributos.append(f"{prefixo}{i:02}={quoteattr(linha[pos:pos + largura].rstrip())}")
            pos += largura
        elementos.append(f"<{tag} {' '.join(atributos)}/>")
    caminho.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<remessa>'
        "<nome_arquivo>B0011709.261</nome_arquivo>" + "".join(elementos)
        + "</remessa>\n", encoding="utf-8")
    return caminho


def test_a_conferencia_da_resposta_da_cra_chega_ao_banco(
        cg_db, cg_db_path, fora_do_sistema, tmp_path):
    resumo = ANALISAR.analisar(_resposta_da_cra(tmp_path / "resposta.xml"), cg_db_path)

    conferencia = resumo["conferencia_existente"]
    assert conferencia["ok"] is True, conferencia.get("erro")
    assert (conferencia["lotes"], conferencia["titulos"]) == (1, 1)
