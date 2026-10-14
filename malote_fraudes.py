"""Do malote para a lista de atenção para fraudes — 13/10/2026.

    «nosso sistema tem um local para registrar essas comunicações de fraudes e
     alertar caso apareçam no nosso cartório?» … «siga a proposta, guarde a
     referência de onde veio o aviso de fraude.» — o oficial, 13/10/2026

O QUE SE MEDIU
    A lista de atenção (`fraude.py`, `fr_alertas`) existia desde 26/08/2026 e
    estava com ZERO alertas na produção, enquanto o malote trouxe 17 assuntos
    sobre fraude, golpe ou falsificação desde julho (36 PDFs com os anexos). O
    aviso chegava, era lido, e não ficava em lugar nenhum que o balcão visse.

O QUE ESTE MÓDULO FAZ
    1. Guarda a PROPOSTA: cada pessoa que a comunicação liga à fraude, com o
       papel (vítima, envolvido, nome em documento fraudado), a frase de onde
       saiu e a REFERÊNCIA COMPLETA do aviso — o código do malote, o documento,
       o remetente, a data de envio, os processos citados e o arquivo. Tabela
       própria, `mt_alertas_propostos`; nada entra na lista ainda.
    2. Depois da revisão do oficial, APLICA: cada proposta aprovada vira um
       alerta pela função da casa (`fraude.incluir`), com a referência em
       `origem`, `origem_data`, `origem_orgao` e `observacao`. É a mesma porta
       da tela de fraudes — duas portas divergiriam no primeiro conserto.

QUEM DECIDE QUEM ENTRA
    O oficial. Quem leu os PDFs e propôs foi um agente; homônimo é a regra e o
    papel errado faz o alerta dizer o contrário do certo (a vítima tratada como
    envolvida). Por isso propor e aplicar são dois passos, e aplicar exige a
    situação APROVADO, que só o revisor marca.

    MUDOU EM 13/10/2026, POR ORDEM DELE, PARA O QUE CHEGA DE AGORA EM DIANTE:
    o aviso novo é lido pela IA interna e as pessoas entram DIRETO
    (`tratar_grupo`, chamado pelo agente do malote), sem expediente e sem
    tarefa. A revisão continua dele, só que depois: na tela de fraudes, onde
    inativar exige motivo. A proposta fica gravada do mesmo jeito, com
    `revisado_por` dizendo que foi a IA — a procedência não se perde.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

QUEM = "AGENTE MALOTE"
PAPEIS = ("VITIMA", "ENVOLVIDO", "DOCUMENTO")
SITUACOES = ("PROPOSTO", "APROVADO", "DESCARTADO", "APLICADO")

SCHEMA = """
CREATE TABLE IF NOT EXISTS mt_alertas_propostos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    documento TEXT,
    papel TEXT NOT NULL,
    trecho TEXT,                 -- a frase do documento que justifica
    -- A REFERÊNCIA DO AVISO, inteira (pedido do oficial, 13/10/2026)
    codigo_malote TEXT,
    documento_malote TEXT,       -- o nome do PDF no malote
    assunto TEXT,
    remetente TEXT,
    enviado_em TEXT,
    processos TEXT,              -- os números de processo citados, separados por «; »
    arquivo TEXT,                -- onde o PDF está guardado nesta casa
    resumo TEXT,                 -- o que a comunicação diz
    situacao TEXT NOT NULL DEFAULT 'PROPOSTO',
    revisado_por TEXT,
    revisado_em TEXT,
    motivo TEXT,                 -- por que se descartou, quando se descartou
    alerta_id INTEGER,           -- fr_alertas.id, depois de aplicada
    criado_em TEXT NOT NULL,
    UNIQUE (codigo_malote, nome, documento, papel)
);
"""


class PropostaError(ValueError):
    """Recusa de regra, com a frase pronta."""


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def referencia(p: dict) -> dict:
    """Os quatro campos de procedência do alerta, montados da proposta.

    `origem` diz de onde veio, e é o que se lê primeiro no balcão: o código do
    malote vem antes de tudo porque é o que acha o documento de novo."""
    partes = [f"Malote Digital nº {p['codigo_malote']}" if p.get("codigo_malote") else "Malote Digital"]
    if p.get("documento_malote"):
        partes.append(f"documento «{p['documento_malote']}»")
    if p.get("processos"):
        partes.append(f"processo(s) {p['processos']}")
    origem = " — ".join(partes)
    obs = []
    if p.get("assunto"):
        obs.append(f"Assunto: {p['assunto']}")
    if p.get("resumo"):
        obs.append(f"Resumo: {p['resumo']}")
    if p.get("trecho"):
        obs.append(f"Trecho: «{p['trecho']}»")
    if p.get("arquivo"):
        obs.append(f"Arquivo nesta casa: {p['arquivo']}")
    return {"origem": origem[:500],
            "origem_data": (p.get("enviado_em") or "")[:10] or None,
            "origem_orgao": p.get("remetente"),
            "observacao": "\n".join(obs)}


def carregar(con: sqlite3.Connection, propostas: list[dict], agora: str | None = None) -> dict:
    """Grava as propostas (situação PROPOSTO). A mesma pessoa do mesmo aviso
    não entra duas vezes (UNIQUE). Não toca na lista de fraudes."""
    init_schema(con)
    agora = agora or datetime.now().isoformat(timespec="seconds")
    novas = repetidas = 0
    for p in propostas:
        # SEM DOCUMENTO GRAVA-SE VAZIO, e não NULL: no SQLite dois NULL não se
        # repetem para o UNIQUE, e a mesma pessoa do mesmo aviso entraria duas
        # vezes (achado pelo teste em 13/10/2026).
        p = dict(p)
        p["nome"] = " ".join(str(p.get("nome") or "").split())
        p["documento"] = "".join(ch for ch in str(p.get("documento") or "") if ch.isdigit())
        if p.get("papel") not in PAPEIS:
            raise PropostaError(f"Papel desconhecido em «{p.get('nome')}»: {p.get('papel')!r}.")
        if not (p.get("nome") or p.get("documento")):
            raise PropostaError("Proposta sem nome nem documento.")
        cur = con.execute(
            """INSERT OR IGNORE INTO mt_alertas_propostos (nome, documento, papel, trecho,
                   codigo_malote, documento_malote, assunto, remetente, enviado_em, processos,
                   arquivo, resumo, situacao, criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'PROPOSTO', ?)""",
            (p.get("nome"), p.get("documento"), p["papel"], p.get("trecho"), p.get("codigo_malote"),
             p.get("documento_malote"), p.get("assunto"), p.get("remetente"), p.get("enviado_em"),
             p.get("processos"), p.get("arquivo"), p.get("resumo"), agora))
        if cur.rowcount:
            novas += 1
        else:
            repetidas += 1
    con.commit()
    return {"novas": novas, "repetidas": repetidas}


def revisar(con: sqlite3.Connection, ids: list[int], *, aprovar: bool, revisor: str,
            motivo: str | None = None, agora: str | None = None) -> int:
    """Marca APROVADO ou DESCARTADO. Descartar exige motivo escrito."""
    if not aprovar and not (motivo or "").strip():
        raise PropostaError("Descartar exige o motivo escrito.")
    agora = agora or datetime.now().isoformat(timespec="seconds")
    n = 0
    for i in ids:
        cur = con.execute(
            """UPDATE mt_alertas_propostos SET situacao=?, revisado_por=?, revisado_em=?, motivo=?
                WHERE id=? AND situacao IN ('PROPOSTO','APROVADO','DESCARTADO')""",
            ("APROVADO" if aprovar else "DESCARTADO", revisor, agora,
             None if aprovar else motivo.strip(), i))
        n += cur.rowcount
    con.commit()
    return n


def _aplicar_uma(con: sqlite3.Connection, p: dict, *, usuario: str, agora: str) -> tuple[int, bool]:
    """Uma proposta na lista, DENTRO da transação de quem chama. Devolve o id do
    alerta e se ele é novo. O mesmo aviso, a mesma pessoa e o mesmo papel não
    viram dois alertas."""
    import fraude
    from pt_schema import normalizar_nome
    ref = referencia(p)
    existente = con.execute(
        """SELECT id FROM fr_alertas WHERE situacao='ATIVO' AND origem=? AND papel=?
             AND ((? <> '' AND documento=?) OR (? <> '' AND nome_norm=?))""",
        (ref["origem"], p["papel"], p.get("documento") or "", p.get("documento") or "",
         normalizar_nome(p.get("nome")) or "", normalizar_nome(p.get("nome")) or "")).fetchone()
    if existente:
        alerta_id, novo = int(existente[0]), False
    else:
        alerta_id = fraude.incluir(con, papel=p["papel"], origem=ref["origem"], agora=agora,
                                   nome=p.get("nome") or None, documento=p.get("documento") or None,
                                   origem_data=ref["origem_data"], origem_orgao=ref["origem_orgao"],
                                   observacao=ref["observacao"], usuario=usuario)["alerta_id"]
        novo = True
    con.execute("UPDATE mt_alertas_propostos SET situacao='APLICADO', alerta_id=? WHERE id=?",
                (alerta_id, p["id"]))
    return alerta_id, novo


def aplicar(con: sqlite3.Connection, *, usuario: str, agora: str | None = None) -> dict:
    """Leva as APROVADAS à lista de fraudes, pela função da casa. Alerta já
    existente da mesma pessoa e do mesmo aviso não se repete."""
    agora = agora or datetime.now().isoformat(timespec="seconds")
    feitos, ja_havia = [], []
    con.row_factory = sqlite3.Row
    aprovadas = [dict(r) for r in con.execute(
        "SELECT * FROM mt_alertas_propostos WHERE situacao='APROVADO' ORDER BY id")]
    try:
        con.execute("BEGIN IMMEDIATE")
        for p in aprovadas:
            alerta_id, novo = _aplicar_uma(con, p, usuario=usuario, agora=agora)
            (feitos if novo else ja_havia).append(alerta_id)
        con.execute(
            """INSERT INTO audit_logs (ts, user_id, username_snapshot, action, entity_type, details)
               VALUES (?, NULL, ?, 'FRAUDE_ALERTAS_DO_MALOTE', 'FR_ALERTAS', ?)""",
            (agora, QUEM, json.dumps({"incluidos": feitos, "ja_havia": ja_havia, "em_nome_de": usuario})))
        con.commit()
    except Exception:
        con.rollback()
        raise
    return {"incluidos": len(feitos), "ja_havia": len(ja_havia)}


# ============================================================ PELA IA INTERNA
#
#     «quando for fraude, apenas cadastrar em fraudes, sem tarefa» … «nem
#      tarefa, nem expediente» … «pode ser a ia interna» … «gostei, pode
#      seguir» — o oficial, 13/10/2026
#
# O CAMINHO DO AVISO DE FRAUDE É OUTRO: o documento do malote que comunica
# fraude não vira expediente nem tarefa. A IA interna (a mesma da triagem do
# malote, `agente_provedores`, com a mesma máscara na ida) lê o aviso e diz quem
# são as pessoas; elas entram DIRETO na lista de fraudes, com a referência
# inteira — a revisão do oficial passa a ser DEPOIS, na tela de fraudes, onde
# inativar um alerta exige motivo e não apaga nada.
#
# A RÉGUA DE QUEM ENTRA É A QUE ELE APLICOU AO VER A PRIMEIRA LISTA (13/10):
# «mantenha todos que participaram dos documentos fraudados» e «vamos tirar
# bradesco e santander» — todo mundo do documento fraudado, menos banco. Banco
# sai também por código, e não só pela instrução: instrução é pedido, filtro é
# garantia.
#
# TRÊS SAÍDAS, e nenhuma some com o arquivo:
#   - aviso com pessoas → lista de fraudes, PDF guardado em
#     `arquivos/malote/fraudes/<código>`, nenhum expediente;
#   - não é aviso, ou é aviso sem pessoa (orientação geral) → expediente normal;
#   - a IA não respondeu (sem chave, rede, resposta torta) → FICA NA PASTA, e o
#     verificador interno acusa MALOTE_PARADO no dia útil seguinte. Cadastrar
#     como expediente seria contrariar a ordem; descartar seria perder o aviso.

#: O que faz o documento ir à IA de fraude. É PORTA, e não juízo: quem decide
#   se é aviso de fraude é a leitura. Medido nos 17 assuntos de 13/10/2026: todos
#   têm uma destas raízes no assunto ou no texto. Sem nenhuma, a IA nem é chamada
#   — o expediente segue o caminho de sempre, e a conta não sobe por circular.
PALAVRAS_DE_FRAUDE = re.compile(
    r"fraud|golpe|falsifica|falsidade|falsos?\b|falsas?\b|estelionat|contrafe|inid[oô]ne",
    re.I)
#: Banco e instituição financeira não entram (ordem de 13/10/2026).
_E_BANCO = re.compile(
    r"\b(banco|bank|bradesco|santander|ita[uú]|caixa econ[oô]mica|sicoob|sicredi|nubank|"
    r"cooperativa de cr[eé]dito|financeira|cr[eé]dito,? financiamento)\b", re.I)
_MARCA = re.compile(r"\[[A-Z_]+_\d+\]|\b[A-Z]+_\d{2}\b")

PROVEDORES_DA_IA = ("claude",)
LIMITE_DO_TEXTO = 18000
MAXIMO_DE_SAIDA = 3000
TETO_POR_RODADA = 20
REVISOR_DA_IA = "IA interna — ordem do oficial de 13/10/2026 (entra direto; revisão na tela de fraudes)"

INSTRUCAO_FRAUDE = """Você lê documentos recebidos pelo Malote Digital por uma \
serventia extrajudicial (cartório) no Maranhão e reconhece os AVISOS DE FRAUDE: \
ofício, circular, decisão ou comunicação que relata um caso concreto de fraude, \
golpe, falsificação de documento, de assinatura, de selo ou de ato notarial ou \
registral, para que as serventias fiquem atentas. Nomes e documentos de pessoas \
vêm com os nomes por extenso; CPF, CNPJ, telefone e e-mail vêm mascarados como \
marcas ([CPF_01], [CNPJ_01]…) — no campo "documento", devolva a marca exatamente \
como veio.

Responda SÓ com um objeto JSON, sem texto em volta:
{
  "aviso_de_fraude": true | false,
  "resumo": "até 400 caracteres: quem comunica, o que aconteceu e onde",
  "processos": ["números de processo, SEI, ofício ou boletim de ocorrência citados"],
  "pessoas": [
    {"nome": "nome completo, como está no texto", "documento": "marca do CPF/CNPJ, ou vazio",
     "papel": "VITIMA" | "ENVOLVIDO" | "DOCUMENTO",
     "trecho": "a frase do texto que liga a pessoa ao caso, até 200 caracteres"}
  ]
}

Regras:
- aviso_de_fraude=false quando o documento não relata caso concreto (orientação \
geral, provimento, curso, estatística). Nesse caso "pessoas" fica vazio.
- VITIMA: quem teve o nome, o documento, a assinatura ou o bem usado no golpe — \
inclusive o tabelião ou escrevente cuja assinatura, etiqueta ou selo foi falsificado.
- ENVOLVIDO: quem praticou ou tentou praticar a fraude, ou é investigado por ela.
- DOCUMENTO: quem figura no documento fraudado (outorgante, outorgado, vendedor, \
comprador, inventariante, filiação, proprietário) sem que o texto diga se é \
vítima ou autor.
- Inclua TODAS as pessoas que participaram dos documentos fraudados.
- NÃO inclua: bancos e instituições financeiras; a autoridade que assina ou \
encaminha a comunicação (juiz, corregedor, coordenador, delegado, servidor do \
tribunal); advogado que só representa a vítima; a serventia ou o órgão público \
como instituição.
- Cada pessoa uma vez, cada uma no seu item (nunca duas pessoas no mesmo "nome"). \
Não invente: documento que o texto não traz fica vazio."""

#: Abaixo disto o PDF é imagem digitalizada, e a IA interna (que lê texto) não
#   tem o que ler. Medido no ensaio de 13/10/2026: o ofício do aviso 81020265824993
#   deu 61 caracteres, e a IA devolveu «FRAUDE» e «PÚBLICA» como pessoas.
MINIMO_DE_LETRAS = 200
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")


def mascarar_numeros(texto: str) -> tuple[str, dict[str, str]]:
    """A máscara DOS NÚMEROS, e não dos nomes — e a razão está medida.

    No ensaio de 13/10/2026 a máscara inteira (`gestor_expedientes.mascarar`,
    a da triagem) estragou o que este caminho existe para fazer: juntou
    «vendedor Maicom Manica e como outorgado comprador Walter da Silva Campos»
    numa marca só, e num aviso de Santa Catarina a IA não achou ninguém. Tirar
    nome de pessoa de um texto em que todo nome virou marca não funciona.

    O PRECEDENTE É DELE: na leitura dos documentos do Registro Civil (12/10/2026)
    decidiu «documentos vão para claude sem máscara». Aqui vai menos que lá: o
    nome sai por extenso, e CPF, CNPJ, telefone, e-mail, IP e segredo continuam
    mascarados — e a conferência de resíduo continua barrando o envio se sobrar
    um."""
    from ajuda_privacidade import (_CPF, _EMAIL, _IP, _SEGREDO, _TELEFONE,
                                   _conferir_residuos, _Sanitizador)
    s = _Sanitizador()
    originais: dict[str, str] = {}
    marcar = s.marcador

    def marcador(tipo, valor):
        m = marcar(tipo, valor)
        originais.setdefault(m, str(valor))
        return m
    s.marcador = marcador
    seguro = str(texto or "")
    for tipo, padrao in (("SEGREDO", _SEGREDO), ("EMAIL", _EMAIL), ("CNPJ", _CNPJ), ("CPF", _CPF),
                         ("TELEFONE", _TELEFONE), ("IP", _IP)):
        seguro = s.simples(seguro, tipo, padrao)
    _conferir_residuos(seguro)
    return seguro, originais


def letras_do_texto(texto: str) -> int:
    """As letras que o PDF deu, fora as linhas que o próprio leitor escreve."""
    sem_cabecalho = re.sub(r"(?m)^--- arquivo:.*$|\[arquivo [^\]]*\]", "", texto or "")
    return len(re.findall(r"[^\W\d_]", sem_cabecalho))

SCHEMA_LEITURAS = """
CREATE TABLE IF NOT EXISTS mt_fraude_leituras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grupo TEXT NOT NULL,             -- o arquivo ou a subpasta do malote
    codigo_malote TEXT,
    hash_texto TEXT NOT NULL,
    lido_em TEXT NOT NULL,
    provedor TEXT,
    modelo TEXT,
    tokens_entrada INTEGER,
    tokens_saida INTEGER,
    resultado_json TEXT,
    erro TEXT
);
"""


def init_schema_ia(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA + SCHEMA_LEITURAS)


def texto_dos_arquivos(arquivos, limite: int = LIMITE_DO_TEXTO) -> str:
    """O texto dos PDFs, na ordem do grupo — a mesma leitura da triagem do
    malote (`gestor_expedientes.texto_dos_anexos`), mas dos arquivos da pasta,
    porque aqui o expediente não existe e não vai existir."""
    import logging
    partes = []
    for p in arquivos:
        p = Path(p)
        if p.suffix.lower() != ".pdf":
            partes.append(f"[arquivo {p.name}: não é PDF, não lido]")
            continue
        try:
            from pypdf import PdfReader
            logging.getLogger("pypdf").setLevel(logging.ERROR)
            texto = " ".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages[:8])
        except Exception as erro:                       # noqa: BLE001 — vai ao texto
            partes.append(f"[arquivo {p.name}: não abriu ({type(erro).__name__})]")
            continue
        partes.append(f"--- arquivo: {p.name}\n{' '.join(texto.split())}")
    return "\n".join(partes)[:limite]


def parece_fraude(*textos: str) -> bool:
    return any(PALAVRAS_DE_FRAUDE.search(t or "") for t in textos)


def _ler_json(texto: str) -> dict:
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        raise ValueError("a resposta não trouxe JSON")
    d = json.loads(m.group(0))
    if not isinstance(d.get("aviso_de_fraude"), bool):
        raise ValueError("a resposta não disse se é aviso de fraude")
    if not isinstance(d.get("pessoas") or [], list):
        raise ValueError("«pessoas» não veio como lista")
    return d


def pessoas_validas(pessoas: list) -> tuple[list[dict], list[str]]:
    """O que a IA devolveu, já desmascarado, passado pela régua da casa. Devolve
    as que entram e a frase de cada uma que ficou de fora — fora não é sumido."""
    from cpf_cnpj import cnpj_valido, cpf_valido
    boas, fora, vistas = [], [], set()
    for p in pessoas or []:
        if not isinstance(p, dict):
            continue
        nome = " ".join(str(p.get("nome") or "").split())
        doc = "".join(ch for ch in str(p.get("documento") or "") if ch.isdigit())
        papel = str(p.get("papel") or "").upper().strip()
        if _MARCA.search(nome):
            fora.append(f"«{nome}»: a marca não voltou a ser nome (a IA citou quem não estava no texto)")
            continue
        if _E_BANCO.search(nome):
            fora.append(f"«{nome}»: banco ou instituição financeira (ordem de 13/10/2026)")
            continue
        if papel not in PAPEIS:
            fora.append(f"«{nome}»: papel desconhecido {papel!r}")
            continue
        if doc and not ((len(doc) == 11 and cpf_valido(doc)) or (len(doc) == 14 and cnpj_valido(doc))):
            fora.append(f"«{nome}»: documento {doc} não confere — entrou só pelo nome")
            doc = ""
        if not (nome or doc):
            continue
        if len(nome.split()) < 2 and not doc:
            fora.append(f"«{nome}»: uma palavra só não identifica pessoa")
            continue
        chave = (nome.lower(), doc, papel)
        if chave in vistas:
            continue
        vistas.add(chave)
        boas.append({"nome": nome, "documento": doc, "papel": papel,
                     "trecho": " ".join(str(p.get("trecho") or "").split())[:300]})
    return boas, fora


def ler_aviso(pasta_dados: Path, texto: str, *, conversar=None, provedor: str | None = None) -> dict:
    """Pergunta à IA interna se é aviso de fraude e quem são as pessoas.
    FALA COM A REDE — nunca dentro de transação. Recusa (exceção) quando não há
    chave ou a resposta não serve; quem chama decide que o arquivo fica."""
    import agente_provedores as AP
    import gestor_expedientes as GE
    conversar = conversar or AP.conversar
    provedor = provedor or next((p for p in PROVEDORES_DA_IA if AP.tem_chave(pasta_dados, p)), None)
    if provedor is None:
        raise PropostaError("A IA interna está sem chave (agente.cred); o aviso fica na pasta.")
    seguro, originais = mascarar_numeros(texto)
    resposta = conversar(pasta_dados, provedor=provedor, sistema=INSTRUCAO_FRAUDE,
                         conversa=[{"tipo": "user", "texto": seguro}], ferramentas=[],
                         modelo=None, maximo_de_saida=MAXIMO_DE_SAIDA)
    r = GE.desmascarar(_ler_json(resposta.get("texto") or ""), originais)
    boas, fora = pessoas_validas(r.get("pessoas") or [])
    return {"aviso": bool(r["aviso_de_fraude"]), "resumo": str(r.get("resumo") or "")[:600],
            "processos": [str(x) for x in (r.get("processos") or []) if str(x).strip()],
            "pessoas": boas, "fora": fora, "provedor": provedor,
            "modelo": resposta.get("modelo"), "entrada": resposta.get("entrada"),
            "saida": resposta.get("saida")}


def _registrar_leitura(con, *, grupo: str, codigo, texto: str, agora: str, lida: dict | None = None,
                       erro: str | None = None, provedor: str | None = None) -> None:
    import hashlib
    con.execute(
        """INSERT INTO mt_fraude_leituras (grupo, codigo_malote, hash_texto, lido_em, provedor, modelo,
               tokens_entrada, tokens_saida, resultado_json, erro) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (grupo, codigo, hashlib.sha256(texto.encode("utf-8")).hexdigest(), agora,
         (lida or {}).get("provedor") or provedor, (lida or {}).get("modelo"),
         (lida or {}).get("entrada"), (lida or {}).get("saida"),
         json.dumps(lida, ensure_ascii=False, default=str) if lida else None, erro))
    con.commit()


def tratar_grupo(con: sqlite3.Connection, g, pasta_dados: Path, raiz_arquivos: Path, usuario: str, *,
                 conversar=None, agora: str | None = None, ler_texto=None) -> dict:
    """Um grupo do malote (`malote_agente.Grupo`) A_CADASTRAR. Devolve
    {"caminho": "EXPEDIENTE" | "FRAUDE" | "PENDENTE", ...}. Só ESCREVE no caminho
    FRAUDE (e a linha da leitura); EXPEDIENTE é para quem chama cadastrar."""
    from storage import copy_existing, safe_component
    import malote_agente as MA
    agora = agora or datetime.now().isoformat(timespec="seconds")
    init_schema_ia(con)
    capa = g.capa or {}
    texto = (ler_texto or texto_dos_arquivos)(g.arquivos)
    if not parece_fraude(capa.get("assunto") or "", g.nome, texto):
        return {"caminho": "EXPEDIENTE", "motivo": "nenhuma palavra de fraude", "leu": False}
    if letras_do_texto(texto) < MINIMO_DE_LETRAS:
        return {"caminho": "PENDENTE", "leu": False,
                "motivo": "parece aviso de fraude, mas o PDF não tem texto (é imagem digitalizada) e a IA "
                          "interna lê texto; fica na pasta — inclua as pessoas à mão na tela de fraudes"}
    cabeca = "\n".join([f"Assunto no malote: {capa.get('assunto') or '—'}",
                        f"Remetente: {capa.get('remetente') or '—'}",
                        f"Arquivo: {g.nome}", "", texto])
    try:
        lida = ler_aviso(pasta_dados, cabeca, conversar=conversar)
    except Exception as erro:                            # noqa: BLE001 — o arquivo fica
        frase = f"{type(erro).__name__}: {str(erro)[:300]}"
        _registrar_leitura(con, grupo=g.nome, codigo=capa.get("codigo"), texto=cabeca,
                           agora=agora, erro=frase)
        return {"caminho": "PENDENTE", "motivo": f"a IA interna não leu o aviso ({frase}); fica na pasta",
                "leu": True}
    _registrar_leitura(con, grupo=g.nome, codigo=capa.get("codigo"), texto=cabeca, agora=agora, lida=lida)
    if not lida["aviso"] or not lida["pessoas"]:
        # AVISO SEM NOME NO TEXTO: no ensaio de 13/10/2026 o aviso de Tubarão/SC
        # tinha as três pessoas só nas IMAGENS coladas no PDF (o BO e o contrato
        # fotografado); o texto não traz nenhuma. Vira expediente, como combinado,
        # e o expediente diz o porquê para quem for conferir.
        return {"caminho": "EXPEDIENTE", "motivo": (
                    "a IA leu: não é aviso de caso concreto" if not lida["aviso"] else
                    "a IA leu: é aviso de fraude, mas o texto não traz nome de pessoa (podem estar em "
                    "imagem dentro do PDF) — conferir e incluir à mão na tela de fraudes"),
                "fora": lida["fora"], "leu": True}

    # O CÓDIGO DOS ANEXOS VAI JUNTO (forma da lista de 13/10/2026): é por ele que
    # se acha o documento de novo no malote.
    codigos = [c for c in (x.get("codigo") for x in filter(None, map(MA.capa_do_pdf, g.arquivos)))
               if c and c != capa.get("codigo")]
    codigo = capa.get("codigo") or ""
    if codigo and codigos:
        codigo = f"{codigo} (e anexos {', '.join(dict.fromkeys(codigos))})"
    destino = Path(raiz_arquivos) / "malote" / "fraudes" / safe_component(capa.get("codigo") or g.nome)
    copiados: list[dict] = []
    try:
        for p in g.arquivos:
            copiados.append(copy_existing(p, destino))
        principal = next((c["stored_path"] for c in copiados
                          if capa.get("nome_original") and c["original_name"] == capa.get("nome_original")),
                         copiados[0]["stored_path"])
        base = {"codigo_malote": codigo or None, "documento_malote": capa.get("nome_original") or g.nome,
                "assunto": capa.get("assunto"), "remetente": capa.get("remetente"),
                "enviado_em": capa.get("enviado_em"), "processos": "; ".join(lida["processos"]) or None,
                "arquivo": principal, "resumo": lida["resumo"]}
        incluidos, ja_havia = [], []
        con.execute("BEGIN IMMEDIATE")
        for pessoa in lida["pessoas"]:
            p = dict(base, **pessoa)
            con.execute(
                """INSERT OR IGNORE INTO mt_alertas_propostos (nome, documento, papel, trecho,
                       codigo_malote, documento_malote, assunto, remetente, enviado_em, processos,
                       arquivo, resumo, situacao, revisado_por, revisado_em, criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'APROVADO', ?, ?, ?)""",
                (p["nome"], p["documento"], p["papel"], p["trecho"], p["codigo_malote"],
                 p["documento_malote"], p["assunto"], p["remetente"], p["enviado_em"], p["processos"],
                 p["arquivo"], p["resumo"], REVISOR_DA_IA, agora, agora))
            cur = con.cursor()
            cur.row_factory = sqlite3.Row
            linha = dict(cur.execute(
                """SELECT * FROM mt_alertas_propostos WHERE codigo_malote IS ? AND nome=? AND documento=?
                     AND papel=?""", (p["codigo_malote"], p["nome"], p["documento"], p["papel"])).fetchone())
            alerta_id, novo = _aplicar_uma(con, linha, usuario=usuario, agora=agora)
            (incluidos if novo else ja_havia).append({"alerta_id": alerta_id, "nome": p["nome"],
                                                      "papel": p["papel"]})
        nota = (f"aviso de fraude: {len(incluidos)} pessoa(s) na lista de fraudes"
                + (f", {len(ja_havia)} já estavam" if ja_havia else "")
                + f"; sem expediente (ordem de 13/10/2026). PDF em {destino}")
        for c, p in zip(copiados, g.arquivos):
            con.execute("""INSERT OR REPLACE INTO mt_arquivos (sha256, caminho, visto_em, situacao,
                               expediente_id, nota) VALUES (?,?,?, 'FRAUDE', NULL, ?)""",
                        (c["sha256"], str(p), agora, nota))
        con.execute(
            """INSERT INTO audit_logs (ts, user_id, username_snapshot, action, entity_type, details)
               VALUES (?, NULL, ?, 'FRAUDE_ALERTAS_DO_MALOTE', 'FR_ALERTAS', ?)""",
            (agora, QUEM, json.dumps({"caminho": "IA interna", "grupo": g.nome, "codigo": codigo,
                                      "incluidos": [x["alerta_id"] for x in incluidos],
                                      "ja_havia": [x["alerta_id"] for x in ja_havia],
                                      "fora": lida["fora"], "em_nome_de": usuario}, ensure_ascii=False)))
        con.commit()
    except Exception:
        con.rollback()
        for c in copiados:                     # cópia sem alerta não fica
            try:
                Path(c["stored_path"]).unlink()
            except OSError:
                pass
        raise
    return {"caminho": "FRAUDE", "leu": True, "nota": nota, "incluidos": incluidos, "ja_havia": ja_havia,
            "fora": lida["fora"], "resumo": lida["resumo"], "codigo": codigo, "pasta": str(destino)}


_ROTULO = {"VITIMA": "vítima", "ENVOLVIDO": "envolvido(a)", "DOCUMENTO": "nome em documento fraudado"}


def pagina_de_revisao(propostas: list[dict], titulo: str = "Alertas de fraude vindos do malote") -> str:
    """A página que o oficial lê para aprovar: por aviso, as pessoas, o papel,
    a frase de onde saiu e a referência que vai junto do alerta."""
    e = html.escape
    por_aviso: dict[str, list[dict]] = {}
    for p in propostas:
        por_aviso.setdefault(p.get("codigo_malote") or p.get("documento_malote") or "?", []).append(p)
    blocos = []
    for codigo, itens in por_aviso.items():
        p0 = itens[0]
        ref = referencia(p0)
        linhas = "".join(
            f"<tr><td>{e(str(p.get('id', '')))}</td><td><b>{e(p.get('nome') or '—')}</b></td>"
            f"<td>{e(p.get('documento') or '—')}</td><td>{e(_ROTULO.get(p['papel'], p['papel']))}</td>"
            f"<td><i>«{e(p.get('trecho') or '')}»</i></td></tr>" for p in itens)
        blocos.append(
            f"<section><h2>{e(p0.get('assunto') or p0.get('documento_malote') or codigo)}</h2>"
            f"<p class=ref><b>Referência que vai no alerta:</b> {e(ref['origem'])}<br>"
            f"<b>Remetente:</b> {e(p0.get('remetente') or '—')} · <b>Enviado em:</b> {e(p0.get('enviado_em') or '—')}</p>"
            f"<p>{e(p0.get('resumo') or '')}</p>"
            f"<table><tr><th>nº</th><th>nome</th><th>CPF/CNPJ</th><th>papel</th><th>de onde saiu</th></tr>{linhas}</table>"
            "</section>")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{e(titulo)}</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;color:#222;max-width:1100px}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:6px;font-size:13px;vertical-align:top}}th{{background:#eee}}
section{{margin-bottom:28px}}.ref{{background:#f6f6f6;padding:8px;font-size:13px}}</style></head><body>
<h1>{e(titulo)}</h1>
<p>{len(propostas)} pessoa(s) em {len(por_aviso)} aviso(s). Nada disto está na lista ainda: entra o que você aprovar.
Para descartar uma linha, diga o número e o motivo.</p>
{''.join(blocos)}
</body></html>"""


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Propostas de alerta de fraude vindas do malote.")
    ap.add_argument("--banco", required=True)
    ap.add_argument("--carregar", help="JSON com a lista de propostas")
    ap.add_argument("--aprovar", help="ids separados por vírgula, ou 'todas'")
    ap.add_argument("--descartar", help="ids separados por vírgula")
    ap.add_argument("--motivo", help="motivo do descarte")
    ap.add_argument("--aplicar", action="store_true", help="leva as aprovadas à lista de fraudes")
    ap.add_argument("--em-nome-de", default="jean")
    ap.add_argument("--pagina", help="grava a página de revisão (HTML)")
    a = ap.parse_args(argv)
    con = sqlite3.connect(a.banco, timeout=60)
    con.row_factory = sqlite3.Row
    try:
        if a.carregar or a.aprovar or a.descartar or a.aplicar:
            # A CÓPIA ANTES DE GRAVAR, longe do banco (ordem do oficial de 11/10/2026).
            from pasta_das_copias import destino_da_copia
            copia = destino_da_copia(
                Path(f"antes_malote_fraudes_{datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3"), Path(a.banco))
            con.execute("VACUUM INTO ?", (str(copia),))
            if not copia.is_file() or copia.stat().st_size == 0:
                raise PropostaError(f"A cópia do banco não saiu ({copia}); nada foi gravado.")
            print("cópia do banco:", copia)
        init_schema(con)
        if a.carregar:
            print("carregar:", carregar(con, json.loads(Path(a.carregar).read_text(encoding="utf-8"))))
        if a.aprovar:
            ids = [r[0] for r in con.execute("SELECT id FROM mt_alertas_propostos WHERE situacao='PROPOSTO'")] \
                if a.aprovar == "todas" else [int(x) for x in a.aprovar.split(",") if x.strip()]
            print("aprovadas:", revisar(con, ids, aprovar=True, revisor=a.em_nome_de))
        if a.descartar:
            print("descartadas:", revisar(con, [int(x) for x in a.descartar.split(",")], aprovar=False,
                                           revisor=a.em_nome_de, motivo=a.motivo))
        if a.aplicar:
            print("aplicar:", aplicar(con, usuario=a.em_nome_de))
        if a.pagina:
            props = [dict(r) for r in con.execute("SELECT * FROM mt_alertas_propostos ORDER BY codigo_malote, id")]
            Path(a.pagina).write_bytes(pagina_de_revisao(props).encode("utf-8"))
            print("página:", a.pagina)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
