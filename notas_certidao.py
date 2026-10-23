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

    - `BREVE_RELATO`: do ato identificado, a cópia RESUMIDA (art. 851: «cópia
      integral ou resumida») — LD02, 21/10/2026, depois do «corrija tudo» do
      oficial. Até aqui ela não existia: resumir um ato é escolher o que dele
      se afirma. **Afirma só o que o livro registra em campo** — a espécie e a
      natureza, o livro, a folha, o termo, a data, as partes com a qualidade
      em que figuram e o selo do ato —, e não resume o teor: o objeto do ato
      continua na de inteiro teor. O texto vai ao catálogo, como o das outras.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

import modelos_da_casa as MODELOS
import html_sem_script as HSS
from bd_nativo import banco
from certidao_texto import sem_linha_de_assinatura_a_mao


class CertidaoNotasError(ValueError):
    """Recusa de regra, com a frase pronta para o balcão."""


TIPOS = ("INTEIRO_TEOR", "POSITIVA", "NEGATIVA", "BREVE_RELATO")
# As do ato identificado; a primeira é a que sai quando o pedido não diz.
TIPOS_DO_ATO = ("INTEIRO_TEOR", "BREVE_RELATO")
# O TÍTULO DE CADA CERTIDÃO saiu daqui no LF06D (19/10/2026): é peça do papel
# dela (`modelos_padrao/notas/NOTAS_CERTIDAO_*__titulo.txt`). `NOME_DO_TIPO`, o
# nome antigo, continua respondendo (`__getattr__`), lido da base — as telas e
# a moldura da certidão (`atribuicoes_web`) o leem por ele.
PECA_DO_TITULO = {
    "INTEIRO_TEOR": "NOTAS_CERTIDAO_INTEIRO_TEOR__titulo",
    "POSITIVA": "NOTAS_CERTIDAO_POSITIVA__titulo",
    "NEGATIVA": "NOTAS_CERTIDAO_NEGATIVA__titulo",
    "BREVE_RELATO": "NOTAS_CERTIDAO_BREVE_RELATO__titulo",
}


def nome_do_tipo(con: Any = None) -> dict[str, str]:
    """`{tipo: título da certidão}`, da base (ajuste da casa → padrão). Só lê."""
    textos = MODELOS.textos(con)
    return {tipo: textos(peca) for tipo, peca in PECA_DO_TITULO.items()}

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
    "BREVE_RELATO": "NOTAS_CERTIDAO_BREVE_RELATO",
}

# `MODELO_INTEIRO_TEOR` — o texto de fábrica do papel NOTAS_CERTIDAO_INTEIRO_TEOR — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/notas/NOTAS_CERTIDAO_INTEIRO_TEOR.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

# `MODELO_POSITIVA` — o texto de fábrica do papel NOTAS_CERTIDAO_POSITIVA — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/notas/NOTAS_CERTIDAO_POSITIVA.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

# `MODELO_NEGATIVA` — o texto de fábrica do papel NOTAS_CERTIDAO_NEGATIVA — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/notas/NOTAS_CERTIDAO_NEGATIVA.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.


SCHEMA = (
    # A CERTIDAO DAS NOTAS — pedido do oficial, 15/10/2026. Tabela propria pela
    # razao de `pt_certidoes` e `at_certidoes`: a certidao nao e ato de livro, e
    # a negativa nem ato tem. Numero por exercicio, teor congelado e sha256.
    """CREATE TABLE IF NOT EXISTS nt_certidoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    numero integer NOT NULL,
    ano integer NOT NULL,
    tipo text NOT NULL,              -- INTEIRO_TEOR | POSITIVA | NEGATIVA
    ato_id bigint REFERENCES nt_atos(id),  -- o ato identificado (nt_atos)
    nome text,                       -- a busca: de quem
    documento text,
    periodo_de text,
    periodo_ate text,
    achados integer NOT NULL DEFAULT 0,
    achados_json text,
    requerente text,
    requerente_documento text,
    finalidade text,
    eletronica integer NOT NULL DEFAULT 0,
    folhas integer,
    busca_item text,
    isento integer NOT NULL DEFAULT 0,
    motivo_isencao text,
    teor text NOT NULL,
    hash_certidao text NOT NULL,
    selo text,
    lancamento_id bigint,
    cancelada integer NOT NULL DEFAULT 0,
    motivo_cancelamento text,
    cancelada_em text,
    cancelada_por text,
    emitida_em text NOT NULL,
    emitida_por text,
    emitida_por_funcao text,
    UNIQUE(numero, ano)
)""",
    "CREATE INDEX IF NOT EXISTS ix_nt_certidoes_ato ON nt_certidoes(ato_id)",
    # POR QUE O SIGILO DO TESTAMENTO FOI LEVANTADO (LG04): o requerimento
    # escrito do testador ou a certidão de óbito — art. 851, §§ 4º e 5º. Fica
    # na linha da certidão, e não só no audit, porque é a primeira pergunta da
    # correição sobre certidão de testamento.
    "ALTER TABLE nt_certidoes ADD COLUMN IF NOT EXISTS sigilo_fundamento text",
)

# O TESTAMENTO É SIGILOSO ENQUANTO VIVE O TESTADOR — Código de Normas do MA
# (Prov. COGEX 28/2026), art. 851:
#
#   § 4º Enquanto vivo o testador, só a este poderão ser fornecidas certidões de
#        seu testamento, mediante requerimento escrito que deverá ser arquivado
#        na Serventia.
#   § 5º Mediante a apresentação da certidão de óbito do testador, qualquer
#        pessoa poderá requerer certidão do testamento.
#
# Até o LG04 (19/10/2026) esta certidão não perguntava nada: o testamento saía
# em inteiro teor a qualquer um, e a busca POSITIVA o listava a quem pedisse.
# O acervo importado guarda testamento como ESCRITURA com `tipo_testamento`
# preenchido, e por isso vale também a coluna, e não só o tipo do ato.
TIPOS_SOB_SIGILO = ("TESTAMENTO", "TESTAMENTO_CERRADO")
QUALIFICACOES_DO_TESTADOR = ("TESTADOR", "TESTADORA", "OUTORGANTE")


def init_notas_certidao_schema(con: Any) -> None:
    """Cria a tabela, se faltar. Idempotente."""
    bd = banco(con)
    for comando in SCHEMA:
        bd.escrever(comando)


def e_testamento(a: dict | None) -> bool:
    """O ato está sob o sigilo do art. 851, § 4º? Só calcula."""
    if not a:
        return False
    return (str(a.get("tipo") or "").upper() in TIPOS_SOB_SIGILO
            or a.get("tipo_testamento") is not None)


def _testadores(con: Any, ato_id: int) -> list[dict]:
    """Quem testou: a parte que não é testemunha, qualificada como testador
    (ou outorgante, que é como o acervo escreve). Só LÊ."""
    partes = banco(con).ler(
        """SELECT nome, documento, qualificacao FROM nt_ato_partes
            WHERE ato_id = %s AND testemunha = 0 ORDER BY ordem, id""",
        (int(ato_id),))
    return [dict(p) for p in partes
            if _norm(p["qualificacao"]).upper() in QUALIFICACOES_DO_TESTADOR]


def fundamento_do_sigilo(con: Any, a: dict, *, requerente_documento: Any,
                         requerimento_escrito: bool,
                         obito_apresentado: Any) -> str | None:
    """Por que esta certidão do testamento pode sair — ou a recusa. Só LÊ.

    Devolve `None` quando o ato não é testamento, e a frase que vai a
    `nt_certidoes.sigilo_fundamento` quando é e o sigilo se levanta. Levanta
    `CertidaoNotasError` quando não se levanta.

    **A CERTIDÃO DE ÓBITO VALE PARA QUALQUER UM** (§ 5º), e o que se guarda é
    a identificação dela (matrícula ou livro/folha/termo) — o papel fica no
    arquivo da serventia, como o requerimento. **O TESTADOR SE PROVA PELO
    DOCUMENTO**, e não pelo nome: homônimo é o caso que o sigilo existe para
    barrar. O requerimento ESCRITO e arquivado é condição do § 4º, e quem
    atende declara tê-lo recebido.
    """
    if not e_testamento(a):
        return None
    obito = str(obito_apresentado or "").strip()
    if len(obito) >= 5:
        return f"Certidão de óbito do testador apresentada: {obito} (art. 851, § 5º)."
    rotulo = (f"o testamento do livro {a.get('livro') or '—'}, folha "
              f"{a.get('folha') or '—'}")
    documento = _digitos(requerente_documento)
    testadores = _testadores(con, int(a["id"]))
    eh_o_testador = bool(documento) and any(
        _digitos(t["documento"]) == documento for t in testadores)
    if not eh_o_testador:
        raise CertidaoNotasError(
            f"Sigilo do testamento: {rotulo} só tem certidão para o próprio "
            f"testador, pelo CPF dele no campo do requerente, enquanto ele "
            f"vive — ou, para qualquer pessoa, com a certidão de óbito "
            f"apresentada (Código de Normas, art. 851, §§ 4º e 5º). Informe a "
            f"matrícula da certidão de óbito, ou o CPF do testador.")
    if not requerimento_escrito:
        raise CertidaoNotasError(
            f"Sigilo do testamento: a certidão de {rotulo} ao testador exige "
            f"requerimento ESCRITO, arquivado na serventia (art. 851, § 4º). "
            f"Receba o requerimento e marque que ele foi arquivado.")
    return ("Requerimento escrito do próprio testador, arquivado na serventia "
            "(art. 851, § 4º).")


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


def ato(con: Any, ato_id: int, *, exige_teor: bool = True) -> dict:
    """O ato identificado, pronto para certificar. Recusa o que não serve.

    O BREVE RELATO NÃO PEDE O TEOR (`exige_teor=False`): ele se monta dos
    campos do livro — espécie, livro, folha, termo, data, partes e selo —, e
    o ato do acervo que veio sem o teor continua tendo o que se resumir.
    """
    a = banco(con).um("SELECT * FROM nt_atos WHERE id = %s", (int(ato_id),))
    if not a:
        raise CertidaoNotasError("Ato não encontrado.")
    if str(a.get("situacao") or "") == SITUACAO_FORA_DO_LIVRO:
        raise CertidaoNotasError(
            "Este ato ainda não foi lançado no livro, e certidão é cópia do "
            "livro. Lance-o primeiro.")
    if exige_teor and not str(a.get("teor") or "").strip():
        raise CertidaoNotasError(
            "Este ato está sem o teor no sistema. A certidão de inteiro teor "
            "reproduz o livro: tire a cópia do livro físico.")
    return a


def buscar(con: Any, *, nome: Any = None, documento: Any = None,
           periodo_de: Any = None, periodo_ate: Any = None) -> list[dict]:
    """Os atos de livro em que a pessoa figura como parte. Só LÊ.

    **O DOCUMENTO VEM ANTES DO NOME**: documento não tem homônimo. Com os
    dois, vale o ato que casar por qualquer um — e a lista diz por qual.
    Testemunha não é parte, e ato em lavratura não está no livro.

    **O TERMO DE CADA ATO VEM JUNTO** (LD07, 21/10/2026): a certidão positiva
    diz o livro e a folha, e a localização do ato no livro é também o seu
    número — «a numeração das escrituras ... não será interrompida» (CN-MA
    arts. 792 e 851, § 1º). O acervo sem termo traz a ordem, como o inteiro
    teor.
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
    for d in banco(con).ler(
            """SELECT a.id AS ato_id, a.tipo, a.tipo_testamento, a.livro,
                      a.folha, a.termo, a.numero_ordem, a.data, a.natureza,
                      a.situacao, p.nome, p.documento, p.qualificacao
                 FROM nt_ato_partes p JOIN nt_atos a ON a.id = p.ato_id
                WHERE p.testemunha = 0 AND a.situacao <> %s
                ORDER BY a.data, a.id, p.ordem, p.id""",
            (SITUACAO_FORA_DO_LIVRO,)):
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


def data_de_papel(valor: Any) -> str:
    """«2026-10-20» → «20/10/2026»: a data como o papel a escreve (CN-MA art.
    795, § 4º). O que não for data do banco volta como veio. Só calcula."""
    d = str(valor or "")[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        return f"{d[8:10]}/{d[5:7]}/{d[0:4]}"
    return str(valor or "")


def partes_do_ato(con: Any, ato_id: int) -> list[dict]:
    """As partes do ato, na ordem do livro, sem as testemunhas — quem figura
    no ato e em que qualidade, para o breve relato. Só LÊ."""
    return [dict(p) for p in banco(con).ler(
        """SELECT nome, documento, qualificacao FROM nt_ato_partes
            WHERE ato_id = %s AND testemunha = 0 ORDER BY ordem, id""",
        (int(ato_id),))]


def frase_do_periodo(periodo_de: Any, periodo_ate: Any, *, con: Any = None) -> str:
    """«no período de 01/01/2010 a 15/10/2026», ou «em todo o acervo».

    As quatro frases são peças da certidão positiva (valem também para a
    negativa) desde o LF06D; qual delas entra é decidido aqui.
    """
    def br(d: str) -> str:
        d = str(d or "")[:10]
        return f"{d[8:10]}/{d[5:7]}/{d[0:4]}" if len(d) == 10 else d
    textos = MODELOS.textos(con)
    de, ate = str(periodo_de or "").strip(), str(periodo_ate or "").strip()
    if de and ate:
        return textos.preencher("NOTAS_CERTIDAO_POSITIVA__periodo", de=br(de), ate=br(ate))
    if de:
        return textos.preencher("NOTAS_CERTIDAO_POSITIVA__desde", de=br(de))
    if ate:
        return textos.preencher("NOTAS_CERTIDAO_POSITIVA__ate", ate=br(ate))
    return textos("NOTAS_CERTIDAO_POSITIVA__todo_o_acervo")


def montar_teor(*, tipo: str, modelo: str | None = None, **contexto) -> str:
    """O teor da certidão, pelo modelo do catálogo. Só calcula."""
    from jinja2.sandbox import SandboxedEnvironment
    texto = modelo or MODELOS.padrao_de(CHAVE_DO_MODELO[tipo])
    return SandboxedEnvironment(autoescape=True).from_string(texto).render(
        **contexto)


def proximo_numero(con: Any, ano: int) -> int:
    bd = banco(con)
    bd.travar("nt_certidoes.numero")
    maior = bd.valor("SELECT MAX(numero) FROM nt_certidoes WHERE ano = %s",
                     (int(ano),))
    return int(maior or 0) + 1


def hash_certidao(numero: int, ano: int, tipo: str, teor: str,
                  emitida_em: str) -> str:
    base = f"NOTAS|{numero}|{ano}|{tipo}|{emitida_em}|{teor}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def emitir(con: Any, *, hoje: str, agora: str,
           ato_id: int | None = None, nome: Any = None, documento: Any = None,
           periodo_de: Any = None, periodo_ate: Any = None,
           tipo: Any = None, requerente: Any = None,
           requerente_documento: Any = None, finalidade: Any = None,
           eletronica: bool = False, busca_item: Any = None,
           isento: bool = False, motivo_isencao: Any = None,
           usuario: Any = None, usuario_funcao: Any = None,
           modelo: str | None = None, requerimento_escrito: bool = False,
           obito_apresentado: Any = None) -> dict:
    """Emite a certidão, com número do exercício, teor congelado e hash.

    ESCREVE, dentro da transação de quem chama. **A BUSCA RODA DE NOVO
    AQUI**, e não se confia no que a tela mostrou: entre procurar e emitir
    alguém pode ter lavrado ato, e negativa sobre busca velha é certidão que
    mente.

    **O TESTAMENTO TEM SIGILO** (LG04, art. 851, §§ 4º e 5º): do ato
    identificado, só com `fundamento_do_sigilo`; da busca, a que alcança
    testamento é RECUSADA inteira quando o sigilo não se levanta — a positiva o
    revelaria, e a negativa diria que não há o que há.

    **DO ATO IDENTIFICADO, O PEDIDO DIZ A FORMA** (LD02): inteiro teor, quando
    não diz, ou breve relato (`TIPOS_DO_ATO`).
    """
    achados: list[dict] = []
    a = None
    sigilo = None
    if ato_id:
        escolhido = str(tipo or TIPOS_DO_ATO[0]).strip().upper()
        if escolhido not in TIPOS_DO_ATO:
            raise CertidaoNotasError(
                f"Tipo de certidão desconhecido para o ato identificado: "
                f"{escolhido!r}. Do ato sai a de inteiro teor ou a em breve "
                f"relato.")
        a = ato(con, int(ato_id), exige_teor=escolhido == "INTEIRO_TEOR")
        sigilo = fundamento_do_sigilo(
            con, a, requerente_documento=requerente_documento,
            requerimento_escrito=requerimento_escrito,
            obito_apresentado=obito_apresentado)
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
        fundamentos = []
        for achado in achados:
            testamento = banco(con).um(
                "SELECT * FROM nt_atos WHERE id = %s", (int(achado["ato_id"]),))
            fundamento = fundamento_do_sigilo(
                con, testamento, requerente_documento=requerente_documento,
                requerimento_escrito=requerimento_escrito,
                obito_apresentado=obito_apresentado)
            if fundamento and fundamento not in fundamentos:
                fundamentos.append(fundamento)
        sigilo = " ".join(fundamentos) or None
    if isento and not str(motivo_isencao or "").strip():
        raise CertidaoNotasError(
            "Certidão gratuita precisa do motivo escrito — é ele que a "
            "conferência lê no selo.")

    try:
        periodo = frase_do_periodo(periodo_de, periodo_ate, con=con)
    except MODELOS.ModeloError as erro:
        # o ajuste da casa que não monta: recusa de balcão, antes de numerar
        raise CertidaoNotasError(str(erro)) from erro
    contexto = {
        "requerente": str(requerente or "").strip() or None,
        "requerente_documento": str(requerente_documento or "").strip()
        or None,
        "finalidade": str(finalidade or "").strip() or None,
        "nome": str(nome or "").strip(),
        "documento": str(documento or "").strip() or None,
        "periodo": periodo,
        # A DATA DE CADA ATO ACHADO SAI COMO DATA DE PAPEL (LD02): o modelo
        # escreve `{{ x.data }}`, e saía «2026-10-20», como o banco a guarda
        # (CN-MA art. 795, § 4º). `achados_json` continua com a do banco.
        "achados": [dict(x, data=data_de_papel(x.get("data"))) for x in achados],
    }
    if a is not None:
        from notas_anotacoes import do_ato
        from markupsafe import Markup
        contexto.update({
            # O TEOR JÁ É HTML (`nt_atos.teor_formato`), e é ele que se
            # reproduz; o resto do contexto é texto do balcão e se escapa.
            # … E SEM O QUE EXECUTA (revisão de segurança de 22/10/2026, A8):
            # o teor é escrito no balcão e vai, pela certidão, ao navegador e
            # ao Chrome que conta as folhas.
            "a": a, "teor": Markup(HSS.limpar(_sem_marcas(a.get("teor")))),
            "rotulo_tipo": _rotulo_tipo(a.get("tipo")),
            "data_do_ato": data_de_papel(str(a.get("data") or "")[:10]),
            "anotacoes": do_ato(con, int(a["id"])),
            "selos_do_ato": selos_do_ato(con, a),
            "partes": partes_do_ato(con, int(a["id"])),
        })
    teor = sem_linha_de_assinatura_a_mao(
        montar_teor(tipo=escolhido, modelo=modelo, **contexto))
    ano = int(str(hoje)[:4])
    numero = proximo_numero(con, ano)
    impressao = hash_certidao(numero, ano, escolhido, teor, agora)
    novo = banco(con).escrever(
        """INSERT INTO nt_certidoes(numero, ano, tipo, ato_id, nome,
               documento, periodo_de, periodo_ate, achados, achados_json,
               requerente, requerente_documento, finalidade, eletronica,
               busca_item, isento, motivo_isencao, teor, hash_certidao,
               emitida_em, emitida_por, emitida_por_funcao,
               sigilo_fundamento)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
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
         str(usuario_funcao or "").strip() or None, sigilo))
    return {"certidao_id": int(novo[0]["id"]), "numero": numero, "ano": ano,
            "tipo": escolhido, "achados": len(achados), "hash": impressao,
            "teor": teor,
            "parte": _parte_do_selo(con, a, contexto)}


def selos_do_ato(con: Any, a: dict) -> list[str]:
    """O(s) selo(s) do ato certificado, como o razão os guarda. Só LÊ.

    «TERMO E CERTIDÃO» — o oficial, 20/10/2026 (LT02). O termo do livro sai
    com o carimbo do selo do ato (número, emolumentos, consulta), e o próprio
    teor diz «Emolumentos e selo de fiscalização ao final do ato»: a certidão
    de inteiro teor que reproduzisse o teor sem o selo diria que eles estão
    ali e não os mostraria (CN-MA arts. 87, XVI, 131 e 851). O texto é o que o
    aparelho declarou (`ato_selado.etiquetas_do_ato`: o do ato e o do
    arquivamento); sem texto no razão, o número — e nunca uma conta refeita.
    """
    import ato_selado as AS
    fora = []
    for selo in AS.etiquetas_do_ato(con, "nt_atos", int(a["id"]),
                                    a.get("selo") or ""):
        texto = (" ".join(str(selo.get("texto") or "").split())
                 or str(selo.get("numero") or "").strip())
        if texto and texto not in fora:
            fora.append(texto)
    return fora


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
        p = banco(con).um(
            """SELECT nome, documento FROM nt_ato_partes
                WHERE ato_id = %s AND testemunha = 0
                ORDER BY ordem, id LIMIT 1""",
            (int(a["id"]),))
        if p:
            return {"nome": p["nome"], "documento": p["documento"] or ""}
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


def certidao(con: Any, certidao_id: int) -> dict | None:
    return banco(con).um("SELECT * FROM nt_certidoes WHERE id = %s",
                         (int(certidao_id),))


def listar(con: Any, limite: int = 100) -> list[dict]:
    return banco(con).ler(
        """SELECT * FROM nt_certidoes ORDER BY ano DESC, numero DESC
            LIMIT %s""", (int(limite),))


def cancelar(con: Any, certidao_id: int, *, motivo: Any,
             agora: str, usuario: Any) -> None:
    """Cancela; o teor fica. Certidão errada não se apaga."""
    if len(str(motivo or "").strip()) < 10:
        raise CertidaoNotasError(
            "Escreva o motivo do cancelamento (pelo menos dez letras).")
    n = banco(con).escrever(
        """UPDATE nt_certidoes SET cancelada = 1, motivo_cancelamento = %s,
               cancelada_em = %s, cancelada_por = %s
            WHERE id = %s AND cancelada = 0 RETURNING id""",
        (str(motivo).strip(), agora, str(usuario or "").strip() or None,
         int(certidao_id)))
    if not n:
        raise CertidaoNotasError("Certidão não encontrada ou já cancelada.")


def __getattr__(nome: str):
    """Os nomes antigos do texto de fábrica, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06A (19/10/2026) e mora em `modelos_padrao/`;
    o título de cada certidão (`NOME_DO_TIPO`) saiu no LF06D. Quem ainda
    importa o nome antigo recebe o padrão da base — o MESMO que o papel
    imprime, e não uma cópia que ficou para trás. Nome que não é de papel
    continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    if nome == "NOME_DO_TIPO":
        return nome_do_tipo()
    return MODELOS.constante_antiga(__name__, nome)
