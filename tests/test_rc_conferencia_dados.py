"""A conferência dos dados do assento do RCPN — e as duas travas que ela arma.

    «verifique se essas importacoes estao perfeitas e, nao sendo, vamos criar
     mecanismos que orientem e bloqueiem introducoes deficitarias ou erradas»
    — o oficial, 11/10/2026

O QUE ESTES TESTES GUARDAM, e cada um é um defeito medido na produção:

    **A testemunha que é o próprio registrado trava a lavratura** — 6 dos 19
    assentos lavrados desde 10/09/2026 tinham essa linha.
    **O traço de quem assina no meio da frase trava; a linha de assinatura do
    acervo, não** — 8 termos foram ao livro com «Eu, ____________, Oficial».
    **CPF que não fecha o dígito trava.**
    **O par mãe/pai invertido trava; um só divergente avisa** (dupla
    maternidade/paternidade existe).
    **A trava mora em `lavrar_assento`**, e por isso pega o robô que lavra por
    script — e nada fica pela metade quando ela recusa.
    **O termo lavrado e selado nesta casa não se corrige pela ficha**; o
    cadastro das pessoas e o acervo continuam corrigíveis.
    **O rascunho volta com a conferência**, sem recusar.

Os nomes são fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_assento as RC                          # noqa: E402
import rc_conferencia_dados as CD                # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from rc_schema import init_rc_schema             # noqa: E402

AGORA = "2026-10-09T10:00:00"
EXTENSO = "nove dias do mês de outubro do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}
CPF_BOM = "52998224725"          # fecha o dígito
CPF_RUIM = "52998224700"

TEOR = ("Aos nove dias de outubro de 2026, compareceu MARIA EXEMPLO DA SILVA, "
        "apresentou a DNV n.º 30-12345678-9, e declarou que no dia 01/10/2026, às "
        "08:46, nasceu uma criança do sexo Masculino, que recebeu o nome de: "
        "\"João Exemplo da Silva\", sendo filho de MARIA EXEMPLO DA SILVA e de "
        "JOSÉ EXEMPLO DA SILVA. Lido e achado conforme, o(a) declarante assina. "
        "Eu, Fulana de Tal, Escrevente Autorizada, dou fé e assino.")


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rc_schema(con)
    return con


def pessoas(**troca):
    base = [
        {"papel": "REGISTRADO", "nome": "JOÃO EXEMPLO DA SILVA", "sexo": "M"},
        {"papel": "MAE", "nome": "MARIA EXEMPLO DA SILVA", "sexo": "F"},
        {"papel": "PAI", "nome": "JOSÉ EXEMPLO DA SILVA", "sexo": "M"},
        {"papel": "DECLARANTE", "nome": "MARIA EXEMPLO DA SILVA", "sexo": "F"},
    ]
    return base + troca.get("mais", [])


def lavrar(con, teor=TEOR, gente=None, dnv="30-12345678-9", hora="08:46"):
    return RC.lavrar_assento(
        con, especie="NASCIMENTO", nome="JOÃO EXEMPLO DA SILVA", sv=SV,
        agora=AGORA, data_extenso=EXTENSO, data_fato="2026-10-01",
        dados={"sexo": "M"}, teor=teor,
        # «Onde nasceu» (1 = hospital): o SIRC exige, e desde o relato #130
        # (14/10/2026) a lavratura também.
        ibge={"dnv": dnv, "local_nascimento": 1},
        termo_dados={"local_fato_nome": "Hospital Municipal", "hora_fato": hora},
        pessoas=gente if gente is not None else pessoas())


def codigos(probs, gravidade=None):
    return sorted(p["codigo"] for p in probs if gravidade in (None, p["gravidade"]))


def dados(**k):
    d = {"especie": "NASCIMENTO", "nome": "JOÃO EXEMPLO DA SILVA",
         "data_fato": "2026-10-01", "data_ato": AGORA, "teor": TEOR,
         "dnv": "30-12345678-9", "hora_fato": "08:46", "pessoas": pessoas()}
    d.update(k)
    return d


# ------------------------------------------------------------------ a régua

def test_assento_limpo_nao_tem_apontamento():
    assert CD.conferir(dados()) == []


def test_traco_de_quem_assina_trava_e_linha_de_assinatura_nao():
    com_traco = TEOR.replace("Eu, Fulana de Tal, Escrevente Autorizada",
                             "Eu, ____________, Oficial")
    assert codigos(CD.conferir(dados(teor=com_traco)), "BLOQUEIA") == ["MARCA_DE_RASCUNHO"]
    linha = TEOR + "\nEm testemunho da verdade.\n______________________"
    assert CD.conferir(dados(teor=linha)) == []


def test_marca_a_confirmar_trava():
    t = TEOR.replace("Masculino", "Masculino [A CONFIRMAR: sexo]")
    assert "MARCA_DE_RASCUNHO" in codigos(CD.conferir(dados(teor=t)), "BLOQUEIA")


def test_testemunha_que_e_o_registrado_trava_e_genitor_avisa():
    fantasma = pessoas(mais=[{"papel": "TESTEMUNHA", "nome": "João Exemplo da Silva"}])
    assert codigos(CD.conferir(dados(pessoas=fantasma)), "BLOQUEIA") == ["TESTEMUNHA_FANTASMA"]
    mae = pessoas(mais=[{"papel": "TESTEMUNHA", "nome": "MARIA EXEMPLO DA SILVA"}])
    assert codigos(CD.conferir(dados(pessoas=mae)), "AVISA") == ["TESTEMUNHA_FANTASMA"]


def test_par_invertido_trava_e_um_so_avisa():
    gente = pessoas()
    gente[1]["sexo"], gente[2]["sexo"] = "M", "F"
    assert codigos(CD.conferir(dados(pessoas=gente)), "BLOQUEIA") == ["SEXO_DO_PAPEL"]
    gente = pessoas()
    gente[2]["sexo"] = "F"                                  # dupla maternidade
    p = CD.conferir(dados(pessoas=gente))
    assert codigos(p, "BLOQUEIA") == [] and codigos(p, "AVISA") == ["SEXO_DO_PAPEL"]


def test_cpf_que_nao_fecha_trava():
    gente = pessoas()
    gente[1].update(documento_tipo="CPF", documento_numero=CPF_RUIM)
    assert codigos(CD.conferir(dados(pessoas=gente)), "BLOQUEIA") == ["CPF_INVALIDO"]
    gente[1]["documento_numero"] = CPF_BOM
    assert CD.conferir(dados(pessoas=gente)) == []


def test_dnv_e_hora_do_campo_contra_o_termo():
    p = CD.conferir(dados(dnv="30-99999999-9", hora_fato="09:10"))
    assert codigos(p, "BLOQUEIA") == ["DNV_DIFERENTE", "HORA_DIFERENTE"]


def test_nome_com_apostrofo_diferente_continua_achado():
    t = TEOR.replace("João Exemplo da Silva", "João Xu’Exemplo da Silva")
    p = CD.conferir(dados(teor=t, nome="JOÃO XU'EXEMPLO DA SILVA"))
    assert "NOME_FORA_DO_TERMO" not in codigos(p)


def test_avo_do_outro_lado_so_avisa():
    gente = pessoas(mais=[{"papel": "AVO_MATERNO", "nome": "PEDRO EXEMPLO",
                           "sexo": "M"}])
    gente[1]["nome"] = "MARIA SOUZA LIMA"
    gente[2]["nome"] = "JOSÉ PEREIRA EXEMPLO"
    gente[3]["nome"] = "MARIA SOUZA LIMA"
    t = TEOR.replace("MARIA EXEMPLO DA SILVA", "MARIA SOUZA LIMA").replace(
        "JOSÉ EXEMPLO DA SILVA", "JOSÉ PEREIRA EXEMPLO") + " Avô PEDRO EXEMPLO."
    p = CD.conferir(dados(pessoas=gente, teor=t))
    assert codigos(p, "BLOQUEIA") == [] and "AVO_DO_OUTRO_LADO" in codigos(p, "AVISA")


def test_formulario_ignora_gaveta_so_com_tipo_de_documento():
    valores = {"especie": "NASCIMENTO", "pessoa_nome": "JOÃO EXEMPLO DA SILVA",
               "testemunha_documento_tipo": "CPF", "filiacao1_nome": "MARIA X"}
    d = CD.dados_do_formulario(valores)
    assert sorted(p["papel"] for p in d["pessoas"]) == ["MAE", "REGISTRADO"]
    assert "TESTEMUNHA" not in [p["papel"] for p in d["pessoas"]]


def test_rascunho_sem_saber_quem_assina_nao_e_acusado():
    v = {"especie": "NASCIMENTO", "pessoa_nome": "JOÃO EXEMPLO DA SILVA",
         "teor": TEOR.replace("Eu, Fulana de Tal, Escrevente Autorizada",
                              "Eu, ____________, Oficial")}
    assert "MARCA_DE_RASCUNHO" not in codigos(
        CD.conferir(CD.dados_do_formulario(v, assina_depois=True)))
    assert "MARCA_DE_RASCUNHO" in codigos(CD.conferir(CD.dados_do_formulario(v)))


# ------------------------------------------------------- a trava da lavratura

def test_lavratura_limpa_passa_e_devolve_os_avisos():
    con = banco()
    r = lavrar(con)
    assert r["assento_id"] and r["avisos_da_conferencia"] == []


def test_lavratura_com_testemunha_fantasma_e_recusada_e_nada_fica():
    con = banco()
    gente = pessoas(mais=[{"papel": "TESTEMUNHA", "nome": "JOÃO EXEMPLO DA SILVA"}])
    con.execute("SAVEPOINT x")
    with pytest.raises(RC.RcError, match="testemunha"):
        lavrar(con, gente=gente)
    con.execute("ROLLBACK TO x")
    assert con.execute("SELECT count(*) FROM rc_assentos").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM rc_pessoas").fetchone()[0] == 0


def test_lavratura_com_marca_de_rascunho_e_recusada():
    con = banco()
    with pytest.raises(RC.RcError, match="marca de rascunho"):
        lavrar(con, teor=TEOR.replace("Masculino", "Masculino [A CONFIRMAR]"))


def test_carga_do_acervo_nao_passa_pela_trava():
    con = banco()
    r = RC.lavrar_assento(
        con, especie="NASCIMENTO", nome="JOÃO EXEMPLO DA SILVA", sv=SV,
        agora=AGORA, data_extenso=EXTENSO, data_fato="1990-01-01",
        teor="Eu, ____________, Oficial", origem="ARQUIVO", origem_chave="x:1",
        pessoas=pessoas(mais=[{"papel": "TESTEMUNHA", "nome": "JOÃO EXEMPLO DA SILVA"}]))
    assert r["assento_id"]


# ------------------------------------------------ a trava da correção por ficha

def _selar(con, assento_id):
    con.execute("UPDATE rc_atos SET selo='SELOTESTE0000000000000000001' "
                "WHERE assento_id=? AND tipo='REGISTRO'", (assento_id,))


def test_termo_lavrado_e_selado_nao_se_corrige_pela_ficha():
    con = banco()
    aid = lavrar(con)["assento_id"]
    _selar(con, aid)
    with pytest.raises(RC.RcError, match="lavrado e selado nesta casa"):
        RC.corrigir_informacoes(con, aid, motivo="corrigindo o termo à mão",
                                agora=AGORA, teor=TEOR + " Acréscimo.")
    with pytest.raises(RC.RcError, match="número do termo"):
        RC.corrigir_informacoes(con, aid, motivo="trocando o número do termo",
                                agora=AGORA, numero=999)


def test_sem_selo_ainda_se_corrige_e_o_interruptor_desliga():
    con = banco()
    aid = lavrar(con)["assento_id"]
    RC.corrigir_informacoes(con, aid, motivo="ainda sem selo, corrige",
                            agora=AGORA, teor=TEOR + " Um.")
    _selar(con, aid)
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO settings VALUES (?, 'DESLIGADO')", (RC.CHAVE_TERMO_TRANCADO,))
    RC.corrigir_informacoes(con, aid, motivo="o oficial desligou a trava",
                            agora=AGORA, teor=TEOR + " Dois.")


def test_acervo_continua_corrigivel():
    con = banco()
    r = RC.lavrar_assento(
        con, especie="NASCIMENTO", nome="JOÃO EXEMPLO DA SILVA", sv=SV,
        agora=AGORA, data_extenso=EXTENSO, data_fato="1990-01-01",
        teor="texto do acervo", origem="EOFICIO", origem_chave="e:1")
    _selar(con, r["assento_id"])
    RC.corrigir_informacoes(con, r["assento_id"], motivo="transcrição do acervo",
                            agora=AGORA, teor="texto do acervo, corrigido")


# --------------------------------------------------------------- o rascunho

def test_rascunho_volta_com_a_conferencia_e_nao_recusa():
    import rascunho_de_tela as R
    con = banco()
    R.init_rascunho_schema(con)
    v = {"especie": "NASCIMENTO", "pessoa_nome": "JOÃO EXEMPLO DA SILVA",
         "pessoa_sexo": "M", "filiacao1_nome": "MARIA EXEMPLO", "filiacao1_sexo": "M",
         "filiacao2_nome": "JOSÉ EXEMPLO", "filiacao2_sexo": "F",
         "testemunha_nome": "JOÃO EXEMPLO DA SILVA"}
    r = R.salvar(con, tela="rcpn_assento_novo", dados=v, titulo="t", agora=AGORA)
    assert r["id"]
    assert {"SEXO_DO_PAPEL", "TESTEMUNHA_FANTASMA"} <= set(codigos(r["conferencia"], "BLOQUEIA"))


# ------------------------------------------------ arrumar só o que travou

def test_campos_para_corrigir_abrem_so_o_que_resolve():
    gente = pessoas()
    gente[1]["sexo"], gente[2]["sexo"] = "M", "F"
    gente[1].update(documento_tipo="CPF", documento_numero=CPF_RUIM)
    t = TEOR.replace("Masculino", "Masculino [A CONFIRMAR]")
    campos = [c["campo"] for c in CD.campos_para_corrigir(
        CD.conferir(dados(pessoas=gente, teor=t)))]
    assert set(campos) == {"teor", "filiacao1_sexo", "filiacao2_sexo",
                           "filiacao1_documento_numero"}
    # o que só avisa não abre campo
    assert CD.campos_para_corrigir([{"gravidade": "AVISA", "codigo": "IDADE_NAO_BATE",
                                     "mensagem": "x", "campo": "MAE"}]) == []
