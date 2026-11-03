"""
Montagem do teor do ato notarial.

O QUE EU DESCOBRI LENDO OS 301 MODELOS IMPORTADOS
    Eles nao sao a procuracao inteira. Sao so a clausula de PODERES — comecam
    em "com amplos poderes para assinar contrato de compra de imovel..." e
    terminam ali. O comparecimento, a qualificacao das partes e o fecho o
    E-Oficio montava por fora, a partir do cadastro.

    Isso muda o desenho para melhor: a qualificacao nao precisa ser digitada,
    porque ja esta nas partes do ato, que por sua vez vieram da ficha de firma.
    O modelo entra so onde ele e insubstituivel — no que a procuracao autoriza.

A ESTRUTURA QUE ESTE MODULO MONTA
    1. epigrafe        LIVRO, FOLHA, natureza do ato
    2. comparecimento  "Saibam quantos este virem que, aos X dias..."
    3. qualificacao    uma parte por vez, na forma do art. 215, § 1º, do
                       Codigo Civil: nome, nacionalidade, estado civil,
                       profissao, documento e domicilio
    4. objeto          a clausula de poderes, que vem do modelo
    5. fecho           "Assim o disse, do que dou fe" e as assinaturas

O QUE ELE NAO FAZ
    Nao inventa clausula. O que o modelo nao disser, nao aparece; o que faltar
    na qualificacao aparece marcado, para o escrevente ver e completar. Texto
    de escritura montado por adivinhacao e defeito, nao comodidade.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime
from typing import Any

import modelos_da_casa as MODELOS
from bd_nativo import banco

# A epigrafe e o fecho mudam conforme o ato. Testamento tem forma propria e
# nao entra aqui: e ato de forma vinculada, e montar por template seria
# temerario — o modulo devolve so a moldura e o tabeliao escreve.
#
# A PROCURAÇÃO PARA EM «perante mim, Tabelião,» — 14/10/2026. O resto
# («compareceu como OUTORGANTE:» ou «compareceram como OUTORGANTES:») depende
# de quantos outorgam, e `montar` o escreve. Antes vinha fixo no singular.
#
# O TEXTO DE CADA ABERTURA E DE CADA FECHO SAIU DAQUI NO LF06D (19/10/2026):
# mora em `modelos_padrao/notas/NOTAS_ABERTURA_*.txt` e `NOTAS_FECHO_*.txt`, um
# papel por tipo de ato, editável na tela de Modelos. Aqui fica qual tipo tem
# abertura — o que não tem é de forma vinculada. `ABERTURAS` e `FECHOS`, os
# nomes antigos, continuam respondendo (`__getattr__`), lidos da base.
PAPEL_DA_ABERTURA = {
    "PROCURACAO": "NOTAS_ABERTURA_PROCURACAO",
    "ESCRITURA": "NOTAS_ABERTURA_ESCRITURA",
    "SUBSTABELECIMENTO": "NOTAS_ABERTURA_SUBSTABELECIMENTO",
    "REVOGACAO": "NOTAS_ABERTURA_REVOGACAO",
    "ATA": "NOTAS_ABERTURA_ATA",
}

PAPEL_DO_FECHO = {
    "PROCURACAO": "NOTAS_FECHO_PROCURACAO",
    "ESCRITURA": "NOTAS_FECHO_ESCRITURA",
    "SUBSTABELECIMENTO": "NOTAS_FECHO_SUBSTABELECIMENTO",
    "REVOGACAO": "NOTAS_FECHO_REVOGACAO",
    "ATA": "NOTAS_FECHO_ATA",
}

# O que falta na qualificacao aparece assim, e nao em branco: campo vazio passa
# despercebido na revisao, marcador nao.
def _falta(rotulo: str) -> str:
    return f"[{rotulo.upper()}]"


UF_EXTENSO = {
    "MA": "do Maranhão", "PI": "do Piauí", "TO": "do Tocantins",
    "PA": "do Pará", "CE": "do Ceará", "BA": "da Bahia", "GO": "de Goiás",
    "SP": "de São Paulo", "RJ": "do Rio de Janeiro", "MG": "de Minas Gerais",
    "DF": "do Distrito Federal",
}


def qualificar(parte: dict | Any, *, con: Any = None) -> str:
    """A qualificação de uma parte, na forma do art. 215, § 1º, do Código Civil.

    Ordem consagrada: nome, nacionalidade, estado civil, profissão, documento
    e domicílio. O que faltar sai marcado entre colchetes.

    A FRASE MORA NA BASE DESDE O LF06D — `NOTAS_QUALIFICACAO_PF` e `_PJ`; o
    que falta, e como se marca, continua decidido aqui.
    """
    textos = MODELOS.textos(con)
    p = dict(parte)
    nome = (p.get("nome") or "").strip().upper() or _falta("nome")

    if (p.get("tipo_pessoa") or "F").upper() == "J":
        doc = (p.get("documento") or "").strip()
        return textos.preencher(
            "NOTAS_QUALIFICACAO_PJ", nome=nome, documento=doc or _falta('cnpj'),
            endereco=p['endereco'] if p.get("endereco") else _falta('endereço'))

    doc = (p.get("documento") or "").strip()
    endereco = (p.get("endereco") or "").strip()
    estado_civil = (p.get("estado_civil") or "").strip().lower()
    return textos.preencher(
        "NOTAS_QUALIFICACAO_PF", nome=nome,
        nacionalidade=(p.get("nacionalidade") or "").strip().lower()
        or _falta("nacionalidade"),
        estado_civil=estado_civil or _falta("estado civil"),
        conjuge=_conjuge(p, estado_civil, textos),
        uniao_estavel=_uniao_estavel(p, textos),
        profissao=(p.get("profissao") or "").strip().lower() or _falta("profissão"),
        identidade=_identidade(p, textos),
        documento=doc or _falta('cpf'), endereco=endereco or _falta('endereço'))


# O QUE O CNN ART. 111 ACRESCENTOU À QUALIFICAÇÃO — LD07, 21/10/2026. «No ato
# notarial, serão inseridos na qualificação dos sujeitos: o nome completo ...;
# o documento de identificação, ou, na sua falta, a filiação; o número de CPF;
# a nacionalidade; o estado civil; a existência de união estável; a profissão;
# e o domicílio» — e o CC art. 215, § 1º, III, e o CN-MA art. 798, V, pedem o
# cônjuge e o regime de bens de quem é casado. Até aqui a qualificação só tinha
# os seis do Código Civil.
#
#   A REGRA DO QUE FALTA É A DOS OUTROS SEIS: sai marcado entre colchetes, e a
#   trava da lavratura (o campo em branco do teor) não deixa o ato ir ao livro
#   assim. A TESTEMUNHA fica de fora da marca: o art. 111 fala dos sujeitos do
#   ato, e a testemunha não é parte — o que ela tiver cadastrado entra, o que
#   não tiver não se cobra. O CÔNJUGE também, por outra razão: ver `_conjuge`.
#
#   Os dados moram na parte do ato (`nt_ato_partes`: `identidade`, `filiacao`,
#   `uniao_estavel`, `conjuge`, `regime_bens`); a parte que vem do cartão de
#   autógrafo já traz o RG, a filiação e o cônjuge de lá (`notas_partes`).
def _parte_do_ato(p: dict) -> bool:
    return not p.get("testemunha")


def _identidade(p: dict, textos) -> str:
    """O documento de identidade — ou, na falta dele, a filiação."""
    identidade = " ".join(str(p.get("identidade") or "").split())
    if identidade:
        return textos.preencher("NOTAS_QUALIFICACAO_PF__identidade", identidade=identidade)
    filiacao = " ".join(str(p.get("filiacao") or "").split())
    if filiacao:
        return textos.preencher("NOTAS_QUALIFICACAO_PF__filiacao", filiacao=filiacao)
    return ", " + _falta("documento de identidade ou filiação") if _parte_do_ato(p) else ""


#: As respostas da parte sobre a união estável, como a tela as grava.
UNIAO_ESTAVEL = ("SIM", "NAO")


def _uniao_estavel(p: dict, textos) -> str:
    """A existência de união estável, como a parte a declarou."""
    resposta = str(p.get("uniao_estavel") or "").strip().upper()
    if resposta == "SIM":
        companheiro = " ".join(str(p.get("conjuge") or "").split())
        return (textos("NOTAS_QUALIFICACAO_PF__uniao_estavel_sim")
                + (textos.preencher("NOTAS_QUALIFICACAO_PF__companheiro",
                                    companheiro=companheiro) if companheiro else ""))
    if resposta == "NAO":
        return textos("NOTAS_QUALIFICACAO_PF__uniao_estavel_nao")
    return ", " + _falta("união estável — sim ou não") if _parte_do_ato(p) else ""


def _casado(estado_civil: str) -> bool:
    return unicodedata.normalize("NFKD", estado_civil or "").lower().startswith("casad")


def _conjuge(p: dict, estado_civil: str, textos) -> str:
    """O cônjuge e o regime de bens de quem é casado. Quem não é: nada.

    NÃO SE MARCA A FALTA DOS DOIS: a lei os pede «quando necessário» (CC art.
    215, § 1º, III) e o CN-MA, «quando se tratar de bens imóveis» (art. 798,
    V) — e este montador não sabe de que é o ato. Exigir sempre ou só no ato
    de imóvel é pergunta ao oficial (relatorios/LD07.perguntas.md). Dito um
    dos dois, o outro sai marcado: a qualificação começada não fica pela metade.
    """
    if not _casado(estado_civil) or str(p.get("uniao_estavel") or "").upper() == "SIM":
        return ""
    conjuge = " ".join(str(p.get("conjuge") or "").split())
    regime = " ".join(str(p.get("regime_bens") or "").split())
    if not (conjuge or regime):
        return ""
    return textos.preencher("NOTAS_QUALIFICACAO_PF__conjuge",
                            conjuge=conjuge or _falta("cônjuge"),
                            regime_bens=regime or _falta("regime de bens"))


def _escapar(texto: Any) -> str:
    return (str(texto or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))



# Marca gravada no teor quando o bloco de assinaturas foi montado por cá —
# o traslado e o termo do livro a usam para não imprimir as linhas duas
# vezes (uma no @@TEOR@@ e outra em @@ASSINATURAS@@). Texto literal, não
# comentário HTML: o conversor ODF descarta comentário.
MARCA_ASSINATURAS = "@@FIM_DO_TEOR_ANTES_DAS_ASSINATURAS@@"


def _norm_titulo(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


def _texto_paragrafo(paragrafo: str) -> str:
    t = re.sub(r"</?[biu]>", "", paragrafo)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _resto_apos_titulo(plain: str, titulo: str) -> str | None:
    """None se o parágrafo inteiro é o título; plain inalterado se não casar."""
    tit_n = _norm_titulo(titulo)
    plain_n = _norm_titulo(plain)
    if not tit_n or not plain_n:
        return plain
    if plain_n == tit_n:
        return None
    if not plain_n.startswith(tit_n):
        return plain
    for k in range(1, len(plain) + 1):
        if _norm_titulo(plain[:k]) == tit_n:
            resto = plain[k:].lstrip(" .-–—:;")
            return resto if resto.strip() else None
    return plain


def teor_sem_titulo_duplicado(teor: str | None, titulo: str | None) -> str:
    """Tira do início do teor o nome do ato que o cabeçalho já imprime.

    Minutas importadas ou editadas no LibreOffice costumam trazer uma linha
    «ESCRITURA PÚBLICA DE …» (sozinha ou colada antes do «Saibam quantos…»).
    O traslado, o termo do livro e o `.odt` de rascunho já repetem o título
    no cabeçalho — o mesmo defeito que `rc_certidao.teor_sem_titulo` evita
    nas certidões do RCPN.
    """
    import notas_teor_arquivo as TA

    if not teor or not str(titulo or "").strip():
        return teor or ""
    paragrafos = TA.paragrafos_do_html(teor)
    if not paragrafos:
        return teor
    plain0 = _texto_paragrafo(paragrafos[0])
    resto = _resto_apos_titulo(plain0, str(titulo))
    if resto == plain0:
        return teor
    if resto is None:
        paragrafos = paragrafos[1:]
    else:
        paragrafos[0] = resto
    return TA.html_dos_paragrafos(paragrafos) if paragrafos else ""


def teor_sem_titulos_duplicados(teor: str | None, titulos: list[str]) -> str:
    """Aplica `teor_sem_titulo_duplicado` para cada título, do mais longo ao curto."""
    vistos: set[str] = set()
    saida = teor or ""
    ordenados = sorted(
        (t.strip() for t in titulos if str(t or "").strip()),
        key=len,
        reverse=True,
    )
    for titulo in ordenados:
        chave = _norm_titulo(titulo)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida = teor_sem_titulo_duplicado(saida, titulo)
    return saida


CHAVE_ASSINANTES = "assinantes_do_ato_e_a_condicao_em_que_assinam"


def texto_dos_assinantes(partes: list, *, con: Any = None) -> str:
    """Nome e condição de quem assina o ato, tirados da qualificação do formulário.

    Serve o campo `[ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]` do fecho
    das escrituras: o balcão já cadastrou as partes; não pede de novo. Ordem
    do formulário — principais e depois testemunhas. Quem lavrou assina no
    fecho próprio ("…assino em público e raso"), não nesta lista.
    """
    principais = [p for p in partes if not dict(p).get("testemunha")]
    testemunhas = [p for p in partes if dict(p).get("testemunha")]
    pedacos: list[str] = []
    for p in principais:
        d = dict(p)
        nome = (d.get("nome") or "").strip().upper()
        if not nome:
            continue
        qual = (d.get("qualificacao") or "").strip()
        pedacos.append(f"{nome}, {qual}" if qual else nome)
    for t in testemunhas:
        d = dict(t)
        nome = (d.get("nome") or "").strip().upper()
        if not nome:
            continue
        pedacos.append(f"{nome}, {MODELOS.textos(con)('NOTAS_FECHO_ESCRITURA__testemunha')}")
    return "; ".join(pedacos)


def bloco_de_assinaturas(partes: list, lavrado_nome: str | None = None,
                         lavrado_titulo: str | None = None, *,
                         con: Any = None) -> str:
    """Linhas de assinatura do instrumento: comparecentes, testemunhas e lavrado.

    O FECHO DIZ QUE TODOS ASSINAM; estas linhas são onde a caneta passa. O
    traslado, o termo do livro e o teor montado por `montar` usam o MESMO
    bloco — 1º traslado e termo do livro ficam alinhados nas assinaturas.

    A LINHA DE ASSINATURA MORA NA BASE DESDE O LF06D (peças `assinatura` e
    `assinatura_condicao` do traslado); quem assina, e em que ordem, é regra.
    """
    textos = MODELOS.textos(con)
    principais = [p for p in partes if not dict(p).get("testemunha")]
    testemunhas = [p for p in partes if dict(p).get("testemunha")]
    blocos: list[str] = []

    def _linha(nome: str, condicao: str | None = None) -> None:
        blocos.append(textos.preencher("NOTAS_TRASLADO__assinatura",
                                       nome=_escapar(nome)))
        if condicao:
            blocos.append(textos.preencher("NOTAS_TRASLADO__assinatura_condicao",
                                           condicao=_escapar(condicao)))

    for p in principais:
        d = dict(p)
        nome = (d.get("nome") or "").strip().upper() or _falta("nome")
        qual = (d.get("qualificacao") or "").strip()
        _linha(nome, qual or None)

    for t in testemunhas:
        d = dict(t)
        nome = (d.get("nome") or "").strip().upper() or _falta("nome")
        _linha(nome, textos("NOTAS_FECHO_ESCRITURA__testemunha"))

    quem = (lavrado_nome or "").strip()
    if quem:
        _linha(quem, (lavrado_titulo or "").strip() or None)
    elif not principais and not testemunhas:
        # Sem partes e sem lavrado: ainda assim deixa a linha do tabelião,
        # senão o papel sai sem onde assinar.
        _linha(_falta("quem lavrou"), None)

    return "\n".join(blocos)


def sem_bloco_de_assinaturas(teor: str | None) -> str:
    """O teor sem o bloco que `montar` acrescentou ao final. Só corta."""
    texto = teor or ""
    if MARCA_ASSINATURAS in texto:
        return texto.split(MARCA_ASSINATURAS, 1)[0].rstrip()
    return texto



def montar(tipo: str, partes: list, poderes: str | None,
           data_extenso: str, cidade: str = "", uf: str = "MA",
           objeto: str | None = None,
           lavrado_nome: str | None = None,
           lavrado_titulo: str | None = None, *, con: Any = None) -> str:
    """Monta o teor completo em HTML.

    `poderes` e o corpo do modelo — a parte que o E-Oficio guardava e que aqui
    entra tal como esta. `objeto` substitui os poderes quando o ato nao usa
    modelo, para a escritura de teor livre.
    """
    textos = MODELOS.textos(con)
    papel_da_abertura = PAPEL_DA_ABERTURA.get(tipo)
    if not papel_da_abertura:
        # Testamento e testamento cerrado tem forma vinculada: nao se monta por
        # template. Devolve so a qualificacao, para o tabeliao construir em volta.
        blocos = [textos("NOTAS_QUALIFICACAO_PF__partes_do_testamento")]
        blocos += [f"<p>{qualificar(p, con=textos)}.</p>" for p in partes]
        return "\n".join(blocos)

    # O ATO SAI EM TEXTO CORRIDO, NUM PARÁGRAFO SÓ — 14/10/2026, ordem do
    # oficial: «Todas procuracoes e escrituras sao em texto corrido, sem
    # espacos no meio do texto». Art. 795, § 2º, do Código de Normas: «a
    # escrituração deve ser seguida, sem claros ou espaços em branco».
    #
    #   ATÉ AQUI SAÍAM CINCO PARÁGRAFOS — a abertura, UM POR PARTE, os poderes
    #   e o fecho —, e o modelo do E-Ofício entrava cru, com os espaços
    #   duplos de dentro dele (181 dos 300 modelos têm). Medido o precedente:
    #   nas 209 procurações e 41 escrituras do E-Ofício, do «SAIBAM» ao fecho
    #   é UM parágrafo, e as partes vêm na mesma linha, separadas por «; e».
    #
    #   E A PROCURAÇÃO NÃO DIZIA QUEM É O PROCURADOR. As partes saíam todas
    #   atrás de «compareceu como OUTORGANTE:», cada uma com «— na qualidade
    #   de …», e o modelo emendava «a quem confere amplos poderes» sem a
    #   nomeação. O precedente tem a cláusula em 200 das 210: «Pela OUTORGANTE
    #   me foi dito que nomeia e constitui seu bastante PROCURADOR: …, a quem
    #   confere …» (a procuração 212, de 07/08/2026, é o modelo copiado).
    uf_extenso = UF_EXTENSO.get((uf or "").upper(), f"de {uf}")
    pedacos = [textos.preencher(papel_da_abertura, data_extenso=data_extenso,
                                cidade=cidade, uf_extenso=uf_extenso)]

    principais = [p for p in partes if not dict(p).get("testemunha")]
    testemunhas = [p for p in partes if dict(p).get("testemunha")]
    corpo = _em_linha(poderes or objeto or "")

    if tipo == "PROCURACAO":
        pedacos.append(_comparecimento_da_procuracao(principais, corpo, textos))
    else:
        if principais:
            pedacos.append("; e ".join(_parte_com_rotulo(p, textos)
                                       for p in principais) + ".")
        else:
            pedacos.append(_falta("nenhuma parte cadastrada no ato") + ".")
        pedacos.append(_fechar_frase(corpo) if corpo else
                       _falta("objeto do ato — escolha um modelo ou escreva aqui") + ".")

    if testemunhas:
        nomes = "; ".join((dict(t).get("nome") or "").strip().upper() for t in testemunhas)
        pedacos.append(textos.preencher("NOTAS_FECHO_ESCRITURA__testemunhas",
                                        nomes=nomes))

    fecho = textos(PAPEL_DO_FECHO.get(tipo, "NOTAS_FECHO_ESCRITURA"))
    # O fecho da escritura pede quem assina e em que condição — o mesmo campo
    # que «Preencher a partir do modelo» já completa sozinho com as partes.
    assinantes = texto_dos_assinantes(partes, con=textos)
    if assinantes:
        fecho = fecho.replace(f"[{CHAVE_ASSINANTES_ROTULO}]", assinantes)
    pedacos.append(fecho)

    texto = _corrido(" ".join(pedacos))
    # AS LINHAS DE ASSINATURA — mesmo bloco do traslado (pedido 18/09/2026).
    # A marca separa o teor narrativo do bloco, para o traslado nao duplicar.
    # Elas continuam linhas próprias: são onde a caneta passa, e não o meio
    # do texto.
    return "\n".join([f"<p>{texto}</p>", MARCA_ASSINATURAS, bloco_de_assinaturas(
        partes, lavrado_nome=lavrado_nome, lavrado_titulo=lavrado_titulo,
        con=textos)])


CHAVE_ASSINANTES_ROTULO = "ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM"


# O CLARO DE «X» DOS MODELOS DO E-OFÍCIO — 14/10/2026. Trinta e nove dos 300
# modelos marcam o dado a escrever com uma fileira de X («o veículo :
# XXXXXXXXXXXXXXXXXXX»), e não com `[CAMPO]`: o detector de campo em branco
# não os via, e a procuração 802 foi lavrada assim. Quatro X seguidos não são
# palavra nem numeral romano em ato desta casa.
_CLARO_DE_X = re.compile(r"[Xx]{4,}")


def claros_de_x(teor: str | None) -> list[str]:
    """As fileiras de X que sobraram no texto — dado do modelo não escrito."""
    plano = re.sub(r"<[^>]+>", " ", teor or "")
    return sorted({m.group(0) for m in _CLARO_DE_X.finditer(plano)})


# A escolha `{ROTULO: a | b}` e a cláusula `«SE ROTULO: …»` que o leitor dos
# modelos não alcança — uma dentro da outra, como na minuta do usufruto e na
# das diretivas antecipadas. Não viram campo nem pendência, e iam ao livro com
# as chaves (LT02, 20/10/2026). O rótulo é o do leitor: até seis palavras em
# maiúsculas antes dos dois pontos.
_MARCA_SOBRANDO = re.compile(
    r"\{\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 ]{1,60}):|«\s*(SE [^:«»]{1,60}):")


def marcas_de_modelo_sobrando(teor: str | None) -> list[str]:
    """Os rótulos de escolha e de cláusula do modelo que sobraram no texto."""
    plano = re.sub(r"<[^>]+>", " ", teor or "")
    return sorted({" ".join((m.group(1) or m.group(2)).split())
                   for m in _MARCA_SOBRANDO.finditer(plano)})


def _em_linha(html: str | None) -> str:
    """O trecho do modelo como texto de DENTRO de um parágrafo.

    Tira `<p>`, `<div>` e `<br>` — que abririam linha nova no meio do ato — e
    deixa o resto (`<b>`, `<i>`, `<u>`). Texto solto, sem marcação, é
    escapado. O espaço duplo sai em `_corrido`.
    """
    bruto = (html or "").strip()
    if not bruto:
        return ""
    if not bruto.startswith("<"):
        return _escapar(bruto)
    bruto = re.sub(r"(?i)<br\s*/?>", " ", bruto)
    bruto = re.sub(r"(?i)</?(p|div)(\s[^>]*)?>", " ", bruto)
    return bruto.strip()


def _corrido(texto: str) -> str:
    """Um espaço entre palavras, nenhum antes de pontuação — art. 795, § 2º.

    É a régua de `notas_modelos.texto_corrido`, a mesma dos modelos do
    submódulo: uma só, para as duas montagens não divergirem.
    """
    from notas_modelos import texto_corrido
    return texto_corrido(re.sub(r"\s+", " ", texto or ""))


def _fechar_frase(texto: str) -> str:
    """Garante o ponto final antes da frase seguinte do ato."""
    t = (texto or "").rstrip()
    plano = re.sub(r"<[^>]+>", "", t).rstrip()
    return t if not plano or plano[-1] in ".;:!?" else t + "."


def _rotulo(parte) -> str:
    return (dict(parte).get("qualificacao") or "").strip().upper()


def _parte_com_rotulo(parte, textos: Any = None) -> str:
    """«como VENDEDOR, <qualificação>» — a forma da escritura 256 do E-Ofício."""
    textos = MODELOS.textos(textos)
    rotulo = _rotulo(parte)
    if not rotulo:
        return qualificar(parte, con=textos)
    return textos.preencher("NOTAS_ABERTURA_ESCRITURA__parte_com_papel", papel=rotulo,
                            qualificacao=qualificar(parte, con=textos))


def _qualificacao_no_lado(parte, *, esperado: tuple[str, ...],
                          textos: Any = None) -> str:
    """A qualificação da parte; o papel só aparece quando não é o óbvio.

    Na procuração, «OUTORGANTE» e «PROCURADOR» já estão ditos pela própria
    frase. Papel diferente (anuente, cônjuge, representante) continua escrito
    — sumir com ele apagaria o que o escrevente qualificou.
    """
    textos = MODELOS.textos(textos)
    rotulo = _rotulo(parte)
    texto = qualificar(parte, con=textos)
    if rotulo and not any(x in _sem_acento_maiusculo(rotulo) for x in esperado):
        texto += ", " + textos.preencher("NOTAS_ABERTURA_PROCURACAO__na_qualidade",
                                         papel=rotulo)
    return texto


def _comparecimento_da_procuracao(principais: list, poderes: str,
                                  textos: Any = None) -> str:
    """Comparecimento, reconhecimento, nomeação e poderes — numa frase corrida.

    Copiado da procuração 212 do E-Ofício (07/08/2026), o precedente mais
    recente desta casa. O plural acompanha quantos outorgam e quantos são
    nomeados; o gênero fica em «(a)», como já faz `qualificar`, porque a
    parte não tem sexo cadastrado.

    AS DUAS METADES DA FRASE MORAM NA BASE DESDE O LF06D — peças da abertura da
    procuração, uma no singular e outra no plural para cada lado; quantos são
    de cada lado é regra, e fica aqui.
    """
    textos = MODELOS.textos(textos)
    lado_a, lado_b, por_outro = [], [], []
    reps = representantes_por_parte(principais)
    ligados = {r.get("id") for lista in reps.values() for r in lista}
    for p in principais:
        # na procuração o anuente continua entre os outorgantes, «na qualidade de ANUENTE»
        lado = lado_da_parte(p, "PROCURACAO")
        if lado == REPRESENTA and dict(p).get("id") in ligados:
            continue                      # sai na qualificação de quem ele representa (item 2)
        (lado_b if lado == OUTORGADO else por_outro if lado == REPRESENTA else lado_a).append(p)
    varios = len(lado_a) > 1
    if lado_a:
        outorgantes = "; e ".join(_qualificacao_no_lado(p, esperado=("OUTORGANT",), textos=textos)
                                  + _representacao(p, reps, textos) for p in lado_a)
    else:
        outorgantes = _falta("outorgante — inclua quem outorga no quadro Partes")
    if lado_b:
        procuradores = "; e ".join(
            _qualificacao_no_lado(p, esperado=("OUTORGAD", "PROCURADOR"), textos=textos)
            + _representacao(p, reps, textos) for p in lado_b)
    else:
        procuradores = _falta("procurador — inclua o outorgado no quadro Partes")
    if por_outro:
        procuradores += "; " + "; ".join(_quem_representa(p, textos) for p in por_outro)
    frase = (textos.preencher("NOTAS_ABERTURA_PROCURACAO__varios_outorgantes"
                              if varios else "NOTAS_ABERTURA_PROCURACAO__um_outorgante",
                              outorgantes=outorgantes)
             + " " + textos.preencher(
                 "NOTAS_ABERTURA_PROCURACAO__varios_procuradores" if len(lado_b) > 1
                 else "NOTAS_ABERTURA_PROCURACAO__um_procurador",
                 procuradores=procuradores))
    if not poderes:
        return frase + ", " + _falta("poderes — escolha um modelo ou escreva aqui") + "."
    plano = re.sub(r"<[^>]+>", "", poderes).lstrip()
    # «a quem confere», «com amplos poderes» — o modelo continua a frase.
    # O que começa por número ou maiúscula («1 - PODERES …») abre frase nova.
    liga = ". " if plano[:1].isdigit() or plano[:1].isupper() else ", "
    return frase + liga + _fechar_frase(poderes)


# A SEGUNDA METADE DO ATO — quem RECEBE (comprador, donatário, procurador).
# Achada de 07/09/2026: os modelos de `notas_modelos.py` usam
# `{{ outorgantes }}` e `{{ outorgados }}`, e nada no sistema os montava —
# a tela de "Preencher a partir do modelo" só troca `[CAMPO]`, `{ESCOLHA}` e
# `«SE»`, nunca Jinja. O ato sairia com as chaves duplas escritas por cima do
# nome das partes, no documento que a serventia assina.
#
# A REGRA E A QUALIFICAÇÃO QUE O ESCREVENTE JÁ DIGITOU, e não uma lista fechada
# de papéis: bater em uma destas palavras manda a parte para a segunda metade;
# o resto — vendedor, doador, outorgante, substabelecente, renunciante, ou
# parte sem qualificação — fica na primeira. Testemunha não entra em nenhuma
# das duas: nenhum destes modelos as cita dentro do corpo.
#
# O LADO PELA QUALIDADE DA CEP, E NÃO POR PEDAÇO DE PALAVRA — ensaio de atos das Notas, 03/11/2026
# (relatorio_notas.md, item 1; o conserto liberado pela sessão de PRs no mesmo dia). A regra de antes
# procurava «OUTORGADO», «COMPRADOR», «DONATARIO» e «PROCURADOR» DENTRO da qualificação, e o ensaio
# lavrou: o procurador do vendedor como OUTORGADO COMPRADOR; quem representa a compradora, a mãe do
# donatário menor e a assistente da nubente como outorgantes; e «OUTORGADA» — que não contém
# «OUTORGADO» — do lado dos outorgantes, deixando a procuração sem procurador. Agora a qualificação
# inteira, ou a primeira palavra dela («OUTORGADO COMPRADOR»), é lida na tabela da CEP
# (`notas_censec.QUALIFICACAO_PARA_CEP`), que já conhece o feminino e o cessionário.
#
# QUEM COMPARECE POR OUTRO NÃO É LADO — procurador (fora da procuração, onde ele é o outorgado),
# representante, assistente, quem assina a rogo: os prefixos que a CEP chama de interveniente
# (`notas_censec.PREFIXOS_INTERVENIENTE`). Sai qualificado, com a marca de onde deve ficar: o quadro
# «Partes» ainda não diz QUEM ele representa nem o instrumento (CN-MA art. 798, VI e VII; item 2 do
# relatório, à espera do oficial). A marca trava a lavratura até o escrevente pô-lo junto de quem
# representa — o que antes ninguém notava, porque ele saía do lado errado sem aviso.
OUTORGANTE, OUTORGADO, REPRESENTA = "OUTORGANTE", "OUTORGADO", "REPRESENTA"

# O ANUENTE CONSENTE, E NÃO VENDE — decisão do oficial, 03/11/2026 (ensaio de atos das Notas, item 3).
# No imóvel do casal em comunhão a casa põe os dois cônjuges como outorgantes, e ninguém é anuente; o
# «ANUENTE», onde cabe (o bem particular de um deles, por exemplo), sai depois dos outorgantes com a
# frase do consentimento (CC art. 1.647, I) — e nunca como mais um deles, que é o que o ensaio lavrou.
ANUENTE = "ANUENTE"

# O ADVOGADO ASSISTE, E NÃO É PARTE — decisão do oficial, 03/11/2026 (ensaio de atos das Notas, item 5).
# Ele entrava entre «as partes … todas maiores, capazes e concordes» do inventário e do divórcio, e o
# parágrafo «DOS ADVOGADOS» o pedia de novo num campo livre da minuta. Fica fora dos lados, e o
# parágrafo é montado dele (`advogados_qualificados`), com a OAB do quadro «Partes».
ADVOGADO = "ADVOGADO"


def _sem_acento_maiusculo(texto) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(texto or "").upper())
    return "".join(c for c in s if not unicodedata.combining(c))


def lado_da_parte(parte, tipo_ato: Any = None) -> str:
    """OUTORGANTE, OUTORGADO ou REPRESENTA (quem comparece por outra parte). So calcula.

    Sem o tipo do ato, o procurador continua outorgado, como antes: quem chama sem o tipo monta
    procuração (`notas_procuracao_ensaio`).
    """
    import notas_censec as NC
    rotulo = " ".join(_sem_acento_maiusculo(dict(parte).get("qualificacao")).split())
    if rotulo.startswith(NC.PREFIXOS_INTERVENIENTE):
        if rotulo.startswith("PROCURADOR") and (
                tipo_ato is None or str(tipo_ato).upper() in NC.ATOS_EM_QUE_O_PROCURADOR_E_OUTORGADO):
            return OUTORGADO
        return REPRESENTA
    if rotulo.startswith(ANUENTE):
        return ANUENTE
    if rotulo.startswith("ADVOGAD"):
        return ADVOGADO
    primeira = re.split(r"[\s,;/(]", rotulo, maxsplit=1)[0]
    if OUTORGADO in {NC.QUALIFICACAO_PARA_CEP.get(rotulo, "").upper(),
                     NC.QUALIFICACAO_PARA_CEP.get(primeira, "").upper()}:
        return OUTORGADO
    return OUTORGANTE


def _quem_representa(parte, textos: Any = None) -> str:
    """A qualificação de quem comparece por outro, com a marca de onde ele deve ficar."""
    return (qualificar(parte, con=textos) + " "
            + _falta(f"{_rotulo(parte)} — diga junto de quem representa, com o instrumento "
                     "(CN-MA art. 798, VI e VII)"))


# A REPRESENTAÇÃO NA QUALIFICAÇÃO DO REPRESENTADO — decisão do oficial, 03/11/2026 (ensaio de atos das
# Notas, item 2): «…, neste ato representado por FULANO, conforme procuração lavrada no livro X, folha
# Y, do …», como no CN-MA art. 798, VI (e, para o menor e o incapaz, o VII: por quem está assistido ou
# representado). Quem representa diz no quadro «Partes» a parte que representa e o instrumento; sem a
# parte, ele continua marcado fora dos lados (`_quem_representa`); sem o instrumento, o instrumento é
# que fica marcado.
def representantes_por_parte(partes: list) -> dict[int, list[dict]]:
    """{id da parte representada: [quem a representa ou assiste]}, das partes deste ato. So calcula."""
    ids = {dict(p).get("id") for p in partes}
    reps: dict[int, list[dict]] = {}
    for p in partes:
        d = dict(p)
        alvo = d.get("representa_parte_id")
        if alvo and alvo in ids and alvo != d.get("id") and not d.get("testemunha"):
            reps.setdefault(alvo, []).append(d)
    return reps


def _representacao(parte, reps: dict, textos: Any = None) -> str:
    """«, neste ato representado(a) por <qualificação>, conforme <instrumento>» — ou nada."""
    frases = []
    for r in reps.get(dict(parte).get("id"), []):
        papel = _sem_acento_maiusculo(r.get("qualificacao"))
        if papel.startswith("ASSINA A ROGO"):
            # quem assina a rogo não representa: assina pela parte que não sabe ou não pode (CC art.
            # 215, § 2º), e o instrumento não cabe
            frases.append(", que não sabe ou não pode assinar, assinando a seu rogo "
                          + qualificar(r, con=textos) + " (Código Civil, art. 215, § 2º)")
            continue
        verbo = "assistido(a)" if papel.startswith("ASSISTENTE") else "representado(a)"
        instrumento = " ".join(str(r.get("representa_instrumento") or "").split())
        frases.append(f", neste ato {verbo} por " + qualificar(r, con=textos) + ", "
                      + (f"conforme {instrumento}" if instrumento else
                         _falta("instrumento da representação — livro, folha e serventia da "
                                "procuração, o contrato social ou o assento (CN-MA art. 798, VI e VII)")))
    return "".join(frases)


def _quem_consente(parte, textos: Any = None) -> str:
    """O cônjuge anuente, com a frase do consentimento (CC art. 1.647, I)."""
    return ("e, como ANUENTE, " + qualificar(parte, con=textos)
            + ", que consente no presente ato, na forma do artigo 1.647, I, do Código Civil")


def partes_por_lado(partes: list, *, con: Any = None, tipo_ato: Any = None) -> tuple[str, str]:
    """Monta `outorgantes` e `outorgados` para os modelos de `notas_modelos.py`.

    O QUE FALTAR FICA MARCADO, E NÃO EM BRANCO — a mesma regra de `_falta()`:
    lado sem parte nenhuma sairia sem ninguém notar, e quem confere o teor
    precisa ver que falta qualificar alguém, não uma lacuna muda. Quem
    comparece por outro vai ao fim dos OUTORGANTES, com a marca (ver acima):
    é o lado que toda minuta tem — a do divórcio, do inventário e do pacto
    só têm `{{ outorgantes }}`, e no fim dos outorgados ele sumiria do teor.
    """
    textos = MODELOS.textos(con)
    lados = {OUTORGANTE: [], OUTORGADO: [], REPRESENTA: [], ANUENTE: [], ADVOGADO: []}
    montar = {REPRESENTA: _quem_representa, ANUENTE: _quem_consente}
    reps = representantes_por_parte(partes)
    ligados = {r.get("id") for lista in reps.values() for r in lista}
    for p in partes:
        d = dict(p)
        if d.get("testemunha"):
            continue
        lado = lado_da_parte(d, tipo_ato)
        if lado == REPRESENTA and d.get("id") in ligados:
            continue                      # sai na qualificação de quem ele representa
        if lado == ADVOGADO:
            continue                      # sai no parágrafo «DOS ADVOGADOS» (`advogados_qualificados`)
        texto = montar[lado](d, textos) if lado in montar else qualificar(d, con=textos)
        lados[lado].append(texto + _representacao(d, reps, textos))
    outorgantes = ("; ".join(lados[OUTORGANTE]) or
                   _falta("outorgante(s) — qualifique a parte no ato"))
    if lados[ANUENTE]:
        outorgantes += "; " + "; ".join(lados[ANUENTE])
    if lados[REPRESENTA]:
        outorgantes += "; " + "; ".join(lados[REPRESENTA])
    outorgados = ("; ".join(lados[OUTORGADO]) or
                  _falta("outorgado(s) — qualifique a parte no ato"))
    return outorgantes, outorgados


def testemunhas_qualificadas(partes: list, *, con: Any = None) -> str:
    """Texto Jinja `{{ testemunhas }}` nos modelos de ata e testamento."""
    ts = [p for p in partes if dict(p).get("testemunha")]
    if not ts:
        return _falta("testemunha(s) — cadastre no ato se houver")
    textos = MODELOS.textos(con)
    return "; ".join(qualificar(t, con=textos) for t in ts)


def advogados_qualificados(partes: list, *, con: Any = None) -> str:
    """Texto Jinja `{{ advogados }}`: cada advogado do ato, qualificado, com a inscrição na OAB."""
    textos = MODELOS.textos(con)
    advogados = [dict(p) for p in partes
                 if not dict(p).get("testemunha") and lado_da_parte(p) == ADVOGADO]
    if not advogados:
        return _falta("advogado — inclua-o no quadro Partes, com a OAB")
    saida = []
    for a in advogados:
        numero = " ".join(str(a.get("oab_numero") or "").split())
        uf = str(a.get("oab_uf") or "").strip().upper()
        oab = (f"inscrito(a) na OAB/{uf} sob o nº {numero}" if numero and uf else
               _falta("inscrição na OAB — número e UF no quadro Partes"))
        saida.append(qualificar(a, con=textos) + ", " + oab)
    return "; ".join(saida)


def contexto_jinja_partes(partes: list, *, con: Any = None, tipo_ato: Any = None) -> dict[str, str]:
    """Variáveis Jinja comuns aos modelos de `notas_modelos.py`."""
    textos = MODELOS.textos(con)
    outorgantes, outorgados = partes_por_lado(partes, con=textos, tipo_ato=tipo_ato)
    return {
        "outorgantes": outorgantes,
        "outorgados": outorgados,
        "testemunhas": testemunhas_qualificadas(partes, con=textos),
        "advogados": advogados_qualificados(partes, con=textos),
    }


def pendencias_da_qualificacao(partes: list) -> list[str]:
    """Diz quem está incompleto, com nome, antes de o ato ser lavrado.

    Desde o LD07 (21/10/2026) conta também o que o CNN art. 111 pôs na
    qualificação da pessoa física — o documento de identidade ou a filiação,
    a união estável — e, de quem é casado e disse um dos dois, o cônjuge ou o
    regime de bens que falta: os mesmos que `qualificar` marca entre colchetes.
    """
    faltas = []
    for p in partes:
        d = dict(p)
        if d.get("testemunha"):
            continue
        fisica = (d.get("tipo_pessoa") or "F").upper() != "J"
        exigidos = ("documento",) if not fisica else \
                   ("documento", "nacionalidade", "estado_civil", "profissao", "endereco")
        vazios = [c.replace("_", " ") for c in exigidos if not str(d.get(c) or "").strip()]
        if fisica:
            if not (str(d.get("identidade") or "").strip()
                    or str(d.get("filiacao") or "").strip()):
                vazios.append("documento de identidade ou filiação")
            uniao = str(d.get("uniao_estavel") or "").strip().upper()
            if uniao not in UNIAO_ESTAVEL:
                vazios.append("união estável")
            # o cônjuge e o regime só contam quando um dos dois foi dito — a
            # mesma regra de `_conjuge`
            casal = (("cônjuge", "conjuge"), ("regime de bens", "regime_bens"))
            if (_casado(str(d.get("estado_civil") or "")) and uniao != "SIM"
                    and any(str(d.get(campo) or "").strip() for _, campo in casal)):
                vazios += [c for c, campo in casal if not str(d.get(campo) or "").strip()]
        if vazios:
            faltas.append(f"{d.get('nome') or 'parte sem nome'}: {', '.join(vazios)}")
    return faltas


# A EMANCIPAÇÃO CONFERE A IDADE — ensaio de atos das Notas, 03/11/2026 (relatorio_notas.md, item 7;
# conserto liberado pela sessão de PRs no mesmo dia). A minuta afirma «portanto com dezesseis anos
# completos» de qualquer data digitada, e o ensaio lavrou a emancipação de quem nasceu no mês do ato.
# CC art. 5º, par. ún., I: a concessão dos pais é para o menor com dezesseis anos completos; quem já
# tem dezoito é capaz e não se emancipa (art. 5º, caput). O campo é texto livre na tela: a data tem
# de vir com os algarismos (dd/mm/aaaa, como a casa já escreve entre parênteses), para ser conferida.
CHAVE_NASCIMENTO_DO_EMANCIPANDO = "data_de_nascimento_do_emancipando"
_DATA_EM_ALGARISMOS = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b")


def recusa_da_emancipacao(valores: dict, hoje: date) -> str:
    """O motivo de não montar o teor da emancipação, ou "" quando a idade confere. So calcula."""
    if CHAVE_NASCIMENTO_DO_EMANCIPANDO not in valores:
        return ""
    texto = str(valores.get(CHAVE_NASCIMENTO_DO_EMANCIPANDO) or "")
    m = _DATA_EM_ALGARISMOS.search(texto)
    if not m:
        return ("Escreva a data de nascimento do emancipando com os algarismos (dd/mm/aaaa), "
                "para a idade ser conferida (Código Civil, art. 5º, parágrafo único, I).")
    try:
        nasceu = (date(int(m[3]), int(m[2]), int(m[1])) if m[1]
                  else date(int(m[4]), int(m[5]), int(m[6])))
    except ValueError:
        return f"A data de nascimento do emancipando não existe: «{texto.strip()}»."
    anos = hoje.year - nasceu.year - ((hoje.month, hoje.day) < (nasceu.month, nasceu.day))
    if anos < 16:
        return (f"O emancipando tem {anos} ano(s): a emancipação pelos pais exige dezesseis anos "
                "completos (Código Civil, art. 5º, parágrafo único, I).")
    if anos >= 18:
        return (f"O emancipando já tem {anos} anos: é maior e capaz, e não se emancipa "
                "(Código Civil, art. 5º).")
    return ""


# O ESTADO CIVIL DO TESTAMENTO É O DA PARTE — ensaio de atos das Notas, 03/11/2026 (relatorio_notas.md,
# item 4; conserto liberado pela sessão de PRs no mesmo dia). A escolha da minuta começava em
# «solteiro» e o ensaio lavrou o testador «casado com …» na qualificação declarando «ser solteiro» na
# primeira disposição (CC art. 215, § 1º, III, e art. 1.864, I). A escolha, a cláusula do casado e o
# cônjuge passam a vir da parte TESTADOR; o escrevente que escolheu outra coisa é avisado.
_ESTADO_CIVIL_DA_MINUTA = (("SOLTEIR", "solteiro"), ("CASAD", "casado"), ("DIVORCIAD", "divorciado"),
                           ("VIUV", "viúvo"), ("SEPARAD", "separado judicialmente"))


def estado_civil_do_testador(valores: dict, partes: list) -> list[str]:
    """Põe em `valores` o estado civil, a cláusula do casado e o cônjuge da parte TESTADOR, e devolve
    os avisos do que a tela dizia diferente. Só mexe na minuta que tem a escolha."""
    if "op_estado_civil_do_testador" not in valores:
        return []
    testador = next((dict(p) for p in partes if not dict(p).get("testemunha")
                     and _sem_acento_maiusculo(dict(p).get("qualificacao")).startswith("TESTADOR")), None)
    if not testador:
        return []
    estado = _sem_acento_maiusculo(testador.get("estado_civil"))
    escolha = next((opcao for raiz, opcao in _ESTADO_CIVIL_DA_MINUTA if raiz in estado), "")
    convive = str(testador.get("uniao_estavel") or "").upper() == "SIM"
    if convive and escolha != "casado":
        escolha = "convivente em união estável"
    if not escolha:
        return []
    avisos = []
    digitada = (valores.get("op_estado_civil_do_testador") or "").strip()
    if digitada and digitada != escolha:
        avisos.append(f"Estado civil do testador: a tela dizia «{digitada}», e a parte é «{escolha}» — "
                      "vale o da parte (corrija a parte, se for ela a errada).")
    valores["op_estado_civil_do_testador"] = escolha
    com_alguem = escolha in ("casado", "convivente em união estável")
    valores["se_se_casado_ou_convivente"] = "1" if com_alguem else ""
    if com_alguem:
        valores["op_conjuge_ou_convivente"] = "cônjuge" if escolha == "casado" else "convivente"
        for campo, da_parte in (("nome_e_qualificacao_do_conjuge_ou_convivente", "conjuge"),
                                ("regime_de_bens", "regime_bens")):
            if not str(valores.get(campo) or "").strip() and str(testador.get(da_parte) or "").strip():
                valores[campo] = str(testador[da_parte]).strip()
    return avisos


def valores_campos_data_lavratura(quando: datetime) -> dict[str, str]:
    """Campos `[DIA POR EXTENSO]` etc. dos modelos SISTEMA, para a data do selo."""
    from notas_livro import por_extenso
    from ri_web import MESES

    d = quando.date()
    h, m = quando.hour, quando.minute
    hora_alg = str(h) if m == 0 else f"{h:02d}:{m:02d}"
    hora_ext = por_extenso(h)
    if m:
        hora_ext = f"{hora_ext} e {por_extenso(m)}"
    return {
        "dia_por_extenso": por_extenso(d.day),
        "dia_em_algarismos": str(d.day),
        "mes_por_extenso": MESES[d.month - 1],
        "ano_por_extenso": por_extenso(d.year),
        "ano_em_algarismos": str(d.year),
        "hora_por_extenso": hora_ext,
        "hora_em_algarismos": hora_alg,
    }


def atualizar_teor_para_data_de_selo(
    con: sqlite3.Connection,
    ato_id: int,
    *,
    quando: datetime,
    sv: dict,
    lavrado_nome: str,
    lavrado_titulo: str,
) -> dict[str, Any]:
    """Alinha `data`, `hora` e a data escrita no teor com o dia em que o selo sai.

    Relato #116: o teor costuma ser montado dias antes; traslado/termo já usam
    «hoje» na exportação, mas o HTML gravado no ato ficava com a data antiga.

    **SÓ SE TROCA A DATA ESCRITA, E NUNCA SE REMONTA O TEXTO — correção de
    14/10/2026.** Até aqui esta função montava o teor DE NOVO a partir do
    modelo (`montar` para os do E-Ofício, `preencher` para os do submódulo) e
    gravava por cima — e ela roda DEPOIS do lançamento, com o ato já no livro.
    Tudo o que o escrevente tinha corrigido à mão sumia. Medido na produção:
    os quatro atos editados antes do selo (778, 788, 791 e 802) ficaram com
    texto diferente da última edição; na procuração 802 as 6.010 letras
    editadas (o veículo identificado, o procurador nomeado) viraram as 2.976
    do modelo cru, com «XXXXXXXXXXXXXXXXXXX» no lugar do veículo — e o termo
    do livro foi impresso depois disso. No ramo do E-Ofício a remontagem
    acontecia até no mesmo dia, quando não havia data nenhuma a trocar.

    Agora: troca-se, no texto gravado, a data por extenso de `data_por_extenso`
    e a frase de data dos modelos do submódulo (montada com os valores que o
    escrevente gravou); o resto do teor não se toca. Se a data mudou e o texto
    não a escreve de nenhuma das duas formas, o teor fica como está e volta um
    `aviso` — a tela diz para conferir, em vez de reescrever o que alguém
    escreveu.
    """
    from ri_web import data_por_extenso

    bd = banco(con)
    row = bd.um("SELECT * FROM nt_atos WHERE id=%s", (int(ato_id),))
    if not row:
        return {"ok": False, "motivo": "ato inexistente"}
    ato = dict(row)
    data_iso = quando.date().isoformat()
    hora = quando.strftime("%H:%M")
    teor = ato.get("teor") or ""
    teor_novo: str | None = None
    modelo_valores_json: str | None = None
    aviso: str | None = None

    try:
        valores = json.loads(ato.get("modelo_valores") or "{}") or {}
    except (TypeError, ValueError):
        valores = {}
    if not isinstance(valores, dict):
        valores = {}
    novos = valores_campos_data_lavratura(quando)

    trocas: list[tuple[str, str]] = []
    data_velha = ato.get("data") or ""
    if data_velha and data_velha != data_iso:
        try:
            trocas.append((data_por_extenso(date.fromisoformat(data_velha)),
                           data_por_extenso(quando.date())))
        except ValueError:
            pass
        frase = ("{dia_por_extenso} ({dia_em_algarismos}) dias do mês de "
                 "{mes_por_extenso} do ano de {ano_por_extenso} ({ano_em_algarismos})")
        chaves = ("dia_por_extenso", "dia_em_algarismos", "mes_por_extenso",
                  "ano_por_extenso", "ano_em_algarismos")
        if all(str(valores.get(k) or "").strip() for k in chaves):
            trocas.append((frase.format(**{k: valores[k] for k in chaves}),
                           frase.format(**novos)))
    if (str(valores.get("hora_por_extenso") or "").strip()
            and str(valores.get("hora_em_algarismos") or "").strip()):
        velha = f"{valores['hora_por_extenso']} ({valores['hora_em_algarismos']}) horas"
        nova = f"{novos['hora_por_extenso']} ({novos['hora_em_algarismos']}) horas"
        if velha != nova:
            trocas.append((velha, nova))

    texto = teor
    for velho, novo in trocas:
        # Espaço e quebra de linha entre as palavras não decidem nada: o
        # mesmo texto gravado por outra tela pode ter um ou outro.
        padrao = r"\s+".join(re.escape(pedaco) for pedaco in velho.split())
        texto = re.sub(padrao, lambda _m, novo=novo: novo, texto)
    if texto != teor:
        teor_novo = texto
        if any(k in valores for k in novos):
            valores.update({k: v for k, v in novos.items() if k in valores})
            modelo_valores_json = json.dumps(valores, ensure_ascii=False)
    elif data_velha and data_velha != data_iso and teor.strip():
        aviso = (f"A data do selo ({quando.date().strftime('%d/%m/%Y')}) não é a "
                 f"que estava no ato ({date.fromisoformat(data_velha).strftime('%d/%m/%Y')}"
                 ") e o texto não a escreve de um jeito que o sistema saiba trocar "
                 "sozinho. O texto NÃO foi mexido: confira a data escrita no teor.")

    if modelo_valores_json is not None:
        bd.escrever(
            """UPDATE nt_atos SET data=%s, hora=%s, teor=%s, modelo_valores=%s
               WHERE id=%s""",
            (data_iso, hora, teor_novo, modelo_valores_json, int(ato_id)),
        )
    elif teor_novo is not None:
        bd.escrever(
            "UPDATE nt_atos SET data=%s, hora=%s, teor=%s WHERE id=%s",
            (data_iso, hora, teor_novo, int(ato_id)),
        )
    else:
        bd.escrever(
            "UPDATE nt_atos SET data=%s, hora=%s WHERE id=%s",
            (data_iso, hora, int(ato_id)),
        )
    return {"ok": True, "alterou_teor": teor_novo is not None, "data": data_iso,
            "aviso": aviso}


def __getattr__(nome: str):
    """Os nomes antigos do texto de fábrica, lidos da base dos padrões.

    `ABERTURAS` e `FECHOS` saíram deste módulo no LF06D (19/10/2026) e moram em
    `modelos_padrao/`. Quem ainda os lê recebe o dicionário lido da base — o
    MESMO texto que o teor usa. Nome que não é de papel continua sendo
    `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    if nome in ("ABERTURAS", "FECHOS"):
        textos = MODELOS.textos()
        papeis = PAPEL_DA_ABERTURA if nome == "ABERTURAS" else PAPEL_DO_FECHO
        return {tipo: textos(papel) for tipo, papel in papeis.items()}
    return MODELOS.constante_antiga(__name__, nome)
