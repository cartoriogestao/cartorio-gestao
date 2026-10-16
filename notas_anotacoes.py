"""
Anotacao a margem do ato notarial.

O PROBLEMA QUE ISTO RESOLVE
    A revogacao era lavrada no livro de procuracoes como ato novo, e a
    procuracao revogada continuava no livro anterior INTACTA. Duas verdades no
    mesmo acervo.

    Quem pedisse certidao da procuracao de 2024 recebia uma certidao que nao
    dizia que ela fora revogada em 2026 — e a certidao do ato notarial vale
    pelo que o livro diz. Uma procuracao revogada circulando com certidao
    limpa e um problema de terceiro de boa-fe, nao de cadastro.

    A tabela `nt_ato_anotacoes` existia no esquema desde o inicio, com as
    colunas certas — data, tipo, texto, selo, ato relacionado — e NENHUMA linha
    do sistema a usava. Nem rota, nem tela, nem teste. Este modulo e o fio que
    faltava ligar.

O QUE MUDA NA PRATICA
    Lancando a revogacao no livro, o sistema escreve sozinho a anotacao a
    margem da procuracao revogada, e poe a procuracao em REVOGADO. O traslado
    e a certidao dela passam a sair COM a anotacao. Nao havendo como achar o
    ato anterior — porque foi lavrado em outra serventia, ou porque os dados do
    ato anterior nao foram preenchidos — o ato entra na lista de PENDENTES, que
    e o que a correicao pergunta.

ANOTACAO NAO SE APAGA
    Nao ha funcao de remover. Anotacao a margem e escrita a tinta: errada, se
    corrige com OUTRA anotacao, que diz o que a anterior tinha de errado. Uma
    tabela onde a margem some por um clique nao serve de prova de nada.

FUNDAMENTO
    Codigo Civil, art. 682, I e II (extincao do mandato por revogacao e por
        renuncia) e arts. 655 e 1.289.
    Lei 8.935/1994, art. 6º, II (conservar os originais e expedir copias
        FIDEDIGNAS) e art. 30, I (manter em ordem os livros).
    Codigo de Normas do Foro Extrajudicial do Maranhao — Provimento TJMA n. 28,
        de 23/04/2026, Secao X do Capitulo IV, "Da Procuracao, do
        Substabelecimento, da Revogacao e da Renuncia de Mandato", arts. 831 a
        833, que trata os quatro atos como um conjunto; e a Secao XV, "Do
        Traslado e da Certidao", arts. 849 a 851.

        As duas secoes e o intervalo estao conferidos contra o sumario oficial
        do Provimento 28/2026. O TEOR dos artigos nao foi lido — o PDF trunca
        antes do Capitulo IV. Por isso este modulo cita a secao, e nao afirma o
        que cada artigo diz.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from notas_livro import LIVRO_DO_ATO
from notas_schema import (ANOTACAO_ENCERRA, ATO_PEDE_ANOTACAO, TIPOS_ANOTACAO,
                          TIPOS_ATO)


class AnotacaoError(ValueError):
    """Regra de anotacao violada. A rota trata com flash, nao com HTTP 500."""


# Como cada tipo de anotacao se escreve na margem. O sujeito e SEMPRE o ato
# anotado: quem le a margem da procuracao quer saber o que aconteceu com ELA.
_VERBO = {
    "REVOGACAO": "REVOGADA",
    "RENUNCIA": "EXTINTA POR RENÚNCIA DO MANDATÁRIO",
    "SUBSTABELECIMENTO": "SUBSTABELECIDA",
    "RETIFICACAO": "RETIFICADA",
    "ADITAMENTO": "ADITADA",
    "CANCELAMENTO": "CANCELADA",
    "ORDEM_JUDICIAL": "ANOTADA POR ORDEM JUDICIAL",
    "OUTRA": "ANOTADA",
}


def _dia(iso: Any) -> str:
    """`2026-08-17` -> `17/08/2026`. Devolve o que veio, se nao for data."""
    texto = str(iso or "")[:10]
    try:
        from datetime import date as _date
        return _date.fromisoformat(texto).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return texto


def texto_padrao(tipo: str, ato_novo: Any = None, sv: dict | None = None,
                 data: str | None = None, externa: bool = False,
                 serventia_externa: str | None = None,
                 cns_externa: str | None = None) -> str:
    """A frase que vai para a margem.

    Diz TRES coisas, que sao as que quem le a margem precisa: o que aconteceu,
    por qual ato, e onde esse ato esta. Sem as tres, a anotacao obriga a
    procurar — e anotacao que obriga a procurar nao cumpre o seu papel.
    """
    sv = sv or {}
    verbo = _VERBO.get(tipo, _VERBO["OUTRA"])
    if externa:
        onde = (serventia_externa or "").strip() or "serventia não informada"
        if (cns_externa or "").strip():
            onde += f", CNS {cns_externa.strip()}"
        origem = f"por ato lavrado em {onde}"
    else:
        origem = f"por ato lavrado nesta {sv.get('unit_name', 'Serventia')}"

    partes = [f"{verbo} {origem}"]
    if ato_novo is not None:
        a = dict(ato_novo)
        rotulo = TIPOS_ATO.get(a.get("tipo"), a.get("tipo") or "ato")
        detalhe = [f"em {_dia(a.get('data'))}", f"— {rotulo}"]
        if a.get("livro"):
            folha = a.get("folha") or "—"
            fim = a.get("folha_final")
            detalhe.append(f", Livro {a['livro']}, folha {folha}"
                           + (f" a {fim}" if fim and fim != folha else ""))
        if a.get("termo"):
            detalhe.append(f", termo nº {a['termo']}")
        elif a.get("numero_ordem"):
            detalhe.append(f", nº de ordem {a['numero_ordem']}")
        if a.get("selo"):
            detalhe.append(f", selo {a['selo']}")
        partes.append(" ".join(detalhe).replace(" ,", ","))
    elif data:
        partes.append(f"em {_dia(data)}")

    texto = " ".join(partes).strip()
    return re.sub(r"\s+", " ", texto).rstrip(".") + "."


def do_ato(con: sqlite3.Connection, ato_id: int) -> list[dict]:
    """As anotacoes de um ato, da mais antiga para a mais nova.

    Ordem cronologica e a ordem da margem do livro: a segunda anotacao vem
    depois da primeira porque foi escrita depois, e pode corrigi-la.
    """
    return [dict(r) for r in con.execute(
        """SELECT n.*, a.tipo tipo_ato_relacionado, a.livro livro_relacionado,
                  a.folha folha_relacionada, a.termo termo_relacionado
           FROM nt_ato_anotacoes n
           LEFT JOIN nt_atos a ON a.id = n.ato_relacionado_id
           WHERE n.ato_id = ?
           ORDER BY n.data, n.id""", (ato_id,))]


def anotar(con: sqlite3.Connection, ato_id: int, tipo: str, agora: str,
           *, texto: str | None = None, data: str | None = None,
           selo: str | None = None, ato_relacionado_id: int | None = None,
           lavrado_por: str | None = None, criado_por: str | None = None,
           sv: dict | None = None, externa: bool = False,
           serventia_externa: str | None = None,
           cns_externa: str | None = None) -> dict:
    """Escreve a anotacao a margem e aplica o efeito dela sobre o ato.

    Roda dentro da transacao do chamador, no molde da casa. Devolve o que foi
    escrito, para o `audit()` que vem DEPOIS de fechar o `with`.
    """
    tipo = (tipo or "").upper()
    if tipo not in TIPOS_ANOTACAO:
        raise AnotacaoError(f"Tipo de anotação desconhecido: {tipo!r}.")

    ato = con.execute("SELECT * FROM nt_atos WHERE id=?", (ato_id,)).fetchone()
    if not ato:
        raise AnotacaoError("Ato não encontrado.")
    if (ato["situacao"] or "") == "EM_LAVRATURA":
        # A margem e do livro. Ato que nao esta no livro nao tem margem.
        raise AnotacaoError("Este ato ainda não foi lançado no livro. Não há "
                            "margem onde anotar.")

    relacionado = None
    if ato_relacionado_id:
        if int(ato_relacionado_id) == int(ato_id):
            raise AnotacaoError("Um ato não se anota a si mesmo.")
        relacionado = con.execute("SELECT * FROM nt_atos WHERE id=?",
                                  (ato_relacionado_id,)).fetchone()
        if not relacionado:
            raise AnotacaoError("O ato que gerou a anotação não foi encontrado.")

    corpo = (texto or "").strip() or texto_padrao(
        tipo, relacionado, sv, data, externa, serventia_externa, cns_externa)
    quando = (data or "").strip()[:10] or (
        relacionado["data"] if relacionado else agora[:10])

    # DUPLICATA SEM ATO RELACIONADO.
    #
    # O `ux_nt_anotacao_par` e parcial (`WHERE ato_relacionado_id IS NOT NULL`)
    # e por isso nao alcanca a anotacao escrita a mao — que e justamente a que
    # tem um botao para clicar duas vezes. Tres cliques produziam tres linhas
    # iguais na margem, transcritas no traslado como "1. ... 2. ... 3. ...", e
    # sem como apagar.
    if not ato_relacionado_id:
        igual = con.execute(
            """SELECT id FROM nt_ato_anotacoes
               WHERE ato_id=? AND tipo=? AND data=? AND texto=?""",
            (ato_id, tipo, quando, corpo)).fetchone()
        if igual:
            raise AnotacaoError("Esta anotação já está na margem deste ato.")

    try:
        cur = con.execute(
            """INSERT INTO nt_ato_anotacoes
               (ato_id, data, tipo, texto, selo, ato_relacionado_id,
                lavrado_por, criado_por, origem_externa, serventia_externa,
                cns_externa, criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ato_id, quando, tipo, corpo,
             (selo or "").strip().upper() or
             (relacionado["selo"] if relacionado else None),
             ato_relacionado_id, lavrado_por, criado_por,
             1 if externa else 0,
             (serventia_externa or "").strip() or None,
             (cns_externa or "").strip() or None, agora))
    except sqlite3.IntegrityError:
        # `ux_nt_anotacao_par`: a mesma anotacao, do mesmo ato, ja esta na
        # margem. Clicar duas vezes nao escreve duas vezes.
        raise AnotacaoError(
            "Esta anotação já está na margem deste ato.") from None

    # O EFEITO DA ANOTACAO SOBRE A SITUACAO DO ATO.
    #
    # `sem_efeito_motivo` e SOBRESCRITO, nao preservado. A tela mostra esse
    # campo no aviso vermelho do topo: guardar o motivo antigo ao lado da
    # situacao nova faz a tela dizer que o ato foi revogado por um motivo que
    # nao e o da revogacao. O motivo velho nao se perde — ele esta na anotacao
    # anterior, que continua na margem, e a margem e o registro.
    nova_situacao = ANOTACAO_ENCERRA.get(tipo)
    mudou = False
    avisa = None
    if nova_situacao:
        atual = (ato["situacao"] or "")
        if atual == "LAVRADO":
            con.execute(
                """UPDATE nt_atos SET situacao=?, revogado_em=?, revogado_por=?,
                       sem_efeito_motivo=? WHERE id=?""",
                (nova_situacao, quando, criado_por or lavrado_por, corpo, ato_id))
            mudou = True
        elif atual != nova_situacao:
            # Ja estava fora de vigor por outra causa. A anotacao entra na
            # margem — o livro registra tudo o que aconteceu —, mas a situacao
            # NAO regride nem troca em silencio.
            avisa = (f"O ato já estava como "
                     f"{atual.replace('_', ' ').lower()}; a anotação entrou na "
                     f"margem e a situação não mudou.")

    return {"anotacao_id": int(cur.lastrowid), "ato_id": ato_id, "tipo": tipo,
            "data": quando, "texto": corpo,
            "ato_relacionado_id": ato_relacionado_id,
            "aviso": avisa,
            "situacao_nova": nova_situacao if mudou else None}


# ------------------------------------------------------- o ato anterior

# O que cada ato pode desfazer. Sem esta lista, "unico candidato" quer dizer
# apenas "o unico ato do acervo INTEIRO que por acaso esta naquele numero de
# livro e naquela folha" — e o livro 27 existe em toda serie.
#
# ISTO NAO E ZELO. Numa revisao adversarial, uma revogacao de procuracao com
# `anterior_livro=27, anterior_folha=139` encontrou como "unico candidato" uma
# ESCRITURA de compra e venda de R$ 150.000 no livro 27 de escrituras, marcou-a
# como REVOGADA e escreveu na margem dela uma anotacao que sai em todo traslado
# — enquanto a procuracao que se queria revogar continuou intacta, e o ato
# sumiu da lista de pendentes. Anotacao nao se apaga.
ALVO_DA_ANOTACAO = {
    "REVOGACAO": ("PROCURACAO", "PROCURACAO_PREVIDENCIARIA", "SUBSTABELECIMENTO"),
    "RENUNCIA": ("PROCURACAO", "PROCURACAO_PREVIDENCIARIA", "SUBSTABELECIMENTO"),
    "SUBSTABELECIMENTO": ("PROCURACAO", "PROCURACAO_PREVIDENCIARIA"),
}


def _mesma_serventia(ato: dict, sv: dict) -> bool:
    """O ato anterior esta NESTE acervo?

    Tres fontes, na ordem de confianca: o CNS, o nome do cartorio, e o silencio.

    O silencio conta a favor porque o acervo do E-Oficio nao trouxe
    `anterior_cns` em ato nenhum — a coluna nem esta na lista de campos da
    importacao. Exigir CNS preenchido desligaria a anotacao automatica para
    todas as 213 procuracoes importadas, que sao justamente as que se revogam.

    Mas o silencio so conta a favor quando NADA aponta para fora: havendo nome
    de cartorio, ele tem de ser o nosso.
    """
    cns_anterior = re.sub(r"\D", "", str(ato.get("anterior_cns") or ""))
    nosso = re.sub(r"\D", "", str((sv or {}).get("ri_cns") or ""))
    if cns_anterior:
        if not nosso:
            # Nao sabemos quem somos. Um CNS informado, sem termo de
            # comparacao, e motivo para NAO adivinhar.
            return False
        return cns_anterior.lstrip("0") == nosso.lstrip("0")

    cartorio = (ato.get("anterior_cartorio") or "").strip().upper()
    if cartorio in ("", "-", "—"):
        return True
    nome = str((sv or {}).get("unit_name") or "").strip().upper()
    # Compara com o nome EM USO, das configuracoes — nao com uma constante.
    # Renomear a serventia na tela nao pode desligar o reconhecimento.
    return bool(nome) and cartorio == nome


def localizar_ato_anterior(con: sqlite3.Connection, ato: Any,
                           sv: dict | None = None) -> sqlite3.Row | None:
    """Acha, no acervo desta serventia, o ato que o novo revoga ou substabelece.

    Procura pelos campos `anterior_*`, que ja existiam para a remessa a CENSEC.
    Quatro cautelas, e cada uma tirou um falso positivo real:

      1. so procura quando o ato anterior E DESTA serventia (`_mesma_serventia`);
      2. so aceita candidato do TIPO que aquele ato pode desfazer — revogacao
         de mandato nao alcanca escritura nem testamento;
      3. so aceita candidato da mesma SERIE DE LIVRO. Livro 27 de escrituras e
         livro 27 de procuracoes sao dois livros de papel diferentes, e o
         importador do E-Oficio joga os dois numeros na mesma coluna `livro`;
      4. so devolve quando sobra UM. Havendo dois — o que o acervo tem, nos
         pares da mesma folha do livro 27 — devolve None e deixa a escolha para
         quem sabe. Anotar a margem do ato errado e pior do que nao anotar.
    """
    a = dict(ato)
    if a.get("anterior_ato_id"):
        return con.execute("SELECT * FROM nt_atos WHERE id=?",
                           (a["anterior_ato_id"],)).fetchone()

    if not _mesma_serventia(a, sv or {}):
        return None

    tipos = ALVO_DA_ANOTACAO.get((a.get("tipo") or "").upper())
    if not tipos:
        return None
    # A serie esperada e a do ATO ALVO, nao a do ato novo. Substabelecimento
    # mora no livro de substabelecimentos e alcanca procuracao, que mora no de
    # procuracoes — sao livros diferentes por desenho.
    series_esperadas = {LIVRO_DO_ATO[x] for x in tipos if x in LIVRO_DO_ATO}

    livro = (a.get("anterior_livro") or "").strip()
    folha = (a.get("anterior_folha") or "").strip()
    if not livro or not folha:
        return None

    marcas = ",".join("?" for _ in tipos)
    achados = [r for r in con.execute(
        f"""SELECT a.*, l.tipo serie_do_livro FROM nt_atos a
            LEFT JOIN nt_livros l ON l.id = a.livro_id
            WHERE a.id <> ? AND a.situacao <> 'EM_LAVRATURA'
              AND a.tipo IN ({marcas})
              AND REPLACE(UPPER(TRIM(COALESCE(a.livro,''))),'-','') = ?
              AND UPPER(TRIM(COALESCE(a.folha,''))) = ?""",
        [a["id"], *tipos, livro.upper().replace("-", ""), folha.upper()])]

    # Cautela 3: quando o candidato tem livro identificado, a serie dele tem de
    # ser a mesma. Sem livro identificado (acervo solto), o filtro de tipo ja
    # garante que e da familia das procuracoes.
    if series_esperadas:
        achados = [r for r in achados
                   if not r["serie_do_livro"]
                   or r["serie_do_livro"] in series_esperadas]

    return achados[0] if len(achados) == 1 else None


def anotar_ato_anterior(con: sqlite3.Connection, ato_id: int, sv: dict,
                        agora: str, usuario: str | None = None) -> dict | None:
    """Escreve sozinho a anotacao que o ato recem-lancado pede.

    Devolve None quando o ato nao pede anotacao, ou quando o ato anterior nao
    pode ser identificado com seguranca — e nesses casos ele fica na lista de
    `pendentes`, que e onde alguem resolve a mao.
    """
    ato = con.execute("SELECT * FROM nt_atos WHERE id=?", (ato_id,)).fetchone()
    if not ato:
        raise AnotacaoError("Ato não encontrado.")
    tipo_anotacao = ATO_PEDE_ANOTACAO.get((ato["tipo"] or "").upper())
    if not tipo_anotacao:
        return None

    anterior = localizar_ato_anterior(con, ato, sv)
    if anterior is None:
        return None

    if not ato["anterior_ato_id"]:
        con.execute("UPDATE nt_atos SET anterior_ato_id=? WHERE id=?",
                    (anterior["id"], ato_id))

    try:
        return anotar(con, anterior["id"], tipo_anotacao, agora,
                      ato_relacionado_id=ato_id, sv=sv,
                      lavrado_por=ato["lavrado_nome"], criado_por=usuario,
                      data=ato["data"])
    except AnotacaoError:
        # Ja anotada — o ato foi relancado ou alguem anotou a mao antes.
        return None


def vincular_anterior(con: sqlite3.Connection, ato_id: int, anterior_id: int,
                      sv: dict) -> dict:
    """Amarra o ato novo ao ato anterior escolhido a mao, e copia os dados.

    Copiar `anterior_livro`, `anterior_folha`, `anterior_data` e o CNS nao e
    redundancia: sao os campos que a remessa a CENSEC exige, e eles tem de
    sobreviver ao ato anterior — se um dia a linha dele sumir do banco, a
    remessa ja informada continua explicavel.
    """
    if int(ato_id) == int(anterior_id):
        raise AnotacaoError("Um ato não se vincula a si mesmo.")

    # REVINCULAR DEPOIS DE ANOTADO NAO SE FAZ.
    #
    # `vincular_anterior` sobrescreve `anterior_ato_id`, mas a anotacao ja
    # escrita na margem do primeiro alvo NAO sai — anotacao nao se apaga.
    # Clicar na linha errada da lista de candidatos, voltar e clicar na certa
    # — o gesto mais natural do balcao — deixava DUAS procuracoes revogadas, e
    # a errada invisivel, porque a tela da revogacao passa a mostrar so a nova.
    ja = con.execute(
        """SELECT ato_id FROM nt_ato_anotacoes WHERE ato_relacionado_id=?""",
        (ato_id,)).fetchall()
    if ja and any(int(r["ato_id"]) != int(anterior_id) for r in ja):
        outros = ", ".join(str(r["ato_id"]) for r in ja)
        raise AnotacaoError(
            f"Este ato já anotou a margem do ato nº {outros}. A anotação não se "
            f"apaga: para corrigir, anote à margem daquele ato uma retificação "
            f"dizendo o que houve, e só então vincule o ato certo.")

    anterior = con.execute("SELECT * FROM nt_atos WHERE id=?",
                           (anterior_id,)).fetchone()
    if not anterior:
        raise AnotacaoError("Ato anterior não encontrado.")
    if (anterior["situacao"] or "") == "EM_LAVRATURA":
        raise AnotacaoError("O ato anterior ainda está em lavratura.")
    con.execute(
        """UPDATE nt_atos SET anterior_ato_id=?, anterior_livro=?,
               anterior_folha=?, anterior_data=?, anterior_cns=?,
               anterior_cartorio=?, anterior_cidade=?, anterior_uf=?,
               anterior_livro_complemento=?, anterior_folha_complemento=?
           WHERE id=?""",
        (anterior["id"], anterior["livro"], anterior["folha"], anterior["data"],
         sv.get("ri_cns"), sv.get("unit_name"), sv.get("ri_cidade"),
         sv.get("ri_uf"), anterior["livro_complemento"],
         anterior["folha_complemento"], ato_id))
    return {"ato_id": ato_id, "anterior_ato_id": anterior["id"],
            "livro": anterior["livro"], "folha": anterior["folha"]}


def candidatos(con: sqlite3.Connection, busca: str, tipo_ato: str = "",
               limite: int = 20) -> list[dict]:
    """Procura o ato anterior por nome de parte, livro/folha, termo ou selo.

    O caso normal e revogar procuracao do acervo, de 2019, cujo unico dado que
    a pessoa traz e o nome dela. Por isso a busca por parte vem primeiro.
    """
    busca = (busca or "").strip()
    if len(busca) < 2:
        return []
    onde = ["a.situacao <> 'EM_LAVRATURA'"]
    args: list[Any] = []
    if tipo_ato:
        onde.append("a.tipo = ?")
        args.append(tipo_ato.upper())
    alvo = f"%{busca.upper()}%"
    onde.append("""(UPPER(COALESCE(a.interessado,'')) LIKE ?
                    OR UPPER(COALESCE(a.selo,'')) LIKE ?
                    OR UPPER(COALESCE(a.livro,'')) = ?
                    OR CAST(a.termo AS TEXT) = ?
                    OR CAST(a.numero_ordem AS TEXT) = ?
                    OR EXISTS (SELECT 1 FROM nt_ato_partes p
                               WHERE p.ato_id = a.id
                                 AND UPPER(COALESCE(p.nome,'')) LIKE ?))""")
    args += [alvo, alvo, busca.upper(), busca, busca, alvo]
    linhas = con.execute(
        f"""SELECT a.*, (SELECT GROUP_CONCAT(p.nome, ' / ') FROM nt_ato_partes p
                         WHERE p.ato_id = a.id AND p.testemunha=0) nomes,
                   (SELECT COUNT(*) FROM nt_ato_anotacoes n
                    WHERE n.ato_id = a.id) anotacoes
            FROM nt_atos a WHERE {' AND '.join(onde)}
            ORDER BY a.data DESC, a.id DESC LIMIT ?""", args + [limite])
    return [dict(r) for r in linhas]


def pendentes(con: sqlite3.Connection) -> list[dict]:
    """Atos lavrados que pedem anotacao a margem e ainda nao a produziram.

    E a pergunta da correicao: "toda revogacao lavrada foi anotada na margem
    da procuracao que ela revoga?". Enquanto a resposta nao for "todas", a
    lista diz quais faltam e por que — sem ato anterior informado, ou com ato
    anterior de outra serventia, que se anota por oficio e nao por aqui.
    """
    tipos = tuple(ATO_PEDE_ANOTACAO)
    marcas = ",".join("?" for _ in tipos)
    linhas = con.execute(
        f"""SELECT a.*, (SELECT GROUP_CONCAT(p.nome, ' / ') FROM nt_ato_partes p
                         WHERE p.ato_id = a.id AND p.testemunha=0) nomes
            FROM nt_atos a
            WHERE a.tipo IN ({marcas})
              AND a.situacao NOT IN ('EM_LAVRATURA', 'CANCELADO')
              AND NOT EXISTS (SELECT 1 FROM nt_ato_anotacoes n
                              WHERE n.ato_relacionado_id = a.id)
              -- Procuração de OUTRA serventia não se anota por aqui: a
              -- providência é a comunicação do art. 831, § 1º. Cumprida ela,
              -- o ato sai desta lista (relato #129, 14/10/2026).
              AND NOT EXISTS (SELECT 1 FROM nt_comunicacoes_origem c
                              WHERE c.ato_id = a.id
                                AND c.situacao = 'CUMPRIDA')
            ORDER BY a.data DESC, a.id DESC""", tipos)
    fora = []
    for r in linhas:
        d = dict(r)
        if d.get("anterior_ato_id"):
            d["motivo"] = "vinculado, mas sem anotação escrita"
        elif not (d.get("anterior_livro") or "").strip():
            d["motivo"] = "o ato anterior não foi informado"
        elif (d.get("anterior_cns") or "").strip():
            d["motivo"] = "o ato anterior é de outra serventia — anote por ofício"
        else:
            d["motivo"] = "o ato anterior não foi localizado no acervo"
        fora.append(d)
    return fora
