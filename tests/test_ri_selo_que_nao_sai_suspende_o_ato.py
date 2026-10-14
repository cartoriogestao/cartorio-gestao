"""O SELO QUE NÃO SAI SUSPENDE O ATO — e uma exceção, medida.

    «se falhar o selo, SEMPRE suspender o ato para corrigir o problema»
      — o oficial, relato #77, 16/09/2026

**ESTE ARQUIVO SE CHAMAVA `test_ri_suspende_so_quando_ha_recusa.py`**, e a
primeira frase dele era «só a recusa do aparelho suspende o ato». Era a regra
da manhã daquele dia, e ela durou até a noite: quando o oficial decidiu o item
1, a casa que **não apontou o aparelho** passou a suspender também. Arquivo
cujo nome afirma uma regra é carimbo — e carimbo que mente é pior que carimbo
nenhum —, e por isso o nome mudou junto.

SÃO DUAS ESPÉCIES DE FALHA, E A FRONTEIRA É «QUEM ATENDE TEM COMO CORRIGIR?»:

  1. **SUSPENDE** — o aparelho recusou, a credencial venceu, o TJMA disse não,
     **ou ninguém apontou o aparelho**. Nos quatro, corrigir e lavrar de novo
     resolve, e o trabalho fica guardado na minuta, com o teor e as partes.
  2. **NÃO SUSPENDE** — o **ato de ACERVO sem item de custa**, que ele
     dispensou no mesmo dia («ato de acerto fica sem item de custa»). Ali não
     há o que corrigir: o ato já foi praticado, cobrado e selado no papel anos
     atrás. Suspendê-lo o poria a ser lavrado e suspenso **para sempre**, e a
     ficha nunca receberia o próprio livro.

**E A DECISÃO NÃO SE LÊ NA PROSA DO RECADO.** `_selar_o_ato_do_ri` devolve um
`bool` — `suspende` — ao lado da frase; adivinhar a espécie procurando
palavras no texto seria o varredor batendo na própria prosa outra vez, e aqui
o preço é um ato que não se lavra.
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

import selador_config as SELCFG

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(tmp_path):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA,
                               "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    # A FICHA ABRE NO INTERVALO QUE ESTA CASA PRODUZ — 4019 é a próxima, e a
    # própria rota o diz (`ri_nova_matricula`). **Ela era a 4014, e isso não é
    # detalhe: número menor que 4.015 é ACERVO** (regra informada pela serventia
    # em 17/09/2026, ordem do oficial, e não guarda de programador). Nessas
    # fichas o número do ato vem do livro físico e a rota recusa sem ele —
    # **antes de chegar ao selo**, que é o que estes três testes medem. Os três
    # ficavam vermelhos medindo a coisa errada: o recado na tela era «Nesta
    # ficha de acervo o número do ato precisa ser informado, conforme o livro
    # físico», e não a suspensão que eles cobram.
    #
    #   O `tipo_ficha` desta bancada continua `ESTRUTURADA`, e continua bem: a
    #   régua do número é `matricula_de_acervo(numero)`, e o que este arquivo
    #   prova é a suspensão. O ato de acervo tem teste próprio — o de baixo, que
    #   declara `ACERVO` na mão e informa o número.
    con.execute(
        """INSERT INTO ri_matriculas(numero, livro, folha, tipo_ficha,
                                     situacao, criado_em)
           VALUES ('4019','2-S','1','ESTRUTURADA','ATIVA',
                   '2026-09-14T10:00')""")
    con.commit()
    mid = con.execute(
        "SELECT id FROM ri_matriculas WHERE numero='4019'").fetchone()[0]
    return {"c": c, "con": con, "mid": mid, "dados": dados}


def _configurar_o_selador(casa):
    """Deixa o aparelho «pronto» — endereço e credencial —, e ele não existe.

    O endereço aponta para uma porta em que nada escuta: a tentativa falha na
    conexão, sem espera, e é exatamente a forma de «o selador não respondeu»
    que o balcão vive quando a máquina da rede local cai.
    """
    with casa["con"] as con:
        SELCFG.gravar(con, base_url="https://127.0.0.1:9", origem="MANUAL",
                      agora="2026-09-16T09:00", usuario_do_sistema="jean")
    SELCFG.gravar_credencial(casa["dados"], "selador", "senha-de-mentira",
                             agora="2026-09-16T09:00",
                             usuario_do_sistema="jean")
    assert SELCFG.situacao(casa["con"], casa["dados"])["pronto"], (
        "o ensaio nao conseguiu deixar o selador pronto")


def _lavrar(casa, **campos):
    ficha = casa["c"].get(
        f"/registro-imoveis/{casa['mid']}?lavrar=1").get_data(as_text=True)
    dados = {"csrf_token": _token(ficha), "tipo": "R",
             "teor": "Registro de compra e venda.",
             "natureza_titulo": "Compra e venda", "codigo_tj": "16.22.2"}
    dados.update(campos)
    return casa["c"].post(f"/registro-imoveis/{casa['mid']}/atos", data=dados,
                          follow_redirects=True)


def _contar(casa, tabela):
    return casa["con"].execute(
        f"SELECT COUNT(*) FROM {tabela} WHERE matricula_id=?",
        (casa["mid"],)).fetchone()[0]


# --------------------------- 1. sem selador apontado, o ato TAMBÉM se suspende


def test_sem_selador_apontado_o_ato_tambem_se_suspende(casa):
    """Item 1 de 16/09/2026, decidido por ele — e isto era o contrário.

    Este teste dizia «não houve recusa: houve ausência; suspender aqui seria
    um laço», e o ato ficava lavrado sem selo. **Laço é o do ato de acervo**,
    onde quem atende não tem como corrigir; aqui há correção e há quem a faça:
    apontar o aparelho em Administrativo → Selador. Para quem lê o livro, o
    ato sem selo é o mesmo nos dois casos.

    **E A TELA DIZ QUAL DAS DUAS COISAS CORRIGIR**: as duas pedem providências
    diferentes de quem está no balcão, e quem aponta o selador não é quem
    atende.
    """
    assert not SELCFG.situacao(casa["con"], casa["dados"])["pronto"]

    html = _lavrar(casa).get_data(as_text=True)

    assert _contar(casa, "ri_atos") == 0, (
        "o ato ficou no livro sem selo — o item 1 mandou suspender tambem "
        "quando o aparelho nao foi apontado")
    assert _contar(casa, "ri_minutas") == 1, "o trabalho tinha de ficar salvo"
    assert "NÃO foi lavrado" in html
    assert "selador ainda não foi apontado" in html, (
        "a recusa nao disse ao balcao qual das duas coisas corrigir")


# --------------------------- 2. com o aparelho apontado, a recusa SUSPENDE


def test_com_o_selador_apontado_a_recusa_suspende_o_ato(casa):
    """Aqui relavrar resolve — é o caso que o oficial descreveu."""
    _configurar_o_selador(casa)

    html = _lavrar(casa).get_data(as_text=True)

    assert _contar(casa, "ri_atos") == 0, "o ato nao podia ficar no livro"
    assert _contar(casa, "ri_minutas") == 1, "o trabalho tinha de ficar salvo"
    mi = casa["con"].execute(
        "SELECT * FROM ri_minutas WHERE matricula_id=?",
        (casa["mid"],)).fetchone()
    assert mi["situacao"] == "A_REVISAR"
    assert "compra e venda" in (mi["teor"] or "").lower()
    assert "NÃO foi lavrado" in html
    assert "Minutas a revisar e lavrar" in html


# ------------------------------------------ 3. a decisão expressa ACABOU


def test_nem_com_o_campo_do_desvio_o_ato_do_RI_fica_sem_selo(casa):
    """A exceção acabou — relato #77, 16/09/2026, ordem do oficial.

        «se falhar o selo, sempre suspender o ato para corrigir o problema»

    Este teste chamava-se «a decisão expressa de lavrar sem selo continua
    valendo», e ela não continua. **Ele foi virado, e não apagado**: o campo
    `lavrar_sem_selo` ainda pode chegar pela mão — de um favorito antigo, de
    uma tela que não foi atualizada, de quem conhece o nome dele — e porta dos
    fundos por campo de formulário é a que se abre sem ninguém ver.

    O caso do aparelho recusando continua provado pelo teste vizinho, com a
    minuta guardada; o que se prova aqui é que não há desvio.
    """
    _configurar_o_selador(casa)

    _lavrar(casa, lavrar_sem_selo="1")

    assert _contar(casa, "ri_atos") == 0, (
        "o campo `lavrar_sem_selo` mandado na mão ainda lavra sem selo — o "
        "desvio que o relato #77 mandou tirar de todo módulo")
    assert _contar(casa, "ri_minutas") == 1, "o trabalho tinha de ficar salvo"
    marcas = [r[0] for r in casa["con"].execute(
        "SELECT action FROM audit_logs WHERE entity_type='RI_ATO'")]
    assert "RI_ATO_LAVRADO_SEM_SELO_FALTA_NO_CADASTRO" not in marcas
    assert "RI_ATO_LAVRADO_SEM_SELO_POR_DECISAO" not in marcas, (
        "a marca «por decisao» saiu em 16/09: ninguem decide mais nada")
    assert "RI_ATO_SUSPENSO_SEM_SELO" in marcas


# ---------------------------------- 4. o ato de acervo sem item não suspende


def test_ficha_de_acervo_sem_item_de_custa_lavra_e_nao_suspende(casa):
    """«Ato de acerto fica sem item de custa» — ordem dele, no mesmo dia.

    Com o selador apontado e o item em branco, o envelope nem chega a ser
    montado: falta o item. Isso não é recusa do aparelho, e suspender poria a
    digitação do acervo num laço — o ato voltaria para a minuta toda vez.
    """
    _configurar_o_selador(casa)
    with casa["con"] as con:
        con.execute("UPDATE ri_matriculas SET tipo_ficha='ACERVO' WHERE id=?",
                    (casa["mid"],))

    html = _lavrar(casa, codigo_tj="", numero="7").get_data(as_text=True)

    assert _contar(casa, "ri_atos") == 1, (
        "o ato de acervo nao pode ser suspenso por falta de item")
    assert _contar(casa, "ri_minutas") == 0
    assert "SEM SELO" in html


# ------------------------------------- 5. a régua é um campo, e não a prosa


def test_a_especie_da_falha_nao_se_le_no_texto_do_recado():
    """Adivinhar a espécie lendo a frase é o varredor batendo na própria prosa.

    `_selar_o_ato_do_ri` devolve `suspende` ao lado do recado, e é esse campo
    que a rota consulta. Se alguém voltar a decidir pelo texto, este teste
    fica vermelho antes de o balcão descobrir.

    **O CAMPO SE CHAMAVA `da_rede` ATÉ 16/09/2026**, e o nome mudou com a
    pergunta: não é mais «a falha veio da rede?», e sim «este ato se
    suspende?» — o aparelho que ninguém apontou também suspende agora.
    """
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert '"suspende"' in codigo, "o campo que decide a suspensao sumiu"
    assert 'saiu_do_selo["suspende"]' in codigo, (
        "a rota voltou a decidir a suspensao sem olhar a especie da falha")
