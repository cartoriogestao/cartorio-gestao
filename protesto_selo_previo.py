"""O selo do Protesto conferido ANTES de lavrar, as obrigações que ele deixa,
e a situação que pede um ato.

Ordem do oficial, 29/10/2026: «trabalhamos com mao de obra muito propensa a
erros e precisamos revisar os processos para nao permitir que a mao de obra
erre. vincular cada obrigacao a uma conduta [...]. se insistir em algo que eh
erro, precisa afirmar expressamente e deixar log.» E, na revisão do mesmo dia:
«precisamos evitar erros e garantir que todos os processos sejam concluídos
todos os dias; não deixar margem para a escrevente esquecer ou fazer errado».

**O SELO SÓ SE DESCOBRIA DEPOIS.** A rota que lança o ato na ficha do título
lavrava primeiro e pedia o selo depois; quando o selo não saía, o ato era
desfeito (`cancelado=1`), com o título voltando à situação de antes. Medido na
produção em 29/10/2026, só leitura: **cinco atos desfeitos por «Selo não
emitido»** — quatro cancelamentos (28 e 29/10) e um pagamento (21/10). Quatro
por **nenhum item marcado**; o quinto, o 4127 (título 1353, 08h43), porque os
itens do protocolo eram **17.1.7 e 17.4.5** — faixas de preço que o aparelho
não conhece («Não foi encontrado um ato para o código informado»). O 9614
ficou PAGO sem pagamento válido e ninguém percebeu em 8 dias; o 1353 precisou
de 4 tentativas.

**TUDO O QUE SE SABE ANTES, SE CONFERE ANTES** (`conferir_antes_de_lavrar`),
depois das regras do domínio e antes de cobrar e de selar. A recusa desfaz a
transação inteira — o ato não chega a existir — e diz o que fazer:

  - **o caminho do selo e a data da tabela de custas** — sem eles o envelope
    não se monta;
  - **o protocolo do título** — o envelope do Protesto o exige, e ele nasce no
    apontamento;
  - **o item** — marcado para cobrança, ou do protocolo do balcão;
  - **o caixa aberto**, quando o item vai ser cobrado nele;
  - **o item serve para este ato** — o código tem de ser um dos que já saíram
    em selo por aquele caminho: os da receita medida nos 24.849 selos do
    E-Ofício (`atribuicoes.ITENS_DE_CUSTA_POR_CAMINHO`) e os que o aparelho
    já aceitou neste sistema (`sd_selos`). **A receita sozinha não basta, e
    isto é medido**: o 4106 (28/10) saiu com 17.7, 17.9 e 17.10.1 pelo caminho
    do cancelamento, e nenhum dos três está na receita dele. Por isso esta é a
    única trava que se vence com **afirmação expressa** — o código novo que
    serve de verdade passa, fica gravado, e entra na lista no dia em que o
    aparelho o aceitar;
  - **o item do protocolo está pago** — a trava do selo pago (3.7.0) recusa
    item não quitado sem depósito prévio que o cubra.

**A FAIXA DE PREÇO NÃO É O ITEM DO SELO.** O aparelho conhece o 17.4 e o 17.1
(o E-Ofício mandou 17.4 em 190 selos de pagamento e retirada, e 17.1 em 70 de
protesto, com o valor do título no envelope); o caixa cobra pela faixa (17.4.5,
17.1.7). `codigo_para_o_selo` manda o item do Tribunal quando a faixa é de um
item que o caminho conhece — a mesma regra do RI para o 16.45
(`caixa_protocolo.subitem_da_faixa`). Sem isso, todo pagamento pago por
protocolo com a faixa do 17.4 seria recusado, e a recusa não teria saída.

**A FALHA QUE SÓ O APARELHO CONHECE VIRA OBRIGAÇÃO** (`pendencias_do_selo`):
rede, recusa do Tribunal. O ato desfeito por selo é uma pendência «ato a
refazer» até haver um ato válido do mesmo tipo, lançado depois, no mesmo
título — e some sozinha, porque é calculada. Junto vão os atos do robô que
ficaram sem selo.

**E O ITEM PAGO QUE FICOU SEM SELO TAMBÉM É OBRIGAÇÃO** (30/10/2026): o ato
que ficou de pé com parte dos selos — o 4131, pagamento do 9614, com sete selos
e o do 17.4.5 recusado — tem o item pago no protocolo e nenhum selo para ele. A
conta é de `protesto_selo_que_faltou`, e a saída é a ação «Emitir o selo que
faltou», na ficha, do oficial em pessoa.

**E O TÍTULO NUNCA FICA NUMA SITUAÇÃO SEM O ATO QUE A SUSTENTE.**
`titulos_sem_ato_que_sustente` é a conferência. A saída é a fila de correções de
ofício (`correcoes_de_oficio`, tipo `PT_SITUACAO_SUSTENTADA`), por decisão do
oficial em 30/10/2026: o botão da ficha só PROPÕE, e quem aprova é o ADMIN em
pessoa. A correção direta, que também abria para o gerente, foi apagada. Nada se
corrige sozinho. Medido em 29/10/2026: cinco títulos PAGO sem pagamento válido
— o 9614 (pagamento desfeito pelo selo) e quatro que vieram assim da carga.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Iterable

import afirmacoes_expressas as AFX
import ato_selado as AS
import atribuicoes as ATR
from bd_nativo import banco


# OS ATOS DA FICHA QUE NÃO PEDEM SELO PRÓPRIO — a lista que a rota lê para
# decidir se pede o selo depois de lavrar, e esta conferência para decidir se
# confere antes. UMA LISTA SÓ: se as duas divergissem, a tela recusaria um ato
# que nunca pediria selo, ou deixaria passar um que vai ser desfeito.
#
# As ordens judiciais não são ato da serventia (cumprimento de ordem de fora);
# o apontamento não sela desde 21/10/2026 — dos 1.409 do E-Ofício, 1.161 não
# têm selo, e os 248 que têm trazem o do ato POSTERIOR.
#
# A AVERBAÇÃO DE RETIFICAÇÃO DE OFÍCIO (29/10/2026, Lei 9.492/1997, art. 25)
# também não sela: sem precedente de selo no E-Ofício (o «Retifica protesto»,
# rotina 82, nunca selou) e sem caminho de averbação no aparelho do Protesto.
# Se o oficial decidir que há selo, ela sai desta lista por decisão dele.
ATOS_SEM_SELO_PROPRIO = frozenset({
    "SUSTACAO", "REVOGACAO_SUSTACAO", "EFEITO_SUSPENSIVO",
    "REVOGACAO_EFEITO_SUSPENSIVO", "APONTAMENTO", "AVERBACAO_RETIFICACAO",
})

# O nome do ato na frase do balcão. O que não está aqui sai como «o ato».
O_ATO = {
    "INTIMACAO": "a intimação",
    "PROTESTO": "o protesto",
    "PAGAMENTO": "o pagamento",
    "DESISTENCIA": "a desistência",
    "RETIRADA": "a retirada",
    "CANCELAMENTO": "o cancelamento",
    "DEVOLUCAO": "a devolução",
}

# O MOTIVO QUE A ROTA GRAVA NO ATO DESFEITO PELO SELO. É por ele que a
# pendência «ato a refazer» se acha — escrito num lugar só, para a rota que
# grava e a conferência que lê não divergirem.
PREFIXO_DO_DESFEITO = "Selo não emitido"

# AS REGRAS — o nome curto de cada trava, o mesmo que vai em `regra` na
# afirmação expressa e que a tela das afirmações filtra.
REGRA_SEM_CAMINHO = "SELO_SEM_CAMINHO"
REGRA_SEM_DATA_DA_TABELA = "SELO_SEM_DATA_DA_TABELA"
REGRA_SEM_PROTOCOLO_DO_TITULO = "SELO_SEM_PROTOCOLO_DO_TITULO"
REGRA_SEM_ITEM = "SELO_SEM_ITEM"
REGRA_CAIXA_FECHADO = "SELO_CAIXA_FECHADO"
REGRA_ITEM_FORA_DO_CAMINHO = "SELO_ITEM_FORA_DO_CAMINHO"
REGRA_ITEM_NAO_PAGO = "SELO_ITEM_NAO_PAGO"

# O CONTRATO COMUM DA AFIRMAÇÃO EXPRESSA (29/10/2026): caixa `afirmo` + texto
# `afirmacao` com pelo menos 30 letras, auditoria `AFIRMACAO_EXPRESSA` com
# `regra`, `afirmacao` e `o_que_faltava`, e o texto no `detalhe_json` do ato —
# na mesma chave que os outros módulos do Protesto usam.
ACAO_DA_AFIRMACAO = "AFIRMACAO_EXPRESSA"
# O piso e a frase moram em `afirmacoes_expressas` (integração de 29/10/2026).
MINIMO_DE_LETRAS_DA_AFIRMACAO = AFX.MINIMO_DE_LETRAS
MODELO_DA_AFIRMACAO = AFX.MODELO + "…"
CHAVE_NO_DETALHE = "afirmacoes_expressas"


class SeloNaoVaiSairError(AS.AtoError):
    """O selo não vai poder sair, e isso se sabe antes. Frase pronta.

    **É `AtoError`** de propósito: as rotas do Protesto já tratam essa família
    como recusa de regra (`flash` e volta). A ficha do título a apanha antes,
    para devolver o formulário preenchido.

    `regra` é o nome curto da trava; `vencivel` diz se a afirmação expressa a
    vence (só o item fora do caminho); `o_que_faltava` é o que vai na
    afirmação, se houver.
    """

    def __init__(self, texto: str, *, regra: str, vencivel: bool = False,
                 o_que_faltava: str = ""):
        super().__init__(texto)
        self.regra = regra
        self.vencivel = bool(vencivel)
        self.o_que_faltava = o_que_faltava or texto


class SeloSemItemError(SeloNaoVaiSairError):
    """Não há item nenhum para o selo."""


class SituacaoError(ValueError):
    """Impedimento da correção de ofício, com frase pronta para a tela."""


def pede_selo_agora(tipo: Any, *, tabela: str = "pt_atos",
                    selo_digitado: bool = False,
                    selo_automatico: bool = True) -> bool:
    """Este lançamento vai pedir selo ao aparelho logo depois de lavrado? Só
    calcula.

    É o espelho da condição da rota: o selo digitado à mão dispensa o pedido;
    o robô não pede selo (`selo_robo.pode_selar_automatico`) e o ato dele fica
    pendente; e os atos de `ATOS_SEM_SELO_PROPRIO` não selam. A certidão sela
    sempre.
    """
    if selo_digitado or not selo_automatico:
        return False
    if str(tabela or "") == "pt_certidoes":
        return True
    return str(tipo or "").strip().upper() not in ATOS_SEM_SELO_PROPRIO


def codigo_para_o_selo(codigo: Any, caminho: Any) -> str:
    """O código que vai no envelope: o item do Tribunal, e não a faixa. Só
    calcula.

    A faixa (17.4.5) vira o item (17.4) quando o item é de faixa
    (`caixa_protocolo.CODIGOS_TJ_DE_FAIXA`) E o caminho do selo o conhece pela
    receita medida. Fora disso o código vai como está — e a conferência diz se
    ele serve.
    """
    import caixa_protocolo as CXP
    cod = str(codigo or "").strip()
    pai = CXP.subitem_da_faixa(cod)
    if pai and pai in ATR.itens_de_custa_do_ato(caminho):
        return pai
    return cod


def validar_afirmacao(afirmo: Any, afirmacao: Any, *,
                      robo: bool = False) -> str | None:
    """O texto da afirmação expressa, se ela cumpre o contrato; None se não
    veio nenhuma. Só calcula. Recusa a afirmação pela metade, e a de robô.

    A RÉGUA É A DO CONTRATO (`afirmacoes_expressas.validar`) desde a
    integração de 29/10/2026: pelo menos 30 LETRAS ALÉM da frase de abertura.
    A cópia que morava aqui contava a frase — e ela sozinha tem 33 letras.
    """
    texto = " ".join(str(afirmacao or "").split())
    if not afirmo and not texto:
        return None
    try:
        return AFX.validar(afirmo, texto, robo=robo)
    except AFX.AfirmacaoError as erro:
        raise SituacaoError(
            f"A afirmação expressa está incompleta. {erro}") from None


def _servem_ao_caminho(con, caminho: str, tabela: str) -> list[str]:
    """Os códigos que já saíram em selo por este caminho. Só LÊ.

    A receita medida nos selos do E-Ofício, mais o que o aparelho aceitou
    neste sistema — a referência do selo é `tabela:ato:código:unidade`.
    """
    servem = list(ATR.itens_de_custa_do_ato(caminho))
    if con is None:
        return servem
    bd = banco(con)
    if not bd.tem_tabela("sd_selos"):
        return servem
    for r in bd.ler(
            """SELECT referencia FROM sd_selos
                WHERE caminho = %s AND tabela = %s
                  AND referencia IS NOT NULL AND cancelado_em IS NULL""",
            (str(caminho), str(tabela))):
        partes = str(r["referencia"] or "").split(":")
        if len(partes) >= 3 and partes[2].strip() and partes[2] not in servem:
            servem.append(partes[2].strip())
    return servem


def _nao_pagos(con, codigos: Iterable[str], *, tabela: str,
               protocolo_id: int) -> list[str]:
    """Os códigos que o protocolo escolhido não paga. Só LÊ.

    O ESPELHO, SEM ESCREVER, DA TRAVA DO SELO PAGO (`ato_selado.cobrir_o_selo`,
    passo do protocolo): o item do mesmo código (a faixa conta, pela regra de
    `caixa_protocolo.itens_para_o_selo`), com saldo, que não seja gratuito e
    esteja quitado — ou diferido por lei, no Protesto — ou que um depósito
    prévio do protocolo cubra. Na dúvida, não recusa: o selo confere de novo
    depois, e desfaz se for o caso.
    """
    import caixa_depositos as DEP
    import caixa_protocolo as CXP
    from caixa_schema import centavos
    faltam, depositos = [], None
    for codigo in sorted(set(codigos)):
        cobre = False
        for it in CXP.itens_para_o_selo(con, protocolo_id, codigo):
            if CXP.item_gratuito(it, con):
                continue
            if CXP.item_pago(it) or (tabela in CXP.TABELAS_QUE_DIFEREM
                                     and CXP.item_diferido(it)):
                cobre = True
                break
            valor = centavos(it.get("valor_total"))
            if valor > 0:
                if depositos is None:
                    depositos = DEP.do_protocolo(con, protocolo_id, tabela=tabela)
                if any(centavos(d["saldo"]) >= valor for d in depositos):
                    cobre = True
                    break
        if not cobre:
            faltam.append(codigo)
    return faltam


def _numero_do_protocolo(con, protocolo_id: int) -> str:
    linha = banco(con).um("SELECT numero FROM cx_protocolos WHERE id = %s",
                          (int(protocolo_id),))
    return str((linha or {}).get("numero") or protocolo_id)


def conferir_antes_de_lavrar(tipo: Any,
                             itens: Iterable[str] | Callable[[], Iterable[str]],
                             *, tabela: str = "pt_atos",
                             selo_digitado: bool = False,
                             selo_automatico: bool = True,
                             protocolo_escolhido: bool = False,
                             con: Any = None,
                             titulo: dict | None = None,
                             data_da_tabela: Any = None,
                             protocolo_id: int | None = None,
                             vai_cobrar_no_caixa: bool = False,
                             caixa_aberto: bool | None = None,
                             lancamento_com_protocolo: bool = False,
                             afirmo: Any = False,
                             afirmacao: Any = "",
                             robo: bool = False) -> dict | None:
    """Recusa, ANTES de o ato existir, o lançamento cujo selo não vai sair.
    Só LÊ.

    `itens` são os códigos que o selo usaria — a rota os tira da mesma função
    que o selo lê —, ou uma função que os devolva: só se pergunta quando o
    lançamento vai mesmo pedir selo. Os outros parâmetros ligam as conferências
    que precisam deles; o que não veio não se confere (`None` em
    `data_da_tabela` e em `caixa_aberto`, sem `titulo`, sem `protocolo_id`).

    Recusa com `SeloNaoVaiSairError`, dizendo o que fazer. Devolve a afirmação
    aceita (`{regra, afirmacao, o_que_faltava}`) quando a escrevente venceu a
    trava do item fora do caminho, para a rota gravar no ato e na auditoria;
    None nos outros casos.
    """
    if not pede_selo_agora(tipo, tabela=tabela, selo_digitado=selo_digitado,
                           selo_automatico=selo_automatico):
        return None
    certidao = str(tabela or "") == "pt_certidoes"
    caminho = AS.caminho_do_ato(tabela, tipo)
    if not caminho:
        raise SeloNaoVaiSairError(_frase(
            tipo, tabela, f"não há caminho de selo medido para {_o_ato(tipo, tabela)}",
            "Fale com o oficial: este ato não tem por onde selar."),
            regra=REGRA_SEM_CAMINHO)
    if data_da_tabela is not None and \
            AS.versao_da_tabela_de_custas(caminho, data_da_tabela) is None:
        raise SeloNaoVaiSairError(_frase(
            tipo, tabela, "a data da tabela de custas não está configurada",
            "Peça ao oficial para informá-la em Administrativo → Selador."),
            regra=REGRA_SEM_DATA_DA_TABELA)
    if titulo is not None and not certidao and \
            not str(titulo.get("protocolo") or "").strip():
        raise SeloNaoVaiSairError(_frase(
            tipo, tabela, "o título ainda não tem número de protocolo, e o "
            "envelope do selo do Protesto o exige",
            "O protocolo nasce no apontamento: aponte o título antes."),
            regra=REGRA_SEM_PROTOCOLO_DO_TITULO)
    lista = list(itens() if callable(itens) else (itens or ()))
    if not lista:
        if protocolo_escolhido:
            falta = ("não tem item marcado para cobrança, e o protocolo "
                     "escolhido não tem item livre — os itens dele já foram "
                     "usados por outro ato, ou ele não tem item da tabela")
        else:
            falta = ("não tem item marcado para cobrança nem protocolo do "
                     "balcão com item")
        raise SeloSemItemError(_frase(
            tipo, tabela, f"{_o_ato(tipo, tabela)} sela pelos itens da tabela de "
            f"emolumentos, e {'este pedido' if certidao else 'este lançamento'} "
            f"{falta}", _o_que_fazer(tabela)), regra=REGRA_SEM_ITEM)
    if vai_cobrar_no_caixa and caixa_aberto is False:
        raise SeloNaoVaiSairError(
            ("Você não tem caixa aberto, e o item marcado vai ser cobrado nele — "
             "sem caixa, o lançamento não aparece na conferência do dia. "
             f"{'A certidão NÃO foi emitida' if certidao else 'O ato NÃO foi lançado'}"
             ", e nada foi gravado. Abra o caixa em Administrativo → Caixa e "
             "lance de novo — ou lance sem marcar cobrança, e cobre depois."),
            regra=REGRA_CAIXA_FECHADO)
    aceita = None
    servem = _servem_ao_caminho(con, caminho, tabela)
    fora = sorted({c for c in lista if c not in servem})
    if fora:
        o_que = (f"{'o item ' if len(fora) == 1 else 'os itens '}"
                 f"{', '.join(fora)} não {'saiu' if len(fora) == 1 else 'saíram'} "
                 f"em selo por este caminho ({caminho}); os que servem: "
                 f"{', '.join(servem) or 'nenhum medido'}")
        try:
            texto = validar_afirmacao(afirmo, afirmacao, robo=robo)
        except SituacaoError as metade:
            # A AFIRMAÇÃO PELA METADE CONTINUA SENDO A MESMA TRAVA: a tela
            # devolve o formulário com a caixa, e não uma página de erro.
            raise SeloNaoVaiSairError(
                _frase(tipo, tabela, o_que, str(metade)),
                regra=REGRA_ITEM_FORA_DO_CAMINHO, vencivel=True,
                o_que_faltava=o_que) from metade
        if texto is None:
            raise SeloNaoVaiSairError(_frase(
                tipo, tabela, o_que,
                "Escolha o protocolo com o item certo, corrija os itens do "
                "protocolo no caixa, ou marque o item certo em «Cobrar no "
                "caixa». Se o item serve mesmo para este ato, marque «Afirmo» e "
                f"escreva por quê (pelo menos {MINIMO_DE_LETRAS_DA_AFIRMACAO} "
                f"letras, começando por «{MODELO_DA_AFIRMACAO}»)."),
                regra=REGRA_ITEM_FORA_DO_CAMINHO, vencivel=True, o_que_faltava=o_que)
        aceita = {"regra": REGRA_ITEM_FORA_DO_CAMINHO, "afirmacao": texto,
                  "o_que_faltava": o_que}
    if con is not None and protocolo_id is not None and \
            not lancamento_com_protocolo and AS.trava_ligada(con):
        faltam = _nao_pagos(con, lista, tabela=tabela, protocolo_id=protocolo_id)
        if faltam:
            raise SeloNaoVaiSairError(_frase(
                tipo, tabela, "o selo pago só sai com o item pago, e no "
                f"protocolo {_numero_do_protocolo(con, protocolo_id)} "
                f"{'o item' if len(faltam) == 1 else 'os itens'} "
                f"{', '.join(faltam)} não "
                f"{'está quitado' if len(faltam) == 1 else 'estão quitados'}, "
                "nem há depósito prévio que os cubra",
                "Quite no caixa (ou receba o depósito prévio) e lance de novo."),
                regra=REGRA_ITEM_NAO_PAGO)
    return aceita


def _o_ato(tipo: Any, tabela: str) -> str:
    if str(tabela or "") == "pt_certidoes":
        return "a certidão"
    return O_ATO.get(str(tipo or "").strip().upper(), "o ato")


def _o_que_fazer(tabela: str) -> str:
    if str(tabela or "") == "pt_certidoes":
        return ("Marque o item da certidão em «Cobrar no caixa» (com o seu caixa "
                "aberto) ou escolha o protocolo do atendimento, e emita de novo.")
    return ("Marque o item em «Cobrar no caixa» (com o seu caixa aberto) ou "
            "escolha o protocolo do atendimento, e lance de novo — o que você "
            "digitou continua no formulário.")


def _frase(tipo: Any, tabela: str, por_que: str, o_que_fazer: str) -> str:
    """A frase do balcão: o que aconteceu, que nada foi gravado, e o que
    fazer. Só calcula."""
    if str(tabela or "") == "pt_certidoes":
        return f"Certidão NÃO emitida, e nada foi gravado: {por_que}. {o_que_fazer}"
    return f"Ato NÃO lançado, e nada foi gravado: {por_que}. {o_que_fazer}"


def anotar_afirmacao_no_ato(con, ato_id: int, afirmacao: dict, *,
                            quem: str = "", agora: str = "") -> None:
    """Acrescenta a afirmação expressa ao `detalhe_json` do ato. ESCREVE.

    DENTRO da transação que lavrou o ato: ato sem a afirmação que o permitiu é
    ato que ninguém explica depois. A chave é a dos outros módulos do Protesto.
    """
    bd = banco(con)
    linha = bd.um("SELECT detalhe_json FROM pt_atos WHERE id = %s", (int(ato_id),))
    try:
        detalhe = json.loads((linha or {}).get("detalhe_json") or "{}")
    except ValueError:
        detalhe = {}
    if not isinstance(detalhe, dict):
        detalhe = {}
    lista = detalhe.get(CHAVE_NO_DETALHE)
    if not isinstance(lista, list):
        lista = []
    lista.append({"regra": afirmacao.get("regra"),
                  "afirmacao": afirmacao.get("afirmacao"),
                  "o_que_faltava": afirmacao.get("o_que_faltava"),
                  "por": quem or None, "em": agora or None})
    detalhe[CHAVE_NO_DETALHE] = lista
    bd.escrever("UPDATE pt_atos SET detalhe_json = %s WHERE id = %s",
                (json.dumps(detalhe, ensure_ascii=False), int(ato_id)))


# ================================================ as obrigações que o selo deixa
#
# «FALHA DO APARELHO DEPOIS DE LAVRAR VIRA OBRIGAÇÃO, E NÃO ESQUECIMENTO» — a
# revisão do oficial, 29/10/2026. O ato desfeito pelo selo já guarda tudo o que
# a pendência precisa dizer: o título, o tipo, quando, o motivo e quem tentou
# (`criado_por`). A pendência é CALCULADA dele, e não gravada à parte: some
# sozinha quando um ato válido do mesmo tipo é lançado depois no mesmo título,
# e não há segunda versão do fato para divergir.

ESPECIE_REFAZER = "REFAZER"
ESPECIE_SELAR = "SELAR"
# O item pago no protocolo cujo selo não saiu, num ato que ficou de pé
# (30/10/2026) — `protesto_selo_que_faltou`.
ESPECIE_ITEM_SEM_SELO = "ITEM_SEM_SELO"

# Os atos da ficha que selam — os de `ATOS_SEM_SELO_PROPRIO` ficam de fora.
TIPOS_QUE_SELAM = ("INTIMACAO", "PROTESTO", "PAGAMENTO", "DESISTENCIA",
                   "RETIRADA", "CANCELAMENTO")


def _robos(bd) -> set[str]:
    """Os nomes e logins das contas de robô. Só LÊ."""
    if not bd.tem_tabela("users") or not bd.tem_coluna("users", "eh_robo"):
        return set()
    nomes: set[str] = set()
    for u in bd.ler("SELECT full_name, username FROM users "
                    "WHERE COALESCE(eh_robo, 0) = 1"):
        nomes |= {str(u.get("full_name") or "").strip(),
                  str(u.get("username") or "").strip()}
    return {n for n in nomes if n}


def _e_robo(quem: Any, robos: set[str]) -> bool:
    import nome_humano as NOMEHUM
    nome = str(quem or "").strip()
    # NOME VAZIO NÃO É ROBÔ AQUI: `eh_rotulo_de_maquina("")` diz que sim, e o
    # ato lavrado sem nome gravado viraria «do robô» sem ninguém saber.
    return bool(nome) and (nome in robos or NOMEHUM.eh_rotulo_de_maquina(nome))


def pendencias_do_selo(con, *, titulo_id: int | None = None,
                       limite: int = 200) -> list[dict]:
    """As obrigações que o selo deixou no Protesto. Só LÊ.

    `REFAZER`: o ato desfeito porque o selo não saiu (rede, recusa do
    aparelho), enquanto não houver ato válido do mesmo tipo lançado DEPOIS no
    mesmo título — uma linha por título e tipo, com a última tentativa e
    quantas foram. `SELAR`: o ato válido que o robô lavrou e ficou sem selo.
    `ITEM_SEM_SELO`: o ato válido com item pago no protocolo e sem o selo
    dele — «falta o selo do item X — emita na ficha» (30/10/2026), uma linha
    por item, com `ato_id` e `item_id` para o botão da ficha.

    É o que o roteiro do dia lê (`protesto_roteiro.GANCHOS`), e o que o painel
    e a ficha mostram. O CONTRATO DO ROTEIRO: cada linha traz `titulo_id`,
    `numero_titulo`, `protocolo` e `explicacao` — a frase pronta, que o
    roteiro mostra como está.
    """
    bd = banco(con)
    filtro, args = "", [f"{PREFIXO_DO_DESFEITO}%"]
    if titulo_id is not None:
        filtro, args = " AND a.titulo_id = %s", args + [int(titulo_id)]
    grupos: dict[tuple[int, str], dict] = {}
    for r in bd.ler(
            f"""SELECT a.id, a.titulo_id, a.tipo, a.criado_em, a.criado_por,
                       a.motivo_cancelamento, t.numero_titulo, t.protocolo
                  FROM pt_atos a
                  JOIN pt_titulos t ON t.id = a.titulo_id
                 WHERE COALESCE(a.cancelado, 0) <> 0
                   AND a.motivo_cancelamento LIKE %s{filtro}
                   AND NOT EXISTS (
                       SELECT 1 FROM pt_atos b
                        WHERE b.titulo_id = a.titulo_id AND b.tipo = a.tipo
                          AND COALESCE(b.cancelado, 0) = 0 AND b.id > a.id)
                 ORDER BY a.id""", args):
        chave = (int(r["titulo_id"]), str(r["tipo"]))
        anterior = grupos.get(chave)
        motivo = str(r["motivo_cancelamento"] or "")
        if motivo.startswith(PREFIXO_DO_DESFEITO):
            motivo = motivo[len(PREFIXO_DO_DESFEITO):].lstrip(" :")
        grupos[chave] = {
            "especie": ESPECIE_REFAZER,
            "titulo_id": int(r["titulo_id"]), "tipo": str(r["tipo"]),
            "numero_titulo": r.get("numero_titulo"),
            "protocolo": r.get("protocolo"),
            "ato": O_ATO.get(str(r["tipo"]), "o ato"),
            "ato_id": int(r["id"]), "quando": str(r["criado_em"] or ""),
            "quando_br": _data_br(r["criado_em"]),
            "motivo": motivo.rstrip(".") or "sem motivo gravado",
            "quem_tentou": str(r["criado_por"] or "") or "não gravado",
            "tentativas": (anterior or {}).get("tentativas", 0) + 1,
        }
    for p in grupos.values():
        p["explicacao"] = (
            f"refazer {p['ato']}: desfeito em {p['quando_br']} porque o selo "
            f"não saiu ({p['motivo']}); tentou: {p['quem_tentou']}"
            + (f", {p['tentativas']} tentativas" if p["tentativas"] > 1 else "")
            + ". Sai da lista quando o ato for lançado de novo.")
    saida = list(grupos.values())
    robos = _robos(bd)
    lugares = ",".join(["%s"] * len(TIPOS_QUE_SELAM))
    sem_selo_ligado = (" AND NOT EXISTS (SELECT 1 FROM sd_selos s WHERE "
                       "s.tabela = 'pt_atos' AND s.ato_id = a.id)"
                       if bd.tem_tabela("sd_selos") else "")
    filtro_t, args_t = "", list(TIPOS_QUE_SELAM)
    if titulo_id is not None:
        filtro_t, args_t = " AND a.titulo_id = %s", args_t + [int(titulo_id)]
    for r in bd.ler(
            f"""SELECT a.id, a.titulo_id, a.tipo, a.criado_em, a.criado_por,
                       t.numero_titulo, t.protocolo
                  FROM pt_atos a
                  JOIN pt_titulos t ON t.id = a.titulo_id
                 WHERE COALESCE(a.cancelado, 0) = 0
                   AND a.tipo IN ({lugares})
                   AND COALESCE(a.origem, '') <> 'EOFICIO'
                   AND (a.selo IS NULL OR a.selo = ''){sem_selo_ligado}{filtro_t}
                 ORDER BY a.id""", args_t):
        if not _e_robo(r["criado_por"], robos):
            continue
        ato = O_ATO.get(str(r["tipo"]), "o ato")
        saida.append({
            "especie": ESPECIE_SELAR,
            "titulo_id": int(r["titulo_id"]), "tipo": str(r["tipo"]),
            "numero_titulo": r.get("numero_titulo"),
            "protocolo": r.get("protocolo"),
            "ato": ato,
            "ato_id": int(r["id"]), "quando": str(r["criado_em"] or ""),
            "quando_br": _data_br(r["criado_em"]),
            "motivo": "lavrado pelo robô, que não pede selo",
            "quem_tentou": str(r["criado_por"] or ""),
            "tentativas": 0,
            "explicacao": (f"selar {ato} (ato {int(r['id'])}, de "
                           f"{_data_br(r['criado_em'])}): lavrado pelo robô, "
                           "que não pede selo — quem sela é o escrevente."),
        })
    # O ITEM PAGO SEM SELO (30/10/2026). A conta mora no módulo da ação, e
    # este só a junta: duas réguas para «falta selo?» divergiriam.
    import protesto_selo_que_faltou as PSF
    saida += PSF.pendencias(con, titulo_id=titulo_id, limite=limite)
    saida.sort(key=lambda p: (p["quando"], p["ato_id"]))
    return saida[:max(1, int(limite))]


# ======================================== a situação que pede um ato válido
#
# CADA SITUAÇÃO DO TÍTULO NASCE DE UM ATO, e é esse ato que a sustenta no
# livro, na certidão e no retorno à CRA. Sem ele, o título afirma um fato que
# o livro não tem: o 9614 está PAGO, e o pagamento dele foi desfeito.
# RECEBIDO não pede ato — é o título antes de qualquer um.
ATO_QUE_SUSTENTA: dict[str, tuple[str, ...]] = {
    "APONTADO": ("APONTAMENTO",),
    "INTIMADO": ("INTIMACAO",),
    "PROTESTADO": ("PROTESTO",),
    "PAGO": ("PAGAMENTO",),
    "DESISTIDO": ("DESISTENCIA", "RETIRADA"),
    "CANCELADO": ("CANCELAMENTO",),
    "DEVOLVIDO": ("DEVOLUCAO",),
}

# A situação que cada ato deixa, e a ordem do caminho. As FINAIS valem pelo
# último ato (o pago depois de protestado e depois cancelado, pela regra
# antiga); as do caminho, pela mais adiantada — a ordem dos ids do acervo não é
# a ordem do livro (o 1353 tem a intimação gravada depois do protesto).
SITUACAO_DO_ATO = {
    "APONTAMENTO": "APONTADO", "INTIMACAO": "INTIMADO",
    "PROTESTO": "PROTESTADO", "PAGAMENTO": "PAGO",
    "DESISTENCIA": "DESISTIDO", "RETIRADA": "DESISTIDO",
    "CANCELAMENTO": "CANCELADO", "DEVOLUCAO": "DEVOLVIDO",
}
ORDEM_DO_CAMINHO = ("RECEBIDO", "APONTADO", "INTIMADO", "PROTESTADO")
SITUACOES_FINAIS = ("PAGO", "DESISTIDO", "CANCELADO", "DEVOLVIDO")

# A CARGA DO E-OFÍCIO marca o título com esta chave de origem
# (`acervo_carga`, `tbAvisoProtesto:<intChave>`). É ela, e não `origem`, que
# diz que a linha veio do acervo: `origem` diz de onde o TÍTULO veio (CRA,
# CENPROT, MANUAL).
PREFIXO_DO_ACERVO = "tbAvisoProtesto:"

# O teto da lista. Alarme que soa sempre é alarme que ninguém ouve, e uma lista
# que não cabe na tela já é outro problema — o número vem junto.
LIMITE_DA_LISTA = 200


def _condicao_do_ato_valido() -> tuple[str, list[str]]:
    """O `OR` que casa a situação com o tipo de ato que a sustenta, e os
    parâmetros dele. Só calcula."""
    partes, params = [], []
    for situacao, tipos in ATO_QUE_SUSTENTA.items():
        lugares = ",".join(["%s"] * len(tipos))
        partes.append(f"(t.situacao = %s AND a.tipo IN ({lugares}))")
        params += [situacao, *tipos]
    return " OR ".join(partes), params


def _achar(con, *, titulo_id: int | None = None,
           limite: int = LIMITE_DA_LISTA) -> list[dict]:
    """Os títulos cuja situação não tem o ato válido. Só LÊ."""
    condicao, params = _condicao_do_ato_valido()
    situacoes = list(ATO_QUE_SUSTENTA)
    lugares = ",".join(["%s"] * len(situacoes))
    filtro_do_titulo = " AND t.id = %s" if titulo_id is not None else ""
    sql = f"""SELECT t.id, t.situacao, t.protocolo, t.numero_titulo,
                     t.origem_chave
                FROM pt_titulos t
               WHERE t.situacao IN ({lugares}){filtro_do_titulo}
                 AND NOT EXISTS (
                     SELECT 1 FROM pt_atos a
                      WHERE a.titulo_id = t.id
                        AND COALESCE(a.cancelado, 0) = 0
                        AND ({condicao}))
               ORDER BY t.id
               LIMIT %s"""
    valores = situacoes + ([int(titulo_id)] if titulo_id is not None else [])
    linhas = banco(con).ler(sql, valores + params + [int(limite)])
    return [_explicar(con, dict(r)) for r in linhas]


def _data_br(texto: Any) -> str:
    bruto = str(texto or "")[:10]
    if len(bruto) == 10 and bruto[4] == "-" and bruto[7] == "-":
        return f"{bruto[8:10]}/{bruto[5:7]}/{bruto[0:4]}"
    return bruto or "data não gravada"


def situacao_sustentada(con, titulo_id: int) -> str:
    """A situação que os atos VÁLIDOS do título sustentam. Só LÊ.

    A final do último ato final, se houver; senão a mais adiantada do caminho;
    sem ato nenhum, RECEBIDO.
    """
    atos = banco(con).ler(
        """SELECT id, tipo FROM pt_atos
            WHERE titulo_id = %s AND COALESCE(cancelado, 0) = 0
            ORDER BY id""", (int(titulo_id),))
    finais = [SITUACAO_DO_ATO[a["tipo"]] for a in atos
              if SITUACAO_DO_ATO.get(a["tipo"]) in SITUACOES_FINAIS]
    if finais:
        return finais[-1]
    alcancadas = {SITUACAO_DO_ATO.get(a["tipo"]) for a in atos}
    for situacao in reversed(ORDEM_DO_CAMINHO):
        if situacao in alcancadas:
            return situacao
    return "RECEBIDO"


def _explicar(con, linha: dict) -> dict:
    """Diz o que se sabe do porquê: o ato foi desfeito, ou o título veio
    assim do acervo, ou não há ato nenhum daquele tipo. E qual situação os
    atos válidos sustentam — o destino da correção de ofício. Só LÊ."""
    tipos = ATO_QUE_SUSTENTA[linha["situacao"]]
    lugares = ",".join(["%s"] * len(tipos))
    desfeito = banco(con).um(
        f"""SELECT id, tipo, criado_em, motivo_cancelamento
              FROM pt_atos
             WHERE titulo_id = %s AND tipo IN ({lugares})
               AND COALESCE(cancelado, 0) <> 0
             ORDER BY id DESC LIMIT 1""",
        [int(linha["id"]), *tipos])
    o_ato = O_ATO.get(tipos[0], "o ato").split(" ", 1)[1]
    if desfeito:
        origem = "DESFEITO"
        motivo = (str(desfeito["motivo_cancelamento"] or "").strip().rstrip(".")
                  or "sem motivo gravado")
        explicacao = (
            f"O ato de {o_ato} lançado em {_data_br(desfeito['criado_em'])} "
            f"(ato {desfeito['id']} do sistema) foi desfeito — {motivo} —, e "
            f"o título continuou {linha['situacao']}.")
    elif str(linha.get("origem_chave") or "").startswith(PREFIXO_DO_ACERVO):
        origem = "ACERVO"
        explicacao = (f"Veio assim da carga do E-Ofício: a situação "
                      f"{linha['situacao']} entrou sem o ato de {o_ato}.")
    else:
        origem = "SEM_ATO"
        explicacao = (f"Não há ato de {o_ato} neste título — nem válido, nem "
                      "desfeito.")
    return {
        "titulo_id": int(linha["id"]),
        "situacao": linha["situacao"],
        "protocolo": linha.get("protocolo"),
        "numero_titulo": linha.get("numero_titulo"),
        "ato_esperado": o_ato,
        "tipos": tipos,
        "origem": origem,
        "desfeito_id": int(desfeito["id"]) if desfeito else None,
        "explicacao": explicacao,
        "situacao_sustentada": situacao_sustentada(con, int(linha["id"])),
    }


def titulos_sem_ato_que_sustente(con, *,
                                 limite: int = LIMITE_DA_LISTA) -> list[dict]:
    """Os títulos cuja situação não tem o ato válido que a sustente. Só LÊ.

    Uma linha por título, com a situação, o ato que falta, o que se sabe do
    porquê (`origem`: DESFEITO, ACERVO ou SEM_ATO) e a situação que os atos
    válidos sustentam. Não corrige nada. É o que o roteiro do dia lê.
    """
    return _achar(con, limite=limite)


def situacao_sem_ato(con, titulo_id: int) -> dict | None:
    """O mesmo achado, para um título só — a ficha. Só LÊ."""
    achados = _achar(con, titulo_id=int(titulo_id), limite=1)
    return achados[0] if achados else None

