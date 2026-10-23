"""Os atos que estao DENTRO do texto da ficha, e a numeracao que eles mandam.

O RELATO DO OFICIAL FOI «AV-28 aparecendo no teor de ficha do acervo», e
parecia coisa de layout. Nao era.

O QUE SE MEDIU EM 28/08/2026
    Nas fichas que vieram do E-Oficio, os atos moram **dentro do texto** da
    matricula — `AV-28/1.490:-`, `R-1/1306:-` — e nao como linhas em `ri_atos`.
    Sao **1.052 das 1.508** matriculas com teor.

    Em **756** delas o texto passa a frente da tabela, e o sistema calcula o
    proximo numero com `MAX(numero) + 1` sobre `ri_atos` — que nao os enxerga.

E AQUI EU QUASE EXAGEREI O TAMANHO DO PROBLEMA
    Escrevi primeiro que eram **752 fichas** em que o ato novo nasceria com
    numero repetido, e cheguei a dizer isso ao oficial. Fui medir o
    `tipo_ficha` antes de deixar a frase de pe:

        ACERVO ......... 743 — o sistema JA EXIGIA o numero a mao, e recusava
                               lavrar sem ele
        ESTRUTURADA .... 13 — as unicas em que ele numera SOZINHO

    **Treze, e nao setecentos.** Nas 743 de acervo havia um `if` que dizia
    «nesta ficha de acervo o numero do ato precisa ser informado, conforme o
    livro fisico»; o problema ali era outro e menor — **a tela nao dizia qual
    era o numero certo**, e quem digitava tinha de ir ao papel.

    Mas as treze sairiam com numero repetido **sem ninguem digitar nada**:

        matricula  314 — a ficha traz R-35, ha 14 linhas: numeraria 15
        matricula 3199 — a ficha traz R-13, ha  2 linhas: numeraria  3
        matricula    8 — a ficha traz R-4,  ha  0 linhas: numeraria  1

    E o defeito de 18/08/2026 outra vez — a numeracao que anda para tras sobre
    acervo —, agora na ficha de imovel. **Dado cru nao e resposta; a resposta e
    o que a funcao devolve**, e a funcao ja se protegia em 98% dos casos.

O QUE ESTE MODULO NAO FAZ, E E O PONTO
    **Nao cria ato.** Ler o texto e inserir linhas em `ri_atos` seria fabricar
    atos com data, natureza e conteudo adivinhados — e ainda pô-los na corrente
    de hash, que existe justamente para provar que nenhum ato foi inventado.
    Um parser errando ali produz registro falso.

    Ele so **le o que esta escrito** e responde duas coisas: qual o maior
    numero que a ficha ja usou, e onde isso esta escrito — para uma pessoa
    conferir. A decisao continua sendo de quem lavra.

A PRECISAO QUE FAZ ISTO VALER: SO CONTA O ROTULO QUE NOMEIA ESTA MATRICULA
    O teor das fichas antigas cita atos de OUTRAS matriculas o tempo todo —
    «Transcrita neste Registro no Lº 2-C, fls. 16 sob nº R-1/503». Contar
    aquele `R-1` como ato desta ficha seria inflar a numeracao com o passado de
    outro imovel.

    Por isso o padrao exige a barra e o numero da matricula depois dela, e
    compara com a desta. `AV-3` solto **nao conta** — e isso perde alguns
    casos de proposito: e melhor deixar de achar do que achar errado, porque o
    numero que este modulo devolve vira o numero de um registro.

E ELE RESPONDE A SEGUNDA PERGUNTA DESDE 15/09/2026 — relato #67
    «precisa atualizar o teor da ficha com os atos recem lavrados». A pergunta
    de cima e pelo NUMERO; esta e pelo TEXTO, e as duas nao se respondem uma a
    outra: um ato pode ter o rotulo citado dentro da frase de outro e o texto
    dele nao estar escrito em lugar nenhum. `texto_escrito_no_teor` e
    `atos_fora_do_teor` sao a comparacao pelo texto, e e ela que a ficha usa
    para mostrar o teor gravado **e**, depois dele, os atos que o texto ainda
    nao conta.
"""
from __future__ import annotations

import re
import sqlite3
from html import unescape

from bd_nativo import banco

# `AV-28/1.490`, `R-1/1306`, `AV 3 / 2.765` — a letra, o numero do ato, a barra
# e a matricula. A barra e obrigatoria: e ela que diz de qual ficha o ato e.
ROTULO = re.compile(r"\b(AV|R)[\s.\-]{0,2}(\d{1,3})\s*/\s*([\d.]{1,12})",
                    re.IGNORECASE)
# O rotulo com o CNM da matricula — `R.02/000000.2.0009001-76`. HOTFIX
# SANDBOX-2026-10-19-02 (certidao de inteiro teor da 9.001 com dois R-01).
ROTULO_CNM = re.compile(
    r"\b(AV|R)[\s.\-]{0,2}(\d{1,3})\s*/\s*(\d{6}\.\d\.\d{7}-\d{2})",
    re.IGNORECASE)


def _so_digitos(v) -> str:
    return "".join(c for c in str(v or "") if c.isdigit()).lstrip("0")


def citados_no_teor(numero_da_matricula, teor, cnm=None) -> list[dict]:
    """Os atos que o texto da ficha atribui A ESTA matricula.

    Devolve `[{tipo, numero, rotulo, trecho}]`, com o trecho em volta para
    quem for conferir ver a frase e nao so o rotulo. Numero que aparece duas
    vezes entra uma vez.
    """
    meu = _so_digitos(numero_da_matricula)
    if not meu:
        return []
    texto = str(teor or "")
    achados: dict[tuple, dict] = {}
    # HOTFIX SANDBOX-2026-10-19-02: a transcricao da digitalizacao escreve o
    # rotulo com o CNM — `R.02/000000.2.0009001-76` — e o `ROTULO` antigo
    # ([\d.]{1,12}) nao o le. Na 9.001 o piso dizia «proximo: 2» com o R.02
    # escrito na ficha. O CNM e desta matricula; conta como o numero dela.
    meu_cnm = _so_digitos(cnm)
    padroes = [ROTULO] + ([ROTULO_CNM] if meu_cnm else [])
    casamentos = [m for p in padroes for m in p.finditer(texto)]
    casamentos.sort(key=lambda m: m.start())
    for m in casamentos:
        tipo, numero, alvo = m.group(1).upper(), int(m.group(2)), m.group(3)
        if _so_digitos(alvo) not in (meu, meu_cnm or meu):
            continue
        chave = (tipo, numero)
        if chave in achados:
            continue
        bruto = texto[max(0, m.start() - 70):m.end() + 70]
        achados[chave] = {
            "tipo": tipo, "numero": numero,
            "rotulo": f"{tipo}-{numero}",
            # O trecho vai SEM as marcas de formatacao: o teor do acervo e HTML,
            # e mostrar `<span style=…>` a quem confere esconde a frase dentro
            # do codigo dela.
            "trecho": " ".join(re.sub(r"<[^>]+>", " ", bruto).split()),
        }
    return [achados[k] for k in sorted(achados)]


def maior_citado(numero_da_matricula, teor) -> int:
    """O maior numero de ato que o texto da ficha atribui a esta matricula."""
    citados = citados_no_teor(numero_da_matricula, teor)
    return max((c["numero"] for c in citados), default=0)


def piso_do_proximo(con: sqlite3.Connection, matricula_id: int) -> dict:
    """De que numero o proximo ato desta matricula NAO pode ser menor.

    Devolve `{em_atos, no_teor, proximo, divergente, citados}`:

      `em_atos`    o maior numero que existe como linha em `ri_atos`
      `no_teor`    o maior que o TEXTO da ficha atribui a esta matricula
      `proximo`    o maior dos dois, mais um — o que se deve usar
      `divergente` se o texto passa a frente das linhas (o caso do risco)

    SO CALCULA. Nao grava, nao consome numero e nao cria ato — as tres coisas
    que uma funcao de contador desta casa nunca faz.
    """
    bd = banco(con)
    m = bd.um("SELECT id, numero, cnm, teor FROM ri_matriculas WHERE id = %s",
              (int(matricula_id),))
    if not m:
        return {"em_atos": 0, "no_teor": 0, "proximo": 1,
                "divergente": False, "citados": []}
    em_atos = int(bd.valor(
        "SELECT MAX(numero) AS n FROM ri_atos WHERE matricula_id = %s",
        (int(matricula_id),)) or 0)
    citados = citados_no_teor(m["numero"], m["teor"], m["cnm"])
    no_teor = max((c["numero"] for c in citados), default=0)
    return {
        "em_atos": em_atos,
        "no_teor": no_teor,
        "proximo": max(em_atos, no_teor) + 1,
        "divergente": no_teor > em_atos,
        "citados": citados,
    }


def ja_usado_na_ficha(con: sqlite3.Connection, matricula_id: int,
                      numero: int) -> dict | None:
    """O ato do TEXTO que ja tem esse numero, se houver. Para recusar com nome.

    A recusa que existia olhava so `ri_atos` («o numero 3 ja esta ocupado pelo
    ato AV-03»). Ela nao via o que esta escrito na ficha — e era ali que
    estavam os 756 casos.
    """
    m = banco(con).um("SELECT numero, cnm, teor FROM ri_matriculas WHERE id = %s",
                      (int(matricula_id),))
    if not m:
        return None
    for c in citados_no_teor(m["numero"], m["teor"], m["cnm"]):
        if c["numero"] == int(numero):
            return c
    return None


def matriculas_em_risco(con: sqlite3.Connection,
                        limite: int = 1000) -> list[dict]:
    """As fichas cujo TEXTO passa a frente das linhas de `ri_atos`.

    E a lista que da tamanho ao problema — 756 nesta casa, 13 delas
    estruturadas —, e sem ela o
    escrevente so descobriria abrindo a ficha na hora de lavrar.

    A leitura e em Python e nao em SQL de proposito: achar rotulo dentro de
    HTML nao e trabalho de `LIKE`, e o teto de portabilidade desta casa recusa
    recorte de texto no banco. Sao 1.508 fichas — roda em segundos, e esta tela
    se abre uma vez.
    """
    bd = banco(con)
    em_risco = []
    for m in bd.ler(
            """SELECT id, numero, cnm, livro, teor FROM ri_matriculas
                WHERE teor IS NOT NULL AND teor <> ''
                ORDER BY id"""):
        citados = citados_no_teor(m["numero"], m["teor"], m["cnm"])
        if not citados:
            continue
        no_teor = max(c["numero"] for c in citados)
        em_atos = int(bd.valor(
            "SELECT MAX(numero) AS n FROM ri_atos WHERE matricula_id = %s",
            (m["id"],)) or 0)
        if no_teor > em_atos:
            em_risco.append({
                "matricula_id": m["id"], "numero": m["numero"],
                "livro": m["livro"], "no_teor": no_teor, "em_atos": em_atos,
                "proximo": no_teor + 1,
                "distancia": no_teor - em_atos,
                "citados": citados,
            })
        if len(em_risco) >= limite:
            break
    # A MAIOR DISTANCIA PRIMEIRO: a ficha em que o sistema mais se enganaria e
    # a que mais precisa de olho. Ordenar por numero de matricula poria as de
    # risco 1 na frente das de risco 32.
    em_risco.sort(key=lambda x: (-x["distancia"], x["numero"] or ""))
    return em_risco


# ------------------------------------------------- o teor e os atos que faltam
#
# RELATO #67, de 15/09/2026: «precisa atualizar o teor da ficha com os atos
# recem lavrados». A medida que ele pediu esta aqui; a LEITURA dele — o painel
# «Teor da ficha», com o teor gravado e, depois dele, os atos que o texto ainda
# nao conta — esta na tela da ficha.
#
# **E NAO SE ESCREVE NO TEOR, e isso nao e falta de zelo.** Tres razoes, as
# tres medidas nas 1.508 fichas desta casa:
#
#   1. O TEXTO DA FICHA NAO E FEITO SO DE ATOS. Nas 429 fichas estruturadas
#      com texto, a descricao do imovel e a maior parte: em 314 delas, mais de
#      METADE do teor esta fora de qualquer ato. Escrever os atos dentro dele
#      obrigaria a reescrever esse texto, e o texto esta no papel assinado.
#   2. O TEOR DO ACERVO E O QUE O E-OFICIO GRAVOU. Acrescentar-lhe texto hoje
#      faria o sistema dizer que a ficha sempre disse aquilo — a ficha de papel
#      na estante nao mudou. E carimbo que mente e pior que carimbo nenhum.
#   3. JA EXISTE UM LUGAR PARA O ATO: `ri_atos`. Duplicar o texto dele dentro
#      do teor faria DOIS lugares guardando o mesmo fato, e eles divergiriam no
#      primeiro conserto — o ato corrigido por averbacao continuaria escrito no
#      teor com o texto antigo.
#
# O que faltava era a LEITURA, e ela e a mesma do papel: a ficha mostra o teor
# e mostra os atos. So que aqui a conta e feita antes de desenhar, para o ato
# que o texto JA conta nao aparecer duas vezes.
#
# A COMPARACAO E PELO TEXTO, E NAO PELO NUMERO — e esta e a diferenca entre
# esta funcao e `citados_no_teor`. La a pergunta e «este NUMERO ja foi usado
# nesta ficha?», e um `R-1/290` citado de passagem dentro de outra frase conta
# (e deve contar: o numero esta ocupado do mesmo jeito). Aqui a pergunta e
# «este TEXTO ja esta escrito?», e o rotulo NAO responde: medido, o texto de um
# ato cita o rotulo de outro o tempo todo — na matricula 11 o `R-1` esta
# escrito na ficha, e o mesmo texto cita `AV-2`, `R-3`, `AV-4` e `AV-5`, que
# nao estao. Quem responde e o texto do ato, inteiro.


def _sem_marcas(texto) -> str:
    """O texto como ele se le: sem marcacao, sem entidade e sem espaco dobrado.

    AS TRES NORMALIZACOES FORAM MEDIDAS, e sem qualquer uma delas a conta sai
    errada:

      MARCA      o teor do acervo e HTML (`<p>`, `<span style=…>`, `<div>`) e o
                 teor do ato novo vem de outra caixa de texto
      ENTIDADE   no acervo o espaco aparece escrito `&nbsp;` e `&#160;`, e no
                 ato novo ele e um espaco de verdade
      ESPACO     um vem com quebra de linha e indentacao no meio da frase, o
                 outro com a frase inteira numa linha

    Comparar sem isto daria ZERO achados nos mesmos 1.244 atos: os dois lados
    vem de fontes diferentes — um do editor do acervo, outro da caixa de texto
    de quem lavra.
    """
    limpo = unescape(re.sub(r"(?s)<[^>]+>", " ", str(texto or "")))
    return " ".join(limpo.split()).upper()


def texto_escrito_no_teor(teor_da_ficha, teor_do_ato) -> bool:
    """O TEXTO deste ato ja esta escrito dentro do texto da ficha?

    SO O TEXTO INTEIRO CONTA. O ato escrito na ficha esta escrito nela por
    inteiro — e o que a producao mostra, medida com esta funcao: **531 dos
    1.246 atos com teor estao escritos assim, todos em ficha ACERVO**, onde o
    E-Oficio escrevia o ato dentro do texto da matricula. Dos 715 que sobram,
    tambem todos de acervo, e sao esses que a ficha passa a mostrar, em 291
    fichas.

    **E ESTE PARAGRAFO DIZIA O CONTRARIO, E MENTIA** — conferido em 18/09/2026,
    junto com o relato #71. Escrevia «531 dos 1.244» e «todos em ficha
    ESTRUTURADA»: as 6 fichas ESTRUTURADA desta casa **nao tem um unico ato**,
    e os 531 sao de ACERVO. Sao **717** os atos que o teor nao conta — 715 com
    teor e 2 sem texto nenhum. **Numero escrito em comentario e numero que
    ninguem confere**, e este e justamente o que decide se um ato APARECE na
    ficha.

    Procurar so o comeco do ato seria a saida barata, e ela troca um erro por
    outro: o comeco de um ato desta casa e a frase de protocolo, que se repete
    entre atos da mesma ficha. **Aqui o falso positivo APAGA um ato da
    leitura** — o painel deixaria de mostrar um ato que a ficha tem, e ninguem
    desconfia de uma ficha que abre.

    Devolve `False` para ato sem teor: sem texto nao ha o que comparar, e o ato
    ainda tem rotulo, natureza e data para mostrar.
    """
    alvo = _sem_marcas(teor_do_ato)
    return bool(alvo) and alvo in _sem_marcas(teor_da_ficha)


def atos_fora_do_teor(teor_da_ficha, atos, matricula=None) -> list:
    """Os atos cujo texto AINDA NAO esta escrito no teor da ficha.

    E o que a ficha mostra depois do teor gravado. O ato que o texto ja conta
    fica de fora — ele ja esta la, e repeti-lo seria a ficha dizendo duas vezes
    a mesma coisa, uma dentro do teor e outra fora.

    Nao grava, nao edita o teor e nao cria ato. A ORDEM DOS ATOS E PRESERVADA:
    quem chama ja os ordenou por data, e reordenar aqui poria a leitura em
    ordem diferente da que a tela escolheu.

    **A DECISAO E PEDIDA A `texto_escrito_no_teor` (e, com a matricula, a
    `ato_transcrito_no_teor`), E NAO ESCRITA DE NOVO AQUI.** Duas contas
    dizendo «este texto ja esta escrito na ficha» divergem no primeiro
    conserto — e e esta conta que decide se um ato APARECE na ficha.

    HOTFIX SANDBOX-2026-10-19-02 — certidao de inteiro teor 70/2026, mat.
    9.001, saiu com DOIS R-01 (19/10/2026). Desde 06/10/2026 o teor de 3.972
    fichas foi SUBSTITUIDO pela transcricao da digitalizacao (ordem do
    oficial: «vale a digitalizacao»). A transcricao traz o ato inteiro, mas
    nao com as mesmas letras do E-Oficio — quebra de pagina no meio
    («[Ficha — Matricula 9.001 — pagina 3 de 4]»), rotulo com o CNM, a linha
    de assinatura. A comparacao pelo texto INTEIRO dava «nao esta no teor», e
    o ato do E-Oficio saia de novo depois do teor. Medido na producao em
    19/10/2026: **1.078 atos em 391 matriculas** saiam assim.

    Com `matricula` (linha com `numero` e `cnm`), um ato tambem conta como
    escrito quando `ato_transcrito_no_teor` diz que sim. Sem `matricula`, a
    regra e a de sempre.
    """
    numero = cnm = None
    if matricula is not None:
        dm = matricula if isinstance(matricula, dict) else dict(matricula)
        numero, cnm = dm.get("numero"), dm.get("cnm")
    cabecas = (cabecas_no_teor(numero, teor_da_ficha, cnm)
               if numero is not None else set())
    blocos = _blocos(teor_da_ficha) if cabecas else set()
    fora = []
    for a in atos or []:
        linha = a if isinstance(a, dict) else dict(a)
        if texto_escrito_no_teor(teor_da_ficha, linha.get("teor")):
            continue
        if cabecas and ato_transcrito_no_teor(
                teor_da_ficha, linha, numero, cnm,
                _cabecas=cabecas, _blocos_do_teor=blocos):
            continue
        fora.append(a)
    return fora


# ---------------------------------------- o ato TRANSCRITO dentro do teor
#
# HOTFIX SANDBOX-2026-10-19-02. A pergunta continua a de `texto_escrito_no_
# teor` — «este ato ja esta escrito na ficha?» —, mas para o teor que e a
# TRANSCRICAO da ficha de papel, em que as letras nao batem uma a uma com o
# E-Oficio. Duas provas, as DUAS exigidas:
#
#   1. O ROTULO DE CABECA. O teor abre um paragrafo com o rotulo do ato e o
#      numero (ou o CNM) DESTA matricula — `R-01/000000.2.0009001-76 (COMPRA
#      E VENDA)`. Rotulo citado no meio da frase NAO conta (a licao da
#      matricula 11, que cita AV-2, R-3, AV-4 e AV-5 dentro do R-1).
#   2. O TEXTO PARECIDO. Pelo menos 25% das sequencias de 6 palavras do ato
#      estao no teor. Sem isso o rotulo bate e o ato e outro — medido: o
#      ato 2.962 da 3.138 esta gravado como R-1 e o texto dele e o R-02 (a
#      cedula), que a transcricao nao traz; ele continua saindo.
#
# E UMA GUARDA: ato com selo gravado (`selo_texto`) nunca e escondido. Ato
# selado foi lavrado com selo do TJMA — se o rotulo dele bate com o da ficha,
# e numeracao em conflito, e o certo e o papel mostrar os dois para alguem
# conferir, e nao sumir com um ato selado.

ROTULO_CABECA = re.compile(
    r"(AV|R)[\s.\-]{0,2}0*(\d{1,3})\s*/\s*([\d.\-]{1,24}\d)", re.IGNORECASE)
_PALAVRAS_POR_BLOCO = 6
LIMIAR_TEXTO_TRANSCRITO = 0.25


def _linhas_do_teor(teor) -> list[str]:
    t = re.sub(r"(?i)<\s*(br|/?p|/?div|li|/?h\d|tr)\b[^>]*>", "\n",
               str(teor or ""))
    t = unescape(re.sub(r"(?s)<[^>]+>", " ", t))
    return [ln.strip() for ln in t.split("\n")]


def cabecas_no_teor(numero_da_matricula, teor, cnm=None) -> set:
    """Os rotulos `(tipo, numero)` que ABREM um paragrafo do teor e nomeiam
    esta matricula (pelo numero ou pelo CNM). So le."""
    meu = _so_digitos(numero_da_matricula)
    if not meu:
        return set()
    meu_cnm = _so_digitos(cnm) or meu
    achados = set()
    for ln in _linhas_do_teor(teor):
        ln = re.sub(r"^[\s\-\u2013\u2014.:*]*", "", ln)
        m = ROTULO_CABECA.match(ln)
        if m and _so_digitos(m.group(3)) in (meu, meu_cnm):
            achados.add((m.group(1).upper(), int(m.group(2))))
    return achados


def _blocos(texto) -> set:
    palavras = re.findall(r"\w+", _sem_marcas(texto))
    k = _PALAVRAS_POR_BLOCO
    return {tuple(palavras[i:i + k])
            for i in range(max(0, len(palavras) - k + 1))}


def _rotulos_do_ato(ato, meu, meu_cnm) -> set:
    rot = set()
    try:
        rot.add((str(ato.get("tipo") or "").upper(), int(ato.get("numero"))))
    except (TypeError, ValueError):
        pass
    # O rotulo com que o PROPRIO texto do ato abre, se nomear esta matricula
    # (o E-Oficio gravou atos com o numero da coluna diferente do texto).
    linhas = [ln for ln in _linhas_do_teor(ato.get("teor")) if ln]
    if linhas:
        m = ROTULO_CABECA.match(re.sub(r"^[\s\-\u2013\u2014.:*]*", "",
                                       linhas[0]))
        if m and _so_digitos(m.group(3)) in (meu, meu_cnm):
            rot.add((m.group(1).upper(), int(m.group(2))))
    return rot


def ato_transcrito_no_teor(teor_da_ficha, ato, numero_da_matricula, cnm=None,
                           *, _cabecas=None, _blocos_do_teor=None) -> bool:
    """Este ato ja esta TRANSCRITO no teor (rotulo de cabeca + texto parecido)?

    So le. Ato sem teor ou com selo gravado devolve `False`.
    """
    linha = ato if isinstance(ato, dict) else dict(ato)
    if str(linha.get("selo_texto") or "").strip():
        return False
    if not str(linha.get("teor") or "").strip():
        return False
    meu = _so_digitos(numero_da_matricula)
    if not meu:
        return False
    meu_cnm = _so_digitos(cnm) or meu
    cabecas = (_cabecas if _cabecas is not None
               else cabecas_no_teor(numero_da_matricula, teor_da_ficha, cnm))
    if not (_rotulos_do_ato(linha, meu, meu_cnm) & cabecas):
        return False
    do_ato = _blocos(linha.get("teor"))
    if not do_ato:
        return False
    do_teor = (_blocos_do_teor if _blocos_do_teor is not None
               else _blocos(teor_da_ficha))
    return len(do_ato & do_teor) / len(do_ato) >= LIMIAR_TEXTO_TRANSCRITO
