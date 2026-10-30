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

    PIX SO E PAGAMENTO COM O CREDITO CONFERIDO (29/10/2026, ordem do
    oficial). Pagamento por PIX nao se lavra direto: o PIX se registra em
    `protesto_pix` (com o comprovante, AGUARDANDO_CREDITO), e
    `lancar_pagamento` so o aceita com `pix_id` de um PIX de credito
    conferido — pelo extrato do banco, ou a mao pelo oficial ou pelo gerente
    com afirmacao expressa. Enquanto o PIX espera, o titulo nao se protesta,
    nao se desiste e nao recebe outro pagamento.

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
from datetime import date
from typing import Any

import escrituracao as ESC
import protesto_cra as CRA
import protesto_termo as TERMO
from bd_nativo import banco
from caixa_schema import centavos
from cpf_cnpj import documento_valido, mensagem_documento_invalido, so_digitos
from pt_schema import normalizar_nome


class ProtestoError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


# O titulo anda RECEBIDO -> APONTADO -> INTIMADO -> PROTESTADO -> CANCELADO,
# e pode receber PAGAMENTO em qualquer ponto ANTES do protesto; ou para em
# DESISTIDO antes do protesto. RETIRADO continua documentado em
# LEVANTAMENTO_PROTESTO.md e por construir.
#
# DEVOLVIDO (decisao do oficial, 30/10/2026): o titulo devolvido por
# irregularidade (codigo 5 da CRA), ou a segunda entrada do mesmo titulo. Nao
# vai a protesto, intimacao, repasse nem XML. Quem o marca e a fila de correcoes
# de oficio (`correcoes_de_oficio.TituloDevolvido`), com o ato DEVOLUCAO: sem
# selo, sem livro e sem folha, so para a situacao ter o ato que a sustente.
SITUACOES_TITULO = ("RECEBIDO", "APONTADO", "INTIMADO", "PROTESTADO",
                    "DESISTIDO", "PAGO", "CANCELADO", "DEVOLVIDO")

# Situacoes finais: nao ha mais o que fazer com o titulo por este modulo.
SITUACOES_FINAIS = ("DESISTIDO", "PAGO", "CANCELADO", "DEVOLVIDO")

# O PROTESTO LAVRADO NÃO SE PAGA MAIS NA SERVENTIA — o oficial, 21/10/2026
# (LH13, pergunta 17, letra c): «protesto nao pode ser pago na serventia
# depois de lavrar». Ele voltou atrás na decisão de 24/08/2026, que admitia o
# pagamento em qualquer ponto do ciclo: o título pago depois do protesto ficava
# PAGO, e o cancelamento — que só cabia no PROTESTADO — não o alcançava mais;
# o protesto continuava para sempre na certidão positiva. Depois do protesto,
# o devedor paga ao CREDOR e pede o cancelamento com a carta de anuência (Lei
# 9.492/1997, art. 26, § 1º; CN-MA art. 942, § 2º).
SITUACOES_SEM_PAGAMENTO = SITUACOES_FINAIS + ("PROTESTADO",)

# O LEGADO DA REGRA ANTIGA: o título PAGO na serventia depois de protestado,
# entre 24/08 e 21/10/2026, tem o protesto em pé e nenhum caminho de baixa.
# Para ele o cancelamento cabe pelo caminho que a decisão de 21/10 manda — a
# anuência do credor — e pela ordem judicial, que vale sempre. A hipótese
# PAGAMENTO, não: usar o pagamento lançado aqui como prova da quitação era a
# letra (a) da pergunta 17, que o oficial não escolheu.
HIPOTESES_DO_PAGO_DEPOIS_DO_PROTESTO = ("ANUENCIA_CREDOR", "ORDEM_JUDICIAL")

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
        "rotulo": "Anuência do credor ou do apresentante",
        "fundamento_legal": (
            "Lei 9.492/1997, art. 26, § 1º; Código de Normas do TJMA, art. "
            "942, § 2º — declaração de anuência, com identificação completa e "
            "firma reconhecida, de quem figurou como credor (ou endossatário, "
            "no endosso translativo), na impossibilidade de apresentar o "
            "título original. O pedido de cancelamento do APRESENTANTE entra "
            "por aqui (decisão do oficial em 14/10/2026)."),
    },
    "ORDEM_JUDICIAL": {
        "rotulo": "Ordem judicial",
        "fundamento_legal": (
            "Decisão judicial determinando o cancelamento do registro do "
            "protesto."),
    },
}
# «ERRO DO APRESENTANTE» SAIU DO CATÁLOGO EM 14/10/2026 — decisão do oficial:
# «pedido do apresentante entra como anuência». O Código de Normas do TJMA,
# art. 943: «o cancelamento do protesto fundado em motivo diverso do pagamento
# somente será realizado mediante ordem judicial»; a hipótese cancelava sem
# anuência e sem ordem. O apresentante pede pela ANUENCIA_CREDOR (art. 942,
# § 2º); o erro material da própria serventia se corrige de ofício (art. 940).
# Nenhum cancelamento gravado a usava (medido na produção em 14/10/2026: zero).

# Como o titulo foi intimado. Diligencia (pessoal, por preposto ou correio
# com AR) primeiro; edital so quando a diligencia nao teve exito — mas este
# modulo nao impõe a ordem, so registra o que o balcao diz que aconteceu.
MODOS_INTIMACAO = ("PESSOAL", "EDITAL")

# As formas de pagamento do Livro de Pagamentos (CN-MA art. 930, III, e os
# meios do art. 925, §§ 1º e 2º). Espécie e cheque são as que o artigo nomeia.
FORMAS_DE_PAGAMENTO = {
    "ESPECIE": "em espécie",
    "CHEQUE": "por cheque",
    "PIX": "por PIX",
    "TRANSFERENCIA": "por transferência bancária",
    "BOLETO": "por boleto",
    "CARTAO": "por cartão",
}

# O vocabulario inteiro dos atos da vida de um titulo — de tbAvisoProtesto e
# de atribuicoes.ATOS (atribuicao 2). So APONTAMENTO tem funcao nesta versao.
TIPOS_ATO = ("APONTAMENTO", "INTIMACAO", "PROTESTO", "PAGAMENTO",
             "CANCELAMENTO", "ARQUIVAMENTO", "CERTIDAO", "DESISTENCIA",
             "RETIRADA", "SUSTACAO", "REVOGACAO_SUSTACAO",
             "EFEITO_SUSPENSIVO", "REVOGACAO_EFEITO_SUSPENSIVO",
             # 29/10/2026: a averbação de retificação de erro material, de
             # ofício (Lei 9.492/1997, art. 25) — `protesto_averbacao`.
             "AVERBACAO_RETIFICACAO",
             # 30/10/2026: a devolução (código 5 da CRA, ou a entrada em
             # duplicidade). Não vai a retorno nem a XML: não é ato lavrado.
             "DEVOLUCAO")

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

# O CARÁTER DA DECISÃO QUE SUSPENDE OS EFEITOS DO PROTESTO — CNN art. 263-K
# (Prov. CN 253, de 18/08/2026), seguido por decisão do oficial em 21/10/2026
# (LH13, pergunta 18, letra a), no lugar da sua decisão de 14/10/2026 pelo
# CN-MA arts. 944 e 948. É o que decide a certidão a terceiro:
#   PROVISORIA — «CONSTA COM SUSTAÇÃO JUDICIAL PRECÁRIA», com os dados do
#                registro, o número da ação e o caráter provisório (III);
#   DEFINITIVA — «NADA CONSTA»: o protesto fica fora da certidão (I).
# A decisão que manda EXPRESSAMENTE emitir negativa cumpre-se nos exatos
# limites, e no segredo de justiça a certidão diz só a sustação e o número do
# processo (§ 1º) — as duas outras marcas da ordem.
#
# SÓ O EFEITO SUSPENSIVO TEM A MARCA, e não a sustação: a sustação chega antes
# do protesto, e título sem protesto lavrado não entra em certidão nenhuma.
CARATER_DA_ORDEM = {
    "PROVISORIA": "provisória (liminar, tutela de urgência)",
    "DEFINITIVA": "definitiva (sentença ou decisão final)",
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


def titulo(con, titulo_id: int) -> dict | None:
    """O titulo, com tudo que foi cadastrado. So LE."""
    return banco(con).um(
        "SELECT * FROM pt_titulos WHERE id=%s", (int(titulo_id),))


def titulo_para_gravar(con, titulo_id: int) -> dict | None:
    """O titulo, com a linha PRESA ate o fim da transacao (FOR UPDATE).

    Para quem confere a situacao do titulo — ou a ordem judicial em vigor —
    e grava em cima dela. Sem a linha presa, a desistencia e a intimacao do
    mesmo titulo, ao mesmo tempo, passariam as duas na conferencia; com ela,
    a segunda espera a primeira e le a situacao ja gravada. Abre a escrita:
    nao e para tela que so mostra (essa usa `titulo`).
    """
    bd = banco(con)
    bd._escrita()
    return bd.um("SELECT * FROM pt_titulos WHERE id=%s FOR UPDATE",
                 (int(titulo_id),))


def devedores_do(con, titulo_id: int) -> list[dict]:
    """Os devedores do titulo, na ordem em que entraram. So LE."""
    return banco(con).ler(
        "SELECT * FROM pt_devedores WHERE titulo_id=%s ORDER BY id",
        (int(titulo_id),))


def atos_do(con, titulo_id: int) -> list[dict]:
    """Os atos ja lancados para o titulo, na ordem em que aconteceram. So LE."""
    return banco(con).ler(
        "SELECT * FROM pt_atos WHERE titulo_id=%s ORDER BY id",
        (int(titulo_id),))


def titulo_por_origem(con, origem: str,
                      origem_chave: str) -> dict | None:
    """O titulo de uma chave de origem, ou None. So LE."""
    return banco(con).um(
        "SELECT * FROM pt_titulos WHERE origem=%s AND origem_chave=%s "
        "ORDER BY id LIMIT 1",
        (origem, origem_chave))


def apresentante_do_titulo(con, titulo: Any) -> dict:
    """Quem apresentou o titulo: nome, CPF/CNPJ e endereco. So LE.

    A NORMA PEDE OS TRES, E O ARQUIVO DA CRA TRAZ UM (LD08, 21/10/2026). O
    aviso leva o apresentante «com respectivos CPF e/ou CNPJ» (CN-MA art.
    923; CNN art. 356, § 4o); o registro e o instrumento, o nome «e
    endereco» (Lei 9.492/1997, art. 22, II; CN-MA art. 914, III). O
    cabecalho da remessa da CRA tem so o codigo (3) e o nome (40) — medido em
    01/09/2026 (`protesto_instrumento.ITENS_DO_ART_22`).

    DE ONDE VEM CADA UM, nesta ordem:
      - do proprio titulo: o balcao os pede a quem traz o titulo (CN-MA art.
        884, I), e eles ficam em `pt_titulos`;
      - do cadastro dos apresentantes (`pt_apresentantes`), pelo codigo da
        CRA — o mesmo que o XML da CENPROT ja le para o CNPJ. O banco
        apresentante e um so para milhares de titulos: o endereco dele se
        escreve uma vez, na tela do XML, e nao titulo a titulo;
      - sem nenhum dos dois, o nome cai para o codigo, e o documento e o
        endereco vem vazios: o papel os omite, e a conferencia do
        instrumento diz o que falta. Nao se inventa.
    """
    t = dict(titulo or {})
    codigo = str(t.get("apresentante_codigo") or "").strip()
    # O «TAB» NÃO TEM CADASTRO QUE SIRVA (28/10/2026): é um apresentante por
    # título — quem pediu na Gestão de Pedidos da CENPROT —, e a linha TAB de
    # `pt_apresentantes` é de UMA pessoa. Cair nela poria no aviso e no
    # instrumento o CPF/CNPJ e o endereço de outro ao lado do nome deste.
    # Medido nos XML reais do E-Ofício: 18 títulos TAB, 8 apresentantes.
    from protesto_cenprot_xml import APRESENTANTES_DO_TITULO
    cadastro = (banco(con).um(
        "SELECT nome, documento, endereco FROM pt_apresentantes WHERE codigo = %s",
        (codigo,)) if codigo and codigo not in APRESENTANTES_DO_TITULO
        else None) or {}

    def _primeiro(*valores: Any) -> str:
        return next((str(v).strip() for v in valores
                     if v is not None and str(v).strip()), "")

    # O NÚMERO GRAVADO NO LUGAR DO NOME (30/10/2026) não é nome: vale o cadastro.
    from protesto_arquivo import nome_de_apresentante
    return {"codigo": codigo,
            "nome": _primeiro(nome_de_apresentante(t.get("apresentante_nome")),
                              cadastro.get("nome"), codigo),
            "documento": _primeiro(so_digitos(t.get("apresentante_documento")),
                                   so_digitos(cadastro.get("documento"))),
            "endereco": _primeiro(t.get("apresentante_endereco"),
                                  cadastro.get("endereco"))}


# ------------------------------------------------------------- o cadastro


def cadastrar_titulo(con, dados: dict, *, origem: str,
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
    # O CPF/CNPJ DO APRESENTANTE VAI AO AVISO (CN-MA art. 923), e número que
    # não fecha o dígito é documento de ninguém num papel que a casa assina.
    # Vazio não é erro: quem exige ou não é o oficial (LD08.perguntas, 1).
    doc_apresentante = so_digitos(dados.get("apresentante_documento"))
    if documento_valido(doc_apresentante) is False:
        raise ProtestoError("CPF/CNPJ do apresentante: "
                            + mensagem_documento_invalido(doc_apresentante))
    bd = banco(con)
    if chave:
        existente = titulo_por_origem(bd, origem, chave)
        if existente:
            return int(existente["id"])

    cedente = dados.get("cedente") or {}
    # O `ON CONFLICT` e a mesma regra de cima para quem chega AO MESMO TEMPO:
    # a conferencia nao ve o cadastro que outro atendimento ainda nao
    # confirmou, e o INSERT puro estouraria o UNIQUE(origem, origem_chave).
    # Com ele, o segundo espera o primeiro e devolve o id que ficou.
    novo = bd.escrever(
        """INSERT INTO pt_titulos(
               especie, numero_titulo, nosso_numero, chave_cenprot,
               data_emissao, data_vencimento, tipo_moeda, valor_centavos,
               saldo_centavos, praca_protesto, tipo_protesto, tipo_endosso,
               aceite, motivo_protesto, irregularidades_json,
               apresentante_codigo, apresentante_nome,
               apresentante_documento, apresentante_endereco,
               cra_identificacao,
               cedente_nome, cedente_documento, cedente_endereco,
               cedente_cep, cedente_cidade, cedente_uf,
               situacao, origem, origem_chave, importacao_id,
               criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (origem, origem_chave) DO NOTHING
           RETURNING id""",
        (dados.get("especie"), dados.get("numero_titulo"), dados.get("nosso_numero"),
         dados.get("chave_cenprot"), dados.get("data_emissao"),
         dados.get("data_vencimento"), dados.get("tipo_moeda") or "1",
         centavos(dados.get("valor")), centavos(dados.get("saldo")),
         dados.get("praca_protesto"), dados.get("tipo_protesto"),
         dados.get("tipo_endosso"), dados.get("aceite"), dados.get("motivo_protesto"),
         json.dumps(dados.get("irregularidades") or [], ensure_ascii=False),
         (dados.get("apresentante_codigo") or None),
         (dados.get("apresentante_nome") or None),
         doc_apresentante or None,
         (str(dados.get("apresentante_endereco") or "").strip() or None),
         (str(dados.get("cra_identificacao") or "").strip() or None),
         cedente.get("nome"), cedente.get("documento"), cedente.get("endereco"),
         cedente.get("cep"), cedente.get("cidade"), cedente.get("uf"),
         "RECEBIDO", origem, chave, importacao_id, agora, usuario))
    if not novo:
        return int(titulo_por_origem(bd, origem, chave)["id"])
    titulo_id = int(novo[0]["id"])

    for devedor in dados.get("devedores") or []:
        documento_tipo = ("CNPJ" if devedor.get("CNPJ")
                          else "CPF" if devedor.get("CPF") else None)
        documento_numero = devedor.get("CNPJ") or devedor.get("CPF")
        endereco = (devedor.get("enderecos") or [{}])[0]
        bd.escrever(
            """INSERT INTO pt_devedores(titulo_id, nome, nome_norm,
                   documento_tipo, documento_numero, endereco, bairro, cep,
                   cidade, uf)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (titulo_id, devedor.get("nome"),
             normalizar_nome(devedor.get("nome")),
             documento_tipo, documento_numero,
             endereco.get("endereco"), endereco.get("bairro"),
             endereco.get("cep"), endereco.get("cidade"), endereco.get("uf")))
    return titulo_id


# ----------------------------------------------------------- o protocolo


def numero_do_protocolo(con, dia: str) -> str:
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
    n = banco(con).valor(
        """SELECT COUNT(*) AS n FROM pt_titulos
            WHERE protocolo IS NOT NULL AND protocolo ILIKE %s""",
        (f"{prefixo}%",))
    return f"{prefixo}{int(n) + 1:04d}"


# ----------------------------------------------------------- o apontamento


def lancar_apontamento(con, titulo_id: int, *, sv: dict,
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
    bd = banco(con)
    tit = titulo_para_gravar(bd, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    if tit["situacao"] != "RECEBIDO":
        raise ProtestoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — não se aponta de novo.")

    ato_id = int(bd.escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem, criado_em,
               criado_por)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (titulo_id, "APONTAMENTO", agora, origem, agora, usuario))[0]["id"])

    # O PROTOCOLO NASCE AQUI, com o apontamento — e o numero que volta para a
    # CRA na posicao 448 do retorno. Titulo que ja tem protocolo (veio do
    # acervo com ele) fica com o que tinha: renumerar apagaria o que a Central
    # ja conhece.
    if not (tit["protocolo"] or "").strip():
        bd.travar("pt_titulos.protocolo")
        bd.escrever("UPDATE pt_titulos SET protocolo=%s WHERE id=%s",
                    (numero_do_protocolo(bd, agora), titulo_id))

    lugar = ESC.reservar(con, SERIE_APONTAMENTO, "pt_atos", ato_id, sv=sv,
                         agora=agora, data_extenso=data_extenso, paginas=1,
                         usuario=usuario)
    bd.escrever(
        """UPDATE pt_atos SET livro_id=%s, folha=%s, verso=%s, numero_ordem=%s,
                              rotulo=%s WHERE id=%s""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    bd.escrever("UPDATE pt_titulos SET situacao='APONTADO' WHERE id=%s",
               (titulo_id,))
    return {"ato_id": ato_id, "titulo_id": titulo_id, **lugar}


# ------------------------------------------------------------ a intimacao


def lancar_intimacao(con, titulo_id: int, *, modo: str,
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
    bd = banco(con)
    tit = titulo_para_gravar(bd, titulo_id)
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

    ato_id = int(bd.escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (titulo_id, "INTIMACAO", agora, json.dumps(detalhe, ensure_ascii=False),
         origem, agora, usuario))[0]["id"])
    bd.escrever("UPDATE pt_titulos SET situacao='INTIMADO' WHERE id=%s",
               (titulo_id,))
    return {"ato_id": ato_id, "titulo_id": titulo_id, **detalhe}


# --------------------------------------------------- o protesto e a desistencia


def esperando_protesto(con, *, hoje: str,
                       limite: int = 300) -> list[dict]:
    """Os títulos intimados e SEM MOVIMENTAÇÃO desde a intimação. Só LÊ.

    É o passo da tarde do roteiro do oficial: «gerar protesto, sem
    movimentação, calcular, listar, gerar». Até 31/08/2026 ele não tinha tela
    nenhuma, e o título intimado ficava esperando alguém lembrar dele.

    O PRAZO NÃO SE CALCULA AQUI: a lista devolve `dias_desde_a_intimacao`, que
    é contagem. O tríduo — termo inicial e final — é de `protesto_triduo`
    desde a tarefa 56 (23/10/2026), e a tela o acrescenta a cada linha.

    SEM MOVIMENTAÇÃO QUER DIZER SEM ATO POSTERIOR. Não basta a situação estar
    `INTIMADO`: um pagamento lançado hoje muda a situação, mas o que importa é
    que **nenhum ato entrou depois da intimação** — e é assim que a consulta
    pergunta, olhando o `id` do ato, que é a ordem em que eles foram lavrados.
    """
    bd = banco(con)
    linhas = bd.ler(
        """SELECT t.id, t.numero_titulo, t.nosso_numero, t.protocolo,
                  t.especie, t.valor_centavos, t.saldo_centavos, t.situacao,
                  i.data_ato AS data_da_intimacao, i.detalhe_json,
                  i.numero_ordem AS numero_da_intimacao
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
            LIMIT %s""", (int(limite),))

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
        d["devedores"] = [dict(r) for r in bd.ler(
            "SELECT nome, documento_numero FROM pt_devedores WHERE titulo_id=%s "
            "ORDER BY id",
            (d["id"],))]
        saida.append(d)
    return saida


def sustacao_revogada(con, *, hoje: str,
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
    bd = banco(con)
    linhas = bd.ler(
        """SELECT t.id, t.numero_titulo, t.nosso_numero, t.protocolo,
                  t.especie, t.valor_centavos, t.saldo_centavos, t.situacao,
                  r.data_ato AS data_da_revogacao, r.detalhe_json
             FROM pt_titulos t
             JOIN pt_atos r ON r.id = (
                    SELECT MAX(a.id) FROM pt_atos a
                     WHERE a.titulo_id = t.id AND a.cancelado = 0
                       AND a.tipo IN ('SUSTACAO','REVOGACAO_SUSTACAO'))
            WHERE r.tipo = 'REVOGACAO_SUSTACAO'
              AND t.situacao NOT IN ('PROTESTADO','PAGO','CANCELADO',
                                     'DESISTIDO','RETIRADO','DEVOLVIDO')
            ORDER BY r.data_ato, t.id
            LIMIT %s""", (int(limite),))

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
        d["devedores"] = [dict(x) for x in bd.ler(
            "SELECT nome, documento_numero FROM pt_devedores WHERE titulo_id=%s "
            "ORDER BY id",
            (d["id"],))]
        saida.append(d)
    return saida


def sustados(con, limite: int = 300) -> list[dict]:
    """Os títulos com o protesto sustado por ordem judicial. Só LÊ.

    Eles ficam **à disposição do Juízo** (art. 17, caput), e não se pagam, não
    se protestam e não se retiram sem autorização judicial (§ 1º). Uma lista
    própria existe porque eles não aparecem em nenhuma outra: saíram da fila
    do «A protestar» de propósito, e sem esta tela ninguém sabe que existem.
    """
    bd = banco(con)
    linhas = bd.ler(
        """SELECT t.id, t.numero_titulo, t.nosso_numero, t.protocolo,
                  t.especie, t.saldo_centavos, t.situacao,
                  s.data_ato AS data_da_sustacao, s.detalhe_json
             FROM pt_titulos t
             JOIN pt_atos s ON s.id = (
                    SELECT MAX(a.id) FROM pt_atos a
                     WHERE a.titulo_id = t.id AND a.cancelado = 0
                       AND a.tipo IN ('SUSTACAO','REVOGACAO_SUSTACAO'))
            WHERE s.tipo = 'SUSTACAO'
            ORDER BY s.data_ato, t.id
            LIMIT %s""", (int(limite),))
    saida = []
    for linha in linhas:
        d = dict(linha)
        try:
            ordem = json.loads(d.get("detalhe_json") or "{}")
        except (TypeError, ValueError):
            ordem = {}
        d["juizo"] = ordem.get("juizo") or ""
        d["processo"] = ordem.get("processo") or ""
        d["devedores"] = [dict(x) for x in bd.ler(
            "SELECT nome, documento_numero FROM pt_devedores WHERE titulo_id=%s "
            "ORDER BY id",
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


def _ordem_em_vigor(con, titulo_id: int,
                    ordem: str) -> dict | None:
    """A ordem judicial daquele tipo que está valendo, ou None. Só LÊ.

    VALE A ÚLTIMA PALAVRA DO JUÍZO, e é por isso que se olha o ato mais
    recente entre os dois — a ordem e a revogação dela — e não se conta
    quantos há de cada. A mesma ordem pode ser dada, revogada e dada de novo;
    somar daria a resposta errada na segunda vez.
    """
    revogacao = ORDEM_JUDICIAL_E_A_REVOGACAO[ordem]
    linha = banco(con).um(
        """SELECT id, tipo, data_ato, detalhe_json, ordem_carater,
                  ordem_manda_negativa, ordem_segredo_de_justica,
                  ordem_marcada_em, ordem_marcada_por
             FROM pt_atos
            WHERE titulo_id = %s AND tipo IN (%s, %s) AND cancelado = 0
            ORDER BY id DESC LIMIT 1""",
        (int(titulo_id), ordem, revogacao))
    if linha is None or linha["tipo"] != ordem:
        return None
    d = dict(linha)
    try:
        d.update(json.loads(d.get("detalhe_json") or "{}"))
    except (TypeError, ValueError):
        pass
    # A MARCA DO CNN art. 263-K vem das colunas (LH13), e o detalhe não a
    # sobrepõe: o que se marcou depois é o que vale.
    for coluna in ("ordem_carater", "ordem_manda_negativa",
                   "ordem_segredo_de_justica", "ordem_marcada_em",
                   "ordem_marcada_por"):
        d[coluna] = linha[coluna]
    return d


def sustacao_em_vigor(con, titulo_id: int) -> dict | None:
    """A ordem que IMPEDE o protesto — art. 17. Só LÊ."""
    return _ordem_em_vigor(con, titulo_id, "SUSTACAO")


def efeito_suspensivo_em_vigor(con,
                               titulo_id: int) -> dict | None:
    """A ordem que SUSPENDE OS EFEITOS de um protesto já lavrado. Só LÊ.

    É o outro instituto, e **esta casa nunca o usou**: o único caso do acervo,
    de 18/08/2025, é uma SUSTAÇÃO — o título nunca chegou a ser protestado.

    Ele existe assim mesmo, e por razão que não depende de frequência: o
    registro fica no livro, e o que para é a **publicidade** dele — quem lê
    isto é a certidão, o papel que faz o banco negar crédito.
    """
    return _ordem_em_vigor(con, titulo_id, "EFEITO_SUSPENSIVO")


def _recusar_se_sustado(con, titulo_id: int,
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


def lancar_sustacao(con, titulo_id: int, *,
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
    tit = titulo_para_gravar(con, titulo_id)
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
    ato_id = int(banco(con).escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (%s,'SUSTACAO',%s,%s,%s,%s,%s) RETURNING id""",
        (titulo_id, recebido_em or agora, detalhe, origem, agora, usuario))[0]["id"])
    return {"ato_id": ato_id, "titulo_id": titulo_id,
            "juizo": quem, "processo": autos}


def lancar_revogacao_sustacao(con, titulo_id: int, *,
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
    tit = titulo_para_gravar(con, titulo_id)
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
    ato_id = int(banco(con).escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (%s,'REVOGACAO_SUSTACAO',%s,%s,%s,%s,%s) RETURNING id""",
        (titulo_id, recebido_em or agora, detalhe, origem, agora, usuario))[0]["id"])
    return {"ato_id": ato_id, "titulo_id": titulo_id,
            "recebido_em": recebido_em or agora}


def _marca_da_ordem(carater: Any) -> str:
    """O caráter da decisão, validado (CNN art. 263-K). Só calcula.

    OBRIGATÓRIO NA ORDEM NOVA (LH13, 21/10/2026): é ele que decide se o
    protesto sai na certidão a terceiro como sustação precária ou se fica
    fora, e o escrevente que lança a ordem é quem tem o mandado na mão. Sem a
    marca, a certidão faria a escolha por ele.
    """
    c = str(carater or "").strip().upper()
    if c not in CARATER_DA_ORDEM:
        raise ProtestoError(
            "Informe o caráter da decisão judicial: provisória (liminar, tutela "
            "de urgência) ou definitiva. Pelo Código Nacional de Normas, art. "
            "263-K, é ele que decide a certidão: a provisória sai como «CONSTA "
            "COM SUSTAÇÃO JUDICIAL PRECÁRIA», e a definitiva fica fora dela.")
    return c


def lancar_efeito_suspensivo(con, titulo_id: int, *,
                            juizo: str, processo: str, agora: str,
                            carater: str | None = None,
                            manda_negativa: Any = False,
                            segredo_de_justica: Any = False,
                            recebido_em: str | None = None,
                            observacao: str | None = None,
                            usuario: str | None = None,
                            origem: str = "MANUAL") -> dict:
    """Suspende os EFEITOS de um protesto já lavrado, por ordem judicial.

    **E A ORDEM VEM MARCADA** (LH13, 21/10/2026 — CNN art. 263-K): o
    `carater` (PROVISORIA × DEFINITIVA, obrigatório), se ela manda
    expressamente emitir certidão negativa e se o processo corre em segredo
    de justiça. A marca mora nas colunas `ordem_*` do ato, e é a certidão que
    a lê (`protesto_certidao.buscar`).

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
    tit = titulo_para_gravar(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    protestado = banco(con).um(
        """SELECT 1 AS um FROM pt_atos WHERE titulo_id=%s AND tipo='PROTESTO'
            AND cancelado = 0 ORDER BY id LIMIT 1""", (int(titulo_id),))
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
    marca = _marca_da_ordem(carater)

    detalhe = json.dumps({"juizo": quem, "processo": autos,
                          "observacao": str(observacao or "").strip()},
                         ensure_ascii=False)
    ato_id = int(banco(con).escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por, ordem_carater,
               ordem_manda_negativa, ordem_segredo_de_justica,
               ordem_marcada_em, ordem_marcada_por)
           VALUES (%s,'EFEITO_SUSPENSIVO',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (titulo_id, recebido_em or agora, detalhe, origem, agora, usuario,
         marca, int(bool(manda_negativa)), int(bool(segredo_de_justica)),
         agora, usuario))[0]["id"])
    return {"ato_id": ato_id, "titulo_id": titulo_id,
            "juizo": quem, "processo": autos, "carater": marca}


def marcar_ordem_judicial(con, ato_id: int, *, carater: str,
                          manda_negativa: Any = False,
                          segredo_de_justica: Any = False, agora: str,
                          usuario: str | None = None) -> dict:
    """Marca (ou corrige a marca de) uma ordem de efeito suspensivo. ESCREVE.

    É A PORTA DAS ORDENS LANÇADAS ANTES DE 21/10/2026 (LH13): elas não têm a
    marca do CNN art. 263-K, e por isso continuam como sempre — o protesto
    fora da certidão — até alguém ler o mandado e dizer se a decisão é
    provisória ou definitiva. A mesma porta corrige a marca posta errada.

    O ATO NÃO SE REESCREVE: o juízo, o processo e a data de recebimento
    ficam como foram lançados; muda só a marca, com quem a pôs e quando. A
    certidão já emitida também não muda — o teor dela congelou na emissão.

    AS TRAVAS NA ORDEM DA CASA: o título primeiro (`titulo_para_gravar`), o
    ato depois — a mesma ordem de todo `lancar_*`.
    """
    bd = banco(con)
    ato = bd.um("SELECT id, titulo_id FROM pt_atos WHERE id = %s",
                (int(ato_id),))
    if not ato:
        raise ProtestoError(f"Ordem judicial {ato_id} não encontrada.")
    tit = titulo_para_gravar(con, int(ato["titulo_id"]))
    bd._escrita()
    ordem = bd.um(
        """SELECT id, tipo, cancelado FROM pt_atos WHERE id = %s FOR UPDATE""",
        (int(ato_id),))
    if ordem["tipo"] != "EFEITO_SUSPENSIVO" or int(ordem["cancelado"] or 0):
        raise ProtestoError(
            "Só a ordem judicial que suspendeu os efeitos de um protesto "
            "lavrado leva a marca do art. 263-K do Código Nacional de Normas "
            "— e esta não é uma, ou foi anulada.")
    marca = _marca_da_ordem(carater)
    bd.escrever(
        """UPDATE pt_atos SET ordem_carater = %s, ordem_manda_negativa = %s,
                  ordem_segredo_de_justica = %s, ordem_marcada_em = %s,
                  ordem_marcada_por = %s
            WHERE id = %s""",
        (marca, int(bool(manda_negativa)), int(bool(segredo_de_justica)),
         agora, usuario, int(ato_id)))
    return {"ato_id": int(ato_id), "titulo_id": int(ato["titulo_id"]),
            "numero_titulo": (tit or {}).get("numero_titulo"),
            "carater": marca, "manda_negativa": bool(manda_negativa),
            "segredo_de_justica": bool(segredo_de_justica)}


def ordens_sem_marca(con, limite: int = 300) -> list[dict]:
    """As ordens de efeito suspensivo EM VIGOR que ainda não têm a marca do
    CNN art. 263-K. Só LÊ.

    Elas são as lançadas antes de 21/10/2026 (LH13), e o protesto delas fica
    FORA da certidão, como ficava — mas se a decisão for provisória, o certo
    hoje é a certidão dizer «CONSTA COM SUSTAÇÃO JUDICIAL PRECÁRIA». A lista
    existe para a tela avisar: sem ela, ninguém sabe que há ordem a marcar.

    EM VIGOR é a última palavra do juízo (a ordem, e não a revogação dela), e
    só sobre protesto em pé — o cancelado não sai em certidão nenhuma.
    """
    return banco(con).ler(
        """SELECT a.id AS ato_id, a.titulo_id, a.data_ato, a.detalhe_json,
                  t.numero_titulo, t.protocolo
             FROM pt_atos a
             JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.tipo = 'EFEITO_SUSPENSIVO' AND a.cancelado = 0
              AND a.ordem_carater IS NULL
              AND a.id = (SELECT max(b.id) FROM pt_atos b
                           WHERE b.titulo_id = a.titulo_id AND b.cancelado = 0
                             AND b.tipo IN ('EFEITO_SUSPENSIVO',
                                            'REVOGACAO_EFEITO_SUSPENSIVO'))
              AND NOT EXISTS (SELECT 1 FROM pt_atos c
                               WHERE c.titulo_id = a.titulo_id
                                 AND c.tipo = 'CANCELAMENTO' AND c.cancelado = 0)
            ORDER BY a.data_ato, a.id
            LIMIT %s""", (int(limite),))


def lancar_revogacao_efeito_suspensivo(
        con, titulo_id: int, *, agora: str,
        recebido_em: str | None = None, observacao: str | None = None,
        usuario: str | None = None, origem: str = "MANUAL") -> dict:
    """Revoga a suspensão dos efeitos: o protesto volta a publicar. ESCREVE.

    E é por isso que ela é ato próprio, e não um `UPDATE`: o dia em que o
    protesto voltou a valer é fato que a certidão de amanhã pode ter de
    explicar.
    """
    tit = titulo_para_gravar(con, titulo_id)
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
    ato_id = int(banco(con).escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (%s,'REVOGACAO_EFEITO_SUSPENSIVO',%s,%s,%s,%s,%s) RETURNING id""",
        (titulo_id, recebido_em or agora, detalhe, origem, agora, usuario))[0]["id"])
    return {"ato_id": ato_id, "titulo_id": titulo_id}


def lancar_protesto(con, titulo_id: int, *, sv: dict,
                    agora: str, data_extenso: str,
                    usuario: str | None = None,
                    origem: str = "MANUAL",
                    modelo_do_termo: str | None = None,
                    conferir_triduo: bool = False,
                    motivo_atraso: str | None = None,
                    afirmacao: str | None = None) -> dict:
    """Lavra o protesto no Livro de Registro de Protestos. ESCREVE.

    Exige que o título já tenha sido intimado (Lei 9.492/1997, art. 14).
    Recusa protestar de novo o que já foi protestado ou desistido.

    A PROVA DA INTIMAÇÃO É CONFERIDA SEMPRE (ordem do oficial, 29/10/2026:
    «nao deixar protestar sem aviso de que foi intimado (com comprovante
    juntado) ou comprovacao do envio do edital na cenprot»). Não há chave
    para desligar, ao contrário do tríduo: guarda que se pode esquecer de
    pedir é guarda que um dia não é pedido, e em outubro de 2026 os 21
    protestos que o sistema lavrou não a teriam passado. A régua é
    `protesto_prova.exigir`; sem a prova, só lavra com a `afirmacao`
    expressa de quem está no balcão, e ela fica no `detalhe_json` do ato
    (`afirmacao_expressa`) e volta no retorno, para a rota gravar a
    auditoria fora da transação.

    O TRÍDUO (tarefa 56, 23/10/2026): com `conferir_triduo`, recusa antes do
    termo inicial e, depois do termo final, exige `motivo_atraso` — a conta é
    `protesto_triduo`, e ela fica gravada no `detalhe_json` do ato, de onde o
    instrumento tira a menção do atraso (CN-MA art. 913, § 1º). As duas rotas
    que protestam passam `True`, e há teste que exige isso delas; o padrão
    `False` é o das montagens de cenário dos testes, que lavram tudo no mesmo
    instante. Desde 27/10/2026 (decisão do oficial, «no dia útil seguinte») o
    termo inicial é o dia útil SEGUINTE ao prazo-limite do devedor: no próprio
    prazo-limite a recusa diz até quando ele paga e a partir de quando se
    protesta, e o protesto do dia útil seguinte é no prazo, sem motivo.

    O lugar sai de `escrituracao.reservar()` na série PT_PROTESTO — um
    protesto por FACE, frente e verso (decisão do oficial em 14/10/2026; ver
    `livro_nucleo`).
    """
    tit = titulo_para_gravar(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    # Art. 17, § 1o: sustado so se protesta com autorizacao judicial.
    _recusar_se_sustado(con, titulo_id, "o protesto")
    if tit["situacao"] != "INTIMADO":
        raise ProtestoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — só se protesta título já intimado.")
    # O DEVEDOR DIZ QUE PAGOU POR PIX (29/10/2026): enquanto o crédito não for
    # conferido — ou dado por não confirmado —, o protesto não se lavra.
    import protesto_pix as PIX
    PIX.recusar_se_esperando(con, titulo_id, "o protesto")
    triduo = None
    if conferir_triduo:
        import protesto_triduo as TRIDUO
        triduo = TRIDUO.conferir_lavratura(con, titulo_id, hoje=str(agora)[:10],
                                           motivo_atraso=motivo_atraso)
    # A PROVA DEPOIS DO TRÍDUO: o «ainda não é dia» não se vence por
    # afirmação nenhuma, e a afirmação escrita para a prova não pode ser
    # pedida a quem nem poderia protestar hoje.
    import protesto_prova as PROVA
    prova = PROVA.exigir(con, titulo_id, hoje=str(agora)[:10],
                         afirmacao=afirmacao)
    detalhe: dict = {"prova": PROVA.resumo_para_o_ato(prova)}
    if triduo:
        detalhe["triduo"] = triduo
    if prova["afirmacao_expressa"]:
        detalhe["afirmacao_expressa"] = prova["afirmacao_expressa"]

    # O TEXTO QUE VAI NO LIVRO, montado dos fatos deste titulo — e ele
    # CONGELA aqui: e o que foi escrito naquele dia. Medido: o E-Oficio o
    # escreveu em 1.132 dos 1.164 protestos, e este sistema nao escrevia
    # nenhum. Ver `protesto_termo`.
    #
    # `modelo` e `base` vem do catalogo que o oficial edita quando a rota os
    # passa; sem eles vale o texto desta casa, copiado do E-Oficio.
    #
    # AS FRASES DA INTIMACAO E AS PALAVRAS DO MOTIVO E DO TIPO SAEM DO PADRAO,
    # e por isso nao se passa `con`. Ate o LF06E (19/10/2026) eram constantes
    # do codigo, e o ajuste da casa nao as alcancava; desde entao sao pecas
    # que a tela de Modelos edita (`PT_TERMO_INTIMACAO_*`, `PT_TERMO_MOTIVOS`,
    # `PT_TERMO_TIPOS`). Fazer o livro segui-las mudaria o que se lavra no
    # Livro de Registro de Protestos (Lei 9.492/1997, art. 22, IV) — regra de
    # negocio, que espera a decisao do oficial. Se ele confirmar, basta
    # passar `con=con` aqui.
    #
    # A QUALIFICAÇÃO DO REGISTRO (LD04, 21/10/2026) — Lei 9.492/1997, art. 22,
    # e CN-MA art. 914: o número de ordem e a data do registro, o protocolo, o
    # apresentante, o título e os devedores. O NÚMERO DE ORDEM SÓ EXISTE DEPOIS
    # DE `reservar`, e por isso o termo se monta duas vezes: a primeira, antes
    # de gravar qualquer coisa, para o modelo quebrado ou o título sem motivo
    # recusarem aqui (e não com o ato e o lugar já tomados); a segunda, com o
    # lugar, é a que se grava. Os fatos são os mesmos — `dados_do_titulo` os
    # relê do banco, e é com eles que o teor se confere depois.
    def _termo() -> str:
        fatos = TERMO.dados_do_titulo(con, titulo_id)
        return TERMO.montar(modelo=modelo_do_termo,
                            edital_data=fatos["edital_data"],
                            edital_motivo=fatos["edital_motivo"],
                            motivo_protesto=fatos["motivo_protesto"],
                            tipo_protesto=fatos["tipo_protesto"],
                            pessoal_data=fatos.get("pessoal_data"),
                            pessoal_digital=bool(fatos.get("pessoal_digital")),
                            qualificacao_do_registro=fatos.get(
                                "qualificacao_do_registro"))
    texto = _termo()
    bd = banco(con)
    ato_id = int(bd.escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, teor, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (titulo_id, "PROTESTO", agora, texto,
         json.dumps(detalhe, ensure_ascii=False),
         origem, agora, usuario))[0]["id"])

    lugar = ESC.reservar(con, SERIE_PROTESTO, "pt_atos", ato_id, sv=sv,
                         agora=agora, data_extenso=data_extenso, paginas=1,
                         usuario=usuario)
    bd.escrever(
        """UPDATE pt_atos SET livro_id=%s, folha=%s, verso=%s, numero_ordem=%s,
                              rotulo=%s WHERE id=%s""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    bd.escrever("UPDATE pt_atos SET teor=%s WHERE id=%s", (_termo(), ato_id))
    bd.escrever("UPDATE pt_titulos SET situacao='PROTESTADO' WHERE id=%s",
               (titulo_id,))
    return {"ato_id": ato_id, "titulo_id": titulo_id, **lugar,
            "afirmacao_expressa": prova["afirmacao_expressa"]}


def lancar_desistencia(con, titulo_id: int, *,
                       motivo: str, agora: str, usuario: str | None = None,
                       origem: str = "MANUAL") -> dict:
    """Registra a desistência do CREDOR, antes de o protesto ser lavrado. ESCREVE.

    Só cabe enquanto o título não foi protestado: tirar protesto já lavrado
    é cancelamento, com o catálogo de hipóteses da Lei 9.492/1997 — ainda
    por construir neste módulo, e não é a mesma coisa. Não ocupa lugar em
    livro: a desistência não tem série própria no acervo.
    """
    tit = titulo_para_gravar(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    # Art. 17, § 1o: sustado so se retira com autorizacao judicial — e a
    # desistencia e a retirada do titulo pelo credor, antes do protesto.
    _recusar_se_sustado(con, titulo_id, "a desistência")
    if tit["situacao"] not in ("RECEBIDO", "APONTADO", "INTIMADO"):
        raise ProtestoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — só se desiste antes do protesto lavrado.")
    # O PIX QUE ESPERA O CRÉDITO (29/10/2026): o dinheiro do devedor pode
    # estar na conta; desistir por cima dele o deixaria sem destino.
    import protesto_pix as PIX
    PIX.recusar_se_esperando(con, titulo_id, "a desistência")
    razao = (motivo or "").strip()
    if len(razao) < 5:
        raise ProtestoError("Escreva o motivo da desistência.")

    detalhe = {"motivo": razao}
    bd = banco(con)
    ato_id = int(bd.escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (titulo_id, "DESISTENCIA", agora, json.dumps(detalhe, ensure_ascii=False),
         origem, agora, usuario))[0]["id"])
    bd.escrever("UPDATE pt_titulos SET situacao='DESISTIDO' WHERE id=%s",
               (titulo_id,))
    return {"ato_id": ato_id, "titulo_id": titulo_id, "motivo": razao}


# ------------------------------------------------------------- o pagamento


def recusar_pagamento_na_situacao(tit: dict) -> None:
    """Recusa o pagamento que a situação do título não comporta. Só calcula.

    Uma régua só para as duas portas do pagamento — `lancar_pagamento` e o
    registro do PIX (`protesto_pix.registrar`): se as duas divergissem, o PIX
    entraria esperando o crédito num título em que o pagamento nunca caberia.
    """
    if tit["situacao"] == "PROTESTADO":
        raise ProtestoError(
            f"O título {tit['numero_titulo']} já está PROTESTADO, e protesto "
            f"lavrado não se paga mais nesta serventia (decisão do oficial de "
            f"21/10/2026). O devedor paga diretamente ao credor e pede o "
            f"CANCELAMENTO do protesto com a carta de anuência do credor, com "
            f"firma reconhecida (Lei 9.492/1997, art. 26, § 1º; Código de "
            f"Normas do TJMA, art. 942, § 2º).")
    if tit["situacao"] in SITUACOES_FINAIS:
        raise ProtestoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — não há como registrar pagamento.")


def lancar_pagamento(con, titulo_id: int, *, sv: dict,
                     agora: str, data_extenso: str,
                     valor_pago: Any = None, usuario: str | None = None,
                     origem: str = "MANUAL", forma_pagamento: Any = None,
                     forma_identificacao: Any = None,
                     emolumentos: Any = None, pix_id: Any = None) -> dict:
    """Registra o pagamento do título, com baixa. ESCREVE.

    PIX SÓ COM O CRÉDITO CONFERIDO (29/10/2026). Forma PIX exige `pix_id`:
    o PIX registrado em `protesto_pix` e com o crédito conferido (pelo
    extrato do banco, ou à mão com afirmação expressa). Sem ele, recusa — e a
    frase diz o caminho. O valor é o do crédito conferido, a identificação no
    Livro sai do PIX quando ninguém a escreveu, e o PIX fica amarrado ao ato.
    Com PIX do título ainda esperando o crédito, nenhum OUTRO pagamento entra.

    O LIVRO DE PAGAMENTOS TEM COLUNAS QUE O ATO NÃO GUARDAVA — Código de
    Normas do TJMA (Prov. 28/2026), art. 930: valor do pagamento, valor dos
    EMOLUMENTOS, e nas ocorrências «se o pagamento se dará em espécie ou por
    cheque, com a correspondente identificação». Até 14/10/2026 só o valor
    entrava, e opcional. `forma_pagamento` é do vocabulário
    `FORMAS_DE_PAGAMENTO`; forma desconhecida recusa.

    Cabe ANTES DO PROTESTO — recebido, apontado ou intimado. Até 21/10/2026
    cabia também no título já protestado (decisão do oficial de 24/08/2026);
    desde então, por decisão dele (LH13, pergunta 17, letra c), «protesto nao
    pode ser pago na serventia depois de lavrar»: o PROTESTADO se recusa com a
    frase que diz o caminho — o credor, a carta de anuência e o cancelamento
    (Lei 9.492/1997, art. 26, § 1º; CN-MA art. 942, § 2º). Ver
    `SITUACOES_SEM_PAGAMENTO`. Também recusa título que já chegou a uma
    situação final (`SITUACOES_FINAIS`): pago de novo, ou pago depois de
    desistido, não fazem sentido.

    Ocupa lugar no Livro de Registro de Pagamentos (PT_PAGAMENTO) — 120 por
    folha, sem verso, medido no acervo — de todo jeito: a série exige
    registrar o pagamento, tenha ou não havido protesto antes.

    `valor_pago`, quando informado, fica no detalhe do ato. Não confere
    contra o saldo do título — decidir o que fazer com pagamento parcial é
    do oficial, não deste módulo.
    """
    tit = titulo_para_gravar(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    # Art. 17, § 1o: sustado so se PAGA com autorizacao judicial.
    # Receber o dinheiro de um titulo que o juiz mandou parar e tao
    # grave quanto lavrar o ato.
    _recusar_se_sustado(con, titulo_id, "o pagamento")
    recusar_pagamento_na_situacao(tit)

    forma = str(forma_pagamento or "").strip().upper()
    if forma and forma not in FORMAS_DE_PAGAMENTO:
        raise ProtestoError(
            f"Forma de pagamento desconhecida: {forma!r}. As que existem "
            f"são: {', '.join(FORMAS_DE_PAGAMENTO.values())}.")
    # PIX NÃO É PAGAMENTO ATÉ O CRÉDITO SER CONFERIDO — 29/10/2026. O PIX
    # entrou em 16/10/2026 e foi lançado só em 21/10, «por PIX», sem
    # comprovante e sem item marcado; o selo falhou, o ato se desfez, o título
    # ficou PAGO e a CRA foi informada com a data do lançamento — e o oficial
    # levou 8 dias para conseguir confirmar se o dinheiro tinha entrado. A
    # recusa vale para toda tela que chame esta função.
    import protesto_pix as PIX
    pix = None
    if forma in PIX.FORMAS_QUE_ESPERAM_O_CREDITO:
        if pix_id in (None, ""):
            raise ProtestoError(
                "PIX NÃO É PAGAMENTO ATÉ O CRÉDITO SER CONFERIDO (ordem do "
                "oficial, 29/10/2026). Registre o PIX em «Pagamento por PIX», na "
                "ficha do título, com o COMPROVANTE anexado: ele fica aguardando "
                "o crédito, o título não vira PAGO, e o pagamento se lavra quando "
                "o crédito for localizado no banco — ou confirmado pelo oficial "
                "ou pelo gerente, com afirmação expressa.")
        pix = PIX.para_o_pagamento(con, titulo_id, pix_id)
        if (valor_pago not in (None, "")
                and centavos(valor_pago) != int(pix["valor_centavos"])):
            raise ProtestoError(
                f"O valor pago tem de ser o do crédito conferido: R$ "
                f"{PIX.reais(int(pix['valor_centavos']))}.")
        valor_pago = PIX.reais(int(pix["valor_centavos"]))
        if not str(forma_identificacao or "").strip():
            forma_identificacao = PIX.identificacao_para_o_livro(pix)
    elif pix_id not in (None, ""):
        raise ProtestoError(
            "O crédito conferido é de um PIX: lance o pagamento com a forma "
            "«por PIX».")
    PIX.recusar_se_esperando(con, titulo_id, "outro pagamento",
                             exceto_pix_id=pix["id"] if pix else None)

    detalhe: dict[str, Any] = {}
    if valor_pago is not None:
        detalhe["valor_pago_centavos"] = centavos(valor_pago)
    if forma:
        detalhe["forma_pagamento"] = forma
        ident = str(forma_identificacao or "").strip()
        if forma == "CHEQUE" and not ident:
            raise ProtestoError(
                "Pagamento em cheque: informe o banco e o número do cheque — "
                "o Livro de Pagamentos exige a identificação (Código de "
                "Normas, art. 930, III).")
        if ident:
            detalhe["forma_identificacao"] = ident
    if emolumentos is not None and str(emolumentos).strip():
        detalhe["emolumentos_centavos"] = centavos(emolumentos)
    if pix:
        detalhe["pix"] = PIX.para_o_detalhe(pix)
        # A DATA DO PAGAMENTO É A DO CRÉDITO, e não a do lançamento (ordem do
        # oficial, 29/10/2026). `data_ato` continua a do assentamento (CN-MA
        # art. 930, b); esta sai no Livro de Pagamentos e no D da CENPROT.
        detalhe["data_do_pagamento"] = PIX.data_do_pagamento(pix)

    bd = banco(con)
    ato_id = int(bd.escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (titulo_id, "PAGAMENTO", agora, json.dumps(detalhe, ensure_ascii=False),
         origem, agora, usuario))[0]["id"])
    if pix:
        PIX.vincular_ao_ato(con, int(pix["id"]), ato_id)

    lugar = ESC.reservar(con, SERIE_PAGAMENTO, "pt_atos", ato_id, sv=sv,
                         agora=agora, data_extenso=data_extenso, paginas=1,
                         usuario=usuario)
    bd.escrever(
        """UPDATE pt_atos SET livro_id=%s, folha=%s, verso=%s, numero_ordem=%s,
                              rotulo=%s WHERE id=%s""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    bd.escrever("UPDATE pt_titulos SET situacao='PAGO' WHERE id=%s",
               (titulo_id,))
    return {"ato_id": ato_id, "titulo_id": titulo_id, **lugar}


# ---------------------------------------------------------- o cancelamento


def protesto_em_pe(con, titulo_id: int) -> bool:
    """Se o título tem protesto lavrado (e não anulado) que não se cancelou.
    Só LÊ."""
    return banco(con).um(
        """SELECT 1 AS um FROM pt_atos p
            WHERE p.titulo_id = %s AND p.tipo = 'PROTESTO' AND p.cancelado = 0
              AND NOT EXISTS (SELECT 1 FROM pt_atos c
                               WHERE c.titulo_id = p.titulo_id
                                 AND c.tipo = 'CANCELAMENTO' AND c.cancelado = 0)
            ORDER BY p.id LIMIT 1""", (int(titulo_id),)) is not None


def hipoteses_que_cabem(con, tit: dict) -> dict[str, dict[str, str]]:
    """As hipóteses de cancelamento que cabem no título AGORA. Só LÊ.

    No PROTESTADO, o catálogo inteiro. No PAGO com protesto em pé — o legado
    da regra de 24/08/2026, que deixava pagar depois do protesto —, só
    `HIPOTESES_DO_PAGO_DEPOIS_DO_PROTESTO` (LH13, 21/10/2026): sem isso ele
    ficava para sempre na certidão positiva, sem caminho de baixa. Nos outros,
    nenhuma. É a mesma conta na ficha (o que se oferece) e em
    `lancar_cancelamento` (o que se aceita).
    """
    situacao = (tit or {}).get("situacao")
    if situacao == "PROTESTADO":
        return dict(CATALOGO_CANCELAMENTO)
    if situacao == "PAGO" and protesto_em_pe(con, int(tit["id"])):
        return {k: v for k, v in CATALOGO_CANCELAMENTO.items()
                if k in HIPOTESES_DO_PAGO_DEPOIS_DO_PROTESTO}
    return {}


def lancar_cancelamento(con, titulo_id: int, *,
                        hipotese: str, fundamento: str, agora: str,
                        usuario: str | None = None,
                        origem: str = "MANUAL",
                        modelo_do_termo: str | None = None) -> dict:
    """Cancela o registro do protesto, com hipótese do catálogo. ESCREVE.

    Só cabe título PROTESTADO — cancelar o que nunca foi protestado não faz
    sentido; para isso há a desistência (antes do protesto) ou não há nada
    a fazer (título pago sem protesto). A EXCEÇÃO É O LEGADO (LH13,
    21/10/2026): o título PAGO aqui depois de protestado, pela regra que valeu
    de 24/08 a 21/10/2026, tem o protesto em pé, e se cancela pela anuência do
    credor ou por ordem judicial (`hipoteses_que_cabem`). Recusa hipótese
    fora do catálogo, e recusa fundamento vazio: o defeito medido no acervo
    foi exatamente 56 cancelamentos com o mesmo motivo genérico, "Erro
    Material", metade sem dizer por quê.

    Não ocupa lugar em livro próprio — o cancelamento é anotação no próprio
    registro do protesto, e o acervo não tem Livro de Cancelamento.

    **E LAVRA O TERMO** (LD04, 21/10/2026): Lei 9.492/1997, art. 26, § 6º —
    no registro eletrônico, «o termo do cancelamento será lançado em
    documento apartado». Ele vai a `pt_atos.teor` do próprio ato, e congela
    ali como o termo do protesto. `modelo_do_termo` é o que o oficial editou
    no catálogo (`PT_TERMO_CANCELAMENTO`); sem ele, o padrão.
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
    tit = titulo_para_gravar(con, titulo_id)
    if not tit:
        raise ProtestoError(f"Título {titulo_id} não encontrado.")
    cabem = hipoteses_que_cabem(con, tit)
    if not cabem:
        raise ProtestoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — só se cancela protesto já lavrado.")
    if hipotese not in cabem:
        raise ProtestoError(
            f"O título {tit['numero_titulo']} foi PAGO nesta serventia depois "
            f"de protestado, pela regra que valeu até 21/10/2026, e o protesto "
            f"continua em pé. Para ele o cancelamento cabe pela "
            f"{' ou pela '.join(v['rotulo'].lower() for v in cabem.values())} "
            f"— e não pela hipótese «{CATALOGO_CANCELAMENTO[hipotese]['rotulo']}»: "
            f"protesto lavrado não se paga mais na serventia, e o caminho é a "
            f"carta de anuência do credor (Lei 9.492/1997, art. 26, § 1º; "
            f"Código de Normas do TJMA, art. 942, § 2º).")

    catalogo = CATALOGO_CANCELAMENTO[hipotese]
    detalhe = {"hipotese": hipotese, "rotulo": catalogo["rotulo"],
              "fundamento_legal": catalogo["fundamento_legal"]}
    # O TERMO SE MONTA ANTES DE GRAVAR: o modelo quebrado recusa aqui, sem
    # ato nenhum lançado. O protesto que ele identifica é o que está em pé.
    bd = banco(con)
    termo = TERMO.montar_cancelamento(
        modelo=modelo_do_termo, data=agora, hipotese=catalogo["rotulo"],
        fundamento_legal=catalogo["fundamento_legal"], fundamento=razao,
        qualificacao_do_registro=TERMO.fatos_da_qualificacao(bd, int(titulo_id)))
    ato_id = int(bd.escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, observacao,
               detalhe_json, teor, origem, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (titulo_id, "CANCELAMENTO", agora, razao,
         json.dumps(detalhe, ensure_ascii=False), termo, origem, agora,
         usuario))[0]["id"])
    bd.escrever("UPDATE pt_titulos SET situacao='CANCELADO' WHERE id=%s",
               (titulo_id,))
    return {"ato_id": ato_id, "titulo_id": titulo_id,
           "fundamento": razao, **detalhe}
