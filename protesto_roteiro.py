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

from bd_nativo import banco

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
     "tela": "protesto_cenprot_xml", "medida": None,
     "onde": "gera aqui; sobe no site da CENPROT",
     "norma": "art. 4o da Resolucao n. 1 do IEPTB-BR",
     "nota": "**o sistema GERA desde 15/10/2026** os dois arquivos que esta "
             "casa manda: o P (protestos) e o D (pagos, retirados e "
             "cancelados) — apontamento a casa nao manda, porque o titulo ja "
             "tem a chave. A forma foi provada byte a byte contra 28 arquivos "
             "reais. O ENVIO e pelo portal: a API da CENPROT nao tem caminho "
             "para este arquivo"},
    {"passo": "Envio do instrumento de protesto eletronico",
     "tela": None, "medida": None,
     "onde": "dentro do arquivo P, no site da CENPROT",
     "norma": "art. 11 da Resolucao n. 1 do IEPTB-BR",
     "nota": "o instrumento ASSINADO com o A3 (tela dos instrumentos) vai "
             "DENTRO do arquivo P, em base64 — e o que a casa sempre fez. "
             "Protesto sem instrumento assinado espera, e a tela diz por que"},
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
                "WHERE especie=%s AND baixada_em >= %s AND baixada_em < %s")

# A LINHA QUE MARCA A VIRADA DO PROTESTO NAO E ARQUIVO (protesto_retorno.
# _registro_do_eoficio): ela traz `cra_enviado_ambiente = 'EOFICIO'`.
_NAO_E_A_VIRADA = "COALESCE(cra_enviado_ambiente, '') <> 'EOFICIO'"


def _um(con: sqlite3.Connection, tabela: str | tuple, sql: str,
        *args) -> int | None:
    """Conta. Devolve `None` — e nao zero — quando a TABELA nao existe aqui.

    `tabela` pode ser uma tupla, quando a consulta junta mais de uma (14/10/2026,
    o painel do dia): basta faltar UMA para nao haver o que contar.

    **E ELE SO PERDOA A TABELA QUE FALTA, e nada mais.** A primeira versao
    tinha `except sqlite3.Error: return 0`, e isso me escondeu um defeito meu
    no mesmo minuto: eu havia escrito `recebido_em` onde a coluna se chama
    **`recebida_em`**, e o guarda largo devolvia **zero com cara de medicao**.
    A tela diria «nenhuma remessa hoje» para sempre, e ninguem desconfiaria.

    E a regra que este projeto ja tinha escrita — «except largo vira zero com
    cara de medicao» — apanhada pelo teste, e nao pela releitura. Coluna errada
    agora **estoura**, que e onde ela tem de aparecer.
    """
    if not _existe(con, *((tabela,) if isinstance(tabela, str) else tabela)):
        return None
    return int(banco(con).valor(sql, args) or 0)


def _existe(con: sqlite3.Connection, *tabelas: str) -> bool:
    """As tabelas existem todas nesta instalacao? So LE o catalogo."""
    for tabela in tabelas:
        if not banco(con).tem_tabela(tabela):
            return False
    return True


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
    # A MARCA DA VIRADA NAO E ARQUIVO DESTE DIA (14/10/2026). A virada do
    # Protesto gravou em `pt_retornos` duas linhas que «nao sao arquivo deste
    # sistema» — marcam o que o E-Oficio ja informou a CRA —, com `gerado_em`
    # do dia da virada e `cra_enviado_ambiente = 'EOFICIO'`. Contadas, a coluna
    # «hoje» diria «1 retorno gerado» no primeiro dia sem ninguem ter gerado.
    por_tipo = ("SELECT COUNT(*) FROM pt_retornos "
                "WHERE tipo=%s AND gerado_em >= %s AND gerado_em < %s "
                f"AND {_NAO_E_A_VIRADA}")
    return {
        "remessa_recebida": _um(
            con, "pt_remessas",
            "SELECT COUNT(*) FROM pt_remessas "
            "WHERE recebida_em >= %s AND recebida_em < %s", dia, ate),
        "confirmacao_gerada": _um(con, "pt_retornos", por_tipo,
                                  "SDTBFOCRT", dia, ate),
        "retorno_gerado": _um(con, "pt_retornos", por_tipo,
                              "SDTBFORTP", dia, ate),
        "andamento_gerado": _um(con, "pt_retornos", por_tipo,
                                "SDTBFOAND", dia, ate),
        "desistencia_recebida": _um(
            con, "pt_desistencias",
            "SELECT COUNT(*) FROM pt_desistencias "
            "WHERE recebida_em >= %s AND recebida_em < %s", dia, ate),
        "edital_publicado": _um(
            con, "pt_editais",
            "SELECT COUNT(*) FROM pt_editais WHERE publicado_em=%s", dia),
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

    painel = painel_do_dia(con, hoje=hoje)
    return {"cra": montar(ROTEIRO_DA_CRA),
            "cenprot": montar(ROTEIRO_DA_CENPROT),
            "horarios": [dict(h) for h in HORARIOS_DA_CRA],
            "so_o_tabeliao": list(SO_O_TABELIAO),
            "fontes": list(FONTES),
            "hoje": str(hoje)[:10],
            # O PAINEL DO DIA (14/10/2026) vai junto, e nao numa rota nova: a
            # rota mora em `atribuicoes_web` e entrega `r` inteiro a tela.
            "etapas": painel["etapas"],
            "relogio": painel["relogio"],
            "estado": painel["estado"]}


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


# ================================================================ o PAINEL DO DIA
#
# Pedido do oficial em 14/10/2026, o primeiro dia operando o protesto no
# sistema: «precisa ter botao claro e bem posicionado para cada parte da rotina
# do protesto, desde recebimento de remessa ao envio de arquivo xml assinado a
# CENPROT» e «preciso que tudo esteja integrado e seja um fluxo natural o
# recebimento do titulo, intimacao, protesto, mais organizado e completo».
#
# O ROTEIRO ACIMA E O PAPEL DO TJMA, na ordem do papel; o PAINEL e a ROTINA, na
# ordem em que o titulo anda — entra, ganha imagem, e confirmado, e intimado,
# desiste ou paga, e protestado, volta a CRA, sobe a CENPROT e vira certidao.
# Os dois ficam: o papel e a fonte; o painel e por onde se trabalha.
#
# CADA ETAPA TEM UM BOTAO PRINCIPAL, e ele leva a tela que FAZ aquilo. Onde a
# peca nao existe, ou so gera arquivo, a etapa diz isso com todas as letras em
# `falta` — e o botao nao aparece fingindo. Um botao «enviar a CENPROT» que
# baixasse um arquivo faria o escrevente dar o passo por feito.
#
# A CONTAGEM E DO QUE ESPERA, e nao julga: nada aqui diz «atrasado». `None` e
# «nao deu para medir» (a tabela nao existe nesta instalacao); zero e medido.

#: O ambiente que os links pedem. A partir de 14/10/2026 tudo e producao, e as
#: telas das Centrais ainda abrem na homologacao quando nao se diz qual — por
#: isso o painel DIZ. E o valor de `centrais_cred.PRODUCAO` (ha teste).
AMBIENTE_DE_PRODUCAO = "PRODUCAO"

#: O que cada contagem quer dizer, na frase que vai a tela. A chave e a mesma
#: de `medir_o_dia`; ha teste que exige as duas listas iguais.
MEDIDAS_DO_DIA: dict[str, str] = {
    "remessas_recebidas_hoje": "remessas recebidas hoje",
    "titulos_sem_apontamento": "títulos cadastrados e ainda não apontados",
    "arquivos_trazidos_da_cra_hoje": "arquivos trazidos da CRA pela API hoje",
    "abertos_sem_imagem": "títulos em aberto sem imagem guardada",
    "confirmacoes_hoje": "confirmações geradas hoje",
    "confirmacoes_aceitas_hoje": "delas, aceitas pela CRA (API, produção)",
    "confirmacoes_com_erro_hoje": "delas, com erro no envio pela API",
    "apontados_sem_aviso": "apontados sem aviso emitido neste sistema",
    "avisos_esperando_entrega": "avisos emitidos esperando o resultado da entrega",
    "avisos_esperando_edital": "avisos não entregues esperando o edital",
    "abertos_sem_chave": "títulos em aberto sem a chave da CENPROT "
                         "(sem ela a intimação digital não vai)",
    "intimacoes_digitais_hoje": "intimações digitais enviadas hoje (produção)",
    "desistencias_hoje": "arquivos de desistência recebidos hoje",
    "desistencias_com_titulo_por_aplicar": "arquivos de desistência com "
                                           "título ainda não aplicado",
    "titulos_em_aberto": "títulos em aberto (apontados ou intimados)",
    "pagamentos_e_retiradas_hoje": "pagamentos e desistências lavrados hoje",
    "a_protestar": "intimados sem movimentação desde a intimação",
    "atos_esperando_retorno": "atos lavrados que ainda não saíram num retorno",
    "atos_esperando_andamento": "apontamentos que ainda não saíram num andamento",
    "retornos_e_andamentos_hoje": "retornos e andamentos gerados hoje",
    "retornos_e_andamentos_aceitos_hoje": "deles, aceitos pela CRA "
                                          "(API, produção)",
    "cenprot_esperando": "pendências da CENPROT esperando resposta (produção)",
    "cenprot_divergencias": "títulos de origem CENPROT em que a Central e o "
                            "sistema divergem (última consulta à Central)",
    "editais_hoje": "editais publicados hoje",
    "emolumentos_enviados_hoje": "arquivos de emolumentos enviados pela API hoje",
    "certidoes_hoje": "certidões de protesto emitidas hoje",
    "pedidos_de_certidao_cenprot": "pedidos de certidão da CENPROT esperando "
                                   "(produção)",
    "protestos_sem_instrumento": "protestos lavrados neste sistema ainda sem "
                                 "instrumento",
}

# AS ETAPAS, NA ORDEM EM QUE O TITULO ANDA. `hora` aponta para HORARIOS_DA_CRA
# pelo nome — o horario mora num lugar so. `botoes`: o primeiro e o principal;
# `args` vao ao `url_for`; `quem` avisa quando a tela e so do oficial/gerente.
# `faz` diz o que a tela FAZ de verdade; `falta`, o que ela NAO faz — e quando
# nao ha tela nenhuma, `botoes` fica vazio e `falta` diz onde se faz.
ETAPAS_DO_DIA: tuple[dict, ...] = (
    {"n": 1, "ancora": "etapa-remessa",
     "titulo": "Receber a remessa da CRA",
     "hora": "Envio de remessa",
     "botoes": (
         {"rotulo": "Conferir e receber a remessa",
          "tela": "protesto_remessas", "args": {}},
         {"rotulo": "Trazer o arquivo da CRA pela API",
          "tela": "protesto_cra_api",
          "args": {"ambiente": AMBIENTE_DE_PRODUCAO},
          "quem": "oficial e gerente"},
     ),
     "faz": ("«Trazer e conferir» busca a remessa na CRA e a leva direto à "
             "conferência (ou suba o arquivo, se já o tiver) — conferir não "
             "grava nada. Depois, Receber: cada título é cadastrado e apontado "
             "(protocolo e lugar no Livro de Apontamento), e saem a confirmação "
             "e o andamento."),
     "falta": ("Trazer da CRA é do oficial e do gerente, e é botão: baixar "
               "marca a remessa como baixada do lado de lá."),
     "medidas": ("remessas_recebidas_hoje", "titulos_sem_apontamento",
                 "arquivos_trazidos_da_cra_hoje")},
    {"n": 2, "ancora": "etapa-imagens",
     "titulo": "Guardar as imagens dos títulos",
     "hora": None,
     "botoes": (
         {"rotulo": "Subir o .zip das imagens",
          "tela": "protesto_imagens", "args": {}},
     ),
     "faz": ("O .zip que a CRA entrega à parte se sobe aqui. Cada imagem só se "
             "prende ao título quando o nosso número E o documento do devedor "
             "apontam para o mesmo título."),
     "falta": ("O .zip se baixa no site da CRA (ou pela tela da API, marcando "
               "«trazer também a imagem»); o sistema não o busca sozinho."),
     "medidas": ("abertos_sem_imagem",)},
    {"n": 3, "ancora": "etapa-confirmacao",
     "titulo": "Confirmar a remessa à CRA",
     "hora": "Envio de confirmacao",
     "botoes": (
         {"rotulo": "Ver as remessas e as confirmações",
          "tela": "protesto_remessas", "args": {}},
     ),
     "faz": ("A confirmação nasce sozinha ao receber a remessa, uma por "
             "apresentante, e sobe pela API logo depois — se o envio automático "
             "de produção estiver ligado nas Configurações e a credencial da "
             "CRA estiver informada (veja o quadro abaixo)."),
     "falta": ("A confirmação que não subiu sozinha se manda pelo botão «Enviar "
               "à CRA», em «Arquivos gerados» na tela do retorno, até as 14:10."),
     "medidas": ("confirmacoes_hoje", "confirmacoes_aceitas_hoje",
                 "confirmacoes_com_erro_hoje"),
     "mostra_envio_automatico": True},
    {"n": 4, "ancora": "etapa-intimar",
     "titulo": "Intimar o devedor",
     "hora": None,
     "botoes": (
         {"rotulo": "Avisos, entregas e editais",
          "tela": "protesto_avisos", "args": {}},
         {"rotulo": "Intimação digital (Resolve)",
          "tela": "protesto_resolve",
          "args": {"ambiente": AMBIENTE_DE_PRODUCAO}},
     ),
     "faz": ("O aviso se emite na ficha de cada título; na tela de avisos se "
             "registra a entrega (a intimação pessoal) ou se publica o edital. "
             "A intimação digital sobe de verdade pela API da Resolve."),
     "falta": ("Não há emissão de avisos em lote: abre-se o título e emite-se "
               "o aviso na ficha. E o que a Resolve chama de «intimado» é "
               "ciência do devedor — a intimação que vale para o protesto se "
               "lavra na ficha do título."),
     "medidas": ("apontados_sem_aviso", "avisos_esperando_entrega",
                 "avisos_esperando_edital", "abertos_sem_chave",
                 "intimacoes_digitais_hoje")},
    {"n": 5, "ancora": "etapa-desistencias",
     "titulo": "Aplicar as desistências da CRA",
     "hora": None,
     "botoes": (
         {"rotulo": "Conferir e aplicar desistências",
          "tela": "protesto_desistencias", "args": {}},
     ),
     "faz": ("Suba o arquivo de desistência (DP), confira e marque os títulos; "
             "cada um vira o ato de desistência. O roteiro manda conferir três "
             "vezes por dia."),
     "falta": ("O arquivo se traz do site da CRA ou pela tela da API "
               "(«Desistências do dia»); o sistema não o aplica sozinho, de "
               "propósito."),
     "medidas": ("desistencias_hoje", "desistencias_com_titulo_por_aplicar")},
    {"n": 6, "ancora": "etapa-balcao",
     "titulo": "Pagamentos e retiradas no balcão",
     "hora": None,
     "botoes": (
         {"rotulo": "Abrir a lista de títulos",
          "tela": "protesto_titulos", "args": {}},
         {"rotulo": "Livro de Registro de Pagamentos",
          "tela": "protesto_livro", "args": {"qual": "pagamentos"}},
         {"rotulo": "Livro de Protocolo",
          "tela": "protesto_livro", "args": {"qual": "protocolo"}},
         # O DINHEIRO DO TÍTULO PAGO AINDA É DO APRESENTANTE (LG05).
         {"rotulo": "Repasses ao apresentante",
          "tela": "protesto_repasses", "args": {}},
     ),
     "faz": ("O pagamento e a retirada se lançam na ficha do título (botões da "
             "ficha), com selo, custas e a forma de pagamento que o Livro de "
             "Pagamentos exige (CN-MA art. 930). Os dois livros que a "
             "inspeção cobrou saem por período, em tela e em papel."),
     "falta": ("Não há uma tela própria de caixa do protesto: procure o título "
               "na lista e lance na ficha."),
     "medidas": ("titulos_em_aberto", "pagamentos_e_retiradas_hoje")},
    {"n": 7, "ancora": "etapa-protestar",
     "titulo": "Lavrar os protestos (lote da tarde)",
     "hora": None,
     "botoes": (
         {"rotulo": "Ver a lista e lavrar os marcados",
          "tela": "protesto_a_protestar", "args": {}},
     ),
     "faz": ("Lista os intimados sem movimentação desde a intimação, com os dias "
             "contados, e lavra só os que você marcar — cada um na sua "
             "transação. O sustado não aparece."),
     "falta": ("O sistema conta os dias e não julga o prazo: quem decide se o "
               "protesto sai é quem assina."),
     "medidas": ("a_protestar",)},
    {"n": 8, "ancora": "etapa-retorno",
     "titulo": "Retorno e andamento à CRA",
     "hora": "Envio de retorno",
     "botoes": (
         {"rotulo": "Gerar retorno e andamento",
          "tela": "protesto_retornos", "args": {}},
     ),
     "faz": ("Gera os dois arquivos juntos, por apresentante, com tudo o que "
             "foi lavrado e a CRA ainda não sabe (sempre que gerar retorno, "
             "gerar andamento)."),
     "falta": ("O retorno sobe pelo botão «Enviar à CRA», em «Arquivos "
               "gerados», até as 11:30. O ANDAMENTO EM PAR COM O RETORNO "
               "(pagamento, protesto, desistência) ainda sobe pelo portal da "
               "CRA: o código dele na Central não foi medido."),
     "medidas": ("atos_esperando_retorno", "atos_esperando_andamento",
                 "retornos_e_andamentos_hoje",
                 "retornos_e_andamentos_aceitos_hoje")},
    {"n": 9, "ancora": "etapa-cenprot",
     "titulo": "CENPROT",
     "hora": None,
     "botoes": (
         {"rotulo": "Pendências da CENPROT (anuências, certidões, "
                    "cancelamentos, renegociações)",
          "tela": "protesto_pendencias",
          "args": {"ambiente": AMBIENTE_DE_PRODUCAO}},
         {"rotulo": "Chave única, emolumentos e edital eletrônico",
          "tela": "protesto_cenprot", "args": {}},
         {"rotulo": "Arquivo XML diário (P e D)",
          "tela": "protesto_cenprot_xml", "args": {}},
         # 29/10/2026 — o que a Central diz de cada pedido × o título aqui.
         {"rotulo": "Conferência CENPROT × sistema",
          "tela": "protesto_cenprot_conferencia", "args": {}},
     ),
     "faz": ("Pendências: baixa da CENPROT, você decide, e a resposta sobe pela "
             "API. Chave única: lê o XML que a CENPROT devolve e grava a chave "
             "de cada título. Emolumentos: gera o arquivo e o envia pela API. "
             "Edital eletrônico: gera o arquivo dos editais publicados no dia."),
     "falta": ("O edital eletrônico só se GERA — o envio é pelo portal da "
               "CENPROT. O XML diário (P e D, com o instrumento assinado dentro) o "
               "sistema GERA desde 15/10/2026; o envio é pelo portal da "
               "CENPROT, porque a API dela não tem caminho para ele."),
     "medidas": ("cenprot_esperando", "abertos_sem_chave", "editais_hoje",
                 "emolumentos_enviados_hoje", "cenprot_divergencias"),
     "sem_botao": ("o ENVIO do XML diário — o arquivo se gera aqui e se "
                   "sobe pelo portal da CENPROT")},
    {"n": 10, "ancora": "etapa-certidoes",
     "titulo": "Certidões e instrumento de protesto",
     "hora": None,
     "botoes": (
         {"rotulo": "Emitir certidão",
          "tela": "protesto_certidoes", "args": {}},
         {"rotulo": "Instrumentos de protesto",
          "tela": "protesto_instrumentos", "args": {}},
         # CN-MA art. 949: a relação do dia às entidades de crédito (LG05).
         {"rotulo": "Certidão diária em relação",
          "tela": "protesto_relacao_diaria", "args": {}},
     ),
     "faz": ("A certidão (negativa, positiva ou de cancelamento) se emite aqui, "
             "com número, teor congelado e selo. O instrumento se emite por "
             "título protestado, com os dez itens do art. 22 conferidos."),
     "falta": ("O instrumento sai para ser assinado FORA do sistema (o A3 não "
               "assina por aqui) e não sobe à CENPROT por API — o envio do "
               "instrumento eletrônico é pelo portal. O pedido de certidão que "
               "chega pela CENPROT fica em Pendências da CENPROT."),
     "medidas": ("certidoes_hoje", "pedidos_de_certidao_cenprot",
                 "protestos_sem_instrumento")},
)


def _faixa(hoje: str) -> tuple[str, str]:
    """O dia inteiro como faixa de texto — a mesma regra de cima, sem recorte."""
    dia = str(hoje)[:10]
    return dia, dia + "~"


def medir_o_dia(con: sqlite3.Connection, *, hoje: str) -> dict:
    """O que espera em cada etapa, e o que ja aconteceu hoje. SO LE.

    **CONTA, E NAO JULGA**, como o resto deste modulo. `None` e «nao deu para
    medir» (a tabela nao existe aqui); zero e medido. O acervo do E-Oficio nao
    vira trabalho de hoje onde a pergunta e «o que este sistema fez»: o
    instrumento conta so o protesto lavrado aqui, e a marca da virada nao conta
    como arquivo gerado.
    """
    import protesto as PT
    import protesto_imagens as PIMG
    import protesto_retorno as PRE
    from cn_schema import CERTIDAO, SITUACOES_TERMINAIS

    dia, ate = _faixa(hoje)
    terminais = sorted(SITUACOES_TERMINAIS)
    marcas = ", ".join(["%s"] * len(terminais))
    gerados = ("SELECT COUNT(*) FROM pt_retornos WHERE tipo IN ({tipos}) "
               "AND gerado_em >= %s AND gerado_em < %s "
               f"AND {_NAO_E_A_VIRADA}")
    aceitos = (gerados + " AND cra_enviado_em IS NOT NULL "
               "AND cra_enviado_ambiente = %s")
    com_erro = (gerados + " AND cra_enviado_em IS NULL "
                "AND TRIM(COALESCE(cra_envio_erro, '')) <> ''")
    um_tipo = "%s"
    dois_tipos = "%s, %s"
    em_aberto = "('APONTADO', 'INTIMADO')"

    m: dict = {
        "remessas_recebidas_hoje": _um(
            con, "pt_remessas",
            "SELECT COUNT(*) FROM pt_remessas "
            "WHERE recebida_em >= %s AND recebida_em < %s", dia, ate),
        "titulos_sem_apontamento": _um(
            con, "pt_titulos",
            "SELECT COUNT(*) FROM pt_titulos WHERE situacao = 'RECEBIDO'"),
        "arquivos_trazidos_da_cra_hoje": _um(
            con, "audit_logs",
            "SELECT COUNT(*) FROM audit_logs "
            "WHERE action = 'cra_baixar' AND ts >= %s AND ts < %s", dia, ate),
        "abertos_sem_imagem": _um(
            con, ("pt_titulos", "attachments"),
            "SELECT COUNT(*) FROM pt_titulos t "
            "WHERE t.situacao IN ('RECEBIDO', 'APONTADO', 'INTIMADO') "
            "AND NOT EXISTS (SELECT 1 FROM attachments a "
            "WHERE a.entity_type = %s AND a.entity_id = t.id)",
            PIMG.ENTIDADE),
        "confirmacoes_hoje": _um(
            con, "pt_retornos", gerados.format(tipos=um_tipo),
            "SDTBFOCRT", dia, ate),
        "confirmacoes_aceitas_hoje": _um(
            con, "pt_retornos", aceitos.format(tipos=um_tipo),
            "SDTBFOCRT", dia, ate, AMBIENTE_DE_PRODUCAO),
        "confirmacoes_com_erro_hoje": _um(
            con, "pt_retornos", com_erro.format(tipos=um_tipo),
            "SDTBFOCRT", dia, ate),
        "apontados_sem_aviso": _um(
            con, ("pt_titulos", "pt_avisos"),
            "SELECT COUNT(*) FROM pt_titulos t WHERE t.situacao = 'APONTADO' "
            "AND NOT EXISTS (SELECT 1 FROM pt_avisos v "
            "WHERE v.titulo_id = t.id AND v.situacao <> 'CANCELADO')"),
        "avisos_esperando_entrega": _um(
            con, "pt_avisos",
            "SELECT COUNT(*) FROM pt_avisos WHERE situacao = 'EMITIDO'"),
        "avisos_esperando_edital": _um(
            con, "pt_avisos",
            "SELECT COUNT(*) FROM pt_avisos WHERE situacao = 'NAO_ENTREGUE'"),
        "abertos_sem_chave": _um(
            con, "pt_titulos",
            "SELECT COUNT(*) FROM pt_titulos "
            f"WHERE situacao IN {em_aberto} "
            "AND TRIM(COALESCE(chave_cenprot, '')) = ''"),
        "intimacoes_digitais_hoje": _um(
            con, "rs_intimacoes",
            "SELECT COUNT(*) FROM rs_intimacoes WHERE ambiente = %s "
            "AND enviada_em >= %s AND enviada_em < %s",
            AMBIENTE_DE_PRODUCAO, dia, ate),
        "desistencias_hoje": _um(
            con, "pt_desistencias",
            "SELECT COUNT(*) FROM pt_desistencias "
            "WHERE recebida_em >= %s AND recebida_em < %s", dia, ate),
        "desistencias_com_titulo_por_aplicar": _um(
            con, "pt_desistencias",
            "SELECT COUNT(*) FROM pt_desistencias WHERE aplicados < titulos"),
        "titulos_em_aberto": _um(
            con, "pt_titulos",
            f"SELECT COUNT(*) FROM pt_titulos WHERE situacao IN {em_aberto}"),
        "pagamentos_e_retiradas_hoje": _um(
            con, "pt_atos",
            "SELECT COUNT(*) FROM pt_atos "
            "WHERE tipo IN ('PAGAMENTO', 'DESISTENCIA') AND cancelado = 0 "
            "AND data_ato >= %s AND data_ato < %s", dia, ate),
        "retornos_e_andamentos_hoje": _um(
            con, "pt_retornos", gerados.format(tipos=dois_tipos),
            "SDTBFORTP", "SDTBFOAND", dia, ate),
        "retornos_e_andamentos_aceitos_hoje": _um(
            con, "pt_retornos", aceitos.format(tipos=dois_tipos),
            "SDTBFORTP", "SDTBFOAND", dia, ate, AMBIENTE_DE_PRODUCAO),
        "cenprot_esperando": _um(
            con, "cn_pendencias",
            "SELECT COUNT(*) FROM cn_pendencias WHERE ambiente = %s "
            f"AND situacao NOT IN ({marcas})",
            AMBIENTE_DE_PRODUCAO, *terminais),
        "pedidos_de_certidao_cenprot": _um(
            con, "cn_pendencias",
            "SELECT COUNT(*) FROM cn_pendencias WHERE ambiente = %s "
            f"AND especie = %s AND situacao NOT IN ({marcas})",
            AMBIENTE_DE_PRODUCAO, CERTIDAO, *terminais),
        "editais_hoje": _um(
            con, "pt_editais",
            "SELECT COUNT(*) FROM pt_editais WHERE publicado_em = %s", dia),
        "emolumentos_enviados_hoje": _um(
            con, "audit_logs",
            "SELECT COUNT(*) FROM audit_logs "
            "WHERE action = 'cenprot_custas_enviadas' "
            "AND ts >= %s AND ts < %s", dia, ate),
        "certidoes_hoje": _um(
            con, "pt_certidoes",
            "SELECT COUNT(*) FROM pt_certidoes WHERE cancelada = 0 "
            "AND emitida_em >= %s AND emitida_em < %s", dia, ate),
        "protestos_sem_instrumento": _um(
            con, ("pt_atos", "pt_instrumentos"),
            "SELECT COUNT(*) FROM pt_atos a WHERE a.tipo = 'PROTESTO' "
            "AND a.cancelado = 0 AND COALESCE(a.origem, '') <> 'EOFICIO' "
            "AND NOT EXISTS (SELECT 1 FROM pt_instrumentos i "
            "WHERE i.titulo_id = a.titulo_id)"),
    }
    # AS TRES LISTAS QUE TEM REGRA PROPRIA NAO SE RECONTAM AQUI: quem diz o
    # que e «sem movimentacao» e `protesto.esperando_protesto`, e quem diz o
    # que a CRA ainda nao sabe e `protesto_retorno.pendentes`. Uma segunda
    # consulta «parecida» divergiria no primeiro conserto.
    if _existe(con, "pt_titulos", "pt_atos", "pt_devedores"):
        m["a_protestar"] = len(PT.esperando_protesto(con, hoje=dia,
                                                     limite=100000))
        m["atos_esperando_retorno"] = len(PRE.pendentes(con))
        m["atos_esperando_andamento"] = len(PRE.pendentes(con,
                                                          tipo="SDTBFOAND"))
    else:
        m["a_protestar"] = None
        m["atos_esperando_retorno"] = None
        m["atos_esperando_andamento"] = None
    # A CONFERÊNCIA CENPROT × SISTEMA (29/10/2026) também tem regra própria —
    # o que diverge é `cenprot_conferencia.quadro`, e não uma contagem daqui.
    # Ela NÃO fala com a rede: compara a última resposta guardada.
    if _existe(con, "pt_titulos", "pt_atos", "pt_cenprot_xml",
               "cn_pendencias", "cn_conferencias", "cn_liquidacoes_portal"):
        import cenprot_conferencia as CCONF
        m["cenprot_divergencias"] = CCONF.quantos_divergem(con)
    else:
        m["cenprot_divergencias"] = None
    return m


def estado_do_envio(con: sqlite3.Connection) -> dict:
    """O que decide se a confirmacao e o andamento sobem sozinhos. SO LE.

    Dois fatos, e os dois mudam o que o escrevente tem de fazer a mao: a
    configuracao `cra_auto_enviar_producao` (padrao DESLIGADO, em
    `protesto_cra_envio.auto_envio_ligado`) e a credencial de producao de cada
    Central. `None` e «nao deu para ler», e a tela diz isso — nunca «nao».
    """
    ligado = None
    if _existe(con, "settings"):
        linha = banco(con).um("SELECT value FROM settings WHERE key = %s",
                              ("cra_auto_enviar_producao",))
        ligado = bool(linha) and str(linha["value"]) == "1"
    credenciais = {}
    try:
        import centrais_cred as CRED
        for nome, central in (("CRA", CRED.CRA), ("CENPROT", CRED.CENPROT),
                              ("Resolve", CRED.RESOLVE)):
            try:
                credenciais[nome] = bool(CRED.tem(central,
                                                  AMBIENTE_DE_PRODUCAO))
            except (ValueError, KeyError, OSError):
                credenciais[nome] = None
    except (ImportError, AttributeError):
        credenciais = {"CRA": None, "CENPROT": None, "Resolve": None}
    return {"cra_envio_automatico_producao": ligado,
            "credenciais_de_producao": credenciais}


def painel_do_dia(con: sqlite3.Connection, *, hoje: str) -> dict:
    """As etapas da rotina, cada uma com o botao, a hora e o que espera. SO LE.

    O resultado e para a tela: cada etapa leva as suas medidas ja com a frase,
    e o relogio do dia (os tres horarios da CRA) aponta para a etapa de cada um.
    """
    medido = medir_o_dia(con, hoje=hoje)
    horas = {h["o_que"]: h for h in HORARIOS_DA_CRA}
    etapas = []
    for e in ETAPAS_DO_DIA:
        linha = dict(e)
        linha["botoes"] = [dict(b) for b in e["botoes"]]
        h = horas.get(e.get("hora") or "")
        linha["hora_limite"] = h["hora"] if h else None
        linha["hora_quem"] = h["quem"] if h else None
        linha["contagens"] = [
            {"chave": k, "rotulo": MEDIDAS_DO_DIA[k], "valor": medido.get(k)}
            for k in e["medidas"]]
        etapas.append(linha)
    # O RELOGIO: os horarios da CRA, em ordem de hora, cada um com a etapa
    # dele. O retorno e o andamento tem a MESMA hora e a mesma etapa, e por
    # isso viram uma linha so — duas linhas «11:30» lado a lado pareceriam
    # dois passos. A hora continua saindo de HORARIOS_DA_CRA.
    etapa_da_hora = {"Envio de remessa": ("etapa-remessa", "Remessa do dia"),
                     "Envio de confirmacao": ("etapa-confirmacao",
                                              "Confirmação"),
                     "Envio de retorno": ("etapa-retorno", "Retorno"),
                     "Andamento": ("etapa-retorno", "Andamento")}
    juntos: dict = {}
    for h in HORARIOS_DA_CRA:
        ancora, nome = etapa_da_hora.get(h["o_que"], (None, h["o_que"]))
        item = juntos.setdefault((h["hora"], ancora), {
            "hora": h["hora"], "ancora": ancora, "nomes": [],
            "quem": h["quem"], "nosso": h["nosso"]})
        item["nomes"].append(nome)
    relogio = []
    for chave in sorted(juntos):
        item = juntos[chave]
        item["o_que"] = " e ".join(item.pop("nomes"))
        relogio.append(item)
    return {"etapas": etapas, "relogio": relogio,
            "estado": estado_do_envio(con)}
