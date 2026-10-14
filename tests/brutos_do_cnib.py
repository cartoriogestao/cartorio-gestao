"""As respostas do CNIB, **transcritas** dos brutos de 18/09/2026.

POR QUE ISTO EXISTE, e não é preguiça de digitar. Os testes deste projeto
montam o dado de que precisam — e quando o dado vem de uma API de fora,
"montar" quer dizer **inventar**, e o teste passa a provar que o programa
entende o que eu imaginei que a Central manda. Foi assim que o `dadosSelo`
embrulhado sobreviveu a 37 testes verdes: eles comparavam o envelope real
contra a minha ideia do envelope real, dos dois lados da mesma suposição.

**Não foi o que aconteceu aqui.** As três formas de resposta do CNIB
apareceram **medindo** — e uma delas, a vazia, vem **embrulhada duas vezes**
(`data.data.orders`) e em camelCase, e não está em contrato nenhum. A régua
dos nomes — `paginação` com til no contrato, `paginacao` sem til na resposta —
só se soube lendo os dois. Um fixture inventado parecido estaria testando a
invenção, e as três formas são justamente o que este módulo tem de acertar.

O QUE FOI TROCADO, e **só isto**, para a transcrição continuar sendo cópia:
nome de pessoa, documento e endereço de e-mail das partes e de quem assinou a
ordem na Central. **O formato ficou**: o CPF continua com pontos e traço, o
CNPJ continua com catorze dígitos, o e-mail continua `.jus.br`. Protocolos,
datas, status, a hierarquia do tribunal, os nulos e a ordem dos campos estão
**como vieram** — é por isso que esta cópia serve para escrever teste.

AS QUATRO COISAS QUE ESTES BRUTOS ENSINAM, e cada uma tem teste:

1. **A ordem de pedido tem 13 campos e a de cancelamento tem 16** — as mesmas
   13 mais `cancelamentodeindisponibilidade`, `cancelamentotipo` e
   `cancelamentodata`. Não há campo a mais nem a menos em nenhuma delas.
2. **O documento da parte vem com máscara numa ordem e sem máscara na outra**,
   na mesma API, no mesmo dia. Quem gravar o que veio guarda as duas formas, e
   quem comparar por igualdade **não acha** — é a armadilha que a casa já pagou
   no CNIB (a busca por nome que devolvia zero).
3. **`ordemprioritaria` e `segredodejustica` vêm `None` nas ordens antigas** e
   `False` nas de 2026. `None` não é `False`: um é «não se aplica a este
   pedido», o outro é «não é prioritária» — e um portão que tratasse os dois
   como falso passaria nos dois sem nunca ter medido a diferença.
4. **`matricula` é uma LISTA, sempre vazia** — o campo existe, é o que ligaria
   a ordem ao imóvel, e não veio preenchido em nenhuma das 6.218.

E a paginação tem os nomes dela, que **não são os do contrato**: a resposta
manda `paginacao`, `pagina_atual`, `total_ordens_encontradas`,
`total_ordens_retornadas_por_pagina`, `ordens_restantes` e
`tem_proxima_pagina`; o contrato declara `paginação`, `pageIndex`, `totalRows`,
`pageSize` e `pageForward`. **Zero nomes em comum.**

COMO SE USA

    from brutos_do_cnib import (ORDEM_DE_PEDIDO, PAGINACAO_SEM_PROXIMA,
                                envelope)

    resposta = envelope([ORDEM_DE_PEDIDO], PAGINACAO_SEM_PROXIMA)

**`envelope` exige a paginação, e não tem padrão.** Um padrão que dissesse
«não há próxima» faria o teste do laço rodar uma página e passar — verde sobre
o defeito que ele existe para pegar.
"""

# ======================================================= as ordens, uma a uma
#
# Transcritas de `tmp/_p72pag_4f.json` (índice 0 de uma página de 500, janela de
# junho/2026) e de `tmp/_p72cf_dia_2026-09-15.json`. Os dois brutos estão com a
# data no nome porque a Central muda de forma sem avisar: **o que se guarda de
# uma medição é o instante dela**, e não a promessa de que continua assim.

# A ORDEM QUE PEDE INDISPONIBILIDADE. É a forma normal: 13 campos, uma parte,
# `ordemprioritaria` e `segredodejustica` presentes e falsos (ordem de 2026).
ORDEM_DE_PEDIDO: dict = {
    "status": "INDISPONIBILIDADE",
    "protocoloindisponibilidade": "202606.0116.04723776-IA-912",
    "numeroprocesso": "00008262320255140426",
    "usuario": "SERVIDOR(A) DE EXEMPLO TRT14",
    "ordemstatus": "CONCLUÍDO",
    "nomeinstituicao": ("Divisão de Pesquisa Patrimonial > Tribunal Regional "
                        "do Trabalho da 14° Região > Tribunal Superior do "
                        "Trabalho > RIO BRANCO"),
    "forumvara": "Divisão de Pesquisa Patrimonial",
    "email": "servidor.exemplo@trt14.jus.br",
    "telefone": None,
    "datapedido": "01/06/2026 16:34:45",
    "ordemprioritaria": False,
    "segredodejustica": False,
    "partes": [
        {
            "cpfcnpj": "000.000.000-00",
            "nomerazao": "PARTE DE EXEMPLO",
            "matricula": [],
        },
    ],
}

# A ORDEM QUE DESFAZ OUTRA. **Ela traz os dois protocolos**, e é esta linha que
# faz o atualizador conseguir desativar sem adivinhar: `protocoloindisponibilidade`
# é o da ordem **cancelada** (`201210...-IA-300`, de 2012) e
# `cancelamentodeindisponibilidade` é o do **próprio cancelamento**
# (`202609...-TA-819`, de 15/09/2026).
#
#     repare nas duas datas: o pedido é de 2012 e o cancelamento, de 2026.
#     É por isso que a janela da casa filtra por `cancelamentodata` — uma
#     janela de 2026 devolve ordem com `datapedido` de 2012, e quem olhasse
#     `datapedido` concluiria que a Central mandou coisa velha.
ORDEM_DE_CANCELAMENTO: dict = {
    "status": "CANCELAMENTO",
    "cancelamentodeindisponibilidade": "202609.1516.00002883-TA-819",
    "cancelamentotipo": 1,
    "cancelamentodata": "15/09/2026 04:49:06",
    "protocoloindisponibilidade": "201210.2318.00002883-IA-300",
    "numeroprocesso": "00479537820128260053",
    "usuario": "SERVIDOR(A) DE EXEMPLO TJSP",
    "ordemstatus": "CONCLUÍDO",
    "forumvara": "5 OFICIO DA FAZENDA PUBLICA",
    "nomeinstituicao": ("Tribunal de Justiça do Estado de São Paulo > Superior "
                        "Tribunal de Justiça > São Paulo - Capital > HELY "
                        "LOPES MEIRELLES > 5 OFICIO DA FAZENDA PUBLICA"),
    "email": "servidor.exemplo@tjsp.jus.br",
    "telefone": "11-11111111",
    "datapedido": "23/10/2012 18:06:57",
    "ordemprioritaria": None,
    "segredodejustica": None,
    "partes": [
        {
            "cpfcnpj": "000.000.000-00",
            "nomerazao": "PARTE DE EXEMPLO",
            "matricula": [],
        },
    ],
}

# A MESMA FORMA, COM AS TRÊS RARIDADES JUNTAS — transcrita de
# `tmp/_p72final_fila_p1.json`, onde ela apareceu:
#
#   * `ordemstatus` **"Cancelamento total - Concluido"**, a terceira grafia. É a
#     que derrubou a régua que eu havia escrito (`startswith("concluido")`): ela
#     **não começa** com a palavra, e as três ordens assim seriam lidas como não
#     concluídas. A régua certa é igualdade contra o vocabulário medido.
#   * **duas partes** — uma pessoa física e uma empresa, com o mesmo nome na
#     raiz (`... - EPP (CARTONAGEM MARTINS)`). É a forma que a carga nova tem de
#     aguentar: 40% das ordens têm mais de uma parte, e o espelho de hoje guarda
#     **uma só**.
#   * **documento sem máscara** — `00000001910` e `00000015000150`, contra
#     `000.000.000-00` das outras duas. Os dois formatos saem da mesma API.
ORDEM_DE_CANCELAMENTO_ANTIGA: dict = {
    "status": "CANCELAMENTO",
    "cancelamentodeindisponibilidade": "202502.0515.00006352-TA-351",
    "cancelamentotipo": 1,
    "cancelamentodata": "05/02/2025 04:45:03",
    "protocoloindisponibilidade": "201303.1412.00006352-IA-000",
    "numeroprocesso": "00001547020124036113",
    "usuario": "SERVIDOR(A) DE EXEMPLO TRF3",
    "ordemstatus": "Cancelamento total - Concluido",
    "forumvara": "1ª VARA FEDERAL DE FRANCA",
    "nomeinstituicao": ("Tribunal Regional Federal da Terceira Região > "
                        "FRANCA > 1ª VARA FEDERAL DE FRANCA"),
    "email": "servidor.exemplo@trf3.jus.br",
    "telefone": None,
    "datapedido": "14/03/2013 17:55:56",
    "ordemprioritaria": None,
    "segredodejustica": None,
    "partes": [
        {
            "cpfcnpj": "00000000000",
            "nomerazao": "PARTE PESSOA FISICA DE EXEMPLO",
            "matricula": [],
        },
        {
            "cpfcnpj": "00000000000000",
            "nomerazao": "PARTE EMPRESA DE EXEMPLO - EPP (RAZAO SOCIAL DE EXEMPLO)",
            "matricula": [],
        },
    ],
}


# ============================================================== a paginação
#
# Transcritas de `tmp/_p72pag_1f.json` e `tmp/_p72cf_dia_2026-09-15.json`. O
# `total_ordens_encontradas: 1757` com `total_ordens_retornadas_por_pagina: 500`
# é o caso que importa: **a Central diz que há 1.757 e devolve 500**, e quem
# ler o total como «o que vem nesta resposta» grava 1.257 ordens que nunca
# chegaram.

PAGINACAO_COM_PROXIMA: dict = {
    "pagina_atual": 1,
    "total_ordens_encontradas": 1757,
    "total_ordens_retornadas_por_pagina": 500,
    "ordens_restantes": 1257,
    "tem_proxima_pagina": True,
}

PAGINACAO_SEM_PROXIMA: dict = {
    "pagina_atual": 1,
    "total_ordens_encontradas": 1,
    "total_ordens_retornadas_por_pagina": 1,
    "ordens_restantes": 0,
    "tem_proxima_pagina": False,
}


# ================================================== as formas que não são ordem
#
# As duas que **não trazem lista de ordens**, transcritas inteiras — e são
# inteiras de propósito: o que se testa aqui é o embrulho, e o embrulho é
# justamente o que um fixture recortado perderia.

# A VAZIA, que é a segunda forma: embrulhada **duas vezes** e em camelCase
# (`data.data.orders`, `data.data.totalCount`), com a frase que **não** prova
# ausência. Medido em 18/09/2026: esta mesma forma, com esta mesma frase, veio
# para dias que **tinham** ordens — e horas depois as ordens apareceram. É por
# isso que o transporte devolve `vazio` e não `sem_ordens`.
ENVELOPE_VAZIA: dict = {
    "data": {
        "data": {
            "orders": [],
            "totalCount": 0,
        },
        "identifierRequest": "800041ef-0004-2d00-b63f-84710c7967bb",
        "success": True,
        "message": "Não há ordens para os critérios informados.",
        "status": 200,
    },
    "identifierRequest": "800041ef-0004-2d00-b63f-84710c7967bb",
    "success": True,
    "message": "Sucesso!",
    "status": 200,
}

# A CONSULTA POR DOCUMENTO, que é a terceira forma: `data.protocolos`, e não
# `data.ordens`. **Não tem paginação porque não tem lista** — é o retrato de
# agora de um documento, e não uma janela.
#
# **E ela traz o recibo de quem perguntou**, no bloco `dados_usuario`: nome,
# documento, data e a serventia. É o que a Central registra de quem consultou,
# e é por isso que o `cpf_usuario` é parâmetro obrigatório do transporte e não
# uma constante escondida — **quem aparece como autor da consulta é quem o
# número diz que é**, e a tela tem de mostrar isso antes de alguém clicar.
#
#     A CONFERIR, e é pergunta para o oficial: as medições foram feitas com o
#     CPF que a Central devolve neste bloco, que **não é o do delegatário**.
#     A decisão registrada foi «o do delegatário, configurável na tela» — o
#     parâmetro é configurável desde já, e o que falta é ele dizer qual número
#     entra ali. Não se troca por conta própria: o recibo é dele.
ENVELOPE_CONSULTA: dict = {
    "data": {
        "documento": "00.000.000/0000-00",
        "nomeRazao": "EMPRESA DE EXEMPLO LTDA",
        "indisponivel": False,
        "qtdOrdens": 0,
        "protocolos": [],
        "dados_usuario": {
            "hash": "hcgidj036h",
            "data": "18/09/2026 13:05:27",
            "nome": "OPERADOR(A) DE EXEMPLO",
            "documento": "000.000.000-00",
            "organizacao": ("SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO - "
                            "OFICIO UNICO"),
            "filtros": None,
        },
    },
    "identifierRequest": "80000332-0800-c900-b63f-84710c7967bb",
    "success": True,
    "message": "Sucesso!",
    "status": 200,
}


def envelope(ordens: list, paginacao: dict) -> dict:
    """A resposta **normal** (`data.ordens` mais `data.paginacao`), montada.

    Os dois argumentos são obrigatórios, e a razão está no cabeçalho de cima:
    um padrão para a paginação faria o teste do laço parar na primeira página e
    passar.

    O `identifierRequest` e o `success` são os da resposta real — eles não
    entram em decisão nenhuma, e é por isso mesmo que ficam: o dia em que
    alguém passar a lê-los, o teste não vai estar medindo um objeto que só
    existe aqui.
    """
    return {
        "data": {
            "ordens": list(ordens),
            "paginacao": dict(paginacao),
        },
        "identifierRequest": "80000332-0800-c900-b63f-84710c7967bb",
        "success": True,
        "message": "Sucesso!",
        "status": 200,
    }
