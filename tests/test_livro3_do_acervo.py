"""
Testes das partes e das averbações do Livro 3 do acervo — 18/09/2026.

O QUE ELES CONFEREM, E POR QUE CADA UM EXISTE

  - A PARTE VEM DO `tbOrtoga`, e NÃO do `tbPessoa`. As duas tabelas têm o mesmo
    espaço de id apontando para PESSOAS DIFERENTES: medido no acervo desta
    casa, o id 10018 é o «BANCO DO BRASIL S/A» numa e «FULANO DO TBPESSOA EXEMPLO»
    na outra. Escolher pelo nome da tabela traria o credor errado para a ficha
    e para o alerta de fraude — e é o tipo de defeito que nenhuma releitura
    pega, porque as duas linhas existem e as duas têm nome;
  - A AVERBAÇÃO ENTRA COMO ATO, com o número que o acervo já deu, a data dela e
    o texto dela. É a baixa que libera a garantia: sem ela a ficha diz que a
    cédula está viva depois de ela ter sido baixada;
  - A PARTE DA AVERBAÇÃO QUE JÁ É PARTE DO REGISTRO NÃO SE REPETE — medido, as
    10 linhas da averbação nomeiam 7 pessoas que já estão entre as 25 do
    registro. Repetir poria a mesma pessoa duas vezes na ficha;
  - O NÚMERO DO ATO OCUPADO NÃO É ROUBADO: se já houver um AV-1 lavrado no
    balcão, o do acervo não entra (ato lavrado não se renumera) e o motivo fica
    contado;
  - A PASSADA ALCANÇA OS REGISTROS QUE JÁ ESTAVAM GRAVADOS — quem rodou esta
    carga antes de 18/09/2026 tem os 14 registros e nenhuma parte, e eles
    voltam como `repetidos`, sem passar pelo `depois` do laço;
  - A BAIXA NÃO MUDA A SITUAÇÃO do registro: o acervo não tem marca de
    cancelamento, e decidir pelo TEXTO da averbação seria a máquina lavrando
    ato;
  - A PRÉVIA CONTA SEM GRAVAR.

    Há também um teste contra o acervo REAL, que roda só quando ele existe na
    máquina — e é ele que pega mapeamento errado de coluna.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import acervo_carga as AC                          # noqa: E402
from ra_schema import init_ra_schema                # noqa: E402

AGORA = "2026-09-18T10:00:00"
ACERVO_REAL = Path(r"C:\ProgramData\CartorioGestao") / AC.NOME_ACERVO


def banco() -> sqlite3.Connection:
    """O banco do sistema, só com o que o Livro 3 usa."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_ra_schema(con)
    return con


def acervo_falso() -> sqlite3.Connection:
    """Um acervo mínimo do Livro 3, com as colunas que a carga lê de verdade.

    Ele tem as duas armadilhas medidas, de propósito:

      - `tbPessoa` com o MESMO id apontando para OUTRA pessoa (o id 102 é o
        BANCO DO NORDESTE no `tbOrtoga` e «FULANO DO TBPESSOA EXEMPLO» no
        `tbPessoa`);
      - documento com máscara em uma das partes, para provar que ele sai em
        dígitos como os do Livro 2.
    """
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE LivroAuxiliar (
            Id INTEGER, Livro TEXT, Registro REAL, Data TEXT, Numero TEXT,
            Titulo TEXT, ValorCompraVenda REAL, Parcelas REAL,
            VencimentoInicial TEXT, VencimentoFinal TEXT, Juros TEXT,
            Garantia TEXT, Condicoes TEXT, strCNM TEXT, Teor TEXT);
        CREATE TABLE LivroAuxiliarPartes (
            Id INTEGER, LivroAuxiliarId INTEGER, ParteId INTEGER,
            QualificacaoId INTEGER, Credor INTEGER);
        CREATE TABLE LivroAuxiliarAverbacao (
            Id INTEGER, LivroAuxiliarId INTEGER, Averbacao INTEGER, Data TEXT,
            TipoAverbacao INTEGER, Vinculo INTEGER, Cancelada INTEGER,
            Finalizado INTEGER, Teor TEXT);
        CREATE TABLE LivroAuxiliarAverbacaoPartes (
            Id INTEGER, LivroAuxiliarAverbacaoId INTEGER, ParteId INTEGER,
            QualificacaoId INTEGER);
        CREATE TABLE TipoAverbacao (Id INTEGER, Descricao TEXT, intCodigoWS INTEGER);
        CREATE TABLE tbQualificacaoPartes (intChave INTEGER, strDescricao TEXT);
        CREATE TABLE tbOrtoga (
            intCodigo INTEGER, strTipoPessoa TEXT, strNome TEXT,
            PJ_RazaoSocial TEXT, strCPF TEXT, strCNPJ TEXT,
            strNacionalidade TEXT, strEstadoCivil TEXT, strProfissao TEXT);
        -- A OUTRA tabela. O mesmo id, outra pessoa: escolher pelo nome dela
        -- traria o credor errado.
        CREATE TABLE tbPessoa (intCodigoPessoa INTEGER, strRazaoSocial TEXT);

        INSERT INTO TipoAverbacao VALUES
            (1,'AVERBAÇÃO DE RETIFICAÇÃO',206),
            (2,'AVERBAÇÃO DE BAIXA',207);
        INSERT INTO tbQualificacaoPartes VALUES
            (1,'Emitente/Creditado'), (2,'CREDOR(A)'), (3,'Proprietário(a)');

        -- O REGISTRO 1549: emitente pessoa física, credor jurídico, um
        -- terceiro que o tbOrtoga não conhece, e uma averbação de BAIXA.
        INSERT INTO LivroAuxiliar(Id, Livro, Registro, Data, Numero, Titulo,
               ValorCompraVenda, Parcelas, Teor)
            VALUES (1,'3',1549,'2020-06-08 00:00:00','40/01800-8',
                    'CÉDULA RURAL PIGNORATICIA E HIPOTECÁRIA',299809.50,6,
                    'Teor do registro 1549.');
        INSERT INTO LivroAuxiliarPartes(Id, LivroAuxiliarId, ParteId,
               QualificacaoId, Credor) VALUES
            (1,1,100,1,1),      -- emitente (física)
            (2,1,101,2,1),      -- credor (jurídica)
            (3,1,102,2,1),      -- credor: a ARMADILHA do tbPessoa
            (4,1,103,3,0);      -- não resolve em lugar nenhum
        INSERT INTO LivroAuxiliarAverbacao(Id, LivroAuxiliarId, Averbacao, Data,
               TipoAverbacao, Finalizado, Teor)
            VALUES (10,1,1,'2020-07-10 00:00:00',2,1,
                    'AV-01/1549. AVERBAÇÃO DE BAIXA. Fica baixada a garantia.');
        INSERT INTO LivroAuxiliarAverbacaoPartes(Id, LivroAuxiliarAverbacaoId,
               ParteId, QualificacaoId) VALUES
            (100,10,100,1),     -- já é parte do registro  -> não repete
            (101,10,100,1),     -- repetida na própria averbação -> não repete
            (102,10,999,2);     -- NÃO é parte do registro -> entra no ato

        -- O REGISTRO 1315: sem teor, partes e uma averbação de retificação.
        INSERT INTO LivroAuxiliar(Id, Livro, Registro, Data, Numero, Titulo,
               ValorCompraVenda, Parcelas)
            VALUES (2,'3',1315,'2022-02-14 00:00:00','81.2012.5294.7847',
                    'CEDULA RURAL HIPOTECARIA',83640.00,1);
        INSERT INTO LivroAuxiliarPartes(Id, LivroAuxiliarId, ParteId,
               QualificacaoId, Credor) VALUES (5,2,101,2,1);
        INSERT INTO LivroAuxiliarAverbacao(Id, LivroAuxiliarId, Averbacao, Data,
               TipoAverbacao, Finalizado, Teor)
            VALUES (11,2,1,'2022-04-19 00:00:00',1,1,
                    'AV-01/1.315. Retificação de área.');

        -- O `tbOrtoga` — a tabela REAL das partes.
        INSERT INTO tbOrtoga(intCodigo, strTipoPessoa, strNome, PJ_RazaoSocial,
               strCPF, strCNPJ, strNacionalidade, strEstadoCivil) VALUES
            (100,'F','JOSÉ EXEMPLO LOPES MARTINS',NULL,'00000002488',NULL,
                 'BRASILEIRO','CASADO'),
            (101,'J',NULL,'BANCO DO BRASIL S/A',NULL,'00000010000127',
                 NULL,NULL),
            (102,'J',NULL,'BANCO DO NORDESTE DO BRASIL S.A',NULL,
                 '00000018000193',NULL,NULL),
            (104,'F','MARIA COM DOCUMENTO COM MASCARA',NULL,'000.000.013-25',
                 NULL,NULL,NULL);
        INSERT INTO tbOrtoga(intCodigo, strTipoPessoa, strNome, PJ_RazaoSocial,
               strCPF) VALUES (999,'F','MARIA AVALISTA',NULL,'11122233344');

        -- O `tbPessoa`, com o MESMO id 102 e OUTRA pessoa.
        INSERT INTO tbPessoa VALUES
            (100,'ALGUÉM COMPLETAMENTE DIFERENTE'),
            (102,'FULANO DO TBPESSOA EXEMPLO');
    """)
    # A parte sem máscara, para o teste do `so_digitos` (o acervo tem as duas).
    con.execute("INSERT INTO LivroAuxiliarPartes(Id, LivroAuxiliarId, ParteId,"
                " QualificacaoId, Credor) VALUES (6,2,104,3,0)")
    con.commit()
    return con


def _registro_ja_gravado(con: sqlite3.Connection, id_no_acervo: int,
                         numero: int) -> int:
    """Grava um registro como uma rodada ANTERIOR da carga teria gravado.

    É a situação de quem aplicou esta versão depois de já ter rodado a carga
    antiga: o registro existe, o ato R-1 existe, e não há parte nenhuma.
    """
    cur = con.execute(
        """INSERT INTO ra_registros(numero, livro, origem, origem_chave, criado_em)
           VALUES (?, '3', 'EOFICIO', ?, ?)""",
        (numero, f"LivroAuxiliar:{id_no_acervo}", AGORA))
    registro_id = int(cur.lastrowid)
    con.execute(
        """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato, origem,
               origem_chave, criado_em) VALUES (?,'R',1,?,?,?,?)""",
        (registro_id, AGORA, "EOFICIO", f"LivroAuxiliar:{id_no_acervo}:R1", AGORA))
    return registro_id


def _contagem(carga: AC.Carga, trecho: str) -> int:
    """Um número das contagens da carga, achado pelo rótulo ou por um trecho.

    Pelo trecho, e não pelo rótulo inteiro: o que o teste guarda é o FATO, e
    ele não deve ficar vermelho porque a frase da tela ganhou uma vírgula.
    O rótulo exato ganha do trecho — há rótulos que contêm outros
    («averbações» está dentro de «partes das averbações que já eram parte…»).
    """
    if trecho in carga.contagens:
        return carga.contagens[trecho]
    achados = {k: v for k, v in carga.contagens.items() if trecho in k}
    assert len(achados) == 1, \
        f"esperava UMA contagem com {trecho!r}; achei {list(carga.contagens)}"
    return next(iter(achados.values()))


def _parte(con: sqlite3.Connection, nome: str) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM ra_partes WHERE nome=?", (nome,)).fetchone()


# ------------------------------------------------- as partes do registro


def test_as_partes_do_registro_entram_com_nome_documento_e_papel():
    con, acervo = banco(), acervo_falso()
    AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    emitente = _parte(con, "JOSÉ EXEMPLO LOPES MARTINS")
    credor = _parte(con, "BANCO DO BRASIL S/A")
    assert emitente is not None and credor is not None
    # O TIPO DIZ ONDE O DOCUMENTO ESTÁ, e não o tamanho do que estiver escrito.
    assert (emitente["documento_tipo"], emitente["documento_numero"]) == \
        ("CPF", "00000002488")
    assert (credor["documento_tipo"], credor["documento_numero"]) == \
        ("CNPJ", "00000010000127")
    # O PAPEL é a palavra do acervo: é ela que o balcão lê na ficha hoje.
    assert emitente["papel"] == "Emitente/Creditado"
    assert credor["papel"] == "CREDOR(A)"
    assert emitente["origem"] == "EOFICIO"
    assert emitente["origem_chave"] == "LivroAuxiliarPartes:1"
    # A parte do REGISTRO não se prende a ato nenhum — ela é do registro.
    assert emitente["ato_id"] is None


def test_o_documento_sai_em_digitos_como_no_livro_2():
    """A busca por documento tem de achar os dois livros do mesmo jeito."""
    con, acervo = banco(), acervo_falso()
    AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    parte = _parte(con, "MARIA COM DOCUMENTO COM MASCARA")
    assert parte["documento_numero"] == "00000001325"


def test_a_parte_vem_do_tbOrtoga_e_nao_do_tbPessoa():
    """O MESMO id aponta para pessoas diferentes nas duas tabelas.

    Medido no acervo desta casa: o id 10018 é o «BANCO DO BRASIL S/A» no
    `tbOrtoga` e «FULANO DO TBPESSOA EXEMPLO» no `tbPessoa`. Quem escolhesse a
    tabela pelo nome traria o credor errado — e as duas linhas existem, as
    duas têm nome, e nenhuma releitura desconfiaria.
    """
    con, acervo = banco(), acervo_falso()
    AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    nomes = [r["nome"] for r in con.execute("SELECT nome FROM ra_partes")]
    assert "BANCO DO NORDESTE DO BRASIL S.A" in nomes
    assert "FULANO DO TBPESSOA EXEMPLO" not in nomes
    assert "ALGUÉM COMPLETAMENTE DIFERENTE" not in nomes


def test_parte_que_o_tbOrtoga_nao_resolve_e_contada_e_nao_entra():
    """Não se inventa nome, e o que não entrou fica MEDIDO.

    A conta fecha com o acervo de ensaio: `LivroAuxiliarPartes` tem 6 linhas,
    a 4ª aponta para uma pessoa que o `tbOrtoga` não conhece, e as outras
    cinco entram — mais a parte própria da averbação, que são 6 em `ra_partes`.
    """
    con, acervo = banco(), acervo_falso()
    carga = AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    assert _contagem(carga, "não resolveu") == 1
    assert con.execute("SELECT COUNT(*) FROM ra_partes").fetchone()[0] == 6


# ----------------------------------------------- as averbações como ato


def test_a_averbacao_entra_como_ato_com_o_numero_a_data_e_o_texto_dela():
    con, acervo = banco(), acervo_falso()
    AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    reg = con.execute("SELECT id FROM ra_registros WHERE numero=1549").fetchone()
    ato = con.execute("SELECT * FROM ra_atos WHERE registro_id=? AND tipo='AV'",
                      (reg["id"],)).fetchone()
    assert ato is not None, "a averbação de baixa não entrou"
    # O NÚMERO VEM DO ACERVO: a averbação diz o próprio número no texto
    # («AV-01/1549»), e renumerar faria o sistema discordar do papel.
    assert ato["numero"] == 1
    assert ato["data_ato"] == "2020-07-10"
    assert ato["teor"].startswith("AV-01/1549")
    assert ato["origem"] == "EOFICIO"
    assert ato["origem_chave"] == "LivroAuxiliarAverbacao:10"
    # O TIPO DA AVERBAÇÃO NÃO VAI PARA `natureza`: o vocabulário daquela coluna
    # é o de `ra_registro.NATUREZAS`, e as palavras do tipo já estão dentro do
    # texto, que entra inteiro.
    assert ato["natureza"] is None


def test_a_parte_da_averbacao_que_ja_e_parte_do_registro_nao_se_repete():
    """As 10 linhas da averbação nomeiam 7 pessoas que já estão no registro."""
    con, acervo = banco(), acervo_falso()
    carga = AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    nomes = [r["nome"] for r in con.execute("SELECT nome FROM ra_partes")]
    assert nomes.count("JOSÉ EXEMPLO LOPES MARTINS") == 1
    # As duas linhas da averbação (a parte e a repetida dela) foram contadas.
    assert _contagem(carga, "não repetidas") == 2


def test_a_parte_da_averbacao_que_nao_e_parte_do_registro_entra_no_ato():
    """O que a averbação tem de próprio não se perde."""
    con, acervo = banco(), acervo_falso()
    AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    avalista = _parte(con, "MARIA AVALISTA")
    assert avalista is not None, "a parte própria da averbação não entrou"
    ato = con.execute(
        "SELECT id FROM ra_atos WHERE origem_chave='LivroAuxiliarAverbacao:10'"
    ).fetchone()
    assert avalista["ato_id"] == ato["id"]
    assert avalista["documento_numero"] == "11122233344"
    assert avalista["papel"] == "CREDOR(A)"


def test_o_numero_do_ato_ocupado_nao_e_roubado():
    """Ato lavrado no balcão não se renumera nem se apaga."""
    con, acervo = banco(), acervo_falso()
    registro_id = _registro_ja_gravado(con, 1, 1549)
    con.execute(
        """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato, teor,
               origem, criado_em) VALUES (?,'AV',1,'2026-09-01',
               'Averbação lavrada no balcão.','MANUAL',?)""",
        (registro_id, AGORA))
    carga = AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    assert _contagem(carga, "ocupado") == 1
    atos = [dict(r) for r in con.execute(
        "SELECT * FROM ra_atos WHERE registro_id=? AND tipo='AV'", (registro_id,))]
    assert len(atos) == 1
    assert atos[0]["origem"] == "MANUAL"
    assert atos[0]["teor"] == "Averbação lavrada no balcão."


def test_a_baixa_nao_muda_a_situacao_do_registro():
    """O acervo não tem marca de cancelamento, e o TEXTO não decide.

    Medido em 18/09/2026: das 5 averbações do acervo, 3 são de BAIXA
    (registros 1315, 1409 e 1560) e os três registros continuam `ATIVO` aqui.
    Decidir pelo texto da averbação seria a máquina lavrando o ato — quem
    cancela é o oficial, com a caneta dele.
    """
    con, acervo = banco(), acervo_falso()
    AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    reg = con.execute("SELECT * FROM ra_registros WHERE numero=1549").fetchone()
    assert "BAIXA" in con.execute(
        "SELECT teor FROM ra_atos WHERE registro_id=? AND tipo='AV'",
        (reg["id"],)).fetchone()["teor"]
    assert reg["situacao"] == "ATIVO"


# ---------------------------------------------------- repetível, e a prévia


def test_a_passada_e_repetivel():
    con, acervo = banco(), acervo_falso()
    AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    antes = (con.execute("SELECT COUNT(*) FROM ra_partes").fetchone()[0],
             con.execute("SELECT COUNT(*) FROM ra_atos").fetchone()[0])
    carga = AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    depois = (con.execute("SELECT COUNT(*) FROM ra_partes").fetchone()[0],
              con.execute("SELECT COUNT(*) FROM ra_atos").fetchone()[0])
    assert antes == depois
    # As 5 partes do registro que entraram na primeira rodada + a parte própria
    # da averbação — o rótulo é um só para as duas seções, de propósito: é a
    # mesma pergunta («esta chave já está aqui?») nos dois lugares.
    assert _contagem(carga, "partes que já estavam") == 6
    assert _contagem(carga, "averbações que já estavam") == 2


def test_a_passada_alcanca_os_registros_que_ja_estavam_gravados():
    """Quem rodou a carga antes de 18/09/2026 tem o registro e não tem a parte.

    `_executar` só chama o `depois` de quem ENTROU AGORA: numa segunda rodada
    os registros voltam como `repetidos`, e as partes e as averbações nunca
    chegariam neles. É o mesmo defeito que a passada da filiação do RCPN e a
    do devedor do Protesto tiveram de resolver.
    """
    con, acervo = banco(), acervo_falso()
    registro_id = _registro_ja_gravado(con, 1, 1549)
    carga = AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    assert carga.inseridos == 1        # só o registro 1315 entrou agora
    assert carga.repetidos == 1        # o 1549 já estava
    assert con.execute("SELECT COUNT(*) FROM ra_partes WHERE registro_id=?",
                       (registro_id,)).fetchone()[0] == 4
    assert con.execute("SELECT COUNT(*) FROM ra_atos WHERE registro_id=? "
                       "AND tipo='AV'", (registro_id,)).fetchone()[0] == 1


def test_a_previa_conta_sem_gravar():
    """A tela mostra o que vai acontecer ANTES de acontecer."""
    con, acervo = banco(), acervo_falso()
    previa = AC.previa_registro_auxiliar(con, acervo)
    assert previa["total_no_acervo"] == 2
    assert previa["total_novos"] == 2
    assert previa["total_ja"] == 0
    assert previa["averbacoes_no_acervo"] == 2
    assert previa["averbacoes_novas"] == 2
    assert previa["partes_no_acervo"] == 6
    assert previa["partes_novas"] == 6
    assert previa["partes_que_entram"] == 5     # a 6ª não tem pessoa no acervo
    assert previa["faltam"] == 9                # 2 + 2 + 5 — o número do botão
    assert previa["tem_ortoga"] is True
    assert [a["numero"] for a in previa["amostras_novos"]] == [1315, 1549]
    # E ela NÃO GRAVOU NADA.
    for tabela in ("ra_registros", "ra_atos", "ra_partes"):
        assert con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0] == 0


def test_a_previa_de_depois_da_carga_conta_tudo_como_ja_importado():
    con, acervo = banco(), acervo_falso()
    AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    previa = AC.previa_registro_auxiliar(con, acervo)
    assert previa["total_novos"] == 0
    assert previa["total_ja"] == 2
    assert previa["averbacoes_novas"] == 0
    assert previa["ja_no_cartorio"] == 2
    # A SEXTA PARTE NUNCA VAI ENTRAR: ela aponta para uma pessoa que o
    # `tbOrtoga` não conhece. A prévia conta o que falta em `ra_partes` (1) e
    # diz POR QUE ele não entra (`partes_sem_pessoa` = 1) — sem o segundo
    # número a tela diria «1 parte nova» para sempre.
    assert previa["partes_novas"] == 1
    assert previa["partes_sem_pessoa"] == 1
    # E O BOTÃO NÃO PEDE O QUE NÃO ENTRA: acabou o que fazer, `faltam` é zero
    # e a tela diz «nada novo» em vez de «faltam 1» para sempre.
    assert previa["partes_que_entram"] == 0
    assert previa["faltam"] == 0


# ------------------------------------------------------- o que não pode cair


def test_acervo_sem_as_tabelas_do_livro_3_nao_derruba_a_carga():
    """Outro sistema pode ter o registro e não ter as partes nem o tbOrtoga."""
    con = banco()
    acervo = sqlite3.connect(":memory:")
    acervo.row_factory = sqlite3.Row
    acervo.executescript("""
        CREATE TABLE LivroAuxiliar (Id INTEGER, Livro TEXT, Registro REAL,
            Data TEXT, Numero TEXT, Titulo TEXT, ValorCompraVenda REAL,
            Parcelas INTEGER, VencimentoInicial TEXT, VencimentoFinal TEXT,
            Juros TEXT, Garantia TEXT, Condicoes TEXT, strCNM TEXT, Teor TEXT);
        INSERT INTO LivroAuxiliar VALUES (1,'3',1549,'2020-06-08','40/01800-8',
            'CÉDULA RURAL', 1000.0, 1, '2020-07-08', '2020-07-08', NULL, NULL,
            NULL, NULL, 'Teor do registro.');
    """)
    carga = AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    assert carga.inseridos == 1
    assert _contagem(carga, "sem `LivroAuxiliarPartes`") == 1
    assert con.execute("SELECT COUNT(*) FROM ra_partes").fetchone()[0] == 0
    # E NENHUMA LINHA SOBRA PARA CONTAR: sem `LivroAuxiliarPartes` não há parte
    # para o `tbOrtoga` resolver, e o aviso do `tbOrtoga` não aparece — quem
    # não achou linha nenhuma não tem o que não ter resolvido.
    assert not [k for k in carga.contagens if "tbOrtoga" in k]


def test_registro_fora_do_livro_3_nao_e_tocado():
    """O que foi digitado à mão tem `origem='MANUAL'` e chave nula."""
    con, acervo = banco(), acervo_falso()
    cur = con.execute(
        """INSERT INTO ra_registros(numero, livro, origem, criado_em)
           VALUES (1198, '3', 'IMPORTACAO', ?)""", (AGORA,))
    manual = int(cur.lastrowid)
    con.execute(
        """INSERT INTO ra_partes(registro_id, nome, papel, origem)
           VALUES (?,'PARTE DIGITADA À MÃO','Emitente','IMPORTACAO')""", (manual,))
    AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
    linhas = [dict(r) for r in con.execute(
        "SELECT * FROM ra_partes WHERE registro_id=?", (manual,))]
    assert len(linhas) == 1
    assert linhas[0]["nome"] == "PARTE DIGITADA À MÃO"


# ---------------------------------------------------- contra o acervo REAL


@pytest.mark.skipif(not ACERVO_REAL.exists(), reason="sem o acervo nesta máquina")
def test_contra_o_acervo_real_do_livro_3():
    """O ensaio que pega mapeamento errado de coluna — medido em 18/09/2026.

    Números medidos na produção naquele dia: 14 registros, 25 partes de
    registro, 5 averbações, e as 10 linhas de parte das averbações nomeando
    pessoas que JÁ estão entre as 25 do registro (por isso nenhuma delas é
    repetida).
    """
    con = banco()
    with AC.abrir_acervo(ACERVO_REAL) as acervo:
        carga = AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
        assert carga.inseridos == 14
        assert con.execute("SELECT COUNT(*) FROM ra_registros").fetchone()[0] == 14
        assert con.execute("SELECT COUNT(*) FROM ra_partes").fetchone()[0] == 25
        assert _contagem(carga, "não repetidas") == 10
        assert _contagem(carga, "partes do registro") == 25
        assert _contagem(carga, "averbações") == 5
        # As cinco averbações têm texto, e cada uma é AV-1 — é o que o acervo
        # diz no próprio texto dela («AV-01/1.315»).
        avs = [dict(r) for r in con.execute(
            "SELECT * FROM ra_atos WHERE tipo='AV'")]
        assert len(avs) == 5
        assert all(a["numero"] == 1 for a in avs)
        assert all((a["teor"] or "").strip() for a in avs)
        assert all(a["origem"] == "EOFICIO" for a in avs)
        # O CNPJ do Banco do Brasil mantém os zeros à esquerda, e o credor é o
        # do `tbOrtoga` — o `tbPessoa` aponta para outra pessoa no mesmo id.
        bb = con.execute("SELECT * FROM ra_partes WHERE nome='BANCO DO BRASIL S/A'"
                         ).fetchone()
        # (o número em si é do acervo real e não se escreve aqui: o público não o leva)
        assert len(bb["documento_numero"]) == 14
        assert bb["documento_numero"].startswith("0000")
        nomes = [r["nome"] for r in con.execute("SELECT nome FROM ra_partes")]
        # A pessoa que o `tbPessoa` guarda no mesmo id do banco é de verdade, e
        # o nome dela vem do próprio acervo (sanitização B3, 11/10/2026).
        id_do_banco = acervo.execute(
            "SELECT intCodigo FROM tbOrtoga WHERE strNome = 'BANCO DO BRASIL S/A'"
        ).fetchone()[0]
        outro = acervo.execute(
            "SELECT strRazaoSocial FROM tbPessoa WHERE intCodigoPessoa = ?",
            (id_do_banco,)).fetchone()[0]
        assert outro and outro not in nomes
        # E a passada é repetível contra o acervo de verdade.
        AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)
        assert con.execute("SELECT COUNT(*) FROM ra_partes").fetchone()[0] == 25
        assert con.execute("SELECT COUNT(*) FROM ra_atos").fetchone()[0] == 19
