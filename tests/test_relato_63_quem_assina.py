"""O relato #63 — o termo ia para o Livro SEM o nome de quem assina.

    «quando eu lavro o assento vejo que o texto do termo vai com espaços para
     preencher ... Eu, ____________, Oficial, dou fé e assino»
    — o oficial, 15/09/2026

**O DEFEITO ESTAVA NO CAMINHO, E NÃO NO MODELO.** O modelo do termo sempre teve
`{escrevente}` e `{funcao_do_escrevente}`, e `rc_termo.montar` sempre soube
preenchê-los. Quem lavra, porém, digita o teor no formulário — e o texto digitado
vai **direto** para `rc_assentos.teor`, sem passar por `montar`. O que não se
digita sai da máquina como traço, e o Livro fica sem dizer quem assinou.

**E A PRIMEIRA LEITURA DO TAMANHO ESTAVA ERRADA.** Procurando o traço em
qualquer lugar, davam 625 dos 1.181 assentos com teor; procurando a **moldura de
quem assina** — o pedaço que o modelo escreve imediatamente antes e depois do
claro —, são **624 do acervo** (a linha de assinatura de vinte e dois
underscores, onde quem assina é a mão) e **um** de verdade, o assento 8.266.

**O RELATO #65 DIZ A MESMA COISA PELO OUTRO LADO**: «não faz sentido escolher
quem assinou». O nome de quem assina não é campo de decisão do balcão — é a
regra viva de quem responde pela serventia (`_servent`), a mesma do cartão de
assinatura e da certidão do RI.

Estes testes guardam as três coisas que fazem o conserto valer:

1. **a lavratura grava o nome de quem assina**, pela rota de verdade;
2. **o traço de OUTRO campo fica onde está** — trocar o primeiro traço do papel
   poria o nome do escrevente no lugar do nome do registrado, e o papel ficaria
   com cara de certo;
3. **o que não se achou avisa**, em vez de passar calado: `str.replace` sem
   achar não estoura, e foi por isso que este defeito viveu escondido.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_da_casa as MODELOS                              # noqa: E402
import rc_termo as TERMO                                       # noqa: E402

TRACO = "____________"
QUEM_ASSINA = "MARIO EXEMPLO DOS SANTOS"
SERVENTIA = {"escrevente": QUEM_ASSINA, "funcao": "Tabelião"}

# O mínimo que a tela do nascimento cobra para lavrar.
NASCIMENTO = {
    "pessoa_nome": "CRIANÇA DA SILVA", "pessoa_sexo": "F",
    "data_fato": "2026-09-15", "local_fato_nome": "Hospital Municipal",
    "ibge_local": "1",                 # relato #130: o SIRC exige
    "filiacao1_nome": "MARIA DA SILVA", "filiacao2_nome": "IGNORADO",
    "declarante_nome": "MARIA DA SILVA",
}


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa_logada):
    """App/DB compartilhados do módulo (conftest), com o ADMIN logado."""
    return cg_casa_logada


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _semear_folha(casa) -> str:
    """Uma folha de segurança na gaveta — lavrar registro gasta papel."""
    con = _con(casa)
    codigo = "9999999"
    with con:
        con.execute(
            """INSERT INTO pp_remessas(fornecedor, codigo_de, codigo_ate,
                   quantas, recebida_em)
               VALUES ('TESTE', ?, ?, 1, '2026-09-15T00:00:00')""",
            (codigo, codigo))
        rid = con.execute(
            "SELECT id FROM pp_remessas ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]
        con.execute(
            "INSERT INTO pp_folhas(codigo, remessa_id, situacao, criada_em)"
            " VALUES (?,?,'EM BRANCO','2026-09-15T00:00:00')",
            (codigo, rid))
    con.close()
    return codigo


def _modelo_com_os_tracos(con, especie: str = "NASCIMENTO") -> str:
    """O texto do modelo como ele chega na tela: com traço onde não se sabe.

    É o que o escrevente tinha à frente em 15/09/2026 — a frase do livro já
    escrita e o traço no lugar do nome de quem assina.
    """
    chave = TERMO.MODELO_DA_ESPECIE.get(especie)
    assert chave, f"a espécie {especie} não tem modelo"
    corpo = MODELOS.corpo_de(con, chave)
    texto = corpo.replace("{escrevente}", TRACO)
    texto = texto.replace("{funcao_do_escrevente}", TRACO)
    # OS OUTROS MARCADORES VÊM PREENCHIDOS, como na tela (13/10/2026). Desde
    # 11/10 a conferência dos dados recusa termo com `{campo}` sobrando — é
    # marca de rascunho, e não vai ao livro. O que este teste prova é só o
    # traço de quem assina; o nome do registrado entra porque a conferência
    # também exige que ele esteja no termo.
    return re.sub(r"\{(\w+)\}",
                  lambda m: NASCIMENTO["pessoa_nome"] if m.group(1) == "nome"
                  else "", texto)


def _lavrar(casa, teor: str, **extra):
    """Lavra um nascimento pela rota, com o teor que se quer testar."""
    html = casa["c"].get("/rcpn/novo/nascimento").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "especie": "NASCIMENTO",
             "folha_seguranca": _semear_folha(casa), "teor": teor}
    dados.update(NASCIMENTO)
    dados.update(extra)
    r = casa["c"].post("/rcpn/novo/nascimento", data=dados,
                       follow_redirects=True)
    return r.get_data(as_text=True)


def _teor_gravado(casa) -> str:
    con = _con(casa)
    linha = con.execute(
        "SELECT teor FROM rc_assentos ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert linha is not None, "nada foi lavrado"
    return linha["teor"] or ""


# ------------------------------------------------- pela rota, como o balcao faz


def test_a_lavratura_grava_quem_assina_no_lugar_do_traco(casa):
    """O relato inteiro: o texto chega com traço e o Livro não pode ficar sem."""
    con = _con(casa)
    teor = _modelo_com_os_tracos(con)
    con.close()
    assert TRACO in teor, "o modelo do nascimento tem os dois claros da assinatura"

    _lavrar(casa, teor)
    gravado = _teor_gravado(casa)

    assert "Lido e achado conforme, o(a) declarante assina." in gravado
    assert f"Eu, {QUEM_ASSINA}, Tabelião" in gravado or (
        f"Eu, {QUEM_ASSINA}, Escrevente" in gravado), gravado[-400:]
    # E O TRAÇO NÃO PODE TER FICADO NO LUGAR DE QUEM ASSINA.
    assert f"Eu, {TRACO}" not in gravado
    assert "Lido e achado conforme, o(a) declarante assina. Eu, MARIO" in gravado


def test_o_traco_de_outro_campo_fica_onde_esta(casa):
    """Trocar o primeiro traço do papel poria o escrevente no lugar do registrado.

    O termo tem dois claros exigidos, e o do nome do registrado vem **antes** do
    de quem assina. `str.replace` no primeiro traço que aparecesse escreveria o
    nome do escrevente sobre o do registrado — e o papel continuaria com cara de
    certo.
    """
    con = _con(casa)
    chave = TERMO.MODELO_DA_ESPECIE["NASCIMENTO"]
    corpo = MODELOS.corpo_de(con, chave)
    # Assinatura JÁ PREENCHIDA, e o traço no lugar do nome do registrado.
    teor = corpo.replace("{escrevente}", QUEM_ASSINA)
    teor = teor.replace("{funcao_do_escrevente}", "Tabelião")
    teor = teor.replace("{nome}", TRACO)
    r = TERMO.completar_quem_assina(con, teor, especie="NASCIMENTO",
                                    serventia=SERVENTIA)
    con.close()

    assert r["mudou"] is False
    assert r["texto"] == teor, "o traço de outro campo foi mexido"
    assert TRACO in r["texto"]


def test_o_texto_do_acervo_com_a_linha_de_assinatura_nao_e_tocado(casa):
    """Os 624 do acervo: quem assina ali é a mão, e não o sistema.

    A linha de assinatura de vinte e dois underscores é do livro de papel, e os
    doze da casa **cabem dentro** dela. Procurar o traço em qualquer lugar
    acusaria os 624 como defeito — alarme que soa sempre é alarme que ninguém
    ouve.
    """
    con = _con(casa)
    teor = ("Aos quinze dias do mês de setembro de dois mil e vinte e seis, "
            "nesta cidade de Cidade Exemplo, compareceu o declarante. Em "
            "testemunho da verdade.\n______________________")
    r = TERMO.completar_quem_assina(con, teor, especie="NASCIMENTO",
                                    serventia=SERVENTIA)
    con.close()

    assert r["mudou"] is False
    assert r["texto"] == teor
    assert r.get("nao_achei") == [], "avisou sobre um traço que não é da assinatura"


def test_o_traco_que_nao_foi_achado_avisa_em_vez_de_passar_calado(casa):
    """`str.replace` sem achar não estoura — e foi por isso que durou escondido.

    **E O CASO PIOR É O MEIO.** Aqui o escrevente reescreveu a frase antes da
    assinatura («achado e conferido»), de modo que a moldura do modelo não casa
    exatamente com o texto: `{escrevente}` fica sem troca e `{funcao_do_…}` é
    trocado. **Metade da assinatura no Livro** — e a primeira versão do aviso só
    olhava o caso em que **nada** tinha sido trocado, e ficava calada neste.
    """
    con = _con(casa)
    teor = _modelo_com_os_tracos(con).replace("achado conforme",
                                              "achado e conferido")
    con.close()

    con = _con(casa)
    r = TERMO.completar_quem_assina(con, teor, especie="NASCIMENTO",
                                    serventia=SERVENTIA)
    con.close()

    assert r["nao_achei"] == ["escrevente"], r
    assert TRACO in r["texto"], "o traço de quem assina ficou no texto"
    assert "Tabelião" in r["texto"], "o outro claro não devia ficar pendente"


def test_a_tela_avisa_quando_o_traco_de_quem_assina_nao_foi_achado(casa):
    """O aviso chega ao balcão, e não só ao teste do domínio."""
    con = _con(casa)
    teor = _modelo_com_os_tracos(con).replace("achado conforme",
                                              "achado e conferido")
    con.close()

    html = _lavrar(casa, teor)

    assert "SEM o nome de quem assina" in html
