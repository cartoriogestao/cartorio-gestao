"""O OURO DO LF06E — os papéis do Protesto como eram ANTES de as frases saírem do código.

`LF06E_protesto.json`, ao lado, foi gravado em 19/10/2026 na árvore do commit
2c41e90, ANTES de qualquer linha do LF06E, pelo `gerar()` abaixo: as frases
ainda eram f-strings e constantes dos módulos do protesto. Sem dado real de
pessoa — os nomes são «DE EXEMPLO», o CPF e o CNPJ são os de teste.

    funcoes[nome]   o que os montadores puros devolvem (certidão, termo,
                    instrumento, edital, linha do protesto, datas)
    banco[nome]     o que os montadores que leem o banco devolvem — o aviso, o
                    canhoto e os dois livros —, com o título semeado por
                    `semear()` num banco de teste vazio de protesto
    vocabulario     os dicionários de rótulos que iam ao papel

E `LF06E_molduras.json`: o HTML que cada rota do protesto entrega ao `.odt`
(certidão, instrumento, aviso com o canhoto, editais, os dois livros), capturado
com `atribuicoes_web.py` intacto — ver o `_como` dele.

**NÃO SE REGERA.** Depois do LF06E as frases moram em `modelos_padrao/protesto/`,
e `gerar()` leria a base: o teste compararia a base com ela mesma. Para conferir
o gerador, rode-o numa cópia do commit 2c41e90 (`git worktree add`).

`chamadas()` e `chamadas_com_banco(con)` são as mesmas listas que o gerador
usou; o teste as refaz depois da mudança e compara saída por saída — byte a
byte, porque texto expedido e congelado (termo lavrado, certidão, edital) não
pode mudar uma vírgula. O retrato dos dicionários (`vocabulario_de_antes`) se
confere contra as peças que os substituíram (`vocabulario_de_hoje`).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent / "LF06E_protesto.json"
MOLDURAS = Path(__file__).resolve().parent / "LF06E_molduras.json"

# Pessoas e empresas de exemplo — LGPD: nada aqui é de ninguém.
CPF = "00000000191"
CNPJ = "00000042000122"
DEVEDOR = "MARIA DE EXEMPLO"
REQUERENTE = "JOÃO DE EXEMPLO"
ORDEM = "1ª Vara de Exemplo, processo 0000000-00.2026.8.10.0000"

SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE EXEMPLO",
      "endereco_completo": "Rua de Exemplo, 1, Centro",
      "serventia_telefone": "(99) 0000-0000",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


def normal(valor):
    """A forma com que o valor foi gravado (tupla vira lista, chave ordenada)."""
    return json.loads(json.dumps(valor, ensure_ascii=False, sort_keys=True))


def tenta(f):
    try:
        return {"ok": f()}
    except Exception as erro:  # noqa: BLE001 — o erro também é saída
        return {"erro": f"{type(erro).__name__}: {erro}"}


def _achado(**mudar) -> dict:
    """Um protesto achado pela busca da certidão — o mais completo possível."""
    base = {"titulo_id": 1, "numero_titulo": "123", "especie": "DMI",
            "situacao": "PROTESTADO", "devedor": DEVEDOR,
            "devedor_documento": "000.000.001-91",
            "cedente": "EMPRESA DE EXEMPLO LTDA",
            "cedente_documento": "00.000.042/0001-22", "protocolo": "2609080001",
            "apresentante": "BANCO DE EXEMPLO", "motivo_protesto": "1",
            "tipo_protesto": "C", "tipo_endosso": "", "valor": "1.234,56",
            "saldo": "1.000,00", "data_emissao": "2026-07-01",
            "data_vencimento": "2026-08-01", "data_protesto": "2026-09-08",
            "efeitos_suspensos": False, "suspensao_juizo": "",
            "suspensao_processo": "", "suspensao_em": "", "livro": "10",
            "folha": "42", "numero_ordem": 7, "selo": None, "cancelado": False,
            "data_cancelamento": None, "motivo_cancelamento": None}
    base.update(mudar)
    return base


def chamadas() -> dict:
    """Cada montador puro do protesto, com os ramos que a regra escolhe."""
    import protesto_aviso as AV
    import protesto_certidao as PTC
    import protesto_instrumento as PTI
    import protesto_termo as PTT

    f: dict = {}

    # ------------------------------------------------ a certidão
    um = [_achado(cancelado=True, data_cancelamento="2026-09-20",
                  motivo_cancelamento="pagamento")]
    dois = um + [_achado(titulo_id=2, numero_titulo="456", cancelado=True,
                         data_cancelamento="2026-09-21")]
    pedidos = {
        "verbal": {},
        "requerente": {"requerente": REQUERENTE},
        "devedor": {"autorizacao": "DEVEDOR_ESCRITO"},
        "devedor_com_nome": {"autorizacao": "DEVEDOR_ESCRITO",
                             "requerente": DEVEDOR},
        "ordem": {"autorizacao": "ORDEM_JUDICIAL"},
        "ordem_com_ref": {"autorizacao": "ORDEM_JUDICIAL",
                          "autorizacao_ref": ORDEM},
    }
    for tipo in PTC.TIPOS:
        ach = [] if tipo == "NEGATIVA" else (
            um if tipo == "CANCELAMENTO" else [_achado()])
        for nome_p, extra in pedidos.items():
            f[f"certidao({tipo},{nome_p})"] = (
                lambda t=tipo, a=ach, e=extra: PTC.montar_teor(
                    tipo=t, nome=f" {DEVEDOR} ", documento=CPF, achados=a,
                    desde="2021-09-08", hoje="2026-09-08", **e))
        for nome_d, doc in (("cnpj", CNPJ), ("sem_documento", None),
                            ("documento_torto", "123")):
            f[f"certidao({tipo},{nome_d})"] = (
                lambda t=tipo, a=ach, d=doc: PTC.montar_teor(
                    tipo=t, nome=DEVEDOR, documento=d, achados=a,
                    desde="2020-01-31", hoje="2026-09-08", periodo_anos=6))
    f["certidao(POSITIVA,dois)"] = lambda: PTC.montar_teor(
        tipo="POSITIVA", nome=DEVEDOR, documento=CPF,
        achados=[_achado(), _achado(titulo_id=2, numero_titulo="456")],
        desde="2021-09-08", hoje="2026-09-08")
    f["certidao(CANCELAMENTO,dois)"] = lambda: PTC.montar_teor(
        tipo="CANCELAMENTO", nome=DEVEDOR, documento=CPF, achados=dois,
        desde="2021-09-08", hoje="2026-09-08")
    for ano in ("2000", "2005", "2010", "2016", "2020", "2021", "2026", "1999"):
        f[f"certidao(POSITIVA,desde {ano})"] = (lambda a=ano: PTC.montar_teor(
            tipo="POSITIVA", nome=DEVEDOR, documento=CPF, achados=[_achado()],
            desde=f"{a}-03-15", hoje="2026-09-08"))
    # O AJUSTE QUE A CASA JÁ TENHA FEITO com os marcadores de antes tem de
    # continuar montando — inclusive o `{cabeca}`, `{fecho}` e `{nome}`.
    f["certidao(NEGATIVA,ajuste antigo)"] = lambda: PTC.montar_teor(
        tipo="NEGATIVA", nome=DEVEDOR, documento=CPF, achados=[],
        desde="2021-09-08", hoje="2026-09-08", requerente=REQUERENTE,
        modelo="{pedido}|{desde}|{identificacao}|{periodo_anos}|{nome}")
    f["certidao(POSITIVA,ajuste antigo)"] = lambda: PTC.montar_teor(
        tipo="POSITIVA", nome=DEVEDOR, documento=CPF, achados=[_achado()],
        desde="2021-09-08", hoje="2026-09-08",
        modelo="{cabeca}\n{corpo}\nPedido: {pedido}. Dou fé. {nome}")
    f["certidao(CANCELAMENTO,ajuste antigo)"] = lambda: PTC.montar_teor(
        tipo="CANCELAMENTO", nome=DEVEDOR, documento=CPF, achados=dois,
        desde="2021-09-08", hoje="2026-09-08",
        modelo="[{cabeca}] [{corpo}] [{fecho}] [{nome}] [{pedido}]")
    f["certidao(POSITIVA,ajuste quebrado)"] = lambda: PTC.montar_teor(
        tipo="POSITIVA", nome=DEVEDOR, documento=CPF, achados=[_achado()],
        desde="2021-09-08", hoje="2026-09-08", modelo="{cabeca} {nao_existe}")
    f["certidao(POSITIVA,sem achado)"] = lambda: PTC.montar_teor(
        tipo="POSITIVA", nome=DEVEDOR, documento=CPF, achados=[],
        desde="2021-09-08", hoje="2026-09-08")
    f["certidao(INVENTADA)"] = lambda: PTC.montar_teor(
        tipo="INVENTADA", nome=DEVEDOR, documento=CPF, achados=[],
        desde="2021-09-08", hoje="2026-09-08")

    linhas = {
        "completa": _achado(),
        "minima": {"numero_titulo": "9", "valor": "10,00",
                   "data_protesto": "2026-09-08"},
        "cedente_e_o_devedor": _achado(cedente=DEVEDOR.lower()),
        "cedente_sem_documento": _achado(cedente_documento=""),
        "saldo_igual": _achado(saldo="1.234,56"),
        "suspenso": _achado(efeitos_suspensos=True,
                            suspensao_juizo="1ª Vara de Exemplo",
                            suspensao_processo="0000000-00.2026.8.10.0000"),
        "suspenso_sem_juizo": _achado(efeitos_suspensos=True),
        "cancelado": _achado(cancelado=True, data_cancelamento="2026-09-20",
                             motivo_cancelamento="pagamento"),
        "cancelado_sem_motivo": _achado(cancelado=True,
                                        data_cancelamento="2026-09-20"),
        "aceite_falimentar": _achado(motivo_protesto="2", tipo_protesto="F"),
        "devolucao": _achado(motivo_protesto="3", tipo_protesto=""),
        "motivo_desconhecido": _achado(motivo_protesto="9"),
        "sem_lugar": _achado(livro=None, folha=None, numero_ordem=None),
        "so_folha": _achado(livro=None, numero_ordem=None),
    }
    for nome_l, a in linhas.items():
        f[f"linha_do_protesto({nome_l})"] = (
            lambda x=a: PTC._linha_do_protesto(x, 3))
    for ano in (2000, 2001, 2009, 2010, 2011, 2019, 2020, 2021, 2030, 2099, 1999,
                2100):
        f[f"por_extenso_ano({ano})"] = lambda a=ano: PTC._por_extenso_ano(a)
    f["mes_e_ano"] = lambda: [PTC._mes_e_ano(f"2026-{m:02d}-01")
                              for m in range(1, 13)]

    # ------------------------------------------------ o termo
    termos = {
        "edital": {"edital_data": "2026-09-08", "edital_motivo": "Ausente"},
        "edital_sem_motivo": {"edital_data": "2026-09-08"},
        "edital_motivo_com_espacos": {"edital_data": "2026-09-08",
                                      "edital_motivo": "  Mudou-se   de vez "},
        "pessoal": {"pessoal_data": "2026-09-08"},
        "digital": {"pessoal_data": "2026-09-08", "pessoal_digital": True},
        "edital_e_pessoal": {"edital_data": "2026-09-08",
                             "pessoal_data": "2026-09-09"},
        "nada": {},
        "data_torta": {"edital_data": "08/09/2026"},
    }
    for nome_t, extra in termos.items():
        for motivo, tipo in (("1", ""), ("2", "F"), ("3", "C")):
            f[f"termo({nome_t},{motivo}{tipo})"] = (
                lambda e=extra, m=motivo, t=tipo: PTT.montar(
                    motivo_protesto=m, tipo_protesto=t, **e))
    f["termo(sem motivo)"] = lambda: PTT.montar(motivo_protesto="", tipo_protesto="")
    f["termo(tipo torto)"] = lambda: PTT.montar(motivo_protesto="1",
                                                tipo_protesto="X")
    f["termo(ajuste antigo)"] = lambda: PTT.montar(
        modelo="LIVRO: {tipo} / {motivo}\n\n{edital}\n", motivo_protesto="1",
        tipo_protesto="C", edital_data="2026-09-08", edital_motivo="Ausente")
    f["termo(ajuste com marcador inventado)"] = lambda: PTT.montar(
        modelo="{base}", motivo_protesto="1", tipo_protesto="C")
    f["frase_do_edital"] = lambda: [
        PTT.frase_do_edital(data="2026-09-08", motivo="Ausente"),
        PTT.frase_do_edital(data="2026-09-08"),
        PTT.frase_do_edital(data=None, motivo="Ausente")]
    f["frase_da_intimacao_pessoal"] = lambda: [
        PTT.frase_da_intimacao_pessoal(data="2026-09-08"),
        PTT.frase_da_intimacao_pessoal(data="2026-09-08", digital=True),
        PTT.frase_da_intimacao_pessoal(data="")]

    # ------------------------------------------------ o instrumento
    intimacoes = {
        "nenhuma": None,
        "edital": {"data": "2026-09-08", "modo": "EDITAL",
                   "motivo_nao_entrega": "Ausente"},
        "edital_sem_motivo": {"data": "2026-09-08", "modo": "edital",
                              "motivo_nao_entrega": None},
        "pessoal": {"data": "2026-09-08", "modo": "PESSOAL",
                    "motivo_nao_entrega": None},
        "sem_modo": {"data": "2026-09-08", "modo": None},
    }
    for copia in (True, False):
        for nome_i, intim in intimacoes.items():
            f[f"instrumento(copia={copia},{nome_i})"] = (
                lambda c=copia, i=intim: PTI.montar_teor(
                    serventia="SERVENTIA DE EXEMPLO", praca="Cidade Exemplo - MA",
                    motivo="falta de pagamento", copia_arquivada=c, intimacao=i,
                    descricao="Título: Duplicata de exemplo."))
    f["instrumento(ajuste antigo)"] = lambda: PTI.montar_teor(
        modelo="{serventia}\n\n{praca} {motivo}\n{descricao}\n{copia}  {intimacao}",
        serventia="SERVENTIA DE EXEMPLO", praca="desta praça", motivo="x",
        copia_arquivada=False, intimacao=None)
    f["instrumento(ajuste com marcador inventado)"] = lambda: PTI.montar_teor(
        modelo="{serventia} {nao_existe}", serventia="S", praca="P", motivo="M",
        copia_arquivada=True, intimacao=None)

    completo = {
        "titulo": {"especie": "dmi", "numero_titulo": "123",
                   "data_emissao": "2026-07-01", "data_vencimento": "2026-08-01",
                   "valor_centavos": 123456, "saldo_centavos": 100000,
                   "protocolo": "2609080001", "apresentante_nome": "BANCO DE EXEMPLO",
                   "apresentante_codigo": "001", "cedente_nome": "EMPRESA DE EXEMPLO LTDA",
                   "cedente_documento": CNPJ, "motivo_protesto": "1",
                   "tipo_protesto": "C"},
        "protesto": {"livro_numero": 10, "rotulo": "42v", "folha": 42,
                     "numero_ordem": 7, "data_ato": "2026-09-10"},
        "apontado_em": "2026-09-08",
        "devedores": [
            {"nome": DEVEDOR, "documento_tipo": "CPF", "documento_numero": CPF,
             "endereco": "Rua de Exemplo, 10", "bairro": "Centro",
             "cidade": "Cidade Exemplo", "uf": "MA"},
            {"nome": REQUERENTE, "documento_tipo": None, "documento_numero": "",
             "endereco": "", "bairro": "", "cidade": "", "uf": ""}]}
    minimo = {"titulo": {"especie": "XYZ", "numero_titulo": "",
                         "valor_centavos": 0, "saldo_centavos": 0,
                         "protocolo": "", "motivo_protesto": "9"},
              "protesto": None, "apontado_em": None, "devedores": []}
    sem_lugar = {**completo, "apontado_em": None,
                 "protesto": {"data_ato": "2026-09-10"},
                 "titulo": {**completo["titulo"], "especie": "",
                            "saldo_centavos": 123456, "apresentante_nome": "",
                            "cedente_documento": "", "motivo_protesto": "2",
                            "tipo_protesto": "F"}}
    for nome_d, d in (("completo", completo), ("minimo", minimo),
                      ("sem_lugar", sem_lugar)):
        f[f"descricao_do_documento({nome_d})"] = (
            lambda x=d: PTI.descricao_do_documento(x))
    f["instrumento_por_extenso"] = lambda: [
        PTI._por_extenso(x) for x in ("2026-09-01", "2026-13-01", "", "x")]

    # ------------------------------------------------ o edital (puro)
    aviso = {"devedor_nome": f" {DEVEDOR} ", "devedor_documento": CPF}
    titulo = {"protocolo": "2609080001", "numero_titulo": "123",
              "especie": "DMI", "saldo_centavos": 123456}
    f["edital(completo)"] = lambda: AV.montar_teor_do_edital(
        aviso=aviso, titulo=titulo, sv=SV, hoje="2026-09-08",
        data_extenso="8 de setembro de 2026", limite="2026-09-11")
    f["edital(sem limite, sem extenso)"] = lambda: AV.montar_teor_do_edital(
        aviso=aviso, titulo=titulo, sv=SV, hoje="2026-09-08")
    f["edital(magro)"] = lambda: AV.montar_teor_do_edital(
        aviso={"devedor_nome": None, "devedor_documento": None},
        titulo={"protocolo": None, "numero_titulo": None, "especie": None,
                "saldo_centavos": None},
        sv={}, hoje="2026-09-08", limite="2026-09-11")

    return f


def vocabulario_de_antes() -> dict:
    """Os dicionários de rótulos, como o gerador os leu NA ÁRVORE DE ANTES.

    É `funcoes["vocabulario"]` do ouro. Depois do LF06E `FORMAS`,
    `OCORRENCIA_DO_ATO` e os textos do motivo e do tipo não são mais
    dicionários do código — o teste compara este retrato com
    `vocabulario_de_hoje()`, que lê as peças.
    """
    import protesto as PT
    import protesto_aviso as AV
    import protesto_certidao as PTC
    import protesto_cra as CRA
    import protesto_instrumento as PTI
    import protesto_livros as PLIV
    import protesto_termo as PTT
    return {
        "MOTIVO_NO_LIVRO": [PTT.motivo_no_livro(c) for c in ("1", "2", "3", " 1 ", "9", None)],
        "TIPO_NO_LIVRO": [PTT.tipo_no_livro(c) for c in ("C", "F", "", None, "falimentar", "X")],
        "ESPECIES": dict(CRA.ESPECIES),
        "MOTIVOS_NAO_ENTREGA": AV.motivos_para_escolher(),
        "motivo_rotulo": [AV.motivo_rotulo(c) for c in (11, "2", 7, 99, None)],
        "FORMAS": dict(PLIV.FORMAS),
        "OCORRENCIA_DO_ATO": dict(PLIV.OCORRENCIA_DO_ATO),
        "CATALOGO_CANCELAMENTO": dict(PT.CATALOGO_CANCELAMENTO),
        "MESES": [list(PTC.MESES), list(PTI.MESES)],
    }


def vocabulario_de_hoje() -> dict:
    """O mesmo retrato, lido de onde os rótulos moram DEPOIS do LF06E.

    O que continuou no código (o catálogo de não-entrega, as hipóteses de
    cancelamento, os meses, a glosa da CRA) é lido como antes; o que virou
    peça é lido da peça — e o nome da espécie NO PAPEL tem de ter nascido
    igual à glosa do leiaute.
    """
    import protesto as PT
    import protesto_aviso as AV
    import protesto_certidao as PTC
    import protesto_instrumento as PTI
    import protesto_livros as PLIV
    import protesto_pecas as PECAS
    import protesto_termo as PTT
    pagamentos = PECAS.vocabulario(None, "PT_LIVRO_PAGAMENTOS")
    protocolo = PECAS.vocabulario(None, "PT_LIVRO_PROTOCOLO")
    return {
        "MOTIVO_NO_LIVRO": [PTT.motivo_no_livro(c) for c in ("1", "2", "3", " 1 ", "9", None)],
        "TIPO_NO_LIVRO": [PTT.tipo_no_livro(c) for c in ("C", "F", "", None, "falimentar", "X")],
        "ESPECIES": PECAS.vocabulario(None, "PT_ESPECIES"),
        "MOTIVOS_NAO_ENTREGA": AV.motivos_para_escolher(),
        "motivo_rotulo": [AV.motivo_rotulo(c) for c in (11, "2", 7, 99, None)],
        "FORMAS": {k: pagamentos[k] for k in PT.FORMAS_DE_PAGAMENTO},
        "OCORRENCIA_DO_ATO": {k: protocolo[k] for k in PLIV.ATOS_NO_PROTOCOLO},
        "CATALOGO_CANCELAMENTO": dict(PT.CATALOGO_CANCELAMENTO),
        "MESES": [list(PTC.MESES), list(PTI.MESES)],
    }


# ----------------------------------------------------- o que lê o banco


def semear(con) -> dict:
    """Dois títulos com aviso e os atos que os livros leem. ESCREVE.

    Os números (aviso, protocolo, ordem) são escritos à mão, e não sorteados
    pelo banco: o papel os imprime, e o ouro tem de ser o mesmo em qualquer
    banco de teste.
    """
    from bd_nativo import banco
    bd = banco(con)
    agora = "2026-09-08T10:00:00"
    bd.escrever("DELETE FROM settings WHERE key IN ('serventia_horario', "
                "'ri_feriados_locais')")
    bd.escrever("INSERT INTO settings(key, value) VALUES (%s, %s), (%s, %s)",
                ("serventia_horario", "segunda a sexta, das 8h às 17h",
                 "ri_feriados_locais", ""))
    ids = {}
    for chave, t in (
            ("cheio", {"especie": "DMI", "numero_titulo": "123", "protocolo": "2609080001",
                       "aceite": "A", "valor_centavos": 123456, "saldo_centavos": 100000,
                       "data_vencimento": "2026-08-01",
                       "cedente_nome": "EMPRESA DE EXEMPLO LTDA",
                       "cedente_documento": CNPJ,
                       "apresentante_nome": "BANCO DE EXEMPLO",
                       "apresentante_codigo": "001", "situacao": "APONTADO"}),
            ("magro", {"especie": "XYZ", "numero_titulo": "", "protocolo": "2609090002",
                       "aceite": None, "valor_centavos": 5000, "saldo_centavos": 0,
                       "data_vencimento": None, "cedente_nome": None,
                       "cedente_documento": None, "apresentante_nome": None,
                       "apresentante_codigo": "237", "situacao": "APONTADO"})):
        ids[chave] = int(bd.escrever(
            """INSERT INTO pt_titulos(especie, numero_titulo, protocolo, aceite,
                   valor_centavos, saldo_centavos, data_vencimento, cedente_nome,
                   cedente_documento, apresentante_nome, apresentante_codigo,
                   situacao, criado_em)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (t["especie"], t["numero_titulo"], t["protocolo"], t["aceite"],
             t["valor_centavos"], t["saldo_centavos"], t["data_vencimento"],
             t["cedente_nome"], t["cedente_documento"], t["apresentante_nome"],
             t["apresentante_codigo"], t["situacao"], agora))[0]["id"])
    bd.escrever(
        "INSERT INTO pt_devedores(titulo_id, nome, documento_tipo, documento_numero) "
        "VALUES (%s, %s, 'CPF', %s), (%s, %s, NULL, NULL)",
        (ids["cheio"], DEVEDOR, CPF, ids["magro"], REQUERENTE))
    avisos = {}
    for chave, numero, end in (
            ("cheio", 901, ("Rua de Exemplo, 10", "Centro", "Cidade Exemplo", "MA",
                            "65000-000")),
            ("magro", 902, (None, None, None, None, None))):
        avisos[chave] = int(bd.escrever(
            """INSERT INTO pt_avisos(titulo_id, numero, ano, devedor_nome,
                   devedor_documento, endereco, bairro, cidade, uf, cep,
                   situacao, emitido_em, criado_em)
               VALUES (%s,%s,2026,%s,%s,%s,%s,%s,%s,%s,'EMITIDO',%s,%s)
               RETURNING id""",
            (ids[chave], numero, DEVEDOR if chave == "cheio" else REQUERENTE,
             CPF if chave == "cheio" else None, *end, agora, agora))[0]["id"])
    atos = (
        ("cheio", "APONTAMENTO", "2026-09-08", 1, "{}", "MANUAL"),
        ("cheio", "INTIMACAO", "2026-09-09", None, '{"modo": "PESSOAL"}', "MANUAL"),
        ("cheio", "INTIMACAO", "2026-09-10", None,
         '{"modo": "PESSOAL", "digital": true}', "MANUAL"),
        ("cheio", "PAGAMENTO", "2026-09-11", 5,
         '{"valor_pago_centavos": 100000, "forma_pagamento": "cheque", '
         '"forma_identificacao": "cheque n. 000001 do Banco de Exemplo", '
         '"emolumentos_centavos": 4321}', "MANUAL"),
        ("magro", "APONTAMENTO", "2026-09-09", 2, "{}", "MANUAL"),
        ("magro", "INTIMACAO", "2026-09-12", None, '{"modo": "EDITAL"}', "MANUAL"),
        ("magro", "PROTESTO", "2026-09-15", 8, "{}", "MANUAL"),
        ("magro", "SUSTACAO", "2026-09-16", None, "{}", "MANUAL"),
        ("magro", "CANCELAMENTO", "2026-09-17", None, "{}", "MANUAL"),
        ("magro", "PAGAMENTO", "2026-09-18", 6, "{}", "EOFICIO"),
        ("magro", "PAGAMENTO", "2026-09-19", 7, '{"forma_pagamento": "PIX"}', "MANUAL"),
        ("magro", "RETIFICACAO", "2026-09-20", None, "{}", "MANUAL"),
    )
    for chave, tipo, dia, ordem, detalhe, origem in atos:
        bd.escrever(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, numero_ordem,
                   detalhe_json, origem, criado_em)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (ids[chave], tipo, dia, ordem, detalhe, origem, agora))
    return {"titulos": ids, "avisos": avisos}


def _sem_id(linhas: list[dict]) -> list[dict]:
    """O id interno muda de banco para banco; o papel não o imprime."""
    return [{k: v for k, v in linha.items() if k not in ("ato_id", "titulo_id")}
            for linha in linhas]


def chamadas_com_banco(con, semeado: dict) -> dict:
    """O aviso, o canhoto e os livros — o que lê o título do banco."""
    import protesto_aviso as AV
    import protesto_livros as PLIV

    f: dict = {}
    for chave, aviso_id in semeado["avisos"].items():
        f[f"aviso({chave})"] = (lambda a=aviso_id: AV.montar_teor_do_aviso(
            con, AV.ler(con, a), sv=SV))
        f[f"canhoto({chave})"] = (lambda a=aviso_id: AV.canhoto_do_aviso(
            con, AV.ler(con, a)))
    f["livro_de_pagamentos"] = lambda: _sem_id(PLIV.livro_de_pagamentos(
        con, de="2026-09-01", ate="2026-09-30"))
    f["livro_de_protocolo"] = lambda: _sem_id(PLIV.livro_de_protocolo(
        con, de="2026-09-01", ate="2026-09-30"))
    return f


def gerar(con) -> None:
    """Grava o ouro. SÓ NA ÁRVORE DE ANTES (commit 2c41e90) — ver o cabeçalho."""
    raiz = Path(__file__).resolve().parents[3]
    funcoes = {nome: normal(tenta(f)) for nome, f in chamadas().items()}
    funcoes["vocabulario"] = normal(tenta(vocabulario_de_antes))
    semeado = semear(con)
    banco_ = {nome: normal(tenta(f))
              for nome, f in chamadas_com_banco(con, semeado).items()}
    commit = subprocess.run(["git", "-C", str(raiz), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    sujo = subprocess.run(["git", "-C", str(raiz), "status", "--porcelain",
                           "--untracked-files=no"],
                          capture_output=True, text=True).stdout.split("\n")
    ARQUIVO.write_text(json.dumps(
        {"_como": ("Gerado ANTES do LF06E, das frases ainda no código do commit "
                   f"{commit}, por tests/fixtures/modelos_ouro/ouro_lf06e.py. Não "
                   "regerar: depois da mudança as frases moram na base, e regerar "
                   "faria o teste comparar a base com ela mesma."),
         "commit": commit, "mudado_na_arvore": [x for x in sujo if x.strip()],
         "funcoes": funcoes, "banco": banco_},
        ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def semear_molduras(con) -> dict:
    """O que as rotas dos papéis impressos leem: os títulos e avisos de
    `semear()`, uma certidão, uma certidão cancelada, um instrumento e um
    edital — com número, data e hash escritos à mão. ESCREVE."""
    from bd_nativo import banco
    semeado = semear(con)
    bd = banco(con)
    tid = semeado["titulos"]["magro"]
    certidao = bd.escrever(
        "INSERT INTO pt_certidoes(numero, ano, tipo, nome, documento, documento_tipo, "
        "periodo_anos, desde, achados, achados_json, teor, hash_certidao, emitida_em, "
        "emitida_por) VALUES (7, 2026, 'POSITIVA', %s, %s, 'CPF', 5, '2021-09-08', 1, "
        "'[]', 'TEOR DE EXEMPLO.', 'abc123', '2026-09-08T10:00:00', 'mario') RETURNING id",
        (DEVEDOR, CPF))[0]["id"]
    cancelada = bd.escrever(
        "INSERT INTO pt_certidoes(numero, ano, tipo, nome, documento, documento_tipo, "
        "periodo_anos, desde, achados, achados_json, teor, hash_certidao, emitida_em, "
        "emitida_por, cancelada, motivo_cancelamento) VALUES (8, 2026, 'NEGATIVA', %s, %s, "
        "'CPF', 5, '2021-09-08', 0, '[]', 'TEOR NEGATIVO DE EXEMPLO.', 'abc124', "
        "'2026-09-09T10:00:00', 'mario', 1, 'erro de exemplo') RETURNING id",
        (DEVEDOR, CPF))[0]["id"]
    ato = bd.valor("SELECT id FROM pt_atos WHERE tipo = 'PROTESTO' AND titulo_id = %s "
                   "ORDER BY id DESC LIMIT 1", (tid,))
    instrumento = bd.escrever(
        "INSERT INTO pt_instrumentos(numero, ano, titulo_id, ato_id, teor, corpo_json, "
        "hash_instrumento, emitido_em, emitido_por) VALUES (3, 2026, %s, %s, "
        "'TEOR DO INSTRUMENTO.', %s, 'def456', '2026-09-16T10:00:00', 'mario') RETURNING id",
        (tid, ato, json.dumps({"protesto": {"data_ato": "2026-09-15"}})))[0]["id"]
    edital = bd.escrever(
        "INSERT INTO pt_editais(numero, ano, aviso_id, titulo_id, publicado_em, teor, "
        "hash_teor, criado_em) VALUES (4, 2026, %s, %s, '2026-09-12', %s, 'h', "
        "'2026-09-12T10:00:00') RETURNING id",
        (semeado["avisos"]["magro"], tid, "EDITAL DE EXEMPLO\n\nlinha 2"))[0]["id"]
    return {**semeado, "certidao": certidao, "cancelada": cancelada,
            "instrumento": instrumento, "edital": edital}


def rotas_das_molduras(semeado: dict) -> dict:
    """Cada papel impresso do protesto, pela rota que o entrega em `.odt`."""
    return {
        "certidao": f"/protesto/certidoes/{semeado['certidao']}/odt?formato=odt",
        "certidao_cancelada": f"/protesto/certidoes/{semeado['cancelada']}/odt?formato=odt",
        "instrumento": f"/protesto/instrumentos/{semeado['instrumento']}/odt?formato=odt",
        "aviso": f"/protesto/avisos/{semeado['avisos']['cheio']}.odt?formato=odt",
        "editais_do_dia": "/protesto/editais/dia.odt?dia=2026-09-12",
        "edital": f"/protesto/editais/{semeado['edital']}.odt",
        "livro_pagamentos": "/protesto/livros/pagamentos?de=2026-09-01&ate=2026-09-30&formato=odt",
        "livro_protocolo": "/protesto/livros/protocolo?de=2026-09-01&ate=2026-09-30&formato=odt",
    }


def ouro() -> dict:
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))


def ouro_das_molduras() -> dict:
    return json.loads(MOLDURAS.read_text(encoding="utf-8"))["molduras"]
