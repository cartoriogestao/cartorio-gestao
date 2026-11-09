"""Importação conferida das guias do TJMA; o modelo não decide o destino do dinheiro."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import despesas as DP
import livro_diario as LD
from bd_nativo import banco

FUNDOS = frozenset(("FERJ", "FERC", "FADEP", "FEMP", "FERRFIS"))
MAX_BYTES = 2 * 1024 * 1024


def _dia(texto: str) -> str:
    return datetime.strptime(texto, "%d/%m/%Y").date().isoformat()


def ler_pdf(conteudo: bytes) -> dict:
    """Lê somente a guia original de uma página, com valor e código consistentes."""
    import fitz
    if not conteudo.startswith(b"%PDF") or len(conteudo) > MAX_BYTES:
        raise DP.DespesaError("Envie a guia PDF original de até 2 MB.")
    try:
        with fitz.open(stream=conteudo, filetype="pdf") as pdf:
            if pdf.needs_pass or len(pdf) != 1:
                raise DP.DespesaError("A guia precisa ter uma página e não pode ter senha.")
            texto = pdf[0].get_text()
        return ler_texto(texto)
    except (RuntimeError, ValueError, IndexError) as erro:
        raise DP.DespesaError("Não reconheci a guia do Portal do Selo. Confira o PDF original.") from erro


def ler_texto(texto: str) -> dict:
    """Contrato textual do PDF, separado para testar sem abrir navegador ou banco."""
    try:
        if "Guia de Arrecação do Tribunal de Justiça do Maranhão" not in texto and \
                "Guia de Arrecadação do Tribunal de Justiça do Maranhão" not in texto:
            raise ValueError("cabeçalho")
        fundos = set(re.findall(r"Referente [àa]\s+(FERJ|FERC|FADEP|FEMP|FERRFIS)\b", texto))
        numeros = set(re.findall(r"\b\d{2}(?:\.\d{3}){5}-\d\b", texto))
        periodo = re.search(r"Per[ií]odo de apura[cç][aã]o:\s*(\d{2}/\d{2}/\d{4})\s+a\s+(\d{2}/\d{2}/\d{4})", texto)
        valores = set(re.findall(r"R\$\s*([\d.]+,\d{2})", texto))
        datas = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", texto)
        linhas = [l.strip() for l in texto.splitlines() if l.strip()]
        cnpjs = [i for i, l in enumerate(linhas) if re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", l)]
        if len(fundos) != 1 or len(numeros) != 1 or len(valores) != 1 or not periodo or len(cnpjs) != 1:
            raise ValueError("campos ambíguos")
        fundo = fundos.pop()
        inicio, fim = (_dia(d) for d in periodo.groups())
        if not 0 <= (date.fromisoformat(fim) - date.fromisoformat(inicio)).days <= 31:
            raise ValueError("período")
        valor = DP.centavos_da_tela(valores.pop())
        vencimento = _dia(datas[0])
        codigos = set()
        for trecho in re.findall(r"\d{11}-\d\s+\d{11}-\d\s+\d{11}-\d\s+\d{11}-\d", texto):
            lido = DP.conferir_pagamento(DP.ARRECADACAO, trecho, valor, vencimento)
            codigos.add(lido["codigo"])
        if len(codigos) != 1:
            raise ValueError("código ausente ou ambíguo")
        i = cnpjs[0]
        nomes = [l for l in linhas if l.startswith("Fundo ") and l.endswith("- " + fundo)]
        if len(nomes) != 1:
            raise ValueError("cedente")
        nome, documento = nomes[0], DP.digitos(linhas[i])
        if not DP.cpf_cnpj.documento_valido(documento):
            raise ValueError("favorecido")
        return {"fundo": fundo, "numero": numeros.pop(), "inicio": inicio, "fim": fim,
                "vencimento": vencimento, "valor_centavos": valor, "codigo": codigos.pop(),
                "beneficiario_nome": nome, "beneficiario_documento": documento}
    except (ValueError, IndexError, StopIteration) as erro:
        raise DP.DespesaError("Os campos da guia não conferem. Use o PDF original do Portal do Selo.") from erro


def esperado_dos_selos(con, guia: dict) -> int | None:
    """Calcula no servidor, nunca aceita o valor esperado fornecido pelo cliente/IA."""
    inicio, fim = guia["inicio"], guia["fim"]
    meses = sorted({inicio[:7], fim[:7]})
    receitas = [r for mes in meses for r in LD.receitas_do_mes(con, mes)
                if inicio <= r["dia"] <= fim and r["tipo"] == LD.NORMAL]
    chave = "FADP" if guia["fundo"] == "FADEP" else guia["fundo"]
    if not receitas or any(r["sem_valor"] or r["fundos"].get(chave) is None for r in receitas):
        return None
    return sum(int(r["fundos"][chave]) for r in receitas)


def conferir(con, conteudo: bytes) -> dict:
    guia = ler_pdf(conteudo)
    bd = banco(con)
    barras = DP.ler_codigo_de_barras(guia["codigo"])["barras"]
    existentes = bd.ler("SELECT id, situacao, categoria, valor, codigo_barras FROM dp_despesas "
                       "WHERE codigo_barras = %s OR documento_numero = %s ORDER BY id",
                       (barras, guia["numero"]))
    if len(existentes) > 1:
        raise DP.DespesaError("Há mais de um cadastro para esta guia. Confira as despesas existentes.")
    existente = existentes[0] if existentes else None
    if existente and (existente["codigo_barras"] != barras or
                      int(existente["valor"]) != guia["valor_centavos"] or
                      existente["categoria"] != "FUNDO_" + guia["fundo"]):
        raise DP.DespesaError("A guia difere da despesa já cadastrada. Confira antes de continuar.")
    esperado = None
    if guia["fundo"] in ("FERJ", "FERC"):
        try:
            esperado = esperado_dos_selos(con, guia)
        except LD.DiarioError:
            # Base ainda não configurada: cadastra, mas não autoriza por palpite.
            esperado = None
    return {**guia, "valor_esperado_centavos": esperado, "existente": existente,
            "somente_banco_do_brasil": "FUNDO_" + guia["fundo"] in DP.FUNDOS_SOMENTE_BANCO_DO_BRASIL}


def importar(con, conteudo: bytes, *, agora: datetime, por: str, pasta: Path,
             usuario_id: int | None) -> dict:
    bd = banco(con)
    bd.travar("despesas.portal_selo.importar")
    g = conferir(con, conteudo)
    if g["existente"]:
        # Inclui as despesas MANUAIS: a automação não duplica nem eleva sua autorização.
        return {"id": int(g["existente"]["id"]), "situacao": g["existente"]["situacao"],
                "novo": False, "fundo": g["fundo"]}
    numero = DP.cadastrar(con, agora=agora, por=por, origem=DP.ORIGEM_PORTAL_SELO,
                          chave_origem=g["fundo"] + ":" + g["numero"],
                          beneficiario_nome=g["beneficiario_nome"],
                          beneficiario_documento=g["beneficiario_documento"],
                          valor_centavos=g["valor_centavos"], vencimento=g["vencimento"],
                          forma=DP.ARRECADACAO, codigo=g["codigo"], categoria="FUNDO_" + g["fundo"],
                          descricao=f"Repasse {g['fundo']} — {g['inicio']} a {g['fim']} — guia {g['numero']}",
                          documento_especie="Guia de arrecadação TJMA", documento_numero=g["numero"],
                          valor_esperado_centavos=g["valor_esperado_centavos"],
                          anexo=(f"{g['inicio']}_{g['fundo']}_{g['numero']}.pdf", conteudo),
                          pasta_anexos=pasta, usuario_id=usuario_id)
    d = DP.despesa(con, numero)
    return {"id": numero, "situacao": d["situacao"], "novo": True, "fundo": g["fundo"]}
