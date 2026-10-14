"""O SELO DO ATO DO LIVRO 3 — o Registro Auxiliar sela como o Livro 2.

    «fiz a averbacao da 1243 e nao emitiu selo, deixe o livro 3 com as mesmas
     ferramentas do livro 2» — o oficial, 20/09/2026

**POR QUE NAO EMITIU, medido no banco vivo antes de escrever uma linha.** A
rota que averba no Livro 3 chamava `_selar_se_pedido`, que **so grava o numero
que o escrevente digitou** — ela nunca pede selo ao aparelho. O Livro 2 tem
duas portas para o selo (a automatica, dentro da lavratura, e o botao «selar
este ato», para o ato que ja nasceu sem); o Livro 3 **nao tinha nenhuma**.
Medido: a AV-01 do registro 1.243, lavrada em 20/09/2026 as 14h33, com
`selo`, `servico_codigo` e `lancamento_id` todos nulos, e a auditoria daquele
minuto com um `RA_ATO` e mais nada — **nenhuma tentativa de selo saiu daqui**.


O CAMINHO E O ENVELOPE SAO MEDIDOS, E NAO ESCOLHIDOS POR PARECENCA

O E-Oficio **selou atos do Livro 3**, e a medicao no acervo (20/09/2026) diz
exatamente como — 17 envelopes da familia `ato-declarado` cuja
`descricaoNatureza` nomeia o Livro 3-AUX:

| o ato | caminho | item | `matricula` | `livro` | `registroAverbacao` |
|---|---|---|---|---|---|
| **registro** (5) | `ato-declarado/com-valor` | **16.9** | o numero do registro (`1550`) | `3` | `0` |
| **averbacao** (2) | `ato-declarado/sem-valor` | **16.22.2** | `AV - 1 do Registro 1332` | `3` | `0` |

**E ELE E O MESMO ENVELOPE DO ATO DO LIVRO 2** — as cinco chaves de fora e as
onze de `dadosSelo` batem uma a uma, `naturezaTitulo` e `126.0` nos 17, o
`com-valor` leva `baseCalculo` e o `sem-valor` leva `quantidade: 1`. Por isso
este modulo **nao monta envelope nenhum**: ele calcula os tres valores que
mudam e chama `ato_selado.envelope_do_ato_do_ri`. Dois montadores do mesmo
envelope divergiriam no primeiro conserto, e o que o Tribunal recebesse
deixaria de ser o que a casa mandou.

**AS DUAS COISAS QUE MUDAM, E ELAS NAO SE ADIVINHAM:**

1. **`matricula` nao e um numero no Livro 3.** Na averbacao a casa escreveu a
   frase `AV - 1 do Registro 1332` — o campo se chama matricula e carrega a
   identificacao do ato. Mandar so `1332` diria ao Tribunal que o selo e do
   registro, e nao da averbacao dele.
2. **`registroAverbacao` e `'0'`, sempre.** No Livro 2 ele e o numero do ato;
   nos sete atos de Livro 3 que a casa selou ele e zero — inclusive nos que
   tem AV-1. Nao se inventa numero em campo que a casa zerou.

**O QUE ESTE MODULO NAO FAZ:** nao lavra, nao numera, nao cobra e nao decide.
Ele diz o que falta para selar e monta o pedido; quem fala com a rede e
`ato_selado.selar_o_ato_lavrado`, e quem decide e quem assina.
"""
from __future__ import annotations

import sqlite3
from typing import Any

import ato_selado as AS

# O LIVRO QUE VAI DENTRO DO SELO. **`'3'`, e nao o volume da matricula** — no
# Livro 2 este campo leva `2-Q`, `2S`; nos envelopes de Livro 3 medidos ele
# leva `3` em 5 dos 7 (um veio `-` e outro `2S`, e esses dois sao a perna do
# Livro 2 da mesma operacao: a hipoteca sobre a matricula).
LIVRO_DO_REGISTRO_AUXILIAR = "3"

# **ZERO, E MEDIDO.** Ver o item 2 do cabecalho. E texto, e nao inteiro: o
# acervo traz `'0'` entre aspas nos sete.
REGISTRO_AVERBACAO_DO_LIVRO_3 = "0"

# OS ITENS QUE A CASA USOU, por tipo de ato, na ordem de uso. A tela os
# oferece; ela **nao** escolhe sozinha, porque o item nao sai do tipo do ato —
# e a mesma regra do Livro 2, onde o mesmo «sem valor» saiu com seis itens
# diferentes nos 120 envelopes.
ITENS_MEDIDOS: dict[str, tuple[tuple[str, str], ...]] = {
    "R": (("16.9", ("Registro de título — o item dos 5 registros de cédula "
                    "que esta casa selou no Livro 3")),),
    "AV": (("16.22.2", ("Averbação sem valor declarado — o item das 2 "
                        "averbações que esta casa selou no Livro 3 (aditivo "
                        "e baixa de hipoteca)")),),
}


class RaSeloError(ValueError):
    """Erro de regra, com frase pronta para o balcão — vira `flash(danger)`."""


def centavos_do_valor(texto: Any) -> int | None:
    """`'1.234,56'` -> `123456`. **Campo vazio é `None`, e não zero.**

    Zero não é «não informado»: é o valor declarado que escolhe entre
    `com-valor` e `sem-valor`, e um zero inventado mandaria toda averbação
    pelo caminho errado sem ninguém ver. Mora aqui, e não nas duas telas que
    a usam, porque duas leituras do mesmo campo divergem no primeiro conserto.
    """
    limpo = "".join(c for c in str(texto or "") if c.isdigit() or c in ",.")
    if not limpo:
        return None
    limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return round(float(limpo) * 100)
    except ValueError:
        return None


def referencia_do_ato(registro_numero: Any, tipo: Any, numero: Any) -> str:
    """O que vai no campo `matricula` do envelope. **Medido, não inventado.**

    `AV - 1 do Registro 1332` na averbação e `1550` no registro — as duas
    formas saíram do acervo, e a primeira é uma frase de propósito: o campo
    identifica o ATO, e no Livro 3 o ato tem número próprio dentro do registro.
    """
    registro = str(registro_numero or "").strip()
    if not registro:
        raise RaSeloError("O selo do Livro 3 não sai sem o número do registro.")
    if str(tipo or "").strip().upper() == "AV":
        return f"AV - {str(numero or '').strip()} do Registro {registro}"
    return registro


def itens_do_tipo(tipo: Any) -> tuple[tuple[str, str], ...]:
    """Os itens medidos para aquele tipo de ato. A tela os oferece."""
    return ITENS_MEDIDOS.get(str(tipo or "").strip().upper(), ())


def itens_disponiveis(con) -> list[tuple[str, str]]:
    """Itens 16.* com preço na tabela vigente, inclusive 16.45.x.

    O 16.45 é cabeçalho por faixa: o código selável é o subitem adequado
    ao valor, não o cabeçalho sem preço. Não limita a busca aos primeiros 30.
    """
    try:
        linhas = con.execute(
            """SELECT s.codigo_tj, MAX(s.descricao) descricao
                 FROM cx_servicos s
                 JOIN cx_servico_valores v ON v.servico=s.codigo
                 JOIN cx_vigencias g ON g.codigo=v.vigencia AND g.vigente=1
                WHERE s.ativo=1 AND s.codigo_tj LIKE '16.%'
                  AND v.total IS NOT NULL
                GROUP BY s.codigo_tj
                ORDER BY s.codigo_tj""").fetchall()
    except sqlite3.OperationalError:  # instalação ainda sem tabela importada
        linhas = []
    return [(str(r[0]), str(r[1] or "")) for r in linhas]


def encerrar_prenotacao_apos_arquivamento(con, registro_id: int) -> dict | None:
    """Encerra somente a prenotação RI aberta associada ao registro auxiliar.

    A identificação é o número gravado em ra_registros.prenotacao. Sem
    correspondência inequívoca, não altera nenhum protocolo.
    """
    r = con.execute("SELECT prenotacao FROM ra_registros WHERE id=?",
                    (int(registro_id),)).fetchone()
    bruto = str((r[0] if r else None) or "").strip()
    if not bruto:
        return None
    dig = "".join(c for c in bruto if c.isdigit())
    linhas = con.execute(
        """SELECT id, numero, situacao FROM ri_protocolos
            WHERE CAST(numero AS TEXT)=?
               OR REPLACE(CAST(numero AS TEXT), '.', '')=?
            ORDER BY id DESC LIMIT 2""", (bruto, dig or bruto)).fetchall()
    if not linhas:
        return {"achou": False, "numero": bruto}
    if len(linhas) > 1:
        return {"ambiguo": True, "numero": bruto}
    p = linhas[0]
    if p["situacao"] != "ABERTO":
        return {"achou": True, "numero": p["numero"],
                "situacao": p["situacao"], "ja_encerrada": True}
    con.execute(
        """UPDATE ri_protocolos
              SET situacao='ENCERRADO',
                  situacao_anterior=COALESCE(situacao_anterior, situacao)
            WHERE id=? AND situacao='ABERTO'""", (int(p["id"]),))
    return {"achou": True, "numero": p["numero"], "encerrou": True,
            "protocolo_id": int(p["id"])}


def falta_para_selar(*, natureza: Any, codigo_tj: Any, versao_tabela: Any,
                     partes: Any = None, isento: bool = False,
                     motivo_isencao: Any = None,
                     protocolo: Any = None) -> list[str]:
    """O que impede este ato de ser selado. **Recusa no balcão, e não na rede.**

    A mesma régua do Livro 2: o que a tela sabe se recusa antes de o pedido
    sair, porque a resposta da rede chega mastigada e o escrevente está com o
    cliente na frente.

    **A FALTA DAS PARTES ENTROU AQUI EM 21/09/2026, E EU HAVIA ESCRITO O
    CONTRÁRIO.** Ao construir isto em 20/09 eu deixei em comentário que «a
    lista vazia não impede o selo, e o envelope do Livro 2 já manda
    `parteAto: []`». Ele manda — **e o aparelho recusa**: relato do oficial no
    dia seguinte, ao tentar selar a AV-01 do registro 1.243, com a frase do
    selador inteira, «Os nomes das partes devem ser informados». É a mesma
    recusa que derrubou o selo da AV-05 da matrícula 3.110 em 15/09.

    Dedução minha contra medição do balcão: ganha o balcão.
    """
    falta: list[str] = []
    if not [p for p in (partes or []) if str(p.get("nome") or "").strip()]:
        falta.append(
            "Este registro não tem partes informadas, e o selo exige os nomes "
            "— o aparelho recusa com «Os nomes das partes devem ser "
            "informados». Cadastre-as no quadro «Partes», na própria ficha.")
    if not str(natureza or "").strip():
        falta.append("Informe a natureza do título — o selo a exige, e ela é o "
                     "texto que descreve o ato dentro dele.")
    if not str(codigo_tj or "").strip():
        falta.append("Escolha o item da tabela de custas — ele não sai do tipo "
                     "do ato, e por isso a tela pergunta.")
    if not str(versao_tabela or "").strip():
        falta.append("Falta dizer de que data é a tabela de custas em vigor, "
                     "em Administrativo → Configurações.")
    if isento and not str(motivo_isencao or "").strip():
        falta.append("Ato gratuito precisa do motivo escrito — é ele que sai "
                     "dentro do selo e que a correição lê.")

    # PROTOCOLO 1..50 — medido 28/09/2026 no registro 1.651 (ato 19): prenotação
    # vazia mandava `protocolo: ""` ao Tribunal, que recusou com «O tamanho do
    # campo "protocolo" deve estar entre 1 e 50». Recusa no balcão, antes da rede.
    proto = str(protocolo or "").strip()
    if not proto:
        falta.append(
            "Informe a prenotação (nº do protocolo) na ficha do registro — o "
            "Tribunal exige o campo protocolo entre 1 e 50 caracteres; sem ele "
            "o selo volta com essa recusa.")
    elif len(proto) > 50:
        falta.append(
            f"A prenotação tem {len(proto)} caracteres; o Tribunal limita o "
            "campo protocolo a 50. Encurte o texto na ficha (ex.: só o número).")
    return falta


def caminho_do_ato(base_calculo_centavos: Any = None) -> str:
    """Com valor declarado ou sem — **e quem decide é o valor, não o tipo**.

    É a mesma função do Livro 2, e de propósito: há averbação com valor e
    registro sem. Os sete envelopes medidos concordam — os 5 registros de
    cédula foram por `com-valor`, com a base em reais, e as 2 averbações por
    `sem-valor`.
    """
    return AS.caminho_do_ato_do_ri((base_calculo_centavos or 0) / 100.0)


def envelope_do_ato(*, registro_numero: Any, tipo: Any, numero: Any,
                    escrevente: Any, versao_tabela: Any, natureza: Any,
                    codigo_tj: Any, protocolo: Any = None,
                    base_calculo_centavos: Any = None, partes: Any = None,
                    isento: bool = False, motivo_isencao: Any = None) -> dict:
    """O pedido de selo do ato do Livro 3. **Só calcula: não fala com a rede.**

    Ele **delega a montagem** a `ato_selado.envelope_do_ato_do_ri` — ver o
    cabeçalho: o envelope é o mesmo, e escrever um segundo aqui seria criar a
    segunda versão do que vai ao Tribunal.
    """
    return AS.envelope_do_ato_do_ri(
        matricula=referencia_do_ato(registro_numero, tipo, numero),
        # `registroAverbacao` VAI ZERADO — medido nos sete. O número do ato
        # já está dentro da `matricula`, na frase.
        numero_do_ato=REGISTRO_AVERBACAO_DO_LIVRO_3,
        escrevente=escrevente, versao_tabela=versao_tabela,
        descricao_natureza=natureza, livro=LIVRO_DO_REGISTRO_AUXILIAR,
        codigo_tj=codigo_tj, protocolo=protocolo,
        # EM REAIS, e não em centavos: a casa guarda centavos inteiros e o
        # selador quer o decimal. A conversão mora aqui, num lugar só.
        base_calculo=(base_calculo_centavos or 0) / 100.0,
        partes=partes, isento=isento, motivo_isencao=motivo_isencao)


# ================================================ o selo da CERTIDAO do Livro 3
#
# **O CAMINHO E O DA CERTIDAO DO IMOVEL, E ISSO E MEDIDO** — 21/09/2026.
#
#   As **9** certidoes do Livro 3 que esta casa emitiu (`LivroAuxiliarCertidao`
#   no acervo) tem, todas as 9, selo de `/selo/imovel/certidao` no protocolo
#   geral delas — prefixo `CERIMV`. A amarracao e pelo PROTOCOLO, e nao pela
#   linha da certidao: a coluna `Selado` esta **vazia nas 9**. Em duas delas —
#   os protocolos `2020.06.48` e `2020.07.35` — **nao ha outro caminho nenhum**
#   no protocolo inteiro, e e isso que fecha a leitura: nao ha um segundo
#   caminho de certidao a que aquele selo pudesse pertencer.
#
# **O ENVELOPE E O DO RI, E NAO UM PARECIDO** (`envelope_da_certidao_do_ri`,
#   medido em 667). Escrever um segundo aqui daria duas versoes do corpo do
#   pedido de `/selo/imovel/certidao`, e elas divergiriam no primeiro conserto.
#
# **O CODIGO DO ITEM SAI DA TABELA, E A PROCEDENCIA FICA MARCADA** — como no
#   RI: `16.24.4` e «certidoes de inteiro teor, onus e de acoes reais», que e a
#   unica especie que este livro emite. MEDIDO e o que a casa mandou; TABELA e
#   o que a norma diz, e os dois nao se confundem.
PROCEDENCIA_DO_CAMINHO_DA_CERTIDAO = "MEDIDO"
PROCEDENCIA_DO_CODIGO_DA_CERTIDAO = "TABELA"
CAMINHO_DA_CERTIDAO = "/selo/imovel/certidao"


# **A CERTIDAO DE MAIS DE UMA FOLHA SAO DOIS SELOS, E ISSO E MEDIDO** —
# 21/09/2026, nos 667 envelopes de `/selo/imovel/certidao` do acervo, agrupados
# pelo protocolo:
#
#   | o que saiu no protocolo | protocolos |
#   |---|---|
#   | `16.24.4` **+** `16.24.4.1` (inteiro teor + folha acrescida) | **99** |
#   | `16.24.1` **+** `16.24.2` (certidao comum + folha acrescida) | **94** |
#   | `16.24.4` sozinho | **44** — e a quantidade e **1 nos 44** |
#   | `16.24.1` sozinho | **44** |
#
#   E a quantidade nos pares diz o resto: o item BASE vai sempre com **1** (uma
#   excecao em 99), e quem carrega o numero e o item da **folha acrescida** —
#   1, 2, 3, ate 12. Ou seja: a casa nao mandou «inteiro teor, quantidade 5»;
#   mandou «inteiro teor, 1» **e** «folha acrescida, 4».
#
#   E a tabela diz a mesma coisa com todas as letras: o `16.24.4.1` se chama
#   «por folha acrescida alem da primeira». **Um selo por item** e a regra
#   desta casa desde 27/08/2026, e aqui ela tem 193 protocolos de prova.
ITEM_BASE_DA_CERTIDAO = "16.24.4"
ITEM_DA_FOLHA_ACRESCIDA = "16.24.4.1"


def itens_da_certidao(folhas: int = 1) -> list[tuple[str, int]]:
    """Os itens de emolumento daquela certidao, na forma que a casa mandou.

    Devolve `[(codigo, quantidade), ...]` — **um selo por item**, que e como
    `selar_o_ato_lavrado` e chamado no resto da casa. Uma folha da um item so;
    mais de uma da o par, com o excedente no segundo.
    """
    # **A REGRA MORA NUM LUGAR SO** — `ato_selado.itens_da_certidao_do_ri`. O
    # caminho e o mesmo (`/selo/imovel/certidao`) e a tabela e a mesma; duas
    # versoes divergiriam no primeiro conserto, e o que diverge aqui e a conta
    # que o cliente paga.
    return AS.itens_da_certidao_do_ri("INTEIRO_TEOR", folhas)


def envelope_da_certidao(*, escrevente, versao_tabela, registro_numero,
                         quantidade: int = 1, requerente=None,
                         requerente_documento=None, codigo=None) -> dict:
    """O corpo do pedido de selo da certidao do Livro 3.

    **SEM REQUERENTE, VAI O QUE SE CERTIFICA** — e no RI a casa mandou
    `MATRICULA 1116`. Aqui a coisa certificada nao se chama matricula: chama-se
    **registro**, e e assim que este livro a escreve no proprio envelope do ato
    (`AV - 1 do Registro 1332`, medido nos 17 do acervo). A forma e a mesma; a
    palavra e a deste livro, e fica declarado que ela e **derivada** — nao ha
    envelope de certidao do Livro 3 no acervo para medir o texto da parte.
    """
    envelope = AS.envelope_da_certidao_do_ri(
        tipo="INTEIRO_TEOR", escrevente=escrevente, versao_tabela=versao_tabela,
        quantidade=quantidade, requerente=requerente,
        requerente_documento=requerente_documento,
        matricula=registro_numero)
    if not str(requerente or "").strip():
        envelope["partes"]["parteAto"] = [
            {"documento": "00000000000",
             "nome": f"Registro {str(registro_numero or '').strip()} "
                     f"do Livro 3"}]
    if codigo:
        # O ITEM DA FOLHA ACRESCIDA E O OUTRO ENVELOPE DO MESMO PEDIDO — o
        # corpo e identico, e o que muda e o codigo e a quantidade.
        envelope["codigoTipoAto"] = str(codigo).strip()
    return envelope
