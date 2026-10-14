"""As comunicações mensais de óbito — art. 226 do Código de Normas do TJMA.

O QUE ESTES TESTES GUARDAM
    **Que cada destino filtra pelo que a norma manda.** Mandar a lista inteira
    ao juiz eleitoral seria mandar nome de criança para cancelar alistamento que
    nunca existiu; mandar só os maiores de 16 à Receita seria esconder dela
    metade dos óbitos.

    **Que quem não tem idade ENTRA.** Deixá-lo de fora seria esconder um óbito
    do órgão por falta de um campo — e o § 2º responsabiliza quem omite.

    **Que o teor fica guardado inteiro.** O § 1º, III manda arquivar por dois
    anos, organizado por períodos mensais, e é isso que se mostra na correição.

    **Que a idade desconta o aniversário.** É conserto de um defeito medido do
    E-Ofício, que mandava a idade um ano a mais ao IBGE — e aqui a idade decide
    quem entra em duas das cinco relações.
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

import rc_comunicacoes as CM                                     # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-01T09:00"

SERVENTIA = {
    "nome": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
    "cidade": "Cidade Exemplo", "uf": "MA",
    "registrador": "MARIO EXEMPLO DOS SANTOS",
    "titulo": "Tabelião e Oficial de Registro",
}


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _obito(con, nome, sexo, data_nascimento, *, numero=1,
           data_ato="2026-07-15", data_fato="2026-07-14", **extras):
    campos = {"serie": "RC_C", "especie": "OBITO", "numero": numero,
              "nome": nome, "data_ato": data_ato, "data_fato": data_fato,
              "situacao": "ATIVO", "origem": "SISTEMA", "criado_em": AGORA}
    campos.update(extras)
    colunas = ", ".join(campos)
    marcas = ", ".join("?" for _ in campos)
    cur = con.execute(f"INSERT INTO rc_assentos ({colunas}) VALUES ({marcas})",
                      tuple(campos.values()))
    aid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm, sexo,
               data_nascimento, criado_em) VALUES (?,?,?,?,?,?,?)""",
        (aid, "FALECIDO", nome, nome.lower(), sexo, data_nascimento, AGORA))
    return aid


def _tres_de_julho(con):
    """Uma criança de 8, um homem de 22 e uma mulher de 70."""
    _obito(con, "CRIANCA X", "F", "2018-03-01", numero=1)
    _obito(con, "JULIO CEZAR", "M", "2004-02-10", numero=2)
    _obito(con, "MARIA DAS DORES", "F", "1956-01-05", numero=3)


# ------------------------------------------------ os cinco destinos


def test_sao_cinco_destinos_e_os_filtros_sao_da_norma():
    assert len(CM.DESTINOS) == 5
    filtros = {d["chave"]: d["quem"] for d in CM.DESTINOS}
    assert filtros["ELEITORAL"] == CM.MAIORES_DE_16
    assert filtros["JUNTA_MILITAR"] == CM.HOMENS_17_A_45
    assert filtros["RECEITA"] == CM.TODOS


def test_cada_destino_traz_o_artigo():
    """Regra sem endereço é regra que ninguém confere."""
    for d in CM.DESTINOS:
        assert d["artigo"], f"{d['chave']} sem artigo"


def test_a_junta_militar_nao_esta_no_codigo_de_normas():
    """É da Lei 4.375/1964 — e por isso quase se perdeu: quem lê só o Código não
    a encontra."""
    jm = CM.destino("JUNTA_MILITAR")
    assert "4.375" in jm["artigo"]
    assert "NÃO está no Código de Normas" in jm["onde"]


def test_o_prazo_e_em_dias_uteis():
    """«até o 5º (quinto) dia útil» — e desta vez o artigo qualifica, ao
    contrário do prazo das anotações e do SIGEF."""
    assert CM.PRAZO_DIAS_UTEIS == 5
    assert CM.ARTIGO_DO_PRAZO == "art. 226, caput"


def test_o_modulo_nao_conta_dia_util():
    """Quem conta dia útil é o núcleo, que conhece os feriados desta comarca.
    Uma segunda contagem divergiria — e num prazo, divergir por um dia é perder
    o prazo.

    O VARREDOR PROCURA O USO, E NÃO A MENÇÃO. A primeira versão procurava o nome
    da função de contagem como texto solto, e bateu no **próprio comentário do
    módulo**, que a cita para explicar por que não a chama.

    **Terceira vez nesta sessão que um varredor bate na prosa** — antes foram o
    de portabilidade e o de escrita. A regra que fica: varredor de código
    procura `import`, chamada ou atribuição; nunca uma palavra solta que também
    cabe numa frase.
    """
    codigo = (RAIZ / "rc_comunicacoes.py").read_text(encoding="utf-8")
    proibidos = (
        "from datetime import",       # importar o módulo de data
        "import datetime",
        "soma_dias_uteis(",           # CHAMAR a contagem, e não citá-la
        "date.today(",
    )
    for p in proibidos:
        assert p not in codigo, f"o módulo conta data com «{p}»"


# ------------------------------------------------ os filtros na prática


def test_a_crianca_de_oito_anos_fica_fora_do_eleitoral(casa):
    """Mandar o nome dela seria pedir o cancelamento de um alistamento que nunca
    existiu."""
    con = _con(casa)
    with con:
        _tres_de_julho(con)
    r = CM.relacao(con, "2026-07", "ELEITORAL")
    assert r["quantos"] == 2
    assert "CRIANCA X" not in [x["nome"] for x in r["entram"]]
    assert "CRIANCA X" in [x["nome"] for x in r["ficam_de_fora"]]


def test_a_receita_recebe_todos(casa):
    """Mandar só os maiores de 16 esconderia dela metade dos óbitos."""
    con = _con(casa)
    with con:
        _tres_de_julho(con)
    assert CM.relacao(con, "2026-07", "RECEITA")["quantos"] == 3


def test_a_junta_militar_so_alcanca_homens_de_17_a_45(casa):
    con = _con(casa)
    with con:
        _tres_de_julho(con)
    r = CM.relacao(con, "2026-07", "JUNTA_MILITAR")
    assert [x["nome"] for x in r["entram"]] == ["JULIO CEZAR"]


def test_a_lista_mostra_quem_ficou_de_fora(casa):
    """Lista que só mostra quem entra deixa quem confere sem saber se faltou
    alguém."""
    con = _con(casa)
    with con:
        _tres_de_julho(con)
    r = CM.relacao(con, "2026-07", "JUNTA_MILITAR")
    assert len(r["ficam_de_fora"]) == 2
    assert r["quantos_no_mes"] == 3


# ------------------------------------------------ a idade


def test_a_idade_desconta_o_aniversario(casa):
    """CONSERTO DE UM DEFEITO DO E-OFÍCIO, medido em 3 dos 11 óbitos
    comparáveis: ele fazia «ano do óbito − ano do nascimento» e mandava a idade
    um ano a mais.

    Aqui a idade decide quem entra em duas das cinco relações — o erro deixaria
    de ser estatístico e passaria a ser de lista."""
    con = _con(casa)
    with con:
        # faz 46 em dezembro; no dia do óbito tem 45, e a Junta Militar o pega
        _obito(con, "ANTES DO ANIVERSARIO", "M", "1980-12-31", numero=1)
    r = CM.relacao(con, "2026-07", "JUNTA_MILITAR")
    assert [x["nome"] for x in r["entram"]] == ["ANTES DO ANIVERSARIO"]
    assert r["entram"][0]["idade"] == 45


def test_quem_nao_tem_idade_entra(casa):
    """Deixá-lo de fora seria esconder um óbito do órgão por falta de um campo —
    e o § 2º responsabiliza quem omite."""
    con = _con(casa)
    with con:
        _obito(con, "SEM DATA DE NASCIMENTO", "M", None, numero=1)
    for chave in ("ELEITORAL", "JUNTA_MILITAR", "RECEITA"):
        r = CM.relacao(con, "2026-07", chave)
        assert r["quantos"] == 1, f"{chave} deixou de fora quem não tem idade"


def test_a_relacao_diz_que_a_idade_nao_foi_informada(casa):
    """Omitir a falta faria o órgão receber a linha sem saber que o dado não
    existe."""
    con = _con(casa)
    with con:
        _obito(con, "SEM DATA", "M", None, numero=1)
        CM.declarar_mes(con, "2026-07", agora=AGORA)
    alguma = CM.pendentes(con)[0]
    texto = CM.montar(con, alguma["id"], serventia=SERVENTIA)["texto"]
    assert "idade não informada no assento" in texto


# ------------------------------------------------ abrir o mês


def test_declarar_abre_as_cinco(casa):
    con = _con(casa)
    with con:
        novas = CM.declarar_mes(con, "2026-07", agora=AGORA)
    assert len(novas) == 5
    assert CM.quantas_pendentes(con) == 5


def test_abre_as_cinco_mesmo_no_mes_vazio(casa):
    """Mês sem óbito continua devendo a resposta: o art. 225, § 3º manda
    comunicar o fato, e o SIRC tem «declaração de inexistência de movimento».
    **Comunicação que não se abre por estar vazia é comunicação que ninguém
    lembra de mandar.**"""
    con = _con(casa)
    with con:
        CM.declarar_mes(con, "2026-02", agora=AGORA)
    assert CM.quantas_pendentes(con) == 5
    alguma = CM.pendentes(con)[0]
    texto = CM.montar(con, alguma["id"], serventia=SERVENTIA)["texto"]
    assert "Nada consta" in texto


def test_declarar_duas_vezes_nao_duplica(casa):
    con = _con(casa)
    with con:
        CM.declarar_mes(con, "2026-07", agora=AGORA)
        segundas = CM.declarar_mes(con, "2026-07", agora=AGORA)
    assert segundas == []
    assert CM.quantas_pendentes(con) == 5


def test_a_competencia_e_o_mes(casa):
    con = _con(casa)
    with con, pytest.raises(CM.ComunicacaoError) as erro:
        CM.declarar_mes(con, "2026", agora=AGORA)
    assert "AAAA-MM" in str(erro.value)


# ------------------------------------------------ o envio congela


def test_o_envio_exige_protocolo(casa):
    """Sem ele não há como mostrar, numa correição, que a comunicação saiu."""
    con = _con(casa)
    with con:
        CM.declarar_mes(con, "2026-07", agora=AGORA)
        alguma = CM.pendentes(con)[0]
    with con, pytest.raises(CM.ComunicacaoError) as erro:
        CM.registrar_envio(con, alguma["id"], canal="OFICIO", protocolo="",
                           quando="2026-08-05", agora=AGORA,
                           serventia=SERVENTIA)
    assert "art. 226, § 2º" in str(erro.value)


def test_o_teor_fica_guardado_inteiro(casa):
    """O § 1º, III manda arquivar por dois anos, organizado por mês — e é isso
    que se mostra na correição. Guardar só a marca de «enviada» seria dizer que
    se cumpriu sem poder mostrar o quê."""
    con = _con(casa)
    with con:
        _tres_de_julho(con)
        CM.declarar_mes(con, "2026-07", agora=AGORA)
        alguma = [x for x in CM.pendentes(con) if x["destino"] == "RECEITA"][0]
        CM.registrar_envio(con, alguma["id"], canal="OFICIO",
                           protocolo="OF-2026-0099", quando="2026-08-05",
                           agora=AGORA, serventia=SERVENTIA, usuario="jean")
    linha = con.execute("SELECT * FROM rc_comunicacoes WHERE id=?",
                        (alguma["id"],)).fetchone()
    assert linha["situacao"] == CM.ENVIADA
    assert "MARIA DAS DORES" in linha["teor"]
    assert linha["quantos"] == 3
    assert len(linha["hash_teor"]) == 64
    assert linha["protocolo"] == "OF-2026-0099"


def test_nao_se_envia_duas_vezes(casa):
    con = _con(casa)
    with con:
        CM.declarar_mes(con, "2026-07", agora=AGORA)
        alguma = CM.pendentes(con)[0]
        CM.registrar_envio(con, alguma["id"], canal="OFICIO", protocolo="1",
                           quando="2026-08-05", agora=AGORA,
                           serventia=SERVENTIA)
    with con, pytest.raises(CM.ComunicacaoError) as erro:
        CM.registrar_envio(con, alguma["id"], canal="OFICIO", protocolo="2",
                           quando="2026-08-06", agora=AGORA,
                           serventia=SERVENTIA)
    assert "já está como" in str(erro.value)


def test_montar_nao_grava(casa):
    con = _con(casa)
    with con:
        CM.declarar_mes(con, "2026-07", agora=AGORA)
        alguma = CM.pendentes(con)[0]
    CM.montar(con, alguma["id"], serventia=SERVENTIA)
    linha = con.execute("SELECT teor, situacao FROM rc_comunicacoes WHERE id=?",
                        (alguma["id"],)).fetchone()
    assert not (linha["teor"] or "")
    assert linha["situacao"] == CM.PENDENTE


# ------------------------------------------------ dispensar


def test_dispensar_exige_motivo(casa):
    con = _con(casa)
    with con:
        CM.declarar_mes(con, "2026-07", agora=AGORA)
        alguma = CM.pendentes(con)[0]
    with con, pytest.raises(CM.ComunicacaoError) as erro:
        CM.dispensar(con, alguma["id"], motivo="não", agora=AGORA)
    assert "responsabiliza a omissão" in str(erro.value)


# ------------------------------------------------ o atraso


def test_a_lista_do_atraso_diz_quantas_faltam(casa):
    """É a lista que diz o tamanho do que está em aberto."""
    con = _con(casa)
    with con:
        _obito(con, "A", "M", "1990-01-01", numero=1, data_ato="2026-04-10")
        _obito(con, "B", "F", "1990-01-01", numero=2, data_ato="2026-07-10")
        CM.declarar_mes(con, "2026-04", agora=AGORA)
    faltando = CM.meses_sem_comunicacao(con)
    assert [x["competencia"] for x in faltando] == ["2026-07"]
    assert faltando[0]["faltam"] == 5


def test_os_meses_com_obito_saem_do_banco(casa):
    con = _con(casa)
    with con:
        _obito(con, "A", "M", "1990-01-01", numero=1, data_ato="2026-04-10")
        _obito(con, "B", "F", "1990-01-01", numero=2, data_ato="2026-04-20")
        _obito(con, "C", "F", "1990-01-01", numero=3, data_ato="2026-07-10")
    meses = CM.meses_com_obito(con)
    assert meses == [{"competencia": "2026-04", "obitos": 2},
                     {"competencia": "2026-07", "obitos": 1}]


def test_a_lista_vem_do_mais_antigo(casa):
    """Aqui o que importa é o prazo, e quem está há mais tempo esperando é quem
    está mais perto de estourá-lo."""
    con = _con(casa)
    with con:
        CM.declarar_mes(con, "2026-07", agora=AGORA)
        CM.declarar_mes(con, "2026-04", agora=AGORA)
    assert CM.pendentes(con)[0]["competencia"] == "2026-04"


# ------------------------------------------------ o módulo não envia


def test_o_modulo_nao_envia_nada():
    """Cada órgão recebe por um caminho próprio, e nenhum está medido. Ele monta,
    guarda e cobra o prazo; quem manda é a pessoa."""
    codigo = (RAIZ / "rc_comunicacoes.py").read_text(encoding="utf-8")
    for proibido in ("requests", "urllib", "smtplib", "socket"):
        assert proibido not in codigo, f"o módulo tenta enviar com {proibido}"
    publicos = [n for n in dir(CM)
                if not n.startswith("_") and callable(getattr(CM, n))]
    for nome in publicos:
        for proibido in ("enviar", "transmitir", "lavrar"):
            assert proibido not in nome.lower(), f"`{nome}` faz o que não deve"
