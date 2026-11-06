"""Prévia da negativa no MESMO modelo RI_NOTA da emissão, sem criar nota."""
from __future__ import annotations

import html
from datetime import date

from bd_nativo import banco
import modelos_da_casa as MODELOS
import serventia as SV


def previa(con, pedido: dict, get_settings, *, fmt_date=str) -> str:
    from jinja2.sandbox import SandboxedEnvironment
    import ri_qualificacao_ia as Q
    from ri_web import data_por_extenso

    itens = (pedido.get("resultado") or {}).get("exigencias") or []
    if not itens:
        raise Q.QualificacaoIAError("O rascunho não contém exigências para nota devolutiva.")
    p = banco(con).um("SELECT * FROM ri_protocolos WHERE id=%s", (pedido["protocolo_id"],))
    if not p:
        raise Q.QualificacaoIAError("Prenotação não encontrada.")
    p = dict(p)
    configuracao = get_settings()
    sv = SV.dados(configuracao)
    linhas = [Q.linha_da_exigencia(x) for x in itens]
    exigencias = "".join(f"<p><b>{i}.</b> {html.escape(t)}</p>"
                         for i, t in enumerate(linhas, 1))
    # Nenhum número oficial é reservado; o prazo vem do protocolo, não do modelo.
    contexto = {
        "nota": {"numero": "RASCUNHO — NÃO EMITIDA", "fundamentacao": "",
                 "prazo_ate": fmt_date(p.get("data_limite") or "")},
        "protocolo": p | {"data_prenotacao": fmt_date(p.get("data_prenotacao") or "")},
        "exigencias_odf": exigencias,
        "serventia": sv | {"nome": sv["unit_name"], "cns": configuracao.get("ri_cns", ""),
                            "cidade": configuracao.get("ri_cidade", ""), "uf": configuracao.get("ri_uf", "MA"),
                            "registrador": "", "substituta": ""},
        "hoje_extenso": data_por_extenso(date.today()),
    }
    corpo = MODELOS.corpo_de(con, "RI_NOTA")
    # Dados da prenotação são texto, nunca HTML executável.
    contexto["protocolo"] = {k: html.escape(v) if isinstance(v, str) else v
                             for k, v in contexto["protocolo"].items()}
    documento = SandboxedEnvironment(autoescape=False).from_string(corpo).render(**contexto)
    return MODELOS.sem_o_que_executa(corpo, documento)
