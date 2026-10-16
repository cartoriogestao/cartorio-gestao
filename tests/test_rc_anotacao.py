"""As anotações devidas do Registro Civil — Seção XIII, arts. 367 a 372.

O QUE ESTES TESTES GUARDAM
    **Que a pendência nasce na lavratura, e não depois.** O prazo do art. 367 é
    de cinco dias contados do ato; abrir a pendência mais tarde faria o relógio
    começar atrasado, que é o mesmo que não ter relógio.

    **Que o módulo não anota sozinho no assento alheio.** O art. 370 manda
    conferir a compatibilidade dos atos antes — um programa que anotasse sozinho
    estaria decidindo que dois assentos são da mesma pessoa, que é justamente o
    que o oficial tem de conferir.

    **Que a comunicação exige protocolo.** A norma pede confirmação de
    recebimento, e comunicação sem confirmação é a que ninguém prova ter
    mandado.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_anotacao as ANOT                                       # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-29T09:00"
HOJE = "2026-08-29"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); usuario+login por teste."""
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = cg_casa["cliente"]
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _liso(t: str) -> str:
    return " ".join((t or "").split())


def _assento(con, *, especie="OBITO", numero="31", data_ato=HOJE, **extras):
    campos = {"serie": "RC_C", "especie": especie, "numero": numero,
              "nome": "ANTONIO DA SILVA", "data_ato": data_ato,
              "data_fato": data_ato, "situacao": "ATIVO",
              "origem": "SISTEMA", "criado_em": AGORA}
    campos.update(extras)
    colunas = ", ".join(campos)
    marcas = ", ".join("?" for _ in campos)
    cur = con.execute(f"INSERT INTO rc_assentos ({colunas}) VALUES ({marcas})",
                      tuple(campos.values()))
    return int(cur.lastrowid)


# ------------------------------------------------ a norma


def test_o_obito_anota_no_nascimento_e_no_casamento():
    """Art. 372, na letra: «O óbito deverá ser anotado, com as remissões
    recíprocas, nos assentos de casamento e nascimento.»"""
    assert set(ANOT.o_que_o_ato_gera("OBITO")) == {"NASCIMENTO", "CASAMENTO"}


def test_o_nascimento_nao_anota_em_lugar_nenhum():
    """Ele É o registro primitivo — e devolver vazio aqui é resposta, e não
    omissão."""
    assert ANOT.o_que_o_ato_gera("NASCIMENTO") == ()
    assert ANOT.o_que_o_ato_gera("NATIMORTO") == ()


def test_as_tres_do_livro_e_tambem_anotam():
    """Art. 328, § 2º — e eu as tinha deixado de fora. Foi a minha própria
    saída de conferência que mostrou: `INTERDICAO` aparecia como «é o registro
    primitivo», o que é falso — é sentença que muda a capacidade de quem já tem
    nascimento lavrado."""
    for especie in ("INTERDICAO", "EMANCIPACAO", "AUSENCIA"):
        assert ANOT.o_que_o_ato_gera(especie) == ("NASCIMENTO", "CASAMENTO")
    assert set(ANOT.AVISAR_O_JUIZ["especies"]) == {"INTERDICAO", "EMANCIPACAO",
                                                   "AUSENCIA"}


def test_o_prazo_e_de_cinco_dias_corridos():
    """O art. 367 escreve «cinco dias» sem qualificar. Inventar «úteis» daria à
    serventia mais prazo do que a norma deu — é a mesma decisão do prazo do
    SIGEF."""
    assert ANOT.PRAZO_DIAS == 5
    assert ANOT.ARTIGO_DO_PRAZO == "art. 367"


def test_a_crc_e_o_primeiro_canal():
    """Provimento 46/2015 do CNJ, e a ordem é da norma."""
    assert ANOT.CANAIS[0] == "CRC"
    assert ANOT.CANAIS == ("CRC", "MALOTE", "CARTA")


def test_todo_artigo_citado_tem_endereco():
    """Regra sem endereço é regra que ninguém confere."""
    citados = ANOT.artigos_citados()
    assert "art. 367" in citados
    assert "art. 372" in citados
    assert "art. 328" in citados      # as três do Livro E
    assert "art. 226" in citados      # o canal da CRC


# ------------------------------------------------ a pendência nasce no ato


def test_a_pendencia_nasce_ao_lavrar(casa):
    """DECLARA-SE NA LAVRATURA. O prazo conta do ato; abrir a pendência mais
    tarde faria o relógio começar atrasado."""
    con = _con(casa)
    with con:
        aid = _assento(con, especie="OBITO")
        ANOT.declarar(con, aid, agora=AGORA)
    p = ANOT.pendencias_do_assento(con, aid)
    assert {x["especie_alvo"] for x in p} == {"NASCIMENTO", "CASAMENTO"}
    assert all(x["situacao"] == ANOT.PENDENTE for x in p)


def test_declarar_duas_vezes_nao_duplica(casa):
    """Lavrar, corrigir e salvar de novo não pode multiplicar a obrigação."""
    con = _con(casa)
    with con:
        aid = _assento(con)
        primeiras = ANOT.declarar(con, aid, agora=AGORA)
        segundas = ANOT.declarar(con, aid, agora=AGORA)
    assert len(primeiras) == 2
    assert segundas == []
    assert len(ANOT.pendencias_do_assento(con, aid)) == 2


def test_o_nascimento_nao_abre_pendencia_nenhuma(casa):
    con = _con(casa)
    with con:
        aid = _assento(con, especie="NASCIMENTO", serie="RC_A")
        ANOT.declarar(con, aid, agora=AGORA)
    assert ANOT.pendencias_do_assento(con, aid) == []


def test_lavrar_pela_casa_ja_abre_a_pendencia(casa):
    """A LIGAÇÃO COM `rc_assento.lavrar_assento` — sem ela o módulo seria mais
    uma função pronta que ninguém chama."""
    import rc_assento as RC
    con = _con(casa)
    with con:
        RC.lavrar_assento(con, especie="OBITO", nome="ANTONIO DA SILVA",
                          agora=AGORA, data_fato="2026-08-28",
                          usuario="mario", origem="SISTEMA",
                          sv={"cidade": "Cidade Exemplo", "uf": "MA"},
                          data_extenso=lambda d: str(d))
    assert ANOT.quantas_pendentes(con) == 2


# ------------------------------------------------ anotar aqui


def test_anotar_aqui_exige_que_o_assento_exista(casa):
    con = _con(casa)
    with con:
        aid = _assento(con)
        ids = ANOT.declarar(con, aid, agora=AGORA)
    with con, pytest.raises(ANOT.AnotacaoError) as erro:
        ANOT.anotar_aqui(con, ids[0], assento_alvo_id=99999, agora=AGORA)
    assert "o caminho é a comunicação" in str(erro.value)


def test_o_assento_nao_se_anota_nele_mesmo(casa):
    con = _con(casa)
    with con:
        aid = _assento(con)
        ids = ANOT.declarar(con, aid, agora=AGORA)
    with con, pytest.raises(ANOT.AnotacaoError) as erro:
        ANOT.anotar_aqui(con, ids[0], assento_alvo_id=aid, agora=AGORA)
    assert "no registro ANTERIOR" in str(erro.value)


def test_anotar_aqui_guarda_qual_assento_foi(casa):
    """É o rastro que a correição procura: quem conferiu, quando, e em qual."""
    con = _con(casa)
    with con:
        alvo = _assento(con, especie="NASCIMENTO", serie="RC_A", numero="100")
        aid = _assento(con)
        ids = ANOT.declarar(con, aid, agora=AGORA)
        ANOT.anotar_aqui(con, ids[0], assento_alvo_id=alvo, agora=AGORA,
                         usuario="mario")
    p = ANOT.pendencias_do_assento(con, aid)[0]
    assert p["situacao"] == ANOT.ANOTADA
    assert p["assento_alvo_id"] == alvo
    assert p["resolvida_por"] == "mario"


def test_o_modulo_nao_escreve_no_assento_alvo(casa):
    """Art. 370 — conferir a compatibilidade é do oficial. Um programa que
    anotasse sozinho estaria decidindo que dois assentos são da mesma pessoa."""
    con = _con(casa)
    with con:
        alvo = _assento(con, especie="NASCIMENTO", serie="RC_A", numero="100")
        antes = dict(con.execute("SELECT * FROM rc_assentos WHERE id=?",
                                 (alvo,)).fetchone())
        aid = _assento(con)
        ids = ANOT.declarar(con, aid, agora=AGORA)
        ANOT.anotar_aqui(con, ids[0], assento_alvo_id=alvo, agora=AGORA)
    depois = dict(con.execute("SELECT * FROM rc_assentos WHERE id=?",
                              (alvo,)).fetchone())
    assert antes == depois, "o módulo mexeu no assento alvo, e não devia"


# ------------------------------------------------ comunicar


def test_a_comunicacao_exige_protocolo(casa):
    """A norma pede confirmação de recebimento — comunicação sem confirmação é
    a que ninguém prova ter mandado."""
    con = _con(casa)
    with con:
        aid = _assento(con)
        ids = ANOT.declarar(con, aid, agora=AGORA)
    with con, pytest.raises(ANOT.AnotacaoError) as erro:
        ANOT.comunicar(con, ids[0], canal="CRC", serventia="1º Ofício",
                       protocolo="", agora=AGORA)
    assert "confirmação de recebimento" in str(erro.value)


def test_a_comunicacao_exige_a_serventia(casa):
    con = _con(casa)
    with con:
        aid = _assento(con)
        ids = ANOT.declarar(con, aid, agora=AGORA)
    with con, pytest.raises(ANOT.AnotacaoError) as erro:
        ANOT.comunicar(con, ids[0], canal="CRC", serventia="",
                       protocolo="123", agora=AGORA)
    assert "registro primitivo" in str(erro.value)


def test_o_canal_sai_da_norma(casa):
    con = _con(casa)
    with con:
        aid = _assento(con)
        ids = ANOT.declarar(con, aid, agora=AGORA)
    with con, pytest.raises(ANOT.AnotacaoError) as erro:
        ANOT.comunicar(con, ids[0], canal="WHATSAPP", serventia="X",
                       protocolo="1", agora=AGORA)
    assert "CRC" in str(erro.value)


def test_comunicar_guarda_o_caminho_inteiro(casa):
    con = _con(casa)
    with con:
        aid = _assento(con)
        ids = ANOT.declarar(con, aid, agora=AGORA)
        ANOT.comunicar(con, ids[0], canal="CRC",
                       serventia="1º Ofício de Imperatriz/MA",
                       protocolo="CRC-2026-0099", agora=AGORA, usuario="mario")
    p = ANOT.pendencias_do_assento(con, aid)[0]
    assert p["situacao"] == ANOT.COMUNICADA
    assert p["canal"] == "CRC"
    assert p["protocolo"] == "CRC-2026-0099"


# ------------------------------------------------ dispensar


def test_dispensar_exige_motivo_escrito(casa):
    """Dispensar é decisão do oficial; ignorar não é."""
    con = _con(casa)
    with con:
        aid = _assento(con)
        ids = ANOT.declarar(con, aid, agora=AGORA)
    with con, pytest.raises(ANOT.AnotacaoError) as erro:
        ANOT.dispensar(con, ids[0], motivo="não", agora=AGORA)
    assert "escreva o motivo" in str(erro.value).lower()


def test_dispensar_com_motivo_resolve(casa):
    con = _con(casa)
    with con:
        aid = _assento(con)
        ids = ANOT.declarar(con, aid, agora=AGORA)
        ANOT.dispensar(con, ids[0], motivo="o falecido nunca foi casado",
                       agora=AGORA)
    p = ANOT.pendencias_do_assento(con, aid)[0]
    assert p["situacao"] == ANOT.DISPENSADA
    assert "nunca foi casado" in p["motivo"]


def test_nao_se_resolve_duas_vezes(casa):
    con = _con(casa)
    with con:
        aid = _assento(con)
        ids = ANOT.declarar(con, aid, agora=AGORA)
        ANOT.dispensar(con, ids[0], motivo="o falecido nunca foi casado",
                       agora=AGORA)
    with con, pytest.raises(ANOT.AnotacaoError) as erro:
        ANOT.comunicar(con, ids[0], canal="CRC", serventia="X",
                       protocolo="1", agora=AGORA)
    assert "já está como" in str(erro.value)


# ------------------------------------------------ o prazo


def test_a_lista_vem_do_mais_antigo_para_o_mais_novo(casa):
    """É o contrário das outras listas do sistema, e é deliberado: aqui o que
    importa é o prazo."""
    con = _con(casa)
    with con:
        novo = _assento(con, numero="99", data_ato="2026-08-28")
        velho = _assento(con, numero="1", data_ato="2026-01-10")
        ANOT.declarar(con, novo, agora=AGORA)
        ANOT.declarar(con, velho, agora=AGORA)
    # PELO ASSENTO, E NAO PELO NUMERO. `rc_assentos.numero` e INTEGER, e o
    # SQLite converte "1" em 1 na entrada — a **quarta vez** que a afinidade
    # morde neste projeto. Comparar pelo id tira a ambiguidade: ele e a chave,
    # e nao um texto que o banco reescreve.
    lista = ANOT.pendentes(con)
    assert lista[0]["assento_id"] == velho


def test_fora_do_prazo_conta_dias_corridos(casa):
    con = _con(casa)
    with con:
        dentro = _assento(con, numero="10", data_ato="2026-08-27")
        fora = _assento(con, numero="11", data_ato="2026-08-01")
        ANOT.declarar(con, dentro, agora=AGORA)
        ANOT.declarar(con, fora, agora=AGORA)
    vencidas = ANOT.fora_do_prazo(con, hoje=HOJE)
    assert {x["assento_id"] for x in vencidas} == {fora}


def test_assento_sem_data_nao_entra_nas_vencidas(casa):
    """Sem data não dá para dizer que o prazo passou — e afirmar que passou
    seria pior que não afirmar nada."""
    con = _con(casa)
    with con:
        aid = _assento(con, data_ato=None)
        ANOT.declarar(con, aid, agora=AGORA)
    assert ANOT.fora_do_prazo(con, hoje=HOJE) == []
    assert ANOT.quantas_pendentes(con) == 2


# ------------------------------------------------ o resumo


def test_o_resumo_e_resumo_e_nao_o_teor(casa):
    """O art. 367 pede «resumo do assento». Mandar o teor a outra serventia é
    espalhar a qualificação de todo mundo, que ela não precisa para anotar."""
    con = _con(casa)
    with con:
        aid = _assento(con, teor="<p>O TEOR INTEIRO COM TODA A QUALIFICAÇÃO</p>",
                       matricula="0000000155202641000000310000031")
    resumo = ANOT.resumo_do_assento(con, aid)
    assert "OBITO" in resumo
    assert "31" in resumo
    assert "ANTONIO DA SILVA" in resumo
    assert "TEOR INTEIRO" not in resumo


# ------------------------------------------------ o módulo não decide


def test_o_modulo_nao_anota_nem_lavra():
    codigo = (RAIZ / "rc_anotacao.py").read_text(encoding="utf-8")
    assert "INSERT INTO rc_assentos" not in codigo
    assert "UPDATE rc_assentos" not in codigo
    publicos = [n for n in dir(ANOT)
                if not n.startswith("_") and callable(getattr(ANOT, n))]
    for nome in publicos:
        for proibido in ("lavrar", "numerar", "selar", "julgar"):
            assert proibido not in nome.lower(), f"`{nome}` faz o que não deve"
