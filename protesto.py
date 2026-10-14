"""
O modulo do Protesto — cadastrar o titulo e lancar o apontamento.

COMO SE USA
    with db.transaction() as con:
        titulo_id = cadastrar_titulo(con, dados, origem="CRA",
                                     origem_chave=chave, agora=agora)
        lugar = lancar_apontamento(con, titulo_id, sv=sv, agora=agora,
                                   data_extenso=hoje, usuario=usuario)
    audit(...)                      # FORA da transacao, como no resto da casa

    `dados` esta no vocabulario que `protesto_arquivo.para_apontamento()`
    produz a partir do arquivo da CRA — o mesmo formato serve para montar o
    titulo a mao, para os sete que chegam pelo balcao.

CARGA REPETIVEL POR CONSTRUCAO
    Reapresentar o mesmo (origem, origem_chave) devolve o id ja cadastrado em
    vez de duplicar. E a mesma decisao que rege o resto da casa: a remessa da
    CRA pode ser processada de novo sem medo.

SOBRE A INTIMACAO
    `lancar_intimacao()` registra o modo (pessoal ou edital), a diligencia e
    o comprovante — e nao calcula prazo nenhum. O acervo do E-Oficio nunca
    controlou data de intimacao (ver pt_schema.py), e contar o prazo de 3
    dias e decisao juridica do oficial, ainda nao tomada. Um titulo pode ser
    intimado mais de uma vez — pessoal sem exito, depois edital.

SOBRE O PROTESTO E A DESISTENCIA
    `lancar_protesto()` lavra o protesto no Livro de Registro de Protestos —
    exige que o titulo ja tenha sido intimado, mas NAO confere se o prazo da
    intimacao venceu, pela mesma razao de `lancar_intimacao()`: essa conta
    ainda nao foi decidida pelo oficial. `lancar_desistencia()` registra a
    desistencia do CREDOR antes de o protesto ser lavrado — depois de
    lavrado, tirar o protesto e cancelamento, com o catalogo de hipoteses da
    Lei 9.492/1997, e nao esta neste modulo ainda.

SOBRE O PAGAMENTO
    `lancar_pagamento()` cabe em QUALQUER ponto do ciclo — apontado,
    intimado ou ja protestado —, decisao do oficial em 24/08/2026: o
    devedor nem sempre espera o protesto ser lavrado para pagar. Ocupa lugar
    no Livro de Registro de Pagamentos (PT_PAGAMENTO) de todo jeito, porque
    a serie exige registrar o pagamento tenha ou nao havido protesto antes.
    Nao confere o valor pago contra o saldo do titulo: decidir o que fazer
    com pagamento parcial e do oficial, nao deste modulo.

SOBRE O CANCELAMENTO
    O acervo tem UM cadastro so de motivo — "Erro Material" — e os 56
    cancelamentos reais saíram todos dele ou de campo livre: metade não diz
    por quê. `lancar_cancelamento()` exige uma hipótese de
    `CATALOGO_CANCELAMENTO`, com o fundamento legal já escrito, e um
    fundamento PRÓPRIO do caso, redigido por quem cancela — não basta
    escolher a hipótese, tem de dizer o que aconteceu neste título.

O QUE ESTE MODULO NAO FAZ, AINDA
    Nao emite selo, nao gera certidao e nao faz o retorno ao CRA. Sao os
    proximos passos de LEVANTAMENTO_PROTESTO.md. `TIPOS_ATO` lista o ciclo
    inteiro porque ele esta medido no acervo, nao porque este modulo o
    implemente — so `APONTAMENTO`, `INTIMACAO`, `PROTESTO`, `DESISTENCIA`,
    `PAGAMENTO` e `CANCELAMENTO` tem funcao que grava.

FUNDAMENTO
    Lei 9.492/1997, arts. 1o, 3o, 33 e 34.
    LEVANTAMENTO_PROTESTO.md e LAYOUT_CRA_MEDIDO.md — o acervo e o arquivo,
        medidos, e nao supostos.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any

import escrituracao as ESC
import protesto_cra as CRA
import protesto_termo as TERMO
from caixa_schema import centavos
from pt_schema import normalizar_nome


class ProtestoError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


# O titulo anda RECEBIDO -> APONTADO -> INTIMADO -> PROTESTADO -> CANCELADO,
# e pode receber PAGAMENTO em qualquer ponto ate PROTESTADO; ou para em
# DESISTIDO antes do protesto. O resto do ciclo (DEVOLVIDO, RETIRADO) esta
# documentado em LEVANTAMENTO_PROTESTO.md e ainda por construir.
SITUACOES_TITULO = ("RECEBIDO", "APONTADO", "INTIMADO", "PROTESTADO",
                    "DESISTIDO", "PAGO", "CANCELADO")

# Situacoes finais: nao ha mais o que fazer com o titulo por este modulo.
SITUACOES_FINAIS = ("DESISTIDO", "PAGO", "CANCELADO")

# As hipoteses de cancelamento do registro do protesto. O acervo tinha UM
# cadastro so — "Erro Material" — e os 56 cancelamentos reais saíram todos
# dele ou de campo livre, sem dizer qual das quatro coisas realmente
# aconteceu. `fundamento` e o texto legal, fixo; o CHAMADOR ainda escreve o
# fundamento PROPRIO do caso, em `lancar_cancelamento(fundamento=...)`.
CATALOGO_CANCELAMENTO: dict[str, dict[str, str]] = {
    "PAGAMENTO": {
        "rotulo": "Pagamento do título",
        "fundamento_legal": (
            "Lei 9.492/1997, art. 26 — apresentação do título ou documento "
            "de dívida protestado, com prova da quitação."),
    },
    "ANUENCIA_CREDOR": {
        "rotulo": "Anuência do credor",
        "fundamento_legal": (
            "Lei 9.492/1997, art. 26, § 1º — declaração de anuência, com "
            "firma reconhecida, de quem figurou como credor no registro do "
            "protesto, na impossibilidade de apresentar o título original."),
    },
    "ORDEM_JUDICIAL": {
        "rotulo": "Ordem judicial",
        "fundamento_legal": (
            "Decisão judicial determinando o cancelamento do registro do "
            "protesto."),
    },
    "ERRO_APRESENTANTE": {
        "rotulo": "Erro do apresentante",
        "fundamento_legal": (
            "Protesto lavrado por erro do apresentante ou do próprio "
            "cartório — título já pago, duplicado, ou encaminhado "
            "indevidamente a protesto."),
    },
}

# Como o titulo foi intimado. Diligencia (pessoal, por preposto ou correio
# com AR) primeiro; edital so quando a diligencia nao teve exito — mas este
# modulo nao impõe a ordem, so registra o que o balcao diz que aconteceu.
MODOS_INTIMACAO = ("PESSOAL", "EDITAL")

# O vocabulario inteiro dos atos da vida de um titulo — de tbAvisoProtesto e
# de atribuicoes.ATOS (atribuicao 2). So APONTAMENTO tem funcao nesta versao.
TIPOS_ATO = ("APONTAMENTO", "INTIMACAO", "PROTESTO", "PAGAMENTO",
             "CANCELAMENTO", "ARQUIVAMENTO", "CERTIDAO", "DESISTENCIA",
             "RETIRADA", "SUSTACAO", "REVOGACAO_SUSTACAO",
             "EFEITO_SUSPENSIVO", "REVOGACAO_EFEITO_SUSPENSIVO")

# OS DOIS INSTITUTOS, e o E-Oficio guarda os dois na mesma tabela:
# `tbProtesto_TipoEfeitoTitulo` tem `1 = Suspensivo` e `2 = Sustado`.
#
#   SUSTACAO ......... a ordem chega ANTES: o protesto nao se lavra.
#   EFEITO_SUSPENSIVO  a ordem chega DEPOIS: o registro fica, e a
#                      publicidade dele para.
#
# MEDIDO NO ACERVO: **uma** sustacao e **zero** efeitos suspensivos — o caso
# de 18/08/2025, protocolo 7792040002, «PROTESTADO POR ENGANO».
#
# E EU ATRIBUI ESSE CASO AO INSTITUTO ERRADO na primeira leitura. O texto e o
# nome da tabela (`tbProtesto_EfeitoSuspensivo`) me fizeram concluir que o
# titulo ja estava protestado. O dado do titulo diz o contrario:
# `snProtestado = 0`, sem livro nem folha, ocorrencia `3` (Retirado) na mesma
# data, e hoje PAGO. **O protesto nunca foi lavrado** — ordem que impede o ato
# e SUSTACAO. Bate com `intTipoEfeito = 2` (Sustado); o `id_tipoEfeito = 1` e
# que esta errado na linha.
#
# **Nome de tabela e afirmacao de quem a criou; o estado do titulo e o fato.**
ORDEM_JUDICIAL_E_A_REVOGACAO = {
    "SUSTACAO": "REVOGACAO_SUSTACAO",
    "EFEITO_SUSPENSIVO": "REVOGACAO_EFEITO_SUSPENSIVO",
}

# OS ATOS QUE A SUSTACAO JUDICIAL BLOQUEIA — Lei 9.492/1997, art. 17, § 1o:
# o titulo sustado «so podera ser PAGO, PROTESTADO ou RETIRADO com autorizacao
# judicial».
#
# SAO TRES, E NAO UM. Ao construir isto eu ia bloquear so o protesto — e o
# paragrafo bloqueia tambem o pagamento e a retirada. Receber o dinheiro de um
# titulo que o juiz mandou parar e tao grave quanto lavrar o ato.
#
# `DESISTENCIA` entra como a RETIRADA do artigo: e o pedido do credor de tirar
# o titulo antes do protesto, e o proprio art. 17, § 1o o condiciona a
# autorizacao judicial quando ha sustacao (Gentil, cap. 7, [p. 2566]).
ATOS_QUE_A_SUSTACAO_BLOQUEIA = ("PROTESTO", "PAGAMENTO", "DESISTENCIA",
                                "RETIRADA")

ORIGENS_TITULO = ("CRA", "CENPROT", "MANUAL")

# AS ESPECIES QUE ESTA CASA USOU, e quantas vezes cada uma. Medido em
# 25/08/2026 nos 1.366 titulos do acervo (`tbAvisoProtesto.strEspecie`).
#
# NAO E RESTRICAO: o contrato da CRA tem 64 especies e todas continuam
# valendo. Isto ORDENA a lista da tela, para o balcao achar primeiro o que
# usa todo dia — dois tercos dos titulos desta serventia sao DMI, e procurar
# "duplicata mercantil por indicacao" no meio de 64 linhas alfabeticas custa
# tempo em toda apresentacao.
#
# ATC e CTI estao aqui e NAO estao no esquema oficial; quem trata disso e
# `protesto_cra.ESPECIES_FORA_DO_ESQUEMA`, que as aceita com observacao.
ESPECIES_USADAS_POR_ESTA_CASA: dict[str, int] = {
    "DMI": 911, "CDA": 353, "CBI": 62, "DSI": 16, "DM": 6, "ATC": 6,
    "NP": 4, "CTI": 4, "SJ": 3, "FPS": 1,
}


def especies_para_escolher() -> list[dict]:
    """As especies para a tela: as desta casa primeiro, o resto depois.

    Nao le banco nenhum. Cada item traz `vezes` — quantas vezes a casa usou —
    e `no_esquema`, que e falso nas duas que o contrato oficial nao tem.
    """
    saida = []
    for codigo, vezes in ESPECIES_USADAS_POR_ESTA_CASA.items():
        d = CRA.especie(codigo)
        saida.append({**d, "vezes": vezes, "desta_casa": True})
    for codigo, rotulo in sorted(CRA.ESPECIES.items()):
        if codigo not in ESPECIES_USADAS_POR_ESTA_CASA:
            saida.append({"codigo": codigo, "rotulo": rotulo, "vezes": 0,
                          "no_esquema": True, "observacao": None,
                          "desta_casa": False})
    return saida

SERIE_APONTAMENTO = "PT_APONTAMENTO"
SERIE_PROTESTO = "PT_PROTESTO"
SERIE_PAGAMENTO = "PT_PAGAMENTO"


# --------------------------------------------------------------- consultas


def titulo(con: sqlite3.Connection, titulo_id: int) -> sqlite3.Row | None:
    """O titulo, com tudo que foi cadastrado. So LE."""
    return con.execute(
        "SELECT * FROM pt_titulos WHERE id=?", (int(titulo_id),)).fetchone()


def devedores_do(con: sqlite3.Connection, titulo_id: int) -> list[sqlite3.Row]:
    """Os devedores do titulo, na ordem em que entraram. So LE."""
    return list(con.execute(
        "SELECT * FROM pt_devedores WHERE titulo_id=? ORDER BY id",
        (int(titulo_id),)))


def atos_do(con: sqlite3.Connection, titulo_id: int) -> list[sqlite3.Row]:
    """Os atos ja lancados para o titulo, na ordem em que aconteceram. So LE."""
    return list(con.execute(
        "SELECT * FROM pt_atos WHERE titulo_id=? ORDER BY id",
        (int(titulo_id),)))


def titulo_por_origem(con: sqlite3.Connection, origem: str,
                      origem_chave: str) -> sqlite3.Row | None:
    """O titulo de uma chave de origem, ou None. So LE."""
    return con.execute(
        "SELECT * FROM pt_titulos WHERE origem=? AND origem_chave=?",
        (origem, origem_chave)).fetchone()


# ------------------------------------------------------------- o cadastro


def cadastrar_titulo(con: sqlite3.Connection, dados: dict, *, origem: str,
                     origem_chave: str | None = None,
                     importacao_id: int | None = None,
                     usuario: str | None = None, agora: str) -> int:
    """Cadastra o titulo. ESCREVE. Devolve o id.

    `dados` esta no vocabulario de `protesto_arquivo.para_apontamento()`.
    Recusa o que o contrato oficial da CRA recusa — `protesto_cra.
    conferir_titulo()` — porque um titulo com codigo que a Central nao
    reconhece nao sai daqui para lugar nenhum.

    Reapresentar a mesma (origem, origem_chave) devolve o id ja cadastrado:
    carga repetivel por construcao, como o resto da casa.
    """
    if origem not in ORIGENS_TITULO:
        raise ProtestoError(
            f"Origem de título desconhecida: {origem!r}. As que existem são "
            f"{', '.join(ORIGENS_TITULO)}.")
    chave = (origem_chave or "").strip() or None
    if origem in ("CRA", "CENPROT") and not chave:
        raise ProtestoError(
            f"Título de origem {origem} precisa de uma chave de origem, para "
            f"a carga poder ser repetida sem duplicar.")
    faltas = CRA.conferir_titulo(dados)
    if faltas:
        raise ProtestoError(
            "O título não passa no contrato da CRA: " + "; ".join(faltas))
    if chave:
        existente = titulo_por_origem(con, origem, chave)
        if existente:
            return int(existente["id"])

    cedente = dados.get("cedente") or {}
    cur = con.execute(
        """INSERT INTO pt_titulos(
               especie, numero_titulo, nosso_numero, chave_cenprot,
               data_emissao, data_vencimento, tipo_moeda, valor_centavos,
               saldo_centavos, praca_protesto, tipo_protesto, tipo_endosso,
               aceite, motivo_protesto, irregularidades_json,
               apresentante_codigo, apresentante_nome,
               cedente_nome, cedente_documento, cedente_endereco,
               cedente_cep, cedente_cidade, cedente_uf,
               situacao, origem, origem_chave, importacao_id,
               criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (dados.get("especie"), dados.get("numero_titulo"), dados.get("nosso_numero"),
         dados.get("chave_cenprot"), dados.get("data_emissao"),
         dados.get("data_vencimento"), dados.get("tipo_moeda") or "1",
         centavos(dados.get("valor")), centavos(dados.get("saldo")),
         dados.get("praca_protesto"), dados.get("tipo_protesto"),
         dados.get("tipo_endosso"), dados.get("aceite"), dados.get("motivo_protesto"),
         json.dumps(dados.get("irregularidades") or [], ensure_ascii=False),
         (dados.get("apresentante_codigo") or None),
         (dados.get("apresentante_nome") or None),
         cedente.get("nome"), cedente.get("documento"), cedente.get("endereco"),
         cedente.get("cep"), cedente.get("cidade"), cedente.get("uf"),
         "RECEBIDO", origem, chave, importacao_id, agora, usuario))
    titulo_id = int(cur.lastrowid)

    for devedor in dados.get("devedores") or []:
        documento_tipo = ("CNPJ" if devedor.get("CNPJ")
                          else "CPF" if devedor.get("CPF") else None)
        documento_numero = devedor.get("CNPJ") or devedor.get("CPF")
        endereco = (devedor.get("enderecos") or [{}])[0]
        con.execute(
            """INSERT INTO pt_devedores(titulo_id, nome, nome_norm,
                   documento_tipo, documento_numero, endereco, bairro, cep,
                   cidade, uf)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (titulo_id, devedor.get("nome"),
             normalizar_nome(devedor.get("nome")),
             documento_tipo, documento_numero,
             endereco.get("endereco"), endereco.get("bairro"),
             endereco.get("cep"), endereco.get("cidade"), endereco.get("uf")))
    return titulo_id


# ----------------------------------------------------------- o protocolo


def numero_do_protocolo(con: sqlite3.Connection, dia: str) -> str:
    """O protocolo da casa: AAMMDD mais o sequencial do dia, com 4 digitos.

    E A FORMA QUE ESTA CASA USA HOJE, medida em 25/08/2026 no acervo. No
    E-Oficio o protocolo e `intProtocolo`, igual a `strCB` nos 1.365 (100%), e
    desde 2024 ele e a data de entrada em AAMMDD seguida do sequencial do dia:
    928 dos 931. Antes de 2024 havia outro esquema — `7797140001` para
    14/02/2022 —, que nao se reproduz: o que vale e o que a casa faz agora.

    O NUMERO SAI DA CONTA DO DIA, e nao de um contador a parte. O Livro de
    Protocolo do Protesto tem numeracao diaria — reinicia sozinha —, e por
    isso nao ha contador em `nu_numeracao` para semear. Contar o que ja saiu
    hoje e o mesmo que `escrituracao._proximo_do_dia` faz para as series
    diarias, sem precisar de livro aberto: a geometria do Livro de Protocolo
    (quantos por face) e pendencia em aberto, e escrever nele antes de
    conferir seria inventar.
    """
    d = str(dia)[:10]
    prefixo = d[2:4] + d[5:7] + d[8:10]
    linha = con.execute(
        """SELECT COUNT(*) n FROM pt_titulos
            WHERE protocolo IS NOT NULL AND protocolo LIKE ?""",
        (f"{prefixo}%",)).fetchone()
    return f"{prefixo}{int(linha['n']) + 1:04d}"


# ----------------------------------------------------------- o apontamento


def lancar_apontamento(con: sqlite3.Connection, titulo_id: int, *, sv: dict,
                       agora: str, data_extenso: str,
                       usuario: str | None = None,
                       origem: str = "MANUAL") -> dict:
    """Lanca o apontamento no Livro de Apontamento. ESCREVE.

    E o primeiro ato da vida do titulo — Lei 9.492/1997, art. 3o. Recusa
    apontar de novo o que ja foi apontado: um titulo tem um apontamento, nao
    dois. O lugar sai de `escrituracao.reservar()`, na serie
    PT_APONTAMENTO — 52 registros por face, sem verso, medido no acervo.

    O ato entra PRIMEIRO na tabela e o lugar depois, como em toda a casa: se
    a reserva falhar por falta de folha, a transacao volta atras inteira e
    nao sobra ato sem lugar.
    """
    tit = titulo(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    if tit["situacao"] != "RECEBIDO":
        raise ProtestoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — não se aponta de novo.")

    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem, criado_em,
               criado_por)
           VALUES (?,?,?,?,?,?)""",
        (titulo_id, "APONTAMENTO", agora, origem, agora, usuario))
    ato_id = int(cur.lastrowid)

    # O PROTOCOLO NASCE AQUI, com o apontamento — e o numero que volta para a
    # CRA na posicao 448 do retorno. Titulo que ja tem protocolo (veio do
    # acervo com ele) fica com o que tinha: renumerar apagaria o que a Central
    # ja conhece.
    if not (tit["protocolo"] or "").strip():
        con.execute("UPDATE pt_titulos SET protocolo=? WHERE id=?",
                    (numero_do_protocolo(con, agora), titulo_id))

    lugar = ESC.reservar(con, SERIE_APONTAMENTO, "pt_atos", ato_id, sv=sv,
                         agora=agora, data_extenso=data_extenso, paginas=1,
                         usuario=usuario)
    con.execute(
        """UPDATE pt_atos SET livro_id=?, folha=?, verso=?, numero_ordem=?,
                              rotulo=? WHERE id=?""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    con.execute("UPDATE pt_titulos SET situacao='APONTADO' WHERE id=?",
               (titulo_id,))
    return {"ato_id": ato_id, "titulo_id": titulo_id, **lugar}


# ------------------------------------------------------------ a intimacao


def lancar_intimacao(con: sqlite3.Connection, titulo_id: int, *, modo: str,
                     agora: str, usuario: str | None = None,
                     digital: bool = False, codigo_edital: str | None = None,
                     comprovante: str | None = None,
                     origem: str = "MANUAL") -> dict:
    """Registra uma intimação do título. ESCREVE. NÃO calcula prazo.

    Só registra o que aconteceu — modo, diligência, comprovante —, porque o
    acervo do E-Ofício nunca controlou data de intimação (ver o cabeçalho de
    `pt_schema.py`) e contar o prazo é decisão jurídica do oficial, ainda
    não tomada. Não há trava de "uma só": intimação pessoal sem êxito,
    seguida de edital, são duas linhas, não um erro.

    Não ocupa lugar em livro — o acervo não guarda Livro de Intimação
    separado, só o selo e a taxa de diligência ou de edital.
    """
    if modo not in MODOS_INTIMACAO:
        raise ProtestoError(
            f"Modo de intimação desconhecido: {modo!r}. Os que existem são "
            f"{', '.join(MODOS_INTIMACAO)}.")
    tit = titulo(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    if tit["situacao"] not in ("APONTADO", "INTIMADO"):
        raise ProtestoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — só se intima título já apontado.")
    if modo == "EDITAL" and not (codigo_edital or "").strip():
        raise ProtestoError(
            "Intimação por edital exige o código do edital.")

    detalhe = {"modo": modo, "digital": bool(digital)}
    if codigo_edital:
        detalhe["codigo_edital"] = codigo_edital.strip()
    if comprovante:
        detalhe["comprovante"] = comprovante.strip()

    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?)""",
        (titulo_id, "INTIMACAO", agora, json.dumps(detalhe, ensure_ascii=False),
         origem, agora, usuario))
    con.execute("UPDATE pt_titulos SET situacao='INTIMADO' WHERE id=?",
               (titulo_id,))
    return {"ato_id": int(cur.lastrowid), "titulo_id": titulo_id, **detalhe}


# --------------------------------------------------- o protesto e a desistencia


def esperando_protesto(con: sqlite3.Connection, *, hoje: str,
                       limite: int = 300) -> list[dict]:
    """Os títulos intimados e SEM MOVIMENTAÇÃO desde a intimação. Só LÊ.

    É o passo da tarde do roteiro do oficial: «gerar protesto, sem
    movimentação, calcular, listar, gerar». Até 31/08/2026 ele não tinha tela
    nenhuma, e o título intimado ficava esperando alguém lembrar dele.

    O PRAZO NÃO SE CALCULA AQUI, e isso é decisão do oficial de 24/08/2026: o
    acervo nunca controlou data de intimação, e contar o tríduo é decisão
    jurídica que esta casa não delegou ao programa. A lista devolve
    `dias_desde_a_intimacao` — que é **contagem, e não juízo**: quem diz se o
    prazo venceu, e se o protesto sai, é quem assina.

    SEM MOVIMENTAÇÃO QUER DIZER SEM ATO POSTERIOR. Não basta a situação estar
    `INTIMADO`: um pagamento lançado hoje muda a situação, mas o que importa é
    que **nenhum ato entrou depois da intimação** — e é assim que a consulta
    pergunta, olhando o `id` do ato, que é a ordem em que eles foram lavrados.
    """
    linhas = con.execute(
        """SELECT t.id, t.numero_titulo, t.nosso_numero, t.protocolo,
                  t.especie, t.valor_centavos, t.saldo_centavos, t.situacao,
                  i.data_ato data_da_intimacao, i.detalhe_json,
                  i.numero_ordem numero_da_intimacao
             FROM pt_titulos t
             JOIN pt_atos i ON i.id = (
                    SELECT MAX(a.id) FROM pt_atos a
                     WHERE a.titulo_id = t.id AND a.tipo = 'INTIMACAO')
            WHERE t.situacao = 'INTIMADO'
              AND NOT EXISTS (SELECT 1 FROM pt_atos d
                               WHERE d.titulo_id = t.id AND d.id > i.id)
              -- O SUSTADO NAO ENTRA NESTA FILA. O `NOT EXISTS` de cima ja o
              -- tiraria quando a ordem chega DEPOIS da intimacao — mas ela
              -- pode chegar antes, e ai o titulo continuaria aqui. Lei
              -- 9.492/1997, art. 17: sustado nao se protesta.
              AND NOT EXISTS (
                    SELECT 1 FROM pt_atos s
                     WHERE s.titulo_id = t.id AND s.cancelado = 0
                       AND s.tipo = 'SUSTACAO'
                       AND s.id > COALESCE((SELECT MAX(r.id) FROM pt_atos r
                                             WHERE r.titulo_id = t.id
                                               AND r.cancelado = 0
                                               AND r.tipo = 'REVOGACAO_SUSTACAO'
                                            ), 0))
            ORDER BY i.data_ato, t.id
            LIMIT ?""", (int(limite),)).fetchall()

    saida = []
    for linha in linhas:
        d = dict(linha)
        d["dias_desde_a_intimacao"] = _dias_entre(d.get("data_da_intimacao"),
                                                  hoje)
        # O MODO DA INTIMAÇÃO — pessoal ou por edital — mora no `detalhe_json`,
        # e não em coluna: `pt_atos` guarda o que varia de um tipo de ato para
        # outro ali. Saber qual dos dois foi importa na tela, porque o edital é
        # a rotina desta casa (1.092 de 1.618 avisos foram publicados).
        try:
            d["modo_da_intimacao"] = (json.loads(d.get("detalhe_json") or "{}")
                                      .get("modo") or "")
        except (TypeError, ValueError):
            d["modo_da_intimacao"] = ""
        d["devedores"] = [dict(r) for r in con.execute(
            "SELECT nome, documento_numero FROM pt_devedores WHERE titulo_id=?",
            (d["id"],))]
        saida.append(d)
    return saida


def sustacao_revogada(con: sqlite3.Connection, *, hoje: str,
                      limite: int = 300) -> list[dict]:
    """Os títulos cuja sustação foi revogada e que ainda não foram protestados.

    **É A LISTA MAIS URGENTE DO PROTESTO**, e até 01/09/2026 ela não existia —
    pior, esses títulos eram invisíveis: depois de sustar e revogar há dois
    atos posteriores à intimação, e a fila do «A protestar» os excluía para
    sempre.

    Lei 9.492/1997, art. 17, § 2º: *«Revogada a ordem de sustação, não há
    necessidade de se proceder a nova intimação do devedor, sendo a lavratura
    e o registro do protesto efetivados até o PRIMEIRO DIA ÚTIL SUBSEQUENTE ao
    do recebimento da revogação (...)»*

    **NÃO HÁ NOVA INTIMAÇÃO**, e isso é do parágrafo: o devedor já sabia da
    apresentação quando entrou com a ação. Por isso o título volta a protestar
    direto, sem repetir o aviso.

    `dias_desde_a_revogacao` é **contagem, e não juízo** — a mesma regra do
    tríduo, que o oficial fixou em 24/08/2026. E conta-se do **recebimento**
    da revogação, que é o que o parágrafo manda, e não da data da decisão.
    """
    linhas = con.execute(
        """SELECT t.id, t.numero_titulo, t.nosso_numero, t.protocolo,
                  t.especie, t.valor_centavos, t.saldo_centavos, t.situacao,
                  r.data_ato data_da_revogacao, r.detalhe_json
             FROM pt_titulos t
             JOIN pt_atos r ON r.id = (
                    SELECT MAX(a.id) FROM pt_atos a
                     WHERE a.titulo_id = t.id AND a.cancelado = 0
                       AND a.tipo IN ('SUSTACAO','REVOGACAO_SUSTACAO'))
            WHERE r.tipo = 'REVOGACAO_SUSTACAO'
              AND t.situacao NOT IN ('PROTESTADO','PAGO','CANCELADO',
                                     'DESISTIDO','RETIRADO')
            ORDER BY r.data_ato, t.id
            LIMIT ?""", (int(limite),)).fetchall()

    saida = []
    for linha in linhas:
        d = dict(linha)
        d["dias_desde_a_revogacao"] = _dias_entre(d.get("data_da_revogacao"),
                                                  hoje)
        try:
            ordem = json.loads(d.get("detalhe_json") or "{}")
        except (TypeError, ValueError):
            ordem = {}
        d["juizo"] = ordem.get("juizo") or ""
        d["processo"] = ordem.get("processo") or ""
        d["devedores"] = [dict(x) for x in con.execute(
            "SELECT nome, documento_numero FROM pt_devedores WHERE titulo_id=?",
            (d["id"],))]
        saida.append(d)
    return saida


def sustados(con: sqlite3.Connection, limite: int = 300) -> list[dict]:
    """Os títulos com o protesto sustado por ordem judicial. Só LÊ.

    Eles ficam **à disposição do Juízo** (art. 17, caput), e não se pagam, não
    se protestam e não se retiram sem autorização judicial (§ 1º). Uma lista
    própria existe porque eles não aparecem em nenhuma outra: saíram da fila
    do «A protestar» de propósito, e sem esta tela ninguém sabe que existem.
    """
    linhas = con.execute(
        """SELECT t.id, t.numero_titulo, t.nosso_numero, t.protocolo,
                  t.especie, t.saldo_centavos, t.situacao,
                  s.data_ato data_da_sustacao, s.detalhe_json
             FROM pt_titulos t
             JOIN pt_atos s ON s.id = (
                    SELECT MAX(a.id) FROM pt_atos a
                     WHERE a.titulo_id = t.id AND a.cancelado = 0
                       AND a.tipo IN ('SUSTACAO','REVOGACAO_SUSTACAO'))
            WHERE s.tipo = 'SUSTACAO'
            ORDER BY s.data_ato, t.id
            LIMIT ?""", (int(limite),)).fetchall()
    saida = []
    for linha in linhas:
        d = dict(linha)
        try:
            ordem = json.loads(d.get("detalhe_json") or "{}")
        except (TypeError, ValueError):
            ordem = {}
        d["juizo"] = ordem.get("juizo") or ""
        d["processo"] = ordem.get("processo") or ""
        d["devedores"] = [dict(x) for x in con.execute(
            "SELECT nome, documento_numero FROM pt_devedores WHERE titulo_id=?",
            (d["id"],))]
        saida.append(d)
    return saida


def _dias_entre(de: Any, ate: Any) -> int | None:
    """Quantos dias correram. CONTAGEM, e não juízo sobre o prazo.

    Devolve None quando falta uma das datas — e None não vira zero na tela:
    zero diria «foi intimado hoje», que é afirmação, e não saber é outra coisa.
    """
    try:
        a = date.fromisoformat(str(de or "")[:10])
        b = date.fromisoformat(str(ate or "")[:10])
    except ValueError:
        return None
    return (b - a).days


def _ordem_em_vigor(con: sqlite3.Connection, titulo_id: int,
                    ordem: str) -> dict | None:
    """A ordem judicial daquele tipo que está valendo, ou None. Só LÊ.

    VALE A ÚLTIMA PALAVRA DO JUÍZO, e é por isso que se olha o ato mais
    recente entre os dois — a ordem e a revogação dela — e não se conta
    quantos há de cada. A mesma ordem pode ser dada, revogada e dada de novo;
    somar daria a resposta errada na segunda vez.
    """
    revogacao = ORDEM_JUDICIAL_E_A_REVOGACAO[ordem]
    linha = con.execute(
        """SELECT id, tipo, data_ato, detalhe_json
             FROM pt_atos
            WHERE titulo_id = ? AND tipo IN (?, ?) AND cancelado = 0
            ORDER BY id DESC LIMIT 1""",
        (int(titulo_id), ordem, revogacao)).fetchone()
    if linha is None or linha["tipo"] != ordem:
        return None
    d = dict(linha)
    try:
        d.update(json.loads(d.get("detalhe_json") or "{}"))
    except (TypeError, ValueError):
        pass
    return d


def sustacao_em_vigor(con: sqlite3.Connection, titulo_id: int) -> dict | None:
    """A ordem que IMPEDE o protesto — art. 17. Só LÊ."""
    return _ordem_em_vigor(con, titulo_id, "SUSTACAO")


def efeito_suspensivo_em_vigor(con: sqlite3.Connection,
                               titulo_id: int) -> dict | None:
    """A ordem que SUSPENDE OS EFEITOS de um protesto já lavrado. Só LÊ.

    É o outro instituto, e **esta casa nunca o usou**: o único caso do acervo,
    de 18/08/2025, é uma SUSTAÇÃO — o título nunca chegou a ser protestado.

    Ele existe assim mesmo, e por razão que não depende de frequência: o
    registro fica no livro, e o que para é a **publicidade** dele — quem lê
    isto é a certidão, o papel que faz o banco negar crédito.
    """
    return _ordem_em_vigor(con, titulo_id, "EFEITO_SUSPENSIVO")


def _recusar_se_sustado(con: sqlite3.Connection, titulo_id: int,
                        que_ato: str) -> None:
    """Lei 9.492/1997, art. 17, § 1º. Recusa com a ordem na mensagem.

    A MENSAGEM DIZ QUAL É A ORDEM, e não só que existe uma: quem está no
    balcão com o cliente na frente precisa do juízo e do processo para
    explicar, e para pedir a autorização judicial que o parágrafo exige.
    """
    ordem = sustacao_em_vigor(con, titulo_id)
    if not ordem:
        return
    onde = " ".join(x for x in (str(ordem.get("juizo") or "").strip(),
                                str(ordem.get("processo") or "").strip()) if x)
    raise ProtestoError(
        f"Este título está com o protesto SUSTADO por ordem judicial"
        f"{(' — ' + onde) if onde else ''}, recebida em "
        f"{ordem.get('data_ato') or 'data não informada'}. "
        f"Pela Lei 9.492/1997, art. 17, § 1º, ele só pode ser pago, "
        f"protestado ou retirado COM AUTORIZAÇÃO JUDICIAL — e por isso "
        f"{que_ato} não pode ser lançado aqui. Se a ordem foi revogada, "
        f"registre a revogação antes.")


def lancar_sustacao(con: sqlite3.Connection, titulo_id: int, *,
                    juizo: str, processo: str, agora: str,
                    recebido_em: str | None = None,
                    observacao: str | None = None,
                    usuario: str | None = None,
                    origem: str = "MANUAL") -> dict:
    """Registra a ordem judicial que susta o protesto. ESCREVE.

    Lei 9.492/1997, art. 17: *«Permanecerão no Tabelionato, à disposição do
    Juízo respectivo, os títulos ou documentos de dívida cujo protesto for
    judicialmente sustado.»*

    O JUÍZO E O PROCESSO SÃO OBRIGATÓRIOS, e não é burocracia: a sustação só
    se levanta por ordem do mesmo juízo, e sem o número do processo o balcão
    não tem como conferir a procedência do mandado nem como pedir a
    autorização que o § 1º exige. **Um campo em branco aqui vira, meses
    depois, um título parado que ninguém sabe por quê.**

    E O SISTEMA NÃO JULGA A ORDEM. Ela vem do juiz; ao tabelião cabe cumprir.
    Este módulo não pergunta se ela procede — pergunta apenas de quem é.

    **NÃO SE SUSTA DUAS VEZES.** Se já há ordem em vigor, a segunda seria um
    registro que não muda nada e que faz a ficha contar duas.
    """
    tit = titulo(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    if sustacao_em_vigor(con, titulo_id):
        raise ProtestoError(
            f"O título {tit['numero_titulo']} já está sustado por ordem "
            f"judicial. Para mudar a ordem, registre primeiro a revogação.")
    quem = str(juizo or "").strip()
    autos = str(processo or "").strip()
    if not quem or not autos:
        raise ProtestoError(
            "Informe o juízo e o número do processo da ordem de sustação. "
            "Sem eles não há como conferir a procedência do mandado, nem "
            "como pedir depois a autorização judicial que o art. 17, § 1º, "
            "da Lei 9.492/1997 exige para pagar, protestar ou retirar.")

    detalhe = json.dumps({"juizo": quem, "processo": autos,
                          "observacao": str(observacao or "").strip()},
                         ensure_ascii=False)
    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (?,'SUSTACAO',?,?,?,?,?)""",
        (titulo_id, recebido_em or agora, detalhe, origem, agora, usuario))
    return {"ato_id": int(cur.lastrowid), "titulo_id": titulo_id,
            "juizo": quem, "processo": autos}


def lancar_revogacao_sustacao(con: sqlite3.Connection, titulo_id: int, *,
                              agora: str, recebido_em: str | None = None,
                              observacao: str | None = None,
                              usuario: str | None = None,
                              origem: str = "MANUAL") -> dict:
    """Registra a revogação da ordem de sustação. ESCREVE.

    Lei 9.492/1997, art. 17, § 2º: *«Revogada a ordem de sustação, não há
    necessidade de se proceder a nova intimação do devedor, sendo a lavratura
    e o registro do protesto efetivados até o primeiro dia útil subsequente ao
    do recebimento da revogação (...)»*

    **A DATA DO RECEBIMENTO É O QUE CONTA**, e não a da decisão: é dela que o
    parágrafo faz correr o prazo. Por isso ela é campo próprio — o mandado
    pode levar dias para chegar, e o prazo é de um dia útil.

    **NÃO SE PROTESTA SOZINHO.** O prazo é curto e está na lei, mas quem lavra
    é quem assina — a mesma regra do tríduo, que o oficial fixou em
    24/08/2026. O sistema conta e mostra; a tela «A protestar» destaca.

    E NÃO SE REVOGA O QUE NÃO ESTÁ SUSTADO: seria registrar o levantamento de
    uma ordem que não existe.
    """
    tit = titulo(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    ordem = sustacao_em_vigor(con, titulo_id)
    if not ordem:
        raise ProtestoError(
            f"O título {tit['numero_titulo']} não está sustado — não há "
            f"ordem de sustação em vigor para revogar.")

    detalhe = json.dumps({"juizo": ordem.get("juizo", ""),
                          "processo": ordem.get("processo", ""),
                          "sustacao_ato_id": ordem.get("id"),
                          "observacao": str(observacao or "").strip()},
                         ensure_ascii=False)
    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (?,'REVOGACAO_SUSTACAO',?,?,?,?,?)""",
        (titulo_id, recebido_em or agora, detalhe, origem, agora, usuario))
    return {"ato_id": int(cur.lastrowid), "titulo_id": titulo_id,
            "recebido_em": recebido_em or agora}


def lancar_efeito_suspensivo(con: sqlite3.Connection, titulo_id: int, *,
                            juizo: str, processo: str, agora: str,
                            recebido_em: str | None = None,
                            observacao: str | None = None,
                            usuario: str | None = None,
                            origem: str = "MANUAL") -> dict:
    """Suspende os EFEITOS de um protesto já lavrado, por ordem judicial.

    A sustação impede o ato; esta ordem chega **depois** dele.

    **E esta casa nunca a usou**: o único caso do acervo, de 18/08/2025, é uma
    sustação — o título nunca foi protestado, e hoje está PAGO. Ela existe
    porque o dano que evita não depende de frequência.

    **O REGISTRO NÃO SAI DO LIVRO.** O que para é a publicidade: o
    cumprimento da ordem recebida depois da lavratura se dá por **averbação,
    de ofício, no respectivo registro**, consignando que os efeitos do
    protesto foram suspensos por determinação judicial. Apagar o protesto
    seria fazer sumir um ato lavrado; deixá-lo publicando é o dano que o juiz
    mandou parar.

    **SÓ CABE SOBRE TÍTULO PROTESTADO.** Antes do protesto o instituto é
    outro — a sustação —, e usar um pelo outro faria a certidão dizer que há
    efeito suspenso sobre um protesto que não existe.
    """
    tit = titulo(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    protestado = con.execute(
        """SELECT 1 FROM pt_atos WHERE titulo_id=? AND tipo='PROTESTO'
            AND cancelado = 0 LIMIT 1""", (int(titulo_id),)).fetchone()
    if not protestado:
        raise ProtestoError(
            f"O título {tit['numero_titulo']} não tem protesto lavrado — não "
            f"há efeito a suspender. Antes do protesto a ordem judicial é de "
            f"SUSTAÇÃO, que impede o ato: registre-a como sustação.")
    if efeito_suspensivo_em_vigor(con, titulo_id):
        raise ProtestoError(
            f"Os efeitos do protesto do título {tit['numero_titulo']} já "
            f"estão suspensos por ordem judicial. Para mudar a ordem, "
            f"registre primeiro a revogação.")
    quem = str(juizo or "").strip()
    autos = str(processo or "").strip()
    if not quem or not autos:
        raise ProtestoError(
            "Informe o juízo e o número do processo da ordem. Sem eles a "
            "certidão não tem como dizer de quem é a determinação que "
            "suspendeu os efeitos deste protesto.")

    detalhe = json.dumps({"juizo": quem, "processo": autos,
                          "observacao": str(observacao or "").strip()},
                         ensure_ascii=False)
    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (?,'EFEITO_SUSPENSIVO',?,?,?,?,?)""",
        (titulo_id, recebido_em or agora, detalhe, origem, agora, usuario))
    return {"ato_id": int(cur.lastrowid), "titulo_id": titulo_id,
            "juizo": quem, "processo": autos}


def lancar_revogacao_efeito_suspensivo(
        con: sqlite3.Connection, titulo_id: int, *, agora: str,
        recebido_em: str | None = None, observacao: str | None = None,
        usuario: str | None = None, origem: str = "MANUAL") -> dict:
    """Revoga a suspensão dos efeitos: o protesto volta a publicar. ESCREVE.

    E é por isso que ela é ato próprio, e não um `UPDATE`: o dia em que o
    protesto voltou a valer é fato que a certidão de amanhã pode ter de
    explicar.
    """
    tit = titulo(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    ordem = efeito_suspensivo_em_vigor(con, titulo_id)
    if not ordem:
        raise ProtestoError(
            f"O protesto do título {tit['numero_titulo']} não está com os "
            f"efeitos suspensos — não há o que revogar.")
    detalhe = json.dumps({"juizo": ordem.get("juizo", ""),
                          "processo": ordem.get("processo", ""),
                          "efeito_ato_id": ordem.get("id"),
                          "observacao": str(observacao or "").strip()},
                         ensure_ascii=False)
    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (?,'REVOGACAO_EFEITO_SUSPENSIVO',?,?,?,?,?)""",
        (titulo_id, recebido_em or agora, detalhe, origem, agora, usuario))
    return {"ato_id": int(cur.lastrowid), "titulo_id": titulo_id}


def lancar_protesto(con: sqlite3.Connection, titulo_id: int, *, sv: dict,
                    agora: str, data_extenso: str,
                    usuario: str | None = None,
                    origem: str = "MANUAL",
                    modelo_do_termo: str | None = None) -> dict:
    """Lavra o protesto no Livro de Registro de Protestos. ESCREVE.

    Exige que o título já tenha sido intimado (Lei 9.492/1997, art. 14) —
    mas NÃO confere se o prazo da intimação venceu, pela mesma razão de
    `lancar_intimacao()`: essa conta ainda não foi decidida pelo oficial.
    Recusa protestar de novo o que já foi protestado ou desistido.

    O lugar sai de `escrituracao.reservar()` na série PT_PROTESTO — um
    registro por FACE, sem folha nova: medido no acervo, os livros 7 e 8
    fecharam com 207 e 219 registros em 200 folhas, o que só fecha se o
    verso leva o protesto seguinte.
    """
    tit = titulo(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    # Art. 17, § 1o: sustado so se protesta com autorizacao judicial.
    _recusar_se_sustado(con, titulo_id, "o protesto")
    if tit["situacao"] != "INTIMADO":
        raise ProtestoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — só se protesta título já intimado.")

    # O TEXTO QUE VAI NO LIVRO, montado dos fatos deste titulo — e ele
    # CONGELA aqui: e o que foi escrito naquele dia. Medido: o E-Oficio o
    # escreveu em 1.132 dos 1.164 protestos, e este sistema nao escrevia
    # nenhum. Ver `protesto_termo`.
    #
    # `modelo` e `base` vem do catalogo que o oficial edita quando a rota os
    # passa; sem eles vale o texto desta casa, copiado do E-Oficio.
    fatos = TERMO.dados_do_titulo(con, titulo_id)
    texto = TERMO.montar(modelo=modelo_do_termo,
                         edital_data=fatos["edital_data"],
                         edital_motivo=fatos["edital_motivo"])
    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, teor, origem,
               criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?)""",
        (titulo_id, "PROTESTO", agora, texto, origem, agora, usuario))
    ato_id = int(cur.lastrowid)

    lugar = ESC.reservar(con, SERIE_PROTESTO, "pt_atos", ato_id, sv=sv,
                         agora=agora, data_extenso=data_extenso, paginas=1,
                         usuario=usuario)
    con.execute(
        """UPDATE pt_atos SET livro_id=?, folha=?, verso=?, numero_ordem=?,
                              rotulo=? WHERE id=?""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    con.execute("UPDATE pt_titulos SET situacao='PROTESTADO' WHERE id=?",
               (titulo_id,))
    return {"ato_id": ato_id, "titulo_id": titulo_id, **lugar}


def lancar_desistencia(con: sqlite3.Connection, titulo_id: int, *,
                       motivo: str, agora: str, usuario: str | None = None,
                       origem: str = "MANUAL") -> dict:
    """Registra a desistência do CREDOR, antes de o protesto ser lavrado. ESCREVE.

    Só cabe enquanto o título não foi protestado: tirar protesto já lavrado
    é cancelamento, com o catálogo de hipóteses da Lei 9.492/1997 — ainda
    por construir neste módulo, e não é a mesma coisa. Não ocupa lugar em
    livro: a desistência não tem série própria no acervo.
    """
    tit = titulo(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    # Art. 17, § 1o: sustado so se retira com autorizacao judicial — e a
    # desistencia e a retirada do titulo pelo credor, antes do protesto.
    _recusar_se_sustado(con, titulo_id, "a desistência")
    if tit["situacao"] not in ("RECEBIDO", "APONTADO", "INTIMADO"):
        raise ProtestoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — só se desiste antes do protesto lavrado.")
    razao = (motivo or "").strip()
    if len(razao) < 5:
        raise ProtestoError("Escreva o motivo da desistência.")

    detalhe = {"motivo": razao}
    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?)""",
        (titulo_id, "DESISTENCIA", agora, json.dumps(detalhe, ensure_ascii=False),
         origem, agora, usuario))
    con.execute("UPDATE pt_titulos SET situacao='DESISTIDO' WHERE id=?",
               (titulo_id,))
    return {"ato_id": int(cur.lastrowid), "titulo_id": titulo_id, "motivo": razao}


# ------------------------------------------------------------- o pagamento


def lancar_pagamento(con: sqlite3.Connection, titulo_id: int, *, sv: dict,
                     agora: str, data_extenso: str,
                     valor_pago: Any = None, usuario: str | None = None,
                     origem: str = "MANUAL") -> dict:
    """Registra o pagamento do título, com baixa. ESCREVE.

    Cabe em QUALQUER ponto do ciclo — apontado, intimado ou já protestado —,
    decisão do oficial em 24/08/2026: o devedor nem sempre espera o
    protesto ser lavrado para pagar. Só recusa título que já chegou a uma
    situação final (`SITUACOES_FINAIS`): pago de novo, ou pago depois de
    desistido, não fazem sentido.

    Ocupa lugar no Livro de Registro de Pagamentos (PT_PAGAMENTO) — 120 por
    folha, sem verso, medido no acervo — de todo jeito: a série exige
    registrar o pagamento, tenha ou não havido protesto antes.

    `valor_pago`, quando informado, fica no detalhe do ato. Não confere
    contra o saldo do título — decidir o que fazer com pagamento parcial é
    do oficial, não deste módulo.
    """
    tit = titulo(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    # Art. 17, § 1o: sustado so se PAGA com autorizacao judicial.
    # Receber o dinheiro de um titulo que o juiz mandou parar e tao
    # grave quanto lavrar o ato.
    _recusar_se_sustado(con, titulo_id, "o pagamento")
    if tit["situacao"] in SITUACOES_FINAIS:
        raise ProtestoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — não há como registrar pagamento.")

    detalhe: dict[str, Any] = {}
    if valor_pago is not None:
        detalhe["valor_pago_centavos"] = centavos(valor_pago)

    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?)""",
        (titulo_id, "PAGAMENTO", agora, json.dumps(detalhe, ensure_ascii=False),
         origem, agora, usuario))
    ato_id = int(cur.lastrowid)

    lugar = ESC.reservar(con, SERIE_PAGAMENTO, "pt_atos", ato_id, sv=sv,
                         agora=agora, data_extenso=data_extenso, paginas=1,
                         usuario=usuario)
    con.execute(
        """UPDATE pt_atos SET livro_id=?, folha=?, verso=?, numero_ordem=?,
                              rotulo=? WHERE id=?""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    con.execute("UPDATE pt_titulos SET situacao='PAGO' WHERE id=?",
               (titulo_id,))
    return {"ato_id": ato_id, "titulo_id": titulo_id, **lugar}


# ---------------------------------------------------------- o cancelamento


def lancar_cancelamento(con: sqlite3.Connection, titulo_id: int, *,
                        hipotese: str, fundamento: str, agora: str,
                        usuario: str | None = None,
                        origem: str = "MANUAL") -> dict:
    """Cancela o registro do protesto, com hipótese do catálogo. ESCREVE.

    Só cabe título PROTESTADO — cancelar o que nunca foi protestado não faz
    sentido; para isso há a desistência (antes do protesto) ou não há nada
    a fazer (título pago sem protesto). Recusa hipótese fora do catálogo, e
    recusa fundamento vazio: o defeito medido no acervo foi exatamente 56
    cancelamentos com o mesmo motivo genérico, "Erro Material", metade sem
    dizer por quê.

    Não ocupa lugar em livro próprio — o cancelamento é anotação no próprio
    registro do protesto, e o acervo não tem Livro de Cancelamento.
    """
    if hipotese not in CATALOGO_CANCELAMENTO:
        raise ProtestoError(
            f"Hipótese de cancelamento desconhecida: {hipotese!r}. As que "
            f"existem são: {', '.join(CATALOGO_CANCELAMENTO)}.")
    razao = (fundamento or "").strip()
    if len(razao) < 10:
        raise ProtestoError(
            "Escreva o fundamento do cancelamento com pelo menos dez "
            "letras — ele sai impresso na certidão e é o que a inspeção lê.")
    tit = titulo(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    if tit["situacao"] != "PROTESTADO":
        raise ProtestoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — só se cancela protesto já lavrado.")

    catalogo = CATALOGO_CANCELAMENTO[hipotese]
    detalhe = {"hipotese": hipotese, "rotulo": catalogo["rotulo"],
              "fundamento_legal": catalogo["fundamento_legal"]}
    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, observacao,
               detalhe_json, origem, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?,?)""",
        (titulo_id, "CANCELAMENTO", agora, razao,
         json.dumps(detalhe, ensure_ascii=False), origem, agora, usuario))
    con.execute("UPDATE pt_titulos SET situacao='CANCELADO' WHERE id=?",
               (titulo_id,))
    return {"ato_id": int(cur.lastrowid), "titulo_id": titulo_id,
           "fundamento": razao, **detalhe}
