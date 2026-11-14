"""O SUPERUSUÁRIO GERENCIA OS OUTROS ROBÔS (`operador/robos.py`,
docs/SUPERUSUARIO.md) — ordem do oficial de 14/11/2026: com um pedido simples,
ele configura o acesso de toda a automação e deixa tudo funcionando.

O QUE ESTES TESTES GUARDAM
    Que o quadro mostra a automação inteira e separa o que o superusuário
    resolve do que só o oficial pode fazer; que a conta de robô nasce com a
    senha SORTEADA e guardada sem ninguém ver; que com o cofre trancado nada
    é mexido; que conta de pessoa não se toca e robô não administra; e que o
    operador nunca lê o cofre.

O cofre aqui é de mentira (o de verdade vive atrás da senha-mestra do
oficial). NOMES: `mario` é o oficial, como manda a regra da casa.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

import automacao as AU
from bd_nativo import banco

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "operador"))

import intervencao as INT  # noqa: E402
import robos as ROBOS  # noqa: E402

SENHA = "Senha#12345"


class _CofreDeMentira:
    SENHA = "SENHA"

    def __init__(self, aberto: bool = True):
        self.aberto = aberto
        self.itens: dict[str, dict] = {}

    def estado(self, *, caminho=None):
        return {"aberto": self.aberto, "guardiao": True, "desde": "2026-11-14T08:00:00",
                "existe": True, "bloqueado_ate": None}

    def listar(self, *, caminho=None):
        return [{"nome": nome, "tipo": "SENHA", "nome_do_tipo": "usuário e senha",
                 "validade": None, "dias_para_vencer": item.get("dias"),
                 "campos_presentes": sorted(item["campos"])}
                for nome, item in sorted(self.itens.items())]

    def tem(self, nome, *, caminho=None):
        return nome in self.itens

    def gravar(self, nome, campos, *, tipo, validade=None, por, caminho=None):
        if not self.aberto:
            raise RuntimeError("cofre trancado")
        self.itens[nome] = {"campos": dict(campos), "tipo": tipo, "por": por}
        return {"nome": nome}

    def gravar_restrito(self, alvo, texto, *, conta_extra=""):
        Path(alvo).write_text(texto, encoding="utf-8")

    def ler(self, *_, **__):
        raise AssertionError("o segredo do cofre não se lê por aqui")


@pytest.fixture
def casa(cg_casa, monkeypatch):
    """A casa de teste, com o oficial (mario), o superusuário e um cofre de mentira."""
    monkeypatch.delenv("CG_MODO_RESERVA", raising=False)
    monkeypatch.delenv("OPERADOR_RAIZ", raising=False)
    monkeypatch.setenv("CARTORIO_GESTAO_DATA", str(cg_casa["dados"]))
    db = cg_casa["db"]
    mario = db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    superusuario = db.create_user(INT.LOGIN, INT.NOME, SENHA, "ADMIN", mario, eh_robo=1)
    import identidade_do_robo as IDR
    with db.transaction() as con:
        IDR.definir_responsavel_do_robo(con, superusuario, mario)
    cofre = _CofreDeMentira()
    monkeypatch.setattr(ROBOS, "_cofre", lambda: (cofre, Path("cofre-de-teste.json")))
    return {"db": db, "cofre": cofre, "dados": Path(cg_casa["dados"]), "mario": mario}


def _um(db, sql, parametros=()):
    with db.connect() as con:
        return banco(con).um(sql, parametros)


def _acoes(db, acao):
    return int(_um(db, "SELECT COUNT(*) AS n FROM audit_logs WHERE action=%s", (acao,))["n"])


def test_o_quadro_mostra_a_automacao_inteira_e_separa_o_que_falta(casa):
    db, cofre = casa["db"], casa["cofre"]
    cofre.aberto = False
    cofre.itens["sirc_portal"] = {"campos": {"usuario": "x", "senha": "segredo-do-portal"},
                                  "dias": 3}
    with db.transaction() as con:      # a casa já nasce com as rotinas de fábrica, desligadas
        codigo = AU.listar(con)[0]["codigo"]
        banco(con).escrever("UPDATE au_processos SET ativo=1, usa_credencial=%s WHERE codigo=%s",
                            ("cra_portal", codigo))
    db.create_user("robo_exemplo", "Robo Exemplo", SENHA, "USER", eh_robo=1)   # sem responsável
    texto = ROBOS.quadro(db=db)
    for titulo in ("## O despachante", "## O cofre das credenciais", "## As rotinas, por robô",
                   "## O quadro dos robôs da casa", "## As contas de robô", "## O que falta"):
        assert titulo in texto, titulo
    assert "NUNCA rodou neste banco" in texto                 # o despachante, num banco novo
    assert "TRANCADO" in texto and "«sirc_portal»" in texto and "vence em 3 dia(s)" in texto
    assert f"- {codigo} " in texto and "LIGADA" in texto
    assert "credencial «cra_portal»: NÃO ESTÁ NO COFRE" in texto
    assert "robo_exemplo (USER) — ativa; SEM RESPONSÁVEL" in texto
    assert f"{INT.LOGIN} (ADMIN) — ativa; responsável: mario" in texto
    meu, dele = texto.split("Só o oficial pode")
    assert "Você (superusuário) resolve:" in meu
    assert "o despachante nunca rodou" in meu and "«robo_exemplo» está sem responsável" in meu
    assert "ACHADOS: " not in texto.split("## O quadro dos robôs")[1].split("## As contas")[0] \
        .replace("ACHADOS: O gestor nunca rodou", "")       # «ainda não bate ponto» não é achado
    assert "desbloquear o cofre" in dele and "cadastrar a credencial «cra_portal»" in dele
    assert "renovar a credencial «sirc_portal»" in dele
    assert "segredo-do-portal" not in texto               # nenhum valor do cofre vai ao quadro


def test_a_conta_do_robo_nasce_com_a_senha_sorteada_no_cofre_e_ninguem_a_ve(casa):
    db, cofre = casa["db"], casa["cofre"]
    frase = ROBOS.conta("robo_malote", nome="Robo do Malote", cofre="sistema_malote", db=db)
    guardado = cofre.itens["sistema_malote"]
    senha = guardado["campos"]["senha"]
    assert guardado["campos"]["usuario"] == "robo_malote" and guardado["por"] == INT.LOGIN
    assert senha not in frase and "ninguém a viu" in frase and "conta criada" in frase
    conta = db.authenticate("robo_malote", senha)             # a senha guardada é a que entra
    assert conta and conta["role"] == "USER" and int(conta["eh_robo"]) == 1
    assert int(_um(db, "SELECT robo_responsavel_id FROM users WHERE username=%s",
                   ("robo_malote",))["robo_responsavel_id"]) == casa["mario"]
    assert _acoes(db, "USER_CREATED") == 1
    # de novo: a conta existe, a senha troca, e a velha deixa de valer
    frase = ROBOS.conta("robo_malote", cofre="sistema_malote", db=db)
    nova = cofre.itens["sistema_malote"]["campos"]["senha"]
    assert "senha trocada" in frase and nova != senha and nova not in frase
    assert db.authenticate("robo_malote", nova) and not db.authenticate("robo_malote", senha)
    assert _acoes(db, "PASSWORD_RESET") == 1


def test_a_senha_do_robo_tambem_pode_ficar_num_cred(casa):
    db = casa["db"]
    frase = ROBOS.conta("robo_selo", papel="auditor", arquivo="../selo robo", db=db)
    arquivo = casa["dados"] / "selo_robo.cred"
    linhas = dict(linha.split("=", 1) for linha in arquivo.read_text(encoding="utf-8").splitlines())
    assert linhas["USUARIO"] == "robo_selo" and linhas["SENHA"] not in frase
    assert db.authenticate("robo_selo", linhas["SENHA"])["role"] == "AUDITOR"
    assert casa["cofre"].itens == {}


def test_definir_o_responsavel_nao_mexe_na_senha_do_robo(casa):
    """O robô que roda mas não diz a mando de quem: acerta-se o responsável, e
    a senha que ele já usa continua valendo."""
    db = casa["db"]
    db.create_user("robo_exemplo", "Robo Exemplo", SENHA, "USER", eh_robo=1)
    frase = ROBOS.responsavel("robo_exemplo", db=db)
    assert "é mario" in frase and "não foi mexida" in frase
    assert int(_um(db, "SELECT robo_responsavel_id FROM users WHERE username=%s",
                   ("robo_exemplo",))["robo_responsavel_id"]) == casa["mario"]
    assert db.authenticate("robo_exemplo", SENHA)
    assert "SEM RESPONSÁVEL" not in ROBOS.quadro(db=db)
    with pytest.raises(ROBOS.Recusa, match="não é conta de robô"):
        ROBOS.responsavel("mario", db=db)
    with pytest.raises(ROBOS.Recusa, match="quem responde"):
        ROBOS.responsavel("robo_exemplo", responsavel="robo_exemplo", db=db)


def test_com_o_cofre_trancado_a_conta_nao_e_mexida(casa):
    db, cofre = casa["db"], casa["cofre"]
    cofre.aberto = False
    with pytest.raises(ROBOS.Recusa, match="trancado"):
        ROBOS.conta("robo_protesto", cofre="sistema_protesto", db=db)
    assert _um(db, "SELECT id FROM users WHERE username=%s", ("robo_protesto",)) is None
    assert cofre.itens == {} and _acoes(db, "USER_CREATED") == 0


def test_conta_de_pessoa_nao_se_toca_e_robo_nao_administra(casa):
    db = casa["db"]
    with pytest.raises(ROBOS.Recusa, match="PESSOA"):
        ROBOS.conta("mario", cofre="x", db=db)
    assert db.authenticate("mario", SENHA)                    # a senha do oficial segue a dele
    with pytest.raises(ROBOS.Recusa, match="USER ou AUDITOR"):
        ROBOS.conta("robo_chefe", papel="ADMIN", cofre="x", db=db)
    with pytest.raises(ROBOS.Recusa, match="criar-conta"):
        ROBOS.conta(INT.LOGIN, cofre="x", db=db)
    with pytest.raises(ROBOS.Recusa, match="Um dos dois"):
        ROBOS.conta("robo_x", db=db)
    with pytest.raises(ROBOS.Recusa, match="Um dos dois"):
        ROBOS.conta("robo_x", cofre="a", arquivo="b", db=db)
    with pytest.raises(ROBOS.Recusa, match="quem responde"):
        ROBOS.conta("robo_x", responsavel="ninguem", cofre="a", db=db)
    assert _um(db, "SELECT id FROM users WHERE username IN ('robo_chefe','robo_x')") is None


def test_ligar_rodar_e_semear_vao_pelas_funcoes_da_casa(casa):
    db, cofre = casa["db"], casa["cofre"]
    assert "Nenhum processo novo" in ROBOS.semear(db=db)       # a casa já os tem
    with db.transaction() as con:          # uma versão nova traz uma rotina que o banco não tem
        codigo = AU.listar(con)[0]["codigo"]
        banco(con).escrever("DELETE FROM au_processos WHERE codigo=%s", (codigo,))
    assert "1 processo(s) de fábrica cadastrado(s), todos desligados" in ROBOS.semear(db=db)
    with db.connect() as con:
        processo = AU.por_codigo(con, codigo)
    assert not processo["ativo"]
    assert "ligado" in ROBOS.processo("ligar", codigo, db=db)
    assert int(_um(db, "SELECT ativo FROM au_processos WHERE codigo=%s", (codigo,))["ativo"]) == 1
    assert "rodada pedida" in ROBOS.processo("rodar", codigo, db=db)
    pedido = _um(db, "SELECT pedido_manual_em, pedido_manual_por FROM au_processos WHERE codigo=%s",
                 (codigo,))
    assert pedido["pedido_manual_em"] and pedido["pedido_manual_por"] == INT.LOGIN
    assert "desligado" in ROBOS.processo("desligar", codigo, db=db)
    with pytest.raises(ROBOS.Recusa, match="Não há processo"):
        ROBOS.processo("ligar", "NAO_EXISTE", db=db)
    assert _acoes(db, "AUTOMACAO_RODAR_AGORA") == 1 and _acoes(db, "AUTOMACAO_ALTERADO") >= 2
    # a rotina que usa credencial fora do cofre liga, e avisa
    with db.transaction() as con:
        banco(con).escrever("UPDATE au_processos SET usa_credencial=%s WHERE codigo=%s",
                            ("cra_portal", codigo))
    assert "não está no cofre" in ROBOS.processo("ligar", codigo, db=db)
    cofre.itens["cra_portal"] = {"campos": {"usuario": "u", "senha": "s"}}
    assert "ATENÇÃO" not in ROBOS.processo("ligar", codigo, db=db)


def test_no_reserva_nada_se_configura(casa, monkeypatch):
    monkeypatch.setenv("CG_MODO_RESERVA", "1")
    for chamada in (lambda: ROBOS.conta("robo_x", cofre="a", db=casa["db"]),
                    lambda: ROBOS.processo("ligar", "QUALQUER", db=casa["db"]),
                    lambda: ROBOS.semear(db=casa["db"])):
        with pytest.raises(ROBOS.Recusa, match="principal"):
            chamada()


def test_o_operador_nunca_le_o_cofre():
    """A regra 2 do cofre: o segredo nunca vai ao modelo de IA. O operador
    grava e lista; quem lê é só o processo que usa a credencial."""
    for arquivo in sorted((RAIZ / "operador").glob("*.py")) + [RAIZ / "operador_web.py"]:
        fonte = arquivo.read_text(encoding="utf-8")
        assert not re.search(r"\b(COFRE|cofre)\.ler\(", fonte), arquivo.name
        assert "ler_com_chave" not in fonte and "conferir_senha" not in fonte, arquivo.name
