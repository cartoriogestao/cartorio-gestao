"""O RELATÓRIO ANUAL DO USO DE IA À COGEX — a montagem, sem tela.

O QUE ELE TEM (LF01, 19/10/2026)
    As quatro partes do Código de Normas do MA, art. 170, § 4º — sistemas e
    finalidades, medidas de segurança, incidentes ou falhas, ações de
    mitigação —, mais o uso do ano por mês, por finalidade e por provedor (de
    `ia_uso`), os dados de cada fornecedor com as PENDÊNCIAS diante do
    requisito do MA, e o lembrete de que a declaração federal do Provimento
    CN 213/2026 é outra obrigação.

O QUE ELE NÃO FAZ
    Não decide se o uso é conforme: mostra o que o código faz, o que foi
    registrado e o que o oficial preencheu, e aponta o que contraria o
    requisito como pendência A CONFERIR. Não envia nada a ninguém — o envio à
    COGEX é do oficial. E não leva conteúdo: nem texto de ato, nem pergunta,
    nem resposta; só contagens e o que o oficial escreveu nos incidentes.

SÓ LÊ. Banco em que as tabelas ainda não existem sai com o ano vazio.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import ia_catalogo as CAT
import ia_uso as USO
from bd_nativo import banco

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


def _vazio() -> dict[str, int]:
    return {"chamadas": 0, "ok": 0, "erro": 0, "recusado": 0, "entrada": 0,
            "saida": 0, "mascaradas": 0, "sem_mascara": 0}


def _somar(alvo: dict, linha: dict) -> None:
    alvo["chamadas"] += linha["chamadas"]
    alvo[linha["resultado"]] = alvo.get(linha["resultado"], 0) + linha["chamadas"]
    for campo in ("entrada", "saida", "mascaradas", "sem_mascara"):
        alvo[campo] += linha[campo]


def _nome_do_provedor(provedor: str) -> str:
    import agente_provedores as AP
    return (AP.PROVEDORES.get(provedor) or {}).get("nome") or provedor


def _provedores_com_chave(con, pasta_de_dados: Any) -> set[str]:
    """Os provedores que têm chave gravada hoje — no agente e nos robôs."""
    import agente_provedores as AP
    achados = {p for p in AP.PROVEDORES if pasta_de_dados and AP.tem_chave(pasta_de_dados, p)}
    try:
        import robo_schema as RS
        achados |= {p for p in RS.PROVEDORES if RS.api_key_do_provedor(con, p)}
    except Exception:  # noqa: BLE001 — banco sem os robôs: só não conta
        pass
    return achados


def montar(con, ano: int, *, pasta_de_dados: Any = None,
           serventia: dict | None = None) -> dict:
    """Tudo o que a página do relatório mostra, para o ano pedido. SÓ LÊ."""
    ano = int(ano)
    linhas = USO.uso_do_ano(con, ano)

    por_mes = [{"mes": f"{ano:04d}-{n:02d}", "nome": MESES[n - 1], **_vazio()}
               for n in range(1, 13)]
    por_finalidade: dict[str, dict] = {}
    por_provedor: dict[str, dict] = {}
    total = _vazio()
    for l in linhas:
        _somar(por_mes[int(l["mes"][5:7]) - 1], l)
        _somar(por_finalidade.setdefault(l["finalidade"], _vazio()), l)
        _somar(por_provedor.setdefault(l["provedor"], _vazio()), l)
        _somar(total, l)

    sistemas = []
    for item in CAT.CATALOGO:
        uso = por_finalidade.get(item["codigo"], _vazio())
        sistemas.append({**item, "uso": uso, "teto_texto": CAT.teto_de(item),
                         "inciso_texto": CAT.INCISOS_DO_ART_171.get(
                             item["inciso"].split()[0], "")})
    finalidades = [{"codigo": c, "nome": CAT.nome_da_finalidade(c),
                    "no_catalogo": CAT.entrada(c) is not None, **v}
                   for c, v in sorted(por_finalidade.items(),
                                      key=lambda kv: (-kv[1]["chamadas"], kv[0]))]
    provedores = [{"provedor": p, "nome": _nome_do_provedor(p), **v}
                  for p, v in sorted(por_provedor.items(),
                                     key=lambda kv: (-kv[1]["chamadas"], kv[0]))]

    incidentes = USO.incidentes(con, ano)
    gravados = USO.fornecedores(con)
    em_uso = (set(USO.provedores_usados(con, ano))
              | _provedores_com_chave(con, pasta_de_dados))
    fornecedores = [{"provedor": p, "nome": _nome_do_provedor(p),
                     "dados": gravados.get(p) or {},
                     "usado_no_ano": p in por_provedor,
                     "pendencias": USO.pendencias(gravados.get(p))}
                    for p in sorted(em_uso)]

    nao_informada = total["chamadas"] - total["mascaradas"] - total["sem_mascara"]
    medidas = [
        "Cada chamada a provedor de IA fica registrada (quando, sistema, "
        f"finalidade, provedor, modelo, tokens e resultado), sem o texto: "
        f"{total['chamadas']} chamada(s) em {ano}.",
        f"Máscara de dado de pessoa onde o sistema a aplica (ver a tabela dos "
        f"sistemas): {total['mascaradas']} chamada(s) com máscara, "
        f"{total['sem_mascara']} sem máscara"
        + (f" e {nao_informada} sem a informação" if nao_informada else "") + ".",
        f"Chave de API fora do banco ({CAT.CHAVE_FORA_DO_BANCO}); o banco vai no "
        "backup. Exceção: os robôs de rascunho guardam a chave no banco "
        "(robo_config).",
        "Endereço dos provedores fixo no código: nenhuma tela ou resposta da IA "
        "escolhe para onde os dados vão.",
        # «EM TODOS OS SISTEMAS» ERA FALSO (achado B3 da auditoria LS03): os
        # avisos de fraude do malote entram direto na lista, por ordem do
        # oficial de 13/10/2026, e a triagem do malote decide sozinha o que é
        # só ciência. O relatório vai à COGEX; diz a exceção com o seu remédio.
        "Revisão humana em cada sistema, na forma da coluna «revisão humana»: "
        "a IA aponta, sugere ou rascunha; quem decide, lavra, sela e cobra é a "
        "pessoa (art. 169, IV). Duas exceções têm revisão DEPOIS, e não antes: "
        "as pessoas dos avisos de fraude do malote entram direto na lista de "
        "atenção (ordem do oficial de 13/10/2026), marcadas «entrado pela IA» e "
        "listadas no despacho diário do oficial; e o expediente que a triagem "
        "lê como ciência vai à fila do oficial («só ciência — confira»).",
        "Tetos de uso por sistema (coluna «teto»), para que um laço que não "
        "fecha não gaste sem limite.",
    ]
    return {
        "ano": ano,
        "serventia": serventia or {},
        "aviso": CAT.AVISO_DO_TEXTO_OFICIAL,
        "norma": CAT.NORMA_DO_RELATORIO,
        "incisos": CAT.INCISOS_DO_ART_171,
        "requisito": CAT.REQUISITO_DO_FORNECEDOR,
        "lembrete_federal": CAT.LEMBRETE_FEDERAL,
        "sistemas": sistemas,
        "primeiro_registro": USO.primeiro_registro(con),
        "por_mes": por_mes,
        "por_finalidade": finalidades,
        "por_provedor": provedores,
        "total": total,
        "medidas": medidas,
        "incidentes": incidentes,
        "falhas": [{**f, "nome": CAT.nome_da_finalidade(f["finalidade"]),
                    "provedor_nome": _nome_do_provedor(f["provedor"])}
                   for f in USO.falhas_do_ano(con, ano)],
        "mitigacoes": [i for i in incidentes if (i.get("mitigacao") or "").strip()],
        "fornecedores": fornecedores,
        "fora_do_catalogo": [f for f in finalidades if not f["no_catalogo"]],
    }


def hoje() -> date:
    """O dia de hoje, num lugar só — é o que o teste troca para ver janeiro."""
    return date.today()


def aviso_do_painel(hoje: date) -> dict | None:
    """Em JANEIRO, o lembrete do relatório do ano anterior; fora dele, nada.

    A norma lida não fixa dia para a entrega (o resumo avisa para não
    inventar um); janeiro é quando o ano anterior acabou de fechar.
    """
    if hoje.month != 1:
        return None
    return {"ano": hoje.year - 1}


def ano_pedido(texto: Any, hoje: date) -> int:
    """O ano da tela: o pedido, se for um ano; senão o anterior em janeiro e o
    corrente no resto do ano."""
    try:
        ano = int(str(texto or "").strip())
    except ValueError:
        ano = 0
    if 2000 <= ano <= hoje.year:
        return ano
    return hoje.year - 1 if hoje.month == 1 else hoje.year


def serventia_de(con) -> dict:
    """Nome, CNS, cidade e UF da serventia, das configurações. SÓ LÊ."""
    chaves = ("unit_name", "ri_cns", "ri_cidade", "ri_uf")
    linhas = banco(con).ler("SELECT key, value FROM settings WHERE key = ANY(%s) "
                            "ORDER BY key", (list(chaves),))
    return {l["key"]: l["value"] for l in linhas}
