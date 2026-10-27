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


# ===================================================================
# FASE 2 — O RETORNO (27/10/2026)
#
# O desenvolvimento responde em `retorno/of-0035.md`; a produção importa como
# nota do desenvolvimento. Nada aqui fecha problema, e quem é mais novo vence.
# ===================================================================

EM = "2026-10-28T14:00:00"
DEPOIS_DO_EM = "2026-10-28T15:00:00"
NOTA_DEV = "Corrigido na tela do caixa; tests/test_x.py; PR #60."


def _exportado(db, pasta: Path, *ids: int) -> None:
    PS.exportar(db, pasta, agora=AGORA, ambiente="OFICIAL")
    for i in ids:
        assert (pasta / "problemas" / f"of-{i:04d}.md").is_file()


def _responder(pasta: Path, problema_id: int, **kw) -> Path:
    kw.setdefault("estado", "NECESSARIO_TESTE")
    kw.setdefault("nota", NOTA_DEV)
    kw.setdefault("prova", "tests/test_x.py")
    kw.setdefault("agora", EM)
    return PS.responder(pasta, f"of-{problema_id:04d}", **kw)


def _importar(db, pasta: Path) -> dict:
    return PS.importar(db, pasta, agora=DEPOIS_DO_EM, ambiente="OFICIAL")


def _linha(db, problema_id: int) -> dict:
    return {p["id"]: p for p in _tabela(db)}[problema_id]


def _auditorias(db, acao: str, problema_id: int) -> list[dict]:
    with db.connect() as con:
        return [dict(x) for x in banco(con).ler(
            "SELECT * FROM audit_logs WHERE action=%s AND entity_id=%s ORDER BY id",
            (acao, problema_id))]


def _retorno_valido(problema_id: int, impressao: str, **kw) -> str:
    dados = {"ambiente": "OFICIAL", "id": problema_id, "impressao": impressao,
             "estado": "NECESSARIO_TESTE", "em": EM, "prova": "tests/test_x.py",
             "reproducao": "", "nota": NOTA_DEV}
    dados.update(kw)
    return PS.texto_do_retorno(dados)


def test_ida_e_volta_grava_a_nota_e_nao_fecha(db, com_cpf, tmp_path):
    _exportado(db, tmp_path, com_cpf)
    situacao = _linha(db, com_cpf)["situacao"]
    _responder(tmp_path, com_cpf)
    r = _importar(db, tmp_path)
    assert r["gravados"] == [f"of-{com_cpf:04d}.md"] and not r["recusados"]
    linha = _linha(db, com_cpf)
    assert linha["nota_dev"] == NOTA_DEV
    assert linha["nota_dev_estado"] == "NECESSARIO_TESTE"
    assert linha["nota_dev_prova"] == "tests/test_x.py"
    assert linha["nota_dev_em"] == EM
    assert linha["nota_dev_por"] == PS.POR_DA_SINCRONIA
    assert linha["situacao"] == situacao                  # não fechou
    audit = _auditorias(db, "AJUDA_PROBLEMA_NOTA_DEV_SINCRONIA", com_cpf)
    assert len(audit) == 1
    assert audit[0]["agente"] == PS.ASSINATURA
    assert NOTA_DEV not in (audit[0]["details"] or "")   # o texto não vai
    # e a próxima exportação mostra o estado do retorno
    PS.exportar(db, tmp_path, agora=AGORA, ambiente="OFICIAL")
    assert "nota_dev_estado: NECESSARIO_TESTE" in (
        tmp_path / "problemas" / f"of-{com_cpf:04d}.md").read_text(encoding="utf-8")


def test_importar_duas_vezes_da_iguais_e_nao_audita_de_novo(db, com_cpf, tmp_path):
    _exportado(db, tmp_path, com_cpf)
    _responder(tmp_path, com_cpf)
    _importar(db, tmp_path)
    segunda = _importar(db, tmp_path)
    assert segunda["gravados"] == [] and segunda["iguais"] == 1
    assert len(_auditorias(db, "AJUDA_PROBLEMA_NOTA_DEV_SINCRONIA", com_cpf)) == 1


def test_a_nota_da_tela_mais_nova_vence_o_arquivo(db, com_cpf, tmp_path):
    _exportado(db, tmp_path, com_cpf)
    _responder(tmp_path, com_cpf)
    with db.transaction() as con:
        AP.anotar_desenvolvimento(con, com_cpf, nota="Escrita pela tela depois.",
                                  estado="EM_ANDAMENTO", agora=DEPOIS_DO_EM,
                                  por=LOGIN)
    r = _importar(db, tmp_path)
    assert r["mais_antigos"] == [f"of-{com_cpf:04d}.md"] and r["gravados"] == []
    assert _linha(db, com_cpf)["nota_dev"] == "Escrita pela tela depois."


def test_o_mesmo_em_com_outro_conteudo_e_recusado(db, com_cpf, tmp_path):
    _exportado(db, tmp_path, com_cpf)
    _responder(tmp_path, com_cpf)
    _importar(db, tmp_path)
    _responder(tmp_path, com_cpf, nota="Outra nota, mesmo em.")
    r = _importar(db, tmp_path)
    assert "mudou sem mudar" in r["recusados"][0]["porque"]
    assert _linha(db, com_cpf)["nota_dev"] == NOTA_DEV


def test_impressao_trocada_e_recusada_e_os_outros_entram(db, com_cpf, tmp_path):
    outro = _anotar(db, titulo="KeyError na tela do protocolo", onde="protocolo")
    _exportado(db, tmp_path, com_cpf, outro)
    impressao_do_outro = _linha(db, outro)["impressao"]
    pasta = tmp_path / "retorno"
    pasta.mkdir()
    (pasta / f"of-{com_cpf:04d}.md").write_text(
        _retorno_valido(com_cpf, impressao_do_outro), encoding="utf-8")
    _responder(tmp_path, outro)
    r = _importar(db, tmp_path)
    assert [x["arquivo"] for x in r["recusados"]] == [f"of-{com_cpf:04d}.md"]
    assert "impressão" in r["recusados"][0]["porque"]
    assert r["gravados"] == [f"of-{outro:04d}.md"]
    assert _linha(db, com_cpf)["nota_dev"] is None
    assert PS.conferir_retorno(tmp_path)["recusados"][0]["arquivo"] == (
        f"of-{com_cpf:04d}.md")


def test_o_retorno_de_outro_ambiente_e_ignorado_e_contado(db, com_cpf, tmp_path):
    pasta = tmp_path / "retorno"
    pasta.mkdir()
    (pasta / "sb-0012.md").write_text(
        _retorno_valido(12, "abc", ambiente="SANDBOX"), encoding="utf-8")
    r = _importar(db, tmp_path)
    assert r["outro_ambiente"] == 1 and not r["recusados"] and not r["gravados"]


@pytest.mark.parametrize("nome, texto, frase", [
    ("of-0035.md", _retorno_valido(35, "abc").replace("em:", "quando:"),
     "chave desconhecida"),
    ("of-0035.md", _retorno_valido(35, "abc").replace("---\n", "", 1),
     "não começa com"),
    ("of-35.md", _retorno_valido(35, "abc"), "padrão"),
    ("of-0036.md", _retorno_valido(35, "abc"), "id «35»"),
    ("sb-0035.md", _retorno_valido(35, "abc"), "ambiente"),
    ("of-0035.md", _retorno_valido(35, "abc", estado="ATENDIDO", prova=""),
     "onde conferir"),
    ("of-0035.md", _retorno_valido(35, "abc", estado="QUASE"),
     "Não conheço o estado"),
    ("of-0035.md", _retorno_valido(35, "abc", em="amanhã"), "data e hora"),
    ("of-0035.md", _retorno_valido(35, "abc", reproducao="TALVEZ"),
     "reprodução"),
])
def test_o_formato_errado_e_recusado_com_motivo(nome, texto, frase):
    with pytest.raises(AP.ProblemaError) as erro:
        PS.ler_retorno(texto, nome)
    assert frase in str(erro.value)


def test_nota_com_dado_de_pessoa_e_recusada_e_a_de_desenvolvimento_passa():
    with pytest.raises(AP.ProblemaError) as erro:
        PS.ler_retorno(_retorno_valido(35, "abc", nota=f"Era o CPF {CPF}."),
                       "of-0035.md")
    assert "CPF" in str(erro.value)
    comum = "tests/test_x.py; PR #60; corrigido em 28/10/2026"
    assert PS.ler_retorno(_retorno_valido(35, "abc", nota=comum),
                          "of-0035.md")["nota"] == comum


def test_responder_e_conferir_nao_precisam_do_banco(db, com_cpf, tmp_path,
                                                    monkeypatch):
    pasta = tmp_path / "repo"
    _exportado(db, pasta, com_cpf)
    monkeypatch.delenv("CG_PG_DSN", raising=False)
    monkeypatch.delenv("CG_PG_SCHEMA", raising=False)
    nota = tmp_path / "nota.txt"
    nota.write_text("Primeira linha.\nSegunda linha.\n", encoding="utf-8")
    assert PS.main(["responder", "--pasta", str(pasta),
                    "--arquivo", f"of-{com_cpf:04d}", "--estado", "EM_ANDAMENTO",
                    "--nota-arquivo", str(nota)]) == 0
    assert "Segunda linha." in (
        pasta / "retorno" / f"of-{com_cpf:04d}.md").read_text(encoding="utf-8")
    assert PS.main(["conferir-retorno", "--pasta", str(pasta)]) == 0


def test_importar_recusa_sem_banco(db, com_cpf, ambiente_da_casa, tmp_path,
                                   monkeypatch):
    _exportado(db, tmp_path, com_cpf)
    _responder(tmp_path, com_cpf)
    monkeypatch.delenv("CG_PG_DSN", raising=False)
    assert PS.main(["importar", "--pasta", str(tmp_path)]) == 2
    monkeypatch.undo()
    assert _linha(db, com_cpf)["nota_dev"] is None


def test_a_reproducao_do_retorno_muda_a_coluna_e_audita(db, com_cpf, tmp_path):
    _exportado(db, tmp_path, com_cpf)
    _responder(tmp_path, com_cpf, reproducao="AQUI_FICTICIOS")
    _importar(db, tmp_path)
    assert _linha(db, com_cpf)["reproducao"] == "AQUI_FICTICIOS"
    audit = _auditorias(db, "AJUDA_PROBLEMA_REPRODUCAO", com_cpf)
    assert len(audit) == 1 and audit[0]["agente"] == PS.ASSINATURA


def test_arquivo_grande_e_recusado(db, com_cpf, tmp_path):
    _exportado(db, tmp_path, com_cpf)
    impressao = _linha(db, com_cpf)["impressao"]
    pasta = tmp_path / "retorno"
    pasta.mkdir()
    (pasta / f"of-{com_cpf:04d}.md").write_text(
        _retorno_valido(com_cpf, impressao, nota="x" * (17 * 1024)),
        encoding="utf-8")
    r = _importar(db, tmp_path)
    assert "KB" in r["recusados"][0]["porque"]
    assert _linha(db, com_cpf)["nota_dev"] is None


def test_dry_run_do_importar_nao_grava(db, com_cpf, ambiente_da_casa, tmp_path,
                                       capsys):
    _exportado(db, tmp_path, com_cpf)
    _responder(tmp_path, com_cpf)
    assert PS.main(["importar", "--pasta", str(tmp_path), "--dry-run"]) == 0
    saida = capsys.readouterr().out
    assert "gravaria: 1" in saida and "nada foi gravado" in saida
    assert _linha(db, com_cpf)["nota_dev"] is None
    assert not _auditorias(db, "AJUDA_PROBLEMA_NOTA_DEV_SINCRONIA", com_cpf)


def test_a_regra_da_nota_mora_num_lugar_so(db, com_cpf):
    """`anotar_desenvolvimento` continua recusando com as mesmas frases — e
    são as de `conferir_nota_dev`, que o retorno também usa."""
    casos = [({"estado": "QUASE", "nota": "x", "prova": ""}, "Não conheço o estado"),
             ({"estado": "EM_ANDAMENTO", "nota": "  ", "prova": ""},
              "não pode ficar vazia"),
             ({"estado": "ATENDIDO", "nota": "feito", "prova": ""}, "onde conferir")]
    for kw, frase in casos:
        with pytest.raises(AP.ProblemaError) as pela_funcao:
            AP.conferir_nota_dev(kw["nota"], kw["estado"], kw["prova"])
        with db.transaction() as con, pytest.raises(AP.ProblemaError) as pela_tela:
            AP.anotar_desenvolvimento(con, com_cpf, agora=AGORA, **kw)
        assert frase in str(pela_funcao.value)
        assert str(pela_tela.value) == str(pela_funcao.value)
