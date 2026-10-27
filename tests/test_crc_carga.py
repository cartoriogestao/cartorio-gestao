"""A carga da CRC Nacional — o XML medido no manual oficial v2.6.

O QUE ESTES TESTES GUARDAM
    **Que o que não pode ir não some.** Volta em `retidos`, com o motivo.
    Mandar só o que deu certo produziria um arquivo bem formado e incompleto — e
    a Central o aceitaria, que é o pior desfecho.

    **Que «Violenta» não vira «Acidental».** A CRC só enumera «Natural ou
    Acidental», e esta casa registrou 27 naturais e 4 violentas. Um homicídio é
    violento e não é acidental.

    **Que a matrícula segura o registro.** Ela é obrigatória e o verificador não
    se gera — o CNJ distribui um programa em vez de publicar o algoritmo.

    **E o defeito que o primeiro ensaio contra dado real achou**: o padrão do
    `get` só vale quando a chave falta, e numa linha de banco ela existe sempre.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import crc_carga as CRC                                          # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-20T09:00"
CNS = "000000"
M32 = "00000001552026100002269100086802"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(tmp_path):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(banco)
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    return {"app": app, "banco": banco, "db": db}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _assento(con, **extras):
    campos = {"serie": "RC_A", "especie": "NASCIMENTO", "numero": 1,
              "nome": "MARIA ÍSIS", "data_ato": "2026-08-20",
              "data_fato": "2026-08-18", "situacao": "ATIVO",
              "origem": "SISTEMA", "criado_em": AGORA, "matricula": M32}
    campos.update(extras)
    colunas = ", ".join(campos)
    marcas = ", ".join("?" for _ in campos)
    cur = con.execute(f"INSERT INTO rc_assentos ({colunas}) VALUES ({marcas})",
                      tuple(campos.values()))
    return int(cur.lastrowid)


def _pessoa(con, aid, papel, nome, **extras):
    campos = {"assento_id": aid, "papel": papel, "nome": nome,
              "nome_norm": nome.lower(), "criado_em": AGORA}
    campos.update(extras)
    colunas = ", ".join(campos)
    marcas = ", ".join("?" for _ in campos)
    con.execute(f"INSERT INTO rc_pessoas ({colunas}) VALUES ({marcas})",
                tuple(campos.values()))


def _municipio(con, nome="Cidade Exemplo", uf="MA", codigo_ibge=2198765):
    """Uma linha de `ib_municipios`, para os testes que precisam do código
    IBGE resolver — a tabela só se popula pela carga do acervo, e um banco
    de teste nasce sem ela."""
    con.execute(
        """INSERT INTO ib_municipios (codigo_ibge, codigo_uf, codigo_mun, uf,
               nome, nome_norm, origem, criado_em)
           VALUES (?, 21, '98765', ?, ?, ?, 'TESTE', ?)""",
        (codigo_ibge, uf, nome, nome.lower(), AGORA))


def _nascimento(con, **extras):
    aid = _assento(con, **extras)
    _pessoa(con, aid, "REGISTRADO", extras.get("nome", "MARIA ÍSIS"), sexo="F")
    _pessoa(con, aid, "PAI", "JOSÉ", sexo="M")
    _pessoa(con, aid, "MAE", "ANA", sexo="F")
    return aid


# ------------------------------------------------ o catálogo do manual


def test_a_versao_e_a_do_manual():
    assert CRC.VERSAO == "2.6"
    assert CRC.ACAO_CARGA == "CARGA"


def test_os_tres_movimentos_sao_os_do_manual():
    blocos = {v[0] for v in CRC.MOVIMENTO_DA_ESPECIE.values()}
    assert blocos == {"MOVIMENTONASCIMENTOTN", "MOVIMENTOCASAMENTOTC",
                      "MOVIMENTOOBITOTO"}


def test_os_vocabulários_que_faltam_estao_declarados():
    """A lista está VAZIA, e a lista vazia é uma resposta.

    **ATÉ 10/09/2026 ELA TINHA CINCO, E OS CINCO ESTAVAM NO XSD.** Estava
    escrito aqui e no módulo que «o manual manda ver o XSD e o XSD não veio» —
    ele veio: `FONTES_EXTERNAS/CRC_manual_carga_webservice_v2.6.pdf`, com o
    texto ao lado, tem **344 enumerações** dentro, e ESTADOCIVIL,
    TIPOLOCALOBITO, ELEITOR, POSSUIBENS e REGIMECASAMENTO estão todas lá.

    **A constante fica**, e não se apaga: é ela que impede o pior desfecho —
    escolher valor por semelhança e a Central aceitar. Quando aparecer um campo
    sem vocabulário, é aqui que ele se declara.
    """
    assert CRC.SEM_VOCABULARIO == ()


def test_os_cinco_vocabularios_existem_de_verdade():
    """E cada um com os valores do XSD, contados.

    Sem este guarda, alguém apagaria uma tabela e os campos voltariam a sair
    vazios **calados** — que foi exatamente o estado anterior.
    """
    assert set(CRC.LOCAL_NASCIMENTO.values()) == {
        "UNIDADE_SAUDE", "FORA_UNIDADE_SAUDE", "IGNORADO"}
    assert set(CRC.TIPO_MORTE.values()) == {"NATURAL", "VIOLENTA", "IGNORADA"}
    assert set(CRC.TIPO_LOCAL_OBITO.values()) == {
        "HOSPITAL", "OUTROS_SERVICOS_SAUDE", "DOMICILIO", "VIA_PUBLICA",
        "OUTRO", "IGNORADO"}
    assert set(CRC.ESTADO_CIVIL.values()) == {
        "SOLTEIRO", "CASADO", "VIUVO", "DIVORCIADO", "SEPARADO", "OUTROS",
        "IGNORADO"}
    assert set(CRC.REGIME_CASAMENTO.values()) == {
        "COMUNHAO_PARCIAL", "COMUNHAO_UNIVERSAL", "PARTICIPACAO_FINAL_AQUESTOS",
        "SEPARACAO_BENS", "SEPARACAO_LEGAL_BENS", "OUTROS", "IGNORADO"}
    assert set(CRC.MARCA_SIM_NAO.values()) == {"S", "N", "I"}


def test_a_chave_do_vocabulario_nao_se_perde_no_acento():
    """**«Viúvo» com acento não achava nada**, e 2 dos 31 falecidos da produção
    subiam sem estado civil, calados. O mesmo engolia «Comunhão Parcial de
    Bens», que é como os dois únicos casamentos com regime o têm escrito.

    É o `UPPER` que é ASCII pela quarta vez neste projeto.
    """
    assert CRC.ESTADO_CIVIL.get(CRC._chave("Viúvo")) == "VIUVO"
    assert CRC.ESTADO_CIVIL.get(CRC._chave("viuva")) == "VIUVO"
    assert (CRC.REGIME_CASAMENTO.get(CRC._chave("Comunhão Parcial de Bens"))
            == "COMUNHAO_PARCIAL")
    # E a separação obrigatória do art. 1.641 é a que a Central chama de LEGAL.
    assert (CRC.REGIME_CASAMENTO.get(CRC._chave("SEPARACAO_OBRIGATORIA"))
            == "SEPARACAO_LEGAL_BENS")


def test_a_funcao_que_tira_acento_e_a_DA_CASA_e_nao_uma_copia():
    """**O defeito mais caro deste projeto foi copiar `normalizar_nome`** com um
    comentário dizendo que era «a mesma» — não era, e a busca por nome deixou de
    achar. Aqui ela se importa, e este teste prova que é a mesma função.
    """
    import ibge_schema
    codigo = Path(CRC.__file__).read_text(encoding="utf-8")
    assert "from ibge_schema import normalizar_nome" in codigo
    assert "def normalizar_nome" not in codigo, (
        "cópia da normalizadora dentro de crc_carga — importe, não copie")
    for bruto in ("Viúvo", "Comunhão Parcial", "SOLTEIRA", "ignorado"):
        assert CRC._chave(bruto) == ibge_schema.normalizar_nome(bruto).upper()


def test_a_cor_tem_os_seis_valores_do_manual():
    assert set(CRC.COR_PELE.values()) == {
        "BRANCA", "PRETA", "PARDA", "AMARELA", "INDIGENA", "IGNORADA"}


# =========================================== o gemeo, e o local do nascimento
#
# **O RELATO QUE ACHOU ISTO FOI DE UM REGISTRO SO:** «verifique o json do
# nilton» — assento 1240 da producao, nascimento nº 5172 de 1974, cujo teor diz
# com todas as letras «O registrado não é gêmeo». O arquivo dizia que sim.


def test_o_codigo_1_do_ibge_quer_dizer_que_NAO_e_gemeo(casa):
    """**210 DOS 212 NASCIMENTOS SUBIAM DIZENDO QUE A PESSOA TEM GÊMEO.**

    Aqui havia `if assento.get("ibge_gemeo"): POSSUIGEMEOS = "S"` — e o código
    do IBGE é **1 = não é gêmeo**, 2 = gêmeo, 3 = trigêmeo ou mais, 9 =
    ignorado. Um é verdadeiro em Python.

    Medido na produção em 10/09/2026: 210 assentos com o código 1, 2 sem
    código, e **zero** com irmão gêmeo amarrado (`gemeo_ordem` e
    `gemeo_irmao_id` vazios em todos).

    **O XSD tem os dois valores** — `S` e `N` —, e por isso «N» é resposta, e
    não silêncio.
    """
    con = _con(casa)
    with con:
        aid = _assento(con, especie="NASCIMENTO", nome="NILTON",
                       ibge_gemeo=1)
        _pessoa(con, aid, "REGISTRADO", "NILTON", sexo="M")
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert "<POSSUIGEMEOS>N</POSSUIGEMEOS>" in xml
    assert "<POSSUIGEMEOS>S</POSSUIGEMEOS>" not in xml


def test_o_gemeo_de_verdade_vai_com_S(casa):
    con = _con(casa)
    with con:
        aid = _assento(con, especie="NASCIMENTO", nome="GEMEO", ibge_gemeo=2)
        _pessoa(con, aid, "REGISTRADO", "GEMEO", sexo="F")
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert "<POSSUIGEMEOS>S</POSSUIGEMEOS>" in xml
    # «Total de irmãos gêmeos do registrado. Se nasceram tri-gêmeos = 2» — o
    # manual na letra, logo o gêmeo simples é 1.
    assert "<NUMEROGEMEOS>1</NUMEROGEMEOS>" in xml


def test_o_numero_de_gemeos_nao_se_inventa(casa):
    """**O código 3 é «trigêmeo OU MAIS», e não dá o número.**

    Escrever 2 ali seria inventar um número num arquivo que vai à Central.
    A marca vai preenchida; a contagem vai **vazia** — e não ausente: desde
    10/09/2026 `NUMEROGEMEOS` é obrigatória na sequência do XSD
    (`minOccurs` não declarado é `1`), e omiti-la faz a Central recusar o
    registro dizendo que o elemento seguinte «não era esperado ali».
    """
    con = _con(casa)
    with con:
        aid = _assento(con, especie="NASCIMENTO", nome="TRIGEMEO",
                       ibge_gemeo=3)
        _pessoa(con, aid, "REGISTRADO", "TRIGEMEO", sexo="M")
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert "<POSSUIGEMEOS>S</POSSUIGEMEOS>" in xml
    assert "<NUMEROGEMEOS></NUMEROGEMEOS>" in xml


def test_o_ignorado_vira_nao_e_gemeo_por_falta_de_valor_neutro(casa):
    """O XSD só tem `S` e `N` para `POSSUIGEMEOS` — sem `''` na enumeração,
    ao contrário de `REGIMECASAMENTO`, que tem `IGNORADO`. Sem um terceiro
    valor honesto, `N` é o padrão seguro: é o que vale para a esmagadora
    maioria (210 de 212 medidos), e o art. 234 já amarra cada gêmeo ao irmão
    por outra coluna (`gemeo_irmao_id`), que não depende deste código.

    O manual **não** põe a tag entre as obrigatórias do nascimento — são
    `NOMEREGISTRADO`, `MATRICULA`, `DATAREGISTRO` e `SEXO` —, mas o XSD a
    exige presente mesmo assim.
    """
    con = _con(casa)
    with con:
        a9 = _assento(con, especie="NASCIMENTO", nome="IGNORADO 9",
                      ibge_gemeo=9)
        _pessoa(con, a9, "REGISTRADO", "IGNORADO 9", sexo="M")
        av = _assento(con, especie="NASCIMENTO", nome="SEM CODIGO")
        _pessoa(con, av, "REGISTRADO", "SEM CODIGO", sexo="F")
    xml = CRC.montar(con, [a9, av], cns=CNS)["xml"]
    assert xml.count("<POSSUIGEMEOS>N</POSSUIGEMEOS>") == 2


def test_a_amarracao_do_art_234_vale_mais_que_o_codigo_do_ibge(casa):
    """`gemeo_irmao_id` diz que ESTE assento está amarrado ao do irmão — é o
    art. 234, e vale mais que um código de remessa estatística.

    A distinção é de 30/08/2026, quando as duas colunas nasceram: «`ibge_gemeo`
    diz se é gêmeo; o art. 234 exige qual é a ordem».
    """
    con = _con(casa)
    with con:
        irmao = _assento(con, especie="NASCIMENTO", nome="IRMAO")
        aid = _assento(con, especie="NASCIMENTO", nome="COM IRMAO",
                       ibge_gemeo=1, gemeo_irmao_id=irmao, gemeo_ordem=1)
        _pessoa(con, aid, "REGISTRADO", "COM IRMAO", sexo="M")
        _pessoa(con, irmao, "REGISTRADO", "IRMAO", sexo="M")
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert "<POSSUIGEMEOS>S</POSSUIGEMEOS>" in xml


def test_o_local_do_nascimento_vai_por_PALAVRA(casa):
    """**A CENTRAL ENUMERA PALAVRA, E SAÍA O NÚMERO DO IBGE** — em 212 de 212.

    O de-para estava no acervo, com esse nome:
    `tbRCPN_LocalNascimento.strWScrc`, escrito pelo próprio E-Ofício.

    E o campo é **obrigatório para registro lavrado de 13/10/2015 em diante**
    (`**` no manual): um nascimento novo seria recusado pela Central.
    """
    con = _con(casa)
    with con:
        hosp = _assento(con, especie="NASCIMENTO", nome="NO HOSPITAL",
                        ibge_local_nascimento=1)
        _pessoa(con, hosp, "REGISTRADO", "NO HOSPITAL", sexo="F")
        casa_ = _assento(con, especie="NASCIMENTO", nome="EM CASA",
                         ibge_local_nascimento=3)
        _pessoa(con, casa_, "REGISTRADO", "EM CASA", sexo="M")
        outro = _assento(con, especie="NASCIMENTO", nome="EM OUTRO LUGAR",
                         ibge_local_nascimento=5)
        _pessoa(con, outro, "REGISTRADO", "EM OUTRO LUGAR", sexo="M")
    xml = CRC.montar(con, [hosp, casa_, outro], cns=CNS)["xml"]
    assert "<LOCALNASCIMENTO>UNIDADE_SAUDE</LOCALNASCIMENTO>" in xml
    assert xml.count("<LOCALNASCIMENTO>FORA_UNIDADE_SAUDE</LOCALNASCIMENTO>") == 2
    # E NENHUM numero cru.
    for n in "12359":
        assert f"<LOCALNASCIMENTO>{n}</LOCALNASCIMENTO>" not in xml


def test_o_local_do_obito_nao_usa_o_id_da_tabela_do_acervo(casa):
    """**AS DUAS TABELAS NUMERAM DIFERENTE, e trocá-las poria «Ignorado» onde é
    hospital.**

    O `id` de `tbRCTO_TipoLocalObito` é `1 = Ignorado` e `4 = Hospital`; o
    código do IBGE, que é o que a coluna guarda, é `1 = hospital` e
    `4 = via pública`. É a armadilha das duas tabelas de tipo de imóvel do ONR.
    """
    con = _con(casa)
    with con:
        a1 = _assento(con, especie="OBITO", serie="RC_C", nome="NO HOSPITAL",
                      ibge_local_obito=1, cor_raca="Branca",
                      obito_possui_bens="N")
        _pessoa(con, a1, "FALECIDO", "NO HOSPITAL", sexo="M")
        a4 = _assento(con, especie="OBITO", serie="RC_C", nome="NA RUA",
                      ibge_local_obito=4, cor_raca="Parda",
                      obito_possui_bens="N")
        _pessoa(con, a4, "FALECIDO", "NA RUA", sexo="M")
    xml = CRC.montar(con, [a1, a4], cns=CNS)["xml"]
    assert "<TIPOLOCALOBITO>HOSPITAL</TIPOLOCALOBITO>" in xml
    assert "<TIPOLOCALOBITO>VIA_PUBLICA</TIPOLOCALOBITO>" in xml
    assert "IGNORADO" not in xml


# ------------------------------------------------ o que fica retido


def test_sem_matricula_o_registro_nao_vai(casa):
    """Ela é obrigatória e o verificador não se gera — o CNJ distribui um
    programa em vez de publicar o algoritmo."""
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="SEM MATRÍCULA", matricula=None)
    r = CRC.montar(con, [aid], cns=CNS)
    assert r["quantos"] == 0
    assert "matrícula de 32 dígitos" in " ".join(r["retidos"][0]["faltas"])


def test_a_morte_violenta_SOBE_porque_o_XSD_a_enumera(casa):
    """**ELA FICAVA RETIDA, E A RETENÇÃO ERA MINHA E ESTAVA ERRADA.**

    O que este teste dizia: «a CRC só enumera Natural ou Acidental; um
    homicídio é violento e não é acidental, e mapear um no outro seria afirmar
    à Central uma coisa que a casa não registrou».

    **O raciocínio estava certo e a premissa era falsa.** A frase «(Natural ou
    Acidental)» existe, e vem de uma **página de recomendações** do manual
    (pág. 76) — a mesma que manda buscar o estado civil numa tabela externa que
    o XSD tem em casa. **O XSD, que é contra o que o arquivo se valida, enumera
    `'', NATURAL, VIOLENTA, IGNORADA`.**

    **Prosa de recomendação não é schema.** Os 4 óbitos violentos desta casa
    deixam de ser retidos, e sobem com a palavra que a Central declara.

    **GRAVA-SE O CÓDIGO 2, E NÃO A PALAVRA «Violenta»** — 19/10/2026, na
    migração para o PostgreSQL. A coluna é número (`bigint` na produção
    migrada, e no SQLite da produção só havia número nela), e nenhum caminho
    do sistema grava palavra ali: a tela passa por `rc_assento._codigo_do_ibge`,
    a leitura de documentos devolve `"2"`, e a carga do acervo traduz o
    «Violenta» de `strTipoMorte` em `2` antes de gravar. O SQLite guardava o
    texto na coluna inteira; o PostgreSQL o recusa — e os 4 violentos desta
    casa são `2`.
    """
    con = _con(casa)
    with con:
        aid = _assento(con, especie="OBITO", serie="RC_C", nome="ANTONIO",
                       ibge_natureza_obito=2, cor_raca="Parda",
                       obito_possui_bens="N")
        _pessoa(con, aid, "FALECIDO", "ANTONIO", sexo="M")
    r = CRC.montar(con, [aid], cns=CNS)
    assert r["quantos"] == 1
    assert r["retidos"] == []
    assert "<TIPOMORTE>VIOLENTA</TIPOMORTE>" in r["xml"]


def test_a_morte_vai_pelo_CODIGO_do_ibge_e_nao_so_pela_palavra(casa):
    """**A COLUNA GUARDA NÚMERO, E O DICIONÁRIO ERA DE PALAVRA.**

    `rc_assentos.ibge_natureza_obito` traz `1` e `2` na produção — os códigos
    do IBGE. A chave aqui era «NATURAL», e o `.get` devolvia `None`: a tag
    **não saía em 31 de 31 óbitos**, sem erro em lugar nenhum. As palavras
    continuam valendo porque o blob do acervo as traz.
    """
    con = _con(casa)
    with con:
        a1 = _assento(con, especie="OBITO", serie="RC_C", nome="POR CODIGO",
                      ibge_natureza_obito="1", cor_raca="Branca",
                      obito_possui_bens="N")
        _pessoa(con, a1, "FALECIDO", "POR CODIGO", sexo="M")
        a2 = _assento(con, especie="OBITO", serie="RC_C", nome="POR CODIGO 2",
                      ibge_natureza_obito=2, cor_raca="Branca",
                      obito_possui_bens="N")
        _pessoa(con, a2, "FALECIDO", "POR CODIGO 2", sexo="F")
    xml = CRC.montar(con, [a1, a2], cns=CNS)["xml"]
    assert "<TIPOMORTE>NATURAL</TIPOMORTE>" in xml
    assert "<TIPOMORTE>VIOLENTA</TIPOMORTE>" in xml


def test_a_morte_natural_vai(casa):
    # O CÓDIGO 1 DO IBGE, e não a palavra «Natural»: a coluna é número e
    # nenhum caminho do sistema grava palavra nela (ver a morte violenta).
    con = _con(casa)
    with con:
        aid = _assento(con, especie="OBITO", serie="RC_C", nome="JOAQUIM",
                       ibge_natureza_obito=1, cor_raca="Branca",
                       obito_possui_bens="N")
        _pessoa(con, aid, "FALECIDO", "JOAQUIM", sexo="M")
    r = CRC.montar(con, [aid], cns=CNS)
    assert r["quantos"] == 1
    # A CAIXA E A DO XSD: `NATURAL`, e nao `Natural`. Enumeracao de schema se
    # compara caractere a caractere.
    assert "<TIPOMORTE>NATURAL</TIPOMORTE>" in r["xml"]
    # E a palavra do acervo, que o vocabulário ainda aceita, sai na mesma caixa.
    assert CRC.TIPO_MORTE.get(CRC._chave("Natural")) == "NATURAL"


def test_cor_fora_do_catalogo_fica_retida(casa):
    con = _con(casa)
    with con:
        aid = _assento(con, especie="OBITO", serie="RC_C", nome="X",
                       cor_raca="MORENA")
        _pessoa(con, aid, "FALECIDO", "X", sexo="M")
    r = CRC.montar(con, [aid], cns=CNS)
    assert r["quantos"] == 0
    assert "MORENA" in " ".join(r["retidos"][0]["faltas"])


def test_especie_que_a_crc_nao_recebe_fica_retida(casa):
    con = _con(casa)
    with con:
        aid = _assento(con, especie="INTERDICAO", serie="RC_E")
    r = CRC.montar(con, [aid], cns=CNS)
    assert r["quantos"] == 0
    assert "nascimento, casamento e óbito" in " ".join(
        r["retidos"][0]["faltas"])


def test_o_retido_nao_some_do_arquivo_calado(casa):
    """Mandar só o que deu certo produziria um arquivo bem formado e incompleto
    — e a Central o aceitaria."""
    con = _con(casa)
    with con:
        bom = _nascimento(con)
        ruim = _nascimento(con, numero=2, nome="SEM MATRÍCULA",
                           matricula=None)
    r = CRC.montar(con, [bom, ruim], cns=CNS)
    assert r["quantos"] == 1
    assert len(r["retidos"]) == 1
    assert r["retidos"][0]["nome"] == "SEM MATRÍCULA"


# ------------------------------------------------ o XML


def test_o_xml_tem_a_raiz_e_o_cns(casa):
    con = _con(casa)
    with con:
        aid = _nascimento(con)
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert xml.startswith('<?xml version="1.0" encoding="utf-8"?>')
    assert "<CARGAREGISTROS>" in xml
    assert "<VERSAO>2.6</VERSAO>" in xml
    assert "<ACAO>CARGA</ACAO>" in xml
    assert f"<CNS>{CNS}</CNS>" in xml


def test_a_data_vai_no_formato_do_manual(casa):
    """`DD/MM/AAAA` — e o que não se reconhece sai vazio, em vez de adivinhar:
    data mal formada derruba o registro inteiro e a recusa não diz qual campo
    era."""
    con = _con(casa)
    with con:
        aid = _nascimento(con)
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert "<DATAREGISTRO>20/08/2026</DATAREGISTRO>" in xml
    assert "<DATANASCIMENTO>18/08/2026</DATANASCIMENTO>" in xml


def test_a_filiacao_precisa_de_nome_E_sexo(casa):
    """«no mínimo o nome e o sexo da filiação devem ser preenchidos» — e é a
    mesma invariante que este projeto descobriu medindo o acervo: um assento tem
    um pai e uma mãe, e o par decide.

    **E ESTE TESTE MUDOU DE CONSEQUÊNCIA EM 10/09/2026, do relato do oficial:
    «estao saindo sem preencher os pais».** Ele afirmava que a mãe sem sexo
    «não entra» — e era verdade: entrava o registro **sem ela**, calado, com o
    nome dela gravado no sistema. A regra da CRC continua a mesma; o que mudou é
    que agora o registro **fica retido, com o motivo**, em vez de subir pela
    metade.

    O que ele guarda continua sendo o mesmo: **filiação sem sexo não sobe.**

    E a consequência mudou **duas vezes no mesmo dia**: primeiro eu fiz o
    registro inteiro ser retido, e os testes existentes me corrigiram — o
    manual não exige a filiação, e travar por ela deixaria 20 registros
    válidos fora da Central. Agora o registro **sobe** e a tela **avisa**, que
    é o que o oficial pediu.
    """
    con = _con(casa)
    with con:
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "MARIA", sexo="F")
        _pessoa(con, aid, "PAI", "JOSÉ", sexo="M")
        _pessoa(con, aid, "MAE", "SEM SEXO")          # sem sexo: não entra
    r = CRC.montar(con, [aid], cns=CNS)
    assert "SEM SEXO" not in r["xml"]
    assert "JOSÉ" in r["xml"]
    # O registro SOBE, e o que falta aparece na lista do que arrumar.
    assert r["quantos"] == 1 and r["retidos"] == []
    assert len(r["a_arrumar"]) == 1
    arrumar = " ".join(r["a_arrumar"][0]["arrumar"])
    assert "sexo" in arrumar and "SEM SEXO" in arrumar


def test_a_filiacao_que_falta_nao_sobe_calada(casa):
    """**O relato de 10/09/2026, e o defeito era o SILÊNCIO.**

        «preciso que resolva o problema do json das certidoes da crc, estao
         saindo sem preencher os pais»

    Medido na produção naquele dia: dos 210 nascimentos, **24 filiações de 420
    não subiam, e nada dizia.** O arquivo saía bem formado e incompleto — o
    desfecho que este módulo existe para evitar.

    **O conserto é o aviso, e não a trava**: o registro sobe (o manual não
    exige a filiação) e a tela diz o que arrumar.
    """
    con = _con(casa)
    with con:
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "MARIA", sexo="F")
        _pessoa(con, aid, "PAI", "JOSÉ", sexo="M")
        # a mãe nem existe — a carga do acervo não a trouxe
    r = CRC.montar(con, [aid], cns=CNS)
    assert r["quantos"] == 1 and r["retidos"] == []
    arrumar = " ".join(r["a_arrumar"][0]["arrumar"])
    assert "filiação 1 (mãe)" in arrumar


def test_a_carga_nao_escreve_sexo_em_lugar_nenhum():
    """**Decisão do oficial em 10/09/2026: «deixa sexo em aberto para quem
    estiver lavrando arrume».**

    Eu perguntei se a tela devia oferecer marcar «ignorado» para o nome subir,
    e ele disse que não. «Ignorado» é uma **declaração** de que ninguém sabe, e
    quem a faz é quem tem o livro na mão — não um programa querendo completar
    o arquivo.

    Este varredor existe para a comodidade não voltar por uma porta lateral:
    este módulo **mede e avisa**, e não escreve. Quem corrige é
    `/rcpn/<id>/editar`, com motivo e auditoria.
    """
    fonte = (RAIZ / "crc_carga.py").read_text(encoding="utf-8")
    corpo = "\n".join(
        linha for linha in fonte.splitlines()
        if not linha.lstrip().startswith("#"))
    for proibido in ("UPDATE ", "INSERT ", "DELETE "):
        assert proibido not in corpo.upper(), (
            f"a carga da CRC passou a escrever no banco ({proibido.strip()}) — "
            "ela mede e avisa; quem corrige é a tela de editar o assento")


def test_o_que_trava_e_o_que_se_avisa_sao_listas_DIFERENTES(casa):
    """**A distinção é a lição do dia, e ela custou seis testes vermelhos.**

    `o_que_falta` retém o registro — é o obrigatório do manual
    (`NOMEREGISTRADO`, `MATRICULA`, `DATAREGISTRO`, `SEXO`).
    `o_que_arrumar` deixa subir e avisa.

    Confundir as duas foi o que eu fiz na primeira versão: travei por um campo
    que a Central não exige.
    """
    con = _con(casa)
    with con:
        # sem matrícula: TRAVA (obrigatório do manual)
        trava = _nascimento(con, matricula="", numero=2)
        # sem a mãe: AVISA (o manual não a exige)
        avisa = _assento(con, numero=3)
        _pessoa(con, avisa, "REGISTRADO", "MARIA", sexo="F")
        _pessoa(con, avisa, "PAI", "JOSÉ", sexo="M")
    r = CRC.montar(con, [trava, avisa], cns=CNS)
    assert r["quantos"] == 1
    assert [x["assento_id"] for x in r["retidos"]] == [trava]
    assert [x["assento_id"] for x in r["a_arrumar"]] == [avisa]


def test_o_aviso_diz_o_NOME_de_quem_falta_o_sexo(casa):
    """Sem o nome no aviso, o escrevente não sabe a qual dos dois ir.

    São vinte assentos retidos na produção; «falta o sexo da filiação» sem
    dizer de quem obrigaria a abrir cada um para descobrir.
    """
    con = _con(casa)
    with con:
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "MARIA", sexo="F")
        _pessoa(con, aid, "PAI", "PLINIO GUEDES DA SILVA")
        _pessoa(con, aid, "MAE", "ANA", sexo="F")
    r = CRC.montar(con, [aid], cns=CNS)
    arrumar = " ".join(r["a_arrumar"][0]["arrumar"])
    assert "PLINIO GUEDES DA SILVA" in arrumar
    assert "filiação 2 (pai)" in arrumar


def test_genitor_declarado_IGNORADO_nao_cobra_sexo(casa):
    """**«IGNORADO» é declaração, e não campo em branco.**

    Medido na produção: no assento 70 o pai **chama-se «IGNORADO»** — é como o
    acervo escreve «pai não declarado». Cobrar o sexo dele mandaria o balcão
    procurar na estante o que o livro diz que não existe.

    A régua é `rc_assento.e_declarado_ausente`, a mesma da lavratura — e não uma
    lista de palavras escrita aqui, que divergiria da dela no primeiro conserto.
    """
    con = _con(casa)
    with con:
        _municipio(con)
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "MARIA", sexo="F",
               naturalidade_cidade="Cidade Exemplo", naturalidade_uf="MA")
        _pessoa(con, aid, "PAI", "IGNORADO")
        _pessoa(con, aid, "MAE", "ANA", sexo="F")
    r = CRC.montar(con, [aid], cns=CNS)
    assert r["quantos"] == 1, "o registro devia subir"
    assert r["retidos"] == []
    # E não se cobra o sexo de quem o livro diz que não foi declarado.
    assert r["a_arrumar"] == []
    # Sobe com a mãe, e sem inventar filiação para o pai não declarado.
    assert r["xml"].count("<FILIACAONASCIMENTO>") == 1
    assert "ANA" in r["xml"]


def test_o_sexo_por_extenso_do_acervo_serve(casa):
    """O acervo escreve «Masculino»; o ato novo escreve `M`. Os dois valem.

    É a armadilha das duas grafias, que este projeto já pagou noutros módulos —
    e aqui o mapa `SEXO` a cobre desde o começo. O teste existe para ela não se
    perder num conserto distraído.
    """
    con = _con(casa)
    with con:
        _municipio(con)
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "MARIA", sexo="Feminino",
               naturalidade_cidade="Cidade Exemplo", naturalidade_uf="MA")
        _pessoa(con, aid, "PAI", "JOSÉ", sexo="Masculino")
        _pessoa(con, aid, "MAE", "ANA", sexo="Feminino")
    r = CRC.montar(con, [aid], cns=CNS)
    assert r["quantos"] == 1 and r["retidos"] == [] and r["a_arrumar"] == []
    assert r["xml"].count("<FILIACAONASCIMENTO>") == 2


def test_filiacao_sem_naturalidade_emite_nao_consta_e_nunca_undefined(casa, xsd):
    """Relato: CRC mostra «Município: undefined / UF: undefined» na filiação
    quando naturalidade_cidade/uf estão vazios — Valter de Sousa Monteiro /
    Hilda da Silva Lima, assento 1239.

    Omitir as duas tags (CODIGOIBGE e TEXTOLIVRE) passa no XSD (`minOccurs=0`)
    e a Central recusa: «não pode ser nulo e se TEXTOLIVREMUNICIPIONAT também
    for nulo». Óbito/casamento já emitem a tag. A filiação precisa de
    conteúdo; «não consta» é o sentinela de texto livre.
    """
    con = _con(casa)
    with con:
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "OSVALDO SOUSA MONTEIRO", sexo="M",
                naturalidade_cidade="Cidade Exemplo", naturalidade_uf="MA")
        _pessoa(con, aid, "PAI", "Valter de Sousa Monteiro", sexo="M")
        _pessoa(con, aid, "MAE", "Hilda da Silva Lima", sexo="F")
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert "undefined" not in xml
    assert xml.count("<FILIACAONASCIMENTO>") == 2
    assert xml.count("<TEXTOLIVREMUNICIPIONAT>não consta</TEXTOLIVREMUNICIPIONAT>") == 2
    assert _validar(xsd, xml) == []


def test_filiacao_com_undefined_no_campo_nao_repete_a_palavra(casa, xsd):
    """Se o campo chegar com a palavra JS gravada, ela não vai no XML."""
    con = _con(casa)
    with con:
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "MARIA", sexo="F")
        _pessoa(con, aid, "PAI", "JOSE", sexo="M",
                naturalidade_cidade="undefined", naturalidade_uf="undefined")
        _pessoa(con, aid, "MAE", "ANA", sexo="F",
                naturalidade_cidade="null", naturalidade_uf="")
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert "undefined" not in xml.lower()
    assert "<TEXTOLIVREMUNICIPIONAT>null</TEXTOLIVREMUNICIPIONAT>" not in xml
    assert xml.count("<TEXTOLIVREMUNICIPIONAT>não consta</TEXTOLIVREMUNICIPIONAT>") == 2
    assert _validar(xsd, xml) == []


def test_o_documento_so_sai_com_dono_e_tipo(casa):
    """«Os Documentos só são gravados se as tags DONO e TIPO_DOC estiverem
    preenchidas.»"""
    con = _con(casa)
    with con:
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "MARIA", sexo="F",
                documento_numero="123")             # sem tipo
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert "<DOCUMENTOS>" not in xml


def test_o_cpf_e_a_preferencia(casa):
    """«A preferência de envio é sempre pelo CPF» — a mesma regra desta casa, de
    que o documento vem antes do nome porque documento não tem homônimo."""
    con = _con(casa)
    with con:
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "MARIA", sexo="F",
                documento_tipo="CPF", documento_numero="000.000.001-91")
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert "<CPFREGISTRADO>00000000191</CPFREGISTRADO>" in xml


def test_o_texto_vai_escapado(casa):
    """E com o escape CERTO do XML, e não o do manual — a tabela dele, como sai
    do PDF, está invertida."""
    con = _con(casa)
    with con:
        aid = _nascimento(con, nome="MARIA & JOSÉ <SILVA>")
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert "&amp;" in xml
    assert "&lt;SILVA&gt;" in xml
    assert "<SILVA>" not in xml


def test_o_nome_que_o_conjuge_passou_a_usar_vai(casa):
    """É o motivo pelo qual a certidão de casamento existe — e medido, o segundo
    cônjuge muda de nome em 17 dos 20 casamentos."""
    con = _con(casa)
    with con:
        aid = _assento(con, especie="CASAMENTO", serie="RC_B",
                       nome="JOÃO e MARIA")
        _pessoa(con, aid, "NUBENTE1", "JOÃO DA SILVA", sexo="M")
        _pessoa(con, aid, "NUBENTE2", "MARIA SOUZA", sexo="F",
                nome_pos="MARIA SOUZA DA SILVA")
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert "<NOVONOMECONJUGE2>MARIA SOUZA DA SILVA</NOVONOMECONJUGE2>" in xml


# ------------------------------------------------ o defeito do primeiro ensaio


def test_coluna_vazia_nao_derruba_a_montagem(casa):
    """O DEFEITO QUE O PRIMEIRO ENSAIO CONTRA DADO REAL ACHOU. O padrão do `get`
    só vale quando a **chave falta** — numa linha de banco ela existe sempre, e
    o que vem é `None`. Chamar `.upper()` nisso estoura, e estourou em quatro
    lugares.

    Teste de domínio escrito à mão preenche tudo, e por isso passaria."""
    con = _con(casa)
    with con:
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "MARIA", sexo="F",
                documento_tipo=None, documento_numero=None)
    r = CRC.montar(con, [aid], cns=CNS)        # não pode estourar
    assert r["quantos"] == 1


# ------------------------------------------------ o módulo não envia


def test_o_modulo_nao_envia_nem_assina():
    """O modelo por web service exige o XML assinado com e-CPF e em Base64, e o
    certificado é do oficial. Ele monta e diz o que falta."""
    codigo = (RAIZ / "crc_carga.py").read_text(encoding="utf-8")
    for proibido in ("requests", "urllib", "base64", "socket"):
        assert proibido not in codigo, f"o módulo tenta enviar com {proibido}"
    publicos = [n for n in dir(CRC)
                if not n.startswith("_") and callable(getattr(CRC, n))]
    for nome in publicos:
        for proibido in ("enviar", "assinar", "transmitir"):
            assert proibido not in nome.lower(), f"`{nome}` faz o que não deve"


# ------------------------------------------------ a validação contra o XSD
#
# **O QUE ESTES TESTES GUARDAM.** Até 10/09/2026 o gerador nunca tinha sido
# conferido contra o XSD real, e todo assento **sem CPF do registrado**
# quebrava a validação — a maioria do acervo. `xmlschema.validate()` não
# aceita nem sequência errada nem enum fora da lista; testes de conteúdo
# (`"<TAG>valor</TAG>" in xml`) não pegam nenhum dos dois.


@pytest.fixture(scope="module")
def xsd():
    from lxml import etree
    return etree.XMLSchema(etree.parse(str(RAIZ / "schemas" /
                                            "cargaRegistrosCompleto.xsd")))


def _validar(xsd, xml: str) -> list[str]:
    from lxml import etree
    doc = etree.fromstring(xml.encode("utf-8"))
    ok = xsd.validate(doc)
    return [] if ok else [str(e) for e in xsd.error_log]


def test_nascimento_sem_cpf_e_sem_gemeo_valida_contra_o_xsd(casa, xsd):
    """**O DEFEITO QUE MAIS CUSTAVA**: sem CPF do registrado, `CPFREGISTRADO`
    nem saía, e o XSD exige a tag presente e vazia na sequência — a Central
    recusaria dizendo que `MATRICULA` «não era esperado ali»."""
    con = _con(casa)
    with con:
        aid = _nascimento(con)
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert _validar(xsd, xml) == []


def test_casamento_sem_cpf_dos_conjuges_valida_contra_o_xsd(casa, xsd):
    """Mesmo defeito, do lado do casamento: `CPFCONJUGE1`/`SEXOCONJUGE1` só
    saíam com dado, e o XSD os exige sempre presentes."""
    con = _con(casa)
    with con:
        aid = _assento(con, especie="CASAMENTO", nome="CASAL",
                       data_fato="2026-08-18", regime_bens="COMUNHAO_PARCIAL")
        _pessoa(con, aid, "NUBENTE1", "JOAO", sexo="M")
        _pessoa(con, aid, "NUBENTE2", "MARIA", sexo="F")
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert _validar(xsd, xml) == []


def test_obito_minimo_valida_contra_o_xsd(casa, xsd):
    """O óbito tem 78 tags no manual — a maioria sem coluna nesta casa —, e
    todas as obrigatórias têm de sair, mesmo vazias."""
    con = _con(casa)
    with con:
        aid = _assento(con, especie="OBITO", nome="FALECIDO",
                       data_fato="2026-08-18", cor_raca="BRANCA",
                       ibge_natureza_obito="1", ibge_local_obito="1")
        _pessoa(con, aid, "FALECIDO", "FALECIDO", sexo="M")
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert _validar(xsd, xml) == []




def test_crm_atestante_com_anotacao_entre_parenteses_cabe_no_xsd(casa, xsd):
    """**HOTFIX-2026-09-30-03**: `atestante_documento` com prosa livre
    ("CRM-MA 4603 (IML Imperatriz)", 28 chars) estourava `CRMATESTANTEPRIMARIO`
    (`maxLength=13`). O gerador tira a anotacao entre parenteses e limita a 13.
    """
    con = _con(casa)
    with con:
        aid = _assento(con, especie="OBITO", nome="FALECIDO CRM LONGO",
                       data_fato="2026-08-18", cor_raca="BRANCA",
                       obito_possui_bens="N",
                       ibge_natureza_obito="1", ibge_local_obito="1",
                       atestante="Jorge Fernando Chaves Rodrigues",
                       atestante_documento="CRM-MA 4603 (IML Imperatriz)")
        _pessoa(con, aid, "FALECIDO", "FALECIDO CRM LONGO", sexo="M")
    montado = CRC.montar(con, [aid], cns=CNS)
    assert montado["quantos"] == 1, f"retido: {montado['retidos']}"
    xml = montado["xml"]
    assert "<CRMATESTANTEPRIMARIO>CRM-MA 4603</CRMATESTANTEPRIMARIO>" in xml
    assert len("CRM-MA 4603") <= CRC.CRM_ATESTANTE_MAXLEN
    assert _validar(xsd, xml) == []


def test_crm_atestante_helper_corta_anotacao_e_respeita_maxlen():
    assert CRC._crm_atestante("CRM-MA 4603 (IML Imperatriz)") == "CRM-MA 4603"
    assert CRC._crm_atestante("CRM-MA 11290 (assistente)") == "CRM-MA 11290"
    assert CRC._crm_atestante("CRM 4123") == "CRM 4123"
    assert CRC._crm_atestante("") == ""
    assert len(CRC._crm_atestante("X" * 40)) == CRC.CRM_ATESTANTE_MAXLEN



def test_hora_normaliza_h_mm_para_hh_mm():
    """**HOTFIX-2026-09-30-04**: `2:18` (ficha) virava HORAOBITO invalida na CRC."""
    assert CRC._hora("2:18") == "02:18"
    assert CRC._hora("02:18") == "02:18"
    assert CRC._hora("14:30") == "14:30"
    assert CRC._hora("14:30:59") == "14:30"
    assert CRC._hora("14h30") == "14:30"
    assert CRC._hora("") == ""
    assert CRC._hora(None) == ""
    assert CRC._hora("24:00") == ""  # fora de 0..23 - nao inventar
    assert CRC._hora("19:68") == ""
    assert CRC._hora("abc") == ""


def test_horaobito_com_hora_sem_zero_a_esquerda_valida_xsd(casa, xsd):
    """Obito ALDERICO: hora_fato=2:18 deve sair como 02:18 e passar no XSD."""
    con = _con(casa)
    with con:
        aid = _assento(con, especie="OBITO", nome="TOMAS MACEDO CORREIRO",
                       data_fato="2026-09-20", cor_raca="PARDA",
                       hora_fato="2:18",
                       obito_possui_bens="S",
                       ibge_natureza_obito="1", ibge_local_obito="1",
                       atestante="Antonio Rubens",
                       atestante_documento="CRM-MA 11290")
        _pessoa(con, aid, "FALECIDO", "TOMAS MACEDO CORREIRO", sexo="M")
    montado = CRC.montar(con, [aid], cns=CNS)
    assert montado["quantos"] == 1, f"retido: {montado['retidos']}"
    xml = montado["xml"]
    assert "<HORAOBITO>02:18</HORAOBITO>" in xml
    assert "<HORAOBITO>2:18</HORAOBITO>" not in xml
    assert _validar(xsd, xml) == []

def test_registro_com_cpf_e_documento_do_genitor_valida_contra_o_xsd(casa, xsd):
    """O caminho OPOSTO do defeito original: com CPF preenchido, e um genitor
    com RG (o `<DOCUMENTOS>` do genitor, que só existe no nascimento e não
    tem `DONO=REGISTRADO` — só `FILIACAO_NASCIMENTO`)."""
    con = _con(casa)
    with con:
        aid = _assento(con, especie="NASCIMENTO", nome="COM DOCUMENTO")
        # CPF de verdade, e nao um qualquer: desde a correcao de 11/09/2026
        # (relato da CRC, "CPFPAI/CPFMAE e invalido") a carga so manda CPF
        # que passa no digito verificador.
        _pessoa(con, aid, "REGISTRADO", "COM DOCUMENTO", sexo="M",
               documento_tipo="CPF", documento_numero="11144477735")
        _pessoa(con, aid, "PAI", "PAI SEM CPF", sexo="M",
               documento_tipo="RG", documento_numero="1234567")
        _pessoa(con, aid, "MAE", "MAE", sexo="F")
    xml = CRC.montar(con, [aid], cns=CNS)["xml"]
    assert "<CPFREGISTRADO>11144477735</CPFREGISTRADO>" in xml
    assert "<DONO>FILIACAO_NASCIMENTO</DONO>" in xml
    assert _validar(xsd, xml) == []


# ------------------------------------------------ a IDADE da filiação


@pytest.mark.parametrize("bruto,esperado", [
    ("23", "23"), ("23 ANOS", "23"), (" 7 anos", "7"), ("100", "100"),
    ("1234", ""), ("IGNORADA", ""), ("", ""), (None, "")])
def test_a_idade_vai_so_com_o_numero(bruto, esperado):
    assert CRC._idade_crc(bruto) == esperado


def test_idade_digitada_com_texto_valida_contra_o_xsd(casa, xsd):
    """**A CRC RECUSOU A CARGA INTEIRA — 26/10/2026.** No assento 8443 a
    idade do pai estava «23 ANOS», e `IDADE` aceita até três caracteres:
    um genitor derrubava os dezesseis registros do arquivo."""
    con = _con(casa)
    with con:
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "MARIA", sexo="F")
        _pessoa(con, aid, "PAI", "JOSE EXEMPLO", sexo="M",
                idade_no_fato="23 ANOS")
        _pessoa(con, aid, "MAE", "ANA EXEMPLO", sexo="F", idade_no_fato="21")
    r = CRC.montar(con, [aid], cns=CNS)
    assert r["quantos"] == 1, r["retidos"]
    assert "<IDADE>23</IDADE>" in r["xml"]
    assert "<IDADE>21</IDADE>" in r["xml"]
    assert "ANOS</IDADE>" not in r["xml"]
    assert _validar(xsd, r["xml"]) == []


def test_idade_com_texto_avisa_para_corrigir_a_ficha(casa):
    con = _con(casa)
    with con:
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "MARIA", sexo="F")
        _pessoa(con, aid, "PAI", "JOSE EXEMPLO", sexo="M",
                idade_no_fato="23 ANOS")
        _pessoa(con, aid, "MAE", "ANA EXEMPLO", sexo="F", idade_no_fato="21")
    r = CRC.montar(con, [aid], cns=CNS)
    arrumar = " ".join(r["a_arrumar"][0]["arrumar"])
    assert "«23 ANOS»" in arrumar and "«23»" in arrumar
    assert "filiação 2 (pai)" in arrumar
    assert "mãe" not in arrumar     # a idade certa da mãe não gera aviso
