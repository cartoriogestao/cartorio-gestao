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

import re
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

# O ATO DE ORIGEM — 24/11/2026. Um papel a mais, e de outra natureza: não é
# pessoa, é o ATO que a comunicação diz suspenso ou fraudado (a procuração do
# livro tal, folha tal, da serventia tal). Fica FORA de `PAPEIS` de propósito:
# `incluir` exige nome ou documento, e o formulário de pessoa não oferece o
# papel de ato. Quem inclui ato é `incluir_ato`, com os campos do ato.
PAPEL_ATO = "ATO"
PAPEIS_DE_ATO: dict[str, dict] = {
    PAPEL_ATO: {
        "rotulo": "Ato suspenso ou fraudado",
        "aviso": (
            "Este ato — livro e folha de outra serventia — consta de "
            "comunicação como SUSPENSO ou FRAUDADO. Antes de lavrar ou "
            "registrar com base nele, confira o traslado com a serventia de "
            "origem e leia a comunicação. O aviso não trava: quem decide é o "
            "oficial."),
    },
}
TODOS_OS_PAPEIS: dict[str, dict] = {**PAPEIS, **PAPEIS_DE_ATO}

SITUACOES = ("ATIVO", "INATIVO")
DECISOES = ("PROSSEGUIU", "RECUSOU", "ANOTOU")


def _rotulo(papel: str) -> str:
    return TODOS_OS_PAPEIS.get(papel, {}).get("rotulo", papel)


def _aviso(papel: str) -> str:
    return TODOS_OS_PAPEIS.get(papel, {}).get("aviso", "")


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
        linha["papel_rotulo"] = _rotulo(linha["papel"])
        linha["aviso"] = _aviso(linha["papel"])
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
        # O ATO SE PROCURA PELA SERVENTIA E PELA CIDADE — é o que quem recebe a
        # circular tem na mão («a de Cidade Exemplo já está na lista?»).
        c = _comparavel(texto)
        if c:
            alternativas += ["ato_serventia_norm ILIKE %s", "ato_cidade_norm ILIKE %s"]
            valores_busca += [f"%{c}%", f"%{c}%"]
        condicoes.append("(" + " OR ".join(alternativas) + ")")
        valores.extend(valores_busca)
    return [dict(r) | {"papel_rotulo": _rotulo(r["papel"]),
                       "ato_descricao": (descrever_ato(r)
                                         if r["papel"] == PAPEL_ATO else None)}
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


# ============================================================ O ATO DE ORIGEM
#
# O CASO, de 24/11/2026: uma circular de outro estado suspendeu procurações
# identificadas SÓ por serventia, livro, folha e número de ordem — sem o nome
# de ninguém. A lista só procurava pessoa: nada entrou, o expediente foi
# arquivado como ciência, e o traslado podia chegar ao balcão sem aviso.
#
# O QUE SE PROCURA É O ATO DE OUTRA SERVENTIA CITADO NO ATO DAQUI: a procuração
# de terceiro com que se lavra uma escritura nas Notas, o ato anterior que um
# substabelecimento ou uma revogação cita, a procuração citada num título
# prenotado no RI.
#
# AS MESMAS TRÊS REGRAS DO ALERTA DE PESSOA
#   1. Não é trava — mostra, com a procedência, e o oficial decide.
#   2. Sem procedência não entra (`origem` obrigatória, como em `incluir`).
#   3. A força do achado se diz: livro e folha batem por coincidência entre
#      serventias diferentes (toda serventia tem um livro 10, folha 20); o que
#      dá certeza é a SERVENTIA bater junto — pelo CNS, que não se repete, ou
#      pelo nome dela. Por isso o achado diz por que bateu, e a tela pinta de
#      vermelho só o que bateu com a serventia.
#
# LIVRO + (FOLHA OU ORDEM) É O MÍNIMO para entrar e para bater. Só o livro
# acenderia o alerta para o livro inteiro; só a folha não identifica nada.

_ORDINAIS = re.compile(r"[º°ª]")


def _leve(texto: Any) -> str:
    """Sem acento, sem caixa e sem ordinal, mas COM a pontuação — é ela que
    separa «120-A» (livro 120A) de «120 a 125» (faixa de folhas)."""
    s = _ORDINAIS.sub("", str(texto or ""))
    return normalizar_nome(s) or ""


def _comparavel(texto: Any) -> str:
    """A forma que compara serventia e cidade: sem acento, sem caixa, sem
    ordinal e sem pontuação. «1º Tabelionato de Notas – Cidade Exemplo/SP» e
    «1 tabelionato de notas cidade exemplo sp» são a mesma coisa aqui."""
    return " ".join(re.sub(r"[^0-9a-z]+", " ", _leve(texto)).split())


def livro_normalizado(valor: Any) -> str | None:
    """«Livro nº 0120-A» -> «120A»; «3-B» -> «3B»; «L. 12» -> «12».

    O ZERO À ESQUERDA SAI (o livro 0120 é o 120), e a letra fica — o livro 3-B
    não é o 3."""
    s = _leve(valor)
    s = re.sub(r"\b(livro|liv|lv|l|numero|num|n)\b\.?", " ", s)
    m = re.search(r"(\d{1,6})\s*-?\s*([a-z])?(?![a-z0-9])", s)
    if m:
        return str(int(m.group(1))) + (m.group(2) or "").upper()
    letras = re.sub(r"[^a-z0-9]", "", s).upper()
    return letras or None


def folhas_normalizadas(valor: Any) -> list[int]:
    """As folhas de um campo de folha: «45» -> [45]; «45v» -> [45];
    «45/47» e «45 a 47» -> [45, 46, 47]; «45 e 52» -> [45, 52].

    O VERSO É A MESMA FOLHA: «45v» bate com «45». A FAIXA ABRE até 20 folhas —
    mais que isso é número de outra coisa que entrou no campo, e abrir
    acenderia o alerta para meio livro."""
    s = _leve(valor)
    m = re.fullmatch(r"\D*?(\d{1,5})\s*(?:v(?:erso)?\.?)?\s*(?:a|ate|/|-)\s*"
                     r"(\d{1,5})\s*(?:v(?:erso)?\.?)?\D*", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 0 < b - a <= 20:
            return list(range(a, b + 1))
    return sorted({int(x) for x in re.findall(r"\d{1,5}", s)})[:20]


def ordem_normalizada(valor: Any) -> str | None:
    d = so_digitos(valor)
    return str(int(d)) if d else None


def _folhas_texto(folhas: list[int]) -> str | None:
    return ("|" + "|".join(str(f) for f in folhas) + "|") if folhas else None


def _folhas_da_linha(linha: dict) -> set[int]:
    return {int(x) for x in str(linha.get("ato_folhas_norm") or "").split("|")
            if x.isdigit()}


def descrever_ato(linha: dict) -> str:
    """O ato numa linha só, como o balcão lê: «Procuração — 1º Tabelionato de
    Cidade Exemplo/SP (CNS 000000), livro 120, folha 45, ordem 3, de 2026-03-10»."""
    d = dict(linha)
    onde = d.get("ato_serventia") or ""
    lugar = "/".join(x for x in (d.get("ato_cidade"), d.get("ato_uf")) if x)
    if lugar and _comparavel(d.get("ato_cidade")) not in _comparavel(onde):
        onde = f"{onde}, {lugar}" if onde else lugar
    if d.get("ato_cns"):
        onde = f"{onde} (CNS {d['ato_cns']})" if onde else f"CNS {d['ato_cns']}"
    partes = [p for p in (
        onde or None,
        f"livro {d['ato_livro']}" if d.get("ato_livro") else None,
        f"folha {d['ato_folha']}" if d.get("ato_folha") else None,
        f"ordem {d['ato_ordem']}" if d.get("ato_ordem") else None,
        f"de {d['ato_data']}" if d.get("ato_data") else None) if p]
    natureza = (d.get("ato_natureza") or "Ato").strip()
    return f"{natureza} — {', '.join(partes)}"


def incluir_ato(con: sqlite3.Connection, *, origem: str, agora: str,
                livro: str | None, folha: str | None = None,
                ordem: str | None = None, serventia: str | None = None,
                cns: str | None = None, cidade: str | None = None,
                uf: str | None = None, natureza: str | None = None,
                data: str | None = None, origem_data: str | None = None,
                origem_orgao: str | None = None,
                observacao: str | None = None,
                usuario: str | None = None) -> dict:
    """Inclui um ATO de outra serventia na lista de atenção. ESCREVE.

    A MESMA PORTA DE `incluir`, com a mesma régua de procedência: sem dizer de
    onde veio, não entra. E o ato tem de ser achável: livro, folha ou ordem, e
    de onde ele é (serventia, CNS ou cidade) — sem a serventia, «livro 120,
    folha 45» é o de qualquer cartório do país.
    """
    livro_n = livro_normalizado(livro)
    folhas = folhas_normalizadas(folha) if (folha or "").strip() else []
    ordem_n = ordem_normalizada(ordem)
    cns_d = so_digitos(cns)
    if not livro_n:
        raise FraudeError(
            "Informe o livro do ato. É por ele que o sistema reconhece o "
            "traslado quando ele aparecer no balcão.")
    if not folhas and not ordem_n:
        raise FraudeError(
            "Informe a folha ou o número de ordem do ato. Só o livro acenderia "
            "o alerta para o livro inteiro.")
    if not ((serventia or "").strip() or cns_d or (cidade or "").strip()):
        raise FraudeError(
            "Diga de que serventia é o ato — o nome, o CNS ou ao menos a "
            "cidade. Sem isso, «livro e folha» é o de qualquer cartório.")
    if not (origem or "").strip():
        raise FraudeError(
            "Diga de onde veio a comunicação — o ofício, o e-mail, o malote. "
            "Alerta sem procedência não se avalia, e vira alerta que se "
            "ignora.")

    def limpo(v):
        return " ".join(str(v or "").split()) or None

    novo = banco(con).escrever(
        """INSERT INTO fr_alertas(papel, origem, origem_data, origem_orgao,
               observacao, situacao, criado_em, criado_por,
               ato_natureza, ato_serventia, ato_serventia_norm, ato_cns,
               ato_cidade, ato_cidade_norm, ato_uf, ato_livro, ato_livro_norm,
               ato_folha, ato_folhas_norm, ato_ordem, ato_ordem_norm, ato_data)
           VALUES (%s,%s,%s,%s,%s,'ATIVO',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                   %s,%s,%s,%s,%s)
           RETURNING id""",
        (PAPEL_ATO, origem.strip(), (origem_data or None),
         limpo(origem_orgao), (observacao or "").strip() or None, agora,
         usuario, limpo(natureza), limpo(serventia),
         _comparavel(serventia) or None, cns_d, limpo(cidade),
         _comparavel(cidade) or None, (limpo(uf) or "").upper() or None,
         limpo(livro), livro_n, limpo(folha), _folhas_texto(folhas),
         limpo(ordem), ordem_n, (data or None)))[0]["id"]
    linha = ler(con, int(novo))
    return {"alerta_id": int(novo), "papel": PAPEL_ATO,
            "descricao": descrever_ato(linha)}


def _candidatos(con, livros: list[str]) -> list[dict]:
    """Os alertas de ato ATIVOS desses livros. Só LÊ."""
    livros = [x for x in dict.fromkeys(livros) if x]
    if not livros:
        return []
    marcas = ",".join(["%s"] * len(livros))
    return [dict(r) for r in banco(con).ler(
        f"""SELECT * FROM fr_alertas
             WHERE situacao='ATIVO' AND papel=%s AND ato_livro_norm IN ({marcas})
             ORDER BY id""", (PAPEL_ATO, *livros))]


_FORCA_DO_ATO = {"SERVENTIA": 0, "CIDADE": 1, "LIVRO_FOLHA": 2}


def _achado_de_ato(linha: dict, *, forca: str, por_que: str,
                   conferido: str) -> dict:
    return {**linha, "forca": forca, "por_que": por_que,
            "papel_rotulo": _rotulo(PAPEL_ATO), "aviso": _aviso(PAPEL_ATO),
            "ato_descricao": descrever_ato(linha),
            # O QUE SE CONFERIU vai no campo de nome do rastro: é ele que a
            # macro do alerta devolve ao registrar a conferência.
            "conferido_nome": conferido, "conferido_documento": None}


def conferir_ato(con: sqlite3.Connection, *, livro: Any = None,
                 folha: Any = None, ordem: Any = None, serventia: Any = None,
                 cns: Any = None, cidade: Any = None, uf: Any = None,
                 natureza: Any = None) -> list[dict]:
    """Procura um ato de outra serventia, dado EM CAMPOS, na lista. **Só LÊ**.

    Bate quando o LIVRO é o mesmo e a FOLHA ou a ORDEM também. Daí, a
    serventia decide a força:
      - CNS igual, ou o mesmo nome de serventia → SERVENTIA (certeza);
      - a mesma cidade → CIDADE (há cidade com mais de um tabelionato);
      - nada sobre a serventia dos dois lados → LIVRO_FOLHA (coincidência
        possível: confira).
    E NÃO BATE quando os dois lados dizem serventias diferentes — CNS diferente,
    cidade diferente ou UF diferente: aí é outro cartório, e o alerta seria
    falso com toda a certeza.
    """
    livro_n = livro_normalizado(livro)
    folhas = set(folhas_normalizadas(folha)) if str(folha or "").strip() else set()
    ordem_n = ordem_normalizada(ordem)
    if not livro_n or not (folhas or ordem_n):
        return []
    cns_d = so_digitos(cns)
    serv = _comparavel(serventia)
    cid = _comparavel(cidade)
    uf_n = _comparavel(uf)
    conferido = descrever_ato({
        "ato_natureza": natureza or "Ato citado", "ato_serventia": serventia,
        "ato_cns": cns_d, "ato_cidade": cidade, "ato_uf": uf, "ato_livro": livro,
        "ato_folha": folha, "ato_ordem": ordem})
    achados = []
    for linha in _candidatos(con, [livro_n]):
        bate_folha = bool(folhas & _folhas_da_linha(linha))
        bate_ordem = bool(ordem_n and linha.get("ato_ordem_norm") == ordem_n)
        if not (bate_folha or bate_ordem):
            continue
        if cns_d and linha.get("ato_cns") and cns_d != linha["ato_cns"]:
            continue
        if cid and linha.get("ato_cidade_norm") and cid != linha["ato_cidade_norm"]:
            continue
        if (uf_n and linha.get("ato_uf")
                and uf_n != _comparavel(linha["ato_uf"])):
            continue
        pelo = "folha" if bate_folha else "número de ordem"
        if cns_d and cns_d == linha.get("ato_cns"):
            forca, por_que = "SERVENTIA", f"o CNS da serventia, o livro e a {pelo}"
        elif serv and serv == linha.get("ato_serventia_norm"):
            forca, por_que = "SERVENTIA", f"o nome da serventia, o livro e a {pelo}"
        elif cid and cid == linha.get("ato_cidade_norm"):
            forca, por_que = "CIDADE", f"a cidade, o livro e a {pelo}"
        else:
            forca, por_que = "LIVRO_FOLHA", f"o livro e a {pelo}"
        achados.append(_achado_de_ato(linha, forca=forca, por_que=por_que,
                                      conferido=conferido))
    achados.sort(key=lambda x: (_FORCA_DO_ATO[x["forca"]], x["id"]))
    return achados


# NO TEXTO LIVRE a referência vem escrita como cada um escreve: «procuração
# lavrada no 2º Tabelionato de Cidade Exemplo/SP, livro 120, fls. 45/46». As
# expressões abaixo leem a forma `_leve` (sem acento, sem caixa, com pontuação).
_LIVRO_NO_TEXTO = re.compile(
    r"\b(?:livro|liv\.?|lv\.?|l\.)\s*(?:n\.?\s*|numero\s*)?(\d{1,6})"
    r"(?:\s*-\s*([a-z])\b|([a-z])\b)?")
_FOLHA_NO_TEXTO = re.compile(
    r"\b(?:folhas?|fls?\.?|f\.)\s*(?:n\.?\s*)?(\d{1,5})\s*(?:v(?:erso)?\b\.?)?"
    r"(?:\s*(?:a|ate|/|-|e)\s*(\d{1,5}))?")
_ORDEM_NO_TEXTO = re.compile(
    r"\b(?:ordem|termo|protocolo|ato)\s*(?:n\.?\s*|numero\s*|de\s+n\.?\s*)?"
    r"(\d{1,7})")


def referencias_no_texto(texto: Any) -> dict:
    """Os livros, folhas e ordens escritos num texto livre. Só calcula."""
    s = _leve(texto)
    livros = [str(int(m.group(1))) + (m.group(2) or m.group(3) or "").upper()
              for m in _LIVRO_NO_TEXTO.finditer(s)]
    folhas: set[int] = set()
    for m in _FOLHA_NO_TEXTO.finditer(s):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else None
        if b is not None and 0 < b - a <= 20:
            folhas.update(range(a, b + 1))
        else:
            folhas.add(a)
            if b is not None:
                folhas.add(b)
    ordens = {str(int(m.group(1))) for m in _ORDEM_NO_TEXTO.finditer(s)}
    return {"livros": list(dict.fromkeys(livros)), "folhas": folhas,
            "ordens": ordens}


def conferir_ato_no_texto(con: sqlite3.Connection, *textos: Any) -> list[dict]:
    """Procura, num TEXTO LIVRE, ato que esteja na lista. **Só LÊ**.

    É o caso do instrumento da representação nas Notas («livro, folha e
    serventia da procuração», um campo só) e dos campos de texto da prenotação
    no RI. Lê os livros, as folhas e as ordens escritas; bate quando o livro e
    a folha (ou a ordem) de um alerta estão lá. A serventia, aqui, se confere
    pelo contrário: é o CNS, o nome ou a cidade DO ALERTA que se procura no
    texto. Achou → SERVENTIA ou CIDADE; não achou → LIVRO_FOLHA, para conferir.
    """
    junto = " · ".join(str(t) for t in textos if str(t or "").strip())
    if not junto:
        return []
    refs = referencias_no_texto(junto)
    if not refs["livros"] or not (refs["folhas"] or refs["ordens"]):
        return []
    comparavel = f" {_comparavel(junto)} "
    # O CNS escrito com ponto ou traço («12.345-6») conta como o mesmo número.
    numeros = set(re.findall(r"\d+", junto)) | {
        re.sub(r"\D", "", m) for m in re.findall(r"\d(?:[.\-]?\d)*", junto)}
    achados = []
    for linha in _candidatos(con, refs["livros"]):
        bate_folha = bool(refs["folhas"] & _folhas_da_linha(linha))
        bate_ordem = bool(linha.get("ato_ordem_norm")
                          and linha["ato_ordem_norm"] in refs["ordens"])
        if not (bate_folha or bate_ordem):
            continue
        pelo = "folha" if bate_folha else "número de ordem"
        serv = linha.get("ato_serventia_norm")
        cid = linha.get("ato_cidade_norm")
        if linha.get("ato_cns") and linha["ato_cns"] in numeros:
            forca, por_que = "SERVENTIA", f"o CNS da serventia, o livro e a {pelo}"
        elif serv and f" {serv} " in comparavel:
            forca, por_que = "SERVENTIA", f"o nome da serventia, o livro e a {pelo}"
        elif cid and f" {cid} " in comparavel:
            forca, por_que = "CIDADE", f"a cidade, o livro e a {pelo}"
        else:
            forca, por_que = "LIVRO_FOLHA", f"o livro e a {pelo}"
        achados.append(_achado_de_ato(linha, forca=forca, por_que=por_que,
                                      conferido=" ".join(junto.split())[:300]))
    achados.sort(key=lambda x: (_FORCA_DO_ATO[x["forca"]], x["id"]))
    return achados


def _uma_vez(achados: list[dict]) -> list[dict]:
    vistos, saida = set(), []
    for a in achados:
        if a["id"] not in vistos:
            vistos.add(a["id"])
            saida.append(a)
    return saida


def atos_citados_no_ato_de_notas(con: sqlite3.Connection, ato: Any,
                                 partes: list) -> list[dict]:
    """Os atos de outra serventia que este ato das Notas cita, conferidos na
    lista. **Só LÊ**.

    ONDE AS NOTAS GUARDAM O ATO DE TERCEIRO, medido no esquema em 24/11/2026:
      - `nt_atos.anterior_*` (livro, folha, cartório, cidade, UF, CNS) — o ato
        anterior que o substabelecimento, a revogação ou a retificação cita,
        em campos, como a CENSEC pede;
      - o INSTRUMENTO de cada representação (`nt_ato_representacoes.instrumento`
        e a coluna antiga `nt_ato_partes.representa_instrumento`) — «livro,
        folha e serventia da procuração» (CN-MA art. 798, VI), em texto livre.
    É o segundo que pega o caso do balcão: a escritura lavrada aqui com
    procuração de outra serventia.
    """
    a = dict(ato or {})
    saida = []
    if a.get("anterior_livro"):
        for x in conferir_ato(con, livro=a.get("anterior_livro"),
                              folha=a.get("anterior_folha"),
                              serventia=a.get("anterior_cartorio"),
                              cns=a.get("anterior_cns"),
                              cidade=a.get("anterior_cidade"),
                              uf=a.get("anterior_uf")):
            saida.append({**x, "papel_no_ato": "ato anterior citado"})
    for p in partes or []:
        d = dict(p)
        textos = [dict(v).get("instrumento") for v in (d.get("representacoes") or [])]
        textos.append(d.get("representa_instrumento"))
        for t in dict.fromkeys(x for x in textos if (x or "").strip()):
            for x in conferir_ato_no_texto(con, t):
                saida.append({**x, "papel_no_ato":
                              f"instrumento de {d.get('nome') or 'representante'}"})
    return _uma_vez(saida)


def atos_citados_na_prenotacao(con: sqlite3.Connection, protocolo: Any) -> list[dict]:
    """Os atos de outra serventia que a prenotação do RI cita, conferidos na
    lista. **Só LÊ**.

    O RI NÃO TINHA CAMPO para a procuração citada no título (medido em
    24/11/2026: `ri_protocolos` só tem a natureza, o objeto, o documento
    apresentado e a anotação, todos texto livre). O mínimo que se acrescentou
    é `procuracao_citada`, um campo de texto como o instrumento das Notas; os
    outros três também se leem, porque é neles que a referência já vinha
    sendo escrita.
    """
    p = dict(protocolo or {})
    textos = [p.get(c) for c in ("procuracao_citada", "documento_descricao",
                                 "objeto", "anotacao")]
    return [{**x, "papel_no_ato": "ato citado no título"}
            for x in conferir_ato_no_texto(con, *textos)]
