"""O que o Código de Normas do TJMA exige da usucapião — lido, não lembrado.

O RELATO DO OFICIAL, pela janela da ajuda:

    «o cadastramento é muito simples e não parece ser maduro para processar um
     usucapião no RI com confiança… Buscar referências»

E a decisão dele em 28/08/2026: **«eu monto do Código de Normas do TJMA e da
lei, e você confere»**.

O CÓDIGO ESTAVA NA CASA, e eu quase respondi de memória: `Código de normas
TJMA atualizado.pdf`, 249 páginas, na pasta de Downloads. A Seção XIV — «Da
Usucapião Extrajudicial» — são os arts. 747 a 761.

O QUE ESTES TESTES GUARDAM
    Não a redação dos artigos, que não é nossa: o que eles guardam é que as
    regras que o sistema aplica **continuem citando o artigo de onde saíram**,
    e que nenhuma delas some numa refatoração. Foi o oficial quem pediu para
    conferir, e ele só consegue conferir o que tem endereço.
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import us_tjma as TJMA
import usucapiao as US

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    banco = cg_casa["banco"]
    app = cg_casa["app"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "cliente": c, "banco": banco, "db": db}

# ------------------------------------------- a Seção inteira está coberta

def test_a_secao_xiv_inteira_tem_regra_no_sistema():
    """Arts. 747 a 761, mais os 738 e 739 da regularização fundiária rural.

    Este teste fica vermelho se alguém apagar um artigo numa refatoração — e
    artigo que some de um rito de meses só aparece na correição."""
    citados = set(TJMA.artigos_citados())
    for n in list(range(747, 762)) + [738, 739]:
        assert f"art. {n}" in citados, f"o art. {n} sumiu"


def test_a_lista_de_conferencia_nao_manda_ao_pdf_errado():
    """`artigos_citados` promete os artigos DO CÓDIGO DE NORMAS. A busca solta
    por «art. NNN» trazia também o art. 216-A e o 247-A, que são da Lei de
    Registros Públicos — e quem fosse conferir procuraria no PDF dois artigos
    que não estão lá. Lista de conferência que manda ao lugar errado é pior
    que nenhuma."""
    citados = set(TJMA.artigos_citados())
    assert "art. 216" not in citados
    assert "art. 247" not in citados


def test_a_faixa_da_secao_vai_ate_761_e_nao_ate_760():
    """EU QUASE GRAVEI UMA CORREÇÃO ERRADA AQUI. `usucapiao.py` citava «arts.
    747 a 761», e eu escrevi que a faixa terminaria no 760 — porque eu tinha
    lido até ali. A Seção XV («Das Cédulas de Crédito») só começa no 762: o
    761 é de usucapião mesmo, e trata do imóvel edificado.

    A citação que já estava no código estava certa. Faixa de artigos se lê no
    cabeçalho da seção seguinte, e não no fim do trecho em que a gente parou
    de ler."""
    assert "art. 761" in TJMA.artigos_citados()
    assert TJMA.IMOVEL_EDIFICADO[0]["base"] == "Código TJMA, art. 761"


# ------------------------------------------- o que faltava no checklist


def test_a_justificacao_do_obice_entrou_no_checklist():
    """O item que mais faltava, e não é papelada: é a pergunta que separa a
    usucapião de uma compra e venda que ninguém quis registrar para não pagar
    ITBI (art. 748)."""
    itens = {c["item"] for c in US.CHECKLIST}
    assert "JUSTIFICACAO_OBICE" in itens
    assert "JUSTIFICACAO_OBICE" in US.TIPOS_DE_PECA


def test_as_sete_hipoteses_do_obice_estao_todas():
    """São as sete do art. 748, § 1º — e mais `OUTRO`, porque a lista do artigo
    é «entre outras». Fechá-la faria o balcão recusar um caso legítimo."""
    assert len(TJMA.OBICES_DO_ART_748) == 8
    assert "OUTRO" in TJMA.OBICES_DO_ART_748
    for esperado in ("IMOVEL_INVADIDO", "ALIENANTE_NAO_LOCALIZADO",
                     "PJ_EXTINTA_IRREGULARMENTE", "TRANSMITENTE_SEM_CND",
                     "LOTEAMENTO_IRREGULAR", "HERDEIROS_RECUSAM_INVENTARIO",
                     "INVENTARIOS_SUCESSIVOS"):
        assert esperado in TJMA.OBICES_DO_ART_748


def test_todo_item_novo_do_checklist_diz_de_que_artigo_saiu():
    """Exigência sem endereço é exigência que ninguém confere — e foi
    exatamente conferir que o oficial pediu."""
    for c in US.CHECKLIST:
        assert c.get("base"), c["item"]
        # `arts.` no plural também vale: a área-limite cita «CF, arts. 183
        # e 191», que são dois artigos de verdade e não uma citação vaga.
        assert re.search(r"arts?\.\s*\d", c["base"]), c["base"]


def test_a_vedacao_do_sfh_e_a_unica_absoluta():
    """Art. 749. Todas as outras situações que parecem impedir estão em
    `NAO_IMPEDEM`, com artigo — e essa lista é a que impede um balcão inseguro
    de travar um pedido bom."""
    assert TJMA.VEDACAO_SFH["base"] == "Código TJMA, art. 749"
    casos = {x["caso"] for x in TJMA.NAO_IMPEDEM}
    assert casos == {"SEM_REGISTRO", "AREA_MENOR_QUE_A_MINIMA",
                     "ONUS_OU_GRAVAME", "INDISPONIBILIDADE_POSTERIOR"}


# ------------------------------------------- o prazo do edital


def test_o_prazo_do_edital_tem_dois_saltos_e_nao_um():
    """Art. 755, § 1º. A data da publicação é o primeiro dia útil DEPOIS da
    disponibilização; os prazos contam do primeiro dia útil DEPOIS dessa data.

    Quem ler o parágrafo com pressa conta o prazo da disponibilização — e num
    edital, errar por um dia é recomeçar o edital.
    """
    # segunda a sexta são úteis; sábado e domingo não
    from datetime import date
    util = lambda d: date.fromisoformat(d).weekday() < 5   # noqa: E731

    # quarta-feira, 26/08/2026
    assert TJMA.data_da_publicacao("2026-08-26", util) == "2026-08-27"
    assert TJMA.inicio_do_prazo("2026-08-26", util) == "2026-08-28"


def test_o_fim_de_semana_empurra_os_dois_saltos():
    from datetime import date
    util = lambda d: date.fromisoformat(d).weekday() < 5   # noqa: E731
    # sexta-feira 28/08/2026 -> publica na segunda 31, conta da terça 1º/09
    assert TJMA.data_da_publicacao("2026-08-28", util) == "2026-08-31"
    assert TJMA.inicio_do_prazo("2026-08-28", util) == "2026-09-01"


def test_calendario_sem_dia_util_recusa_em_vez_de_inventar_data():
    """Trinta dias sem dia útil não é feriado: é calendário errado. Devolver
    uma data assim mesmo poria um prazo falso num edital."""
    with pytest.raises(ValueError) as e:
        TJMA.inicio_do_prazo("2026-08-26", lambda d: False)
    assert "feriados" in str(e.value)


# ------------------------------------------- o módulo não julga


def test_o_modulo_do_codigo_de_normas_nao_decide_nada():
    """Ele diz o que o Código manda perguntar; quem responde é o delegatário.
    Quinta vez que esta regra aparece no projeto — usucapião, fraudes,
    impedimento de casamento, CNIB, e agora."""
    publicos = [n for n in dir(TJMA) if not n.startswith("_")]
    for proibido in ("julgar", "decidir", "deferir", "indeferir", "recusar",
                     "registrar", "averbar"):
        assert not [n for n in publicos if proibido in n.lower()], proibido


# ------------------------------------------- a tela de conferência


def test_a_tela_mostra_cada_regra_com_o_artigo_do_lado(casa):
    html = casa["cliente"].get(
        "/usucapiao/codigo-de-normas").get_data(as_text=True)
    assert "art. 748" in html          # a justificação do óbice
    assert "art. 749" in html          # a vedação do SFH
    assert "art. 753" in html          # a planta
    assert "art. 760" in html          # a indisponibilidade
    assert "art. 761" in html          # o imóvel edificado
    assert "SIRGAS 2000" in html       # o conteúdo concreto da planta


def test_a_tela_traz_os_tres_deveres_da_indisponibilidade(casa):
    """Num parágrafo corrido o do meio se perde — e é o único que pode
    indeferir o pedido."""
    html = " ".join(casa["cliente"].get(
        "/usucapiao/codigo-de-normas").get_data(as_text=True).split())
    assert "malote digital" in html
    assert "má-fé" in html
    assert "matrícula atualizada" in html


def test_a_tela_nao_grava_nada(casa):
    """Ela é de leitura. Rota de consulta que grava é o defeito que faz uma
    tela de leitura ficar dez segundos presa no busy_timeout."""
    import sqlite3
    con = sqlite3.connect(casa["banco"])
    antes = con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    casa["cliente"].get("/usucapiao/codigo-de-normas")
    depois = con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    assert antes == depois
