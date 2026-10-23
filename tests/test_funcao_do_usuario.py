"""
O ato tem de sair com o nome e a função de QUEM O PRATICOU.

O DEFEITO
    Os três módulos — notas, caixa e registro de imóveis — descobriam quem
    estava atendendo assim:

        getattr(request, "usuario_nome", None) or get_setting("ri_substituta")

    Nada no sistema jamais definiu `request.usuario_nome`. Não é uma linha que
    quebrou: é uma linha que nunca existiu. O `getattr` devolvia None em toda
    requisição, sempre, e o `or` caía na substituta do registro de imóveis.

    Todo ato novo saía assinado pela mesma pessoa, qualquer que fosse quem
    estivesse logado, e com a função "Escrevente" — porque a busca seguinte
    procurava no cadastro pelo NOME dela e caía no padrão. Cadastrar a função
    de cada um na tela Usuários não mudava nada, e não tinha como mudar.

POR QUE ISSO NÃO É DETALHE DE CADASTRO
    Quem assina por delegação tem de dizer em que qualidade o faz — Lei
    8.935/94, arts. 20 e 21. A função sai impressa embaixo da assinatura no
    reconhecimento de firma, na autenticação de cópia, no recibo, no orçamento,
    no protocolo de recepção e no comprovante de prenotação. Errada, é defeito
    de forma do ato.

O QUE ESTES TESTES PROTEGEM
    Que o nome e a função venham da SESSÃO, pelo id — e não de um atributo que
    ninguém define, nem de uma busca por nome, que não identifica pessoa.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from protocolo_de_teste import atender_protocolo_pago  # noqa: E402

SUBSTITUTA = "Beatriz Exemplo de Souza"


@pytest.fixture()
def serventia(cg_casa):
    """Duas pessoas de funções diferentes, e a substituta do RI configurada.

    **E UM SELADOR DE MENTIRA LIGADO, desde 16/09/2026.** Pelo relato #77 o
    ato que não sela é desfeito; sem aparelho nenhum não haveria ato onde ler
    o nome, e a prova deste arquivo — que o rodapé sai com quem está logado, e
    não com a substituta — nem chegaria a ser lida. O selador é o
    `tests/selador_falso.py`, o mesmo de `test_ato_selado`.
    """
    try:
        import cryptography              # noqa: F401
    except ImportError:
        pytest.skip("o selador de mentira precisa de `cryptography`")
    import selador_cliente as CL
    import selador_config as SC
    from selador_falso import SeladorFalso, impressao_digital

    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    d = cg_casa['db']
    d.create_user("tabeliao", "ANTONIO PEREIRA LIMA", "Senha#12345", "ADMIN")
    d.create_user("escrevente", "LAURA MARIA DA COSTA", "Senha#12345", "USER")
    d.set_settings({"ri_substituta": SUBSTITUTA,
                    "serventia_funcao_padrao": "Escrevente",
                    "ri_cns": "000000",
                    "selo_tabela_custas_em": "2026-01-01"})

    con = sqlite3.connect(banco)
    con.execute("UPDATE users SET funcao=? WHERE username=?",
                ("Tabelião e Oficial de Registro", "tabeliao"))
    con.execute("UPDATE users SET funcao=? WHERE username=?",
                ("Escrevente Autorizado", "escrevente"))
    # O SERVIÇO 413 COM O ITEM DA TABELA — medido na produção em 16/09/2026:
    # `codigo_tj = '13.17.2'`, o item que esta casa usou 518 vezes só em 2026.
    con.execute("""INSERT OR IGNORE INTO cx_servicos
                       (codigo, codigo_tj, descricao, descricao_norm, ativo)
                   VALUES (413, '13.17.2',
                           'Reconhecimento de firma, por assinatura',
                           'RECONHECIMENTO DE FIRMA, POR ASSINATURA', 1)""")
    # CADA UM ATENDE O SEU PROTOCOLO PAGO — desde o LX16 (19/10/2026) o selo
    # pago só sai com protocolo e pagamento, e a trava procura o item no
    # protocolo de QUEM está logado. Sem isto o selo nem é pedido, o
    # reconhecimento é desfeito e o nome no livro não chega a ser lido.
    for nome in ("ANTONIO PEREIRA LIMA", "LAURA MARIA DA COSTA"):
        atender_protocolo_pago(con, usuario=nome, codigos=("13.17.2",))
    con.commit()
    con.close()

    aparelho = SeladorFalso()
    aparelho.__enter__()
    SC.gravar_credencial(dados, "fulano.detal123", "abcde123",
                         agora="2026-08-17T09:00:00")
    CL.esquecer_tokens()
    con = sqlite3.connect(banco)
    with con:
        SC.gravar(con, base_url=aparelho.base, usuario="fulano.detal123",
                  agora="2026-08-17T09:00:00")
        CL.fixar_certificado(con, aparelho.base, sha256=impressao_digital(),
                             agora="2026-08-17T09:00:00", usuario="TESTE")
    con.close()
    try:
        yield {"app": app, "banco": banco}
    finally:
        aparelho.__exit__(None, None, None)


def entrar(app, usuario: str):
    c = app.test_client()
    pagina = c.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": token}, follow_redirects=True)
    return c


def quem(app, usuario: str) -> tuple[str, str]:
    """O nome e a função que o sistema usaria para lavrar, com esse login."""
    c = entrar(app, usuario)
    with app.test_request_context():
        pass
    # As funções vivem em app.extensions e leem a sessão — é dentro de uma
    # requisição autenticada que elas têm de ser perguntadas.
    with c.session_transaction() as sessao:
        uid = sessao.get("user_id")
    with app.test_request_context():
        from flask import session
        session["user_id"] = uid
        return (app.extensions["usuario_nome"](),
                app.extensions["usuario_funcao"]())


# ------------------------------------------------------------------- o nome

def test_o_ato_sai_com_o_nome_de_quem_esta_logado(serventia):
    app = serventia["app"]
    assert quem(app, "tabeliao")[0] == "ANTONIO PEREIRA LIMA"
    assert quem(app, "escrevente")[0] == "LAURA MARIA DA COSTA"


def test_nao_sai_mais_o_nome_da_substituta_para_todo_mundo(serventia):
    """O sintoma exato que o usuário relatou."""
    app = serventia["app"]
    for login in ("tabeliao", "escrevente"):
        assert quem(app, login)[0] != SUBSTITUTA


# ----------------------------------------------------------------- a função

def test_cada_um_sai_com_a_sua_funcao(serventia):
    app = serventia["app"]
    assert quem(app, "tabeliao")[1] == "Tabelião e Oficial de Registro"
    assert quem(app, "escrevente")[1] == "Escrevente Autorizado"


def test_sem_funcao_cadastrada_cai_no_padrao_da_serventia(serventia):
    """O único caso em que o padrão deve aparecer — e a tela Usuários avisa."""
    con = sqlite3.connect(serventia["banco"])
    con.execute("UPDATE users SET funcao=NULL WHERE username='escrevente'")
    con.commit()
    con.close()
    assert quem(serventia["app"], "escrevente")[1] == "Escrevente"


def test_a_funcao_nao_vem_mais_de_busca_por_nome(serventia):
    """Nome não identifica pessoa: dois homônimos casam na mesma linha.

    Antes a função era buscada com `WHERE full_name=? OR username=?`. Com dois
    usuários de mesmo nome e funções diferentes, quem lavrasse o ato receberia
    a função do outro — a do primeiro que o SELECT devolvesse.
    """
    from database import Database
    d = Database(serventia["banco"])
    d.create_user("joana2", "LAURA MARIA DA COSTA", "Senha#12345", "USER")
    con = sqlite3.connect(serventia["banco"])
    con.execute("UPDATE users SET funcao='Substituto' WHERE username='joana2'")
    con.commit()
    con.close()
    # Mesmo nome completo, funções diferentes: cada login traz a sua.
    assert quem(serventia["app"], "escrevente")[1] == "Escrevente Autorizado"
    assert quem(serventia["app"], "joana2")[1] == "Substituto"


# ------------------------------------------------------------- sem ninguém

def test_sem_sessao_e_rotina_de_fundo_e_nao_gente(serventia):
    """Backup e tarefa agendada não têm usuário logado. Antes ESTE era o
    caminho normal de toda requisição; agora é a exceção."""
    app = serventia["app"]
    with app.test_request_context():
        assert app.extensions["usuario_nome"]() == SUBSTITUTA


# ------------------------------------------------------- não voltar atrás

def test_nenhum_modulo_le_o_atributo_que_ninguem_define():
    """A linha que causou tudo isto não pode reaparecer em módulo nenhum.

    Ela existiu igual em três arquivos. Três cópias de uma regra é a garantia
    de que uma delas vai divergir — e foi assim que o defeito se espalhou por
    todos os documentos que a serventia emite.
    """
    for nome in ("notas_web.py", "caixa_web.py", "ri_web.py", "app.py"):
        codigo = (RAIZ / nome).read_text(encoding="utf-8")
        # Só o que é código: as linhas de comentário contam a história e devem
        # continuar podendo citá-la.
        vivas = [ln for ln in codigo.splitlines()
                 if 'getattr(request, "usuario_nome"' in ln
                 and not ln.lstrip().startswith("#")]
        assert not vivas, f"{nome} voltou a ler o atributo: {vivas}"


def test_a_tela_de_usuarios_avisa_quem_esta_sem_funcao(serventia):
    con = sqlite3.connect(serventia["banco"])
    con.execute("UPDATE users SET funcao=NULL WHERE username='escrevente'")
    con.commit()
    con.close()
    html = entrar(serventia["app"], "tabeliao").get("/usuarios").get_data(as_text=True)
    assert "sem função cadastrada" in html
    assert "LAURA MARIA DA COSTA" in html


def test_get_user_traz_a_funcao_junto(serventia):
    """Faltando aqui, quem monta o ato tem de ir buscá-la por conta própria —
    e foi indo pelo nome que o defeito começou."""
    from database import Database
    d = Database(serventia["banco"])
    uid = [u["id"] for u in d.list_users() if u["username"] == "tabeliao"][0]
    assert d.get_user(uid)["funcao"] == "Tabelião e Oficial de Registro"


# =================================================== a prova, no ato lavrado
#
# Os testes acima provam a função que devolve o nome. Este prova o que ficou
# GRAVADO NO LIVRO depois de um reconhecimento de firma feito pela tela — que
# é onde o defeito aparecia e o que o usuário relatou.

def _cartao_de_teste(banco, nome="MARIA DA SILVA", documento="52998224725"):
    con = sqlite3.connect(banco)
    con.execute(
        """INSERT INTO nt_cartoes (nome, nome_norm, documento, origem, ativo,
                                   abertura, criado_em)
           VALUES (?,?,?,'MANUAL',1,'2024-02-10','2026-08-17 09:00:00')""",
        (nome, nome, documento))
    con.commit()
    cid = con.execute("SELECT id FROM nt_cartoes WHERE nome=?", (nome,)).fetchone()[0]
    con.close()
    return cid


def _reconhecer(cliente, cartao_id):
    pagina = cliente.get("/notas/reconhecimento").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    # O ATO SÓ FICA DE PÉ COM SELO — relato #77, 16/09/2026. O `serventia`
    # sobe um selador de mentira exatamente para isto: sem ele a rota apaga o
    # ato e a `assert` que falha é «o reconhecimento não chegou a ser
    # lavrado», sem a prova do nome chegar a ser lida.
    #
    # ATÉ 16/09 ESTE TESTE MANDAVA `lavrar_sem_selo`, e o comentário daqui
    # dizia que era «o que a tela oferece a quem está no balcão com o selador
    # caído». A tela não oferece mais: ele mandou tirar a caixa de todo módulo.
    return cliente.post("/notas/reconhecimento",
                        data={"csrf_token": token, "acao": "reconhecer",
                              "cartao_id": str(cartao_id), "especie": "SEMELHANCA"},
                        follow_redirects=True)


def test_o_reconhecimento_lavrado_guarda_quem_reconheceu(serventia):
    cartao = _cartao_de_teste(serventia["banco"])
    _reconhecer(entrar(serventia["app"], "escrevente"), cartao)

    con = sqlite3.connect(serventia["banco"])
    con.row_factory = sqlite3.Row
    ato = con.execute("SELECT oficial, oficial_funcao FROM nt_reconhecimentos "
                      "ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert ato is not None, "o reconhecimento não chegou a ser lavrado"
    assert ato["oficial"] == "LAURA MARIA DA COSTA"
    assert ato["oficial_funcao"] == "Escrevente Autorizado"
    assert ato["oficial"] != SUBSTITUTA


def test_dois_usuarios_lavram_com_nomes_diferentes(serventia):
    """O coração do defeito: os dois atos saíam idênticos no rodapé."""
    app = serventia["app"]
    c1 = _cartao_de_teste(serventia["banco"], "MARIA DA SILVA", "52998224725")
    c2 = _cartao_de_teste(serventia["banco"], "PEDRO ALVES", "11144477735")
    _reconhecer(entrar(app, "tabeliao"), c1)
    _reconhecer(entrar(app, "escrevente"), c2)

    con = sqlite3.connect(serventia["banco"])
    con.row_factory = sqlite3.Row
    atos = list(con.execute("SELECT oficial, oficial_funcao FROM nt_reconhecimentos "
                            "ORDER BY id"))
    con.close()
    assert len(atos) == 2
    assert {a["oficial"] for a in atos} == {"ANTONIO PEREIRA LIMA",
                                           "LAURA MARIA DA COSTA"}
    assert {a["oficial_funcao"] for a in atos} == {"Tabelião e Oficial de Registro",
                                                  "Escrevente Autorizado"}
