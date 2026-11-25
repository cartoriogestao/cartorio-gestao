"""A INTIMAÇÃO DO DEVEDOR FIDUCIANTE, no Registro de Imóveis — o procedimento inteiro, sem a Central.

    «pode abrir a I1 da intimação também»                    — o oficial, 24/11/2026 (RI013)

A NORMA
    Lei 9.514/1997, art. 26 (texto compilado em `base_normativa/federal/lei-9514-1997-11-20.md`);
    Código de Normas do TJMA, arts. 721 a 726 (`base_normativa/estadual_ma/codigo_de_normas_tjma.md`);
    Lei 6.015/1973, art. 9º, §§ 1º a 3º (contagem dos prazos).

O QUE ELE FAZ
    O credor pede a intimação; o requerimento é prenotado no Livro 1 pelo caminho de sempre, e
    esta ficha se liga à prenotação e à matrícula. Cada pessoa a intimar é uma linha (devedor,
    cônjuge, proprietário diverso do devedor; avalista e fiador só a pedido expresso do credor —
    TJMA 722, § 5º). Cada linha tem os endereços indicados pelo credor e os que a serventia acha
    no acervo — o do contrato e o do imóvel (TJMA 724, § 5º). Cada tentativa é uma diligência
    com meio, data e resultado. Quando todos estão intimados, corre o prazo de 15 dias da purga,
    contado da intimação do último (TJMA 723, § 1º). Purgada a mora, recibo e aviso ao credor em
    3 dias úteis (TJMA 725); sem purga, a certidão de não purgação, que instrui a consolidação
    (TJMA 726). A certidão — de purgação ou de não purgação — encerra a prenotação (TJMA 723).

A PRENOTAÇÃO NÃO VENCE
    Autuar suspende o prazo da prenotação com o motivo `INTIMACAO_FIDUCIARIA`
    (`ri_prenotacao_prazo`). Suspensa, ela continua ABERTA, e por isso continua na cláusula das
    prenotações abertas de toda certidão da matrícula (TJMA 723, § 3º;
    `ri_web.clausula_html_prenotacoes_abertas`). Ela não se retoma à mão enquanto o procedimento
    estiver aberto: só a certidão a encerra.

OS PRAZOS — O TEXTO DA LEI
    · Purga: «no prazo de 15 (quinze) dias» (Lei 9.514, art. 26, § 1º). A lei não diz «úteis», e
      o § 1º do art. 9º da Lei 6.015 manda contar em dias úteis os prazos «para a prática de atos
      pelos oficiais» — a purga é ato do devedor. Por isso CORRIDOS, com os critérios do CPC que o
      § 3º do mesmo art. 9º manda seguir: começa no primeiro dia útil depois da intimação e o fim
      que cai em dia sem expediente passa ao dia útil seguinte (CPC, art. 224). A contagem é
      configurável (`ri_intimacao_purga_contagem`), porque a leitura é do titular.
    · Edital: publicado por no mínimo 3 dias; o prazo da purga conta da última publicação
      (art. 26, § 4º). Havendo e-mail do devedor no contrato, a intimação vai por ele com 15 dias,
      no mínimo, de antecedência do edital (§ 4º-B).
    · Aviso ao credor da purga: em até 3 dias úteis (TJMA 725; Lei 9.514, art. 26, § 6º).
    · Depois da não purgação: o credor tem 120 dias corridos para pedir a consolidação (TJMA 726,
      § 2º); no financiamento habitacional ela só se averba 30 dias úteis depois de expirado o
      prazo da purga (TJMA 726, § 1º; Lei 9.514, art. 26-A, § 1º). Só se mostram: a
      consolidação é título novo, e este módulo não a lavra.

O QUE O SISTEMA NÃO QUALIFICA
    O demonstrativo do débito e a projeção são do credor (TJMA 722, § 2º); a carência também
    (§ 3º). A ficha guarda e mostra, e a tela diz isso.

O QUE ESTE MÓDULO NÃO FAZ
    Não fala com o ONR nem com os Correios (o AR digital, `correios_api`, ainda é simulador: a
    diligência pelo correio tem o lugar do número do objeto, e nada mais). Não sela nem cobra:
    os atos que levam selo estão em `ATOS_COBRADOS`, com o que falta decidir. A linha do tempo
    não se apaga nem se edita.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any, Callable, Iterable

from bd_nativo import banco


class IntimacaoError(ValueError):
    """Impedimento de regra, com a frase pronta para a tela."""


# ---------------------------------------------------------------- vocabulário

BALCAO = "BALCAO"
CENTRAL_ONR = "CENTRAL_ONR"
ORIGENS = {BALCAO: "Balcão", CENTRAL_ONR: "Central de Intimações do ONR"}

AUTUADO = "AUTUADO"
EXIGENCIA = "EXIGENCIA"
INTIMANDO = "INTIMANDO"
PRAZO_PURGA = "PRAZO_PURGA"
PURGADA = "PURGADA"
ENCERRADO_PURGACAO = "ENCERRADO_PURGACAO"
ENCERRADO_NAO_PURGACAO = "ENCERRADO_NAO_PURGACAO"
RECUSADO = "RECUSADO"
DESISTENCIA = "DESISTENCIA"
CANCELADO_JUDICIAL = "CANCELADO_JUDICIAL"

SITUACOES = {
    AUTUADO: "Autuado, aguarda a qualificação",
    EXIGENCIA: "Aguarda o credor cumprir exigência",
    INTIMANDO: "Intimações em curso",
    PRAZO_PURGA: "Prazo da purga correndo",
    PURGADA: "Mora purgada, aguarda a certidão",
    ENCERRADO_PURGACAO: "Encerrado: certidão de purgação da mora",
    ENCERRADO_NAO_PURGACAO: "Encerrado: certidão de não purgação da mora",
    RECUSADO: "Encerrado: requerimento recusado",
    DESISTENCIA: "Encerrado: desistência do credor",
    CANCELADO_JUDICIAL: "Encerrado: cancelado por ordem judicial",
}
TERMINAIS = (ENCERRADO_PURGACAO, ENCERRADO_NAO_PURGACAO, RECUSADO, DESISTENCIA, CANCELADO_JUDICIAL)

DEVEDOR = "DEVEDOR"
PAPEIS = {
    DEVEDOR: "Devedor fiduciante",
    "TERCEIRO_FIDUCIANTE": "Terceiro fiduciante",
    "CONJUGE": "Cônjuge ou companheiro",
    "PROPRIETARIO": "Proprietário, diverso do devedor",
    "CESSIONARIO": "Cessionário",
    "AVALISTA": "Avalista",
    "FIADOR": "Fiador",
}
#: Só entram a pedido expresso do credor (TJMA 722, § 5º).
SO_A_PEDIDO = frozenset({"AVALISTA", "FIADOR"})
#: Quem precisa estar na lista para a qualificação positiva.
QUEM_DEVE = frozenset({DEVEDOR, "TERCEIRO_FIDUCIANTE"})

CREDOR = "CREDOR"
CONTRATO = "CONTRATO"
IMOVEL = "IMOVEL"
ORIGENS_DO_ENDERECO = {
    CREDOR: "Indicado pelo credor (TJMA 722, II)",
    CONTRATO: "Domicílio do contrato, no acervo (TJMA 724, § 5º)",
    IMOVEL: "Endereço do imóvel (TJMA 724, § 5º)",
    "OUTRO": "Achado na diligência",
}

PESSOAL = "PESSOAL"
RTD = "RTD"
CORREIO = "CORREIO"
MEIOS = {
    PESSOAL: "Pessoal, pela serventia (TJMA 724, § 1º: a preferência)",
    RTD: "Pelo RTD da comarca do imóvel ou do domicílio (TJMA 724)",
    CORREIO: "SEDEX registrado, com AR e mão própria (TJMA 724, § 1º)",
}

# O efeito de cada resultado. INTIMADO conta para o prazo; NEGATIVA e IGNORADO fundamentam o
# edital (com o PESSOAL ou o RTD: o correio que falha manda usar os outros meios, 724, § 2º);
# OCULTACAO marca a hora certa (Lei 9.514, art. 26, § 3º-A).
INTIMADO = "INTIMADO"
NEGATIVA = "NEGATIVA"
IGNORADO = "IGNORADO"
OCULTACAO = "OCULTACAO"

RESULTADOS: dict[str, dict[str, Any]] = {
    # pessoal e RTD
    "INTIMADO": {"rotulo": "Intimado: o próprio, o representante legal ou o procurador",
                 "efeito": INTIMADO, "meios": (PESSOAL, RTD)},
    "RECUSOU_ASSINAR": {"rotulo": "Intimado; recusou-se a assinar, e isso foi certificado",
                        "efeito": INTIMADO, "meios": (PESSOAL, RTD)},
    "NAO_ENCONTRADO": {"rotulo": "Procurado no endereço e não encontrado",
                       "efeito": NEGATIVA, "meios": (PESSOAL, RTD)},
    "SUSPEITA_OCULTACAO": {"rotulo": "Suspeita motivada de ocultação: hora certa marcada (art. 26, § 3º-A)",
                           "efeito": OCULTACAO, "meios": (PESSOAL, RTD)},
    "HORA_CERTA": {"rotulo": "Intimado com hora certa (art. 26, § 3º-A)",
                   "efeito": INTIMADO, "meios": (PESSOAL, RTD)},
    "PORTARIA": {"rotulo": "Intimado na portaria do condomínio (art. 26, § 3º-B)",
                 "efeito": INTIMADO, "meios": (PESSOAL, RTD)},
    "LOCAL_IGNORADO": {"rotulo": "Local ignorado, incerto ou inacessível, certificado (art. 26, §§ 4º e 4º-C)",
                       "efeito": IGNORADO, "meios": (PESSOAL, RTD)},
    # correio
    "ENTREGUE_MP": {"rotulo": "Entregue em mão própria: AR assinado pelo destinatário",
                    "efeito": INTIMADO, "meios": (CORREIO,)},
    "RECUSOU": {"rotulo": "Recusou receber ou assinar (TJMA 724, § 2º)",
                "efeito": NEGATIVA, "meios": (CORREIO,)},
    "AUSENTE_3": {"rotulo": "Não encontrado nas 3 tentativas do carteiro (TJMA 724, § 2º)",
                  "efeito": NEGATIVA, "meios": (CORREIO,)},
    "MUDOU_SE": {"rotulo": "Mudou-se", "efeito": NEGATIVA, "meios": (CORREIO,)},
    "DESCONHECIDO": {"rotulo": "Desconhecido no endereço", "efeito": NEGATIVA, "meios": (CORREIO,)},
    "ENDERECO_INSUFICIENTE": {"rotulo": "Endereço insuficiente ou inexistente", "efeito": NEGATIVA,
                              "meios": (CORREIO,)},
    "FALECIDO": {"rotulo": "Falecido (avise o credor)", "efeito": NEGATIVA, "meios": (CORREIO,)},
}
#: Sem estas, a hora certa e a portaria não cabem: a lei pede duas procuras e a suspeita motivada.
PROCURAS_ANTES_DA_HORA_CERTA = 2
TENTATIVAS_DO_CARTEIRO = 3
PUBLICACOES_DO_EDITAL = 3
DIAS_DO_EMAIL_ANTES_DO_EDITAL = 15

PENDENTE = "PENDENTE"
EDITAL_EM_CURSO = "EDITAL_EM_CURSO"
INTIMADO_EDITAL = "INTIMADO_EDITAL"
SITUACOES_DO_INTIMANDO = {
    PENDENTE: "A intimar",
    INTIMADO: "Intimado",
    EDITAL_EM_CURSO: "Edital em publicação",
    INTIMADO_EDITAL: "Intimado por edital",
}
JA_INTIMADO = (INTIMADO, INTIMADO_EDITAL)

FORMAS_DA_PURGA = {
    "TRANSFERENCIA": "Transferência bancária ou Pix (TJMA 725, parágrafo único: não se recusa)",
    "DEPOSITO": "Depósito na conta indicada pela serventia",
    "BOLETO": "Boleto da Central",
    "OUTRA": "Outra (descrever no comprovante)",
}
FORMAS_DO_REPASSE = {
    "RETIRADA": "Comunicado ao credor para retirada (TJMA 725)",
    "ENTREGA_DIRETA": "Entregue diretamente ao credor (TJMA 725)",
}

DIAS_DA_PURGA = 15            # Lei 9.514, art. 26, § 1º
UTEIS_DO_AVISO_AO_CREDOR = 3  # TJMA 725
DIAS_PARA_CONSOLIDAR = 120    # TJMA 726, § 2º: corridos
UTEIS_DO_HABITACIONAL = 30    # TJMA 726, § 1º
MINIMO_DO_TEXTO = 10

# A QUALIFICAÇÃO DO REQUERIMENTO. TJMA 721, 722 e 724, § 4º. O demonstrativo NÃO se qualifica.
REQUISITOS: tuple[dict, ...] = tuple(
    {"chave": c, "artigo": a, "texto": t} for c, a, t in (
        ("contrato_registrado", "TJMA 721",
         "O contrato de alienação fiduciária está registrado nesta serventia, na matrícula indicada."),
        ("qualificacao", "TJMA 722, I",
         "Nome e qualificação completa dos devedores fiduciantes e dos cônjuges, se casados."),
        ("enderecos", "TJMA 722, II", "Endereço completo para as intimações."),
        ("planilha", "TJMA 722, III",
         "Planilha com o demonstrativo do débito e a projeção dos valores atualizados para a purga."),
        ("representacao", "TJMA 722, § 1º",
         "Prova de que quem assina representa o credor (dispensada pela Central, § 4º)."),
        ("pj", "TJMA 724, § 4º",
         "Intimando pessoa jurídica: certidão do contrato ou estatuto social, para aferir a representação."),
    ))
NAO_SE_QUALIFICA = (
    "O demonstrativo do débito e a projeção dos valores são de responsabilidade exclusiva do credor "
    "(TJMA 722, § 2º), e o prazo de carência também (§ 3º): a serventia guarda e mostra, e não confere.")

PECAS = {
    "INTIMACAO": "Intimação ao devedor fiduciante (Lei 9.514, art. 26, §§ 1º e 3º)",
    "EDITAL": "Edital de intimação (Lei 9.514, art. 26, § 4º)",
    "RECIBO": "Recibo da purgação da mora (TJMA 725)",
    "CERTIDAO_PURGACAO": "Certidão de purgação da mora (TJMA 723)",
    "CERTIDAO_NAO_PURGACAO": "Certidão de não purgação da mora (TJMA 723 e 726)",
}
PECAS_DO_INTIMANDO = frozenset({"INTIMACAO", "EDITAL"})
AVISO_SEM_SELO = "SEM SELO — NÃO ENTREGAR"

# O QUE LEVA SELO E EMOLUMENTO. Medido na tabela vigente em 24/11/2026 e no `ato_selado`; o
# valor nunca mora aqui — sai da tabela (`emolumentos`) na hora de mostrar. O que não se achou
# é pendência, escrita como tal.
ATOS_COBRADOS: tuple[dict, ...] = tuple(
    {"ato": a, "codigo_tj": c, "selo": s, "pendencia": p} for a, c, s, p in (
        ("Prenotação do requerimento", "16.1",
         "Sim: o selo da prenotação de sempre (ato_selado.CODIGO_DA_PRENOTACAO).", ""),
        ("Intimação, por pessoa intimada, inclusive por edital", "16.23",
         "Sim: o caminho existe (notificacao_selo, AtosEmGeral), hoje só para retificação e usucapião.",
         "Ligar a tabela ri_intimacao_intimandos ao notificacao_selo e ao ato_selado (fase I1b)."),
        ("Diligência da serventia na intimação pessoal", "16.34",
         "A confirmar: o item existe na tabela; não há caminho de selo próprio no sistema.",
         "O titular decide se a diligência pessoal se cobra à parte, por ida."),
        ("Certidão de purgação ou de não purgação", "16.24.1",
         "A confirmar: é certidão de uma folha (16.24.1, mais 16.24.2 por folha).",
         "Confirmar o item e o caminho do selo da certidão no selador."),
        ("Publicação do edital na imprensa", "",
         "Não é emolumento: é despesa do credor (TJMA 724, caput).", ""),
        ("Recibo da purga", "",
         "Não achei item na tabela.", "Confirmar que o recibo não se cobra."),
        ("Averbação da consolidação", "16.43",
         "Título novo, fora desta fase (cobra-se pela 16.9).", ""),
    ))


# ---------------------------------------------------------------- o esquema

SCHEMA = """
CREATE TABLE IF NOT EXISTS ri_intimacoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    numero INTEGER NOT NULL,
    ano INTEGER NOT NULL,
    protocolo_id INTEGER NOT NULL UNIQUE,
    matricula_id INTEGER NOT NULL,
    ato_garantia_id INTEGER,
    situacao TEXT NOT NULL,
    origem TEXT NOT NULL DEFAULT 'BALCAO',
    protocolo_central TEXT,
    data_remessa TEXT,
    contrato TEXT,
    credor_nome TEXT NOT NULL,
    credor_documento TEXT,
    credor_contato TEXT,
    solicitante_nome TEXT,
    solicitante_documento TEXT,
    representante_nome TEXT,
    habitacional INTEGER NOT NULL DEFAULT 0,
    avalistas_a_pedido INTEGER NOT NULL DEFAULT 0,
    demonstrativo_centavos INTEGER,
    demonstrativo_data TEXT,
    prestacoes TEXT NOT NULL DEFAULT '[]',
    projecao TEXT NOT NULL DEFAULT '[]',
    dados_central TEXT,
    requisitos TEXT NOT NULL DEFAULT '[]',
    exigencia TEXT,
    prazo_ate TEXT,
    prazo_rotulo TEXT,
    purga_dia TEXT,
    purga_centavos INTEGER,
    purga_forma TEXT,
    purga_comprovante TEXT,
    purga_conta TEXT,
    credor_avisar_ate TEXT,
    credor_avisado_em TEXT,
    repasse_dia TEXT,
    repasse_forma TEXT,
    repasse_centavos INTEGER,
    repasse_despesas_centavos INTEGER,
    repasse_comprovante TEXT,
    certidao_tipo TEXT,
    certidao_dia TEXT,
    certidao_texto TEXT,
    encerrado_em TEXT,
    encerrado_motivo TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    UNIQUE(ano, numero),
    FOREIGN KEY(protocolo_id) REFERENCES ri_protocolos(id),
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id),
    FOREIGN KEY(ato_garantia_id) REFERENCES ri_atos(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_intimacoes_situacao ON ri_intimacoes(situacao, prazo_ate);
CREATE INDEX IF NOT EXISTS ix_ri_intimacoes_matricula ON ri_intimacoes(matricula_id);

-- Uma linha por pessoa a intimar (TJMA 724, § 3º). As colunas do selo são as mesmas da
-- notificação da retificação (`rt_confrontantes`): é o encaixe do 16.23 (`notificacao_selo`).
CREATE TABLE IF NOT EXISTS ri_intimacao_intimandos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    intimacao_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    documento TEXT,
    papel TEXT NOT NULL,
    participacao TEXT,
    email TEXT,
    pessoa_juridica INTEGER NOT NULL DEFAULT 0,
    representante TEXT,
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',
    intimado_em TEXT,
    intimado_como TEXT,
    email_enviado_em TEXT,
    sem_endereco_no_acervo TEXT,
    edital_publicacoes TEXT NOT NULL DEFAULT '[]',
    ordem INTEGER NOT NULL DEFAULT 0,
    selo TEXT,
    selo_texto TEXT,
    selo_qr TEXT,
    selo_em TEXT,
    selo_por TEXT,
    selo_item TEXT,
    impresso_em TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    FOREIGN KEY(intimacao_id) REFERENCES ri_intimacoes(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_intimandos_intimacao ON ri_intimacao_intimandos(intimacao_id, ordem);

CREATE TABLE IF NOT EXISTS ri_intimacao_enderecos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    intimando_id INTEGER NOT NULL,
    origem TEXT NOT NULL,
    endereco TEXT NOT NULL,
    fonte TEXT,
    criado_em TEXT NOT NULL,
    FOREIGN KEY(intimando_id) REFERENCES ri_intimacao_intimandos(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_intimacao_enderecos ON ri_intimacao_enderecos(intimando_id);

-- Cada tentativa. `rastreio` e `ar_id` são o lugar do AR digital (`correios_api`), que ainda é
-- simulador e não se liga daqui.
CREATE TABLE IF NOT EXISTS ri_intimacao_diligencias (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    intimando_id INTEGER NOT NULL,
    endereco_id INTEGER,
    endereco TEXT,
    meio TEXT NOT NULL,
    dia TEXT NOT NULL,
    hora TEXT,
    resultado TEXT NOT NULL,
    tentativas_carteiro INTEGER,
    quem_recebeu TEXT,
    detalhe TEXT,
    rastreio TEXT,
    ar_id TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    FOREIGN KEY(intimando_id) REFERENCES ri_intimacao_intimandos(id),
    FOREIGN KEY(endereco_id) REFERENCES ri_intimacao_enderecos(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_intimacao_diligencias ON ri_intimacao_diligencias(intimando_id, dia);

CREATE TABLE IF NOT EXISTS ri_intimacao_eventos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    intimacao_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    dia TEXT NOT NULL,
    texto TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    FOREIGN KEY(intimacao_id) REFERENCES ri_intimacoes(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_intimacao_eventos ON ri_intimacao_eventos(intimacao_id, id)
"""


def init_ri_intimacao_schema(con) -> None:
    """Cria as tabelas. Idempotente. Vem depois do `ri_schema`, para o qual aponta."""
    bd = banco(con)
    for comando in re.split(r";[ \t]*\n", SCHEMA):
        if re.sub(r"--[^\n]*", "", comando).strip():
            bd.escrever(comando)


# ---------------------------------------------------------------- configuração

#: As decisões do titular, com o padrão mais seguro até ele decidir.
CONFIGURACOES = {
    "ri_intimacao_meio_padrao": PESSOAL,       # TJMA 724, § 1º: a pessoal é a preferência
    "ri_intimacao_conta_purga": "",            # em que conta o devedor deposita
    "ri_intimacao_repasse": "",                # RETIRADA ou ENTREGA_DIRETA (TJMA 725)
    "ri_intimacao_purga_contagem": "CORRIDOS",  # o texto da lei; UTEIS se o titular decidir
}
CONTAGENS = {"CORRIDOS": "Dias corridos (o texto do art. 26, § 1º)",
             "UTEIS": "Dias úteis (leitura ampla do art. 9º da Lei 6.015)"}


def configuracao(get_setting: Callable[[str, str], str]) -> dict:
    """As quatro escolhas, já conferidas. Valor estranho volta ao padrão. Só LÊ."""
    saida = {k: (get_setting(k, v) or v).strip() for k, v in CONFIGURACOES.items()}
    if saida["ri_intimacao_meio_padrao"] not in MEIOS:
        saida["ri_intimacao_meio_padrao"] = PESSOAL
    if saida["ri_intimacao_purga_contagem"] not in CONTAGENS:
        saida["ri_intimacao_purga_contagem"] = "CORRIDOS"
    if saida["ri_intimacao_repasse"] not in FORMAS_DO_REPASSE:
        saida["ri_intimacao_repasse"] = ""
    return saida


def conferir_configuracao(form: dict) -> dict:
    """O que a tela de configuração mandou, pronto para gravar. Recusa o que não é escolha."""
    meio = _texto(form.get("ri_intimacao_meio_padrao")) or PESSOAL
    contagem = _texto(form.get("ri_intimacao_purga_contagem")) or "CORRIDOS"
    repasse = _texto(form.get("ri_intimacao_repasse"))
    if meio not in MEIOS or contagem not in CONTAGENS or (repasse and repasse not in FORMAS_DO_REPASSE):
        raise IntimacaoError("Escolha uma das opções da lista.")
    return {"ri_intimacao_meio_padrao": meio, "ri_intimacao_purga_contagem": contagem,
            "ri_intimacao_repasse": repasse,
            "ri_intimacao_conta_purga": _texto(form.get("ri_intimacao_conta_purga"))[:500]}


# ---------------------------------------------------------------- utilidades


def _dia_util_padrao(d: date) -> bool:
    from ri_schema import eh_dia_util
    return eh_dia_util(d, ())


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _dia(v: Any, o_que: str = "a data") -> date:
    bruto = _texto(v)
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", bruto[:10])
    if m:
        bruto = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    try:
        return date.fromisoformat(bruto[:10])
    except ValueError as erro:
        raise IntimacaoError(f"Informe {o_que} no formato do calendário.") from erro


def _dia_ou_nada(v: Any) -> str | None:
    return _dia(v).isoformat() if _texto(v) else None


def _exigir_texto(v: Any, o_que: str) -> str:
    limpo = _texto(v)
    if len(limpo) < MINIMO_DO_TEXTO:
        raise IntimacaoError(f"Escreva {o_que} com pelo menos dez letras.")
    return limpo


def centavos(v: Any) -> int | None:
    """«1.234,56», «1234.56», 1234.56 → 123456. Vazio → None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(round(float(v) * 100))
    limpo = _texto(v).replace("R$", "").replace(" ", "")
    if not limpo:
        return None
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return int(round(float(limpo) * 100))
    except ValueError as erro:
        raise IntimacaoError(f"«{v}» não é um valor em reais.") from erro


def reais(c: Any) -> str:
    if c is None or c == "":
        return ""
    c = int(c)
    inteiro = f"{abs(c) // 100:,}".replace(",", ".")
    return f"{'-' if c < 0 else ''}R$ {inteiro},{abs(c) % 100:02d}"


def _digitos(v: Any) -> str:
    return re.sub(r"\D", "", _texto(v))


def primeiro_util_depois(d: date, e_util: Callable[[date], bool] = _dia_util_padrao) -> date:
    d += timedelta(days=1)
    while not e_util(d):
        d += timedelta(days=1)
    return d


def somar_uteis(d: date, n: int, e_util: Callable[[date], bool] = _dia_util_padrao) -> date:
    for _ in range(n):
        d = primeiro_util_depois(d, e_util)
    return d


def fim_da_purga(intimado_em: date, *, contagem: str = "CORRIDOS",
                 e_util: Callable[[date], bool] = _dia_util_padrao, dias: int = DIAS_DA_PURGA) -> date:
    """O último dia para purgar. Só calcula.

    CORRIDOS: o dia 1 é o primeiro dia útil depois da intimação, e o fim que cai em dia sem
    expediente passa ao primeiro dia útil (Lei 6.015, art. 9º, § 3º; CPC, art. 224). UTEIS: os
    15 dias contados só nos dias de expediente.
    """
    if contagem == "UTEIS":
        return somar_uteis(intimado_em, dias, e_util)
    fim = primeiro_util_depois(intimado_em, e_util) + timedelta(days=dias - 1)
    while not e_util(fim):
        fim += timedelta(days=1)
    return fim


def ler_valores(texto: Any) -> list[dict]:
    """Uma linha por valor: «DD/MM/AAAA; 1.234,56» (ou com tabulação). Só calcula.

    É como a tela recebe as prestações vencidas e a projeção do credor.
    """
    saida = []
    for n, linha in enumerate(_texto(texto).splitlines(), 1):
        linha = linha.strip()
        if not linha:
            continue
        partes = [p.strip() for p in re.split(r"[;\t|]", linha) if p.strip()]
        if len(partes) < 2:
            raise IntimacaoError(f"Linha {n} dos valores: escreva a data, ponto e vírgula, e o valor.")
        saida.append({"vencimento": _dia(partes[0], f"a data da linha {n}").isoformat(),
                      "centavos": centavos(partes[-1])})
    return sorted(saida, key=lambda x: x["vencimento"])


def valor_da_projecao(projecao: Iterable[dict], dia: str) -> int | None:
    """O que a projeção manda pagar naquele dia: a primeira linha que vence nele ou depois."""
    for linha in sorted(projecao, key=lambda x: x["vencimento"]):
        if linha["vencimento"] >= dia[:10]:
            return linha["centavos"]
    return None


# ---------------------------------------------------------------- leitura


def _json(v: Any, padrao: Any) -> Any:
    try:
        return json.loads(v) if v else padrao
    except (TypeError, ValueError):
        return padrao


def um(con, iid: int) -> dict | None:
    linha = banco(con).um(
        """SELECT i.*, p.numero AS protocolo_numero, p.data_prenotacao, p.situacao AS protocolo_situacao,
                  p.prazo_suspenso_motivo, m.numero AS matricula_numero
             FROM ri_intimacoes i
             JOIN ri_protocolos p ON p.id = i.protocolo_id
             JOIN ri_matriculas m ON m.id = i.matricula_id
            WHERE i.id = %s""", (int(iid),))
    if not linha:
        return None
    i = dict(linha)
    i["rotulo"] = f"{i['numero']}/{i['ano']}"
    i["requisitos_ok"] = set(_json(i["requisitos"], []))
    i["prestacoes_lista"] = _json(i["prestacoes"], [])
    i["projecao_lista"] = _json(i["projecao"], [])
    i["situacao_rotulo"] = SITUACOES.get(i["situacao"], i["situacao"])
    return i


def do_protocolo(con, protocolo_id: int) -> dict | None:
    bd = banco(con)
    if not bd.tem_tabela("ri_intimacoes"):
        return None
    linha = bd.um("SELECT id FROM ri_intimacoes WHERE protocolo_id=%s", (int(protocolo_id),))
    return um(con, int(linha["id"])) if linha else None


def aberta_no_protocolo(con, protocolo_id: int) -> bool:
    """Há procedimento de intimação aberto nesta prenotação? Só LÊ. `ri_prenotacao_prazo` pergunta."""
    i = do_protocolo(con, protocolo_id)
    return bool(i and i["situacao"] not in TERMINAIS)


def intimandos_de(con, iid: int) -> list[dict]:
    bd = banco(con)
    saida = []
    for r in bd.ler("SELECT * FROM ri_intimacao_intimandos WHERE intimacao_id=%s ORDER BY ordem, id",
                    (int(iid),)):
        x = dict(r)
        x["enderecos"] = [dict(e) for e in bd.ler(
            "SELECT * FROM ri_intimacao_enderecos WHERE intimando_id=%s ORDER BY id", (int(x["id"]),))]
        x["diligencias"] = [dict(d) for d in bd.ler(
            "SELECT * FROM ri_intimacao_diligencias WHERE intimando_id=%s ORDER BY dia, id", (int(x["id"]),))]
        x["publicacoes"] = _json(x["edital_publicacoes"], [])
        x["papel_rotulo"] = PAPEIS.get(x["papel"], x["papel"])
        x["situacao_rotulo"] = SITUACOES_DO_INTIMANDO.get(x["situacao"], x["situacao"])
        saida.append(x)
    return saida


def eventos_de(con, iid: int) -> list[dict]:
    return [dict(x) for x in banco(con).ler(
        "SELECT * FROM ri_intimacao_eventos WHERE intimacao_id=%s ORDER BY id", (int(iid),))]


def prenotacoes_para_autuar(con) -> list[dict]:
    """Prenotações abertas, sem procedimento, com a matrícula amarrada ou digitada. Só LÊ."""
    return [dict(x) for x in banco(con).ler(
        """SELECT p.id, p.numero, p.data_prenotacao, p.apresentante, p.natureza_titulo, p.objeto,
                  p.matricula_id, p.matricula_numero, p.prazo_suspenso_motivo
             FROM ri_protocolos p
            WHERE p.situacao = 'ABERTO'
              AND NOT EXISTS (SELECT 1 FROM ri_intimacoes i WHERE i.protocolo_id = p.id)
            ORDER BY p.data_prenotacao DESC, p.numero DESC
            LIMIT 200""")]


# ---------------------------------------------------------------- o acervo (TJMA 724, § 5º)

_CHAVES_DO_DOMICILIO = re.compile(
    r"(residentes?\b|domiciliad[oa]s?\b|com sede\b|sediad[oa]\b|estabelecid[oa]\b)", re.I)


def _endereco_da_qualificacao(qualificacao: str) -> str:
    """O trecho da qualificação que fala do domicílio. Sugestão, para o escrevente conferir."""
    q = _texto(qualificacao)
    m = _CHAVES_DO_DOMICILIO.search(q)
    if not m:
        return ""
    trecho = q[m.start():]
    return re.split(r";", trecho, maxsplit=1)[0].strip(" .,")


def endereco_do_imovel(m: dict) -> str:
    """O endereço do imóvel, pelos campos da ficha. Vazio se a ficha não os tem. Só calcula."""
    rua = ", ".join(x for x in (_texto(m.get("logradouro")), _texto(m.get("numero_predial")),
                                _texto(m.get("complemento_endereco")), _texto(m.get("bairro"))) if x)
    if not rua:
        return ""
    lugar = "/".join(x for x in (_texto(m.get("cidade")), _texto(m.get("uf"))) if x)
    cep = f"CEP {_texto(m.get('cep'))}" if _texto(m.get("cep")) else ""
    return ", ".join(x for x in (rua, lugar, cep) if x)


def enderecos_do_acervo(con, matricula_id: int, *, nome: str, documento: str = "") -> list[dict]:
    """O que o acervo diz do domicílio desta pessoa e do imóvel (TJMA 724, § 5º). Só LÊ.

    · IMOVEL: os campos da ficha da matrícula.
    · CONTRATO: a qualificação da parte no acervo desta matrícula, de preferência no ato da
      alienação fiduciária, casando pelo CPF/CNPJ ou pelo nome. É sugestão: a tela diz de onde veio.
    """
    from ri_schema import normalizar_busca
    bd = banco(con)
    saida: list[dict] = []
    m = bd.um("SELECT * FROM ri_matriculas WHERE id=%s", (int(matricula_id),))
    if m:
        texto = endereco_do_imovel(dict(m))
        if texto:
            saida.append({"origem": IMOVEL, "endereco": texto,
                          "fonte": f"Ficha da matrícula {m['numero']}"})
    doc = _digitos(documento)
    nome_n = normalizar_busca(nome)
    candidatos = []
    for p in bd.ler(
            """SELECT p.nome, p.documento_numero, p.qualificacao, p.nome_norm, a.tipo, a.numero,
                      a.natureza_titulo
                 FROM ri_partes p LEFT JOIN ri_atos a ON a.id = p.ato_id
                WHERE p.matricula_id = %s AND COALESCE(p.qualificacao, '') <> ''
                ORDER BY a.numero DESC NULLS LAST, p.id DESC""", (int(matricula_id),)):
        mesma = (doc and _digitos(p["documento_numero"]) == doc) or (
            nome_n and (p.get("nome_norm") or normalizar_busca(p["nome"])) == nome_n)
        if not mesma:
            continue
        texto = _endereco_da_qualificacao(p["qualificacao"])
        if not texto:
            continue
        fiduciaria = "FIDUCI" in normalizar_busca(p.get("natureza_titulo") or "").upper()
        ato = f"{p['tipo']}-{p['numero']}" if p.get("tipo") else "partes da ficha"
        candidatos.append((0 if fiduciaria else 1, {
            "origem": CONTRATO, "endereco": texto,
            "fonte": f"Qualificação no {ato} da matrícula — conferir"}))
    if candidatos:
        candidatos.sort(key=lambda x: x[0])
        saida.append(candidatos[0][1])
    return saida


def sugerir_proprietarios(con, iid: int) -> list[dict]:
    """Os proprietários atuais da matrícula que ainda não estão na lista (TJMA 724, § 4º). Só LÊ."""
    from ri_schema import normalizar_busca
    i = um(con, iid)
    if not i:
        return []
    ja = intimandos_de(con, iid)
    docs = {_digitos(x["documento"]) for x in ja if _digitos(x["documento"])}
    nomes = {normalizar_busca(x["nome"]) for x in ja}
    saida = []
    for p in banco(con).ler(
            """SELECT DISTINCT nome, documento_numero FROM ri_partes
                WHERE matricula_id=%s AND proprietario_ativo=1 ORDER BY nome""", (int(i["matricula_id"]),)):
        d = _digitos(p["documento_numero"])
        if (d and d in docs) or normalizar_busca(p["nome"]) in nomes:
            continue
        saida.append({"nome": p["nome"], "documento": p["documento_numero"] or ""})
    return saida


# ---------------------------------------------------------------- as regras do intimando


def _efeito(d: dict) -> str:
    return RESULTADOS.get(d["resultado"], {}).get("efeito", "")


def faltas_para_o_edital(x: dict) -> list[str]:
    """O que falta para o oficial promover o edital deste intimando. Vazio = cabe. Só calcula.

    · todo endereço conhecido foi procurado pela serventia ou pelo RTD, sem o encontrar — o
      correio que falha manda usar os outros meios (TJMA 724, § 2º), e o edital é «à vista da
      certidão» do serventuário (Lei 9.514, art. 26, § 4º);
    · entre os endereços estão o do contrato e o do imóvel, tirados do acervo, ou está escrito por
      que o acervo não os tem (TJMA 724, § 5º; art. 26, § 4º-B);
    · não há hora certa marcada e ainda não cumprida.
    """
    if x["situacao"] in JA_INTIMADO:
        return ["Já está intimado."]
    faltas = []
    if not x["enderecos"]:
        faltas.append("Não há endereço cadastrado.")
    origens = {e["origem"] for e in x["enderecos"]}
    if not _texto(x.get("sem_endereco_no_acervo")):
        if CONTRATO not in origens:
            faltas.append("Falta procurar no endereço do domicílio do contrato (TJMA 724, § 5º).")
        if IMOVEL not in origens:
            faltas.append("Falta procurar no endereço do imóvel (TJMA 724, § 5º).")
    for e in x["enderecos"]:
        procurado = any(d["endereco_id"] == e["id"] and d["meio"] in (PESSOAL, RTD)
                        and _efeito(d) in (NEGATIVA, IGNORADO) for d in x["diligencias"])
        if not procurado:
            faltas.append(f"Sem certidão negativa da serventia ou do RTD em: {e['endereco']}.")
    ultima = x["diligencias"][-1] if x["diligencias"] else None
    if ultima and _efeito(ultima) == OCULTACAO:
        faltas.append("Há hora certa marcada: cumpra-a antes do edital (art. 26, § 3º-A).")
    return faltas


def _recalcular(con, iid: int, *, contagem: str, e_util: Callable[[date], bool]) -> None:
    """Todos intimados → corre a purga, da intimação do último (TJMA 723, § 1º). ESCREVE."""
    i = um(con, iid)
    if i["situacao"] not in (INTIMANDO, PRAZO_PURGA):
        return
    lista = intimandos_de(con, iid)
    if lista and all(x["situacao"] in JA_INTIMADO for x in lista):
        ultimo = max(_dia(x["intimado_em"]) for x in lista)
        fim = fim_da_purga(ultimo, contagem=contagem, e_util=e_util)
        rotulo = f"Purga: 15 dias {'úteis' if contagem == 'UTEIS' else 'corridos'} da última intimação ({ultimo:%d/%m/%Y})"
        if i["situacao"] != PRAZO_PURGA or i["prazo_ate"] != fim.isoformat():
            _mudar(con, iid, PRAZO_PURGA, fim, rotulo)
            _evento(con, iid, "PRAZO_PURGA", ultimo.isoformat(),
                    f"Todos intimados; a purga corre até {fim:%d/%m/%Y} ({rotulo}).", agora=None, usuario=None)
    elif i["situacao"] == PRAZO_PURGA:
        _mudar(con, iid, INTIMANDO)
        _evento(con, iid, "INTIMANDO", date.today().isoformat(),
                "Entrou intimando novo: o prazo da purga volta a esperar a última intimação.", agora=None, usuario=None)


# ---------------------------------------------------------------- escrita: o básico


def _agora_padrao() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def _evento(con, iid: int, tipo: str, dia: Any, texto: str, *, agora: str | None, usuario: str | None) -> None:
    banco(con).escrever(
        """INSERT INTO ri_intimacao_eventos(intimacao_id, tipo, dia, texto, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (int(iid), tipo, str(dia)[:10], texto, agora or _agora_padrao(), usuario))


def _mudar(con, iid: int, situacao: str, prazo: Any = None, rotulo: str | None = None) -> None:
    banco(con).escrever("UPDATE ri_intimacoes SET situacao=%s, prazo_ate=%s, prazo_rotulo=%s WHERE id=%s",
                        (situacao, str(prazo)[:10] if prazo else None, rotulo, int(iid)))


def _proc(con, iid: int, *permitidas: str) -> dict:
    i = um(con, iid)
    if not i:
        raise IntimacaoError(f"Procedimento {iid} não encontrado.")
    if i["situacao"] in TERMINAIS:
        raise IntimacaoError("Este procedimento já se encerrou, e não recebe mais lançamento.")
    if permitidas and i["situacao"] not in permitidas:
        raise IntimacaoError(f"Isso não cabe agora: o procedimento está em «{i['situacao_rotulo']}».")
    return i


def _intimando(con, iid: int, intimando_id: int) -> dict:
    for x in intimandos_de(con, iid):
        if int(x["id"]) == int(intimando_id):
            return x
    raise IntimacaoError("Esta pessoa não está na lista deste procedimento.")


def _encerrar_prenotacao(con, i: dict, *, situacao: str, rotulo: str, agora: str, usuario: str | None) -> None:
    """Cessa a prenotação (TJMA 723): tira a suspensão e encerra com o motivo. ESCREVE."""
    import ri_prenotacao_encerrar as ENCERRAR
    bd = banco(con)
    bd.escrever("""UPDATE ri_protocolos SET prazo_suspenso_desde=NULL, prazo_suspenso_motivo=NULL,
                          prazo_suspenso_por=NULL
                    WHERE id=%s AND prazo_suspenso_motivo='INTIMACAO_FIDUCIARIA'""", (int(i["protocolo_id"]),))
    ENCERRAR.gravar(bd, int(i["protocolo_id"]),
                    {"rotulo": rotulo, "situacao": situacao,
                     "observacao": f"Procedimento de intimação fiduciária n. {i['rotulo']}"},
                    quem=usuario, agora=agora)


# ---------------------------------------------------------------- autuação


def autuar(con, *, protocolo_id: int, credor_nome: str, ano: int, agora: str, hoje: date,
           matricula_id: Any = None, matricula_numero: str = "", origem: str = BALCAO, protocolo_central: str = "",
           data_remessa: Any = None, contrato: str = "", credor_documento: str = "",
           credor_contato: str = "", solicitante_nome: str = "", solicitante_documento: str = "",
           representante_nome: str = "", habitacional: bool = False, avalistas_a_pedido: bool = False,
           demonstrativo_valor: Any = None, demonstrativo_data: Any = None,
           prestacoes: Any = (), projecao: Any = (), ato_garantia_id: Any = None,
           dados_central: dict | None = None, usuario: str | None = None) -> dict:
    """Autua o requerimento sobre a prenotação aberta, e suspende o prazo dela. ESCREVE.

    TJMA 721 (o requerimento vai ao RI onde o contrato está registrado) e 723 (a prenotação só
    cessa com a certidão). A prenotação é a do Livro 1, feita pelo balcão de sempre: é ela que dá
    o número, a data e o selo da prenotação.
    """
    import ri_prenotacao_prazo as PRAZO
    bd = banco(con)
    if origem not in ORIGENS:
        raise IntimacaoError("Escolha a origem: balcão ou Central de Intimações do ONR.")
    p = bd.um("SELECT * FROM ri_protocolos WHERE id=%s", (int(protocolo_id or 0),))
    if not p:
        raise IntimacaoError("Escolha a prenotação do requerimento: é ela que dá a prioridade e o prazo.")
    if p["situacao"] != "ABERTO":
        raise IntimacaoError("A prenotação precisa estar ABERTA para receber o procedimento.")
    if bd.um("SELECT id FROM ri_intimacoes WHERE protocolo_id=%s", (int(protocolo_id),)):
        raise IntimacaoError("Esta prenotação já tem procedimento de intimação.")
    if p["prazo_suspenso_desde"] and p["prazo_suspenso_motivo"] != PRAZO.INTIMACAO_FIDUCIARIA:
        raise IntimacaoError(
            "O prazo desta prenotação já está suspenso por outro motivo "
            f"({PRAZO.MOTIVOS.get(p['prazo_suspenso_motivo'], p['prazo_suspenso_motivo'])}). Retome-o antes.")
    mid = int(_texto(matricula_id) or 0)
    digitado = _texto(matricula_numero)
    if not mid and digitado:
        achada = bd.ler("SELECT id FROM ri_matriculas WHERE numero=%s ORDER BY id", (digitado.replace(".", ""),))
        if len(achada) != 1:
            raise IntimacaoError(f"Não achei uma matrícula só com o n. {digitado}.")
        mid = achada[0]["id"]
    mid = mid or p["matricula_id"]
    if not mid and _texto(p["matricula_numero"]):
        achada = bd.ler("SELECT id FROM ri_matriculas WHERE numero=%s ORDER BY id", (_texto(p["matricula_numero"]),))
        if len(achada) == 1:
            mid = achada[0]["id"]
    if not mid or not bd.um("SELECT id FROM ri_matriculas WHERE id=%s", (int(mid),)):
        raise IntimacaoError("Ligue a matrícula onde o contrato está registrado (TJMA 721).")
    if not _texto(credor_nome):
        raise IntimacaoError("Informe o credor fiduciário.")
    garantia = None
    if _texto(ato_garantia_id):
        a = bd.um("SELECT id, matricula_id FROM ri_atos WHERE id=%s", (int(ato_garantia_id),))
        if not a or int(a["matricula_id"]) != int(mid):
            raise IntimacaoError("O ato da alienação fiduciária escolhido não é desta matrícula.")
        garantia = int(a["id"])
    prest = list(prestacoes) if not isinstance(prestacoes, str) else ler_valores(prestacoes)
    proj = list(projecao) if not isinstance(projecao, str) else ler_valores(projecao)
    bd.travar("ri_intimacoes.numero")
    numero = int(bd.valor("SELECT COALESCE(MAX(numero),0) n FROM ri_intimacoes WHERE ano=%s", (int(ano),))) + 1
    linha = bd.escrever(
        """INSERT INTO ri_intimacoes(numero, ano, protocolo_id, matricula_id, ato_garantia_id, situacao,
               origem, protocolo_central, data_remessa, contrato, credor_nome, credor_documento,
               credor_contato, solicitante_nome, solicitante_documento, representante_nome,
               habitacional, avalistas_a_pedido, demonstrativo_centavos, demonstrativo_data,
               prestacoes, projecao, dados_central, requisitos, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (numero, int(ano), int(protocolo_id), int(mid), garantia, AUTUADO, origem,
         _texto(protocolo_central), _dia_ou_nada(data_remessa), _texto(contrato), _texto(credor_nome),
         _texto(credor_documento), _texto(credor_contato), _texto(solicitante_nome),
         _texto(solicitante_documento), _texto(representante_nome), 1 if habitacional else 0,
         1 if avalistas_a_pedido else 0, centavos(demonstrativo_valor), _dia_ou_nada(demonstrativo_data),
         json.dumps(prest), json.dumps(proj),
         json.dumps(dados_central, ensure_ascii=False, default=str) if dados_central else None,
         json.dumps(["representacao"] if origem == CENTRAL_ONR else []), agora, usuario))
    iid = int(linha[0]["id"])
    if not p["prazo_suspenso_desde"]:
        PRAZO.suspender(con, int(protocolo_id), motivo=PRAZO.INTIMACAO_FIDUCIARIA, quem=usuario, hoje=hoje,
                        pelo_procedimento=True)
    texto = f"Requerimento do credor {_texto(credor_nome)} autuado sob o n. {numero}/{ano}"
    if origem == CENTRAL_ONR:
        texto += (f", recebido pela Central de Intimações (protocolo {_texto(protocolo_central) or 'não informado'}); "
                  "a prova da representação fica dispensada (TJMA 722, § 4º)")
    _evento(con, iid, "AUTUADO", agora, texto + ". Prazo da prenotação suspenso (TJMA 723).",
            agora=agora, usuario=usuario)
    return {"id": iid, "rotulo": f"{numero}/{ano}"}


# ---------------------------------------------------------------- os intimandos


def adicionar_intimando(con, iid: int, *, nome: str, papel: str, agora: str, documento: str = "",
                        participacao: str = "", email: str = "", pessoa_juridica: bool = False,
                        representante: str = "", enderecos: Any = (), buscar_no_acervo: bool = True,
                        contagem: str = "CORRIDOS", e_util: Callable[[date], bool] = _dia_util_padrao,
                        usuario: str | None = None) -> dict:
    """Uma pessoa a intimar, com os endereços do credor e os do acervo. ESCREVE.

    Avalista e fiador só a pedido expresso do credor (TJMA 722, § 5º). A pessoa jurídica é
    intimada na pessoa do representante legal (TJMA 724, § 4º).
    """
    i = _proc(con, iid, AUTUADO, EXIGENCIA, INTIMANDO, PRAZO_PURGA)
    if papel not in PAPEIS:
        raise IntimacaoError("Escolha o papel da pessoa na lista.")
    if papel in SO_A_PEDIDO and not i["avalistas_a_pedido"]:
        raise IntimacaoError("Avalista e fiador só se intimam a pedido expresso do credor (TJMA 722, § 5º). "
                             "Marque o pedido expresso no requerimento, se ele existe.")
    if not _texto(nome):
        raise IntimacaoError("Informe o nome de quem será intimado.")
    bd = banco(con)
    ordem = int(bd.valor("SELECT COALESCE(MAX(ordem),0) FROM ri_intimacao_intimandos WHERE intimacao_id=%s",
                         (int(iid),))) + 1
    novo = int(bd.escrever(
        """INSERT INTO ri_intimacao_intimandos(intimacao_id, nome, documento, papel, participacao, email,
               pessoa_juridica, representante, ordem, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(iid), _texto(nome), _texto(documento), papel, _texto(participacao), _texto(email),
         1 if pessoa_juridica else 0, _texto(representante), ordem, agora, usuario))[0]["id"])
    lista = [enderecos] if isinstance(enderecos, str) else list(enderecos)
    linhas = [ln.strip() for bloco in lista for ln in _texto(bloco).splitlines() if ln.strip()]
    for texto in linhas:
        _gravar_endereco(con, novo, CREDOR, texto, "Requerimento do credor", agora)
    achados = enderecos_do_acervo(con, i["matricula_id"], nome=nome, documento=documento) if buscar_no_acervo else []
    for e in achados:
        _gravar_endereco(con, novo, e["origem"], e["endereco"], e["fonte"], agora)
    _evento(con, iid, "INTIMANDO_NOVO", agora,
            f"{PAPEIS[papel]}: {_texto(nome)}; {len(linhas)} endereço(s) do credor e {len(achados)} do acervo.",
            agora=agora, usuario=usuario)
    _recalcular(con, iid, contagem=contagem, e_util=e_util)
    return {"id": novo, "do_acervo": len(achados)}


def _gravar_endereco(con, intimando_id: int, origem: str, texto: str, fonte: str, agora: str) -> int | None:
    bd = banco(con)
    limpo = re.sub(r"\s+", " ", _texto(texto))
    if not limpo:
        return None
    for e in bd.ler("SELECT id, endereco FROM ri_intimacao_enderecos WHERE intimando_id=%s", (int(intimando_id),)):
        if re.sub(r"\s+", " ", e["endereco"]).casefold() == limpo.casefold():
            return int(e["id"])
    return int(bd.escrever(
        """INSERT INTO ri_intimacao_enderecos(intimando_id, origem, endereco, fonte, criado_em)
           VALUES (%s,%s,%s,%s,%s) RETURNING id""",
        (int(intimando_id), origem, limpo, _texto(fonte), agora))[0]["id"])


def adicionar_endereco(con, iid: int, intimando_id: int, *, origem: str, endereco: str, agora: str,
                       fonte: str = "", usuario: str | None = None) -> dict:
    """Mais um endereço a procurar. ESCREVE."""
    _proc(con, iid, AUTUADO, EXIGENCIA, INTIMANDO)
    x = _intimando(con, iid, intimando_id)
    if origem not in ORIGENS_DO_ENDERECO:
        raise IntimacaoError("Escolha de onde veio o endereço.")
    if not _texto(endereco):
        raise IntimacaoError("Escreva o endereço.")
    eid = _gravar_endereco(con, intimando_id, origem, endereco, fonte or ORIGENS_DO_ENDERECO[origem], agora)
    _evento(con, iid, "ENDERECO", agora, f"Endereço para {x['nome']} ({ORIGENS_DO_ENDERECO[origem]}): {_texto(endereco)}.",
            agora=agora, usuario=usuario)
    return {"id": eid}


def corrigir_intimando(con, iid: int, intimando_id: int, *, agora: str, representante: Any = None,
                       email: Any = None, documento: Any = None, usuario: str | None = None) -> None:
    """Completa o representante, o e-mail ou o documento de quem já está na lista. ESCREVE."""
    _proc(con, iid, AUTUADO, EXIGENCIA, INTIMANDO)
    x = _intimando(con, iid, intimando_id)
    novos = {k: _texto(v) for k, v in (("representante", representante), ("email", email),
                                         ("documento", documento)) if v is not None and _texto(v) != _texto(x[k])}
    if not novos:
        return
    if "email" in novos and x["email_enviado_em"]:
        raise IntimacaoError("A intimação já foi mandada a este e-mail: a linha fica como prova.")
    for coluna, valor in novos.items():
        banco(con).escrever(f"UPDATE ri_intimacao_intimandos SET {coluna}=%s WHERE id=%s", (valor, int(intimando_id)))
    _evento(con, iid, "INTIMANDO_CORRIGIDO", agora,
            f"{x['nome']}: " + "; ".join(f"{k} «{v}»" for k, v in novos.items()) + ".", agora=agora, usuario=usuario)


def acervo_sem_endereco(con, iid: int, intimando_id: int, *, motivo: str, agora: str,
                        usuario: str | None = None) -> None:
    """Escreve por que o acervo não tem o endereço do contrato ou do imóvel. ESCREVE."""
    _proc(con, iid, AUTUADO, EXIGENCIA, INTIMANDO)
    x = _intimando(con, iid, intimando_id)
    razao = _exigir_texto(motivo, "por que o acervo não traz o endereço")
    banco(con).escrever("UPDATE ri_intimacao_intimandos SET sem_endereco_no_acervo=%s WHERE id=%s",
                        (razao, int(intimando_id)))
    _evento(con, iid, "ACERVO_SEM_ENDERECO", agora, f"{x['nome']}: {razao}", agora=agora, usuario=usuario)


def retirar_intimando(con, iid: int, intimando_id: int, *, motivo: str, agora: str,
                      contagem: str = "CORRIDOS", e_util: Callable[[date], bool] = _dia_util_padrao,
                      usuario: str | None = None) -> None:
    """Tira da lista quem entrou por engano, se ainda não houve diligência. ESCREVE."""
    _proc(con, iid, AUTUADO, EXIGENCIA, INTIMANDO, PRAZO_PURGA)
    x = _intimando(con, iid, intimando_id)
    if x["diligencias"] or x["publicacoes"]:
        raise IntimacaoError("Esta pessoa já tem diligência ou edital: a linha fica, porque é prova.")
    razao = _exigir_texto(motivo, "por que a pessoa sai da lista")
    bd = banco(con)
    bd.escrever("DELETE FROM ri_intimacao_enderecos WHERE intimando_id=%s", (int(intimando_id),))
    bd.escrever("DELETE FROM ri_intimacao_intimandos WHERE id=%s", (int(intimando_id),))
    _evento(con, iid, "INTIMANDO_RETIRADO", agora, f"{x['nome']} saiu da lista: {razao}", agora=agora, usuario=usuario)
    _recalcular(con, iid, contagem=contagem, e_util=e_util)


# ---------------------------------------------------------------- a qualificação


def qualificar(con, iid: int, *, resultado: str, itens: Any = (), motivo: str = "", dia: str, agora: str,
               hoje: date | None = None, usuario: str | None = None) -> dict:
    """POSITIVA, EXIGENCIA ou NEGATIVA. ESCREVE. O demonstrativo não se qualifica (TJMA 722, § 2º)."""
    i = _proc(con, iid, AUTUADO, EXIGENCIA)
    validas = {r["chave"] for r in REQUISITOS}
    marcados = {x for x in itens if x in validas}
    if i["origem"] == CENTRAL_ONR:
        marcados.add("representacao")
    banco(con).escrever("UPDATE ri_intimacoes SET requisitos=%s WHERE id=%s",
                        (json.dumps(sorted(marcados)), int(iid)))
    lista = intimandos_de(con, iid)
    if resultado == "POSITIVA":
        exigidos = validas - ({"pj"} if not any(x["pessoa_juridica"] for x in lista) else set())
        faltam = [r["artigo"] for r in REQUISITOS if r["chave"] in exigidos and r["chave"] not in marcados]
        if faltam:
            raise IntimacaoError("Faltam itens para a qualificação positiva: " + "; ".join(faltam)
                                 + ". Se faltam mesmo, lance a exigência.")
        if not any(x["papel"] in QUEM_DEVE for x in lista):
            raise IntimacaoError("Ponha na lista ao menos o devedor fiduciante (ou o terceiro fiduciante).")
        sem_rep = [x["nome"] for x in lista if x["pessoa_juridica"] and not _texto(x["representante"])]
        if sem_rep:
            raise IntimacaoError("Pessoa jurídica se intima na pessoa do representante legal (TJMA 724, § 4º): "
                                 "informe-o para " + ", ".join(sem_rep) + ".")
        sem = [x["nome"] for x in lista if not x["enderecos"]]
        if sem:
            raise IntimacaoError("Sem endereço para intimar: " + ", ".join(sem) + " (TJMA 722, II).")
        _mudar(con, iid, INTIMANDO)
        banco(con).escrever("UPDATE ri_intimacoes SET exigencia=NULL WHERE id=%s", (int(iid),))
        _evento(con, iid, "QUALIFICADO", dia, "Qualificação positiva: começam as intimações.", agora=agora, usuario=usuario)
    elif resultado == "EXIGENCIA":
        razao = _exigir_texto(motivo, "a exigência ao credor")
        _mudar(con, iid, EXIGENCIA)
        banco(con).escrever("UPDATE ri_intimacoes SET exigencia=%s WHERE id=%s", (razao, int(iid)))
        _evento(con, iid, "EXIGENCIA", dia, f"Exigência ao credor: {razao}", agora=agora, usuario=usuario)
    elif resultado == "NEGATIVA":
        razao = _exigir_texto(motivo, "o fundamento da recusa")
        _mudar(con, iid, RECUSADO)
        banco(con).escrever("UPDATE ri_intimacoes SET encerrado_em=%s, encerrado_motivo=%s WHERE id=%s",
                            (agora, razao, int(iid)))
        _evento(con, iid, "RECUSADO", dia, f"Requerimento recusado: {razao}", agora=agora, usuario=usuario)
        _encerrar_prenotacao(con, i, situacao="RECUSADO", rotulo="Requerimento de intimação fiduciária recusado",
                             agora=agora, usuario=usuario)
    else:
        raise IntimacaoError("Escolha o resultado da qualificação.")
    return {"situacao": um(con, iid)["situacao"]}


# ---------------------------------------------------------------- diligências e edital


def diligencia(con, iid: int, intimando_id: int, *, meio: str, dia: str, resultado: str, agora: str,
               endereco_id: Any = None, hora: str = "", tentativas_carteiro: Any = None,
               quem_recebeu: str = "", detalhe: str = "", rastreio: str = "",
               contagem: str = "CORRIDOS", e_util: Callable[[date], bool] = _dia_util_padrao,
               usuario: str | None = None) -> dict:
    """Uma tentativa de intimar. ESCREVE. TJMA 724; Lei 9.514, art. 26, §§ 3º a 4º-C.

    A positiva marca o intimado e a data; quando todos estão intimados, corre a purga.
    """
    _proc(con, iid, INTIMANDO)
    x = _intimando(con, iid, intimando_id)
    if x["situacao"] in JA_INTIMADO:
        raise IntimacaoError(f"{x['nome']} já está intimado.")
    if x["situacao"] == EDITAL_EM_CURSO:
        raise IntimacaoError(f"O edital de {x['nome']} está em publicação.")
    if meio not in MEIOS:
        raise IntimacaoError("Escolha o meio da intimação.")
    regra = RESULTADOS.get(resultado)
    if not regra or meio not in regra["meios"]:
        raise IntimacaoError("Este resultado não é deste meio de intimação.")
    endereco = next((e for e in x["enderecos"] if _texto(endereco_id) and int(e["id"]) == int(endereco_id)), None)
    if not endereco:
        raise IntimacaoError("Escolha em qual dos endereços cadastrados foi a tentativa.")
    d = _dia(dia, "a data da diligência").isoformat()
    tentativas = int(_texto(tentativas_carteiro) or 0) or None
    if resultado == "AUSENTE_3" and (tentativas or 0) < TENTATIVAS_DO_CARTEIRO:
        raise IntimacaoError("Pelo correio, o ausente só fecha a tentativa depois das 3 do carteiro (TJMA 724, § 2º).")
    anteriores = [y for y in x["diligencias"] if y["meio"] in (PESSOAL, RTD)]
    if resultado == "SUSPEITA_OCULTACAO":
        procuras = sum(1 for y in anteriores if y["resultado"] == "NAO_ENCONTRADO")
        if procuras < PROCURAS_ANTES_DA_HORA_CERTA:
            raise IntimacaoError("A hora certa pede duas procuras sem encontrar a pessoa (art. 26, § 3º-A).")
        _exigir_texto(detalhe, "o motivo da suspeita de ocultação e a hora designada")
    if resultado in ("HORA_CERTA", "PORTARIA"):
        if not any(y["resultado"] == "SUSPEITA_OCULTACAO" for y in anteriores):
            raise IntimacaoError("A intimação com hora certa, ou na portaria, vem depois da suspeita de ocultação "
                                 "registrada (art. 26, §§ 3º-A e 3º-B).")
    if resultado == "LOCAL_IGNORADO":
        _exigir_texto(detalhe, "o que o serventuário certificou")
    if regra["efeito"] == INTIMADO and resultado in ("INTIMADO", "HORA_CERTA", "PORTARIA", "ENTREGUE_MP") \
            and not _texto(quem_recebeu):
        raise IntimacaoError("Diga quem recebeu a intimação.")
    banco(con).escrever(
        """INSERT INTO ri_intimacao_diligencias(intimando_id, endereco_id, endereco, meio, dia, hora, resultado,
               tentativas_carteiro, quem_recebeu, detalhe, rastreio, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (int(intimando_id), int(endereco["id"]), endereco["endereco"], meio, d, _texto(hora), resultado,
         tentativas, _texto(quem_recebeu), _texto(detalhe), _texto(rastreio), agora, usuario))
    texto = f"{x['nome']} — {MEIOS[meio].split(' (')[0]}, em {endereco['endereco']}: {regra['rotulo']}."
    if regra["efeito"] == INTIMADO:
        banco(con).escrever(
            "UPDATE ri_intimacao_intimandos SET situacao=%s, intimado_em=%s, intimado_como=%s WHERE id=%s",
            (INTIMADO, d, meio, int(intimando_id)))
    _evento(con, iid, "DILIGENCIA", d, texto, agora=agora, usuario=usuario)
    _recalcular(con, iid, contagem=contagem, e_util=e_util)
    return {"efeito": regra["efeito"]}


def email_enviado(con, iid: int, intimando_id: int, *, dia: str, agora: str, usuario: str | None = None) -> None:
    """A intimação mandada ao e-mail do contrato, antes do edital (art. 26, § 4º-B). ESCREVE."""
    _proc(con, iid, INTIMANDO)
    x = _intimando(con, iid, intimando_id)
    if not _texto(x["email"]):
        raise IntimacaoError("Esta pessoa não tem e-mail cadastrado.")
    d = _dia(dia).isoformat()
    banco(con).escrever("UPDATE ri_intimacao_intimandos SET email_enviado_em=%s WHERE id=%s", (d, int(intimando_id)))
    _evento(con, iid, "EMAIL", d, f"Intimação enviada a {x['nome']} pelo e-mail {x['email']} (art. 26, § 4º-B).",
            agora=agora, usuario=usuario)


def publicar_edital(con, iid: int, intimando_id: int, *, dia: str, veiculo: str, agora: str,
                    contagem: str = "CORRIDOS", e_util: Callable[[date], bool] = _dia_util_padrao,
                    usuario: str | None = None) -> dict:
    """Uma publicação do edital. ESCREVE. Lei 9.514, art. 26, §§ 4º e 4º-B.

    A primeira só sai quando `faltas_para_o_edital` está vazia e, havendo e-mail no contrato,
    15 dias depois do envio. Na terceira, o intimando conta como intimado na data da última.
    """
    _proc(con, iid, INTIMANDO)
    x = _intimando(con, iid, intimando_id)
    d = _dia(dia, "a data da publicação").isoformat()
    if not _texto(veiculo):
        raise IntimacaoError("Diga em que jornal ou meio o edital saiu.")
    pubs = list(x["publicacoes"])
    if not pubs:
        faltas = faltas_para_o_edital(x)
        if faltas:
            raise IntimacaoError("O edital ainda não cabe: " + " ".join(faltas))
        if _texto(x["email"]):
            if not x["email_enviado_em"]:
                raise IntimacaoError("O contrato traz e-mail: mande a intimação por ele antes do edital (art. 26, § 4º-B).")
            minimo = _dia(x["email_enviado_em"]) + timedelta(days=DIAS_DO_EMAIL_ANTES_DO_EDITAL)
            if _dia(d) < minimo:
                raise IntimacaoError(f"O edital só pode sair a partir de {minimo:%d/%m/%Y}: 15 dias depois do e-mail "
                                     "(art. 26, § 4º-B).")
    elif d in {p["dia"] for p in pubs}:
        raise IntimacaoError("Já há publicação nesta data: o edital pede três dias.")
    elif d < max(p["dia"] for p in pubs):
        raise IntimacaoError("A publicação nova não pode ser anterior à última lançada.")
    pubs.append({"dia": d, "veiculo": _texto(veiculo)})
    pubs.sort(key=lambda p: p["dia"])
    completo = len(pubs) >= PUBLICACOES_DO_EDITAL
    banco(con).escrever(
        """UPDATE ri_intimacao_intimandos SET edital_publicacoes=%s, situacao=%s, intimado_em=%s,
                  intimado_como=%s WHERE id=%s""",
        (json.dumps(pubs, ensure_ascii=False), INTIMADO_EDITAL if completo else EDITAL_EM_CURSO,
         pubs[-1]["dia"] if completo else None, "EDITAL" if completo else None, int(intimando_id)))
    _evento(con, iid, "EDITAL", d,
            f"Edital de {x['nome']}: {len(pubs)}ª publicação, em {_texto(veiculo)}."
            + (" Publicação completa: a purga conta da última (art. 26, § 4º)." if completo else ""),
            agora=agora, usuario=usuario)
    _recalcular(con, iid, contagem=contagem, e_util=e_util)
    return {"publicacoes": len(pubs), "completo": completo}


# ---------------------------------------------------------------- a purga e o encerramento


def purgar(con, iid: int, *, dia: str, valor: Any, forma: str, agora: str, conta: str = "",
           comprovante: str = "", e_util: Callable[[date], bool] = _dia_util_padrao,
           usuario: str | None = None) -> dict:
    """O devedor pagou na serventia. ESCREVE. TJMA 725; Lei 9.514, art. 26, §§ 1º, 5º e 6º.

    Paga-se o que o demonstrativo e a projeção informam (TJMA 725): havendo projeção, o valor não
    pode ser menor que o dela para aquele dia. A transação bancária não se recusa (parágrafo único).
    """
    i = _proc(con, iid, INTIMANDO, PRAZO_PURGA)
    d = _dia(dia, "a data do pagamento").isoformat()
    if i["prazo_ate"] and d > i["prazo_ate"]:
        raise IntimacaoError(f"O prazo da purga terminou em {_dia(i['prazo_ate']):%d/%m/%Y}.")
    if forma not in FORMAS_DA_PURGA:
        raise IntimacaoError("Escolha a forma do pagamento.")
    pago = centavos(valor)
    if not pago or pago <= 0:
        raise IntimacaoError("Informe o valor recebido.")
    esperado = valor_da_projecao(i["projecao_lista"], d)
    if esperado is not None and pago < esperado:
        raise IntimacaoError(f"A projeção do credor manda pagar {reais(esperado)} nesta data, e foram {reais(pago)}. "
                             "A purga é do valor informado (TJMA 725).")
    avisar = somar_uteis(_dia(d), UTEIS_DO_AVISO_AO_CREDOR, e_util)
    banco(con).escrever(
        """UPDATE ri_intimacoes SET purga_dia=%s, purga_centavos=%s, purga_forma=%s, purga_comprovante=%s,
                  purga_conta=%s, credor_avisar_ate=%s WHERE id=%s""",
        (d, pago, forma, _texto(comprovante), _texto(conta), avisar.isoformat(), int(iid)))
    _mudar(con, iid, PURGADA, avisar, "Aviso ao credor da purga (TJMA 725: 3 dias úteis)")
    _evento(con, iid, "PURGA", d,
            f"Mora purgada: {reais(pago)} ({FORMAS_DA_PURGA[forma].split(' (')[0]}). Avisar o credor até "
            f"{avisar:%d/%m/%Y}." + ("" if _texto(conta) else " A conta da purga não está configurada."),
            agora=agora, usuario=usuario)
    return {"avisar_ate": avisar.isoformat()}


def avisar_credor(con, iid: int, *, dia: str, agora: str, usuario: str | None = None) -> None:
    """O credor foi avisado da purga, para retirar ou receber. ESCREVE. Cabe depois da certidão."""
    i = um(con, iid)
    if not i or not i["purga_dia"]:
        raise IntimacaoError("Não há purga lançada neste procedimento.")
    d = _dia(dia).isoformat()
    banco(con).escrever("UPDATE ri_intimacoes SET credor_avisado_em=%s WHERE id=%s", (d, int(iid)))
    if i["situacao"] == PURGADA:
        _mudar(con, iid, PURGADA)
    fora = i["credor_avisar_ate"] and d > i["credor_avisar_ate"]
    _evento(con, iid, "CREDOR_AVISADO", d, "Credor avisado da purga (TJMA 725)."
            + (" Fora dos 3 dias úteis." if fora else ""), agora=agora, usuario=usuario)


def repassar(con, iid: int, *, dia: str, forma: str, valor: Any, agora: str, despesas: Any = None,
             comprovante: str = "", usuario: str | None = None) -> None:
    """O valor saiu para o credor, deduzidas as despesas (art. 26, § 6º). ESCREVE."""
    i = um(con, iid)
    if not i or not i["purga_dia"]:
        raise IntimacaoError("Não há purga lançada neste procedimento.")
    if i["repasse_dia"]:
        raise IntimacaoError("O repasse já está lançado.")
    if forma not in FORMAS_DO_REPASSE:
        raise IntimacaoError("Escolha como o valor chegou ao credor.")
    v = centavos(valor) or 0
    desp = centavos(despesas) or 0
    if v <= 0 or v + desp > int(i["purga_centavos"] or 0):
        raise IntimacaoError("O repasse mais as despesas não pode passar do valor recebido.")
    d = _dia(dia).isoformat()
    banco(con).escrever(
        """UPDATE ri_intimacoes SET repasse_dia=%s, repasse_forma=%s, repasse_centavos=%s,
                  repasse_despesas_centavos=%s, repasse_comprovante=%s,
                  credor_avisado_em=COALESCE(credor_avisado_em, %s) WHERE id=%s""",
        (d, forma, v, desp, _texto(comprovante), d, int(iid)))
    _evento(con, iid, "REPASSE", d, f"Repasse ao credor: {reais(v)}" + (f", deduzidas despesas de {reais(desp)}" if desp else "")
            + f" ({FORMAS_DO_REPASSE[forma].split(' (')[0]}).", agora=agora, usuario=usuario)


def certificar(con, iid: int, *, tipo: str, dia: str, hoje: str, agora: str, sv: dict | None = None,
               usuario: str | None = None) -> dict:
    """A certidão de purgação ou de não purgação. Encerra o procedimento e a prenotação. ESCREVE.

    TJMA 723: os efeitos da prenotação cessam com ela. A não purgação só depois de vencido o
    prazo, sem pagamento. O texto fica congelado: a reimpressão sai igual.
    """
    i = _proc(con, iid, PURGADA, PRAZO_PURGA)
    d = _dia(dia, "a data da certidão").isoformat()
    if tipo == "PURGACAO":
        if i["situacao"] != PURGADA:
            raise IntimacaoError("A certidão de purgação vem depois do pagamento lançado.")
        situacao, rotulo = ENCERRADO_PURGACAO, "Mora purgada: certidão de purgação emitida (TJMA 723)"
    elif tipo == "NAO_PURGACAO":
        if i["situacao"] != PRAZO_PURGA:
            raise IntimacaoError("A certidão de não purgação cabe quando o prazo da purga correu sem pagamento.")
        if not i["prazo_ate"] or hoje[:10] <= i["prazo_ate"] or d <= i["prazo_ate"]:
            raise IntimacaoError(f"O prazo da purga vai até {_dia(i['prazo_ate']):%d/%m/%Y}: a certidão de não "
                                 "purgação só no dia seguinte.")
        situacao, rotulo = ENCERRADO_NAO_PURGACAO, "Mora não purgada: certidão de não purgação emitida (TJMA 723)"
    else:
        raise IntimacaoError("Escolha a certidão: purgação ou não purgação.")
    lista = intimandos_de(con, iid)
    i_para_texto = dict(i, certidao_dia=d)
    paragrafos = texto_da_peca(i_para_texto, "CERTIDAO_" + tipo, lista, sv=sv or {})
    banco(con).escrever(
        """UPDATE ri_intimacoes SET certidao_tipo=%s, certidao_dia=%s, certidao_texto=%s, encerrado_em=%s,
                  encerrado_motivo=%s WHERE id=%s""",
        (tipo, d, json.dumps(paragrafos, ensure_ascii=False), agora, rotulo, int(iid)))
    # O fim da purga fica gravado na não purgação: é dele que conta o habitacional (TJMA 726, § 1º).
    if tipo == "NAO_PURGACAO":
        _mudar(con, iid, situacao, i["prazo_ate"], i["prazo_rotulo"])
    else:
        _mudar(con, iid, situacao)
    _evento(con, iid, "CERTIDAO_" + tipo, d, rotulo + ".", agora=agora, usuario=usuario)
    _encerrar_prenotacao(con, i, situacao="ENCERRADO", rotulo=rotulo, agora=agora, usuario=usuario)
    return {"situacao": situacao}


def encerrar_sem_certidao(con, iid: int, *, motivo: str, texto: str, dia: str, agora: str,
                          usuario: str | None = None) -> None:
    """Desistência do credor ou ordem judicial. Encerra o procedimento e cancela a prenotação. ESCREVE."""
    i = _proc(con, iid)
    if motivo not in (DESISTENCIA, CANCELADO_JUDICIAL):
        raise IntimacaoError("Escolha: desistência do credor ou ordem judicial.")
    razao = _exigir_texto(texto, "o que fundamenta o encerramento")
    if i["situacao"] == PURGADA:
        raise IntimacaoError("Há purga lançada: o procedimento se encerra pela certidão de purgação.")
    banco(con).escrever("UPDATE ri_intimacoes SET encerrado_em=%s, encerrado_motivo=%s WHERE id=%s",
                        (agora, razao, int(iid)))
    _mudar(con, iid, motivo)
    _evento(con, iid, motivo, dia, f"{SITUACOES[motivo]}: {razao}", agora=agora, usuario=usuario)
    _encerrar_prenotacao(con, i, situacao="CANCELADO", rotulo=SITUACOES[motivo], agora=agora, usuario=usuario)


# ---------------------------------------------------------------- o que a tela oferece


def acoes_possiveis(i: dict, *, hoje: str) -> set[str]:
    """A mesma régua que as funções cobram, para a tela não oferecer o que será recusado. Só calcula."""
    s = i["situacao"]
    a: set[str] = set()
    if i.get("purga_dia") and not i.get("repasse_dia"):
        a.add("repassar")
        if not i.get("credor_avisado_em"):
            a.add("avisar_credor")
    if s in TERMINAIS:
        return a
    if s in (AUTUADO, EXIGENCIA):
        a.add("qualificar")
    if s in (AUTUADO, EXIGENCIA, INTIMANDO, PRAZO_PURGA):
        a.add("intimando")
    if s in (AUTUADO, EXIGENCIA, INTIMANDO):
        a.add("endereco")
    if s == INTIMANDO:
        a |= {"diligencia", "edital", "email"}
    if s in (INTIMANDO, PRAZO_PURGA) and not (i.get("prazo_ate") and hoje > i["prazo_ate"]):
        a.add("purgar")
    if s == PURGADA:
        a.add("certidao_purgacao")
    if s == PRAZO_PURGA and i.get("prazo_ate") and hoje > i["prazo_ate"]:
        a.add("certidao_nao_purgacao")
    if s != PURGADA:
        a.add("encerrar")
    return a


def pecas_disponiveis(i: dict, intimandos: list[dict]) -> dict[str, str]:
    saida = {}
    if i["situacao"] not in (AUTUADO, EXIGENCIA, RECUSADO) and intimandos:
        saida["INTIMACAO"] = PECAS["INTIMACAO"]
    if any(x["publicacoes"] or not faltas_para_o_edital(x) for x in intimandos if x["situacao"] not in JA_INTIMADO) \
            or any(x["situacao"] == INTIMADO_EDITAL for x in intimandos):
        saida["EDITAL"] = PECAS["EDITAL"]
    if i.get("purga_dia"):
        saida["RECIBO"] = PECAS["RECIBO"]
    if i.get("certidao_tipo") == "PURGACAO":
        saida["CERTIDAO_PURGACAO"] = PECAS["CERTIDAO_PURGACAO"]
    if i.get("certidao_tipo") == "NAO_PURGACAO":
        saida["CERTIDAO_NAO_PURGACAO"] = PECAS["CERTIDAO_NAO_PURGACAO"]
    return saida


def depois_da_nao_purgacao(i: dict, *, e_util: Callable[[date], bool] = _dia_util_padrao) -> dict | None:
    """Os dois marcos do credor depois da não purgação. Só calcula; a consolidação é título novo.

    · até quando ele pode pedir a consolidação sem repetir o procedimento (TJMA 726, § 2º);
    · no habitacional, desde quando ela pode ser averbada (TJMA 726, § 1º; art. 26-A, § 1º).
    """
    if i.get("certidao_tipo") != "NAO_PURGACAO" or not i.get("certidao_dia"):
        return None
    ate = _dia(i["certidao_dia"]) + timedelta(days=DIAS_PARA_CONSOLIDAR)
    desde = somar_uteis(_dia(i["prazo_ate"]), UTEIS_DO_HABITACIONAL, e_util) if i.get("habitacional") and i.get("prazo_ate") else None
    return {"pedir_ate": ate.isoformat(), "averbar_desde": desde.isoformat() if desde else None}


def painel(con, *, hoje: str, e_util: Callable[[date], bool] = _dia_util_padrao) -> dict:
    """Os procedimentos e os prazos, o vencido primeiro. Só LÊ.

    `abertos`: em andamento. `repasses`: purga sem repasse lançado, aberta ou já certificada.
    `consolidacao`: não purgação dentro dos 120 dias do credor.
    """
    abertos, encerrados, repasses, consolidacao = [], [], [], []
    for r in banco(con).ler("SELECT id FROM ri_intimacoes ORDER BY id DESC"):
        i = um(con, r["id"])
        lista = intimandos_de(con, r["id"])
        i["intimandos_n"] = len(lista)
        i["intimados_n"] = sum(1 for x in lista if x["situacao"] in JA_INTIMADO)
        i["vencido"] = bool(i["prazo_ate"] and i["prazo_ate"] < hoje)
        if i["purga_dia"] and not i["repasse_dia"]:
            repasses.append(i | {"atrasado": bool(i["credor_avisar_ate"] and not i["credor_avisado_em"]
                                                   and i["credor_avisar_ate"] < hoje)})
        marcos = depois_da_nao_purgacao(i, e_util=e_util)
        if marcos and marcos["pedir_ate"] >= hoje:
            consolidacao.append(i | marcos)
        (encerrados if i["situacao"] in TERMINAIS else abertos).append(i)
    abertos.sort(key=lambda x: (not x["vencido"], x["prazo_ate"] or "9999", -int(x["id"])))
    return {"abertos": abertos, "encerrados": encerrados, "repasses": repasses, "consolidacao": consolidacao}


def atos_e_emolumentos(con) -> list[dict]:
    """`ATOS_COBRADOS` com o valor da tabela vigente, quando há. Só LÊ; sem tabela, sem valor."""
    saida = []
    for a in ATOS_COBRADOS:
        linha = dict(a, total="")
        if a["codigo_tj"]:
            try:
                import emolumentos as EMOL
                cod = EMOL.servico_pelo_codigo_tj(con, a["codigo_tj"])
                item = EMOL.calcular_item(con, servico=cod, quantidade=1) if cod is not None else None
                linha["total"] = reais(item["total"]) if item and item.get("total") else ""
            except Exception:  # noqa: BLE001 — sem o caixa, a tela mostra o código sem valor
                linha["total"] = ""
        saida.append(linha)
    return saida


def fases(i: dict, *, intimandos: list[dict], eventos: list[dict]) -> dict:
    """A régua no layout novo, na forma de `notas_fases`. Só calcula."""
    s = i["situacao"]
    ordem = ["requerimento", "intimacoes", "prazo", "encerramento"]
    feito = {
        "requerimento": s not in (AUTUADO, EXIGENCIA),
        "intimacoes": bool(intimandos) and all(x["situacao"] in JA_INTIMADO for x in intimandos),
        "prazo": s in (PURGADA,) + TERMINAIS,
        "encerramento": s in TERMINAIS,
    }
    rotulos = {"requerimento": "Requerimento", "intimacoes": "Intimações", "prazo": "Prazo e purga",
               "encerramento": "Certidão"}
    lista = []
    for n, chave in enumerate(ordem, 1):
        lista.append({"chave": chave, "rotulo": rotulos[chave], "numero": n, "pendencias": 0 if feito[chave] else 1,
                      "estado": "feita" if feito[chave] else "liberada", "aviso": "", "trava": None})
    for k, fase in enumerate(lista):
        fase["voltar"] = {c: lista[k - 1][c] for c in ("chave", "rotulo")} if k else None
        fase["avancar"] = {c: lista[k + 1][c] for c in ("chave", "rotulo")} if k < len(lista) - 1 else None
    inicial = next((f["chave"] for f in lista if f["estado"] != "feita"), "encerramento")
    apoio = [{"chave": "historico", "rotulo": "Linha do tempo", "contagem": len(eventos), "alerta": 0}]
    return {"fases": lista, "apoio": apoio, "foco": inicial, "inicial": inicial}


# ---------------------------------------------------------------- as peças


def _lista_dos_intimados(intimandos: list[dict]) -> str:
    partes = []
    for x in intimandos:
        if x["situacao"] in JA_INTIMADO:
            como = "por edital" if x["intimado_como"] == "EDITAL" else MEIOS.get(x["intimado_como"], "").split(" (")[0].lower()
            partes.append(f"{x['nome']} ({x['papel_rotulo'].lower()}), {como}, em {_dia(x['intimado_em']):%d/%m/%Y}")
    return "; ".join(partes)


def texto_da_peca(i: dict, qual: str, intimandos: list[dict], *, sv: dict, intimando: dict | None = None,
                  conta: str = "") -> list[str]:
    """Os parágrafos da peça. Só calcula. A certidão já emitida sai do texto congelado."""
    if qual.startswith("CERTIDAO_") and i.get("certidao_texto"):
        congelado = _json(i["certidao_texto"], None)
        if congelado:
            return congelado
    oficial = _texto(sv.get("serventia_titular")) or "o Oficial"
    prenot = f"prenotado sob o n. {i.get('protocolo_numero')} em {_dia(i['data_prenotacao']):%d/%m/%Y}" \
        if i.get("data_prenotacao") else "prenotado nesta serventia"
    base = (f"o requerimento de intimação do credor fiduciário {i['credor_nome']}"
            + (f", contrato {i['contrato']}" if _texto(i.get("contrato")) else "")
            + f", {prenot}, relativo ao imóvel da matrícula n. {i.get('matricula_numero')}")
    if qual == "INTIMACAO" and intimando:
        quem = intimando["nome"] + (f", na pessoa de seu representante legal {intimando['representante']}"
                                    if intimando.get("pessoa_juridica") and intimando.get("representante") else "")
        valores = ""
        if i.get("demonstrativo_centavos"):
            valores = f" O débito informado pelo credor é de {reais(i['demonstrativo_centavos'])}"
            valores += f", em {_dia(i['demonstrativo_data']):%d/%m/%Y}." if i.get("demonstrativo_data") else "."
        proj = "; ".join(f"até {_dia(p['vencimento']):%d/%m/%Y}, {reais(p['centavos'])}" for p in i.get("projecao_lista", []))
        return [
            f"Fica INTIMADO(A) {quem}, na qualidade de {intimando['papel_rotulo'].lower()}, nos termos do art. 26 da "
            f"Lei 9.514/1997, em razão de {base}.",
            "Deverá satisfazer, no prazo de 15 (quinze) dias, a prestação vencida e as que vencerem até a data do "
            "pagamento, os juros convencionais, as penalidades e os demais encargos contratuais, os encargos legais, "
            "inclusive os tributos, as contribuições condominiais imputáveis ao imóvel e as despesas de cobrança e "
            "de intimação (art. 26, § 1º)." + valores,
            ("Valores atualizados informados pelo credor para o pagamento: " + proj + ".") if proj else "",
            "Havendo mais de um intimado, o prazo conta da intimação do último (Código de Normas do TJMA, art. 723, "
            "§ 1º). O pagamento se faz nesta serventia" + (f": {conta}." if _texto(conta) else "."),
            "Fica cientificado(a) de que, se a mora não for purgada no prazo legal, a propriedade será consolidada no "
            "patrimônio do credor e o imóvel será levado a leilão, nos termos dos arts. 26-A, 27 e 27-A da Lei "
            "9.514/1997 (art. 26, § 3º).",
        ]
    if qual == "EDITAL" and intimando:
        return [
            f"{oficial}, na forma do art. 26, § 4º, da Lei 9.514/1997, faz saber a {intimando['nome']}, que se encontra "
            f"em local ignorado, incerto ou inacessível, que tramita nesta serventia {base}.",
            "Fica INTIMADO(A) a satisfazer, no prazo de 15 (quinze) dias contados da última publicação deste edital, "
            "a prestação vencida e as que vencerem até a data do pagamento, com os encargos do art. 26, § 1º, sob pena "
            "de consolidação da propriedade no patrimônio do credor e de leilão do imóvel (art. 26, § 3º).",
            "Este edital é publicado por três dias, no mínimo (art. 26, § 4º).",
        ]
    if qual == "RECIBO":
        return [
            f"Recebi a importância de {reais(i.get('purga_centavos'))}, em {_dia(i['purga_dia']):%d/%m/%Y}, "
            f"para a purgação da mora no {base}.",
            "O valor fica à disposição do credor fiduciário, que será avisado em até 3 (três) dias úteis (Código de "
            "Normas do TJMA, art. 725), deduzidas as despesas de cobrança e de intimação (Lei 9.514, art. 26, § 6º). "
            "Purgada a mora, convalesce o contrato de alienação fiduciária (art. 26, § 5º).",
        ]
    lista = _lista_dos_intimados(intimandos) or "—"
    if qual == "CERTIDAO_PURGACAO":
        return [
            f"CERTIFICO que, em {base}, foram intimados: {lista}.",
            f"CERTIFICO que a mora foi purgada em {_dia(i['purga_dia']):%d/%m/%Y}, com o pagamento de "
            f"{reais(i.get('purga_centavos'))}, convalescendo o contrato de alienação fiduciária (Lei 9.514, art. 26, § 5º).",
            "Com esta certidão conclui-se o procedimento de intimação e cessam os efeitos da prenotação (Código de "
            "Normas do TJMA, art. 723).",
        ]
    if qual == "CERTIDAO_NAO_PURGACAO":
        return [
            f"CERTIFICO que, em {base}, foram intimados: {lista}.",
            f"CERTIFICO que o prazo de 15 (quinze) dias para a purgação da mora, contado da intimação do último "
            f"intimado (Código de Normas do TJMA, art. 723, § 1º), terminou em {_dia(i['prazo_ate']):%d/%m/%Y}, "
            "sem que a mora fosse purgada nesta serventia.",
            "Esta certidão instrui o requerimento de averbação da consolidação da propriedade em nome do fiduciário, "
            "com a prova do pagamento do imposto de transmissão e, se for o caso, do laudêmio (Lei 9.514, art. 26, "
            "§ 7º; Código de Normas do TJMA, art. 726). Não apresentados esses documentos em até 120 (cento e vinte) "
            "dias corridos desta certidão, a consolidação dependerá de novo procedimento (art. 726, § 2º).",
            "Com esta certidão conclui-se o procedimento de intimação e cessam os efeitos da prenotação (art. 723).",
        ]
    raise IntimacaoError("Esta peça não existe.")


# ---------------------------------------------------------------- a Central (I2 chama; aqui só se traduz)

_PAPEL_DA_PARTICIPACAO = (
    (r"C[OÔ]NJ|COMPANHEIR", "CONJUGE"), (r"AVAL", "AVALISTA"), (r"FIAD", "FIADOR"),
    (r"PROPRIET", "PROPRIETARIO"), (r"TERCEIR", "TERCEIRO_FIDUCIANTE"), (r"CESSION", "CESSIONARIO"),
)


def papel_da_participacao(participacao: Any) -> str:
    texto = _texto(participacao).upper()
    for padrao, papel in _PAPEL_DA_PARTICIPACAO:
        if re.search(padrao, texto):
            return papel
    return DEVEDOR


def _lista(v: Any, chave: str) -> list[dict]:
    """A lista de um `ArrayOf…` como o leitor SOAP a devolver: lista solta ou {chave: [..]}."""
    if not v:
        return []
    if isinstance(v, dict):
        v = v.get(chave, list(v.values())[0] if v else [])
    if isinstance(v, dict):
        v = [v]
    return [dict(x) for x in v or []]


def da_central(resp: dict) -> dict:
    """Traduz o `GetDetalhesIN_V3` do WSOficio (`intimacoes.asmx`) para o modelo daqui. Só calcula.

    Os nomes dos campos são os do contrato público, lido em 24/11/2026. Nada aqui fala com a
    Central: a I2 lê o pedido e entrega o dicionário a esta função.
    """
    valores = lambda arr, k: sorted(  # noqa: E731
        ({"vencimento": _dia(x.get("DataVencimento")).isoformat(), "centavos": centavos(x.get("Valor"))}
         for x in _lista(arr, k) if _texto(x.get("DataVencimento"))), key=lambda y: y["vencimento"])
    enderecos: dict[str, list[str]] = {}
    for e in _lista(resp.get("EnderecosIntimacoes"), "GetDetalhesIN_EnderecoIntimacao_WSResp"):
        enderecos.setdefault(_texto(e.get("NomeDevedor")).casefold(), []).append(_texto(e.get("EnderecoCompleto")))
    devedores = _lista(resp.get("Devedores"), "GetDetalhesIN_Devedor_v2_WSResp") or \
        _lista(resp.get("Devedores"), "GetDetalhesIN_Devedor_WSResp")
    intimandos = []
    for dv in devedores:
        doc = _digitos(dv.get("CPFCNPJ"))
        intimandos.append({
            "nome": _texto(dv.get("Nome")), "documento": doc, "papel": papel_da_participacao(dv.get("Participacao")),
            "participacao": _texto(dv.get("Participacao")), "email": _texto(dv.get("Email")),
            "pessoa_juridica": len(doc) == 14,
            "enderecos": [x for x in enderecos.get(_texto(dv.get("Nome")).casefold(), []) if x]})
    credor_contato = " ".join(x for x in (_texto(resp.get("CredorEmail")),
                                          _texto(resp.get("CredorDDD")) + _texto(resp.get("CredorTelefone"))) if x)
    projecao = valores(resp.get("Purgas"), "GetDetalhesIN_Purga_WSResp")
    prestacoes = valores(resp.get("PrestacoesVencidas"), "GetDetalhesIN_PrestacaoVencida_WSResp")
    return {
        "requerimento": {
            "origem": CENTRAL_ONR, "protocolo_central": _texto(resp.get("Protocolo")),
            "data_remessa": _dia_ou_nada(resp.get("DataRemessa")), "contrato": _texto(resp.get("NumeroContrato")),
            "credor_nome": _texto(resp.get("Credor")), "credor_documento": _digitos(resp.get("CredorCPFCNPJ")),
            "credor_contato": credor_contato, "solicitante_nome": _texto(resp.get("Solicitante")),
            "solicitante_documento": _digitos(resp.get("SolicitanteCPFCNPJ")),
            "avalistas_a_pedido": any(x["papel"] in SO_A_PEDIDO for x in intimandos),
            "prestacoes": prestacoes, "projecao": projecao,
            "dados_central": {"IDPedido": resp.get("IDPedido"), "IDStatus": resp.get("IDStatus"),
                              "Boletos": _lista(resp.get("Boletos"), "GetDetalhesIN_Boleto_WSResp"),
                              "Reingressos": _lista(resp.get("Reingressos"), "GetDetalhesIN_Reingresso_WSResp"),
                              "Prenotacoes": _lista(resp.get("Prenotacoes"), "GetDetalhesIN_Prenotacao_WSResp"),
                              "TipoCobranca": resp.get("TipoCobranca")},
        },
        "matriculas": [_texto(x.get("Matricula")) for x in _lista(resp.get("Imoveis"), "GetDetalhesIN_Imovel_WSResp")],
        "intimandos": intimandos,
    }


def autuar_da_central(con, *, protocolo_id: int, resp: dict, ano: int, agora: str, hoje: date,
                      matricula_id: Any = None, usuario: str | None = None) -> dict:
    """Autua o pedido da Central e põe os devedores na lista. ESCREVE. É o que a I2 vai chamar."""
    traduzido = da_central(resp)
    numero = ""
    if not matricula_id:
        p = banco(con).um("SELECT matricula_id FROM ri_protocolos WHERE id=%s", (int(protocolo_id or 0),))
        if p and not p["matricula_id"] and traduzido["matriculas"]:
            numero = traduzido["matriculas"][0]
    feito = autuar(con, protocolo_id=protocolo_id, ano=ano, agora=agora, hoje=hoje, matricula_id=matricula_id,
                   matricula_numero=numero, usuario=usuario, **traduzido["requerimento"])
    for x in traduzido["intimandos"]:
        adicionar_intimando(con, feito["id"], agora=agora, usuario=usuario, **x)
    return feito
