"""OS LIVROS DO RCPJ E DO RTD, as partes, os bens e a lista do que conferir (01/11/2026).

    «Não temos aba do livro de protocolo, nem nos demais livros obrigatórios.»
                                                       — o oficial, 01/11/2026

O QUE ESTES TESTES GUARDAM
    - cada atribuição tem as abas da lei: RTD de A a G, RCPJ com Protocolo, A, B e Índices;
    - o Protocolo traz o que o CN-MA art. 966 manda lançar e a referência do art. 968;
    - o termo do dia relaciona os pendentes com o motivo (art. 970), e o Protesto não muda;
    - o indicador acha pelo nome sem acento e pelo documento; parte retirada sai dele sem sumir;
    - o marcador «Apresentante» do acervo não vira pessoa;
    - o Livro F fica fora do Livro D (art. 957, § 5º) e aparece no Livro G;
    - a lista do que conferir lembra e não recusa;
    - a carga é repetível e não toma número.

Dados fictícios: Cidade Exemplo, CNS 000000.
"""
from __future__ import annotations

import ast
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
from banco_de_teste import conexao_de_teste  # noqa: E402

import acervo_carga as AC
import banco_pg
import escrituracao as ESC
import rg_livros as RGL
import rg_normas as NORMAS
import rg_registro as RG
import rg_schema as RGS
import rg_titulo as TIT
from bd_nativo import banco
from nucleo_schema import init_nucleo_schema

AGORA = "2026-11-01T09:30:00"
HOJE = "2026-11-01"
EXTENSO = "um de novembro de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO/MA",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA", "ri_cns": "000000",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro"}
CPF_FICTICIO = "00000000191"


@pytest.fixture()
def con(tmp_path):
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS cx_protocolos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT);
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT);
    """)
    RGS.init_rg_schema(c)
    return c


def _titulo(con, atribuicao=TIT.RTD, **kw) -> dict:
    padrao = {"atribuicao": atribuicao, "sv": SV, "agora": AGORA, "data_extenso": EXTENSO,
              "data_apresentacao": HOJE, "apresentante": "Maria Exemplo",
              "natureza": "Contrato de locação", "usuario": "mario"}
    padrao.update(kw)
    return TIT.receber(con, **padrao)


def _registro(con, serie="TD_B", atribuicao=TIT.RTD, numero=1, requerente="José Exemplo") -> int:
    linha = banco(con).escrever(
        """INSERT INTO rg_registros(atribuicao, serie, numero, requerente_nome, situacao, origem,
               origem_chave, criado_em)
           VALUES (%s,%s,%s,%s,'ATIVO','TESTE',%s,%s) RETURNING id""",
        (atribuicao, serie, numero, requerente, f"t:{serie}:{numero}", AGORA))
    return int(linha[0]["id"])


# ------------------------------------------------------------------ as abas


def test_o_rtd_tem_os_sete_livros_da_lei():
    assert [x["curto"] for x in RGL.livros_de(TIT.RTD)] == [
        "Livro A", "Livro B", "Auxiliar do B", "Livro C", "Livro D", "Livro E", "Livro F", "Livro G"]


def test_o_rcpj_tem_protocolo_livros_e_indices():
    assert [x["curto"] for x in RGL.livros_de(TIT.RCPJ)] == [
        "Protocolo", "Livro A", "Livro B", "Índices"]


def test_toda_aba_cita_a_fonte():
    for atribuicao in TIT.ATRIBUICOES:
        for livro in RGL.livros_de(atribuicao):
            assert "art." in livro["fonte"] or "arts." in livro["fonte"], livro["chave"]


def test_aba_que_nao_existe_abre_o_protocolo():
    assert RGL.livro_pedido(TIT.RTD, "z")["tipo"] == RGL.PROTOCOLO


# --------------------------------------------------------------- o protocolo


def test_o_protocolo_traz_as_colunas_do_art_966(con):
    feito = _titulo(con, especie_lancamento="EXTRATO")
    linha = RGL.linhas_do_protocolo(con, TIT.RTD)[0]
    assert linha["numero"] == feito["numero_ordem"]
    assert linha["data_apresentacao"] == HOJE
    assert linha["natureza"] == "Contrato de locação"
    assert linha["especie_rotulo"] == "Registro por extrato"
    assert linha["apresentante"] == "Maria Exemplo"


def test_as_atribuicoes_nao_se_misturam_no_protocolo(con):
    _titulo(con, atribuicao=TIT.RCPJ)
    assert RGL.linhas_do_protocolo(con, TIT.RTD) == []


def test_especie_desconhecida_e_recusada(con):
    with pytest.raises(TIT.TituloError):
        _titulo(con, especie_lancamento="QUALQUER")


def test_atualizar_sem_os_campos_novos_nao_os_apaga(con):
    feito = _titulo(con, previsao_entrega="2026-11-10", especie_lancamento="INTEGRAL")
    TIT.atualizar(con, feito["titulo_id"], apresentante="Outra Exemplo")
    t = TIT.um(con, feito["titulo_id"])
    assert t["previsao_entrega"] == "2026-11-10"
    assert t["especie_lancamento"] == "INTEGRAL"


def test_a_anotacao_do_titulo_segue_o_art_966(con):
    feito = _titulo(con, especie_lancamento="AVERBACAO")
    texto = RGL.anotacao_no_titulo(TIT.um(con, feito["titulo_id"]))
    assert texto == f"Protocolizado em 01/11/2026 sob n. {feito['numero_ordem']}, para averbação."


# ------------------------------------------------------- o termo do dia


def test_o_termo_do_dia_relaciona_os_pendentes_com_o_motivo(con):
    feito = _titulo(con)
    r = ESC.encerrar_o_dia(con, "TD_PROTOCOLO", HOJE, sv=SV, agora=AGORA, dia_extenso=EXTENSO)
    teor = banco(con).valor("SELECT teor FROM nu_encerramentos_diarios WHERE serie='TD_PROTOCOLO'")
    assert r["quantidade"] == 1
    assert f"n. {feito['numero_ordem']} (aguarda qualificação)" in teor


def test_o_termo_diz_quando_nao_ha_pendente(con):
    assert "Não há título" in RGL.frase_dos_pendentes(con, "PJ_PROTOCOLO", HOJE)


def test_o_protesto_nao_ganha_a_frase_do_rtd(con):
    assert RGL.frase_dos_pendentes(con, "PT_PROTOCOLO", HOJE) == ""


def test_titulo_encerrado_nao_fica_pendente(con):
    feito = _titulo(con)
    TIT.encerrar(con, feito["titulo_id"], situacao=TIT.CANCELADO,
                 motivo="Desistência do apresentante.", agora=AGORA, usuario="mario")
    assert RGL.pendentes_ao_fim_do_dia(con, TIT.RTD, HOJE) == []


# ------------------------------------------------- o termo de um dia passado

D1, D2, D3, D4 = "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"


def _pendentes(con, dia):
    return {p["numero"]: p["motivo"] for p in RGL.pendentes_ao_fim_do_dia(con, TIT.RTD, dia)}


def _registrado_em(con, feito, dia, serie="TD_B"):
    """O título que virou registro naquele dia: o ato é o que diz quando ele saiu."""
    bd = banco(con)
    r = _registro(con, serie=serie, numero=feito["titulo_id"] + 100)
    bd.escrever("UPDATE rg_registros SET titulo_id=%s WHERE id=%s", (feito["titulo_id"], r))
    bd.escrever("INSERT INTO rg_atos(registro_id, tipo, data_ato, origem, origem_chave, criado_em) "
                "VALUES (%s,'REGISTRO',%s,'TESTE',%s,%s)", (r, dia, f"a:{r}", AGORA))
    bd.escrever("UPDATE rg_titulos SET situacao=%s, registro_id=%s WHERE id=%s",
                (TIT.REGISTRADO, r, feito["titulo_id"]))


def test_o_termo_de_um_dia_passado_ve_o_titulo_que_foi_registrado_depois(con):
    """Era o defeito: registrado hoje, sumia do termo de ontem, e o livro dizia que não havia pendência."""
    feito = _titulo(con, data_apresentacao=D1)
    _registrado_em(con, feito, D3)
    assert _pendentes(con, D1) == {feito["numero_ordem"]: "aguarda qualificação"}
    assert _pendentes(con, D2) == {feito["numero_ordem"]: "aguarda qualificação"}
    assert _pendentes(con, D3) == {}, "no dia do registro ele já saiu"
    assert "n. " in RGL.frase_dos_pendentes(con, "TD_PROTOCOLO", D2)
    assert "Não há título" in RGL.frase_dos_pendentes(con, "TD_PROTOCOLO", D3)


def test_o_motivo_e_o_daquele_dia_e_nao_o_de_hoje(con):
    feito = _titulo(con, data_apresentacao=D1)
    tid, numero = feito["titulo_id"], feito["numero_ordem"]
    TIT.qualificar(con, tid, resultado=TIT.NEGATIVA, exigencias="Trazer o original assinado.", prazo_ate=D4,
                   data_qualificacao=D2, agora=AGORA, usuario="mario")
    TIT.qualificar(con, tid, resultado=TIT.POSITIVA, data_qualificacao=D3, agora=AGORA, usuario="mario")
    assert _pendentes(con, D1)[numero] == "aguarda qualificação"
    assert _pendentes(con, D2)[numero] == "com exigência: Trazer o original assinado."
    assert _pendentes(con, D3)[numero] == "qualificado, aguarda a lavratura"
    assert RGL.motivo_da_pendencia(con, TIT.um(con, tid)) == "qualificado, aguarda a lavratura"


def test_o_titulo_devolvido_saiu_no_dia_em_que_foi_devolvido(con):
    feito = _titulo(con, data_apresentacao=D1)
    TIT.encerrar(con, feito["titulo_id"], situacao=TIT.DEVOLVIDO, motivo="Devolvido a pedido do apresentante.",
                 agora=f"{D3}T10:00:00", usuario="mario")
    assert feito["numero_ordem"] in _pendentes(con, D2)
    assert _pendentes(con, D3) == {}


def test_o_sobrestamento_so_explica_os_dias_em_que_valeu(con):
    feito = _titulo(con, data_apresentacao=D1)
    tid, numero = feito["titulo_id"], feito["numero_ordem"]
    tipo = next(iter(TIT.SOBRESTAR_POR))
    TIT.sobrestar(con, tid, tipo=tipo, motivo="Sobrestado por ordem de ensaio.", agora=f"{D2}T10:00:00", usuario="mario")
    assert _pendentes(con, D1)[numero] == "aguarda qualificação"
    assert _pendentes(con, D2)[numero].startswith("sobrestado")
    TIT.retomar(con, tid, forma=next(iter(TIT.RETOMAR_POR)), motivo="Retomado por requerimento no ensaio.",
                agora=f"{D3}T10:00:00", usuario="mario")
    assert _pendentes(con, D2)[numero].startswith("sobrestado"), "o fim não apaga o que valeu"
    assert _pendentes(con, D3)[numero] == "aguarda qualificação"


def test_titulo_antigo_sem_dia_de_saida_nao_entra_como_pendente(con):
    """O título do acervo é memória: sem ato nem dia gravado, o termo não afirma que ele estava pendente."""
    feito = _titulo(con, data_apresentacao=D1)
    banco(con).escrever("UPDATE rg_titulos SET situacao=%s WHERE id=%s", (TIT.REGISTRADO, feito["titulo_id"]))
    assert _pendentes(con, D2) == {}
    banco(con).escrever("UPDATE rg_titulos SET situacao=%s WHERE id=%s", (TIT.CANCELADO, feito["titulo_id"]))
    assert _pendentes(con, D2) == {}


def test_o_ato_antigo_do_registro_nao_diz_quando_o_titulo_de_averbacao_saiu(con):
    feito = _titulo(con, data_apresentacao=D2)
    bd = banco(con)
    r = _registro(con, numero=148)
    bd.escrever("INSERT INTO rg_atos(registro_id, tipo, data_ato, origem, origem_chave, criado_em) "
                "VALUES (%s,'REGISTRO','2020-01-01','TESTE','a:antigo',%s)", (r, AGORA))
    bd.escrever("INSERT INTO rg_atos(registro_id, tipo, data_ato, origem, origem_chave, criado_em) "
                "VALUES (%s,'AVERBACAO',%s,'TESTE','a:novo',%s)", (r, D4, AGORA))
    bd.escrever("UPDATE rg_titulos SET situacao=%s, registro_id=%s WHERE id=%s", (TIT.REGISTRADO, r, feito["titulo_id"]))
    assert feito["numero_ordem"] in _pendentes(con, D3)
    assert _pendentes(con, D4) == {}


# ------------------------------------------------------- a busca dos livros de atos


def test_a_busca_nas_abas_de_atos_ignora_acento_e_caixa(con):
    r = _registro(con, requerente="João da Conceição")
    banco(con).escrever("INSERT INTO rg_atos(registro_id, tipo, data_ato, origem, origem_chave, criado_em) "
                        "VALUES (%s,'REGISTRO',%s,'TESTE','a:busca',%s)", (r, D1, AGORA))
    for procura in ("Joao", "JOÃO", "conceicao"):
        assert RGL.atos_do_livro(con, "TD_B", busca=procura)["total"] == 1, procura
    assert RGL.atos_do_livro(con, "TD_B", busca="Maria")["total"] == 0


# ------------------------------------------------------- o documento na tela


def test_o_documento_sai_como_se_le():
    assert RGL.documento_na_tela("00000000191") == "000.000.001-91"
    assert RGL.documento_na_tela(None) == "" and RGL.documento_na_tela("") == ""


# -------------------------------------------------------------- os indicadores


def test_o_requerente_entra_no_indicador_sem_parte_detalhada(con):
    _registro(con)
    assert [x["nome"] for x in RGL.indicador_pessoal(con, atribuicao=TIT.RTD)] == ["José Exemplo"]


def test_o_marcador_apresentante_nao_vira_pessoa(con):
    _registro(con, requerente="Apresentante")
    assert RGL.indicador_pessoal(con, atribuicao=TIT.RTD) == []


def test_acha_pelo_nome_sem_acento_e_pelo_documento(con):
    r = _registro(con)
    RGL.incluir_parte(con, r, nome="Conceição Exemplo", documento=CPF_FICTICIO, papel="Cônjuge",
                      agora=AGORA, usuario="mario")
    assert [x["papel"] for x in RGL.indicador_pessoal(con, busca="conceicao")] == ["Cônjuge"]
    assert [x["nome"] for x in RGL.indicador_pessoal(con, busca="000.000.001-91")] == ["Conceição Exemplo"]


def test_documento_invalido_e_recusado(con):
    r = _registro(con)
    with pytest.raises(RGL.LivroDoRegistroError):
        RGL.incluir_parte(con, r, nome="Exemplo", documento="11111111112", agora=AGORA)


def test_a_mesma_pessoa_com_o_mesmo_papel_nao_entra_duas_vezes(con):
    r = _registro(con)
    RGL.incluir_parte(con, r, nome="Ana Exemplo", papel="Credor", agora=AGORA)
    with pytest.raises(RGL.LivroDoRegistroError):
        RGL.incluir_parte(con, r, nome="ANA EXEMPLO", papel="Credor", agora=AGORA)


def test_retirar_exige_motivo_sai_do_indicador_e_a_linha_fica(con):
    r = _registro(con, requerente="Apresentante")
    p = RGL.incluir_parte(con, r, nome="Ana Exemplo", agora=AGORA)["parte_id"]
    with pytest.raises(RGL.LivroDoRegistroError):
        RGL.retirar_parte(con, r, p, motivo="curto", agora=AGORA)
    RGL.retirar_parte(con, r, p, motivo="Lançada no registro errado.", agora=AGORA, usuario="mario")
    assert RGL.indicador_pessoal(con, atribuicao=TIT.RTD) == []
    assert RGL.partes_do_registro(con, r)[0]["retirada_motivo"] == "Lançada no registro errado."


def test_o_livro_f_fica_fora_do_d_e_aparece_no_g(con):
    _registro(con, serie="TD_F", requerente="Quem Conserva")
    _registro(con, serie="TD_B", numero=2, requerente="Quem Registra")
    d = RGL.indicador_pessoal(con, atribuicao=TIT.RTD, series=("TD_B", "TD_C"))
    g = RGL.indicador_pessoal(con, series=("TD_F",))
    assert [x["nome"] for x in d] == ["Quem Registra"]
    assert [x["nome"] for x in g] == ["Quem Conserva"]


def test_o_livro_e_e_so_do_rtd_e_a_baixa_nao_apaga(con):
    pj = _registro(con, serie="PJ_A", atribuicao=TIT.RCPJ)
    with pytest.raises(RGL.LivroDoRegistroError):
        RGL.incluir_bem(con, pj, descricao="Veículo exemplo", agora=AGORA)
    td = _registro(con)
    b = RGL.incluir_bem(con, td, descricao="Veículo exemplo", identificacao="CHASSI000",
                        onus="Alienação fiduciária", agora=AGORA)["bem_id"]
    assert RGL.indicador_real(con, busca="chassi000")[0]["numero"] == 1
    RGL.baixar_bem(con, td, b, motivo="Quitação averbada no registro.", agora=AGORA)
    assert RGL.indicador_real(con)[0]["baixa_motivo"] == "Quitação averbada no registro."


def test_a_ordem_cronologica_poe_o_mais_novo_em_cima(con):
    for numero, nome, dia in ((1, "Zé Antigo", "2020-01-01"), (2, "Ana Nova", "2026-01-01")):
        r = _registro(con, numero=numero, requerente=nome)
        banco(con).escrever(
            "INSERT INTO rg_atos(registro_id, tipo, data_ato, origem, origem_chave, criado_em) "
            "VALUES (%s,'REGISTRO',%s,'TESTE',%s,%s)", (r, dia, f"a:{numero}", AGORA))
    assert RGL.indicador_pessoal(con, ordem="cronologica")[0]["nome"] == "Ana Nova"
    assert RGL.indicador_pessoal(con, ordem="alfabetica")[0]["nome"] == "Ana Nova"
    assert RGL.indicador_pessoal(con, ordem="alfabetica")[1]["nome"] == "Zé Antigo"


# ------------------------------------------------------------------- a norma


def test_a_natureza_puxa_a_regra_da_atribuicao_dela():
    assert [r["artigo"] for r in NORMAS.para_a_natureza(TIT.RCPJ, "Estatuto de COOPERATIVA")] == [
        "CN-MA art. 407, I"]
    assert NORMAS.para_a_natureza(TIT.RTD, "Estatuto de cooperativa") == []
    assert NORMAS.para_a_natureza(TIT.RTD, None) == []


def test_a_palavra_reservada_acha_sem_acento_e_inteira():
    assert NORMAS.avisos_do_nome("Associação do Cartório Velho") == ["cartorio"]
    assert NORMAS.avisos_do_nome("Oficina Exemplo") == []


def test_o_nome_igual_acha_o_outro_e_nao_a_si_mesmo(con):
    a = _registro(con, serie="PJ_A", atribuicao=TIT.RCPJ, requerente="Associação Exemplo")
    b = _registro(con, serie="PJ_A", atribuicao=TIT.RCPJ, numero=2, requerente="ASSOCIACAO EXEMPLO")
    assert [x["id"] for x in NORMAS.nomes_parecidos(con, "Associação Exemplo", registro_id=a)] == [b]


def test_a_lista_lembra_e_nao_recusa():
    """Alerta não é trava: nenhum nome público do módulo promete barrar título."""
    arvore = ast.parse((RAIZ / "rg_normas.py").read_text(encoding="utf-8"))
    nomes = [n.name for n in arvore.body if isinstance(n, ast.FunctionDef)]
    assert not [n for n in nomes if any(p in n for p in ("recusar", "bloquear", "impedir", "travar"))]


# ------------------------------------------------------------------- a carga


def _acervo():
    a = getattr(banco_pg, "_CONNECT_ORIGINAL", sqlite3.connect)(":memory:")
    a.row_factory = sqlite3.Row
    a.executescript("""
        CREATE TABLE tbRegistroTD(intChave, strTipoRegistro, intNumeroRegistro, intProtocolo, dtmData,
            strApresentante, strTipoInscricaoMatricula, strProtocoloGeral);
        CREATE TABLE tbTD_Partes(intChave, strTD_PJ, intNumeroRegistro, intQualificacao, intCodigoParte);
        CREATE TABLE tbOrtoga(intCodigo, strTipoPessoa, strNome, PJ_RazaoSocial, strCPF, strCNPJ);
        CREATE TABLE tbQualificacaoPartes(intChave, strDescricao);
        CREATE TABLE tbTD_Propriedade(intProtocolo_RTD, intProtocolo_RPJ);
        INSERT INTO tbRegistroTD VALUES (1,'TD',8,1475,'2022-12-15 00:00:00','Apresentante','Contrato','2022.12.140');
        INSERT INTO tbRegistroTD VALUES (2,'PJ',321,1448,'2020-05-18 00:00:00','Associação Exemplo','Estatuto',NULL);
        INSERT INTO tbTD_Partes VALUES (1,'TD',8,76,10);
        INSERT INTO tbOrtoga VALUES (10,'F','Ana Exemplo',NULL,'00000000191','');
        INSERT INTO tbQualificacaoPartes VALUES (76,'OUTORGADO');
        INSERT INTO tbTD_Propriedade VALUES (1275,1273);
    """)
    return a


def _registros_do_acervo(con):
    for chave, atrib, serie, numero in ((1, 4, "TD_B", 8), (2, 3, "PJ_A", 321)):
        banco(con).escrever(
            """INSERT INTO rg_registros(atribuicao, serie, numero, situacao, origem, origem_chave, criado_em)
               VALUES (%s,%s,%s,'ATIVO','EOFICIO',%s,%s)""",
            (atrib, serie, numero, f"tbRegistroTD:{chave}", AGORA))


def test_a_carga_e_repetivel_e_nao_toma_numero(con):
    _registros_do_acervo(con)
    acervo = _acervo()
    primeira = AC.carregar_rcpj_rtd_livros(con, acervo, agora=AGORA)
    assert primeira.inseridos == 2
    assert primeira.contagens["partes no indicador"] == 1
    segunda = AC.carregar_rcpj_rtd_livros(con, acervo, agora=AGORA)
    assert segunda.inseridos == 0
    assert segunda.repetidos == 2
    bd = banco(con)
    assert bd.valor("SELECT COUNT(*) n FROM rg_titulos") == 2
    assert bd.valor("SELECT COUNT(*) n FROM rg_partes") == 1
    assert bd.valor("SELECT COUNT(*) n FROM nu_lugares") == 0
    linha = RGL.linhas_do_protocolo(con, TIT.RTD)[0]
    assert (linha["numero"], linha["situacao"], linha["apresentante"]) == (1475, "REGISTRADO", None)


def test_a_carga_nao_inventa_a_data_da_apresentacao(con):
    _registros_do_acervo(con)
    acervo = _acervo()
    acervo.execute("UPDATE tbRegistroTD SET dtmData=NULL WHERE intChave=1")
    carga = AC.carregar_rcpj_rtd_livros(con, acervo, agora=AGORA)
    assert carga.inseridos == 1 and len(carga.rejeitados) == 1
    assert banco(con).valor("SELECT COUNT(*) n FROM rg_titulos WHERE data_apresentacao=%s", (AGORA[:10],)) == 0
    # O registro sem data continua com as partes: elas não dependem do Protocolo.
    assert carga.contagens["partes no indicador"] == 1


def test_a_carga_esta_nas_duas_listas():
    assert "rcpj_rtd_livros" in AC.CARGAS and "rcpj_rtd_livros" in AC.TITULO_DA_CARGA
