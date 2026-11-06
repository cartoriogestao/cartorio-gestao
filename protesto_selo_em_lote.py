"""Selo do protesto já lavrado, em lote, com o emolumento DEVIDO.

O CASO (05/11/2026)
    O lote «Gerar protesto» e o robô lavram o ato e param: o selo é chamada de
    rede, e segurá-la dentro da lavratura poria a casa no `busy_timeout`. O
    escrevente precisa selar esses atos já lavrados, e lançar o emolumento no
    caixa como devido — o dinheiro só entra quando pagam para cancelar ou
    desistir. Este módulo não sela: quem fala com o aparelho é a rota, no
    clique humano. Aqui se lista e se deixa devido.

O QUE ESTE MÓDULO FAZ
    - `pendentes`: lê e separa o que este clique pode selar do que fica de
      fora. Não escreve.
    - `preparar`: recusa o robô, trava a linha (`FOR UPDATE`) e chama
      `protesto_posteriori.diferir`. A cobertura do selo sai como DIFERIDO
      quando a rota pede o selo — `ato_selado.cobrir_o_selo` lê o devido do
      próprio ato. Não abre lançamento e não emite recibo.

QUEM ENTRA
    Ato de tipo PROTESTO, não cancelado, origem MANUAL (a casa lavrou; o
    acervo e o E-Ofício ficam de fora), sem selo na coluna, sem linha em
    `sd_selos`, sem cobertura CONFIRMADA ou RESERVADA, título PROTESTADO, regime
    diferido (o antecipado de balcão não entra: aquele se cobra na hora) e com
    item gerado pela tabela (a faixa 17.1.N que cobre o 17.1). Sem item, não
    se adivinha preço.

O LIMITE
    `LIMITE_POR_CLIQUE` é 10. A tela mostra a fila inteira; cada clique prepara
    no máximo dez. O escrevente revê a lista antes de clicar. Nenhum id de ato
    está cravado aqui.
"""
from __future__ import annotations

from typing import Any

import ato_selado as AS
import protesto_posteriori as POST
import selo_robo as SR
from bd_nativo import banco

TABELA = "pt_atos"
TIPO = "PROTESTO"
ORIGEM_DA_CASA = "MANUAL"
MARCA_DO_ACERVO = "EOFICIO"

#: A auditoria do clique. O dinheiro não entra: `entrou_no_caixa` vai false.
ACAO_DA_AUDITORIA = "PROTESTO_SELADO_DEPOIS"

#: Dez por clique. Vinte selos são vinte chamadas de rede; o lote de lavrar
#: não sela por isso, e este botão também não esvazia a fila numa tacada só.
LIMITE_POR_CLIQUE = 10

MSG_ROBO = ("Robô não sela. O protesto lavrado sem selo é selado pelo "
            "escrevente, em pessoa.")


class SeloEmLoteError(ValueError):
    """Impedimento do selo em lote, com frase pronta para o balcão."""


def _int(valor: Any) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _dia(linha: dict, hoje: str) -> str:
    """O dia da tabela é o dia do ato. Sem data no ato, vale o dia do clique."""
    dia = str(linha.get("data_ato") or "")[:10]
    return dia or str(hoje or "")[:10]


def _ficha(linha: dict, motivo: str, itens: list[dict]) -> dict:
    codigo = ""
    if itens:
        codigo = str(itens[0].get("codigo_tj") or "")
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
    """Protestos lavrados com a coluna do selo vazia. Só LÊ.

    Cancelado, outro tipo e título que não está PROTESTADO nem entram na
    conta: não são pendência deste botão. O que entra e não pode ser selado
    aqui sai em `de_fora`, com o motivo.
    """
    filtro = ""
    params: list[Any] = []
    if titulo_id is not None:
        filtro = " AND a.titulo_id = %s"
        params.append(int(titulo_id))
    return bd.ler(
        f"""SELECT a.id AS ato_id, a.titulo_id, a.tipo, a.origem, a.selo,
                   a.cancelado, a.data_ato, t.situacao, t.numero_titulo,
                   t.protocolo, t.origem AS origem_titulo,
                   (SELECT d.nome FROM pt_devedores d
                     WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1) AS devedor
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
             WHERE a.tipo = %s
               AND COALESCE(a.cancelado, 0) = 0
               AND t.situacao = 'PROTESTADO'
               AND (a.selo IS NULL OR btrim(a.selo) = ''){filtro}
             ORDER BY a.id""",
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
    """'selavel' ou 'de_fora', o motivo, e os itens da tabela. Só LÊ."""
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
        return "de_fora", "antecipado (balcão): o emolumento entra na hora, e este botão não cobra", []
    itens = POST.itens_do_ato_pela_tabela(con, titulo_id, TIPO, data=dia)
    if not itens:
        return "de_fora", "a tabela não gerou o item do protesto (faixa 17.1)", []
    return "selavel", "", itens


def pendentes(con, *, titulo_id: int | None = None, hoje: str) -> dict:
    """Separa seláveis e os que ficam de fora. Só LÊ.

    `titulo_id`, quando vem, restringe à ficha daquele título. A lista inteira
    volta: o limite de dez é do clique (`preparar`), não da leitura. O
    escrevente vê quem vai ser selado antes de apertar o botão.
    """
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
    """A linha do ato, presa até o fim da transação. LÊ com `FOR UPDATE`."""
    return bd.um(
        """SELECT a.id AS ato_id, a.titulo_id, a.tipo, a.origem, a.selo,
                  a.cancelado, a.data_ato, t.situacao, t.numero_titulo,
                  t.protocolo, t.origem AS origem_titulo,
                  (SELECT d.nome FROM pt_devedores d
                    WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1) AS devedor
             FROM pt_atos a
             JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.id = %s
            FOR UPDATE OF a""",
        (int(ato_id),))


def preparar(con, *, eh_robo: Any, usuario: str | None, agora: str,
             ato_id: int | None = None, hoje: str | None = None) -> dict:
    """Deixa DEVIDO o que este clique vai selar. ESCREVE. Não sela.

    O robô é recusado antes de qualquer escrita. Cada ato escolhido é lido de
    novo com `FOR UPDATE` e reclassificado: o que deixou de servir sai da
    leva. `ato_id` é o botão da ficha — um ato, e se ele não serve a frase
    diz por quê. Sem `ato_id`, vale a fila, até `LIMITE_POR_CLIQUE`.

    O selo é da rota, fora desta transação: a cobertura DIFERIDO só existe
    depois que `diferir` gravou, e a chamada de rede não pode segurar a trava.
    """
    if eh_robo or SR.usuario_e_robo():
        raise SeloEmLoteError(MSG_ROBO)
    dia_do_clique = str(hoje or agora or "")[:10]
    pedido = _int(ato_id)
    quadro = pendentes(con, hoje=dia_do_clique)
    if pedido is not None:
        escolhidos = [p for p in quadro["selaveis"] if int(p["ato_id"]) == pedido]
        if not escolhidos:
            motivo = next((p["motivo"] for p in quadro["de_fora"]
                           if int(p["ato_id"]) == pedido), "")
            raise SeloEmLoteError(
                f"O ato {pedido} não entra neste selo"
                + (f": {motivo}" if motivo else
                   ". Não é protesto lavrado pendente de selo."))
    else:
        escolhidos = quadro["selaveis"][:LIMITE_POR_CLIQUE]

    bd = banco(con)
    prontos: list[dict] = []
    for item in escolhidos:
        preso = _travar(bd, int(item["ato_id"]))
        if not preso:
            if pedido is not None:
                raise SeloEmLoteError(f"O ato {pedido} não foi encontrado.")
            continue
        classe, motivo, itens = _classificar(con, bd, preso, hoje=dia_do_clique)
        if classe != "selavel":
            if pedido is not None:
                raise SeloEmLoteError(
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
