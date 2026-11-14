"""O SUPERUSUÁRIO (docs/SUPERUSUARIO.md) — o que a prudência garante por
programa: o original guardado, o relatório, o «CONFIRMO», o reserva que não
grava, o segredo que não se lê; o posto único das três portas; a memória e o
diário que se acumulam; e a ponte que só atende o oficial.

Nada aqui fala com o Telegram, com a API nem com o PostgreSQL: a ponte recebe
um Telegram de mentira e um operador de mentira, e o `sql` recebe um `rodar`
de mentira. O Claude Code de verdade se prova com `python operador/ensaio.py`.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "operador"))

import bandeja as BANDEJA  # noqa: E402
import conhecimento as CONH  # noqa: E402
import guarda as GUARDA  # noqa: E402
import intervencao as INT  # noqa: E402
import ponte as PONTE  # noqa: E402
import posto as POSTO  # noqa: E402

SENHA = "Senha#12345"
OFICIAL = 1001      # número de usuário fictício do Telegram
ESTRANHO = 2002


@pytest.fixture
def casa(tmp_path, monkeypatch):
    """Um sistema de mentira (dois arquivos) e uma pasta de dados vazia."""
    sistema = tmp_path / "sistema"
    sistema.mkdir()
    (sistema / "VERSAO.txt").write_text("9.9.9\n", encoding="utf-8")
    (sistema / "modulo.py").write_bytes(b"def soma(a, b):\r\n    return a - b\r\n")
    (sistema / "outro.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setenv("OPERADOR_RAIZ", str(sistema))
    monkeypatch.setenv("CARTORIO_GESTAO_DATA", str(tmp_path / "dados"))
    for variavel in ("CG_PG_DSN", "CG_PG_SCHEMA", "CG_MODO_RESERVA", "OPERADOR_NOME",
                     "OPERADOR_AMBIENTE", "OPERADOR_PELA_PONTE", "OPERADOR_SAIDA",
                     "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        monkeypatch.delenv(variavel, raising=False)
    return sistema


# ---------------------------------------------------------------- o relatório

def test_o_original_fica_guardado_e_o_relatorio_traz_o_diff(casa):
    INT.abrir("a soma está subtraindo")
    assert INT.guardar([casa / "modulo.py"]) == ["modulo.py"]
    (casa / "modulo.py").write_bytes(b"def soma(a, b):\r\n    return a + b\r\n")
    INT.nota("o sinal estava trocado")
    dados = INT.fechar("troquei o sinal")
    pasta = INT.base() / "intervencoes" / dados["id"]
    assert (pasta / "antes" / "modulo.py").read_bytes().endswith(b"a - b\r\n")
    patch = (pasta / "codigo.patch").read_bytes()
    assert b"-    return a - b\r\n" in patch and b"+    return a + b\r\n" in patch
    relatorio = (pasta / "RELATORIO.md").read_text(encoding="utf-8")
    assert "a soma está subtraindo" in relatorio and "troquei o sinal" in relatorio
    assert "`modulo.py` (alterado)" in relatorio and "o sinal estava trocado" in relatorio
    assert "outro.py" not in relatorio
    assert INT.atual() is None


def test_guardar_duas_vezes_nao_troca_o_original_pela_versao_do_meio(casa):
    INT.guardar([casa / "outro.py"])
    (casa / "outro.py").write_text("X = 2\n", encoding="utf-8")
    assert INT.guardar([casa / "outro.py"]) == []
    (casa / "outro.py").write_text("X = 3\n", encoding="utf-8")
    dados = INT.fechar()
    patch = (INT.base() / "intervencoes" / dados["id"] / "codigo.patch").read_text(encoding="utf-8")
    assert "-X = 1" in patch and "+X = 3" in patch and "X = 2" not in patch


def test_o_que_mudou_pelo_shell_sem_guardar_aparece_no_relatorio(casa):
    INT.abrir("mexi por fora")
    (casa / "outro.py").write_text("X = 5\n", encoding="utf-8")
    (casa / "novo.py").write_text("Y = 1\n", encoding="utf-8")
    dados = INT.fechar()
    situacao = {m["arquivo"]: m for m in dados["mudancas"]}
    assert situacao["outro.py"]["com_diff"] is False
    assert situacao["novo.py"] == {"arquivo": "novo.py", "situacao": "criado", "com_diff": True}
    relatorio = (INT.base() / "intervencoes" / dados["id"] / "RELATORIO.md").read_text(encoding="utf-8")
    assert "SEM O ORIGINAL GUARDADO" in relatorio


def test_pedido_que_nao_mudou_nada_nao_deixa_relatorio(casa):
    INT.abrir("só uma pergunta")
    assert INT.fechar("respondi") is None
    assert INT.listar() == []


def test_rascunho_do_operador_e_arquivo_temporario_nao_se_guardam(casa, tmp_path):
    rascunho = INT.base() / "mudanca.sql"
    rascunho.write_text("SELECT 1;\n", encoding="utf-8")
    fora = tmp_path / "fora.py"            # a pasta do pytest é temporária
    fora.write_text("Z = 1\n", encoding="utf-8")
    assert INT.guardar([rascunho, fora]) == []
    assert INT.atual() is None


def test_arquivo_de_fora_do_sistema_e_guardado_e_listado_a_parte(casa, tmp_path, monkeypatch):
    """O ato de informática: o `.cmd` do serviço não é código da casa, mas a
    mudança nele tem de constar — sem entrar no patch nem na exportação."""
    monkeypatch.setattr(INT, "_pastas_de_rascunho", lambda: [INT.base()])
    servico = tmp_path / "servico" / "iniciar_servidor_servico.cmd"
    servico.parent.mkdir()
    servico.write_text("set CG_PORTA=8765\n", encoding="utf-8")
    assert GUARDA.decidir("Edit", {"file_path": str(servico)}) is None
    servico.write_text("set CG_PORTA=8766\n", encoding="utf-8")
    dados = INT.fechar("troquei a porta")
    assert dados["mudancas"] == []
    assert dados["de_fora_mudou"][0]["caminho"] == str(servico.resolve())
    pasta = INT.base() / "intervencoes" / dados["id"]
    assert (pasta / "codigo.patch").read_text(encoding="utf-8") == ""
    assert "+set CG_PORTA=8766" in (pasta / "fora_do_sistema.diff").read_text(encoding="utf-8")
    relatorio = (pasta / "RELATORIO.md").read_text(encoding="utf-8")
    assert "Fora da pasta do sistema" in relatorio and "iniciar_servidor_servico.cmd" in relatorio
    repositorio = tmp_path / "privado"
    repositorio.mkdir()
    levadas = INT.exportar(repositorio, mascarar=str)
    assert "fora_do_sistema.diff" not in [
        p.name for p in (repositorio / "intervencoes" / levadas[0]).iterdir()]


def test_arquivo_binario_de_fora_entra_na_lista_sem_despejar_bytes(casa, tmp_path, monkeypatch):
    monkeypatch.setattr(INT, "_pastas_de_rascunho", lambda: [INT.base()])
    pdf = tmp_path / "arquivos" / "certidao.pdf"
    pdf.parent.mkdir()
    assert GUARDA.decidir("Write", {"file_path": str(pdf)}) is None
    pdf.write_bytes(b"%PDF-1.7\x00\x01 binario")
    dados = INT.fechar("gerei a certidão")
    assert dados["de_fora_mudou"] == [
        {"caminho": str(pdf.resolve()), "situacao": "criado", "copia": ""}]
    assert not (INT.base() / "intervencoes" / dados["id"] / "fora_do_sistema.diff").exists()
    # e o arquivo de fora que foi aberto para editar e ficou igual não entra
    INT.abrir("só olhei")
    GUARDA.decidir("Edit", {"file_path": str(pdf)})
    assert INT.fechar("não mudei") is None


def test_os_comandos_ficam_no_relatorio_e_o_pedido_so_de_comando_nao_gera_um(casa):
    INT.abrir("reinicie o serviço")
    assert GUARDA.decidir("Bash", {"command": "launchctl kickstart -k gui/501/servidor"}) is None
    detalhes: dict = {}
    assert INT.fechar("reiniciei", detalhes) is None        # nada de código nem de banco
    assert [c["comando"] for c in detalhes["comandos"]] == ["launchctl kickstart -k gui/501/servidor"]
    assert INT.listar() == []
    # com mudança de código, os comandos entram no relatório
    INT.abrir("conserte")
    GUARDA.decidir("Bash", {"command": "python -m py_compile outro.py"})
    GUARDA.decidir("Edit", {"file_path": str(casa / "outro.py")})
    (casa / "outro.py").write_text("X = 7\n", encoding="utf-8")
    dados = INT.fechar("consertei")
    relatorio = (INT.base() / "intervencoes" / dados["id"] / "RELATORIO.md").read_text(encoding="utf-8")
    assert "Comandos de shell (1)" in relatorio and "py_compile outro.py" in relatorio


# ------------------------------------------------------------------ o ambiente

def test_o_arquivo_de_ambiente_e_lido_nas_tres_formas(tmp_path):
    arquivo = tmp_path / "servico.cmd"
    arquivo.write_text('@echo off\nrem comentario\nset CG_PG_SCHEMA=producao\n'
                       'set "CG_PG_DSN=host=127.0.0.1 port=5434 dbname=cartorio"\n'
                       'CG_MODO_RESERVA="1"\nexport CG_PG_BIN=/opt/pg/bin\ncd /d C:\\x\n',
                       encoding="utf-8")
    assert INT.ler_ambiente(arquivo) == {
        "CG_PG_SCHEMA": "producao", "CG_PG_DSN": "host=127.0.0.1 port=5434 dbname=cartorio",
        "CG_MODO_RESERVA": "1", "CG_PG_BIN": "/opt/pg/bin"}


def test_depois_de_assumir_o_operador_enxerga_que_o_reserva_grava(casa, tmp_path, monkeypatch):
    """O `emergencia.sh` troca o `reserva.env` e só reinicia o servidor. A
    ponte nasceu antes, com o ambiente de réplica: ela relê o arquivo."""
    env = tmp_path / "reserva.env"
    env.write_text("CG_MODO_RESERVA=1\nCG_PG_DSN=host=x user=cg_leitor\n", encoding="utf-8")
    monkeypatch.setenv("OPERADOR_AMBIENTE", str(env))
    monkeypatch.setenv("OPERADOR_NOME", "reserva")
    monkeypatch.setenv("CG_MODO_RESERVA", "1")
    monkeypatch.setenv("CG_PG_DSN", "host=x user=cg_leitor")
    assert INT.carregar_ambiente() == [] and INT.no_reserva()
    assert "só lê" in INT.situacao()
    env.write_text("CG_MODO_RESERVA=0\nCG_PG_DSN=host=x user=cg\n", encoding="utf-8")
    assert sorted(INT.carregar_ambiente()) == ["CG_MODO_RESERVA", "CG_PG_DSN"]
    assert not INT.no_reserva() and "ASSUMIU" in INT.situacao()


# --------------------------------------------------------------------- o banco

@pytest.mark.parametrize("sql, esperado", [
    ("DROP TABLE users", "DROP TABLE"),
    ("truncate settings", "TRUNCATE"),
    ("DELETE FROM users;", "DELETE sem WHERE"),
    ("UPDATE users SET active=0", "UPDATE sem WHERE"),
    ("ALTER TABLE users DROP COLUMN funcao", None),   # qualquer frase serve
    ("SELECT setval('seq', 1)", "SETVAL("),
    ("DELETE FROM users WHERE id=3", None),
    ("UPDATE users SET active=0 WHERE id=3", None),
    ("-- DROP TABLE users\nSELECT 1", None),
    ("ALTER TABLE users ADD COLUMN x TEXT", None),
])
def test_o_que_nao_tem_volta(sql, esperado):
    achado = INT.sem_volta(sql)
    if "DROP COLUMN" in sql:
        assert achado
    else:
        assert achado == esperado


def _rodar_de_mentira(chamadas):
    def rodar(comando, **argumentos):
        chamadas.append((comando, argumentos))
        return types.SimpleNamespace(returncode=0, stdout="UPDATE 1\n", stderr="")
    return rodar


@pytest.fixture
def com_banco(casa, monkeypatch):
    monkeypatch.setenv("CG_PG_DSN", "host=127.0.0.1 dbname=ficticio")
    monkeypatch.setenv("CG_PG_SCHEMA", "producao")
    monkeypatch.setattr(INT, "_binario", lambda nome: nome)
    monkeypatch.setattr(INT, "_auditar", lambda dados, mudancas: "não gravada: teste")
    arquivo = INT.base() / "mudanca.sql"
    arquivo.write_text("UPDATE settings SET value='x' WHERE key='k';\n", encoding="utf-8")
    return arquivo


def test_o_sql_faz_a_copia_antes_e_roda_numa_transacao_so(com_banco):
    chamadas = []
    r = INT.executar_sql(com_banco, ["settings"], "acerto de configuração",
                         rodar=_rodar_de_mentira(chamadas))
    comandos = [c for c, _ in chamadas]
    assert comandos[0][0] == "pg_dump" and "producao.settings" in comandos[0]
    assert comandos[1][0] == "psql" and "-1" in comandos[1] and "ON_ERROR_STOP=1" in comandos[1]
    assert r["codigo_de_saida"] == 0 and r["copia"] == "banco/01-antes.dump"
    dados = INT.fechar("acertei")
    relatorio = (INT.base() / "intervencoes" / dados["id"] / "RELATORIO.md").read_text(encoding="utf-8")
    assert "acerto de configuração" in relatorio and "banco/01-antes.dump" in relatorio


def test_sem_a_copia_nao_roda(com_banco):
    def falha(comando, **_):
        return types.SimpleNamespace(returncode=1, stdout="", stderr="sem permissão")
    with pytest.raises(INT.Recusa, match="não rodei"):
        INT.executar_sql(com_banco, ["settings"], "acerto", rodar=falha)


def test_sql_que_grava_exige_tabelas_e_motivo(com_banco):
    with pytest.raises(INT.Recusa, match="--tabelas"):
        INT.executar_sql(com_banco, [], "acerto", rodar=_rodar_de_mentira([]))
    with pytest.raises(INT.Recusa, match="--motivo"):
        INT.executar_sql(com_banco, ["settings"], "", rodar=_rodar_de_mentira([]))


def test_no_reserva_o_sql_que_grava_e_recusado(com_banco, monkeypatch):
    monkeypatch.setenv("CG_MODO_RESERVA", "1")
    chamadas = []
    with pytest.raises(INT.Recusa, match="RESERVA"):
        INT.executar_sql(com_banco, ["settings"], "acerto", rodar=_rodar_de_mentira(chamadas))
    assert chamadas == []


def test_o_que_nao_tem_volta_espera_o_confirmo(com_banco):
    com_banco.write_text("DELETE FROM settings;\n", encoding="utf-8")
    chamadas = []
    with pytest.raises(INT.Recusa, match="CONFIRMO"):
        INT.executar_sql(com_banco, ["settings"], "limpar", rodar=_rodar_de_mentira(chamadas))
    assert chamadas == []
    INT.registrar_confirmacao("CONFIRMO")
    r = INT.executar_sql(com_banco, ["settings"], "limpar", rodar=_rodar_de_mentira(chamadas))
    assert r["sem_volta"] == "DELETE sem WHERE" and len(chamadas) == 2


def test_a_confirmacao_vence(casa, monkeypatch):
    INT.registrar_confirmacao("CONFIRMO")
    assert INT.confirmacao_valida()
    agora = INT.time.time()
    monkeypatch.setattr(INT.time, "time", lambda: agora + INT.VALIDADE_DA_CONFIRMACAO + 1)
    assert not INT.confirmacao_valida()


def test_a_consulta_so_le_e_nao_deixa_relatorio(com_banco):
    chamadas = []
    codigo, saida = INT.consultar("SELECT count(*) FROM users WHERE role = 'UPDATE'",
                                  rodar=_rodar_de_mentira(chamadas))
    comando, argumentos = chamadas[0]
    assert codigo == 0 and comando[0] == "psql" and "-1" not in comando
    assert "default_transaction_read_only=on" in argumentos["env"]["PGOPTIONS"]
    assert "search_path=producao" in argumentos["env"]["PGOPTIONS"]
    assert INT.atual() is None                      # perguntar não é intervir
    for grava in ("UPDATE users SET active=0 WHERE id=1", "DELETE FROM x WHERE a=1",
                  "CREATE TABLE y (a int)"):
        with pytest.raises(INT.Recusa, match="só de leitura"):
            INT.consultar(grava, rodar=_rodar_de_mentira(chamadas))
    assert len(chamadas) == 1


def test_sql_que_so_le_pela_ferramenta_nao_vira_relatorio(com_banco):
    com_banco.write_text("SELECT 1;\n", encoding="utf-8")
    INT.executar_sql(com_banco, [], "", rodar=_rodar_de_mentira([]))
    assert INT.fechar("consultei") is None and INT.listar() == []


# ---------------------------------------------------------------- a exportação

def test_exportar_leva_mascarado_e_nunca_o_dump(com_banco, tmp_path):
    INT.executar_sql(com_banco, ["settings"], "acerto", rodar=_rodar_de_mentira([]))
    dados = INT.fechar("acertei")
    (INT.base() / "intervencoes" / dados["id"] / "banco" / "01-antes.dump").write_bytes(b"dado real")
    repositorio = tmp_path / "privado"
    repositorio.mkdir()
    levadas = INT.exportar(repositorio, mascarar=lambda texto: texto.replace("acerto", "[M]"))
    alvo = repositorio / "intervencoes" / levadas[0]
    assert levadas == [f"principal-{dados['id']}"]
    assert sorted(p.name for p in alvo.iterdir()) == ["01.sql", "RELATORIO.md", "codigo.patch"]
    assert "[M]" in (alvo / "RELATORIO.md").read_text(encoding="utf-8")
    assert INT.exportar(repositorio, mascarar=str) == []     # não leva duas vezes


def test_o_que_a_mascara_recusa_fica_no_servidor(casa, tmp_path):
    INT.guardar([casa / "outro.py"])
    (casa / "outro.py").write_text("X = 9\n", encoding="utf-8")
    INT.fechar("mudei")
    repositorio = tmp_path / "privado"
    repositorio.mkdir()

    def recusa(texto):
        raise ValueError("sobrou dado de pessoa")
    levadas = INT.exportar(repositorio, mascarar=recusa)
    alvo = repositorio / "intervencoes" / levadas[0]
    assert not (alvo / "RELATORIO.md").exists()
    assert "RELATORIO.md" in (alvo / "FICOU_NO_SERVIDOR.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------- a guarda

def test_a_guarda_guarda_o_original_antes_do_edit(casa):
    assert GUARDA.decidir("Edit", {"file_path": str(casa / "modulo.py")}) is None
    pasta = INT.atual()
    assert pasta and (pasta / "antes" / "modulo.py").is_file()


def test_a_guarda_nao_deixa_ler_segredo(casa):
    for caminho in ("/dados/cofre.key", "C:\\ProgramData\\CartorioGestao\\cenprot.cred",
                    "/Users/x/.pgpass", "/dados/operador/operador.cred"):
        assert GUARDA.decidir("Read", {"file_path": caminho})
    assert GUARDA.decidir("Grep", {"pattern": "TOKEN", "path": "/dados/operador/operador.cred"})
    assert GUARDA.decidir("Glob", {"pattern": "x", "glob": "**/*.key"})
    assert GUARDA.decidir("Read", {"file_path": str(casa / "modulo.py")}) is None
    assert GUARDA.decidir("Grep", {"pattern": "soma", "path": str(casa)}) is None
    assert INT.atual() is None       # ler não abre intervenção
    assert GUARDA.decidir("Bash", {"command": "cat '/dados/cofre.key'"})
    assert GUARDA.decidir("PowerShell", {"command": "Get-Content C:\\dados\\avisos.cred"})


@pytest.mark.parametrize("comando", [
    'python -c "db.execute(\'DROP TABLE users\')"',
    "bash installer/macos/assumir.sh ASSUMIR",
    "rm -rf /Users/x/dados/arquivos",
    "Remove-Item C:\\dados -Recurse -Force",
    "pg_restore -d cartorio copia.dump",
    "git push --force origin main",
])
def test_a_guarda_cobra_o_confirmo_no_shell(casa, comando):
    recusa = GUARDA.decidir("Bash", {"command": comando})
    assert recusa and "CONFIRMO" in recusa
    INT.registrar_confirmacao("CONFIRMO")
    assert GUARDA.decidir("Bash", {"command": comando}) is None


@pytest.mark.parametrize("comando", [
    'psql -c "SELECT count(*) FROM users"',
    'psql -c "\\d users"',
    "python -m py_compile modulo.py",
    "ls -la", "rm arquivo_temporario.txt",
    "./op sql mudanca.sql --tabelas settings --motivo acerto",
    './op consulta "SELECT 1"',
])
def test_a_guarda_deixa_passar_o_que_tem_volta(casa, comando):
    assert GUARDA.decidir("Bash", {"command": comando}) is None


@pytest.mark.parametrize("comando", [
    'psql -c "DELETE FROM settings WHERE key=\'x\'"',
    'psql -c "UPDATE users SET active=0 WHERE id=1"',
    'psql "$CG_PG_DSN" -f mudanca.sql',
    "psql -d cartorio < mudanca.sql",
    'psql -c "DROP TABLE users"',
])
def test_gravar_por_psql_direto_e_barrado_mesmo_com_o_confirmo(casa, comando):
    """Gravar é pela ferramenta `sql`, que copia as tabelas antes. O CONFIRMO
    libera o que não tem volta — não libera gravar sem cópia."""
    INT.registrar_confirmacao("CONFIRMO")
    recusa = GUARDA.decidir("Bash", {"command": comando})
    assert recusa and "psql" in recusa and "sql" in recusa
    linhas = INT.comandos(INT.atual())
    assert linhas[-1]["comando"] == comando and linhas[-1]["barrado"]


def test_a_confirmacao_e_do_oficial_e_a_guarda_nao_se_desliga_sozinha(casa):
    confirmacao = INT.base() / "confirmacao"
    assert "do oficial" in GUARDA.decidir("Write", {"file_path": str(confirmacao)})
    assert "do oficial" in GUARDA.decidir(
        "Bash", {"command": f"echo '{{}}' > {INT.base()}/confirmacao"})
    assert not INT.confirmacao_valida()
    guarda = casa / "operador" / "guarda.py"
    assert "CONFIRMO" in GUARDA.decidir("Edit", {"file_path": str(guarda)})
    ajustes = INT.base() / "posto" / ".claude" / "settings.json"
    assert "CONFIRMO" in GUARDA.decidir("Write", {"file_path": str(ajustes)})
    INT.registrar_confirmacao("CONFIRMO")
    assert GUARDA.decidir("Edit", {"file_path": str(guarda)}) is None


# ---------------------------------------------------------------- o conhecimento

def test_a_memoria_guarda_um_fato_por_linha_e_nao_repete(casa):
    assert CONH.lembrar("o backup roda às 23h") .endswith("o backup roda às 23h")
    assert CONH.lembrar("o  backup roda   às 23h") == ""       # já sabia
    CONH.lembrar("o balcão abre às 8h")
    memoria = CONH.ler_memoria()
    assert memoria.count("backup") == 1 and "balcão abre" in memoria
    with pytest.raises(ValueError):
        CONH.lembrar("   ")


def test_o_diario_guarda_todo_pedido_e_se_procura(casa):
    CONH.anotar("telegram", "por que o selo não saiu?", "Faltava o lote; pedi outro.",
                relatorio={"id": "2026-11-12-001", "arquivos": 0, "sql": 1}, comandos=4)
    CONH.anotar("sistema", "confira o caixa de ontem", "Fechou certo.")
    CONH.anotar("app", "reinicie a sincronia", "Reiniciada.")
    assert [e["porta"] for e in CONH.entradas()] == ["telegram", "sistema", "app"]
    assert [e["porta"] for e in CONH.entradas(2)] == ["sistema", "app"]
    achados = CONH.procurar("SELO")
    assert len(achados) == 1 and "relatório 2026-11-12-001" in achados[0]
    CONH.lembrar("o selo vem em lotes de 500")
    assert len(CONH.procurar("selo")) == 2 and CONH.procurar("inexistente") == []


def test_o_contexto_traz_a_situacao_a_memoria_os_pedidos_e_as_pendencias(casa, monkeypatch):
    monkeypatch.setenv("CG_MODO_RESERVA", "1")
    CONH.lembrar("o oficial prefere resposta curta")
    CONH.anotar("telegram", "confira a réplica", "Em dia.")
    INT.guardar([casa / "outro.py"])
    (casa / "outro.py").write_text("X = 2\n", encoding="utf-8")
    fechada = INT.fechar("mudei")
    texto = CONH.contexto()
    assert "RESERVA" in texto and "só lê" in texto
    assert "o oficial prefere resposta curta" in texto
    assert "confira a réplica" in texto and "Em dia." in texto
    assert f"Relatórios por exportar: {fechada['id']}" in texto


def test_o_conhecimento_vai_mascarado_e_o_do_outro_servidor_chega(casa, tmp_path, monkeypatch):
    CONH.lembrar("fato do principal")
    CONH.anotar("telegram", "pedido com nome de pessoa", "resposta comum", sessao="s-1")
    repositorio = tmp_path / "privado"
    (repositorio / "conhecimento" / "reserva" / "diario").mkdir(parents=True)
    (repositorio / "conhecimento" / "reserva" / "MEMORIA.md").write_text(
        "- 2026-11-01 — o disco do reserva é pequeno\n", encoding="utf-8")
    (repositorio / "conhecimento" / "reserva" / "diario" / "2026-11.jsonl").write_text(
        json.dumps({"quando": "2026-11-01T10:00:00", "servidor": "reserva", "porta": "app",
                    "pedido": "limpe o disco", "resposta": "Limpei."}) + "\n", encoding="utf-8")

    def mascarar(texto):
        if "nome de pessoa" in texto:
            raise ValueError("sobrou dado")
        return texto.replace("principal", "[P]")
    assert "MEMORIA.md" in CONH.exportar_para(repositorio, mascarar)
    meu = repositorio / "conhecimento" / "principal"
    assert "fato do [P]" in (meu / "MEMORIA.md").read_text(encoding="utf-8")
    linha = json.loads(next((meu / "diario").glob("*.jsonl")).read_text(encoding="utf-8"))
    assert linha["pedido"] == CONH.FICOU and linha["resposta"] == "resposta comum"
    assert "sessao" not in linha
    assert CONH.trazer_de(repositorio) == ["reserva"]
    assert CONH.outros() == ["reserva"]
    texto = CONH.contexto()
    assert "o disco do reserva é pequeno" in texto and "limpe o disco" in texto
    assert any("reserva" in achado for achado in CONH.procurar("disco"))


# ----------------------------------------------------------------------- o posto

def test_o_posto_liga_a_guarda_os_ganchos_e_nega_os_segredos(casa):
    alvo = POSTO.montar()
    ajustes = json.loads((alvo / ".claude" / "settings.json").read_text(encoding="utf-8"))
    guarda = ajustes["hooks"]["PreToolUse"][0]
    for ferramenta in ("Bash", "PowerShell", "Read", "Edit", "Write", "Grep"):
        assert ferramenta in guarda["matcher"].split("|")
    assert "guarda.py" in guarda["hooks"][0]["command"]
    for gancho, nome in (("SessionStart", "inicio"), ("UserPromptSubmit", "pedido"),
                         ("Stop", "fim")):
        assert ajustes["hooks"][gancho][0]["hooks"][0]["command"].endswith(f'posto.py" {nome}')
    assert "Read(//**/*.cred)" in ajustes["permissions"]["deny"]
    assert str(casa) in ajustes["permissions"]["additionalDirectories"]
    assert ajustes["env"]["CARTORIO_GESTAO_DATA"] == str(INT.pasta_de_dados())
    instrucoes = (alvo / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Você é o superusuário" in instrucoes and str(casa) in instrucoes
    assert not [marca for marca in ("{SERVIDOR}", "{SISTEMA}", "{DADOS}", "{OPERADOR}", "{OP}")
                if marca in instrucoes]
    assert "op.py" in (alvo / "op").read_text(encoding="utf-8")
    assert (alvo / "op.cmd").is_file()


def test_no_app_os_ganchos_abrem_fecham_e_anotam_no_diario(casa, tmp_path):
    """A porta do app não passa pela ponte: é o posto que abre a intervenção,
    fecha o relatório e escreve o diário."""
    POSTO.gancho_pedido({"prompt": "troque o X por 42", "session_id": "s-app"})
    aberta = INT._ler(INT.atual())
    assert aberta["pedido"] == "troque o X por 42" and aberta["porta"] == "app"
    GUARDA.decidir("Edit", {"file_path": str(casa / "outro.py")})
    (casa / "outro.py").write_text("X = 42\n", encoding="utf-8")
    transcricao = tmp_path / "conversa.jsonl"
    transcricao.write_text("\n".join(json.dumps(linha) for linha in [
        {"type": "user", "message": {"role": "user", "content": "troque o X por 42"}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Troquei o X."}]}},
        {"type": "system", "subtype": "stop_hook_summary"},
    ]) + "\n", encoding="utf-8")
    POSTO.gancho_fim({"transcript_path": str(transcricao), "session_id": "s-app"})
    assert INT.atual() is None
    entrada = CONH.entradas()[-1]
    assert entrada["porta"] == "app" and entrada["pedido"] == "troque o X por 42"
    assert entrada["resposta"] == "Troquei o X." and entrada["relatorio"]["arquivos"] == 1
    assert INT.listar()[0]["resumo"] == "Troquei o X."


def test_no_app_o_confirmo_do_oficial_vale_e_pela_ponte_os_ganchos_nao_agem(casa, monkeypatch):
    POSTO.gancho_pedido({"prompt": "CONFIRMO, pode apagar"})
    assert INT.confirmacao_valida()
    POSTO.gancho_fim({"last_assistant_message": "Apaguei."})
    assert CONH.entradas()[-1]["resposta"] == "Apaguei."
    monkeypatch.setenv("OPERADOR_PELA_PONTE", "1")
    POSTO.gancho_pedido({"prompt": "pedido que a ponte já abriu"})
    assert INT.atual() is None
    POSTO.gancho_fim({"last_assistant_message": "resposta"})
    assert len(CONH.entradas()) == 1


def test_o_que_o_operador_ja_sabe_entra_na_conversa_nova_e_nao_na_retomada(casa):
    CONH.lembrar("o servidor reinicia aos domingos")
    assert "o servidor reinicia aos domingos" in POSTO.gancho_inicio({"source": "startup"})
    assert "O que você já sabe" in POSTO.gancho_inicio({"source": "compact"})
    assert POSTO.gancho_inicio({"source": "resume"}) == ""
    assert (POSTO.pasta() / "CLAUDE.md").is_file()      # o início remonta o posto


# --------------------------------------------------------------------- a bandeja

def test_a_bandeja_entrega_na_ordem_e_uma_vez_so(casa):
    base = INT.base()
    BANDEJA.pedir(base, "primeiro", ["/x/a.pdf"], de="mario", tela="/caixa")
    BANDEJA.comandar(base, "NOVO")
    BANDEJA.pedir(base, "segundo")
    colhidos = BANDEJA.colher(base)
    assert [(c["tipo"], c.get("texto"), c.get("comando")) for c in colhidos] == [
        ("pedido", "primeiro", None), ("comando", "", "novo"), ("pedido", "segundo", None)]
    assert colhidos[0]["anexos"] == ["/x/a.pdf"] and colhidos[0]["tela"] == "/caixa"
    assert BANDEJA.colher(base) == []


def test_a_tela_sabe_se_a_ponte_esta_viva(casa):
    base = INT.base()
    assert BANDEJA.ler_estado(base)["viva"] is False
    BANDEJA.gravar_estado(base, {"servidor": "principal", "rodando": None})
    estado = BANDEJA.ler_estado(base)
    assert estado["viva"] is True and estado["servidor"] == "principal"
    assert BANDEJA.ler_estado(base, agora=estado["gravado_em"] + 600)["viva"] is False


def test_a_frase_errada_cinco_vezes_tranca_as_duas_portas(casa):
    base = INT.base()
    assert BANDEJA.frase_confere(base, " girassol azul ", "girassol azul", agora=1000.0) == (True, "")
    for vez in range(1, BANDEJA.ERROS_ATE_TRANCAR):
        confere, recado = BANDEJA.frase_confere(base, "errada", "girassol azul", agora=1000.0)
        assert not confere and f"({vez} de" in recado
    confere, recado = BANDEJA.frase_confere(base, "errada", "girassol azul", agora=1000.0)
    assert not confere and "tranquei" in recado
    assert BANDEJA.frase_confere(base, "girassol azul", "girassol azul", agora=1001.0)[0] is False
    depois = 1000.0 + BANDEJA.MINUTOS_TRANCADO * 60 + 1
    assert BANDEJA.frase_confere(base, "girassol azul", "girassol azul", agora=depois)[0] is True
    assert BANDEJA.frase_confere(base, "", "", agora=depois)[0] is False     # sem frase não abre


# ---------------------------------------------------------------------- a ponte

class _TelegramDeMentira:
    def __init__(self):
        self.ditas: list[tuple[int, str]] = []
        self.apagadas: list = []
        self.enviados: list[str] = []
        self.agiu = 0

    def dizer(self, conversa, texto):
        self.ditas.append((conversa, texto))

    def baixar(self, file_id, destino):
        Path(destino).write_bytes(b"%PDF-ficticio")

    def apagar(self, conversa, mensagem):
        self.apagadas.append(mensagem)

    def agindo(self, conversa):
        self.agiu += 1

    def enviar_arquivo(self, conversa, caminho):
        self.enviados.append(Path(caminho).name)


def _mensagem(de, texto="", **mais):
    return {"update_id": 1, "message": {
        "message_id": 77, "from": {"id": de}, "chat": {"id": de, "type": "private"},
        "text": texto, **mais}}


def _encerrar_aqui(dados, ambiente):
    return POSTO.encerrar(dados["porta"], dados["pedido"], dados["resposta"],
                          custo=dados["custo"], sessao=dados["sessao"],
                          arquivos=dados["arquivos"], numero=dados["numero"])


def _ponte(config=None, **mais):
    telegram = _TelegramDeMentira()
    mais.setdefault("sair", lambda codigo: None)       # nenhum teste derruba o pytest
    p = PONTE.Ponte({"OPERADOR_TELEGRAM_USUARIO": str(OFICIAL), **(config or {})}, telegram,
                    encerrar=_encerrar_aqui, **mais)
    return p, telegram


@pytest.fixture
def ponte(casa):
    return _ponte()


def _pedido_da_fila(p):
    p.despejar_lote(forcar=True)
    return p.fila.get_nowait()


def test_a_ponte_so_atende_o_oficial(ponte):
    p, telegram = ponte
    p.receber(_mensagem(ESTRANHO, "apague tudo"))
    assert p.lote is None and p.fila.empty() and telegram.ditas == []
    p.receber(_mensagem(OFICIAL, "confira o caixa de hoje"))
    pedido = _pedido_da_fila(p)
    assert pedido["texto"] == "confira o caixa de hoje" and pedido["porta"] == "telegram"
    assert telegram.ditas[-1][1] == "Recebido."


def test_pedido_que_comeca_por_barra_nao_e_comando(ponte):
    p, telegram = ponte
    p.receber(_mensagem(OFICIAL, "/administrativo/gestor não abre"))
    assert _pedido_da_fila(p)["texto"] == "/administrativo/gestor não abre"
    p.receber(_mensagem(OFICIAL, "/estado"))
    assert p.lote is None and "Servidor: principal" in telegram.ditas[-1][1]


def test_o_oficial_num_grupo_nao_e_atendido(ponte):
    p, _ = ponte
    mensagem = _mensagem(OFICIAL, "confira o caixa")
    mensagem["message"]["chat"] = {"id": -5, "type": "group"}
    p.receber(mensagem)
    assert p.lote is None and p.fila.empty()


def test_bot_sem_dono_so_diz_o_numero_e_nao_roda_nada(casa):
    telegram = _TelegramDeMentira()
    p = PONTE.Ponte({}, telegram)
    p.receber(_mensagem(ESTRANHO, "oi"))
    assert p.lote is None and p.fila.empty()
    assert str(ESTRANHO) in telegram.ditas[0][1]


def test_o_confirmo_do_oficial_libera_e_o_de_estranho_nao(ponte):
    p, _ = ponte
    p.receber(_mensagem(ESTRANHO, "CONFIRMO"))
    assert not INT.confirmacao_valida()
    p.receber(_mensagem(OFICIAL, "CONFIRMO, pode apagar"))
    assert INT.confirmacao_valida()


def test_o_album_de_fotos_e_as_mensagens_seguidas_viram_um_pedido_so(casa):
    """Três fotos de uma escritura chegam como três mensagens; antes, cada
    uma virava um pedido, e duas iam sem texto."""
    agora = [100.0]
    p, telegram = _ponte(relogio=lambda: agora[0])
    for numero in (1, 2, 3):
        campos = {"media_group_id": "album", "photo": [{"file_id": f"f{numero}", "file_size": 9}]}
        if numero == 1:
            campos["caption"] = "confira esta escritura"
        p.receber(_mensagem(OFICIAL, **campos))
    p.receber(_mensagem(OFICIAL, "o comprador é o segundo outorgado"))
    assert p.despejar_lote() is False and p.fila.empty()        # ainda pode vir mais
    agora[0] += PONTE.ESPERA_DO_LOTE + 0.1
    assert p.despejar_lote() is True
    pedido = p.fila.get_nowait()
    assert pedido["texto"] == "confira esta escritura\no comprador é o segundo outorgado"
    assert len(pedido["anexos"]) == 3 and p.fila.empty()
    assert [texto for _, texto in telegram.ditas] == ["Recebido."]


def test_o_anexo_chega_com_nome_seguro_e_vai_no_pedido(ponte):
    p, _ = ponte
    p.receber(_mensagem(OFICIAL, caption="analise", document={
        "file_id": "f1", "file_name": "../../escritura; rm -rf.pdf", "file_size": 10}))
    pedido = _pedido_da_fila(p)
    anexo = Path(pedido["anexos"][0])
    assert anexo.parent.parent == INT.base() / "entrada"
    assert ";" not in anexo.name and " " not in anexo.name and ".." not in anexo.name
    assert str(anexo) in p.texto_do_pedido(pedido)


def test_anexo_grande_demais_e_recusado_com_aviso(ponte):
    p, telegram = ponte
    p.receber(_mensagem(OFICIAL, document={
        "file_id": "f1", "file_name": "livro.pdf", "file_size": PONTE.LIMITE_DO_ARQUIVO + 1}))
    assert p.lote is None and "20 MB" in telegram.ditas[0][1]


def test_o_audio_chega_ao_operador_como_texto(casa):
    p, telegram = _ponte(ouvir=lambda arquivo: "confira o protesto do título doze")
    p.receber(_mensagem(OFICIAL, voice={"file_id": "v1", "file_size": 2000}))
    pedido = _pedido_da_fila(p)
    assert pedido["texto"] == "[áudio transcrito] confira o protesto do título doze"
    assert pedido["anexos"] == []          # o operador não ouve: o arquivo não vai


def test_audio_que_nao_transcreve_avisa_e_nao_vira_pedido_vazio(casa):
    def surdo(arquivo):
        raise RuntimeError("o modelo não está instalado")
    p, telegram = _ponte(ouvir=surdo)
    p.receber(_mensagem(OFICIAL, voice={"file_id": "v1", "file_size": 2000}))
    assert p.lote is None and p.fila.empty()
    assert "transcrever" in telegram.ditas[0][1] and "o modelo não está instalado" in telegram.ditas[0][1]
    p.receber(_mensagem(OFICIAL, sticker={"file_id": "s1"}))
    assert "Não sei ler" in telegram.ditas[-1][1]


def test_com_frase_a_ponte_so_abre_para_quem_a_diz(casa):
    agora = [1000.0]
    p, telegram = _ponte({"OPERADOR_FRASE": "girassol azul"}, relogio=lambda: agora[0])
    p.receber(_mensagem(OFICIAL, "apague o protocolo"))
    assert p.lote is None and "Trancado" in telegram.ditas[-1][1]
    p.receber(_mensagem(OFICIAL, "/abrir tulipa"))
    assert "errada" in telegram.ditas[-1][1] and telegram.apagadas == [77]
    p.receber(_mensagem(OFICIAL, "/abrir girassol azul"))
    assert "Aberto" in telegram.ditas[-1][1] and len(telegram.apagadas) == 2
    p.receber(_mensagem(OFICIAL, "confira o caixa"))
    assert _pedido_da_fila(p)["texto"] == "confira o caixa"
    agora[0] += PONTE.HORAS_DA_FRASE * 3600 + 1         # venceu
    p.receber(_mensagem(OFICIAL, "outro pedido"))
    assert p.lote is None and "Trancado" in telegram.ditas[-1][1]


def test_novo_esquece_a_conversa_e_lembrar_guarda_na_memoria(ponte):
    p, telegram = ponte
    p.estado["sessao"] = "abc"
    p.receber(_mensagem(OFICIAL, "/novo"))
    assert p.estado["sessao"] is None and p.lote is None
    p.receber(_mensagem(OFICIAL, "/lembrar o malote sai às 16h"))
    assert "o malote sai às 16h" in CONH.ler_memoria()
    assert "Guardado" in telegram.ditas[-1][1]


def test_a_tela_do_sistema_entra_na_mesma_fila(ponte):
    p, telegram = ponte
    p.estado["sessao"] = "abc"
    BANDEJA.pedir(INT.base(), "por que este selo não saiu?", ["/x/print.png"],
                  de="mario", tela="/protesto/titulo/12")
    BANDEJA.pedir(INT.base(), "CONFIRMO")
    BANDEJA.comandar(INT.base(), "lembrar", "o selo vem em lotes")
    BANDEJA.comandar(INT.base(), "novo")
    assert p.colher_da_bandeja() == 4
    pedido = p.fila.get_nowait()
    assert pedido["porta"] == "sistema" and pedido["anexos"] == ["/x/print.png"]
    assert "/protesto/titulo/12" in p.texto_do_pedido(pedido)
    assert "Porta: tela do sistema" in p.texto_do_pedido(pedido)
    assert p.fila.get_nowait()["texto"] == "CONFIRMO" and INT.confirmacao_valida()
    assert "o selo vem em lotes" in CONH.ler_memoria() and p.estado["sessao"] is None
    assert telegram.ditas == []                 # a tela não fala pelo Telegram
    assert BANDEJA.ler_estado(INT.base())["viva"] is True


def test_a_resposta_longa_e_cortada_em_mensagens():
    texto = "\n".join(f"linha {n} " + "x" * 80 for n in range(200))
    partes = PONTE.partes_da_resposta(texto)
    assert len(partes) > 1 and all(len(p) <= PONTE.LIMITE_DA_MENSAGEM for p in partes)
    assert "".join(partes).replace("\n", "") == texto.replace("\n", "")


def test_o_comando_do_operador_nao_fica_esperando_tela():
    comando = PONTE.comando_do_operador({}, "sessao-1")
    assert comando[comando.index("--permission-mode") + 1] == "dontAsk"
    assert comando[comando.index("--model") + 1] == PONTE.MODELO_PADRAO
    assert comando[comando.index("--output-format") + 1] == "stream-json" and "--verbose" in comando
    assert comando[comando.index("--effort") + 1] == PONTE.ESFORCO_PADRAO
    assert comando[comando.index("--resume") + 1] == "sessao-1"
    assert "--bare" not in comando       # --bare desligaria a guarda
    assert "--fallback-model" not in comando and "--max-budget-usd" not in comando
    comando = PONTE.comando_do_operador({"OPERADOR_MODELO_RESERVA": "claude-sonnet-5-5",
                                         "OPERADOR_TETO_USD": "5", "OPERADOR_ESFORCO": "padrao"},
                                        None)
    assert comando[comando.index("--fallback-model") + 1] == "claude-sonnet-5-5"
    assert comando[comando.index("--max-budget-usd") + 1] == "5"
    assert "--effort" not in comando and "--resume" not in comando


def test_a_assinatura_ganha_da_api_e_a_chave_sai_do_ambiente(casa, monkeypatch):
    """«Sem gastar a API»: com a assinatura dita, a chave não pode ficar no
    ambiente do operador — o Claude Code cobraria por ela sem avisar."""
    assert PONTE.pagamento({})[0] == ""
    assert PONTE.pagamento({"ANTHROPIC_API_KEY": "chave"})[0] == "API (chave do operador)"
    frase, entra, sai = PONTE.pagamento({"ANTHROPIC_API_KEY": "chave",
                                         "CLAUDE_CODE_OAUTH_TOKEN": "token"})
    assert frase.startswith("assinatura") and entra == {"CLAUDE_CODE_OAUTH_TOKEN": "token"}
    assert sai == ["ANTHROPIC_API_KEY"]
    assert PONTE.pagamento({"OPERADOR_ASSINATURA": "1"})[0] == "assinatura (login desta conta)"
    assert PONTE.pagamento({"OPERADOR_CHAVE_DA_CASA": "1"},
                           chave_da_casa=lambda: "chave-da-casa")[1] == {
                               "ANTHROPIC_API_KEY": "chave-da-casa"}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "herdada-do-ambiente")
    p, _ = _ponte({"OPERADOR_ASSINATURA": "1", "TELEGRAM_TOKEN": "segredo-do-bot",
                   "OPERADOR_FRASE": "girassol"})
    ambiente = p._ambiente(p._pedido("telegram", "oi", []))
    assert "ANTHROPIC_API_KEY" not in ambiente
    assert "TELEGRAM_TOKEN" not in ambiente and "OPERADOR_FRASE" not in ambiente
    assert ambiente["OPERADOR_PELA_PONTE"] == "1" and ambiente["OPERADOR_PORTA"] == "telegram"


def test_o_ambiente_do_operador_vem_do_arquivo_da_casa_e_nao_do_cred_velho(casa, tmp_path, monkeypatch):
    env = tmp_path / "reserva.env"
    env.write_text("CG_MODO_RESERVA=0\nCG_PG_DSN=host=x user=cg\n", encoding="utf-8")
    monkeypatch.setenv("OPERADOR_AMBIENTE", str(env))
    p, _ = _ponte({"ANTHROPIC_API_KEY": "chave", "CG_PG_DSN": "host=x user=cg_leitor"})
    ambiente = p._ambiente(p._pedido("sistema", "oi", []))
    assert ambiente["CG_PG_DSN"] == "host=x user=cg" and ambiente["CG_MODO_RESERVA"] == "0"


class _Entrada:
    def __init__(self):
        self.texto = ""

    def write(self, texto):
        self.texto += texto

    def close(self):
        pass


class _OperadorDeMentira:
    """Faz o que o Claude Code faria: edita um arquivo pelo caminho da guarda
    e devolve os eventos do `stream-json`."""
    returncode = 0
    pid = None
    eventos = [
        {"type": "system", "subtype": "init", "session_id": "s-9"},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/sistema/outro.py"}}]}},
        {"type": "result", "subtype": "success", "is_error": False, "session_id": "s-9",
         "result": "Corrigi o X.", "total_cost_usd": 0.5},
    ]
    edita = True

    def __init__(self, comando, **argumentos):
        self.comando, self.argumentos = comando, argumentos
        self.stdin = _Entrada()
        if self.edita:
            raiz = INT.raiz_do_sistema()
            GUARDA.decidir("Edit", {"file_path": str(raiz / "outro.py")})
            (raiz / "outro.py").write_text("X = 42\n", encoding="utf-8")
        saida = Path(argumentos["env"]["OPERADOR_SAIDA"])
        if getattr(self, "devolve", None):
            saida.mkdir(parents=True, exist_ok=True)
            (saida / self.devolve).write_bytes(b"%PDF-ficticio")
        self.stdout = iter(json.dumps(evento) + "\n" for evento in self.eventos)

    def wait(self):
        return 0

    def kill(self):
        pass


def test_um_pedido_inteiro_responde_fecha_o_relatorio_e_vai_para_o_diario(casa):
    vistos = {}

    class Operador(_OperadorDeMentira):
        devolve = "certidao.pdf"

        def __init__(self, comando, **argumentos):
            super().__init__(comando, **argumentos)
            vistos["processo"] = self
    p, telegram = _ponte({"ANTHROPIC_API_KEY": "chave-ficticia", "TELEGRAM_TOKEN": "t"},
                         rodar_processo=Operador)
    p.receber(_mensagem(OFICIAL, "o X está errado"))
    p.atender(_pedido_da_fila(p))
    resposta = telegram.ditas[-1][1]
    assert resposta.startswith("Corrigi o X.") and "Relatório" in resposta and "1 arquivo" in resposta
    assert "Custo do pedido: US$ 0,50" in resposta
    assert p.estado["sessao"] == "s-9" and p.atual is None
    feita = INT.listar()[0]
    assert feita["pedido"] == "o X está errado" and feita["fechada_em"] and feita["porta"] == "telegram"
    assert [m["arquivo"] for m in feita["mudancas"]] == ["outro.py"]
    entrada = CONH.entradas()[-1]
    assert entrada["porta"] == "telegram" and entrada["resposta"] == "Corrigi o X."
    assert entrada["relatorio"]["id"] == feita["id"] and entrada["custo_usd"] == 0.5
    assert entrada["arquivos"] == ["certidao.pdf"] and telegram.enviados == ["certidao.pdf"]
    processo = vistos["processo"]
    assert "o X está errado" in processo.stdin.texto and "Porta: Telegram" in processo.stdin.texto
    assert processo.argumentos["cwd"] == str(POSTO.pasta())     # roda de dentro do posto
    assert (POSTO.pasta() / ".claude" / "settings.json").is_file()
    assert processo.argumentos["env"]["ANTHROPIC_API_KEY"] == "chave-ficticia"
    assert "TELEGRAM_TOKEN" not in processo.argumentos["env"]


def test_a_recusa_da_anthropic_chega_em_portugues_e_nao_troca_a_conversa(casa):
    class Recusado(_OperadorDeMentira):
        edita = False
        eventos = [
            {"type": "system", "subtype": "init", "session_id": "s-ruim"},
            {"type": "result", "subtype": "success", "is_error": True, "session_id": "s-ruim",
             "result": "Invalid API key · Fix external API key", "total_cost_usd": 0},
        ]
    p, telegram = _ponte({"ANTHROPIC_API_KEY": "chave-ficticia"}, rodar_processo=Recusado)
    p.estado["sessao"] = "s-boa"
    p.receber(_mensagem(OFICIAL, "confira o caixa"))
    p.atender(_pedido_da_fila(p))
    resposta = telegram.ditas[-1][1]
    assert "recusou a chave" in resposta and "operador.cred" in resposta
    assert "Invalid API key" not in resposta
    assert p.estado["sessao"] == "s-boa"
    assert "login" in PONTE.traduzir_erro("Not logged in · Please run /login")


def test_o_operador_que_para_no_limite_diz_como_continuar(casa):
    class NoLimite(_OperadorDeMentira):
        edita = False
        eventos = [{"type": "system", "subtype": "init", "session_id": "s-3"},
                   {"type": "result", "subtype": "error_max_turns", "is_error": True,
                    "session_id": "s-3"}]
    p, telegram = _ponte({"ANTHROPIC_API_KEY": "chave"}, rodar_processo=NoLimite)
    p.atender(p._pedido("telegram", "tarefa comprida", [], conversa=OFICIAL))
    assert "limite de passos" in telegram.ditas[-1][1] and "continue" in telegram.ditas[-1][1]
    assert p.estado["sessao"] == "s-3"          # dá para retomar de onde parou


def test_a_conversa_parada_ha_muito_tempo_recomeca(casa):
    agora = [50_000.0]
    vistos = []

    class Operador(_OperadorDeMentira):
        edita = False

        def __init__(self, comando, **argumentos):
            vistos.append(comando)
            super().__init__(comando, **argumentos)
    p, telegram = _ponte({"ANTHROPIC_API_KEY": "chave"}, rodar_processo=Operador,
                         relogio=lambda: agora[0])
    p.atender(p._pedido("telegram", "primeiro", [], conversa=OFICIAL))
    agora[0] += 3600
    p.atender(p._pedido("telegram", "segundo", [], conversa=OFICIAL))
    assert vistos[1][vistos[1].index("--resume") + 1] == "s-9"
    agora[0] += PONTE.HORAS_DA_CONVERSA * 3600 + 1
    p.atender(p._pedido("telegram", "terceiro", [], conversa=OFICIAL))
    assert "--resume" not in vistos[2] and "Conversa nova" in telegram.ditas[-1][1]


def test_enquanto_trabalha_a_ponte_mostra_que_esta_viva(casa):
    agora = [100.0]
    p, telegram = _ponte(relogio=lambda: agora[0])
    p.atual = {**p._pedido("telegram", "tarefa", [], conversa=OFICIAL), "desde": 100.0,
               "andamento": "começando", "passos": 0, "avisado_em": 100.0}
    p._andou(PONTE.descrever({"message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "python   -m  py_compile app.py"}}]}}))
    agora[0] += 6
    p.pulso()
    assert telegram.agiu == 1 and telegram.ditas == []
    agora[0] += PONTE.AVISO_A_CADA
    p.pulso()
    assert "ainda trabalhando" in telegram.ditas[-1][1]
    assert "rodando: python -m py_compile app.py" in telegram.ditas[-1][1]
    estado = BANDEJA.ler_estado(INT.base())
    assert estado["rodando"]["andamento"].startswith("rodando: python") and estado["rodando"]["passos"] == 1
    assert PONTE.descrever({"message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": "C:\\sistema\\app.py"}}]}}) == "lendo app.py"


def test_a_fila_sobrevive_ao_reinicio_e_o_pedido_do_meio_nao_se_refaz_sozinho(casa):
    p, telegram = _ponte()
    em_andamento = p._pedido("telegram", "apague as duplicatas", [], conversa=OFICIAL)
    p.atual = {**em_andamento, "desde": 1.0, "andamento": "rodando", "passos": 3, "avisado_em": 1.0}
    p.enfileirar(p._pedido("sistema", "confira o caixa", []))
    # a ponte cai e volta
    outra, telegram = _ponte()
    assert outra.fila.empty()
    outra.retomar()
    assert outra.fila.get_nowait()["texto"] == "confira o caixa" and outra.fila.empty()
    assert "reiniciou no meio" in telegram.ditas[-1][1] and "apague as duplicatas" in telegram.ditas[-1][1]
    assert "reiniciou no meio" in CONH.entradas()[-1]["resposta"]


def test_a_ponte_parada_sai_para_voltar_com_o_programa_novo(casa, monkeypatch):
    """O pacote de atualização (principal) e a troca de versão (reserva)
    mudam o programa debaixo da ponte, que ficaria com o velho na memória."""
    agora, saidas = [1000.0], []
    p, _ = _ponte(relogio=lambda: agora[0], sair=saidas.append)
    assert p.voltar_com_o_codigo_novo() is False               # nada mudou
    monkeypatch.setattr(PONTE, "assinatura_do_codigo", lambda: (("ponte.py", 2, 2),))
    p.atual = {**p._pedido("telegram", "tarefa", [], conversa=OFICIAL), "desde": 1.0,
               "andamento": "rodando", "passos": 1, "avisado_em": agora[0]}
    agora[0] += 61
    p.pulso()
    assert saidas == []                                        # no meio do pedido, espera
    p.atual = None
    agora[0] += 61
    p.pulso()
    assert saidas == [PONTE.CODIGO_DE_REINICIO]
    monkeypatch.setattr(PONTE, "assinatura_do_codigo", lambda: None)    # no meio da troca
    assert p.voltar_com_o_codigo_novo() is False


# ---------------------------------------------------------- a exceção na conta

def test_so_o_superusuario_e_robo_com_admin(cg_casa):
    db = cg_casa["db"]
    with pytest.raises(ValueError, match="USER ou AUDITOR"):
        db.create_user("robo_exemplo", "Robo Exemplo", SENHA, "ADMIN", eh_robo=1)
    with pytest.raises(ValueError, match="USER ou AUDITOR"):
        db.create_user(INT.LOGIN, INT.NOME, SENHA, "MANAGER", eh_robo=1)
    uid = db.create_user(INT.LOGIN, INT.NOME, SENHA, "ADMIN", eh_robo=1)
    conta = db.get_user(uid)
    assert conta["role"] == "ADMIN"
    # e a exceção não vaza para quem troca o nome depois
    with pytest.raises(ValueError, match="USER ou AUDITOR"):
        db.update_user(uid, "robo_dois", "Robo Dois", "ADMIN", eh_robo=1)
