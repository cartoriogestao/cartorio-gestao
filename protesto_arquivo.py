"""
O arquivo da CRA — ler a remessa de titulos e escrever o retorno.

POR QUE ISTO E O CORACAO DO PROTESTO
    Dos 1.370 titulos do acervo, 1.268 entraram pela CRA e 91 pela CENPROT.
    SETE foram digitados a mao, em seis anos. O Protesto desta serventia nao e
    uma tela de digitacao com uma integracao ao lado: e uma integracao, com uma
    tela de digitacao ao lado para os sete.

DE ONDE VEIO O LAYOUT
    NAO de manual. O layout de 600 posicoes da CRA nao estava documentado em
    lugar nenhum da maquina — o que havia era o `LAYOUT 600 PROTESTO - Novo.PDF`
    da SERASA, que e OUTRO arquivo com o mesmo tamanho e serve para reportar
    protestos a SERASA, nao para receber titulos da Central.

    Entao o layout abaixo foi MEDIDO. Ha 99 arquivos reais em
    `arquivos\\eoficio\\CRA`, com 1.058 registros de titulo. Cada campo foi conferido
    contra o que o E-Oficio gravou para o MESMO titulo em `tbAvisoProtesto`,
    e a taxa de acerto de cada um esta escrita ao lado. Os 1.058 registros
    casaram por numero do titulo — 100%.

    Onde a medicao nao fechou, esta escrito que nao fechou. Onde eu nao
    identifiquei o campo, ele se chama `reservado_NNN` e nao um nome bonito
    que fingisse conhecimento.

QUATRO ARQUIVOS, E NAO UM
    As posicoes 53 a 61 do cabecalho trazem ORIGEM(3) + DESTINO(3) + TIPO(3):

        BFOSDTTPR   apresentante -> cartorio : titulos para protesto (remessa)
        SDTBFORTP   cartorio -> apresentante : retorno dos protestados
        SDTBFOCRT   cartorio -> apresentante : confirmacao do recebimento
        SDTBFOAND   cartorio -> apresentante : andamento

    Isto importa mais do que parece: as pastas do E-Oficio NAO sao confiaveis.
    Ha arquivo de remessa dentro da pasta `Retorno`. Quem se guiar pela pasta
    le o arquivo errado com o layout errado. Guia-se pelo cabecalho.

O QUE ESTE MODULO NAO FAZ
    Nao aponta titulo, nao cobra, nao sela e nao grava. Le o arquivo e devolve
    estrutura; ou recebe estrutura e devolve arquivo. Quem aponta e o modulo do
    Protesto, dentro da transacao dele, usando `protesto_cra` para conferir os
    codigos e o nucleo para achar o lugar no livro.

FUNDAMENTO
    Lei 9.492/1997, arts. 5o a 8o (recepcao, protocolo e prazo).
    Provimento CNJ n. 87/2019; Codigo Nacional de Normas, Foro Extrajudicial.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import protesto_cra as CRA

TAMANHO_DO_REGISTRO = 600


class ArquivoError(ValueError):
    """Arquivo fora do padrao, com mensagem pronta para a tela."""


# --------------------------------------------------------- tipos de arquivo

TIPOS: dict[str, dict[str, str]] = {
    "BFOSDTTPR": {"origem": "apresentante", "destino": "cartório",
                  "nome": "Remessa de títulos para protesto",
                  "sentido": "ENTRADA"},
    "SDTBFORTP": {"origem": "cartório", "destino": "apresentante",
                  "nome": "Retorno dos títulos protestados",
                  "sentido": "SAIDA"},
    "SDTBFOCRT": {"origem": "cartório", "destino": "apresentante",
                  "nome": "Confirmação do recebimento da remessa",
                  "sentido": "SAIDA"},
    "SDTBFOAND": {"origem": "cartório", "destino": "apresentante",
                  "nome": "Andamento dos títulos",
                  "sentido": "SAIDA"},
}


# ------------------------------------------------------------------ o campo


@dataclass(frozen=True)
class Campo:
    """Um campo do registro, com a procedencia da medicao.

    `conferido` e a taxa de acerto contra o que o E-Oficio gravou para o mesmo
    titulo, em 343 registros de remessa. `None` quer dizer que nao houve como
    conferir — nao que esteja certo.
    """

    nome: str
    inicio: int          # 1-based, como no papel
    tamanho: int
    tipo: str = "texto"  # texto | numero | data | centavos
    conferido: float | None = None
    observacao: str = ""

    @property
    def fim(self) -> int:
        return self.inicio + self.tamanho - 1


def _fatiar(linha: str, c: Campo) -> str:
    return linha[c.inicio - 1:c.fim]


# ------------------------------------------------------- o registro de titulo
#
# Medido em 343 registros de remessa, campo a campo, contra `tbAvisoProtesto`.
# A ordem no arquivo e: CEDENTE na frente, DEVEDOR atras — e eu tinha invertido
# na primeira leitura. O que denunciou foi o endereco: o devedor e de Montes
# Altos (por isso protesta aqui) e o cedente e de fora. Endereco local no
# segundo bloco, e nao no primeiro.

TITULO_NA_REMESSA: tuple[Campo, ...] = (
    Campo("tipo_registro", 1, 1, "texto", 100.0),
    Campo("codigo_do_apresentante", 2, 3, "texto", None,
          "003 no acervo inteiro; o mesmo do cabeçalho"),
    Campo("identificacao_do_apresentante", 5, 15, "texto", None,
          "em branco em 221 dos 343; identificação livre do apresentante"),
    Campo("cedente_nome", 20, 45, "texto", 86.6,
          "as diferenças são acento e abreviação corrigidos depois no E-Ofício"),
    Campo("cedente_nome_2", 65, 45, "texto", 82.8,
          "segunda linha do nome, ou nome de fantasia"),
    Campo("cedente_documento", 110, 14, "texto", 100.0,
          "conferiu ao dígito nos 57 títulos em que o acervo tem o documento"),
    Campo("cedente_endereco", 124, 45, "texto", 49.1,
          "metade diverge: o E-Ofício guarda o endereço corrigido, não o "
          "recebido. A CONFERIR qual das duas versões vale."),
    Campo("cedente_cep", 169, 8, "texto", 100.0),
    Campo("cedente_cidade", 177, 20, "texto", 82.5,
          "diferenças de acento: «SAO LUIS» no arquivo, «São Luís» no acervo"),
    Campo("cedente_uf", 197, 2, "texto", 100.0),
    Campo("nosso_numero", 199, 15, "texto", None,
          "290 valores distintos em 343 registros — é identificador, não código"),
    Campo("especie", 214, 3, "texto", 100.0,
          "um dos 64 códigos de protesto_cra.ESPECIES"),
    Campo("numero_do_titulo", 217, 11, "texto", 100.0,
          "os 1.058 registros de todos os tipos casaram por este campo"),
    Campo("data_de_emissao", 228, 8, "data", 99.7),
    Campo("data_de_vencimento", 236, 8, "data_vencimento", 87.2,
          "as falhas são «99999999», que é a marca de título sem vencimento. "
          "O tipo é `data_vencimento` e não `data` porque a VOLTA é "
          "diferente: vazio aqui se escreve como a marca, não como zeros"),
    Campo("tipo_de_moeda", 244, 3, "numero", None,
          "«001» nos 343; é o real, como o tipo_moeda «1» do esquema XML"),
    Campo("valor_do_titulo", 247, 14, "centavos", None,
          "o valor de face; o acervo guarda o saldo, então não dá para "
          "conferir os dois contra a mesma coluna"),
    Campo("saldo_a_protestar", 261, 14, "centavos", 99.1,
          "é ESTE que vira `curValor` no acervo, e é sobre ele que se protesta"),
    Campo("praca_de_protesto", 275, 20, "texto", None,
          "traz «CIDADE EXEMPLO» — é a praça para onde o título foi remetido. "
          "Não há coluna equivalente no acervo para conferir contra, e por "
          "isso fica sem taxa."),
    Campo("tipo_de_endosso", 295, 1, "texto", None,
          "M mandato (263), T translativo (2), branco (78) — o M/T/S do esquema"),
    Campo("aceite", 296, 1, "texto", None, "N não aceito (259), A aceito (61)"),
    Campo("motivo_do_protesto", 297, 1, "texto", None,
          "«1» nos 343: falta de pagamento"),
    Campo("devedor_nome", 298, 45, "texto", 92.7),
    Campo("devedor_tipo_de_documento", 343, 3, "numero", 100.0,
          "001 = CNPJ (119), 002 = CPF (224); bate exatamente com quantos "
          "títulos têm CNPJ no acervo"),
    Campo("devedor_documento", 346, 14, "texto", 100.0),
    Campo("reservado_360", 360, 11, "texto", None, "brancos ou zeros nos 343"),
    Campo("devedor_endereco", 371, 45, "texto", 87.2),
    Campo("devedor_cep", 416, 8, "texto", 96.5),
    Campo("devedor_cidade", 424, 20, "texto", 100.0),
    Campo("devedor_uf", 444, 2, "texto", 99.7,
          "a única falha é «ma» minúsculo no arquivo"),
    Campo("reservado_446", 446, 40, "texto", None,
          "zeros, com uma letra D/C/I na posição 477 — não identificada"),
    # ERA `devedor_bairro` em 486, com 22 posicoes, e "A CONFERIR". O limite
    # estava errado por DUAS posicoes, e quem achou foi o teste de ida e
    # volta: o arquivo real traz `000  VL JOA` e a reescrita saia
    # `000VL JOAO `. As duas posicoes de 486 sao separador — dois espacos em
    # 343 de 343 linhas de remessa e 328 de 328 de confirmacao —, e o bairro
    # comeca em 488 com 20 posicoes.
    #
    # Com o limite certo, deixa de ser "A CONFERIR": o que sai sao bairros de
    # Cidade Exemplo — CENTRO, VL JOAO ALBERTO, ACUDE. Nao ha coluna de bairro
    # em `tbAvisoProtesto` contra a qual conferir (nao existe), e por isso a
    # primeira medicao parou aqui; o proprio arquivo respondeu.
    Campo("reservado_486", 486, 2, "texto", None,
          "separador: dois espaços em todas as 343 linhas de remessa e 328 "
          "de confirmação medidas"),
    Campo("devedor_bairro", 488, 20, "texto", None,
          "o bairro do devedor. Achado pelo teste de ida e volta, que mostrou "
          "o limite errado por duas posições; antes disto era «A CONFERIR» em "
          "486 com 22 posições"),
    # TEXTO, e nao numero: campo que ninguem identificou nao se interpreta.
    # Lido como numero, `0000000000        000000000000` — que e o que o
    # ANDAMENTO traz aqui — virava um inteiro so, e a volta escrevia 38 zeros
    # seguidos, perdendo os espacos do meio. Quem achou foi o teste de ida e
    # volta. Texto e o unico tipo que devolve o campo como ele veio.
    Campo("reservado_508", 508, 38, "texto", None,
          "zeros nas 343 remessas; no andamento vem em três pedaços, com "
          "espaços no meio. Lido como texto de propósito — campo sem nome "
          "não se interpreta"),
    Campo("reservado_546", 546, 51, "texto", None, "zeros e brancos nos 343"),
    Campo("sequencial", 597, 4, "numero", 100.0,
          "conta a partir do cabeçalho, que é 0001"),
)


# --------------------------------------------------- o registro do retorno
#
# Medido em 24/08/2026, contra 383 registros reais de `SDTBFORTP` — ver
# DOCUMENTACAO/LAYOUT_RETORNO_MEDIDO.md. Não é o layout da remessa: metade do
# registro (espécie, cedente, devedor) vem sempre em branco, porque o retorno
# não repete o que já foi enviado, e um bloco novo em 446–485 carrega o que só
# o retorno sabe — protocolo, ocorrência e a data dela.
#
# Os 383 casaram 100% com o acervo por `nosso_numero` — é essa a chave que
# liga o retorno ao título, e não `numero_do_titulo`, que aqui vem em branco.

TITULO_NO_RETORNO: tuple[Campo, ...] = (
    Campo("tipo_registro", 1, 1, "texto", 100.0),
    Campo("codigo_do_apresentante", 2, 3, "texto", None,
          "mesma posição da remessa; não medido separadamente no retorno"),
    Campo("identificacao_do_apresentante", 5, 15, "texto", None,
          "mesma posição da remessa; não medido separadamente no retorno"),
    Campo("branco_20", 20, 179, "texto", None,
          "espécie, cedente e devedor: sempre em branco nos 383"),
    Campo("nosso_numero", 199, 15, "texto", 100.0,
          "a chave que casou os 383 registros com tbAvisoProtesto"),
    Campo("branco_214", 214, 33, "texto", None,
          "espécie, número do título e datas de emissão/vencimento: sempre "
          "em branco nos 383"),
    Campo("valor_do_titulo", 247, 14, "centavos", 99.7,
          "contra curValorRealTitulo — mesma posição da remessa"),
    Campo("saldo_a_protestar", 261, 14, "centavos", 99.7,
          "contra curValor — mesma posição da remessa"),
    Campo("branco_275", 275, 171, "texto", None,
          "praça, endosso, aceite, motivo, cedente e devedor: sempre em "
          "branco nos 383"),
    Campo("reservado_446", 446, 2, "texto", None,
          "constante «01» nos 383 — código fixo, não dado"),
    Campo("protocolo", 448, 10, "numero", 98.4, "contra intProtocolo"),
    Campo("ocorrencia", 458, 1, "texto", 95.8,
          "contra intCodigoOcorrencia — inclusive o «C» sem significado "
          "oficial, já visto 1.027 vezes no acervo inteiro. As 6 divergências "
          "dos 383 são todas título com cancelamento: hipótese não "
          "confirmada é que ali entra strOcorrenciaCancelamento em vez do "
          "código numérico"),
    Campo("data_entrada", 459, 8, "data", 65.5,
          "a data em que o título entrou no cartório. 65,5% contra "
          "dtmE_Cartorio em 443 registros — e o que fecha a identificação "
          "não é essa taxa, é a ORDEM: cruzando com as remessas que "
          "trouxeram os mesmos títulos, esta data nunca é ANTERIOR à data "
          "da remessa (253 no mesmo dia, 354 de 362 dentro de sete dias, e "
          "as três exceções são títulos reapresentados). Some-se a posição, "
          "colada ao protocolo. Os 34,5% que divergem de dtmE_Cartorio são "
          "esperados: o E-Ofício deixava editar aquela data depois"),
    Campo("reservado_467", 467, 10, "texto", None,
          "A CUSTA DO CARTÓRIO NA RETIRADA, em centavos, na ocorrência «3». "
          "FECHADO EM 30/10/2026 pela recusa da CRA: o retorno com «3» e este "
          "campo zerado voltou com o código 2239 «FALTOU INFORMAR AS CUSTAS "
          "DO CARTÓRIO/DISTRIBUIDOR». Medido: a conta tem 4 FOLHAS de "
          "arquivamento (`protesto_retorno.FOLHAS_DA_RETIRADA_NO_RETORNO`), e "
          "fecha os dois valores reais da «3» em 2026: 75,89 + 35,85 = 111,74 "
          "e 75,89 + 56,32 (17.4.5) = 132,21. Título de R$ 418,17 na vigência "
          "10022 dá R$ 111,74. O arquivo de emolumentos da CENPROT continua "
          "com 5 folhas. Quem preenche é "
          "`protesto_retorno.montar`, e só na «3»; sem faixa ou com a tabela "
          "incompleta ele recusa, e nunca manda zero. AS OUTRAS OCORRÊNCIAS "
          "SEGUEM EM ZERO: é o que o E-Ofício escreveu em 416 dos 443 e o que "
          "a Central aceita em 57 dos 64 retornos de 2026. O que ficou do "
          "histórico: os 27 não-zero dos 443 e os 7 dos 64 se agrupam pela "
          "ocorrência — «A» R$ 230–250 e R$ 53,58, «3» R$ 68–134, «C» "
          "R$ 1.170,71 (4 vezes). «A» e «C» continuam sem "
          "explicação: nenhum item de `cx_servicos` tem esses totais, e a "
          "busca nas colunas `cur*` de tbAvisoProtesto explicou só 2 dos 27"),
    Campo("separador_477", 477, 1, "texto", None, "sempre branco nos 443"),
    Campo("data_ocorrencia", 478, 8, "data", 95.6, "contra dtmOcorrencia"),
    Campo("reservado_486", 486, 2, "texto", None,
          "constante «00» em 442 dos 443, de 2022 a 2026 — preenchimento "
          "fixo. Na remessa esta mesma posição é separador, com dois espaços"),
    Campo("devedor_bairro", 488, 20, "texto", None,
          "vem em branco no retorno — que não repete os dados do devedor. "
          "É a mesma posição do bairro na remessa, onde vem preenchido"),
    Campo("reservado_508", 508, 38, "texto", None, "branco nos 443"),
    Campo("reservado_546", 546, 20, "texto", None, "branco nos 443"),
    Campo("reservado_566", 566, 1, "texto", None,
          "«A» em 173, «P» em 140, branco em 130. É campo DO ARQUIVO e não "
          "do registro: constante em todos os 194 arquivos medidos, sem uma "
          "única exceção. O branco casa com título pago ou arquivado (76 dos "
          "130 têm selo de arquivamento; a maioria tem strTipoPG); «A» e «P» "
          "casam com título protestado e sem arquivamento (287 de 313). O "
          "que separa «A» de «P» não é atributo de título nenhum — testei "
          "todas as 176 colunas de tbAvisoProtesto, e a melhor explicou 60% "
          "contra 42% de linha de base. Fica como marca de arquivo"),
    Campo("reservado_567", 567, 1, "texto", None, "separador, branco nos 443"),
    Campo("reservado_568", 568, 10, "texto", None,
          "constante zero nos 443, de 2022 a 2026 — preenchimento fixo"),
    Campo("reservado_578", 578, 19, "texto", None, "branco nos 443"),
    Campo("sequencial", 597, 4, "numero", 100.0),
)


# ------------------------------------- a confirmacao e o andamento
#
# MEDIDO em 24/08/2026, em 371 registros de confirmacao e 105 de andamento.
#
# Estes dois NAO tem layout proprio: sao o layout da REMESSA — com cedente,
# devedor, endereco, especie, tudo preenchido — mais o bloco 446–485 do
# RETORNO, que traz protocolo, ocorrencia e as datas. Faz sentido: eles
# devolvem ao apresentante o titulo que ele mandou, dizendo o que a casa fez
# com ele.
#
# A prova: lidos com o layout da remessa, a especie de TODOS os 476 registros
# confere com o acervo, casando por numero do titulo — 105/105 e 371/371.
#
# O layout se COMPOE em vez de ser transcrito, para nao divergir: qualquer
# correcao futura na remessa ou no bloco do retorno chega aqui sozinha.


def _compor(base: tuple[Campo, ...], substituir: str,
            por: tuple[Campo, ...]) -> tuple[Campo, ...]:
    """Troca um campo de `base` pelos campos de `por`, que o cobrem exato.

    Recusa a troca que nao cobre a mesma faixa de posicoes — layout com buraco
    ou sobreposicao le campo errado silenciosamente, e o teste de cobertura
    das 600 posicoes so pegaria depois.
    """
    alvo = next(c for c in base if c.nome == substituir)
    if not por or por[0].inicio != alvo.inicio or por[-1].fim != alvo.fim:
        raise ArquivoError(
            f"A composição não cobre {substituir} ({alvo.inicio}-{alvo.fim}).")
    return tuple(x for c in base for x in (por if c is alvo else (c,)))


# O bloco que o retorno acrescenta: de 446 a 485.
_BLOCO_DO_RETORNO: tuple[Campo, ...] = tuple(
    c for c in TITULO_NO_RETORNO if 446 <= c.inicio <= 485)

TITULO_NA_CONFIRMACAO: tuple[Campo, ...] = _compor(
    TITULO_NA_REMESSA, "reservado_446", _BLOCO_DO_RETORNO)

# Andamento tem a mesma forma. Nome proprio porque sao arquivos diferentes, e
# se um dia divergirem, divergem sem mexer no outro.
TITULO_NO_ANDAMENTO: tuple[Campo, ...] = TITULO_NA_CONFIRMACAO


# Qual layout usar para a linha de titulo (tipo_registro "1"), por tipo de
# arquivo. Os quatro tipos do catalogo estao medidos.
_CAMPOS_DO_TITULO: dict[str, tuple[Campo, ...]] = {
    "BFOSDTTPR": TITULO_NA_REMESSA,
    "SDTBFORTP": TITULO_NO_RETORNO,
    "SDTBFOCRT": TITULO_NA_CONFIRMACAO,
    "SDTBFOAND": TITULO_NO_ANDAMENTO,
}


CABECALHO: tuple[Campo, ...] = (
    Campo("tipo_registro", 1, 1, "texto", 100.0),
    Campo("codigo_do_apresentante", 2, 3, "texto", None),
    Campo("nome_do_apresentante", 5, 40, "texto", None),
    Campo("data_do_movimento", 45, 8, "data", None),
    Campo("tipo_do_arquivo", 53, 9, "texto", 100.0,
          "ORIGEM(3)+DESTINO(3)+TIPO(3) — é por aqui que se sabe o que o "
          "arquivo é, e não pela pasta em que ele está"),
    Campo("numero_da_remessa", 62, 6, "numero", None),
    Campo("reservado_68", 68, 22, "texto", None),
    Campo("codigo_do_portador", 90, 11, "texto", None),
    Campo("reservado_101", 101, 496, "texto", None, "brancos"),
    Campo("sequencial", 597, 4, "numero", 100.0, "sempre 0001"),
)


# O rodape da REMESSA (e da confirmacao) NAO conta titulos: conta REGISTROS —
# cabecalho + titulos + rodape. Num arquivo de um titulo ele diz 3.
#
# Isto estava errado, e o erro tinha consequencia: `quantidade_de_titulos` de 8
# digitos a partir de 53 lia 3.000 num arquivo de um titulo, e a conferencia
# acusava "arquivo truncado ou emendado" em 191 remessas boas. Alarme que soa
# sempre e alarme que ninguem ouve.
#
# Medido: 149 dos 191 (78%) batem com a contagem de registros. Nao e 100%, e
# por isso a conferencia so reclama quando o declarado e MAIOR que o achado —
# que e a assinatura de arquivo truncado. Declarado menor e emenda, e aparece
# pela linha de tipo estranho no meio.
RODAPE: tuple[Campo, ...] = (
    Campo("tipo_registro", 1, 1, "texto", 100.0),
    Campo("codigo_do_apresentante", 2, 3, "texto", None),
    Campo("nome_do_apresentante", 5, 40, "texto", None),
    Campo("data_do_movimento", 45, 8, "data", None),
    Campo("quantidade_de_registros", 53, 5, "numero", 78.0,
          "cabeçalho + títulos + rodapé, e não a quantidade de títulos — "
          "medido em 191 remessas e 179 confirmações"),
    Campo("reservado_58", 58, 3, "texto", None),
    Campo("soma_dos_valores", 61, 15, "centavos", 100.0,
          "confere nos 191 e nos 179"),
    Campo("reservado_76", 76, 521, "texto", None),
    Campo("sequencial", 597, 4, "numero", None),
)


# O rodape do RETORNO nao e o mesmo: `quantidade_de_titulos` de 8 digitos
# sempre le "1000" — nao a quantidade real. Medido em 194 arquivos reais de
# SDTBFORTP: o campo certo tem 4 digitos, nao 8; `soma_dos_valores` continua
# na mesma posicao (96,9% de acerto nos dois).
RODAPE_RETORNO: tuple[Campo, ...] = (
    Campo("tipo_registro", 1, 1, "texto", 100.0),
    Campo("codigo_do_apresentante", 2, 3, "texto", None),
    Campo("nome_do_apresentante", 5, 40, "texto", None),
    Campo("data_do_movimento", 45, 8, "data", None),
    Campo("quantidade_de_titulos", 53, 5, "numero", 100.0,
          "confere nos 188 arquivos de retorno de um lote só. Aqui é a "
          "quantidade de TÍTULOS, ao contrário da remessa, que conta "
          "registros — e lido com a largura da remessa (8 dígitos) dava "
          "sempre «1000»"),
    Campo("reservado_58", 58, 3, "texto", None,
          "entre a quantidade e a soma — não identificado no retorno"),
    Campo("soma_dos_valores", 61, 15, "centavos", 96.9,
          "medido em 194 arquivos reais"),
    Campo("reservado_76", 76, 521, "texto", None),
    Campo("sequencial", 597, 4, "numero", None),
)

# So o rodape do retorno foi medido separado. Os outros tipos usam o mesmo
# rodape da remessa ate serem medidos — nao adivinhados.
_CAMPOS_DO_RODAPE: dict[str, tuple[Campo, ...]] = {
    "SDTBFORTP": RODAPE_RETORNO,
    # O andamento conta titulos como o retorno (2 de 2 nos arquivos medidos),
    # e nao registros como a remessa.
    "SDTBFOAND": RODAPE_RETORNO,
}


# --------------------------------------------------------------- conversoes


def _texto(bruto: str) -> str:
    return bruto.strip()


def _numero(bruto: str) -> int | None:
    limpo = bruto.strip().lstrip("0")
    return int(limpo) if limpo.isdigit() else (0 if bruto.strip("0 ") == "" and
                                               bruto.strip() else None)


def _centavos(bruto: str) -> int | None:
    limpo = bruto.strip()
    return int(limpo) if limpo.isdigit() else None


SEM_VENCIMENTO = "99999999"


def _data(bruto: str) -> str | None:
    """`05092022` -> `2022-09-05`. `99999999` e a marca de sem vencimento.

    Devolve None em vez de levantar quando a data nao presta: um titulo com
    data torta nao pode derrubar a leitura dos outros mil do arquivo. A falta
    aparece na conferencia, com o numero do titulo do lado.
    """
    bruto = bruto.strip()
    if not bruto or bruto == SEM_VENCIMENTO or set(bruto) <= {"0"}:
        return None
    if len(bruto) != 8 or not bruto.isdigit():
        return None
    d, m, a = bruto[:2], bruto[2:4], bruto[4:]
    if not ("01" <= d <= "31" and "01" <= m <= "12" and a >= "1900"):
        return None
    return f"{a}-{m}-{d}"


_CONVERSOR = {"texto": _texto, "numero": _numero, "data": _data,
              # Le igual a `data`; o que muda e a ESCRITA — ver
              # `_escrever_data_vencimento`.
              "data_vencimento": _data,
              "centavos": _centavos}


def _ler_registro(linha: str, campos: tuple[Campo, ...]) -> dict:
    saida: dict[str, Any] = {}
    for c in campos:
        saida[c.nome] = _CONVERSOR[c.tipo](_fatiar(linha, c))
    return saida


# ------------------------------------------------------------------- leitura


@dataclass
class Arquivo:
    """O arquivo lido: cabecalho, titulos, rodape e o que nao fechou."""

    tipo: str
    sentido: str
    nome_do_tipo: str
    cabecalho: dict
    titulos: list[dict] = field(default_factory=list)
    rodape: dict = field(default_factory=dict)
    achados: list[str] = field(default_factory=list)

    @property
    def em_ordem(self) -> bool:
        return not self.achados


def ler(conteudo: str | bytes) -> Arquivo:
    """Le um arquivo de 600 posicoes. Nao grava nada.

    Aceita bytes, porque o arquivo vem em latin-1 e nao em UTF-8 — e ler como
    UTF-8 estoura no primeiro nome com cedilha. Ja estourou.
    """
    if isinstance(conteudo, bytes):
        conteudo = conteudo.decode("latin-1")
    linhas = [x for x in conteudo.replace("\r\n", "\n").replace("\r", "\n")
              .split("\n") if x.strip()]
    if not linhas:
        raise ArquivoError("O arquivo está vazio.")
    fora = [i + 1 for i, x in enumerate(linhas) if len(x) != TAMANHO_DO_REGISTRO]
    if fora:
        raise ArquivoError(
            f"O arquivo da CRA tem registros de {TAMANHO_DO_REGISTRO} "
            f"caracteres. A linha {fora[0]} tem {len(linhas[fora[0] - 1])}. "
            f"({len(fora)} linha(s) fora do tamanho.)")
    if linhas[0][0] != "0":
        raise ArquivoError(
            "A primeira linha do arquivo não é o cabeçalho — ela teria de "
            "começar com «0».")
    if linhas[-1][0] != "9":
        raise ArquivoError(
            "A última linha do arquivo não é o rodapé — ela teria de começar "
            "com «9».")

    cabecalho = _ler_registro(linhas[0], CABECALHO)
    tipo = cabecalho["tipo_do_arquivo"]
    conhecido = TIPOS.get(tipo, {})
    campos_do_rodape = _CAMPOS_DO_RODAPE.get(tipo, RODAPE)
    arquivo = Arquivo(
        tipo=tipo,
        sentido=conhecido.get("sentido", "DESCONHECIDO"),
        nome_do_tipo=conhecido.get("nome", f"tipo não catalogado ({tipo})"),
        cabecalho=cabecalho,
        rodape=_ler_registro(linhas[-1], campos_do_rodape))
    if not conhecido:
        arquivo.achados.append(
            f"O cabeçalho diz que o arquivo é do tipo «{tipo}», que não está "
            f"no catálogo. Os conhecidos são: {', '.join(sorted(TIPOS))}.")

    campos_do_titulo = _CAMPOS_DO_TITULO.get(tipo)
    avisou_layout_desconhecido = False
    for i, linha in enumerate(linhas[1:-1], start=2):
        if linha[0] != "1":
            arquivo.achados.append(
                f"A linha {i} começa com «{linha[0]}» — só o cabeçalho (0), o "
                f"título (1) e o rodapé (9) são previstos.")
            continue
        if campos_do_titulo is None:
            arquivo.titulos.append({"bruto": linha})
            if not avisou_layout_desconhecido:
                arquivo.achados.append(
                    f"O layout do registro de título para «{tipo}» ainda não "
                    f"foi medido — só {', '.join(sorted(_CAMPOS_DO_TITULO))} "
                    f"foram. Os títulos deste arquivo vieram como linha crua, "
                    f"em `bruto`.")
                avisou_layout_desconhecido = True
            continue
        arquivo.titulos.append(_ler_registro(linha, campos_do_titulo))

    arquivo.achados.extend(_conferir(arquivo))
    return arquivo


def _conferir(a: Arquivo) -> list[str]:
    """O que o proprio arquivo diz de si e nao bate. So calcula.

    O rodape declara quantos titulos e quanto somam. Conferir isso e o que
    pega arquivo truncado — que e o modo como um arquivo estraga na pratica,
    e nao com dado invalido no meio.
    """
    achados: list[str] = []
    # O rodape do RETORNO e do ANDAMENTO conta TITULOS, e confere exato nos
    # 190 arquivos medidos — logo, diferenca ali e defeito.
    declarados = a.rodape.get("quantidade_de_titulos")
    if declarados is not None and declarados != len(a.titulos):
        achados.append(
            f"O rodapé declara {declarados} título(s) e o arquivo traz "
            f"{len(a.titulos)}. Arquivo truncado ou emendado.")
    # O da REMESSA e da CONFIRMACAO conta REGISTROS, e so bate em 78%. Aqui
    # so se reclama quando o declarado e MAIOR que o achado, que e a
    # assinatura de arquivo truncado. Comparar por igualdade fazia a
    # conferencia gritar em 191 remessas boas, e alarme que soa sempre e
    # alarme que ninguem ouve.
    registros = a.rodape.get("quantidade_de_registros")
    if registros is not None:
        no_arquivo = len(a.titulos) + 2              # cabecalho e rodape
        if registros > no_arquivo:
            achados.append(
                f"O rodapé declara {registros} registro(s) e o arquivo traz "
                f"{no_arquivo}. Ou falta pedaço do arquivo, ou quem o gerou "
                f"contou de outro jeito — confira antes de processar.")
    soma = a.rodape.get("soma_dos_valores")
    if soma is not None:
        somado = sum(t.get("saldo_a_protestar") or 0 for t in a.titulos)
        if soma != somado:
            achados.append(
                f"O rodapé declara R$ {soma / 100:.2f} de saldo e os títulos "
                f"somam R$ {somado / 100:.2f}.")
    esperado = 1
    for t in a.titulos:
        esperado += 1
        if t.get("sequencial") not in (None, esperado):
            identificacao = t.get("numero_do_titulo") or t.get("nosso_numero")
            achados.append(
                f"O título {identificacao} está com o sequencial "
                f"{t.get('sequencial')} onde deveria estar {esperado}.")
            break
    return achados


# ---------------------------------------------------------- para o Protesto


def nome_de_apresentante(valor: Any) -> str:
    """O nome do apresentante gravado no título, ou vazio se aquilo não é nome.
    Só calcula.

    NÚMERO NÃO É NOME — 30/10/2026. As posições 005/019 do registro são a
    «Agência / Código do Cedente» do apresentante, e até esta data a leitura da
    remessa as gravava em `apresentante_nome`. Medido na produção: os 3 títulos
    que entraram por remessa neste sistema têm ali um número (11 ou 15 dígitos,
    e não o documento do cedente, que mora na posição 110). O dado antigo fica
    como está; quem mostra o nome pergunta aqui, e cai no cadastro.
    """
    texto = str(valor or "").strip()
    return texto if any(c.isalpha() for c in texto) else ""


def para_apontamento(titulo: dict) -> dict:
    """Traduz o registro do arquivo para o vocabulario do modulo de Protesto.

    E aqui que o arquivo vira ato. O que sai daqui vai para
    `protesto_cra.conferir_titulo`, que confere os codigos contra o esquema
    oficial, e so depois para o apontamento.
    """
    devedor = {
        "nome": titulo.get("devedor_nome"),
        **documento_do_devedor(titulo),
        "enderecos": [{
            "endereco": titulo.get("devedor_endereco"),
            "bairro": titulo.get("devedor_bairro"),
            "cep": titulo.get("devedor_cep"),
            "cidade": titulo.get("devedor_cidade"),
            "uf": titulo.get("devedor_uf"),
        }],
    }
    return {
        # QUEM APRESENTOU, que e para quem o retorno volta. Estava no registro
        # (posicoes 2 a 19) e nao vinha para o modulo de Protesto — e sem ele
        # `montar_retorno` nao sabe nem a letra da posicao 566.
        "apresentante_codigo": titulo.get("codigo_do_apresentante"),
        # AS POSIÇÕES 005/019 NÃO SÃO O NOME (30/10/2026): são a identificação
        # que o retorno devolve à CRA no mesmo lugar, e por isso ficam em
        # `cra_identificacao`. O nome vem do cabeçalho (`protesto_remessa`).
        "apresentante_nome": None,
        "cra_identificacao": titulo.get("identificacao_do_apresentante") or None,
        "especie": titulo.get("especie"),
        "numero_titulo": titulo.get("numero_do_titulo"),
        "nosso_numero": titulo.get("nosso_numero"),
        "data_emissao": titulo.get("data_de_emissao"),
        "data_vencimento": titulo.get("data_de_vencimento"),
        "tipo_moeda": "1",
        "valor": _reais(titulo.get("valor_do_titulo")),
        "saldo": _reais(titulo.get("saldo_a_protestar")),
        "praca_protesto": titulo.get("praca_de_protesto"),
        "tipo_endosso": (titulo.get("tipo_de_endosso") or None),
        "aceite": titulo.get("aceite"),
        "motivo_protesto": titulo.get("motivo_do_protesto"),
        "cedente": {
            "nome": titulo.get("cedente_nome"),
            "documento": titulo.get("cedente_documento"),
            "endereco": titulo.get("cedente_endereco"),
            "cep": titulo.get("cedente_cep"),
            "cidade": titulo.get("cedente_cidade"),
            "uf": titulo.get("cedente_uf"),
        },
        "devedores": [devedor],
    }


def documento_do_devedor(titulo: dict) -> dict:
    """`{"CNPJ": ...}` ou `{"CPF": ...}`, com o numero do tamanho certo.

    O campo tem 14 posicoes e vem com zeros a esquerda, entao o CPF chega como
    `00012345678901`. Cortar zero por zero seria errado nos dois sentidos: um
    CNPJ que comeca com zero — e ha muitos — perderia o primeiro digito, e um
    CPF ficaria com onze digitos so por sorte. O tipo, que vem no campo ao
    lado, e que diz quantos digitos o numero tem: 14 para CNPJ, 11 para CPF.
    """
    bruto = "".join(c for c in str(titulo.get("devedor_documento") or "")
                    if c.isdigit())
    e_cnpj = str(titulo.get("devedor_tipo_de_documento") or "") == "1"
    tamanho = 14 if e_cnpj else 11
    return {("CNPJ" if e_cnpj else "CPF"): bruto[-tamanho:].zfill(tamanho)
            if bruto else ""}


def _reais(centavos: int | None) -> str | None:
    if centavos is None:
        return None
    return f"{centavos // 100}.{centavos % 100:02d}"


def conferir_remessa(a: Arquivo) -> list[dict]:
    """Confere cada titulo do arquivo contra o contrato da CRA. So calcula.

    Devolve uma linha por titulo COM problema — e nao uma excecao no primeiro.
    Recusar o arquivo inteiro porque um titulo de mil veio torto e devolver ao
    banco mil titulos bons junto com o ruim.
    """
    problemas = []
    for i, t in enumerate(a.titulos, start=1):
        faltas = CRA.conferir_titulo(para_apontamento(t))
        if faltas:
            problemas.append({
                "posicao": i,
                "numero_do_titulo": t.get("numero_do_titulo"),
                "devedor": t.get("devedor_nome"),
                "faltas": faltas,
            })
    return problemas


def descrever_layout(campos: tuple[Campo, ...] = TITULO_NA_REMESSA) -> list[dict]:
    """O layout em forma de tabela, para a tela de conferencia e para o manual."""
    return [{"nome": c.nome, "inicio": c.inicio, "fim": c.fim,
             "tamanho": c.tamanho, "tipo": c.tipo,
             "conferido": c.conferido, "observacao": c.observacao}
            for c in campos]


# ------------------------------------------------------------------- escrita
#
# ESCREVER E O QUE FECHA O CICLO: o cartorio recebe a remessa, aponta, protesta
# ou da baixa, e devolve o retorno ao apresentante. Sem isto o modulo le e nao
# responde.
#
# COMO SE SABE QUE ESTA CERTO
#     Nao por conferir campo a campo — isso ja se fez na leitura. A prova aqui
#     e o IDA E VOLTA: ler um arquivo real e reescreve-lo, e o resultado tem de
#     sair identico byte a byte. Um arquivo que volta identico prova que a
#     escrita conhece cada posicao, cada regra de alinhamento e cada
#     preenchimento — inclusive os campos que ninguem identificou, porque eles
#     tambem tem de voltar como estavam.
#
#     E o teste que so existe porque ha 900 arquivos reais na maquina.


# ---------------------------------------- a marca do apresentante (pos. 566)
#
# A letra da posicao 566 e CONSTANTE dentro de cada arquivo, e nenhuma das 176
# colunas de `tbAvisoProtesto` a explica. O que a explica e o APRESENTANTE:
# medindo os 234 retornos dos dois lotes, 29 de 30 apresentantes usam sempre a
# MESMA letra.
#
# Conferido em dado que nao foi usado para descobrir: a tabela montada com o
# lote de 2022-23 acerta 11 de 11 no lote de 2026. No proprio lote de origem,
# 127 de 128.
#
# Isto e o que o oficial mandou fazer em 24/08/2026: na duvida, como o
# E-Oficio fazia, ou um padrao aceito antes. Cada linha abaixo e uma letra que
# a Central JA ACEITOU daquele apresentante.
#
# A tendencia que se ve, e que NAO viro regra porque tem excecao: banco e
# instituicao de credito levam «P»; conselho profissional, governo e comercio
# levam «A». O `FAA`, fundo de investimento com «A», quebra a leitura fácil —
# e e por isso que vale a tabela medida, e nao a teoria.

MARCA_POR_APRESENTANTE: dict[str, str] = {
    "001": "P",   # 12x — BANCO DO BRASIL
    "033": "P",   #  3x — BANCO SANTANDER
    "1IN": "A",   # 16x — PJA PROTESTO E COBRANÇA
    "1LV": "P",   # 31x — EQUATORIAL MARANHÃO DISTRIBUIDORA
    "1MF": "A",   #  7x — CRF-MA CONSELHO REGIONAL DE FARMÁCIA
    "1PE": "A",   #  5x — FINCH BRASIL SOLUÇÕES INTEGRADAS
    "1QY": "A",   #  2x
    "1VK": "P",   #  1x — WIP SOCIEDADE DE CRÉDITO DIRETO
    "237": "P",   # 11x — BRADESCO SA
    "2JW": "A",   #  2x — CRM/MA CONSELHO REGIONAL DE MEDICINA
    "2RB": "P",   #  1x — GVC GERAÇÃO DE VALOR EM COBRANÇA
    "341": "P",   #  6x — BANCO ITAU S/A
    "3HU": "A",   #  4x — FINCH BRASIL SOLUÇÕES INTEGRADAS
    "3SR": "A",   #  1x — CRM/MA CONSELHO REGIONAL DE MEDICINA
    "748": "P",   #  1x — BANCO SICREDI
    "901": "A",   #  6x — PGFN, Procuradoria-Geral da Fazenda Nacional
    "911": "A",   #  5x — PORTAL DE DOCUMENTOS
    "917": "A",   #  1x — BCR COMERCIO E INDUSTRIA S/A
    "935": "A",   #  1x — CREFITO-16
    "948": "A",   #  1x — MATEUS SUPERMERCADO S.A
    "949": "A",   #  8x — ARMAZÉM MATEUS S.A
    "987": "A",   #  3x — SEFAZ-MA
    "997": "A",   #  1x — GKSEG EPI MAQUINAS E EQUIPAMENTOS
    "ALJ": "A",   #  2x — CRBS S.A.
    "CSK": "P",   #  1x — SOLFACIL ENERGIA SOLAR
    "CXQ": "A",   #  2x — PROVI SOLUÇÕES E SERVIÇOS
    "DRG": "P",   #  2x — FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS
    "DWT": "P",   #  1x — SUPERSIM ANALISE DE DADOS
    "ENS": "P",   #  3x — GREEN SOLFÁCIL IV FUNDO DE INVESTIMENTO
                  #        (o único misto dos 30: «P» duas vezes, «A» uma)
    "FAA": "A",   #  1x — FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS
    "HDT": "P",   #  1x — IS GREEN SOLFACIL VI FUNDO DE INVESTIMENTO
    "TAB": "A",   #  6x
}


def marca_do_apresentante(codigo: str) -> str | None:
    """A letra que este apresentante ja aceitou, ou None se nao ha historico."""
    return MARCA_POR_APRESENTANTE.get(str(codigo or "").strip().upper())


def _escrever_texto(valor: Any, tamanho: int) -> str:
    """Texto: encostado a ESQUERDA, completado com espacos a direita."""
    return str("" if valor is None else valor)[:tamanho].ljust(tamanho)


def _escrever_numero(valor: Any, tamanho: int) -> str:
    """Numero: encostado a DIREITA, completado com ZEROS a esquerda."""
    if valor is None or valor == "":
        return "0" * tamanho
    return str(int(valor))[-tamanho:].zfill(tamanho)


def _escrever_data(valor: Any, tamanho: int) -> str:
    """`2022-09-05` -> `05092022`. Vazio vira zeros, como o arquivo faz."""
    texto = str(valor or "").strip()
    if not texto:
        return "0" * tamanho
    if len(texto) == 10 and texto[4] == "-":
        a, m, d = texto[:4], texto[5:7], texto[8:10]
        return f"{d}{m}{a}"[:tamanho].ljust(tamanho)
    return texto[:tamanho].ljust(tamanho)


def _escrever_data_vencimento(valor: Any, tamanho: int) -> str:
    """Sem vencimento sai como `99999999`, e nao como zeros.

    E convencao da CRA, medida: 44 titulos reais trazem `99999999` no
    vencimento. A leitura traduz isso para vazio — o que esta certo, porque
    nao ha data —, mas na volta o vazio tem de virar a marca outra vez. Zeros
    ali seriam uma data invalida onde o arquivo dizia "nao tem".

    Foi o teste de ida e volta que cobrou esta distincao: sem ela, 22 arquivos
    reais voltavam diferentes do que entraram.
    """
    texto = str(valor or "").strip()
    if not texto:
        return SEM_VENCIMENTO[:tamanho].ljust(tamanho)
    return _escrever_data(valor, tamanho)


_ESCRITOR = {"texto": _escrever_texto, "numero": _escrever_numero,
             "data": _escrever_data, "centavos": _escrever_numero,
             "data_vencimento": _escrever_data_vencimento}


def _escrever_registro(dados: dict, campos: tuple[Campo, ...]) -> str:
    """Monta uma linha de 600 posicoes a partir do dicionario lido.

    Campo que nao esta no dicionario sai como o vazio do seu tipo — brancos
    para texto, zeros para numero. Nunca sai linha de tamanho errado: a
    montagem e por posicao, e o tamanho e a soma dos campos.
    """
    partes = []
    for c in campos:
        if c.nome == "bruto":
            continue
        partes.append(_ESCRITOR[c.tipo](dados.get(c.nome), c.tamanho))
    linha = "".join(partes)
    if len(linha) != TAMANHO_DO_REGISTRO:
        raise ArquivoError(
            f"A linha montada tem {len(linha)} caracteres e não "
            f"{TAMANHO_DO_REGISTRO}. O layout usado não cobre o registro.")
    return linha


def escrever(arquivo: Arquivo, *, renumerar_sequencial: bool = False) -> str:
    """Monta o arquivo de 600 posicoes a partir da estrutura. Nao grava em disco.

    O tipo vem de `arquivo.tipo`, e e ele que escolhe o layout — o mesmo
    catalogo da leitura. Tipo sem layout medido e recusado: escrever com o
    layout de outro tipo produziria arquivo que a Central le errado, e a casa
    nao teria como saber.

    `renumerar_sequencial` recalcula o sequencial de cada linha (cabecalho
    0001, titulos a partir de 0002, rodape por ultimo). Fica DESLIGADO por
    padrao para o ida e volta poder provar a escrita sem que ela "conserte" o
    arquivo de origem pelo caminho — arquivo real com sequencial torto tem de
    voltar torto, senao o teste nao prova nada.

    Devolve texto. Quem grava escolhe a codificacao — e o arquivo da CRA e
    latin-1, nao UTF-8.
    """
    campos_titulo = _CAMPOS_DO_TITULO.get(arquivo.tipo)
    if campos_titulo is None:
        raise ArquivoError(
            f"Não sei escrever arquivo do tipo «{arquivo.tipo}»: o layout do "
            f"registro de título dele não foi medido. Os medidos são "
            f"{', '.join(sorted(_CAMPOS_DO_TITULO))}.")
    if any("bruto" in t for t in arquivo.titulos):
        raise ArquivoError(
            "Há título que só foi lido como linha crua. Escrever a partir "
            "dele mudaria o que não se sabe ler.")
    # Arquivo com mais de um LOTE emendado — cabeçalho, títulos e rodapé
    # repetidos no mesmo arquivo. São 12 dos 572 reais. A leitura já avisa
    # (a linha que começa com «0» ou «9» no meio vira achado), mas escrever
    # a partir dela produziria arquivo com os lotes de trás FALTANDO, e
    # calado. Recusar é o certo: quem quer reescrever um desses tem de
    # separar os lotes primeiro.
    emendado = [x for x in arquivo.achados
                if "só o cabeçalho (0), o" in x]
    if emendado:
        raise ArquivoError(
            "Este arquivo tem mais de um lote emendado — há cabeçalho ou "
            "rodapé no meio dele. Reescrevê-lo agora deixaria de fora os "
            "lotes seguintes. Separe os lotes antes. (" +
            emendado[0] + ")")

    campos_rodape = _CAMPOS_DO_RODAPE.get(arquivo.tipo, RODAPE)
    linhas = [_escrever_registro(arquivo.cabecalho, CABECALHO)]
    linhas += [_escrever_registro(t, campos_titulo) for t in arquivo.titulos]
    linhas.append(_escrever_registro(arquivo.rodape, campos_rodape))

    if renumerar_sequencial:
        for i, linha in enumerate(linhas, start=1):
            linhas[i - 1] = linha[:596] + f"{i:04d}"
    return "\r\n".join(linhas) + "\r\n"


def montar_andamento(*, apresentante_codigo: str, apresentante_nome: str,
                     dia: str, titulos: list[dict],
                     numero_da_remessa: Any = 1,
                     codigo_do_portador: str = "",
                     marca: str | None = None) -> Arquivo:
    """Monta o ANDAMENTO — o irmao do retorno, que vai junto com ele.

    E REGRA DA CASA, e nao deducao do layout: o oficial trouxe o roteiro do
    protesto da serventia em que trabalhou, e ele diz, em letra maiuscula,
    "SEMPRE QUE GERAR RETORNO (FINAL), GERAR ANDAMENTO". Quem faz protesto
    todo dia sabe que os dois andam em par; o layout sozinho nao contava isso.

    O ANDAMENTO NAO TEM LAYOUT PROPRIO: e o da REMESSA — com cedente, devedor,
    endereco e especie preenchidos — mais o bloco 446-485 do retorno, que traz
    protocolo, ocorrencia e as datas. Medido em 105 registros de andamento e
    371 de confirmacao: lidos com o layout da remessa, a especie confere com o
    acervo em 476 de 476.

    Por isso ele leva MAIS dado que o retorno, e nao menos: o retorno devolve
    so a chave e o resultado; o andamento devolve o titulo inteiro.
    """
    return _montar_saida(
        tipo="SDTBFOAND", apresentante_codigo=apresentante_codigo,
        apresentante_nome=apresentante_nome, dia=dia, titulos=titulos,
        numero_da_remessa=numero_da_remessa,
        codigo_do_portador=codigo_do_portador, marca=marca)


def montar_confirmacao(*, apresentante_codigo: str, apresentante_nome: str,
                       dia: str, titulos: list[dict],
                       numero_da_remessa: Any = 1,
                       codigo_do_portador: str = "",
                       marca: str | None = None) -> Arquivo:
    """Monta a CONFIRMACAO do recebimento da remessa.

    No roteiro do oficial ela e do MEIO-DIA, junto com o recebimento da
    remessa: "recebimento de remessa, confirmacao e emissao do aviso". E o
    recibo do que chegou.

    Mesma forma do andamento: remessa mais o bloco do retorno.
    """
    return _montar_saida(
        tipo="SDTBFOCRT", apresentante_codigo=apresentante_codigo,
        apresentante_nome=apresentante_nome, dia=dia, titulos=titulos,
        numero_da_remessa=numero_da_remessa,
        codigo_do_portador=codigo_do_portador, marca=marca)


def _montar_saida(*, tipo: str, apresentante_codigo: str,
                  apresentante_nome: str, dia: str, titulos: list[dict],
                  numero_da_remessa: Any = 1, codigo_do_portador: str = "",
                  marca: str | None = None) -> Arquivo:
    """O que os tres arquivos de saida tem em comum: cabecalho, rodape e as
    constantes do bloco do retorno.

    Escrever tres vezes daria tres versoes divergentes do rodape — e foi
    justamente o rodape que ja enganou uma medicao inteira, contando registros
    onde devia contar titulos.
    """
    # A LETRA DA 566 E DO RETORNO, E SO DELE — medido em 25/08/2026, quando a
    # tela da remessa a pediu para confirmar um recebimento e nao devia.
    #
    # `reservado_566` existe no layout do RETORNO e em mais nenhum: na
    # confirmacao e no andamento aquela posicao cai dentro de
    # `reservado_546` (546-596), que veio "zeros e brancos nos 343" registros
    # medidos. Exigir a letra para montar uma confirmacao seria travar o
    # recebimento da remessa de um apresentante NOVO por causa de um campo que
    # nem chega a ser escrito — e apresentante novo e justamente quem nunca
    # teve retorno para imitar.
    precisa_da_marca = any(c.nome == "reservado_566"
                           for c in _CAMPOS_DO_TITULO.get(tipo, ()))
    if marca is None:
        marca = marca_do_apresentante(apresentante_codigo)
    if marca is None and precisa_da_marca:
        raise ArquivoError(
            f"Não sei que letra usar na posição 566 para o apresentante "
            f"{apresentante_codigo!r}: não há retorno anterior dele nesta "
            f"casa para imitar, e nos arquivos medidos a divisão é exata — "
            f"metade usa «A» e metade usa «P». Confira num retorno recente "
            f"que a Central aceitou deste apresentante e informe a letra.")
    marca = str(marca or "").strip().upper()[:1]

    for i, t in enumerate(titulos, start=1):
        t.setdefault("tipo_registro", "1")
        t.setdefault("sequencial", i + 1)
        # Os campos que a medicao mostrou serem preenchimento FIXO, e nao
        # dado: 486 traz "00" e 568 traz zeros em 443 registros de quatro anos.
        t.setdefault("reservado_486", "00")
        t.setdefault("reservado_446", "01")
        # `467` sai zero, que e o que o E-Oficio escreveu em 416 dos 443. A
        # ocorrencia «3» chega aqui com a custa da retirada ja preenchida
        # (`protesto_retorno.montar`): a CRA recusa o zero dela com 2239.
        t.setdefault("reservado_467", "0" * 10)
        t.setdefault("reservado_566", marca)
    soma = sum(int(t.get("saldo_a_protestar") or 0) for t in titulos)
    return Arquivo(
        tipo=tipo,
        sentido=TIPOS[tipo]["sentido"],
        nome_do_tipo=TIPOS[tipo]["nome"],
        cabecalho={
            "tipo_registro": "0",
            "codigo_do_apresentante": apresentante_codigo,
            "nome_do_apresentante": apresentante_nome,
            "data_do_movimento": dia,
            "tipo_do_arquivo": tipo,
            "numero_da_remessa": numero_da_remessa,
            "codigo_do_portador": codigo_do_portador,
            "sequencial": 1,
        },
        titulos=list(titulos),
        rodape={
            "tipo_registro": "9",
            "codigo_do_apresentante": apresentante_codigo,
            "nome_do_apresentante": apresentante_nome,
            "data_do_movimento": dia,
            "quantidade_de_titulos": len(titulos),
            "soma_dos_valores": soma,
            "sequencial": len(titulos) + 2,
        })


def montar_retorno(*, apresentante_codigo: str, apresentante_nome: str,
                   dia: str, titulos: list[dict],
                   numero_da_remessa: Any = 1,
                   codigo_do_portador: str = "",
                   marca: str | None = None) -> Arquivo:
    """Monta a estrutura de um retorno novo, para `escrever()`. Nao grava.

    `titulos` sao dicionarios no vocabulario de `TITULO_NO_RETORNO` — o mesmo
    que a leitura devolve, para que o que se le e o que se escreve nao
    divirjam.

    O rodape se calcula do que foi passado: a quantidade e a soma dos saldos.
    Foi conferir isso que pegou o rodape de 8 digitos que lia sempre 1000.

    `marca` e a letra da posicao 566. Em branco, sai a que este apresentante
    ja aceitou (`MARCA_POR_APRESENTANTE`) — a regra do oficial: na duvida,
    como o E-Oficio fazia. Apresentante SEM historico e recusado, porque ali
    nao ha o que imitar: dos 148 arquivos medidos, 74 levam «A» e 74 levam
    «P». Chutar num empate desses seria inventar, e inventar e o que este
    modulo nao faz.
    """
    return _montar_saida(
        tipo="SDTBFORTP", apresentante_codigo=apresentante_codigo,
        apresentante_nome=apresentante_nome, dia=dia, titulos=titulos,
        numero_da_remessa=numero_da_remessa,
        codigo_do_portador=codigo_do_portador, marca=marca)
