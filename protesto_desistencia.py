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
    da pasta do Proton Drive que o oficial indicou, e foi ele que fechou a
    medicao: o numero do titulo dele, `NF-74654-/1`, tem forma inconfundivel e
    prende a fronteira do campo, coisa que `92000001907` e `1  00053603`
    sozinhos nao faziam.

    E a mesma licao do retorno: **o que fecha uma lacuna de layout e mais
    amostra, e nao engenhosidade.**

O QUE ESTE MODULO NAO FAZ

    **Nao escreve o arquivo.** A desistencia chega, nao sai.

    **Nao aplica sozinho.** Cada titulo e uma escolha do oficial, e a tela
    mostra o que vai acontecer com cada um antes de qualquer escrita. Com cinco
    titulos de amostra, ler errado continua sendo possivel — e o preco de ler
    errado e protesto lavrado contra quem o credor desistiu de protestar.

    **Nao recusa o arquivo por causa da contagem que nao se explica.** O
    registro `8` e o rodape trazem um numero igual ao DOBRO dos titulos nos
    quatro arquivos, e o que ele conta de fato nao se sabe. A conferencia
    compara e AVISA. Recusar por causa dele seria travar o balcao por uma
    hipotese.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

import protesto as PT

TAMANHO_DO_REGISTRO = 127

# O nome do arquivo comeca por `DP` nos quatro medidos — mas quem manda e o
# conteudo, e nao o nome: AS PASTAS DO E-OFICIO MENTEM, e a do Proton Drive
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
    cedilha, e ja estourou nesta casa.
    """
    if isinstance(conteudo, bytes):
        conteudo = conteudo.decode("latin-1")
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


def _conferir(a: dict) -> list[str]:
    """O que o proprio arquivo diz de si e nao bate. So calcula.

    A SOMA E A CONFERENCIA QUE VALE: ela fecha nos quatro arquivos medidos, e
    e o que pega arquivo truncado — que e como um arquivo estraga na pratica.
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
    if contagem is not None and contagem != len(titulos) * 2:
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


# ---------------------------------------------------------- conferir


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
    arquivo = ler(conteudo)
    assinatura = hash_arquivo(conteudo)
    ja = pelo_hash(con, assinatura)

    linhas = []
    cabem = nao_cabem = nao_achados = 0
    for t in arquivo["titulos"]:
        achado = con.execute(
            """SELECT t.id, t.numero_titulo, t.situacao, t.protocolo,
                      t.saldo_centavos, t.apresentante_codigo,
                      d.nome devedor_nome
                 FROM pt_titulos t
                 LEFT JOIN pt_devedores d ON d.titulo_id = t.id
                WHERE t.protocolo = ? ORDER BY t.id LIMIT 1""",
            (t["protocolo"],)).fetchone()
        linha = {**t, "titulo": dict(achado) if achado else None}
        if achado is None:
            linha["situacao"] = "SEM TÍTULO"
            linha["cabe"] = False
            linha["porque"] = (
                f"Nenhum título desta casa tem o protocolo "
                f"{t['protocolo']}. Pode ser de outra serventia, ou o título "
                f"pode não ter entrado.")
            nao_achados += 1
        elif achado["situacao"] not in SITUACOES_QUE_ACEITAM:
            linha["situacao"] = achado["situacao"]
            linha["cabe"] = False
            linha["porque"] = (
                f"O título está {achado['situacao']} — só se desiste antes do "
                f"protesto lavrado. Tirar protesto já lavrado é cancelamento, "
                f"e é outro ato.")
            nao_cabem += 1
        else:
            linha["situacao"] = achado["situacao"]
            linha["cabe"] = True
            linha["porque"] = ""
            cabem += 1
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
    }


def pelo_hash(con: sqlite3.Connection, assinatura: str) -> sqlite3.Row | None:
    """O arquivo de desistencia que ja entrou com esse mesmo conteudo. So LE."""
    return con.execute("SELECT * FROM pt_desistencias WHERE hash_arquivo=?",
                       (assinatura,)).fetchone()


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
    """
    visto = conferir(con, conteudo)
    escolhidos = {str(p).strip() for p in protocolos if str(p).strip()}
    if not escolhidos:
        raise DesistenciaError(
            "Nenhum título foi marcado. Marque os que o apresentante desistiu "
            "e mande aplicar.")

    linha = pelo_hash(con, visto["hash_arquivo"])
    if linha is None:
        cur = con.execute(
            """INSERT INTO pt_desistencias(apresentante_codigo,
                   apresentante_nome, dia, nome_arquivo, conteudo,
                   hash_arquivo, titulos, soma_centavos, achados_json,
                   recebida_em, recebida_por)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (visto["apresentante_codigo"], visto["apresentante_nome"],
             visto["dia"], nome_arquivo, visto["conteudo"],
             visto["hash_arquivo"], visto["quantidade"],
             visto["soma_centavos"],
             json.dumps(visto["achados"], ensure_ascii=False), agora, usuario))
        desistencia_id = int(cur.lastrowid)
    else:
        desistencia_id = int(linha["id"])

    aplicados: list[dict] = []
    recusados: list[dict] = []
    for t in visto["titulos"]:
        if t["protocolo"] not in escolhidos:
            continue
        if not t["cabe"]:
            recusados.append({"protocolo": t["protocolo"],
                              "porque": t["porque"]})
            continue
        motivo = (
            f"Desistência do apresentante "
            f"{visto['apresentante_codigo']} — arquivo de "
            f"{visto['dia'] or 'data não lida'}"
            + (f", título {t['numero_do_titulo']}"
               if t["numero_do_titulo"] else ""))
        r = PT.lancar_desistencia(
            con, int(t["titulo"]["id"]), motivo=motivo, agora=agora,
            usuario=usuario, origem="CRA")
        con.execute("UPDATE pt_atos SET desistencia_id=? WHERE id=?",
                    (desistencia_id, r["ato_id"]))
        aplicados.append({**t, "ato_id": r["ato_id"]})

    con.execute(
        """UPDATE pt_desistencias SET aplicados=(
               SELECT COUNT(*) FROM pt_atos WHERE desistencia_id=?)
            WHERE id=?""", (desistencia_id, desistencia_id))
    return {**visto, "desistencia_id": desistencia_id,
            "aplicados": aplicados, "recusados": recusados}


# --------------------------------------------------------- consultas


def desistencia(con: sqlite3.Connection, desistencia_id: int) -> sqlite3.Row | None:
    """O arquivo de desistencia guardado inteiro. So LE."""
    return con.execute("SELECT * FROM pt_desistencias WHERE id=?",
                       (int(desistencia_id),)).fetchone()


def listar(con: sqlite3.Connection, limite: int = 60) -> list[dict]:
    """Os arquivos de desistencia recebidos, do mais novo para o mais velho."""
    return [dict(r) for r in con.execute(
        """SELECT id, apresentante_codigo, apresentante_nome, dia,
                  nome_arquivo, titulos, aplicados, soma_centavos,
                  hash_arquivo, recebida_em, recebida_por
             FROM pt_desistencias ORDER BY id DESC LIMIT ?""", (int(limite),))]


def atos_da_desistencia(con: sqlite3.Connection,
                        desistencia_id: int) -> list[dict]:
    """Que titulos foram desistidos por aquele arquivo. So LE."""
    return [dict(r) for r in con.execute(
        """SELECT a.id ato_id, a.data_ato, a.detalhe_json, t.id titulo_id,
                  t.numero_titulo, t.protocolo, t.saldo_centavos, t.situacao
             FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.desistencia_id = ? ORDER BY a.id""",
        (int(desistencia_id),))]


def _inteiro(valor: Any, padrao: int = 0) -> int:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return padrao
