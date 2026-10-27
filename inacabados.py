"""O que começou e não terminou nesta casa — uma LENTE, e não uma segunda gaveta.

    «Sobre os expedientes, eles seriam de **abastecimento automático**, pegariam
     todos atos que começaram e não terminaram no sistema (…) Criar módulo para
     gerenciar a melhor aplicação disso, para moldar o que fica, o que sai, como
     melhora.» — o oficial, 29/08/2026

A DECISÃO DE FUNDO: A LISTA É MEDIDA NA HORA
    A tentação é criar uma linha de expediente para cada ato inacabado. **Não.**
    O ato já é o registro; uma linha ao lado dele seriam **dois lugares guardando
    o mesmo fato** — e este projeto já sabe como isso termina: o
    `normalizar_nome` copiado, o `VERSAO.txt` que dizia 3.2.1, a documentação em
    duas pastas, os modelos em duas telas. **A cópia diverge no primeiro
    conserto**, e aqui divergiria de um jeito caro: o ato seria concluído e o
    expediente continuaria aberto — que é *exatamente* o relato #24.

    Então a lista sai das tabelas onde os atos já moram. **Ato concluído sai da
    lista sozinho**, porque a lista é a pergunta e não a resposta guardada.

O QUE SE GUARDA É SÓ O QUE NÃO EXISTE EM LUGAR NENHUM
    A anotação do oficial sobre o item — quem está cuidando, até quando, o que
    falta. Uma tabela só, `ex_anotacoes`, apontando para (tabela, id). E a
    configuração de cada fonte, em `ex_fontes`.

A DIVISÃO ENTRE O CÓDIGO E A TELA
    **A fonte é declarada no código**, porque saber onde o ato mora e o que o
    termina não se digita numa tela. **A tela liga, desliga e ajusta os dias** —
    e isso mora no banco, para o oficial mexer num sábado sem programador.

    É a mesma divisão de `aj_config`: *quem pode usar a ajuda* mora no banco;
    *como a ajuda funciona* mora no código.

O QUE ELE NÃO FAZ
    **Não conclui nada.** Mostra e leva à tela do ato — concluir é lá, com as
    regras de lá. **Não cria expediente.** E **não avisa por conta própria**
    enquanto o oficial não disser quantos dias: alarme que soa sempre é alarme
    que ninguém ouve, e isto olha **640 protocolos** no primeiro dia.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from bd_nativo import banco


class InacabadoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


# ------------------------------------------------------------------- as fontes
#
# CADA FONTE DIZ ONDE O ATO MORA, O QUE O COMECOU E O QUE O TERMINA — e nada
# disso e invencao: as colunas foram lidas do esquema, uma a uma, em 29/08/2026.
#
# **O `onde` E SEMPRE A TABELA REAL**, e a consulta se monta dela. Eu ja escrevi
# `a.folha` num modulo desta mesma manha pedindo coluna que nao existe — livro e
# folha moram no ATO, e nao no assento. Por isso ha teste que **roda a consulta
# de cada fonte** contra o esquema de verdade: fonte com coluna errada fica
# vermelha na suite, e nao no balcao seis meses depois.
FONTES: tuple[dict, ...] = (
    {"chave": "NOTAS_RASCUNHO",
     "nome": "Escritura em lavratura",
     "atribuicao": "NOTAS",
     "tabela": "nt_atos",
     "onde": "COALESCE(situacao,'') = 'EM_LAVRATURA'",
     "quando": "criado_em",
     "rotulo": "interessado",
     "terminou": "quando a escritura é lavrada",
     "o_acervo": "não entra: a situação o basta — escritura do E-Ofício veio "
                 "LAVRADA, e nenhuma das 259 está em EM_LAVRATURA",
     "dias": 7,
     "tela": "notas_ato", "parametro": "ato_id"},

    # A COMUNICAÇÃO À SERVENTIA DE ORIGEM — relato #129, 14/10/2026, vindo da
    # inspeção. Código de Normas TJMA, art. 831, § 1º: substabelecimento de
    # mandato lavrado em OUTRA serventia se comunica IMEDIATAMENTE, com
    # comprovante de recebimento.
    #
    #   **ESTA FONTE LÊ A OBRIGAÇÃO, E NÃO OS CAMPOS DO ATO.** Medida pelos
    #   campos `anterior_*`, ela sumiria no dia em que alguém apagasse o nome
    #   do cartório de origem — e o relato pede aviso que só some com a
    #   providência. A linha nasce em `notas_comunicacao_origem.abrir` e só
    #   deixa de ser ABERTA por comprovante juntado ou ofício anotado.
    #
    #   **UM DIA**, porque a norma diz «imediatamente»: o prazo daqui é o de
    #   «parado», e o oficial o ajusta na tela.
    {"chave": "NOTAS_COMUNICACAO_ORIGEM",
     "nome": "Substabelecimento sem comunicação à serventia de origem",
     "atribuicao": "NOTAS",
     "tabela": "nt_comunicacoes_origem",
     "id": "ato_id",
     "onde": "situacao = 'ABERTA'",
     "quando": "nascida_em",
     "rotulo": "destinatario",
     "terminou": "quando se junta o comprovante de recebimento ou se anota "
                 "o envio do ofício, na ficha do ato",
     "o_acervo": "não entra sozinho: a obrigação nasce no lançamento ou por "
                 "ato de alguém na ficha — o acervo só entra quando alguém o "
                 "olha e lança a obrigação",
     "dias": 1,
     "tela": "notas_ato", "parametro": "ato_id"},

    {"chave": "RI_PRENOTACAO",
     "nome": "Prenotação sem ato",
     "atribuicao": "RI",
     "tabela": "ri_protocolos",
     "onde": "ato_id IS NULL AND COALESCE(situacao,'') NOT IN "
             "('CANCELADO','ENCERRADO','DEVOLVIDO')",
     "quando": "data_prenotacao",
     "rotulo": "apresentante",
     "terminou": "quando o ato sai e a prenotação se amarra a ele",
     # **ESTA FICOU CERTA POR ACIDENTE, e o acidente tem data.** As 784
     # prenotações do acervo só não aparecem aqui porque ganharam `ato_id`
     # em 28/08/2026 — antes disso eram 784 de 784 com ele vazio, e esta
     # fonte teria mostrado setenta anos de protocolo como trabalho de hoje.
     # A declaração passa a ser a razão; a coincidência não é razão.
     "o_acervo": "não entra: prenotação do acervo tem `ato_id` preenchido — "
                 "**se alguma perder o vínculo, ela volta, e aí o filtro por "
                 "origem tem de entrar aqui**",
     # O PRAZO DA PRENOTACAO E DE 20 DIAS UTEIS (40 no REURB-S), e por isso o
     # padrao daqui e menor: quem olha esta lista precisa ver o titulo ANTES de
     # o prazo vencer, e nao no dia.
     "dias": 10,
     "tela": "ri_protocolo_ver", "parametro": "protocolo_id"},

    {"chave": "RI_RASCUNHO",
     "nome": "Rascunho de ato do RI",
     "atribuicao": "RI",
     "tabela": "ri_rascunhos",
     # O `id` DESTA FONTE E O DA MATRICULA, e nao o da linha do rascunho: a tela
     # para onde ela leva e a da matricula. Fonte cujo id nao serve a tela dela
     # produz link que abre a ficha errada — e no RI isso e ficha de OUTRO
     # imovel.
     "id": "matricula_id",
     "onde": "1 = 1",
     "quando": "atualizado_em",
     "rotulo": "tipo",
     "terminou": "quando o ato é lavrado — o rascunho é apagado",
     "dias": 7,
     # `ri_rascunho_ver`, e nao `ri_ficha`: quem clica num rascunho quer ver **a
     # matricula como ela vai ficar**, que e a tela que o rascunho tem.
     "tela": "ri_rascunho_ver", "parametro": "matricula_id"},

    # A MINUTA DO RI ESPERA UMA PESSOA, E POR ISSO ENTRA AQUI — 15/09/2026.
    #
    #   Ela aparece na ficha da matrícula, que é onde quem lavra está. Mas
    #   ficha se abre de propósito: minuta de uma ficha que ninguém abre é
    #   averbação que não sai, e nada avisaria. É a lição do painel dos
    #   inacabados aplicada à peça que nasceu hoje.
    #
    #   O ACERVO NÃO ENTRA por construção: `ri_minutas` nasceu em 15/09/2026 e
    #   nenhuma carga a alimenta — as três primeiras linhas vieram de atos que
    #   a importação lavrou por engano, e são justamente o trabalho de hoje.
    {"chave": "RI_MINUTA",
     "nome": "Minuta do RI a revisar e lavrar",
     "atribuicao": "RI",
     "tabela": "ri_minutas",
     # O `id` DESTA FONTE É O DA MATRÍCULA, como no rascunho: a tela é a ficha,
     # e é nela que o painel «Minutas a revisar e lavrar» mora.
     "id": "matricula_id",
     "onde": "COALESCE(situacao,'') = 'A_REVISAR'",
     "quando": "criado_em",
     # O RÓTULO DIZ QUAL ATO É, e não só «AV» — e as duas colunas se juntam em
     # PYTHON (`_rotulo_da_linha`), porque `||` no SQL custa acoplamento e o
     # teto deste módulo é zero.
     "rotulo": "tipo",
     "rotulo_2": "numero_pretendido",
     "terminou": "quando a minuta é lavrada pela tela de sempre, ou descartada "
                 "com motivo escrito",
     "o_acervo": "não entra: `ri_minutas` nasceu em 15/09/2026 e nenhuma carga "
                 "a alimenta",
     "dias": 7,
     "tela": "ri_ficha", "parametro": "matricula_id"},

    # FICHA NOVA ABERTA E SEM UM ÚNICO ATO — 15/09/2026, e o número é o que
    # torna esta fonte possível.
    #
    #   Medido: **1.549** fichas abertas não têm ato nenhum em `ri_atos`, e
    #   listá-las seria alarme que soa sempre. Quase todas são ACERVO, onde os
    #   atos moram DENTRO do texto da ficha («AV-28/1.490») e não como linha —
    #   a lição do «AV-28 aparecendo no teor».
    #
    #   Só nas **ESTRUTURADAS** o sistema numera sozinho, e ali ficha sem ato é
    #   ficha que ninguém escriturou. São **4**: as matrículas 8, 4.010, 4.016 e
    #   4.018 — e a 4.016 é a que a AV-06 da 3.110 abriu pelo transporte, com a
    #   descrição perimétrica inteira e nenhum registro em cima.
    #
    #   E O FILTRO É `tipo_ficha`, E NÃO `origem`: das quatro, uma é `EOFICIO`,
    #   uma é `PDF_OCR` e duas são `MANUAL`. `origem` diz de onde a LINHA veio;
    #   o que decide aqui é como a ficha se escritura.
    {"chave": "RI_FICHA_SEM_ATO",
     "nome": "Ficha do RI aberta sem nenhum ato",
     "atribuicao": "RI",
     "tabela": "ri_matriculas",
     "onde": "encerrada = 0 AND COALESCE(tipo_ficha,'') = 'ESTRUTURADA' "
             "AND NOT EXISTS (SELECT 1 FROM ri_atos a "
             "WHERE a.matricula_id = ri_matriculas.id)",
     "quando": "data_abertura",
     "rotulo": "numero",
     "terminou": "quando o primeiro ato é lavrado na ficha",
     "o_acervo": "entra, e de propósito: o filtro é `tipo_ficha` e não "
                 "`origem` — as 1.545 fichas de ACERVO ficam de fora porque "
                 "nelas o ato mora dentro do teor, e não porque são antigas",
     # O PRAZO É LARGO porque abrir ficha e escriturar podem ser dias
     # diferentes — o que não pode é a ficha ficar em branco por semanas.
     "dias": 15,
     "tela": "ri_ficha", "parametro": "matricula_id"},

    {"chave": "BALCAO_PROTOCOLO",
     "nome": "Atendimento do balcão em aberto",
     "atribuicao": "ADMINISTRATIVO",
     "tabela": "cx_protocolos",
     # O ACERVO NAO VIRA ATRASO, e aqui ele quase virou 21 MIL VEZES.
     #
     #   **E o comentario que estava nesta linha media a coisa errada.** Ele
     #   dizia «os 640 abertos sao todos do E-Oficio», e 640 e o numero da
     #   situacao `ABERTO`; a condicao desta fonte e `NOT IN
     #   ('ENTREGUE','CANCELADO')`, que apanha tambem os **16.755 PAGO** e os
     #   **3.947 A_PAGAR**. Medido na producao em 30/08/2026: **21.348**, dos
     #   quais **21.342 sao do E-Oficio**. O painel anunciaria vinte e um mil
     #   pendencias, e uma lista que o balcao nao tem como zerar e uma lista
     #   que ninguem abre duas vezes.
     #
     #   Sobram **6** — os que esta casa abriu. Esse numero o balcao zera.
     #
     #   E `PAGO` **nao** entrou como situacao terminal: pago nao e entregue, e
     #   dizer que e faria sumir da lista o servico que o cliente pagou e ainda
     #   nao recebeu. Quem encerra e a tela, com motivo escrito.
     "onde": "COALESCE(situacao,'') NOT IN ('ENTREGUE','CANCELADO') "
             "AND COALESCE(origem,'') <> 'EOFICIO'",
     "o_acervo": "filtrado pela origem — eram **21.342 de 21.348**",
     "quando": "data_abertura",
     "rotulo": "interessado",
     "terminou": "quando é ENTREGUE ou CANCELADO — e são coisas diferentes",
     # Com 7 dias esta fonte gritaria no primeiro dia — e alarme que soa
     # sempre e alarme que ninguem ouve. O oficial ajusta na tela.
     "dias": 30,
     "tela": "caixa_protocolo", "parametro": "protocolo_id"},

    {"chave": "USUCAPIAO",
     "nome": "Usucapião em andamento",
     "atribuicao": "RI",
     "tabela": "us_processos",
     "onde": "COALESCE(situacao,'') NOT IN ('REGISTRADO','ARQUIVADO',"
             "'IMPROCEDENTE')",
     "quando": "atualizado_em",
     "rotulo": "requerente_nome",
     "terminou": "quando o reconhecimento é registrado na matrícula",
     # RITO DE MESES: 30 dias sem andar num usucapiao e parado de verdade.
     "dias": 30,
     "tela": "usucapiao_processo", "parametro": "processo_id"},

    {"chave": "RETIFICACAO",
     "nome": "Retificação de área em andamento",
     "atribuicao": "RI",
     "tabela": "rt_processos",
     "onde": "COALESCE(situacao,'') NOT IN ('AVERBADO','ARQUIVADO',"
             "'INDEFERIDO')",
     "quando": "atualizado_em",
     "rotulo": "requerente_nome",
     "terminou": "quando a retificação é averbada na matrícula",
     "dias": 30,
     "tela": "ri_retificacao", "parametro": "processo_id"},

    {"chave": "HABILITACAO",
     "nome": "Habilitação de casamento aberta",
     "atribuicao": "RCPN",
     "tabela": "hc_habilitacoes",
     "onde": "COALESCE(situacao,'') NOT IN ('CELEBRADO','ARQUIVADA',"
             "'CANCELADA')",
     "quando": "data_entrada",
     "rotulo": "nubente1_nome",
     "terminou": "quando o casamento é celebrado",
     "o_acervo": "não há acervo: o E-Ofício não tinha tabela de habilitação — "
                 "guardava três datas dentro do assento final",
     # A HABILITACAO VALE 90 DIAS (CC art. 1.532), e celebrar com ela vencida e
     # celebrar sem habilitacao. Trinta dias e o aviso com folga para agir.
     "dias": 30,
     "tela": "rcpn_habilitacao", "parametro": "habilitacao_id"},

    {"chave": "EXPEDIENTE",
     "nome": "Expediente sem encerrar",
     "atribuicao": "ADMINISTRATIVO",
     "tabela": "expedientes",
     "onde": "completed_at IS NULL",
     "quando": "received_at",
     "rotulo": "subject",
     "terminou": "quando é RESPONDIDO ou ARQUIVADO",
     "dias": 15,
     "tela": "expediente_detail", "parametro": "expediente_id"},

    {"chave": "TAREFA",
     "nome": "Tarefa em aberto",
     "atribuicao": "ADMINISTRATIVO",
     "tabela": "tasks",
     "onde": "completed_at IS NULL",
     "quando": "created_at",
     "rotulo": "title",
     "terminou": "quando é concluída",
     "dias": 15,
     "tela": "task_detail", "parametro": "task_id"},

    # A DECISAO QUE O OFICIAL GRAVOU E NAO SUBIU — 02/09/2026. Ela e
    # exatamente «o que comecou e nao terminou»: alguem olhou a pendencia,
    # decidiu, e a Central **ainda nao sabe**. Sem esta fonte ela ficaria
    # esperando na tela da CENPROT, que so quem se lembra dela abre.
    #
    # **O PRAZO E CURTO DE PROPOSITO.** O roteiro das Centrais tem hora
    # marcada — 11h30 e 14h10 —, e decisao que dorme um dia e o apresentante
    # sem resposta com o titulo aparecendo protestado na Central.
    #
    # O ACERVO NAO ENTRA: `cn_pendencias` nasceu em 02/09/2026 e so recebe o
    # que a API baixa. Nao ha uma linha de acervo nela, e nunca havera.
    {"chave": "CENPROT_DECIDIDA",
     "nome": "Pendência da CENPROT decidida e não enviada",
     "atribuicao": "PROTESTO",
     "tabela": "cn_pendencias",
     "onde": "situacao = 'DECIDIDA'",
     "quando": "decidida_em",
     "rotulo": "resumo",
     "terminou": "quando a resposta sobe à Central",
     "o_acervo": "não entra: a tabela nasceu em 02/09/2026 e só recebe o que "
                 "a API baixa — não há uma linha de acervo nela",
     "dias": 1,
     "tela": "protesto_pendencia", "parametro": "pendencia_id"},

    # O TITULO DO RCPJ/RTD QUE ENTROU E AINDA NAO SAIU — 03/09/2026.
    #
    #   **`APRESENTADO` e `QUALIFICADO` sao os dois estados em que o titulo
    #   esta com a casa.** No primeiro, ninguem olhou ainda; no segundo, a
    #   qualificacao foi positiva e o registro nao foi lavrado. Os dois sao
    #   trabalho comecado.
    #
    #   **`EXIGENCIA` NAO ENTRA, e a razao e a mesma dos prazos do Protesto:**
    #   ali a bola esta com o APRESENTANTE, e nao com a casa. Contar o titulo
    #   devolvido como trabalho parado faria a lista crescer com o que nao
    #   depende de ninguem daqui — e alarme que soa sempre e alarme que ninguem
    #   ouve.
    #
    #   O ACERVO NAO ENTRA: `rg_titulos` nasceu em 03/09/2026, e a carga do
    #   E-Oficio nao a alimenta — la o titulo apresentado **nao era guardado**
    #   (`strPet` e `strPetImg` estao vazias em 72 de 72). Nao ha uma linha de
    #   acervo nela.
    #
    #   **DEZ DIAS**, e nao um: aqui nao ha hora marcada com Central nenhuma.
    #   E o titulo apresentado tem a prioridade garantida pelo protocolo, que e
    #   justamente o que o prazo curto existiria para proteger.
    {"chave": "RG_TITULO",
     "nome": "Título de RCPJ/RTD apresentado e não registrado",
     "atribuicao": "RCPJ_RTD",
     "tabela": "rg_titulos",
     "onde": "situacao IN ('APRESENTADO','QUALIFICADO')",
     "quando": "data_apresentacao",
     "rotulo": "natureza",
     "terminou": "quando o registro é lavrado, ou o título é devolvido",
     "o_acervo": "não entra: a tabela nasceu em 03/09/2026 e a carga do "
                 "E-Ofício não a alimenta — lá o título apresentado não era "
                 "guardado",
     "dias": 10,
     "tela": "rcpj_rtd_titulo", "parametro": "titulo_id"},

    # O TERMO DE ALEGAÇÃO DE PATERNIDADE AINDA NÃO REMETIDO AO JUIZ — 23/10/2026.
    #
    #   A Lei nº 8.560/1992 (art. 2º) manda remeter; o código de normas dá 30
    #   dias. O painel avisa aos VINTE, para a remessa não sair no último dia.
    #   O termo NEGATIVO não entra: ele não se remete, fica arquivado. E a
    #   MÃE AUSENTE (27/10/2026) também não: sem suposto pai, não há remessa.
    {"chave": "RCPN_ALEGACAO_PATERNIDADE",
     "nome": "Termo de alegação de paternidade não remetido ao juiz",
     "atribuicao": "RCPN",
     "tabela": "rc_termos_paternidade",
     # O assento cancelado (o selo do nascimento falhou) não tem termo a
     # remeter: sem esta condição ele ficava no painel para sempre (27/10/2026).
     "onde": "tipo = 'ALEGACAO' AND remetido_em IS NULL AND assento_id NOT IN "
             "(SELECT id FROM rc_assentos WHERE situacao = 'CANCELADO')",
     "quando": "criado_em",
     "rotulo": "registrado_nome",
     "id": "assento_id",
     "terminou": "quando a remessa ao juiz é registrada na ficha do assento",
     "o_acervo": "não entra: a tabela nasceu em 23/10/2026 e só recebe o termo "
                 "lavrado com o nascimento do balcão",
     "dias": 20,
     "tela": "rcpn_assento", "parametro": "assento_id"},
    # O DIA DE PROTOCOLO DO RCPJ/RTD SEM TERMO DE ENCERRAMENTO — 23/10/2026.
    #
    #   «o aviso no painel fica valendo enquanto houver dia de protocolo sem
    #   encerrar» — o oficial. O livro diário nasce no primeiro protocolo do
    #   dia (`nu_livros.dia`), e o dia termina quando o termo é lavrado
    #   (`nu_encerramentos_diarios`). UM DIA: o de hoje ainda não está parado,
    #   o de ontem já está.
    #
    #   O dia útil SEM movimento não aparece aqui, porque não há livro dele
    #   para olhar; quem o cobra é o PDF do mês, que recusa juntar enquanto
    #   faltar termo de dia útil.
    {"chave": "NUCLEO_DIA_SEM_ENCERRAR",
     "nome": "Dia de protocolo do RCPJ/RTD sem termo de encerramento",
     "atribuicao": "RCPJ_RTD",
     "tabela": "nu_livros",
     "onde": "serie IN ('PJ_PROTOCOLO','TD_PROTOCOLO') AND dia IS NOT NULL "
             "AND NOT EXISTS (SELECT 1 FROM nu_encerramentos_diarios e "
             "WHERE e.serie = nu_livros.serie AND e.dia = nu_livros.dia)",
     "quando": "dia",
     "rotulo": "serie",
     "rotulo_2": "dia",
     "rotulo_junta": " — ",
     "terminou": "quando o dia é encerrado, com termo",
     "o_acervo": "não entra: a carga do acervo não abre livro diário — ela "
                 "não chama o núcleo, e o livro de protocolo do dia só nasce "
                 "quando o sistema protocola",
     "dias": 1,
     "tela": "nucleo_livro", "parametro": "livro_id"},
)

CHAVES = tuple(f["chave"] for f in FONTES)

# O QUE ESTE MODULO NAO FAZ, escrito para quem for mexer nele depois.
NAO_FAZ = (
    "não conclui nada — mostra e leva à tela do ato, onde as regras estão",
    "não cria expediente — o ato já é o registro, e a cópia diverge",
    "não avisa sozinho antes de o oficial dizer quantos dias",
)


def _texto(v: Any) -> str:
    """O valor como texto, e vazio quando não há. Nunca `str(v or "")`."""
    if v is None:
        return ""
    return str(v).strip()


def fonte(chave: str) -> dict:
    """A fonte pela chave, ou erro de balcão."""
    for f in FONTES:
        if f["chave"] == chave:
            return f
    raise InacabadoError(f"Não conheço a fonte «{chave}».")


def consulta_da_fonte(f: dict) -> str:
    """O SQL de uma fonte. Só monta o texto — não executa.

    **ELA SE MONTA DA DECLARAÇÃO, e não se escreve nove vezes.** Nove consultas
    escritas à mão divergiriam na primeira correção, e a que ficasse velha
    mostraria como aberto o que já foi concluído — que é o relato #24 de novo,
    por outro caminho.
    """
    # O SEGUNDO PEDAÇO DO RÓTULO VEM COMO COLUNA, E JUNTA-SE EM PYTHON.
    #
    #   A primeira versão disto escrevia `tipo || '-' || numero_pretendido` na
    #   própria declaração da fonte, e o varredor de portabilidade me pegou:
    #   o teto de `inacabados.py` é **zero**, e `||` muda de nome fora do
    #   SQLite. **A regra escrita é «recorte e junte em Python, depois de
    #   ler»** — e ela vale para mim como vale para o resto da casa.
    #
    #   Subir o teto era permitido e era o caminho preguiçoso: juntar duas
    #   colunas é justamente o que o Python faz de graça.
    mais = f", {f['rotulo_2']} AS rotulo_2" if f.get("rotulo_2") else ""
    # O DESEMPATE É O `id` DA PRÓPRIA TABELA, e não o `AS id` da fonte.
    #
    #   No SQLite, dois itens com o mesmo `quando` saíam na ordem em que
    #   entraram; no PostgreSQL, sem desempate, saem em qualquer ordem — e o
    #   corte do `limite` pode levar um ou outro. O `AS id` não basta: no RI ele
    #   é a matrícula, e três minutas da mesma ficha empatariam de novo.
    return (f"SELECT {f.get('id', 'id')} AS id, {f['rotulo']} AS rotulo{mais}, "
            f"{f['quando']} AS quando "
            f"FROM {f['tabela']} WHERE {f['onde']} "
            f"ORDER BY {f['quando']} IS NULL, {f['quando']}, {f['tabela']}.id")


def configuracao(con: sqlite3.Connection) -> dict[str, dict]:
    """Como cada fonte está ajustada — o padrão do código, mais o que o oficial
    mudou na tela. Só lê.

    **O CÓDIGO É O PISO; A TABELA É O AJUSTE**, como nos modelos da casa. Sem
    linha em `ex_fontes`, a fonte funciona com o padrão declarado — e «voltar ao
    padrão» é apagar a linha. Instalação nova nasce funcionando.
    """
    bd = banco(con)
    salvo = {}
    for linha in bd.ler("SELECT * FROM ex_fontes ORDER BY chave"):
        salvo[linha["chave"]] = dict(linha)
    saida = {}
    for f in FONTES:
        ajuste = salvo.get(f["chave"], {})
        # `is None` E NAO `or`: o oficial pode DESLIGAR uma fonte (ligada=0), e
        # `ajuste.get("ligada") or f["ligada"]` religaria o que ele desligou —
        # porque zero e falso. E o mesmo `str(v or "")` que comia o zero na
        # remessa do SIRC, custando outra coisa: ali a quantidade virava «nao
        # sei»; aqui a fonte desligada voltaria a gritar.
        ligada = ajuste.get("ligada")
        dias = ajuste.get("dias")
        saida[f["chave"]] = dict(
            f,
            ligada=bool(f.get("ligada", 1) if ligada is None else ligada),
            dias=int(f["dias"] if dias is None else dias),
            ajustada=f["chave"] in salvo)
    return saida


def ajustar(con: sqlite3.Connection, chave: str, *, ligada: bool, dias: int,
            agora: str, por: str) -> None:
    """Liga, desliga e muda os dias de uma fonte. GRAVA.

    É a tela que o oficial pediu — «moldar o que fica, o que sai». **A fonte em
    si continua no código**: a tela liga e desliga o que existe, e não inventa
    fonte, porque saber onde o ato mora e o que o termina não se digita.
    """
    fonte(chave)                        # recusa chave que nao existe
    if dias < 1:
        raise InacabadoError(
            "O prazo tem de ser de ao menos um dia — com zero, tudo apareceria "
            "como parado no mesmo dia em que entrou.")
    banco(con).escrever(
        """INSERT INTO ex_fontes (chave, ligada, dias, atualizado_em,
               atualizado_por)
           VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT(chave) DO UPDATE SET
               ligada=excluded.ligada, dias=excluded.dias,
               atualizado_em=excluded.atualizado_em,
               atualizado_por=excluded.atualizado_por""",
        (chave, 1 if ligada else 0, int(dias), agora, por))


def voltar_ao_padrao(con: sqlite3.Connection, chave: str) -> None:
    """Apaga o ajuste e a fonte volta ao que o código declara. GRAVA."""
    fonte(chave)
    banco(con).escrever("DELETE FROM ex_fontes WHERE chave = %s", (chave,))


def _dias(de: Any, ate: str) -> int | None:
    """Dias corridos entre duas datas. Só calcula, e `None` quando não dá.

    `None` NÃO VIRA ZERO: zero diria «entrou hoje», que é afirmação, e não saber
    é outra coisa. Item sem data não é item novo.
    """
    from datetime import date

    def _d(bruto: Any) -> date | None:
        b = _texto(bruto)[:10]
        if len(b) != 10 or b[4] != "-" or b[7] != "-":
            return None
        try:
            return date(int(b[:4]), int(b[5:7]), int(b[8:10]))
        except ValueError:
            return None

    a, b = _d(de), _d(ate)
    return None if a is None or b is None else (b - a).days


def _rotulo_da_linha(f: dict, linha) -> str:
    """O rótulo de um item, juntado EM PYTHON.

    Três minutas da mesma ficha levam ao mesmo link, e com o rótulo `tipo`
    sozinho o painel mostrava **três linhas idênticas** («AV», «AV», «AV») —
    quem lesse não saberia se era uma repetida ou três coisas para fazer.
    Medido contra a produção, que tem exatamente esse caso: AV-4, AV-5 e AV-6
    da matrícula 3.110.

    E A JUNÇÃO É AQUI, e não no SQL: `||` muda de nome fora do SQLite, e o
    teto de acoplamento deste módulo é zero.
    """
    rotulo = _texto(linha["rotulo"])
    if not f.get("rotulo_2"):
        return rotulo
    segundo = _texto(linha["rotulo_2"])
    if not segundo:
        return rotulo
    return f"{rotulo}{f.get('rotulo_junta', '-')}{segundo}"


def lista(con: sqlite3.Connection, *, hoje: str, chave: str = "",
          atribuicao: str = "", so_parados: bool = False,
          limite: int = 300) -> list[dict]:
    """O que começou e não terminou. SÓ LÊ, e mede na hora.

    **ATO CONCLUÍDO SAI DAQUI SOZINHO**, porque a lista é a pergunta e não a
    resposta guardada. É o que impede o defeito do relato #24 — o expediente
    aberto com a tarefa concluída.

    **FONTE QUE NÃO RESPONDE NÃO VIRA LISTA VAZIA**: ela volta com o motivo, do
    mesmo jeito que o painel das comunicações. Uma tabela renomeada faria a lista
    encolher em silêncio, e ninguém repara em item que deixou de aparecer.
    """
    bd = banco(con)
    config = configuracao(bd)
    anotadas = _anotacoes(bd)
    saida: list[dict] = []
    for f in FONTES:
        c = config[f["chave"]]
        if not c["ligada"]:
            continue
        if chave and f["chave"] != chave:
            continue
        if atribuicao and f["atribuicao"] != atribuicao:
            continue
        try:
            linhas = bd.ler(consulta_da_fonte(f))
        except sqlite3.Error as erro:
            saida.append({"chave": f["chave"], "fonte": f["nome"],
                          "atribuicao": f["atribuicao"],
                          "erro": f"não deu para medir: {erro}",
                          "id": None, "rotulo": "", "dias": None,
                          "parado": False})
            continue
        for linha in linhas[:limite]:
            dias = _dias(linha["quando"], hoje)
            parado = dias is not None and dias >= c["dias"]
            if so_parados and not parado:
                continue
            saida.append({
                "chave": f["chave"], "fonte": f["nome"],
                "atribuicao": f["atribuicao"], "tabela": f["tabela"],
                "id": linha["id"], "rotulo": _rotulo_da_linha(f, linha),
                "quando": _texto(linha["quando"])[:10],
                "dias": dias, "parado": parado, "limite_de_dias": c["dias"],
                "terminou": f["terminou"],
                "tela": f["tela"], "parametro": f["parametro"],
                "anotacao": anotadas.get((f["tabela"], linha["id"])),
                "erro": ""})
    # O MAIS PARADO PRIMEIRO — e quem nao tem data vai para o fim, porque nao se
    # pode afirmar que ele esta parado nem que nao esta.
    saida.sort(key=lambda x: (x["dias"] is None, -(x["dias"] or 0)))
    return saida


def resumo(con: sqlite3.Connection, *, hoje: str) -> list[dict]:
    """Quantos por fonte, e quantos parados. Só lê — é o alto da tela."""
    bd = banco(con)
    tudo = lista(bd, hoje=hoje, limite=100000)
    por_fonte: dict[str, dict] = {}
    for f in FONTES:
        por_fonte[f["chave"]] = {"chave": f["chave"], "fonte": f["nome"],
                                 "atribuicao": f["atribuicao"],
                                 "quantos": 0, "parados": 0, "erro": ""}
    for x in tudo:
        alvo = por_fonte[x["chave"]]
        if x["erro"]:
            alvo["erro"] = x["erro"]
            continue
        alvo["quantos"] += 1
        alvo["parados"] += 1 if x["parado"] else 0
    config = configuracao(bd)
    for chave, alvo in por_fonte.items():
        alvo["ligada"] = config[chave]["ligada"]
        alvo["dias"] = config[chave]["dias"]
    return list(por_fonte.values())


# ------------------------------------------------------------- a anotação
#
# **E O UNICO DADO NOVO DESTE MODULO**, porque e o unico que nao existe em lugar
# nenhum: quem esta cuidando, ate quando, o que falta. Todo o resto e medido.


def _anotacoes(con: sqlite3.Connection) -> dict[tuple, dict]:
    return {(x["tabela"], x["item_id"]): dict(x)
            for x in banco(con).ler(
                "SELECT * FROM ex_anotacoes ORDER BY tabela, item_id")}


def anotar(con: sqlite3.Connection, *, tabela: str, item_id: int, texto: str,
           responsavel: str = "", ate: str = "", agora: str, por: str) -> None:
    """A anotação do oficial sobre um item. GRAVA.

    NÃO CONCLUI NADA — anotar não é resolver. Concluir é na tela do ato, com as
    regras de lá.
    """
    if tabela not in {f["tabela"] for f in FONTES}:
        raise InacabadoError(f"«{tabela}» não é uma das fontes desta lista.")
    if not _texto(texto):
        raise InacabadoError("Escreva o que falta neste item.")
    banco(con).escrever(
        """INSERT INTO ex_anotacoes (tabela, item_id, texto, responsavel, ate,
               criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT(tabela, item_id) DO UPDATE SET
               texto=excluded.texto, responsavel=excluded.responsavel,
               ate=excluded.ate, criado_em=excluded.criado_em,
               criado_por=excluded.criado_por""",
        (tabela, int(item_id), _texto(texto), _texto(responsavel),
         _texto(ate), agora, por))


def apagar_anotacao(con: sqlite3.Connection, *, tabela: str,
                    item_id: int) -> None:
    """Tira a anotação. GRAVA.

    O ITEM CONTINUA NA LISTA — quem o tira de lá é a conclusão do ato, na tela
    dele. Apagar a anotação aqui e o item sumir seria a lista virando gaveta, que
    é exatamente o que este módulo não é.
    """
    banco(con).escrever(
        "DELETE FROM ex_anotacoes WHERE tabela=%s AND item_id=%s",
        (tabela, int(item_id)))
