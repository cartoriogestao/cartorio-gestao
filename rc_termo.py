"""O TERMO do Registro Civil — o texto que vai escrito no livro.

    «vamos seguir no desenvolvimento do nosso módulo maduro e completo de RCPN»
    — o oficial, 29/08/2026

O BURACO QUE ESTE MODULO FECHA
    Este projeto construiu a **certidão** do RCPN — montada dos campos, no
    modelo nacional do CNJ — e nunca construiu o **termo**, que é o que se
    escreve no livro. O motivo estava registrado e era falso por omissão: «os
    244 assentos do acervo não têm teor nenhum».

    Em 29/08/2026 se descobriu **por quê**: o E-Ofício não guardava o teor — ele
    o montava do modelo na hora de imprimir. O termo existia; só não estava no
    banco. Os treze modelos dele estão no acervo, e o de nascimento usa **62
    campos**.

    Sétima vez neste projeto que «a coluna está vazia» não queria dizer «a coisa
    não acontecia».

O TERMO E A CERTIDAO SAO PAPEIS DIFERENTES, E ISSO DECIDE O DESENHO
    | | o termo | a certidão |
    |---|---|---|
    | onde vive | **no livro**, escrito uma vez | fora, quantas vezes se pedir |
    | quando | na lavratura | a qualquer tempo |
    | quem assina | o oficial **e o declarante** | só o oficial |
    | se muda | **nunca** — averba-se ao lado | a próxima sai já corrigida |

    Por isso o termo **congela**: `rc_assentos.teor` guarda o texto montado, e
    ele não se remonta depois. Remontar faria o livro de hoje discordar do papel
    que o declarante assinou — e é o papel assinado que vale.

DE ONDE VEM O MODELO
    De `modelos_da_casa`, o catálogo do relato #28: **o padrão da base é o
    piso e o ajuste da casa vence**. O corpo de cada termo é o papel
    `RC_TERMO_*` (`modelos_padrao/rcpn/`), e as frases ocasionais são peças
    dele, montadas por `rc_modelos_do_livro`. Os três modelos Jinja lidos dos
    treze do E-Ofício (`MODELO_TERMO_*`), com o `contexto()` que os
    preenchia, saíram no LF06C (19/10/2026): ninguém os usava, e eram o
    catálogo outra vez, noutro formato.

    **O CABEÇALHO NÃO VEIO JUNTO, E É DELIBERADO.** Os modelos do E-Ofício
    trazem o oficial impresso no texto, e dois deles trazem a **oficial
    anterior**, com endereço, telefone e CEP antigos. Copiar o cabeçalho traria
    o oficial de ontem para dentro do sistema de hoje — o «carimbo que mente»
    outra vez. Quem responde pela serventia sai da regra viva, que mora num
    lugar só.
"""
from __future__ import annotations

import sqlite3

import rc_assento as ASSENTO
import rc_textos as TEXTOS
from bd_nativo import banco


class TermoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


# --------------------------------------------------------------- os modelos

# A especie manda no modelo, e nao o chamador. E a mesma regra da serie
# (`rc_assento.SERIE_DA_ESPECIE`): deixar o balcao escolher o modelo seria
# deixar lavrar um obito com o texto de nascimento, e o defeito so apareceria
# na certidao, meses depois.
MODELO_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "RC_TERMO_NASCIMENTO",
    "NATIMORTO": "RC_TERMO_NASCIMENTO",
    "OBITO": "RC_TERMO_OBITO",
    "CASAMENTO": "RC_TERMO_CASAMENTO",
    "CASAMENTO_RELIGIOSO": "RC_TERMO_CASAMENTO",
    # Livro E — um modelo só (ordem do oficial: «livro e usa o mesmo modelo»).
    "AUSENCIA": "RC_TERMO_LIVRO_E",
    "INTERDICAO": "RC_TERMO_LIVRO_E",
    "TUTELA": "RC_TERMO_LIVRO_E",
    "EMANCIPACAO": "RC_TERMO_LIVRO_E",
    "UNIAO_ESTAVEL": "RC_TERMO_LIVRO_E",
    "OPCAO_NACIONALIDADE": "RC_TERMO_LIVRO_E",
    "OUTRO": "RC_TERMO_LIVRO_E",
}


def especies_com_termo() -> tuple[str, ...]:
    """As espécies para as quais existe modelo de termo. Só calcula.

    Inclui as do Livro E (ausência, interdição, tutela, emancipação, união
    estável, opção de nacionalidade e outro): **um modelo compartilhado**,
    ordem do oficial em 07/09/2026 — «livro e usa o mesmo modelo». O título
    do ato muda pela espécie; o corpo é o de `RC_TERMO_LIVRO_E`.
    """
    return tuple(sorted(set(MODELO_DA_ESPECIE)))


# ------------------------------------------------------------ a qualificação
#
# «FULANO, brasileiro, lavrador, portador do RG n.o X, inscrito no CPF n.o Y,
#  natural de Z, nascido aos W, residente e domiciliado em V»
#
# ELA SE MONTA DO QUE EXISTE, E PULA O QUE FALTA. O termo do E-Oficio escrevia
# a frase inteira com os campos vazios no meio — sai «portador do RG n.o ,
# inscrito no CPF n.o ,» —, e papel assinado com buraco no meio e pior que papel
# sem a informacao: ele AFIRMA que ha um RG e nao diz qual.


def qualificacao(pessoa: dict | None) -> str:
    """A qualificação de uma pessoa, com o que houver. Só calcula."""
    if not pessoa:
        return ""
    p = dict(pessoa)
    partes: list[str] = []

    if p.get("nacionalidade"):
        partes.append(str(p["nacionalidade"]).strip().lower())
    if p.get("estado_civil"):
        partes.append(str(p["estado_civil"]).strip().lower())
    if p.get("profissao"):
        partes.append(str(p["profissao"]).strip().lower())

    doc_tipo = str(p.get("documento_tipo") or "").strip().upper()
    doc_num = str(p.get("documento_numero") or "").strip()
    if doc_num:
        rotulo = {"CPF": "inscrito(a) no CPF n.º",
                  "RG": "portador(a) do RG n.º"}.get(doc_tipo,
                                                     f"portador(a) de {doc_tipo or 'documento'} n.º")
        pedaco = f"{rotulo} {doc_num}"
        if p.get("documento_orgao"):
            pedaco += f", expedido por {p['documento_orgao']}"
        partes.append(pedaco)

    natural = ", ".join(x for x in (p.get("naturalidade_cidade"),
                                    p.get("naturalidade_uf")) if x)
    if natural:
        partes.append(f"natural de {natural}")
    if p.get("data_nascimento"):
        partes.append(f"nascido(a) aos {p['data_nascimento']}")

    onde = ", ".join(str(x) for x in (p.get("endereco"), p.get("bairro"),
                                      p.get("cidade"), p.get("uf")) if x)
    if onde:
        partes.append(f"residente e domiciliado(a) em {onde}")

    return ", ".join(partes)


# ------------------------------------------------------------------ o teor


def montar(con: sqlite3.Connection, assento_id: int, *, serventia: dict,
           livro: str = "", folha: str = "", selo: str = "") -> str:
    """O texto do termo, montado. Só calcula — NÃO grava.

    QUEM GRAVA E `congelar`, e a separacao e deliberada: montar e barato e se
    pode fazer quantas vezes quiser para ver como fica; **gravar acontece uma
    vez, na lavratura**, e depois o texto nao muda mais.
    """
    return montar_para_conferir(con, assento_id, serventia=serventia,
                                livro=livro, folha=folha, selo=selo)["texto"]


def montar_para_conferir(con: sqlite3.Connection, assento_id: int, *,
                         serventia: dict, livro: str = "", folha: str = "",
                         selo: str = "") -> dict:
    """O termo montado E o que ficou em branco nele. Só calcula — NÃO grava.

    **A CONFERÊNCIA DO MODELO CONTRA UM ASSENTO REAL USA ESTA, E NÃO UMA CÓPIA**
    — relato #123, 15/10/2026. A tela dos teores (`/rcpn/formulario/<chave>`)
    chamava a ponte do nascimento à mão, com dois parâmetros que ela não
    aceita: «Preencher com este» virava HTTP 500, e casamento e óbito nem
    tinham o botão. Conferir com uma régua e lavrar com outra é como a tela
    aprova o que o livro não monta; por isso `montar` passou a chamar esta, e
    a tela também.
    """
    import modelos_da_casa as MODELOS
    import modelos_motor_versao as VERSAO
    import rc_modelos_do_livro as LIVRO

    bd = banco(con)
    especie = str(
        bd.valor("SELECT especie FROM rc_assentos WHERE id = %s",
                 (assento_id,)) or "").upper()
    chave = MODELO_DA_ESPECIE.get(especie)
    if not chave:
        raise TermoError(
            f"Não há modelo de termo para {ASSENTO.NOME_DA_ESPECIE.get(especie, especie)}. "
            "O sistema antigo não tinha modelo para essa espécie e esta casa nunca "
            "lavrou nenhuma — inventar a forma de um ato que ninguém praticou "
            "é o que a correição acha.")

    # **O CORPO SAI DO CATALOGO, E O TEXTO E O DA CASA** — decisao do oficial em
    # 30/08/2026 («nao utilizaremos os modelos ruins do e-oficio»), com a forma
    # que ele escolheu em 31/08 («opcao B»).
    #
    #   `corpo_de` devolve o que ele editou, ou o padrao — que agora aponta para
    #   `rc_modelos_do_livro`, construido dos requisitos legais. As duas coisas
    #   ao mesmo tempo: o termo e o da casa, **e continua editavel por ele**,
    #   que e o relato #28.
    # Plug do motor (SANDBOX): flag USAR_CONTEUDO_PUBLICADO_EDITOR=False
    # -> nao consulta o Editor; None/vazio -> corpo_de legado (dentro do helper).
    corpo, _origem = VERSAO.corpo_do_termo(con, chave)
    if corpo is None and chave:
        corpo = MODELOS.corpo_de(con, chave)

    ruim = LIVRO.conferir_corpo(chave.replace("RC_TERMO_", ""), corpo)
    if ruim:
        raise TermoError(ruim)

    pessoas = [dict(p) for p in bd.ler(
        "SELECT * FROM rc_pessoas WHERE assento_id = %s ORDER BY ordem, id",
        (assento_id,))]
    assento = dict(bd.um(
        "SELECT * FROM rc_assentos WHERE id = %s", (assento_id,)))
    assento["livro_do_ato"] = livro
    assento["folha_do_ato"] = folha
    assento["selo_do_ato"] = selo

    # **A ASSINATURA E A DA REGRA VIVA, E A LEITURA E UMA SO.** `comum` leva os
    # dois claros pelo nome que os modelos usam — `escrevente` e
    # `funcao_do_escrevente` —, e quem os resolve é `quem_assina_da_serventia`,
    # a mesma que a prévia do modelo chama.
    comum = {"sv": _como_as_pontes_leem(serventia),
             **quem_assina_da_serventia(serventia)}

    try:
        # **AS FRASES DO TERMO SÃO LIDAS DEZ CHAMADAS ABAIXO DAQUI** (LF06C):
        # a qualificação de cada parte (papel `RC_QUALIFICACAO`) e as peças de
        # cada termo (`RC_TERMO_*__dnv`, `__sepultamento`…) saem de dentro das
        # funções puras de `rc_modelos_do_livro`, que não têm conexão — e a
        # prévia do motor (`modelos_motor_termo`) as chama sem banco, lendo o
        # padrão. Aqui, que é quem lavra, `lendo_da_casa` faz essas mesmas
        # leituras passarem pela busca única: o ajuste da casa vale no termo
        # que vai para o livro, sem pendurar `con` em dez assinaturas.
        with TEXTOS.lendo_da_casa(con):
            if chave == "RC_TERMO_CASAMENTO":
                documentos = _documentos_da_habilitacao(con, assento_id)
                # A HABILITAÇÃO DESTA CASA DÁ A DATA DOS PROCLAMAS — LD01,
                # 21/10/2026. O termo a escrevia só quando a habilitação era
                # de fora (o balcão a digitava); a desta casa tem o edital
                # gravado (LRP art. 70, 4º; CN-MA art. 284, IV).
                habilitacao = _habilitacao_desta_casa(con, assento_id, assento)
                if habilitacao:
                    if not str(assento.get("proclamas_data") or "").strip():
                        assento["proclamas_data"] = habilitacao.get("edital_em")
                    if not documentos:
                        documentos = _documentos_da_habilitacao(
                            con, assento_id, habilitacao_id=habilitacao["id"])
                r = LIVRO.montar_casamento_do_assento(
                    assento, pessoas, corpo, documentos=documentos, **comum)
            elif chave == "RC_TERMO_LIVRO_E":
                r = LIVRO.montar_livro_e_do_assento(
                    assento, pessoas, corpo, **comum)
            elif chave == "RC_TERMO_OBITO":
                # **AS MARCAS SAO DICIONARIO PARA A PONTE, E LISTA NO MODULO.**
                #
                #   `do_assento` devolve a LISTA das quatro, cada uma com
                #   rotulo e estado — que e o que a TELA precisa para desenhar
                #   as caixinhas. A ponte do termo pergunta outra coisa:
                #   `marcas.get("obito_eleitor")`, comparado com `SIM`.
                #
                #   Passar a lista nao estoura aqui: estoura la dentro, com
                #   `'list' object has no attribute 'get'` — **HTTP 500 no
                #   meio da lavratura de um obito**. E eu tinha acabado de
                #   corrigir a assinatura desta mesma chamada sem olhar o TIPO
                #   do que ela devolve; quem pegou foi o teste que monta um
                #   obito de verdade, e nao a releitura.
                import rc_marcas_do_obito as MARCAS
                r = LIVRO.montar_obito_do_assento(
                    assento, pessoas, corpo,
                    marcas={m["chave"]: m["estado"]
                            for m in MARCAS.do_assento(assento)}, **comum)
            else:
                r = LIVRO.montar_do_assento(assento, pessoas, corpo, **comum)
    except (LIVRO.ModeloError, MODELOS.ModeloError) as erro:
        # A peça que falta na pasta (e sem ajuste da casa) chega aqui com o
        # nome do arquivo — a mensagem já é a do balcão.
        raise TermoError(str(erro)) from erro
    except (KeyError, IndexError, ValueError) as erro:
        raise TermoError(
            f"O modelo do termo tem um claro que o sistema não sabe preencher: "
            f"{erro}. Confira o modelo em Configuração → Modelos dos "
            f"documentos.") from erro
    return r


# ===================================================== quem assina, e de onde

# **A SERVENTIA CHEGA AQUI COM OUTROS NOMES, e isto quase saiu no livro.**
#
#   `atribuicoes_web._servent()` monta `{nome, cidade, uf, estado, registrador,
#   titulo}` — e as pontes do termo leem `ri_cidade`, `ri_uf` e `estado`, que sao
#   os nomes das CONFIGURACOES. Sem a traducao, o termo sairia com
#   «neste Municipio de ____________» e **sem ninguem assinando embaixo**, no
#   papel que vai escrito no livro.
#
#   Nenhum teste de mesa pegaria: eles montam a serventia com os nomes que a
#   funcao que estao testando espera. Quem pegou foi o teste que usa a serventia
#   como a TELA a monta. E a traducao aceita as duas grafias de proposito —
#   `dados_serventia` devolve uma, `_servent` devolve a outra, e as duas sao
#   chamadores legitimos desta funcao.
def _como_as_pontes_leem(serventia: dict) -> dict:
    """A serventia com os nomes que o modelo do livro usa. So calcula."""
    sv = dict(serventia or {})
    for de, para in (("cidade", "ri_cidade"), ("uf", "ri_uf")):
        if not str(sv.get(para) or "").strip():
            sv[para] = sv.get(de) or ""
    if not str(sv.get("estado") or "").strip():
        sv["estado"] = sv.get("ri_estado") or ""
    return sv


def _quem_assina(serventia: dict) -> str:
    """**QUEM ASSINA SAI DA REGRA VIVA** — a substituta se houver, senao o
    titular. `_servent` ja resolve isso e entrega em `registrador`; `escrevente`
    fica na frente para quem passar o nome de quem lavrou."""
    for onde in ("escrevente", "registrador", "nome"):
        quem = str(serventia.get(onde) or "").strip()
        if quem:
            return quem
    return ""


def _funcao_de_quem_assina(serventia: dict) -> str:
    """A funcao de quem assina. «Oficial» e o piso, e nao a resposta."""
    for onde in ("funcao", "titulo"):
        qual = str(serventia.get(onde) or "").strip()
        if qual:
            return qual
    return "Oficial"


def quem_assina_da_serventia(serventia: dict) -> dict:
    """Os dois claros da assinatura, lidos da regra viva. Só calcula.

    **ESTA LEITURA É UMA SÓ, E TEM DOIS CHAMADORES** — `montar`, que monta o
    termo do assento, e a prévia do modelo (`/rcpn/formulario/<chave>`), em que
    a assinatura é campo de texto e sairia em branco no papel. Escrever a lista
    duas vezes faria a prévia preencher um claro e a lavratura outro.

    A lista de quais são **vem da constante do modelo** — que mora em
    `rc_modelos_do_livro`, o mesmo lugar que os declara lá —, e não de uma
    cópia daqui: se aparecer um terceiro claro da assinatura, o `KeyError`
    avisa, em vez de o valor ficar em branco no papel assinado, calado.
    """
    import rc_modelos_do_livro as LIVRO

    como_se_le = {"escrevente": _quem_assina,
                  "funcao_do_escrevente": _funcao_de_quem_assina}
    return {n: como_se_le[n](serventia)
            for n in LIVRO.QUEM_ASSINA_VEM_DE_FORA}


def _habilitacao_desta_casa(con, assento_id: int,
                            assento: dict) -> dict | None:
    """A habilitação DESTA casa que autorizou o casamento, ou None. Só lê.

    Casamento à vista de habilitação de outra serventia não tem habilitação
    aqui (o balcão digita a serventia, a data e os documentos). A ligação é a
    de `habilitacao.habilitacao_relacionada_ao_assento`: o assento amarrado
    na celebração, ou o `habilitacao_id` que a tela de lavrar grava — e que,
    desde o LD01, já está no assento quando o termo se escreve.
    """
    if str(assento.get("habilitacao_serventia") or "").strip():
        return None
    bd = banco(con)
    if not bd.tem_tabela("hc_habilitacoes"):
        return None
    import habilitacao as HAB
    return HAB.habilitacao_relacionada_ao_assento(bd, assento_id)


def _documentos_da_habilitacao(con: sqlite3.Connection,
                               assento_id: int, *,
                               habilitacao_id: int | None = None) -> list[dict]:
    """Os documentos da habilitação ligada ao assento. Só lê.

    **PEDIDO DO OFICIAL**: «no casamento, apresentar relação dos documentos
    apresentados no termo». Eles já estavam em `hc_documentos` — com código,
    descrição, fundamento e se foi apresentado ou dispensado — e nenhuma tela
    os levava ao papel.

    Sem habilitação ligada devolve lista vazia, e o termo diz o que sabe: um
    casamento cuja habilitação veio de outra serventia não tem os documentos
    aqui dentro.
    """
    # **A LIGACAO MORA NA HABILITACAO, E NAO NO ASSENTO** — medido em
    # 31/08/2026: `rc_assentos` tem `habilitacao_serventia` e
    # `habilitacao_selo`, e nenhum `habilitacao_id`; quem aponta e
    # `hc_habilitacoes.casamento_assento_id`. Eu escrevi o `JOIN` ao contrario
    # na primeira versao, e ele nao estouraria: `sqlite3.Error` viraria lista
    # vazia, e **o termo sairia sem a relacao de documentos, calado**.
    bd = banco(con)
    try:
        # No PostgreSQL um erro de SQL aborta a transação da rota; por isso a
        # ausência da tabela/coluna se pergunta antes, em vez de se apanhar.
        if not (bd.tem_tabela("hc_documentos")
                and bd.tem_coluna("hc_habilitacoes", "casamento_assento_id")):
            return []
        if habilitacao_id is not None:
            # A habilitação já achada pela tela de lavrar (LD01): o assento
            # ainda não foi amarrado a ela na celebração.
            return [dict(x) for x in bd.ler(
                """SELECT * FROM hc_documentos WHERE habilitacao_id = %s
                    ORDER BY id""", (int(habilitacao_id),))]
        return [dict(x) for x in bd.ler(
            """SELECT d.* FROM hc_documentos d
                 JOIN hc_habilitacoes h ON h.id = d.habilitacao_id
                WHERE h.casamento_assento_id = %s ORDER BY d.id""",
            (assento_id,))]
    except sqlite3.Error:
        # SEM A LIGACAO, O TERMO SAI SEM A RELACAO — e nao estoura. A coluna
        # pode nao existir numa instalacao antiga, e derrubar a lavratura por
        # causa da lista de documentos seria trocar um papel incompleto por
        # nenhum papel.
        return []


def congelar(con: sqlite3.Connection, assento_id: int, *, serventia: dict,
             agora: str, livro: str = "", folha: str = "",
             selo: str = "") -> str:
    """Monta o termo e o guarda no assento. ESCREVE, e uma vez só.

    **O TERMO NAO SE REMONTA.** Ele é o texto que o declarante leu e assinou; um
    sistema que o remontasse depois faria o livro de hoje discordar do papel
    assinado ontem — e é o papel assinado que vale.

    Corrigir termo é **averbar ao lado**, que é o que a lei manda e o que
    `rc_assento` já sabe fazer com os três atos da divisão tripartite.
    """
    bd = banco(con)
    a = bd.um("SELECT teor FROM rc_assentos WHERE id = %s",
              (assento_id,))
    if not a:
        raise TermoError(f"Não achei o assento nº {assento_id}.")
    if (a["teor"] or "").strip():
        raise TermoError(
            "Este assento já tem termo escrito, e termo não se reescreve — o "
            "que o declarante assinou é o que vale. Para corrigir, averbe ao "
            "lado (averbação, anotação ou retificação).")

    texto = montar(con, assento_id, serventia=serventia, livro=livro,
                   folha=folha, selo=selo)
    bd.escrever(
        """UPDATE rc_assentos SET teor = %s, teor_formato = 'html'
            WHERE id = %s""", (texto, assento_id))
    return texto


def _trocar_o_traco(texto: str, corpo: str, campo: str, valor: str,
                    traco: str) -> str:
    """Troca o traço daquele campo pelo valor. Só calcula — e devolve o texto.

    **O LUGAR SE ACHA PELO MODELO, E NÃO NO PALPITE.** O corpo do termo diz o
    que vem antes e o que vem depois do claro — `Eu, {escrevente},` —, e é essa
    moldura que localiza o traço no texto congelado. Procurar só
    `____________` trocaria o primeiro traço do papel, que pode ser de outro
    campo: o termo de nascimento tem dois exigidos, e trocar o errado poria o
    nome do escrevente no lugar do nome do registrado, **e o papel continuaria
    com cara de certo**.

    Se o traço não está onde a moldura diz, **nada muda** — quem chama diz que
    não achou. `str.replace` sem achar não estoura, e é justamente por isso que
    o silêncio aqui seria perigoso.

    O `traco` vem de fora porque quem o escreve é `rc_modelos_do_livro`: **uma
    constante só**, e não duas com o mesmo desenho.
    """
    marcador = "{" + campo + "}"
    if marcador not in corpo or not valor:
        return texto
    antes, depois = _a_moldura(corpo, campo)
    alvo = antes + traco + depois
    if alvo not in texto:
        return texto
    return texto.replace(alvo, antes + valor + depois, 1)


def _a_moldura(corpo: str, campo: str, largura: int = 40) -> tuple[str, str]:
    """O texto que cerca o claro — sem atravessar outro claro. Só calcula.

    **A MOLDURA NÃO PODE CONTER OUTRO CLARO, E ESTA ERA A METADE QUE FALTAVA.**
    A primeira versão colhia 40 caracteres de cada lado do `{escrevente}`, e o
    vizinho da direita é `{funcao_do_escrevente}` — de modo que a moldura saía
    com o claro **dentro** dela:

        «...assina. Eu, {escrevente}, {funcao_do_escrevente}, dou fé e assino.»

    No texto que veio da tela aquele lugar já tem o valor (ou o outro traço), a
    comparação não achava nada, e `str.replace` sem achar **não estoura**: o
    nome de quem assina ficava em branco no Livro, em silêncio — que é
    exatamente o defeito do relato #63. Medido contra o modelo real de
    nascimento em 15/09/2026: `mudou: False`, com os dois traços no texto.

    O corte no último `}` e no primeiro `{` mantém a moldura **dentro do trecho
    que não tem claro**, que é o que ela precisa provar: o que vem imediatamente
    antes e depois daquela assinatura, e não o desenho do modelo em volta.
    """
    marcador = "{" + campo + "}"
    antes, _, depois = corpo.partition(marcador)
    corte = antes.rfind("}")
    if corte >= 0:
        antes = antes[corte + 1:]
    corte = depois.find("{")
    if corte >= 0:
        depois = depois[:corte]
    # A moldura é o FIM do texto anterior ao claro e o COMEÇO do posterior: o
    # modelo tem quebras de linha e espaços de sobra, e comparar tudo não
    # acharia nada.
    return antes[-largura:], depois[:largura]


def _o_traco_ficou(corpo: str, campo: str, texto: str, traco: str) -> bool:
    """O traço ainda está ONDE o modelo diz que o nome de quem assina vai?

    **A PERGUNTA NÃO É «TEM TRAÇO NO TEXTO?», E A MEDIÇÃO MOSTROU POR QUÊ.**
    Dos 625 assentos com o traço da casa dentro do `teor`, **624 são texto do
    acervo** — e ali o traço é a linha de assinatura de vinte e dois
    underscores, «Em testemunho da verdade.\\n______________________», onde
    quem assina é a mão. Os doze underscores da casa **cabem dentro** daqueles
    vinte e dois: procurar o traço em qualquer lugar acusaria os 624 como
    defeito, e alarme que soa sempre é alarme que ninguém ouve.

    Aqui se procura a **moldura de quem assina** — o pedaço que o modelo escreve
    imediatamente antes e depois do claro —, e só ela. No texto do acervo essa
    moldura não existe; no assento 8.266 existe, e é o defeito de verdade.
    """
    antes, depois = _a_moldura(corpo, campo)
    return ((len(antes) >= 8 and (antes[-20:] + traco) in texto)
            or (len(depois) >= 8 and (traco + depois[:20]) in texto))


def completar_quem_assina(con: sqlite3.Connection, teor: str, *,
                          especie: str, serventia: dict) -> dict[str, object]:
    """Põe quem assina no termo que chegou com o traço. SÓ CALCULA.

    **RELATO #63 DO OFICIAL, 15/09/2026** — o assento 8266 foi lavrado com

        «...o(a) declarante assina. Eu, ____________, Oficial, dou fé e
         assino.»

    e o nome de quem assinou **não está no Livro**. O estrago é do tamanho do
    livro: medido em 15/09/2026, **625 dos 1.181 assentos com teor** desta casa
    têm o traço — **e a primeira leitura disso estava errada**. Recontado
    procurando a **moldura** de quem assina, e não o traço em qualquer lugar,
    **624 são texto do acervo**: ali o traço é a linha de assinatura de vinte e
    dois underscores («Em testemunho da verdade.\\n______________________»),
    onde quem assina é a mão, e os doze da casa **cabem dentro** daqueles vinte
    e dois. O defeito de verdade é **um** — o assento 8.266. **Escrever 625
    como se fossem todos lavrados aqui seria o carimbo que mente com um número
    de verdade dentro**, e quem o lesse mandaria consertar 624 livros de papel
    que não têm defeito.

    **A CAUSA É O CAMINHO, E NÃO O MODELO.** O modelo sempre teve
    `{escrevente}` e `{funcao_do_escrevente}`, e `montar` sempre soube
    preenchê-los: quem lavra digita o teor no formulário, e o texto digitado vai
    **direto** para `rc_assentos.teor`, sem passar por `montar`. O que o
    escrevente não digita, sai da máquina como traço — do mesmo jeito que o
    E-Ofício fazia, o que explica o hábito.

    **E É MELHOR CONSERTAR DO QUE EXIGIR.** `escrevente` e
    `funcao_do_escrevente` não são campo de decisão do balcão: são a **regra
    viva de quem responde pela serventia**, a mesma do cartão de assinatura e da
    certidão do RI (`_quem_assina`). Pedir que alguém os digite a cada assento
    seria pedir que os digitasse certo — e o relato #65 diz o contrário: «não faz
    sentido escolher quem assinou».

    Por isso o conserto é **preencher pelo que o sistema já sabe**, na hora de
    gravar: quem lavrou é quem está na sessão, e a função sai da mesma regra.

    Devolve `{texto, mudou, quais, nao_achei, motivo}` — e **nada é gravado
    aqui**. Quem grava é `congelar`.

    **`quais` E `nao_achei` SÃO COISAS DIFERENTES, E É A METADE QUE MAIS
    IMPORTA.** Um diz o que foi preenchido; o outro, o claro que o modelo tem e
    a troca **não achou** — o caso pior dos dois, porque o Livro sai com metade
    da assinatura («Eu, ____, dou fé e assino», com a função preenchida). Antes
    o aviso só olhava o caso em que **nada** tinha sido trocado, e ficava calado
    neste. `str.replace` sem achar não estoura, e é por isso que o defeito viveu
    escondido: quem avisa o balcão é `_teor_com_quem_assina`, na rota.
    """
    fora = {"texto": teor, "mudou": False, "quais": [], "motivo": ""}
    if not (teor or "").strip():
        fora["motivo"] = "o teor está vazio"
        return fora
    import modelos_motor_versao as VERSAO
    import rc_modelos_do_livro as LIVRO

    chave = MODELO_DA_ESPECIE.get(str(especie or "").upper())
    if not chave:
        fora["motivo"] = f"a espécie {especie!r} não tem modelo de termo"
        return fora
    valores = quem_assina_da_serventia(serventia)
    if not valores.get("escrevente"):
        fora["motivo"] = ("não sei quem assina — a serventia não tem escrevente "
                          "nem registrador informado")
        return fora
    # **O CORPO VEM DO CATÁLOGO** (`modelos_da_casa.corpo_de`), e é dele que sai
    # a moldura que localiza o traço: `corpo_de` é a fonte única do modelo, a
    # mesma que `montar` usa.
    # Mesmo plug de montar: flag off -> caminho atual; None -> corpo_de legado.
    corpo, _origem = VERSAO.corpo_do_termo(con, chave)
    if corpo is None and chave:
        import modelos_da_casa as MODELOS
        corpo = MODELOS.corpo_de(con, chave)
    texto = teor
    quais = []
    nao_achei = []
    for campo in LIVRO.QUEM_ASSINA_VEM_DE_FORA:
        novo = _trocar_o_traco(texto, corpo, campo, valores.get(campo) or "",
                               LIVRO.O_TRACO_DA_CASA)
        if novo != texto:
            texto = novo
            quais.append(campo)
        elif (valores.get(campo)
                and _o_traco_ficou(corpo, campo, texto, LIVRO.O_TRACO_DA_CASA)):
            # **A TROCA QUE NÃO ACHOU O LUGAR NÃO PODE PASSAR CALADA.** O
            #   modelo tem o claro e o texto tem traço, e mesmo assim nada
            #   mudou: ou o teor veio de outra versão do modelo, ou o trecho
            #   foi editado à mão. `str.replace` sem achar não estoura — e o
            #   Livro iria para o papel sem o nome de quem assinou, que é o
            #   relato #63 inteiro. Quem avisa é quem chama.
            nao_achei.append(campo)
    fora["texto"] = texto
    fora["mudou"] = bool(quais)
    fora["quais"] = quais
    fora["nao_achei"] = nao_achei
    if not quais:
        fora["motivo"] = ("o termo não tem os traços de quem assina — ou já "
                          "estão preenchidos")
        if nao_achei:
            fora["motivo"] = ("não achei o lugar de quem assina no texto, e o "
                              "traço continua lá — o nome vai ficar em branco")
    return fora


def texto_para_mostrar(con: sqlite3.Connection, assento_id: int, *,
                       serventia: dict, livro: str = "", folha: str = "",
                       selo: str = "") -> dict[str, object]:
    """O texto que a tela e a folha mostram. SÓ LÊ — não grava.

    **PÁGINA EM BRANCO É DEFEITO.** Relato #38, 31/08/2026: o E-Ofício não
    guardava o teor — montava na hora de imprimir — e a carga deixou
    `rc_assentos.teor` vazio. A folha que só lia a coluna saía sem o ato.

    Se o teor já está escrito, é ele — congelado. Se está vazio, monta dos
    campos pelo catálogo da casa (`montar` / `rc_modelos_do_livro`). **Montar
    não é gravar.** O importado não congela só porque a prévia abriu; gravar
    continua sendo `congelar`, uma vez só, com confirmação.
    """
    bd = banco(con)
    a = bd.um("SELECT * FROM rc_assentos WHERE id = %s",
              (assento_id,))
    if not a:
        raise TermoError(f"Não achei o assento nº {assento_id}.")
    a = dict(a)
    escrito = (a.get("teor") or "").strip()
    especie = str(a.get("especie") or "").upper()
    do_acervo = veio_do_acervo(a)
    if escrito:
        return {"texto": escrito, "congelado": True,
                "do_acervo": do_acervo, "especie": especie, "erro": ""}
    try:
        texto = montar(con, assento_id, serventia=serventia,
                       livro=livro, folha=folha, selo=selo)
        return {"texto": texto, "congelado": False,
                "do_acervo": do_acervo, "especie": especie, "erro": ""}
    except TermoError as erro:
        return {"texto": "", "congelado": False,
                "do_acervo": do_acervo, "especie": especie,
                "erro": str(erro)}


# ---------------------------------------------------------- O QUE VEIO DO ACERVO
#
# **ORDEM DO OFICIAL, EM 30/08/2026, E ELA CORRIGE O QUE EU TINHA FEITO:**
#
#     «aparentemente vc esta gerando uma expectativa de termo, que nao
#      corresponde à realidade. nao gere o termo, apenas importe as informaçoes.
#      essas informaçoes serão utilizadas apenas para certidoes, o termo nao será
#      lavrado novamente, por isso nao precisamos imaginar como ficou o termo.»
#
# EU ESTAVA CERTO NA CONCLUSAO E ERRADO NA TELA. O modulo ja dizia, em prosa, que
# os do acervo ficam sem termo de proposito — e mesmo assim os LISTAVA numa tela
# chamada «Termos a escrever». **Lista e promessa**: o que esta numa lista de
# trabalho e trabalho que alguem vai fazer, por mais que a legenda diga o
# contrario.
#
# O termo daqueles assentos **existe, em papel, e foi assinado**. O que o sistema
# tem deles sao as INFORMACOES, e elas servem a CERTIDAO — que se monta dos
# campos e diz o que o assento contem, sem fingir ser a copia do que foi escrito.
ORIGEM_SEM_TERMO_A_ESCREVER = "EOFICIO"

# ONDE O PDF DO TERMO DE PAPEL FICA. A tabela `attachments` ja serve expediente,
# tarefa e protocolo — **nao se cria a quarta**: `entity_type` e o que distingue,
# e uma tabela nova seria o mesmo dado em dois lugares.
ANEXO_DO_TERMO = "rc_termo"

POR_QUE_O_ACERVO_NAO_ENTRA = (
    "o termo deles existe em papel e foi assinado; o que o sistema guarda são as "
    "**informações**, e elas servem à certidão. A prévia monta o que os campos "
    "permitem ver — e **não é a cópia do que foi escrito**")


def veio_do_acervo(assento: dict) -> bool:
    """Se o assento veio da carga do E-Ofício. Só calcula."""
    return str((assento or {}).get("origem") or "").upper() ==         ORIGEM_SEM_TERMO_A_ESCREVER


def quantos_termos_faltam(con) -> dict:
    """Quantos termos faltam escrever de verdade. Só lê.

    **OS DO ACERVO NÃO ENTRAM MAIS NA CONTA NEM NA LISTA** — ordem do oficial em
    30/08/2026. Eles aparecem só num contador à parte, para quem quiser saber
    quantos são, e com a palavra que os descreve: *informações importadas*, e não
    *termos a escrever*.
    """
    linhas = [dict(r) for r in banco(con).ler(
        """SELECT id, origem FROM rc_assentos
            WHERE COALESCE(teor, '') = ''
              AND COALESCE(situacao, 'ATIVO') <> 'CANCELADO'
         ORDER BY id""")]
    do_acervo = [x for x in linhas if veio_do_acervo(x)]
    return {"a_escrever": len(linhas) - len(do_acervo),
            "importados": len(do_acervo),
            "total_sem_teor": len(linhas)}


def assentos_sem_termo(con: sqlite3.Connection,
                       limite: int = 500) -> list[dict]:
    """Os assentos lavrados AQUI que ainda não têm o texto do livro. Só lê.

    **OS DO ACERVO NÃO ENTRAM** — ordem do oficial em 30/08/2026. Antes eles
    apareciam com uma legenda explicando que ficavam sem termo de propósito, e
    **isso era pior que não mostrá-los**: lista é promessa, e o que está numa
    lista de trabalho é trabalho que alguém vai fazer.

    O termo deles existe em papel e foi assinado. O caminho para eles é a
    **certidão**, que se monta dos campos.
    """
    return [dict(r) for r in banco(con).ler(
        """SELECT id, serie, especie, numero, nome, data_ato, origem
             FROM rc_assentos
            WHERE COALESCE(teor, '') = ''
              AND COALESCE(origem, '') <> %s
              AND COALESCE(situacao, 'ATIVO') <> 'CANCELADO'
         ORDER BY id DESC LIMIT %s""",
        (ORIGEM_SEM_TERMO_A_ESCREVER, limite))]


def informacoes_importadas(con: sqlite3.Connection,
                           limite: int = 500) -> list[dict]:
    """Os assentos vindos do acervo, com o que se sabe deles. Só lê.

    **NÃO É UMA LISTA DE TRABALHO**, e por isso tem nome próprio: são as
    informações que a carga trouxe, e elas servem à **certidão**. A tela mostra
    se cada um já tem o **PDF do termo** anexado, que é a única coisa que ainda
    pode ser trazida do papel.
    """
    return [dict(r) for r in banco(con).ler(
        """SELECT a.id, a.serie, a.especie, a.numero, a.nome, a.data_ato,
                  a.livro_volume, a.matricula,
                  (SELECT COUNT(*)::int FROM attachments x
                    WHERE x.entity_type = %s AND x.entity_id = a.id) AS anexos
             FROM rc_assentos a
            WHERE COALESCE(a.origem, '') = %s
              AND COALESCE(a.situacao, 'ATIVO') <> 'CANCELADO'
         ORDER BY a.data_ato IS NULL, a.data_ato DESC, a.id DESC LIMIT %s""",
        (ANEXO_DO_TERMO, ORIGEM_SEM_TERMO_A_ESCREVER, limite))]
