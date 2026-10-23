"""A remessa do SIRC — o prazo mais apertado do sistema inteiro.

O QUE ESTES TESTES GUARDAM
    **Que o teto de 250 registros é regra do arquivo, e não detalhe de
    transporte.** Estourar não faz a Dataprev aceitar 250 e recusar o resto: ela
    recusa **o arquivo inteiro**.

    **Que o limite de tamanho é em BYTES.** «JOSÉ» ocupa 5 bytes em UTF-8 e 4
    caracteres — e no Registro Civil quase todo nome tem acento. Medir por
    caractere deixaria passar arquivo que a Dataprev recusa.

    **Que a remessa leva as SETE coisas**, e não só os registros: o art. 225
    manda também as averbações, as anotações e as retificações — que moram em
    outra tabela.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — suite pesada + DROP TABLE
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_matricula as RCM                                       # noqa: E402
import sirc_remessa as SIRC                                      # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-20T09:00"


def _matricula(*, termo=19565, folha=166, livro=24, ano=2026):
    """Uma matrícula de nascimento válida, para os testes que precisam de uma
    de verdade — a partir da 13/09/2026 ela é OBRIGATÓRIA: os nove campos de
    `registroCivil` (acervo, anoRegistro, codServentia, dvMatricula, folha,
    numeroLivro, termo, tipoLivro, tipoServico) vêm todos dela."""
    return RCM.compor(cns="000000", ano=ano, livro_tipo="1", livro=livro,
                      folha=folha, termo=termo)


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


def _assento(con, *, especie="NASCIMENTO", nome="MARIA", numero=1,
             data_ato="2026-08-20", matricula=None, local=1):
    """`local` é o `ibge_local_nascimento` (1 = hospital): desde 06/10/2026
    o nascimento sem local fica retido — o SIRC o recusa."""
    if matricula is None:
        matricula = _matricula(termo=numero)
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em, matricula,
               ibge_local_nascimento)
           VALUES ('RC_A',?,?,?,?,?,'ATIVO','SISTEMA',?,?,?)""",
        (especie, numero, nome, data_ato, data_ato, AGORA, matricula,
         local if especie == "NASCIMENTO" else None))
    aid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm, sexo,
               criado_em) VALUES (?,'REGISTRADO',?,?,'F',?)""",
        (aid, nome, nome.lower(), AGORA))
    return aid


# ------------------------------------------------ a norma


def test_o_prazo_e_de_um_dia_util():
    """É o prazo mais curto do sistema inteiro — e cobre tudo."""
    assert SIRC.PRAZO_DIAS_UTEIS == 1
    assert SIRC.PRAZO_SEM_INTERNET_DIAS_UTEIS == 5
    assert SIRC.PRAZO_DA_INEXISTENCIA_DIAS_UTEIS == 5
    assert "art. 225" in SIRC.ARTIGO


def test_a_sancao_esta_escrita():
    """O § 4º pune o descumprimento **e a informação inexata** — mandar errado é
    pior que não mandar, e quem lê o módulo precisa saber disso."""
    assert "art. 92 da Lei nº 8.212/1991" in SIRC.SANCAO
    assert "ação regressiva" in SIRC.SANCAO


def test_o_sirc_recebe_sete_coisas():
    """A CRC recebe três; o SIRC recebe também averbação, anotação e
    retificação."""
    assert len(SIRC.O_QUE_VAI) == 7
    assert {"AVERBACAO", "ANOTACAO", "RETIFICACAO"} <= set(SIRC.ESPECIES)


def test_os_tres_atos_tem_regra_de_data_propria():
    """Seção 4.8 do manual, e cada um tem a sua."""
    assert set(SIRC.ATOS_COM_DATA) == {"ANOTACAO", "AVERBACAO", "RETIFICACAO"}
    for regra in SIRC.ATOS_COM_DATA.values():
        assert regra["texto_minimo"] == 10
        assert regra["texto_maximo"] == 1000


def test_o_regime_de_casamento_e_enumerado_aqui():
    """O SIRC enumera (medido no XSD, seção 8.3) — e o enum NÃO é o mesmo da
    CRC: ela tem `SEPARACAO_LEGAL_BENS`, que o SIRC não enumera. Por isso o
    de-para é próprio, e não o de `crc_carga.REGIME_CASAMENTO`."""
    assert SIRC.regime_casamento_sirc("Comunhão Parcial de Bens", "2020-01-01") \
        == "COMUNHAO_PARCIAL"
    assert SIRC.regime_casamento_sirc("Comunhão Universal de Bens", "2020-01-01") \
        == "COMUNHAO_UNIVERSAL"
    # Separação LEGAL (obrigatória) não tem enum próprio no SIRC — fica
    # indefinida de propósito, e não forçada para `SEPARACAO_BENS`.
    assert SIRC.regime_casamento_sirc(
        "Separação Obrigatória de Bens", "2020-01-01") == ""


# ------------------------------------------------ os limites do arquivo


def test_o_lote_tem_no_maximo_duzentos_e_cinquenta():
    """Estourar não faz a Dataprev aceitar 250 e recusar o resto: ela recusa o
    arquivo inteiro."""
    assert SIRC.MAXIMO_DE_REGISTROS == 250
    lotes = SIRC.em_lotes(list(range(600)))
    assert [len(x) for x in lotes] == [250, 250, 100]


def test_a_remessa_vazia_devolve_um_lote_vazio():
    """Mês sem movimento também se comunica (§ 3º) — e um lote vazio é o que
    carrega a declaração de inexistência."""
    assert SIRC.em_lotes([]) == [[]]


def test_o_lote_nao_pode_ser_de_zero():
    with pytest.raises(SIRC.SircError):
        SIRC.em_lotes([1, 2, 3], tamanho=0)


def test_o_limite_de_tamanho_e_em_bytes():
    """«JOSÉ» ocupa 5 bytes em UTF-8 e 4 caracteres — e no Registro Civil quase
    todo nome tem acento. Medir por caractere deixaria passar arquivo que a
    Dataprev recusa."""
    r = SIRC.cabe_no_arquivo("JOSÉ")
    assert r["bytes"] == 5
    assert len("JOSÉ") == 4
    assert r["cabe"]


def test_arquivo_grande_demais_nao_cabe():
    grande = "a" * (SIRC.MAXIMO_DE_BYTES + 1)
    r = SIRC.cabe_no_arquivo(grande)
    assert not r["cabe"]
    assert r["limite"] == 1024 * 1024


def test_o_intervalo_entre_envios_esta_declarado():
    """Um minuto — por isso o módulo devolve os lotes, e não os manda num laço
    apertado."""
    assert SIRC.INTERVALO_MINIMO_SEGUNDOS == 60


# ------------------------------------------------ o que vai


def test_a_lista_traz_os_assentos(casa):
    con = _con(casa)
    with con:
        _assento(con, nome="MARIA", numero=1)
        _assento(con, especie="OBITO", nome="ANTONIO", numero=2)
    lista = SIRC.pendentes_de_remessa(con)
    assert {x["nome"] for x in lista} == {"MARIA", "ANTONIO"}
    assert all(x["onde"] == "rc_assentos" for x in lista)


def test_a_lista_traz_tambem_os_tres_atos(casa):
    """O art. 225 manda a relação «das averbações, das anotações e das
    retificações» — e elas moram em `rc_atos`, não em `rc_assentos`.

    **`tipo` NÃO É MAIS «AVERBACAO»/«ANOTACAO»/«RETIFICACAO» — desde
    14/09/2026 é a ESPÉCIE do assento** (o manual manda reenviar o
    registro inteiro numa Alteração, e não um envelope de ato à parte); a
    lista de atos pendentes fica em `atos`, dentro do candidato."""
    con = _con(casa)
    with con:
        aid = _assento(con, nome="MARIA")
        for tipo in ("AVERBACAO", "ANOTACAO", "RETIFICACAO"):
            con.execute(
                """INSERT INTO rc_atos (assento_id, tipo, data_ato, criado_em)
                   VALUES (?,?,?,?)""", (aid, tipo, "2026-08-21", AGORA))
    lista = SIRC.pendentes_de_remessa(con)
    candidatos_com_ato = [x for x in lista if x.get("onde") == "rc_atos"]
    assert len(candidatos_com_ato) == 1  # os três atos, um assento, um candidato
    tipos_dos_atos = {a["tipo"] for a in candidatos_com_ato[0]["atos"]}
    assert tipos_dos_atos == {"AVERBACAO", "ANOTACAO", "RETIFICACAO"}
    assert candidatos_com_ato[0]["tipo"] == "NASCIMENTO"


def test_a_lista_vem_do_mais_antigo(casa):
    """O prazo é de um dia útil: o que está esperando há mais tempo já
    estourou."""
    con = _con(casa)
    with con:
        _assento(con, nome="NOVO", numero=1, data_ato="2026-08-20")
        _assento(con, nome="VELHO", numero=2, data_ato="2026-01-05")
    assert SIRC.pendentes_de_remessa(con)[0]["nome"] == "VELHO"


def test_a_falta_da_tabela_de_atos_nao_derruba_a_lista(casa):
    """Meia remessa é melhor que remessa nenhuma, e a falta fica visível."""
    con = _con(casa)
    with con:
        _assento(con, nome="MARIA")
    con.execute("DROP TABLE IF EXISTS rc_atos")
    lista = SIRC.pendentes_de_remessa(con)
    assert [x["nome"] for x in lista] == ["MARIA"]


# ------------------------------------------------ a conferência


def test_a_conferencia_vem_antes_do_arquivo():
    """O § 4º pune **o fornecimento de informação inexata** com a penalidade do
    art. 92 e ação regressiva. Mandar errado é pior que não mandar.

    **SEM ESPÉCIE (tipo vazio)**, de propósito: é o único jeito de exercitar
    a checagem de nome/data/matrícula isolada da retenção por espécie — hoje
    NENHUMA espécie está pronta para sair (ver `ESPECIES_PRONTAS_PARA_O_SIRC`
    e o achado de 13/09/2026 sobre o envelope errado)."""
    m = _matricula()
    assert SIRC.o_que_falta(
        None, {"nome": "MARIA", "data_ato": "2026-08-20",
               "matricula": m}) == []
    assert "a data do ato" in SIRC.o_que_falta(
        None, {"nome": "MARIA", "matricula": m})
    assert "o nome" in SIRC.o_que_falta(
        None, {"data_ato": "2026-08-20", "matricula": m})


def test_coluna_vazia_nao_derruba_a_conferencia():
    """O padrão do `get` só vale quando a chave falta — numa linha de banco ela
    existe sempre. `crc_carga` estourou assim em quatro lugares."""
    assert SIRC.o_que_falta(None, {"nome": None, "data_ato": None, "tipo": None})


def test_a_matricula_agora_e_obrigatoria():
    """**ACHADO EM 13/09/2026, medindo o XSD contra o que o módulo montava.**
    `registroCivil` — a base de qualquer registro — exige NOVE campos sem
    `minOccurs="0"`, e todos vêm da matrícula. Sem ela, a Central recusaria o
    arquivo por estrutura, não por conteúdo."""
    faltas = SIRC.o_que_falta(
        None, {"nome": "MARIA", "data_ato": "2026-08-20"})
    assert "a matrícula de 32 dígitos" in faltas


def test_nascimento_casamento_obito_e_natimorto_estao_prontos():
    """**NASCIMENTO, validado em 13/09/2026; CASAMENTO e ÓBITO, em
    14/09/2026 — os três contra o XSD de verdade, não só lendo o manual por
    cima.**

    O casamento validou **638 de 638** registros reais desta casa
    (`registroCasamento`, seção 8.3 do manual) — `filiacoesConjuge` com
    `minOccurs="2"`, `sexoConjuge` reaproveitando o mesmo enum do
    nascimento, e a ordem de `conjugeAbstrato` («documentosConjuge» e
    «filiacoesConjuge» ANTES de «nome», que vem antes de «sexo» — a mesma
    família de erro que o nascimento já tinha ensinado, um nível mais
    fundo).

    O óbito validou **398 de 398** — e achou o defeito irmão do do
    casamento, num campo sem par: `idade` não tem marcador de ignorado
    nenhum no XSD, e uma entrada especulativa de sessão anterior
    (`"idade": "idadeIgnorada"`) fazia **50 dos 398** falharem por elemento
    inesperado.

    **NATIMORTO não tem envelope próprio** — o manual (seção 5.4) diz que
    um natimorto se manda pela MESMA operação e pelo MESMO
    `registroObitoAbstrato` do óbito, só com `tipoLivro="5"` (que já vem da
    matrícula). Não há registro real desta serventia para validar em
    escala — zero natimortos em produção —, e por isso a garantia aqui é a
    letra do manual, e não uma medição contra 398 como o óbito teve.

    **OS TRÊS ATOS DA DIVISÃO TRIPARTITE TAMBÉM NÃO SÃO MAIS «TIPO»
    NENHUM** — desde 14/09/2026 eles viram Alteração da própria espécie
    (ver a seção «OS TRÊS ATOS», mais abaixo), e `o_que_falta` nunca mais
    recebe `tipo="AVERBACAO"` de verdade — só o teste explícito de baixo,
    que prova que uma espécie DE FATO desconhecida continua retida."""
    m = _matricula()
    for tipo in ("NASCIMENTO", "CASAMENTO", "CASAMENTO_RELIGIOSO", "OBITO",
                "NATIMORTO"):
        assert SIRC.o_que_falta(
            None, {"nome": "MARIA", "data_ato": "2026-08-20",
                   "tipo": tipo, "matricula": m}) == [], tipo


def test_especie_de_verdade_desconhecida_continua_retida():
    """Um `tipo` que não é nenhuma espécie do SIRC — e não mais «AVERBACAO»/
    «ANOTACAO»/«RETIFICACAO», que deixaram de chegar aqui como tipo."""
    faltas = SIRC.o_que_falta(
        None, {"nome": "MARIA", "data_ato": "2026-08-20", "tipo": "XPTO"})
    assert any("ainda não foi construído" in f for f in faltas)


# ------------------------------------------------ o módulo não envia


def test_o_modulo_nao_fala_com_rede_nenhuma():
    """**QUEM FALA COM A CENTRAL É `sirc_cliente.py`, NUNCA ESTE MÓDULO.**

    Até 14/09/2026 este teste também recusava `import gzip` — porque até
    então compactar só fazia sentido para enviar, e este módulo não
    envia. **Isso deixou de ser verdade no mesmo dia, e por um motivo
    honesto**: o SIRC-Web (upload manual, para quando a API não responde
    ou a credencial ainda não foi liberada) exige o arquivo comprimido e
    cifrado (`.mrc`, seção 3 do manual) — `arquivo_mrc()` monta esse
    pacote, mas **não fala com rede nenhuma**: devolve bytes, para quem
    chamar decidir o que fazer com eles.

    **A GUARDA DE VERDADE CONTINUA A MESMA**: nenhum import de
    rede (`requests`/`urllib`/`socket`), e nenhuma função pública com nome
    de quem transmite (`enviar`, `transmitir`, `assinar`) — só de quem
    monta e empacota.
    """
    codigo = (RAIZ / "sirc_remessa.py").read_text(encoding="utf-8")
    for proibido in ("import requests", "import urllib", "import socket"):
        assert proibido not in codigo, f"o módulo tenta falar com rede: «{proibido}»"
    publicos = [n for n in dir(SIRC)
                if not n.startswith("_") and callable(getattr(SIRC, n))]
    for nome in publicos:
        for proibido in ("enviar", "transmitir", "assinar"):
            assert proibido not in nome.lower(), f"`{nome}` faz o que não deve"


# ------------------------------------------------ o marcador de ignorado


def test_campo_cheio_sai_com_o_valor():
    assert SIRC.campo("nome", "MARIA") == "<nome>MARIA</nome>"


def test_campo_vazio_sai_com_o_marcador():
    """É AQUI QUE ESTE ENVELOPE SE SEPARA DO DA CRC. Lá, tag em branco já quer
    dizer «nulo ou Ignorado(a)»; aqui, tag vazia é campo mal preenchido."""
    assert SIRC.campo("nome", None) == "<nomeIgnorado>true</nomeIgnorado>"
    assert SIRC.campo("cpf", "") == "<cpfIgnorado>true</cpfIgnorado>"


def test_o_marcador_concorda_em_genero():
    """**NÃO SE CALCULA COLANDO «Ignorado» NO FIM.** O nome do marcador concorda
    com o substantivo do campo, e uma função que colasse o sufixo acertaria uns e
    erraria os outros — calada, porque o XML continua bem formado."""
    assert SIRC.MARCADOR_IGNORADO["nome"] == "nomeIgnorado"
    assert SIRC.MARCADOR_IGNORADO["dataNascimento"] == "dataNascimentoIgnorada"
    assert SIRC.MARCADOR_IGNORADO["hora" + "Nascimento"] == \
        "horaNascimentoIgnorada"
    assert SIRC.MARCADOR_IGNORADO["sexo"] == "sexoIgnorado"
    # E há campo cujo nome termina em «a» e o marcador é masculino, e vice-versa
    # — que é o que impede a regra mecânica.
    assert SIRC.MARCADOR_IGNORADO["documentos"] == "documentosIgnorado"
    assert SIRC.MARCADOR_IGNORADO["corPele"] == "corPeleIgnorada"
    # `idade` NÃO tem marcador — é `minOccurs="0"` sozinho no XSD do óbito.
    assert "idade" not in SIRC.MARCADOR_IGNORADO


def test_a_conferencia_pega_valor_e_marcador_juntos():
    """A REGRA TEM DOIS LADOS, E O SEGUNDO É O QUE ESCAPA. Faltar o marcador quem
    monta percebe; sobrar o marcador ao lado do campo cheio ninguém percebe."""
    ruim = "<nome>MARIA</nome><nomeIgnorado>true</nomeIgnorado>"
    achados = SIRC.conferir_marcadores(ruim)
    assert len(achados) == 1
    assert "não pode estar informado" in achados[0]


def test_a_conferencia_nao_grita_no_arquivo_certo():
    """Alarme que soa sempre é alarme que ninguém ouve."""
    assert SIRC.conferir_marcadores("<nome>MARIA</nome>") == []
    assert SIRC.conferir_marcadores("<nomeIgnorado>true</nomeIgnorado>") == []


def test_o_marcador_nao_se_confunde_com_o_campo():
    """`<nome>` não pode casar com `<nomeIgnorado>` — o `>` vem colado ao nome."""
    assert SIRC.conferir_marcadores(
        "<codigoIBGEUFNaturalidade>21</codigoIBGEUFNaturalidade>"
        "<codigoIBGEUFIgnorado>true</codigoIBGEUFIgnorado>") == []


def test_a_filiacao_nao_se_confunde_com_o_registrado():
    """O nome do REGISTRADO preenchido e o nome do PAI marcado como ignorado
    são a mesma tag (`nome`/`nomeIgnorado`) em dois lugares do XSD — o
    registro e dentro de cada `filiacoesNascimento`. Não são o mesmo campo, e
    a conferência não pode confundi-los."""
    xml = ("<registro><nome>PESSOA</nome>"
          "<filiacoesNascimento><nomeIgnorado>true</nomeIgnorado>"
          "</filiacoesNascimento></registro>")
    assert SIRC.conferir_marcadores(xml) == []


def test_mas_dentro_da_mesma_filiacao_a_regra_vale():
    """Dentro do MESMO bloco de filiação, campo cheio e marcador juntos
    continuam sendo o defeito que a regra existe para pegar."""
    xml = ("<filiacoesNascimento><nome>JOÃO</nome>"
          "<nomeIgnorado>true</nomeIgnorado></filiacoesNascimento>")
    assert len(SIRC.conferir_marcadores(xml)) == 1


# ------------------------------------------------ a data e o vocabulário


def test_a_data_vai_em_dia_mes_ano():
    """O banco guarda `aaaa-mm-dd` e o SIRC quer o contrário. Mandar o ISO produz
    arquivo bem formado que a Dataprev recusa — inteiro, e não a linha."""
    assert SIRC.data_do_sirc("2026-08-20") == "20/08/2026"
    assert SIRC.FORMATO_DA_DATA == "dd/mm/aaaa"


def test_data_ilegivel_volta_vazia_e_vira_ignorado():
    """Inventar um dia para uma data ilegível seria afirmar ao INSS uma coisa que
    ninguém sabe."""
    assert SIRC.data_do_sirc(None) == ""
    assert SIRC.data_do_sirc("20/08/2026") == ""
    assert SIRC.data_do_sirc("aaaa-mm-dd") == ""
    assert SIRC.campo("dataNascimento", SIRC.data_do_sirc(None)) == \
        "<dataNascimentoIgnorada>true</dataNascimentoIgnorada>"


def test_o_sexo_nao_e_o_da_crc():
    """A CRC escreve `M`, `F` e `I`; o SIRC escreve a palavra inteira e tem três
    valores que a CRC não tem. Usar um pelo outro produz arquivo bem formado que
    a Dataprev recusa."""
    assert SIRC.SEXO["M"] == "MASCULINO"
    assert SIRC.SEXO["F"] == "FEMININO"
    assert "NAO_BINARIO" in SIRC.SEXO.values()
    assert "I" not in SIRC.SEXO


def test_o_zero_nao_some():
    """`str(v or "")` come o `0` junto com o `None`, e aqui isso não é estilo: um
    zero vira «não sei», que é afirmação diferente de «zero»."""
    assert SIRC._texto(0) == "0"
    assert SIRC._texto(None) == ""


# ------------------------------------------------ montar
#
# **SEM `tipo` DE PROPÓSITO, NOS TESTES DAQUI PARA BAIXO.** Desde 13/09/2026
# nenhuma espécie tem envelope pronto (`ESPECIES_PRONTAS_PARA_O_SIRC` está
# vazia), e um registro COM `tipo` sempre fica retido — o que é o
# comportamento certo, coberto em `test_nenhuma_especie_esta_pronta_ainda`.
# Estes testes exercitam `_registro()`/`montar()` em si (a base da matrícula,
# as filiações, o DNV, os lotes) por fora dessa retenção por espécie, que é
# uma segunda coisa: um registro sem espécie declarada só passa pela
# checagem de nome/data/matrícula, que continua valendo para qualquer um.


def _registro_pronto(i):
    return {"nome": f"PESSOA {i}", "data_ato": "2026-08-20",
            "matricula": _matricula(termo=i + 1)}


def test_montar_parte_em_lotes_e_conta():
    registros = [_registro_pronto(i) for i in range(600)]
    r = SIRC.montar(None, registros, cns="000000", competencia="2026-08")
    assert r["quantos"] == 600
    assert [x["quantos"] for x in r["lotes"]] == [250, 250, 100]
    assert all(x["cabe"] for x in r["lotes"])


def test_montar_retem_o_incompleto_com_o_motivo():
    """O § 4º pune o fornecimento de informação inexata com ação regressiva do
    INSS. Mandar errado é pior que não mandar — e o retido não some."""
    r = SIRC.montar(None,
                    [_registro_pronto(1),
                     {"nome": None, "data_ato": None, "tipo": "NASCIMENTO"}],
                    cns="000000")
    assert r["quantos"] == 1
    assert len(r["retidos"]) == 1
    assert "o nome" in r["retidos"][0]["faltas"]


def test_o_envelope_e_o_movimentonascimentoto():
    """**`cns`, `competencia` e `quantidade` NÃO VÃO NO CORPO DO MOVIMENTO —
    achado em 13/09/2026.** O exemplo real do manual (seção 7.1) não traz
    nenhum dos três; a raiz é `movimentoNascimentoTO`, com
    `versaoLayoutNascimento` logo no início. O `cns`/`competencia` que este
    módulo montava antes eram um envelope inventado."""
    r = SIRC.montar(None, [_registro_pronto(1)],
                    cns="000000", competencia="2026-08")
    xml = r["lotes"][0]["xml"]
    assert xml.startswith(
        '<?xml version="1.0" encoding="utf-8"?><movimentoNascimentoTO>'
        "<versaoLayoutNascimento>5.0</versaoLayoutNascimento>")
    assert xml.endswith("</movimentoNascimentoTO>")
    assert xml.count("<registroNascimentoInclusao>") == 1
    assert "<cns>" not in xml
    assert "<competencia>" not in xml
    assert "<quantidade>" not in xml


def test_o_arquivo_montado_passa_na_propria_conferencia():
    """Se o montador da casa produzisse campo cheio com marcador, o conferidor
    teria de acusar — e é o próprio arquivo que se confere."""
    r = SIRC.montar(None, [_registro_pronto(1)], cns="000000")
    assert r["lotes"][0]["avisos"] == []


def test_o_acento_conta_no_tamanho_do_arquivo():
    """O limite é em bytes, e no Registro Civil quase todo nome tem acento."""
    com_registro = _registro_pronto(1)
    com_registro["nome"] = "JOSÉ"
    sem_registro = _registro_pronto(2)
    sem_registro["nome"] = "JOSE"
    com = SIRC.montar(None, [com_registro], cns="000000")["lotes"][0]["bytes"]
    sem = SIRC.montar(None, [sem_registro], cns="000000")["lotes"][0]["bytes"]
    assert com == sem + 1


def test_os_nove_campos_base_saem_da_matricula():
    """`registroCivil` — a base comum a qualquer registro — exige acervo,
    anoRegistro, codServentia, dvMatricula, folha, numeroLivro, termo,
    tipoLivro e tipoServico, nenhum com `minOccurs="0"`. Todos vêm da
    matrícula, sem uma segunda digitação."""
    r = SIRC.montar(None, [_registro_pronto(1)], cns="000000")
    xml = r["lotes"][0]["xml"]
    for tag in ("acervo", "anoRegistro", "codServentia", "dvMatricula",
                "folha", "numeroLivro", "termo", "tipoLivro", "tipoServico"):
        assert f"<{tag}>" in xml, f"faltou <{tag}>"


def test_as_duas_filiacoes_sempre_saem():
    """`filiacoesNascimento` tem `minOccurs=\"2\"` no XSD — o XSD conta
    elementos, e por isso saem sempre dois blocos, mesmo sem pai ou mãe
    identificados (aí com o marcador de ignorado)."""
    r = SIRC.montar(None, [_registro_pronto(1)], cns="000000")
    xml = r["lotes"][0]["xml"]
    assert xml.count("<filiacoesNascimento>") == 2


def test_dnv_com_mais_de_onze_caracteres_vira_inexistente():
    """`dnv` é `string11` no XSD — 11 caracteres, no máximo. Achado
    conferindo o primeiro lote real: o valor guardado às vezes vem com
    hífens (`30-94275444-3`, 13 caracteres) e estourava o limite."""
    registro = _registro_pronto(1)
    registro["dnv"] = "30-94275444-3"
    xml = SIRC.montar(None, [registro], cns="000000")["lotes"][0]["xml"]
    assert "<dnvInexistente>true</dnvInexistente>" in xml
    assert "<dnv>" not in xml


def test_dnv_curta_o_bastante_vai_no_arquivo():
    registro = _registro_pronto(1)
    registro["dnv"] = "12345678901"
    xml = SIRC.montar(None, [registro], cns="000000")["lotes"][0]["xml"]
    assert "<dnv>12345678901</dnv>" in xml


def test_hora_invalida_vira_ignorada():
    """`horaNascimento` tem padrão próprio no XSD — só 00:00 a 23:59 existem.
    Achado na carga do acervo em 14/09/2026: o .docx trouxe "24:00", "24:40"
    e "19:68" — hora e minuto que não existem, e o XSD recusaria o arquivo
    inteiro por causa disso."""
    for hora_ruim in ("24:00", "24:40", "19:68", "9:30", "abc"):
        registro = _registro_pronto(1)
        registro["hora_fato"] = hora_ruim
        xml = SIRC.montar(None, [registro], cns="000000")["lotes"][0]["xml"]
        assert "<horaNascimentoIgnorada>true</horaNascimentoIgnorada>" in xml, hora_ruim
        assert f"<horaNascimento>{hora_ruim}</horaNascimento>" not in xml, hora_ruim


def test_hora_valida_vai_no_arquivo():
    registro = _registro_pronto(1)
    registro["hora_fato"] = "23:59"
    xml = SIRC.montar(None, [registro], cns="000000")["lotes"][0]["xml"]
    assert "<horaNascimento>23:59</horaNascimento>" in xml


def test_conferencia_nao_confunde_registros_diferentes_no_mesmo_lote():
    """**ACHADO NA CARGA DO ACERVO EM 14/09/2026, com dado real em escala**:
    um lote de 250 registros tem gente com CPF conhecido e gente sem — e a
    primeira versão da conferência, que lia o XML do lote inteiro de uma
    vez, confundia o campo preenchido de UM registrado com o mesmo campo
    ignorado de OUTRO, no mesmo lote. É a mesma armadilha da filiação, uma
    escala acima: a mesma tag em registros DIFERENTES não é o mesmo campo."""
    com_cpf = _registro_pronto(1)
    com_cpf["nome"] = "COM CPF"
    com_cpf["cpf_registrado"] = "12345678901"
    sem_cpf = _registro_pronto(2)
    sem_cpf["nome"] = "SEM CPF"
    # ambos passam por `montar`, que os concatena no MESMO lote
    xml = SIRC.montar(None, [com_cpf, sem_cpf], cns="000000")["lotes"][0]["xml"]
    assert "<cpf>12345678901</cpf>" in xml
    assert "<cpfIgnorado>true</cpfIgnorado>" in xml
    assert SIRC.conferir_marcadores(xml) == []


# ------------------------------------------------ o CASAMENTO
#
# ENTROU EM 14/09/2026, validado contra **638 de 638** casamentos reais
# desta casa (`registroCasamento`, seção 8.3 do manual) — ver
# `DOCUMENTACAO/SIRC_CASAMENTO_MEDIDO.md` para o ensaio em escala.


def _matricula_casamento(*, termo=976, folha=4, livro=4, ano=2023):
    return RCM.compor(cns="000000", ano=ano, livro_tipo="2", livro=livro,
                      folha=folha, termo=termo)


def _assento_casamento(con, *, numero=1, nubente1="FULANO", nubente2="SICRANA",
                       matricula=None, com_filiacao=True):
    if matricula is None:
        matricula = _matricula_casamento(termo=numero)
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em, matricula, regime_bens)
           VALUES ('RC_B','CASAMENTO',?,?,?,?,'ATIVO','SISTEMA',?,?,?)""",
        (numero, f"{nubente1} e {nubente2}", AGORA[:10], AGORA[:10], AGORA,
         matricula, "Comunhão Parcial de Bens"))
    aid = int(cur.lastrowid)
    for papel, nome, sexo in (("NUBENTE1", nubente1, "M"),
                              ("NUBENTE2", nubente2, "F")):
        con.execute(
            """INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm,
                   sexo, criado_em) VALUES (?,?,?,?,?,?)""",
            (aid, papel, nome, nome.lower(), sexo, AGORA))
    if com_filiacao:
        for papel, nome, sexo in (
                ("MAE_NUBENTE1", "MAE DO PRIMEIRO", "F"),
                ("PAI_NUBENTE1", "PAI DO PRIMEIRO", "M"),
                ("MAE_NUBENTE2", "MAE DO SEGUNDO", "F"),
                ("PAI_NUBENTE2", "PAI DO SEGUNDO", "M")):
            con.execute(
                """INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm,
                       sexo, criado_em) VALUES (?,?,?,?,?,?)""",
                (aid, papel, nome, nome.lower(), sexo, AGORA))
    return aid


def test_casamento_esta_pronto_e_precisa_dos_dois_nomes():
    """`OBRIGATORIOS["CASAMENTO"]` do manual: `NOMECONJUGE1`, `NOMECONJUGE2`."""
    m = _matricula_casamento()
    assert SIRC.o_que_falta(
        None, {"nome": "A e B", "data_ato": "2026-08-20",
               "tipo": "CASAMENTO", "matricula": m}) == []


def test_casamento_sem_um_dos_conjuges_fica_retido(casa):
    """Sem `con`, `o_que_falta` não pode checar os nomes de `pessoas` — a
    checagem exige o banco, porque os nomes moram em `rc_pessoas`."""
    con = _con(casa)
    aid = _assento_casamento(con, numero=1)
    con.execute("DELETE FROM rc_pessoas WHERE assento_id=? AND papel='NUBENTE2'",
                (aid,))
    con.commit()
    registro = {"assento_id": aid, "nome": "X e Y", "data_ato": AGORA[:10],
               "tipo": "CASAMENTO", "matricula": _matricula_casamento()}
    faltas = SIRC.o_que_falta(con, registro)
    assert any("segundo cônjuge" in f for f in faltas)


def test_o_registro_de_casamento_valida_contra_o_xsd_real(casa):
    """**A prova de verdade**: monta o registro com dado real do banco e
    confere estrutura (as duas filiações, a ordem do `<conjuge>`, o CPF
    dentro de `documentosConjuge`)."""
    con = _con(casa)
    aid = _assento_casamento(con, numero=2)
    con.commit()
    registro = dict(con.execute(
        "SELECT id, id assento_id, especie tipo, numero, nome, data_ato, "
        "data_fato, matricula, regime_bens FROM rc_assentos WHERE id=?",
        (aid,)).fetchone())
    assert SIRC.o_que_falta(con, registro) == []
    xml = SIRC._registro_casamento(con, registro)
    assert xml.startswith("<registroCasamentoInclusao>")
    assert xml.count("<conjuge1>") == 1 and xml.count("<conjuge2>") == 1
    assert xml.count("<filiacoesConjuge>") == 4, "duas filiações por cônjuge"
    assert "<regimeCasamento>COMUNHAO_PARCIAL</regimeCasamento>" in xml
    # A ordem dentro do `<conjuge>`: documentos/filiações vêm ANTES do nome.
    c1 = xml.split("<conjuge1>")[1].split("</conjuge1>")[0]
    assert c1.index("filiacoesConjuge") < c1.index("<nome>")
    assert SIRC.conferir_marcadores(xml) == []


def test_o_casamento_nao_confunde_o_sexo_do_conjuge_com_o_da_filiacao(casa):
    """A MESMA tag `sexo`/`sexoIgnorado` existe no cônjuge e em cada
    filiação dele — a conferência recursiva não pode confundir os níveis."""
    con = _con(casa)
    aid = _assento_casamento(con, numero=3)
    # Sexo do NUBENTE2 fica sem valor; o das filiações continua preenchido.
    con.execute("UPDATE rc_pessoas SET sexo=NULL WHERE assento_id=? AND papel='NUBENTE2'",
               (aid,))
    con.commit()
    registro = dict(con.execute(
        "SELECT id, id assento_id, especie tipo, numero, nome, data_ato, "
        "data_fato, matricula, regime_bens FROM rc_assentos WHERE id=?",
        (aid,)).fetchone())
    xml = SIRC._registro_casamento(con, registro)
    assert "<sexoIgnorado>true</sexoIgnorado>" in xml  # do NUBENTE2
    assert xml.count("<sexo>FEMININO</sexo>") >= 1     # das filiações
    assert SIRC.conferir_marcadores(xml) == [], (
        "confundiu o sexo ignorado do cônjuge com o preenchido da filiação")


def test_montar_agrupa_nascimento_e_casamento_em_arquivos_separados(casa):
    """**Cada espécie vai num arquivo próprio, nunca misturada** — os três
    exemplos do manual (seção 7) mostram sempre um elemento-raiz por
    arquivo, e o WSDL público declara operações SEPARADAS
    (`enviarMovimentoNascimento`, `enviarMovimentoCasamento`)."""
    con = _con(casa)
    n_id = _assento(con, especie="NASCIMENTO", nome="BEBE", numero=101)
    c_id = _assento_casamento(con, numero=102)
    con.commit()
    registros = [
        dict(con.execute(
            "SELECT id, id assento_id, especie tipo, numero, nome, data_ato, "
            "data_fato, matricula, hora_fato, dnv, cpf_registrado, regime_bens "
            "FROM rc_assentos WHERE id=?", (n_id,)).fetchone()),
        dict(con.execute(
            "SELECT id, id assento_id, especie tipo, numero, nome, data_ato, "
            "data_fato, matricula, hora_fato, dnv, cpf_registrado, regime_bens "
            "FROM rc_assentos WHERE id=?", (c_id,)).fetchone()),
    ]
    r = SIRC.montar(con, registros, cns="000000")
    assert not r["retidos"]
    assert len(r["lotes"]) == 2
    especies = {l["especie"] for l in r["lotes"]}
    assert especies == {"NASCIMENTO", "CASAMENTO"}
    for lote in r["lotes"]:
        tem_nasc = "movimentoNascimentoTO" in lote["xml"]
        tem_cas = "movimentoCasamentoTO" in lote["xml"]
        assert tem_nasc != tem_cas, "um lote não pode ter as duas raízes"


# ------------------------------------------------ o ÓBITO
#
# ENTROU EM 14/09/2026, validado contra **398 de 398** óbitos reais desta
# casa (`registroObito`, seção do manual) — e achou um defeito num campo
# sem marcador nenhum (`idade`), que a validação do casamento não tinha
# como revelar.


def _assento_obito(con, *, numero=1, falecido="FULANO DE TAL",
                   declarante="BELTRANO DECLARANTE", com_filiacao=True,
                   matricula=None):
    if matricula is None:
        matricula = _matricula(termo=numero)
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em, matricula, hora_fato,
               cor_raca, ibge_local_obito, ibge_natureza_obito,
               local_sepultamento, local_fato_nome, local_fato_endereco,
               causa_morte)
           VALUES ('RC_A','OBITO',?,?,?,?,'ATIVO','SISTEMA',?,?,'10:20',
                   'PARDA',3,1,'Cemitério Municipal','Residência',
                   'Rua Tal, 123','Parada cardiorrespiratória')""",
        (numero, falecido, AGORA[:10], AGORA[:10], AGORA, matricula))
    aid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm, sexo,
               estado_civil, idade_no_fato, criado_em)
           VALUES (?,'FALECIDO',?,?,'M','CASADO',72,?)""",
        (aid, falecido, falecido.lower(), AGORA))
    con.execute(
        """INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm,
               criado_em) VALUES (?,'DECLARANTE',?,?,?)""",
        (aid, declarante, declarante.lower(), AGORA))
    if com_filiacao:
        for papel, nome, sexo in (("PAI", "PAI DO FALECIDO", "M"),
                                  ("MAE", "MAE DO FALECIDO", "F")):
            con.execute(
                """INSERT INTO rc_pessoas (assento_id, papel, nome,
                       nome_norm, sexo, criado_em)
                   VALUES (?,?,?,?,?,?)""",
                (aid, papel, nome, nome.lower(), sexo, AGORA))
    return aid


def _registro_obito(con, aid):
    return dict(con.execute(
        "SELECT id, id assento_id, especie tipo, numero, nome, data_ato, "
        "data_fato, matricula, hora_fato, cor_raca, ibge_local_obito, "
        "ibge_natureza_obito, local_sepultamento, local_fato_nome, "
        "local_fato_endereco, causa_morte FROM rc_assentos WHERE id=?",
        (aid,)).fetchone())


def test_obito_esta_pronto_e_precisa_do_nome_do_falecido():
    m = _matricula()
    assert SIRC.o_que_falta(
        None, {"nome": "FULANO", "data_ato": "2026-08-20",
               "tipo": "OBITO", "matricula": m}) == []


def test_obito_sem_falecido_fica_retido(casa):
    """Sem `con`, `o_que_falta` não pode checar o nome do FALECIDO — ele
    mora em `rc_pessoas`, e não no assento."""
    con = _con(casa)
    aid = _assento_obito(con, numero=1)
    con.execute("DELETE FROM rc_pessoas WHERE assento_id=? AND papel='FALECIDO'",
               (aid,))
    con.commit()
    registro = {"assento_id": aid, "nome": "X", "data_ato": AGORA[:10],
               "tipo": "OBITO", "matricula": _matricula(termo=1)}
    faltas = SIRC.o_que_falta(con, registro)
    assert any("falecido" in f for f in faltas)


def test_o_registro_de_obito_valida_contra_o_xsd_real(casa):
    """A prova de verdade: as duas filiações, o vocabulário próprio de
    `corPele`/`estadoCivil`/`tipoLocalObito`/`tipoMorte`, e `idade` sem
    marcador de ignorado nenhum."""
    con = _con(casa)
    aid = _assento_obito(con, numero=2)
    con.commit()
    registro = _registro_obito(con, aid)
    assert SIRC.o_que_falta(con, registro) == []
    xml = SIRC._registro_obito(con, registro)
    assert xml.startswith("<registroObitoInclusao>")
    assert xml.count("<filiacoesObito>") == 2
    assert "<corPele>PARDA</corPele>" in xml
    assert "<estadoCivil>CASADO</estadoCivil>" in xml
    assert "<tipoLocalObito>DOMICILIO</tipoLocalObito>" in xml
    assert "<tipoMorte>NATURAL</tipoMorte>" in xml
    assert "<idade>72</idade>" in xml
    # A MARCA INTEIRA, e não a palavra: desde 09/10/2026 o óbito leva
    # `<nacionalidadeIgnorada>`, que CONTÉM «idadeIgnorada».
    assert "<idadeIgnorada>" not in xml
    assert SIRC.conferir_marcadores(xml) == []


def test_obito_sem_idade_nao_inventa_marcador(casa):
    """**O DEFEITO REAL, MEDIDO EM PRODUÇÃO**: `idade` não tem par de
    ignorado no XSD do óbito — sem valor, ela some do XML, e não vira
    `idadeIgnorada`, que a Central recusaria por elemento inesperado."""
    con = _con(casa)
    aid = _assento_obito(con, numero=3)
    con.execute("UPDATE rc_pessoas SET idade_no_fato=NULL "
               "WHERE assento_id=? AND papel='FALECIDO'", (aid,))
    con.commit()
    registro = _registro_obito(con, aid)
    xml = SIRC._registro_obito(con, registro)
    assert "<idade>" not in xml
    # A MARCA INTEIRA, e não a palavra: desde 09/10/2026 o óbito leva
    # `<nacionalidadeIgnorada>`, que CONTÉM «idadeIgnorada».
    assert "<idadeIgnorada>" not in xml


def test_o_obito_nao_confunde_o_sexo_do_falecido_com_o_da_filiacao(casa):
    """`sexo`/`sexoIgnorado` aparece no FALECIDO e em cada `filiacoesObito`
    — a mesma armadilha do casamento, um nível abaixo."""
    con = _con(casa)
    aid = _assento_obito(con, numero=4)
    con.execute("UPDATE rc_pessoas SET sexo=NULL WHERE assento_id=? AND "
               "papel='FALECIDO'", (aid,))
    con.commit()
    registro = _registro_obito(con, aid)
    xml = SIRC._registro_obito(con, registro)
    assert "<sexoIgnorado>true</sexoIgnorado>" in xml   # do FALECIDO
    assert xml.count("<sexo>") >= 1                     # das filiações
    assert SIRC.conferir_marcadores(xml) == []


def test_o_nome_do_falecido_e_seu_marcador_nao_ficam_juntos_no_xsd(casa):
    """**ACHADO SÓ NO EXEMPLO REAL DO MANUAL** — `nome`/`nomeEspecial` do
    falecido vêm logo depois de `nacionalidadeIgnorada`, e `nomeIgnorado`
    só aparece bem mais adiante na sequência, perto de `nomeLocalObito`.
    Por isso este módulo não usa `campo()` para o nome do falecido."""
    con = _con(casa)
    aid = _assento_obito(con, numero=5)
    con.commit()
    registro = _registro_obito(con, aid)
    xml = SIRC._registro_obito(con, registro)
    assert xml.index("<nome>") < xml.index("nomeLocalObito")
    assert "<nomeIgnorado>" not in xml  # o nome existe; o marcador não sai


def test_montar_agrupa_obito_no_proprio_envelope(casa):
    con = _con(casa)
    aid = _assento_obito(con, numero=6)
    con.commit()
    r = SIRC.montar(con, [_registro_obito(con, aid)], cns="000000")
    assert not r["retidos"]
    assert len(r["lotes"]) == 1
    assert r["lotes"][0]["especie"] == "OBITO"
    assert "movimentoObitoTO" in r["lotes"][0]["xml"]


# ------------------------------------------------ o NATIMORTO
#
# ENTROU EM 14/09/2026, e não com envelope próprio: o manual (seção 5.4)
# diz que um natimorto se manda pela MESMA operação e pelo MESMO
# `registroObitoAbstrato` do óbito — só muda o `tipoLivro`, que já vem da
# matrícula (`"5"`). **Não há registro real desta serventia para validar
# em escala** — zero natimortos em produção —, e por isso não há aqui um
# «398 de 398»: a garantia é a letra do manual.


def _matricula_natimorto(*, termo=1, folha=1, livro=1, ano=2026):
    return RCM.compor(cns="000000", ano=ano, livro_tipo="5", livro=livro,
                      folha=folha, termo=termo)


def _assento_natimorto(con, *, numero=1, nome="NATIMORTO DE TAL",
                       matricula=None):
    """Mesma forma de `_assento_obito`, mas com o papel `REGISTRADO` — é
    assim que `rc_assento.PAPEIS_DA_ESPECIE["NATIMORTO"]` chama o
    principal, ao contrário de `FALECIDO` no óbito."""
    if matricula is None:
        matricula = _matricula_natimorto(termo=numero)
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em, matricula)
           VALUES ('RC_C_AUXILIAR','NATIMORTO',?,?,?,?,'ATIVO','SISTEMA',?,?)""",
        (numero, nome, AGORA[:10], AGORA[:10], AGORA, matricula))
    aid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm, sexo,
               criado_em) VALUES (?,'REGISTRADO',?,?,'M',?)""",
        (aid, nome, nome.lower(), AGORA))
    return aid


def test_natimorto_usa_o_papel_registrado_e_nao_falecido(casa):
    con = _con(casa)
    aid = _assento_natimorto(con, numero=1)
    con.commit()
    registro = _registro_obito(con, aid)
    assert SIRC.o_que_falta(con, registro) == []
    xml = SIRC._registro_obito(con, registro)
    assert "<nome>NATIMORTO DE TAL</nome>" in xml
    assert "<tipoLivro>5</tipoLivro>" in xml
    assert SIRC.conferir_marcadores(xml) == []


def test_natimorto_sem_nome_fica_retido(casa):
    con = _con(casa)
    aid = _assento_natimorto(con, numero=2)
    con.execute("DELETE FROM rc_pessoas WHERE assento_id=? AND papel='REGISTRADO'",
               (aid,))
    con.commit()
    registro = _registro_obito(con, aid)
    faltas = SIRC.o_que_falta(con, registro)
    assert any("natimorto" in f for f in faltas)


def test_montar_agrupa_natimorto_no_envelope_do_obito(casa):
    """O `especie` do lote continua «NATIMORTO» (para o retido/pendente
    saber de onde veio), mas a RAIZ do XML é a do óbito — não há
    `movimentoNatimortoTO` no contrato."""
    con = _con(casa)
    aid = _assento_natimorto(con, numero=3)
    con.commit()
    r = SIRC.montar(con, [_registro_obito(con, aid)], cns="000000")
    assert not r["retidos"]
    assert len(r["lotes"]) == 1
    assert r["lotes"][0]["especie"] == "NATIMORTO"
    assert "movimentoObitoTO" in r["lotes"][0]["xml"]
    assert "registroObitoInclusao" in r["lotes"][0]["xml"]


# ------------------------------------------------ OS TRÊS ATOS (averbação/
# anotação/retificação) — 14/09/2026
#
# **NÃO HÁ ENVELOPE PRÓPRIO**: o manual (seção 6.1) manda reenviar TODO o
# registro dentro de `registroXAlteracao`, com o bloco do ato embutido.
# Validado contra o ÚNICO caso real desta serventia que não veio do acervo
# (assento 1231, «Determinação do oficial…», motivo OUTROS) — ver
# `DOCUMENTACAO/SIRC_A_REMESSA_CONSTRUIDA.md`.


def _ato(con, assento_id, *, tipo="AVERBACAO", data_ato="2026-09-01",
        fundamento="art. 347 do Código de Normas do TJMA"):
    cur = con.execute(
        """INSERT INTO rc_atos (assento_id, tipo, data_ato, fundamento,
               criado_em) VALUES (?,?,?,?,?)""",
        (assento_id, tipo, data_ato, fundamento, AGORA))
    return int(cur.lastrowid)


def test_um_ato_pendente_vira_alteracao_do_registro(casa):
    con = _con(casa)
    aid = _assento(con, nome="MARIA", numero=1)
    _ato(con, aid)
    con.commit()
    pendentes = SIRC.pendentes_de_remessa(con)
    alteracoes = [p for p in pendentes if p.get("atos")]
    assert len(alteracoes) == 1
    candidato = alteracoes[0]
    assert candidato["tipo"] == "NASCIMENTO"  # e não «AVERBACAO»
    assert len(candidato["atos"]) == 1
    xml = SIRC._registro(con, candidato)
    assert xml.startswith("<registroNascimentoAlteracao>")
    assert "<averbacoesNascimento>" in xml
    assert "<motivoAverbacao>ANOTACAO_CPF</motivoAverbacao>" in xml
    assert SIRC.conferir_marcadores(xml) == []


def test_duas_averbacoes_no_mesmo_assento_vao_juntas(casa):
    """**A RAZÃO DE AGRUPAR POR ASSENTO**: o manual diz que campo ausente
    numa Alteração vira NULL — mandar duas Alterações separadas apagaria a
    primeira averbação ao enviar a segunda."""
    con = _con(casa)
    aid = _assento(con, nome="MARIA", numero=2)
    _ato(con, aid, data_ato="2026-09-01",
        fundamento="art. 347 do Código de Normas do TJMA")
    _ato(con, aid, data_ato="2026-09-05",
        fundamento="Determinação judicial de outro motivo qualquer")
    con.commit()
    pendentes = SIRC.pendentes_de_remessa(con)
    alteracoes = [p for p in pendentes if p.get("atos")]
    assert len(alteracoes) == 1
    xml = SIRC._registro(con, alteracoes[0])
    assert xml.count("<averbacoesNascimento>") == 2
    assert "<motivoAverbacao>ANOTACAO_CPF</motivoAverbacao>" in xml
    assert "<motivoAverbacao>OUTROS</motivoAverbacao>" in xml
    assert SIRC.conferir_marcadores(xml) == []


def test_motivo_nao_reconhecido_cai_em_outros_com_o_complemento(casa):
    """**O ÚNICO CASO REAL** que passa pelo filtro do acervo: «Determinação
    do oficial à lavratura no livro físico errado» não bate com nenhum
    motivo estruturado, e o manual reserva `OUTROS` — com o complemento —
    para exatamente isso."""
    con = _con(casa)
    aid = _assento(con, nome="MARIA", numero=3)
    _ato(con, aid, fundamento="Determinação do oficial à lavratura no "
                             "livro físico errado (A-1 em vez de A-24).")
    con.commit()
    pendentes = SIRC.pendentes_de_remessa(con)
    candidato = [p for p in pendentes if p.get("atos")][0]
    xml = SIRC._registro(con, candidato)
    assert "<motivoAverbacao>OUTROS</motivoAverbacao>" in xml
    assert "livro físico errado" in xml


def test_anotacao_e_retificacao_tambem_viram_alteracao(casa):
    """Zero anotações e retificações reais nesta serventia — a garantia
    aqui é a estrutura do XSD, não a medição contra dado real."""
    con = _con(casa)
    aid = _assento(con, nome="MARIA", numero=4)
    _ato(con, aid, tipo="ANOTACAO", fundamento="Nascimento de filho")
    _ato(con, aid, tipo="RETIFICACAO", fundamento="Correção de grafia")
    con.commit()
    pendentes = SIRC.pendentes_de_remessa(con)
    candidato = [p for p in pendentes if p.get("atos")][0]
    xml = SIRC._registro(con, candidato)
    assert "<anotacoesNascimento>" in xml
    assert "<retificacoesNascimento>" in xml
    assert "<motivoAnotacao>OUTROS</motivoAnotacao>" in xml
    assert SIRC.conferir_marcadores(xml) == []


def test_o_ato_sem_data_recusa_com_a_regra_do_manual(casa):
    """A regra de data da seção 4.8 — agora conferida DENTRO de `atos`, e
    não mais no `tipo` de fora (que passou a ser a espécie)."""
    con = _con(casa)
    aid = _assento(con, nome="MARIA", numero=5)
    con.execute(
        """INSERT INTO rc_atos (assento_id, tipo, data_ato, fundamento,
               criado_em) VALUES (?,'AVERBACAO','',?,?)""",
        (aid, "art. 347", AGORA))
    con.commit()
    pendentes = SIRC.pendentes_de_remessa(con)
    candidato = [p for p in pendentes if p.get("atos")][0]
    faltas = SIRC.o_que_falta(con, candidato)
    assert any("data da averbação" in f for f in faltas)


def test_casamento_e_obito_tambem_embutem_os_atos():
    """Mesma forma nas três espécies — `_TAG_DOS_ATOS` decide as tags."""
    m_cas = RCM.compor(cns="000000", ano=2026, livro_tipo="2", livro=4,
                       folha=4, termo=981)
    r_cas = {"tipo": "CASAMENTO", "nome": "A e B", "data_ato": "2026-08-20",
            "data_fato": "2026-08-18", "matricula": m_cas,
            "regime_bens": None,
            "atos": [{"tipo": "AVERBACAO", "data_ato": "2026-09-01",
                      "fundamento": "art. 347"}]}
    xml_cas = SIRC._registro_casamento(None, r_cas)
    assert xml_cas.startswith("<registroCasamentoAlteracao>")
    assert "<averbacoesCasamento>" in xml_cas

    m_ob = RCM.compor(cns="000000", ano=2026, livro_tipo="4", livro=9,
                      folha=1, termo=501)
    r_ob = {"tipo": "OBITO", "nome": "FULANO", "data_ato": "2026-08-20",
           "data_fato": "2026-08-18", "matricula": m_ob,
           "atos": [{"tipo": "RETIFICACAO", "data_ato": "2026-09-01",
                     "fundamento": "correção"}]}
    xml_ob = SIRC._registro_obito(None, r_ob)
    assert xml_ob.startswith("<registroObitoAlteracao>")
    assert "<retificacoesObito>" in xml_ob


def test_a_conferencia_de_marcadores_nao_confunde_alteracao_com_inclusao():
    """`\\1\\2` no regex de `conferir_marcadores` — sem ele, um lote misto
    (uma inclusão e uma alteração) casaria a abertura de uma com o fecho
    da outra."""
    inclusao = "<registroNascimentoInclusao><nome>A</nome></registroNascimentoInclusao>"
    alteracao = "<registroNascimentoAlteracao><nome>B</nome></registroNascimentoAlteracao>"
    assert SIRC.conferir_marcadores(inclusao + alteracao) == []


# ------------------------------------------------ o mês sem movimento


def test_o_mes_vazio_tambem_se_comunica():
    """§ 3º. É a obrigação que mais se esquece, porque não há trabalho que a
    lembre: não houve registro, não houve remessa, e ninguém repara na falta.

    **O ENVELOPE NÃO ERA `<movimento><cns>...<quantidade>`** — essa forma
    nunca existiu no manual. Achado em 14/09/2026 ao ler o XSD de verdade
    (`declaracaoInexistenciaMovimentoServicoTO`, seção 11): quatro
    booleanos independentes, e `competencia` em `MM/AAAA` — não `AAAA-MM`,
    que é só a forma que a tela usa por dentro.
    """
    xml = SIRC.declaracao_de_inexistencia(competencia="2026-07")
    assert "<competencia>7/2026</competencia>" in xml
    assert "<declaracaoInexistenciaMovimentoCasamento>true</declaracaoInexistenciaMovimentoCasamento>" in xml
    assert "<declaracaoInexistenciaMovimentoNascimento>true</declaracaoInexistenciaMovimentoNascimento>" in xml
    assert "<declaracaoInexistenciaMovimentoObito>true</declaracaoInexistenciaMovimentoObito>" in xml
    assert "<declaracaoInexistenciaMovimentoObitoNatimorto>true</declaracaoInexistenciaMovimentoObitoNatimorto>" in xml
    assert "<inexistenciaDeMovimento>" not in xml
    assert "<quantidade>" not in xml


def test_a_declaracao_aceita_um_mes_de_dois_digitos():
    """`competencia` no XSD é `M/AAAA` sem zero à esquerda — dezembro é «12»,
    mas janeiro é «1», e não «01»."""
    xml = SIRC.declaracao_de_inexistencia(competencia="2026-01")
    assert "<competencia>1/2026</competencia>" in xml
    xml = SIRC.declaracao_de_inexistencia(competencia="2026-12")
    assert "<competencia>12/2026</competencia>" in xml


def test_a_declaracao_pode_ser_so_de_algumas_especies():
    """O § 3º fala nas quatro juntas, mas um mês pode ter nascimento e não
    ter casamento — o parâmetro existe para esse dia."""
    xml = SIRC.declaracao_de_inexistencia(competencia="2026-07",
                                          especies=("Casamento",))
    assert "<declaracaoInexistenciaMovimentoCasamento>true</declaracaoInexistenciaMovimentoCasamento>" in xml
    assert "Nascimento" not in xml
    assert "Obito" not in xml


def test_a_declaracao_sem_mes_recusa():
    with pytest.raises(SIRC.SircError):
        SIRC.declaracao_de_inexistencia(competencia="")


# ------------------------------------------------ o CANCELAMENTO DE TERMO —
# 14/09/2026, seção 5.7 do manual. NÃO é um dos sete do art. 225: é para um
# termo que nunca valeu (livro errado, por exemplo), não um registro que
# existe e mudou. Validado contra o ÚNICO caso real desta serventia —
# assento 1231, `situacao='CANCELADO'`, a mesma história do «livro físico
# errado» que já apareceu na averbação (ver `sirc-tres-atos-sao-alteracao`).


def _assento_cancelado(con, *, numero=1, nome="CANCELADO DE TAL",
                       motivo="Determinação do oficial", matricula=None):
    if matricula is None:
        matricula = _matricula(termo=numero)
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em, matricula)
           VALUES ('RC_A','NASCIMENTO',?,?,?,?,'CANCELADO','SISTEMA',?,?)""",
        (numero, nome, AGORA[:10], AGORA[:10], AGORA, matricula))
    aid = int(cur.lastrowid)
    if motivo:
        con.execute(
            """INSERT INTO rc_atos (assento_id, tipo, data_ato, fundamento,
                   criado_em) VALUES (?,'AVERBACAO',?,?,?)""",
            (aid, AGORA[:10], motivo, AGORA))
    return aid


def test_cancelamento_pronto_e_valido_contra_o_caso_real(casa):
    """O motivo não tem coluna própria — vem da averbação mais recente
    sobre o mesmo assento, que na prática é onde o oficial já registra
    por que cancelou."""
    con = _con(casa)
    aid = _assento_cancelado(con, numero=1,
                             motivo="Determinação do oficial à lavratura "
                                   "no livro físico errado.")
    con.commit()
    pendentes = SIRC.pendentes_de_cancelamento(con)
    assert len(pendentes) == 1
    assert pendentes[0]["id"] == aid
    faltas = SIRC.o_que_falta_cancelamento(pendentes[0])
    assert faltas == []
    xml = SIRC._registro_termo_cancelado(pendentes[0])
    assert xml.startswith("<registroTermoCancelado>")
    assert "<tipoRegistroCivil>NASCIMENTO</tipoRegistroCivil>" in xml
    assert "livro físico errado" in xml


def test_cancelamento_sem_averbacao_fica_retido_por_falta_de_motivo(casa):
    """`motivo` é obrigatório no XSD (`string350`, `minOccurs="1"`) — sem
    averbação com fundamento, não se inventa texto para um campo que vai
    a um sistema federal."""
    con = _con(casa)
    _assento_cancelado(con, numero=2, motivo=None)
    con.commit()
    pendentes = SIRC.pendentes_de_cancelamento(con)
    faltas = SIRC.o_que_falta_cancelamento(pendentes[0])
    assert any("motivo do cancelamento" in f for f in faltas)


def test_cancelamento_de_natimorto_fica_retido_sem_correspondencia_no_enum(casa):
    """`tipoRegistroCivil` só tem NASCIMENTO/CASAMENTO/OBITO no XSD —
    natimorto não está entre eles, e não se adivinha qual dos dois usar."""
    con = _con(casa)
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em, matricula)
           VALUES ('RC_C_AUXILIAR','NATIMORTO',3,'NATIMORTO','2026-08-20',
                   '2026-08-20','CANCELADO','SISTEMA',?,?)""",
        (AGORA, RCM.compor(cns="000000", ano=2026, livro_tipo="5", livro=1,
                          folha=1, termo=3)))
    aid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO rc_atos (assento_id, tipo, data_ato, fundamento,
               criado_em) VALUES (?,'AVERBACAO',?,?,?)""",
        (aid, AGORA[:10], "motivo qualquer", AGORA))
    con.commit()
    pendentes = SIRC.pendentes_de_cancelamento(con)
    faltas = SIRC.o_que_falta_cancelamento(pendentes[0])
    assert any("tipo de registro civil" in f for f in faltas)


def test_cancelamento_sem_matricula_fica_retido(casa):
    con = _con(casa)
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em)
           VALUES ('RC_A','NASCIMENTO',4,'SEM MATRICULA','2026-08-20',
                   '2026-08-20','CANCELADO','SISTEMA',?)""", (AGORA,))
    aid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO rc_atos (assento_id, tipo, data_ato, fundamento,
               criado_em) VALUES (?,'AVERBACAO',?,?,?)""",
        (aid, AGORA[:10], "motivo qualquer", AGORA))
    con.commit()
    pendentes = SIRC.pendentes_de_cancelamento(con)
    faltas = SIRC.o_que_falta_cancelamento(pendentes[0])
    assert any("matrícula" in f for f in faltas)


def test_cancelamento_do_acervo_nao_se_remete(casa):
    con = _con(casa)
    con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em)
           VALUES ('RC_A','NASCIMENTO',283,'DO ACERVO','1955-10-12',
                   '1955-10-01','CANCELADO','EOFICIO',?)""", (AGORA,))
    con.commit()
    assert SIRC.pendentes_de_cancelamento(con) == []


def test_averbacao_de_assento_cancelado_nao_vira_alteracao(casa):
    """**O CASO REAL DO ASSENTO 1231, achado em 02/10/2026.** O termo
    cancelado tem uma averbação — a do próprio cancelamento —, e a busca dos
    atos não olhava a situação do assento: ele saía na remessa do dia como
    uma Alteração de um registro que nunca valeu. O caminho dele é o
    cancelamento, e só ele."""
    con = _con(casa)
    aid = _assento_cancelado(con, numero=5,
                             motivo="Determinação do oficial à lavratura "
                                   "no livro físico errado.")
    con.commit()
    ids = {p["id"] for p in SIRC.pendentes_de_remessa(con)}
    assert aid not in ids
    assert aid in {p["id"] for p in SIRC.pendentes_de_cancelamento(con)}


def test_cancelamento_com_matricula_de_assento_vivo_fica_retido(casa):
    """**OS CASOS REAIS 8311/8315 E 8300/8298, achados em 02/10/2026.** O termo
    foi refeito no mesmo lugar do livro, e o cancelado e o vivo têm a MESMA
    matrícula. O SIRC identifica o termo só pela matrícula: mandar este
    cancelamento cancelaria lá o registro que vale."""
    con = _con(casa)
    mesma = _matricula(termo=77)
    _assento_cancelado(con, numero=77, matricula=mesma,
                       motivo="Lavrado com erro e refeito.")
    vivo = _assento(con, numero=77, matricula=mesma)
    con.commit()
    pendente = SIRC.pendentes_de_cancelamento(con)[0]
    assert pendente["matricula_em_uso_por"] == vivo
    faltas = SIRC.o_que_falta_cancelamento(pendente)
    assert any(f"assento {vivo}" in f for f in faltas)
    montado = SIRC.montar_cancelamento([pendente])
    assert montado["quantos"] == 0
    assert montado["retidos"]


def test_montar_cancelamento_agrupa_em_lotes_de_250(casa):
    con = _con(casa)
    for i in range(1, 4):
        _assento_cancelado(con, numero=i, nome=f"PESSOA {i}",
                          motivo="art. 347 do Código de Normas")
    con.commit()
    pendentes = SIRC.pendentes_de_cancelamento(con)
    r = SIRC.montar_cancelamento(pendentes)
    assert not r["retidos"]
    assert r["quantos"] == 3
    assert len(r["lotes"]) == 1
    assert "movimentoCancelamentoTO" in r["lotes"][0]["xml"]
    assert "versaoLayoutCancelamento" in r["lotes"][0]["xml"]
    assert r["lotes"][0]["xml"].count("<registroTermoCancelado>") == 3


# ------------------------------------------------ o arquivo .mrc do SIRC-Web
#
# ENTROU EM 14/09/2026, quando a API recusou a credencial (usuário/senha
# inválido) e o oficial foi tentar a importação manual. Sem isto, o botão
# só entregava XML cru — que o SIRC-Web recusaria: a seção 3 do manual
# exige GZIP + AES-128-ECB (chave = MD5 do CNS sem zeros à esquerda) +
# extensão `.mrc`.


def test_arquivo_mrc_bate_byte_a_byte_com_o_comando_do_manual():
    """**A PROVA DE VERDADE**: o comando de exemplo do próprio manual
    (`openssl aes-128-ecb -k <cns sem zeros> -e -nosalt`) foi rodado à
    parte contra este mesmo conteúdo, com `-md md5` (sem isso, o OpenSSL
    3.x usa um KDF diferente — SHA-256 — e o exemplo do manual, escrito
    numa época de OpenSSL mais antigo, não bate mais). O resultado
    ficou fixo aqui como o valor medido. Medido de novo em 10/10/2026 com o
    CNS fictício 999999 (sanitização B3): `openssl aes-128-ecb -k 999999 -e
    -nosalt -md md5` deu exatamente os bytes abaixo.

    O GZIP conferido é o que o módulo cifra (`_comprimido`), e não o
    `gzip.compress` cru: o byte 9 do cabeçalho do cru é o do sistema que
    roda o teste (0a no Windows, 13 no Mac), e a medição foi feita com o do
    Windows."""
    conteudo = "conteudo de teste xml"
    gz = SIRC._comprimido(conteudo)
    assert gz.hex() == (
        "1f8b080000000000020a4bcecf2b492d4dc95748495528492d2e4"
        "955a8c8cd0100766430b615000000")
    mrc = SIRC.arquivo_mrc(conteudo, cns="999999")
    assert mrc.hex() == (
        "edde2d33bfc79d61071f5694d1a1be433cee72b2d185422eb7be64e8"
        "c391215f65305b3900d52b38eb69d9013a6b98cf")


def test_arquivo_mrc_roda_para_frente_e_para_tras():
    """Descomprime e decifra o que `arquivo_mrc` produziu, sem depender
    de `openssl` estar instalado na máquina que roda o teste — usa a
    mesma biblioteca (`cryptography`) ao contrário."""
    import gzip
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    xml_original = "<registroNascimentoInclusao><nome>MARIA ÍSIS</nome></registroNascimentoInclusao>"
    mrc = SIRC.arquivo_mrc(xml_original, cns="000000")

    chave = SIRC._chave_do_arquivo("000000")
    decifrador = Cipher(algorithms.AES(chave), modes.ECB()).decryptor()
    preenchido = decifrador.update(mrc) + decifrador.finalize()
    despadder = padding.PKCS7(128).unpadder()
    comprimido = despadder.update(preenchido) + despadder.finalize()
    xml_de_volta = gzip.decompress(comprimido).decode("utf-8")
    assert xml_de_volta == xml_original


def test_a_chave_e_o_md5_do_cns_sem_zeros_a_esquerda():
    """A seção 3.3 do manual: «a chave para cifrar deve ser o hash MD5 do
    CNS» — e o comando de exemplo usa `<código serventia SEM ZEROS À
    ESQUERDA>`."""
    import hashlib
    assert SIRC._chave_do_arquivo("999999") == hashlib.md5(b"999999").digest()
    assert SIRC._chave_do_arquivo("0999999") == hashlib.md5(b"999999").digest()


def test_o_nome_do_arquivo_tem_extensao_mrc():
    """«Quaisquer outras extensões serão ignoradas pelo SIRC» (seção 3.4)."""
    nome = SIRC.nome_do_arquivo_mrc("sirc-remessa", 7)
    assert nome == "sirc-remessa-007.mrc"
    assert nome.endswith(".mrc")


def test_arquivo_mrc_e_deterministico():
    """`mtime=0` no GZIP — sem isso, o mesmo XML gerava um `.mrc`
    diferente a cada chamada, só porque o relógio mudou."""
    xml = "<a>teste</a>"
    assert SIRC.arquivo_mrc(xml, cns="000000") == SIRC.arquivo_mrc(xml, cns="000000")


@pytest.mark.parametrize("sistema", [0x03, 0x0A, 0x13, 0xFF])
def test_o_mrc_sai_igual_qualquer_que_seja_o_sistema_que_comprimiu(monkeypatch, sistema):
    """O zlib escreve no cabeçalho do GZIP o byte do sistema que comprimiu (3
    no Linux, 10 no Windows, 19 no Mac, 255 no Python 3.13+), e esse byte cai
    no primeiro bloco cifrado. Aqui o `gzip.compress` finge ser cada um deles:
    o `.mrc` tem de sair o mesmo, o medido contra o openssl."""
    import gzip
    original = gzip.compress

    def comprime_como(dados, *args, **kwargs):
        gz = bytearray(original(dados, *args, **kwargs))
        gz[9] = sistema
        return bytes(gz)

    monkeypatch.setattr(gzip, "compress", comprime_como)
    mrc = SIRC.arquivo_mrc("conteudo de teste xml", cns="999999")
    assert mrc.hex() == (
        "edde2d33bfc79d61071f5694d1a1be433cee72b2d185422eb7be64e8"
        "c391215f65305b3900d52b38eb69d9013a6b98cf")


# ------------------------------------------------ o que veio do acervo


def test_o_que_veio_do_acervo_nao_entra_na_remessa(casa):
    """**ACHADO NO ENSAIO CONTRA A PRODUÇÃO, em 30/08/2026.** Sem este filtro a
    lista devolvia **243 registros, o mais antigo de 12/10/1955** — numa tela que
    diz «o prazo é de 1 dia útil». Aquele nascimento apareceria como vinte e
    cinco mil dias em atraso, numa lista que o balcão não teria como zerar.

    O registro deles aconteceu há décadas, antes de o SIRC existir; o que
    aconteceu foi a **digitação**. A remessa é do que se **registrou**.
    """
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',283,'HEITOR DIAS CAMARGO',
                       '1955-10-12','1955-10-01','ATIVO','EOFICIO',?)""",
            (AGORA,))
        _assento(con, nome="LAVRADO AQUI", numero=1)
    lista = SIRC.pendentes_de_remessa(con)
    assert [x["nome"] for x in lista] == ["LAVRADO AQUI"]


def test_o_ato_sobre_assento_do_acervo_tambem_nao_entra(casa):
    """A averbação lançada num assento de 1955 é ato desta casa — mas o SIRC não
    tem o assento dela, e mandar averbação de registro que ele nunca recebeu é
    mandar informação que ele não sabe onde pôr.

    **Enquanto a carga do acervo não subir à Central, o ato sobre ele fica
    fora** — e quem decide subir o acervo é o oficial.
    """
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',283,'DO ACERVO','1955-10-12',
                       '1955-10-01','ATIVO','EOFICIO',?)""", (AGORA,))
        aid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO rc_atos (assento_id, tipo, data_ato, criado_em)
               VALUES (?,'AVERBACAO','2026-08-21',?)""", (aid, AGORA))
    assert SIRC.pendentes_de_remessa(con) == []


def test_a_origem_que_nao_se_remete_esta_declarada():
    """Um filtro sem nome é um filtro que alguém apaga sem saber o que perdeu.

    Passou de uma origem só para três em 13/09/2026 — o lote de 6.757
    assentos do acervo em .docx chegou com `origem='IMPORTACAO'`, que este
    filtro ainda não conhecia, e apareceu inteiro na lista de pendentes do
    SIRC com o mais antigo de 1900."""
    assert set(SIRC.ORIGENS_QUE_NAO_SE_REMETEM) == {
        "EOFICIO", "ARQUIVO", "IMPORTACAO"}


def test_o_que_veio_do_docx_tambem_nao_se_remete(casa):
    """A mesma armadilha do EOFICIO, pela origem nova — achado em 13/09/2026
    contra a produção: 6.757 assentos com `origem='IMPORTACAO'` apareciam
    inteiros na lista de pendentes, o mais antigo de 1900."""
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',1,'DO ACERVO EM DOCX','1900-07-07',
                       '1900-07-01','ATIVO','IMPORTACAO',?)""", (AGORA,))
    assert SIRC.pendentes_de_remessa(con) == []


def test_arquivo_tambem_nao_se_remete(casa):
    """`ARQUIVO` é a mesma família — assento importado de outra fonte que
    não o E-Ofício, sem que o registro tenha acontecido agora."""
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',1,'DO ARQUIVO','1967-12-18',
                       '1967-12-01','ATIVO','ARQUIVO',?)""", (AGORA,))
    assert SIRC.pendentes_de_remessa(con) == []


def test_quantos_ficam_de_fora_pelo_acervo(casa):
    """**RELATO DO OFICIAL EM 13/09/2026: "não aparece todos registros do
    sistema para envio".** A lista caiu de milhares para poucos depois do
    conserto do vazamento — certo, mas sem este número a tela parecia estar
    escondendo registro. Ele conta exatamente o que `pendentes_de_remessa`
    exclui."""
    con = _con(casa)
    with con:
        _assento(con, nome="DO SISTEMA", numero=1)
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',2,'DO ACERVO','1967-12-18',
                       '1967-12-01','ATIVO','ARQUIVO',?)""", (AGORA,))
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',3,'DO DOCX','1900-07-07',
                       '1900-07-01','ATIVO','IMPORTACAO',?)""", (AGORA,))
    assert SIRC.quantos_ficam_de_fora_pelo_acervo(con) == 2


# ------------------------------------------------ a carga do acervo em .docx


def test_a_carga_do_acervo_traz_so_importacao(casa):
    """**DECISÃO DO OFICIAL EM 14/09/2026**: o lote em .docx precisa subir
    ao SIRC, porque o E-Ofício nunca o enviou. `EOFICIO` e `ARQUIVO` ficam
    de fora até se confirmar que não cumpriram a obrigação sozinhos —
    diferente de `IMPORTACAO`, que nunca esteve em sistema nenhum."""
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em, matricula,
                   ibge_local_nascimento)
               VALUES ('RC_A','NASCIMENTO',1,'DO DOCX','1900-07-07',
                       '1900-07-01','ATIVO','IMPORTACAO',?,?,3)""",
            (AGORA, _matricula(termo=1)))
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',2,'DO EOFICIO','1955-10-12',
                       '1955-10-01','ATIVO','EOFICIO',?)""", (AGORA,))
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',3,'DO ARQUIVO','1967-12-18',
                       '1967-12-01','ATIVO','ARQUIVO',?)""", (AGORA,))
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em, matricula)
               VALUES ('RC_A','NASCIMENTO',4,'DO SISTEMA','2026-09-09',
                       '2026-09-08','ATIVO','SISTEMA',?,?)""",
            (AGORA, _matricula(termo=4)))
    carga = SIRC.pendentes_de_carga_do_acervo(con)
    assert [x["nome"] for x in carga] == ["DO DOCX"]


def test_a_carga_do_acervo_monta_e_valida(casa):
    """A carga usa o MESMO envelope da remessa — o que muda é só a fonte dos
    assentos. Um registro do .docx, com matrícula, sai pronto."""
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em, matricula,
                   ibge_local_nascimento)
               VALUES ('RC_A','NASCIMENTO',1,'DO DOCX','1900-07-07',
                       '1900-07-01','ATIVO','IMPORTACAO',?,?,3)""",
            (AGORA, _matricula(termo=1)))
    carga = SIRC.pendentes_de_carga_do_acervo(con)
    m = SIRC.montar(con, carga, cns="000000")
    assert m["quantos"] == 1
    assert "<movimentoNascimentoTO>" in m["lotes"][0]["xml"]
    assert "DO DOCX" in m["lotes"][0]["xml"]


# ------------------------------------------ o que já saiu para o SIRC


def test_a_chave_do_envio_e_a_do_gestor():
    """A chave gravada em `ge_envios` tem de ser a que
    `gestor_conferencia.regra_sirc` procura — outra chave gravaria o envio
    e a cobrança continuaria."""
    assert SIRC.referencia_do_envio(
        {"onde": "rc_assentos", "assento_id": 8266,
         "data_ato": "2026-09-15T10:00"}) == "rc_assentos:8266:2026-09-15"
    alteracao = {"onde": "rc_atos", "assento_id": 12, "data_ato": "2026-01-01",
                 "atos": [{"data_ato": "2026-09-02"}, {"data_ato": "2026-09-20"}]}
    assert SIRC.referencia_do_envio(alteracao) == "rc_atos:12:2026-09-20"
    assert SIRC.referencia_do_envio(
        {"onde": "rc_assentos", "assento_id": 5, "data_ato": ""}) == "rc_assentos:5"


def test_o_ja_enviado_sai_da_remessa_e_o_alterado_depois_volta():
    con = conexao_de_teste()
    con.execute("CREATE TABLE ge_envios (central TEXT, referencia TEXT, "
                "situacao TEXT DEFAULT 'ENVIADO')")
    con.execute("INSERT INTO ge_envios (central, referencia) VALUES "
                "('SIRC', 'rc_assentos:1:2026-09-10')")
    con.execute("INSERT INTO ge_envios (central, referencia, situacao) VALUES "
                "('SIRC', 'rc_assentos:2:2026-09-11', 'REJEITADO')")
    con.execute("INSERT INTO ge_envios (central, referencia) VALUES "
                "('SIRC', 'rc_atos:3:2026-09-01')")
    pend = [
        {"onde": "rc_assentos", "assento_id": 1, "data_ato": "2026-09-10"},
        {"onde": "rc_assentos", "assento_id": 2, "data_ato": "2026-09-11"},
        {"onde": "rc_atos", "assento_id": 3, "data_ato": "2026-09-01",
         "atos": [{"data_ato": "2026-09-01"}, {"data_ato": "2026-09-30"}]},
    ]
    ficam = [p["assento_id"] for p in SIRC.sem_os_ja_enviados(con, pend)]
    # o 1 foi enviado; o 2 foi REJEITADO (continua devido); o 3 ganhou
    # averbação depois do envio — é envio novo.
    assert ficam == [2, 3]


def test_sem_a_tabela_do_gestor_nada_sai_da_remessa():
    con = conexao_de_teste()
    pend = [{"onde": "rc_assentos", "assento_id": 1, "data_ato": "2026-09-10"}]
    assert SIRC.sem_os_ja_enviados(con, pend) == pend
    assert SIRC.ja_enviados(con) == set()


def test_o_cancelamento_enviado_sai_da_lista():
    con = conexao_de_teste()
    con.execute("CREATE TABLE ge_envios (central TEXT, referencia TEXT, "
                "situacao TEXT DEFAULT 'ENVIADO')")
    con.execute("INSERT INTO ge_envios (central, referencia) VALUES "
                "('SIRC_CANCELAMENTO', 'rc_assentos:9')")
    ficam = SIRC.cancelamentos_sem_os_ja_enviados(con, [{"id": 9}, {"id": 10}])
    assert ficam == [{"id": 10}]


# ------------------------------------------ o LOCAL do nascimento (06/10/2026)


def test_o_local_do_nascimento_vai_no_arquivo(casa):
    """O SIRC-Web da casa recusou os termos 19572 a 19575, duas vezes, com
    «Dados Obrigatórios não informados: local». O XSD o declara opcional; a
    Central o exige."""
    con = _con(casa)
    hosp = _assento(con, nome="NO HOSPITAL", numero=301, local=1)
    em_casa = _assento(con, nome="EM CASA", numero=302, local=3)
    con.commit()
    m = SIRC.montar(con, [r for r in SIRC.pendentes_de_remessa(con)
                          if r["assento_id"] in (hosp, em_casa)], cns="000000")
    assert not m["retidos"]
    xml = m["lotes"][0]["xml"]
    assert "<local>UNIDADE_SAUDE</local>" in xml
    assert "<local>FORA_UNIDADE_SAUDE</local>" in xml
    # a ordem do xs:sequence: depois da hora, antes do nome do registrado
    registro = xml[:xml.index("NO HOSPITAL")]
    registro = registro[registro.rindex("<registroNascimento"):]
    assert registro.index("<local>") > registro.index("<horaNascimento")


def test_nascimento_sem_local_ou_ignorado_fica_retido(casa):
    con = _con(casa)
    sem = _assento(con, nome="SEM LOCAL", numero=303, local=None)
    ign = _assento(con, nome="LOCAL IGNORADO", numero=304, local=9)
    con.commit()
    m = SIRC.montar(con, [r for r in SIRC.pendentes_de_remessa(con)
                          if r["assento_id"] in (sem, ign)], cns="000000")
    assert m["quantos"] == 0
    assert len(m["retidos"]) == 2
    assert all(any("local do nascimento" in f for f in r["faltas"])
               for r in m["retidos"])


def test_o_painel_conta_so_o_que_nao_foi_enviado(casa):
    """`rc_obrigacoes` pergunta `quantas_pendentes` antes de
    `pendentes_de_remessa`: o já enviado não pode continuar no painel."""
    import rc_obrigacoes
    con = _con(casa)
    aid = _assento(con, nome="JA FOI", numero=401)
    con.commit()
    antes = SIRC.quantas_pendentes(con)
    ref = SIRC.referencia_do_envio(
        next(p for p in SIRC.pendentes_de_remessa(con) if p["assento_id"] == aid))
    # `ge_envios` nasce na subida desde o LH09 (21/10/2026), com o que o
    # gestor exige de todo envio: quando saiu, quando e por quem se registrou.
    con.execute("INSERT INTO ge_envios (central, referencia, enviado_em, registrado_em, "
                "registrado_por) VALUES ('SIRC', ?, '2026-10-21T10:00:00', "
                "'2026-10-21T10:00:00', 'mario')", (ref,))
    con.commit()
    assert SIRC.quantas_pendentes(con) == antes - 1
    assert rc_obrigacoes._quantas("sirc_remessa", con)["quantas"] == antes - 1
