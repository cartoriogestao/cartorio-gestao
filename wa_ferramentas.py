"""As ferramentas do escrevente do WhatsApp: o que a IA consulta e deixa pronto no sistema.

Pedido do oficial em 14/11/2026: o WhatsApp «abre tarefas e encaminha ao
escrevente responsável», «recebe documentos e dá protocolo (criando tarefa)
quando o cliente expressamente requerer» e «prepara encaminhamentos no sistema,
deixando para o escrevente revisar e finalizar».

SÃO TRÊS, E NENHUMA LAVRA
    `abrir_pedido`     grava ou completa o pedido (`wa_pedido`) e a tarefa do
                       escrevente do setor; com `protocolo`, devolve o número do
                       protocolo de atendimento. Não abre protocolo do Caixa,
                       não prenota, não cobra e não sela.
    `consultar_valor`  a estimativa pela tabela de emolumentos da casa, só para
                       o item da lista que o oficial aprovou. O número sai do
                       cálculo de custas, e nunca do modelo.
    `consultar_norma`  os artigos da base normativa da casa, com a citação.

O QUE A FERRAMENTA ALCANÇA É SÓ ESTA CONVERSA
    Nenhuma recebe número de conversa, de cliente ou de protocolo por argumento:
    o alcance vem do `Contexto`, montado por quem atende. O pior que um texto
    malicioso consegue é abrir pedido nesta conversa — que uma pessoa lê.

NO ENSAIO NADA SE GRAVA
    `abrir_pedido` devolve o que diria, sem escrever. As outras duas só leem.

ESTE MÓDULO NÃO IMPORTA O ATENDENTE
    Quem abre a tarefa é `wa_atendente._tarefa_do_pedido`, que chega aqui pelo
    `Contexto`. Importá-lo fecharia um círculo com `wa_escrevente`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from bd_nativo import banco

import ajuda_privacidade as PRIV
import wa_fila as FILA
import wa_horario as HORARIO
import wa_oficio as OFICIO
import wa_pedido as PEDIDO
import wa_schema as WA
import wa_vocabulario as VOCAB

LOG = logging.getLogger("cartorio.wa_ferramentas")

POR = "atendente com IA"
TAMANHO_DO_RESUMO = 300
TAMANHO_DO_QUE_FALTA = 300
TETO_DA_NORMA = 6_000
ARTIGOS = 3

ABRIR_PEDIDO = "abrir_pedido"
CONSULTAR_VALOR = "consultar_valor"
CONSULTAR_NORMA = "consultar_norma"


def definicoes() -> list[dict]:
    """As ferramentas como o transporte as recebe. Só calcula, e é ESTÁVEL: elas
    vão no prefixo que o provedor guarda, e mudar um caractere o invalida."""
    servicos = "; ".join(f"{s['id']} = {s['nome']} ({s['quando']})" for s in OFICIO.SERVICOS)
    return [
        {"nome": ABRIR_PEDIDO,
         "descricao": (
             "Deixa o caso encaminhado ao escrevente responsável: grava o pedido e abre a "
             "tarefa dele no sistema. Use quando a pessoa quer o serviço feito, pede para "
             "falar com alguém, traz caso concreto, manda documento para conferir, ou "
             "quando a resposta não está nas suas fontes. Chamar de novo com o mesmo "
             "serviço COMPLETA o pedido que já existe (não duplica): use para acrescentar "
             "o que a pessoa contou depois. O resumo é para o escrevente, e o cliente não "
             "o vê: escreva o fato (o que ela quer, de quem ou de qual imóvel, o que já "
             "tem em mãos), sem dado pessoal além do que ela mesma escreveu. A resposta "
             "diz o número do pedido, o setor, quem é o responsável e quando o cartório "
             "volta a atender. Serviços: " + servicos + "."),
         "schema": {
             "type": "object",
             "properties": {
                 "servico": {"type": "string", "enum": [s["id"] for s in OFICIO.SERVICOS],
                             "description": "O serviço que a pessoa quer feito. Arquivo para "
                                            "registrar uma escritura é registro_imovel; "
                                            "conferir_arquivo só quando ainda não se sabe "
                                            "para que serve o arquivo."},
                 "resumo": {"type": "string",
                            "description": "O fato para o escrevente, em até três frases."},
                 "falta": {"type": "string",
                           "description": "O que ainda falta a pessoa informar ou trazer, "
                                          "se você souber. Opcional."},
                 "urgente": {"type": "boolean",
                             "description": "Verdadeiro só com prazo que vence hoje ou "
                                            "amanhã, sepultamento, viagem marcada ou "
                                            "risco de protesto."},
                 "protocolo": {"type": "boolean",
                               "description": "Verdadeiro só quando a pessoa pediu "
                                              "expressamente protocolo ou comprovante de "
                                              "que entregou os documentos."},
             },
             "required": ["servico", "resumo"],
         }},
        {"nome": CONSULTAR_VALOR,
         "descricao": (
             "Calcula a estimativa de um ato pela tabela de emolumentos da casa. `item` é o "
             "número da LISTA DE VALORES. Item marcado «pelo valor do negócio» precisa de "
             "`valor_do_negocio`, em reais: pergunte ao cliente antes, se ele não disse. "
             "Compra de imóvel soma dois itens: a escritura e o registro. Nunca escreva "
             "valor em dinheiro que não tenha saído desta ferramenta nesta conversa."),
         "schema": {
             "type": "object",
             "properties": {
                 "item": {"type": "integer"},
                 "valor_do_negocio": {"type": "number"},
                 "quantidade": {"type": "integer", "minimum": 1, "maximum": 50},
             },
             "required": ["item"],
         }},
        {"nome": CONSULTAR_NORMA,
         "descricao": (
             "Busca na base normativa da casa (Lei de Registros Públicos, Lei dos "
             "Cartórios, Lei de Protesto, Código Civil, Código de Normas do Maranhão, "
             "Código Nacional de Normas) os artigos sobre um assunto. Use quando a "
             "pergunta é sobre uma regra ou um prazo de lei que o manual não traz. Não "
             "use para pergunta de balcão que o manual responde. Achado que não responde "
             "à pergunta não é resposta: encaminhe."),
         "schema": {
             "type": "object",
             "properties": {"termo": {"type": "string",
                                      "description": "O assunto, em poucas palavras."}},
             "required": ["termo"],
         }},
    ]


@dataclass
class Contexto:
    """O alcance das ferramentas nesta resposta. Quem monta é `wa_escrevente`."""
    db: Any
    conversa: dict
    cfg: dict
    agora: str
    ensaio: bool = False
    # (pedido_id, *, setor, servico, resumo, relato, quando, urgente, arquivos) -> id | None
    abrir_tarefa: Callable | None = None
    relato: str = ""               # o que a pessoa contou, sem dado pessoal
    arquivos: int = 0              # quantos arquivos ela mandou neste atendimento
    rotina: dict = field(default_factory=dict)
    abertos: list[dict] = field(default_factory=list)   # o que ESTA resposta abriu
    valores: list[str] = field(default_factory=list)    # as estimativas desta resposta


# ------------------------------------------------------------- o que se lê


def primeiro_nome(nome: Any) -> str:
    return str(nome or "").strip().split(" ")[0][:30]


def responsavel_do_setor(con: Any, setor: str) -> dict:
    """{user_id, nome} de quem responde pelo setor, ou vazio. SÓ LÊ.

    O balcão geral (ATENDIMENTO) não tem linha em `ge_responsaveis`: vale quem a
    tela do atendente diz que responde pelo balcão (15/11/2026), e o mesmo para o
    setor que ficou sem responsável. Sem ninguém, a tarefa nasce sem dono."""
    try:
        linha = banco(con).um(
            """SELECT r.user_id, u.full_name FROM ge_responsaveis r
                 LEFT JOIN users u ON u.id = r.user_id
                WHERE r.setor=%s""", (setor,))
    except Exception:                               # noqa: BLE001
        LOG.exception("o responsável do setor não foi lido")
        return {}
    if linha and linha.get("user_id"):
        return {"user_id": int(linha["user_id"]),
                "nome": primeiro_nome(linha.get("full_name"))}
    return dono_do_balcao(con)


def dono_do_balcao(con: Any) -> dict:
    """{user_id, nome} de quem responde pelo balcão geral, gravado na tela do
    atendente; vazio se ninguém foi escolhido ou se a pessoa não está ativa. SÓ LÊ."""
    import wa_balcao as BALCAO
    valor = BALCAO.ler_config(con, WA.CHAVE_DONO_DO_BALCAO)
    if not valor.isdigit():
        return {}
    linha = banco(con).um("SELECT id, full_name FROM users WHERE id=%s AND active=1",
                          (int(valor),))
    if not linha:
        return {}
    return {"user_id": int(linha["id"]), "nome": primeiro_nome(linha.get("full_name"))}


def quando_responde(rotina: dict, agora: str) -> str:
    """«o cartório está aberto agora» ou quando reabre. Só calcula.

    Sem horário gravado não se promete nada: a frase sai vazia."""
    regra = (rotina or {}).get("regra")
    if not regra:
        return ""
    quando = FILA._dt(agora) or datetime.now()
    if HORARIO.aberto(regra, quando):
        return "O cartório está aberto agora."
    abre = HORARIO.quando_abre(regra, quando)
    return f"O cartório está fechado agora e reabre {abre}." if abre else ""


def numero_do_protocolo(pedido_id: int, quando: str) -> str:
    """O protocolo de atendimento do WhatsApp. Só calcula.

    NÃO É O PROTOCOLO DO CAIXA NEM A PRENOTAÇÃO: é o número do pedido, com o ano
    e o prefixo que o distingue dos dois («2026.11.4» é do Caixa)."""
    return f"WA-{str(quando)[:4]}-{int(pedido_id):05d}"


# ------------------------------------------------------------- abrir_pedido


def _texto(valor: Any, teto: int) -> str:
    return " ".join(str(valor or "").split())[:teto]


def _sem_dado(texto: str) -> str:
    """O resumo que o modelo escreveu, sem CPF, telefone nem e-mail. Só calcula.

    O modelo só viu o que subiu mascarado: o resumo dele não traz nome de cliente
    para esconder. A máscara inteira aqui (até 15/11/2026) trocava a cidade e a
    «Justiça Federal» por [PESSOA_01], e o escrevente lia um enigma (achado no
    ensaio com o modelo de verdade). Fica a barreira dos identificadores
    inequívocos, para o caso de o modelo escrever um número que pareça um."""
    try:
        return " ".join(PRIV.sanitizar_para_modelo(texto, nomes_livres=False,
                                                   texto_publico=True).split())
    except PRIV.PrivacidadeError:
        return ""


def abrir_pedido(ctx: Contexto, args: dict) -> tuple[str, bool]:
    servico = OFICIO.servico_valido(args.get("servico"))
    if not servico:
        return ("Serviço fora da lista. Escolha um dos ids da descrição da ferramenta.", True)
    resumo = _sem_dado(_texto(args.get("resumo"), TAMANHO_DO_RESUMO))
    if len(resumo) < 8:
        return ("O resumo veio vazio ou só com dado pessoal. Escreva o fato para o "
                "escrevente em uma frase.", True)
    falta = _sem_dado(_texto(args.get("falta"), TAMANHO_DO_QUE_FALTA))
    urgente = bool(args.get("urgente"))
    quer_protocolo = bool(args.get("protocolo"))
    setor = OFICIO.setor_do_servico(servico)
    if setor == WA.SETOR_PADRAO:
        # orientação e conferência seguem o setor que a conversa já tem
        setor = FILA.setor_valido(ctx.conversa.get("setor")) or WA.SETOR_PADRAO
        if setor == "GESTAO":
            setor = WA.SETOR_PADRAO
    nome_setor = WA.SETORES.get(setor, setor)
    texto = resumo + (f" Falta: {falta}" if falta else "")
    if ctx.ensaio:
        ctx.abertos.append({"id": 0, "setor": setor, "servico": servico, "resumo": texto,
                            "novo": True, "urgente": urgente})
        return (f"(ensaio) O pedido seria aberto para {nome_setor} — "
                f"{OFICIO.nome_do_servico(servico)}. Nada foi gravado.", False)
    try:
        with ctx.db.transaction() as con:
            gravado = PEDIDO.abrir(con, int(ctx.conversa["id"]), setor=setor, servico=servico,
                                   resumo=texto, orientacao="", por=POR, quando=ctx.agora)
        with ctx.db.connect() as con:
            dono = responsavel_do_setor(con, setor)
    except Exception:                               # noqa: BLE001
        LOG.exception("o pedido do WhatsApp não abriu")
        return ("O pedido não pôde ser gravado agora. Diga ao cliente que o recado será "
                "passado ao escrevente, sem prometer número.", True)
    pid = int(gravado["id"])
    tarefa = None
    if ctx.abrir_tarefa:
        tarefa = ctx.abrir_tarefa(pid, setor=setor, servico=servico, resumo=texto,
                                  relato=ctx.relato, quando=ctx.agora, urgente=urgente,
                                  arquivos=ctx.arquivos)
    ctx.abertos.append({"id": pid, "setor": setor, "servico": servico, "resumo": texto,
                        "novo": bool(gravado.get("novo")), "urgente": urgente,
                        "tarefa": tarefa})
    partes = [f"Pedido nº {pid} {'aberto' if gravado.get('novo') else 'completado'} para "
              f"{nome_setor} — {OFICIO.nome_do_servico(servico)}."]
    partes.append(f"Responsável: {dono['nome']}." if dono.get("nome")
                  else "Responsável: o escrevente do balcão (ainda sem nome definido).")
    if ctx.arquivos:
        partes.append(f"O escrevente vê na conversa o(s) {ctx.arquivos} arquivo(s) enviado(s).")
    volta = quando_responde(ctx.rotina, ctx.agora)
    if volta:
        partes.append(volta)
    if quer_protocolo:
        partes.append(
            f"Protocolo de atendimento: {numero_do_protocolo(pid, ctx.agora)}. Informe este "
            "número e diga que é o recebimento para análise do escrevente, e não o "
            "protocolo oficial do título.")
    partes.append("Não prometa data de entrega.")
    return (" ".join(partes), False)


# ------------------------------------------------------------- consultar_valor


def tabela_de_faixa(codigo_tj: str) -> int | None:
    """O número da tabela de faixas daquele item, ou None se é de valor fixo.

    Lê os rótulos de `emolumentos.TABELAS_FAIXA` («13.1 — Notas: ...»): a
    correspondência mora lá, e não numa segunda lista aqui."""
    import emolumentos as EMOL
    for numero, rotulo in EMOL.TABELAS_FAIXA.items():
        if str(rotulo).split(" ")[0].strip() == str(codigo_tj).strip():
            return int(numero)
    return None


def valores_para_o_modelo(valores: list[dict]) -> str:
    """A lista de valores como vai na instrução. Só calcula."""
    linhas = []
    for v in valores:
        faixa = " (pelo valor do negócio)" if tabela_de_faixa(v["codigo_tj"]) else ""
        linhas.append(f"{v['id']} | {v['nome']}{faixa}")
    return "\n".join(linhas) or "(vazia — nenhum valor aprovado: encaminhe a pergunta de preço)"


def estimar(con: Any, item: dict, *, hoje: str, valor_do_negocio: Any = None,
            quantidade: int = 1) -> tuple[str, str]:
    """(texto da estimativa, motivo de não dar). O número sai do cálculo. SÓ LÊ."""
    import ato_selado as ATO
    import custas as CUSTAS
    from caixa_schema import reais
    quantidade = max(1, min(int(quantidade or 1), 50))
    tabela = tabela_de_faixa(item["codigo_tj"])
    try:
        if tabela:
            if valor_do_negocio in (None, "") or float(valor_do_negocio) <= 0:
                return "", ("este item depende do valor do negócio: pergunte o valor ao "
                            "cliente e consulte de novo com `valor_do_negocio`")
            conta = CUSTAS.calcular(con, tabela=tabela, base=float(valor_do_negocio),
                                    data=hoje[:10])
        else:
            servico = ATO.servico_do_codigo_tj(con, item["codigo_tj"])
            if not servico:
                return "", f"o item {item['codigo_tj']} não está na tabela importada"
            conta = ATO.calcular_custas(con, servico=servico["codigo"], data=hoje[:10],
                                        quantidade=quantidade)
    except (ATO.AtoError, CUSTAS.CustasError, ValueError) as erro:
        return "", f"o cálculo de custas recusou: {erro}"
    total = int(conta.get("total_devido_centavos") or 0)
    if total == 0:
        return "", "o valor depende do caso (gratuidade ou item sem preço fixo)"
    vig = conta.get("vigencia_descricao") or "tabela vigente"
    de_que = item["nome"]
    if tabela:
        de_que += f", para negócio de R$ {reais(int(round(float(valor_do_negocio) * 100)))}"
        if conta.get("acima_do_teto"):
            de_que += " (acima da última faixa da tabela)"
    elif quantidade > 1:
        de_que += f", {quantidade} unidades"
    return (f"ESTIMATIVA pela tabela de emolumentos ({vig}): {de_que} — R$ {reais(total)}, "
            "com os fundos. É estimativa: o valor final é conferido pelo escrevente e pode "
            "mudar conforme o caso (quantidade, gratuidade, documentos, imposto à parte)."), ""


def consultar_valor(ctx: Contexto, args: dict) -> tuple[str, bool]:
    item = next((v for v in ctx.cfg.get("valores") or []
                 if str(v["id"]) == str(args.get("item"))), None)
    if not item:
        return ("Esse item não está na LISTA DE VALORES. Sem item que sirva, não informe "
                "valor: encaminhe a pergunta ao escrevente.", True)
    with ctx.db.connect() as con:
        texto, porque = estimar(con, item, hoje=ctx.agora,
                                valor_do_negocio=args.get("valor_do_negocio"),
                                quantidade=args.get("quantidade") or 1)
    if not texto:
        return (f"Não deu para estimar: {porque}.", True)
    ctx.valores.append(texto)
    return (texto, False)


# ------------------------------------------------------------- consultar_norma


def consultar_norma(ctx: Contexto, args: dict) -> tuple[str, bool]:
    termo = _texto(args.get("termo"), 200)
    if len(termo) < 3:
        return ("Diga o assunto em poucas palavras.", True)
    import normativa as NORMA
    setor = FILA.setor_valido(ctx.conversa.get("setor")) or ""
    atribuicao = {"RI": "RI", "NOTAS": "NOTAS"}.get(setor, "")
    try:
        achado = NORMA.trechos_para_o_pedido(termo, atribuicao=atribuicao, limite=ARTIGOS)
    except Exception:                               # noqa: BLE001
        LOG.exception("a base normativa não respondeu ao atendimento")
        return ("A base normativa não respondeu agora. Não cite artigo: encaminhe.", True)
    if not achado:
        return ("Nada achado na base normativa para esse assunto. Ausência de achado não "
                "prova ausência de regra: não afirme, encaminhe ao escrevente.", False)
    if len(achado) > TETO_DA_NORMA:
        achado = achado[:TETO_DA_NORMA] + "\n[…]"
    return (achado, False)


EXECUTORES: dict[str, Callable[[Contexto, dict], tuple[str, bool]]] = {
    ABRIR_PEDIDO: abrir_pedido,
    CONSULTAR_VALOR: consultar_valor,
    CONSULTAR_NORMA: consultar_norma,
}


def executar(ctx: Contexto, nome: str, argumentos: Any) -> tuple[str, bool]:
    """(o que a ferramenta devolve ao modelo, se é erro). Nunca levanta."""
    fn = EXECUTORES.get(str(nome or ""))
    if not fn:
        return (f"A ferramenta «{nome}» não existe.", True)
    try:
        return fn(ctx, argumentos if isinstance(argumentos, dict) else {})
    except Exception:                               # noqa: BLE001
        LOG.exception("a ferramenta %s do WhatsApp falhou", nome)
        return ("A ferramenta falhou agora. Siga sem ela: não invente o que ela diria.", True)
