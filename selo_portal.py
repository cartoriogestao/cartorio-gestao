"""O que a casa deve ao Portal do Selo: o pedido de cancelamento e o ressarcimento.

    «Selo cancelado/inutilizado: o oficial comunica à mão e pede o cancelamento
     de TODOS.» · «no portal do selo é preciso enviar o comprovante da
     gratuidade PARA CADA SELO»                      — LG07, 19/10/2026

DUAS DÍVIDAS, UMA FORMA SÓ
    As duas coisas são remessas ao Tribunal: um conjunto de selos que sai de
    uma vez e, depois, alguém diz «mandei, em tal dia, com tal protocolo».
    Por isso são as mesmas duas tabelas (`sd_portal_remessas` e
    `sd_portal_itens`), com `tipo` CANCELAMENTO ou GRATUIDADE. Um selo entra em
    UMA remessa de cada tipo (`UNIQUE (tipo, selo_id)`): pedir duas vezes o
    cancelamento do mesmo selo, ou subir duas vezes o mesmo comprovante, é o
    erro que a chave impede — e não a memória de quem gerou.

    A remessa nasce RASCUNHO (`comunicado_em` vazio). Rascunho se descarta
    (período errado, selo que faltava); comunicada, não se desfaz: é o
    registro de que o Tribunal foi avisado.

NÃO HÁ API DO PORTAL NO CÓDIGO, E POR ISSO NÃO HÁ REDE AQUI
    O `selador.py` documenta o contrato do aparelho, que GERA selo (inclusive
    os de ato de cancelamento, que são outra coisa). Nenhum endpoint de pedir
    cancelamento de selo nem de subir comprovante de ressarcimento existe nele.
    O que este módulo faz é o que a especificação manda nesse caso: a lista, o
    ofício e o pacote; quem comunica é o oficial, pelo canal oficial (Malote
    Digital — Código de Normas do MA, art. 127 — ou o próprio Portal).

O CANCELADO É O DO RAZÃO
    `sd_selos.cancelado_em` é preenchido pelo cancelamento da certidão
    (`cancelamento_certidao.concluir`), pelo `selador_cliente.
    registrar_cancelamento` e pela carga do acervo. A régua do que é cancelado
    é a de `selos_emitidos` (`SEM.CANCELADO`), e não uma terceira: 79 selos do
    acervo foram cancelados com texto vazio em vez de NULL, e duas réguas
    discordariam justamente neles.

    O AVISO conta a partir de `settings.selo_cancelamento_comunicar_desde`
    (sem ela, 19/10/2026, a data da ordem). O passado não vira aviso sozinho —
    não se sabe se os 79 do E-Ofício foram pedidos —, mas a LISTA aceita
    qualquer período: o oficial pode pedir os antigos de uma vez.

O GRATUITO PRECISA DE DUAS PEÇAS, E UM ARQUIVO PODE TRAZER AS DUAS
    O Portal pede, por selo, o comprovante da gratuidade (declaração de
    pobreza, decisão, documento da gratuidade legal…) E a cópia da certidão
    do ato praticado. O comprovante continua morando onde o aviso do
    escrevente o procura (`attachments`, entidade `SELO_GRATUIDADE`, por
    `gratuidade_comprovante.guardar`) — guardá-lo daqui também apaga o aviso
    vermelho dele. A cópia da certidão vai em entidade própria
    (`SELO_GRATUIDADE_CERTIDAO`): sozinha, ela não é o comprovante e não pode
    apagar aquele aviso.

    `sd_gratuidade_pecas` diz o que cada arquivo é. «Geralmente se junta tudo
    num PDF» (o oficial, LX16): o comprovante pode ser marcado AMBOS. Anexo de
    comprovante sem linha aqui é o que sempre foi — COMPROVANTE —, e é assim
    que os guardados antes desta versão entram na conta sem migração.

O PACOTE É UM PDF POR SELO, COM O NÚMERO DO SELO NO NOME
    É o que se sobe no Portal, um a um. As peças do selo se juntam num PDF só
    (`pymupdf`, já exigido no `requirements.txt`), comprovante primeiro e
    certidão depois; imagem vira página. Vai junto `lista.csv`, para conferir
    o que subiu — sem o nome de quem obteve o selo: o Tribunal não precisa
    dele, e o pacote sai de casa (LGPD, minimização).

BASE NORMATIVA (Prov. COGEX 28/2026, o PDF em `referencia/` manda)
    Art. 133 (selo de ato isento ou gratuito, de uso obrigatório); art. 134
    (gestão e controle dos selos é dever pessoal do delegatário); art. 135
    (inconsistência ou erro no selo comunicado imediatamente à Corregedoria,
    por canal oficial, com registro para auditoria); art. 127 (Malote Digital,
    o canal oficial); art. 217 (gratuidades com ressarcimento pelo FERC) e
    art. 151, § 2º (ressarcimento ao RCPN). Prov. CNJ 149/2023: conferir no
    texto oficial — não está em `referencia/`.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from pathlib import Path
from typing import Any

import gratuidade_comprovante as GC
import selos_emitidos as SEM
from bd_nativo import banco

CANCELAMENTO = "CANCELAMENTO"
GRATUIDADE = "GRATUIDADE"
TIPOS = (CANCELAMENTO, GRATUIDADE)

DESDE_PADRAO = "2026-10-19"
CHAVE_DO_DESDE = "selo_cancelamento_comunicar_desde"

ENTIDADE_CERTIDAO = "SELO_GRATUIDADE_CERTIDAO"
COMPROVANTE, CERTIDAO, AMBOS = "COMPROVANTE", "CERTIDAO", "AMBOS"
PECAS = {
    COMPROVANTE: "Comprovante da gratuidade",
    CERTIDAO: "Cópia da certidão do ato",
    AMBOS: "Um PDF com os dois (comprovante + certidão do ato)",
}
#: O que se escolhe como comprovante. A lista é de documento, e não de
#: fundamento: o fundamento legal é escolha do LX16, no ato.
TIPOS_DE_COMPROVANTE = {
    "DECLARACAO_POBREZA": "Declaração de pobreza (hipossuficiência)",
    "DECISAO_JUDICIAL": "Decisão judicial ou requisição do juiz",
    "REQUISICAO_MP": "Requisição do Ministério Público",
    "REQUISICAO_DEFENSORIA": "Requisição da Defensoria Pública",
    "GRATUIDADE_LEGAL": "Gratuidade da lei (documento que a prova)",
    "OUTRO": "Outro documento",
}

SITUACOES_DA_GRATUIDADE = {
    "FALTAM_OS_DOIS": "Falta o comprovante e a certidão do ato",
    "FALTA_COMPROVANTE": "Falta o comprovante da gratuidade",
    "FALTA_CERTIDAO": "Falta a cópia da certidão do ato",
    "PRONTO": "Pronto para o pacote",
    "NO_PACOTE": "No pacote, ainda não enviado",
    "ENVIADO": "Enviado ao Portal",
}
FALTANDO = ("FALTAM_OS_DOIS", "FALTA_COMPROVANTE", "FALTA_CERTIDAO")

SCHEMA: tuple[tuple[str, str], ...] = (
    ("sd_portal_remessas", """
        CREATE TABLE IF NOT EXISTS sd_portal_remessas (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            tipo TEXT NOT NULL CHECK (tipo IN ('CANCELAMENTO', 'GRATUIDADE')),
            inicio TEXT NOT NULL,
            fim TEXT NOT NULL,
            gerado_em TEXT NOT NULL,
            gerado_por TEXT NOT NULL DEFAULT '',
            comunicado_em TEXT NOT NULL DEFAULT '',
            comunicado_por TEXT NOT NULL DEFAULT '',
            protocolo TEXT NOT NULL DEFAULT ''
        )"""),
    ("sd_portal_itens", """
        CREATE TABLE IF NOT EXISTS sd_portal_itens (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            remessa_id bigint NOT NULL REFERENCES sd_portal_remessas(id),
            tipo TEXT NOT NULL CHECK (tipo IN ('CANCELAMENTO', 'GRATUIDADE')),
            selo_id bigint NOT NULL REFERENCES sd_selos(id),
            UNIQUE (tipo, selo_id)
        )"""),
    ("ix_sd_portal_itens_remessa",
     "CREATE INDEX IF NOT EXISTS ix_sd_portal_itens_remessa "
     "ON sd_portal_itens (remessa_id, id)"),
    ("sd_gratuidade_pecas", """
        CREATE TABLE IF NOT EXISTS sd_gratuidade_pecas (
            attachment_id bigint PRIMARY KEY REFERENCES attachments(id),
            selo_id bigint NOT NULL REFERENCES sd_selos(id),
            peca TEXT NOT NULL CHECK (peca IN ('COMPROVANTE', 'CERTIDAO', 'AMBOS')),
            tipo_comprovante TEXT NOT NULL DEFAULT '',
            marcado_em TEXT NOT NULL,
            marcado_por TEXT NOT NULL DEFAULT ''
        )"""),
    ("ix_sd_gratuidade_pecas_selo",
     "CREATE INDEX IF NOT EXISTS ix_sd_gratuidade_pecas_selo "
     "ON sd_gratuidade_pecas (selo_id, attachment_id)"),
)

_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PortalError(ValueError):
    """Recusa com frase de balcão."""


def init_selo_portal_schema(con) -> None:
    """Cria as tabelas e os índices que faltarem — um por um, para a tabela
    que já existe não ficar sem o índice. Depende de `sd_selos` e de
    `attachments`, e por isso vem depois dos dois."""
    bd = banco(con)
    for nome, comando in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(comando)


# ------------------------------------------------------------- o período


def _periodo(inicio: Any, fim: Any) -> tuple[str, str]:
    """Duas datas AAAA-MM-DD, a primeira não depois da segunda. Só calcula."""
    a, b = str(inicio or "").strip(), str(fim or "").strip()
    if not _DATA.match(a) or not _DATA.match(b):
        raise PortalError("Informe o período com as duas datas (início e fim).")
    if a > b:
        raise PortalError("O início do período vem depois do fim.")
    return a, b


def _ate(fim: str) -> str:
    """O fim do dia, nos dois formatos de data do razão («2020-03-19 14:21:03»
    do acervo e «2026-09-01T14:17:06» deste sistema) — o `z` de
    `selos_emitidos`: passa de todo dígito, do espaço e do `T`."""
    return f"{fim}z"


def desde_cancelamento(con) -> str:
    """Desde quando o selo cancelado não comunicado vira aviso. Só LÊ."""
    valor = banco(con).valor("SELECT value FROM settings WHERE key = %s", (CHAVE_DO_DESDE,))
    valor = str(valor or "")[:10]
    return valor if _DATA.match(valor) else DESDE_PADRAO


def descrever_ato(con, linha: dict) -> str:
    """O ato do selo em palavras: o tipo pelo prefixo, a referência e o rótulo
    do ato quando o sistema o conhece. Só LÊ."""
    partes = [SEM.nome_do_tipo(linha.get("numero"))]
    rotulo = GC.rotulo(con, linha.get("tabela"), linha.get("ato_id"))
    if rotulo:
        partes.append(rotulo)
    elif linha.get("tabela") and linha.get("ato_id"):
        partes.append(f"{str(linha['tabela']).replace('_', ' ')} {linha['ato_id']}")
    if str(linha.get("referencia") or "").strip():
        partes.append(str(linha["referencia"]).strip())
    return " – ".join(p for p in partes if p)


# ----------------------------------------------------- os selos cancelados


def cancelados(con, *, inicio: str, fim: str) -> list[dict]:
    """Os selos cancelados no período, com o pé em que está o pedido. Só LÊ.

    `pedido` é NAO_PEDIDO, RASCUNHO (num ofício ainda não comunicado) ou
    COMUNICADO.
    """
    inicio, fim = _periodo(inicio, fim)
    bd = banco(con)
    rows = bd.ler(
        f"""SELECT sd_selos.id, sd_selos.numero, sd_selos.atribuicao, sd_selos.referencia,
                   sd_selos.tabela, sd_selos.ato_id, sd_selos.obtido_em, sd_selos.cancelado_em,
                   sd_selos.cancelado_por, sd_selos.motivo_cancelamento,
                   r.id AS remessa_id, r.comunicado_em AS comunicado_em
              FROM sd_selos
              LEFT JOIN sd_portal_itens i ON i.tipo = %s AND i.selo_id = sd_selos.id
              LEFT JOIN sd_portal_remessas r ON r.id = i.remessa_id
             WHERE {SEM.CANCELADO}
               AND sd_selos.cancelado_em >= %s AND sd_selos.cancelado_em <= %s
             ORDER BY sd_selos.cancelado_em, sd_selos.id""",
        (CANCELAMENTO, inicio, _ate(fim)))
    saida = []
    for r in rows:
        d = dict(r)
        d["ato"] = descrever_ato(con, d)
        d["pedido"] = ("COMUNICADO" if r["comunicado_em"]
                       else "RASCUNHO" if r["remessa_id"] else "NAO_PEDIDO")
        saida.append(d)
    return saida


def nao_comunicados(con) -> dict:
    """Quantos selos cancelados desde o «desde» ainda não foram comunicados ao
    TJMA, e o mais antigo. É o que o aviso do topo mostra. Só LÊ.

    Selo num ofício em RASCUNHO ainda conta: gerar o papel não é comunicar.
    """
    linha = banco(con).um(
        f"""SELECT count(*) AS n, min(sd_selos.cancelado_em) AS mais_antigo
              FROM sd_selos
             WHERE {SEM.CANCELADO} AND sd_selos.cancelado_em >= %s
               AND NOT EXISTS (
                   SELECT 1 FROM sd_portal_itens i
                     JOIN sd_portal_remessas r ON r.id = i.remessa_id
                    WHERE i.tipo = %s AND i.selo_id = sd_selos.id AND r.comunicado_em <> '')""",
        (desde_cancelamento(con), CANCELAMENTO))
    return {"n": int(linha["n"] or 0) if linha else 0,
            "mais_antigo": (linha["mais_antigo"] or "") if linha else ""}


# --------------------------------------------------- os selos gratuitos


def _situacao_da_gratuidade(linha: dict) -> str:
    """A régua da fila, num lugar só. Só calcula."""
    if linha.get("enviado_em"):
        return "ENVIADO"
    if linha.get("remessa_id"):
        return "NO_PACOTE"
    comprovante, certidao = bool(linha.get("tem_comprovante")), bool(linha.get("tem_certidao"))
    if not comprovante and not certidao:
        return "FALTAM_OS_DOIS"
    if not comprovante:
        return "FALTA_COMPROVANTE"
    if not certidao:
        return "FALTA_CERTIDAO"
    return "PRONTO"


def gratuitos(con, *, inicio: str | None = None, fim: str | None = None,
              situacao: str = "", nome: str = "", username: str = "") -> list[dict]:
    """Os selos isentos do período, cada um com o que falta para o Portal. Só LÊ.

    Sem período, vale o «desde» do comprovante (`gratuidade_comprovante.desde`,
    com os incluídos à mão) até hoje — a mesma régua do aviso do escrevente.
    `situacao` FALTANDO junta as três faltas: é a fila «falta comprovante».
    Com `nome`/`username`, só os selos daquela pessoa (a tela do escrevente).
    """
    bd = banco(con)
    incluidos = GC.incluidos(con) if not inicio else []
    inicio = inicio or GC.desde(con)
    fim = fim or "9999-12-31"
    inicio, fim = _periodo(inicio, fim)
    em = ",".join(["%s"] * len(incluidos)) or "NULL"
    rows = bd.ler(
        f"""SELECT sd_selos.id, sd_selos.numero, sd_selos.atribuicao, sd_selos.referencia,
                   sd_selos.tabela, sd_selos.ato_id, sd_selos.obtido_em, sd_selos.obtido_por,
                   EXISTS (SELECT 1 FROM attachments a
                             LEFT JOIN sd_gratuidade_pecas p ON p.attachment_id = a.id
                            WHERE a.entity_type = %s AND a.entity_id = sd_selos.id
                              AND coalesce(p.peca, 'COMPROVANTE') IN ('COMPROVANTE', 'AMBOS'))
                       AS tem_comprovante,
                   EXISTS (SELECT 1 FROM attachments a
                             JOIN sd_gratuidade_pecas p ON p.attachment_id = a.id
                            WHERE a.entity_type IN (%s, %s) AND a.entity_id = sd_selos.id
                              AND p.peca IN ('CERTIDAO', 'AMBOS'))
                       AS tem_certidao,
                   r.id AS remessa_id, r.comunicado_em AS enviado_em
              FROM sd_selos
              LEFT JOIN sd_portal_itens i ON i.tipo = %s AND i.selo_id = sd_selos.id
              LEFT JOIN sd_portal_remessas r ON r.id = i.remessa_id
             WHERE sd_selos.texto ILIKE %s AND {SEM.SEM_CANCELAR}
               AND ((sd_selos.obtido_em >= %s AND sd_selos.obtido_em <= %s)
                    OR sd_selos.id IN ({em}))
             ORDER BY sd_selos.obtido_em, sd_selos.id""",
        (GC.ENTIDADE, GC.ENTIDADE, ENTIDADE_CERTIDAO, GRATUIDADE, GC.MARCA_DO_SELO_ISENTO,
         inicio, _ate(fim), *incluidos))
    alvos = {GC._norm(nome), GC._norm(username)} - {""}
    saida = []
    for r in rows:
        if alvos and GC._norm(r["obtido_por"]) not in alvos:
            continue
        d = dict(r)
        d["situacao"] = _situacao_da_gratuidade(d)
        if situacao == "FALTANDO" and d["situacao"] not in FALTANDO:
            continue
        if situacao and situacao != "FALTANDO" and d["situacao"] != situacao:
            continue
        d["ato"] = descrever_ato(con, d)
        saida.append(d)
    return saida


def pecas(con, selo_id: int) -> list[dict]:
    """Os arquivos de um selo gratuito, cada um com o que ele é. Só LÊ.

    Comprovante primeiro, certidão depois — é a ordem das páginas no pacote.
    """
    return [dict(r) for r in banco(con).ler(
        """SELECT a.id, a.entity_type, a.original_name, a.stored_path, a.uploaded_at,
                  coalesce(p.peca, 'COMPROVANTE') AS peca,
                  coalesce(p.tipo_comprovante, '') AS tipo_comprovante
             FROM attachments a
             LEFT JOIN sd_gratuidade_pecas p ON p.attachment_id = a.id
            WHERE a.entity_type IN (%s, %s) AND a.entity_id = %s
            ORDER BY CASE coalesce(p.peca, 'COMPROVANTE')
                         WHEN 'COMPROVANTE' THEN 0 WHEN 'AMBOS' THEN 1 ELSE 2 END, a.id""",
        (GC.ENTIDADE, ENTIDADE_CERTIDAO, int(selo_id)))]


def _selo_isento(bd, selo_id: int) -> dict:
    r = bd.um("SELECT id, numero, texto FROM sd_selos WHERE id = %s", (int(selo_id),))
    if not r:
        raise PortalError("Selo não encontrado.")
    if "selo isento" not in (r["texto"] or "").lower():
        raise PortalError("Este selo não é de ato gratuito.")
    return r


def _marcar(bd, attachment_id: int, selo_id: int, *, peca: str, tipo_comprovante: str,
            agora: str, usuario: str) -> None:
    bd.escrever(
        """INSERT INTO sd_gratuidade_pecas (attachment_id, selo_id, peca, tipo_comprovante,
                                            marcado_em, marcado_por)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (attachment_id) DO UPDATE SET
               peca = excluded.peca, tipo_comprovante = excluded.tipo_comprovante,
               marcado_em = excluded.marcado_em, marcado_por = excluded.marcado_por""",
        (int(attachment_id), int(selo_id), peca, tipo_comprovante, agora, usuario or ""))


def _conferir_peca(peca: str, tipo_comprovante: str) -> tuple[str, str]:
    peca = str(peca or "").strip().upper()
    tipo = str(tipo_comprovante or "").strip().upper()
    if peca not in PECAS:
        raise PortalError("Diga o que é o arquivo: comprovante, certidão do ato ou os dois.")
    if peca == CERTIDAO:
        return peca, ""
    if tipo not in TIPOS_DE_COMPROVANTE:
        raise PortalError("Escolha o tipo do comprovante (declaração de pobreza, decisão…).")
    return peca, tipo


def guardar_peca(con, selo_id: int, *, peca: str, tipo_comprovante: str = "",
                 nome_arquivo: str, conteudo: bytes, pasta: Path, usuario_id: int | None,
                 usuario: str = "", agora: str) -> int:
    """Guarda um arquivo do selo gratuito e diz o que ele é. ESCREVE.

    O comprovante (ou o PDF com os dois) entra pelo `gratuidade_comprovante.
    guardar`, e o aviso do escrevente some como sempre sumiu. A certidão
    sozinha entra em entidade própria e não mexe nele.
    """
    peca, tipo = _conferir_peca(peca, tipo_comprovante)
    bd = banco(con)
    selo = _selo_isento(bd, selo_id)
    if peca in (COMPROVANTE, AMBOS):
        try:
            aid = GC.guardar(con, int(selo_id), nome_arquivo=nome_arquivo, conteudo=conteudo,
                             pasta=pasta, usuario_id=usuario_id, agora=agora,
                             origem="Portal do Selo")
        except GC.ComprovanteError as erro:
            raise PortalError(str(erro)) from None
    else:
        nome_arquivo = Path(nome_arquivo or "").name
        if not nome_arquivo.lower().endswith(GC.EXTENSOES):
            raise PortalError("Certidão em PDF ou imagem (JPG, PNG).")
        if not conteudo:
            raise PortalError("O arquivo veio vazio.")
        sha = hashlib.sha256(conteudo).hexdigest()
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"{selo['numero']}_certidao_{sha[:10]}{Path(nome_arquivo).suffix.lower()}"
        destino.write_bytes(conteudo)
        aid = int(bd.escrever(
            """INSERT INTO attachments (entity_type, entity_id, original_name, stored_name,
                                        stored_path, sha256, size_bytes, description,
                                        uploaded_by, uploaded_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (ENTIDADE_CERTIDAO, int(selo_id), nome_arquivo, destino.name, str(destino), sha,
             len(conteudo), f"Cópia da certidão do ato do selo {selo['numero']}",
             usuario_id, agora))[0]["id"])
    _marcar(bd, aid, int(selo_id), peca=peca, tipo_comprovante=tipo, agora=agora,
            usuario=usuario)
    return int(aid)


def classificar(con, attachment_id: int, *, peca: str, tipo_comprovante: str = "",
                agora: str, usuario: str = "") -> int:
    """Diz o que um comprovante já guardado é — em geral, que o PDF traz também
    a certidão (AMBOS). Devolve o id do selo. ESCREVE.

    O que entrou como comprovante não vira «só certidão»: isso apagaria o
    comprovante da conta sem tirar o arquivo da entidade em que o aviso do
    escrevente o enxerga. Para isso, guarda-se a certidão como peça nova.
    """
    peca, tipo = _conferir_peca(peca, tipo_comprovante)
    bd = banco(con)
    anexo = bd.um("SELECT id, entity_type, entity_id FROM attachments WHERE id = %s",
                  (int(attachment_id),))
    if not anexo or anexo["entity_type"] not in (GC.ENTIDADE, ENTIDADE_CERTIDAO):
        raise PortalError("Arquivo não encontrado entre os da gratuidade.")
    if anexo["entity_type"] == GC.ENTIDADE and peca == CERTIDAO:
        raise PortalError("Este arquivo entrou como comprovante. Se ele traz também a "
                          "certidão, marque «os dois»; se não, guarde a certidão à parte.")
    if anexo["entity_type"] == ENTIDADE_CERTIDAO and peca != CERTIDAO:
        raise PortalError("Este arquivo entrou como certidão. Guarde o comprovante à parte.")
    _marcar(bd, int(anexo["id"]), int(anexo["entity_id"]), peca=peca, tipo_comprovante=tipo,
            agora=agora, usuario=usuario)
    return int(anexo["entity_id"])


# ------------------------------------------------------------ as remessas


def _gerar(bd, tipo: str, ids: list[int], *, inicio: str, fim: str, agora: str,
           usuario: str) -> int:
    novo = int(bd.escrever(
        """INSERT INTO sd_portal_remessas (tipo, inicio, fim, gerado_em, gerado_por)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (tipo, inicio, fim, agora, usuario or ""))[0]["id"])
    for selo_id in ids:
        bd.escrever("INSERT INTO sd_portal_itens (remessa_id, tipo, selo_id) VALUES (%s, %s, %s)",
                    (novo, tipo, int(selo_id)))
    return novo


def gerar_oficio(con, *, inicio: str, fim: str, agora: str, usuario: str = "") -> int:
    """O ofício de pedido de cancelamento: todos os selos cancelados do período
    que ainda não estão em ofício nenhum. ESCREVE.

    A trava vem ANTES da lista: dois gestores clicando juntos leriam os mesmos
    selos e o segundo estouraria a chave — ou, sem a chave, pediria duas vezes.
    """
    inicio, fim = _periodo(inicio, fim)
    bd = banco(con)
    bd.travar("sd_portal_remessas.CANCELAMENTO")
    ids = [r["id"] for r in cancelados(con, inicio=inicio, fim=fim)
           if r["pedido"] == "NAO_PEDIDO"]
    if not ids:
        raise PortalError("Nenhum selo cancelado neste período falta pedir ao TJMA.")
    return _gerar(bd, CANCELAMENTO, ids, inicio=inicio, fim=fim, agora=agora, usuario=usuario)


def gerar_pacote(con, *, inicio: str, fim: str, agora: str, usuario: str = "") -> int:
    """O pacote do ressarcimento: os selos gratuitos do período com as duas
    peças e fora de pacote. Os que ainda faltam ficam na fila. ESCREVE."""
    inicio, fim = _periodo(inicio, fim)
    bd = banco(con)
    bd.travar("sd_portal_remessas.GRATUIDADE")
    ids = [r["id"] for r in gratuitos(con, inicio=inicio, fim=fim, situacao="PRONTO")]
    if not ids:
        raise PortalError("Nenhum selo gratuito do período está pronto: cada um precisa do "
                          "comprovante e da cópia da certidão do ato.")
    return _gerar(bd, GRATUIDADE, ids, inicio=inicio, fim=fim, agora=agora, usuario=usuario)


def remessas(con, tipo: str, limite: int = 30) -> list[dict]:
    """As últimas remessas de um tipo, com quantos selos cada uma tem. Só LÊ."""
    return [dict(r) | {"selos": int(r["selos"])} for r in banco(con).ler(
        """SELECT r.id, r.tipo, r.inicio, r.fim, r.gerado_em, r.gerado_por, r.comunicado_em,
                  r.comunicado_por, r.protocolo, count(i.id) AS selos
             FROM sd_portal_remessas r
             LEFT JOIN sd_portal_itens i ON i.remessa_id = r.id
            WHERE r.tipo = %s
            GROUP BY r.id
            ORDER BY r.id DESC LIMIT %s""",
        (tipo, int(limite)))]


def remessa(con, remessa_id: int) -> dict:
    """A remessa e os selos dela, na ordem do papel. Só LÊ."""
    bd = banco(con)
    cab = bd.um("SELECT * FROM sd_portal_remessas WHERE id = %s", (int(remessa_id),))
    if not cab:
        raise PortalError("Remessa não encontrada.")
    itens = []
    for r in bd.ler(
            """SELECT s.id, s.numero, s.atribuicao, s.referencia, s.tabela, s.ato_id,
                      s.obtido_em, s.cancelado_em, s.motivo_cancelamento
                 FROM sd_portal_itens i JOIN sd_selos s ON s.id = i.selo_id
                WHERE i.remessa_id = %s
                ORDER BY s.cancelado_em, s.obtido_em, s.id""", (int(remessa_id),)):
        d = dict(r)
        d["ato"] = descrever_ato(con, d)
        itens.append(d)
    return dict(cab) | {"itens": itens}


def marcar_comunicado(con, remessa_id: int, *, agora: str, usuario: str = "",
                      protocolo: str = "") -> None:
    """«Mandei.» Uma vez só, e o UPDATE é que decide quem chegou primeiro. ESCREVE."""
    feito = banco(con).escrever(
        """UPDATE sd_portal_remessas
              SET comunicado_em = %s, comunicado_por = %s, protocolo = %s
            WHERE id = %s AND comunicado_em = '' RETURNING id""",
        (agora, usuario or "", str(protocolo or "").strip()[:200], int(remessa_id)))
    if not feito:
        raise PortalError("Esta remessa não existe ou já foi marcada como enviada.")


def descartar(con, remessa_id: int) -> str:
    """Desfaz um rascunho: os selos voltam a faltar. Devolve o tipo. ESCREVE.

    Prende a linha antes de conferir: sem o FOR UPDATE, o «mandei» de outra
    tela podia entrar entre a conferência e o DELETE, e o registro de que o
    Tribunal foi avisado sumiria.
    """
    bd = banco(con)
    bd._escrita()
    cab = bd.um("SELECT id, tipo, comunicado_em FROM sd_portal_remessas WHERE id = %s FOR UPDATE",
                (int(remessa_id),))
    if not cab:
        raise PortalError("Remessa não encontrada.")
    if cab["comunicado_em"]:
        raise PortalError("Remessa já enviada não se desfaz: ela é o registro de que o "
                          "Tribunal foi avisado.")
    bd.escrever("DELETE FROM sd_portal_itens WHERE remessa_id = %s", (int(remessa_id),))
    bd.escrever("DELETE FROM sd_portal_remessas WHERE id = %s", (int(remessa_id),))
    return str(cab["tipo"])


# ------------------------------------------------------ o papel e o pacote


def lista_csv(con, remessa_id: int) -> bytes:
    """A lista da remessa em CSV (`;`, com BOM, para abrir no Excel). Só LÊ.

    Sem o nome de quem obteve ou cancelou: a lista sai de casa.
    """
    r = remessa(con, remessa_id)
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    if r["tipo"] == CANCELAMENTO:
        w.writerow(["Selo", "Ato", "Atribuição", "Obtido em", "Cancelado em", "Motivo"])
        for i in r["itens"]:
            w.writerow([i["numero"], i["ato"], i["atribuicao"] or "", (i["obtido_em"] or "")[:10],
                        (i["cancelado_em"] or "")[:10], i["motivo_cancelamento"] or ""])
    else:
        w.writerow(["Selo", "Ato", "Atribuição", "Obtido em", "Comprovante", "Arquivo"])
        for i in r["itens"]:
            tipos = sorted({TIPOS_DE_COMPROVANTE.get(p["tipo_comprovante"], "")
                            for p in pecas(con, i["id"])} - {""})
            w.writerow([i["numero"], i["ato"], i["atribuicao"] or "", (i["obtido_em"] or "")[:10],
                        ", ".join(tipos), f"{i['numero']}.pdf"])
    return ("﻿" + saida.getvalue()).encode("utf-8")


def _pymupdf():
    try:
        import pymupdf
    except ImportError:  # versões antigas só têm o nome velho
        import fitz as pymupdf
    return pymupdf


def juntar_em_pdf(arquivos: list[tuple[str, bytes]]) -> bytes:
    """Junta PDFs e imagens num PDF só, na ordem dada. Só calcula.

    Arquivo que não abre recusa o pacote inteiro, com o nome dele: subir ao
    Portal um PDF sem a página do comprovante seria pior que não subir.
    """
    fitz = _pymupdf()
    saida = fitz.open()
    for nome, conteudo in arquivos:
        ext = Path(nome).suffix.lower().lstrip(".") or "pdf"
        try:
            doc = fitz.open(stream=conteudo, filetype=ext)
            if ext != "pdf":
                doc = fitz.open(stream=doc.convert_to_pdf(), filetype="pdf")
            saida.insert_pdf(doc)
        except Exception as erro:  # noqa: BLE001 — o PyMuPDF levanta tipos variados
            raise PortalError(f"O arquivo «{nome}» não abre como PDF ou imagem: troque-o "
                              f"antes de montar o pacote.") from erro
    if not saida.page_count:
        raise PortalError("Nenhuma página para juntar.")
    return saida.tobytes(garbage=3, deflate=True)


def montar_pacote(con, remessa_id: int) -> bytes:
    """O ZIP para o Portal: um `<número do selo>.pdf` por selo e `lista.csv`.
    Só LÊ (o banco e os arquivos guardados)."""
    r = remessa(con, remessa_id)
    if r["tipo"] != GRATUIDADE:
        raise PortalError("Só a remessa de gratuidade tem pacote de arquivos.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in r["itens"]:
            arquivos = []
            for p in pecas(con, item["id"]):
                caminho = Path(p["stored_path"] or "")
                if not caminho.is_file():
                    raise PortalError(f"O arquivo «{p['original_name']}» do selo "
                                      f"{item['numero']} não está mais na pasta do sistema.")
                arquivos.append((p["original_name"], caminho.read_bytes()))
            zf.writestr(f"{item['numero']}.pdf", juntar_em_pdf(arquivos))
        zf.writestr("lista.csv", lista_csv(con, remessa_id))
    return buf.getvalue()
