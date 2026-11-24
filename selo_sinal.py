"""O sinal do selo na tela do ato: verde (o selo sai) ou vermelho (falta algo). Só LÊ.

Pedido do oficial em 24/11/2026: «vamos fazer esse sinal verde e vermelho».

O QUE ACONTECIA (réplica, 26/10 a 23/11/2026): 67 selos não saíram porque o
protocolo não tinha o item do código com unidade sobrando, ou o item não
estava pago. Cada um é lavrar, ler o recado, ir a «Selo e caixa», acertar e
pedir de novo — de 1 a 28 minutos, e às vezes um estorno de reserva. A tela
do ato já mostrava a lista de protocolos (`_protocolo_do_selo.html`), mas:

- a coluna «Cobre?» dizia «sim» pelo GRUPO da tabela, e não pelo código: o
  protocolo com o 13.17.4 pago aparecia como «sim» para a firma comum, que
  pede o 13.17.2 (10 dos 14 reconhecimentos suspensos);
- quem não escolhia nada ficava com o protocolo que ATENDIA antes — de outro
  cliente, às vezes de outra atribuição — e a tela não dizia que ele não
  servia (50 das 67 suspensões, sem escolha na tela);
- o ato do RI (registro e averbação) não conferia nada antes de lavrar.

O SINAL FAZ A MESMA CONTA DO SELO, sem gravar: `ato_selado.cobrir_o_selo`
procura (1) o item ligado ao ato — no RI, os itens marcados na tela —, (3) o
item do MESMO código no protocolo em atendimento, pago, diferido (Protesto)
ou que o depósito prévio paga, e (4) a liberação do oficial, que ato novo não
tem. Aqui se pergunta o mesmo ao protocolo que a tela vai usar: o marcado na
lista (vira o «em atendimento» antes do selo) ou, sem marca, o que já está em
atendimento.

NÃO BLOQUEIA (decisão do pedido): com vermelho o botão de lavrar avisa e
oferece «assim mesmo». Quem decide continua sendo quem lavra, e o selo
continua saindo DEPOIS do ato (27/08/2026) com o protocolo que o escrevente
confirmou (22/10/2026).
"""
from __future__ import annotations

from typing import Any, Callable

from bd_nativo import banco

VERDE = "verde"
VERMELHO = "vermelho"
AMARELO = "amarelo"

TITULOS = {
    VERDE: "Selo: pode lavrar",
    VERMELHO: "Selo: falta acertar o caixa antes de lavrar",
    AMARELO: "Selo: confira o item antes de lavrar",
}

NOMES_DOS_GRUPOS = {"13": "Notas", "14": "Registro Civil", "15": "RTD e PJ",
                    "16": "Registro de Imóveis", "17": "Protesto"}


def _sim(valor: Any) -> bool:
    return str(valor or "").strip().lower() in {"1", "on", "true", "sim", "s", "yes"}


def _inteiro(valor: Any) -> int | None:
    bruto = str(valor or "").strip()
    return int(bruto) if bruto.isdigit() else None


def _unidades(n: int) -> str:
    return "1 unidade" if n == 1 else f"{n} unidades"


def _hora(desde: Any) -> str:
    texto = str(desde or "")
    return texto[11:16] if len(texto) >= 16 else ""


# --------------------------------------------------------------- o que a tela pede

def pedidos_do_reconhecimento(con, form) -> dict:
    """O item da firma pela espécie, veículo e financeiro — um selo por cartão. Só LÊ.

    A mesma escolha da rota (`notas_schema.servico_do_reconhecimento`): a
    lista da tela não sabe qual dos três itens, a rota sabe.
    """
    from notas_schema import servico_do_reconhecimento
    servico = servico_do_reconhecimento(
        str(form.get("especie") or "SEMELHANCA").upper(),
        form.get("veiculo") == "1", form.get("financeiro") == "1")
    codigo = _codigo_do_servico(con, servico)
    if not codigo:
        return {}
    cartoes = [c for c in form.getlist("cartao_id") if str(c or "").strip()]
    return {"pedidos": [(codigo, max(1, len(cartoes)))]}


def pedidos_do_cartao(con, form) -> dict:
    """O cartão de assinatura sela na abertura: o item do serviço CARTAO. Só LÊ."""
    from notas_schema import SERVICOS
    codigo = _codigo_do_servico(con, SERVICOS["CARTAO"])
    return {"pedidos": [(codigo, 1)]} if codigo else {}


def pedidos_da_certidao_do_ri(con, form) -> dict:
    """Os itens da certidão do RI pelo tipo, as folhas e a marca da ONR. Só LÊ.

    Folhas em branco («auto») contam uma: o número de folhas só se sabe com o
    teor montado, e o sinal avisa da folha acrescida.
    """
    import ato_selado as AS
    if "tipo" not in form:
        # A certidão negativa do indicador não tem o campo: o código já vem
        # da tela (16.24.1), nos pedidos da lista.
        return {}
    tipo = str(form.get("tipo") or "INTEIRO_TEOR").strip().upper()
    folhas = _inteiro(form.get("folhas"))
    digital = _sim(form.get("certidao_digital_onr"))
    try:
        itens = AS.itens_da_certidao_do_ri(tipo, folhas or 1, digital=digital)
    except AS.AtoError:
        return {}
    avisos = []
    if digital:
        avisos.append("Certidão digital da ONR: o selo sai se o pedido estiver "
                      "pago na ONR.")
    elif not folhas and AS.ITEM_DA_FOLHA_ACRESCIDA_DO_RI.get(itens[0][0]):
        avisos.append(f"Se a certidão passar de uma folha, cada folha a mais pede "
                      f"o item {AS.ITEM_DA_FOLHA_ACRESCIDA_DO_RI[itens[0][0]]} "
                      f"no protocolo. Informe as folhas para conferir.")
    return {"pedidos": itens, "avisos": avisos, "online": digital}


def pedidos_do_ato_do_ri(con, form) -> dict:
    """Os selos do registro ou averbação, na mesma ordem da rota que lavra. Só LÊ.

    1. «Vários selos» (código + quantidade), se preenchido;
    2. senão, os itens MARCADOS do protocolo do caixa — eles ficam ligados ao
       ato e pagam o selo pelo passo 1 da cobertura;
    3. senão, os itens do catálogo e, por fim, o «outro código».
    """
    import caixa_protocolo as CXP
    if "codigo_tj_selo" not in form:
        # Só o formulário de LAVRAR tem «Vários selos»; o arquivamento e a
        # abertura trazem o código pronto nos pedidos da lista.
        return {}
    pedidos: list[tuple[str, int]] = []
    codigos = [str(x or "").strip() for x in form.getlist("codigo_tj_selo")]
    qtds = form.getlist("qtd_selo")
    for i, cod in enumerate(codigos):
        if not cod:
            continue
        q = _inteiro(qtds[i] if i < len(qtds) else "1") or 1
        pedidos.append((cod, max(1, min(q, 50))))
    marcados: list[int] = []
    if not pedidos:
        ids = {n for n in map(_inteiro, form.getlist("protocolo_item_id")) if n}
        caixa = _inteiro(form.get("protocolo_id"))
        if ids and caixa is not None:
            for item in CXP.itens_disponiveis(con, caixa):
                if int(item["id"]) in ids and str(item.get("codigo_ato") or "").strip():
                    marcados.append(int(item["id"]))
                    pedidos.append((str(item["codigo_ato"]).strip(), 1))
    if not pedidos:
        pedidos = [(c, 1) for c in (str(x or "").strip()
                                    for x in form.getlist("codigo_tj_item")) if c]
    if not pedidos and str(form.get("codigo_tj") or "").strip():
        pedidos = [(str(form.get("codigo_tj")).strip(), 1)]
    if not pedidos:
        return {"pedidos": [], "sem_item": True}
    return {"pedidos": pedidos, "itens_ligados": marcados,
            "caixa_da_tela": _inteiro(form.get("protocolo_id"))}


def pedidos_da_abertura_da_matricula(con, form) -> dict:
    """A abertura sela o item do campo (16.2 por padrão), que a pessoa pode trocar. Só LÊ."""
    codigo = str(form.get("codigo_tj") or "").strip()
    return {"pedidos": [(codigo, 1)]} if codigo else {}


#: A tela que sabe o código EXATO antes do clique. As outras usam os pedidos
#: que a macro já tinha (o código, quando a tela o conhece, ou a família do
#: grupo da tabela, «14.*») — e a família nunca dá verde: dá amarelo.
PEDIDOS_DA_TELA: dict[str, Callable[[Any, Any], dict]] = {
    "nt_reconhecimentos": pedidos_do_reconhecimento,
    "nt_cartoes": pedidos_do_cartao,
    "ri_certidoes": pedidos_da_certidao_do_ri,
    "ri_atos": pedidos_do_ato_do_ri,
    "ri_matriculas": pedidos_da_abertura_da_matricula,
}


def _codigo_do_servico(con, servico: Any) -> str | None:
    bd = banco(con)
    if servico is None or not bd.tem_tabela("cx_servicos"):
        return None
    linha = bd.um("SELECT codigo_tj FROM cx_servicos WHERE codigo = %s", (int(servico),))
    return str((linha or {}).get("codigo_tj") or "").strip() or None


def isento_no_formulario(form) -> bool:
    """A tela marcou o ato como gratuito? A marca ou o motivo escrito (R-01/4019). Só calcula."""
    return (_sim(form.get("isento")) or _sim(form.get("gratuito"))
            or bool(str(form.get("motivo_isencao") or "").strip()))


# --------------------------------------------------------------------- a conta

def _cobre(bd, item: dict, *, tabela: str, protocolo_id: int) -> str | None:
    """Como este item pagaria o selo: «pago», «diferido», «depósito» ou None. Só LÊ.

    A régua de `ato_selado._cobre_o_item`, sem debitar: o item gratuito não
    paga selo pago (28/10/2026), e o depósito prévio só paga o item inteiro.
    """
    import caixa_depositos as DEP
    import caixa_protocolo as CXP
    from caixa_schema import centavos
    if CXP.item_gratuito(item, bd):
        return None
    if CXP.item_pago(item):
        return "pago"
    if tabela in CXP.TABELAS_QUE_DIFEREM and CXP.item_diferido(item):
        return "diferido"
    valor = centavos(item.get("valor_total"))
    if valor > 0 and bd.tem_tabela("cx_depositos") and any(
            centavos(d["saldo"]) >= valor
            for d in DEP.do_protocolo(bd, protocolo_id, tabela=tabela)):
        return "depósito"
    return None


def _do_codigo(itens: list[dict], codigo: str) -> list[dict]:
    import caixa_protocolo as CXP
    iguais = [i for i in itens if str(i.get("codigo_ato") or "").strip() == codigo]
    return iguais or [i for i in itens
                      if CXP.subitem_da_faixa(i.get("codigo_ato")) == codigo]


def _botao(texto: str, protocolo: dict | None = None, url: str | None = None) -> dict:
    return {"texto": texto, "url": url,
            "protocolo_id": int(protocolo["id"]) if protocolo else None}


def sinal_da_cobertura(con, *, tabela: Any, usuario: Any, pedidos: Any,
                       protocolo_id: Any = None, itens_ligados: Any = (),
                       gratuito: bool = False, avisos: Any = (),
                       online: bool = False, sem_item: bool = False,
                       caixa_da_tela: Any = None) -> dict:
    """Verde, vermelho ou amarelo, com o porquê e o botão que resolve. Só LÊ.

    `pedidos` é `[(código, quantidade), ...]` (o código «14.*» é a família do
    grupo); `protocolo_id`, o protocolo marcado na tela — sem ele vale o que
    está em atendimento; `itens_ligados`, os itens que a tela liga ao ato (o
    RI marca os do protocolo do caixa).
    """
    import ato_selado as AS
    import caixa_protocolo as CXP
    bd = banco(con)
    tabela = str(tabela or "").strip().lower()
    pedidos = CXP.pedidos_do_selo(pedidos)
    exato = bool(pedidos) and not any(c.endswith("*") for c, _ in pedidos)
    saida = {"tabela": tabela, "pedidos": pedidos, "exato": exato,
             "linhas": [], "botoes": [], "avisos": list(avisos or ()),
             "protocolo": None}

    def fim(cor: str, *linhas: str, botoes=()) -> dict:
        saida.update(cor=cor, titulo=TITULOS[cor])
        saida["linhas"] = [str(l) for l in linhas if l]
        saida["botoes"] = list(botoes)
        return saida

    if gratuito:
        return fim(VERDE, "Ato marcado como isento: o selo sai sem pagamento.",
                   "Depois do ato, junte o comprovante da gratuidade.")
    if not AS.trava_ligada(bd):
        return fim(VERDE, "A trava do selo está desligada pelo oficial: o selo "
                          "sai sem conferir o pagamento.")
    if online:
        return fim(AMARELO, *saida["avisos"])
    if sem_item:
        return fim(VERMELHO, "Nenhum item da tabela escolhido para este ato: "
                             "marque o item do protocolo ou escolha pelo catálogo.")
    if not pedidos:
        return fim(AMARELO, "A tela ainda não sabe qual item da tabela este ato "
                            "usa: confira o protocolo antes de lavrar.")

    # 1. os itens que a tela liga ao ato (o RI): pagos, cobrem o selo
    ligados = []
    for item_id in itens_ligados or ():
        it = bd.um("""SELECT i.*, p.numero AS protocolo_numero,
                             p.situacao AS protocolo_situacao
                        FROM cx_protocolo_atos i
                        JOIN cx_protocolos p ON p.id = i.protocolo_id
                       WHERE i.id = %s""", (int(item_id),))
        if it:
            ligados.append(dict(it))
    faltam_dos_ligados = []
    if ligados:
        for codigo, _q in pedidos:
            cands = _do_codigo(ligados, codigo) or ligados
            if not any(_cobre(bd, i, tabela=tabela, protocolo_id=int(i["protocolo_id"]))
                       for i in cands):
                faltam_dos_ligados.append(codigo)
        if not faltam_dos_ligados:
            numero = ligados[0].get("protocolo_numero")
            itens = ", ".join(sorted({str(i.get("codigo_ato")).strip() for i in ligados}))
            return fim(VERDE, f"O protocolo {numero} tem o item {itens} marcado e "
                              f"pago para este ato: o selo sai.")

    # 3. o protocolo que vai pagar: o marcado na tela, ou o do atendimento
    atendendo = CXP.em_atendimento(bd, usuario)
    escolhido = _inteiro(protocolo_id)
    if escolhido is not None and (not atendendo or int(atendendo["id"]) != escolhido):
        protocolo = bd.um("SELECT * FROM cx_protocolos WHERE id = %s", (escolhido,))
        veio_do_atendimento = False
    else:
        protocolo = atendendo
        veio_do_atendimento = bool(atendendo) and escolhido is None
    if not protocolo:
        if ligados:
            n = ligados[0].get("protocolo_numero")
            alvo = {"id": ligados[0]["protocolo_id"]}
            return fim(VERMELHO,
                       f"Falta registrar o pagamento do item "
                       f"{', '.join(faltam_dos_ligados)} no protocolo {n}.",
                       botoes=[_botao(f"Registrar o pagamento no protocolo {n}", alvo)])
        if tabela == "ri_atos":
            return fim(VERMELHO,
                       "Nenhum protocolo do caixa paga este ato: falta ligar o "
                       "protocolo à prenotação, ou escolher o protocolo do "
                       "caixa acima e marcar o item.",
                       botoes=[_botao("Abrir os protocolos do caixa",
                                      url="/caixa/protocolos")])
        return fim(VERMELHO,
                   "Nenhum protocolo escolhido: marque acima o protocolo de quem "
                   "está no balcão, ou abra um no caixa com o item deste ato.",
                   botoes=[_botao("Abrir os protocolos do caixa", url="/caixa/protocolos")])
    protocolo = dict(protocolo)
    pid, numero = int(protocolo["id"]), protocolo.get("numero")
    saida["protocolo"] = {"id": pid, "numero": numero,
                          "do_atendimento": veio_do_atendimento}
    abrir = _botao(f"Abrir o protocolo {numero}", protocolo)
    de_quem = ""
    if veio_do_atendimento:
        hora = _hora(protocolo.get("atendendo_desde"))
        de_quem = (f"É o protocolo que você já atendia{(' desde ' + hora) if hora else ''}"
                   f"{(' (' + str(protocolo.get('interessado')) + ')') if protocolo.get('interessado') else ''}"
                   f": se o cliente é outro, marque o protocolo dele.")

    itens = CXP.itens_disponiveis(bd, pid)
    for i in itens:
        i["protocolo_numero"] = numero
        i["protocolo_situacao"] = protocolo.get("situacao")
    fora = CXP.motivo_de_ficar_fora(protocolo, itens, pedidos,
                                    AS.atribuicoes_do_ato(tabela))
    if fora and (fora.startswith("encerrado") or fora.startswith("atribuição")):
        return fim(VERMELHO, f"O protocolo {numero} não serve para este ato: {fora}.",
                   de_quem, botoes=[abrir])

    if not exato:
        return _sinal_da_familia(fim, bd, tabela=tabela, pedidos=pedidos,
                                 protocolo=protocolo, itens=itens, de_quem=de_quem,
                                 abrir=abrir)

    # o código exato: soma as unidades que pagam, item a item
    verdes, vermelhas, botoes = [], [], []
    for codigo, pedidas in pedidos:
        do_codigo = _do_codigo(itens, codigo)
        pagam = 0
        formas = set()
        nao_pagos, gratuitos = [], []
        for it in do_codigo:
            forma = _cobre(bd, it, tabela=tabela, protocolo_id=pid)
            if forma:
                pagam += int(it.get("saldo") or 0)
                formas.add(forma)
            elif CXP.item_gratuito(it, bd):
                gratuitos.append(it)
            else:
                nao_pagos.append(it)
        if pagam >= pedidas:
            como = (" (o depósito prévio paga na hora do selo)" if formas == {"depósito"}
                    else " (diferido)" if formas == {"diferido"} else " pago")
            uso = f" — este ato usa {_unidades(pedidas)}" if pedidas > 1 else ""
            verdes.append(f"O protocolo {numero} tem o item {codigo}{como}{uso}: "
                          f"o selo sai.")
            continue
        if nao_pagos:
            vermelhas.append(f"Falta registrar o pagamento do item {codigo} no "
                             f"protocolo {numero}.")
            botoes.append(_botao(f"Registrar o pagamento no protocolo {numero}",
                                 protocolo))
        elif gratuitos:
            vermelhas.append(f"O item {codigo} do protocolo {numero} é gratuito: "
                             f"item gratuito não paga selo pago. Se o ato é "
                             f"isento, marque a isenção com o motivo.")
        elif pagam:
            vermelhas.append(f"Este ato usa {_unidades(pedidas)} do item {codigo}, "
                             f"e o protocolo {numero} tem {pagam} paga(s): faltam "
                             f"{pedidas - pagam}. Acrescente no protocolo.")
            botoes.append(abrir)
        else:
            gasto = bd.valor(
                """SELECT count(*) FROM cx_protocolo_atos
                    WHERE protocolo_id = %s AND btrim(codigo_ato) = %s""",
                (pid, codigo)) or 0
            porque = (" — a unidade que havia já foi usada por outro ato"
                      if int(gasto) else "")
            vermelhas.append(f"O protocolo {numero} não tem o item {codigo} com "
                             f"unidade sobrando{porque}. Acrescente o item no "
                             f"protocolo e registre o pagamento.")
            botoes.append(abrir)
    if tabela == "ri_atos" and vermelhas and not ligados:
        caixa = _inteiro(caixa_da_tela)
        if caixa is not None and caixa != pid:
            vermelhas.append("Os itens escolhidos pelo catálogo só se pagam pelo "
                             "protocolo que você atende: para usar o do caixa "
                             "acima, marque o item dele na tabela.")
    if vermelhas:
        return fim(VERMELHO, *vermelhas, *verdes, de_quem,
                   botoes=_sem_repetir(botoes))
    return fim(VERDE, *verdes)


def _sinal_da_familia(fim, bd, *, tabela, pedidos, protocolo, itens, de_quem, abrir):
    """Sem o código exato, nunca verde: o que o protocolo tem, para conferir. Só LÊ."""
    import caixa_protocolo as CXP
    pid, numero = int(protocolo["id"]), protocolo.get("numero")
    prefixos = [c[:-1] for c, _ in pedidos if c.endswith("*")]
    exatos = [c for c, _ in pedidos if not c.endswith("*")]
    do_grupo = [i for i in itens
                if any(str(i.get("codigo_ato") or "").strip().startswith(p) for p in prefixos)
                or str(i.get("codigo_ato") or "").strip() in exatos]
    pagos = [i for i in do_grupo if _cobre(bd, i, tabela=tabela, protocolo_id=pid)]
    grupos = sorted({p.rstrip(".") for p in prefixos})
    nome = " ou ".join(f"{g} ({NOMES_DOS_GRUPOS[g]})" if g in NOMES_DOS_GRUPOS else g
                       for g in grupos)
    if pagos:
        lista = "; ".join(f"{str(i.get('codigo_ato')).strip()} ×{i.get('saldo')}"
                          for i in pagos)
        return fim(AMARELO,
                   f"O protocolo {numero} tem pago: {lista}. Confira se é o item "
                   f"deste ato — o selo só sai com o item do mesmo código.",
                   de_quem, botoes=[abrir])
    if do_grupo:
        lista = ", ".join(sorted({str(i.get("codigo_ato")).strip() for i in do_grupo}))
        return fim(VERMELHO,
                   f"Falta registrar o pagamento do item {lista} no protocolo "
                   f"{numero}.", de_quem,
                   botoes=[_botao(f"Registrar o pagamento no protocolo {numero}",
                                  protocolo)])
    return fim(VERMELHO,
               f"O protocolo {numero} não tem item do grupo {nome} da tabela com "
               f"unidade sobrando. Acrescente o item deste ato no protocolo e "
               f"registre o pagamento.", de_quem, botoes=[abrir])


def _sem_repetir(botoes: list[dict]) -> list[dict]:
    vistos, saida = set(), []
    for b in botoes:
        chave = (b["texto"], b.get("url"), b.get("protocolo_id"))
        if chave not in vistos:
            vistos.add(chave)
            saida.append(b)
    return saida


def sinal_do_formulario(con, *, tabela: Any, usuario: Any, form,
                        pedidos_da_macro: Any = None) -> dict:
    """O sinal a partir do formulário do ato como está agora na tela. Só LÊ.

    A tela que sabe o código exato está em `PEDIDOS_DA_TELA`; as outras usam
    `pedidos_da_macro` (os que a lista de protocolos já mostrava).
    """
    tabela = str(tabela or "").strip().lower()
    regra = PEDIDOS_DA_TELA.get(tabela)
    lido = (regra(con, form) if regra else {}) or {}
    pedidos = lido.get("pedidos")
    if pedidos is None or (not pedidos and not lido.get("sem_item")):
        pedidos = pedidos_da_macro or []
    # O protocolo que a tela vai atender: o da lista (`protocolo_selo`) ou o do
    # quadro de cobrança (`_cobrar.html`), a mesma regra do gancho que o
    # transforma no «em atendimento» antes da rota.
    escolhido = (form.get("protocolo_selo") or "").strip()
    if not escolhido and form.get("protocolo_do_quadro"):
        escolhido = (form.get("protocolo_id") or "").strip()
    sinal = sinal_da_cobertura(
        con, tabela=tabela, usuario=usuario, pedidos=pedidos,
        protocolo_id=escolhido or None,
        itens_ligados=lido.get("itens_ligados") or (),
        gratuito=isento_no_formulario(form), avisos=lido.get("avisos") or (),
        online=bool(lido.get("online")),
        sem_item=bool(lido.get("sem_item")) and not pedidos,
        caixa_da_tela=lido.get("caixa_da_tela"))
    return sinal
