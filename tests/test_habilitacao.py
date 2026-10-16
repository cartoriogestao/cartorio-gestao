"""A habilitação de casamento — o processo que antecede todo casamento.

O QUE ESTES TESTES PROTEGEM É A ORDEM, e cada etapa protege alguém:

    habilitar sem edital        tira de terceiro o direito de opor impedimento
                                — e é o impedimento que anula o casamento depois
    habilitar dentro do prazo   o prazo É esse direito; usá-lo pela metade é o
                                mesmo que não ter publicado
    celebrar com ela vencida    CC art. 1.532: passados noventa dias o processo
                                se refaz

QUEM RECUSA É O DOMÍNIO, E NÃO A TELA. Estes testes chamam as funções direto,
sem passar por rota nenhuma — a tela esconde o botão por educação; o domínio
recusa por dever.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import habilitacao as HAB                                    # noqa: E402
import hc_schema as HC                                       # noqa: E402
from hc_schema import init_hc_schema                          # noqa: E402
from nucleo_schema import init_nucleo_schema                  # noqa: E402
from rc_schema import init_rc_schema                         # noqa: E402

AGORA = "2026-08-27T10:00:00"
TEOR = ("Faço saber que pretendem casar-se FULANO DE TAL e BELTRANA DE TAL, "
        "e que apresentaram os documentos exigidos pelo art. 1.525 do Código "
        "Civil. Quem souber de impedimento, oponha-o na forma da lei.")


@pytest.fixture()
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    # O NÚCLEO ENTRA PORQUE `rc_atos` APONTA PARA `nu_livros`, e as travas ficam
    # LIGADAS: foi a lição do usucapião — o teste de domínio que rodava com a
    # chave estrangeira desligada passava, e o defeito só aparecia na tela, no
    # fim de um processo de meses.
    init_nucleo_schema(c)
    init_rc_schema(c)
    init_hc_schema(c)
    return c


def _abrir(con, **extra) -> int:
    dados = {"nubente1_nome": "FULANO DE TAL",
             "nubente1_estado_civil": "SOLTEIRO",
             "nubente2_nome": "BELTRANA DE TAL",
             "nubente2_estado_civil": "SOLTEIRA",
             "tipo": "CIVIL", "regime": "COMUNHAO_PARCIAL"}
    dados.update(extra)
    return HAB.abrir(con, dados, agora=AGORA, usuario="MARIO")


def _entregar_tudo(con, habilitacao_id: int) -> None:
    for d in HAB.o_que_falta(con, habilitacao_id):
        HAB.marcar_documento(con, d["id"], apresentado=True, agora=AGORA,
                             usuario="MARIO")


def _publicar(con, habilitacao_id: int, hoje="2026-08-27"):
    return HAB.publicar_edital(con, habilitacao_id, teor=TEOR, agora=AGORA,
                               hoje=hoje, usuario="MARIO")


# ------------------------------------------------------------- abrir


def test_o_processo_nasce_com_o_checklist_da_lei(con):
    """Item que alguém tem de lembrar de acrescentar é item que fica de fora."""
    h = _abrir(con)
    docs = HAB.documentos_de(con, h)
    codigos = {d["codigo"] for d in docs}
    # Os quatro primeiros incisos valem para todo mundo.
    assert {"CERTIDAO_NASCIMENTO", "AUTORIZACAO", "DECLARACAO_TESTEMUNHAS",
            "DECLARACAO_ESTADO_CIVIL"} <= codigos
    # E cada um vale PARA CADA NUBENTE: a certidão de um não supre a do outro.
    de_quem = {d["de_quem"] for d in docs}
    assert de_quem == {"NUBENTE1", "NUBENTE2"}
    assert all(d["fundamento"].startswith("CC art. 1.525") for d in docs)


def test_solteiro_nao_recebe_item_de_prova_de_dissolucao(con):
    """Checklist com item impossível é checklist que se ignora inteiro."""
    docs = HAB.documentos_de(con, _abrir(con))
    assert not any(d["codigo"] == "PROVA_DISSOLUCAO" for d in docs)


def test_viuvo_recebe(con):
    h = _abrir(con, nubente1_estado_civil="VIÚVO")
    docs = [d for d in HAB.documentos_de(con, h)
            if d["codigo"] == "PROVA_DISSOLUCAO"]
    assert len(docs) == 1
    assert docs[0]["de_quem"] == "NUBENTE1"


def test_sem_os_dois_nomes_nao_abre(con):
    with pytest.raises(HAB.HabilitacaoError, match="segundo nubente"):
        HAB.abrir(con, {"nubente1_nome": "FULANO"}, agora=AGORA)


def test_regime_e_tipo_saem_de_catalogo(con):
    with pytest.raises(HAB.HabilitacaoError, match="Tipo de casamento"):
        _abrir(con, tipo="INVENTADO")
    with pytest.raises(HAB.HabilitacaoError, match="Regime"):
        _abrir(con, regime="MEIO A MEIO")


def test_o_numero_e_por_exercicio(con):
    a, b = _abrir(con), _abrir(con)
    numeros = [con.execute("SELECT numero, ano FROM hc_habilitacoes WHERE id=?",
                           (x,)).fetchone() for x in (a, b)]
    assert [r["numero"] for r in numeros] == [1, 2]
    assert all(r["ano"] == 2026 for r in numeros)


# --------------------------------------------------------- documentos


def test_dispensar_exige_motivo_escrito(con):
    """Dispensar é decisão do oficial; ignorar não é."""
    h = _abrir(con)
    doc = HAB.o_que_falta(con, h)[0]
    with pytest.raises(HAB.HabilitacaoError, match="motivo"):
        HAB.dispensar_documento(con, doc["id"], motivo="não", agora=AGORA)
    HAB.dispensar_documento(con, doc["id"],
                            motivo="apresentou o original em cartório e o "
                                   "escrevente conferiu",
                            agora=AGORA, usuario="MARIO")
    assert doc["id"] not in {d["id"] for d in HAB.o_que_falta(con, h)}


def test_o_dispensado_sai_do_que_falta_e_o_motivo_fica(con):
    h = _abrir(con)
    doc = HAB.o_que_falta(con, h)[0]
    HAB.dispensar_documento(con, doc["id"], motivo="motivo suficiente aqui",
                            agora=AGORA)
    guardado = con.execute("SELECT * FROM hc_documentos WHERE id=?",
                           (doc["id"],)).fetchone()
    assert guardado["dispensado"] == 1
    assert guardado["dispensado_motivo"] == "motivo suficiente aqui"


# -------------------------------------------------------------- edital


def test_nao_se_publica_edital_com_documento_faltando(con):
    """Chamar o público antes de a casa conferir é pedir que ele confira."""
    h = _abrir(con)
    with pytest.raises(HAB.HabilitacaoError, match="Faltam"):
        _publicar(con, h)


def test_o_edital_abre_prazo_legal_do_edital(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    r = _publicar(con, h, hoje="2026-08-27")
    assert r["prazo_ate"] == "2026-09-01"       # 27/08 + HC.PRAZO_DO_EDITAL (5)
    linha = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?", (h,)).fetchone()
    assert linha["situacao"] == "EDITAL_PUBLICADO"
    assert linha["edital_hash"]


def test_o_teor_do_edital_nao_sai_em_branco(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    with pytest.raises(HAB.HabilitacaoError, match="branco"):
        HAB.publicar_edital(con, h, teor="curto", agora=AGORA)


# ------------------------------------------------------------ oposição


def test_a_oposicao_para_o_processo_e_exige_decisao(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.registrar_oposicao(con, h, quem="MARIA VIZINHA",
                           teor="já é casada em outra comarca", agora=AGORA)
    assert con.execute("SELECT situacao FROM hc_habilitacoes WHERE id=?",
                       (h,)).fetchone()["situacao"] == "COM_OPOSICAO"
    with pytest.raises(HAB.HabilitacaoError, match="impedimento oposto"):
        HAB.habilitar(con, h, agora=AGORA, hoje="2026-09-20")


def test_quem_opoe_tem_nome_e_o_teor_fica_inteiro(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    with pytest.raises(HAB.HabilitacaoError, match="quem"):
        HAB.registrar_oposicao(con, h, quem="", teor="alguma coisa aqui",
                               agora=AGORA)


def test_a_decisao_sobre_o_impedimento_exige_fundamento(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.registrar_oposicao(con, h, quem="MARIA", teor="já é casada", agora=AGORA)
    with pytest.raises(HAB.HabilitacaoError, match="fundamento"):
        HAB.decidir_oposicao(con, h, decisao="REJEITADA", fundamento="não",
                             agora=AGORA)


def test_impedimento_acolhido_arquiva_o_processo(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.registrar_oposicao(con, h, quem="MARIA", teor="já é casada", agora=AGORA)
    HAB.decidir_oposicao(con, h, decisao="ACOLHIDA",
                         fundamento="certidão de casamento anterior juntada aos autos",
                         agora=AGORA)
    linha = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?", (h,)).fetchone()
    assert linha["situacao"] == "ARQUIVADO"
    assert "impedimento acolhido" in linha["arquivado_motivo"]


def test_impedimento_rejeitado_devolve_o_processo_ao_ponto_em_que_estava(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.registrar_oposicao(con, h, quem="MARIA", teor="já é casada", agora=AGORA)
    HAB.decidir_oposicao(con, h, decisao="REJEITADA",
                         fundamento="a certidão apresentada é de homônima, "
                                    "com filiação diversa",
                         agora=AGORA)
    assert con.execute("SELECT situacao FROM hc_habilitacoes WHERE id=?",
                       (h,)).fetchone()["situacao"] == "EDITAL_PUBLICADO"


# ---------------------------------------------------------- habilitar


def test_nao_se_habilita_sem_edital(con):
    """Habilitar sem edital tira de terceiro o direito de opor impedimento."""
    h = _abrir(con)
    _entregar_tudo(con, h)
    with pytest.raises(HAB.HabilitacaoError, match="edital"):
        HAB.habilitar(con, h, agora=AGORA)


def test_habilita_com_edital_publicado_mesmo_no_prazo(con):
    """HOTFIX-2026-10-07-04: edital publicado basta; prazo é informativo."""
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h, hoje="2026-08-27")
    # Dentro do prazo (e no último dia) já pode habilitar.
    r = HAB.habilitar(con, h, agora=AGORA, hoje="2026-08-30", usuario="MARIO")
    assert r["numero"] == 1 and r["ano"] == 2026
    linha = con.execute("SELECT situacao FROM hc_habilitacoes WHERE id=?", (h,)).fetchone()
    assert linha["situacao"] == "HABILITADO"


def test_vencido_o_prazo_a_certidao_sai_e_vale_noventa_dias(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h, hoje="2026-08-27")
    r = HAB.habilitar(con, h, agora=AGORA, hoje="2026-09-02", usuario="MARIO")
    assert r["numero"] == 1 and r["ano"] == 2026
    assert r["vale_ate"] == "2026-12-01"        # 02/09 + 90
    linha = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?", (h,)).fetchone()
    assert linha["situacao"] == "HABILITADO"
    assert linha["certidao_hash"]


def test_nao_se_habilita_duas_vezes(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.habilitar(con, h, agora=AGORA, hoje="2026-09-12")
    with pytest.raises(HAB.HabilitacaoError, match="já foi expedida"):
        HAB.habilitar(con, h, agora=AGORA, hoje="2026-09-13")


# ---------------------------------------------------------- celebração


def _assento_de_casamento(con) -> int:
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               situacao, origem, criado_em)
           VALUES ('RC_B','CASAMENTO',40,'FULANO E BELTRANA','2026-09-20',
                   'ATIVO','MANUAL','2026-09-20T10:00:00')""")
    return int(cur.lastrowid)


def test_a_celebracao_amarra_o_assento_a_habilitacao(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.habilitar(con, h, agora=AGORA, hoje="2026-09-12")
    assento = _assento_de_casamento(con)
    HAB.registrar_celebracao(con, h, assento_id=assento, agora=AGORA,
                             hoje="2026-09-20")
    linha = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?", (h,)).fetchone()
    assert linha["situacao"] == "CELEBRADO"
    assert linha["casamento_assento_id"] == assento


def test_nao_se_celebra_com_habilitacao_vencida(con):
    """CC art. 1.532: passados noventa dias, o processo se refaz."""
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.habilitar(con, h, agora=AGORA, hoje="2026-09-12")
    assento = _assento_de_casamento(con)
    with pytest.raises(HAB.HabilitacaoError, match="venceu"):
        HAB.registrar_celebracao(con, h, assento_id=assento, agora=AGORA,
                                 hoje="2026-12-12")


def test_o_assento_tem_de_existir(con):
    """A lição do usucapião: sem conferir, batia na chave estrangeira."""
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.habilitar(con, h, agora=AGORA, hoje="2026-09-12")
    with pytest.raises(HAB.HabilitacaoError, match="não existe"):
        HAB.registrar_celebracao(con, h, assento_id=99999, agora=AGORA,
                                 hoje="2026-09-20")


def test_um_assento_nao_liga_a_duas_habilitacoes(con):
    h1 = _abrir(con)
    _entregar_tudo(con, h1)
    _publicar(con, h1)
    HAB.habilitar(con, h1, agora=AGORA, hoje="2026-09-12")
    h2 = _abrir(con, nubente1_nome="ALFA", nubente2_nome="BETA")
    _entregar_tudo(con, h2)
    _publicar(con, h2)
    HAB.habilitar(con, h2, agora=AGORA, hoje="2026-09-12")
    assento = _assento_de_casamento(con)
    HAB.registrar_celebracao(con, h1, assento_id=assento, agora=AGORA,
                             hoje="2026-09-20")
    with pytest.raises(HAB.HabilitacaoError, match="já está ligado"):
        HAB.registrar_celebracao(con, h2, assento_id=assento, agora=AGORA,
                                 hoje="2026-09-21")


def test_valores_para_lavrar_casamento_copia_nubentes(con):
    h = _abrir(con, nubente1_nome="MARIA", nubente2_nome="JOSE",
               nubente1_documento="111", regime="COMUNHAO_PARCIAL")
    linha = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?",
                        (h,)).fetchone()
    vals = HAB.valores_para_lavrar_casamento(linha)
    assert vals["nubente1_nome"] == "MARIA"
    assert vals["nubente2_nome"] == "JOSE"
    assert vals["regime_bens"] == "COMUNHAO_PARCIAL"
    assert vals["habilitacao_id"] == str(h)


def test_habilitacao_relacionada_le_dados_json(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.habilitar(con, h, agora=AGORA, hoje="2026-09-12")
    assento = _assento_de_casamento(con)
    con.execute(
        "UPDATE rc_assentos SET dados_json=? WHERE id=?",
        (json.dumps({"habilitacao_id": h}), assento))
    achou = HAB.habilitacao_relacionada_ao_assento(con, assento)
    assert achou and achou["id"] == h and achou["situacao"] == "HABILITADO"


def test_nao_se_arquiva_o_que_terminou_em_ato(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.habilitar(con, h, agora=AGORA, hoje="2026-09-12")
    HAB.registrar_celebracao(con, h, assento_id=_assento_de_casamento(con),
                             agora=AGORA, hoje="2026-09-20")
    with pytest.raises(HAB.HabilitacaoError, match="já foi celebrado"):
        HAB.arquivar(con, h, motivo="os nubentes desistiram", agora=AGORA)


# --------------------------------------------------- o que fazer agora


def test_os_proximos_passos_saem_do_estado(con):
    """«E agora?» é a pergunta que mais se repete num rito de semanas."""
    h = _abrir(con)
    assert "Receber" in HAB.proximos_passos(con, h)[0]
    _entregar_tudo(con, h)
    assert "Publicar o edital" in HAB.proximos_passos(con, h)[0]
    _publicar(con, h, hoje="2026-08-27")
    # O PRIMEIRO PASSO PASSA A SER A CENTRAL — o oficial informou em 28/08/2026
    # que o edital desta casa vai para o **e-Proclamas da CRC**, e não para a
    # parede nem para a imprensa. Quem esquecer de publicar só descobre quando
    # alguém perguntar, e por isso o lembrete vem à frente do «aguardar».
    # HOTFIX-2026-10-07-04: com o edital publicado a certidão já pode ser
    # expedida; o prazo de oposição virou linha informativa, e não espera.
    passos = HAB.proximos_passos(con, h, "2026-09-01")
    assert "e-Proclamas" in passos[0]
    assert any("Prazo de oposição em curso" in p for p in passos)
    HAB.registrar_publicacao(con, h, protocolo="CRC-2026-00123", agora=AGORA)
    passos = HAB.proximos_passos(con, h, "2026-09-01")
    assert "e-Proclamas" not in passos[0]
    assert "Expedir a certidão" in passos[0]
    assert any("Prazo de oposição em curso" in p for p in passos)
    assert "Expedir a certidão" in HAB.proximos_passos(con, h, "2026-09-12")[0]
    HAB.habilitar(con, h, agora=AGORA, hoje="2026-09-12")
    passos = HAB.proximos_passos(con, h, "2026-09-20")
    assert any("Registrar casamento" in p or "Lavrar" in p for p in passos)
    assert "venceu" in HAB.proximos_passos(con, h, "2026-12-20")[0]


def test_o_andamento_guarda_o_caminho_inteiro(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.habilitar(con, h, agora=AGORA, hoje="2026-09-12")
    passos = [x["o_que"] for x in HAB.andamento_de(con, h)]
    assert passos[0] == "Processo aberto"
    assert "Edital de proclamas publicado" in passos
    assert passos[-1] == "Habilitação expedida"


# ------------------------------------------------------- o que NÃO há


def test_o_modulo_nao_julga_impedimento():
    """Se o impedimento procede é matéria de direito, e a decisão é do oficial.

    A mesma regra do usucapião e da lista de fraudes: o módulo registra o que
    foi decidido, com fundamento, e nunca decide por ele.
    """
    proibidos = ("julgar", "decidir_impedimento", "procede", "avaliar_oposicao",
                 "impedimento_procede")
    publicos = {n for n in dir(HAB) if not n.startswith("_")}
    assert not (publicos & set(proibidos))


def test_a_busca_acha_por_qualquer_um_dos_nubentes(con):
    _abrir(con, nubente1_nome="JOSÉ DA SILVA", nubente2_nome="MARIA SOUZA")
    assert len(HAB.listar(con, busca="jose")) == 1
    assert len(HAB.listar(con, busca="souza")) == 1
    assert len(HAB.listar(con, busca="ninguém")) == 0


# ---------------------------------------------------------------------------
# O EDITAL DESTA CASA VAI PARA O e-PROCLAMAS DA CRC
#
# Informação do oficial em 28/08/2026, quando perguntei se ele era publicado na
# imprensa ou só afixado na serventia. **Não é nem um nem outro**: é publicação
# digital na Central de Informações do Registro Civil.
#
# Isso mudou duas coisas. O item `14.1.10` da tabela — publicação na imprensa —
# não entra nesta casa. E o processo passou a guardar o **protocolo que a
# Central devolve**: edital afixado se prova com o papel na parede; edital
# publicado na Central se prova com o número dela.


def test_a_publicacao_na_central_guarda_o_protocolo(con):
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.registrar_publicacao(con, h, protocolo="CRC-2026-00123", agora=AGORA,
                             usuario="MARIO")
    linha = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?", (h,)).fetchone()
    assert linha["eproclamas_protocolo"] == "CRC-2026-00123"
    assert linha["eproclamas_em"] == AGORA[:10]
    assert "Publicado no e-Proclamas" in [
        x["o_que"] for x in HAB.andamento_de(con, h)]


def test_sem_protocolo_nao_se_registra_a_publicacao(con):
    """É o número que prova que a publicação aconteceu."""
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    with pytest.raises(HAB.HabilitacaoError, match="protocolo"):
        HAB.registrar_publicacao(con, h, protocolo="  ", agora=AGORA)


def test_nao_se_publica_na_central_antes_de_publicar_aqui(con):
    """É deste edital que sai o teor que vai para a Central."""
    h = _abrir(con)
    _entregar_tudo(con, h)
    with pytest.raises(HAB.HabilitacaoError, match="edital aqui primeiro"):
        HAB.registrar_publicacao(con, h, protocolo="CRC-1", agora=AGORA)


def test_onde_se_publica_esta_escrito_no_modulo():
    """Para quem ler daqui a cinco anos: não é a parede, e não é a imprensa."""
    assert HC.ONDE_SE_PUBLICA == "e-Proclamas (CRC)"


# ------------------------------------------------ UM SELO SÓ, e ele é o da habilitação
#
# Decisão do oficial em 28/08/2026:
#
#     «O selo é emitido uma vez apenas. Ele é reaproveitado apenas no assento,
#      mas já foi emitido na habilitação.»
#
# E a tabela de custas do TJMA concorda, com todas as letras: o item `14.1.1` é
# um só, e cobre «Habilitação **e registro**, lavratura de assento de casamento
# (...) compreendendo todas as despesas».


def _registro_do_assento(con, assento_id: int) -> int:
    cur = con.execute(
        """INSERT INTO rc_atos (assento_id, tipo, data_ato, criado_em)
           VALUES (?, 'REGISTRO', '2026-09-20', '2026-09-20T10:00:00')""",
        (assento_id,))
    return int(cur.lastrowid)


def _ate_celebrar(con) -> tuple[int, int, int]:
    h = _abrir(con)
    _entregar_tudo(con, h)
    _publicar(con, h)
    HAB.habilitar(con, h, agora=AGORA, hoje="2026-09-12")
    assento = _assento_de_casamento(con)
    ato = _registro_do_assento(con, assento)
    return h, assento, ato


def test_a_celebracao_leva_o_selo_da_habilitacao_para_o_assento(con):
    """O assento não compra selo: recebe o que a habilitação já comprou."""
    h, assento, ato = _ate_celebrar(con)
    con.execute("UPDATE hc_habilitacoes SET selo=? WHERE id=?",
                ("HAB0000000000000000000000AAAA", h))
    HAB.registrar_celebracao(con, h, assento_id=assento, agora=AGORA,
                             hoje="2026-09-20")
    assert con.execute("SELECT selo FROM rc_atos WHERE id=?",
                       (ato,)).fetchone()["selo"] == (
        "HAB0000000000000000000000AAAA")


def test_o_assento_sai_da_lista_de_atos_sem_selo(con):
    """Sem isto ele ficaria lá para sempre — e alguém compraria um segundo
    selo só para tirá-lo de lá, que é exatamente o gasto que se quer evitar."""
    import ato_selado as AS
    h, assento, ato = _ate_celebrar(con)
    con.execute("UPDATE hc_habilitacoes SET selo='SELO123' WHERE id=?", (h,))
    assert ato in [linha["id"] for linha in AS.atos_sem_selo(con, "rc_atos")]
    HAB.registrar_celebracao(con, h, assento_id=assento, agora=AGORA,
                             hoje="2026-09-20")
    assert ato not in [linha["id"] for linha in AS.atos_sem_selo(con, "rc_atos")]


def test_selo_digitado_a_mao_no_assento_nao_e_sobrescrito(con):
    """O que está no papel assinado manda sobre o que o sistema deduz."""
    h, assento, ato = _ate_celebrar(con)
    con.execute("UPDATE rc_atos SET selo='ODOPAPEL' WHERE id=?", (ato,))
    con.execute("UPDATE hc_habilitacoes SET selo='ODOSISTEMA' WHERE id=?", (h,))
    HAB.registrar_celebracao(con, h, assento_id=assento, agora=AGORA,
                             hoje="2026-09-20")
    assert con.execute("SELECT selo FROM rc_atos WHERE id=?",
                       (ato,)).fetchone()["selo"] == "ODOPAPEL"


def test_habilitacao_sem_selo_nao_inventa_um_para_o_assento(con):
    """O aparelho pode ter estado fora do ar. Ato sem selo é melhor que ato
    com selo inventado — é a regra da casa, e vale aqui também."""
    h, assento, ato = _ate_celebrar(con)
    HAB.registrar_celebracao(con, h, assento_id=assento, agora=AGORA,
                             hoje="2026-09-20")
    assert not (con.execute("SELECT COALESCE(selo,'') s FROM rc_atos WHERE id=?",
                            (ato,)).fetchone()["s"])


def test_o_selo_que_chega_depois_tambem_alcanca_o_assento(con):
    """A ordem incomum: casamento celebrado antes de a habilitação ter selo.

    É por isso que espelhar é uma função, e não duas linhas dentro de
    `registrar_celebracao` — chamada nos dois momentos, ela acerta as duas
    ordens.
    """
    h, assento, ato = _ate_celebrar(con)
    HAB.registrar_celebracao(con, h, assento_id=assento, agora=AGORA,
                             hoje="2026-09-20")
    con.execute("UPDATE hc_habilitacoes SET selo='CHEGOUDEPOIS' WHERE id=?", (h,))
    assert HAB.espelhar_o_selo_no_assento(con, h) == "CHEGOUDEPOIS"
    assert con.execute("SELECT selo FROM rc_atos WHERE id=?",
                       (ato,)).fetchone()["selo"] == "CHEGOUDEPOIS"


def test_espelhar_duas_vezes_nao_faz_mal(con):
    """Ela roda em dois pontos, e pode rodar nos dois no mesmo processo."""
    h, assento, ato = _ate_celebrar(con)
    con.execute("UPDATE hc_habilitacoes SET selo='UMSO' WHERE id=?", (h,))
    HAB.registrar_celebracao(con, h, assento_id=assento, agora=AGORA,
                             hoje="2026-09-20")
    assert HAB.espelhar_o_selo_no_assento(con, h) is None
    assert con.execute("SELECT selo FROM rc_atos WHERE id=?",
                       (ato,)).fetchone()["selo"] == "UMSO"
