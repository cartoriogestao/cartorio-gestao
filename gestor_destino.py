"""PARA ONDE VAI CADA REGRA DO GESTOR — a checklist, a tarefa do escrevente ou o projeto.

    «limpar o checklist do dia e deixar apenas tarefas que podem ser feitas pela
    TI ou por admin. Checklist do dia nao serve para pratica de atos do
    cartorio, nem para atos materiais que necessitam estar fisicamente no
    cartorio. [...] As tarefas dos escreventes devem ficar no campo de
    processos com tarefas para resolverem. [...] A aba projetos serve para
    projetos maiores» — o oficial, 25/11/2026 (G007)

OS TRÊS LUGARES
    TI_ADMIN    a Checklist do dia (`gestor_checklist`). O que a TI ou o
                administrador resolvem em lote, por mudança no sistema, por IA
                ou por rotina geral: as cargas das centrais em dia (SIRC, CRC,
                CENSEC, DOI, CTP, IBGE, óbitos, ONR), cópia de segurança, robô
                parado, conciliação do selo com o TJ, decisão do oficial, visto
                no caixa, regra que mede errado.
    ESCREVENTE  a tarefa no processo (Processos e Malote). A prática do ato, a
                retificação, a digitalização, o que pede livro, papel, balcão ou
                dinheiro contado, e a conferência física. O gestor já abre uma
                tarefa por regra e setor (`gestor_rotina.sincronizar_tarefas`);
                a checklist só diz quantos saíram dela e onde está a tarefa.
    PROJETO     a aba Projetos. O passivo grande, a carga inicial numa central
                nova, a decisão sobre o acervo inteiro.

UMA TABELA SÓ, E ELA NÃO MEXE NA COR
    `DESTINO` é o único lugar que diz o destino de uma regra. Ele muda o que a
    checklist LISTA, e só: o semáforo (`conformidade.medir`) continua contando
    todos os achados abertos, de qualquer destino. Ninguém pinta área de verde
    tirando achado da lista.

REGRA QUE A TABELA NÃO CONHECE FICA NA CHECKLIST
    Regra nova sem destino aparece na checklist (TI_ADMIN), para a TI ver e
    classificar — sumir com ela seria esconder o que ninguém decidiu. O teste
    (`tests/test_gestor_destino.py`) cobra que toda regra com rótulo no gestor
    esteja aqui.

O QUE AINDA NÃO TEM CAMINHO DE TAREFA (proposta ao titular, G007)
    Algumas regras de escrevente estão em `gestor_rotina.REGRAS_SEM_TAREFA` por
    ordens anteriores do oficial (06/10, 13/10 e 18/11/2026: só vira tarefa o
    que pode dar responsabilidade civil). Elas saem da checklist como as outras,
    mas a tela as mostra à parte, «sem tarefa», para não sumirem: é
    `SEM_TAREFA_A_DECIDIR`. Virar tarefa depende do «pode» do titular — e a
    mudança é tirá-las de `REGRAS_SEM_TAREFA`. O teste amarra as duas listas.

SÓ CALCULA
    Nada aqui grava. `tarefas_do_gestor` só lê `tasks`.
"""
from __future__ import annotations

from bd_nativo import banco

TI_ADMIN, ESCREVENTE, PROJETO = "TI_ADMIN", "ESCREVENTE", "PROJETO"
DESTINOS = (TI_ADMIN, ESCREVENTE, PROJETO)
ROTULO_DO_DESTINO = {
    TI_ADMIN: "TI e administração (checklist do dia)",
    ESCREVENTE: "Escreventes (tarefa no processo)",
    PROJETO: "Projeto",
}

#: Os motivos que se repetem, para a tabela caber na tela.
_CARGA = "carga ou comunicação a central: envio em lote pela TI ou por agente"
_INFRA = "infraestrutura, robô ou configuração do sistema"
_CONCILIA = "conciliação do selo com o TJ: em lote, pelo administrador"
_DECIDE = "decisão do oficial"
_CONTROLE = "controle do que já passou: medir e corrigir a regra, sem ato a praticar"
_ATO = "prática ou correção do ato, por quem lavrou"
_LIVRO = "livro, folha ou termo: precisa estar no cartório"
_CAIXA = "dinheiro contado no balcão: quem fechou o caixa"
_DIGI = "digitalização: só quem está no cartório (ordem de 25/11/2026)"
_TEXTO = "texto do ato lavrado: retificação por quem qualifica"
_PASSIVO = "passivo grande ou cadastro em central nova"

#: A TABELA: regra → (destino, motivo). Uma linha por regra do gestor.
DESTINO: dict[str, tuple[str, str]] = {
    # ---- as centrais e as cargas (ordem de 13/10/2026: centralizadas por agentes)
    "SIRC": (TI_ADMIN, _CARGA),
    "SIRC_CANCELAMENTO": (TI_ADMIN, _CARGA),
    "CRC": (TI_ADMIN, _CARGA),
    "FUNAI": (TI_ADMIN, _CARGA),
    "IBGE": (TI_ADMIN, _CARGA),
    "OBITO_MENSAL": (TI_ADMIN, _CARGA),
    "CENSEC": (TI_ADMIN, _CARGA),
    "CENSEC_AUTOMATICO": (TI_ADMIN, _CARGA),
    "DOI": (TI_ADMIN, _CARGA),
    "CARGAS_RCPN_AGENTE_PARADO": (TI_ADMIN, _INFRA),
    "CARGAS_RCPN_DECISAO": (TI_ADMIN, _DECIDE),
    "CARGAS_RCPN_FALTA": (TI_ADMIN, "dado que falta para montar a carga: completar em lote"),
    "CARGAS_RCPN_INVALIDA": (TI_ADMIN, _CARGA),
    "CARGAS_RCPN_PRONTA": (TI_ADMIN, _CARGA),
    "ONR_AGENTE_PARADO": (TI_ADMIN, _INFRA),
    "ONR_CREDENCIAL": (TI_ADMIN, _DECIDE),
    "ONR_ENVIO_DESLIGADO": (TI_ADMIN, _DECIDE),
    "ONR_ENVIO_FALHOU": (TI_ADMIN, _CARGA),
    "ONR_FILA_PARADA": (TI_ADMIN, _CARGA),
    "ONR_IMAGEM_PROBLEMA": (TI_ADMIN, _CARGA),
    "ONR_INDICADOR_INCOMPLETO": (TI_ADMIN, "dado da matrícula para o Indicador Real: IA ou lote"),
    "ONR_INDICADOR_RECUSADO": (TI_ADMIN, _CARGA),
    "ONR_IPS_NAO_LEVOU": (TI_ADMIN, _CARGA),
    "ONR_PAINEL_DIVERGENCIA": (TI_ADMIN, _CARGA),
    "ONR_PAINEL_OBRIGACAO": (TI_ADMIN, _DECIDE),
    "ONR_PAINEL_PENDENCIA": (TI_ADMIN, _CARGA),
    "ONR_PASTA": (TI_ADMIN, _INFRA),
    "RTDPJ_CENTRAL_NAO_LIDA": (TI_ADMIN, _INFRA),
    # ---- infraestrutura, robôs e o próprio sistema
    "BACKUP": (TI_ADMIN, _INFRA),
    "DISCO": (TI_ADMIN, _INFRA),
    "PASTA_DO_BANCO": (TI_ADMIN, _INFRA),
    "DADO_DE_TESTE": (TI_ADMIN, _INFRA),
    "CNIB_PARADO": (TI_ADMIN, _INFRA),
    "CORRENTE_RI": (TI_ADMIN, _INFRA),
    "IDENTIDADE_DOS_ROBOS": (TI_ADMIN, _INFRA),
    "RCPN_AGENTE_PARADO": (TI_ADMIN, _INFRA),
    "PROTESTO_CRA": (TI_ADMIN, _INFRA),
    "PROTESTO_PASTA_CRA": (TI_ADMIN, _INFRA),
    "PROTESTO_MODELO_DO_TERMO": (TI_ADMIN, "modelo do termo: mudança no sistema, com o oficial"),
    "RTDPJ_REGISTRO_REPETIDO": (TI_ADMIN, "dado repetido na base: correção em lote"),
    "RTDPJ_CORRIGIDO": (TI_ADMIN, "revisar o que o agente corrigiu sozinho"),
    "ATO_POR_FORA": (TI_ADMIN, "trilha do sistema: apurar quem lavrou por fora"),
    "SELO_ORFAO": (TI_ADMIN, _CONCILIA),
    # ---- selo, fundos e caixa — o que se faz pela tela, em lote
    "SELO_CANCELADO_LOCAL": (TI_ADMIN, _CONCILIA),
    "FISCAL_CANCELADO_SO_NO_SISTEMA": (TI_ADMIN, _CONCILIA),
    "FISCAL_ISENCAO_DIVERGENTE": (TI_ADMIN, _CONCILIA),
    "FISCAL_ISENTOS_DO_DIA": (TI_ADMIN, _CONCILIA),
    "FISCAL_PORTAL_SEM_RESPOSTA": (TI_ADMIN, _CONCILIA),
    "FISCAL_SELO_FORA_DO_PORTAL": (TI_ADMIN, _CONCILIA),
    "FISCAL_VALOR_DIVERGENTE": (TI_ADMIN, _CONCILIA),
    "FISCAL_SELOS_FORA_DO_SISTEMA": (TI_ADMIN, _CONCILIA),
    "FISCAL_GRATUIDADE_EM_ANALISE": (TI_ADMIN, "acompanhar a análise do TJ"),
    "FISCAL_GRATUIDADE_SEM_MOTIVO": (TI_ADMIN, _CONCILIA),
    "FISCAL_GRATUIDADE_INDEFERIDA": (TI_ADMIN, _DECIDE + ": recorrer ou recolher"),
    "CAIXA_PRONTO_PARA_VISTO": (TI_ADMIN, "visto do oficial no caixa fechado"),
    "CAIXA_COM_PONTOS": (TI_ADMIN, "visto do oficial no caixa fechado"),
    "FECHAMENTO_DO_MES": (TI_ADMIN, "fechamento do mês: selos × caixa, pelo administrador"),
    "PLD_COAF": (TI_ADMIN, _DECIDE + " (sigiloso)"),
    "RTDPJ_SEM_PAGAMENTO": (TI_ADMIN, "cobrança e dinheiro da casa: administrador"),
    # ---- o que já passou do prazo e não tem ato a praticar: controle
    "PROTESTO_FORA_DO_TRIDUO": (TI_ADMIN, _CONTROLE),
    "PROTESTO_INTIMACAO_TARDIA": (TI_ADMIN, _CONTROLE),
    "PROTESTO_PROTOCOLO_TARDIO": (TI_ADMIN, _CONTROLE),
    "PROTESTO_RETORNO_TARDIO": (TI_ADMIN, _CONTROLE),
    "PROTESTO_FORA_DO_SISTEMA": (TI_ADMIN, "processo de trabalho fora do sistema: administrador"),
    # ---- PROJETO: o passivo grande e a central nova
    "ONR_ACERVO_DECISAO": (PROJETO, _PASSIVO),
    "ONR_CARGA_INICIAL": (PROJETO, _PASSIVO),
    "PROTESTO_ANTES_DO_CORTE": (PROJETO, _PASSIVO),
    # ---- ESCREVENTE: digitalização
    "DIGITALIZACAO_DA_FICHA": (ESCREVENTE, _DIGI),
    "DIGITALIZACAO_ATRASADA": (ESCREVENTE, _DIGI),
    # ---- ESCREVENTE: caixa do balcão
    "CAIXA_DO_DIA_ABERTO": (ESCREVENTE, _CAIXA),
    "CAIXA_ABERTO": (ESCREVENTE, _CAIXA),
    "CAIXA_DIFERENCA": (ESCREVENTE, _CAIXA),
    # ---- ESCREVENTE: o ato, o texto e o livro
    "ATO_SEM_SELO": (ESCREVENTE, _ATO),
    "FISCAL_CANCELADO_NO_PORTAL": (ESCREVENTE, "selo novo no ato vivo: por quem lavrou"),
    "NUMERACAO": (ESCREVENTE, _LIVRO),
    "DOCUMENTO_INVALIDO": (ESCREVENTE, _ATO),
    "TEXTO_CONTRA_CADASTRO": (ESCREVENTE, _TEXTO),
    "LEITURA_DO_TEXTO": (ESCREVENTE, _TEXTO),
    "MODELO_NAO_PREENCHIDO": (ESCREVENTE, _TEXTO),
    "REVISAO_DO_AGENTE": (ESCREVENTE, _TEXTO),
    "MINUTA_EM_FICHA_ENCERRADA": (ESCREVENTE, _ATO),
    "PRENOTACAO_VENCIDA": (ESCREVENTE, _ATO),
    "PRENOTACAO_A_VENCER": (ESCREVENTE, _ATO),
    "REGISTRO_SEM_CNIB": (ESCREVENTE, _ATO),
    "REGISTRO_SEM_PRENOTACAO": (ESCREVENTE, _LIVRO),
    # Notas
    "NOTAS_ANOTACAO": (ESCREVENTE, _ATO),
    "NOTAS_CENSEC": (ESCREVENTE, "cadastro do ato que a carga recusaria: por quem lavrou"),
    "NOTAS_IMOVEL": (ESCREVENTE, _ATO),
    "NOTAS_LIVRO": (ESCREVENTE, _LIVRO),
    "NOTAS_MINUTA": (ESCREVENTE, _ATO),
    "NOTAS_PDF": (ESCREVENTE, "PDF assinado do ato: papel e assinatura no cartório"),
    "NOTAS_PDF_30_DIAS": (ESCREVENTE, "PDF assinado do ato: papel e assinatura no cartório"),
    "NOTAS_RASCUNHO": (ESCREVENTE, "rascunho: quem lavra decide se completa ou apaga"),
    "NOTAS_RASCUNHO_QUINZENA_FECHADA": (ESCREVENTE, _ATO),
    # Protesto
    "PROTESTO_ATO_SEM_SELO": (ESCREVENTE, _ATO),
    "PROTESTO_CERTIDAO_NEGATIVA_INDEVIDA": (ESCREVENTE, _ATO),
    "PROTESTO_DESISTENCIA_SEM_BAIXA": (ESCREVENTE, _ATO),
    "PROTESTO_DOCUMENTO_DO_DEVEDOR": (ESCREVENTE, _ATO),
    "PROTESTO_EDITAL_SEM_DILIGENCIA": (ESCREVENTE, _ATO),
    "PROTESTO_INDEVIDO": (ESCREVENTE, "levantar o caso; o oficial decide cada um"),
    "PROTESTO_PAGAMENTO_SEM_LIVRO": (ESCREVENTE, _LIVRO),
    "PROTESTO_REMESSA_SEM_CONFIRMACAO": (ESCREVENTE, _ATO),
    "PROTESTO_SEM_RESPOSTA": (ESCREVENTE, _ATO),
    "PROTESTO_SUSTACAO_REVOGADA": (ESCREVENTE, _ATO),
    "PROTESTO_TITULO_PARADO": (ESCREVENTE, _ATO),
    # Registro Civil
    "RCPN_ANOTACAO": (ESCREVENTE, "anotação e comunicação do art. 367: ato do registrador"),
    "RCPN_ANOTACAO_DE_CANCELADO": (ESCREVENTE, _ATO),
    "RCPN_DADOS_A_CONFERIR": (ESCREVENTE, "conferir o assento contra o livro: no cartório"),
    "RCPN_DADOS_CONTRADITORIOS": (ESCREVENTE, _ATO),
    "RCPN_DADO_COMPLEMENTAR": (ESCREVENTE, "conferir o assento contra o livro: no cartório"),
    "RCPN_DADO_OBRIGATORIO": (ESCREVENTE, _ATO),
    "RCPN_DUPLICIDADE": (ESCREVENTE, _ATO),
    "RCPN_FOLHA_SEGURANCA": (ESCREVENTE, "folha de segurança: estoque físico no cartório"),
    "RCPN_HABILITACAO": (ESCREVENTE, _ATO),
    "RCPN_INACABADO": (ESCREVENTE, _ATO),
    "RCPN_PEDIDO_CENTRAL": (ESCREVENTE, "certidão pedida pela central: ato a praticar"),
    "RCPN_RETIFICACAO": (ESCREVENTE, _ATO),
    "RCPN_SEM_TERMO": (ESCREVENTE, _LIVRO),
    "RCPN_TERMO_ALTERADO": (ESCREVENTE, _ATO),
    # RTD e PJ
    "RTDPJ_CENTRAL_PENDENTE": (ESCREVENTE, "pedido da central: ato a praticar"),
    "RTDPJ_CERTIDAO_SEM_SELO": (ESCREVENTE, _ATO),
    "RTDPJ_ENCERRAMENTO_DIARIO": (ESCREVENTE, _LIVRO),
    "RTDPJ_LIVRO": (ESCREVENTE, _LIVRO),
    "RTDPJ_SELO_DA_ETIQUETA": (ESCREVENTE, _ATO),
    "RTDPJ_TITULO_ATENDIDO": (ESCREVENTE, _ATO),
    "RTDPJ_TITULO_PARADO": (ESCREVENTE, _ATO),
}

#: As regras de ESCREVENTE que o gestor hoje não transforma em tarefa
#: (`gestor_rotina.REGRAS_SEM_TAREFA`). A checklist as mostra à parte, «sem
#: tarefa». Proposta G007 ao titular: tirá-las de `REGRAS_SEM_TAREFA`. O teste
#: cobra que esta lista seja exatamente o cruzamento das duas.
SEM_TAREFA_A_DECIDIR = frozenset({
    "DIGITALIZACAO_DA_FICHA", "DIGITALIZACAO_ATRASADA",
    "CAIXA_DO_DIA_ABERTO", "CAIXA_ABERTO", "CAIXA_DIFERENCA",
    "NOTAS_PDF", "NOTAS_RASCUNHO",
    "PROTESTO_PAGAMENTO_SEM_LIVRO",
    "RCPN_DADOS_A_CONFERIR", "RCPN_DADO_COMPLEMENTAR", "RCPN_FOLHA_SEGURANCA",
    "RTDPJ_ENCERRAMENTO_DIARIO", "RTDPJ_LIVRO",
})


def destino(regra: str | None) -> str:
    """O destino de uma regra. A que a tabela não conhece fica na checklist."""
    return DESTINO.get(str(regra or "").upper(), (TI_ADMIN, ""))[0]


def motivo(regra: str | None) -> str:
    """Por que a regra vai para onde vai. Vazio para a regra não classificada."""
    return DESTINO.get(str(regra or "").upper(), (TI_ADMIN, ""))[1]


def tarefas_do_gestor(con) -> dict[str, list[dict]]:
    """As tarefas ABERTAS que o gestor mantém, por regra: {regra: [{id, setor}]}. SÓ LÊ.

    A referência da tarefa é `GESTOR:<regra>:<setor ou PESSOA:n>`
    (`gestor_rotina.sincronizar_tarefas`).
    """
    saida: dict[str, list[dict]] = {}
    for r in banco(con).ler(
            """SELECT id, source_ref FROM tasks
                WHERE source_type = 'GESTOR' AND status NOT IN ('CONCLUIDA', 'CANCELADA')
                ORDER BY id"""):
        partes = str(r["source_ref"] or "").split(":", 2)
        if len(partes) < 3 or partes[0] != "GESTOR":
            continue
        saida.setdefault(partes[1], []).append({"id": r["id"], "setor": partes[2]})
    return saida


def fora_da_checklist(achados: dict[str, list[dict]],
                      tarefas: dict[str, list[dict]] | None,
                      rotulos: dict[str, str] | None = None) -> dict[str, list[dict]]:
    """O que saiu da checklist, por destino e regra, com a tarefa que o leva. Só calcula.

    `achados` é o de `gestor_checklist.achados_por_area` (cada achado com
    `destino`). Devolve `{ESCREVENTE: [...], PROJETO: [...]}`, uma linha por
    regra e área: quantos, quantos fazem a cor, e as tarefas abertas da regra
    (`tarefas=None` quer dizer «não deu para ler as tarefas», e a linha diz
    isso em vez de «sem tarefa»).
    """
    rotulos = rotulos or {}
    linhas: dict[tuple[str, str, str], dict] = {}
    for area, lista in achados.items():
        for a in lista:
            d = a.get("destino") or destino(a["regra"])
            if d == TI_ADMIN:
                continue
            chave = (d, a["regra"], area)
            linha = linhas.setdefault(chave, {
                "regra": a["regra"], "area": area,
                "rotulo": rotulos.get(a["regra"], a["regra"]), "motivo": motivo(a["regra"]),
                "n": 0, "fazem_a_cor": 0,
                "tarefas": None if tarefas is None else tarefas.get(a["regra"], []),
                "sem_tarefa_a_decidir": a["regra"] in SEM_TAREFA_A_DECIDIR})
            linha["n"] += 1
            linha["fazem_a_cor"] += 1 if a.get("faz_a_cor") else 0
    saida: dict[str, list[dict]] = {ESCREVENTE: [], PROJETO: []}
    for (d, _, _), linha in sorted(linhas.items(), key=lambda kv: (kv[0][0], -kv[1]["n"],
                                                                     kv[0][1], kv[0][2])):
        saida[d].append(linha)
    return saida
