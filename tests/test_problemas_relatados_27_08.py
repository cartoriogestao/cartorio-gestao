"""Os defeitos que o balcão relatou pela janela da ajuda em 27/08/2026.

Quatro chegaram no mesmo dia, e todos por ali — não por teste. Cada um vira
um teste aqui, com o nome de quem o achou e a frase que ele escreveu, porque
é a frase que diz o que a pessoa esperava.

O MAIOR DELES não parecia o maior: «erro: Reconhecimento nº 13215 lavrado —
1 firma(s). O ato foi lavrado SEM SELO: … O campo "nomesReconhecido" é
obrigatório; O campo "escrevente" é obrigatório». Eram os dois campos que nós
mandávamos — um nível abaixo de onde o aparelho os procurava. Com o embrulho,
**nenhum selo automático sairia, em atribuição nenhuma**.
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

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    c = cg_casa["cliente"]
    cg_casa["db"].create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    with sqlite3.connect(cg_casa["banco"]) as con:
        # A autenticação usa o serviço interno 415, cujo item TJMA é 13.18.
        # A bancada mede etiqueta/impressão, não ausência de cadastro.
        con.execute(
            """INSERT OR REPLACE INTO cx_servicos
                   (codigo, codigo_tj, descricao, ativo)
               VALUES (415,'13.18','Autenticação de cópia',1)""")
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


@pytest.fixture(autouse=True)
def _selador_da_bancada(cg_casa):
    """Atos alheios à falha de transporte usam o selador TLS de ensaio."""
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(cg_casa):
        yield

def _tarefa(casa, **campos) -> int:
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    dados = {"title": "Enviar declaração", "status": "ABERTA",
             "priority": "MEDIA", "evidence_required": 0,
             "created_at": "2026-08-27T10:00:00",
             "updated_at": "2026-08-27T10:00:00"}
    dados.update(campos)
    with con:
        cur = con.execute(
            f"INSERT INTO tasks ({','.join(dados)}) "
            f"VALUES ({','.join('?' * len(dados))})", tuple(dados.values()))
    return int(cur.lastrowid)


def _situacao(casa, task_id: int) -> str:
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con.execute("SELECT status FROM tasks WHERE id=?",
                       (task_id,)).fetchone()["status"]


# ------------------------------------------------------- «bad request error»
#
# «erro ao clicar em trazer as configurações do e-ofício para esse sistema»


def test_a_tela_do_selador_manda_o_token(casa):
    """Sem ele, os quatro cliques da configuração devolvem HTTP 400."""
    html = casa["cliente"].get("/selador").get_data(as_text=True)
    formularios = re.findall(r"<form\b[^>]*method=[\"']post[\"'].*?</form>",
                             html, re.S | re.I)
    assert formularios, "a tela do selador perdeu os formulários"
    assert all("csrf_token" in f for f in formularios)


# --------------------------------------------- «não estou achando o botão de
# concluir uma tarefa ou dar baixa»


def test_a_tarefa_tem_botao_de_concluir(casa):
    tid = _tarefa(casa)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    # 12/10/2026: a tarefa virou processo (ordem do oficial), e o botão diz isso
    assert "Concluir processo" in html


def test_concluir_num_clique(casa):
    tid = _tarefa(casa)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    casa["cliente"].post(f"/tarefas/{tid}",
                         data={"action": "concluir", "csrf_token": _token(html)},
                         follow_redirects=True)
    assert _situacao(casa, tid) == "CONCLUIDA"


def test_o_botao_nao_e_caminho_por_fora_da_evidencia(casa):
    """A regra existe porque tarefa sem prova é tarefa que não se demonstra."""
    tid = _tarefa(casa, evidence_required=1)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    r = casa["cliente"].post(f"/tarefas/{tid}",
                             data={"action": "concluir",
                                   "csrf_token": _token(html)},
                             follow_redirects=True)
    assert _situacao(casa, tid) == "ABERTA"
    assert "evidência" in r.get_data(as_text=True)


def test_tarefa_concluida_pode_ser_reaberta(casa):
    """Reabrir é a metade de volta — e, desde 17/09/2026 (relato #59), ela vem
    pela palavra que o sistema conhece e apaga o carimbo de conclusão."""
    tid = _tarefa(casa, status="CONCLUIDA",
                  completed_at="2026-08-27T11:00:00", completed_by=1)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Reabrir tarefa" in html
    casa["cliente"].post(f"/tarefas/{tid}",
                         data={"action": "reabrir",
                               "motivo": "O documento voltou com erro de digitação.",
                               "csrf_token": _token(html)},
                         follow_redirects=True)
    assert _situacao(casa, tid) == "ABERTA", (
        "`PENDENTE` não é palavra deste sistema: a tarefa saía do filtro "
        "«Abertas» e não voltava a nenhum")
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    linha = con.execute("SELECT completed_at, completed_by FROM tasks WHERE id=?",
                        (tid,)).fetchone()
    assert linha["completed_at"] is None and linha["completed_by"] is None, (
        "o carimbo de conclusão afirmava o dia em que o serviço terminou, e o "
        "serviço voltou a andar")


# ---------------------------------------------- «preciso apagar o texto da
# anterior, que segue no campo mesmo após a resposta»


def test_a_janela_da_ajuda_esvazia_o_campo_depois_da_resposta():
    janela = (RAIZ / "static" / "ajuda.js").read_text(encoding="utf-8")
    i = janela.index("mostrar(resposta.resposta")
    trecho = janela[i:i + 1400]
    assert 'campo.value = ""' in trecho, (
        "a pergunta antiga fica no campo, e a próxima nasce dentro dela")


def test_o_campo_nao_se_esvazia_quando_a_resposta_nao_veio():
    """Apagar a pergunta de quem vai tentar de novo é fazê-la digitar tudo outra vez."""
    janela = (RAIZ / "static" / "ajuda.js").read_text(encoding="utf-8")
    i = janela.index('|| "A ajuda nao respondeu."')
    assert 'campo.value = ""' not in janela[i:i + 400]


# ------------------------------- «O campo "nomesReconhecido" é obrigatório»
#
# O maior dos quatro, e o que nenhum teste tinha pego.


def test_o_corpo_do_pedido_de_selo_nao_vai_embrulhado():
    """Medido: dos 26.123 envelopes que esta casa mandou, ZERO vão embrulhados."""
    import selador as SD
    dados = {"escrevente": "JEAN",
             "nomesReconhecido": {"nomePartes": [], "parteAto": [
                 {"nome": "MARIA", "documento": "00000001082"}]},
             "natureza": {"tipo": 1},
             "ato": {"codigo": "13.17.2", "codigoTabelaCusta": "0520260101"}}
    corpo = SD.montar_pedido("/selo/notas/reconhecimento-firma", dados)["corpo"]
    assert corpo == dados
    # Os dois campos que o aparelho disse faltar têm de estar na RAIZ.
    assert "escrevente" in corpo
    assert "nomesReconhecido" in corpo


@pytest.mark.parametrize("caminho", [
    "/selo/notas/reconhecimento-firma",
    "/selo/notas/autenticacao",
    "/selo/notas/cartao-assinatura",
    "/selo/protesto/titulo",
    "/selo/civil/nascimento",
])
def test_nenhum_caminho_embrulha_o_corpo(caminho):
    """O defeito era de `montar_pedido`, e alcançava todas as atribuições."""
    import selador as SD
    dados = {"escrevente": "JEAN", "ato": {"codigo": "1"}}
    assert SD.montar_pedido(caminho, dados)["corpo"] == dados


# ------------------------- «Não foi encontrado um ato para o código informado»
#
# O segundo defeito do mesmo reconhecimento de firma, meia hora depois do
# primeiro: consertado o embrulho, o aparelho passou a validar mais fundo.


def test_a_versao_da_tabela_e_a_data_de_vigencia_e_nao_a_de_hoje():
    """`0520260101`, e não `0520260827`.

    A tabela de custas entra em vigor num dia e vale o ano inteiro. Mandar a
    data do ato produz uma versão que não existe no aparelho, e ele responde
    que não achou ato para o código — medido: esta casa usou `0520260101` com
    o item `13.17.2` **518 vezes só em 2026**.
    """
    import ato_selado as AS
    assert AS.versao_da_tabela_de_custas(
        "/selo/notas/reconhecimento-firma", "20260101") == "0520260101"
    # A data de um ato qualquer do meio do ano produz coisa diferente — e é
    # exatamente o que não pode ser mandado.
    assert AS.versao_da_tabela_de_custas(
        "/selo/notas/reconhecimento-firma", "2026-08-27") == "0520260827"


def test_nenhuma_tela_monta_a_versao_da_tabela_com_a_data_de_hoje():
    """A regra vale para as cinco atribuições, e por isso se varre.

    O engano cabe em qualquer módulo que sele: `versao_da_tabela_de_custas`
    pede a data de VIGÊNCIA, e `date.today()` está sempre à mão na mesma
    função. Quem tem de responder é a configuração `selo_tabela_custas_em`.
    """
    import re
    suspeitas = []
    for tela in sorted(RAIZ.glob("*_web.py")):
        texto = tela.read_text(encoding="utf-8")
        for m in re.finditer(r"versao_da_tabela_de_custas\((.{0,200}?)\)",
                             texto, re.S):
            if "today" in m.group(1) or "now(" in m.group(1):
                suspeitas.append(f"{tela.name}: {m.group(1).strip()[:70]}")
    assert not suspeitas, (
        "Estas chamadas montam a versão da tabela com a data de hoje. O "
        "selador responde «não foi encontrado um ato para o código "
        "informado», e o ato sai sem selo: " + " | ".join(suspeitas))


def test_sem_a_data_configurada_a_tela_diz_onde_informar(casa):
    """Recusa que não diz onde resolver faz o balcão parar sem saída."""
    import sqlite3 as sq
    con = sq.connect(casa["banco"])
    with con:
        con.execute("DELETE FROM settings WHERE key='selo_tabela_custas_em'")
        # O item da tabela do TJMA tem de existir, senão a recusa é a OUTRA —
        # a de serviço sem item — e o teste não chegaria ao que quer provar.
        con.execute("""INSERT OR REPLACE INTO cx_servicos
                       (codigo, codigo_tj, descricao, ativo)
                       VALUES (413,'13.17.2','Reconhecimento por assinatura',1)""")
    con2 = sq.connect(casa["banco"])
    con2.row_factory = sq.Row
    with con2:
        cur = con2.execute(
            """INSERT INTO nt_cartoes (nome, documento, criado_em)
               VALUES ('MARIA','00000001082',datetime('now'))""")
        cid = int(cur.lastrowid)
    html = casa["cliente"].get("/notas/reconhecimento").get_data(as_text=True)
    r = casa["cliente"].post(
        "/notas/reconhecimento",
        data={"acao": "reconhecer", "cartao_id": [str(cid)],
              "especie": "SEMELHANCA", "csrf_token": _token(html)},
        follow_redirects=True)
    texto = r.get_data(as_text=True)
    assert "NÃO lavrado" in texto
    assert "tabela de custas" in texto
    # A falha fica à vista e não deixa um ato incompleto no livro.
    assert sq.connect(casa["banco"]).execute(
        "SELECT COUNT(*) FROM nt_reconhecimentos").fetchone()[0] == 0


# ----------- «O selo saiu, mas não consegui amarrá-lo ao ato (vincular()
#              missing 1 required keyword-only argument: 'agora')»
#
# O pior momento possível para um defeito: o selo JÁ FOI COMPRADO. Ele existe,
# foi pago, e não está em ato nenhum — que é como o E-Ofício acumulou 1.304
# órfãos.


def test_amarrar_o_selo_ao_ato_marca_a_hora(casa):
    """Sem `usado_em`, o selo não se distingue de um que nunca foi usado."""
    import sqlite3 as sq
    import ato_selado as AS
    con = sq.connect(casa["banco"])
    con.row_factory = sq.Row
    numero = "RECFIR000000AAAAAAAAAAAAAAAA"
    with con:
        con.execute(
            """INSERT INTO sd_selos (numero, sid, caminho, atribuicao,
                   referencia, obtido_em)
               VALUES (?,?,?,?,?,?)""",
            (numero, "sid-1", "/selo/notas/reconhecimento-firma", "NOTAS",
             "x", "2026-08-27T18:40:03"))
        con.execute(
            """INSERT INTO nt_reconhecimentos (id, data, hora, especie,
                   servico_codigo, quantidade, oficial, criado_em)
               VALUES (1,'2026-08-27','18:40','SEMELHANCA',413,1,'JEAN',
                       '2026-08-27T18:40:03')""")
        AS.vincular_ao_ato(con, numero, tabela="nt_reconhecimentos",
                           ato_id=1, agora="2026-08-27T18:40:05")
    linha = con.execute("SELECT * FROM sd_selos WHERE numero=?",
                        (numero,)).fetchone()
    assert linha["usado_em"] == "2026-08-27T18:40:05"
    assert linha["tabela"] == "nt_reconhecimentos" and linha["ato_id"] == 1
    assert con.execute("SELECT selo FROM nt_reconhecimentos WHERE id=1"
                       ).fetchone()["selo"] == numero


@pytest.mark.parametrize("tabela,coluna", [
    ("nt_cartoes", "selo_abertura"),
    ("ri_atos", "selo_texto"),
])
def test_as_duas_tabelas_que_nao_chamam_a_coluna_de_selo(casa, tabela, coluna):
    """Supor `selo` para todas fazia a amarração estourar nestas duas.

    E estourar DEPOIS de o selo ter sido comprado — o selo existe, foi pago, e
    não fica em ato nenhum.
    """
    import sqlite3 as sq
    import ato_selado as AS
    assert AS.COLUNA_DO_SELO[tabela] == coluna
    con = sq.connect(casa["banco"])
    colunas = [c[1] for c in con.execute(f"PRAGMA table_info({tabela})")]
    assert coluna in colunas and "selo" not in colunas


def test_toda_tabela_de_ato_tem_onde_guardar_o_selo(casa):
    """Tabela nova sem lugar para o selo fica vermelha aqui — e não no balcão."""
    import sqlite3 as sq
    import ato_selado as AS
    con = sq.connect(casa["banco"])
    sem = []
    for tabela in AS.TABELAS_DE_ATO:
        colunas = [c[1] for c in con.execute(f"PRAGMA table_info({tabela})")]
        if not colunas:
            continue                       # tabela de outro módulo, não criada
        alvo = AS.COLUNA_DO_SELO.get(tabela, "selo")
        if alvo not in colunas:
            sem.append(f"{tabela} (procurei `{alvo}`, tem {colunas})")
    assert not sem, ("Estas tabelas de ato não têm onde guardar o número do "
                     "selo. A amarração estoura DEPOIS da compra: " + "; ".join(sem))


# --------- «a aba ajuda fica acumulando itens de notificação que eu não
#            entendo. Está com 2 e não sei o que é»


def test_a_marca_da_ajuda_diz_o_que_ela_conta(casa):
    """Número sozinho não diz nada, e o rótulo no `title` exige parar o mouse."""
    import sqlite3 as sq
    con = sq.connect(casa["banco"])
    with con:
        for n in (1, 2):
            con.execute(
                """INSERT INTO aj_problemas (impressao, origem, onde, caminho,
                       titulo, versao, vezes, primeira_em, ultima_em, situacao)
                   VALUES (?,?,?,?,?,?,1,?,?, 'ABERTO')""",
                (f"marca{n}", "RELATADO", "dashboard", "/",
                 f"defeito {n}", "3.6.20", "2026-08-27T18:00:00",
                 "2026-08-27T18:00:00"))
    html = casa["cliente"].get("/").get_data(as_text=True)
    assert "2 relatos" in html, (
        "a marca mostra só o número, e quem a vê não sabe o que ela conta")
    # E a gaveta diz de onde vem a lista e como ela some.
    assert "ainda em aberto" in html
    assert "marque como resolvido" in html


def test_um_relato_so_nao_vira_plural(casa):
    """«1 relatos» é o tipo de detalhe que faz a tela parecer de brinquedo."""
    import sqlite3 as sq
    con = sq.connect(casa["banco"])
    with con:
        con.execute(
            """INSERT INTO aj_problemas (impressao, origem, onde, caminho,
                   titulo, versao, vezes, primeira_em, ultima_em, situacao)
               VALUES ('so-um','RELATADO','dashboard','/','defeito','3.6.20',
                       1,'2026-08-27T18:00:00','2026-08-27T18:00:00','ABERTO')""")
    html = casa["cliente"].get("/").get_data(as_text=True)
    assert "1 relato<" in html or "1 relato " in html
    assert "1 relatos" not in html


# ------------------- «gera o selo de autenticação de cópia, mas não dá opção
#                      de imprimir a etiqueta»


def _autenticar(casa, folhas: int = 1):
    html = casa["cliente"].get("/notas/autenticacao").get_data(as_text=True)
    casa["cliente"].post("/notas/autenticacao",
                         data={"acao": "autenticar", "folhas": str(folhas),
                               "tipo": "PADRAO", "csrf_token": _token(html)},
                         follow_redirects=True)
    import sqlite3 as sq
    con = sq.connect(casa["banco"])
    return int(con.execute("SELECT MAX(id) FROM nt_autenticacoes").fetchone()[0])


def test_a_autenticacao_com_selo_oferece_a_etiqueta(casa):
    import sqlite3 as sq
    aid = _autenticar(casa)
    con = sq.connect(casa["banco"])
    with con:
        con.execute("UPDATE nt_autenticacoes SET selo=? WHERE id=?",
                    ("AUTENT000000AAAAAAAAAAAAAAAA", aid))
    html = casa["cliente"].get("/notas/autenticacao").get_data(as_text=True)
    assert f"/notas/autenticacao/{aid}/etiqueta" in html


def test_sem_selo_nao_se_oferece_etiqueta(casa):
    """Etiqueta sem número é papel que parece conferível e não é."""
    import sqlite3 as sq
    aid = _autenticar(casa)
    with sq.connect(casa["banco"]) as con:
        con.execute("UPDATE nt_autenticacoes SET selo=NULL WHERE id=?", (aid,))
    html = casa["cliente"].get("/notas/autenticacao").get_data(as_text=True)
    assert f"/notas/autenticacao/{aid}/etiqueta" not in html


def test_a_etiqueta_da_autenticacao_conta_a_impressao(casa):
    """Segunda via é o mesmo selo em dois papéis — a conferência tem de ver."""
    import sqlite3 as sq
    aid = _autenticar(casa)
    con = sq.connect(casa["banco"])
    con.row_factory = sq.Row
    with con:
        con.execute("UPDATE nt_autenticacoes SET selo=? WHERE id=?",
                    ("AUTENT000000AAAAAAAAAAAAAAAA", aid))
    for esperado in (1, 2):
        casa["cliente"].get(f"/notas/autenticacao/{aid}/etiqueta")
        n = con.execute("SELECT etiqueta_impressoes n FROM nt_autenticacoes "
                        "WHERE id=?", (aid,)).fetchone()["n"]
        assert n == esperado


# ------------- «tire o espaço do "em test da verdade". não gosto de espaço»


def test_o_fecho_da_etiqueta_nao_tem_o_traco():
    from notas_schema import FECHO_ETIQUETA
    assert FECHO_ETIQUETA == "EM TEST. DA VERDADE."
    assert "_" not in FECHO_ETIQUETA


# ============ O QUE O OFICIAL RELATOU DEPOIS, E FOI ATENDIDO EM 28/08 ============


def test_as_tabelas_tem_listras(tmp_path=None):
    """«Layout das caixas de seleção muito separadas, falta listras nas
    tabelas» — o oficial, pela janela da ajuda.

    Listra em tabela não é enfeite: numa tabela larga, como a dos lançamentos
    do caixa, é o que impede o olho de pular de linha no meio do caminho.
    """
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "static" / "app.css"
           ).read_text(encoding="utf-8")
    assert "tbody tr:nth-child(even) td" in css


def test_a_linha_sob_o_mouse_continua_acendendo_nas_pares():
    """O defeito que a correção quase criou: `tr:hover td` é MENOS específico
    que `tbody tr:nth-child(even) td`, e sozinho perderia — a linha sob o
    mouse deixaria de acender justamente nas pares, que são metade delas."""
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "static" / "app.css"
           ).read_text(encoding="utf-8")
    assert "tbody tr:nth-child(even):hover td" in css


def test_os_campos_do_formulario_ficaram_mais_juntos():
    """Eram 18px entre campos no `grid2`. Num formulário de dez campos isso
    empurra metade deles para fora da tela, e quem preenche rola para achar o
    próximo."""
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "static" / "app.css"
           ).read_text(encoding="utf-8")
    assert ".grid2{display:grid;grid-template-columns:1fr 1fr;gap:11px 16px}" in css
