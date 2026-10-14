"""
A certidao de inteiro teor do RCPJ, do RTD e do Livro 3.

UM MODULO PARA AS DUAS ATRIBUICOES, e nao um para cada
    As duas certidoes tem a mesma forma: achar o registro, reproduzir o teor
    que esta no livro, numerar por exercicio, congelar e assinar. O que muda e
    a FRASE DE ABERTURA — e ela e a unica coisa que `PAINEIS` guarda. Escrever
    duas vezes daria duas versoes divergentes do papel que sai da casa.

OS TEXTOS SAO OS DA CASA
    Medidos em 25/08/2026 nas certidoes que o E-Oficio guardou:

    - `tbTD_Certidao`, 38 com teor (25 do RCPJ, 14 do RTD): 34 comecam com
      "CERTIFICO E DOU FE", e as 38 tem "COM O SEGUINTE TEOR" e "Para
      conhecimento de terceiros e sua conservacao".
    - `LivroAuxiliarCertidao`, 6 com teor: "CERTIFICO E DOU FE, que revendo os
      livros proprios desta Serventia Imobiliaria, a pedido de parte
      interessado encontrei no Livro 3 Auxiliar de Registro Geral de Imoveis,
      no registro n.NNNN o seguinte:-".

    O cabecalho da serventia — Republica Federativa do Brasil, comarca,
    endereco, oficial — NAO entra no teor: quem o escreve e o `.odt`, uma vez
    so, como ja faz nos termos dos livros e no recibo do caixa.

SEM TEOR NAO HA CERTIDAO DE INTEIRO TEOR
    24 dos 72 registros do RCPJ/RTD e 2 dos 14 do Livro 3 vieram do acervo sem
    o texto. Certidao de inteiro teor sem o teor seria papel que promete o que
    nao entrega — o modulo recusa dizendo que o registro EXISTE no livro e que
    a copia se tira do livro fisico. E a mesma resposta que o Registro de
    Imoveis ja da nas certidoes importadas sem corpo.

O TEOR CONGELA NA EMISSAO
    Depois de emitida, a certidao nao se recalcula, e traz o sha256. Averbacao
    lavrada amanha nao muda a certidao de hoje — mudar seria reescrever o que a
    serventia ja afirmou, e a via do cliente ficaria diferente da do banco.

    Por isso a certidao DIZ QUANTOS ATOS existiam quando saiu: quem confere
    depois sabe se o registro andou.

O RCPN NAO ESTA AQUI, E ISSO E DECISAO DO OFICIAL
    Medido em 25/08/2026: os 244 assentos do acervo NAO TEM TEOR NENHUM —
    `memTexto`, `memTextoInteiroTeor` e `memInteiroTeorFormatado` estao vazias
    nas tres tabelas de origem, todas. O E-Oficio montava a certidao dos
    CAMPOS, no modelo nacional do CNJ. O oficial decidiu, em 25/08/2026, fechar
    primeiro estas duas e deixar o RCPN para uma passada propria — e por isso
    `PAINEIS` tem duas entradas e nao tres.

FUNDAMENTO
    Lei 6.015/1973, arts. 16 a 21 (certidao), 114 a 148 (RCPJ), 127 a 130 (RTD)
    e 178 (Registro Auxiliar).
"""
from __future__ import annotations
from certidao_texto import sem_linha_de_assinatura_a_mao

import hashlib
import sqlite3
from typing import Any, Sequence, Sequence

import cancelamento_certidao as CANC
import livro_nucleo as LN

SCHEMA = """
-- A certidao das atribuicoes que nao sao Protesto nem Registro de Imoveis.
--
-- Uma tabela para as duas, porque a forma e a mesma; o que muda e a frase de
-- abertura, e ela mora no codigo. `atribuicao` diz de quem e a certidao.
--
-- A NUMERACAO E POR ATRIBUICAO E POR EXERCICIO, como no acervo, que tinha uma
-- tabela de certidoes por atribuicao — `tbTD_Certidao` e
-- `LivroAuxiliarCertidao` numeravam cada uma a sua.
CREATE TABLE IF NOT EXISTS at_certidoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atribuicao TEXT NOT NULL,               -- RCPJ_RTD | LIVRO3
    numero INTEGER NOT NULL,
    ano INTEGER NOT NULL,

    tabela TEXT NOT NULL,                   -- rg_registros | ra_registros
    registro_id INTEGER NOT NULL,
    registro_numero TEXT,                   -- como sai impresso

    requerente TEXT,
    finalidade TEXT,

    atos INTEGER NOT NULL DEFAULT 0,        -- quantos o registro tinha ao sair
    atos_ids TEXT,                          -- JSON ids dos atos incluídos (opcional)
    teor TEXT NOT NULL,                     -- congelado na emissao
    hash_certidao TEXT,

    selo TEXT,
    lancamento_id INTEGER,                  -- as custas, no caixa

    cancelada INTEGER NOT NULL DEFAULT 0,
    motivo_cancelamento TEXT,
    cancelada_em TEXT,
    cancelada_por TEXT,
    declaracao_selo_tjma_em TEXT,
    declaracao_selo_tjma_por TEXT,

    emitida_em TEXT NOT NULL,
    emitida_por TEXT,
    UNIQUE(atribuicao, numero, ano)
);

CREATE INDEX IF NOT EXISTS ix_at_certidoes_registro
    ON at_certidoes(tabela, registro_id);
"""


class CertidaoError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcao."""


# O que muda de uma atribuicao para a outra. E a unica coisa que muda.
PAINEIS: dict[str, dict] = {
    "RCPJ_RTD": {
        "nome": "RCPJ / RTD",
        "tabela": "rg_registros",
        "atos": "rg_atos",
        "rota_ficha": "rcpj_rtd_registro",
    },
    "LIVRO3": {
        "nome": "Registro Auxiliar — Livro 3",
        "tabela": "ra_registros",
        "atos": "ra_atos",
        "rota_ficha": "livro3_registro",
    },
}


def painel(atribuicao: str) -> dict:
    """O painel da atribuicao, ou erro de balcao."""
    chave = str(atribuicao or "").strip().upper()
    if chave not in PAINEIS:
        raise CertidaoError(
            f"Atribuição desconhecida para certidão: {atribuicao!r}. As que "
            f"existem são: {', '.join(PAINEIS)}.")
    return {**PAINEIS[chave], "chave": chave}


# --------------------------------------------------------------- utilidades


def _dia(data: Any) -> str:
    """`2022-01-31` -> `31/01/2022`. E como as certidoes do acervo escrevem."""
    s = str(data or "")[:10]
    if len(s) == 10 and s[4] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}"
    return s


# COMO O ACERVO CHAMA CADA REGISTRO na certidao. Medido nas 38 de
# `tbTD_Certidao`: `no Livro "A-5" de Registro de Pessoas Juridicas`.
#
# NAO se usa `livro_nucleo.SERIES[...].nome` aqui: aquele e o nome do LIVRO
# ("Livro A do Registro Civil das Pessoas Juridicas"), e sai duplicado —
# `no Livro "A-4" de Livro A do Registro Civil...`. A certidao nomeia o
# REGISTRO, e o livro ela ja disse entre aspas.
NOME_DO_REGISTRO: dict[int, str] = {
    3: "Registro de Pessoas Jurídicas",
    4: "Registro de Títulos e Documentos",
}

# Estes eram textos presos dentro de ``montar_teor``. São constantes porque o
# catálogo de modelos lê o padrão no próprio módulo que efetivamente o usa.
MODELO_CERTIDAO_RCPJ_RTD = (
    "CERTIFICO E DOU FÉ, que revendo os livros próprios desta Serventia "
    "{onde}, encontrei o seguinte registro{natureza}. Para conhecimento de "
    "terceiros e sua conservação: COM O SEGUINTE TEOR: -\n\n{teor}"
)
# **QUANDO O QUE SE CERTIFICA É A AVERBAÇÃO, E NÃO O REGISTRO** — pedido do
# oficial em 11/09/2026: «apesar de ter escolhido duas averbações para
# constar na certidão, foi erroneamente como objeto o registro da
# assembleia de constituição». O modelo de cima sempre afirma «encontrei o
# seguinte registro», mesmo quando o operador desmarcou o registro-base e
# só quer certificar averbações específicas — a certidão dizia o que NÃO
# tinha sido pedido. Este modelo nomeia o registro só como referência (o
# «ao qual constam») e o objeto certificado passa a ser, de fato, as
# averbações escolhidas.
MODELO_CERTIDAO_RCPJ_RTD_SO_AVERBACOES = (
    "CERTIFICO E DOU FÉ, que revendo os livros próprios desta Serventia "
    "{onde}, ao qual constam as seguintes averbações, as quais ora "
    "certifico. Para conhecimento de terceiros e sua conservação: COM O "
    "SEGUINTE TEOR: -\n\n{teor}"
)
# **O `{atos}` ENTROU EM 21/09/2026, E ELE CONSERTA UMA CERTIDÃO QUE OMITIA.**
#
#   Até aqui o teor da certidão do Livro 3 era o do REGISTRO e mais nada: as
#   averbações não entravam — **e a tela oferecia escolhê-las** (o quadro da
#   certidão recebe `atos=atos`). O operador marcava a averbação e ela era
#   ignorada em silêncio.
#
#   O QUE ISSO PRODUZ É O PIOR PAPEL QUE ESTA CASA PODE PÔR NO MUNDO: uma
#   certidão do registro 1.243 sairia reproduzindo a cédula **sem dizer que
#   ela foi integralmente cancelada** pela AV-01. Quem a lesse concluiria que
#   a garantia está de pé.
#
#   O claro novo é **aditivo**: quem já tiver ajustado este modelo no catálogo
#   continua com o texto dele — o preenchimento não estoura por chave a mais —
#   e a tela de modelos mostra o `{atos}` para ele acrescentar quando quiser.
MODELO_CERTIDAO_LIVRO3 = (
    "CERTIFICO E DOU FÉ, que revendo os livros próprios desta Serventia "
    "Imobiliária, a pedido de parte interessada encontrei no Livro 3 "
    "Auxiliar de Registro Geral de Imóveis, no registro n.{numero} o "
    "seguinte:-\n\n"
    "NATUREZA: {natureza}\n"
    "SITUAÇÃO: {situacao}\n\n"
    "TÍTULO: {titulo_tipo}, nº {titulo_numero}\n"
    "PRENOTAÇÃO: {prenotacao}\n"
    "VALOR: {valor}\n\n"
    "PARTES:\n{partes}\n\n"
    "TEOR DO REGISTRO:\n{teor}\n\n"
    "ATOS POSTERIORES AO REGISTRO:\n{atos}"
)


def _bloco_atos_certidao_livro3(atos: list,
                                ids_filtro: set | None) -> str:
    """Trecho `{atos}` da certidão do Livro 3 — só averbações com conteúdo."""
    linhas = []
    for a in atos:
        if str(a.get("tipo") or "").upper() == "R":
            continue
        if ids_filtro is not None and int(a.get("id")) not in ids_filtro:
            continue
        corpo = (str(a.get("teor") or "").strip()
                 or str(a.get("motivo_cancelamento") or "").strip())
        if not corpo:
            continue
        rotulo = f"{a.get('tipo')}-{a.get('numero')}"
        data = _dia(a.get("data_ato"))
        cabeca = f"{rotulo} — {data}:-" if data else f"{rotulo}:-"
        linhas.append(f"\n{cabeca}\n{corpo}")
    return "\n".join(linhas) if linhas else "  (nenhum ato posterior informado)"


def claros_certidao_livro3(*, reg: dict, atos: list, teor: str,
                           partes: list | None = None,
                           ids_filtro: set | None = None) -> dict:
    """Claros do modelo `RI_LIVRO3_CERTIDAO` — emissão e prévia usam o mesmo mapa."""
    import ra_ficha_odt as FICHA

    base = FICHA.contexto(
        registro=reg,
        atos=atos,
        partes=partes or [],
        serventia={},
        impresso_em="",
    )
    return {
        "numero": base["numero"] or str(reg.get("numero") or ""),
        "natureza": base["natureza"],
        "situacao": base["situacao"],
        "titulo_tipo": base["titulo_tipo"],
        "titulo_numero": base["titulo_numero"],
        "prenotacao": base["prenotacao"],
        "valor": base["valor"],
        "partes": base["partes"],
        "teor": (teor or "").strip() or base["teor"],
        "atos": _bloco_atos_certidao_livro3(atos, ids_filtro),
    }


def _teor_do_livro3(modelo: str, reg: dict, atos: list, teor: str,
                    ids_filtro: set | None,
                    partes: list | None = None) -> str:
    """O teor da certidão do Livro 3, **com as averbações dentro**. Só monta.

    **AS QUE O OPERADOR MARCOU; SEM MARCAÇÃO, TODAS.** Certidão que cala uma
    averbação por omissão de clique é o mesmo defeito que ela veio consertar.

    **O ATO DE REGISTRO NÃO SE REPETE AQUI**: o corpo dele já é o teor lá em
    cima, e imprimi-lo duas vezes faria a certidão parecer ter dois registros.

    **AVERBAÇÃO SEM TEOR NÃO VIRA LINHA EM BRANCO** — ela sai com o motivo do
    cancelamento, que é o que o cancelamento escreve; e se não houver nem um
    nem outro, ela não entra, porque um rótulo sozinho não certifica nada.
    """
    claros = claros_certidao_livro3(
        reg=reg, atos=atos, teor=teor, partes=partes, ids_filtro=ids_filtro)
    try:
        return modelo.format(**claros)
    except (KeyError, ValueError) as erro:
        raise CertidaoError(
            f"O modelo da certidão do Livro 3 está incompleto: {erro}."
        ) from erro


def cabeca_do_ato(ato: dict) -> tuple[str, ...]:
    """As formas como `_teor_do_livro3` escreve o rótulo daquele ato. Só calcula.

    É a mesma regra que MONTA o teor, lida ao contrário: com data sai
    «AV-1 — 22/09/2026:-», sem data sai «AV-1:-». Escrever a forma aqui de novo,
    à mão, faria o papel deixar de achar o ato no dia em que o rótulo mudasse.
    """
    rotulo = f"{ato.get('tipo')}-{ato.get('numero')}"
    return (f"{rotulo} — ", f"{rotulo}:-")


def blocos_por_ato(teor: str, atos: Sequence[dict],
                   ato_ids: Sequence[int] | None = None) -> list[tuple]:
    """O teor da certidão do Livro 3 partido ATO A ATO. SÓ LÊ — não muda texto.

    Devolve `[(trecho, ato_ou_None), ...]` na ordem do texto, e a junção dos
    trechos é **o teor inteiro, letra por letra** — há teste que confere. Serve
    para o papel pôr **o selo de cada averbação logo abaixo dela**, que é como
    a certidão do Livro 2 sempre fez (`MIOLO_CERTIDAO_INTEIRO_TEOR`: o teor do
    ato e, em seguida, o selo do ato).

    **POR QUE NA IMPRESSÃO, E NÃO NO TEOR** — 23/09/2026, relato do oficial:
    «e falta o selo na averbação». O teor é **congelado** com sha256 na
    emissão; pôr o selo dentro dele mudaria a impressão digital das que já
    saíram. Desenhado no papel, a certidão 1/2026 ganha o selo da AV-1 **sem
    uma letra do teor mudar** — é o precedente das linhas entre os atos, que o
    Livro 2 desenha ao imprimir pelo mesmo motivo.

    **O QUE NÃO SE ACHA NÃO SE INVENTA**: ato cujo rótulo não está no teor
    (certidão do acervo, montada por outro sistema) não ganha trecho — o papel
    sai como sempre saiu, sem um selo pendurado no lugar errado.
    """
    filtro = {int(x) for x in ato_ids} if ato_ids else None
    marcos = []
    for a in atos:
        if str(a.get("tipo") or "").upper() == "R":
            continue
        if filtro is not None and int(a.get("id") or 0) not in filtro:
            continue
        for forma in cabeca_do_ato(a):
            achado = teor.find("\n" + forma)
            if achado >= 0:
                marcos.append((achado + 1, a))
                break
    if not marcos:
        return [(teor, None)]
    marcos.sort(key=lambda x: x[0])
    # A FRASE DO REGISTRO CANCELADO VEM DEPOIS DOS ATOS (`emitir` a acrescenta),
    # e ela não é do último ato: fica num trecho seu, sem selo.
    cauda = teor.find("\n\nCERTIFICO ainda que o referido registro",
                      marcos[-1][0])
    fim = cauda if cauda >= 0 else len(teor)
    blocos = [(teor[:marcos[0][0]], None)]
    for i, (inicio, ato) in enumerate(marcos):
        proximo = marcos[i + 1][0] if i + 1 < len(marcos) else fim
        blocos.append((teor[inicio:proximo], ato))
    if fim < len(teor):
        blocos.append((teor[fim:], None))
    return blocos


def _livro_impresso(serie: str | None, volume: str | None) -> str:
    """`PJ_A` + `05` -> `A-5`. Sem volume, so a letra.

    E como as 38 certidoes do acervo escrevem — `Livro "A-5"`. O acervo guarda
    o volume com zero a esquerda ('05', '04'); a certidao antiga imprime sem.
    """
    letra = (serie or "").split("_")[-1] or "?"
    v = str(volume or "").strip().lstrip("0")
    return f"{letra}-{v}" if v else letra


# ---------------------------------------------------------------- consultas


def registro(con: sqlite3.Connection, atribuicao: str,
             registro_id: int) -> dict | None:
    """O registro e os atos dele, para a certidao. So LE."""
    p = painel(atribuicao)
    linha = con.execute(f"SELECT * FROM {p['tabela']} WHERE id=?",
                        (int(registro_id),)).fetchone()
    if not linha:
        return None
    atos = [dict(r) for r in con.execute(
        f"SELECT * FROM {p['atos']} WHERE registro_id=? ORDER BY id",
        (int(registro_id),))]
    out: dict = {"painel": p, "registro": dict(linha), "atos": atos}
    if p["chave"] == "LIVRO3":
        out["partes"] = [dict(r) for r in con.execute(
            "SELECT * FROM ra_partes WHERE registro_id=? ORDER BY id",
            (int(registro_id),))]
    return out


def certidao(con: sqlite3.Connection, certidao_id: int) -> sqlite3.Row | None:
    """A certidao, como foi emitida. So LE."""
    return con.execute("SELECT * FROM at_certidoes WHERE id=?",
                       (int(certidao_id),)).fetchone()


def listar(con: sqlite3.Connection, *, atribuicao: str | None = None,
           termo: str = "", limite: int = 100) -> list[sqlite3.Row]:
    """As certidoes emitidas, da mais nova para a mais velha. So LE."""
    onde, params = [], []
    if atribuicao:
        onde.append("atribuicao = ?")
        params.append(painel(atribuicao)["chave"])
    t = (termo or "").strip()
    if t:
        onde.append("(registro_numero LIKE ? OR requerente LIKE ? "
                    "OR CAST(numero AS TEXT) = ?)")
        params += [f"%{t}%", f"%{t}%", t]
    filtro = (" WHERE " + " AND ".join(onde)) if onde else ""
    return list(con.execute(
        f"""SELECT * FROM at_certidoes{filtro}
             ORDER BY ano DESC, numero DESC LIMIT ?""",
        (*params, int(limite))))


def proximo_numero(con: sqlite3.Connection, atribuicao: str, ano: int) -> int:
    """O proximo numero do exercicio, naquela atribuicao. So LE.

    GET nao abre transacao de escrita: a tela de conferencia chama isto, e
    contador consumido num GET fica preso no `busy_timeout`.
    """
    linha = con.execute(
        """SELECT MAX(numero) n FROM at_certidoes
            WHERE atribuicao=? AND ano=?""",
        (painel(atribuicao)["chave"], int(ano))).fetchone()
    return int(linha["n"] if linha and linha["n"] else 0) + 1


# ------------------------------------------------------------------ o teor


def eh_so_averbacoes(atribuicao: str, dados: dict,
                     ato_ids: Sequence[int] | None) -> bool:
    """O REGISTRO foi desmarcado, e só averbações restaram? Só LÊ.

    Usada em dois lugares que precisam da MESMA resposta: `montar_teor`
    (para trocar a frase de abertura e não incluir o corpo do registro) e
    `emitir` (para saber que não pode usar o modelo padrão do catálogo —
    ver o comentário lá). Duas contas divergentes da mesma pergunta
    seriam a certidão dizendo uma coisa e escolhendo o modelo de outra.
    """
    p = painel(atribuicao)
    if p["chave"] != "RCPJ_RTD" or ato_ids is None:
        return False
    registro_ato = next(
        (a for a in dados["atos"] if a.get("tipo") == "REGISTRO"), None)
    if registro_ato is None:
        return False
    ids_filtro = {int(x) for x in ato_ids}
    return int(registro_ato["id"]) not in ids_filtro


def montar_teor(atribuicao: str, dados: dict, *, modelo: str | None = None,
                 ato_ids: Sequence[int] | None = None) -> str:
    """O teor da certidao, nas palavras que esta casa usa.

    Nao le banco e nao grava nada: recebe o que `registro()` devolveu.
    """
    p = painel(atribuicao)
    reg, atos = dados["registro"], dados["atos"]
    registro_ato = next((a for a in atos if a.get("tipo") == "REGISTRO"), None)
    ids_filtro = {int(x) for x in ato_ids} if ato_ids is not None else None

    # **O OBJETO CERTIFICADO É O QUE FOI MARCADO, E NÃO SEMPRE O REGISTRO**
    # — pedido do oficial em 11/09/2026: «apesar de ter escolhido duas
    # averbações para constar na certidão, foi erroneamente como objeto o
    # registro da assembleia de constituição». Se o operador desmarcou o
    # próprio ato de REGISTRO (só quer as averbações), a certidão não pode
    # continuar afirmando «encontrei o seguinte registro» com o corpo dele
    # — o objeto agora é a(s) averbação(ões) escolhida(s).
    so_averbacoes = eh_so_averbacoes(atribuicao, dados, ato_ids)

    teor = ""
    if not so_averbacoes:
        teor = (reg.get("teor") or "").strip()
        if not teor:
            # Se o REGISTRO nao tem teor, o ato de registro pode ter: no
            # RCPJ/RTD a carga poe o inteiro teor nos dois.
            teor = next((str(a.get("teor") or "").strip() for a in atos
                        if str(a.get("teor") or "").strip()), "")
        if not teor:
            raise CertidaoError(
                f"O registro n. {reg.get('numero')} existe no livro, mas o "
                f"acervo do E-Ofício não trouxe o teor dele — e certidão de "
                f"inteiro teor sem o teor seria papel que promete o que não "
                f"entrega. A cópia se tira do livro físico.")

    if p["chave"] == "LIVRO3":
        # **AS AVERBAÇÕES ENTRAM NO TEOR — 21/09/2026.** Ver o comentário do
        # modelo: até aqui elas eram ignoradas em silêncio, e uma certidão do
        # registro 1.243 sairia sem dizer que ele foi cancelado.
        return _teor_do_livro3(modelo or MODELO_CERTIDAO_LIVRO3, reg, atos,
                               teor, ids_filtro,
                               partes=dados.get("partes"))

    # RCPJ / RTD
    serie = reg.get("serie")
    atribuicao_numero = (LN.serie(serie).atribuicao if serie in LN.SERIES
                         else reg.get("atribuicao"))
    nome_registro = NOME_DO_REGISTRO.get(atribuicao_numero, "Registro")
    onde = (f'no Livro "{_livro_impresso(serie, reg.get("volume"))}" '
            f'de {nome_registro}')
    if registro_ato and registro_ato.get("folha"):
        onde += f", fls. {registro_ato['folha']}"
    if reg.get("numero"):
        onde += f", ATO n. {reg['numero']}"
    if registro_ato and registro_ato.get("data_ato"):
        onde += f" datada de {_dia(registro_ato['data_ato'])}"
    natureza = (reg.get("natureza") or "").strip()
    # Averbações posteriores ao registro entram no teor textual — o oficial
    # precisa vê-las na certidão depois de averbar (11/09/2026). Só o que
    # já está em rg_atos; não se inventa conteúdo.
    blocos_av = []
    for a in atos:
        if str(a.get("tipo") or "").upper() != "AVERBACAO":
            continue
        if ids_filtro is not None and int(a["id"]) not in ids_filtro:
            continue
        teor_av = (a.get("teor") or "").strip()
        if not teor_av:
            continue
        ordem = a.get("numero_ordem") or a.get("rotulo") or ""
        blocos_av.append(
            f"--- AVERBAÇÃO n. {ordem} ---\n{teor_av}")

    if so_averbacoes:
        if not blocos_av:
            raise CertidaoError(
                "Nenhuma averbação com teor foi selecionada para esta "
                "certidão, e o registro-base também não foi marcado — "
                "marque ao menos um ato com conteúdo para certificar.")
        teor_final = "\n\n".join(blocos_av)
        # **`modelo` NÃO SE USA AQUI** — achado do oficial em 12/09/2026:
        # a certidão continuava dizendo «encontrei o seguinte registro»
        # mesmo com o registro desmarcado. A causa: `mo_modelos` está
        # vazio (nenhum ajuste salvo), e o catálogo (`modelos_da_casa`)
        # devolve, como PISO, o texto de `MODELO_CERTIDAO_RCPJ_RTD` — o
        # modelo de SEMPRE, não o de só-averbações, porque ainda não há
        # uma chave própria no catálogo para este caso. `modelo` chegava
        # aqui sempre preenchido com o texto errado, e `modelo or ...`
        # nunca chegava a usar o padrão certo. `emitir()` já evita passar
        # `modelo` neste caso (não busca no catálogo); esta linha é a
        # segunda trava, para quem chamar `montar_teor` direto.
        try:
            return MODELO_CERTIDAO_RCPJ_RTD_SO_AVERBACOES.format(
                onde=onde, natureza=(", " + natureza if natureza else ""),
                teor=teor_final, numero=reg.get("numero") or "")
        except (KeyError, ValueError) as erro:
            raise CertidaoError(f"O modelo da certidão de averbação está incompleto: {erro}.") from erro

    if blocos_av:
        teor = teor.rstrip() + "\n\n" + "\n\n".join(blocos_av)
    try:
        return (modelo or MODELO_CERTIDAO_RCPJ_RTD).format(
            onde=onde, natureza=(", " + natureza if natureza else ""),
            teor=teor, numero=reg.get("numero") or "")
    except (KeyError, ValueError) as erro:
        raise CertidaoError(f"O modelo da certidão de inteiro teor está incompleto: {erro}.") from erro


def teor_traz_cabecalho(teor: str | None) -> bool:
    """O teor ja comeca com o cabecalho da serventia?

    O E-OFICIO GUARDAVA A PAGINA INTEIRA. `memInteiroTeorSemFormatacao` nao e
    so o registro: e a folha como saia impressa, com "REPUBLICA FEDERATIVA DO
    BRASIL", a comarca, o endereco e o nome do oficial no alto.

    Quem imprime decide o que fazer com isso: se o teor ja traz cabecalho, o
    `.odt` NAO poe o dele em cima — sairiam dois. E nao se corta nada do teor:
    texto de certidao nao se edita, so se decide onde ele entra na folha.
    """
    # Procura no TEXTO INTEIRO, e nao so no comeco: o cabecalho antigo fica
    # dentro do teor do registro, que na certidao ja vem depois da frase de
    # abertura. E exige as DUAS marcas — so "Republica Federativa do Brasil"
    # apareceria num registro que a cite por outro motivo.
    todo = " ".join(str(teor or "").split()).upper()
    tem_brasao = ("REPÚBLICA FEDERATIVA DO BRASIL" in todo
                  or "REPUBLICA FEDERATIVA DO BRASIL" in todo)
    return tem_brasao and "SERVENTIA EXTRAJUDICIAL" in todo


def hash_certidao(atribuicao: str, numero: int, ano: int, teor: str,
                  emitida_em: str) -> str:
    """Impressao digital da certidao, para provar que a segunda via e a mesma."""
    bruto = f"{atribuicao}|{numero}|{ano}|{emitida_em}|{teor}"
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- emitir


def validade_de(hoje: str) -> str:
    """Até quando esta certidão vale. **Trinta dias, e o prazo é da norma.**

    Art. 53 do Código de Normas da CGJ/TJMA. O Livro 2 grava isto desde
    sempre; a certidão daqui saía **sem prazo nenhum** — e prazo que não está
    escrito é prazo que ninguém confere. O número é lido de `ri_schema`, e não
    repetido aqui: duas cópias de um prazo divergem no dia em que a norma
    mudar, e a casa passaria a prometer dois prazos diferentes.
    """
    from datetime import date, timedelta

    from ri_schema import VALIDADE_CERTIDAO_DIAS
    try:
        dia = date.fromisoformat(str(hoje)[:10])
    except ValueError:
        return ""
    return (dia + timedelta(days=VALIDADE_CERTIDAO_DIAS)).isoformat()


FONTES_DO_CORPO = ("TEXTO", "DIGITALIZACAO")

_MARCADORES_TEOR_CERTIDAO_LIVRO3 = (
    "NATUREZA:",
    "TEOR DO REGISTRO:",
    "ATOS POSTERIORES AO REGISTRO:",
    "PARTES:",
)


def modelo_certidao_livro3(con: sqlite3.Connection) -> str:
    """Molde `RI_LIVRO3_CERTIDAO` — mesma junção de partes da prévia ao vivo."""
    import modelos_elementos as ELEM
    import modelos_previa as PREVIA

    partes = ELEM.partes_do_documento(con, "RI_LIVRO3_CERTIDAO")
    return PREVIA.montar(partes)


def certidao_livro3_teor_precisa_modelo_novo(teor: str | None) -> bool:
    """Certidão por texto gravada antes do molde completo de 3.6.227? Só lê."""
    t = (teor or "").strip()
    if not t:
        return True
    if "REPRODUÇÃO" in t.upper():
        return False
    return not all(m in t for m in _MARCADORES_TEOR_CERTIDAO_LIVRO3)


def remontar_teor_certidao_livro3(con: sqlite3.Connection, certidao_id: int,
                                  *, agora: str | None = None) -> dict:
    """Recalcula o teor congelado da certidão L3 pelo molde vigente. ESCREVE.

    Usado na emissão corrigida e no ensaio sandbox quando a certidão antiga
    ficou só com o texto cru do registro. Mantém número, ano e `emitida_em`
    para o hash continuar identificando a mesma via.
    """
    linha = certidao(con, certidao_id)
    if not linha:
        raise CertidaoError("Certidão não encontrada.")
    if str(linha["atribuicao"] or "").upper() != "LIVRO3":
        raise CertidaoError("Esta rotina é só para certidões do Livro 3.")
    fonte = str(dict(linha).get("fonte_corpo") or "TEXTO").strip().upper()
    if fonte == "DIGITALIZACAO":
        return {"certidao_id": int(certidao_id), "atualizado": False,
                "motivo": "reproducao"}
    registro_id = int(linha["registro_id"])
    dados = registro(con, "LIVRO3", registro_id)
    if not dados:
        raise CertidaoError(
            f"Registro {registro_id} não encontrado para remontar a certidão.")
    ato_ids = None
    bruto = dict(linha).get("atos_ids")
    if bruto:
        import json as _json
        try:
            parsed = _json.loads(bruto)
            if isinstance(parsed, list) and parsed:
                ato_ids = [int(x) for x in parsed]
        except (TypeError, ValueError):
            ato_ids = None
    try:
        modelo = modelo_certidao_livro3(con)
    except Exception:
        modelo = None
    teor = montar_teor("LIVRO3", dados, modelo=modelo, ato_ids=ato_ids)
    reg = dados["registro"]
    if str(reg.get("situacao") or "").upper() == "CANCELADO":
        if "CANCELADO nesta Serventia" not in teor:
            teor += (
                "\n\nCERTIFICO ainda que o referido registro encontra-se "
                "CANCELADO nesta Serventia.")
    teor = sem_linha_de_assinatura_a_mao(teor)
    emitida_em = str(linha["emitida_em"] or agora or "")
    impressao = hash_certidao(
        "LIVRO3", int(linha["numero"]), int(linha["ano"]), teor, emitida_em)
    con.execute(
        "UPDATE at_certidoes SET teor=?, hash_certidao=? WHERE id=?",
        (teor, impressao, int(certidao_id)))
    return {"certidao_id": int(certidao_id), "atualizado": True, "teor": teor,
            "hash": impressao}


def corpo_por_reproducao(*, registro_numero, paginas: int,
                         sha256: str) -> str:
    """O teor curto que fica no livro quando a certidao e por reproducao.

    **O PAPEL E A IMAGEM; ISTO E O QUE FICA GRAVADO.** O teor da certidao por
    reproducao nao pode ser o texto do registro — se fosse, o banco afirmaria
    um texto que a via impressa nao traz. Ele diz o que a via e: quantas
    folhas, e a impressao digital do arquivo reproduzido, que e por onde se
    confere que a via de hoje e a mesma de amanha.

    E a forma e a do Livro 2 (`ri_digitalizacao.corpo_resumo_digitalizacao`),
    trocado o que muda: la e matricula, aqui e registro.
    """
    return ("CERTIDÃO DE INTEIRO TEOR do registro n. "
            f"{registro_numero} do Livro 3 — Registro Auxiliar, por "
            f"REPRODUÇÃO da digitalização oficial desta Serventia "
            f"({int(paginas)} folha(s); sha256 {sha256})."
            "\n\n"
            "O documento impresso reproduz as folhas digitalizadas e traz o "
            "selo desta certidão ao final.")


def emitir(con: sqlite3.Connection, atribuicao: str, registro_id: int, *,
           hoje: str, agora: str, requerente: str | None = None,
           requerente_documento: str | None = None,
           finalidade: str | None = None,
           usuario: str | None = None, usuario_nome: str | None = None,
           usuario_funcao: str | None = None,
           ato_ids: Sequence[int] | None = None,
           fonte_corpo: str = "TEXTO",
           digitalizacao: dict | None = None) -> dict:
    """Emite a certidao de inteiro teor. ESCREVE.

    O TEOR SAI DO REGISTRO, e nao de quem pede: a certidao reproduz o que esta
    no livro. Por isso ela nao aceita texto de fora — papel que a serventia
    assina nao se digita no balcao.
    """
    p = painel(atribuicao)
    dados = registro(con, atribuicao, registro_id)
    if not dados:
        raise CertidaoError(
            f"Registro {registro_id} não encontrado em {p['nome']}.")
    chave_modelo = ("RI_LIVRO3_CERTIDAO" if p["chave"] == "LIVRO3"
                    else "RCPJ_CERTIDAO" if p["chave"] == "RCPJ"
                    else "RTD_CERTIDAO")
    modelo = None
    try:
        if p["chave"] == "LIVRO3":
            modelo = modelo_certidao_livro3(con)
        else:
            import modelos_da_casa as MODELOS
            modelo = MODELOS.corpo_de(con, chave_modelo)
    except Exception:  # instalação no meio da atualização: mantém o padrão
        modelo = None
    reg = dados["registro"]

    fonte = str(fonte_corpo or "TEXTO").strip().upper()
    if fonte not in FONTES_DO_CORPO:
        raise CertidaoError(
            f"Fonte do teor desconhecida: {fonte_corpo!r}. As que existem são "
            f"{' e '.join(FONTES_DO_CORPO)}.")
    if fonte == "DIGITALIZACAO":
        # **SO O LIVRO 3 TEM VARREDURA DE FICHA**, e por isso so ele reproduz.
        # O RCPJ/RTD guarda o documento apresentado, que e outra coisa: e o
        # papel que o cliente trouxe, e nao a folha do livro desta casa.
        if p["chave"] != "LIVRO3":
            raise CertidaoError(
                f"A certidão por reprodução da digitalização existe no "
                f"Livro 3. Em {p['nome']} a certidão sai pelo teor do livro.")
        caminho = str((digitalizacao or {}).get("path") or "").strip()
        if not caminho:
            raise CertidaoError(
                "Não há digitalização deste registro. Envie a varredura da "
                "ficha ou emita a certidão pelo teor.")
        teor = corpo_por_reproducao(
            registro_numero=reg.get("numero") or "",
            paginas=int((digitalizacao or {}).get("paginas") or 0),
            sha256=str((digitalizacao or {}).get("sha256") or ""))
    else:
        teor = montar_teor(atribuicao, dados, modelo=modelo, ato_ids=ato_ids)

    if str(reg.get("situacao") or "").upper() == "CANCELADO":
        # REGISTRO CANCELADO TAMBEM SE CERTIFICA, e a certidao diz que ele
        # foi. Recusar seria esconder o que existe; calar seria mentir.
        teor += ("\n\nCERTIFICO ainda que o referido registro encontra-se "
                 "CANCELADO nesta Serventia.")

    ano = int(str(hoje)[:4])
    numero = proximo_numero(con, atribuicao, ano)
    # A LINHA DA ASSINATURA A MAO SAI ANTES DO HASH, E NAO ANTES DO
    # INSERT. Esta chamada estava DENTRO do texto do SQL — colada entre
    # as aspas e o `INSERT INTO`, de modo que o banco recusava com
    # «near "teor": syntax error» e a certidao NAO SAIA. Posta so antes
    # do `con.execute`, o teor gravado deixaria de ser o teor que o
    # `hash_certidao` carimbou, e a conferencia de «este e o teor que
    # saiu?» passaria a falhar em toda certidao nova.
    teor = sem_linha_de_assinatura_a_mao(teor)
    impressao = hash_certidao(p["chave"], numero, ano, teor, agora)
    try:
        import json as _json
        atos_ids_json = None
        if ato_ids is not None:
            atos_ids_json = _json.dumps([int(x) for x in ato_ids],
                                       ensure_ascii=False)
        cur = con.execute(
            """INSERT INTO at_certidoes(atribuicao, numero, ano, tabela,
                   registro_id, registro_numero, requerente,
                   requerente_documento, finalidade, atos,
                   atos_ids, teor, hash_certidao, validade_ate, emitida_em,
                   emitida_por, emitida_por_nome, emitida_por_funcao,
                   fonte_corpo, digi_path, digi_sha256)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (p["chave"], numero, ano, p["tabela"], int(registro_id),
             str(reg.get("numero") or ""), (requerente or "").strip() or None,
             # SÓ OS DÍGITOS — é como o documento se compara, e é como o
             # resto da casa o guarda.
             ("".join(c for c in str(requerente_documento or "")
                      if c.isdigit()) or None),
             (finalidade or "").strip() or None, len(dados["atos"]),
             atos_ids_json, teor, impressao, validade_de(hoje), agora,
             usuario, (usuario_nome or "").strip() or None,
             (usuario_funcao or "").strip() or None,
             # O CAMINHO GRAVADO AQUI E O DA VARREDURA DA FICHA; a rota o
             # troca pela COPIA CONGELADA logo depois, que so existe depois
             # de a certidao ter id. Ver `marcar_a_copia_congelada`.
             fonte,
             (str((digitalizacao or {}).get("path") or "") or None
              if fonte == "DIGITALIZACAO" else None),
             (str((digitalizacao or {}).get("sha256") or "") or None
              if fonte == "DIGITALIZACAO" else None)))
    except sqlite3.IntegrityError as erro:
        raise CertidaoError(
            f"A certidão n. {numero}/{ano} de {p['nome']} já existe. Nada foi "
            f"emitido — tente de novo. ({erro})") from erro
    return {"certidao_id": int(cur.lastrowid), "numero": numero, "ano": ano,
            "atribuicao": p["chave"], "nome": p["nome"], "teor": teor,
            "hash": impressao, "atos": len(dados["atos"]), "fonte": fonte}


def marcar_a_copia_congelada(con: sqlite3.Connection, certidao_id: int, *,
                             path: str, sha256: str) -> None:
    """Troca a varredura de hoje pela copia congelada daquela certidao. ESCREVE.

    Chamada DEPOIS do `INSERT`, porque a copia mora numa pasta que leva o id
    da certidao dentro. Enquanto ela nao acontece, a certidao aponta para a
    varredura da ficha — que e verdade naquele instante, e nao um caminho
    inventado.
    """
    con.execute(
        "UPDATE at_certidoes SET digi_path=?, digi_sha256=? WHERE id=?",
        (str(path), str(sha256), int(certidao_id)))


def cancelar(con: sqlite3.Connection, certidao_id: int, *, motivo: str,
             agora: str, usuario: str | None = None,
             selo_cancelado_tjma: Any = False) -> dict:
    """Cancela a certidao emitida. ESCREVE. O teor fica — o que saiu, saiu.

    Certidao errada nao se apaga: apaga-la deixaria a via que o cliente levou
    sem par no banco, e e essa via que alguem vai conferir.
    """
    linha = certidao(con, certidao_id)
    if not linha:
        raise CertidaoError("Certidão não encontrada.")
    if int(linha["cancelada"] or 0):
        raise CertidaoError(
            f"A certidão n. {linha['numero']}/{linha['ano']} já está cancelada "
            f"desde {linha['cancelada_em']}.")
    razao = (motivo or "").strip()
    if len(razao) < 10:
        raise CertidaoError(
            "Escreva por que a certidão está sendo cancelada, com pelo menos "
            "dez letras — é o que fica no lugar dela.")
    if not CANC.declaracao_confirmada(selo_cancelado_tjma):
        raise CertidaoError(CANC.MENSAGEM_DECLARACAO_OBRIGATORIA)
    con.execute(
        """UPDATE at_certidoes SET cancelada=1, motivo_cancelamento=?,
                                   cancelada_em=?, cancelada_por=?,
                                   declaracao_selo_tjma_em=?,
                                   declaracao_selo_tjma_por=?
            WHERE id=?""", (razao, agora, usuario, agora, usuario,
                              int(certidao_id)))
    return CANC.concluir(
        con, tabela="at_certidoes", ato_id=int(certidao_id), motivo=razao,
        agora=agora, usuario=usuario)


# **A FORMA E (TABELA, COLUNA, TIPO), COMO NO RESTO DA CASA** — corrigido em
# 10/09/2026. Estava `(coluna, tipo)`, com a tabela implicita, e **isso
# desligava o guarda das migracoes do sistema inteiro**:
# `tests/test_esquemas.py` varre todo modulo que tenha um `MIGRACOES` e
# desempacota tres valores, de modo que os **quatro** varredores dele
# estouravam com `ValueError: not enough values to unpack` — sem chegar a
# conferir modulo nenhum.
#
# E o estrago nao era o teste vermelho: era que, com ele estourando, **nenhuma
# migracao do sistema estava sendo conferida**. As quatro perguntas que ele faz
# — indice sobre coluna de migracao no SCHEMA, `NOT NULL` sem `DEFAULT`,
# coluna declarada duas vezes, coluna que falta no SCHEMA — sao as que
# custaram caro a este projeto, duas delas no mesmo dia de 25/08/2026.
#
# E a licao de sempre, pela enesima vez: **a mesma palavra em dois lugares nao
# quer dizer a mesma coisa.** Aqui `MIGRACOES` queria dizer «(coluna, tipo) de
# `at_certidoes`»; na casa inteira quer dizer «(tabela, coluna, tipo)». Quem
# ganha e a convencao da casa, porque e ela que o varredor le.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    ("at_certidoes", "declaracao_selo_tjma_em", "TEXT"),
    ("at_certidoes", "declaracao_selo_tjma_por", "TEXT"),
    ("at_certidoes", "atos_ids", "TEXT"),
    # AS BALIZAS DO LIVRO 2 QUE FALTAVAM AQUI — 21/09/2026, ordem do oficial:
    # «mesmas balizas para emissao de certidao».
    #
    #   `validade_ate` e a mais importante, e ela e do CODIGO DE NORMAS: o
    #   art. 53 da o prazo de 30 dias, e a certidao do Livro 2 ja o grava
    #   desde sempre. A daqui saia sem prazo nenhum — e prazo que nao esta
    #   escrito e prazo que ninguem confere.
    #
    #   `requerente_documento` existe no Livro 2 e faltava aqui: o nome
    #   sozinho tem homonimo, e e o documento que diz quem pediu.
    #
    #   `emitida_por_nome` e `emitida_por_funcao` sao quem assina, por
    #   extenso — `emitida_por` guarda o login, e «jean» nao responde «quem
    #   assinou esta certidao?».
    ("at_certidoes", "validade_ate", "TEXT"),
    ("at_certidoes", "requerente_documento", "TEXT"),
    ("at_certidoes", "emitida_por_nome", "TEXT"),
    ("at_certidoes", "emitida_por_funcao", "TEXT"),
    # A CERTIDAO POR REPRODUCAO DA DIGITALIZACAO — 21/09/2026, «aplique o
    # mesmo codigo do livro 2 adaptado».
    #
    #   O Livro 2 emite a certidao de inteiro teor de dois modos: pelo TEXTO
    #   do teor, e por REPRODUCAO da varredura da ficha. O Livro 3 so tinha o
    #   primeiro — e DOIS REGISTROS VIERAM DO ACERVO SEM TEOR NENHUM: o
    #   1.315 e o 1.560, cedulas de credito rural, com zero caractere no
    #   registro e no R-1 (medido em 21/09/2026). Para esses a certidao por
    #   texto e recusada — a copia se tira do livro fisico —, e a reproducao
    #   da varredura e o caminho que eles passam a ter.
    #
    #   `digi_path` guarda a COPIA CONGELADA, e nao a varredura da ficha: a
    #   ficha pode ser varrida de novo amanha, e a certidao que saiu hoje tem
    #   de continuar reproduzindo o que reproduziu. O `digi_sha256` e o da
    #   copia, que e o arquivo que a via leva.
    ("at_certidoes", "fonte_corpo", "TEXT"),
    ("at_certidoes", "digi_path", "TEXT"),
    ("at_certidoes", "digi_sha256", "TEXT"),
)


def init_atrib_certidao_schema(con: sqlite3.Connection) -> None:
    """Cria `at_certidoes`. Idempotente. Chamar DEPOIS de rg e ra."""
    con.executescript(SCHEMA)
    existentes = {r[1] for r in con.execute("PRAGMA table_info(at_certidoes)")}
    for tabela, coluna, tipo in MIGRACOES:
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
