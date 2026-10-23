"""
A LISTA DE ATENÇÃO PARA FRAUDES — e o alerta no momento em que importa.

O PEDIDO, do oficial em 26/08/2026
    *"Recebemos pelo malote continuamente comunicações de fraudes. Quero
    incluir um módulo no sistema de controle, em que colocamos nomes e/ou
    documentos de pessoas envolvidas em fraudes, seja vítima ou fraudador ou
    nome que conste em documento fraudado, e o sistema alerta quando um ato for
    requerido ou cadastrado com um nome que consta na lista de atenção para
    fraudes."*

    As comunicações chegam **continuamente**, e em papel. Hoje viram uma pasta,
    e pasta só serve para quem lembra de abrir. O que protege a casa é o nome
    ser reconhecido **na hora em que alguém o digita no balcão**.

AS TRÊS REGRAS, e cada uma existe por um motivo que se pode explicar

    **1. ALERTA NÃO É TRAVA.** Homônimo é a regra, não a exceção: há muitos
    José da Silva. Travar o ato pararia o balcão para gente inocente, e recusar
    um ato é decisão do oficial — não de uma lista. O sistema mostra, com a
    procedência, e quem decide decide.

    **2. A VÍTIMA É QUEM SE PROTEGE, e não quem se barra.** Ela está na lista
    porque o nome dela foi usado por outro. Barrá-la seria fazer com o inocente
    exatamente o que o fraudador fez. Por isso o texto do alerta MUDA com o
    papel, e o de vítima diz o contrário do de envolvido.

    **3. ALERTA SEM PROCEDÊNCIA NÃO SE AVALIA.** "Fulano está na lista" não
    ajuda ninguém a decidir nada. "Fulano consta na comunicação tal, de tal
    órgão, de tal data, como vítima" é o que permite julgar.

O DOCUMENTO É FORTE; O NOME É FRACO
    Documento não tem homônimo: bater CPF é praticamente certeza. Nome bate por
    coincidência o tempo todo. O achado diz **por qual dos dois** bateu, e a
    tela trata os dois de forma diferente — senão o alerta por homônimo afoga
    o alerta por documento, que é o que importa.

O QUE PROTEGE A CASA NÃO É O ALERTA: É O RASTRO DE QUE ELE FOI VISTO
    Se um ato fraudado passar apesar do alerta, a pergunta que vem é "o sistema
    avisou?". `registrar_conferencia()` é a resposta escrita.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from bd_nativo import banco
from fr_schema import so_digitos, tipo_do_documento

# A NORMALIZACAO DO NOME SE IMPORTA DO PROTESTO, e nao se copia — a direcao
# parece estranha (um modulo das seis atribuicoes puxando de uma delas), e e
# menos ruim que a alternativa.
#
# EU COPIEI ESTA FUNCAO em 26/08/2026, com um comentario dizendo que era "a
# mesma" de `pt_schema`. Nao era: a minha devolvia MAIUSCULAS e a da casa
# devolve minusculas. A consulta achava pelo documento e NAO achava pelo nome.
# Nenhuma releitura pegou; quem pegou foi o teste de tela.
#
# `pt_schema.normalizar_nome` e `notas_import.normalizar` concordam entre si
# desde sempre. Uma terceira forma faria a busca da fraude achar coisa
# diferente da busca do protesto para o mesmo nome — que e exatamente o que o
# comentario da minha copia dizia para evitar.
from pt_schema import normalizar_nome

# OS TRÊS PAPÉIS SÃO OS DO OFICIAL, e não uma classificação minha. Ele
# escreveu: "seja vítima ou fraudador ou nome que conste em documento
# fraudado". Cada um muda o que o alerta diz ao balcão.
PAPEIS: dict[str, dict] = {
    "VITIMA": {
        "rotulo": "Vítima de fraude",
        "aviso": (
            "O nome desta pessoa já foi usado por outro numa fraude "
            "comunicada. **Ela é quem se protege, e não quem se barra** — "
            "confira a identificação com atenção redobrada, e se for mesmo "
            "ela, o ato segue normalmente."),
    },
    "ENVOLVIDO": {
        "rotulo": "Envolvido em fraude",
        "aviso": (
            "Esta pessoa consta como envolvida numa fraude comunicada. "
            "Confira a identificação e leia a comunicação antes de lavrar."),
    },
    "DOCUMENTO": {
        "rotulo": "Nome em documento fraudado",
        "aviso": (
            "Este nome consta em documento que foi comunicado como fraudado. "
            "Confira o documento apresentado contra o que a comunicação diz."),
    },
}

SITUACOES = ("ATIVO", "INATIVO")
DECISOES = ("PROSSEGUIU", "RECUSOU", "ANOTOU")


class FraudeError(ValueError):
    """Erro de regra da lista de atenção, com a mensagem pronta para o balcão."""


# ---------------------------------------------------------------- cadastrar


def incluir(con: sqlite3.Connection, *, papel: str, origem: str, agora: str,
            nome: str | None = None, documento: str | None = None,
            origem_data: str | None = None, origem_orgao: str | None = None,
            observacao: str | None = None,
            usuario: str | None = None) -> dict:
    """Inclui um nome ou documento na lista de atenção. ESCREVE.

    EXIGE NOME **OU** DOCUMENTO, e a procedência. Sem um dos dois primeiros não
    há o que procurar; sem a procedência o alerta não se avalia — e alerta que
    não se avalia vira alerta que se ignora.
    """
    if papel not in PAPEIS:
        raise FraudeError(
            f"Papel desconhecido: {papel!r}. Os que existem são " +
            ", ".join(f"{k} ({v['rotulo']})" for k, v in PAPEIS.items()) + ".")

    limpo_nome = (nome or "").strip() or None
    digitos = so_digitos(documento)
    if not limpo_nome and not digitos:
        raise FraudeError(
            "Informe o nome, o documento, ou os dois. Sem um deles não há o "
            "que o sistema possa reconhecer no balcão.")
    if not (origem or "").strip():
        raise FraudeError(
            "Diga de onde veio a comunicação — o ofício, o e-mail, o malote. "
            "Alerta sem procedência não se avalia, e vira alerta que se "
            "ignora.")

    novo = banco(con).escrever(
        """INSERT INTO fr_alertas(nome, nome_norm, documento, documento_tipo,
               papel, origem, origem_data, origem_orgao, observacao,
               situacao, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'ATIVO',%s,%s)
           RETURNING id""",
        (limpo_nome, normalizar_nome(limpo_nome), digitos,
         tipo_do_documento(digitos), papel, origem.strip(),
         (origem_data or None), (origem_orgao or "").strip() or None,
         (observacao or "").strip() or None, agora, usuario))[0]["id"]
    return {"alerta_id": int(novo), "papel": papel,
            "nome": limpo_nome, "documento": digitos}


def inativar(con: sqlite3.Connection, alerta_id: int, *, motivo: str,
             agora: str, usuario: str | None = None) -> dict:
    """Tira o nome da lista, com motivo escrito. ESCREVE.

    NÃO APAGA. Comunicação de fraude é documento, e o que ela gerou fica — o
    que muda é a lista deixar de alertar. Tirar da lista é decisão que alguém
    assina, e por isso o motivo é obrigatório.
    """
    linha = ler(con, alerta_id)
    if not linha:
        raise FraudeError(f"Alerta {alerta_id} não encontrado.")
    texto = (motivo or "").strip()
    if len(texto) < 10:
        raise FraudeError(
            "Escreva por que este nome sai da lista. Comunicação de fraude é "
            "documento: o que ela gerou não se apaga sem explicação.")
    banco(con).escrever(
        """UPDATE fr_alertas SET situacao='INATIVO', inativado_motivo=%s,
               inativado_em=%s, inativado_por=%s WHERE id=%s""",
        (texto, agora, usuario, int(alerta_id)))
    return {"alerta_id": int(alerta_id), "motivo": texto}


def reativar(con: sqlite3.Connection, alerta_id: int, *, agora: str,
             usuario: str | None = None) -> dict:
    """Devolve o nome à lista. ESCREVE. O motivo da saída FICA escrito."""
    linha = ler(con, alerta_id)
    if not linha:
        raise FraudeError(f"Alerta {alerta_id} não encontrado.")
    banco(con).escrever(
        """UPDATE fr_alertas SET situacao='ATIVO', inativado_em=NULL,
               inativado_por=NULL WHERE id=%s""", (int(alerta_id),))
    return {"alerta_id": int(alerta_id)}


# ------------------------------------------------------------- a conferência


def conferir(con: sqlite3.Connection, *, nome: Any = None,
             documento: Any = None) -> list[dict]:
    """Procura o nome e o documento na lista. **Só LÊ**.

    É esta função que as telas chamam antes de lavrar. Ela não grava nada:
    conferência é leitura, e tela de leitura que grava fica presa no
    `busy_timeout` enquanto outro balcão lavra.

    Devolve os achados em ordem de FORÇA — o que bateu por documento primeiro,
    porque documento não tem homônimo e nome tem. Sem essa ordem, um alerta por
    homônimo afogaria o alerta por documento, que é o que importa.
    """
    n = normalizar_nome(nome)
    d = so_digitos(documento)
    if not n and not d:
        return []

    condicoes, valores = [], []
    if d:
        condicoes.append("documento = %s")
        valores.append(d)
    if n:
        condicoes.append("nome_norm = %s")
        valores.append(n)

    achados = []
    for r in banco(con).ler(
            f"""SELECT * FROM fr_alertas
                 WHERE situacao='ATIVO' AND ({' OR '.join(condicoes)})
                 ORDER BY id""", valores):
        linha = dict(r)
        por_documento = bool(d and linha["documento"] == d)
        por_nome = bool(n and linha["nome_norm"] == n)
        linha["por_documento"] = por_documento
        linha["por_nome"] = por_nome
        linha["forca"] = "DOCUMENTO" if por_documento else "NOME"
        linha["papel_rotulo"] = PAPEIS.get(linha["papel"], {}).get(
            "rotulo", linha["papel"])
        linha["aviso"] = PAPEIS.get(linha["papel"], {}).get("aviso", "")
        achados.append(linha)
    achados.sort(key=lambda x: (not x["por_documento"], x["id"]))
    return achados


def conferir_pessoas(con: sqlite3.Connection,
                     pessoas: list[dict]) -> list[dict]:
    """Confere uma lista de pessoas de uma vez. Só LÊ.

    O ato tem partes, e não uma pessoa: um título tem devedor e cedente, um
    assento tem os pais, uma escritura tem outorgantes e outorgados. Conferir
    uma só deixaria o resto passar.

    Cada pessoa é `{"nome": ..., "documento": ..., "papel_no_ato": ...}`, e o
    `papel_no_ato` volta no achado para a tela poder dizer **quem** bateu.
    """
    saida = []
    for p in pessoas or []:
        for achado in conferir(con, nome=p.get("nome"),
                               documento=p.get("documento")):
            saida.append({**achado,
                          "conferido_nome": p.get("nome"),
                          "conferido_documento": p.get("documento"),
                          "papel_no_ato": p.get("papel_no_ato")})
    return saida


def registrar_conferencia(con: sqlite3.Connection, alerta_id: int, *,
                          decisao: str, agora: str, onde: str | None = None,
                          referencia: str | None = None,
                          nome: str | None = None,
                          documento: str | None = None,
                          observacao: str | None = None,
                          usuario: str | None = None) -> dict:
    """Registra que o alerta foi visto, e o que se decidiu. ESCREVE.

    É ISTO QUE PROTEGE A CASA, e não o alerta. Se um ato fraudado passar apesar
    do aviso, a pergunta que vem é "o sistema avisou?" — e esta linha é a
    resposta escrita, com quem viu, quando e o que decidiu.
    """
    if decisao not in DECISOES:
        raise FraudeError(
            f"Decisão desconhecida: {decisao!r}. As que existem são "
            f"{', '.join(DECISOES)}.")
    if not ler(con, alerta_id):
        raise FraudeError(f"Alerta {alerta_id} não encontrado.")
    novo = banco(con).escrever(
        """INSERT INTO fr_conferencias(alerta_id, onde, referencia,
               nome_conferido, documento_conferido, decisao, observacao,
               conferido_em, conferido_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (int(alerta_id), onde, referencia, nome, so_digitos(documento),
         decisao, (observacao or "").strip() or None, agora, usuario))[0]["id"]
    return {"conferencia_id": int(novo), "decisao": decisao}


# ---------------------------------------------------------------- consultas


def ler(con: sqlite3.Connection, alerta_id: int) -> dict | None:
    """Um alerta. Só LÊ."""
    return banco(con).um("SELECT * FROM fr_alertas WHERE id=%s",
                         (int(alerta_id),))


def listar(con: sqlite3.Connection, *, situacao: str = "ATIVO",
           busca: str | None = None, limite: int = 300) -> list[dict]:
    """A lista, filtrada. Só LÊ.

    A BUSCA PROCURA NOME **E** DOCUMENTO com o mesmo texto: quem está no balcão
    tem uma coisa só na mão, e não sabe se é nome ou documento até digitar.
    """
    condicoes, valores = ["situacao = %s"], [situacao]
    texto = (busca or "").strip()
    if texto:
        n = normalizar_nome(texto)
        d = so_digitos(texto)
        alternativas = ["nome_norm ILIKE %s"]
        valores_busca: list[Any] = [f"%{n}%"]
        if d:
            alternativas.append("documento ILIKE %s")
            valores_busca.append(f"%{d}%")
        condicoes.append("(" + " OR ".join(alternativas) + ")")
        valores.extend(valores_busca)
    return [dict(r) | {"papel_rotulo": PAPEIS.get(r["papel"], {}).get(
                "rotulo", r["papel"])}
            for r in banco(con).ler(
                f"""SELECT * FROM fr_alertas WHERE {' AND '.join(condicoes)}
                     ORDER BY id DESC LIMIT %s""", (*valores, int(limite)))]


def conferencias(con: sqlite3.Connection, *, alerta_id: int | None = None,
                 limite: int = 200) -> list[dict]:
    """O rastro das conferências, do mais novo. Só LÊ."""
    onde, valores = "", []
    if alerta_id is not None:
        onde = "WHERE c.alerta_id = %s"
        valores.append(int(alerta_id))
    return [dict(r) for r in banco(con).ler(
        f"""SELECT c.*, a.nome, a.documento, a.papel
              FROM fr_conferencias c
              LEFT JOIN fr_alertas a ON a.id = c.alerta_id
              {onde}
             ORDER BY c.id DESC LIMIT %s""", (*valores, int(limite)))]


def contagem(con: sqlite3.Connection) -> dict:
    """Quantos nomes na lista, e quantas conferências. Só LÊ — para o alto da
    tela e para o painel."""
    bd = banco(con)
    ativos = bd.valor(
        "SELECT count(*) AS c FROM fr_alertas WHERE situacao='ATIVO'")
    por_papel = {r["papel"]: r["n"] for r in bd.ler(
        """SELECT papel, count(*) AS n FROM fr_alertas WHERE situacao='ATIVO'
            GROUP BY papel ORDER BY papel""")}
    conferidas = bd.valor("SELECT count(*) AS c FROM fr_conferencias")
    return {"ativos": int(ativos or 0),
            "por_papel": {k: int(v) for k, v in por_papel.items()},
            "conferencias": int(conferidas or 0)}


# ------------------------------------------------- o que a casa já tem dele
#
# QUANDO UM NOME NOVO ENTRA NA LISTA, a primeira pergunta é: **essa pessoa já
# fez ato aqui?** A comunicação chega depois do fato, e o que ela protege é
# tanto o que vier quanto o que já veio.
#
# As tabelas e colunas abaixo são as que guardam pessoa nesta casa. É uma lista
# DECLARADA e não adivinhada: varrer todas as tabelas procurando coluna com
# "nome" acharia nome de livro, nome de arquivo e nome de usuário.
# `nome_norm` é a coluna já normalizada, quando a tabela tem uma. Onde há, a
# busca acha `JOSÉ` digitando `jose`; onde não há, sobra comparar o texto cru
# em maiúsculas, que acha o nome sem acento e é melhor que não achar nada.
ONDE_MORA_PESSOA: tuple[dict, ...] = (
    {"tabela": "pt_devedores", "nome": "nome", "nome_norm": "nome_norm",
     "documento": "documento_numero", "o_que_e": "devedor de protesto"},
    {"tabela": "pt_titulos", "nome": "cedente_nome", "nome_norm": None,
     "documento": "cedente_documento", "o_que_e": "credor de protesto"},
    {"tabela": "pt_certidoes", "nome": "nome", "nome_norm": None,
     "documento": "documento", "o_que_e": "certidão de protesto"},
    {"tabela": "nt_ato_partes", "nome": "nome", "nome_norm": "nome_norm",
     "documento": "documento", "o_que_e": "parte em ato das Notas"},
    {"tabela": "ri_partes", "nome": "nome", "nome_norm": None,
     "documento": "documento_numero", "o_que_e": "parte em matrícula do RI"},
    {"tabela": "rc_assentos", "nome": "nome", "nome_norm": None,
     "documento": None, "o_que_e": "assento do Registro Civil"},
    {"tabela": "rg_registros", "nome": "requerente_nome", "nome_norm": None,
     "documento": "requerente_documento",
     "o_que_e": "requerente de registro do RCPJ/RTD"},
    {"tabela": "ra_partes", "nome": "nome", "nome_norm": None,
     "documento": "documento_numero", "o_que_e": "parte no Livro 3"},
)


def _fontes_existentes(con: sqlite3.Connection) -> list[dict]:
    """Só as tabelas que existem neste banco. Só LÊ.

    O sistema tem seis atribuições e nem toda instalação tem todas as tabelas
    criadas — e uma consulta a tabela que não existe derruba a tela inteira
    por causa de uma atribuição que a casa não usa.
    """
    bd = banco(con)
    return [f for f in ONDE_MORA_PESSOA if bd.tem_tabela(f["tabela"])]


def atos_da_pessoa(con: sqlite3.Connection, *, nome: Any = None,
                   documento: Any = None, limite: int = 50) -> list[dict]:
    """O que esta casa já lavrou com esse nome ou documento. Só LÊ.

    A comunicação de fraude chega DEPOIS do fato. Saber que a pessoa já tem
    três atos aqui é o que transforma um aviso numa diligência.
    """
    n = normalizar_nome(nome)
    d = so_digitos(documento)
    if not n and not d:
        return []
    bd = banco(con)
    saida = []
    for f in _fontes_existentes(bd):
        condicoes, valores = [], []
        if n:
            # ONDE A TABELA TEM `nome_norm`, COMPARA-SE COM ELA — é a coluna
            # que existe justamente para isto.
            #
            # ONDE NÃO HÁ, A PRÓPRIA FUNÇÃO DA CASA É CHAMADA NO BANCO:
            # `nome_da_casa()` mora no PostgreSQL (`banco_pg_funcoes.sql`) e
            # faz o mesmo que `normalizar_nome`. `LOWER()` sozinho não tira o
            # acento — `JOSÉ` vira `josé`, e não `jose` —, e no Registro Civil
            # quase todo nome tem acento: comparar com `LOWER()` simplesmente
            # não acharia ninguém.
            if f["nome_norm"]:
                condicoes.append(f"{f['nome_norm']} = %s")
            else:
                condicoes.append(f"nome_da_casa({f['nome']}) = %s")
            valores.append(n)
        if d and f["documento"]:
            condicoes.append(
                f"REPLACE(REPLACE(REPLACE({f['documento']},'.',''),"
                f"'-',''),'/','') = %s")
            valores.append(d)
        if not condicoes:
            continue
        try:
            for r in bd.ler(
                    f"""SELECT id, {f['nome']} AS nome FROM {f['tabela']}
                         WHERE {' OR '.join(condicoes)} ORDER BY id LIMIT %s""",
                    (*valores, int(limite))):
                saida.append({"tabela": f["tabela"], "id": r["id"],
                              "nome": r["nome"], "o_que_e": f["o_que_e"]})
        except sqlite3.Error:
            continue
    return saida
