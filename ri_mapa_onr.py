"""A base do Mapa do Registro de Imóveis do ONR — a parte que é do Gestão.

    «A serventia vai entregar o mapa ao ONR em breve.» — LF02, 19/10/2026

O QUE O ONR PEDE, E O QUE DISSO É DESTE SISTEMA
    O mapa leva, por imóvel, o **polígono** e quatro atributos — MATRICULA,
    CNS, PROPRIETAR e AREA_HA —, em Shapefile ou GeoPackage. **O Gestão não
    guarda geometria**, e por isso não gera o arquivo: quem tem o polígono é o
    QGIS, com o plugin de referência (em-rezende/qgis-registro-onr-plugin,
    licença MIT), que lê os atributos de uma tabela `imoveis`. Este módulo é
    essa tabela, de dois jeitos: a VIEW `onr_mapa_imoveis`, que o plugin lê
    direto (trocando o `mysql.connector` por `psycopg`), e o CSV da rota
    `/ri/mapa-onr.csv`, para juntar à camada à mão. Como usar, e o que falta,
    está em `docs/MAPA_ONR.md`.

ONDE CADA ATRIBUTO MORA — medido no esquema em 19/10/2026
    MATRICULA   `ri_matriculas.numero`, com `-complemento` quando há: é como a
                ficha se escreve na tela (`ri_ficha.html`, `ri_matriculas.html`).
    CNS         `settings.ri_cns`, e `serventia_cns` quando aquela não tem
                dígito — a ordem de `ri_onr_web._cns`, que é o outro canal desta
                casa com o ONR. Só os dígitos, como `ri_onr_central` os manda.
    PROPRIETAR  `ri_partes` com `proprietario_ativo = 1`, **e não
                `proprietario`**: a segunda diz que a pessoa já foi dona
                (`ri_onr_central._proprietarios`), e o mapa poria no imóvel
                quem o vendeu. Vários, juntos por «; », na ordem em que foram
                gravados; o mesmo nome escrito duas vezes entra uma.
    AREA_HA     `ri_matriculas.area_valor` + `area_unidade` — TEXTO, em hectare
                ou em metro —, pela régua da casa (`onr_api.area_em_metros`), e
                dividido por 10.000. O que a régua não sabe ler fica vazio.

QUEM FICA DE FORA
    A matrícula encerrada — `encerrada = 1` **ou** `situacao = 'ENCERRADA'`,
    as duas marcas que `gestor_conferencia` confere juntas — e as outras
    situações de `ri_schema.SITUACOES` que dizem que a ficha não vale mais
    (`ANULADA`, `CANCELADA`, `INEXISTENTE`). **Não se filtra por
    `situacao = 'ATIVA'`**: a reabertura (`ri_reabrir_matricula`) grava
    `'ATIVO'`, e a ficha reaberta sumiria do mapa sem ninguém ver.

A ÁREA DA VIEW VEM DE UM DE-PARA, E NÃO DE SQL — E O MOTIVO É A RÉGUA
    A coluna guarda a área de catorze jeitos (`231,00,00`, `347.0168`, `63`,
    `8.435,26`, `19,3419 ha (dezenove hectares…)`), e a régua que os lê já
    errou por mil e por dez mil vezes antes de ficar certa — a história está
    em `onr_api.area_em_metros`. **Uma VIEW não chama Python**, e reescrever a
    régua em SQL seria a segunda definição que aquela docstring proíbe: «eram
    dois lugares e um deles não a chamava». Por isso a régua roda em Python e
    grava o resultado em `ri_mapa_onr_areas`, um de-para do TEXTO da coluna
    para os metros, e a VIEW o junta pela coluna.

    **O de-para se refaz a cada subida do sistema** (`init_mapa_onr_schema`), e
    não no download: GET não escreve (`docs/ARQUITETURA.md`). Um texto de área
    que a casa nunca tinha escrito — a ficha aberta ou corrigida depois da
    subida — aparece **sem área** na VIEW até a próxima, e não com área errada:
    a junção é pelo texto, e texto novo não casa com o de-para velho. O plugin,
    sem a área do banco, calcula a geodésica, que é a que o ONR pede. **O CSV
    não tem esse atraso**: `dados_do_mapa` chama a régua na hora.

PostgreSQL nativo, pelo `bd_nativo`.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Iterable

import onr_api as API
from bd_nativo import banco

# As situações de `ri_schema.SITUACOES` que tiram a ficha do mapa. Ver o
# cabeçalho: a lista é do que SAI, e não do que fica, por causa do `'ATIVO'`.
SITUACOES_FORA_DO_MAPA = ("ENCERRADA", "ANULADA", "CANCELADA", "INEXISTENTE")

# Os nomes do ONR, na ordem do plugin (`fields.append(...)` em
# `processar_dados`). O CSV sai com eles para que a junção no QGIS dê a
# camada com os nomes que o ONR recebe, sem renomear coluna.
COLUNAS_DO_ONR = ("MATRICULA", "CNS", "PROPRIETAR", "AREA_HA")

# O separador dos CSV da casa (`gestor_web.gestor_erros_csv`). A área sai com
# PONTO decimal: é o que o QGIS lê sem marcar nada no diálogo, e o CSV é para
# ele — `docs/MAPA_ONR.md` diz como abrir.
SEPARADOR_DO_CSV = ";"

# O CSV leva o nome de cada proprietário: é exportação de dado pessoal, e por
# isso é do oficial, com rastro na auditoria.
QUEM_BAIXA = ("ADMIN",)

# O B-tree do PostgreSQL recusa chave que, mesmo comprimida, passa de ~2,7 KB
# (o limite que levou o `imovel_norm` para trigramas, em `ri_schema`). Área
# com mais de mil bytes não é área — é teor colado na coluna —, e um INSERT
# recusado derrubaria a subida do sistema inteiro. Ela fica fora do de-para,
# e sem área na VIEW; o CSV, que não passa pelo de-para, a lê.
_MAIOR_CHAVE_DO_DE_PARA = 1000

# ------------------------------------------------- a regra, escrita uma vez
#
# Os pedaços de SQL abaixo são a definição de «quem entra e com o quê», e
# servem à VIEW e a `dados_do_mapa` — escritos duas vezes, a VIEW e o CSV
# acabariam dizendo coisas diferentes do mesmo imóvel. São constantes do
# código: nada aqui vem da tela.

_MATRICULA = "concat_ws('-', btrim(m.numero), nullif(btrim(m.complemento), ''))"

_CNS = """coalesce(
        (SELECT nullif(regexp_replace(s.value, '[^0-9]', '', 'g'), '')
           FROM settings s WHERE s.key = 'ri_cns'),
        (SELECT nullif(regexp_replace(s.value, '[^0-9]', '', 'g'), '')
           FROM settings s WHERE s.key = 'serventia_cns'),
        '')"""

# `''`, e não NULL, quando não há dono ativo: o plugin faz
# `str(db_data.get("proprietario", ""))`, e NULL viraria a palavra «None» no
# arquivo que vai ao ONR. O CNS segue a mesma regra, pelo mesmo motivo.
_PROPRIETARIOS = """coalesce((
        SELECT string_agg(d.nome, '; ' ORDER BY d.primeiro)
          FROM (SELECT btrim(p.nome) AS nome, min(p.id) AS primeiro
                  FROM ri_partes p
                 WHERE p.matricula_id = m.id
                   AND p.proprietario_ativo = 1
                   AND btrim(p.nome) <> ''
                 GROUP BY btrim(p.nome)) d), '')"""

_NO_MAPA = ("COALESCE(m.encerrada, 0) = 0 AND m.situacao NOT IN ("
            + ", ".join(f"'{s}'" for s in SITUACOES_FORA_DO_MAPA) + ")")

SCHEMA_DO_DE_PARA = """
CREATE TABLE IF NOT EXISTS ri_mapa_onr_areas (
    area_valor text NOT NULL,
    area_unidade text NOT NULL DEFAULT '',
    area_m2 bigint,
    PRIMARY KEY (area_valor, area_unidade)
)"""

# `CREATE OR REPLACE`, e não DROP e CREATE: o acesso do QGIS se dá por um
# `GRANT SELECT` nesta VIEW (ver `docs/MAPA_ONR.md`), e o DROP o apagaria a
# cada subida. Sem ORDER BY de propósito: quem lê a VIEW filtra por matrícula.
VIEW_DO_MAPA = f"""
CREATE OR REPLACE VIEW onr_mapa_imoveis AS
SELECT {_MATRICULA} AS matricula,
       {_CNS} AS cns,
       {_PROPRIETARIOS} AS proprietario,
       round(a.area_m2 / 10000.0, 4) AS area_ha
  FROM ri_matriculas m
  LEFT JOIN ri_mapa_onr_areas a
         ON a.area_valor = m.area_valor
        AND a.area_unidade = coalesce(m.area_unidade, '')
 WHERE {_NO_MAPA}"""


def init_mapa_onr_schema(con) -> None:
    """O de-para, a VIEW e as áreas de hoje. Idempotente; roda a cada subida.

    Vem depois de `init_ri_schema`: a VIEW lê `ri_matriculas` e `ri_partes`,
    e o PostgreSQL cobra a tabela já na criação dela.
    """
    bd = banco(con)
    bd.escrever(SCHEMA_DO_DE_PARA)
    bd.escrever(VIEW_DO_MAPA)
    atualizar_areas(bd)


def atualizar_areas(con) -> int:
    """Refaz o de-para do texto da área para metros. Devolve quantos textos.

    **Refaz tudo, e não só o que falta**: quem muda a régua muda o resultado
    de texto que já estava no de-para, e a subida seguinte é quando a régua
    nova passa a valer. O `ON CONFLICT ... WHERE ... IS DISTINCT FROM` só
    regrava a linha que mudou.

    Sem trava de assunto: o resultado é função só do texto, e duas passadas ao
    mesmo tempo gravariam o mesmo número — o `ON CONFLICT` cuida da chave.
    """
    bd = banco(con)
    valores: list[str] = []
    unidades: list[str] = []
    metros: list[int | None] = []
    for par in bd.ler(
            """SELECT DISTINCT m.area_valor, coalesce(m.area_unidade, '') AS area_unidade
                 FROM ri_matriculas m
                WHERE m.area_valor IS NOT NULL
                ORDER BY 1, 2"""):
        tamanho = len(par["area_valor"].encode()) + len(par["area_unidade"].encode())
        if tamanho > _MAIOR_CHAVE_DO_DE_PARA:
            continue
        valores.append(par["area_valor"])
        unidades.append(par["area_unidade"])
        metros.append(_metros(par["area_valor"], par["area_unidade"]))
    bd.escrever(
        """INSERT INTO ri_mapa_onr_areas (area_valor, area_unidade, area_m2)
           SELECT u.valor, u.unidade, u.metros
             FROM unnest(%s::text[], %s::text[], %s::bigint[]) AS u(valor, unidade, metros)
           ON CONFLICT (area_valor, area_unidade)
           DO UPDATE SET area_m2 = excluded.area_m2
            WHERE ri_mapa_onr_areas.area_m2 IS DISTINCT FROM excluded.area_m2""",
        (valores, unidades, metros))
    # O texto que nenhuma ficha escreve mais sai: o de-para não cresce para
    # sempre com cada correção de área.
    bd.escrever(
        """DELETE FROM ri_mapa_onr_areas a
            WHERE NOT EXISTS (SELECT 1 FROM ri_matriculas m
                               WHERE m.area_valor = a.area_valor
                                 AND coalesce(m.area_unidade, '') = a.area_unidade)""")
    return len(valores)


def _metros(valor: Any, unidade: Any) -> int | None:
    """A régua da casa, e o zero como «não se sabe».

    **Zero não é área**: é a afirmação de que o imóvel não tem área, e a régua
    já o devolve `None` no ramo do metro (`onr_api._metros_quadrados`). No do
    hectare, `"0"` ainda dá 0 — e no mapa seria um `AREA_HA` de 0,0000 ao lado
    do polígono. Vale para o CSV e para o de-para da VIEW, que passam por aqui.
    """
    return API.area_em_metros(valor, unidade) or None


def area_em_hectares(valor: Any, unidade: Any = None) -> float | None:
    """A área da ficha em hectares, com quatro casas — `None` se não se sabe.

    **Quatro casas são o metro quadrado** (1 m² = 0,0001 ha), e a régua da casa
    responde em metro quadrado inteiro: mais casas seriam precisão inventada.
    O `None` é resposta, e não falha — `3808` tanto pode ser 38,08 ha quanto
    3.808 m², e a régua prefere não saber a saber errado por cem vezes.
    """
    metros = _metros(valor, unidade)
    return None if metros is None else round(metros / 10_000, 4)


def dados_do_mapa(con, matriculas: Iterable[Any] | None = None) -> list[dict]:
    """`[{matricula, cns, proprietario, area_ha}]` das fichas que vão ao mapa.

    `matriculas` restringe às pedidas, escritas como a ficha as escreve
    (`"4015"`, `"4015-A"`); `None` traz todas, e uma lista vazia não traz
    nenhuma — pedir nada é pedir nada. A ordem é a do número da matrícula, e o
    `id` desempata a mesma matrícula em dois livros.

    Só lê. A área vem da régua na hora, e não do de-para da VIEW (ver o
    cabeçalho): é o CSV que não pode atrasar.
    """
    bd = banco(con)
    onde = _NO_MAPA
    parametros: list[Any] = []
    if isinstance(matriculas, (str, int)):
        # Uma só: `"4015"` percorrido letra a letra pediria as matrículas 4, 0…
        matriculas = [matriculas]
    if matriculas is not None:
        pedidas = sorted({str(x).strip() for x in matriculas
                          if x is not None and str(x).strip()})
        if not pedidas:
            return []
        onde += f" AND {_MATRICULA} = ANY(%s)"
        parametros.append(pedidas)
    linhas = bd.ler(
        f"""SELECT {_MATRICULA} AS matricula, {_CNS} AS cns,
                   {_PROPRIETARIOS} AS proprietario,
                   m.area_valor, m.area_unidade
              FROM ri_matriculas m
             WHERE {onde}
             ORDER BY substring(btrim(m.numero) FROM '^[0-9]+')::numeric NULLS LAST,
                      m.numero, m.complemento, m.id""",
        parametros or None)
    return [{"matricula": r["matricula"], "cns": r["cns"],
             "proprietario": r["proprietario"],
             "area_ha": area_em_hectares(r["area_valor"], r["area_unidade"])}
            for r in linhas]


def csv_do_mapa(linhas: Iterable[dict]) -> str:
    """O CSV para juntar à camada no QGIS, com os nomes de coluna do ONR."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=SEPARADOR_DO_CSV)
    escritor.writerow(COLUNAS_DO_ONR)
    for r in linhas:
        area = r.get("area_ha")
        escritor.writerow([r["matricula"], r["cns"], r["proprietario"],
                           "" if area is None else f"{area:.4f}"])
    return saida.getvalue()


# ---------------------------------------------------------------- a rota


def registrar_rotas(app, db, login_required, roles_required, audit) -> None:
    """Pendura o download do mapa no app já construído."""
    from flask import Response

    @app.route("/ri/mapa-onr.csv")
    @login_required
    @roles_required(*QUEM_BAIXA)
    def ri_mapa_onr_csv():
        """O CSV do mapa. Só lê: o de-para da VIEW é da subida, não daqui."""
        with db.connect() as con:
            linhas = dados_do_mapa(con)
        audit("RI_MAPA_ONR_EXPORTADO", "RI_MAPA_ONR", None,
              {"imoveis": len(linhas)})
        # O «﻿» é para o Excel abrir os acentos certos, como nos outros
        # CSV da casa.
        return Response("﻿" + csv_do_mapa(linhas),
                        mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition":
                                 "attachment; filename=mapa_onr.csv"})
