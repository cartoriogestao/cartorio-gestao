"""Os pedidos da CRA no clique do dia — DP, CP e AC (29/10/2026).

O QUE MOTIVOU (medido na produção, só leitura): desde a virada de 14/10/2026
o registro das Centrais não tinha UMA chamada a `Desistencia`, `Cancelamento`
ou `Autorizacao`, e `pt_desistencias` estava vazia. Se algum credor desistiu
pela CRA, o sistema nunca soube — e um título desistido podia ser protestado.

O QUE ESTES TESTES CONFEREM
    - o XML que a API devolve (as duas formas dos exemplos da P21) se lê na
      MESMA forma do arquivo de 127 posições;
    - a resposta inteira se GUARDA antes de qualquer leitura, e «nada veio»
      também é registro;
    - a falha de uma consulta não derruba as outras, e a falha de rede (em
      que não se sabe se a CRA marcou o arquivo como baixado) vira pendência;
    - a desistência se aplica pelo caminho que já existe nos títulos que casam
      pelo protocolo E pelo número — os irmãos inclusive, que o `LIMIT 1`
      deixava de fora —, e a de título já PROTESTADO vem destacada;
    - cancelamento e autorização não lavram nada: viram pendência até o ato
      ou até alguém registrar por que não se lavra.

A REDE É SEMPRE SIMULADA: nenhuma chamada sai para a CRA. Os dados são
fictícios (LGPD): documentos da lista `tests/fixtures/anti_vazamento/
documentos_ficticios.txt`, e nomes de exemplo.
"""
from __future__ import annotations

from contextlib import contextmanager
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import centrais_http as HTTP  # noqa: E402
import cra21_api as CRA  # noqa: E402
import protesto as PT  # noqa: E402
import protesto_cra_pedidos as PCP  # noqa: E402
import protesto_desistencia as DS  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from pt_schema import init_pt_schema  # noqa: E402

AGORA = "2026-10-29T10:30:00"
DIA = "2026-10-29"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
CPF = "00000000191"           # 000.000.001-91, da lista dos fictícios
CNPJ = "00000001000055"       # 00.000.001/0000-55, idem


# --------------------------------------------- os arquivos sintéticos


def _tr(protocolo: str, numero: str, devedor: str, centavos: int,
        letra: str = "S", anexo: str = "", *, seq: int) -> str:
    return (f'<tr t01="2" t02="{protocolo}" t03="20102026" t04="{numero}" '
            f't05="{devedor}" t06="{centavos:014d}" t07="{letra}" '
            f't08="000000000000" t09="000000000000" t10="{anexo}" '
            f't11="000000" t12="{seq:05d}" />')


def xml_de_atributos(raiz: str, nome: str, titulos: list[tuple]) -> str:
    """A forma do `EXEMPLO_DP_CP_AD_AC.zip` da P21: hdb/hdc/tr/tlc/tlb."""
    linhas = [_tr(*t, seq=i + 3) for i, t in enumerate(titulos)]
    soma = sum(t[3] for t in titulos)
    return (
        '<?xml version="1.0" encoding="ISO-8859-1" standalone="no"?>\r\n'
        f'<{raiz}>\r\n<nome_arquivo>{nome}</nome_arquivo>\r\n'
        '<hdb h01="0" h02="001" h03="BANCO DE EXEMPLO SA" h04="29102026" '
        f'h05="{len(titulos):05d}" h06="{len(titulos):05d}" h07="" h08="00001" />\r\n'
        f'<hdc h01="1" h02="01" h03="{len(titulos):05d}" h04="2198765" h05="" h06="00002" />\r\n'
        + "\r\n".join(linhas) +
        f'\r\n<tlc t01="8" t02="01" t03="{2 * len(titulos):05d}" t04="" t05="00001" />\r\n'
        '<tlb t01="9" t02="001" t03="BANCO DE EXEMPLO SA" t04="29102026" '
        f't05="{2 * len(titulos):05d}" t06="{soma:014d}" t07="" t08="00009" />\r\n'
        f'</{raiz}>\r\n')


def relatorio(codigo: str, frase: str) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?><relatorio>'
            '<nome_arquivo>X</nome_arquivo><datahora>29/10/2026 10:30</datahora>'
            f'<codigo>{codigo}</codigo><ocorrencia>{frase}</ocorrencia></relatorio>')


NADA_DP = relatorio("0006", "NÃO EXISTE DESISTÊNCIA NA DATA INFORMADA.")
NADA_CP = relatorio("0007", "NÃO EXISTE CANCELAMENTO NA DATA INFORMADA.")


def falha_de_rede() -> CRA.CraError:
    """A falha como `cra21_api._bater` a levanta numa operação que escreve."""
    try:
        try:
            raise HTTP.CentralHttpError("a ligação caiu")
        except HTTP.CentralHttpError as causa:
            raise CRA.CraError("Falha de comunicação com a CRA. Não é "
                               "possível saber se a Central marcou o arquivo "
                               "como baixado.") from causa
    except CRA.CraError as erro:
        return erro


# ----------------------------------------------------------- o banco


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    init_pt_schema(c)
    c.commit()
    yield c
    c.close()


def transacao_de(c):
    @contextmanager
    def _t():
        try:
            yield c
        except BaseException:
            c.rollback()
            raise
        c.commit()
    return _t


def titulo(c, *, protocolo: str, numero: str, situacao: str | None = None,
           devedor: str = "EMPRESA DE EXEMPLO LTDA") -> int:
    tid = PT.cadastrar_titulo(c, {
        "apresentante_codigo": "001", "apresentante_nome": "BANCO DE EXEMPLO SA",
        "especie": "DMI", "numero_titulo": numero, "nosso_numero": f"N{numero}",
        "data_emissao": "2026-09-01", "data_vencimento": "2026-10-01",
        "valor": "221.00", "saldo": "221.00", "praca_protesto": "CIDADE EXEMPLO",
        "cedente": {"nome": "LOJA DE EXEMPLO", "documento": CNPJ},
        "devedores": [{"nome": devedor, "CPF": CPF,
                       "enderecos": [{"endereco": "RUA DE EXEMPLO, 10",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }, origem="CRA", origem_chave=f"lote:{protocolo}:{numero}:{devedor}",
        agora=AGORA)
    PT.lancar_apontamento(c, tid, sv=SV, agora=AGORA, data_extenso="x")
    c.execute("UPDATE pt_titulos SET protocolo=? WHERE id=?", (protocolo, tid))
    if situacao:
        c.execute("UPDATE pt_titulos SET situacao=? WHERE id=?",
                  (situacao, tid))
    c.commit()
    return tid


def porta(respostas: dict):
    """A CRA simulada: `o_que` -> texto devolvido ou exceção levantada."""
    chamadas: list[tuple] = []

    def trazer(o_que, nome, com_imagem):
        chamadas.append((o_que, nome, com_imagem))
        r = respostas[o_que]
        if isinstance(r, BaseException):
            raise r
        return r
    return trazer, chamadas


def trazer(c, respostas, **k):
    t, chamadas = porta(respostas)
    linhas = PCP.trazer_do_dia(transacao_de(c), t, dia=DIA, agora=AGORA,
                               usuario="carla", **k)
    return {l["tipo"]: l for l in linhas}, chamadas


def consultas(c) -> list[dict]:
    return [dict(r) for r in c.execute(
        "SELECT * FROM pt_cra_consultas ORDER BY id").fetchall()]


def pedidos(c) -> list[dict]:
    return [dict(r) for r in c.execute(
        "SELECT * FROM pt_cra_pedidos ORDER BY id").fetchall()]


# ------------------------------------------------- o XML da API


def test_o_xml_de_atributos_se_le_na_forma_do_arquivo_de_127():
    xml = xml_de_atributos("sustacao", "DP0012910.261", [
        ("2610200001", "NF-1001/1", "EMPRESA DE EXEMPLO LTDA", 22100),
        ("2610200002", "1  00053603", "FULANO DE TAL EXEMPLO", 15000)])
    a = DS.ler(xml)
    assert a["cabecalho"]["apresentante_codigo"] == "001"
    assert a["cabecalho"]["dia"] == "2026-10-29"
    assert [t["protocolo"] for t in a["titulos"]] == ["2610200001",
                                                      "2610200002"]
    assert a["titulos"][1]["numero_do_titulo"] == "1  00053603"
    assert a["titulos"][0]["valor_centavos"] == 22100
    assert a["titulos"][0]["cidade_ibge"] == "2198765"
    # A SOMA FECHA, como no arquivo de 127 — e a contagem do «dobro», que só
    # se mediu no de 127, não vira achado no XML.
    assert a["achados"] == []
    assert a["nome_arquivo"] == "DP0012910.261"


def test_o_xml_de_elementos_traz_o_valor_em_reais():
    xml = ('<?xml version="1.0" encoding="ISO-8859-1"?>\n<desistencia>'
           '<comarca><CodMun>2198765</CodMun><cartorio>'
           '<numero_cartorio>01</numero_cartorio><titulo>'
           '<numero_protocolo>2610200003</numero_protocolo>'
           '<data_protocolo>20102026</data_protocolo>'
           '<numero_titulo>DUP-55</numero_titulo>'
           '<nome_devedor>JOSÉ EXEMPLO</nome_devedor>'
           '<valor_titulo>268.82</valor_titulo><imagem>UEsDBA==</imagem>'
           '</titulo></cartorio></comarca></desistencia>')
    a = DS.ler(xml.encode("latin-1"))
    t = a["titulos"][0]
    assert t["protocolo"] == "2610200003"
    assert t["devedor_nome"] == "JOSÉ EXEMPLO"
    assert t["valor_centavos"] == 26882
    assert t["tem_anexo"] is True
    assert t["cidade_ibge"] == "2198765"


@pytest.mark.parametrize("ruim,frase", [
    ('<!DOCTYPE x [<!ENTITY a "b">]><sustacao/>', "DTD"),
    ("<remessa></remessa>", "<remessa>"),
    (NADA_DP, "0006"),
])
def test_o_que_nao_e_pedido_da_cra_se_recusa_dizendo_o_que_veio(ruim, frase):
    with pytest.raises(DS.DesistenciaError) as erro:
        DS.ler(ruim)
    assert frase in str(erro.value)


def test_o_arquivo_de_127_continua_lendo_igual():
    exemplo = (Path(__file__).parent / "cra_desistencia_exemplo.txt").read_bytes()
    a = DS.ler(exemplo)
    assert a["titulos"][0]["numero_do_titulo"] == "NF-74654-/1"
    assert a["achados"] == []


# ------------------------------------------ o nome e a classificação


def test_o_nome_pedido_e_o_de_todos_os_apresentantes_com_a_data():
    # O precedente desta casa: B000ddmm.26s nas remessas do E-Ofício.
    assert PCP.nome_do_pedido("DP", DIA) == "DP0002910.261"
    assert PCP.nome_do_pedido("CP", "2026-01-05") == "CP0000501.261"
    assert PCP.nome_do_pedido("AC", DIA) == "AC0002910.261"


@pytest.mark.parametrize("tipo,texto,esperado", [
    ("DP", NADA_DP, PCP.NADA),
    ("CP", NADA_CP, PCP.NADA),
    # O «nada» da autorização não está no manual: não se chama de nada.
    ("AC", relatorio("0006", "NADA"), PCP.AVISO),
    ("DP", relatorio("0002", "NOME INVÁLIDO"), PCP.FALHA),
    ("DP", "<erro><mensagem>Falha de autenticação</mensagem>"
           "<codigo>1</codigo></erro>", PCP.FALHA),
    ("DP", "   ", PCP.AVISO),
    ("DP", "<sustacao></sustacao>", None),
])
def test_a_resposta_se_classifica_pela_raiz(tipo, texto, esperado):
    assert PCP.classificar(tipo, texto)[0] == esperado


# --------------------------------------------- guardar antes de ler


def test_a_resposta_inteira_fica_guardada_mesmo_quando_nao_se_le(con):
    lixo = "<sustacao><isto nao fecha"
    linhas, _ = trazer(con, {"desistencias": lixo, "cancelamentos": NADA_CP,
                             "autorizacoes": relatorio("0006", "NADA")})
    assert linhas["DP"]["resultado"] == PCP.NAO_LIDO
    dp = consultas(con)[0]
    assert dp["bruto"] == lixo and dp["hash_bruto"] and dp["tamanho"] == len(lixo)
    assert dp["resultado"] == PCP.NAO_LIDO
    # E o arquivo que veio e não se leu É PENDÊNCIA: ele pode não existir mais
    # do lado da CRA.
    assert any(p["consulta_id"] == dp["id"] and p["pedido_id"] is None
               for p in DS.pendencias_da_cra(con))


def test_nada_veio_tambem_e_registro(con):
    linhas, chamadas = trazer(con, {
        "desistencias": NADA_DP, "cancelamentos": NADA_CP,
        "autorizacoes": relatorio("0006", "NADA")})
    assert [c[0] for c in chamadas] == ["desistencias", "cancelamentos",
                                        "autorizacoes"]
    assert [c[1] for c in chamadas] == ["DP0002910.261", "CP0002910.261",
                                        "AC0002910.261"]
    # A desistência não pede imagem; cancelamento e autorização pedem (a
    # carta de anuência vem no anexo).
    assert [c[2] for c in chamadas] == [False, True, True]
    assert linhas["DP"]["resultado"] == PCP.NADA
    assert linhas["CP"]["resultado"] == PCP.NADA
    assert linhas["AC"]["resultado"] == PCP.AVISO
    assert [q["resultado"] for q in consultas(con)] == [PCP.NADA, PCP.NADA,
                                                        PCP.AVISO]
    assert DS.pendencias_da_cra(con) == []


def test_a_falha_de_uma_nao_derruba_as_outras(con):
    titulo(con, protocolo="2610200005", numero="DUP-9", situacao="PROTESTADO")
    cp = xml_de_atributos("sustacao", "CP0012910.261", [
        ("2610200005", "DUP-9", "EMPRESA DE EXEMPLO LTDA", 9000)])
    linhas, _ = trazer(con, {"desistencias": falha_de_rede(),
                             "cancelamentos": cp,
                             "autorizacoes": CRA.CraRecusou("SOAP fault")})
    assert linhas["DP"]["resultado"] == PCP.FALHA
    assert linhas["DP"]["incerta"] is True
    assert linhas["DP"]["cor"] == "danger"
    assert linhas["CP"]["resultado"] == PCP.RECEBIDO
    assert linhas["AC"]["resultado"] == PCP.FALHA
    # A resposta fora do combinado também é incerta: a Central pode ter feito
    # o trabalho e devolvido outra coisa.
    assert linhas["AC"]["incerta"] is True
    abertas = DS.pendencias_da_cra(con)
    textos = " ".join(p["explicacao"] for p in abertas)
    assert "confira no portal da CRA" in textos           # a falha incerta
    assert any(p["tipo"] == "CP" and p["titulo_id"] for p in abertas)
    assert sum(1 for p in abertas if p["pedido_id"] is None) == 2  # DP e AC


def test_sem_credencial_e_falha_certa_e_nao_vira_pendencia(con):
    import centrais_cred as CRED
    erro = CRED.CredencialError("A credencial da CRA ainda não foi informada.")
    trazer(con, {"desistencias": erro, "cancelamentos": erro,
                 "autorizacoes": erro})
    assert [q["incerta"] for q in consultas(con)] == [0, 0, 0]
    assert DS.pendencias_da_cra(con) == []


def test_se_o_banco_recusa_o_bruto_vai_para_o_disco(con, tmp_path):
    @contextmanager
    def recusa():
        raise sqlite3.OperationalError("database is locked")
        yield con  # pragma: no cover

    t, _ = porta({"desistencias": "<sustacao/>", "cancelamentos": NADA_CP,
                  "autorizacoes": NADA_CP})
    linhas = {l["tipo"]: l for l in PCP.trazer_do_dia(
        recusa, t, dia=DIA, agora=AGORA, pasta_reserva=tmp_path)}
    assert linhas["DP"]["resultado"] == PCP.NAO_LIDO
    guardado = Path(linhas["DP"]["onde"])
    assert guardado.is_file() and guardado.read_text(encoding="utf-8") == "<sustacao/>"
    assert tmp_path in guardado.parents


# ---------------------------------------------------- a desistência


def test_dp_aplica_pelo_caminho_que_existe_e_o_protestado_vem_grave(con):
    apontado = titulo(con, protocolo="2610200001", numero="NF-1001/1")
    protestado = titulo(con, protocolo="2610200002", numero="NF-1002/1",
                        situacao="PROTESTADO")
    dp = xml_de_atributos("sustacao", "DP0012910.261", [
        ("2610200001", "NF-1001/1", "EMPRESA DE EXEMPLO LTDA", 22100),
        ("2610200002", "NF-1002/1", "EMPRESA DE EXEMPLO LTDA", 22100)])
    linhas, _ = trazer(con, {"desistencias": dp, "cancelamentos": NADA_CP,
                             "autorizacoes": NADA_CP})
    r = linhas["DP"]
    assert r["resultado"] == PCP.RECEBIDO
    assert (r["aplicados"], r["pendentes"], r["graves"]) == (1, 1, 1)
    assert r["cor"] == "danger"
    situ = {row[0]: row[1] for row in con.execute(
        "SELECT id, situacao FROM pt_titulos").fetchall()}
    assert situ[apontado] == "DESISTIDO"
    assert situ[protestado] == "PROTESTADO"           # nada se desfaz sozinho
    ato = con.execute("SELECT * FROM pt_atos WHERE tipo='DESISTENCIA'").fetchone()
    assert ato["origem"] == "CRA" and ato["desistencia_id"] == r["desistencia_id"]
    # O ARQUIVO ENTROU EM `pt_desistencias`, que o roteiro já lê.
    assert con.execute("SELECT COUNT(*) FROM pt_desistencias").fetchone()[0] == 1
    abertas = DS.pendencias_da_cra(con)
    assert abertas[0]["destaque"] == PCP.GRAVE           # o grave vem primeiro
    assert abertas[0]["titulo_id"] == protestado
    assert "PROTESTADO" in abertas[0]["explicacao"]
    # O contrato do roteiro: as quatro chaves que ele lê.
    for chave in ("titulo_id", "numero_titulo", "protocolo", "explicacao"):
        assert chave in abertas[0]


def test_dp_de_titulo_intimado_se_aplica_e_vem_destacado(con):
    tid = titulo(con, protocolo="2610200001", numero="NF-1001/1",
                 situacao="INTIMADO")
    dp = xml_de_atributos("sustacao", "DP0012910.261", [
        ("2610200001", "NF-1001/1", "EMPRESA DE EXEMPLO LTDA", 22100)])
    trazer(con, {"desistencias": dp, "cancelamentos": NADA_CP,
                 "autorizacoes": NADA_CP})
    p = pedidos(con)[0]
    assert p["estado"] == PCP.APLICADO and p["destaque"] == PCP.POR_POUCO
    assert p["titulo_id"] == tid and p["ato_id"]
    assert DS.pendencias_da_cra(con) == []


def test_os_irmaos_desistem_juntos_e_o_limit_1_acabou(con):
    """Os 34 protocolos da produção com dois títulos de mesmo número — a CDA
    com o corresponsável. A desistência pegava só o primeiro."""
    um = titulo(con, protocolo="2610200007", numero="CDA-77",
                devedor="EMPRESA DE EXEMPLO LTDA")
    dois = titulo(con, protocolo="2610200007", numero="CDA-77",
                  devedor="FULANO DE TAL EXEMPLO")
    dp = xml_de_atributos("sustacao", "DP0012910.261", [
        ("2610200007", "CDA-77", "EMPRESA DE EXEMPLO LTDA", 15000),
        ("2610200007", "CDA-77", "FULANO DE TAL EXEMPLO", 15000)])
    visto = DS.conferir(con, dp)
    assert [x["id"] for x in visto["titulos"][0]["titulos"]] == [um, dois]
    linhas, _ = trazer(con, {"desistencias": dp, "cancelamentos": NADA_CP,
                             "autorizacoes": NADA_CP})
    assert linhas["DP"]["aplicados"] == 2
    assert {r[0] for r in con.execute(
        "SELECT situacao FROM pt_titulos WHERE protocolo='2610200007'"
    ).fetchall()} == {"DESISTIDO"}
    # UMA desistência por título — as duas linhas do arquivo não desistem duas
    # vezes do mesmo.
    assert con.execute("SELECT COUNT(*) FROM pt_atos WHERE tipo='DESISTENCIA'"
                       ).fetchone()[0] == 2


def test_o_aplicar_da_tela_tambem_alcanca_os_irmaos(con):
    titulo(con, protocolo="2610200007", numero="CDA-77")
    titulo(con, protocolo="2610200007", numero="CDA-77",
           devedor="FULANO DE TAL EXEMPLO")
    dp = xml_de_atributos("sustacao", "DP0012910.261", [
        ("2610200007", "CDA-77", "EMPRESA DE EXEMPLO LTDA", 15000)])
    r = DS.aplicar(con, dp, protocolos=["2610200007"], agora=AGORA)
    assert len(r["aplicados"]) == 2 and not r["recusados"]


def test_numero_que_diverge_nao_se_aplica_por_palpite(con):
    tid = titulo(con, protocolo="2610200008", numero="PARC/1")
    dp = xml_de_atributos("sustacao", "DP0012910.261", [
        ("2610200008", "PARC/2", "EMPRESA DE EXEMPLO LTDA", 23000)])
    visto = DS.conferir(con, dp)
    linha = visto["titulos"][0]
    assert linha["cabe"] is False and linha["titulo"] is None
    assert "a CRA fala do título PARC/2" in linha["porque"]
    trazer(con, {"desistencias": dp, "cancelamentos": NADA_CP,
                 "autorizacoes": NADA_CP})
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "APONTADO"
    assert [p["titulo_id"] for p in DS.pendencias_da_cra(con)] == [None]


def test_o_numero_se_compara_sem_espacos_e_sem_zeros_a_esquerda(con):
    titulo(con, protocolo="2610200009", numero="100053603")
    dp = xml_de_atributos("sustacao", "DP0012910.261", [
        ("2610200009", "1  00053603", "EMPRESA DE EXEMPLO LTDA", 23000)])
    assert DS.conferir(con, dp)["titulos"][0]["cabe"] is True


def test_o_sustado_volta_recusado_e_nao_derruba_o_arquivo(con):
    sustado = titulo(con, protocolo="2610200010", numero="S-1",
                     situacao="INTIMADO")
    livre = titulo(con, protocolo="2610200011", numero="S-2")
    PT.lancar_sustacao(con, sustado, juizo="1ª Vara de Cidade Exemplo",
                       processo="0000001-00.2026.8.10.0001", agora=AGORA)
    con.commit()
    dp = xml_de_atributos("sustacao", "DP0012910.261", [
        ("2610200010", "S-1", "EMPRESA DE EXEMPLO LTDA", 1000),
        ("2610200011", "S-2", "EMPRESA DE EXEMPLO LTDA", 1000)])
    linhas, _ = trazer(con, {"desistencias": dp, "cancelamentos": NADA_CP,
                             "autorizacoes": NADA_CP})
    assert linhas["DP"]["resultado"] == PCP.RECEBIDO
    assert linhas["DP"]["aplicados"] == 1
    situ = {r[0]: r[1] for r in con.execute(
        "SELECT id, situacao FROM pt_titulos").fetchall()}
    assert situ[livre] == "DESISTIDO" and situ[sustado] != "DESISTIDO"
    pendente = [p for p in DS.pendencias_da_cra(con) if p["titulo_id"] == sustado]
    assert pendente and "SUSTADO" in pendente[0]["explicacao"]


def test_o_mesmo_arquivo_de_novo_nao_duplica(con):
    titulo(con, protocolo="2610200002", numero="NF-1002/1", situacao="PROTESTADO")
    dp = xml_de_atributos("sustacao", "DP0012910.261", [
        ("2610200002", "NF-1002/1", "EMPRESA DE EXEMPLO LTDA", 22100)])
    respostas = {"desistencias": dp, "cancelamentos": NADA_CP,
                 "autorizacoes": NADA_CP}
    trazer(con, respostas)
    trazer(con, respostas)
    assert len(consultas(con)) == 6                    # as duas consultas ficam
    assert len(pedidos(con)) == 1                      # o pedido, uma vez
    assert con.execute("SELECT COUNT(*) FROM pt_desistencias").fetchone()[0] == 1


# --------------------------------------------- cancelamento e autorização


def test_cp_e_ac_viram_pendencia_e_nao_lavram_nada(con):
    p1 = titulo(con, protocolo="2610200020", numero="C-1", situacao="PROTESTADO")
    p2 = titulo(con, protocolo="2610200021", numero="C-2", situacao="PROTESTADO")
    p3 = titulo(con, protocolo="2610200022", numero="C-3", situacao="INTIMADO")
    cp = xml_de_atributos("sustacao", "CP0012910.261", [
        ("2610200020", "C-1", "EMPRESA DE EXEMPLO LTDA", 5000)])
    ac = xml_de_atributos("autorizacao", "AC0012910.261", [
        ("2610200021", "C-2", "EMPRESA DE EXEMPLO LTDA", 5000, "C", "UEsDBA=="),
        ("2610200022", "C-3", "EMPRESA DE EXEMPLO LTDA", 5000, "S")])
    antes = con.execute("SELECT COUNT(*) FROM pt_atos").fetchone()[0]
    linhas, _ = trazer(con, {"desistencias": NADA_DP, "cancelamentos": cp,
                             "autorizacoes": ac})
    assert con.execute("SELECT COUNT(*) FROM pt_atos").fetchone()[0] == antes
    assert linhas["CP"]["pendentes"] == 1 and linhas["AC"]["pendentes"] == 2
    tipos = {p["titulo_id"]: p["tipo"] for p in DS.pendencias_da_cra(con)}
    # A letra t07 da autorização diz o tipo: C cancelamento, S desistência.
    assert tipos == {p1: "CP", p2: "AC", p3: "AD"}
    ac_c = [p for p in pedidos(con) if p["titulo_id"] == p2][0]
    assert ac_c["tem_anexo"] == 1                      # a carta de anuência


def test_a_pendencia_fecha_pelo_ato(con):
    tid = titulo(con, protocolo="2610200020", numero="C-1", situacao="PROTESTADO")
    cp = xml_de_atributos("sustacao", "CP0012910.261", [
        ("2610200020", "C-1", "EMPRESA DE EXEMPLO LTDA", 5000)])
    trazer(con, {"desistencias": NADA_DP, "cancelamentos": cp,
                 "autorizacoes": NADA_CP})
    assert [p["titulo_id"] for p in DS.pendencias_da_cra(con)] == [tid]
    con.execute("UPDATE pt_titulos SET situacao='CANCELADO' WHERE id=?", (tid,))
    con.commit()
    assert DS.pendencias_da_cra(con) == []


def test_tratar_exige_motivo_e_o_grave_so_o_oficial_encerra(con):
    tid = titulo(con, protocolo="2610200002", numero="NF-1002/1",
                 situacao="PROTESTADO")
    dp = xml_de_atributos("sustacao", "DP0012910.261", [
        ("2610200002", "NF-1002/1", "EMPRESA DE EXEMPLO LTDA", 22100)])
    trazer(con, {"desistencias": dp, "cancelamentos": NADA_CP,
                 "autorizacoes": NADA_CP})
    pid = DS.pendencias_da_cra(con)[0]["pedido_id"]
    with pytest.raises(PCP.PedidoCraError, match="motivo"):
        PCP.tratar_pedido(con, pid, motivo="ok", agora=AGORA,
                          usuario="carla", papel="USER")
    with pytest.raises(PCP.PedidoCraError, match="oficial"):
        PCP.tratar_pedido(con, pid, motivo="O protesto foi lavrado antes da "
                          "desistência chegar", agora=AGORA, usuario="carla",
                          papel="USER")
    r = PCP.tratar_pedido(con, pid, motivo="O protesto foi lavrado antes da "
                          "desistência chegar", agora=AGORA, usuario="mario",
                          papel="ADMIN")
    con.commit()
    assert r["estado"] == PCP.TRATADO and r["titulo_id"] == tid
    assert DS.pendencias_da_cra(con) == []
    with pytest.raises(PCP.PedidoCraError, match="já está"):
        PCP.tratar_pedido(con, pid, motivo="de novo, por engano da tela",
                          agora=AGORA, usuario="mario", papel="ADMIN")


def test_a_falha_incerta_sai_da_lista_quando_alguem_confere_no_portal(con):
    trazer(con, {"desistencias": falha_de_rede(), "cancelamentos": NADA_CP,
                 "autorizacoes": NADA_CP})
    cid = DS.pendencias_da_cra(con)[0]["consulta_id"]
    PCP.tratar_consulta(con, cid, motivo="Conferido no portal da CRA: nada "
                        "marcado como baixado", agora=AGORA, usuario="carla")
    con.commit()
    assert DS.pendencias_da_cra(con) == []


# --------------------------------------------- a contagem desde 14/10


def test_a_contagem_le_o_registro_das_centrais(con):
    sem = PCP.contagem_desde_a_virada(con)
    if sem["DP"] is None:                              # sem a tabela, sem medida
        from centrais_schema import init_centrais_schema
        init_centrais_schema(con)
    for quando, operacao in (("2026-10-13T10:00:00", "Desistencia"),
                             ("2026-10-20T10:00:00", "Desistencia"),
                             ("2026-10-21T10:00:00", "Autorizacao"),
                             ("2026-10-21T10:00:00", "RemessaPendente")):
        con.execute("INSERT INTO centrais_log(quando, central, operacao, nivel,"
                    " evento) VALUES (?,?,?,?,?)",
                    (quando, "CRA", operacao, "INFO", "REQUISICAO"))
    con.commit()
    c = PCP.contagem_desde_a_virada(con)
    assert (c["DP"], c["CP"], c["AC"]) == (1, 0, 1)   # o de 13/10 não conta
    assert c["desde_br"] == "14/10/2026"
