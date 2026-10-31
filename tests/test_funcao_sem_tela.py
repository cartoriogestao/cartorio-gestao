"""**FUNCAO PRONTA QUE NENHUMA TELA ALCANCA.**

POR QUE ESTE VARREDOR EXISTE
    E o defeito que mais se repetiu neste projeto, e ele nao da erro nenhum:
    a funcao existe, o teste dela passa, e o escrevente nao tem como chegar
    nela. **Teste verde da a sensacao de entrega sem a entrega.**

    Ja havia um varredor de ROTA orfa (`test_debitos_do_balcao`), e ele nao
    pega este caso: a rota pode existir e simplesmente nao chamar a funcao. Foi
    por essa fresta que passaram, em 30/08/2026, duas entregas anunciadas ao
    oficial no dia anterior:

      - `rc_termo.informacoes_importadas` — a lista dos 244 assentos do acervo.
        Eu os tirei de «Termos a escrever», o que estava certissimo, e disse ao
        oficial que passavam a ter «lista propria». Escrevi a funcao e nao
        construi a tela. **Tirar de uma lista nao e dar um lugar.**
      - `rc_checklist.atos_sem_checklist` — a lista dos atos que faltam
        conferir, sendo essa a exigencia de **prazo zero** da inspecao.

    Nenhuma das duas deu erro. Elas simplesmente nao existiam para quem usa.

COMO ELE PERGUNTA
    A pergunta certa nao e «quem chama esta funcao» — a primeira versao deste
    varredor perguntava assim e acusava `digito_verificador`, que e chamada por
    `compor`, no mesmo arquivo, que a tela chama. A pergunta e **«existe
    caminho de uma tela ate ela?»**: monta o grafo de chamadas, parte das rotas
    do Flask e dos nomes citados nos templates, e anda.

O QUE ELE NAO PROVA
    Nomes iguais em arquivos diferentes contam como um so, e chamada dinamica
    nao aparece. Por isso a lista abaixo e de **conhecidas**, e nao de
    condenadas: o teste cobra que nao apareca orfa NOVA.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def _nomes_usados(no: ast.AST) -> set[str]:
    fora: set[str] = set()
    for x in ast.walk(no):
        if isinstance(x, ast.Call) and isinstance(x.func, ast.Name):
            fora.add(x.func.id)
        elif isinstance(x, ast.Attribute):
            fora.add(x.attr)
        elif isinstance(x, ast.Name):
            fora.add(x.id)
    return fora


def _orfas() -> dict[str, list[str]]:
    """As funcoes sem caminho ate uma tela. Nome -> onde esta definida."""
    chama: dict[str, set] = {}
    onde: dict[str, list[str]] = {}
    raizes: set[str] = {"create_app", "main"}
    solto: set[str] = set()

    for p in sorted(RAIZ.glob("*.py")):
        t = p.read_text(encoding="utf-8", errors="replace")
        decoradas = set(re.findall(
            r"@app\.route\([^)]*\)(?:\s*@[^\n]+)*\s*\n\s*def (\w+)", t))
        try:
            arvore = ast.parse(t)
        except SyntaxError:
            continue
        # O GRAFO INCLUI TUDO — metodos tambem, porque eles CHAMAM.
        for no in ast.walk(arvore):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chama.setdefault(no.name, set()).update(_nomes_usados(no))
                if no.name in decoradas:
                    raizes.add(no.name)
            # NOME TRAZIDO POR `from X import Y` ESTA EM USO. Sem esta linha o
            # varredor acusa todos os `init_*_schema`, que o `database` importa
            # assim — quinze acusacoes falsas de uma vez.
            elif isinstance(no, ast.ImportFrom):
                for al in no.names:
                    # O que `onde` conhece e o nome DEFINIDO no modulo de
                    # origem, nao o apelido local. `extrair as extrair_doc`
                    # tornava `extrair_doc` raiz — nome que nao existe em
                    # `onde` — e deixava `extrair` e seus tres auxiliares com
                    # cara de orfa, embora a rota do RI os alcance.
                    raizes.add(al.name)
        # MAS SO SE ACUSA FUNCAO DE NIVEL DE MODULO. **Metodo de classe nunca e
        # chamado pelo nome** — `init_schema` e do `Database`, `handle_data` e
        # do HTMLParser da biblioteca —, e cobra-los aqui seria acusar a
        # linguagem em vez do codigo. Quem instancia a classe e outra conversa.
        for no in arvore.body:
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                onde.setdefault(no.name, []).append(f"{p.name}:{no.lineno}")
        for no in arvore.body:
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef,
                                   ast.ClassDef, ast.Import, ast.ImportFrom)):
                solto |= _nomes_usados(no)

    telas = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                      for p in RAIZ.glob("templates/*.html"))
    # **TEXTO DA PAGINA NAO E CHAMADA.** A primeira versao varria toda palavra
    # do HTML; quando a tela do Next Cloud passou a dizer «imagens parciais»,
    # ela fez `backup.parciais` parecer alcancada sem que ninguem a chamasse.
    # So o que esta numa expressao Jinja pode citar funcao ou endpoint Python.
    # Prosa igual ao nome de uma funcao nao abre caminho ate ela.
    jinja = "\n".join(re.findall(r"\{\{.*?\}\}|\{%.*?%\}", telas,
                                 re.DOTALL))
    raizes |= (set(re.findall(r"[A-Za-z_][A-Za-z_0-9]{3,}", jinja))
               & set(onde))
    raizes |= solto & set(onde)

    vistas, fila = set(), list(raizes)
    while fila:
        n = fila.pop()
        if n in vistas:
            continue
        vistas.add(n)
        fila.extend(chama.get(n, ()))

    return {n: locais for n, locais in onde.items()
            if not n.startswith("_") and n not in vistas}


# AS CONHECIDAS EM 30/08/2026. Sao auxiliares que os testes exercitam e o
# produto ainda nao usa. **Esta lista so pode ENCOLHER**: o teste de baixo
# recusa nome que ja deixou de ser orfao, para que ela nao vire deposito.
#
# `quantos_do_acervo_ficaram_de_fora` entrou em 30/08/2026, com o relato #13.
# Ela serve `atos_sem_selo`. Ela e a frase que impede a lista de encolher em silencio quando o filtro do acervo
# tirar 2.783 linhas: sem ela, quem lesse concluiria que o trabalho acabou.
# **DUAS SAIRAM DESTA LISTA EM 02/09/2026, e a razao e a mesma para as duas:
# elas deixaram de ser orfas.** `instrumento` estava aqui porque «o modulo
# esta desligado» — e o Protesto voltou, como alcance de tres posicoes; e
# `data_do_protocolo` porque «a tela usa `decompor_chave`» — e agora as telas
# da CENPROT alcancam `protesto_cenprot` inteiro.
#
# **Quem as tirou foi o piso, e nao a releitura.** `test_a_lista_de_conhecidas_
# nao_vira_deposito` compara a lista com o que o varredor acha e reclama do que
# sobra: sem ele a lista so cresce, e daqui a um ano ninguem sabe quais
# daqueles nomes ainda sao de verdade.

# `atos_do` SAIU DAQUI EM 03/09/2026, e nao por releitura: a ficha do titulo do
# RCPJ/RTD (`rg_web.rcpj_rtd_titulo`) passou a chama-la para mostrar os atos do
# registro que saiu do titulo. **Construir uma coisa fechou o orfao de outra**,
# e quem apontou foi o piso deste arquivo.
#
# `operacao_ctp` E `teor_html` SAIRAM EM 07/09/2026 SEM MUDANCA NO PRODUTO:
# elas ja eram chamadas como `operacao_sauin` (`ri_ctp`) e `teor_html_doc`
# (`ri_web`). O varredor e que aprendeu a atravessar `import ... as ...`.
JA_SABIDAS: frozenset[str] = frozenset({
    # `atos_do_retorno` e `exigencias_da_inspecao` SAÍRAM EM 30/10/2026, com as
    # outras da revisão de telas: ganharam quadro nas telas vizinhas, e
    # `tests/test_funcoes_com_tela.py` guarda cada uma.
    #
    # `atos_sem_cobranca` SAIU, APAGADA, POR DECISÃO DO OFICIAL EM 30/10/2026: a
    # régua dela era o `lancamento_id`, e desde a 3.7.0 o dinheiro entra pelo
    # protocolo. «Selos × caixa — conferência» já responde pela régua nova.
    "atos_da",
    # `atos_sem_selo` SAIU DAQUI EM 14/09/2026: a tela de selos do RI passou
    # a chama-la. Ela era a mais cara desta lista — oito comentarios em sete
    # modulos prometiam ao operador que «o ato sem selo aparece» nela.
    # `blocos_do` FICA (30/10/2026): a ficha do assento já separa os blocos, com
    # cada ato levando quem lavrou e a folha, que esta função não traz.
    "quantos_do_acervo_ficaram_de_fora", "blocos_do", "caminhos_da_atribuicao",
    "campos_do_ato", "cib_valido", "claros_restantes", "codigo_da_tabela",
    # `compor_do_assento` SAIU DAQUI EM 03/09/2026, e o varredor foi quem
    # mandou: ela deixou de ser orfa quando `proclamas.matricula_do_proclama`
    # passou a chama-la para montar a matricula do Livro D que vai ao
    # e-Proclamas. **Nome que deixou de ser orfao sai da lista**, senao ela so
    # cresce e o varredor vira enfeite.
    "conferir_ato", "conferir_declaracao",
    # `conferir_remessa` FICA (30/10/2026): `protesto_remessa._conferir_lote`
    # confere título a título pela mesma `CRA.conferir_titulo`, e a tela de conferir
    # a remessa mostra a falta de cada um. Uma segunda conta diria a mesma coisa.
    "conferir_idade_da_genitora", "conferir_remessa", "conferir_texto",
    # `copy_existing`, `decisoes_da_matricula`, `dv_mod97`, `gerar_cnm` e
    # `registrar_cancelamento` SAIRAM EM 12/10/2026 — já têm caminho até tela.
    "data_da_publicacao",
    "declaracoes_do_ato", "descrever_layout", "devedores_do",
    "endpoints_de",
    "face_da", "folha_da",
    "inicio_do_prazo", "inutilizar_sobra",
    "larguras_em_mm", "ler_tabela_de_custas", "liberar",
    "lugar_estrangeiro", "maior_citado", "paginas_de",
    "para_conferir", "partes_do", "pendencias_do_assento",
    # `backup.parciais` saiu daqui em 26/10/2026: o processo de backup da
    # automacao (`backup_automacao.rodar_backup`) avisa os `.parcial` esquecidos.
    "prenomes_se_distinguem", "quantas_pendentes",
    "semelhanca_fina",
    # **`rc_cpf.solicitar` NAO TEM TELA DE PROPOSITO.** Ela existe para RECUSAR
    # e dizer o que falta — o Termo de Adesao da RFB, que o oficial assina na
    # CRC Nacional. Dar-lhe uma tela seria oferecer ao balcao um botao que so
    # devolve erro. Ela sai desta lista no dia em que a integracao existir.
    "solicitar",
    "somam_um",
    # `texto_corrido` SAIU em 14/10/2026: a montagem do ato das Notas
    # (`notas_teor._corrido`) passou a chamá-la — o ato em texto corrido.
    "somar", "texto_puro", "trimestre_de",
    "vai_direto_para_edital", "valida_cnm", "valor_doi", "voltar_ao_padrao",
})


# AS QUE NASCERAM ENTRE A 3.6.51 E A 3.6.61 — lista propria, e nao despejo
# na de cima.
#
# **POR QUE UMA SEGUNDA LISTA, E NAO doze nomes na primeira.** Aquela se chama
# «as conhecidas em 30/08/2026», e por isso enfiar ali coisa de 01/09 seria
# datar errado o que se sabia quando. A procedencia e o que este projeto
# guarda com mais cuidado; ela vale tanto quanto o nome.
#
# **E COMO ELAS PASSARAM DESPERCEBIDAS POR OITO VERSOES.** A suite inteira so
# roda quando o oficial pede — ordem dele de 31/08/2026 —, e a ultima rodada
# foi na 3.6.51. Da 3.6.52 a 3.6.59 nada aqui foi varrido. Medido comparando
# o `.cgu` da 3.6.51 com a arvore de hoje: **63 orfas la, 75 aqui**. Nao e
# argumento contra a cadencia que ele escolheu; e o preco dela, escrito.
NASCIDAS_DEPOIS_DA_3_6_51: dict[str, str] = {
    # A REGUA QUE COMPARA O VOCABULARIO COM O CONTRATO. `codigos_do_enum` parte
    # o `enum` do ONR — que e `["64 = Casa", ...]`, documentacao e nao valor —
    # e e ela que `tools/gerar_logradouros.py` e `tests/test_onr_api.py` usam
    # para provar que os 129 logradouros, os 23 atos e os 10 imoveis
    # transcritos batem com o contrato. **Tela ela nao tem, e nao deve ter.**
    "codigos_do_enum": "onr_api — e a regua do teste contra o contrato",
    # O PROTESTO ESTA DESLIGADO POR ORDEM DO OFICIAL (01/09/2026), e a tela
    # destas tres vem quando ele voltar. Constru-las agora seria construir
    # tela para modulo que o balcao nao ve.
    "por_que_nao_esta_completo": "protesto_instrumento — o modulo esta desligado",
    # `titulos_sem_chave` SAIU EM 30/10/2026: a lista entrou junto da contagem.
    #
    # ------------------------------------------------------------------
    # AS SEIS ABAIXO NAO SAO DESTA NOITE, e duas delas parecem DEFEITO.
    # Ficam aqui declaradas para nao se perderem, e estao no roteiro da
    # 3.6.61 como pendencia — nao como coisa resolvida.
    #
    # **`o_que_sai` e `montar_envio` sao o caso mais grave.** O comentario de
    # `ajuda_web.py` (linhas 44-45) afirma que a pre-visualizacao usa «as
    # mesmas funcoes da consulta — `montar_envio`, `montar_instrucao` e
    # `o_que_sai` —, e nao uma copia parecida, que divergiria no primeiro
    # conserto». O varredor diz que **ninguem as chama**. Ou o comentario
    # mente, ou a previa foi reescrita por fora: nos dois casos e o defeito
    # que aquelas funcoes existiam para impedir.
    #
    # **AS DUAS SAIRAM EM 12/10/2026, e o defeito que elas acusavam fechou**: a
    # prévia da ajuda passou a chamar `montar_envio` e `o_que_sai` — o varredor
    # as achou com caminho até tela, e o comentário de `ajuda_web` deixou de mentir.
    #
    # **`html_odt_da_certidao` faz `return ""`**, e e a ULTIMA funcao de um
    # arquivo de 287 linhas. Toco, ou sobra de algo interrompido.
    "html_odt_da_certidao": "rc_certidao_odt — A CONFERIR: devolve string vazia",
    #
    # Estas tres sao auxiliares legitimas, e nao acusam nada.
    #
    # `sem_mascara` SAIU DAQUI EM 19/10/2026 (LF06G), e quem a tirou da lista
    # foi o LF01: `templates/gestor_relatorio_ia.html` passou a escrever
    # `{{ f.sem_mascara }}` (o contador do relatório da IA), e o varredor, que
    # casa nome com nome, a dá por alcançada. Medido com `git log -S`.
    # `nome_do_dedo` SAIU DAQUI EM 07/09/2026: o relato #39 ligou a colheita
    # das quatro digitais ao cartao, e `notas_web` usa o rotulo tanto na tela
    # quanto na confirmacao da captura.
    "prenome": "rc_gemeos — auxiliar de `prenomes_se_distinguem`, que ja esta na lista",
    "teor_sem_titulo": "rc_certidao — auxiliar do papel, ainda nao ligado",
}


# REVELADAS EM 07/09/2026 AO PARAR DE CONTAR PROSA DE TEMPLATE COMO CHAMADA.
#
# Elas nao nasceram juntas. O que nasceu nesta data foi a medicao correta:
# antes, palavras comuns da interface — «carregar», «configuracoes»,
# «indicador», «instrumento» — escondiam funcoes de mesmo nome. Uma lista
# propria guarda essa procedencia sem reescrever a data de `JA_SABIDAS` nem
# alargar a lista que mede somente o intervalo 3.6.51--3.6.61.
REVELADAS_AO_SEPARAR_PROSA_DE_CHAMADA: dict[str, str] = {
    # A copia integral e imutavel do E-Oficio foi uma ferramenta da migracao,
    # executada sobre a pasta exportada; nao e operacao cotidiana do balcao.
    # A lista existe para a prova que confere se todas as regulagens de
    # etiqueta continuam cobertas; a tela le as medidas, nao esta enumeracao.
    "configuracoes": "etiqueta — introspeccao usada pelo guarda dos testes",
    # O proprio modulo declara: o cache so e descartado porque cada teste troca
    # o banco e precisa medir de novo.
    "esquecer": "ajuda_mapa — limpa o cache somente entre testes",
    # A API conserva a operacao GET do contrato. A tela corrente concilia pela
    # lista (`indicadores`) e pelo rastro local, sem abrir o GET individual.
    "indicador": "onr_api — operacao individual do contrato ainda sem botao",
    # `protesto_instrumento.instrumento` SAIU DAQUI EM 14/10/2026: a rota do
    # papel do instrumento (`/protesto/instrumentos/<id>/odt`) passou a lê-la.
}


# ACHADAS EM 14/09/2026, AO LIGAR O SELO AUTOMATICO DO ATO DO RI.
#
# **NENHUMA DELAS E DESTA PASSADA, E POR ISSO ELAS SAO DECLARADAS E NAO
# CONSERTADAS** — a regra de 02/09: quem nao esta construindo o modulo nao mexe
# nele. Todas nasceram em modulos que esta passada nao tocou (certidao em PDF
# do RTD/RCPJ, inteiro teor do RCPN, papel de seguranca, teor do RTD), e quem
# as construiu sabe se falta tela ou se elas sao auxiliares.
#
# Lista propria e datada, como a de 07/09: assim a procedencia nao se perde
# dentro de uma lista que mede outro intervalo.
ACHADAS_EM_14_09_2026: dict[str, str] = {
    "chave_capa": "rg_certidao_pdf — auxiliar do papel, de outra passada",
    "chave_faixa": "rg_certidao_pdf — auxiliar do papel, de outra passada",
    "rotulo_ato_para_certidao": (
        "rg_certidao_pdf — auxiliar do papel, de outra passada"),
    "escapar_xml": (
        "rc_certidao_inteiro_teor — auxiliar do XML, de outra passada"),
    "linha_data": "rg_teor_rtdpj — auxiliar do teor, de outra passada",
    # `movimentos_da_folha` SAIU EM 30/10/2026: a tela do papel procura a folha.
    # **ESTA E DE 14/09 TAMBEM, E DE OUTRA PASSADA** — a do agente do sistema,
    # no mesmo dia. Ela entra aqui pelo mesmo motivo das duas acima: a porta
    # dela e a ABERTURA DO BANCO (`database.init_schema`), e nao uma tela. Ela
    # fecha a sessao que o programa deixou ABERTA no meio de uma rodada — e sem
    # ela a conversa interrompida nao teria como ser continuada, porque
    # `responder` recusa sessao aberta. Nao e funcao sem porta: e funcao cuja
    # porta nao e uma tela.
    # `init_papel_schema`, `recuperar_cancelados_existentes` e
    # `recuperar_sessoes_interrompidas` SAIRAM EM 12/10/2026: o varredor passou
    # a enxergar o caminho delas (a abertura do banco chega a uma tela).
}


# ACHADAS EM 15/09/2026, E A PROCEDÊNCIA DELAS FOI MEDIDA NO `.cgu`.
#
# **Nenhuma das três existia na 3.6.99** — conferido abrindo o pacote de
# 11/09, 20h03: `ri_minuta.py` não está lá, e nem `backfill_por_deposito`
# nem `preencher_colunas_derivadas` aparecem em arquivo nenhum. Elas
# nasceram depois, em módulos que **esta passada não tocou** — a do
# ciclo do ato do RI (minuta), a do vínculo do protocolo do caixa com o RI, e
# a da lista de matrículas. É a regra de 02/09: quem não está construindo o
# módulo não mexe nele, e por isso elas são **declaradas, e não consertadas**.
#
# **A MEDIÇÃO É A DO `.cgu`, e não a data do arquivo em disco** — o projeto
# não tem git, e duas passadas escrevendo a mesma árvore misturam `mtime` no
# mesmo minuto. O pacote é a única linha do tempo datada do código.
ACHADAS_EM_15_09_2026: dict[str, str] = {
    "quantas_a_revisar": (
        "ri_minuta — a contagem das minutas por ficha, de outra passada; "
        "o painel dos inacabados conta pela fonte dele, não por esta"),
    "backfill_por_deposito": (
        "caixa_protocolo — passada de reparo do vínculo, chamada pelos testes "
        "e ainda sem botão"),
    # `preencher_colunas_derivadas` SAIU EM 12/10/2026 — já tem caminho.
    #
    # ------------------------------------------------------------------
    # AS DUAS DE BAIXO ACHARAM O SEU CAMINHO AQUI EM 15/09/2026, na mesma
    # varredura em que a terceira acusação — `texto_escrito_no_teor` — era
    # MINHA. As duas são de outras passadas, e ficam declaradas e não
    # consertadas: a regra de 02/09, quem não está construindo o módulo não
    # mexe nele.
    #
    # **E A MINHA VIROU CONSERTO, E NÃO DECLARAÇÃO — porque o varredor estava
    # certo sobre ela por um motivo que valia.** `texto_escrito_no_teor`
    # existia, estava testada, e quem devia chamá-la (`atos_fora_do_teor`) havia
    # refeito a conta por dentro: duas contas dizendo «este texto já está escrito
    # na ficha». É a mesma família da `normalizar_nome`, e aqui o preço seria
    # alto — é esta conta que decide se um ato APARECE na ficha.
    #
    # **A PROCEDÊNCIA DE CADA UMA FOI MEDIDA NO PACOTE, e as duas deram
    # diferente** — o que é a razão de se medir caso a caso em vez de datar
    # tudo pela hora do arquivo:
    #
    #   `pedir` ESTÁ na 3.6.131, empacotada hoje às 16h55 — nasceu com o
    #   agente do sistema, e já viajou para o servidor.
    #
    #   `propor_do_banco` NÃO está em pacote nenhum, nem na 3.6.131: o módulo
    #   `onr_endereco_do_teor.py` nasceu na árvore depois de ele ser fechado,
    #   também por outra passada.
    # `pedir` SAIU EM 12/10/2026 — voltou a ter caminho até tela.
    #
    # `propor_do_banco` **SAIU DESTA LISTA EM 16/09/2026**, e o `piso` abaixo
    # foi quem cobrou: ela ficou sem tela em 15/09, quando o módulo do extrator
    # nasceu; no dia seguinte o botão «o que o teor diz» entrou na ficha do
    # imóvel e ela passou a ter porta. **Declaração que envelhece faz planejar
    # trabalho já feito** — e, no sentido contrário, deixá-la aqui faria o
    # varredor cobrar conserto de uma peça que já está consertada.
}


ACHADAS_EM_19_09_2026: dict[str, str] = {
    # A camada da CNIB foi construída e testada como API, mas ainda não está
    # ligada a rota/tela. A consulta pública é a operação de entrada; as demais
    # são os leitores internos das respostas e dos estados do protocolo.
    #
    # **OITO DELAS SAÍRAM DESTA LISTA NO MESMO DIA 19/09/2026**, e no mesmo dia
    # de propósito: `ordens_na_janela`, `uma_pagina`, os três leitores da
    # resposta e os dois do protocolo ganharam porta quando o **atualizador**
    # nasceu (`cnib_atualizador.py`), com a tela «CNIB — a cópia local e a
    # Central». A declaração acima foi escrita de manhã e envelheceu à tarde —
    # que é exatamente o que a régua do `piso` existe para cobrar: deixá-las
    # aqui faria o varredor pedir conserto de peça já consertada.
    "consultar_por_documento": (
        "cnib_api — consulta pronta e testada, ainda sem rota/tela"),
    # ESTES TRÊS CONTINUAM SEM PORTA, e é declaração, não esquecimento. O
    # espelho não guarda `ordemstatus`: o atualizador grava o que a ficha
    # precisa (protocolo, partes, cancelamento) e **não inventa coluna para
    # campo cujo uso ninguém mediu** — os 6.218 registros lidos trazem 6.216
    # concluídos, e o que fazer com uma ordem não concluída nunca foi decidido
    # por quem assina. `protocolo_cancelado` é o mesmo valor que a gravação já
    # lê por `protocolo_da_ordem`, e chamá-la por simetria seria chamada de
    # enfeite.
    "e_concluida": "cnib_api — classificador interno do estado",
    "e_cancelamento": "cnib_api — classificador interno do estado",
    "protocolo_cancelado": "cnib_api — leitor interno do protocolo",
    # `rotulo_folha_da_pagina` SAIU EM 12/10/2026 — ganhou tela.
}


# NASCIDAS EM 05/10/2026 COM A BASE COMUM DAS CENTRAIS — marco (a).
#
# **SAO A API PUBLICA DE UMA PECA DE INFRAESTRUTURA, E O CONSUMIDOR VEM NA
# ETAPA SEGUINTE.** O marco (a) entrega o cliente HTTP comum, a fila generica e
# o log; quem passa a chama-los e a etapa (b) — CENPROT/CRA21 — e, depois,
# Notas/RI ao migrar `onr_api`/`cnib_api`. A porta de tela que ja existe e o
# painel `/centrais/status` (resumo, falhas, log, reprocesso local), e por
# isso `resumo_por_central`, `ultimas_falhas`, `listar`, `reprocessar`,
# `ultimos` e `registrar` NAO estao aqui. Contrato em
# `DOCUMENTACAO/CENTRAIS_BASE_COMUM.md`.
#
# **QUANDO A ETAPA (b) LIGAR CADA UMA, ELA SAI DAQUI** — o `piso` cobra.
# `processar_proximo` puxa sozinha `devolver_presos`, `pegar_proximo`,
# `marcar_falha`, `marcar_enviado` e `espera_da_tentativa`; `requisitar` puxa
# `contexto_tls`. Ligar as duas raizes tira sete nomes de uma vez.
# **ESVAZIADA EM 05/10/2026 PELO MARCO (b)** — as onze sairam juntas:
# `cenprot_api._bater`/`cra21_api._bater` passaram a chamar `requisitar`
# (que puxa `contexto_tls`) e `centrais_log.anotar_resposta` ->
# `registrar_resposta`; o botao «testar a conexao» da CENPROT e da CRA, em
# homologacao, chama `protesto_centrais_fila.testar_pela_fila`, que puxa
# `enfileirar`, `processar_proximo` (e os passos dela) e `marcar_confirmado`.
# O dicionario fica, vazio, para o `_conhecidas` e o historico da medicao.
ACHADAS_EM_05_10_2026: dict[str, str] = {}


# NASCIDAS EM 08/10/2026 COM O PROBLEMA #121 — o termo do RCPN digitalizado.
#
# **A PORTA DELAS NÃO É UMA TELA: É A CARGA DO ACERVO TRANSCRITO**, que outra
# frente está montando por script (o pedido do oficial: «juntaremos o teor e
# digitalização para que tenhamos todo acervo do registro civil pronto para
# emitir certidão com um clique»). Elas existem para que a carga NÃO escreva
# direto em `rc_assentos` — a lição de «a importação do RI lavra por fora do
# sistema»: sem auditoria e passando por cima do que o balcão enviou. Quando o
# script da carga entrar na raiz e chamá-las, elas saem daqui — o `piso` cobra.
ACHADAS_EM_08_10_2026: dict[str, str] = {
    "anexar_digitalizacao": (
        "rc_digitalizacao — anexa por programa o termo digitalizado; a porta "
        "é o script da carga do acervo transcrito, não uma tela"),
    "gravar_teor_transcrito": (
        "rc_digitalizacao — grava o teor transcrito só onde está vazio; a "
        "porta é o script da carga do acervo transcrito, não uma tela"),
}


# ACHADAS EM 12/10/2026, NA ORDEM DO OFICIAL «resolve as 7».
#
# **NENHUMA É DA PASSADA QUE AS DECLAROU** (a dos Processos), e por isso elas
# ficam DECLARADAS, com o caminho que cada uma tem — medido procurando quem a
# chama na raiz, em `tests/` e em `tools/`. Quatro espécies:
#   1. a porta é JavaScript ou blueprint, que este varredor não lê;
#   2. a porta é um script de `tools/` (importação, empacotamento, release);
#   3. auxiliar testada de módulo cuja tela ainda não ligou a peça;
#   4. **SEM CHAMADOR NENHUM** — nem teste nem script. São as candidatas a
#      apagar, e apagar é de quem constrói o módulo: estão marcadas «SEM
#      CHAMADOR», para a próxima passada naquele módulo decidir.
_JS = "porta é JavaScript/blueprint (`modelos_motor_api`), que o varredor não lê"
_TOOLS = "a porta é script de `tools/`, e não tela"
_TESTE = "auxiliar testada; a tela ainda não ligou esta peça"
_DOMINIAL = "ri_dominial — régua interna da cadeia dominial/vintenária, testada"
_SAEC = "onr_api — operação do contrato SAEC (atendimento/cobrança), testada; sem botão ainda"
_SEM = "SEM CHAMADOR — nem teste nem script; candidata a apagar (decisão de quem constrói o módulo)"
ACHADAS_EM_12_10_2026: dict[str, str] = {
    "api_campos": _JS, "api_previa": _JS, "api_trechos_bloqueados": _JS,
    # `arquivo_xml`, `ato_entra`, `indicador_em_xml`, `completar_ficha` e
    # `donos_presumidos` SAÍRAM EM 30/10/2026: o botão «Indicador Real (.XML)» da
    # exportação e a tela do arquivo inteiro (`onr_ir_inteiro`).
    # `cobranca` e `mensagem_documento_invalido` SAÍRAM em 20/10/2026 (LX22B2),
    # porque o varredor já as alcança. A segunda tem porta de verdade: o erro de
    # documento da apostila e das Notas (`apostila.py`, `nt_publica_forma.py`,
    # `nt_veiculo_detran.py`). A PRIMEIRA, NÃO: o LG05 pôs uma variável
    # `cobranca` numa rota de `atribuicoes_web` (a do ato do protesto), e nome
    # igual conta como um só (ver «O QUE ELE NAO PROVA», no topo). A operação do
    # SAEC continua sem botão, como as vizinhas desta linha.
    # «atendimento» saiu em 27/10/2026: o painel do celular (PR #28) lhe deu
    # caminho até tela, e o varredor é pelo nome.
    "atendimentos": _SAEC,
    "detalhes_do_protocolo": _SAEC, "gerar_cobranca": _SAEC,
    "interagir_no_atendimento": _SAEC, "tipos_de_pagamento": _SAEC,
    "validar_token_do_protocolo": _SAEC,
    # As nove de `ri_dominial` (cadeia_dominial, conteudo_vintenaria e as
    # auxiliares delas) SAÍRAM desta lista em 14/10/2026: a certidão dominial
    # e a vintenária voltaram para a ficha da matrícula (`ri_web`), e com elas
    # a porta. Fica só a que continua sem chamador.
    "atos_na_janela": "ri_dominial — " + _SEM,
    "atualizar_andamento_cenprot": "dev_projetos — " + _SEM,
    "claros_documento": "notas_atas_ensaio/notas_procuracao_ensaio — " + _SEM,
    "dias_selecionados_do_row": "nu_avisos_gestao — " + _SEM,
    "nome_ou_login_indica_robo": "selo_robo — " + _SEM,
    # `pendentes_onr` SAIU EM 30/10/2026: a exportação para o ONR mostra a lista.
    "host_da_serventia": "selador_config — " + _SEM + " (só a própria base_sugerida a chama)",
    "base_sugerida": "selador_config — " + _TESTE,
    "buscar_duplicatas_por_documento": "cpf_cnpj — " + _TESTE,
    "carregar_privada": "assinatura_da_atualizacao — a porta é `tools/criar_atualizacao.py` (assinar o .cgu)",
    # 27/10/2026 (PR #48): cadastrar a chave pública na instalação é do oficial,
    # na linha de comando, com a senha digitada por ele — de propósito sem tela.
    "gravar_chave_na_instalacao": "assinatura_da_atualizacao — a porta é `tools/chave_de_atualizacao.py` (gerar/cadastrar --instalacao)",
    # 14/10/2026: a porta é `tools/conferir_instalacao.py emergencia`, que o
    # SERVIDOR\ATUALIZAR_SISTEMA.cmd chama depois de copiar — de propósito sem
    # tela: a emergência é o caminho que não passa pela tela de Atualizações.
    "registrar_emergencia": "retrato_da_instalacao — " + _TOOLS + " (o ATUALIZAR_SISTEMA.cmd a chama)",
    "contagem_criticas_notificacao": "tarefa_processo — " + _TOOLS + " (release 262)",
    "contagem_pendentes_nao_criticas": "tarefa_processo — " + _TOOLS + " (release 262)",
    "contagem_pendentes_notificacao": "tarefa_processo — " + _TOOLS + " (release 262)",
    "texto_tarefas_pendentes": "tarefa_processo — " + _TOOLS + " (release 262/263)",
    "definir_chave": "modelos_editor — " + _TESTE,
    "fonte_mapa": "modelos_editor_serventia — " + _TESTE,
    "folha_da_certidao": "papel_seguranca — " + _TESTE + " (1ª via, 09/10)",
    "hosts_producao_conhecidos": "centrais_trava_sandbox — régua do teste da trava do SANDBOX",
    "id_livre": "ajuda_problemas — " + _TOOLS + " (`import_problemas_fila.py`)",
    "id_oficial_da_nota": "ajuda_problemas — auxiliar de `realinhar_id_problema`",
    "preencher_ambiente_abertura": "ajuda_problemas — " + _TOOLS + " (`import_problemas_fila.py`)",
    "realinhar_id_problema": "ajuda_problemas — " + _TOOLS + " (`import_problemas_fila.py`)",
    "realinhar_ids_replicados": "ajuda_problemas — " + _TOOLS + " (`import_problemas_fila.py`)",
    "ligar_o_selador": "selador_de_bancada — a bancada dos testes, e não peça do balcão",
    "tem_cryptography": "selador_de_bancada — a bancada dos testes, e não peça do balcão",
    "numero_de_controle": "notas_doi — " + _TESTE,
    "reservar_processo": "recursos_da_maquina — " + _TESTE,
    "status_payload": "a3_servico_local — resposta do serviço local do A3, fora do Flask",
    "sugerir_entrelinha": "notas_inutilizacao — " + _TESTE,
}


# 13/10/2026 — o assinador A3 do CCN. As duas moram no serviço local
# (`a3_servico_local.py`), que é um processo à parte do Flask: quem as chama é
# o `Manipulador` dele (as rotas POST /assinar/cades e a guarda de origem), e
# a «tela» é a extensão CG CCN Assistente. Mesma razão de `status_payload`.
ACHADAS_EM_13_10_2026: dict[str, str] = {
    "assinar_cades": "a3_servico_local — rota POST /assinar/cades do serviço local, fora do Flask",
    "origem_recusada": "a3_servico_local — guarda das rotas do serviço local, fora do Flask",
}


# 14/10/2026 — achada na suíte inteira desse dia. Escrita em 13/10/2026 pela
# passada do Protesto («a virada do protesto»: marcar como já informados à CRA
# os atos do E-Ofício que os arquivos da pasta da CRA provam). Medido em
# 14/10: nenhum chamador na raiz, em `tests/`, em `tools/`, em FERRAMENTAS nem
# no INSTALAR; quem a chamou foi o script pontual
# `CartorioGestao/tmp/protesto_virada_20261013/2_virada.py`, fora da árvore
# do sistema. Fica DECLARADA, e não apagada: o módulo é de outra passada, e
# ligar a porta (tela ou script de `tools/`) é decisão dela.
#
# E A FILA COMUM DAS CENTRAIS (marco b, 05/10/2026) PERDEU A ÚNICA PORTA NO
# MESMO DIA, às 08h44: a passada do Protesto tirou a homologação das telas da
# CRA e da CENPROT («SÓ PRODUÇÃO, E DIRETO (14/10/2026)», `cra21_web.py` e
# `cenprot_web.py`), e o teste de ligação em homologação era quem chamava
# `testar_pela_fila`. As peças continuam testadas em
# `tests/test_centrais_fila.py`. Religar ou apagar é decisão daquela passada.
_FILA = ("centrais_fila — a porta (teste de ligação em homologação) saiu da "
         "tela em 14/10/2026; testada, sem chamador no sistema")
ACHADAS_EM_14_10_2026: dict[str, str] = {
    "marcar_o_que_o_eoficio_ja_informou":
        "protesto_retorno — virada do protesto (13/10); a porta foi o script "
        "pontual tmp/protesto_virada_20261013/2_virada.py, fora do sistema",
    # «enfileirar» saiu em 26/10/2026: o nome ganhou caminho até tela com os
    # avisos de andamento (`andamento_avisos.enfileirar`), e o varredor é pelo nome.
    "devolver_presos": _FILA,
    "espera_da_tentativa": _FILA, "marcar_confirmado": _FILA,
    "marcar_enviado": _FILA, "marcar_falha": _FILA, "pegar_proximo": _FILA,
    "processar_proximo": _FILA,
    "testar_pela_fila": "protesto_centrais_fila — " + _FILA,
}

# LF06A, 19/10/2026 — os modelos saíram do código para a base dos padrões. As
# que estão aqui não são ação de balcão, e cada uma diz por quê.
#
# `texto_do_papel` SAIU DAQUI NO MESMO DIA, com o LF06G: a notificação da
# retificação, os papéis da usucapião e o dossiê a chamam, e as telas deles a
# alcançam — era o que a entrada dela esperava dos lotes seguintes. O LF06B
# chegou ao mesmo lugar por outro lado: as frases do RI a leem por
# `ri_frases.texto`, e a ficha, a certidão e o cancelamento chegam a ela.
# O LF06C também: os papéis do Registro Civil a leem por `rc_textos.texto`.
ACHADAS_EM_19_10_2026: dict[str, str] = {
    "constante_antiga":
        "modelos_da_casa — chamada pelo `__getattr__` dos catorze módulos que "
        "guardavam o texto; o varredor não segue `__getattr__`",
    "esquecer_padroes":
        "modelos_da_casa — para quem recarregou a base no mesmo processo "
        "(teste, ferramenta); o serviço recarrega ao reiniciar na atualização",
    # LF06D, mesmo dia — os textos das Notas foram para a base.
    "tipos_autenticacao":
        "notas_schema — devolve o `TIPOS_AUTENTICACAO` antigo (texto + item), "
        "lido da base, pelo `__getattr__` do módulo; o varredor não segue "
        "`__getattr__`, e a tela usa `AUTENTICACOES`, que não precisa do texto",
}


# 20/10/2026 (LX22B2) — AS CINCO QUE A SEGUNDA LEVA DA MIGRAÇÃO DEIXOU.
#
# Medido contra `relatorios/base_antes_dos_lotes.log` (a suíte de antes dos
# lotes LX10–LX21 e LG01–LG08): a lista de órfãs de lá tinha 32 nomes, a da
# suíte de 19/10 22:53 tem 37, e a diferença é exatamente esta. Nenhuma é
# tela anunciada que faltou: duas são a régua da RFC que o teste confere, uma
# é peça da ponte que a conversão esvaziou, e duas perderam o chamador DE
# PROPÓSITO — o lote que as trocou fez a troca certa e não apagou a velha.
ACHADAS_EM_20_10_2026: dict[str, str] = {
    # LG02 — o servidor confere o código passo a passo por `hotp` dentro de
    # `passo_aceito`; `totp` é o código que o APLICATIVO calcula, e o teste o
    # usa para fazer de aplicativo (vetores da RFC 6238, apêndice B).
    "totp": "dois_fatores — " + _TESTE + " (o aplicativo do celular é quem calcula; LG02)",
    "de_base32": "dois_fatores — inverso de `em_base32`; " + _TESTE + " (LG02)",
    # Só `Conexao.executescript` a chama, e os lotes nativos trocaram todo
    # `executescript` do caminho das telas por `bd.escrever` por comando.
    "dividir_comandos": "banco_pg — só a ponte (`Conexao.executescript`) a chama, e a "
                        "conversão nativa tirou o último `executescript` das telas",
    # LX14 (B1 do LS03): a tela dos robôs e a do WhatsApp mostram só
    # «configurado», sem os últimos quatro do segredo. A troca é a regra nova;
    # a máscara ficou sem chamador.
    "mascarar_segredo": "robo_schema/wa_balcao — " + _SEM + " (o LX14 tirou a máscara da tela)",
    # LX16: a barra das gratuidades passou a dizer também o selo mais antigo, e
    # `aviso` faz a conta inteira; a contagem solta ficou sem chamador.
    "quantos_pendentes": "gratuidade_comprovante — " + _SEM + " (o LX16 a trocou por `aviso`)",
}


# 27/10/2026 — A DA PESQUISA DE SATISFAÇÃO (PR da ouvidoria). Sem tela DE
# PROPÓSITO: o oficial decidiu que o link vai só ao cliente, e a tela do balcão
# nunca mostra o token. Quem assina é o ENVIO do convite, que não existe neste
# ramo — o convite fica na fila (`NA_FILA`) até haver o canal.
ACHADAS_EM_27_10_2026: dict[str, str] = {
    # O ENVIO EXISTE desde a pesquisa na VPS (26/10/2026), mas o link do e-mail
    # leva `satisfacao_envio.codigo_do_convite`, e não este token: a página
    # local do convite ficou sem quem assine.
    "assinar_convite": "satisfacao — o envio por e-mail usa `codigo_do_convite` (a "
                       "página na VPS); " + _SEM,
    # A cobrança por boleto (PR #65): o processo da central de automação é
    # chamado pelo catálogo (`CATALOGO` → «cobranca_automacao.acompanhar»,
    # texto que este varredor não lê), e a tela dele é a da central.
    "acompanhar": "cobranca_automacao — a porta é o catálogo da central de "
                  "automação (`automacao_processos.MODULOS_COM_PROCESSOS`)",
    # O robô do Malote (PR #123, 29/10/2026): o mesmo caminho — o catálogo
    # da automação («malote_robo.ciencia_diaria»).
    "ciencia_diaria": "malote_robo — a porta é o catálogo da central de "
                      "automação (`automacao_processos.MODULOS_COM_PROCESSOS`)",
    # A conferência CENPROT × sistema (PR #105): o roteiro do protesto a lê
    # pelo gancho (`protesto_roteiro.GANCHOS`, módulo e função em texto, que
    # este varredor não lê), e a tela dela é a conduta 9 do roteiro.
    "quantos_divergem": "cenprot_conferencia — a porta é o gancho do roteiro "
                        "do protesto (`protesto_roteiro.GANCHOS`)",
}


# 29/10/2026 — A RELAÇÃO DA GUIA DE REPASSE DO PROTESTO. A rotina é chamada pelo
# catálogo de `protesto_repasse_automacao` («...gerar_a_relacao_do_dia», texto
# que este varredor não lê); o que ela faz tem porta própria na tela de
# repasses (`gerar_guias_do_dia`, `pendencias_do_repasse`), e só a casca da
# rotina fica sem tela.
ACHADAS_EM_29_10_2026_REPASSE: dict[str, str] = {
    "gerar_a_relacao_do_dia": "protesto_repasse_automacao — a porta é o catálogo "
                              "da central de automação "
                              "(`automacao_processos.MODULOS_COM_PROCESSOS`)",
}


# ACHADAS EM 26/10/2026, NA ORDEM DO OFICIAL «não deixar nenhuma falha antiga
# sem correção». Eram 33 e este teste estava vermelho no `main` desde a virada
# para o PostgreSQL. Medido quem chama cada uma, na raiz, em `tests/`, em
# `tools/` e nos roteiros do SANDBOX:
#   - **uma não tinha chamador em lugar nenhum** (`banco_pg.apagar_reservas`) e
#     foi APAGADA, e não declarada;
#   - as outras têm porta de verdade, que este varredor não enxerga porque só
#     lê os módulos da raiz: o banco de teste (`tests/conftest.py`,
#     `tests/banco_de_teste.py`), o serviço A3 — processo próprio, porta 8766 —
#     e o cliente dele, os roteiros de ensaio chamados por
#     `tools/carga_de_demonstracao.py`, e auxiliares testadas.
_BANCO_DE_TESTE = ("banco_pg — infraestrutura do PostgreSQL de teste: quem a chama "
                   "é `tests/conftest.py`/`tests/banco_de_teste.py`, ou outra "
                   "função dela mesma a partir dali")
_A3 = ("serviço A3 local (processo próprio, porta 8766) e o cliente dele "
       "(`assinar_com_a3`): a porta é o HTTP do serviço e `tools/a3_ensaio_cli.py`")
_ENSAIO = ("roteiro de ensaio do sandbox — a porta é "
           "`tools/carga_de_demonstracao.py` (ou outra função do mesmo roteiro)")
ACHADAS_EM_26_10_2026: dict[str, str] = {
    "guardar_semente": _BANCO_DE_TESTE, "marca_do_codigo": _BANCO_DE_TESTE,
    "devolver_schema": _BANCO_DE_TESTE, "apagar_lixo": _BANCO_DE_TESTE,
    "tomar_da_reserva": _BANCO_DE_TESTE,
    # `schema_existe` saiu em 27/10/2026: a linha de comando da sincronia dos
    # problemas (`problemas_sincronia.main`) a usa para recusar schema que não
    # existe, em vez de criá-lo vazio.
    "comecar_gravacao": _BANCO_DE_TESTE,
    "terminar_gravacao": _BANCO_DE_TESTE, "criar_por_reproducao": _BANCO_DE_TESTE,
    "descartar_schema": _BANCO_DE_TESTE, "schemas_criados": _BANCO_DE_TESTE,
    # `instalar_desvio`, `registrar_banco`, `listar_certificados`, `assinar_pdf` e
    # `status_do_servico` saíram em 27/10/2026: os PRs que entraram antes deste
    # (#11, #13, #27) lhes deram caminho até tela.
    "esvaziar_reservatorio": _BANCO_DE_TESTE,
    "garantir_certidao": "rcpn_*_ensaio — " + _ENSAIO,
    "garantir_assento": "rcpn_*_ensaio — " + _ENSAIO,
    "assento_precisa_remontar": "rcpn_*_ensaio — " + _ENSAIO,
    "certidao_precisa_remontar": "rcpn_*_ensaio — " + _ENSAIO,
    "montar_teor_certidao": "rcpn_*_ensaio — " + _ENSAIO,
    "teor_precisa_remontar": "notas_*_ensaio — " + _ENSAIO,
    "garantir_registrado": "ri_certidao_emissao — " + _TESTE + " (ponte fora do request)",
    "montar_corpo": "ri_certidao_emissao — " + _TESTE + " (ponte fora do request)",
    "teor_precisa_remontar_modelo": "ri_certidao_emissao — " + _TESTE,
    # REESCREVE O CORPO DE CERTIDÃO JÁ EMITIDA: só o roteiro de ensaio do
    # SANDBOX (`ensaio_revisao_modular.py`, fora do repositório) a chama, e ela
    # não deve ganhar botão — certidão emitida não se remonta no balcão.
    "remontar_corpo_gravado": ("ri_certidao_emissao — só o roteiro de ensaio do "
                               "SANDBOX a chama; não deve ganhar tela"),
    # `pagamentos_pendentes` SAIU EM 30/10/2026: «Selo e caixa» mostra a cobrança
    # de quem abriu a tela, que é para onde a barra vermelha manda.
    "certidao_livro3_teor_precisa_modelo_novo": "atrib_certidao — " + _TESTE,
    "remontar_teor_certidao_livro3": "atrib_certidao — " + _TESTE,
    "novo_caminho": "pastas_da_casa — " + _TESTE,
}


# 30/10/2026 — o lote de assinatura pelo Windows. Mora no assinador do serviço
# local, e quem a chama é o `Manipulador` dele (POST /assinar/pdfs-windows). Mesma
# razão de `assinar_cades`.
ACHADAS_EM_30_10_2026: dict[str, str] = {
    "assinar_pdfs": ("a3_windows — rota POST /assinar/pdfs-windows do serviço "
                     "local, fora do Flask"),
}


def _conhecidas() -> set[str]:
    """As medições datadas que formam o piso do varredor."""
    return (set(JA_SABIDAS) | set(NASCIDAS_DEPOIS_DA_3_6_51)
            | set(REVELADAS_AO_SEPARAR_PROSA_DE_CHAMADA)
            | set(ACHADAS_EM_14_09_2026)
            | set(ACHADAS_EM_15_09_2026)
            | set(ACHADAS_EM_19_09_2026)
            | set(ACHADAS_EM_05_10_2026)
            | set(ACHADAS_EM_08_10_2026)
            | set(ACHADAS_EM_12_10_2026)
            | set(ACHADAS_EM_13_10_2026)
            | set(ACHADAS_EM_14_10_2026)
            | set(ACHADAS_EM_19_10_2026)
            | set(ACHADAS_EM_20_10_2026)
            | set(ACHADAS_EM_26_10_2026)
            | set(ACHADAS_EM_27_10_2026)
            | set(ACHADAS_EM_29_10_2026_REPASSE)
            | set(ACHADAS_EM_30_10_2026))


def test_nenhuma_funcao_nova_fica_sem_tela():
    """**O TETO.** Funcao nova sem porta fica vermelha aqui, e nao meses
    depois, quando o oficial perguntar por que a tela que lhe foi anunciada
    nao existe."""
    achadas = _orfas()
    conhecidas = _conhecidas()
    novas = sorted(set(achadas) - conhecidas)
    assert not novas, (
        "estas funções não têm caminho até nenhuma tela:\n  "
        + "\n  ".join(f"{n}  ({', '.join(achadas[n])})" for n in novas)
        + "\n\nFunção pronta que ninguém chama é o defeito que mais se repetiu "
          "neste projeto — construa a tela junto, ou diga aqui por que ela não "
          "tem uma.")


def test_a_lista_de_conhecidas_nao_vira_deposito():
    """**O PISO.** Nome que deixou de ser órfão sai da lista.

    Sem isto, a lista só cresce e o varredor vira enfeite: daqui a um ano
    ninguém sabe quais daqueles nomes ainda são de verdade.
    """
    achadas = set(_orfas())
    conhecidas = _conhecidas()
    ja_resolvidas = sorted(conhecidas - achadas)
    assert not ja_resolvidas, (
        f"estas já têm tela e continuam na lista de conhecidas: "
        f"{ja_resolvidas}. Tire-as de `JA_SABIDAS`.")


def test_as_duas_que_motivaram_este_varredor_tem_tela():
    """As de 30/08/2026. Se voltarem a ficar sem porta, o conserto se desfez."""
    achadas = set(_orfas())
    for nome in ("informacoes_importadas", "atos_sem_checklist"):
        assert nome not in achadas, (
            f"«{nome}» voltou a ficar sem tela — foi exatamente esta a falha "
            f"que este arquivo existe para impedir")


# ===================================================================
# O IRMAO DO VARREDOR ACIMA, PARA **CAMPO**
#
# Em 30/08/2026 se mediu que cinco colunas de `rc_assentos` — `cor_raca`,
# `hora_fato`, `local_fato_nome`, `local_fato_endereco` e
# `naturalidade_declarada` — tinham sido criadas na vespera para o termo e as
# remessas, e que **nada as preenchia**: o formulario de lavratura nao
# perguntava nenhuma, e `lavrar_assento` nao lia nenhuma.
#
# **COLUNA QUE NADA PREENCHE E COLUNA QUE MENTE.** A remessa acusa «falta o
# dado», o escrevente procura onde informar, e nao ha onde. E pior que o campo
# nao existir: quem ve a coluna no banco supoe que alguem a preenche.
# ===================================================================

FORMULARIO_DE_LAVRATURA = RAIZ / "templates" / "atrib_rcpn_novo.html"


def _campos_do_formulario() -> set[str]:
    """Os `name=` da tela, incluindo os que as macros geram por prefixo."""
    html = FORMULARIO_DE_LAVRATURA.read_text(encoding="utf-8")
    nomes = set(re.findall(r'name="([a-zA-Z_0-9]+)"', html))
    # As macros geram `{{ p }}_campo`; aqui basta o sufixo.
    for m in RAIZ.glob("templates/_*.html"):
        t = m.read_text(encoding="utf-8")
        nomes |= set(re.findall(r'name="\{\{ *\w+ *\}\}_([a-zA-Z_0-9]+)"', t))
        nomes |= set(re.findall(r'name="[^"]*_([a-zA-Z_0-9]+)"', t))
    # A MACRO QUE A TELA IMPORTA É A TELA — 13/10/2026. O bloco do Livro E
    # mora em `_livro_e.html` porque a tela de corrigir a ficha usa o mesmo;
    # os nomes dele são LITERAIS (`livro_e_juizo`), e o sufixo acima só
    # guardava o pedaço depois do último «_». Vale só para a macro que o
    # formulário de lavratura de fato importa.
    for importada in re.findall(r"""{%\s*from\s+['"](_[\w]+\.html)['"]""", html):
        alvo = RAIZ / "templates" / importada
        if alvo.exists():
            nomes |= set(re.findall(r'name="([a-zA-Z_0-9]+)"',
                                    alvo.read_text(encoding="utf-8")))
    return nomes


def test_o_que_o_termo_pede_a_tela_pergunta():
    """Se `lavrar_assento` aceita um campo do termo, a tela tem de oferece-lo.

    Sem isto, a coluna nasce, o modulo a le, e ninguem a preenche nunca — que
    foi exatamente o que aconteceu com estas cinco entre 29 e 30/08/2026.
    """
    import rc_assento as RC
    na_tela = _campos_do_formulario()
    todos = {c for campos in RC.CAMPOS_DO_TERMO_POR_ESPECIE.values()
             for c in campos}
    faltam = sorted(c for c in todos if c not in na_tela)
    assert not faltam, (
        f"o termo pede estes campos e o formulário de lavratura não os "
        f"pergunta: {faltam}. Coluna que nada preenche é coluna que mente — "
        f"a remessa acusa «falta o dado» e não há onde informá-lo.")


def test_as_quatro_marcas_do_obito_tem_onde_ser_respondidas():
    """Elas sao gatilhos: marcar «eleitor» e o que faz a comunicacao a Justica
    Eleitoral existir. Sem tela, a obrigacao nunca nasce.

    **PROCURAR O NOME LITERAL NO HTML NAO SERVE AQUI**, e a primeira versao
    deste teste ficou vermelha por isso: a tela gera os campos num laco,
    `name="{{ m.chave }}"`, e o nome so existe em tempo de execucao. Campo
    gerado por laco se confere pela ROTA que o le — que e o que esta abaixo.
    """
    import rc_marcas_do_obito as MARCA
    web = (RAIZ / "atribuicoes_web.py").read_text(encoding="utf-8")
    assert "MARCA.CHAVES" in web, (
        "nenhuma rota lê as marcas do óbito — a pergunta não tem onde ser "
        "feita, e a obrigação que ela dispara nunca nasce")
    telas = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                      for p in RAIZ.glob("templates/*.html"))
    assert "marcas" in telas and "assento_id" in telas
    # e a lista de chaves nao pode ter encolhido sem a tela saber
    assert len(MARCA.CHAVES) == 4
