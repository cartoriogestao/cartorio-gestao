"""Selo da intimação já lavrada, com o emolumento DEVIDO.

A intimação da casa sela pelo item 17.2, natureza pessoal ou edital conforme
o modo gravado no ato. O lote de editais e a entrega lavam o ato e param: o
selo é rede, e o botão do protesto só lista protesto. Este módulo lista e
deixa devido. Quem fala com o aparelho é a rota, no clique humano.

Entra intimação não cancelada, origem MANUAL, sem selo, sem razão, sem
cobertura viva, regime diferido e com o 17.2 na tabela. O acervo fica de
fora. O título pode já estar protestado: o selo é da intimação, não do
protesto. Dez por clique. O robô não sela.
"""
from __future__ import annotations

from typing import Any

import ato_selado as AS
import protesto_posteriori as POST
import selo_robo as SR
from bd_nativo import banco

TABELA = "pt_atos"
TIPO = "INTIMACAO"
ORIGEM_DA_CASA = "MANUAL"
MARCA_DO_ACERVO = "EOFICIO"
ACAO_DA_AUDITORIA = "PROTESTO_INTIMACAO_SELADA_DEPOIS"
LIMITE_POR_CLIQUE = 10
MSG_ROBO = ("Robô não sela. A intimação lavrada sem selo é selada pelo "
            "escrevente, em pessoa.")


class SeloIntimacaoError(ValueError):
    """Impedimento do selo da intimação, com frase pronta para o balcão."""


def _int(valor: Any) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _dia(linha: dict, hoje: str) -> str:
    dia = str(linha.get("data_ato") or "")[:10]
    return dia or str(hoje or "")[:10]


def _ficha(linha: dict, motivo: str, itens: list[dict]) -> dict:
    codigo = str(itens[0].get("codigo_tj") or "") if itens else ""
    return {
        "ato_id": int(linha["ato_id"] if "ato_id" in linha else linha["id"]),
        "titulo_id": int(linha["titulo_id"]),
        "numero_titulo": linha.get("numero_titulo") or "",
        "protocolo": linha.get("protocolo") or "",
        "devedor": linha.get("devedor") or "",
        "data_ato": str(linha.get("data_ato") or "")[:10],
        "motivo": motivo,
        "itens": itens,
        "codigo_tj": codigo,
    }


def _ler_sem_selo(bd, titulo_id: int | None) -> list[dict]:
    filtro = ""
    params: list[Any] = []
    if titulo_id is not None:
        filtro = " AND a.titulo_id = %s"
        params.append(int(titulo_id))
    return bd.ler(
        f"""SELECT a.id AS ato_id, a.titulo_id, a.tipo, a.origem, a.selo,
                   a.cancelado, a.data_ato, t.situacao, t.numero_titulo,
                   t.protocolo,
                   (SELECT d.nome FROM pt_devedores d
                     WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1) AS devedor
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
             WHERE a.tipo = %s
               AND COALESCE(a.cancelado, 0) = 0
               AND (a.selo IS NULL OR btrim(a.selo) = ''){filtro}
             ORDER BY a.data_ato, a.id""",
        [TIPO, *params])


def _tem_selo_no_razao(bd, ato_id: int) -> bool:
    if not bd.tem_tabela("sd_selos"):
        return False
    return bd.um(
        """SELECT 1 AS tem FROM sd_selos
            WHERE tabela = %s AND ato_id = %s AND cancelado_em IS NULL
            LIMIT 1""",
        (TABELA, int(ato_id))) is not None


def _tem_cobertura_que_conta(bd, ato_id: int) -> bool:
    if not bd.tem_tabela("cx_selo_coberturas"):
        return False
    return bd.um(
        """SELECT 1 AS tem FROM cx_selo_coberturas
            WHERE tabela = %s AND ato_id = %s
              AND situacao IN (%s, %s)
            LIMIT 1""",
        (TABELA, int(ato_id), AS.CONFIRMADA, AS.RESERVADA)) is not None


def _classificar(con, bd, linha: dict, *, hoje: str) -> tuple[str, str, list]:
    ato_id = int(linha["ato_id"] if "ato_id" in linha else linha["id"])
    origem = str(linha.get("origem") or "").strip().upper()
    if origem == MARCA_DO_ACERVO or origem != ORIGEM_DA_CASA:
        texto = ("acervo ou E-Ofício" if origem == MARCA_DO_ACERVO
                 else f"origem {origem or 'vazia'}, fora do que a casa lavrou")
        return "de_fora", texto, []
    if _tem_selo_no_razao(bd, ato_id):
        return "de_fora", "já tem selo no razão", []
    if _tem_cobertura_que_conta(bd, ato_id):
        return "de_fora", "já tem cobertura de selo", []
    dia = _dia(linha, hoje)
    titulo_id = int(linha["titulo_id"])
    cobranca = POST.cobranca_do_ato(con, titulo_id, TIPO, hoje=dia)
    if not cobranca.get("diferir"):
        return "de_fora", ("antecipado (balcão): o emolumento entra na hora, "
                           "e este botão não cobra"), []
    itens = POST.itens_do_ato_pela_tabela(con, titulo_id, TIPO, data=dia)
    if not itens:
        return "de_fora", "a tabela não gerou o item da intimação (17.2)", []
    return "selavel", "", itens


def pendentes(con, *, titulo_id: int | None = None, hoje: str) -> dict:
    """Separa o que este clique sela do que fica de fora. Só LÊ."""
    bd = banco(con)
    selaveis: list[dict] = []
    de_fora: list[dict] = []
    for linha in _ler_sem_selo(bd, titulo_id):
        classe, motivo, itens = _classificar(con, bd, linha, hoje=hoje)
        ficha = _ficha(linha, motivo, itens)
        (selaveis if classe == "selavel" else de_fora).append(ficha)
    return {"selaveis": selaveis, "de_fora": de_fora,
            "limite": LIMITE_POR_CLIQUE}


def _travar(bd, ato_id: int) -> dict | None:
    return bd.um(
        """SELECT a.id AS ato_id, a.titulo_id, a.tipo, a.origem, a.selo,
                  a.cancelado, a.data_ato, t.numero_titulo, t.protocolo,
                  (SELECT d.nome FROM pt_devedores d
                    WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1) AS devedor
             FROM pt_atos a
             JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.id = %s
            FOR UPDATE OF a""",
        (int(ato_id),))


def preparar(con, *, eh_robo: Any, usuario: str | None, agora: str,
             ato_id: int | None = None, hoje: str | None = None) -> dict:
    """Deixa DEVIDO o 17.2 do que este clique vai selar. ESCREVE. Não sela."""
    if eh_robo or SR.usuario_e_robo():
        raise SeloIntimacaoError(MSG_ROBO)
    dia_do_clique = str(hoje or agora or "")[:10]
    pedido = _int(ato_id)
    quadro = pendentes(con, hoje=dia_do_clique)
    if pedido is not None:
        escolhidos = [p for p in quadro["selaveis"] if int(p["ato_id"]) == pedido]
        if not escolhidos:
            motivo = next((p["motivo"] for p in quadro["de_fora"]
                           if int(p["ato_id"]) == pedido), "")
            raise SeloIntimacaoError(
                f"O ato {pedido} não entra neste selo"
                + (f": {motivo}" if motivo else
                   ". Não é intimação lavrada pendente de selo."))
    else:
        escolhidos = quadro["selaveis"][:LIMITE_POR_CLIQUE]

    prontos: list[dict] = []
    for item in escolhidos:
        preso = _travar(banco(con), int(item["ato_id"]))
        if not preso:
            if pedido is not None:
                raise SeloIntimacaoError(f"O ato {pedido} não foi encontrado.")
            continue
        classe, motivo, itens = _classificar(con, banco(con), preso,
                                            hoje=dia_do_clique)
        if classe != "selavel":
            if pedido is not None:
                raise SeloIntimacaoError(
                    f"O ato {pedido} não entra neste selo: {motivo}")
            continue
        registro = POST.diferir(
            con, titulo_id=int(preso["titulo_id"]), ato_id=int(preso["ato_id"]),
            tipo_ato=TIPO, itens=itens, data_do_ato=_dia(preso, dia_do_clique),
            agora=agora, usuario=usuario)
        ficha = _ficha(preso, "", itens)
        ficha["estimado_centavos"] = int(registro.get("estimado_centavos") or 0)
        prontos.append(ficha)
    return {"prontos": prontos, "limite": LIMITE_POR_CLIQUE}
