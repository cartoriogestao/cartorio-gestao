"""
Exportacao para o ONR — Operador Nacional do Registro de Imoveis.

O formato aqui NAO foi inferido de documentacao: foi levantado dos arquivos que
esta serventia efetivamente enviou, encontrados em C:\\ARPNET\\C11\\ONR. Isso
importa porque o ONR trocou a especificacao antiga em XML por modelos em JSON,
e implementar contra o modelo errado seria trabalho perdido.

O que os arquivos reais mostraram:

  Indicador Pessoal  XML, raiz <BANCOLIGHT>, um <INDIVIDUO> por vinculo.
                     Datas em ddmmaaaa. Documento desconhecido vai como
                     '00000000000' — nao vazio.

                     CORRECAO DE 04/09/2026: aqui estava escrito "7.772 de
                     10.685 registros". Recontado nos 19 XML de
                     C:\\ARPNET\\C11\\ONR, sao 10.781 <INDIVIDUO>: 7.812
                     onze zeros, 2.259 CPF, 604 CNPJ e 106 com catorze zeros.
                     A conclusao nao muda — 73% do que esta casa mandou tem o
                     documento zerado —, o numero, sim. Numero escrito em
                     comentario e numero que ninguem confere.

                     E ELE CONTRARIA O MODELO DO ONR, que diz em comentario
                     dentro do proprio XML: "A INFORMACAO DEVE SER MAIOR QUE
                     ZERO". Vale a regra do oficial de 24/08/2026 — na duvida,
                     como o E-Oficio fazia —, e `onr_carga` declara a
                     divergencia na tela, em vez de escolher calado.

  Indicador Real     JSON, {"INDICADOR_REAL": {"CNS": ..., "REAL": [...]}}.
                     Campos numericos sao codigos; TIPO_DE_IMOVEL vem da
                     tabela de dominio do E-Oficio, cuja coluna onr_id ja
                     traz o codigo do ONR.

Nada aqui transmite arquivo. A geracao produz o arquivo para conferencia e
envio manual pelos canais do ONR.
"""
from __future__ import annotations

import json
from datetime import date
from xml.sax.saxutils import escape

# ------------------------------------------------------------------ codigos

# tbRI_TipoImovel.onr_id do E-Oficio. A descricao fica ao lado para a tela.
TIPO_IMOVEL_ONR = {
    0: "Casa", 1: "Apto", 2: "Loja", 3: "Sala/Conjunto", 4: "Terreno/fração",
    5: "Galpão", 6: "Prédio Comercial", 7: "Prédio Residencial",
    8: "Fazenda/Sítio/Chácara", 9: "Outros",
}

TIPO_IMOVEL_PADRAO_RURAL = 8    # Fazenda/Sítio/Chácara
TIPO_IMOVEL_PADRAO_URBANO = 4   # Terreno/fração

LOCALIZACAO_URBANO = 1
LOCALIZACAO_RURAL = 2

# Valores observados nos arquivos enviados pela serventia.
TIPOENVIO_INCLUSAO = 0
REGISTRO_TIPO_MATRICULA = 1

DOC_DESCONHECIDO = "00000000000"


def _data_onr(iso: str | None) -> str:
    """'2024-03-18' -> '18032024'. Vazio quando nao ha data."""
    if not iso:
        return ""
    partes = str(iso)[:10].split("-")
    if len(partes) != 3:
        return ""
    ano, mes, dia = partes
    return f"{dia}{mes}{ano}"


def _so_digitos(valor) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


# --------------------------------------------------- Indicador Pessoal (XML)


def gerar_indicador_pessoal(vinculos: list[dict], cns: str = "") -> str:
    """Monta o XML <BANCOLIGHT> com um <INDIVIDUO> por vinculo pessoa-matricula.

    Cada linha e uma pessoa ligada a uma matricula por um ato. Uma pessoa com
    tres matriculas gera tres INDIVIDUO — e assim que o historico da serventia
    esta montado.
    """
    linhas = ['<?xml version="1.0" encoding="utf-8"?>', "<BANCOLIGHT>"]
    for v in vinculos:
        doc = _so_digitos(v.get("documento"))
        if len(doc) not in (11, 14):
            doc = DOC_DESCONHECIDO
        linhas += [
            "  <INDIVIDUO>",
            f"    <NOME>{escape(str(v.get('nome') or '').strip())}</NOME>",
            f"    <CNPJCPF>{doc}</CNPJCPF>",
            f"    <NMATRICULA>{escape(str(v.get('matricula') or '').strip())}</NMATRICULA>",
            f"    <TIPODEATO>{escape(str(v.get('tipo_ato') or 'MATRICULA').strip())}</TIPODEATO>",
            f"    <DTREGAVERB>{_data_onr(v.get('data_ato'))}</DTREGAVERB>",
            f"    <DTVENDA>{_data_onr(v.get('data_venda'))}</DTVENDA>",
            "  </INDIVIDUO>",
        ]
    linhas.append("</BANCOLIGHT>")
    return "\n".join(linhas)


# ------------------------------------------------------ Indicador Real (JSON)


def _tipo_imovel_onr(matricula: dict) -> int:
    bruto = matricula.get("tipo_imovel")
    if bruto is not None and str(bruto).strip().isdigit():
        codigo = int(str(bruto).strip())
        if codigo in TIPO_IMOVEL_ONR:
            return codigo
    rural = (matricula.get("rural_urbano") or "").upper().startswith("R")
    return TIPO_IMOVEL_PADRAO_RURAL if rural else TIPO_IMOVEL_PADRAO_URBANO


def gerar_indicador_real(matriculas: list[dict], cns: str) -> str:
    """Monta o JSON do Indicador Real.

    Campos não aplicáveis vão como null, do jeito que os arquivos enviados
    fazem — o ONR distingue ausente de vazio, então não se troca null por "".
    """
    reais = []
    for m in matriculas:
        rural = (m.get("rural_urbano") or "").upper().startswith("R")
        bloco_rural = {
            "CAR": m.get("car") or "",
            "NIRF": m.get("nirf") or "",
            "CCIR": m.get("ccir") or "",
            "NUMERO_INCRA": m.get("incra") or "",
            "SIGEF": m.get("sigef") or "",
            "DENOMINACAORURAL": (m.get("logradouro") or "") if rural else "",
            "ACIDENTEGEOGRAFICO": "",
        }
        reais.append({
            "TIPOENVIO": TIPOENVIO_INCLUSAO,
            "NUMERO_REGISTRO": str(m.get("numero") or "").strip(),
            "REGISTRO_TIPO": REGISTRO_TIPO_MATRICULA,
            "TIPO_DE_IMOVEL": _tipo_imovel_onr(m),
            "LOCALIZACAO": LOCALIZACAO_RURAL if rural else LOCALIZACAO_URBANO,
            "TIPO_LOGRADOURO": 0,
            "NOME_LOGRADOURO": m.get("logradouro") or "",
            "NUMERO_LOGRADOURO": m.get("numero_predial") or "",
            "UF": 0,
            "CIDADE": 0,
            "BAIRRO": m.get("bairro") or "",
            "CEP": _so_digitos(m.get("cep")),
            "COMPLEMENTO": m.get("complemento_endereco") or "",
            "QUADRA": None,
            "CONJUNTO": None,
            "SETOR": None,
            "LOTE": None,
            "LOTEAMENTO": None,
            "CONTRIBUINTE": None,
            "RURAL": bloco_rural,
            "CONDOMINIO": None,
        })
    return json.dumps({"INDICADOR_REAL": {"CNS": cns, "REAL": reais}},
                      ensure_ascii=False, indent=2)


def nome_arquivo(tipo: str, inicio: date, fim: date) -> str:
    """Padrao observado: IndicadorPessoal_ddmmaaaa_ddmmaaaa.XML"""
    a = inicio.strftime("%d%m%Y")
    b = fim.strftime("%d%m%Y")
    if tipo == "PESSOAL":
        return f"IndicadorPessoal_{a}_{b}.XML"
    return f"IndicadorReal_{a}_{b}.json"
