"""O ensaio de atos do Registro de Imóveis: as SEQUÊNCIAS na mesma matrícula, e as certidões depois delas.

O PEDIDO, do oficial (01/11/2026): «um teste que usasse todos botões e formulários do sistema para
simular todos atos possíveis previstos em lei ou nos códigos de normas […] e fizesse uma análise
crítica apurada sobre o resultado de saída.» O RI veio depois das Notas (03/11/2026).

O QUE ESTE TESTE FAZ
    `test_fluxo_ri` já leva cada um dos 25 modelos de ato da casa da prenotação paga à certidão, cada
    um numa matrícula limpa. Este pratica, pelas mesmas telas e com os mesmos passos (os auxiliares de
    lá), as SEQUÊNCIAS em que a certidão de propriedade e a de ônus podem errar: a venda com a hipoteca
    de pé, o cancelamento, a penhora, a indisponibilidade, o casal que adquire, o usufruto e a extinção.
    O inventário está em `docs/ensaio_de_atos/inventario_ri.md`, e o relatório em `relatorio_ri.md`.

OS DEFEITOS FICAM À VISTA: a asserção é a da lei; o defeito aberto fica em `xfail(strict=True)`.

Pessoas, imóveis e documentos fictícios (os CPF da lista dos fictícios).
"""
from __future__ import annotations

import json
import re

import pytest

import test_fluxo_ri as F
from test_fluxo_ri import casa  # noqa: F401 — a serventia do RI (fixture)

pytestmark = pytest.mark.lento

TERCEIRO = {"nome": "PAULO EXEMPLO TESTEMUNHA", "cpf": "00000000353", "cpf_fmt": "000.000.003-53",
            "qualificacao": ("brasileiro, solteiro, maior, motorista, residente e domiciliado na Rua "
                             "Exemplo, 30, Centro, Cidade Exemplo/MA")}
CONJUGE = {"nome": "LUCIA EXEMPLO TESTEMUNHA", "cpf": "00000001082", "cpf_fmt": "000.000.010-82",
           "qualificacao": ("brasileira, casada, maior, costureira, residente e domiciliada na Rua "
                            "Exemplo, 20, Centro, Cidade Exemplo/MA")}


def _defeito(motivo: str):
    return pytest.mark.xfail(strict=True, reason=f"DEFEITO: {motivo}")


def _ato(casa, m: dict, codigo: str, *, interessado: dict, partes=(), valores: dict | None = None,  # noqa: F811
         base: str = "100.000,00") -> dict:
    """Um ato do modelo `codigo` na matrícula `m`, pelo caminho inteiro do balcão: protocolo pago,
    prenotação para a matrícula, o texto do modelo preenchido como o balcão preenche, a lavratura."""
    import ri_modelos_atos as MOD
    modelo = MOD.por_codigo(codigo)
    tipo = modelo["tipo"]
    item = "16.3.14" if tipo == "R" else "16.22.2"
    cx = F._protocolo_geral(casa, interessado=interessado, itens=[("16.1", 1), (item, 1)])
    p = F._prenotar(casa, cx, apresentante=interessado, natureza=modelo["natureza"],
                    objeto=f"Matrícula {F.PRIMEIRA_MATRICULA}", matricula=str(F.PRIMEIRA_MATRICULA))
    r = casa["balcao"].get(f"/registro-imoveis/{m['id']}/modelo/{codigo}")
    teor = json.loads(r.get_data(as_text=True))["teor"]
    for marcador, valor in (valores or {}).items():
        teor = re.sub(re.escape("[" + marcador) + r"[^\]]*\]", lambda _m: valor, teor)
    teor, _ = F._como_o_balcao_preenche(teor)
    antes = F._um(casa, "SELECT coalesce(max(id), 0) AS n FROM ri_atos WHERE matricula_id=%s", (m["id"],))["n"]
    html = F._lavrar(casa, m, tipo=tipo, teor=teor, natureza=modelo["natureza"], prenotacao=p, cx=cx,
                     itens=[item], partes=list(partes), base_calculo=base if tipo == "R" else "",
                     modelo=codigo)
    ato = F._um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s AND id > %s ORDER BY id DESC LIMIT 1",
                (m["id"], antes))
    return {"ato": ato, "recado": html, "cx": cx}


def _onus_oferecidos(casa, m: dict) -> set[int]:  # noqa: F811
    """Os atos que a ficha oferece ao escrevente como ônus da certidão (`onus_item=ATO:<id>`)."""
    html = casa["balcao"].get(f"/registro-imoveis/{m['id']}").get_data(as_text=True)
    import os
    if os.environ.get("CG_ENSAIO_SAIDA"):
        for x in re.finditer(r'value="ATO:', html):
            print("OFERTA:", re.sub(r"\s+", " ", html[x.start() - 600:x.start() + 600]))
    return {int(x) for x in re.findall(r'value="ATO:(\d+)"', html)}


def _dono_na_certidao(casa, m: dict) -> str:  # noqa: F811
    cert = F._certidao(casa, m, "PROPRIEDADE", cx=F._pede_certidao(casa, itens=(("16.24.1", 1), ("16.24.2", 9))))
    atual = cert["papel"].split("PROPRIETÁRIO(S) ATUAL(IS):", 1)
    assert len(atual) == 2, f"a certidão não diz quem é o proprietário: {cert['papel'][:600]}"
    return atual[1].split(".", 1)[0]


# ------------------------------------------------------------------ a venda com a hipoteca de pé

def test_a_venda_com_a_hipoteca_de_pe_muda_o_dono_e_a_hipoteca_continua_onus(casa):  # noqa: F811
    """LRP art. 19, § 9º (o proprietário vigente) e CC art. 1.419 (a hipoteca segue o imóvel): depois da
    venda, o dono é o comprador novo — e a hipoteca do dono anterior continua sendo ônus da matrícula."""
    f = F._com_hipoteca(casa)
    m, r2 = f["matricula"], f["r2"]
    venda = _ato(casa, m, "R-COMPRA-VENDA", interessado=TERCEIRO,
                 partes=[(F.COMPRADORA, "transmitente"), (TERCEIRO, "adquirente")])
    assert venda["ato"] and venda["ato"]["selo_texto"], venda["recado"][:1200]
    dono = _dono_na_certidao(casa, m)
    assert TERCEIRO["nome"] in dono and F.COMPRADORA["nome"] not in dono, dono
    assert r2["id"] in _onus_oferecidos(casa, m)


@_defeito("o AV de cancelamento não se liga ao R que cancela (`ri_onus.classificar` só olha `ri_atos.cancelado`, "
          "que é o ato tornado sem efeito): depois do cancelamento, o pedido de certidão de ônus ainda vem com "
          "«Positiva» marcada e a hipoteca cancelada marcada para transcrição")
def test_a_hipoteca_cancelada_deixa_de_ser_onus(casa):  # noqa: F811
    """LRP arts. 248 e 250: a hipoteca cancelada por averbação não pesa mais na certidão de ônus."""
    f = F._com_hipoteca(casa)
    m, r2 = f["matricula"], f["r2"]
    cancela = _ato(casa, m, "AV-CANCELAMENTO-HIPOTECA", interessado=F.BANCO)
    assert cancela["ato"] and cancela["ato"]["selo_texto"], cancela["recado"][:1200]
    assert r2["id"] not in _onus_oferecidos(casa, m)


# ------------------------------------------------------------------ a penhora e a indisponibilidade

def test_a_penhora_averbada_e_onus(casa):  # noqa: F811
    """CPC art. 844 e LRP art. 167, I, 5 (e II, como o modelo da casa a lavra): a penhora averbada entra
    na certidão de ônus."""
    f = F._compra_e_venda(casa)
    m = f["matricula"]
    penhora = _ato(casa, m, "AV-PENHORA", interessado=F.COMPRADORA)
    assert penhora["ato"] and penhora["ato"]["selo_texto"], penhora["recado"][:1200]
    assert penhora["ato"]["id"] in _onus_oferecidos(casa, m)


@_defeito("a lavratura confere a indisponibilidade só na cópia local da CNIB, e não na própria matrícula: com "
          "a AV de indisponibilidade de pé (e a ficha mostrando-a como ônus), a venda vai ao livro com o recado "
          "«CNIB consultada e gravada no ato: nada consta»")
def test_a_indisponibilidade_averbada_e_onus_e_barra_a_venda(casa):  # noqa: F811
    """Prov. CNJ 149/2023 (a CNIB, como o modelo da casa a cita): a indisponibilidade averbada é ônus, e
    o imóvel indisponível não se aliena — a venda não vai ao livro sem o cancelamento dela."""
    f = F._compra_e_venda(casa)
    m = f["matricula"]
    indisponivel = _ato(casa, m, "AV-INDISPONIBILIDADE", interessado=F.COMPRADORA)
    assert indisponivel["ato"] and indisponivel["ato"]["selo_texto"], indisponivel["recado"][:1200]
    assert indisponivel["ato"]["id"] in _onus_oferecidos(casa, m)
    venda = _ato(casa, m, "R-COMPRA-VENDA", interessado=TERCEIRO,
                 partes=[(F.COMPRADORA, "transmitente"), (TERCEIRO, "adquirente")])
    assert not (venda["ato"] and venda["ato"]["natureza_titulo"] == "Compra e venda"), \
        "a venda de imóvel indisponível foi ao livro"


# ------------------------------------------------------------------ quem é o dono

def test_o_casal_que_compra_sai_inteiro_na_certidao_de_propriedade(casa):  # noqa: F811
    """LRP art. 176, § 1º, III, 2, e art. 19, § 9º: os dois adquirentes são proprietários."""
    f = F._compra_e_venda(casa)
    m = f["matricula"]
    venda = _ato(casa, m, "R-COMPRA-VENDA", interessado=TERCEIRO,
                 partes=[(F.COMPRADORA, "transmitente"), (TERCEIRO, "adquirente"), (CONJUGE, "adquirente")])
    assert venda["ato"] and venda["ato"]["selo_texto"], venda["recado"][:1200]
    dono = _dono_na_certidao(casa, m)
    assert TERCEIRO["nome"] in dono and CONJUGE["nome"] in dono and F.COMPRADORA["nome"] not in dono, dono



# ------------------------------------------------------------------ o usufruto

@_defeito("como no cancelamento da hipoteca, a AV de extinção não se liga ao R do usufruto — e ela mesma é "
          "oferecida como ônus (a palavra «usufruto» do teor; a natureza «Extinção de usufruto» não está na tabela)")
def test_o_usufruto_e_onus_e_extinto_deixa_de_ser(casa):  # noqa: F811
    """LRP art. 167, I, 7, e II, 2; CC art. 1.410: o usufruto registrado é ônus (direito real sobre coisa
    alheia); averbada a extinção, não é mais."""
    f = F._compra_e_venda(casa)
    m = f["matricula"]
    usufruto = _ato(casa, m, "R-USUFRUTO", interessado=F.COMPRADORA,
                    partes=[(F.COMPRADORA, "nu-proprietario"), (TERCEIRO, "usufrutuario")])
    assert usufruto["ato"] and usufruto["ato"]["selo_texto"], usufruto["recado"][:1200]
    assert usufruto["ato"]["id"] in _onus_oferecidos(casa, m)
    extinto = _ato(casa, m, "AV-EXTINCAO-USUFRUTO", interessado=F.COMPRADORA,
                   valores={"ATO DO USUFRUTO": f"R-{usufruto['ato']['numero']:02d}"})
    assert extinto["ato"] and extinto["ato"]["selo_texto"], extinto["recado"][:1200]
    oferecidos = _onus_oferecidos(casa, m)
    assert usufruto["ato"]["id"] not in oferecidos and extinto["ato"]["id"] not in oferecidos, oferecidos
