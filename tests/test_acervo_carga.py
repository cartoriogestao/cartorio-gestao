"""
Testes da carga do acervo para Protesto, RCPN, RCPJ/RTD e Livro 3.

O QUE ELES CONFEREM
    A regra, e nao "a funcao devolveu alguma coisa":

      - os contadores FECHAM: lidos = inseridos + rejeitados, sempre. Neste
        projeto ja houve contador que relatou 4.060 cartoes numa rodada que
        inseriu zero;
      - REJEITADO e AVISADO sao coisas diferentes: rejeitado nao entrou,
        avisado entrou com anotacao. Somar os dois faz o numero mentir;
      - carga repetivel: rodar duas vezes nao duplica nada;
      - titulo sem numero mas com sinal de vida ENTRA marcado — protesto que
        existiu e nao entra faz a certidao dizer que a pessoa esta limpa
        quando ela nao esta;
      - o Livro 3 vem de `LivroAuxiliar`, e NAO de `tbRI_Auxiliar`, que apesar
        do nome guarda volumes do Livro 2;
      - o acervo e aberto em SO LEITURA.

    Os testes montam um acervo de mentira com as colunas que a carga le. Ha
    tambem um teste contra o acervo REAL, que roda so quando ele existe na
    maquina — e e ele que pega mapeamento errado de coluna.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import acervo_carga as AC                          # noqa: E402
from nucleo_schema import init_nucleo_schema       # noqa: E402
from pt_schema import init_pt_schema               # noqa: E402
from ra_schema import init_ra_schema
from papel_seguranca import init_papel_schema
from selador_config import init_selador_schema               # noqa: E402
from ibge_schema import init_ibge_schema
from rc_schema import init_rc_schema               # noqa: E402
from rg_schema import init_rg_schema               # noqa: E402
from ri_schema import init_ri_schema               # noqa: E402

AGORA = "2026-08-24T12:00:00"
EXTENSO = "vinte e quatro dias do mês de agosto do ano de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


def _so_as_cargas(resultado: dict) -> dict:
    """As entradas de CARGA do resultado, sem o relatório da numeração.

    `carregar_tudo` devolve uma entrada por carga MAIS `numeracao`, que tem
    outra forma. Quem percorre o resultado tem de saber disso — e é melhor um
    helper do que cada teste lembrar.
    """
    return {k: v for k, v in resultado.items() if k in AC.CARGAS}


ACERVO_REAL = Path(r"C:\ProgramData\CartorioGestao") / AC.NOME_ACERVO


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    # `ri_schema` aponta para `users` (FK): o PostgreSQL cobra a FK
    # na criacao, e o banco da casa cria `users` antes. Aqui basta o esqueleto.
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    # `rg_titulos` aponta para `cx_protocolos` (FK): o PostgreSQL cobra a FK
    # na criacao, e o banco da casa cria o caixa antes. Aqui basta o esqueleto.
    con.execute("CREATE TABLE IF NOT EXISTS cx_protocolos (id INTEGER PRIMARY KEY)")
    for iniciar in (init_nucleo_schema, init_pt_schema, init_rc_schema,
                    init_rg_schema, init_ri_schema, init_ra_schema,
                    # O PAPEL DE SEGURANCA entrou nas cargas em 27/08/2026: a
                    # casa tem 349 folhas em branco na gaveta, e sem a carga o
                    # estoque nasceria vazio.
                    init_papel_schema,
                    # O RAZAO DOS SELOS entrou nas cargas em 27/08/2026: o
                    # razao comecava vazio, e a trava do selo repetido nao
                    # tinha contra o que comparar.
                    init_selador_schema,
                    # O DE-PARA DO IBGE entrou nas cargas em 28/08/2026: sem os
                    # 5.570 municípios, cada código da remessa teria de ser
                    # digitado à mão — e código digitado numa remessa
                    # estatística é erro que ninguém confere.
                    init_ibge_schema):
        iniciar(con)
    # A CARGA DO IBGE GRAVA CONFIGURAÇÃO, e `settings` mora no `database.py`, e
    # não num esquema de módulo. Aqui ela se cria na mão, porque o que se testa
    # é a carga e não a montagem do banco.
    con.executescript(
        "CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
    return con


def acervo_falso() -> sqlite3.Connection:
    """Um acervo minimo, com as colunas que a carga le de verdade.

    SQLITE DE VERDADE, como o da producao (`acervo_carga.abrir_acervo` abre o
    arquivo pela porta do SQLite): no PostgreSQL de teste o nome da coluna
    viraria minusculo (`strsexo`), e o acervo do E-Oficio guarda `strSexo`."""
    import banco_pg
    con = getattr(banco_pg, "_CONNECT_ORIGINAL", sqlite3.connect)(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        -- O DE-PARA DO IBGE, com o bastante para a carga rodar: um município
        -- com código, um sem (as 68 assim que o acervo real tem), e o
        -- cabeçalho desta serventia.
        CREATE TABLE tbMunicipio (
            strEstado TEXT, intEstadoIBGE INTEGER,
            strMunicipio TEXT, intMunicipioIBGE REAL, id REAL
        );
        INSERT INTO tbMunicipio VALUES
            ('MA', 21, 'Cidade Exemplo', 2198765, 1),
            ('MA', 21, 'São Luís',     2111300, 2),
            ('MA', 21, 'Pindaré Mirim', NULL,   3);
        CREATE TABLE tbIBGE_Propriedades (
            strUF TEXT, strMunicipio TEXT, strDistrito TEXT, strCodigo TEXT
        );
        INSERT INTO tbIBGE_Propriedades VALUES ('21','98765','05','01');

        CREATE TABLE tbAvisoProtesto (
            intChave REAL, intNumero TEXT, strEspecie TEXT,
            strNossoNumero TEXT, dtmEmissao TEXT, dtmVencimento TEXT,
            curValorRealTitulo REAL, curValor REAL, strPracaPgto TEXT,
            strEndosso TEXT, intMotivoProtesto TEXT, canal_entrada TEXT,
            snCanceladoProtesto INTEGER, strTipoPG TEXT, snProtestado INTEGER,
            intNumeroApontamento REAL, intFolhaApontamento REAL,
            intLivroApontamento REAL, strSelo_Apontamento TEXT,
            dtmE_Cartorio TEXT, intCodigoPessoa REAL, intCodigoCedente REAL,
            intProtestoLivro REAL, intProtestoFolha REAL, dtmOcorrencia TEXT,
            intCodigoOcorrencia TEXT, dtmCancelaProtesto TEXT,
            strSelo_Cancelamento TEXT, memObsCancelamento TEXT);
        CREATE TABLE tbPessoa (
            intCodigoPessoa REAL, strRazaoSocial TEXT, strTipoPessoa TEXT,
            strCGC TEXT, strCIC TEXT, strEndereco TEXT, strNumero TEXT,
            strBairro TEXT, strCep TEXT, strCidade TEXT, strUF TEXT);
        -- O CEDENTE MORA AQUI, e nao em `tbPessoa` (29/10/2026): o
        -- `intCodigoCedente` do aviso e chave desta tabela.
        CREATE TABLE tbCedente (
            intCodigoCedente REAL, strRazaoSocial TEXT, strNomeFantasia TEXT,
            strTipoPessoa TEXT, strCGC TEXT, strCIC TEXT, strEndereco TEXT,
            strNumero TEXT, strComplemento TEXT, strBairro TEXT, strCep TEXT,
            strCidade TEXT, strUF TEXT);
        CREATE TABLE tbRegistroNascimento (
            intChave REAL, strNomeNascido TEXT, dtmDataNascimento TEXT,
            dtmDataAssento TEXT, strNumeroMatricula TEXT,
            intNumeroRegistro REAL, strLivro TEXT, strTipoLivro TEXT,
            intFolha REAL, strSexo TEXT, memTexto TEXT,
            -- O QUE O REGISTRADO E A REMESSA DO IBGE PEDEM, acrescentado em
            -- 28/08/2026: sem estas colunas o assento guardava so o NOME da
            -- pessoa, e o arquivo do IBGE saia todo em «ignorado».
            strUF TEXT, strCidade TEXT,
            intCodigoLocalNascimento INTEGER, bitGemeos INTEGER,
            intQuantidadeGemeos INTEGER, strDeclaracaoNascidoVivo TEXT);
        -- O DE-PARA DO LOCAL DO NASCIMENTO, que mora no proprio acervo: o
        -- E-Oficio numera de 1 a 5 e o IBGE nao tem 4 — pula do 3 para o 5.
        CREATE TABLE tbRCPN_LocalNascimento (
            id REAL, strDescricao TEXT, intCodigoIBGE INTEGER, strWScrc TEXT);
        INSERT INTO tbRCPN_LocalNascimento VALUES
            (1,'Hospital',1,'UNIDADE_SAUDE'),
            (2,'Outros estabelecimentos de saude sem internacao',2,'UNIDADE_SAUDE'),
            (3,'Domicilio',3,'FORA_UNIDADE_SAUDE'),
            (4,'Outros',5,'FORA_UNIDADE_SAUDE'),
            (5,'Ignorado',9,'IGNORADO');
        CREATE TABLE tbFiliacao (
            intChave REAL, intChaveRegistro REAL, intTipoRegistro REAL,
            intCodigoFiliacao REAL, strNome TEXT, strSexo TEXT, strCPF TEXT,
            strProfissao TEXT, strNacionalidade TEXT,
            strNaturalidadeCidade TEXT, strNaturalidadeUF TEXT);
        CREATE TABLE tbProgenitor (
            intChave REAL, intChaveRegistro REAL, intTipoRegistro REAL,
            intCodigoFiliacao REAL, intCodigoProgenitor REAL, strNome TEXT,
            strSexo TEXT, strNaturalidadeCidade TEXT, strNaturalidadeUF TEXT);
        CREATE TABLE tbSeloIndividual (
            intChave INTEGER, strSelo TEXT, strTextoSelo TEXT, strURLAto TEXT,
            dtmData TEXT, dtmdata_selo TEXT, bitUtilizado INTEGER,
            bitSeloCancelado INTEGER, strUserid_Selou TEXT);
        CREATE TABLE tbPapelMoedaRCPN (
            intChave INTEGER, strCodigo TEXT, strProtocoloGeral TEXT,
            intTipoAto INTEGER, bitUtilizado INTEGER,
            intCodigoRemessa INTEGER, strSerie TEXT);
        CREATE TABLE tbRegistroTD (
            intChave REAL, strTipoRegistro TEXT, intNumeroRegistro REAL,
            strLivro TEXT, strApresentante TEXT,
            strTipoInscricaoMatricula TEXT, memInteiroTeor TEXT,
            memInteiroTeorSemFormatacao TEXT, dtmData TEXT,
            strFolha_DE TEXT, intProtocolo REAL);
        CREATE TABLE LivroAuxiliar (
            Id INTEGER, Livro TEXT, Registro REAL, Data TEXT, Numero TEXT,
            Titulo TEXT, ValorCompraVenda REAL, Parcelas REAL,
            VencimentoInicial TEXT, VencimentoFinal TEXT, Juros TEXT,
            Garantia TEXT, Condicoes TEXT, strCNM TEXT, Teor TEXT);
    """)
    con.execute(
        """INSERT INTO tbAvisoProtesto(intChave, intNumero, strEspecie,
               strNossoNumero, curValorRealTitulo, curValor, snProtestado,
               intNumeroApontamento, intFolhaApontamento, canal_entrada,
               dtmE_Cartorio, intCodigoPessoa, intCodigoCedente,
               intProtestoLivro, intProtestoFolha, dtmOcorrencia,
               intCodigoOcorrencia)
           VALUES (1,'84713/1','DMI','00200000991',1482.78,1482.78,1,912,3,
                   'CRA','2022-06-01 00:00:00',1,2,
                   4,22,'2022-06-21 00:00:00','C')""")
    # O devedor e pessoa FISICA (CPF em strCIC) e o cedente e JURIDICA (CNPJ
    # em strCGC) — as duas formas que o acervo tem, medidas em 980 e 386.
    con.execute(
        """INSERT INTO tbPessoa(intCodigoPessoa, strRazaoSocial, strTipoPessoa,
               strCGC, strCIC, strEndereco, strNumero, strBairro, strCep,
               strCidade, strUF)
           VALUES (1,'MARIA SANTOS DA SILVA','F','','04785512388',
                   'PCA SANTANINHA','341','CENTRO','65936000',
                   'Cidade Exemplo','MA')""")
    # O CEDENTE ESTA EM `tbCedente`, e `tbPessoa` TEM OUTRA PESSOA NO MESMO
    # NUMERO — a armadilha de 29/10/2026: a carga lia o cedente em `tbPessoa`
    # e todo titulo do acervo saiu com o credor errado. Os dois espacos de id
    # se cruzam de verdade no acervo desta casa.
    con.execute(
        """INSERT INTO tbCedente(intCodigoCedente, strRazaoSocial,
               strTipoPessoa, strCGC, strCIC, strEndereco, strCidade, strUF)
           VALUES (2,'BANCO DO NORDESTE DO BRASIL SA','J','00000017000149','',
                   'AV PARANJANA','Fortaleza','CE')""")
    con.execute(
        """INSERT INTO tbPessoa(intCodigoPessoa, strRazaoSocial, strTipoPessoa,
               strCGC, strCIC, strEndereco, strCidade, strUF)
           VALUES (2,'PESSOA DE OUTRA TABELA COM O MESMO CODIGO','F','',
                   '00000004189','RUA DO DEVEDOR','Cidade Exemplo','MA')""")
    con.execute(
        """INSERT INTO tbRegistroNascimento(intChave, strNomeNascido,
               dtmDataNascimento, dtmDataAssento, strNumeroMatricula,
               intNumeroRegistro, strLivro, strTipoLivro, intFolha,
               strSexo)
           VALUES (1,'JOÃO DA SILVA','2020-01-15 00:00:00',
                   '2020-01-20 00:00:00','1'||substr('0',1,0)||'2',
                   19552,'24','A',127,'M')""")
    # OS PAIS (tbFiliacao: 1 = pai, 2 = mae) e OS QUATRO AVOS
    # (tbProgenitor: filiacao 1 = paternos, 2 = maternos; o sexo separa).
    for codigo, nome, sexo in ((1, "JOSÉ DA SILVA", "Masculino"),
                               (2, "MARIA DAS GRAÇAS", "Feminino")):
        con.execute(
            """INSERT INTO tbFiliacao(intChave, intChaveRegistro,
                   intTipoRegistro, intCodigoFiliacao, strNome, strSexo)
               VALUES (?,1,1,?,?,?)""", (codigo, codigo, nome, sexo))
    for chave, filiacao, ordem, nome, sexo in (
            (1, 1, 1, "ANTÔNIO DA SILVA", "Masculino"),
            (2, 1, 2, "ANA DA SILVA", "Feminino"),
            (3, 2, 1, "PEDRO GOMES", "Masculino"),
            (4, 2, 2, "RITA GOMES", "Feminino")):
        con.execute(
            """INSERT INTO tbProgenitor(intChave, intChaveRegistro,
                   intTipoRegistro, intCodigoFiliacao, intCodigoProgenitor,
                   strNome, strSexo)
               VALUES (?,1,1,?,?,?,?)""",
            (chave, filiacao, ordem, nome, sexo))
    con.execute(
        """INSERT INTO tbRegistroTD(intChave, strTipoRegistro,
               intNumeroRegistro, strLivro, strApresentante, dtmData,
               strFolha_DE, memInteiroTeorSemFormatacao)
           VALUES (1,'TD',1508,'7','EMPRESA X','2022-12-15 00:00:00','79',
                   'Teor do registro, como o livro o tem.')""")
    con.execute(
        """INSERT INTO LivroAuxiliar(Id, Livro, Registro, Data, Numero, Titulo,
               ValorCompraVenda, Parcelas)
           VALUES (1,'3',1549,'2020-06-08 00:00:00','40/01800-8',
                   'CÉDULA RURAL PIGNORATICIA E HIPOTECÁRIA',299809.50,6)""")
    con.commit()
    return con


# --------------------------------------------------------- os contadores


def test_os_contadores_fecham():
    # lidos = inseridos + rejeitados, sempre. Contador que nao fecha e
    # contador que mente, e este projeto ja levou esse prejuizo.
    con, acervo = banco(), acervo_falso()
    resultado = AC.carregar_tudo(con, acervo, agora=AGORA)
    for nome, r in _so_as_cargas(resultado).items():
        assert "erro" not in r, (nome, r)
        assert r["lidos"] == r["inseridos"] + r["rejeitados"], nome


def test_rejeitado_e_avisado_nao_se_misturam():
    # Rejeitado nao entrou; avisado entrou com anotacao. Somar os dois fez a
    # carga informar "11 rejeitados" numa rodada em que 7 tinham entrado.
    carga = AC.Carga("teste")
    carga.lidos = 2
    carga.rejeitar(1, "linha vazia")
    carga.avisar(2, "entrou marcado")
    d = carga.como_dict()
    assert d["rejeitados"] == 1
    assert d["avisados"] == 1
    assert d["motivos_da_rejeicao"] == ["linha vazia"]
    assert d["motivos_do_aviso"] == ["entrou marcado"]


def test_a_carga_e_repetivel():
    con, acervo = banco(), acervo_falso()
    primeira = AC.carregar_tudo(con, acervo, agora=AGORA)
    contagens = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                 for t in ("pt_titulos", "pt_devedores", "pt_atos",
                           "rc_assentos", "rg_registros", "rg_atos",
                           "ra_registros", "ra_atos")}
    segunda = AC.carregar_tudo(con, acervo, agora="2026-08-24T13:00:00")
    depois = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in contagens}
    assert depois == contagens
    for nome, r in _so_as_cargas(segunda).items():
        assert r["inseridos"] == 0, nome
        assert r["repetidos"] == primeira[nome]["inseridos"], nome


# ----------------------------------------------------- o que cada uma faz


def test_o_codigo_5_vira_devolvido_com_o_ato_que_o_sustenta():
    """Até 30/10/2026 o «5» deixava como estava, e isso produziu PAGO sem ato."""
    import protesto_selo_previo as PSELO
    con, acervo = banco(), acervo_falso()
    acervo.execute("""UPDATE tbAvisoProtesto SET snProtestado = 0,
                          intCodigoOcorrencia = '5',
                          dtmOcorrencia = '2022-06-21 00:00:00'""")
    AC.carregar_protesto(con, acervo, agora=AGORA)
    t = con.execute("SELECT * FROM pt_titulos").fetchone()
    assert t["situacao"] == "DEVOLVIDO"
    ato = con.execute("SELECT * FROM pt_atos WHERE tipo = 'DEVOLUCAO'").fetchone()
    assert ato["titulo_id"] == t["id"] and str(ato["data_ato"])[:10] == "2022-06-21"
    assert PSELO.titulos_sem_ato_que_sustente(con) == []


def test_o_titulo_entra_com_o_apontamento_que_o_acervo_ja_tem():
    # O lugar no livro vem do acervo, e nao do nucleo: o ato antigo ja tem
    # livro, folha e ordem do livro fisico, e mandar `reservar()` achar lugar
    # para ele reescreveria a historia.
    con, acervo = banco(), acervo_falso()
    AC.carregar_protesto(con, acervo, agora=AGORA)
    t = con.execute("SELECT * FROM pt_titulos").fetchone()
    assert t["numero_titulo"] == "84713/1"
    assert t["saldo_centavos"] == 148278
    assert t["situacao"] == "PROTESTADO"
    assert t["origem"] == "CRA"
    ato = con.execute("SELECT * FROM pt_atos").fetchone()
    assert ato["tipo"] == "APONTAMENTO"
    assert ato["numero_ordem"] == 912
    assert ato["folha"] == 3


def test_o_devedor_entra_junto_com_o_titulo():
    # SEM DEVEDOR NAO HA CERTIDAO. Certidao de protesto se pede pelo nome e
    # pelo CPF de quem foi protestado; titulo sem devedor faz a busca nao
    # achar ninguem e a certidao dizer que a pessoa esta limpa.
    #
    # O devedor mora em `tbPessoa`, apontado por `intCodigoPessoa`, e a carga
    # passava por ele sem entrar.
    con, acervo = banco(), acervo_falso()
    AC.carregar_protesto(con, acervo, agora=AGORA)
    d = con.execute("SELECT * FROM pt_devedores").fetchone()
    assert d["nome"] == "MARIA SANTOS DA SILVA"
    assert d["documento_tipo"] == "CPF"          # strTipoPessoa 'F'
    assert d["documento_numero"] == "04785512388"
    assert d["endereco"] == "PCA SANTANINHA, 341"
    assert d["cidade"] == "Cidade Exemplo"


def test_rodar_a_carga_de_novo_alcanca_quem_ja_estava_no_banco_sem_devedor():
    # QUEM RODOU A CARGA ANTES DE 25/08/2026 tem os titulos gravados e nenhum
    # devedor. Numa segunda rodada eles voltam como `repetidos`, e o `depois`
    # da linha nao roda neles: so uma passada que olha o que FALTA os alcanca.
    con, acervo = banco(), acervo_falso()
    AC.carregar_protesto(con, acervo, agora=AGORA)
    con.execute("DELETE FROM pt_devedores")          # o banco de antes
    r = AC.carregar_protesto(con, acervo, agora=AGORA).como_dict()
    assert r["inseridos"] == 0 and r["repetidos"] == 1
    assert r["contagens"]["devedores trazidos do acervo"] == 1
    assert con.execute("SELECT COUNT(*) FROM pt_devedores").fetchone()[0] == 1


def test_a_passada_do_devedor_nao_duplica_em_carga_repetida():
    con, acervo = banco(), acervo_falso()
    AC.carregar_protesto(con, acervo, agora=AGORA)
    AC.carregar_protesto(con, acervo, agora=AGORA)
    assert con.execute("SELECT COUNT(*) FROM pt_devedores").fetchone()[0] == 1


def test_o_cedente_entra_no_titulo_com_o_documento_do_tipo_dele():
    # Cedente pessoa juridica: o documento esta em `strCGC` e e CNPJ. Quem
    # decide e o TIPO, e nao o tamanho do que estiver escrito.
    con, acervo = banco(), acervo_falso()
    AC.carregar_protesto(con, acervo, agora=AGORA)
    t = con.execute("SELECT * FROM pt_titulos").fetchone()
    assert t["cedente_nome"] == "BANCO DO NORDESTE DO BRASIL SA"
    assert t["cedente_documento"] == "00000017000149"
    assert t["cedente_uf"] == "CE"


def test_o_cedente_vem_de_tbCedente_e_nao_da_pessoa_de_mesmo_codigo():
    # A ARMADILHA DE 29/10/2026. `intCodigoCedente` e chave de `tbCedente`; a
    # carga o procurava em `tbPessoa`, que e outro espaco de id — e no mesmo
    # numero `tbPessoa` tem outra pessoa. Medido na producao: dos 1.409
    # titulos do acervo, NENHUM com o credor certo (488 vazios, 921 com o nome
    # de outra pessoa). O acervo falso tem o numero 2 nas duas tabelas, com
    # nomes diferentes, e o credor tem de ser o de `tbCedente`.
    con, acervo = banco(), acervo_falso()
    assert acervo.execute(
        "SELECT strRazaoSocial FROM tbPessoa WHERE intCodigoPessoa = 2"
        ).fetchone()[0] == "PESSOA DE OUTRA TABELA COM O MESMO CODIGO"
    AC.carregar_protesto(con, acervo, agora=AGORA)
    t = con.execute("SELECT * FROM pt_titulos").fetchone()
    assert t["cedente_nome"] == "BANCO DO NORDESTE DO BRASIL SA"
    assert t["cedente_documento"] == "00000017000149"      # strCGC, tipo 'J'
    assert t["cedente_endereco"] == "AV PARANJANA"
    assert t["cedente_cidade"] == "Fortaleza"
    # nada da pessoa de `tbPessoa` com o mesmo numero chega ao titulo
    assert t["cedente_endereco"] != "RUA DO DEVEDOR"
    # e o devedor continua sendo o de `tbPessoa`, pelo codigo DELE
    d = con.execute("SELECT nome FROM pt_devedores").fetchone()
    assert d["nome"] == "MARIA SANTOS DA SILVA"


def _com_registro_da_cra(acervo, *, nome: str, documento: str) -> None:
    """Liga o titulo do acervo falso a uma linha de `tbSDT` — o registro da
    CRA —, pelo protocolo, como o acervo real liga."""
    acervo.execute("ALTER TABLE tbAvisoProtesto ADD COLUMN intProtocolo REAL")
    acervo.execute("UPDATE tbAvisoProtesto SET intProtocolo = 2206010001")
    acervo.executescript("""
        CREATE TABLE tbSDT (
            intChave REAL, intProtocolo REAL, Campo01 TEXT, Campo02 TEXT,
            Campo03 TEXT, Campo04 TEXT, Campo05 TEXT, Campo06 TEXT,
            Campo07 TEXT, Campo08 TEXT, Campo09 TEXT, Campo10 TEXT);""")
    # Duas linhas do mesmo protocolo: vale a PRIMEIRA (`intChave`), como em
    # `_o_que_o_retorno_precisa`.
    for chave, campo04 in ((7, nome), (8, "SEGUNDA LINHA QUE NAO VALE")):
        acervo.execute(
            """INSERT INTO tbSDT(intChave, intProtocolo, Campo01, Campo02,
                   Campo04, Campo05, Campo06, Campo07, Campo09, Campo10)
               VALUES (?, 2206010001, '1', '237', ?, 'SACADOR DE EXEMPLO LTDA',
                       ?, 'RUA DO SACADOR', 'Cidade Exemplo', 'MA')""",
            (chave, campo04, documento))


def test_o_nome_do_cedente_e_o_do_registro_da_cra_e_o_resto_e_de_tbCedente():
    # O E-OFICIO IMPRIMIA O NOME DO REGISTRO DA CRA (`tbSDT.Campo04`): no
    # aviso, 1.673 de 1.675; na certidao positiva, 25 de 25 — e a razao
    # social de `tbCedente` nunca onde as duas divergem. O documento e o
    # endereco ficam com `tbCedente`: no registro da CRA eles sao do SACADOR.
    con, acervo = banco(), acervo_falso()
    _com_registro_da_cra(acervo, nome="BANCO DO NORDESTE - AGENCIA EXEMPLO",
                         documento="00000018000193")
    r = AC.carregar_protesto(con, acervo, agora=AGORA).como_dict()
    t = con.execute("SELECT * FROM pt_titulos").fetchone()
    assert t["cedente_nome"] == "BANCO DO NORDESTE - AGENCIA EXEMPLO"
    assert t["cedente_documento"] == "00000017000149"       # o de tbCedente
    assert t["cedente_endereco"] == "AV PARANJANA"
    assert r["contagens"][
        "títulos em que o nome do cedente é o do registro da CRA, "
        "diferente da razão social de `tbCedente`"] == 1


def test_o_documento_do_sacador_na_cra_nao_vira_documento_do_cedente():
    # Cedente e sacador diferentes: a linha do cedente em `tbCedente` nao tem
    # documento (medido: 410 de 410 assim), e o `Campo06` do registro da CRA e
    # o CNPJ do SACADOR. Completar um com o outro daria ao credor o CNPJ de
    # outra empresa — o titulo fica sem documento, e isso e o certo.
    con, acervo = banco(), acervo_falso()
    acervo.execute("UPDATE tbCedente SET strCGC = '', strEndereco = NULL, "
                   "strCidade = NULL, strUF = NULL")
    _com_registro_da_cra(acervo, nome="BANCO DO NORDESTE DO BRASIL SA",
                         documento="00000018000193")
    AC.carregar_protesto(con, acervo, agora=AGORA)
    t = con.execute("SELECT * FROM pt_titulos").fetchone()
    assert t["cedente_nome"] == "BANCO DO NORDESTE DO BRASIL SA"
    assert t["cedente_documento"] is None
    assert t["cedente_endereco"] is None and t["cedente_uf"] is None


def test_sem_linha_em_tbCedente_o_cedente_entra_so_com_o_nome_da_cra():
    con, acervo = banco(), acervo_falso()
    acervo.execute("UPDATE tbAvisoProtesto SET intCodigoCedente = 999")
    _com_registro_da_cra(acervo, nome="CREDOR SO DA CRA LTDA",
                         documento="00000018000193")
    r = AC.carregar_protesto(con, acervo, agora=AGORA).como_dict()
    t = con.execute("SELECT * FROM pt_titulos").fetchone()
    assert t["cedente_nome"] == "CREDOR SO DA CRA LTDA"
    assert t["cedente_documento"] is None
    assert r["contagens"]["títulos sem linha em `tbCedente`: o cedente entrou "
                          "só com o nome do registro da CRA"] == 1


def test_titulo_sem_cedente_no_acervo_entra_do_mesmo_jeito_e_e_contado():
    # Titulo cujo cedente nao esta nem em `tbCedente` nem no registro da CRA.
    # O titulo entra inteiro: a falta do cedente nao apaga o protesto. Mas o
    # numero aparece, porque nada entra calado.
    con, acervo = banco(), acervo_falso()
    acervo.execute("UPDATE tbAvisoProtesto SET intCodigoCedente = 999")
    r = AC.carregar_protesto(con, acervo, agora=AGORA).como_dict()
    assert r["inseridos"] == 1
    assert r["contagens"]["títulos sem cedente no acervo (nem em `tbCedente`, "
                          "nem no registro da CRA)"] == 1
    t = con.execute("SELECT * FROM pt_titulos").fetchone()
    assert t["cedente_nome"] is None
    # E o devedor continua entrando: uma ligacao quebrada nao leva a outra.
    assert con.execute("SELECT COUNT(*) FROM pt_devedores").fetchone()[0] == 1


def test_acervo_sem_tbCedente_nao_derruba_a_carga_e_diz_o_que_faltou():
    con, acervo = banco(), acervo_falso()
    acervo.execute("DROP TABLE tbCedente")
    r = AC.carregar_protesto(con, acervo, agora=AGORA).como_dict()
    assert r["inseridos"] == 1
    assert ("acervo sem `tbCedente`: o cedente vem só do registro da CRA, "
            "onde houver") in r["contagens"]
    t = con.execute("SELECT * FROM pt_titulos").fetchone()
    # e NAO cai para `tbPessoa`: nome trocado e pior que nome faltando
    assert t["cedente_nome"] is None
    assert con.execute("SELECT COUNT(*) FROM pt_devedores").fetchone()[0] == 1


def test_acervo_sem_tbPessoa_nao_derruba_a_carga_do_protesto():
    # Carga que para inteira por causa de uma tabela ligada seria pior do que
    # carga incompleta que diz o que faltou.
    con, acervo = banco(), acervo_falso()
    acervo.execute("DROP TABLE tbPessoa")
    r = AC.carregar_protesto(con, acervo, agora=AGORA).como_dict()
    assert r["inseridos"] == 1
    assert "acervo sem `tbPessoa`: títulos entraram sem devedor" in r["contagens"]
    assert con.execute("SELECT COUNT(*) FROM pt_devedores").fetchone()[0] == 0


def test_titulo_sem_numero_mas_com_vida_entra_marcado():
    # Protesto que existiu e nao entra faz a certidao dizer que a pessoa esta
    # limpa quando ela nao esta. Certidao que mente e pior que carga que
    # rejeita.
    con, acervo = banco(), acervo_falso()
    acervo.execute(
        """INSERT INTO tbAvisoProtesto(intChave, intNumero, strEspecie,
               curValor, snProtestado)
           VALUES (2,'','SJ',984.04,1)""")
    carga = AC.carregar_protesto(con, acervo, agora=AGORA)
    assert carga.inseridos == 2
    assert len(carga.rejeitados) == 0
    assert len(carga.avisos) == 1
    marcado = con.execute("SELECT * FROM pt_titulos WHERE numero_titulo=?",
                          (AC.SEM_NUMERO,)).fetchone()
    assert marcado is not None
    assert marcado["especie"] == "SJ"


def test_linha_totalmente_vazia_e_rejeitada():
    con, acervo = banco(), acervo_falso()
    acervo.execute(
        "INSERT INTO tbAvisoProtesto(intChave, curValor) VALUES (3, 0)")
    carga = AC.carregar_protesto(con, acervo, agora=AGORA)
    assert len(carga.rejeitados) == 1
    assert "linha vazia" in carga.rejeitados[0]["motivo"]


def test_o_assento_leva_os_campos_proprios_em_dados_json():
    # O casamento tem 94 colunas no acervo. Uma coluna por campo aqui
    # encheria a tabela de vazios para as outras cinco especies.
    con, acervo = banco(), acervo_falso()
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    a = con.execute("SELECT * FROM rc_assentos").fetchone()
    assert a["especie"] == "NASCIMENTO"
    assert a["serie"] == "RC_A"
    assert a["nome"] == "JOÃO DA SILVA"
    assert a["numero"] == 19552
    import json
    assert json.loads(a["dados_json"])["strSexo"] == "M"


def test_a_letra_sozinha_nao_manda_o_assento_para_o_livro_E():
    """CORRIGIDO EM 27/08/2026, e este teste guardava a suposição errada.

    Ele dizia: «há um no acervo; assento lançado no Livro E não é assento do
    Livro A» — e provava que a LETRA decide. Fui conferir o tal registro: é o
    nascimento de IGOR PAIVA DE SOUSA, Livro 9, folha 102, número 8686, um
    nascimento comum de 1994, e **a matrícula dele diz tipo de livro 1**, que é
    o Livro A.

    Medido: `strTipoLivro` traz 'A' em 192 e 'E' em 1; a matrícula traz `1` em
    192 de 192. A letra era erro de digitação, e a carga — e este teste —
    confiavam nela.

    Sem matrícula que confirme, o assento fica na espécie da TABELA. É a mesma
    regra do Livro 3: quem define a pertinência é a tabela.
    """
    con, acervo = banco(), acervo_falso()
    acervo.execute(
        """INSERT INTO tbRegistroNascimento(intChave, strNomeNascido,
               intNumeroRegistro, strLivro, strTipoLivro)
           VALUES (2,'MARIA',1,'2','E')""")
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    a = con.execute("SELECT * FROM rc_assentos WHERE nome='MARIA'").fetchone()
    assert a["especie"] == "NASCIMENTO"
    assert a["serie"] == "RC_A"


def test_o_tipo_de_registro_decide_a_atribuicao_no_rcpj_rtd():
    con, acervo = banco(), acervo_falso()
    acervo.execute(
        """INSERT INTO tbRegistroTD(intChave, strTipoRegistro,
               intNumeroRegistro, strLivro) VALUES (2,'PJ',372,'05')""")
    AC.carregar_rcpj_rtd(con, acervo, agora=AGORA)
    linhas = {r["atribuicao"]: r for r in con.execute(
        "SELECT * FROM rg_registros")}
    assert linhas[4]["serie"] == "TD_B"      # TD
    assert linhas[3]["serie"] == "PJ_A"      # PJ


def test_tipo_de_registro_desconhecido_e_rejeitado():
    con, acervo = banco(), acervo_falso()
    acervo.execute(
        "INSERT INTO tbRegistroTD(intChave, strTipoRegistro) VALUES (9,'ZZ')")
    carga = AC.carregar_rcpj_rtd(con, acervo, agora=AGORA)
    assert any("desconhecido" in r["motivo"] for r in carga.rejeitados)


def test_o_livro_3_vem_de_LivroAuxiliar_e_a_natureza_sai_do_titulo():
    con, acervo = banco(), acervo_falso()
    AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    r = con.execute("SELECT * FROM ra_registros").fetchone()
    assert r["numero"] == 1549
    assert r["livro"] == "3"
    assert r["natureza"] == "CEDULA_CREDITO_RURAL"   # deduzido do título
    assert r["valor_centavos"] == 29980950
    assert con.execute("SELECT COUNT(*) FROM ra_atos").fetchone()[0] == 1


def test_livro_esquisito_na_origem_entra_avisado_e_nao_rejeitado():
    # O registro 1551 do acervo real tem `Livro = '-'`. Quem define a
    # pertinencia e a TABELA, nao a coluna: estar em LivroAuxiliar e ser do
    # Livro 3. Recusar perderia uma cedula de credito bancario de verdade.
    con, acervo = banco(), acervo_falso()
    acervo.execute(
        """INSERT INTO LivroAuxiliar(Id, Livro, Registro, Titulo)
           VALUES (2,'-',1551,'CÉDULA DE CRÉDITO BANCÁRIO N° 81')""")
    carga = AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    assert carga.inseridos == 2
    assert len(carga.rejeitados) == 0
    assert len(carga.avisos) == 1
    r = con.execute("SELECT * FROM ra_registros WHERE numero=1551").fetchone()
    assert r["livro"] == "3"
    assert r["natureza"] == "CEDULA_CREDITO_BANCARIO"
    assert "Livro na origem" in (r["condicoes"] or "")


@pytest.mark.parametrize("titulo,esperado", [
    ("CÉDULA RURAL PIGNORATICIA E HIPOTECÁRIA", "CEDULA_CREDITO_RURAL"),
    ("CÉDULA DE CRÉDITO BANCÁRIO N° 81", "CEDULA_CREDITO_BANCARIO"),
    ("CONVENÇÃO DE CONDOMÍNIO", "CONVENCAO_CONDOMINIO"),
    ("REGISTRO: Nº 1315 (Protc. nº 9673)", "OUTRO"),
    (None, "OUTRO"),
])
def test_a_natureza_do_livro_3_sai_do_nome_do_titulo(titulo, esperado):
    assert AC._natureza_do_titulo(titulo) == esperado


# --------------------------------------------------------- as protecoes


# ------------------------------ o contador do núcleo, semeado pela carga
#
# O DEFEITO QUE O ENSAIO CONTRA O BANCO DE PRODUÇÃO ACHOU, em 25/08/2026.
#
# A carga não chama o núcleo, de propósito — o ato do acervo já tem lugar. Mas
# o CONTADOR ficava vazio, porque `escrituracao._semente()` o lê de
# `nu_lugares` e a carga escreve em `pt_atos`. Resultado: a casa tem
# apontamentos até 2.156 e o primeiro protesto novo saía com o número 1.
#
# É o 18/08 outra vez, e nenhum teste de unidade pegou: só o ensaio contra
# dado real.


def test_a_carga_semeia_o_contador_do_nucleo():
    con, acervo = banco(), acervo_falso()
    r = AC.carregar_tudo(con, acervo, agora=AGORA)
    semeadas = {x["serie"]: x for x in r["numeracao"]["semeadas"]}
    # O acervo falso traz um apontamento de ordem 912.
    assert semeadas["PT_APONTAMENTO"]["maior_em_uso"] == 912
    assert semeadas["PT_APONTAMENTO"]["proximo"] == 913
    linha = con.execute(
        "SELECT * FROM nu_numeracao WHERE serie='PT_APONTAMENTO'").fetchone()
    assert linha["proximo"] == 913
    assert linha["semeado_de"] == "acervo do E-Ofício"


def test_o_ato_novo_nasce_depois_do_maior_do_acervo():
    # A prova do que importa: o número não repete o que a serventia já usou.
    import protesto as PT
    con, acervo = banco(), acervo_falso()
    AC.carregar_tudo(con, acervo, agora=AGORA)
    titulo_id = PT.cadastrar_titulo(
        con, {"especie": "DMI", "numero_titulo": "NOVO/1",
              "data_emissao": "2026-01-01", "data_vencimento": "2026-02-01",
              "valor": "100.00", "saldo": "100.00",
              "praca_protesto": "CIDADE EXEMPLO", "tipo_moeda": "1",
              "devedores": [{"nome": "X", "CPF": "12345678901",
                             "enderecos": [{"endereco": "R X",
                                            "cidade": "Cidade Exemplo",
                                            "uf": "MA"}]}]},
        origem="MANUAL", agora=AGORA)
    lugar = PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA,
                                  data_extenso=EXTENSO)
    assert lugar["numero_ordem"] == 913          # e não 1


def test_semear_nunca_baixa_um_contador():
    # Se alguém já lavrou ato novo, o número dele vale mais que o do acervo:
    # baixar faria o próximo ato repetir número.
    con, acervo = banco(), acervo_falso()
    con.execute(
        """INSERT INTO nu_numeracao(serie, proximo, maior_em_uso, semeado_de)
           VALUES ('PT_APONTAMENTO', 5000, 4999, 'balcão')""")
    AC.carregar_tudo(con, acervo, agora=AGORA)
    assert con.execute(
        "SELECT proximo FROM nu_numeracao WHERE serie='PT_APONTAMENTO'"
    ).fetchone()[0] == 5000


def test_a_serie_sem_contador_no_acervo_e_declarada_e_nao_calada():
    # Série sem contador semeado é série em que o primeiro ato nasceria com o
    # número 1 — isso tem de estar dito, e não descoberto depois.
    con, acervo = banco(), acervo_falso()
    r = AC.carregar_tudo(con, acervo, agora=AGORA)
    pendentes = {x["serie"]: x["motivo"] for x in r["numeracao"]["pendentes"]}
    assert "PT_PROTESTO" in pendentes
    assert "nenhuma coluna com o número" in pendentes["PT_PROTESTO"]
    assert "PT_PROTOCOLO" in pendentes            # numeração diária
    assert "reinicia" in pendentes["PT_PROTOCOLO"]


def test_carga_desconhecida_e_recusada():
    con, acervo = banco(), acervo_falso()
    with pytest.raises(AC.CargaError, match="Carga desconhecida"):
        AC.carregar_tudo(con, acervo, agora=AGORA, quais=["notas"])


def test_uma_carga_que_estoura_nao_derruba_as_outras():
    # Perder a carga do Protesto porque a do RCPJ achou tabela faltando seria
    # desperdicar as duas.
    con, acervo = banco(), acervo_falso()
    acervo.execute("DROP TABLE tbRegistroTD")
    resultado = AC.carregar_tudo(con, acervo, agora=AGORA)
    assert "erro" in resultado["rcpj_rtd"]
    assert resultado["protesto"]["inseridos"] == 1


def test_acervo_que_nao_existe_da_frase_de_balcao():
    with pytest.raises(AC.CargaError, match="Não achei o acervo"):
        AC.abrir_acervo(r"C:\nao\existe\mesmo")


# ------------------------------------------------- contra o acervo REAL
#
# E este que pega mapeamento errado de coluna. O acervo falso tem as colunas
# que eu ESCREVI; o real tem as que o E-Oficio gravou.


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_contra_o_acervo_real():
    con = banco()
    acervo = AC.abrir_acervo(ACERVO_REAL)
    r = AC.carregar_tudo(con, acervo, agora=AGORA)

    for nome, d in _so_as_cargas(r).items():
        assert "erro" not in d, (nome, d)
        assert d["lidos"] == d["inseridos"] + d["rejeitados"], nome
        assert d["inseridos"] > 0, nome

    # OS NUMEROS FORAM MEDIDOS DE NOVO EM 14/09/2026 — nove linhas a mais que
    # em 24/08/2026. **O ACERVO CRESCEU; A CARGA NAO MUDOU**, e a prova nao e
    # a leitura de quem mediu: e o que NAO se moveu junto.
    #
    #   - os oito protestos novos sao todos de pessoa fisica (CPF 980 -> 988) e
    #     nenhum tem cedente em `tbPessoa` (sem cedente 458 -> 466) — por isso
    #     CNPJ (386) e títulos com cedente (908) ficaram PARADOS (e o cedente
    #     NAO e de `tbPessoa`: ver a correcao de 29/10/2026, mais abaixo);
    #   - o mesmo-cedente-e-devedor (28), os devedores sem endereço (16), as
    #     intimações (1.176) e as quatro series de numeração que nao sao do
    #     protesto (RC_A, RC_C, PJ_A, TD_B) também ficaram parados.
    #
    # Mapeamento errado de coluna mexeria em TUDO isso de uma vez. O que se
    # moveu foi so o que o E-Ofício acrescentou no dia a dia: o acervo tem
    # `dtmE_Cartorio` até 10/09/2026, e a serventia trabalhou depois da data em
    # que este teste foi escrito. A nona linha a mais e a vazia do fim, que o
    # E-Ofício deixa e a carga rejeita pelo mesmo motivo de sempre.
    #
    # **E `PT_APONTAMENTO` CONFIRMA POR FORA:** o contador do protesto foi de
    # 2.156 para 2.164 — exatamente os oito que entraram —, e as outras quatro
    # series nao se moveram. Soma que fecha por dois caminhos.
    #
    # QUEM VIER ATUALIZAR ISTO DE NOVO: dois numeros congelados moram dentro
    # de NOME de chave (`protocolos ... (1373)` e `sem intimação ... (198)`).
    # Subir so os `assert` deixa o teste vermelho pela chave, e a mensagem
    # aponta para o lugar errado.
    assert r["protesto"]["lidos"] == 1379
    assert r["protesto"]["inseridos"] == 1374
    assert r["protesto"]["rejeitados"] == 5      # linhas sem nada
    assert r["protesto"]["avisados"] == 7        # sem número, entraram marcados
    # O DEVEDOR, medido em 25/08/2026 e remedido em 14/09/2026. Antes da
    # primeira data a carga nao o trazia, e sem ele a certidao de protesto nao
    # acha ninguem por nome nem por CPF.
    #
    # **OS OITO DEVEDORES NOVOS SAO OITO, E NAO NOVE**: um dos protestos que
    # entraram nao tem `intCodigoPessoa` que resolva em `tbPessoa`, e a carga
    # nao inventa devedor sem nome. E o CNPJ nao se moveu — quem chegou foi
    # pessoa fisica.
    assert con.execute("SELECT COUNT(*) FROM pt_devedores").fetchone()[0] == 1374
    por_tipo = dict(con.execute(
        """SELECT documento_tipo, COUNT(*) FROM pt_devedores
            GROUP BY documento_tipo"""))
    assert por_tipo == {"CPF": 988, "CNPJ": 386}   # nenhum sem documento
    # O CEDENTE, CORRIGIDO EM 29/10/2026. Os «908 com cedente» e os «466 sem
    # cedente em `tbPessoa`» que estavam aqui mediam o ENGANO: a carga lia o
    # cedente em `tbPessoa`, e o `intCodigoCedente` e chave de `tbCedente`.
    # Saiu tambem «o mesmo cedente e devedor» (28), que comparava numeros de
    # duas tabelas diferentes. A conferencia agora e a REGRA contra o proprio
    # acervo, e nao um numero congelado: o nome e o do registro da CRA
    # (primeira linha de `tbSDT` do protocolo), e sem ele a razao social de
    # `tbCedente` — o que o E-Oficio imprimia no aviso e na certidao.
    def _t(v):
        return (str(v).strip() or None) if v is not None else None
    regra = {
        f"tbAvisoProtesto:{chave}": _t(cra) or _t(razao)
        for chave, razao, cra in acervo.execute(
            """SELECT a.intChave, c.strRazaoSocial, s.Campo04
                 FROM tbAvisoProtesto a
                 LEFT JOIN tbCedente c ON c.intCodigoCedente = a.intCodigoCedente
                 LEFT JOIN (SELECT intProtocolo, MIN(intChave) chave FROM tbSDT
                             GROUP BY intProtocolo) sp
                        ON sp.intProtocolo = a.intProtocolo
                 LEFT JOIN tbSDT s ON s.intChave = sp.chave""")}
    gravado = {k: v for k, v in con.execute(
        """SELECT origem_chave, cedente_nome FROM pt_titulos
            WHERE origem_chave LIKE 'tbAvisoProtesto:%'""")}
    assert gravado
    assert {k: v for k, v in gravado.items() if regra[k] != v} == {}
    # A VIDA DOS TÍTULOS (14/10/2026, virada do protesto) acrescenta as suas
    # contagens — pagamentos, desistências, situações acertadas, o motivo da
    # remessa da CRA —, e elas são medidas em `test_vida_dos_titulos_*`. Aqui
    # se confere que as de antes continuam IGUAIS, e não que não há outras.
    esperado = {
        "devedores trazidos do acervo": 1374,
        "devedores sem endereço no acervo": 16,
        "protestos sem livro e folha no acervo": 1,
        # O QUE O RETORNO À CRA PRECISA, acrescentado em 01/09/2026 — e o que
        # o **ensaio contra a produção** achou, depois de todo o módulo passar
        # em teste de mesa:
        #
        #   `pendentes()` devolvia 1.211 atos, e **os 1.211 sem protocolo**;
        #   `apresentantes_pendentes()` devolvia **um grupo de código vazio**;
        #   e havia **zero** atos de INTIMACAO em 1.366 títulos.
        #
        # Ou seja: **nenhum retorno saía**, para nenhum título do acervo. O
        # sistema já recusava com a mensagem certa; ninguém tinha medido que a
        # recusa alcança todos.
        "protocolos trazidos do acervo (1373)": 1,
        "apresentantes trazidos do acervo (1357)": 1,
        # 1.115 por edital e 61 em mãos — **o edital é a rotina desta casa**,
        # e não a exceção.
        "intimações trazidas do acervo (1176)": 1,
        # E ESTES NÃO SE INVENTAM: sem edital publicado e sem entrega
        # confirmada, o ato não entra. Quase todos foram pagos ou desistidos
        # antes da intimação; 8 deles estão protestados, e são buraco do
        # próprio E-Ofício.
        "títulos sem intimação no acervo do E-Ofício (198) — a maioria foi "
        "paga ou desistida antes dela": 1,
    }
    contagens = r["protesto"]["contagens"]
    assert {k: contagens.get(k) for k in esperado} == esperado

    # OS ATOS DE PROTESTO E DE CANCELAMENTO, que a carga passou a trazer em
    # 25/08/2026 porque a CERTIDAO os cobrou: certidao positiva diz
    # "protestado no Livro X, fl. Y", e ate essa data so o apontamento entrava.
    # E A CONFERENCIA SE REPETE AQUI, nos atos: sete protestos a mais
    # (1.160 -> 1.167) e um cancelamento a mais (56 -> 57). **A DIFERENCA NAO E
    # A MESMA, e nao precisa ser**: o protesto novo e o cancelamento novo sao
    # fatos diferentes do acervo, e a carga le os dois da mesma tabela sem
    # tratar um como consequencia do outro.
    assert con.execute(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo='PROTESTO'").fetchone()[0] == 1167
    assert con.execute(
        """SELECT COUNT(*) FROM pt_atos
            WHERE tipo='PROTESTO' AND folha IS NOT NULL""").fetchone()[0] == 1166
    assert con.execute(
        "SELECT COUNT(*) FROM pt_atos WHERE tipo='CANCELAMENTO'").fetchone()[0] == 57
    # Os 57 cancelamentos do acervo tem selo, todos.
    assert con.execute(
        """SELECT COUNT(*) FROM pt_atos
            WHERE tipo='CANCELAMENTO' AND selo IS NOT NULL""").fetchone()[0] == 57
    # E todo devedor entra com o nome de busca preenchido, senao a certidao
    # nao acha a pessoa pelo nome.
    assert con.execute(
        "SELECT COUNT(*) FROM pt_devedores WHERE nome_norm IS NULL").fetchone()[0] == 0

    assert r["rcpn"]["inseridos"] == 244         # 192+1 nasc., 20 cas., 31 ób.
    assert r["rcpj_rtd"]["inseridos"] == 72      # 41 RTD + 31 RCPJ
    assert r["registro_auxiliar"]["inseridos"] == 14

    # O Livro 3 vem de LivroAuxiliar. Se alguem trocar para tbRI_Auxiliar,
    # entram 1.273 atos do Livro 2 e este teste cai.
    numeros = [x[0] for x in con.execute(
        "SELECT numero FROM ra_registros ORDER BY numero")]
    assert numeros == [1315, 1332, 1409, 1468, 1531, 1549, 1550, 1551,
                       1552, 1553, 1554, 1560, 1628, 1636]

    # O CONTADOR FICA À FRENTE DO ACERVO. Estes números são os mesmos que
    # `tbPropriedadeRCPN` e `tbTD_Propriedade` declaram, e foi o ensaio contra
    # o banco de produção que mostrou que sem semear o primeiro ato novo
    # nasceria com o número 1.
    semeadas = {x["serie"]: x for x in r["numeracao"]["semeadas"]}
    # **Este e o numero que fecha a conta do acervo crescido**: 2.156 -> 2.164
    # sao EXATAMENTE os oito protestos que entraram acima. Contador do nucleo e
    # carga lendo a mesma coisa por dois caminhos — e por isso os dois servem de
    # prova um do outro.
    assert semeadas["PT_APONTAMENTO"]["maior_em_uso"] == 2164
    assert semeadas["RC_A"]["maior_em_uso"] == 19552
    assert semeadas["RC_C"]["maior_em_uso"] == 1976
    assert semeadas["PJ_A"]["maior_em_uso"] == 372
    assert semeadas["TD_B"]["maior_em_uso"] == 1508
    for x in semeadas.values():
        assert x["proximo"] == x["maior_em_uso"] + 1


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_o_acervo_real_e_aberto_so_para_leitura():
    acervo = AC.abrir_acervo(ACERVO_REAL)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        acervo.execute("DELETE FROM tbAvisoProtesto")


# ------------------------------------------------- os pais e os avos do RCPN


def test_a_carga_traz_os_pais_e_os_avos():
    """A CERTIDAO COBROU DA CARGA pela terceira vez neste projeto.

    Antes foram o devedor do Protesto e o ato de registro do RCPJ/RTD. Aqui e
    a filiacao: `tbFiliacao` e `tbProgenitor` estavam no acervo e a carga
    nunca as tinha aberto — e sem elas nao ha certidao de nascimento.
    """
    con, acervo = banco(), acervo_falso()
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    papeis = {r["papel"]: r["nome"] for r in
              con.execute("SELECT papel, nome FROM rc_pessoas")}
    assert papeis["PAI"] == "JOSÉ DA SILVA"
    assert papeis["MAE"] == "MARIA DAS GRAÇAS"
    assert papeis["AVO_PATERNO"] == "ANTÔNIO DA SILVA"
    assert papeis["AVO_PATERNA"] == "ANA DA SILVA"
    assert papeis["AVO_MATERNO"] == "PEDRO GOMES"
    assert papeis["AVO_MATERNA"] == "RITA GOMES"


def test_a_chave_do_acervo_e_REAL_e_vem_com_ponto_zero():
    """`intChave` e REAL nas tabelas do civil, e isso ja custou 193 assentos.

    A chave de origem sai como `tbRegistroNascimento:1.0`, e `'1.0'.isdigit()`
    e False. Com o teste antigo, 193 dos 244 assentos eram PULADOS EM
    SILENCIO — a carga dizia que tinha rodado e so 83 pessoas entravam.

    O defeito nao aparecia em banco vazio nem em contador nenhum: aparecia na
    certidao, meses depois, dizendo que o assento estava sem filiacao.
    """
    con, acervo = banco(), acervo_falso()
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    chave = con.execute(
        "SELECT origem_chave FROM rc_assentos").fetchone()["origem_chave"]
    assert chave.endswith(".0")            # e assim que ela e mesmo
    assert AC._chave_do_acervo(chave) == 1
    # SEIS DA FILIAÇÃO (pai, mãe e quatro avós) MAIS O REGISTRADO, que entrou
    # em 28/08/2026 — até então o assento guardava só o nome dele.
    assert con.execute("SELECT COUNT(*) c FROM rc_pessoas").fetchone()["c"] == 7


def test_o_pai_vem_antes_da_mae():
    """A certidao escreve «pai e mae», e a ordem sai daqui."""
    con, acervo = banco(), acervo_falso()
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    ordem = [r["papel"] for r in con.execute(
        "SELECT papel FROM rc_pessoas ORDER BY ordem, id")]
    # A POSIÇÃO É RELATIVA, e não absoluta: desde 28/08/2026 o REGISTRADO entra
    # antes deles — ele é o sujeito do assento, e a certidão o nomeia primeiro.
    # O teste continua sendo sobre o que o nome dele diz: o pai antes da mãe.
    assert ordem.index("PAI") < ordem.index("MAE")
    assert ordem[0] == "REGISTRADO"


def test_a_passada_da_filiacao_e_repetivel():
    """Carga rodada duas vezes nao duplica o pai.

    E ela alcanca quem JA ESTAVA no banco: `_executar` so chama o `depois` de
    quem entrou agora, e quem rodou a carga antes de 26/08/2026 tem os
    assentos gravados. A passada olha o que FALTA, e nao o que entrou.
    """
    con, acervo = banco(), acervo_falso()
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    AC.carregar_rcpn(con, acervo, agora="2026-08-26T13:00:00")
    # SEIS DA FILIAÇÃO (pai, mãe e quatro avós) MAIS O REGISTRADO, que entrou
    # em 28/08/2026 — até então o assento guardava só o nome dele.
    assert con.execute("SELECT COUNT(*) c FROM rc_pessoas").fetchone()["c"] == 7


def test_acervo_sem_as_tabelas_da_filiacao_nao_derruba_a_carga():
    """Nem todo acervo tem as duas tabelas; a carga segue e conta zero."""
    con, acervo = banco(), acervo_falso()
    acervo.execute("DROP TABLE tbFiliacao")
    acervo.execute("DROP TABLE tbProgenitor")
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    assert con.execute("SELECT COUNT(*) c FROM rc_assentos").fetchone()["c"] == 1
    # SEM `tbFiliacao` NÃO ENTRA PAI NEM MÃE — que é o que este teste guarda.
    # O REGISTRADO entra, porque ele não vem de lá: vem da própria tabela de
    # registro, e por isso não depende da filiação existir.
    assert con.execute(
        "SELECT COUNT(*) c FROM rc_pessoas"
        " WHERE papel IN ('PAI','MAE')").fetchone()["c"] == 0


def test_pessoa_sem_nome_nao_entra():
    """Linha de filiacao vazia viraria «FILIAÇÃO: ND e MARIA» na certidao."""
    con, acervo = banco(), acervo_falso()
    acervo.execute("UPDATE tbFiliacao SET strNome='' WHERE intCodigoFiliacao=1")
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    papeis = [r["papel"] for r in con.execute("SELECT papel FROM rc_pessoas")]
    assert "PAI" not in papeis
    assert "MAE" in papeis


# --------------------------------------------- o ato de registro do RCPN


def test_a_carga_lavra_o_ato_de_registro_do_assento():
    """A CERTIDAO COBROU DA CARGA PELA QUARTA VEZ neste projeto.

    Sem o ato de REGISTRO a certidao imprimia `LIVRO ND / FOLHA ND` — papel
    que nao diz de onde foi tirado. E era calado: nenhum contador acusava, e
    nenhum dos testes de dominio via, porque neles o ato ja vinha pronto.
    """
    con, acervo = banco(), acervo_falso()
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    ato = con.execute(
        "SELECT * FROM rc_atos WHERE tipo='REGISTRO'").fetchone()
    assert ato is not None
    assert ato["folha"] == 127
    assert ato["numero_ordem"] == 19552
    # A DATA E A DO ASSENTO, e nao a da carga: o registro e de 2020.
    assert ato["data_ato"] == "2020-01-20"


def test_o_volume_do_livro_entra_com_a_letra_medida():
    """`A` + `24` = `A-24` — a capa do livro de papel."""
    con, acervo = banco(), acervo_falso()
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    assert con.execute(
        "SELECT livro_volume FROM rc_assentos").fetchone()[0] == "A-24"


def test_a_passada_do_ato_de_registro_e_repetivel():
    con, acervo = banco(), acervo_falso()
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    AC.carregar_rcpn(con, acervo, agora="2026-08-26T13:00:00")
    assert con.execute(
        "SELECT COUNT(*) c FROM rc_atos WHERE tipo='REGISTRO'"
    ).fetchone()["c"] == 1


def test_acervo_sem_a_coluna_da_folha_nao_derruba_a_carga():
    """A COLUNA SE PERGUNTA ANTES DE LER, como a tabela.

    O ato de registro e acabamento da certidao: ele nao pode derrubar a carga
    dos 244 assentos num acervo que nao tenha `intFolha`.
    """
    con, acervo = banco(), acervo_falso()
    acervo.execute("ALTER TABLE tbRegistroNascimento RENAME COLUMN intFolha "
                   "TO intFolhaAntiga")
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    ato = con.execute(
        "SELECT * FROM rc_atos WHERE tipo='REGISTRO'").fetchone()
    assert ato is not None and ato["folha"] is None


def test_a_carga_pergunta_do_livro_do_casamento_religioso():
    """PENDENCIA E DECLARADA, NAO ADIVINHADA.

    O acervo separa os casamentos por , e o grupo 1 tem
    numeracao propria — o que distingue o B-Auxiliar do B. Sao poucos casos, e
    o sistema NAO decide o livro de um assento por poucos casos: pergunta.
    """
    con, acervo = banco(), acervo_falso()
    _casamento_do_segundo_grupo(acervo)
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    aberta = con.execute(
        "SELECT * FROM nu_implantacao WHERE chave='RCPN_LIVRO_DO_CASAMENTO_RELIGIOSO'"
    ).fetchone()
    assert aberta is not None
    assert aberta["serie"] == "RC_B_AUXILIAR"
    assert aberta["situacao"] == "ABERTA"


def test_acervo_sem_o_segundo_grupo_nao_ganha_a_pergunta():
    """Alarme que soa sempre e alarme que ninguem ouve."""
    con, acervo = banco(), acervo_falso()
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    assert con.execute(
        "SELECT COUNT(*) c FROM nu_implantacao "
        "WHERE chave='RCPN_LIVRO_DO_CASAMENTO_RELIGIOSO'").fetchone()[0] == 0


def _casamento_do_segundo_grupo(acervo) -> None:
    """Um casamento com `intTipoRegistroLivro = 1` — o grupo que levanta a
    duvida do Livro B-Auxiliar."""
    acervo.executescript("""
        CREATE TABLE IF NOT EXISTS tbRegistroCasamento (
            intChave REAL, strNomeConjuge1 TEXT, strNomeConjuge2 TEXT,
            dtmDataCelebracaoCasamento TEXT, dtmDataRegistroCasamento TEXT,
            strMatricula TEXT, intNumeroRegistro REAL, strLivro TEXT,
            intFolha REAL, intTipoRegistroLivro REAL);
    """)
    acervo.execute(
        """INSERT INTO tbRegistroCasamento(intChave, strNomeConjuge1,
               strNomeConjuge2, dtmDataCelebracaoCasamento,
               dtmDataRegistroCasamento, strMatricula, intNumeroRegistro,
               strLivro, intFolha, intTipoRegistroLivro)
           VALUES (9,'JOÃO DA SILVA','MARIA DE SOUZA','1957-09-10 00:00:00',
                   '1957-09-10 00:00:00','000000...',26,'1',20,1)""")
    acervo.commit()


# ------------------------------------------------- o livro por confirmar


def test_o_assento_do_segundo_grupo_leva_a_marca_do_livro():
    """«Deixe como o E-Oficio guardou, PENDENTE DE CONFIRMACAO QUANDO FOREM
    CONSULTADOS EFETIVAMENTE» — o oficial, 26/08/2026.

    A primeira metade da frase nao precisa de codigo: nao mexer e de graca. A
    marca existe pela SEGUNDA — o aviso tem de aparecer no dia em que alguem
    abrir aquele assento, que pode ser daqui a cinco anos com outro escrevente
    no balcao.

    E ela e TEXTO, e nao um `1`: quem ler a ficha daqui a cinco anos precisa
    saber POR QUE o livro esta por confirmar, e nao so que esta.
    """
    con, acervo = banco(), acervo_falso()
    _casamento_do_segundo_grupo(acervo)
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    marca = con.execute(
        "SELECT livro_a_confirmar FROM rc_assentos WHERE especie='CASAMENTO'"
    ).fetchone()[0]
    assert marca and "B-Auxiliar" in marca
    assert "livro de papel" in marca


def test_o_assento_do_primeiro_grupo_nao_leva_marca():
    """Marcar todo mundo seria alarme que soa sempre."""
    con, acervo = banco(), acervo_falso()
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    marcas = [r[0] for r in con.execute(
        "SELECT livro_a_confirmar FROM rc_assentos")]
    assert marcas == [None]


def test_a_carga_nao_ressuscita_a_marca_ja_conferida():
    """Se alguem foi a estante e conferiu, rodar a carga de novo NAO desfaz.

    Marca que volta e pior que marca que nunca existiu: ensina o balcao a
    ignora-la.
    """
    con, acervo = banco(), acervo_falso()
    _casamento_do_segundo_grupo(acervo)
    AC.carregar_rcpn(con, acervo, agora=AGORA)
    # Como a TELA faz ao confirmar: limpa a marca E grava quem conferiu.
    con.execute("UPDATE rc_assentos SET livro_a_confirmar=NULL, "
                "livro_volume='B-1', livro_conferido_em='2026-08-26T12:00:00' "
                "WHERE especie='CASAMENTO'")
    AC.carregar_rcpn(con, acervo, agora="2026-08-26T13:00:00")
    linha = con.execute(
        "SELECT livro_volume, livro_a_confirmar FROM rc_assentos "
        "WHERE especie='CASAMENTO'").fetchone()
    assert linha["livro_a_confirmar"] is None
    assert linha["livro_volume"] == "B-1"


# ---------------------------------------------------------------------------
# A TELA DA CARGA OFERECE AS CARGAS QUE EXISTEM — nem mais, nem menos.
#
# O DEFEITO, relatado pelo escrevente em 27/08/2026 as 16h16: «nao encontrou
# livro3 no e-oficio para importar». A tela montava as caixinhas da lista de
# TELAS (`atribuicoes_web.PAINEIS`), onde o Livro 3 se chama `livro3`; aqui a
# carga dele se chama `registro_auxiliar`.
#
# E a recusa de carga desconhecida derruba a TRANSACAO INTEIRA: marcar tudo e
# mandar nao trazia nada. As duas cargas novas da 3.6.17 — papel e selos — nao
# tinham caixinha nenhuma e ficaram em ZERO no servidor.


def test_toda_carga_tem_nome_de_balcao():
    """Carga nova sem nome fica vermelha aqui, e nao muda sem caixinha."""
    assert set(AC.TITULO_DA_CARGA) == set(AC.CARGAS), (
        "A lista de nomes e a lista de cargas divergiram. A tela sai da "
        "primeira e a carga roda pela segunda: quem cair fora some da tela ou "
        "derruba a carga inteira.")


def test_os_nomes_estao_na_ordem_das_cargas():
    """A ordem nao e enfeite: o papel vem depois do RCPN, e os selos por ultimo."""
    assert list(AC.TITULO_DA_CARGA) == list(AC.CARGAS)


def test_a_ordem_nao_e_a_do_formulario():
    """Pedir fora de ordem nao muda a ordem em que as cargas rodam.

    Os selos se amarram aos atos que as outras acabaram de trazer; obedecer a
    ordem em que o navegador mandou as caixinhas poria isso na mao dele.
    """
    con, ace = banco(), acervo_falso()
    r = AC.carregar_tudo(con, ace, agora="2026-08-27T10:00:00",
                         quais=["selos", "protesto"])
    assert list(k for k in r if k != "numeracao") == ["protesto", "selos"]


def test_carga_desconhecida_diz_quais_existem():
    """A mensagem que o escrevente leu tinha de dizer o que fazer."""
    con, ace = banco(), acervo_falso()
    with pytest.raises(AC.CargaError) as erro:
        AC.carregar_tudo(con, ace, agora="2026-08-27T10:00:00",
                         quais=["livro3"])
    assert "livro3" in str(erro.value)
    assert "registro_auxiliar" in str(erro.value)


# ---------------------------------------------------------------------------
# OS CONTADORES QUE O ACERVO GUARDA FORA DAS TABELAS DE REGISTRO
#
# Eu havia declarado como pendência do oficial o próximo número de PROCLAMAS e
# de NATIMORTOS, com o motivo «o acervo não tem tabela dessas duas». A conclusão
# sobre as TABELAS estava certa; a conclusão sobre os NÚMEROS estava errada:
# `tbPropriedadeRCPN` guarda o contador de cada série, e lá estão
# `intRegistroAtualRegistroProclamas = 1358` e
# `intObito_Numero_Registro_CAuxiliar = 12`.
#
# É a mesma lição do `codigoAto`, pela terceira vez: **ausência de tabela não
# prova ausência de dado** — prova que aquela tabela não é onde ele fica.


def _propriedade_rcpn(acervo, **campos):
    colunas = {"intRegistroAtualNascimento": 19552,
               "intRegistroAtualRegistroProclamas": 1358,
               "intObito_Numero_Registro_CAuxiliar": 12}
    colunas.update(campos)
    acervo.execute("DROP TABLE IF EXISTS tbPropriedadeRCPN")
    acervo.execute(f"CREATE TABLE tbPropriedadeRCPN "
                   f"({','.join(f'{c} INTEGER' for c in colunas)})")
    acervo.execute(f"INSERT INTO tbPropriedadeRCPN VALUES "
                   f"({','.join('?' * len(colunas))})", tuple(colunas.values()))


def test_o_contador_de_proclamas_e_de_natimortos_sai_do_acervo():
    con, ace = banco(), acervo_falso()
    _propriedade_rcpn(ace)
    r = AC.semear_numeracao(con, agora="2026-08-27T10:00:00", acervo=ace)
    semeadas = {x["serie"]: x["proximo"] for x in r["semeadas"]}
    assert semeadas.get("RC_D") == 1359, "o proclamas não foi semeado"
    assert semeadas.get("RC_C_AUXILIAR") == 13, "o natimorto não foi semeado"


def test_serie_semeada_deixa_de_ser_pendencia_do_oficial():
    """Perguntar o que o sistema já sabe faz o próximo aviso ser ignorado."""
    con, ace = banco(), acervo_falso()
    _propriedade_rcpn(ace)
    r = AC.semear_numeracao(con, agora="2026-08-27T10:00:00", acervo=ace)
    pendentes = {x["serie"] for x in r["pendentes"]}
    assert "RC_D" not in pendentes
    assert "RC_C_AUXILIAR" not in pendentes


def test_as_duas_que_o_acervo_nao_tem_continuam_pendentes():
    """E as duas têm a mesma prova: há livro e não há número de registro."""
    con, ace = banco(), acervo_falso()
    _propriedade_rcpn(ace)
    r = AC.semear_numeracao(con, agora="2026-08-27T10:00:00", acervo=ace)
    pendentes = {x["serie"] for x in r["pendentes"]}
    assert "RC_B_AUXILIAR" in pendentes
    assert "RC_E" in pendentes


def test_sem_acervo_aberto_tudo_continua_pendente():
    """Vazio aqui quer dizer «continua pendência», que é a verdade."""
    r = AC.semear_numeracao(banco(), agora="2026-08-27T10:00:00", acervo=None)
    pendentes = {x["serie"] for x in r["pendentes"]}
    assert {"RC_D", "RC_C_AUXILIAR"} <= pendentes


def test_a_carga_nao_morre_se_a_propriedade_mudar_de_forma():
    """Tabela de propriedade que muda entre versões não pode derrubar a carga."""
    con, ace = banco(), acervo_falso()
    ace.execute("DROP TABLE IF EXISTS tbPropriedadeRCPN")
    ace.execute("CREATE TABLE tbPropriedadeRCPN (outra_coisa TEXT)")
    ace.execute("INSERT INTO tbPropriedadeRCPN VALUES ('x')")
    r = AC.semear_numeracao(con, agora="2026-08-27T10:00:00", acervo=ace)
    assert "RC_D" in {x["serie"] for x in r["pendentes"]}


def test_o_contador_do_acervo_nao_baixa_o_que_ja_andou():
    """Ato novo já lavrado vale mais que o acervo — a regra de sempre."""
    con, ace = banco(), acervo_falso()
    _propriedade_rcpn(ace)
    con.execute("""INSERT INTO nu_numeracao(serie, proximo, maior_em_uso)
                   VALUES ('RC_D', 2000, 1999)""")
    AC.semear_numeracao(con, agora="2026-08-27T10:00:00", acervo=ace)
    linha = con.execute("SELECT proximo FROM nu_numeracao WHERE serie='RC_D'").fetchone()
    assert linha["proximo"] == 2000


def test_o_contador_da_propriedade_sai_da_primeira_linha_e_nao_da_menor_coluna():
    """A tabela de propriedade deveria ter uma linha só. Se tiver duas, vale a
    PRIMEIRA que o E-Ofício gravou (`intChave`), que é a que a leitura antiga
    pegava — e não a de menor valor na primeira coluna, que é o que um
    `ORDER BY 1` escolheria. Aqui `intChave` é a segunda coluna de propósito.
    """
    con, ace = banco(), acervo_falso()
    ace.execute("DROP TABLE IF EXISTS tbPropriedadeRCPN")
    ace.execute("CREATE TABLE tbPropriedadeRCPN "
                "(intRegistroAtualRegistroProclamas INTEGER, intChave INTEGER)")
    ace.execute("INSERT INTO tbPropriedadeRCPN VALUES (1358, 1)")
    ace.execute("INSERT INTO tbPropriedadeRCPN VALUES (5, 2)")
    r = AC.semear_numeracao(con, agora="2026-08-27T10:00:00", acervo=ace)
    semeadas = {x["serie"]: x["proximo"] for x in r["semeadas"]}
    assert semeadas.get("RC_D") == 1359, "leu a outra linha da propriedade"


def test_o_cabecalho_do_ibge_sai_da_primeira_linha_do_acervo_e_nao_da_menor_uf():
    """Mesma regra para `tbIBGE_Propriedades`: com duas linhas, vale a primeira
    gravada (`intChave`), e não a de menor `strUF`. O cabeçalho alimenta a
    remessa do IBGE, e UF trocada é remessa de outra casa."""
    con, ace = banco(), acervo_falso()
    ace.execute("DROP TABLE IF EXISTS tbIBGE_Propriedades")
    ace.execute("CREATE TABLE tbIBGE_Propriedades (intChave INTEGER, strUF TEXT, "
                "strMunicipio TEXT, strDistrito TEXT, strCodigo TEXT)")
    ace.execute("INSERT INTO tbIBGE_Propriedades VALUES (1,'21','98765','05','01')")
    ace.execute("INSERT INTO tbIBGE_Propriedades VALUES (2,'13','00001','01','09')")
    AC.carregar_ibge(con, ace, agora=AGORA)
    valor = {k: con.execute("SELECT value FROM settings WHERE key=?",
                            (k,)).fetchone()["value"]
             for k in ("ibge_uf", "ibge_municipio", "ibge_cartorio")}
    assert valor == {"ibge_uf": "21", "ibge_municipio": "98765",
                     "ibge_cartorio": "01"}, "leu a outra linha da propriedade"


# ---------------------------------------------------------------------------
# A MATRÍCULA DECIDE A ESPÉCIE, E NÃO A LETRA DO ACERVO
#
# A carga mandava para o Livro E todo assento com `strTipoLivro = 'E'`, e há
# exatamente um. Fui conferi-lo em 27/08/2026: é um nascimento
# do Livro 9, folha 102, número 8686 — um nascimento comum de 1994. **A
# matrícula diz tipo de livro `1`**, que é o Livro A.
#
# Medido: `strTipoLivro` traz 'A' em 192 e 'E' em 1; a matrícula traz `1` em
# **192 de 192**. A letra é erro de digitação, e a carga confiava nela.
#
# O ESTRAGO PASSAVA DO ASSENTO: aquele registro semeava o contador do Livro E em
# **8687**, com um número que é de nascimento. O primeiro ato de Livro E desta
# casa nasceria com o número 8688 — o defeito de 18/08 num livro que ainda nem
# foi usado.


def test_a_matricula_desmente_a_letra_e_o_assento_fica_no_livro_certo():
    con, ace = banco(), acervo_falso()
    ace.execute("""INSERT INTO tbRegistroNascimento
                   (intChave, intNumeroRegistro, strLivro, intFolha,
                    strNomeNascido, dtmDataAssento, strNumeroMatricula,
                    strTipoLivro)
                   VALUES (500, 8686, '9', 102, 'IGOR PAIVA DE SOUSA',
                           '1994-09-16', '00000001551994100009102000868611',
                           'E')""")
    AC.carregar_rcpn(con, ace, agora="2026-08-27T10:00:00")
    linha = con.execute(
        "SELECT serie, especie FROM rc_assentos WHERE numero='8686'").fetchone()
    assert linha["serie"] == "RC_A", "o nascimento foi para o Livro E"
    assert linha["especie"] == "NASCIMENTO"


def test_a_divergencia_vira_aviso_e_nao_silencio():
    """Correção que ninguém vê é correção que ninguém confere."""
    con, ace = banco(), acervo_falso()
    ace.execute("""INSERT INTO tbRegistroNascimento
                   (intChave, intNumeroRegistro, strLivro, intFolha,
                    strNomeNascido, dtmDataAssento, strNumeroMatricula,
                    strTipoLivro)
                   VALUES (501, 8686, '9', 102, 'RAFAEL', '1994-09-16',
                           '00000001551994100009102000868611', 'E')""")
    r = AC.carregar_rcpn(con, ace, agora="2026-08-27T10:00:00").como_dict()
    assert r["avisados"] == 1


def test_quando_a_matricula_CONCORDA_o_assento_vai_para_o_livro_e():
    """A letra não é ignorada: ela decide quando a matrícula confirma.

    O dígito da posição 15 é o tipo de livro, e `7` é o Livro E.
    """
    con, ace = banco(), acervo_falso()
    ace.execute("""INSERT INTO tbRegistroNascimento
                   (intChave, intNumeroRegistro, strLivro, intFolha,
                    strNomeNascido, dtmDataAssento, strNumeroMatricula,
                    strTipoLivro)
                   VALUES (502, 40, '2', 39, 'FULANO DE TAL', '2020-01-10',
                           '00000001552020700002039000004062', 'E')""")
    AC.carregar_rcpn(con, ace, agora="2026-08-27T10:00:00")
    linha = con.execute(
        "SELECT serie, especie FROM rc_assentos WHERE numero='40'").fetchone()
    assert linha["serie"] == "RC_E"
    assert linha["especie"] == "OUTRO"


def test_sem_matricula_o_assento_fica_na_especie_da_tabela():
    """False aqui quer dizer «fique onde a tabela diz», que é o seguro."""
    assert AC._matricula_diz_livro_e(None) is False
    assert AC._matricula_diz_livro_e("") is False
    assert AC._matricula_diz_livro_e("123") is False
    assert AC._matricula_diz_livro_e("00000001551994100009102000868611") is False
    assert AC._matricula_diz_livro_e("000000 0155 2020 7 00002 039 0000040 62") is True


# ---------------------------------------------------------------------------
# O DECLARANTE E AS TESTEMUNHAS


def test_o_declarante_entra_e_a_passada_e_repetivel():
    """Assento que já tem pai e mãe nunca voltaria pela passada da filiação."""
    con, ace = banco(), acervo_falso()
    ace.execute("""INSERT INTO tbRegistroNascimento
                   (intChave, intNumeroRegistro, strLivro, intFolha,
                    strNomeNascido, dtmDataAssento)
                   VALUES (600, 1, '24', 1, 'CRIANCA', '2026-01-10')""")
    ace.execute("""CREATE TABLE IF NOT EXISTS tbDeclarante
                   (intChave INTEGER, intChaveRegistro REAL, intTipoRegistro INTEGER,
                    strNome TEXT, strCPF TEXT, strSexo TEXT, strProfissao TEXT,
                    strNacionalidade TEXT, strMunicipioNaturalidade TEXT,
                    strUFNaturalidade TEXT, strLogradouro TEXT, strBairro TEXT,
                    strMunicipio TEXT, strUF TEXT)""")
    ace.execute("""INSERT INTO tbDeclarante VALUES
                   (1, 600.0, 1, 'JOSE DECLARANTE', '000.000.010-82', 'M',
                    'lavrador', 'BRASILEIRA', 'CIDADE EXEMPLO', 'MA',
                    'RUA A', 'CENTRO', 'CIDADE EXEMPLO', 'MA')""")
    AC.carregar_rcpn(con, ace, agora="2026-08-27T10:00:00")
    p = con.execute(
        "SELECT * FROM rc_pessoas WHERE papel='DECLARANTE'").fetchone()
    assert p is not None, "o declarante não entrou"
    assert p["nome"] == "JOSE DECLARANTE"
    # SÓ DÍGITOS, como no resto da casa.
    assert p["documento_numero"] == "00000001082"
    # E rodar de novo não duplica.
    AC._ligadas_que_faltam(con, ace, agora="2026-08-27T11:00:00")
    assert con.execute(
        "SELECT COUNT(*) n FROM rc_pessoas WHERE papel='DECLARANTE'"
    ).fetchone()["n"] == 1


def test_declarante_sem_nome_nao_vira_linha_vazia():
    """105 dos 225 do acervo estão sem nome.

    Linha vazia na certidão é pior que ausência: ela afirma que há um
    declarante e não diz quem.
    """
    con, ace = banco(), acervo_falso()
    ace.execute("""INSERT INTO tbRegistroNascimento
                   (intChave, intNumeroRegistro, strLivro, intFolha,
                    strNomeNascido, dtmDataAssento)
                   VALUES (601, 2, '24', 2, 'CRIANCA', '2026-01-10')""")
    ace.execute("""CREATE TABLE IF NOT EXISTS tbDeclarante
                   (intChave INTEGER, intChaveRegistro REAL, intTipoRegistro INTEGER,
                    strNome TEXT, strCPF TEXT)""")
    ace.execute("INSERT INTO tbDeclarante(intChave,intChaveRegistro,intTipoRegistro,strNome) "
                "VALUES (2, 601.0, 1, '')")
    AC.carregar_rcpn(con, ace, agora="2026-08-27T10:00:00")
    assert con.execute(
        "SELECT COUNT(*) n FROM rc_pessoas WHERE papel='DECLARANTE'"
    ).fetchone()["n"] == 0
