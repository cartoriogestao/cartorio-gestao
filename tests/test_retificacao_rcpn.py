"""Retificação, restauração e suprimento no Registro Civil — arts. 348 a 355.

O QUE ESTES TESTES GUARDAM
    **Que não se decide sem a consulta à CRC.** O art. 348, § 2º a torna
    *condição de validade da decisão* — decidir sem consultar é decidir sem o
    que a norma exige. Não é aviso: é recusa.

    **Que «erro imputável à serventia» não é caixinha de marcar.** O art. 353 a
    transforma em gratuidade, comunicação ao FERC **e** ao FERJ, e cobrança
    contra o delegatário titular da época — uma pessoa nomeada.

    **Que o prazo conta do pedido INSTRUÍDO**, e não do dia em que a pessoa
    apareceu. Contar da chegada poria o oficial em atraso por falta de documento
    que o requerente ainda não trouxe.

    **Que o suprimento não exige assento** — ali o assento não existe: é o que se
    supre. Exigi-lo travaria justamente o instituto para o qual ele não existe.
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import retificacao_rcpn as RR                                    # noqa: E402
import rr_tjma as NORMA                                          # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-20T09:00"
FUNDAMENTO = ("o erro é evidente na comparação com a certidão de nascimento "
              "apresentada, e não exige indagação (art. 352, I)")


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _assento(con, nome="MARIA DAS DORES", numero=1):
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em)
           VALUES ('RC_A','NASCIMENTO',?,?,'2026-01-15','2026-01-10','ATIVO',
                   'SISTEMA',?)""", (numero, nome, AGORA))
    return int(cur.lastrowid)


def _abrir(con, **extra):
    campos = dict(instituto="RETIFICACAO", forma="ESCRITO",
                  requerente_nome="MARIA DAS DORES",
                  o_que_se_pede="corrigir o nome da genitora",
                  ano=2026, agora=AGORA, por="jean",
                  assento_descricao="Livro A-24, fl. 166, termo 19552")
    campos.update(extra)
    return RR.abrir(con, **campos)


def _ate_a_decisao(con, **extra):
    """Leva um processo até a véspera da decisão — instruído e com a CRC."""
    pid = _abrir(con, **extra)
    RR.instruir(con, pid, agora=AGORA, por="jean")
    RR.registrar_consulta_crc(
        con, pid, o_que_se_procurou="nome, data de nascimento e filiação",
        resultado="nenhuma duplicidade; nenhum ato em outra serventia",
        agora=AGORA, por="jean")
    return pid


# ------------------------------------------------ a norma


def test_os_tres_institutos_nao_sao_a_mesma_coisa():
    """Um menu que os juntasse num «corrigir assento» faria o escrevente
    escolher o caminho errado."""
    assert NORMA.CHAVES == ("RETIFICACAO", "RESTAURACAO", "SUPRIMENTO")
    for x in NORMA.INSTITUTOS:
        assert x["artigo"] and x["requisito"] and x["o_que"]
    # e cada um tem o SEU requisito
    assert len({x["requisito"] for x in NORMA.INSTITUTOS}) >= 2


def test_as_tres_formas_do_pedido_e_a_verbal_exige_termo():
    """Quem chega ao balcão dizendo «meu nome está errado» está formulando um
    requerimento — e mandá-lo voltar com petição é negar o que a norma
    permite."""
    assert NORMA.FORMAS == ("ESCRITO", "ELETRONICO", "VERBAL")
    assert "imediatamente" in NORMA.forma("VERBAL")["exige"]
    assert NORMA.forma("ESCRITO")["exige"] == ""


def test_o_prazo_e_de_dez_dias_uteis_e_conta_do_instruido():
    """O § 3º **qualifica**: «10 (dez) dias úteis». E «devidamente instruído» é
    a condição, não enfeite."""
    assert NORMA.PRAZO_DECISAO_DIAS_UTEIS == 10
    assert "devidamente instruído" in NORMA.DE_QUANDO_CONTA


def test_a_consulta_a_crc_e_condicao_de_validade():
    assert "art. 348, § 2º" == NORMA.CONSULTA_CRC["artigo"]
    assert "condição de validade" in NORMA.CONSULTA_CRC["por_que"]
    assert "art. 365" in NORMA.CONSULTA_CRC["se_achar"]


def test_o_deferido_lanca_no_livro_CORRENTE():
    """Lançar no livro antigo seria escrever em livro encerrado; lançar no
    corrente sem a remissão deixaria dois assentos da mesma pessoa sem um
    apontar para o outro — que é como nasce a duplicidade do art. 365."""
    assert "corrente" in NORMA.ONDE_SE_LANCA["livro"]
    assert "recíprocas" in NORMA.ONDE_SE_LANCA["remissoes"]
    assert NORMA.ONDE_SE_LANCA["pode_ser"] == ("parcial", "total")


def test_sao_dois_fundos_e_nao_um():
    """Comunicar só a um deixaria o ressarcimento pela metade, e a norma nomeia
    os dois."""
    siglas = [x["sigla"] for x in NORMA.ERRO_DA_SERVENTIA["comunicar"]]
    assert siglas == ["FERC", "FERJ"]
    assert "Registro Civil" in NORMA.ERRO_DA_SERVENTIA["comunicar"][0]["nome"]


def test_o_mandado_de_outra_comarca_nao_precisa_de_cumpra_se():
    """Isto evita uma recusa comum no balcão."""
    assert "independente do «cumpra-se»" in \
        NORMA.MANDADO_DE_OUTRA_COMARCA["texto"]


def test_a_peticao_pode_ser_assinada_por_procurador():
    """Recusar a procuração no balcão seria negar o que a norma permite —
    redação do Provimento nº 8/2023."""
    assert "procurador" in NORMA.QUEM_ASSINA
    assert "representante legal" in NORMA.QUEM_ASSINA


# ------------------------------------------------ abrir


def test_abrir_numera_por_exercicio(casa):
    con = _con(casa)
    with con:
        assert _abrir(con)
        con.execute("SELECT 1")
        segundo = _abrir(con)
    linha = dict(con.execute("SELECT * FROM rr_processos WHERE id=?",
                             (segundo,)).fetchone())
    assert linha["numero"] == "2"
    assert linha["ano"] == 2026


def test_o_pedido_verbal_sem_termo_recusa(casa):
    """O § 1º, III manda reduzi-lo a termo **imediatamente**, colhendo a
    assinatura do declarante."""
    con = _con(casa)
    with pytest.raises(RR.RetificacaoRcpnError) as erro:
        with con:
            _abrir(con, forma="VERBAL")
    assert "reduzido a termo" in str(erro.value)


def test_o_pedido_verbal_com_termo_entra(casa):
    con = _con(casa)
    with con:
        pid = _abrir(con, forma="VERBAL",
                     termo_verbal="Compareceu MARIA e declarou que o nome da "
                                  "genitora está grafado como MARIA e o certo "
                                  "é MARIA JOSÉ.")
    linha = dict(con.execute("SELECT * FROM rr_processos WHERE id=?",
                             (pid,)).fetchone())
    assert linha["termo_verbal_em"] == AGORA


def test_o_suprimento_nao_exige_assento(casa):
    """ALI O ASSENTO NÃO EXISTE: é o que se supre. Exigi-lo travaria justamente o
    instituto para o qual ele não existe."""
    con = _con(casa)
    with con:
        pid = RR.abrir(con, instituto="SUPRIMENTO", forma="ESCRITO",
                       requerente_nome="JOÃO", o_que_se_pede="suprir o assento",
                       ano=2026, agora=AGORA, por="jean")
    assert pid


def test_a_retificacao_exige_dizer_de_que_assento_se_trata(casa):
    con = _con(casa)
    with pytest.raises(RR.RetificacaoRcpnError) as erro:
        with con:
            RR.abrir(con, instituto="RETIFICACAO", forma="ESCRITO",
                     requerente_nome="JOÃO", o_que_se_pede="corrigir",
                     ano=2026, agora=AGORA, por="jean")
    assert "de que assento" in str(erro.value)


def test_instituto_e_forma_desconhecidos_recusam(casa):
    con = _con(casa)
    for extra in ({"instituto": "INVENTADO"}, {"forma": "TELEPATIA"}):
        with pytest.raises(ValueError):
            with con:
                _abrir(con, **extra)


# ------------------------------------------------ o prazo


def test_o_prazo_conta_do_instruido_e_em_dias_uteis(casa):
    """Contar da chegada poria o oficial em atraso por falta de documento que o
    requerente ainda não trouxe."""
    con = _con(casa)
    with con:
        pid = _abrir(con)
    linha = dict(con.execute("SELECT * FROM rr_processos WHERE id=?",
                             (pid,)).fetchone())
    assert linha["prazo_ate"] is None       # ainda nao conta
    with con:
        r = RR.instruir(con, pid, agora=AGORA, por="jean")
    # 20/08/2026 mais 10 dias uteis nao e 30/08: ha fim de semana no meio
    assert r["prazo_ate"] > "2026-08-30"


def test_nao_se_instrui_duas_vezes(casa):
    con = _con(casa)
    with con:
        pid = _abrir(con)
        RR.instruir(con, pid, agora=AGORA, por="jean")
    with pytest.raises(RR.RetificacaoRcpnError):
        with con:
            RR.instruir(con, pid, agora=AGORA, por="jean")


def test_fora_do_prazo_lista_quem_estourou(casa):
    con = _con(casa)
    with con:
        pid = _abrir(con)
        RR.instruir(con, pid, agora=AGORA, por="jean")
    assert RR.fora_do_prazo(con, hoje="2026-08-25") == []
    assert len(RR.fora_do_prazo(con, hoje="2026-12-01")) == 1


# ------------------------------------------------ a consulta à CRC


def test_nao_se_decide_sem_a_consulta_a_crc(casa):
    """**É CONDIÇÃO DE VALIDADE DA DECISÃO**, e não zelo: decidir sem consultar é
    decidir sem o que a norma exige."""
    con = _con(casa)
    with con:
        pid = _abrir(con)
        RR.instruir(con, pid, agora=AGORA, por="jean")
    with pytest.raises(RR.RetificacaoRcpnError) as erro:
        with con:
            RR.decidir(con, pid, decisao="DEFERIDO", fundamento=FUNDAMENTO,
                       agora=AGORA, por="jean")
    assert "consulta obrigatória à CRC" in str(erro.value)


def test_a_consulta_exige_dizer_o_que_se_achou(casa):
    """«ok» não responde à pergunta que a correição faz, e é o que um campo solto
    receberia."""
    con = _con(casa)
    with con:
        pid = _abrir(con)
    for extra in ({"o_que_se_procurou": " "}, {"resultado": " "}):
        campos = dict(o_que_se_procurou="nome e filiação",
                      resultado="nada encontrado", agora=AGORA, por="jean")
        campos.update(extra)
        with pytest.raises(RR.RetificacaoRcpnError):
            with con:
                RR.registrar_consulta_crc(con, pid, **campos)


def test_a_duplicidade_vira_andamento_com_o_art_365(casa):
    """O art. 365 manda comunicar imediatamente ao juiz corregedor, com bloqueio
    cautelar do registro mais recente."""
    con = _con(casa)
    with con:
        pid = _abrir(con)
        RR.registrar_consulta_crc(
            con, pid, o_que_se_procurou="nome e data",
            resultado="há assento da mesma pessoa na serventia de Imperatriz",
            achou_duplicidade=True, agora=AGORA, por="jean")
    andamento = [x["o_que"] for x in con.execute(
        "SELECT o_que FROM rr_andamento WHERE processo_id=?", (pid,))]
    assert any("art. 365" in x for x in andamento)


def test_o_modulo_nao_consulta_a_crc_sozinho():
    """Um botão que dissesse «consultado» sem consultar seria pior que não ter
    botão: ele responderia, e responderia errado."""
    codigo = (RAIZ / "retificacao_rcpn.py").read_text(encoding="utf-8")
    for proibido in ("import requests", "import urllib", "import http.client"):
        assert proibido not in codigo


# ------------------------------------------------ decidir


def test_decidir_exige_fundamento(casa):
    """O § 3º diz «de forma fundamentada». Decisão sem fundamento é a que se
    desfaz depois."""
    con = _con(casa)
    with con:
        pid = _ate_a_decisao(con)
    with pytest.raises(RR.RetificacaoRcpnError) as erro:
        with con:
            RR.decidir(con, pid, decisao="DEFERIDO", fundamento="sim",
                       agora=AGORA, por="jean")
    assert "fundamentada" in str(erro.value)


def test_decidir_com_tudo_pronto(casa):
    con = _con(casa)
    with con:
        pid = _ate_a_decisao(con)
        r = RR.decidir(con, pid, decisao="DEFERIDO", fundamento=FUNDAMENTO,
                       agora=AGORA, por="jean")
    assert r["decisao"] == "DEFERIDO"
    assert r["comunicacoes_abertas"] == []


def test_nao_se_decide_duas_vezes(casa):
    con = _con(casa)
    with con:
        pid = _ate_a_decisao(con)
        RR.decidir(con, pid, decisao="DEFERIDO", fundamento=FUNDAMENTO,
                   agora=AGORA, por="jean")
    with pytest.raises(RR.RetificacaoRcpnError) as erro:
        with con:
            RR.decidir(con, pid, decisao="INDEFERIDO", fundamento=FUNDAMENTO,
                       agora=AGORA, por="jean")
    assert "já foi decidido" in str(erro.value)


def test_decisao_inventada_recusa(casa):
    con = _con(casa)
    with con:
        pid = _ate_a_decisao(con)
    with pytest.raises(RR.RetificacaoRcpnError):
        with con:
            RR.decidir(con, pid, decisao="TALVEZ", fundamento=FUNDAMENTO,
                       agora=AGORA, por="jean")


def test_o_que_falta_para_decidir_diz_a_crc_primeiro(casa):
    """É a única que a norma chama de obrigatória."""
    con = _con(casa)
    with con:
        pid = _abrir(con)
    faltas = RR.o_que_falta_para_decidir(con, pid)
    assert "CRC" in faltas[0]


# ------------------------------------------------ o art. 353


def test_erro_da_serventia_exige_fundamento_proprio(casa):
    """A marca gera gratuidade, duas comunicações e uma cobrança contra **uma
    pessoa nomeada**: o delegatário titular da época."""
    con = _con(casa)
    with con:
        pid = _ate_a_decisao(con)
    with pytest.raises(RR.RetificacaoRcpnError) as erro:
        with con:
            RR.decidir(con, pid, decisao="DEFERIDO", fundamento=FUNDAMENTO,
                       agora=AGORA, por="jean", erro_da_serventia=True,
                       erro_fundamento="foi erro nosso")
    assert "delegatário titular da época" in str(erro.value)


def test_erro_da_serventia_abre_as_duas_comunicacoes(casa):
    """Comunicar só a um deixaria o ressarcimento pela metade."""
    con = _con(casa)
    with con:
        pid = _ate_a_decisao(con)
        r = RR.decidir(
            con, pid, decisao="DEFERIDO", fundamento=FUNDAMENTO, agora=AGORA,
            por="jean", erro_da_serventia=True,
            erro_fundamento="a grafia do nome divergiu do documento "
                            "apresentado no ato originário, por falha da "
                            "digitação desta serventia")
    assert set(r["comunicacoes_abertas"]) == {"FERC", "FERJ"}
    assert len(RR.comunicacoes_353(con, pid)) == 2


def test_registrar_a_comunicacao_congela_o_teor(casa):
    con = _con(casa)
    with con:
        pid = _ate_a_decisao(con)
        RR.decidir(con, pid, decisao="DEFERIDO", fundamento=FUNDAMENTO,
                   agora=AGORA, por="jean", erro_da_serventia=True,
                   erro_fundamento="erro de digitação desta serventia no ato "
                                   "originário, conferido no livro")
        RR.registrar_comunicacao_353(con, pid, fundo="FERC",
                                     teor="Ofício ao FERC...", agora=AGORA,
                                     por="jean", canal="malote")
    ferc = [x for x in RR.comunicacoes_353(con, pid) if x["fundo"] == "FERC"][0]
    assert ferc["situacao"] == "ENVIADA"
    assert len(ferc["hash_teor"]) == 64


def test_comunicacao_sem_pendencia_avisa_em_vez_de_mentir(casa):
    """`rowcount` É RESPOSTA; «deu certo» É SUPOSIÇÃO. O recibo da DOI dizia
    «registrado» com zero linhas mudadas."""
    con = _con(casa)
    with con:
        pid = _ate_a_decisao(con)
        RR.decidir(con, pid, decisao="DEFERIDO", fundamento=FUNDAMENTO,
                   agora=AGORA, por="jean")
    with pytest.raises(RR.RetificacaoRcpnError) as erro:
        with con:
            RR.registrar_comunicacao_353(con, pid, fundo="FERJ", teor="Ofício",
                                         agora=AGORA, por="jean")
    assert "Não há comunicação pendente" in str(erro.value)


def test_fundo_inventado_recusa(casa):
    con = _con(casa)
    with con:
        pid = _ate_a_decisao(con)
    with pytest.raises(RR.RetificacaoRcpnError):
        with con:
            RR.registrar_comunicacao_353(con, pid, fundo="FUNDEB",
                                         teor="Ofício", agora=AGORA,
                                         por="jean")


# ------------------------------------------------ o ato


def test_so_o_deferido_produz_ato(casa):
    con = _con(casa)
    with con:
        pid = _ate_a_decisao(con)
        RR.decidir(con, pid, decisao="INDEFERIDO", fundamento=FUNDAMENTO,
                   agora=AGORA, por="jean")
    with pytest.raises(RR.RetificacaoRcpnError) as erro:
        with con:
            RR.registrar_ato(con, pid, ato_id=1, agora=AGORA, por="jean")
    assert "Só o pedido deferido" in str(erro.value)


def test_amarrar_ato_que_nao_existe_recusa_em_vez_de_estourar(casa):
    """Sem isso batia na chave estrangeira e virava HTTP 500 no fim de um
    processo de dias — o defeito que o teste de tela do usucapião pegou."""
    con = _con(casa)
    with con:
        pid = _ate_a_decisao(con)
        RR.decidir(con, pid, decisao="DEFERIDO", fundamento=FUNDAMENTO,
                   agora=AGORA, por="jean")
    with pytest.raises(RR.RetificacaoRcpnError) as erro:
        with con:
            RR.registrar_ato(con, pid, ato_id=9999, agora=AGORA, por="jean")
    assert "Esse ato não existe" in str(erro.value)


def test_amarrar_o_ato_conclui_o_processo(casa):
    con = _con(casa)
    with con:
        aid = _assento(con)
        cur = con.execute(
            """INSERT INTO rc_atos (assento_id, tipo, data_ato, criado_em)
               VALUES (?,'RETIFICACAO','2026-08-25',?)""", (aid, AGORA))
        ato_id = int(cur.lastrowid)
        pid = _ate_a_decisao(con, assento_id=aid)
        RR.decidir(con, pid, decisao="DEFERIDO", fundamento=FUNDAMENTO,
                   agora=AGORA, por="jean")
        RR.registrar_ato(con, pid, ato_id=ato_id, agora=AGORA, por="jean")
    linha = dict(con.execute("SELECT * FROM rr_processos WHERE id=?",
                             (pid,)).fetchone())
    assert linha["situacao"] == "CONCLUIDO"
    assert linha["ato_id"] == ato_id


# ------------------------------------------------ o que fazer agora


def test_os_proximos_passos_seguem_o_rito(casa):
    """Num rito de dias, «e agora?» é a pergunta que mais se repete."""
    con = _con(casa)
    with con:
        pid = _abrir(con)
    passos = " ".join(RR.proximos_passos(con, pid))
    assert "instruído" in passos
    assert "CRC" in passos
    with con:
        RR.instruir(con, pid, agora=AGORA, por="jean")
        RR.registrar_consulta_crc(con, pid, o_que_se_procurou="nome",
                                  resultado="nada", agora=AGORA, por="jean")
    assert "Decidir" in " ".join(RR.proximos_passos(con, pid))


def test_depois_de_deferir_o_passo_e_lavrar_no_livro_corrente(casa):
    con = _con(casa)
    with con:
        pid = _ate_a_decisao(con)
        RR.decidir(con, pid, decisao="DEFERIDO", fundamento=FUNDAMENTO,
                   agora=AGORA, por="jean")
    passos = " ".join(RR.proximos_passos(con, pid))
    assert "livro corrente" in passos
    assert "recíprocas" in passos


def test_o_verbal_sem_termo_aparece_nos_proximos_passos(casa):
    """Só chega aqui quem gravou o termo depois — mas se o campo esvaziar, a
    tela tem de cobrar."""
    con = _con(casa)
    with con:
        pid = _abrir(con, forma="VERBAL", termo_verbal="Compareceu MARIA...")
        con.execute("UPDATE rr_processos SET termo_verbal='' WHERE id=?",
                    (pid,))
    assert "termo" in " ".join(RR.proximos_passos(con, pid)).lower()


# ------------------------------------------------ o módulo não decide sozinho


def test_o_modulo_nao_decide_se_o_erro_e_da_serventia():
    """É juízo do oficial, com efeito sobre o patrimônio de terceiro. **Sexta vez
    que esta regra aparece neste projeto**: usucapião, fraudes, habilitação,
    impedimento, inacabados, e agora."""
    publicos = [n for n in dir(RR)
                if not n.startswith("_") and callable(getattr(RR, n))]
    for nome in publicos:
        for proibido in ("julgar", "avaliar_erro", "imputar", "classificar"):
            assert proibido not in nome.lower(), f"`{nome}` faz o que não deve"


def test_o_modulo_nao_lavra_ato():
    """Quem lavra é a tela do RCPN, que tem o livro, o selo e os emolumentos."""
    codigo = (RAIZ / "retificacao_rcpn.py").read_text(encoding="utf-8")
    assert "INSERT INTO rc_atos" not in codigo
    assert "INSERT INTO rc_assentos" not in codigo
