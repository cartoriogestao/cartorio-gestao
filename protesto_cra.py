"""
O contrato da CRA e da CENPROT — o que entra e o que sai do Protesto, em XML.

DE ONDE ISTO VEIO
    Dos esquemas OFICIAIS, encontrados na maquina da serventia em 21/08/2026:

        C:\\ARPNET\\CRA\\Remessa\\v1_21.xsd
        C:\\ARPNET\\CRA\\Remessa\\v1_22-apontamento.xsd
        C:\\ARPNET\\CRA\\Remessa\\v1_22-geral.xsd

    Sao 66 especies de titulo, 76 codigos de irregularidade, 10 ocorrencias, e
    os dominios de tipo de protesto, motivo, endosso, apresentante e anuencia —
    todos com o texto que o proprio esquema documenta. Nenhum rotulo foi
    escrito por mim.

POR QUE ISTO E O CORACAO DO MODULO, E NAO UM ACESSORIO
    Dos 1.370 titulos do acervo, 1.268 entraram pela CRA e 91 pela CENPROT.
    SETE entraram a mao, em seis anos. E 1.359 dos 1.370 sao NATO_DIGITAL.

    Ou seja: o Protesto desta serventia nao e uma tela de digitacao com uma
    integracao ao lado. E uma integracao, com uma tela de digitacao ao lado
    para os sete.

AS DUAS VERSOES, E A DIFERENCA QUE IMPORTA
    A 1.21 tem duas ocorrencias que a 1.22-apontamento nao tem:

        X   Anuencia recebida
        W   Averbacao / correcao de titulo ja protestado

    E a 1.22-apontamento tem uma que a 1.21 nao tem:

        0   Apontamento

    Isto NAO significa que a averbacao de titulo protestado deixou de existir
    — significa que ela nao cabe num arquivo de apontamento. Quem valida
    precisa saber contra qual versao esta validando, e por isso cada ocorrencia
    abaixo diz em que versoes vale.

O QUE ESTE MODULO NAO FAZ
    Nao abre conexao, nao envia arquivo, nao grava no banco. E contrato e
    validacao: dado um titulo, ele diz se os codigos existem, o que cada um
    significa, e o que falta. Quem transmite e quem grava vem depois.

FUNDAMENTO
    Lei 9.492/1997 — servicos concernentes ao protesto de titulos.
    Provimento CNJ n. 87/2019 e n. 149/2023 (Codigo Nacional de Normas),
        Central Nacional de Protesto.
    Esquemas XML da CRA/CENPROT, versoes 1.21 e 1.22.
"""
from __future__ import annotations

from typing import Any

VERSOES: tuple[str, ...] = ("1.21", "1.22-apontamento", "1.22-geral")

# A serventia de Cidade Exemplo, na CRA e na CENPROT (de `tbPropProtesto`).
CODIGO_CRA = "01"
CODIGO_CENPROT = "01"


class CraError(ValueError):
    """Codigo fora do contrato, com mensagem pronta para a tela."""


# ------------------------------------------------------ especies de titulo
#
# 66 especies. As que esta serventia realmente recebe, por volume no acervo:
# DMI 911, CDA 353, CBI 62, DSI 16, DM 6, ATC 6, NP 4, CTI 4, SJ 3, FPS 1.
#
# DMI e CDA sao 92% do movimento. A tela tem de ser boa nessas duas antes de
# ser completa nas sessenta e seis.

ESPECIES: dict[str, str] = {
    'CBI': "Cédula de Crédito Bancário por Indicação",
    'CC': "Contrato de Câmbio",
    'CCB': "Cédula de Crédito Bancário",
    'CCC': "Cédula de Crédito Comercial",
    'CCE': "Cédula de Crédito à Exportação",
    'CCI': "Cédula de Crédito Industrial",
    'CCR': "Cédula de Crédito Rural",
    'CD': "Confissão de Dívida – Apenas para fins de falência (uma declaração do devedor)",
    'CDA': "Certidão da Dívida Ativa",
    'CDI': "Certidao de Divida por Indicação",
    'CH': "Cheque",
    'CHP': "Cédula Hipotecária",
    'CJV': "Conta Judicialmente Verificada – Verificação de livro de empresa – protesto de um processo judicial – falência",
    'CM': "Contrato de Mútuo",
    'CPH': "Cédula Rural Pignoratícia Hipotecária",
    'CPS': "Conta de Prestação de Serviços – Profissional liberal – declaração do profissional, documentos comprobatórios e notificação do devedor, pelo Cartório de Registro de Títulos e Documentos",
    'CRH': "Cédula Rural Hipotecária",
    'CRP': "Cédula Rural Pignoratícia",
    'CT': "Espécie de Contrato",
    'DM': "Duplicata de Venda Mercantil",
    'DMI': "Duplicata de Venda Mercantil por Indicação",
    'DR': "Duplicata Rural",
    'DRI': "Duplicata Rural por Indicação",
    'DS': "Duplicata de Prestação de Serviços – Original",
    'DSI': "Duplicata de Prestação de Serviços por Indicação – Comprovante de prestação dos serviços",
    'DV': "Diversos - Quando não enquadrar na relação acima.",
    'EC': "Encargos Condominiais",
    'LC': "Letra de Câmbio",
    'NCC': "Nota de Crédito Comercial",
    'NCE': "Nota de Crédito à Exportação",
    'NCI': "Nota de Crédito Industrial",
    'NCR': "Nota de Crédito Rural",
    'NP': "Nota Promissória",
    'NPR': "Nota Promissória Rural",
    'RA': "Recibo de Aluguel – Só para pessoa jurídica (contrato aluguel e recibo)",
    'SJ': "Sentença Judicial",
    'TA': "Termo de Acordo – Ex. Ação trabalhista",
    'TM': "Triplicata de Venda Mercantil",
    'TS': "Triplicata de Prestação de Serviços",
    'W': "Warrant",
    'CAC': "Contrato de Adesao ao Cred Direto",
    'CACI': "Contrato de Abertura de Cred Indicacao",
    'CADC': "Contrato de Adesao Cred Direto Caixa",
    'CAM': "Contrato de Arrendamento Mercantil",
    'CCJ': "Carta de Credito Judicial",
    'CDT': "Certidao de Debito do Tribunal",
    'CF': "Contrato de Financiamento",
    'CL': "Contrato de Leasing",
    'CLC': "Contrato de Locacao",
    'CRC': "Contrato de Cred Rotativo de Cheque",
    'CRJ': "Certidao de Credito Judicial",
    'CRPH': "Cedula Rural Pignorat Hipotecaria",
    'DD': "Documento de Divida",
    'ED': "Encargos Condominais",
    'FPS': "Fatura de Prestacao de Servico",
    'FVM': "Fatura de Venda Mercantil",
    'ND': "Nota de Debito",
    'OD': "Ordem de Servico",
    'RFED': "Warrant",
    'RPS': "Recibo de Prest Servico",
    'RPSI': "Recibo de Prest Servico Indicacao",
    'TAJ': "Termo de Acordo Judicial",
    'TJD': "Titulo Executivo Judicial Definitivo",
    'ZZZ': "Outros",
}

# DUAS ESPECIES VEM DUPLICADAS NO PROPRIO ESQUEMA OFICIAL, com redacao
# diferente e o mesmo codigo:
#
#   SJ   "Sentença Judicial"                     e  "Sentenca Judicial"
#   TS   "Triplicata de Prestação de Serviços"   e  "Triplicata de Prest Servico"
#
# E o mesmo titulo escrito duas vezes, uma com acento e outra sem. Ficou a
# primeira redacao, que e a completa. Sao 66 enumeracoes e 64 especies.
DUPLICADAS_NO_ESQUEMA: dict[str, str] = {
    "SJ": "declarada duas vezes no esquema: 'Sentença Judicial' e "
          "'Sentenca Judicial'",
    "TS": "declarada duas vezes no esquema: 'Triplicata de Prestação de "
          "Serviços' e 'Triplicata de Prest Servico'",
}

# ATC e CTI aparecem no acervo e NAO estao no esquema oficial.
#
# Nao sao erro de digitacao: sao dez titulos reais, apontados e protestados.
# Ou vieram de uma versao mais antiga do layout, ou foram digitados a mao no
# E-Oficio, que nao valida contra o esquema. Ficam registrados para serem
# perguntados a CRA — nao para serem silenciados.
ESPECIES_FORA_DO_ESQUEMA: dict[str, str] = {
    "ATC": "aparece em 6 títulos do acervo; ausente dos esquemas 1.21 e 1.22",
    "CTI": "aparece em 4 títulos do acervo; ausente dos esquemas 1.21 e 1.22",
}


# --------------------------------------------------------------- ocorrencias

OCORRENCIAS: dict[str, dict] = {
    '0': {"rotulo": "Apontamento", "versoes": ('1.22',)},
    '1': {"rotulo": "Pago", "versoes": ('1.21', '1.22')},
    '2': {"rotulo": "Protestado", "versoes": ('1.21', '1.22')},
    '3': {"rotulo": "Retirado", "versoes": ('1.21', '1.22')},
    '4': {"rotulo": "Sustado / Suspenso", "versoes": ('1.21', '1.22')},
    '5': {"rotulo": "Devolvido por irregularidade", "versoes": ('1.21', '1.22')},
    '7': {"rotulo": "Liquidação em condicional", "versoes": ('1.21', '1.22')},
    'A': {"rotulo": "Protesto cancelado", "versoes": ('1.21', '1.22')},
    'W': {"rotulo": "Averbação / correção de título já protestado", "versoes": ('1.21',)},
    'X': {"rotulo": "Anuência recebida", "versoes": ('1.21',)},
    'Y': {"rotulo": "Outras ocorrências", "versoes": ('1.21', '1.22')},
}

# O E-Oficio gravou, em `tbProtesto_RO`, dois codigos que NAO sao da CRA:
#
#   'C'  1.027 vezes — o mais usado de todos
#   'E'  1 vez
#
# Sao codigos internos do programa, e nao ocorrencias do contrato. Traduzir um
# 'C' interno para a CRA como se fosse ocorrencia oficial seria mandar dado
# invalido; por isso ficam separados, com o que se sabe deles.
OCORRENCIAS_INTERNAS_DO_EOFICIO: dict[str, str] = {
    "C": "1.027 registros no acervo; código interno do E-Ofício, não da CRA — "
         "significado a confirmar antes de qualquer migração",
    "E": "1 registro no acervo; idem",
}


# ---------------------------------------------------------- irregularidades
#
# Os 76 motivos de devolucao. Sao eles que vao no retorno quando o titulo nao
# pode ser apontado — e o de numero 52, "Titulo apresentado em duplicidade",
# e justamente o que aparece escrito a mao em `tbProtestoGratuito` como motivo
# de gratuidade. Com o codigo, deixa de ser texto livre.

IRREGULARIDADES: dict[str, str] = {
    '1': "Data da apresentação inferior à data de vencimento",
    '2': "Falta de comprovante da prestação de serviço",
    '3': "Nome do pagador incompleto/incorreto",
    '4': "Nome do beneficiário incompleto/incorreto",
    '5': "Nome do sacador incompleto/incorreto",
    '6': "Endereço do pagador insuficiente",
    '7': "CNPJ/CPF do pagador inválido/incorreto",
    '8': "CNPJ/CPF incompatível c/ o nome do pagador/sacador/avalista",
    '9': "CNPJ/CPF do pagador incompatível com o tipo de documento",
    '10': "CNPJ/CPF do sacador incompatível com a espécie",
    '11': "Título aceito sem a assinatura do pagador",
    '12': "Título aceito rasurado ou rasgado",
    '13': "Título aceito – falta título (ag ced: enviar)",
    '14': "CEP incorreto",
    '15': "Praça de pagamento incompatível com endereço",
    '16': "Falta número do título",
    '17': "Título sem endosso do beneficiário ou irregular",
    '18': "Falta data de emissão do título",
    '19': "Título aceito: valor por extenso diferente do valor por numérico",
    '20': "Data de emissão posterior ao vencimento",
    '21': "Espécie inválida para protesto",
    '22': "CEP do pagador incompatível com a praça de protesto",
    '23': "Falta espécie do título",
    '24': "Saldo maior que o valor do título",
    '25': "Tipo de endosso inválido",
    '26': "Devolvido por ordem judicial",
    '27': "Dados do título não conferem com disquete",
    '28': "Pagador e Sacador/Avalista são a mesma pessoa",
    '29': "Corrigir a espécie do título",
    '30': "Aguardar um dia útil após o vencimento para protestar",
    '31': "Data do vencimento rasurada",
    '32': "Vencimento – extenso não confere com número",
    '33': "Falta data de vencimento no título",
    '34': "DM/DMI sem comprovante autenticado ou declaração",
    '35': "Comprovante ilegível para conferência e microfilmagem",
    '36': "Nome solicitado não confere com emitente ou pagador",
    '37': "Confirmar se são 2 emitentes. Se sim, indicar os dados dos 2",
    '38': "Endereço do pagador igual ao do sacador ou do portador",
    '39': "Endereço do apresentante incompleto ou não informado",
    '40': "Rua / Número inexistente no endereço",
    '41': "Informar a qualidade do endosso (M ou T)",
    '42': "Falta endosso do favorecido para o apresentante",
    '43': "Data da emissão rasurada",
    '44': "Protesto de cheque proibido – motivo 20/25/28/30 ou 35",
    '45': "Falta assinatura do emitente no cheque",
    '46': "Endereço do emitente no cheque igual ao do banco pagador",
    '47': "Falta o motivo da devolução no cheque ou motivo ilegível",
    '48': "Falta assinatura do sacador no título",
    '49': "Nome do apresentante não informado/incompleto/incorreto",
    '50': "Erro de preenchimento do título",
    '51': "Título com direito de regresso vencido",
    '52': "Título apresentado em duplicidade",
    '53': "Título já protestado",
    '54': "Letra de Câmbio vencida – falta aceite do pagador",
    '55': "Título – falta tradução por tradutor público",
    '56': "Falta declaração de saldo assinada no título",
    '57': "Contrato de Câmbio – falta conta gráfica",
    '58': "Ausência do Documento Físico",
    '59': "Pagador Falecido",
    '60': "Pagador Apresentou Quitação do Título",
    '61': "Título de outra jurisdição territorial",
    '62': "Título com emissão anterior à concordata do pagador",
    '63': "Pagador consta na lista de falência",
    '64': "Apresentante não aceita publicação de edital",
    '65': "Dados do sacador em branco ou inválido",
    '66': "Titulo sem autorização para protesto por edital",
    '67': "Valor divergente entre título e comprovante",
    '68': "Condomínio não pode ser protestado para fins falimentares",
    '69': "Vedada a intimação por edital para protesto falimentar",
    '70': "Dados do Beneficiário em branco ou inválido",
    '71': "CNPJ/CPF do beneficiário incompatível com a espécie",
    '72': "Rua incorreta",
    '73': "Apartamento incorreto",
    '74': "Bloco incorreto",
    '98': "Falta de tempo hábil para recolhimento do pagamento",
    '99': "Outros",
}


# ------------------------------------------------------------- outros dominios

TIPOS_DE_PROTESTO: dict[str, str] = {
    'C': "Comum",
    'F': "Falimentar",
}

MOTIVOS_DE_PROTESTO: dict[str, str] = {
    '1': "Falta de pagamento",
    '2': "Falta de aceite",
    '3': "Falta de devolucao",
}

TIPOS_DE_ENDOSSO: dict[str, str] = {
    'M': "Mandato",
    'T': "Translativo",
    'S': "Sem endosso",
}

TIPOS_DE_APRESENTANTE: dict[str, str] = {
    '0': "Banco",
    '1': "Empresa",
    '2': "Condominio",
    '3': "Governo",
    '4': "Particular",
}

ORIGENS_DE_ANUENCIA: dict[str, str] = {
    '1': "Arquivo da CRA",
    '2': "Cenprot",
    '3': "documento recebido no cartório",
}

TIPOS_DE_MOEDA: dict[str, str] = {
    '1': "Real Brasileiro (R$)",
}

UFS: tuple[str, ...] = ('AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO', 'EX')


# ---------------------------------------------------------------- consultas


_DOMINIOS: dict[str, dict] = {
    "especie": ESPECIES,
    "ocorrencia": OCORRENCIAS,
    "irregularidade": IRREGULARIDADES,
    "tipo_protesto": TIPOS_DE_PROTESTO,
    "motivo_protesto": MOTIVOS_DE_PROTESTO,
    "tipo_endosso": TIPOS_DE_ENDOSSO,
    "tipo_apresentante": TIPOS_DE_APRESENTANTE,
    "anuencia_origem": ORIGENS_DE_ANUENCIA,
    "tipo_moeda": TIPOS_DE_MOEDA,
}


def rotulo(dominio: str, codigo: Any) -> str:
    """O que o codigo significa, em portugues, ou '' se nao existir.

    Devolve texto vazio em vez de levantar: isto vai para a TELA, e uma tela
    que quebra porque o arquivo trouxe um codigo novo e pior que uma tela que
    mostra o codigo cru ao lado do resto do titulo.
    """
    tabela = _DOMINIOS.get(dominio)
    if not tabela:
        raise CraError(
            f"Domínio {dominio!r} não existe. Os que existem são: "
            f"{', '.join(sorted(_DOMINIOS))}.")
    achado = tabela.get(str(codigo).strip().upper() if dominio == "especie"
                        else str(codigo).strip())
    if isinstance(achado, dict):
        return achado.get("rotulo", "")
    return achado or ""


def especie(codigo: Any) -> dict:
    """A especie do titulo, com o aviso quando ela esta fora do esquema."""
    chave = str(codigo or "").strip().upper()
    if chave in ESPECIES:
        return {"codigo": chave, "rotulo": ESPECIES[chave], "no_esquema": True,
                "observacao": None}
    if chave in ESPECIES_FORA_DO_ESQUEMA:
        return {"codigo": chave, "rotulo": chave, "no_esquema": False,
                "observacao": ESPECIES_FORA_DO_ESQUEMA[chave]}
    raise CraError(
        f"Espécie de título {chave!r} não existe no contrato da CRA. As mais "
        f"usadas nesta serventia são DMI (duplicata mercantil por indicação) e "
        f"CDA (certidão da dívida ativa).")


def ocorrencia(codigo: Any, versao: str = "1.22-apontamento") -> dict:
    """A ocorrencia, conferida contra a VERSAO do arquivo.

    Conferir contra a versao importa: 'W' — averbacao de titulo ja protestado —
    vale na 1.21 e nao vale num arquivo de apontamento 1.22. Mandar 'W' num
    apontamento e arquivo recusado pela Central, e o titulo fica sem retorno.
    """
    chave = str(codigo or "").strip().upper()
    curta = versao.split("-")[0]
    if chave in OCORRENCIAS_INTERNAS_DO_EOFICIO:
        raise CraError(
            f"{chave!r} é código interno do E-Ofício, e não ocorrência da CRA "
            f"({OCORRENCIAS_INTERNAS_DO_EOFICIO[chave]}).")
    achado = OCORRENCIAS.get(chave)
    if not achado:
        raise CraError(f"Ocorrência {chave!r} não existe no contrato da CRA.")
    if curta not in achado["versoes"]:
        raise CraError(
            f"A ocorrência {chave} ({achado['rotulo']}) não vale na versão "
            f"{versao} — só em {' e '.join(achado['versoes'])}.")
    return {"codigo": chave, "rotulo": achado["rotulo"],
            "versoes": achado["versoes"]}


def irregularidade(codigo: Any) -> dict:
    """Um dos 76 motivos de devolucao do titulo."""
    chave = str(codigo or "").strip()
    if chave not in IRREGULARIDADES:
        raise CraError(
            f"Irregularidade {chave!r} não existe. São 76 códigos, de 1 a 74 "
            f"mais 98 e 99.")
    return {"codigo": chave, "rotulo": IRREGULARIDADES[chave]}


def conferir_titulo(titulo: dict, versao: str = "1.22-apontamento") -> list[str]:
    """O que esta errado no titulo, em frases de balcao. Lista vazia = em ordem.

    Confere o CONTRATO — os codigos e o que e obrigatorio no esquema. Nao
    confere a regra de protesto: prazo, competencia e valor sao do modulo do
    Protesto, nao da CRA.
    """
    faltas: list[str] = []
    # `data_vencimento` NAO ESTA AQUI, e isso e correcao de 25/08/2026.
    #
    # Eu a tinha posto na lista de obrigatorios, e a medicao das remessas
    # reais desmentiu: 37 titulos de 343 chegam da PROPRIA CENTRAL com
    # `99999999` nas posicoes 236-243 — a marca de "sem vencimento" —, todos
    # da especie CDA, que e certidao de divida ativa e nao tem vencimento
    # nenhum. Recusa-los seria recusar o que a Central manda.
    #
    # E o contrato oficial ja tem palavra para isso, e nao e "arquivo torto":
    # a irregularidade 33 e "Falta data de vencimento no titulo". Titulo sem
    # vencimento e um titulo com irregularidade catalogada — que e, aliais,
    # motivo para protestar, e nao para devolver.
    obrigatorios = ("especie", "numero_titulo", "data_emissao",
                    "valor", "saldo", "praca_protesto")
    for campo in obrigatorios:
        if not str(titulo.get(campo) or "").strip():
            faltas.append(f"Falta {campo.replace('_', ' ')}.")
    for campo, dominio in (("especie", "especie"), ("ocorrencia", "ocorrencia"),
                           ("tipo_protesto", "tipo_protesto"),
                           ("motivo_protesto", "motivo_protesto"),
                           ("tipo_endosso", "tipo_endosso"),
                           ("tipo_moeda", "tipo_moeda")):
        valor = titulo.get(campo)
        if valor in (None, ""):
            continue
        try:
            if dominio == "ocorrencia":
                ocorrencia(valor, versao)
            elif dominio == "especie":
                especie(valor)
            elif not rotulo(dominio, valor):
                raise CraError(
                    f"{campo.replace('_', ' ').capitalize()} {valor!r} não "
                    f"existe no contrato da CRA.")
        except CraError as erro:
            faltas.append(str(erro))
    for codigo in (titulo.get("irregularidades") or []):
        try:
            irregularidade(codigo)
        except CraError as erro:
            faltas.append(str(erro))
    devedores = titulo.get("devedores") or []
    if not devedores:
        faltas.append("O título tem de ter ao menos um devedor.")
    for i, d in enumerate(devedores, 1):
        if not str(d.get("nome") or "").strip():
            faltas.append(f"O devedor {i} está sem nome.")
        if not (str(d.get("CPF") or "").strip() or str(d.get("CNPJ") or "").strip()):
            faltas.append(f"O devedor {i} está sem CPF nem CNPJ.")
        if not (d.get("enderecos") or []):
            faltas.append(f"O devedor {i} está sem endereço — sem ele não há "
                          f"como intimar, e o protesto sai por edital.")
    if len(titulo.get("irregularidades") or []) > 9:
        faltas.append("O esquema aceita no máximo nove irregularidades por "
                      "título.")
    return faltas
