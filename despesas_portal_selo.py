"""Importação conferida das guias do TJMA; o modelo não decide o destino do dinheiro."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import Path

import despesas as DP
import livro_diario as LD
from bd_nativo import banco

FUNDOS = frozenset(("FERJ", "FERC", "FADEP", "FEMP", "FERRFIS"))
# FERJ e FERC se pagam pelo Pix do QR code da guia (oficial, 10/11/2026): o código
# de barras «demora muito e se der erro não dá tempo de pagar no dia».
FUNDOS_PAGOS_POR_PIX = frozenset(("FERJ", "FERC"))
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


def ler_pix(conteudo: bytes, *, hoje: date) -> str | None:
    """O Pix copia e cola do QR code da guia; None se ela não traz Pix. Só lê.

    Usa o mesmo leitor das despesas (texto do PDF e imagem do QR). Dois Pix
    diferentes na mesma guia é recusa: não se escolhe destino de dinheiro.
    """
    import despesas_documento
    opcoes = despesas_documento.ler(conteudo, hoje=hoje)["opcoes"]
    pix = {o["codigo"] for o in opcoes if o["forma"] == DP.PIX_COPIA_E_COLA}
    if len(pix) > 1:
        raise DP.DespesaError("A guia traz mais de um Pix. Use o PDF original do Portal do Selo.")
    return pix.pop() if pix else None


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


def conferir(con, conteudo: bytes, *, hoje: date | None = None) -> dict:
    guia = ler_pdf(conteudo)
    pix = None
    if guia["fundo"] in FUNDOS_PAGOS_POR_PIX:
        pix = ler_pix(conteudo, hoje=hoje or date.today())
        if pix is not None:
            lido = DP.ler_pix_copia_e_cola(pix)
            if lido["valor_centavos"] is not None and lido["valor_centavos"] != guia["valor_centavos"]:
                raise DP.DespesaError(
                    f"O Pix da guia diz R$ {DP.reais(lido['valor_centavos'])} e a guia diz "
                    f"R$ {DP.reais(guia['valor_centavos'])}. Use o PDF original do Portal do Selo.")
    bd = banco(con)
    barras = DP.ler_codigo_de_barras(guia["codigo"])["barras"]
    existentes = bd.ler("SELECT id, situacao, categoria, valor, forma, codigo, codigo_barras, vencimento, "
                        "beneficiario_documento FROM dp_despesas "
                        "WHERE codigo_barras = %s OR documento_numero = %s ORDER BY id",
                        (barras, guia["numero"]))
    if len(existentes) > 1:
        raise DP.DespesaError("Há mais de um cadastro para esta guia. Confira as despesas existentes.")
    existente = existentes[0] if existentes else None
    # O cadastro existente paga pelo código de barras desta guia ou pelo Pix dela.
    mesmo_pagamento = existente and (
        existente["codigo_barras"] == barras if existente["forma"] != DP.PIX_COPIA_E_COLA
        else bool(pix) and existente["codigo"] == pix)
    if existente and (not mesmo_pagamento or
                      int(existente["valor"]) != guia["valor_centavos"] or
                      existente["categoria"] != "FUNDO_" + guia["fundo"] or
                      existente["vencimento"] != guia["vencimento"] or
                      DP.digitos(existente["beneficiario_documento"]) != guia["beneficiario_documento"]):
        raise DP.DespesaError("A guia difere da despesa já cadastrada. Confira antes de continuar.")
    esperado = None
    if guia["fundo"] in ("FERJ", "FERC"):
        try:
            esperado = esperado_dos_selos(con, guia)
        except LD.DiarioError:
            # Base ainda não configurada: cadastra, mas não autoriza por palpite.
            esperado = None
    motivo_pix = (DP.pix_do_fundo_confere(DP.configuracao(con), "FUNDO_" + guia["fundo"], pix)
                  if pix else "")
    return {**guia, "valor_esperado_centavos": esperado, "existente": existente,
            "pix": pix, "pix_conferido": bool(pix) and not motivo_pix, "motivo_pix": motivo_pix,
            "somente_banco_do_brasil": "FUNDO_" + guia["fundo"] in DP.FUNDOS_SOMENTE_BANCO_DO_BRASIL}


def importar(con, conteudo: bytes, *, agora: datetime, por: str, pasta: Path,
             usuario_id: int | None) -> dict:
    bd = banco(con)
    bd.travar("despesas.portal_selo.importar")
    g = conferir(con, conteudo, hoje=agora.date())
    if g["existente"]:
        # Inclui as despesas MANUAIS sem elevar sua autorização. O PDF faltante
        # entra no mesmo cadastro; reenvio dos mesmos bytes não repete o anexo.
        digest = hashlib.sha256(conteudo).hexdigest()
        if not any(a["sha256"] == digest for a in DP.anexos(con, int(g["existente"]["id"]))):
            DP.guardar_anexo(con, int(g["existente"]["id"]), nome_arquivo=g["fundo"] + ".pdf",
                             conteudo=conteudo, pasta=pasta, usuario_id=usuario_id,
                             agora=agora.isoformat(timespec="seconds"))
        return {"id": int(g["existente"]["id"]), "situacao": g["existente"]["situacao"],
                "novo": False, "fundo": g["fundo"]}
    numero = DP.cadastrar(con, agora=agora, por=por, origem=DP.ORIGEM_PORTAL_SELO,
                          chave_origem=g["fundo"] + ":" + g["numero"],
                          beneficiario_nome=g["beneficiario_nome"],
                          beneficiario_documento=g["beneficiario_documento"],
                          valor_centavos=g["valor_centavos"], vencimento=g["vencimento"],
                          forma=DP.PIX_COPIA_E_COLA if g["pix"] else DP.ARRECADACAO,
                          codigo=g["pix"] or g["codigo"], categoria="FUNDO_" + g["fundo"],
                          descricao=f"Repasse {g['fundo']} — {g['inicio']} a {g['fim']} — guia {g['numero']}",
                          documento_especie="Guia de arrecadação TJMA", documento_numero=g["numero"],
                          valor_esperado_centavos=g["valor_esperado_centavos"],
                          anexo=(f"{g['inicio']}_{g['fundo']}_{g['numero']}.pdf", conteudo),
                          pasta_anexos=pasta, usuario_id=usuario_id)
    d = DP.despesa(con, numero)
    return {"id": numero, "situacao": d["situacao"], "novo": True, "fundo": g["fundo"]}


def destinatario_automatico(con, d: dict, *, hoje: str) -> dict | None:
    """Exceção FERJ/FERC aprovada pelo titular: prova refeita antes de enviar.

    Só aceita a autorização pela regra desta importação, paga pelo Pix do QR
    code da guia, com o recebedor conferido do fundo (chave ou domínio) que
    vale AGORA. Cadastro manual, autorização antiga, código de barras, PDF
    ausente/alterado, Pix de outro recebedor ou valores sem base não entram.
    A conferência humana de todas as outras despesas continua no seu domínio.
    """
    fundo = str(d.get("categoria") or "").removeprefix("FUNDO_")
    if (fundo not in FUNDOS_PAGOS_POR_PIX or d.get("origem") != DP.ORIGEM_PORTAL_SELO
            or d.get("forma") != DP.PIX_COPIA_E_COLA or not d.get("autorizada_pela_regra")
            or d.get("autorizada_por") != "regra das guias"
            or d.get("situacao") not in (DP.AUTORIZADA, DP.ENVIADA)):
        return None
    cfg = DP.configuracao(con)
    valor = int(d["valor"])
    if (cfg.get("despesas_regra_guias_ligada") != "1"
            or not DP.valor_confere_com_o_calculado(valor, d.get("valor_esperado"), cfg)
            or valor > min(DP.tetos(cfg)["guia"], DP.tetos(cfg)["pagamento"])):
        return None
    for anexo in DP.anexos(con, int(d["id"])):
        arquivo = Path(anexo["stored_path"])
        if arquivo.suffix.lower() != ".pdf":
            continue
        try:
            with arquivo.open("rb") as origem:
                conteudo = origem.read(MAX_BYTES + 1)
            if len(conteudo) > MAX_BYTES or hashlib.sha256(conteudo).hexdigest() != anexo["sha256"]:
                continue
            g = conferir(con, conteudo, hoje=date.fromisoformat(hoje))
        except (OSError, DP.DespesaError, ValueError):
            continue
        if (g["fundo"] == fundo and g["existente"] and int(g["existente"]["id"]) == int(d["id"])
                and g["numero"] == d.get("documento_numero")
                and g["pix"] == d.get("codigo") and g["pix_conferido"]
                and d.get("chave_origem") == fundo + ":" + g["numero"]
                and DP.valor_confere_com_o_calculado(valor, g["valor_esperado_centavos"], cfg)
                and g["vencimento"] >= hoje
                and DP.nome_do_recebedor(g["beneficiario_nome"]) == DP.nome_do_recebedor(d.get("beneficiario_nome"))):
            return {"nome": g["beneficiario_nome"], "documento": g["beneficiario_documento"]}
    return None
