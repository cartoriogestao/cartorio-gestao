"""
O ARQUIVO DE DESISTENCIA DA CRA — o quinto layout, e o passo que faltava.

O roteiro do oficial poe a desistencia nos TRES TURNOS do dia. E a unica coisa
que aparece nos tres, e o motivo esta na consequencia: titulo de que o
apresentante desistiu e a casa protestou e protesto que se cancela depois, com
carta. E o erro mais caro do dia.

POR QUE ELE E UM MODULO A PARTE, E NAO MAIS UM TIPO EM `protesto_arquivo`
    Aquele modulo e do arquivo de 600 posicoes, com tres tipos de registro e o
    sequencial no comeco. A desistencia tem **127 posicoes, cinco tipos de
    registro e o sequencial no fim**. Enfia-la la dentro faria `ler()` ter dois
    corpos, e o teste de ida e volta — que ja pegou quatro defeitos naquele
    modulo — deixaria de valer para os dois.

A MEDICAO, e ela esta inteira em `LAYOUT_DESISTENCIA_MEDIDO.md`
    Quatro arquivos, cinco titulos, dois apresentantes, **quatro anos** — de
    26/08/2022 a 05/08/2026 —, e o layout e o mesmo nos quatro. O de 2026 veio
    da pasta que o oficial indicou, e foi ele que fechou a
    medicao: o numero do titulo dele, `NF-74654-/1`, tem forma inconfundivel e
    prende a fronteira do campo, coisa que `92000001907` e `1  00053603`
    sozinhos nao faziam.

    E a mesma licao do retorno: **o que fecha uma lacuna de layout e mais
    amostra, e nao engenhosidade.**

O QUE ESTE MODULO NAO FAZ

    **Nao escreve o arquivo.** A desistencia chega, nao sai.

    **`aplicar` LAVRA, mas nao escolhe.** Ele lanca o ato DESISTENCIA em cada
    titulo que recebe na lista `protocolos`, na hora, sem outra conferencia.
    Quem escolhe e quem chama: a tela de conferencia (o que a escrevente
    marcou) ou, desde 29/10/2026, o clique diario da remessa
    (`protesto_cra_pedidos`), que manda so o que CASA pelo protocolo E pelo
    numero do titulo e esta numa situacao que aceita desistir. O que nao casa,
    nao cabe ou esta sustado fica de fora e vira pendencia — nada se lavra por
    palpite.

    **Nao recusa o arquivo por causa da contagem que nao se explica.** O
    registro `8` e o rodape trazem um numero igual ao DOBRO dos titulos nos
    quatro arquivos, e o que ele conta de fato nao se sabe. A conferencia
    compara e AVISA. Recusar por causa dele seria travar o balcao por uma
    hipotese.

OS TITULOS IRMAOS (29/10/2026)
    Ate aqui a desistencia achava o titulo pelo protocolo com `LIMIT 1`. Em 34
    protocolos da producao ha DOIS titulos com o mesmo numero — a CDA com o
    corresponsavel, uma linha por devedor (`protesto_titulos_irmaos`) —, e a
    desistencia alcancava so o primeiro: o segundo seguia para o protesto. A
    regra agora: o pedido vale para TODOS os titulos do protocolo com AQUELE
    numero. Protocolo cujos titulos tem numero diferente do pedido nao se
    aplica (a tela diz por que): e o caso das parcelas, e pelo protocolo so
    nao se sabe qual delas o credor quis.

O MESMO LAYOUT EM XML (29/10/2026)
    Pela API a CRA devolve XML, e nao o arquivo de 127 posicoes — foi assim com
    a remessa, medido na homologacao em 23/09/2026. O formato do XML de
    desistencia, cancelamento e autorizacao NAO FOI MEDIDO contra a CRA-MA;
    `ler` aceita as duas formas dos exemplos publicos da P21 (repositorio
    manual-cra-21: `EXEMPLO_DP_CP_AD_AC.zip`, registros hdb/hdc/tr/tlc/tlb com
    os campos em atributos, e `EXEMPLO_DP-CP-AC-AD_XML.zip`, comarca/cartorio/
    titulo em elementos). Os atributos `tr` sao os mesmos campos do registro
    `2` de 127 posicoes, na mesma ordem: t02 protocolo, t03 data, t04 numero
    do titulo, t05 devedor, t06 valor em centavos. O que nao for nenhuma das
    duas formas e RECUSADO dizendo a raiz que veio — e o bruto ja esta
    guardado por quem trouxe (`pt_cra_consultas`).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import sqlite3
from typing import Any

from lxml import etree as LXML

from bd_nativo import banco
import protesto as PT

TAMANHO_DO_REGISTRO = 127

# O nome do arquivo comeca por `DP` nos quatro medidos — mas quem manda e o
# conteudo, e nao o nome: AS PASTAS DO E-OFICIO MENTEM, e a da serventia
# tambem (a pasta `desistencia` dela guarda um arquivo de 600 posicoes).
PREFIXO_OBSERVADO = "DP"


class DesistenciaError(ValueError):
    """Erro de regra da desistencia, com a mensagem pronta para o balcao."""


# --------------------------------------------------------------- ler


def _texto(bruto: str) -> str:
    return bruto.strip()


def _numero(bruto: str) -> int | None:
    b = bruto.strip()
    return int(b) if b.isdigit() else None


def _data(bruto: str) -> str | None:
    """`24082022` -> `2022-08-24`. Devolve None quando nao presta.

    Data torta num titulo nao pode derrubar a leitura dos outros do arquivo —
    a falta aparece na conferencia, com o titulo do lado. E a mesma regra de
    `protesto_arquivo._data`.
    """
    b = bruto.strip()
    if len(b) != 8 or not b.isdigit():
        return None
    d, m, a = b[:2], b[2:4], b[4:]
    if not ("01" <= d <= "31" and "01" <= m <= "12" and a >= "1900"):
        return None
    return f"{a}-{m}-{d}"


def _fatia(linha: str, ini: int, fim: int) -> str:
    return linha[ini - 1:fim]


def _cabecalho(linha: str) -> dict:
    return {
        "apresentante_codigo": _texto(_fatia(linha, 2, 4)),
        "apresentante_nome": _texto(_fatia(linha, 5, 49)),
        "dia": _data(_fatia(linha, 50, 57)),
        "quantidade_de_titulos": _numero(_fatia(linha, 58, 62)),
        "reservado_63": _fatia(linha, 63, 67),
        "sequencial": _numero(_fatia(linha, 123, 127)),
    }


def _praca(linha: str) -> dict:
    return {
        "praca": _texto(_fatia(linha, 2, 3)),
        "quantidade_de_titulos": _numero(_fatia(linha, 4, 8)),
        "cidade_ibge": _texto(_fatia(linha, 9, 15)),
        "sequencial": _numero(_fatia(linha, 123, 127)),
    }


def _titulo(linha: str) -> dict:
    return {
        "protocolo": _texto(_fatia(linha, 2, 11)),
        "data": _data(_fatia(linha, 12, 19)),
        "numero_do_titulo": _texto(_fatia(linha, 20, 30)),
        "devedor_nome": _texto(_fatia(linha, 31, 75)),
        "valor_centavos": _numero(_fatia(linha, 76, 89)),
        # OS CINCO RESERVADOS SE LEEM COMO TEXTO. Campo sem nome nao se
        # interpreta — foi essa regra que evitou quatro defeitos no arquivo de
        # 600, e nenhum deles carrega nada que identifique o titulo: sao
        # constantes, zeros ou brancos nos cinco titulos medidos.
        "reservado_90": _fatia(linha, 90, 90),
        "reservado_91": _fatia(linha, 91, 102),
        "reservado_103": _fatia(linha, 103, 114),
        "reservado_115": _fatia(linha, 115, 116),
        "reservado_117": _fatia(linha, 117, 122),
        "sequencial": _numero(_fatia(linha, 123, 127)),
    }


def _total_da_praca(linha: str) -> dict:
    return {
        "praca": _texto(_fatia(linha, 2, 3)),
        "contagem": _numero(_fatia(linha, 4, 8)),
        "sequencial": _numero(_fatia(linha, 123, 127)),
    }


def _rodape(linha: str) -> dict:
    return {
        "apresentante_codigo": _texto(_fatia(linha, 2, 4)),
        "apresentante_nome": _texto(_fatia(linha, 5, 49)),
        "dia": _data(_fatia(linha, 50, 57)),
        "contagem": _numero(_fatia(linha, 58, 62)),
        "soma_centavos": _numero(_fatia(linha, 63, 76)),
        "sequencial": _numero(_fatia(linha, 123, 127)),
    }


def normalizar(conteudo: str | bytes) -> str:
    """As linhas validas, unidas por `\\n`. Mesma forma da remessa.

    O arquivo vem em latin-1: ler como UTF-8 estoura no primeiro nome com
    cedilha, e ja estourou nesta casa. O XML se decodifica pela declaracao
    dele (`_texto_do_xml`).
    """
    if isinstance(conteudo, bytes):
        conteudo = (_texto_do_xml(conteudo) if parece_xml(conteudo)
                    else conteudo.decode("latin-1"))
    return "\n".join(
        x for x in conteudo.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if x.strip())


def hash_arquivo(conteudo: str | bytes) -> str:
    """Impressao digital do arquivo, ja normalizado."""
    return hashlib.sha256(
        normalizar(conteudo).encode("latin-1", errors="replace")).hexdigest()


def ler(conteudo: str | bytes) -> dict:
    """Le o arquivo de desistencia. NAO GRAVA NADA.

    Recusa o que nao e desistencia dizendo o tamanho que achou — foi essa
    mensagem que fez este layout inteiro aparecer, quando alguem tentou abrir
    um `DP` com o leitor do arquivo de 600.
    """
    if parece_xml(conteudo):
        return _ler_xml(conteudo)
    texto = normalizar(conteudo)
    if not texto:
        raise DesistenciaError("O arquivo está vazio.")
    linhas = texto.split("\n")
    fora = [i + 1 for i, x in enumerate(linhas)
            if len(x) != TAMANHO_DO_REGISTRO]
    if fora:
        largura = len(linhas[fora[0] - 1])
        extra = ("" if largura != 600 else
                 " Esse é o tamanho da remessa, do retorno, da confirmação e "
                 "do andamento — abra-o em «Protesto — remessa da CRA» ou em "
                 "«retorno à CRA», conforme o caso.")
        raise DesistenciaError(
            f"O arquivo de desistência da CRA tem registros de "
            f"{TAMANHO_DO_REGISTRO} caracteres. A linha {fora[0]} tem "
            f"{largura}.{extra}")
    if linhas[0][:1] != "0":
        raise DesistenciaError(
            "A primeira linha do arquivo não é o cabeçalho — ela teria de "
            "começar com «0».")
    if linhas[-1][:1] != "9":
        raise DesistenciaError(
            "A última linha do arquivo não é o rodapé — ela teria de começar "
            "com «9».")

    arquivo = {
        "cabecalho": _cabecalho(linhas[0]),
        "rodape": _rodape(linhas[-1]),
        "pracas": [],
        "titulos": [],
        "totais": [],
        "achados": [],
    }
    praca_atual = None
    for i, linha in enumerate(linhas[1:-1], start=2):
        tipo = linha[:1]
        if tipo == "1":
            praca_atual = _praca(linha)
            arquivo["pracas"].append(praca_atual)
        elif tipo == "2":
            t = _titulo(linha)
            t["praca"] = (praca_atual or {}).get("praca")
            t["cidade_ibge"] = (praca_atual or {}).get("cidade_ibge")
            arquivo["titulos"].append(t)
        elif tipo == "8":
            arquivo["totais"].append(_total_da_praca(linha))
        else:
            arquivo["achados"].append(
                f"A linha {i} começa com «{tipo}» — os previstos são o "
                f"cabeçalho (0), a praça (1), o título (2), o total da praça "
                f"(8) e o rodapé (9).")
    arquivo["achados"].extend(_conferir(arquivo))
    return arquivo


def _conferir(a: dict, *, contagem_medida: bool = True) -> list[str]:
    """O que o proprio arquivo diz de si e nao bate. So calcula.

    A SOMA E A CONFERENCIA QUE VALE: ela fecha nos quatro arquivos medidos, e
    e o que pega arquivo truncado — que e como um arquivo estraga na pratica.

    `contagem_medida=False` no XML: o «dobro dos titulos» foi medido no
    arquivo de 127 posicoes, e o exemplo da P21 em XML nao o segue.
    """
    achados: list[str] = []
    titulos = a["titulos"]

    declarados = a["cabecalho"].get("quantidade_de_titulos")
    if declarados is not None and declarados != len(titulos):
        achados.append(
            f"O cabeçalho declara {declarados} título(s) e o arquivo traz "
            f"{len(titulos)}. Arquivo truncado ou emendado.")

    soma = a["rodape"].get("soma_centavos")
    somado = sum(t.get("valor_centavos") or 0 for t in titulos)
    if soma is not None and soma != somado:
        achados.append(
            f"O rodapé declara R$ {soma / 100:.2f} e os títulos somam "
            f"R$ {somado / 100:.2f}.")

    # A CONTAGEM QUE NAO SE EXPLICA. Nos quatro arquivos medidos ela e o dobro
    # do numero de titulos, e o que ela conta de fato nao se sabe. Aqui ela
    # AVISA e nao recusa: travar o balcao por uma hipotese seria pior que
    # deixar passar um arquivo esquisito, que a soma ja teria pegado.
    contagem = a["rodape"].get("contagem")
    if contagem_medida and contagem is not None \
            and contagem != len(titulos) * 2:
        achados.append(
            f"O rodapé traz {contagem} onde os quatro arquivos medidos trazem "
            f"o dobro dos títulos ({len(titulos) * 2}). O que esse número "
            f"conta nunca ficou estabelecido — confira o arquivo, mas a soma "
            f"dos valores é a conferência que vale.")

    for t in titulos:
        if not t.get("protocolo"):
            achados.append(
                f"O título {t.get('numero_do_titulo') or 'sem número'} veio "
                f"sem protocolo, e é por ele que se acha o título nesta casa.")
        if t.get("data") is None:
            achados.append(
                f"O título {t.get('numero_do_titulo') or 'sem número'} veio "
                f"com data ilegível.")
    return achados


# ------------------------------------------------------- o mesmo, em XML

# AS RAIZES DOS DOIS EXEMPLOS DA P21 (ver o cabecalho deste modulo): <sustacao>
# para DP e CP e <autorizacao> para AC e AD no de atributos; <desistencia>,
# <cancelamento>, <autoriza_cancelamento> e <autoriza_desistencia> no de
# elementos.
RAIZES_DO_XML = ("sustacao", "desistencia", "cancelamento", "autorizacao",
                 "autoriza_cancelamento", "autoriza_desistencia")

_DECLARACAO_XML = re.compile(r"^\s*<\?xml[^>]{0,500}\?>", re.IGNORECASE)
_CODIFICACAO_LATINA = re.compile(
    rb"encoding\s*=\s*['\"](?:iso-8859-1|latin-?1|windows-1252)['\"]",
    re.IGNORECASE)


def parece_xml(conteudo: str | bytes) -> bool:
    """Comeca com `<` — o arquivo de 127 posicoes comeca com o tipo `0`."""
    inicio = conteudo[:200]
    if isinstance(inicio, bytes):
        return inicio.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<")
    return inicio.lstrip("\ufeff \t\r\n").startswith("<")


def _texto_do_xml(conteudo: str | bytes) -> str:
    """O XML como texto, pela codificacao que ele declara."""
    if isinstance(conteudo, bytes):
        if _CODIFICACAO_LATINA.search(conteudo[:300]):
            texto = conteudo.decode("latin-1")
        else:
            try:
                texto = conteudo.decode("utf-8-sig")
            except UnicodeDecodeError:
                texto = conteudo.decode("latin-1")
    else:
        texto = conteudo
    return texto.lstrip("\ufeff")


def _parser_seguro() -> "LXML.XMLParser":
    """O parser do XML que vem de fora: sem expandir entidade, sem DTD, sem
    rede e sem `huge_tree`. Um por leitura — o do lxml nao se divide entre
    linhas de execucao."""
    return LXML.XMLParser(resolve_entities=False, no_network=True,
                          load_dtd=False, dtd_validation=False,
                          huge_tree=False, remove_comments=True,
                          remove_pis=True)


def _sem_espaco_de_nomes(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1].strip().lower()


def _centavos(bruto: Any) -> int | None:
    """`268.82` -> 26882. O XML de elementos traz o valor em reais."""
    b = str(bruto or "").strip().replace(",", ".")
    if not b:
        return None
    try:
        return int((Decimal(b) * 100).to_integral_value())
    except InvalidOperation:
        return None


def _ler_xml(conteudo: str | bytes) -> dict:
    """O arquivo de desistencia, cancelamento ou autorizacao em XML. NAO GRAVA.

    Devolve a MESMA forma de `ler` — cabecalho, rodape, pracas, titulos,
    totais e achados —, para a conferencia e a aplicacao nao saberem de que
    forma o arquivo veio. DTD e entidade propria se recusam antes do parser,
    como na remessa XML (`protesto_cra_xml.ler`) — E O PARSER E O DO LXML,
    que nao expande entidade, nao le DTD e nao vai a rede
    (`_PARSER_SEGURO`): o arquivo chega pela tela de qualquer escrevente, e a
    guarda de texto sozinha e uma linha que alguem tira sem saber.
    """
    texto = _texto_do_xml(conteudo)
    alto = texto.upper()
    if "<!DOCTYPE" in alto or "<!ENTITY" in alto:
        raise DesistenciaError(
            "XML com DTD ou entidade própria não é aceito.")
    if "&quot;" in texto[:120]:
        # A CRA devolve os delimitadores escapados (medido na remessa).
        texto = texto.replace("&quot;", '"')
    # A DECLARACAO SAI ANTES DO PARSER: o texto ja esta decodificado, e a
    # declaracao «ISO-8859-1» faria o parser decodificar de novo.
    texto = _DECLARACAO_XML.sub("", texto, count=1)
    try:
        raiz = LXML.fromstring(texto, _parser_seguro())
    except (LXML.XMLSyntaxError, ValueError) as erro:
        raise DesistenciaError(f"O XML não abre: {erro}.") from erro
    nome_da_raiz = _sem_espaco_de_nomes(raiz.tag)
    if nome_da_raiz in ("relatorio", "erro"):
        codigo = (raiz.findtext("codigo") or "").strip()
        mensagem = (raiz.findtext("ocorrencia") or raiz.findtext("mensagem")
                    or "").strip()
        raise DesistenciaError(
            f"A CRA informou: {mensagem or 'relatório sem títulos'}"
            + (f" (código {codigo})" if codigo else "")
            + ". Não há título nesta resposta.")
    if nome_da_raiz not in RAIZES_DO_XML:
        raise DesistenciaError(
            f"O XML tem a raiz <{nome_da_raiz[:60]}>, e as de desistência, "
            f"cancelamento e autorização são "
            f"{', '.join('<' + r + '>' for r in RAIZES_DO_XML)}. Se for uma "
            f"remessa, abra-a em «Protesto — remessa da CRA».")

    arquivo: dict = {
        "cabecalho": {"apresentante_codigo": None, "apresentante_nome": None,
                      "dia": None, "quantidade_de_titulos": None},
        "rodape": {"contagem": None, "soma_centavos": None},
        "pracas": [], "titulos": [], "totais": [], "achados": [],
        "formato": "XML", "raiz": nome_da_raiz,
        "nome_arquivo": (raiz.findtext("nome_arquivo") or "").strip()[:60]
                        or None,
    }
    praca: dict | None = None
    cidade: str | None = None
    for el in raiz.iter():
        if not isinstance(el.tag, str):
            continue            # comentario ou instrucao: nao e registro
        nome = _sem_espaco_de_nomes(el.tag)
        a = {k: str(v or "") for k, v in el.attrib.items()}
        if nome == "hdb":
            arquivo["cabecalho"] = {
                "apresentante_codigo": _texto(a.get("h02", "")) or None,
                "apresentante_nome": _texto(a.get("h03", "")) or None,
                "dia": _data(a.get("h04", "")),
                "quantidade_de_titulos": _numero(a.get("h05", "")),
                "reservado_63": a.get("h06", ""),
                "sequencial": _numero(a.get("h08", "")),
            }
        elif nome == "hdc":
            praca = {"praca": _texto(a.get("h02", "")),
                     "quantidade_de_titulos": _numero(a.get("h03", "")),
                     "cidade_ibge": _texto(a.get("h04", "")),
                     "sequencial": _numero(a.get("h06", ""))}
            arquivo["pracas"].append(praca)
        elif nome == "tr":
            arquivo["titulos"].append({
                "protocolo": _texto(a.get("t02", "")),
                "data": _data(a.get("t03", "")),
                "numero_do_titulo": _texto(a.get("t04", "")),
                "devedor_nome": _texto(a.get("t05", "")),
                "valor_centavos": _numero(a.get("t06", "")),
                # Os mesmos reservados do registro `2`, como TEXTO. Na
                # autorizacao o t07 diz o tipo (C cancelamento, S
                # desistencia — manual da P21); quem o le e quem recebe a
                # autorizacao, e nao este leitor.
                "reservado_90": a.get("t07", ""),
                "reservado_91": a.get("t08", ""),
                "reservado_103": a.get("t09", ""),
                "reservado_117": a.get("t11", ""),
                "sequencial": _numero(a.get("t12", "")),
                "tem_anexo": bool(a.get("t10", "").strip()),
                "praca": (praca or {}).get("praca"),
                "cidade_ibge": (praca or {}).get("cidade_ibge") or cidade,
            })
        elif nome == "tlc":
            arquivo["totais"].append({"praca": _texto(a.get("t02", "")),
                                      "contagem": _numero(a.get("t03", ""))})
        elif nome == "tlb":
            arquivo["rodape"] = {
                "apresentante_codigo": _texto(a.get("t02", "")) or None,
                "apresentante_nome": _texto(a.get("t03", "")) or None,
                "dia": _data(a.get("t04", "")),
                "contagem": _numero(a.get("t05", "")),
                "soma_centavos": _numero(a.get("t06", "")),
                "sequencial": _numero(a.get("t08", "")),
            }
        elif nome == "codmun":
            cidade = _texto(el.text or "") or None
        elif nome == "titulo":
            filhos = {_sem_espaco_de_nomes(f.tag): (f.text or "") for f in el
                      if isinstance(f.tag, str)}
            arquivo["titulos"].append({
                "protocolo": _texto(filhos.get("numero_protocolo", "")),
                "data": _data(filhos.get("data_protocolo", "")),
                "numero_do_titulo": _texto(filhos.get("numero_titulo", "")),
                "devedor_nome": _texto(filhos.get("nome_devedor", "")),
                "valor_centavos": _centavos(filhos.get("valor_titulo")),
                "reservado_90": "", "reservado_91": "", "reservado_103": "",
                "reservado_117": "", "sequencial": None,
                "tem_anexo": bool(filhos.get("imagem", "").strip()),
                "praca": None, "cidade_ibge": cidade,
            })
    arquivo["achados"].extend(_conferir(arquivo, contagem_medida=False))
    return arquivo


# ---------------------------------------------------------- conferir


def numero_comparavel(valor: Any) -> str:
    """O numero do titulo reduzido ao que se compara: letras e algarismos, sem
    zeros a esquerda. E a mesma regua de `protesto_titulos_irmaos._numero` —
    «1  00053603» do arquivo e «100053603» gravado dao o mesmo."""
    return re.sub(r"[^0-9A-Z]", "", str(valor or "").upper()).lstrip("0")


def titulos_do_protocolo(con, protocolo: Any) -> list[dict]:
    """Os titulos desta casa com aquele protocolo, com o PRIMEIRO devedor de
    cada um (pelo `id`, que e a ordem em que entraram). So LE."""
    p = str(protocolo or "").strip()
    if not p:
        return []
    return banco(con).ler(
        """SELECT t.id, t.numero_titulo, t.situacao, t.protocolo,
                  t.saldo_centavos, t.apresentante_codigo,
                  (SELECT d.nome FROM pt_devedores d
                    WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1)
                      AS devedor_nome
             FROM pt_titulos t WHERE t.protocolo = %s ORDER BY t.id""", (p,))


# Como o pedido casou com a casa.
CASOU_PELO_NUMERO = "NUMERO"
CASOU_SO_PELO_PROTOCOLO = "PROTOCOLO"
SEM_TITULO = "SEM"
NUMERO_DIVERGE = "DIVERGE"
PROTOCOLO_AMBIGUO = "AMBIGUO"


def casar(con, pedido: dict) -> tuple[list[dict], str, list[dict]]:
    """Os titulos desta casa de que o pedido fala. So LE.

    Devolve (os casados, como casou, todos os do protocolo). A regra e a dos
    IRMAOS: vale para TODOS os titulos do protocolo com o numero do pedido.
    Sem numero no pedido, vale para o protocolo inteiro so quando todos os
    titulos dele tem o mesmo numero; senao e ambiguo, e nao se adivinha.
    """
    todos = [dict(x) for x in titulos_do_protocolo(con, pedido.get("protocolo"))]
    if not todos:
        return [], SEM_TITULO, []
    numero = numero_comparavel(pedido.get("numero_do_titulo"))
    if not numero:
        if len({numero_comparavel(x["numero_titulo"]) for x in todos}) == 1:
            return todos, CASOU_SO_PELO_PROTOCOLO, todos
        return [], PROTOCOLO_AMBIGUO, todos
    iguais = [x for x in todos
              if numero_comparavel(x["numero_titulo"]) == numero]
    if iguais:
        return iguais, CASOU_PELO_NUMERO, todos
    return [], NUMERO_DIVERGE, todos


def _numeros(titulos: list[dict]) -> str:
    return ", ".join(dict.fromkeys(str(x.get("numero_titulo") or "sem número")
                                   for x in titulos))


def porque_nao_casou(pedido: dict, como: str, todos: list[dict]) -> str:
    """A frase do balcao para o pedido que nao achou titulo nesta casa."""
    p = pedido.get("protocolo") or "—"
    if como == NUMERO_DIVERGE:
        return (f"O protocolo {p} desta casa é do(s) título(s) {_numeros(todos)}, "
                f"e a CRA fala do título {pedido.get('numero_do_titulo')}. "
                f"Confira antes de qualquer ato — e, se o pedido for mesmo "
                f"deste título, lance pela ficha.")
    if como == PROTOCOLO_AMBIGUO:
        return (f"O protocolo {p} tem títulos de números diferentes "
                f"({_numeros(todos)}), e o pedido veio sem número: confira "
                f"qual é pela ficha.")
    return (f"Nenhum título desta casa tem o protocolo {p}. Pode ser de "
            f"outra serventia, ou o título pode não ter entrado.")


# Situacoes em que ainda cabe desistir. E a mesma lista de
# `protesto.lancar_desistencia` — repetida aqui NAO para decidir, mas para a
# tela poder dizer por que um titulo nao entra. Quem recusa continua sendo o
# dominio.
SITUACOES_QUE_ACEITAM = ("RECEBIDO", "APONTADO", "INTIMADO")


def conferir(con: sqlite3.Connection, conteudo: str | bytes) -> dict:
    """Le o arquivo e procura cada titulo nesta casa. NAO GRAVA NADA.

    O PROTOCOLO E A CHAVE. Ele e o numero que esta casa deu ao titulo quando o
    apontou, e o mesmo que volta para a CRA na posicao 448 do retorno — logo e
    o que a Central usa para falar do titulo.

    Devolve uma linha por titulo do arquivo, dizendo o que a casa tem: o
    titulo achado e a situacao dele, ou que nao ha titulo com aquele
    protocolo.
    """
    bd = banco(con)
    arquivo = ler(conteudo)
    assinatura = hash_arquivo(conteudo)
    ja = pelo_hash(bd, assinatura)

    linhas = []
    cabem = nao_cabem = nao_achados = 0
    for t in arquivo["titulos"]:
        # OS IRMAOS (29/10/2026): todos os titulos do protocolo com AQUELE
        # numero, e nao o primeiro do protocolo (`LIMIT 1` alcancava so um
        # dos dois devedores da CDA).
        casados, como, todos = casar(bd, t)
        for x in casados:
            x["cabe"] = x["situacao"] in SITUACOES_QUE_ACEITAM
            x["porque"] = "" if x["cabe"] else _porque_nao_cabe(x["situacao"])
        linha = {**t, "titulo": casados[0] if casados else None,
                 "titulos": casados, "casou_por": como,
                 "titulos_do_protocolo": todos}
        if not casados:
            linha["situacao"] = ("SEM TÍTULO" if como == SEM_TITULO else
                                 "NÚMERO DIVERGE" if como == NUMERO_DIVERGE
                                 else "PROTOCOLO AMBÍGUO")
            linha["cabe"] = False
            linha["porque"] = porque_nao_casou(t, como, todos)
            if como == SEM_TITULO:
                nao_achados += 1
            else:
                nao_cabem += 1
        else:
            situacoes = list(dict.fromkeys(x["situacao"] for x in casados))
            linha["situacao"] = " / ".join(situacoes)
            linha["cabe"] = any(x["cabe"] for x in casados)
            fora = [x for x in casados if not x["cabe"]]
            linha["porque"] = ("" if not fora else
                               fora[0]["porque"] if len(casados) == 1 else
                               "; ".join(f"título {x['numero_titulo']} "
                                         f"(id {x['id']}): {x['porque']}"
                                         for x in fora))
            if linha["cabe"]:
                cabem += 1
            else:
                nao_cabem += 1
        linhas.append(linha)

    return {
        **arquivo["cabecalho"],
        "hash_arquivo": assinatura,
        "conteudo": normalizar(conteudo),
        "pracas": arquivo["pracas"],
        "achados": arquivo["achados"],
        "titulos": linhas,
        "quantidade": len(linhas),
        "cabem": cabem,
        "nao_cabem": nao_cabem,
        "nao_achados": nao_achados,
        "soma_centavos": arquivo["rodape"].get("soma_centavos") or 0,
        "ja_entrou": dict(ja) if ja else None,
        # O XML diz o próprio nome e a raiz; o arquivo de 127 não diz nada.
        "nome_arquivo": arquivo.get("nome_arquivo"),
        "raiz": arquivo.get("raiz"),
    }


def _porque_nao_cabe(situacao: str) -> str:
    return (f"O título está {situacao} — só se desiste antes do protesto "
            f"lavrado. Tirar protesto já lavrado é cancelamento, e é outro "
            f"ato.")


def pelo_hash(con: sqlite3.Connection, assinatura: str) -> dict | None:
    """O arquivo de desistencia que ja entrou com esse mesmo conteudo. So LE."""
    return banco(con).um("SELECT * FROM pt_desistencias WHERE hash_arquivo=%s",
                         (assinatura,))


# ----------------------------------------------------------- aplicar


def aplicar(con: sqlite3.Connection, conteudo: str | bytes, *,
            protocolos: list[str], agora: str, nome_arquivo: str | None = None,
            usuario: str | None = None) -> dict:
    """Lanca a desistencia dos titulos ESCOLHIDOS. ESCREVE.

    O ARQUIVO NAO SE REJEITA QUANDO JA ENTROU, e aqui isso e diferente da
    remessa. Receber a mesma remessa duas vezes apontaria tudo de novo; aplicar
    a mesma desistencia duas vezes nao faz nada, porque o dominio recusa
    desistir de titulo ja desistido. E o caso comum e justamente o segundo
    turno: o oficial aplicou metade de manha e volta ao meio-dia para o resto.

    Por isso o arquivo se GRAVA UMA VEZ (achado pelo hash) e a aplicacao e
    parcial por construcao.

    CADA PROTOCOLO VALE PARA OS IRMAOS (29/10/2026): o ato se lanca em todos
    os titulos do protocolo com o numero do pedido (`casar`), uma vez por
    titulo — duas linhas do arquivo para o mesmo protocolo nao desistem duas
    vezes. O titulo SUSTADO por ordem judicial volta em `recusados` com a
    ordem na frase, em vez de derrubar o arquivo inteiro (art. 17, § 1º).
    """
    bd = banco(con)
    visto = conferir(bd, conteudo)
    escolhidos = {str(p).strip() for p in protocolos if str(p).strip()}
    if not escolhidos:
        raise DesistenciaError(
            "Nenhum título foi marcado. Marque os que o apresentante desistiu "
            "e mande aplicar.")

    desistencia_id = guardar_arquivo(bd, visto, nome_arquivo=nome_arquivo,
                                     agora=agora, usuario=usuario)

    aplicados: list[dict] = []
    recusados: list[dict] = []
    feitos: set[int] = set()
    for t in visto["titulos"]:
        if t["protocolo"] not in escolhidos:
            continue
        if not t["cabe"]:
            recusados.append({"protocolo": t["protocolo"],
                              "titulo_id": (t["titulo"] or {}).get("id"),
                              "porque": t["porque"]})
            continue
        for x in t["titulos"]:
            tid = int(x["id"])
            if tid in feitos:
                continue
            feitos.add(tid)
            if not x["cabe"]:
                recusados.append({"protocolo": t["protocolo"],
                                  "titulo_id": tid, "porque": x["porque"]})
                continue
            ordem = PT.sustacao_em_vigor(con, tid)
            if ordem:
                recusados.append({
                    "protocolo": t["protocolo"], "titulo_id": tid,
                    "porque": (
                        "O título está SUSTADO por ordem judicial"
                        + (f" ({ordem.get('juizo')})" if ordem.get("juizo")
                           else "")
                        + " — a desistência só se faz com autorização "
                          "judicial (Lei 9.492/1997, art. 17, § 1º).")})
                continue
            motivo = (
                f"Desistência do apresentante "
                f"{visto['apresentante_codigo'] or 'não lido'} — arquivo de "
                f"{visto['dia'] or 'data não lida'}"
                + (f", título {t['numero_do_titulo']}"
                   if t["numero_do_titulo"] else ""))
            r = PT.lancar_desistencia(
                con, tid, motivo=motivo, agora=agora,
                usuario=usuario, origem="CRA")
            bd.escrever("UPDATE pt_atos SET desistencia_id=%s WHERE id=%s",
                        (desistencia_id, r["ato_id"]))
            aplicados.append({**t, "titulo": x, "ato_id": r["ato_id"]})

    bd.escrever(
        """UPDATE pt_desistencias SET aplicados=(
               SELECT COUNT(*) FROM pt_atos WHERE desistencia_id=%s)
            WHERE id=%s""", (desistencia_id, desistencia_id))
    return {**visto, "desistencia_id": desistencia_id,
            "aplicados": aplicados, "recusados": recusados}


def guardar_arquivo(con, visto: dict, *, nome_arquivo: str | None,
                    agora: str, usuario: str | None) -> int:
    """Grava o arquivo conferido UMA vez (pelo hash). ESCREVE.

    Separada de `aplicar` em 29/10/2026: o clique do dia guarda o arquivo
    mesmo quando nenhum titulo cabe — o caso grave, desistencia de titulo ja
    protestado, e justamente o que nao se aplica.
    """
    bd = banco(con)
    linha = pelo_hash(bd, visto["hash_arquivo"])
    if linha is not None:
        return int(linha["id"])
    return int(bd.escrever(
        """INSERT INTO pt_desistencias(apresentante_codigo,
               apresentante_nome, dia, nome_arquivo, conteudo,
               hash_arquivo, titulos, soma_centavos, achados_json,
               recebida_em, recebida_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (visto["apresentante_codigo"], visto["apresentante_nome"],
         visto["dia"], nome_arquivo, visto["conteudo"],
         visto["hash_arquivo"], visto["quantidade"],
         visto["soma_centavos"],
         json.dumps(visto["achados"], ensure_ascii=False), agora,
         usuario))[0]["id"])


def pendencias_da_cra(con) -> list[dict]:
    """O que veio da CRA (DP, CP, AC) e ainda nao foi tratado. So LE.

    O CONTRATO COM O ROTEIRO DO PROTESTO (`protesto_roteiro.GANCHOS`): ele
    chama esta funcao pelo nome, passando so a conexao, e le de cada linha
    `titulo_id`, `numero_titulo`, `protocolo` e `explicacao`. As linhas trazem
    mais chaves (`tipo`, `destaque`, `pedido_id`, `consulta_id`), que a tela
    dos pedidos usa e o roteiro ignora. A desistencia de titulo ja PROTESTADO
    vem primeiro. Quem mede e `protesto_cra_pedidos.pendencias`.
    """
    import protesto_cra_pedidos as PCP
    return PCP.pendencias(con)


# --------------------------------------------------------- consultas


def desistencia(con: sqlite3.Connection, desistencia_id: int) -> dict | None:
    """O arquivo de desistencia guardado inteiro. So LE."""
    return banco(con).um("SELECT * FROM pt_desistencias WHERE id=%s",
                         (int(desistencia_id),))


def listar(con: sqlite3.Connection, limite: int = 60) -> list[dict]:
    """Os arquivos de desistencia recebidos, do mais novo para o mais velho."""
    return banco(con).ler(
        """SELECT id, apresentante_codigo, apresentante_nome, dia,
                  nome_arquivo, titulos, aplicados, soma_centavos,
                  hash_arquivo, recebida_em, recebida_por
             FROM pt_desistencias ORDER BY id DESC LIMIT %s""", (int(limite),))


def atos_da_desistencia(con: sqlite3.Connection,
                        desistencia_id: int) -> list[dict]:
    """Que titulos foram desistidos por aquele arquivo. So LE."""
    return banco(con).ler(
        """SELECT a.id ato_id, a.data_ato, a.detalhe_json, t.id titulo_id,
                  t.numero_titulo, t.protocolo, t.saldo_centavos, t.situacao
             FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.desistencia_id = %s ORDER BY a.id""",
        (int(desistencia_id),))


def _inteiro(valor: Any, padrao: int = 0) -> int:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return padrao
