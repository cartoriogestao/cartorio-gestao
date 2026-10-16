"""A CERTIDÃO DAS NOTAS — do ato identificado, ou pela busca da parte.

    «precisa emitir certidão do notas, com selo e etc, inclusive busca quando
     não disser o ato»  — pedido do oficial, 15/10/2026

O PRECEDENTE, MEDIDO EM 15/10/2026 (acervo do E-Ofício e produção, só leitura)
    **O SELO**: 10 selos de certidão das Notas, em 7 protocolos de 2023 e
    2024, TODOS por `/selo/notas/atos-em-geral`, no envelope `AtosEmGeral`:

    | item | selos | quantidade |
    |---|---|---|
    | `13.12.1` certidão ou traslado, uma folha | 6 | 1 em todos |
    | `13.12.3` por folha acrescida | 3 | 1, 1 e **6** — é o número de folhas a mais |
    | `13.12.4` certidão eletrônica (já com buscas e folhas) | 1 | 1 |

    A folha acrescida é **selo próprio**, ao lado do da primeira folha, no
    mesmo protocolo (2023.07.299: `13.12.1` × 1 e `13.12.3` × 6) — a mesma
    forma que a certidão do RI tem medida em 193 protocolos. A parte vai em
    `parteAto` com nome e documento; o envelope não leva folha de segurança
    (`AtosEmGeral` não tem `papelMoeda`), e por isso esta certidão não gasta
    folha.

    **A BUSCA DAS NOTAS (13.13) NUNCA FOI SELADA** — zero no acervo. O caminho
    dela é decisão do oficial de 15/10/2026: selo próprio pelo mesmo
    `atos-em-geral` (`buscas.CAMINHO_DO_SELO_DA_BUSCA`).

    **O TEXTO NÃO TEM PRECEDENTE**: o E-Ofício não guardava certidão das
    Notas (`tbCertidoes` tem 11 modelos, nenhum das Notas, e não há tabela
    de certidões emitidas desta atribuição). O texto de fábrica abaixo se
    monta do que a lei pede — reproduzir o livro e as anotações à margem
    (Lei 8.935/1994, art. 6º, II: cópia FIDEDIGNA) — e **vai ao catálogo de
    modelos**, porque afirmação jurídica em papel assinado é do oficial.

AS ESPÉCIES, E O QUE FICOU DE FORA
    - `INTEIRO_TEOR`: do ato identificado (livro e folha), reproduz o teor e
      a margem;
    - `POSITIVA` e `NEGATIVA`: pela busca da parte (nome ou documento, num
      período) — a positiva relaciona os atos achados, a negativa diz que
      nada consta. **O tipo sai do que a busca achou**, e não de quem pede:
      é a regra da certidão do Protesto, e pelo mesmo motivo.

    **A CERTIDÃO EM BREVE RELATÓRIO NÃO FOI CONSTRUÍDA**: resumir um ato é
    escolher o que dele se afirma, e não há modelo nem precedente nesta casa.
    Fica a pergunta ao oficial.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from typing import Any

from certidao_texto import sem_linha_de_assinatura_a_mao


class CertidaoNotasError(ValueError):
    """Recusa de regra, com a frase pronta para o balcão."""


TIPOS = ("INTEIRO_TEOR", "POSITIVA", "NEGATIVA")
NOME_DO_TIPO = {
    "INTEIRO_TEOR": "Certidão de inteiro teor",
    "POSITIVA": "Certidão positiva de atos",
    "NEGATIVA": "Certidão negativa de atos",
}

# O CAMINHO E OS ITENS MEDIDOS (ver o cabeçalho).
CAMINHO_DO_SELO = "/selo/notas/atos-em-geral"
ITEM_PRIMEIRA_FOLHA = "13.12.1"
ITEM_FOLHA_ACRESCIDA = "13.12.3"
ITEM_ELETRONICA = "13.12.4"
ITENS_DA_CERTIDAO = frozenset({ITEM_PRIMEIRA_FOLHA, "13.12.2",
                               ITEM_FOLHA_ACRESCIDA, ITEM_ELETRONICA})

# O ATO EM LAVRATURA NÃO ESTÁ NO LIVRO, e certidão é cópia do livro: de ato
# que não está em livro nenhum sairia «LIVRO — FOLHA —» com a assinatura do
# tabelião embaixo — a mesma recusa do traslado (`notas_web`).
SITUACAO_FORA_DO_LIVRO = "EM_LAVRATURA"

# As chaves do catálogo de modelos (Administrativo → Modelos).
CHAVE_DO_MODELO = {
    "INTEIRO_TEOR": "NOTAS_CERTIDAO_INTEIRO_TEOR",
    "POSITIVA": "NOTAS_CERTIDAO_POSITIVA",
    "NEGATIVA": "NOTAS_CERTIDAO_NEGATIVA",
}

MODELO_INTEIRO_TEOR = """\
<p><b>CERTIFICO</b>, a pedido de {{ requerente or 'parte interessada' }}{% if requerente_documento %}, {{ requerente_documento }}{% endif %}, que, revendo o Livro {{ a.livro or '—' }}, folha {{ a.folha or '—' }}{% if a.folha_final and a.folha_final != a.folha %} a {{ a.folha_final }}{% endif %}, deste Tabelionato de Notas, nele encontrei {{ rotulo_tipo|lower }} lavrada em {{ data_do_ato }}, cujo teor, na íntegra, é o seguinte:</p>
<p>«{{ teor }}»</p>
{% if anotacoes %}<p><b>ANOTAÇÕES À MARGEM:</b></p>{% for n in anotacoes %}<p>{{ n.tipo }}{% if n.data %} em {{ n.data }}{% endif %}{% if n.texto %}: {{ n.texto }}{% endif %}</p>{% endfor %}{% else %}<p>Nada mais consta à margem do referido ato.</p>{% endif %}
{% if finalidade %}<p><b>FINALIDADE:</b> {{ finalidade }}</p>{% endif %}
<p>O referido é verdade e dou fé.</p>
"""

MODELO_POSITIVA = """\
<p><b>CERTIFICO</b>, a pedido de {{ requerente or 'parte interessada' }}{% if requerente_documento %}, {{ requerente_documento }}{% endif %}, que, feitas as buscas nos livros deste Tabelionato de Notas {{ periodo }}, em nome de <b>{{ nome }}</b>{% if documento %}, {{ documento }}{% endif %}, CONSTA(M) o(s) seguinte(s) ato(s):</p>
{% for x in achados %}<p>— {{ x.rotulo_tipo }}{% if x.natureza %} ({{ x.natureza }}){% endif %}, Livro {{ x.livro or '—' }}, folha {{ x.folha or '—' }}, de {{ x.data }}, em que figura como {{ x.qualificacao or 'parte' }}.</p>{% endfor %}
{% if finalidade %}<p><b>FINALIDADE:</b> {{ finalidade }}</p>{% endif %}
<p>O referido é verdade e dou fé.</p>
"""

MODELO_NEGATIVA = """\
<p><b>CERTIFICO</b>, a pedido de {{ requerente or 'parte interessada' }}{% if requerente_documento %}, {{ requerente_documento }}{% endif %}, que, feitas as buscas nos livros deste Tabelionato de Notas {{ periodo }}, em nome de <b>{{ nome }}</b>{% if documento %}, {{ documento }}{% endif %}, <b>NADA CONSTA</b>.</p>
{% if finalidade %}<p><b>FINALIDADE:</b> {{ finalidade }}</p>{% endif %}
<p>O referido é verdade e dou fé.</p>
"""

MODELO_POR_TIPO = {"INTEIRO_TEOR": MODELO_INTEIRO_TEOR,
                   "POSITIVA": MODELO_POSITIVA,
                   "NEGATIVA": MODELO_NEGATIVA}

SCHEMA = """
-- A CERTIDAO DAS NOTAS — pedido do oficial, 15/10/2026. Tabela propria pela
-- razao de `pt_certidoes` e `at_certidoes`: a certidao nao e ato de livro, e
-- a negativa nem ato tem. Numero por exercicio, teor congelado e sha256.
CREATE TABLE IF NOT EXISTS nt_certidoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,
    ano INTEGER NOT NULL,
    tipo TEXT NOT NULL,              -- INTEIRO_TEOR | POSITIVA | NEGATIVA
    ato_id INTEGER,                  -- o ato identificado (nt_atos)
    nome TEXT,                       -- a busca: de quem
    documento TEXT,
    periodo_de TEXT,
    periodo_ate TEXT,
    achados INTEGER NOT NULL DEFAULT 0,
    achados_json TEXT,
    requerente TEXT,
    requerente_documento TEXT,
    finalidade TEXT,
    eletronica INTEGER NOT NULL DEFAULT 0,
    folhas INTEGER,
    busca_item TEXT,
    isento INTEGER NOT NULL DEFAULT 0,
    motivo_isencao TEXT,
    teor TEXT NOT NULL,
    hash_certidao TEXT NOT NULL,
    selo TEXT,
    lancamento_id INTEGER,
    cancelada INTEGER NOT NULL DEFAULT 0,
    motivo_cancelamento TEXT,
    cancelada_em TEXT,
    cancelada_por TEXT,
    emitida_em TEXT NOT NULL,
    emitida_por TEXT,
    emitida_por_funcao TEXT,
    UNIQUE(numero, ano),
    FOREIGN KEY(ato_id) REFERENCES nt_atos(id)
);
CREATE INDEX IF NOT EXISTS ix_nt_certidoes_ato ON nt_certidoes(ato_id);
"""


def init_notas_certidao_schema(con: sqlite3.Connection) -> None:
    """Cria a tabela, se faltar. Idempotente."""
    con.executescript(SCHEMA)


def _norm(texto: Any) -> str:
    """Sem acento, sem caixa e sem espaço repetido — a régua de
    `notas_partes.normalizar`, comparada em Python: `LOWER` do SQLite é ASCII
    e deixaria «JOSÉ» como «josÉ»."""
    t = unicodedata.normalize("NFD", str(texto or "").strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def _digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def _rotulo_tipo(tipo: Any) -> str:
    try:
        from notas_schema import TIPOS_ATO
        return TIPOS_ATO.get(str(tipo or ""), str(tipo or "").title())
    except Exception:                                     # noqa: BLE001
        return str(tipo or "")


def ato(con: sqlite3.Connection, ato_id: int) -> dict:
    """O ato identificado, pronto para certificar. Recusa o que não serve."""
    linha = con.execute("SELECT * FROM nt_atos WHERE id=?",
                        (int(ato_id),)).fetchone()
    if not linha:
        raise CertidaoNotasError("Ato não encontrado.")
    a = dict(zip(linha.keys(), tuple(linha))) if hasattr(linha, "keys") \
        else dict(linha)
    if str(a.get("situacao") or "") == SITUACAO_FORA_DO_LIVRO:
        raise CertidaoNotasError(
            "Este ato ainda não foi lançado no livro, e certidão é cópia do "
            "livro. Lance-o primeiro.")
    if not str(a.get("teor") or "").strip():
        raise CertidaoNotasError(
            "Este ato está sem o teor no sistema. A certidão de inteiro teor "
            "reproduz o livro: tire a cópia do livro físico.")
    return a


def buscar(con: sqlite3.Connection, *, nome: Any = None, documento: Any = None,
           periodo_de: Any = None, periodo_ate: Any = None) -> list[dict]:
    """Os atos de livro em que a pessoa figura como parte. Só LÊ.

    **O DOCUMENTO VEM ANTES DO NOME**: documento não tem homônimo. Com os
    dois, vale o ato que casar por qualquer um — e a lista diz por qual.
    Testemunha não é parte, e ato em lavratura não está no livro.
    """
    alvo_nome = _norm(nome)
    alvo_doc = _digitos(documento)
    if not alvo_nome and not alvo_doc:
        raise CertidaoNotasError(
            "Informe o nome ou o CPF/CNPJ de quem se busca.")
    if alvo_nome and len(alvo_nome) < 3 and not alvo_doc:
        raise CertidaoNotasError("Nome curto demais para buscar.")
    de = str(periodo_de or "").strip()[:10]
    ate = str(periodo_ate or "").strip()[:10]
    achados: dict[int, dict] = {}
    for r in con.execute(
            """SELECT a.id ato_id, a.tipo, a.livro, a.folha, a.data,
                      a.natureza, a.situacao, p.nome, p.documento,
                      p.qualificacao
                 FROM nt_ato_partes p JOIN nt_atos a ON a.id = p.ato_id
                WHERE p.testemunha = 0 AND a.situacao <> ?
                ORDER BY a.data, a.id""", (SITUACAO_FORA_DO_LIVRO,)):
        d = dict(zip(("ato_id", "tipo", "livro", "folha", "data", "natureza",
                      "situacao", "nome", "documento", "qualificacao"),
                     tuple(r)))
        data = str(d["data"] or "")[:10]
        if de and data < de:
            continue
        if ate and data > ate:
            continue
        por_doc = bool(alvo_doc) and _digitos(d["documento"]) == alvo_doc
        por_nome = bool(alvo_nome) and _norm(d["nome"]) == alvo_nome
        if not (por_doc or por_nome):
            continue
        if d["ato_id"] in achados:
            continue
        d["por"] = "documento" if por_doc else "nome"
        d["rotulo_tipo"] = _rotulo_tipo(d["tipo"])
        achados[d["ato_id"]] = d
    return list(achados.values())


def tipo_para(achados: list) -> str:
    """O tipo sai do que se achou — a regra da certidão do Protesto."""
    return "POSITIVA" if achados else "NEGATIVA"


def frase_do_periodo(periodo_de: Any, periodo_ate: Any) -> str:
    """«no período de 01/01/2010 a 15/10/2026», ou «em todo o acervo»."""
    def br(d: str) -> str:
        d = str(d or "")[:10]
        return f"{d[8:10]}/{d[5:7]}/{d[0:4]}" if len(d) == 10 else d
    de, ate = str(periodo_de or "").strip(), str(periodo_ate or "").strip()
    if de and ate:
        return f"no período de {br(de)} a {br(ate)}"
    if de:
        return f"desde {br(de)}"
    if ate:
        return f"até {br(ate)}"
    return "em todo o acervo do sistema"


def montar_teor(*, tipo: str, modelo: str | None = None, **contexto) -> str:
    """O teor da certidão, pelo modelo do catálogo. Só calcula."""
    from jinja2.sandbox import SandboxedEnvironment
    texto = modelo or MODELO_POR_TIPO[tipo]
    return SandboxedEnvironment(autoescape=True).from_string(texto).render(
        **contexto)


def proximo_numero(con: sqlite3.Connection, ano: int) -> int:
    linha = con.execute("SELECT MAX(numero) FROM nt_certidoes WHERE ano=?",
                        (int(ano),)).fetchone()
    return int((linha[0] if linha else 0) or 0) + 1


def hash_certidao(numero: int, ano: int, tipo: str, teor: str,
                  emitida_em: str) -> str:
    base = f"NOTAS|{numero}|{ano}|{tipo}|{emitida_em}|{teor}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def emitir(con: sqlite3.Connection, *, hoje: str, agora: str,
           ato_id: int | None = None, nome: Any = None, documento: Any = None,
           periodo_de: Any = None, periodo_ate: Any = None,
           tipo: Any = None, requerente: Any = None,
           requerente_documento: Any = None, finalidade: Any = None,
           eletronica: bool = False, busca_item: Any = None,
           isento: bool = False, motivo_isencao: Any = None,
           usuario: Any = None, usuario_funcao: Any = None,
           modelo: str | None = None) -> dict:
    """Emite a certidão, com número do exercício, teor congelado e hash.

    ESCREVE, dentro da transação de quem chama. **A BUSCA RODA DE NOVO
    AQUI**, e não se confia no que a tela mostrou: entre procurar e emitir
    alguém pode ter lavrado ato, e negativa sobre busca velha é certidão que
    mente.
    """
    achados: list[dict] = []
    a = None
    if ato_id:
        a = ato(con, int(ato_id))
        escolhido = "INTEIRO_TEOR"
    else:
        achados = buscar(con, nome=nome, documento=documento,
                         periodo_de=periodo_de, periodo_ate=periodo_ate)
        cabivel = tipo_para(achados)
        escolhido = str(tipo or cabivel).strip().upper()
        if escolhido not in ("POSITIVA", "NEGATIVA"):
            raise CertidaoNotasError(
                f"Tipo de certidão desconhecido para a busca: {escolhido!r}.")
        if escolhido == "NEGATIVA" and achados:
            raise CertidaoNotasError(
                f"Não se emite certidão negativa: a busca achou "
                f"{len(achados)} ato(s) em nome de {str(nome or documento)}.")
        if escolhido == "POSITIVA" and not achados:
            raise CertidaoNotasError(
                "A busca não achou ato nenhum — a certidão que cabe é a "
                "NEGATIVA.")
    if isento and not str(motivo_isencao or "").strip():
        raise CertidaoNotasError(
            "Certidão gratuita precisa do motivo escrito — é ele que a "
            "conferência lê no selo.")

    contexto = {
        "requerente": str(requerente or "").strip() or None,
        "requerente_documento": str(requerente_documento or "").strip()
        or None,
        "finalidade": str(finalidade or "").strip() or None,
        "nome": str(nome or "").strip(),
        "documento": str(documento or "").strip() or None,
        "periodo": frase_do_periodo(periodo_de, periodo_ate),
        "achados": achados,
    }
    if a is not None:
        from notas_anotacoes import do_ato
        data = str(a.get("data") or "")[:10]
        from markupsafe import Markup
        contexto.update({
            # O TEOR JÁ É HTML (`nt_atos.teor_formato`), e é ele que se
            # reproduz; o resto do contexto é texto do balcão e se escapa.
            "a": a, "teor": Markup(_sem_marcas(a.get("teor"))),
            "rotulo_tipo": _rotulo_tipo(a.get("tipo")),
            "data_do_ato": (f"{data[8:10]}/{data[5:7]}/{data[0:4]}"
                            if len(data) == 10 else data),
            "anotacoes": do_ato(con, int(a["id"])),
        })
    teor = sem_linha_de_assinatura_a_mao(
        montar_teor(tipo=escolhido, modelo=modelo, **contexto))
    ano = int(str(hoje)[:4])
    numero = proximo_numero(con, ano)
    impressao = hash_certidao(numero, ano, escolhido, teor, agora)
    cur = con.execute(
        """INSERT INTO nt_certidoes(numero, ano, tipo, ato_id, nome,
               documento, periodo_de, periodo_ate, achados, achados_json,
               requerente, requerente_documento, finalidade, eletronica,
               busca_item, isento, motivo_isencao, teor, hash_certidao,
               emitida_em, emitida_por, emitida_por_funcao)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (numero, ano, escolhido, int(a["id"]) if a else None,
         contexto["nome"] or None, contexto["documento"],
         str(periodo_de or "").strip() or None,
         str(periodo_ate or "").strip() or None,
         len(achados), json.dumps(achados, ensure_ascii=False, default=str),
         contexto["requerente"], contexto["requerente_documento"],
         contexto["finalidade"], 1 if eletronica else 0,
         str(busca_item or "").strip() or None, 1 if isento else 0,
         (str(motivo_isencao or "").strip() or None) if isento else None,
         teor, impressao, agora, str(usuario or "").strip() or None,
         str(usuario_funcao or "").strip() or None))
    return {"certidao_id": int(cur.lastrowid), "numero": numero, "ano": ano,
            "tipo": escolhido, "achados": len(achados), "hash": impressao,
            "teor": teor,
            "parte": _parte_do_selo(con, a, contexto)}


def _sem_marcas(teor: Any) -> str:
    """O teor do livro sem as marcas internas do sistema (`@@…@@`)."""
    return re.sub(r"@@[A-Z_]+@@", "", str(teor or "")).strip()


def _parte_do_selo(con, a, contexto) -> dict:
    """Quem vai em `parteAto`: o requerente; sem ele, a pessoa buscada ou a
    primeira parte do ato. Os 10 selos do acervo levaram UMA pessoa."""
    if contexto.get("requerente"):
        return {"nome": contexto["requerente"],
                "documento": contexto.get("requerente_documento") or ""}
    if contexto.get("nome"):
        return {"nome": contexto["nome"],
                "documento": contexto.get("documento") or ""}
    if a is not None:
        p = con.execute(
            """SELECT nome, documento FROM nt_ato_partes
                WHERE ato_id=? AND testemunha=0 ORDER BY ordem LIMIT 1""",
            (int(a["id"]),)).fetchone()
        if p:
            return {"nome": p[0], "documento": p[1] or ""}
    return {"nome": "", "documento": ""}


def itens_do_selo(folhas: int, *, eletronica: bool = False
                  ) -> list[tuple[str, int]]:
    """Os itens que viram selo, na forma medida. Só calcula.

    Uma folha: `13.12.1` × 1. Mais de uma: o par, com o excedente no
    `13.12.3` (2023.07.299: 1 + 6). A eletrônica é um item só, `13.12.4`,
    que já inclui buscas e folhas.
    """
    if eletronica:
        return [(ITEM_ELETRONICA, 1)]
    n = max(1, int(folhas or 1))
    itens = [(ITEM_PRIMEIRA_FOLHA, 1)]
    if n > 1:
        itens.append((ITEM_FOLHA_ACRESCIDA, n - 1))
    return itens


def envelope(*, codigo: Any, quantidade: int, escrevente: Any,
             versao_tabela: Any, parte: dict | None = None,
             isento: bool = False, motivo_isencao: Any = None) -> dict:
    """O corpo do pedido de `/selo/notas/atos-em-geral`. Só calcula.

    Medido nos 10 envelopes: `ato{codigo, codigoTabelaCusta}`, `escrevente`,
    `partes{nomePartes: [], parteAto: [{documento, nome}]}`, `quantidade`.
    O documento vai com onze zeros quando não há, como lá. A isenção vai na
    forma `DadosIsento` do contrato (`isento{value, motivo}`).
    """
    faltando = [o for o, v in (("o item", codigo), ("o escrevente", escrevente),
                               ("a versão da tabela de custas", versao_tabela))
                if not str(v or "").strip()]
    if faltando:
        raise CertidaoNotasError(
            f"O selo da certidão das Notas não sai sem {', '.join(faltando)}.")
    if isento and not str(motivo_isencao or "").strip():
        raise CertidaoNotasError(
            "Certidão gratuita precisa do motivo escrito.")
    p = parte or {}
    corpo: dict[str, Any] = {
        "ato": {"codigo": str(codigo).strip(),
                "codigoTabelaCusta": str(versao_tabela).strip()},
        "escrevente": str(escrevente).strip(),
        "partes": {"nomePartes": [],
                   "parteAto": [{"documento": _digitos(p.get("documento"))
                                 or "00000000000",
                                 "nome": str(p.get("nome") or "").strip()}]},
        "quantidade": max(1, int(quantidade or 1)),
    }
    if isento:
        corpo["isento"] = {"value": True,
                           "motivo": str(motivo_isencao).strip().upper()}
    return corpo


def certidao(con: sqlite3.Connection, certidao_id: int) -> dict | None:
    linha = con.execute("SELECT * FROM nt_certidoes WHERE id=?",
                        (int(certidao_id),)).fetchone()
    if not linha:
        return None
    return dict(zip(linha.keys(), tuple(linha))) if hasattr(linha, "keys") \
        else dict(linha)


def listar(con: sqlite3.Connection, limite: int = 100) -> list[dict]:
    cur = con.execute(
        """SELECT * FROM nt_certidoes ORDER BY ano DESC, numero DESC
            LIMIT ?""", (int(limite),))
    nomes = [d[0] for d in cur.description]
    return [dict(zip(nomes, r)) for r in cur.fetchall()]


def cancelar(con: sqlite3.Connection, certidao_id: int, *, motivo: Any,
             agora: str, usuario: Any) -> None:
    """Cancela; o teor fica. Certidão errada não se apaga."""
    if len(str(motivo or "").strip()) < 10:
        raise CertidaoNotasError(
            "Escreva o motivo do cancelamento (pelo menos dez letras).")
    n = con.execute(
        """UPDATE nt_certidoes SET cancelada=1, motivo_cancelamento=?,
               cancelada_em=?, cancelada_por=?
            WHERE id=? AND cancelada=0""",
        (str(motivo).strip(), agora, str(usuario or "").strip() or None,
         int(certidao_id))).rowcount
    if not n:
        raise CertidaoNotasError("Certidão não encontrada ou já cancelada.")
