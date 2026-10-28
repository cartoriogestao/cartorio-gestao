"""O atendente com IA do WhatsApp — o que ele responde sozinho, e o que passa.

    «ATENDENTE COM IA NO WHATSAPP» («é importante») — decisão do oficial,
    26/10/2026.

A REGRA ANTIGA FOI REVOGADA, E SÓ PARA QUATRO CASOS (26/10/2026)
    Desde 02/09/2026 a regra da casa era «autoenvio desligado»: o WhatsApp só
    preparava rascunho, e quem enviava era a pessoa (`wa_textos`, cabeçalho;
    `docs/decisoes/02_modelos_ia_privacidade.md`, «Mensageiro externo...»). Em
    26/10/2026 o oficial a REVOGOU PARA ESTES QUATRO CASOS, e só para eles:

      1. ANDAMENTO DO PROTOCOLO — só depois da identificação por NÚMERO +
         CÓDIGO DE ACOMPANHAMENTO impresso no recibo
         (`acompanhamento_cliente.consultar`);
      2. DÚVIDAS GERAIS (horário, endereço, documentos por ato) — a partir do
         TEXTO-BASE aprovado pelo oficial e editável na tela; a IA não responde
         fora dele;
      3. VALORES PELA TABELA de emolumentos — sempre marcados ESTIMATIVA, e o
         número sai do cálculo de custas da casa (`ato_selado.calcular_custas`
         sobre `cx_servicos`), e NUNCA do modelo: o modelo só escolhe QUAL item
         da lista que o oficial aprovou;
      4. TRANSCREVER O ÁUDIO do cliente, para a IA e para quem atende
         (`wa_transcricao`).

    TUDO O MAIS PASSA PARA UMA PESSOA, com a conversa marcada para o setor
    (`wa_fila.passar_para_pessoa`): quando o cliente pede, quando a IA não
    sabe, e sempre que o assunto é sensível — protesto, registro civil, dado
    pessoal, reclamação.

O QUE SEGURA ISSO
    - UM INTERRUPTOR GERAL, DESLIGADO DE FÁBRICA (`wa_schema.CHAVE_IA_LIGADA`).
      Só o ADMIN liga, e ligar grava quem e quando; só se responde o que chegou
      DEPOIS de ligado — o acúmulo de antes não recebe resposta automática.
      A transcrição tem interruptor próprio (`CHAVE_AUDIO_LIGADO`).
    - O REGISTRO DE CADA RESPOSTA (`wa_ia_registro`): o que a IA leu (já
      mascarado), o que respondeu, se saiu, provedor, modelo, tokens, segundos
      de áudio e custo. E o `ia_uso` da casa, que o transporte grava sozinho.
    - O QUE É DETERMINÍSTICO NÃO PASSA PELO MODELO: a identificação do
      protocolo, o limite de tentativas, o assunto sensível e o pedido de
      pessoa são decididos aqui, por regra, ANTES de qualquer rede. O número do
      protocolo e o código nunca sobem ao provedor.
    - A RESPOSTA DA DÚVIDA É CONFERIDA CONTRA O TEXTO-BASE: número que não
      está no texto-base, valor em dinheiro ou marcador de dado ocultado fazem
      a resposta não sair — a conversa passa para uma pessoa.
    - NADA DE REDE DENTRO DE `db.transaction()`: lê-se numa conexão curta,
      fala-se com a rede fora dela, e grava-se noutra transação curta.

O QUE SAI DA SERVENTIA (dito também na tela do atendente)
    Ao provedor que responde: a mensagem do cliente MASCARADA
    (`ajuda_privacidade.preparar_saida`), o texto-base e a lista de valores
    (que são da casa, aprovados pelo oficial, e não dado de cliente). Mensagem
    em que a máscara acha dado pessoal não sobe: passa para uma pessoa. À
    OpenAI, na transcrição: o ÁUDIO INTEIRO — áudio não se mascara.

IDENTIFICAÇÃO DO PROTOCOLO
    A interface é do módulo do portal do cliente, que é de outra passada:
    `acompanhamento_cliente.consultar(con, numero, codigo) -> dict | None`.
    None = não confere, e a resposta é a MESMA quer o número exista quer não
    (nunca se diz qual dos dois errou). Há limite de tentativas por telefone
    (`TENTATIVAS_POR_DIA`); passou, a conversa vai para uma pessoa. Enquanto o
    módulo não estiver instalado, o andamento passa para uma pessoa.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from unicodedata import normalize

from bd_nativo import banco

import agente_provedores as PROV
import ajuda_privacidade as PRIV
import ia_uso as USO
import identidade_do_robo as IDR
import wa_balcao as BALCAO
import wa_fila as FILA
import wa_schema as WA
import wa_transcricao as TRANSC

LOG = logging.getLogger("cartorio.wa_atendente")

AUTOR_IA = "ia"
FINALIDADE = "wa_atendente"
FINALIDADE_AUDIO = "wa_audio"

CASO_ANDAMENTO = "andamento"
CASO_IDENTIFICACAO_FALHOU = "identificacao_falhou"
CASO_PEDE_IDENTIFICACAO = "pede_identificacao"
CASO_DUVIDA = "duvida"
CASO_VALOR = "valor"
CASO_AUDIO = "audio"
CASO_PASSAGEM = "passagem"
ROTULO_DO_CASO = {
    CASO_ANDAMENTO: "andamento do protocolo",
    CASO_IDENTIFICACAO_FALHOU: "identificação que não conferiu",
    CASO_PEDE_IDENTIFICACAO: "pediu número e código",
    CASO_DUVIDA: "dúvida pelo texto-base",
    CASO_VALOR: "valor (estimativa)",
    CASO_AUDIO: "transcrição de áudio",
    CASO_PASSAGEM: "passou para pessoa",
}

PROVEDOR_PADRAO = "claude"
TENTATIVAS_POR_DIA = 5
JANELA_HORAS = 24          # a Meta só aceita resposta livre dentro de 24 h
PRAZO_IA = 40
PRESO_MINUTOS = 15         # «processando» mais velho que isso é rodada que caiu
CONVERSAS_POR_RODADA = 20
CONVERSAS_NA_TELA = 5      # o botão do balcão não espera a fila inteira
TAMANHO_DA_RESPOSTA = 1200
# O QUE SOBE AO MODELO TEM TETO DE TAMANHO (26/10/2026, revisão de segurança,
# MÉDIA). As mensagens pendentes da conversa sobem juntas, e o único freio era o
# `LIMITE_DE_ENVIO` de 900 mil caracteres do transporte — teto de engano, e não
# de custo: um cliente anônimo que mandasse dezenas de mensagens longas antes
# da rodada faria cada chamada levar centenas de milhares de tokens. Pergunta
# de balcão cabe em dois mil caracteres; acima disso a conversa vai para uma
# pessoa, sem subir. O pedido inteiro leva, além da pergunta, só a instrução.
TAMANHO_DA_PERGUNTA = 2000
FOLGA_DO_PEDIDO = 16_384   # bytes além da instrução: a pergunta (até ~8 KB em UTF-8) e o envelope
CONTEXTO_ANTERIOR = 4

RODAPE = ("\n\n— Resposta automática do atendimento. Para falar com uma "
          "pessoa, escreva ATENDENTE.")
TEXTO_PEDE_IDENTIFICACAO = (
    "Para consultar o andamento, mande o número do protocolo e o código de "
    "acompanhamento impresso no recibo, assim: protocolo 12345 código ABC123.")
TEXTO_NAO_CONFERE = (
    "Não consegui conferir esse protocolo com esse código. Confira os dois no "
    "recibo — o código de acompanhamento vem impresso nele — e mande de novo "
    "assim: protocolo NÚMERO código CÓDIGO.")
TEXTO_PASSAGEM = ("Sua mensagem foi passada para a equipe ({setor}). "
                  "Respondemos no horário de atendimento.")
TEXTO_BASE_EXEMPLO = (
    "HORÁRIO: [preencha os dias e o horário de atendimento]\n"
    "ENDEREÇO: [preencha o endereço completo]\n"
    "DOCUMENTOS — RECONHECIMENTO DE FIRMA: [preencha]\n"
    "DOCUMENTOS — AUTENTICAÇÃO DE CÓPIA: [preencha]\n"
    "DOCUMENTOS — CERTIDÃO DE MATRÍCULA: [preencha]\n")

# O que a máscara acha e faz a mensagem ir para uma pessoa. NOME NÃO ENTRA: o
# nome é mascarado e a conversa segue — «sou a Maria» não é assunto sensível.
NAO_E_DADO_SENSIVEL = frozenset({"PESSOA"})


class AtendenteErro(ValueError):
    """Configuração do atendente recusada. Mensagem pronta para a tela."""


# ------------------------------------------------------------- a configuração


def _ler(con: Any, chave: str) -> str:
    return BALCAO.ler_config(con, chave)


def _numero(texto: Any) -> float | None:
    t = str(texto or "").strip().replace(",", ".")
    if not t:
        return None
    try:
        valor = float(t)
    except ValueError:
        return None
    return valor if valor >= 0 else None


def configuracao(con: Any) -> dict:
    """O que o atendente precisa saber da casa. SÓ LÊ."""
    provedor = _ler(con, WA.CHAVE_IA_PROVEDOR) or PROVEDOR_PADRAO
    try:
        provedor = PROV.normalizar_provedor(provedor)
    except PROV.AgenteError:
        provedor = PROVEDOR_PADRAO
    modelo = _ler(con, WA.CHAVE_IA_MODELO)
    preco_min = _numero(_ler(con, WA.CHAVE_AUDIO_PRECO_MINUTO))
    return {
        "ia_ligada": _ler(con, WA.CHAVE_IA_LIGADA) == "1",
        "ia_ligada_em": _ler(con, WA.CHAVE_IA_LIGADA_EM),
        "ia_ligada_por": _ler(con, WA.CHAVE_IA_LIGADA_POR),
        "audio_ligado": _ler(con, WA.CHAVE_AUDIO_LIGADO) == "1",
        "aviso_passagem": _ler(con, WA.CHAVE_IA_AVISO_PASSAGEM) == "1",
        "provedor": provedor,
        "modelo": modelo or PROV.modelo_de(provedor),
        "modelo_gravado": modelo,
        "preco_entrada": _numero(_ler(con, WA.CHAVE_IA_PRECO_ENTRADA)),
        "preco_saida": _numero(_ler(con, WA.CHAVE_IA_PRECO_SAIDA)),
        "audio_modelo": _ler(con, WA.CHAVE_AUDIO_MODELO) or TRANSC.MODELO_PADRAO,
        "audio_preco_minuto": (TRANSC.PRECO_PADRAO_POR_MINUTO if preco_min is None
                               else preco_min),
        "texto_base": _ler(con, WA.CHAVE_TEXTO_BASE),
        "texto_base_por": _ler(con, WA.CHAVE_TEXTO_BASE_POR),
        "texto_base_em": _ler(con, WA.CHAVE_TEXTO_BASE_EM),
        "valores_texto": _ler(con, WA.CHAVE_VALORES),
        "valores": ler_valores(_ler(con, WA.CHAVE_VALORES)),
        "prazo_minutos": FILA.prazo_minutos(con),
    }


def ler_valores(texto: str) -> list[dict]:
    """«codigo_tj | nome», um por linha → [{id, codigo_tj, nome}]. Só calcula.

    O `id` é a posição (1, 2, 3...): é ele que o modelo devolve, e não o código
    do Tribunal — o modelo escolhe da lista, e não inventa item."""
    saida = []
    for linha in str(texto or "").splitlines():
        if "|" not in linha:
            continue
        codigo, nome = (p.strip() for p in linha.split("|", 1))
        if codigo and nome:
            saida.append({"id": len(saida) + 1, "codigo_tj": codigo, "nome": nome})
    return saida


def conferir_valores(con: Any, texto: str) -> list[str]:
    """Os erros da lista de valores, linha por linha. SÓ LÊ."""
    import ato_selado as ATO
    erros = []
    for n, linha in enumerate(str(texto or "").splitlines(), start=1):
        if not linha.strip():
            continue
        if "|" not in linha:
            erros.append(f"Linha {n}: use «código do Tribunal | nome do ato».")
            continue
        codigo = linha.split("|", 1)[0].strip()
        if not ATO.servico_do_codigo_tj(con, codigo):
            erros.append(f"Linha {n}: o código «{codigo}» não está na tabela de "
                         "emolumentos importada.")
    return erros


def gravar_configuracao(con: Any, form: dict, *, por: str, agora: str) -> list[str]:
    """Grava o que a tela do atendente mandou. ESCREVE. Devolve os avisos.

    LIGAR grava quem e quando, e o «quando» é a régua: só se responde o que
    chegar depois. O texto-base gravado pelo ADMIN É a aprovação — fica quem
    aprovou e quando, e a IA só usa o que está gravado."""
    avisos = []
    valores = str(form.get("valores") or "").replace("\r\n", "\n").strip()
    erros = conferir_valores(con, valores)
    if erros:
        raise AtendenteErro("A lista de valores não foi gravada: " + " ".join(erros))
    antes = configuracao(con)
    ligar = form.get("ia_ligada") == "1"
    if ligar and not antes["ia_ligada"]:
        BALCAO.gravar_config(con, WA.CHAVE_IA_LIGADA_EM, agora)
        BALCAO.gravar_config(con, WA.CHAVE_IA_LIGADA_POR, por)
    BALCAO.gravar_config(con, WA.CHAVE_IA_LIGADA, "1" if ligar else "")
    BALCAO.gravar_config(con, WA.CHAVE_AUDIO_LIGADO,
                         "1" if form.get("audio_ligado") == "1" else "")
    BALCAO.gravar_config(con, WA.CHAVE_IA_AVISO_PASSAGEM,
                         "1" if form.get("aviso_passagem") == "1" else "")
    provedor = str(form.get("provedor") or "").strip().lower()
    if provedor and provedor not in PROV.PROVEDORES:
        raise AtendenteErro("Provedor desconhecido.")
    BALCAO.gravar_config(con, WA.CHAVE_IA_PROVEDOR, provedor)
    for chave, campo in ((WA.CHAVE_IA_MODELO, "modelo"),
                         (WA.CHAVE_AUDIO_MODELO, "audio_modelo")):
        BALCAO.gravar_config(con, chave, str(form.get(campo) or "").strip()[:80])
    for chave, campo in ((WA.CHAVE_IA_PRECO_ENTRADA, "preco_entrada"),
                         (WA.CHAVE_IA_PRECO_SAIDA, "preco_saida"),
                         (WA.CHAVE_AUDIO_PRECO_MINUTO, "audio_preco_minuto")):
        bruto = str(form.get(campo) or "").strip()
        if bruto and _numero(bruto) is None:
            raise AtendenteErro(f"O preço «{bruto}» não é um número.")
        BALCAO.gravar_config(con, chave, bruto)
    prazo = str(form.get("prazo_minutos") or "").strip()
    if prazo and not (prazo.isdigit() and int(prazo) > 0):
        raise AtendenteErro("O prazo de resposta é um número inteiro de minutos.")
    BALCAO.gravar_config(con, WA.CHAVE_PRAZO_MINUTOS, prazo)
    base = str(form.get("texto_base") or "").replace("\r\n", "\n").strip()
    if base != antes["texto_base"]:
        BALCAO.gravar_config(con, WA.CHAVE_TEXTO_BASE, base)
        BALCAO.gravar_config(con, WA.CHAVE_TEXTO_BASE_POR, por if base else "")
        BALCAO.gravar_config(con, WA.CHAVE_TEXTO_BASE_EM, agora if base else "")
    BALCAO.gravar_config(con, WA.CHAVE_VALORES, valores)
    if ligar and not base:
        avisos.append("O atendente está ligado sem texto-base: dúvidas gerais "
                      "vão todas para uma pessoa até o texto ser gravado.")
    if ligar and "[preencha" in base.lower():
        avisos.append("O texto-base ainda tem «[preencha ...]». A IA não usa "
                      "colchete como informação, mas confira antes de deixar ligado.")
    return avisos


# --------------------------------------------------- as regras sem modelo


def _sem_acento(texto: Any) -> str:
    n = normalize("NFD", str(texto or ""))
    return "".join(c for c in n if not (0x300 <= ord(c) <= 0x36F)).lower()


_PEDE_PESSOA = re.compile(
    r"\b(atendente|humano|falar com (alguem|uma pessoa|um atendente|o cartorio|"
    r"a escrevente|o escrevente|o oficial|a oficial)|pessoa de verdade)\b")
_QUER_ANDAMENTO = re.compile(
    r"\b(andamento|protocolo|ficou pronto|ficou pronta|esta pronto|esta pronta|"
    r"ja esta pronto|ja esta pronta|acompanhar|acompanhamento|situacao do)\b")
_NUMERO = re.compile(
    r"\b(?:protocolo|pedido|numero|n[o.]?)\s*(?:do\s+protocolo\s*)?[:#nº°.-]*\s*"
    r"(\d[\d./-]{0,24}\d|\d)\b")
_CODIGO = re.compile(
    r"\bcod(?:igo)?\.?\s*(?:de\s+acompanhamento\s*)?[:#-]?\s*([a-z0-9][a-z0-9-]{2,23})\b")


def pede_pessoa(texto: str) -> bool:
    return bool(_PEDE_PESSOA.search(_sem_acento(texto)))


def assunto_sensivel(texto: str) -> tuple[str, str] | None:
    """(setor, motivo) do primeiro assunto sensível achado, ou None.

    AS PALAVRAS MORAM NA TABELA ÚNICA (`wa_fila.SETOR_POR_PALAVRA`, 27/10/2026):
    a mesma que define o setor na chegada. Aqui só valem os sensíveis
    (`FILA.SETORES_SENSIVEIS`), na ordem de antes."""
    for setor, motivo, _palavra in FILA.setores_pelo_texto(texto):
        if setor in FILA.SETORES_SENSIVEIS:
            return setor, motivo
    return None


def quer_andamento(texto: str) -> bool:
    return bool(_QUER_ANDAMENTO.search(_sem_acento(texto)))


def identificacao(texto: str) -> tuple[str, str] | None:
    """(número, código) quando a mensagem traz os DOIS, ou None. Só calcula.

    O código mantém a caixa original do que o cliente escreveu — quem compara
    é o portal, e não daqui."""
    bruto = str(texto or "")
    t = _sem_acento(bruto)
    numero = _NUMERO.search(t)
    codigo = _CODIGO.search(t)
    if not (numero and codigo):
        return None
    inicio, fim = codigo.span(1)
    valor = bruto[inicio:fim] if len(bruto) == len(t) else codigo.group(1)
    # «o código está no recibo» não é código: palavra comum, toda minúscula e
    # sem dígito, não se manda ao portal — gastaria uma tentativa do cliente.
    if not (any(c.isdigit() for c in valor) or valor.isupper()):
        return None
    return numero.group(1), valor


def tentativas_falhas(con: Any, wa_id: str, *, agora: str) -> int:
    inicio = (FILA._dt(agora) or datetime.now()) - timedelta(hours=24)
    return int(banco(con).valor(
        """SELECT count(*) AS n FROM wa_ia_registro
            WHERE wa_id=%s AND caso=%s AND quando >= %s""",
        (wa_id, CASO_IDENTIFICACAO_FALHOU, inicio.strftime("%Y-%m-%dT%H:%M:%S")))
        or 0)


def _consultar_protocolo(con: Any, numero: str, codigo: str) -> Any:
    """A interface do portal do cliente. Ausente o módulo, devolve `False`
    (diferente de None, que é «não confere»)."""
    try:
        import acompanhamento_cliente as AC
    except ImportError:
        return False
    return AC.consultar(con, numero, codigo)


def texto_do_andamento(r: dict) -> str:
    partes = [f"Protocolo {r.get('numero')}"]
    if r.get("atribuicao"):
        partes[0] += f" ({r['atribuicao']})"
    partes[0] += f": {r.get('situacao_publica') or 'situação não informada'}."
    if r.get("previsao"):
        partes.append(f"Previsão: {r['previsao']}.")
    if r.get("atualizado_em"):
        partes.append(f"Atualizado em {str(r['atualizado_em'])[:16].replace('T', ' ')}.")
    return " ".join(partes)


# --------------------------------------------------- a resposta conferida


_MARCA = re.compile(r"\[[A-Z_]+_\d+\]")


def resposta_cabe_no_texto_base(resposta: str, texto_base: str) -> str:
    """O motivo de a resposta NÃO poder sair, ou "" se ela pode. Só calcula.

    É a régua de «a IA não inventa fora do texto-base» que o código consegue
    medir: todo número que a resposta escreve tem de estar no texto-base (hora,
    dia, número da rua, telefone), não há valor em dinheiro (valor é o cálculo
    de custas, e não o modelo), e não há marcador de dado ocultado."""
    r = str(resposta or "").strip()
    if not r:
        return "a IA não escreveu resposta"
    if len(r) > TAMANHO_DA_RESPOSTA:
        return "a resposta da IA ficou longa demais"
    if "r$" in r.lower():
        return "a resposta da IA escreveu valor em dinheiro"
    if _MARCA.search(r):
        return "a resposta da IA repetiu um dado ocultado"
    da_base = set(re.findall(r"\d+", texto_base or ""))
    fora = sorted(set(re.findall(r"\d+", r)) - da_base)
    if fora:
        return ("a resposta da IA escreveu número que não está no texto-base ("
                + ", ".join(fora[:5]) + ")")
    return ""


def estimativa(con: Any, item: dict, *, hoje: str) -> tuple[str, str]:
    """(texto, motivo de não dar). O valor sai do cálculo da casa. SÓ LÊ."""
    import ato_selado as ATO
    from caixa_schema import reais
    servico = ATO.servico_do_codigo_tj(con, item["codigo_tj"])
    if not servico:
        return "", f"o item {item['codigo_tj']} não está na tabela importada"
    try:
        conta = ATO.calcular_custas(con, servico=servico["codigo"], data=hoje[:10])
    except ATO.AtoError as erro:
        return "", f"o cálculo de custas recusou: {erro}"
    total = int(conta.get("total_devido_centavos") or 0)
    if total == 0:
        # Zero sem gratuidade é item de faixa: o preço depende do valor do
        # negócio, e quem sabe é a pessoa. Gratuito também passa: gratuidade
        # depende de quem pede, e isso não se responde por WhatsApp.
        return "", "o valor depende do caso (item de faixa ou gratuidade)"
    vig = conta.get("vigencia_descricao") or "tabela vigente"
    return (f"ESTIMATIVA pela tabela de emolumentos ({vig}): {item['nome']} — "
            f"R$ {reais(total)} por ato, com os fundos. É uma estimativa: o valor "
            "final é conferido no balcão e pode mudar conforme o caso (quantidade, "
            "gratuidade, documentos)."), ""


def instrucao(cfg: dict) -> str:
    """O que o modelo recebe como sistema. Só calcula."""
    lista = "\n".join(f"{v['id']} | {v['nome']}" for v in cfg["valores"]) or "(vazia)"
    setores = ", ".join(WA.SETORES)
    return (
        "Você é o atendente automático do WhatsApp de uma serventia extrajudicial "
        "(cartório). Trate o cliente por «você», em português do Brasil, em frases "
        "curtas e educadas.\n"
        "REGRAS QUE NÃO SE NEGOCIAM:\n"
        "1. Responda SOMENTE com o que está no TEXTO-BASE abaixo, aprovado pelo "
        "oficial. Não use conhecimento próprio. Se a resposta não está no "
        "texto-base, a ação é \"pessoa\". Texto entre colchetes no texto-base não "
        "é informação.\n"
        "2. Nunca escreva valor em dinheiro, nem número que não esteja no "
        "texto-base. Para pergunta de preço, escolha o item da LISTA DE VALORES "
        "(tipo \"valor\", com o número do item em valor_id): o sistema calcula. "
        "Se nenhum item servir, a ação é \"pessoa\".\n"
        "3. Protesto, registro civil (nascimento, casamento, óbito), dados "
        "pessoais, reclamação, ou pedido de falar com alguém: ação \"pessoa\".\n"
        "4. Andamento de protocolo não se responde aqui: ação \"pessoa\".\n"
        "5. Marcadores entre colchetes na mensagem ([PESSOA_01] e outros) são "
        "dados ocultados: não os repita.\n"
        "Responda APENAS um objeto JSON, sem nada fora dele:\n"
        "{\"acao\": \"responder\" ou \"pessoa\", \"tipo\": \"duvida\" ou \"valor\", "
        "\"resposta\": \"texto ao cliente (vazio se pessoa ou valor)\", "
        "\"valor_id\": número ou null, \"setor\": um de [" + setores + "], "
        "\"motivo\": \"por quê, curto\"}\n"
        "=== TEXTO-BASE ===\n" + (cfg["texto_base"] or "(vazio)") + "\n"
        "=== LISTA DE VALORES ===\n" + lista + "\n")


def ler_decisao(texto: str) -> dict | None:
    """O JSON que o modelo devolveu, ou None se não há JSON legível."""
    achado = re.search(r"\{.*\}", str(texto or ""), re.S)
    if not achado:
        return None
    try:
        d = json.loads(achado.group(0))
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def custo_dos_tokens(entrada: int, saida: int, cfg: dict) -> float | None:
    if cfg["preco_entrada"] is None or cfg["preco_saida"] is None:
        return None
    return round((int(entrada or 0) * cfg["preco_entrada"]
                  + int(saida or 0) * cfg["preco_saida"]) / 1_000_000, 6)


# ------------------------------------------------------------- a decisão


def decidir(db: Any, conversa: dict, texto: str, cfg: dict, *, agora: str,
            pasta_de_dados: Any, conversar: Callable | None = None) -> dict:
    """O que fazer com as mensagens novas desta conversa. **PODE FALAR COM A
    REDE** (o provedor de IA), e por isso recebe `db`, e não `con`: cada leitura
    abre a sua conexão curta, e nenhuma transação fica aberta durante a rede.

    Devolve {"caso", "resposta" (texto ao cliente ou ""), "passar" (setor ou
    None), "motivo", "lido", e os números do provedor}."""
    base = {"caso": CASO_PASSAGEM, "resposta": "", "passar": None, "motivo": "",
            "lido": "", "provedor": None, "modelo": None, "entrada": 0,
            "saida": 0, "custo": None, "erro": ""}
    wa_id = conversa["wa_id"]
    setor_atual = FILA.setor_valido(conversa.get("setor")) or WA.SETOR_PADRAO
    if not texto.strip():
        return {**base, "passar": setor_atual,
                "motivo": "mensagem sem texto (anexo, ou áudio sem transcrição)"}
    if pede_pessoa(texto):
        return {**base, "passar": setor_atual, "motivo": "o cliente pediu uma pessoa",
                "lido": "(pedido de atendente)"}

    ident = identificacao(texto)
    if ident:
        numero, codigo = ident
        lido = f"identificação: protocolo {numero} (código omitido)"
        with db.connect() as con:
            if tentativas_falhas(con, wa_id, agora=agora) >= TENTATIVAS_POR_DIA:
                return {**base, "passar": setor_atual, "lido": lido,
                        "motivo": "tentativas de identificação esgotadas hoje"}
            achado = _consultar_protocolo(con, numero, codigo)
        if achado is False:
            return {**base, "passar": setor_atual, "lido": lido,
                    "motivo": "a consulta de protocolo ainda não está instalada"}
        if not achado:
            return {**base, "caso": CASO_IDENTIFICACAO_FALHOU, "lido": lido,
                    "resposta": TEXTO_NAO_CONFERE}
        return {**base, "caso": CASO_ANDAMENTO, "lido": lido,
                "resposta": texto_do_andamento(achado)}

    if quer_andamento(texto):
        return {**base, "caso": CASO_PEDE_IDENTIFICACAO,
                "lido": "(pedido de andamento sem número e código)",
                "resposta": TEXTO_PEDE_IDENTIFICACAO}

    sensivel = assunto_sensivel(texto)
    if sensivel:
        return {**base, "passar": sensivel[0], "motivo": sensivel[1],
                "lido": "(assunto sensível — não subiu à IA)"}
    if len(texto) > TAMANHO_DA_PERGUNTA:
        return {**base, "passar": setor_atual,
                "motivo": f"mensagem longa demais para a resposta automática "
                          f"({len(texto)} caracteres; o teto é {TAMANHO_DA_PERGUNTA})",
                "lido": "(mensagem longa — não subiu à IA)"}

    try:
        pacote = PRIV.preparar_saida(instrucao="", pergunta=texto)
    except PRIV.PrivacidadeError:
        return {**base, "passar": setor_atual, "motivo": "a mensagem tem dado pessoal",
                "lido": "(dado pessoal — não subiu à IA)"}
    achados = sorted(set(pacote.contagens) - NAO_E_DADO_SENSIVEL)
    if achados:
        return {**base, "passar": setor_atual,
                "motivo": "a mensagem tem dado pessoal (" + ", ".join(achados) + ")",
                "lido": "(dado pessoal — não subiu à IA)"}
    lido = pacote.pergunta
    if not cfg["texto_base"].strip():
        return {**base, "passar": setor_atual, "lido": lido,
                "motivo": "o texto-base do atendente ainda não foi aprovado"}
    with db.connect() as con:
        teto = USO.passou_do_teto(con, FINALIDADE, agora=agora)
    if teto:
        return {**base, "passar": setor_atual, "lido": lido,
                "motivo": "o teto de uso de IA do dia foi atingido"}

    fn = conversar or PROV.conversar
    numeros = {"provedor": cfg["provedor"], "modelo": cfg["modelo"]}
    sistema = instrucao(cfg)
    try:
        lida = fn(pasta_de_dados, provedor=cfg["provedor"], sistema=sistema,
                  conversa=[{"tipo": "user", "texto": lido}], ferramentas=[],
                  modelo=cfg["modelo"], maximo_de_saida=600, prazo=PRAZO_IA,
                  modulo="wa_atendente", finalidade="wa_atendente",
                  usuario=AUTOR_IA, referencia=f"wa_conversa:{conversa['id']}",
                  mascarado=True,
                  limite_de_envio=len(sistema.encode("utf-8")) + FOLGA_DO_PEDIDO)
    except Exception as falha:                          # noqa: BLE001
        return {**base, **numeros, "passar": setor_atual, "lido": lido,
                "motivo": "a IA não respondeu",
                "erro": getattr(falha, "motivo", "") or type(falha).__name__}
    numeros.update(modelo=lida.get("modelo") or cfg["modelo"],
                   entrada=int(lida.get("entrada") or 0),
                   saida=int(lida.get("saida") or 0))
    numeros["custo"] = custo_dos_tokens(numeros["entrada"], numeros["saida"], cfg)
    d = ler_decisao(lida.get("texto"))
    if not d:
        return {**base, **numeros, "passar": setor_atual, "lido": lido,
                "motivo": "a IA não respondeu no formato combinado"}
    setor_ia = FILA.setor_valido(d.get("setor")) or setor_atual
    if str(d.get("acao") or "").lower() != "responder":
        return {**base, **numeros, "passar": setor_ia, "lido": lido,
                "motivo": "a IA passou para pessoa: "
                          + str(d.get("motivo") or "sem motivo")[:200]}
    if str(d.get("tipo") or "").lower() == "valor":
        item = next((v for v in cfg["valores"]
                     if str(v["id"]) == str(d.get("valor_id"))), None)
        if not item:
            return {**base, **numeros, "passar": setor_ia, "lido": lido,
                    "motivo": "a IA escolheu um item fora da lista de valores"}
        with db.connect() as con:
            texto_valor, porque = estimativa(con, item, hoje=agora)
        if not texto_valor:
            return {**base, **numeros, "passar": setor_ia, "lido": lido,
                    "motivo": porque}
        return {**base, **numeros, "caso": CASO_VALOR, "lido": lido,
                "resposta": texto_valor}
    resposta = str(d.get("resposta") or "").strip()
    porque = resposta_cabe_no_texto_base(resposta, cfg["texto_base"])
    if porque:
        return {**base, **numeros, "passar": setor_ia, "lido": lido,
                "motivo": porque, "erro": resposta[:300]}
    return {**base, **numeros, "caso": CASO_DUVIDA, "lido": lido,
            "resposta": resposta}


# ------------------------------------------------------------- o registro


def _registrar(con: Any, conversa: dict, decisao: dict, *, enviado: bool,
               meta_id: str | None, agora: str, respondido: str = "") -> None:
    banco(con).escrever(
        """INSERT INTO wa_ia_registro (conversa_id, wa_id, quando, caso, lido,
               respondido, enviado, meta_id, passou_para, motivo, provedor, modelo,
               tokens_entrada, tokens_saida, segundos_audio, custo_usd, erro)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                   %s, %s)""",
        (int(conversa["id"]), conversa["wa_id"], agora, decisao["caso"],
         (decisao.get("lido") or "")[:4000], (respondido or "")[:4000],
         1 if enviado else 0, meta_id, decisao.get("passar"),
         (decisao.get("motivo") or "")[:500], decisao.get("provedor"),
         decisao.get("modelo"), int(decisao.get("entrada") or 0),
         int(decisao.get("saida") or 0), float(decisao.get("segundos") or 0),
         decisao.get("custo"), (decisao.get("erro") or "")[:500] or None))


def registros(con: Any, *, limite: int = 200, conversa_id: int | None = None) -> list[dict]:
    """O registro das respostas automáticas, mais novo primeiro. SÓ LÊ."""
    filtro, args = "", []
    if conversa_id is not None:
        filtro, args = "WHERE r.conversa_id=%s", [int(conversa_id)]
    linhas = banco(con).ler(
        f"""SELECT r.*, c.nome FROM wa_ia_registro r
              JOIN wa_conversa c ON c.id = r.conversa_id {filtro}
             ORDER BY r.id DESC LIMIT %s""", (*args, int(limite)))
    return [dict(r) for r in linhas]


def resumo_do_dia(con: Any, *, agora: str) -> dict:
    """Quantas respostas, passagens e quanto custou, hoje. SÓ LÊ."""
    dia = str(agora)[:10]
    linhas = banco(con).ler(
        """SELECT caso, enviado, custo_usd, segundos_audio FROM wa_ia_registro
            WHERE quando >= %s AND quando < %s""", (dia, dia + "z"))
    custos = [float(r["custo_usd"]) for r in linhas if r["custo_usd"] is not None]
    return {
        "respostas": sum(1 for r in linhas if r["enviado"]),
        "passagens": sum(1 for r in linhas if r["caso"] == CASO_PASSAGEM),
        "audios": sum(1 for r in linhas if r["caso"] == CASO_AUDIO),
        "minutos_audio": round(sum(float(r["segundos_audio"] or 0) for r in linhas) / 60, 1),
        "custo_usd": round(sum(custos), 4),
        "sem_custo": sum(1 for r in linhas if r["custo_usd"] is None
                         and (r["caso"] == CASO_AUDIO or r["caso"] in
                              (CASO_DUVIDA, CASO_VALOR))),
    }


# ------------------------------------------------------------- a rodada


def _janela(cfg: dict, agora: str) -> str:
    """Desde quando se responde: o maior entre «ligado em» e 24 h atrás."""
    inicio = ((FILA._dt(agora) or datetime.now()) - timedelta(hours=JANELA_HORAS)
              ).strftime("%Y-%m-%dT%H:%M:%S")
    return max(inicio, cfg.get("ia_ligada_em") or "")


def transcrever_pendentes(db: Any, cfg: dict, *, agora: str, pasta_de_dados: Any,
                          limite: int = CONVERSAS_POR_RODADA,
                          https: Callable | None = None,
                          transcrever: Callable | None = None) -> int:
    """Baixa e transcreve os áudios das últimas 24 h. **FALA COM A REDE**, fora
    de transação. A mensagem é marcada antes (transcrição "" = pega), e por
    isso duas rodadas não transcrevem o mesmo áudio.

    O TETO DO DIA SE CONFERE ANTES DE CADA ÁUDIO (26/10/2026, revisão de
    segurança, ALTA). O catálogo declarava `wa_audio` com 200 por dia e nada o
    aplicava: com a transcrição ligada e a rodada em laço, qualquer número de
    WhatsApp mandava áudios à vontade, e cada um era um download na Graph e
    um POST pago à OpenAI. Agora `ia_uso.passou_do_teto` é perguntado antes de
    pegar cada mensagem — uma rodada de 20 pode cruzar o teto no meio. Passado
    o teto, o áudio não é pego nem baixado: a mensagem segue sem transcrição
    (vai para uma pessoa, como o áudio com a transcrição desligada), e o
    motivo vai ao log."""
    if not cfg["audio_ligado"]:
        return 0
    inicio = ((FILA._dt(agora) or datetime.now()) - timedelta(hours=JANELA_HORAS)
              ).strftime("%Y-%m-%dT%H:%M:%S")
    with db.connect() as con:
        candidatos = banco(con).ler(
            """SELECT m.id, m.midia_id, c.id AS conversa_id, c.wa_id
                 FROM wa_mensagem m JOIN wa_conversa c ON c.id = m.conversa_id
                WHERE m.direcao='in' AND m.tipo='audio' AND m.transcricao IS NULL
                  AND m.midia_id IS NOT NULL AND m.criado_em >= %s
                ORDER BY m.id LIMIT %s""", (inicio, int(limite)))
        token = BALCAO.ler_config(con, WA.CHAVE_TOKEN)
    feitos = 0
    fn = transcrever or TRANSC.transcrever
    for m in candidatos:
        with db.connect() as con:
            teto = USO.passou_do_teto(con, FINALIDADE_AUDIO, agora=agora)
        if teto:
            LOG.warning("ÁUDIOS DO WHATSAPP SEM TRANSCRIÇÃO NESTA RODADA: %s", teto)
            break
        with db.transaction() as con:
            pegou = banco(con).escrever(
                "UPDATE wa_mensagem SET transcricao='' WHERE id=%s "
                "AND transcricao IS NULL RETURNING id", (int(m["id"]),))
        if not pegou:
            continue
        conversa = {"id": m["conversa_id"], "wa_id": m["wa_id"]}
        decisao = {"caso": CASO_AUDIO, "lido": f"áudio da mensagem {m['id']}",
                   "provedor": TRANSC.PROVEDOR, "modelo": cfg["audio_modelo"]}
        texto = ""
        try:
            audio, mime = TRANSC.baixar_audio(token, m["midia_id"], https=https)
            r = fn(pasta_de_dados, audio, mime, modelo=cfg["audio_modelo"],
                   preco_por_minuto=cfg["audio_preco_minuto"],
                   # literal, e não FINALIDADE_AUDIO: o varredor do catálogo
                   # (`test_ia_uso`) lê a finalidade escrita na chamada
                   modulo="wa_atendente", finalidade="wa_audio",
                   usuario=AUTOR_IA, referencia=f"wa_mensagem:{m['id']}",
                   https=https)
            texto = r["texto"]
            decisao.update(segundos=r["segundos"], custo=r["custo_usd"],
                           modelo=r["modelo"])
        except TRANSC.TranscricaoErro as falha:
            decisao["erro"] = str(falha)
        with db.transaction() as con:
            if texto:
                banco(con).escrever(
                    "UPDATE wa_mensagem SET transcricao=%s WHERE id=%s",
                    (texto, int(m["id"])))
            _registrar(con, conversa, decisao, enviado=False, meta_id=None,
                       agora=agora,
                       respondido="(transcrição gravada na mensagem)" if texto else "")
        feitos += 1
    return feitos


def _soltar_presas(db: Any, *, agora: str) -> None:
    limite = ((FILA._dt(agora) or datetime.now()) - timedelta(minutes=PRESO_MINUTOS)
              ).strftime("%Y-%m-%dT%H:%M:%S")
    with db.transaction() as con:
        banco(con).escrever(
            "UPDATE wa_mensagem SET ia_situacao=%s WHERE ia_situacao=%s "
            "AND ia_desde < %s", (WA.IA_ERRO, WA.IA_PROCESSANDO, limite))


def atender_conversa(db: Any, conversa_id: int, cfg: dict, *, agora: str,
                     pasta_de_dados: Any, conversar: Callable | None = None,
                     http_post: Callable | None = None) -> dict | None:
    """Pega as mensagens novas da conversa, decide, envia e registra.

    Três tempos, e só o do meio fala com a rede: (1) transação curta que marca
    as mensagens como «processando» — é a trava contra duas rodadas responderem
    a mesma pergunta; (2) a decisão e o envio, sem transação; (3) transação
    curta que grava o que saiu, a passagem e o registro."""
    desde = _janela(cfg, agora)
    with db.transaction() as con:
        bd = banco(con)
        conversa = bd.um("SELECT * FROM wa_conversa WHERE id=%s", (int(conversa_id),))
        if not conversa:
            return None
        pegas = bd.escrever(
            """UPDATE wa_mensagem SET ia_situacao=%s, ia_desde=%s
                WHERE conversa_id=%s AND direcao='in' AND ia_situacao IS NULL
                  AND criado_em >= %s
            RETURNING id, texto, tipo, transcricao""",
            (WA.IA_PROCESSANDO, agora, int(conversa_id), desde))
        if not pegas:
            return None
        ids = [int(p["id"]) for p in pegas]
        if (conversa.get("modo") or WA.MODO_IA) == WA.MODO_PESSOA:
            bd.escrever("UPDATE wa_mensagem SET ia_situacao=%s WHERE id = ANY(%s)",
                        (WA.IA_FORA, ids))
            return {"caso": "com_pessoa", "conversa_id": conversa_id}
    conversa = dict(conversa)
    partes = []
    for p in sorted(pegas, key=lambda x: int(x["id"])):
        t = (p.get("texto") or "").strip()
        if (p.get("tipo") or "") == "audio":
            t = (p.get("transcricao") or "").strip() or t
        if t:
            partes.append(t)
    texto = "\n".join(partes)
    decisao = decidir(db, conversa, texto, cfg, agora=agora,
                      pasta_de_dados=pasta_de_dados, conversar=conversar)

    enviar = decisao["resposta"]
    if not enviar and decisao.get("passar") and cfg["aviso_passagem"]:
        enviar = TEXTO_PASSAGEM.format(setor=FILA.nome_do_setor(decisao["passar"]))
    meta_id, enviado, texto_saida = None, False, ""
    if enviar:
        texto_saida = enviar + RODAPE
        try:
            with db.connect() as con:
                pedido = BALCAO.montar_envio(con, conversa["wa_id"], texto_saida)
            meta_id = BALCAO.postar_envio(pedido, http_post)
            enviado = True
        except BALCAO.EnvioErro as falha:
            decisao["erro"] = str(falha)[:300]
            if not decisao.get("passar"):
                decisao.update(caso=CASO_PASSAGEM,
                               passar=FILA.setor_valido(conversa.get("setor"))
                               or WA.SETOR_PADRAO,
                               motivo="a resposta automática não saiu")
    situacao = (WA.IA_PASSADA if decisao.get("passar") else WA.IA_RESPONDIDA)
    with db.transaction() as con:
        if enviado:
            BALCAO.gravar_saida(con, conversa_id, texto_saida, meta_id,
                                autor=AUTOR_IA, agora=agora)
        if decisao.get("passar"):
            FILA.passar_para_pessoa(con, conversa_id, setor=decisao["passar"],
                                    motivo=decisao.get("motivo") or "",
                                    por="atendente com IA", quando=agora)
        banco(con).escrever(
            "UPDATE wa_mensagem SET ia_situacao=%s WHERE id = ANY(%s)",
            (situacao, ids))
        _registrar(con, conversa, decisao, enviado=enviado, meta_id=meta_id,
                   agora=agora, respondido=texto_saida)
    try:
        # quem age é o atendente, a mando de quem responde pelas rotinas (PR #36)
        db.log(None, None, "WA_IA_RESPOSTA", "wa_conversa", int(conversa_id),
               {"caso": decisao["caso"], "enviado": enviado,
                "passou_para": decisao.get("passar")},
               agente="atendente com IA do WhatsApp", a_mando_de=IDR.PELO_RESPONSAVEL)
    except Exception:                                   # noqa: BLE001
        LOG.exception("a resposta automática foi gravada, e a auditoria falhou")
    return {"caso": decisao["caso"], "enviado": enviado,
            "passou_para": decisao.get("passar"), "conversa_id": conversa_id}


def rodada(db: Any, *, agora: str | None = None, pasta_de_dados: Any = None,
           limite: int = CONVERSAS_POR_RODADA, conversar: Callable | None = None,
           http_post: Callable | None = None, https: Callable | None = None,
           transcrever: Callable | None = None) -> dict:
    """Uma passada do atendente: transcreve os áudios e responde as conversas.
    **FALA COM A REDE**, e nunca de dentro de uma transação."""
    quando = agora or db.now()
    pasta = pasta_de_dados or Path(db.db_path).parent
    with db.connect() as con:
        cfg = configuracao(con)
    if not (cfg["ia_ligada"] or cfg["audio_ligado"]):
        return {"ok": True, "desligado": True, "audios": 0, "conversas": []}
    _soltar_presas(db, agora=quando)
    audios = transcrever_pendentes(db, cfg, agora=quando, pasta_de_dados=pasta,
                                   limite=limite, https=https,
                                   transcrever=transcrever)
    feitas = []
    if cfg["ia_ligada"]:
        with db.connect() as con:
            cids = [int(r["conversa_id"]) for r in banco(con).ler(
                """SELECT conversa_id, min(id) AS primeira FROM wa_mensagem
                    WHERE direcao='in' AND ia_situacao IS NULL AND criado_em >= %s
                    GROUP BY conversa_id ORDER BY primeira LIMIT %s""",
                (_janela(cfg, quando), int(limite)))]
        for cid in cids:
            try:
                r = atender_conversa(db, cid, cfg, agora=quando, pasta_de_dados=pasta,
                                     conversar=conversar, http_post=http_post)
            except Exception:                           # noqa: BLE001
                LOG.exception("o atendente falhou na conversa %s", cid)
                r = {"caso": "erro", "conversa_id": cid}
            if r:
                feitas.append(r)
    return {"ok": True, "desligado": False, "audios": audios, "conversas": feitas}


# ------------------------------------------------------------- fora do Flask


def main(argv=None) -> int:
    """`python wa_atendente.py --pasta-dados <pasta> [--laco 60]`.

    Puxa a caixa-postal e roda o atendente. Com `--laco`, repete a cada N
    segundos. A tarefa do Agendador que chamaria isto NÃO é instalada por este
    código: ligar o atendente fora do horário de alguém olhando é decisão do
    oficial (ver o PR)."""
    p = argparse.ArgumentParser(description="Atendente com IA do WhatsApp.")
    p.add_argument("--pasta-dados", required=True)
    p.add_argument("--laco", type=int, default=0,
                   help="segundos entre rodadas (0 = uma rodada só)")
    a = p.parse_args(argv)
    from database import Database
    import wa_puxar as PUXAR
    pasta = Path(a.pasta_dados)
    db = Database(pasta / "cartorio_gestao.sqlite3")
    while True:
        with db.connect() as con:
            achado = PUXAR.buscar_pendentes(con)
        if achado.get("ok"):
            with db.transaction() as con:
                aplicado = PUXAR.aplicar_itens(con, achado["itens"], agora=db.now())
            with db.connect() as con:          # o ack depois de aplicar, fora da transação
                PUXAR.confirmar(con, aplicado.get("ids"))
        r = rodada(db, pasta_de_dados=pasta)
        print(json.dumps({"puxar": {k: v for k, v in achado.items() if k != "itens"},
                          "atendente": r}, ensure_ascii=False))
        if a.laco <= 0:
            return 0
        time.sleep(max(15, a.laco))


if __name__ == "__main__":
    sys.exit(main())
