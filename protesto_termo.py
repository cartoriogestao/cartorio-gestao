"""O TEXTO QUE VAI NO REGISTRO DO PROTESTO — e este sistema nunca o teve.

Achado em 01/09/2026, seguindo a regua que o oficial deu no mesmo dia: *«sobre
tudo que o e-oficio faz, tente buscar dados dentro do banco de dados»*. A
tabela apareceu com **1.132 linhas**:

    tbProtesto_Motivo — o `memInformativo` de cada protesto lavrado

Contra **1.164 protestos** no acervo. Quase um por protesto, e o nosso
`lancar_protesto` nao escrevia uma palavra: gravava livro, folha e numero de
ordem, e mais nada. **O Livro de Registro de Protestos ficava sem o texto do
ato.**

E o defeito e o mesmo do Registro Civil, achado em 29/08: *«o termo e o texto
que vai no livro, e este sistema nunca o teve»*. Segunda atribuicao, mesmo
buraco.

===========================================================================
O TEXTO SE COMPOE DE FRASES INTEIRAS, E ISSO E MEDIDO
===========================================================================

Sao **23 formas distintas** nas 1.132 linhas — e as 23 sao a mesma base mais
duas frases que entram ou nao:

    base .............................. 1.126 de 1.132   (99,5%)
    «pagamento a posteriori» .......... 1.105 de 1.132   (97,6%)
    «intimado por Edital em <data>» ... 1.078 de 1.132   (95,2%)
    «pelo motivo <motivo>» ............ 1.007 de 1.132

E por serem frases inteiras, o formato deste modelo e `CHAVES` — `{nome}`, do
`str.format` —, e nao Jinja. **A decisao de a frase existir e do modulo, e nao
do modelo**: quem escreve o texto do livro nao deveria precisar de `{% if %}`
para dizer que houve edital. E a mesma razao dos termos do civil.

===========================================================================
O QUE O SISTEMA DECIDE, E O QUE O OFICIAL DECIDE
===========================================================================

**A FRASE DO EDITAL O SISTEMA MONTA**, porque ele sabe: se a intimacao foi por
edital, em que data, e por que motivo a entrega falhou. Sao fatos que estao em
`pt_atos` e em `pt_avisos`.

**E ELA CONSERTA UM DEFEITO DO E-OFICIO.** Nas linhas medidas aparece
`«pelo motivo Ausente Ausente»` **24 vezes** e `«Ausente Ausente Ausente»`
**4 vezes** — ele repetia o motivo a cada edital emitido. E em **7** linhas a
frase seguinte veio colada sem ponto: `«...pelo motivo Ausente Este protesto
foi registrado...»`. Aqui o motivo entra **uma vez**, e as frases terminam com
ponto.

**A BASE E A FRASE DO PAGAMENTO A POSTERIORI SAO DO OFICIAL**, e vao para o
catalogo de modelos que ele edita (relato #28). Duas razoes:

  1) A base afirma «PROTESTO LAVRADO PARA FINS E EFEITOS DO ART. 9o-A DA LEI
     No 9.430/1996» — que e o artigo da **divida ativa da Fazenda** — em 1.126
     de 1.132 protestos, **inclusive nos que nao sao de divida ativa**. Isso e
     afirmacao juridica num papel que a serventia assina, e quem responde por
     ela e quem assina.

  2) O que decide a frase do «pagamento a posteriori» **nao esta no dado**:
     os 27 protestos sem ela se espalham por 2024, 2025 e 2026, e se dividem
     meio a meio entre os que tiveram o protesto cobrado e os que nao. Nao ha
     traco comum visivel. **A CONFERIR** — e ate la ela e do modelo, com o
     numero ao lado.

===========================================================================
O TERMO CONGELA
===========================================================================

Ele e o texto que foi escrito no livro naquele dia. Remonta-lo depois faria o
livro de hoje discordar do que esta no papel — e corrigir protesto e averbar
ao lado, nao reescrever. Por isso ele se grava no ato, e nao se recalcula.

    A CERTIDAO E O OPOSTO: ela se monta a cada emissao, e a proxima ja sai
    corrigida. Sao papeis diferentes com regras opostas, e ja foi assim no
    Registro Civil.

FUNDAMENTO
    Lei 9.492/1997, arts. 21 a 24 — o registro do protesto e o que ele contem.
    Medido em `tbProtesto_Motivo` (1.132) e `tbmotivoprotesto` (o catalogo).
"""
from __future__ import annotations

# Chave em `modelos_da_casa.CATALOGO` (tela /modelos).
CHAVE_NO_CATALOGO = "PT_TERMO_PROTESTO"

import json
import sqlite3
from typing import Any

# ---------------------------------------------------------------- as pecas
#
# O TEXTO E O DESTA CASA, copiado do catalogo do E-Oficio
# (`tbmotivoprotesto.memInformativo`) — nao foi redigido aqui. E o precedente
# real, que e o que a regra do oficial manda imitar quando nao ha norma que
# decida a forma.

TEXTO_BASE = (
    "CERTIFICO que não houve manifestação e que o responsável acima "
    "mencionado e qualificado foi intimado conforme preceitua a Lei Federal "
    "específica de Protesto e normas determinadas pela Corregedoria Geral de "
    "Justiça do Estado do Maranhão.\n"
    "PROTESTO LAVRADO PARA FINS E EFEITOS DO ART. 9º-A DA LEI Nº 9.430/1996"
)

# 1.105 de 1.132. O que decide os outros 27 nao esta no dado — ver o cabecalho.
FRASE_PAGAMENTO_POSTERIORI = (
    "Este protesto foi registrado com o procedimento de pagamento a "
    "posteriori. Os emolumentos serão pagos pelo devedor no ato do "
    "cancelamento, conforme tabela vigente."
)

# O MODELO E O TEXTO INTEIRO, e nao o esqueleto dele.
#
# ISTO FOI CORRECAO, e o teste do catalogo a apanhou: eu havia posto como
# padrao `"{base}\n{posteriori}\n{edital}"` — 28 caracteres. O oficial
# abriria a tela de editar e veria **tres marcadores**, com a frase que afirma
# o art. 9o-A da Lei 9.430/1996 — que e a razao de este modelo ir ao catalogo
# — invisivel e ineditavel.
#
# SOBRA UM MARCADOR, e ele e o unico que o sistema sabe preencher sozinho:
# `{edital}`. Sem edital ele entra vazio, e `montar()` limpa a linha que sobra
# — e por isso o modelo nao precisa de condicao, que e o que justifica ele ser
# `CHAVES` e nao Jinja.
TERMO_DO_PROTESTO = (
    TEXTO_BASE + "\n" + FRASE_PAGAMENTO_POSTERIORI + "\n{edital}"
)


class TermoError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcao."""


def _texto(v: Any) -> str:
    return " ".join(str(v or "").split())


def _data_br(iso: Any) -> str:
    """`2026-08-26` -> `26/08/2026`, que e como o texto do livro escreve."""
    s = str(iso or "")[:10]
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}"
    return s


def frase_do_edital(*, data: Any, motivo: Any = None) -> str:
    """«O Sacado foi intimado por Edital em DD/MM/AAAA pelo motivo X.»

    O MOTIVO ENTRA UMA VEZ SO, e isto conserta o E-Ofício: nas linhas medidas
    ele aparece repetido — «pelo motivo Ausente Ausente» 24 vezes, e três
    vezes seguidas em outras 4 —, porque cada edital emitido acrescentava o
    seu. Reemitir edital é rotina nesta casa (1.618 avisos para 1.361
    títulos), e por isso o defeito era frequente.

    E A FRASE TERMINA COM PONTO. Em 7 linhas medidas a seguinte veio colada:
    «...pelo motivo Ausente Este protesto foi registrado...».
    """
    quando = _data_br(data)
    if not quando:
        return ""
    razao = _texto(motivo)
    fim = f" pelo motivo {razao}" if razao else ""
    return f"O Sacado foi intimado por Edital em {quando}{fim}."


def montar(*, modelo: str | None = None, edital_data: Any = None,
           edital_motivo: Any = None) -> str:
    """O texto do registro do protesto. Só calcula.

    `modelo` é o que o oficial editou no catálogo; sem ele vale
    `TERMO_DO_PROTESTO`, que é o texto desta casa copiado do E-Ofício.

    **UM MARCADOR SÓ**, `{edital}`, e é o único que o sistema sabe preencher
    sozinho — se a intimação foi por edital, em que data e por qual motivo.
    Sem edital ele entra vazio, e a linha que sobra some: por isso o modelo
    não precisa de condição, que é o que justifica ele ser `CHAVES` e não
    Jinja.

    **E NÃO HÁ MAIS UM `pagamento_posteriori`.** Ele era um `bool` que ninguém
    sabe quando desligar: a frase está em 1.105 de 1.132, e os 27 sem ela não
    têm traço comum — três anos diferentes, metade com o protesto cobrado e
    metade não. **Marca que ninguém sabe quando marcar é marca que vai ser
    marcada errado.** A frase é parte do texto que o oficial edita; se um dia
    aparecer a regra, ela vira marcador.
    """
    partes = {"edital": frase_do_edital(data=edital_data,
                                        motivo=edital_motivo)}
    try:
        texto = (modelo or TERMO_DO_PROTESTO).format(**partes)
    except (KeyError, IndexError, ValueError) as erro:
        raise TermoError(
            f"O modelo do termo do protesto tem um marcador que não existe: "
            f"{erro}. O único que vale é {{edital}} — as demais frases são "
            f"texto, e se escrevem inteiras no modelo."
        ) from erro
    # O `\n` EM `TEXTO_BASE`/`TERMO_DO_PROTESTO` É SÓ FRONTEIRA DE FRASE — o
    # que decide onde uma parte acaba e a linha vazia do edital ausente some.
    # O QUE VAI PARA O LIVRO É CORRIDO: art. 795, § 2º do Código de Normas,
    # a mesma regra de `notas_modelos.py`. Até 07/09/2026 este `join` era por
    # `"\n"`, e o texto saía com quebra de linha real — o «claro» que a norma
    # proíbe — no que é gravado em `pt_atos.teor`, o próprio Livro de
    # Registro de Protestos.
    linhas = [x.strip() for x in texto.split("\n")]
    return " ".join(x for x in linhas if x)


# ------------------------------------------------- o que o ato já sabe


def dados_do_titulo(con: sqlite3.Connection, titulo_id: int) -> dict:
    """Os fatos que a frase do edital precisa, lidos do próprio título.

    A ÚLTIMA INTIMAÇÃO É A QUE CONTA — o aviso não é um por título (1.618 para
    1.361), e reemitir é rotina. O texto do livro descreve a intimação que
    levou a este protesto, que é a última.
    """
    linha = con.execute(
        """SELECT data_ato, detalhe_json FROM pt_atos
            WHERE titulo_id = ? AND tipo = 'INTIMACAO' AND cancelado = 0
            ORDER BY id DESC LIMIT 1""", (int(titulo_id),)).fetchone()
    if linha is None:
        return {"edital_data": None, "edital_motivo": None}
    try:
        detalhe = json.loads(linha["detalhe_json"] or "{}")
    except (TypeError, ValueError):
        detalhe = {}
    if str(detalhe.get("modo") or "").upper() != "EDITAL":
        # INTIMAÇÃO PESSOAL NÃO GERA A FRASE, e é o certo: ela diz «intimado
        # por Edital». Escrevê-la numa intimação em mãos seria afirmar no
        # livro uma publicação que não houve.
        return {"edital_data": None, "edital_motivo": None}
    return {"edital_data": linha["data_ato"],
            "edital_motivo": detalhe.get("motivo_nao_entrega")
            or detalhe.get("motivo") or None}
