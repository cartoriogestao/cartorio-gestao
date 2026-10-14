"""Os modelos dos papéis que esta casa emite — um catálogo só, das seis atribuições.

O RELATO #28 DO OFICIAL:

    «preciso de mais controle sobre os modelos de todos os atos, de todas
     atribuições. preciso ter controle geral sobre os modelos, em especial os
     cabeçalhos padrão de cada atribuição e ato, corpo, encerramento, eventual
     notas de rodapé»

O QUE SE MEDIU EM 29/08/2026
    Havia **duas realidades** convivendo:

      · **Quatro** modelos do Registro de Imóveis — cabeçalho, ficha, certidão
        e nota devolutiva — já liam de tabela, caindo no padrão do código
        quando ela estivesse vazia. E `ri_modelos` está com **zero linhas**:
        todos os quatro saem do código hoje.

      · **Cinco** não liam de lugar nenhum: o **recibo**, o **orçamento** e a
        **recepção** do caixa, o **traslado** das notas e o **comprovante de
        prenotação** do RI. Para mudar uma vírgula neles era preciso mexer no
        programa.

    E `nt_modelos` tem **333 linhas** — mas aquilo é outra coisa: são as
    minutas das escrituras, o CORPO DO ATO, com os campos da CENSEC. Não são o
    papel que a casa imprime.

O DESENHO, E ELE É O QUE A CASA JÁ FAZIA
    **O código é o piso; a tabela é o ajuste.** Sem linha na tabela, vale o
    modelo escrito no programa — que é como os quatro do RI já funcionavam
    (`modelo["corpo"] if modelo else MODELO_CERTIDAO_PADRAO`).

    Isso dá três coisas de graça:

    1. **nada se perde** — o padrão não é apagável, porque não mora no banco;
    2. **«voltar ao padrão» é apagar a linha**, e não recadastrar um texto que
       ninguém tem mais;
    3. **instalação nova já nasce funcionando**, sem carga de modelos.

POR QUE UMA TABELA SÓ, E NÃO UMA POR MÓDULO
    O pedido é «controle geral». Espalhar por `ri_modelos`, `cx_modelos`,
    `nt_modelos_de_papel` daria quatro telas e a pergunta «onde eu mudo o
    cabeçalho?» continuaria sem resposta — que é o relato.

    `ri_modelos` continua sendo lida como legado: ela tem zero linhas nesta
    casa, mas uma instalação que já tivesse ajustado alguma coisa ali não pode
    perder o ajuste ao subir de versão.
"""
from __future__ import annotations

import sqlite3
from typing import Any

# ---------------------------------------------------------------- o catálogo
#
# CADA LINHA E UM PAPEL QUE SAI DESTA CASA, e a lista foi MEDIDA: sao as dez
# constantes `MODELO_*` que existem no codigo, achadas por varredura em
# 29/08/2026. Nao ha nenhuma aqui que eu tenha imaginado.
#
# `padrao` diz onde mora o texto de fabrica — modulo e nome —, e nao o texto:
# copiar o texto para ca faria duas versoes do mesmo modelo, e elas divergiriam
# no primeiro conserto. E o que se mostra na tela e o que o programa usa.
from modelos_papeis import CATALOGO  # noqa: E402 — catálogo por atribuição

# O `notas_selo.MODELO_PADRAO` FICOU DE FORA, e o motivo e a licao de sempre:
# **a mesma palavra em dois lugares nao quer dizer a mesma coisa**. Ele se
# chama `MODELO_`, mas nao e modelo de documento: e a URL que vai DENTRO do QR
# do selo — `https://selo.tjma.jus.br/#/resumo/{selo}`, o endereco da consulta
# daquele selo, medido no portal em 24/09/2026 —, com marcador do `str.format`
# e nao do Jinja.
#
# Posto neste catalogo, a tela o ofereceria como corpo de papel e a conferencia
# o passaria pelo Jinja, que e o motor errado: `{selo}` nao e sintaxe de Jinja,
# e a conferencia aprovaria um texto que o QR nao sabe montar. Ele ja tem
# lugar proprio na tela do selo.

POR_CHAVE: dict[str, dict] = {c["chave"]: c for c in CATALOGO}

# OS DOIS FORMATOS DE MARCADOR, e por que ha dois.
#
#   `JINJA` e o da casa inteira: `{{ a.numero }}`, com laco e condicao.
#   `CHAVES` e o do `str.format`: `{numero}`, sem logica nenhuma.
#
#   **Os termos do Registro Civil sao `CHAVES` de proposito.** Eles se montam
#   de frases inteiras que ja vem prontas — «, apresentou a DNV n.º 123» —, e
#   a decisao de a frase existir ou nao e do modulo, e nao do modelo: quem
#   escreve o termo nao deveria precisar de `{% if %}` para dizer que um
#   nascimento nao e de gemeos.
#
#   E o formato importa para a CONFERENCIA: passar um `{numero}` pelo Jinja
#   aprova um texto que o `str.format` nao sabe montar, e vice-versa. Foi o que
#   quase aconteceu com `notas_selo.MODELO_PADRAO`, que se chama modelo e e a
#   URL de dentro do QR.
JINJA = "JINJA"
# ---------------------------------------------------------------- tipagem
# Metadado ADITIVO (Fase 0/1 do plano de modelos). Não muda o piso nem o
# texto: só classifica o papel para a matriz, o inventário e a UI.
# Valores: TEXTO | MOLDE_ODT | MINUTA_ATO | DOC_AVULSO | MONTADO_POR_CAMPO
from modelos_papeis.tipagem import TIPOS_POR_CHAVE

for _entrada in CATALOGO:
    _tipo, _motivo = TIPOS_POR_CHAVE[_entrada["chave"]]
    _entrada["tipo"] = _tipo
    if _motivo:
        _entrada["motivo"] = _motivo


CHAVES = "CHAVES"


def formato_de(chave: str) -> str:
    """Em que formato aquele modelo escreve os claros. So calcula."""
    return _do_catalogo(chave).get("formato") or JINJA

# A tabela velha do RI. Ela tem ZERO linhas nesta casa, e continua sendo lida
# para que uma instalacao que ja tivesse ajustado alguma coisa ali nao perca o
# ajuste ao subir de versao. O de-para e so destes quatro, que sao os que ela
# conhecia.
LEGADO_RI: dict[str, str] = {
    "CABECALHO": "RI_CABECALHO",
    "FICHA": "RI_FICHA",
    "CERTIDAO": "RI_CERTIDAO",
    "NOTA": "RI_NOTA",
}


class ModeloError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


def _do_catalogo(chave: str) -> dict:
    c = POR_CHAVE.get(str(chave or "").upper())
    if not c:
        raise ModeloError(
            f"«{chave}» não é um papel que esta casa emita. Os que existem: "
            + ", ".join(f"{x['chave']} ({x['nome']})" for x in CATALOGO) + ".")
    return c


def marcador_do_miolo(chave: str) -> str:
    """O marcador que o molde daquele papel PRECISA carregar — ou ``""``.

    **UM PAPEL PODE SER UM MOLDE E UM MIOLO, E O `RI_CERTIDAO` E** — problema
    #75, 18/09/2026. O texto do tipo escolhido entra no molde onde o marcador
    manda, e essa emenda e a unica coisa que nao pode se perder: molde salvo sem
    ela sai com a abertura, a validade e a assinatura, e **sem o teor** — a
    certidao afirmando «cujo inteiro teor segue:» e nao reproduzindo nada.

    **QUEM DECIDE ISSO E O CATALOGO, e nao uma lista escrita aqui.** A declaracao
    `"miolo"` diz onde o marcador mora, e o texto vem LIDO de la, como o padrao:
    duas copias divergiriam no primeiro conserto, e este projeto ja pagou por
    isso com a `normalizar_nome`.
    """
    onde = _do_catalogo(chave).get("miolo")
    if not onde:
        return ""
    modulo, nome = onde
    import importlib
    return str(getattr(importlib.import_module(modulo), nome, "") or "")


def conferir_marcadores(chave: str, corpo: str) -> str:
    """O texto informado serve como molde daquele papel? Devolve o erro, ou ``""``.

    Chamada pelos DOIS lados que importam: a tela que grava (onde ha tempo de
    consertar) e a emissao (onde quem le o erro esta com o cliente na frente).
    Uma regra so, conferida com a mesma regua nos dois — conferir com uma e
    emitir com outra e como a tela passa a aprovar o que o papel nao sabe montar.
    """
    marcador = marcador_do_miolo(chave)
    if marcador and marcador not in str(corpo or ""):
        return (f"Este modelo é o MOLDE da certidão, e ele perdeu o ponto onde o "
                f"texto do tipo entra: falta `{marcador}`. Sem ele a certidão "
                "sairia com a abertura e a assinatura, e sem o teor. Reponha o "
                "marcador ou use «Voltar ao padrão».")
    return ""


def padrao_de(chave: str) -> str:
    """O texto de fabrica, lido do proprio modulo que o usa.

    LIDO, E NAO COPIADO. Guardar aqui uma copia do texto faria duas versoes do
    mesmo modelo, e elas divergiriam no primeiro conserto — e a tela passaria a
    mostrar uma coisa e o programa a imprimir outra. Este projeto ja pagou por
    isso com a `normalizar_nome`.
    """
    modulo, nome = _do_catalogo(chave)["padrao"]
    import importlib
    return str(getattr(importlib.import_module(modulo), nome, "") or "")


def corpo_gravado_ou_padrao(con: sqlite3.Connection, chave: str) -> str:
    """O ajuste GRAVADO daquele papel, ou o padrao do codigo. So le.

    E A REGRA QUE OS QUATRO MODELOS DO RI JA SEGUIAM, agora valendo para os
    quinze — `modelo["corpo"] if modelo else MODELO_CERTIDAO_PADRAO`. O codigo
    e o piso: **sem linha na tabela, o papel sai do jeito de fabrica**, e por
    isso nao ha como uma edicao ruim deixar a casa sem modelo nenhum.

    **ESTA FUNCAO ERA O `corpo_de` ATE 07/09/2026**, e mudou de nome por uma
    razao de recursao: `corpo_de` passou a COMPOR o documento pelos elementos
    (`modelos_elementos`), e o modulo dos elementos precisa deste piso aqui
    para montar o degrau de baixo. Se ele chamasse `corpo_de`, os dois se
    chamariam para sempre.
    """
    c = _do_catalogo(chave)
    con.row_factory = sqlite3.Row
    r = con.execute(
        """SELECT corpo FROM mo_modelos
            WHERE chave = ? AND COALESCE(ativo, 1) = 1
              AND COALESCE(corpo, '') <> ''""", (c["chave"],)).fetchone()
    if r:
        return str(r["corpo"])

    # O LEGADO DO RI, para nao perder ajuste de quem ja tinha um.
    velho = next((k for k, v in LEGADO_RI.items() if v == c["chave"]), None)
    if velho:
        try:
            r = con.execute(
                """SELECT corpo FROM ri_modelos
                    WHERE tipo = ? AND ativo = 1
                      AND COALESCE(corpo, '') <> ''
                    ORDER BY id LIMIT 1""", (velho,)).fetchone()
        except sqlite3.OperationalError:
            r = None                      # instalacao sem a tabela antiga
        if r:
            return str(r["corpo"])

    return padrao_de(c["chave"])


def corpo_de(con: sqlite3.Connection, chave: str) -> str:
    """O papel INTEIRO que vale hoje — corpo, encerramento e rodape. So le.

    **OS TREZE SITIOS QUE EMITEM PAPEL CHAMAM ESTA FUNCAO**, no RI, no caixa,
    nas notas, no termo do civil e no protesto. Ela mudou de conteudo em
    07/09/2026 e **nao mudou de nome nem de assinatura**, de proposito: assim os
    treze ganham o encerramento e o rodape sem que nenhum deles seja editado —
    e edicao em treze lugares e treze chances de errar um.

    **E NO DIA DA SUBIDA ELA DEVOLVE EXATAMENTE O QUE DEVOLVIA NA VESPERA**,
    porque o encerramento e o rodape nascem vazios e parte vazia nao entra na
    juncao. Era a condicao do oficial: «manter a forma e diminuir o risco de ir
    errado».

    **QUEM EDITA NAO CHAMA ESTA**, e sim `modelos_elementos.corpo_do_ato`:
    mostrar o documento composto na caixa de edicao faria o escrevente gravar o
    fecho DENTRO do corpo, e o fecho sairia duas vezes no papel seguinte.
    """
    c = _do_catalogo(chave)
    try:
        import modelos_elementos as ELEM
        return ELEM.montar_documento(con, c["chave"])
    except Exception:                                        # noqa: BLE001
        # **O PISO NAO PODE DEPENDER DO ANDAR DE CIMA.** Se a tabela dos
        # elementos ainda nao existir — instalacao a meio de migrar —, o papel
        # continua saindo. Um documento que nao sai e pior que um documento sem
        # o fecho novo.
        return corpo_gravado_ou_padrao(con, c["chave"])


def esta_ajustado(con: sqlite3.Connection, chave: str) -> bool:
    """Se a casa mexeu neste modelo. So calcula.

    A TELA PRECISA DIZER ISSO, porque «igual ao padrao» e «ajustado pela casa»
    parecem a mesma coisa quando o texto e o mesmo — e sao diferentes no dia em
    que o padrao mudar numa versao nova: o ajustado NAO acompanha.
    """
    c = _do_catalogo(chave)
    con.row_factory = sqlite3.Row
    return con.execute(
        """SELECT 1 FROM mo_modelos
            WHERE chave = ? AND COALESCE(corpo, '') <> ''""",
        (c["chave"],)).fetchone() is not None


def salvar(con: sqlite3.Connection, chave: str, *, corpo: str,
           quem: str | None, agora: str) -> None:
    """Guarda o ajuste da casa para aquele papel.

    O CORPO VAZIO NAO SE GRAVA — ele volta ao padrao. Guardar vazio faria a
    casa imprimir folha em branco, e folha em branco assinada e pior que
    modelo feio.
    """
    c = _do_catalogo(chave)
    limpo = (corpo or "").strip()
    if not limpo:
        restaurar(con, chave)
        return
    con.execute(
        """INSERT INTO mo_modelos (chave, corpo, ativo, atualizado_em,
               atualizado_por)
           VALUES (?,?,1,?,?)
           ON CONFLICT(chave) DO UPDATE SET
               corpo = excluded.corpo, ativo = 1,
               atualizado_em = excluded.atualizado_em,
               atualizado_por = excluded.atualizado_por""",
        (c["chave"], limpo, agora, quem))


def restaurar(con: sqlite3.Connection, chave: str) -> bool:
    """Joga fora o ajuste e volta ao padrao do codigo. Devolve se havia ajuste.

    E POR ISSO QUE O PADRAO NAO MORA NO BANCO: voltar atras e apagar uma linha,
    e nao recadastrar um texto que ninguem tem mais guardado.
    """
    c = _do_catalogo(chave)
    cur = con.execute("DELETE FROM mo_modelos WHERE chave = ?", (c["chave"],))
    return cur.rowcount > 0


def conferir(corpo: str, contexto: dict[str, Any]) -> str | None:
    """Tenta montar o modelo com um contexto de exemplo. Devolve o erro, ou None.

    MODELO QUEBRADO NAO PODE APARECER NA HORA DO ATO. Sem esta conferencia, o
    erro de chave surge quando o escrevente clica em «emitir certidao» com o
    cliente na frente — e o ato ja esta lavrado. Aqui ele aparece na tela de
    quem edita, que e onde da para consertar.

    Roda no MESMO ambiente restrito do resto da casa (`SandboxedEnvironment`):
    conferir num ambiente mais solto aprovaria modelo que a hora do ato recusa.
    """
    from jinja2.sandbox import SandboxedEnvironment
    try:
        SandboxedEnvironment(autoescape=False).from_string(
            corpo or "").render(**contexto)
    except Exception as erro:                      # noqa: BLE001 — e o recado
        return f"{type(erro).__name__}: {erro}"
    return None


def por_atribuicao() -> list[tuple[str, list[dict]]]:
    """O catalogo agrupado, na ordem em que a tela mostra.

    A ORDEM E A DO CATALOGO, e nao alfabetica: ela poe o Registro de Imoveis
    primeiro porque e onde estao cinco dos dez papeis, e alfabetica poria
    «Caixa» na frente sem que isso ajudasse ninguem a achar.
    """
    grupos: list[tuple[str, list[dict]]] = []
    for c in CATALOGO:
        if not grupos or grupos[-1][0] != c["atribuicao"]:
            grupos.append((c["atribuicao"], []))
        grupos[-1][1].append(c)
    return grupos
