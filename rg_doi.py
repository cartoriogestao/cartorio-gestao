"""A DOI DO REGISTRO DE TÍTULOS E DOCUMENTOS — CN-MA art. 962.

    «O oficial comunicará à Secretaria da Receita Federal do Brasil o registro de atos que
     envolvam aquisição ou alienação de bens imóveis celebradas por instrumento particular.»

O ARQUIVO É UM SÓ, O DA SERVENTIA. A decisão do oficial de 28/08/2026 vale aqui: a linha do
RTD entra na mesma tela e no mesmo arquivo das escrituras e do RI (`ri_web.ri_doi`), e o
montador é o de `notas_doi`. O layout do DOI-Web tem o tipo de serviço 3, «Registro de
títulos e documentos», e o tipo de ato 4, «Registro», ou 6, «para fins de conservação».

O LADO DE CADA PARTE SAI DO PAPEL DELA, com a mesma régua das escrituras: o procurador não é
quem vendeu. Quem não se classifica para a declaração, e diz por quê.
"""
from __future__ import annotations

from typing import Any

import notas_doi as NDOI
from bd_nativo import banco


class DoiDoRegistroError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


TIPO_SERVICO_RTD = "3"
TIPO_ATO_REGISTRO = "4"
TIPO_ATO_CONSERVACAO = "6"
NATUREZA_INSTRUMENTO_PARTICULAR = "1"


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _centavos(v: Any) -> int | None:
    limpo = _texto(v).replace("R$", "").replace(" ", "")
    if not limpo:
        return None
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return int(round(float(limpo) * 100))
    except ValueError as erro:
        raise DoiDoRegistroError(f"«{v}» não é um valor em reais.") from erro


def do_registro(con, registro_id: int) -> dict | None:
    linha = banco(con).um("SELECT * FROM rg_doi WHERE registro_id=%s", (int(registro_id),))
    return dict(linha) if linha else None


def gravar(con, registro_id: int, *, operacao: str, matricula: str, valor: Any, data: str = "",
           tipo_imovel: str = "", endereco: str = "", area: str = "", torna: Any = None,
           folha: str = "", agora: str, usuario: str | None = None) -> dict:
    """Marca que o registro envolve imóvel, com os dados da declaração. ESCREVE."""
    from ri_ctp import TIPO_OPERACAO
    bd = banco(con)
    registro = bd.um("SELECT id, atribuicao FROM rg_registros WHERE id=%s", (int(registro_id),))
    if not registro or int(registro["atribuicao"]) != 4:
        raise DoiDoRegistroError("A DOI do art. 962 é de registro do RTD.")
    if _texto(operacao) not in TIPO_OPERACAO:
        raise DoiDoRegistroError("Escolha a operação imobiliária.")
    bd.escrever(
        """INSERT INTO rg_doi(registro_id, operacao, matricula, valor_centavos, data_ato, tipo_imovel,
               endereco, area, torna_centavos, folha, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (registro_id) DO UPDATE SET operacao=EXCLUDED.operacao, matricula=EXCLUDED.matricula,
               valor_centavos=EXCLUDED.valor_centavos, data_ato=EXCLUDED.data_ato,
               tipo_imovel=EXCLUDED.tipo_imovel, endereco=EXCLUDED.endereco, area=EXCLUDED.area,
               torna_centavos=EXCLUDED.torna_centavos, folha=EXCLUDED.folha""",
        (int(registro_id), _texto(operacao), _texto(matricula), _centavos(valor), _texto(data)[:10] or None,
         _texto(tipo_imovel) or None, _texto(endereco) or None, _texto(area) or None, _centavos(torna),
         _texto(folha) or None, agora, usuario))
    return {"registro_id": int(registro_id)}


def retirar(con, registro_id: int) -> None:
    """Desfaz a marca, quando o título não envolve imóvel. ESCREVE."""
    banco(con).escrever("DELETE FROM rg_doi WHERE registro_id=%s", (int(registro_id),))


def declaracoes_da_competencia(con, primeiro: str, seguinte: str, cns: str, ibge: str) -> list[dict]:
    """As linhas do RTD no mês, com a declaração ou o que a impede. Só LÊ."""
    bd = banco(con)
    saida = []
    for r in bd.ler(
            """SELECT d.*, r.numero, r.volume, r.serie, r.natureza,
                      (SELECT MIN(a.data_ato) FROM rg_atos a
                        WHERE a.registro_id = r.id AND a.tipo = 'REGISTRO') AS data_do_registro,
                      (SELECT MIN(a.folha) FROM rg_atos a
                        WHERE a.registro_id = r.id AND a.tipo = 'REGISTRO') AS folha_do_registro
                 FROM rg_doi d JOIN rg_registros r ON r.id = d.registro_id ORDER BY r.id"""):
        dia = _texto(r["data_ato"] or r["data_do_registro"])[:10]
        if not (primeiro <= dia < seguinte):
            continue
        ato = {"id": int(r["registro_id"]), "data": dia, "livro": r["volume"] or r["serie"],
               "folha": _texto(r["folha"] or r["folha_do_registro"]), "natureza": r["natureza"],
               "numero_ordem": r["numero"], "doi_transacao": r["operacao"], "doi_matricula": r["matricula"],
               "valor_transacao": r["valor_centavos"], "doi_torna_dinheiro": r["torna_centavos"],
               "doi_tipo_imovel": r["tipo_imovel"], "doi_endereco": r["endereco"], "doi_area": r["area"]}
        partes = [{**dict(p), "qualificacao": p["papel"]} for p in bd.ler(
            "SELECT * FROM rg_partes WHERE registro_id=%s AND retirada_em IS NULL ORDER BY id",
            (int(r["registro_id"]),))]
        reg, problemas = NDOI.declaracao_da_escritura(
            ato, partes, cns, ibge, natureza_titulo=NATUREZA_INSTRUMENTO_PARTICULAR,
            tipo_servico=TIPO_SERVICO_RTD,
            tipo_ato=TIPO_ATO_CONSERVACAO if r["serie"] == "TD_F" else TIPO_ATO_REGISTRO)
        if reg:
            # O que `montar_registro` não preenche, como `ri_doi.montar` faz para o RI.
            reg["naturezaTitulo"] = NATUREZA_INSTRUMENTO_PARTICULAR
            reg["numeroRegistroAverbacao"] = str(int(r["numero"] or 0)).zfill(7)
        saida.append({"ato": ato, "registro": reg, "problemas": problemas,
                      "rotulo": f"RTD, registro {r['numero']} — {r['natureza'] or 'sem natureza'}"})
    return saida
