"""O de-para de município do IBGE, e o cabeçalho desta serventia.

POR QUE ISTO PRECISOU EXISTIR
    `ibge_remessa.py` sabia o layout do arquivo desde 27/08/2026, e o arquivo
    continuava impossível de gerar: ele pede **código** de município e de UF —
    `21` e `07001` — e o sistema guarda **nome** de cidade em texto.

    Sem o de-para, cada município teria de ser digitado em código pelo
    escrevente. E código digitado à mão numa remessa estatística é o pior tipo
    de erro: ninguém lê o arquivo depois para conferir.

O QUE SE MEDIU NO ACERVO (28/08/2026)
    O E-Ofício tem duas tabelas de município, e elas não são iguais:

        `tbMunicipio`  5.638 linhas, **5.570 códigos distintos** — exatamente o
                       número de municípios do Brasil.
        `MUNICIPIOS`   5.444 linhas. Faltam 126.

    E tem `tbIBGE_Propriedades`, com o cabeçalho que esta casa mandava: UF
    `21`, município `07001`, distrito `05`, cartório `01`.

    **Os dois se conferem sozinhos**: o código IBGE de Cidade Exemplo é
    `2198765`, que é `21` + `07001` — a UF e o município do cabeçalho. Não
    precisei acreditar em nenhum dos dois isoladamente.
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

import acervo_carga as AC          # noqa: E402
import ibge_schema as IB           # noqa: E402

AGORA = "2026-08-28T04:00:00"
ACERVO_REAL = Path(r"C:\ProgramData\CartorioGestao\acervo_eoficio.sqlite3")


@pytest.fixture()
def banco():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    IB.init_ibge_schema(con)
    con.executescript(
        "CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
    return con


@pytest.fixture()
def acervo():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE tbMunicipio (
            strEstado TEXT, intEstadoIBGE INTEGER,
            strMunicipio TEXT, intMunicipioIBGE REAL, id REAL
        );
        INSERT INTO tbMunicipio VALUES
            ('MA', 21, 'Cidade Exemplo',  2198765, 1),
            ('MA', 21, 'São Luís',      2111300, 2),
            ('SP', 35, 'São Paulo',     3550308, 3),
            ('MA', 21, 'Pindaré Mirim', NULL,    4);
        CREATE TABLE tbIBGE_Propriedades (
            strUF TEXT, strMunicipio TEXT, strDistrito TEXT, strCodigo TEXT
        );
        INSERT INTO tbIBGE_Propriedades VALUES ('21','98765','05','01');
    """)
    return con


# ------------------------------------------------------- o de-para


def test_o_codigo_de_sete_digitos_se_parte_em_uf_e_municipio(banco, acervo):
    """`2198765` é `21` (Maranhão) mais `07001` (Cidade Exemplo).

    O arquivo pede os dois em campos SEPARADOS — `COD-UF-NASC` com 2 posições e
    `COD-MUNIC-NASC` com 5 —, e por isso os dois se guardam prontos. Recortar
    na hora de montar a linha poria a mesma conta em cinco lugares do código.
    """
    AC.carregar_ibge(banco, acervo, agora=AGORA)
    m = banco.execute(
        "SELECT * FROM ib_municipios WHERE codigo_ibge=2198765").fetchone()
    assert m["codigo_uf"] == 21
    assert m["codigo_mun"] == "98765"
    assert m["uf"] == "MA"


def test_os_zeros_a_esquerda_ficam(banco, acervo):
    """`07001` com cinco posições — o arquivo é de largura fixa.

    Guardar `7001` faria a linha inteira andar uma casa para a esquerda, e o
    IBGE leria outro município.
    """
    AC.carregar_ibge(banco, acervo, agora=AGORA)
    for codigo, esperado in ((2198765, "98765"), (3550308, "50308")):
        assert banco.execute(
            "SELECT codigo_mun FROM ib_municipios WHERE codigo_ibge=?",
            (codigo,)).fetchone()["codigo_mun"] == esperado


def test_a_busca_acha_com_acento_e_sem(banco, acervo):
    """`UPPER` e `LOWER` do SQLite são ASCII, e por isso a busca é pelo
    `nome_norm` — quem digita «sao luis» tem de achar «São Luís»."""
    AC.carregar_ibge(banco, acervo, agora=AGORA)
    for escrito in ("São Luís", "sao luis", "SAO LUIS", "  São   Luís  "):
        achado = banco.execute(
            "SELECT nome FROM ib_municipios WHERE nome_norm=? AND uf='MA'",
            (IB.normalizar_nome(escrito),)).fetchone()
        assert achado, escrito
        assert achado["nome"] == "São Luís"


def test_municipio_sem_codigo_e_rejeitado_e_nao_calado(banco, acervo):
    """Ele não entra — a chave da tabela É o código —, e a rejeição fica
    escrita. `lidos = inseridos + repetidos + rejeitados` é a conta que faz o
    número da tela não mentir."""
    r = AC.carregar_ibge(banco, acervo, agora=AGORA).como_dict()
    assert r["lidos"] == r["inseridos"] + r["repetidos"] + r["rejeitados"]
    assert r["rejeitados"] == 1
    assert "sem código do IBGE" in r["motivos_da_rejeicao"][0]


def test_rodar_de_novo_nao_conta_como_novo(banco, acervo):
    """Repetível por construção: a segunda rodada não inventa 5.570 inserções.

    E ela atualiza o nome, porque o IBGE renomeia município — `OR REPLACE`, e
    não `OR IGNORE`.
    """
    AC.carregar_ibge(banco, acervo, agora=AGORA)
    quantos = banco.execute("SELECT COUNT(*) n FROM ib_municipios").fetchone()["n"]
    segunda = AC.carregar_ibge(banco, acervo, agora=AGORA).como_dict()
    assert segunda["inseridos"] == 0
    assert segunda["repetidos"] == quantos
    assert banco.execute(
        "SELECT COUNT(*) n FROM ib_municipios").fetchone()["n"] == quantos


# ------------------------------------------------- o cabeçalho da casa


def test_o_cabecalho_vem_do_acervo(banco, acervo):
    """As quatro primeiras posições de toda linha do arquivo dizem quem manda."""
    AC.carregar_ibge(banco, acervo, agora=AGORA)
    guardado = dict(banco.execute("SELECT key, value FROM settings").fetchall())
    assert guardado == {"ibge_uf": "21", "ibge_municipio": "98765",
                        "ibge_distrito": "05", "ibge_cartorio": "01"}


def test_o_cabecalho_confere_com_o_codigo_do_municipio(banco, acervo):
    """A prova cruzada: o cabeçalho que a casa mandava e a tabela oficial
    dizem a mesma coisa sobre onde esta serventia fica.

    Foi isso que me deixou usar os dois sem ter de acreditar em nenhum
    isoladamente — onde a igualdade importa, ela se constrói.
    """
    AC.carregar_ibge(banco, acervo, agora=AGORA)
    s = dict(banco.execute("SELECT key, value FROM settings").fetchall())
    m = banco.execute(
        "SELECT * FROM ib_municipios WHERE nome_norm='cidade exemplo'").fetchone()
    assert f"{m['codigo_uf']:02d}" == s["ibge_uf"]
    assert m["codigo_mun"] == s["ibge_municipio"]


def test_o_que_o_oficial_ja_respondeu_nao_e_sobrescrito(banco, acervo):
    """O que a pessoa respondeu vale mais que o que o programa antigo guardava.

    Mesma regra da marca do livro a confirmar: carga que ressuscita o que
    alguém já resolveu ensina o balcão a ignorar o sistema.
    """
    banco.execute("INSERT INTO settings(key, value) VALUES ('ibge_cartorio','07')")
    r = AC.carregar_ibge(banco, acervo, agora=AGORA).como_dict()
    assert banco.execute(
        "SELECT value FROM settings WHERE key='ibge_cartorio'").fetchone()[0] == "07"
    assert r["contagens"].get("cabecalho_ja_respondido") == 1


def test_acervo_sem_a_tabela_recusa_com_frase_de_balcao(banco):
    vazio = conexao_de_teste()
    vazio.row_factory = sqlite3.Row
    with pytest.raises(AC.CargaError, match="tbMunicipio"):
        AC.carregar_ibge(banco, vazio, agora=AGORA)


# ------------------------------------------------ contra o acervo real


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_contra_o_acervo_real(banco):
    """Teste sobre acervo falso prova a REGRA; sobre o real prova o DADO.

    São 5.570 municípios — o número de municípios do Brasil — e 27 UFs. Se um
    dia isso mudar, é aqui que se vê, e não numa remessa recusada pelo IBGE.
    """
    acervo = sqlite3.connect(f"file:{ACERVO_REAL}?mode=ro", uri=True)
    acervo.row_factory = sqlite3.Row
    r = AC.carregar_ibge(banco, acervo, agora=AGORA).como_dict()
    assert r["inseridos"] == 5570
    assert r["rejeitados"] == 68
    assert r["lidos"] == r["inseridos"] + r["repetidos"] + r["rejeitados"]
    assert banco.execute(
        "SELECT COUNT(DISTINCT uf) n FROM ib_municipios").fetchone()["n"] == 27
    # E a serventia se acha nela (o nome vem do acervo, e não se escreve aqui:
    # sanitização B3, 10/10/2026).
    cab = acervo.execute(
        "SELECT strUF, strMunicipio FROM tbIBGE_Propriedades LIMIT 1").fetchone()
    codigo = int(str(cab[0]).strip().zfill(2) + str(cab[1]).strip().zfill(5))
    achado = banco.execute(
        "SELECT nome FROM ib_municipios WHERE codigo_ibge=?", (codigo,)).fetchone()
    assert achado and achado["nome"].strip()


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_o_acervo_guarda_os_nomes_em_utf8(banco):
    """Conferido nos BYTES, e não no que o console mostra.

    O console desta máquina mangia acento, e por duas vezes me fez ler o
    contrário do que estava no banco. `c3a1` é «á» em UTF-8; em latin-1 seria
    `e1`. Sem isso, «São Luís» entraria como «SÃ£o LuÃ­s» e a busca por nome
    não acharia nunca.
    """
    acervo = sqlite3.connect(f"file:{ACERVO_REAL}?mode=ro", uri=True)
    acervo.text_factory = bytes
    cru = acervo.execute(
        "SELECT strMunicipio FROM tbMunicipio WHERE intMunicipioIBGE=2111300"
    ).fetchone()[0]
    assert cru.decode("utf-8") == "São Luís"


# ==================================================================
# O QUE O ASSENTO PASSOU A GUARDAR PARA O IBGE
#
# Três coisas do nascimento e uma do óbito que não estavam em lugar nenhum
# deste sistema, e que não se deduzem de nada: onde a criança nasceu, se o
# parto foi gemelar, o número da DNV e o número da DO.
#
# O RESTO DO LAYOUT NÃO VIROU CAMPO, de propósito: o lugar do nascimento é a
# naturalidade do registrado, a residência da mãe é o endereço dela, e a idade
# da genitora se calcula da data de nascimento. Campo para dado que já existe é
# a segunda fonte que diverge da primeira.
# ==================================================================

import ibge_remessa as IBGE      # noqa: E402
import rc_assento as RC          # noqa: E402
from nucleo_schema import init_nucleo_schema   # noqa: E402
from rc_schema import init_rc_schema           # noqa: E402

SERVENTIA = {"nome": "SERVENTIA", "cidade_uf": "CIDADE EXEMPLO/MA",
             "ri_cns": "000000"}


@pytest.fixture()
def civil():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rc_schema(con)
    return con


def _lavrar(con, especie="NASCIMENTO", **ibge):
    extra = {}
    if especie in ("NASCIMENTO", "NATIMORTO"):
        extra = {
            "dados": {"sexo": "M"},
            "termo_dados": {"local_fato_nome": "Hospital Municipal"},
            "pessoas": [
                {"papel": "REGISTRADO", "nome": "FULANO DE TAL", "sexo": "M"},
                {"papel": "MAE", "nome": "MARIA DA SILVA"},
                {"papel": "PAI", "nome": "IGNORADO"},
                {"papel": "DECLARANTE", "nome": "MARIA DA SILVA"},
            ],
        }
        if especie == "NATIMORTO":
            ibge.setdefault("numero_do", "12345")
    elif especie == "OBITO":
        extra = {
            "termo_dados": {"local_fato_nome": "Hospital Municipal"},
            "pessoas": [
                {"papel": "FALECIDO", "nome": "FULANO DE TAL"},
                {"papel": "MAE", "nome": "IGNORADO"},
                {"papel": "PAI", "nome": "IGNORADO"},
                {"papel": "DECLARANTE", "nome": "FULANO"},
            ],
            # «deixou bens»: a CRC exige, e desde o relato #130 (14/10/2026)
            # a lavratura também
            "marcas_do_obito": {"obito_possui_bens": "NAO"},
        }
        ibge.setdefault("numero_do", "98765")
    elif especie in ("CASAMENTO", "CASAMENTO_RELIGIOSO"):
        extra = {
            "regime_bens": "COMUNHAO_PARCIAL",
            "pessoas": [
                {"papel": "NUBENTE1", "nome": "FULANO"},
                {"papel": "NUBENTE2", "nome": "BELTRANA"},
                {"papel": "MAE_NUBENTE1", "nome": "ANA"},
                {"papel": "PAI_NUBENTE1", "nome": "IGNORADO"},
                {"papel": "MAE_NUBENTE2", "nome": "RITA"},
                {"papel": "PAI_NUBENTE2", "nome": "IGNORADO"},
                {"papel": "TESTEMUNHA", "nome": "CICLANO"},
            ],
        }
    return RC.lavrar_assento(
        con, especie=especie, nome="FULANO DE TAL", sv=SERVENTIA,
        agora="2026-08-28T09:00:00", data_extenso="vinte e oito de agosto",
        data_fato="2026-08-20", ibge=(ibge or None), **extra)


def test_o_nascimento_guarda_o_que_o_ibge_pede(civil):
    r = _lavrar(civil, local_nascimento=1, gemeo=2, dnv="1234567890")
    linha = civil.execute("SELECT * FROM rc_assentos WHERE id=?",
                          (r["assento_id"],)).fetchone()
    assert linha["ibge_local_nascimento"] == 1
    assert linha["ibge_gemeo"] == 2
    assert linha["dnv"] == "1234567890"


def test_o_que_nao_se_informa_fica_nulo(civil):
    """Preencher com «ignorado» por conta própria seria afirmar que se
    perguntou. A remessa mostra o que falta.

    O LOCAL DO NASCIMENTO SAIU DESTE TESTE em 14/10/2026: o SIRC o exige, e
    desde o relato #130 a lavratura do balcão recusa sem ele (ver
    `test_relato_130_centrais_na_lavratura.py`). Os outros continuam nulos."""
    r = _lavrar(civil, local_nascimento=1)
    linha = civil.execute("SELECT * FROM rc_assentos WHERE id=?",
                          (r["assento_id"],)).fetchone()
    assert linha["ibge_gemeo"] is None
    assert linha["dnv"] is None


def test_codigo_fora_do_catalogo_e_recusado_no_balcao(civil):
    """O catálogo de LOCAL-NASC pula do 3 para o 5, e o de GEMEO do 3 para o 9.

    Quem digitar 4 acerta o tipo do campo e erra o conteúdo — e sem esta
    conferência o IBGE recusaria o trimestre inteiro meses depois, sem dizer
    qual linha. Recusar aqui custa uma frase; recusar lá custa o trimestre.
    """
    assert 4 not in IBGE.LOCAL_DO_NASCIMENTO
    with pytest.raises(RC.RcError, match="não é código do IBGE"):
        _lavrar(civil, local_nascimento=4)
    with pytest.raises(RC.RcError, match="não é código do IBGE"):
        _lavrar(civil, gemeo=4)


def test_a_recusa_diz_quais_codigos_existem(civil):
    """Mensagem que só diz «inválido» faz a pessoa tentar de novo no escuro."""
    try:
        _lavrar(civil, local_nascimento=4)
    except RC.RcError as erro:
        for texto in IBGE.LOCAL_DO_NASCIMENTO.values():
            assert texto in str(erro)
    else:
        pytest.fail("devia ter recusado")


def test_dnv_nao_entra_em_obito_e_do_nao_entra_em_nascimento(civil):
    """Cada espécie tem o seu papel: a DNV é do hospital, a DO é do médico."""
    with pytest.raises(RC.RcError, match="dados do IBGE"):
        _lavrar(civil, especie="OBITO", dnv="123")
    with pytest.raises(RC.RcError, match="dados do IBGE"):
        _lavrar(civil, especie="NASCIMENTO", numero_do="123")


def test_o_obito_guarda_o_numero_da_declaracao(civil):
    r = _lavrar(civil, especie="OBITO", numero_do="98765")
    assert civil.execute("SELECT numero_do FROM rc_assentos WHERE id=?",
                         (r["assento_id"],)).fetchone()["numero_do"] == "98765"


def test_completar_depois_funciona(civil):
    """Assento tardio, óbito de pessoa achada: nem sempre se sabe na hora.

    Lavra com o local (o SIRC o exige desde o relato #130, 14/10/2026) e o
    completar de depois o troca — o que se guarda é o completar."""
    r = _lavrar(civil, local_nascimento=1)
    RC.anotar_para_o_ibge(civil, r["assento_id"], local_nascimento=3,
                          gemeo=1, dnv="55555")
    linha = civil.execute("SELECT * FROM rc_assentos WHERE id=?",
                          (r["assento_id"],)).fetchone()
    assert (linha["ibge_local_nascimento"], linha["ibge_gemeo"],
            linha["dnv"]) == (3, 1, "55555")


def test_a_tela_de_lavrar_oferece_os_catalogos_medidos():
    """Digitar código de IBGE à mão é erro que ninguém confere."""
    html = (RAIZ / "templates" / "atrib_rcpn_novo.html").read_text(
        encoding="utf-8")
    assert 'name="ibge_local"' in html
    assert 'name="ibge_gemeo"' in html
    assert 'name="dnv"' in html
    assert 'name="numero_do"' in html
    # e ela diz que aquilo não sai na certidão
    assert "não sai na certidão" in html


# ==================================================================
# A HABILITAÇÃO DE OUTRA SERVENTIA — item 14.1.6 da tabela
#
# Decisão do oficial em 28/08/2026: o casamento leva UM selo, comprado na
# habilitação; quando a habilitação é de outro cartório, o assento compra selo
# próprio, citando o de lá.
#
# O QUE ESTES TESTES PROTEGEM É DINHEIRO DO CASAL: os dois caminhos têm de ser
# exclusivos, e o que os separa é uma coisa que o escrevente RESPONDE — nunca
# uma dedução do sistema.
# ==================================================================


def test_o_casamento_daqui_nao_marca_serventia_nenhuma(civil):
    """Vazio quer dizer «é daqui», e é o caso comum."""
    r = _lavrar(civil, especie="CASAMENTO")
    linha = civil.execute("SELECT * FROM rc_assentos WHERE id=?",
                          (r["assento_id"],)).fetchone()
    assert not linha["habilitacao_serventia"]


def test_o_casamento_de_fora_guarda_a_serventia_e_o_selo(civil):
    r = RC.lavrar_assento(
        civil, especie="CASAMENTO", nome="FULANO E BELTRANA", sv=SERVENTIA,
        agora="2026-08-28T09:00:00", data_extenso="vinte e oito de agosto",
        habilitacao_serventia="CARTÓRIO DE IMPERATRIZ/MA",
        habilitacao_selo="DELA0000000000000000000AAAA",
        data_fato="2026-08-20",
        regime_bens="COMUNHAO_PARCIAL",
        pessoas=[
            {"papel": "NUBENTE1", "nome": "FULANO"},
            {"papel": "NUBENTE2", "nome": "BELTRANA"},
            {"papel": "MAE_NUBENTE1", "nome": "ANA"},
            {"papel": "PAI_NUBENTE1", "nome": "IGNORADO"},
            {"papel": "MAE_NUBENTE2", "nome": "RITA"},
            {"papel": "PAI_NUBENTE2", "nome": "IGNORADO"},
            {"papel": "TESTEMUNHA", "nome": "CICLANO"},
        ],
    )
    linha = civil.execute("SELECT * FROM rc_assentos WHERE id=?",
                          (r["assento_id"],)).fetchone()
    assert linha["habilitacao_serventia"] == "CARTÓRIO DE IMPERATRIZ/MA"
    assert linha["habilitacao_selo"] == "DELA0000000000000000000AAAA"


def test_o_selo_de_fora_sozinho_e_recusado(civil):
    """Ele não diz de onde veio — e é o «de onde» que vai no papel e no selo."""
    with pytest.raises(RC.RcError, match="de que serventia"):
        RC.lavrar_assento(
            civil, especie="CASAMENTO", nome="FULANO E BELTRANA", sv=SERVENTIA,
            agora="2026-08-28T09:00:00", data_extenso="vinte e oito",
            habilitacao_selo="DELA000000",
            data_fato="2026-08-20",
            regime_bens="COMUNHAO_PARCIAL",
            pessoas=[
                {"papel": "NUBENTE1", "nome": "FULANO"},
                {"papel": "NUBENTE2", "nome": "BELTRANA"},
                {"papel": "MAE_NUBENTE1", "nome": "ANA"},
                {"papel": "PAI_NUBENTE1", "nome": "IGNORADO"},
                {"papel": "MAE_NUBENTE2", "nome": "RITA"},
                {"papel": "PAI_NUBENTE2", "nome": "IGNORADO"},
                {"papel": "TESTEMUNHA", "nome": "CICLANO"},
            ],
        )


def test_so_o_casamento_se_lavra_a_vista_de_habilitacao(civil):
    """Um óbito com «habilitação de outra serventia» é dado que confunde — e,
    pior, poderia fazer o sistema comprar selo onde não deve."""
    for especie in ("NASCIMENTO", "OBITO"):
        with pytest.raises(RC.RcError, match="Só o casamento"):
            RC.lavrar_assento(
                civil, especie=especie, nome="FULANO", sv=SERVENTIA,
                agora="2026-08-28T09:00:00", data_extenso="vinte e oito",
                habilitacao_serventia="CARTÓRIO DE IMPERATRIZ/MA",
                data_fato="2026-08-20",
                dados={"sexo": "M"} if especie == "NASCIMENTO" else None,
                termo_dados={"local_fato_nome": "Hospital Municipal"},
                ibge={"numero_do": "1"} if especie == "OBITO" else None,
                pessoas=(
                    [{"papel": "REGISTRADO", "nome": "FULANO", "sexo": "M"},
                     {"papel": "MAE", "nome": "M"},
                     {"papel": "PAI", "nome": "IGNORADO"},
                     {"papel": "DECLARANTE", "nome": "M"}]
                    if especie == "NASCIMENTO" else
                    [{"papel": "FALECIDO", "nome": "FULANO"},
                     {"papel": "MAE", "nome": "IGNORADO"},
                     {"papel": "PAI", "nome": "IGNORADO"},
                     {"papel": "DECLARANTE", "nome": "X"}]
                ))


def test_a_tela_pergunta_de_onde_veio_a_habilitacao(civil):
    """A pergunta tem de estar lá, e tem de dizer o que cada resposta faz —
    é uma decisão de dinheiro tomada por quem está no balcão."""
    html = (RAIZ / "templates" / "atrib_rcpn_novo.html").read_text(
        encoding="utf-8")
    assert 'name="habilitacao_serventia"' in html
    assert 'name="habilitacao_selo"' in html
    assert "não compra selo nenhum" in html
    assert "compra selo próprio" in html


# ------------------------------------------ os catálogos do óbito, fechados


def test_os_catalogos_do_obito_batem_com_o_que_a_casa_exportou():
    """Medidos nas 13 linhas reais, e confirmados pela especificação do IBGE.

    A coincidência que fecha: a única linha com NATUREZA 2 é justamente a morte
    em via pública (LOCAL 4) de um homem de 26 anos. «Violenta» encaixa; nenhuma
    outra leitura encaixaria as duas coisas ao mesmo tempo.
    """
    assert IBGE.NATUREZA_DO_OBITO == {1: "natural", 2: "violenta",
                                      9: "ignorado"}
    assert set(IBGE.LOCAL_DO_OBITO) == {1, 2, 3, 4, 5, 9}
    assert IBGE.LOCAL_DO_OBITO[4] == "via pública"


def test_o_catalogo_do_obito_nao_e_o_do_nascimento():
    """A diferença é o `4`: o óbito tem «via pública» e o nascimento não.

    Usar um pelo outro mandaria «outros» onde o IBGE espera «via pública» — e
    é essa a informação que ele mais quer, porque é onde a morte violenta
    acontece.
    """
    assert 4 in IBGE.LOCAL_DO_OBITO
    assert 4 not in IBGE.LOCAL_DO_NASCIMENTO


def test_os_catalogos_oficiais_pulam_numero(civil):
    """E quem preencher a sequência «óbvia» acerta o tipo do campo e erra o
    conteúdo. O estado civil não tem 5; o local do nascimento não tem 4."""
    assert 5 not in IBGE.ESTADO_CIVIL_DO_FALECIDO
    assert 4 not in IBGE.LOCAL_DO_NASCIMENTO
