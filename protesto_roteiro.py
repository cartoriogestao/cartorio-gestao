"""O ROTEIRO DAS CENTRAIS — o que a escrevente FAZ, e a cobrança de cada conduta.

DE ONDE VEIO
    Dois papeis que o oficial trouxe em 01/09/2026: o **ROTEIRO DAS CENTRAIS DE
    PROTESTO** (TJMA), com os QUATRO HORARIOS da CRA, e o **Oficio Circular
    IEPTB-MA/CRA-MA n. 015/2025**, que da o fundamento de quatro dos passos da
    CENPROT. Isto nao esta no acervo e nao se descobre medindo: a ORDEM e a HORA
    sao combinacao com a Central.

A ORDEM NOVA, DE 29/10/2026 — e ela inverte o que este modulo dizia de si
    Pedido do oficial: *«reestruturar o roteiro das centrais para ter apenas
    itens necessarios (tirar, por exemplo, a parte de baixar imagem, que ja vem
    com a remessa ou a confirmacao que ja vai automatica) e vincular a
    operacao. [...] vincular cada obrigacao a uma conduta, nao deixando a
    escrevente cometer erros. se insistir em algo que eh erro, precisa afirmar
    expressamente e deixar log.»*

    **ATE AQUI ESTE MODULO «CONTAVA E NAO JULGAVA»**, e havia teste que varria
    os nomes publicos procurando «atrasado» e «pendente» para garantir isso. A
    ordem nova e o contrario: **a obrigacao e cobrada.** Cada item do roteiro
    virou uma CONDUTA, com o botao que leva a tela que FAZ aquilo e uma
    situacao calculada do banco — FEITO, PENDENTE ou ATRASADO —, com o numero
    do que falta e a lista.

O QUE NAO MUDOU: SO SE DIZ «ATRASADO» SOBRE O QUE O BANCO PROVA
    O alarme que soa sempre continua sendo o defeito que era. Por isso:
      - **ATRASADO exige prazo**: so a obrigacao que tem hora do papel (11:30,
        14:10) ou prazo da norma (o triduo, o repasse no dia util seguinte, o
        arquivo diario da CENPROT) pode ficar atrasada. A que nao tem prazo
        escrito fica PENDENTE, e nunca vermelha;
      - **zero que pode ser «nada chegou» nao e atraso**: a remessa so fica
        atrasada quando o banco prova que NINGUEM consultou a CRA no dia, e a
        consulta pelo botao deixa rastro mesmo quando a CRA nao manda nada;
      - **o que o banco nao guarda nao se cobra como se guardasse**: a subida do
        XML diario no portal da CENPROT nao deixa prova aqui, e a conduta diz
        isso em vez de fingir que mediu;
      - `None` continua sendo «nao deu para medir» (a tabela nao existe nesta
        instalacao), e a obrigacao fica SEM_MEDIDA — nunca zero.

O QUE SAIU DO ROTEIRO, E A PROVA
    `FORA_DO_ROTEIRO`: o que o sistema faz sozinho, com a prova no codigo e a
    medicao na producao. **Nao se tira item por suposicao** — o que nao tem
    prova continua sendo conduta. E a excecao do automatico (o envio que
    falhou) continua cobrada, dentro da conduta da remessa.

O FECHAMENTO DO DIA, E O DIA SEGUINTE (acrescimo do oficial, 29/10/2026)
    *«garantir que todos processos sejam concluidos todos os dias; nao deixar
    margem para a escrevente esquecer ou fazer errado»*. A conduta 11, ENCERRAR
    O DIA, so se conclui com as outras feitas; o que ficar exige a afirmacao
    expressa de CADA item (`conferir_o_encerramento`), e o encerramento fica
    gravado (`pt_encerramentos_do_dia`) com o que estava pendente e o que se
    afirmou. No dia seguinte, `o_que_ficou` abre a tela com isso — e com o que
    esta atrasado agora —, sem depender da memoria de ninguem.

OS GANCHOS DAS OUTRAS PECAS (`GANCHOS`)
    As pendencias que os outros pedidos da reestruturacao medem (selo previo,
    situacao sem ato, prova da intimacao, conferencia CENPROT, titulos irmaos,
    protocolo repetido) entram nas condutas por import tolerante: peca ausente
    e a linha «ainda nao instalada», e nao erro.

ESTE MODULO SO GRAVA O ENCERRAMENTO — o resto ele COBRA. Nao gera arquivo, nao
lavra ato, nao marca passo como feito. Quem faz e a tela de cada botao; quem diz
se foi feito e o banco.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta

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


def _hora_do_papel(o_que: str) -> str:
    """A hora mora num lugar so — `HORARIOS_DA_CRA`."""
    return next(h["hora"] for h in HORARIOS_DA_CRA if h["o_que"] == o_que)


HORA_DO_RETORNO = _hora_do_papel("Envio de retorno")
HORA_DA_CONFIRMACAO = _hora_do_papel("Envio de confirmacao")
HORA_DA_REMESSA = _hora_do_papel("Envio de remessa")

#: A VIRADA DO PROTESTO: 14/10/2026, o primeiro dia operando em producao. O
#: arquivo gerado antes dela foi ensaio de homologacao, e nao e obrigacao de
#: hoje — sem este piso, os testes de setembro apareceriam como retorno atrasado
#: para sempre.
VIRADA_DO_PROTESTO = "2026-10-14"

#: O ambiente que os links pedem. Desde 14/10/2026 tudo e producao, e as telas
#: das Centrais ainda abrem na homologacao quando nao se diz qual — por isso o
#: roteiro DIZ. E o valor de `centrais_cred.PRODUCAO` (ha teste).
AMBIENTE_DE_PRODUCAO = "PRODUCAO"

# AS QUATRO SITUACOES DE UMA OBRIGACAO. As tres primeiras sao a ordem do
# oficial; a quarta e a regra antiga que continua valendo: «nao deu para medir»
# nao e zero.
FEITO = "FEITO"
PENDENTE = "PENDENTE"
ATRASADO = "ATRASADO"
SEM_MEDIDA = "SEM_MEDIDA"

ROTULO_DA_SITUACAO = {FEITO: "Feito", PENDENTE: "Pendente",
                      ATRASADO: "Atrasado", SEM_MEDIDA: "Sem como medir"}

#: Quantas linhas cada obrigacao mostra. O numero do que falta e sempre o
#: total; a lista e o comeco dela, com «e mais N» embaixo.
LINHAS_NA_LISTA = 15

# ------------------------------------------------------------------ o PAPEL

# OS DEZESSEIS PASSOS DO PAPEL CONTINUAM AQUI, COMO FONTE — e cada um diz para
# onde foi: `conduta` (a chave da conduta que o cobra) ou `fora` (a chave de
# `FORA_DO_ROTEIRO`, quando o sistema faz sozinho). Passo sem nenhum dos dois
# seria passo esquecido, e ha teste que recusa.
#
# `tela` e o endpoint; `None` quer dizer «o sistema nao faz isto», e `onde` diz
# onde se faz. NAO SE INVENTA TELA: apontar para uma tela parecida faria o
# escrevente dar o passo por feito sem te-lo feito.
ROTEIRO_DA_CRA = (
    {"passo": "Recebimento de remessa",
     "tela": "protesto_remessas", "conduta": "remessa",
     "nota": "conferir e receber sao dois passos, e o primeiro nao grava nada"},
    {"passo": "Confirmacao de remessa",
     "tela": "protesto_remessas", "fora": "confirmacao",
     "nota": "sai sozinha ao receber o lote — uma por apresentante — e sobe "
             "pela API; a que falhar e cobrada na conduta da remessa"},
    {"passo": "Envio do retorno",
     "tela": "protesto_retornos", "conduta": "retorno",
     "nota": "ate as 11:30"},
    {"passo": "Envio do arquivo de andamento",
     "tela": "protesto_retornos", "conduta": "retorno",
     "nota": "SEMPRE QUE GERAR RETORNO, GERAR ANDAMENTO — o par sai junto. O "
             "andamento do apontamento, que sai ao receber a remessa, e "
             "automatico"},
    {"passo": "Recebimento de pedidos de desistencia",
     "tela": "protesto_desistencias", "conduta": "pedidos_cra",
     "nota": "conferir tres vezes por dia: protestar titulo de que o credor "
             "desistiu e o erro que menos se desfaz"},
    {"passo": "Recebimento de pedidos de cancelamento",
     "tela": "protesto_cra_api", "conduta": "pedidos_cra",
     "onde": "no site da CRA, ou pela API",
     "nota": "MEDIDO: dos 54 cancelamentos que esta casa lavrou, 2 vieram "
             "pela Central — a anuencia do credor chega ao balcao. O arquivo "
             "se TRAZ pela API, e vem CRU"},
    {"passo": "Recebimento de pedidos de autorizacao de cancelamento (AC)",
     "tela": "protesto_cra_api", "conduta": "pedidos_cra",
     "onde": "no site da CRA, ou pela API",
     "nota": "MEDIDO: 2 titulos de 1.370. A consulta de uma autorizacao MARCA "
             "como baixada na Central salvo se se disser que nao"},
    {"passo": "Geracao de boleto de repasse dos titulos pagos "
              "(apresentantes IEPTB-MA, ex.: SEFAZ-MA)",
     "tela": "protesto_repasses", "conduta": "repasse",
     "onde": "a guia e emitida pelo IEPTB; aqui se registra cada passo",
     "nota": "o dinheiro do titulo pago e do apresentante no primeiro dia "
             "util seguinte (Lei 9.492/1997, art. 19, § 2º; CN-MA art. 929)"},
)

# ------------------------------------------------------------------ a CENPROT

# O FUNDAMENTO de cada um veio do Oficio Circular 015/2025 do IEPTB-MA. Onde
# ele nao cita norma, o campo fica vazio — e nao se preenche por semelhanca.
ROTEIRO_DA_CENPROT = (
    {"passo": "Recebimento de remessa (menu Gestao de Pedidos)",
     "tela": "protesto_pendencias", "conduta": "cenprot",
     "onde": "no site da CENPROT, menu Gestao de Pedidos",
     "nota": "o pedido vem pela API (`/pedidos/consulta`) e se protocola por "
             "ela (`/pedidos/protocolar`)"},
    {"passo": "Envio do arquivo XML diario dos apontados e suas ocorrencias",
     "tela": "protesto_cenprot_xml", "conduta": "xml",
     "onde": "gera aqui; sobe no site da CENPROT",
     "norma": "art. 4o da Resolucao n. 1 do IEPTB-BR",
     "nota": "o sistema GERA o P (protestos) e o D (pagos, retirados e "
             "cancelados); o ENVIO e pelo portal — a API da CENPROT nao tem "
             "caminho para este arquivo"},
    {"passo": "Envio do instrumento de protesto eletronico",
     "tela": "protesto_instrumentos", "conduta": "instrumentos",
     "onde": "dentro do arquivo P, no site da CENPROT",
     "norma": "art. 11 da Resolucao n. 1 do IEPTB-BR",
     "nota": "o instrumento ASSINADO com o A3 vai DENTRO do arquivo P, em "
             "base64. Protesto sem instrumento assinado nao entra no P"},
    {"passo": "Recebimento de pedido de certidao eletronica de protesto",
     "tela": "protesto_pendencias", "conduta": "cenprot",
     "onde": "o PEDIDO chega pela API, em Pendencias da CENPROT",
     "nota": "a certidao se emite aqui, e o orcamento sobe pela API"},
    {"passo": "Recebimento dos pedidos de anuencia",
     "tela": "protesto_pendencias", "conduta": "cenprot",
     "onde": "no site da CENPROT",
     "nota": "a aprovacao e AUTOMATICA por meio do arquivo de emolumentos — "
             "e por isso mandar o arquivo em dia faz diferenca aqui"},
    {"passo": "Recebimento de pedido de cancelamento",
     "tela": "protesto_pendencias", "conduta": "cenprot",
     "onde": "no site da CENPROT",
     "nota": "o ato de cancelamento se lavra na ficha do titulo; a tela "
             "apenas INFORMA a Central do que ja foi lavrado"},
    {"passo": "Envio do edital eletronico",
     "tela": "protesto_avisos", "conduta": "editais",
     "norma": "art. 15, § 1o, da Lei 9.492/1997, e Resolucao n. 8 do IEPTB-BR",
     "nota": "o arquivo sai do que ja foi PUBLICADO no dia; a prova do envio "
             "e o comprovante anexado ao dia (CN-MA art. 922, § 1o)"},
    {"passo": "Envio do arquivo de emolumentos",
     "tela": "protesto_cenprot", "conduta": "cenprot",
     "norma": "Resolucao n. 9 de 2024",
     "nota": "os dois valores que o devedor paga para retirar e para cancelar; "
             "o mesmo arquivo sobe pela API, pelo botao «Enviar a CENPROT pela "
             "API»"},
)

# O QUE SO O TABELIAO OU O SUBSTITUTO FAZ, e o papel diz com essas palavras.
SO_O_TABELIAO = (
    ("Cadastro de usuario na CENPROT e na CRA — o Tabeliao ou Substituto "
     "deve faze-lo."),
)

# CADA FONTE ENTRE PARENTESES, e nao pela quebra de linha solta: sem eles o
# Python junta duas linhas vizinhas numa string so, e a lista perde uma fonte
# sem erro nenhum.
FONTES = (
    ("ROTEIRO DAS CENTRAIS DE PROTESTO (TJMA), trazido pelo oficial em "
     "01/09/2026"),
    ("Oficio Circular IEPTB-MA/CRA-MA n. 015/2025, de 28/03/2025 — "
     "«Rotina de Alimentacao da CENPROT»"),
    ("Pedido do oficial em 29/10/2026: so o que a escrevente faz, cada "
     "obrigacao ligada a uma conduta, e a insistencia no erro afirmada "
     "expressamente e registrada"),
)

# ------------------------------------------------------- o que saiu do roteiro

# O QUE O SISTEMA FAZ SOZINHO — e por isso nao e conduta de ninguem. Cada um
# com a prova no CODIGO e a medicao na PRODUCAO (so leitura, 29/10/2026). O
# que nao tinha prova ficou no roteiro.
FORA_DO_ROTEIRO = (
    {"chave": "imagens",
     "o_que": "Baixar e guardar as imagens dos títulos",
     "por_que": ("A imagem vem junto com a remessa: o botão «Trazer e "
                 "conferir» pede a imagem à CRA, e o recebimento a anexa ao "
                 "título na mesma transação. Quando a CRA não manda imagem, "
                 "não há o que baixar à parte."),
     "codigo": ("templates/protesto_remessas.html manda com_imagem=1; "
                "cra21_api pede downloadImagem=1; protesto_remessa.receber_xml "
                "chama protesto_cra_imagens.anexar na mesma transação dos "
                "títulos"),
     "medido": ("Produção, 29/10/2026: as remessas da virada para cá entraram "
                "pela CRA em XML; a tela de subir o .zip das imagens nunca foi "
                "usada (o único anexo de título é a imagem de um pedido da "
                "CENPROT). A tela continua no menu, para o caso de exceção.")},
    {"chave": "confirmacao",
     "o_que": "Enviar a confirmação da remessa (até 14:10)",
     "por_que": ("A confirmação nasce ao receber a remessa e sobe sozinha pela "
                 "API, logo depois, quando o envio automático de produção está "
                 "ligado. A que NÃO subir continua cobrada na conduta da "
                 "remessa, com a hora das 14:10."),
     "codigo": ("protesto_remessa_receber gera a confirmação na mesma "
                "transação; protesto_cra_envio.enviar_pos_remessa a envia "
                "quando cra_auto_enviar_producao = 1"),
     "medido": ("Produção, 29/10/2026: cra_auto_enviar_producao = 1; as 3 "
                "remessas recebidas desde 14/10 geraram 3 confirmações, e as 3 "
                "entraram na CRA pelo envio automático (CRA_ENVIO), nenhuma "
                "pelo botão.")},
    {"chave": "andamento_da_remessa",
     "o_que": "Enviar o andamento do apontamento (o que sai ao receber a remessa)",
     "por_que": ("Ele é gerado ao receber a remessa e sobe pela API logo depois "
                 "da confirmação. O andamento EM PAR COM O RETORNO continua "
                 "conduta, junto com o retorno; e o apontamento que ficar sem "
                 "andamento é cobrado lá."),
     "codigo": ("protesto_remessa_receber chama protesto_retorno."
                "gerar_andamento; enviar_pos_remessa o manda depois da "
                "confirmação"),
     "medido": ("Produção, 29/10/2026: os 4 andamentos gerados ao receber "
                "remessa desde 14/10 entraram na CRA pelo envio automático.")},
)

# ------------------------------------------------------------------ as CONDUTAS

# A ORDEM DO DIA, do jeito que deve ser feito. Cada conduta e UMA coisa que a
# escrevente faz, com o botao que leva a tela que FAZ aquilo; as obrigacoes de
# cada uma sao medidas em `cobrar_o_dia`. `hora` aponta para HORARIOS_DA_CRA
# pelo nome — o horario mora num lugar so.
#
# AS OBRIGACOES QUE CAUSARAM OS ERROS DE OUTUBRO ESTAO AQUI COM NOME: o edital
# sem o comprovante do envio a CENPROT (36 editais de 07 a 27/10, nenhum com
# comprovante — medido em 29/10/2026), a entrega sem comprovante, o protesto
# sem instrumento (21 protestos lavrados neste sistema, nenhum instrumento
# emitido) e o XML P que por isso nao saiu.
CONDUTAS_DO_DIA: tuple[dict, ...] = (
    {"n": 1, "chave": "retorno", "ancora": "conduta-retorno",
     "titulo": "Retorno e andamento à CRA",
     "hora": "Envio de retorno",
     "conduta": ("Gere o retorno (o andamento sai em par) e envie pelo botão "
                 "«Enviar à CRA», em «Arquivos gerados», até as 11:30."),
     "botoes": ({"rotulo": "Gerar e enviar o retorno",
                 "tela": "protesto_retornos", "args": {}},)},
    {"n": 2, "chave": "remessa", "ancora": "conduta-remessa",
     "titulo": "Trazer e receber a remessa da CRA",
     "hora": "Envio de confirmacao",
     "conduta": ("Traga a remessa pelo botão «Trazer e conferir» (a CRA a "
                 "disponibiliza às 12:30), confira e receba: cada título é "
                 "apontado, e a confirmação e o andamento sobem sozinhos. O "
                 "que não subir, envie até as 14:10."),
     "botoes": ({"rotulo": "Trazer e receber a remessa",
                 "tela": "protesto_remessas", "args": {}},)},
    {"n": 3, "chave": "pedidos_cra", "ancora": "conduta-pedidos-cra",
     "titulo": "Desistências e pedidos da CRA",
     "hora": None,
     "conduta": ("Traga as desistências pela API e aplique-as ANTES de lavrar "
                 "qualquer protesto (o papel manda conferir três vezes por "
                 "dia); consulte também os cancelamentos e as autorizações."),
     "botoes": ({"rotulo": "Conferir e aplicar desistências",
                 "tela": "protesto_desistencias", "args": {}},
                {"rotulo": "Trazer da CRA pela API",
                 "tela": "protesto_cra_api", "args": {}})},
    {"n": 4, "chave": "entregas", "ancora": "conduta-entregas",
     "titulo": "Entrega do aviso só com o comprovante",
     "hora": None,
     "conduta": ("Registre a entrega do aviso e anexe, no mesmo dia, o "
                 "comprovante assinado (o canhoto escaneado). A intimação "
                 "pessoal só se comprova com ele (CN-MA art. 921)."),
     "botoes": ({"rotulo": "Avisos entregues e comprovantes",
                 "tela": "protesto_avisos", "args": {}, "ancora": "entregues"},)},
    {"n": 5, "chave": "editais", "ancora": "conduta-editais",
     "titulo": "Edital: publicar, subir na CENPROT e anexar o comprovante",
     "hora": None,
     "conduta": ("Publique o edital dos avisos não entregues, gere o arquivo "
                 "do edital do dia, suba-o no portal da CENPROT e anexe o "
                 "comprovante do envio ao dia — no mesmo dia (CN-MA art. 922, "
                 "§ 1º)."),
     "botoes": ({"rotulo": "Editais e comprovante do envio",
                 "tela": "protesto_avisos", "args": {},
                 "ancora": "envio-do-edital"},)},
    {"n": 6, "chave": "protestos", "ancora": "conduta-protestos",
     "titulo": "Lavrar os protestos do dia",
     "hora": None,
     "conduta": ("Depois de aplicar as desistências, lavre os protestos cujo "
                 "tríduo vence hoje; o que passou do prazo se lavra com o "
                 "motivo do atraso escrito (CN-MA art. 913, § 1º)."),
     "botoes": ({"rotulo": "Lavrar os protestos",
                 "tela": "protesto_a_protestar", "args": {}},)},
    {"n": 7, "chave": "instrumentos", "ancora": "conduta-instrumentos",
     "titulo": "Emitir e assinar os instrumentos",
     "hora": None,
     "conduta": ("Emita o instrumento de cada protesto lavrado e assine com o "
                 "A3 no mesmo dia: sem o instrumento assinado o protesto não "
                 "entra no XML P."),
     "botoes": ({"rotulo": "Emitir e assinar instrumentos",
                 "tela": "protesto_instrumentos", "args": {}},)},
    {"n": 8, "chave": "xml", "ancora": "conduta-xml",
     "titulo": "XML diário P e D à CENPROT",
     "hora": None,
     "conduta": ("Gere o XML P (protestos) e o D (pagos, retirados e "
                 "cancelados) e suba os dois no portal da CENPROT no mesmo dia "
                 "(art. 4º da Resolução n. 1 do IEPTB-BR)."),
     "botoes": ({"rotulo": "Gerar o XML P e D",
                 "tela": "protesto_cenprot_xml", "args": {}},)},
    {"n": 9, "chave": "cenprot", "ancora": "conduta-cenprot",
     "titulo": "Responder à CENPROT",
     "hora": None,
     "conduta": ("Baixe e responda as pendências da CENPROT — pedidos de "
                 "protesto, anuências, cancelamentos, certidões — e envie o "
                 "arquivo de emolumentos pela API depois de cada protesto novo."),
     "botoes": ({"rotulo": "Pendências da CENPROT",
                 "tela": "protesto_pendencias",
                 "args": {"ambiente": AMBIENTE_DE_PRODUCAO}},
                {"rotulo": "Emolumentos e chave única",
                 "tela": "protesto_cenprot", "args": {}})},
    {"n": 10, "chave": "repasse", "ancora": "conduta-repasse",
     "titulo": "Repasse ao apresentante",
     "hora": None,
     "conduta": ("Ponha à disposição do apresentante o valor do título pago "
                 "no primeiro dia útil seguinte ao pagamento: pela guia do "
                 "IEPTB (título da CRA ou da CENPROT) ou direto (título do "
                 "balcão)."),
     "botoes": ({"rotulo": "Repasses ao apresentante",
                 "tela": "protesto_repasses", "args": {}},)},
    # O FECHAMENTO DO DIA (29/10/2026) — acrescimo do oficial: «garantir que
    # todos processos sejam concluidos todos os dias; nao deixar margem para a
    # escrevente esquecer ou fazer errado». So se conclui com as outras dez
    # FEITAS; o que ficar exige afirmacao expressa POR ITEM, e o dia seguinte
    # abre mostrando isso primeiro.
    {"n": 11, "chave": "encerrar", "ancora": "conduta-encerrar",
     "titulo": "Encerrar o dia",
     "hora": None,
     "conduta": ("No fim do expediente, encerre o dia no fim desta página. Ele "
                 "só se encerra com as outras condutas feitas; o que ficar "
                 "exige a sua afirmação expressa, item por item, e aparece "
                 "primeiro no roteiro do dia seguinte. Encerre também o termo "
                 "diário do Livro de Protocolo, quando ele estiver aberto no "
                 "núcleo."),
     "botoes": ({"rotulo": "Encerrar o dia",
                 "tela": "protesto_painel", "args": {},
                 "ancora": "encerrar-o-dia"},
                {"rotulo": "Termo diário do Livro de Protocolo",
                 "tela": "nucleo_encerramento_diario", "args": {}})},
)

# ------------------------------------------- os ganchos das outras pecas

# AS PENDENCIAS QUE AS OUTRAS PECAS DA REESTRUTURACAO DE 29/10/2026 MEDEM. Cada
# uma mora no modulo dela, e o roteiro so as LE — por import tolerante: modulo
# ou funcao que ainda nao existe no main vira a linha «ainda nao instalada», e
# nao erro, para este roteiro nao depender da ordem em que os pedidos entram.
#
# A FUNCAO RECEBE `con` E DEVOLVE O QUE TEM: um numero (quantos), ou uma lista
# de linhas (dicionarios com `titulo_id`, `protocolo`, `numero_titulo`,
# `explicacao`/`texto`/`motivo`). Linha com `origem = 'ACERVO'` nao entra: o
# acervo nao vira trabalho de hoje. NENHUM GANCHO TEM PRAZO AQUI — quem sabe
# o prazo e a peca dele; o roteiro cobra como pendente.
#
# `nome_a_confirmar`: o nome do modulo e da funcao foi escrito antes de a peca
# existir no main; quando ela entrar com outro nome, corrige-se aqui, numa
# linha so — e ate la a linha diz «ainda nao instalada», que e a verdade.
GANCHOS: tuple[dict, ...] = (
    {"chave": "atos_sem_selo", "conduta": "protestos",
     "rotulo": "atos que esperam o selo (selo prévio)",
     "modulo": "protesto_selo_previo", "funcao": "pendencias_do_selo",
     "de_onde": "PR #103, o selo conferido antes de lavrar"},
    {"chave": "situacao_sem_ato", "conduta": "protestos",
     "rotulo": "títulos cuja situação não tem o ato que a sustente",
     "modulo": "protesto_selo_previo",
     "funcao": "titulos_sem_ato_que_sustente",
     "de_onde": "PR #103, a situação sem ato"},
    {"chave": "intimacao_sem_prova", "conduta": "entregas",
     "rotulo": "intimações sem a prova que o protesto exige",
     "modulo": "protesto_prova", "funcao": "intimacoes_sem_prova",
     "de_onde": "PR #106, a trava do protesto pela prova da intimação"},
    {"chave": "cenprot_diverge", "conduta": "cenprot",
     "rotulo": "títulos em que a CENPROT e o sistema divergem",
     "modulo": "cenprot_conferencia", "funcao": "quantos_divergem",
     "tela": "protesto_cenprot_conferencia",
     "de_onde": "PR #105, a conferência CENPROT × sistema"},
    {"chave": "titulos_irmaos", "conduta": "remessa",
     "rotulo": "títulos irmãos a conferir",
     "modulo": "protesto_titulos_irmaos", "funcao": "pendencias_dos_irmaos",
     "de_onde": "a conferência dos títulos irmãos",
     "nome_a_confirmar": True},
    {"chave": "protocolo_repetido", "conduta": "retorno",
     "rotulo": "atos do retorno com protocolo repetido",
     "modulo": "protesto_retorno", "funcao": "protocolos_repetidos_na_fila",
     "de_onde": "o retorno com protocolo repetido",
     "nome_a_confirmar": True},
)


# ------------------------------------------------------------------ medir


def _um(con: sqlite3.Connection, tabela: str | tuple, sql: str,
        *args) -> int | None:
    """Conta. Devolve `None` — e nao zero — quando a TABELA nao existe aqui.

    **E ELE SO PERDOA A TABELA QUE FALTA, e nada mais.** A primeira versao
    tinha `except sqlite3.Error: return 0`, e isso escondeu um defeito no mesmo
    minuto: `recebido_em` onde a coluna se chama **`recebida_em`**, e o guarda
    largo devolvia **zero com cara de medicao**. Coluna errada **estoura**.
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


# A LINHA QUE MARCA A VIRADA DO PROTESTO NAO E ARQUIVO (protesto_retorno.
# _registro_do_eoficio): ela traz `cra_enviado_ambiente = 'EOFICIO'`.
_NAO_E_A_VIRADA = "COALESCE(cra_enviado_ambiente, '') <> 'EOFICIO'"


def _instante(texto) -> datetime | None:
    """`2026-10-29T11:00:00`, `2026-10-29 11:00` ou `2026-10-29`."""
    s = str(texto or "").strip().replace(" ", "T")[:19]
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _dia(texto) -> date | None:
    try:
        return date.fromisoformat(str(texto or "")[:10])
    except ValueError:
        return None


def _br(texto) -> str:
    """`2026-10-29T11:05:00` -> `29/10 11:05`; so a data -> `29/10/2026`."""
    s = str(texto or "")
    d = _dia(s)
    if d is None:
        return s or "—"
    if len(s) > 10 and s[10] in "T " and len(s) >= 16:
        return f"{d:%d/%m} {s[11:16]}"
    return f"{d:%d/%m/%Y}"


def _as(dia: date, hora: str) -> datetime:
    h, m = (int(x) for x in hora.split(":"))
    return datetime.combine(dia, time(h, m))


def _feriados(con) -> set[date]:
    """Os feriados locais da casa — a mesma lista do triduo e do aviso."""
    from ri_schema import ler_feriados_locais
    if not _existe(con, "settings"):
        return set()
    linha = banco(con).um("SELECT value FROM settings WHERE key = %s",
                          ("ri_feriados_locais",))
    return ler_feriados_locais(((linha or {}).get("value")) or "")


def _contexto(con, agora: str) -> dict:
    """O instante da cobranca e o que se calcula uma vez so a partir dele."""
    from ri_schema import eh_dia_util
    instante = _instante(agora)
    if instante is None:
        raise ValueError(f"Instante invalido para cobrar o dia: {agora!r}.")
    feriados = _feriados(con)
    hoje = instante.date()
    return {"agora": instante, "hoje": hoje, "dia": hoje.isoformat(),
            "ate": hoje.isoformat() + "~", "feriados": feriados,
            "dia_util": eh_dia_util(hoje, feriados)}


def _util_seguinte(dia: date, ctx: dict) -> date:
    from ri_schema import soma_dias_uteis
    return soma_dias_uteis(dia, 1, ctx["feriados"])


def _item(texto: str, *, quando=None, prazo: datetime | None, ctx: dict,
          tela: str | None = None, args: dict | None = None) -> dict:
    """Uma linha da lista do que falta. `prazo` None = sem prazo provado."""
    return {"texto": texto, "quando": _br(quando) if quando else "",
            "prazo": (f"{prazo:%d/%m %H:%M}" if prazo is not None else ""),
            "atrasado": prazo is not None and ctx["agora"] > prazo,
            "tela": tela, "args": dict(args or {})}


def _obrigacao(chave: str, rotulo: str, itens: list[dict] | None, *,
               regra: str, tem_prazo: bool, motivo: str = "",
               feito: str = "", nota: str = "",
               quantos: int | None = None) -> dict:
    """A obrigacao pronta para a tela, com a situacao calculada.

    `itens` None e «nao deu para medir»; lista vazia e «nada falta» — medido.
    **SEM PRAZO NAO HA ATRASO** (`tem_prazo=False`): a obrigacao que o papel e
    a norma nao datam fica PENDENTE, e o vermelho e reservado ao que o banco
    prova que passou da hora.
    """
    if itens is None:
        return {"chave": chave, "rotulo": rotulo, "regra": regra,
                "situacao": SEM_MEDIDA, "faltam": None, "atrasados": 0,
                "lista": [], "mais": 0, "motivo": motivo, "feito": "",
                "nota": nota}
    if not tem_prazo:
        for i in itens:
            i["atrasado"] = False
    atrasados = sum(1 for i in itens if i["atrasado"])
    # OS ATRASADOS VEM PRIMEIRO: e o que a escrevente tem de fazer antes.
    ordem = sorted(itens, key=lambda i: not i["atrasado"])
    situacao = (ATRASADO if atrasados else PENDENTE if itens else FEITO)
    # `quantos`: quando a fonte so diz o numero (uma linha na lista, «N
    # titulos — abra a tela»), o que falta e o numero, e nao a linha.
    return {"chave": chave, "rotulo": rotulo, "regra": regra,
            "situacao": situacao,
            "faltam": (int(quantos) if quantos is not None and itens
                       else len(itens)),
            "atrasados": atrasados, "lista": ordem[:LINHAS_NA_LISTA],
            "mais": max(0, len(itens) - LINHAS_NA_LISTA), "motivo": motivo,
            "feito": feito if not itens else "", "nota": nota}


def _sem_tabela(chave: str, rotulo: str, regra: str, *tabelas: str) -> dict:
    return _obrigacao(chave, rotulo, None, regra=regra, tem_prazo=False,
                      motivo=("nesta instalação não existe "
                              + ", ".join(tabelas)))


def _auditoria_do_dia(con, ctx: dict, *acoes: str) -> list[dict]:
    """As linhas de auditoria de hoje destas acoes, com os detalhes lidos."""
    if not _existe(con, "audit_logs"):
        return []
    marcas = ", ".join(["%s"] * len(acoes))
    saida = []
    for linha in banco(con).ler(
            f"""SELECT ts, action, details FROM audit_logs
                 WHERE action IN ({marcas}) AND ts >= %s AND ts < %s
                 ORDER BY ts""", (*acoes, ctx["dia"], ctx["ate"])):
        try:
            detalhe = json.loads(linha["details"] or "{}")
        except (TypeError, ValueError):
            detalhe = {}
        saida.append({"ts": str(linha["ts"]), "action": linha["action"],
                      "detalhe": detalhe if isinstance(detalhe, dict) else {}})
    return saida


def _titulo_do_ato(a: dict) -> str:
    return (f"título {a.get('numero_titulo') or '—'}, protocolo "
            f"{a.get('protocolo') or '—'}")


# ------------------------------------------------- 1. retorno e andamento


def _atos_sem_arquivo_da_cra(con, ctx: dict, *, tipo: str, chave: str,
                             rotulo: str) -> dict:
    """Os atos que a CRA ainda nao sabe — a fila de `protesto_retorno`.

    O PRAZO: o ato lavrado num dia vai no arquivo ate as 11:30 do dia UTIL
    SEGUINTE. E a leitura mais folgada do papel (que so diz a hora): ela nunca
    chama de atrasado o que uma leitura mais estrita ainda daria por no prazo.
    """
    regra = (f"o ato lavrado num dia vai à CRA até as {HORA_DO_RETORNO} do dia "
             f"útil seguinte")
    if not _existe(con, "pt_titulos", "pt_atos"):
        return _sem_tabela(chave, rotulo, regra, "pt_titulos", "pt_atos")
    import protesto_retorno as PRE
    itens = []
    for a in PRE.pendentes(con, tipo=tipo):
        a = dict(a)
        d = _dia(a.get("data_ato"))
        prazo = _as(_util_seguinte(d, ctx), HORA_DO_RETORNO) if d else None
        itens.append(_item(
            f"{str(a.get('tipo') or '').lower()} — {_titulo_do_ato(a)} "
            f"(apresentante {a.get('apresentante_codigo') or '—'})",
            quando=a.get("data_ato"), prazo=prazo, ctx=ctx,
            tela="protesto_titulo", args={"titulo_id": a["titulo_id"]}))
    return _obrigacao(chave, rotulo, itens, regra=regra, tem_prazo=True,
                      feito="nenhum ato esperando arquivo")


def _arquivos_nao_aceitos(con, ctx: dict, *, tipos: tuple[str, ...],
                          hora: str, mesmo_dia: bool, chave: str,
                          rotulo: str) -> dict:
    """Os arquivos gerados desde a virada que a CRA ainda nao aceitou.

    `mesmo_dia`: a confirmacao vence as 14:10 do dia em que nasceu; o retorno e
    o andamento, as 11:30 — do mesmo dia se gerados antes disso, senao do dia
    util seguinte. O arquivo RECUSADO cujos atos ja voltaram a fila nao conta
    aqui: quem o cobra e a fila dos atos.
    """
    regra = (f"o arquivo gerado tem de entrar na CRA até as {hora}"
             + (" do dia em que nasceu" if mesmo_dia else ""))
    if not _existe(con, "pt_retornos"):
        return _sem_tabela(chave, rotulo, regra, "pt_retornos")
    bd = banco(con)
    marcas = ", ".join(["%s"] * len(tipos))
    tem_recusa = bd.tem_coluna("pt_retornos", "cra_recusado_em")
    sem_recusa_resolvida = (
        " AND NOT (r.cra_recusado_em IS NOT NULL AND NOT EXISTS ("
        "SELECT 1 FROM pt_atos a WHERE a.retorno_id = r.id))"
        if tem_recusa and _existe(con, "pt_atos") else "")
    # O ARQUIVO DE TITULO QUE NAO VEIO DA CRA NAO E OBRIGACAO COM A CRA
    # (21/10/2026): o retorno RTAB2110.261 levava o pagamento de um titulo da
    # Gestao de Pedidos da CENPROT, e a CRA o recusa para sempre (codigo 2154,
    # «sequencial remessa nao foi encontrado»). Esse pagamento vai pelo XML D;
    # cobra-lo aqui seria o aviso sem saida.
    so_da_cra = (
        " AND NOT EXISTS (SELECT 1 FROM pt_atos a JOIN pt_titulos t "
        "ON t.id = a.titulo_id WHERE a.retorno_id = r.id "
        "AND COALESCE(t.origem, '') <> 'CRA')"
        if _existe(con, "pt_atos", "pt_titulos") else "")
    coluna_recusa = ("r.cra_recusado_em" if tem_recusa else "NULL")
    linhas = bd.ler(
        f"""SELECT r.id, r.tipo, r.nome_arquivo, r.gerado_em,
                   r.apresentante_codigo, r.cra_envio_erro,
                   {coluna_recusa} AS recusado_em
              FROM pt_retornos r
             WHERE r.tipo IN ({marcas}) AND r.cra_enviado_em IS NULL
               AND COALESCE(r.cra_enviado_ambiente, '') <> 'EOFICIO'
               AND r.gerado_em >= %s{sem_recusa_resolvida}{so_da_cra}
             ORDER BY r.id""", (*tipos, VIRADA_DO_PROTESTO))
    itens = []
    for r in linhas:
        r = dict(r)
        nasceu = _instante(r.get("gerado_em"))
        prazo = None
        if nasceu is not None:
            limite = _as(nasceu.date(), hora)
            if not mesmo_dia and nasceu > limite:
                limite = _as(_util_seguinte(nasceu.date(), ctx), hora)
            prazo = limite
        porque = ("recusado pela CRA — devolva os atos à fila e gere de novo"
                  if r.get("recusado_em")
                  else "o envio falhou" if str(r.get("cra_envio_erro") or "").strip()
                  else "não enviado")
        itens.append(_item(
            f"{r.get('nome_arquivo') or '#' + str(r['id'])} — apresentante "
            f"{r.get('apresentante_codigo') or '—'} ({porque})",
            quando=r.get("gerado_em"), prazo=prazo, ctx=ctx,
            tela="protesto_retornos"))
    return _obrigacao(chave, rotulo, itens, regra=regra, tem_prazo=True,
                      feito="todos os arquivos gerados entraram na CRA")


def _cobrar_retorno(con, ctx: dict) -> list[dict]:
    return [
        _atos_sem_arquivo_da_cra(
            con, ctx, tipo="SDTBFORTP", chave="atos_sem_retorno",
            rotulo="atos lavrados que a CRA ainda não sabe (retorno)"),
        _atos_sem_arquivo_da_cra(
            con, ctx, tipo="SDTBFOAND", chave="apontamentos_sem_andamento",
            rotulo="apontamentos que ainda não saíram num andamento"),
        _arquivos_nao_aceitos(
            con, ctx, tipos=("SDTBFORTP", "SDTBFOAND"), hora=HORA_DO_RETORNO,
            mesmo_dia=False, chave="retornos_nao_aceitos",
            rotulo="retornos e andamentos gerados e não aceitos pela CRA"),
    ]


# ------------------------------------------------------------- 2. a remessa


#: As consultas que provam que a escrevente foi buscar a remessa: o botao
#: «Trazer e conferir» e a tela da API. As duas gravam auditoria MESMO QUANDO
#: a CRA nao devolve nada — e por isso o zero aqui nao e «nada chegou».
ACOES_DA_CONSULTA_DA_REMESSA = ("cra_baixar_e_conferir", "cra_baixar")
O_QUE_E_REMESSA = ("remessa", "pendentes")


def _remessa_do_dia(con, ctx: dict) -> dict:
    """Foi buscar a remessa hoje? A unica obrigacao que se prova pela CONSULTA.

    FEITO quando ha remessa recebida hoje ou consulta a CRA registrada hoje.
    Sem nenhuma das duas: PENDENTE, e ATRASADO so depois das 14:10 de dia util
    — a confirmacao do dia vence nessa hora, e o banco prova que ninguem foi
    buscar. Sabado, domingo e feriado nunca ficam atrasados.
    """
    chave, rotulo = "remessa_do_dia", "a remessa do dia foi trazida da CRA"
    regra = (f"a CRA disponibiliza às {HORA_DA_REMESSA}; a confirmação vence "
             f"às {HORA_DA_CONFIRMACAO}")
    recebidas = _um(con, "pt_remessas",
                    "SELECT COUNT(*) FROM pt_remessas "
                    "WHERE recebida_em >= %s AND recebida_em < %s",
                    ctx["dia"], ctx["ate"])
    if recebidas is None:
        return _sem_tabela(chave, rotulo, regra, "pt_remessas")
    consultas = [x for x in _auditoria_do_dia(
        con, ctx, *ACOES_DA_CONSULTA_DA_REMESSA)
        if str(x["detalhe"].get("o_que") or "") in O_QUE_E_REMESSA]
    if recebidas:
        return _obrigacao(chave, rotulo, [], regra=regra, tem_prazo=True,
                          feito=f"{recebidas} remessa(s) recebida(s) hoje")
    if consultas:
        return _obrigacao(
            chave, rotulo, [], regra=regra, tem_prazo=True,
            feito=(f"a CRA foi consultada {len(consultas)} vez(es) hoje, a "
                   f"última às {consultas[-1]['ts'][11:16]}; nenhuma remessa "
                   f"recebida"))
    prazo = (_as(ctx["hoje"], HORA_DA_CONFIRMACAO) if ctx["dia_util"]
             else None)
    return _obrigacao(chave, rotulo, [_item(
        "ninguém trouxe a remessa da CRA hoje", prazo=prazo, ctx=ctx,
        tela="protesto_remessas")], regra=regra, tem_prazo=prazo is not None)


def _titulos_sem_apontamento(con, ctx: dict) -> dict:
    """Titulo recebido e nao apontado: Lei 9.492/1997, art. 5º — 24 horas."""
    chave, rotulo = "titulos_sem_apontamento", "títulos recebidos e não apontados"
    regra = ("o título se protocoliza em 24 horas (Lei 9.492/1997, art. 5º): "
             "até a mesma hora do dia útil seguinte")
    if not _existe(con, "pt_titulos"):
        return _sem_tabela(chave, rotulo, regra, "pt_titulos")
    itens = []
    for t in banco(con).ler(
            """SELECT id, numero_titulo, protocolo, criado_em FROM pt_titulos
                WHERE situacao = 'RECEBIDO' ORDER BY id"""):
        t = dict(t)
        entrou = _instante(t.get("criado_em"))
        prazo = (datetime.combine(_util_seguinte(entrou.date(), ctx),
                                  entrou.time()) if entrou else None)
        itens.append(_item(_titulo_do_ato(t), quando=t.get("criado_em"),
                           prazo=prazo, ctx=ctx, tela="protesto_titulo",
                           args={"titulo_id": t["id"]}))
    return _obrigacao(chave, rotulo, itens, regra=regra, tem_prazo=True,
                      feito="todo título recebido está apontado")


def _cobrar_remessa(con, ctx: dict) -> list[dict]:
    return [
        _remessa_do_dia(con, ctx),
        _titulos_sem_apontamento(con, ctx),
        # A EXCECAO DO AUTOMATICO: a confirmacao que nao subiu sozinha. E por
        # ela que o passo saiu do roteiro sem sair da cobranca.
        _arquivos_nao_aceitos(
            con, ctx, tipos=("SDTBFOCRT",), hora=HORA_DA_CONFIRMACAO,
            mesmo_dia=True, chave="confirmacoes_nao_aceitas",
            rotulo="confirmações que não entraram na CRA (o envio automático "
                   "falhou ou está desligado)"),
    ]


# ------------------------------------------------- 3. desistencias e pedidos

ACOES_DA_CONSULTA_A_CRA = ("cra_baixar",)
O_QUE_E_DESISTENCIA = ("desistencias",)
O_QUE_E_CANCELAMENTO = ("cancelamentos", "autorizacoes", "ordem")


def _desistencias_por_aplicar(con, ctx: dict) -> list[dict]:
    """O arquivo de desistencia com titulo ainda nao aplicado. Sem prazo no
    papel — pendente, e nunca vermelho: o que fica atrasado e o protesto
    lavrado antes da conferencia, cobrado ao lado."""
    chave, rotulo = ("desistencias_por_aplicar",
                     "arquivos de desistência com título ainda não aplicado")
    regra = "aplicar antes de lavrar o protesto do título"
    if not _existe(con, "pt_desistencias"):
        return [_sem_tabela(chave, rotulo, regra, "pt_desistencias")]
    itens = [_item(
        f"{r['nome_arquivo'] or 'arquivo #' + str(r['id'])} — "
        f"{r['aplicados']} de {r['titulos']} aplicados",
        quando=r["recebida_em"], prazo=None, ctx=ctx,
        tela="protesto_desistencia", args={"desistencia_id": r["id"]})
        for r in banco(con).ler(
            """SELECT id, nome_arquivo, titulos, aplicados, recebida_em
                 FROM pt_desistencias WHERE aplicados < titulos
                ORDER BY id""")]
    return [_obrigacao(chave, rotulo, itens, regra=regra, tem_prazo=False,
                       feito="toda desistência recebida foi aplicada")]


def _cobrar_pedidos_da_cra(con, ctx: dict) -> list[dict]:
    """Desistencia ANTES do protesto — e e isso que o banco consegue provar.

    A CONSULTA DE DESISTENCIA FICA ATRASADA EM UM CASO SO: houve protesto
    lavrado hoje e nenhuma consulta de desistencia antes dele. E exatamente o
    erro que o papel manda evitar conferindo tres vezes por dia.
    """
    saida = []
    if not _existe(con, "audit_logs"):
        # SEM A AUDITORIA NAO HA PROVA DA CONSULTA — nem de que houve, nem de
        # que nao houve. «Ninguem conferiu» seria afirmar o que nao se mediu.
        return [
            _sem_tabela("consulta_de_desistencia",
                        "as desistências foram conferidas hoje",
                        "a desistência se confere antes de lavrar protesto",
                        "audit_logs"),
            *_desistencias_por_aplicar(con, ctx),
            _sem_tabela("consulta_de_cancelamento",
                        "cancelamentos e autorizações (AC) consultados na CRA "
                        "hoje", "o papel lista o passo sem hora",
                        "audit_logs")]
    consultas = _auditoria_do_dia(con, ctx, *ACOES_DA_CONSULTA_A_CRA)
    de_desistencia = [x["ts"] for x in consultas
                      if x["detalhe"].get("o_que") in O_QUE_E_DESISTENCIA]
    if _existe(con, "pt_desistencias"):
        de_desistencia += [str(r["recebida_em"]) for r in banco(con).ler(
            """SELECT recebida_em FROM pt_desistencias
                WHERE recebida_em >= %s AND recebida_em < %s""",
            (ctx["dia"], ctx["ate"]))]
    de_desistencia.sort()
    primeiro_protesto = None
    if _existe(con, "pt_atos"):
        linha = banco(con).um(
            """SELECT MIN(data_ato) AS primeiro FROM pt_atos
                WHERE tipo = 'PROTESTO' AND cancelado = 0
                  AND COALESCE(origem, '') <> 'EOFICIO'
                  AND data_ato >= %s AND data_ato < %s""",
            (ctx["dia"], ctx["ate"]))
        primeiro_protesto = (linha or {}).get("primeiro")
    regra = ("a desistência se confere antes de lavrar protesto — o papel manda "
             "três vezes por dia")
    # A ORDEM SO SE PROVA QUANDO O PROTESTO TEM HORA. `data_ato` so com a data
    # (o caso do acervo e de teste antigo) nao diz se veio antes ou depois da
    # conferencia — e o que nao se prova nao vira atraso.
    primeiro = str(primeiro_protesto or "")
    com_hora = len(primeiro) > 10
    antes = [ts for ts in de_desistencia if not com_hora or ts < primeiro]
    if com_hora and not antes:
        lavrado = _instante(primeiro)
        saida.append(_obrigacao(
            "consulta_de_desistencia", "as desistências foram conferidas hoje",
            [_item(f"o primeiro protesto de hoje ({primeiro[11:16]}) foi "
                   f"lavrado antes de qualquer conferência de desistência",
                   prazo=lavrado - timedelta(seconds=1) if lavrado else None,
                   ctx=ctx, tela="protesto_cra_api")],
            regra=regra, tem_prazo=True))
    elif de_desistencia:
        saida.append(_obrigacao(
            "consulta_de_desistencia", "as desistências foram conferidas hoje",
            [], regra=regra, tem_prazo=True,
            feito=(f"{len(de_desistencia)} conferência(s) hoje, a última às "
                   f"{de_desistencia[-1][11:16] or '—'} (o papel manda três)")))
    else:
        saida.append(_obrigacao(
            "consulta_de_desistencia", "as desistências foram conferidas hoje",
            [_item("ninguém conferiu as desistências hoje", prazo=None, ctx=ctx,
                   tela="protesto_cra_api")],
            regra=regra, tem_prazo=False))

    saida += _desistencias_por_aplicar(con, ctx)

    cancelamento = [x["ts"] for x in consultas
                    if x["detalhe"].get("o_que") in O_QUE_E_CANCELAMENTO]
    saida.append(_obrigacao(
        "consulta_de_cancelamento",
        "cancelamentos e autorizações (AC) consultados na CRA hoje",
        [] if cancelamento else [_item(
            "ninguém consultou cancelamentos nem autorizações hoje",
            prazo=None, ctx=ctx, tela="protesto_cra_api")],
        regra="o papel lista o passo sem hora", tem_prazo=False,
        feito=(f"consultados às {cancelamento[-1][11:16]}" if cancelamento
               else "")))
    return saida


# ---------------------------------------------------------- 4. as entregas


def _cobrar_entregas(con, ctx: dict) -> list[dict]:
    """Entrega registrada sem o comprovante anexado. CN-MA art. 921.

    O aviso trazido do E-Oficio nao entra: o papel dele e do arquivo do
    sistema antigo (`protesto_aviso.entregues` faz o mesmo corte).
    """
    chave, rotulo = ("entregas_sem_comprovante",
                     "entregas registradas sem o comprovante anexado")
    regra = "o comprovante se anexa no dia em que a entrega é registrada"
    if not _existe(con, "pt_avisos", "pt_titulos", "attachments"):
        return [_sem_tabela(chave, rotulo, regra, "pt_avisos", "attachments")]
    import protesto_aviso as AV
    bd = banco(con)
    fora = ("AND COALESCE(a.origem, '') <> 'EOFICIO'"
            if bd.tem_coluna("pt_avisos", "origem") else "")
    itens = []
    for a in bd.ler(
            f"""SELECT a.id, a.numero, a.ano, a.entrega_em, a.titulo_id,
                       t.numero_titulo, t.protocolo
                  FROM pt_avisos a JOIN pt_titulos t ON t.id = a.titulo_id
                 WHERE a.situacao = 'ENTREGUE' {fora}
                   AND NOT EXISTS (SELECT 1 FROM attachments x
                                    WHERE x.entity_type = %s
                                      AND x.entity_id = a.id)
                 ORDER BY a.id""", (AV.ENTIDADE_DO_COMPROVANTE,)):
        a = dict(a)
        d = _dia(a.get("entrega_em"))
        prazo = _as(d, "23:59") if d else None
        itens.append(_item(
            f"aviso {a.get('numero')}/{a.get('ano')} — {_titulo_do_ato(a)}",
            quando=a.get("entrega_em"), prazo=prazo, ctx=ctx,
            tela="protesto_titulo", args={"titulo_id": a["titulo_id"]}))
    return [_obrigacao(chave, rotulo, itens, regra=regra, tem_prazo=True,
                       feito="toda entrega registrada tem comprovante")]


# ------------------------------------------------------------ 5. os editais


def _cobrar_editais(con, ctx: dict) -> list[dict]:
    """Edital publicado -> arquivo do dia -> CENPROT -> comprovante anexado.

    O ERRO DE OUTUBRO: 36 editais publicados de 07 a 27/10/2026 e NENHUM com o
    comprovante do envio a CENPROT (medido em 29/10). O CN-MA art. 922, § 1º,
    manda afixar e PUBLICAR na CENPROT, e o protesto conta da publicacao.
    """
    saida = []
    chave, rotulo = ("avisos_esperando_edital",
                     "avisos não entregues esperando o edital")
    regra = "o aviso não entregue vai a edital"
    if not _existe(con, "pt_avisos", "pt_titulos"):
        saida.append(_sem_tabela(chave, rotulo, regra, "pt_avisos"))
    else:
        itens = [_item(f"aviso {a['numero']}/{a['ano']} — {_titulo_do_ato(a)}",
                       quando=a["entrega_em"], prazo=None, ctx=ctx,
                       tela="protesto_titulo",
                       args={"titulo_id": a["titulo_id"]})
                 for a in banco(con).ler(
                     """SELECT a.id, a.numero, a.ano, a.entrega_em,
                               a.titulo_id, t.numero_titulo, t.protocolo
                          FROM pt_avisos a
                          JOIN pt_titulos t ON t.id = a.titulo_id
                         WHERE a.situacao = 'NAO_ENTREGUE'
                           AND t.situacao IN ('APONTADO', 'INTIMADO')
                         ORDER BY a.id""")]
        saida.append(_obrigacao(chave, rotulo, itens, regra=regra,
                                tem_prazo=False,
                                feito="nenhum aviso esperando edital"))

    chave, rotulo = ("editais_sem_comprovante",
                     "dias com edital publicado sem o comprovante do envio à "
                     "CENPROT")
    regra = ("o arquivo do edital sobe à CENPROT e o comprovante se anexa no "
             "dia da publicação (CN-MA art. 922, § 1º)")
    if not _existe(con, "pt_editais", "attachments"):
        saida.append(_sem_tabela(chave, rotulo, regra, "pt_editais"))
        return saida
    import protesto_aviso as AV
    gerados = set()
    if _existe(con, "audit_logs"):
        desde = (ctx["hoje"] - timedelta(days=AV.DIAS_DO_QUADRO_DE_ENVIO + 1))
        for linha in banco(con).ler(
                """SELECT details FROM audit_logs
                    WHERE action = 'PROTESTO_CENPROT_EDITAL' AND ts >= %s""",
                (desde.isoformat(),)):
            try:
                gerados.add(str(json.loads(linha["details"] or "{}")
                                .get("dia") or "")[:10])
            except (TypeError, ValueError, AttributeError):
                continue
    itens = []
    for d in AV.envios_do_edital(con, ctx["dia"]):
        if d["completo"]:
            continue
        dia = _dia(d["dia"])
        itens.append(_item(
            f"{_br(d['dia'])}: {d['com_comprovante']} de {d['editais']} "
            f"edital(is) com comprovante; arquivo do dia "
            f"{'gerado' if d['dia'] in gerados else 'NÃO gerado'}",
            quando=d["dia"], prazo=_as(dia, "23:59") if dia else None,
            ctx=ctx, tela="protesto_avisos"))
    saida.append(_obrigacao(chave, rotulo, itens, regra=regra, tem_prazo=True,
                            feito="todo dia com edital tem o comprovante"))
    return saida


# ----------------------------------------------------------- 6. os protestos


def _cobrar_protestos(con, ctx: dict) -> list[dict]:
    """O triduo de cada intimado sem movimentacao — a conta de `protesto_triduo`.

    Entra o que vence HOJE (no prazo) e o que JA VENCEU; o que ainda esta no
    prazo do devedor nao entra, porque protestar antes seria o erro do outro
    lado. Sem conta (falta um fato), entra como pendente, dizendo o que falta.
    """
    chave, rotulo = ("protestos_do_dia",
                     "intimados com o tríduo vencendo hoje ou já vencido")
    regra = ("o protesto se lavra no dia útil seguinte ao prazo-limite do "
             "devedor (CN-MA art. 913)")
    if not _existe(con, "pt_titulos", "pt_atos", "pt_devedores"):
        return [_sem_tabela(chave, rotulo, regra, "pt_titulos", "pt_atos")]
    import protesto as PT
    import protesto_triduo as TRI
    itens = []
    for linha in PT.esperando_protesto(con, hoje=ctx["dia"], limite=100000):
        conta = TRI.contar(con, int(linha["id"]), feriados=ctx["feriados"])
        onde = TRI.situacao(conta, ctx["dia"])
        if onde == TRI.ANTES:
            continue
        prazo = None
        texto = _titulo_do_ato(linha)
        if onde == TRI.SEM_CONTA:
            texto += f" — o sistema não contou o tríduo: {conta.get('sem_conta')}"
        else:
            final = _dia(conta.get("termo_final"))
            prazo = _as(final, "23:59") if final else None
            texto += f" — tríduo até {_br(conta.get('termo_final'))}"
        itens.append(_item(texto, quando=linha.get("data_da_intimacao"),
                           prazo=prazo, ctx=ctx, tela="protesto_titulo",
                           args={"titulo_id": linha["id"]}))
    return [_obrigacao(chave, rotulo, itens, regra=regra, tem_prazo=True,
                       feito="nenhum protesto vence hoje")]


# --------------------------------------------------------- 7. os instrumentos


def _cobrar_instrumentos(con, ctx: dict) -> list[dict]:
    """Protesto sem instrumento, e instrumento sem assinatura.

    O instrumento ASSINADO vai dentro do XML P (art. 11 da Resolucao n. 1 do
    IEPTB-BR), e o XML e diario: o do protesto de ontem ja devia ter saido.
    """
    saida = []
    regra = ("o instrumento assinado vai no XML P do dia do protesto (arts. 4º "
             "e 11 da Resolução n. 1 do IEPTB-BR)")
    chave, rotulo = ("protestos_sem_instrumento",
                     "protestos lavrados neste sistema sem instrumento")
    if not _existe(con, "pt_atos", "pt_titulos", "pt_instrumentos"):
        saida.append(_sem_tabela(chave, rotulo, regra, "pt_instrumentos"))
    else:
        itens = []
        for a in banco(con).ler(
                """SELECT a.id, a.data_ato, a.titulo_id, t.numero_titulo,
                          t.protocolo
                     FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
                    WHERE a.tipo = 'PROTESTO' AND a.cancelado = 0
                      AND COALESCE(a.origem, '') <> 'EOFICIO'
                      AND NOT EXISTS (SELECT 1 FROM pt_instrumentos i
                                       WHERE i.titulo_id = a.titulo_id)
                    ORDER BY a.data_ato, a.id"""):
            a = dict(a)
            d = _dia(a.get("data_ato"))
            itens.append(_item(
                _titulo_do_ato(a), quando=a.get("data_ato"),
                prazo=_as(d, "23:59") if d else None, ctx=ctx,
                tela="protesto_titulo", args={"titulo_id": a["titulo_id"]}))
        saida.append(_obrigacao(chave, rotulo, itens, regra=regra,
                                tem_prazo=True,
                                feito="todo protesto tem instrumento"))

    chave, rotulo = ("instrumentos_sem_assinatura",
                     "instrumentos emitidos e ainda não assinados")
    if not _existe(con, "pt_instrumentos", "as_documentos"):
        saida.append(_sem_tabela(chave, rotulo, regra, "as_documentos"))
    else:
        import protesto_instrumento as PI
        itens = []
        for i in PI.a_assinar(con, limite=100000):
            i = dict(i)
            d = _dia(i.get("emitido_em"))
            itens.append(_item(
                f"instrumento {i.get('numero')}/{i.get('ano')} — protocolo "
                f"{i.get('protocolo') or '—'}", quando=i.get("emitido_em"),
                prazo=_as(d, "23:59") if d else None, ctx=ctx,
                tela="protesto_instrumentos"))
        saida.append(_obrigacao(chave, rotulo, itens, regra=regra,
                                tem_prazo=True,
                                feito="todo instrumento emitido está assinado"))
    return saida


# ----------------------------------------------------------------- 8. o XML


def _cobrar_xml(con, ctx: dict) -> list[dict]:
    """Os atos deste sistema que ainda nao foram para um XML P ou D.

    A SUBIDA NO PORTAL NAO DEIXA PROVA NO BANCO: o arquivo gerado fica gravado
    (`pt_cenprot_xml`), e o envio e pelo portal, sem comprovante anexado. O que
    se cobra e o que o banco prova — o ato sem arquivo —, e a nota diz o resto.
    """
    chave, rotulo = ("atos_sem_xml",
                     "atos lavrados neste sistema que ainda não foram num XML")
    regra = ("o XML é diário: o ato do dia vai no arquivo do mesmo dia (art. 4º "
             "da Resolução n. 1 do IEPTB-BR)")
    if not _existe(con, "pt_atos", "pt_titulos", "pt_cenprot_xml") or \
            not banco(con).tem_coluna("pt_atos", "cenprot_xml_id"):
        return [_sem_tabela(chave, rotulo, regra, "pt_cenprot_xml")]
    import protesto_cenprot_xml as PCXML
    letra_do_ato = {tipo: letra for letra, tipos in PCXML.ATOS_DA_LETRA.items()
                    for tipo in tipos}
    marcas = ", ".join(["%s"] * len(letra_do_ato))
    itens = []
    for a in banco(con).ler(
            f"""SELECT a.id, a.tipo, a.data_ato, a.titulo_id,
                       t.numero_titulo, t.protocolo
                  FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
                 WHERE a.tipo IN ({marcas}) AND a.cancelado = 0
                   AND a.cenprot_xml_id IS NULL
                   AND COALESCE(a.origem, '') <> 'EOFICIO'
                 ORDER BY a.data_ato, a.id""", tuple(letra_do_ato)):
        a = dict(a)
        d = _dia(a.get("data_ato"))
        itens.append(_item(
            f"XML {letra_do_ato.get(a['tipo'], '?')} — "
            f"{str(a['tipo']).lower()}, {_titulo_do_ato(a)}",
            quando=a.get("data_ato"), prazo=_as(d, "23:59") if d else None,
            ctx=ctx, tela="protesto_titulo", args={"titulo_id": a["titulo_id"]}))
    gerados = _um(con, "pt_cenprot_xml",
                  "SELECT COUNT(*) FROM pt_cenprot_xml WHERE dia = %s",
                  ctx["dia"])
    return [_obrigacao(
        chave, rotulo, itens, regra=regra, tem_prazo=True,
        feito="todo ato lavrado já foi num XML",
        nota=(f"{gerados or 0} arquivo(s) gerado(s) hoje. A subida no portal "
              f"da CENPROT não deixa prova neste sistema: confira lá."))]


# ------------------------------------------------------------- 9. a CENPROT


def _cobrar_cenprot(con, ctx: dict) -> list[dict]:
    """O que a CENPROT mandou e espera resposta, e os emolumentos.

    Nenhum dos dois tem hora no papel: ficam PENDENTES, e nunca vermelhos.
    """
    saida = []
    chave, rotulo = ("cenprot_esperando",
                     "pendências da CENPROT esperando resposta (produção)")
    regra = "o papel lista os pedidos sem hora"
    if not _existe(con, "cn_pendencias"):
        saida.append(_sem_tabela(chave, rotulo, regra, "cn_pendencias"))
    else:
        from cn_schema import NOME_DA_ESPECIE, SITUACOES_TERMINAIS
        terminais = sorted(SITUACOES_TERMINAIS)
        marcas = ", ".join(["%s"] * len(terminais))
        itens = [_item(
            f"{NOME_DA_ESPECIE.get(p['especie'], p['especie'])} "
            f"{p['codigo']} — {str(p['situacao']).lower()}",
            quando=p["baixada_em"], prazo=None, ctx=ctx,
            tela="protesto_pendencia", args={"pendencia_id": p["id"]})
            for p in banco(con).ler(
                f"""SELECT id, especie, codigo, situacao, baixada_em
                      FROM cn_pendencias
                     WHERE ambiente = %s AND situacao NOT IN ({marcas})
                     ORDER BY id""", (AMBIENTE_DE_PRODUCAO, *terminais))]
        saida.append(_obrigacao(chave, rotulo, itens, regra=regra,
                                tem_prazo=False,
                                feito="nada da CENPROT esperando resposta"))

    chave, rotulo = ("emolumentos",
                     "protestos com chave lavrados depois do último envio do "
                     "arquivo de emolumentos pela API")
    regra = ("a anuência se aprova pelo arquivo de emolumentos (Resolução n. 9 "
             "de 2024)")
    if not _existe(con, "pt_titulos", "pt_atos", "audit_logs"):
        saida.append(_sem_tabela(chave, rotulo, regra, "audit_logs"))
        return saida
    ultimo = banco(con).um(
        """SELECT MAX(ts) AS ultimo FROM audit_logs
            WHERE action = 'cenprot_custas_enviadas'""")
    ultimo = str((ultimo or {}).get("ultimo") or "")
    itens = [_item(_titulo_do_ato(t), quando=t["data_ato"], prazo=None,
                   ctx=ctx, tela="protesto_titulo", args={"titulo_id": t["id"]})
             for t in banco(con).ler(
                 """SELECT t.id, t.numero_titulo, t.protocolo,
                           MAX(a.data_ato) AS data_ato
                      FROM pt_titulos t JOIN pt_atos a ON a.titulo_id = t.id
                     WHERE t.situacao = 'PROTESTADO'
                       AND TRIM(COALESCE(t.chave_cenprot, '')) <> ''
                       AND a.tipo = 'PROTESTO' AND a.cancelado = 0
                       AND COALESCE(a.origem, '') <> 'EOFICIO'
                       AND a.data_ato > %s
                     GROUP BY t.id, t.numero_titulo, t.protocolo
                     ORDER BY t.id""", (ultimo,))]
    saida.append(_obrigacao(
        chave, rotulo, itens, regra=regra, tem_prazo=False,
        feito="o último arquivo de emolumentos já leva todo protesto com chave",
        nota=("último envio pela API: " + (_br(ultimo) if ultimo else
                                           "nenhum registrado"))))
    return saida


# ------------------------------------------------------------- 10. o repasse


def _cobrar_repasse(con, ctx: dict) -> list[dict]:
    """O pagamento sem repasse — a fila de `protesto_repasse`, com o prazo dela."""
    chave, rotulo = ("repasses", "pagamentos ainda sem repasse ao apresentante")
    regra = ("o valor fica à disposição do apresentante no primeiro dia útil "
             "seguinte (Lei 9.492/1997, art. 19, § 2º)")
    if not _existe(con, "pt_atos", "pt_titulos", "pt_repasses"):
        return [_sem_tabela(chave, rotulo, regra, "pt_repasses")]
    import protesto_repasse as REP
    itens = []
    for p in REP.pendentes(con, hoje=ctx["dia"], feriados=ctx["feriados"]):
        prazo_dia = _dia(p.get("prazo"))
        itens.append(_item(
            f"{_titulo_do_ato(p)} — pago em {_br(p.get('recebido_em'))}, "
            f"repasse até {_br(p.get('prazo'))} ({p.get('canal')})",
            quando=p.get("data_ato"),
            prazo=_as(prazo_dia, "23:59") if prazo_dia else None, ctx=ctx,
            tela="protesto_repasses"))
    return [_obrigacao(chave, rotulo, itens, regra=regra, tem_prazo=True,
                       feito="todo pagamento tem repasse")]


# ------------------------------------------------------- 11. encerrar o dia

#: A serie do Livro de Protocolo do Protesto no nucleo (`livro_nucleo`).
SERIE_DO_PROTOCOLO = "PT_PROTOCOLO"
#: Quantos dias para tras se procura dia sem encerramento. Mais que isso e
#: outra conversa — e a lista que nao cabe na tela ja e outro problema.
DIAS_PARA_TRAS = 30


def encerramento_do_dia(con, dia: str) -> dict | None:
    """O encerramento gravado daquele dia, com as listas lidas. SO LE."""
    if not _existe(con, "pt_encerramentos_do_dia"):
        return None
    linha = banco(con).um(
        "SELECT * FROM pt_encerramentos_do_dia WHERE dia = %s",
        (str(dia)[:10],))
    return _encerramento_lido(linha)


def _encerramento_lido(linha) -> dict | None:
    if not linha:
        return None
    e = dict(linha)
    for campo in ("pendencias_json", "afirmacoes_json"):
        try:
            e[campo[:-5]] = json.loads(e.get(campo) or "[]")
        except (TypeError, ValueError):
            e[campo[:-5]] = []
    return e


def _dia_util_anterior(dia: date, ctx: dict) -> date:
    from ri_schema import eh_dia_util
    anterior = dia - timedelta(days=1)
    for _ in range(DIAS_PARA_TRAS):
        if eh_dia_util(anterior, ctx["feriados"]):
            break
        anterior -= timedelta(days=1)
    return anterior


def _cobrar_encerramento(con, ctx: dict) -> list[dict]:
    """O termo do livro de protocolo, os dias que ficaram sem fechar e hoje.

    O TERMO DIARIO DO NUCLEO E OUTRA COISA, E ENTRA COMO ITEM: aquele e ato
    escrito no Livro de Protocolo (`escrituracao.encerrar_o_dia`), e este e a
    conferencia do dia de trabalho. Medido na producao em 29/10/2026: o Livro
    de Protocolo do Protesto NUNCA foi aberto no nucleo (zero livros
    `PT_PROTOCOLO`, zero termos diarios) — e por isso, sem livro, o item diz
    «nao se aplica», em vez de cobrar termo de livro que a casa nao usa.
    """
    saida = []
    chave, rotulo = ("termo_do_protocolo",
                     "dias com movimento no Livro de Protocolo sem o termo "
                     "de encerramento diário")
    regra = "o livro diário se encerra no dia (Lei 9.492/1997, art. 33)"
    if not _existe(con, "nu_livros", "nu_encerramentos_diarios"):
        saida.append(_sem_tabela(chave, rotulo, regra, "nu_livros"))
    elif not banco(con).um("SELECT 1 AS um FROM nu_livros WHERE serie = %s "
                           "LIMIT 1", (SERIE_DO_PROTOCOLO,)):
        saida.append(_obrigacao(
            chave, rotulo, None, regra=regra, tem_prazo=False,
            motivo=("não se aplica: o Livro de Protocolo do Protesto não está "
                    "aberto no núcleo")))
    else:
        import escrituracao as ESC
        itens = []
        for dia in ESC.dias_sem_encerrar(con, SERIE_DO_PROTOCOLO):
            d = _dia(dia)
            itens.append(_item(f"termo diário de {_br(dia)}", quando=dia,
                               prazo=_as(d, "23:59") if d else None, ctx=ctx,
                               tela="nucleo_encerramento_diario"))
        saida.append(_obrigacao(chave, rotulo, itens, regra=regra,
                                tem_prazo=True,
                                feito="todo dia com movimento tem termo"))

    chave, rotulo = ("dias_sem_encerramento",
                     "dias de expediente que ficaram sem encerrar o roteiro")
    regra = ("todo dia de expediente se encerra; conta a partir do último "
             "encerramento gravado")
    if not _existe(con, "pt_encerramentos_do_dia"):
        saida.append(_sem_tabela(chave, rotulo, regra,
                                 "pt_encerramentos_do_dia"))
        saida.append(_sem_tabela("dia_encerrado", "o dia de hoje foi encerrado",
                                 "", "pt_encerramentos_do_dia"))
        return saida
    from ri_schema import eh_dia_util
    hoje = encerramento_do_dia(con, ctx["dia"])
    linha = banco(con).um(
        "SELECT MAX(dia) AS ultimo FROM pt_encerramentos_do_dia WHERE dia < %s",
        (ctx["dia"],))
    ultimo = _dia((linha or {}).get("ultimo"))
    # SEM NENHUM ENCERRAMENTO GRAVADO NAO HA DIA ATRASADO: a obrigacao nasce
    # com o primeiro. Cobrar os dias de antes dela seria o alarme do primeiro
    # dia da instalacao, sobre um dever que ainda nao existia. E O DIA DE HOJE,
    # JA ENCERRADO, COBRIU OS DE ANTES: para encerrar, cada um deles foi
    # afirmado — esta lista estava entre as pendencias.
    itens = []
    if ultimo is not None and not hoje:
        d = max(ultimo + timedelta(days=1),
                ctx["hoje"] - timedelta(days=DIAS_PARA_TRAS))
        while d < ctx["hoje"]:
            if eh_dia_util(d, ctx["feriados"]):
                itens.append(_item(f"{_br(d.isoformat())} não foi encerrado",
                                   quando=d.isoformat(),
                                   prazo=_as(d, "23:59"), ctx=ctx,
                                   tela="protesto_painel"))
            d += timedelta(days=1)
    saida.append(_obrigacao(
        chave, rotulo, itens, regra=regra, tem_prazo=True,
        feito=("nenhum dia ficou sem encerrar" if ultimo or hoje
               else "nenhum encerramento gravado ainda — a conta começa no "
                    "primeiro")))

    saida.append(_obrigacao(
        "dia_encerrado", "o dia de hoje foi encerrado",
        [] if hoje else [_item("o dia de hoje ainda não foi encerrado",
                               prazo=None, ctx=ctx, tela="protesto_painel")],
        regra="no fim do expediente", tem_prazo=False,
        feito=(f"encerrado por {hoje.get('encerrado_por') or '—'} às "
               f"{str(hoje.get('encerrado_em') or '')[11:16]}"
               + (f", com {hoje.get('pendencias')} item(ns) afirmado(s)"
                  if hoje.get("pendencias") else ", com tudo feito")
               if hoje else "")))
    return saida


# --------------------------------------------------- os ganchos, lidos


def _desfazer_a_leitura(con) -> None:
    """Depois de uma consulta que estourou, a transacao de leitura do
    PostgreSQL fica abortada, e a proxima consulta tambem estouraria. So se
    desfaz LEITURA aqui: os ganchos rodam fora de qualquer escrita."""
    desfazer = getattr(con, "rollback", None)
    if callable(desfazer):
        desfazer()


def _itens_do_gancho(achado, g: dict, ctx: dict) -> tuple[list | None, int | None]:
    """O que a peca devolveu, como linhas do roteiro. (None, None) quando a
    forma nao e nenhuma das combinadas — e a linha diz isso."""
    if isinstance(achado, bool):
        achado = int(achado)
    if isinstance(achado, int):
        if not achado:
            return [], None
        return [_item(f"{achado} — abra a tela para ver quais", prazo=None,
                      ctx=ctx, tela=g.get("tela"))], achado
    if isinstance(achado, dict):
        achado = (achado.get("linhas") or achado.get("itens")
                  or achado.get("lista") or [])
    if not isinstance(achado, (list, tuple)):
        return None, None
    itens = []
    for linha in achado:
        if not isinstance(linha, dict):
            itens.append(_item(str(linha), prazo=None, ctx=ctx))
            continue
        if str(linha.get("origem") or "").upper() == "ACERVO":
            continue
        partes = [p for p in (
            (f"título {linha['numero_titulo']}" if linha.get("numero_titulo")
             else ""),
            (f"protocolo {linha['protocolo']}" if linha.get("protocolo")
             else ""),
            str(linha.get("explicacao") or linha.get("texto")
                or linha.get("motivo") or "")) if p]
        tid = linha.get("titulo_id")
        itens.append(_item(" — ".join(partes) or json.dumps(
            linha, ensure_ascii=False, default=str)[:200], prazo=None, ctx=ctx,
            tela="protesto_titulo" if tid else g.get("tela"),
            args={"titulo_id": tid} if tid else None))
    return itens, None


def _rodar_gancho(con, ctx: dict, g: dict) -> dict:
    """Le a pendencia de outra peca. Ausente = «ainda nao instalada»."""
    import importlib
    regra = f"medido por {g['de_onde']}"
    try:
        modulo = importlib.import_module(g["modulo"])
    except ImportError:
        modulo = None
    funcao = getattr(modulo, g["funcao"], None) if modulo else None
    if not callable(funcao):
        return _obrigacao(
            g["chave"], g["rotulo"], None, regra=regra, tem_prazo=False,
            motivo=(f"ainda não instalada ({g['de_onde']}: "
                    f"{g['modulo']}.{g['funcao']})"))
    # O GANCHO QUE ESTOURA NAO DERRUBA O ROTEIRO: ele vira «nao respondeu»,
    # com o erro a vista — nunca zero. E a peca de outro pedido, e o roteiro
    # inteiro fora do ar por causa dela seria o balcao sem roteiro nenhum.
    try:
        achado = funcao(con)
    except Exception as erro:  # noqa: BLE001 — o motivo vai a tela
        _desfazer_a_leitura(con)
        return _obrigacao(
            g["chave"], g["rotulo"], None, regra=regra, tem_prazo=False,
            motivo=(f"{g['modulo']}.{g['funcao']} não respondeu: "
                    f"{type(erro).__name__}: {erro}"[:300]))
    itens, quantos = _itens_do_gancho(achado, g, ctx)
    if itens is None:
        return _obrigacao(
            g["chave"], g["rotulo"], None, regra=regra, tem_prazo=False,
            motivo=(f"{g['modulo']}.{g['funcao']} respondeu numa forma que o "
                    f"roteiro não lê ({type(achado).__name__})"))
    return _obrigacao(g["chave"], g["rotulo"], itens, regra=regra,
                      tem_prazo=False, quantos=quantos,
                      feito="nada pendente")


_COBRANCA_DA_CONDUTA = {
    "retorno": _cobrar_retorno,
    "remessa": _cobrar_remessa,
    "pedidos_cra": _cobrar_pedidos_da_cra,
    "entregas": _cobrar_entregas,
    "editais": _cobrar_editais,
    "protestos": _cobrar_protestos,
    "instrumentos": _cobrar_instrumentos,
    "xml": _cobrar_xml,
    "cenprot": _cobrar_cenprot,
    "repasse": _cobrar_repasse,
    "encerrar": _cobrar_encerramento,
}


def _situacao_da_conduta(obrigacoes: list[dict]) -> str:
    """A pior das obrigacoes. Sem medida em todas, sem medida."""
    situacoes = {o["situacao"] for o in obrigacoes}
    for s in (ATRASADO, PENDENTE):
        if s in situacoes:
            return s
    if situacoes and situacoes <= {SEM_MEDIDA}:
        return SEM_MEDIDA
    return FEITO


def cobrar_o_dia(con: sqlite3.Connection, *, agora: str) -> list[dict]:
    """As condutas do dia, cada uma com as obrigacoes e a situacao. SO LE.

    `agora` e o instante da cobranca (`db.now()`), e nao so a data: a hora do
    papel e o que separa PENDENTE de ATRASADO.
    """
    ctx = _contexto(con, agora)
    horas = {h["o_que"]: h for h in HORARIOS_DA_CRA}
    papel = [("CRA", p) for p in ROTEIRO_DA_CRA] + [
        ("CENPROT", p) for p in ROTEIRO_DA_CENPROT]
    saida = []
    for c in CONDUTAS_DO_DIA:
        linha = dict(c)
        linha["botoes"] = [dict(b) for b in c["botoes"]]
        h = horas.get(c.get("hora") or "")
        linha["hora_limite"] = h["hora"] if h else None
        linha["obrigacoes"] = _COBRANCA_DA_CONDUTA[c["chave"]](con, ctx)
        linha["papel"] = [f"{central}: {p['passo']}" for central, p in papel
                          if p.get("conduta") == c["chave"]]
        saida.append(linha)
    # OS GANCHOS RODAM POR ULTIMO: a peca de outro pedido que estoura desfaz a
    # leitura, e o que ja foi medido nao se perde. Cada um entra na conduta
    # dele, antes do encerramento — que so se calcula com eles dentro.
    por_chave = {c["chave"]: c for c in saida}
    for g in GANCHOS:
        por_chave[g["conduta"]]["obrigacoes"].append(_rodar_gancho(con, ctx, g))
    for linha in saida:
        linha["situacao"] = _situacao_da_conduta(linha["obrigacoes"])
        linha["faltam"] = sum(o["faltam"] or 0 for o in linha["obrigacoes"])
        linha["atrasados"] = sum(o["atrasados"] for o in linha["obrigacoes"])
    return saida


# ------------------------------------------------------ o encerramento

#: A regra que a afirmacao do encerramento grava — o contrato comum da casa.
REGRA_DO_ENCERRAMENTO = "DIA_ENCERRADO_COM_PENDENCIA"
#: O piso da afirmacao: LETRAS, e nao caracteres — «.......» nao e afirmacao
#: de ninguem. E o mesmo piso das outras travas da reestruturacao.
MINIMO_DE_LETRAS_DA_AFIRMACAO = 30
MODELO_DA_AFIRMACAO = "Afirmo, sob minha responsabilidade, que"
#: A obrigacao que o encerramento CUMPRE nao entra na lista do que ele cobra.
OBRIGACAO_DO_PROPRIO_ENCERRAMENTO = "dia_encerrado"


class EncerramentoError(ValueError):
    """O dia nao se encerra — a frase diz o que falta."""


def pendencias_para_encerrar(condutas: list[dict]) -> list[dict]:
    """O que esta PENDENTE ou ATRASADO no dia, item por item. So calcula.

    SEM MEDIDA NAO PRENDE O DIA: o que nao deu para medir nesta instalacao (a
    tabela que nao existe, a peca ainda nao instalada) nao e pendencia de
    ninguem — e dizer que e seria o alarme que soa sempre.
    """
    saida = []
    for c in condutas:
        for o in c["obrigacoes"]:
            if o["chave"] == OBRIGACAO_DO_PROPRIO_ENCERRAMENTO:
                continue
            if o["situacao"] in (PENDENTE, ATRASADO):
                saida.append({
                    "chave": o["chave"], "conduta_n": c["n"],
                    "conduta": c["titulo"], "rotulo": o["rotulo"],
                    "situacao": o["situacao"], "faltam": o["faltam"],
                    "atrasados": o["atrasados"],
                    "o_que_faltava": (
                        f"conduta {c['n']} ({c['titulo']}): {o['rotulo']} — "
                        f"{o['faltam']} pendente(s)"
                        + (f", {o['atrasados']} atrasado(s)"
                           if o["atrasados"] else ""))})
    return saida


def _letras(texto: str) -> int:
    return sum(1 for ch in texto if ch.isalpha())


def conferir_o_encerramento(con, *, agora: str,
                            afirmacoes: dict) -> dict:
    """Confere se o dia pode ser encerrado. SO LE; recusa com a lista.

    `afirmacoes` e `{chave da obrigacao: (afirmo, texto)}` — o contrato comum
    da casa, item por item: a caixa «Afirmo» marcada E pelo menos 30 letras.
    O que se confere e a lista calculada AQUI, e nao a que veio do
    formulario: item que a tela nao mostrou continua pendente, e chave que
    nao e pendencia e ignorada.
    """
    if not _existe(con, "pt_encerramentos_do_dia"):
        raise EncerramentoError(
            "Esta instalação ainda não tem onde guardar o encerramento do dia "
            "— atualize o sistema antes de encerrar.")
    dia = str(agora)[:10]
    ja = encerramento_do_dia(con, dia)
    if ja:
        raise EncerramentoError(
            f"O dia {_br(dia)} já foi encerrado por "
            f"{ja.get('encerrado_por') or '—'} às "
            f"{str(ja.get('encerrado_em') or '')[11:16]}.")
    pendencias = pendencias_para_encerrar(cobrar_o_dia(con, agora=agora))
    afirmadas, sem = [], []
    for p in pendencias:
        afirmo, texto = afirmacoes.get(p["chave"]) or (False, "")
        texto = " ".join(str(texto or "").split())
        if afirmo and _letras(texto) >= MINIMO_DE_LETRAS_DA_AFIRMACAO:
            afirmadas.append(dict(p, afirmacao=texto))
        else:
            sem.append(p)
    if sem:
        lista = "; ".join(f"{p['conduta_n']}. {p['conduta']} — {p['rotulo']} "
                          f"({p['faltam']})" for p in sem)
        raise EncerramentoError(
            f"O dia não se encerra: {len(sem)} item(ns) pendente(s) sem "
            f"afirmação — {lista}. Faça o que falta, ou, em CADA item, marque "
            f"«Afirmo» e escreva pelo menos {MINIMO_DE_LETRAS_DA_AFIRMACAO} "
            f"letras, começando por «{MODELO_DA_AFIRMACAO}…». A afirmação fica "
            f"gravada com o seu nome e aparece primeiro amanhã.")
    return {"dia": dia, "pendencias": pendencias, "afirmacoes": afirmadas}


def gravar_o_encerramento(con, conferido: dict, *, agora: str,
                          usuario: str | None) -> dict:
    """Grava o encerramento conferido. ESCREVE; recusa o dia ja encerrado.

    A conferencia roda numa leitura antes (`conferir_o_encerramento`), e esta
    escrita so confere de novo o que a trava do banco garante: um por dia.
    """
    bd = banco(con)
    dia = conferido["dia"]
    if bd.um("SELECT 1 AS um FROM pt_encerramentos_do_dia WHERE dia = %s",
             (dia,)):
        raise EncerramentoError(f"O dia {_br(dia)} já foi encerrado.")
    situacao = "COM_PENDENCIA" if conferido["afirmacoes"] else "COMPLETO"
    novo = bd.escrever(
        """INSERT INTO pt_encerramentos_do_dia(dia, situacao, pendencias,
               pendencias_json, afirmacoes_json, encerrado_em, encerrado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (dia, situacao, len(conferido["afirmacoes"]),
         json.dumps(conferido["pendencias"], ensure_ascii=False),
         json.dumps(conferido["afirmacoes"], ensure_ascii=False),
         agora, usuario))
    return {"id": int(novo[0]["id"]), "dia": dia, "situacao": situacao,
            "afirmacoes": conferido["afirmacoes"]}


def o_que_ficou(con, *, agora: str, condutas: list[dict]) -> dict:
    """O que o dia seguinte mostra PRIMEIRO, sem depender da memoria. SO LE.

    O ultimo encerramento antes de hoje (com o que ficou e o que se afirmou),
    se o dia util anterior foi encerrado, e o que esta atrasado agora — que e,
    por definicao, o que veio de antes.
    """
    ctx = _contexto(con, agora)
    anterior = _dia_util_anterior(ctx["hoje"], ctx).isoformat()
    ultimo = None
    if _existe(con, "pt_encerramentos_do_dia"):
        ultimo = _encerramento_lido(banco(con).um(
            """SELECT * FROM pt_encerramentos_do_dia WHERE dia < %s
                ORDER BY dia DESC LIMIT 1""", (ctx["dia"],)))
    atrasados = [{"n": c["n"], "titulo": c["titulo"], "ancora": c["ancora"],
                  "rotulo": o["rotulo"], "atrasados": o["atrasados"]}
                 for c in condutas for o in c["obrigacoes"]
                 if o["situacao"] == ATRASADO]
    return {"dia_util_anterior": anterior,
            "anterior_encerrado": (None if not _existe(
                con, "pt_encerramentos_do_dia")
                else bool(ultimo and ultimo["dia"] == anterior)),
            "ultimo": ultimo, "atrasados": atrasados}


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


def quantos_o_sistema_faz() -> dict:
    """Quantos passos de cada papel tem tela nesta casa. So conta.

    **O NUMERO FICA A VISTA**: um roteiro que nao diz quanto dele o sistema
    cobre deixa o escrevente supor que cobre tudo.
    """
    return {"cra_com_tela": sum(1 for p in ROTEIRO_DA_CRA if p.get("tela")),
            "cra_total": len(ROTEIRO_DA_CRA),
            "cenprot_com_tela": sum(1 for p in ROTEIRO_DA_CENPROT
                                    if p.get("tela")),
            "cenprot_total": len(ROTEIRO_DA_CENPROT)}


def roteiro(con: sqlite3.Connection, *, agora: str) -> dict:
    """Tudo o que a tela do roteiro mostra. SO LE.

    As condutas cobradas, o relogio do dia (os horarios da CRA, cada um
    apontando para a conduta dele), o estado do envio automatico, o que saiu do
    roteiro com a prova, e o papel como fonte.
    """
    condutas = cobrar_o_dia(con, agora=agora)
    ancora_da_hora = {"Envio de remessa": ("conduta-remessa", "Remessa do dia"),
                      "Envio de confirmacao": ("conduta-remessa",
                                               "Confirmação"),
                      "Envio de retorno": ("conduta-retorno", "Retorno"),
                      "Andamento": ("conduta-retorno", "Andamento")}
    # O RETORNO E O ANDAMENTO TEM A MESMA HORA E A MESMA CONDUTA, e viram uma
    # linha so: duas linhas «11:30» lado a lado pareceriam dois passos.
    juntos: dict = {}
    for h in HORARIOS_DA_CRA:
        ancora, nome = ancora_da_hora.get(h["o_que"], (None, h["o_que"]))
        item = juntos.setdefault((h["hora"], ancora), {
            "hora": h["hora"], "ancora": ancora, "nomes": [],
            "nosso": h["nosso"]})
        item["nomes"].append(nome)
    relogio = []
    for chave in sorted(juntos):
        item = juntos[chave]
        item["o_que"] = " e ".join(item.pop("nomes"))
        relogio.append(item)
    total = {s: sum(1 for c in condutas if c["situacao"] == s)
             for s in (FEITO, PENDENTE, ATRASADO, SEM_MEDIDA)}
    papel = []
    for central, lista in (("CRA", ROTEIRO_DA_CRA),
                           ("CENPROT", ROTEIRO_DA_CENPROT)):
        for p in lista:
            linha = dict(p, central=central)
            conduta = next((c for c in CONDUTAS_DO_DIA
                            if c["chave"] == p.get("conduta")), None)
            linha["conduta_n"] = conduta["n"] if conduta else None
            linha["conduta_ancora"] = conduta["ancora"] if conduta else None
            linha["fora_o_que"] = next(
                (f["o_que"] for f in FORA_DO_ROTEIRO
                 if f["chave"] == p.get("fora")), None)
            papel.append(linha)
    return {"condutas": condutas, "relogio": relogio, "total": total,
            "estado": estado_do_envio(con),
            # O FECHAMENTO E O DIA SEGUINTE (29/10/2026): o que ficou de ontem
            # abre a tela; o que falta para encerrar hoje fecha.
            "de_ontem": o_que_ficou(con, agora=agora, condutas=condutas),
            "para_encerrar": pendencias_para_encerrar(condutas),
            "encerrado_hoje": encerramento_do_dia(con, str(agora)[:10]),
            "minimo_de_letras": MINIMO_DE_LETRAS_DA_AFIRMACAO,
            "modelo_da_afirmacao": MODELO_DA_AFIRMACAO,
            "fora_do_roteiro": [dict(f) for f in FORA_DO_ROTEIRO],
            "papel": papel, "horarios": [dict(h) for h in HORARIOS_DA_CRA],
            "so_o_tabeliao": list(SO_O_TABELIAO), "fontes": list(FONTES),
            "rotulo_da_situacao": dict(ROTULO_DA_SITUACAO),
            "hoje": str(agora)[:10], "agora": str(agora)[:16]}
