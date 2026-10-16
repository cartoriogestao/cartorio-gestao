"""O selo de BUSCA que vai junto com a certidão — as faixas de tempo de cada
atribuição, e o envelope medido. SÓ CALCULA: não fala com a rede e não grava.

    «colocar selo de busca para ir junto com as certidões (escolhe o item de
     tempo pelo protocolo ou por seleção manual quando da emissão da
     certidão)»  — pedido do oficial, 15/10/2026

A TABELA DO TJMA (vigência 10022, `cx_servicos`) TEM UM GRUPO «DAS BUSCAS» EM
CADA ATRIBUIÇÃO, e as faixas são as mesmas nas cinco: até 2, 5, 10, 15, 20,
30, 50 anos, e acima de 50 — Notas 13.13.1–8, RCPN 14.6.1–8, RTD/PJ
15.11.1–8, RI 16.25.1–8, Protesto 17.6.1–8. Cada grupo tem ainda o «.9»: «se
indicados dia, mês e ano da prática do ato, ou número e livro corretos do ato,
não serão cobradas buscas» — R$ 0,00. **No Protesto o 17.6.1 está REVOGADO**
na tabela (medido: «REVOGADO», R$ 0,00): a faixa mais curta dele é a de cinco
anos.

O PRECEDENTE, MEDIDO NO ACERVO DO E-OFÍCIO EM 15/10/2026
    **A busca é SELO PRÓPRIO, e nunca item dentro do pedido da certidão.** Os
    91 selos de busca do acervo saíram cada um num pedido, com `quantidade`
    1, no MESMO protocolo geral da certidão (87 dos 91 têm protocolo):

    | atribuição | selos | caminho | faixas usadas |
    |---|---|---|---|
    | Protesto | 51 | `/selo/protesto/atos-em-geral` (51) | 17.6.2 em 47, 17.6.3 em 3, 17.6.1 em 1 |
    | RI | 32 | `/selo/imovel/atos-em-geral` (27, 2022–2025) e `/selo/imovel/certidao` (5, 2020) | 16.25.2 a 16.25.7 (16.25.7 em 15) |
    | RCPN | 8 | `/selo/civil/atos-em-geral` (7, até 2024) e `/selo/civil/nascimento/segunda-via` (1, 30/07/2026) | 14.6.1, 14.6.6, 14.6.7, 14.6.8 |
    | Notas · RTD/PJ | **0** | — | — |

    O caso de 30/07/2026 é o mais novo e decide o civil: protocolo
    2026.07.276, dois selos com um segundo de diferença pelo MESMO caminho da
    segunda via — `14.5.1` (CERTID…, R$ 53,58) e `14.6.6` (BRCXXX…, R$ 45,58)
    —, com o mesmo livro, folha, termo e a MESMA folha de segurança nos dois.
    Dois selos, um papel.

    **E A FREQUÊNCIA É O QUE O PEDIDO MUDA.** Medido pelo protocolo geral:
    a busca acompanhou **50 de 119** certidões do Protesto, **27 de 482** do
    RI e **5 de 1.341** do RCPN. No E-Ofício ela era exceção que o balcão
    acrescentava; a ordem de 15/10/2026 a põe na tela de toda certidão, com o
    «.9» à mão para quando a busca não se cobra.

QUEM ESCOLHE A FAIXA
    O tempo entre a data do ato certificado (o registro, a abertura da
    matrícula, a lavratura) e a data da emissão SUGERE o item; quem emite
    confere e troca na tela. **Sem data do ato não há sugestão**, e a tela
    exige a escolha: certidão negativa e busca por nome não têm ato de onde
    contar. No Protesto quem diz o tempo é o PERÍODO pesquisado — a certidão
    já pergunta quantos anos —, e não um ato.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


class BuscaError(ValueError):
    """Recusa de regra, com a frase pronta para o balcão."""


# O NÚMERO DO GRUPO «DAS BUSCAS» DE CADA ATRIBUIÇÃO, lido em `cx_servicos`
# (vigência 10022) em 15/10/2026. A chave é o nome canônico que este módulo
# usa; os apelidos das telas vão em `APELIDOS`.
GRUPO_DA_BUSCA: dict[str, str] = {
    "NOTAS": "13.13",
    "RCPN": "14.6",
    "RTDPJ": "15.11",
    "IMOVEL": "16.25",
    "PROTESTO": "17.6",
}

# AS TELAS DESTA CASA CHAMAM A MESMA ATRIBUIÇÃO DE NOMES DIFERENTES — `RI` e
# `IMOVEL`, `CIVIL` e `RCPN`, `RCPJ_RTD` —, e o Livro 3 é do Registro de
# Imóveis (é por isso que a certidão dele sela pela família `imovel`).
APELIDOS: dict[str, str] = {
    "RI": "IMOVEL", "LIVRO3": "IMOVEL", "IMOVEIS": "IMOVEL",
    "CIVIL": "RCPN",
    "RCPJ": "RTDPJ", "RTD": "RTDPJ", "RCPJ_RTD": "RTDPJ", "RG": "RTDPJ",
    "TABELIONATO": "NOTAS",
}

# AS FAIXAS SÃO AS MESMAS NAS CINCO, e o último algarismo do item é a ordem
# delas: `(anos até, sufixo, rótulo)`. `None` é «acima de cinquenta anos».
FAIXAS: tuple[tuple[int | None, int, str], ...] = (
    (2, 1, "Até dois anos"),
    (5, 2, "Até cinco anos"),
    (10, 3, "Até dez anos"),
    (15, 4, "Até quinze anos"),
    (20, 5, "Até vinte anos"),
    (30, 6, "Até trinta anos"),
    (50, 7, "Até cinquenta anos"),
    (None, 8, "Acima de cinquenta anos"),
)

# O 17.6.1 ESTÁ REVOGADO NA TABELA — medido em `cx_servicos` (vigência 10022):
# descrição «REVOGADO», R$ 0,00. Até dois anos, no Protesto, cai na faixa de
# cinco. **O acervo tem UM selo 17.6.1** (26/01/2024): foi vendido por um item
# que hoje não existe, e não se repete.
FAIXAS_REVOGADAS: dict[str, frozenset[int]] = {"PROTESTO": frozenset({1})}

# O «.9»: indicados dia, mês e ano do ato (ou livro e número corretos), não se
# cobram buscas. R$ 0,00 em todos os grupos. **Não vira selo** — ver
# `vira_selo`.
SUFIXO_SEM_COBRANCA = 9

ROTULO_SEM_COBRANCA: dict[str, str] = {
    "NOTAS": "Sem busca — dia, mês e ano, ou livro e número do ato indicados",
    "RCPN": "Sem busca — dia, mês e ano, ou livro e número do ato indicados",
    "RTDPJ": "Sem busca — dia, mês e ano, ou livro e número do ato indicados",
    "IMOVEL": ("Sem busca — dia, mês e ano, número da matrícula ou número de "
               "ordem indicados"),
    "PROTESTO": "Sem busca — dia, mês e ano da prática do ato indicados",
}

# AS CERTIDÕES QUE JÁ TRAZEM A BUSCA DENTRO DO PREÇO — a descrição do item diz
# com todas as letras: «Certidão Eletrônica COM BUSCAS e folhas excedentes
# incluídas» (13.12.4, 14.5.7), «incluídas buscas de 05 (cinco) anos» (17.5.5)
# e «incluídas buscas e folhas excedentes — por registro» (17.5.4). Vender a
# busca junto delas seria cobrar duas vezes a mesma coisa.
CERTIDOES_QUE_JA_INCLUEM_BUSCA = frozenset({"13.12.4", "14.5.7", "17.5.4",
                                            "17.5.5"})

# O CAMINHO DO SELO DA BUSCA, onde ele é próprio. O civil não está aqui de
# propósito: a busca do civil sai pelo caminho da SEGUNDA VIA, com o item no
# `codigoTipoAtoCertidao` (o caso de 30/07/2026), e quem monta aquele envelope
# é `ato_selado.envelope_do_civil` — que já recebe o item pronto.
#
# NOTAS E RTD/PJ NÃO TÊM PRECEDENTE (zero selos de busca no acervo), e o
# caminho deles é DECISÃO DO OFICIAL de 15/10/2026: «a busca sai como selo
# próprio pelo caminho de atos em geral da atribuição». O do RTD/PJ é o mesmo
# `ato_selado.CAMINHO_RTDPJ_GERAL` por onde a certidão dele já sela.
CAMINHO_DO_SELO_DA_BUSCA: dict[str, str] = {
    "IMOVEL": "/selo/imovel/atos-em-geral",
    "PROTESTO": "/selo/protesto/atos-em-geral",
    "NOTAS": "/selo/notas/atos-em-geral",
    "RTDPJ": "/selo/rtdpj/atos-em-geral",
}


def atribuicao_canonica(atribuicao: Any) -> str:
    """`RI` → `IMOVEL`; nome desconhecido devolve vazio. Só calcula."""
    nome = str(atribuicao or "").strip().upper()
    nome = APELIDOS.get(nome, nome)
    return nome if nome in GRUPO_DA_BUSCA else ""


def _grupo(atribuicao: Any) -> str:
    canonica = atribuicao_canonica(atribuicao)
    if not canonica:
        raise BuscaError(
            f"Não há grupo de buscas na tabela para a atribuição "
            f"«{atribuicao}».")
    return canonica


def opcoes(atribuicao: Any) -> list[dict]:
    """As faixas daquela atribuição, mais o «.9», na ordem da tabela."""
    canonica = _grupo(atribuicao)
    grupo = GRUPO_DA_BUSCA[canonica]
    revogadas = FAIXAS_REVOGADAS.get(canonica, frozenset())
    saida = [{"codigo": f"{grupo}.{sufixo}", "rotulo": rotulo, "cobra": True}
             for _anos, sufixo, rotulo in FAIXAS if sufixo not in revogadas]
    saida.append({"codigo": f"{grupo}.{SUFIXO_SEM_COBRANCA}",
                  "rotulo": ROTULO_SEM_COBRANCA[canonica], "cobra": False})
    return saida


def codigos(atribuicao: Any) -> set[str]:
    """Os códigos aceitos na tela daquela atribuição. Só calcula."""
    return {o["codigo"] for o in opcoes(atribuicao)}


def e_item_de_busca(codigo: Any) -> bool:
    """`16.25.4` é busca; `16.24.1` não é. Só calcula.

    Compara o GRUPO, e não um prefixo de texto: `14.6` casaria com `14.60`.
    """
    partes = str(codigo or "").strip().split(".")
    return len(partes) == 3 and ".".join(partes[:2]) in GRUPO_DA_BUSCA.values()


def vira_selo(codigo: Any) -> bool:
    """O item gera selo? O «.9» não: ele é a busca que NÃO se cobra.

    **NÃO HÁ PRECEDENTE DE SELO «.9»** — zero no acervo —, e vender um selo de
    R$ 0,00 para dizer que nada se cobrou seria inventar ato. A escolha fica
    na auditoria da certidão, que é onde a correição pergunta.
    """
    texto = str(codigo or "").strip()
    return e_item_de_busca(texto) and not texto.endswith(
        f".{SUFIXO_SEM_COBRANCA}")


def ja_inclui_busca(itens: Any) -> bool:
    """Algum dos itens da certidão já traz a busca no preço? Só calcula."""
    return any(str(c or "").strip() in CERTIDOES_QUE_JA_INCLUEM_BUSCA
               for c in (itens or ()))


def busca_entre(itens: Any, atribuicao: Any = None) -> str | None:
    """O item de busca que já está entre os itens (do protocolo, do caixa).

    É o «pelo protocolo» do pedido — decisão do oficial em 15/10/2026: «se o
    protocolo do pedido já traz um item de busca, vale ele». Os itens podem
    vir em pares `(codigo, quantidade)`, como `_itens_para_selar` os dá.
    Com a atribuição, só vale a busca do grupo dela.
    """
    grupo = GRUPO_DA_BUSCA.get(atribuicao_canonica(atribuicao)) if atribuicao \
        else None
    for item in itens or ():
        c = item[0] if isinstance(item, (tuple, list)) else item
        if e_item_de_busca(c) and (
                grupo is None or str(c).strip().startswith(grupo + ".")):
            return str(c).strip()
    return None


def busca_do_protocolo(con, numero: Any, atribuicao: Any) -> str | None:
    """O item de busca que o protocolo do caixa já traz, pelo NÚMERO. Só LÊ.

    Na certidão do RI o protocolo é campo de texto (o número do caixa, ou o
    da prenotação); procura-se o protocolo do caixa com esse número e, nele,
    um item de busca ainda não usado por outro ato.
    """
    texto = str(numero or "").strip()
    if not texto:
        return None
    linhas = con.execute(
        """SELECT a.codigo_ato FROM cx_protocolo_atos a
             JOIN cx_protocolos p ON p.id = a.protocolo_id
            WHERE p.numero = ? AND a.usado_em IS NULL
              AND a.codigo_ato IS NOT NULL""", (texto,)).fetchall()
    return busca_entre([r[0] for r in linhas], atribuicao)


def codigos_dos_servicos(con, servicos: Any) -> list[str]:
    """Os códigos do Tribunal dos serviços marcados no caixa. Só LÊ."""
    numeros = [int(s) for s in (servicos or ()) if str(s).strip().isdigit()]
    if not numeros:
        return []
    lugares = ",".join("?" * len(numeros))
    return [str(r[0]) for r in con.execute(
        f"""SELECT codigo_tj FROM cx_servicos WHERE codigo IN ({lugares})
              AND codigo_tj IS NOT NULL""", numeros).fetchall()]


def servico_da_busca(con, codigo: Any) -> int | None:
    """O serviço do caixa daquele item de busca, o que TEM preço. Só LÊ.

    **O MESMO CÓDIGO DO TRIBUNAL PODE ESTAR EM MAIS DE UM SERVIÇO** (medido
    em 21/09/2026: 273 códigos repetidos), e só um tem preço na vigência —
    a régua de `emolumentos.buscar`. Pegar o primeiro poria no recibo um
    serviço sem valor.
    """
    linha = con.execute(
        """SELECT s.codigo FROM cx_servicos s
             LEFT JOIN cx_servico_valores v
                    ON v.servico = s.codigo
                   AND v.vigencia = (SELECT codigo FROM cx_vigencias
                                      WHERE vigente = 1)
            WHERE s.codigo_tj = ?
            ORDER BY (v.total IS NULL), s.ativo DESC, s.codigo
            LIMIT 1""", (str(codigo or "").strip(),)).fetchone()
    return int(linha[0]) if linha else None


def _data(valor: Any) -> date | None:
    """Lê `2020-01-20`, `2026-10-13T12:52:05` ou `20/01/2020`. Só calcula."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor or "").strip()
    if not texto:
        return None
    for formato, tamanho in (("%Y-%m-%d", 10), ("%d/%m/%Y", 10)):
        try:
            return datetime.strptime(texto[:tamanho], formato).date()
        except ValueError:
            continue
    return None


def _mais_anos(d: date, anos: int) -> date:
    """`d` mais `anos` anos; 29/02 cai em 28/02 no ano que não tem."""
    try:
        return d.replace(year=d.year + anos)
    except ValueError:
        return d.replace(year=d.year + anos, day=28)


def _faixa(atribuicao: str, cabe) -> str:
    """O primeiro item cuja faixa `cabe(anos)` — ou o «acima de cinquenta»."""
    canonica = _grupo(atribuicao)
    grupo = GRUPO_DA_BUSCA[canonica]
    revogadas = FAIXAS_REVOGADAS.get(canonica, frozenset())
    for anos, sufixo, _rotulo in FAIXAS:
        if sufixo in revogadas:
            continue
        if anos is None or cabe(anos):
            return f"{grupo}.{sufixo}"
    return f"{grupo}.8"


def item_de_busca(atribuicao: Any, data_do_ato: Any,
                  data_emissao: Any) -> str | None:
    """O item de busca pelo tempo entre o ato e a emissão. Só calcula.

    «ATÉ N ANOS» INCLUI O DIA EM QUE COMPLETA: o ato de 15/10/2024 emitido em
    15/10/2026 ainda está «até dois anos»; no dia seguinte já não está.

    **DEVOLVE None QUANDO NÃO HÁ DE ONDE CONTAR** — data do ato vazia, que não
    se lê, ou DEPOIS da emissão (medido na produção: há matrícula aberta em
    «2207-10-26»). None quer dizer «quem emite escolhe»; adivinhar uma faixa
    aqui cobraria do cliente um tempo que ninguém mediu.
    """
    inicio = _data(data_do_ato)
    fim = _data(data_emissao)
    if inicio is None or fim is None or inicio > fim:
        return None
    return _faixa(str(atribuicao), lambda anos: fim <= _mais_anos(inicio, anos))


def item_do_periodo(atribuicao: Any, anos: Any) -> str | None:
    """O item de busca pelo PERÍODO pesquisado — o caso do Protesto.

    A certidão do Protesto pergunta quantos anos se pesquisa (cinco, por
    padrão), e é esse o tempo da busca: cinco anos dão 17.6.2 — a faixa de
    47 dos 51 selos de busca do Protesto no acervo.
    """
    try:
        n = int(anos)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return _faixa(str(atribuicao), lambda limite: n <= limite)


def rotulo(codigo: Any) -> str:
    """«16.25.4 — Até quinze anos». Só calcula."""
    texto = str(codigo or "").strip()
    for canonica, grupo in GRUPO_DA_BUSCA.items():
        if texto.startswith(grupo + "."):
            for o in opcoes(canonica):
                if o["codigo"] == texto:
                    return f"{texto} — {o['rotulo']}"
    return texto


def item_sem_cobranca(atribuicao: Any) -> str:
    """O «.9» daquela atribuição. Só calcula."""
    return f"{GRUPO_DA_BUSCA[_grupo(atribuicao)]}.{SUFIXO_SEM_COBRANCA}"


def para_a_tela(atribuicao: Any, data_do_ato: Any = None,
                data_emissao: Any = None, anos: Any = None,
                identificado: Any = None) -> dict:
    """O que o campo da busca precisa para se desenhar. Só calcula.

    `sugerido` vem pré-selecionado; sem ele a tela abre em «escolha» e a
    emissão recusa até alguém escolher.

    **QUANDO O PEDIDO IDENTIFICA O ATO, O «.9» VEM MARCADO** — decisão do
    oficial em 15/10/2026: certidão do RI pelo número da matrícula ou de
    ordem, 2ª via do RCPN pelo livro, folha e termo, Notas pelo livro e
    folha, Protesto com a data do ato informada. `identificado` é a frase que
    diz POR QUE, e ela aparece na tela: o balcão troca se o pedido não foi
    assim. A faixa de tempo só vem sugerida na busca por nome, ou quando não
    há dado do ato.
    """
    canonica = _grupo(atribuicao)
    emissao = _data(data_emissao) or date.today()
    if str(identificado or "").strip():
        return {"atribuicao": canonica, "opcoes": opcoes(canonica),
                "sugerido": item_sem_cobranca(canonica),
                "de_onde": str(identificado).strip(), "identificado": True}
    if anos is not None:
        sugerido = item_do_periodo(canonica, anos)
        de_onde = (f"pelo período pesquisado ({anos} anos)"
                   if sugerido else "")
    else:
        sugerido = item_de_busca(canonica, data_do_ato, emissao)
        inicio = _data(data_do_ato)
        de_onde = (f"pela data do ato ({inicio.strftime('%d/%m/%Y')}) até a "
                   f"emissão" if sugerido and inicio else "")
    return {"atribuicao": canonica, "opcoes": opcoes(canonica),
            "sugerido": sugerido, "de_onde": de_onde, "identificado": False}


def escolher(atribuicao: Any, escolhido: Any) -> str:
    """Confere o item que a tela mandou. Só calcula; recusa o que não serve.

    **VAZIO SE RECUSA**: a tela vem com a sugestão marcada, e chegar vazio é
    alguém ter aberto em «escolha» — sem data do ato — e não ter escolhido.
    """
    canonica = _grupo(atribuicao)
    texto = str(escolhido or "").strip()
    if not texto:
        raise BuscaError(
            "Escolha o item da busca antes de emitir a certidão. Sem a data "
            "do ato o sistema não sabe o tempo da busca — escolha a faixa, "
            "ou o «.9» se o ato foi indicado por data ou por livro e número.")
    if texto not in codigos(canonica):
        raise BuscaError(
            f"O item {texto} não é busca desta atribuição. Escolha uma das "
            f"faixas da lista.")
    return texto


def envelope_da_busca(*, codigo: Any, escrevente: Any, versao_tabela: Any,
                      nome: Any = None, documento: Any = None,
                      isento: bool = False, motivo_isencao: Any = None) -> dict:
    """O corpo do pedido de `…/atos-em-geral` para a busca. Só calcula.

    **MEDIDO NOS 78 ENVELOPES de busca do RI e do Protesto que saíram por
    `atos-em-geral`** (2022 a 2026): `ato{codigo, codigoTabelaCusta}`,
    `escrevente`, `partes{nomePartes: [], parteAto: [{documento, nome}]}` e
    `quantidade` 1 — sempre 1: a busca é uma por certidão. O documento vai
    com onze zeros quando não há (é o que a casa mandou nos envelopes sem
    CPF da parte).

    A ISENÇÃO SEGUE A DA CERTIDÃO, e vai na forma `DadosIsento` do contrato
    (`isento{value, motivo}`) — a mesma do arquivamento do RI, que também é
    `AtosEmGeral`. Motivo em branco se recusa antes da rede.
    """
    item = str(codigo or "").strip()
    if not vira_selo(item):
        raise BuscaError(f"O item {item or '(vazio)'} não gera selo de busca.")
    faltando = [o for o, v in (("o escrevente", escrevente),
                               ("a versão da tabela de custas", versao_tabela))
                if not str(v or "").strip()]
    if faltando:
        raise BuscaError(
            f"O selo da busca não sai sem {', '.join(faltando)}.")
    if isento and not str(motivo_isencao or "").strip():
        raise BuscaError(
            "Busca isenta precisa do motivo escrito — é o mesmo da certidão.")
    doc = "".join(c for c in str(documento or "") if c.isdigit())
    envelope: dict[str, Any] = {
        "ato": {"codigo": item,
                "codigoTabelaCusta": str(versao_tabela).strip()},
        "escrevente": str(escrevente).strip(),
        "partes": {"nomePartes": [],
                   "parteAto": [{"documento": doc or "00000000000",
                                 "nome": str(nome or "").strip()}]},
        "quantidade": 1,
    }
    if isento:
        envelope["isento"] = {"value": True,
                              "motivo": str(motivo_isencao).strip().upper()}
    return envelope
