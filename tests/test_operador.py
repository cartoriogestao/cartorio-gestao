"""O SUPERUSUÁRIO (docs/SUPERUSUARIO.md) — o que a prudência garante por
programa: o original guardado, o relatório, o «CONFIRMO», o reserva que não
grava, o segredo que não se lê, e a ponte que só atende o oficial.

Nada aqui fala com o Telegram, com a API nem com o PostgreSQL: a ponte recebe
um Telegram de mentira e o `sql` recebe um `rodar` de mentira.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "operador"))

import guarda as GUARDA  # noqa: E402
import intervencao as INT  # noqa: E402
import ponte as PONTE  # noqa: E402

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
    for variavel in ("CG_PG_DSN", "CG_PG_SCHEMA", "CG_MODO_RESERVA", "OPERADOR_NOME"):
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


def test_arquivo_de_fora_do_sistema_nao_se_guarda(casa, tmp_path):
    fora = tmp_path / "fora.py"
    fora.write_text("Z = 1\n", encoding="utf-8")
    assert INT.guardar([fora]) == []
    assert INT.atual() is None


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
    def rodar(comando, **_):
        chamadas.append(comando)
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
    assert chamadas[0][0] == "pg_dump" and "producao.settings" in chamadas[0]
    assert chamadas[1][0] == "psql" and "-1" in chamadas[1] and "ON_ERROR_STOP=1" in chamadas[1]
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
    assert GUARDA.decidir("Bash", {"command": "cat '/dados/cofre.key'"})
    assert GUARDA.decidir("PowerShell", {"command": "Get-Content C:\\dados\\avisos.cred"})
    assert GUARDA.decidir("Read", {"file_path": str(casa / "modulo.py")}) is None
    assert INT.atual() is None       # ler não abre intervenção


@pytest.mark.parametrize("comando", [
    'psql -c "DROP TABLE users"',
    'psql -c "DELETE FROM ri_matriculas"',
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
    "python -m py_compile modulo.py",
    "ls -la", "rm arquivo_temporario.txt",
    'psql -c "DELETE FROM settings WHERE key=\'x\'"',
])
def test_a_guarda_deixa_passar_o_que_tem_volta(casa, comando):
    assert GUARDA.decidir("Bash", {"command": comando}) is None


# ---------------------------------------------------------------------- a ponte

class _TelegramDeMentira:
    def __init__(self):
        self.ditas: list[tuple[int, str]] = []

    def dizer(self, conversa, texto):
        self.ditas.append((conversa, texto))

    def baixar(self, file_id, destino):
        Path(destino).write_bytes(b"%PDF-ficticio")


def _mensagem(de, texto="", **mais):
    return {"update_id": 1, "message": {
        "from": {"id": de}, "chat": {"id": de, "type": "private"}, "text": texto, **mais}}


@pytest.fixture
def ponte(casa):
    telegram = _TelegramDeMentira()
    p = PONTE.Ponte({"OPERADOR_TELEGRAM_USUARIO": str(OFICIAL)}, telegram)
    return p, telegram


def test_a_ponte_so_atende_o_oficial(ponte):
    p, telegram = ponte
    p.receber(_mensagem(ESTRANHO, "apague tudo"))
    assert p.fila.empty() and telegram.ditas == []
    p.receber(_mensagem(OFICIAL, "confira o caixa de hoje"))
    assert p.fila.get_nowait()["texto"] == "confira o caixa de hoje"


def test_o_oficial_num_grupo_nao_e_atendido(ponte):
    p, _ = ponte
    mensagem = _mensagem(OFICIAL, "confira o caixa")
    mensagem["message"]["chat"] = {"id": -5, "type": "group"}
    p.receber(mensagem)
    assert p.fila.empty()


def test_bot_sem_dono_so_diz_o_numero_e_nao_roda_nada(casa):
    telegram = _TelegramDeMentira()
    p = PONTE.Ponte({}, telegram)
    p.receber(_mensagem(ESTRANHO, "oi"))
    assert p.fila.empty()
    assert str(ESTRANHO) in telegram.ditas[0][1]


def test_o_confirmo_do_oficial_libera_e_o_de_estranho_nao(ponte):
    p, _ = ponte
    p.receber(_mensagem(ESTRANHO, "CONFIRMO"))
    assert not INT.confirmacao_valida()
    p.receber(_mensagem(OFICIAL, "CONFIRMO, pode apagar"))
    assert INT.confirmacao_valida()


def test_o_anexo_chega_com_nome_seguro_e_vai_no_pedido(ponte):
    p, _ = ponte
    p.receber(_mensagem(OFICIAL, caption="analise", document={
        "file_id": "f1", "file_name": "../../escritura; rm -rf.pdf", "file_size": 10}))
    pedido = p.fila.get_nowait()
    anexo = pedido["anexos"][0]
    assert anexo.parent.parent == INT.base() / "entrada"
    assert ";" not in anexo.name and " " not in anexo.name and ".." not in anexo.name
    assert str(anexo) in p.texto_do_pedido(pedido)


def test_anexo_grande_demais_e_recusado_com_aviso(ponte):
    p, telegram = ponte
    p.receber(_mensagem(OFICIAL, document={
        "file_id": "f1", "file_name": "livro.pdf", "file_size": PONTE.LIMITE_DO_ARQUIVO + 1}))
    assert p.fila.empty() and "20 MB" in telegram.ditas[0][1]


def test_novo_esquece_a_conversa(ponte):
    p, _ = ponte
    p.estado["sessao"] = "abc"
    p.receber(_mensagem(OFICIAL, "/novo"))
    assert p.estado["sessao"] is None and p.fila.empty()


def test_a_resposta_longa_e_cortada_em_mensagens():
    texto = "\n".join(f"linha {n} " + "x" * 80 for n in range(200))
    partes = PONTE.partes_da_resposta(texto)
    assert len(partes) > 1 and all(len(p) <= PONTE.LIMITE_DA_MENSAGEM for p in partes)
    assert "".join(partes).replace("\n", "") == texto.replace("\n", "")


def test_o_comando_do_operador_nao_fica_esperando_tela(tmp_path):
    comando = PONTE.comando_do_operador({}, "sessao-1", tmp_path / "a.json", "instruções")
    assert comando[comando.index("--permission-mode") + 1] == "dontAsk"
    assert comando[comando.index("--model") + 1] == PONTE.MODELO_PADRAO
    assert comando[comando.index("--resume") + 1] == "sessao-1"
    assert "--bare" not in comando       # --bare desligaria a guarda


def test_os_ajustes_ligam_a_guarda_em_toda_ferramenta_que_mexe(casa):
    ajustes = json.loads(PONTE.escrever_ajustes().read_text(encoding="utf-8"))
    gancho = ajustes["hooks"]["PreToolUse"][0]
    for ferramenta in ("Bash", "PowerShell", "Read", "Edit", "Write"):
        assert ferramenta in gancho["matcher"].split("|")
    assert "guarda.py" in gancho["hooks"][0]["command"]


def test_a_configuracao_le_chave_valor_e_tira_as_aspas(tmp_path):
    arquivo = tmp_path / "operador.cred"
    arquivo.write_text('# comentário\nTELEGRAM_TOKEN="abc"\nOPERADOR_NOME=reserva\n\nsolto\n',
                       encoding="utf-8")
    assert PONTE.ler_configuracao(arquivo) == {"TELEGRAM_TOKEN": "abc", "OPERADOR_NOME": "reserva"}


class _ProcessoDeMentira:
    returncode = 0

    def __init__(self, comando, **argumentos):
        self.comando, self.argumentos = comando, argumentos
        raiz = Path(argumentos["cwd"])
        # o «operador» edita um arquivo pelo caminho da guarda
        GUARDA.decidir("Edit", {"file_path": str(raiz / "outro.py")})
        (raiz / "outro.py").write_text("X = 42\n", encoding="utf-8")

    def communicate(self, entrada=None, timeout=None):
        self.entrada = entrada
        return json.dumps({"result": "Corrigi o X.", "session_id": "s-9",
                           "total_cost_usd": 0.5}), ""

    def kill(self):
        pass


def test_um_pedido_inteiro_responde_e_fecha_o_relatorio(casa, monkeypatch):
    (casa / "operador").mkdir()
    monkeypatch.setattr(PONTE, "AQUI", RAIZ / "operador")
    telegram = _TelegramDeMentira()
    p = PONTE.Ponte({"OPERADOR_TELEGRAM_USUARIO": str(OFICIAL),
                     "ANTHROPIC_API_KEY": "chave-ficticia", "TELEGRAM_TOKEN": "t"},
                    telegram, rodar_processo=_ProcessoDeMentira)
    p.receber(_mensagem(OFICIAL, "o X está errado"))
    p.atender(p.fila.get_nowait())
    resposta = telegram.ditas[-1][1]
    assert resposta.startswith("Corrigi o X.") and "Relatório" in resposta and "1 arquivo" in resposta
    assert p.estado["sessao"] == "s-9"
    feita = INT.listar()[0]
    assert feita["pedido"] == "o X está errado" and feita["fechada_em"]
    assert [m["arquivo"] for m in feita["mudancas"]] == ["outro.py"]


def test_o_token_do_telegram_nao_vai_para_o_ambiente_do_operador(casa, monkeypatch):
    monkeypatch.setattr(PONTE, "AQUI", RAIZ / "operador")
    vistos = {}

    class Processo(_ProcessoDeMentira):
        def __init__(self, comando, **argumentos):
            vistos.update(argumentos["env"])
            super().__init__(comando, **argumentos)
    p = PONTE.Ponte({"OPERADOR_TELEGRAM_USUARIO": str(OFICIAL), "TELEGRAM_TOKEN": "segredo-do-bot",
                     "ANTHROPIC_API_KEY": "chave-ficticia"},
                    _TelegramDeMentira(), rodar_processo=Processo)
    p.atender({"conversa": OFICIAL, "texto": "oi", "anexos": []})
    assert "TELEGRAM_TOKEN" not in vistos and vistos["ANTHROPIC_API_KEY"] == "chave-ficticia"


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
