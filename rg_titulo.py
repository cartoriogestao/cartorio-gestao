"""
O TÍTULO APRESENTADO no RCPJ e no RTD — do protocolo ao registro.

O PEDIDO DO OFICIAL, EM 03/09/2026
    «Preciso que o sistema receba o título em protocolo, esteja disponível
     para analisar no visualizador de pdf direto no sistema, disponível para
     baixar, se positiva a qualificação possa imprimir a etiqueta de registro
     para o título apresentado em papel, ou encaminhamento pela ONRTDPJ para
     os eletrônicos. Verificar o que o e-ofício pode nos ensinar.»

    São cinco coisas, e elas formam **um caminho só**: o título entra, é lido,
    é qualificado, e sai — pela etiqueta se veio em papel, pela Central se veio
    eletrônico.

O QUE O E-OFÍCIO ENSINOU, MEDIDO EM 03/09/2026 CONTRA O ACERVO
    **1. O protocolo é UM, e serve as seis atribuições.** `tbProtocoloGeral`,
    21.360 linhas, com `intAtribuicao` dizendo de quem é cada uma — 13.176 de
    Notas, 4.862 do RCPN, 2.838 do RI, 231 do RTD, 212 do Protesto, 38 do
    RCPJ. Nesta casa esse protocolo já existe: é o `cx_protocolos` do balcão, e
    `rg_titulos.protocolo_geral_id` é a ponte com ele — do mesmo feitio de
    `cx_protocolos.ri_protocolo_id`, que já liga a prenotação do RI.

    **2. E o título tem um SEGUNDO número, o da atribuição.**
    `tbRegistroTD.intProtocolo` (1.275 no último registro do RTD) ao lado de
    `strProtocoloGeral` ('2026.01.164'). Os dois contadores estão em
    `tbTD_Propriedade`: `intProtocolo_RTD` = 1.275 e `intProtocolo_RPJ` =
    1.273. Guardar só um perderia metade da amarração — e é justamente o
    segundo que vai na etiqueta e na certidão.

    **3. O Livro de Protocolo já estava declarado aqui, e ninguém escrevia
    nele.** `livro_nucleo` traz `PJ_PROTOCOLO` e `TD_PROTOCOLO` desde
    21/08/2026, diários, com termo contínuo, citando esses mesmos contadores —
    e nenhuma tela jamais os usou. Este módulo é a tela que faltava.

    **4. O E-Ofício abria protocolo e NUNCA O FECHAVA.** Medido: `bitFinalizado
    = 0` em 21.360 de 21.360; `dtmFinalizado` vazia em todas; as 9.987
    ocorrências de situação são **todas** o código 1, «Aberto protocolo geral»;
    e os 9.988 trâmites são **todos** do setor 0 para o setor 0. A máquina de
    situação (cinco estados), de trâmite entre setores e de finalização existia
    inteira **e nunca foi exercitada**.

        É por isso que aqui a situação do título não é enfeite: **um protocolo
        que só abre é um diário, não é um protocolo.** As situações deste
        módulo são as que alguma rota consegue produzir, e há teste que exige
        isso de cada uma.

    **5. O título apresentado não tinha lugar no E-Ofício.** As 155 imagens de
    `tbTD_Img` estão amarradas ao REGISTRO (`intnumeroregistro`), e não ao
    protocolo: eram a digitalização do livro depois do ato. E as colunas do
    documento do apresentante — `strPet` e `strPetImg` — estão **vazias em 72
    de 72**. Ou seja: **o título como entrou não era guardado**. É a lacuna que
    este módulo fecha, e ela não é pequena — sem ela, quem qualifica não tem o
    que ler na tela.

    **6. E os caminhos dos arquivos apontavam para fora.** Das 155 imagens,
    umas vão para `\\\\servidor\\C11\\RTD_RPJ\\` e outras para
    `C:\\Users\\<usuario>\\Desktop\\PJ_345_0.png` — a Área de Trabalho de alguém.
    Aqui o arquivo vai para a pasta de arquivos da casa, pela `attachments`,
    que já serve expediente, tarefa, protocolo do RI e termo do RCPN.

O QUE ESTE MÓDULO NÃO FAZ
    **Não transmite nada para a ONRTDPJ** — quem fala com a Central é
    `onrtdpj_api`, e este módulo só guarda o que aconteceu. É a mesma separação
    de `cenprot_pendencias` e `cenprot_api`.

    > **E EU ESCREVI AQUI, HORAS ANTES, QUE NÃO HAVIA CONTRATO A MEDIR.** O
    > texto dizia que «escrever um endereço, um nome de operação ou um formato
    > de mensagem seria inventar», porque medi o acervo do E-Ofício e ele não
    > tem **uma única tabela nem uma única coluna** de RTDPJ ou de Central.
    >
    > **A medição estava certa e a conclusão estava errada.** O E-Ofício não
    > tinha o que ensinar; **o mundo tinha** — o contrato da Central está
    > público em `https://centralinside.rtdbrasil.org.br/swagger/docs/v1`,
    > Swagger 2.0, 81 caminhos, exatamente como o WSDL da CRA estava. É a lição
    > deste projeto pela sexta vez, agora pelo lado da fonte: **não achar onde
    > eu procurei não prova que não existe.**
    >
    > O que desfez não foi releitura: foi **procurar noutro lugar**.

FUNDAMENTO
    Lei 6.015/1973, arts. 114 a 126 (RCPJ) e 127 a 144 (RTD); art. 12 — o
    título se lança no protocolo com o seu número de ordem antes de qualquer
    exigência.
"""
from __future__ import annotations

import sqlite3

import escrituracao as ESC
import livro_nucleo as LN
import rg_registro as RG
from bd_nativo import banco


class TituloError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


# AS DUAS ATRIBUIÇÕES, e o livro de protocolo de cada uma. Os códigos são os do
# E-Ofício, adotados pela casa inteira (`atribuicoes.ATRIBUICOES`).
RCPJ = 3
RTD = 4
ATRIBUICOES = (RCPJ, RTD)

NOME_DA_ATRIBUICAO: dict[int, str] = {
    RCPJ: "RCPJ — Registro Civil das Pessoas Jurídicas",
    RTD: "RTD — Registro de Títulos e Documentos",
}

# O LIVRO DE PROTOCOLO DE CADA UMA. Estas séries já existiam em
# `livro_nucleo` — declaradas, diárias, com termo contínuo — e nenhuma tela
# jamais escreveu nelas.
PROTOCOLO_DA_ATRIBUICAO: dict[int, str] = {
    RCPJ: "PJ_PROTOCOLO",
    RTD: "TD_PROTOCOLO",
}

# COMO O TÍTULO ENTROU. É esta palavra que parte o caminho em dois no fim: o de
# papel recebe etiqueta colada nele; o eletrônico volta pela Central.
PAPEL = "PAPEL"
ELETRONICO = "ELETRONICO"
FORMAS: dict[str, str] = {
    PAPEL: "Em papel, no balcão",
    ELETRONICO: "Eletrônico, pela Central (ONRTDPJ)",
}

# AS SITUAÇÕES DO TÍTULO.
#
#   **CADA UMA DELAS TEM QUEM A PRODUZA**, e isso é a lição medida do E-Ofício:
#   lá havia cinco situações declaradas e 21.360 protocolos, todos na primeira.
#   Situação que nenhuma rota alcança é trava esperando um estado que nada cria
#   — foi o defeito que o `caixa_protocolo` consertou em 28/08/2026.
APRESENTADO = "APRESENTADO"
QUALIFICADO = "QUALIFICADO"
EXIGENCIA = "EXIGENCIA"
REGISTRADO = "REGISTRADO"
DEVOLVIDO = "DEVOLVIDO"
CANCELADO = "CANCELADO"

SITUACOES: dict[str, str] = {
    APRESENTADO: "Apresentado — aguarda qualificação",
    QUALIFICADO: "Qualificado — positiva, pode registrar",
    EXIGENCIA: "Com exigência — devolvido para cumprir",
    REGISTRADO: "Registrado",
    DEVOLVIDO: "Devolvido — saiu sem registro",
    CANCELADO: "Cancelado — não virou serviço",
}

# As terminais: título que chegou nelas não recebe mais decisão.
SITUACOES_TERMINAIS = (REGISTRADO, DEVOLVIDO, CANCELADO)

POSITIVA = "POSITIVA"
NEGATIVA = "NEGATIVA"
RESULTADOS: dict[str, str] = {
    POSITIVA: "Positiva — o título pode ser registrado",
    NEGATIVA: "Negativa — com exigências a cumprir",
}

RECEBIDO = "RECEBIDO"
ENVIADO = "ENVIADO"
SENTIDOS: dict[str, str] = {
    RECEBIDO: "Recebido da Central",
    ENVIADO: "Enviado à Central",
}

# A entidade dos anexos. A tabela é a `attachments`, a mesma do expediente, da
# tarefa, da prenotação do RI e do termo do RCPN — **não se cria a quinta**.
ANEXO_DO_TITULO = "RG_TITULO"

# Dez letras não é formalidade: é o mínimo para uma frase dizer alguma coisa.
# «ok», «falta doc» e «-» não explicam nada a quem ler daqui a dois anos. É a
# mesma régua de `caixa_protocolo.MINIMO_DO_MOTIVO` e de `rg_registro`.
MINIMO_DO_TEXTO = 10


def _texto(v) -> str:
    return "" if v is None else str(v).strip()


def _atribuicao(valor) -> int:
    try:
        codigo = int(valor)
    except (TypeError, ValueError):
        codigo = 0
    if codigo not in ATRIBUICOES:
        raise TituloError(
            f"Atribuição {valor!r} não é RCPJ nem RTD. São duas: "
            f"{RCPJ} (RCPJ) e {RTD} (RTD).")
    return codigo


def serie_cabe_na_atribuicao(serie: str, atribuicao: int) -> bool:
    """A série pretendida é de livro daquela atribuição? Só calcula.

    **A ATRIBUIÇÃO NÃO SE PERGUNTA DUAS VEZES.** Quem sabe de qual atribuição é
    a série é `livro_nucleo.SERIES` — o mesmo lugar de onde `rg_registro` a lê.
    Dois módulos não podem discordar de qual atribuição uma série pertence.
    """
    codigo = _texto(serie).upper()
    if not codigo:
        return True                 # série ainda não escolhida é falta, não erro
    if codigo not in RG.SERIES_CONHECIDAS:
        return False
    return LN.serie(codigo).atribuicao == int(atribuicao)


# --------------------------------------------------------------- consultas


def um(con: sqlite3.Connection, titulo_id: int) -> dict | None:
    """O título, com tudo que foi cadastrado. Só LÊ."""
    return banco(con).um("SELECT * FROM rg_titulos WHERE id=%s", (int(titulo_id),))


def fila(con: sqlite3.Connection, *, atribuicao: int | None = None,
         situacao: str | None = None, limite: int = 200) -> list[dict]:
    """Os títulos, do mais novo para o mais velho. Só LÊ."""
    onde, param = [], []
    if atribuicao is not None:
        onde.append("atribuicao=%s")
        param.append(_atribuicao(atribuicao))
    if situacao:
        onde.append("situacao=%s")
        param.append(_texto(situacao).upper())
    sql = "SELECT * FROM rg_titulos"
    if onde:
        sql += " WHERE " + " AND ".join(onde)
    sql += " ORDER BY id DESC LIMIT %s"
    param.append(max(1, int(limite)))
    return banco(con).ler(sql, param)


def painel(con: sqlite3.Connection) -> dict[str, int]:
    """Quantos títulos em cada situação. Só LÊ.

    **AS SEIS SITUAÇÕES SAEM SEMPRE, MESMO EM ZERO.** Coluna que só aparece
    quando tem número faz o painel mudar de forma conforme o dia — e quem lê
    todo dia perde a referência de onde olhar.
    """
    quadro = dict.fromkeys(SITUACOES, 0)
    for linha in banco(con).ler(
            "SELECT situacao, COUNT(*) AS n FROM rg_titulos GROUP BY situacao "
            "ORDER BY situacao"):
        quadro[str(linha["situacao"])] = int(linha["n"])
    return quadro


def qualificacoes_de(con: sqlite3.Connection, titulo_id: int) -> list[dict]:
    """As qualificações daquele título, na ordem em que foram feitas. Só LÊ."""
    return banco(con).ler(
        "SELECT * FROM rg_qualificacoes WHERE titulo_id=%s ORDER BY ordem, id",
        (int(titulo_id),))


def ultima_qualificacao(con: sqlite3.Connection, titulo_id: int) -> dict | None:
    """A decisão que vale hoje — a mais recente. Só LÊ."""
    return banco(con).um(
        """SELECT * FROM rg_qualificacoes WHERE titulo_id=%s
            ORDER BY ordem DESC, id DESC LIMIT 1""", (int(titulo_id),))


def encaminhamentos_de(con: sqlite3.Connection, titulo_id: int) -> list[dict]:
    """O que passou pela Central, naquele título. Só LÊ."""
    return banco(con).ler(
        "SELECT * FROM rg_encaminhamentos WHERE titulo_id=%s ORDER BY id",
        (int(titulo_id),))


def titulo_do_registro(con: sqlite3.Connection, registro_id: int) -> dict | None:
    """De que título saiu aquele registro, se de algum. Só LÊ.

    **A PONTE GRAVADA, e não o número digitado.** Aqui só existe a boa —
    `rg_registros.titulo_id`, escrita pela máquina ao registrar. O RI precisou
    de uma segunda ponte pelo texto porque tem 784 atos de acervo sem
    amarração; aqui os 72 registros do acervo nasceram sem título nenhum, e
    inventar uma ponte por aproximação acharia título errado.
    """
    return banco(con).um(
        """SELECT t.* FROM rg_titulos t
             JOIN rg_registros r ON r.titulo_id = t.id
            WHERE r.id = %s""", (int(registro_id),))


# ------------------------------------------------------- receber o título


def receber(con: sqlite3.Connection, *, atribuicao: int, sv: dict, agora: str,
            data_extenso: str, data_apresentacao: str, hora: str | None = None,
            apresentante: str | None = None,
            apresentante_documento: str | None = None,
            telefone: str | None = None, email: str | None = None,
            natureza: str | None = None, serie: str | None = None,
            valor_declarado: str | None = None, vias: int = 1,
            forma: str = PAPEL, observacao: str | None = None,
            protocolo_geral_id: int | None = None,
            usuario: str | None = None, origem: str = "MANUAL",
            origem_chave: str | None = None,
            importacao_id: int | None = None) -> dict:
    """Recebe o título e o lança no Livro de Protocolo. ESCREVE.

    **O NÚMERO SAI DO LIVRO, E NÃO DE UM CONTADOR DESTE MÓDULO.** Quem numera é
    `escrituracao.reservar` sobre a série `PJ_PROTOCOLO`/`TD_PROTOCOLO`, que é
    a mesma máquina que numera todos os livros da casa. Um segundo contador
    aqui seria a segunda fonte para o mesmo número — o defeito que abriu a
    matrícula 4011 depois de a 4013 já existir, em 18/08/2026.

    **O TÍTULO ENTRA ANTES DE QUALQUER EXIGÊNCIA** (Lei 6.015/1973, art. 12):
    natureza, série e apresentante podem faltar e o protocolo se lança do mesmo
    jeito. O que não pode faltar é a data — sem ela não há ordem no livro.

    Carga repetível por construção: reapresentar a mesma (origem, origem_chave)
    devolve o id já existente, como em `rg_registro.abrir_registro`.
    """
    codigo = _atribuicao(atribuicao)
    dia = _texto(data_apresentacao)[:10]
    if not dia:
        raise TituloError(
            "O título precisa da data em que foi apresentado — é ela que dá a "
            "ordem no Livro de Protocolo.")

    como = _texto(forma).upper() or PAPEL
    if como not in FORMAS:
        raise TituloError(
            f"«{forma}» não é forma de apresentação. São duas: "
            f"{', '.join(FORMAS)}.")

    pretendida = _texto(serie).upper() or None
    if pretendida and not serie_cabe_na_atribuicao(pretendida, codigo):
        raise TituloError(
            f"O livro {pretendida} não é do {NOME_DA_ATRIBUICAO[codigo]}. "
            f"Escolha um dos livros da atribuição, ou deixe em branco para "
            f"decidir na qualificação.")

    chave = _texto(origem_chave) or None
    if origem == "EOFICIO" and not chave:
        raise TituloError(
            "Título de origem EOFICIO precisa de uma chave de origem, para a "
            "carga poder ser repetida sem duplicar.")
    bd = banco(con)
    if chave:
        existente = bd.um(
            "SELECT id FROM rg_titulos WHERE origem=%s AND origem_chave=%s",
            (origem, chave))
        if existente:
            return {"titulo_id": int(existente["id"]), "reaproveitado": True}

    novo = bd.escrever(
        """INSERT INTO rg_titulos(atribuicao, data_apresentacao, hora,
               apresentante, apresentante_documento, telefone, email,
               natureza, serie, valor_declarado, vias, forma, situacao,
               protocolo_geral_id, observacao, origem, origem_chave,
               importacao_id, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (codigo, dia, _texto(hora) or None, _texto(apresentante) or None,
         _texto(apresentante_documento) or None, _texto(telefone) or None,
         _texto(email) or None, _texto(natureza) or None, pretendida,
         _texto(valor_declarado) or None, max(1, int(vias or 1)), como,
         APRESENTADO,
         int(protocolo_geral_id) if protocolo_geral_id else None,
         _texto(observacao) or None, origem, chave, importacao_id, agora,
         usuario))
    titulo_id = int(novo[0]["id"])

    # O LUGAR NO LIVRO DE PROTOCOLO. `dia` é o do livro diário: o protocolo é
    # livro que se encerra todo dia, e não quando enche.
    lugar = ESC.reservar(con, PROTOCOLO_DA_ATRIBUICAO[codigo], "rg_titulos",
                         titulo_id, sv=sv, agora=agora,
                         data_extenso=data_extenso, paginas=1, dia=dia,
                         usuario=usuario)
    bd.escrever(
        """UPDATE rg_titulos SET numero=%s, livro_id=%s, folha=%s, verso=%s,
                                 rotulo=%s WHERE id=%s""",
        (lugar["numero_ordem"], lugar["livro_id"], lugar["folha"],
         int(lugar["verso"]), lugar["rotulo"], titulo_id))
    return {"titulo_id": titulo_id, "reaproveitado": False, **lugar}


def atualizar(con: sqlite3.Connection, titulo_id: int, *,
              apresentante: str | None = None,
              apresentante_documento: str | None = None,
              telefone: str | None = None, email: str | None = None,
              natureza: str | None = None, serie: str | None = None,
              valor_declarado: str | None = None, vias: int = 1,
              forma: str = PAPEL, observacao: str | None = None) -> dict:
    """Completa ou corrige os dados do título antes de ele sair. ESCREVE.

    O título pode entrar só com a data, mas isso não pode significar que os
    campos vazios ficam vazios para sempre. Número, data, hora e atribuição não
    são editados aqui: eles formam a ordem do protocolo. Depois do registro ou
    do encerramento, a correção também não é edição silenciosa.
    """
    titulo = um(con, titulo_id)
    if not titulo:
        raise TituloError(f"Título {titulo_id} não encontrado.")
    if titulo["situacao"] in SITUACOES_TERMINAIS:
        raise TituloError(
            "Este título já saiu do protocolo. Para corrigir registro ou "
            "encerramento, use o ato próprio e preserve o histórico.")

    pretendida = _texto(serie).upper() or None
    if pretendida and not serie_cabe_na_atribuicao(
            pretendida, int(titulo["atribuicao"])):
        raise TituloError(
            f"O livro {pretendida} não é do "
            f"{NOME_DA_ATRIBUICAO[int(titulo['atribuicao'])]}.")
    como = _texto(forma).upper() or PAPEL
    if como not in FORMAS:
        raise TituloError(
            f"«{forma}» não é forma de apresentação. São duas: "
            f"{', '.join(FORMAS)}.")
    try:
        quantidade = max(1, int(vias or 1))
    except (TypeError, ValueError) as erro:
        raise TituloError("Informe a quantidade de vias em número.") from erro

    valores = {
        "apresentante": _texto(apresentante) or None,
        "apresentante_documento": _texto(apresentante_documento) or None,
        "telefone": _texto(telefone) or None,
        "email": _texto(email) or None,
        "natureza": _texto(natureza) or None,
        "serie": pretendida,
        "valor_declarado": _texto(valor_declarado) or None,
        "vias": quantidade,
        "forma": como,
        "observacao": _texto(observacao) or None,
    }
    bd = banco(con)
    bd.escrever(
        """UPDATE rg_titulos SET apresentante=%s, apresentante_documento=%s,
               telefone=%s, email=%s, natureza=%s, serie=%s, valor_declarado=%s,
               vias=%s, forma=%s, observacao=%s WHERE id=%s""",
        (*valores.values(), int(titulo_id)))

    # A ponte com o protocolo geral não pode deixar o mesmo atendimento com
    # dois nomes e dois assuntos. Não se mexe em situação, número nem datas.
    if titulo.get("protocolo_geral_id"):
        bd.escrever(
            """UPDATE cx_protocolos SET interessado=%s,
                   interessado_documento=%s, telefone=%s, email=%s, assunto=%s,
                   documento_numero=%s, documento_descricao=%s WHERE id=%s""",
            (valores["apresentante"], valores["apresentante_documento"],
             valores["telefone"], valores["email"], valores["natureza"],
             valores["apresentante_documento"], valores["natureza"],
             int(titulo["protocolo_geral_id"])))
    return {"titulo_id": int(titulo_id), **valores}


# ------------------------------------------------------------ qualificar


def qualificar(con: sqlite3.Connection, titulo_id: int, *, resultado: str,
               agora: str, fundamentacao: str | None = None,
               exigencias: str | None = None, prazo_ate: str | None = None,
               data_qualificacao: str | None = None,
               qualificada_por: str | None = None,
               usuario: str | None = None) -> dict:
    """Decide sobre o título: positiva, ou negativa com exigências. ESCREVE.

    **A NEGATIVA SEM EXIGÊNCIA ESCRITA NÃO PASSA.** Devolver um título dizendo
    apenas «não pode» é devolver sem dizer o que fazer — e o apresentante volta
    ao balcão para perguntar, o que é o mesmo trabalho feito duas vezes. A
    régua são as mesmas dez letras do resto da casa.

    **REQUALIFICAR É LINHA NOVA, e não correção da anterior.** O título voltou
    com exigência, o apresentante cumpriu, e agora se decide de novo. A decisão
    velha fica: é ela que explica por que o título voltou, e é ela que a
    correição lê.
    """
    titulo = um(con, titulo_id)
    if not titulo:
        raise TituloError(f"Título {titulo_id} não encontrado.")
    if titulo["situacao"] in SITUACOES_TERMINAIS:
        raise TituloError(
            f"Este título está {SITUACOES[titulo['situacao']].split(' —')[0].lower()} "
            f"— não se qualifica título que já saiu.")

    decisao = _texto(resultado).upper()
    if decisao not in RESULTADOS:
        raise TituloError(
            f"«{resultado}» não é resultado de qualificação. São dois: "
            f"{', '.join(RESULTADOS)}.")

    razao = _texto(exigencias)
    if decisao == NEGATIVA and len(razao) < MINIMO_DO_TEXTO:
        raise TituloError(
            "Qualificação negativa sem exigência escrita devolve o título sem "
            "dizer o que fazer. Escreva as exigências — com pelo menos dez "
            "letras.")
    if decisao == POSITIVA and razao:
        # Não é impedimento: é a exigência sobrando de um rascunho anterior.
        # Guardá-la numa decisão positiva faria a tela mostrar exigência em
        # título liberado, e alguém a leria como pendente.
        razao = ""

    bd = banco(con)
    bd.travar("rg_qualificacoes.ordem")
    ordem = int(bd.valor(
        "SELECT COALESCE(MAX(ordem),0)+1 AS n FROM rg_qualificacoes WHERE titulo_id=%s",
        (int(titulo_id),)))

    novo = bd.escrever(
        """INSERT INTO rg_qualificacoes(titulo_id, ordem, resultado,
               fundamentacao, exigencias, prazo_ate, data_qualificacao,
               qualificada_por, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(titulo_id), ordem, decisao, _texto(fundamentacao) or None,
         razao or None, _texto(prazo_ate) or None,
         _texto(data_qualificacao) or str(agora)[:10],
         _texto(qualificada_por) or None, agora, usuario))

    situacao = QUALIFICADO if decisao == POSITIVA else EXIGENCIA
    bd.escrever("UPDATE rg_titulos SET situacao=%s, prazo_ate=%s WHERE id=%s",
                (situacao, _texto(prazo_ate) or None, int(titulo_id)))
    return {"titulo_id": int(titulo_id), "qualificacao_id": int(novo[0]["id"]),
            "ordem": ordem, "resultado": decisao, "situacao": situacao}


# ------------------------------------------------- registrar, e o que sai


def registrar(con: sqlite3.Connection, titulo_id: int, *, serie: str,
              sv: dict, agora: str, data_extenso: str,
              teor: str | None = None, teor_formato: str = "texto",
              usuario: str | None = None,
              declaracoes: dict | None = None) -> dict:
    """Lavra o registro do título qualificado. ESCREVE.

    **SÓ DEPOIS DA QUALIFICAÇÃO POSITIVA** — é a frase do oficial, e ela é
    regra registral: o registro é o efeito da qualificação, não o contrário.
    Registrar antes seria gastar número de livro num título que ainda pode
    voltar.

    O registro em si é o do `rg_registro`, e não uma segunda versão dele: o
    livro, a folha, a numeração e a regra de folha nova são as mesmas para o
    título que entrou pelo protocolo e para o que veio do acervo.

    `declaracoes` são as do termo do livro escolhido (LD09: o extrato do Livro
    C, a inscrição da pessoa jurídica, a matrícula do periódico) — quem as
    confere e grava no ato é `rg_registro.abrir_registro`, antes do número.
    """
    titulo = um(con, titulo_id)
    if not titulo:
        raise TituloError(f"Título {titulo_id} não encontrado.")
    if titulo["situacao"] == REGISTRADO:
        raise TituloError(
            "Este título já foi registrado. Um título tem um registro e não "
            "dois.")
    if titulo["situacao"] != QUALIFICADO:
        raise TituloError(
            "Só se registra título com qualificação positiva. Este está "
            f"«{SITUACOES.get(titulo['situacao'], titulo['situacao'])}» — "
            f"qualifique antes.")

    escolhida = _texto(serie).upper()
    if not serie_cabe_na_atribuicao(escolhida, int(titulo["atribuicao"])):
        raise TituloError(
            f"O livro {escolhida or '(em branco)'} não é do "
            f"{NOME_DA_ATRIBUICAO[int(titulo['atribuicao'])]}.")

    feito = RG.abrir_registro(
        con, serie=escolhida, sv=sv, agora=agora, data_extenso=data_extenso,
        natureza=titulo["natureza"], requerente_nome=titulo["apresentante"],
        requerente_documento=titulo["apresentante_documento"],
        teor=teor, teor_formato=teor_formato, usuario=usuario,
        declaracoes=declaracoes)

    bd = banco(con)
    bd.escrever("UPDATE rg_registros SET titulo_id=%s WHERE id=%s",
                (int(titulo_id), int(feito["registro_id"])))
    bd.escrever("UPDATE rg_titulos SET situacao=%s, registro_id=%s, serie=%s "
                "WHERE id=%s",
                (REGISTRADO, int(feito["registro_id"]), escolhida,
                 int(titulo_id)))
    return {"titulo_id": int(titulo_id), **feito}


def encerrar(con: sqlite3.Connection, titulo_id: int, *, situacao: str,
             motivo: str, agora: str, usuario: str | None = None) -> dict:
    """Fecha o título sem registro: devolvido, ou cancelado. ESCREVE.

    **DUAS PALAVRAS, E NÃO UMA**, pelo mesmo motivo de `caixa_protocolo`:
    `DEVOLVIDO` é o título que voltou ao apresentante; `CANCELADO` é o que não
    virou serviço. Juntar as duas faria a correição não distinguir o trabalho
    feito do trabalho que não houve.
    """
    titulo = um(con, titulo_id)
    if not titulo:
        raise TituloError(f"Título {titulo_id} não encontrado.")
    if titulo["situacao"] in SITUACOES_TERMINAIS:
        raise TituloError(
            f"Este título já está «{SITUACOES[titulo['situacao']]}».")

    fim = _texto(situacao).upper()
    if fim not in (DEVOLVIDO, CANCELADO):
        raise TituloError(
            f"«{situacao}» não encerra título. São duas: {DEVOLVIDO} e "
            f"{CANCELADO}.")
    razao = _texto(motivo)
    if len(razao) < MINIMO_DO_TEXTO:
        raise TituloError(
            "Escreva o motivo com pelo menos dez letras — «ok» não explica "
            "nada a quem ler daqui a dois anos.")

    anotacao = _texto(titulo["observacao"])
    anotacao = (anotacao + "\n" if anotacao else "") + f"{fim}: {razao}"
    banco(con).escrever("UPDATE rg_titulos SET situacao=%s, observacao=%s WHERE id=%s",
                        (fim, anotacao, int(titulo_id)))
    return {"titulo_id": int(titulo_id), "situacao": fim, "motivo": razao}


# --------------------------------- o título que virou ato num registro antigo
#
# O TÍTULO DE AVERBAÇÃO NÃO TINHA SAÍDA — medido na produção em 09/10/2026.
#
#   O título n. 1 do RCPJ (Caixa Escolar Uex Santa Isabel, 11/09/2026) era uma
#   ata e um estatuto **para averbar** no registro n. 148, que já existia. A
#   qualificação foi positiva, as duas averbações (378 e 379) foram lavradas e
#   seladas pela ficha do REGISTRO, gastando os itens do protocolo deste título
#   — e o título ficou «Qualificado» para sempre. `registrar` abre registro
#   NOVO, e `encerrar` só conhece «devolvido» e «cancelado»: as duas saídas que
#   existiam diriam uma coisa falsa sobre um título que foi atendido.
#
#   É a lição do E-Ofício que este módulo cita no alto, pelo outro lado:
#   **situação que nenhuma rota alcança é trava esperando um estado que nada
#   cria** — aqui não a situação, mas o CAMINHO até ela.
#
# A PALAVRA É «REGISTRADO», E NÃO UMA QUARTA. Averbação é ato de registro no
# livro; inventar «averbado» seria vocabulário novo tendo o antigo à mão, e a
# lista e o painel passariam a ter uma coluna que só um caminho produz.

TIPOS_QUE_CONCLUEM = ("AVERBACAO", "CANCELAMENTO")


def _tem_colunas_de_uso(con: sqlite3.Connection) -> bool:
    """O protocolo do balcão já sabe que ato gastou cada item? Só LÊ.

    Pergunta ao catálogo do banco (`bd.tem_coluna`), como os outros módulos
    nativos — o teto de acoplamento de módulo de domínio é zero
    (`tests/test_portabilidade.py`).
    """
    bd = banco(con)
    return (bd.tem_coluna("cx_protocolo_atos", "usado_por_tabela")
            and bd.tem_coluna("cx_protocolo_atos", "usado_por_ato_id"))


def atos_do_protocolo(con: sqlite3.Connection, titulo_id: int) -> list[dict]:
    """Os atos do RCPJ/RTD que gastaram itens do protocolo deste título. Só LÊ.

    **A PONTE GRAVADA**: `cx_protocolo_atos.usado_por_ato_id`, escrita pela
    máquina quando o ato consumiu o item — e não a data, nem o nome do
    apresentante. Só entram atos da mesma atribuição do título.
    """
    bd = banco(con)
    titulo = um(bd, titulo_id)
    if not titulo or not titulo.get("protocolo_geral_id") \
            or not _tem_colunas_de_uso(bd):
        return []
    return bd.ler(
        """SELECT DISTINCT a.id, a.registro_id, a.tipo, a.data_ato,
                  a.numero_ordem, a.rotulo, r.serie, r.atribuicao,
                  r.numero AS registro_numero
             FROM cx_protocolo_atos i
             JOIN rg_atos a ON a.id = i.usado_por_ato_id
             JOIN rg_registros r ON r.id = a.registro_id
            WHERE i.protocolo_id = %s AND i.usado_por_tabela = 'rg_atos'
              AND r.atribuicao = %s
            ORDER BY a.id""",
        (int(titulo["protocolo_geral_id"]), int(titulo["atribuicao"])))


def atos_para_concluir(con: sqlite3.Connection, titulo_id: int) -> list[dict]:
    """Os atos que podem concluir este título, para a tela oferecer. Só LÊ.

    Primeiro os que gastaram o protocolo dele (`pelo_protocolo`); depois as
    averbações e os cancelamentos da mesma atribuição lavrados desde a
    apresentação e ainda sem título — o caso do ato cobrado à mão, sem item do
    protocolo marcado. **Quem escolhe entre eles é quem qualifica**: a lista
    oferece, e não decide.
    """
    bd = banco(con)
    titulo = um(bd, titulo_id)
    if not titulo:
        return []
    pelo_protocolo = [dict(a, pelo_protocolo=True)
                      for a in atos_do_protocolo(bd, titulo_id)
                      if a["tipo"] in TIPOS_QUE_CONCLUEM]
    vistos = {a["id"] for a in pelo_protocolo}
    lugares = ",".join(["%s"] * len(TIPOS_QUE_CONCLUEM))
    pela_data = [dict(r, pelo_protocolo=False) for r in bd.ler(
        f"""SELECT a.id, a.registro_id, a.tipo, a.data_ato, a.numero_ordem,
                   a.rotulo, r.serie, r.atribuicao,
                   r.numero AS registro_numero
              FROM rg_atos a JOIN rg_registros r ON r.id = a.registro_id
             WHERE r.atribuicao = %s AND a.tipo IN ({lugares})
               AND a.data_ato >= %s
             ORDER BY a.id""",
        (int(titulo["atribuicao"]), *TIPOS_QUE_CONCLUEM,
         _texto(titulo["data_apresentacao"])[:10]))
        if r["id"] not in vistos]
    return pelo_protocolo + pela_data


def concluir_pelo_ato(con: sqlite3.Connection, titulo_id: int, *, ato_id: int,
                      agora: str, usuario: str | None = None) -> dict:
    """Fecha o título que virou averbação ou cancelamento. ESCREVE.

    O título qualificado cujo ato foi lavrado na ficha de um registro que JÁ
    existia passa a «Registrado», apontando para esse registro. Não lavra,
    não numera, não sela e não cobra: o ato já está no livro, e é ele que
    conclui o título.
    """
    titulo = um(con, titulo_id)
    if not titulo:
        raise TituloError(f"Título {titulo_id} não encontrado.")
    if titulo["situacao"] == REGISTRADO:
        raise TituloError("Este título já está concluído como registrado.")
    if titulo["situacao"] != QUALIFICADO:
        raise TituloError(
            "Só se conclui título com qualificação positiva. Este está "
            f"«{SITUACOES.get(titulo['situacao'], titulo['situacao'])}».")
    candidatos = {int(a["id"]): a for a in atos_para_concluir(con, titulo_id)}
    ato = candidatos.get(int(ato_id))
    if not ato:
        raise TituloError(
            "Este ato não serve para concluir o título: tem de ser averbação "
            "ou cancelamento da mesma atribuição, lavrado desde a apresentação "
            "ou com os itens do protocolo deste título. O registro NOVO se "
            "lavra pelo botão «Lavrar o registro».")
    rotulo = "AV" if ato["tipo"] == "AVERBACAO" else "CANCELAMENTO"
    nota = (f"REGISTRADO pelo ato já lavrado: {rotulo} n. "
            f"{ato['numero_ordem'] or '?'} do registro n. "
            f"{ato['registro_numero'] or '?'} ({ato['serie']}), em "
            f"{_texto(agora)[:10]}"
            + (f", por {usuario}" if usuario else "") + ".")
    anotacao = _texto(titulo["observacao"])
    anotacao = (anotacao + "\n" if anotacao else "") + nota
    banco(con).escrever(
        """UPDATE rg_titulos SET situacao=%s, registro_id=%s,
               serie=COALESCE(NULLIF(serie,''), %s), observacao=%s WHERE id=%s""",
        (REGISTRADO, int(ato["registro_id"]), ato["serie"], anotacao,
         int(titulo_id)))
    return {"titulo_id": int(titulo_id), "ato_id": int(ato["id"]),
            "registro_id": int(ato["registro_id"]), "tipo": ato["tipo"],
            "pelo_protocolo": bool(ato["pelo_protocolo"]), "nota": nota}


def titulo_do_ato(con: sqlite3.Connection, ato_id: int) -> dict | None:
    """De que título saiu aquele ato, se de algum. Só LÊ.

    Pela ponte do protocolo (o item que o ato gastou), e só depois pela do
    registro. A averbação não tem `rg_registros.titulo_id` — o registro é de
    outro título, ou do acervo —, e sem esta ponte a etiqueta dela saía sem o
    número do protocolo.
    """
    bd = banco(con)
    if _tem_colunas_de_uso(bd):
        linha = bd.um(
            """SELECT t.* FROM rg_titulos t
                 JOIN cx_protocolo_atos i ON i.protocolo_id = t.protocolo_geral_id
                WHERE i.usado_por_tabela = 'rg_atos' AND i.usado_por_ato_id = %s
                ORDER BY t.id LIMIT 1""", (int(ato_id),))
        if linha:
            return linha
    ato = bd.um("SELECT registro_id FROM rg_atos WHERE id=%s", (int(ato_id),))
    return titulo_do_registro(bd, int(ato["registro_id"])) if ato else None


# ------------------------------------------------ o que passou pela Central


ORIGEM_DA_CENTRAL = "ONRTDPJ"


def _do_pedido(pedido: dict, *caminho: str) -> str:
    """Um campo aninhado do `PedidoModel`, ou vazio. Só calcula.

    **O `PedidoModel` tem 60 campos e vários objetos dentro** — `Cliente`,
    `Servico`, `Situacao`. Cada `pedido["Cliente"]["Nome"]` escrito à mão
    estoura quando a Central manda o objeto nulo, que é o caso normal de um
    pedido sem cliente informado.
    """
    atual: object = pedido
    for parte in caminho:
        if not isinstance(atual, dict):
            return ""
        atual = atual.get(parte)
    return _texto(atual)


def protocolo_na_central(con: sqlite3.Connection, titulo_id: int) -> str:
    """O protocolo daquele título na Central, se ele veio de lá. Só LÊ.

    **DERIVADO, e não guardado numa terceira coluna.** Ele já está em
    `rg_encaminhamentos.protocolo_central`, na linha do que foi RECEBIDO; uma
    cópia em `rg_titulos` seria o mesmo número em dois lugares, divergindo no
    primeiro conserto.
    """
    linha = banco(con).um(
        """SELECT protocolo_central FROM rg_encaminhamentos
            WHERE titulo_id=%s AND sentido=%s AND protocolo_central IS NOT NULL
            ORDER BY id LIMIT 1""", (int(titulo_id), RECEBIDO))
    return _texto(linha["protocolo_central"]) if linha else ""


def receber_da_central(con: sqlite3.Connection, pedido: dict, *,
                       atribuicao: int, sv: dict, agora: str,
                       data_extenso: str, usuario: str | None = None) -> dict:
    """Recebe em protocolo um pedido que veio da Central. ESCREVE.

    **É POR AQUI QUE O TÍTULO ELETRÔNICO ENTRA NA CASA** — a metade do pedido
    do oficial que a ONRTDPJ atende. O que chega é o `PedidoModel` do contrato
    dela, medido em 03/09/2026.

    **O TÍTULO DA CENTRAL ENTRA NO MESMO LIVRO DE PROTOCOLO DO DE PAPEL.** Duas
    numerações — uma para o balcão e outra para o eletrônico — fariam dois
    títulos com o mesmo número de ordem no mesmo livro, que é a pior coisa que
    pode acontecer a um protocolo.

    **E REAPRESENTAR NÃO DUPLICA**: a chave de origem é o protocolo da Central,
    com `UNIQUE(origem, origem_chave)` no banco. A fila de lá traz o mesmo
    pedido todo dia até alguém tratá-lo; sem a chave, cada baixada abriria um
    protocolo novo aqui.

    **A ATRIBUIÇÃO É PERGUNTADA, e não deduzida.** O contrato traz
    `Servico.Especialidade`, e o que ela vale para separar RTD de RCPJ **não
    foi medido** — não há um pedido real desta serventia para conferir. Deduzir
    por semelhança poria o título no livro errado, e livro errado só aparece
    quando a certidão sai.
    """
    protocolo = _texto(pedido.get("Protocolo"))
    if not protocolo:
        raise TituloError(
            "O pedido veio da Central sem número de protocolo — sem ele não dá "
            "para amarrar o título ao que está lá.")

    # A DATA DE ENTRADA É A DA CENTRAL, e não a de hoje: a ordem de chegada é
    # do dia em que o pedido foi feito, e baixar a fila com atraso não pode
    # mudar a prioridade de quem apresentou primeiro.
    cadastro = _do_pedido(pedido, "DataCadastro")[:10] or str(agora)[:10]

    natureza = " · ".join(x for x in (_do_pedido(pedido, "Servico", "Nome"),
                                      _texto(pedido.get("DescricaoResumida")))
                          if x)
    anotacao = [f"Pedido {protocolo} da Central ONRTDPJ."]
    for rotulo, valor in (
            ("Situação na Central", _do_pedido(pedido, "Situacao", "Nome")),
            ("Serviço", _do_pedido(pedido, "Servico", "Nome")),
            ("Finalidade", _texto(pedido.get("Finalidade"))),
            ("Alerta da Central", _texto(pedido.get("Alerta"))),
            ("Arquivo enviado", _texto(pedido.get("LinkArquivoEnviado")))):
        if valor:
            anotacao.append(f"{rotulo}: {valor}")

    feito = receber(
        con, atribuicao=atribuicao, sv=sv, agora=agora,
        data_extenso=data_extenso, data_apresentacao=cadastro,
        apresentante=(_do_pedido(pedido, "Cliente", "Nome")
                      or _texto(pedido.get("NomeRazaoSocialRtd"))),
        apresentante_documento=(_do_pedido(pedido, "Cliente", "CPFCNPJ")
                                or _texto(pedido.get("CpfCnpjRtd"))),
        telefone=(_do_pedido(pedido, "Cliente", "Celular")
                  or _do_pedido(pedido, "Cliente", "Telefone")),
        email=_do_pedido(pedido, "Cliente", "Email"),
        natureza=natureza or None,
        valor_declarado=_texto(pedido.get("ValorOrcamento")) or None,
        forma=ELETRONICO, observacao="\n".join(anotacao),
        usuario=usuario, origem=ORIGEM_DA_CENTRAL, origem_chave=protocolo)

    if feito.get("reaproveitado"):
        return feito | {"protocolo_central": protocolo}

    registrar_encaminhamento(
        con, feito["titulo_id"], sentido=RECEBIDO, agora=agora,
        data_encaminhamento=cadastro, protocolo_central=protocolo,
        observacao="Baixado da fila da Central.", usuario=usuario)
    return feito | {"protocolo_central": protocolo}


def registrar_encaminhamento(con: sqlite3.Connection, titulo_id: int, *,
                             sentido: str, agora: str,
                             data_encaminhamento: str | None = None,
                             protocolo_central: str | None = None,
                             observacao: str | None = None,
                             central: str = "ONRTDPJ",
                             usuario: str | None = None) -> dict:
    """Guarda que o título passou pela Central. ESCREVE — e **não transmite**.

    **O QUE ESTA FUNÇÃO É, E O QUE ELA NÃO É.** Ela é o livro da passagem: em
    que dia o título veio da Central, com que protocolo de lá, e em que dia a
    resposta saiu. Ela **não** fala com a ONRTDPJ, e o nome dela diz isso.

    Medido no acervo do E-Ofício em 03/09/2026: **zero tabelas e zero colunas**
    de RTDPJ ou de Central. Aquela casa nunca usou a Central, então não há
    precedente a imitar — e inventar endereço, operação ou formato seria
    inventar número. O transporte entra quando houver especificação e
    credencial, como entrou o da CENPROT e o da CRA.

    **Vale para o título ELETRÔNICO e para o de papel.** Um título de papel
    pode ter sido enviado à Central depois de registrado, e recusar o registro
    da passagem por causa da forma esconderia um fato que aconteceu.
    """
    titulo = um(con, titulo_id)
    if not titulo:
        raise TituloError(f"Título {titulo_id} não encontrado.")

    para_onde = _texto(sentido).upper()
    if para_onde not in SENTIDOS:
        raise TituloError(
            f"«{sentido}» não é sentido de encaminhamento. São dois: "
            f"{', '.join(SENTIDOS)}.")

    novo = banco(con).escrever(
        """INSERT INTO rg_encaminhamentos(titulo_id, central, sentido,
               protocolo_central, data_encaminhamento, observacao, criado_em,
               criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(titulo_id), _texto(central).upper() or "ONRTDPJ", para_onde,
         _texto(protocolo_central) or None,
         _texto(data_encaminhamento) or str(agora)[:10],
         _texto(observacao) or None, agora, usuario))
    return {"titulo_id": int(titulo_id),
            "encaminhamento_id": int(novo[0]["id"]), "sentido": para_onde}
