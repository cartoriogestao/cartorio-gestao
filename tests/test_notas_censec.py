"""
Testes da remessa as centrais da CENSEC.

COMO ESTES TESTES RODAM
    Com PRAGMA foreign_keys ligado, como a producao. A importacao da tabela de
    emolumentos ja quebrou em producao passando no teste justamente porque o
    SQLite desliga a trava por padrao e a producao a liga.

O QUE ELES CONFEREM
    Menos "a funcao devolveu alguma coisa" e mais "o que ela devolveu bate com
    o layout". Teste que verifica se o arquivo foi criado nao verifica se o
    documento esta certo.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import notas_censec as NC          # noqa: E402
from notas_schema import init_notas_schema   # noqa: E402


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")      # como a producao
    init_notas_schema(con)
    return con


# ------------------------------------------------------------- quinzena

def test_quinzena_pela_data_do_ato():
    assert NC.quinzena_de("2026-06-15") == (2026, 6, 1)
    assert NC.quinzena_de("2026-06-16") == (2026, 6, 2)
    assert NC.quinzena_de("2026-01-01") == (2026, 1, 1)


def test_segunda_quinzena_termina_no_ultimo_dia_do_mes():
    assert NC.periodo_da_quinzena(2026, 2, 2) == ("2026-02-16", "2026-02-28")
    assert NC.periodo_da_quinzena(2024, 2, 2) == ("2024-02-16", "2024-02-29")
    assert NC.periodo_da_quinzena(2026, 12, 2) == ("2026-12-16", "2026-12-31")
    assert NC.periodo_da_quinzena(2026, 6, 1) == ("2026-06-01", "2026-06-15")


def test_prazo_de_fechamento():
    # 1a quinzena fecha no dia 20 do proprio mes; a 2a, no dia 5 do seguinte.
    assert NC.prazo_de_fechamento(2026, 6, 1) == "2026-06-20"
    assert NC.prazo_de_fechamento(2026, 6, 2) == "2026-07-05"
    assert NC.prazo_de_fechamento(2026, 12, 2) == "2027-01-05"


def test_cabecalho_traz_o_mes_por_extenso():
    # A CENSEC pede "Junho", nao 6. Mandar o numero faz a carga ser recusada.
    c = NC.cabecalho("999999", 2026, 6, 2)
    assert c["Cns"] == 999999
    assert c["quinzena"] == {"anoReferencia": 2026, "quinzenaReferencia": 2,
                             "mesReferencia": "Junho"}


# ---------------------------------------------------------------- dinheiro

def test_valor_sai_de_centavos_sem_passar_por_float():
    assert NC.valor_censec(123456) == "1234.56"
    assert NC.valor_censec(5) == "0.05"
    assert NC.valor_censec(100) == "1.00"
    assert NC.valor_censec(0) == "0.00"
    assert NC.valor_censec(None) is None
    # O caso que quebra quem usa ponto flutuante: 0,1 + 0,2.
    assert NC.valor_censec(10 + 20) == "0.30"


def test_texto_tira_os_caracteres_que_a_censec_recusa():
    assert NC._texto("JOÃO D'ARC & CIA*") == "JOÃO DARC  CIA"
    assert NC._texto("  espaço   demais ") == "espaço demais"
    assert NC._texto("ABCDEFGH", 4) == "ABCD"
    assert NC._texto(None) is None


# --------------------------------------------------------------- dominios

def test_a_tabela_de_naturezas_esta_completa():
    # A carga do E-Oficio trouxe 38; a tabela oficial tem 54. Se este numero
    # cair, alguem apagou natureza que a CENSEC aceita.
    assert len(NC.NATUREZA_ESCRITURA) == 54
    for codigo in (35, 43, 45, 46, 50, 51, 54, 55, 70, 71, 72, 75, 76, 77, 78, 79, 80):
        assert codigo in NC.NATUREZA_ESCRITURA, f"natureza {codigo} sumiu"


def test_os_papeis_que_a_serventia_grava_viram_qualidade_da_cep():
    # A serventia nao grava "outorgante": grava o papel do ato. Sao os 22
    # rotulos encontrados nas 105 partes de escritura do acervo — se algum
    # deixar de mapear, ele volta a aparecer como impedimento na tela.
    assert NC.qualidade_cep("VENDEDOR(A)") == "Outorgante"
    assert NC.qualidade_cep("Vendedor(a)") == "Outorgante"      # a caixa varia
    assert NC.qualidade_cep("CEDENTE(S)") == "Outorgante"
    assert NC.qualidade_cep("PROPRIETÁRIO(A)") == "Outorgante"
    assert NC.qualidade_cep("HERDEIRO(A) CEDENTE") == "Outorgante"
    assert NC.qualidade_cep("DECLARANTE") == "Outorgante"
    assert NC.qualidade_cep("COMPRADOR(A)") == "Outorgado"
    assert NC.qualidade_cep("DONATÁRIO(A)") == "Outorgado"


def test_procurador_e_representante_entram_como_interveniente():
    # Regra, e nao lista: o acervo tem seis grafias de procurador. O layout diz
    # que Interveniente contempla representante.
    for rotulo in ("PROCURADOR DO VENDEDOR", "PROCURADORA DA VENDEDORA",
                   "PROCURADOR DO PROPRIETÁRIO", "Procurador do vendedor",
                   "REPRESENTANTE"):
        assert NC.qualidade_cep(rotulo) == "Interveniente", rotulo


def test_papel_desconhecido_nao_vira_outorgante_calado():
    assert NC.qualidade_cep("SÍNDICO DO CONDOMÍNIO") is None
    problemas = NC.conferir_ato_cep(
        ato_bom(), [dict(parte_boa(), qualificacao="SÍNDICO DO CONDOMÍNIO")])
    assert any("SÍNDICO DO CONDOMÍNIO" in x.motivo for x in problemas)


def test_testemunha_vira_interveniente():
    # Nao e arredondamento: o layout da CEP diz que Interveniente contempla
    # anuente e testemunha.
    assert NC.qualidade_cep("TESTEMUNHA") == "Interveniente"
    assert NC.qualidade_cep("outorgante") == "Outorgante"
    assert NC.qualidade_cep("Usufrutuário") == "Usufrutuário"
    assert NC.qualidade_cep("HERDEIRO") is None    # nao existe na CEP


def test_tipo_de_documento_vem_do_numero_e_nao_do_palpite():
    assert NC.tipo_documento("000.000.048-55") == "CPF"
    assert NC.tipo_documento("00.000.042/0001-22") == "CNPJ"
    assert NC.tipo_documento("") == "Desconhecido"


def test_regime_de_bens_no_codigo_json():
    assert NC.regime_bens_censec("COMUNHÃO PARCIAL") == "ComunhaoParcial"
    assert NC.regime_bens_censec("separacao total") == "SeparacaoTotal"
    assert NC.regime_bens_censec("regime exótico") is None
    # 13/10/2026: como a escritura e a certidão escrevem (divórcio 778)
    assert NC.regime_bens_censec("COMUNHÃO PARCIAL DE BENS") == "ComunhaoParcial"
    assert NC.regime_bens_censec("Separação Total de Bens") == "SeparacaoTotal"


# ------------------------------------------------------------- conferencia

def ato_bom() -> dict:
    return {"id": 1, "tipo": "PROCURACAO", "data": "2026-06-20", "livro": "27",
            "folha": "139", "valor_transacao": 0, "situacao": "LAVRADO"}


def parte_boa() -> dict:
    return {"nome": "MARIA DA SILVA", "documento": "00000004855",
            "qualificacao": "OUTORGANTE", "tipo_pessoa": "F"}


def test_ato_completo_passa():
    assert NC.conferir_ato_cep(ato_bom(), [parte_boa()]) == []


def test_ato_sem_parte_nao_passa():
    problemas = NC.conferir_ato_cep(ato_bom(), [])
    assert any(x.campo == "partes" for x in problemas)


def test_procuracao_sem_valor_passa_e_sai_zerada():
    # Procuracao nao discrimina valor: o zero e a informacao correta, e nao um
    # preenchimento de conveniencia. Decisao do delegatario em 15/08/2026.
    ato = ato_bom()
    ato["valor_transacao"] = None
    assert NC.conferir_ato_cep(ato, [parte_boa()]) == []
    assert NC.montar_cep(ato, [parte_boa()])["valor"] == "0.00"


def test_escritura_sem_valor_continua_barrada():
    # Na escritura o valor E o conteudo economico do ato. Mandar zero seria
    # declaracao falsa a uma central nacional.
    ato = ato_bom()
    ato["tipo"] = "ESCRITURA"
    ato["natureza_censec"] = 6
    ato["valor_transacao"] = None
    problemas = NC.conferir_ato_cep(ato, [parte_boa()])
    assert any(x.campo == "valor" for x in problemas)


def test_cpf_invalido_barra_o_ato():
    # A CENSEC recusa o arquivo inteiro por um CPF errado. Melhor segurar um
    # ato aqui do que perder a carga da quinzena la.
    parte = parte_boa()
    parte["documento"] = "00000000000"
    problemas = NC.conferir_ato_cep(ato_bom(), [parte])
    assert any(x.campo == "partes.numeroDocumento" for x in problemas)


def test_escritura_sem_natureza_nao_passa():
    ato = ato_bom()
    ato["tipo"] = "ESCRITURA"
    problemas = NC.conferir_ato_cep(ato, [parte_boa()])
    assert any(x.campo == "naturezaEscritura" for x in problemas)


def test_revogacao_exige_o_ato_anterior():
    ato = ato_bom()
    ato["tipo"] = "REVOGACAO_PROCURACAO"
    problemas = NC.conferir_ato_cep(ato, [parte_boa()])
    campos = {x.campo for x in problemas}
    assert "referentes" in campos and "referentes.cns" in campos


def test_testamento_sem_nome_da_mae_nao_passa():
    # O RCTO exige nomeMae. Sem ele a central recusa o registro.
    ato = {"tipo_testamento": 4, "data": "2026-06-20", "livro": "1", "folha": "10"}
    testador = {"nome": "JOSÉ", "documento": "00000004855",
                "nascimento": "1950-03-02", "mae": None}
    problemas = NC.conferir_ato_rcto(ato, testador)
    assert any(x.campo == "nomeMae" for x in problemas)


def test_separacao_exige_advogado_e_dois_separandos():
    ato = {"tipo_cesdi": 1, "data": "2026-06-20", "livro": "1", "folha": "10",
           "casamento_data": "2000-01-01", "regime_bens": "COMUNHÃO PARCIAL",
           "responsavel_menores": "3"}
    partes = [{"nome": "A", "qualidade_cesdi": "Separando", "nascimento": "1980-01-01",
               "sexo": "M", "municipio_ibge": "2198765", "documento": "00000004855"}]
    problemas = NC.conferir_ato_cesdi(ato, partes)
    motivos = " ".join(x.motivo for x in problemas)
    assert "ao menos 3 partes" in motivos
    assert "Advogado" in motivos


# ----------------------------------------------------------------- montagem

def test_a_carga_montada_tem_o_que_o_layout_pede():
    linha = NC.montar_cep(ato_bom(), [parte_boa()])
    assert linha["tipoAtoCep"] == 2
    assert linha["data"] == "2026-06-20"
    assert linha["valor"] == "0.00"
    assert linha["partes"][0]["qualidade"] == "Outorgante"
    assert linha["partes"][0]["tipoDocumento"] == "CPF"
    assert linha["partes"][0]["numeroDocumento"] == "00000004855"
    # Campo vazio nao vai no arquivo: a CENSEC nao pede, e sujeira atrapalha
    # quem for ler o retorno. Vale DENTRO da parte tambem — foi ali que a
    # primeira versao vazava "identidade": null e "orgaoEmissor": null, e o
    # teste antigo, que so olhava o nivel de cima, passou assim mesmo.
    assert "livroComplemento" not in linha
    assert "identidade" not in linha["partes"][0]
    assert "orgaoEmissor" not in linha["partes"][0]
    assert ": null" not in json.dumps(linha)


def test_o_advogado_nao_e_a_primeira_parte_da_cesdi():
    ato = {"tipo_cesdi": 5, "data": "2026-06-20", "livro": "1", "folha": "10"}
    partes = [
        {"nome": "DR FULANO", "qualidade_cesdi": "Advogado", "documento": "00000004855"},
        {"nome": "DE CUJUS", "qualidade_cesdi": "Falecido", "documento": "00000004855"},
    ]
    linha = NC.montar_cesdi(ato, partes)
    assert linha["partes"][0]["qualidade"] == "Falecido"
    assert linha["partes"][-1]["qualidade"] == "Advogado"
    # O advogado nao leva qualificacao pessoal.
    assert "dataNascimento" not in linha["partes"][-1]


# --------------------------------------------------------- contra o banco

def test_separar_nao_repete_ato_ja_confirmado():
    con = banco()
    agora = "2026-06-20T10:00:00"
    con.execute("""INSERT INTO nt_atos(id, tipo, data, livro, folha,
                       valor_transacao, situacao, criado_em)
                   VALUES (1,'PROCURACAO','2026-06-20','27','139',0,'LAVRADO',?)""",
                (agora,))
    con.execute("""INSERT INTO nt_ato_partes(ato_id, nome, documento,
                       qualificacao, criado_em)
                   VALUES (1,'MARIA DA SILVA','00000004855','OUTORGANTE',?)""",
                (agora,))
    con.commit()

    primeira = NC.separar(con, "CEP", 2026, 6, 2)
    assert len(primeira["aptos"]) == 1 and not primeira["impedidos"]

    con.execute("""INSERT INTO nt_remessas(id, central, situacao, criado_em)
                   VALUES (1,'CEP','ENVIADA',?)""", (agora,))
    con.execute("""INSERT INTO nt_remessa_itens(remessa_id, ato_id, situacao, criado_em)
                   VALUES (1,1,'CONFIRMADA',?)""", (agora,))
    con.commit()

    segunda = NC.separar(con, "CEP", 2026, 6, 2)
    assert segunda["aptos"] == [] and segunda["impedidos"] == []


def test_escritura_da_cesdi_nao_aparece_tambem_na_cep():
    # O layout da CEP e explicito: recebe todas as escrituras EXCETO as que se
    # enquadram na CESDI e no RCTO. Sem esta exclusao o mesmo ato ia para duas
    # centrais.
    con = banco()
    agora = "2026-06-20T10:00:00"
    con.execute("""INSERT INTO nt_atos(id, tipo, data, livro, folha, tipo_cesdi,
                       valor_transacao, situacao, criado_em)
                   VALUES (1,'ESCRITURA','2026-06-20','30','12',1,100,'LAVRADO',?)""",
                (agora,))
    con.execute("""INSERT INTO nt_ato_partes(ato_id, nome, documento,
                       qualificacao, qualidade_cesdi, criado_em)
                   VALUES (1,'MARIA DA SILVA','00000004855','OUTORGANTE','Separando',?)""",
                (agora,))
    con.commit()

    cep = NC.separar(con, "CEP", 2026, 6, 2)
    assert cep["aptos"] == [] and cep["impedidos"] == []
    # E continua sendo visto pela CESDI, com as pendencias dela.
    cesdi = NC.separar(con, "CESDI", 2026, 6, 2)
    assert len(cesdi["impedidos"]) == 1


def test_a_quantidade_relatada_e_a_quantidade_do_arquivo():
    # O contador ja mentiu uma vez neste projeto, relatando 4.060 cartoes numa
    # rodada que inseriu zero. Aqui a contagem sai do proprio arquivo.
    con = banco()
    agora = "2026-06-20T10:00:00"
    for i in (1, 2, 3):
        con.execute("""INSERT INTO nt_atos(id, tipo, data, livro, folha,
                           valor_transacao, situacao, criado_em)
                       VALUES (?,'PROCURACAO','2026-06-20','27',?,0,'LAVRADO',?)""",
                    (i, str(100 + i), agora))
        con.execute("""INSERT INTO nt_ato_partes(ato_id, nome, documento,
                           qualificacao, criado_em)
                       VALUES (?,'MARIA DA SILVA','00000004855','OUTORGANTE',?)""",
                    (i, agora))
    con.commit()

    carga = NC.gerar(con, "CEP", 2026, 6, 2, "999999")
    escrito = json.loads(carga["texto"])
    assert carga["quantidade"] == len(escrito[NC.ENVELOPE_CHAVES["CEP"]]) == 3
    assert escrito["quinzena"]["mesReferencia"] == "Junho"
    # UTF-8 sem BOM, como o layout exige.
    assert not carga["texto"].encode("utf-8").startswith(b"\xef\xbb\xbf")


def test_o_resumo_agrupa_os_motivos():
    impedidos = [{"ato": {}, "problemas": [{"campo": "valor", "motivo": "sem valor"}]},
                 {"ato": {}, "problemas": [{"campo": "valor", "motivo": "sem valor"},
                                           {"campo": "livro", "motivo": "sem livro"}]}]
    resumo = NC.resumo_impedimentos(impedidos)
    assert resumo[0] == {"campo": "valor", "motivo": "sem valor", "atos": 2}
    assert len(resumo) == 2


# ------------------------------------------------- os tipos do sistema (09/10/2026)

def test_todo_tipo_de_ato_do_sistema_tem_destino_na_cep():
    """O dicionário da CEP dizia ATA_NOTARIAL/RENUNCIA_PROCURACAO/
    REVOGACAO_PROCURACAO e o sistema grava ATA/RENUNCIA/REVOGACAO: atas,
    renúncias e revogações sumiam da carga sem aviso (a CENSEC recebeu a 2ª
    quinzena de setembro com 0 atos, tendo uma ata)."""
    from notas_schema import TIPOS_ATO
    fora = [t for t in TIPOS_ATO
            if not t.startswith("TESTAMENTO") and t not in NC.TIPO_SISTEMA_PARA_CEP]
    assert fora == []


def test_ata_notarial_entra_na_cep_com_o_solicitante():
    con = banco()
    agora = "2026-09-17T12:00:00"
    con.execute("""INSERT INTO nt_atos(id, tipo, data, livro, folha, termo,
                       valor_transacao, situacao, criado_em)
                   VALUES (1,'ATA','2026-09-17','1','48',9,0,'LAVRADO',?)""", (agora,))
    con.execute("""INSERT INTO nt_ato_partes(ato_id, nome, documento,
                       qualificacao, criado_em)
                   VALUES (1,'MARIA DA SILVA','00000004855','SOLICITANTE',?)""", (agora,))
    con.commit()
    r = NC.separar(con, "CEP", 2026, 9, 2)
    assert len(r["aptos"]) == 1, r["impedidos"]
    assert r["aptos"][0]["linha"]


# ------------------------------------------- as partes do ato (migração PG)

def test_a_nacionalidade_das_partes_e_a_da_parte_e_nao_a_do_cartao():
    """O SQL junta `p.*` (que tem `nacionalidade`) com colunas do cartão. No
    SQLite o dict ficava com a coluna da parte; no PostgreSQL o `dict_row`
    fica com a última de nome repetido — e um `c.nacionalidade` no fim
    trocava a da parte pela do cartão, ou por nada quando não há cartão."""
    con = banco()
    agora = "2026-09-17T12:00:00"
    con.execute("""INSERT INTO nt_atos(id, tipo, data, situacao, criado_em)
                   VALUES (1,'ESCRITURA','2026-09-17','LAVRADO',?)""", (agora,))
    con.execute("""INSERT INTO nt_cartoes(id, nome, nacionalidade, sexo,
                       criado_em)
                   VALUES (1,'PESSOA FICTICIA UM','PORTUGUESA','F',?)""",
                (agora,))
    con.execute("""INSERT INTO nt_ato_partes(ato_id, cartao_id, nome,
                       nacionalidade, qualificacao, ordem, criado_em)
                   VALUES (1,1,'PESSOA FICTICIA UM','BRASILEIRA',
                           'OUTORGANTE',1,?)""", (agora,))
    con.execute("""INSERT INTO nt_ato_partes(ato_id, nome, nacionalidade,
                       qualificacao, ordem, criado_em)
                   VALUES (1,'PESSOA FICTICIA DOIS','BRASILEIRA',
                           'OUTORGADO',2,?)""", (agora,))
    con.commit()

    com_cartao, sem_cartao = NC._partes_do_ato(con, 1)
    assert com_cartao["nacionalidade"] == "BRASILEIRA"
    assert com_cartao["sexo"] == "F"          # o que só o cartão tem continua vindo
    assert sem_cartao["nacionalidade"] == "BRASILEIRA"
    assert sem_cartao["sexo"] is None
