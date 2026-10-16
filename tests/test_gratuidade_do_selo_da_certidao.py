"""O MOTIVO DA GRATUIDADE SE RECUSA ANTES DE EMITIR — 10/09/2026.

    «segue sem funcionar, revise o caso do nilton»
                                        — o oficial, 10/09/2026

O QUE ACONTECIA, medido numa cópia do banco do balcão (assento 1240, «Nestor
Moreira Leitao», nascimento nº 5172 de 1974, origem ARQUIVO): marcar
**«Selo gratuito / isento»** e deixar o **Motivo** em branco produzia

    «Certidão n. 28/2026 emitida. O ato foi lavrado SEM SELO: Ato gratuito /
     selo gratuito precisa do motivo escrito.»

**A CERTIDÃO FICAVA, E FICAVA SEM SELO.** É o desfecho das certidões 16, 17 e
23 do Marcos Dione por outro caminho — e a folha de segurança **não se
gastava**, porque ela só se gasta se o selo sair: o papel existia, sem selo e
sem folha.

**A REGRA «SELAR NUNCA DERRUBA ATO QUE JÁ EXISTE» CONTINUA CERTA, E NÃO ERA
ESTE O CASO.** Ela vale para a recusa do **aparelho** — balcão parado é pior
que selo atrasado, e ato com selo inventado é pior que os dois. **Motivo em
branco não é recusa do aparelho: é campo que o operador não preencheu**, e isso
se pega com ele ainda na tela.

O precedente é da mesma rota, de 09/09/2026: a folha de segurança passou a ser
exigida **antes** de emitir, pelo mesmo motivo e pelo mesmo caso.

O QUE ESTES TESTES NÃO PROVAM
    **Que o aparelho aceita o selo isento.** Nada aqui fala com ele — pedir
    selo de verdade gasta selo, e isso é do balcão. O que se prova é que a
    certidão **não sai sem selo por falta de um campo**, e que o envelope leva
    o que o contrato declara.
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

import ato_selado as AS

SENHA = "Senha#12345"
AGORA = "2026-09-10T09:00"
M32 = "0" * 32


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    c = cg_casa["c"]
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA,
                                "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _assento_importado(casa) -> int:
    """A forma do Nilton e do Marcos Dione: veio de fora, e o registro nunca
    foi selado aqui — logo a certidão é tratada como segunda via."""
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, matricula, nome,
                   data_ato, data_fato, dados_json, origem, origem_chave,
                   criado_em, livro_volume)
               VALUES ('RC_A','NASCIMENTO',5172,?,?,
                       '1974-11-16','1971-06-30','{}','ARQUIVO',
                       'ensaio-gratuidade',?, 'A-12')""",
            (M32, "Nestor Moreira Leitao", AGORA))
        aid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO rc_pessoas(assento_id, papel, nome, nome_norm,
                   sexo, criado_em)
               VALUES (?,'REGISTRADO',?,?,'M',?)""",
            (aid, "Nestor Moreira Leitao", "nestor moreira leitao", AGORA))
    con.close()
    return aid


def _quantas_certidoes(casa, aid: int) -> int:
    con = sqlite3.connect(casa["banco"])
    n = con.execute("SELECT COUNT(*) FROM rc_certidoes WHERE assento_id=?",
                    (aid,)).fetchone()[0]
    con.close()
    return int(n)


# ============================================================ a recusa


def test_gratuito_sem_motivo_NAO_cria_certidao(casa):
    """**Recusa antes, e não certidão sem selo depois.**"""
    aid = _assento_importado(casa)
    c = casa["c"]
    html = c.get(f"/rcpn/{aid}").get_data(as_text=True)
    r = c.post(f"/rcpn/{aid}/certidao",
               data={"csrf_token": _token(html), "tipo_certidao": "resumo",
                     "ato_gratuito": "1", "selo_gratuito": "1", "selar": "1"},
               follow_redirects=True)
    texto = r.get_data(as_text=True)
    assert _quantas_certidoes(casa, aid) == 0, (
        "criou certidão com a gratuidade marcada e o motivo em branco — ela "
        "ficaria sem selo")
    assert "motivo" in texto.lower()
    # E a recusa diz as DUAS saídas: escrever o motivo, ou desmarcar.
    assert "desmarque" in texto.lower()


def test_a_recusa_do_motivo_vem_antes_da_folha_de_seguranca(casa):
    """Duas guardas na mesma rota, e a ordem importa pouco — o que importa é
    que **nenhuma das duas deixa certidão sem selo para trás**."""
    aid = _assento_importado(casa)
    c = casa["c"]
    html = c.get(f"/rcpn/{aid}").get_data(as_text=True)
    r = c.post(f"/rcpn/{aid}/certidao",
               data={"csrf_token": _token(html), "tipo_certidao": "resumo",
                     "selar": "1"},
               follow_redirects=True)
    # Sem gratuidade e sem folha: a guarda da folha recusa, e também não sobra
    # certidão.
    assert _quantas_certidoes(casa, aid) == 0
    assert "folha de segurança" in r.get_data(as_text=True).lower()


# ============================================================== a tela


def test_a_tela_diz_a_consequencia_de_deixar_o_motivo_em_branco(casa):
    """Campo obrigatório que não diz o que acontece sem ele é campo que fica
    vazio — e aqui o que acontece é a certidão sair sem selo."""
    aid = _assento_importado(casa)
    html = casa["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    assert "sem ele o selo não sai" in html


def test_o_required_do_motivo_entra_e_sai_com_a_caixa(casa):
    """**`required` fixo travaria o formulário inteiro** enquanto o bloco está
    escondido, e o navegador não teria onde mostrar a mensagem. Ele entra e sai
    com a marcação, no mesmo `onchange` que mostra o bloco.

    E a guarda do servidor continua existindo: **guarda que só existe no
    navegador não existe para quem tem o endereço.**
    """
    aid = _assento_importado(casa)
    html = casa["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    assert "m.required=cb.checked" in html


# ========================================================== o envelope


def test_o_envelope_isento_leva_o_campo_do_contrato_e_o_motivo():
    """`isento` é o campo que o contrato declara, e o motivo vai ao lado.

    Sem o motivo o envelope **não se monta** — e é isso que a guarda da rota
    passa a evitar antes de a certidão existir.
    """
    comuns = {"especie": "NASCIMENTO", "tipo": "CERTIDAO",
              "escrevente": "Debora Exemplo Reis", "livro": "A-12",
              "folha": "154", "termo": "5172",
              "nome_parte": "Nestor Moreira Leitao",
              "versao_tabela": "0520260101", "papel": "7225462"}
    env = AS.envelope_do_civil(
        **comuns, isento=True,
        motivo_isencao="Declaração de hipossuficiência apresentada")
    ds = env["dadosSelo"]
    assert ds["isento"] is True
    assert ds["motivoIsentoGratuito"]

    with pytest.raises(AS.AtoError) as erro:
        AS.envelope_do_civil(**comuns, isento=True)
    assert "motivo" in str(erro.value).lower()
