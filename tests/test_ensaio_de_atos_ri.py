"""O ensaio de atos do Registro de Imóveis: as SEQUÊNCIAS na mesma matrícula, e as certidões depois delas.

O PEDIDO, do oficial (01/11/2026): «um teste que usasse todos botões e formulários do sistema para
simular todos atos possíveis previstos em lei ou nos códigos de normas […] e fizesse uma análise
crítica apurada sobre o resultado de saída.» O RI veio depois das Notas (03/11/2026).

O QUE ESTE TESTE FAZ
    `test_fluxo_ri` já leva cada um dos modelos de ato da casa da prenotação paga à certidão, cada
    um numa matrícula limpa. Este pratica, pelas mesmas telas e com os mesmos passos (os auxiliares de
    lá), as SEQUÊNCIAS em que a certidão de propriedade e a de ônus podem errar: a venda com a hipoteca
    de pé, o cancelamento, a penhora, a indisponibilidade, o casal que adquire, o usufruto e a extinção;
    na segunda leva, a prioridade entre prenotações, a partilha e o desmembramento; na terceira, a doação
    com reserva de usufruto, o indicador pessoal, a DOI e a arrematação.
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

HERDEIRO = {"nome": "MARCOS EXEMPLO FILHO", "cpf": "00000001163", "cpf_fmt": "000.000.011-63",
            "qualificacao": ("brasileiro, solteiro, maior, estudante, residente e domiciliado na Rua "
                             "Exemplo, 40, Centro, Cidade Exemplo/MA")}
HERDEIRA = {"nome": "JULIA EXEMPLO FILHA", "cpf": "00000001244", "cpf_fmt": "000.000.012-44",
            "qualificacao": ("brasileira, solteira, maior, enfermeira, residente e domiciliada na Rua "
                             "Exemplo, 50, Centro, Cidade Exemplo/MA")}


def _defeito(motivo: str):
    return pytest.mark.xfail(strict=True, reason=f"DEFEITO: {motivo}")


def _ato(casa, m: dict, codigo: str, *, interessado: dict, partes=(), valores: dict | None = None,  # noqa: F811
         base: str = "100.000,00", de_novo: dict | None = None, **extra) -> dict:
    """Um ato do modelo `codigo` na matrícula `m`, pelo caminho inteiro do balcão: protocolo pago,
    prenotação para a matrícula, o texto do modelo preenchido como o balcão preenche, a lavratura."""
    import ri_modelos_atos as MOD
    modelo = MOD.por_codigo(codigo)
    tipo = modelo["tipo"]
    item = "16.3.14" if tipo == "R" else "16.22.2"
    if de_novo:
        # O MESMO TÍTULO, DE NOVO: a lavratura recusada antes do número deixa a prenotação e o item do
        # protocolo como estavam, e o balcão lavra outra vez por eles — e não por uma prenotação nova, que
        # viria depois da dele (a prioridade, «d1»).
        cx, p = de_novo["cx"], de_novo["prenotacao"]
    else:
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
                     modelo=codigo, **extra)
    ato = F._um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s AND id > %s ORDER BY id DESC LIMIT 1",
                (m["id"], antes))
    return {"ato": ato, "recado": html, "cx": cx, "prenotacao": p}


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


def test_a_hipoteca_cancelada_deixa_de_ser_onus(casa):  # noqa: F811
    """LRP arts. 248 e 250: a hipoteca cancelada por averbação não pesa mais na certidão de ônus."""
    f = F._com_hipoteca(casa)
    m, r2 = f["matricula"], f["r2"]
    # SEM DIZER QUAL ATO, o modelo não lavra (decisão do oficial, 03/11/2026, «a1»; CONSERTADO).
    sem_alvo = _ato(casa, m, "AV-CANCELAMENTO-HIPOTECA", interessado=F.BANCO)
    assert not sem_alvo["ato"], "o cancelamento sem «qual ato se cancela» foi ao livro"
    assert "Qual ato se cancela" in _avisos(sem_alvo["recado"]), _avisos(sem_alvo["recado"])
    cancela = _ato(casa, m, "AV-CANCELAMENTO-HIPOTECA", interessado=F.BANCO, cancela_ato_id=str(r2["id"]),
                   de_novo=sem_alvo)
    assert cancela["ato"] and cancela["ato"]["selo_texto"], _avisos(cancela["recado"])
    marcado = F._um(casa, "SELECT cancelado, cancelado_por_ato_id FROM ri_atos WHERE id=%s", (r2["id"],))
    assert marcado["cancelado"] == 1 and marcado["cancelado_por_ato_id"] == cancela["ato"]["id"], marcado
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
    # O RECADO DIZ POR QUÊ (decisão do oficial, 03/11/2026, «b1»; CONSERTADO).
    assert "INDISPONIBILIDADE averbada" in _avisos(venda["recado"]), _avisos(venda["recado"])


def test_a_arrematacao_do_imovel_indisponivel_se_lavra_com_aviso(casa):  # noqa: F811
    """A outra metade de «b1» (decisão do oficial, 03/11/2026): a indisponibilidade não impede o ato judicial
    — a arrematação vai ao livro, e a tela avisa que a matrícula tem a indisponibilidade averbada."""
    f = F._compra_e_venda(casa)
    m = f["matricula"]
    _ato(casa, m, "AV-INDISPONIBILIDADE", interessado=F.COMPRADORA)
    arrematacao = _ato(casa, m, "R-ARREMATACAO", interessado=TERCEIRO,
                       partes=[(F.COMPRADORA, "transmitente"), (TERCEIRO, "adquirente")])
    assert arrematacao["ato"] and arrematacao["ato"]["natureza_titulo"] == "Arrematação", \
        _avisos(arrematacao["recado"])
    assert "INDISPONIBILIDADE averbada" in _avisos(arrematacao["recado"]), _avisos(arrematacao["recado"])


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



def test_depois_do_casamento_a_certidao_de_propriedade_diz_a_qualificacao_atual(casa):  # noqa: F811
    """Decisão do oficial (05/11/2026, item c): a certidão de propriedade traz a qualificação ATUAL do
    titular, estado civil inclusive — quem a pede quer saber se precisa da outorga conjugal (CC art.
    1.647). A AV de casamento traz a dona com a qualificação nova, e é ela que vale; a dona sai UMA vez."""
    f = F._compra_e_venda(casa)
    m = f["matricula"]
    assert "solteira" in _dono_na_certidao(casa, m)
    casada = dict(F.COMPRADORA, qualificacao=(
        "brasileira, casada sob o regime da comunhão parcial de bens, maior, professora, residente e "
        "domiciliada na Rua Exemplo, 20, Centro, Cidade Exemplo/MA"))
    av = _ato(casa, m, "AV-ESTADO-CIVIL", interessado=F.COMPRADORA, partes=[(casada, "proprietária")])
    assert av["ato"] and av["ato"]["selo_texto"], av["recado"][:1200]
    dono = _dono_na_certidao(casa, m)
    assert "casada sob o regime da comunhão parcial" in dono and "solteira" not in dono, dono
    assert dono.count(F.COMPRADORA["nome"]) == 1, dono


# ------------------------------------------------------------------ o usufruto

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
                   valores={"ATO DO USUFRUTO": f"R-{usufruto['ato']['numero']:02d}"},
                   cancela_ato_id=str(usufruto["ato"]["id"]))
    assert extinto["ato"] and extinto["ato"]["selo_texto"], extinto["recado"][:1200]
    oferecidos = _onus_oferecidos(casa, m)
    assert usufruto["ato"]["id"] not in oferecidos and extinto["ato"]["id"] not in oferecidos, oferecidos


def test_pelo_botao_cancelar_este_ato_a_hipoteca_e_o_usufruto_deixam_de_ser_onus(casa):  # noqa: F811
    """A OUTRA PORTA, a que funciona: «Cancelar este ato» na ficha (só OFICIAL e substituto) lavra a AV, marca
    o R com `cancelado_por_ato_id`, e o R sai do pedido de certidão de ônus — a hipoteca e o usufruto."""
    f = F._com_hipoteca(casa)
    m, r2 = f["matricula"], f["r2"]
    usufruto = _ato(casa, m, "R-USUFRUTO", interessado=F.COMPRADORA,
                    partes=[(F.COMPRADORA, "nu-proprietario"), (TERCEIRO, "usufrutuario")])["ato"]
    ficha = f"/registro-imoveis/{m['id']}"
    for alvo, motivo in ((r2, "Termo de quitação do credor de 18 de outubro de 2026"),
                         (usufruto, "Certidão de óbito do usufrutuário, expedida em 20 de outubro de 2026")):
        cx = F._protocolo_geral(casa, interessado=F.COMPRADORA, itens=[("16.1", 1), ("16.22.2", 1)])
        p = F._prenotar(casa, cx, apresentante=F.COMPRADORA, natureza="Cancelamento",
                        objeto=f"Matrícula {F.PRIMEIRA_MATRICULA}", matricula=str(F.PRIMEIRA_MATRICULA))
        html = F._clicar(casa["oficial"], ficha, f"/registro-imoveis/atos/{alvo['id']}/cancelar",
                         motivo=motivo, data_ato=F.date.today().isoformat(), protocolo=str(p["numero"]))
        marcado = F._um(casa, "SELECT cancelado, cancelado_por_ato_id FROM ri_atos WHERE id=%s", (alvo["id"],))
        assert marcado["cancelado"] == 1 and marcado["cancelado_por_ato_id"], html[:1200]
    oferecidos = _onus_oferecidos(casa, m)
    assert r2["id"] not in oferecidos and usufruto["id"] not in oferecidos, oferecidos


# ------------------------------------------------------------------ a prioridade

def _avisos(html: str) -> str:
    """Os recados da tela (`flash`), sem o resto da página — a ficha escreve «prioridade» em rótulo fixo."""
    pedacos = re.findall(r'<div class="flash [^"]*" data-aviso>(.*?)</div>', html, re.S)
    return " ".join(" ".join(re.sub(r"<[^>]+>", " ", p).split()) for p in pedacos)


def test_o_titulo_prenotado_depois_nao_passa_na_frente_do_anterior(casa):  # noqa: F811
    """LRP arts. 182, 186 e 191: o número de ordem da prenotação determina a prioridade do título, e esta a
    preferência dos direitos. Duas vendas da mesma dona a compradores diferentes, prenotadas nesta ordem: a
    segunda não vai ao livro antes de se resolver a primeira — ou, no mínimo, a tela diz que há prenotação
    anterior aberta sobre a matrícula (a escolha entre barrar e avisar é do oficial)."""
    f = F._compra_e_venda(casa)
    m = f["matricula"]
    prenotadas = []
    for quem in (TERCEIRO, CONJUGE):
        cx = F._protocolo_geral(casa, interessado=quem, itens=[("16.1", 1), ("16.3.14", 1)])
        p = F._prenotar(casa, cx, apresentante=quem, natureza="Compra e venda",
                        objeto=f"Matrícula {F.PRIMEIRA_MATRICULA}", matricula=str(F.PRIMEIRA_MATRICULA))
        prenotadas.append((cx, p))
    (_, primeira), (cx, segunda) = prenotadas
    assert primeira["numero"] < segunda["numero"]
    r = casa["balcao"].get(f"/registro-imoveis/{m['id']}/modelo/R-COMPRA-VENDA")
    teor, _ = F._como_o_balcao_preenche(json.loads(r.get_data(as_text=True))["teor"])
    html = F._lavrar(casa, m, tipo="R", teor=teor, natureza="Compra e venda", prenotacao=segunda, cx=cx,
                     itens=["16.3.14"], partes=[(F.COMPRADORA, "transmitente"), (CONJUGE, "adquirente")],
                     base_calculo="100.000,00", modelo="R-COMPRA-VENDA")
    lavrado = F._um(casa, "SELECT id FROM ri_atos WHERE matricula_id=%s AND numero=2", (m["id"],))
    avisos = _avisos(html)
    # O NÚMERO DA PRIMEIRA PERTO DE «PRENOTAÇÃO»/«PROTOCOLO»: um «2» solto casava com o «R-2 lavrado».
    avisou = re.search(rf"(?i)(prenota\w*|protocolo)\s+(n\.?\s*º?\s*)?{primeira['numero']}\b", avisos)
    assert not lavrado or avisou, f"a venda da prenotação {segunda['numero']} foi ao livro sem aviso: {avisos!r}"
    # CONSERTADO (decisão do oficial, 03/11/2026, «d1»): sem a confirmação, nada se lavra; com ela e o
    # motivo, lavra-se, e a auditoria guarda quem passou na frente de qual prenotação.
    assert not lavrado, avisos
    html = F._lavrar(casa, m, tipo="R", teor=teor, natureza="Compra e venda", prenotacao=segunda, cx=cx,
                     itens=["16.3.14"], partes=[(F.COMPRADORA, "transmitente"), (CONJUGE, "adquirente")],
                     base_calculo="100.000,00", modelo="R-COMPRA-VENDA", confirmo_prioridade="1",
                     motivo_prioridade="A primeira prenotação foi retirada pelo apresentante, que desistiu.")
    ato = F._um(casa, "SELECT id FROM ri_atos WHERE matricula_id=%s AND numero=2", (m["id"],))
    assert ato, _avisos(html)
    log = F._um(casa, "SELECT details FROM audit_logs WHERE action='RI_PRIORIDADE_CONFIRMADA' AND entity_id=%s",
                (ato["id"],))
    assert log and "desistiu" in str(log["details"]), log


# ------------------------------------------------------------------ a partilha

def test_a_partilha_poe_a_meeira_e_os_herdeiros_e_tira_a_falecida(casa):  # noqa: F811
    """CPC arts. 610 e 659; LRP art. 167, I, 25, e art. 19, § 9º: registrado o formal de partilha, os donos são
    a meeira e os herdeiros a quem o imóvel coube, e a falecida sai do quadro. (A fração de cada um fica no
    texto do ato: o quadro de titulares não guarda fração — observação O4 do relatório.)"""
    f = F._compra_e_venda(casa)
    m = f["matricula"]
    partilha = _ato(casa, m, "R-PARTILHA", interessado=CONJUGE,
                    partes=[(F.COMPRADORA, "transmitente"), (CONJUGE, "adquirente"),
                            (HERDEIRO, "adquirente"), (HERDEIRA, "adquirente")])
    assert partilha["ato"] and partilha["ato"]["selo_texto"], partilha["recado"][:1200]
    dono = _dono_na_certidao(casa, m)
    for quem in (CONJUGE, HERDEIRO, HERDEIRA):
        assert quem["nome"] in dono, dono
    assert F.COMPRADORA["nome"] not in dono, dono


# ------------------------------------------------------------------ o desmembramento

def test_a_matricula_filha_aberta_de_imovel_hipotecado_traz_o_onus(casa):  # noqa: F811
    """LRP art. 230: se na certidão da origem constar ônus, o oficial abre a matrícula e, logo em seguida,
    averba a existência do ônus. Desmembrado o imóvel hipotecado, a filha nasce gravada — e a tela que a abre
    (ou a ficha dela) tem de dizer que a origem tem a hipoteca de pé, para a averbação não ser esquecida."""
    f = F._com_hipoteca(casa)
    mae, r2 = f["matricula"], f["r2"]
    campos = dict(F.IMOVEL, data_abertura=F.date.today().isoformat(), area_valor="180,00",
                  registro_anterior=f"Matrícula {F.PRIMEIRA_MATRICULA} deste Ofício (desmembramento)",
                  proprietario_nome=F.COMPRADORA["nome"], proprietario_documento=F.COMPRADORA["cpf_fmt"],
                  proprietario_qualificacao=F.COMPRADORA["qualificacao"], confrontacoes=F.CONFRONTACOES)
    abertura = F._clicar(casa["balcao"], "/registro-imoveis/nova", "/registro-imoveis/nova", **campos)
    filha = F._um(casa, "SELECT * FROM ri_matriculas WHERE id <> %s ORDER BY id DESC LIMIT 1", (mae["id"],))
    assert filha, abertura[:800]
    ficha = casa["balcao"].get(f"/registro-imoveis/{filha['id']}").get_data(as_text=True)
    rotulo = f"R-02/{F.PRIMEIRA_MATRICULA}"
    assert rotulo in _avisos(abertura) or rotulo in _avisos(ficha) or re.search(
        rf"(?is)origem.{{0,300}}{re.escape(rotulo)}", re.sub(r"<[^>]+>", " ", ficha)), \
        f"nada sobre a hipoteca da origem: {_avisos(abertura)!r}"
    # CONSERTADO (decisão do oficial, 03/11/2026, «e2»): averbado o transporte pelo modelo novo, o aviso
    # sai da ficha, e a certidão de ônus da filha oferece o ônus transportado.
    transporte = _ato(casa, filha, "AV-TRANSPORTE-ONUS", interessado=F.COMPRADORA,
                      valores={"ATO DE ORIGEM": "R-02", "MATRICULA DE ORIGEM": f"{F.PRIMEIRA_MATRICULA}",
                               "NATUREZA DO ONUS": "hipoteca", "CREDOR OU BENEFICIARIO": F.BANCO["nome"]})
    assert transporte["ato"] and transporte["ato"]["selo_texto"], transporte["recado"][:1200]
    ficha = casa["balcao"].get(f"/registro-imoveis/{filha['id']}").get_data(as_text=True)
    assert "ainda não averbou" not in ficha, "o aviso continua depois do transporte"
    assert transporte["ato"]["id"] in _onus_oferecidos(casa, filha)


# ------------------------------------------------------------------ a doação com reserva de usufruto

def test_a_doacao_com_reserva_de_usufruto_faz_dona_a_donataria_e_o_usufruto_e_onus(casa):  # noqa: F811
    """LRP art. 167, I, 33 e 7; CC arts. 538 e 1.390: a doação com reserva de usufruto rende dois registros
    (o modelo R-DOACAO o diz: «objeto de registro proprio»). A donatária é a dona (a nua-propriedade), o
    doador sai do quadro de titulares e fica usufrutuário, e o usufruto é ônus."""
    f = F._compra_e_venda(casa)
    m = f["matricula"]
    doacao = _ato(casa, m, "R-DOACAO", interessado=CONJUGE,
                  partes=[(F.COMPRADORA, "transmitente"), (CONJUGE, "adquirente")])
    assert doacao["ato"] and doacao["ato"]["selo_texto"], doacao["recado"][:1200]
    usufruto = _ato(casa, m, "R-USUFRUTO", interessado=CONJUGE,
                    partes=[(CONJUGE, "nu-proprietário"), (F.COMPRADORA, "usufrutuário")])
    assert usufruto["ato"] and usufruto["ato"]["selo_texto"], usufruto["recado"][:1200]
    dono = _dono_na_certidao(casa, m)
    assert CONJUGE["nome"] in dono and F.COMPRADORA["nome"] not in dono, dono
    oferecidos = _onus_oferecidos(casa, m)
    assert usufruto["ato"]["id"] in oferecidos and doacao["ato"]["id"] not in oferecidos, oferecidos


# ------------------------------------------------------------------ os indicadores e a DOI

def _texto(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<(script|style).*?</\1>", " ", html)).split())


def test_o_indicador_pessoal_guarda_quem_figurou_e_marca_so_o_dono_de_hoje(casa):  # noqa: F811
    """LRP art. 180 (o Livro 5, indicador pessoal, de todos os que figuram nos atos): depois de duas vendas, o
    primeiro vendedor e a compradora que revendeu continuam achados na matrícula, com o papel; só o casal que
    comprou por último aparece como proprietário atual."""
    f = F._compra_e_venda(casa)
    m = f["matricula"]
    _ato(casa, m, "R-COMPRA-VENDA", interessado=TERCEIRO,
         partes=[(F.COMPRADORA, "transmitente"), (TERCEIRO, "adquirente"), (CONJUGE, "adquirente")])
    for quem, dono in ((F.VENDEDOR, False), (F.COMPRADORA, False), (TERCEIRO, True), (CONJUGE, True)):
        t = _texto(casa["balcao"].get(f"/registro-imoveis/indicador-pessoal?busca={quem['cpf']}").get_data(as_text=True))
        # O RESULTADO, NÃO O CABEÇALHO: «Atendendo: <nome>» também traz o nome do interessado do protocolo.
        resultado = t.split("encontrada(s).", 1)[-1]
        achado = resultado.split(quem["nome"], 1)[-1][:600]
        assert quem["nome"] in resultado and str(F.PRIMEIRA_MATRICULA) in achado, (quem["nome"], achado)
        assert ("Proprietário atual" in achado) is dono, (quem["nome"], achado)


def test_a_doi_do_mes_traz_cada_venda_com_quem_aliena_e_quem_adquire(casa):  # noqa: F811
    """Lei 10.426/2002, art. 8º, e IN RFB da DOI: uma declaração por operação, com alienantes e adquirentes.
    A tela da DOI (do oficial) lista as duas vendas da matrícula com as partes certas, e não as deixa entrar
    enquanto falta o que a Receita pede (o tipo da operação, o valor, a participação de cada um)."""
    f = F._compra_e_venda(casa)
    m = f["matricula"]
    _ato(casa, m, "R-COMPRA-VENDA", interessado=TERCEIRO,
         partes=[(F.COMPRADORA, "transmitente"), (TERCEIRO, "adquirente"), (CONJUGE, "adquirente")])
    t = _texto(casa["oficial"].get("/registro-imoveis/doi").get_data(as_text=True))
    r1 = f"R-01/{F.PRIMEIRA_MATRICULA}"
    r2 = f"R-02/{F.PRIMEIRA_MATRICULA}"
    assert r1 in t and r2 in t, t[:2000]
    linha_r2 = t[t.index(r2):].split("O que é a DOI", 1)[0]
    for quem in (F.COMPRADORA, TERCEIRO, CONJUGE):
        assert quem["nome"] in linha_r2, linha_r2
    assert F.VENDEDOR["nome"] not in linha_r2, linha_r2
    assert "sem percentual de participação" in linha_r2, linha_r2


def test_a_arrematacao_muda_o_dono_e_a_penhora_fica_ate_o_mandado_de_cancelamento(casa):  # noqa: F811
    """CPC arts. 901 e 903; LRP art. 167, I, 26, e art. 251: arrematado o imóvel penhorado, o arrematante é o
    dono e a executada sai; a penhora continua na certidão de ônus até a averbação do cancelamento por
    mandado — o registro não se cancela sozinho (LRP art. 250)."""
    f = F._compra_e_venda(casa)
    m = f["matricula"]
    penhora = _ato(casa, m, "AV-PENHORA", interessado=F.COMPRADORA)["ato"]
    arrematacao = _ato(casa, m, "R-ARREMATACAO", interessado=TERCEIRO,
                       partes=[(F.COMPRADORA, "transmitente"), (TERCEIRO, "adquirente")])
    assert arrematacao["ato"] and arrematacao["ato"]["selo_texto"], arrematacao["recado"][:1200]
    dono = _dono_na_certidao(casa, m)
    assert TERCEIRO["nome"] in dono and F.COMPRADORA["nome"] not in dono, dono
    assert penhora["id"] in _onus_oferecidos(casa, m)



def test_a_lista_das_averbacoes_antigas_acha_o_cancelamento_sem_marca(casa):  # noqa: F811
    """«Para as matrículas antigas, faça a lista das averbações lavradas por esses modelos, para conferir»
    (o oficial, 03/11/2026, «a1»). A averbação de cancelamento gravada SEM a marca — como as lavradas
    antes deste conserto — sai na lista, com o R-02 que o texto cita, de pé; a lavrada pelo modelo, com
    a marca, não sai."""
    import ri_cancelamentos_sem_marca as LISTA
    f = F._com_hipoteca(casa)
    m, r2 = f["matricula"], f["r2"]
    with casa["db"].connect() as con:
        assert LISTA.listar(con) == []
    cancela = _ato(casa, m, "AV-CANCELAMENTO-HIPOTECA", interessado=F.BANCO, cancela_ato_id=str(r2["id"]),
                   valores={"ATO CANCELADO": "R-02"})
    with casa["db"].transaction() as con:
        # COMO ERA ANTES DO CONSERTO: a averbação no livro, e o R-02 sem a marca.
        from bd_nativo import banco
        banco(con).escrever("UPDATE ri_atos SET cancelado=0, cancelado_por_ato_id=NULL WHERE id=%s", (r2["id"],))
    with casa["db"].connect() as con:
        achadas = LISTA.listar(con)
    assert [a["averbacao_id"] for a in achadas] == [cancela["ato"]["id"]], achadas
    assert [(c["tipo"], c["numero"]) for c in achadas[0]["citados"]] == [("R", 2)], achadas
    assert "de pé — candidato" in LISTA.em_texto(achadas)



# ------------------------------------------------------------------ o nome do modelo e o da tabela

@pytest.mark.parametrize("nome_do_modelo,nome_da_tabela,codigo", [
    ("Arrematação", "Carta de Arrematação", 31),
    ("Adjudicação", "Carta de Adjudicação", 33),
    ("Partilha", "Formal de Partilha", 32),
    ("Usucapião", "Sentenças Declaratórias de Usucapião", 34),
])
def test_o_ato_judicial_se_reconhece_pelo_nome_do_modelo_e_pelo_da_tabela(nome_do_modelo, nome_da_tabela,
                                                                          codigo):
    """Decisão do oficial, 05/11/2026 («t»): os modelos não se renomeiam à força, e a régua não depende de o
    nome bater. A consulta obrigatória à CNIB (TJMA 506) e a trava da indisponibilidade reconhecem a
    arrematação, a adjudicação, a partilha e a usucapião pelos dois nomes — e o modelo da casa é um deles."""
    import ri_cnib as CNIB
    import ri_modelos_atos as MOD
    assert nome_do_modelo in {m["natureza"] for m in MOD.MODELOS}
    for nome in (nome_do_modelo, nome_da_tabela):
        assert CNIB.codigo_reconhecido(nome) == codigo, nome
        assert CNIB.exige_consulta(nome, "R"), nome
        assert codigo not in CNIB.NATUREZAS_VOLUNTARIAS          # avisa, e não barra («b1»)
