"""A fila da Central de Certidoes e a certidao eletronica — o dominio.

O QUE ESTES TESTES PROTEGEM, e cada um custou uma decisao:

    o casamento pela matricula  casar por livro/folha abriria a ficha de OUTRA
                                pessoa, e ninguem desconfia de uma ficha que
                                abre

    registro nao e certidao     P13 e EOB pedem que se LAVRE. O modulo recusa
                                cumpri-los como se fossem pedido de certidao

    o que NAO se inventa        o sexo em branco nao vira «ignorado»; a letra
                                do tipo de registro so vale para o «N»; o
                                natimorto nao vira «nascimento»

    dinheiro                    o deposito previo volta com virgula e o valor
                                sobe com ponto — a conta erra por cem se
                                ninguem converter

QUEM RECUSA E O DOMINIO. Estes testes chamam as funcoes direto, sem rota
nenhuma — e **nenhum deles fala com a Central**.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_assento as RC
import rc_pedidos as PED
import rc_pedidos_schema as ESQ
from nucleo_schema import init_nucleo_schema
from rc_pedidos_schema import init_rc_pedidos_schema
from rc_schema import init_rc_schema

AGORA = "2026-09-03T10:00:00"
CNS = "000000"
MATRICULA = "00000001552026100001001000012345"
SV = {"ri_cns": CNS, "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
      "escrevente": "MARIO", "funcao": "Escrevente"}


@pytest.fixture()
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(c)
    init_rc_schema(c)
    init_rc_pedidos_schema(c)
    return c


# AS PESSOAS QUE A LEI EXIGE EM CADA ESPECIE. Sem elas `lavrar_assento`
# recusa — «nao se lavra o assento em branco» —, e e a recusa certa: o teste
# monta um assento de verdade, e nao um esqueleto que a producao nao teria.
PESSOAS_DA_ESPECIE = {
    "NASCIMENTO": [
        {"papel": "REGISTRADO", "nome": "FULANO DE TAL", "sexo": "M",
         "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "MA"},
        {"papel": "MAE", "nome": "MARIA DE TAL"},
        {"papel": "PAI", "nome": "JOSE DE TAL"},
        {"papel": "DECLARANTE", "nome": "JOSE DE TAL"},
    ],
    "NATIMORTO": [
        {"papel": "REGISTRADO", "nome": "NATIMORTO DE TAL", "sexo": "M"},
        {"papel": "MAE", "nome": "MARIA DE TAL"},
        {"papel": "PAI", "nome": "JOSE DE TAL"},
        {"papel": "DECLARANTE", "nome": "JOSE DE TAL"},
    ],
    "OBITO": [
        {"papel": "FALECIDO", "nome": "JOSE DA SILVA", "sexo": "M",
         "estado_civil": "casado", "data_nascimento": "1950-02-20",
         "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "MA"},
        {"papel": "MAE", "nome": "ROSA DA SILVA"},
        {"papel": "PAI", "nome": "ANTONIO DA SILVA"},
        {"papel": "DECLARANTE", "nome": "PEDRO DA SILVA"},
    ],
    "CASAMENTO": [
        {"papel": "NUBENTE1", "nome": "FULANO DE TAL", "sexo": "M",
         "nacionalidade": "Brasileira", "estado_civil": "solteiro",
         "data_nascimento": "1990-05-12",
         "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "MA"},
        {"papel": "NUBENTE2", "nome": "BELTRANA DE TAL E SILVA", "sexo": "F",
         "nacionalidade": "Brasileira", "estado_civil": "solteira",
         "data_nascimento": "1992-03-08"},
        {"papel": "PAI_NUBENTE1", "nome": "JOSE DE TAL"},
        {"papel": "MAE_NUBENTE1", "nome": "MARIA DE TAL"},
        {"papel": "PAI_NUBENTE2", "nome": "ANTONIO DE TAL"},
        {"papel": "MAE_NUBENTE2", "nome": "JOANA DE TAL"},
        {"papel": "TESTEMUNHA", "nome": "CARLOS TESTEMUNHA"},
    ],
}

TERMO_DA_ESPECIE = {
    "NASCIMENTO": {"local_fato_nome": "Hospital Municipal"},
    "NATIMORTO": {"local_fato_nome": "Hospital Municipal"},
    "OBITO": {"local_fato_nome": "Hospital Municipal"},
    "CASAMENTO": {"local_fato_nome": "Sede da serventia"},
}


def _assento(con, especie="NASCIMENTO", nome=None, matricula=MATRICULA,
             pessoas=None, **campos) -> int:
    """Um assento completo, com o que a lei exige. Depois, as colunas extras."""
    especie = especie.upper()
    lista = [dict(p) for p in (pessoas or PESSOAS_DA_ESPECIE[especie])]
    titular = lista[0]["nome"]
    # O NUMERO DA DECLARACAO DE OBITO ENTRA POR `ibge`, e nao por `dados` —
    # medido em `rc_assento.lavrar_assento`, que monta o assento da
    # conferencia com `(ibge or {}).get("numero_do")`.
    extras = {}
    if especie in ("OBITO", "NATIMORTO"):
        extras["ibge"] = {"numero_do": "123456789"}
    # O QUE A CRC E O SIRC EXIGEM — desde o relato #130 (14/10/2026) a
    # lavratura recusa sem eles: «onde nasceu» e «deixou bens». As colunas que
    # o teste pede em `campos` continuam por cima, como antes.
    if especie == "NASCIMENTO":
        extras["ibge"] = {"local_nascimento": 1}
    if especie == "OBITO":
        extras["marcas_do_obito"] = {"obito_possui_bens": "NAO"}
    feito = RC.lavrar_assento(
        con, especie=especie, nome=(nome or titular), sv=SV, agora=AGORA,
        data_extenso="tres de setembro de dois mil e vinte e seis",
        data_fato="2020-01-15", usuario="MARIO", pessoas=lista,
        termo_dados=TERMO_DA_ESPECIE[especie],
        regime_bens=("Comunhao parcial de bens"
                     if especie == "CASAMENTO" else None),
        **extras)
    ident = feito["assento_id"]
    con.execute("UPDATE rc_assentos SET matricula=? WHERE id=?",
                (matricula, ident))
    if campos:
        con.execute(
            "UPDATE rc_assentos SET "
            + ", ".join(f"{c}=?" for c in campos)
            + " WHERE id=?", (*campos.values(), ident))
    return ident


def _sem(especie, *papeis):
    """As pessoas daquela especie, menos as dos papeis dados."""
    return [dict(p) for p in PESSOAS_DA_ESPECIE[especie]
            if p["papel"] not in papeis]


def _linha_da_central(**extra) -> dict:
    """Uma linha de `rows`, como a Central a manda."""
    base = {"pedido_certidao_id": 11111111,
            "numero_cnj_solicitante": "000000",
            "numero_cnj_recebedor": CNS,
            "nome_requerente": "ENZO FERREIRA",
            "documento_requerente": "33521478",
            "data_pedido": "30/12/2024", "tipo_registro": "N",
            "nome_registrado": "FULANO DE TAL",
            "data_ato_fato": "15/01/2020", "data_registro": "16/01/2020",
            "num_livro": "00061", "num_folha": "051",
            "num_registro": "0001111", "matricula": MATRICULA,
            "obs_pedido": "", "deposito_previo": "43,76"}
    base.update(extra)
    return base


def _guardar(con, **extra) -> int:
    """Poe um pedido na fila sem passar pela rede."""
    import json
    linha = _linha_da_central(**extra)
    cur = con.execute(
        """INSERT INTO rc_pedidos(modulo, ambiente, numero_pedido,
               letra_registro, especie, assento_id, casamento_motivo, teor,
               resumo, deposito_previo, deposito_previo_valor, baixado_em,
               situacao)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (extra.pop("modulo", "CRC"), PED.ambiente(),
         str(linha["pedido_certidao_id"]), linha["tipo_registro"],
         "nascimento", None, "", json.dumps(linha), "resumo",
         linha["deposito_previo"], 43.76, AGORA, ESQ.PENDENTE))
    return int(cur.lastrowid)


# ------------------------------------------------- o casamento com o assento


def test_casa_pela_matricula(con):
    ident = _assento(con)
    achado = PED._casar(con, {"matricula": MATRICULA,
                              "nome_registrado": "FULANO DE TAL"})
    assert achado["assento_id"] == ident
    assert MATRICULA in achado["motivo"]


def test_a_matricula_casa_e_o_nome_diferente_VIRA_AVISO_e_nao_recusa(con):
    """O nome muda legitimamente — o de casada muda em 17 dos 20 casamentos
    desta casa."""
    ident = _assento(con)
    achado = PED._casar(con, {"matricula": MATRICULA,
                              "nome_registrado": "FULANA DE TAL E SILVA"})
    assert achado["assento_id"] == ident
    assert "não é igual" in achado["motivo"]


def test_sem_matricula_nao_se_adivinha_pelo_livro_e_folha(con):
    """**Casar por livro/folha abriria a ficha de outra pessoa.** Os numeros
    reiniciam por volume nesta casa."""
    _assento(con)
    achado = PED._casar(con, {"matricula": "", "num_livro": "00061",
                              "num_folha": "051", "num_registro": "0001111",
                              "nome_registrado": "FULANO DE TAL"})
    assert achado["assento_id"] is None
    assert "não trouxe matrícula" in achado["motivo"]


def test_matricula_que_nao_existe_diz_o_que_conferir(con):
    achado = PED._casar(con, {"matricula": "9" * 32,
                              "nome_registrado": "QUEM"})
    assert achado["assento_id"] is None
    assert "desta serventia" in achado["motivo"]


def test_amarrar_a_mao_o_assento_que_a_matricula_nao_achou(con):
    ident = _assento(con)
    p = _guardar(con)
    PED.amarrar_assento(con, p, ident, motivo="conferido no livro A-12")
    lido = PED.pedido(con, p)
    assert lido["assento_id"] == ident
    assert "livro A-12" in lido["casamento_motivo"]


def test_amarrar_assento_que_nao_existe_e_recusado(con):
    p = _guardar(con)
    with pytest.raises(PED.PedidoError):
        PED.amarrar_assento(con, p, 9999)


# ---------------------------------------------------- registro nao e certidao


def test_marcar_registrado_recusa_modulo_que_pede_CERTIDAO(con):
    """CRC pede certidao; so P13 e EOB pedem que se lavre."""
    ident = _assento(con)
    p = _guardar(con, modulo="CRC")
    with pytest.raises(PED.PedidoError) as erro:
        PED.marcar_registrado(con, p, assento_id=ident, agora=AGORA)
    assert "P13" in str(erro.value)


def test_marcar_registrado_aceita_P13_e_nao_lavra_nada(con):
    ident = _assento(con)
    p = _guardar(con, modulo="P13")
    antes = con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0]
    PED.marcar_registrado(con, p, assento_id=ident, agora=AGORA)
    depois = con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0]
    assert antes == depois, "marcar como registrado LAVROU um assento"
    assert PED.pedido(con, p)["situacao"] == ESQ.REGISTRADO


def test_a_ficha_diz_que_o_modulo_pede_registro(con):
    p = _guardar(con, modulo="EOB")
    lido = PED.pedido(con, p)
    assert lido["pede_registro"] is True
    assert lido["especie_a_lavrar"] == "OBITO"


# ----------------------------------------------------------- dispensar


def test_dispensar_exige_motivo_escrito(con):
    p = _guardar(con)
    with pytest.raises(PED.PedidoError):
        PED.dispensar(con, p, motivo="nao", agora=AGORA)


def test_dispensar_com_motivo_tira_da_fila(con):
    p = _guardar(con)
    PED.dispensar(con, p, motivo="o registro e de outra serventia",
                  agora=AGORA)
    assert PED.pedido(con, p)["situacao"] == ESQ.DISPENSADO
    assert PED.pendentes(con) == []


# --------------------------------------------------------- a montagem


def test_montar_nascimento_traz_filiacao_e_avos_juntos(con):
    ident = _assento(con, pessoas=PESSOAS_DA_ESPECIE["NASCIMENTO"] + [
        {"papel": "AVO_PATERNO", "nome": "ANTONIO DE TAL"},
        {"papel": "AVO_PATERNA", "nome": "ROSA DE TAL"},
        {"papel": "AVO_MATERNO", "nome": "PEDRO DE TAL"},
        {"papel": "AVO_MATERNA", "nome": "JOANA DE TAL"}])

    m = PED.montar(con, ident, cns=CNS)
    assert m["tipo_registro"] == "nascimento"
    assert m["registro"]["sexo"] == "masculino"
    assert m["registro"]["matricula"] == MATRICULA
    assert len(m["registro"]["filiacao"]) == 2
    # **A CENTRAL JUNTA OS DOIS AVOS NUM CAMPO SO**, com ponto e virgula.
    nomes = {f["nome"]: f["avos"] for f in m["registro"]["filiacao"]}
    assert nomes["JOSE DE TAL"] == "ANTONIO DE TAL; ROSA DE TAL"
    assert nomes["MARIA DE TAL"] == "PEDRO DE TAL; JOANA DE TAL"


def test_montar_nascimento_nao_exporta_nao_consta_como_municipio(con):
    """Anotação de ausência não pode virar uma cidade no JSON da CRC."""
    ident = _assento(con)
    con.execute("UPDATE rc_pessoas SET naturalidade_cidade='NADA CONSTA', "
                "naturalidade_uf='PB' WHERE assento_id=? AND papel='PAI'",
                (ident,))

    m = PED.montar(con, ident, cns=CNS)

    pai = next(f for f in m["registro"]["filiacao"]
               if f["nome"] == "JOSE DE TAL")
    # Chave presente e vazia: omitir vira «undefined» na tela da CRC.
    assert pai["municipio_nascimento"] == ""
    assert "undefined" not in str(pai["municipio_nascimento"]).lower()
    assert pai["uf_nascimento"] == "PB"
    assert any("município válido" in aviso for aviso in m["avisos"])


def test_montar_nascimento_filiacao_sem_naturalidade_nao_vira_undefined(con):
    """Campo ausente no JSON vira a palavra JS «undefined» na tela da CRC."""
    ident = _assento(con)
    con.execute("UPDATE rc_pessoas SET naturalidade_cidade=NULL, "
                "naturalidade_uf=NULL WHERE assento_id=? AND papel IN "
                "('PAI','MAE')", (ident,))
    m = PED.montar(con, ident, cns=CNS)
    corpo = json.dumps(m["registro"]["filiacao"], ensure_ascii=False)
    assert "undefined" not in corpo.lower()
    for f in m["registro"]["filiacao"]:
        assert "municipio_nascimento" in f
        assert "uf_nascimento" in f
        assert f["municipio_nascimento"] == ""
        assert f["uf_nascimento"] == ""


def test_o_sexo_em_branco_NAO_vira_ignorado(con):
    """`ignorado` e uma resposta que alguem pode ter dado; vazio e campo que
    ninguem preencheu.

    O caso e real: **14 pessoas da producao tem `sexo` vazio**. A lavratura
    nova exige o sexo (art. 54), de modo que este assento nasce com ele e o
    teste o apaga — que e como aquelas 14 chegaram, pela carga do acervo.
    """
    ident = _assento(con)
    con.execute("UPDATE rc_pessoas SET sexo='' WHERE assento_id=? AND papel=?",
                (ident, "REGISTRADO"))
    m = PED.montar(con, ident, cns=CNS)
    assert "sexo" not in m["registro"]
    assert any("sexo" in a for a in m["avisos"])


def test_o_cpf_vai_com_mascara(con):
    ident = _assento(con, cpf_registrado="00000004693")
    m = PED.montar(con, ident, cns=CNS)
    assert m["registro"]["cpf"] == "000.000.046-93"


def test_sem_filiacao_o_aviso_diz_onde_consertar(con):
    """A lavratura nova EXIGE filiacao (art. 54); quem chega sem ela e o
    acervo."""
    ident = _assento(con)
    con.execute("DELETE FROM rc_pessoas WHERE assento_id=? AND papel IN "
                "('PAI','MAE')", (ident,))
    m = PED.montar(con, ident, cns=CNS)
    assert m["registro"].get("filiacao") in (None, [])
    assert any("filia" in a for a in m["avisos"])


def test_o_natimorto_NAO_vira_nascimento(con):
    """Afirmaria nascimento com vida — a mesma recusa que o papel ja faz."""
    ident = _assento(con, especie="NATIMORTO")
    with pytest.raises(PED.PedidoError) as erro:
        PED.montar(con, ident, cns=CNS)
    assert "quatro" in str(erro.value)


def test_o_obito_leva_os_tres_campos_que_o_revisor_cobrou(con):
    """Causa da morte, quem atestou e onde se sepultou — o achado 2 do revisor
    registral, que a Central pede com estes nomes."""
    ident = _assento(con, especie="OBITO",
                     causa_morte="infarto agudo do miocardio",
                     atestante="DRA. ANA", atestante_documento="CRM 12256363",
                     local_sepultamento="Cemiterio Municipal")
    m = PED.montar(con, ident, cns=CNS)
    assert m["tipo_registro"] == "obito"
    assert m["registro"]["causa_morte"] == "infarto agudo do miocardio"
    assert m["registro"]["nome_medico"] == "DRA. ANA"
    assert m["registro"]["crm_medico"] == "CRM 12256363"
    assert m["registro"]["local_sepultamento_cremacao"] == "Cemiterio Municipal"
    assert m["registro"]["nome_declarante"] == "PEDRO DA SILVA"
    assert m["registro"]["filiacao"] == "ANTONIO DA SILVA; ROSA DA SILVA"


def test_existencia_de_bens_que_a_central_nao_entende_fica_em_branco(con):
    """Mandar «nao» sobre um texto que nao se entendeu afirmaria que o falecido
    nao deixou bens."""
    ident = _assento(con, especie="OBITO",
                     obito_possui_bens="uma casa e um terreno")
    m = PED.montar(con, ident, cns=CNS)
    assert "existencia_bens" not in m["registro"]
    assert any("bens" in a for a in m["avisos"])


def test_existencia_de_bens_reconhecida_vai(con):
    ident = _assento(con, especie="OBITO", obito_possui_bens="sim")
    m = PED.montar(con, ident, cns=CNS)
    assert m["registro"]["existencia_bens"] == "sim"


def test_o_casamento_avisa_que_o_nome_apos_o_casamento_nao_vai(con):
    """E o campo que a certidao de casamento existe para dizer."""
    ident = _assento(con, especie="CASAMENTO", nome="FULANO e BELTRANA")
    m = PED.montar(con, ident, cns=CNS)
    assert m["tipo_registro"] == "casamento"
    assert len(m["registro"]["conjuges"]) == 2
    assert m["registro"]["conjuges"][0]["genitores"] == (
        "JOSE DE TAL; MARIA DE TAL")
    assert m["registro"]["regime_bens"] == "Comunhao parcial de bens"
    assert any("passou a utilizar" in a for a in m["avisos"])


def test_o_inteiro_teor_sem_teor_avisa_e_impede(con):
    """Os 244 assentos do acervo vieram sem teor — para eles a copia se tira do
    livro de papel."""
    ident = _assento(con)
    con.execute("UPDATE rc_assentos SET teor=NULL WHERE id=?", (ident,))
    c = PED.conferir(con, ident, cns=CNS, tipo_registro="inteiro_teor")
    assert any("teor" in a for a in c["avisos"])
    assert any("Inteiro teor sem teor" in i for i in c["impedem"])


def test_o_inteiro_teor_com_teor_sai(con):
    ident = _assento(con)
    con.execute("UPDATE rc_assentos SET teor=? WHERE id=?",
                ("Aos quinze dias de janeiro...", ident))
    m = PED.montar(con, ident, cns=CNS, tipo_registro="inteiro_teor")
    assert m["registro"]["texto_certidao"].startswith("Aos quinze")
    # `tipo_certidao` so existe no inteiro teor, e diz de que especie ele e:
    assert m["certidao"]["tipo_certidao"] == "nascimento"


def test_o_tipo_certidao_NAO_vai_fora_do_inteiro_teor(con):
    ident = _assento(con)
    m = PED.montar(con, ident, cns=CNS)
    assert "tipo_certidao" not in m["certidao"]


def test_o_isento_vai_mesmo_sendo_falso(con):
    """«nao e isento» e diferente de «nao se disse» — e por isso o booleano nao
    passa pelo filtro de vazios."""
    ident = _assento(con)
    m = PED.montar(con, ident, cns=CNS)
    assert m["certidao"]["cota_emolumentos_isento"] is False


def test_a_cota_vai_com_reais_e_virgula(con):
    ident = _assento(con)
    m = PED.montar(con, ident, cns=CNS, cota_emolumentos="43,76")
    assert m["certidao"]["cota_emolumentos"] == "R$ 43,76"


def test_a_averbacao_sai_de_rc_atos_e_nao_de_coluna_do_assento(con):
    """**CORRECAO VISIVEL**: a primeira versao lia
    `assento["averbacao_anotacao"]`, e essa coluna NAO EXISTE — eu montei o
    nome a partir do campo da Central, que se chama assim. Nome plausivel e o
    que mais se parece com medicao sem ser.

    O dado mora em `rc_atos`, que e onde a divisao tripartite do RCPN vive.
    """
    colunas = {linha[1] for linha in con.execute(
        "PRAGMA table_info(rc_assentos)")}
    assert "averbacao_anotacao" not in colunas
    ident = _assento(con)
    RC.averbar(con, ident, teor="Averbado o divorcio dos genitores.",
               agora=AGORA, usuario="MARIO")
    m = PED.montar(con, ident, cns=CNS)
    assert "divorcio" in m["registro"]["averbacao_anotacao"]


# ------------------------------------------------------- a conferencia


def test_sem_matricula_a_conferencia_impede(con):
    ident = _assento(con, matricula=None)
    c = PED.conferir(con, ident, cns=CNS)
    assert not c["pronto"]
    assert any("matr" in i for i in c["impedem"])


def test_sem_cns_a_conferencia_impede(con):
    ident = _assento(con)
    c = PED.conferir(con, ident, cns="")
    assert any("CNS" in i for i in c["impedem"])


def test_o_aviso_do_selo_diz_que_a_casa_nao_compra(con):
    ident = _assento(con)
    c = PED.conferir(con, ident, cns=CNS)
    assert any("compra" in a or "selou" in a for a in c["avisos"])


# ------------------------------------------------------------- dinheiro


def test_o_valor_adicional_e_a_diferenca_e_converte_a_virgula(con):
    """O deposito volta «43,76» e o valor sobe «10.00» — quem nao converter
    erra por cem."""
    p = _guardar(con)
    lido = PED.pedido(con, p)
    s = PED.sugerir_valor_adicional(lido, "50,00")
    assert s["deposito_previo"] == 43.76
    assert s["valor_final"] == 50.0
    assert s["valor_adicional"] == 6.24


def test_deposito_maior_que_o_valor_final_NAO_some(con):
    """Esconder a diferenca tiraria a decisao do balcao."""
    p = _guardar(con)
    lido = PED.pedido(con, p)
    s = PED.sugerir_valor_adicional(lido, "10,00")
    assert s["valor_adicional"] == 0.0
    assert s["houve_devolucao"] is True
    assert s["diferenca"] < 0


# --------------------------------------------------------------- a fila


def test_a_fila_conta_por_modulo(con):
    _guardar(con)
    _guardar(con, modulo="P13", pedido_certidao_id=22222222)
    contagem = PED.quantos_por_modulo(con)
    assert contagem["CRC"] == 1
    assert contagem["P13"] == 1
    assert contagem["EOB"] == 0
    assert set(contagem) == set(__import__("onrcpn_certidao_api").MODULOS)


def test_o_mesmo_pedido_nao_entra_duas_vezes(con):
    """A trava e o indice unico, e nao uma conferencia em Python."""
    _guardar(con)
    with pytest.raises(sqlite3.IntegrityError):
        _guardar(con)


def test_a_letra_desconhecida_deixa_a_especie_em_branco_na_ficha(con):
    p = _guardar(con, tipo_registro="Z")
    con.execute("UPDATE rc_pedidos SET especie=NULL, letra_registro=? "
                "WHERE id=?", ("Z", p))
    lido = PED.pedido(con, p)
    assert lido["especie"] is None
    assert lido["letra_registro"] == "Z"
