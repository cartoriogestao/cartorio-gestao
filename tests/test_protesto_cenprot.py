"""
A CHAVE DO CENPROT — que a Central devolve, e que a casa nunca guardou.

Este projeto tentou explicar a chave de 23 digitos duas vezes e a chamou de
«verificador que nao se explica». **Ela nao tem verificador: tem data** — e o
que resolveu nao foi engenhosidade, foi o oficial gerar um arquivo pelo
E-Oficio. Terceira vez que a lacuna de layout se fecha com mais amostra.

O QUE ESTES TESTES GUARDAM
      - a chave se DECOMPOE em quatro partes, e a data dela bate com o
        `<data_protocolo>` do proprio XML — nos 175 titulos reais;
      - o casamento e por DUAS PARTES: protocolo mais nosso numero (ou, sem
        ele, o valor). Prender so pelo protocolo escreveria no titulo de uma
        pessoa a chave do titulo de outra — e essa chave viaja para a Central;
      - a recusa DIZ QUAL PARTE FALHOU, porque o conserto de cada uma e
        diferente;
      - chave que ja esta la NAO SE SOBRESCREVE — vai para `divergem` e espera
        o oficial;
      - o que nao casa NAO DERRUBA o arquivo;
      - `quantos_sem_chave` devolve TRES numeros, e nao um: sem protocolo nao
        ha por onde casar, e isso e outro problema.

E O ENSAIO CONTRA O ARQUIVO REAL, que e o que prova o leitor — o mesmo lugar
onde o primeiro ensaio me pegou inventando a coluna `atualizado_em`.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — referencia acervo_eoficio ou sqlite de producao
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import protesto_cenprot as CP
from pt_schema import init_pt_schema

AGORA = "2026-09-01T10:00:00"

# Uma chave real desta casa, do arquivo de 31/08/2026.
CHAVE = "21987650141243301260417"
PROTOCOLO = "2604170001"
NOSSO = "YK0000000000072"



def _arquivo_real(padrao: str) -> Path:
    """O arquivo real do oficial, achado pela FORMA do nome em Downloads — o
    código IBGE da casa, que está no nome, não se escreve aqui (B3)."""
    achados = sorted((Path.home() / "Downloads").glob(padrao))
    return achados[0] if achados else Path.home() / "Downloads" / ("_inexistente_" + padrao)

ARQUIVO_REAL = _arquivo_real("MA-???????-01-P-20260831-01.xml")


# A IDENTIDADE DESTA CASA — `ibge_uf` + `ibge_municipio` dao a comarca
# (`21` + `07001`) e `ibge_cartorio` da o cartorio. Sao as MESMAS quatro
# configuracoes que a remessa do IBGE ja usa, e as duas fontes se conferem.
CASA = {"comarca": "2198765", "cartorio": "01"}


def conferir(con, conteudo):
    return CP.conferir(con, conteudo, **CASA)


def guardar(con, conteudo):
    return CP.guardar(con, conteudo, **CASA)


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_pt_schema(con)
    return con


def titulo(con, *, protocolo=PROTOCOLO, nosso=NOSSO, valor=200785,
           chave=None, numero="EDILENA0003") -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
               valor_centavos, saldo_centavos, situacao, protocolo,
               chave_cenprot, origem, criado_em)
           VALUES ('DMI',?,?,?,?,'APONTADO',?,?,'CRA',?)""",
        (numero, nosso, valor, valor, protocolo, chave, AGORA))
    return int(cur.lastrowid)


def xml(*titulos: str, versao: str = CP.VERSAO_MEDIDA) -> str:
    """Monta um XML com a MESMA forma do real — aninhamento inteiro."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<estados total="1" versao="{}"><estado uf="MA">'
        '<cartorios total="1"><cartorio codigo="01" comarca="2198765">'
        '<apresentantes total="1"><apresentante codigo="033">'
        '<nome>BANCO SANTANDER</nome><titulos total="{}">{}</titulos>'
        '</apresentante></apresentantes></cartorio></cartorios>'
        '</estado></estados>'.format(versao, len(titulos), "".join(titulos)))


def um(*, chave=CHAVE, protocolo=PROTOCOLO, nosso=NOSSO, valor="2007.8500",
       data="2026-04-17") -> str:
    return (
        f'<titulo id="{chave}"><nosso_numero>{nosso}</nosso_numero>'
        f'<numero_titulo>EDILENA0003</numero_titulo><valor>{valor}</valor>'
        f'<protocolo>{protocolo}</protocolo><data_protocolo>{data}</data_protocolo>'
        '</titulo>')


# ------------------------------------------------------------------ a chave


def test_a_chave_se_decompoe_em_quatro_partes():
    d = CP.decompor_chave(CHAVE)
    assert d["ibge"] == "2198765"
    assert d["sequencial_cenprot"] == "01412433"
    assert d["cartorio"] == "01"
    assert d["data_protocolo"] == "260417"


def test_o_bloco_do_meio_nao_se_abre_mais_que_isso():
    """EU O ABRI ERRADO NA PRIMEIRA VEZ, e a outra casa ja estava medida.

    Escrevi que as posicoes 8 e 9 sao o cartorio, porque nesta casa sao `01`
    em 175 de 175. O `CENPROT_XML_MEDIDO.md` deste projeto registra
    `2801405|0005640|2|01|200330`, de outra serventia, com **`00`** ali.

    Regularidade forte dentro de uma casa parece lei ate alguem olhar outra
    casa — a licao da posicao 566, pela segunda vez. O bloco fica inteiro.
    """
    de_sergipe = CP.decompor_chave("2801405" + "00056402" + "01" + "200330")
    assert de_sergipe["ibge"] == "2801405"
    assert de_sergipe["cartorio"] == "01", "o cartorio esta nas 16-17, e la bate"
    assert de_sergipe["sequencial_cenprot"].startswith("00"), (
        "e nas 8-9 vem `00`, que e o que desmente a minha primeira leitura")


def test_chave_de_tamanho_errado_nao_se_decompoe():
    """Nao estoura: quem chama esta lendo arquivo de fora."""
    assert CP.decompor_chave("2198765") is None
    assert CP.decompor_chave("") is None
    assert CP.decompor_chave(None) is None
    assert CP.decompor_chave(CHAVE + "9") is None


def test_a_data_sai_da_chave():
    assert CP.data_do_protocolo(CHAVE) == "2026-04-17"


def test_data_impossivel_devolve_none_em_vez_de_data_torta():
    """Melhor nao responder que responder errado — carimbo que mente."""
    assert CP.data_do_protocolo("21987650141243301269917") is None


# ------------------------------------------------------------------ ler


def test_le_o_arquivo_com_bom_na_frente():
    """O arquivo real vem com `\\ufeff`, e o ElementTree estoura com ele."""
    lido = CP.ler(("\ufeff" + xml(um())).encode("utf-8"))
    assert lido["titulos"][0]["chave"] == CHAVE


def test_le_o_cabecalho_e_o_apresentante_de_cada_titulo():
    lido = CP.ler(xml(um()))
    assert lido["comarca"] == "2198765"
    assert lido["cartorio"] == "01"
    assert lido["titulos"][0]["apresentante_codigo"] == "033"
    assert lido["titulos"][0]["apresentante_nome"] == "BANCO SANTANDER"


def test_arquivo_que_nao_e_xml_recusa_dizendo_qual_e_o_certo():
    with pytest.raises(CP.CenprotError) as e:
        CP.ler(b"nao sou xml nenhum")
    assert "letra «P»" in str(e.value)


# --------------------------------------------------- o arquivo e desta casa?


def test_arquivo_de_outra_serventia_e_recusado():
    """O GUARDA QUE NASCEU AO CONSTRUIR A TELA.

    E o unico jeito de o casamento por duas partes errar: nem o protocolo nem
    o nosso numero sao nacionais, e dois arquivos de casas diferentes podem
    trazer os mesmos. Sem isto, carregar o arquivo da serventia vizinha
    escreveria chaves ALHEIAS nos titulos daqui — e elas viajam para a Central.
    """
    con = banco()
    titulo(con)
    de_fora = xml(um()).replace('comarca="2198765"', 'comarca="2801405"')
    with pytest.raises(CP.CenprotError) as e:
        conferir(con, de_fora)
    texto = str(e.value)
    assert "NAO e desta serventia" in texto
    assert "2801405" in texto and "2198765" in texto


def test_cartorio_diferente_na_mesma_comarca_tambem_e_recusado():
    """Duas serventias da mesma comarca sao duas casas."""
    con = banco()
    titulo(con)
    do_vizinho = xml(um()).replace('codigo="01" comarca', 'codigo="02" comarca')
    with pytest.raises(CP.CenprotError):
        conferir(con, do_vizinho)


def test_sem_saber_quem_e_a_casa_nao_se_confere_nada():
    """Guarda que se pode esquecer de pedir e guarda que um dia nao e pedido.

    Sem as configuracoes do IBGE o sistema NAO tem como saber se o arquivo e
    desta casa — e a resposta certa e parar e dizer onde informa-las, nao
    seguir em frente sem conferir.
    """
    con = banco()
    titulo(con)
    with pytest.raises(CP.CenprotError) as e:
        CP.conferir(con, xml(um()), comarca="", cartorio="01")
    assert "configuracoes do IBGE" in str(e.value)


def test_guardar_tambem_recusa_arquivo_de_outra_casa():
    """A guarda esta no caminho que ESCREVE, e nao so no que mostra."""
    con = banco()
    tid = titulo(con)
    de_fora = xml(um()).replace('comarca="2198765"', 'comarca="2801405"')
    with pytest.raises(CP.CenprotError):
        guardar(con, de_fora)
    assert con.execute("SELECT chave_cenprot FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] is None


# ------------------------------------------------------------------ conferir


def test_casa_pelo_protocolo_e_confere_pelo_nosso_numero():
    con = banco()
    tid = titulo(con)
    c = conferir(con, xml(um()))
    assert len(c["entram"]) == 1
    assert c["entram"][0]["titulo_id"] == tid
    assert c["entram"][0]["chave"] == CHAVE
    assert c["versao_conhecida"] is True


def test_protocolo_bate_e_nosso_numero_nao_vira_divergencia_que_diz_qual():
    """A CONSEQUENCIA DE ERRAR AQUI VIAJA PARA A CENTRAL."""
    con = banco()
    titulo(con, nosso="YK0000000000999")
    c = conferir(con, xml(um()))
    assert not c["entram"]
    assert len(c["divergem"]) == 1
    motivo = c["divergem"][0]["motivo"]
    assert "nosso numero" in motivo
    assert "YK0000000000999" in motivo and NOSSO in motivo


def test_sem_nosso_numero_confere_pelo_valor():
    con = banco()
    titulo(con, nosso="")
    assert len(conferir(con, xml(um(nosso="")))["entram"]) == 1


def test_sem_nosso_numero_e_com_valor_diferente_recusa():
    con = banco()
    titulo(con, nosso="", valor=100)
    c = conferir(con, xml(um(nosso="")))
    assert not c["entram"]
    assert "valor" in c["divergem"][0]["motivo"]


def test_sem_nada_para_conferir_entra_em_divergencia_e_nao_calado():
    con = banco()
    titulo(con, nosso="", valor=0)
    c = conferir(con, xml(um(nosso="", valor="")))
    assert not c["entram"]
    assert "nem valor para conferir" in c["divergem"][0]["motivo"]


def test_dois_titulos_com_o_mesmo_protocolo_nao_se_desempatam():
    con = banco()
    titulo(con)
    titulo(con, numero="OUTRO")
    c = conferir(con, xml(um()))
    assert not c["entram"]
    assert "qual deles" in c["divergem"][0]["motivo"]


def test_titulo_que_ja_tem_a_mesma_chave_nao_entra_de_novo():
    con = banco()
    titulo(con, chave=CHAVE)
    c = conferir(con, xml(um()))
    assert not c["entram"]
    assert len(c["ja_tem"]) == 1


def test_chave_diferente_da_que_esta_la_nao_sobrescreve():
    """Trocar a chave ja usada faria os dois lados falarem de titulos
    diferentes com o mesmo nome."""
    con = banco()
    titulo(con, chave="21987650100000001260417")
    c = conferir(con, xml(um()))
    assert not c["entram"]
    assert "ja tem a chave" in c["divergem"][0]["motivo"]


def test_chave_com_tamanho_errado_fica_de_fora_dizendo_por_que():
    con = banco()
    titulo(con)
    c = conferir(con, xml(um(chave="123")))
    assert c["fora"][0]["motivo"].endswith("digitos do CENPROT")


def test_titulo_sem_protocolo_no_arquivo_fica_de_fora():
    con = banco()
    titulo(con)
    c = conferir(con, xml(um(protocolo="")))
    assert "nao diz o protocolo" in c["fora"][0]["motivo"]


def test_protocolo_que_esta_casa_nao_tem_fica_de_fora():
    con = banco()
    titulo(con, protocolo="9999999999")
    c = conferir(con, xml(um()))
    assert "nenhum titulo desta casa" in c["fora"][0]["motivo"]


def test_versao_diferente_da_medida_e_avisada_e_nao_recusada():
    """Ler arquivo mais novo e seguro; GERAR na versao que ninguem conferiu
    e que nao se pode."""
    con = banco()
    titulo(con)
    c = conferir(con, xml(um(), versao="1.24-geral"))
    assert c["versao_conhecida"] is False
    assert len(c["entram"]) == 1


def test_conferir_nao_grava_nada():
    con = banco()
    tid = titulo(con)
    conferir(con, xml(um()))
    assert con.execute("SELECT chave_cenprot FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] is None


# ------------------------------------------------------------------ guardar


def test_guardar_preenche_a_chave():
    con = banco()
    tid = titulo(con)
    r = guardar(con, xml(um()))
    assert r["gravadas"] == 1
    assert con.execute("SELECT chave_cenprot FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == CHAVE


def test_o_que_nao_casa_nao_derruba_o_arquivo():
    """A regra do lote da remessa: um titulo sem par sao os outros que
    continuam sendo o trabalho do dia."""
    con = banco()
    tid = titulo(con)
    outra = "21987650199999901260418"
    r = guardar(con, xml(um(), um(chave=outra, protocolo="2604180001")))
    assert r["gravadas"] == 1
    assert len(r["fora"]) == 1
    assert con.execute("SELECT chave_cenprot FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == CHAVE


def test_guardar_nao_sobrescreve_chave_que_ja_esta_la():
    con = banco()
    tid = titulo(con, chave="21987650100000001260417")
    with pytest.raises(CP.CenprotError):
        guardar(con, xml(um()))
    assert con.execute("SELECT chave_cenprot FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "21987650100000001260417"


def test_arquivo_em_que_nada_entra_recusa_contando_cada_caso():
    con = banco()
    titulo(con, chave=CHAVE)
    with pytest.raises(CP.CenprotError) as e:
        guardar(con, xml(um()))
    texto = str(e.value)
    assert "1 titulos" in texto and "ja tem a mesma chave" in texto


def test_guardar_e_repetivel_a_segunda_vez_recusa_por_ja_ter():
    con = banco()
    titulo(con)
    guardar(con, xml(um()))
    with pytest.raises(CP.CenprotError) as e:
        guardar(con, xml(um()))
    assert "ja tem a mesma chave" in str(e.value)


# ------------------------------------------------------------------ o outro lado


def test_quantos_sem_chave_devolve_tres_numeros():
    """«Faltam 1.366» esconde que a maioria falta por outro motivo."""
    con = banco()
    titulo(con)
    titulo(con, protocolo="", nosso="A", numero="SEM PROTOCOLO")
    titulo(con, protocolo="2604180001", nosso="B", chave=CHAVE, numero="COM")
    q = CP.quantos_sem_chave(con)
    assert q == {"total": 3, "com_chave": 1, "sem_protocolo": 1,
                 "a_preencher": 1}


def test_titulos_sem_chave_so_lista_quem_tem_protocolo():
    """Sem protocolo nao ha por onde casar — listar seria dar trabalho que
    este modulo nao resolve."""
    con = banco()
    tid = titulo(con)
    titulo(con, protocolo="", nosso="A", numero="SEM PROTOCOLO")
    assert [t["id"] for t in CP.titulos_sem_chave(con)] == [tid]


# ------------------------------------------------------------------ o ensaio


@pytest.mark.skipif(not ARQUIVO_REAL.exists(),
                    reason="o XML do CENPROT so existe na maquina do oficial")
def test_ensaio_o_arquivo_real_de_31_08_2026():
    """O QUE PROVA O LEITOR E O ARQUIVO DE VERDADE, e nao o boneco.

    Os 175 titulos, a versao, e a conferencia que fecha a chave: a data que ela
    carrega tem de ser a mesma que o proprio XML declara no `<data_protocolo>`.
    Sao duas fontes dentro do mesmo arquivo, e e por isso que a leitura da
    chave se sustenta sem ninguem ter documentado o formato.
    """
    lido = CP.ler(ARQUIVO_REAL.read_bytes())
    assert lido["versao"] == CP.VERSAO_MEDIDA
    # A comarca é a da casa de verdade, e sai do próprio arquivo (B3): o que se
    # prova é que ela tem sete dígitos e que TODA chave começa por ela.
    comarca_real = lido["comarca"]
    assert comarca_real.isdigit() and len(comarca_real) == 7
    assert lido["cartorio"] == "01"
    assert len(lido["titulos"]) == 175

    decompoem = bate_a_data = tem_protocolo = 0
    for t in lido["titulos"]:
        partes = CP.decompor_chave(t["chave"])
        if not partes:
            continue
        decompoem += 1
        assert partes["ibge"] == comarca_real
        assert partes["cartorio"] == "01"
        if CP.data_do_protocolo(t["chave"]) == t["data_protocolo"]:
            bate_a_data += 1
        if t["protocolo"]:
            tem_protocolo += 1

    assert decompoem == 175, "as 175 chaves tem a forma medida"
    assert bate_a_data == 175, "a data da chave e a data do protocolo"
    assert tem_protocolo == 175, "todo titulo traz o nosso protocolo ao lado"


@pytest.mark.skipif(not ARQUIVO_REAL.exists(),
                    reason="o XML do CENPROT so existe na maquina do oficial")
def test_ensaio_os_175_do_arquivo_real_casariam_com_os_titulos_desta_casa():
    """Com o protocolo preenchido, os 175 entram — e e a carga que o preenche.

    Na producao de hoje o `conferir` devolve **175 fora**, e esta certo: o
    `protocolo` esta vazio em 1.366 de 1.366, porque a passada da carga que o
    traz ainda nao rodou no servidor. O teste monta o que a carga vai montar.
    """
    con = banco()
    lido = CP.ler(ARQUIVO_REAL.read_bytes())
    for i, t in enumerate(lido["titulos"]):
        titulo(con, protocolo=t["protocolo"], nosso=t["nosso_numero"],
               valor=CP._centavos(t["valor"]) or 0, numero=f"T{i}")
    # A casa, aqui, é a do arquivo real (a comarca não se escreve no teste).
    c = CP.conferir(con, ARQUIVO_REAL.read_bytes(),
                    comarca=lido["comarca"], cartorio=lido["cartorio"])
    assert len(c["entram"]) == 175, (
        "fora: {} · divergem: {}".format(len(c["fora"]), len(c["divergem"])))


# ------------------------------------------------- o arquivo de emolumentos


ARQUIVO_EMOLUMENTOS = _arquivo_real("MA-???????-01-E-20260831-01.txt")


def com_custas(con) -> sqlite3.Connection:
    """Traz `cx_faixas` e `cx_vigencias` da producao, so leitura.

    A TABELA DE EMOLUMENTOS NAO SE ESCREVE A MAO NO TESTE. Transcrever as 270
    faixas daria um teste que prova a minha transcricao, e nao a tabela — e o
    preco que sai daqui e o que o devedor paga no balcao.
    """
    con.execute("ATTACH DATABASE 'file:C:/ProgramData/CartorioGestao"
                "/cartorio_gestao.sqlite3?mode=ro' AS prod")
    for t in ("cx_faixas", "cx_vigencias", "cx_servicos", "cx_servico_valores"):
        con.execute(f"CREATE TABLE {t} AS SELECT * FROM prod.{t}")
    con.execute("DETACH DATABASE prod")
    return con


def banco_com_custas() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:", uri=True)
    con.row_factory = sqlite3.Row
    init_pt_schema(con)
    return com_custas(con)


def protestado(con, *, valor, chave, situacao="PROTESTADO") -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, valor_centavos,
               saldo_centavos, situacao, chave_cenprot, origem, criado_em)
           VALUES ('DMI','T',?,?,?,?,'CRA',?)""",
        (valor, valor, situacao, chave, AGORA))
    return int(cur.lastrowid)


tem_producao = pytest.mark.skipif(
    not Path(r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3").exists(),
    reason="a tabela de emolumentos so existe na maquina da serventia")


@tem_producao
def test_os_dois_precos_saem_da_faixa_do_valor():
    """A conta medida contra o arquivo do ano — 166 de 173 no centavo."""
    con = banco_com_custas()
    # R$ 101,60 cai na faixa 2 dos dois itens.
    p = CP.precos_do_titulo(con, 10160, vigencia=CP.VIGENCIA_MEDIDA)
    assert p["retirada"] == 9654          # 82,64 + 13,90
    assert p["cancelamento"] == 24826     # 224,68 + 23,58


@tem_producao
def test_a_fronteira_da_faixa_bate_no_centavo():
    """R$ 220,00 esta na 17.4.2 (ate 220,07) e R$ 220,08 ja e a 17.4.3.

    Errar a fronteira por um centavo publica na Central um preco que a casa
    nao pode cobrar — e quem descobre e o devedor, no balcao.
    """
    con = banco_com_custas()
    antes = CP.precos_do_titulo(con, 22000, vigencia=CP.VIGENCIA_MEDIDA)
    depois = CP.precos_do_titulo(con, 22008, vigencia=CP.VIGENCIA_MEDIDA)
    assert antes["retirada"] == 9654
    assert depois["retirada"] == 10073
    assert antes["cancelamento"] == 24826
    assert depois["cancelamento"] == 25560


@tem_producao
def test_a_faixa_de_cima_nao_tem_teto_na_pratica():
    """MEDIDO: a ultima faixa vai ate R$ 999.999.999.999,99.

    Eu havia escrito um teste dizendo que valor alto «cai fora de toda faixa»,
    e ele ficou vermelho: **nao cai**. Valor nenhum desta casa fica de fora, e
    e bom que seja assim — titulo de R$ 1 milhao tem preco.
    """
    con = banco_com_custas()
    base = CP.constantes(con, CP.VIGENCIA_MEDIDA)
    p = CP.precos_do_titulo(con, 100_000_000_00, vigencia=CP.VIGENCIA_MEDIDA)
    assert p["retirada"] == base["retirada"] + 96410
    assert p["cancelamento"] == base["cancelamento"] + 160691


@tem_producao
def test_sem_faixa_carregada_devolve_none_e_nao_zero():
    """O `None` guarda a TABELA QUE NAO CARREGOU, e nao o valor alto.

    Zero num arquivo de precos e uma afirmacao — «nao custa nada» —, e o
    devedor viria ao balcao com ela na mao. Importacao de tabela que entrou
    pela metade e o caso real: a vigencia existe e as faixas nao.
    """
    con = banco_com_custas()
    con.execute("DELETE FROM cx_faixas WHERE vigencia = ?",
                (CP.VIGENCIA_MEDIDA,))
    p = CP.precos_do_titulo(con, 10160, vigencia=CP.VIGENCIA_MEDIDA)
    assert p["retirada"] is None and p["cancelamento"] is None


@tem_producao
def test_titulo_sem_faixa_sai_da_lista_com_o_motivo_em_vez_de_virar_zero():
    con = banco_com_custas()
    protestado(con, valor=10160, chave=CHAVE)
    con.execute("DELETE FROM cx_faixas WHERE vigencia = ?",
                (CP.VIGENCIA_MEDIDA,))
    r = CP.gerar_emolumentos(con, comarca="2198765", cartorio="01", uf="MA",
                             data="2026-08-31")
    assert r["linhas"] == 0
    assert "nao cai em nenhuma faixa" in r["fora"][0]["motivo"]
    assert "0.00" not in r["conteudo"]


@tem_producao
def test_so_entra_protesto_vivo_e_com_chave():
    """MEDIDO: os 173 do arquivo real sao todos protestados e nao cancelados.

    E sem a chave nao ha linha — ela e o primeiro campo.
    """
    con = banco_com_custas()
    protestado(con, valor=10160, chave=CHAVE)
    protestado(con, valor=10160, chave="21987650199999901260418",
               situacao="PAGO")
    protestado(con, valor=10160, chave="21987650188888801260419",
               situacao="CANCELADO")
    protestado(con, valor=10160, chave="", situacao="PROTESTADO")
    r = CP.gerar_emolumentos(con, comarca="2198765", cartorio="01", uf="MA",
                             data="2026-08-31")
    assert r["linhas"] == 1
    assert CHAVE in r["conteudo"]


@tem_producao
def test_o_formato_do_arquivo():
    """Seis campos por `|`, cabecalho, e PONTO decimal — nao virgula."""
    con = banco_com_custas()
    protestado(con, valor=10160, chave=CHAVE)
    r = CP.gerar_emolumentos(con, comarca="2198765", cartorio="01", uf="MA",
                             data="2026-08-31")
    linhas = r["conteudo"].splitlines()
    assert linhas[0] == CP.CABECALHO_EMOLUMENTOS
    campos = linhas[1].split("|")
    assert len(campos) == 6
    assert campos == [CHAVE, "96.54", "248.26", "2198765", "01", "20260831"]


@tem_producao
def test_o_nome_do_arquivo_e_o_medido():
    assert CP.nome_do_arquivo(uf="MA", comarca="2198765", cartorio="01",
                              data="2026-08-31") == \
        "MA-2198765-01-E-20260831-01.txt"


@tem_producao
def test_a_constante_SOMADA_bate_com_a_MEDIDA_no_arquivo_real():
    """O GUARDA MAIS IMPORTANTE DESTE MODULO.

    De um lado, os R$ 82,64 e R$ 224,68 **medidos** no arquivo de emolumentos
    do ano — 166 de 173 titulos no centavo. Do outro, a soma dos itens que o
    arquivo de EDITAL nomeia, tirada da tabela na hora.

    **As duas tem de dar o mesmo numero.** Se um dia divergirem — item que
    mudou de codigo, tabela importada pela metade —, o vermelho aparece aqui, e
    nao num arquivo publicado na Central com o preco errado.
    """
    con = banco_com_custas()
    base = CP.constantes(con, CP.VIGENCIA_MEDIDA)
    assert base["retirada"] == CP.CONSTANTE_RETIRADA_MEDIDA
    assert base["cancelamento"] == CP.CONSTANTE_CANCELAMENTO_MEDIDA


@tem_producao
def test_a_constante_ACOMPANHA_a_tabela_em_vez_de_ficar_parada():
    """ANTES ELE RECUSAVA GERAR FORA DA 10022, e isso deixou de ser preciso.

    Enquanto a receita da constante era desconhecida, um numero fixo publicaria
    o preco do ano passado. Agora ela se soma da tabela — e o teste prova que a
    soma MUDA de uma vigencia para a outra, que e o que faz o arquivo seguir a
    virada sozinho.
    """
    con = banco_com_custas()
    corrente = CP.constantes(con, CP.VIGENCIA_MEDIDA)
    anterior = CP.constantes(con, 10021)
    assert anterior["retirada"] is not None
    assert anterior["retirada"] < corrente["retirada"], (
        "a tabela anterior e mais barata, e a constante tem de refletir isso")


@tem_producao
def test_tabela_sem_os_itens_recusa_dizendo_quais():
    """Arquivo de precos com item faltando publica valor MENOR que o cobrado."""
    con = banco_com_custas()
    protestado(con, valor=10160, chave=CHAVE)
    con.execute("""DELETE FROM cx_servico_valores WHERE servico IN
                   (SELECT codigo FROM cx_servicos WHERE codigo_tj = ?)""",
                (CP.ITEM_POR_FOLHA,))
    with pytest.raises(CP.CenprotError) as e:
        CP.gerar_emolumentos(con, comarca="2198765", cartorio="01", uf="MA",
                             data="2026-08-31")
    assert CP.ITEM_POR_FOLHA in str(e.value)


@tem_producao
@pytest.mark.skipif(not ARQUIVO_EMOLUMENTOS.exists(),
                    reason="o arquivo do CENPROT so existe na maquina do oficial")
def test_ensaio_o_arquivo_de_emolumentos_real():
    """O ENSAIO CONTRA O ARQUIVO DE VERDADE — 375 linhas do ano de 2025.

    Ele nao compara linha a linha: os valores dos titulos vem do acervo, e o
    casamento entre a chave da Central e o titulo daqui so e CERTO nos dias com
    um titulo so. O que se prova aqui e o **formato** e a **conta**.
    """
    linhas = ARQUIVO_EMOLUMENTOS.read_text(encoding="utf-8").splitlines()
    assert linhas[0] == CP.CABECALHO_EMOLUMENTOS, "o cabecalho que a casa gera"

    con = banco_com_custas()
    reais = {}
    comarcas = set()
    for linha in linhas[1:]:
        if not linha.strip():
            continue
        c = linha.split("|")
        assert len(c) == 6
        reais[c[0]] = (c[1], c[2])
        assert CP.decompor_chave(c[0]), "toda chave tem a forma medida"
        # A comarca é a da casa de verdade e sai do próprio arquivo (B3): o
        # que se prova é que ela tem sete dígitos e que a chave começa por ela.
        assert c[3].isdigit() and len(c[3]) == 7 and c[0].startswith(c[3])
        assert c[4] == "01" and c[5] == "20260831"
        comarcas.add(c[3])
    assert len(reais) == 375
    assert len(comarcas) == 1, "o arquivo é de uma casa só"

    # A CONTA: todo par (retirada, cancelamento) do arquivo tem de ser
    # produzivel por alguma faixa — se um par nao for, a formula esta errada.
    possiveis = set()
    for centavos in (5000, 10160, 30000, 50000, 100000, 200000, 400000,
                     800000, 1600000, 3000000, 6000000, 12000000, 25000000,
                     50000000, 100000000):
        p = CP.precos_do_titulo(con, centavos, vigencia=CP.VIGENCIA_MEDIDA)
        if p["retirada"]:
            possiveis.add((CP._reais(p["retirada"]),
                           CP._reais(p["cancelamento"])))
    achados = sum(1 for v in reais.values() if v in possiveis)
    assert achados >= 300, (
        f"so {achados} de 375 pares saem da formula — ela nao explica o "
        f"arquivo")


@tem_producao
def test_o_arquivo_sai_com_CRLF_e_sem_BOM():
    """MEDIDO BYTE A BYTE no arquivo real: `0d 0a`, e comeca em `nm_`.

    O `\n` sozinho pareceria igual em qualquer editor daqui e chegaria
    diferente na Central — o pior tipo de diferenca, a que so aparece do lado
    de la. E foi assim que eu escrevi na primeira versao.
    """
    con = banco_com_custas()
    protestado(con, valor=10160, chave=CHAVE)
    r = CP.gerar_emolumentos(con, comarca="2198765", cartorio="01", uf="MA",
                             data="2026-08-31")
    bruto = r["conteudo"].encode("utf-8")
    assert not bruto.startswith(b"\xef\xbb\xbf"), "o real nao tem BOM"
    assert bruto.startswith(b"nm_")
    assert b"\r\n" in bruto
    assert bruto.count(b"\n") == bruto.count(b"\r\n"), "todo \n e CRLF"
    assert bruto.endswith(b"\r\n")


@tem_producao
@pytest.mark.skipif(not ARQUIVO_EMOLUMENTOS.exists(),
                    reason="o arquivo do CENPROT so existe na maquina do oficial")
def test_o_que_a_casa_gera_tem_os_MESMOS_bytes_de_forma_do_real():
    """Cabecalho, separador, fim de linha e ausencia de BOM — conferidos
    contra o arquivo que a Central aceitou."""
    real = ARQUIVO_EMOLUMENTOS.read_bytes()
    con = banco_com_custas()
    protestado(con, valor=10160, chave=CHAVE)
    meu = CP.gerar_emolumentos(con, comarca="2198765", cartorio="01", uf="MA",
                               data="2026-08-31")["conteudo"].encode("utf-8")
    assert meu.split(b"\r\n")[0] == real.split(b"\r\n")[0], "o cabecalho"
    assert real.startswith(b"nm_") and meu.startswith(b"nm_")
    assert real.count(b"\r\n") and meu.count(b"\r\n")
    assert len(meu.split(b"\r\n")[1].split(b"|")) == \
        len(real.split(b"\r\n")[1].split(b"|")) == 6
