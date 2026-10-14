"""O CPF no registro de nascimento.

O QUE ESTES TESTES GUARDAM
    **Que `solicitar` RECUSA, e diz por que.** Nao ha canal para pedir CPF a
    Receita: falta o endereco do servico, o contrato da mensagem e a
    credencial da serventia no convenio. Medido em 30/08/2026: nem a carga da
    CRC nem a remessa do SIRC geram CPF — as duas apenas transportam o numero
    que ja existe. **Fingir que integra e pior que nao ter.**

    **Que o digito verificador e conferido antes de gravar.** CPF com um
    digito trocado tem onze algarismos como qualquer outro: passa em
    conferencia de formato e so e descoberto quando alguem tenta usa-lo — e
    ai ja saiu na certidao.

    **Que o acervo fica de fora da lista.** O CPF dos assentos antigos e o
    mutirao do art. 347, com tela e caminho proprios. Misturar faria uma lista
    de 244 linhas onde a de hoje tem poucas.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_cpf as CPF                                           # noqa: E402


# --------------------------------------------------- o digito verificador


def test_aceita_cpf_certo():
    """O do termo real desta casa, nº 19.555."""
    assert CPF.valido("000.000.045-02") is True
    assert CPF.valido("00000004502") is True


def test_recusa_digito_trocado():
    """**E o caso que mais importa**: onze algarismos, formato certo, numero
    errado. So se descobre quando alguem tenta usar — e ai ja saiu na
    certidao."""
    assert CPF.valido("13672050343") is False


def test_recusa_todos_iguais():
    """`111.111.111-11` fecha a conta do modulo 11 e nao e CPF de ninguem."""
    for n in range(10):
        assert CPF.valido(str(n) * 11) is False


def test_recusa_tamanho_errado():
    for ruim in ("", None, "123", "1367205034", "136720503421"):
        assert CPF.valido(ruim) is False


def test_formatar_e_devolve_como_veio_quando_nao_da():
    assert CPF.formatar("00000004502") == "000.000.045-02"
    assert CPF.formatar("abc") == "abc"


# --------------------------------------------------- o que ainda nao ha


def test_solicitar_recusa_e_diz_o_que_falta():
    """**A funcao existe para que a falta tenha um lugar.** Sem ela, quem
    procurar a integracao conclui que ela esta escondida em algum canto — e
    ela nao esta: ela nao existe."""
    with pytest.raises(CPF.CpfError) as e:
        CPF.solicitar()
    texto = str(e.value)
    # **O TERMO DE ADESAO TRAVA OS TRES CAMINHOS**, inclusive o formulario
    # manual: sem ele nem a tela da CRC aparece. Por isso vem primeiro na
    # recusa — e uma acao do oficial, nao um desenvolvimento.
    assert "Termo de Adesão" in texto
    assert "sistema.registrocivil.org.br" in texto
    # E a recusa aponta o caminho que JA funciona, para que a falta da
    # integracao nao seja lida como falta do servico.
    assert "formulário da CRC" in texto


def test_a_inscricao_e_obrigatoria_e_isso_esta_dito():
    """«A inscricao no CPF nao e um ato discricionario dos usuarios e sim
    obrigatorio» — IN RFB 1.548/2015, art. 3º, V. **Nao e conveniencia que se
    oferece: e dever**, e a tela precisa poder dizer isso."""
    assert "1.548" in CPF.NORMA and "obrigatória" in CPF.NORMA


def test_os_tres_caminhos_e_o_que_funciona_hoje():
    """O manual da ARPEN da tres, e so um funciona sem desenvolvimento
    nenhum — o formulario na tela deles."""
    assert {c["chave"] for c in CPF.CAMINHOS} == {
        "FORMULARIO", "UNIDADE_INTERLIGADA", "WEBSERVICE"}
    hoje = [c for c in CPF.CAMINHOS if "funciona hoje" in c["porque"]]
    assert len(hoje) == 1 and hoje[0]["chave"] == "FORMULARIO"


def test_o_erro_do_cpf_nao_segura_o_registro():
    """«Nos casos em que houver algum erro e o CPF nao for gerado, o cartorio
    devera proceder a emissao da certidao **normalmente sem o CPF**» — manual
    da ARPEN. O registro e obrigatorio e tem prazo proprio."""
    assert "sem o CPF" in CPF.O_QUE_FAZER_SE_ERRAR
    assert "Receita Federal" in CPF.O_QUE_FAZER_SE_ERRAR
    assert len(CPF.ERROS_CONHECIDOS) >= 2
    assert any("60" in e["o_que"] for e in CPF.ERROS_CONHECIDOS)


def test_ha_prazo_para_corrigir_e_ele_esta_dito():
    """Noventa dias, na CRC Nacional. Prazo que nao se sabe e prazo perdido."""
    assert CPF.PRAZO_CORRECAO_DIAS == 90
    assert "CRC Nacional" in CPF.ONDE_CORRIGIR


def test_o_que_falta_para_integrar_diz_de_quem_e_cada_coisa():
    """Falta sem dono e falta que ninguem vai buscar."""
    assert len(CPF.FALTA_PARA_INTEGRAR) >= 3
    for x in CPF.FALTA_PARA_INTEGRAR:
        assert x["o_que"] and x["de_quem"]
    junto = " ".join(x["de_quem"] for x in CPF.FALTA_PARA_INTEGRAR)
    assert "ARPEN" in junto


def test_o_certificado_ja_existe_e_esta_dito():
    """Das quatro faltas, uma **ja esta resolvida** — e dize-lo evita que o
    oficial va buscar o que ja tem."""
    cert = [x for x in CPF.FALTA_PARA_INTEGRAR
            if "certificado digital** que autentica" in x["o_que"]]
    assert cert and "já existe" in cert[0]["de_quem"]
    # E exatamente UMA das faltas trava tudo — a adesao.
    travam = [x for x in CPF.FALTA_PARA_INTEGRAR if x.get("trava_tudo")]
    assert len(travam) == 1 and "Adesão" in travam[0]["o_que"]


# --------------------------------------------------- o pedido e a lista


def test_diz_o_que_falta_no_assento_para_pedir():
    """Vale **antes** do servico: quando o canal chegar, a casa ja sabera
    quais assentos estao prontos, em vez de descobrir um a um, no erro."""
    faltam = [d["chave"] for d in CPF.o_que_falta_para_pedir({}, [])]
    assert set(faltam) == {d["chave"] for d in CPF.DADOS_DO_PEDIDO}

    completo = {"nome": "PAULO", "data_fato": "2026-08-08",
                "naturalidade_declarada": "Cidade Exemplo",
                "matricula": "0" * 32}
    pessoas = [{"papel": "REGISTRADO", "sexo": "M"},
               {"papel": "MAE", "nome": "VALDENISA"}]
    assert CPF.o_que_falta_para_pedir(completo, pessoas) == []


def test_uma_filiacao_basta():
    """A Receita identifica com **ao menos uma** filiacao — exigir as duas
    barraria o registro sem filiacao paterna, que e caso comum."""
    a = {"nome": "X", "data_fato": "2026-01-01",
         "naturalidade_declarada": "Y", "matricula": "0" * 32}
    so_pai = [{"papel": "REGISTRADO", "sexo": "M"},
              {"papel": "PAI", "nome": "FULANO"}]
    assert CPF.o_que_falta_para_pedir(a, so_pai) == []


def _banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE rc_assentos (id INTEGER PRIMARY KEY, "
                "especie TEXT, numero INTEGER, nome TEXT, data_ato TEXT, "
                "data_fato TEXT, matricula TEXT, situacao TEXT, origem TEXT, "
                "cpf_registrado TEXT)")
    con.executemany(
        "INSERT INTO rc_assentos VALUES (?,?,?,?,?,?,?,?,?,?)", [
            (1, "NASCIMENTO", 1, "DE HOJE", "2026-08-30", "2026-08-28",
             "0" * 32, "ATIVO", "MANUAL", ""),
            (2, "NASCIMENTO", 2, "DO ACERVO", "1990-01-01", "1990-01-01",
             "0" * 32, "ATIVO", "EOFICIO", ""),
            (3, "NASCIMENTO", 3, "JA TEM", "2026-08-01", "2026-07-30",
             "0" * 32, "ATIVO", "MANUAL", "00000004502"),
            (4, "OBITO", 4, "OBITO", "2026-08-01", "2026-07-30",
             "0" * 32, "ATIVO", "MANUAL", ""),
        ])
    con.commit()
    return con


def test_a_lista_e_do_balcao_e_o_acervo_fica_de_fora():
    """O CPF dos assentos antigos e o mutirao do art. 347, com tela propria.
    Misturar faria uma lista de 244 linhas onde a de hoje tem poucas — e lista
    assim ninguem abre duas vezes."""
    con = _banco()
    assert [a["id"] for a in CPF.assentos_sem_cpf(con)] == [1]
    assert 2 in [a["id"] for a in CPF.assentos_sem_cpf(con, so_do_balcao=False)]
    con.close()


def test_so_nascimento_entra():
    con = _banco()
    assert 4 not in [a["id"] for a in CPF.assentos_sem_cpf(con)]
    con.close()


def test_gravar_confere_antes():
    """O numero vai para a certidao, e certidao com CPF errado e papel que o
    cliente leva e volta."""
    con = _banco()
    assert CPF.gravar(con, 1, "00000004502") == "000.000.045-02"
    with pytest.raises(CPF.CpfError):
        CPF.gravar(con, 1, "13672050343")
    con.close()


def test_gravado_sai_da_lista():
    con = _banco()
    CPF.gravar(con, 1, "00000004502")
    assert CPF.assentos_sem_cpf(con) == []
    con.close()


def test_a_coluna_esta_na_migracao():
    import rc_schema
    declaradas = {c for t, c, _ in rc_schema.MIGRACOES if t == "rc_assentos"}
    assert "cpf_registrado" in declaradas


# ------------------------------- o que a propria tela da CRC avisa
#
# Lido no print de `receitaFederal/gerarInscricao.cfm` em 30/08/2026.


def test_o_prazo_e_de_um_dia_util():
    """«No momento do registro (...) ou, na impossibilidade, no maximo no
    primeiro dia util posterior» — e prazo, e nao recomendacao."""
    assert CPF.PRAZO_DIAS_UTEIS == 1
    assert "primeiro dia útil" in CPF.QUANDO_SE_PODE
    assert "Livro A" in CPF.QUANDO_SE_PODE


def test_pedir_pelo_acervo_e_proibido_e_nao_so_inutil():
    """**Confirma de fora a decisao de deixar o acervo de fora.** A lista ja
    nascia so com os do balcao porque o CPF dos antigos e o mutirao do art.
    347; agora se sabe que pedir por eles **e proibido**, com penalidade."""
    assert CPF.ACERVO_E_PROIBIDO is True
    assert "expressamente proibido" in CPF.QUANDO_NAO_SE_PODE
    assert "lavrados anteriormente" in CPF.QUANDO_NAO_SE_PODE
    assert "transcri" in CPF.QUANDO_NAO_SE_PODE
    assert "penalidade" in CPF.PENALIDADE.lower()


def test_os_campos_estao_na_ordem_da_tela_da_CRC():
    """**A ordem importa**: quem preenche desce a tela de cima para baixo, e
    uma lista fora de ordem obriga a procurar cada campo. Medida no print."""
    d = CPF.dados_para_copiar(
        {"nome": "X", "data_fato": "2026-08-08", "data_ato": "2026-08-13",
         "matricula": "0" * 32, "numero": 1},
        [{"papel": "REGISTRADO", "sexo": "M"}], lugar={"livro_numero": 24,
                                                       "folha": 169})
    rotulos = [x["rotulo"] for x in d]
    assert rotulos[:6] == ["Nome da Criança", "Sexo", "Data de Nascimento",
                           "DNV", "Estado Naturalidade", "Cidade Naturalidade"]
    assert rotulos[6:11] == ["Livro", "Folha", "Número", "Data do Registro",
                             "Matrícula"]
    # a filiacao vem na etapa seguinte — o botao da tela diz «Avançar Formulario»
    assert "etapa seguinte" in rotulos[-1]


def test_a_matricula_vai_so_com_numeros():
    """A tela diz «(somente números)» ao lado do campo."""
    d = CPF.dados_para_copiar(
        {"nome": "X", "matricula": "000000 01 55 2026 1 00024 169 0019555 12"},
        [])
    m = [x for x in d if x["rotulo"] == "Matrícula"][0]
    assert m["valor"].isdigit() and len(m["valor"]) == 32


# ------------------------------------------ averbação do CPF (art. 347)


def test_texto_averbacao_monta_o_teor_e_confere():
    """O teor vai para `rc_atos` via RC.averbar — número inválido não entra.

    Forma curta do oficial: CPF (+ selo + data + usuario após selar).
    Fundamento art. 347 fica no campo separado do ato, não no teor.
    """
    t = CPF.texto_averbacao("00000004502")
    assert t == "Averbo neste assento o CPF n. 000.000.045-02."
    assert "art. 347" not in t
    assert "n.º" not in t
    with pytest.raises(CPF.CpfError):
        CPF.texto_averbacao("13672050343")


def test_texto_averbacao_completo_apos_selo():
    """Depois do selo: CPF. selo. data. usuario[, função]. — nessa ordem."""
    t = CPF.texto_averbacao(
        "000.000.015-97",
        selo="AVERBA000000WOGST2V2BKC6LG79",
        data="2026-09-08T10:02:59",
        usuario="Jean Santos")
    assert t == (
        "Averbo neste assento o CPF n. 000.000.015-97. "
        "AVERBA000000WOGST2V2BKC6LG79. 08/09/2026. Jean Santos.")
    t2 = CPF.texto_averbacao(
        "000.000.015-97",
        selo="AVERBA000000WOGST2V2BKC6LG79",
        data="2026-09-08T10:02:59",
        usuario="Jean Santos",
        funcao="Tabelião e Oficial de Registro")
    assert t2 == (
        "Averbo neste assento o CPF n. 000.000.015-97. "
        "AVERBA000000WOGST2V2BKC6LG79. 08/09/2026. "
        "Jean Santos, Tabelião e Oficial de Registro.")


def test_reescrever_teor_cpf_a_partir_do_antigo():
    antigo = ("Averbo neste assento o CPF n.º 000.000.015-97, na forma do "
              "art. 347 do Código de Normas do TJMA.\n"
              "Lavrado por: Jean Santos.")
    novo = CPF.reescrever_teor_cpf(
        antigo, selo="AVERBA000000WOGST2V2BKC6LG79",
        data="2026-09-08", usuario="Jean Santos")
    assert novo == (
        "Averbo neste assento o CPF n. 000.000.015-97. "
        "AVERBA000000WOGST2V2BKC6LG79. 08/09/2026. Jean Santos.")
    novo2 = CPF.reescrever_teor_cpf(
        antigo, selo="AVERBA000000WOGST2V2BKC6LG79",
        data="2026-09-08", usuario="Jean Santos",
        funcao="Tabelião e Oficial de Registro")
    assert novo2 == (
        "Averbo neste assento o CPF n. 000.000.015-97. "
        "AVERBA000000WOGST2V2BKC6LG79. 08/09/2026. "
        "Jean Santos, Tabelião e Oficial de Registro.")
    assert CPF.reescrever_teor_cpf("Averbação de retificação de grafia.") is None
    assert CPF.nome_usuario_teor("operador") == ""


def test_gravar_no_registrado_atualiza_documento():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE rc_pessoas (
            id INTEGER PRIMARY KEY, assento_id INTEGER, papel TEXT,
            nome TEXT, documento_tipo TEXT, documento_numero TEXT);
        INSERT INTO rc_pessoas VALUES (1, 1, 'REGISTRADO', 'X', NULL, NULL);
        INSERT INTO rc_pessoas VALUES (2, 1, 'MAE', 'Y', NULL, NULL);
    """)
    assert CPF.gravar_no_registrado(con, 1, "000.000.045-02") == "000.000.045-02"
    reg = con.execute(
        "SELECT documento_tipo, documento_numero FROM rc_pessoas "
        "WHERE papel='REGISTRADO'").fetchone()
    assert reg["documento_tipo"] == "CPF"
    assert reg["documento_numero"] == "00000004502"
    mae = con.execute(
        "SELECT documento_numero FROM rc_pessoas WHERE papel='MAE'").fetchone()
    assert mae["documento_numero"] is None
    con.close()


# ------------------- o casamento tem DOIS nubentes, e cada um o seu CPF


def _banco_do_casal():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE rc_pessoas (
            id INTEGER PRIMARY KEY, assento_id INTEGER, papel TEXT,
            nome TEXT, documento_tipo TEXT, documento_numero TEXT);
        INSERT INTO rc_pessoas VALUES
            (1, 1, 'NUBENTE1', 'JOÃO', NULL, NULL);
        INSERT INTO rc_pessoas VALUES
            (2, 1, 'NUBENTE2', 'MARIA', NULL, NULL);
    """)
    return con


def test_gravar_na_pessoa_alcanca_cada_nubente_separado():
    """O defeito relatado: `gravar_no_registrado` só sabia REGISTRADO, que
    não existe no casamento — os dois nubentes ficavam sem onde gravar."""
    con = _banco_do_casal()
    CPF.gravar_na_pessoa(con, 1, "000.000.045-02", papel="NUBENTE1")
    n1 = con.execute("SELECT documento_numero FROM rc_pessoas "
                     "WHERE papel='NUBENTE1'").fetchone()[0]
    n2 = con.execute("SELECT documento_numero FROM rc_pessoas "
                     "WHERE papel='NUBENTE2'").fetchone()[0]
    assert n1 == "00000004502"
    assert n2 is None            # o segundo nubente continua sem CPF

    CPF.gravar_na_pessoa(con, 1, "000.000.015-97", papel="NUBENTE2")
    n2 = con.execute("SELECT documento_numero FROM rc_pessoas "
                     "WHERE papel='NUBENTE2'").fetchone()[0]
    assert n2 == "00000001597"
    # ... e o primeiro continua com o dele, intacto.
    n1 = con.execute("SELECT documento_numero FROM rc_pessoas "
                     "WHERE papel='NUBENTE1'").fetchone()[0]
    assert n1 == "00000004502"


def test_principais_da_especie_tem_os_dois_nubentes_no_casamento():
    assert CPF.PRINCIPAIS_DA_ESPECIE["CASAMENTO"] == (
        ("NUBENTE1", "Primeiro nubente"), ("NUBENTE2", "Segundo nubente"))
    assert CPF.PRINCIPAIS_DA_ESPECIE["NASCIMENTO"] == (("REGISTRADO", ""),)
    assert CPF.PRINCIPAIS_DA_ESPECIE["OBITO"] == (("FALECIDO", ""),)


def test_texto_averbacao_diz_de_quem_e_o_cpf():
    """Pedido do oficial em 09/09/2026: «o texto precisa dizer qual cpf se
    refere a cada cônjuge»."""
    t = CPF.texto_averbacao("00000004502", nome="JOÃO DA SILVA",
                            papel_rotulo="Primeiro nubente")
    assert t == ("Averbo neste assento o CPF n. 000.000.045-02, referente "
                "ao primeiro nubente, JOÃO DA SILVA.")


def test_texto_averbacao_sem_nome_continua_igual_a_sempre():
    """Nascimento e óbito não mudam: só há um principal, e dizer «referente
    a» ali seria informação óbvia virando ruído no livro."""
    t = CPF.texto_averbacao("00000004502")
    assert t == "Averbo neste assento o CPF n. 000.000.045-02."


def test_texto_averbacao_com_papel_e_sem_nome_nao_inventa_pessoa():
    """Assento sem a linha da pessoa (papel existe, nome não) — não inventa
    nome, mas ainda diz de qual dos dois é o número."""
    t = CPF.texto_averbacao("00000004502", papel_rotulo="Segundo nubente")
    assert t == ("Averbo neste assento o CPF n. 000.000.045-02, referente "
                "ao segundo nubente.")


def test_reescrever_teor_cpf_preserva_o_referente_apos_o_selo():
    """O selo chega DEPOIS, e a sincronização reconstrói o teor do zero a
    cada vez — sem isto, ela apagaria «referente ao primeiro nubente, ...»
    assim que o selo saísse."""
    antes = CPF.texto_averbacao("00000004502", nome="JOÃO DA SILVA",
                                papel_rotulo="Primeiro nubente")
    depois = CPF.reescrever_teor_cpf(
        antes, selo="AVERBA000000ABCDEF", data="2026-09-09", usuario="Jean")
    assert depois == (
        "Averbo neste assento o CPF n. 000.000.045-02, referente ao "
        "primeiro nubente, JOÃO DA SILVA. AVERBA000000ABCDEF. "
        "09/09/2026. Jean.")


# ------------------------------------------- quem_falta_cpf, para a ficha


def test_quem_falta_cpf_no_casamento_traz_os_dois_nubentes_sem_cpf():
    pessoas = [{"papel": "NUBENTE1", "nome": "JOÃO"},
              {"papel": "NUBENTE2", "nome": "MARIA"}]
    falta = CPF.quem_falta_cpf(pessoas, "CASAMENTO")
    assert falta == [
        {"papel": "NUBENTE1", "rotulo": "Primeiro nubente", "nome": "JOÃO"},
        {"papel": "NUBENTE2", "rotulo": "Segundo nubente", "nome": "MARIA"}]


def test_quem_falta_cpf_no_casamento_tira_quem_ja_tem():
    pessoas = [{"papel": "NUBENTE1", "nome": "JOÃO",
               "documento_tipo": "CPF", "documento_numero": "1"},
              {"papel": "NUBENTE2", "nome": "MARIA"}]
    falta = CPF.quem_falta_cpf(pessoas, "CASAMENTO")
    assert falta == [
        {"papel": "NUBENTE2", "rotulo": "Segundo nubente", "nome": "MARIA"}]


def test_quem_falta_cpf_no_casamento_completo_e_lista_vazia():
    pessoas = [{"papel": "NUBENTE1", "nome": "JOÃO",
               "documento_tipo": "CPF", "documento_numero": "1"},
              {"papel": "NUBENTE2", "nome": "MARIA",
               "documento_tipo": "CPF", "documento_numero": "2"}]
    assert CPF.quem_falta_cpf(pessoas, "CASAMENTO") == []


def test_quem_falta_cpf_no_nascimento_e_um_item_sem_papel():
    """O formulário de sempre: um CPF só, sem pedir para escolher ninguém."""
    pessoas = [{"papel": "REGISTRADO", "nome": "ANA"}]
    falta = CPF.quem_falta_cpf(pessoas, "NASCIMENTO")
    assert falta == [{"papel": None, "rotulo": "", "nome": "ANA"}]


def test_quem_falta_cpf_no_nascimento_ja_no_assento_e_lista_vazia():
    pessoas = [{"papel": "REGISTRADO", "nome": "ANA"}]
    falta = CPF.quem_falta_cpf(pessoas, "NASCIMENTO", cpf_registrado="1")
    assert falta == []
