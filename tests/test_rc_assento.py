"""
Testes do RCPN — o assento e a divisao tripartite que a inspecao cobra.

O QUE ELES CONFEREM
    A regra, e nao "a funcao devolveu alguma coisa":

      - a ESPECIE manda na serie: nascimento no Livro A, obito no C. O
        balcao nao escolhe o livro, senao lanca obito em livro de
        nascimento;
      - averbacao, anotacao e retificacao NAO ocupam folha nova — elas se
        lancam no espaco do proprio assento, como no livro fisico. Se
        ocupassem, o Livro A encheria em um ano;
      - a retificacao exige fundamento e as outras duas nao — retificar sem
        dizer com base em que e o que faz o livro nao explicar a mudanca;
      - `blocos_do` separa os tres blocos, que e o que a ficha precisa para
        imprimir campos proprios de nota, averbacao e retificacao;
      - carga repetivel: a mesma (origem, origem_chave) nao duplica.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_assento as RC                          # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from rc_schema import init_rc_schema             # noqa: E402

AGORA = "2026-08-24T09:00:00"
EXTENSO = "vinte e quatro dias do mês de agosto do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rc_schema(con)
    return con


def extras_legais(especie: str, nome="ALGUÉM") -> dict:
    """O mínimo da Lei 6.015/1973 para a lavratura MANUAL do balcão."""
    especie = (especie or "").upper()
    if especie in {"NASCIMENTO", "NATIMORTO"}:
        extra = {
            "data_fato": "2026-08-20",
            "dados": {"sexo": "M"},
            "termo_dados": {"local_fato_nome": "Hospital Municipal"},
            "pessoas": [
                {"papel": "REGISTRADO", "nome": nome, "sexo": "M"},
                {"papel": "MAE", "nome": "MARIA DA SILVA"},
                {"papel": "PAI", "nome": "IGNORADO"},
                {"papel": "DECLARANTE", "nome": "MARIA DA SILVA"},
            ],
        }
        if especie == "NATIMORTO":
            extra["ibge"] = {"numero_do": "12345"}
        else:
            # «Onde nasceu» — o SIRC recusa o nascimento sem ele, e desde o
            # relato #130 (14/10/2026) a lavratura também.
            extra["ibge"] = {"local_nascimento": 1}
            # PAI IGNORADO EXIGE O TERMO (23/10/2026) — o negativo basta aqui.
            extra["paternidade"] = {"tipo": "NEGATIVO"}
        return extra
    if especie in RC.ESPECIES_DE_CASAMENTO:
        return {
            "data_fato": "2026-08-20",
            "regime_bens": "COMUNHAO_PARCIAL",
            "pessoas": [
                {"papel": "NUBENTE1", "nome": "JOAO"},
                {"papel": "NUBENTE2", "nome": "MARIA"},
                {"papel": "MAE_NUBENTE1", "nome": "ANA"},
                {"papel": "PAI_NUBENTE1", "nome": "IGNORADO"},
                {"papel": "MAE_NUBENTE2", "nome": "RITA"},
                {"papel": "PAI_NUBENTE2", "nome": "IGNORADO"},
                {"papel": "TESTEMUNHA", "nome": "CICLANO"},
            ],
        }
    if especie == "OBITO":
        return {
            "data_fato": "2026-08-01",
            "termo_dados": {"local_fato_nome": "Hospital Municipal"},
            "ibge": {"numero_do": "98765"},
            # «Deixou bens» — a CRC recusa o óbito sem S ou N, e desde o
            # relato #130 (14/10/2026) a lavratura também.
            "marcas_do_obito": {"obito_possui_bens": "NAO"},
            "pessoas": [
                {"papel": "FALECIDO", "nome": nome},
                {"papel": "MAE", "nome": "IGNORADO"},
                {"papel": "PAI", "nome": "IGNORADO"},
                {"papel": "DECLARANTE", "nome": "FULANO"},
            ],
        }
    return {}


def nascimento(con, nome="JOÃO DA SILVA", **kw):
    if kw.get("origem", "MANUAL") == "MANUAL":
        kw.setdefault("data_fato", "2026-08-20")
        td = dict(kw.get("termo_dados") or {})
        td.setdefault("local_fato_nome", "Hospital Municipal de Cidade Exemplo")
        kw["termo_dados"] = td
        dados = dict(kw.get("dados") or {})
        dados.setdefault("sexo", "M")
        kw["dados"] = dados
        ibge = dict(kw.get("ibge") or {})
        ibge.setdefault("local_nascimento", 1)       # relato #130: o SIRC exige
        kw["ibge"] = ibge
        if "pessoas" not in kw:
            kw["pessoas"] = [
                {"papel": "REGISTRADO", "nome": nome, "sexo": dados["sexo"]},
                {"papel": "MAE", "nome": "MARIA DA SILVA"},
                {"papel": "PAI", "nome": "IGNORADO"},
                {"papel": "DECLARANTE", "nome": "MARIA DA SILVA"},
            ]
        # PAI IGNORADO EXIGE O TERMO (23/10/2026): quem não diz qual, leva o
        # negativo. Quem quer ver a recusa passa `paternidade=None`.
        if "paternidade" not in kw:
            import rc_paternidade as RP
            if RP.exige_termo("NASCIMENTO", kw["pessoas"], "MANUAL"):
                kw["paternidade"] = {"tipo": "NEGATIVO"}
    return RC.lavrar_assento(con, especie="NASCIMENTO", nome=nome, sv=SV,
                             agora=AGORA, data_extenso=EXTENSO, **kw)


# ------------------------------------------------------------- o assento


def test_lavra_assento_de_nascimento_no_livro_a():
    con = banco()
    r = nascimento(con, data_fato="2026-08-20", dados={"sexo": "M"})
    assert r["serie"] == "RC_A"
    assert r["numero_ordem"] == 1
    ass = RC.assento(con, r["assento_id"])
    assert ass["especie"] == "NASCIMENTO"
    assert ass["nome"] == "JOÃO DA SILVA"
    assert ass["situacao"] == "ATIVO"
    assert json.loads(ass["dados_json"]) == {"sexo": "M"}


@pytest.mark.parametrize("especie,serie", [
    ("NASCIMENTO", "RC_A"),
    ("CASAMENTO", "RC_B"),
    ("CASAMENTO_RELIGIOSO", "RC_B_AUXILIAR"),
    ("OBITO", "RC_C"),
    ("NATIMORTO", "RC_C_AUXILIAR"),
    ("PROCLAMAS", "RC_D"),
    ("OUTRO", "RC_E"),
])
def test_a_especie_manda_na_serie(especie, serie):
    # O balcao nao escolhe o livro: escolher e o que faz lancar obito em
    # livro de nascimento.
    con = banco()
    r = RC.lavrar_assento(con, especie=especie, nome="ALGUÉM", sv=SV,
                          agora=AGORA, data_extenso=EXTENSO,
                          **extras_legais(especie, "ALGUÉM"))
    assert r["serie"] == serie


def test_especie_desconhecida_e_recusada():
    con = banco()
    with pytest.raises(RC.RcError, match="Espécie de assento desconhecida"):
        RC.lavrar_assento(con, especie="DIVORCIO", nome="ALGUÉM", sv=SV,
                          agora=AGORA, data_extenso=EXTENSO)


def test_assento_sem_nome_e_recusado():
    con = banco()
    with pytest.raises(RC.RcError, match="nome de quem é o registro"):
        RC.lavrar_assento(con, especie="NASCIMENTO", nome="   ", sv=SV,
                          agora=AGORA, data_extenso=EXTENSO)


def test_cada_assento_ocupa_folha_propria():
    # `tbPropriedadeRCPN` mede 1 registro por folha em todos os livros.
    con = banco()
    assert nascimento(con, "PRIMEIRO")["folha"] == 1
    assert nascimento(con, "SEGUNDO")["folha"] == 2


def test_carga_e_repetivel_por_construcao():
    con = banco()
    a = nascimento(con, origem="EOFICIO", origem_chave="ACERVO:19552")
    b = nascimento(con, origem="EOFICIO", origem_chave="ACERVO:19552")
    assert a["assento_id"] == b["assento_id"]
    assert b["reaproveitado"] is True
    assert con.execute("SELECT COUNT(*) n FROM rc_assentos").fetchone()["n"] == 1


def test_assento_de_eoficio_sem_chave_e_recusado():
    con = banco()
    with pytest.raises(RC.RcError, match="chave de origem"):
        nascimento(con, origem="EOFICIO")


def test_a_matricula_de_32_digitos_e_guardada_como_recebida():
    # A digitada nao e recomposta — ver rc_schema.py.
    #
    # ERA "2" * 32 ATE 14/10/2026, e deixou de poder ser: desde o relato #130
    # a lavratura do balcao confere o que a CRC confere (`crc_carga.
    # o_que_falta`), e a CRC retem matricula com digito verificador errado.
    # O que o teste guarda continua o mesmo: uma matricula VALIDA, diferente
    # da que a lavratura comporia, fica como veio.
    import rc_matricula as MATR
    con = banco()
    m = MATR.compor(cns="000000", ano="2026", livro_tipo="1", livro=7,
                    folha=91, termo=4321)
    r = nascimento(con, matricula=m)
    assert RC.assento(con, r["assento_id"])["matricula"] == m


def test_matricula_digitada_com_digito_errado_e_recusada_na_lavratura():
    """Relato #130: a CRC retém matrícula com o dígito errado, e o balcão agora
    sabe disso antes de lavrar — e não na carga, com o assento no livro."""
    import rc_centrais_na_lavratura as CENT
    con = banco()
    with pytest.raises(CENT.FaltaParaAsCentraisError, match="dígito verificador"):
        nascimento(con, matricula="2" * 32)


# --------------------------------------------------- a divisao tripartite


@pytest.mark.parametrize("funcao,tipo", [
    (RC.averbar, "AVERBACAO"),
    (RC.anotar, "ANOTACAO"),
])
def test_averbacao_e_anotacao_nao_ocupam_folha_nova(funcao, tipo):
    # Elas se lancam no espaco do proprio assento, como no livro fisico. Se
    # ocupassem folha nova, o Livro A encheria em um ano.
    con = banco()
    r = nascimento(con)
    resultado = funcao(con, r["assento_id"],
                       teor="Reconhecimento de paternidade por escritura.",
                       agora=AGORA)
    assert resultado["tipo"] == tipo
    ato = next(a for a in RC.atos_do(con, r["assento_id"]) if a["tipo"] == tipo)
    assert ato["livro_id"] is None
    assert ato["numero_ordem"] is None
    # e o proximo assento continua na folha 2, e nao na 3
    assert nascimento(con, "SEGUNDO")["folha"] == 2


def test_retificacao_exige_fundamento():
    # Retificar sem dizer com base em que e o que faz o livro nao explicar a
    # mudanca.
    con = banco()
    r = nascimento(con)
    with pytest.raises(RC.RcError, match="exige o fundamento"):
        RC.retificar(con, r["assento_id"], teor="Corrige o nome da genitora.",
                     fundamento="  ", agora=AGORA)


def test_retificacao_com_fundamento_entra():
    con = banco()
    r = nascimento(con)
    RC.retificar(con, r["assento_id"], teor="Corrige o nome da genitora.",
                 fundamento="Processo 123, sentença de 20/08/2026.",
                 agora=AGORA)
    ato = next(a for a in RC.atos_do(con, r["assento_id"])
               if a["tipo"] == "RETIFICACAO")
    assert ato["fundamento"] == "Processo 123, sentença de 20/08/2026."


def test_averbacao_e_anotacao_nao_exigem_fundamento():
    con = banco()
    r = nascimento(con)
    RC.averbar(con, r["assento_id"], teor="Averbação de casamento.", agora=AGORA)
    RC.anotar(con, r["assento_id"], teor="Anotação remissiva ao Livro B.",
              agora=AGORA)
    assert len(RC.atos_do(con, r["assento_id"])) == 3


def test_teor_curto_e_recusado():
    con = banco()
    r = nascimento(con)
    with pytest.raises(RC.RcError, match="dez letras"):
        RC.averbar(con, r["assento_id"], teor="ok", agora=AGORA)


def test_blocos_do_separa_os_tres_campos_da_ficha():
    # E o que a inspecao pede que apareca em campos proprios.
    con = banco()
    r = nascimento(con)
    RC.averbar(con, r["assento_id"], teor="Averbação de casamento.", agora=AGORA)
    RC.averbar(con, r["assento_id"], teor="Averbação de óbito.", agora=AGORA)
    RC.anotar(con, r["assento_id"], teor="Anotação remissiva.", agora=AGORA)
    RC.retificar(con, r["assento_id"], teor="Corrige grafia do nome.",
                 fundamento="Pedido do interessado, art. 110.", agora=AGORA)

    blocos = RC.blocos_do(con, r["assento_id"])
    assert len(blocos["REGISTRO"]) == 1
    assert len(blocos["AVERBACAO"]) == 2
    assert len(blocos["ANOTACAO"]) == 1
    assert len(blocos["RETIFICACAO"]) == 1


def test_nao_lanca_em_assento_inexistente():
    con = banco()
    with pytest.raises(RC.RcError, match="não encontrado"):
        RC.averbar(con, 999, teor="Averbação qualquer.", agora=AGORA)


# ============ O LIVRO E SE PARTIU EM SEIS (27/08/2026)
#
# A razao veio de fora: o contrato do selador tem uma familia inteira de
# caminhos para CADA uma das seis coisas que o Livro E registra. Enquanto as
# seis se chamavam «OUTRO», o sistema nao tinha como pedir selo para nenhuma —
# `OUTRO` nao diz qual.


def test_as_seis_do_livro_E_tem_nome_proprio():
    """A Lei 6.015/1973, art. 33, V, manda o Livro E registrar coisas
    juridicamente distintas. Chama-las pelo mesmo nome era o sistema sabendo
    menos que o livro de papel."""
    for especie in ("AUSENCIA", "INTERDICAO", "TUTELA", "EMANCIPACAO",
                    "UNIAO_ESTAVEL", "OPCAO_NACIONALIDADE"):
        assert RC.SERIE_DA_ESPECIE[especie] == "RC_E", especie


def test_OUTRO_continua_existindo():
    """Ele recebe o que nao e nenhuma das seis — e impede que um assento ja
    lavrado como «OUTRO» perca o nome."""
    assert RC.SERIE_DA_ESPECIE["OUTRO"] == "RC_E"


def test_toda_especie_tem_nome_de_gente():
    """Sem isto o balcao leria `OPCAO_NACIONALIDADE` num menu suspenso."""
    assert set(RC.NOME_DA_ESPECIE) == set(RC.SERIE_DA_ESPECIE)
    assert "Livro E" in RC.NOME_DA_ESPECIE["TUTELA"]
    assert RC.NOME_DA_ESPECIE["PROCLAMAS"].startswith("Proclamas")


def test_o_livro_de_cada_especie_nao_muda_por_engano():
    """A especie manda na serie, e a serie manda no livro. Trocar uma linha
    destas em silencio poria óbito em livro de nascimento."""
    assert RC.SERIE_DA_ESPECIE["NASCIMENTO"] == "RC_A"
    assert RC.SERIE_DA_ESPECIE["CASAMENTO"] == "RC_B"
    assert RC.SERIE_DA_ESPECIE["CASAMENTO_RELIGIOSO"] == "RC_B_AUXILIAR"
    assert RC.SERIE_DA_ESPECIE["OBITO"] == "RC_C"
    assert RC.SERIE_DA_ESPECIE["NATIMORTO"] == "RC_C_AUXILIAR"
    assert RC.SERIE_DA_ESPECIE["PROCLAMAS"] == "RC_D"


# ------------------------------------------ a matricula de 32 digitos
#
# MUDOU EM 30/08/2026. Ate esse dia o sistema nao compunha a matricula, e o
# motivo estava escrito na rota: «o algoritmo oficial nao foi medido, e numero
# de matricula inventado e pior que campo em branco». O motivo era bom e deixou
# de valer — a regra saiu do Anexo IV do manual de carga da CRC.


def test_lavrar_compoe_a_matricula():
    """**E o teste que prova a entrega.** Sem ele, `compor` seria funcao pronta
    que ninguem chama — o defeito que mais se repetiu neste projeto."""
    import rc_matricula as MATR
    con = banco()
    r = nascimento(con)
    assert r["matricula"], "lavrou sem compor a matricula"
    assert len(r["matricula"]) == 32
    assert MATR.confere(r["matricula"])["ok"], "compos uma matricula que nao fecha"
    gravada = con.execute("SELECT matricula FROM rc_assentos WHERE id=?",
                          (r["assento_id"],)).fetchone()[0]
    assert gravada == r["matricula"], "devolveu uma e gravou outra"
    con.close()


def test_a_matricula_carrega_o_livro_a_folha_e_o_termo_do_proprio_assento():
    """Ela nao e um numero qualquer de 32 digitos: **contem** os dados do
    assento. Se estes tres deixarem de bater, a matricula aponta para outro
    registro e ninguem percebe — os 32 digitos continuam la."""
    import rc_matricula as MATR
    con = banco()
    r = nascimento(con)
    p = MATR.partes(r["matricula"])
    assert p["cns"] == "000000"
    assert p["ano"] == "2026", "o ano e o do REGISTRO"
    assert p["livro_tipo"] == "1", "nascimento e Livro A"
    assert int(p["termo"]) == int(r["numero_ordem"])
    assert int(p["folha"]) == int(r["folha"])
    con.close()


def test_a_especie_manda_no_tipo_de_livro_da_matricula():
    """Obito e Livro C (digito 4). Sair como 1 poria o obito no livro de
    nascimentos dentro do numero nacional do ato."""
    import rc_matricula as MATR
    con = banco()
    r = RC.lavrar_assento(con, especie="OBITO", nome="FULANO DE TAL", sv=SV,
                          agora=AGORA, data_extenso=EXTENSO,
                          **extras_legais("OBITO", "FULANO DE TAL"))
    assert MATR.partes(r["matricula"])["livro_tipo"] == "4"
    con.close()


def test_a_matricula_digitada_manda_e_nao_e_sobrescrita():
    """Assento antigo sendo cadastrado, ou registro transportado: o numero
    nacional ja existe e e **unico e imutavel**. Sobrescreve-lo trocaria a
    identidade de um assento que ja pode ter saido em certidao."""
    # ERA UMA MATRICULA DE 1955 COM O DIGITO ERRADO ATE 14/10/2026 ("…53",
    # e o certo e 94). Desde o relato #130 a lavratura do balcao confere o
    # que a CRC confere — digito e ano igual ao do registro —, e o assento
    # antigo se cadastra por «Digitar acervo» (origem ACERVO), que nao passa
    # por essa recusa. A propriedade guardada e a mesma: a digitada manda.
    import rc_matricula as MATR
    veio = MATR.compor(cns="000000", ano="2026", livro_tipo="1", livro=1,
                       folha=70, termo=283)
    con = banco()
    r = nascimento(con, matricula=veio)
    assert r["matricula"] == veio
    gravada = con.execute("SELECT matricula FROM rc_assentos WHERE id=?",
                          (r["assento_id"],)).fetchone()[0]
    assert gravada == veio
    con.close()


def test_duas_matriculas_seguidas_sao_diferentes():
    """Cada assento tem a sua: o termo entra no numero. Se sairem iguais, a
    composicao nao esta lendo o numero de ordem."""
    con = banco()
    a = nascimento(con, nome="PRIMEIRO")["matricula"]
    b = nascimento(con, nome="SEGUNDO")["matricula"]
    assert a and b and a != b
    con.close()


# --------------------------------- o que o TERMO pede (e ninguem preenchia)
#
# MEDIDO EM 30/08/2026: as colunas `cor_raca`, `hora_fato`, `local_fato_nome`,
# `local_fato_endereco` e `naturalidade_declarada` nasceram em 29/08 para o
# termo e as remessas — e nada as preenchia. O formulario nao perguntava
# nenhuma, e `lavrar_assento` nao lia nenhuma. **Coluna que nada preenche e
# coluna que mente**: a remessa acusa «falta o dado» e ninguem sabe onde
# informa-lo.


def test_lavrar_grava_o_que_o_termo_pede():
    con = banco()
    r = nascimento(con, termo_dados={
        "cor_raca": "PARDA", "hora_fato": "18:04",
        "local_fato_nome": "MATERNIDADE DE ALTO RISCO",
        "local_fato_endereco": "RUA CORIOLANO MILHOMEM, 42",
        "naturalidade_declarada": "Cidade Exemplo"})
    a = dict(con.execute("SELECT * FROM rc_assentos WHERE id=?",
                         (r["assento_id"],)).fetchone())
    assert a["cor_raca"] == "PARDA"
    assert a["hora_fato"] == "18:04"
    assert a["local_fato_nome"].startswith("MATERNIDADE")
    assert a["naturalidade_declarada"] == "Cidade Exemplo"
    con.close()


def test_a_cor_e_lista_fechada_porque_a_CRC_recusa_a_carga_inteira():
    """A Central aceita seis palavras. Uma setima volta como recusa do lote,
    meses depois, sem dizer qual linha. **Recusar aqui custa uma pergunta;
    recusar la custa um trimestre.**"""
    con = banco()
    with pytest.raises(RC.RcError) as e:
        nascimento(con, termo_dados={"cor_raca": "MORENA"})
    assert "Branca" in str(e.value), "a recusa tem de dizer quais valem"
    con.close()


def test_a_cor_aceita_sem_caixa_e_grava_padronizada():
    con = banco()
    r = nascimento(con, termo_dados={"cor_raca": "indigena"})
    a = dict(con.execute("SELECT cor_raca FROM rc_assentos WHERE id=?",
                         (r["assento_id"],)).fetchone())
    assert a["cor_raca"] == "INDIGENA"
    con.close()


def test_campo_que_nao_cabe_na_especie_recusa():
    """Cor ou raca nao entra em casamento: o assento e de duas pessoas, e a
    pergunta nao teria a quem se referir."""
    con = banco()
    with pytest.raises(RC.RcError) as e:
        RC.lavrar_assento(con, especie="CASAMENTO", nome="A E B", sv=SV,
                          agora=AGORA, data_extenso=EXTENSO,
                          **{**extras_legais("CASAMENTO"),
                             "termo_dados": {"cor_raca": "PARDA"}})
    assert "cor_raca" in str(e.value)
    con.close()


def test_o_que_nao_se_informa_fica_nulo():
    """Preencher «ignorada» por conta propria seria afirmar que se perguntou —
    e «ignorada» e uma resposta legitima que alguem pode ter dado."""
    con = banco()
    r = nascimento(con)
    a = dict(con.execute("SELECT * FROM rc_assentos WHERE id=?",
                         (r["assento_id"],)).fetchone())
    for c in ("cor_raca", "hora_fato", "naturalidade_declarada"):
        assert a[c] in (None, ""), f"{c} veio preenchido sozinho"
    con.close()


def test_anotar_do_termo_completa_depois():
    """Assento tardio, obito de pessoa achada: nem sempre se sabe na hora."""
    con = banco()
    r = nascimento(con)
    RC.anotar_do_termo(con, r["assento_id"], cor_raca="BRANCA")
    a = dict(con.execute("SELECT cor_raca FROM rc_assentos WHERE id=?",
                         (r["assento_id"],)).fetchone())
    assert a["cor_raca"] == "BRANCA"
    con.close()


def test_as_cores_sao_as_mesmas_da_CRC():
    """Duas listas divergem no primeiro conserto, e a carga inteira volta."""
    import crc_carga
    assert set(RC.CORES_E_RACAS) <= set(crc_carga.COR_PELE)


def test_todo_campo_da_pessoa_tem_lugar_no_formulario():
    """**A LISTA E A TELA TEM DE BATER.** `_pessoas_do_formulario` le
    exatamente `CAMPOS_DA_PESSOA`; campo que esta na lista e nao na macro e
    campo que nunca chega, e campo na macro fora da lista e pergunta que se
    perde no caminho.

    Medido em 30/08/2026: faltavam `documento_tipo`, `naturalidade_pais` e
    `cep` na macro, e `documento_orgao` e `idade_no_fato` na lista — cinco
    colunas do banco que nada preenchia.
    """
    import re
    macro = (Path(__file__).resolve().parent.parent / "templates"
             / "_pessoa_do_assento.html").read_text(encoding="utf-8")
    na_tela = set(re.findall(r'name="\{\{ *prefixo *\}\}_([a-z_0-9]+)"', macro))
    faltam = [c for c in RC.CAMPOS_DA_PESSOA if c not in na_tela]
    assert not faltam, f"a macro não pergunta: {faltam}"
    sobram = [c for c in na_tela if c not in RC.CAMPOS_DA_PESSOA]
    assert not sobram, f"a macro pergunta o que ninguém lê: {sobram}"


def test_a_pessoa_grava_os_campos_novos():
    con = banco()
    extra = extras_legais("OBITO", "NARIO DA SILVA")
    extra["pessoas"] = [
        {"papel": "FALECIDO", "nome": "NARIO DA SILVA",
         "documento_tipo": "RG", "documento_numero": "123456",
         "documento_orgao": "SSP/MA", "idade_no_fato": "69",
         "cep": "65936-000", "naturalidade_pais": "Brasil"},
        {"papel": "MAE", "nome": "IGNORADO"},
        {"papel": "PAI", "nome": "IGNORADO"},
        {"papel": "DECLARANTE", "nome": "FULANO"},
    ]
    r = RC.lavrar_assento(
        con, especie="OBITO", nome="NARIO DA SILVA", sv=SV, agora=AGORA,
        data_extenso=EXTENSO, **extra)
    p = dict(con.execute(
        "SELECT * FROM rc_pessoas WHERE assento_id=? AND papel=?",
        (r["assento_id"], "FALECIDO")).fetchone())
    assert p["documento_tipo"] == "RG"
    assert p["documento_orgao"] == "SSP/MA"
    assert str(p["idade_no_fato"]) == "69"
    assert p["cep"] == "65936-000"
    con.close()


# ------------------------------------------------ a filiacao
#
# ELA FALTAVA INTEIRA ATE 30/08/2026. Medido na producao: a carga do acervo
# gravou 235 PAI, 218 MAE e 631 avos — e `PAPEIS_DA_ESPECIE`, que governa a
# lavratura NOVA, so permitia o registrado. **O acervo tinha filiacao e o ato
# novo nao conseguia ter.**


def test_o_nascimento_aceita_filiacao_e_avos():
    """Sem filiacao nao ha certidao de nascimento: e o que ela diz logo depois
    do nome, e o termo desta casa escreve «filho de ...»."""
    con = banco()
    r = nascimento(con, pessoas=[
        # o sexo do registrado: a CRC exige (relato #130, 14/10/2026)
        {"papel": "REGISTRADO", "nome": "PAULO HENRIQUE", "sexo": "M"},
        {"papel": "PAI", "nome": "BALTAZAR SOARES DA SILVA", "sexo": "M"},
        {"papel": "MAE", "nome": "ADA BARROS ALMEIDA", "sexo": "F"},
        {"papel": "AVO_PATERNO", "nome": "JOSE SOARES"},
        {"papel": "AVO_MATERNA", "nome": "MARIA AMARAL BARROS DA SILVA"},
        {"papel": "DECLARANTE", "nome": "JOAO BATISTA ALMEIDA SILVA"},
        {"papel": "TESTEMUNHA", "nome": "FULANO TESTEMUNHA"},
    ])
    papeis = [x[0] for x in con.execute(
        "SELECT papel FROM rc_pessoas WHERE assento_id=? ORDER BY ordem",
        (r["assento_id"],))]
    # A FILIACAO 1 E A MAE, e por isso ela vem primeiro — decisao do oficial
    # em 30/08/2026. E o contrario do E-Oficio, onde a 1 e o pai.
    assert papeis == ["REGISTRADO", "MAE", "PAI", "AVO_MATERNA",
                      "AVO_PATERNO", "DECLARANTE", "TESTEMUNHA"]
    con.close()


def test_a_ordem_e_a_do_termo_e_nao_a_alfabetica():
    """Primeiro de quem e o assento, depois a filiacao, os avos, e por fim
    quem declarou e testemunhou — como o texto do livro os apresenta."""
    assert RC.ORDEM_DO_PAPEL["REGISTRADO"] < RC.ORDEM_DO_PAPEL["MAE"]
    assert RC.ORDEM_DO_PAPEL["MAE"] < RC.ORDEM_DO_PAPEL["PAI"], (
        "a filiacao 1 e a mae, e vem primeiro")
    assert RC.ORDEM_DO_PAPEL["PAI"] < RC.ORDEM_DO_PAPEL["AVO_MATERNO"]
    assert RC.ORDEM_DO_PAPEL["AVO_PATERNA"] < RC.ORDEM_DO_PAPEL["DECLARANTE"]
    assert RC.ORDEM_DO_PAPEL["DECLARANTE"] < RC.ORDEM_DO_PAPEL["TESTEMUNHA"]


def test_o_obito_nao_aceita_avos_e_o_casamento_nao_aceita_filiacao():
    """O papel sai da ESPECIE, e nao do formulario. Um obito com avos seria
    dado que confunde quem ler depois."""
    con = banco()
    with pytest.raises(RC.RcError):
        RC.lavrar_assento(con, especie="OBITO", nome="X", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO,
                          pessoas=[{"papel": "AVO_PATERNO", "nome": "Y"}])
    con.close()


def test_todo_papel_tem_rotulo_prefixo_e_ordem():
    """Papel sem rotulo aparece na tela como chave de banco; sem prefixo, o
    formulario nao o le; sem ordem, ele cai no comeco da certidao."""
    todos = {p for ps in RC.PAPEIS_DA_ESPECIE.values() for p in ps}
    for papel in todos:
        assert papel in RC.ROTULO_DO_PAPEL, f"{papel} sem rótulo"
        assert papel in RC.PREFIXO_DO_PAPEL, f"{papel} sem prefixo"
        assert papel in RC.ORDEM_DO_PAPEL, f"{papel} sem ordem"


def test_a_filiacao_1_e_a_mae_com_o_parentese_de_indicacao():
    """**Decisao do oficial em 30/08/2026:** «filiacao 1 e 2, indicando a 1
    para mae entre parenteses (mera indicacao)».

    O PARENTESE E INDICACAO, E NAO REGRA: ha seis assentos nesta casa com as
    duas filiacoes do mesmo sexo, e ali «(mae)» e so uma dica de onde a maioria
    escreve.

    **E o contrario do E-Oficio**, onde a filiacao 1 e o pai — medido no acervo
    bruto, 162 masculinas contra 30 femininas na 1. A escolha foi do oficial.
    """
    assert RC.ROTULO_DO_PAPEL["MAE"] == "Filiação 1 (mãe)"
    assert RC.ROTULO_DO_PAPEL["PAI"] == "Filiação 2 (pai)"
    assert "Progenitor" in RC.ROTULO_DO_PAPEL["AVO_MATERNO"]


def test_o_prefixo_nao_se_deduz_do_numero_de_papeis():
    """Ate 30/08/2026 a rota deduzia o prefixo pelo NUMERO de papeis — «se for
    um so, chama-se pessoa» —, e isso quebrava assim que a especie passasse a
    ter tres. Passou a ter nove no mesmo dia."""
    assert RC.PREFIXO_DO_PAPEL["MAE"] == "filiacao1"
    assert RC.PREFIXO_DO_PAPEL["REGISTRADO"] == "pessoa"
    assert len(set(RC.PREFIXO_DO_PAPEL.values())) >= 10, (
        "prefixos repetidos fariam dois papéis lerem o mesmo bloco da tela")


# ---------- a naturalidade da PESSOA, derivada do que o termo declara
#
# **O DEFEITO — 22/09/2026.** A CRC reteve **19 dos 47** nascimentos
# pendentes, e **17 pelo mesmo motivo**: «o município de nascimento do
# registrado não está na ficha». A naturalidade estava escrita — no campo do
# ASSENTO —, e a carga lê o da PESSOA. Dois campos para a mesma coisa, e o
# balcão preenchia um: **todo assento novo saía retido**, um por dia, de 16 a
# 22/09, pelo caminho do teor colado.
#
# **A REGRA MORA NO DOMÍNIO, E NÃO NA ROTA** — e não é preferência de arrumação:
# o mesmo conserto tinha de valer para a tela de lavrar e para o script que
# acerta os que já estão gravados. Duas leituras da naturalidade divergiriam no
# primeiro conserto.


def _com_municipios(con, *linhas):
    """`ib_municipios` na bancada — a tabela que a busca do IBGE consulta.

    Sem ela `lugar()` não acha nada, e a derivação (que **só grava o que o
    cadastro confirma**) recusaria tudo — o teste passaria por falta de dado,
    e não por acerto.
    """
    from ibge_schema import init_ibge_schema
    init_ibge_schema(con)
    for codigo, uf, nome in linhas or ((2198765, "MA", "Cidade Exemplo"),):
        con.execute(
            """INSERT INTO ib_municipios (codigo_ibge, codigo_uf, codigo_mun,
                   uf, nome, nome_norm, origem, criado_em)
               VALUES (?, ?, ?, ?, ?, ?, 'TESTE', ?)""",
            (codigo, str(codigo)[:2], str(codigo)[2:], uf, nome,
             __import__("ibge_schema").normalizar_nome(nome), AGORA))


def _naturalidade_da_pessoa(con, assento_id, papel="REGISTRADO"):
    linha = con.execute(
        """SELECT naturalidade_cidade, naturalidade_uf FROM rc_pessoas
           WHERE assento_id=? AND papel=?""", (assento_id, papel)).fetchone()
    return (linha["naturalidade_cidade"], linha["naturalidade_uf"])


def test_o_municipio_vem_depois_da_ultima_virgula():
    """O povoado é onde a pessoa nasceu; o município é o que o IBGE conhece.

    Ficar com o povoado faria a busca não achar nada — ou, pior, achar um
    município homônimo noutro estado.
    """
    assert RC.municipio_da_naturalidade(
        "VÃO DA POSSE, Cidade Exemplo-MA") == ("Cidade Exemplo", "MA")
    assert RC.municipio_da_naturalidade(
        "Povoado Passagem Boa, Cidade Exemplo-MA") == ("Cidade Exemplo", "MA")


def test_a_uf_se_corta_com_barra_e_com_hifen():
    """As duas formas aparecem no mesmo lote, digitadas pela mesma casa."""
    assert RC.municipio_da_naturalidade("Imperatriz/MA") == ("Imperatriz", "MA")
    assert RC.municipio_da_naturalidade("Cidade Exemplo-MA") == ("Cidade Exemplo", "MA")
    assert RC.municipio_da_naturalidade("IMPERATRIZ/MA.") == ("IMPERATRIZ", "MA")


def test_municipio_com_hifen_no_nome_nao_se_parte():
    """**O guarda que evita inventar cidade.** Há município com hífen no nome
    — Mogi-Mirim, Embu-Guaçu —, e cortar no último hífen sem conferir o
    tamanho transformaria «Mogi-Mirim» em «Mogi», que também existe."""
    assert RC.municipio_da_naturalidade("Mogi-Mirim") == ("Mogi-Mirim", "")
    assert RC.municipio_da_naturalidade("Mogi-Mirim-SP") == ("Mogi-Mirim", "SP")


def test_sem_uf_escrita_nao_se_inventa_uma():
    """Quem não escreveu o estado não disse «MA» — e município homônimo em
    dois estados é a regra, não a exceção."""
    assert RC.municipio_da_naturalidade("Cidade Exemplo") == ("Cidade Exemplo", "")
    assert RC.municipio_da_naturalidade("") == ("", "")
    assert RC.municipio_da_naturalidade(None) == ("", "")


def test_lavrar_com_naturalidade_declarada_preenche_a_pessoa():
    """**O conserto, pelo caminho que o balcão usa.**"""
    con = banco()
    _com_municipios(con)
    r = nascimento(con, termo_dados={
        "local_fato_nome": "Hospital Municipal",
        "naturalidade_declarada": "VÃO DA POSSE, Cidade Exemplo-MA"})
    assert _naturalidade_da_pessoa(con, r["assento_id"]) == ("Cidade Exemplo", "MA")
    con.close()


def test_municipio_que_o_cadastro_do_ibge_nao_confirma_nao_e_gravado():
    """**A guarda que torna a derivação defensável.** O campo sobe para uma
    Central nacional; gravar nome que ninguém conferiu seria o sistema
    afirmando um município. Vazio, a carga retém e diz que é grafia — que é a
    rede que já existia."""
    con = banco()
    _com_municipios(con)
    td = {"local_fato_nome": "Hospital",
          "naturalidade_declarada": "Cidade Que Não Existe/XX"}
    # DESDE O RELATO #130 (14/10/2026) a lavratura do balcão já recusa: sem
    # município confirmado, a CRC retém o nascimento. A derivação se confere
    # pela saída de emergência do oficial, que lavra por cima e deixa gravado.
    import rc_centrais_na_lavratura as CENT
    con.execute("SAVEPOINT x")
    with pytest.raises(CENT.FaltaParaAsCentraisError, match="município"):
        nascimento(con, termo_dados=td)
    con.execute("ROLLBACK TO x")
    con.execute("RELEASE x")
    r = nascimento(con, termo_dados=td, usuario="MARIO EXEMPLO DOS SANTOS",
                   forcar_motivo="municipio de nascimento a conferir na DNV")
    assert _naturalidade_da_pessoa(con, r["assento_id"]) == (None, None)
    con.close()


def test_nao_sobrescreve_naturalidade_que_alguem_escreveu():
    """Campo preenchido é resposta de gente. Derivar por cima apagaria a
    correção que ela fez justamente porque a derivação estava errada."""
    con = banco()
    _com_municipios(con, (2198765, "MA", "Cidade Exemplo"),
                    (2103000, "MA", "Imperatriz"))
    r = nascimento(con, pessoas=[
        {"papel": "REGISTRADO", "nome": "JOÃO", "sexo": "M",
         "naturalidade_cidade": "Imperatriz", "naturalidade_uf": "MA"},
        {"papel": "MAE", "nome": "MARIA DA SILVA"},
        {"papel": "PAI", "nome": "IGNORADO"},
        {"papel": "DECLARANTE", "nome": "MARIA DA SILVA"},
    ], termo_dados={"local_fato_nome": "Hospital",
                    "naturalidade_declarada": "Cidade Exemplo-MA"})
    assert _naturalidade_da_pessoa(con, r["assento_id"]) == ("Imperatriz", "MA")
    con.close()


def test_anotar_o_termo_depois_tambem_preenche():
    """O assento tardio completa o termo dias depois, e a naturalidade tem de
    seguir junto — senão o conserto valeria só para quem lavra de uma vez."""
    con = banco()
    # O cadastro do IBGE entra DEPOIS da lavratura: com ele carregado, desde o
    # relato #130 (14/10/2026) o balcão não lavra nascimento sem o município
    # que a CRC exige. O que se guarda aqui é o completar de depois.
    r = nascimento(con)
    _com_municipios(con)
    assert _naturalidade_da_pessoa(con, r["assento_id"]) == (None, None)
    saida = RC.anotar_do_termo(con, r["assento_id"],
                               naturalidade_declarada="Cidade Exemplo/MA")
    assert saida["naturalidade"]["gravou"] is True
    assert _naturalidade_da_pessoa(con, r["assento_id"]) == ("Cidade Exemplo", "MA")
    con.close()


def test_rodar_duas_vezes_da_o_mesmo_resultado():
    """O script que acerta os assentos já gravados chama esta mesma função, e
    roda mais de uma vez na vida."""
    con = banco()
    _com_municipios(con)
    r = nascimento(con, termo_dados={"local_fato_nome": "Hospital",
                                     "naturalidade_declarada": "Cidade Exemplo-MA"})
    antes = _naturalidade_da_pessoa(con, r["assento_id"])
    segunda = RC.anotar_do_termo(con, r["assento_id"],
                                 naturalidade_declarada="Cidade Exemplo-MA")
    assert segunda["naturalidade"]["gravou"] is False
    assert _naturalidade_da_pessoa(con, r["assento_id"]) == antes
    con.close()


def test_o_titular_da_naturalidade_cobre_as_especies_que_tem_o_campo():
    """Espécie cujo termo declara naturalidade e que não estivesse no mapa
    passaria batido — o assento guardaria o texto e a pessoa continuaria
    vazia, que é exatamente o defeito de 22/09."""
    com_campo = {e for e, campos in RC.CAMPOS_DO_TERMO_POR_ESPECIE.items()
                 if "naturalidade_declarada" in campos}
    assert com_campo == set(RC.TITULAR_DA_NATURALIDADE)


# ------------------------------------- a situação se confere com a linha presa
#
# L039R (varredura do mesmo padrão da ressalva 1 do L039): o lançamento
# (averbar, anotar, retificar) e a correção da ficha conferiam a situação do
# assento sem prender a linha. Com a ponte, a transação da rota já pega a
# trava única do banco; sem ela, um cancelamento ao mesmo tempo (o da rota de
# lavratura quando o selo falha) passava pela conferência. Os testes usam
# conexões do psycopg sem a ponte — como a transação vai ficar quando a ponte
# sair.

import banco_pg                                  # noqa: E402
from bd_nativo import banco as banco_nativo      # noqa: E402

SO_NO_POSTGRES = pytest.mark.skipif(
    not banco_pg.ativo(),
    reason="trava de linha: só existe com o PostgreSQL ligado (CG_PG_DSN)")


def _psycopg_puro(con, *, autocommit=False):
    """Uma conexão do psycopg no schema do teste, SEM a ponte."""
    import psycopg
    pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
    pg.execute(f'SET search_path TO "{con.schema}", public')
    if not autocommit:
        pg.commit()
    return pg


def _cancelado_no_meio(con, assento_id, faz):
    """Uma conexão cancela o assento e ainda não confirmou; `faz(outra)` roda
    noutra, num fio, e tem de ESPERAR a linha. Devolve o erro dela, ou None."""
    import threading
    import time
    um, dois = _psycopg_puro(con), _psycopg_puro(con)
    vigia = _psycopg_puro(con, autocommit=True)
    try:
        banco_nativo(um).escrever(
            "UPDATE rc_assentos SET situacao='CANCELADO' WHERE id=%s",
            (assento_id,))
        pid = banco_nativo(dois).valor("SELECT pg_backend_pid() AS pid")
        saida: dict = {}

        def corre():
            try:
                faz(dois)
                dois.commit()
            except Exception as erro:  # o teste confere qual
                saida["erro"] = erro
                dois.rollback()

        fio = threading.Thread(target=corre)
        fio.start()
        for _ in range(200):
            if banco_nativo(vigia).valor(
                    "SELECT count(*) AS n FROM pg_locks WHERE pid=%s AND NOT granted",
                    (pid,)):
                break
            time.sleep(0.05)
        um.commit()
        fio.join(30)
        return saida.get("erro")
    finally:
        for c in (um, dois, vigia):
            c.close()


@SO_NO_POSTGRES
def test_averbacao_que_chega_no_meio_do_cancelamento_e_recusada():
    con = banco()
    r = nascimento(con)
    con.commit()

    def averba(outra):
        RC.averbar(outra, r["assento_id"], teor="Averbação de reconhecimento.",
                   agora=AGORA)

    erro = _cancelado_no_meio(con, r["assento_id"], averba)
    assert isinstance(erro, RC.RcError), erro
    assert "situação CANCELADO" in str(erro)
    assert [a["tipo"] for a in RC.atos_do(con, r["assento_id"])] == ["REGISTRO"]


@SO_NO_POSTGRES
def test_correcao_que_chega_no_meio_do_cancelamento_e_recusada():
    con = banco()
    r = nascimento(con)
    con.commit()

    def corrige(outra):
        RC.corrigir_informacoes(outra, r["assento_id"], nome="JOÃO DA SILVA SOUZA",
                                motivo="Grafia do sobrenome conferida no livro.",
                                agora=AGORA)

    erro = _cancelado_no_meio(con, r["assento_id"], corrige)
    assert isinstance(erro, RC.RcError), erro
    assert "assento ativo" in str(erro)
    assert RC.assento(con, r["assento_id"])["nome"] == "JOÃO DA SILVA"
