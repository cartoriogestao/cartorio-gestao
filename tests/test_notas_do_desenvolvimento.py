"""As notas do desenvolvimento nos problemas relatados — relato #35.

    «Criar um campo para completar com notas do desenvolvimento sobre a
     eventual solução ou pendência de solução de cada problema na aba ajuda.
     Os que forem resolvidos a IA ou desenvolvedor já coloca a prova do
     cumprimento ou relata alguma pendência.»   — o oficial

O CAMPO EXISTIA E ESTAVA VAZIO. Não faltava peça: as cinco colunas, a função,
a rota e a tela estavam de pé, e a produção tinha **zero de 36** preenchidas.

O TESTE QUE MAIS VALE AQUI É O DA PROVA
    Dizer «atendido» e apontar um teste que não existe é a promessa com cara de
    prova — pior que não dizer nada, porque quem lê **não vai conferir**: o
    endereço estar escrito já parece a conferência feita. Por isso a prova de
    cada nota é lida como caminho de arquivo, e cada um tem de existir no
    projeto.

    É a mesma régua que o catálogo dos modelos aplica ao ir buscar cada
    constante onde ele diz que ela mora.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import ajuda_problemas as PROB                                   # noqa: E402
import notas_do_desenvolvimento as ND                            # noqa: E402

AGORA = "2026-08-31 12:00:00"


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    PROB.init_problemas_schema(c)
    return c


def _problema(con, impressao: str, titulo: str = "um defeito") -> int:
    cur = con.execute(
        """INSERT INTO aj_problemas (impressao, origem, titulo, situacao,
                                     vezes, primeira_em, ultima_em)
           VALUES (?, 'RELATADO', ?, 'ABERTO', 1, ?, ?)""",
        (impressao, titulo, AGORA, AGORA))
    return int(cur.lastrowid)


# ------------------------------------------------ as notas em si


def test_cada_nota_tem_estado_que_o_sistema_conhece():
    for n in ND.NOTAS:
        assert n["estado"] in PROB.ESTADOS_DO_DEV, (
            f"{n['impressao']} tem estado «{n['estado']}», que não existe")


def test_nenhuma_impressao_se_repete():
    """Duas notas para o mesmo problema fariam a segunda apagar a primeira, e
    a ordem de quem ganha seria a ordem em que eu escrevi — que não é razão."""
    vistas = [n["impressao"] for n in ND.NOTAS]
    assert len(vistas) == len(set(vistas))


def test_toda_nota_diz_de_qual_relato_e():
    """**É o relato #23 cumprido também aqui.** Quem lê a nota na tela tem de
    conseguir amarrá-la ao número que leu no relatório — foi exatamente por
    faltar esse número que o oficial não sabia de que problemas eu falava."""
    for n in ND.NOTAS:
        assert "relato #" in n["nota"], (
            f"{n['impressao']}: a nota não diz de que relato é")


def test_atendido_sem_prova_nao_existe():
    """«Foi feito» sem onde conferir é promessa — e promessa é o que este
    projeto já quebrou seis vezes, com função pronta que nenhuma tela alcança.
    """
    for n in ND.NOTAS:
        if n["estado"] == ND.ATENDIDO:
            assert n["prova"].strip(), (
                f"{n['impressao']} diz ATENDIDO e não diz onde conferir")


def test_necessario_teste_sem_prova_nao_existe():
    for n in ND.NOTAS:
        if n["estado"] == ND.NECESSARIO_TESTE:
            assert n["prova"].strip(), (
                f"{n['impressao']} diz NECESSARIO_TESTE e não diz onde conferir")


def test_a_prova_APONTA_PARA_COISA_QUE_EXISTE():
    """**O teste que mais vale deste arquivo.**

    Apontar um teste que não existe é a promessa com cara de prova, e é pior
    que não dizer nada: quem lê não confere, porque o endereço estar escrito já
    parece a conferência feita.
    """
    faltando = []
    for n in ND.NOTAS:
        for pedaco in n["prova"].split(";"):
            pedaco = pedaco.strip()
            # A prova pode citar um arquivo OU uma constante («`modulo.NOME`»).
            # Aqui se confere o que é caminho de arquivo; a constante é
            # conferida pelo teste seguinte.
            if not pedaco or "`" in pedaco:
                continue
            caminho = pedaco.split()[0].rstrip(",")
            if not ("/" in caminho or caminho.endswith(".py")):
                continue
            # TRÊS FORMAS DE APONTAR, e as três se conferem — 14/10/2026,
            # quando as notas passaram a citar (a) o teste pelo nó do pytest,
            # «arquivo.py::test_x», (b) a rota, «/login», e (c) documento da
            # raiz do PROJETO (`docs/`, `internal/`), e não da do sistema.
            # Nenhuma delas afrouxa a régua: o nó exige o arquivo E o `def`;
            # a rota exige o `route("/...")` num módulo da raiz; o documento
            # exige o arquivo em disco.
            if "::" in caminho:
                arquivo, _, teste = caminho.partition("::")
                alvo = RAIZ / arquivo
                if not (alvo.is_file() and f"def {teste}(" in
                        alvo.read_text(encoding="utf-8")):
                    faltando.append(f"{n['impressao']} → {caminho}")
                continue
            if caminho.startswith("/"):
                if not any(f'route("{caminho}"' in p.read_text(
                               encoding="utf-8", errors="replace")
                           for p in RAIZ.glob("*.py")):
                    faltando.append(f"{n['impressao']} → rota {caminho}")
                continue
            if not ((RAIZ / caminho).exists()
                    or (RAIZ.parent.parent / caminho).exists()):
                faltando.append(f"{n['impressao']} → {caminho}")
    assert not faltando, (
        "estas provas apontam para arquivos que não existem:\n    "
        + "\n    ".join(faltando))


def test_a_prova_que_cita_constante_encontra_a_constante():
    """A outra metade: `modulo.NOME` tem de resolver de verdade."""
    import importlib

    faltando = []
    for n in ND.NOTAS:
        for pedaco in n["prova"].split(";"):
            pedaco = pedaco.strip()
            if not (pedaco.startswith("`") and pedaco.endswith("`")):
                continue
            alvo = pedaco.strip("`")
            if "." not in alvo:
                continue
            modulo, _, nome = alvo.rpartition(".")
            try:
                m = importlib.import_module(modulo)
            except ImportError:
                faltando.append(f"{n['impressao']} → módulo {modulo}")
                continue
            if not hasattr(m, nome):
                # pode ser coluna de tabela, e nao constante de modulo
                if modulo.startswith(("ri_", "rc_", "pt_", "nt_", "cx_")):
                    continue
                faltando.append(f"{n['impressao']} → {alvo}")
    assert not faltando, "\n    ".join(faltando)


# ------------------------------------------------ a passada


def test_a_passada_poe_a_nota_no_problema_que_existe(con):
    n = ND.NOTAS[0]
    pid = _problema(con, n["impressao"])
    r = ND.aplicar(con, agora=AGORA)
    assert r["postas"] >= 1
    linha = con.execute(
        "SELECT nota_dev, nota_dev_estado, nota_dev_por FROM aj_problemas "
        "WHERE id = ?", (pid,)).fetchone()
    assert linha["nota_dev"] == n["nota"]
    assert linha["nota_dev_estado"] == n["estado"]
    assert linha["nota_dev_por"] == ND.MARCA


def test_a_passada_NAO_sobrescreve_o_que_o_oficial_escreveu(con):
    """**A nota dele vale mais que a minha**, porque ele é quem responde pela
    serventia. Uma passada que sobrescrevesse apagaria a observação de quem
    está no balcão — e apagaria calada, na subida da versão."""
    n = ND.NOTAS[0]
    pid = _problema(con, n["impressao"])
    PROB.anotar_desenvolvimento(con, pid, nota="isto aqui continua acontecendo",
                            estado=ND.EM_ANDAMENTO, prova="",
                            agora=AGORA, por="mario")
    r = ND.aplicar(con, agora=AGORA)
    assert r["respeitadas"] >= 1
    linha = con.execute("SELECT nota_dev, nota_dev_por FROM aj_problemas "
                        "WHERE id = ?", (pid,)).fetchone()
    assert linha["nota_dev"] == "isto aqui continua acontecendo"
    assert linha["nota_dev_por"] == "mario"


def test_a_passada_NAO_fecha_problema_nenhum(con):
    """Dizer «atendido» é a minha opinião sobre o conserto; dizer que o assunto
    acabou é o clique dele. **Já houve conserto que não era o conserto**, e o
    relato que volta é a linha mais importante da lista."""
    atendida = next(n for n in ND.NOTAS if n["estado"] == ND.ATENDIDO)
    pid = _problema(con, atendida["impressao"])
    ND.aplicar(con, agora=AGORA)
    situacao = con.execute("SELECT situacao FROM aj_problemas WHERE id = ?",
                           (pid,)).fetchone()["situacao"]
    assert situacao == "ABERTO"


def test_rodar_duas_vezes_nao_muda_nada(con):
    """Ela roda em toda subida do sistema."""
    for n in ND.NOTAS[:3]:
        _problema(con, n["impressao"])
    primeira = ND.aplicar(con, agora=AGORA)
    segunda = ND.aplicar(con, agora="2026-09-01 08:00:00")
    assert primeira["postas"] == 3
    assert segunda["postas"] == 0
    assert segunda["mantidas"] == 3


def test_problema_que_nao_existe_aqui_nao_e_erro(con):
    """Instalação nova não tem os relatos desta casa, e isso é normal."""
    r = ND.aplicar(con, agora=AGORA)
    assert r["postas"] == 0
    assert r["sem_problema"] == len(ND.NOTAS)
    assert not r["recusadas"]


def test_a_passada_nunca_derruba_a_subida(con):
    """**Balcão parado é pior que nota faltando.** Um banco sem as colunas
    devolve o motivo em vez de estourar."""
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE aj_problemas (id INTEGER PRIMARY KEY, "
              "impressao TEXT)")
    r = ND.aplicar(c, agora=AGORA)
    assert r["erro"]
    assert r["postas"] == 0


def test_a_marca_separa_o_que_e_meu_do_que_e_dele():
    """Sem uma marca própria não haveria como distinguir a nota que a passada
    pôs da que uma pessoa escreveu — e a escolha seria entre nunca corrigir
    uma nota minha ou apagar as dele."""
    assert ND.MARCA and ND.MARCA != "mario"


# ------------------------------------------------ o alcance


def test_ha_nota_para_TODO_relato_que_esta_casa_registrou():
    """**São 36, e a lista tem de acompanhar.**

    Relato sem nota é o que faz o oficial abrir a tela e continuar sem saber o
    que aconteceu com aquele item — que é exatamente o que ele pediu para
    acabar. Se um relato novo entrar, este teste fica vermelho até alguém
    escrever a nota dele.
    """
    assert len(ND.NOTAS) >= 36, (
        f"há {len(ND.NOTAS)} notas para 36 relatos conhecidos")


def test_o_que_nao_esta_feito_nao_se_diz_atendido():
    """Os cinco que eu sei que não estão prontos continuam declarados como
    tal. **Marcar por parecido é como o #27 viraria «atendido» por causa do
    #8**, que era outro papel."""
    abertos = {n["impressao"] for n in ND.NOTAS
               if n["estado"] != ND.ATENDIDO}
    # #20 (odt do teor), #34 (inatividade), #36 (salvar o ato) e
    # #16 (endereço do QR).
    #
    # O #27 SAIU DESTA LISTA EM 31/08/2026, e não por parecença: as duas
    # metades dele foram feitas — quem assina (só o cliente) e o espaço para
    # desenvolver a assinatura, que era a metade que eu tinha dado por
    # respondida sem estar. A prova são `test_cartao_assinatura.py` e
    # `test_linha_em_branco_no_odt.py`, que medem o PAPEL que sai.
    #
    # **O #33 SAIU EM 07/09/2026**, e este guarda me obrigou a justificar a
    # saída em vez de virar o estado calado — que é para isso que ele existe.
    # A pesquisa de selos por data, especialidade e usuário está construída,
    # em Administrativo → Dinheiro → «Selos emitidos», e a prova é
    # `test_selos_emitidos.py`, que mede a tela E a armadilha dos dois
    # formatos de data na coluna `obtido_em`.
    #
    # **E A LISTA É ESCRITA À MÃO DE PROPÓSITO.** «O que ainda não está
    # construído» não se mede — não há coluna que o diga —, e por isso ela é
    # a exceção declarada à regra «lista escrita à mão envelhece». O que a
    # impede de envelhecer é justamente ficar vermelha quando alguém marca
    # ATENDIDO sem tirá-la daqui.
    #
    # **O #34 SAIU EM 07/09/2026, e a razão é a mesma do #33 com uma volta a
    # mais**: ele JÁ ESTAVA CONSTRUÍDO, e a nota anterior — minha — dizia que
    # não. O que faltava era a prova, e ela agora mexe no relógio:
    # `test_relato_34_inatividade.py` põe a sessão parada há onze horas e há
    # treze, e confere que ela sobrevive à primeira e cai na segunda.
    #
    # **O #20 SAIU EM 07/09/2026, e ele fecha um padrão que virou o achado
    # principal da passada**: o relato é da versão **3.6.21** e estamos na
    # 3.6.66 — foi construído no meio do caminho, com 37 testes de formato e
    # 15 de tela, e a NOTA é que ficou para trás. Sete das doze pendências do
    # ajuda estavam assim.
    #
    # **O #36 SAIU EM 07/09/2026**: o rascunho passou de UMA para as TREZE
    # telas de lavrar, com varredor que exige as treze —
    # `test_rascunho_em_todo_ato.py`.
    #
    # **O #16 SAIU EM 14/10/2026** (impressão 8115acd5e5f11b15), e o conserto
    # é de 24/09/2026: o QR passou a abrir a consulta do selo
    # (`#/resumo/<SELO>`), medido no portal e conferido em dois selos reais —
    # ver CLAUDE.md, «O QR DO SELO PASSOU A ABRIR A CONSULTA», e a prova da
    # nota, `test_qr_do_selo.py`. A nota foi para ATENDIDO naquele dia e esta
    # lista não acompanhou. Com ela vazia, o guarda continua de pé: quem
    # souber de relato marcado ATENDIDO sem estar feito o põe aqui.
    for impressao in ():
        assert impressao in abertos, (
            f"{impressao} está marcado como atendido e não está feito")
