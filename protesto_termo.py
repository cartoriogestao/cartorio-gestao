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

from bd_nativo import banco
from typing import Any

# ---------------------------------------------------------------- as pecas
#
# O TEXTO E O DESTA CASA, copiado do catalogo do E-Oficio
# (`tbmotivoprotesto.memInformativo`) — nao foi redigido aqui. E o precedente
# real, que e o que a regra do oficial manda imitar quando nao ha norma que
# decida a forma.

# O TIPO E O MOTIVO SÃO DE CADA TÍTULO — inspeção da Corregedoria, tarefa #49:
# «deixar de usar motivo genérico e registrar tipo/motivo de forma clara e
# individualizada». Até 13/10/2026 a base terminava com «PROTESTO LAVRADO
# PARA FINS E EFEITOS DO ART. 9º-A DA LEI Nº 9.430/1996» — o único motivo do
# catálogo do E-Ofício (`tbmotivoprotesto`, uma linha), escrito em 1.126 de
# 1.132 protestos, inclusive nos que não são de dívida ativa. É exatamente o
# motivo genérico que a inspeção reprovou.
#
# O DADO INDIVIDUAL JÁ EXISTIA: é o campo «motivo do protesto» da remessa da
# CRA (posição 297; `tbSDT.Campo22` no acervo — «1» em 1.403 títulos e «2» em
# 34), com o vocabulário oficial de `protesto_cra.MOTIVOS_DE_PROTESTO`. O tipo
# é comum ou para fins falimentares (`TIPOS_DE_PROTESTO`); o falimentar é o
# que se pede expressamente, e no acervo não há um só
# (`strProtestoFalimentar` vazio nos 1.414).
#
# O TEXTO-BASE DO TERMO («CERTIFICO que não houve manifestação … PROTESTO
# {tipo} LAVRADO POR {motivo}.») ERA A CONSTANTE `TEXTO_BASE`, e saiu daqui no
# LF06A (19/10/2026) junto com o termo inteiro — ver `TERMO_DO_PROTESTO` abaixo.

# QUAIS códigos valem — o vocabulário da CRA. É regra: motivo ou tipo fora
# daqui não se escreve (ver `montar`). COMO cada um se escreve no livro, por
# extenso, eram os dicionários `MOTIVO_NO_LIVRO` e `TIPO_NO_LIVRO`, e saiu
# daqui no LF06E (19/10/2026): são as peças `PT_TERMO_MOTIVOS` e
# `PT_TERMO_TIPOS`, que o oficial edita na tela de Modelos.
MOTIVOS_DO_PROTESTO = ("1", "2", "3")
TIPOS_DO_PROTESTO = ("C", "F")

# A FRASE DO PAGAMENTO A POSTERIORI está em 1.105 de 1.132. O que decide os
# outros 27 nao esta no dado — ver o cabecalho. Ela era a constante
# `FRASE_PAGAMENTO_POSTERIORI` e e parte do texto do termo, que o oficial edita.

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
#
# O TEXTO MORA EM `modelos_padrao/protesto/PT_TERMO_PROTESTO.txt` desde o LF06A
# (19/10/2026) — o texto-base, a frase do pagamento a posteriori e o
# `{edital}`, uma linha cada, com os MESMOS bytes de quando era
# `TEXTO_BASE + "\n" + FRASE_PAGAMENTO_POSTERIORI + "\n{edital}"`. Chega pela
# base dos padrões; o nome antigo `TERMO_DO_PROTESTO` continua respondendo —
# ver `__getattr__` no fim deste módulo.


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


def _frase(con: Any, chave: str, **claros: Any) -> str:
    """A peça do termo, com o ajuste da casa (com `con`) ou o padrão."""
    import protesto_pecas as PECAS
    return PECAS.montar(con, chave, TermoError, **claros)


def frase_do_edital(*, data: Any, motivo: Any = None, con: Any = None) -> str:
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
    # «O DEVEDOR», e não «o Sacado»: na nota promissória e no cheque o devedor
    # é o emitente (CN-MA art. 919, § 4º). O E-Ofício escrevia «Sacado» em
    # todos; até 14/10/2026, este também.
    #
    # COM OU SEM MOTIVO É REGRA DAQUI; as duas frases são do oficial (LF06E,
    # `PT_TERMO_INTIMACAO_EDITAL` e `..._SEM_MOTIVO`).
    if razao:
        return _frase(con, "PT_TERMO_INTIMACAO_EDITAL", data=quando, motivo=razao)
    return _frase(con, "PT_TERMO_INTIMACAO_EDITAL_SEM_MOTIVO", data=quando)


def motivo_no_livro(codigo: Any, con: Any = None) -> str:
    """«1» -> «FALTA DE PAGAMENTO». Código desconhecido devolve vazio.

    Com `con`, o texto é o da casa (`PT_TERMO_MOTIVOS`); sem ele, o padrão.
    """
    c = _texto(codigo).upper()
    if c not in MOTIVOS_DO_PROTESTO:
        return ""
    import protesto_pecas as PECAS
    return PECAS.vocabulario(con, "PT_TERMO_MOTIVOS").get(c, "")


def tipo_no_livro(codigo: Any, con: Any = None) -> str:
    """«F» -> «PARA FINS FALIMENTARES»; vazio é o protesto COMUM.

    O falimentar se pede expressamente (Lei 9.492/1997, art. 23); sem o pedido
    o protesto é o comum — e é o que o acervo diz em 1.414 de 1.414.
    """
    c = _texto(codigo).upper()[:1] or "C"
    if c not in TIPOS_DO_PROTESTO:
        return ""
    import protesto_pecas as PECAS
    return PECAS.vocabulario(con, "PT_TERMO_TIPOS").get(c, "")


def frase_da_intimacao_pessoal(*, data: Any, digital: bool = False,
                               con: Any = None) -> str:
    """«O devedor foi intimado pessoalmente em DD/MM/AAAA.»

    A CERTIDÃO DA INTIMAÇÃO É ITEM DO REGISTRO (Lei 9.492/1997, art. 22, IV;
    CN-MA art. 914), e até 14/10/2026 o termo só a escrevia quando ela era por
    edital — a intimação em mãos, que é a regra da lei, saía sem uma palavra.
    A digital é a do CN-MA art. 919, § 1º, cumprida pela confirmação da
    plataforma (art. 921, § 6º, II).
    """
    quando = _data_br(data)
    if not quando:
        return ""
    if digital:
        return _frase(con, "PT_TERMO_INTIMACAO_DIGITAL", data=quando)
    return _frase(con, "PT_TERMO_INTIMACAO_PESSOAL", data=quando)


def qualificacao(fatos: dict | None, con: Any = None) -> dict[str, str]:
    """Os claros da qualificação do registro, já escritos. Só calcula.

    **O «ACIMA MENCIONADO E QUALIFICADO» NÃO TINHA O QUE ESTAVA ACIMA** (LD04,
    21/10/2026). O texto da casa, copiado do E-Ofício, diz que «o responsável
    acima mencionado e qualificado foi intimado» — e no E-Ofício a folha do
    Livro de Registro de Protestos trazia a qualificação em cima. Aqui o livro
    é o próprio `pt_atos.teor`, e ele saía sem ela: nem o protocolo, nem o
    apresentante, nem o título, nem o devedor. A Lei 9.492/1997, art. 22, I a
    VII, manda o REGISTRO conter tudo isso, e o art. 21, § 4º, diz que «os
    devedores não poderão deixar de figurar no termo» (CN-MA art. 914).

    A REDAÇÃO É A DO INSTRUMENTO (`protesto_instrumento.pedacos_da_descricao`):
    o registro e a certidão dele têm de BATER, item a item. O texto em volta é
    a peça `PT_TERMO_QUALIFICACAO`, que `montar` põe NO ALTO do termo. Sem
    `fatos` — o montador chamado solto, o ouro — os claros vêm vazios, e a
    peça some inteira.
    """
    vazio = {"lugar": "", "data": "", "protocolo": "", "apresentante": "",
             "titulo": "", "credor": "", "devedor": ""}
    if not fatos or not fatos.get("titulo"):
        return vazio
    import protesto_instrumento as PI
    p = PI.pedacos_da_descricao(
        {"titulo": fatos["titulo"], "protesto": fatos.get("protesto"),
         "apontado_em": fatos.get("apontado_em"),
         "apresentante": fatos.get("apresentante"),
         "devedores": fatos.get("devedores") or []}, con)
    return {"lugar": p["lugar"], "data": p["data_registro"],
            "protocolo": p["protocolo"], "apresentante": p["apresentante"],
            "titulo": p["titulo"], "credor": p["credor"],
            "devedor": " ".join(p["devedores"])}


def montar(*, modelo: str | None = None, edital_data: Any = None,
           edital_motivo: Any = None, motivo_protesto: Any = None,
           tipo_protesto: Any = None, pessoal_data: Any = None,
           pessoal_digital: bool = False, qualificacao_do_registro: dict | None = None,
           con: Any = None) -> str:
    """O texto do registro do protesto. Só calcula.

    `modelo` é o que o oficial editou no catálogo; sem ele vale
    `TERMO_DO_PROTESTO`, que é o texto desta casa copiado do E-Ofício. Com
    `con`, a frase da intimação, o motivo e o tipo saem com o ajuste da casa
    (LF06E); sem ele, do padrão.

    **O LIVRO LAVRA O PADRÃO**: `protesto.lancar_protesto` não passa `con`.
    Essas frases eram constantes até o LF06E, e o ajuste da casa não chegava
    ao livro; fazê-lo chegar muda o que se lavra, e espera a decisão do
    oficial.

    **UM MARCADOR SÓ**, `{edital}`, e é o único que o sistema sabe preencher
    sozinho — se a intimação foi por edital, em que data e por qual motivo.
    Sem edital ele entra vazio, e a linha que sobra some: por isso o modelo
    não precisa de condição, que é o que justifica ele ser `CHAVES` e não
    Jinja.

    **A QUALIFICAÇÃO DO REGISTRO VAI NO ALTO, E NÃO NO MODELO** (LD04,
    21/10/2026). `qualificacao_do_registro` (lida por `dados_do_titulo`) traz
    o lugar e a data do registro, o protocolo, o apresentante, o título, o
    credor e os devedores, e a peça `PT_TERMO_QUALIFICACAO` os escreve ANTES
    do texto do modelo — o «acima mencionado e qualificado» dele. É peça, e
    não claro do modelo, porque a Lei 9.492/1997, art. 21, § 4º, diz que «os
    devedores não poderão deixar de figurar no termo»: o termo que a casa
    personalizou também a recebe, sem que o texto dela seja tocado.

    **E NÃO HÁ MAIS UM `pagamento_posteriori`.** Ele era um `bool` que ninguém
    sabe quando desligar: a frase está em 1.105 de 1.132, e os 27 sem ela não
    têm traço comum — três anos diferentes, metade com o protesto cobrado e
    metade não. **Marca que ninguém sabe quando marcar é marca que vai ser
    marcada errado.** A frase é parte do texto que o oficial edita; se um dia
    aparecer a regra, ela vira marcador.
    """
    if not modelo:
        import modelos_da_casa as CASA
        modelo = CASA.padrao_de(CHAVE_NO_CATALOGO)
    molde = modelo
    # O MARCADOR CONTINUA SE CHAMANDO `{edital}` — trocar o nome quebraria o
    # modelo que o oficial já tenha editado —, e passa a levar a certidão da
    # intimação que houve: por edital, em mãos ou digital.
    partes = {"edital": (frase_do_edital(data=edital_data, motivo=edital_motivo,
                                         con=con)
                         or frase_da_intimacao_pessoal(
                             data=pessoal_data, digital=pessoal_digital,
                             con=con)),
              "motivo": motivo_no_livro(motivo_protesto, con),
              "tipo": tipo_no_livro(tipo_protesto, con)}
    # MOTIVO QUE NÃO SE SABE NÃO SE ESCREVE: escrever um no lugar dele seria
    # o motivo genérico que a inspeção reprovou, agora inventado.
    if "{motivo}" in molde and not partes["motivo"]:
        raise TermoError(
            "O título não diz o motivo do protesto (falta de pagamento, de "
            "aceite ou de devolução) — ele vem no arquivo da CRA. Informe-o "
            "na ficha do título antes de lavrar.")
    if "{tipo}" in molde and not partes["tipo"]:
        raise TermoError(
            f"O tipo de protesto «{_texto(tipo_protesto)}» não é comum (C) "
            f"nem para fins falimentares (F). Corrija-o na ficha do título.")
    try:
        texto = molde.format(**partes)
    except (KeyError, IndexError, ValueError) as erro:
        raise TermoError(
            f"O modelo do termo do protesto tem um marcador que não existe: "
            f"{erro}. Os que valem são {{tipo}}, {{motivo}} e {{edital}} — as "
            f"demais frases são texto, e se escrevem inteiras no modelo."
        ) from erro
    # O `\n` EM `TEXTO_BASE`/`TERMO_DO_PROTESTO` É SÓ FRONTEIRA DE FRASE — o
    # que decide onde uma parte acaba e a linha vazia do edital ausente some.
    # O QUE VAI PARA O LIVRO É CORRIDO: art. 795, § 2º do Código de Normas,
    # a mesma regra de `notas_modelos.py`. Até 07/09/2026 este `join` era por
    # `"\n"`, e o texto saía com quebra de linha real — o «claro» que a norma
    # proíbe — no que é gravado em `pt_atos.teor`, o próprio Livro de
    # Registro de Protestos.
    linhas = [x.strip() for x in texto.split("\n")]
    corpo = " ".join(x for x in linhas if x)
    return " ".join(x for x in (_qualificacao_no_alto(qualificacao_do_registro,
                                                       con), corpo) if x)


# A peça da qualificação, em `modelos_padrao/protesto/`; o nome
# `QUALIFICACAO_DO_REGISTRO` responde pelo `__getattr__` do fim deste módulo.
CHAVE_DA_QUALIFICACAO = "PT_TERMO_QUALIFICACAO"


def _qualificacao_no_alto(fatos: dict | None, con: Any = None) -> str:
    """A peça da qualificação preenchida, ou vazio sem os fatos. Só calcula.

    A LINHA CUJOS CLAROS VIERAM TODOS VAZIOS SOME (`_corrido`): «Registro do
    protesto: {lugar}, em {data}.» antes de o protesto ter lugar no livro
    sairia «Registro do protesto: , em .» — o claro que a norma proíbe, com
    a pontuação em volta. O claro inventado num ajuste da casa recusa com o
    nome da peça (`protesto_pecas.preencher`).
    """
    if not fatos:
        return ""
    import protesto_pecas as PECAS
    claros = qualificacao(fatos, con)
    molde = PECAS.texto(con, CHAVE_DA_QUALIFICACAO)
    PECAS.preencher(molde, CHAVE_DA_QUALIFICACAO, TermoError, **claros)
    return _corrido(molde, claros)


def _corrido(molde: str, partes: dict) -> str:
    """O texto do livro, CORRIDO: uma frase por linha do modelo, e a linha
    cujos claros vieram todos vazios fora. Só calcula — o modelo já foi
    conferido por quem chama (o marcador que não existe recusa lá)."""
    return " ".join(linhas_com_fatos(molde, partes))


def linhas_com_fatos(molde: str, partes: dict) -> list[str]:
    """As linhas do modelo preenchidas, sem a que ficou sem fato nenhum. Só calcula.

    A regra da linha que some vale para todo papel do protesto montado de
    frases inteiras (o termo, o do cancelamento, a quitação): quem escreve o
    modelo não precisa de condição para dizer que houve cheque ou credor.
    """
    import string
    linhas = []
    for linha in molde.split("\n"):
        claros = [n for _, n, _, _ in string.Formatter().parse(linha) if n]
        if claros and not any(str(partes.get(n) or "").strip() for n in claros):
            continue
        pronta = " ".join(linha.format(**partes).split())
        if pronta:
            linhas.append(pronta)
    return linhas


# --------------------------------------------- o termo do cancelamento

# O TERMO DO CANCELAMENTO (LD04, 21/10/2026). `protesto.lancar_cancelamento`
# gravava a hipótese e o fundamento, e nenhum texto: `pt_atos.teor` ficava
# vazio. A Lei 9.492/1997, art. 26, § 6º: no registro eletrônico, «o termo do
# cancelamento será lançado em documento apartado, que será arquivado
# juntamente com os documentos que instruíram o pedido, e anotado no índice
# respectivo» (CN-MA art. 896). O texto mora em
# `modelos_padrao/protesto/PT_TERMO_CANCELAMENTO.txt` e é do oficial; o nome
# `TERMO_DO_CANCELAMENTO` responde pelo `__getattr__` do fim deste módulo.
CHAVE_DO_CANCELAMENTO = "PT_TERMO_CANCELAMENTO"


def montar_cancelamento(*, modelo: str | None = None, data: Any,
                        hipotese: str, fundamento_legal: str, fundamento: str,
                        qualificacao_do_registro: dict | None = None,
                        con: Any = None) -> str:
    """O texto do termo do cancelamento. Só calcula.

    O REGISTRO QUE SE CANCELA SE IDENTIFICA COMO O PRÓPRIO REGISTRO SE
    IDENTIFICA: lugar e data, protocolo, título, credor e devedores, com os
    pedaços do instrumento (`qualificacao`) — uma redação só para o mesmo
    fato. `modelo` é o que o oficial editou no catálogo; sem ele, o padrão.
    Com `con`, os pedaços saem com o ajuste da casa; o livro não o passa,
    como no termo do protesto.
    """
    if not modelo:
        import modelos_da_casa as CASA
        modelo = CASA.padrao_de(CHAVE_DO_CANCELAMENTO)
    fatos = qualificacao_do_registro or {}
    p: dict = {}
    if fatos.get("titulo"):
        import protesto_instrumento as PI
        p = PI.pedacos_da_descricao(
            {"titulo": fatos["titulo"], "protesto": fatos.get("protesto"),
             "apontado_em": fatos.get("apontado_em"),
             "devedores": fatos.get("devedores") or []}, con)
    caso = _texto(fundamento)
    # O FUNDAMENTO DO CASO é escrito por quem cancela; a frase do termo
    # termina com ponto, escreva ele ou não.
    if caso and caso[-1] not in ".!?":
        caso += "."
    partes = {"data": _data_br(data), "hipotese": _texto(hipotese),
              "fundamento_legal": _texto(fundamento_legal), "fundamento": caso,
              "registro": p.get("registro", ""),
              "protocolo": p.get("protocolo", ""), "titulo": p.get("titulo", ""),
              "credor": p.get("credor", ""),
              "devedor": " ".join(p.get("devedores") or ())}
    # O CLARO QUE NÃO EXISTE RECUSA com o nome do papel e os claros que valem
    # — a régua das peças (`protesto_pecas.preencher`), a mesma da tela.
    import protesto_pecas as PECAS
    PECAS.preencher(modelo, CHAVE_DO_CANCELAMENTO, TermoError, **partes)
    return _corrido(modelo, partes)


# ------------------------------------------------- o que o ato já sabe


def fatos_da_qualificacao(bd: Any, titulo_id: int) -> dict | None:
    """O título, o protesto que vale, o apontamento e os devedores. Só LÊ.

    O NÚMERO DO LIVRO MORA EM `nu_livros`, que é do núcleo: banco só com o
    esquema do protesto não a tem — a mesma guarda de `protesto_instrumento`.
    """
    titulo = bd.um("SELECT * FROM pt_titulos WHERE id=%s", (titulo_id,))
    if titulo is None:
        return None
    livro_sql = ("(SELECT v.numero FROM nu_livros v WHERE v.id = a.livro_id)"
                 if bd.tem_tabela("nu_livros") else "NULL")
    protesto = bd.um(
        f"""SELECT a.data_ato, a.folha, a.rotulo, a.numero_ordem,
                   {livro_sql} AS livro_numero
              FROM pt_atos a
             WHERE a.titulo_id = %s AND a.tipo = 'PROTESTO' AND a.cancelado = 0
             ORDER BY a.id DESC LIMIT 1""", (titulo_id,))
    apontamento = bd.um(
        """SELECT data_ato FROM pt_atos
            WHERE titulo_id = %s AND tipo = 'APONTAMENTO' AND cancelado = 0
            ORDER BY id LIMIT 1""", (titulo_id,))
    devedores = bd.ler(
        """SELECT nome, documento_tipo, documento_numero, endereco, bairro,
                  cep, cidade, uf
             FROM pt_devedores WHERE titulo_id = %s ORDER BY id""", (titulo_id,))
    # O ENDEREÇO DO APRESENTANTE (LD08) — Lei 9.492/1997, art. 22, II: «o
    # registro do protesto e seu instrumento» o contêm. A mesma leitura do
    # instrumento: o título, ou o cadastro dos apresentantes pelo código.
    import protesto as PT
    return {"titulo": dict(titulo),
            "apresentante": PT.apresentante_do_titulo(bd, titulo),
            "protesto": dict(protesto) if protesto is not None else None,
            "apontado_em": apontamento["data_ato"] if apontamento else None,
            "devedores": [dict(d) for d in devedores]}


def dados_do_titulo(con: sqlite3.Connection, titulo_id: int) -> dict:
    """Os fatos que a frase do edital precisa, lidos do próprio título.

    A ÚLTIMA INTIMAÇÃO É A QUE CONTA — o aviso não é um por título (1.618 para
    1.361), e reemitir é rotina. O texto do livro descreve a intimação que
    levou a este protesto, que é a última.
    """
    bd = banco(con)
    tit = bd.um(
        "SELECT motivo_protesto, tipo_protesto FROM pt_titulos WHERE id=%s",
        (int(titulo_id),))
    proprio = {"motivo_protesto": tit["motivo_protesto"] if tit else None,
               "tipo_protesto": tit["tipo_protesto"] if tit else None}
    # A QUALIFICAÇÃO DO REGISTRO (LD04) — os mesmos fatos que o instrumento lê
    # (`protesto_instrumento.dados`): o título, o PROTESTO que vale (com o
    # lugar no livro, que só existe depois de `escrituracao.reservar`), a data
    # do apontamento e os devedores, na ordem em que entraram.
    proprio["qualificacao_do_registro"] = fatos_da_qualificacao(bd, int(titulo_id))
    linha = bd.um(
        """SELECT data_ato, detalhe_json FROM pt_atos
            WHERE titulo_id = %s AND tipo = 'INTIMACAO' AND cancelado = 0
            ORDER BY id DESC LIMIT 1""", (int(titulo_id),))
    if linha is None:
        return {"edital_data": None, "edital_motivo": None, **proprio}
    try:
        detalhe = json.loads(linha["detalhe_json"] or "{}")
    except (TypeError, ValueError):
        detalhe = {}
    if str(detalhe.get("modo") or "").upper() != "EDITAL":
        # INTIMAÇÃO PESSOAL NÃO GERA A FRASE DO EDITAL — escrevê-la seria
        # afirmar no livro uma publicação que não houve —, e gera a dela.
        return {"edital_data": None, "edital_motivo": None, **proprio,
                "pessoal_data": linha["data_ato"],
                "pessoal_digital": bool(detalhe.get("digital"))}
    return {"edital_data": linha["data_ato"],
            "edital_motivo": detalhe.get("motivo_nao_entrega")
            or detalhe.get("motivo") or None, **proprio}


def __getattr__(nome: str):
    """Os nomes antigos do texto de fábrica, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06A (19/10/2026) e mora em `modelos_padrao/`.
    Quem ainda importa o nome antigo recebe o padrão da base — o MESMO que o
    papel imprime, e não uma cópia que ficou para trás. Nome que não é de papel
    continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
