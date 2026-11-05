"""O ensaio de atos do Tabelionato de Protesto: as SITUAÇÕES do título e as SEQUÊNCIAS no mesmo devedor.

O PEDIDO, do oficial (01/11/2026): «um teste que usasse todos botões e formulários do sistema para
simular todos atos possíveis previstos em lei ou nos códigos de normas […] e fizesse uma análise
crítica apurada sobre o resultado de saída.» O Protesto vem depois do RI, na ordem do BRIEFING.

O QUE ESTE TESTE FAZ
    `test_fluxo_protesto` já leva cada ato do protocolo pago à certidão, sempre com o mesmo título: uma
    nota promissória, protesto comum por falta de pagamento, devedor pessoa física. Este pratica, pelas
    mesmas telas e com os mesmos auxiliares de lá, o que muda o ato: o motivo (falta de aceite), a
    espécie (cheque), o título apresentado duas vezes, o devedor pessoa jurídica, dois protestos do
    mesmo devedor e o cancelamento de um deles; na segunda leva, a falta de devolução e o título sustado.
    O inventário está em
    `docs/ensaio_de_atos/inventario_protesto.md`, e o relatório em `relatorio_protesto.md`.

OS DEFEITOS FICAM À VISTA: a asserção é a da lei; o defeito aberto fica em `xfail(strict=True)`.

Pessoas e documentos fictícios (os da lista dos fictícios).
"""
from __future__ import annotations

import pytest

import test_fluxo_protesto as F
from test_fluxo_protesto import s  # noqa: F401 — a serventia do Protesto (fixture)

pytestmark = pytest.mark.lento

EMPRESA = {"devedor_nome": "EMPRESA EXEMPLO LTDA", "devedor_documento_tipo": "CNPJ",
           "devedor_documento": "00000001000055"}
CNPJ_EMPRESA = "00.000.001/0000-55"


def _defeito(motivo: str):
    return pytest.mark.xfail(strict=True, reason=f"DEFEITO: {motivo}")


def _cadastrado(s, **mudar) -> tuple[int, list[str]]:  # noqa: F811
    """O título pelo balcão (`/protesto/novo`), devolvendo também o que a tela disse."""
    r = F._post(s, "/protesto/novo", "/protesto/novo", **{**F.TITULO, **mudar})
    avisos = F._avisos(r)
    assert any("cadastrado" in a for a in avisos), avisos
    return F._um(s, "SELECT id FROM pt_titulos ORDER BY id DESC LIMIT 1")["id"], avisos


def _ate_o_protesto(s, **mudar) -> dict:  # noqa: F811
    """Cadastro, apontamento, intimação em mãos e protesto, pela ficha — e tudo o que as telas disseram."""
    p = F._protocolo(s, F.PROTESTO, F.PROTESTO)
    tid, avisos = _cadastrado(s, **mudar)
    r = F._lancar(s, tid, "APONTAMENTO", p, p["itens"][0])
    avisos += F._avisos(r)
    if not F._lancado(r, "Apontamento"):
        return {"id": tid, "avisos": avisos, "situacao": F._situacao(s, tid)}
    F._intimado_em_maos(s, tid)
    r = F._lancar(s, tid, "PROTESTO", p, p["itens"][1])
    avisos += F._avisos(r)
    return {"id": tid, "avisos": avisos, "situacao": F._situacao(s, tid)}


def _emitir(s, *, nome: str, documento: str, **campos) -> dict:  # noqa: F811
    """A certidão pela tela, para quem se pede (a de `test_fluxo_protesto` é sempre a do devedor de lá)."""
    p = F._protocolo(s, F.CERTIDAO)
    antes = F._um(s, "SELECT max(id) AS m FROM pt_certidoes")["m"] or 0
    r = F._post(s, "/protesto/certidoes/emitir", "/protesto/certidoes", nome=nome, documento=documento,
                anos="5", protocolo_id=str(p["id"]), protocolo_item_id=str(p["itens"][0]), **campos)
    assert any("emitida" in a for a in F._avisos(r)), F._avisos(r)
    return F._um(s, "SELECT * FROM pt_certidoes WHERE id > %s ORDER BY id", (antes,))


# ------------------------------------------------------------------ o título apresentado duas vezes

def test_o_mesmo_titulo_nao_se_protesta_duas_vezes(s):  # noqa: F811
    """Lei 9.492/1997, art. 9º (o tabelião examina os caracteres formais do título); o vocabulário da CRA
    tem a recusa: «Título já protestado» (53). Decisão do oficial, 03/11/2026 («g1»; CONSERTADO): com o
    mesmo título PROTESTADO, o segundo não se aponta, e a ficha diz por quê antes do clique."""
    primeiro = _ate_o_protesto(s)
    assert primeiro["situacao"] == "PROTESTADO", primeiro["avisos"]
    p = F._protocolo(s, F.PROTESTO)
    segundo, _ = _cadastrado(s)
    ficha = s["c"].get(f"/protesto/{segundo}").get_data(as_text=True)
    assert "Este título já está nesta casa" in ficha and "protestado" in ficha, "a ficha não avisa"
    r = F._lancar(s, segundo, "APONTAMENTO", p, p["itens"][0])
    assert F._situacao(s, segundo) == "RECEBIDO", F._avisos(r)
    assert any("PROTESTADO" in a and "art. 9º" in a for a in F._avisos(r)), F._avisos(r)


def test_o_mesmo_titulo_so_apontado_se_aponta_de_novo_afirmando(s):  # noqa: F811
    """A outra metade de «g1» (decisão do oficial, 03/11/2026): o mesmo título só APONTADO pode ser a
    reapresentação de um título retirado — o segundo apontamento pede a afirmação expressa, e ela vai à
    auditoria com o nome de quem afirmou (`afirmacoes_expressas`, o contrato comum da casa)."""
    p = F._protocolo(s, F.PROTESTO, F.PROTESTO)
    primeiro, _ = _cadastrado(s, numero_titulo="NP-0031")
    assert F._lancado(F._lancar(s, primeiro, "APONTAMENTO", p, p["itens"][0]), "Apontamento")
    segundo, _ = _cadastrado(s, numero_titulo="NP-0031")
    r = F._lancar(s, segundo, "APONTAMENTO", p, p["itens"][1])
    assert F._situacao(s, segundo) == "RECEBIDO" and any("duplicidade" in a for a in F._avisos(r)), F._avisos(r)
    r = F._lancar(s, segundo, "APONTAMENTO", p, p["itens"][1], afirmo_dobrado="1",
                  afirmacao_dobrado="o credor retirou o primeiro por engano e o reapresentou no mesmo dia.")
    assert F._lancado(r, "Apontamento"), F._avisos(r)
    log = F._um(s, """SELECT details FROM audit_logs WHERE action='AFIRMACAO_EXPRESSA'
                       AND entity_type='pt_titulos' AND entity_id=%s ORDER BY id DESC LIMIT 1""", (segundo,))
    assert log and "PROTESTO_TITULO_EM_DUPLICIDADE" in str(log["details"]), log


# ------------------------------------------------------------------ o motivo e a espécie

@pytest.mark.parametrize("motivo,por_extenso", [("2", "FALTA DE ACEITE"), ("3", "FALTA DE DEVOLU")])
def test_depois_do_vencimento_o_protesto_e_sempre_por_falta_de_pagamento(s, motivo, por_extenso):  # noqa: F811
    """Lei 9.492/1997, art. 21, § 1º: o protesto por falta de aceite «somente poderá ser efetuado antes do
    vencimento da obrigação»; § 2º: depois do vencimento, «o protesto sempre será efetuado por falta de
    pagamento». O § 3º (a falta de devolução) só muda a base do protesto — a segunda via, as indicações —,
    e não a regra do § 2º. O título do balcão vence em 10/02/2025: o protesto se lavra por falta de
    pagamento, e a tela avisa a troca (decisão do oficial, 03/11/2026, «h2»; CONSERTADO)."""
    feito = _ate_o_protesto(s, especie="DMI", numero_titulo=f"DMI-000{motivo}", motivo_protesto=motivo)
    assert feito["situacao"] == "PROTESTADO", feito["avisos"]
    ato = F._ato(s, feito["id"], "PROTESTO")
    termo = (ato["teor"] or "").upper()
    assert por_extenso not in termo and "FALTA DE PAGAMENTO" in termo, termo
    assert any("POR FALTA DE PAGAMENTO" in a and "art. 21, § 2º" in a for a in feito["avisos"]), feito["avisos"]
    import json
    assert json.loads(ato["detalhe_json"])["motivo_trocado"]["de"] == motivo


def test_antes_do_vencimento_a_falta_de_aceite_fica(s):  # noqa: F811
    """O outro lado da régua: a duplicata que ainda não venceu se protesta por falta de aceite, como o
    cadastro diz, e sem aviso de troca (Lei 9.492/1997, art. 21, § 1º)."""
    feito = _ate_o_protesto(s, especie="DMI", numero_titulo="DMI-0099", motivo_protesto="2",
                            data_vencimento="2099-12-31")
    assert feito["situacao"] == "PROTESTADO", feito["avisos"]
    termo = (F._ato(s, feito["id"], "PROTESTO")["teor"] or "").upper()
    assert "FALTA DE ACEITE" in termo, termo
    assert not any("POR FALTA DE PAGAMENTO" in a for a in feito["avisos"]), feito["avisos"]


# O CHEQUE, DEPOIS DA DECISÃO DO OFICIAL (05/11/2026, «i» e «u»): a casa recebe cheque. Banco sacado,
# motivo da devolução e data da apresentação são obrigatórios (Lei 9.492/1997, art. 6º; CN-MA art. 910),
# salvo o protesto para instruir medida contra o próprio banco; os motivos 20, 25, 28, 30 e 35 se recusam
# (art. 883, § 1º) — mesmo com endosso ou aval, por ora; e o cheque de mais de um ano pede o endereço do
# emitente (§ 5º).
CHEQUE = {"especie": "CH", "cheque_banco_sacado": "Banco Exemplo S.A.", "cheque_motivo_devolucao": "11",
          "cheque_apresentado_em": "2025-02-12"}


def _recusado(s, recado: str, **mudar):  # noqa: F811
    antes = F._um(s, "SELECT count(*) AS n FROM pt_titulos")["n"]
    r = F._post(s, "/protesto/novo", "/protesto/novo", **{**F.TITULO, **mudar})
    assert any(recado in a for a in F._avisos(r)), F._avisos(r)
    assert F._um(s, "SELECT count(*) AS n FROM pt_titulos")["n"] == antes


def test_o_cheque_pede_a_prova_da_apresentacao_ao_banco(s):  # noqa: F811
    """Lei 9.492/1997, art. 6º; CN-MA art. 910: sem a apresentação ao banco sacado, o cheque não entra."""
    _recusado(s, "a data da apresentação ao banco", especie="CH", numero_titulo="CH-0005",
              cheque_banco_sacado="Banco Exemplo S.A.", cheque_motivo_devolucao="11")
    _recusado(s, "falta o banco sacado, o motivo da devolução", especie="CH", numero_titulo="CH-0005")


def test_o_cheque_com_a_apresentacao_vai_ao_protesto_e_a_ficha_a_diz(s):  # noqa: F811
    feito = _ate_o_protesto(s, numero_titulo="CH-0006", **CHEQUE)
    assert feito["situacao"] == "PROTESTADO", feito["avisos"]
    ficha = s["c"].get(f"/protesto/{feito['id']}").get_data(as_text=True)
    assert "Banco sacado: Banco Exemplo S.A. — devolvido pelo motivo 11, apresentado em 2025-02-12" in ficha


@pytest.mark.parametrize("motivo", ["20", "25", "28", "30", "35"])
def test_o_cheque_furtado_ou_extraviado_nao_se_aponta(s, motivo):  # noqa: F811
    """CN-MA art. 883, § 1º, e art. 911 (CNN art. 390). A exceção do endosso e do aval (§§ 2º e 3º) não está
    no sistema, e a recusa o diz."""
    _recusado(s, "essa exceção ainda não está no sistema",
              **{**CHEQUE, "numero_titulo": f"CH-1{motivo}", "cheque_motivo_devolucao": motivo})


def test_o_protesto_contra_o_proprio_banco_dispensa_a_apresentacao(s):  # noqa: F811
    tid, _ = _cadastrado(s, especie="CH", numero_titulo="CH-0007", cheque_contra_o_banco="1")
    t = F._um(s, "SELECT * FROM pt_titulos WHERE id=%s", (tid,))
    assert t["cheque_contra_o_banco"] == 1 and t["cheque_banco_sacado"] is None


def test_o_cheque_de_mais_de_um_ano_pede_o_endereco_do_emitente(s):  # noqa: F811
    """CN-MA art. 883, § 5º: avisa, e não barra."""
    _, avisos = _cadastrado(s, numero_titulo="CH-0008", **CHEQUE)
    assert any("comprovar o endereço do emitente" in a for a in avisos), avisos
    recente = (F.date.fromisoformat(F._hoje(s)) - F.timedelta(days=30)).isoformat()
    _, avisos = _cadastrado(s, numero_titulo="CH-0009", **{**CHEQUE, "data_emissao": recente,
                                                           "cheque_apresentado_em": recente})
    assert not any("comprovar o endereço do emitente" in a for a in avisos), avisos


# ------------------------------------------------------------------ o devedor e a certidão

def test_dois_protestos_do_mesmo_devedor_cancelado_um_a_certidao_traz_so_o_outro(s):  # noqa: F811
    """Lei 9.492/1997, arts. 26 e 27; CN-MA arts. 944 e 948: cancelado um dos dois protestos, a certidão a
    terceiro é POSITIVA e traz só o que está em pé."""
    primeiro = _ate_o_protesto(s, numero_titulo="NP-0011", valor="1.111,11", saldo="1.111,11")
    segundo = _ate_o_protesto(s, numero_titulo="NP-0012", valor="2.222,22", saldo="2.222,22")
    assert primeiro["situacao"] == segundo["situacao"] == "PROTESTADO"
    p = F._protocolo(s, F.CANCELAMENTO)
    r = F._lancar(s, primeiro["id"], "CANCELAMENTO", p, p["itens"][0], hipotese="ANUENCIA_CREDOR",
                  fundamento="Carta de anuência do credor, com firma reconhecida.")
    assert F._lancado(r), F._avisos(r)
    cert = _emitir(s, nome=F.DEVEDOR, documento=F.CPF_DEVEDOR)
    assert cert["tipo"] == "POSITIVA", cert
    assert "2.222,22" in cert["teor"] and "1.111,11" not in cert["teor"], cert["teor"]


def test_a_empresa_devedora_sai_na_certidao_pelo_cnpj(s):  # noqa: F811
    """Lei 9.492/1997, art. 27, e CNN art. 259: a certidão se pede pelo nome e pelo documento. Protestada a
    empresa, a certidão pelo CNPJ dela é POSITIVA; a do sócio que tem outro documento, não."""
    feito = _ate_o_protesto(s, numero_titulo="NP-0021", **EMPRESA)
    assert feito["situacao"] == "PROTESTADO", feito["avisos"]
    cert = _emitir(s, nome=EMPRESA["devedor_nome"], documento=CNPJ_EMPRESA)
    assert cert["tipo"] == "POSITIVA" and EMPRESA["devedor_nome"] in cert["teor"], cert
    outro = _emitir(s, nome=F.DEVEDOR, documento=F.CPF_DEVEDOR)
    assert outro["tipo"] == "NEGATIVA", outro


# ------------------------------------------------------------------ o título sustado

def _sustado(s) -> tuple[int, dict]:  # noqa: F811
    p = F._protocolo(s, F.PROTESTO, F.RETIRADA)
    tid = F._apontado(s, p, p["itens"][0])
    F._intimado_em_maos(s, tid)
    r = F._lancar(s, tid, "SUSTACAO", juizo="1ª Vara Cível de Cidade Exemplo",
                  processo="0800001-00.2026.8.10.0001", recebido_em=F._hoje(s))
    assert F._lancado(r), F._avisos(r)
    return tid, p


@pytest.mark.parametrize("ato,campos", [
    ("PAGAMENTO", {"valor_pago": "1.234,56", "emolumentos": "30,00", "forma_pagamento": "TRANSFERENCIA",
                   "forma_identificacao": "TED 0002"}),
    ("DESISTENCIA", {"motivo": "O credor desistiu, por escrito."}),
])
def test_o_titulo_sustado_nao_se_paga_nem_se_retira_sem_ordem_do_juiz(s, ato, campos):  # noqa: F811
    """Lei 9.492/1997, art. 17, § 1º: o título cujo protesto foi sustado judicialmente «só poderá ser pago,
    protestado ou retirado com autorização judicial». O protesto já é barrado (`test_fluxo_protesto`); o
    pagamento e a retirada também têm de ser."""
    tid, p = _sustado(s)
    r = F._lancar(s, tid, ato, p, p["itens"][1], **campos)
    # O EFEITO, E NÃO A PALAVRA: a recusa também diz «lançado» («não pode ser lançado aqui»).
    feitos = F._ler(s, "SELECT id FROM pt_atos WHERE titulo_id=%s AND tipo=%s AND cancelado=0", (tid, ato))
    assert not feitos and F._situacao(s, tid) == "INTIMADO", F._avisos(r)
    assert any("art. 17" in a or "SUSTADO" in a for a in F._avisos(r)), F._avisos(r)
    # E O RECADO CONCORDA COM O ATO (observação O6): «a desistência não pode ser lançada».
    esperado = {"PAGAMENTO": "o pagamento não pode ser lançado", "DESISTENCIA": "a desistência não pode ser lançada"}
    assert any(esperado[ato] in a for a in F._avisos(r)), F._avisos(r)


# ------------------------------------------------------------------ o falimentar por edital

def test_o_protesto_falimentar_por_edital_pede_a_afirmacao_de_que_a_procura_se_esgotou(s):  # noqa: F811
    """A CRA recusa o protesto falimentar intimado por edital (irregularidade 69), e a Súmula 361 do STJ
    exige a identificação de quem recebeu a intimação; a jurisprudência o admite quando a empresa não é
    achada. Decisão do oficial, 03/11/2026 («k»): avisar e pedir a afirmação de que a procura se esgotou —
    e ela vai à auditoria. O protesto comum por edital não pede nada disso."""
    import io
    p = F._protocolo(s, F.PROTESTO, F.PROTESTO)
    tid = F._apontado(s, p, p["itens"][0], numero_titulo="NP-0041", tipo_protesto="F", **EMPRESA)
    aviso = F._aviso(s, tid)
    F._post(s, f"/protesto/avisos/{aviso['id']}/entrega", "/protesto/avisos", entregue="0", motivo="1",
            quando=F._hoje(s))
    r = F._post(s, f"/protesto/avisos/{aviso['id']}/edital", "/protesto/avisos",
                justificativa="Devedora mudou-se e não há outro endereço conhecido.")
    assert any("intimação por edital foi lavrada" in a for a in F._avisos(r)), F._avisos(r)
    F._post(s, "/protesto/editais/comprovante-cenprot", "/protesto/avisos", dia=F._hoje(s),
            comprovante=(io.BytesIO(F.PDF_DO_CANHOTO + b" envio a CENPROT"), "envio-cenprot.pdf"))
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert 'name="afirmo_falimentar"' in ficha, "a ficha não pede a afirmação"
    r = F._lancar(s, tid, "PROTESTO", p, p["itens"][1])
    assert F._situacao(s, tid) == "INTIMADO", F._avisos(r)
    assert any("FALIMENTARES" in a and "Súmula 361" in a for a in F._avisos(r)), F._avisos(r)
    r = F._lancar(s, tid, "PROTESTO", p, p["itens"][1], afirmo_falimentar="1",
                  afirmacao_falimentar="a devedora foi procurada na sede, na filial e no endereço da Receita, sem achá-la.")
    assert F._lancado(r, "Protesto"), F._avisos(r)
    log = F._um(s, """SELECT details FROM audit_logs WHERE action='AFIRMACAO_EXPRESSA'
                       AND entity_type='pt_titulos' AND entity_id=%s ORDER BY id DESC LIMIT 1""", (tid,))
    assert log and "PROTESTO_FALIMENTAR_POR_EDITAL" in str(log["details"]), log


# ------------------------------------------------------------------ a frase do pagamento a posteriori

FRASE_POSTERIORI = "registrado com o procedimento de pagamento a posteriori"


@pytest.mark.parametrize("vencimento,diferido", [("2025-02-10", False), ("2026-10-01", True)])
def test_a_frase_do_pagamento_a_posteriori_so_sai_no_diferido(s, vencimento, diferido):  # noqa: F811
    """CN-MA art. 925, §§ 11 e 12: o emolumento a posteriori é do título DIFERIDO — o de qualquer pessoa,
    se o vencimento não passa de um ano na apresentação (§ 12, II). Decisão do oficial, 03/11/2026 («l»):
    a frase «Os emolumentos serão pagos pelo devedor no ato do cancelamento» vira marcador e sai só no
    diferido. O título do balcão vencido em 2025 é antecipado (pago no protocolo): sem a frase."""
    import protesto_posteriori as POSTERIORI
    feito = _ate_o_protesto(s, numero_titulo=f"NP-07{int(diferido)}", data_vencimento=vencimento)
    assert feito["situacao"] == "PROTESTADO", feito["avisos"]
    with s["db"].connect() as con:
        assert (POSTERIORI.regime(con, feito["id"])["regime"] == "DIFERIDO") is diferido
    termo = F._ato(s, feito["id"], "PROTESTO")["teor"] or ""
    assert (FRASE_POSTERIORI in termo) is diferido, termo


# ------------------------------------------------------------------ o título em moeda estrangeira

def test_o_titulo_em_moeda_estrangeira_guarda_a_origem_e_cobra_em_reais(s):  # noqa: F811
    """Lei 9.492/1997, art. 10. Decisão do oficial, 05/11/2026 («j»): a casa recebe o título em moeda
    estrangeira; a ficha guarda a moeda e o valor de origem, e o valor em REAIS é obrigatório — é o
    convertido, o que se cobra e se intima. Até a decisão, o sistema só conhecia o real (observação O3)."""
    tid, _ = _cadastrado(s, numero_titulo="NP-USD1", moeda_estrangeira="dólar americano (USD)",
                         valor_na_moeda="1.000,00", valor="5.432,10", saldo="5.432,10")
    t = F._um(s, "SELECT * FROM pt_titulos WHERE id=%s", (tid,))
    assert (t["moeda_estrangeira"], t["valor_na_moeda"]) == ("dólar americano (USD)", "1.000,00")
    assert t["valor_centavos"] == 543210 and t["saldo_centavos"] == 543210
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "convertido de 1.000,00 — dólar americano (USD)" in ficha


@pytest.mark.parametrize("mudar,recado", [
    ({"moeda_estrangeira": "euro (EUR)"}, "informe a moeda e o valor na moeda de origem"),
    ({"valor_na_moeda": "1.000,00"}, "informe a moeda e o valor na moeda de origem"),
    ({"moeda_estrangeira": "euro (EUR)", "valor_na_moeda": "mil"}, "não é um número"),
    ({"moeda_estrangeira": "euro (EUR)", "valor_na_moeda": "1.000,00", "valor": "0,00", "saldo": "0,00"},
     "o valor e o saldo vão em REAIS"),
])
def test_o_titulo_em_moeda_estrangeira_incompleto_e_recusado(s, mudar, recado):  # noqa: F811
    antes = F._um(s, "SELECT count(*) AS n FROM pt_titulos")["n"]
    r = F._post(s, "/protesto/novo", "/protesto/novo", **{**F.TITULO, "numero_titulo": "NP-EUR1", **mudar})
    assert any(recado in a for a in F._avisos(r)), F._avisos(r)
    assert F._um(s, "SELECT count(*) AS n FROM pt_titulos")["n"] == antes
