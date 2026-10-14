"""O que começou e não terminou — a lente sobre as nove fontes.

O TESTE QUE VALE MAIS QUE OS OUTROS
    **`test_toda_fonte_tem_consulta_que_roda`.** Ele executa a consulta de cada
    fonte declarada contra o esquema de verdade. Sem ele, uma fonte com nome de
    coluna errado só apareceria como lista vazia — e ninguém repara em item que
    deixou de aparecer.

    Não é hipótese: escrevi `a.folha` em `rc_funai` nesta mesma manhã, pedindo
    de `rc_assentos` uma coluna que mora em `rc_atos`. Ali quem me avisou foi o
    painel das comunicações, que não engole erro; aqui o guarda é este teste.

O SEGUNDO É O IRMÃO DELE
    **`test_toda_fonte_leva_a_uma_tela_que_existe`.** Duas das nove apontavam
    para rota inexistente ou com outro parâmetro quando eu as escrevi. O link
    quebrado só aparece quando alguém clica — e no RI, um `id` que não serve à
    tela abre a ficha de **outro imóvel**.
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — DROP TABLE + suite larga
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import inacabados as IN                                          # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-20T09:00"
HOJE = "2026-08-20"


@pytest.fixture()
def casa(tmp_path):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(banco)
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    return {"app": app, "banco": banco, "db": db}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------ os dois guardas


def test_toda_fonte_tem_consulta_que_roda(casa):
    """SEM ESTE TESTE, fonte com coluna errada vira lista vazia — e ninguém
    repara em item que deixou de aparecer."""
    con = _con(casa)
    for f in IN.FONTES:
        try:
            con.execute(IN.consulta_da_fonte(f)).fetchall()
        except sqlite3.Error as erro:
            pytest.fail(f"a fonte «{f['chave']}» não roda: {erro}\n"
                        f"  {IN.consulta_da_fonte(f)}")


def test_toda_fonte_leva_a_uma_tela_que_existe(casa):
    """Duas das nove apontavam para rota inexistente quando eu as escrevi. O
    link quebrado só aparece quando alguém clica — e no RI, um `id` que não
    serve à tela abre a ficha de OUTRO imóvel."""
    rotas = {r.endpoint: sorted(r.arguments)
             for r in casa["app"].url_map.iter_rules()}
    for f in IN.FONTES:
        assert f["tela"] in rotas, \
            f"a fonte «{f['chave']}» aponta para a tela «{f['tela']}», que não existe"
        assert f["parametro"] in rotas[f["tela"]], \
            (f"«{f['tela']}» espera {rotas[f['tela']]} e a fonte «{f['chave']}» "
             f"passa «{f['parametro']}»")


# ------------------------------------------------ as fontes são declaradas


def test_cada_fonte_diz_as_quatro_coisas():
    """Onde o ato mora, o que o começou, o que o termina, e quantos dias sem
    andar. Nenhuma delas se inventa."""
    for f in IN.FONTES:
        assert f["tabela"], f"{f['chave']} sem tabela"
        assert f["onde"], f"{f['chave']} sem a condição que o faz existir"
        assert f["terminou"], f"{f['chave']} não diz o que o tira da lista"
        assert f["dias"] >= 1, f"{f['chave']} com prazo de zero dias"
        assert f["atribuicao"], f"{f['chave']} sem atribuição"


def test_as_chaves_nao_se_repetem():
    assert len(set(IN.CHAVES)) == len(IN.FONTES)


def test_o_que_ele_nao_faz_esta_escrito():
    """Para quem for mexer nele depois."""
    junto = " ".join(IN.NAO_FAZ)
    assert "não conclui" in junto
    assert "não cria expediente" in junto


# ------------------------------------------------ a configuração


def test_sem_ajuste_vale_o_padrao_do_codigo(casa):
    """O CÓDIGO É O PISO; A TABELA É O AJUSTE. Instalação nova nasce
    funcionando, e «voltar ao padrão» é apagar a linha."""
    config = IN.configuracao(_con(casa))
    assert len(config) == len(IN.FONTES)
    assert all(x["ligada"] for x in config.values())
    assert not any(x["ajustada"] for x in config.values())
    assert config["BALCAO_PROTOCOLO"]["dias"] == 30


def test_desligar_uma_fonte_a_tira_da_lista(casa):
    """É o «o que fica, o que sai» que o oficial pediu."""
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao,
                   interessado, situacao, criado_em)
               VALUES ('1','2026-01-05','NOTAS','MARIA','ABERTO',?)""",
            (AGORA,))
    assert any(x["chave"] == "BALCAO_PROTOCOLO"
               for x in IN.lista(con, hoje=HOJE))
    with con:
        IN.ajustar(con, "BALCAO_PROTOCOLO", ligada=False, dias=30,
                   agora=AGORA, por="jean")
    assert not any(x["chave"] == "BALCAO_PROTOCOLO"
                   for x in IN.lista(con, hoje=HOJE))


def test_desligada_nao_volta_a_ligar_sozinha(casa):
    """`ajuste.get("ligada") or padrão` religaria o que o oficial desligou,
    porque **zero é falso**. É o mesmo `str(v or "")` que comia o zero na remessa
    do SIRC, custando outra coisa: lá a quantidade virava «não sei»; aqui a fonte
    desligada voltaria a gritar."""
    con = _con(casa)
    with con:
        IN.ajustar(con, "TAREFA", ligada=False, dias=15, agora=AGORA,
                   por="jean")
    assert IN.configuracao(con)["TAREFA"]["ligada"] is False


def test_mudar_os_dias_muda_quem_esta_parado(casa):
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao,
                   interessado, situacao, criado_em)
               VALUES ('1','2026-08-05','NOTAS','MARIA','ABERTO',?)""",
            (AGORA,))
    def _parado():
        return [x for x in IN.lista(con, hoje=HOJE)
                if x["chave"] == "BALCAO_PROTOCOLO"][0]["parado"]
    assert not _parado()                       # 15 dias, limite de 30
    with con:
        IN.ajustar(con, "BALCAO_PROTOCOLO", ligada=True, dias=10, agora=AGORA,
                   por="jean")
    assert _parado()


def test_prazo_de_zero_dias_recusa(casa):
    """Com zero, tudo apareceria como parado no mesmo dia em que entrou."""
    con = _con(casa)
    with pytest.raises(IN.InacabadoError):
        with con:
            IN.ajustar(con, "TAREFA", ligada=True, dias=0, agora=AGORA,
                       por="jean")


def test_fonte_que_nao_existe_recusa(casa):
    con = _con(casa)
    with pytest.raises(IN.InacabadoError):
        with con:
            IN.ajustar(con, "NAO_EXISTE", ligada=True, dias=5, agora=AGORA,
                       por="jean")


def test_voltar_ao_padrao_apaga_a_linha(casa):
    con = _con(casa)
    with con:
        IN.ajustar(con, "TAREFA", ligada=False, dias=99, agora=AGORA,
                   por="jean")
    assert IN.configuracao(con)["TAREFA"]["ajustada"]
    with con:
        IN.voltar_ao_padrao(con, "TAREFA")
    config = IN.configuracao(con)["TAREFA"]
    assert not config["ajustada"]
    assert config["ligada"] and config["dias"] == 15


# ------------------------------------------------ a lista mede na hora


def test_o_concluido_sai_da_lista_sozinho(casa):
    """É O CORAÇÃO DO DESENHO. A lista é a pergunta, e não a resposta guardada —
    é isso que impede o defeito do relato #24: a tarefa concluída e o expediente
    ainda aberto."""
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO tasks (title, status, created_at, updated_at)
               VALUES ('conferir o livro','ABERTA',?,?)""", (AGORA, AGORA))
        tid = int(cur.lastrowid)
    assert any(x["chave"] == "TAREFA" for x in IN.lista(con, hoje=HOJE))
    with con:
        con.execute("UPDATE tasks SET completed_at=? WHERE id=?",
                    (AGORA, tid))
    assert not any(x["chave"] == "TAREFA" for x in IN.lista(con, hoje=HOJE))


def test_o_mais_parado_vem_primeiro(casa):
    con = _con(casa)
    with con:
        con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                       VALUES ('nova','2026-08-19','2026-08-19')""")
        con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                       VALUES ('velha','2026-01-05','2026-01-05')""")
    lista = IN.lista(con, hoje=HOJE)
    assert lista[0]["rotulo"] == "velha"


def test_item_sem_data_vai_para_o_fim_e_nao_vira_zero(casa):
    """Zero diria «entrou hoje», que é afirmação; não saber é outra coisa."""
    con = _con(casa)
    with con:
        con.execute("INSERT INTO tasks (title, created_at, updated_at) "
                    "VALUES ('sem','','')")
        con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                       VALUES ('com','2026-08-19','2026-08-19')""")
    lista = IN.lista(con, hoje=HOJE)
    assert lista[-1]["rotulo"] == "sem"
    assert lista[-1]["dias"] is None
    assert not lista[-1]["parado"]


def test_filtrar_por_atribuicao(casa):
    """Para o balcão do civil não ver a fila do protesto."""
    con = _con(casa)
    with con:
        con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                       VALUES ('tarefa','2026-08-19','2026-08-19')""")
    assert IN.lista(con, hoje=HOJE, atribuicao="ADMINISTRATIVO")
    assert IN.lista(con, hoje=HOJE, atribuicao="RCPN") == []


def test_so_parados(casa):
    con = _con(casa)
    with con:
        con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                       VALUES ('ontem','2026-08-19','2026-08-19')""")
        con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                       VALUES ('velha','2026-01-05','2026-01-05')""")
    assert len(IN.lista(con, hoje=HOJE)) == 2
    so = IN.lista(con, hoje=HOJE, so_parados=True)
    assert [x["rotulo"] for x in so] == ["velha"]


def test_fonte_que_nao_responde_nao_vira_lista_vazia(casa):
    """Uma tabela renomeada faria a lista encolher em silêncio — e ninguém repara
    em item que deixou de aparecer."""
    con = _con(casa)
    with con:
        con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                       VALUES ('tarefa','2026-08-19','2026-08-19')""")
    con.execute("DROP TABLE IF EXISTS expedientes")
    lista = IN.lista(con, hoje=HOJE)
    ruins = [x for x in lista if x["erro"]]
    assert len(ruins) == 1
    assert ruins[0]["chave"] == "EXPEDIENTE"
    assert "não deu para medir" in ruins[0]["erro"]
    # e o resto continua saindo — meia lista é melhor que lista nenhuma
    assert any(x["rotulo"] == "tarefa" for x in lista)


# ------------------------------------------------ o resumo


def test_o_resumo_conta_por_fonte(casa):
    con = _con(casa)
    with con:
        con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                       VALUES ('ontem','2026-08-19','2026-08-19')""")
        con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                       VALUES ('velha','2026-01-05','2026-01-05')""")
    por_chave = {x["chave"]: x for x in IN.resumo(con, hoje=HOJE)}
    assert por_chave["TAREFA"]["quantos"] == 2
    assert por_chave["TAREFA"]["parados"] == 1
    assert por_chave["EXPEDIENTE"]["quantos"] == 0


def test_o_resumo_traz_todas_as_fontes_mesmo_as_vazias(casa):
    """Fonte que some do resumo quando está vazia faz o operador achar que ela
    não existe."""
    assert len(IN.resumo(_con(casa), hoje=HOJE)) == len(IN.FONTES)


# ------------------------------------------------ a anotação


def test_anotar_e_o_unico_dado_novo(casa):
    con = _con(casa)
    with con:
        cur = con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                             VALUES ('conferir','2026-08-19','2026-08-19')""")
        tid = int(cur.lastrowid)
        IN.anotar(con, tabela="tasks", item_id=tid,
                  texto="esperando o documento do requerente",
                  responsavel="Debora", ate="2026-09-10",
                  agora=AGORA, por="jean")
    item = [x for x in IN.lista(con, hoje=HOJE) if x["id"] == tid][0]
    assert item["anotacao"]["texto"] == "esperando o documento do requerente"
    assert item["anotacao"]["responsavel"] == "Debora"


def test_anotar_duas_vezes_atualiza_em_vez_de_duplicar(casa):
    """Duas anotações fariam a tela mostrar uma e o operador ter escrito a
    outra."""
    con = _con(casa)
    with con:
        cur = con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                             VALUES ('conferir','2026-08-19','2026-08-19')""")
        tid = int(cur.lastrowid)
        IN.anotar(con, tabela="tasks", item_id=tid, texto="primeira",
                  agora=AGORA, por="jean")
        IN.anotar(con, tabela="tasks", item_id=tid, texto="segunda",
                  agora=AGORA, por="jean")
    assert con.execute("SELECT COUNT(*) FROM ex_anotacoes").fetchone()[0] == 1
    item = [x for x in IN.lista(con, hoje=HOJE) if x["id"] == tid][0]
    assert item["anotacao"]["texto"] == "segunda"


def test_anotacao_vazia_recusa(casa):
    con = _con(casa)
    with pytest.raises(IN.InacabadoError):
        with con:
            IN.anotar(con, tabela="tasks", item_id=1, texto="  ",
                      agora=AGORA, por="jean")


def test_nao_se_anota_em_tabela_que_nao_e_fonte(casa):
    """A anotação não tem chave estrangeira — aponta para nove tabelas, e uma FK
    só pode apontar para uma. Quem garante que a tabela é válida é esta recusa."""
    con = _con(casa)
    with pytest.raises(IN.InacabadoError) as erro:
        with con:
            IN.anotar(con, tabela="users", item_id=1, texto="qualquer",
                      agora=AGORA, por="jean")
    assert "não é uma das fontes" in str(erro.value)


def test_apagar_a_anotacao_nao_tira_o_item_da_lista(casa):
    """Quem tira o item de lá é a conclusão do ato, na tela dele. Se apagar a
    anotação sumisse com o item, a lista viraria gaveta — que é exatamente o que
    este módulo não é."""
    con = _con(casa)
    with con:
        cur = con.execute("""INSERT INTO tasks (title, created_at, updated_at)
                             VALUES ('conferir','2026-08-19','2026-08-19')""")
        tid = int(cur.lastrowid)
        IN.anotar(con, tabela="tasks", item_id=tid, texto="algo",
                  agora=AGORA, por="jean")
        IN.apagar_anotacao(con, tabela="tasks", item_id=tid)
    item = [x for x in IN.lista(con, hoje=HOJE) if x["id"] == tid][0]
    assert item["anotacao"] is None


# ------------------------------------------------ o módulo não conclui


def test_o_modulo_nao_conclui_nada():
    """Mostra e leva à tela do ato — concluir é lá, com as regras de lá. É a
    quarta vez que esta regra aparece: usucapião, fraudes, habilitação, e agora."""
    publicos = [n for n in dir(IN)
                if not n.startswith("_") and callable(getattr(IN, n))]
    for nome in publicos:
        for proibido in ("concluir", "encerrar", "finalizar", "arquivar",
                         "lavrar"):
            assert proibido not in nome.lower(), f"`{nome}` faz o que não deve"


def test_o_modulo_nao_cria_expediente():
    """O ato já é o registro; uma linha ao lado dele seriam dois lugares
    guardando o mesmo fato, e a cópia diverge no primeiro conserto."""
    codigo = (RAIZ / "inacabados.py").read_text(encoding="utf-8")
    for proibido in ("INSERT INTO expedientes", "INSERT INTO tasks",
                     "INSERT INTO cx_protocolos"):
        assert proibido not in codigo, f"o módulo escreve com «{proibido}»"


def test_o_modulo_so_escreve_nas_duas_tabelas_dele():
    """Todo o resto ele mede."""
    import re
    codigo = (RAIZ / "inacabados.py").read_text(encoding="utf-8")
    # `UPDATE\s+(\w+)` SOZINHO BATE EM «DO UPDATE SET», do `ON CONFLICT` — e
    # foi o que aconteceu na primeira vez que rodei este teste: ele acusou o
    # modulo de escrever numa tabela chamada «SET». **Varredor procura a FORMA,
    # e nunca a palavra solta que tambem cabe noutra frase** — quarta vez que
    # esta licao volta neste projeto.
    escritas = re.findall(
        r"(?:INSERT INTO|DELETE FROM|(?<!DO )UPDATE)\s+(\w+)", codigo)
    escritas = [x for x in escritas if x != "SET"]
    assert set(escritas) <= {"ex_fontes", "ex_anotacoes"}, \
        f"ele escreve fora das tabelas dele: {set(escritas)}"
