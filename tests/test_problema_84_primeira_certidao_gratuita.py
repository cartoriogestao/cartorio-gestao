"""A PRIMEIRA CERTIDÃO GRATUITA DERRUBAVA A EMISSÃO DEPOIS DE GRAVAR — 18/09/2026.

    «ai deixou o sistema com um erro depois de emitir. ele emitiu, mas deu erro,
    ai emitir novamente. deu certo e cobrou os emolumentos. eis o problema»
                                        — o oficial, 18/09/2026 (problema #84)

O QUE ACONTECIA, medido na produção: assento **8283**, nascimento registrado
**nesta casa** em 18/09 às 09h05, com o selo do REGISTRO (`REGNAS…`) já no ato.

    1º clique → `UnboundLocalError: cannot access local variable
                 'recado_do_selo' where it is not associated with a value`

**A CERTIDÃO 57/2026 JÁ ESTAVA GRAVADA QUANDO O ERRO SUBIU**, e é isso que faz
este defeito ser caro: a exceção estoura **depois** do `with db.transaction()`,
na hora de decidir se o aparelho é chamado. Como ninguém chega à linha do
`audit`, **a certidão ficou sem uma linha de auditoria** — e sem a via gratuita,
que era o que o balcão tinha pedido.

    2º clique → como a 57 já existia ATIVA, a régua
                (`eh_primeira_certidao_do_registro`) disse «não é mais a
                primeira» → caminho PAGO → certidão 58 com `CERTID…` comprado.

**O ERRO NÃO PERDEU DINHEIRO: ELE COMPROU O SELO ERRADO.** A via gratuita usa o
selo do REGISTRO, e não custa nada; a segunda via compra `CERTID` e gasta folha
de segurança. O operador clicou duas vezes porque a tela disse «erro» sobre um
ato que tinha sido praticado — e a segunda tentativa cobrou.

A CAUSA, no código, é de uma linha: `recado_do_selo` só era atribuído no `else`
(2ª via), e o `if primeira:` caía direto no `_motivo_da_falha_do_selo(
recado_do_selo)`. As outras duas funções desta mesma casa que usam o mesmo
recado (`protesto_certidoes` e `protesto_lancar_ato`) **já o inicializavam com
`""` antes do `if`** — este caminho é que nasceu sem a inicialização.

O QUE ESTES TESTES PROVAM
    Que a emissão da 1ª certidão gratuita **volta para a ficha** (e não para uma
    página de erro), **sem comprar selo**, **sem gastar folha** e **com
    auditoria** — e que a segunda emissão do mesmo assento não é gratuita.

O QUE ELES NÃO PROVAM
    Que o aparelho aceita o selo isento. Nada aqui fala com a rede: a 1ª via
    não chama o selador (espelha o selo do registro), e é por isso que a
    ausência de `sd_selos` nestes testes é medição, e não falta de ensaio.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

M32 = "000000015520260900112700103859 0"
SELO_REGISTRO = "REGNAS000000PROBLEMA84X"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _con(casa) -> sqlite3.Connection:
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _assento_registrado_aqui(casa) -> int:
    """A forma do assento 8283: lavrado NESTA casa, com o REGNAS no registro.

    `origem='MANUAL'` (não é `EOFICIO`/`ARQUIVO`/`IMPORTACAO`) é o que separa
    este caso do ensaio de importado: aqui a 1ª via gratuita é a do registro,
    e não a segunda via paga.
    """
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, matricula, nome,
                   data_ato, data_fato, dados_json, situacao, origem,
                   criado_em)
               VALUES ('RC_A','NASCIMENTO',19553,?,'REGISTRADO HOJE DA SILVA',
                       '2026-09-18','2026-09-01','{"strSexo": "Masculino"}',
                       'ATIVO','MANUAL','2026-09-18T09:00:00')""",
            (M32,))
        aid = int(cur.lastrowid)
        cur = con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem,
                   rotulo, data_ato, selo, origem, criado_em)
               VALUES (?,'REGISTRO',154,19553,'154','2026-09-18',?,'MANUAL',
                       '2026-09-18T09:00:00')""",
            (aid, SELO_REGISTRO))
        registro_id = int(cur.lastrowid)
        # TESTE VELHO, ATUALIZADO EM 14/10/2026. Este arquivo é de 18/09 e
        # emitia a 1ª via SEM folha de segurança. Depois dele vieram duas
        # regras de propósito, as duas em `rcpn_certidao_emitir`:
        #   · relato #92 (22/09/2026, 3.6.240) — FOLHA OBRIGATÓRIA EM TODA
        #     EMISSÃO, inclusive a 1ª via: sem folha a rota recusa antes de
        #     emitir (e a certidão nem chegava a existir aqui);
        #   · FOLHA_DA_1A_VIA (09/10/2026) — a 1ª via sai na folha que o
        #     REGISTRO baixou e mandou ao TJMA no `papelMoeda`, amarrada sem
        #     baixa dupla.
        # O assento ganha, então, o que o registro desta casa tem hoje: a
        # folha 840001 USADA no ato de registro (e uma 840002 em branco na
        # gaveta, que a 1ª via não pode gastar).
        import papel_seguranca as PP
        PP.receber_remessa(con, fornecedor="ARPENBRASIL", serie="HA",
                           codigo_de="840001", codigo_ate="840002",
                           agora="2026-09-18T08:00:00", usuario="ENSAIO")
        PP.usar(con, "840001", tabela="rc_atos", ato_id=registro_id,
                agora="2026-09-18T09:00:00", selo=SELO_REGISTRO,
                usuario="ENSAIO")
        for papel, quem, ordem in (
                ("PAI", "JOSÉ DA SILVA", 1),
                ("MAE", "MARIA DAS GRAÇAS SILVA", 2)):
            con.execute(
                """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem,
                       origem, criado_em)
                   VALUES (?,?,?,?,'MANUAL','2026-09-18T09:00:00')""",
                (aid, papel, quem, ordem))
    con.close()
    return aid


def _emitir_a_gratuita(casa, aid: int):
    html = casa["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    return casa["c"].post(
        f"/rcpn/{aid}/certidao",
        data={"csrf_token": _token(html), "tipo_certidao": "resumo",
              "requerente": "O PRÓPRIO", "finalidade": "TESTE"},
        follow_redirects=True)


def _certidoes(casa, aid: int) -> list[dict]:
    con = _con(casa)
    linhas = [dict(x) for x in con.execute(
        """SELECT id, numero, ano, selo, cancelada_em, lancamento_id,
                  modalidade, emitida_em
             FROM rc_certidoes WHERE assento_id=? ORDER BY id""", (aid,))]
    con.close()
    return linhas


def _auditoria(casa, aid: int, acao: str) -> int:
    con = _con(casa)
    n = con.execute(
        """SELECT COUNT(*) FROM audit_logs l
            WHERE l.action=?
              AND l.entity_type='rc_certidoes'
              AND l.entity_id IN (SELECT id FROM rc_certidoes WHERE assento_id=?)""",
        (acao, aid)).fetchone()[0]
    con.close()
    return int(n)


# ============================================== o defeito #84, propriamente


def test_a_primeira_certidao_gratuita_emite_e_volta_para_a_ficha(cg_casa_logada):
    """**O clique que deu erro no balcão.** Antes do conserto esta rota
    estourava `UnboundLocalError` DEPOIS de gravar a certidão."""
    casa = cg_casa_logada
    aid = _assento_registrado_aqui(casa)
    r = _emitir_a_gratuita(casa, aid)
    assert r.status_code == 200, (
        f"a emissão da 1ª certidão gratuita não devolveu a ficha "
        f"(HTTP {r.status_code})")
    texto = r.get_data(as_text=True)
    assert "emitida" in texto.lower()
    assert "UnboundLocalError" not in texto

    linhas = _certidoes(casa, aid)
    assert len(linhas) == 1, "a 1ª via gratuita tem de sair UMA vez"
    certidao = linhas[0]
    assert certidao["selo"] == SELO_REGISTRO, (
        "a 1ª via usa o selo do REGISTRO, espelhado — não compra CERTID")
    assert certidao["cancelada_em"] is None
    assert certidao["lancamento_id"] is None


def test_a_primeira_certidao_gratuita_nao_compra_selo_nem_gasta_folha(
        cg_casa_logada):
    """O dinheiro e o papel do caso #84, medidos nos dois lados.

    Na produção o 2º clique (já no caminho pago) comprou um `CERTID`. Aqui se
    prova o inverso: **a via gratuita não fala com o aparelho e não consome
    folha de segurança** — se falasse, `sd_selos` teria linha; se consumisse,
    `pp_folhas` também.
    """
    casa = cg_casa_logada
    aid = _assento_registrado_aqui(casa)
    _emitir_a_gratuita(casa, aid)

    con = _con(casa)
    selos = con.execute(
        """SELECT COUNT(*) FROM sd_selos
            WHERE COALESCE(referencia,'') LIKE '%rc_certidoes%'""").fetchone()[0]
    # Desde 09/10/2026 a 1ª via sai na folha que o REGISTRO já baixou (ver
    # `_assento_registrado_aqui`): «não consome folha» passou a querer dizer
    # nenhuma baixa NOVA — a do registro continua no registro, e a da gaveta
    # continua em branco. Antes o teste contava `pp_folhas` vazia.
    folhas = {r["codigo"]: (r["situacao"], r["tabela"]) for r in con.execute(
        "SELECT codigo, situacao, tabela FROM pp_folhas")}
    con.close()
    assert len(_certidoes(casa, aid)) == 1, "a 1ª via gratuita não saiu"
    assert int(selos) == 0, "a 1ª via gratuita não pede selo ao aparelho"
    assert folhas == {"840001": ("USADA", "rc_atos"),
                      "840002": ("EM BRANCO", None)}, (
        "a 1ª via gratuita não pode baixar folha nova nem tirar a do registro")


def test_a_primeira_certidao_gratuita_deixa_auditoria(cg_casa_logada):
    """O 500 de 18/09 subiu ANTES do `audit`, e por isso a certidão 57 da
    produção ficou sem uma única linha de rastro."""
    casa = cg_casa_logada
    aid = _assento_registrado_aqui(casa)
    _emitir_a_gratuita(casa, aid)
    assert _auditoria(casa, aid, "RCPN_CERTIDAO") == 1
    assert _auditoria(casa, aid, "RCPN_CERTIDAO_NAO_EMITIDA_SELO_FALHOU") == 0


def test_a_segunda_certidao_do_mesmo_assento_nao_e_gratuita(cg_casa_logada):
    """**É o 2º clique do relato.** A gratuidade vale uma vez: com uma certidão
    ativa, a régua manda para a 2ª via — que sem folha escolhida é recusada
    antes de emitir, e não sai comprando selo calada."""
    casa = cg_casa_logada
    aid = _assento_registrado_aqui(casa)
    _emitir_a_gratuita(casa, aid)

    html = casa["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    r = casa["c"].post(f"/rcpn/{aid}/certidao",
                       data={"csrf_token": _token(html),
                             "tipo_certidao": "resumo"},
                       follow_redirects=True)
    assert len(_certidoes(casa, aid)) == 1, (
        "a 2ª emissão não pode sair como a 1ª — nem comprar selo sozinha")
    assert "folha de segurança" in r.get_data(as_text=True).lower()
