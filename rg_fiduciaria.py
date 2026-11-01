"""A CONSOLIDAÇÃO DA PROPRIEDADE E A BUSCA E APREENSÃO EXTRAJUDICIAIS, no RTD.

    «termine o que ficou de fora»                       — o oficial, 01/11/2026

A NORMA
    Decreto-Lei 911/1969, arts. 8º-B e seguintes (Lei 14.711/2023); Código Nacional de
    Normas, arts. 397-A a 397-AM (Provimento CN 196/2025); CN-MA arts. 955 e 956.

ESTE MÓDULO É O CONTROLE DA SERVENTIA, E NÃO SUBSTITUI A CENTRAL. O art. 397-G dá ao módulo
da Central RTDPJ Brasil, com exclusividade, a gestão nacional do processo, e o art. 397-S
faz o requerimento entrar por ela. Não há contrato medido dessa parte da API, e por isso
nada aqui transmite: guarda-se o número que a Central deu.

O QUE ELE FAZ: autua com numeração própria (CN-MA art. 956, I), confere o requerimento,
conta os prazos, guarda a linha do tempo e monta as peças. Quem decide é o oficial, e quem
lavra a averbação do art. 397-M é a tela de sempre: aqui fica o texto sugerido e a amarração.
Linha do tempo não se apaga nem se edita.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Callable

import rg_titulo as TIT
from bd_nativo import banco


class FiduciariaError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


AUTUADO = "AUTUADO"
EMENDA = "EMENDA"
QUALIFICADO = "QUALIFICADO"
NOTIFICANDO = "NOTIFICANDO"
PRAZO_DEVEDOR = "PRAZO_DEVEDOR"
IMPUGNADO = "IMPUGNADO"
AGUARDA_ENTREGA = "AGUARDA_ENTREGA"
BUSCA = "BUSCA"
CONSOLIDADO = "CONSOLIDADO"
NAO_PROCESSADO = "NAO_PROCESSADO"
PAGO = "PAGO"
IMPUGNACAO_ACOLHIDA = "IMPUGNACAO_ACOLHIDA"
DESISTENCIA = "DESISTENCIA"
EXTINTO = "EXTINTO"
REVERTIDO = "REVERTIDO"
CONCLUIDO = "CONCLUIDO"

SITUACOES = {
    AUTUADO: "Autuado, aguarda qualificação",
    EMENDA: "Aguarda emenda do credor",
    QUALIFICADO: "Qualificado, aguarda a notificação",
    NOTIFICANDO: "Notificação enviada, aguarda a ciência",
    PRAZO_DEVEDOR: "Prazo do devedor correndo",
    IMPUGNADO: "Impugnação em análise",
    AGUARDA_ENTREGA: "Aguarda a entrega do bem",
    BUSCA: "Busca e apreensão em curso",
    CONSOLIDADO: "Propriedade consolidada, prazo de reversão",
    NAO_PROCESSADO: "Não processado",
    PAGO: "Encerrado pelo pagamento",
    IMPUGNACAO_ACOLHIDA: "Encerrado: impugnação acolhida",
    DESISTENCIA: "Encerrado: desistência do credor",
    EXTINTO: "Extinto por inércia do credor",
    REVERTIDO: "Consolidação revertida",
    CONCLUIDO: "Concluído",
}
TERMINAIS = (NAO_PROCESSADO, PAGO, IMPUGNACAO_ACOLHIDA, DESISTENCIA, EXTINTO, REVERTIDO, CONCLUIDO)

# O QUE O REQUERIMENTO TEM DE TRAZER. CN 397-E, V; 397-H; 397-K; 397-T. Facultativo não trava.
REQUISITOS: tuple[dict, ...] = tuple(
    {"chave": c, "artigo": a, "texto": t, "obrigatorio": o} for c, a, t, o in (
        ("competencia", "CN art. 397-K", "Esta serventia é a do domicílio do devedor ou da localização do bem na celebração do contrato.", True),
        ("clausula", "CN arts. 397-E, V, e 397-I", "O contrato ou o aditamento tem a cláusula expressa, destacada e específica da execução extrajudicial.", True),
        ("sem_acao", "CN art. 397-H, § 1º", "Não há ação judicial sobre a consolidação, ou a desistência foi homologada.", True),
        ("sem_incapaz", "CN art. 397-H, § 2º", "Não há interessado incapaz, menor de idade ou fundação.", True),
        ("legitimidade", "CN art. 397-J", "Quem requer é o credor fiduciário, o procurador ou o representante legal.", True),
        ("enderecos", "CN art. 397-T, I e § 1º", "O pedido traz os endereços do contrato, ou a prova da atualização feita pelo devedor.", True),
        ("contrato", "CN art. 397-T, II", "Cópia do contrato e do eventual aditamento.", True),
        ("mora", "CN art. 397-T, III e § 2º", "Comprovante da mora: carta com aviso de recebimento, protesto ou aviso registral.", True),
        ("planilha", "CN art. 397-T, IV", "Planilha com a evolução da dívida.", True),
        ("montante", "CN art. 397-T, V", "Montante atualizado, com projeção para pagamento em até 20 dias do protocolo.", True),
        ("instrucoes", "CN art. 397-T, VI", "Instruções para o pagamento.", True),
        ("credor", "CN art. 397-T, VII", "Dados do credor, com CPF ou CNPJ, contato e dados para transferência.", True),
        ("gravame", "CN art. 397-T, VIII", "Veículo: comprovação do gravame (facultativa).", False),
        ("entrega", "CN art. 397-T, IX", "Procedimento para a entrega voluntária do bem.", True),
        ("meio_credor", "CN art. 397-T, X", "Forma eletrônica de o credor receber as notificações.", True),
    ))

# As providências do art. 397-AH, que o art. 397-AJ manda cancelar depois da apreensão.
PROVIDENCIAS = {
    "RENAVAM": "Restrição no Renavam (397-AH, I: veículo, se houver acesso à base)",
    "ORGAOS": "Comunicação aos órgãos registrais (397-AH, II)",
    "CENTRAL": "Lançamento no módulo da Central (397-AH, III)",
    "CERTIDAO": "Certidão de busca e apreensão expedida (397-AH, IV)",
}
FORMAS_DE_NOTIFICAR = {"ELETRONICA": "Eletrônica", "POSTAL": "Postal, com AR", "PESSOAL": "Pessoal, pelo oficial ou preposto"}
RESULTADOS_DA_DILIGENCIA = {
    "POSITIVA": "Apreendido e entregue ao credor",
    "NEGATIVA": "Negativa: sem o bem, ou sem o credor no local",
    "TERCEIRO_RECUSOU": "Terceiro possuidor recusou a entrega",
}
PECAS = {
    "NOTIFICACAO": "Carta de notificação ao devedor (art. 397-V)",
    "CERTIDAO_BUSCA": "Certidão de busca e apreensão (art. 397-AH, IV)",
    "AUTO": "Auto de apreensão e de entrega da posse (art. 397-AI, § 3º)",
    "NEGATIVA": "Certidão de diligência negativa (art. 397-AI, § 4º)",
    "RECUSA": "Certidão circunstanciada: recusa do terceiro (art. 397-K, § 4º)",
    "CONSOLIDACAO": "Certidão de consolidação da propriedade (CN-MA art. 956, V)",
    "ENCERRAMENTO": "Certidão de encerramento do processo",
}

DIAS_DO_DEVEDOR = 20        # 397-V, II; 397-X; 397-AF: corridos
DIAS_DA_EMENDA = 10         # 397-U: corridos
DIAS_DO_CREDOR = 10         # 397-AA: corridos
UTEIS_DA_DECISAO = 5        # 397-AA
UTEIS_DA_LEITURA = 3        # 397-V, § 2º
UTEIS_DA_REVERSAO = 5       # 397-AK
MINIMO_DO_TEXTO = 10


def _dia_util_padrao(d: date) -> bool:
    from ri_schema import eh_dia_util
    return eh_dia_util(d, ())


def _dia(v: Any) -> date:
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError as erro:
        raise FiduciariaError("Informe a data no formato do calendário.") from erro


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _exigir_texto(v: Any, o_que: str) -> str:
    limpo = _texto(v)
    if len(limpo) < MINIMO_DO_TEXTO:
        raise FiduciariaError(f"Escreva {o_que} com pelo menos dez letras.")
    return limpo


def _centavos(v: Any) -> int | None:
    limpo = _texto(v).replace("R$", "").replace(" ", "")
    if not limpo:
        return None
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return int(round(float(limpo) * 100))
    except ValueError as erro:
        raise FiduciariaError(f"«{v}» não é um valor em reais.") from erro


def reais(centavos: Any) -> str:
    if centavos is None:
        return ""
    inteiro = f"{int(centavos) // 100:,}".replace(",", ".")
    return f"R$ {inteiro},{int(centavos) % 100:02d}"


def primeiro_util_depois(d: date, e_util: Callable[[date], bool] = _dia_util_padrao) -> date:
    d += timedelta(days=1)
    while not e_util(d):
        d += timedelta(days=1)
    return d


def somar_uteis(d: date, n: int, e_util: Callable[[date], bool] = _dia_util_padrao) -> date:
    for _ in range(n):
        d = primeiro_util_depois(d, e_util)
    return d


def fim_dos_corridos(ciencia: date, dias: int, e_util: Callable[[date], bool] = _dia_util_padrao) -> date:
    """Prazo em dias corridos, «contados a partir do primeiro dia útil posterior».

    O primeiro dia útil depois da ciência é o dia 1 do prazo. A tela mostra as duas datas.
    """
    return primeiro_util_depois(ciencia, e_util) + timedelta(days=dias - 1)


# ------------------------------------------------------------------ leitura


def um(con, proc_id: int) -> dict | None:
    linha = banco(con).um(
        """SELECT p.*, t.numero AS protocolo, t.data_apresentacao, r.numero AS registro_numero
             FROM rg_fiduciarias p JOIN rg_titulos t ON t.id = p.titulo_id
             LEFT JOIN rg_registros r ON r.id = p.registro_id
            WHERE p.id = %s""", (int(proc_id),))
    if not linha:
        return None
    p = dict(linha)
    p["rotulo"] = f"{p['numero']}/{p['ano']}"
    p["requisitos_ok"] = set(json.loads(p["requisitos"] or "[]"))
    return p


def eventos_de(con, proc_id: int) -> list[dict]:
    return [dict(x) for x in banco(con).ler(
        "SELECT * FROM rg_fiduciaria_eventos WHERE fiduciaria_id=%s ORDER BY id", (int(proc_id),))]


def fila(con, *, hoje: str, abertos: bool = True) -> list[dict]:
    """Os processos, com o prazo vencido primeiro e o mais próximo em seguida. Só LÊ."""
    linhas = []
    for r in banco(con).ler(
            """SELECT p.*, t.numero AS protocolo FROM rg_fiduciarias p
                 JOIN rg_titulos t ON t.id = p.titulo_id ORDER BY p.id DESC"""):
        p = dict(r)
        if abertos == (p["situacao"] in TERMINAIS):
            continue
        p["rotulo"] = f"{p['numero']}/{p['ano']}"
        p["situacao_rotulo"] = SITUACOES.get(p["situacao"], p["situacao"])
        p["vencido"] = bool(p["prazo_ate"] and p["prazo_ate"] < hoje)
        linhas.append(p)
    return sorted(linhas, key=lambda x: (not x["vencido"], x["prazo_ate"] or "9999", -int(x["id"])))


def do_titulo(con, titulo_id: int) -> dict | None:
    linha = banco(con).um("SELECT id FROM rg_fiduciarias WHERE titulo_id=%s ORDER BY id DESC LIMIT 1",
                          (int(titulo_id),))
    return um(con, int(linha["id"])) if linha else None


def titulos_para_autuar(con) -> list[dict]:
    """Títulos do RTD em aberto, sem processo. Só LÊ."""
    return [dict(x) for x in banco(con).ler(
        """SELECT t.id, t.numero, t.apresentante, t.natureza FROM rg_titulos t
            WHERE t.atribuicao = %s AND t.situacao NOT IN ('REGISTRADO','DEVOLVIDO','CANCELADO')
              AND NOT EXISTS (SELECT 1 FROM rg_fiduciarias p WHERE p.titulo_id = t.id)
            ORDER BY t.id DESC""", (TIT.RTD,))]


def acoes_possiveis(p: dict, *, hoje: str) -> set[str]:
    """O que a tela oferece agora: a mesma régua que as funções cobram. Só calcula."""
    s = p["situacao"]
    if s in TERMINAIS:
        return set()
    vencido = bool(p.get("prazo_ate") and p["prazo_ate"] < hoje)
    a: set[str] = set()
    if s in (AUTUADO, EMENDA):
        a.add("qualificar")
    if s in (QUALIFICADO, NOTIFICANDO):
        a.add("notificar")
    if s == NOTIFICANDO:
        a.add("ciencia")
    if s in (PRAZO_DEVEDOR, IMPUGNADO, AGUARDA_ENTREGA, BUSCA):
        a.add("pagamento")
    if s == PRAZO_DEVEDOR:
        a.add("impugnar")
    if s == IMPUGNADO:
        a.add("decidir" if p.get("impugnacao_conhecida") else "conhecer")
    if s in (PRAZO_DEVEDOR, AGUARDA_ENTREGA, BUSCA):
        a.add("entrega")
    if s in (PRAZO_DEVEDOR, AGUARDA_ENTREGA) and vencido:
        a.add("requerer_busca")
    if s == BUSCA:
        a |= {"providencia", "diligencia"}
    if s == CONSOLIDADO:
        a |= {"reverter", "cancelar_providencias"}
        if vencido:
            a.add("concluir")
    if s != CONSOLIDADO:
        a |= {"desistir", "extinguir"}
    return a


def pecas_disponiveis(p: dict, eventos: list[dict]) -> dict[str, str]:
    tipos = {e["tipo"] for e in eventos}
    saida = {}
    if "QUALIFICADO" in tipos:
        saida["NOTIFICACAO"] = PECAS["NOTIFICACAO"]
    if "BUSCA_REQUERIDA" in tipos:
        saida["CERTIDAO_BUSCA"] = PECAS["CERTIDAO_BUSCA"]
    if "DILIGENCIA_POSITIVA" in tipos:
        saida["AUTO"] = PECAS["AUTO"]
    if "DILIGENCIA_NEGATIVA" in tipos:
        saida["NEGATIVA"] = PECAS["NEGATIVA"]
    if "DILIGENCIA_TERCEIRO_RECUSOU" in tipos:
        saida["RECUSA"] = PECAS["RECUSA"]
    if p["situacao"] in (CONSOLIDADO, CONCLUIDO):
        saida["CONSOLIDACAO"] = PECAS["CONSOLIDACAO"]
    if p["situacao"] in TERMINAIS:
        saida["ENCERRAMENTO"] = PECAS["ENCERRAMENTO"]
    return saida


def averbacoes_pendentes(p: dict, eventos: list[dict]) -> list[dict]:
    """Os atos que o art. 397-M manda averbar, e ainda sem o ato amarrado. Só LÊ."""
    return [e for e in eventos if e["averbar"] and not e["ato_id"]]


# ------------------------------------------------------------------- escrita


def _evento(con, pid: int, tipo: str, dia: Any, texto: str, *, prazo: Any = None, averbar: bool = False,
            agora: str, usuario: str | None) -> None:
    banco(con).escrever(
        """INSERT INTO rg_fiduciaria_eventos(fiduciaria_id, tipo, dia, texto, prazo_ate, averbar,
               criado_em, criado_por) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (int(pid), tipo, str(dia)[:10], texto, str(prazo)[:10] if prazo else None,
         1 if averbar else 0, agora, usuario))


def _mudar(con, pid: int, situacao: str, prazo: Any = None, rotulo: str | None = None) -> None:
    banco(con).escrever(
        "UPDATE rg_fiduciarias SET situacao=%s, prazo_ate=%s, prazo_rotulo=%s WHERE id=%s",
        (situacao, str(prazo)[:10] if prazo else None, rotulo, int(pid)))


def _proc(con, pid: int, *permitidas: str) -> dict:
    p = um(con, pid)
    if not p:
        raise FiduciariaError(f"Processo {pid} não encontrado.")
    if p["situacao"] in TERMINAIS:
        raise FiduciariaError("Este processo já se encerrou, e não recebe mais lançamento.")
    if permitidas and p["situacao"] not in permitidas:
        raise FiduciariaError(
            f"Isso não cabe agora: o processo está em «{SITUACOES[p['situacao']]}».")
    return p


def autuar(con, *, titulo_id: int, credor_nome: str, devedor_nome: str, ano: int, agora: str,
           credor_documento: str = "", credor_contato: str = "", devedor_documento: str = "",
           devedor_email: str = "", devedor_endereco: str = "", contrato: str = "",
           bem_descricao: str = "", bem_identificacao: str = "", valor_divida: Any = None,
           registro_numero: Any = None, protocolo_central: str = "", usuario: str | None = None) -> dict:
    """Autua o requerimento com numeração própria. ESCREVE. CN-MA art. 956, I; CN art. 397-S, § 2º.

    O protocolo é o do título, e tem os efeitos da prenotação (art. 397-R, parágrafo único).
    O contrato não precisa estar registrado (art. 397-L): sem ele, é a carta que se registra.
    """
    bd = banco(con)
    titulo = TIT.um(con, int(titulo_id))
    if not titulo:
        raise FiduciariaError("Escolha o título protocolado: é ele que dá a prioridade do processo.")
    if int(titulo["atribuicao"]) != TIT.RTD:
        raise FiduciariaError("Este processo é do Registro de Títulos e Documentos.")
    if bd.um("SELECT id FROM rg_fiduciarias WHERE titulo_id=%s", (int(titulo_id),)):
        raise FiduciariaError("Este título já tem processo autuado.")
    if not _texto(credor_nome) or not _texto(devedor_nome):
        raise FiduciariaError("Informe o credor e o devedor.")
    if not _texto(bem_descricao):
        raise FiduciariaError("Descreva o bem dado em garantia.")
    registro_id = None
    if _texto(registro_numero):
        achados = bd.ler(
            "SELECT id FROM rg_registros WHERE atribuicao=%s AND numero=%s ORDER BY id",
            (TIT.RTD, int(_texto(registro_numero)) if _texto(registro_numero).isdigit() else -1))
        if len(achados) != 1:
            raise FiduciariaError(
                f"Não achei um registro só do RTD com o n. {registro_numero}. Confira o número, ou "
                "deixe em branco se o contrato não está registrado aqui.")
        registro_id = int(achados[0]["id"])
    bd.travar("rg_fiduciarias.numero")
    numero = int(bd.valor("SELECT COALESCE(MAX(numero),0) n FROM rg_fiduciarias WHERE ano=%s", (int(ano),))) + 1
    linha = bd.escrever(
        """INSERT INTO rg_fiduciarias(numero, ano, titulo_id, registro_id, situacao, credor_nome,
               credor_documento, credor_contato, devedor_nome, devedor_documento, devedor_email,
               devedor_endereco, contrato, bem_descricao, bem_identificacao, valor_centavos,
               protocolo_central, requisitos, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (numero, int(ano), int(titulo_id), registro_id, AUTUADO, _texto(credor_nome), _texto(credor_documento),
         _texto(credor_contato), _texto(devedor_nome), _texto(devedor_documento), _texto(devedor_email),
         _texto(devedor_endereco), _texto(contrato), _texto(bem_descricao), _texto(bem_identificacao),
         _centavos(valor_divida), _texto(protocolo_central), "[]", agora, usuario))
    pid = int(linha[0]["id"])
    _evento(con, pid, "AUTUADO", agora, f"Requerimento autuado sob o n. {numero}/{ano}.", agora=agora, usuario=usuario)
    return {"id": pid, "rotulo": f"{numero}/{ano}"}


def qualificar(con, pid: int, *, resultado: str, itens: Any = (), motivo: str = "", dia: str, agora: str,
               usuario: str | None = None) -> dict:
    """A qualificação do pedido: POSITIVA, EMENDA ou NEGATIVA. ESCREVE. CN-MA art. 956, I; CN art. 397-U."""
    _proc(con, pid, AUTUADO, EMENDA)
    marcados = {i for i in itens if i in {r["chave"] for r in REQUISITOS}}
    banco(con).escrever("UPDATE rg_fiduciarias SET requisitos=%s WHERE id=%s",
                        (json.dumps(sorted(marcados)), int(pid)))
    if resultado == "POSITIVA":
        faltam = [r for r in REQUISITOS if r["obrigatorio"] and r["chave"] not in marcados]
        if faltam:
            raise FiduciariaError(
                "Faltam itens para a qualificação positiva: "
                + "; ".join(r["artigo"] for r in faltam) + ". Se faltam mesmo, peça a emenda.")
        _mudar(con, pid, QUALIFICADO)
        _evento(con, pid, "QUALIFICADO", dia, "Qualificação positiva: requerimento em ordem.", agora=agora, usuario=usuario)
    elif resultado == "EMENDA":
        razao = _exigir_texto(motivo, "o que o credor precisa emendar")
        ate = _dia(dia) + timedelta(days=DIAS_DA_EMENDA)
        _mudar(con, pid, EMENDA, ate, "Emenda do credor (397-U)")
        _evento(con, pid, "EMENDA", dia, f"Emenda em {DIAS_DA_EMENDA} dias corridos: {razao}", prazo=ate, agora=agora, usuario=usuario)
    elif resultado == "NEGATIVA":
        razao = _exigir_texto(motivo, "o fundamento")
        _mudar(con, pid, NAO_PROCESSADO)
        _evento(con, pid, "NAO_PROCESSADO", dia, f"Qualificação negativa: {razao}", agora=agora, usuario=usuario)
    else:
        raise FiduciariaError("Escolha o resultado da qualificação.")
    return {"id": pid, "resultado": resultado}


def notificar(con, pid: int, *, forma: str, dia: str, agora: str, usuario: str | None = None,
              e_util: Callable = _dia_util_padrao) -> dict:
    """Registra a notificação enviada. ESCREVE. CN art. 397-V. Sem leitura em 3 dias úteis, vai pelo correio."""
    p = _proc(con, pid, QUALIFICADO, NOTIFICANDO)
    if forma not in FORMAS_DE_NOTIFICAR:
        raise FiduciariaError("Escolha a forma da notificação.")
    prazo, rotulo = None, None
    if forma == "ELETRONICA":
        prazo, rotulo = somar_uteis(_dia(dia), UTEIS_DA_LEITURA, e_util), "Leitura; depois, via postal (397-V, § 2º)"
    primeira = p["situacao"] == QUALIFICADO
    _mudar(con, pid, NOTIFICANDO, prazo, rotulo)
    _evento(con, pid, "NOTIFICACAO", dia, f"Notificação enviada: {FORMAS_DE_NOTIFICAR[forma]}.", prazo=prazo,
            averbar=primeira, agora=agora, usuario=usuario)
    return {"id": pid, "prazo_ate": str(prazo) if prazo else None}


def ciencia(con, pid: int, *, dia: str, agora: str, usuario: str | None = None,
            e_util: Callable = _dia_util_padrao) -> dict:
    """A leitura comprovada ou o AR de volta: começa o prazo do devedor. ESCREVE. CN art. 397-V, II e § 1º."""
    _proc(con, pid, NOTIFICANDO)
    ate = fim_dos_corridos(_dia(dia), DIAS_DO_DEVEDOR, e_util)
    _mudar(con, pid, PRAZO_DEVEDOR, ate, "Pagar, impugnar ou entregar o bem (397-V)")
    _evento(con, pid, "CIENCIA", dia,
            f"Ciência comprovada. {DIAS_DO_DEVEDOR} dias corridos, de "
            f"{primeiro_util_depois(_dia(dia), e_util).strftime('%d/%m/%Y')} a {ate.strftime('%d/%m/%Y')}.",
            prazo=ate, agora=agora, usuario=usuario)
    return {"id": pid, "prazo_ate": str(ate)}


def pagamento(con, pid: int, *, dia: str, valor: Any = None, integral: bool = False, credor_aceitou: bool = False,
              ao_oficial: bool = False, agora: str, usuario: str | None = None,
              e_util: Callable = _dia_util_padrao) -> dict:
    """O pagamento voluntário. ESCREVE. CN art. 397-W. Parcial só encerra com a concordância do credor."""
    _proc(con, pid, PRAZO_DEVEDOR, IMPUGNADO, AGUARDA_ENTREGA, BUSCA)
    cents = _centavos(valor)
    repasse = somar_uteis(_dia(dia), 2, e_util) if ao_oficial else None
    texto = "Pagamento " + ("integral" if integral else "parcial") + (f" de {reais(cents)}" if cents else "")
    if ao_oficial:
        texto += f". Recebido pela serventia: repassar ao credor até {repasse.strftime('%d/%m/%Y')} (397-W, § 5º)"
    if integral or credor_aceitou:
        _mudar(con, pid, PAGO)
        _evento(con, pid, "PAGO", dia, texto + ". Processo encerrado, contrato convalescido, sem emolumentos.",
                prazo=repasse, averbar=True, agora=agora, usuario=usuario)
        return {"id": pid, "encerrou": True}
    _evento(con, pid, "PAGAMENTO_PARCIAL", dia, texto + ". O processo continua pelo saldo.", prazo=repasse, agora=agora, usuario=usuario)
    return {"id": pid, "encerrou": False}


def impugnar(con, pid: int, *, dia: str, texto: str, valor: Any = None, agora: str, usuario: str | None = None) -> dict:
    """Recebe a impugnação. ESCREVE. CN arts. 397-X e 397-Y."""
    _proc(con, pid, PRAZO_DEVEDOR)
    alegado = _exigir_texto(texto, "o que o devedor alegou")
    cents = _centavos(valor)
    _mudar(con, pid, IMPUGNADO)
    banco(con).escrever("UPDATE rg_fiduciarias SET impugnacao_conhecida=0 WHERE id=%s", (int(pid),))
    _evento(con, pid, "IMPUGNACAO", dia,
            f"Impugnação recebida: {alegado}" + (f" Valor que entende devido e pagou: {reais(cents)}." if cents else ""),
            agora=agora, usuario=usuario)
    return {"id": pid}


def _segue_para_entrega(con, pid: int, dia: str, texto: str, tipo: str, agora: str, usuario: str | None) -> None:
    ate = _dia(dia) + timedelta(days=DIAS_DO_DEVEDOR)
    _mudar(con, pid, AGUARDA_ENTREGA, ate, "Entregar ou disponibilizar o bem (397-AF)")
    _evento(con, pid, tipo, dia, texto + f" Entrega do bem até {ate.strftime('%d/%m/%Y')} (397-AF).", prazo=ate, agora=agora, usuario=usuario)


def conhecer(con, pid: int, *, conhece: bool, fundamento: str, dia: str, agora: str, usuario: str | None = None,
             e_util: Callable = _dia_util_padrao) -> dict:
    """Conhece ou não a impugnação. ESCREVE. CN arts. 397-Z e 397-AA."""
    _proc(con, pid, IMPUGNADO)
    razao = _exigir_texto(fundamento, "o fundamento")
    if not conhece:
        _segue_para_entrega(con, pid, dia, f"Impugnação não conhecida: {razao}. Informada a via judicial.",
                            "IMPUGNACAO_NAO_CONHECIDA", agora, usuario)
        return {"id": pid}
    ate = fim_dos_corridos(_dia(dia), DIAS_DO_CREDOR, e_util)
    banco(con).escrever("UPDATE rg_fiduciarias SET impugnacao_conhecida=1 WHERE id=%s", (int(pid),))
    _mudar(con, pid, IMPUGNADO, ate, "Manifestação do credor (397-AA)")
    _evento(con, pid, "IMPUGNACAO_CONHECIDA", dia,
            f"Impugnação conhecida: {razao}. Credor notificado; depois do prazo, decisão em {UTEIS_DA_DECISAO} dias úteis.",
            prazo=ate, agora=agora, usuario=usuario)
    return {"id": pid}


def decidir(con, pid: int, *, procedente: bool, fundamento: str, dia: str, agora: str, usuario: str | None = None) -> dict:
    """Decide a impugnação, e isso esgota a instância administrativa. ESCREVE. CN arts. 397-AB a 397-AE."""
    p = _proc(con, pid, IMPUGNADO)
    if not p["impugnacao_conhecida"]:
        raise FiduciariaError("Antes de decidir, diga se a impugnação é conhecida.")
    razao = _exigir_texto(fundamento, "o fundamento")
    if procedente:
        _mudar(con, pid, IMPUGNACAO_ACOLHIDA)
        _evento(con, pid, "IMPUGNACAO_ACOLHIDA", dia, f"Impugnação acolhida: {razao}. Contrato convalescido.",
                averbar=True, agora=agora, usuario=usuario)
    else:
        _segue_para_entrega(con, pid, dia, f"Impugnação indeferida: {razao}.", "IMPUGNACAO_INDEFERIDA", agora, usuario)
    return {"id": pid}


def _consolidar(con, pid: int, dia: str, e_util: Callable) -> date:
    ate = somar_uteis(_dia(dia), UTEIS_DA_REVERSAO, e_util)
    _mudar(con, pid, CONSOLIDADO, ate, "Reversão pelo devedor (397-AK)")
    return ate


def entrega(con, pid: int, *, dia: str, detalhe: str = "", agora: str, usuario: str | None = None,
            e_util: Callable = _dia_util_padrao) -> dict:
    """A entrega voluntária, com o termo firmado pelo credor. ESCREVE. CN arts. 397-V, III, b, e 397-AF."""
    _proc(con, pid, PRAZO_DEVEDOR, AGUARDA_ENTREGA, BUSCA)
    ate = _consolidar(con, pid, dia, e_util)
    _evento(con, pid, "ENTREGA", dia, f"Bem entregue pelo devedor, com termo do credor. {_texto(detalhe)}".strip(),
            prazo=ate, averbar=True, agora=agora, usuario=usuario)
    return {"id": pid, "prazo_ate": str(ate)}


def requerer_busca(con, pid: int, *, dia: str, valor: Any, tem_planilha: bool, hoje: str, agora: str,
                   usuario: str | None = None) -> dict:
    """O requerimento de busca e apreensão, só depois do prazo. ESCREVE. CN art. 397-AG."""
    p = _proc(con, pid, PRAZO_DEVEDOR, AGUARDA_ENTREGA)
    if not p["prazo_ate"] or p["prazo_ate"] >= hoje:
        raise FiduciariaError(
            f"O prazo do devedor vai até {p['prazo_ate'] or 'data não lançada'}: "
            "a busca e apreensão só cabe depois dele (art. 397-AG).")
    cents = _centavos(valor)
    if not cents or not tem_planilha:
        raise FiduciariaError("O requerimento precisa do valor total da dívida e da planilha (art. 397-AG, parágrafo único).")
    _mudar(con, pid, BUSCA)
    _evento(con, pid, "BUSCA_REQUERIDA", dia, f"Busca e apreensão requerida. Dívida: {reais(cents)}.",
            averbar=True, agora=agora, usuario=usuario)
    return {"id": pid}


def providencia(con, pid: int, *, qual: str, dia: str, agora: str, usuario: str | None = None) -> dict:
    """Marca uma providência do art. 397-AH. ESCREVE. A máquina não lança no Renavam nem na Central."""
    _proc(con, pid, BUSCA)
    if qual not in PROVIDENCIAS:
        raise FiduciariaError("Escolha a providência.")
    _evento(con, pid, f"PROVIDENCIA_{qual}", dia, PROVIDENCIAS[qual], agora=agora, usuario=usuario)
    return {"id": pid}


def diligencia(con, pid: int, *, dia: str, hora: str = "", local: str, resultado: str, detalhe: str = "",
               agora: str, usuario: str | None = None, e_util: Callable = _dia_util_padrao) -> dict:
    """O resultado da diligência. ESCREVE. CN arts. 397-AI, 397-AJ e 397-K, §§ 3º a 5º."""
    _proc(con, pid, BUSCA)
    if resultado not in RESULTADOS_DA_DILIGENCIA:
        raise FiduciariaError("Escolha o resultado da diligência.")
    if not _texto(local):
        raise FiduciariaError("Informe o local da diligência.")
    texto = f"{RESULTADOS_DA_DILIGENCIA[resultado]}. Local: {_texto(local)}"
    texto += f", às {_texto(hora)}." if _texto(hora) else "."
    if resultado != "POSITIVA":
        texto += " " + _exigir_texto(detalhe, "as razões")
        _evento(con, pid, f"DILIGENCIA_{resultado}", dia, texto, agora=agora, usuario=usuario)
        return {"id": pid, "apreendido": False}
    ate = _consolidar(con, pid, dia, e_util)
    _evento(con, pid, "DILIGENCIA_POSITIVA", dia, f"{texto} {_texto(detalhe)}".strip() + " Propriedade consolidada.",
            prazo=ate, averbar=True, agora=agora, usuario=usuario)
    return {"id": pid, "apreendido": True, "prazo_ate": str(ate)}


def cancelar_providencias(con, pid: int, *, dia: str, agora: str, usuario: str | None = None) -> dict:
    """Marca o cancelamento dos lançamentos do art. 397-AH. ESCREVE. CN art. 397-AJ."""
    _proc(con, pid, CONSOLIDADO)
    _evento(con, pid, "PROVIDENCIAS_CANCELADAS", dia,
            "Cancelados os lançamentos e as comunicações do art. 397-AH.", agora=agora, usuario=usuario)
    return {"id": pid}


def reverter(con, pid: int, *, dia: str, detalhe: str = "", agora: str, usuario: str | None = None) -> dict:
    """O devedor pagou no prazo, e a posse volta. ESCREVE. CN art. 397-AK."""
    _proc(con, pid, CONSOLIDADO)
    _mudar(con, pid, REVERTIDO)
    _evento(con, pid, "REVERTIDO", dia, f"Consolidação revertida pelo pagamento integral. {_texto(detalhe)}".strip(),
            averbar=True, agora=agora, usuario=usuario)
    return {"id": pid}


def concluir(con, pid: int, *, dia: str, valor_venda: Any = None, detalhe: str = "", hoje: str, agora: str,
             usuario: str | None = None) -> dict:
    """A conclusão, passado o prazo de reversão. ESCREVE. CN arts. 397-AL e 397-AM, § 1º."""
    p = _proc(con, pid, CONSOLIDADO)
    if p["prazo_ate"] and p["prazo_ate"] >= hoje:
        raise FiduciariaError(f"O prazo de reversão vai até {p['prazo_ate']}: conclua depois dele.")
    cents = _centavos(valor_venda)
    texto = "Processo concluído, com baixa da indisponibilidade e da restrição."
    if cents:
        texto += f" Valor da venda informado pelo credor: {reais(cents)}."
    _mudar(con, pid, CONCLUIDO)
    _evento(con, pid, "CONCLUIDO", dia, f"{texto} {_texto(detalhe)}".strip(), averbar=True, agora=agora, usuario=usuario)
    return {"id": pid}


def desistir(con, pid: int, *, motivo: str, dia: str, agora: str, usuario: str | None = None,
             e_util: Callable = _dia_util_padrao) -> dict:
    """A desistência do credor, a qualquer tempo. ESCREVE. CN art. 397-O."""
    _proc(con, pid)
    razao = _exigir_texto(motivo, "o pedido do credor")
    ate = somar_uteis(_dia(dia), 5, e_util)
    _mudar(con, pid, DESISTENCIA)
    _evento(con, pid, "DESISTENCIA", dia, f"Desistência do credor: {razao}. Excluir da Central e comunicar até "
            f"{ate.strftime('%d/%m/%Y')}. Sem emolumentos.", prazo=ate, averbar=True, agora=agora, usuario=usuario)
    return {"id": pid}


def extinguir(con, pid: int, *, motivo: str, dia: str, agora: str, usuario: str | None = None) -> dict:
    """A extinção por inércia do credor, depois do prazo fixado. ESCREVE. CN art. 397-Q."""
    _proc(con, pid)
    razao = _exigir_texto(motivo, "qual ato o credor deixou de praticar, e o prazo que tinha")
    _mudar(con, pid, EXTINTO)
    _evento(con, pid, "EXTINTO", dia, f"Extinto por inércia do credor: {razao}. Sem emolumentos.",
            averbar=True, agora=agora, usuario=usuario)
    return {"id": pid}


def amarrar_averbacao(con, pid: int, evento_id: int, *, ato_id: int) -> dict:
    """Diz qual ato lançado cumpriu a averbação pedida. ESCREVE. CN art. 397-M."""
    bd = banco(con)
    p = um(con, pid)
    if not p:
        raise FiduciariaError(f"Processo {pid} não encontrado.")
    ato = bd.um("SELECT id, registro_id FROM rg_atos WHERE id=%s", (int(ato_id),))
    if not ato:
        raise FiduciariaError("Escolha um ato lançado.")
    titulo = TIT.um(con, int(p["titulo_id"])) or {}
    if int(ato["registro_id"]) not in {x for x in (p["registro_id"], titulo.get("registro_id")) if x}:
        raise FiduciariaError("Este ato é de outro registro.")
    feitos = bd.escrever(
        "UPDATE rg_fiduciaria_eventos SET ato_id=%s WHERE id=%s AND fiduciaria_id=%s RETURNING id",
        (int(ato_id), int(evento_id), int(pid)))
    if not feitos:
        raise FiduciariaError("Este lançamento não é deste processo.")
    return {"id": pid}


# ------------------------------------------------------------------- a tela


def fases(p: dict, *, pode_decidir: bool, eventos: list[dict]) -> dict:
    """A régua da ficha, na forma de `rg_titulo_fases`. Só calcula."""
    s = p["situacao"]
    ordem = {AUTUADO: 1, EMENDA: 1, QUALIFICADO: 2, NOTIFICANDO: 2, PRAZO_DEVEDOR: 3, IMPUGNADO: 3,
             AGUARDA_ENTREGA: 3, BUSCA: 4, CONSOLIDADO: 5, CONCLUIDO: 6, REVERTIDO: 6}
    tipos = {e["tipo"] for e in eventos}
    onde = ordem.get(s, 1)
    if s in TERMINAIS and s not in (CONCLUIDO, REVERTIDO):
        onde = max((n for t, n in (("QUALIFICADO", 2), ("CIENCIA", 3), ("BUSCA_REQUERIDA", 4)) if t in tipos), default=1)

    def fase(chave, rotulo, n):
        estado = "feita" if (n < onde or onde == 6) else "liberada" if n == onde else "travada"
        trava = None
        if estado == "travada":
            trava = {"titulo": f"Ainda não chegou em {rotulo.lower()}",
                     "texto": "O rito tem ordem, e cada passo depende do anterior.",
                     "ir": ("autuacao", "notificacao", "defesa", "busca", "consolidacao")[max(onde, 1) - 1],
                     "ir_rotulo": "Passo atual"}
        pend = 1 if (estado == "liberada" and s not in TERMINAIS and (pode_decidir or n > 1)) else 0
        return {"chave": chave, "rotulo": rotulo, "numero": n, "estado": estado, "pendencias": pend,
                "aviso": SITUACOES[s] if estado == "liberada" else "", "trava": trava}

    lista = [fase("autuacao", "Autuação", 1), fase("notificacao", "Notificação", 2),
             fase("defesa", "Pagamento e impugnação", 3), fase("busca", "Busca e apreensão", 4),
             fase("consolidacao", "Consolidação", 5)]
    for i, x in enumerate(lista):
        x["voltar"] = {k: lista[i - 1][k] for k in ("chave", "rotulo")} if i else None
        x["avancar"] = {k: lista[i + 1][k] for k in ("chave", "rotulo")} if i < len(lista) - 1 else None
    inicial = lista[min(onde, 5) - 1]["chave"]
    return {"fases": lista, "foco": inicial, "inicial": inicial,
            "apoio": [{"chave": "pecas", "rotulo": "Linha do tempo e peças",
                       "contagem": len(eventos), "alerta": 0}]}


def texto_da_peca(p: dict, qual: str, eventos: list[dict], *, sv: dict) -> list[str]:
    """Os parágrafos da peça, com o que o artigo manda conter. Só monta."""
    def ultimo(tipo: str) -> dict:
        return next((e for e in reversed(eventos) if e["tipo"] == tipo), {})

    def br(d: Any) -> str:
        d = str(d or "")[:10]
        return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if len(d) == 10 else ""

    base = (f"Processo n. {p['rotulo']}, protocolo n. {p.get('protocolo') or '—'}. "
            f"Credor fiduciário: {p['credor_nome']}. Devedor fiduciante: {p['devedor_nome']}. "
            f"Bem: {p['bem_descricao']}" + (f", identificação {p['bem_identificacao']}" if p.get("bem_identificacao") else "") + ".")
    if qual == "NOTIFICACAO":
        return [
            f"A {p['devedor_nome']}" + (f", {p['devedor_endereco']}" if p.get("devedor_endereco") else "") + ".",
            base + (f" Contrato: {p['contrato']}." if p.get("contrato") else "")
            + (f" Montante indicado pelo credor: {reais(p['valor_centavos'])}." if p.get("valor_centavos") else ""),
            "Seguem o requerimento do credor e os documentos que o instruem.",
            f"Fica Vossa Senhoria notificada para, em {DIAS_DO_DEVEDOR} dias corridos, contados do primeiro dia útil "
            "seguinte à comprovação da leitura da notificação eletrônica ou ao recebimento do aviso de recebimento nesta serventia:",
            "a) pagar voluntariamente a dívida, sob pena de consolidação da propriedade do bem em favor do credor; ou",
            "b) apresentar impugnação, limitada ao valor total da dívida ou a pagamento não processado pelo credor, com a "
            "indicação do valor devido, os documentos comprobatórios e o respectivo pagamento.",
            "Advertências: (a) o pagamento integral convalesce o contrato; (b) não havendo pagamento, deverá, no mesmo prazo, "
            "entregar ou disponibilizar o bem conforme as instruções do credor, sob pena de multa de 5% do valor da dívida, "
            "comunicando a entrega a esta serventia em até 2 dias úteis, com o termo firmado pelo credor; (c) sem a entrega, "
            "haverá indisponibilidade e restrição de circulação e transferência do bem, além da busca e apreensão e da "
            "consolidação da propriedade em favor do credor.",
        ]
    if qual == "CERTIDAO_BUSCA":
        e = ultimo("BUSCA_REQUERIDA")
        return [f"CERTIFICO, nos termos do art. 397-AH, IV, do Código Nacional de Normas, que em {br(e.get('dia'))} o credor "
                "fiduciário requereu a busca e apreensão extrajudicial do bem abaixo, vencido o prazo do devedor sem "
                "pagamento, entrega ou disponibilização.", base,
                "A diligência não é ato coercitivo (art. 397-AI, § 5º)."]
    if qual in ("AUTO", "NEGATIVA", "RECUSA"):
        tipo = {"AUTO": "DILIGENCIA_POSITIVA", "NEGATIVA": "DILIGENCIA_NEGATIVA", "RECUSA": "DILIGENCIA_TERCEIRO_RECUSOU"}[qual]
        e = ultimo(tipo)
        abre = {"AUTO": "AUTO DE APREENSÃO E DE ENTREGA DA POSSE ao credor ou a seu mandatário.",
                "NEGATIVA": "CERTIFICO o resultado negativo da diligência de apreensão.",
                "RECUSA": "CERTIFICO que o terceiro possuidor recusou a entrega do bem, cabendo ao credor as medidas judiciais."}[qual]
        return [abre, base, f"Em {br(e.get('dia'))}. {e.get('texto') or ''}"]
    if qual == "CONSOLIDACAO":
        e = ultimo("DILIGENCIA_POSITIVA") or ultimo("ENTREGA")
        return [f"CERTIFICO a consolidação da propriedade fiduciária em favor do credor, em {br(e.get('dia'))}, "
                "nos termos do art. 8º-B do Decreto-Lei 911/1969 e dos arts. 397-AJ do Código Nacional de Normas e 956, V, do "
                "Código de Normas da CGJ/TJMA.", base, e.get("texto") or ""]
    if qual == "ENCERRAMENTO":
        e = eventos[-1] if eventos else {}
        return [f"CERTIFICO o encerramento do processo: {SITUACOES.get(p['situacao'], p['situacao'])}, em {br(e.get('dia'))}.",
                base, e.get("texto") or ""]
    raise FiduciariaError("Esta peça não existe.")
