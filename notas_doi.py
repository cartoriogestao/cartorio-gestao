"""
Declaracao sobre Operacoes Imobiliarias — a DOI da Receita Federal.

POR QUE ESTE MODULO EXISTE, E COM PRESSA
    O relatorio de inspecao aponta a DOI de 2026 como pendencia CRITICA no
    AUDITUS, com prazo de quinze dias: "Anexar comprovacoes de DOI ou
    declaracoes negativas dos meses sem atos imobiliarios."

DE ONDE VEIO A REGRA
    Do manual oficial de preenchimento da Receita Federal, lido em 15/08/2026:
    https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/manuais/doi/doi-preenchimento.pdf
    e da IN RFB 1.112/2010, com o art. 8º da Lei 10.426/2002. O Codigo de
    Normas do TJMA manda comunicar no art. 797.

    Os dominios (tipo de operacao, tipo de imovel, natureza do titulo) vieram
    do E-Oficio e FORAM CONFERIDOS contra as listas do manual: batem item a
    item. Duas fontes independentes concordando e melhor do que uma.

AS REGRAS QUE MUDAM O DESENHO
    UMA DECLARACAO PARA CADA IMOVEL. Nao uma por ato. Alienando-se uma
    coletividade de imoveis em escritura unica, sai uma DOI por unidade; na
    PERMUTA, uma para cada imovel permutado. E por isso que este modulo
    devolve uma LISTA de declaracoes a partir de um ato, e nao uma so.

    PRAZO: ate as 23h59min59s do ULTIMO DIA UTIL DO MES SUBSEQUENTE ao da
    lavratura, anotacao, matricula, registro ou averbacao. Perdido o prazo,
    incide a Multa por Atraso na Entrega de Declaracao (MAED).

    A SOMA DAS PARTICIPACOES nao pode ser inferior a 99,00% nem superior a
    100,00%. E validacao da propria Receita, e barra o arquivo.

    PERCENTUAL DE PROPRIEDADE NO IMOVEL NAO E PERCENTUAL DE PARTICIPACAO NA
    OPERACAO. O manual repete isso tres vezes, em negrito, e os quatro
    exemplos que ele traz existem so para explicar a diferenca. Aqui os dois
    sao campos separados, de proposito.

    AREA URBANA EM METROS QUADRADOS, AREA RURAL EM HECTARES. Misturar as duas
    e erro que passa despercebido porque o numero continua "parecendo certo".

O QUE ESTE MODULO NAO FAZ, PORQUE JA ESTAVA FEITO
    Nao monta o registro nem carrega tabela de dominio. Isso e do `ri_ctp`.

    A primeira versao deste arquivo reimplementou as duas coisas, e errou nas
    duas: descreveu a operacao 19 como "Doacao em Pagamento" — que e o que
    esta gravado no E-Oficio, e esta errado; a Receita chama de DACAO em
    pagamento, que e outro instituto — e inventou codigos simbolicos para a
    forma de pagamento quando os oficiais sao numericos ("5", "7", "9", "10",
    "11"). Pior: batizou os campos do arquivo com os nomes das FICHAS DA TELA
    do manual, e nao com os do layout.

    O `ri_ctp` nao tem nenhum desses defeitos porque foi escrito a partir da
    especificacao publicada. E a CTP usa o MESMO FORMATO DE ARQUIVO da DOI-Web
    — quem diz e o proprio CNB: "Para facilitar a informacao dos dados na CTP
    pelos notarios, foi utilizado o mesmo formato de arquivo previsto na
    DOIWEB da Receita Federal."

    De novo a mesma licao do projeto: eu tinha a ferramenta e improvisei outra.

O QUE E DAQUI, E SO DAQUI
    O que a DOI tem e a CTP nao: o prazo do ultimo dia UTIL, o numero de
    controle, a regra de UMA DECLARACAO POR IMOVEL, a retificadora, a
    canceladora, a declaracao NEGATIVA dos meses sem ato — e as conferencias
    que a Receita faz e recusa o arquivo.

DINHEIRO
    Em centavos inteiros, como no resto do sistema.
"""
from __future__ import annotations

import calendar
import json
import re
import unicodedata
from datetime import date
from typing import Any

from notas_partes import documento_valido, so_digitos
# O layout e as tabelas de dominio vem do ri_ctp, que os tirou da
# especificacao publicada. Uma fonte so, para nao divergirem.
from ri_ctp import (FORMA_PAGAMENTO, TIPO_IMOVEL, TIPO_OPERACAO,
                    montar_registro)

# --------------------------------------------------------------- dominios

# Operacoes que a Receita DESATIVOU, com o que as substituiu.
#
# O `ri_ctp` deixa as desativadas de fora, e faz certo: oferecer na tela um
# codigo recusado so gera retrabalho. Aqui elas precisam existir, porque o
# acervo importado do E-Oficio TEM atos gravados com elas — sem esta tabela o
# sistema nao saberia dizer por que aquele ato antigo nao pode ser redeclarado.
OPERACOES_DESATIVADAS = {
    25: ("Desapropriação", "63 (reforma agrária) ou 64 (as demais)"),
    27: ("Herança, Legado ou Meação (adjudicação)", "69 (inventário)"),
    43: ("Dissolução de Sociedade", "58 (cisão total ou parcial)"),
    49: ("Partilha amigável ou litigiosa",
         "70 (partilha por separação, divórcio ou união estável)"),
    51: ("Retorno de Capital próprio", "71 ou 72"),
    53: ("Doação", "55 (adiantamento de legítima) ou 67 (as demais)"),
}

TIPOS_DECLARACAO = {
    "ORIGINAL": "Original",
    "RETIFICADORA": "Retificadora",
    "CANCELADORA": "Canceladora",
    # A negativa nao e um tipo do layout: e a AUSENCIA de carga no mes, provada
    # pelo fechamento negativo na tela. Fica aqui porque e o que a inspecao
    # cobra no AUDITUS, e o sistema precisa saber que o mes foi resolvido.
    "NEGATIVA": "Negativa — mês sem ato imobiliário",
}

# Operacoes em que o manual e explicito sobre uma declaracao por imovel, por
# serem as que mais costumam trazer varios imoveis no mesmo instrumento.
UMA_POR_IMOVEL_SEMPRE = (13, 69, 70, 45)   # permuta, inventario, partilha, loteamento

# O ENVELOPE DOI-Web FOI CONFERIDO contra o arquivo manual
# DOI_000000_202608_Livro30_fls184-192.json (Livro 30 fls 184-192 / DOI-Web):
# upload = {"declaracoes": [ ...registros... ]} — SEM cns/competencia/quantidade/
# numeroControle no JSON. O REGISTRO interno continua vindo do ri_ctp (mesmo
# layout de campos da especificacao CTP/DOI). numero_de_controle() permanece
# disponivel para UI/testes; nao entra no arquivo de carga DOI-Web.
ESQUEMA_CONFERIDO = True


# ----------------------------------------------------------------- prazo

def prazo_de_entrega(data_ato: str) -> str:
    """Ultimo dia util do mes subsequente ao do ato.

    O QUE ESTE CALCULO NAO SABE
        Feriado. Ele devolve o ultimo dia que nao e sabado nem domingo; se
        cair em feriado nacional, estadual ou municipal, o prazo e o dia util
        anterior. O sistema nao conhece o calendario de Cidade Exemplo, e
        inventar um seria pior do que nao ter: a tela avisa e quem confere e a
        serventia.
    """
    ano, mes = int(data_ato[0:4]), int(data_ato[5:7])
    ano_s, mes_s = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    dia = calendar.monthrange(ano_s, mes_s)[1]
    while date(ano_s, mes_s, dia).weekday() >= 5:      # 5 sabado, 6 domingo
        dia -= 1
    return f"{ano_s:04d}-{mes_s:02d}-{dia:02d}"


def numero_de_controle(sequencial: int, ano: int) -> str:
    """NNNNNNAA — seis digitos de sequencial e dois de ano.

    O manual diz que o numero e gerado pelo sistema, nao se repete na
    serventia e nao pode ser editado. Retificadora e canceladora NAO ganham
    numero novo: usam o da original.
    """
    return f"{int(sequencial):06d}{ano % 100:02d}"


# ------------------------------------------------------------- formatacao

def valor_doi(centavos: int | None) -> str | None:
    """Centavos inteiros -> "1234.56", sem passar por ponto flutuante."""
    if centavos is None:
        return None
    sinal = "-" if centavos < 0 else ""
    n = abs(int(centavos))
    return f"{sinal}{n // 100}.{n % 100:02d}"


def _texto(v: Any, limite: int | None = None) -> str | None:
    if v is None:
        return None
    s = " ".join(str(v).split())
    if limite:
        s = s[:limite]
    return s or None


def _numero(v: Any) -> float | None:
    """Aceita '1.234,56' e '1234.56'. Devolve None se nao for numero."""
    s = str(v or "").strip()
    if not s:
        return None
    s = re.sub(r"\.(?=\d{3}\b)", "", s).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def cib_valido(cib: Any) -> bool | None:
    """O CIB tem oito digitos, sendo o ultimo o verificador.

    Devolve None quando nao ha o que conferir — o manual admite imovel sem
    CIB, e nesse caso o campo vai vazio em vez de errado.
    """
    n = so_digitos(cib)
    if not n:
        return None
    return len(n) == 8


# ------------------------------------------------------------ conferencia

class Impedimento:
    """Um motivo pelo qual a declaracao nao pode ser entregue."""

    __slots__ = ("campo", "motivo")

    def __init__(self, campo: str, motivo: str):
        self.campo, self.motivo = campo, motivo

    def __repr__(self) -> str:                              # pragma: no cover
        return f"{self.campo}: {self.motivo}"

    def como_dict(self) -> dict:
        return {"campo": self.campo, "motivo": self.motivo}


def conferir_participacoes(partes: list[dict], papel: str) -> list[Impedimento]:
    """A soma tem de ficar entre 99,00% e 100,00%.

    E validacao da propria Receita, nao arredondamento nosso: fora dessa faixa
    o arquivo e recusado. A folga de um ponto existe porque a divisao de um
    imovel entre tres nao fecha em cem — 33,33 tres vezes da 99,99.
    """
    p: list[Impedimento] = []
    if not partes:
        p.append(Impedimento(papel, f"declaração sem nenhum {papel[:-1]}"))
        return p
    soma = 0.0
    for parte in partes:
        pct = _numero(parte.get("participacao"))
        if pct is None:
            p.append(Impedimento(f"{papel}.participacao",
                                 f"{parte.get('nome') or 'parte'} sem percentual "
                                 "de participação na operação"))
            continue
        soma += pct
    if p:
        return p
    if soma < 99.0 or soma > 100.0:
        p.append(Impedimento(f"{papel}.participacao",
                             f"a soma das participações é {soma:.2f}% — a Receita "
                             "só aceita entre 99,00% e 100,00%"))
    return p


# ------------------------------------------------- QUEM ALIENA E QUEM ADQUIRE
#
# Medido em 28/08/2026 nas 88 partes das 47 escrituras desta casa.
#
# A QUALIFICACAO E CAMPO LIVRE, e o balcao escreve como fala: `VENDEDOR(A)`,
# `VENDEDORA`, `Vendedor(a)`, `CEDENTE(S)`, `PROPRIETARIO(A)`, `DONATARIO(A)`,
# `HERDEIRO(A) CEDENTE`. Nao ha catalogo a consultar — ha o que esta escrito.
# `OUTORGANTE`/`OUTORGADO`, o par das procuracoes, aparece em 6 das 88.
#
# A ORDEM DAS REGRAS E O QUE IMPORTA, e o defeito estava a um passo:
# **«PROCURADOR DO VENDEDOR» CONTEM «VENDEDOR»**. Quem procurar o vendedor
# primeiro declara a Receita que o procurador vendeu o imovel — o CPF de quem
# so assinou por outro, numa transacao que ele nao fez, cruzado com a
# declaracao de imposto de renda dele. Por isso o descarte vem ANTES.
#
# E o descarte e seguro porque foi medido: em **7 das 8** escrituras com
# procurador ele aparece AO LADO de quem representa, e a parte de verdade
# entra. Na oitava nao ha vendedor nenhum na lista — e ali a escritura para,
# que e exatamente o que ela deve fazer.
NAO_E_PARTE_DO_NEGOCIO = (
    "PROCURADOR", "TESTEMUNHA", "REPRESENTANTE", "INTERPRETE",
    "ASSINA A ROGO", "ANUENTE", "INTERVENIENTE",
)

# As duas listas: primeiro as palavras MEDIDAS no acervo desta casa, depois a
# contraparte de cada uma — que e a palavra da propria Receita para o mesmo
# papel. Nao ha nenhuma aqui que eu tenha imaginado sozinho.
QUEM_ALIENA = ("VENDEDOR", "CEDENTE", "OUTORGANTE",                   # medidas
               "DOADOR", "TRANSMITENTE", "ALIENANTE")                 # contraparte
QUEM_ADQUIRE = ("COMPRADOR", "OUTORGADO", "DONATARIO",                # medidas
                "CESSIONARIO", "ADQUIRENTE")                          # contraparte

# QUATRO PALAVRAS FICARAM DE FORA DE PROPOSITO, e cada uma por um motivo:
#
#   `PROPRIETARIO` — eu a tinha posto entre quem aliena, e um ato desmente:
#   na escritura 222 ela aparece AO LADO de um `Vendedor(a)` e de dois
#   compradores. Se o proprietario fosse o vendedor, o vendedor nao estaria
#   ali. Nos outros tres atos em que aparece nao ha contraparte nenhuma, e
#   nenhum dos quatro resolve a pergunta. Proprietario e quem consta como dono
#   — nao e, por si, quem transferiu.
#
#   `PERMUTANTE` — na permuta cada um e as duas coisas ao mesmo tempo, e
#   escolher um lado por ele seria inventar metade da declaracao.
#
#   `HERDEIRO` — o acervo tem `HERDEIRO(A) CEDENTE`, que e quem CEDE. Se
#   `HERDEIRO` estivesse na lista de quem adquire, essa linha bateria nas duas
#   e o herdeiro que cedeu entraria como quem comprou. A palavra sozinha nao
#   diz o lado; `CEDENTE`, que esta ali do lado, diz.
#
#   `DECLARANTE` — nas duas linhas em que aparece o ato e dissolucao de uniao
#   estavel, onde quem transfere depende do que foi partilhado.
#
# As quatro caem em duvida, e duvida para a declaracao ate alguem responder.
#
# POR QUE ESTA FUNCAO NAO E A `ri_ctp._papel`, QUE RESPONDE A MESMA PERGUNTA
#   Porque as duas tabelas nao falam a mesma lingua. `ri_partes.papel` e
#   vocabulario controlado — medido: `proprietario` em 3.894 das 3.992 linhas,
#   `adquirente` em 1 —, e ali `proprietario` quer dizer «dono de registro»,
#   ao lado de `proprietario_ativo`. Aqui a qualificacao e campo livre e o
#   balcao escreve como fala, em 24 formas.
#
#   A MESMA PALAVRA NOS DOIS LUGARES NAO QUER DIZER A MESMA COISA, e juntar as
#   duas funcoes faria os 3.894 donos de registro do Registro de Imoveis
#   virarem alienantes de uma hora para outra. Ficam separadas de proposito, e
#   ha teste que guarda isso.


def _sem_acento_maiusculo(texto) -> str:
    """A forma em que as listas acima estao escritas.

    Nao e a `normalizar_nome` da casa nem quer ser: aquela devolve minusculas e
    serve para comparar NOMES entre tabelas. Esta compara com literais escritos
    logo acima, no mesmo arquivo — a igualdade que importa aqui e com eles.
    Copiar a outra por parecer «a mesma» ja custou um defeito neste projeto.
    """
    cru = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in cru if not unicodedata.combining(c)).upper()


def lado_da_parte(qualificacao) -> str:
    """ALIENANTE, ADQUIRENTE, FORA (nao e parte do negocio) ou DUVIDA."""
    q = _sem_acento_maiusculo(qualificacao)
    if not q.strip():
        return "DUVIDA"
    if any(x in q for x in NAO_E_PARTE_DO_NEGOCIO):
        return "FORA"
    aliena = any(x in q for x in QUEM_ALIENA)
    adquire = any(x in q for x in QUEM_ADQUIRE)
    if aliena and adquire:
        # BATER NOS DOIS LADOS NAO E EMPATE A DESEMPATAR POR ORDEM: e uma
        # qualificacao que o balcao escreveu e estas listas nao sabem ler.
        # Deixar a ordem decidir daria uma resposta com cara de certa.
        return "DUVIDA"
    return "ALIENANTE" if aliena else ("ADQUIRENTE" if adquire else "DUVIDA")


def lado_da_parte_no_ato(parte: dict) -> str:
    """O papel fiscal explícito prevalece só neste ato; o cadastro não muda."""
    lado = (parte.get("doi_lado") or "").strip().upper()
    return lado if lado in ("ALIENANTE", "ADQUIRENTE", "FORA") else lado_da_parte(
        parte.get("qualificacao"))


def lados_das_partes(partes: list[dict]) -> tuple[list, list, list]:
    """Separa as partes nos dois lados. Devolve (alienantes, adquirentes, duvidas).

    QUEM NAO SE CLASSIFICA VIRA DUVIDA, E DUVIDA PARA A DECLARACAO. O caminho
    facil seria mandar so quem se reconheceu e deixar o resto de fora — e a
    Receita ACEITARIA, porque o arquivo estaria bem formado. Declaracao aceita
    sem quem alienou e pior que declaracao recusada: a recusada volta.
    """
    alienantes, adquirentes, duvidas = [], [], []
    for parte in partes:
        onde = lado_da_parte_no_ato(parte)
        if onde == "ALIENANTE":
            alienantes.append(parte)
        elif onde == "ADQUIRENTE":
            adquirentes.append(parte)
        elif onde == "DUVIDA":
            duvidas.append(parte)
    return alienantes, adquirentes, duvidas


def participacoes_sugeridas(quantos: int) -> list[str]:
    """A divisao igual entre `quantos` do mesmo lado, uma por parte, em TEXTO.

    E SUGESTAO, E NAO CALCULO SILENCIOSO — decisao do oficial em 28/08/2026.
    Ela vai preenchida no campo da tela para o escrevente ver e corrigir; o que
    a Receita recebe e o que ficou GRAVADO, e nao o que esta funcao devolveu.

    O RESTO DA DIVISAO VAI NO PRIMEIRO, e nao se espalha. Tres pessoas dao
    33,33 tres vezes, que soma 99,99 e passa — a faixa da Receita comeca em
    99,00 justamente por causa disso. Mas SETE dao 14,28 sete vezes, que soma
    99,96, e o arredondamento sozinho nao garante a faixa em todo numero de
    partes. Somar o que falta ao primeiro fecha em 100,00 SEMPRE, e a Receita
    nao pergunta por que uma parte tem dois centesimos a mais que as outras.
    """
    if quantos <= 0:
        return []
    cada = round(100.0 / quantos, 2)
    primeiro = 100.0 - cada * (quantos - 1)
    return [f"{v:.2f}".replace(".", ",")
            for v in [primeiro] + [cada] * (quantos - 1)]


def conferir_declaracao(dec: dict) -> list[Impedimento]:
    """Confere uma declaracao contra o manual. Lista vazia = pode ir."""
    p: list[Impedimento] = []

    operacao = dec.get("operacao")
    if operacao is None:
        p.append(Impedimento("operacao", "sem o tipo de operação imobiliária"))
    elif int(operacao) in OPERACOES_DESATIVADAS:
        nome, troca = OPERACOES_DESATIVADAS[int(operacao)]
        p.append(Impedimento(
            "operacao",
            f"a operação {operacao} — {nome} — foi desativada pela Receita; "
            f"o código de hoje é {troca}"))
    elif str(operacao) not in TIPO_OPERACAO:
        p.append(Impedimento("operacao",
                             f"operação {operacao} não existe na tabela da Receita"))

    if not dec.get("data_ato"):
        p.append(Impedimento("data_ato", "sem a data do ato"))


    if dec.get("valor_operacao") is None:
        p.append(Impedimento("valor_operacao", "sem o valor da operação"))
    if dec.get("valor_base_calculo") is None:
        p.append(Impedimento("valor_base_calculo",
                             "sem o valor da base de cálculo do ITBI ou do ITCMD"))

    forma = dec.get("forma_pagamento")
    if forma and str(forma) not in FORMA_PAGAMENTO:
        p.append(Impedimento(
            "forma_pagamento",
            f"forma de pagamento {forma!r} fora da tabela — os códigos são "
            + ", ".join(f"{k} ({v})" for k, v in FORMA_PAGAMENTO.items())))

    # ---- o imovel
    imovel = dec.get("imovel") or {}
    if not imovel:
        p.append(Impedimento("imovel", "declaração sem imóvel"))
        return p + conferir_participacoes(dec.get("alienantes") or [], "alienantes") \
                 + conferir_participacoes(dec.get("adquirentes") or [], "adquirentes")

    if cib_valido(imovel.get("cib")) is False:
        p.append(Impedimento("imovel.cib", "o CIB tem oito dígitos"))

    rural = bool(imovel.get("rural"))
    if rural:
        if not _texto(imovel.get("denominacao")):
            p.append(Impedimento("imovel.denominacao",
                                 "imóvel rural sem denominação"))
        if not _texto(imovel.get("localizacao")):
            p.append(Impedimento("imovel.localizacao",
                                 "imóvel rural sem localização"))
        if _numero(imovel.get("area_hectares")) is None:
            p.append(Impedimento("imovel.area_hectares",
                                 "imóvel rural: a área vai em HECTARES, e está vazia"))
        if imovel.get("area_terreno") or imovel.get("area_construida"):
            p.append(Impedimento("imovel.area",
                                 "imóvel rural com área preenchida em metros "
                                 "quadrados — a Receita pede hectares"))
    else:
        if _numero(imovel.get("area_terreno")) is None:
            p.append(Impedimento("imovel.area_terreno",
                                 "imóvel urbano: a área do terreno vai em METROS "
                                 "QUADRADOS, e está vazia"))
        if imovel.get("area_hectares"):
            p.append(Impedimento("imovel.area",
                                 "imóvel urbano com área em hectares — a Receita "
                                 "pede metros quadrados"))
        if imovel.get("tipo") and str(imovel["tipo"]) not in TIPO_IMOVEL:
            p.append(Impedimento("imovel.tipo",
                                 f"tipo de imóvel {imovel['tipo']} fora da tabela"))
        if not _texto(imovel.get("logradouro")):
            p.append(Impedimento("imovel.logradouro", "imóvel urbano sem logradouro"))

    if not so_digitos(imovel.get("matricula")) and not _texto(imovel.get("transcricao")):
        p.append(Impedimento("imovel.matricula",
                             "imóvel sem matrícula nem transcrição"))

    # ---- as partes
    for papel in ("alienantes", "adquirentes"):
        partes = dec.get(papel) or []
        p += conferir_participacoes(partes, papel)
        for parte in partes:
            doc = so_digitos(parte.get("documento"))
            if not doc and not parte.get("sem_documento"):
                p.append(Impedimento(f"{papel}.documento",
                                     f"{parte.get('nome') or 'parte'} sem CPF ou CNPJ"))
            elif doc and documento_valido(doc) is False:
                p.append(Impedimento(f"{papel}.documento",
                                     f"documento de {parte.get('nome')} não passa "
                                     "no dígito verificador"))
            if not _texto(parte.get("nome")):
                p.append(Impedimento(f"{papel}.nome", "parte sem nome"))
    return p


# ----------------------------------------------------------------- montagem

def declaracoes_do_ato(ato: dict, imoveis: list[dict], alienantes: list[dict],
                       adquirentes: list[dict]) -> list[dict]:
    """De um ato saem TANTAS DECLARACOES QUANTOS FOREM OS IMOVEIS.

    E a regra do manual, e nao uma escolha de desenho: "Deve ser enviada uma
    declaracao para cada imovel alienado ou adquirido. Nas alienacoes de uma
    coletividade de imoveis em escritura unica, preencher a DOI para cada
    unidade. Na Permuta preencher uma declaracao para cada imovel permutado."

    Na permuta, quem aliena um imovel adquire o outro: por isso os papeis vem
    de cada imovel, e nao do ato. Quem montar isso do ato para baixo troca os
    lados na segunda declaracao e nao percebe.
    """
    saida = []
    for imovel in imoveis:
        saida.append({
            "operacao": imovel.get("operacao") or ato.get("doi_transacao"),
            "natureza_titulo": ato.get("doi_natureza_titulo", 2),  # escritura publica
            "data_ato": (ato.get("data") or "")[:10],
            "livro": _texto(ato.get("livro"), 8),
            "folha": _texto(ato.get("folha"), 6),
            "mne": _texto(ato.get("mne")),
            "valor_operacao": imovel.get("valor_operacao"),
            "valor_base_calculo": imovel.get("valor_base_calculo")
            or ato.get("base_itbi"),
            "parte_transacionada": imovel.get("parte_transacionada"),
            "houve_permuta": bool(imovel.get("houve_permuta")),
            "houve_pagamento_dinheiro": bool(imovel.get("houve_pagamento_dinheiro")),
            "valor_especie": imovel.get("valor_especie"),
            "forma_pagamento": imovel.get("forma_pagamento"),
            "houve_alienacao_fiduciaria": bool(imovel.get("houve_alienacao_fiduciaria")),
            "imovel": imovel,
            "alienantes": imovel.get("alienantes") or alienantes,
            "adquirentes": imovel.get("adquirentes") or adquirentes,
            "ato_id": ato.get("id"),
        })
    return saida


def declarar(dec: dict, cns: str, codigo_ibge: str,
             tipo_servico: str = "1", tipo_ato: str = "1") -> dict:
    """Monta o registro DELEGANDO ao ri_ctp, que tem o layout da especificacao.

    A CTP e a DOI usam o mesmo formato de arquivo — quem diz e o CNB. Manter
    dois montadores faria os dois divergirem no primeiro campo que mudasse, e
    o que divergisse seria descoberto por uma carga recusada.
    """
    imovel = dec.get("imovel") or {}
    ato = {"data_ato": dec.get("data_ato")}
    m = {
        "livro": dec.get("livro"), "folha": dec.get("folha"),
        "numero": imovel.get("matricula"), "cnm": imovel.get("cnm"),
        "rural_urbano": "RURAL" if imovel.get("rural") else "URBANO",
        "nirf": imovel.get("cib"), "incra": imovel.get("codigo_incra"),
        "ccir": imovel.get("ccir"),
        "logradouro": imovel.get("denominacao") if imovel.get("rural")
        else imovel.get("logradouro"),
        "bairro": imovel.get("bairro"),
        "numero_predial": imovel.get("numero"),
        "complemento_endereco": imovel.get("complemento_numero"),
        "cep": imovel.get("cep"),
        "inscricao_municipal": imovel.get("inscricao_municipal"),
        "area_valor": imovel.get("area_hectares") if imovel.get("rural")
        else imovel.get("area_terreno"),
    }
    dados = {
        "data_negocio": dec.get("data_negocio") or dec.get("data_ato"),
        "operacao": str(dec.get("operacao") or ""),
        "valor_operacao": _reais(dec.get("valor_operacao")),
        "valor_base_itbi": _reais(dec.get("valor_base_calculo")),
        "forma_pagamento": dec.get("forma_pagamento"),
        "permuta": dec.get("houve_permuta"),
        "pagamento_dinheiro": dec.get("houve_pagamento_dinheiro"),
        "valor_especie": _reais(dec.get("valor_especie")),
        "alienacao_fiduciaria": dec.get("houve_alienacao_fiduciaria"),
        "ultima_parcela": dec.get("mes_ano_ultima_parcela"),
        "valor_pago_ate_ato": _reais(dec.get("valor_pago_ate_ato")),
        "tipo_parte": dec.get("tipo_parte_transacionada") or "1",
        "valor_parte": dec.get("parte_transacionada"),
        "tipo_imovel": imovel.get("tipo"),
        "area_construida": imovel.get("area_construida"),
        "codigo_ibge": imovel.get("municipio_ibge") or codigo_ibge,
        "denominacao": imovel.get("denominacao"),
        "localizacao": imovel.get("localizacao"),
        "descricao_outras": dec.get("descricao_outras"),
    }
    # O ri_ctp le o documento em `documento_numero`, e nao em `documento`. Sem
    # esta traducao a parte sai com "indicadorNiIdentificado": false e a
    # Receita recebe uma declaracao sem quem alienou — que e pior do que uma
    # declaracao recusada, porque esta e aceita.
    #
    # Nome nao vai: a ficha de alienantes do manual nao tem campo de nome. A
    # Receita resolve pelo CPF, e por isso o CPF invalido barra o ato.
    partes = ([dict(x, papel="ALIENANTE",
                    documento_numero=x.get("documento_numero") or x.get("documento"))
               for x in (dec.get("alienantes") or [])] +
              [dict(x, papel="ADQUIRENTE",
                    documento_numero=x.get("documento_numero") or x.get("documento"))
               for x in (dec.get("adquirentes") or [])])
    # O MONTADOR É O DA CTP, E A LÍNGUA DO ARQUIVO É A DO DOI-WEB — 22/10/2026.
    # A CTP chama o cônjuge de `niConjuge`/`indicadorConjugeParticipante` e
    # escreve `IndicadorNaoConsta…` com «I»; o layout oficial do DOI-Web não
    # tem nenhum dos três (medido no `/api/layout-doiweb.json`). Ver `ri_doi`.
    from ri_doi import no_layout_do_doiweb
    return no_layout_do_doiweb(montar_registro(ato, m, partes, dados, cns, codigo_ibge,
                                               tipo_servico=tipo_servico,
                                               tipo_ato=tipo_ato))



def declaracao_da_escritura(ato: dict, partes: list[dict], cns: str,
                            codigo_ibge: str) -> tuple[dict | None, list[dict]]:
    """A declaração DOI-Web da escritura com imóvel, ou o que impede.

    MORAVA DENTRO DA ROTA DA DOI (`ri_web.ri_doi`) até 22/10/2026, e saiu
    para cá porque a CTP da CENSEC (`censec_ctp`) declara as MESMAS
    escrituras com os mesmos campos: dois montadores divergiriam no primeiro
    conserto, e a Receita e a prefeitura receberiam versões diferentes do
    mesmo negócio. Devolve `(registro, [])` ou `(None, problemas)`; cada
    problema é `{"campo", "motivo"}`, a forma que `resumo_impedimentos` lê.
    A declaração passa pelo layout oficial do DOI-Web antes de sair.
    """
    from ri_ctp import TIPO_OPERACAO
    from ri_doi import conferir_layout
    # A CHAVE E `motivo`, E NUNCA `texto`: e a que
    # `Impedimento.como_dict` devolve, e e por ela que
    # `resumo_impedimentos` conta os motivos no alto da tela. Com a
    # outra palavra as escrituras ficariam de fora da conferencia —
    # presentes na lista, ausentes da conta que se le antes de gerar o
    # arquivo. Eu escrevi `texto` na primeira versao.
    problemas = []
    # `str(...)` PORQUE `doi_transacao` E COLUNA INTEGER: o `11` que
    # a tela gravou como texto volta do banco como o numero 11, e
    # `.strip()` num numero estoura a tela inteira. A afinidade da
    # coluna converte na entrada, calada, e so aparece na leitura.
    for chave, rotulo in (("doi_transacao", "a operação imobiliária"),
                          ("doi_matricula", "a matrícula do imóvel")):
        if not str(ato.get(chave) or "").strip():
            problemas.append({"campo": chave,
                              "motivo": f"falta {rotulo}"})
    if str(ato.get("doi_transacao") or "") not in TIPO_OPERACAO:
        problemas.append({"campo": "doi_transacao",
                          "motivo": "operação imobiliária inválida"})
    if not ato.get("valor_transacao") or ato["valor_transacao"] <= 0:
        problemas.append({"campo": "valor_transacao",
                          "motivo": "falta o valor total da operação"})
    torna = ato.get("doi_torna_dinheiro") or 0
    if torna < 0 or (ato.get("valor_transacao") and torna > ato["valor_transacao"]):
        problemas.append({"campo": "doi_torna_dinheiro",
                          "motivo": "torna em dinheiro inválida para o valor total"})
    if torna and str(ato.get("doi_transacao") or "") != "13":
        problemas.append({"campo": "doi_torna_dinheiro",
                          "motivo": "torna em dinheiro exige operação Permuta"})

    partes_e = [dict(x) for x in partes]
    # QUEM ALIENOU E QUEM ADQUIRIU SAI DA QUALIFICACAO, medida — e nao
    # de um campo `papel`, que esta tabela nao tem. Ver
    # `notas_doi.lados_das_partes`: o procurador e descartado ANTES de
    # se procurar o vendedor, porque «PROCURADOR DO VENDEDOR» contem
    # «VENDEDOR» e o CPF de quem so assinou por outro iria a Receita
    # como o de quem vendeu.
    alienantes, adquirentes, duvidas = lados_das_partes(partes_e)
    if not partes_e:
        problemas.append({"campo": "partes",
                          "motivo": "falta lançar as partes da escritura"})
    else:
        if not alienantes:
            problemas.append({
                "campo": "alienantes",
                "motivo": "nenhuma parte foi qualificada como quem "
                          "alienou (vendedor, cedente, doador)"})
        if not adquirentes:
            problemas.append({
                "campo": "adquirentes",
                "motivo": "nenhuma parte foi qualificada como quem "
                          "adquiriu (comprador, cessionário, donatário)"})
        for d in duvidas:
            problemas.append({
                "campo": "partes",
                "motivo": f"não dá para saber de que lado "
                          f"{d.get('nome')} está: a qualificação é "
                          f"«{d.get('qualificacao') or 'em branco'}»"})
        # A SOMA DA PARTICIPACAO DE CADA LADO, que a Receita valida
        # entre 99% e 100% — e fora da faixa ela recusa o ARQUIVO
        # INTEIRO, e nao a linha. A ficha ja recusa no balcao; esta
        # conferencia pega o que foi gravado ANTES desta versao, que e
        # onde o percentual nao existia.
        for rotulo, lado in (("alienantes", alienantes),
                             ("adquirentes", adquirentes)):
            for x in conferir_participacoes(lado, rotulo) if lado else []:
                problemas.append(x.como_dict())

    if problemas:
        return None, problemas
    reg_e = declarar(
        {"operacao": ato["doi_transacao"],
         "natureza_titulo": 2,          # escritura pública
         "data_ato": (ato.get("data") or "")[:10],
         "livro": ato.get("livro"), "folha": ato.get("folha"),
         "valor_operacao": ato.get("valor_transacao"),
         "houve_permuta": str(ato.get("doi_transacao") or "") == "13",
         "houve_pagamento_dinheiro": bool(ato.get("doi_torna_dinheiro")),
         "valor_especie": ato.get("doi_torna_dinheiro"),
         "imovel": {"matricula": ato.get("doi_matricula"),
                    "tipo": ato.get("doi_tipo_imovel"),
                    "logradouro": ato.get("doi_endereco"),
                    "area": ato.get("doi_area")},
         "alienantes": alienantes, "adquirentes": adquirentes,
         "ato_id": ato["id"]},
        cns, codigo_ibge)
    erros = conferir_layout(reg_e)
    if erros:
        return None, problemas + [{"campo": "layout", "motivo": x} for x in erros]
    return reg_e, problemas


def _reais(centavos: int | None):
    """Centavos inteiros -> reais, que e o que o ri_ctp espera.

    Divisao inteira, e a fracao montada como texto: o valor nao vira float
    antes de precisar.
    """
    if centavos is None:
        return None
    sinal = "-" if centavos < 0 else ""
    n = abs(int(centavos))
    return f"{sinal}{n // 100},{n % 100:02d}"


def conferir_do_ctp(ato: dict, m: dict, partes: list[dict],
                    dados: dict) -> list[Impedimento]:
    """Confere um ato do Registro de Imoveis com o que ja foi digitado na CTP.

    POR QUE PASSA PELA CONFERENCIA DA CTP PRIMEIRO
        As duas obrigacoes nascem do mesmo dado. O que a CTP recusa, a DOI
        recusa tambem — e o `ri_ctp.conferir` ja sabe disso. Repetir aquelas
        regras aqui faria as duas divergirem na primeira que mudasse.

    O QUE SE ACRESCENTA
        So o que e da DOI e nao da CTP: a operacao desativada, a soma das
        participacoes e a unidade de area. Sao as tres que a Receita valida e
        recusa o arquivo inteiro.
    """
    from ri_ctp import conferir as conferir_ctp

    p = [Impedimento("ctp", motivo) for motivo in conferir_ctp(ato, m, partes, dados)]

    operacao = dados.get("operacao")
    if operacao and str(operacao).isdigit() and int(operacao) in OPERACOES_DESATIVADAS:
        nome, troca = OPERACOES_DESATIVADAS[int(operacao)]
        p.append(Impedimento("operacao",
                             f"a operação {operacao} — {nome} — foi desativada "
                             f"pela Receita; o código de hoje é {troca}"))

    for papel, filtro in (("alienantes", "ALIENANTE"), ("adquirentes", "ADQUIRENTE")):
        from ri_ctp import _papel as papel_ctp
        do_papel = [dict(x, participacao=x.get("participacao")
                         or dados.get(f"participacao_{x.get('id')}"))
                    for x in partes if papel_ctp(x) == filtro]
        if do_papel:
            p += conferir_participacoes(do_papel, papel)

    rural = (m.get("rural_urbano") or "").upper().startswith("R")
    area = m.get("area_valor") or dados.get("area")
    unidade = (m.get("area_unidade") or "").lower()
    if area and unidade:
        if rural and "m" in unidade and "ha" not in unidade:
            p.append(Impedimento("area",
                                 "imóvel rural com área em metros quadrados — a "
                                 "Receita pede hectares"))
        if not rural and "ha" in unidade:
            p.append(Impedimento("area",
                                 "imóvel urbano com área em hectares — a Receita "
                                 "pede metros quadrados"))
    return p


def gerar_carga(registros: list[dict], cns: str, competencia: str,
                sequencial_inicial: int = 1) -> str:
    """Serializa a carga DOI-Web: {"declaracoes": [ ... ]}.

    Fonte conferida: DOI_000000_202608_Livro30_fls184-192.json (DOI-Web /
    Livro 30 fls 184-192). O upload NAO leva cns/competencia/quantidade/
    numeroControle — esses campos ficam no LEIA-ME / metadados da remessa.
    `cns`, `competencia` e `sequencial_inicial` permanecem na assinatura por
    compatibilidade com a UI; `numero_de_controle()` segue disponivel se a
    tela ou testes precisarem do sequencial, mas nao entra no JSON de carga.

    Vide ESQUEMA_CONFERIDO.
    """
    # cns/competencia/sequencial: API da tela; envelope DOI-Web = so declaracoes.
    _ = (cns, competencia, sequencial_inicial)
    corpo = {"declaracoes": list(registros)}
    return json.dumps(corpo, ensure_ascii=False, indent=2)


def nome_arquivo(cns: str, competencia: str) -> str:
    return f"DOI_{so_digitos(cns)}_{competencia.replace('-', '')}.json"


def competencias_em_aberto(competencias_com_ato: list[str],
                           resolvidas: set[str], hoje: str) -> list[dict]:
    """Os meses que ainda devem satisfacao a Receita.

    POR QUE ISSO E O CORACAO DA TELA
        A inspecao nao cobra "gerar a DOI": cobra "anexar comprovacoes de DOI
        OU DECLARACOES NEGATIVAS DOS MESES SEM ATOS IMOBILIARIOS". Quer dizer
        que o mes sem ato tambem precisa de prova — e o mes esquecido nao
        aparece em lista nenhuma justamente por estar vazio.

        Por isso a lista sai do CALENDARIO, e nao dos atos: todo mes entre o
        primeiro ato do acervo e hoje deve ter uma resposta, nem que seja "nao
        houve ato".
    """
    if not competencias_com_ato:
        return []
    primeiro = min(competencias_com_ato)
    ano, mes = int(primeiro[:4]), int(primeiro[5:7])
    limite = hoje[:7]
    com_ato = set(competencias_com_ato)
    saida = []
    while f"{ano:04d}-{mes:02d}" <= limite:
        comp = f"{ano:04d}-{mes:02d}"
        if comp not in resolvidas:
            prazo = prazo_de_entrega(f"{comp}-01")
            saida.append({
                "competencia": comp,
                "tem_ato": comp in com_ato,
                "prazo": prazo,
                "vencida": prazo < hoje,
            })
        mes += 1
        if mes > 12:
            ano, mes = ano + 1, 1
    return saida


def resumo_impedimentos(impedidas: list[dict]) -> list[dict]:
    """Agrupa os motivos, do mais comum para o menos."""
    contas: dict[tuple[str, str], int] = {}
    for item in impedidas:
        for problema in item["problemas"]:
            chave = (problema["campo"], problema["motivo"])
            contas[chave] = contas.get(chave, 0) + 1
    return [{"campo": campo, "motivo": motivo, "declaracoes": n}
            for (campo, motivo), n in sorted(contas.items(), key=lambda x: -x[1])]
