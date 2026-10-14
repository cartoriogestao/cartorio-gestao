"""A fila da Central de Certidões, e a certidão eletrônica que a atende.

    «siga no desenvolvimento das integrações até terminar de todas» — o
    oficial, 03/09/2026

Fica entre o **assento** desta casa e a **API da Certidão Eletrônica**. A
corrente é esta, e cada elo é uma pergunta diferente:

    pedido na Central  →  assento desta casa  →  certidão eletrônica  →  cumprir
      (quem pediu)         (qual registro)        (o id da Central)      (entregar)

**A RECUSA DIZ EM QUE ELO PAROU**, porque o conserto de cada um é noutro lugar:
pedido sem assento se resolve procurando no livro; assento sem matrícula se
resolve na ficha; certidão que a Central recusou se resolve no campo que ela
apontou. Recusa que não diz onde manda o escrevente procurar em quatro lugares.

**ESTE MÓDULO NÃO LAVRA ATO — pela quinta vez neste projeto**, depois do
usucapião, das fraudes, do CNIB e da CENPROT. Dois dos sete módulos da Central
(`P13` e `EOB`) pedem **registro**, e não certidão: registro toma número, ocupa
folha, gasta selo e entra na corrente de hash. Quem faz isso é a tela do
assento, que tem as quatro coisas; aqui o pedido fica marcado como
**`REGISTRADO`** depois que alguém lavrou, e o botão leva para lá.

**CONFERIR E ENVIAR SÃO DOIS BOTÕES** — a forma da remessa da CRA e do
e-Proclamas, e pela mesma razão: o que sobe **sai no mundo e é cobrado**.

**A CHAMADA DE REDE NUNCA ACONTECE DENTRO DE `db.transaction()`.** Todas as
funções que falam com a Central recebem `db`, e não `con` — a mesma assinatura
de `ato_selado.obter_selo` e de `proclamas.enviar`, e pelo mesmo motivo:
segurar o `BEGIN IMMEDIATE` durante uma chamada de sessenta segundos poria todo
outro balcão no `busy_timeout`.

**O CASAMENTO DO PEDIDO COM O ASSENTO É PELA MATRÍCULA, E SÓ POR ELA.**

    O pedido traz também livro, folha e número, e seria fácil casar por eles.
    **Não se casa**: os números do livro reiniciam por volume nesta casa (é a
    pendência de numeração do casamento, declarada desde 29/08/2026), e um
    casamento errado mostraria ao balcão **o registro de outra pessoa** — e
    ninguém desconfia de uma ficha que abre. É a regra da dupla chave de
    `protesto_imagens`, aqui pelo lado da cautela.

    Quando a matrícula casa, o **nome também se compara** — e a divergência
    vira **aviso, e não recusa**: o nome muda legitimamente (o de casada muda
    em 17 dos 20 casamentos desta casa).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

import centrais_cred as CRED
import onrcpn_certidao_api as API
import rc_certidao as CERT
import rc_pedidos_schema as ESQ

# COMO A CASA SE CHAMA PARA A CENTRAL. O contrato pede «nome da plataforma que
# está solicitando».
PLATAFORMA = "CartorioGestao"

# O DE-PARA DO SEXO. **Medido na produção**: `rc_pessoas.sexo` tem `M` em 751,
# `F` em 719 e **vazio em 14**.
#
#   O VAZIO NÃO VIRA «ignorado». `ignorado` é uma resposta que alguém pode ter
#   dado; vazio é campo que ninguém preencheu. Mandar um pelo outro afirmaria
#   que se perguntou. Campo ausente não afirma nada — é a regra de
#   `anotar_do_termo`, e a mesma do e-Proclamas.
SEXO_DA_CASA: dict[str, str] = {"M": "masculino", "F": "feminino"}

# A ESPÉCIE DA CASA → O `tipo_registro` DA CENTRAL.
#
#   **NATIMORTO, PROCLAMAS e as seis coisas do Livro E não estão aqui**, e não
#   por esquecimento: a Central declara **quatro** tipos, e nenhum deles é
#   natimorto. Mandar um natimorto como «nascimento» seria afirmar nascimento
#   com vida — é a mesma recusa que `rc_certidao_odt` já faz no papel.
TIPO_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "nascimento",
    "CASAMENTO": "casamento",
    "CASAMENTO_RELIGIOSO": "casamento",
    "OBITO": "obito",
}

# A FILIAÇÃO DO CASAMENTO, por nubente.
PAIS_DO_NUBENTE: dict[str, tuple[str, str]] = {
    "NUBENTE1": ("PAI_NUBENTE1", "MAE_NUBENTE1"),
    "NUBENTE2": ("PAI_NUBENTE2", "MAE_NUBENTE2"),
}

# COMO A CENTRAL JUNTA DUAS PESSOAS NUM CAMPO SÓ. Medido nos exemplos:
# `avos: "João da silva; Maria da Graça"` e `genitores: "José da Silva;
# Maria da Silva"` — ponto e vírgula, com espaço.
SEPARADOR_DE_NOMES = "; "


class PedidoError(ValueError):
    """Recusa de regra, com a frase pronta para o balcão."""


# --------------------------------------------------------------- o ambiente


def ambiente() -> str:
    """O ambiente em que esta casa fala com a Central.

    **Um só, e é o de homologação** — ver `centrais_cred.AMBIENTES_DA_CENTRAL`:
    nenhum dos dois contratos do ON-RCPN publica o endereço de produção.
    """
    return CRED.ambientes_de(CRED.ONRCPN)[0]


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _municipio_da_crc(v: Any) -> str:
    """Devolve município que a Central pode procurar em sua tabela.

    ``NADA CONSTA`` é uma anotação para o ser humano, não o nome de um
    município. Se ela sair em ``municipio_nascimento`` de um genitor, o
    importador da CRC deixa de montar toda a filiação. Também «undefined»
    e «null»: são a interpolação JS de campo ausente, não um município.
    O campo vai vazio — chave presente, conteúdo em branco — para a tela
    da CRC não escrever a palavra JS; o importador não trata vazio como
    cidade.
    """
    municipio = _texto(v)
    chave = (municipio.upper().replace("Ã", "A").replace("Á", "A")
             .replace("Â", "A").replace("Ç", "C"))
    if chave in {"NADA CONSTA", "NAO CONSTA", "N/C", "NC",
                 "UNDEFINED", "NULL", "NONE", "NAN"}:
        return ""
    return municipio


def _uf_da_crc(v: Any) -> str:
    """UF do genitor, nunca a palavra JS «undefined»."""
    uf = _texto(v)
    chave = uf.upper()
    if chave in {"UNDEFINED", "NULL", "NONE", "NAN",
                 "NADA CONSTA", "NAO CONSTA", "N/C", "NC"}:
        return ""
    return uf


def _hash(corpo: dict) -> str:
    return hashlib.sha256(
        json.dumps(corpo, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


# ----------------------------------------------------------------- a fila


def baixar(db, modulo: Any, *, cns: Any, agora: str, usuario: str | None = None,
           pasta=None) -> dict:
    """Traz os pedidos pendentes daquele módulo. **Rede fora de transação.**

    Devolve `{modulo, vieram, novos, repetidos, contagem_bate, pedidos}`.

    **O MESMO PEDIDO NÃO ENTRA DUAS VEZES** — a trava é o índice único
    `(ambiente, modulo, numero_pedido)`, e não uma conferência em Python. Baixar
    de novo é rotina: o balcão baixa de manhã e ao meio-dia.
    """
    qual = API.modulo_da_central(modulo)
    onde = ambiente()
    # 1) A REDE, sem transação nenhuma aberta.
    trazidos = API.obter_pedidos(qual, cns, pasta=pasta)

    # 2) A GRAVAÇÃO, numa transação curta.
    novos, repetidos = 0, 0
    with db.transaction() as con:
        con.row_factory = sqlite3.Row
        for p in trazidos["pedidos"]:
            numero = _texto(p.get("pedido_certidao_id"))
            if not numero:
                # Pedido sem número não se guarda: é por ele que se responde,
                # e sem ele a linha nasceria impossível de cumprir.
                continue
            casado = _casar(con, p)
            cur = con.execute(
                """INSERT OR IGNORE INTO rc_pedidos(
                       modulo, ambiente, numero_pedido, letra_registro,
                       especie, assento_id, casamento_motivo, teor, resumo,
                       deposito_previo, deposito_previo_valor,
                       baixado_em, baixado_por, situacao)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (qual, onde, numero, _texto(p.get("tipo_registro")) or None,
                 p.get("especie"), casado["assento_id"], casado["motivo"],
                 json.dumps(p.get("teor"), ensure_ascii=False), _resumo(p),
                 _texto(p.get("deposito_previo")) or None,
                 p.get("deposito_previo_valor"),
                 agora, usuario, ESQ.PENDENTE))
            if cur.rowcount:
                novos += 1
            else:
                repetidos += 1
    return {"modulo": qual, "ambiente": onde,
            "vieram": len(trazidos["pedidos"]), "novos": novos,
            "repetidos": repetidos,
            "contagem_bate": trazidos["contagem_bate"],
            "quantos_a_central_disse": trazidos["quantos_a_central_disse"]}


def _resumo(p: dict) -> str:
    """A linha que o balcão lê na fila, montada na baixa.

    Sem ela a tela teria de abrir o JSON de cada pedido para desenhar a lista.
    """
    partes = [_texto(p.get("nome_registrado")) or "sem nome",
              (p.get("especie") or _texto(p.get("letra_registro"))
               or _texto(p.get("tipo_registro")) or "espécie não informada")]
    quem = _texto(p.get("nome_requerente"))
    if quem:
        partes.append(f"pedido por {quem}")
    return " · ".join(partes)[:300]


def _casar(con: sqlite3.Connection, p: dict) -> dict:
    """Acha o assento desta casa. **Pela matrícula, e só por ela.**

    Devolve `{assento_id, motivo}`. `motivo` é escrito para o balcão ler: ele
    diz **como** se achou, ou **por que** não — e são consertos diferentes.
    """
    matricula = "".join(c for c in _texto(p.get("matricula")) if c.isdigit())
    if not matricula:
        return {"assento_id": None,
                "motivo": ("O pedido não trouxe matrícula. Procure o assento "
                           "pelo nome e amarre-o à mão.")}
    linha = con.execute(
        "SELECT id, nome, especie FROM rc_assentos WHERE matricula=?",
        (matricula,)).fetchone()
    if not linha:
        return {"assento_id": None,
                "motivo": (f"Nenhum assento desta casa tem a matrícula "
                           f"{matricula}. Confira se o pedido é mesmo desta "
                           f"serventia.")}
    motivo = f"Achado pela matrícula {matricula}."
    pedido_nome = _texto(p.get("nome_registrado")).casefold()
    do_assento = _texto(linha["nome"]).casefold()
    if pedido_nome and do_assento and pedido_nome != do_assento:
        # **AVISO, E NÃO RECUSA.** O nome muda legitimamente — o de casada
        # muda em 17 dos 20 casamentos medidos nesta casa.
        motivo += (f" O nome do pedido («{p.get('nome_registrado')}») não é "
                   f"igual ao do assento («{linha['nome']}») — confira antes "
                   f"de emitir.")
    return {"assento_id": int(linha["id"]), "motivo": motivo}


def pendentes(con: sqlite3.Connection, *, modulo: Any = None,
              situacao: str | None = ESQ.PENDENTE) -> list[dict]:
    """A fila. Só LÊ."""
    onde = [ "ambiente=?" ]
    valores: list[Any] = [ambiente()]
    if modulo:
        onde.append("modulo=?")
        valores.append(API.modulo_da_central(modulo))
    if situacao:
        onde.append("situacao=?")
        valores.append(situacao)
    return [dict(r) for r in con.execute(
        "SELECT * FROM rc_pedidos WHERE " + " AND ".join(onde)
        + " ORDER BY baixado_em DESC, id DESC", valores)]


def quantos_por_modulo(con: sqlite3.Connection) -> dict[str, int]:
    """Quantos pendentes há em cada módulo. Só CONTA — não julga atraso.

    **A Central não diz quando o pedido venceu**, e o contrato não traz prazo
    nenhum. Dizer «atrasado» sobre um número que ninguém sabe de quando é seria
    o alarme que soa sempre.
    """
    contagem = {m: 0 for m in API.MODULOS}
    for linha in con.execute(
            "SELECT modulo, COUNT(*) n FROM rc_pedidos "
            "WHERE ambiente=? AND situacao=? GROUP BY modulo",
            (ambiente(), ESQ.PENDENTE)):
        contagem[str(linha[0])] = int(linha[1])
    return contagem


def pedido(con: sqlite3.Connection, pedido_id: int) -> dict | None:
    """Um pedido, com o assento que casou e o teor aberto. Só LÊ."""
    linha = con.execute("SELECT * FROM rc_pedidos WHERE id=?",
                        (int(pedido_id),)).fetchone()
    if not linha:
        return None
    p = dict(linha)
    try:
        p["teor_aberto"] = json.loads(p.get("teor") or "{}")
    except ValueError:
        p["teor_aberto"] = {}
    p["nome_do_modulo"] = API.NOME_DO_MODULO.get(p["modulo"], p["modulo"])
    p["pede_registro"] = p["modulo"] in API.MODULOS_DE_REGISTRO
    p["especie_a_lavrar"] = API.ESPECIE_DO_MODULO_DE_REGISTRO.get(p["modulo"])
    p["assento"] = None
    if p.get("assento_id"):
        a = con.execute("SELECT * FROM rc_assentos WHERE id=?",
                        (int(p["assento_id"]),)).fetchone()
        p["assento"] = dict(a) if a else None
    p["eletronicas"] = [dict(r) for r in con.execute(
        "SELECT * FROM rc_certidoes_eletronicas WHERE pedido_id=? "
        "ORDER BY id DESC", (int(pedido_id),))]
    # **AS OUTRAS CERTIDOES DO MESMO REGISTRO.** Nao e enfeite: um segundo
    # pedido do mesmo assento chega com frequencia, e quem nao ve que ja saiu
    # certidao eletronica dali **cria outra** — que custa, e que deixa dois
    # identificadores vivos para o mesmo registro.
    p["outras_do_registro"] = []
    if p.get("assento_id"):
        deste = {e["id"] for e in p["eletronicas"]}
        p["outras_do_registro"] = [
            e for e in eletronicas_do_assento(con, int(p["assento_id"]))
            if e["id"] not in deste]
    return p


def amarrar_assento(con: sqlite3.Connection, pedido_id: int, assento_id: int,
                    *, motivo: str = "") -> dict:
    """Amarra à mão o assento que a matrícula não achou. ESCREVE.

    Existe porque a matrícula falta em pedido antigo e o balcão sabe qual é o
    assento — e sem esta porta o pedido ficaria para sempre sem como cumprir.
    """
    a = con.execute("SELECT id, nome FROM rc_assentos WHERE id=?",
                    (int(assento_id),)).fetchone()
    if not a:
        raise PedidoError(f"O assento {assento_id} não existe.")
    con.execute(
        "UPDATE rc_pedidos SET assento_id=?, casamento_motivo=? WHERE id=?",
        (int(assento_id),
         (_texto(motivo) or "Amarrado à mão no balcão.")
         + f" Assento: {a['nome']}.", int(pedido_id)))
    return {"pedido_id": int(pedido_id), "assento_id": int(assento_id)}


def dispensar(con: sqlite3.Connection, pedido_id: int, *, motivo: str,
              agora: str, usuario: str | None = None) -> dict:
    """Tira o pedido da fila **sem responder à Central**. ESCREVE.

    **Dispensar exige motivo escrito**, como no usucapião e na pendência de
    numeração — e a Central continua achando que o pedido está aberto, o que a
    tela diz com todas as letras.
    """
    texto = _texto(motivo)
    if len(texto) < 10:
        raise PedidoError(
            "Escreva por que este pedido sai da fila sem resposta. A Central "
            "continua com ele em aberto, e daqui a seis meses ninguém lembra.")
    con.execute(
        "UPDATE rc_pedidos SET situacao=?, dispensa_motivo=?, "
        "respondido_em=?, respondido_por=? WHERE id=?",
        (ESQ.DISPENSADO, texto, agora, usuario, int(pedido_id)))
    return {"pedido_id": int(pedido_id), "motivo": texto}


def marcar_registrado(con: sqlite3.Connection, pedido_id: int, *,
                      assento_id: int, agora: str,
                      usuario: str | None = None) -> dict:
    """Marca que o registro pedido por `P13`/`EOB` **foi lavrado**. ESCREVE.

    **Não lavra nada** — quem lavrou foi a tela do assento. O que esta função
    faz é tirar da fila o que já virou livro, amarrando ao assento que saiu.
    """
    p = con.execute("SELECT modulo FROM rc_pedidos WHERE id=?",
                    (int(pedido_id),)).fetchone()
    if not p:
        raise PedidoError(f"O pedido {pedido_id} não existe.")
    if str(p["modulo"]) not in API.MODULOS_DE_REGISTRO:
        raise PedidoError(
            f"O módulo {p['modulo']} pede certidão, e não registro. "
            f"Só os módulos "
            f"{', '.join(API.MODULOS_DE_REGISTRO)} pedem que se lavre.")
    con.execute(
        "UPDATE rc_pedidos SET situacao=?, assento_id=?, respondido_em=?, "
        "respondido_por=? WHERE id=?",
        (ESQ.REGISTRADO, int(assento_id), agora, usuario, int(pedido_id)))
    return {"pedido_id": int(pedido_id), "assento_id": int(assento_id)}


def rejeitar(db, pedido_id: int, *, motivo: str, agora: str,
             usuario: str | None = None, pasta=None) -> dict:
    """Recusa o pedido na Central, com o motivo escrito. **Rede fora de
    transação, e a gravação depois.**

    **O REQUERENTE LÊ ESTA FRASE.** «Não foi possível atender» não diz o que
    fazer; «o registro não é desta serventia» e «falta o nome da mãe no pedido»
    dizem.
    """
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        p = pedido(con, pedido_id)
    if not p:
        raise PedidoError(f"O pedido {pedido_id} não existe.")
    if p["situacao"] in ESQ.SITUACOES_TERMINAIS:
        raise PedidoError(
            f"Este pedido já saiu da fila como «{p['situacao'].lower()}» em "
            f"{p.get('respondido_em') or 'data não registrada'}.")

    feito = API.rejeitar_pedido(numero_pedido=p["numero_pedido"],
                                modulo=p["modulo"], motivo=motivo, pasta=pasta)
    with db.transaction() as con:
        con.execute(
            "UPDATE rc_pedidos SET situacao=?, rejeicao_motivo=?, "
            "respondido_em=?, respondido_por=?, resposta=?, corpo_enviado=?, "
            "corpo_hash=? WHERE id=?",
            (ESQ.REJEITADO, feito["corpo"]["descricao_motivo"], agora, usuario,
             json.dumps(feito.get("resposta"), ensure_ascii=False),
             json.dumps(feito["corpo"], ensure_ascii=False),
             _hash(feito["corpo"]), int(pedido_id)))
    return {"pedido_id": int(pedido_id), "motivo": feito["corpo"]["descricao_motivo"],
            "resposta": feito.get("resposta")}


# ------------------------------------------------- a certidão eletrônica


def _por_papel(pessoas: list[dict]) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = {}
    for p in pessoas:
        grupos.setdefault(str(p.get("papel") or ""), []).append(p)
    return grupos


def _um(grupos: dict[str, list[dict]], papel: str) -> dict:
    lista = grupos.get(papel) or []
    return lista[0] if lista else {}


def _sexo(pessoa: dict) -> str:
    return SEXO_DA_CASA.get(_texto(pessoa.get("sexo")).upper(), "")


def _juntar(*nomes: Any) -> str:
    """Junta pessoas num campo só, como a Central escreve: `A; B`."""
    limpos = [_texto(n) for n in nomes if _texto(n)]
    return SEPARADOR_DE_NOMES.join(limpos)


def _data(valor: Any) -> str:
    texto = _texto(valor)
    return API.data_para_a_central(texto) if texto else ""


def _sem_vazios(d: dict) -> dict:
    """Tira do corpo o que ficou em branco.

    **CAMPO AUSENTE NÃO AFIRMA NADA; CAMPO VAZIO PARECE RESPOSTA.** E o
    contrato não declara obrigatório nenhum, de modo que omitir é legítimo.
    """
    saida = {}
    for k, v in d.items():
        if v in (None, "", [], {}):
            continue
        saida[k] = v
    return saida


def montar(con: sqlite3.Connection, assento_id: int, *, cns: Any,
           tipo_registro: str | None = None, tipo_certidao: str | None = None,
           modalidade: str = "eletronica", selo: Any = None,
           cod_selo: Any = None, cota_emolumentos: Any = None,
           cota_isento: bool = False,
           texto_do_inteiro_teor: Any = None) -> dict:
    """Monta `{certidao, registro}` do assento. **SÓ CALCULA — não grava nem
    manda.**

    Devolve também `avisos`: o que **não** vai, e por quê. É a forma do
    e-Proclamas, e ela existe porque campo que some calado é campo que ninguém
    conserta.
    """
    a = con.execute("SELECT * FROM rc_assentos WHERE id=?",
                    (int(assento_id),)).fetchone()
    if not a:
        raise PedidoError(f"O assento {assento_id} não existe.")
    assento = dict(a)
    especie = _texto(assento.get("especie")).upper()

    tipo = _texto(tipo_registro) or TIPO_DA_ESPECIE.get(especie, "")
    if not tipo:
        raise PedidoError(
            f"A Central não tem tipo de registro para um assento de "
            f"{especie.lower() or 'espécie não informada'}. Ela declara "
            f"quatro: {', '.join(API.TIPOS_DE_REGISTRO)}.")
    tipo = API.tipo_de_registro_para_a_central(tipo)

    avisos: list[str] = []
    pessoas = CERT.pessoas(con, assento_id)
    grupos = _por_papel([dict(p) for p in pessoas])

    if tipo == "inteiro_teor":
        registro = _inteiro_teor(assento, grupos, texto_do_inteiro_teor,
                                 avisos)
    elif tipo == "nascimento":
        registro = _nascimento(con, assento, grupos, avisos)
    elif tipo == "casamento":
        registro = _casamento(con, assento, grupos, avisos)
    else:
        registro = _obito(con, assento, grupos, avisos)

    certidao = _sem_vazios({
        "plataformaId": PLATAFORMA,
        "tipo_registro": tipo,
        # **`tipo_certidao` SÓ EXISTE NO INTEIRO TEOR** — o próprio contrato o
        # descreve como «somente quando inteiro_teor».
        "tipo_certidao": (API.tipo_de_registro_para_a_central(
            tipo_certidao or TIPO_DA_ESPECIE.get(especie, "") or "nascimento")
            if tipo == "inteiro_teor" else ""),
        "cartorio_cns": "".join(c for c in _texto(cns) if c.isdigit()),
        "selo": _texto(selo),
        "cod_selo": _texto(cod_selo),
        "modalidade": API.modalidade_para_a_central(modalidade),
        "cota_emolumentos": (API.cota_para_a_central(cota_emolumentos)
                             if cota_emolumentos not in (None, "") else ""),
    })
    # **O BOOLEANO VAI MESMO SENDO FALSO.** `_sem_vazios` tiraria o `False`, e
    # aqui ele é resposta: «não é isento» é diferente de «não se disse».
    certidao["cota_emolumentos_isento"] = bool(cota_isento)

    if not certidao.get("cartorio_cns"):
        avisos.append(
            "O CNS da serventia não está configurado, e a Central identifica o "
            "cartório por ele. Informe em Administrativo → Configurações.")
    if not certidao.get("selo"):
        avisos.append(
            "Vai sem selo. O sistema **não compra selo** por este caminho: a "
            "casa nunca selou certidão eletrônica, e selar por caminho que ela "
            "nunca usou seria assinar por quem selou.")
    return {"certidao": certidao, "registro": _sem_vazios(registro),
            "avisos": avisos, "tipo_registro": tipo, "especie": especie,
            "assento": assento}


def _anotacoes_de_cadastro(assento: dict) -> list[dict]:
    """As anotações do art. 347 que a casa guarda em coluna própria.

    **Só o título de eleitor entra**, e o motivo é medido: das colunas que o
    mutirão preenche, `titulo_eleitor` é a que tem um `tipo` correspondente no
    vocabulário da Central (`titulo_eleitor`). O **CPF não entra aqui** — ele é
    campo próprio do registro, e repeti-lo como anotação o mostraria duas vezes.
    """
    anotacoes = []
    titulo = _texto(assento.get("titulo_eleitor"))
    if titulo:
        anotacoes.append({"tipo": "titulo_eleitor", "documento": titulo})
    return anotacoes


# OS ATOS QUE VÃO NO CAMPO `averbacao_anotacao` DA CENTRAL. O registro não
# entra: ele **é** a certidão, e repeti-lo ali o mostraria duas vezes.
ATOS_DA_MARGEM: tuple[str, ...] = ("AVERBACAO", "ANOTACAO", "RETIFICACAO")


def _averbacoes(con: sqlite3.Connection, assento_id: int) -> str:
    """O que está lançado à margem, num campo só, como a Central o quer.

    > **CORREÇÃO, e ela fica à vista.** A primeira versão desta função lia
    > `assento["averbacao_anotacao"]` — e **essa coluna não existe**. Eu montei
    > o nome a partir do campo da Central, que se chama assim, e ele tem toda a
    > cara de ser o da casa. Nome plausível é o que mais se parece com medição
    > sem ser, e este projeto já pagou por isso três vezes
    > (`lugar_no_brasil`, `atualizado_em`, `strDescricao`).
    >
    > **O dado mora em `rc_atos`**, que é onde a divisão tripartite do RCPN
    > vive: averbação, anotação e retificação são atos, com teor, data e lugar
    > no livro — e não um campo de texto do assento. Conferido nas colunas da
    > produção.

    Em produção há **244 atos, todos `REGISTRO`** — de modo que hoje isto
    devolve vazio para todos, e é a resposta certa: não há margem escrita.
    """
    linhas = con.execute(
        "SELECT rotulo, teor FROM rc_atos WHERE assento_id=? AND tipo IN "
        "(" + ",".join("?" * len(ATOS_DA_MARGEM)) + ") ORDER BY id",
        (int(assento_id), *ATOS_DA_MARGEM)).fetchall()
    partes = []
    for linha in linhas:
        rotulo, teor = _texto(linha[0]), _texto(linha[1])
        if teor:
            partes.append(f"{rotulo}: {teor}" if rotulo else teor)
    return " | ".join(partes)


def _nascimento(con: sqlite3.Connection, assento: dict,
                grupos: dict[str, list[dict]], avisos: list[str]) -> dict:
    quem = _um(grupos, "REGISTRADO")
    pai, mae = _um(grupos, "PAI"), _um(grupos, "MAE")

    filiacao = []
    for genitor, avo1, avo2 in ((pai, "AVO_PATERNO", "AVO_PATERNA"),
                                (mae, "AVO_MATERNO", "AVO_MATERNA")):
        if not _texto(genitor.get("nome")):
            continue
        municipio = _municipio_da_crc(genitor.get("naturalidade_cidade"))
        uf = _uf_da_crc(genitor.get("naturalidade_uf"))
        if not municipio and _texto(genitor.get("naturalidade_cidade")):
            avisos.append(
                "A naturalidade de " + _texto(genitor.get("nome"))
                + " não contém município válido para a CRC. O JSON manterá "
                "a UF e deixará o município vazio; confirme-o no livro "
                "antes de retificar o assento.")
        # municipio/UF ficam no dict MESMO VAZIOS: omitir vira «undefined»
        # na tela da CRC (interpolação JS). Vazio é o sentinela — «não
        # consta» como nome de município derruba a filiação no importador.
        bloco = _sem_vazios({
            "nome": _texto(genitor.get("nome")),
            "avos": _juntar(_um(grupos, avo1).get("nome"),
                            _um(grupos, avo2).get("nome")),
        })
        bloco["municipio_nascimento"] = municipio
        bloco["uf_nascimento"] = uf
        filiacao.append(bloco)
    if not filiacao:
        avisos.append(
            "O assento está sem filiação, e a filiação é o corpo da certidão "
            "de nascimento. Traga-a na ficha do assento antes de emitir.")

    gemeos = {}
    if assento.get("gemeo_ordem"):
        irmaos = []
        if assento.get("gemeo_irmao_id"):
            irmao = con.execute(
                "SELECT nome, matricula FROM rc_assentos WHERE id=?",
                (int(assento["gemeo_irmao_id"]),)).fetchone()
            if irmao:
                irmaos.append(_sem_vazios({
                    "nome": _texto(irmao["nome"]),
                    "matricula": _texto(irmao["matricula"])}))
        # **`quantidade` NÃO É A ORDEM.** O art. 234 pede a ordem de
        # nascimento; a Central pede quantos são. Aqui vai o que se sabe: o
        # próprio mais os irmãos amarrados.
        gemeos = {"quantidade": 1 + len(irmaos)}
        if irmaos:
            gemeos["irmao"] = irmaos

    sexo = _sexo(quem)
    if not sexo:
        avisos.append(
            "O sexo do registrado não está preenchido no assento, e vai em "
            "branco. Preencher «ignorado» por conta própria afirmaria que se "
            "perguntou.")

    return {
        "nome_completo": _texto(quem.get("nome")) or _texto(assento.get("nome")),
        "cpf": API.cpf_para_a_central(
            assento.get("cpf_registrado") or quem.get("documento_numero")),
        "matricula": _texto(assento.get("matricula")),
        "data_registro": _data(assento.get("data_ato")),
        "data_nascimento": _data(assento.get("data_fato")),
        "hora_nascimento": _texto(assento.get("hora_fato")),
        "municipio_naturalidade": _texto(quem.get("naturalidade_cidade")),
        "uf_naturalidade": _texto(quem.get("naturalidade_uf")),
        "local_nascimento": _texto(assento.get("local_fato_nome")),
        "sexo": sexo,
        "gemeos": gemeos,
        "filiacao": filiacao,
        "numero_dnv": _texto(assento.get("dnv")),
        "averbacao_anotacao": _averbacoes(con, int(assento["id"])),
        "anotacoes_cadastro": _anotacoes_de_cadastro(assento),
    }


def _casamento(con: sqlite3.Connection, assento: dict,
               grupos: dict[str, list[dict]], avisos: list[str]) -> dict:
    conjuges = []
    for papel in ("NUBENTE1", "NUBENTE2"):
        n = _um(grupos, papel)
        if not _texto(n.get("nome")):
            continue
        pai, mae = PAIS_DO_NUBENTE[papel]
        conjuges.append(_sem_vazios({
            "nome_atual_habilitacao": _texto(n.get("nome")),
            "cpf": API.cpf_para_a_central(n.get("documento_numero")),
            "data_nascimento": _data(n.get("data_nascimento")),
            "nacionalidade": _texto(n.get("nacionalidade")),
            "estado_civil": _texto(n.get("estado_civil")),
            "municipio_naturalidade": _texto(n.get("naturalidade_cidade")),
            "uf_naturalidade": _texto(n.get("naturalidade_uf")),
            "genitores": _juntar(_um(grupos, pai).get("nome"),
                                 _um(grupos, mae).get("nome")),
        }))
    if len(conjuges) < 2:
        avisos.append(
            "O assento não tem os dois cônjuges gravados como pessoas, e a "
            "certidão de casamento é sobre os dois. Complete na ficha.")
    # **`nome_apos_casamento` NÃO SE DEDUZ DO NOME ATUAL.** O que a casa guarda
    # é o nome de cada pessoa hoje; qual deles é «o que passou a usar» é o que
    # o assento registra no termo, e não há coluna com essa resposta separada.
    avisos.append(
        "O «nome que passou a utilizar» vai em branco: a casa guarda o nome de "
        "cada cônjuge, e não qual deles é o de antes e o de depois. É o campo "
        "que a certidão de casamento existe para dizer — se quiser que vá, ele "
        "precisa de lugar próprio na ficha do assento.")
    return {
        "conjuges": conjuges,
        "matricula": _texto(assento.get("matricula")),
        "data_celebracao": _data(assento.get("data_fato")),
        "regime_bens": _texto(assento.get("regime_bens")),
        "data_registro": _data(assento.get("data_ato")),
        "averbacao_anotacao": _averbacoes(con, int(assento["id"])),
    }


def _obito(con: sqlite3.Connection, assento: dict,
           grupos: dict[str, list[dict]], avisos: list[str]) -> dict:
    quem = _um(grupos, "FALECIDO")
    pai, mae = _um(grupos, "PAI"), _um(grupos, "MAE")

    # **O `existencia_bens` DA CENTRAL TEM TRÊS PALAVRAS**, e a casa guarda um
    # texto livre em `obito_possui_bens`. Traduz-se o que se reconhece e o
    # resto **fica em branco**, com aviso: mandar «nao» sobre um texto que não
    # se entendeu afirmaria que o falecido não deixou bens.
    bens = _texto(assento.get("obito_possui_bens")).lower()
    bens = {"sim": "sim", "s": "sim", "true": "sim", "1": "sim",
            "nao": "nao", "não": "nao", "n": "nao", "false": "nao", "0": "nao",
            "ignorada": "ignorada", "ignorado": "ignorada"}.get(bens, "")
    if _texto(assento.get("obito_possui_bens")) and not bens:
        avisos.append(
            f"«{assento.get('obito_possui_bens')}» não é uma das três palavras "
            f"que a Central aceita para existência de bens "
            f"({', '.join(API.EXISTENCIA_BENS)}), e o campo vai em branco.")

    sexo = _sexo(quem)
    return {
        "nome_completo": _texto(quem.get("nome")) or _texto(assento.get("nome")),
        "cpf": API.cpf_para_a_central(quem.get("documento_numero")),
        "matricula": _texto(assento.get("matricula")),
        "data_falecimento": _data(assento.get("data_fato")),
        "hora_falecimento": _texto(assento.get("hora_fato")),
        "local_falecimento": _texto(assento.get("local_fato_nome")),
        "sexo": sexo,
        "estado_civil": _texto(quem.get("estado_civil")),
        "data_nascimento": _data(quem.get("data_nascimento")),
        "municipio_naturalidade": _texto(quem.get("naturalidade_cidade")),
        "uf_naturalidade": _texto(quem.get("naturalidade_uf")),
        "filiacao": _juntar(pai.get("nome"), mae.get("nome")),
        # OS TRÊS QUE O REVISOR COBROU (achado 2), e que a casa passou a
        # guardar: causa da morte, quem atestou e onde se sepultou.
        "causa_morte": _texto(assento.get("causa_morte")),
        "nome_medico": _texto(assento.get("atestante")),
        "crm_medico": _texto(assento.get("atestante_documento")),
        "local_sepultamento_cremacao": _texto(assento.get("local_sepultamento")),
        "data_registro": _data(assento.get("data_ato")),
        "nome_declarante": _texto(_um(grupos, "DECLARANTE").get("nome")),
        "existencia_bens": bens,
        "averbacao_anotacao": _averbacoes(con, int(assento["id"])),
        "anotacoes_cadastro": _anotacoes_de_cadastro(assento),
    }


def _inteiro_teor(assento: dict, grupos: dict[str, list[dict]],
                  texto: Any, avisos: list[str]) -> dict:
    """O inteiro teor. **O texto é o TERMO do assento, e não se inventa.**

    O contrato pede `texto_certidao`, e o que esta casa tem é o `teor` do
    assento — o texto que foi escrito no livro. **Os 244 assentos do acervo
    vieram sem teor** (medido), e para eles o inteiro teor não sai: o que se
    escreveria hoje não é o que está no livro de papel.
    """
    corpo = _texto(texto) or _texto(assento.get("teor"))
    if not corpo:
        avisos.append(
            "Este assento não tem teor gravado, e o inteiro teor é a "
            "reprodução do que está escrito no livro. Os assentos vindos do "
            "acervo do E-Ofício estão todos assim — para eles, a cópia se tira "
            "do livro de papel.")
    principal = (_um(grupos, "REGISTRADO") or _um(grupos, "FALECIDO")
                 or _um(grupos, "NUBENTE1"))
    segundo = _um(grupos, "NUBENTE2")
    return {
        "nome_completo": _texto(principal.get("nome")) or _texto(assento.get("nome")),
        "cpf": API.cpf_para_a_central(principal.get("documento_numero")),
        "matricula": _texto(assento.get("matricula")),
        "nome_secundario_completo": _texto(segundo.get("nome")),
        "cpf_secundario": API.cpf_para_a_central(segundo.get("documento_numero")),
        "texto_certidao": corpo,
    }


def corpo_crc(con: sqlite3.Connection, assento_id: int, *, cns: Any,
             **campos) -> dict:
    """O JSON {certidao, registro} no formato certificate-json da CRC/ON-RCPN.

    Reaproveita montar — **não inventa esquema paralelo**. Devolve só o que
    iria no POST /api/v1.0/certificate-json.

    Opção local enquanto a API CRC não está em uso operacional: só calcula,
    **não grava e não chama a Central**.
    """
    montado = montar(con, assento_id, cns=cns, **campos)
    return {"certidao": montado["certidao"], "registro": montado["registro"]}


def conferir(con: sqlite3.Connection, assento_id: int, *, cns: Any,
             **campos) -> dict:
    """O que iria para a Central, com o que impede e o que vai em branco.

    **NÃO GRAVA E NÃO MANDA.** É a tela anterior ao botão que publica.
    """
    montado = montar(con, assento_id, cns=cns, **campos)
    impedem: list[str] = []
    if not montado["certidao"].get("cartorio_cns"):
        impedem.append(
            "Sem o CNS da serventia a Central não sabe de quem é a certidão. "
            "Informe em Administrativo → Configurações.")
    if not montado["registro"].get("matricula"):
        impedem.append(
            "O assento está sem a matrícula de 32 dígitos, e é por ela que a "
            "Central identifica o registro. Ela se compõe na ficha do assento.")
    if montado["tipo_registro"] == "inteiro_teor" and not \
            montado["registro"].get("texto_certidao"):
        impedem.append(
            "Inteiro teor sem teor não se emite — ver o aviso acima.")
    if not API.tem_credencial():
        impedem.append(
            "O token do IdRC não foi informado, e sem ele nada sobe. "
            "É o mesmo token do e-Proclamas.")
    montado["impedem"] = impedem
    montado["pronto"] = not impedem
    return montado


def emitir(db, assento_id: int, *, cns: Any, agora: str,
           pedido_id: int | None = None, usuario: str | None = None,
           pasta=None, **campos) -> dict:
    """Cria a certidão eletrônica na Central e **grava o que se mandou**.

    A ordem é a de `proclamas.enviar`, e pelo mesmo motivo:

        conferir (leitura) → mandar (fora de transação) → gravar (transação
        curta)

    **A CHAMADA QUE ACONTECEU NÃO SOME DO RASTRO**: se a Central recusar, a
    tentativa fica registrada com o corpo congelado, e a recusa sobe para a
    tela.
    """
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        conferido = conferir(con, assento_id, cns=cns, **campos)
    if conferido["impedem"]:
        raise PedidoError(" ".join(conferido["impedem"]))

    corpo = {"certidao": conferido["certidao"], "registro": conferido["registro"]}
    feito = API.criar(conferido["certidao"], conferido["registro"], pasta=pasta)

    with db.transaction() as con:
        cur = con.execute(
            """INSERT INTO rc_certidoes_eletronicas(
                   assento_id, pedido_id, ambiente, tipo_registro,
                   tipo_certidao, modalidade, certidao_id, corpo_enviado,
                   corpo_hash, resposta, situacao, criada_em, criada_por)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (int(assento_id), int(pedido_id) if pedido_id else None,
             ambiente(), conferido["tipo_registro"],
             conferido["certidao"].get("tipo_certidao"),
             conferido["certidao"].get("modalidade", "eletronica"),
             feito["id"] or None,
             json.dumps(corpo, ensure_ascii=False), _hash(corpo),
             json.dumps(feito.get("bruto"), ensure_ascii=False),
             ESQ.CRIADA, agora, usuario))
    return {"eletronica_id": int(cur.lastrowid), "certidao_id": feito["id"],
            "mensagem": feito.get("mensagem"), "hash": _hash(corpo)}


def eletronica(con: sqlite3.Connection, eletronica_id: int) -> dict | None:
    """Uma certidão eletrônica desta casa. Só LÊ."""
    linha = con.execute(
        "SELECT * FROM rc_certidoes_eletronicas WHERE id=?",
        (int(eletronica_id),)).fetchone()
    return dict(linha) if linha else None


def eletronicas_do_assento(con: sqlite3.Connection,
                           assento_id: int) -> list[dict]:
    """As certidões eletrônicas daquele assento, da mais nova. Só LÊ."""
    return [dict(r) for r in con.execute(
        "SELECT * FROM rc_certidoes_eletronicas WHERE assento_id=? "
        "ORDER BY id DESC", (int(assento_id),))]


def corpo_crc_da_eletronica(con: sqlite3.Connection, eletronica_id: int, *,
                            cns: Any) -> dict:
    """O corpo já gravado (corpo_enviado) ou, se ainda não houve, o de agora.

    Opção local enquanto a API CRC não está em uso operacional.
    """
    linha = eletronica(con, eletronica_id)
    if not linha:
        raise PedidoError(
            f"A certidão eletrônica {eletronica_id} não existe.")
    bruto = _texto(linha.get("corpo_enviado"))
    if bruto:
        try:
            corpo = json.loads(bruto)
        except json.JSONDecodeError as erro:
            raise PedidoError(
                "O corpo_enviado desta certidão não é JSON válido.") from erro
        if (isinstance(corpo, dict) and isinstance(corpo.get("certidao"), dict)
                and isinstance(corpo.get("registro"), dict)):
            return {"certidao": corpo["certidao"],
                    "registro": corpo["registro"]}
        raise PedidoError(
            "O corpo_enviado desta certidão não tem certidao/registro.")
    return corpo_crc(
        con, int(linha["assento_id"]), cns=cns,
        tipo_registro=linha.get("tipo_registro") or None,
        tipo_certidao=linha.get("tipo_certidao") or None,
        modalidade=linha.get("modalidade") or "eletronica")


def assinar(db, eletronica_id: int, *, agora: str, usuario: str | None = None,
            pasta=None) -> dict:
    """Manda a Central assinar. Devolve o link. **Rede fora de transação.**

    A assinatura acontece **do lado de lá** — ver o cabeçalho de
    `onrcpn_certidao_api.assinar`: esta máquina não pode carregar o driver do
    A3 dentro do Flask sem derrubar o balcão.
    """
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        linha = eletronica(con, eletronica_id)
    if not linha:
        raise PedidoError(f"A certidão eletrônica {eletronica_id} não existe.")
    if not _texto(linha.get("certidao_id")):
        raise PedidoError(
            "Esta certidão não tem o identificador da Central, e é por ele que "
            "se assina. Ela pode ter sido criada e a resposta não ter chegado.")
    if linha["situacao"] == ESQ.CANCELADA:
        raise PedidoError("Esta certidão está cancelada; não se assina.")

    feito = API.assinar(linha["certidao_id"], pasta=pasta)
    with db.transaction() as con:
        con.execute(
            "UPDATE rc_certidoes_eletronicas SET situacao=?, "
            "assinatura_link=?, assinatura_id=?, assinada_em=? WHERE id=?",
            (ESQ.ASSINADA, feito["link"] or None,
             feito["id_assinatura"] or None, agora, int(eletronica_id)))
    return {"eletronica_id": int(eletronica_id), "link": feito["link"],
            "id_assinatura": feito["id_assinatura"]}


def atualizar_eletronica(db, eletronica_id: int, *, cns: Any, agora: str,
                         usuario: str | None = None, pasta=None,
                         **campos) -> dict:
    """Corrige na Central uma certidao ja criada, com os dados de agora.

    **O TIPO DE REGISTRO NAO SE ALTERA** — esta escrito na descricao do proprio
    caminho, e a Central recusa. Por isso ele nao vem do formulario: sai da
    linha que ja esta gravada.

    Existe porque o caminho oposto e pior: cancelar e criar de novo **queima o
    identificador** que o pedido ja pode ter recebido como `id_verificador`, e
    quem esta do outro lado ficaria com um numero que nao aponta para nada.
    """
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        linha = eletronica(con, eletronica_id)
        if not linha:
            raise PedidoError(
                f"A certidao eletronica {eletronica_id} nao existe.")
        if not _texto(linha.get("certidao_id")):
            raise PedidoError(
                "Esta certidao nao tem o identificador da Central, e e por ele "
                "que se corrige.")
        if linha["situacao"] == ESQ.CANCELADA:
            raise PedidoError("Esta certidao esta cancelada; nao se corrige.")
        campos.pop("tipo_registro", None)
        conferido = conferir(con, int(linha["assento_id"]), cns=cns,
                             tipo_registro=linha["tipo_registro"], **campos)
    if conferido["impedem"]:
        raise PedidoError(" ".join(conferido["impedem"]))

    corpo = {"certidao": conferido["certidao"],
             "registro": conferido["registro"]}
    feito = API.atualizar(linha["certidao_id"], conferido["certidao"],
                          conferido["registro"], pasta=pasta)
    with db.transaction() as con:
        con.execute(
            "UPDATE rc_certidoes_eletronicas SET corpo_enviado=?, "
            "corpo_hash=?, resposta=? WHERE id=?",
            (json.dumps(corpo, ensure_ascii=False), _hash(corpo),
             json.dumps(feito.get("bruto"), ensure_ascii=False),
             int(eletronica_id)))
    return {"eletronica_id": int(eletronica_id),
            "certidao_id": linha["certidao_id"],
            "mensagem": feito.get("mensagem"), "hash": _hash(corpo)}


def cancelar_eletronica(db, eletronica_id: int, *, agora: str,
                        usuario: str | None = None, pasta=None) -> dict:
    """Cancela a certidão eletrônica na Central.

    **Não cancela a certidão de papel** — aquele é outro ato, na ficha do
    assento, com motivo escrito. `rc_certidao.cancelar` continua sendo o
    caminho dele.
    """
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        linha = eletronica(con, eletronica_id)
    if not linha:
        raise PedidoError(f"A certidão eletrônica {eletronica_id} não existe.")
    if not _texto(linha.get("certidao_id")):
        raise PedidoError(
            "Esta certidão não tem o identificador da Central, e é por ele que "
            "se cancela.")
    API.cancelar(linha["certidao_id"], pasta=pasta)
    with db.transaction() as con:
        con.execute(
            "UPDATE rc_certidoes_eletronicas SET situacao=?, cancelada_em=?, "
            "cancelada_por=? WHERE id=?",
            (ESQ.CANCELADA, agora, usuario, int(eletronica_id)))
    return {"eletronica_id": int(eletronica_id)}


def buscar_na_central(eletronica_row: dict, *, pasta=None) -> dict:
    """Busca o PDF e a situação corrente na Central. **Só LÊ, e não grava.**

    O arquivo **não mora no banco** — ver o cabeçalho de `rc_pedidos_schema`.
    """
    if not _texto(eletronica_row.get("certidao_id")):
        raise PedidoError(
            "Esta certidão não tem o identificador da Central.")
    return API.buscar(eletronica_row["certidao_id"], pasta=pasta)


# ------------------------------------------------------- cumprir o pedido


def atender(db, pedido_id: int, *, eletronica_id: int,
            valor_emolumentos: Any, agora: str, uf_da_serventia: str = "",
            observacoes: Any = "", valor_adicional: Any = None,
            quantidade_averbacao: Any = None, usuario: str | None = None,
            pasta=None) -> dict:
    """Entrega a certidão ao requerente. **É a chamada que fecha o pedido.**

    `id_verificador` é o identificador que a Central devolveu ao criar a
    certidão; `id_externo` é o número desta casa — o `id` da linha local —,
    que é o que permite achar de que lado veio quando a Central perguntar.

    **`quantidade_averbacao` VAI NULO FORA DE SÃO PAULO**, e quem impõe isso é
    a descrição do próprio caminho. O Maranhão é outro estado.
    """
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        p = pedido(con, pedido_id)
        e = eletronica(con, eletronica_id)
    if not p:
        raise PedidoError(f"O pedido {pedido_id} não existe.")
    if not e:
        raise PedidoError(f"A certidão eletrônica {eletronica_id} não existe.")
    if p["situacao"] in ESQ.SITUACOES_TERMINAIS:
        raise PedidoError(
            f"Este pedido já saiu da fila como «{p['situacao'].lower()}».")
    if p["modulo"] in API.MODULOS_DE_REGISTRO:
        raise PedidoError(
            f"O módulo {p['modulo']} pede **registro**, e não certidão: "
            f"{API.NOME_DO_MODULO[p['modulo']]}. Lavre o assento na tela do "
            f"Registro Civil e depois marque este pedido como registrado.")
    if not _texto(e.get("certidao_id")):
        raise PedidoError(
            "A certidão eletrônica não tem o identificador da Central, e é ele "
            "que vai como «id_verificador».")
    if e["situacao"] == ESQ.CANCELADA:
        raise PedidoError(
            "Esta certidão eletrônica está cancelada; não se entrega.")

    feito = API.enviar_pedido(
        numero_pedido=p["numero_pedido"], modulo=p["modulo"],
        valor_emolumentos=valor_emolumentos,
        id_externo=str(e["id"]), id_verificador=e["certidao_id"],
        observacoes_emissao=observacoes, valor_adicional=valor_adicional,
        quantidade_averbacao=quantidade_averbacao,
        uf_da_serventia=uf_da_serventia, pasta=pasta)

    with db.transaction() as con:
        con.execute(
            "UPDATE rc_pedidos SET situacao=?, respondido_em=?, "
            "respondido_por=?, resposta=?, corpo_enviado=?, corpo_hash=? "
            "WHERE id=?",
            (ESQ.ATENDIDO, agora, usuario,
             json.dumps(feito.get("resposta"), ensure_ascii=False),
             json.dumps(feito["corpo"], ensure_ascii=False),
             _hash(feito["corpo"]), int(pedido_id)))
        con.execute(
            "UPDATE rc_certidoes_eletronicas SET pedido_id=? WHERE id=?",
            (int(pedido_id), int(eletronica_id)))
    return {"pedido_id": int(pedido_id), "eletronica_id": int(eletronica_id),
            "resposta": feito.get("resposta"), "corpo": feito["corpo"]}


def sugerir_valor_adicional(pedido_row: dict, valor_final: Any) -> dict:
    """A diferença entre o depósito prévio e o valor final. **Sugestão.**

    A descrição do caminho: «Representa a diferença entre o depósito prévio
    realizado no momento da solicitação e o valor final do serviço». O depósito
    vem da Central **com vírgula** (`"43,76"`) e o valor sobe **com ponto**
    (`"10.00"`) — quem subtrair sem converter erra por cem.

    **É sugestão, e a tela diz isso.** É a regra da receita de custas e a do
    protocolar da CENPROT: onde o erro custa dinheiro do cliente, quem responde
    é a pessoa.
    """
    deposito = float(pedido_row.get("deposito_previo_valor") or 0.0)
    final = API.ler_valor_da_central(valor_final)
    diferenca = round(final - deposito, 2)
    return {
        "deposito_previo": deposito,
        "valor_final": final,
        # **NEGATIVO NÃO VIRA ZERO CALADO.** Se o depósito foi maior que o
        # valor final, quem decide o que fazer é o balcão — devolver, abater ou
        # cobrar zero — e esconder a diferença tiraria a decisão dele.
        "valor_adicional": max(diferenca, 0.0),
        "houve_devolucao": diferenca < 0,
        "diferenca": diferenca,
    }
