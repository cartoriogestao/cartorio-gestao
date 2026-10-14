"""O LAÇO DO AGENTE — pensa, pede ferramenta, lê o resultado, e para.

POR QUE O LAÇO MORA NUM MÓDULO SÓ
    Porque o pedaço que decide «o agente já terminou?» é o pedaço que não pode
    existir em dois lugares. Se o transporte (`agente_provedores.py`) também
    decidisse quando parar, uma correção feita num lado deixaria o outro
    mentindo — e este projeto já pagou caro por régua escrita duas vezes.

AS TRÊS TRAVAS, E POR QUE SÃO TRÊS
    Turnos: sem teto, um agente que não fecha o raciocínio fica pensando até a
    conta chegar. Gasto: o teto de turnos não limita o tamanho de cada turno, e
    uma sessão que arrasta o histórico inteiro a cada volta gasta muito por
    volta. Máscara: o agente lê o banco, o código e os problemas anotados, e
    cada leitura é uma porta pela qual um dado de pessoa pode sair.

    **As três são do mesmo tipo: um número que alguém escolheu.** Nenhuma delas
    depende de o modelo se comportar, e é por isso que elas funcionam.

A TRANSAÇÃO NÃO ATRAVESSA A REDE
    Um turno leva dezenas de segundos. Se ele acontecesse dentro de um
    `BEGIN IMMEDIATE`, o balcão inteiro ficaria esperando o agente pensar — e o
    `busy_timeout` de dez segundos estouraria no primeiro pedido de certidão.
    Então cada leitura e cada gravação abre a sua transação, e entre uma e
    outra não há nada aberto. **É a mesma razão pela qual `conversar` não recebe
    `con`:** a assinatura avisa.

A CONVERSA É REMONTADA DO BANCO, TURNO A TURNO
    Nada de guardar a conversa em memória e mandá-la adiante. O que a conversa
    é, está em `ag_passos`; a cada volta ela é relida e traduzida
    (`_conversa`). Custa um `SELECT` por turno e paga três vezes: uma sessão
    interrompida no meio continua de onde parou, a tela mostra exatamente o que
    o modelo recebeu, e a máscara aplicada antes de gravar é a mesma que o
    provedor vê — **não há duas versões do que foi dito.**

O QUE SAI DAQUI JÁ PASSOU PELA BARREIRA
    O pedido do oficial, o texto do modelo e os argumentos de cada ferramenta
    passam por `ajuda_privacidade.sanitizar_para_modelo` **antes** de serem
    gravados. Não é para proteger a tela: é porque o banco vai no backup, e o
    backup sai da serventia. O que está em `ag_passos` é o que pode sair de
    casa; o que não podia sair não chega a ser escrito.

    **O texto do próprio modelo também passa.** Ele escreveu sobre dados que
    recebeu já mascarados, e poderia reescrever de memória um dado que viu em
    outro lugar. Uma porta a mais é uma porta a mais.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from typing import Any

import agente_ferramentas as FER
import agente_provedores as PROV
import agente_schema as AG
import ajuda_privacidade as PRIV

# O REGISTRO DA CASA. Ele só é usado para uma coisa, e é a que não pode ficar
# calada: uma rodada que estoura por um defeito inesperado. O `_rodar` não
# levanta por falha de provedor — isso é estado, e fica gravado na sessão —, mas
# um erro de programação (coluna que não existe, ferramenta que estourou) sai
# por aqui, e sai com o rastro inteiro, em vez de morrer dentro de uma linha de
# execução sem ninguém para contar.
_REGISTRO = logging.getLogger(__name__)


class AgenteRecusado(ValueError):
    """Recusa do agente, com a frase pronta para o oficial."""


# O TETO DURO DE SAÍDA. Ele é o que impede uma resposta de virada de turno
# virar um relatório inteiro — que custaria mais que o diagnóstico que a
# produziu.
MAXIMO_DE_SAIDA = 4000

# O FREIO DE GASTO DA SESSÃO. Não está na tela porque não é decisão de quem
# opera: é o limite acima do qual alguma coisa saiu do controle, e o certo é
# parar e contar a alguém.
#
# **E ELE CONTAVA POR RODADA, O QUE NÃO É UM TETO** — consertado em 18/09/2026.
# Os dois contadores do laço nascem em zero a cada rodada, e era contra eles que
# o teto se conferia: a sessão 1 desta instalação parou DUAS vezes com o aviso
# de «passou de 400000 tokens» e **aceitou mais dois pedidos depois disso**,
# porque cada rodada recomeçava a contagem. O número da sessão está gravado:
# **1.395.475 de entrada + 24.946 de saída = 1.420.421 tokens**, que é **3,55
# vezes** o teto — e é o que o problema #68 relatou («logo disse que passou do
# limite de 400k tokens»).
#
# **E O NÚMERO SUBIU NO MESMO DIA, PORQUE 400 MIL AINDA PARAVA SESSÃO LEGÍTIMA.**
# Medido com a poda ligada (`_poupar`), sobre a conversa REAL daquela sessão: as
# 32 chamadas ao provedor somam **1.669.358 caracteres em vez de 4.420.607** — a
# poda corta **62,2 %** — e, ao câmbio que a própria instalação declarou (3,17
# caracteres por token), isso são **~527 mil tokens**. Ou seja: **um teto de 400
# mil ainda teria parado aquela sessão**, só que no fim em vez do meio. **Alarme
# que soa sempre é alarme que ninguém ouve**, e o teto existe para o laço
# descontrolado, não para a leitura pesada.
#
# **UM MILHÃO É A FOLGA PARA UMA SESSÃO DO DOBRO DAQUELA**, e continua sendo
# pouco perto do que um laço faz: o que segura o laço é o teto de TURNOS de cada
# rodada, que é do oficial, mais o `teto_de_sessoes` do dia. Este aqui é o
# último freio, e ele parou de mentir sobre o tamanho do que mede.
TETO_DE_TOKENS = 1_000_000

# A PODA DO QUE JÁ FOI LIDO — 18/09/2026
#
# POR QUE ISTO EXISTE, E O NÚMERO É DESTA INSTALAÇÃO. A sessão 1 do console
# (problema #68) tem 107 passos, e o que ela leu e escreveu soma **240.095
# caracteres**. Só que a conversa INTEIRA vai ao provedor A CADA TURNO, e nada a
# podava no caminho: ela foi reenviada nos **32 pontos de chamada**, e o que
# subiu somou **4.420.607 caracteres** — **18,4 vezes** o que a sessão leu. Foi
# assim que uma sessão de 240 mil caracteres gastou **1.395.475 tokens de
# entrada** e parou no teto sem ter respondido nada. Com a poda, essa soma cai a
# **1.669.358** — **7,0 vezes** o que ela leu, e **62,2 % menos**.
#
# **OS QUATRO NÚMEROS SAEM DO MESMO LUGAR**:
# `tools/medir_o_peso_da_conversa.py`, que reconstrói a conversa com o
# `_conversa` de verdade e a mede nos dois mundos — as duas somas, as duas
# razões e as duas porcentagens, na mesma rodada. Ele existe porque a primeira
# versão deste comentário citava **outra** conta (3.317.711 caracteres, de um
# script que media só o texto dos resultados) — e dois números para o mesmo fato
# é o carimbo que mente começando. Quem mexer na poda, meça de novo com ele.
#
# **O TETO CONTA TOKENS, E NÃO REAIS** — conte os que o provedor devolveu
# (descontados ou não), e é esse número que faz a sessão parar. A poda é o que
# o mantém em pé, e é por isso que ela mora aqui e não no preço.
#
# **E É O MAIOR ENVIO QUE DERRUBA A CONVERSA, NÃO A SOMA — 18/09/2026.** O
# problema #74 («a conversa demorou e deu timeout») não é sobre o gasto: é sobre
# UMA requisição que não coube no prazo. Medido nos 32 pontos de chamada da
# sessão 1 (`tools/medir_o_peso_da_conversa.py`, que SÓ LÊ), o MAIOR deles era o
# do passo 106, com **256.965 caracteres**. **O MESMO ponto**, com a poda, vai a
# **88.622** — **65,5 % menor**, que é a diferença entre uma conversa que o
# provedor começa a responder em segundos e uma que estoura o prazo.
#
# **A COMPARAÇÃO É NO MESMO PONTO, e isso é deliberado.** Depois da poda o maior
# envio passa a ser outro — o do passo 98, com 89.077 caracteres —, e comparar
# 256.965 com 89.077 daria 65,3 %: uma porcentagem entre dois pontos diferentes,
# que não descreve nem o que estourava o prazo nem o que passou a ser o maior.
# **A poda reordena os pontos**, e por isso a conta do #74 se faz ponto a ponto.
# E **a poda não é economia de fatura: é o conserto do timeout** — que é o que
# faz dela o conserto dos dois problemas relatados de uma vez.
#
# E O QUE ISTO NÃO É: não é apagar o que ele leu. O `ag_passos` guarda tudo, e
# a tela continua mostrando tudo — o que sai é o que VOLTA AO MODELO. Os
# resultados antigos e grandes viram uma linha com o nome da ferramenta e o
# tamanho do que ela devolveu, e ele pode chamá-la de novo quando precisar.
# Os últimos `RESULTADOS_INTEIROS` vão inteiros, porque é neles que ele está
# trabalhando; e resultado pequeno fica, porque resumir o que já é curto só
# tira dele o que ele tinha à mão.
RESULTADOS_INTEIROS = 6
PISO_DE_RESULTADO_INTEIRO = 3_000
RESULTADO_RESUMIDO = (
    "[resumido para o orçamento desta sessão: era a resposta de {nome}, com "
    "{tamanho} caracteres. O texto inteiro está guardado na tela da sessão; "
    "chame a ferramenta de novo se precisar dele.]")

# O TEXTO DE APOIO QUE VIRA A INSTRUÇÃO DO AGENTE. Ele é escrito para o
# modelo, e não para a tela: por isso é direto e imperativo, e por isso fala de
# dinheiro em vez de falar de elegância.
INSTRUCAO = """\
Você é o agente de manutenção do Cartório Gestão, o sistema de uma serventia \
registral brasileira. Quem fala com você é o oficial, que responde pela \
serventia: ele decide, e você apura.

O QUE VOCÊ FAZ
    Você lê esta instalação — o código, o banco, a documentação e a lista de \
problemas anotados — e responde o que ela tem. Você diagnostica. Quando a \
escrita estiver liberada, você também resolve o que for pequeno e objetivo: \
anotar no problema o que apurou, registrar um achado da conferência, e abrir \
ou fechar um módulo. Nada além disso.

COMO FALAR
    Em português do Brasil, direto, para quem opera um cartório e não \
programa. Frases curtas, sem jargão e sem enfeite. Diga o que você VIU, e não \
o que você imagina: se não mediu, diga que não mediu. Número vale mais que \
adjetivo.

COMO USAR AS FERRAMENTAS
    - Leia antes de concluir. Conclusão sem leitura é chute, e chute em cima \
de um ato é o que não pode acontecer nesta casa.
    - Cada turno custa dinheiro de verdade. Peça o que interessa, com as \
colunas escritas, e pare de ler quando já souber.
    - Não invente nome de ferramenta, de tabela nem de arquivo. O catálogo \
que você recebe é completo, e o esquema do banco se pergunta antes de usar.
    - Quando uma ferramenta recusar ou falhar, leia o que ela disse e mude de \
caminho. Não repita o mesmo pedido do mesmo jeito.

O QUE VOCÊ NÃO FAZ
    - Não toca em ato. Não existe ferramenta que escreva em livro, matrícula, \
escritura, título, selo, cobrança ou caixa — e não é esquecimento: ato é do \
delegatário, com gente no meio. Se o conserto exigisse mexer em ato, escreva \
a recomendação em vez de tentar.
    - Não executa código, não abre terminal e não lê nada fora do sistema.
    - Não decide o que é grave. Você relata; o oficial decide.

O QUE VOCÊ VÊ, E O QUE NÃO VÊ
    O que chega até você já passou pela barreira de privacidade desta casa. \
Marcadores como [PESSOA_01] ou [CPF_01] são dados de pessoa que NÃO foram \
enviados — não são lacunas a preencher. Não tente descobrir quem é, não \
pergunte e não deduza: trabalhe com a estrutura e com os números.

COMO TERMINAR
    Ao terminar, escreva um resumo curto, com os blocos que tiverem conteúdo:
    O QUE EU VI: o que foi medido, com os números.
    O QUE EU FIZ: cada mudança feita, e por que ela é segura.
    O QUE FALTA: o que precisa de decisão ou de mão humana — uma frase por \
item, dizendo o que fazer.
"""

# O TURNO DE FECHO — 18/09/2026
#
# POR QUE ISTO EXISTE, E ELE É O CONSERTO DO PROBLEMA #68. O laço parava no
# teto e escrevia o aviso, e **não pedia a resposta**: a sessão terminava sem
# uma linha do que ele tinha apurado, com 1,4 milhão de tokens já pagos. Quem
# lê a tela vê a conversa inteira e nenhuma conclusão — a pior forma do
# trabalho perdido, porque ele está todo ali, pago, e não vira resposta.
#
# Então a última vaga da rodada é DA RESPOSTA, e ela é pedida SEM FERRAMENTA
# NENHUMA: com o catálogo aberto ele leria mais uma vez, e a rodada acabaria
# do mesmo jeito. Sem catálogo, a única saída é escrever.
INSTRUCAO_DE_FECHO = """\
O ORÇAMENTO DESTA RODADA ACABOU. Nenhuma ferramenta está disponível, e pedir \
qualquer uma não vai funcionar.

Responda agora, com o que você JÁ apurou nesta conversa — em português, para \
quem opera um cartório:

    O QUE EU VI: o que foi medido, com os números que você tem.
    O QUE ESTÁ ERRADO: o que você achou de errado, e onde.
    O QUE FAZER: o que mudar, com o arquivo e a linha de cada coisa.
    O QUE FALTA: o que você não conseguiu apurar, e o que precisaria ler para \
apurar — dizer «não deu para concluir, falta X» é resposta, e silêncio não é.

Escreva o que você sabe agora. Não escreva que vai olhar depois, não prometa \
investigação e não peça desculpa por parar: quem lê sabe por que a rodada \
acabou, e o que ele precisa é do que você viu.
"""

# QUANDO A ESCRITA ESTÁ DESLIGADA, O MODELO PRECISA SABER — e não descobrir
# levando uma recusa. Ferramenta de escrita desligada nem é oferecida a ele
# (ver `agente_ferramentas.catalogo`), e sem esta frase o modelo concluiria que
# o sistema não sabe consertar o que ele achou.
SEM_ESCRITA = """\
A ESCRITA ESTÁ DESLIGADA nesta instalação: você não tem ferramenta nenhuma que \
mude coisa alguma. Faça o diagnóstico completo e diga ao oficial exatamente o \
que mudar, onde e para que valor — uma frase por mudança, para ele clicar.
"""

# O QUE O MODELO RECEBE NO LUGAR DE UM RESULTADO QUE NÃO FICOU GRAVADO. A
# sessão morre no meio de um turno quando falta luz ou alguém fecha o console,
# e a conversa não pode voltar ao provedor com um pedido de ferramenta sem
# resposta: a API recusa o pedido inteiro, e a sessão ficaria irrecuperável.
INTERROMPIDO = (
    "O resultado desta ferramenta não ficou registrado: a sessão foi "
    "interrompida no meio da execução. Eu não sei se ela chegou a rodar. Se "
    "ela escrevia, confira o estado atual antes de pedir de novo — a leitura "
    "custa um turno, a escrita repetida custa mais."
)

# E O RECADO QUE FICA NA SESSÃO quando é o PROGRAMA que para no meio da rodada.
# Ele não vai ao provedor: é para quem lê a conversa na tela, no ponto exato em
# que ela se interrompeu — sem ele, a pausa entre o pedido da ferramenta e a
# fala seguinte pareceria descuido de quem escreveu.
AVISO_DE_INTERRUPCAO = (
    "Esta sessão foi interrompida: o programa foi fechado no meio de uma "
    "rodada. O que já tinha sido apurado continua aqui — escreva de novo e ela "
    "continua de onde parou."
)


# =====================================================================
# A RODADA NAO PRENDE A TELA — 15/09/2026
#
# POR QUE ISTO EXISTE
#     O console chamava `pedir` e esperava. Um turno com ferramentas leva
#     dezenas de segundos, e a sessao inteira pode levar minutos: quem pediu
#     ficava olhando uma pagina parada, sem saber se o agente estava pensando ou
#     se o sistema tinha morrido — e sem poder conferir nada enquanto isso.
#
#     Aqui a rodada passa a acontecer FORA do pedido HTTP. Quem chama recebe o
#     numero da sessao na hora, e a tela pergunta «como esta?» a cada segundo,
#     mostrando cada passo NO MOMENTO EM QUE ELE E GRAVADO. **O que a tela
#     mostra continua saindo do banco** — nao ha copia em memoria para
#     divergir do que o modelo viu.
#
# E O MAIS IMPORTANTE: NAO HA RODADA FORA DESTE MODULO
#     A rodada de fundo roda por `_rodar`, que e a MESMA funcao da chamada
#     sincrona e continua sendo a unica que fala com o provedor, executa
#     ferramenta e grava passo. O que mudou foi quem espera por ela, e nao o
#     que ela faz. **Esta e a licao que este projeto pagou caro quatro vezes**:
#     uma segunda versao do laco divergiria da primeira no primeiro conserto,
#     e a que divergisse seria justamente a que ninguem esta olhando.
#
# A CONVERSA E UMA SO, E POR ISSO HA UMA TRAVA
#     Duas rodadas da mesma sessao gravariam passos intercalados. `_RODANDO`
#     guarda quem esta rodando AGORA, e `continuar` recusa antes de qualquer
#     escrita — para a recusa ser a mesma que a de sessao aberta, e nao uma
#     segunda regra parecida com ela.
#
# O QUE A TRAVA NAO RESOLVE, E ESTA DECLARADO
#     Ela mora na memoria do processo. Com dois processos servindo (nao e o
#     caso desta casa: e um waitress e um banco local), cada um teria a sua
#     lista. O segundo esbarraria na trava do banco, que e a de sempre —
#     `db.transaction()` e `BEGIN IMMEDIATE` —, e o pior que aconteceria seria
#     uma sessao marcada como ABERTA que a recuperacao da abertura conserta.
# =====================================================================

# QUEM ESTA RODANDO AGORA. A chave e o id da sessao, e o valor e o retrato de
# quem pediu — o que a tela mostra enquanto o primeiro passo ainda nao chegou.
_RODANDO: dict[int, dict[str, Any]] = {}
_CADEADO = threading.Lock()


def em_curso(sessao_id: Any) -> bool:
    """Esta sessão está rodando neste instante? Só calcula."""
    with _CADEADO:
        return int(sessao_id) in _RODANDO


def rodando() -> list[int]:
    """As sessões que estão rodando agora, em ordem. Só calcula.

    **É O QUE PERMITE A TELA DIZER A VERDADE NO PRIMEIRO SEGUNDO.** A sessão é
    gravada como ABERTA, e ABERTA quer dizer exatamente isto — mas quem lê a
    lista precisa saber se é uma rodada viva ou uma sessão que ficou presa
    porque o programa parou. São coisas diferentes, e pedem providências
    diferentes.
    """
    with _CADEADO:
        return sorted(_RODANDO)


def recado_do_fim(sessao: Any) -> dict[str, str] | None:
    """Como a sessão terminou, em uma frase. Só calcula. `None` se ainda corre.

    **MORA AQUI, E NAO NA TELA.** A mesma frase serve ao console, ao aviso do
    alto da página e à gaveta que opera de qualquer tela — e duas versões dela
    diriam coisas diferentes sobre o mesmo fato. É a régua do relato #23: **duas
    vistas do mesmo fato precisam do mesmo texto**.

    O `tom` é o da casa (`success`, `warning`, `danger`), e não uma cor: quem
    pinta é o template, com as classes que já existem.
    """
    if sessao is None:
        return None
    estado = str(sessao.get("estado") or "")
    if estado in (AG.ABERTA, AG.INTERROMPIDA):
        return None
    if estado == AG.LIMITE:
        # **E O RECADO DIZ QUAL TETO, PORQUE SÃO DOIS.** O de turnos é da rodada
        # e o de tokens é da sessão inteira; sem a razão escrita, o console
        # dizia só «parou no teto» — e foi exatamente isso que o #68 relatou
        # («disse que passou do limite de 400k tokens» e não havia como saber
        # de onde saía o número). O campo é o mesmo que a tela mostra como
        # «Por que parou», e as duas vistas passam a contar o mesmo fato.
        porque = str(sessao.get("erro") or "").strip()
        return {"tom": "warning",
                "texto": "O agente parou no teto, e não por ter terminado. "
                         f"{porque + ' ' if porque else ''}"
                         "O que ele já apurou está abaixo — se precisar de "
                         "mais, continue a conversa escrevendo de novo."}
    if estado == AG.ERRO:
        return {"tom": "danger",
                "texto": "A sessão parou com uma falha: "
                         f"{sessao.get('erro') or '—'}"}
    if estado == AG.CONCLUIDA:
        gastos = (int(sessao.get("tokens_de_entrada") or 0)
                  + int(sessao.get("tokens_de_saida") or 0))
        return {"tom": "success",
                "texto": f"O agente terminou: {sessao.get('turnos')} turno(s), "
                         f"{gastos} tokens."}
    if estado == AG.RECUSADA:
        return {"tom": "warning",
                "texto": "A sessão foi recusada: "
                         f"{sessao.get('erro') or 'sem motivo registrado'}."}
    return None


def _onde_estamos(onde: Any) -> str:
    """A tela de onde o pedido saiu, já passada pela barreira. Só calcula.

    **O AGENTE PRECISA SABER ONDE QUEM PERGUNTOU ESTAVA.** «Não funciona» dito
    do balcão do RI é outra pergunta que o mesmo «não funciona» dito da tela de
    selos, e sem esta linha o modelo gasta um turno perguntando o que a casa já
    sabia. Vai mascarado porque, em tese, é texto que chega de fora (a rota o
    monta do módulo e da rota, mas a régua não depende de quem chama).
    """
    texto = " ".join(str(onde or "").split())
    if not texto:
        return ""
    try:
        return _seguro(texto[:200], nomes_livres=False)
    except PRIV.PrivacidadeError:
        return ""


def _despachar(db: Any, *, sessao_id: int, preparo: dict, onde: str,
               pasta_de_dados: Any, raiz: Any, usuario: str, versao: str,
               app: Any, hora: Callable[[], str], prazo: int,
               maximo_de_saida: int) -> threading.Thread:
    """Solta a rodada numa linha de execução própria. Devolve a linha.

    **A LINHA É DEVOLVIDA PARA QUEM PRECISA ESPERAR.** A tela não espera — ela
    pergunta «como está?». A chamada de dentro do sistema (`pedir`/`responder`,
    que a suíte usa) espera, e continua tendo o retrato dela. As duas passam
    pela MESMA `_rodar`: esperar é uma decisão de quem chama, e não um segundo
    caminho.
    """
    def trabalhar() -> None:
        antes = None
        try:
            # A ORDEM DE PARTIDA DESTA RODADA, para a guarda do fim saber se ela
            # escreveu alguma coisa. Fica dentro do `try` porque um banco
            # travado aqui é falha da rodada como qualquer outra — e não uma
            # linha solta que estoura sem ninguém fechar a sessão.
            antes = _ordem_de_agora(db, sessao_id)
            _rodar(db, sessao_id=sessao_id, pedidos=[], preparo=preparo,
                   onde=onde, pasta_de_dados=pasta_de_dados, raiz=raiz,
                   usuario=usuario, versao=versao, app=app, hora=hora,
                   prazo=prazo, maximo_de_saida=maximo_de_saida)
        except (AssertionError, KeyboardInterrupt, SystemExit):
            # **AFIRMAÇÃO DE PROGRAMA NÃO SE ENGOLE.** Uma asserção que falha é
            # alguém dizendo «isto não pode acontecer» — e virá-la em «estado
            # ERRO» faria o defeito aparecer como sessão que não terminou, que é
            # outra coisa. Sobe, e o rastro fica na saída.
            raise
        except Exception as falha:      # a rodada não pode morrer calada
            _REGISTRO.exception("a rodada do agente #%s estourou", sessao_id)
            _falhou_a_rodada(db, sessao_id, falha, hora=hora)
        finally:
            # **A RODADA QUE NÃO ESCREVEU NADA DEIXA UMA LINHA** — problema #74.
            # Antes desta guarda, o console ficava com a conversa parada no meio
            # e nenhuma pista de que a rodada tinha morrido; a sessão continuava
            # ABERTA, recusando a fala seguinte. Isto fecha as duas coisas.
            if antes is not None:
                _a_rodada_nao_escreveu_nada(db, sessao_id, desde=antes,
                                            hora=hora)
            with _CADEADO:
                _RODANDO.pop(int(sessao_id), None)

    with _CADEADO:
        _RODANDO[int(sessao_id)] = {"comecou_em": hora(),
                                    "provedor": preparo["provedor"],
                                    "modelo": preparo["modelo"]}
    linha = threading.Thread(target=trabalhar, name=f"agente-{int(sessao_id)}",
                             daemon=True)
    linha.start()
    return linha


# A RODADA QUE NÃO DEIXOU NADA ESCRITO — problema #74, 18/09/2026.
#
# **O SILÊNCIO É O DEFEITO.** Uma rodada pode terminar sem gravar um único passo
# — uma exceção que sobe no meio, um caminho que morre antes do `_aviso`, o
# processo que cai —, e até aqui isso deixava o console exatamente como estava:
# a conversa com os passos de antes, nada depois, e a sessão marcada como se
# estivesse rodando. Quem perguntou não tem como saber se travou, se ainda está
# pensando, ou se a resposta se perdeu.
#
# Medido na sessão 1 desta instalação: duas rodadas ficaram sem uma linha, e a
# única pista estava no `ag_passos` — o vazio entre a pergunta e a vez seguinte.
# **A tela não tinha como dizer o que o banco não guardou.**
AVISO_DE_RODADA_MUDA = (
    "Esta rodada terminou sem deixar uma linha: não houve resposta, nem "
    "ferramenta, nem erro registrado. Nada do que já foi lido se perdeu — "
    "escreva de novo para continuar de onde parou.")


def _ordem_de_agora(db: Any, sessao_id: int) -> int:
    """O número do próximo passo desta sessão, lido agora. **SÓ LÊ.**"""
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        return AG.proxima_ordem(con, int(sessao_id))


def _a_rodada_nao_escreveu_nada(db: Any, sessao_id: int, *, desde: int,
                                hora: Callable[[], str]) -> None:
    """Se a rodada não gravou passo nenhum, deixa a linha que faltava. **ESCREVE.**

    **A CONTA É A DA GRAVAÇÃO, E NÃO UMA SEGUNDA CONTAGEM.** `proxima_ordem` é o
    mesmo número que `registrar_passo` usa; comparar o de antes com o de agora
    responde «escreveu alguma coisa?» sem manter um contador paralelo que
    divergiria do de lá no primeiro conserto.

    **E A SESSÃO NÃO FICA ABERTA.** `ABERTA` quer dizer «alguém está rodando
    agora», e é essa palavra que recusa a próxima fala do oficial: rodada morta
    que a deixa assim trava a conversa. A recuperação da abertura do banco já
    conserta isso; aqui ela é aplicada no mesmo instante, com o motivo escrito.

    **NADA AQUI PODE DERRUBAR QUEM CHAMOU** — quem chama está num `finally`,
    muitas vezes no caminho de uma exceção que ainda precisa subir.
    """
    try:
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            if AG.proxima_ordem(con, int(sessao_id)) != int(desde):
                return                  # escreveu: não há silêncio a cobrir
            sessao = AG.ler_sessao(con, int(sessao_id))
        with db.transaction() as con:
            _aviso(con, int(sessao_id), AVISO_DE_RODADA_MUDA, agora=hora())
            if sessao is not None and str(sessao["estado"]) == AG.ABERTA:
                AG.atualizar_sessao(
                    con, int(sessao_id), estado=AG.INTERROMPIDA,
                    turnos=int(sessao["turnos"] or 0),
                    tokens_de_entrada=int(sessao["tokens_de_entrada"] or 0),
                    tokens_de_saida=int(sessao["tokens_de_saida"] or 0),
                    erro=AVISO_DE_RODADA_MUDA, agora=hora())
    except Exception:           # a linha que falta não pode virar um segundo defeito
        _REGISTRO.exception("não consegui registrar a rodada muda da sessão #%s",
                            sessao_id)


def _falhou_a_rodada(db: Any, sessao_id: int, falha: Any, *,
                     hora: Callable[[], str]) -> None:
    """A sessão não pode ficar ABERTA porque a rodada estourou. **ESCREVE.**

    Sem isto, uma falha inesperada deixaria a sessão marcada como «alguém está
    rodando agora» para sempre — e a próxima fala do oficial bateria numa
    recusa que não é verdade. O estado vai para ERRO com a frase à vista, que é
    o mesmo desfecho de uma falha de provedor: **o trabalho que já foi feito
    fica gravado, e o motivo fica escrito.**
    """
    frase = f"A rodada não terminou: {falha}"
    try:
        with db.transaction() as con:
            sessao = AG.ler_sessao(con, int(sessao_id))
            _aviso(con, int(sessao_id), frase, agora=hora())
            AG.atualizar_sessao(
                con, int(sessao_id), estado=AG.ERRO,
                turnos=int(sessao["turnos"] or 0) if sessao else 0,
                tokens_de_entrada=int(sessao["tokens_de_entrada"] or 0) if sessao else 0,
                tokens_de_saida=int(sessao["tokens_de_saida"] or 0) if sessao else 0,
                erro=frase, agora=hora())
    except Exception:                   # nem o conserto do erro pode derrubar isto
        _REGISTRO.exception("não consegui fechar a sessão #%s depois da falha",
                            sessao_id)


# --------------------------------------------------------------- os nomes


def _relogio(agora: Any) -> Callable[[], str]:
    """A hora, venha ela pronta ou venha o relógio.

    **A sessão atravessa minutos**, e um instante fixo carimbaria todos os
    passos com a hora do começo — o que faria a tela mentir sobre a ordem em
    que as coisas aconteceram. Quem chama pode mandar a função de hora da casa
    (é o que `ajuda_web.py` faz) ou um instante fixo, que é o que o teste quer.
    """
    if callable(agora):
        return lambda: str(agora())
    fixo = str(agora or "")
    return lambda: fixo


def _titulo(pedido: str) -> str:
    """Um resumo de uma linha para a lista de sessões. Não muda o pedido."""
    linha = " ".join(str(pedido or "").split())
    if len(linha) <= 60:
        return linha
    return linha[:57] + "..."


def _seguro(conteudo: Any, *, nomes_livres: bool) -> str:
    """A barreira, aplicada na hora de gravar. Ela levanta, e quem chama trata."""
    return PRIV.sanitizar_para_modelo(conteudo, nomes_livres=nomes_livres)


# ---------------------------------------------------------- as ferramentas


def _esquema_do_dia(db: Any, hoje: str) -> dict[str, int]:
    """Quanto já se pediu ao provedor hoje. **SÓ LÊ.**"""
    with db.connect() as con:
        return AG.contagem_do_dia(con, desde=str(hoje or "")[:10])


def _preparo(db: Any, *, pasta_de_dados: Any, hoje: str,
             provedor: Any, modelo: Any) -> dict[str, Any]:
    """Confere os freios e resolve provedor e modelo **antes** de abrir sessão.

    Conferir antes, e não depois, é o que impede a lista de sessões de encher
    de sessão que já nasceu recusada — e o oficial de achar que pediu algo
    quando o pedido nunca saiu daqui.
    """
    with db.connect() as con:
        configurado = AG.ler_config(con, AG.CHAVE_PROVEDOR)
        modelo_gravado = AG.ler_config(con, AG.CHAVE_MODELO)
        teto_turnos = AG.teto_de_turnos(con)
        teto_sessoes = AG.teto_de_sessoes(con)
        ligada = AG.escrita_ligada(con)

    prov = PROV.normalizar_provedor(provedor or configurado)
    pedido_de_modelo = str(modelo or "").strip() or modelo_gravado
    escolhido = PROV.modelo_de(prov, pedido_de_modelo)

    do_dia = _esquema_do_dia(db, hoje)
    if do_dia["sessoes"] >= teto_sessoes:
        raise AgenteRecusado(
            f"Hoje já foram {do_dia['sessoes']} sessões com o agente, e o teto "
            f"do dia é {teto_sessoes}. Esse teto existe para a conta não "
            f"surpreender no fim do mês: ele é ajustado em Administrativo, e "
            f"sobe com um clique se o trabalho de hoje precisa continuar.")

    if not PROV.tem_chave(pasta_de_dados, prov):
        raise AgenteRecusado(
            f"Não há chave do {PROV.PROVEDORES[prov]['nome']} informada nesta "
            f"instalação. A chave é gravada em Administrativo, na "
            f"configuração do agente, e mora num arquivo fora do banco — o "
            f"banco vai no backup, e o backup sai da serventia.")

    return {"provedor": prov, "modelo": escolhido, "teto_de_turnos": teto_turnos,
            "teto_de_sessoes": teto_sessoes, "escrita_ligada": bool(ligada),
            "do_dia": do_dia}



def _instrucao_do_momento(preparo: dict[str, Any], *, agora: str, usuario: str,
                          versao: str, onde: str = "") -> str:
    """A instrução do modelo, com o retrato desta instalação no pé.

    **O QUE MUDA DE UM TURNO PARA O OUTRO VAI NO FIM.** A data, a hora e a tela
    de onde se perguntou são as únicas linhas que mudam no meio de uma conversa;
    deixando-as por último, o começo da instrução fica idêntico de um turno para
    o outro — e é o começo que o provedor reaproveita.
    """
    nome = PROV.PROVEDORES[preparo["provedor"]]["nome"]
    escrita = ("LIGADA" if preparo["escrita_ligada"] else "DESLIGADA")
    linhas = [
        INSTRUCAO,
        "ONDE VOCÊ ESTÁ AGORA:",
        f"    - Versão do sistema: {versao or 'não informada'}.",
        f"    - Quem pediu: {usuario or 'não identificado'}.",
        f"    - Provedor: {nome}, no modelo {preparo['modelo']}.",
        f"    - Ferramentas que mudam o sistema: {escrita}.",
        f"    - Turnos desta sessão: no máximo {preparo['teto_de_turnos']}, e o "
        f"último é o que fecha a conta. Vá direto ao que interessa.",
    ]
    if onde:
        linhas.append(
            f"    - Tela de onde se perguntou: {onde}. Se o problema for de "
            f"outra tela, confirme antes de concluir.")
    linhas.append(f"    - Data e hora: {agora}.")
    if not preparo["escrita_ligada"]:
        linhas += ["", SEM_ESCRITA]
    return "\n".join(linhas)


# ---------------------------------------------------------- a conversa


def _argumentos(texto: Any) -> dict:
    """Os argumentos gravados, de volta em dicionário. Quebrado devolve vazio."""
    if isinstance(texto, dict):
        return texto
    try:
        achado = json.loads(str(texto or "") or "{}")
    except ValueError:
        return {}
    return achado if isinstance(achado, dict) else {}


def _poupar(eventos: list[dict]) -> list[dict]:
    """Tira do que é REENVIADO o resultado antigo e grande, sem perder o rastro.

    **O QUE ISTO NÃO FAZ: apagar o que ele leu.** O `ag_passos` continua com o
    texto inteiro, e a tela continua mostrando o texto inteiro. O que muda é só
    o que volta ao provedor no turno seguinte — e é aí que estava o gasto, porque
    a conversa inteira é reenviada a cada turno.

    **A CONTA É POR POSIÇÃO.** Ficam inteiras as últimas `RESULTADOS_INTEIROS`
    respostas de ferramenta, contando de trás para frente: o que ele acabou de
    ler nunca é podado, e a poda não depende de o resultado ter sido grande ou
    pequeno. Resultado abaixo do piso fica como está, porque resumir o que já é
    curto só tira dele o que estava à mão.

    Devolve uma lista nova quando há o que podar; sem nada a podar, devolve a
    mesma lista que recebeu — e ninguém a muta, porque ela é a conversa
    recém-montada para este turno e vive só até o fim dele.
    """
    respostas = [resultado
                 for evento in eventos if evento.get("tipo") == "tool"
                 for resultado in (evento.get("resultados") or [])]
    if len(respostas) <= RESULTADOS_INTEIROS:
        return eventos
    cortados = {id(resultado)
                for resultado in respostas[:-RESULTADOS_INTEIROS]
                if len(str(resultado.get("conteudo") or "")) > PISO_DE_RESULTADO_INTEIRO}
    if not cortados:
        return eventos
    saida: list[dict] = []
    for evento in eventos:
        if evento.get("tipo") != "tool":
            saida.append(evento)
            continue
        saida.append({**evento, "resultados": [
            {**resultado, "conteudo": RESULTADO_RESUMIDO.format(
                nome=str(resultado.get("nome") or "a ferramenta"),
                tamanho=len(str(resultado.get("conteudo") or "")))}
            if id(resultado) in cortados else resultado
            for resultado in (evento.get("resultados") or [])]})
    return saida


def _conversa(pedidos: list[str], passos: list[Any]) -> list[dict]:
    """Os passos gravados, traduzidos para o formato neutro do transporte.

    **A ORDEM É A DO BANCO, e não a de memória.** Se um dia a gravação mudar, a
    conversa que o modelo recebe muda junto — e é isso que faz o que a tela
    mostra ser, palavra por palavra, o que ele leu.

    **E ELA É FIEL: o que sai daqui é o que está gravado.** Quem poda é o
    `_poupar`, e quem o chama é só quem fala com o provedor — é por isso que ele
    não mora aqui dentro. Esta função também monta a conversa que o console
    DESENHA (`retrato`), e podar aqui mostraria ao oficial um resumo onde o
    resultado inteiro está guardado: a tela passaria a mentir sobre o que o
    agente leu, que é justamente o que a poda não pode fazer.
    """
    eventos: list[dict] = [{"tipo": "user", "texto": p} for p in pedidos if p]
    i = 0
    total = len(passos)
    while i < total:
        passo = passos[i]
        tipo = str(passo["tipo"])
        if tipo == AG.PEDIDO:
            eventos.append({"tipo": "user", "texto": str(passo["conteudo"] or "")})
            i += 1
            continue
        if tipo in (AG.TEXTO, AG.FERRAMENTA):
            textos: list[str] = []
            chamadas: list[dict] = []
            while i < total and str(passos[i]["tipo"]) in (AG.TEXTO, AG.FERRAMENTA):
                atual = passos[i]
                if str(atual["tipo"]) == AG.TEXTO:
                    textos.append(str(atual["conteudo"] or ""))
                else:
                    chamadas.append({"id": str(atual["chamada_id"] or ""),
                                     "nome": str(atual["ferramenta"] or ""),
                                     "argumentos": _argumentos(atual["argumentos"])})
                i += 1
            eventos.append({"tipo": "assistant",
                            "texto": "\n".join(t for t in textos if t),
                            "chamadas": chamadas})
            continue
        if tipo == AG.RESULTADO:
            resultados: list[dict] = []
            while i < total and str(passos[i]["tipo"]) == AG.RESULTADO:
                atual = passos[i]
                resultados.append({"id": str(atual["chamada_id"] or ""),
                                   "nome": str(atual["ferramenta"] or ""),
                                   "conteudo": str(atual["conteudo"] or ""),
                                   "erro": bool(atual["erro"])})
                i += 1
            eventos.append({"tipo": "tool", "resultados": resultados})
            continue
        # `AVISO` é recado para a tela e não vai ao provedor: ele descreve o
        # que a CASA fez (parar por teto, recusar por segredo), e mandá-lo de
        # volta faria o modelo comentar a mecânica em vez do problema.
        i += 1
    return _completar(eventos)


def _completar(eventos: list[dict]) -> list[dict]:
    """Fecha todo pedido de ferramenta com um resultado.

    O provedor recusa o pedido inteiro quando falta um resultado — e o caso
    acontece de verdade: falta luz, alguém fecha o console, o processo cai
    entre a gravação do pedido e a do resultado. Sem este conserto, a sessão
    interrompida ficaria irrecuperável, e o trabalho dela perdido.
    """
    saida: list[dict] = []
    i = 0
    total = len(eventos)
    while i < total:
        evento = eventos[i]
        saida.append(evento)
        i += 1
        chamadas = evento.get("chamadas") or []
        if evento.get("tipo") != "assistant" or not chamadas:
            continue
        seguinte = (eventos[i] if i < total
                    and eventos[i].get("tipo") == "tool" else None)
        if seguinte is None:
            saida.append({"tipo": "tool",
                          "resultados": [{"id": c["id"], "nome": c["nome"],
                                          "conteudo": INTERROMPIDO,
                                          "erro": True} for c in chamadas]})
            continue
        i += 1
        presentes = {str(r.get("id") or "") for r in seguinte.get("resultados") or []}
        faltando = [c for c in chamadas if str(c["id"]) not in presentes]
        if faltando:
            seguinte = {"tipo": "tool",
                        "resultados": list(seguinte.get("resultados") or [])
                        + [{"id": c["id"], "nome": c["nome"],
                            "conteudo": INTERROMPIDO, "erro": True}
                           for c in faltando]}
        saida.append(seguinte)
    return saida


# ------------------------------------------------------------- a gravação


def _grava_pedido(con: sqlite3.Connection, sessao_id: int, *, pedido: str,
                  agora: str) -> None:
    """Grava a fala do oficial. **ESCREVE.** O texto já vem mascarado."""
    AG.registrar_passo(con, sessao_id, ordem=AG.proxima_ordem(con, sessao_id),
                       tipo=AG.PEDIDO, conteudo=pedido, agora=agora)


def _grava_turno(con: sqlite3.Connection, sessao_id: int, *, texto: str,
                 chamadas: list[dict], agora: str) -> None:
    """Grava o que o modelo disse e o que ele pediu. **ESCREVE.**

    O texto e os argumentos já vêm mascarados de quem chamou. Mascarar de novo
    aqui seria a segunda régua — e a segunda régua é a que diverge.
    """
    ordem = AG.proxima_ordem(con, sessao_id)
    if texto:
        AG.registrar_passo(con, sessao_id, ordem=ordem, tipo=AG.TEXTO,
                           conteudo=texto, agora=agora)
        ordem += 1
    for chamada in chamadas:
        AG.registrar_passo(con, sessao_id, ordem=ordem, tipo=AG.FERRAMENTA,
                           ferramenta=chamada["nome"],
                           chamada_id=chamada["id"],
                           argumentos=json.dumps(chamada["argumentos"],
                                                 ensure_ascii=False),
                           agora=agora)
        ordem += 1


def _grava_resultados(con: sqlite3.Connection, sessao_id: int, *,
                      resultados: list[dict], agora: str) -> None:
    """Grava o que cada ferramenta devolveu. **ESCREVE.**"""
    ordem = AG.proxima_ordem(con, sessao_id)
    for resultado in resultados:
        AG.registrar_passo(con, sessao_id, ordem=ordem, tipo=AG.RESULTADO,
                           ferramenta=resultado["nome"],
                           chamada_id=resultado["id"],
                           conteudo=resultado["conteudo"],
                           erro=bool(resultado["erro"]), agora=agora)
        ordem += 1


def _aviso(con: sqlite3.Connection, sessao_id: int, texto: str, *,
           agora: str) -> None:
    """Grava um recado para quem lê a tela, e não para o modelo. **ESCREVE.**"""
    AG.registrar_passo(con, sessao_id, ordem=AG.proxima_ordem(con, sessao_id),
                       tipo=AG.AVISO, conteudo=texto, agora=agora)


# ---------------------------------------------------------------- o laço


def _rodar(db: Any, *, sessao_id: int, pedidos: list[str], preparo: dict,
           pasta_de_dados: Any, raiz: Any, usuario: str, versao: str,
           app: Any, hora: Callable[[], str], prazo: int,
           maximo_de_saida: int, onde: str = "") -> dict[str, Any]:
    """O laço. Devolve como terminou — e nunca levanta por falha de provedor.

    Falha de rede, chave recusada e crédito no fim são **estados da sessão**, e
    não exceções: elas ficam gravadas com a frase que explica o que houve, e a
    tela mostra o trabalho que já tinha sido feito. Um `raise` aqui perderia o
    diagnóstico inteiro por causa da última chamada.
    """
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        sessao = AG.ler_sessao(con, sessao_id)
    # OS NÚMEROS SOMAM ATRAVÉS DAS RETOMADAS. O teto de turnos vale por rodada
    # — cada fala nova do oficial é uma decisão dele, e é o humano que segura o
    # gasto —, mas o que já se gastou é DA SESSÃO. Gravar só a última rodada
    # faria a tela dizer um preço que ninguém pagou.
    turnos_antes = int(sessao["turnos"] or 0) if sessao else 0
    entrada_antes = int(sessao["tokens_de_entrada"] or 0) if sessao else 0
    saida_antes = int(sessao["tokens_de_saida"] or 0) if sessao else 0

    turnos = 0
    entrada = 0
    saida = 0
    estado = AG.LIMITE
    erro = ""
    modelo = str(preparo["modelo"])

    def _fecha(con: sqlite3.Connection, situacao: str, falha: str) -> None:
        """Fecha a conta da sessão. **ESCREVE.** Soma o que havia com o de agora."""
        AG.atualizar_sessao(con, sessao_id, estado=situacao,
                            turnos=turnos_antes + turnos,
                            tokens_de_entrada=entrada_antes + entrada,
                            tokens_de_saida=saida_antes + saida,
                            erro=falha, agora=hora(), modelo=modelo)

    # O ORÇAMENTO ACABOU, E ELE NÃO É MAIS UM `break` SECO — problema #68.
    #
    # POR QUE ISTO MUDOU. As duas paradas do topo do laço encerravam a rodada, e
    # quem terminava era o `break`: nenhuma chamada era feita, o modelo não
    # escrevia nada, e a sessão ficava sem uma linha do que ele tinha apurado.
    # Na sessão 1 desta instalação isso custou **1.420.421 tokens** pagos e um
    # console mostrando a conversa inteira, cheia de medição, e nenhuma
    # conclusão — e o pedido seguinte voltou, porque o teto contava por rodada.
    #
    # Agora o `forcado` diz que o turno que vem é o DE FECHO: ele é pedido sem
    # ferramenta nenhuma, e o que o modelo escrever ali é o relatório do que viu.
    # A rodada para igual, e para com resposta.
    forcado = False
    while True:
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            ligada = AG.escrita_ligada(con)
            passos = AG.passos_da_sessao(con, sessao_id)

        if not forcado and turnos >= int(preparo["teto_de_turnos"]):
            estado = AG.LIMITE
            # O `erro` DESTA SESSÃO É «POR QUE PAROU», e a tela o mostra como
            # isso (agente_sessao.html). Ele ficava VAZIO justamente quando a
            # parada era no teto — e é aí que a pergunta existe: o #68 é alguém
            # lendo «passou do limite» sem saber de qual limite se tratava.
            erro = (f"Esta rodada parou no teto de turnos "
                    f"({preparo['teto_de_turnos']}).")
            with db.transaction() as con:
                _aviso(con, sessao_id,
                       f"Parei no teto de {preparo['teto_de_turnos']} turnos "
                       f"desta rodada. Vou pedir o resumo do que já foi apurado, "
                       f"sem ferramenta nenhuma; para continuar o trabalho, "
                       f"escreva de novo no console — a sessão retoma de onde "
                       f"parou, com tudo o que já foi lido.",
                       agora=hora())
            forcado = True

        # **O TETO É DA SESSÃO, E NÃO DESTA RODADA** — a diferença é o #68. Os
        # dois contadores nascem em zero em cada rodada, e conferir o teto contra
        # eles deixa a sessão gastar o teto INTEIRO de novo a cada pedido novo.
        # Somado ao que já está gravado, ele passa a ser o que o nome promete.
        gasto = entrada_antes + saida_antes + entrada + saida
        if not forcado and gasto >= TETO_DE_TOKENS:
            estado = AG.LIMITE
            erro = (f"Esta sessão já passou de {TETO_DE_TOKENS} tokens "
                    f"({gasto} até aqui, somadas todas as rodadas dela).")
            with db.transaction() as con:
                _aviso(con, sessao_id,
                       f"Parei porque esta sessão já passou de {TETO_DE_TOKENS} "
                       f"tokens ({gasto} até aqui, somadas todas as rodadas "
                       f"dela). Isso é sinal de que alguma coisa saiu do "
                       f"controle. Vou pedir o resumo do que já foi apurado, sem "
                       f"ferramenta nenhuma; para continuar, comece uma sessão "
                       f"nova — esta já leu mais do que precisava.", agora=hora())
            forcado = True

        instrucao = _instrucao_do_momento(preparo, agora=hora(),
                                          usuario=usuario, versao=versao,
                                          onde=onde)
        ferramentas = FER.esquemas(escrita=bool(ligada))
        if forcado:
            # O FECHO VAI SEM CATÁLOGO. Com as ferramentas à mão ele leria mais
            # uma vez — e a rodada acabaria do mesmo jeito, agora sem a resposta,
            # que é a única coisa que ainda dá para ter.
            instrucao = f"{instrucao}\n\n{INSTRUCAO_DE_FECHO}"
            ferramentas = []
        # **A PODA É SÓ DO QUE VAI AO PROVEDOR, E ELA É DECLARADA AQUI.** Este é
        # o único ponto do módulo em que a conversa que sobe difere da que a tela
        # desenha — e ele é um `_poupar(...)` explícito, e não um `if` lá dentro,
        # para que quem leia a gravação saiba que o registro está inteiro.
        conversa = _poupar(_conversa(pedidos, passos))

        try:
            resposta = PROV.conversar(
                pasta_de_dados, provedor=preparo["provedor"],
                sistema=instrucao, conversa=conversa,
                ferramentas=ferramentas,
                modelo=modelo, maximo_de_saida=maximo_de_saida, prazo=prazo)
        except PROV.AgenteError as falha:
            estado = AG.ERRO
            erro = str(falha)
            with db.transaction() as con:
                _aviso(con, sessao_id, f"A conversa parou: {falha}",
                       agora=hora())
            break

        turnos += 1
        entrada += int(resposta.get("entrada") or 0)
        saida += int(resposta.get("saida") or 0)
        modelo = str(resposta.get("modelo") or modelo)

        chamadas = [{"id": str(c.get("id") or f"chamada_{turnos}_{i}"),
                     "nome": str(c.get("nome") or ""),
                     "argumentos": _argumentos(c.get("argumentos"))}
                    for i, c in enumerate(resposta.get("chamadas") or [], 1)]

        try:
            # A ESCOLHA AQUI É DECLARADA, COMO MANDA A BARREIRA, e é a frouxa:
            # o texto do modelo é prosa com cabeçalho em maiúsculas — «O QUE EU
            # VI» —, e a passagem ampla de nomes comeria justamente o cabeçalho
            # do relatório, que é o produto desta tela. O que continua sendo
            # removido é tudo o que identifica pessoa: CPF, e-mail, telefone,
            # IP, segredo, documento, endereço, data pessoal e nome rotulado.
            #
            # E o que sustenta a escolha frouxa é a de cima: o que pode trazer
            # nome de gente para dentro da conversa — o banco e o problema
            # anotado — é declarado como dado de pessoa (`nomes_livres=True`) e
            # chega aqui já mascarado. Nome de pessoa não atravessa, nome de
            # código atravessa: é a régua da ajuda, e ela vale igual aqui.
            texto = _seguro(resposta.get("texto"), nomes_livres=False)
        except PRIV.PrivacidadeError as recusa:
            # O MODELO ESCREVEU ALGO QUE A CASA NÃO DEIXA SAIR. Isso não
            # deveria acontecer — ele só viu dado mascarado —, e é exatamente
            # por isso que a conferência existe: o dia em que acontecer, o
            # certo é parar e contar, e não gravar.
            estado = AG.ERRO
            erro = f"A resposta do modelo foi bloqueada pela barreira: {recusa}"
            with db.transaction() as con:
                _aviso(con, sessao_id, erro, agora=hora())
            break

        try:
            guardadas = [{**c, "argumentos": _argumentos(
                _seguro(json.dumps(c["argumentos"], ensure_ascii=False),
                        nomes_livres=False))} for c in chamadas]
        except PRIV.PrivacidadeError as recusa:
            estado = AG.ERRO
            erro = (f"Os argumentos de uma ferramenta foram bloqueados pela "
                    f"barreira: {recusa}")
            with db.transaction() as con:
                _aviso(con, sessao_id, erro, agora=hora())
            break

        if not chamadas and not texto:
            # O MODELO RESPONDEU VAZIO — E ISSO ERA SILÊNCIO PURO. Problema #74.
            #
            # `_grava_turno` não escreve nada quando não há texto nem ferramenta,
            # e a rodada seguia para o `if not chamadas` daqui de baixo e fechava
            # como CONCLUIDA: quem perguntou ficava sem resposta, **sem erro e
            # sem aviso**, e o console parecia travado — a conversa com os passos
            # de antes e nada depois.
            #
            # E O PROVEDOR JÁ DIZIA POR QUÊ: `parou` vem de `finish_reason`, era
            # devolvido por `conversar` e **ninguém o lia**. Quando ele diz
            # `length`, o modelo gastou o teto de saída (`maximo_de_saida`)
            # pensando e devolveu o conteúdo vazio — que é o caso clássico dos
            # modelos de raciocínio. Aqui ele não é adivinhado: vai escrito.
            parou = str(resposta.get("parou") or "")
            estado = AG.ERRO
            erro = ("O modelo respondeu sem texto nenhum"
                    + (" e disse que parou por limite de tamanho da resposta"
                       if parou == "length" else "")
                    + (f" (o provedor devolveu «{parou}»)" if parou and parou != "length"
                       else "")
                    + ". Escreva de novo para ele responder: a conversa e tudo o "
                      "que já foi lido continuam aqui.")
            with db.transaction() as con:
                _aviso(con, sessao_id, erro, agora=hora())
            break

        with db.transaction() as con:
            _grava_turno(con, sessao_id, texto=texto, chamadas=guardadas,
                         agora=hora())
            _fecha(con, AG.ABERTA, "")

        # O FECHO VEM ANTES DO «ACABOU», E A ORDEM AQUI NÃO É DETALHE — 18/09/2026.
        # `forcado` quer dizer «esta rodada parou no teto», e a sessão que parou no
        # teto PAROU NO TETO, mesmo quando o modelo obedece ao pedido de fecho e
        # responde só o resumo. Na ordem antiga esse resumo — que é justamente o
        # caso bom — caía no `if not chamadas` de baixo e a sessão fechava como
        # CONCLUIDA: o recado da tela diria «terminou» sobre um trabalho que parou
        # no meio, e quem lê pararia de continuar. **Carimbo que mente é pior que
        # carimbo nenhum**, e este mentia sobre o motivo de a rodada ter acabado.
        if forcado:
            # A GUARDA NÃO É ZELO: `forcado` pula as duas paradas do topo, e sem
            # esta linha uma resposta teimosa — o provedor não é obrigado a
            # obedecer ao «não há ferramenta» — faria a rodada seguir sem
            # orçamento nenhum, para sempre. O texto que o modelo escreveu já
            # está gravado; o que não acontece é a ferramenta.
            estado = AG.LIMITE
            if chamadas:
                with db.transaction() as con:
                    _aviso(con, sessao_id,
                           "O turno de fecho voltou pedindo ferramenta, e ela não foi "
                           "executada: o orçamento desta rodada acabou. Escreva de "
                           "novo no console para continuar de onde parou.",
                           agora=hora())
            break

        if not chamadas:
            estado = AG.CONCLUIDA
            break

        # AS FERRAMENTAS RODAM FORA DA TRANSAÇÃO, uma a uma. Cada uma abre a
        # sua — e a de escrita abre `BEGIN IMMEDIATE` por dentro.
        resultados = []
        for chamada in chamadas:
            ctx = FER.Contexto(db=db, raiz=raiz, pasta_de_dados=pasta_de_dados,
                               agora=hora(), usuario=usuario,
                               sessao_id=sessao_id, versao=versao, app=app)
            devolvido = FER.executar(ctx, chamada["nome"], chamada["argumentos"])
            resultados.append({"id": chamada["id"], "nome": devolvido["ferramenta"],
                               "conteudo": devolvido["conteudo"],
                               "erro": bool(devolvido["erro"])})

        with db.transaction() as con:
            _grava_resultados(con, sessao_id, resultados=resultados, agora=hora())
            _fecha(con, AG.ABERTA, "")

    with db.transaction() as con:
        _fecha(con, estado, erro)
    return {"estado": estado, "turnos": turnos, "entrada": entrada,
            "saida": saida, "erro": erro}


# ------------------------------------------------ quem ficou sem resposta


def recuperar_sessoes_interrompidas(con: sqlite3.Connection, *,
                                    agora: str) -> int:
    """Fecha as sessões que ficaram ABERTAS porque o programa parou no meio.
    **ESCREVE.** Devolve quantas fechou.

    **UMA SESSÃO ABERTA É UMA SESSÃO QUE NINGUÉM CONSEGUE CONTINUAR**, e é
    desta contradição que esta função nasce: `responder` recusa sessão aberta —
    «alguém está rodando agora» —, e é essa recusa que impede duas rodadas da
    mesma conversa. Só que fechar o console no meio de um turno, ou faltar luz,
    deixa exatamente essa marca; a sessão ficaria presa para sempre, com o
    diagnóstico já pago dentro dela e sem ninguém podendo continuá-lo.

    Então na abertura do banco o que ficou ABERTO vira INTERROMPIDO, com o aviso
    gravado na própria sessão. Ela volta a aceitar a fala do oficial, e o pedido
    de ferramenta que ficou sem resultado é preenchido pelo `_completar` — que é
    o que faz o provedor aceitar a conversa de volta.

    **É IDEMPOTENTE**, como a recuperação das folhas presas: sessão já fechada
    não se move de novo, e chamar duas vezes não escreve o aviso duas vezes.
    """
    abertas = list(con.execute(
        "SELECT id, turnos, tokens_de_entrada, tokens_de_saida FROM ag_sessoes "
        "WHERE estado = ? ORDER BY id", (AG.ABERTA,)))
    for sessao in abertas:
        _aviso(con, int(sessao["id"]), AVISO_DE_INTERRUPCAO, agora=agora)
        AG.atualizar_sessao(
            con, int(sessao["id"]), estado=AG.INTERROMPIDA,
            turnos=int(sessao["turnos"] or 0),
            tokens_de_entrada=int(sessao["tokens_de_entrada"] or 0),
            tokens_de_saida=int(sessao["tokens_de_saida"] or 0),
            erro="A rodada anterior não terminou: o programa foi fechado antes "
                 "de ela terminar.", agora=agora)
    return len(abertas)


# --------------------------------------------------------- o que a tela pede


def _prepara_o_texto(texto: Any, *, o_que: str,
                     dica: str = "") -> str:
    """Confere e mascara a fala do oficial. Devolve o texto que pode sair.

    **A MÁSCARA ACONTECE ANTES DE QUALQUER GRAVAÇÃO.** Gravar sem mascarar para
    mascarar depois deixaria o CPF no banco — e o banco viaja no backup. Quem
    recusa é a barreira (`ajuda_privacidade`), e a frase da recusa diz o que
    fazer, porque erro de regra não é HTTP 500.
    """
    limpo = str(texto or "").strip()
    if not limpo:
        raise AgenteRecusado(o_que)
    try:
        return _seguro(limpo, nomes_livres=True)
    except PRIV.PrivacidadeError as recusa:
        raise AgenteRecusado(
            f"O seu pedido não pode sair desta casa: {recusa}{dica}") from recusa


def _abrir_rodada(db: Any, *, pedido: str, pasta_de_dados: Any, raiz: Any,
                  agora: Any, usuario: str, versao: str = "", app: Any = None,
                  provedor: Any = None, modelo: Any = None,
                  prazo: int = PROV.PRAZO_PADRAO,
                  maximo_de_saida: int = MAXIMO_DE_SAIDA,
                  onde: str = "") -> tuple[int, threading.Thread]:
    """Abre a sessão e solta a rodada. Devolve `(id da sessão, linha)`. **ESCREVE.**

    **A SESSÃO E A FALA VÃO PARA O BANCO ANTES DE A LINHA EXISTIR.** Se o
    programa cair no meio, o que se perdeu foi a leitura — e não a pergunta,
    que ficou gravada com o estado que a recuperação da abertura conserta.

    A ORDEM DAS CONFERÊNCIAS É A DO MAIS BARATO PARA O MAIS CARO, e há teste
    que a fixa. A fala se confere sem abrir o banco e sem ler chave nenhuma
    (`_prepara_o_texto`); a falta de chave e o teto do dia custam uma conexão e
    a leitura do arquivo da credencial (`_preparo`). Quem manda o pedido em
    branco ouve isso primeiro, e ouve uma coisa só — a que a conferência dele
    viu. Ela não promete que o resto está em ordem.

    (A ordem contrária também tem argumento — quem não tem chave reescreveria a
    frase à toa tirando um CPF —, e ela foi considerada e descartada: o pedido
    vazio é o erro que mais acontece no balcão, e mandá-lo esperar pela chave
    faz a pessoa corrigir a coisa errada primeiro.)
    """
    guardado = _prepara_o_texto(
        pedido,
        o_que="Escreva o que você quer que o agente apure. Um pedido vazio gasta "
              "um turno inteiro para o modelo perguntar o que você quis dizer.",
        dica=" Tire o dado de pessoa do texto e descreva o que você quer pelo "
             "que ele é — «o cadastro do titular», em vez do nome ou do número.")
    hora = _relogio(agora)
    preparo = _preparo(db, pasta_de_dados=pasta_de_dados, hoje=hora(),
                       provedor=provedor, modelo=modelo)
    with db.transaction() as con:
        sessao_id = AG.abrir_sessao(con, titulo=_titulo(guardado),
                                    pedido=guardado,
                                    provedor=preparo["provedor"],
                                    modelo=preparo["modelo"], agora=hora(),
                                    criada_por=usuario)
        _grava_pedido(con, sessao_id, pedido=guardado, agora=hora())
    linha = _despachar(db, sessao_id=sessao_id, preparo=preparo,
                       onde=_onde_estamos(onde), pasta_de_dados=pasta_de_dados,
                       raiz=raiz, usuario=usuario, versao=versao, app=app,
                       hora=hora, prazo=prazo, maximo_de_saida=maximo_de_saida)
    return int(sessao_id), linha


def _retomar_rodada(db: Any, sessao_id: int, *, pedido: str,
                    pasta_de_dados: Any, raiz: Any, agora: Any, usuario: str,
                    versao: str = "", app: Any = None, provedor: Any = None,
                    modelo: Any = None, prazo: int = PROV.PRAZO_PADRAO,
                    maximo_de_saida: int = MAXIMO_DE_SAIDA,
                    onde: str = "") -> tuple[int, threading.Thread]:
    """Continua uma sessão que já existe. Devolve `(id, linha)`. **ESCREVE.**

    **AS DUAS RECUSAS AQUI SÃO A MESMA COISA DITA DUAS VEZES**, e é de
    propósito: `ABERTA` no banco e «rodando agora» na memória são o mesmo fato
    visto de dois lugares — e um deles sobrevive à queda do programa, enquanto o
    outro não. Recusar por qualquer dos dois é recusar a mesma coisa: **um
    segundo laço escrevendo por cima do primeiro.**
    """
    guardado = _prepara_o_texto(
        pedido, o_que="Escreva o que você quer acrescentar à conversa.")
    hora = _relogio(agora)
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        sessao = AG.ler_sessao(con, int(sessao_id))
    if not sessao:
        raise AgenteRecusado(f"Não achei a sessão #{int(sessao_id)}.")
    if str(sessao["estado"]) == AG.ABERTA or em_curso(sessao_id):
        raise AgenteRecusado(
            f"A sessão #{int(sessao_id)} está rodando agora. Espere ela "
            f"terminar — o que ela já apurou aparece na tela enquanto isso —, "
            f"ou comece outra.")

    preparo = _preparo(db, pasta_de_dados=pasta_de_dados, hoje=hora(),
                       provedor=provedor or sessao["provedor"],
                       modelo=modelo if modelo is not None else sessao["modelo"])
    with db.transaction() as con:
        _grava_pedido(con, int(sessao_id), pedido=guardado, agora=hora())
    linha = _despachar(db, sessao_id=int(sessao_id), preparo=preparo,
                       onde=_onde_estamos(onde), pasta_de_dados=pasta_de_dados,
                       raiz=raiz, usuario=usuario, versao=versao, app=app,
                       hora=hora, prazo=prazo, maximo_de_saida=maximo_de_saida)
    return int(sessao_id), linha


def iniciar(db: Any, *, pedido: str, pasta_de_dados: Any, raiz: Any,
            agora: Any, usuario: str, versao: str = "", app: Any = None,
            provedor: Any = None, modelo: Any = None,
            prazo: int = PROV.PRAZO_PADRAO,
            maximo_de_saida: int = MAXIMO_DE_SAIDA,
            onde: str = "") -> int:
    """Abre a sessão e **devolve o id na hora**. A rodada corre em segundo plano.

    É o que o console usa. Antes disto a tela chamava `pedir` e esperava: um
    turno leva dezenas de segundos, e uma sessão inteira pode levar minutos —
    tempo em que quem pediu ficava olhando uma página parada, sem saber se o
    agente estava pensando ou se o sistema tinha morrido.

    **Não levanta por falha de provedor** — como `pedir`, ela vira estado da
    sessão e aparece na tela. Levanta só quando o pedido não podia sair daqui.
    """
    sessao_id, _linha = _abrir_rodada(
        db, pedido=pedido, pasta_de_dados=pasta_de_dados, raiz=raiz,
        agora=agora, usuario=usuario, versao=versao, app=app,
        provedor=provedor, modelo=modelo, prazo=prazo,
        maximo_de_saida=maximo_de_saida, onde=onde)
    return sessao_id


def continuar(db: Any, sessao_id: int, *, pedido: str, pasta_de_dados: Any,
              raiz: Any, agora: Any, usuario: str, versao: str = "",
              app: Any = None, provedor: Any = None, modelo: Any = None,
              prazo: int = PROV.PRAZO_PADRAO,
              maximo_de_saida: int = MAXIMO_DE_SAIDA,
              onde: str = "") -> int:
    """Continua a conversa e **devolve o id na hora**. A rodada corre atrás."""
    ident, _linha = _retomar_rodada(
        db, sessao_id, pedido=pedido, pasta_de_dados=pasta_de_dados, raiz=raiz,
        agora=agora, usuario=usuario, versao=versao, app=app, provedor=provedor,
        modelo=modelo, prazo=prazo, maximo_de_saida=maximo_de_saida, onde=onde)
    return ident


def andamento(db: Any, sessao_id: int, *, desde: int = 0,
              mudanca_desde: int = 0) -> dict:
    """Como a sessão está AGORA, e só o que ainda não foi desenhado. **SÓ LÊ.**

    **É ESTA FUNÇÃO QUE A TELA CHAMA A CADA SEGUNDO**, e por isso ela é de
    leitura pura: nada aqui consome contador, abre transação de escrita ou
    depende de o agente estar vivo. Uma tela que perguntasse «como está?» e
    escrevesse alguma coisa ficaria presa no `busy_timeout` enquanto o balcão
    lavra — a regra da casa desde 25/08.

    `desde` e `mudanca_desde` são os CURSORES: quem desenha guarda até onde leu
    e recebe só o que veio depois. Sem eles, a cada segundo a tela releria a
    conversa inteira para descobrir que nada mudou — e o resultado de uma
    ferramenta pode ter dezenas de linhas.
    """
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        sessao = AG.ler_sessao(con, int(sessao_id))
        if not sessao:
            raise AgenteRecusado(f"Não achei a sessão #{int(sessao_id)}.")
        novos = [dict(p) for p in AG.passos_desde(con, int(sessao_id),
                                                  ordem=desde)]
        mudancas = [dict(m) for m in AG.mudancas_desde(con, int(sessao_id),
                                                      mudanca_id=mudanca_desde)]
        total = con.execute(
            "SELECT COUNT(*) c FROM ag_passos WHERE sessao_id = ?",
            (int(sessao_id),)).fetchone()["c"]
    return {
        "sessao": dict(sessao),
        "rodando": em_curso(sessao_id),
        "recado": recado_do_fim(dict(sessao)),
        # O SELO VAI PRONTO, E NÃO SÓ O ESTADO. Quem desenha a tela ao vivo
        # precisa trocar a palavra e a cor do selo a cada segundo, e a régua
        # dessa troca é a de `agente_schema.selo_do_estado`, a mesma que a tela
        # usa na primeira carga. Mandar só `estado` faria o JavaScript aprender
        # a tradução — e a segunda tradução diria outra coisa.
        "selo": AG.selo_do_estado(sessao["estado"]),
        "passos": novos,
        "mudancas": mudancas,
        # O CURSOR VAI COM O ÚLTIMO PASSO, e não com a contagem: `ordem` é o
        # número que o banco usa para ordenar, e é ele que não deixa um passo
        # nascer fora da tela se duas rodadas se cruzarem.
        "proximo": (int(novos[-1]["ordem"]) if novos else int(desde or 0)),
        "mudanca_proxima": (int(mudancas[-1]["id"]) if mudancas
                            else int(mudanca_desde or 0)),
        "total_de_passos": int(total),
    }


def pedir(db: Any, *, pedido: str, pasta_de_dados: Any, raiz: Any, agora: Any,
          usuario: str, versao: str = "", app: Any = None,
          provedor: Any = None, modelo: Any = None,
          prazo: int = PROV.PRAZO_PADRAO,
          maximo_de_saida: int = MAXIMO_DE_SAIDA,
          onde: str = "") -> dict:
    """Abre uma sessão, roda o laço **e espera**, devolvendo o retrato. **ESCREVE.**

    O oficial escreve o que quer; o agente apura e responde. **Esta função não
    levanta por falha do provedor** — ela fica gravada na sessão, e o retrato
    volta com o estado e a frase. Levanta só quando o pedido não podia sair
    daqui: sem chave, sem teto no dia, ou pedido vazio.

    **ELA E `iniciar` SÃO A MESMA COISA COM UMA DIFERENÇA SÓ: QUEM ESPERA.** As
    duas abrem a sessão do mesmo jeito e passam pela mesma `_rodar`. Esta espera
    porque quem a chama precisa do resultado na mão — é o caminho de dentro do
    sistema, e o que a suíte usa. A tela usa `iniciar` e pergunta o andamento,
    que é o que faz o console não ficar parado.
    """
    sessao_id, linha = _abrir_rodada(
        db, pedido=pedido, pasta_de_dados=pasta_de_dados, raiz=raiz,
        agora=agora, usuario=usuario, versao=versao, app=app,
        provedor=provedor, modelo=modelo, prazo=prazo,
        maximo_de_saida=maximo_de_saida, onde=onde)
    linha.join()
    return retrato(db, sessao_id)


def responder(db: Any, sessao_id: int, *, pedido: str, pasta_de_dados: Any,
              raiz: Any, agora: Any, usuario: str, versao: str = "",
              app: Any = None, provedor: Any = None, modelo: Any = None,
              prazo: int = PROV.PRAZO_PADRAO,
              maximo_de_saida: int = MAXIMO_DE_SAIDA,
              onde: str = "") -> dict:
    """Continua uma sessão existente **e espera pelo retrato**. **ESCREVE.**

    É o que faz o console ser um console: o agente para no teto, ou termina e
    faz uma pergunta, e o oficial escreve de volta **na mesma conversa** — com
    tudo o que já foi lido ali dentro. Sem isto, continuar um diagnóstico custaria
    repetir o diagnóstico.
    """
    ident, linha = _retomar_rodada(
        db, sessao_id, pedido=pedido, pasta_de_dados=pasta_de_dados, raiz=raiz,
        agora=agora, usuario=usuario, versao=versao, app=app, provedor=provedor,
        modelo=modelo, prazo=prazo, maximo_de_saida=maximo_de_saida, onde=onde)
    linha.join()
    return retrato(db, ident)


# ------------------------------------------------------------ o que se lê


def retrato(db: Any, sessao_id: int) -> dict:
    """Uma sessão inteira: o que foi dito, o que foi pedido, o que mudou.

    **A sessão já vem com os pedidos em ordem**, e é isso que a tela desenha:
    o oficial não lê uma lista de eventos, ele lê uma conversa.

    **E ELA VEM COM OS CURSORES E COM O «ESTÁ RODANDO»**, que são o começo da
    conversa ao vivo: a tela desenha o que já existe e daí em diante pergunta a
    `/agente/andamento/<id>` pelo que vier. Os cursores saem daqui, e não são
    calculados no modelo de tela, porque quem sabe até onde se leu é quem tem a
    lista na mão — e é a mesma conta que o `andamento` faz.
    """
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        sessao = AG.ler_sessao(con, int(sessao_id))
        if not sessao:
            raise AgenteRecusado(f"Não achei a sessão #{int(sessao_id)}.")
        passos = [dict(p) for p in AG.passos_da_sessao(con, int(sessao_id))]
        mudancas = [dict(m) for m in AG.mudancas_da_sessao(con, int(sessao_id))]
    return {"sessao": dict(sessao), "passos": passos, "mudancas": mudancas,
            "conversa": _conversa([], passos),
            "rodando": em_curso(sessao_id),
            "selo": AG.selo_do_estado(sessao["estado"]),
            "recado": recado_do_fim(dict(sessao)),
            "proximo": int(passos[-1]["ordem"]) if passos else 0,
            "mudanca_proxima": int(mudancas[-1]["id"]) if mudancas else 0}


def painel(db: Any, *, pasta_de_dados: Any, hoje: Any) -> dict:
    """O que a tela do agente mostra. **SÓ LÊ.**

    Devolve a configuração, os provedores com o que cada um tem de chave, as
    últimas sessões, as últimas mudanças e quanto já se gastou hoje. Tudo em
    uma leitura só, porque a tela é uma só.
    """
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        config = AG.config_para_tela(con)
        sessoes = [dict(r) for r in AG.sessoes_recentes(con)]
        mudancas = [dict(r) for r in AG.mudancas_recentes(con)]
        do_dia = AG.contagem_do_dia(con, desde=str(hoje or "")[:10])
    return {
        "config": config,
        "provedores": PROV.catalogo_para_tela(pasta_de_dados),
        "sessoes": sessoes,
        "mudancas": mudancas,
        "do_dia": do_dia,
        "catalogo": [
            {"nome": f.nome, "descricao": f.descricao,
             "tipo": f.tipo}
            for f in FER.FERRAMENTAS],
        "avisos": _avisos(pasta_de_dados, config, do_dia),
    }


def _avisos(pasta_de_dados: Any, config: dict, do_dia: dict) -> list[str]:
    """O que a tela diz antes de alguém clicar. **SÓ LÊ.**

    **O que se avisa aqui é o que não pode surpreender depois:** que a escrita
    está ligada, que a conta está perto do teto, e que o provedor escolhido não
    tem chave. Cada aviso é uma frase que alguém leria depois e diria «eu não
    sabia» — e a tela existe para ninguém precisar dizer isso.
    """
    avisos: list[str] = []
    if config["escrita_ligada"]:
        avisos.append(
            "A escrita está LIGADA: o agente pode anotar nos problemas e abrir "
            "ou fechar módulos. Toda mudança fica registrada e volta com um "
            "clique, mas quem liga isto é você.")
    if do_dia["sessoes"] >= config["teto_de_sessoes"]:
        avisos.append(
            f"O teto de sessões de hoje ({config['teto_de_sessoes']}) já foi "
            f"atingido: o agente não responde mais até amanhã, ou até você "
            f"subir o teto.")
    prov = config["provedor_padrao"]
    if not PROV.tem_chave(pasta_de_dados, prov):
        avisos.append(
            f"O provedor escolhido ({prov}) ainda não tem chave informada — "
            f"sem ela o agente não responde.")
    return avisos


def resumo_para_a_gaveta(db: Any, *, pasta_de_dados: Any, hoje: Any) -> dict:
    """O que a gaveta mostra ANTES de alguém clicar nela. **SÓ LÊ.**

    A GAVETA É A JANELA DA AJUDA PARA QUEM MANDA, e não um segundo console:
    ela abre por cima de QUALQUER tela — é ali que o oficial está quando
    percebe o que quer apurar —, mostra a última sessão (quase sempre a que ele
    acabou de abrir), diz como ela está e deixa continuar. O histórico inteiro,
    o catálogo de ferramentas e os tetos continuam na tela do agente, que é
    onde se decide sobre eles.

    **TUDO NUMA LEITURA SÓ, e é isto que a torna possível em toda tela:** a
    configuração, a última sessão e o gasto do dia saem da mesma conexão.

    **E ELA NÃO ACONTECE EM TODA TELA — ACONTECE QUANDO A GAVETA ABRE.** O que
    mora em toda página é só a pergunta «esta pessoa pode?», respondida na
    sessão do Flask (ver `agente_web._o_agente_em_toda_tela`); quem busca este
    resumo é `/agente/gaveta`. Lia-se aqui o catálogo de provedores — que abre
    um arquivo de credencial por provedor — para desenhar uma lista que a
    gaveta não desenha, e isso seria pagar no carregamento de toda tela do
    sistema por uma caixa que a maioria nem abre.

    Os avisos são os MESMOS do console, pela mesma função: se eles divergissem,
    a gaveta diria que está tudo bem onde o console diz que a escrita está
    ligada.
    """
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        config = AG.config_para_tela(con)
        ultimas = [dict(r) for r in AG.sessoes_recentes(con, limite=1)]
        do_dia = AG.contagem_do_dia(con, desde=str(hoje or "")[:10])
    sessao = ultimas[0] if ultimas else None
    return {
        "config": config,
        "sessao": sessao,
        # RODANDO É DIFERENTE DE ABERTA, e a diferença é a que a tela precisa:
        # ABERTA quer dizer «não terminou»; RODANDO quer dizer «tem uma linha
        # viva agora». Sessão que ficou presa porque o programa parou é ABERTA e
        # não está rodando — e quem a vê precisa saber disso.
        "rodando": bool(sessao) and em_curso(sessao["id"]),
        "recado": recado_do_fim(sessao) if sessao else None,
        "do_dia": do_dia,
        "avisos": _avisos(pasta_de_dados, config, do_dia),
    }


def config_para_tela(db: Any) -> dict:
    """A configuração do agente. **SÓ LÊ.**"""
    with db.connect() as con:
        return AG.config_para_tela(con)


def salvar_config(db: Any, *, provedor: Any = None, modelo: Any = None,
                  teto_de_turnos: Any = None, teto_de_sessoes: Any = None,
                  escrita_ligada: Any = None) -> dict:
    """Grava a configuração do agente. **ESCREVE.**

    **Os tetos passam por aqui e são presos nos limites duros** — quem digita
    na tela pode escrever 900, e o agente vai obedecer a 24. Prender calado, em
    vez de recusar, é de propósito: a tela devolve o número que valeu, e a
    diferença entre o que se pediu e o que valeu fica visível no lugar de virar
    um erro que ninguém sabe explicar.
    """
    with db.transaction() as con:
        if provedor is not None:
            AG.gravar_config(con, AG.CHAVE_PROVEDOR,
                             PROV.normalizar_provedor(provedor))
        if modelo is not None:
            AG.gravar_config(con, AG.CHAVE_MODELO, str(modelo or "").strip())
        if teto_de_turnos is not None:
            AG.gravar_config(con, AG.CHAVE_TETO_TURNOS,
                             _preso(teto_de_turnos, AG.PADROES[AG.CHAVE_TETO_TURNOS],
                                    AG.TETO_MAXIMO_DE_TURNOS))
        if teto_de_sessoes is not None:
            AG.gravar_config(con, AG.CHAVE_TETO_SESSOES,
                             _preso(teto_de_sessoes, AG.PADROES[AG.CHAVE_TETO_SESSOES],
                                    AG.TETO_MAXIMO_DE_SESSOES))
        if escrita_ligada is not None:
            AG.gravar_config(con, AG.CHAVE_ESCRITA,
                             "1" if _ligado(escrita_ligada) else "0")
        return AG.config_para_tela(con)


def _preso(valor: Any, padrao: str, maximo: int) -> str:
    """O número que vale, entre 1 e o teto duro. O que não é número vira padrão."""
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        numero = int(padrao)
    return str(max(1, min(int(maximo), numero)))


def _ligado(valor: Any) -> bool:
    """Um campo de caixa de seleção: o que conta como «sim» e o que não."""
    if isinstance(valor, bool):
        return valor
    return str(valor or "").strip().lower() in ("1", "on", "true", "sim", "ligado")


def gravar_chave(pasta_de_dados: Any, provedor: Any, chave: Any) -> dict:
    """Grava a chave de um provedor **fora do banco**. **ESCREVE EM DISCO.**

    A chave vazia apaga a do provedor: é o único jeito de desligar um provedor
    sem deixar a credencial dele viva no disco. E o retorno é o catálogo, para
    a tela redesenhar sem uma segunda leitura.
    """
    prov = PROV.normalizar_provedor(provedor)
    PROV.gravar_chave(pasta_de_dados, prov, chave)
    return {"provedor": prov,
            "caminho": str(PROV.caminho_da_credencial(pasta_de_dados)),
            "provedores": PROV.catalogo_para_tela(pasta_de_dados)}


def desfazer(db: Any, mudanca_id: int, *, agora: Any, usuario: str) -> dict:
    """Volta atrás uma mudança que o agente fez. **ESCREVE.**

    É a função que faz a permissão de escrever ser defensável, e por isso ela
    não pertence à tela: quem desfaz é o domínio, com as mesmas recusas.
    """
    hora = _relogio(agora)
    return FER.desfazer(db, int(mudanca_id), agora=hora(), usuario=usuario)
