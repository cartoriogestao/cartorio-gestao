"""Este selo é isento? A régua, num lugar só. Só LÊ.

POR QUE EXISTE (G005, achado G-5 da auditoria G002, 18/11/2026): a régua do
isento era `sd_selos.texto ILIKE '%Selo Isento%'`, repetida no aviso do
comprovante, na fila do Portal do Selo, nos isentos do dia, na conferência
local e na lista dos selos pagos sem cobertura. Seis selos do RCPN isentos no
TJ (averbações de 24/09 a 16/10/2026) ficaram com o texto NULL e sumiram de
todas elas ao mesmo tempo: nem aviso, nem fila, nem cobrança — e dois já
venceram sem comprovante.

DE ONDE VEIO O TEXTO VAZIO: do selo DIGITADO. Quem lança a averbação e digita
o número do selo tirado fora do sistema passa por
`ato_selado.registrar_selo_obtido_a_mao`, que só guarda o número — o texto
que o aparelho imprimiu não vem junto (a tela não pede a etiqueta inteira
desde o relato #66, de 15/09/2026). A marca «ato gratuito» do formulário se
perdia no caminho.

A RÉGUA:
  1. **Selo com texto: vale o texto, e só ele.** É a mesma régua de sempre;
     nada muda para os 1.500 selos que o aparelho escreveu.
  2. **Selo sem texto: vale a resposta do TJ** (`ge_portal_selos`, situação
     ACHADO), quando a consulta já chegou nele.
  3. **Sem texto e sem resposta: vale a marca da casa** — o «ato gratuito»
     que o escrevente marcou ao digitar o selo (`sd_selos.isento_declarado`)
     ou a coluna `isento` do ato, nas tabelas que a têm.

O TJ vem antes da marca da casa porque é ele que diz o que o selo é. E é ele
que separa a gratuidade presumida (14.a, 14.c), que o portal devolve com
`isento` falso e o aviso do comprovante não cobra.

Os bancos de teste montados à mão não têm todas as tabelas: o que não existe
fica fora da conta, e a régua cai para a do texto.
"""
from __future__ import annotations

from typing import Any, Iterable

from bd_nativo import banco

#: A marca que o aparelho escreve no texto do selo isento.
MARCA = "Selo Isento"
#: O padrão do `ILIKE` — o mesmo de sempre (`gratuidade_comprovante`).
PADRAO = "%Selo Isento%"
#: Tabelas de ato que guardam a marca de isenção da casa ao lado do selo
#: (as mesmas de `gestor_fiscal.TABELAS_COM_ISENTO`).
TABELAS_COM_ISENTO = ("ri_atos", "ri_certidoes", "ra_atos")
#: A coluna do selo digitado à mão marcado «ato gratuito»
#: (`selador_config.MIGRACOES`).
COLUNA_DECLARADA = "isento_declarado"


def sem_texto(texto: Any) -> bool:
    """O selo não tem texto gravado? Só calcula."""
    return not str(texto or "").strip()


def _fontes(bd) -> set[tuple[str, str]]:
    """As colunas que a régua lê e que existem neste banco. Uma consulta só:
    a barra do comprovante passa por aqui em toda tela."""
    pares = [("sd_selos", COLUNA_DECLARADA), ("ge_portal_selos", "isento"),
             *((t, "isento") for t in TABELAS_COM_ISENTO)]
    filtro = " OR ".join(["(table_name = %s AND column_name = %s)"] * len(pares))
    return {(r["table_name"], r["column_name"]) for r in bd.ler(
        "SELECT table_name, column_name FROM information_schema.columns "
        f"WHERE table_schema = current_schema() AND ({filtro})",
        tuple(x for par in pares for x in par))}


def _sinais_sem_texto(bd, alias: str) -> str:
    """O que diz que um selo SEM TEXTO é isento, em SQL. Sem parâmetros.

    Vazio quando o banco não tem nenhuma das fontes.
    """
    tem = _fontes(bd)
    da_casa = []
    if ("sd_selos", COLUNA_DECLARADA) in tem:
        da_casa.append(f"coalesce({alias}.{COLUNA_DECLARADA}, 0) = 1")
    for tabela in TABELAS_COM_ISENTO:
        if (tabela, "isento") in tem:
            da_casa.append(
                f"({alias}.tabela = '{tabela}' AND EXISTS (SELECT 1 FROM {tabela} x "
                f"WHERE x.id = {alias}.ato_id AND coalesce(x.isento, 0) = 1))")
    casa = " OR ".join(da_casa)
    if ("ge_portal_selos", "isento") not in tem:
        return casa
    achado = ("SELECT 1 FROM ge_portal_selos p WHERE p.numero = "
              f"{alias}.numero AND p.situacao = 'ACHADO'")
    tj = f"EXISTS ({achado} AND coalesce(p.isento, 0) = 1)"
    if not casa:
        return tj
    return f"({tj} OR (NOT EXISTS ({achado}) AND ({casa})))"


def condicao(con, alias: str = "s") -> tuple[str, tuple]:
    """`(sql, parametros)` que diz «este selo é isento» numa consulta a `sd_selos`.

    `alias` é o nome da tabela na consulta (`s`, ou `sd_selos` sem apelido).
    Nunca dá NULL: pode ir atrás de `NOT`.
    """
    bd = banco(con)
    pelo_texto = f"coalesce({alias}.texto, '') ILIKE %s"
    sinais = _sinais_sem_texto(bd, alias)
    if not sinais:
        return f"({pelo_texto})", (PADRAO,)
    return (f"({pelo_texto} OR (trim(coalesce({alias}.texto, '')) = '' AND {sinais}))",
            (PADRAO,))


def isentos_sem_texto(con, ids: Iterable[Any]) -> set[int]:
    """Dos selos `ids`, os SEM TEXTO que a régua diz isentos. Só LÊ.

    Para quem já leu os selos e decide pelo texto em Python (a conferência,
    os isentos do dia): o texto continua decidindo como antes, e só o selo
    vazio passa por aqui.
    """
    lista = sorted({int(i) for i in ids if i is not None})
    if not lista:
        return set()
    bd = banco(con)
    sinais = _sinais_sem_texto(bd, "s")
    if not sinais:
        return set()
    marcas = ",".join(["%s"] * len(lista))
    return {int(r["id"]) for r in bd.ler(
        f"SELECT s.id FROM sd_selos s WHERE s.id IN ({marcas}) "
        f"AND trim(coalesce(s.texto, '')) = '' AND {sinais}", tuple(lista))}


def selo_e_isento(con, selo_id: Any) -> bool:
    """Um selo só, pelo id: é isento? Só LÊ. Selo que não existe não é."""
    sql, args = condicao(con, "s")
    return banco(con).um(
        f"SELECT 1 AS sim FROM sd_selos s WHERE s.id = %s AND {sql}",
        (int(selo_id), *args)) is not None
