"""
O vocabulario comum das seis atribuicoes da serventia.

DE ONDE VEM ESTE ARQUIVO
    Nao foi digitado: foi GERADO do acervo do E-Oficio, das tabelas
    tbAtribuicao, tbAtos, tbTipoSelo, tbFundo, tbTipoPapel e tbServico.
    Sao os codigos que o Tribunal reconhece, e mudar um deles a mao aqui
    e desalinhar o sistema do selo, da remessa e da tabela de custas.

POR QUE UM MODULO SO, E NAO UM POR ATRIBUICAO
    Porque o selo, os fundos, a tabela de custas e o papel de seguranca
    sao os MESMOS para as seis. Notas, Protesto, RCPJ, RTD, Registro de
    Imoveis e RCPN se distinguem pelo livro e pelo ato, nao pela maquina
    que sela e cobra. Quatro copias divergentes disto seria repetir,
    quatro vezes, o erro de numeracao de 18/08/2026.

O QUE ESTE MODULO NAO FAZ
    Nao fala com o selador, nao calcula emolumento e nao grava nada. E
    vocabulario: quem sao as atribuicoes, quais atos existem em cada uma,
    que tipo de selo cada ato usa, quais fundos incidem e que papel de
    seguranca a certidao pede.
"""
from __future__ import annotations


# ------------------------------------------------- as seis atribuicoes

ATRIBUICOES: dict[int, dict[str, str]] = {
    1: {"sigla": "NOTAS", "nome": "Notas"},
    2: {"sigla": "PROTESTO", "nome": "Protesto"},
    3: {"sigla": "RCPJ", "nome": "Registro Civil das Pessoas Jurídicas"},
    4: {"sigla": "RTD", "nome": "Registro de Títulos e Documento"},
    5: {"sigla": "RI", "nome": "Registro de Imóveis"},
    6: {"sigla": "RCPN", "nome": "Registro Civil das Pessoas Naturais"},
}

SIGLA_PARA_CODIGO: dict[str, int] = {v["sigla"]: k for k, v in ATRIBUICOES.items()}


# ------------------------------------------------------ tipos de selo
#
# Onze tipos. O 20, "Selo Eletronico", e o que 1.301 dos 1.317 servicos do
# acervo usavam; os outros dez sao selo fisico, de talao.

TIPOS_DE_SELO: dict[int, str] = {
    1: "Atos Gerais",
    2: "Atos Gratuitos",
    3: "Autenticações",
    4: "Reconhecimento de Firma",
    5: "Ato Gratuito Judicial",
    6: "Ato Oneroso Judicial",
    7: "Reconhecimento de Firma - Veículo",
    8: "Abertura de Firma",
    11: "Certidão",
    13: "Reconhecimento de Firma - Financeiro",
    20: "Selo Eletrônico",
}

SELO_ELETRONICO = 20

# ---- DOIS ESPACOS DE CODIGO, e confundi-los quebra o selo
#
# `tbAtos.intCodigoSelo` NAO aponta para TIPOS_DE_SELO: aponta para o cadastro
# de selos do E-Oficio (tbSelos), que por sua vez diz qual e o TIPO. O acervo
# tinha um unico selo cadastrado — o de codigo 10, "Eletronico", do tipo 20.
#
# Escrevo isto porque a armadilha e silenciosa: ler o 10 como tipo de selo
# devolve "nada encontrado" sem erro nenhum, e o ato sairia sem tipo.

SELOS: dict[int, dict] = {
    10: {"nome": "Eletrônico", "tipo": SELO_ELETRONICO, "serie": None},
    # O 20 nao existia no cadastro de selos do acervo: sao os CINCO ATOS DO
    # RCPN que gravaram, no campo do selo, o codigo do TIPO (20) em vez do
    # codigo do cadastro (10). Todos os outros 67 atos gravaram 10.
    #
    # Resolve para o mesmo selo eletronico, entao o efeito pratico e nenhum —
    # mas so porque esta tratado aqui. Sem este alias, os cinco atos do RCPN
    # sairiam "sem tipo de selo", e a inspecao ja apontou exatamente isso no
    # Livro C: "regularizar selos, emolumentos e destinacoes".
    20: {"nome": "Eletrônico", "tipo": SELO_ELETRONICO, "serie": None,
         "observacao": "alias: o acervo do RCPN gravou o tipo no lugar do código"},
}


# ------------------------------------------------------------ os atos
#
# 72 tipos de ato, com o codigo que o selador reconhece. `liberado`
# repete o que o acervo dizia: ato nao liberado nao se sela. `selo` e o
# codigo do CADASTRO de selos (ver SELOS acima), nao o tipo.

ATOS: dict[int, dict] = {
    101: {"atribuicao": 2, "selo": 10, "liberado": False, "nome": "Apostila de Haia"},
    102: {"atribuicao": 2, "selo": 10, "liberado": True, "nome": "Registro para Atos em Geral"},
    103: {"atribuicao": 2, "selo": 10, "liberado": True, "nome": "Averbação de Pagamento de Título"},
    104: {"atribuicao": 2, "selo": 10, "liberado": True, "nome": "Registro de para Baixa ou Cancelamento de Protesto"},
    105: {"atribuicao": 2, "selo": 10, "liberado": True, "nome": "Certidão de Protestos"},
    106: {"atribuicao": 2, "selo": 10, "liberado": False, "nome": "Certidão Unificada de Protesto"},
    107: {"atribuicao": 2, "selo": 10, "liberado": True, "nome": "Registro de Protesto para Intimação"},
    108: {"atribuicao": 2, "selo": 10, "liberado": True, "nome": "Pagamento de Título de Protesto"},
    109: {"atribuicao": 2, "selo": 10, "liberado": True, "nome": "Retirada de Título"},
    110: {"atribuicao": 2, "selo": 10, "liberado": True, "nome": "Registro de Protesto de Título"},
    201: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Apostila de Haia"},
    202: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Registro de Notas para Escritura com Valor Declarado"},
    203: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Registro de Notas para Escritura sem Valor Declarado"},
    204: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Registro para Atos em Geral"},
    205: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Registro para Autenticação"},
    206: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Averbação"},
    207: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Confecção de Cartão de Assinatura"},
    208: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Registro de Notas para Certidão"},
    209: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Comunicação Eletrônica de Transferência de Veículo"},
    210: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Notas para Procuração Poderes Específicos"},
    211: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Notas para Procuração Simples"},
    212: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Notas para Procuração Venda de Qualquer Espécie"},
    213: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Registro de Pública Forma de Documento"},
    214: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Reconhecimento de Firma"},
    215: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Revogação de Procuração"},
    216: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Notas para Substabelecimento"},
    217: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Notas para Testamento"},
    218: {"atribuicao": 1, "selo": 10, "liberado": True, "nome": "Notas para Procuração INSS"},
    301: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Acima de 3 Diligências"},
    302: {"atribuicao": 4, "selo": 10, "liberado": True, "nome": "Apostila de Haia"},
    303: {"atribuicao": 4, "selo": 10, "liberado": True, "nome": "Averbação de Títulos e Documentos com Valor Declarado"},
    304: {"atribuicao": 4, "selo": 10, "liberado": True, "nome": "Averbação Integral de Título e Documento sem Valor Declarado"},
    305: {"atribuicao": 4, "selo": 10, "liberado": True, "nome": "Registro Integral de Títulos e Documentos com Valor Declarado"},
    306: {"atribuicao": 4, "selo": 10, "liberado": True, "nome": "Registro Integral de Títulos e Documentos sem Valor Declarado"},
    307: {"atribuicao": 4, "selo": 10, "liberado": True, "nome": "Registro Resumido de Títulos e Documentos com Valor Declarado"},
    308: {"atribuicao": 4, "selo": 10, "liberado": True, "nome": "Registro Resumido de Títulos e Documentos sem Valor Declarado"},
    309: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Registro para Atos em Geral"},
    310: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Autenticação de Livros Contábeis"},
    311: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Buscas em Livros ou Papéis Arquivados Acima de Dez Anos"},
    312: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Buscas em Livros ou Papéis Arquivados até Dez Anos"},
    313: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Cancelamento, Inclusive Busca e Certidão"},
    314: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Certidão Negativa para Pessoas Jurídicas"},
    315: {"atribuicao": 4, "selo": 10, "liberado": True, "nome": "Certidão Negativa para Títulos e Documentos"},
    316: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Certidão Notificação"},
    317: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Registro de Diligências Fora da Zona Urbana"},
    318: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Matrícula de Oficina Impressora, Jornal e Outros Periódicos, Inclusive a Certidão"},
    319: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Averbação de Pessoas Jurídicas, Incluíndo os Atos do Processo, Registro e Arquivamento"},
    320: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Certidão de Atos de Processo de Pessoa Jurídica"},
    321: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Certidão por Peça Reproduzida e/ ou Folha (Pessoa Jurídica)"},
    322: {"atribuicao": 4, "selo": 10, "liberado": True, "nome": "Certidão por peça Reproduzida e/ ou Folha (Títulos e Documentos)"},
    323: {"atribuicao": 3, "selo": 10, "liberado": True, "nome": "Inscrição de Pessoa Jurídica Incluindo os Atos do Processo, Registro e Arquivamento"},
    401: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Apostila de Haia"},
    402: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Registro/Averbação de Imóvel para o Ato com Valor Declarado"},
    403: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Registro/Averbação de Imóvel para o Ato sem Valor Declarado"},
    404: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Registro para Atos em Geral"},
    405: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Baixa ou Cancelamento"},
    406: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Certidão de Registro de Imóvel"},
    407: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Constituição, Incorporação ou Instituição de Condomínio"},
    408: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Convenção de Condomínio"},
    409: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Unidades de Condominio"},
    410: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Remembramento de Lote"},
    411: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Subdivisão de Lote"},
    412: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Loteamento Rural"},
    413: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Loteamento Urbano"},
    414: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Registro de Pagamento de Prestação"},
    415: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Registro de Imóvel para o Ato de Prenotação"},
    416: {"atribuicao": 5, "selo": 10, "liberado": True, "nome": "Abertura de Matrícula"},
    501: {"atribuicao": 6, "selo": 20, "liberado": True, "nome": "Atos em Geral RCPN"},
    502: {"atribuicao": 6, "selo": 20, "liberado": True, "nome": "Registro e Certidão de Nascimento"},
    503: {"atribuicao": 6, "selo": 20, "liberado": True, "nome": "Registro e Certidão de Casamento"},
    504: {"atribuicao": 6, "selo": 20, "liberado": True, "nome": "Registro e Certidão de Óbito"},
    505: {"atribuicao": 6, "selo": 20, "liberado": True, "nome": "Edital de Proclamas"},
}

# ---- o que o acervo trazia torto, e nao se conserta por conta propria
#
# O E-Oficio tinha o codigo 305 cadastrado DUAS vezes: uma no RTD, com
# selo cadastrado, e outra no RCPJ, SEM selo. Codigo de ato e o que o
# selador reconhece — dois donos para o mesmo codigo e ambiguidade na hora
# de selar. Ficou a entrada com tipo de selo, e a outra esta registrada
# aqui para ser perguntada a COGEX, nao para ser esquecida.

CONFLITOS_NO_ACERVO: tuple[dict, ...] = (
    {"codigo": 305, "atribuicao_descartada": 3, "selo": None, "nome": "Registro Integral de Títulos e Documentos com Valor Declarado", "observacao": "codigo repetido no acervo; prevaleceu a entrada com tipo de selo"},
    {"codigo": 501, "selo": 20, "nome": "Atos em Geral RCPN",
     "observacao": "os cinco atos do RCPN (501 a 505) gravaram o TIPO de selo no "
                   "campo do código do selo; os outros 67 atos gravaram o código"},
)


# ------------------------------------------------------------- fundos
#
# Os cinco que o cadastro de fundos do E-Oficio traz. QUATRO deles entram na
# conta da parte e aparecem na linha do selo:
#   "Total R$ 134,43 Emol R$ 120,03 FERC R$ 3,60 FADEP R$ 4,80 FEMP R$ 4,80
#    FERRFIS R$ 1,20"
#
# CORRECAO DE 21/08/2026. Esta lista dizia "sao eles que aparecem na linha do
# selo", no plural dos cinco. Nao e verdade, e a diferenca custa 5% de todo
# ato. Conferindo:
#   - nos 39 textos de selo reais, um por prefixo: FERC em 39, FADEP em 38,
#     FEMP em 38, FERRFIS em 4 e ISS em ZERO;
#   - a tabela de precos (`tbServico_Tabela`) tem quatro colunas de fundo —
#     FERMOJUPI, MP, DP e ferrfis — e NENHUMA de ISS;
#   - em 400 valores reais de 2026, o total fecha ao centavo com emolumento +
#     os quatro.
# O ISS e o imposto municipal sobre o servico, devido pelo delegatario ao
# Municipio; nao e repasse cobrado no balcao. Quem calcula deve usar
# `custas.CAMPOS_NO_TOTAL`, e nao esta lista.
#
# DIVERGENCIA DE SIGLA, e nao e erro de digitacao: o cadastro de fundos
# escreve FADP e o texto do selo do Tribunal escreve FADEP. E o mesmo
# fundo, o da Defensoria. A leitura aceita as duas formas.
#
# CORRECAO DE 25/10/2026 — O NOME DO FERC. O `tbFundo` do E-Oficio da ao
# codigo 1 (FERC) o nome «Fundo Especial de Modernizacao e Reaparelhamento do
# Judiciario», e este arquivo o copiou. Esse nome e o do FERJ, que e OUTRO
# fundo: o FERJ e a taxa de 12% que sai de dentro do emolumento; o FERC sao os
# 3% cobrados por cima, que ressarcem os atos gratuitos do Registro Civil
# (correcao do oficial: «ferj e ferc sao diferentes»). O nome agora e o do
# Codigo de Normas do MA, art. 217. O codigo, a sigla e o percentual, que sao
# o que o Tribunal reconhece, nao mudaram.

FUNDOS: tuple[dict, ...] = (
    {"codigo": 1, "sigla": "FERC", "percentual": 3, "nome": "Fundo Especial das Serventias de Registro Civil de Pessoas Naturais do Estado do Maranhão"},
    {"codigo": 2, "sigla": "FEMP", "percentual": 4, "nome": "Fundo Especial do Ministério Público Estadual"},
    {"codigo": 3, "sigla": "FADP", "percentual": 4, "nome": "Fundo de Aparelhamento da Defensoria Pública do Estado do Maranhão"},
    {"codigo": 4, "sigla": "ISS", "percentual": 5, "nome": "Imposto Sobre Serviços"},
    {"codigo": 5, "sigla": "FERRFIS", "percentual": 1, "nome": "Fundo Especial Registral de Regularização Fundiária de Interesse Social"},
)

SINONIMOS_DE_FUNDO: dict[str, tuple[str, ...]] = {
    "FERC": ("FERC", "FERMOJUPI"),
    "FEMP": ("FEMP", "MP"),
    "FADP": ("FADP", "FADEP", "DP"),
    "ISS": ("ISS",),
    "FERRFIS": ("FERRFIS", "FERFIS"),
}


# ------------------------------------------------- papel de seguranca
#
# A certidao sai em papel de seguranca, e o papel tem fornecedor e serie a
# controlar. Zero e "sem papel" — a certidao comum, em papel branco.

TIPOS_DE_PAPEL: dict[int, str] = {
    0: "Sem papel",
    1: "Azul (Certidão Portável)",
    2: "Rosa (Certidão Portável)",
    3: "Papel de Segurança - TJMA",
    4: "Papel de Segurança - ARPEN",
    5: "Papel de Segurança - Casa da Moeda",
    6: "Papel de Segurança - Extradigital Softwares e Equipamentos Ltda",
    7: "Papel de Segurança - Gráfica e Editora Líder Ltda",
    8: "Papel de Segurança - Indústria Gráfica Brasileira Ltda",
    9: "Papel de Segurança - Js Grafica Editora Encadernadora Ltda",
    10: "Papel de Segurança - Setagraf",
    11: "Papel de Segurança - Tress Impressos De Segurança Ltda",
}


# --------------------------------------- caminhos observados do selador
#
# O E-Oficio guardava, em tbServico.strURL_Selador, um caminho relativo por
# servico. Dos 1.317 servicos do acervo, so estes doze tinham caminho, e todos
# sao de RTD/RCPJ.
#
# CUIDADO COM A CONCLUSAO ERRADA, QUE EU TIREI E O OFICIAL DESFEZ
#     Esta lista dizia, ate 24/08/2026, que "nesta serventia o selo automatico
#     funcionava apenas nessas duas atribuicoes; as outras eram seladas a mao,
#     no portal". Estava ERRADO, e o oficial — que operou o sistema — corrigiu.
#
#     O que a coluna `strURL_Selador` mostra e so onde o E-Oficio guardou o
#     caminho POR SERVICO. Ele selava automatico em TUDO; nas outras
#     atribuicoes o caminho vinha de outro lugar do programa.
#
#     A prova esta em `tbSeloIndividual`: as 26.130 linhas tem `memJson` — o
#     payload enviado ao selador — preenchido em TODAS as atribuicoes, e
#     `strURLAto` guarda o caminho que cada selo usou. Ver
#     `CAMINHOS_USADOS_POR_ESTA_CASA`, logo abaixo, que e a medida de verdade.
#
#     A licao: coluna vazia nao prova que a coisa nao acontecia — prova que
#     aquela coluna nao era onde ela ficava.
#
# A base (URL, usuario e senha) morava em tbSeladorConfiguracao, tabela de
# tres colunas que saiu VAZIA na exportacao.

CAMINHOS_OBSERVADOS_DO_SELADOR: tuple[str, ...] = (
    "/selo/rtdpj/acima-tres-diligencias",
    "/selo/rtdpj/apostila-haia",
    "/selo/rtdpj/ato-declarado/integral/com-valor",
    "/selo/rtdpj/ato-declarado/integral/sem-valor",
    "/selo/rtdpj/ato-declarado/resumido/sem-valor",
    "/selo/rtdpj/atos-em-geral",
    "/selo/rtdpj/busca-ate-dez-anos",
    "/selo/rtdpj/diligencia/zona-urbana",
    "/selo/rtdpj/matricula",
    "/selo/rtdpj/pessoa-juridica/averbacao",
    "/selo/rtdpj/pessoa-juridica/certidao",
    "/selo/rtdpj/titulo-documento/certidao/por-peca",
)


# ------------------------- os caminhos que esta casa REALMENTE usou
#
# MEDIDO em 24/08/2026, em `tbSeloIndividual.strURLAto`: 26.123 selos com o
# caminho gravado, em 34 caminhos distintos, cobrindo as CINCO atribuicoes que
# a casa pratica. E a prova de que o selo automatico funcionava em todas — e
# nao so em RTD/RCPJ, como esta lista acima levou a crer.
#
# O numero ao lado e quantos selos sairam por aquele caminho. Serve para
# escolher o que fazer primeiro: `/selo/notas/reconhecimento-firma` sozinho
# responde por metade do movimento da casa.
#
# TODOS os 34 estao no contrato de `selador.py`, que tem 181 endpoints vindos
# da documentacao oficial. Nenhum caminho usado ficou de fora — o contrato
# cobre o que a casa faz.

CAMINHOS_USADOS_POR_ESTA_CASA: dict[str, int] = {
    "/selo/civil/atos-em-geral": 1238,
    "/selo/civil/casamento/segunda-via": 15,
    "/selo/civil/nascimento": 28,
    "/selo/civil/nascimento/segunda-via": 122,
    "/selo/civil/nascimento/transcricao/segunda-via": 1,
    "/selo/civil/obito": 8,
    "/selo/civil/obito/segunda-via": 1,
    "/selo/imovel/ato-declarado/com-valor": 34,
    "/selo/imovel/ato-declarado/sem-valor": 86,
    "/selo/imovel/atos-em-geral": 451,
    "/selo/imovel/certidao": 667,
    "/selo/imovel/lote/subdivisao": 41,
    "/selo/imovel/prenotacao": 829,
    "/selo/notas/ato-declarado/com-valor": 28,
    "/selo/notas/ato-declarado/sem-valor": 15,
    "/selo/notas/atos-em-geral": 739,
    "/selo/notas/autenticacao": 3664,
    "/selo/notas/cartao-assinatura": 2667,
    "/selo/notas/procuracao/poderes-especificos": 217,
    "/selo/notas/procuracao/simples": 22,
    "/selo/notas/procuracao/venda": 1,
    "/selo/notas/reconhecimento-firma": 13776,
    "/selo/protesto/atos-em-geral": 406,
    "/selo/protesto/baixa-cancelamento": 163,
    "/selo/protesto/certidao": 57,
    "/selo/protesto/pagamento": 465,
    "/selo/protesto/retirada": 147,
    "/selo/protesto/titulo": 70,
    "/selo/rtdpj/ato-declarado/integral/com-valor": 1,
    "/selo/rtdpj/ato-declarado/integral/sem-valor": 27,
    "/selo/rtdpj/atos-em-geral": 53,
    "/selo/rtdpj/atos-em-geral-com-livro": 46,
    "/selo/rtdpj/pessoa-juridica/certidao": 36,
    "/selo/rtdpj/pessoa-juridica/certidao/por-peca": 2,
}

# A familia do caminho — o pedaco depois de `/selo/` — diz a atribuicao.
FAMILIA_DA_ATRIBUICAO: dict[str, int] = {
    "notas": 1,
    "protesto": 2,
    "imovel": 5,
    "civil": 6,
    # RTD e RCPJ dividem a familia `rtdpj`, como dividem os livros no acervo.
    # Qual das duas e depende do ato, e nao do caminho.
}


def caminhos_da_atribuicao(atribuicao: int | str) -> dict[str, int]:
    """Os caminhos de selo que esta casa usou naquela atribuicao. So calcula.

    RTD e RCPJ devolvem os mesmos caminhos: o selador nao os separa, e o
    acervo tambem nao.
    """
    codigo = codigo_da_atribuicao(atribuicao)
    familias = {f for f, c in FAMILIA_DA_ATRIBUICAO.items() if c == codigo}
    if codigo in (3, 4):
        familias = {"rtdpj"}
    return {c: n for c, n in CAMINHOS_USADOS_POR_ESTA_CASA.items()
            if c.split("/")[2] in familias}


# ------------------------------------------------------------ consultas

def codigo_da_atribuicao(atribuicao: int | str) -> int:
    """Aceita 2, "PROTESTO" ou "protesto" e devolve sempre o codigo."""
    if isinstance(atribuicao, int):
        codigo = atribuicao
    else:
        codigo = SIGLA_PARA_CODIGO.get(str(atribuicao).strip().upper())
    if codigo not in ATRIBUICOES:
        raise KeyError(f"Atribuicao desconhecida: {atribuicao!r}")
    return codigo


def atos_da(atribuicao: int | str, so_liberados: bool = True) -> dict[int, dict]:
    """Os atos de uma atribuicao, pelo codigo ou pela sigla."""
    codigo = codigo_da_atribuicao(atribuicao)
    return {k: v for k, v in ATOS.items()
            if v["atribuicao"] == codigo and (v["liberado"] or not so_liberados)}


def ato(codigo: int) -> dict:
    """Um ato pelo codigo, com atribuicao e tipo de selo resolvidos."""
    if codigo not in ATOS:
        raise KeyError(f"Ato desconhecido: {codigo!r}")
    a = dict(ATOS[codigo], codigo=codigo)
    a["atribuicao_sigla"] = ATRIBUICOES[a["atribuicao"]]["sigla"]
    a["atribuicao_nome"] = ATRIBUICOES[a["atribuicao"]]["nome"]
    # `selo` e o codigo do cadastro de selos; o TIPO vem por dentro dele.
    cadastro = SELOS.get(a["selo"] or 0)
    a["selo_nome"] = cadastro["nome"] if cadastro else "sem selo cadastrado"
    a["tipo_selo"] = cadastro["tipo"] if cadastro else None
    a["tipo_selo_nome"] = (TIPOS_DE_SELO.get(a["tipo_selo"], "sem tipo de selo")
                           if cadastro else "sem tipo de selo")
    a["eletronico"] = bool(cadastro and cadastro["tipo"] == SELO_ELETRONICO)
    return a


def fundo(sigla: str) -> dict | None:
    """Um fundo pela sigla, aceitando as formas alternativas do texto do selo."""
    alvo = str(sigla or "").strip().upper()
    for f in FUNDOS:
        if alvo == f["sigla"] or alvo in SINONIMOS_DE_FUNDO.get(f["sigla"], ()):
            return dict(f)
    return None


def papel(codigo: int | None) -> str:
    """O nome do papel de seguranca; 0 e vazio dao "Sem papel"."""
    return TIPOS_DE_PAPEL.get(int(codigo or 0), f"Papel desconhecido ({codigo})")


# --------------------- os itens de custa que cada ato cobra, medidos
#
# MEDIDO em 24/08/2026: 24.849 selos de `tbSeloIndividual` em que deu para ler
# o codigo do ato dentro do `memJson` — o payload que foi ao selador.
#
# O MODELO QUE ISTO REVELA, E QUE NAO E O OBVIO
#     O CAMINHO e o ATO; o codigo TJ e o ITEM DE CUSTA. Um ato cobra VARIOS
#     itens. Nao ha de-para de um para um, e procurar um seria procurar o que
#     nao existe: medi, e so 55% dos codigos TJ saem por um caminho so.
#
#     A prova mais limpa esta na retirada de titulo protestado: os itens
#     17.10.1, 17.4 e 17.2 aparecem 49 vezes CADA — sempre os tres juntos, no
#     mesmo ato. E o "um selo por etapa" do Protesto, que o levantamento ja
#     tinha achado, valendo para as outras atribuicoes tambem.
#
#     O codigo do payload E o `strCodigoTJ` do servico: conferido em 24.048 de
#     24.360 (98,7%). E o mesmo `codigo_tj` de `cx_servicos`, no banco vivo —
#     logo, daqui sai o preco sem transcrever tabela nenhuma.
#
# COMO SE USA
#     Ao lavrar, `itens_de_custa_do_ato(caminho)` diz o que a casa cobrou
#     naquele ato, em ordem de frequencia. O numero e quantas vezes o item
#     saiu — item de 1 uso em 800 e excecao, e nao regra.

ITENS_DE_CUSTA_POR_CAMINHO: dict[str, dict[str, int]] = {
    "/selo/civil/casamento/segunda-via": {"14.5.1": 14, "14.5.7": 1},
    "/selo/civil/nascimento/segunda-via": {
        "14.5.1": 95, "14.5.6": 23, "14.5.7": 3, "14.6.6": 1,
    },
    "/selo/civil/nascimento/transcricao/segunda-via": {"14.5.1": 1},
    "/selo/civil/obito/segunda-via": {"14.5.1": 1},
    "/selo/imovel/ato-declarado/com-valor": {
        "16.3": 19, "16.9": 10, "16.11": 2, "16.45": 2, "16.22.4": 1,
    },
    "/selo/imovel/ato-declarado/sem-valor": {
        "16.22.2": 48, "16.5": 18, "16.9": 10, "16.22.4": 7, "16.24.1": 1, "16.2": 1,
        "16.22.4.2": 1,
    },
    "/selo/imovel/atos-em-geral": {
        "16.24.4": 187, "16.24.4.1": 184, "16.39": 22, "16.24.1": 19, "16.25.7": 14,
        "16.25.2": 5, "16.22.2": 3, "16.25.4": 3, "16.2": 3, "16.25.6": 2,
        "16.25.5": 2, "16.1": 2, "16.24.1.1": 1, "13.18": 1, "16.25.3": 1,
        "16.9.18": 1, "16.9.26": 1,
    },
    "/selo/imovel/certidao": {
        "16.24.1": 193, "16.24.4": 191, "16.24.4.1": 148, "16.24.2": 128,
        "16.24.1.1": 2, "16.25.6": 2, "16.25.4": 1, "16.25.5": 1, "16.25.7": 1,
    },
    "/selo/imovel/lote/subdivisao": {"16.2": 41},
    "/selo/imovel/prenotacao": {"16.1": 797, "16.39": 32},
    "/selo/notas/ato-declarado/com-valor": {"13.1": 21, "13.30": 6, "13.2": 1},
    "/selo/notas/ato-declarado/sem-valor": {"13.2": 13, "13.30": 2},
    "/selo/notas/atos-em-geral": {
        "13.30": 712, "14.5.1": 8, "13.12.1": 6, "13.12.3": 3, "17.5.1": 2,
        "13.9.4": 2, "13.9.3": 2, "13.17.2": 1, "13.12.4": 1, "16.42": 1,
        "13.17.1": 1,
    },
    "/selo/notas/autenticacao": {"13.18": 3664},
    "/selo/notas/cartao-assinatura": {"13.17.1": 2667},
    "/selo/notas/procuracao/poderes-especificos": {
        "13.9.3": 136, "13.17.1": 39, "13.9.2": 29, "13.30": 10, "13.18": 1,
        "13.21.1": 1, "13.17.2": 1,
    },
    "/selo/notas/procuracao/simples": {
        "13.9.3": 8, "13.30": 7, "13.9.2": 6, "13.17.1": 1,
    },
    "/selo/notas/procuracao/venda": {"13.9.3": 1},
    "/selo/notas/reconhecimento-firma": {
        "13.17.2": 7461, "13.17.4": 4973, "13.17.3": 1342,
    },
    "/selo/protesto/atos-em-geral": {
        "17.9": 263, "17.10.1": 72, "17.6.2": 47, "17.5.5": 10, "16.24.4": 6,
        "17.5.1": 4, "17.6.3": 3, "17.6.1": 1,
    },
    "/selo/protesto/baixa-cancelamento": {"17.2": 57, "17.3": 55, "17.5.1": 51},
    "/selo/protesto/certidao": {"17.5.1": 56, "17.5.2": 1},
    "/selo/protesto/pagamento": {
        "17.2": 163, "17.4": 143, "17.10.1": 142, "17.5.1": 17,
    },
    "/selo/protesto/retirada": {"17.10.1": 49, "17.4": 49, "17.2": 49},
    "/selo/protesto/titulo": {"17.1": 70},
    "/selo/rtdpj/ato-declarado/integral/com-valor": {"15.2": 1},
    "/selo/rtdpj/ato-declarado/integral/sem-valor": {"15.7.1": 24, "15.5.1": 3},
    "/selo/rtdpj/atos-em-geral": {
        "15.10.2": 38, "15.7.1": 9, "15.5.2": 3, "15.10.1": 2, "15.22": 1,
    },
    "/selo/rtdpj/atos-em-geral-com-livro": {"15.1": 46},
    "/selo/rtdpj/pessoa-juridica/certidao": {"15.10.1": 36},
    "/selo/rtdpj/pessoa-juridica/certidao/por-peca": {"15.10.1": 2},
}


def itens_de_custa_do_ato(caminho: str) -> dict[str, int]:
    """Os itens da tabela do Tribunal que esta casa cobrou naquele ato. So calcula.

    A chave e o codigo TJ (`16.1`, `17.2`), que e o mesmo `codigo_tj` de
    `cx_servicos` — de onde sai o preco. O valor e quantas vezes o item saiu
    naquele ato, em 24.849 selos reais: item de um uso so e excecao, e nao
    regra da casa.

    Caminho que a casa nunca usou devolve vazio, e nao erro: ato novo nao tem
    historico, e nao ter historico nao e defeito.
    """
    return dict(ITENS_DE_CUSTA_POR_CAMINHO.get(str(caminho or "").strip(), {}))
