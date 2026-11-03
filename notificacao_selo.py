"""O selo da notificação pessoal — retificação e usucapião, o mesmo caminho.

O item é o 16.23 da tabela do RI: intimação ou notificação, por pessoa, em
cumprimento de lei ou de determinação judicial, inclusive por edital. O
caminho é o dos outros atos do capítulo 16 que não são ato de matrícula
(`/selo/imovel/atos-em-geral`), o mesmo do arquivamento (16.39) e da
conferência de documento (16.42).

QUEM PAGA É O PROTOCOLO DO CAIXA ligado ao processo. Sem o item 16.23 com
unidade sobrando, não se sela: avisa-se e deixa lançar o item naquele
protocolo. Selo que não sai devolve a unidade e não apaga a notificação.

O PAPEL FINAL SÓ SAI SELADO. Antes disso a rota entrega prévia, com a frase
``SEM SELO — NÃO ENTREGAR`` no alto. Robô não chega aqui: quem sela é gente,
e a rota responde 403.
"""
from __future__ import annotations

from typing import Any

from bd_nativo import banco

CODIGO = "16.23"
CAMINHO = "/selo/imovel/atos-em-geral"
DESCRICAO = (
    "Intimação ou notificação, por pessoa, em cumprimento de lei ou de "
    "determinação judicial, inclusive por edital")
AVISO_SEM_SELO = "SEM SELO — NÃO ENTREGAR"
TABELAS = frozenset({"rt_confrontantes", "us_movimentos"})


class NotificacaoSeloError(ValueError):
    """Recusa de regra, com a frase para o balcão. `pode_lancar` abre o botão."""

    def __init__(self, mensagem: str, *, pode_lancar: bool = False):
        super().__init__(mensagem)
        self.pode_lancar = pode_lancar


def _tabela(nome: str) -> str:
    if nome not in TABELAS:
        raise NotificacaoSeloError(f"Não selo notificação em {nome}.")
    return nome


def item_do_protocolo(con, protocolo_id: int) -> dict | None:
    """O 16.23 com unidade sobrando, se houver. Só lê."""
    import caixa_protocolo as CXP
    if not protocolo_id:
        return None
    for item in CXP.itens_disponiveis(con, int(protocolo_id)):
        if str(item.get("codigo_ato") or "").strip() == CODIGO and int(item.get("saldo") or 0) >= 1:
            return item
    return None


def preparar(con, *, protocolo_id: Any, tabela: str, ato_id: int,
             selo_atual: Any) -> dict:
    """Confere se esta notificação pode ganhar o 16.23. Só lê."""
    _tabela(tabela)
    if str(selo_atual or "").strip():
        raise NotificacaoSeloError(
            "Esta notificação já tem selo. Um segundo selo cobraria de novo "
            "a mesma intimação.")
    if not str(protocolo_id or "").strip():
        raise NotificacaoSeloError(
            "Ligue o protocolo de recepção do Caixa ao processo antes de "
            "selar a notificação. É nele que está (ou vai entrar) o item 16.23.")
    bd = banco(con)
    protocolo = bd.um("SELECT * FROM cx_protocolos WHERE id = %s",
                      (int(protocolo_id),))
    if not protocolo:
        raise NotificacaoSeloError("Não achei o protocolo de recepção ligado ao processo.")
    import caixa_protocolo as CXP
    if CXP.esta_encerrado(protocolo.get("situacao")):
        raise NotificacaoSeloError(
            f"O protocolo {protocolo.get('numero')} está encerrado. Reabra-o "
            "antes de selar a notificação.")
    item = item_do_protocolo(bd, int(protocolo_id))
    if not item:
        raise NotificacaoSeloError(
            f"O protocolo {protocolo.get('numero')} não tem o item 16.23 "
            "(intimação em cumprimento de lei, inclusive edital) com unidade "
            "sobrando. Lance o item neste protocolo, receba ou marque a "
            "gratuidade, e sele.",
            pode_lancar=True)
    return {"protocolo": dict(protocolo), "item": item,
            "gratuito": CXP.item_gratuito(item, bd)}


def consumir(con, *, item_id: int, tabela: str, ato_id: int,
             agora: str, quem: str | None) -> None:
    """Gasta uma unidade do 16.23 nesta notificação. ESCREVE."""
    import caixa_protocolo as CXP
    gastas = CXP.consumir_item(
        con, int(item_id), ato_id=int(ato_id), tabela=_tabela(tabela),
        agora=agora, quantas=1, origem=CXP.ORIGEM_CONSUMO, quem=quem)
    if gastas < 1:
        raise NotificacaoSeloError(
            "A unidade do item 16.23 acabou enquanto o selo era pedido. "
            "Nada foi selado: confira o protocolo e tente de novo.")


def devolver(con, *, item_id: int, tabela: str, ato_id: int) -> None:
    """Devolve a unidade quando o selo não sai. ESCREVE. A notificação fica."""
    import caixa_protocolo as CXP
    bd = banco(con)
    CXP.devolver_item(bd, int(item_id), quantas=1)
    if bd.tem_tabela("cx_item_do_ato"):
        bd.escrever(
            """DELETE FROM cx_item_do_ato
                WHERE tabela = %s AND ato_id = %s AND item_id = %s
                  AND origem = %s""",
            (_tabela(tabela), int(ato_id), int(item_id), CXP.ORIGEM_CONSUMO))


def envelope(*, escrevente: Any, versao_tabela: Any, nome: str,
             documento: str = "", isento: bool = False,
             motivo_isencao: str = "") -> dict:
    """O pedido AtosEmGeral do 16.23, quantidade 1. Só calcula.

    A gratuidade leva `isento` com motivo escrito — a mesma forma do
    arquivamento do RI. REURB-S, REURB-E e misto entram por esse motivo,
    como nos outros atos.
    """
    if not str(escrevente or "").strip() or not str(versao_tabela or "").strip():
        raise NotificacaoSeloError(
            "O selo da notificação não sai sem o escrevente e a versão da "
            "tabela de custas (Administrativo → Configurações).")
    if isento and not str(motivo_isencao or "").strip():
        raise NotificacaoSeloError(
            "Notificação gratuita precisa do motivo escrito (REURB-S, REURB-E, "
            "misto, ou o fundamento da isenção). É ele que a correição lê.")
    doc = "".join(c for c in str(documento or "") if c.isdigit())
    parte = []
    if str(nome or "").strip():
        parte.append({"nome": str(nome).strip(),
                      "documento": doc} if doc else {"nome": str(nome).strip()})
    pedido = {
        "escrevente": str(escrevente).strip(),
        "partes": {"nomePartes": [], "parteAto": parte},
        "quantidade": 1,
        "ato": {"codigo": CODIGO,
                "codigoTabelaCusta": str(versao_tabela).strip()},
    }
    if isento:
        pedido["isento"] = {"value": True,
                            "motivo": str(motivo_isencao).strip().upper()}
    return pedido


def lancar_item(con, protocolo_id: int) -> dict:
    """Acrescenta um 16.23 ao protocolo, pelo preço da tabela vigente. ESCREVE.

    É o mesmo cálculo de quem lança o item na ficha do protocolo. Sem o código
    na tabela vigente, não se inventa preço.
    """
    import emolumentos as EMOL
    bd = banco(con)
    protocolo = bd.um("SELECT id, numero FROM cx_protocolos WHERE id = %s",
                      (int(protocolo_id),))
    if not protocolo:
        raise NotificacaoSeloError("Não achei o protocolo para lançar o 16.23.")
    codigo = EMOL.servico_pelo_codigo_tj(bd, CODIGO)
    if codigo is None:
        raise NotificacaoSeloError(
            "Não encontrei o item 16.23 na tabela de emolumentos vigente. "
            "Sem o preço da tabela não lanço o item.")
    item = EMOL.calcular_item(bd, servico=codigo, quantidade=1)
    if not item:
        raise NotificacaoSeloError(
            "A tabela vigente não devolveu valor para o item 16.23.")
    novo = int(bd.escrever(
        """INSERT INTO cx_protocolo_atos
           (protocolo_id, descricao, codigo_ato, quantidade, valor_total,
            emolumentos, ferc, fadep, femp, ferrfis, servico_codigo,
            base_calculo, origem_valor)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(protocolo_id), item["descricao"] or DESCRICAO, CODIGO,
         item["quantidade"], item["total"], item["emolumentos"],
         item["ferc"], item["fadep"], item["femp"], item["ferrfis"],
         item["servico_codigo"], item["base_calculo"], item["origem_valor"]))[0]["id"])
    return {"id": novo, "protocolo_numero": protocolo["numero"],
            "total": item["total"]}


def selar(db, pasta_de_dados, *, tabela: str, ato_id: int, protocolo_id: Any,
         nome: str, documento: str, escrevente: str, versao_tabela: str,
         cns: Any, agora: str, quem: str | None, isento: bool,
         motivo_isencao: str, selo_atual: Any) -> dict:
    """Pede o 16.23 e guarda o carimbo. FALA COM A REDE, fora da transação.

    Selo que não sai devolve a unidade e não mexe na notificação. Devolve
    `{ok, motivo, numero, pode_lancar}`.
    """
    import ato_selado as AS
    try:
        with db.connect() as con:
            prep = preparar(con, protocolo_id=protocolo_id, tabela=tabela,
                            ato_id=ato_id, selo_atual=selo_atual)
            if prep["gratuito"] and not isento:
                isento = True
                motivo_isencao = motivo_isencao or "ATO GRATUITO"
            pedido = envelope(
                escrevente=escrevente, versao_tabela=versao_tabela, nome=nome,
                documento=documento, isento=isento, motivo_isencao=motivo_isencao)
            item_id = int(prep["item"]["id"])
        with db.transaction() as con:
            consumir(con, item_id=item_id, tabela=tabela, ato_id=ato_id,
                     agora=agora, quem=quem)
    except NotificacaoSeloError as erro:
        return {"ok": False, "motivo": str(erro), "numero": "",
                "pode_lancar": erro.pode_lancar}
    res = AS.selar_o_ato_lavrado(
        db, pasta_de_dados, tabela=tabela, ato_id=int(ato_id),
        tipo="NOTIFICACAO", atribuicao="IMOVEL", agora=agora, cns=cns,
        usuario=quem, dados=pedido, caminho=CAMINHO,
        referencia=f"{tabela}:{int(ato_id)}:{CODIGO}:1")
    if not res.get("selado") or not res.get("numero"):
        with db.transaction() as con:
            devolver(con, item_id=item_id, tabela=tabela, ato_id=ato_id)
        return {"ok": False, "motivo": str(res.get("motivo") or "o selador não devolveu número"),
                "numero": "", "pode_lancar": False}
    numero = str(res["numero"])
    with db.connect() as con:
        linha = banco(con).um("SELECT texto FROM sd_selos WHERE numero = %s", (numero,))
        from notas_selo import marca_do_selo
        texto = (linha["texto"] if linha else "") or ""
        qr = (marca_do_selo(numero).get("qr") or "") if numero else ""
    with db.transaction() as con:
        completar(con, tabela, ato_id, numero=numero, texto=texto, qr=qr,
                  quando=agora, quem=quem)
    return {"ok": True, "motivo": "", "numero": numero, "pode_lancar": False,
            "texto": texto}


def completar(con, tabela: str, ato_id: int, *, numero: str, texto: str,
              qr: str, quando: str, quem: str | None) -> None:
    """Guarda o carimbo na notificação. ESCREVE. O número já está em `selo`."""
    nome = _tabela(tabela)
    banco(con).escrever(
        f"""UPDATE {nome}
               SET selo_texto = %s, selo_qr = %s, selo_em = %s, selo_por = %s,
                   selo_item = %s
             WHERE id = %s AND selo = %s""",
        (texto or None, qr or None, quando, quem or None, CODIGO,
         int(ato_id), str(numero)))


def marcar_impressao(con, tabela: str, ato_id: int, *, quando: str) -> None:
    """A impressão final, a que já leva selo. ESCREVE."""
    nome = _tabela(tabela)
    banco(con).escrever(
        f"""UPDATE {nome} SET impresso_em = COALESCE(impresso_em, %s)
             WHERE id = %s AND COALESCE(selo, '') <> ''""",
        (quando, int(ato_id)))


def corpo_do_papel(teor: str, *, selado: bool, selo_texto: str = "",
                   selo_numero: str = "") -> str:
    """O ODF da notificação. Prévia sem selo leva a tarja. Só calcula."""
    from ri_odt import carimbo_do_selo_odf, texto_para_odf
    miolo = texto_para_odf(teor)
    if not selado:
        tarja = texto_para_odf(
            f"{AVISO_SEM_SELO}\n"
            "Prévia. Este papel não se entrega enquanto a notificação não "
            "estiver selada.")
        return tarja + "\n" + miolo
    carimbo = carimbo_do_selo_odf(selo_texto, por_fileira=1) if selo_texto else ""
    if not carimbo:
        from notas_selo import marca_do_selo
        marca = marca_do_selo(selo_numero) if selo_numero else {}
        consulta = marca.get("qr_texto") or ""
        carimbo = texto_para_odf(
            "SELO DIGITAL DO TJMA\n"
            + (selo_texto or f"Selo: {selo_numero}. Ato: {CODIGO}.")
            + (f"\nConsulte em {consulta}" if consulta else ""))
    return miolo + "\n" + carimbo
