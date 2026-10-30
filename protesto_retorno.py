"""
O retorno a CRA — o arquivo que devolve ao apresentante o que a casa fez.

O QUE FALTAVA
    `protesto_arquivo` ja lia e ja ESCREVIA o arquivo de 600 posicoes, e a
    prova disso e o ida e volta: dos 572 arquivos reais, 558 voltam identicos
    byte a byte. O que faltava era a ponte — ligar o `montar_retorno()` ao que
    foi LAVRADO nesta casa, em vez de a um arquivo que se acabou de ler.

    93% dos titulos entram pela CRA. Sem o retorno, eles entram e nunca
    voltam: a Central fica sem saber o que aconteceu com o titulo que mandou.

A OCORRENCIA SAI DO ATO, e ela foi medida
    | Ato lavrado   | Ocorrencia | Onde se mediu |
    |---------------|-----------|---------------|
    | PROTESTO      | `C`       | 287 dos 383 registros de retorno REAIS, e 1.106 dos 1.107 `C` do acervo estao com `snProtestado` e com livro e folha |
    | PAGAMENTO     | `1`       | "Pago" no contrato da CRA; 133 titulos do acervo, todos com `strTipoPG` de pagamento ('12' e '0') |
    | DESISTENCIA   | `3`       | "Retirado" no contrato; 46 do acervo, todos com `strTipoPG` '2' e '4' |
    | CANCELAMENTO  | `A`       | "Protesto cancelado" no contrato |

    O `C` NAO ESTA NO CONTRATO OFICIAL, e sai assim mesmo — porque e o que
    esta casa mandou e a Central aceitou, 287 vezes em 383. E a regra do
    oficial, de 24/08/2026: na duvida, faca como o E-Oficio fazia.

O QUE O RETORNO LEVA DE CADA TITULO
    Nosso numero, valor, saldo, protocolo, a ocorrencia, a data de entrada
    (a do apontamento) e a data da ocorrencia (a do ato). O resto do registro
    vem em branco, e isso e medido: nos 383 reais, especie, cedente e devedor
    estao sempre vazios — o apresentante ja sabe o que mandou.

NADA SAI DUAS VEZES
    Ato informado ganha `retorno_id`, e a lista de pendentes so mostra o que
    ainda nao foi. Mandar o mesmo protesto duas vezes faz a Central registrar
    dois — e desfazer isso e trabalho de carta.

    A OCORRENCIA TAMBEM NAO SAI DUAS VEZES — 29/10/2026. Desfazer o ato e
    lancar outro no lugar nao apaga o que a CRA ja aceitou. O substituto, com
    a mesma ocorrencia no mesmo titulo ou protocolo, nao volta a fila.

    O PROTOCOLO E O QUE A CRA CONHECE, E NAO O TITULO — 29/10/2026. CDA com
    dois devedores entra aqui como DOIS titulos com o MESMO protocolo, e a
    Central so conhece o protocolo. O protocolo 2610070011 (dois titulos)
    foi protestado e aceito no R9012310.261; o protesto de um dos titulos foi
    tornado sem efeito e refeito, e o R9012810.261 levou o protocolo de novo
    como protestado — a CRA recusou o arquivo inteiro com 2161. O ato que
    fica de fora por isso aparece numa lista propria, com o titulo que ja
    informou, o arquivo e a data (`quem_ja_informou`). Ordem do oficial no
    mesmo dia: o sistema impede; quem insistir, so com AFIRMACAO EXPRESSA e
    log (`forcar_envio_de_protocolo_ja_informado`). A conferencia
    `protocolos_com_mais_de_um_titulo` mostra cada caso para o oficial.

    E O ARQUIVO SEM RESPOSTA TAMBEM SEGURA — decisao do oficial, 29/10/2026.
    Retorno gerado e ainda nao respondido pela CRA segura a mesma ocorrencia
    do mesmo titulo ou protocolo, como o aceito; recusado solta
    (`_sql_arquivo_que_segura`).

O ARQUIVO INTEIRO FICA GRAVADO
    Nao so o nome: o que saiu daqui e o que a Central recebeu, e quando ela
    reclamar de um titulo e este teor que se le. Mesma razao do teor congelado
    da certidao.

FUNDAMENTO
    Lei 9.492/1997. Layout medido em `LAYOUT_RETORNO_MEDIDO.md`, sobre 443
    retornos reais de dois lotes.
"""
from __future__ import annotations

import hashlib
import sqlite3

from bd_nativo import banco
from typing import Any

import protesto_arquivo as PA
import protesto_prova as PROVA

# Que ocorrencia cada ato desta casa vira no arquivo. Ver o cabecalho.
#
#   CONFERIDO CONTRA OS ARQUIVOS DE 2026 em 31/08/2026, e as quatro batem:
#   C sai 45 vezes, 1 sai 11, 3 sai 4 e A sai 2. (O `2` do contrato tambem
#   aparece, 2 vezes — e o codigo oficial de «protestado», que esta casa
#   escreve como `C`; os dois convivem nos arquivos reais.)
OCORRENCIA_DO_ATO: dict[str, str] = {
    "PROTESTO": "C",
    "PAGAMENTO": "1",
    "DESISTENCIA": "3",
    "CANCELAMENTO": "A",
}

# O ANDAMENTO LEVA SEMPRE `0` — APONTAMENTO —, e nao a ocorrencia do ato.
#
#   MEDIDO em 31/08/2026 nos 25 andamentos que esta casa mandou em 2026:
#   **`0` em 103 de 103 registros**, sem uma excecao.
#
#   O SISTEMA COPIAVA A DO RETORNO, e o comentario de `gerar` dizia que era «o
#   que se quer». Metade daquilo estava certa — os dois arquivos levam quase os
#   mesmos titulos (42 dos 47 aparecem nos dois) —, e a outra metade nao: e o
#   mesmo movimento contado de outro jeito, e o «outro jeito» inclui a
#   ocorrencia.
#
#   O ESTRAGO QUE ISSO EVITA: um andamento dizendo `C` afirma um PROTESTO que o
#   retorno do mesmo dia ja afirmou. A Central registraria o mesmo protesto
#   duas vezes, por dois arquivos — que e o estrago que a marcacao dos atos
#   existe para impedir, entrando pela porta do lado.
OCORRENCIA_DO_ANDAMENTO = "0"

# Os atos que a CRA precisa saber. Apontamento NAO entra: a Central ja sabe
# que o titulo chegou — foi ela que o mandou — e o apontamento e o recibo
# disso, que vai na CONFIRMACAO e nao no retorno.
ATOS_QUE_VOLTAM = tuple(OCORRENCIA_DO_ATO)

# O QUE VAI EM CADA ARQUIVO, e sao conjuntos DIFERENTES.
#
# Correcao do oficial em 31/08/2026: «sempre que recebe remessa, precisa gerar
# o andamento para atualizar a CRA sobre o andamento». Ate aqui o andamento
# saia com OS MESMOS ATOS do retorno — dizendo «Apontamento» sobre um titulo
# que acabava de ser protestado.
#
# Medido nos 125 arquivos de 2026: o andamento leva `0` (Apontamento) em 103
# de 103 linhas; **38 dos 39** titulos recebidos por remessa aparecem num
# andamento; ele vem na data da remessa ou depois em **38 de 38**, e na data
# do retorno ou antes em **42 de 42**. A ordem e remessa -> andamento ->
# retorno.
ATOS_POR_TIPO_DE_ARQUIVO: dict[str, tuple[str, ...]] = {
    # O retorno conta O QUE ACONTECEU com o titulo.
    "SDTBFORTP": ATOS_QUE_VOLTAM,
    # O andamento conta QUE ELE ENTROU.
    "SDTBFOAND": ("APONTAMENTO",),
}


class RetornoError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcao."""


def _letra_da_ocorrencia(tipo_ato: str | None) -> str:
    """A letra que o ato vira no arquivo. So calcula.

    Cada ato de `OCORRENCIA_DO_ATO` tem uma letra so. Casar o tipo do ato e
    casar a ocorrencia — e o teste que conta as letras guarda isso.
    """
    tipo = str(tipo_ato or "")
    if tipo == "APONTAMENTO":
        return OCORRENCIA_DO_ANDAMENTO
    return OCORRENCIA_DO_ATO.get(tipo, "?")


def _sql_mesmo_titulo_ou_protocolo(ato: str = "a", titulo: str = "t") -> str:
    """O outro ato e do mesmo titulo, ou do mesmo protocolo do mesmo apresentante.

    Protocolo vazio nao casa com protocolo vazio. O apresentante entra no
    protocolo porque cada retorno e de um banco: o protocolo de outro
    apresentante nao e este titulo na CRA.
    """
    return f"""(
        antigo.titulo_id = {ato}.titulo_id
        OR (
            COALESCE(ta.apresentante_codigo, '')
                = COALESCE({titulo}.apresentante_codigo, '')
            AND NULLIF(BTRIM(COALESCE(ta.protocolo, '')), '') IS NOT NULL
            AND BTRIM(ta.protocolo) = BTRIM(COALESCE({titulo}.protocolo, ''))
        )
    )"""


def _sql_arquivo_que_segura(r: str = "r", tipo_do_arquivo: str = "%s") -> str:
    """O arquivo do ato antigo segura a ocorrência: existe, é do tipo que
    leva aquele ato e a CRA NÃO o recusou. Só monta o SQL.

    ACEITO OU AINDA SEM RESPOSTA — decisão do oficial, 29/10/2026. Até aqui só
    segurava o arquivo que a CRA aceitou (`cra_enviado_em` preenchido). O
    arquivo gerado e ainda sem resposta também segura: se ele subir, a CRA
    grava a ocorrência, e o segundo arquivo com a mesma letra para o mesmo
    protocolo seria recusado inteiro (2161). Recusado não segura — a Central
    não gravou nada, e o ato se solta. `_gravar_envio` limpa a recusa e
    `_registrar_recusa` limpa o envio, então «sem recusa» é aceito ou sem
    resposta.

    UMA DEFINIÇÃO SÓ: a fila, o nome do arquivo anterior e `quem_ja_informou`
    a usam. Três cópias divergiriam no primeiro conserto.
    """
    return (f"({r}.id IS NOT NULL"
            f" AND COALESCE(BTRIM({r}.cra_recusado_em), '') = ''"
            f" AND {r}.tipo = {tipo_do_arquivo})")


def _sql_ocorrencia_ja_aceita(ato: str = "a", titulo: str = "t") -> str:
    """Verdadeiro se a CRA ja tem esta ocorrencia. Um `%s`: o tipo do arquivo.

    O ato antigo pode estar desfeito. O que a Central gravou nao se apaga
    porque o selo daqui nao saiu. Retorno recusado nao conta: e ocorrencia
    que ela nao gravou. O arquivo gerado e ainda sem resposta CONTA desde
    29/10/2026 (`_sql_arquivo_que_segura`). A marca manual
    (`cra_ja_informado_em`) conta do mesmo jeito — foi o oficial quem disse
    que a Central ja tem esta ocorrencia.

    A AFIRMAÇÃO EXPRESSA DESTRAVA O QUE OUTRO ATO INFORMOU — 29/10/2026. Com
    `cra_reenvio_afirmado_em` preenchido, o ato volta à fila mesmo que outro
    título do protocolo (ou o ato desfeito no lugar dele) já tenha levado a
    letra. A marca manual DO PRÓPRIO ATO continua valendo: quem marcou disse
    que a Central já tem a ocorrência, e `forcar_envio_de_protocolo_ja_informado`
    recusa contradizê-la.
    """
    return f"""(
        {ato}.cra_ja_informado_em IS NOT NULL
        OR ({ato}.cra_reenvio_afirmado_em IS NULL AND EXISTS (
            SELECT 1
              FROM pt_atos antigo
              JOIN pt_titulos ta ON ta.id = antigo.titulo_id
              LEFT JOIN pt_retornos r ON r.id = antigo.retorno_id
             WHERE antigo.id <> {ato}.id
               AND antigo.tipo = {ato}.tipo
               AND (
                    {_sql_arquivo_que_segura()}
                 OR antigo.cra_ja_informado_em IS NOT NULL
               )
               AND {_sql_mesmo_titulo_ou_protocolo(ato, titulo)}
        ))
    )"""


def _where_da_fila(tipo: str, apresentante: str | None, *,
                   ja_aceita: bool) -> tuple[str, list[Any]]:
    """O filtro de `pendentes`, ou o inverso (os que a CRA ja aceitou).

    Os `%s`, nesta ordem: os tipos de ato, o tipo do arquivo (o `%s` de
    `_sql_ocorrencia_ja_aceita`) e, se houver, o apresentante.
    """
    quais = ATOS_POR_TIPO_DE_ARQUIVO.get(str(tipo), ATOS_QUE_VOLTAM)
    marca = _sql_ocorrencia_ja_aceita()
    onde = [
        "a.retorno_id IS NULL",
        "COALESCE(a.cancelado, 0) = 0",
        f"a.tipo IN ({','.join(['%s'] * len(quais))})",
        "t.origem = 'CRA'",
        (marca if ja_aceita else f"NOT {marca}"),
    ]
    params: list[Any] = [*quais, str(tipo)]
    if apresentante:
        onde.append("t.apresentante_codigo = %s")
        params.append(str(apresentante).strip())
    return " AND ".join(onde), params


#: Motivo escrito da marca manual — o mesmo piso das outras razoes da casa.
MINIMO_DO_MOTIVO = 10

# ------------------------------------------ a afirmação expressa do retorno
#
# O CONTRATO COMUM DA CASA — ordem do oficial, 29/10/2026: «o sistema tem de
# impedir o erro; se a escrevente insistir, só com afirmação expressa e log».
# A caixa `afirmo` marcada E o texto `afirmacao`, com pelo menos 30 LETRAS
# além da frase de abertura; a rota grava
# `audit("AFIRMACAO_EXPRESSA", "pt_atos", ato_id, {"regra", "afirmacao",
# "o_que_faltava"})` FORA da transação, porque `audit` abre a sua.
#
# É O MESMO CONTRATO das outras travas da reestruturação do protesto, e mora
# num lugar só: `protesto_prova` (PR #106, no `main` desde 29/10/2026). A
# frase, o piso, a ação de auditoria e a conferência do texto vêm de lá —
# duas réguas para «a afirmação vale?» divergiriam no primeiro conserto.
# (Até o #106 entrar, este módulo tinha uma cópia; ela saiu.)

#: A frase com que a afirmação começa. A tela a mostra fixa, antes do texto.
FRASE_DA_AFIRMACAO = PROVA.FRASE_DA_AFIRMACAO
#: Quantas LETRAS a afirmação precisa ter, além da frase.
PISO_DA_AFIRMACAO = PROVA.PISO_DA_AFIRMACAO
#: O nome curto desta trava, que a tela das afirmações filtra.
REGRA_PROTOCOLO_JA_INFORMADO = "RETORNO_PROTOCOLO_JA_INFORMADO"

COMO_AFIRMAR = (
    f"Se você tem certeza de que a CRA NÃO tem esta ocorrência, marque "
    f"«Afirmo» e escreva a afirmação expressa — «{FRASE_DA_AFIRMACAO} …», "
    f"com pelo menos {PISO_DA_AFIRMACAO} letras. Ela fica gravada no ato e na "
    f"auditoria, com o seu nome.")


def afirmacao_valida(texto: Any) -> str | None:
    """O texto inteiro da afirmação, já com a frase de abertura — ou `None`
    se ela não vale. Só calcula. A régua é a de `protesto_prova`."""
    return PROVA.afirmacao_valida(texto)


def _data_br(texto: Any) -> str:
    """`2026-10-23T13:25:00` -> `23/10/2026`. Sem data, vazio. Só calcula."""
    s = str(texto or "").strip()[:10]
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}"
    return s


def descrever_informante(i: dict) -> str:
    """Uma linha: qual ato já levou a ocorrência à CRA, e quando. Só calcula.

    O NÚMERO DO TÍTULO NÃO BASTA, e foi medido: no protocolo 2610070011 os
    dois títulos têm o MESMO número (é a mesma CDA, um por devedor). O que
    os separa é o número interno do título, `#9602` e `#9603`.
    """
    quem = (f"título {i.get('numero_titulo') or '—'} #{i.get('titulo_id')}, "
            f"ato {i.get('ato_id')}")
    if int(i.get("desfeito") or 0):
        quem += " (hoje desfeito)"
    if i.get("arquivo"):
        if str(i.get("ambiente") or "") == "EOFICIO":
            return f"{quem}, informado pelo sistema antigo antes da virada"
        quando = _data_br(i.get("aceito_em"))
        if not quando:
            # Gerado e ainda sem resposta — segura desde 29/10/2026.
            gerado = _data_br(i.get("gerado_em"))
            return (f"{quem}, no arquivo {i['arquivo']}"
                    + (f" gerado em {gerado}" if gerado else "")
                    + ", ainda sem resposta da CRA")
        return (f"{quem}, no arquivo {i['arquivo']}, aceito pela CRA em "
                f"{quando}")
    marcado = _data_br(i.get("marcado_em"))
    return (f"{quem}, marcado à mão como já informado"
            + (f" em {marcado}" if marcado else "")
            + (f" (arquivo {i['arquivo_marcado']})"
               if i.get("arquivo_marcado") else ""))


def frase_dos_pulados(pulados: list[dict], *, intro: str | None = None) -> str:
    """A frase da tela: quais atos ficaram de fora, e em que arquivo a CRA
    ja aceitou a ocorrencia. So calcula.

    DESDE 29/10/2026 ela diz QUAL TÍTULO já informou, quando foi outro título
    do mesmo protocolo — sem isso o balcão procura o ato no título errado.
    """
    if not pulados:
        return ""
    cabeca = intro or (
        "Não entram neste retorno: a CRA já aceitou a mesma ocorrência, ou "
        "ela já vai num arquivo que a CRA ainda não respondeu (mesmo título "
        "ou o mesmo protocolo)")

    def uma(p: dict) -> str:
        arquivo = (str(p.get("arquivo_anterior") or "").strip()
                   or "um retorno anterior")
        letra = p.get("ocorrencia") or _letra_da_ocorrencia(p.get("tipo"))
        numero = p.get("numero_titulo") or "—"
        if p.get("titulo_id") is not None:
            numero = f"{numero} #{p.get('titulo_id')}"
        base = (f"ato {p.get('ato_id')} ({p.get('tipo')}, ocorrência {letra}, "
                f"título {numero}, "
                f"protocolo {p.get('protocolo') or 'sem protocolo'})")
        outros = [i for i in (p.get("informantes") or [])
                  if str(i.get("titulo_id")) != str(p.get("titulo_id"))]
        if outros:
            return (f"{base} — já informado por outro título do mesmo "
                    f"protocolo: "
                    + "; ".join(descrever_informante(i) for i in outros[:2]))
        return f"{base} — arquivo {arquivo}"

    mostrados = list(pulados)[:8]
    texto = "; ".join(uma(p) for p in mostrados)
    if len(pulados) > len(mostrados):
        texto += f"; e mais {len(pulados) - len(mostrados)}"
    return f"{cabeca} — {texto}."


def _data_arquivo(data: Any) -> str:
    """`2026-08-25` -> `25082026`, que e como o arquivo escreve data."""
    s = str(data or "")[:10]
    if len(s) == 10 and s[4] == "-":
        return f"{s[8:10]}{s[5:7]}{s[:4]}"
    return s


# ---------------------------------------------------------------- pendentes


def pendentes(con: sqlite3.Connection, *,
              apresentante_codigo: str | None = None,
              tipo: str = "SDTBFORTP") -> list[dict]:
    """Os atos lavrados que a CRA ainda nao sabe. So LE.

    So entra titulo que VEIO DA CRA — o digitado no balcao nao tem para onde
    voltar. E so ato do tipo que AQUELE ARQUIVO carrega.

    `tipo` NAO E DETALHE: o retorno leva os atos finais (protesto, pagamento,
    desistencia, cancelamento) e o andamento leva **o apontamento**. Ate
    31/08/2026 os dois liam a mesma lista, e o andamento saia dizendo
    «Apontamento» sobre um titulo que acabara de ser protestado. Ver
    `ATOS_POR_TIPO_DE_ARQUIVO`, com a medicao ao lado.
    """
    # TÍTULO QUE VEIO DA CENPROT NÃO VOLTA PELA CRA — 21/10/2026. Até aqui
    # entrava `t.origem IN ('CRA', 'CENPROT')`, e o retorno do 900001/2
    # (pedido 9000002 da Gestão de Pedidos) foi recusado três vezes:
    # «APRESENTANTE: TAB - SEQUENCIAL REMESSA: 000077 NÃO FOI ENCONTRADO NA
    # CRA» (código 2154) — a remessa nunca passou por ela. O pagamento entrou
    # na CENPROT pelo XML «D» (aceito no mesmo dia). Esses atos vão pela tela
    # «XML do CENPROT»; `pendentes_da_cenprot` os conta para a tela dizer isso.
    #
    # ATO DESFEITO NÃO VAI À CRA — 28/10/2026. Até aqui a lista não olhava
    # `cancelado`, e o ato que se lavrou e foi desfeito (o selo não saiu, ou
    # foi tornado sem efeito) entrava no retorno como se existisse. Caso
    # real: no título 1353 o CANCELAMENTO (ato 4104) foi desfeito às 13h57
    # por falta de selo, o retorno R3412810.261 saiu às 14h32 dizendo «A —
    # protesto cancelado», a CRA aceitou — e hoje a Central diz «cancelado»
    # enquanto o livro diz «protestado». Medido na produção nesse dia: 19
    # atos desfeitos já tinham sido informados (16 protestos, 2
    # cancelamentos, 1 pagamento). É o filtro que a certidão, o XML da
    # CENPROT e `pendentes_da_cenprot` já faziam.
    #
    # OCORRÊNCIA JÁ ACEITA NÃO VOLTA — 29/10/2026. No mesmo título 1353 o
    # cancelamento 4104 saiu no R3412810.261 (pt_retornos 26), a CRA aceitou
    # com 0000, o ato foi desfeito por falta de selo e o 4128, novo
    # cancelamento do mesmo título, entrou de novo na fila. A lista só olhava
    # se ESTE ato tinha `retorno_id`. Mandar o segundo «A» faz a CRA recusar
    # o arquivo inteiro com 2161 «NENHUM REGISTRO FOI GRAVADO». Fica de fora
    # o ato cuja ocorrência (mesmo título ou mesmo protocolo, mesma letra) já
    # foi aceita, ou que o oficial marcou como já informada.
    onde, params = _where_da_fila(
        str(tipo), apresentante_codigo, ja_aceita=False)

    #
    # E O PROTOCOLO COM DOIS TÍTULOS — 29/10/2026. A mesma régua alcança o
    # título irmão: a CRA conhece o protocolo, e não o título. O ato liberado
    # por afirmação expressa (`cra_reenvio_afirmado_em`) volta, e a tela diz
    # quem afirmou. E o arquivo gerado e ainda sem resposta segura como o
    # aceito (decisão do oficial no mesmo dia); o recusado solta.
    linhas = banco(con).ler(
        f"""SELECT a.id ato_id, a.tipo, a.data_ato, t.id titulo_id,
                   a.cra_reenvio_afirmado_em, a.cra_reenvio_afirmado_por,
                   t.numero_titulo, t.nosso_numero, t.valor_centavos,
                   t.saldo_centavos, t.protocolo, t.apresentante_codigo,
                   t.apresentante_nome, t.cra_identificacao, t.situacao,
                   (SELECT data_ato FROM pt_atos e
                     WHERE e.titulo_id = t.id AND e.tipo = 'APONTAMENTO'
                       AND COALESCE(e.cancelado, 0) = 0
                     ORDER BY e.id LIMIT 1) data_entrada
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
             WHERE {onde}
             ORDER BY t.apresentante_codigo, a.data_ato, a.id""",
        params)
    return linhas


def quem_ja_informou(con: sqlite3.Connection,
                     ato_ids: list[int]) -> dict[int, list[dict]]:
    """Para cada ato, os OUTROS atos que já levaram a mesma ocorrência à CRA
    pelo mesmo título ou pelo mesmo protocolo. Só LÊ.

    É a mesma régua de `_sql_ocorrencia_ja_aceita` — mesmo tipo, mesmo título
    ou mesmo protocolo do mesmo apresentante, arquivo ACEITO OU AINDA SEM
    RESPOSTA do tipo que leva aquele ato (o andamento leva o apontamento; o
    retorno, os atos finais), ou a marca manual —, agora dizendo QUEM: o
    título, o ato, se ele está desfeito, o arquivo e a data em que a Central
    aceitou (ou em que o arquivo foi gerado, se ela ainda não respondeu).

    POR QUE A TELA PRECISA DISSO — 29/10/2026. O protocolo 2610070011 tem dois
    títulos com o mesmo número (#9602 e #9603). O protesto do #9603 foi
    refeito e voltou a «Esperando retorno» como se a CRA nunca o tivesse
    ouvido; ela tinha, pelo #9602, no R9012310.261. Dizer só «a CRA já
    aceitou» manda o balcão procurar no título errado.
    """
    ids = sorted({int(i) for i in ato_ids if i is not None})
    if not ids:
        return {}
    # O arquivo que conta, do tipo que leva aquele ato — a régua da fila.
    # Vale para o SELECT (dizer se foi ele) e para o WHERE.
    segura = _sql_arquivo_que_segura(
        "r", "CASE WHEN a.tipo = 'APONTAMENTO' THEN 'SDTBFOAND' "
             "ELSE 'SDTBFORTP' END")
    linhas = banco(con).ler(
        f"""SELECT a.id alvo_id, antigo.id ato_id, antigo.tipo,
                   antigo.titulo_id, ta.numero_titulo,
                   COALESCE(antigo.cancelado, 0) desfeito, antigo.data_ato,
                   r.id retorno_id, r.nome_arquivo arquivo,
                   r.cra_enviado_em aceito_em, r.gerado_em,
                   r.cra_enviado_ambiente ambiente,
                   CASE WHEN {segura} THEN 1 ELSE 0 END pelo_arquivo,
                   antigo.cra_ja_informado_em marcado_em,
                   antigo.cra_ja_informado_por marcado_por,
                   rm.nome_arquivo arquivo_marcado
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
              JOIN pt_atos antigo
                ON antigo.id <> a.id AND antigo.tipo = a.tipo
              JOIN pt_titulos ta ON ta.id = antigo.titulo_id
              LEFT JOIN pt_retornos r ON r.id = antigo.retorno_id
              LEFT JOIN pt_retornos rm
                ON rm.id = antigo.cra_ja_informado_retorno_id
             WHERE a.id IN ({','.join(['%s'] * len(ids))})
               AND ({segura} OR antigo.cra_ja_informado_em IS NOT NULL)
               AND {_sql_mesmo_titulo_ou_protocolo()}
             ORDER BY a.id, COALESCE(antigo.cancelado, 0), antigo.id""",
        ids)
    saida: dict[int, list[dict]] = {}
    for linha in linhas:
        alvo = int(linha.pop("alvo_id"))
        if not int(linha.pop("pelo_arquivo") or 0):
            # Só a marca manual sustenta este: o arquivo dele não conta.
            linha["arquivo"] = None
            linha["aceito_em"] = None
        # A frase sai daqui, e a tela só a mostra: duas descrições do mesmo
        # fato (a da tela e a da recusa) divergiriam no primeiro conserto.
        linha["frase"] = descrever_informante(linha)
        saida.setdefault(alvo, []).append(linha)
    return saida


def _completar_pulados(con: sqlite3.Connection,
                       linhas: list[dict]) -> list[dict]:
    """Junta o nome do arquivo anterior, a letra e QUEM já informou. Só LÊ.

    `por_outro_titulo` separa os dois casos na tela: o substituto do ato
    desfeito no mesmo título (PR #101) e o título irmão do mesmo protocolo
    (29/10/2026). `pode_insistir` diz se a afirmação expressa cabe — não
    cabe quando a marca manual é DO PRÓPRIO ATO.
    """
    quem = quem_ja_informou(con, [int(x["ato_id"]) for x in linhas])
    for linha in linhas:
        linha["arquivo_anterior"] = (
            linha.get("arquivo_aceito")
            or linha.get("arquivo_marcado")
            or linha.get("arquivo_proprio")
            or "")
        linha["ocorrencia"] = _letra_da_ocorrencia(linha.get("tipo"))
        informantes = quem.get(int(linha["ato_id"]), [])
        linha["informantes"] = informantes
        linha["por_outro_titulo"] = any(
            str(i.get("titulo_id")) != str(linha.get("titulo_id"))
            for i in informantes)
        linha["pode_insistir"] = (not linha.get("cra_ja_informado_em")
                                  and bool(informantes))
    return linhas


def pulados_por_ocorrencia_aceita(con: sqlite3.Connection, *,
                                  apresentante_codigo: str | None = None,
                                  tipo: str = "SDTBFORTP") -> list[dict]:
    """Atos que entrariam na fila e ficam de fora porque a CRA já aceitou
    a mesma ocorrência — ou ela já vai num arquivo que a CRA ainda não
    respondeu (desde 29/10/2026). Só LÊ.

    É o avesso de `pendentes`: mesma régua, menos esta. A tela avisa quais
    são, e `montar` não os põe no arquivo.
    """
    onde, params_da_fila = _where_da_fila(
        str(tipo), apresentante_codigo, ja_aceita=True)
    # O `%s` do nome do arquivo aceito vem no SELECT, antes dos da fila.
    params: list[Any] = [str(tipo), *params_da_fila]
    linhas = banco(con).ler(
        f"""SELECT a.id ato_id, a.tipo, a.data_ato,
                   a.cra_ja_informado_motivo, a.cra_ja_informado_em,
                   t.id titulo_id,
                   t.numero_titulo, t.protocolo, t.apresentante_codigo,
                   t.apresentante_nome,
                   (SELECT r.nome_arquivo
                      FROM pt_atos antigo
                      JOIN pt_titulos ta ON ta.id = antigo.titulo_id
                      JOIN pt_retornos r ON r.id = antigo.retorno_id
                     WHERE antigo.id <> a.id
                       AND antigo.tipo = a.tipo
                       AND {_sql_arquivo_que_segura()}
                       AND {_sql_mesmo_titulo_ou_protocolo()}
                     ORDER BY (NULLIF(BTRIM(r.cra_enviado_em), '') IS NULL),
                              r.id DESC
                     LIMIT 1) arquivo_aceito,
                   (SELECT r.nome_arquivo
                      FROM pt_atos antigo
                      JOIN pt_titulos ta ON ta.id = antigo.titulo_id
                      LEFT JOIN pt_retornos r
                        ON r.id = antigo.cra_ja_informado_retorno_id
                     WHERE antigo.id <> a.id
                       AND antigo.tipo = a.tipo
                       AND antigo.cra_ja_informado_em IS NOT NULL
                       AND {_sql_mesmo_titulo_ou_protocolo()}
                     ORDER BY antigo.id DESC
                     LIMIT 1) arquivo_marcado,
                   (SELECT r.nome_arquivo FROM pt_retornos r
                     WHERE r.id = a.cra_ja_informado_retorno_id
                   ) arquivo_proprio
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
             WHERE {onde}
             ORDER BY t.apresentante_codigo, a.data_ato, a.id""",
        params)
    return _completar_pulados(con, linhas)


def ja_aceitas_fora_da_fila(con: sqlite3.Connection) -> list[dict]:
    """Os atos fora da fila do retorno e do andamento por ocorrência já
    aceita. Só LÊ. A tela de retornos mostra a lista."""
    vistos: dict[int, dict] = {}
    for qual in ("SDTBFORTP", "SDTBFOAND"):
        for p in pulados_por_ocorrencia_aceita(con, tipo=qual):
            vistos[int(p["ato_id"])] = p
    return list(vistos.values())


#: Como a explicação diz a ocorrência — a palavra do contrato da CRA.
NOME_DA_OCORRENCIA = {"PROTESTO": "protestado", "PAGAMENTO": "pago",
                      "DESISTENCIA": "retirado", "CANCELAMENTO": "cancelado",
                      "APONTAMENTO": "apontado"}


def _informante_principal(linha: dict) -> dict | None:
    """O ato que mais explica a trava: o de OUTRO título, válido, primeiro;
    depois o de outro título desfeito; depois o do próprio título. Só calcula."""
    meu = str(linha.get("titulo_id"))
    informantes = list(linha.get("informantes") or [])
    for chave in (lambda i: str(i.get("titulo_id")) != meu
                  and not int(i.get("desfeito") or 0),
                  lambda i: str(i.get("titulo_id")) != meu,
                  lambda i: True):
        for i in informantes:
            if chave(i):
                return i
    return None


def _explicacao_do_repetido(linha: dict) -> str:
    """«já informado como protestado pelo título X #id em dd/mm/aaaa». Só calcula."""
    nome = NOME_DA_OCORRENCIA.get(str(linha.get("tipo") or ""),
                                  f"ocorrência {linha.get('ocorrencia')}")
    i = _informante_principal(linha)
    if i is None:
        # Só a marca manual do próprio ato sustenta a trava.
        return (f"já informado como {nome} — marcado à mão pela serventia"
                + (f" ({linha['arquivo_anterior']})"
                   if linha.get("arquivo_anterior") else ""))
    if i.get("arquivo") and not str(i.get("aceito_em") or "").strip():
        # Arquivo gerado e ainda sem resposta — segura desde 29/10/2026.
        gerado = _data_br(i.get("gerado_em"))
        return (f"já vai como {nome} pelo título "
                f"{i.get('numero_titulo') or '—'} #{i.get('titulo_id')} no "
                f"arquivo {i['arquivo']}"
                + (f", gerado em {gerado}" if gerado else "")
                + ", ainda sem resposta da CRA")
    quando = _data_br(i.get("aceito_em") or i.get("marcado_em"))
    texto = (f"já informado como {nome} pelo título "
             f"{i.get('numero_titulo') or '—'} #{i.get('titulo_id')}"
             + (f" em {quando}" if quando else ""))
    if i.get("arquivo") and str(i.get("ambiente") or "") != "EOFICIO":
        texto += f" ({i['arquivo']})"
    elif str(i.get("ambiente") or "") == "EOFICIO":
        texto += " (pelo sistema antigo, antes da virada)"
    return texto


def _por_que_retido(linha: dict) -> str:
    """`ACEITE` se a CRA já tem a ocorrência; `SEM_RESPOSTA` se ela só vai num
    arquivo ainda não respondido. Só calcula.

    A marca manual conta como aceite: foi o oficial quem disse que a Central a
    tem. O que o E-Ofício informou antes da virada, também.
    """
    if str(linha.get("cra_ja_informado_em") or "").strip():
        return "ACEITE"
    for i in linha.get("informantes") or []:
        if (str(i.get("aceito_em") or "").strip()
                or str(i.get("marcado_em") or "").strip()
                or str(i.get("ambiente") or "") == "EOFICIO"):
            return "ACEITE"
    return "SEM_RESPOSTA"


def protocolos_repetidos_na_fila(con: sqlite3.Connection) -> list[dict]:
    """Os atos do próximo retorno (ou andamento) cujo PROTOCOLO a CRA já tem
    com aquela ocorrência. Só LÊ — o contrato do roteiro do protesto.

    O ROTEIRO LÊ POR ESTE NOME (PR #104, `protesto_roteiro.GANCHOS`): passa
    só a conexão e mostra cada linha como pendência, com `titulo_id`,
    `numero_titulo`, `protocolo` e `explicacao` («já informado como
    protestado pelo título X em dd/mm/aaaa»).

    SÃO DUAS SITUAÇÕES, e as duas pedem olho:
      - `RETIDO`: o ato ficou fora da fila (a régua de `pendentes`) porque a
        mesma ocorrência já foi aceita pelo mesmo título ou pelo outro título
        do protocolo — é o 2610070011 de 29/10/2026;
      - `LIBERADO`: o ato voltou à fila por AFIRMAÇÃO EXPRESSA de alguém da
        serventia, e vai no próximo arquivo mesmo assim — se a CRA o recusar,
        é este o caso.

    O RETIDO COM ACEITE DA CRA ESTÁ CERTO — 30/10/2026. `so_informacao` o marca:
    o roteiro o mostra como informação, sem cobrar nem exigir afirmação no
    encerramento, porque não há tela nem motivo para ele sair desta lista. Só é
    pendência o retido por arquivo ainda sem resposta (`retido_por`).
    """
    saida: list[dict] = []
    for p in ja_aceitas_fora_da_fila(con):
        retido_por = _por_que_retido(p)
        saida.append({
            "ato_id": int(p["ato_id"]), "tipo": p["tipo"],
            "ocorrencia": p.get("ocorrencia"),
            "titulo_id": int(p["titulo_id"]),
            "numero_titulo": p.get("numero_titulo"),
            "protocolo": p.get("protocolo"),
            "apresentante_codigo": p.get("apresentante_codigo"),
            "situacao": "RETIDO",
            "retido_por": retido_por,
            "so_informacao": retido_por == "ACEITE",
            "por_outro_titulo": bool(p.get("por_outro_titulo")),
            "explicacao": _explicacao_do_repetido(p)})
    liberados: dict[int, dict] = {}
    for qual in ("SDTBFORTP", "SDTBFOAND"):
        for a in pendentes(con, tipo=qual):
            if str(a.get("cra_reenvio_afirmado_em") or "").strip():
                liberados[int(a["ato_id"])] = dict(a)
    quem = quem_ja_informou(con, list(liberados))
    for ato_id, a in liberados.items():
        a["informantes"] = quem.get(ato_id, [])
        a["ocorrencia"] = _letra_da_ocorrencia(a.get("tipo"))
        saida.append({
            "ato_id": ato_id, "tipo": a["tipo"], "ocorrencia": a["ocorrencia"],
            "titulo_id": int(a["titulo_id"]),
            "numero_titulo": a.get("numero_titulo"),
            "protocolo": a.get("protocolo"),
            "apresentante_codigo": a.get("apresentante_codigo"),
            "situacao": "LIBERADO",
            "por_outro_titulo": any(
                str(i.get("titulo_id")) != str(a["titulo_id"])
                for i in a["informantes"]),
            "explicacao": (
                f"{_explicacao_do_repetido(a)}; voltou à fila por afirmação "
                f"expressa de {a.get('cra_reenvio_afirmado_por') or '—'} em "
                f"{_data_br(a.get('cra_reenvio_afirmado_em'))}")})
    return saida


def pendentes_da_cenprot(con: sqlite3.Connection, *,
                         apresentante_codigo: str | None = None) -> int:
    """Quantos atos de título VINDO DA CENPROT esperam ser informados. Só LÊ.

    Eles não entram no retorno à CRA (ver `pendentes`); a conta existe para a
    tela dizer onde eles vão, em vez de o apresentante parecer em dia.
    """
    onde = ["a.retorno_id IS NULL", "a.cenprot_xml_id IS NULL",
            "COALESCE(a.cancelado, 0) = 0",
            f"a.tipo IN ({','.join(['%s'] * len(ATOS_QUE_VOLTAM))})",
            "t.origem = 'CENPROT'"]
    params: list[Any] = list(ATOS_QUE_VOLTAM)
    if apresentante_codigo:
        onde.append("t.apresentante_codigo = %s")
        params.append(str(apresentante_codigo).strip())
    return int(banco(con).valor(
        f"""SELECT count(*) AS n FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
             WHERE {' AND '.join(onde)}""", params) or 0)


def apresentantes_pendentes(con: sqlite3.Connection) -> list[dict]:
    """Quantos atos esperam retorno, por apresentante. So LE."""
    grupos: dict[str, dict] = {}
    for a in pendentes(con):
        codigo = (a["apresentante_codigo"] or "").strip()
        g = grupos.setdefault(codigo, {
            "apresentante_codigo": codigo,
            "apresentante_nome": a["apresentante_nome"],
            "atos": 0,
            "marca": PA.marca_do_apresentante(codigo) if codigo else None,
        })
        g["atos"] += 1
    return sorted(grupos.values(), key=lambda g: -g["atos"])


# ------------------------------------------------------------------ montar


def _titulo_completo(con: sqlite3.Connection, a: dict) -> dict:
    """Os campos da REMESSA do titulo, para o andamento e a confirmacao.

    O andamento nao tem layout proprio: e o da remessa mais o bloco do
    retorno. Por isso ele leva o titulo inteiro — cedente, devedor, endereco,
    especie —, e nao so a chave como o retorno.
    """
    bd = banco(con)
    t = bd.um(
        """SELECT * FROM pt_titulos WHERE id=%s""", (int(a["titulo_id"]),))
    d = bd.um(
        """SELECT * FROM pt_devedores WHERE titulo_id=%s ORDER BY id LIMIT 1""",
        (int(a["titulo_id"]),))
    devedor = dict(d) if d else {}
    return {
        "cedente_nome": t["cedente_nome"] or "",
        "cedente_documento": t["cedente_documento"] or "",
        "cedente_endereco": t["cedente_endereco"] or "",
        "cedente_cep": t["cedente_cep"] or "",
        "cedente_cidade": t["cedente_cidade"] or "",
        "cedente_uf": t["cedente_uf"] or "",
        "especie": t["especie"] or "",
        "numero_do_titulo": t["numero_titulo"] or "",
        "data_de_emissao": _data_arquivo(t["data_emissao"]),
        "data_de_vencimento": _data_arquivo(t["data_vencimento"]),
        "tipo_de_moeda": t["tipo_moeda"] or "1",
        "praca_de_protesto": t["praca_protesto"] or "",
        "tipo_de_endosso": t["tipo_endosso"] or "",
        "aceite": t["aceite"] or "",
        "motivo_do_protesto": t["motivo_protesto"] or "",
        "devedor_nome": devedor.get("nome") or "",
        "devedor_tipo_de_documento": ("002" if devedor.get("documento_tipo")
                                      == "CNPJ" else "001"),
        "devedor_documento": devedor.get("documento_numero") or "",
        "devedor_endereco": devedor.get("endereco") or "",
        "devedor_cep": devedor.get("cep") or "",
        "devedor_cidade": devedor.get("cidade") or "",
        "devedor_uf": devedor.get("uf") or "",
        "devedor_bairro": devedor.get("bairro") or "",
    }


def montar(con: sqlite3.Connection, *, apresentante_codigo: str, dia: str,
           marca: str | None = None, numero_da_remessa: Any = 1,
           tipo: str = "SDTBFORTP") -> dict:
    """Monta o arquivo de saida do apresentante, com o que falta informar.

    So LE — quem grava e `gerar()`. Devolve o arquivo escrito e os atos que
    entraram nele, para a tela mostrar antes de mandar.

    `tipo` escolhe entre o RETORNO (so a chave e o resultado) e o ANDAMENTO
    (o titulo inteiro, no layout da remessa mais o bloco do retorno).
    """
    codigo = str(apresentante_codigo or "").strip()
    if not codigo:
        raise RetornoError(
            "Informe o apresentante: o retorno volta para quem mandou, e sem o "
            "código dele não há nem cabeçalho nem a letra da posição 566.")
    # Antes dos pendentes: se a fila está vazia porque a ocorrência já foi
    # aceita, a frase diz quais atos ficaram de fora — e não só «não há ato».
    pulados = pulados_por_ocorrencia_aceita(
        con, apresentante_codigo=codigo, tipo=tipo)
    atos = pendentes(con, apresentante_codigo=codigo, tipo=tipo)
    if not atos:
        if pulados:
            raise RetornoError(frase_dos_pulados(pulados))
        qual = ("apontamento" if tipo == "SDTBFOAND" else "ato")
        da_cenprot = (pendentes_da_cenprot(con, apresentante_codigo=codigo)
                      if tipo == "SDTBFORTP" else 0)
        if da_cenprot:
            raise RetornoError(
                f"Não há {qual} para a CRA do apresentante {codigo}, mas "
                f"{da_cenprot} ato(s) de título que veio pela CENPROT esperam ser "
                f"informados — esses vão no arquivo XML da CENPROT (Protesto → "
                f"XML do CENPROT), e não no retorno à CRA.")
        raise RetornoError(
            f"Não há {qual} novo para informar ao apresentante {codigo}. Tudo "
            f"o que foi lavrado para ele já entrou num arquivo anterior.")

    faltando = [a for a in atos if not (a["protocolo"] or "").strip()]
    if faltando:
        raise RetornoError(
            f"{len(faltando)} título(s) deste apresentante estão sem número de "
            f"protocolo, e ele é o que volta na posição 448 do arquivo. Os "
            f"títulos vindos do acervo antigo podem estar assim; confira o "
            f"protocolo no livro e informe antes de gerar o retorno.")

    titulos = []
    for a in atos:
        extra = (_titulo_completo(con, a) if tipo != "SDTBFORTP" else {})
        titulos.append({
            **extra,
            "codigo_do_apresentante": codigo,
            # A identificação do título na Central, quando a carga a trouxe
            # (`tbSDT.Campo03`); senão o que o título recebido aqui guardou nas
            # posições 005/019 — que, no título da remessa, é ela mesma.
            "identificacao_do_apresentante": (a.get("cra_identificacao")
                                              or a["apresentante_nome"] or ""),
            "nosso_numero": a["nosso_numero"] or "",
            "valor_do_titulo": int(a["valor_centavos"] or 0),
            "saldo_a_protestar": int(a["saldo_centavos"] or 0),
            "protocolo": (a["protocolo"] or "").strip(),
            # O ANDAMENTO DIZ «APONTADO»; O RETORNO DIZ O QUE ACONTECEU.
            #
            # Agora as duas coisas se sustentam sozinhas: o andamento so leva
            # ato de APONTAMENTO, e a ocorrencia dele e `0` — que e o que o
            # contrato chama de «Apontamento» e o que esta casa mandou em 103
            # de 103 linhas. Ate 31/08/2026 este `if` era a UNICA coisa que
            # separava os dois arquivos, e os titulos eram os mesmos.
            "ocorrencia": (OCORRENCIA_DO_ANDAMENTO if tipo == "SDTBFOAND"
                           else OCORRENCIA_DO_ATO[a["tipo"]]),
            "data_entrada": _data_arquivo(a["data_entrada"] or a["data_ato"]),
            "data_ocorrencia": _data_arquivo(a["data_ato"]),
        })

    # UMA LINHA POR PROTOCOLO — 23/10/2026. Título com dois devedores entra
    # como duas linhas da remessa e dois títulos aqui, com o MESMO protocolo
    # (35 no acervo; o E-Ofício fazia igual). No arquivo que volta, a CRA
    # recusa o lote inteiro com 9999 «MESMO PROTOCOLO… ARQUIVO NÃO FOI
    # ENVIADO» (medido no retorno de um banco, 23/10). Vai a primeira linha de
    # cada protocolo; os atos das duas continuam em `atos` e são marcados
    # juntos como informados.
    #
    # SÓ O IRMÃO COM A MESMA OCORRÊNCIA VAI JUNTO — correção de 27/10/2026.
    # O corte valia para QUALQUER segundo ato do protocolo, e `gerar` marcava
    # todos como informados: um protesto (`C`) e um cancelamento (`A`) do mesmo
    # protocolo no mesmo dia saíam só com o `C`, e o `A` ficava marcado sem ter
    # ido — a CRA continuaria dando o título por protestado. Agora o ato com
    # outra ocorrência fica FORA de `atos` (continua pendente e entra no
    # arquivo seguinte), e só o irmão do título com dois devedores, que diz a
    # mesma coisa, é marcado junto.
    ocorrencia_do_protocolo: dict[str, str] = {}
    unicos, atos_no_arquivo, adiados = [], [], []
    for a, t in zip(atos, titulos):
        prot = t["protocolo"]
        if prot not in ocorrencia_do_protocolo:
            ocorrencia_do_protocolo[prot] = t["ocorrencia"]
            unicos.append(t)
            atos_no_arquivo.append(a)
        elif ocorrencia_do_protocolo[prot] == t["ocorrencia"]:
            atos_no_arquivo.append(a)
        else:
            adiados.append(a)
    titulos = unicos
    atos = atos_no_arquivo

    # O NOME DO APRESENTANTE VEM DO CABEÇALHO DA REMESSA — correção de
    # 13/10/2026. `pt_titulos.apresentante_nome` guarda o campo 005/019 do
    # registro do título («Agência / Código do Cedente», no layout da P21), e
    # o cabeçalho do andamento saía com `h03 = 537681502381151` no lugar de
    # «BRADESCO SA» (medido no ensaio da homologação). O título continua
    # levando aquele código no lugar dele; só o cabeçalho e o rodapé mudam.
    linha = banco(con).um(
        """SELECT apresentante_nome FROM pt_remessas
            WHERE apresentante_codigo = %s AND COALESCE(apresentante_nome, '') <> ''
            ORDER BY id DESC LIMIT 1""", (codigo,))
    nome = ((linha["apresentante_nome"] if linha else "") or atos[0]["apresentante_nome"] or "").strip()
    monta = {"SDTBFORTP": PA.montar_retorno,
             "SDTBFOAND": PA.montar_andamento,
             "SDTBFOCRT": PA.montar_confirmacao}.get(tipo)
    if not monta:
        raise RetornoError(
            f"Tipo de arquivo desconhecido: {tipo!r}. Os que esta casa manda "
            f"são o retorno (SDTBFORTP), o andamento (SDTBFOAND) e a "
            f"confirmação (SDTBFOCRT).")
    arquivo = monta(
        apresentante_codigo=codigo, apresentante_nome=nome,
        dia=_data_arquivo(dia), titulos=titulos,
        numero_da_remessa=numero_da_remessa, marca=marca)
    conteudo = _como_o_eoficio_mandava(
        con, PA.escrever(arquivo, renumerar_sequencial=True), tipo, codigo,
        len(titulos))
    return {
        "tipo": tipo,
        "apresentante_codigo": codigo,
        "apresentante_nome": nome,
        "dia": str(dia)[:10],
        "marca": (titulos[0].get("reservado_566") if titulos else None),
        "atos": atos,
        # Os atos do mesmo protocolo com outra ocorrência: não entram neste
        # arquivo e continuam pendentes para o próximo.
        "adiados": adiados,
        # Atos da mesma ocorrência já aceita pela CRA: não entram no arquivo.
        "pulados": pulados,
        "arquivo": arquivo,
        "conteudo": conteudo,
        "soma_centavos": sum(int(t["saldo_a_protestar"]) for t in titulos),
        "nome_arquivo": nome_do_arquivo(tipo, codigo, dia, numero_da_remessa, con=con),
    }


def _como_o_eoficio_mandava(con: sqlite3.Connection, conteudo: str, tipo: str,
                            codigo: str, quantos: int) -> str:
    """Preenche o que o escritor deixa em branco, como o E-Ofício preenchia. SÓ CALCULA.

    MEDIDO EM 13/10/2026 nos 67 lotes de retorno de 2026 da pasta da CRA (os 67
    iguais) e nos 53 andamentos, depois que a CRA de homologação respondeu
    «9999» ao retorno do sistema — que saía com:
      - cabeçalho 68–100 em branco: o E-Ofício manda h09 = quantos títulos
        (no andamento, «0000» em 49 de 53), h10–h12 em zeros, h13 = a agência
        centralizadora da remessa (ou «000000») e h14+h15 = «043» + o IBGE;
      - rodapé 58–60 em branco: a soma é de 18 posições (58–75, layout da P21)
        e o leitor desta casa a parte em `reservado_58` + 15 — escrito em
        branco, o XML sem espaços levava um número de 15 dígitos;
      - título 508–517 (t40) e 568–577 (t50) em branco: zeros em 87 de 87.
    O leitor e o escritor (`protesto_arquivo`) não mudam: o ajuste é do que SAI.
    """
    bd = banco(con)
    ultima = bd.um(
        """SELECT conteudo FROM pt_remessas WHERE apresentante_codigo = %s
            ORDER BY id DESC LIMIT 1""", (codigo,))
    cab_remessa = ((ultima["conteudo"] if ultima else "") or "").replace("\r", "").split("\n")[0]
    agencia = cab_remessa[83:89] if len(cab_remessa) == 600 else ""
    portador = cab_remessa[89:100] if len(cab_remessa) == 600 else ""
    if not portador.strip():
        # A régua da casa (ri_ctp): `ri_codigo_ibge`, ou UF + município.
        from ri_ctp import codigo_ibge_da_casa

        def _config(chave, padrao=""):
            try:
                r = bd.um("SELECT value FROM settings WHERE key=%s",
                          (chave,))
            except sqlite3.Error:
                r = None
            return (r["value"] if r else None) or padrao
        portador = "043" + codigo_ibge_da_casa(_config)
    h09 = "0000" if tipo == "SDTBFOAND" else f"{quantos:04d}"
    saida = []
    for linha in [x for x in conteudo.replace("\r", "").split("\n") if x.strip()]:
        if linha[:1] == "0":
            linha = (linha[:67] + h09 + "0" * 12 + (agencia.strip() or "000000").ljust(6)
                     + portador.ljust(11)[:11] + linha[100:])
        elif linha[:1] == "1":
            for a, b in ((507, 517), (567, 577)):
                # NO ANDAMENTO, NENHUM DOS DOIS: t40 é «não preencher» (layout da
                # P21), e 546–596 o leitor da casa lê como UM campo de texto —
                # zeros em 568–577 se deslocam no ida e volta
                # (test_o_que_a_casa_escreve_a_casa_le_de_volta). O E-Ofício
                # mandava zeros ali (170 de 170): A CONFERIR quando o andamento
                # tiver caminho de envio e o leitor partir aquele bloco.
                if tipo == "SDTBFOAND":
                    continue
                if not linha[a:b].strip():
                    linha = linha[:a] + "0" * (b - a) + linha[b:]
        elif linha[:1] == "9" and not linha[57:60].strip():
            linha = linha[:57] + "000" + linha[60:]
        saida.append(linha)
    return "\r\n".join(saida) + "\r\n"


#: A letra do nome FEBRABAN de cada arquivo que sai.
LETRA_DO_ARQUIVO = {"SDTBFOCRT": "C", "SDTBFORTP": "R", "SDTBFOAND": "M"}


def nome_do_arquivo(tipo: str, apresentante_codigo: str, dia: str,
                    numero_da_remessa: Any = 1, *, con: sqlite3.Connection | None = None,
                    sequencia: int | None = None) -> str:
    """O nome FEBRABAN: `<letra><apresentante><DDMM>.<AA><sequência>`.

    CORREÇÃO DE 13/10/2026. Até aqui o nome era `<tipo>-<apresentante>-<AAAAMMDD>-
    <remessa>.txt`, e este comentário dizia que «o E-Ofício nomeava de outro jeito
    em cada pasta, e não há padrão a imitar». HÁ, e a CRA o exige: medido nos 125
    arquivos de 2026 da pasta da CRA (C9871007.261, M3410408.261, R1LV1809.261…),
    e é o que o manual da CRA21 e o layout do andamento da P21 descrevem. Nome fora
    dele a CRA recusa (código 0002, medido em 12/09); com ele, a confirmação
    `C2371609.263` voltou «0000» na homologação em 13/10/2026.

    `dia` é a data que o nome carrega: a da REMESSA na confirmação (a confirmação
    de `B2371609.263` é `C2371609.263`) e a do envio no andamento e no retorno.
    A sequência conta os arquivos do mesmo tipo, apresentante e dia que já
    existem — o terceiro lote do Bradesco de 16/09 é `.263`. `numero_da_remessa`
    fica na assinatura pelos chamadores antigos e não entra no nome.
    """
    letra = LETRA_DO_ARQUIVO.get(str(tipo or "").strip())
    if not letra:
        raise RetornoError(f"Tipo de arquivo desconhecido para nomear: {tipo!r}.")
    d = str(dia)[:10]
    base = f"{letra}{str(apresentante_codigo).strip()}{d[8:10]}{d[5:7]}.{d[2:4]}"
    if sequencia is None:
        sequencia = 1
        if con is not None:
            sequencia += int(banco(con).valor(
                "SELECT COUNT(*) FROM pt_retornos WHERE nome_arquivo ILIKE %s",
                (base + "_",)))
    if not 1 <= int(sequencia) <= 9:
        raise RetornoError(
            f"Já há {int(sequencia) - 1} arquivos «{base}?» — o nome FEBRABAN só "
            f"tem um dígito de sequência. Confira na Central antes de gerar outro.")
    return f"{base}{int(sequencia)}"


def hash_retorno(conteudo: str) -> str:
    """Impressao digital do arquivo que saiu."""
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ gerar


def gerar(con: sqlite3.Connection, *, apresentante_codigo: str, dia: str,
          agora: str, marca: str | None = None, numero_da_remessa: Any = 1,
          usuario: str | None = None,
          tipos: tuple[str, ...] = ("SDTBFORTP", "SDTBFOAND")) -> dict:
    """Gera o RETORNO e o ANDAMENTO e marca os atos de cada um. ESCREVE.

    OS DOIS SAEM JUNTOS, E ISSO E REGRA DA CASA. O roteiro do protesto que o
    oficial trouxe da serventia em que trabalhou diz, em maiuscula: "SEMPRE
    QUE GERAR RETORNO (FINAL), GERAR ANDAMENTO".

    E O ANDAMENTO SAI TAMBEM AO RECEBER A REMESSA — correcao do oficial em
    31/08/2026: *«sempre que recebe remessa, precisa gerar o andamento para
    atualizar a CRA sobre o andamento»*. Para isso serve `tipos`: a tela da
    remessa pede so `("SDTBFOAND",)`.

    CADA ARQUIVO LEVA OS SEUS ATOS, e ate 31/08/2026 nao era assim: os dois
    saiam do mesmo conjunto, e o andamento dizia «Apontamento» sobre um titulo
    que acabara de ser protestado. Agora o retorno leva os atos finais e o
    andamento leva os apontamentos. Ver `ATOS_POR_TIPO_DE_ARQUIVO`.

    A MARCACAO E O QUE IMPEDE MANDAR DUAS VEZES, e agora ela e DE CADA UM.
    Sao atos diferentes — o APONTAMENTO vai no andamento, o PROTESTO vai no
    retorno —, e um nao marca o outro. Sem marcacao, o mesmo protesto sai
    amanha outra vez e a Central registra dois; desfazer isso e trabalho de
    carta.

    UM ARQUIVO SEM CONTEUDO NAO DERRUBA O OUTRO. Ha dia em que chega remessa e
    nao se lavra ato final nenhum — e ha dia em que e o contrario. Recusar os
    dois porque um esta vazio faria o balcao deixar de mandar o que tem.
    """
    def grava(montado: dict, par_id: int | None) -> int:
        conteudo = montado["conteudo"]
        return int(banco(con).escrever(
            """INSERT INTO pt_retornos(tipo, par_id, apresentante_codigo,
                   apresentante_nome, dia, numero_da_remessa, marca, titulos,
                   soma_centavos, nome_arquivo, conteudo, hash_arquivo,
                   gerado_em, gerado_por)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (montado["tipo"], par_id, montado["apresentante_codigo"],
             montado["apresentante_nome"], montado["dia"],
             int(numero_da_remessa or 1), montado["marca"],
             len(montado["atos"]), montado["soma_centavos"],
             montado["nome_arquivo"], conteudo, hash_retorno(conteudo), agora,
             usuario))[0]["id"])

    # A TRAVA VEM ANTES DE `montar`, porque é ele que lê as duas coisas que
    # dois `gerar` ao mesmo tempo disputariam: os PENDENTES — o mesmo protesto
    # sairia em dois arquivos, e a Central registraria dois — e a SEQUÊNCIA DO
    # NOME, que `nome_do_arquivo` conta em `pt_retornos` (os dois sairiam com
    # o mesmo `…1`). No SQLite a escrita era uma por vez; no PostgreSQL só
    # espera quem trava com a MESMA chave. `montar` e `nome_do_arquivo` só
    # leem, e a tela que mostra antes de gerar não espera por ninguém.
    banco(con).travar("pt_retornos.nome_arquivo")
    feitos: dict[str, dict] = {}
    recusas: dict[str, str] = {}
    for qual in tipos:
        try:
            feitos[qual] = montar(con,
                                  apresentante_codigo=apresentante_codigo,
                                  dia=dia, marca=marca,
                                  numero_da_remessa=numero_da_remessa,
                                  tipo=qual)
        except RetornoError as erro:
            # Vazio nao e erro: e o dia em que nao havia aquilo para informar.
            # Guarda-se o motivo para a tela contar, em vez de calar.
            recusas[qual] = str(erro)

    if not feitos:
        raise RetornoError(" ".join(recusas.values()) or
                           "Não há nada a informar a este apresentante.")

    retorno_montado = feitos.get("SDTBFORTP")
    andamento_montado = feitos.get("SDTBFOAND")
    retorno_id = grava(retorno_montado, None) if retorno_montado else None
    andamento_id = (grava(andamento_montado, retorno_id)
                    if andamento_montado else None)
    if retorno_id and andamento_id:
        banco(con).escrever("UPDATE pt_retornos SET par_id=%s WHERE id=%s",
                            (andamento_id, retorno_id))

    # A marcacao vem por ULTIMO: enquanto ela nao acontece, `montar` continua
    # achando os mesmos atos — e e assim que o andamento sai com os mesmos
    # TITULOS do retorno, que e o que se quer.
    #
    #   MESMOS TITULOS, OCORRENCIA DIFERENTE — correcao de 31/08/2026. Este
    #   comentario dizia so «os mesmos», e o codigo copiava tambem a
    #   ocorrencia: o andamento saia dizendo `C`, `1`, `3` ou `A`. Medido nos
    #   arquivos reais, ele leva `0` (Apontamento) em 103 de 103.
    # A MARCACAO VEM POR ULTIMO, e agora e de CADA arquivo: enquanto ela nao
    # acontece, `montar` continua achando os mesmos atos — e e por isso que os
    # dois se montam antes de qualquer `UPDATE`.
    for montado, quem in ((retorno_montado, retorno_id),
                          (andamento_montado, andamento_id)):
        if not montado:
            continue
        for a in montado["atos"]:
            banco(con).escrever("UPDATE pt_atos SET retorno_id=%s WHERE id=%s",
                                (quem, int(a["ato_id"])))

    principal = retorno_montado or andamento_montado
    pulados: list[dict] = []
    vistos: set[int] = set()
    for montado in (retorno_montado, andamento_montado):
        if not montado:
            continue
        for p in montado.get("pulados") or []:
            chave = int(p["ato_id"])
            if chave in vistos:
                continue
            vistos.add(chave)
            pulados.append(p)
    return {**principal, "retorno_id": retorno_id,
            "andamento_id": andamento_id,
            "retorno": retorno_montado,
            "andamento": andamento_montado,
            "recusas": recusas,
            "pulados": pulados,
            "hash": hash_retorno(principal["conteudo"])}


def gerar_andamento(con: sqlite3.Connection, *, apresentante_codigo: str,
                    dia: str, agora: str, marca: str | None = None,
                    numero_da_remessa: Any = 1,
                    usuario: str | None = None) -> dict:
    """So o ANDAMENTO — o aviso de que os titulos entraram e foram apontados.

    Pedido do oficial em 31/08/2026: *«sempre que recebe remessa, precisa
    gerar o andamento para atualizar a CRA sobre o andamento»*.

    Ate aqui o andamento so nascia preso ao retorno, e o momento em que ele
    existe para ser mandado — logo depois do apontamento — nao tinha por onde.
    Medido: **38 dos 39** titulos recebidos por remessa aparecem num andamento,
    e ele vem na data da remessa ou depois em **38 de 38**.
    """
    return gerar(con, apresentante_codigo=apresentante_codigo, dia=dia,
                 agora=agora, marca=marca,
                 numero_da_remessa=numero_da_remessa, usuario=usuario,
                 tipos=("SDTBFOAND",))


# --------------------------------------------------------------- consultas


def retorno(con: sqlite3.Connection, retorno_id: int) -> dict | None:
    """O retorno gerado, com o arquivo inteiro. So LE."""
    return banco(con).um("SELECT * FROM pt_retornos WHERE id=%s",
                         (int(retorno_id),))


class RetornoNaoRecusadoError(RetornoError):
    """Devolver os atos só cabe a arquivo que a CRA recusou."""


def devolver_atos_do_recusado(con: sqlite3.Connection, retorno_id: int, *,
                              agora: str, usuario: str | None = None) -> dict:
    """Devolve à fila de «Esperando retorno» os atos de um arquivo RECUSADO. ESCREVE.

    A CRA RECUSOU, ENTÃO OS ATOS NÃO FORAM INFORMADOS — 28/10/2026. Seis
    retornos voltaram com 2161 «NENHUM REGISTRO FOI GRAVADO» e o sistema os
    deu por enviados. A recusa agora se grava (`protesto_cra_envio`), e os
    atos continuam presos ao arquivo recusado: fora da fila, e com a tela
    dizendo que não foram informados.

    POR QUE NÃO VOLTAM SOZINHOS. Medido na produção em 28/10/2026: os 16 atos
    dos seis recusados são PROTESTOS relavrados, e o protesto anterior do
    mesmo título (hoje desfeito) já tinha ido à CRA, aceito. A Central
    recusou porque já sabia — e devolver sozinho faria o retorno seguinte
    levá-los outra vez, e ser recusado outra vez. Quem decide é quem lê o
    motivo da recusa: corrigido o que a CRA apontou (ou conferido na Central
    que ela não sabe), o balcão devolve, e o próximo retorno os leva.

    O ARQUIVO RECUSADO FICA como foi gerado, com o teor e a recusa; perde só
    a amarração dos atos. E `protesto_cra_envio._preparar` passa a recusar
    reenviá-lo — os atos dele estarão no arquivo seguinte.

    DESDE 29/10/2026, soltar o ato não o põe na fila se a mesma ocorrência já
    foi aceita num retorno anterior — ou se está noutro arquivo ainda sem
    resposta. `continuam_de_fora` são esses: a tela avisa, em vez de dizer
    que voltaram a «Esperando retorno».

    E O ARQUIVO NÃO ENVIADO QUE LEVA ATO DESFEITO (29/10/2026) também solta
    os atos: `protesto_cra_envio._preparar` recusa enviá-lo (a CRA ouviria
    uma ocorrência sem ato que a sustente), e sem esta saída os atos VÁLIDOS
    dele ficariam presos a um arquivo que não vai. O desfeito, solto, não
    volta à fila (`pendentes` só lê ato válido); o válido volta, e o retorno
    novo o leva.
    """
    # A MESMA TRAVA DE `gerar`: devolver muda os PENDENTES que um `gerar` ao
    # mesmo tempo estaria lendo.
    banco(con).travar("pt_retornos.nome_arquivo")
    linha = retorno(con, retorno_id)
    if not linha:
        raise RetornoError(f"O arquivo #{retorno_id} não existe.")
    if str(linha.get("cra_enviado_ambiente") or "") == "EOFICIO":
        raise RetornoNaoRecusadoError(
            "Esta linha não é um arquivo: é o registro do que o sistema antigo "
            "já informou à CRA antes da virada. Não há o que devolver.")
    leva_desfeito = (not linha.get("cra_enviado_em") and banco(con).um(
        """SELECT 1 AS um FROM pt_atos
            WHERE retorno_id = %s AND COALESCE(cancelado, 0) <> 0 LIMIT 1""",
        (int(retorno_id),)) is not None)
    if linha.get("cra_enviado_em") or not (linha.get("cra_recusado_em")
                                           or leva_desfeito):
        raise RetornoNaoRecusadoError(
            f"«{linha['nome_arquivo']}» não está recusado pela CRA — "
            + ("ela o aceitou, e os atos dele estão informados."
               if linha.get("cra_enviado_em") else
               "ele ainda não teve resposta da Central. Envie-o, ou confira o "
               "erro de envio, antes de mexer nos atos."))
    atos = banco(con).ler(
        "SELECT id FROM pt_atos WHERE retorno_id = %s ORDER BY id",
        (int(retorno_id),))
    if not atos:
        raise RetornoError(
            f"Os atos de «{linha['nome_arquivo']}» já voltaram à fila — não "
            f"há nada preso a este arquivo.")
    ids = [int(a["id"]) for a in atos]
    # A AFIRMAÇÃO EXPRESSA VALE PARA UM ENVIO — 29/10/2026. O ato que voltou
    # à fila por afirmação («a CRA não tem esta ocorrência») e foi num arquivo
    # que ela recusou perde a afirmação aqui: a recusa é a Central dizendo o
    # contrário, e mandar de novo exige afirmar de novo, à vista do motivo. A
    # afirmação anterior continua na auditoria.
    banco(con).escrever(
        """UPDATE pt_atos
              SET retorno_id = NULL, cra_reenvio_afirmado_em = NULL,
                  cra_reenvio_afirmado_por = NULL, cra_reenvio_afirmacao = NULL
            WHERE retorno_id = %s""",
        (int(retorno_id),))
    marcas = {int(p["ato_id"]): p
              for p in ja_aceitas_fora_da_fila(con)}
    fora = [marcas[i] for i in ids if i in marcas]
    return {"retorno_id": int(retorno_id),
            "nome_arquivo": linha["nome_arquivo"],
            "atos": ids,
            "continuam_de_fora": fora,
            "devolvidos_em": agora, "devolvidos_por": usuario}


def _retorno_foi_aceito(linha: dict) -> bool:
    """A CRA gravou este arquivo. Recusado não é aceito. Só calcula."""
    if not str(linha.get("cra_enviado_em") or "").strip():
        return False
    if str(linha.get("cra_recusado_em") or "").strip():
        return False
    return True


def marcar_ja_informado_a_cra(con: sqlite3.Connection, ato_id: int, *,
                              retorno_id: int, motivo: str, agora: str,
                              usuario: str | None = None) -> dict:
    """Marca o ato como já informado à CRA, sem gerar arquivo. ESCREVE.

    Quem chama é o ADMIN ou o MANAGER, pela tela. O motivo e o retorno
    anterior ficam no ato; a auditoria da rota guarda o mesmo. O ato sai da
    fila. Um substituto posterior, da mesma ocorrência, também sai — a marca
    é a prova de que a Central já tem esta ocorrência.

    Não grava `retorno_id`: o ato não estava naquele arquivo, e a tela dos
    atos do arquivo mentiria.
    """
    razao = " ".join(str(motivo or "").split())
    if len(razao) < MINIMO_DO_MOTIVO:
        raise RetornoError(
            "Escreva o motivo com pelo menos dez letras: por que este ato "
            "já foi informado à CRA e não deve sair de novo.")
    # A mesma trava de `gerar`: marcar muda quem está pendente.
    banco(con).travar("pt_retornos.nome_arquivo")
    bd = banco(con)
    ato = bd.um(
        """SELECT a.id, a.tipo, a.cancelado, a.retorno_id,
                  a.cra_ja_informado_em, t.id titulo_id, t.numero_titulo,
                  t.protocolo, t.apresentante_codigo, t.origem
             FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.id = %s""", (int(ato_id),))
    if not ato:
        raise RetornoError(f"O ato {int(ato_id)} não existe.")
    if int(ato["cancelado"] or 0):
        raise RetornoError(
            f"O ato {int(ato_id)} está desfeito e já não entra no retorno à CRA.")
    if ato["retorno_id"]:
        raise RetornoError(
            f"O ato {int(ato_id)} já está amarrado ao arquivo "
            f"#{int(ato['retorno_id'])}. Não se marca de novo o que já saiu.")
    if str(ato["cra_ja_informado_em"] or "").strip():
        raise RetornoError(
            f"O ato {int(ato_id)} já foi marcado como informado à CRA em "
            f"{str(ato['cra_ja_informado_em'])[:16]}.")
    tipos_da_fila = set(ATOS_QUE_VOLTAM) | {"APONTAMENTO"}
    if ato["tipo"] not in tipos_da_fila or str(ato["origem"] or "") != "CRA":
        raise RetornoError(
            f"O ato {int(ato_id)} ({ato['tipo']}) não entra no retorno à CRA — "
            f"não há fila de onde tirá-lo.")
    linha = retorno(con, int(retorno_id))
    if not linha:
        raise RetornoError(
            f"O retorno #{int(retorno_id)} não existe. Cite o arquivo que a "
            f"CRA já aceitou.")
    if not _retorno_foi_aceito(linha):
        if str(linha.get("cra_recusado_em") or "").strip():
            codigo = str(linha.get("cra_recusa_codigo") or "").strip()
            com_codigo = f" (código {codigo})" if codigo else ""
            raise RetornoError(
                f"«{linha['nome_arquivo']}» foi recusado pela CRA{com_codigo}. "
                f"A ocorrência não foi gravada — não serve de prova de que a "
                f"Central já a recebeu.")
        raise RetornoError(
            f"«{linha['nome_arquivo']}» ainda não foi aceito pela CRA. "
            f"Cite o retorno anterior que ela aceitou (código 0000).")
    codigo_arquivo = str(linha.get("apresentante_codigo") or "").strip()
    codigo_titulo = str(ato["apresentante_codigo"] or "").strip()
    if codigo_arquivo and codigo_arquivo != codigo_titulo:
        raise RetornoError(
            f"«{linha['nome_arquivo']}» é do apresentante {codigo_arquivo}, "
            f"e este título é do {codigo_titulo}. Cite o retorno que a CRA "
            f"aceitou para este apresentante.")
    esperado = "SDTBFOAND" if ato["tipo"] == "APONTAMENTO" else "SDTBFORTP"
    if str(linha.get("tipo") or "") != esperado:
        nome_do = {"SDTBFOAND": "um andamento", "SDTBFOCRT": "uma confirmação",
                   "SDTBFORTP": "um retorno"}.get(str(linha.get("tipo") or ""),
                                                  "um arquivo")
        nome_esperado = ("um andamento" if esperado == "SDTBFOAND"
                         else "um retorno")
        raise RetornoError(
            f"«{linha['nome_arquivo']}» é {nome_do}, e este ato se informa em "
            f"{nome_esperado}. Cite o arquivo em que a CRA aceitou esta "
            f"ocorrência.")
    gravou = bd.escrever(
        """UPDATE pt_atos
              SET cra_ja_informado_em=%s, cra_ja_informado_por=%s,
                  cra_ja_informado_motivo=%s, cra_ja_informado_retorno_id=%s
            WHERE id=%s AND retorno_id IS NULL
              AND COALESCE(BTRIM(cra_ja_informado_em), '') = ''
            RETURNING id""",
        (agora, usuario, razao, int(linha["id"]), int(ato_id)))
    if not gravou:
        raise RetornoError(
            f"O ato {int(ato_id)} mudou enquanto era marcado — confira a fila "
            f"e tente de novo.")
    return {"ato_id": int(ato_id),
            "tipo": ato["tipo"],
            "titulo_id": int(ato["titulo_id"]),
            "numero_titulo": ato["numero_titulo"],
            "protocolo": ato["protocolo"],
            "apresentante_codigo": codigo_titulo,
            "retorno_id": int(linha["id"]),
            "nome_arquivo": linha["nome_arquivo"],
            "motivo": razao,
            "ocorrencia": _letra_da_ocorrencia(ato["tipo"]),
            "marcado_em": agora,
            "marcado_por": usuario}


def forcar_envio_de_protocolo_ja_informado(
        con: sqlite3.Connection, ato_id: int, *, afirmacao: Any, agora: str,
        usuario: str | None = None) -> dict:
    """Devolve à fila um ato cuja ocorrência a CRA já aceitou por outro ato
    do mesmo título ou protocolo — SÓ COM AFIRMAÇÃO EXPRESSA. ESCREVE.

    Ordem do oficial, 29/10/2026: o sistema impede mandar à CRA o protocolo
    que ela já tem; «se a escrevente insistir, só com afirmação expressa e
    log». Esta é a insistência: a afirmação (`afirmacao_valida`) fica no ato
    (`cra_reenvio_*`), e a rota grava `AFIRMACAO_EXPRESSA` na auditoria com o
    registro que esta função devolve — `regra`, `afirmacao` e `o_que_faltava`,
    que diz qual título já informou, em que arquivo e quando.

    O QUE ELA RECUSA, e por quê:
      - o ato que não está fora da fila por isto: não há o que forçar;
      - o ato que a SERVENTIA marcou à mão como já informado: quem marcou
        afirmou o contrário, e uma afirmação não desmancha a outra calada;
      - o ato já liberado: a primeira afirmação vale até o próximo arquivo.

    Ela não gera arquivo nem manda nada: o ato volta a «Esperando retorno», e
    sai no próximo retorno (ou andamento) do apresentante, como qualquer
    outro. Se a CRA recusar aquele arquivo, devolver os atos apaga a
    afirmação (`devolver_atos_do_recusado`).
    """
    # A mesma trava de `gerar`: liberar muda quem está pendente.
    banco(con).travar("pt_retornos.nome_arquivo")
    bd = banco(con)
    ato = bd.um(
        """SELECT a.id, a.tipo, a.cancelado, a.retorno_id,
                  a.cra_ja_informado_em, a.cra_ja_informado_por,
                  a.cra_ja_informado_motivo, a.cra_reenvio_afirmado_em,
                  a.cra_reenvio_afirmado_por, t.id titulo_id,
                  t.numero_titulo, t.protocolo, t.apresentante_codigo,
                  t.origem
             FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.id = %s""", (int(ato_id),))
    if not ato:
        raise RetornoError(f"O ato {int(ato_id)} não existe.")
    if int(ato["cancelado"] or 0):
        raise RetornoError(
            f"O ato {int(ato_id)} está desfeito e não vai à CRA — não há o "
            f"que mandar.")
    if ato["retorno_id"]:
        raise RetornoError(
            f"O ato {int(ato_id)} já está no arquivo #{int(ato['retorno_id'])}. "
            f"Se a CRA o recusou, devolva os atos daquele arquivo primeiro.")
    tipos_da_fila = set(ATOS_QUE_VOLTAM) | {"APONTAMENTO"}
    if ato["tipo"] not in tipos_da_fila or str(ato["origem"] or "") != "CRA":
        raise RetornoError(
            f"O ato {int(ato_id)} ({ato['tipo']}) não entra no retorno à CRA — "
            f"não há fila para onde devolvê-lo.")
    if str(ato["cra_ja_informado_em"] or "").strip():
        raise RetornoError(
            f"O ato {int(ato_id)} foi marcado à mão como já informado à CRA "
            f"(por {ato['cra_ja_informado_por'] or '—'} em "
            f"{_data_br(ato['cra_ja_informado_em'])}). Quem marcou afirmou que "
            f"a Central já tem esta ocorrência; a afirmação contrária não a "
            f"desmancha. Fale com o oficial.")
    if str(ato["cra_reenvio_afirmado_em"] or "").strip():
        raise RetornoError(
            f"O ato {int(ato_id)} já voltou à fila por afirmação expressa de "
            f"{ato['cra_reenvio_afirmado_por'] or '—'} em "
            f"{_data_br(ato['cra_reenvio_afirmado_em'])}. Ele está em "
            f"«Esperando retorno» e sai no próximo arquivo.")
    informantes = quem_ja_informou(con, [int(ato_id)]).get(int(ato_id), [])
    if not informantes:
        raise RetornoError(
            f"O ato {int(ato_id)} não está fora da fila por ocorrência já "
            f"informada — ele já está em «Esperando retorno». Não há o que "
            f"forçar.")
    letra = _letra_da_ocorrencia(ato["tipo"])
    prot = str(ato["protocolo"] or "").strip() or "sem protocolo"
    o_que_faltava = (
        f"O protocolo {prot} (apresentante "
        f"{str(ato['apresentante_codigo'] or '').strip() or '—'}) já foi "
        f"informado à CRA com a ocorrência {letra} ({ato['tipo']}), ou ela já "
        f"vai num arquivo que a CRA ainda não respondeu: "
        + "; ".join(descrever_informante(i) for i in informantes[:4])
        + ". Mandar a mesma ocorrência de novo faz a CRA recusar o arquivo "
          "inteiro (2161).")
    texto = afirmacao_valida(afirmacao)
    if texto is None:
        recado = ""
        if str(afirmacao or "").strip():
            recado = (f" A afirmação escrita é curta demais: precisa de pelo "
                      f"menos {PISO_DA_AFIRMACAO} letras além de "
                      f"«{FRASE_DA_AFIRMACAO}».")
        raise RetornoError(f"{o_que_faltava}{recado} {COMO_AFIRMAR}")
    gravou = bd.escrever(
        """UPDATE pt_atos
              SET cra_reenvio_afirmado_em=%s, cra_reenvio_afirmado_por=%s,
                  cra_reenvio_afirmacao=%s
            WHERE id=%s AND retorno_id IS NULL
              AND COALESCE(BTRIM(cra_reenvio_afirmado_em), '') = ''
              AND COALESCE(BTRIM(cra_ja_informado_em), '') = ''
            RETURNING id""",
        (agora, usuario, texto, int(ato_id)))
    if not gravou:
        raise RetornoError(
            f"O ato {int(ato_id)} mudou enquanto era liberado — confira a fila "
            f"e tente de novo.")
    return {"regra": REGRA_PROTOCOLO_JA_INFORMADO,
            "afirmacao": texto,
            "o_que_faltava": o_que_faltava,
            "ato_id": int(ato_id),
            "tipo": ato["tipo"],
            "ocorrencia": letra,
            "titulo_id": int(ato["titulo_id"]),
            "numero_titulo": ato["numero_titulo"],
            "protocolo": ato["protocolo"],
            "apresentante_codigo": ato["apresentante_codigo"],
            "informantes": informantes,
            "afirmado_em": agora,
            "afirmado_por": usuario}


def listar(con: sqlite3.Connection, limite: int = 100) -> list[dict]:
    """Os retornos gerados, do mais novo para o mais velho. So LE.

    `atos_presos` conta os atos ainda amarrados ao arquivo: no RECUSADO
    (28/10/2026) eles não foram informados, e a tela precisa dizer quantos.
    `atos_desfeitos` conta os que foram desfeitos depois de o arquivo ser
    gerado (29/10/2026): o arquivo não enviado que os leva não vai à CRA.
    """
    return banco(con).ler(
        """SELECT r.id, r.tipo, r.par_id, r.apresentante_codigo,
                  r.apresentante_nome, r.dia, r.numero_da_remessa, r.titulos,
                  r.soma_centavos, r.nome_arquivo, r.hash_arquivo, r.gerado_em,
                  r.gerado_por, r.cra_enviado_em, r.cra_enviado_ambiente,
                  r.cra_envio_erro, r.cra_enviado_por, r.cra_recusado_em,
                  r.cra_recusa_codigo, r.cra_recusa_motivo,
                  (SELECT COUNT(*) FROM pt_atos a
                    WHERE a.retorno_id = r.id) AS atos_presos,
                  (SELECT COUNT(*) FROM pt_atos a
                    WHERE a.retorno_id = r.id
                      AND COALESCE(a.cancelado, 0) <> 0) AS atos_desfeitos
             FROM pt_retornos r ORDER BY r.id DESC LIMIT %s""",
        (int(limite),))


def atos_do_retorno(con: sqlite3.Connection, retorno_id: int) -> list[dict]:
    """Que atos entraram naquele retorno. So LE."""
    return banco(con).ler(
        """SELECT a.id ato_id, a.tipo, a.data_ato, t.numero_titulo,
                  t.nosso_numero, t.protocolo, t.saldo_centavos
             FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.retorno_id = %s ORDER BY a.id""", (int(retorno_id),))


def informados_e_desfeitos(con: sqlite3.Connection, *,
                           apresentante_codigo: str | None = None
                           ) -> list[dict]:
    """Os atos que entraram num arquivo à CRA e hoje estão DESFEITOS. Só LÊ.

    O QUE A CENTRAL OUVIU NÃO É O QUE O LIVRO DIZ, e a tela tem de mostrar
    isso. Medido na produção em 28/10/2026: **19** atos com `retorno_id` e
    `cancelado = 1`, todos em retornos já enviados à CRA de produção — 16
    protestos tornados sem efeito, 2 cancelamentos e 1 pagamento desfeitos
    porque o selo não saiu. Em 17 deles há outro ato válido do mesmo tipo no
    título; em 2 (o cancelamento do título 1353 e um pagamento) não há, e ali
    a Central afirma o que não aconteceu.

    NÃO SE REENVIA NADA SOZINHO. O contrato da CRA não tem ocorrência medida
    para «desfaça o que eu disse», e qual providência cabe (carta, contato
    com a Central, novo ato) é decisão do oficial. Esta função só junta os
    fatos — o arquivo em que o ato foi, se ele já subiu, o motivo de ter sido
    desfeito e se o título tem outro ato válido do mesmo tipo — para a tela
    avisar. Os arquivos da virada (o E-Ofício) entram também: o que ele
    informou a Central ouviu do mesmo jeito.
    """
    onde = ["a.retorno_id IS NOT NULL", "COALESCE(a.cancelado, 0) = 1"]
    params: list[Any] = []
    if apresentante_codigo:
        onde.append("t.apresentante_codigo = %s")
        params.append(str(apresentante_codigo).strip())
    return banco(con).ler(
        f"""SELECT a.id ato_id, a.tipo, a.data_ato, a.motivo_cancelamento,
                   a.retorno_id, t.id titulo_id, t.numero_titulo,
                   t.protocolo, t.situacao, t.apresentante_codigo,
                   r.tipo tipo_arquivo, r.nome_arquivo, r.gerado_em,
                   r.cra_enviado_em, r.cra_enviado_ambiente,
                   (SELECT v.id FROM pt_atos v
                     WHERE v.titulo_id = a.titulo_id AND v.tipo = a.tipo
                       AND COALESCE(v.cancelado, 0) = 0
                     ORDER BY v.id DESC LIMIT 1) ato_valido_id,
                   (SELECT v.retorno_id FROM pt_atos v
                     WHERE v.titulo_id = a.titulo_id AND v.tipo = a.tipo
                       AND COALESCE(v.cancelado, 0) = 0
                     ORDER BY v.id DESC LIMIT 1) ato_valido_retorno_id
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
              LEFT JOIN pt_retornos r ON r.id = a.retorno_id
             WHERE {' AND '.join(onde)}
             ORDER BY a.id DESC""",
        params)


# ------------------------------- protocolo com mais de um título: a conferência


def _situacao_do_arquivo(linha: dict) -> str:
    """ACEITO, RECUSADO, AGUARDANDO ou EOFICIO — a do arquivo do ato. Só calcula."""
    if str(linha.get("cra_enviado_ambiente") or "") == "EOFICIO":
        return "EOFICIO"
    if str(linha.get("cra_enviado_em") or "").strip():
        return "ACEITO"
    if str(linha.get("cra_recusado_em") or "").strip():
        return "RECUSADO"
    return "AGUARDANDO"


def _estado_do_ato(linha: dict, fora: set[int]) -> tuple[str, str]:
    """O que este ato já disse à CRA, em código e em frase. Só calcula."""
    desfeito = int(linha.get("desfeito") or 0)
    arquivo = linha.get("nome_arquivo") or f"arquivo #{linha.get('retorno_id')}"
    if linha.get("retorno_id"):
        sit = _situacao_do_arquivo(linha)
        antes = "desfeito depois — " if desfeito else ""
        if sit == "EOFICIO":
            return ("INFORMADO",
                    f"{antes}informado pelo sistema antigo antes da virada")
        if sit == "ACEITO":
            return ("INFORMADO", f"{antes}aceito pela CRA em "
                    f"{_data_br(linha.get('cra_enviado_em'))} — {arquivo}")
        if sit == "RECUSADO":
            codigo = str(linha.get("cra_recusa_codigo") or "").strip()
            return ("RECUSADO", f"{antes}recusado pela CRA"
                    + (f" (código {codigo})" if codigo else "")
                    + f" — {arquivo}; NÃO foi informado")
        return ("AGUARDANDO",
                f"{antes}no arquivo {arquivo}, ainda sem resposta da CRA")
    if desfeito:
        return ("DESFEITO", "desfeito sem ter ido à CRA")
    if str(linha.get("cra_ja_informado_em") or "").strip():
        return ("MARCADO", "marcado à mão como já informado"
                + (f" ({linha['arquivo_marcado']})"
                   if linha.get("arquivo_marcado") else ""))
    if str(linha.get("cra_reenvio_afirmado_em") or "").strip():
        return ("LIBERADO",
                f"liberado por afirmação expressa de "
                f"{linha.get('cra_reenvio_afirmado_por') or '—'} em "
                f"{_data_br(linha.get('cra_reenvio_afirmado_em'))} — vai no "
                f"próximo arquivo")
    if int(linha["ato_id"]) in fora:
        return ("JA_INFORMADO",
                "fora da fila: esta ocorrência já foi à CRA (aceita ou ainda "
                "sem resposta) por este título ou pelo outro título do "
                "protocolo")
    return ("NA_FILA", "em «Esperando retorno»")


def protocolos_com_mais_de_um_titulo(
        con: sqlite3.Connection, *,
        apresentante_codigo: str | None = None) -> dict:
    """Os protocolos com mais de um título vindo da CRA, e o que cada título
    já disse a ela. Só LÊ — a conferência do oficial.

    POR QUE EXISTE — 29/10/2026. A CRA conhece o PROTOCOLO; esta casa, o
    título. A CDA com dois devedores vira dois títulos com o mesmo protocolo,
    e o que um deles informa vale para os dois lá do outro lado. Medido na
    produção nesse dia (só leitura): **34 protocolos com dois títulos**, 33
    da PGFN (901) — 27 de 2025 e 7 de 2026 —, e um deles, o 2610070011, já
    custou um arquivo inteiro recusado (o R9012810.261, 2161).

    O QUE ELA MOSTRA, por protocolo: os títulos, cada ato que vai à CRA
    (apontamento e atos finais) com o arquivo em que foi e a resposta da
    Central, e três sinais —
      - `repeticoes`: a mesma ocorrência em dois arquivos (o que a Central
        recusa quando o primeiro foi aceito);
      - `situacoes_divergentes`: os títulos do protocolo em situações
        diferentes, quando a Central guarda uma ocorrência só;
      - quantos atos estão fora da fila, presos em arquivo recusado ou
        liberados por afirmação expressa.

    ELA NÃO DECIDE NADA. Qual título vale na Central, e se cabe carta ou
    contato com a CRA, é decisão do oficial; ela junta os fatos.
    """
    onde = ["t.origem = 'CRA'",
            "NULLIF(BTRIM(COALESCE(t.protocolo, '')), '') IS NOT NULL"]
    params: list[Any] = []
    if apresentante_codigo:
        onde.append("COALESCE(t.apresentante_codigo, '') = %s")
        params.append(str(apresentante_codigo).strip())
    tipos = ("APONTAMENTO", *ATOS_QUE_VOLTAM)
    linhas = banco(con).ler(
        f"""WITH dup AS (
              SELECT COALESCE(t.apresentante_codigo, '') ap,
                     BTRIM(t.protocolo) prot
                FROM pt_titulos t
               WHERE {' AND '.join(onde)}
               GROUP BY COALESCE(t.apresentante_codigo, ''), BTRIM(t.protocolo)
              HAVING COUNT(*) > 1)
            SELECT dup.ap apresentante_codigo, dup.prot protocolo,
                   t.id titulo_id, t.numero_titulo, t.situacao,
                   a.id ato_id, a.tipo, a.data_ato,
                   COALESCE(a.cancelado, 0) desfeito, a.retorno_id,
                   a.cra_ja_informado_em, a.cra_reenvio_afirmado_em,
                   a.cra_reenvio_afirmado_por,
                   r.nome_arquivo, r.cra_enviado_em, r.cra_enviado_ambiente,
                   r.cra_recusado_em, r.cra_recusa_codigo,
                   rm.nome_arquivo arquivo_marcado
              FROM dup
              JOIN pt_titulos t
                ON t.origem = 'CRA'
               AND COALESCE(t.apresentante_codigo, '') = dup.ap
               AND BTRIM(t.protocolo) = dup.prot
              LEFT JOIN pt_atos a
                ON a.titulo_id = t.id
               AND a.tipo IN ({','.join(['%s'] * len(tipos))})
              LEFT JOIN pt_retornos r ON r.id = a.retorno_id
              LEFT JOIN pt_retornos rm ON rm.id = a.cra_ja_informado_retorno_id
             ORDER BY dup.prot DESC, dup.ap, t.id, a.id""",
        [*params, *tipos])
    fora = {int(p["ato_id"]) for p in ja_aceitas_fora_da_fila(con)}

    protocolos: dict[tuple[str, str], dict] = {}
    for linha in linhas:
        chave = (linha["apresentante_codigo"], linha["protocolo"])
        p = protocolos.setdefault(chave, {
            "apresentante_codigo": linha["apresentante_codigo"],
            "protocolo": linha["protocolo"],
            "titulos": {}, "arquivos_por_tipo": {}})
        tit = p["titulos"].setdefault(int(linha["titulo_id"]), {
            "titulo_id": int(linha["titulo_id"]),
            "numero_titulo": linha["numero_titulo"],
            "situacao": linha["situacao"], "atos": []})
        if linha["ato_id"] is None:
            continue
        codigo, frase = _estado_do_ato(linha, fora)
        tit["atos"].append({
            "ato_id": int(linha["ato_id"]), "tipo": linha["tipo"],
            "ocorrencia": _letra_da_ocorrencia(linha["tipo"]),
            "data_ato": linha["data_ato"],
            "desfeito": bool(int(linha["desfeito"] or 0)),
            "estado": codigo, "frase": frase,
            "retorno_id": linha["retorno_id"],
            "nome_arquivo": linha["nome_arquivo"]})
        if linha["retorno_id"]:
            p["arquivos_por_tipo"].setdefault(linha["tipo"], {})[
                int(linha["retorno_id"])] = {
                    "nome_arquivo": linha["nome_arquivo"],
                    "situacao": _situacao_do_arquivo(linha),
                    "codigo": linha["cra_recusa_codigo"]}

    saida = []
    for p in protocolos.values():
        p["titulos"] = list(p["titulos"].values())
        # REPETIÇÃO é a mesma letra num arquivo DEPOIS de outro que a segura
        # (aceito, sistema antigo ou ainda sem resposta). Recusado seguido de
        # aceito não é repetição — é o conserto que deu certo.
        p["repeticoes"] = [
            {"tipo": tipo, "ocorrencia": _letra_da_ocorrencia(tipo),
             "arquivos": [arquivos[k] for k in sorted(arquivos)]}
            for tipo, arquivos in sorted(p.pop("arquivos_por_tipo").items())
            if _repete_o_que_ja_foi_aceito(arquivos)]
        situacoes = sorted({str(t["situacao"] or "") for t in p["titulos"]})
        p["situacoes"] = situacoes
        p["situacoes_divergentes"] = len(situacoes) > 1
        estados = [a["estado"] for t in p["titulos"] for a in t["atos"]]
        p["fora_da_fila"] = estados.count("JA_INFORMADO")
        p["presos_em_recusado"] = estados.count("RECUSADO")
        p["liberados"] = estados.count("LIBERADO")
        p["precisa_olhar"] = bool(
            p["repeticoes"] or p["situacoes_divergentes"] or p["fora_da_fila"]
            or p["presos_em_recusado"] or p["liberados"])
        saida.append(p)
    saida.sort(key=lambda p: (not p["precisa_olhar"],
                              _ordem_decrescente(p["protocolo"]),
                              p["apresentante_codigo"]))
    return {
        "protocolos": saida,
        "total": len(saida),
        "titulos": sum(len(p["titulos"]) for p in saida),
        "com_repeticao": sum(1 for p in saida if p["repeticoes"]),
        "divergentes": sum(1 for p in saida if p["situacoes_divergentes"]),
        "com_ato_fora_da_fila": sum(1 for p in saida if p["fora_da_fila"]),
        "com_recusado": sum(1 for p in saida if p["presos_em_recusado"]),
        "apresentante_codigo": str(apresentante_codigo or "").strip(),
    }


def _repete_o_que_ja_foi_aceito(arquivos: dict[int, dict]) -> bool:
    """Há arquivo gerado depois do primeiro que segura a ocorrência — o que a
    Central aceitou, o que o sistema antigo informou, ou o que ainda não teve
    resposta (decisão do oficial, 29/10/2026)? A ordem é a do `id`. Recusado
    não segura. Só calcula."""
    seguram = [k for k, a in arquivos.items() if a["situacao"] != "RECUSADO"]
    return bool(seguram) and any(k > min(seguram) for k in arquivos)


def _ordem_decrescente(texto: Any) -> tuple:
    """Chave que põe o protocolo mais NOVO primeiro: `AAMMDD` + sequencial,
    só dígitos; o que não for número vai ao fim. Só calcula."""
    s = str(texto or "").strip()
    return (0, -int(s)) if s.isdigit() else (1, s)


# ------------------------------------------ o que o E-Ofício já mandou à CRA
#
# A VIRADA DO PROTESTO (13/10/2026). Os atos trazidos do E-Ofício não têm
# `retorno_id`, e `pendentes()` os oferecia de volta: a tela da CRA mandaria
# reenviar mais de mil atos que o E-Ofício já informou. Marcar TODOS seria o
# erro do outro lado — o que o E-Ofício lavrou e ainda não retornou ficaria
# calado. Marca-se só o que aparece nos ARQUIVOS que ele gerou (a pasta da
# CRA), e o que é anterior a esses arquivos todos.
NOME_DO_INFORMADO_PELO_EOFICIO = {
    "SDTBFORTP": "E-OFICIO-RETORNOS-ANTES-DA-VIRADA",
    "SDTBFOAND": "E-OFICIO-ANDAMENTOS-ANTES-DA-VIRADA",
}
#: Que ocorrência do retorno prova cada ato final (`protesto_cra.OCORRENCIAS`;
#: «C» é o protesto como o E-Ofício o escrevia, 1.106 de 1.107 no acervo).
OCORRENCIA_QUE_PROVA = {"PROTESTO": {"2", "C"}, "PAGAMENTO": {"1"},
                        "DESISTENCIA": {"3"}, "CANCELAMENTO": {"A"}}


def _registro_do_eoficio(con: sqlite3.Connection, tipo: str, agora: str) -> int:
    nome = NOME_DO_INFORMADO_PELO_EOFICIO[tipo]
    bd = banco(con)
    linha = bd.um("SELECT id FROM pt_retornos WHERE nome_arquivo=%s",
                  (nome,))
    if linha:
        return int(linha["id"])
    return int(bd.escrever(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, apresentante_nome,
               dia, numero_da_remessa, titulos, soma_centavos, nome_arquivo,
               conteudo, gerado_em, gerado_por, cra_enviado_em,
               cra_enviado_ambiente, cra_envio_resumo)
           VALUES (%s, '', 'E-Ofício', %s, 1, 0, 0, %s, '', %s, 'virada do protesto',
                   %s, 'EOFICIO', %s)
           RETURNING id""",
        (tipo, agora[:10], nome, agora, agora,
         "Não é arquivo deste sistema: marca os atos que o E-Ofício já "
         "informou à CRA antes da virada (13/10/2026)."))[0]["id"])


def marcar_o_que_o_eoficio_ja_informou(con: sqlite3.Connection, fluxo: dict,
                                       *, agora: str) -> dict:
    """Marca como informados os atos do E-Ofício que os arquivos provam. ESCREVE.

    `fluxo` é `gestor_protesto.ler_fluxo_da_cra` da pasta da CRA. Ato final
    entra se o retorno do mesmo protocolo traz a ocorrência dele; apontamento
    entra se o título aparece em qualquer arquivo devolvido. Ato anterior ao
    primeiro arquivo da pasta entra também: o E-Ofício era o único sistema, e
    ato pendente de retorno há mais tempo que a pasta alcança não existe. O que
    sobra fica pendente — e sai no primeiro retorno do Cartório Gestão.
    """
    datas = [r["enviado"] for v in fluxo.get("retorno", {}).values() for r in v
             if r.get("enviado")]
    desde = min(datas).isoformat() if datas else None
    contagem = {"retorno": 0, "andamento": 0, "anterior_aos_arquivos": 0,
                "fica_pendente": 0, "desde": desde}
    reg_ret = reg_and = None
    # A MESMA TRAVA DE `gerar`, e antes da lista: os dois marcam os mesmos
    # atos (`retorno_id IS NULL`), e `_registro_do_eoficio` confere se a linha
    # da virada já existe antes de inserir — duas passadas ao mesmo tempo
    # gravariam duas.
    banco(con).travar("pt_retornos.nome_arquivo")
    linhas = banco(con).ler(
        """SELECT a.id, a.tipo, a.data_ato, t.protocolo, t.apresentante_codigo,
                  t.nosso_numero, t.numero_titulo
             FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.retorno_id IS NULL AND a.origem = 'EOFICIO'
              AND t.origem IN ('CRA', 'CENPROT')
            ORDER BY a.id""")
    for a in linhas:
        tipo, prot = a["tipo"], str(a["protocolo"] or "").strip()
        if tipo == "APONTAMENTO":
            apres = str(a["apresentante_codigo"] or "").strip()
            provado = ((apres, str(a["nosso_numero"] or "").strip())
                       in fluxo.get("respondido", set())
                       or (apres, str(a["numero_titulo"] or "").strip())
                       in fluxo.get("respondido", set()))
            arquivo = "SDTBFOAND"
        elif tipo in OCORRENCIA_QUE_PROVA:
            provado = any(str(r.get("ocorrencia") or "").upper()
                          in OCORRENCIA_QUE_PROVA[tipo]
                          for r in fluxo.get("retorno", {}).get(prot, []))
            arquivo = "SDTBFORTP"
        else:
            continue
        antigo = bool(desde and str(a["data_ato"] or "")[:10] < desde)
        if not (provado or antigo):
            contagem["fica_pendente"] += 1
            continue
        if arquivo == "SDTBFORTP":
            reg_ret = reg_ret or _registro_do_eoficio(con, arquivo, agora)
            alvo = reg_ret
            contagem["retorno"] += 1
        else:
            reg_and = reg_and or _registro_do_eoficio(con, arquivo, agora)
            alvo = reg_and
            contagem["andamento"] += 1
        if antigo and not provado:
            contagem["anterior_aos_arquivos"] += 1
        banco(con).escrever("UPDATE pt_atos SET retorno_id=%s WHERE id=%s",
                            (alvo, a["id"]))
    return contagem
