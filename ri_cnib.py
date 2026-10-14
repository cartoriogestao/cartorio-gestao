"""A indisponibilidade da CNIB: avisar, PREPARAR a averbacao, e esperar o okay.

DE ONDE VEIO
    O oficial relatou, em 27/08/2026, que faltava a CNIB averbar sozinha a
    indisponibilidade. Perguntei em 28/08 se ela devia averbar automatico, e
    ele respondeu com uma terceira coisa, que e melhor que as duas que eu
    tinha oferecido:

        «avisar e preparar a averbacao, ficando pendente okay do cartorio»

    O trabalho fica pronto; a decisao continua sendo de quem assina.

POR QUE NAO SE AVERBA SOZINHO — e o numero decide
    Medido em 28/08/2026, entre as 50.054 pessoas das ordens do CNIB e as
    partes das 1.701 matriculas desta casa:

        por CPF/CNPJ ....... 0 pessoas batem
        por nome ........... 6 pessoas, em 10 matriculas

    E os seis sao «ANTONIO ALVES DOS SANTOS», «ANTONIO PEREIRA DA SILVA»,
    «ULISSES ALVES DOS SANTOS», «MAURO LUIZ DA SILVA» e dois «JOAO PEREIRA
    DA SILVA» — e as ordens vem do TJSC, do TJPR, do TRF6 e de vara do Rio
    Grande do Sul. Homonimo nao e a excecao: e a regra.

    Averbar indisponibilidade na matricula do homonimo tira de um inocente o
    direito de dispor do imovel dele — e nao se desfaz sozinho: para sair,
    precisa de ordem de cancelamento pela mesma via. E a mesma razao pela qual
    a lista de atencao para fraudes avisa e nao trava.

    > **E EU MEDI ESSE NUMERO ERRADO ANTES.** Na primeira contagem, feita a mao
    > comparando `nome.strip().upper()` dos dois lados, deram QUATRO. Sao seis:
    > a comparacao certa e a normalizada, sem acento e sem espaco sobrando, que
    > e a que o sistema faz. Contar de um jeito e o programa comparar de outro
    > da um numero que parece medicao e nao e.

O QUE ESTAVA DESLIGADO, E CALADO
    Enquanto se construia isto apareceram DOIS defeitos em `consultar_cnib`,
    que e a funcao que a ficha da matricula usa para avisar. Cada um sozinho ja
    bastava para o aviso por nome nunca sair; ver o comentario dela, em
    `ri_schema.py`. Com os dois de pe o alerta desta casa nunca apareceu para
    ninguem, porque por documento o numero de achados e zero.

O QUE ESTE MODULO NAO FAZ
    Nao lavra ato. Ele prepara o TEOR e devolve; quem lavra e a tela de ato do
    Registro de Imoveis, que ja existe, ja tem a corrente de hash, o selo, os
    emolumentos e o delegatario. Um atalho de um clique pularia os quatro.

DECISAO SE GRAVA, E POR ISSO A LISTA DIMINUI
    «Aviso sem saida e aviso que fica para sempre»: na terceira vez que a
    mesma linha aparece, ninguem le mais. Quem decidir que nao e a mesma
    pessoa escreve o porque, e aquela linha nao volta.
"""
from __future__ import annotations

import re
import sqlite3

import ri_modelos_atos as MOD
import ri_numeros_do_teor as NUMT
from ri_odt import rotulo_ato
from ri_schema import consultar_cnib, matricula_de_acervo

CODIGO_DO_MODELO = "AV-INDISPONIBILIDADE"

# O marcador Jinja do modelo — `{{ rotulo }}`, `{{ protocolo_frase }}`.
_MARCA_JINJA = re.compile(r"\{\{\s*(\w+)\s*\}\}")

# As duas saidas possiveis. Nao ha uma terceira chamada «depois»: pendencia
# que se pode adiar num clique e pendencia que se adia para sempre.
AVERBADA = "AVERBADA"
NAO_E_A_PESSOA = "NAO_E_A_PESSOA"
ORDEM_BAIXADA = "ORDEM_BAIXADA"


class CnibError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


def _dia(iso) -> str:
    """`2023-03-19` -> `19/03/2023`.

    A DATA NAO SAI EM FORMA ISO NUM TEXTO DE AVERBACAO. O banco guarda em ISO
    porque assim ela ordena; o livro le em portugues. Data que nao se sabe ler
    fica como esta — inventar formato para o que nao e data seria esconder o
    problema dentro do ato.
    """
    from datetime import date as _date
    cru = str(iso or "").strip()
    try:
        d = _date.fromisoformat(cru[:10])
    except ValueError:
        return cru
    # A data se monta a mao, e nao com o formatador da biblioteca. O varredor
    # de portabilidade (`tests/test_portabilidade.py`) procura o NOME da funcao
    # no texto do arquivo, e nao sabe distinguir a do Python da do SQL — modulo
    # novo entra com teto zero, e um falso positivo aqui obrigaria a subir o
    # teto por um uso que nao e acoplamento nenhum. Tres campos formatados sao
    # mais baratos que uma excecao mal explicada.
    return f"{d.day:02d}/{d.month:02d}/{d.year:04d}"


def _documento(cru) -> str:
    """`00012345678` -> `000.123.456-78`; `00000012000116` -> CNPJ pontuado.

    O NUMERO NAO MUDA — muda so a pontuacao, que e como ele se le no livro. E
    o que nao tiver onze nem quatorze digitos sai como esta: pontuar o que nao
    se reconhece daria a um numero errado a aparencia de um CPF.
    """
    d = "".join(c for c in str(cru or "") if c.isdigit())
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return str(cru or "").strip()


def parte_fixa(con=None, matricula_id: int | None = None, *,
               numero: int | None = None) -> dict:
    """O que o modelo deixa em Jinja: `{{ rotulo }}` e `{{ protocolo_frase }}`.

    O DEFEITO QUE ISTO FECHA — 06/10/2026, achado pela conferência diária do
    gestor (regra MODELO_NAO_PREENCHIDO). `teor_preparado` passava o modelo
    só por `ri_modelos_atos.preencher`, que troca os `[COLCHETES]` e deixa o
    Jinja de propósito — quem resolve o Jinja nas telas é `render_modelo`, em
    `ri_web`, com o contexto da matrícula. Aqui ninguém o resolvia: as 11
    minutas de 04 e 06/10 nasceram com `{{ rotulo }}` e `{{ protocolo_frase }}`
    crus, e a rota de lavrar grava o teor como vem — o marcador iria ao livro
    e à corrente de hash.

    A RÉGUA É A DA ROTA DE LAVRAR, e não uma parecida:
      - o NÚMERO, em ficha estruturada, é `ri_numeros_do_teor.piso_do_proximo`
        — o mesmo que `ri_lavrar_ato` usa; em ficha de ACERVO o número vem do
        livro físico (a rota o exige à mão), e por isso aqui ele NÃO se
        calcula: fica `[NUMERO DO ATO]` visível, como todo campo que o
        sistema não sabe. `numero` explícito (o pretendido, ou o que o oficial
        informou do livro) ganha dos dois;
      - o RÓTULO sai de `ri_odt.rotulo_ato`, a forma da ficha (AV-06/1840);
      - a FRASE DO PROTOCOLO é a da prenotação ABERTA mais recente da
        matrícula, a mesma consulta de `ri_web._contexto_modelo`; sem ela,
        `[INFORMAR O PROTOCOLO].`, o mesmo texto que a tela usa.

    SÓ LÊ. Não consome número, não toma prenotação.
    """
    m = None
    if con is not None and matricula_id is not None:
        con.row_factory = sqlite3.Row
        m = con.execute(
            "SELECT id, numero, tipo_ficha FROM ri_matriculas WHERE id=?",
            (int(matricula_id),)).fetchone()
    n = int(numero) if numero else None
    if n is None and m is not None and not (
            m["tipo_ficha"] == "ACERVO" or matricula_de_acervo(m["numero"])):
        n = NUMT.piso_do_proximo(con, int(m["id"]))["proximo"]
    if m is None:
        rotulo = "[ROTULO DO ATO]"
    elif n:
        rotulo = rotulo_ato("AV", n, m["numero"])
    else:
        rotulo = f"AV-[NUMERO DO ATO]/{m['numero']}"

    protocolo = None
    if m is not None:
        protocolo = con.execute(
            """SELECT numero, data_prenotacao FROM ri_protocolos
                WHERE matricula_id=? AND situacao='ABERTO'
                ORDER BY numero DESC LIMIT 1""", (int(m["id"]),)).fetchone()
    frase = (f"PROTOCOLO N. {protocolo['numero']}, DE "
             f"{_dia(protocolo['data_prenotacao'])}."
             if protocolo else "[INFORMAR O PROTOCOLO].")
    return {"rotulo": rotulo, "protocolo_frase": frase, "numero": n,
            "protocolo": (protocolo["numero"] if protocolo else None)}


def teor_preparado(ordem: dict, con=None, matricula_id: int | None = None, *,
                   numero: int | None = None) -> str:
    """O texto da averbacao, com o que a ordem da CNIB traz ja no lugar.

    O QUE NAO SE SOUBER CONTINUA APARECENDO COMO `[CAMPO]`, e isso e de
    proposito — e o que `ri_modelos_atos.preencher` faz com todo modelo desta
    casa. Campo vazio tem de saltar aos olhos de quem confere, e nao sumir do
    texto: uma averbacao que diz «nos autos n. » sem numero e pior que uma que
    diz «nos autos n. [PROCESSO]», porque a primeira parece pronta.

    E O JINJA DO MODELO SAI RESOLVIDO, nunca cru — ver `parte_fixa`. A troca é
    feita no MODELO, antes de os dados da ordem entrarem: o que vem da CNIB é
    texto de fora e não passa por motor de modelo nenhum. Marcador que esta
    função não conhece recusa, em vez de seguir para a minuta.
    """
    modelo = MOD.por_codigo(CODIGO_DO_MODELO)
    if not modelo:
        raise CnibError(
            f"O modelo {CODIGO_DO_MODELO} não está no cadastro de modelos do "
            f"Registro de Imóveis. Sem ele não dá para preparar a averbação.")
    fixo = parte_fixa(con, matricula_id, numero=numero)

    def troca(achado):
        chave = achado.group(1)
        if chave not in ("rotulo", "protocolo_frase"):
            raise CnibError(
                f"O modelo {CODIGO_DO_MODELO} passou a usar «{{{{ {chave} }}}}», "
                f"que a preparação da CNIB não sabe preencher. A averbação não "
                f"foi preparada — corrija o modelo ou esta função.")
        return fixo[chave]

    corpo = _MARCA_JINJA.sub(troca, modelo["corpo"])
    if "{{" in corpo or "{%" in corpo:
        raise CnibError(
            f"O modelo {CODIGO_DO_MODELO} tem marcação de modelo que a "
            f"preparação da CNIB não sabe preencher. A averbação não foi "
            f"preparada.")
    return MOD.preencher(dict(modelo, corpo=corpo), {
        "protocolo_cnib": (ordem.get("protocolo_cnib") or "").strip(),
        "data": _dia(ordem.get("data_pedido")),
        "orgao_juizo": " — ".join(
            x for x in ((ordem.get("instituicao") or "").strip(),
                        (ordem.get("forum_vara") or "").strip()) if x),
        "processo": (ordem.get("processo") or "").strip(),
        "nome_do_atingido": (ordem.get("nome") or "").strip(),
        "cpf_cnpj": _documento(ordem.get("documento")),
    })


def chave_da_minuta(matricula_id: int, ordem: dict) -> str:
    return f"CNIB:{int(matricula_id)}:{ordem.get('protocolo_cnib') or ''}:{ordem.get('documento') or ''}"


def filtrar_pendentes(con, matricula_id: int, ordens: list[dict]) -> list[dict]:
    """Ocorrencias ainda sem decisao ou minuta efetivamente lavrada."""
    decisoes = {(r['protocolo_cnib'], r['pessoa_documento'] or '', r['pessoa_nome'] or '')
                for r in con.execute('SELECT * FROM ri_cnib_decisoes WHERE matricula_id=?',
                                     (int(matricula_id),)).fetchall()}
    lavradas = {r['origem_chave'] for r in con.execute(
        """SELECT m.origem_chave FROM ri_minutas m JOIN ri_atos a ON a.id=m.ato_id
           WHERE m.matricula_id=? AND m.situacao='LAVRADA'""",
        (int(matricula_id),)).fetchall()}
    return [o for o in ordens
            if (o.get('protocolo_cnib'), o.get('documento') or '', o.get('nome') or '') not in decisoes
            and chave_da_minuta(matricula_id, o) not in lavradas]


def resolver_ocorrencia(con, *, matricula_id: int, protocolo: str,
                        pessoa_nome: str, pessoa_documento: str,
                        decisao: str, motivo: str, quem: str, agora: str) -> int:
    """Resolve somente a ocorrencia desta ficha, com dados conferidos no banco."""
    if decisao not in (NAO_E_A_PESSOA, ORDEM_BAIXADA):
        raise CnibError("Escolha se nao e a mesma pessoa ou se a ordem foi baixada.")
    if len((motivo or '').strip()) < 10:
        raise CnibError("Descreva a conferencia e sua evidencia com pelo menos 10 caracteres.")
    if not con.execute('SELECT 1 FROM ri_matriculas WHERE id=?',
                       (int(matricula_id),)).fetchone():
        raise CnibError("Matricula nao encontrada.")
    identidade = (str(protocolo or '').strip(), str(pessoa_nome or '').strip(),
                  str(pessoa_documento or '').strip())
    partes = con.execute('SELECT nome,documento_numero FROM ri_partes WHERE matricula_id=?',
                          (int(matricula_id),)).fetchall()
    ordens = consultar_cnib(con, [p['documento_numero'] for p in partes],
                           [p['nome'] for p in partes])
    ordem = next((o for o in ordens if
                  (str(o.get('protocolo_cnib') or '').strip(),
                   str(o.get('nome') or '').strip(),
                   str(o.get('documento') or '').strip()) == identidade), None)
    if ordem is None:
        raise CnibError("Esta ocorrencia nao esta mais ativa para as partes desta matricula. Atualize a ficha.")
    existente = con.execute(
        """SELECT id,decisao FROM ri_cnib_decisoes WHERE matricula_id=? AND protocolo_cnib=?
           AND COALESCE(pessoa_nome,'')=? AND COALESCE(pessoa_documento,'')=?""",
        (int(matricula_id), *identidade)).fetchone()
    if existente:
        if existente['decisao'] != decisao:
            raise CnibError('Ja existe outra decisao registrada para esta ocorrencia. Consulte o historico.')
        return int(existente['id'])
    decisao_id = decidir(con, matricula_id=matricula_id, ordem=ordem,
                        decisao=decisao, motivo=motivo, ato_id=None, quem=quem, agora=agora)
    # Uma minuta da ocorrencia resolvida continua preservada para o historico,
    # mas sai da fila de lavratura. Atos lavrados e outras minutas nao mudam.
    import ri_minuta as MIN
    chave = chave_da_minuta(matricula_id, ordem)
    for m in con.execute("SELECT id FROM ri_minutas WHERE origem_chave=? AND situacao='A_REVISAR'",
                          (chave,)).fetchall():
        MIN.descartar(con, m['id'], motivo=f"CNIB {decisao}: {motivo}", agora=agora, usuario=quem)
    for t in con.execute("SELECT id FROM tasks WHERE source_ref=?", (chave,)).fetchall():
        con.execute('INSERT INTO task_history(task_id,ts,action,note) VALUES (?,?,?,?)',
                    (t['id'], agora, 'NOTA', f"CNIB: {decisao}. Conferencia por {quem}: {motivo}. Consulte a decisao na matricula."))
    return decisao_id


def pendentes(con) -> list[dict]:
    """As matriculas cujas partes batem com ordem ATIVA, e ainda sem decisao.

    A BUSCA E A MESMA DA FICHA — `consultar_cnib`, matricula por matricula.
    Uma segunda consulta «parecida», escrita aqui em SQL proprio, divergiria da
    da ficha no primeiro conserto, e as duas telas passariam a dizer coisas
    diferentes sobre a mesma pessoa. Custa uma consulta por matricula, e esta
    tela se abre uma vez por semana — nao e o laco do balcao.
    """
    ja = {(r["matricula_id"], r["protocolo_cnib"], (r["pessoa_documento"] or ""),
           (r["pessoa_nome"] or "")) for r in con.execute(
        "SELECT * FROM ri_cnib_decisoes")}

    achados = []
    # A MATRICULA ENCERRADA TAMBEM ENTRA, e isso e deliberado. Medido em
    # 28/08/2026: das 1.701, 1.700 estao ATIVA e 1 ENCERRADA. Encerrada quer
    # dizer que o imovel virou outra coisa — foi unificado, desmembrado —, e a
    # indisponibilidade acompanha o imovel, nao a ficha. Filtrar por situacao
    # esconderia justamente o caso em que ninguem esta olhando.
    # `fetchall` E NAO O CURSOR PREGUICOSO, e isso nao e estilo: o SQLite recusa
    # registrar funcao (`create_function`) enquanto ha comando em andamento, e
    # `consultar_cnib` registra a `nome_da_casa()` a cada chamada. Percorrendo
    # o cursor aberto, a primeira matricula ja estourava com «Error creating
    # function». Lendo as 1.701 de uma vez o laco fica livre — e 1.701 linhas
    # de tres colunas cabem na memoria sem pensar duas vezes.
    for m in con.execute("""SELECT id, numero, livro, situacao FROM ri_matriculas
                             ORDER BY id""").fetchall():
        partes = [dict(x) for x in con.execute(
            """SELECT nome, documento_numero FROM ri_partes
                WHERE matricula_id = ?""", (m["id"],)).fetchall()]
        if not partes:
            continue
        ordens = consultar_cnib(
                con,
                [x.get("documento_numero") for x in partes],
                [x.get("nome") for x in partes])
        for ordem in filtrar_pendentes(con, m["id"], ordens):
            chave = (m["id"], ordem.get("protocolo_cnib"),
                     ordem.get("documento") or "", ordem.get("nome") or "")
            if chave in ja:
                continue
            achados.append({
                "matricula_id": m["id"],
                "matricula_numero": m["numero"],
                "matricula_livro": m["livro"],
                "matricula_situacao": m["situacao"],
                "ordem": ordem,
                "criterio": ordem.get("criterio"),
                # O ALERTA POR DOCUMENTO VEM ANTES DO ALERTA POR NOME: documento
                # nao tem homonimo, nome tem. Sem essa ordem, os homonimos
                # afogam o achado que importa. Mesma regra da lista de fraudes.
                "peso": 0 if ordem.get("criterio") == "documento" else 1,
                "teor": teor_preparado(ordem, con, m["id"]),
            })
    achados.sort(key=lambda x: (x["peso"], x["matricula_numero"] or ""))
    return achados


def decidir(con, *, matricula_id: int, ordem: dict, decisao: str,
            motivo: str | None, ato_id: int | None, quem: str | None,
            agora: str) -> int:
    """Guarda o okay do cartorio sobre uma pendencia. Devolve o id da decisao.

    MOTIVO ESCRITO E OBRIGATORIO PARA DIZER «NAO E A PESSOA» — a mesma regra
    do usucapiao e da dispensa de item do rito. Dispensar e decisao de quem
    assina; ignorar nao e. E daqui a dois anos, numa correicao, a pergunta vai
    ser exatamente por que aquela ordem nao foi averbada.
    """
    if decisao not in (AVERBADA, NAO_E_A_PESSOA, ORDEM_BAIXADA):
        raise CnibError(f"«{decisao}» não é uma decisão que eu saiba registrar.")
    limpo = (motivo or "").strip()
    if decisao == NAO_E_A_PESSOA and len(limpo) < 10:
        raise CnibError(
            "Escreva por que esta ordem não atinge esta matrícula — o nome de "
            "quem confirmou, o documento conferido, o que separa as duas "
            "pessoas. Daqui a dois anos essa frase é a única coisa que vai "
            "explicar por que a indisponibilidade não foi averbada.")
    if decisao == ORDEM_BAIXADA and len(limpo) < 10:
        raise CnibError("Informe a evidencia da baixa da ordem, com pelo menos 10 caracteres.")
    cur = con.execute(
        """INSERT INTO ri_cnib_decisoes
              (matricula_id, protocolo_cnib, pessoa_nome, pessoa_documento,
               criterio, decisao, motivo, ato_id, decidido_por, decidido_em)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (int(matricula_id), (ordem.get("protocolo_cnib") or "").strip(),
         (ordem.get("nome") or "").strip(),
         (ordem.get("documento") or "").strip(),
         ordem.get("criterio"), decisao, limpo or None, ato_id, quem, agora))
    return int(cur.lastrowid)


COPIA_LOCAL = "COPIA_LOCAL"
CENTRAL = "CENTRAL"
NADA_CONSTA = "NADA_CONSTA"
POSITIVO = "POSITIVO"

# Configuracao da casa: "1" exige o protocolo da consulta na Central antes de
# lavrar alienacao/oneracao. Desligada, a consulta a copia local e gravada do
# mesmo jeito — so nao se trava o balcao.
CHAVE_EXIGIR_PROTOCOLO = "ri_cnib_exigir_protocolo_na_lavratura"


def exige_consulta(natureza_titulo, tipo: str) -> bool:
    """Alienacao ou oneracao do imovel (TJMA 506): transmissao ou onus."""
    import ri_naturezas as NAT
    import ri_onus as ONUS
    codigo = ONUS.codigo_da_natureza(natureza_titulo)
    if codigo is None:
        return False
    if codigo in ONUS.CODIGOS_DE_ONUS:
        return True
    return bool(NAT.POR_CODIGO[codigo][2])


def gravar_consulta_do_ato(con, *, ato_id: int, matricula_id: int,
                              ato_rotulo: str, base_ate,
                              protocolo_consulta: str | None,
                              quem: str | None, agora: str) -> dict:
    """Consulta a CNIB pelas partes do ato e pelos titulares ativos, e grava.

    Chamar DEPOIS de inserir as partes do ato, na mesma transacao: assim o
    transmitente (titular ativo) e o adquirente (parte do ato) entram juntos.
    Positivo nao trava — homonimo e a regra aqui (ver o topo do modulo).
    """
    import json
    partes = con.execute(
        """SELECT nome, documento_numero FROM ri_partes
            WHERE matricula_id = ? AND (ato_id = ? OR proprietario_ativo = 1)""",
        (int(matricula_id), int(ato_id))).fetchall()
    documentos = sorted({"".join(c for c in str(doc or "") if c.isdigit())
                         for _nome, doc in partes} - {""})
    nomes = sorted({(nome or "").strip() for nome, _doc in partes} - {""})
    ordens = consultar_cnib(con, documentos, nomes)
    protocolo = (protocolo_consulta or "").strip() or None
    linha = {
        "ato_id": int(ato_id), "matricula_id": int(matricula_id),
        "ato_rotulo": ato_rotulo,
        "fonte": CENTRAL if protocolo else COPIA_LOCAL,
        "base_ate": str(base_ate)[:10] if base_ate else None,
        "protocolo_consulta": protocolo,
        "documentos": documentos, "nomes": nomes,
        "resultado": POSITIVO if ordens else NADA_CONSTA,
        "ordens": [{"protocolo_cnib": o.get("protocolo_cnib"),
                    "nome": o.get("nome"), "documento": o.get("documento"),
                    "criterio": o.get("criterio")} for o in ordens],
        "consultado_por": quem, "consultado_em": agora,
    }
    cur = con.execute(
        """INSERT INTO ri_atos_cnib
              (ato_id, matricula_id, ato_rotulo, fonte, base_ate,
               protocolo_consulta, documentos, nomes, resultado, ordens,
               consultado_por, consultado_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (linha["ato_id"], linha["matricula_id"], ato_rotulo, linha["fonte"],
         linha["base_ate"], protocolo,
         json.dumps(documentos, ensure_ascii=False),
         json.dumps(nomes, ensure_ascii=False), linha["resultado"],
         json.dumps(linha["ordens"], ensure_ascii=False), quem, agora))
    linha["id"] = int(cur.lastrowid)
    return linha


def soltar_do_ato(con, ato_id: int) -> None:
    """O ato saiu do livro (suspenso ou expurgado): a consulta fica na ficha."""
    con.execute("UPDATE ri_atos_cnib SET ato_id = NULL WHERE ato_id = ?",
                (int(ato_id),))


def consultas_da_matricula(con, matricula_id: int) -> dict[int, dict]:
    """Ultima consulta gravada por ato, para a ficha mostrar ao lado do ato."""
    saida: dict[int, dict] = {}
    cur = con.execute(
        """SELECT * FROM ri_atos_cnib
            WHERE matricula_id = ? AND ato_id IS NOT NULL
            ORDER BY id""", (int(matricula_id),))
    colunas = [d[0] for d in cur.description]
    for r in cur.fetchall():
        linha = dict(zip(colunas, r))
        saida[int(linha["ato_id"])] = linha
    return saida


def recado_da_consulta(linha: dict) -> str:
    """Frase curta para o flash depois de lavrar."""
    if not linha:
        return ""
    base = (f"protocolo da Central {linha['protocolo_consulta']}"
            if linha["fonte"] == CENTRAL
            else f"cópia local até {_dia(linha['base_ate'])}"
            if linha["base_ate"] else "cópia local (sem data de base)")
    if linha["resultado"] == POSITIVO:
        return (f" CNIB: {len(linha['ordens'])} ordem(ns) ativa(s) coincidem "
                f"com as partes ({base}) — confira em «CNIB — o que espera seu "
                f"okay»; a consulta ficou gravada no ato.")
    return f" CNIB consultada e gravada no ato: nada consta ({base})."


def decisoes_da_matricula(con, matricula_id: int) -> list[dict]:
    """O que ja se decidiu sobre esta matricula — para a ficha mostrar.

    A ficha avisa que ha ordem; quem ja resolveu precisa ver que resolveu, e
    quem resolveu, e quando. Sem isso o proximo abre a ficha, ve o mesmo aviso
    vermelho e vai conferir de novo o que ja foi conferido.
    """
    return [dict(r) for r in con.execute(
        """SELECT * FROM ri_cnib_decisoes WHERE matricula_id = ?
            ORDER BY id DESC""", (int(matricula_id),))]
