"""PIX NO PROTESTO SÓ É PAGAMENTO COM O CRÉDITO CONFERIDO — 29/10/2026.

O CASO
    Em 16/10/2026 entrou na conta da serventia um PIX de R$ 1.765,14, o
    pagamento de um título. A escrevente só o lançou na ficha em 21/10 —
    «por PIX», SEM comprovante anexado e sem protocolo de atendimento com o
    item marcado. O selo falhou e o ato se desfez no mesmo segundo, mas o
    título ficou PAGO; em 23/10 o retorno informou à CRA a ocorrência «1»
    (pago), com a data do lançamento, e a CRA aceitou. Sem comprovante e sem
    crédito conferido no sistema — nada no caixa, em boleto ou em repasse —,
    o oficial levou 8 dias para conseguir confirmar se o dinheiro tinha
    entrado.

    A ordem do oficial: «a escrevente não pode conseguir errar; se insistir,
    tem de afirmar expressamente e deixar log». Com esta trava, o caso não
    teria acontecido: sem o comprovante o PIX não entra, e sem o crédito
    localizado o título não vira PAGO nem vai à CRA.

O QUE MUDA
    1. **LANÇAR PAGAMENTO POR PIX NÃO LAVRA O PAGAMENTO**: registra o PIX
       (`registrar`), com o comprovante anexado no mesmo ato, numa linha de
       `pt_pix` AGUARDANDO_CREDITO. Nenhum ato nasce — e por isso o título
       não vira PAGO, nada vai ao retorno da CRA nem ao XML da CENPROT (eles
       leem `pt_atos`), e nada se sela.
    2. **O CRÉDITO SE LOCALIZA**
       - pelo banco (`conferir_no_banco`, `pix_credito`): o extrato do Inter,
         com um token que só lê; pelo E2E do comprovante ou pelo valor e pelo
         dia; confirma sozinho quando o crédito é um só;
       - à mão (`confirmar_a_mao`): só o ADMIN ou o gerente (MANAGER) — quem
         confere o caixa —, NUNCA quem lançou o PIX, e com afirmação expressa
         («Afirmo, sob minha responsabilidade, que o crédito de R$ X entrou em
         dd/mm na conta …»), regra `PIX_SEM_CREDITO_CONFERIDO`.
    3. **CONFIRMADO, O PAGAMENTO SE LAVRA PELO CAMINHO DE SEMPRE**: a ficha
       oferece o pagamento por PIX com o crédito conferido (`pix_id`), com o
       selo, a situação PAGO e o retorno de sempre — e
       `protesto.lancar_pagamento` RECUSA PIX sem crédito conferido, venha de
       que tela vier.
    4. **ENQUANTO O PIX ESPERA, O TÍTULO NÃO ANDA** (`recusar_se_esperando`):
       não se protesta, não se desiste e não recebe outro pagamento — o
       devedor diz que pagou. O oficial ou o gerente dá o PIX por não
       confirmado (`dar_por_nao_confirmado`, com motivo), e o título volta a
       andar.
    5. **O QUE ESPERA MAIS DE UM DIA ÚTIL É PENDÊNCIA** (`pendencias_do_pix`),
       no contrato dos ganchos do roteiro do Protesto.
    6. **A DATA DO PAGAMENTO É A DO CRÉDITO** — a do extrato, quando a
       conferência o achou; a afirmada, na confirmação à mão; a do
       comprovante, se nenhuma outra houver — e NÃO a do lançamento. Ela fica
       no ato (`detalhe_json.data_do_pagamento`) e sai no Livro de Pagamentos
       (na coluna das ocorrências: a data da coluna «data» é a do
       assentamento, CN-MA art. 930, b) e na data da ocorrência do D da
       CENPROT.

    7. **A CONCILIAÇÃO AO CONTRÁRIO** (`conciliar_creditos`): o PIX e a TED
       que ENTRARAM e batem com um título em aberto (APONTADO ou INTIMADO) —
       pelo valor (o saldo mais as custas, com tolerância de centavos) e pelo
       pagador ou pelo E2E —, sem pagamento lançado, viram «dinheiro recebido
       sem pagamento lançado» (`creditos_sem_pagamento`), com o título
       provável: pendência no mesmo dia, atrasada no dia útil seguinte. Foi o
       que faltou no caso: o dinheiro estava na conta desde 16/10.

O QUE ESTE MÓDULO NÃO FAZ
    Não lavra ato (quem lavra é `protesto.lancar_pagamento`, pela rota de
    sempre), não paga nada e não escreve no banco do Inter: a conferência só
    lê o extrato.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pix_credito as PC
import protesto as PT
from bd_nativo import banco
from caixa_schema import centavos, reais

AGUARDANDO = "AGUARDANDO_CREDITO"
CONFIRMADO = "CONFIRMADO"
NAO_CONFIRMADO = "NAO_CONFIRMADO"
SITUACOES = {
    AGUARDANDO: "aguardando o crédito",
    CONFIRMADO: "crédito conferido",
    NAO_CONFIRMADO: "crédito não confirmado",
}
PELO_BANCO = "BANCO"
A_MAO = "MANUAL"
MODOS = {PELO_BANCO: "no extrato do banco", A_MAO: "à mão, com afirmação expressa"}

#: As formas de pagamento que só contam com o crédito conferido. Só o PIX, por
#: ordem do oficial; a transferência tem o mesmo risco, e entrar aqui é
#: decisão dele.
FORMAS_QUE_ESPERAM_O_CREDITO = ("PIX",)

#: A regra da afirmação expressa — o contrato comum da casa (29/10/2026).
REGRA = "PIX_SEM_CREDITO_CONFERIDO"
ACAO_DA_AFIRMACAO = "AFIRMACAO_EXPRESSA"
#: Quem confirma o crédito à mão: quem confere o caixa (`caixa_web`, ação
#: «conferir»), e nunca quem lançou.
QUEM_CONFIRMA_A_MAO = ("ADMIN", "MANAGER")
#: Quantos dias úteis o PIX espera o crédito antes de virar pendência.
DIAS_UTEIS_DE_TOLERANCIA = 1
MINIMO_DO_MOTIVO = 10

#: O comprovante mora em `attachments`, com dono próprio: o PIX.
ENTIDADE_DO_COMPROVANTE = "PT_PIX"
ASSINATURA_DO_COMPROVANTE = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG",),
    ".jpg": (b"\xff\xd8",),
    ".jpeg": (b"\xff\xd8",),
}
LIMITE_DO_COMPROVANTE = 10 * 1024 * 1024
#: A extensão que vai ao disco SAI DESTA LISTA, e não do nome enviado: o nome
#: de fora só fica como rótulo (`original_name`).
EXTENSAO_GRAVADA = {".pdf": ".pdf", ".png": ".png", ".jpg": ".jpg", ".jpeg": ".jpg"}

#: O processo da automação que lê o extrato — é ele, e não a tela, que fala
#: com o banco quando a credencial mora no cofre.
CODIGO_DO_PROCESSO = "PROTESTO_PIX_CREDITO"
CATALOGO = (
    {"codigo": CODIGO_DO_PROCESSO,
     "nome": "Protesto — localizar no extrato o crédito dos PIX lançados",
     "setor": "PROTESTO", "funcao": "protesto_pix.conferir",
     "descricao": ("Lê o extrato do Banco Inter (só leitura, escopo extrato.read) e "
                   "confirma o PIX do Protesto cujo crédito está lá: pelo E2E do "
                   "comprovante, ou pelo valor e pelo dia quando o crédito é um só. "
                   "Confirmar não lavra nada: o pagamento se lavra na ficha."),
     "agenda": {"dias": [0, 1, 2, 3, 4], "intervalo_min": 30,
                "janela": ["08:00", "18:00"]}},
)


class PixError(PT.ProtestoError):
    """Impedimento de regra do PIX, com a frase pronta para o balcão."""


# ------------------------------------------------------------- utilidades


def _br(iso: Any) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) == 10 and s[4] == "-" else (s or "—")


def _dia(texto: Any) -> date | None:
    try:
        return date.fromisoformat(str(texto or "").strip()[:10])
    except ValueError:
        return None


def _letras(texto: str) -> int:
    return sum(1 for c in str(texto or "") if c.isalpha())


def _mesma_pessoa(a: Any, b: Any) -> bool:
    x = " ".join(str(a or "").upper().split())
    y = " ".join(str(b or "").upper().split())
    return bool(x) and x == y


def _tem_tabela(con) -> bool:
    return banco(con).tem_tabela("pt_pix")


def _ler(con, pix_id: Any, *, prender: bool = False) -> dict | None:
    try:
        numero = int(pix_id)
    except (TypeError, ValueError):
        return None
    bd = banco(con)
    if prender:
        bd._escrita()
    return bd.um(
        "SELECT * FROM pt_pix WHERE id=%s" + (" FOR UPDATE" if prender else ""),
        (numero,))


def _ato_valido(con, ato_id: Any) -> bool:
    if not ato_id:
        return False
    return banco(con).um(
        "SELECT 1 AS um FROM pt_atos WHERE id=%s AND COALESCE(cancelado, 0) = 0",
        (int(ato_id),)) is not None


def comprovantes(con, pix_id: int) -> list[dict]:
    """Os comprovantes daquele PIX. Só LÊ."""
    return [dict(r) for r in banco(con).ler(
        """SELECT id, original_name, size_bytes, uploaded_at
             FROM attachments WHERE entity_type=%s AND entity_id=%s
            ORDER BY id""", (ENTIDADE_DO_COMPROVANTE, int(pix_id)))]


# ------------------------------------------------------------- consultas


_SQL_ESPERANDO = """
    (p.situacao = 'AGUARDANDO_CREDITO'
     OR (p.situacao = 'CONFIRMADO' AND NOT EXISTS (
            SELECT 1 FROM pt_atos a
             WHERE a.id = p.ato_id AND COALESCE(a.cancelado, 0) = 0)))"""


def ativo_do_titulo(con, titulo_id: int) -> dict | None:
    """O PIX do título que ainda não virou pagamento: o que espera o crédito,
    ou o de crédito conferido sem o pagamento lavrado. Só LÊ."""
    if not _tem_tabela(con):
        return None
    return banco(con).um(
        f"""SELECT p.* FROM pt_pix p
             WHERE p.titulo_id = %s AND {_SQL_ESPERANDO}
             ORDER BY p.id DESC LIMIT 1""", (int(titulo_id),))


def do_titulo(con, titulo_id: int) -> list[dict]:
    """Todos os PIX do título, do mais novo ao mais velho, com os
    comprovantes. Só LÊ."""
    if not _tem_tabela(con):
        return []
    linhas = [dict(r) for r in banco(con).ler(
        "SELECT * FROM pt_pix WHERE titulo_id=%s ORDER BY id DESC",
        (int(titulo_id),))]
    for p in linhas:
        p["comprovantes"] = comprovantes(con, int(p["id"]))
        p["lavrado"] = _ato_valido(con, p.get("ato_id"))
    return linhas


def para_a_ficha(con, titulo_id: int) -> dict:
    """O que a ficha do título mostra do PIX. Só LÊ.

    `ativo` é o PIX que ainda não virou pagamento; `para_lavrar` é o de
    crédito conferido, que o formulário do pagamento leva no `pix_id`.
    """
    ativo = ativo_do_titulo(con, titulo_id)
    return {
        "ativo": ativo,
        "para_lavrar": ativo if ativo and ativo["situacao"] == CONFIRMADO else None,
        "historico": do_titulo(con, titulo_id),
        "com_cofre": PC.com_cofre(),
        # o dinheiro que entrou e parece ser deste título (29/10/2026)
        "creditos_sem_pagamento": creditos_sem_pagamento(con, titulo_id=titulo_id),
    }


def lista(con, *, limite: int = 200) -> dict:
    """Os PIX para a tela própria: os que esperam e os resolvidos há pouco.
    Só LÊ."""
    if not _tem_tabela(con):
        return {"esperando": [], "resolvidos": []}
    bd = banco(con)
    colunas = """p.*, t.numero_titulo, t.protocolo, t.situacao AS situacao_titulo"""
    esperando = [dict(r) for r in bd.ler(
        f"""SELECT {colunas} FROM pt_pix p JOIN pt_titulos t ON t.id = p.titulo_id
             WHERE {_SQL_ESPERANDO}
             ORDER BY p.id LIMIT %s""", (int(limite),))]
    resolvidos = [dict(r) for r in bd.ler(
        f"""SELECT {colunas} FROM pt_pix p JOIN pt_titulos t ON t.id = p.titulo_id
             WHERE NOT {_SQL_ESPERANDO}
             ORDER BY p.id DESC LIMIT %s""", (int(limite),))]
    for p in esperando + resolvidos:
        p["comprovantes"] = comprovantes(con, int(p["id"]))
    return {"esperando": esperando, "resolvidos": resolvidos}


# ------------------------------------------------- a trava do título


def recusar_se_esperando(con, titulo_id: int, o_que: str, *,
                         exceto_pix_id: Any = None) -> None:
    """Recusa o ato quando há PIX do título que ainda não virou pagamento.
    Só LÊ (e recusa).

    O devedor diz que pagou: protestar, desistir ou receber outro pagamento
    por cima disso é o erro que a ordem de 29/10/2026 manda impedir. O
    caminho de saída é o crédito conferido — ou o PIX dado por não confirmado.
    """
    ativo = ativo_do_titulo(con, titulo_id)
    if not ativo:
        return
    if exceto_pix_id is not None and str(ativo["id"]) == str(exceto_pix_id):
        return
    valor = reais(int(ativo["valor_centavos"]))
    if ativo["situacao"] == CONFIRMADO:
        raise PixError(
            f"O crédito do PIX de R$ {valor} deste título foi conferido em "
            f"{_br(ativo['confirmado_em'])}: lance o PAGAMENTO por PIX com ele "
            f"(a ficha o oferece em «Lançar o próximo ato»). {o_que.capitalize()} "
            f"não cabe por cima de um pagamento conferido.")
    raise PixError(
        f"Há um PIX de R$ {valor}, de {_br(ativo['data_pix'])}, AGUARDANDO O "
        f"CRÉDITO neste título (lançado em {_br(ativo['lancado_em'])} por "
        f"{ativo['lancado_por'] or 'quem não ficou gravado'}). Enquanto o crédito "
        f"não for conferido, {o_que} não pode ser lançado — o devedor diz que "
        f"pagou. Confira o crédito no banco, ou peça ao oficial ou ao gerente "
        f"que o confirme à mão ou o dê por não confirmado.")


# ------------------------------------------------------------- registrar


def _conferir_comprovante(bd, *, nome: Any, conteudo: bytes) -> dict:
    """O arquivo é um comprovante? Recusa o que não é arquivo de verdade e o
    comprovante já apresentado noutro PIX. Só LÊ."""
    nome_limpo = Path(str(nome or "")).name.strip()
    sufixo = Path(nome_limpo).suffix.lower()
    if not nome_limpo or not conteudo:
        raise PixError(
            "PIX só se lança com o COMPROVANTE anexado, no mesmo ato — escolha "
            "o arquivo (PDF, PNG ou JPG) que o devedor apresentou.")
    if sufixo not in ASSINATURA_DO_COMPROVANTE:
        raise PixError("O comprovante do PIX tem de ser PDF, PNG ou JPG.")
    ext = EXTENSAO_GRAVADA[sufixo]
    conteudo = bytes(conteudo)
    if len(conteudo) > LIMITE_DO_COMPROVANTE:
        raise PixError(
            f"O comprovante passa de {LIMITE_DO_COMPROVANTE // 1024 // 1024} MB.")
    if not conteudo.startswith(ASSINATURA_DO_COMPROVANTE[sufixo]):
        raise PixError(
            f"O arquivo diz ser {ext} e não é — o conteúdo não começa como um "
            f"{ext[1:].upper()}. Salve o comprovante de novo e anexe.")
    sha = hashlib.sha256(conteudo).hexdigest()
    outro = bd.um(
        """SELECT p.id, p.titulo_id, t.numero_titulo
             FROM attachments x
             JOIN pt_pix p ON p.id = x.entity_id
             JOIN pt_titulos t ON t.id = p.titulo_id
            WHERE x.entity_type = %s AND x.sha256 = %s
            ORDER BY p.id LIMIT 1""", (ENTIDADE_DO_COMPROVANTE, sha))
    if outro:
        raise PixError(
            f"Este comprovante já foi apresentado no PIX nº {outro['id']} (título "
            f"{outro['numero_titulo']}). O mesmo PIX não paga dois títulos.")
    return {"nome_limpo": nome_limpo, "ext": ext, "conteudo": conteudo,
            "sha256": sha}


def _gravar_comprovante(bd, pix: dict, conferido: dict, *, pasta_de_arquivos: Any,
                        agora: str, usuario_id: Any = None) -> int:
    """Grava o arquivo e a linha em `attachments`. ESCREVE.

    O NOME EM DISCO NÃO VEM DE FORA: é o número do título e do PIX, com a
    extensão da lista — o nome do arquivo enviado só fica como rótulo.
    """
    destino = (Path(pasta_de_arquivos) / "Protesto" / "PIX"
               / str(int(pix["titulo_id"])))
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"pix-{int(pix['id'])}{conferido['ext']}"
    arquivo.write_bytes(conferido["conteudo"])
    return int(bd.escrever(
        """INSERT INTO attachments(entity_type, entity_id, original_name,
               stored_name, stored_path, sha256, size_bytes, description,
               uploaded_by, uploaded_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (ENTIDADE_DO_COMPROVANTE, int(pix["id"]), conferido["nome_limpo"],
         arquivo.name, str(arquivo), conferido["sha256"],
         len(conferido["conteudo"]),
         f"Comprovante do PIX nº {int(pix['id'])} — R$ "
         f"{reais(int(pix['valor_centavos']))} de {_br(pix['data_pix'])}",
         usuario_id, agora))[0]["id"])


def registrar(con, titulo_id: int, *, valor: Any, data_pix: Any,
              e2eid: Any = None, nome: Any, conteudo: bytes,
              pasta_de_arquivos: Any, agora: str, usuario: str | None = None,
              usuario_id: Any = None) -> dict:
    """Registra o PIX declarado, AGUARDANDO O CRÉDITO, com o comprovante.
    ESCREVE (a linha, o anexo e o arquivo).

    NÃO É PAGAMENTO: nenhum ato nasce, o título fica como está, nada vai à CRA
    nem à CENPROT, e nada se sela. Recusa o que `lancar_pagamento` recusaria
    (sustado, protestado, situação final), o título com outro PIX esperando,
    o comprovante que falta ou que já pagou outro título, e o E2E repetido.
    """
    bd = banco(con)
    tit = PT.titulo_para_gravar(con, titulo_id)
    if not tit:
        raise PixError(f"Título {titulo_id} não encontrado.")
    PT._recusar_se_sustado(con, titulo_id, "o pagamento")
    PT.recusar_pagamento_na_situacao(tit)
    ativo = ativo_do_titulo(con, titulo_id)
    if ativo:
        raise PixError(
            f"Este título já tem o PIX nº {ativo['id']}, de R$ "
            f"{reais(int(ativo['valor_centavos']))}, "
            f"{SITUACOES[ativo['situacao']]}. Um título, um pagamento: resolva "
            f"aquele antes (conferir o crédito, ou dá-lo por não confirmado).")
    valor_centavos = centavos(str(valor or ""))
    if valor_centavos <= 0:
        raise PixError("Informe o valor do PIX, como está no comprovante.")
    dia = _dia(data_pix)
    if not dia:
        raise PixError("Informe a data do PIX, como está no comprovante.")
    if dia > (_dia(agora) or date.today()):
        raise PixError(f"A data do PIX ({_br(dia.isoformat())}) é futura — confira "
                       f"o comprovante.")
    e2e = None
    if str(e2eid or "").strip():
        e2e = PC.e2e_valido(e2eid)
        if not e2e:
            raise PixError(
                "O identificador do PIX (E2E) tem 32 caracteres e começa com «E» — "
                "confira no comprovante, ou deixe o campo em branco.")
    conferido = _conferir_comprovante(bd, nome=nome, conteudo=conteudo)
    lido = False
    if not e2e:
        e2e = PC.e2e_do_comprovante(conferido["conteudo"], conferido["ext"])
        lido = bool(e2e)
    if e2e:
        repetido = bd.um(
            """SELECT p.id, t.numero_titulo FROM pt_pix p
                 JOIN pt_titulos t ON t.id = p.titulo_id
                WHERE UPPER(p.e2eid) = UPPER(%s) OR UPPER(p.credito_e2eid) = UPPER(%s)
                ORDER BY p.id LIMIT 1""", (e2e, e2e))
        if repetido:
            raise PixError(
                f"Este PIX (E2E {e2e}) já foi apresentado no PIX nº "
                f"{repetido['id']} (título {repetido['numero_titulo']}). O mesmo "
                f"PIX não paga dois títulos.")
    pix = dict(bd.escrever(
        """INSERT INTO pt_pix(titulo_id, valor_centavos, data_pix, e2eid,
               e2eid_lido_do_comprovante, situacao, lancado_em, lancado_por,
               lancado_por_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (int(titulo_id), valor_centavos, dia.isoformat(), e2e, int(lido),
         AGUARDANDO, agora, usuario,
         int(usuario_id) if usuario_id else None))[0])
    anexo_id = _gravar_comprovante(bd, pix, conferido,
                                   pasta_de_arquivos=pasta_de_arquivos,
                                   agora=agora, usuario_id=usuario_id)
    return {"pix_id": int(pix["id"]), "titulo_id": int(titulo_id),
            "numero_titulo": tit["numero_titulo"],
            "valor_centavos": valor_centavos, "data_pix": dia.isoformat(),
            "e2eid": e2e, "e2eid_lido_do_comprovante": lido,
            "anexo_id": anexo_id}


# ------------------------------------------------------------- conferir


def anotar_consulta(con, pix_id: int, *, resultado: str, motivo: str,
                    agora: str) -> None:
    """Guarda o que a última consulta ao extrato achou. ESCREVE."""
    banco(con).escrever(
        """UPDATE pt_pix SET ultima_consulta_em=%s, ultima_consulta=%s
            WHERE id=%s AND situacao=%s""",
        (agora, f"{PC.RESULTADOS.get(resultado, resultado)}: {motivo}"[:500],
         int(pix_id), AGUARDANDO))


def confirmar_pelo_banco(con, pix_id: int, *, credito: dict, agora: str,
                         por: str = "automação") -> dict:
    """Confirma o PIX cujo crédito o extrato mostrou. ESCREVE.

    Só o que espera o crédito, e só com o crédito do mesmo valor. O índice
    único de `credito_id` impede o mesmo crédito de confirmar dois PIX.
    """
    pix = _ler(con, pix_id, prender=True)
    if not pix or pix["situacao"] != AGUARDANDO:
        raise PixError("Este PIX não está aguardando o crédito.")
    if int(credito.get("valor_centavos") or -1) != int(pix["valor_centavos"]):
        raise PixError("O crédito achado não tem o valor do PIX.")
    banco(con).escrever(
        """UPDATE pt_pix SET situacao=%s, confirmacao_modo=%s, confirmado_em=%s,
               confirmado_por=%s, credito_id=%s, credito_data=%s,
               credito_valor_centavos=%s, credito_e2eid=%s, credito_pagador=%s,
               ultima_consulta_em=%s, ultima_consulta=%s
            WHERE id=%s""",
        (CONFIRMADO, PELO_BANCO, agora, por, str(credito.get("id") or "") or None,
         str(credito.get("dia") or "")[:10] or None,
         int(credito["valor_centavos"]), credito.get("e2eid") or None,
         credito.get("pagador") or None, agora,
         PC.RESULTADOS[PC.ACHADO], int(pix_id)))
    return {"pix_id": int(pix_id), "titulo_id": int(pix["titulo_id"]),
            "credito_id": credito.get("id"), "credito_data": credito.get("dia")}


def aguardando(con) -> list[dict]:
    """Os PIX que esperam o crédito, para a conferência. Só LÊ."""
    if not _tem_tabela(con):
        return []
    return [dict(r) for r in banco(con).ler(
        "SELECT * FROM pt_pix WHERE situacao=%s ORDER BY id", (AGUARDANDO,))]


def _ja_usados(con) -> set[str]:
    usados: set[str] = set()
    for r in banco(con).ler(
            """SELECT credito_id, credito_e2eid FROM pt_pix
                WHERE credito_id IS NOT NULL OR credito_e2eid IS NOT NULL"""):
        usados |= {str(v) for v in (r["credito_id"], r["credito_e2eid"]) if v}
    return usados


def conferir_no_banco(db, *, cliente: Any, agora: datetime,
                      por: str = "automação") -> dict:
    """Lê o extrato UMA vez e faz as duas conferências. Lê o banco do Inter;
    escreve só em `pt_pix` e em `pt_creditos_banco`.

    1. O PIX QUE ESPERA O CRÉDITO: procura o crédito de cada um e confirma o
       que achou (`pix_credito.procurar`).
    2. A CONCILIAÇÃO AO CONTRÁRIO (`conciliar_creditos`): o PIX e a TED que
       entraram nos últimos `DIAS_DA_CONCILIACAO` dias e batem com título em
       aberto, sem pagamento lançado.

    A REDE CORRE FORA DE TRANSAÇÃO: lê o que espera (transação curta), pede
    o extrato para o período que cobre as duas, e grava cada achado na sua
    transação curta. PIX de mais de 90 dias fica de fora — o extrato do Inter
    não alcança —, e vai à confirmação à mão.
    """
    with db.connect() as con:
        pendentes = aguardando(con)
        usados = _ja_usados(con)
    saida: dict[str, Any] = {"lidas": 0, "confirmados": [], "sem_credito": [],
                             "fora_da_janela": [], "sem_pagamento": []}
    hoje = agora.date()
    limite = hoje - timedelta(days=PC.JANELA_MAXIMA_DIAS - 1)
    dentro = [p for p in pendentes if (_dia(p["data_pix"]) or hoje) >= limite]
    saida["fora_da_janela"] = [int(p["id"]) for p in pendentes if p not in dentro]
    inicio = hoje - timedelta(days=DIAS_DA_CONCILIACAO - 1)
    if dentro:
        inicio = min(inicio, max(min(_dia(p["data_pix"]) or hoje for p in dentro)
                                 - timedelta(days=1), limite))
    creditos = cliente.creditos(inicio.isoformat(), hoje.isoformat())
    saida["lidas"] = len(creditos)
    carimbo = agora.replace(microsecond=0, tzinfo=None).isoformat()
    for p in dentro:
        achado = PC.procurar(creditos, valor_centavos=int(p["valor_centavos"]),
                             dia=p["data_pix"], e2eid=p.get("e2eid"),
                             ja_usados=usados)
        with db.transaction() as con:
            if achado["resultado"] == PC.ACHADO:
                feito = confirmar_pelo_banco(con, int(p["id"]),
                                             credito=achado["credito"],
                                             agora=carimbo, por=por)
                usados |= {str(achado["credito"].get("id") or ""),
                           str(achado["credito"].get("e2eid") or "")} - {""}
                saida["confirmados"].append(feito)
            else:
                anotar_consulta(con, int(p["id"]), resultado=achado["resultado"],
                                motivo=achado["motivo"], agora=carimbo)
                saida["sem_credito"].append({"pix_id": int(p["id"]),
                                             "titulo_id": int(p["titulo_id"]),
                                             "resultado": achado["resultado"],
                                             "motivo": achado["motivo"]})
    with db.transaction() as con:
        saida["sem_pagamento"] = conciliar_creditos(
            con, creditos, hoje=hoje, agora=carimbo, usados=usados)
    return saida


# ===================================== a conciliação ao contrário (29/10/2026)
#
# O DINHEIRO QUE ENTROU E NINGUÉM LANÇOU. O PIX do caso entrou em 16/10 e o
# pagamento só foi lançado em 21/10; o repasse ao apresentante atrasou, e o
# oficial só soube no dia 29. A trava do lançamento não pega isso — ninguém
# lançou nada. O que pega é ler o extrato ao contrário: o crédito que bate com
# um título em aberto e não tem pagamento lançado é PENDÊNCIA NO MESMO DIA, e
# fica ATRASADO no dia útil seguinte.

#: As situações em que o título ainda espera o pagamento.
SITUACOES_EM_ABERTO = ("APONTADO", "INTIMADO")
#: Quantos dias de extrato a conferência diária relê — a do dia e os anteriores,
#: para o fim de semana e a rodada que falhou não deixarem crédito de fora.
DIAS_DA_CONCILIACAO = 5
#: A diferença que ainda casa: centavos, e não reais.
TOLERANCIA_CENTAVOS = 99
ESPECIE_CREDITO = "CREDITO_SEM_PAGAMENTO"
#: As tabelas que a conta das custas lê (`protesto_cenprot.precos_do_titulo`).
TABELAS_DAS_CUSTAS = ("cx_vigencias", "cx_faixas", "cx_servicos",
                      "cx_servico_valores")
CREDITO_ABERTO = "ABERTO"
CREDITO_DESCARTADO = "DESCARTADO"


#: Quantas folhas o título arquiva — a parte das custas que muda de título
#: para título (item 17.9, por folha). Medido no acervo: o arquivamento divide
#: sempre em 3, 4 ou 5 folhas; o preço da CENPROT conta 5.
FOLHAS_POSSIVEIS = (5, 4, 3)


def _custas_possiveis(con, valor_centavos: int, vigencia: Any) -> list[tuple[int, int]]:
    """O que o devedor pode ter pago de emolumentos para retirar o título
    pago: a conta do arquivo de emolumentos da CENPROT (`precos_do_titulo`,
    com 5 folhas), e a mesma com 4 e com 3. Lista de (custas, folhas); vazia
    quando não dá para calcular (sem tabela, sem faixa) — aí casa só pelo
    saldo. Só LÊ.

    AS FOLHAS ENTRAM PORQUE O CASO AS EXIGIU — medido na produção (só
    leitura) em 29/10/2026: o PIX de R$ 1.765,14 é o saldo (R$ 1.632,93) mais
    as custas com QUATRO folhas (R$ 132,21); com as cinco da CENPROT daria
    R$ 1.771,89, e a tolerância de centavos não o acharia.
    """
    if vigencia is None or not valor_centavos:
        return []
    # SÓ PERDOA A TABELA QUE FALTA (a instalação sem a tabela de emolumentos):
    # aí casa só pelo saldo. Coluna errada estoura, como deve.
    if not all(banco(con).tem_tabela(t) for t in TABELAS_DAS_CUSTAS):
        return []
    import protesto_cenprot as CENP
    try:
        retirada = CENP.precos_do_titulo(con, int(valor_centavos),
                                         vigencia=int(vigencia))["retirada"]
        folha = CENP._preco_do_item(con, CENP.ITEM_POR_FOLHA, int(vigencia))
    except (CENP.CenprotError, ValueError, KeyError, TypeError):
        return []
    if retirada is None:
        return []
    if folha is None:
        return [(int(retirada), CENP.FOLHAS_ARQUIVADAS)]
    return [(int(retirada) - (CENP.FOLHAS_ARQUIVADAS - n) * int(folha), n)
            for n in FOLHAS_POSSIVEIS]


def _vigencia(con, dia: date) -> Any:
    import custas
    if not banco(con).tem_tabela("cx_vigencias"):
        return None
    try:
        return custas.vigencia_do_dia(con, dia.isoformat())["codigo"]
    except (custas.CustasError, KeyError, TypeError):
        return None


def titulos_em_aberto(con, *, hoje: date) -> list[dict]:
    """Os títulos APONTADO ou INTIMADO sem pagamento lançado, com os valores
    que o devedor pode ter pago e os devedores. Só LÊ.

    «Sem pagamento lançado»: sem PAGAMENTO válido e sem PIX que espera ou foi
    conferido — o PIX registrado já é o pagamento sendo lançado, e a
    conferência dele cuida do resto.
    """
    from pt_schema import normalizar_nome
    bd = banco(con)
    lugares = ",".join(["%s"] * len(SITUACOES_EM_ABERTO))
    titulos = [dict(r) for r in bd.ler(
        f"""SELECT t.id, t.numero_titulo, t.protocolo, t.situacao,
                   t.valor_centavos, t.saldo_centavos
              FROM pt_titulos t
             WHERE t.situacao IN ({lugares})
               AND NOT EXISTS (SELECT 1 FROM pt_atos a WHERE a.titulo_id = t.id
                                 AND a.tipo = 'PAGAMENTO'
                                 AND COALESCE(a.cancelado, 0) = 0)
               AND NOT EXISTS (SELECT 1 FROM pt_pix p WHERE p.titulo_id = t.id
                                 AND p.situacao <> 'NAO_CONFIRMADO')
             ORDER BY t.id""", list(SITUACOES_EM_ABERTO))]
    vigencia = _vigencia(con, hoje)
    for t in titulos:
        saldo = int(t["saldo_centavos"] or 0) or int(t["valor_centavos"] or 0)
        esperados = [(saldo + custas, f"o saldo do título mais as custas "
                                      f"({folhas} folhas arquivadas)")
                     for custas, folhas in _custas_possiveis(
                         con, int(t["valor_centavos"] or 0) or saldo, vigencia)]
        esperados.append((saldo, "o saldo do título"))
        t["esperados"] = [e for e in esperados if e[0] > 0]
        t["devedores"] = [
            {"documento": "".join(c for c in str(d["documento_numero"] or "")
                                  if c.isdigit()),
             "nome": normalizar_nome(d["nome"]) or ""}
            for d in bd.ler("SELECT documento_numero, nome FROM pt_devedores "
                            "WHERE titulo_id = %s", (int(t["id"]),))]
    return titulos


def casar_credito(t: dict, titulos: list[dict]) -> list[dict]:
    """Os títulos com que o crédito pode bater, do mais provável ao menos.
    Só calcula.

    PELO VALOR — o saldo mais as custas, ou só o saldo, com tolerância de
    centavos — e PELO PAGADOR: o documento de quem pagou igual ao de um
    devedor vale mais que o nome igual. O documento sozinho também casa
    (o devedor pode ter pago outra conta junto); o valor sozinho casa, e a
    lista diz que foi só pelo valor.
    """
    from pt_schema import normalizar_nome
    valor = PC.centavos_do_banco(t.get("valor"))
    if not valor:
        return []
    documento = PC.documento_do_pagador(t)
    nome = normalizar_nome(PC.nome_do_pagador(t)) or ""
    saida = []
    for tit in titulos:
        pelo_valor = next((rotulo for esperado, rotulo in tit["esperados"]
                           if abs(int(esperado) - int(valor)) <= TOLERANCIA_CENTAVOS),
                          None)
        doc = bool(documento) and any(documento == d["documento"]
                                      for d in tit["devedores"])
        mesmo_nome = bool(nome) and any(nome == d["nome"] for d in tit["devedores"])
        if not (pelo_valor or doc):
            continue
        motivos = []
        if pelo_valor:
            motivos.append(f"o valor bate com {pelo_valor}")
        if doc:
            motivos.append("o documento de quem pagou é o do devedor")
        elif mesmo_nome:
            motivos.append("o nome de quem pagou é o do devedor")
        saida.append({"titulo_id": int(tit["id"]),
                      "numero_titulo": tit["numero_titulo"],
                      "protocolo": tit["protocolo"],
                      "pontos": (2 if pelo_valor else 0) + (3 if doc else 0)
                                + (1 if mesmo_nome and not doc else 0),
                      "documento_bate": doc,
                      "motivo": "; ".join(motivos)})
    saida.sort(key=lambda c: (-c["pontos"], c["titulo_id"]))
    return saida


def conciliar_creditos(con, creditos: list[dict], *, hoje: date, agora: str,
                       usados: set[str] | None = None) -> list[dict]:
    """O PIX e a TED recebidos nos últimos dias que batem com título em aberto
    e não têm pagamento lançado: entram em `pt_creditos_banco`, com o título
    provável. ESCREVE (só a lista). Devolve os que entraram agora.

    O crédito que já confirmou um PIX, o que já está na lista e o que não bate
    com título nenhum ficam de fora. Rodar de novo não duplica (o
    `credito_id` é único).
    """
    if not banco(con).tem_tabela("pt_creditos_banco"):
        return []
    usados = {str(u).upper() for u in (usados or set()) if u}
    desde = hoje - timedelta(days=DIAS_DA_CONCILIACAO - 1)
    bd = banco(con)
    ja = {str(r["credito_id"]) for r in bd.ler(
        "SELECT credito_id FROM pt_creditos_banco")}
    titulos = None
    novos = []
    for t in creditos:
        tipo = PC.tipo_do_credito(t)
        ident = PC.id_da_transacao(t)
        dia = _dia(PC.dia_da_transacao(t))
        if not tipo or not ident or ident in ja or not dia or dia < desde:
            continue
        if (ident.upper() in usados
                or PC.e2e_da_transacao(t).upper() in usados - {""}):
            continue
        if titulos is None:
            titulos = titulos_em_aberto(con, hoje=hoje)
        candidatos = casar_credito(t, titulos)
        if not candidatos:
            continue
        provavel = candidatos[0]
        linha = bd.escrever(
            """INSERT INTO pt_creditos_banco(credito_id, dia, valor_centavos, tipo,
                   e2eid, pagador, titulo_id, documento_bate, candidatos_json,
                   lido_em)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (credito_id) DO NOTHING RETURNING id""",
            (ident, dia.isoformat(), PC.centavos_do_banco(t.get("valor")), tipo,
             PC.e2e_da_transacao(t) or None, PC.nome_do_pagador(t) or None,
             provavel["titulo_id"], int(provavel["documento_bate"]),
             json.dumps([{k: c[k] for k in ("titulo_id", "numero_titulo",
                                            "protocolo", "motivo")}
                         for c in candidatos[:5]], ensure_ascii=False),
             agora))
        ja.add(ident)
        if linha:
            novos.append({"id": int(linha[0]["id"]), "credito_id": ident,
                          "dia": dia.isoformat(), "tipo": tipo,
                          "titulo_id": provavel["titulo_id"],
                          "candidatos": len(candidatos)})
    return novos


_SQL_CREDITO_SEM_PAGAMENTO = """
    c.situacao = 'ABERTO'
    AND NOT EXISTS (SELECT 1 FROM pt_pix p WHERE p.credito_id = c.credito_id)
    AND NOT EXISTS (SELECT 1 FROM pt_atos a WHERE a.titulo_id = c.titulo_id
                      AND a.tipo = 'PAGAMENTO' AND COALESCE(a.cancelado, 0) = 0)
    AND NOT EXISTS (SELECT 1 FROM pt_pix p WHERE p.titulo_id = c.titulo_id
                      AND p.situacao <> 'NAO_CONFIRMADO')"""


def creditos_sem_pagamento(con, *, titulo_id: int | None = None,
                           limite: int = 200) -> list[dict]:
    """O DINHEIRO RECEBIDO SEM PAGAMENTO LANÇADO. Só LÊ.

    Sai da lista sozinho quando o pagamento (ou o PIX) é lançado no título
    provável, ou quando o crédito confirma um PIX. Não sai sozinho se o
    título for protestado — aí é o caso mais grave: protesto com o dinheiro
    na conta.
    """
    bd = banco(con)
    if not bd.tem_tabela("pt_creditos_banco"):
        return []
    filtro, args = "", []
    if titulo_id is not None:
        filtro, args = " AND c.titulo_id = %s", [int(titulo_id)]
    linhas = [dict(r) for r in bd.ler(
        f"""SELECT c.*, t.numero_titulo, t.protocolo, t.situacao AS situacao_titulo
              FROM pt_creditos_banco c
              LEFT JOIN pt_titulos t ON t.id = c.titulo_id
             WHERE {_SQL_CREDITO_SEM_PAGAMENTO}{filtro}
             ORDER BY c.dia, c.id LIMIT %s""", args + [int(limite)])]
    for c in linhas:
        try:
            c["candidatos"] = json.loads(c.get("candidatos_json") or "[]")
        except ValueError:
            c["candidatos"] = []
    return linhas


def descartar_credito(con, credito_id: int, *, papel: Any, usuario: str | None,
                      motivo: Any, agora: str) -> dict:
    """O crédito não é de título nenhum (ou não é deste): sai da lista, com o
    motivo. ESCREVE. Do oficial e do gerente."""
    if papel not in QUEM_CONFIRMA_A_MAO:
        raise PixError("Descartar o crédito da lista é do oficial ou do gerente.")
    razao = " ".join(str(motivo or "").split())
    if _letras(razao) < MINIMO_DO_MOTIVO:
        raise PixError(f"Escreva de quem é este dinheiro, se não é do título (pelo "
                       f"menos {MINIMO_DO_MOTIVO} letras).")
    bd = banco(con)
    bd._escrita()
    linha = bd.um("SELECT * FROM pt_creditos_banco WHERE id=%s FOR UPDATE",
                  (int(credito_id),))
    if not linha:
        raise PixError(f"Crédito {credito_id} não encontrado.")
    if linha["situacao"] != CREDITO_ABERTO:
        raise PixError("Este crédito já foi descartado.")
    bd.escrever(
        """UPDATE pt_creditos_banco SET situacao=%s, motivo_descarte=%s,
               descartado_em=%s, descartado_por=%s WHERE id=%s""",
        (CREDITO_DESCARTADO, razao[:500], agora, usuario, int(credito_id)))
    return {"credito_id": int(credito_id), "titulo_id": linha["titulo_id"],
            "motivo": razao}


# ------------------------------------------------- a confirmação à mão


def modelo_da_afirmacao(pix: dict) -> str:
    """O começo da afirmação, preenchido com o valor — a tela o oferece."""
    return (f"Afirmo, sob minha responsabilidade, que o crédito de R$ "
            f"{reais(int(pix['valor_centavos']))} entrou em … na conta …")


def _diz_o_valor(texto: str, valor_centavos: int) -> bool:
    corrido = str(texto or "").replace(" ", "")
    v = reais(int(valor_centavos))
    return v in corrido or v.replace(".", "") in corrido.replace(".", "")


def o_que_faltava(con, pix: dict) -> str:
    """A frase que vai na afirmação: o que o sistema não conseguiu provar.
    Só LÊ."""
    tit = PT.titulo(con, int(pix["titulo_id"])) or {}
    consulta = (f"última consulta ao extrato em {_br(pix['ultima_consulta_em'])}: "
                f"{pix['ultima_consulta']}" if pix.get("ultima_consulta")
                else "a conferência pelo extrato não rodou para ele")
    return (f"o crédito do PIX de R$ {reais(int(pix['valor_centavos']))} de "
            f"{_br(pix['data_pix'])} (título {tit.get('numero_titulo') or '—'}, "
            f"protocolo {tit.get('protocolo') or '—'}) não foi localizado pelo "
            f"sistema no extrato do banco — {consulta}")


def confirmar_a_mao(con, pix_id: int, *, papel: Any, usuario: str | None,
                    usuario_id: Any, por_robo: bool, afirmo: Any,
                    afirmacao: Any, credito_data: Any, conta: Any,
                    agora: str) -> dict:
    """O oficial ou o gerente confirma o crédito que o sistema não achou.
    ESCREVE. Devolve o registro da afirmação para a rota auditar FORA da
    transação (`AFIRMACAO_EXPRESSA`, regra `PIX_SEM_CREDITO_CONFERIDO`).

    QUEM CONFIRMA: o ADMIN ou o MANAGER — quem confere o caixa —, nunca quem
    lançou o PIX (se fossem a mesma pessoa, a conferência não valeria nada),
    e nunca um robô. A afirmação diz o valor; a data do crédito e a conta
    ficam em campos próprios.
    """
    import protesto_prova as PROVA
    if por_robo:
        raise PixError("Conta de robô não afirma «sob minha responsabilidade»: a "
                       "confirmação à mão do crédito é de gente.")
    if papel not in QUEM_CONFIRMA_A_MAO:
        raise PixError("A confirmação à mão do crédito é do oficial ou do gerente "
                       "— quem confere o caixa.")
    pix = _ler(con, pix_id, prender=True)
    if not pix:
        raise PixError(f"PIX {pix_id} não encontrado.")
    if pix["situacao"] != AGUARDANDO:
        raise PixError(f"Este PIX está «{SITUACOES.get(pix['situacao'], pix['situacao'])}» "
                       f"— só se confirma o que aguarda o crédito.")
    if ((usuario_id and pix["lancado_por_id"]
         and int(pix["lancado_por_id"]) == int(usuario_id))
            or _mesma_pessoa(pix["lancado_por"], usuario)):
        raise PixError("Quem lançou o PIX não confirma o crédito dele: a "
                       "conferência é de outra pessoa, como a do caixa.")
    dia = _dia(credito_data)
    if not dia:
        raise PixError("Informe a data em que o crédito entrou na conta.")
    if dia > (_dia(agora) or date.today()):
        raise PixError("A data do crédito é futura — confira o extrato.")
    if dia < (_dia(pix["data_pix"]) or dia):
        raise PixError(f"O crédito não pode ter entrado antes do PIX "
                       f"({_br(pix['data_pix'])}).")
    conta_limpa = " ".join(str(conta or "").split())
    if sum(1 for c in conta_limpa if c.isalnum()) < 3:
        raise PixError("Diga em que conta o crédito entrou (banco, agência e conta).")
    texto = PROVA.afirmacao_valida(afirmacao) if afirmo else None
    if not texto:
        raise PixError(
            f"A confirmação à mão exige a AFIRMAÇÃO EXPRESSA: marque «Afirmo» e "
            f"escreva, com pelo menos {PROVA.PISO_DA_AFIRMACAO} letras, "
            f"«{modelo_da_afirmacao(pix)}». Ela fica no PIX e na auditoria, com "
            f"o seu nome.")
    if not _diz_o_valor(texto, int(pix["valor_centavos"])):
        raise PixError(f"A afirmação tem de dizer o valor do crédito: R$ "
                       f"{reais(int(pix['valor_centavos']))}.")
    falta = o_que_faltava(con, pix)
    banco(con).escrever(
        """UPDATE pt_pix SET situacao=%s, confirmacao_modo=%s, confirmado_em=%s,
               confirmado_por=%s, confirmado_por_id=%s, credito_data=%s,
               credito_valor_centavos=%s, conta=%s, afirmacao=%s
            WHERE id=%s""",
        (CONFIRMADO, A_MAO, agora, usuario,
         int(usuario_id) if usuario_id else None, dia.isoformat(),
         int(pix["valor_centavos"]), conta_limpa[:200], texto, int(pix_id)))
    return {"regra": REGRA, "afirmacao": texto, "o_que_faltava": falta,
            "pix_id": int(pix_id), "titulo_id": int(pix["titulo_id"])}


def dar_por_nao_confirmado(con, pix_id: int, *, papel: Any, usuario: str | None,
                           motivo: Any, agora: str) -> dict:
    """O crédito não entrou: o PIX fica NAO_CONFIRMADO, e o título volta a
    andar. ESCREVE. Do oficial e do gerente, com o motivo escrito."""
    if papel not in QUEM_CONFIRMA_A_MAO:
        raise PixError("Dar o PIX por não confirmado é do oficial ou do gerente.")
    razao = " ".join(str(motivo or "").split())
    if _letras(razao) < MINIMO_DO_MOTIVO:
        raise PixError(f"Escreva por que o crédito não se confirmou (pelo menos "
                       f"{MINIMO_DO_MOTIVO} letras) — ex.: «conferido o extrato "
                       f"do período, nenhum PIX desse valor».")
    pix = _ler(con, pix_id, prender=True)
    if not pix:
        raise PixError(f"PIX {pix_id} não encontrado.")
    esperando = pix["situacao"] == AGUARDANDO or (
        pix["situacao"] == CONFIRMADO and not _ato_valido(con, pix.get("ato_id")))
    if not esperando:
        raise PixError("Este PIX já foi resolvido — "
                       + ("o pagamento foi lavrado com ele."
                          if pix["situacao"] == CONFIRMADO
                          else "já está dado por não confirmado."))
    banco(con).escrever(
        """UPDATE pt_pix SET situacao=%s, motivo_nao_confirmado=%s,
               nao_confirmado_em=%s, nao_confirmado_por=%s
            WHERE id=%s""",
        (NAO_CONFIRMADO, razao[:500], agora, usuario, int(pix_id)))
    return {"pix_id": int(pix_id), "titulo_id": int(pix["titulo_id"]),
            "situacao_antes": pix["situacao"], "motivo": razao}


# ------------------------------------------------- o pagamento lavrado


def para_o_pagamento(con, titulo_id: int, pix_id: Any) -> dict:
    """O PIX de crédito conferido que o pagamento vai levar, com a linha
    presa. Só LÊ (e recusa). É `protesto.lancar_pagamento` quem chama."""
    pix = _ler(con, pix_id, prender=True)
    if not pix or int(pix["titulo_id"]) != int(titulo_id):
        raise PixError("Este PIX não é deste título.")
    if pix["situacao"] != CONFIRMADO:
        raise PixError(
            f"O crédito deste PIX ainda não foi conferido "
            f"({SITUACOES.get(pix['situacao'], pix['situacao'])}): sem o crédito "
            f"localizado no banco, PIX não é pagamento.")
    if _ato_valido(con, pix.get("ato_id")):
        raise PixError(f"Este PIX já virou o pagamento (ato {pix['ato_id']}).")
    return dict(pix)


def data_do_pagamento(pix: dict) -> str:
    """A DATA DO PAGAMENTO É A DO CRÉDITO — 29/10/2026, ordem do oficial. A do
    extrato (ou a afirmada na confirmação à mão); sem ela, a do comprovante.
    Nunca a do lançamento: no caso que trouxe esta regra, o crédito entrou em
    16/10 e o pagamento foi lançado em 21/10. Só calcula."""
    return str(pix.get("credito_data") or pix.get("data_pix") or "")[:10]


def para_o_detalhe(pix: dict) -> dict:
    """O que o ato do pagamento guarda do PIX que o sustenta. Só calcula."""
    return {"pix_id": int(pix["id"]), "data_pix": pix["data_pix"],
            "credito_data": pix.get("credito_data"),
            "conferido": pix.get("confirmacao_modo"),
            "conferido_por": pix.get("confirmado_por"),
            "e2eid": pix.get("credito_e2eid") or pix.get("e2eid")}


def identificacao_para_o_livro(pix: dict) -> str:
    """A identificação do PIX na coluna do Livro de Pagamentos. Só calcula.

    A data do crédito não entra aqui: o livro a escreve a partir de
    `data_do_pagamento`, que vale também para quem digitou a identificação."""
    e2e = pix.get("credito_e2eid") or pix.get("e2eid")
    if e2e:
        return f"E2E {e2e}"
    quem = ("no extrato do banco" if pix.get("confirmacao_modo") == PELO_BANCO
            else f"por {pix.get('confirmado_por') or 'quem confirmou'}")
    return f"crédito conferido {quem}"


def vincular_ao_ato(con, pix_id: int, ato_id: int) -> None:
    """Amarra o PIX ao pagamento lavrado com ele. ESCREVE."""
    banco(con).escrever("UPDATE pt_pix SET ato_id=%s WHERE id=%s",
                        (int(ato_id), int(pix_id)))


# ------------------------------------------------------------- pendências


def _feriados(con) -> set[date]:
    from ri_schema import ler_feriados_locais
    bd = banco(con)
    if not bd.tem_tabela("settings"):
        return set()
    linha = bd.um("SELECT value FROM settings WHERE key=%s", ("ri_feriados_locais",))
    return ler_feriados_locais((linha or {}).get("value") or "")


def pendencias_do_pix(con, *, hoje: Any = None, feriados: set[date] | None = None,
                      limite: int = 200) -> list[dict]:
    """O PIX que não virou pagamento há mais de um dia útil. Só LÊ.

    O CONTRATO DOS GANCHOS DO ROTEIRO (`protesto_roteiro.GANCHOS`): cada linha
    traz `titulo_id`, `numero_titulo`, `protocolo` e `explicacao` — a frase
    pronta. Vêm também `pix_id`, `especie` (AGUARDANDO_CREDITO ou LAVRAR),
    `desde` e `dias_uteis`.

    São dois casos, e os dois deixam o título sem o que o devedor pagou: o
    PIX que AGUARDA O CRÉDITO (o título não está pago, e não anda) e o de
    crédito conferido cujo pagamento não se lavrou (o dinheiro entrou, e o
    livro, a situação e a CRA não sabem).
    """
    if not _tem_tabela(con):
        return []
    from ri_schema import dias_uteis_entre
    dia_hoje = _dia(hoje) or date.today()
    if feriados is None:
        feriados = _feriados(con)
    saida: list[dict] = []
    for r in banco(con).ler(
            f"""SELECT p.*, t.numero_titulo, t.protocolo FROM pt_pix p
                  JOIN pt_titulos t ON t.id = p.titulo_id
                 WHERE {_SQL_ESPERANDO}
                 ORDER BY p.id"""):
        especie = "LAVRAR" if r["situacao"] == CONFIRMADO else AGUARDANDO
        desde = _dia(r["confirmado_em"] if especie == "LAVRAR" else r["lancado_em"])
        if not desde:
            continue
        dias = dias_uteis_entre(desde, dia_hoje, feriados)
        if dias <= DIAS_UTEIS_DE_TOLERANCIA:
            continue
        valor = reais(int(r["valor_centavos"]))
        if especie == "LAVRAR":
            explicacao = (
                f"crédito do PIX de R$ {valor} conferido em {_br(r['confirmado_em'])} "
                f"({MODOS.get(r['confirmacao_modo'], r['confirmacao_modo'])}), há "
                f"{dias} dias úteis, e o pagamento ainda não foi lavrado: lance-o "
                f"na ficha do título — até lá, o título não está PAGO e a CRA não "
                f"sabe.")
        else:
            consulta = (f" Última consulta ao extrato: {r['ultima_consulta']}."
                        if r.get("ultima_consulta") else "")
            explicacao = (
                f"PIX de R$ {valor} de {_br(r['data_pix'])}, lançado em "
                f"{_br(r['lancado_em'])} por {r['lancado_por'] or '—'}, aguarda o "
                f"crédito há {dias} dias úteis — o título NÃO está pago.{consulta} "
                f"Confira o crédito no banco, ou o oficial ou o gerente o confirma "
                f"à mão ou o dá por não confirmado.")
        saida.append({"titulo_id": int(r["titulo_id"]),
                      "numero_titulo": r["numero_titulo"],
                      "protocolo": r["protocolo"], "explicacao": explicacao,
                      "pix_id": int(r["id"]), "especie": especie,
                      "situacao": r["situacao"],
                      "valor_centavos": int(r["valor_centavos"]),
                      "desde": desde.isoformat(), "dias_uteis": dias,
                      "atrasado": True})
    # O DINHEIRO RECEBIDO SEM PAGAMENTO LANÇADO entra NO MESMO DIA, e fica
    # atrasado no dia útil seguinte ao crédito (a conciliação ao contrário).
    from ri_schema import soma_dias_uteis
    for c in creditos_sem_pagamento(con, limite=limite):
        dia = _dia(c["dia"])
        if not dia:
            continue
        vence = soma_dias_uteis(dia, 1, feriados)
        atrasado = dia_hoje >= vence
        outros = [x for x in c["candidatos"][1:]]
        explicacao = (
            f"DINHEIRO RECEBIDO SEM PAGAMENTO LANÇADO: {c['tipo'] or 'crédito'} de "
            f"R$ {reais(int(c['valor_centavos']))} em {_br(c['dia'])}"
            + (f", de {c['pagador']}" if c.get("pagador") else "")
            + f", bate com este título ({(c['candidatos'] or [{}])[0].get('motivo') or 'pelo valor'})"
            + (f" — ou com {', '.join(str(x.get('numero_titulo')) for x in outros)}"
               if outros else "")
            + f". Hoje o título está {c.get('situacao_titulo') or '—'}. Lance o "
            f"pagamento (registre o PIX com o comprovante); se o dinheiro não for "
            f"deste título, o oficial ou o gerente o descarta, com o motivo."
            + (f" ATRASADO desde {_br(vence.isoformat())}." if atrasado else
               f" Vence em {_br(vence.isoformat())}."))
        saida.append({"titulo_id": int(c["titulo_id"]) if c.get("titulo_id") else None,
                      "numero_titulo": c.get("numero_titulo"),
                      "protocolo": c.get("protocolo"), "explicacao": explicacao,
                      "credito_id": int(c["id"]), "especie": ESPECIE_CREDITO,
                      "situacao": c["situacao"],
                      "valor_centavos": int(c["valor_centavos"]),
                      "desde": dia.isoformat(), "vence": vence.isoformat(),
                      "atrasado": atrasado,
                      "dias_uteis": dias_uteis_entre(dia, dia_hoje, feriados)})
    return saida[:max(1, int(limite))]


# ------------------------------------------------- o processo da automação


def _auditar(contexto, acao: str, pix_id: int, detalhes: dict, *,
             tabela: str = "pt_pix") -> None:
    """A confirmação pela automação entra em `audit_logs`, fora de
    transação, dizendo quem agiu e a mando de quem (PR #36)."""
    log = getattr(contexto.db, "log", None)
    if log is None:
        return
    import identidade_do_robo as IDR
    processo = getattr(contexto, "processo", None) or {}
    mandante = (str(processo.get("alterado_por") or processo.get("criado_por")
                    or "").strip() or IDR.PELO_RESPONSAVEL)
    try:
        log(None, "automação", acao, tabela, int(pix_id), detalhes,
            agente="automação — PIX do Protesto (extrato do Banco Inter)",
            a_mando_de=mandante)
    except TypeError:
        log(None, "automação", acao, tabela, int(pix_id), detalhes)


def conferir(contexto) -> dict:
    """O processo PROTESTO_PIX_CREDITO — o contrato do `automacao_processos`.

    Ler o extrato é só leitura no banco; CONFIRMAR é gravar o que é da casa,
    e por isso só com `pode_agir`: desligado, ele conta o que espera e não
    consulta nada. Cofre trancado, credencial que falta e banco fora do ar
    são AVISO: o PIX fica esperando, e a rodada seguinte retoma.
    """
    import despesas as DP
    import despesas_inter as INTER
    with contexto.db.connect() as con:
        esperando = aguardando(con)
        sem_pagamento = creditos_sem_pagamento(con)
        cfg = DP.configuracao(con)
    if not contexto.processo.get("pode_agir"):
        return {"situacao": "AVISO" if esperando or sem_pagamento else "OK",
                "relato": (f"{len(esperando)} PIX do Protesto aguardando o crédito; "
                           f"{len(sem_pagamento)} crédito(s) sem pagamento lançado "
                           f"(pode_agir desligado: o processo só conta, e não lê o "
                           f"extrato)."),
                "achados": [{"pix_id": int(p["id"])} for p in esperando],
                "acoes": []}
    try:
        cliente = PC.cliente_da_casa(cfg, pasta=getattr(contexto, "pasta_dados", None))
    except (INTER.CredencialTrancada, INTER.CredencialAusente) as erro:
        return {"situacao": "AVISO", "relato": str(erro), "achados": [], "acoes": []}
    try:
        r = conferir_no_banco(contexto.db, cliente=cliente, agora=contexto.agora,
                              por="automação")
    except INTER.InterError as erro:
        return {"situacao": "AVISO", "relato": f"O extrato não veio: {erro}",
                "achados": [], "acoes": []}
    for c in r["confirmados"]:
        _auditar(contexto, "PROTESTO_PIX_CREDITO_CONFERIDO", c["pix_id"],
                 {"titulo_id": c["titulo_id"], "credito_id": c["credito_id"],
                  "credito_data": c["credito_data"]})
    for n in r["sem_pagamento"]:
        _auditar(contexto, "PROTESTO_CREDITO_SEM_PAGAMENTO", n["id"],
                 {"titulo_id": n["titulo_id"], "dia": n["dia"], "tipo": n["tipo"]},
                 tabela="pt_creditos_banco")
    with contexto.db.connect() as con:
        abertos = creditos_sem_pagamento(con)
    achados = ([{"tipo": "SEM_CREDITO", **s} for s in r["sem_credito"]]
               + [{"tipo": "FORA_DA_JANELA", "pix_id": i} for i in r["fora_da_janela"]]
               + [{"tipo": ESPECIE_CREDITO, "credito_id": int(c["id"]),
                   "titulo_id": c.get("titulo_id"), "dia": c["dia"]}
                  for c in abertos])
    relato = (f"{len(r['confirmados'])} PIX com o crédito localizado no extrato; "
              f"{len(r['sem_credito'])} sem crédito localizado; "
              f"{len(r['fora_da_janela'])} fora dos 90 dias do extrato; "
              f"{len(abertos)} crédito(s) recebido(s) sem pagamento lançado "
              f"({len(r['sem_pagamento'])} novo(s)) — {r['lidas']} crédito(s) lido(s).")
    return {"situacao": "AVISO" if achados else "OK", "relato": relato,
            "achados": achados,
            "acoes": [f"PIX {c['pix_id']}: crédito conferido" for c in r["confirmados"]]}
