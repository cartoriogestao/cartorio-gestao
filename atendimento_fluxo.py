"""A ficha de trabalho reúne fatos nativos; não cria outro protocolo legal."""
from __future__ import annotations

import hashlib
import json
from datetime import date

from bd_nativo import banco
import caixa_schema as CX
import ri_pedidos as RI

SCHEMA = (
    ("at_responsaveis", """CREATE TABLE IF NOT EXISTS at_responsaveis (
        protocolo_id bigint PRIMARY KEY REFERENCES cx_protocolos(id),
        usuario_id bigint NOT NULL REFERENCES users(id),
        assumido_em text NOT NULL, iniciado_em text, alterado_por bigint NOT NULL REFERENCES users(id)
    )"""),
    ("at_exigencia_itens", """CREATE TABLE IF NOT EXISTS at_exigencia_itens (
        protocolo_id bigint NOT NULL REFERENCES cx_protocolos(id),
        origem text NOT NULL, nota_id bigint NOT NULL, ordem bigint NOT NULL,
        texto_hash text NOT NULL, estado text NOT NULL
            CHECK (estado IN ('APRESENTADO','CONFERIDO','PENDENTE')),
        anexo_id bigint REFERENCES attachments(id), observacao text NOT NULL DEFAULT '',
        atualizado_em text NOT NULL, usuario_id bigint NOT NULL REFERENCES users(id),
        PRIMARY KEY (protocolo_id, origem, nota_id, ordem)
    )"""),
)


class FluxoError(ValueError):
    pass


def versao_item(item):
    return hashlib.sha256(json.dumps(item,sort_keys=True,default=str).encode()).hexdigest()[:24] if item else ""


def init_schema(con):
    bd = banco(con)
    for nome, sql in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(sql)


def _protocolo(con, pid):
    p = banco(con).um("SELECT * FROM cx_protocolos WHERE id=%s", (int(pid),))
    if not p:
        raise FluxoError("Atendimento não encontrado.")
    return p


def responsavel(con, pid):
    return banco(con).um("""SELECT r.*, u.full_name FROM at_responsaveis r
        JOIN users u ON u.id=r.usuario_id WHERE r.protocolo_id=%s""", (int(pid),))


def anotacoes_anteriores(con, p):
    """Conserva a atribuição textual antiga, sem vinculá-la a um usuário por nome."""
    return banco(con).ler("""SELECT tabela,responsavel,texto,ate FROM ex_anotacoes
        WHERE (tabela='cx_protocolos' AND item_id=%s)
           OR (tabela='ri_protocolos' AND item_id=%s) ORDER BY id""",
        (int(p["id"]),p.get("ri_protocolo_id") or -1))


def assumir(con, pid, *, usuario_id, autor_id, agora, gerencia=False):
    bd = banco(con)
    p = _protocolo(bd, pid)
    bd.travar(f"atendimento.responsavel.{int(pid)}")
    atual = responsavel(bd, pid)
    if p["situacao"] in ("ENTREGUE", "CANCELADO"):
        raise FluxoError("Este atendimento está encerrado.")
    if not gerencia and int(usuario_id) != int(autor_id):
        raise FluxoError("Você pode assumir o próprio trabalho; a gestão distribui para outra pessoa.")
    if atual and int(atual["usuario_id"]) != int(autor_id) and not gerencia:
        raise FluxoError("Outro escrevente cuida deste pedido. Peça a redistribuição à gestão.")
    u = bd.um("SELECT id, role, active FROM users WHERE id=%s", (int(usuario_id),))
    if not u or not u["active"] or u["role"] not in ("ADMIN", "MANAGER", "USER"):
        raise FluxoError("Escolha um escrevente ativo autorizado a trabalhar.")
    bd.escrever("""INSERT INTO at_responsaveis
        (protocolo_id,usuario_id,assumido_em,iniciado_em,alterado_por) VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (protocolo_id) DO UPDATE SET usuario_id=EXCLUDED.usuario_id,
        assumido_em=EXCLUDED.assumido_em, iniciado_em=EXCLUDED.iniciado_em,
        alterado_por=EXCLUDED.alterado_por""",
        (int(pid), int(usuario_id), agora, agora if int(usuario_id)==int(autor_id) else None, int(autor_id)))
    return {"antes": atual["usuario_id"] if atual else None, "depois": int(usuario_id)}


def etapa(con, p, *, hoje=None):
    bd = banco(con)
    if p["situacao"] in ("ENTREGUE", "CANCELADO"):
        return (p["situacao"], "Entregue" if p["situacao"] == "ENTREGUE" else "Cancelado")
    if p.get("tipo") == "ORCAMENTO":
        return "ORCAMENTO", "Só orçamento"
    if p.get("ri_protocolo_id"):
        r = bd.um("SELECT * FROM ri_protocolos WHERE id=%s", (p["ri_protocolo_id"],))
        if r:
            if r["situacao"] not in ("ABERTO", "DEVOLVIDO"):
                return "RI_ENCERRADA", f"Prenotação {str(r['situacao']).lower()} - conferir entrega"
            qq = RI.qualificacoes_de(bd, r["id"])
            e = RI.etapa(r, qq[-1] if qq else None, (hoje or date.today()).isoformat())
            nome = RI.ROTULO_DA_ETAPA[e]
            if e == "A_QUALIFICAR" and qq and qq[-1]["resultado"] == "NEGATIVA":
                return "A_REQUALIFICAR", "A requalificar"
            dono = responsavel(bd, p["id"])
            if e == "A_QUALIFICAR" and dono and dono.get("iniciado_em"):
                nome = "Em qualificação"
            return e, nome
    import caixa_exigencia as EX
    if EX.exigencias_abertas_do_protocolo(bd, p["id"]):
        return "EM_EXIGENCIA", "Aguardando cumprimento"
    return "RECEBIDO", "Recebido para encaminhar"


def listar(con, *, busca="", usuario_id=None, sem_responsavel=False, pagina=1,
           historico=False, atribuicao="", filtro_etapa=""):
    """Paginação antes de montar fichas: não varre o acervo para abrir o balcão."""
    bd = banco(con)
    onde, args = ["1=1"], []
    if not historico and not busca:
        onde += ["p.situacao NOT IN ('ENTREGUE','CANCELADO')", "COALESCE(p.origem,'')<>'EOFICIO'"]
    if busca:
        termo = "%" + str(busca).strip()[:120] + "%"
        onde.append("""(p.numero ILIKE %s OR p.interessado ILIKE %s OR p.assunto ILIKE %s
            OR r.numero::text ILIKE %s OR r.matricula_numero ILIKE %s)""")
        args += [termo] * 5
    if usuario_id is not None:
        onde.append("a.usuario_id=%s"); args.append(int(usuario_id))
    if sem_responsavel:
        onde.append("a.usuario_id IS NULL")
    if atribuicao in ("RI", "NOTAS", "FIRMAS", "RCPN", "RTD", "RCPJ", "PROTESTO", "OUTROS"):
        onde.append("p.atribuicao=%s"); args.append(atribuicao)
    base = """ FROM cx_protocolos p LEFT JOIN ri_protocolos r ON r.id=p.ri_protocolo_id
        LEFT JOIN at_responsaveis a ON a.protocolo_id=p.id """
    where = " WHERE " + " AND ".join(onde)
    total = int(bd.valor("SELECT count(*)" + base + where, args) or 0)
    pagina = min(max(1, int(pagina)), max(1, (total + 39) // 40))
    rows = bd.ler("SELECT p.*" + base + where + """
        ORDER BY CASE WHEN r.data_limite IS NULL THEN 1 ELSE 0 END,
                 r.data_limite, r.numero, p.data_abertura, p.id LIMIT 40 OFFSET %s""",
        [*args, (pagina - 1) * 40])
    for p in rows:
        p["etapa"], p["etapa_nome"] = etapa(bd, p)
        p["responsavel"] = responsavel(bd, p["id"])
        p["anotacoes_anteriores"] = anotacoes_anteriores(bd, p)
    # O filtro de etapa é uma lente sobre fatos, não uma segunda coluna editável.
    # Nunca filtrar após LIMIT: o chamador usa a fila específica nativa do RI.
    return {"pedidos": rows, "total": total, "pagina": pagina, "paginas": max(1, (total + 39)//40)}


def financeiro(p):
    def valor(v):
        if v in (None, ""):
            return None
        try:
            return CX.centavos(v)
        except (ValueError, TypeError):
            return None
    total, pago = valor(p.get("valor_total")), valor(p.get("valor_pago"))
    return {"total": total, "pago": pago, "saldo": max(0, total - (pago or 0)) if total is not None else None,
            "rotulo": "Só cálculo" if p.get("tipo") == "ORCAMENTO" else (
                "Gratuito" if p.get("gratuito") else "Pago" if p["situacao"] == "PAGO" else
                "A receber" if p["situacao"] == "A_PAGAR" else "A conferir")}


def ficha(con, pid):
    bd = banco(con)
    p = _protocolo(bd, pid)
    e, nome = etapa(bd, p)
    ri = bd.um("SELECT * FROM ri_protocolos WHERE id=%s", (p["ri_protocolo_id"],)) if p.get("ri_protocolo_id") else None
    import protocolo_documentos as DOC
    import caixa_exigencia as EX
    docs = DOC.documentos(bd, pid)
    import ri_documentos as RIDOC
    anexos_ri = RIDOC.documentos_de(bd,"RI_PROTOCOLO",ri["id"]) if ri else []
    notas = bd.ler("SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=%s ORDER BY id DESC", (ri["id"],)) if ri else []
    exigencias = EX.exigencias_abertas_do_protocolo(bd, pid)
    controles = bd.ler("SELECT * FROM at_exigencia_itens WHERE protocolo_id=%s", (int(pid),))
    for n in exigencias:
        n["controle"] = []
        for i, texto in enumerate(n["itens"], 1):
            h = hashlib.sha256(texto.encode()).hexdigest()
            atual = next((x for x in controles if x["origem"]==n["origem"] and x["nota_id"]==n["id"]
                          and x["ordem"]==i and x["texto_hash"]==h), None)
            n["controle"].append({"ordem": i, "texto": texto, "atual": atual,"versao":versao_item(atual)})
    depositos = bd.ler("""SELECT * FROM cx_depositos WHERE protocolo_id=%s
        OR ri_protocolo_id=%s ORDER BY id DESC""", (int(pid),ri["id"] if ri else -1))
    return {"p": p, "etapa": e, "etapa_nome": nome, "ri": ri,
            "responsavel": responsavel(bd, pid), "financeiro": financeiro(p),
            "anotacoes_anteriores": anotacoes_anteriores(bd, p),
            "documentos": docs, "anexos_ri": anexos_ri, "notas": notas, "exigencias": exigencias,
            "qualificacoes": RI.qualificacoes_de(bd, ri["id"]) if ri else [],
            "itens": bd.ler("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s ORDER BY id", (int(pid),)),
            "depositos": depositos,
            "recibos": bd.ler("SELECT id,numero,ano,data_emissao,valor_total FROM cx_recibos WHERE protocolo_id=%s ORDER BY id DESC", (int(pid),))}


def conferir_item(con, pid, *, origem, nota_id, ordem, estado, anexo_id, observacao,
                  usuario_id, agora, versao_esperada=""):
    bd = banco(con)
    p = _protocolo(bd, pid)
    if p["situacao"] in ("ENTREGUE", "CANCELADO"):
        raise FluxoError("O atendimento está encerrado.")
    if estado not in ("APRESENTADO", "CONFERIDO", "PENDENTE"):
        raise FluxoError("Situação de cumprimento inválida.")
    import caixa_exigencia as EX
    n = next((x for x in EX.exigencias_abertas_do_protocolo(bd, pid)
              if x["origem"] == origem and x["id"] == int(nota_id)), None)
    if not n or not 1 <= int(ordem) <= len(n["itens"]):
        raise FluxoError("A exigência não está aberta neste atendimento.")
    if anexo_id:
        a = bd.um("SELECT entity_type,entity_id,retirado_em FROM attachments WHERE id=%s", (int(anexo_id),))
        if a and a.get("retirado_em"):
            raise FluxoError("O documento foi retirado. Escolha uma evidência ativa.")
        if not a or not ((a["entity_type"] == "PROTOCOLO" and a["entity_id"] == int(pid)) or
                         (a["entity_type"] == "RI_PROTOCOLO" and a["entity_id"] == p.get("ri_protocolo_id"))):
            raise FluxoError("O documento precisa pertencer a este atendimento ou à sua prenotação.")
    if estado in ("APRESENTADO", "CONFERIDO") and not anexo_id and len(observacao.strip()) < 10:
        raise FluxoError("Vincule o documento ou descreva a evidência da conferência (mínimo 10 caracteres).")
    texto = n["itens"][int(ordem)-1]
    bd.travar(f"atendimento.exigencia.{int(pid)}.{origem}.{int(nota_id)}.{int(ordem)}")
    atual=bd.um("""SELECT * FROM at_exigencia_itens
        WHERE protocolo_id=%s AND origem=%s AND nota_id=%s AND ordem=%s""",
        (int(pid),origem,int(nota_id),int(ordem)))
    if atual and atual["texto_hash"]==hashlib.sha256(texto.encode()).hexdigest() and versao_item(atual)!=versao_esperada:
        raise FluxoError("Este item foi atualizado por outra conferência. Reabra a ficha antes de continuar.")
    bd.escrever("""INSERT INTO at_exigencia_itens
        (protocolo_id,origem,nota_id,ordem,texto_hash,estado,anexo_id,observacao,atualizado_em,usuario_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (protocolo_id,origem,nota_id,ordem) DO UPDATE SET
        texto_hash=EXCLUDED.texto_hash,estado=EXCLUDED.estado,anexo_id=EXCLUDED.anexo_id,
        observacao=EXCLUDED.observacao,atualizado_em=EXCLUDED.atualizado_em,usuario_id=EXCLUDED.usuario_id""",
        (int(pid), origem, int(nota_id), int(ordem), hashlib.sha256(texto.encode()).hexdigest(), estado,
         int(anexo_id) if anexo_id else None, observacao.strip()[:2000], agora, int(usuario_id)))
    # A conferência de um item não altera prazo, nota ou qualificação: a decisão
    # formal usa a rotina nativa da atribuição, com as validações dela.
    return {"origem": origem, "nota": int(nota_id), "ordem": int(ordem), "estado": estado}
