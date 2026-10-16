"""A retificação de área como processo — o pedido do oficial de 29/08/2026.

O QUE ESTES TESTES GUARDAM
    As recusas, e **cada uma protege alguém**:

    - averbar sem decisão procedente é registro sem fundamento;
    - decidir procedente com confrontante ainda no prazo tira dele o direito de
      opor a divisa — e é a notificação malfeita que anula a averbação depois;
    - impugnação sem fundamento não é impugnação (art. 593);
    - decisão sem fundamento é a que desfaz o registro depois (art. 604).

    E as duas regras que parecem contradição e não são (art. 599, §§ 1º e 3º):
    o silêncio vale anuência, **mas a porta só fecha quando a averbação sai**.
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

import retificacao as RT                                         # noqa: E402
import rt_tjma as NORMA                                          # noqa: E402

SENHA = "Senha#12345"
HOJE = "2026-08-29"
AGORA = "2026-08-29T09:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _matricula(con, numero="1083"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, situacao, criado_em)
           VALUES (?, '2', 'ATIVA', ?)""", (numero, AGORA))
    return int(cur.lastrowid)


def _processo(con, *, especie=NORMA.GEORREFERENCIADA,
              fundamento=NORMA.A_REQUERIMENTO, rural=True, numero="1/2026"):
    m = _matricula(con)
    pid = RT.autuar(con, numero=numero, especie=especie, fundamento=fundamento,
                    matricula_id=m, rural=rural, agora=AGORA,
                    requerente_nome="ANTONIO JARDINEIRO PEREIRA",
                    usuario="mario")
    return pid, m


# ------------------------------------------------ autuar


def test_o_processo_nasce_com_o_checklist_do_art_592(casa):
    """O checklist sai da NORMA, e não de uma lista aqui — uma segunda lista
    envelheceria na tarde em que fosse escrita."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
    itens = RT.conferencia(con, pid)
    esperados = NORMA.checklist(georreferenciada=True, rural=True)
    assert len(itens) == len(esperados)
    assert all(x["situacao"] == "PENDENTE" for x in itens)


def test_o_checklist_do_urbano_nao_pede_ccir(casa):
    con = _con(casa)
    with con:
        pid, _ = _processo(con, especie=NORMA.NAO_GEORREFERENCIADA,
                           rural=False)
    texto = " ".join(x["item"] for x in RT.conferencia(con, pid))
    assert "CCIR" not in texto


def test_sem_matricula_nao_ha_o_que_retificar(casa):
    """A diferença em relação ao usucapião: lá o imóvel pode não ter matrícula;
    aqui o que se retifica É o registro."""
    con = _con(casa)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.autuar(con, numero="9/2026", especie=NORMA.GEORREFERENCIADA,
                  fundamento=NORMA.A_REQUERIMENTO, matricula_id=99999,
                  rural=True, agora=AGORA)
    assert "sem matrícula não há o que retificar" in str(erro.value)


def test_especie_e_fundamento_saem_do_catalogo(casa):
    con = _con(casa)
    with con:
        m = _matricula(con)
    with con, pytest.raises(RT.RetificacaoError):
        RT.autuar(con, numero="8/2026", especie="INVENTADA",
                  fundamento=NORMA.A_REQUERIMENTO, matricula_id=m, rural=True,
                  agora=AGORA)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.autuar(con, numero="8/2026", especie=NORMA.GEORREFERENCIADA,
                  fundamento="213_III", matricula_id=m, rural=True,
                  agora=AGORA)
    assert "art. 213" in str(erro.value)


def test_o_numero_nao_se_repete(casa):
    con = _con(casa)
    with con:
        pid, _ = _processo(con, numero="7/2026")
    with con, pytest.raises(RT.RetificacaoError) as erro:
        _processo(con, numero="7/2026")
    assert "Já existe" in str(erro.value)


# ------------------------------------------------ quem se notifica


def test_quem_assinou_a_planta_nao_se_notifica(casa):
    """Art. 592, II — a planta vai assinada pelos confrontantes; quem assinou já
    anuiu. Notificar de novo é trabalho e espera à toa."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        RT.anotar_confrontante(con, pid, nome="MARIA DAS DORES", agora=AGORA,
                               assinou_planta=True)
        RT.anotar_confrontante(con, pid, nome="PEDRO FRANCISCO", agora=AGORA)
    faltam = RT.quem_precisa_ser_notificado(con, pid)
    assert [c["nome"] for c in faltam] == ["PEDRO FRANCISCO"]


def test_quem_nao_tem_divisa_afetada_nem_se_intima(casa):
    """Art. 596, parágrafo único — dispensada a anuência OU INTIMAÇÃO de quem
    não tem medida alterada."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        RT.anotar_confrontante(con, pid, nome="JOAO DA MATA", agora=AGORA,
                               divisa_afetada=False)
    assert RT.quem_precisa_ser_notificado(con, pid) == []
    fora = RT.dispensados_de_notificacao(con, pid)
    assert fora[0]["artigo"] == "art. 596, parágrafo único"


def test_a_carta_de_anuencia_apartada_dispensa(casa):
    """Art. 598: só se notifica «se a planta não contiver a assinatura de algum
    confrontante, E NÃO FOR APRESENTADA carta de anuência apartada»."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        RT.anotar_confrontante(con, pid, nome="ANA LIMA", agora=AGORA,
                               carta_anuencia=True)
    assert RT.quem_precisa_ser_notificado(con, pid) == []
    assert RT.dispensados_de_notificacao(con, pid)[0]["artigo"] == "art. 598"


def test_a_dispensa_aparece_com_o_artigo(casa):
    """Dispensa que não se vê vira dúvida no balcão, e a dúvida vira notificação
    a mais — que é o que a lista existe para evitar."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        RT.anotar_confrontante(con, pid, nome="A", agora=AGORA,
                               assinou_planta=True)
        RT.anotar_confrontante(con, pid, nome="B", agora=AGORA,
                               divisa_afetada=False)
    artigos = {x["artigo"] for x in RT.dispensados_de_notificacao(con, pid)}
    assert artigos == {"art. 592, II", "art. 596, parágrafo único"}


def test_o_credor_real_e_papel_proprio(casa):
    """Art. 593 e 617 — ele não precisa ANUIR, basta a notificação."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        RT.anotar_confrontante(con, pid, nome="BANCO DO NORDESTE",
                               papel=RT.CREDOR_REAL, agora=AGORA)
    c = RT.confrontantes(con, pid)[0]
    assert c["papel"] == RT.CREDOR_REAL


# ------------------------------------------------ a notificação


def test_a_forma_sai_do_art_598(casa):
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        cid = RT.anotar_confrontante(con, pid, nome="X", agora=AGORA)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.notificar(con, cid, forma="WHATSAPP", quando=HOJE, agora=AGORA,
                     prazo_ate="2026-09-19")
    assert "art. 598" in str(erro.value)


def test_nao_se_notifica_duas_vezes(casa):
    """Uma segunda notificação recomeçaria o prazo dele — e num rito de meses
    isso é meio mês perdido, ou um prazo contado errado."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        cid = RT.anotar_confrontante(con, pid, nome="X", agora=AGORA)
        RT.notificar(con, cid, forma="CORREIO", quando=HOJE, agora=AGORA,
                     prazo_ate="2026-09-19")
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.notificar(con, cid, forma="PESSOAL", quando=HOJE, agora=AGORA,
                     prazo_ate="2026-09-30")
    assert "recomeçaria o prazo" in str(erro.value)


def test_o_prazo_mora_na_linha_de_cada_um(casa):
    """Art. 599: «conta-se individualmente para cada notificado». Um prazo só
    para todos faria a averbação sair antes de o último ter tido os seus
    quinze dias."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        a = RT.anotar_confrontante(con, pid, nome="A", agora=AGORA)
        b = RT.anotar_confrontante(con, pid, nome="B", agora=AGORA)
        RT.notificar(con, a, forma="PESSOAL", quando="2026-08-01", agora=AGORA,
                     prazo_ate="2026-08-22")
        RT.notificar(con, b, forma="CORREIO", quando="2026-08-20", agora=AGORA,
                     prazo_ate="2026-09-12")
    prazos = RT.situacao_dos_prazos(con, pid, hoje=HOJE)
    assert [c["nome"] for c in prazos["venceu"]] == ["A"]
    assert [c["nome"] for c in prazos["no_prazo"]] == ["B"]


# ------------------------------------------------ silêncio e atraso


def test_o_silencio_e_uma_resposta_com_nome(casa):
    """Chamá-lo de «sem resposta» faria a tela mostrar como pendência o que a
    norma já resolveu — art. 599, § 1º."""
    assert RT.SILENCIO in RT.RESPOSTAS
    assert "anuência presumida" in RT.NOME_DA_RESPOSTA[RT.SILENCIO]


def test_a_porta_so_fecha_quando_a_averbacao_sai(casa):
    """Art. 599, § 3º. Um sistema que trate «prazo vencido» como «acabou»
    erraria — e erraria contra quem não foi ouvido."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
    assert RT.situacao_dos_prazos(con, pid, hoje=HOJE)["porta_aberta"] is True


def test_impugnacao_sem_fundamento_nao_e_impugnacao(casa):
    """Art. 593: «não bastando mera alegação de prejuízo»."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        cid = RT.anotar_confrontante(con, pid, nome="X", agora=AGORA)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.responder(con, cid, resposta=RT.IMPUGNOU, agora=AGORA,
                     impugnacao="não")
    assert "mera alegação de prejuízo" in str(erro.value)


# ------------------------------------------------ decidir


def test_nao_se_decide_procedente_com_confrontante_no_prazo(casa):
    """Decidir com alguém ainda no prazo tira dele o direito de opor a divisa —
    e é a notificação malfeita que anula a averbação depois."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        cid = RT.anotar_confrontante(con, pid, nome="X", agora=AGORA)
        RT.notificar(con, cid, forma="PESSOAL", quando=HOJE, agora=AGORA,
                     prazo_ate="2026-09-19")
        for item in RT.conferencia(con, pid):
            RT.marcar_item(con, pid, item["item"], situacao="ATENDIDO",
                           agora=AGORA)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.decidir(con, pid, sentido=RT.PROCEDENTE, fundamento="tudo em ordem",
                   agora=AGORA, hoje=HOJE)
    assert "dentro do prazo" in str(erro.value)


def test_nao_se_decide_procedente_com_item_pendente(casa):
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.decidir(con, pid, sentido=RT.PROCEDENTE, fundamento="tudo em ordem",
                   agora=AGORA, hoje=HOJE)
    assert "conferência do art. 592" in str(erro.value)


def test_decisao_sem_fundamento_e_recusada(casa):
    """Art. 604 pede decisão FUNDAMENTADA — decisão sem fundamento é a que
    desfaz o registro depois."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.decidir(con, pid, sentido=RT.IMPROCEDENTE, fundamento="não",
                   agora=AGORA, hoje=HOJE)
    assert "FUNDAMENTADA" in str(erro.value)


def test_improcedente_avisa_do_prazo_de_suscitar_duvida(casa):
    """Art. 604, § 2º — 15 dias úteis, e o interessado precisa saber disso."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        RT.decidir(con, pid, sentido=RT.IMPROCEDENTE,
                   fundamento="a planta não fecha com as divisas do vizinho",
                   agora=AGORA, hoje=HOJE)
    texto = " ".join(x["o_que"] for x in RT.andamento(con, pid))
    assert "suscite dúvida" in texto


def test_nao_se_decide_duas_vezes(casa):
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        RT.decidir(con, pid, sentido=RT.IMPROCEDENTE,
                   fundamento="a planta não fecha com as divisas",
                   agora=AGORA, hoje=HOJE)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.decidir(con, pid, sentido=RT.PROCEDENTE, fundamento="mudei de ideia",
                   agora=AGORA, hoje=HOJE)
    assert "já foi decidido" in str(erro.value)


# ------------------------------------------------ averbar e o SIGEF


def _ate_a_averbacao(con, pid):
    for item in RT.conferencia(con, pid):
        RT.marcar_item(con, pid, item["item"], situacao="ATENDIDO", agora=AGORA)
    RT.decidir(con, pid, sentido=RT.PROCEDENTE,
               fundamento="planta e memorial conferem com as divisas",
               agora=AGORA, hoje=HOJE)


def test_nao_se_averba_sem_decisao_procedente(casa):
    """Averbação sem decisão é registro sem fundamento."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.registrar_averbacao(con, pid, ato_id=1, agora=AGORA)
    assert "julgar procedente" in str(erro.value)


def test_o_ato_tem_de_existir(casa):
    """Sem conferir, batia na chave estrangeira e virava HTTP 500 no fim de um
    processo de meses — foi o defeito que o usucapião teve."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        _ate_a_averbacao(con, pid)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.registrar_averbacao(con, pid, ato_id=99999, agora=AGORA)
    assert "Não achei o ato" in str(erro.value)


def test_o_sigef_so_conta_depois_da_averbacao(casa):
    """Art. 620, § 2º: o prazo conta da averbação da poligonal certificada."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.registrar_sigef(con, pid, protocolo="123", quando=HOJE, agora=AGORA)
    assert "ainda não foi averbado" in str(erro.value)


def test_o_prazo_do_sigef_aparece_na_lista(casa):
    """É O ACHADO QUE SOZINHO JUSTIFICA O MÓDULO: obrigação da serventia que
    nasce DEPOIS do ato, quando o cliente já foi embora."""
    con = _con(casa)
    with con:
        pid, m = _processo(con)
        _ate_a_averbacao(con, pid)
        cur = con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, teor,
                   teor_formato, origem, hash_ato, lavrado_em)
               VALUES (?, 'AVERBACAO', 16, 'teor', 'texto', 'SISTEMA',
                       'hash-de-ensaio', ?)""",
            (m, AGORA))
        RT.registrar_averbacao(con, pid, ato_id=int(cur.lastrowid),
                               agora=AGORA)
    faltando = RT.sigef_a_vencer(con)
    assert len(faltando) == 1
    assert faltando[0]["id"] == pid
    passos = RT.proximos_passos(con, pid, hoje=HOJE)
    assert passos[0]["artigo"] == "art. 620, § 2º"
    assert passos[0].get("urgente")


def test_feito_o_sigef_o_processo_sai_da_lista(casa):
    con = _con(casa)
    with con:
        pid, m = _processo(con)
        _ate_a_averbacao(con, pid)
        cur = con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, teor,
                   teor_formato, origem, hash_ato, lavrado_em)
               VALUES (?, 'AVERBACAO', 16, 'teor', 'texto', 'SISTEMA',
                       'hash-de-ensaio', ?)""",
            (m, AGORA))
        RT.registrar_averbacao(con, pid, ato_id=int(cur.lastrowid), agora=AGORA)
        RT.registrar_sigef(con, pid, protocolo="SIGEF-2026-0001",
                           quando="2026-09-10", agora=AGORA)
    assert RT.sigef_a_vencer(con) == []
    assert RT.processo(con, pid)["situacao"] == RT.ENCERRADO


def test_o_sigef_exige_o_protocolo_que_voltou(casa):
    """É a prova de que a serventia cumpriu o prazo."""
    con = _con(casa)
    with con:
        pid, m = _processo(con)
        _ate_a_averbacao(con, pid)
        cur = con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, teor,
                   teor_formato, origem, hash_ato, lavrado_em)
               VALUES (?, 'AVERBACAO', 16, 'teor', 'texto', 'SISTEMA',
                       'hash-de-ensaio', ?)""",
            (m, AGORA))
        RT.registrar_averbacao(con, pid, ato_id=int(cur.lastrowid), agora=AGORA)
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.registrar_sigef(con, pid, protocolo="", quando=HOJE, agora=AGORA)
    assert "protocolo" in str(erro.value)


# ------------------------------------------------ dispensar exige motivo


def test_dispensar_item_exige_motivo_escrito(casa):
    """Dispensar é decisão do oficial; ignorar não é."""
    con = _con(casa)
    with con:
        pid, _ = _processo(con)
        item = RT.conferencia(con, pid)[0]["item"]
    with con, pytest.raises(RT.RetificacaoError) as erro:
        RT.marcar_item(con, pid, item, situacao="DISPENSADO", agora=AGORA,
                       nota="ok")
    assert "motivo" in str(erro.value)


# ------------------------------------------------ o módulo não decide nem lavra


def test_o_modulo_nao_averba_nem_julga_a_impugnacao():
    """Quem lavra é a tela do RI, que tem a corrente de hash, o selo, os
    emolumentos e o nome de quem assina. E se a impugnação procede é matéria de
    direito — sexta vez que esta regra aparece neste projeto."""
    # SO O QUE E CHAMAVEL, e a primeira versao deste teste errou nisso: ele
    # varria TODO nome publico e batia em `IMPROCEDENTE`, que e o nome de uma
    # DECISAO e nao de uma funcao. Varredor que acusa constante gasta a
    # confianca de quem o le — e varredor em que ninguem confia e varredor que
    # alguem desliga.
    publicos = [n for n in dir(RT)
                if not n.startswith("_") and callable(getattr(RT, n))]
    for nome in publicos:
        for proibido in ("averbar", "lavrar", "julgar", "procede",
                         "decidir_impugnacao"):
            assert proibido not in nome.lower(), f"`{nome}` faz o que não deve"
    # `registrar_averbacao` GUARDA o que a tela lavrou; não lavra.
    assert "registrar_averbacao" in publicos
    codigo = (RAIZ / "retificacao.py").read_text(encoding="utf-8")
    assert "INSERT INTO ri_atos" not in codigo
    assert "INSERT INTO ri_matriculas" not in codigo


def test_o_modulo_nao_calcula_data():
    """Contar dia útil é do núcleo, que conhece os feriados desta comarca."""
    codigo = (RAIZ / "retificacao.py").read_text(encoding="utf-8")
    for proibido in ("timedelta", "date.today", "datetime.now"):
        assert proibido not in codigo, f"o módulo calcula data com {proibido}"


def test_a_normalizacao_do_nome_e_a_da_casa():
    """Copiá-la faria duas formas de normalizar nome, e a busca deste módulo
    acharia coisa diferente da do Protesto para o mesmo nome — que é o defeito
    que o módulo de fraudes já teve, duas vezes."""
    codigo = (RAIZ / "retificacao.py").read_text(encoding="utf-8")
    assert "from pt_schema import normalizar_nome" in codigo
    assert "def normalizar_nome" not in codigo
