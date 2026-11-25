"""
Exportacao para o ONR — Operador Nacional do Registro de Imoveis.

O formato aqui NAO foi inferido de documentacao: foi levantado dos arquivos que
esta serventia efetivamente enviou, encontrados em arquivos\\eoficio\\ONR. Isso
importa porque o ONR trocou a especificacao antiga em XML por modelos em JSON,
e implementar contra o modelo errado seria trabalho perdido.

O que os arquivos reais mostraram:

  Indicador Pessoal  XML, raiz <BANCOLIGHT>, um <INDIVIDUO> por vinculo.
                     Datas em ddmmaaaa. Documento desconhecido vai como
                     '00000000000' — nao vazio.

                     CORRECAO DE 04/09/2026: aqui estava escrito "7.772 de
                     10.685 registros". Recontado nos 19 XML de
                     arquivos\\eoficio\\ONR, sao 10.781 <INDIVIDUO>: 7.812
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
                     CORRECAO DE 23/11/2026: o formato e os codigos agora
                     seguem o manual do ONR, v2.0, em `onr_ir_json`. O unico
                     arquivo antigo tinha UF, CIDADE e TIPO_LOGRADOURO zerados
                     e nao servia de modelo.

Nada aqui transmite arquivo. A geracao produz o arquivo para conferencia e
envio manual pelos canais do ONR.
"""
from __future__ import annotations

from datetime import date
from xml.sax.saxutils import escape

# ------------------------------------------------------------------ codigos

# tbRI_TipoImovel.onr_id do E-Oficio, so para mostrar o que veio do sistema antigo.
# **NAO E A TABELA DO ARQUIVO DO ONR**, que vai de 1 a 13: ver `onr_ir_json.TIPOS_DE_IMOVEL`.
TIPO_IMOVEL_ONR = {
    0: "Casa", 1: "Apto", 2: "Loja", 3: "Sala/Conjunto", 4: "Terreno/fração",
    5: "Galpão", 6: "Prédio Comercial", 7: "Prédio Residencial",
    8: "Fazenda/Sítio/Chácara", 9: "Outros",
}

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


def gerar_indicador_real(registros: list[dict], casa) -> bytes:
    """O arquivo JSON do manual do ONR, v2.0, a partir de registros ja montados.

    Quem monta e valida e `onr_ir_json`, e quem escolhe as fichas e `onr_ir_lotes`. Registro que
    contraria o manual derruba o arquivo aqui, antes de chegar ao portal.
    """
    import onr_ir_json as IRJ
    return IRJ.arquivo_json(registros, casa)


def nome_arquivo(tipo: str, inicio: date, fim: date) -> str:
    """Padrao observado: IndicadorPessoal_ddmmaaaa_ddmmaaaa.XML"""
    a = inicio.strftime("%d%m%Y")
    b = fim.strftime("%d%m%Y")
    if tipo == "PESSOAL":
        return f"IndicadorPessoal_{a}_{b}.XML"
    if tipo == "REAL_XML":
        return f"IndicadorReal_{a}_{b}.XML"
    return f"IndicadorReal_{a}_{b}.json"
