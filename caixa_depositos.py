"""
Deposito previo — o dinheiro que entra antes do ato.

POR QUE ESTE MODULO EXISTE, E NAO O CODIGO SOLTO NA TELA DO CAIXA
    O deposito precisava passar a ser lancado tambem pela tela do titulo do
    Registro de Imoveis: e la que o apresentante deixa o adiantamento, e obrigar
    a pessoa a sair do titulo, abrir o caixa e procurar o protocolo e um passo
    que se esquece.

    A alternativa era copiar a criacao do deposito para o `ri_web`. Nao copiei —
    e a mesma armadilha que produziu o defeito da funcao do usuario, onde a
    mesma regra vivia escrita em tres arquivos e um deles divergiu em silencio.
    Aqui e uma implementacao so, e as duas telas chamam ela.

O QUE UM DEPOSITO PRECISA FAZER, TODA VEZ
    1. ganhar um numero de controle proprio (DP2026.08.7), para o cliente citar
       um numero so quando voltar;
    2. entrar no caixa do dia, senao a gaveta nao fecha;
    3. guardar a que titulo pertence, quando pertencer a um.

    Esquecer o passo 2 e o erro que so aparece no fim do expediente, quando a
    conferencia nao bate e ninguem lembra do deposito da manha.

DINHEIRO EM CENTAVOS INTEIROS
    Como no resto do caixa. Ponto flutuante erra: 0,1 + 0,2 nao da 0,3, e
    conferencia de caixa nao perdoa um centavo.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from bd_nativo import banco
from caixa_schema import reais


def proximo_numero(con, hoje: date | None = None) -> str:
    """O numero de controle do deposito: DP<ano>.<mes>.<sequencial>.

    A sequencia reinicia por mes, e por isso o filtro do prefixo. Ordenar por
    texto daria DP2026.08.10 antes de DP2026.08.9 — por isso o maior se le
    como NUMERO, pelo prefixo numerico do sufixo (como o CAST do SQLite lia).
    """
    hoje = hoje or date.today()
    prefixo = f"DP{hoje.year}.{hoje.month:02d}."
    maior = banco(con).valor(
        """SELECT max(substring(substring(numero FROM %(inicio)s) FROM '^[0-9]+')::bigint)
             FROM cx_depositos
            WHERE starts_with(numero, %(prefixo)s)""",
        {"prefixo": prefixo, "inicio": len(prefixo) + 1})
    return f"{prefixo}{int(maior or 0) + 1}"


def criar(con, *, valor_centavos: int, depositante: str,
          agora: str, documento: str | None = None, observacao: str | None = None,
          forma_pagamento: str = "DINHEIRO", caixa_id: int | None = None,
          protocolo_id: int | None = None,
          ri_protocolo_id: int | None = None,
          nt_ato_id: int | None = None,
          atribuicao: str | None = None,
          servico_codigo: int | None = None,
          hoje: date | None = None,
          data_do_deposito: date | None = None) -> dict:
    """Grava o deposito e o lanca no caixa do dia. Devolve o que foi criado.

    `caixa_id` vindo None quer dizer que nao ha caixa aberto para o operador. O
    deposito e gravado assim mesmo — o dinheiro entrou, e recusar o registro
    porque a gaveta esta fechada seria perder o fato. Quem chama avisa que
    falta lancar.

    `ri_protocolo_id` e a ligacao com o titulo do Registro de Imoveis; o
    `protocolo_id` e com o protocolo do caixa. Um deposito pode ter os dois, um
    so, ou nenhum — dinheiro deixado "para quando o titulo chegar" existe.

    `data_do_deposito` e' a data do PAPEL, e pode nao ser hoje — RELATO #50 do
    oficial: «neste campo de deposito previo deve conter data do deposito». O
    caso comum e' o dinheiro deixado na sexta e registrado na segunda. Ela vai
    para `cx_depositos.data`; a numeracao e o lancamento no caixa continuam
    saindo de `hoje`, porque **a gaveta conta o dinheiro quando ele entra, e
    nao quando o papel foi assinado** — lancar com a data do papel mexeria no
    caixa de um dia ja conferido.

    `atribuicao` e `servico_codigo` sao a SEGUNDA METADE do mesmo relato —
    «informacoes do tipo de servico». Os dois sao OPCIONAIS: medido em
    17/09/2026, **8 dos 14 depositos nao tem vinculo nenhum**, e o dinheiro
    deixado «para quando o titulo chegar» e' legitimo. Mas o que for informado
    e' conferido antes de entrar: atribuicao fora do vocabulario da casa, ou
    servico que nao esta no catalogo, viraria uma linha que nenhum filtro acha
    depois — e o pedido do relato e' justamente poder achar.
    """
    hoje = hoje or date.today()
    data = data_do_deposito or hoje
    bd = banco(con)
    if valor_centavos <= 0:
        raise ValueError("O valor do depósito tem de ser maior que zero.")
    depositante = (depositante or "").strip()
    if not depositante:
        raise ValueError("Informe quem está depositando.")

    qual = (str(atribuicao or "").strip().upper()) or None
    if qual and qual not in ATRIBUICOES:
        raise ValueError(
            f"«{atribuicao}» não é uma atribuição desta casa. Escolha uma da "
            f"lista: {', '.join(ATRIBUICOES)}.")
    servico = None
    if servico_codigo:
        tentativa = resolver_servico(con, servico_codigo)
        if tentativa.get("servico"):
            servico = tentativa["servico"]
        elif tentativa.get("ambiguos"):
            raise ValueError(_recado_dos_ambiguos(
                str(servico_codigo).strip(), tentativa["ambiguos"]))
        else:
            raise ValueError(
                f"Não achei nenhum serviço com «{str(servico_codigo).strip()}». "
                f"Procure pelo código do TJ (por exemplo 13.17.2) ou por uma "
                f"palavra da descrição — ou deixe em branco, que o tipo é "
                f"opcional.")

    # O QUE O VÍNCULO JÁ DECLARA, O DEPÓSITO NÃO PERGUNTA.
    #
    #   Medido em 17/09/2026: dos 14 depósitos da produção, seis estão amarrados
    #   a um protocolo, a uma prenotação ou a um ato de livro — e nesses o tipo
    #   é FATO LIDO, não palpite: o protocolo do balcão grava a própria
    #   atribuição (`cx_protocolos.atribuicao`), a prenotação é da tabela do
    #   Registro de Imóveis e o ato de livro é do Tabelionato de Notas.
    #
    #   Por isso as duas telas que criam depósito COM vínculo — o título do
    #   Registro de Imóveis e o ato das Notas — não precisam oferecer campo
    #   nenhum: o vínculo responde. A tela do caixa, onde o dinheiro costuma
    #   chegar solto, é a única que pergunta.
    #
    #   QUEM RESPONDE ISSO É `sugerir_tipo`, E UMA VEZ SÓ. A mesma função que
    #   sugere na tela é a que o cadastro usa para gravar, e a que o botão dos
    #   depósitos antigos usa — três caminhos, uma régua. Escritas em separado,
    #   elas divergiriam no primeiro conserto, e a divergência aqui é dinheiro
    #   classificado de dois jeitos.
    dica = sugerir_tipo(bd, protocolo_id=protocolo_id,
                        ri_protocolo_id=ri_protocolo_id, nt_ato_id=nt_ato_id,
                        servico_codigo=(servico or {}).get("codigo"))
    if not qual:
        qual = dica["atribuicao"]
    if not servico and dica["servico"]:
        servico = dica["servico"]
    # O ORÇAMENTO SE CONGELA AQUI, no dia do depósito (CN-MA art. 198, VI):
    # é o que foi dito ao cliente quando ele deixou o dinheiro.
    orcamento = orcamento_do_deposito(bd, protocolo_id=protocolo_id, servico=servico)
    bd.travar("cx_depositos.numero")
    numero = proximo_numero(bd, hoje)
    novo = bd.escrever(
        """INSERT INTO cx_depositos
           (numero, data, depositante, depositante_documento, valor, saldo,
            protocolo_id, ri_protocolo_id, nt_ato_id, atribuicao,
            servico_codigo, observacao, orcamento, criado_em, atualizado_em)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (numero, data.isoformat(), depositante, (documento or "").strip() or None,
         reais(valor_centavos), reais(valor_centavos), protocolo_id, ri_protocolo_id,
         nt_ato_id, qual, (servico or {}).get("codigo"),
         (observacao or "").strip() or None,
         json.dumps(orcamento, ensure_ascii=False) if orcamento else None,
         agora, agora))
    deposito_id = int(novo[0]["id"])

    # O depósito é dinheiro que entrou: tem de aparecer no caixa do dia, senão
    # a gaveta não fecha. E o lançamento fica apontado no depósito — é pelo
    # recibo DELE que o orçamento sai para o cliente (art. 197).
    if caixa_id:
        lancamento = bd.escrever(
            """INSERT INTO cx_lancamentos
               (caixa_id, protocolo_id, data, hora, natureza, sentido,
                forma_pagamento, descricao, pagador, valor, criado_em)
               VALUES (%s,%s,%s,%s, 'DEPOSITO_PREVIO','ENTRADA',%s,%s,%s,%s,%s)
               RETURNING id""",
            (caixa_id, protocolo_id, hoje.isoformat(),
             datetime.now().strftime("%H:%M"), forma_pagamento or "DINHEIRO",
             f"Depósito prévio nº {numero} — {depositante}",
             depositante, reais(valor_centavos), agora))
        bd.escrever("UPDATE cx_depositos SET lancamento_id = %s WHERE id = %s",
                    (int(lancamento[0]["id"]), deposito_id))

    # Se o deposito ja aponta os dois lados e o protocolo de caixa ainda
    # nao tem a ponte, grava agora — evidencia explicita, sem adivinhar.
    if protocolo_id and ri_protocolo_id:
        if bd.tem_coluna("cx_protocolos", "ri_protocolo_id"):
            atual = bd.um(
                "SELECT ri_protocolo_id FROM cx_protocolos WHERE id = %s",
                (int(protocolo_id),))
            if atual is not None and atual["ri_protocolo_id"] is None:
                import caixa_protocolo as CXP
                try:
                    CXP.vincular_ri(bd, int(protocolo_id), int(ri_protocolo_id))
                except CXP.ProtocoloError:
                    # Deposito vale mesmo se a prenotacao sumiu; nao bloqueia.
                    pass

    return {"id": deposito_id, "numero": numero, "valor": reais(valor_centavos),
            "data": data.isoformat(), "atribuicao": qual,
            "servico_codigo": (servico or {}).get("codigo"),
            "orcamento": orcamento,
            # A DIVERGÊNCIA ENTRE O VÍNCULO E O SERVIÇO NÃO PASSA CALADA, e não
            # derruba o depósito: quem manda é o vínculo, e quem confere é quem
            # atende. Devolvida para a tela poder dizer.
            "aviso": dica["aviso"],
            "lancado_no_caixa": bool(caixa_id)}


def do_titulo(con, ri_protocolo_id: int) -> list[dict]:
    """Os depositos ligados a um titulo do Registro de Imoveis."""
    return banco(con).ler(
        """SELECT * FROM cx_depositos WHERE ri_protocolo_id = %s
           ORDER BY data, id""", (ri_protocolo_id,))


def do_ato(con, nt_ato_id: int) -> list[dict]:
    """Os depositos ligados a um ato de livro do Tabelionato de Notas."""
    return banco(con).ler(
        """SELECT * FROM cx_depositos WHERE nt_ato_id = %s
           ORDER BY data, id""", (nt_ato_id,))


def saldo_do_titulo(depositos) -> int:
    """Quanto ainda ha de saldo, em centavos, somando os depositos do titulo."""
    from caixa_schema import centavos
    return sum(centavos(d["saldo"]) for d in depositos if not d["encerrado"])


# ------------------------------------------- o orçamento (art. 198, VI)
#
# «No Livro de Controle de Depósito Prévio, o delegatário deverá indicar, no
#  mínimo: [...] VI - A descrição completa do orçamento, inclusive seus
#  acréscimos» (CN-MA art. 198) — e o recibo do depósito «deverá incluir a
#  discriminação orçamentária de todos os valores previstos para o serviço
#  requerido» (art. 197).
#
# O ORÇAMENTO NÃO SE DIGITA: sai de onde a casa já orça. Os itens do
# protocolo, quando o depósito aponta um — é ali que o balcão monta o
# orçamento, item a item, pela tabela do tribunal (o «mero cálculo» é um
# protocolo do tipo ORÇAMENTO) —; senão, o serviço escolhido, pela tabela
# vigente, pela MESMA conta que o protocolo faz (`emolumentos.calcular_item`).
# Duas contas do mesmo preço divergiriam na primeira tabela nova.
#
# OS ACRÉSCIMOS SÃO OS FUNDOS (FERC, FADEP, FEMP e FERRFIS — art. 881, § 1º),
# item a item e somados. Sem preço na tabela vigente não há orçamento completo,
# e o depósito fica sem ele: o livro diz a falta, em vez de imprimir só o nome
# do serviço como se fosse o orçamento.

_FUNDOS_DO_ORCAMENTO = ("emolumentos", "ferc", "fadep", "femp", "ferrfis")


def _orcamento(itens: list[dict], *, de_onde: str, vigencia: Any = None) -> dict:
    """O orçamento pronto para guardar: itens, soma e procedência. Só calcula."""
    import emolumentos as EMOL
    limpos = [{"codigo_ato": i.get("codigo_ato"), "descricao": i.get("descricao"),
               "quantidade": int(i.get("quantidade") or 1),
               "base_calculo": i.get("base_calculo"),
               **{f: i.get(f) for f in _FUNDOS_DO_ORCAMENTO},
               "valor_total": i.get("valor_total")} for i in itens]
    return {"itens": limpos, "soma": EMOL.somar_itens(limpos), "de_onde": de_onde,
            "vigencia": vigencia}


def orcamento_do_deposito(con, *, protocolo_id: Any = None,
                          servico: dict | None = None) -> dict | None:
    """A descrição completa do orçamento do depósito, com os fundos. Só LÊ.

    Do protocolo vêm os itens AINDA A PAGAR, na ordem em que entraram: o
    depósito adianta o que falta, e o item que o cliente já pagou no caixa
    não é orçamento de nada. Devolve None quando não há de onde tirar o
    orçamento com valor — e quem lê o depósito diz a falta.
    """
    bd = banco(con)
    if protocolo_id:
        itens = bd.ler(
            """SELECT codigo_ato, descricao, quantidade, base_calculo, emolumentos,
                      ferc, fadep, femp, ferrfis, valor_total
                 FROM cx_protocolo_atos
                WHERE protocolo_id = %s AND coalesce(quitado, 0) = 0
                ORDER BY id""", (int(protocolo_id),))
        if itens:
            numero = bd.valor("SELECT numero FROM cx_protocolos WHERE id = %s",
                              (int(protocolo_id),))
            return _orcamento(itens, de_onde=f"os itens do protocolo {numero or ''}"
                              .strip())
    if servico and servico.get("codigo"):
        import emolumentos as EMOL
        item = EMOL.calcular_item(bd, servico=int(servico["codigo"]))
        if item:
            codigo = str(item.get("codigo_tj") or "").strip()
            return _orcamento(
                [item | {"codigo_ato": codigo or None, "valor_total": item["total"]}],
                de_onde=(f"o serviço {codigo} da tabela vigente" if codigo
                         else "o serviço da tabela vigente"),
                vigencia=item.get("vigencia"))
    return None


def orcamento_gravado(d) -> dict | None:
    """O orçamento congelado no depósito, ou None. Só lê a linha.

    Texto que não é o JSON esperado vale como ausente — e a falta aparece no
    livro —, em vez de derrubar a tela.
    """
    try:
        bruto = d.get("orcamento") if hasattr(d, "get") else None
        lido = json.loads(bruto) if bruto else None
    except (TypeError, ValueError):
        return None
    if not isinstance(lido, dict) or not lido.get("itens"):
        return None
    return lido


def linhas_do_orcamento(orcamento: dict | None) -> list[str]:
    """O orçamento por extenso, uma linha por item e a soma. Só calcula.

    É a forma do livro e da lista do caixa: o código do TJ, o ato, a
    quantidade, os emolumentos e CADA FUNDO — os acréscimos do art. 198, VI.
    """
    if not orcamento:
        return []
    linhas = []
    for i in orcamento.get("itens") or []:
        fundos = "; ".join(f"{rotulo} R$ {i.get(f) or '0,00'}" for f, rotulo in (
            ("emolumentos", "emolumentos"), ("ferc", "FERC"), ("fadep", "FADEP"),
            ("femp", "FEMP"), ("ferrfis", "FERRFIS")))
        linhas.append(f"{i.get('codigo_ato') or '—'} {i.get('descricao') or ''} × "
                      f"{i.get('quantidade') or 1}: {fundos}; total R$ "
                      f"{i.get('valor_total') or '0,00'}")
    soma = orcamento.get("soma") or {}
    linhas.append(f"Total do orçamento: R$ {soma.get('total') or '0,00'} "
                  f"({orcamento.get('de_onde') or 'origem não registrada'})")
    return linhas


# ---------------------------------------------------------------- espelho

# A CONSULTA QUE O CAIXA USA PARA MOSTRAR A QUE CADA DEPOSITO PERTENCE.
#
#   O deposito passou a poder nascer em tres telas: no caixa, no titulo do
#   Registro de Imoveis e no ato de livro do Tabelionato. Se a tela do caixa
#   nao disser de onde ele veio, o dinheiro fica la sem dizer a que veio — e
#   quem confere no fim do dia nao tem como saber.
#
#   Uma consulta so, aqui, para as telas nao montarem cada uma a sua versao do
#   mesmo LEFT JOIN e divergirem no dia em que um vinculo novo aparecer.
SQL_COM_VINCULO = """
    SELECT d.*,
           p.numero  AS protocolo_numero,
           p.atribuicao AS protocolo_atribuicao,
           r.numero  AS ri_numero,
           r.livro   AS ri_livro,
           a.id      AS ato_id,
           a.tipo    AS ato_tipo,
           a.livro   AS ato_livro,
           a.folha   AS ato_folha,
           s.codigo_tj AS servico_codigo_tj,
           s.descricao AS servico_descricao
      FROM cx_depositos d
      LEFT JOIN cx_protocolos  p ON p.id = d.protocolo_id
      LEFT JOIN ri_protocolos  r ON r.id = d.ri_protocolo_id
      LEFT JOIN nt_atos        a ON a.id = d.nt_ato_id
      LEFT JOIN cx_servicos    s ON s.codigo = d.servico_codigo
"""


def vinculo(d) -> dict:
    """Como o deposito se apresenta na tela do caixa: rotulo e para onde leva.

    Devolve `{"rotulo", "rota", "params"}` — `params` ja no formato que o
    `url_for` espera, porque cada tela nomeia o seu parametro de um jeito
    (`protocolo_id`, `ato_id`). Montar isso no template daria uma linha
    ilegivel, e ilegivel e onde o erro se esconde.

    Sem vinculo nenhum, o rotulo diz isso em vez de mostrar um traco: deposito
    solto existe — dinheiro deixado "para quando o titulo chegar" — e nao e
    defeito.
    """
    if d.get("ri_numero"):
        return {"rotulo": f"Título {d['ri_numero']}/{d.get('ri_livro') or '1A'}"
                          " — Registro de Imóveis",
                "rota": "ri_protocolo_ver",
                "params": {"protocolo_id": d["ri_protocolo_id"]}}
    if d.get("ato_id"):
        onde = " ".join(str(x) for x in (d.get("ato_livro"), d.get("ato_folha")) if x)
        return {"rotulo": f"Ato de livro nº {d['ato_id']}"
                          + (f" ({onde})" if onde else "") + " — Notas",
                "rota": "notas_ato", "params": {"ato_id": d["nt_ato_id"]}}
    if d.get("protocolo_numero"):
        return {"rotulo": f"Protocolo {d['protocolo_numero']} — caixa",
                "rota": "caixa_protocolo",
                "params": {"protocolo_id": d["protocolo_id"]}}
    return {"rotulo": "sem vínculo", "rota": None, "params": {}}


# ------------------------------------------------- o tipo de serviço
#
# A SEGUNDA METADE DO RELATO #50 — «INFORMAÇÕES DO TIPO DE SERVIÇO».
#
# O QUE ESTAVA FALTANDO, MEDIDO EM 17/09/2026 NOS 14 DEPÓSITOS DA PRODUÇÃO
#     Seis têm vínculo: três com protocolo do balcão (dois do RI, um de Notas)
#     e três com prenotação do RI. **Oito não têm vínculo nenhum**, e nesses o
#     serviço foi escrito à mão na observação — «REGISTRO ESCRITURA DE COMPRA E
#     VENDA LAVRADA NESTA», «AVERBAÇÕES CADASTROS RURAIS», «GEORREFERENCIAMENTO
#     AGUARDANDO CUMPRIMENTO DE NOTA». É texto livre: não se soma, não se
#     filtra e não se confere.
#
# AS DUAS METADES DO TIPO, E POR QUE SÃO DUAS
#     A **atribuição** diz de que cartório é o dinheiro — é o que se soma num
#     relatório. O **serviço** diz qual item do catálogo da casa ele adianta —
#     é o que se confere contra o que foi cobrado.
#
#     E ELES VÊM DE LUGARES DIFERENTES, medido: a atribuição se **lê do
#     vínculo** — `cx_protocolos.atribuicao` quando o depósito está amarrado a
#     um protocolo do balcão, ou a própria tabela quando é prenotação do RI ou
#     ato de livro das Notas. O serviço **vem do catálogo**, que é o que a casa
#     cobra de verdade.
#
#     **DEDUZIR A ATRIBUIÇÃO DO SERVIÇO NÃO DÁ** — e isso foi medido antes de
#     escolher: dos 1.317 serviços, só **três** têm histórico suficiente em
#     protocolo para se deduzir com segurança (três usos e 90% na mesma
#     atribuição). O código do TJ parece família (13 = Tabela XIII, 16 = XVI),
#     mas o `grupo` do acervo diz que **o 13 é de Notas E de Firmas** — 1.576
#     usos de um lado e 10.310 do outro —, e o prefixo 18 (Tabela XVIII, 110
#     serviços) é de todo mundo. Por isso o campo aparece na tela para quem
#     atende confirmar, em vez de a máquina decidir sozinha.

# As atribuições da casa, na língua em que `cx_protocolos.atribuicao` já fala.
#
# MEDIDO no banco que roda em 17/09/2026: FIRMAS 13.168 · RCPN 4.882 ·
# RI 2.848 · NOTAS 235 · PROTESTO 212 · RTD 38 · OUTROS 3 · RCPJ 1. Os oito
# ficam porque os oito existem: oferecer menos faria a tela recusar atendimento
# que a casa faz. A ordem é a do dia — primeiro o que o balcão faz o dia
# inteiro, por último o que é exceção.
ATRIBUICOES: dict[str, str] = {
    "FIRMAS": "Firmas e autenticações",
    "NOTAS": "Notas — atos de livro",
    "RCPN": "Registro Civil das Pessoas Naturais",
    "RI": "Registro de Imóveis",
    "PROTESTO": "Protesto",
    "RCPJ": "Registro Civil das Pessoas Jurídicas",
    "RTD": "Registro de Títulos e Documentos",
    "OUTROS": "Outros",
}

# O `grupo` do catálogo diz A QUE ATRIBUIÇÃO o item pertence — medido.
#
# A fonte é o próprio acervo: `tbGrupoTJ` nomeia os grupos (**21** «DOS ATOS
# DOS TABELIONTAS DE NOTAS», **22** «DOS ATOS DO REGISTRO CIVIL DAS PESSOAS
# NATURAIS», **23** «DOS ATOS DO REGISTRO DE TÍTULOS E DOCUMENTOS», **24**
# «DOS ATOS DO REGISTRO DE IMÓVEIS», **25** «DOS ATOS DOS TABELIONTOS DE
# PROTESTO»), e `tbServico.intGrupo` amarra cada serviço ao seu.
#
# **O NOME DO GRUPO É UMA COISA E O QUE A CASA FAZ É OUTRA** — e a diferença
# está medida nos 13.168 protocolos: o grupo 21, que o acervo chama de «atos
# dos tabelionatos de notas», é onde o balcão registra **firmas** (10.310 usos)
# e **atos de livro** (1.576). São dois preços e dois caminhos de selo
# diferentes, e quem sabe qual dos dois é quem atende. Por isso o grupo diz
# «pode ser FIRMAS ou NOTAS», e não escolhe.
#
# **GRUPO FORA DESTA LISTA NÃO ESTREITA NADA**, e é o caso do prefixo 18
# (Tabela XVIII, 110 serviços de averbação e busca, grupo 0 no acervo): quando
# o grupo é 0 ou nulo, o campo oferece as oito atribuições em vez de esconder
# as que a casa usa. Instalação sem o grupo semeado continua funcionando.
GRUPO_E_ATRIBUICAO: dict[int, tuple[str, ...]] = {
    21: ("FIRMAS", "NOTAS"),
    22: ("RCPN",),
    23: ("RCPJ", "RTD"),
    24: ("RI",),
    25: ("PROTESTO",),
}

# Quantos serviços a busca do catálogo devolve de uma vez.
#
# O mesmo número para os dois caminhos (a lista da página e o fragmento da
# busca instantânea), pela razão de sempre: dois números divergiriam no dia em
# que alguém mexesse num só. A tabela tem 1.305 serviços — abrir a tela não é
# pedir todos.
LIMITE_DA_BUSCA_DE_SERVICOS = 30


def atribuicoes_do_grupo(grupo: Any) -> tuple[str, ...]:
    """As atribuições que aquele grupo do catálogo pode ser. Só calcula.

    Vazio quer dizer «este grupo não decide» — e é resposta, não ausência: o
    campo oferece todas em vez de esconder as que a casa usa.
    """
    try:
        return GRUPO_E_ATRIBUICAO.get(int(grupo), ())
    except (TypeError, ValueError):
        return ()


def servico_do_catalogo(con, servico_codigo: Any) -> dict | None:
    """O item do catálogo da casa, com o grupo. Só LÊ.

    Sem item devolve `None` — quem chama decide o que dizer; inventar um item
    vazio faria o depósito parecer tipado sem estar.
    """
    if not servico_codigo:
        return None
    return banco(con).um(
        """SELECT codigo, codigo_tj, descricao, grupo, ativo
             FROM cx_servicos WHERE codigo = %s""", (int(servico_codigo),))


def rotulo_do_servico(servico: dict | None) -> str:
    """Como o serviço se lê na tela e na lista. Só calcula."""
    if not servico:
        return ""
    codigo = servico.get("codigo_tj") or ""
    return (f"{codigo} — {servico.get('descricao') or ''}".strip(" —"))


def _recado_dos_ambiguos(termo: str, achados: list[dict]) -> str:
    """A recusa que diz QUAIS são. Só calcula.

    Recusar sem listar faria a pessoa procurar de novo pelo mesmo termo e
    receber o mesmo silêncio; a lista com os códigos é o que permite escolher.
    São até oito, e o resto vira «e mais N» — a mensagem inteira com trinta
    serviços é a que ninguém lê.
    """
    oito = [f"{a.get('codigo_tj') or a.get('codigo')} — {a.get('descricao') or ''}"
            for a in achados[:8]]
    resto = (f", e mais {len(achados) - 8}" if len(achados) > 8 else "")
    return (f"Achei {len(achados)} serviços com «{termo}». Escreva o código do TJ "
            f"de um deles: " + "; ".join(oito) + resto + ".")


def resolver_servico(con, termo: Any) -> dict:
    """O item do catálogo da casa a partir do que a pessoa escreveu. **SÓ LÊ.**

    Devolve `{"servico": {...}}` quando há **um só** candidato,
    `{"ambiguos": [...]}` quando há vários e `{}` quando não há nenhum.

    O CAMPO ACEITA O CÓDIGO E ACEITA A PALAVRA, e isto é decisão de desenho:
    a busca da tela do protocolo (relato #53) é instantânea porque o formulário
    dela não recarrega a página ao digitar. Aqui o formulário É o cadastro do
    depósito — Enter manda registrar —, e uma busca que sequestrasse o Enter
    faria o balcão registrar depósito sem querer. Então a busca acontece **no
    servidor**: quem digita «arquivamento» recebe o serviço quando ele é um só,
    e a lista com os códigos quando há vários. Funciona sem JavaScript, e é
    testável sem navegador.

    SÓ ESCOLHE QUANDO É UM. Com dois candidatos, escolher o primeiro da lista
    seria a máquina decidindo em cima de dinheiro — a regra do CNIB outra vez:
    prepara, mostra, e quem decide é quem atende.
    """
    texto = str(termo or "").strip()
    if not texto:
        return {}
    if texto.isdigit():
        item = servico_do_catalogo(con, int(texto))
        return {"servico": item} if item else {}
    achados = buscar_servicos(con, texto)
    # O CÓDIGO DO TJ ESCRITO À MÃO («13.17.2») ACHA MESMO COM PONTO: a busca do
    # protocolo procura por trecho, então «13.17.2» pode voltar junto com
    # «13.17.20» — e o exato, quando existe, é o que a pessoa quis dizer.
    exatos = [a for a in achados if str(a.get("codigo_tj") or "") == texto]
    if len(exatos) == 1:
        return {"servico": servico_do_catalogo(con, exatos[0].get("codigo"))}
    if len(achados) == 1:
        return {"servico": servico_do_catalogo(con, achados[0].get("codigo"))}
    return {"ambiguos": achados} if achados else {}


def buscar_servicos(con, termo: str,
                    limite: int = LIMITE_DA_BUSCA_DE_SERVICOS) -> list[dict]:
    """Os serviços do catálogo que casam com a busca, com a atribuição que o
    grupo declara. **SÓ LÊ** — a mesma consulta do protocolo (`emolumentos.buscar`,
    que já acha por código do TJ ou por palavra da descrição), com o grupo junto.

    O grupo vem numa segunda consulta, e não numa cópia da busca: duas buscas
    divergiriam no primeiro conserto, e a que a pessoa vê ao digitar deixaria
    de ser a que ela vê ao clicar.
    """
    import emolumentos as EMOL

    achados = EMOL.buscar(con, termo, limite=limite)
    if not achados:
        return []
    codigos = [int(r["codigo"]) for r in achados if r.get("codigo") is not None]
    grupos: dict[int, Any] = {}
    if codigos:
        for linha in banco(con).ler(
                """SELECT codigo, grupo FROM cx_servicos
                    WHERE codigo = ANY(%s) ORDER BY codigo""", (codigos,)):
            grupos[int(linha["codigo"])] = linha["grupo"]
    for r in achados:
        qual = atribuicoes_do_grupo(grupos.get(int(r["codigo"])))
        r["grupo"] = grupos.get(int(r["codigo"]))
        r["atribuicoes"] = qual
        # UMA atribuição só quer dizer que o grupo decidiu; duas ou nenhuma
        # quer dizer que quem decide é quem atende.
        r["atribuicao"] = qual[0] if len(qual) == 1 else None
    return achados


def _qual_do_registro(con, tabela: str, coluna: str,
                      identificador: Any) -> str | None:
    """A atribuição que o registro declara, se ela estiver no vocabulário. Só LÊ.

    `tabela` e `coluna` são constantes deste arquivo — nunca texto de fora.
    """
    if not identificador:
        return None
    valor = banco(con).valor(
        f"SELECT {coluna} FROM {tabela} WHERE id = %s", (int(identificador),))
    if not valor:
        return None
    qual = str(valor).strip().upper()
    return qual if qual in ATRIBUICOES else None


def atribuicao_do_vinculo(con, *, protocolo_id: Any = None,
                          ri_protocolo_id: Any = None,
                          nt_ato_id: Any = None) -> dict | None:
    """A atribuição que o VÍNCULO declara — e de onde ela saiu. Só LÊ.

    **É FATO LIDO, E NÃO PALPITE.** O protocolo do balcão já grava de que
    atribuição ele é (`cx_protocolos.atribuicao`, escrito pela tela que o
    abriu); a prenotação é da tabela do Registro de Imóveis; o ato de livro, do
    Tabelionato de Notas. Quem sabe disso é o registro a que o dinheiro está
    amarrado — e é por isso que depósito com vínculo não precisa perguntar.

    Devolve `{"atribuicao", "de_onde"}` ou `None` quando não há vínculo (ou
    quando o vínculo é de uma atribuição que esta casa não usa — nesse caso
    quem decide é quem atende, e não a máquina).

    A ordem importa: **o protocolo do caixa vem primeiro** porque é declaração
    explícita de quem atendeu; a tabela de destino é dedução, e só entra quando
    não há declaração.
    """
    if protocolo_id:
        bd = banco(con)
        qual = _qual_do_registro(bd, "cx_protocolos", "atribuicao", protocolo_id)
        if qual:
            numero = bd.um("SELECT numero FROM cx_protocolos WHERE id = %s",
                           (int(protocolo_id),))
            return {"atribuicao": qual,
                    "de_onde": f"o protocolo {numero['numero'] if numero else ''}".strip()}
    if ri_protocolo_id:
        # A prenotação mora em `ri_protocolos`, que é a tabela de protocolo do
        # Registro de Imóveis — a atribuição é a da tabela, não uma suposição.
        return {"atribuicao": "RI", "de_onde": "a prenotação do Registro de Imóveis"}
    if nt_ato_id:
        # `nt_atos` é o ato de LIVRO do Tabelionato de Notas.
        return {"atribuicao": "NOTAS", "de_onde": "o ato de livro do Tabelionato"}
    return None


def sugerir_tipo(con, *, protocolo_id: Any = None,
                 ri_protocolo_id: Any = None, nt_ato_id: Any = None,
                 servico_codigo: Any = None) -> dict:
    """O que o sistema já sabe do tipo, antes de a pessoa escolher. Só LÊ.

    Devolve `{"atribuicao", "de_onde", "servico", "servico_codigo",
    "atribuicoes", "aviso"}`:

      · `servico` — o item do catálogo, o que foi informado ou, não havendo
        nenhum, **o item único do protocolo**: com um item só, o depósito é
        daquele serviço; com vários, ele cobre o conjunto, e escolher um deles
        seria escolher por quem atende;
      · `atribuicao` — a que veio do vínculo, ou a que o grupo do serviço
        declara quando o grupo decide uma só;
      · `de_onde` — a frase que diz de onde ela saiu («o protocolo 2026.08.146»,
        «o serviço 16.24.4»), porque sugestão sem procedência é palpite;
      · `atribuicoes` — as que o campo deve OFERECER: as do grupo quando ele
        estreita (um serviço de Notas não faz ninguém procurar Protesto),
        senão as oito;
      · `aviso` — quando o vínculo e o serviço discordam. **O vínculo ganha** —
        a mesma ordem do selo, onde o código do ato precede o texto —, e a
        divergência aparece em vez de sumir.
    """
    bd = banco(con)
    do_vinculo = atribuicao_do_vinculo(
        bd, protocolo_id=protocolo_id, ri_protocolo_id=ri_protocolo_id,
        nt_ato_id=nt_ato_id)
    servico = servico_do_catalogo(bd, servico_codigo)
    if not servico and protocolo_id:
        # O ITEM ÚNICO DO PROTOCOLO.
        itens = bd.ler(
            """SELECT servico_codigo FROM cx_protocolo_atos
                WHERE protocolo_id = %s AND servico_codigo IS NOT NULL
                ORDER BY id""",
            (int(protocolo_id),))
        if len(itens) == 1:
            servico = servico_do_catalogo(bd, itens[0]["servico_codigo"])
    do_grupo = atribuicoes_do_grupo(servico.get("grupo") if servico else None)
    uma_so_do_grupo = do_grupo[0] if len(do_grupo) == 1 else None

    escolhida, de_onde = None, None
    if do_vinculo:
        escolhida, de_onde = do_vinculo["atribuicao"], do_vinculo["de_onde"]
    elif uma_so_do_grupo:
        escolhida = uma_so_do_grupo
        de_onde = f"o serviço {rotulo_do_servico(servico)}"

    aviso = None
    if do_vinculo and do_grupo and do_vinculo["atribuicao"] not in do_grupo:
        # O vínculo é fato; o grupo do serviço diz por quais tabelas ele passa.
        # Discordarem não é empate a desempatar por ordem: é uma das duas
        # coisas que está errada, e quem sabe qual é quem atende.
        aviso = (f"O vínculo diz {ATRIBUICOES[do_vinculo['atribuicao']]} "
                 f"({do_vinculo['de_onde']}) e o serviço escolhido passa pelas "
                 f"tabelas de "
                 f"{' e '.join(ATRIBUICOES[a] for a in do_grupo)}. Ficou valendo "
                 f"o vínculo — confira qual dos dois está certo.")

    oferecidas = do_grupo or tuple(ATRIBUICOES)
    if escolhida and escolhida not in oferecidas:
        # Quem estreita o campo é o grupo do serviço; o vínculo, porém, é fato —
        # e esconder dele a atribuição faria a lista gravar outra coisa.
        oferecidas = (escolhida,) + oferecidas

    return {"atribuicao": escolhida, "de_onde": de_onde, "servico": servico,
            "servico_codigo": servico["codigo"] if servico else None,
            "atribuicoes": oferecidas, "aviso": aviso}


def tipo_do_deposito(con, d) -> dict:
    """Como o tipo daquele depósito se lê na lista. Só LÊ.

    **O QUE ESTÁ GRAVADO MANDA**; o que não estiver é lido do vínculo e
    marcado como tal. É a regra do CNM: o que se calcula pode ser mostrado sem
    ser gravado — e o que veio do vínculo aparece com a procedência à vista,
    porque quem confere precisa saber se aquilo alguém escolheu ou o sistema
    deduziu.

    Devolve `{"atribuicao", "rotulo", "de_onde", "servico", "rotulo_servico",
    "origem"}`, com `origem` em `GRAVADO | VINCULO | NENHUM`.
    """
    gravada = (d.get("atribuicao") or "").strip().upper() or None
    servico = None
    if d.get("servico_codigo_tj") or d.get("servico_descricao"):
        servico = {"codigo": d.get("servico_codigo"),
                   "codigo_tj": d.get("servico_codigo_tj"),
                   "descricao": d.get("servico_descricao")}
    rotulo_servico = rotulo_do_servico(servico)
    if gravada:
        return {"atribuicao": gravada, "rotulo": ATRIBUICOES.get(gravada, gravada),
                "de_onde": None, "servico": servico,
                "rotulo_servico": rotulo_servico, "origem": "GRAVADO"}
    do_vinculo = atribuicao_do_vinculo(
        con, protocolo_id=d.get("protocolo_id"),
        ri_protocolo_id=d.get("ri_protocolo_id"), nt_ato_id=d.get("nt_ato_id"))
    if do_vinculo:
        return {"atribuicao": do_vinculo["atribuicao"],
                "rotulo": ATRIBUICOES.get(do_vinculo["atribuicao"], ""),
                "de_onde": do_vinculo["de_onde"], "servico": servico,
                "rotulo_servico": rotulo_servico, "origem": "VINCULO"}
    return {"atribuicao": None, "rotulo": "", "de_onde": None, "servico": servico,
            "rotulo_servico": rotulo_servico, "origem": "NENHUM"}


def gravar_tipos_do_vinculo(con) -> dict:
    """Grava a atribuição dos depósitos que TÊM vínculo e ainda não têm tipo.

    ESCREVE — e é botão de apertar uma vez, de propósito.

    **A ATRIBUIÇÃO DELES É FATO LIDO DO VÍNCULO, NÃO PALPITE** (decisão do
    oficial em 17/09/2026): dos 14 depósitos da produção, seis estão amarrados
    a protocolo ou prenotação, e nesses o cartório já sabe a resposta. O
    serviço só é preenchido quando o protocolo tem **um item só** — com vários
    itens o depósito cobre um conjunto, e escolher um deles seria escolher por
    quem atende.

    Os que não têm vínculo — oito dos catorze — **ficam sem tipo**, e a lista
    declara isso: é o estado honesto, e a tela diz o que fazer (abrir o depósito
    e escolher). O contador `sem_tipo` conta também o vínculo que não declara
    atribuição, porque para quem lê o resultado a pergunta é a mesma.

    Devolve os contadores, para a tela poder dizer o que fez — mudar linha em
    silêncio é o que faz a conferência desconfiar do sistema.
    """
    bd = banco(con)
    linhas = [tuple(r.values()) for r in bd.ler(
        """SELECT id, protocolo_id, ri_protocolo_id, nt_ato_id, atribuicao,
                  servico_codigo
             FROM cx_depositos ORDER BY id""")]
    gravados = servicos = sem_tipo = 0
    for did, protocolo_id, ri_protocolo_id, nt_ato_id, qual, servico in linhas:
        if qual:
            continue
        # A MESMA RÉGUA DO CADASTRO — `sugerir_tipo` —, e não uma segunda
        # leitura do vínculo: o que o botão grava tem de ser o que a tela ia
        # gravar se aquele depósito fosse registrado hoje.
        dica = sugerir_tipo(bd, protocolo_id=protocolo_id,
                            ri_protocolo_id=ri_protocolo_id,
                            nt_ato_id=nt_ato_id, servico_codigo=servico)
        if not dica["atribuicao"]:
            sem_tipo += 1
            continue
        item = dica["servico_codigo"]
        bd.escrever(
            """UPDATE cx_depositos
                  SET atribuicao = %s, servico_codigo = COALESCE(%s, servico_codigo)
                WHERE id = %s""",
            (dica["atribuicao"], item, int(did)))
        gravados += 1
        if item and not servico:
            servicos += 1
    return {"gravados": gravados, "com_servico": servicos,
            "sem_tipo": sem_tipo}


# ------------------------------------------ o deposito que paga o selo (LX16)
#
# «Não tem como permitir selo pago sem um protocolo e sem o registro de que o
#  item foi pago ou entrou antes em depósito prévio» — o oficial, 19/10/2026
#
# O DEPÓSITO PAGA O ITEM, E NÃO O SELO. O débito quita o item do protocolo
# (`quitado`), e é a quitação que a trava do selo lê: o segundo selo do mesmo
# item acha o item pago e não debita de novo. Debitar por selo cobraria o
# cliente duas vezes pelo mesmo serviço.
#
# SEM SALDO NEGATIVO E SEM DOIS DÉBITOS DO MESMO SALDO. O saldo se lê e se
# grava com a linha presa (FOR UPDATE), como no «usar» da tela do caixa; e o
# item também fica preso, para dois selos do mesmo item ao mesmo tempo não o
# pagarem duas vezes.

SCHEMA_USOS = """
CREATE TABLE IF NOT EXISTS cx_deposito_usos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    deposito_id bigint NOT NULL,
    valor_centavos bigint NOT NULL,
    saldo_depois_centavos bigint NOT NULL,
    protocolo_id bigint,
    item_id bigint,
    tabela TEXT,
    ato_id bigint,
    motivo TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT
)
"""


class DepositoSemSaldo(ValueError):
    """O depósito não cobre o valor — frase de balcão, sem número de erro."""


def init_usos_schema(con) -> None:
    """O rastro de cada débito do depósito. Idempotente."""
    banco(con).escrever(SCHEMA_USOS)


def do_protocolo(con, protocolo_id, *, tabela: str | None = None,
                 ato_id: int | None = None) -> list[dict]:
    """Os depósitos com saldo que podem pagar este protocolo. Só LÊ.

    Do protocolo é o depósito amarrado a ele, à MESMA prenotação do RI (o
    dinheiro deixado no título) ou, nas Notas, ao mesmo ato de livro. Depósito
    solto não entra: usar dinheiro de outro cliente seria pior que não selar.
    """
    from caixa_schema import centavos
    bd = banco(con)
    condicoes = ["d.protocolo_id = %(p)s",
                 """(d.ri_protocolo_id IS NOT NULL AND d.ri_protocolo_id =
                     (SELECT c.ri_protocolo_id FROM cx_protocolos c
                       WHERE c.id = %(p)s))"""]
    if tabela == "nt_atos" and ato_id is not None:
        condicoes.append("d.nt_ato_id = %(a)s")
    linhas = bd.ler(
        f"""SELECT d.* FROM cx_depositos d
             WHERE coalesce(d.encerrado, 0) = 0
               AND ({' OR '.join(condicoes)})
             ORDER BY d.data, d.id""",
        {"p": int(protocolo_id), "a": int(ato_id or 0)})
    return [d for d in linhas if centavos(d["saldo"]) > 0]


def saldo_do_protocolo(con, protocolo_id, **kw) -> int:
    """Quanto há, em centavos, nos depósitos que podem pagar o protocolo."""
    from caixa_schema import centavos
    return sum(centavos(d["saldo"]) for d in do_protocolo(con, protocolo_id, **kw))


def debitar(con, deposito_id: int, valor_centavos: int, *, agora: str,
            quem: str | None = None, protocolo_id: int | None = None,
            item_id: int | None = None, tabela: str | None = None,
            ato_id: int | None = None, motivo: str | None = None) -> dict:
    """Tira do saldo do depósito, sem nunca deixá-lo negativo. ESCREVE.

    Recusa com `DepositoSemSaldo` — e não grava nada — quando o saldo DE
    AGORA (lido com a linha presa) não cobre o valor.
    """
    from caixa_schema import centavos
    valor = int(valor_centavos or 0)
    if valor <= 0:
        raise DepositoSemSaldo("O valor a debitar tem de ser maior que zero.")
    bd = banco(con)
    bd._escrita()
    d = bd.um("SELECT * FROM cx_depositos WHERE id = %s FOR UPDATE",
              (int(deposito_id),))
    if not d or int(d["encerrado"] or 0):
        raise DepositoSemSaldo("Este depósito prévio não existe mais ou já foi encerrado.")
    saldo = centavos(d["saldo"])
    if valor > saldo:
        raise DepositoSemSaldo(
            f"O depósito {d['numero'] or d['id']} tem R$ {reais(saldo)} e o "
            f"item custa R$ {reais(valor)}. Falta R$ {reais(valor - saldo)}: "
            f"registre o pagamento da diferença no caixa.")
    novo = saldo - valor
    bd.escrever(
        """UPDATE cx_depositos SET saldo = %s, encerrado = %s, atualizado_em = %s
            WHERE id = %s""",
        (reais(novo), 1 if novo == 0 else 0, agora, int(deposito_id)))
    if bd.tem_tabela("cx_deposito_usos"):
        bd.escrever(
            """INSERT INTO cx_deposito_usos
                   (deposito_id, valor_centavos, saldo_depois_centavos,
                    protocolo_id, item_id, tabela, ato_id, motivo, criado_em,
                    criado_por)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (int(deposito_id), valor, novo, protocolo_id, item_id, tabela,
             ato_id, motivo, agora, quem))
    return {"deposito_id": int(deposito_id), "numero": d["numero"],
            "valor_centavos": valor, "saldo_centavos": novo}


def pagar_item(con, item_id: int, *, agora: str, quem: str | None = None,
               tabela: str | None = None, ato_id: int | None = None) -> dict | None:
    """Quita o item do protocolo com o depósito prévio, se houver saldo. ESCREVE.

    Devolve o débito feito, `{"ja_quitado": True}` se outro selo pagou o item
    enquanto este esperava a trava, ou None quando nenhum depósito cobre o
    valor (ou o item não tem valor — e sem valor não há o que debitar).
    """
    import caixa_protocolo as CXP
    from caixa_schema import centavos
    bd = banco(con)
    bd._escrita()
    linha = bd.um("SELECT * FROM cx_protocolo_atos WHERE id = %s FOR UPDATE",
                  (int(item_id),))
    if not linha:
        return None
    if CXP._sim(linha["quitado"]):
        return {"ja_quitado": True}
    valor = centavos(linha["valor_total"])
    if valor <= 0:
        return None
    for d in do_protocolo(bd, linha["protocolo_id"], tabela=tabela, ato_id=ato_id):
        if centavos(d["saldo"]) < valor:
            continue
        try:
            feito = debitar(bd, d["id"], valor, agora=agora, quem=quem,
                            protocolo_id=linha["protocolo_id"], item_id=int(item_id),
                            tabela=tabela, ato_id=ato_id,
                            motivo="Quitação do item pelo depósito prévio (selo)")
        except DepositoSemSaldo:
            # Outro balcão gastou o saldo entre a lista e a trava: tenta o
            # próximo depósito, e não estoura.
            continue
        quitar_o_item(bd, linha, feito, agora=agora)
        return feito
    return None


def quitar_o_item(con, item: dict, feito: dict, *, agora: str) -> None:
    """Marca o item como pago pelo depósito e regrava o protocolo. ESCREVE.

    A MESMA MARCA NOS DOIS CAMINHOS QUE PAGAM O ITEM COM O DEPÓSITO — o selo
    (`pagar_item`) e o «usar» da tela do caixa (LD06). `quitado_por` começa
    por «DEPÓSITO PRÉVIO»: é por ela que o estorno da reserva do selo sabe
    que a quitação é do depósito, e que o caixa recusa cobrar o item de novo
    ou reabri-lo sem devolver o dinheiro.
    """
    import caixa_protocolo as CXP
    bd = banco(con)
    bd.escrever(
        """UPDATE cx_protocolo_atos
              SET quitado = 1, quitado_em = %s, quitado_por = %s
            WHERE id = %s""",
        (agora, f"DEPÓSITO PRÉVIO {feito['numero'] or feito['deposito_id']}",
         int(item["id"])))
    CXP.atualizar_situacao(bd, item["protocolo_id"])


# ------------------------------- o «usar» da tela do caixa quita o item (LD06)
#
# «Praticado o ato notarial ou de registro para o qual o depósito prévio foi
#  efetuado, o valor correspondente deverá ser baixado do Livro de Controle de
#  Depósito Prévio e lançado como receita» — CN-MA art. 202.
#
# O DEFEITO, MEDIDO PELO LT06 (20/10/2026): «usar» o depósito na tela do caixa,
# com o número do protocolo, baixava o saldo e lançava o uso, mas NÃO quitava
# o item. O protocolo continuava A_PAGAR, a trava do selo pedia pagamento de
# novo e o item ainda podia ser quitado em dinheiro — o cliente pagava duas
# vezes. Quem quitava era só o quadro «Selo e caixa» (`pagar_item`).
#
# AGORA OS DOIS SÃO UM CAMINHO SÓ para o item: o débito de `debitar` (com o
# rastro em `cx_deposito_usos`, que o livro lê com o item) e a marca de
# `quitar_o_item`. O que o valor usado não cobre de item inteiro continua sendo
# o uso de sempre — dinheiro do depósito que vira receita sem item no protocolo.


def prender_itens_a_pagar(con, protocolo_id: int) -> list[dict]:
    """Os itens do protocolo ainda a pagar, PRESOS, na ordem em que entraram.

    PRESOS ANTES DO DEPÓSITO, na ordem de `pagar_item` (item → depósito →
    protocolo): o «usar» e o selo do mesmo protocolo, presos em ordens
    contrárias, se esperariam um ao outro, e o PostgreSQL derrubaria um dos
    dois por deadlock.
    """
    bd = banco(con)
    bd._escrita()
    return bd.ler(
        """SELECT * FROM cx_protocolo_atos
            WHERE protocolo_id = %s AND coalesce(quitado, 0) = 0
            ORDER BY id FOR UPDATE""", (int(protocolo_id),))


def quitar_itens_com_o_deposito(con, deposito_id: int, itens: list[dict],
                                valor_centavos: int, *, agora: str,
                                quem: str | None = None) -> list[dict]:
    """Quita, com o valor usado do depósito, os itens que ele cobre. ESCREVE.

    `itens` são os de `prender_itens_a_pagar` — já presos. Cada item, na ordem
    do protocolo, é quitado INTEIRO se o que resta do valor cobre o preço
    dele; o que não cabe fica a pagar e o seguinte é tentado — meio item pago
    não existe no caixa, e parar no primeiro que não cabe deixaria a pagar um
    item que o dinheiro já usado cobria (e o cliente o pagaria de novo).

    O saldo de quem chama já foi conferido com a linha do depósito presa; o
    débito de cada item passa por `debitar`, que confere de novo. Devolve os
    débitos feitos, um por item, com o item dentro.
    """
    from caixa_schema import centavos
    bd = banco(con)
    resta = int(valor_centavos or 0)
    feitos = []
    for item in itens:
        preco = centavos(item.get("valor_total"))
        if preco <= 0 or preco > resta:
            continue
        feito = debitar(bd, deposito_id, preco, agora=agora, quem=quem,
                        protocolo_id=int(item["protocolo_id"]),
                        item_id=int(item["id"]),
                        motivo="Quitação do item pelo uso do depósito prévio "
                               "(tela do caixa)")
        quitar_o_item(bd, item, feito, agora=agora)
        feitos.append(feito | {"item": item})
        resta -= preco
    return feitos
