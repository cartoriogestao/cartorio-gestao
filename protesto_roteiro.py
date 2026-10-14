"""O ROTEIRO DAS CENTRAIS, como o TJMA e o IEPTB-MA o escreveram.

Trazido pelo oficial em 01/09/2026, em dois papeis:

  - **ROTEIRO DAS CENTRAIS DE PROTESTO** — a lista dos passos da CRA e da
    CENPROT, com os QUATRO HORARIOS da CRA;
  - **Oficio Circular IEPTB-MA/CRA-MA n. 015/2025**, de 28/03/2025, que da o
    FUNDAMENTO de quatro dos passos da CENPROT.

**ISTO NAO ESTA NO ACERVO, e nao se descobre medindo.** O acervo guarda o que
foi lavrado; a ORDEM em que se faz, e a HORA ate a qual se pode fazer, sao
combinacao com a Central. E a segunda vez que um papel do oficial ensina uma
coisa que nenhuma medicao daria — a primeira foi o «SEMPRE QUE GERAR RETORNO,
GERAR ANDAMENTO», que reorganizou o modulo do retorno em 25/08/2026.

**O HORARIO E O QUE MAIS PESA, e o sistema nao o tinha em lugar nenhum.**
Perder as 11h30 do retorno nao e atraso de um dia: e o apresentante sem
resposta, e o titulo pago que continua aparecendo como protestado na Central.

**ESTE MODULO NAO FAZ NADA — ele DIZ.** Nao gera arquivo, nao lavra ato e nao
marca passo como feito: ele lista o roteiro, aponta a tela de cada passo e
mede, onde da, se aquilo ja aconteceu HOJE. Quem faz o passo e o escrevente;
quem sabe se ele foi feito e o balcao.

**E O QUE O SISTEMA NAO FAZ APARECE DIZENDO QUE NAO FAZ.** Um roteiro que
lista dez passos e leva a tela em oito, calando os dois, faz o escrevente
procurar o que nao existe — e concluir que errou o caminho. Aqui o passo sem
tela **diz onde se faz** (no site da Central) e por que o sistema ainda nao o
cobre.
"""
from __future__ import annotations

import sqlite3

# ------------------------------------------------------------------ a CRA

# OS QUATRO HORARIOS, do papel do oficial. Sao da CRA, e nao da CENPROT.
HORARIOS_DA_CRA = (
    {"o_que": "Envio de remessa", "hora": "12:30",
     "quem": "a CRA manda", "nosso": False},
    {"o_que": "Envio de confirmacao", "hora": "14:10",
     "quem": "a casa manda", "nosso": True},
    {"o_que": "Envio de retorno", "hora": "11:30",
     "quem": "a casa manda", "nosso": True},
    {"o_que": "Andamento", "hora": "11:30",
     "quem": "a casa manda", "nosso": True},
)

# `tela` e o endpoint; `None` quer dizer «o sistema nao faz isto», e o campo
# `onde` diz onde se faz. NAO SE INVENTA TELA: apontar para uma tela parecida
# faria o escrevente marcar o passo como feito sem te-lo feito.
ROTEIRO_DA_CRA = (
    {"passo": "Recebimento de remessa",
     "tela": "protesto_remessas",
     "medida": "remessa_recebida",
     "nota": "conferir e receber sao dois passos, e o primeiro nao grava nada"},
    {"passo": "Confirmacao de remessa",
     "tela": "protesto_remessas",
     "medida": "confirmacao_gerada",
     "nota": "sai sozinha ao receber o lote — uma por apresentante"},
    {"passo": "Envio do retorno",
     "tela": "protesto_retornos",
     "medida": "retorno_gerado",
     "nota": "ate as 11:30"},
    {"passo": "Envio do arquivo de andamento",
     "tela": "protesto_retornos",
     "medida": "andamento_gerado",
     "nota": "SEMPRE QUE GERAR RETORNO, GERAR ANDAMENTO — e tambem ao receber "
             "remessa"},
    {"passo": "Recebimento de pedidos de desistencia",
     "tela": "protesto_desistencias",
     "medida": "desistencia_recebida",
     "nota": "conferir tres vezes por dia: protestar titulo de que o credor "
             "desistiu e o erro que menos se desfaz"},
    {"passo": "Recebimento de pedidos de cancelamento",
     "tela": "protesto_cra_api", "medida": None,
     "onde": "no site da CRA, ou pela API",
     "nota": "MEDIDO: dos 54 cancelamentos que esta casa lavrou, 2 vieram "
             "pela Central — a anuencia do credor chega ao balcao. **Desde "
             "02/09/2026 o arquivo se TRAZ pela API**, e vem CRU: o formato "
             "do que a Central devolve ainda nao foi medido, e aplica-lo por "
             "palpite apontaria titulo que ninguem apresentou"},
    {"passo": "Recebimento de pedidos de autorizacao de cancelamento (AC)",
     "tela": "protesto_cra_api", "medida": None,
     "onde": "no site da CRA, ou pela API",
     "nota": "MEDIDO: 2 titulos de 1.370, os dois da Equatorial Maranhao. "
             "**Desde 02/09/2026 as autorizacoes se TRAZEM pela API** — de "
             "retirada e de cancelamento —, e a consulta de uma delas MARCA "
             "como baixada na Central salvo se se disser que nao"},
    {"passo": "Geracao de boleto de repasse dos titulos pagos "
              "(apresentantes IEPTB-MA, ex.: SEFAZ-MA)",
     "tela": None, "medida": None,
     "onde": "no site da CRA",
     "nota": "o sistema NAO gera boleto: o verificador do codigo de barras "
             "desta casa nao se explicou (melhor acerto 465 de 1.618, nivel "
             "de acaso). Codigo errado e dinheiro no lugar errado"},
)

# ------------------------------------------------------------------ a CENPROT

# O FUNDAMENTO de cada um veio do Oficio Circular 015/2025 do IEPTB-MA. Onde
# ele nao cita norma, o campo fica vazio — e nao se preenche por semelhanca.
ROTEIRO_DA_CENPROT = (
    {"passo": "Recebimento de remessa (menu Gestao de Pedidos)",
     "tela": "protesto_pendencias", "medida": "pedido_protesto_baixado",
     "onde": "no site da CENPROT, menu Gestao de Pedidos",
     "nota": "e a remessa que chega pela CENPROT, e nao pela CRA. **Passou a "
             "ter tela em 02/09/2026**, pela API: `/pedidos/consulta` traz o "
             "pedido e `/pedidos/protocolar` devolve o protocolo desta casa. "
             "O site continua servindo — o que mudou e nao ser obrigatorio"},
    {"passo": "Envio do arquivo XML diario dos apontados e suas ocorrencias",
     "tela": None, "medida": None,
     "onde": "no site da CENPROT",
     "norma": "art. 4o da Resolucao n. 1 do IEPTB-BR",
     "nota": "o sistema LE este arquivo (e dele que vem a chave unica), e "
             "ainda NAO o gera. As oito ocorrencias que a norma lista sao "
             "apontados, devolvidos por irregularidade, pagos, retirados por "
             "desistencia, sustados, protestados, suspensos e cancelados"},
    {"passo": "Envio do instrumento de protesto eletronico",
     "tela": None, "medida": None,
     "onde": "no site da CENPROT",
     "norma": "art. 11 da Resolucao n. 1 do IEPTB-BR",
     "nota": "vai ao apresentante e ao credor"},
    {"passo": "Recebimento de pedido de certidao eletronica de protesto",
     "tela": "protesto_certidoes", "medida": None,
     "onde": "o PEDIDO chega no site da CENPROT",
     "nota": "a certidao se emite aqui. **O pedido passou a chegar pela API "
             "em 02/09/2026** — em Pendencias da CENPROT —, e o orcamento "
             "sobe por la; o que a Central exige e o `vl_orcamento`, que e o "
             "numero que o solicitante ve"},
    {"passo": "Recebimento dos pedidos de anuencia",
     "tela": "protesto_pendencias", "medida": "anuencia_baixada",
     "onde": "no site da CENPROT",
     "nota": "a aprovacao e AUTOMATICA por meio do arquivo de emolumentos — "
             "e por isso mandar o arquivo em dia faz diferenca aqui. **Passou "
             "a ter tela em 02/09/2026**: a anuencia se baixa, o oficial "
             "aprova ou recusa, e os PDFs assinados com e-CPF vem pelo botao "
             "«Baixar os arquivos assinados» — e eles sao a prova de que o "
             "credor consentiu"},
    {"passo": "Recebimento de pedido de cancelamento",
     "tela": "protesto_pendencias", "medida": "cancelamento_cenprot_baixado",
     "onde": "no site da CENPROT",
     "nota": "o ato de cancelamento se lavra na ficha do titulo, e continua "
             "assim: **a tela de 02/09/2026 apenas INFORMA a Central** do que "
             "ja foi lavrado. Uma coisa fica A CONFERIR na homologacao — o "
             "contrato chama o numero de `cd_pedido` no envio e de "
             "`nr_pedido` na resposta"},
    {"passo": "Envio do edital eletronico",
     "tela": "protesto_cenprot", "medida": "edital_publicado",
     "norma": "art. 15, § 1o, da Lei 9.492/1997, e Resolucao n. 8 do IEPTB-BR",
     "nota": "o arquivo sai do que ja foi PUBLICADO no dia"},
    {"passo": "Envio do arquivo de emolumentos",
     "tela": "protesto_cenprot", "medida": None,
     "norma": "Resolucao n. 9 de 2024",
     "nota": "os dois valores que o devedor paga para retirar e para cancelar. "
             "**Desde 02/09/2026 o mesmo arquivo sobe pela API**, e nao so "
             "baixa: e o botao «Enviar a CENPROT pela API», ao lado do de "
             "baixar, e o arquivo e o MESMO — pela mesma funcao"},
)

# O QUE SO O TABELIAO OU O SUBSTITUTO FAZ, e o papel diz com essas palavras.
SO_O_TABELIAO = (
    ("Cadastro de usuario na CENPROT e na CRA — o Tabeliao ou Substituto "
     "deve faze-lo."),
)

# CADA FONTE ENTRE PARENTESES, e nao pela quebra de linha solta: sem eles o
# Python junta duas linhas vizinhas numa string so, e a lista perde uma fonte
# sem erro nenhum. O ruff chama isso de «esqueceu a virgula?», e aqui o
# estrago seria a tela citar um papel a menos.
FONTES = (
    ("ROTEIRO DAS CENTRAIS DE PROTESTO (TJMA), trazido pelo oficial em "
     "01/09/2026"),
    ("Oficio Circular IEPTB-MA/CRA-MA n. 015/2025, de 28/03/2025 — "
     "«Rotina de Alimentacao da CENPROT»"),
)


# ------------------------------------------------------------------ medir


# O QUE ENTROU HOJE, POR ESPECIE DA CENPROT. Escrita uma vez: tres copias da
# mesma consulta divergiriam no primeiro conserto.
_POR_ESPECIE = ("SELECT COUNT(*) FROM cn_pendencias "
                "WHERE especie=? AND baixada_em >= ? AND baixada_em < ?")


def _um(con: sqlite3.Connection, tabela: str, sql: str, *args) -> int | None:
    """Conta. Devolve `None` — e nao zero — quando a TABELA nao existe aqui.

    **E ELE SO PERDOA A TABELA QUE FALTA, e nada mais.** A primeira versao
    tinha `except sqlite3.Error: return 0`, e isso me escondeu um defeito meu
    no mesmo minuto: eu havia escrito `recebido_em` onde a coluna se chama
    **`recebida_em`**, e o guarda largo devolvia **zero com cara de medicao**.
    A tela diria «nenhuma remessa hoje» para sempre, e ninguem desconfiaria.

    E a regra que este projeto ja tinha escrita — «except largo vira zero com
    cara de medicao» — apanhada pelo teste, e nao pela releitura. Coluna errada
    agora **estoura**, que e onde ela tem de aparecer.
    """
    existe = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (tabela,)).fetchone()
    if not existe:
        return None
    return int(con.execute(sql, args).fetchone()[0] or 0)


def o_que_ja_aconteceu_hoje(con: sqlite3.Connection, *, hoje: str) -> dict:
    """Quantos de cada passo ja aconteceram HOJE. So LE.

    **CONTA, E NAO JULGA.** Devolve numeros; quem diz se o dia esta em ordem e
    quem esta no balcao. Um zero aqui pode ser «ainda nao fiz» ou «hoje nao
    veio nada da Central», e o sistema **nao tem como saber qual** — dizer
    «atrasado» sobre um dia em que nada chegou seria alarme que soa sempre.
    """
    dia = str(hoje)[:10]
    # O DIA SE COMPARA POR FAIXA, e nao recortando texto dentro do banco: o
    # teto de acoplamento ao SQLite e ZERO para modulo novo, e o varredor me
    # pegou com tres recortes. A coluna guarda `2026-09-01T11:00:00`; a faixa
    # `[dia, dia+'~')` apanha o dia inteiro, porque `~` vem depois de todo
    # digito e da letra `T` na ordem do ASCII.
    #
    # E ELE ME PEGOU DUAS VEZES: na segunda, pela funcao citada no COMENTARIO
    # que explicava tirar a funcao. E a licao «varredor bate na propria prosa»
    # pela quinta vez neste projeto — e desta vez a prosa era minha.
    #
    # AS COLUNAS SAO `recebida_em` E `gerado_em`, medidas no esquema. Eu havia
    # escrito `recebido_em` nas duas primeiras — nome plausivel, coluna
    # inexistente —, e so apareceu porque o guarda deixou de engolir o erro.
    ate = dia + "~"
    por_tipo = ("SELECT COUNT(*) FROM pt_retornos "
                "WHERE tipo=? AND gerado_em >= ? AND gerado_em < ?")
    return {
        "remessa_recebida": _um(
            con, "pt_remessas",
            "SELECT COUNT(*) FROM pt_remessas "
            "WHERE recebida_em >= ? AND recebida_em < ?", dia, ate),
        "confirmacao_gerada": _um(con, "pt_retornos", por_tipo,
                                  "SDTBFOCRT", dia, ate),
        "retorno_gerado": _um(con, "pt_retornos", por_tipo,
                              "SDTBFORTP", dia, ate),
        "andamento_gerado": _um(con, "pt_retornos", por_tipo,
                                "SDTBFOAND", dia, ate),
        "desistencia_recebida": _um(
            con, "pt_desistencias",
            "SELECT COUNT(*) FROM pt_desistencias "
            "WHERE recebida_em >= ? AND recebida_em < ?", dia, ate),
        "edital_publicado": _um(
            con, "pt_editais",
            "SELECT COUNT(*) FROM pt_editais WHERE publicado_em=?", dia),
        # AS TRES DA CENPROT, de 02/09/2026. **O que se conta e o que ENTROU
        # hoje**, e nao o que espera — a pergunta deste quadro e «o que ja
        # aconteceu», como no `remessa_recebida` logo acima. Quantas esperam e
        # outra pergunta, e quem a responde e `cenprot_pendencias.painel`.
        #
        # **A FAIXA DE DATA E A MESMA**, e nao um recorte de texto no SQL: o
        # teto de acoplamento deste modulo e ZERO, e o varredor ja me pegou
        # duas vezes aqui.
        "anuencia_baixada": _um(
            con, "cn_pendencias", _POR_ESPECIE, "ANUENCIA", dia, ate),
        "cancelamento_cenprot_baixado": _um(
            con, "cn_pendencias", _POR_ESPECIE, "CANCELAMENTO", dia, ate),
        "pedido_protesto_baixado": _um(
            con, "cn_pendencias", _POR_ESPECIE, "PEDIDO_PROTESTO", dia, ate),
    }


def roteiro(con: sqlite3.Connection, *, hoje: str) -> dict:
    """As duas listas, com o que ja aconteceu hoje ao lado de cada passo.

    O RESULTADO E PARA A TELA, e por isso ele ja vem com tudo junto: o passo,
    a tela (ou o «onde», quando o sistema nao faz), a norma quando o oficio a
    cita, e o numero de hoje quando ha o que contar.
    """
    feito = o_que_ja_aconteceu_hoje(con, hoje=hoje)

    def montar(lista):
        saida = []
        for p in lista:
            linha = dict(p)
            chave = p.get("medida")
            linha["quantos_hoje"] = feito.get(chave) if chave else None
            linha["o_sistema_faz"] = bool(p.get("tela"))
            saida.append(linha)
        return saida

    return {"cra": montar(ROTEIRO_DA_CRA),
            "cenprot": montar(ROTEIRO_DA_CENPROT),
            "horarios": [dict(h) for h in HORARIOS_DA_CRA],
            "so_o_tabeliao": list(SO_O_TABELIAO),
            "fontes": list(FONTES),
            "hoje": str(hoje)[:10]}


def quantos_o_sistema_faz() -> dict:
    """Quantos passos de cada roteiro tem tela nesta casa. So conta.

    **O NUMERO FICA A VISTA, e nao escondido no fim da lista.** Um roteiro que
    nao diz quanto dele o sistema cobre deixa o escrevente supor que cobre
    tudo — e o que ele nao cobre e justamente o que alguem precisa lembrar de
    fazer no site da Central.
    """
    return {"cra_com_tela": sum(1 for p in ROTEIRO_DA_CRA if p.get("tela")),
            "cra_total": len(ROTEIRO_DA_CRA),
            "cenprot_com_tela": sum(1 for p in ROTEIRO_DA_CENPROT
                                    if p.get("tela")),
            "cenprot_total": len(ROTEIRO_DA_CENPROT)}
