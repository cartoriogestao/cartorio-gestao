"""Confere, sem escrita, uma resposta XML da CRA guardada na área privada.

Mostra apenas métricas agregadas. Não imprime dados pessoais nem títulos.
As larguras vêm do Layout de Transmissão de Arquivo de Protesto da FEBRABAN,
campos h01..h17, t01..t52 e t01..t08 do trailer.
"""
from __future__ import annotations

import collections
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import banco_pg  # noqa: E402
import protesto_arquivo as PA  # noqa: E402
import protesto_remessa as PR  # noqa: E402


LARGURAS = {
    "hd": (1, 3, 40, 8, 3, 3, 3, 6, 4, 4, 4, 4, 6, 3, 7, 497, 4),
    "tr": (1, 3, 15, 45, 45, 14, 45, 8, 20, 2, 15, 3, 11, 8, 8, 3,
           14, 14, 20, 1, 1, 1, 45, 3, 14, 11, 45, 8, 20, 2, 2, 10,
           1, 8, 10, 1, 8, 2, 20, 10, 6, 10, 5, 15, 3, 1, 8, 1, 1,
           10, 19, 4),
    "tl": (1, 3, 40, 8, 5, 18, 521, 4),
}
for larguras in LARGURAS.values():
    assert sum(larguras) == 600


def linha_fixa(elemento: ET.Element) -> str:
    prefixo = {"hd": "h", "tr": "t", "tl": "t"}[elemento.tag]
    partes = []
    for i, tamanho in enumerate(LARGURAS[elemento.tag], 1):
        valor = elemento.get(f"{prefixo}{i:02}", "")
        if len(valor) > tamanho:
            raise ValueError(f"{elemento.tag} campo {i:02}: maior que {tamanho}")
        partes.append(valor.ljust(tamanho))
    return "".join(partes)


def analisar(caminho: Path, banco: Path) -> dict:
    texto = caminho.read_text(encoding="utf-8")
    # A resposta observada traz &quot; nas aspas da declaração e dos atributos
    # de TODO o documento. São delimitadores, não valores: sem normalizá-los,
    # o XML devolvido pela CRA não é analisável por um parser XML comum.
    linhas = texto.splitlines()
    if not linhas or not linhas[0].startswith("<?xml "):
        raise ValueError("Declaração XML ausente")
    raiz = ET.fromstring(texto.replace("&quot;", '"'))
    if raiz.tag != "remessa":
        raise ValueError("Raiz diferente de remessa")

    lotes: list[list[ET.Element]] = []
    atual: list[ET.Element] = []
    for filho in raiz:
        if filho.tag == "nome_arquivo":
            continue
        if filho.tag == "hd":
            if atual:
                raise ValueError("Cabeçalho antes do trailer")
            atual = [filho]
        elif filho.tag == "tr":
            if not atual:
                raise ValueError("Título sem cabeçalho")
            atual.append(filho)
        elif filho.tag == "tl":
            if not atual:
                raise ValueError("Trailer sem cabeçalho")
            atual.append(filho)
            lotes.append(atual)
            atual = []
        else:
            raise ValueError(f"Elemento inesperado: {filho.tag}")
    if atual:
        raise ValueError("Último lote sem trailer")

    resumo = {
        "declaracao_com_aspas_escapadas": "&quot;" in texto.splitlines()[0],
        "caracteres_substituidos_na_resposta": texto.count("\ufffd"),
        "nome_arquivo": raiz.findtext("nome_arquivo"),
        "lotes": len(lotes),
        "titulos": sum(len(lote) - 2 for lote in lotes),
        "lotes_detalhes": [],
        "especies": dict(collections.Counter(
            tr.get("t12", "") for lote in lotes for tr in lote[1:-1])),
        "tipos_documento_devedor": dict(collections.Counter(
            tr.get("t24", "") for lote in lotes for tr in lote[1:-1])),
        "datas_invalidas": 0,
        "identificadores_repetidos_no_mesmo_apresentante": 0,
    }
    identificadores = []
    conteudo_fixo = []
    for lote in lotes:
        hd, *meio, tl = lote
        quantidade = len(meio)
        anunciado = int(hd.get("h10", "0"))
        soma_real = sum(int(tr.get("t18", "0")) for tr in meio)
        soma_anunciada = int(tl.get("t06", "0"))
        seguranca = sum(int(hd.get(f"h{i:02}", "0")) for i in range(9, 13))
        resultado = {
            "apresentante": hd.get("h02"),
            "layout": hd.get("h14"),
            "municipio": hd.get("h15"),
            "titulos": quantidade,
            "quantidade_confere": quantidade == anunciado,
            "seguranca_confere": seguranca == int(tl.get("t05", "0")),
            "saldo_confere": soma_real == soma_anunciada,
            "saldo_centavos": soma_real,
            "sequenciais_conferem": [int(e.get("h17" if e.tag == "hd" else "t08" if e.tag == "tl" else "t52", "0")) for e in lote] == list(range(int(hd.get("h17", "0")), int(hd.get("h17", "0")) + len(lote))),
        }
        for tr in meio:
            identificadores.append((hd.get("h02"), tr.get("t11"), tr.get("t13")))
            for campo in ("t14", "t15"):
                valor = tr.get(campo, "")
                if valor not in ("00000000", "99999999"):
                    try:
                        datetime.strptime(valor, "%d%m%Y")
                    except ValueError:
                        resumo["datas_invalidas"] += 1
        resumo["lotes_detalhes"].append(resultado)
        conteudo_fixo.append("\n".join(linha_fixa(e) for e in lote))
    resumo["identificadores_repetidos_no_mesmo_apresentante"] = len(identificadores) - len(set(identificadores))

    # Ensaio de compatibilidade: a conversão é apenas em memória. Não grava
    # título, selo ou confirmação, nem substitui o adaptador de produção.
    amostra = "\n".join(conteudo_fixo)
    # PELA PORTA DO BANCO: `protesto_remessa` já é nativo e recusa o `sqlite3`
    # cru, e fora do sistema ninguém instala o desvio do `sqlite3.connect` — a
    # conferência caía sempre no `except` abaixo, com BancoNaoEPostgres.
    try:
        with banco_pg.conectar(f"file:{banco}?mode=ro", uri=True, timeout=2) as con:
            conferencia = PR.conferir(con, amostra)
    except Exception as erro:
        resumo["conferencia_existente"] = {"ok": False, "erro": f"{type(erro).__name__}: {erro}"[:300]}
    else:
        resumo["conferencia_existente"] = {
            "ok": True,
            "lotes": conferencia["quantidade_de_lotes"],
            "titulos": conferencia["quantidade"],
            "aceitos": conferencia["aceitos"],
            "recusados": conferencia["recusados"],
            "avisados": conferencia["avisados"],
            "achados": len(conferencia["achados"]),
            "avisos_sao_so_contagem_do_trailer": all(
                aviso.startswith("O rodapé declara") and "registro(s)" in aviso
                for aviso in conferencia["achados"]),
        }
    return resumo


if __name__ == "__main__":
    arquivo = Path(sys.argv[1])
    banco = Path(sys.argv[2])
    print(json.dumps(analisar(arquivo, banco), ensure_ascii=False, indent=2))
