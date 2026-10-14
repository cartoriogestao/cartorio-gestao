"""
Correcoes administrativas em registro ja lavrado: numero da matricula e partes.

POR QUE ESTE MODULO EXISTE
    Dois erros do dia 18/08/2026 nao tinham conserto em tela nenhuma, e os dois
    sao de cadastro, nao de conteudo do ato:

    1. A MATRICULA NASCEU COM NUMERO JA USADO. O sistema contava o proximo
       numero POR LIVRO. Mas o numero da matricula e unico NA SERVENTIA: os
       livros 2, 2A ... 2S sao VOLUMES do mesmo Livro 2 de Registro Geral, e a
       letra e o volume, nao uma serie propria. O livro "2" estava em 4010 e o
       volume "2S" ja tinha a 4013 — o sistema olhou so o "2" e deu 4011, numero
       que a serventia ja havia usado. Os tres atos lavrados nela dizem, no
       proprio teor, 4014: a escrevente escreveu certo, a maquina contou errado.

    2. O PAPEL DAS PARTES FICOU TROCADO. No R-01 o INCRA entrou como
       "adquirente" — e o INCRA e quem transmite — e a adquirente ficou sem
       papel nenhum. Como o sistema so marca proprietario quem tem papel
       comecando por "propriet", a matricula ficou SEM TITULAR ATIVO: certidao
       de propriedade em branco, ausencia no Indicador Pessoal, e recusa na CTP
       e na DOI por falta de transmitente e de adquirente.

O QUE ESTE MODULO NAO E
    Nao e edicao de teor. Teor lavrado nao se altera aqui nem em lugar nenhum
    deste sistema: erro de teor se corrige por averbacao retificadora. O que se
    corrige aqui e o CADASTRO em volta do ato — numero da ficha e qualificacao
    das partes — e sempre com motivo obrigatorio e rastro completo.

O HASH, E POR QUE ELE E RECALCULADO
    O hash de cada ato inclui o NUMERO DA MATRICULA. Renumerar 4011 para 4014
    invalida, por construcao, a cadeia dos atos daquela ficha. Isso nao e efeito
    colateral indesejado: e o mecanismo funcionando. O que se faz e recalcular a
    cadeia com o numero novo e GRAVAR OS DOIS HASHES na auditoria, de forma que
    a troca seja auditavel e nao um apagamento silencioso. Depois disso a cadeia
    volta a conferir — e passa a conferir contra a verdade, porque os teores
    sempre disseram 4014.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from ri_schema import hash_ato, norm_livro, normalizar_busca, so_digitos, valida_cpf_cnpj


class CorrecaoError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


# ------------------------------------------------------- serie e numeracao


def serie_do_livro(livro: Any) -> str:
    """A serie a que o livro pertence: os digitos iniciais do nome.

    '2' -> '2' | '2-C' -> '2' | '2S' -> '2' | '3' -> '3' | '1A' -> '1'

    A letra e o VOLUME do mesmo livro, e volumes do mesmo livro compartilham a
    numeracao. Livro 2 (Registro Geral) e Livro 3 (Registro Auxiliar) sao series
    distintas e contam separado, cada uma a partir do seu proprio maior numero.
    """
    nome = norm_livro(livro)
    digitos = ""
    for c in nome:
        if c.isdigit():
            digitos += c
        else:
            break
    return digitos or nome


def livros_da_serie(con: sqlite3.Connection, livro: Any) -> list[str]:
    """Todos os livros (volumes) da mesma serie que existem no banco."""
    serie = serie_do_livro(livro)
    encontrados = {norm_livro(livro)}
    con.row_factory = sqlite3.Row
    for tabela, coluna in (("ri_numeracao", "livro"), ("ri_matriculas", "livro_norm")):
        for r in con.execute(f"SELECT DISTINCT {coluna} v FROM {tabela} "
                             f"WHERE COALESCE({coluna},'') <> ''"):
            if serie_do_livro(r["v"]) == serie:
                encontrados.add(norm_livro(r["v"]))
    return sorted(encontrados)


def maior_numero_da_serie(con: sqlite3.Connection, livro: Any) -> int:
    """O maior numero de matricula ja usado na serie, olhando as duas fontes.

    Olha as matriculas de verdade E a tabela de numeracao. A tabela sozinha nao
    basta: ela pode estar atrasada. As matriculas sozinhas nao bastam: um numero
    pode ter sido reservado e a matricula, expurgada.
    """
    volumes = livros_da_serie(con, livro)
    marcas = ",".join("?" * len(volumes))
    con.row_factory = sqlite3.Row
    maior = 0
    linha = con.execute(
        f"""SELECT MAX(CAST(numero AS INTEGER)) n FROM ri_matriculas
            WHERE livro_norm IN ({marcas}) AND numero GLOB '[0-9]*'
              AND CAST(numero AS INTEGER) < ?""", (*volumes, NUMERO_PROVISORIO)).fetchone()
    maior = max(maior, int(linha["n"] or 0))
    linha = con.execute(
        f"""SELECT MAX(maior_em_uso) m, MAX(proximo_numero) p FROM ri_numeracao
            WHERE livro IN ({marcas}) AND proximo_numero < ?""",
        (*volumes, NUMERO_PROVISORIO)).fetchone()
    maior = max(maior, int(linha["m"] or 0), int(linha["p"] or 1) - 1)
    return maior


#: NÚMERO PROVISÓRIO NÃO É NÚMERO DA SÉRIE — 07/10/2026, ordem do oficial («opção 2»).
#: Medido em 06/10 na produção: quatro matrículas encerradas, 904020 a 904023, nascidas
#: de importação e ensaio em setembro, faziam `proximo_numero` devolver 904024 — a
#: próxima matrícula do balcão sairia com esse número. O ajuste de 24/09 mexeu só em
#: `ri_numeracao`, que perde para a maior matrícula. A casa está na casa dos 4.000;
#: nenhum número de seis dígitos a partir de 900.000 é desta série.
NUMERO_PROVISORIO = 900000


def proximo_numero(con: sqlite3.Connection, livro: Any) -> int:
    """O numero da proxima matricula da serie. Nunca repete numero ja usado."""
    return maior_numero_da_serie(con, livro) + 1


def numero_em_uso(con: sqlite3.Connection, livro: Any, numero: Any) -> sqlite3.Row | None:
    """A matricula que ja ocupa este numero na serie, se houver."""
    volumes = livros_da_serie(con, livro)
    marcas = ",".join("?" * len(volumes))
    con.row_factory = sqlite3.Row
    return con.execute(
        f"""SELECT id, numero, livro, complemento FROM ri_matriculas
            WHERE CAST(numero AS INTEGER)=? AND livro_norm IN ({marcas})""",
        (int(numero), *volumes)).fetchone()


# ------------------------------------------------------------- renumeracao


def renumerar_matricula(con: sqlite3.Connection, matricula_id: int, novo_numero: Any, *,
                        motivo: str, agora: str, usuario: str | None = None) -> dict[str, Any]:
    """Troca o numero da matricula e refaz a cadeia de integridade dos atos.

    Roda DENTRO da transacao de quem chama. Nao audita: quem chama audita depois.
    """
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise CorrecaoError("Escreva o motivo da renumeração com pelo menos dez letras.")

    con.row_factory = sqlite3.Row
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?", (matricula_id,)).fetchone()
    if not m:
        raise CorrecaoError("Esta matrícula não existe.")

    try:
        novo = int(so_digitos(novo_numero))
    except ValueError:
        raise CorrecaoError("O número novo tem de ser um número.") from None
    if novo <= 0:
        raise CorrecaoError("O número novo tem de ser maior que zero.")

    antigo = str(m["numero"] or "").strip()
    if antigo == str(novo):
        raise CorrecaoError(f"A matrícula já é a {novo}. Nada a renumerar.")

    if (m["origem"] or "").upper() != "MANUAL":
        raise CorrecaoError(
            f"A matrícula {antigo} veio do acervo (origem {m['origem']}). Matrícula "
            f"importada não se renumera: o número dela é o do livro físico.")

    ocupada = numero_em_uso(con, m["livro"], novo)
    if ocupada and int(ocupada["id"]) != int(matricula_id):
        raise CorrecaoError(
            f"O número {novo} já é da matrícula do Livro {ocupada['livro']}. "
            f"Número de matrícula não se repete na serventia.")

    for c in con.execute("""SELECT numero, ano FROM ri_certidoes
                            WHERE matricula_id=? AND COALESCE(cancelada,0)=0""",
                         (matricula_id,)):
        raise CorrecaoError(
            f"A certidão {c['numero']}/{c['ano']} foi expedida sobre a matrícula {antigo} "
            f"e não está cancelada. Ela afirma o número antigo. Cancele a certidão antes "
            f"de renumerar, ou a certidão passa a divergir da ficha.")

    con.execute("""UPDATE ri_matriculas SET numero=?, atualizado_em=?, atualizado_por=?
                   WHERE id=?""", (str(novo), agora, None, matricula_id))

    # Refaz a cadeia com o numero novo, na mesma ordem de lavratura.
    atos = list(con.execute("""SELECT id, tipo, numero, data_ato, teor, hash_ato
                               FROM ri_atos WHERE matricula_id=? ORDER BY id""",
                            (matricula_id,)))
    refeitos = []
    anterior = None
    for a in atos:
        novo_hash = hash_ato(str(novo), a["tipo"], a["numero"],
                             a["data_ato"] or "", a["teor"] or "", anterior)
        con.execute("UPDATE ri_atos SET hash_ato=?, hash_anterior=? WHERE id=?",
                    (novo_hash, anterior, a["id"]))
        refeitos.append({"ato": f"{a['tipo']}-{a['numero']:02d}",
                         "hash_antigo": a["hash_ato"], "hash_novo": novo_hash})
        anterior = novo_hash

    # A numeracao da serie tem de refletir o numero novo, senao a proxima
    # matricula nasce com o numero que acabamos de ocupar.
    _sincronizar_numeracao(con, m["livro"], agora, usuario)

    return {"matricula_id": matricula_id, "de": antigo, "para": str(novo),
            "motivo": motivo, "atos": refeitos,
            "livro": m["livro"], "serie": serie_do_livro(m["livro"])}


def _sincronizar_numeracao(con: sqlite3.Connection, livro: Any, agora: str,
                           usuario: str | None) -> int:
    """Poe o proximo numero de TODOS os volumes da serie acima do maior em uso.

    Sem isto, corrigir o numero de uma matricula deixaria a contagem apontando
    para tras, e o proximo atendimento repetiria o erro.
    """
    maior = maior_numero_da_serie(con, livro)
    observacao = ("Sincronizado pela numeração da série: o número da matrícula é "
                  "único na serventia, não no volume")
    for volume in livros_da_serie(con, livro):
        con.execute(
            """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso, fixado_em,
                                        observacao)
               VALUES (?,?,?,?,?)
               ON CONFLICT(livro) DO UPDATE SET proximo_numero=excluded.proximo_numero,
                                                maior_em_uso=excluded.maior_em_uso,
                                                fixado_em=excluded.fixado_em,
                                                observacao=excluded.observacao""",
            (volume, maior + 1, maior, agora, observacao))
    return maior + 1


def sincronizar_numeracao(con: sqlite3.Connection, livro: Any, agora: str,
                          usuario: str | None = None) -> int:
    """Versao publica de _sincronizar_numeracao, para a tela de numeração."""
    return _sincronizar_numeracao(con, livro, agora, usuario)


# ---------------------------------------------------------------- partes


PAPEIS = (
    "proprietário",
    "transmitente",
    "adquirente",
    "credor",
    "devedor",
    "usufrutuário",
    "nu-proprietário",
    "outorgante",
    "outorgado",
    "interveniente",
    "cônjuge",
    "representante",
)

# Papel que faz da parte TITULAR ATUAL do imovel. O sistema marca proprietario
# ativo por aqui, e nao por "quem aparece no ultimo ato": em permuta as duas
# pontas aparecem, e so uma passa a ser dona.
PAPEL_DE_TITULAR = ("proprietário", "proprietario", "adquirente", "nu-proprietário",
                    "nu-proprietario")


def e_titular(papel: Any) -> bool:
    """Se este papel faz da parte titular atual do imovel."""
    p = (str(papel or "").strip().lower())
    return any(p.startswith(x) for x in PAPEL_DE_TITULAR)


def corrigir_parte(con: sqlite3.Connection, parte_id: int, *, motivo: str, agora: str,
                   nome: str | None = None, documento: str | None = None,
                   qualificacao: str | None = None, papel: str | None = None,
                   titular: bool | None = None,
                   usuario: str | None = None) -> dict[str, Any]:
    """Corrige nome, documento, qualificacao e papel de uma parte.

    Campo nao informado (None) fica como esta. Roda DENTRO da transacao de quem
    chama, e nao audita.
    """
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise CorrecaoError("Escreva o motivo da correção com pelo menos dez letras.")

    con.row_factory = sqlite3.Row
    p = con.execute("SELECT * FROM ri_partes WHERE id=?", (parte_id,)).fetchone()
    if not p:
        raise CorrecaoError("Esta parte não existe.")

    mudancas: dict[str, dict[str, Any]] = {}
    campos: dict[str, Any] = {}

    if nome is not None:
        limpo = nome.strip()
        if not limpo:
            raise CorrecaoError("O nome da parte não pode ficar em branco.")
        if limpo != (p["nome"] or ""):
            campos["nome"] = limpo
            campos["nome_norm"] = normalizar_busca(limpo)
            mudancas["nome"] = {"de": p["nome"], "para": limpo}

    if documento is not None:
        digitos = so_digitos(documento)
        tipo = "CPF" if len(digitos) == 11 else "CNPJ" if len(digitos) == 14 else None
        if digitos and tipo is None:
            raise CorrecaoError(
                f"O documento tem {len(digitos)} dígitos. CPF tem 11 e CNPJ tem 14.")
        if (digitos or None) != (p["documento_numero"] or None):
            campos["documento_numero"] = digitos or None
            campos["documento_tipo"] = tipo
            campos["documento_valido"] = 1 if (digitos and valida_cpf_cnpj(digitos)) else 0
            mudancas["documento"] = {"de": p["documento_numero"], "para": digitos or None}

    if qualificacao is not None and qualificacao.strip() != (p["qualificacao"] or ""):
        campos["qualificacao"] = qualificacao.strip() or None
        mudancas["qualificacao"] = {"de": p["qualificacao"], "para": qualificacao.strip() or None}

    if papel is not None:
        limpo = papel.strip()
        if limpo != (p["papel"] or ""):
            campos["papel"] = limpo or None
            mudancas["papel"] = {"de": p["papel"], "para": limpo or None}

    # A titularidade segue o papel, salvo ordem expressa em contrario. Quem
    # informa `titular` esta dizendo "eu sei o que estou fazendo" — permuta e
    # partilha existem, e nem todo adquirente fica dono de tudo.
    novo_papel = campos.get("papel", p["papel"])
    alvo = e_titular(novo_papel) if titular is None else bool(titular)
    if int(p["proprietario_ativo"] or 0) != int(alvo):
        campos["proprietario"] = 1 if alvo else int(p["proprietario"] or 0)
        campos["proprietario_ativo"] = 1 if alvo else 0
        mudancas["titular_atual"] = {"de": bool(p["proprietario_ativo"]), "para": alvo}

    if not mudancas:
        raise CorrecaoError("Nada foi alterado nesta parte.")

    atribuicoes = ", ".join(f"{k}=?" for k in campos)
    con.execute(f"UPDATE ri_partes SET {atribuicoes} WHERE id=?",
                (*campos.values(), parte_id))
    con.execute("UPDATE ri_matriculas SET atualizado_em=? WHERE id=?",
                (agora, p["matricula_id"]))

    return {"parte_id": parte_id, "matricula_id": p["matricula_id"],
            "ato_id": p["ato_id"], "nome": campos.get("nome", p["nome"]),
            "motivo": motivo, "mudancas": mudancas}
