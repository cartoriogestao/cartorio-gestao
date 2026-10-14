"""
Naturezas do titulo do Registro de Imoveis — vocabulario do SAUIN.

DE ONDE VEIO
    Da tabela `tbRI_NaturezaTitulo_SAUIN` do E-Oficio, o sistema extrajudicial
    em uso na serventia: 128 naturezas, todas ativas. Nao e lista inventada — e
    a mesma que o selo eletronico do Maranhao reconhece. Adotar esta lista evita
    que o nosso sistema nomeie o ato de um jeito e o selo de outro.

O QUE CADA COLUNA E
    codigo  o codigo do SAUIN, preservado — e por ele que o selo conversa
    tipo    R = registro, AV = averbacao
    nome    a descricao como esta na tabela de origem
    ctp     operacao imobiliaria correspondente na carga da CTP, ou None quando
            a natureza nao e transacao imobiliaria. Garantia, constricao,
            retificacao, cancelamento e afins nao entram na CTP.

SOBRE A COLUNA `tipo`
    A tabela de origem NAO diz se e registro ou averbacao. A classificacao aqui
    foi feita pelo nome — o que comeca por "Averbacao" ou "Cancelamento" e AV —
    com cinco excecoes anotadas a mao: penhora, arresto, sequestro, renuncia de
    usufruto e indisponibilidade. As tres primeiras sao averbadas por forca do
    Codigo de Normas da CGJ/TJMA, arts. 502 e 532, "k", ainda que a Lei 6.015 as
    arrole no inciso de registro.

    Deu 55 registros e 73 averbacoes. E classificacao util, nao e dogma:
    confira antes de usar em massa.
"""
from __future__ import annotations

# (codigo SAUIN, tipo, nome, operacao da CTP)
NATUREZAS: tuple[tuple[int, str, str, str | None], ...] = (
    (  0, "R", "Bem de Família", None),
    (  1, "R", "Hipoteca", None),
    (  2, "R", "Alienação Fiduciária", None),
    (  3, "R", "Penhor", None),
    (  4, "AV", "Penhora", None),
    (  5, "AV", "Arresto", None),
    (  6, "AV", "Sequestro", None),
    (  7, "R", "Servidão", None),
    (  8, "R", "Usufruto", None),
    (  9, "R", "Contrato de Locação", None),
    ( 10, "R", "Rendas sobre imóveis", None),
    ( 11, "R", "Compromisso de Compra e Venda", "33"),
    ( 12, "R", "Cessão de Promessa de Compra e Venda", "35"),
    ( 13, "R", "Enfiteuse", "56"),
    ( 14, "R", "Anticrese", None),
    ( 15, "R", "Convenções Antenupciais", None),
    ( 16, "R", "Cédulas de Crédito Rural", None),
    ( 17, "R", "Cédulas de Crédito Industrial", None),
    ( 18, "R", "Cédulas de Crédito Bancário", None),
    ( 19, "R", "Cédulas de Crédito Comercial", None),
    ( 20, "R", "Cédulas de Crédito Hipotecária", None),
    ( 21, "R", "Contratos de Penhora Rural", None),
    ( 22, "R", "Empréstimos por Obrigações ao portador ou debêntures", None),
    ( 23, "R", "Incorporações de Condomínio", "68"),
    ( 24, "R", "Instituição de Condomínio", None),
    ( 25, "R", "Convenção de Condomínio", None),
    ( 26, "R", "Incorporação de Bens", "39"),
    ( 27, "R", "Integralização de Capital", "47"),
    ( 28, "R", "Loteamento Urbano", "45"),
    ( 29, "R", "Loteamento Rural", "45"),
    ( 30, "R", "Citações de Ações Reais ou Pessoais Reipersecutórias", None),
    ( 31, "R", "Carta de Arrematação", "41"),
    ( 32, "R", "Formal de Partilha", "69"),
    ( 33, "R", "Carta de Adjudicação", "15"),
    ( 34, "R", "Sentenças Declaratórias de Usucapião", "74"),
    ( 35, "R", "Usucapião Extrajudicial", "74"),
    ( 36, "R", "Compra e Venda", "11"),
    ( 37, "R", "Permuta", "13"),
    ( 38, "R", "Dação em Pagamento", "19"),
    ( 39, "R", "Transferência de Imóvel a Sociedade", "47"),
    ( 40, "R", "Doação", "67"),
    ( 41, "R", "Desapropriação", "64"),
    ( 42, "R", "Imissão Provisória na Posse", None),
    ( 43, "R", "Termos Administrativos ou Sentenças Declaratórias da Concessão de Uso Especial para fins de moradia", "61"),
    ( 44, "R", "Constituição do Direito de Superfície de Imóvel Urbano", "66"),
    ( 45, "R", "Contrato de Concessão de Direito Real de Uso de Imóvel Público", "60"),
    ( 46, "R", "Legitimação de Posse", "39"),
    ( 47, "R", "Conversão de Legitimação de Posse em Propriedade", "39"),
    ( 48, "R", "Título Definitivo", "73"),
    ( 49, "R", "Cisão", "58"),
    ( 50, "R", "Formal de Separação", "70"),
    ( 51, "R", "Divórcio Judicial", "70"),
    ( 52, "R", "Divórcio Extrajudicial", "70"),
    ( 53, "R", "Doação do Usufruto", "67"),
    ( 54, "R", "Convenções Antenupciais", None),
    ( 55, "AV", "Cancelamento de Hipoteca", None),
    ( 56, "AV", "Cancelamento de Alienação Fiduciária", None),
    ( 57, "AV", "Cancelamento do Usufruto", None),
    ( 58, "AV", "Renúncia de Usufruto", None),
    ( 59, "AV", "Cancelamento de Condição Resolutiva", None),
    ( 60, "AV", "Cancelamento de Pacto Comissório", None),
    ( 61, "AV", "Cancelamento de Matrícula", None),
    ( 62, "AV", "Cancelamento de Penhora", None),
    ( 63, "AV", "Cancelamento de Arresto", None),
    ( 64, "AV", "Cancelamento de Sequestro", None),
    ( 65, "AV", "Cancelamento de Servidão", None),
    ( 66, "AV", "Cancelamento de Notas Promissórias", None),
    ( 67, "AV", "Cancelamento de Cláusulas de Impenhorabilidade", None),
    ( 68, "AV", "Cancelamento de Cláusulas de Inalienabilidade", None),
    ( 69, "AV", "Cancelamento de Cláusulas de Incomunicabilidade", None),
    ( 70, "AV", "Cancelamento de Locação", None),
    ( 71, "AV", "Averbação da Emissão da CCI", None),
    ( 72, "AV", "Averbação de Patrimônio de Afetação", None),
    ( 73, "R", "Extinção de Patrimônio de Afetação", None),
    ( 74, "AV", "Averbação de Desistência de Incorporação", None),
    ( 75, "AV", "Averbação de Cláusulas de Impenhorabilidade", None),
    ( 76, "AV", "Averbação de Cláusulas de Inalienabilidade", None),
    ( 77, "AV", "Averbação de Cláusulas de Incomunicabilidade", None),
    ( 78, "AV", "Averbação de Cessão de Crédito", None),
    ( 79, "AV", "Averbação de Cessão de Promessa de Compra e Venda", None),
    ( 80, "AV", "Averbação de Mudança de Endereço", None),
    ( 81, "AV", "Averbação de Demolição", None),
    ( 82, "AV", "Averbação de Construção", None),
    ( 83, "AV", "Averbação de Reconstrução", None),
    ( 84, "AV", "Averbação de Desmembramento", None),
    ( 85, "AV", "Averbação de Unificação", None),
    ( 86, "AV", "Averbação de Remembramento", None),
    ( 87, "AV", "Averbação de Inscrição Municipal", None),
    ( 88, "AV", "Averbação de Alteração do Estado Civil", None),
    ( 89, "AV", "Averbação de Alteração de Nome", None),
    ( 90, "AV", "Averbação de Alteração de Regime de Bens", None),
    ( 91, "AV", "Averbação de Qualificação Pessoal", None),
    ( 92, "AV", "Averbação de Indicação ou Atualização de Confrontação", None),
    ( 93, "AV", "Averbação de Retificação de Área", None),
    ( 94, "AV", "Averbação de Omissão ou Erro", None),
    ( 95, "AV", "Averbação de Caução", None),
    ( 96, "AV", "Averbação de Caução Locatícia", None),
    ( 97, "AV", "Averbação de Cessão Fiduciária", None),
    ( 98, "AV", "Averbação de Restabelecimento Conjugal", None),
    ( 99, "AV", "Averbação de Constituição de Fideicomisso", None),
    (100, "AV", "Averbação de Premonitória", None),
    (101, "AV", "Averbação de Ajuizamento de Execução", None),
    (102, "AV", "Averbação de ex officio dos nomes do logradouros decretados pelo Poder Público", None),
    (103, "AV", "Averbação de Rerratificação do Contrato de Mútuo com Pacto Adjeto de Hipoteca", None),
    (104, "AV", "Averbação do Contrato de Locação", None),
    (105, "AV", "Averbação do Termo de Securatização de Crédito Imobiliário", None),
    (106, "AV", "Averbação da Notificação Extrajudicial", None),
    (107, "AV", "Averbação da Extinção da Concessão de Uso Especial para fins de Moradia", None),
    (108, "AV", "Averbação da Extinção do direito de Superfície de Imóvel Urbano", None),
    (109, "AV", "Averbação de Reserva Legal", None),
    (110, "AV", "Averbação de Servidão Ambiental", None),
    (111, "AV", "Averbação da Extinção da Legitimidade de Posse", None),
    (112, "AV", "Averbação da Extinção da Concessão de Direito real de Uso", None),
    (113, "AV", "Averbação da Sub-Rogação de Dívida", None),
    (114, "AV", "Averbação de Portabilidade", None),
    (115, "AV", "Averbação de Indisponibilidade de Bens", None),
    (116, "AV", "Averbação de Cancelamento de Indisponibilidade de Bens", None),
    (117, "AV", "Averbação de Bloqueio de Imóvel", None),
    (118, "AV", "Averbação de Mora", None),
    (119, "AV", "Averbação da Consolidação da Propriedade Fiduciária", "62"),
    (120, "AV", "Averbação de Distrato de Promessa de Compra e Venda", "21"),
    (121, "AV", "Averbação de Distrato de Compra e Venda", "21"),
    (122, "AV", "Averbação de Distrato por Extinção de Empresa", None),
    (123, "AV", "Averbação de Arrolamento de Bens", None),
    (124, "AV", "Averbação de Alteração de Novas Divisas", None),
    (125, "AV", "Averbação de Interdição", None),
    (126, "R", "Outro", None),
    (127, "R", "Não se aplica", None),

)

POR_CODIGO = {c: (t, n, op) for c, t, n, op in NATUREZAS}
POR_NOME = {n.lower(): (c, t, op) for c, t, n, op in NATUREZAS}

REGISTROS = tuple((c, n) for c, t, n, op in NATUREZAS if t == "R")
AVERBACOES = tuple((c, n) for c, t, n, op in NATUREZAS if t == "AV")


def operacao_ctp(nome_ou_codigo) -> str:
    """Operacao da CTP a partir da natureza. Vazio quando nao e transacao."""
    if nome_ou_codigo is None:
        return ""
    texto = str(nome_ou_codigo).strip()
    if texto.isdigit():
        item = POR_CODIGO.get(int(texto))
        return (item[2] or "") if item else ""
    item = POR_NOME.get(texto.lower())
    return (item[2] or "") if item else ""


def nomes(tipo: str | None = None) -> list[str]:
    """Nomes para a caixa de escolha da tela de lavratura."""
    return [n for c, t, n, op in NATUREZAS if tipo is None or t == tipo]
