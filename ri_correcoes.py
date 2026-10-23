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

from typing import Any

from bd_nativo import banco
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


def livros_da_serie(con: Any, livro: Any) -> list[str]:
    """Todos os livros (volumes) da mesma serie que existem no banco."""
    serie = serie_do_livro(livro)
    encontrados = {norm_livro(livro)}
    bd = banco(con)
    for tabela, coluna in (("ri_numeracao", "livro"), ("ri_matriculas", "livro_norm")):
        for r in bd.ler(f"SELECT DISTINCT {coluna} AS v FROM {tabela} "
                        f"WHERE COALESCE({coluna},'') <> '' ORDER BY 1"):
            if serie_do_livro(r["v"]) == serie:
                encontrados.add(norm_livro(r["v"]))
    return sorted(encontrados)


def maior_numero_da_serie(con: Any, livro: Any) -> int:
    """O maior numero de matricula ja usado na serie, olhando as duas fontes.

    Olha as matriculas de verdade E a tabela de numeracao. A tabela sozinha nao
    basta: ela pode estar atrasada. As matriculas sozinhas nao bastam: um numero
    pode ter sido reservado e a matricula, expurgada.
    """
    volumes = livros_da_serie(con, livro)
    marcas = ",".join(["%s"] * len(volumes))
    bd = banco(con)
    maior = 0
    # O CASE protege o cast: o PostgreSQL não garante a ordem de um AND.
    linha = bd.um(
        f"""SELECT MAX(CASE WHEN numero ~ '^[0-9]' THEN
                      CASE WHEN substring(numero FROM '^[0-9]+')::bigint < %s
                           THEN substring(numero FROM '^[0-9]+')::bigint END
                    END) AS n
              FROM ri_matriculas
             WHERE livro_norm IN ({marcas})""", (NUMERO_PROVISORIO, *volumes))
    maior = max(maior, int(linha["n"] or 0))
    linha = bd.um(
        f"""SELECT MAX(maior_em_uso) AS m, MAX(proximo_numero) AS p FROM ri_numeracao
            WHERE livro IN ({marcas}) AND proximo_numero < %s""",
        (*volumes, NUMERO_PROVISORIO))
    maior = max(maior, int(linha["m"] or 0), int(linha["p"] or 1) - 1)
    return maior


#: NÚMERO PROVISÓRIO NÃO É NÚMERO DA SÉRIE — 07/10/2026, ordem do oficial («opção 2»).
#: Medido em 06/10 na produção: quatro matrículas encerradas, 904020 a 904023, nascidas
#: de importação e ensaio em setembro, faziam `proximo_numero` devolver 904024 — a
#: próxima matrícula do balcão sairia com esse número. O ajuste de 24/09 mexeu só em
#: `ri_numeracao`, que perde para a maior matrícula. A casa está na casa dos 4.000;
#: nenhum número de seis dígitos a partir de 900.000 é desta série.
NUMERO_PROVISORIO = 900000


def proximo_numero(con: Any, livro: Any) -> int:
    """O numero da proxima matricula da serie. Nunca repete numero ja usado."""
    return maior_numero_da_serie(con, livro) + 1


def numero_em_uso(con: Any, livro: Any, numero: Any) -> dict | None:
    """A matricula que ja ocupa este numero na serie, se houver."""
    volumes = livros_da_serie(con, livro)
    marcas = ",".join(["%s"] * len(volumes))
    return banco(con).um(
        f"""SELECT id, numero, livro, complemento FROM ri_matriculas
            WHERE CASE WHEN numero ~ '^[0-9]' THEN substring(numero FROM '^[0-9]+')::bigint
                       ELSE 0 END = %s
              AND livro_norm IN ({marcas}) ORDER BY id LIMIT 1""",
        (int(numero), *volumes))


# ------------------------------------------------------------- renumeracao


def renumerar_matricula(con: Any, matricula_id: int, novo_numero: Any, *,
                        motivo: str, agora: str, usuario: str | None = None) -> dict[str, Any]:
    """Troca o numero da matricula e refaz a cadeia de integridade dos atos.

    Roda DENTRO da transacao de quem chama. Nao audita: quem chama audita depois.
    """
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise CorrecaoError("Escreva o motivo da renumeração com pelo menos dez letras.")

    bd = banco(con)
    # A conferencia do numero ocupado e a gravacao ficam sob a trava de quem
    # numera a matricula (abertura em `ri_web`, `_sincronizar_numeracao`).
    bd.travar("ri_numeracao.livro")
    m = bd.um("SELECT * FROM ri_matriculas WHERE id=%s", (matricula_id,))
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

    for c in bd.ler("""SELECT numero, ano FROM ri_certidoes
                       WHERE matricula_id=%s AND COALESCE(cancelada,0)=0
                       ORDER BY id""", (matricula_id,)):
        raise CorrecaoError(
            f"A certidão {c['numero']}/{c['ano']} foi expedida sobre a matrícula {antigo} "
            f"e não está cancelada. Ela afirma o número antigo. Cancele a certidão antes "
            f"de renumerar, ou a certidão passa a divergir da ficha.")

    bd.escrever("""UPDATE ri_matriculas SET numero=%s, atualizado_em=%s, atualizado_por=%s
                   WHERE id=%s""", (str(novo), agora, None, matricula_id))

    # Refaz a cadeia com o numero novo, na mesma ordem de lavratura.
    atos = bd.ler("""SELECT id, tipo, numero, data_ato, teor, hash_ato
                     FROM ri_atos WHERE matricula_id=%s ORDER BY id""",
                  (matricula_id,))
    refeitos = []
    anterior = None
    for a in atos:
        novo_hash = hash_ato(str(novo), a["tipo"], a["numero"],
                             a["data_ato"] or "", a["teor"] or "", anterior)
        bd.escrever("UPDATE ri_atos SET hash_ato=%s, hash_anterior=%s WHERE id=%s",
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


def _sincronizar_numeracao(con: Any, livro: Any, agora: str,
                           usuario: str | None) -> int:
    """Poe o proximo numero de TODOS os volumes da serie acima do maior em uso.

    Sem isto, corrigir o numero de uma matricula deixaria a contagem apontando
    para tras, e o proximo atendimento repetiria o erro.
    """
    bd = banco(con)
    bd.travar("ri_numeracao.livro")
    maior = maior_numero_da_serie(con, livro)
    observacao = ("Sincronizado pela numeração da série: o número da matrícula é "
                  "único na serventia, não no volume")
    for volume in livros_da_serie(con, livro):
        bd.escrever(
            """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso, fixado_em,
                                        observacao)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT(livro) DO UPDATE SET proximo_numero=excluded.proximo_numero,
                                                maior_em_uso=excluded.maior_em_uso,
                                                fixado_em=excluded.fixado_em,
                                                observacao=excluded.observacao""",
            (volume, maior + 1, maior, agora, observacao))
    return maior + 1


def sincronizar_numeracao(con: Any, livro: Any, agora: str,
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


# Papel de quem TRANSMITE o imovel no ato — o espelho de `PAPEL_DE_TITULAR`.
PAPEL_DE_QUEM_TRANSMITE = ("transmitente",)


def e_transmitente(papel: Any) -> bool:
    """Se este papel e o de quem transmite o imovel no ato."""
    p = (str(papel or "").strip().lower())
    return any(p.startswith(x) for x in PAPEL_DE_QUEM_TRANSMITE)


def chave_dos_titulares(matricula_id: Any) -> str:
    """A trava do assunto «quem e titular atual desta matricula». So calcula.

    Quem tira (`titulares_que_transmitiram`) e quem corrige (`corrigir_parte`)
    o titular da mesma ficha pegam a mesma, e ANTES de prender as linhas — a
    ordem do renumerar: trava do assunto, depois a linha.
    """
    return f"ri_partes.titular:{int(matricula_id)}"


def titulares_que_transmitiram(con: Any, matricula_id: int, ato_id: int,
                               partes: list[dict]) -> dict[str, list[str]]:
    """Tira da titularidade atual quem transmitiu o imovel no ato. ESCREVE.

    O DEFEITO QUE ISTO CONSERTA — LT03 achou, LD03 consertou (21/10/2026):
    depois do R-1 de compra e venda (transmitente e adquirente), a certidao de
    propriedade afirmava o VENDEDOR como dono, e nao a compradora. A lavratura
    so fazia titular quem tinha papel «propriet...» — a regra desta mesma
    tabela ja contava o adquirente, e as duas divergiam — e ninguem tirava o
    transmitente do quadro. A certidao de propriedade e o quadro de ônus dizem
    o proprietario VIGENTE (Lei 6.015/1973, art. 19, § 9º).

    SO QUANDO O ATO TRAZ QUEM ADQUIRE. Ato com transmitente e sem titular novo
    (papel errado, ato que nao transmite) nao esvazia a matricula: sem dono
    nenhum, a certidao sairia em branco, que e o defeito de 18/08 de novo.

    QUEM E O MESMO — LD10, 21/10/2026 (ressalva da revisao do LD03, «corrija
    tudo»). O LD03 casava pelo nome sempre que faltava o documento de UM dos
    lados, e o homonimo sem CPF saia junto. Agora:
      - pelo DOCUMENTO, quando o ato e o quadro o tem;
      - pelo NOME so quando NENHUM dos dois lados tem documento, e so se ha
        UM titular atual com aquele nome.
    O resto NAO tira ninguem e volta em `a_conferir`, com a frase pronta para
    a tela e para a auditoria: o homonimo (dois ou mais com o nome) e o
    documento de um lado so (o nome bate, mas so o ato ou so o quadro tem
    CPF/CNPJ — a parte da abertura do acervo vem sem ele). Tirar o dono
    errado do quadro e pior que deixar o certo: a certidao afirmaria que ele
    nao e mais dono, e o quadro nao avisa ninguem.

    PRESO, e a leitura e a escrita sao a mesma decisao: a trava do assunto
    (`chave_dos_titulares`) e as linhas lidas `FOR UPDATE`. Esta funcao roda
    na transacao propria, depois do selo; uma correcao de parte ou outra
    lavratura na mesma ficha, no meio, mudaria o quadro entre o que se leu e o
    que se grava. A correcao que chegou antes e vista: a linha que ela tirou
    do quadro sai desta leitura quando ela confirma.

    A LINHA FICA, so deixa de ser atual: `proprietario` continua dizendo que
    ela foi dona, e a abertura continua mostrando quem era. A venda de PARTE
    IDEAL (o vendedor continua condomino) se acerta em «Corrigir» na parte,
    com motivo escrito — o sistema nao guarda a fracao.

    Devolve `{"sairam": nomes, "a_conferir": frases}`.
    """
    saida: dict[str, list[str]] = {"sairam": [], "a_conferir": []}
    if not any(e_titular(p.get("papel")) for p in partes):
        return saida
    quem_transmite = [p for p in partes if e_transmitente(p.get("papel"))]
    if not quem_transmite:
        return saida
    bd = banco(con)
    bd.travar(chave_dos_titulares(matricula_id))
    bd._escrita()
    atuais = bd.ler(
        """SELECT id, nome, nome_norm, documento_numero FROM ri_partes
            WHERE matricula_id=%s AND proprietario_ativo=1
              AND ato_id IS DISTINCT FROM %s
            ORDER BY id FOR UPDATE""", (int(matricula_id), int(ato_id)))
    saem: dict[int, str] = {}
    for t in quem_transmite:
        doc = so_digitos(t.get("documento_numero") or "")
        nome = normalizar_busca(t.get("nome") or "")
        quem = (t.get("nome") or "").strip() or doc
        if doc:
            for a in atuais:
                if so_digitos(a["documento_numero"] or "") == doc:
                    saem[int(a["id"])] = a["nome"]
        xaras = [a for a in atuais if int(a["id"]) not in saem and nome
                 and nome == (a["nome_norm"] or normalizar_busca(a["nome"] or ""))]
        if doc:
            # Com documento no ato, só o xará SEM documento no quadro fica em
            # dúvida; o que tem outro CPF/CNPJ é outra pessoa.
            xaras = [a for a in xaras if not so_digitos(a["documento_numero"] or "")]
        if not xaras:
            continue
        if len(xaras) > 1:
            saida["a_conferir"].append(
                f"{quem}: há {len(xaras)} titulares atuais com este nome e o "
                f"documento não decide qual transmitiu — ninguém saiu do "
                f"quadro. Diga qual em Partes → Corrigir (titular), com o "
                f"motivo.")
        elif doc or so_digitos(xaras[0]["documento_numero"] or ""):
            saida["a_conferir"].append(
                f"{quem}: o nome bate com o titular atual {xaras[0]['nome']}, "
                f"mas só um dos dois tem CPF/CNPJ — pelo nome ninguém saiu do "
                f"quadro. Se é a mesma pessoa, tire-a em Partes → Corrigir "
                f"(titular), com o motivo.")
        else:
            saem[int(xaras[0]["id"])] = xaras[0]["nome"]
    for parte_id in sorted(saem):
        bd.escrever("UPDATE ri_partes SET proprietario_ativo=0 WHERE id=%s",
                    (parte_id,))
    saida["sairam"] = sorted(set(saem.values()))
    return saida


def corrigir_parte(con: Any, parte_id: int, *, motivo: str, agora: str,
                   nome: str | None = None, documento: str | None = None,
                   qualificacao: str | None = None, papel: str | None = None,
                   titular: bool | None = None,
                   usuario: str | None = None) -> dict[str, Any]:
    """Corrige nome, documento, qualificacao e papel de uma parte.

    Campo nao informado (None) fica como esta. Roda DENTRO da transacao de quem
    chama, e nao audita.

    A LINHA SE PRENDE ANTES DE SE CONFERIR — LD10, 21/10/2026. A titularidade
    nova sai da comparacao com a que a linha tem (`proprietario_ativo`); lida
    solta, a saida do transmitente que outra transacao ainda nao confirmou
    passava despercebida, e «ponha de volta como titular» (a venda de parte
    ideal) virava «Nada foi alterado» com o vendedor fora do quadro. A trava
    e a mesma de `titulares_que_transmitiram`, e vem antes da linha.

    A FICHA SE LE ANTES DA TRAVA, E ISSO E SEGURO — LD13, 21/10/2026
    (ressalva da revisao do LD10). O primeiro SELECT so diz QUAL trava pegar,
    e a ficha de uma parte nao muda: nenhum codigo grava `ri_partes.
    matricula_id` depois do INSERT (conferido no LD13; o `acervo_correcao`
    nao libera `ri_partes`). O que se decide — a titularidade — sai da linha
    relida `FOR UPDATE` depois da trava. O chamador em laço
    (`ri_onus_ia.acatar_proprietarios`) corrige so partes da MESMA ficha, e
    pega esta trava antes de ler a lista: quando chega aqui, a trava ja e da
    transacao (pedi-la de novo nao espera) e nenhuma linha de outra ficha
    esta presa — a ordem e sempre trava do assunto, depois linha, e nao fecha
    ciclo com quem tira o transmitente.
    """
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise CorrecaoError("Escreva o motivo da correção com pelo menos dez letras.")

    bd = banco(con)
    ficha = bd.valor("SELECT matricula_id FROM ri_partes WHERE id=%s", (parte_id,))
    if ficha is None:
        raise CorrecaoError("Esta parte não existe.")
    bd.travar(chave_dos_titulares(ficha))
    bd._escrita()
    p = bd.um("SELECT * FROM ri_partes WHERE id=%s FOR UPDATE", (parte_id,))
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

    atribuicoes = ", ".join(f"{k}=%s" for k in campos)
    bd.escrever(f"UPDATE ri_partes SET {atribuicoes} WHERE id=%s",
                (*campos.values(), parte_id))
    bd.escrever("UPDATE ri_matriculas SET atualizado_em=%s WHERE id=%s",
                (agora, p["matricula_id"]))

    return {"parte_id": parte_id, "matricula_id": p["matricula_id"],
            "ato_id": p["ato_id"], "nome": campos.get("nome", p["nome"]),
            "motivo": motivo, "mudancas": mudancas}
