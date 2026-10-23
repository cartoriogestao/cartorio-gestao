"""
Testes da certidao de protesto.

O QUE ELES CONFEREM
    A regra que importa mais do que todas: **nao se emite negativa sobre quem
    tem protesto**. Negativa errada e a certidao que faz o banco emprestar
    para quem nao devia, e ela nao se desfaz depois.

    E o outro lado: **apontamento nao e protesto**. Titulo apontado e pago no
    triduo nunca foi protestado, e certidao que o mostrasse mentiria contra a
    pessoa. Medido no acervo: dos 189 titulos pagos, so 4 chegaram a protesto.

    Mais: o teor CONGELA na emissao — protesto lavrado amanha nao muda a
    certidao de hoje, porque mudar seria reescrever o que a serventia ja
    afirmou.

    Ha tambem um teste contra o acervo REAL, que roda so onde ele existe.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — referencia acervo_eoficio ou sqlite de producao
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto_certidao as PC
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema, normalizar_nome

HOJE = "2026-08-25"
AGORA = "2026-08-25T18:00:00"
ACERVO_REAL = Path(r"C:\ProgramData\CartorioGestao") / "acervo_eoficio.sqlite3"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo(con, *, nome="JOSÉ DA SILVA", documento="04785512388",
           numero="9911/1", protesto="2024-03-10", cancelamento=None,
           apenas_apontado=False, cedente="BANCO DO NORDESTE",
           livro=5, folha=120) -> int:
    """Um titulo com devedor e, salvo pedido em contrario, ato de PROTESTO."""
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, valor_centavos,
               saldo_centavos, data_emissao, data_vencimento, cedente_nome,
               situacao, origem, criado_em)
           VALUES ('DMI',?,148278,148278,'2024-01-05','2024-02-05',?,?,
                   'MANUAL',?)""",
        (numero, cedente, "APONTADO" if apenas_apontado else "PROTESTADO",
         AGORA))
    titulo_id = int(cur.lastrowid)
    con.execute(
        """INSERT INTO pt_devedores(titulo_id, nome, nome_norm, documento_tipo,
               documento_numero, cidade, uf)
           VALUES (?,?,?,?,?,'Cidade Exemplo','MA')""",
        (titulo_id, nome, normalizar_nome(nome),
         PC.tipo_do_documento(documento), documento))
    con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, folha, numero_ordem, data_ato,
               origem, criado_em)
           VALUES (?,'APONTAMENTO',3,912,'2024-02-20','MANUAL',?)""",
        (titulo_id, AGORA))
    if not apenas_apontado:
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, folha, data_ato,
                   detalhe_json, origem, criado_em)
               VALUES (?,'PROTESTO',?,?,?,'MANUAL',?)""",
            (titulo_id, folha, protesto,
             '{"livro_do_acervo": ' + str(livro) + '}', AGORA))
    if cancelamento:
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato,
                   motivo_cancelamento, origem, criado_em)
               VALUES (?,'CANCELAMENTO',?,'Título quitado.','MANUAL',?)""",
            (titulo_id, cancelamento, AGORA))
        con.execute("UPDATE pt_titulos SET situacao='CANCELADO' WHERE id=?",
                    (titulo_id,))
    return titulo_id


# ------------------------------------------------------------------ a busca


def test_a_busca_acha_pelo_nome_e_pelo_documento_com_pontuacao():
    # Quem pede traz o CPF com ponto e traco; no banco ele esta so com
    # digitos. Casar por digitos e o que faz a certidao achar a pessoa.
    con = banco()
    titulo(con)
    assert len(PC.buscar(con, nome="josé da silva")) == 1
    assert len(PC.buscar(con, nome="SILVA")) == 1
    assert len(PC.buscar(con, documento="047.855.123-88")) == 1
    assert len(PC.buscar(con, documento="04785512388")) == 1
    assert PC.buscar(con, nome="OUTRA PESSOA") == []


def test_com_o_cpf_a_busca_casa_pelo_documento_e_o_nome_nao_amplia():
    # CN-MA art. 906, § 2º (LD11). Era documento OU nome: quem pedia com o
    # CPF certo e um nome parcial levava o protesto e o protocolo do
    # homonimo de outro CPF — a positiva que mente contra a pessoa, e o Livro
    # de Protocolo de terceiros. Com o documento, so ele decide; sem ele, o
    # nome continua achando todos.
    import protesto_livros as PLIV
    con = banco()
    titulo(con, nome="JOSÉ DA SILVA", documento="00000000191", numero="1/1")
    titulo(con, nome="MARIA DA SILVA", documento="00000000272", numero="2/1")
    for pedido in ({"nome": "SILVA", "documento": "000.000.001-91"},
                   {"nome": "MARIA DA SILVA", "documento": "00000000191"}):
        assert [a["devedor"] for a in PC.buscar(con, **pedido)] == [
            "JOSÉ DA SILVA"], pedido
        assert [l["devedor"] for l in PLIV.protocolo_do_devedor(con, **pedido)
                ] == ["JOSÉ DA SILVA"], pedido
    assert len(PC.buscar(con, nome="SILVA")) == 2
    assert len(PLIV.protocolo_do_devedor(con, nome="SILVA")) == 2


def test_o_nome_pedido_e_texto_e_nao_curinga():
    # O `%` e o `_` digitados sao letras, e nao o curinga do ILIKE (LD11): o
    # nome «%» casava com todos os devedores da casa, e a certidao a pedido
    # escrito certificava o Livro de Protocolo de terceiros (CN-MA art. 906,
    # § 2º). O `_` que esta de verdade no nome continua achando.
    import protesto_livros as PLIV
    con = banco()
    titulo(con, nome="JOSÉ DA SILVA", documento="00000000191", numero="1/1")
    for curinga in ("%", "_", "\\", "%silva", "jos_"):
        assert PC.buscar(con, nome=curinga) == [], curinga
        assert PLIV.protocolo_do_devedor(con, nome=curinga) == [], curinga
    titulo(con, nome="ALFA_BETA COMERCIO", documento="00000001000055",
           numero="2/1")
    for nome, achados in (("alfa_beta", ["ALFA_BETA COMERCIO"]),
                          ("alfa%beta", []), ("alfaxbeta", [])):
        assert [a["devedor"] for a in PC.buscar(con, nome=nome)] == achados, nome
        assert [l["devedor"] for l in PLIV.protocolo_do_devedor(
            con, nome=nome)] == achados, nome


def test_o_devedor_gravado_sem_documento_sai_na_certidao_pedida_com_o_cpf_e_o_mesmo_nome():
    # A RESSALVA DA REVISAO DO LD11 (LD12). So pelo documento, o titulo cujo
    # devedor foi apontado sem CPF/CNPJ sumia da certidao pedida com o CPF
    # dele, e ela saia NEGATIVA para quem tem protesto. O nome inteiro — sem
    # acento, sem caixa, sem espaco a mais — acha o devedor sem documento
    # (nulo ou vazio), e o achado vem marcado para o escrevente conferir.
    import protesto_livros as PLIV
    pedido = {"nome": "jose da  silva", "documento": "000.000.001-91"}
    for gravado in (None, "", "..."):
        # Uma conexao por volta, fechada no fim: a emissao trava a numeracao
        # ate a transacao acabar, e a volta seguinte esperaria por ela.
        con = banco()
        try:
            titulo(con, nome="JOSÉ DA SILVA", documento=gravado, numero="1/1")
            achados = PC.buscar(con, **pedido)
            assert [(a["numero_titulo"], a["so_pelo_nome"])
                    for a in achados] == [("1/1", True)], gravado
            assert PC.tipo_para(achados) == "POSITIVA"
            [linha] = PLIV.protocolo_do_devedor(con, **pedido)
            assert (linha["titulo"], linha["so_pelo_nome"]) == ("1/1", True), gravado
            r = PC.emitir(con, nome="JOSÉ DA SILVA",
                          documento=pedido["documento"], achados=achados,
                          hoje=HOJE, agora=AGORA)
            assert r["tipo"] == "POSITIVA" and r["so_pelo_nome"] == 1
            assert "Título n. 1/1" in r["teor"]
            # A MARCA NAO MUDA O TEOR: a mesma certidao, com os achados sem
            # ela, diz palavra por palavra o mesmo.
            sem_marca = [{k: v for k, v in a.items() if k != "so_pelo_nome"}
                         for a in achados]
            outra = PC.emitir(con, nome="JOSÉ DA SILVA",
                              documento=pedido["documento"], achados=sem_marca,
                              hoje=HOJE, agora=AGORA)
            assert outra["teor"] == r["teor"] and outra["so_pelo_nome"] == 0
        finally:
            con.close()


def test_com_o_cpf_o_homonimo_de_outro_documento_e_o_nome_parcial_ficam_de_fora():
    # O que o LD11 quis continua (LD12): o homonimo que tem OUTRO CPF nao entra
    # na certidao de quem pediu. E o nome que acha o devedor sem documento e o
    # nome INTEIRO: com o CPF na mao, «SILVA» traria todos os SILVA sem
    # documento a positiva de quem pediu — e «JOSÉ DA SILVA FILHO» e outra
    # pessoa.
    import protesto_livros as PLIV
    con = banco()
    titulo(con, nome="JOSÉ DA SILVA", documento="00000000191", numero="1/1")
    titulo(con, nome="JOSÉ DA SILVA", documento="00000000272", numero="2/1")
    titulo(con, nome="JOSÉ DA SILVA", documento=None, numero="3/1")
    titulo(con, nome="JOSÉ DA SILVA FILHO", documento=None, numero="4/1")
    pedido = {"nome": "JOSÉ DA SILVA", "documento": "000.000.001-91"}
    assert [(a["numero_titulo"], a["so_pelo_nome"])
            for a in PC.buscar(con, **pedido)] == [("1/1", False), ("3/1", True)]
    assert [(l["titulo"], l["so_pelo_nome"])
            for l in PLIV.protocolo_do_devedor(con, **pedido)] == [
        ("1/1", False), ("3/1", True)]
    for parcial in ("SILVA", "JOSÉ", "DA SILVA FILHO"):
        com_cpf = {"nome": parcial, "documento": "00000000191"}
        assert [a["numero_titulo"] for a in PC.buscar(con, **com_cpf)] == [
            "1/1"], parcial
        assert [l["titulo"] for l in PLIV.protocolo_do_devedor(
            con, **com_cpf)] == ["1/1"], parcial
    # Com o CPF de quem nao tem titulo nenhum, o nome inteiro ainda acha o
    # devedor sem documento — e so ele.
    assert [a["numero_titulo"] for a in PC.buscar(
        con, nome="JOSÉ DA SILVA", documento="00000000353")] == ["3/1"]


def test_so_com_o_nome_a_busca_e_a_de_antes_e_marca_quem_nao_tem_documento():
    # Sem documento no pedido, nada muda (LD12): o nome contido no gravado,
    # sem acento e sem caixa, acha com e sem documento. A marca so diz quem
    # foi gravado sem ele.
    import protesto_livros as PLIV
    con = banco()
    titulo(con, nome="JOSÉ DA SILVA", documento="00000000191", numero="1/1")
    titulo(con, nome="MARIA DA SILVA", documento=None, numero="2/1")
    titulo(con, nome="OUTRA PESSOA", documento=None, numero="3/1")
    assert [(a["devedor"], a["so_pelo_nome"])
            for a in PC.buscar(con, nome="silva")] == [
        ("JOSÉ DA SILVA", False), ("MARIA DA SILVA", True)]
    assert [(l["devedor"], l["so_pelo_nome"])
            for l in PLIV.protocolo_do_devedor(con, nome="silva")] == [
        ("JOSÉ DA SILVA", False), ("MARIA DA SILVA", True)]
    assert PC.titulos_so_pelo_nome(PC.buscar(con, nome="silva")) == 1


def test_com_o_cpf_o_curinga_no_nome_nao_traz_o_devedor_sem_documento():
    # O nome que acha o devedor sem documento continua sendo TEXTO (LD12, com
    # o escape do LD11): «jos_ da silva» nao e «jose da silva», e «%» nao e
    # todo mundo.
    import protesto_livros as PLIV
    con = banco()
    titulo(con, nome="JOSÉ DA SILVA", documento=None, numero="1/1")
    for curinga in ("%", "_", "\\", "%silva", "%da silva", "jos_ da silva",
                    "jose da silv_", "jose da silva%"):
        com_cpf = {"nome": curinga, "documento": "00000000191"}
        assert PC.buscar(con, **com_cpf) == [], curinga
        assert PLIV.protocolo_do_devedor(con, **com_cpf) == [], curinga
    assert len(PC.buscar(con, nome="jose da silva", documento="00000000191")) == 1


def test_a_certidao_a_pedido_escrito_conta_o_apontamento_que_entrou_so_pelo_nome():
    # O Livro de Protocolo da certidao a pedido escrito (CN-MA art. 906, § 2º)
    # segue a mesma regra (LD12): o apontamento do devedor gravado sem
    # documento entra, e conta para o aviso ao escrevente. A tela, antes de
    # emitir, faz a mesma conta (`protocolo_a_certificar`).
    con = banco()
    titulo(con, nome="JOSÉ DA SILVA", documento=None, numero="1/1",
           apenas_apontado=True)
    pedido = {"nome": "JOSÉ DA SILVA", "documento": "00000000191"}
    achados = PC.buscar(con, **pedido, autorizacao="DEVEDOR_ESCRITO")
    assert achados == []
    linhas = PC.protocolo_a_certificar(
        con, **pedido, desde=PC.data_limite(HOJE), achados=achados,
        autorizacao="DEVEDOR_ESCRITO")
    assert [(l["titulo"], l["so_pelo_nome"]) for l in linhas] == [("1/1", True)]
    assert PC.protocolo_a_certificar(
        con, **pedido, desde=PC.data_limite(HOJE), achados=achados,
        autorizacao=None) == []
    r = PC.emitir(con, **pedido, achados=achados, hoje=HOJE, agora=AGORA,
                  autorizacao="DEVEDOR_ESCRITO", requerente="JOSÉ DA SILVA")
    assert r["tipo"] == "NEGATIVA" and r["so_pelo_nome"] == 1
    assert "título n. 1/1" in r["teor"]
    assert "1 título entrou só pelo NOME" in PC.aviso_so_pelo_nome(1)
    assert "2 títulos entraram" in PC.aviso_so_pelo_nome(2)


def test_a_busca_sem_nome_e_sem_documento_e_recusada():
    with pytest.raises(PC.CertidaoError) as erro:
        PC.buscar(banco())
    assert "não há o que buscar" in str(erro.value)


def test_apontamento_nao_e_protesto():
    # A REGRA QUE PROTEGE O DEVEDOR. Titulo apontado e pago no triduo nunca
    # foi protestado; certidao que o mostrasse mentiria contra a pessoa.
    con = banco()
    titulo(con, apenas_apontado=True)
    assert PC.buscar(con, nome="JOSÉ DA SILVA") == []
    assert PC.tipo_para([]) == "NEGATIVA"


def test_o_periodo_limita_a_busca():
    con = banco()
    titulo(con, protesto="2019-05-02")
    assert PC.buscar(con, nome="SILVA", desde="2021-08-25") == []
    assert len(PC.buscar(con, nome="SILVA", desde="2018-01-01")) == 1


def test_a_busca_traz_o_lugar_do_protesto_e_a_baixa():
    con = banco()
    titulo(con, cancelamento="2024-06-01")
    # O cancelado só aparece com a autorização da lei (14/10/2026).
    a = PC.buscar(con, nome="SILVA", autorizacao="DEVEDOR_ESCRITO")[0]
    assert a["livro"] == 5 and a["folha"] == 120
    assert a["data_protesto"] == "2024-03-10"
    assert a["cancelado"] is True
    assert a["data_cancelamento"] == "2024-06-01"


# ------------------------------------------------------------- que tipo cabe


def test_o_tipo_sai_do_que_se_achou():
    con = banco()
    assert PC.tipo_para(PC.buscar(con, nome="NINGUÉM")) == "NEGATIVA"
    titulo(con, numero="1/1")
    assert PC.tipo_para(PC.buscar(con, nome="SILVA")) == "POSITIVA"
    con2 = banco()
    titulo(con2, numero="2/1", cancelamento="2024-06-01")
    # Até 14/10/2026 o cancelado entrava sozinho e saía «CANCELAMENTO» a
    # requerimento verbal. Lei 9.492, art. 27, § 2º; CN-MA arts. 944 e 948:
    # sem pedido escrito do devedor ou ordem judicial, ele não entra.
    assert PC.tipo_para(PC.buscar(con2, nome="SILVA")) == "NEGATIVA"
    assert PC.tipo_para(PC.buscar(con2, nome="SILVA",
                                  autorizacao="DEVEDOR_ESCRITO")) == "CANCELAMENTO"


def test_um_protesto_em_pe_no_meio_de_cancelados_faz_positiva():
    # Basta um protesto vivo para a certidao ser positiva: dizer
    # "cancelamento" ali esconderia o que ainda existe.
    con = banco()
    titulo(con, numero="1/1", cancelamento="2024-06-01")
    titulo(con, numero="2/1")
    assert PC.tipo_para(PC.buscar(con, nome="SILVA")) == "POSITIVA"


# ---------------------------------------------------------------- o teor


def test_a_negativa_diz_o_periodo_e_o_nome():
    con = banco()
    r = PC.emitir(con, nome="MARIA DAS DORES", documento="04785512388",
                  achados=[], hoje=HOJE, agora=AGORA)
    assert r["tipo"] == "NEGATIVA"
    assert "NÃO ENCONTREI protesto contra MARIA DAS DORES" in r["teor"]
    assert "CPF: 047.855.123-88" in r["teor"]
    assert "Período de Busca: 5 Anos" in r["teor"]
    assert "a partir do mês de Agosto de 2021" in r["teor"]


def test_sem_requerente_sai_a_requerimento_verbal_como_a_casa_escreve():
    # E o que as 44 negativas do acervo dizem. Informado o requerente, ele e
    # quem aparece: dizer "verbal" sobre pedido escrito seria certificar o que
    # nao houve.
    con = banco()
    sem = PC.emitir(con, nome="X", documento="04785512388", achados=[], hoje=HOJE,
                    agora=AGORA)
    assert "a requerimento verbal de parte interessada" in sem["teor"]
    com = PC.emitir(con, nome="X", documento="04785512388", achados=[], hoje=HOJE,
                    agora=AGORA, requerente="BANCO DO BRASIL S.A.")
    assert "a requerimento de BANCO DO BRASIL S.A." in com["teor"]
    assert "verbal" not in com["teor"]


def test_a_positiva_lista_o_protesto_com_livro_folha_e_datas_do_balcao():
    con = banco()
    titulo(con)
    achados = PC.buscar(con, nome="SILVA")
    r = PC.emitir(con, nome="JOSÉ DA SILVA", documento="04785512388",
                  achados=achados, hoje=HOJE, agora=AGORA)
    assert r["tipo"] == "POSITIVA"
    assert "encontrei protesto contra JOSÉ DA SILVA" in r["teor"]
    assert "Título n. 9911/1" in r["teor"]
    assert "Livro 5, fl. 120" in r["teor"]
    # O cedente é o CREDOR; «apresentado por» ele estava errado até 14/10/2026.
    assert "credor BANCO DO NORDESTE" in r["teor"]
    # DATA DE BALCAO, e nao ISO: `10/03/2024`, como as 19 do acervo escrevem.
    assert "protestado em 10/03/2024" in r["teor"]
    assert "2024-03-10" not in r["teor"]


def test_a_certidao_de_cancelamento_fecha_com_o_art_26():
    con = banco()
    titulo(con, cancelamento="2024-06-01")
    achados = PC.buscar(con, nome="SILVA", autorizacao="DEVEDOR_ESCRITO")
    r = PC.emitir(con, nome="JOSÉ DA SILVA", documento="04785512388",
                  achados=achados, hoje=HOJE, agora=AGORA,
                  autorizacao="DEVEDOR_ESCRITO")
    assert r["tipo"] == "CANCELAMENTO"
    assert "a requerimento escrito do próprio devedor" in r["teor"]
    assert "CANCELADO em 01/06/2024" in r["teor"]
    assert "art. 26 da lei 9492/97" in r["teor"]
    assert "dou fé" in r["teor"]


def test_o_fecho_do_cancelamento_concorda_em_numero():
    # O acervo tem as duas formas, singular e plural. Sai a que couber.
    con = banco()
    titulo(con, numero="1/1", cancelamento="2024-06-01")
    um = PC.emitir(con, nome="JOSÉ DA SILVA", documento="04785512388",
                   achados=PC.buscar(con, nome="SILVA",
                                     autorizacao="DEVEDOR_ESCRITO"),
                   hoje=HOJE, agora=AGORA, autorizacao="DEVEDOR_ESCRITO")
    assert "no referido livro e folha consta a BAIXA" in um["teor"]
    titulo(con, numero="2/1", cancelamento="2024-07-01")
    dois = PC.emitir(con, nome="JOSÉ DA SILVA", documento="04785512388",
                     achados=PC.buscar(con, nome="SILVA",
                                       autorizacao="DEVEDOR_ESCRITO"),
                     hoje=HOJE, agora=AGORA, autorizacao="DEVEDOR_ESCRITO")
    assert "nos referidos livros e folhas constam as BAIXAS" in dois["teor"]


def test_cedente_igual_ao_devedor_nao_sai_no_teor():
    # Em 28 dos 1.366 titulos o acervo traz o mesmo codigo como cedente e como
    # devedor. Certificar que fulano apresentou protesto contra fulano seria
    # pôr no papel um engano que a carga so copiou.
    con = banco()
    titulo(con, cedente="JOSÉ DA SILVA")
    r = PC.emitir(con, nome="JOSÉ DA SILVA", documento="04785512388",
                  achados=PC.buscar(con, nome="SILVA"), hoje=HOJE, agora=AGORA)
    assert "credor JOSÉ" not in r["teor"]


# --------------------------------------------------------------- a emissao


def test_nao_se_emite_negativa_sobre_quem_tem_protesto():
    # A REGRA MAIS IMPORTANTE DESTE MODULO. Negativa errada e a certidao que
    # faz o banco emprestar para quem nao devia, e ela nao se desfaz depois.
    con = banco()
    titulo(con)
    achados = PC.buscar(con, nome="SILVA")
    with pytest.raises(PC.CertidaoError) as erro:
        PC.emitir(con, nome="JOSÉ DA SILVA", documento="04785512388", achados=achados,
                  hoje=HOJE, agora=AGORA, tipo="NEGATIVA")
    assert "achou 1 protesto" in str(erro.value)
    assert con.execute("SELECT COUNT(*) FROM pt_certidoes").fetchone()[0] == 0


def test_nao_se_emite_positiva_sem_protesto_nenhum():
    with pytest.raises(PC.CertidaoError) as erro:
        PC.emitir(banco(), nome="X", documento="04785512388", achados=[], hoje=HOJE,
                  agora=AGORA, tipo="POSITIVA")
    assert "a certidão que cabe é a NEGATIVA" in str(erro.value)


def test_certidao_sem_nome_e_recusada():
    with pytest.raises(PC.CertidaoError):
        PC.emitir(banco(), nome="   ", documento="04785512388", achados=[], hoje=HOJE,
                  agora=AGORA)


def test_a_numeracao_e_por_exercicio_e_nao_repete():
    con = banco()
    a = PC.emitir(con, nome="A", documento="04785512388", achados=[], hoje="2026-08-25",
                  agora=AGORA)
    b = PC.emitir(con, nome="B", documento="04785512388", achados=[], hoje="2026-12-31",
                  agora=AGORA)
    c = PC.emitir(con, nome="C", documento="04785512388", achados=[], hoje="2027-01-02",
                  agora=AGORA)
    assert (a["numero"], a["ano"]) == (1, 2026)
    assert (b["numero"], b["ano"]) == (2, 2026)
    assert (c["numero"], c["ano"]) == (1, 2027)   # exercício novo recomeça


def test_emitir_trava_a_numeracao_antes_de_ler_o_maior(monkeypatch):
    """Dois balcoes emitindo juntos leriam o mesmo `max(numero)+1`, e um deles
    cairia na UNIQUE(numero, ano) sem a certidao sair. No PostgreSQL nao ha o
    `busy_timeout` que serializava isso no SQLite: `emitir` trava o assunto
    `pt_certidoes.numero` antes de ler o maior. A tela de conferencia
    (`proximo_numero`) continua so lendo — nao trava nada."""
    import bd_nativo
    travadas: list[str] = []
    original = bd_nativo.Banco.travar

    def espiao(self, chave):
        travadas.append(chave)
        return original(self, chave)

    monkeypatch.setattr(bd_nativo.Banco, "travar", espiao)
    con = banco()
    PC.proximo_numero(con, 2026)
    assert travadas == []
    PC.emitir(con, nome="A", documento="04785512388", achados=[], hoje=HOJE,
              agora=AGORA)
    assert travadas == ["pt_certidoes.numero"]


def test_o_teor_congela_na_emissao():
    # Protesto lavrado amanha nao muda a certidao de hoje: mudar seria
    # reescrever o que a serventia ja afirmou, e a via do cliente ficaria
    # diferente da do banco.
    con = banco()
    r = PC.emitir(con, nome="JOSÉ DA SILVA", documento="04785512388", achados=[],
                  hoje=HOJE, agora=AGORA)
    titulo(con)                                    # o protesto vem depois
    guardada = PC.certidao(con, r["certidao_id"])
    assert "NÃO ENCONTREI" in guardada["teor"]
    assert guardada["achados"] == 0
    assert guardada["hash_certidao"] == r["hash"]


def test_o_hash_muda_quando_o_teor_muda():
    a = PC.hash_certidao(1, 2026, "X", "teor um", AGORA)
    b = PC.hash_certidao(1, 2026, "X", "teor dois", AGORA)
    assert a != b and len(a) == 64


def test_a_certidao_guarda_o_que_achou_congelado():
    con = banco()
    titulo(con)
    r = PC.emitir(con, nome="JOSÉ DA SILVA", documento="04785512388",
                  achados=PC.buscar(con, nome="SILVA"), hoje=HOJE, agora=AGORA,
                  finalidade="crédito bancário", usuario="TABELIÃO")
    linha = PC.certidao(con, r["certidao_id"])
    assert linha["achados"] == 1
    assert "9911/1" in linha["achados_json"]
    assert linha["documento"] == "04785512388"     # só dígitos
    assert linha["documento_tipo"] == "CPF"
    assert linha["finalidade"] == "crédito bancário"
    assert linha["emitida_por"] == "TABELIÃO"


# ------------------------------------------------------------- cancelar


def test_cancelar_a_certidao_exige_motivo_escrito():
    con = banco()
    r = PC.emitir(con, nome="X", documento="04785512388", achados=[], hoje=HOJE,
                  agora=AGORA)
    with pytest.raises(PC.CertidaoError) as erro:
        PC.cancelar(con, r["certidao_id"], motivo="erro", agora=AGORA)
    assert "dez letras" in str(erro.value)


def test_a_certidao_cancelada_guarda_o_teor_que_saiu():
    # Certidao errada nao se apaga: a via que o cliente levou ficaria sem par
    # no banco, e e essa via que alguem vai conferir.
    con = banco()
    r = PC.emitir(con, nome="X", documento="04785512388", achados=[], hoje=HOJE,
                  agora=AGORA)
    PC.cancelar(con, r["certidao_id"], motivo="emitida com o nome errado",
                agora=AGORA, usuario="TABELIÃO", selo_cancelado_tjma=True)
    linha = PC.certidao(con, r["certidao_id"])
    assert int(linha["cancelada"]) == 1
    assert linha["motivo_cancelamento"] == "emitida com o nome errado"
    assert linha["declaracao_selo_tjma_por"] == "TABELIÃO"
    assert "NÃO ENCONTREI" in linha["teor"]
    with pytest.raises(PC.CertidaoError) as erro:
        PC.cancelar(con, r["certidao_id"], motivo="de novo, por engano",
                    agora=AGORA)
    assert "já está cancelada" in str(erro.value)


# ------------------------------------------------------------ utilidades


@pytest.mark.parametrize("documento,esperado", [
    ("04785512388", "CPF"), ("047.855.123-88", "CPF"),
    ("00000017000149", "CNPJ"), ("00.000.017/0001-49", "CNPJ"),
    ("123", None), ("", None), (None, None),
])
def test_o_tipo_do_documento_sai_do_tamanho(documento, esperado):
    assert PC.tipo_do_documento(documento) == esperado


def test_a_data_limite_subtrai_anos_sem_datetime():
    assert PC.data_limite("2026-08-25") == "2021-08-25"
    assert PC.data_limite("2026-08-25", 10) == "2016-08-25"


@pytest.mark.parametrize("ano,esperado", [
    (2020, "dois mil e vinte"), (2026, "dois mil e vinte e seis"),
    (2000, "dois mil"), (2015, "dois mil e quinze"),
])
def test_o_ano_por_extenso(ano, esperado):
    assert PC._por_extenso_ano(ano) == esperado


# ---------------------------------------------------- contra o acervo real


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_contra_o_acervo_real():
    """A certidao sobre os 1.366 titulos que a casa realmente protestou."""
    import acervo_carga as AC
    from ra_schema import init_ra_schema
    from rc_schema import init_rc_schema
    from rg_schema import init_rg_schema
    from ri_schema import init_ri_schema

    con = banco()
    # `rg_titulos` aponta para `cx_protocolos` (FK): o PostgreSQL cobra a FK
    # na criacao, e o banco da casa cria o caixa antes. Aqui basta o esqueleto.
    con.execute("CREATE TABLE IF NOT EXISTS cx_protocolos (id INTEGER PRIMARY KEY)")
    for iniciar in (init_rc_schema, init_rg_schema, init_ri_schema,
                    init_ra_schema):
        iniciar(con)
    AC.carregar_protesto(con, AC.abrir_acervo(ACERVO_REAL.parent), agora=AGORA)

    # Os atos que a carga passou a trazer em 25/08/2026, medidos.
    def q(sql: str) -> int:
        return int(con.execute(sql).fetchone()[0])

    # O acervo de produção continua crescendo. A régua é o piso já conferido,
    # não uma fotografia que fica vermelha toda vez que entram atos legítimos.
    assert q("SELECT COUNT(*) FROM pt_atos WHERE tipo='PROTESTO'") >= 1160
    assert q("SELECT COUNT(*) FROM pt_atos WHERE tipo='CANCELAMENTO'") >= 56

    # Quem tem protesto aparece; e o teor sai com o lugar dele.
    alvo = con.execute(
        """SELECT d.nome, d.documento_numero FROM pt_devedores d
             JOIN pt_atos a ON a.titulo_id=d.titulo_id AND a.tipo='PROTESTO'
            WHERE d.documento_numero IS NOT NULL LIMIT 1""").fetchone()
    desde = PC.data_limite(HOJE, 20)
    achados = PC.buscar(con, documento=alvo["documento_numero"], desde=desde,
                        autorizacao="DEVEDOR_ESCRITO")
    assert achados, "quem tem protesto no acervo tem de aparecer na busca"
    r = PC.emitir(con, nome=alvo["nome"], documento=alvo["documento_numero"],
                  achados=achados, hoje=HOJE, agora=AGORA, periodo_anos=20,
                  desde=desde, autorizacao="DEVEDOR_ESCRITO")
    assert r["tipo"] in ("POSITIVA", "CANCELAMENTO")
    assert "Livro" in r["teor"] and "fl." in r["teor"]

    # E quem nao tem sai negativa, sobre o mesmo acervo carregado.
    vazio = PC.buscar(con, nome="NOME QUE NÃO EXISTE NO ACERVO", desde=desde)
    assert vazio == []
    n = PC.emitir(con, nome="NOME QUE NÃO EXISTE NO ACERVO", documento="04785512388",
                  achados=vazio, hoje=HOJE, agora=AGORA)
    assert n["tipo"] == "NEGATIVA"


# --------------------------- o que a lei deixa certificar (14/10/2026)


def test_cancelado_NAO_entra_sem_pedido_escrito_ou_ordem_judicial():
    """Lei 9.492/1997, art. 27, § 2º; CN-MA (Prov. 28/2026) arts. 944 e 948."""
    con = banco()
    titulo(con, cancelamento="2024-06-01")
    assert PC.buscar(con, nome="SILVA") == []
    r = PC.emitir(con, nome="JOSÉ DA SILVA", documento="04785512388",
                  achados=PC.buscar(con, nome="SILVA"), hoje=HOJE, agora=AGORA)
    assert r["tipo"] == "NEGATIVA"


def test_achados_passados_por_fora_nao_furam_a_regra():
    con = banco()
    titulo(con, cancelamento="2024-06-01")
    com_cancelado = PC.buscar(con, nome="SILVA", autorizacao="DEVEDOR_ESCRITO")
    r = PC.emitir(con, nome="JOSÉ DA SILVA", documento="04785512388",
                  achados=com_cancelado, hoje=HOJE, agora=AGORA)
    assert r["tipo"] == "NEGATIVA"


def test_ordem_judicial_exige_o_juizo_e_o_processo():
    con = banco()
    titulo(con, cancelamento="2024-06-01")
    achados = PC.buscar(con, nome="SILVA", autorizacao="ORDEM_JUDICIAL")
    with pytest.raises(PC.CertidaoError, match="juízo e o processo"):
        PC.emitir(con, nome="JOSÉ DA SILVA", documento="04785512388",
                  achados=achados, hoje=HOJE, agora=AGORA,
                  autorizacao="ORDEM_JUDICIAL")
    r = PC.emitir(con, nome="JOSÉ DA SILVA", documento="04785512388",
                  achados=achados, hoje=HOJE, agora=AGORA,
                  autorizacao="ORDEM_JUDICIAL",
                  autorizacao_ref="1ª Vara, processo 0800123-45.2026")
    assert "por determinação judicial expressa (1ª Vara" in r["teor"]


def test_sem_cpf_ou_cnpj_a_certidao_nao_sai():
    """CN-MA art. 906: o CPF/CNPJ consta de toda certidão."""
    with pytest.raises(PC.CertidaoError, match="art. 906"):
        PC.emitir(banco(), nome="X", documento=None, achados=[], hoje=HOJE,
                  agora=AGORA)


def test_autorizacao_desconhecida_recusa():
    with pytest.raises(PC.CertidaoError, match="Autorização desconhecida"):
        PC.buscar(banco(), nome="X", autorizacao="QUALQUER")


# ------------------------------- a data do protocolo e o endosso (LD08)


def test_a_linha_traz_o_protocolo_com_a_data_do_apontamento_e_o_endosso():
    """CNN art. 259, parágrafo único, VII («data e número do protocolo») e V
    («tipo do endosso»). A data da protocolização é a do APONTAMENTO, o ato
    que a busca lê; o endosso é o código do título (M mandato)."""
    from bd_nativo import banco as nativo
    con = banco()
    tid = titulo(con)
    nativo(con).escrever(
        "UPDATE pt_titulos SET protocolo='2402200001', tipo_endosso='M',"
        " apresentante_nome='BANCO DE EXEMPLO' WHERE id=%s", (tid,))
    [achado] = PC.buscar(con, nome="SILVA")
    assert str(achado["data_protocolo"])[:10] == "2024-02-20"
    linha = PC._linha_do_protesto(achado, 1)
    assert "protocolo 2402200001 de 20/02/2024;" in linha
    assert "apresentante BANCO DE EXEMPLO; endosso mandato;" in linha


def test_sem_apontamento_a_data_nao_se_inventa_e_sem_endosso_nao_ha_tipo():
    """O título do acervo sem o ato de apontamento sai com o número do
    protocolo e sem data. «S» (sem endosso), o vazio e o código que o leiaute
    não tem não viram tipo de endosso no papel."""
    base = {"numero_titulo": "9", "valor": "10,00", "data_protesto": "2026-09-08",
            "protocolo": "2609080001", "apresentante": "BANCO DE EXEMPLO",
            "data_protocolo": None}
    for codigo in ("S", "", None, "X"):
        linha = PC._linha_do_protesto({**base, "tipo_endosso": codigo}, 1)
        assert "protocolo 2609080001;" in linha, linha
        assert "endosso" not in linha, (codigo, linha)
    assert "; endosso translativo;" in PC._linha_do_protesto(
        {**base, "tipo_endosso": "t"}, 1)
