"""
Testes do ESTOQUE DAS FOLHAS DE SEGURANCA.

POR QUE ELE EXISTE
    Medindo o selo do civil em 27/08/2026, os 175 selos das especies carregavam
    um campo que este sistema nao sabia preencher: `papelMoeda`. O E-Oficio
    controlava 510 folhas numeradas em `tbPapelMoedaRCPN`; o sistema novo nao
    controlava nenhuma. **Sem o numero da folha, o selo do civil nao se monta.**

O QUE ESTES TESTES GUARDAM
      - A FOLHA E UNICA, e a regra mora no banco. Duas com o mesmo numero sao
        duas certidoes no mundo dizendo ser a mesma folha;
      - A ORDEM E A DA GAVETA: a proxima e a MENOR em branco, e por NUMERO —
        os codigos desta casa tem larguras diferentes, e em ordem de texto
        `7225136` viria antes de `725061`;
      - FOLHA GASTA NAO SE GASTA DUAS VEZES, e a recusa diz em que ato ela esta;
      - FOLHA NAO SE APAGA: inutiliza-se, COM MOTIVO — como a folha do livro;
      - O ESTOQUE AVISA ANTES DE ACABAR, porque papel demora a chegar.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import papel_seguranca as PP                       # noqa: E402

AGORA = "2026-08-27T10:00:00"
DEPOIS = "2026-08-27T15:30:00"


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    PP.init_papel_schema(con)
    return con


def _caixa(con, de="7225136", ate="7225145", serie="HA"):
    return PP.receber_remessa(con, fornecedor="ARPENBRASIL", serie=serie,
                              codigo_de=de, codigo_ate=ate, agora=AGORA,
                              nota_fiscal="NF 1234", usuario="JEAN")


# ---------------------------------------------------------- a remessa


def test_a_caixa_vira_uma_linha_por_folha():
    """E o unico jeito de responder «onde esta a folha 7225319?» sem abrir a
    gaveta."""
    con = banco()
    r = _caixa(con)
    assert r["quantas"] == 10
    assert PP.estoque(con)["em_branco"] == 10
    assert PP.ler(con, "7225140")["situacao"] == "EM BRANCO"


def test_a_mesma_caixa_duas_vezes_e_recusada():
    """Receber duas vezes criaria folhas que ja existem, com a numeracao
    andando duas vezes pelo mesmo lugar."""
    con = banco()
    _caixa(con)
    with pytest.raises(PP.PapelError, match="já estão cadastradas"):
        _caixa(con)


def test_faixa_que_se_sobrepoe_a_outra_e_recusada():
    con = banco()
    _caixa(con, "7225136", "7225145")
    with pytest.raises(PP.PapelError, match="já estão cadastradas"):
        _caixa(con, "7225140", "7225150")


def test_a_mesma_folha_com_ZERO_A_MAIS_e_recusada():
    """O incidente de 09/09/2026: a carga gravou `7225136` sem zero à
    esquerda, e uma remessa nova digitada `007225140` (9 dígitos, como veio
    impressa na caixa) não batia contra ela num `codigo IN (...)` de texto —
    86 folhas entraram duplicadas. A recusa agora olha o NÚMERO."""
    con = banco()
    _caixa(con, "7225136", "7225145")
    with pytest.raises(PP.PapelError, match="já estão cadastradas"):
        _caixa(con, "007225140", "007225150")


def test_a_largura_do_primeiro_numero_manda():
    """`0725061` e `725061` sao a mesma folha para o fornecedor e dois codigos
    diferentes para um UNIQUE."""
    assert PP.faixa("0725061", "725063") == ["0725061", "0725062", "0725063"]
    assert PP.faixa("725061", "725063") == ["725061", "725062", "725063"]


def test_faixa_ao_contrario_e_recusada():
    with pytest.raises(PP.PapelError, match="menor que o inicial"):
        PP.faixa("7225145", "7225136")


def test_o_zero_a_mais_no_numero_final_e_recusado():
    """`1` a `1000000` criaria um milhao de linhas e travaria o banco."""
    with pytest.raises(PP.PapelError, match="limite de uma remessa"):
        PP.faixa("1", "1000000")


def test_codigo_que_nao_e_numero_e_recusado():
    with pytest.raises(PP.PapelError, match="algarismos"):
        PP.faixa("HA-136", "HA-145")


def test_remessa_sem_fornecedor_e_recusada():
    con = banco()
    with pytest.raises(PP.PapelError, match="de quem veio"):
        PP.receber_remessa(con, fornecedor="  ", codigo_de="1", codigo_ate="9",
                           agora=AGORA)


# ------------------------------------------------------------- a gaveta


def test_a_proxima_e_a_menor_em_branco_e_por_NUMERO():
    """Em ordem de TEXTO, `7225136` viria antes de `725061` — e a gaveta nao e
    alfabetica."""
    con = banco()
    _caixa(con, "7225136", "7225140", serie="HA")
    _caixa(con, "725061", "725063", serie="HA")
    assert PP.proxima_folha(con)["codigo"] == "725061"


def test_a_folha_gasta_sai_da_frente_da_gaveta():
    con = banco()
    _caixa(con)
    PP.usar(con, "7225136", tabela="rc_certidoes", ato_id=7, agora=AGORA,
            selo="CERTID000000ABC")
    assert PP.proxima_folha(con)["codigo"] == "7225137"
    linha = PP.ler(con, "7225136")
    assert linha["situacao"] == "USADA"
    assert linha["tabela"] == "rc_certidoes" and linha["ato_id"] == 7
    assert linha["selo"] == "CERTID000000ABC"


def test_a_mesma_folha_nao_se_gasta_duas_vezes():
    """Duas certidoes na mesma folha e o defeito que so aparece quando as duas
    estao na rua."""
    con = banco()
    _caixa(con)
    PP.usar(con, "7225136", tabela="rc_certidoes", ato_id=7, agora=AGORA)
    with pytest.raises(PP.PapelError) as erro:
        PP.usar(con, "7225136", tabela="rc_certidoes", ato_id=8, agora=DEPOIS)
    assert "já foi usada" in str(erro.value)
    assert "rc_certidoes" in str(erro.value)      # diz ONDE ela esta


def test_folha_que_nao_esta_no_estoque_e_recusada():
    con = banco()
    _caixa(con)
    with pytest.raises(PP.PapelError, match="não está no estoque"):
        PP.usar(con, "9999999", tabela="rc_certidoes", ato_id=1, agora=AGORA)


# ---------------------------------------------------------- a recuperacao


def test_cancelar_o_ato_devolve_a_folha_e_guarda_o_caminho():
    """A linha volta limpa à gaveta, mas a ligação anterior não desaparece."""
    con = banco()
    _caixa(con)
    PP.usar(con, "7225136", tabela="rc_certidoes", ato_id=7, agora=AGORA,
            selo="CERTID000000ABC", usuario="BEATRIZ")

    r = PP.recuperar_do_ato(
        con, tabela="rc_certidoes", ato_id=7, agora=DEPOIS,
        motivo="certidão emitida com erro", usuario="JEAN")

    assert r == {"quantas": 1, "codigos": ["7225136"]}
    folha = PP.ler(con, "7225136")
    assert folha["situacao"] == "EM BRANCO"
    assert folha["tabela"] is None and folha["ato_id"] is None
    assert folha["selo"] is None and folha["usada_em"] is None
    assert PP.proxima_folha(con)["codigo"] == "7225136"

    movimentos = PP.movimentos_da_folha(con, "7225136")
    assert [(m["situacao_anterior"], m["situacao_nova"])
            for m in movimentos] == [("EM BRANCO", "USADA"),
                                     ("USADA", "EM BRANCO")]
    volta = movimentos[-1]
    assert volta["tabela"] == "rc_certidoes" and volta["ato_id"] == 7
    assert volta["selo"] == "CERTID000000ABC"
    assert volta["ocorrido_por"] == "JEAN"


def test_recuperar_e_idempotente_e_nao_toca_outro_ato():
    con = banco()
    _caixa(con)
    PP.usar(con, "7225136", tabela="rc_certidoes", ato_id=7, agora=AGORA)
    PP.usar(con, "7225137", tabela="rc_certidoes", ato_id=8, agora=AGORA)

    assert PP.recuperar_do_ato(
        con, tabela="rc_certidoes", ato_id=7, agora=DEPOIS)["quantas"] == 1
    assert PP.recuperar_do_ato(
        con, tabela="rc_certidoes", ato_id=7, agora=DEPOIS)["quantas"] == 0
    assert PP.ler(con, "7225137")["situacao"] == "USADA"
    assert len(PP.movimentos_da_folha(con, "7225136")) == 2


def test_abertura_do_sistema_recupera_folha_presa_a_cancelamento_antigo():
    con = banco()
    _caixa(con)
    con.execute("CREATE TABLE rc_certidoes (id INTEGER PRIMARY KEY, cancelada_em TEXT)")
    con.execute("INSERT INTO rc_certidoes VALUES (19, '2026-08-20T10:00:00')")
    PP.usar(con, "7225136", tabela="rc_certidoes", ato_id=19, agora=AGORA)

    r = PP.recuperar_cancelados_existentes(con, agora=DEPOIS)

    assert r == {"quantas": 1, "por_tabela": {"rc_certidoes": ["7225136"]}}
    assert PP.ler(con, "7225136")["situacao"] == "EM BRANCO"


# ------------------------------------------------------- a inutilizacao


def test_a_folha_estragada_sai_do_estoque_com_motivo():
    con = banco()
    _caixa(con)
    PP.inutilizar(con, "7225136", motivo="saiu borrada na impressora",
                  agora=AGORA, usuario="DEBORA")
    linha = PP.ler(con, "7225136")
    assert linha["situacao"] == "INUTILIZADA"
    assert "borrada" in linha["inutilizada_motivo"]
    assert linha["inutilizada_por"] == "DEBORA"
    # E ela sai da frente da gaveta, sem sumir da contagem.
    assert PP.proxima_folha(con)["codigo"] == "7225137"
    assert PP.estoque(con)["total"] == 10


def test_inutilizar_sem_motivo_e_recusado():
    """Folha que some sem explicacao e folha que a inspecao cobra e ninguem
    sabe responder."""
    con = banco()
    _caixa(con)
    with pytest.raises(PP.PapelError, match="Escreva por que"):
        PP.inutilizar(con, "7225136", motivo="   ", agora=AGORA)


def test_folha_ja_usada_nao_se_inutiliza():
    """Se a certidao saiu errada, o caminho e cancelar a certidao."""
    con = banco()
    _caixa(con)
    PP.usar(con, "7225136", tabela="rc_certidoes", ato_id=7, agora=AGORA)
    with pytest.raises(PP.PapelError, match="cancelar a certidão"):
        PP.inutilizar(con, "7225136", motivo="rasgou", agora=DEPOIS)


def test_folha_inutilizada_nao_se_usa():
    con = banco()
    _caixa(con)
    PP.inutilizar(con, "7225136", motivo="rasgou", agora=AGORA)
    with pytest.raises(PP.PapelError, match="inutilizada"):
        PP.usar(con, "7225136", tabela="rc_certidoes", ato_id=1, agora=DEPOIS)


# --------------------------------------------------------- o estoque


def test_o_estoque_avisa_antes_de_acabar():
    """Papel se compra de fornecedor e demora a chegar; acabar no meio do
    expediente e o balcao sem poder entregar certidao."""
    con = banco()
    _caixa(con)                       # 10 folhas, abaixo do piso de 100
    q = PP.estoque(con)
    assert q["acabando"] is True
    assert q["acabou"] is False
    assert q["piso"] == PP.PISO_DO_ESTOQUE


def test_estoque_cheio_nao_avisa():
    """Alarme que soa sempre e alarme que ninguem ouve."""
    con = banco()
    _caixa(con, "7225136", "7225500")
    assert PP.estoque(con)["acabando"] is False


def test_sem_papel_nenhum_a_tela_diz_outra_coisa():
    """Nao e «va comprando»: e «a certidao nao sai hoje»."""
    con = banco()
    q = PP.estoque(con)
    assert q["acabou"] is True
    assert q["proxima"] is None


def test_as_folhas_de_um_ato():
    """Duas folhas num ato so e o caso da certidao de mais de uma folha."""
    con = banco()
    _caixa(con)
    PP.usar(con, "7225136", tabela="rc_certidoes", ato_id=7, agora=AGORA)
    PP.usar(con, "7225137", tabela="rc_certidoes", ato_id=7, agora=AGORA)
    assert [f["codigo"] for f in PP.do_ato(con, "rc_certidoes", 7)] \
        == ["7225136", "7225137"]


def test_o_modulo_nao_lavra_nada():
    """O papel nao pratica ato: ele e o suporte em que o ato e impresso."""
    proibidas = [n for n in dir(PP) if not n.startswith("_")
                 and any(p in n.lower() for p in
                         ("lavrar", "numerar", "selar", "cobrar", "cancelar",
                          "averbar", "decidir"))]
    assert proibidas == [], f"o papel nao pratica ato: {proibidas}"


# ============ A CARGA DO ESTOQUE, do acervo do E-Oficio (27/08/2026)
#
# O modulo do papel nasceu com o estoque VAZIO, e a casa tem 349 folhas em
# branco na gaveta. Sem a carga, o oficial digitaria cinco faixas a mao — e,
# pior, o sistema nao saberia quais das 510 ja foram gastas, e ofereceria como
# proxima uma folha que ja esta numa certidao no mundo.


def _acervo_falso() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE tbPapelMoedaRCPN (
            intChave INTEGER, strCodigo TEXT, strProtocoloGeral TEXT,
            intTipoAto INTEGER, bitUtilizado INTEGER,
            intCodigoRemessa INTEGER, strSerie TEXT);
    """)
    con.executemany(
        "INSERT INTO tbPapelMoedaRCPN VALUES (?,?,?,?,?,?,?)",
        [(1, "7225136", "2026.08.152", 1, 1, 5, "HA"),
         (2, "7225137", None, None, 0, 5, "HA"),
         (3, "7225138", None, None, 0, 5, "HA"),
         (4, "17610001", "2023.01.162", 1, 1, 1, "BA"),
         (5, "17610002", None, None, 0, 1, "BA")])
    con.commit()
    return con


def test_a_carga_traz_o_estoque_com_as_usadas_marcadas():
    """A folha usada entra USADA. Ofere-la como proxima seria mandar imprimir
    numa folha que ja esta numa certidao no mundo."""
    import acervo_carga as AC

    con = banco()
    r = AC.carregar_papel(con, _acervo_falso(), agora=AGORA)
    assert r.lidos == 5
    assert r.inseridos == 5
    assert r.contagens == {"usadas": 2, "em_branco": 3}

    q = PP.estoque(con)
    assert q["em_branco"] == 3 and q["usadas"] == 2
    # A proxima e a menor EM BRANCO — e nao a menor de todas.
    assert q["proxima"] == "7225137"
    assert PP.ler(con, "17610001")["situacao"] == "USADA"


def test_a_carga_do_papel_e_repetivel():
    """Ela e repetivel por construcao, como as outras: o que ja esta no banco
    volta como «repetido» e nao se duplica."""
    import acervo_carga as AC

    con = banco()
    acervo = _acervo_falso()
    AC.carregar_papel(con, acervo, agora=AGORA)
    de_novo = AC.carregar_papel(con, acervo, agora=DEPOIS)
    assert de_novo.inseridos == 0
    assert de_novo.repetidos == 5
    assert PP.estoque(con)["total"] == 5


def test_cada_remessa_do_acervo_vira_uma_remessa_aqui():
    """Sem isso a folha nao teria de onde ter vindo — e a inspecao pergunta de
    onde veio a folha numero tal."""
    import acervo_carga as AC

    con = banco()
    AC.carregar_papel(con, _acervo_falso(), agora=AGORA)
    caixas = PP.remessas(con)
    assert len(caixas) == 2                    # a remessa 5 (HA) e a 1 (BA)
    assert {c["serie"] for c in caixas} == {"HA", "BA"}
    assert all(c["fornecedor"] == "ARPENBRASIL" for c in caixas)


def test_a_folha_usada_entra_SEM_ato_amarrado():
    """O acervo guarda o protocolo geral, e nao a chave do ato.

    Amarrar por aproximacao seria dizer que a folha esta num ato que talvez
    nao seja o dela — e o razao passaria a mentir sobre onde cada folha foi
    parar.
    """
    import acervo_carga as AC

    con = banco()
    AC.carregar_papel(con, _acervo_falso(), agora=AGORA)
    linha = PP.ler(con, "7225136")
    assert linha["situacao"] == "USADA"
    assert linha["tabela"] is None and linha["ato_id"] is None
    # ... mas o protocolo do E-Oficio fica, que e a verdade que o acervo tem.
    assert linha["usada_por"] == "2026.08.152"


# --------------------------------------------------------- estornar remessa


def test_estornar_inutiliza_as_folhas_em_branco_da_remessa():
    con = banco()
    r = _caixa(con, "7225415", "7225417")
    ok = PP.estornar_remessa(con, r["remessa_id"],
                             motivo="duplicou a remessa 5", agora=DEPOIS,
                             usuario="JEAN")
    assert ok["inutilizadas"] == 3
    assert ok["ja_usadas"] == 0
    for codigo in ("7225415", "7225416", "7225417"):
        linha = PP.ler(con, codigo)
        assert linha["situacao"] == "INUTILIZADA"
        assert linha["inutilizada_motivo"] == "duplicou a remessa 5"


def test_estornar_NAO_TOCA_folha_ja_usada():
    """Desfazer a remessa nao desfaz o ato que ja gastou uma folha dela."""
    con = banco()
    r = _caixa(con, "7225415", "7225417")
    with con:
        PP.usar(con, "7225416", tabela="rc_certidoes", ato_id=1, agora=AGORA,
               usuario="JEAN")
    ok = PP.estornar_remessa(con, r["remessa_id"], motivo="engano", agora=DEPOIS)
    assert ok["inutilizadas"] == 2
    assert ok["ja_usadas"] == 1
    assert PP.ler(con, "7225416")["situacao"] == "USADA"
    assert PP.ler(con, "7225415")["situacao"] == "INUTILIZADA"


def test_estornar_exige_motivo():
    con = banco()
    r = _caixa(con)
    with pytest.raises(PP.PapelError, match="Escreva por que"):
        PP.estornar_remessa(con, r["remessa_id"], motivo="", agora=DEPOIS)


def test_estornar_remessa_desconhecida_e_recusado():
    con = banco()
    with pytest.raises(PP.PapelError, match="não encontrada"):
        PP.estornar_remessa(con, 999, motivo="engano", agora=DEPOIS)


def test_estornar_recusa_id_que_nao_e_numero():
    con = banco()
    with pytest.raises(PP.PapelError, match="não é um número válido"):
        PP.estornar_remessa(con, "abc", motivo="engano", agora=DEPOIS)


# -------------------------------------------------------- listar sem teto


def test_listar_com_limite_none_traz_todas_mesmo_passando_de_200():
    """Achado em 09/09/2026: a escolha livre da certidão chamava `listar`
    com o teto padrão (200), e uma folha em branco de verdade — na posição
    285 de 344 — ficava fora da lista que o escrevente via. Escolha não pode
    ter teto escondendo o que existe."""
    con = banco()
    _caixa(con, "1000000", "1000300")          # 301 folhas EM BRANCO
    todas = PP.listar(con, situacao="EM BRANCO", limite=None)
    assert len(todas) == 301
    assert "1000300" in [f["codigo"] for f in todas]


def test_listar_com_limite_continua_cortando_quando_pedido():
    """O histórico (`usadas`, `inutilizadas` em /rcpn/papel) pode continuar
    cortado — ninguém precisa ver a milésima folha já gasta."""
    con = banco()
    _caixa(con, "1000000", "1000300")
    so_dez = PP.listar(con, situacao="EM BRANCO", limite=10)
    assert len(so_dez) == 10
