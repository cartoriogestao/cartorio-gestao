"""
RCPJ e RTD — abrir o registro, averbar, cancelar.

COMO SE USA
    with db.transaction() as con:
        registro_id = abrir_registro(
            con, serie="PJ_A", natureza="Estatuto de associação",
            requerente_nome="ASSOCIAÇÃO X", sv=sv, agora=agora,
            data_extenso=hoje, teor=texto)
    audit(...)                      # FORA da transação, como no resto da casa

SERIES CONHECIDAS, E A ATRIBUICAO DE CADA UMA
    PJ_A, PJ_B  — RCPJ (atribuição 3)
    TD_B, TD_C, TD_F — RTD (atribuição 4)

    A atribuição não é parâmetro: vem da série, em `livro_nucleo.SERIES`, e é
    de lá que este módulo a lê — dois módulos não podem discordar de qual
    atribuição uma série pertence.

O QUE ESTE MODULO NAO FAZ
    Não emite selo e não cobra custas — isso é da camada web
    (`atribuicoes_web` / `rg_web`), opcional, na mesma transação do
    lançamento. A regra da casa é: domínio não sela/cobra; a TELA faz.
    Inventar selo aqui seria gravar número sem o escrevente ter digitado.

    A amarração automática ao protocolo geral do caixa também não: a tela
    oferece o select (`protocolo_id`). A regra "averbação consome
    protocolo no RTD e não no RCPJ" (LEVANTAMENTO_QUATRO_ATRIBUICOES.md)
    permanece anotada como fato medido, não como código.

FUNDAMENTO
    Lei 6.015/1973, arts. 114 a 148 (RCPJ) e 127 a 130 (RTD).
"""
from __future__ import annotations

import json
import sqlite3

from bd_nativo import banco
import escrituracao as ESC
import livro_nucleo as LN


class RgError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


SERIES_RCPJ = ("PJ_A", "PJ_B")
SERIES_RTD = ("TD_B", "TD_C", "TD_F")
SERIES_CONHECIDAS = SERIES_RCPJ + SERIES_RTD

# Medido em LEVANTAMENTO_QUATRO_ATRIBUICOES.md, `tbTD_Propriedade`:
# `bitIncrementoProtocoloAVTD` é verdadeiro só no RTD. Ainda não gera
# número de protocolo — ver o cabeçalho do módulo — mas a distinção já
# fica registrada, para quando a integração existir.
AVERBACAO_CONSOME_PROTOCOLO = {3: False, 4: True}

SITUACOES_REGISTRO = ("ATIVO", "CANCELADO")
TIPOS_ATO = ("REGISTRO", "AVERBACAO", "CANCELAMENTO")

# OS DOIS ITENS DO PROTOCOLO QUE SELAM JUNTO COM O ATO E NÃO SÃO O ATO.
#
#   Medido na produção em 09/10/2026, na averbação 378 (registro 148, Caixa
#   Escolar Santa Isabel): o protocolo trouxe `15.1` («Prenotação de títulos»,
#   selo PRENOT…), `15.9.1` e `15.9.2` (a averbação), e a coluna `selo` ficou
#   com o da PRENOTAÇÃO, porque era o primeiro da lista. A etiqueta colada no
#   título saiu **seis vezes** declarando um selo de prenotação de R$ 42,60
#   onde devia estar o da averbação. `15.22` é o arquivamento, que já tinha
#   coluna própria (`selo_arquivamento`) desde 11/09/2026.
CODIGO_TJ_PRENOTACAO = "15.1"
CODIGO_TJ_ARQUIVAMENTO = "15.22"


def papel_dos_selos(saidos: list[tuple[str, str]]) -> tuple[str | None, str | None]:
    """De `(codigo_tj, numero)` dos selos que saíram para UM ato, qual vai em
    `selo` e qual em `selo_arquivamento`. Só calcula.

    `selo` é o do próprio ato — o primeiro que não seja prenotação nem
    arquivamento. **A prenotação só entra em `selo` se ela for tudo o que
    saiu além do arquivamento**: ato sem número na coluna é pior que ato com
    o selo da prenotação, que ao menos é dele.
    """
    principal = prenotacao = arquivamento = None
    for codigo, numero in saidos:
        codigo = str(codigo or "").strip()
        if codigo == CODIGO_TJ_ARQUIVAMENTO:
            arquivamento = arquivamento or numero
        elif codigo == CODIGO_TJ_PRENOTACAO:
            prenotacao = prenotacao or numero
        else:
            principal = principal or numero
    return principal or prenotacao, arquivamento


# OS ITENS DA TABELA 15 QUE SÃO DE OUTRO ATO, E NÃO DO REGISTRO (LD05,
# 21/10/2026). «Um protocolo para todo o trabalho pedido pelo cliente» (o
# oficial, 11/09/2026): o protocolo da notificação traz o registro (15.8), a
# diligência (15.8.1) e a certidão (15.8.2); o de um contrato traz o registro
# e a certidão dele (15.10.1). O registro pelo título selava TODOS — e gastava,
# com o selo do registro, o dinheiro que o cliente pagou pela diligência e
# pela certidão (CN-MA art. 130: um selo por ato, do ato).
#
#   Cada um destes tem a SUA tela, que o sela: a diligência e a certidão da
#   notificação (`rg_notificacao`), a averbação e o cancelamento (a ficha do
#   registro), a certidão e a busca (`atribuicoes_web`), a autenticação de
#   livro (`rg_livro_contabil`) e a apostila. O resto — o registro, a
#   prenotação (15.1), a folha que excede (15.5.2, 15.8.3, 15.18.1) e o
#   arquivamento (15.22) — sela com o registro, como sempre selou
#   (`papel_dos_selos`). O código vale com os filhos: «15.9» cobre «15.9.2».
ITENS_DE_OUTRO_ATO: dict[str, str] = {
    "15.7": "autenticação de livro contábil",
    "15.8.1": "diligência da notificação",
    "15.8.2": "certidão da notificação",
    "15.9": "averbação ou cancelamento",
    "15.10": "certidão",
    "15.11": "busca",
    "15.16": "apostila",
}


def item_e_do_registro(codigo_tj) -> bool:
    """O item da tabela sela com o REGISTRO, ou é de outro ato? Só calcula."""
    codigo = str(codigo_tj or "").strip()
    return bool(codigo) and not any(
        codigo == outro or codigo.startswith(outro + ".")
        for outro in ITENS_DE_OUTRO_ATO)


# O ITEM DO REGISTRO GRATUITO, quando o protocolo não traz item nenhum (LD05,
# 21/10/2026). O ato gratuito não passa pelo caixa — não há o que pagar —, e o
# selo isento continua precisando dizer QUE ATO é (CN-MA art. 133: selo
# «isento» de categoria própria, do ato). É o item que a casa usa em cada livro
# (o mesmo da bancada do LT05): o registro sem valor econômico no Livro B e no
# C, o conjunto de documentos para conservação no F, a inscrição da pessoa
# jurídica no A e a matrícula do periódico no B do RCPJ. A tela deixa trocar.
ITEM_DO_REGISTRO_POR_SERIE: dict[str, str] = {
    "TD_B": "15.3.1", "TD_C": "15.3.1", "TD_F": "15.18",
    "PJ_A": "15.5.1", "PJ_B": "15.6",
}


# AS DECLARAÇÕES QUE O TERMO DE CADA LIVRO FAZ, E QUE A CASA NÃO GUARDAVA
# (LD09, 21/10/2026). O registro do Livro B do RTD é a trasladação (LRP art.
# 142): o documento digitalizado diz tudo, e o termo o encerra. Os outros três
# livros DECLARAM no termo o que a lei enumera — e o termo deles saía com a
# mesma frase do Livro B, sem nenhuma das declarações:
#
#   TD_C — o registro por extrato (LRP art. 143; CN-MA art. 981);
#   PJ_A — a inscrição da pessoa jurídica (LRP art. 120, I a VI; CN-MA 409);
#   PJ_B — a matrícula do jornal ou periódico (LRP art. 123, I).
#
# **É DECLARAÇÃO DO ATO, E NÃO CADASTRO.** Quem lavra as escreve na tela do
# registro, elas vão para o próprio ato (`rg_atos.declaracoes`) na transação
# da lavratura, e o termo as reimprime iguais em qualquer segunda via. Os dados
# da pessoa jurídica que o breve relato certifica (`gravar_dados_da_pj`) são a
# leitura de HOJE, e mudam a cada averbação: se o termo os lesse, a segunda via
# da inscrição de dez anos atrás sairia com a diretoria de hoje.
#
# Cada campo é (o claro do termo, o que a tela pergunta); o claro é o do modelo
# padrão (`modelos_padrao/rcpj_rtd/<RTD|RCPJ>_TEOR_REGISTRO.txt`), numa linha
# só dele, que sai do termo quando a declaração não foi feita.
DECLARACOES_POR_SERIE: dict[str, dict] = {
    "TD_C": {
        "quadro": "Livro C — registro por extrato (LRP art. 143; CN-MA art. 981)",
        "campos": (
            ("valor", "Valor"),
            ("prazo", "Prazo"),
            ("lugar", "Lugar em que foi celebrado"),
            ("partes", "Partes, com a condição jurídica de cada uma "
                       "(ex.: LOCADOR: …; LOCATÁRIO: …)"),
            ("testemunhas", "Testemunhas, quando constarem"),
            ("reconhecimento", "Reconhecimento de firma, se houver: a data e "
                               "o tabelião"),
            ("imposto", "Imposto pago: a importância e a espécie"),
        ),
    },
    "PJ_A": {
        "quadro": ("Livro A — inscrição da pessoa jurídica (LRP art. 120; "
                   "CN-MA art. 409)"),
        "campos": (
            ("denominacao", "Denominação"),
            ("fundo_social", "Fundo social, quando houver"),
            ("fins", "Fins"),
            ("sede", "Sede (endereço completo — CN-MA art. 407, IX)"),
            ("duracao", "Tempo de duração"),
            ("administracao", "Modo por que se administra e representa, ativa e "
                              "passivamente, judicial e extrajudicialmente"),
            ("reforma", "Se o estatuto é reformável no tocante à "
                        "administração, e de que modo"),
            ("responsabilidade", "Se os membros respondem, ou não, "
                                 "subsidiariamente pelas obrigações sociais"),
            ("extincao", "Condições de extinção e destino do patrimônio"),
            ("fundadores", "Fundadores ou instituidores (nacionalidade, estado "
                           "civil e profissão)"),
            ("diretoria", "Diretoria, provisória ou definitiva (nacionalidade, "
                          "estado civil e profissão)"),
            ("residencia_apresentante", "Residência do apresentante dos "
                                        "exemplares"),
        ),
    },
    "PJ_B": {
        "quadro": ("Livro B — matrícula de jornal ou periódico (LRP art. 123, "
                   "I)"),
        "campos": (
            ("titulo_periodico", "Título do jornal ou periódico"),
            ("sede_redacao", "Sede da redação"),
            ("oficinas", "Administração e oficinas impressoras (próprias ou de "
                         "terceiros, com os proprietários)"),
            ("diretor", "Diretor ou redator-chefe (nome, idade, residência e "
                        "nacionalidade)"),
            ("proprietario", "Proprietário (nome, idade, residência e "
                             "nacionalidade)"),
        ),
    },
}

#: Todos os claros de declaração, dos três livros — o termo os conhece.
CLAROS_DAS_DECLARACOES: tuple[str, ...] = tuple(
    claro for livro in DECLARACOES_POR_SERIE.values()
    for claro, _ in livro["campos"])

#: O prefixo dos campos da tela (`declaracao_valor`, `declaracao_sede`…).
PREFIXO_DA_DECLARACAO = "declaracao_"


def declaracoes_do_livro(serie: str, declaracoes: dict | None) -> dict[str, str]:
    """As declarações do termo daquele livro, limpas. Só calcula.

    **A DECLARAÇÃO DE OUTRO LIVRO É RECUSADA, E NÃO ESQUECIDA** (LD09): a tela
    mostra os quadros dos livros da atribuição, e quem preencheu o do Livro A
    e escolheu o Livro B perderia, calado, o que escreveu — e lavraria um
    termo sem as declarações que achou que fez. O espaço repetido sai, como na
    leitura do estatuto (`gravar_dados_da_pj`); declaração vazia não se grava.
    """
    limpas = {str(chave): " ".join(str(valor or "").split())
              for chave, valor in (declaracoes or {}).items()}
    limpas = {chave: valor for chave, valor in limpas.items() if valor}
    do_livro = {claro for claro, _ in
                DECLARACOES_POR_SERIE.get(str(serie or "").upper(), {}).get(
                    "campos", ())}
    fora = sorted(set(limpas) - do_livro)
    if fora:
        rotulos = {claro: rotulo for livro in DECLARACOES_POR_SERIE.values()
                   for claro, rotulo in livro["campos"]}
        raise RgError(
            f"O termo do livro {serie} não declara "
            f"{'; '.join(rotulos.get(c, c) for c in fora)} — isso é de outro "
            f"livro. Confira o livro escolhido ou apague o que não é dele: "
            f"nada foi lavrado.")
    return limpas


def declaracoes_do_formulario(form) -> dict[str, str]:
    """Os campos `declaracao_*` que a tela mandou, sem o prefixo. Só calcula.

    Todos, de qualquer livro: quem confere se são do livro escolhido é
    `declaracoes_do_livro`, na lavratura."""
    return {chave[len(PREFIXO_DA_DECLARACAO):]: valor
            for chave, valor in form.items()
            if chave.startswith(PREFIXO_DA_DECLARACAO)}


def dados_do_termo(con, ato: dict, registro: dict) -> dict:
    """O que o termo do ato declara além do teor — os claros que o LD09 deu a
    `rg_teor_rtdpj.gerar_pdf`. Só LÊ.

    - **REGISTRO**: o protocolo do título que o gerou — o número, a data e o
      apresentante (LRP art. 136: «lançando-se, antes de cada registro, o
      número de ordem, a data do protocolo e o nome do apresentante»; art.
      143; art. 120, caput e VI) —, e as declarações do livro, que a
      lavratura gravou no ato.
    - **AVERBAÇÃO**: o número de ordem dela (LRP arts. 149 e 153; CN-MA art.
      968) — o termo dizia só o do registro averbado.

    O QUE NÃO SE ACHA NÃO SE INVENTA: o registro do acervo, ou o aberto sem
    título (`/rcpj-rtd/novo`, que não passa pelo Livro de Protocolo), não tem
    protocolo a declarar, e a linha dele não sai do termo.
    """
    tipo = str((ato or {}).get("tipo") or "").strip().upper()
    dados: dict = {}
    if tipo == "REGISTRO":
        titulo_id = (registro or {}).get("titulo_id")
        if titulo_id:
            titulo = banco(con).um(
                """SELECT numero, data_apresentacao, apresentante
                     FROM rg_titulos WHERE id=%s""", (int(titulo_id),))
            if titulo:
                dia = str(titulo["data_apresentacao"] or "")[:10]
                dados.update(
                    protocolo=("" if titulo["numero"] is None
                               else str(titulo["numero"])),
                    data_protocolo=(f"{dia[8:10]}/{dia[5:7]}/{dia[:4]}"
                                    if len(dia) == 10 else ""),
                    apresentante=str(titulo["apresentante"] or "").strip())
        try:
            gravadas = json.loads(ato.get("declaracoes") or "{}")
        except ValueError:
            gravadas = {}
        if isinstance(gravadas, dict) and gravadas:
            dados["declaracoes"] = gravadas
    elif tipo.startswith("AVERB") and (ato or {}).get("numero_ordem") is not None:
        dados["numero_averbacao"] = str(ato["numero_ordem"])
    return dados


def subscritor_do_ato(con, ato: dict) -> tuple[str, str] | None:
    """Quem subscreveu o ato, e com que função — (nome, função), ou None. Só LÊ.

    **É QUEM LAVROU, E NÃO QUEM IMPRIME** (LD05, 21/10/2026). O termo dizia
    «Eu, <quem está na tela>, o subscrevo e assino»: a segunda via impressa
    por outro escrevente trocava a assinatura do ato — e a certidão de inteiro
    teor, que reproduz o termo (LRP art. 19, § 1º), não tinha de quem dizer
    que subscreveu. O nome é o que a lavratura gravou (`rg_atos.criado_por`,
    o nome de quem estava na tela); a função é a do cadastro dessa pessoa, e,
    sem ela, a padrão da serventia — a mesma régua de `usuario_funcao`.

    Ato do acervo (sem `criado_por`) devolve None: o que não se acha não se
    inventa, e quem chama decide (o termo cai em quem imprime, como sempre; a
    certidão não reproduz um encerramento que o livro não tem).
    """
    nome = str((ato or {}).get("criado_por") or "").strip()
    if not nome or str((ato or {}).get("origem") or "").upper() == "EOFICIO":
        return None
    bd = banco(con)
    usuario = bd.um(
        """SELECT funcao FROM users WHERE full_name = %s OR username = %s
            ORDER BY (full_name = %s) DESC, id LIMIT 1""", (nome, nome, nome))
    funcao = str((usuario or {}).get("funcao") or "").strip()
    if not funcao:
        padrao = bd.um("SELECT value FROM settings WHERE key = %s",
                       ("serventia_funcao_padrao",))
        funcao = str((padrao or {}).get("value") or "").strip() or "Escrevente"
    return nome, funcao


def _serie(codigo: str) -> LN.Serie:
    if codigo not in SERIES_CONHECIDAS:
        raise RgError(
            f"Série {codigo!r} não é de RCPJ nem de RTD. As que existem "
            f"são: {', '.join(SERIES_CONHECIDAS)}.")
    return LN.serie(codigo)


# --------------------------------------------------------------- consultas


def registro(con: sqlite3.Connection, registro_id: int) -> dict | None:
    """O registro, com tudo que foi cadastrado. Só LÊ."""
    return banco(con).um(
        "SELECT * FROM rg_registros WHERE id=%s", (int(registro_id),))


def atos_do(con: sqlite3.Connection, registro_id: int) -> list[dict]:
    """Os atos do registro, na ordem em que aconteceram. Só LÊ."""
    return banco(con).ler(
        "SELECT * FROM rg_atos WHERE registro_id=%s ORDER BY id",
        (int(registro_id),))


def registro_por_origem(con: sqlite3.Connection, origem: str,
                        origem_chave: str) -> dict | None:
    """O registro de uma chave de origem, ou None. Só LÊ."""
    return banco(con).um(
        "SELECT * FROM rg_registros WHERE origem=%s AND origem_chave=%s "
        "ORDER BY id LIMIT 1",
        (origem, origem_chave))


def _registro_preso(con: sqlite3.Connection, registro_id: int) -> dict | None:
    """O registro, com a linha presa até o fim da transação. ESCREVE.

    Quem confere a situação (ou o que havia antes) e grava em seguida lê por
    aqui, e não por `registro`, que só lê: sem a ponte, dois cancelamentos ao
    mesmo tempo passariam os dois pela conferência, porque a trava do lugar
    no livro (`escrituracao.reservar`) vem depois dela. É o mesmo FOR UPDATE
    de `ra_registro._registro_preso`.
    """
    bd = banco(con)
    bd._escrita()
    return bd.um("SELECT * FROM rg_registros WHERE id=%s FOR UPDATE",
                 (int(registro_id),))


# --------------------------------------------------------- abrir o registro


def abrir_registro(con: sqlite3.Connection, *, serie: str, sv: dict,
                   agora: str, data_extenso: str,
                   natureza: str | None = None,
                   requerente_nome: str | None = None,
                   requerente_documento: str | None = None,
                   teor: str | None = None,
                   teor_formato: str = "texto",
                   usuario: str | None = None, origem: str = "MANUAL",
                   origem_chave: str | None = None,
                   importacao_id: int | None = None,
                   declaracoes: dict | None = None) -> dict:
    """Abre o registro e lavra o ato de REGISTRO. ESCREVE.

    Cada série é folha nova (`livro_nucleo.SERIES[serie].folha_nova`): o
    registro nasce com o próprio ato já ocupando lugar — não há "registro
    sem ato", ao contrário do título de Protesto, que existe antes do
    apontamento.

    Carga repetível por construção: reapresentar a mesma (origem,
    origem_chave) devolve o id já existente.

    `declaracoes` são as do termo do livro (LD09 — `DECLARACOES_POR_SERIE`),
    conferidas ANTES de gastar número de livro e gravadas no ato.
    """
    s = _serie(serie)
    declaradas = declaracoes_do_livro(serie, declaracoes)
    chave = (origem_chave or "").strip() or None
    if origem == "EOFICIO" and not chave:
        raise RgError(
            "Registro de origem EOFICIO precisa de uma chave de origem, "
            "para a carga poder ser repetida sem duplicar.")
    bd = banco(con)
    if chave:
        # «Já entrou?» vale até o INSERT. Sem a ponte, duas cargas da mesma
        # chave passariam as duas pela conferência, e a segunda bateria no
        # UNIQUE(origem, origem_chave) em vez de reaproveitar.
        bd.travar("rg_registros.origem_chave")
        existente = registro_por_origem(bd, origem, chave)
        if existente:
            return {"registro_id": int(existente["id"]), "reaproveitado": True}

    registro_id = int(bd.escrever(
        """INSERT INTO rg_registros(atribuicao, serie, natureza,
               requerente_nome, requerente_documento, situacao, teor,
               teor_formato, origem, origem_chave, importacao_id,
               criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (s.atribuicao, serie, natureza, requerente_nome, requerente_documento,
         "ATIVO", teor, teor_formato, origem, chave, importacao_id, agora,
         usuario))[0]["id"])

    ato_id = int(bd.escrever(
        """INSERT INTO rg_atos(registro_id, tipo, data_ato, teor,
               teor_formato, origem, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (registro_id, "REGISTRO", agora, teor, teor_formato, origem, agora,
         usuario))[0]["id"])
    if declaradas:
        # à parte do INSERT de sempre: o ato sem declaração (o Livro B, a carga
        # do acervo) se grava exatamente como antes do LD09
        bd.escrever("UPDATE rg_atos SET declaracoes=%s WHERE id=%s",
                    (json.dumps(declaradas, ensure_ascii=False, sort_keys=True),
                     ato_id))

    lugar = ESC.reservar(con, serie, "rg_atos", ato_id, sv=sv, agora=agora,
                         data_extenso=data_extenso, paginas=1, usuario=usuario)
    bd.escrever(
        """UPDATE rg_atos SET livro_id=%s, folha=%s, verso=%s, numero_ordem=%s,
                              rotulo=%s WHERE id=%s""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    bd.escrever("UPDATE rg_registros SET numero=%s WHERE id=%s",
                (lugar["numero_ordem"], registro_id))
    return {"registro_id": registro_id, "ato_id": ato_id,
           "reaproveitado": False, **lugar}


# -------------------------------------------------------------- a averbacao


def lancar_averbacao(con: sqlite3.Connection, registro_id: int, *, teor: str,
                     sv: dict, agora: str, data_extenso: str,
                     teor_formato: str = "texto",
                     usuario: str | None = None,
                     origem: str = "MANUAL") -> dict:
    """Lavra a averbação, em folha nova. ESCREVE.

    Ocupa lugar PRÓPRIO no livro — a série é folha nova, e o E-Ofício mede
    cada ato como uma escritura à parte, não como anotação na folha do
    registro original. Só cabe em registro ATIVO.
    """
    reg = _registro_preso(con, registro_id)
    if not reg:
        raise RgError(f"Registro {registro_id} não encontrado.")
    if reg["situacao"] != "ATIVO":
        raise RgError(
            f"O registro está com situação {reg['situacao']} — só se "
            f"averba registro ativo.")
    razao = (teor or "").strip()
    if len(razao) < 10:
        raise RgError(
            "O teor da averbação precisa de pelo menos dez letras.")

    bd = banco(con)
    ato_id = int(bd.escrever(
        """INSERT INTO rg_atos(registro_id, tipo, data_ato, teor,
               teor_formato, origem, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (registro_id, "AVERBACAO", agora, razao, teor_formato, origem, agora,
         usuario))[0]["id"])

    lugar = ESC.reservar(con, reg["serie"], "rg_atos", ato_id, sv=sv,
                         agora=agora, data_extenso=data_extenso, paginas=1,
                         usuario=usuario)
    bd.escrever(
        """UPDATE rg_atos SET livro_id=%s, folha=%s, verso=%s, numero_ordem=%s,
                              rotulo=%s WHERE id=%s""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    return {"registro_id": registro_id, "ato_id": ato_id, **lugar}


# ---------------------------------------------------------- o cancelamento


def lancar_cancelamento(con: sqlite3.Connection, registro_id: int, *,
                        motivo: str, sv: dict, agora: str,
                        data_extenso: str, usuario: str | None = None,
                        origem: str = "MANUAL") -> dict:
    """Cancela o registro, com o ato próprio de cancelamento. ESCREVE.

    Como a averbação, ocupa lugar próprio no livro — em folha nova. Só cabe
    em registro ATIVO; não há cancelamento de cancelamento.
    """
    reg = _registro_preso(con, registro_id)
    if not reg:
        raise RgError(f"Registro {registro_id} não encontrado.")
    if reg["situacao"] != "ATIVO":
        raise RgError(
            f"O registro já está com situação {reg['situacao']}.")
    razao = (motivo or "").strip()
    if len(razao) < 10:
        raise RgError(
            "Escreva o motivo do cancelamento com pelo menos dez letras.")

    bd = banco(con)
    ato_id = int(bd.escrever(
        """INSERT INTO rg_atos(registro_id, tipo, data_ato,
               motivo_cancelamento, origem, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (registro_id, "CANCELAMENTO", agora, razao, origem, agora, usuario))[0]["id"])

    lugar = ESC.reservar(con, reg["serie"], "rg_atos", ato_id, sv=sv,
                         agora=agora, data_extenso=data_extenso, paginas=1,
                         usuario=usuario)
    bd.escrever(
        """UPDATE rg_atos SET livro_id=%s, folha=%s, verso=%s, numero_ordem=%s,
                              rotulo=%s WHERE id=%s""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    bd.escrever("UPDATE rg_registros SET situacao='CANCELADO' WHERE id=%s",
                (registro_id,))
    return {"registro_id": registro_id, "ato_id": ato_id, "motivo": razao,
           **lugar}


# ------------------------------------------- os dados da pessoa jurídica


# O que o breve relato do RCPJ certifica e a casa não guardava (LD05). A
# denominação e o CNPJ são o cadastro do requerente (`corrigir_requerente`).
CAMPOS_DA_PJ = ("pj_sede", "pj_objeto", "pj_capital", "pj_socios",
                "pj_diretoria")


def gravar_dados_da_pj(con, registro_id: int, *, sede: str | None,
                       objeto: str | None, capital: str | None,
                       socios: str | None, diretoria: str | None, agora: str,
                       usuario: str | None) -> dict:
    """Grava os dados da pessoa jurídica que o breve relato certifica. ESCREVE.

    **ISTO NÃO É EDIÇÃO DE TEOR**, como `corrigir_requerente`: o estatuto e as
    atas estão no livro, congelados; isto é a LEITURA deles, gravada na ficha
    por quem leu, com data e nome (LD05, 21/10/2026). Sem ela, a certidão em
    breve relato (CN-MA art. 420, II) teria de ser redigida no balcão — e papel
    que a serventia assina não se redige no balcão. Só do Livro A do RCPJ, que
    é o da pessoa jurídica. A linha presa (`_registro_preso`): duas leituras
    gravadas ao mesmo tempo não se misturam campo a campo.
    """
    reg = _registro_preso(con, registro_id)
    if not reg:
        raise RgError(f"Registro {registro_id} não encontrado.")
    if reg["serie"] != "PJ_A":
        raise RgError(
            "Os dados da pessoa jurídica são do registro do Livro A do RCPJ "
            "(CN-MA art. 420, II).")
    novos = {"pj_sede": sede, "pj_objeto": objeto, "pj_capital": capital,
             "pj_socios": socios, "pj_diretoria": diretoria}
    novos = {k: (" ".join(str(v or "").split()) or None) for k, v in novos.items()}
    faltam = [rotulo for campo, rotulo in (("pj_sede", "o endereço da sede"),
                                           ("pj_objeto", "o objeto social"))
              if not novos[campo]]
    if not (novos["pj_socios"] or novos["pj_diretoria"]):
        faltam.append("os sócios (com as participações) ou a diretoria")
    if faltam:
        raise RgError(f"Falta {', '.join(faltam)} — o breve relato os certifica "
                      f"(CN-MA art. 420, II).")
    antes = {k: reg.get(k) for k in CAMPOS_DA_PJ}
    banco(con).escrever(
        """UPDATE rg_registros
              SET pj_sede=%(pj_sede)s, pj_objeto=%(pj_objeto)s,
                  pj_capital=%(pj_capital)s, pj_socios=%(pj_socios)s,
                  pj_diretoria=%(pj_diretoria)s, pj_dados_em=%(agora)s,
                  pj_dados_por=%(usuario)s
            WHERE id=%(id)s""",
        {**novos, "agora": agora, "usuario": usuario, "id": int(registro_id)})
    return {"registro_id": int(registro_id), "antes": antes, "depois": novos}


# ------------------------------------------------- corrigir dados cadastrais


def corrigir_requerente(con: sqlite3.Connection, registro_id: int, *,
                        requerente_nome: str | None,
                        requerente_documento: str | None,
                        motivo: str) -> dict:
    """Corrige o nome/documento do requerente NO CADASTRO. ESCREVE.

    **ISTO NÃO É EDIÇÃO DE TEOR** — a mesma distinção de `ri_correcoes.py`.
    O teor de cada ato (a ata, a averbação) já congelou o que foi escrito
    naquele dia, e continua sendo a fonte da verdade sobre o que aconteceu
    no livro; esta função corrige só `rg_registros.requerente_nome`/
    `requerente_documento` — o CADASTRO em volta do registro, usado para
    achar o registro na lista e para preencher "Denominação" na certidão e
    na etiqueta.

    Pedido do oficial em 12/09/2026: uma pessoa jurídica muda de nome (por
    averbação, já lavrada) e o cadastro continuava com o nome antigo — sem
    tela nenhuma para corrigir isso, quem procurasse pelo nome novo não
    achava o registro. `motivo` é obrigatório e sempre citado na auditoria,
    com o nome/documento de ANTES ao lado do de depois: é assim que a
    correção fica visível, e não um `UPDATE` silencioso.
    """
    reg = _registro_preso(con, registro_id)
    if not reg:
        raise RgError(f"Registro {registro_id} não encontrado.")
    razao = (motivo or "").strip()
    if len(razao) < 10:
        raise RgError(
            "Escreva o motivo da correção com pelo menos dez letras.")
    novo_nome = (requerente_nome or "").strip() or None
    novo_doc = (requerente_documento or "").strip() or None
    banco(con).escrever(
        "UPDATE rg_registros SET requerente_nome=%s, requerente_documento=%s "
        "WHERE id=%s", (novo_nome, novo_doc, registro_id))
    return {
        "registro_id": registro_id, "motivo": razao,
        "requerente_nome_antes": reg["requerente_nome"],
        "requerente_documento_antes": reg["requerente_documento"],
        "requerente_nome_depois": novo_nome,
        "requerente_documento_depois": novo_doc,
    }
