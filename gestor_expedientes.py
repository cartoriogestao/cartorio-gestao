"""A triagem dos expedientes pelo agente — o malote lido e despachado.

    «vamos seguir no desenvolvimento para ter um agente completo que faça todo
     trabalho do oficial amanhã» — o oficial, 06/10/2026

O QUE SE MEDIU
    Em 06/10/2026 havia 22 expedientes em RECEBIDO, quase todos do Malote
    Digital, e só 5 com tarefa: ofícios de juízo pedindo certidão, mandados,
    decisões da COGEX com prazo, circulares. O que fazer está DENTRO do PDF, e
    o PDF tem texto (o `pypdf` da instalação o lê — conferido em seis deles).

O QUE O AGENTE FAZ
    Lê o expediente e os anexos, passa pela MESMA barreira de privacidade da
    ajuda (`sanitizar_para_modelo`) e pergunta à IA o que é, de que setor, qual
    o prazo e o que fazer. Com a resposta:
      - CUMPRIMENTO / RESPOSTA / PROVIDÊNCIA → cria a tarefa LIGADA ao
        expediente (`linked_expediente_id`, `source_type='EXPEDIENTE'`, a mesma
        forma da tela que cadastra expediente), para o responsável do setor
        segundo a distribuição do oficial, com o prazo e os passos;
      - CIÊNCIA → não vira tarefa: vai para o despacho diário do oficial, com o
        resumo. Circular que só informa, transformada em tarefa, é ruído.

O QUE ELE NÃO FAZ
    Não responde ao juízo, não arquiva, não muda a etapa do expediente: isso
    é de quem cumpre. O rascunho de resposta, quando a IA o escreve, vai DENTRO
    da tarefa, para quem cumpre revisar.

UMA VEZ POR VERSÃO: o mesmo expediente com os mesmos anexos não volta à IA
(o hash do dossiê), e há teto por dia. A rede nunca fica dentro de transação.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

TETO_POR_DIA = 30
LIMITE_DO_TEXTO = 18000
MAXIMO_DE_SAIDA = 4000
PROVEDORES = ("claude",)

TIPOS = ("CUMPRIMENTO", "RESPOSTA", "PROVIDENCIA", "CIENCIA")
SETORES_VALIDOS = ("RCPN", "RI", "RI_QUALIFICACAO", "NOTAS", "NOTAS_QUALIFICACAO",
                   "RCPJ_RTD", "PROTESTO", "GESTAO", "TI")

SCHEMA = """
CREATE TABLE IF NOT EXISTS ge_triagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expediente_id INTEGER NOT NULL,
    hash_dossie TEXT NOT NULL,
    lido_em TEXT NOT NULL,
    provedor TEXT,
    modelo TEXT,
    resultado_json TEXT,
    erro TEXT,
    tarefa_id INTEGER,
    UNIQUE (expediente_id, hash_dossie)
);
"""

INSTRUCAO = """Você faz a triagem do malote de uma serventia extrajudicial (cartório \
de ofício único: Registro Civil, Registro de Imóveis, Notas, RTD/PJ e Protesto) no \
Maranhão. Recebe um expediente (ofício, mandado, decisão, circular) e o texto dos \
anexos. Nomes e documentos de pessoas vêm mascarados como marcas — use as marcas.

Responda SÓ com um objeto JSON, sem texto em volta:
{
  "tipo": "CUMPRIMENTO" | "RESPOSTA" | "PROVIDENCIA" | "CIENCIA",
  "setor": "RCPN" | "RI" | "RI_QUALIFICACAO" | "NOTAS" | "NOTAS_QUALIFICACAO" | "RCPJ_RTD" | "PROTESTO" | "GESTAO" | "TI",
  "resumo": "até 300 caracteres: quem manda, o que é",
  "o_que_fazer": "passos concretos, até 600 caracteres; vazio se CIENCIA",
  "prazo_dias": número ou null,
  "dias_uteis": true | false,
  "data_limite": "AAAA-MM-DD" ou null,
  "urgencia": "ALTA" | "MEDIA" | "BAIXA",
  "quem_decide": "OFICIAL" | "ESCREVENTE",
  "rascunho_resposta": "minuta curta de ofício de resposta, ou null"
}

Regras:
- CUMPRIMENTO: mandado ou ordem para praticar ato (averbar, registrar, cancelar, \
emitir certidão). RESPOSTA: pede informação ou documento de volta. PROVIDENCIA: \
pede uma providência interna da serventia (cadastro, declaração em sistema, \
inscrição). CIENCIA: só informa (circular, convite, aviso, edição de provimento) \
e nada pede à serventia.
- Setor: certidão/registro de pessoa → RCPN; ato em matrícula, penhora, usucapião \
→ RI_QUALIFICACAO; certidão de matrícula → RI; escritura/procuração → \
NOTAS_QUALIFICACAO; COGEX, correição, declarações, produtividade → GESTAO.
- Prazo: o que o documento disser; se disser "X dias" sem data, prazo_dias=X e \
dias_uteis conforme o texto (prazo judicial em dias é útil, salvo se disser \
corridos). Se não houver prazo, null.
- Não invente: se o texto não diz, deixe null ou vazio.
- quem_decide=OFICIAL quando a providência é do delegatário (responder à \
COGEX, decidir qualificação, inscrever-se em edital)."""


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def _tem_tabela(con, nome: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (nome,)).fetchone() is not None


def texto_dos_anexos(con: sqlite3.Connection, expediente_id: int,
                     limite: int = LIMITE_DO_TEXTO) -> str:
    """O texto dos PDFs anexos, na ordem em que entraram. O que não se lê, se diz."""
    partes = []
    for nome, caminho in con.execute(
            """SELECT original_name, stored_path FROM attachments
                WHERE entity_type = 'EXPEDIENTE' AND entity_id = ? ORDER BY id""",
            (expediente_id,)):
        if not str(nome or "").lower().endswith(".pdf"):
            partes.append(f"[anexo {nome}: não é PDF, não lido]")
            continue
        try:
            import logging
            from pypdf import PdfReader
            # O PDF DO MALOTE TRAZ DICIONÁRIO REPETIDO, e o pypdf avisa linha a
            # linha: medido em 06/10/2026, centenas de avisos inúteis no log.
            logging.getLogger("pypdf").setLevel(logging.ERROR)
            leitor = PdfReader(str(caminho))
            texto = " ".join((p.extract_text() or "") for p in leitor.pages[:8])
        except Exception as erro:                       # noqa: BLE001 — vai ao dossiê
            partes.append(f"[anexo {nome}: não abriu ({type(erro).__name__})]")
            continue
        partes.append(f"--- anexo: {nome}\n{' '.join(texto.split())}")
    return "\n".join(partes)[:limite]


def candidatos(con: sqlite3.Connection) -> list[dict]:
    """Expediente em RECEBIDO sem tarefa aberta ligada."""
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT e.* FROM expedientes e
            WHERE e.stage = 'RECEBIDO'
              AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.linked_expediente_id = e.id
                                 AND t.status NOT IN ('CONCLUIDA','CANCELADA'))
            ORDER BY e.received_at, e.id""")]


def dossie(con, e: dict) -> str:
    return "\n".join([
        f"Protocolo interno: {e.get('internal_protocol') or '—'}",
        f"Recebido em: {e.get('received_at') or '—'} pelo {e.get('source') or '—'}",
        f"Remetente: {e.get('sender') or '—'}",
        f"Assunto: {e.get('subject') or '—'}",
        f"Categoria anotada no balcão: {e.get('category') or '—'}; "
        f"setor anotado: {e.get('sector') or '—'}",
        f"Observação do balcão: {e.get('notes') or '—'}",
        "", texto_dos_anexos(con, e["id"])])


def mascarar(texto: str) -> tuple[str, dict[str, str]]:
    """A MESMA barreira (`ajuda_privacidade`), guardando o caminho de volta.

    O que sai para a IA sai mascarado, como sempre. A volta existe porque a
    TAREFA fica dentro da casa: medido em 06/10/2026, a primeira rodada escreveu
    «[PESSOA_02]» na tarefa de quem ia emitir a certidão — e quem cumpre precisa
    do nome. O mapa vive só durante a triagem; não é gravado.
    """
    from ajuda_privacidade import _conferir_residuos, _Sanitizador
    s = _Sanitizador()
    originais: dict[str, str] = {}
    marcar = s.marcador

    def marcador(tipo, valor):
        m = marcar(tipo, valor)
        originais.setdefault(m, str(valor))
        return m
    s.marcador = marcador
    seguro = s.sanitizar(texto, nomes_livres=True)
    _conferir_residuos(seguro)
    return seguro, originais


def desmascarar(valor, originais: dict[str, str]):
    """Põe de volta os nomes nas respostas da IA (texto, ou dict de textos)."""
    if isinstance(valor, dict):
        return {k: desmascarar(v, originais) for k, v in valor.items()}
    if isinstance(valor, list):
        return [desmascarar(v, originais) for v in valor]
    if not isinstance(valor, str):
        return valor
    for marca, original in originais.items():
        valor = valor.replace(marca, original).replace(marca.strip("[]"), original)
    return valor


def _hash(texto: str) -> str:
    return hashlib.sha256((INSTRUCAO + "\n" + texto).encode("utf-8")).hexdigest()


def _ler_json(texto: str) -> dict:
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        raise ValueError("a resposta não trouxe JSON")
    d = json.loads(m.group(0))
    if d.get("tipo") not in TIPOS:
        raise ValueError(f"tipo desconhecido: {d.get('tipo')!r}")
    if d.get("setor") not in SETORES_VALIDOS:
        d["setor"] = "GESTAO"
    return d


def _prazo(e: dict, r: dict) -> str | None:
    """O prazo da tarefa: o anotado no balcão; senão a data do documento; senão
    os dias contados do recebimento. Prazo inventado é pior que prazo nenhum."""
    if e.get("deadline_date"):
        return str(e["deadline_date"])[:10]
    if r.get("data_limite") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r["data_limite"])):
        return r["data_limite"]
    dias = r.get("prazo_dias")
    try:
        inicio = date.fromisoformat(str(e.get("received_at") or "")[:10])
    except ValueError:
        return None
    if not isinstance(dias, int) or dias <= 0:
        return None
    if r.get("dias_uteis"):
        from ri_schema import soma_dias_uteis
        return soma_dias_uteis(inicio, dias).isoformat()
    return (inicio + timedelta(days=dias)).isoformat()


_PRIORIDADE = {"ALTA": "ALTA", "MEDIA": "MEDIA", "BAIXA": "BAIXA"}


def _assunto(t: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (t or "").upper())


#: O CNPJ da própria serventia aparece em todo ofício e não se pesquisa.
#   Vazio desde 09/10/2026 (sanitização): lido de `settings.serventia_cnpj`
#   em `pesquisa_nos_indices` — ver `_cnpj_da_serventia`.
CNPJ_DA_SERVENTIA = ""
_DOCUMENTO = re.compile(r"\b(\d{3}\.?\d{3}\.?\d{3}-?\d{2}|\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})\b")


def _cnpj_da_serventia(con: sqlite3.Connection) -> str:
    """Os 14 dígitos de `settings.serventia_cnpj` (ou a reserva vazia). Só lê."""
    try:
        r = con.execute("SELECT value FROM settings WHERE key='serventia_cnpj'").fetchone()
    except sqlite3.Error:
        r = None
    digitos = "".join(ch for ch in str((r[0] if r else "") or "") if ch.isdigit())
    return digitos or CNPJ_DA_SERVENTIA


def pesquisa_nos_indices(con: sqlite3.Connection, texto: str) -> list[str]:
    """Todo CPF/CNPJ válido citado no expediente, procurado nos índices do RI.

    NASCEU DO EXPEDIENTE 7 (06/10/2026): a COGEX pergunta se há imóvel em nome
    de uma massa liquidanda, pelo CNPJ — busca que o balcão faria à mão e que o
    agente faz na triagem. Só o DOCUMENTO, que não tem homônimo; o nome fica
    para quem cumpre, porque busca por nome erra para os dois lados.
    """
    from cpf_cnpj import cnpj_valido, cpf_valido, so_digitos
    vistos, saida = set(), []
    proprio = _cnpj_da_serventia(con)
    for bruto in _DOCUMENTO.findall(texto or ""):
        doc = so_digitos(bruto)
        if doc in vistos or (proprio and doc == proprio) or len(set(doc)) == 1:
            continue
        if not (cpf_valido(doc) if len(doc) == 11 else cnpj_valido(doc)):
            continue
        vistos.add(doc)
        achados = con.execute(
            """SELECT DISTINCT m.numero, COALESCE(p.proprietario_ativo, 0)
                 FROM ri_partes p JOIN ri_matriculas m ON m.id = p.matricula_id
                WHERE p.documento_numero = ? ORDER BY m.numero""", (doc,)).fetchall()
        if achados:
            fichas = ", ".join(f"{n}{' (proprietário hoje)' if ativo else ''}"
                               for n, ativo in achados[:20])
            saida.append(f"{bruto}: aparece em {len(achados)} matrícula(s) — {fichas}")
        else:
            saida.append(f"{bruto}: nenhuma matrícula com este documento nos índices do RI")
    return saida


def _corpo(e: dict, r: dict, prazo: str | None, hoje: date) -> str:
    corpo = [f"Triagem do agente gestor ({hoje:%d/%m/%Y}) — confira no expediente.",
             "", f"O que é: {r.get('resumo') or '—'}",
             "", f"O que fazer: {r.get('o_que_fazer') or '—'}"]
    if r.get("quem_decide") == "OFICIAL":
        corpo += ["", "Decisão do oficial: leve a ele antes de cumprir ou responder."]
    corpo += ["", f"Prazo: {datetime.fromisoformat(prazo):%d/%m/%Y}" if prazo
              else "Prazo: o documento não diz."]
    if r.get("pesquisa"):
        corpo += ["", "Pesquisa do agente nos índices do RI (por documento; a busca por "
                  "nome fica com quem cumpre):"] + [f"  - {x}" for x in r["pesquisa"]]
    if r.get("rascunho_resposta"):
        corpo += ["", "Rascunho de resposta (revisar antes de mandar):",
                  str(r["rascunho_resposta"])]
    return "\n".join(corpo)


def despachar(con: sqlite3.Connection, e: dict, r: dict, hoje: date) -> int | None:
    """Cria a tarefa do expediente que pede algo. Devolve o id, ou None (ciência)."""
    import gestor_rotina as GR
    if r["tipo"] == "CIENCIA":
        return None
    # O MESMO OFÍCIO CHEGA DUAS VEZES PELO MALOTE (06/10/2026: a DECISÃO-COGEx
    # 1635/2026 entrou como expedientes 7 e 8). A segunda cópia não abre outra
    # tarefa: fica anotada na que já existe.
    for tid, assunto in con.execute(
            """SELECT t.id, x.subject FROM tasks t JOIN expedientes x
                   ON x.id = t.linked_expediente_id
                WHERE t.source_type = 'EXPEDIENTE' AND x.id <> ?
                  AND t.status NOT IN ('CONCLUIDA','CANCELADA')""", (e["id"],)).fetchall():
        if _assunto(assunto) and _assunto(assunto) == _assunto(e.get("subject")):
            GR._historico(con, tid, "NOTA", nota=f"O mesmo expediente chegou de novo "
                          f"({e.get('internal_protocol') or e['id']}); não abri outra tarefa.")
            return tid
    responsaveis = GR.inferir_responsaveis(con)
    # O SETOR É O DO ASSUNTO, e não o de quem decide: a primeira versão mandava
    # ao oficial todo item marcado «quem decide: oficial», e o mandado de
    # averbação do Registro Civil foi parar na mesa dele (06/10/2026). Quem
    # cumpre é o setor; a tarefa diz quando é preciso levar ao oficial.
    setor = r["setor"]
    dono, substituto = GR.escolher_responsavel(con, responsaveis, setor)
    prazo = _prazo(e, r)
    prioridade = _PRIORIDADE.get(r.get("urgencia"), "MEDIA")
    if prazo and prazo <= (hoje + timedelta(days=2)).isoformat():
        prioridade = "CRITICA"
    agora = datetime.now().isoformat(timespec="seconds")
    # SEM EXIGIR EVIDÊNCIA (hotfix de 06/10/2026, ordem do oficial: «tire a regra
    # de exigir evidencia para todas as tarefas»).
    titulo = f"[Expediente {e.get('internal_protocol') or e['id']}] {e.get('subject') or ''}"
    cur = con.execute(
        """INSERT INTO tasks (source_type, source_ref, title, description, sector,
               priority, status, start_date, due_date, assigned_user_id, backup_user_id,
               linked_expediente_id, evidence_required, created_at, updated_at)
           VALUES ('EXPEDIENTE', ?, ?, ?, ?, ?, 'ABERTA', ?, ?, ?, ?, ?, 0, ?, ?)""",
        (e.get("internal_protocol") or str(e["id"]), titulo[:200], _corpo(e, r, prazo, hoje),
         GR.NOME_DO_SETOR.get(setor, setor), prioridade, hoje.isoformat(), prazo,
         dono, substituto, e["id"], agora, agora))
    GR._historico(con, cur.lastrowid, "CRIADA",
                  nota="Aberta pela triagem do agente gestor, ligada ao expediente.")
    return int(cur.lastrowid)


def triar_pendentes(con: sqlite3.Connection, pasta_dados: Path, hoje: date | None = None,
                    *, teto: int = TETO_POR_DIA, conversar=None) -> dict:
    """Lê e despacha o que chegou. FALA COM A REDE, fora de transação."""
    import agente_provedores as AP
    conversar = conversar or AP.conversar
    hoje = hoje or date.today()
    con.row_factory = sqlite3.Row
    init_schema(con)
    # A DISTRIBUIÇÃO DO OFICIAL ANTES DA PRIMEIRA TAREFA: numa casa em que a
    # conferência ainda não rodou, a triagem não saberia de quem é cada setor.
    import gestor_rotina as GR
    from gestor_schema import init_gestor_schema
    init_gestor_schema(con)
    GR.aplicar_distribuicao(con)
    con.commit()
    provedor = next((p for p in PROVEDORES if AP.tem_chave(pasta_dados, p)), None)
    if provedor is None:
        return {"triados": 0, "sem_chave": PROVEDORES[0]}
    feitos = con.execute("SELECT count(*) FROM ge_triagens WHERE lido_em LIKE ?",
                         (hoje.isoformat() + "%",)).fetchone()[0]
    triados = tarefas = erros = 0
    for e in candidatos(con):
        if feitos + triados + erros >= teto:
            break
        texto = dossie(con, e)
        h = _hash(texto)
        seguro, originais = mascarar(texto)
        if con.execute("""SELECT 1 FROM ge_triagens WHERE expediente_id=? AND hash_dossie=?
                             AND erro IS NULL""", (e["id"], h)).fetchone():
            continue
        agora = datetime.now().isoformat(timespec="seconds")
        try:
            resposta = conversar(pasta_dados, provedor=provedor, sistema=INSTRUCAO,
                                 conversa=[{"tipo": "user", "texto": seguro}],
                                 ferramentas=[], modelo=None,
                                 maximo_de_saida=MAXIMO_DE_SAIDA)
            r = desmascarar(_ler_json(resposta.get("texto") or ""), originais)
            if r["tipo"] != "CIENCIA":
                r["pesquisa"] = pesquisa_nos_indices(con, texto)
        except Exception as erro:                       # noqa: BLE001 — vai à tabela
            con.execute(
                """INSERT OR REPLACE INTO ge_triagens (expediente_id, hash_dossie, lido_em,
                       provedor, erro) VALUES (?,?,?,?,?)""",
                (e["id"], h, agora, provedor, f"{type(erro).__name__}: {str(erro)[:300]}"))
            con.commit()
            erros += 1
            continue
        try:
            con.execute("BEGIN IMMEDIATE")
            tarefa = despachar(con, e, r, hoje)
            con.execute(
                """INSERT OR REPLACE INTO ge_triagens (expediente_id, hash_dossie, lido_em,
                       provedor, modelo, resultado_json, tarefa_id) VALUES (?,?,?,?,?,?,?)""",
                (e["id"], h, agora, provedor, resposta.get("modelo"),
                 json.dumps(r, ensure_ascii=False), tarefa))
            con.commit()
        except Exception:
            con.rollback()
            raise
        triados += 1
        tarefas += tarefa is not None
    return {"triados": triados, "tarefas": tarefas, "erros": erros, "provedor": provedor}


def para_ciencia(con: sqlite3.Connection) -> list[dict]:
    """As circulares que o agente leu e que só pedem ciência — para o despacho."""
    if not _tem_tabela(con, "ge_triagens"):
        return []
    saida = []
    for eid, proto, assunto, resultado in con.execute(
            """SELECT e.id, e.internal_protocol, e.subject, g.resultado_json
                 FROM ge_triagens g JOIN expedientes e ON e.id = g.expediente_id
                WHERE g.erro IS NULL AND e.stage = 'RECEBIDO'
                  AND g.id = (SELECT max(id) FROM ge_triagens WHERE expediente_id = e.id
                                 AND erro IS NULL)"""):
        r = json.loads(resultado or "{}")
        if r.get("tipo") == "CIENCIA":
            saida.append({"id": eid, "protocolo": proto, "assunto": assunto,
                          "resumo": r.get("resumo") or ""})
    return saida
