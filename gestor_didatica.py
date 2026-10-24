"""O TEXTO DIDÁTICO DAS TAREFAS DO GESTOR.

Pedido do oficial em 06/10/2026: «edite as tarefas com erros para corrigir para
ficar mais didatico. precisa ficar bem claro o que foi errado, como resolver e
onde acessar o ato com erro».

Até aqui a tarefa trazia `[CRITICO] ri_minutas 14: texto com campo de modelo não
preenchido` — o nome da TABELA e o número interno da linha, que ninguém no
balcão sabe abrir. Agora cada tarefa diz, nesta ordem:

    POR QUE ESTA TAREFA EXISTE — o que a regra confere, em português;
    COMO RESOLVER             — os passos, com a tela onde se faz;
    OS ITENS                  — cada ato com erro: qual é (como o balcão o
                                chama), o que está errado, quem praticou e
                                ONDE ABRIR (o caminho no menu e o endereço).

**O PASSO A PASSO É HONESTO SOBRE O QUE NÃO TEM TELA.** Dois casos (consulta ao
CNIB e prenotação de ato já lavrado) não têm tela que os grave depois; a
tarefa diz isso em vez de mandar procurar um botão que não existe.

SÓ ESCREVE TEXTO: quem cria e fecha a tarefa continua sendo `gestor_rotina`.
"""
from __future__ import annotations

import re

import gestor_erros as GER

#: «Onde abrir» de quem não tem ato próprio — a tela da obrigação.
#: (caminho no menu, endereço)
TELA = {
    "SIRC": ("Registro Civil → SIRC", "/rcpn/sirc"),
    "SIRC_CANCELAMENTO": ("Registro Civil → SIRC (cancelamentos)", "/rcpn/sirc"),
    "FUNAI": ("Registro Civil → FUNAI", "/rcpn/funai"),
    "CRC": ("Registro Civil → CRC", "/rcpn/crc"),
    "OBITO_MENSAL": ("Registro Civil → Comunicações", "/rcpn/comunicacoes"),
    "IBGE": ("Registro Civil → IBGE", "/rcpn/ibge"),
    "PLD_COAF": ("Administrativo → PLD/COAF", "/administrativo/pld"),
    "ENVIOS": ("Administrativo → Envios às Centrais", "/administrativo/gestor/envios"),
    "LEITURAS": ("Administrativo → Leitura dos textos (IA)", "/administrativo/gestor/leituras"),
    "CAIXA": ("Caixa", "/caixa"),
    "CAIXAS_VISTO": ("Administrativo → Caixas para o visto", "/administrativo/gestor/caixas"),
    "SELOS": ("Relatórios → Selos", "/relatorios/selos"),
    "CNIB": ("Registro de Imóveis → CNIB", "/registro-imoveis/cnib"),
}

FECHA_SOZINHA = ("Cada item sai desta lista sozinho na conferência seguinte (07:30, "
                 "14:00 e 14:30) quando o sistema vir que foi resolvido, e a tarefa "
                 "fecha quando a lista zerar — não é preciso concluí-la à mão. "
                 "Concluir à mão com item pendente faz a conferência reabri-la.")

#: regra → (por que existe, [passos])
GUIA: dict[str, tuple[str, list[str]]] = {
    "SIRC": (
        "Todo registro do Registro Civil — e também cada averbação, anotação e "
        "retificação — tem de ser comunicado ao SIRC (INSS) em 1 dia útil "
        "(art. 225 do Código de Normas). Os itens abaixo foram lavrados e não têm "
        "envio registrado.",
        ["Abra Registro Civil → SIRC e gere o arquivo do lote.",
         "Valide e envie (pelo botão Enviar ou pelo SIRC-Web).",
         "Registre o envio com o número do protocolo em Administrativo → Envios às "
         "Centrais. É o registro do envio que tira o item da lista."]),
    "SIRC_CANCELAMENTO": (
        "Termo cancelado também se comunica ao SIRC. Os itens abaixo foram "
        "cancelados e o cancelamento não foi comunicado.",
        ["Leia o detalhe de cada item: se disser RETIDO, NÃO envie — confira antes "
         "no SIRC-Web o que foi enviado (enviar cancelaria o registro que vale).",
         "Para os demais, abra Registro Civil → SIRC, gere o arquivo de "
         "cancelamento e envie.",
         "Registre o envio em Administrativo → Envios às Centrais."]),
    "FUNAI": (
        "Nascimento de criança indígena se comunica à FUNAI imediatamente "
        "(art. 253, § 2º).",
        ["Abra Registro Civil → FUNAI, gere o ofício do assento e envie.",
         "Registre o envio em Administrativo → Envios às Centrais."]),
    "CRC": (
        "Todo assento lavrado sobe à CRC Nacional em até 5 dias (arts. 243 e 367).",
        ["Abra Registro Civil → CRC, gere a carga e envie.",
         "Registre o envio em Administrativo → Envios às Centrais."]),
    "OBITO_MENSAL": (
        "Os óbitos do mês se comunicam até o 5º dia útil do mês seguinte a cada "
        "destino (Justiça Eleitoral, Receita, Instituto de Identificação, "
        "Ministério e Junta Militar). Mês sem óbito também se comunica, com "
        "declaração negativa.",
        ["Abra Registro Civil → Comunicações e abra a comunicação do mês para o "
         "destino de cada item.",
         "Envie pelo canal daquele destino (INFODIP para a Justiça Eleitoral).",
         "Registre o envio em Administrativo → Envios às Centrais."]),
    "IBGE": (
        "O mapa trimestral do IBGE vence no dia 8 do mês seguinte ao trimestre; "
        "atraso tem multa de 1 a 5 salários mínimos (art. 224).",
        ["Abra Registro Civil → IBGE, gere o mapa do trimestre e entregue.",
         "Registre a entrega na mesma tela."]),
    "CENSEC": (
        "Escrituras, procurações e atas da quinzena se informam à CENSEC "
        "(Provimento CNJ 18/2012).",
        ["Abra Notas → CENSEC, gere a remessa da quinzena e envie.",
         "Marque a remessa como enviada / registre em Envios às Centrais."]),
    "DOI": (
        "Todo mês deve uma DOI à Receita, ou a declaração negativa.",
        ["Abra a tela da DOI, gere o arquivo do mês e envie pelo programa da Receita.",
         "Registre o recibo da entrega."]),
    "ATO_SEM_SELO": (
        "Todo ato lavrado leva selo de fiscalização. Os atos abaixo estão sem selo.",
        ["Clique em «Onde abrir» do item: abre a ficha do ato.",
         "No ato, use «Selar este ato» (no RI, o botão fica na linha do ato).",
         "Se o ato for isento, marque a isenção COM o motivo — isento sem motivo "
         "continua na lista."]),
    "SELO_CANCELADO_LOCAL": (
        "O selo foi cancelado no sistema, mas o cancelamento no sistema não "
        "cancela no Tribunal: no Portal do Selo ele continua como usado.",
        ["Entre no Portal do Selo do TJMA e cancele o selo do item.",
         "Avise o administrador para anotar no razão «cancelado também no Portal "
         "do Selo» — é essa anotação que tira o item da lista."]),
    "SELO_ORFAO": (
        "O selo do ato não está no razão dos selos (foi digitado à mão sem "
        "conferência), ou o razão aponta para um ato que não existe.",
        ["Abra o ato pelo «Onde abrir» e confira o selo no Portal do Selo.",
         "Se o selo é desta serventia e deste ato, registre-o pelo campo de selo "
         "do próprio ato (ele confere e grava no razão).",
         "Se é selo de ato que não existe mais: cancele no Portal do Selo e "
         "avise o administrador."]),
    "PRENOTACAO_A_VENCER": (
        "A prenotação garante a prioridade do título e vence em 20 dias úteis "
        "(40 no REURB-S). Vencida, a prioridade se perde (art. 205 da Lei 6.015).",
        ["Abra Registro de Imóveis → Protocolo e procure a prenotação do item.",
         "Qualifique o título: registre, ou emita a nota devolutiva ANTES do prazo.",
         "Se houver motivo legal, suspenda o prazo com o motivo escrito."]),
    "PRENOTACAO_VENCIDA": (
        "A prenotação venceu e continua aberta.",
        ["Abra a prenotação em Registro de Imóveis → Protocolo.",
         "Registre, suspenda o prazo com motivo, ou cancele a prenotação."]),
    "DIGITALIZACAO_DA_FICHA": (
        "Depois de todo registro ou averbação, a ficha atualizada tem de ser "
        "digitalizada em até 7 dias corridos (ordem do oficial de 06/10/2026).",
        ["Imprima/pegue a ficha física com o ato novo e escaneie.",
         "Abra a matrícula pelo «Onde abrir» e anexe em «Digitalização oficial "
         "desta matrícula».",
         "Confira que a imagem nova mostra o último ato."]),
    "DIGITALIZACAO_ATRASADA": (
        "Aviso ao administrador: estas fichas passaram dos 7 dias sem a "
        "digitalização nova. A tarefa de quem digitaliza já está crítica.",
        ["Cobre de quem digitaliza (a tarefa dele/dela é a «Digitalizar a ficha "
         "depois do ato»).",
         "Esta sai sozinha quando a imagem for anexada."]),
    "REVISAO_DO_AGENTE": (
        "A revisão por IA dos atos já lavrados desde 10/09 apontou possível erro "
        "nestes atos. A IA aponta; quem decide é quem qualifica.",
        ["Abra o ato pelo «Onde abrir» e leia o trecho apontado.",
         "Se o apontamento procede: o ato lavrado não se edita — prepare a "
         "averbação de retificação (ou leve ao oficial).",
         "Se não procede (ou já foi corrigido): marque «Conferi» em Administrativo → "
         "Leitura dos textos (IA), com uma nota do que conferiu. Isso tira o item "
         "da lista."]),
    "LEITURA_DO_TEXTO": (
        "A leitura diária por IA apontou possível erro no texto. A IA aponta; "
        "quem decide é quem qualifica.",
        ["Abra o ato pelo «Onde abrir» e confira o trecho no título.",
         "Se é erro: corrija a minuta (ou, se já lavrado, retificação).",
         "Se não é: marque «Conferi» em Administrativo → Leitura dos textos (IA)."]),
    "MODELO_NAO_PREENCHIDO": (
        "O texto tem um campo do modelo que não foi trocado pelo dado — por exemplo "
        "«[INSERIR APÓS EMISSÃO]» ou «{{ rotulo }}». Lavrado assim, o marcador vai "
        "escrito no livro.",
        ["Abra pelo «Onde abrir» e procure no texto o marcador citado no item.",
         "Minuta: troque o marcador pelo dado real (do título/documento) e use "
         "«Guardar revisão».",
         "Ficha ou ato JÁ lavrado: não se edita — leve ao oficial para a averbação "
         "de retificação."]),
    "TEXTO_CONTRA_CADASTRO": (
        "O texto do ato não bate com o cadastro das partes: um nome, um documento "
        "ou o número da matrícula que está no cadastro não aparece no texto.",
        ["Abra pelo «Onde abrir» e compare o texto com o título apresentado.",
         "Se o erro está no CADASTRO (parte com nome/CPF errado), corrija a parte.",
         "Se está no TEXTO: minuta → corrija e guarde; ato lavrado → retificação."]),
    "MINUTA_EM_FICHA_ENCERRADA": (
        "A minuta está esperando revisão numa ficha que já foi encerrada — "
        "lavrá-la ali seria lavrar em ficha fechada.",
        ["Abra a matrícula pelo «Onde abrir».",
         "Se o ato já foi lavrado em outra ficha: descarte a minuta com o motivo.",
         "Se não foi: leve o texto para a ficha certa e descarte esta."]),
    "REGISTRO_SEM_CNIB": (
        # 06/10/2026, ordem do oficial: «já temos a base atualizada, só verificar se
        # tem ordem». A regra deixou de cobrar consulta anotada: agora só aparece
        # quando a base local do CNIB TEM ordem ativa contra parte do registro.
        "A base do CNIB tem ordem de indisponibilidade ATIVA contra uma parte deste "
        "registro já lavrado. Registrar sobre bem indisponível gera responsabilidade.",
        ["Abra a matrícula pelo «Onde abrir» e compare o documento da parte com o da "
         "ordem (o detalhe diz o protocolo, o juízo e o processo).",
         "Se bateu só pelo NOME, pode ser homônimo: confira o CPF da parte no título.",
         "Se for a mesma pessoa, leve ao oficial na hora — é ele quem decide a "
         "averbação e a comunicação ao juízo."]),
    "REGISTRO_SEM_PRENOTACAO": (
        "O registro (R) não está amarrado à prenotação de onde veio — sem ela, a "
        "prioridade do título não se prova (art. 186 da Lei 6.015).",
        ["Abra a matrícula e ache, em Registro de Imóveis → Protocolo, a "
         "prenotação do título deste registro.",
         "Escreva no histórico desta tarefa o número da prenotação. Para ato já "
         "lavrado NÃO há tela que faça a amarração depois: o item continua na "
         "lista até o administrador amarrá-la."]),
    "ATO_POR_FORA": (
        "O ato entrou no sistema sem passar pela tela de lavrar (sem registro de "
        "quem lavrou) — foi o caso da importação de minutas de 15/09. Ato assim "
        "pode estar sem selo e sem custas.",
        ["Abra o ato pelo «Onde abrir» e confira se tem selo e se foi cobrado.",
         "Se for acervo marcado errado, avise o administrador."]),
    "DOCUMENTO_INVALIDO": (
        "O CPF/CNPJ cadastrado não fecha o dígito verificador — está digitado "
        "errado, e vai errado às Centrais.",
        ["Abra pelo «Onde abrir» e confira o número no documento original.",
         "Corrija o documento no cadastro da parte."]),
    "CAIXA_ABERTO": (
        "Este caixa ficou aberto de um dia para o outro — mistura o dinheiro de "
        "dois dias no fechamento.",
        ["Abra o Caixa, conte o dinheiro e feche o caixa daquele dia.",
         "Se houver diferença, escreva a justificativa ao fechar."]),
    "CAIXA_DO_DIA_ABERTO": (
        "O expediente acabou e o seu caixa de hoje está aberto.",
        ["Abra o Caixa, conte o dinheiro e feche antes de sair."]),
    "CAIXA_COM_PONTOS": (
        "O agente refez a conta destes caixas fechados e achou ponto a explicar.",
        ["Abra Administrativo → Caixas para o visto e leia o ponto de cada caixa.",
         "Pergunte a quem contou; com a explicação, dê o visto no caixa."]),
    "CAIXA_PRONTO_PARA_VISTO": (
        "Estes caixas fecham (esperado, contado e lançamentos batem) e esperam o "
        "visto do oficial.",
        ["Abra Administrativo → Caixas para o visto e dê o visto em lote."]),
    "CAIXA_DIFERENCA": (
        "Caixa fechado com diferença e sem justificativa.",
        ["Abra o caixa e escreva a justificativa da diferença."]),
    "PLD_COAF": (
        "Caso selecionado pela prevenção à lavagem de dinheiro (CNN, arts. 151 a "
        "172) que espera análise ou comunicação, com prazo vencido ou perto de "
        "vencer. É sigiloso: os detalhes ficam só na tela do PLD/COAF.",
        ["Abra Administrativo → PLD/COAF e o caso pelo número.",
         "Analise com fundamentação e decida: comunicar no Siscoaf ou registrar a "
         "análise sem comunicação (art. 141, § 3º)."]),
    "FECHAMENTO_DO_MES": (
        "Os selos usados no mês não batem com as entradas do caixa no mês.",
        ["Compare em Relatórios → Selos e no Caixa do mês; explique a diferença "
         "(depósito em outro dia, ato gratuito, cobrança esquecida)."]),
    "BACKUP": (
        "O backup completo está atrasado.",
        ["Rode FERRAMENTAS/BACKUP_AGORA.cmd no servidor (ele também espelha fora)."]),
    "CNIB_PARADO": (
        "A base local do CNIB não é atualizada há dias: a conferência de ordem nos "
        "registros responde sobre base velha.",
        ["Rode a atualização do CNIB (TI) e, até lá, consulte direto na Central."]),
}


_TABELA_E_ID = re.compile(r"\(?\b(?:ri|nt|rc|rg|ra|pt|cx|sd)_[a-z_]+ \d+\)?:?\s*")
_ID_INTERNO = re.compile(r"\s*\((?:matrícula|matricula) id \d+\)")
_DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b")


def limpar(texto: str | None) -> str:
    """Tira do texto o que só o programa entende: «ri_minutas 14:», «(matrícula id
    5385)» — o número interno da linha, que ninguém no balcão sabe abrir — e põe a
    data como se lê (23/09/2026)."""
    t = _TABELA_E_ID.sub("", str(texto or ""))
    t = _ID_INTERNO.sub("", t)
    t = _DATA_ISO.sub(lambda m: f"{m.group(3)}/{m.group(2)}/{m.group(1)}", t)
    t = t.strip(" :")
    return t[:1].upper() + t[1:] if t else t


def _menu_do_ato(tabela: str, rotulo: str) -> str:
    if tabela in ("ri_atos", "ri_matriculas", "ri_minutas"):
        return f"Registro de Imóveis → {rotulo}"
    if tabela == "nt_atos":
        return f"Notas → {rotulo}"
    if tabela in ("rc_assentos", "rc_atos", "rc_pessoas"):
        return f"Registro Civil → {rotulo}"
    if tabela == "cx_caixas":
        return f"Caixa → {rotulo}"
    if tabela == "sd_selos":
        return f"Relatórios → Selos → {rotulo}"
    return rotulo


def _onde_da_regra(regra: str) -> tuple[str, str] | None:
    if regra in TELA:
        return TELA[regra]
    if regra in ("CAIXA_ABERTO", "CAIXA_DO_DIA_ABERTO", "CAIXA_DIFERENCA"):
        return TELA["CAIXA"]
    if regra in ("CAIXA_COM_PONTOS", "CAIXA_PRONTO_PARA_VISTO"):
        return TELA["CAIXAS_VISTO"]
    if regra in ("REVISAO_DO_AGENTE", "LEITURA_DO_TEXTO"):
        return TELA["LEITURAS"]
    if regra in ("SELO_CANCELADO_LOCAL", "FECHAMENTO_DO_MES"):
        return TELA["SELOS"]
    return None


def descricao(con, regra: str, itens: list[dict], gravidades: list[str]) -> str:
    """O texto da tarefa de uma regra. `itens` são os achados dela."""
    pessoas = GER._Pessoas(con)
    por_que, passos = GUIA.get(regra, (
        "A conferência diária achou os itens abaixo.",
        ["Abra cada item pelo «Onde abrir» e resolva o que o detalhe diz."]))
    linhas = ["POR QUE ESTA TAREFA EXISTE", por_que, "", "COMO RESOLVER"]
    linhas += [f"{i}. {p}" for i, p in enumerate(passos, 1)]
    linhas += [FECHA_SOZINHA, ""]
    tela = _onde_da_regra(regra)
    if tela:
        linhas += [f"Tela: {tela[0]} — {tela[1]}", ""]
    ordenados = sorted(itens, key=lambda x: (gravidades.index(x["gravidade"])
                                             if x["gravidade"] in gravidades else 9,
                                             x["prazo"] or "9999"))
    linhas.append(f"OS ITENS ({len(itens)})")
    for n, a in enumerate(ordenados, 1):
        alv = None
        try:
            alv = GER.alvo(con, a["chave"])
        except Exception:                               # noqa: BLE001
            alv = None
        rotulo, link, quem = None, None, None
        if alv:
            try:
                rotulo, link = GER.descrever(con, *alv)
                if regra in GER.CATEGORIAS:
                    q, como = GER.autor(con, pessoas, *alv)
                    quem = f"{q} — {como}" if como else q
            except Exception:                           # noqa: BLE001
                rotulo, link = None, None
        gravidade = {"CRITICO": "CRÍTICO", "ATENCAO": "ATENÇÃO"}.get(a["gravidade"], a["gravidade"])
        cabeca = f"{n}. [{gravidade}] " + (rotulo or limpar(a["titulo"]))
        linhas.append(cabeca)
        if rotulo:
            errado = limpar(a["titulo"])
            if errado.startswith(rotulo + ":"):
                errado = errado[len(rotulo) + 1:].strip()
                errado = errado[:1].upper() + errado[1:]
            linhas.append(f"   O que está errado: {errado}")
        if a.get("detalhe"):
            linhas.append(f"   Detalhe: {limpar(a['detalhe'])}")
        if a.get("prazo"):
            p = str(a["prazo"])[:10]
            linhas.append(f"   Prazo: {p[8:10]}/{p[5:7]}/{p[:4]}")
        if quem:
            linhas.append(f"   Quem praticou: {quem}")
        if link:
            linhas.append(f"   Onde abrir: {_menu_do_ato(alv[0], rotulo)} — {link}")
        elif tela:
            linhas.append(f"   Onde abrir: {tela[0]} — {tela[1]}")
    return "\n".join(linhas)
