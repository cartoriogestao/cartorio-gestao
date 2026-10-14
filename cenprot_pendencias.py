"""O que a CENPROT manda, e o que a casa responde — o domínio.

Ordem do oficial em 02/09/2026: *«acho que agora poderemos resolver todos
problemas do protesto. vamos integrar a api»*, e depois *«pode seguir na
construção»*.

**ESTE MÓDULO NÃO LAVRA ATO, E ISSO É A QUARTA VEZ QUE A REGRA APARECE** —
depois do usucapião, das fraudes e do CNIB. Ele baixa a pendência, guarda o
teor congelado, mostra ao balcão, registra a decisão do oficial e sobe a
resposta. **O ato de cancelamento continua se lavrando na ficha do título**,
com hipótese do catálogo e fundamento escrito; a sustação continua sendo
registrada por quem recebeu o mandado. Há teste que varre os nomes públicos
procurando `lavrar`, `protestar`, `cancelar_titulo`, `selar` e `cobrar`.

**BAIXAR E ENVIAR RECEBEM `db`; O RESTO RECEBE `con`.** É a mesma assinatura
de `ato_selado.obter_selo` e da ajuda do Claude, e pelo mesmo motivo: assim
**não há como chamar a rede de dentro de uma transação sem reparar**. Um
`BEGIN IMMEDIATE` segurado por trinta segundos de rede põe todo outro balcão
no `busy_timeout`.

**DECIDIR E ENVIAR SÃO DOIS PASSOS.** É a forma de `conferir`/`receber` da
remessa da CRA, e pela mesma razão: o que sobe **muda coisa na Central** —
aprova anuência, orça certidão, cancela protesto — e um botão que decidisse e
mandasse no mesmo clique faria vinte respostas saírem de uma vez, sem ninguém
ter olhado a vigésima.

**OS NOMES DOS CAMPOS SÃO MEDIDOS NO `swagger.yaml`, E NÃO SUPOSTOS.** Eu já
os inventei uma vez neste mesmo trabalho, e errei em quase todos — o estrago
seria calado, porque campo que a Central não conhece ela ignora. O que está
escrito aqui saiu do contrato, e há teste que confere cada um contra ele.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

import cenprot_api as API
import centrais_cred as CRED
import cn_schema as CN
import custas
import protesto_cenprot as PC


class PendenciaError(ValueError):
    """Erro de regra, com a mensagem pronta para o balcão."""


# COMO CADA ESPÉCIE SE BAIXA. Uma linha por espécie, e não cinco funções que
# fazem a mesma coisa — a lição do núcleo outra vez.
BAIXA_DA_ESPECIE: dict[str, Any] = {
    CN.ANUENCIA: API.anuencias,
    CN.CERTIDAO: API.certidoes,
    CN.CANCELAMENTO: API.pedidos_de_cancelamento,
    CN.DECISAO_JUDICIAL: API.decisoes_judiciais,
    CN.PEDIDO_PROTESTO: API.pedidos_de_protesto,
    CN.RENEGOCIACAO: API.renegociacoes,
}

# O CAMPO QUE IDENTIFICA CADA PENDÊNCIA NA RESPOSTA DA CENTRAL — **medido**,
# um por um, e eles NÃO se chamam a mesma coisa:
#
#     /v2/anuencias              cd_anuencia
#     /v2/certidoes              cd_pedido
#     /cancelamento/pedidos      nr_pedido          ← e não `cd_pedido`
#     /decisao-judicial/pendentes  nm_chave         ← não há `cd_*` nenhum
#     /pedidos/consulta          cd_pedido_protesto
CODIGO_DA_ESPECIE: dict[str, str] = {
    CN.ANUENCIA: "cd_anuencia",
    CN.CERTIDAO: "cd_pedido",
    CN.CANCELAMENTO: "nr_pedido",
    CN.DECISAO_JUDICIAL: "nm_chave",
    CN.PEDIDO_PROTESTO: "cd_pedido_protesto",
    # `/renegociacoes` → `cd_renegociacao_divida`, e o nome dele é o
    # sexto diferente numa API só. Medido no schema da resposta.
    CN.RENEGOCIACAO: "cd_renegociacao_divida",
}

# **O DO CANCELAMENTO É O ÚNICO QUE NÃO SE LÊ DIRETO, e fica declarado.**
#
# O `POST /cancelamento/cancelar-protesto` exige `cd_pedido` — «ID do pedido
# (tabela pedidos) obtido via GET /cancelamento/pedidos» —, e o GET **não
# devolve campo com esse nome**: devolve `nr_pedido` e `cd_pedido_cartorio`.
#
# Quem desempata são os EXEMPLOS do próprio contrato, que trazem números
# diferentes de propósito:
#
#     POST cd_pedido            example: 1000001
#     GET  nr_pedido            example: 1000001     ← bate
#     GET  cd_pedido_cartorio   example:  100001     ← não bate
#
# Mais o nome: `cd_pedido_cartorio` é o código **do cartório** para aquele
# pedido, que é outra coisa. **Um caso que separa vale mais que cinco que
# concordam** — é a régua que já decidiu o `numerotitulo` do edital.
#
# **E ISTO ESTÁ A CONFERIR NA HOMOLOGAÇÃO**, que é para isso que ela serve. A
# tela mostra o número antes de mandar, e a P21 vai liberar o ambiente de
# teste: enquanto não se conferir lá, o balcão vê de onde o número saiu.
CODIGO_DO_CANCELAMENTO_A_CONFERIR = (
    "O número que sobe no cancelamento é o `nr_pedido` que a Central devolveu. "
    "Confira-o na homologação antes de usar em produção — o contrato o chama "
    "de `cd_pedido` no envio e de `nr_pedido` na resposta.")

# ONDE MORA A CHAVE E O PROTOCOLO, quando a espécie os traz. São os dois
# campos por onde a pendência acha o título desta casa.
CAMPO_DA_CHAVE = "nm_chave"
CAMPO_DO_PROTOCOLO = "nm_nr_protocolo"

# O QUE A LINHA DA LISTA MOSTRA, na ordem em que o balcão lê.
CAMPOS_DO_RESUMO: tuple[str, ...] = (
    "nm_devedor", "nm_nr_titulo", "nm_nr_protocolo", "vl_protesto",
    "vl_titulo", "dt_pedido", "dt_solicitacao_anuencia", "dt_ocorrencia",
    # DA RENEGOCIAÇÃO: o que o devedor propôs, quando vence e em que pé
    # está. Sem eles a linha da proposta sairia com o nome do devedor e
    # mais nada — e o que se decide aqui é o valor.
    "vl_proposta", "dt_vencimento_proposta", "nm_descricao")


def _procurar(item: Any, campo: str) -> Any:
    """O valor daquele campo, **em qualquer profundidade** da resposta.

    **A CENTRAL DEVOLVE ANINHADO**, e não plano: o pedido de cancelamento vem
    em `dados_pedido`, `dados_solicitante`, `dados_cartorio` e `dados_anuencia`.
    Escrever o caminho de cada campo daria uma tabela de caminhos que
    envelheceria na primeira versão da API — e a resposta é dela, não nossa.

    Procura em largura, para que o campo do primeiro nível ganhe do homônimo
    de dentro de um bloco: `nm_chave` do pedido vale mais que o da anuência
    citada nele.
    """
    fila: list[Any] = [item]
    while fila:
        atual = fila.pop(0)
        if isinstance(atual, dict):
            if campo in atual and atual[campo] not in (None, ""):
                return atual[campo]
            fila.extend(v for v in atual.values() if isinstance(v, (dict, list)))
        elif isinstance(atual, list):
            fila.extend(v for v in atual if isinstance(v, (dict, list)))
    return None


def _resumo(item: Any) -> str:
    """A linha que o balcão lê, sem ele ter de abrir o JSON."""
    partes = []
    for campo in CAMPOS_DO_RESUMO:
        valor = _procurar(item, campo)
        if valor not in (None, ""):
            partes.append(str(valor))
        if len(partes) >= 4:
            break
    return " · ".join(partes)


def _lista_da_resposta(resposta: Any) -> list[dict]:
    """A lista de itens, venha ela crua ou embrulhada.

    **A MESMA API RESPONDE DAS DUAS FORMAS**, e por isso isto não se supõe: uns
    caminhos devolvem o array direto e outros o põem dentro de `data`, `dados`
    ou `pedidos`. Ler só um jeito faria metade das telas dizer «nada pendente»
    com a Central cheia — o pior tipo de zero, o que tem cara de medição.
    """
    if isinstance(resposta, list):
        return [i for i in resposta if isinstance(i, dict)]
    if isinstance(resposta, dict):
        for chave in ("data", "dados", "pedidos", "items", "resultado"):
            dentro = resposta.get(chave)
            if isinstance(dentro, list):
                return [i for i in dentro if isinstance(i, dict)]
        # um item só, fora de lista
        if any(k.startswith(("cd_", "nr_", "nm_", "dados_")) for k in resposta):
            return [resposta]
    return []


def _titulo_da_pendencia(con: sqlite3.Connection, item: dict) -> int | None:
    """O título desta casa, achado pela chave ou pelo protocolo. Só LÊ.

    **A CHAVE VEM PRIMEIRO PORQUE ELA É NACIONAL** — carrega o código IBGE do
    município e o número do cartório —, e o protocolo **não é**: a serventia
    vizinha tem o protocolo 2604170001 tanto quanto esta. É a mesma razão pela
    qual `protesto_imagens` prende por duas partes.

    **Não achar não é defeito**: a pendência entra assim mesmo, e a tela mostra
    que ela não casou. Pendência sem título é justamente o que o balcão precisa
    olhar primeiro — pode ser título que não entrou, ou pedido de outra casa.
    """
    chave = PC.so_digitos(_procurar(item, CAMPO_DA_CHAVE) or "")
    if chave and PC.decompor_chave(chave):
        linha = con.execute(
            "SELECT id FROM pt_titulos WHERE chave_cenprot = ? LIMIT 2",
            (chave,)).fetchall()
        if len(linha) == 1:
            return int(linha[0][0])
        if len(linha) > 1:
            # Duas linhas com a mesma chave é defeito de dado, e escolher uma
            # seria escolher no escuro. Fica sem casar, e à vista.
            return None
    protocolo = str(_procurar(item, CAMPO_DO_PROTOCOLO) or "").strip()
    if protocolo:
        linha = con.execute(
            "SELECT id FROM pt_titulos WHERE TRIM(protocolo) = ? LIMIT 2",
            (protocolo,)).fetchall()
        if len(linha) == 1:
            return int(linha[0][0])
    return None


def _especie(qual: Any) -> str:
    nome = str(qual or "").strip().upper()
    if nome not in CN.ESPECIES:
        raise PendenciaError(
            f"Espécie desconhecida: «{qual}». As que existem são "
            f"{', '.join(CN.ESPECIES)}.")
    return nome


# ------------------------------------------------------------------ baixar


def baixar(db, especie: Any, *, ambiente: Any = CRED.HOMOLOGACAO,
           quem: str = "", pasta=None, **filtros) -> dict:
    """Traz da Central o que está pendente e guarda o que ainda não estava.

    **RECEBE `db`, E NÃO `con`** — a chamada de rede acontece FORA de qualquer
    transação, e só depois se abre a transação curta que grava.

    Devolve `{especie, ambiente, vieram, entraram, repetidas, sem_titulo}`.
    **`vieram` e `entraram` são contadores diferentes**, e somá-los é o defeito
    que a carga do acervo já cometeu: repetida não é entrada, e dizer «entraram
    50» numa baixa em que 48 já estavam faria o balcão procurar 50 linhas
    novas.
    """
    qual = _especie(especie)
    onde = str(ambiente or "").strip().upper() or CRED.HOMOLOGACAO
    resposta = BAIXA_DA_ESPECIE[qual](onde, pasta=pasta, **filtros)
    itens = _lista_da_resposta(resposta)

    campo = CODIGO_DA_ESPECIE[qual]
    entraram = repetidas = sem_codigo = sem_titulo = 0
    agora = db.now()
    with db.transaction() as con:
        for item in itens:
            codigo = str(_procurar(item, campo) or "").strip()
            if not codigo:
                # **NÃO SE INVENTA CÓDIGO.** Sem ele não há como responder à
                # Central, e uma linha sem resposta possível é pior que a
                # ausência dela: o balcão a olharia todo dia sem saída.
                sem_codigo += 1
                continue
            titulo_id = _titulo_da_pendencia(con, item)
            if titulo_id is None:
                sem_titulo += 1
            cur = con.execute(
                """INSERT OR IGNORE INTO cn_pendencias
                       (especie, ambiente, codigo, chave, titulo_id, teor,
                        resumo, baixada_em, baixada_por, situacao)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (qual, onde, codigo,
                 PC.so_digitos(_procurar(item, CAMPO_DA_CHAVE) or "") or None,
                 titulo_id, json.dumps(item, ensure_ascii=False),
                 _resumo(item), agora, quem or None, CN.PENDENTE))
            # **CONTAR PELO `lastrowid` MUDAR, e não pela tentativa.** O
            # `OR IGNORE` não estoura no repetido, e contar tentativa foi
            # exatamente o que fez a carga dizer «entraram 20» com a tabela
            # em zero.
            if cur.rowcount:
                entraram += 1
            else:
                repetidas += 1
    return {"especie": qual, "ambiente": onde, "vieram": len(itens),
            "entraram": entraram, "repetidas": repetidas,
            "sem_codigo": sem_codigo, "sem_titulo": sem_titulo}


# ------------------------------------------------------------------ olhar


def abertas(con: sqlite3.Connection, *, especie: Any = None,
            ambiente: Any = None, limite: int = 200) -> list[dict]:
    """A fila do balcão: o que chegou e ainda não foi respondido. Só LÊ."""
    onde = ["p.situacao NOT IN (?, ?)"]
    valores: list[Any] = [CN.ENVIADA, CN.DISPENSADA]
    if especie:
        onde.append("p.especie = ?")
        valores.append(_especie(especie))
    if ambiente:
        onde.append("p.ambiente = ?")
        valores.append(str(ambiente).strip().upper())
    valores.append(int(limite))
    linhas = con.execute(
        f"""SELECT p.*, t.numero_titulo, t.protocolo AS titulo_protocolo,
                   t.situacao AS titulo_situacao
              FROM cn_pendencias p
              LEFT JOIN pt_titulos t ON t.id = p.titulo_id
             WHERE {' AND '.join(onde)}
             ORDER BY p.especie, p.baixada_em DESC, p.id DESC
             LIMIT ?""", valores).fetchall()
    return [dict(linha) for linha in linhas]


def uma(con: sqlite3.Connection, pendencia_id: int) -> dict | None:
    """Uma pendência, com o teor aberto para a tela mostrar. Só LÊ."""
    linha = con.execute(
        """SELECT p.*, t.numero_titulo, t.protocolo AS titulo_protocolo,
                  t.situacao AS titulo_situacao,
                  t.valor_centavos AS titulo_valor_centavos
             FROM cn_pendencias p
             LEFT JOIN pt_titulos t ON t.id = p.titulo_id
            WHERE p.id = ?""", (int(pendencia_id),)).fetchone()
    if linha is None:
        return None
    fora = dict(linha)
    try:
        fora["teor_aberto"] = json.loads(fora.get("teor") or "{}")
    except ValueError:
        # Teor que não abre continua valendo como registro do que chegou, e a
        # tela mostra o texto cru em vez de estourar.
        fora["teor_aberto"] = None
    try:
        fora["decisao_aberta"] = json.loads(fora.get("decisao") or "null")
    except ValueError:
        fora["decisao_aberta"] = None
    return fora


def retirada_sugerida(con: sqlite3.Connection, pendencia: dict,
                      *, hoje: str) -> dict:
    """O que o devedor paga para retirar aquele título. Só LÊ.

    **É SUGESTÃO, E A TELA DIZ ISSO** — a mesma regra da receita de custas e da
    participação das partes na DOI: o número vem do que a casa cobra, e quem
    confirma é quem atende. Devolver como valor fechado faria o balcão cobrar
    pela tabela em vez de pelo caso.

    **E ELE NÃO SE DIGITAVA: JÁ ESTAVA CALCULADO.** `protesto_cenprot.
    precos_do_titulo` monta a retirada da constante somada da tabela mais a
    faixa do item 17.4 pelo valor do título — **166 de 173 no centavo**,
    medido no arquivo do ano que o oficial baixou do E-Ofício. A tela mandava
    redigitar o que o sistema sabia: é «a peça está pronta e quem devia
    chamá-la não chama», pela décima vez neste projeto.

    Devolve `{"centavos": int|None, "reais": str, "motivo": str}` — e
    **`None` não vira zero**: zero é uma afirmação («não custa nada»), e o
    devedor viria ao balcão com ela.
    """
    valor = pendencia.get("titulo_valor_centavos")
    if pendencia.get("titulo_id") is None or valor in (None, ""):
        return {"centavos": None, "reais": "",
                "motivo": ("esta pendência não casou com título desta casa, e "
                           "sem o valor do título não há faixa a aplicar")}
    try:
        vigente = custas.vigencia_do_dia(con, str(hoje)[:10])
        precos = PC.precos_do_titulo(con, int(valor),
                                     vigencia=int(vigente["codigo"]))
    except (custas.CustasError, PC.CenprotError) as erro:
        # **A FALHA VOLTA COMO MOTIVO, E NÃO COMO ZERO.** Zero num campo de
        # dinheiro é afirmação; «não deu para calcular» é o que se sabe.
        return {"centavos": None, "reais": "", "motivo": str(erro)}
    centavos = precos.get("retirada")
    if centavos is None:
        return {"centavos": None, "reais": "",
                "motivo": (f"o valor do título (R$ {int(valor) / 100:.2f}) não "
                           f"cai em nenhuma faixa do item 17.4 desta vigência")}
    return {"centavos": int(centavos),
            "reais": f"{int(centavos) // 100}.{int(centavos) % 100:02d}",
            "motivo": (f"somado da tabela desta casa: a constante da retirada "
                       f"mais a faixa do item 17.4 pelo valor do título "
                       f"(R$ {int(valor) / 100:.2f})")}


def custa_de_cancelamento_sugerida(con: sqlite3.Connection, pendencia: dict,
                                   *, hoje: str) -> dict:
    """A custa de cancelamento daquele título. Só LÊ.

    **É OUTRO NÚMERO, E NÃO O DA RETIRADA.** `precos_do_titulo` devolve os
    dois — `retirada` e `cancelamento` —, e eles não são o mesmo: retirar é o
    devedor pagar antes de o protesto sair; cancelar é desfazer o protesto já
    lavrado. **O `cancelamento` já estava calculado e ninguém o usava** — a
    peça pronta que quem devia chamar não chamava, pela décima primeira vez
    neste projeto.

    Trocar um pelo outro mandaria à Central um valor que o devedor **paga**:
    é o tipo de engano que não aparece em tela nenhuma e só se descobre no
    balcão, com o cliente reclamando do preço.

    **É SUGESTÃO, e a tela diz isso** — a mesma regra da retirada. E `None`
    não vira zero: zero afirma «não custa nada», e o devedor viria com essa
    afirmação na mão.
    """
    valor = pendencia.get("titulo_valor_centavos")
    if pendencia.get("titulo_id") is None or valor in (None, ""):
        return {"centavos": None, "reais": "",
                "motivo": ("esta pendência não casou com título desta "
                           "casa, e sem o valor do título não há faixa a "
                           "aplicar")}
    try:
        vigente = custas.vigencia_do_dia(con, str(hoje)[:10])
        precos = PC.precos_do_titulo(con, int(valor),
                                     vigencia=int(vigente["codigo"]))
    except (custas.CustasError, PC.CenprotError) as erro:
        return {"centavos": None, "reais": "", "motivo": str(erro)}
    centavos = precos.get("cancelamento")
    if centavos is None:
        return {"centavos": None, "reais": "",
                "motivo": (f"o valor do título (R$ {int(valor) / 100:.2f}) não "
                           f"cai em nenhuma faixa desta vigência")}
    return {"centavos": int(centavos),
            "reais": f"{int(centavos) // 100}.{int(centavos) % 100:02d}",
            "motivo": (f"somado da tabela desta casa: a constante do "
                       f"cancelamento mais a faixa pelo valor do título "
                       f"(R$ {int(valor) / 100:.2f})")}


def painel(con: sqlite3.Connection) -> list[dict]:
    """Quantas esperam, por espécie — para a tela do dia do Protesto.

    **CONTA, E NÃO JULGA.** Um zero aqui pode ser «nada chegou hoje» ou «ainda
    não baixei», e o sistema não tem como saber qual: dizer «em atraso» sobre
    um dia em que nada veio é o alarme que soa sempre. A tela mostra o número e
    **quando foi a última baixa**, que é o que responde a diferença.
    """
    fora = []
    for especie in CN.ESPECIES:
        linha = con.execute(
            """SELECT COUNT(*) AS quantas, MAX(baixada_em) AS ultima
                 FROM cn_pendencias
                WHERE especie = ? AND situacao NOT IN (?, ?)""",
            (especie, CN.ENVIADA, CN.DISPENSADA)).fetchone()
        ultima = con.execute(
            "SELECT MAX(baixada_em) FROM cn_pendencias WHERE especie = ?",
            (especie,)).fetchone()
        fora.append({"especie": especie,
                     "nome": CN.NOME_DA_ESPECIE[especie],
                     "esperando": int(linha["quantas"] or 0),
                     "ultima_baixa": (ultima[0] if ultima else None)})
    return fora


# ------------------------------------------------------------ decidir


def _o_cancelamento_ja_esta_lavrado(con: sqlite3.Connection,
                                    pendencia_id: int) -> None:
    """Responder «cancelei» à CENPROT só depois de cancelar. Só LÊ.

    **O CAMINHO DO CONTRATO** (ordem do oficial em 13/10/2026: «vamos seguir o
    caminho do contrato»): a anuência chega, a casa cota, o interessado pede o
    cancelamento — e o pedido chega com a anuência aprovada e o valor dos
    emolumentos —, a casa LAVRA o cancelamento na ficha do título e, só então,
    informa a Central. Informar antes faria a Central dar o protesto por
    cancelado enquanto o livro desta casa continua dizendo que ele está de pé.
    """
    linha = con.execute(
        """SELECT p.especie, p.titulo_id, t.situacao
             FROM cn_pendencias p LEFT JOIN pt_titulos t ON t.id = p.titulo_id
            WHERE p.id = ?""", (pendencia_id,)).fetchone()
    if linha is None or linha["especie"] != CN.CANCELAMENTO:
        return
    if linha["titulo_id"] is None:
        raise PendenciaError(
            "Este pedido de cancelamento não casou com título desta casa — não "
            "há protesto aqui para dizer que foi cancelado. Confira na Central "
            "de que título ele fala.")
    if linha["situacao"] != "CANCELADO":
        raise PendenciaError(
            f"O protesto deste título ainda está {linha['situacao']} no livro "
            f"desta casa. Lavre o cancelamento na ficha do título (hipótese "
            f"«Anuência do credor»), com os emolumentos pagos, e só depois "
            f"informe a Central.")


def decidir(con: sqlite3.Connection, pendencia_id: int, *, decisao: dict,
            quem: str = "", agora: str) -> None:
    """Guarda o que o oficial decidiu. **NÃO MANDA NADA À CENTRAL.**

    Separar isto do envio é a forma de `conferir`/`receber` da remessa: entre
    decidir e mandar cabe uma releitura, e o que sobe muda coisa na Central.
    """
    linha = con.execute(
        "SELECT situacao FROM cn_pendencias WHERE id = ?",
        (int(pendencia_id),)).fetchone()
    if linha is None:
        raise PendenciaError("Essa pendência não existe mais na lista.")
    if linha["situacao"] == CN.ENVIADA:
        # **NADA SAI DUAS VEZES** — a regra do retorno à CRA. Redecidir o que
        # já subiu faria a segunda resposta contradizer a primeira lá dentro.
        raise PendenciaError(
            "Essa pendência já foi respondida à CENPROT, e a resposta não se "
            "refaz por aqui. Se a decisão mudou, trate com a Central.")
    if not isinstance(decisao, dict) or not decisao:
        raise PendenciaError("Informe a decisão antes de gravar.")
    _o_cancelamento_ja_esta_lavrado(con, int(pendencia_id))
    con.execute(
        """UPDATE cn_pendencias
              SET decisao = ?, decidida_em = ?, decidida_por = ?,
                  situacao = ?
            WHERE id = ?""",
        (json.dumps(decisao, ensure_ascii=False), agora, quem or None,
         CN.DECIDIDA, int(pendencia_id)))


def dispensar(con: sqlite3.Connection, pendencia_id: int, *, motivo: str,
              quem: str = "", agora: str) -> None:
    """Tira da fila o que não é desta casa ou não tem o que responder.

    **DISPENSAR EXIGE MOTIVO ESCRITO**, como no usucapião e na pendência de
    numeração: dispensar é decisão de quem responde pela serventia; ignorar
    não é. E o motivo fica, porque em seis meses ninguém lembra.
    """
    if not str(motivo or "").strip():
        raise PendenciaError(
            "Escreva por que esta pendência sai da lista — sem o motivo, quem "
            "olhar daqui a seis meses não terá como saber.")
    linha = con.execute(
        "SELECT situacao FROM cn_pendencias WHERE id = ?",
        (int(pendencia_id),)).fetchone()
    if linha is None:
        raise PendenciaError("Essa pendência não existe mais na lista.")
    if linha["situacao"] == CN.ENVIADA:
        raise PendenciaError(
            "Essa pendência já foi respondida à CENPROT, e o que subiu não se "
            "apaga daqui.")
    con.execute(
        """UPDATE cn_pendencias
              SET situacao = ?, dispensa_motivo = ?, decidida_em = ?,
                  decidida_por = ?
            WHERE id = ?""",
        (CN.DISPENSADA, str(motivo).strip(), agora, quem or None,
         int(pendencia_id)))


# ------------------------------------------------------------- enviar


def decididas(con: sqlite3.Connection, especie: Any,
              ambiente: Any = CRED.HOMOLOGACAO) -> list[dict]:
    """O que já tem decisão e ainda não subiu. Só LÊ — é o que o envio manda."""
    linhas = con.execute(
        """SELECT * FROM cn_pendencias
            WHERE especie = ? AND ambiente = ? AND situacao = ?
            ORDER BY id""",
        (_especie(especie), str(ambiente).strip().upper(),
         CN.DECIDIDA)).fetchall()
    return [dict(linha) for linha in linhas]


def enviar(db, especie: Any, *, ambiente: Any = CRED.HOMOLOGACAO,
           quem: str = "", pasta=None) -> dict:
    """Sobe à Central o que o oficial decidiu. **ESCREVE NA CENTRAL.**

    **RECEBE `db`, E A CHAMADA É FORA DA TRANSAÇÃO** — a mesma regra da baixa.
    E o registro do que subiu se grava **depois** da resposta: gravar antes
    faria a lista dizer «respondida» num dia em que a internet caiu.

    **A RESPOSTA DA CENTRAL FICA GRAVADA**, e não só o «deu certo»: quando ela
    reclamar de uma anuência, é esse texto que se lê.
    """
    qual = _especie(especie)
    onde = str(ambiente or "").strip().upper() or CRED.HOMOLOGACAO
    if qual not in _MANDA_DA_ESPECIE:
        # A decisao judicial so se BAIXA — ver a nota no fim do modulo.
        raise PendenciaError(
            f"{CN.NOME_DA_ESPECIE[qual]} nao se responde pela API: quem "
            f"registra a ordem do juiz, com o juizo, o processo e a data do "
            f"recebimento, e o oficial, na tela de sustacao do titulo.")
    with db.transaction() as con:
        fila = decididas(con, qual, onde)
    if not fila:
        raise PendenciaError(
            f"Não há {CN.NOME_DA_ESPECIE[qual].lower()} decidida esperando "
            f"envio. Decida na lista antes de mandar.")

    corpos = []
    for linha in fila:
        try:
            corpos.append(json.loads(linha["decisao"] or "null"))
        except ValueError as erro:
            raise PendenciaError(
                f"A decisão da pendência {linha['id']} não abre — grave-a de "
                f"novo antes de enviar.") from erro

    resposta = _MANDA_DA_ESPECIE[qual](corpos, onde, pasta=pasta)

    agora = db.now()
    texto = json.dumps(resposta, ensure_ascii=False)[:4000]
    with db.transaction() as con:
        for linha in fila:
            con.execute(
                """UPDATE cn_pendencias
                      SET situacao = ?, enviada_em = ?, enviada_por = ?,
                          resposta = ?
                    WHERE id = ? AND situacao = ?""",
                (CN.ENVIADA, agora, quem or None, texto, linha["id"],
                 CN.DECIDIDA))
    return {"especie": qual, "ambiente": onde, "enviadas": len(fila),
            "resposta": resposta}


def _mandar_anuencias(corpos: list, ambiente, *, pasta=None):
    return API.processar_anuencia(corpos, ambiente, pasta=pasta)


def _mandar_certidoes(corpos: list, ambiente, *, pasta=None):
    return API.processar_certidao(corpos, ambiente, pasta=pasta)


def _mandar_cancelamentos(corpos: list, ambiente, *, pasta=None):
    """**UM POR VEZ, porque o contrato é unitário.** O `cancelar-protesto`
    recebe um objeto, e não um array — escrever aqui um lote faria a Central
    recusar o corpo inteiro, ou pior, cancelar só o primeiro."""
    fora = []
    for corpo in corpos:
        fora.append(API.cancelar_protesto(
            corpo.get("cd_pedido"), ambiente,
            certidao_b64=str(corpo.get("certidao_cancelamento_b64") or ""),
            pasta=pasta))
    return fora


def _mandar_renegociacoes(corpos: list, ambiente, *, pasta=None):
    """**EM LOTE, porque o contrato é de lote** — até 1.000 por vez, e o
    `processar_renegociacoes` recusa acima disso antes de bater na rede."""
    return API.processar_renegociacoes(corpos, ambiente, pasta=pasta)


def _mandar_protocolos(corpos: list, ambiente, *, pasta=None):
    return API.protocolar_pedidos(corpos, ambiente, pasta=pasta)


# **A DECISÃO JUDICIAL NÃO SOBE POR AQUI, E É DELIBERADO.** O
# `/decisao-judicial/processar/{nm_chave}` responde a uma ordem do juiz, e
# **o sistema não julga ordem judicial**: quem registra a sustação, com o
# juízo, o processo e a data do recebimento, é o oficial, na tela que a
# 01/09/2026 construiu. Aqui ela só é BAIXADA, para o balcão saber que ela
# existe — que é justamente o que faltava para o «A protestar» não oferecer,
# no meio dos outros, um título que o juiz mandou parar.
_MANDA_DA_ESPECIE: dict[str, Any] = {
    CN.ANUENCIA: _mandar_anuencias,
    CN.CERTIDAO: _mandar_certidoes,
    CN.CANCELAMENTO: _mandar_cancelamentos,
    CN.PEDIDO_PROTESTO: _mandar_protocolos,
    CN.RENEGOCIACAO: _mandar_renegociacoes,
}

ESPECIES_QUE_SO_SE_BAIXAM: frozenset[str] = frozenset({CN.DECISAO_JUDICIAL})
