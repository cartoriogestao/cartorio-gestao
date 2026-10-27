"""A EXPORTAÇÃO DOS PROBLEMAS PARA O DESENVOLVIMENTO — fase 1 da sincronia.

O que se prova aqui é o que `problemas_sincronia` promete nunca fazer: deixar
sair dado de pessoa, apagar arquivo, gravar na tabela, criar banco. Só dados
fictícios da casa.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ajuda_privacidade as PRIV                   # noqa: E402
import ajuda_problemas as AP                       # noqa: E402
import banco_pg                                    # noqa: E402
import problemas_sincronia as PS                   # noqa: E402
from bd_nativo import banco                        # noqa: E402

AGORA = "2026-10-27T10:15:00"
CPF = "000.000.001-91"
NOME = "MARIO EXEMPLO DOS SANTOS"
LOGIN = "mario.exemplo"
NOTA = "Corrigido no desenvolvimento e conferido no balcão."


def _anotar(db, **kw) -> int:
    kw.setdefault("origem", "ERRO_DE_TELA")
    kw.setdefault("agora", AGORA)
    with db.transaction() as con:
        return AP.anotar(con, **kw)["id"]


def _tabela(db) -> list[dict]:
    with db.connect() as con:
        return [dict(x) for x in banco(con).ler(
            "SELECT * FROM aj_problemas ORDER BY id")]


@pytest.fixture
def db(cg_casa):
    return cg_casa["db"]


@pytest.fixture
def com_cpf(db) -> int:
    """Um problema que estourou gravando uma pessoa — o caso que a máscara
    existe para pegar."""
    return _anotar(db, titulo="IntegrityError ao gravar a parte",
                   detalhe=f"INSERT ... ('{NOME}', '{CPF}')", onde="caixa",
                   usuario=NOME, criado_por=LOGIN, versao="3.7.4")


def _arquivos(pasta: Path) -> dict[str, str]:
    return {str(p.relative_to(pasta)).replace("\\", "/"):
            p.read_text(encoding="utf-8")
            for p in pasta.rglob("*") if p.is_file()}


# ------------------------------------------------------------ a máscara


def test_a_mascara_tira_o_cpf_e_o_nome(db, com_cpf, tmp_path):
    r = PS.exportar(db, tmp_path, agora=AGORA, ambiente="OFICIAL")
    assert not r["recusados"]
    texto = (tmp_path / "problemas" / f"of-{com_cpf:04d}.md").read_text(
        encoding="utf-8")
    assert CPF not in texto
    assert NOME not in texto and "MARIO" not in texto
    assert "IntegrityError" in texto        # o ponto do programa continua


def test_problema_que_a_mascara_recusa_nao_sai_e_os_outros_seguem(
        db, com_cpf, tmp_path, monkeypatch):
    outro = _anotar(db, titulo="KeyError na tela do protocolo", onde="protocolo")
    verdadeira = PRIV.sanitizar_texto

    def recusa_o_primeiro(texto):
        if f"### #{com_cpf} " in str(texto):
            raise PRIV.PrivacidadeError("sobrou dado depois de mascarar")
        return verdadeira(texto)

    monkeypatch.setattr(PRIV, "sanitizar_texto", recusa_o_primeiro)
    r = PS.exportar(db, tmp_path, agora=AGORA, ambiente="OFICIAL")
    assert [x["id"] for x in r["recusados"]] == [com_cpf]
    assert "sobrou dado" in r["recusados"][0]["porque"]
    assert not (tmp_path / "problemas" / f"of-{com_cpf:04d}.md").exists()
    assert (tmp_path / "problemas" / f"of-{outro:04d}.md").is_file()
    assert f"of-{com_cpf:04d}" not in (tmp_path / "INDICE.md").read_text(
        encoding="utf-8")


def test_nenhum_arquivo_leva_login_nem_nome_de_quem_usou(db, com_cpf, tmp_path):
    PS.exportar(db, tmp_path, agora=AGORA, ambiente="OFICIAL")
    linha = next(p for p in _tabela(db) if p["id"] == com_cpf)
    assert linha["criado_por"] == LOGIN and linha["ultimo_usuario"] == NOME
    for nome, texto in _arquivos(tmp_path).items():
        assert LOGIN not in texto, nome
        assert NOME not in texto, nome


# ------------------------------------------------------- o arquivo e a pasta


def test_o_nome_do_arquivo_diz_o_ambiente():
    assert PS.nome_do_arquivo({"id": 35}, "OFICIAL") == "of-0035.md"
    assert PS.nome_do_arquivo({"id": 12}, "SANDBOX") == "sb-0012.md"
    with pytest.raises(AP.ProblemaError):
        PS.nome_do_arquivo({"id": 1}, "OUTRO")


def test_o_cabecalho_e_uma_informacao_por_linha(db, com_cpf):
    p = next(p for p in _tabela(db) if p["id"] == com_cpf)
    texto = PS.texto_do_arquivo(p, "OFICIAL", None)
    cabecalho = texto.split("---")[1].strip().splitlines()
    assert [x.split(":")[0] for x in cabecalho] == [
        "ambiente", "id", "impressao", "origem", "situacao", "reproducao",
        "versao", "vezes", "ultima_em", "nota_dev_estado"]
    assert f"id: {com_cpf}" in cabecalho
    assert "nota_dev_estado: (vazio)" in cabecalho


def test_exportar_duas_vezes_nao_regrava_nada(db, com_cpf, tmp_path):
    _anotar(db, titulo="KeyError na tela do protocolo", onde="protocolo")
    primeira = PS.exportar(db, tmp_path, agora=AGORA, ambiente="OFICIAL")
    assert len(primeira["escritos"]) == 3          # dois problemas e o índice
    datas = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*.md")}
    segunda = PS.exportar(db, tmp_path, agora=AGORA, ambiente="OFICIAL")
    assert segunda["escritos"] == []
    assert segunda["iguais"] == 2
    assert {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*.md")} == datas


def test_exportar_nunca_apaga(db, com_cpf, tmp_path):
    sobra = tmp_path / "problemas" / "of-9999.md"
    sobra.parent.mkdir(parents=True)
    sobra.write_text("problema que sumiu do banco\n", encoding="utf-8")
    PS.exportar(db, tmp_path, agora=AGORA, ambiente="OFICIAL")
    assert sobra.read_text(encoding="utf-8") == "problema que sumiu do banco\n"


def test_exportar_so_le_o_banco(db, com_cpf, tmp_path):
    antes = _tabela(db)
    PS.exportar(db, tmp_path, agora=AGORA, ambiente="OFICIAL")
    assert _tabela(db) == antes


def test_vao_os_abertos_e_os_resolvidos_dos_ultimos_trinta_dias(db, tmp_path):
    aberto = _anotar(db, titulo="Erro A na tela", onde="a")
    recente = _anotar(db, titulo="Erro B na tela", onde="b")
    antigo = _anotar(db, titulo="Erro C na tela", onde="c")
    with db.transaction() as con:
        AP.fechar(con, recente, agora="2026-10-20T09:00:00", usuario=LOGIN,
                  nota=NOTA)
        AP.fechar(con, antigo, agora="2026-08-01T09:00:00", usuario=LOGIN,
                  nota=NOTA)
    PS.exportar(db, tmp_path, agora=AGORA, ambiente="OFICIAL")
    pasta = tmp_path / "problemas"
    assert (pasta / f"of-{aberto:04d}.md").is_file()
    assert (pasta / f"of-{recente:04d}.md").is_file()
    assert not (pasta / f"of-{antigo:04d}.md").exists()


def test_o_indice_lista_os_arquivos_com_a_reproducao(db, com_cpf, tmp_path):
    conf = _anotar(db, origem="CONFERENCIA", titulo="Chave órfã no banco",
                   onde="conferencia")
    r = PS.exportar(db, tmp_path, agora=AGORA, ambiente="OFICIAL")
    assert "INDICE.md" in r["escritos"]
    indice = (tmp_path / "INDICE.md").read_text(encoding="utf-8")
    assert f"of-{com_cpf:04d}.md" in indice and f"of-{conf:04d}.md" in indice
    assert AP.REPRODUCOES["A_CLASSIFICAR"] in indice
    assert AP.REPRODUCOES["SO_PRODUCAO_DADOS"] in indice
    assert CPF not in indice


# ---------------------------------------------------------- a reprodução


def test_a_reproducao_nasce_pela_origem_e_se_classifica(db):
    conf = _anotar(db, origem="CONFERENCIA", titulo="Chave órfã no banco",
                   onde="conferencia")
    rel = _anotar(db, origem="RELATADO", titulo="A certidão saiu torta",
                  onde="certidao")
    linhas = {p["id"]: p for p in _tabela(db)}
    assert linhas[conf]["reproducao"] == "SO_PRODUCAO_DADOS"
    assert linhas[rel]["reproducao"] == "A_CLASSIFICAR"
    # a linha antiga, sem valor, conta como «a classificar»
    assert AP.reproducao_de({"reproducao": None}) == "A_CLASSIFICAR"

    with db.transaction() as con, pytest.raises(AP.ProblemaError) as erro:
        AP.classificar_reproducao(con, rel, "TALVEZ", agora=AGORA, por=LOGIN)
    assert "TALVEZ" in str(erro.value)

    with db.transaction() as con:
        AP.classificar_reproducao(con, rel, "aqui_ficticios", agora=AGORA,
                                  por=LOGIN)
    depois = {p["id"]: p for p in _tabela(db)}[rel]
    assert depois["reproducao"] == "AQUI_FICTICIOS"
    assert depois["situacao"] == linhas[rel]["situacao"]   # não mexe nela
    bloco = "\n".join(AP._bloco_do_problema(depois, None))
    assert f"- **Reprodução**: {AP.REPRODUCOES['AQUI_FICTICIOS']}" in bloco
    assert bloco.index("**Situação**") < bloco.index("**Reprodução**")


# ------------------------------------------------------- a linha de comando


@pytest.fixture
def ambiente_da_casa(cg_casa, monkeypatch):
    """O ambiente que o servidor teria: o DSN de teste e o schema do banco
    deste módulo, dito por `CG_PG_SCHEMA`."""
    if not banco_pg.ativo():
        pytest.skip("a ferramenta só abre o PostgreSQL")
    monkeypatch.delenv("CG_PG_SCHEMA", raising=False)
    schema = banco_pg.schema_do_caminho(cg_casa["banco"])
    monkeypatch.setenv("CG_PG_SCHEMA", schema)
    monkeypatch.setenv("CARTORIO_GESTAO_DATA", str(cg_casa["dados"]))
    return schema


def test_dry_run_mostra_e_nao_escreve(db, com_cpf, ambiente_da_casa, tmp_path,
                                      capsys):
    assert PS.main(["exportar", "--pasta", str(tmp_path), "--dry-run"]) == 0
    assert list(tmp_path.iterdir()) == []
    saida = capsys.readouterr().out
    assert f"of-{com_cpf:04d}.md" in saida and "nada foi escrito" in saida


def test_classificar_grava_a_auditoria_assinada_pela_ferramenta(
        db, com_cpf, ambiente_da_casa):
    assert PS.main(["classificar", "--id", str(com_cpf),
                    "--valor", "SO_PRODUCAO_EQUIPAMENTO", "--por", LOGIN]) == 0
    with db.connect() as con:
        linha = banco(con).um(
            """SELECT * FROM audit_logs WHERE action='AJUDA_PROBLEMA_REPRODUCAO'
                AND entity_id=%s ORDER BY id DESC LIMIT 1""", (com_cpf,))
    assert linha["username_snapshot"] == PS.ASSINATURA
    assert linha["agente"] == PS.ASSINATURA and linha["a_mando_de"] == LOGIN
    assert {p["id"]: p for p in _tabela(db)}[com_cpf]["reproducao"] == (
        "SO_PRODUCAO_EQUIPAMENTO")


def test_classificar_recusa_valor_fora_do_vocabulario(db, com_cpf,
                                                      ambiente_da_casa, capsys):
    assert PS.main(["classificar", "--id", str(com_cpf), "--valor", "TALVEZ",
                    "--por", LOGIN]) == 1
    assert "TALVEZ" in capsys.readouterr().err


@pytest.mark.parametrize("variavel", ["CG_PG_DSN", "CG_PG_SCHEMA"])
def test_recusa_sem_a_variavel_do_banco(ambiente_da_casa, monkeypatch,
                                        tmp_path, capsys, variavel):
    monkeypatch.delenv(variavel, raising=False)
    assert PS.main(["exportar", "--pasta", str(tmp_path)]) == 2
    assert variavel in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_recusa_schema_que_nao_existe_e_nao_o_cria(ambiente_da_casa,
                                                   monkeypatch, tmp_path,
                                                   capsys, cg_casa):
    monkeypatch.setenv("CG_PG_SCHEMA", "cg_sincronia_nao_existe")
    assert not banco_pg.schema_existe(cg_casa["banco"])
    assert PS.main(["exportar", "--pasta", str(tmp_path)]) == 2
    assert "cg_sincronia_nao_existe" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []
    assert not banco_pg.schema_existe(cg_casa["banco"])   # nada nasceu
