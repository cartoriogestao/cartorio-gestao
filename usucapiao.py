"""
Usucapião extrajudicial — o rito, o que falta e o relatório para qualificação.

O QUE ESTE MODULO RESPONDE
    Tres perguntas, e sao as que o balcao faz todo dia sobre um processo que
    leva meses:

      onde ele esta?          `etapa`
      o que falta?            `etapas_faltantes()` e `conferir()`
      o que faco agora?       `proximos_passos()`

    E uma quarta: **o que eu mando para fora, quando quero um parecer
    sobre a qualificacao?** — `montar_dossie()` exporta o processo inteiro em
    texto, e o parecer que volta entra por `registrar_analise()`.

    **QUEM LE O RELATORIO NAO IMPORTA AO MODULO** — decisao do oficial em
    30/08/2026: «tratar apenas como forma de exportacao e importacao de
    relatorio para qualificacao». Pode ser um advogado, uma assessoria, outra
    serventia ou uma ferramenta. A peca e o RELATORIO, e nao quem o le.

O RELATORIO AUXILIA, E NAO DECIDE. ISSO ESTA NO ESQUEMA, E NAO SO NO TEXTO
    `us_analises` nao tem campo de sentido nem de registro: ela guarda
    parecer e achados. Quem decide e o oficial, em `us_decisoes`, e a decisao
    aponta para a analise que leu — nunca o contrario.

    `registrar_analise()` grava `conferida_por_humano = 0`, e `decidir()`
    RECUSA fechar o processo apoiado em analise que ninguem conferiu. Nao e
    desconfianca da maquina: e que a decisao do registrador e ato dele, e ato
    de delegatario nao se delega a uma ferramenta.

O DOSSIE E TEXTO, E NAO ARQUIVO
    `montar_dossie()` devolve o processo inteiro em texto — dados, pecas com
    teor, movimentos, prazos e o checklist. Nao manda PDF: o que se le e revisa
    bem e
    texto, e o PDF ja esta em disco para quem quiser abrir.

    Ele tambem NAO MANDA o que nao precisa sair: o dossie mascara CPF e CNPJ
    das partes por padrao, como todo papel que deixa esta casa. Quem precisa
    do documento inteiro pede `mascarar=False`, e a escolha fica registrada.

FUNDAMENTO
    Lei 6.015/1973, art. 216-A.
    Codigo de Normas do Foro Extrajudicial do Maranhao — Provimento TJMA n. 28,
        de 23/04/2026, arts. 747 a 761.
    Provimento CNJ n. 65/2017.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from serventia import mascarar_documento


class UsucapiaoError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcao."""


# As cinco do acervo (`tb_natureza_ata_notarial_usucapiao`) — sao os nomes que
# o TJMA reconhece na ata notarial, e nao uma lista minha.
MODALIDADES: dict[str, str] = {
    "ORDINARIA": "Ordinária",
    "EXTRAORDINARIA": "Extraordinária",
    "ESPECIAL_RURAL": "Especial Rural",
    "ESPECIAL_URBANA": "Especial Urbana",
    "ESPECIAL_FAMILIAR": "Especial Familiar",
}

# O rito, em ordem. Cada etapa so se alcanca depois da anterior — e
# `avancar()` recusa pular, porque pular etapa em usucapiao e o que faz o
# registro nascer nulo.
ETAPAS: tuple[tuple[str, str], ...] = (
    ("AUTUACAO", "Autuação — requerimento e ata notarial recebidos"),
    ("CONFERENCIA", "Conferência dos documentos de entrada"),
    ("NOTIFICACAO", "Notificação dos titulares e confrontantes"),
    ("CIENCIA_ENTES", "Ciência à União, ao Estado e ao Município"),
    ("EDITAL", "Edital para terceiros interessados"),
    ("DILIGENCIA", "Diligências e esclarecimentos"),
    ("CONCLUSAO", "Conclusos ao oficial"),
    ("DECISAO", "Decisão do oficial"),
    ("REGISTRO", "Registro do reconhecimento"),
)

ORDEM_DAS_ETAPAS: dict[str, int] = {e: i for i, (e, _) in enumerate(ETAPAS)}
NOME_DA_ETAPA: dict[str, str] = dict(ETAPAS)

SITUACOES: tuple[str, ...] = (
    "EM_ANDAMENTO", "SUSPENSO", "REGISTRADO", "REJEITADO", "REMETIDO_AO_JUIZO",
)

# Onde o processo para, e nao continua andando.
SITUACOES_FINAIS: tuple[str, ...] = ("REGISTRADO", "REJEITADO",
                                     "REMETIDO_AO_JUIZO")

TIPOS_DE_PECA: dict[str, str] = {
    "REQUERIMENTO": "Requerimento do interessado",
    "ATA_NOTARIAL": "Ata notarial do tabelião",
    "PLANTA": "Planta do imóvel",
    "MEMORIAL": "Memorial descritivo",
    "ART_RRT": "ART ou RRT do profissional",
    "ANUENCIA": "Anuência de titular ou confrontante",
    "CERTIDAO_NEGATIVA": "Certidão negativa de distribuidor",
    "JUSTO_TITULO": "Justo título ou prova da origem da posse",
    "PROVA_POSSE": "Prova do tempo e da natureza da posse",
    "JUSTIFICACAO_OBICE": "Justificação do óbice à escrituração "
                          "(Código TJMA, art. 748)",
    "COMPROVANTE_NOTIFICACAO": "Comprovante de notificação",
    "EDITAL_PUBLICADO": "Edital publicado",
    "IMPUGNACAO": "Impugnação",
    "PROCURACAO": "Procuração",
    "OUTRO": "Outro documento",
}

TIPOS_DE_MOVIMENTO: dict[str, str] = {
    "AUTUACAO": "Autuação",
    "JUNTADA": "Juntada de documento",
    "NOTIFICACAO": "Notificação expedida",
    "CIENCIA": "Ciência a ente público",
    "EDITAL": "Edital publicado",
    "RESPOSTA": "Resposta recebida",
    "IMPUGNACAO": "Impugnação apresentada",
    "EXIGENCIA": "Exigência formulada",
    "DILIGENCIA": "Diligência",
    "CONCLUSAO": "Conclusos ao oficial",
    "DECISAO": "Decisão",
    # A CHAVE FICA `ANALISE_IA`, E O ROTULO MUDOU — 30/08/2026.
    #
    #   O oficial pediu para tirar as referencias a IA e tratar isto como
    #   exportacao e importacao de relatorio para qualificacao. **A chave e
    #   valor GRAVADO em `us_movimentos.tipo`**: troca-la faria os movimentos ja
    #   lancados apontarem para um tipo que nao existe mais, e eles sumiriam da
    #   tela sem ninguem ver. Renomeia-se a etiqueta; a chave fica como legado.
    "ANALISE_IA": "Relatório de qualificação",
    "SUSPENSAO": "Suspensão",
    "OUTRO": "Outro",
}

# As respostas possiveis a uma notificacao. O SILENCIO e resposta: no rito do
# art. 216-A ele tem efeito, e por isso e um valor e nao a ausencia de um.
RESPOSTAS: dict[str, str] = {
    "ANUIU": "Anuiu",
    "IMPUGNOU": "Impugnou",
    "SILENCIO": "Silêncio — decorreu o prazo sem manifestação",
}

SENTIDOS: dict[str, str] = {
    "PROCEDENTE": "Procedente — reconhece a usucapião e determina o registro",
    "IMPROCEDENTE": "Improcedente — rejeita o pedido, com fundamento",
    "EXIGENCIA": "Baixa em exigência — o pedido volta ao interessado",
    "REMESSA_JUIZO": "Remessa ao juízo competente — houve impugnação",
}


# ---------------------------------------------------------- o checklist
#
# Cada item e uma exigencia do rito. `peca` liga o item ao tipo de documento
# que o cumpre — e e o que deixa `conferir()` marcar sozinho o que ja foi
# juntado, sem ninguem clicar.
#
# `so_se` limita o item a certas modalidades: a especial urbana e a familiar
# tem limite de area e exigem que o requerente nao tenha outro imovel, o que
# nao se pede na extraordinaria.

CHECKLIST: tuple[dict, ...] = (
    {"item": "REQUERIMENTO", "peca": "REQUERIMENTO",
     "rotulo": "Requerimento assinado pelo interessado",
     "base": "LRP, art. 216-A, caput"},
    {"item": "ATA_NOTARIAL", "peca": "ATA_NOTARIAL",
     "rotulo": "Ata notarial do tabelião, com o tempo de posse",
     "base": "LRP, art. 216-A, caput e I"},
    {"item": "PLANTA", "peca": "PLANTA",
     "rotulo": "Planta do imóvel",
     "base": "LRP, art. 216-A, II"},
    {"item": "MEMORIAL", "peca": "MEMORIAL",
     "rotulo": "Memorial descritivo",
     "base": "LRP, art. 216-A, II"},
    {"item": "ART_RRT", "peca": "ART_RRT",
     "rotulo": "ART ou RRT do profissional habilitado",
     "base": "LRP, art. 216-A, II"},
    {"item": "ANUENCIAS", "peca": "ANUENCIA",
     "rotulo": "Anuência dos titulares e confrontantes na planta",
     "base": "LRP, art. 216-A, II e § 2º",
     "nota": "sem a anuência na planta, o rito exige notificação"},
    {"item": "CERTIDOES", "peca": "CERTIDAO_NEGATIVA",
     "rotulo": "Certidões negativas dos distribuidores",
     "base": "LRP, art. 216-A, III",
     "nota": "dispensáveis quando não se consegue a qualificação pessoal dos "
             "titulares — basta a pesquisa online pelo nome, impressa "
             "(Código TJMA, art. 751)"},
    {"item": "JUSTO_TITULO", "peca": "JUSTO_TITULO",
     "rotulo": "Justo título ou prova da origem da posse",
     "base": "LRP, art. 216-A, IV"},
    {"item": "PROVA_POSSE", "peca": "PROVA_POSSE",
     "rotulo": "Prova do tempo, da natureza e da continuidade da posse",
     "base": "LRP, art. 216-A, IV"},
    {"item": "AREA_LIMITE", "peca": None,
     "rotulo": "Área dentro do limite legal da modalidade",
     "base": "CF, arts. 183 e 191",
     "so_se": ("ESPECIAL_URBANA", "ESPECIAL_RURAL", "ESPECIAL_FAMILIAR"),
     "nota": "urbana até 250 m²; rural até 50 ha — conferir na planta"},
    {"item": "NAO_PROPRIETARIO", "peca": None,
     "rotulo": "Requerente não é proprietário de outro imóvel",
     "base": "CF, arts. 183 e 191",
     "so_se": ("ESPECIAL_URBANA", "ESPECIAL_RURAL", "ESPECIAL_FAMILIAR")},
    {"item": "PRENOTACAO", "peca": None,
     "rotulo": "Prenotação do requerimento",
     "base": "Código TJMA, art. 747"},

    # ------------------- O QUE O CODIGO DE NORMAS DO TJMA ACRESCENTA
    #
    # Lido no PDF que esta na casa — `Codigo de normas TJMA atualizado.pdf`,
    # Secao XIV, arts. 747 a 760 —, a pedido do oficial em 28/08/2026: «o
    # cadastramento e muito simples e nao parece ser maduro para processar um
    # usucapiao no RI com confianca».
    #
    # A CITACAO ANTIGA — «arts. 747 a 761» — ESTAVA CERTA, e eu quase a
    # «corrigi» para 760. A Secao XV comeca no 762, de modo que o 761 e de
    # usucapiao mesmo: e o imovel edificado. O que faltava nao era acertar a
    # faixa: era o CONTEUDO dela chegar ao balcao, artigo por artigo. Ele mora
    # em `us_tjma.py`, com o texto de cada um ao lado da regra.
    {"item": "JUSTIFICACAO_OBICE", "peca": "JUSTIFICACAO_OBICE",
     "rotulo": "Justificação do óbice à escrituração, com o alerta ao "
               "requerente e às testemunhas",
     "base": "Código TJMA, art. 748",
     "nota": "é a pergunta que separa a usucapião da compra e venda que "
             "ninguém quis registrar para não pagar ITBI — sem ela o cartório "
             "vira o caminho barato da transmissão"},
    {"item": "PLANTA_CONTEUDO", "peca": None,
     "rotulo": "A planta traz perímetro, configuração geométrica, coordenadas "
               "UTM SIRGAS 2000 e a identificação de cada confrontante",
     "base": "Código TJMA, art. 753",
     "nota": "é aqui que o pedido volta em exigência depois de semanas"},
    {"item": "AREA_CONTRA_MATRICULA", "peca": None,
     "rotulo": "Respondido o que a área usucapida tem a ver com a da matrícula "
               "— igual, maior, menor, ou sem matrícula",
     "base": "Código TJMA, art. 753, §§ 2º a 4º",
     "nota": "cada resposta leva o registro a um lugar diferente; perguntar na "
             "entrada evita a diligência do terceiro mês"},
    {"item": "NAO_E_GARANTIA_SFH", "peca": None,
     "rotulo": "O imóvel não é objeto de garantia no Sistema Financeiro da "
               "Habitação",
     "base": "Código TJMA, art. 749",
     "nota": "é a única vedação absoluta da Seção: não é caso de exigência "
             "nem de diligência"},
)

ITENS_DO_CHECKLIST: dict[str, dict] = {c["item"]: c for c in CHECKLIST}

# Quem tem de tomar ciencia, e e por isso que sao tres e nao um.
ENTES_PUBLICOS: tuple[str, ...] = ("UNIAO", "ESTADO", "MUNICIPIO")


def checklist_da_modalidade(modalidade: str) -> tuple[dict, ...]:
    """Os itens que valem para aquela modalidade. So calcula."""
    m = _modalidade(modalidade)
    return tuple(c for c in CHECKLIST
                 if "so_se" not in c or m in c["so_se"])


# ------------------------------------------------------------ utilidades


def _modalidade(valor: Any) -> str:
    m = str(valor or "").strip().upper()
    if m not in MODALIDADES:
        raise UsucapiaoError(
            f"Modalidade {valor!r} não existe. As do acervo são: "
            f"{', '.join(MODALIDADES)}.")
    return m


def _texto(v: Any) -> str | None:
    s = str(v or "").strip()
    return s or None


def processo(con: sqlite3.Connection, processo_id: int) -> sqlite3.Row | None:
    """O processo, ou None. So LE."""
    return con.execute("SELECT * FROM us_processos WHERE id=?",
                       (int(processo_id),)).fetchone()


def _exigir(con: sqlite3.Connection, processo_id: int) -> sqlite3.Row:
    p = processo(con, processo_id)
    if not p:
        raise UsucapiaoError(f"Processo {processo_id} não encontrado.")
    return p


def pecas(con: sqlite3.Connection, processo_id: int) -> list[sqlite3.Row]:
    """As peças juntadas, na ordem em que entraram. So LE."""
    return list(con.execute(
        "SELECT * FROM us_pecas WHERE processo_id=? ORDER BY id",
        (int(processo_id),)))


def movimentos(con: sqlite3.Connection, processo_id: int) -> list[sqlite3.Row]:
    """O andamento, em ordem. So LE."""
    return list(con.execute(
        """SELECT * FROM us_movimentos WHERE processo_id=?
            ORDER BY data_movimento, id""", (int(processo_id),)))


def decisoes(con: sqlite3.Connection, processo_id: int) -> list[sqlite3.Row]:
    """As decisões, da mais nova para a mais velha. So LE."""
    return list(con.execute(
        "SELECT * FROM us_decisoes WHERE processo_id=? ORDER BY id DESC",
        (int(processo_id),)))


def analises(con: sqlite3.Connection, processo_id: int) -> list[sqlite3.Row]:
    """As análises recebidas, da mais nova para a mais velha. So LE."""
    return list(con.execute(
        "SELECT * FROM us_analises WHERE processo_id=? ORDER BY id DESC",
        (int(processo_id),)))


# ------------------------------------------------------------- autuação


def autuar(con: sqlite3.Connection, *, numero: str, modalidade: str,
           agora: str, requerente_nome: str | None = None,
           requerente_documento: str | None = None,
           imovel_descricao: str | None = None,
           imovel_municipio: str | None = None,
           usuario: str | None = None, **campos: Any) -> int:
    """Autua o processo. ESCREVE. Devolve o id.

    O numero e da CASA, e nao do Tribunal: usucapiao extrajudicial nao tem
    numero unico nacional. Repetir numero e recusado pelo UNIQUE.

    Nasce em AUTUACAO com o checklist da modalidade ja montado, todo
    pendente — assim a tela mostra o que falta desde o primeiro dia, em vez de
    mostrar vazio ate alguem clicar.
    """
    m = _modalidade(modalidade)
    num = _texto(numero)
    if not num:
        raise UsucapiaoError("O processo precisa de um número.")
    if con.execute("SELECT 1 FROM us_processos WHERE numero=?",
                   (num,)).fetchone():
        raise UsucapiaoError(f"Já existe processo com o número {num}.")

    aceitos = ("ano", "advogado_nome", "advogado_oab", "matricula_id",
               "imovel_area", "imovel_endereco", "imovel_uf", "valor_centavos",
               "prenotacao", "protocolo_id", "ata_notarial_livro",
               "ata_notarial_folha", "ata_notarial_data",
               "ata_notarial_cartorio", "posse_inicio", "posse_tempo_alegado",
               "observacao")
    extra = {k: campos.get(k) for k in aceitos if campos.get(k) is not None}
    colunas = ["numero", "modalidade", "etapa", "situacao", "requerente_nome",
               "requerente_documento", "imovel_descricao", "imovel_municipio",
               "criado_em", "criado_por", *extra]
    valores = [num, m, "AUTUACAO", "EM_ANDAMENTO", _texto(requerente_nome),
               _texto(requerente_documento), _texto(imovel_descricao),
               _texto(imovel_municipio), agora, usuario, *extra.values()]
    cur = con.execute(
        f"INSERT INTO us_processos({', '.join(colunas)}) "
        f"VALUES ({', '.join('?' * len(colunas))})", valores)
    processo_id = int(cur.lastrowid)

    for item in checklist_da_modalidade(m):
        con.execute(
            """INSERT INTO us_conferencia(processo_id, item, estado,
                   atualizado_em, atualizado_por)
               VALUES (?,?, 'PENDENTE', ?, ?)""",
            (processo_id, item["item"], agora, usuario))
    _mover(con, processo_id, tipo="AUTUACAO", etapa="AUTUACAO",
           descricao=f"Autuado o processo {num}, modalidade {MODALIDADES[m]}.",
           data_movimento=agora, agora=agora, usuario=usuario)
    return processo_id


def _mover(con: sqlite3.Connection, processo_id: int, *, tipo: str,
           descricao: str, data_movimento: str, agora: str,
           etapa: str | None = None, usuario: str | None = None,
           **campos: Any) -> int:
    """Grava um movimento. ESCREVE. Uso interno e das funcoes do modulo."""
    if tipo not in TIPOS_DE_MOVIMENTO:
        raise UsucapiaoError(
            f"Tipo de movimento desconhecido: {tipo!r}. Os que existem: "
            f"{', '.join(TIPOS_DE_MOVIMENTO)}.")
    # OS CAMPOS QUE O MOVIMENTO ACEITA.
    #
    #   **ESTA LISTA JA DIVERGIU DO BANCO NOUTRO MODULO**, e custou caro: o
    #   `INSERT` de `rc_pessoas` listava colunas a mao, e `documento_orgao` e
    #   `idade_no_fato` existiam na tabela e na tela e **nunca eram salvas**.
    #   Por isso ha teste que compara esta lista com as colunas reais de
    #   `us_movimentos`: coluna nova que nasca sem entrar aqui fica vermelha
    #   la, em vez de sumir calada.
    aceitos = ("destinatario", "destinatario_papel", "prazo_dias",
               "prazo_inicio", "prazo_fim", "prazo_uteis", "respondido_em",
               "resposta", "resposta_teor",
               # Os da notificacao como ATO PRATICADO — relato #30.
               "endereco", "forma", "tentativa", "resultado_da_entrega",
               "entregue_em", "teor_expedido")
    extra = {k: campos[k] for k in aceitos if campos.get(k) is not None}
    colunas = ["processo_id", "tipo", "etapa", "descricao", "data_movimento",
               "criado_em", "criado_por", *extra]
    valores = [int(processo_id), tipo, etapa, descricao, data_movimento,
               agora, usuario, *extra.values()]
    cur = con.execute(
        f"INSERT INTO us_movimentos({', '.join(colunas)}) "
        f"VALUES ({', '.join('?' * len(colunas))})", valores)
    con.execute("UPDATE us_processos SET atualizado_em=? WHERE id=?",
                (agora, int(processo_id)))
    return int(cur.lastrowid)


def movimentar(con: sqlite3.Connection, processo_id: int, *, tipo: str,
               descricao: str, agora: str, data_movimento: str | None = None,
               usuario: str | None = None, **campos: Any) -> int:
    """Lança um movimento no processo. ESCREVE.

    Recusa movimentar processo em situacao final: processo registrado ou
    rejeitado nao anda mais, e movimento nele seria andar depois do fim.
    """
    p = _exigir(con, processo_id)
    if p["situacao"] in SITUACOES_FINAIS:
        raise UsucapiaoError(
            f"O processo está {p['situacao']} — não há mais o que movimentar.")
    if not _texto(descricao):
        raise UsucapiaoError("Descreva o movimento.")
    return _mover(con, processo_id, tipo=tipo, descricao=descricao,
                  data_movimento=data_movimento or agora, agora=agora,
                  etapa=p["etapa"], usuario=usuario, **campos)


def notificar(con: sqlite3.Connection, processo_id: int, *, destinatario: str,
              destinatario_papel: str, endereco: str, forma: str,
              prazo_chave: str, agora: str, serventia: dict,
              hoje_extenso: str = "", tentativa: Any = None,
              data_movimento: str | None = None,
              usuario: str | None = None) -> dict:
    """Expede uma notificação: confere, monta o papel e lança o movimento.

    Relato #30 do oficial. ESCREVE.

    **O PAPEL É CONFERIDO ANTES DE O MOVIMENTO EXISTIR.** Se `us_notificacao`
    recusar — falta endereço, forma que não é da norma —, nada é gravado: um
    movimento de notificação sem papel que a sustente é uma linha dizendo que a
    serventia notificou alguém sem ter notificado.

    **E O TEOR EXPEDIDO FICA GUARDADO.** Remontá-lo depois traria o processo
    como ele está hoje, e não como estava quando o papel saiu — e o que o
    notificado leu é o de então. É a mesma regra do termo do Registro Civil e
    da certidão de protesto: o que a casa entregou congela.
    """
    import us_notificacao as UN

    p = _exigir(con, processo_id)
    if p["situacao"] in SITUACOES_FINAIS:
        raise UsucapiaoError(
            f"O processo está {p['situacao']} — não há mais o que notificar.")

    regra = UN.prazo(prazo_chave)
    dados = {"destinatario": destinatario,
             "destinatario_papel": destinatario_papel,
             "endereco": endereco, "forma": forma,
             "prazo_dias": regra["dias"], "prazo_chave": prazo_chave}

    teor = UN.montar(processo=dict(p), notificacao=dados,
                     serventia=serventia, hoje_extenso=hoje_extenso)

    forma_rotulo = UN.FORMA_POR_CHAVE.get(
        str(forma).upper(), {}).get("o_que", forma)
    mov = _mover(
        con, processo_id, tipo="NOTIFICACAO",
        descricao=f"Notificação de {destinatario} ({destinatario_papel}), "
                  f"por: {forma_rotulo}.",
        data_movimento=data_movimento or agora, agora=agora, etapa=p["etapa"],
        usuario=usuario, destinatario=destinatario,
        destinatario_papel=destinatario_papel, endereco=endereco,
        forma=str(forma).upper(), tentativa=tentativa,
        prazo_dias=regra["dias"], prazo_uteis=1 if regra["uteis"] else 0,
        teor_expedido=teor)
    return {"movimento_id": mov, "teor": teor, "prazo": regra}


def publicar_edital(con: sqlite3.Connection, processo_id: int, *, agora: str,
                    serventia: dict, hoje_extenso: str = "",
                    imovel_sem_origem: bool = False,
                    disponibilizado_em: str | None = None,
                    usuario: str | None = None) -> dict:
    """Monta o edital e lança o movimento. ESCREVE.

    **O TEOR FICA GUARDADO**, como na notificação: o edital que se publicou é o
    de então, e remontá-lo depois traria o processo como está hoje.

    **A DATA DA DISPONIBILIZAÇÃO É DE QUEM PUBLICA**, e não a de hoje: quem
    publica na Central recebe dela a data, e é dessa data que saem os dois
    saltos do art. 755, § 1º. Supor «hoje» faria o prazo começar no dia errado.
    """
    import us_notificacao as UN

    p = _exigir(con, processo_id)
    if p["situacao"] in SITUACOES_FINAIS:
        raise UsucapiaoError(
            f"O processo está {p['situacao']} — não há mais o que publicar.")

    teor = UN.montar_edital(processo=dict(p), serventia=serventia,
                            hoje_extenso=hoje_extenso,
                            imovel_sem_origem=imovel_sem_origem)
    mov = _mover(
        con, processo_id, tipo="EDITAL",
        descricao="Edital para terceiros interessados"
                  + (" — imóvel sem origem registrária consignada"
                     if imovel_sem_origem else "") + ".",
        data_movimento=_texto(disponibilizado_em) or agora, agora=agora,
        etapa=p["etapa"], usuario=usuario,
        prazo_dias=UN.PRAZO_DO_EDITAL["dias"], prazo_uteis=0,
        teor_expedido=teor)
    return {"movimento_id": mov, "teor": teor}


def dar_ciencia_aos_entes(con: sqlite3.Connection, processo_id: int, *,
                          agora: str, serventia: dict, hoje_extenso: str = "",
                          usuario: str | None = None) -> list[dict]:
    """Monta os três ofícios e lança um movimento por ente. ESCREVE.

    **SÃO TRÊS, E OS TRÊS DE UMA VEZ** — art. 216-A, § 3º. Deixar escolher qual
    seria abrir a porta para avisar dois: o vício de faltar um só aparece quando
    o que faltou reclamar, depois de o registro estar feito.
    """
    import us_notificacao as UN

    p = _exigir(con, processo_id)
    if p["situacao"] in SITUACOES_FINAIS:
        raise UsucapiaoError(
            f"O processo está {p['situacao']} — não há mais o que comunicar.")

    saida = []
    for ente in UN.ENTES:
        teor = UN.montar_oficio_ao_ente(ente=ente, processo=dict(p),
                                        serventia=serventia,
                                        hoje_extenso=hoje_extenso)
        mov = _mover(
            con, processo_id, tipo="CIENCIA",
            descricao=f"Ciência a: {ente} (art. 216-A, § 3º).",
            data_movimento=agora, agora=agora, etapa=p["etapa"],
            usuario=usuario, destinatario=ente,
            destinatario_papel="Ente público",
            prazo_dias=UN.PRAZO_DOS_ENTES["dias"], prazo_uteis=0,
            teor_expedido=teor)
        saida.append({"ente": ente, "movimento_id": mov, "teor": teor})
    return saida


# ------------------------------------------------------------- as peças


def juntar_peca(con: sqlite3.Connection, processo_id: int, *, tipo: str,
                agora: str, descricao: str | None = None,
                nome_arquivo: str | None = None, caminho: str | None = None,
                sha256: str | None = None, bytes_: int | None = None,
                paginas: int | None = None, teor: str | None = None,
                usuario: str | None = None) -> int:
    """Junta um documento aos autos. ESCREVE. Devolve o id da peça.

    Juntar peça mexe no checklist: o item que aquele tipo de peça cumpre passa
    a CUMPRIDO sozinho. Fazer o escrevente juntar e depois marcar a mesma coisa
    à mão é o jeito de as duas divergirem.
    """
    p = _exigir(con, processo_id)
    if tipo not in TIPOS_DE_PECA:
        raise UsucapiaoError(
            f"Tipo de peça desconhecido: {tipo!r}. Os que existem: "
            f"{', '.join(TIPOS_DE_PECA)}.")
    cur = con.execute(
        """INSERT INTO us_pecas(processo_id, tipo, descricao, nome_arquivo,
               caminho, sha256, bytes, paginas, teor, juntada_em, juntada_por)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (int(processo_id), tipo, _texto(descricao), _texto(nome_arquivo),
         _texto(caminho), _texto(sha256), bytes_, paginas, _texto(teor),
         agora, usuario))
    peca_id = int(cur.lastrowid)

    for item in checklist_da_modalidade(p["modalidade"]):
        if item.get("peca") == tipo:
            con.execute(
                """UPDATE us_conferencia SET estado='CUMPRIDO',
                       atualizado_em=?, atualizado_por=?
                    WHERE processo_id=? AND item=? AND estado='PENDENTE'""",
                (agora, usuario, int(processo_id), item["item"]))
    _mover(con, processo_id, tipo="JUNTADA", etapa=p["etapa"],
           descricao=f"Juntada de {TIPOS_DE_PECA[tipo]}"
                     + (f": {_texto(descricao)}" if _texto(descricao) else "."),
           data_movimento=agora, agora=agora, usuario=usuario)
    return peca_id


# --------------------------------------------------------- a conferência


def conferir(con: sqlite3.Connection, processo_id: int) -> dict:
    """O checklist do processo, item a item, com o que falta. So LE.

    Devolve `pendentes`, `cumpridos` e `dispensados` — e `pronto_para_decidir`,
    que e o que a tela usa para deixar (ou nao) chamar a decisao.
    """
    p = _exigir(con, processo_id)
    gravados = {r["item"]: r for r in con.execute(
        "SELECT * FROM us_conferencia WHERE processo_id=?", (int(processo_id),))}
    linhas = []
    for item in checklist_da_modalidade(p["modalidade"]):
        g = gravados.get(item["item"])
        linhas.append({
            **item,
            "estado": g["estado"] if g else "PENDENTE",
            "motivo": g["motivo"] if g else None,
            "anotacao": g["anotacao"] if g else None,
        })
    pendentes = [x for x in linhas if x["estado"] == "PENDENTE"]
    return {
        "processo_id": int(processo_id),
        "modalidade": p["modalidade"],
        "itens": linhas,
        "pendentes": pendentes,
        "cumpridos": [x for x in linhas if x["estado"] == "CUMPRIDO"],
        "dispensados": [x for x in linhas if x["estado"] == "DISPENSADO"],
        "pronto_para_decidir": not pendentes,
    }


def marcar_item(con: sqlite3.Connection, processo_id: int, item: str, *,
                estado: str, agora: str, motivo: str | None = None,
                anotacao: str | None = None,
                usuario: str | None = None) -> None:
    """Marca um item do checklist. ESCREVE.

    DISPENSAR EXIGE MOTIVO ESCRITO, e isso nao e formalidade: dispensar item
    do rito e decisao do oficial, e decisao sem motivo e o que a inspecao
    aponta. Recusar aqui e mais barato que explicar depois.
    """
    _exigir(con, processo_id)
    if item not in ITENS_DO_CHECKLIST:
        raise UsucapiaoError(f"Item de conferência desconhecido: {item!r}.")
    if estado not in ("PENDENTE", "CUMPRIDO", "DISPENSADO"):
        raise UsucapiaoError(
            f"Estado inválido: {estado!r}. Use PENDENTE, CUMPRIDO ou DISPENSADO.")
    if estado == "DISPENSADO" and len(_texto(motivo) or "") < 10:
        raise UsucapiaoError(
            "Dispensar item do rito exige motivo escrito, com pelo menos dez "
            "letras — ele fica nos autos e é o que a inspeção lê.")
    con.execute(
        """INSERT INTO us_conferencia(processo_id, item, estado, motivo,
               anotacao, atualizado_em, atualizado_por)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(processo_id, item) DO UPDATE SET
               estado=excluded.estado, motivo=excluded.motivo,
               anotacao=excluded.anotacao,
               atualizado_em=excluded.atualizado_em,
               atualizado_por=excluded.atualizado_por""",
        (int(processo_id), item, estado, _texto(motivo), _texto(anotacao),
         agora, usuario))


# ---------------------------------------------- onde está e o que falta


def etapas_faltantes(con: sqlite3.Connection, processo_id: int) -> list[dict]:
    """As etapas que ainda nao aconteceram, na ordem. So LE."""
    p = _exigir(con, processo_id)
    atual = ORDEM_DAS_ETAPAS.get(p["etapa"], 0)
    return [{"etapa": e, "nome": nome, "ordem": i}
            for i, (e, nome) in enumerate(ETAPAS) if i > atual]


def prazos_abertos(con: sqlite3.Connection, processo_id: int,
                   hoje: str) -> list[dict]:
    """Os prazos que correm e ainda nao foram respondidos. So LE.

    `vencido` compara texto de data ISO, que ordena igual a data — e evita
    trazer `datetime` para um modulo que so precisa comparar.
    """
    saida = []
    for m in con.execute(
            """SELECT * FROM us_movimentos
                WHERE processo_id=? AND prazo_fim IS NOT NULL
                  AND respondido_em IS NULL
                ORDER BY prazo_fim""", (int(processo_id),)):
        saida.append({
            "movimento_id": m["id"], "tipo": m["tipo"],
            "destinatario": m["destinatario"],
            "papel": m["destinatario_papel"],
            "prazo_fim": m["prazo_fim"],
            "vencido": bool(m["prazo_fim"] and m["prazo_fim"] < hoje),
        })
    return saida


def proximos_passos(con: sqlite3.Connection, processo_id: int,
                    hoje: str) -> list[dict]:
    """O que fazer agora, em frases de balcao. So LE.

    E a resposta a pergunta que o escrevente faz olhando os autos: "e agora?".
    Cada passo diz o que e, por que, e quao urgente — `urgencia` serve para a
    tela ordenar, e nao para decidir por ninguem.
    """
    p = _exigir(con, processo_id)
    passos: list[dict] = []

    if p["situacao"] in SITUACOES_FINAIS:
        return [{"passo": f"Nada a fazer: o processo está {p['situacao']}.",
                 "porque": "Processo em situação final não anda mais.",
                 "urgencia": 0}]
    if p["situacao"] == "SUSPENSO":
        passos.append({
            "passo": "Retomar ou encerrar a suspensão.",
            "porque": "Enquanto suspenso, nenhum prazo do rito avança.",
            "urgencia": 2})

    vencidos = [x for x in prazos_abertos(con, processo_id, hoje) if x["vencido"]]
    for v in vencidos:
        passos.append({
            "passo": f"Certificar o decurso do prazo de {v['destinatario'] or v['tipo']}.",
            "porque": (f"O prazo venceu em {v['prazo_fim']} e ninguém respondeu. "
                       f"No rito do art. 216-A o silêncio tem efeito, mas ele "
                       f"precisa estar certificado nos autos."),
            "urgencia": 3, "movimento_id": v["movimento_id"]})

    conf = conferir(con, processo_id)
    for item in conf["pendentes"]:
        passos.append({
            "passo": f"Obter: {item['rotulo']}.",
            "porque": f"{item['base']}."
                      + (f" {item['nota']}." if item.get("nota") else ""),
            "urgencia": 2, "item": item["item"]})

    # O passo da etapa em que ele esta — o que aquela etapa pede para fechar.
    etapa = p["etapa"]
    if etapa == "AUTUACAO" and conf["cumpridos"]:
        passos.append({
            "passo": "Passar à conferência dos documentos.",
            "porque": "Já há peça juntada; a etapa de autuação cumpriu o seu papel.",
            "urgencia": 1})
    elif etapa == "CONFERENCIA" and conf["pronto_para_decidir"]:
        passos.append({
            "passo": "Notificar titulares e confrontantes que não anuíram.",
            "porque": "LRP, art. 216-A, § 2º — sem anuência na planta, notifica-se.",
            "urgencia": 2})
    elif etapa == "NOTIFICACAO":
        feitos = {m["destinatario_papel"] for m in movimentos(con, processo_id)
                  if m["tipo"] == "CIENCIA"}
        faltam = [e for e in ENTES_PUBLICOS if e not in feitos]
        if faltam:
            passos.append({
                "passo": f"Dar ciência a: {', '.join(faltam)}.",
                "porque": ("LRP, art. 216-A, § 3º — os três entes têm de ser "
                           "cientificados, e a falta de um só vicia o rito."),
                "urgencia": 2})
    elif etapa == "CIENCIA_ENTES":
        passos.append({
            "passo": "Publicar o edital para terceiros interessados.",
            "porque": "LRP, art. 216-A, § 4º.",
            "urgencia": 2})
    elif etapa in ("EDITAL", "DILIGENCIA") and not vencidos:
        passos.append({
            "passo": "Concluir os autos ao oficial.",
            "porque": "Cumpridas as fases, o processo vai à decisão.",
            "urgencia": 1})
    elif etapa == "CONCLUSAO":
        passos.append({
            "passo": "Decidir.",
            "porque": "Os autos estão conclusos; falta a decisão fundamentada.",
            "urgencia": 3})
    elif etapa == "DECISAO":
        passos.append({
            "passo": "Registrar o reconhecimento.",
            "porque": "Há decisão procedente e o registro ainda não foi feito.",
            "urgencia": 3})

    impugnou = [m for m in movimentos(con, processo_id)
                if m["resposta"] == "IMPUGNOU"]
    if impugnou and p["situacao"] == "EM_ANDAMENTO":
        passos.append({
            "passo": "Remeter os autos ao juízo competente.",
            "porque": ("Houve impugnação. O art. 216-A, § 10, manda remeter — "
                       "o oficial não julga impugnação."),
            "urgencia": 3})

    passos.sort(key=lambda x: -x["urgencia"])
    return passos


def avancar(con: sqlite3.Connection, processo_id: int, *, etapa: str,
            agora: str, usuario: str | None = None) -> str:
    """Move o processo para a etapa seguinte. ESCREVE.

    RECUSA PULAR ETAPA. No usucapiao extrajudicial cada fase existe para
    proteger alguem — o confrontante, o ente publico, o terceiro do edital —,
    e registro feito com fase pulada nasce nulo. Voltar atras e permitido:
    diligencia nova pode devolver o processo a uma fase anterior.
    """
    p = _exigir(con, processo_id)
    if etapa not in ORDEM_DAS_ETAPAS:
        raise UsucapiaoError(
            f"Etapa desconhecida: {etapa!r}. As do rito: "
            f"{', '.join(e for e, _ in ETAPAS)}.")
    if p["situacao"] in SITUACOES_FINAIS:
        raise UsucapiaoError(
            f"O processo está {p['situacao']} — não muda mais de etapa.")
    atual, novo = ORDEM_DAS_ETAPAS[p["etapa"]], ORDEM_DAS_ETAPAS[etapa]
    if novo > atual + 1:
        pulada = ETAPAS[atual + 1]
        raise UsucapiaoError(
            f"Não dá para pular a etapa «{pulada[1]}». Cada fase do rito "
            f"protege alguém, e registro com fase pulada nasce nulo.")
    con.execute("UPDATE us_processos SET etapa=?, atualizado_em=? WHERE id=?",
                (etapa, agora, int(processo_id)))
    _mover(con, processo_id, tipo="OUTRO", etapa=etapa,
           descricao=(f"Etapa alterada de «{NOME_DA_ETAPA[p['etapa']]}» para "
                      f"«{NOME_DA_ETAPA[etapa]}»."),
           data_movimento=agora, agora=agora, usuario=usuario)
    return etapa


# --------------------------------- o relatório para qualificação


def montar_dossie(con: sqlite3.Connection, processo_id: int, *, hoje: str,
                  mascarar: bool = True) -> dict:
    """O processo inteiro em texto, para mandar a quem vai opinar. So LE.

    **QUEM LE NAO IMPORTA AO MODULO** — advogado, assessoria, outra serventia
    ou ferramenta. O que sai e um relatorio do processo para qualificacao, e o
    que volta e um parecer que entra POR CONFERIR.

    Devolve `{"texto": ..., "sha256": ..., "pecas": n}`. O texto e o que se
    cola na conversa; o sha256 identifica o que foi mandado, para a analise
    que voltar poder ser conferida contra ele.

    MASCARA POR PADRAO. CPF e CNPJ saem mascarados, como todo papel que deixa
    esta casa — e um dossie que vai para fora e papel que deixa a casa, mesmo
    que o destino seja uma ferramenta. Quem precisa do documento inteiro pede
    `mascarar=False`, e a escolha aparece no cabecalho do proprio dossie, para
    quem receber saber o que tem em maos.

    NAO MANDA PDF. O que se le e revisa bem e texto; o PDF continua em disco
    para
    quem quiser abrir. O que vai e o TEOR das pecas, quando alguem o digitou
    ou extraiu.
    """
    p = _exigir(con, processo_id)
    conf = conferir(con, processo_id)

    def doc(v: Any) -> str:
        s = _texto(v) or "—"
        return mascarar_documento(s) if (mascarar and s != "—") else s

    linhas: list[str] = []
    add = linhas.append
    add(f"# Usucapião extrajudicial — processo {p['numero']}")
    add("")
    add(f"- Modalidade: {MODALIDADES.get(p['modalidade'], p['modalidade'])}")
    add(f"- Etapa: {NOME_DA_ETAPA.get(p['etapa'], p['etapa'])}")
    add(f"- Situação: {p['situacao']}")
    add(f"- Requerente: {_texto(p['requerente_nome']) or '—'} "
        f"({doc(p['requerente_documento'])})")
    if _texto(p["advogado_nome"]):
        add(f"- Advogado: {p['advogado_nome']} (OAB {p['advogado_oab'] or '—'})")
    add("")
    add("## O imóvel")
    add(f"- Descrição: {_texto(p['imovel_descricao']) or '—'}")
    add(f"- Área: {_texto(p['imovel_area']) or '—'}")
    add(f"- Endereço: {_texto(p['imovel_endereco']) or '—'}")
    add(f"- Município: {_texto(p['imovel_municipio']) or '—'}"
        f"/{_texto(p['imovel_uf']) or '—'}")
    add(f"- Matrícula: {p['matricula_id'] or 'sem matrícula'}")
    add("")
    add("## A posse alegada")
    add(f"- Início: {_texto(p['posse_inicio']) or '—'}")
    add(f"- Tempo alegado: {_texto(p['posse_tempo_alegado']) or '—'}")
    add(f"- Ata notarial: livro {_texto(p['ata_notarial_livro']) or '—'}, "
        f"folha {_texto(p['ata_notarial_folha']) or '—'}, "
        f"de {_texto(p['ata_notarial_data']) or '—'}, "
        f"{_texto(p['ata_notarial_cartorio']) or '—'}")
    add("")

    todas = pecas(con, processo_id)
    add(f"## Peças juntadas ({len(todas)})")
    for i, peca in enumerate(todas, 1):
        add(f"### {i}. {TIPOS_DE_PECA.get(peca['tipo'], peca['tipo'])}")
        if _texto(peca["descricao"]):
            add(f"- {peca['descricao']}")
        add(f"- Juntada em {peca['juntada_em']}"
            + (f", {peca['paginas']} página(s)" if peca["paginas"] else ""))
        if _texto(peca["teor"]):
            add("")
            add("```")
            add(peca["teor"].strip())
            add("```")
        else:
            add("- *(sem teor em texto — o arquivo está em disco)*")
        add("")

    add("## Andamento")
    for m in movimentos(con, processo_id):
        prazo = ""
        if m["prazo_fim"]:
            estado = ("respondido" if m["respondido_em"]
                      else ("VENCIDO" if m["prazo_fim"] < hoje else "em curso"))
            prazo = f" [prazo até {m['prazo_fim']}: {estado}]"
        alvo = f" — {m['destinatario']}" if _texto(m["destinatario"]) else ""
        add(f"- {m['data_movimento']}: "
            f"{TIPOS_DE_MOVIMENTO.get(m['tipo'], m['tipo'])}{alvo}. "
            f"{m['descricao']}{prazo}")
        if _texto(m["resposta"]):
            add(f"  - Resposta: {RESPOSTAS.get(m['resposta'], m['resposta'])}")
            if _texto(m["resposta_teor"]):
                add(f"    {m['resposta_teor']}")
    add("")

    add("## Conferência do rito")
    for item in conf["itens"]:
        marca = {"CUMPRIDO": "[x]", "DISPENSADO": "[~]"}.get(item["estado"], "[ ]")
        extra = ""
        if item["estado"] == "DISPENSADO":
            extra = f" — dispensado: {item['motivo']}"
        add(f"- {marca} {item['rotulo']} ({item['base']}){extra}")
    add("")

    add("## O que falta")
    faltantes = etapas_faltantes(con, processo_id)
    if faltantes:
        add("Etapas do rito ainda não percorridas:")
        for e in faltantes:
            add(f"- {e['nome']}")
    else:
        add("Todas as etapas do rito foram percorridas.")
    add("")
    for passo in proximos_passos(con, processo_id, hoje):
        add(f"- {passo['passo']} ({passo['porque']})")
    add("")

    add("---")
    add("")
    add("## O que se pede a quem analisar")
    add("")
    add("1. Aponte documento **faltante ou insuficiente** para a modalidade, "
        "citando o dispositivo.")
    add("2. Aponte **contradição entre peças** — área, confrontação, nome, "
        "datas, tempo de posse.")
    add("3. Diga se o **tempo de posse alegado** basta para a modalidade, e o "
        "que nos autos o comprova.")
    add("4. Aponte o que **impediria o registro** se a decisão fosse hoje.")
    add("5. Separe o que é **exigência** do que é mera **observação**.")
    add("")
    add("> Não redija a decisão nem conclua pelo deferimento: a decisão é do "
        "oficial registrador, e o que se pede aqui é a análise que a informa.")
    add("")
    add(f"*Dossiê gerado em {hoje}. "
        f"{'Documentos mascarados.' if mascarar else 'ATENÇÃO: documentos NÃO mascarados.'}*")

    texto = "\n".join(linhas)
    return {
        "processo_id": int(processo_id),
        "numero": p["numero"],
        "texto": texto,
        "sha256": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
        "pecas": len(todas),
        "mascarado": bool(mascarar),
    }


def registrar_analise(con: sqlite3.Connection, processo_id: int, *,
                      parecer: str, agora: str, ferramenta: str | None = None,
                      dossie_sha256: str | None = None,
                      dossie_pecas: int | None = None,
                      achados: list | None = None,
                      usuario: str | None = None,
                      observacao: str | None = None) -> int:
    """Guarda o parecer que voltou. ESCREVE. Devolve o id.

    Entra com `conferida_por_humano = 0`. Enquanto ninguem conferir, `decidir()`
    recusa fechar o processo apoiado nela — ver o cabecalho do modulo.
    """
    _exigir(con, processo_id)
    texto = _texto(parecer)
    if not texto:
        raise UsucapiaoError("O parecer veio vazio — não há o que guardar.")
    cur = con.execute(
        """INSERT INTO us_analises(processo_id, origem, ferramenta,
               dossie_sha256, dossie_pecas, parecer, achados_json,
               recebida_em, recebida_por, observacao)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (int(processo_id), "IA_EXTERNA", _texto(ferramenta), dossie_sha256,
         dossie_pecas, texto,
         json.dumps(achados, ensure_ascii=False) if achados else None,
         agora, usuario, _texto(observacao)))
    analise_id = int(cur.lastrowid)
    _mover(con, processo_id, tipo="ANALISE_IA",
           descricao=(f"Parecer recebido de "
                      f"{_texto(ferramenta) or 'origem não informada'} "
                      f"e juntada aos autos. Aguarda conferência do oficial."),
           data_movimento=agora, agora=agora, usuario=usuario)
    return analise_id


def conferir_analise(con: sqlite3.Connection, analise_id: int, *, agora: str,
                     usuario: str | None = None,
                     observacao: str | None = None) -> None:
    """O oficial diz que leu a análise. ESCREVE.

    E o que destrava a decisao apoiada nela. Conferir nao e concordar: e ter
    lido, e assumir o que se faz com aquilo.
    """
    linha = con.execute("SELECT * FROM us_analises WHERE id=?",
                        (int(analise_id),)).fetchone()
    if not linha:
        raise UsucapiaoError(f"Análise {analise_id} não encontrada.")
    con.execute(
        """UPDATE us_analises SET conferida_por_humano=1, conferida_em=?,
               observacao=COALESCE(?, observacao) WHERE id=?""",
        (agora, _texto(observacao), int(analise_id)))
    _mover(con, int(linha["processo_id"]), tipo="OUTRO",
           descricao="O oficial conferiu o parecer.",
           data_movimento=agora, agora=agora, usuario=usuario)


# -------------------------------------------------------------- a decisão


def modelos_de_decisao(p: sqlite3.Row | dict, sv: dict) -> dict[str, str]:
    """Os modelos de decisao, com o processo ja preenchido. So calcula.

    Sao MODELOS e nao textos prontos: o fundamento de cada caso e do oficial, e
    o modelo deixa isso explicito com o trecho que ele tem de completar.
    """
    numero = p["numero"]
    modalidade = MODALIDADES.get(p["modalidade"], p["modalidade"])
    requerente = _texto(p["requerente_nome"]) or "o requerente"
    imovel = _texto(p["imovel_descricao"]) or "o imóvel descrito nos autos"
    cidade = sv.get("ri_cidade", "")
    uf = sv.get("ri_uf", "")
    titular = sv.get("serventia_titular", "")
    titulo = sv.get("serventia_titulo", "")
    fecho = (f"{cidade}-{uf}, nesta data. {titular} — {titulo}.")

    return {
        "PROCEDENTE": (
            f"DECISÃO. Processo de usucapião extrajudicial n. {numero}, "
            f"modalidade {modalidade}, requerido por {requerente}, tendo por "
            f"objeto {imovel}.\n\n"
            f"Os autos vieram instruídos com a ata notarial, a planta e o "
            f"memorial descritivo assinados por profissional habilitado, as "
            f"certidões e a prova da posse, na forma do art. 216-A da Lei "
            f"6.015/1973.\n\n"
            f"Os titulares de direitos registrados e os confrontantes foram "
            f"cientificados; a União, o Estado e o Município tomaram ciência; "
            f"o edital foi publicado, e decorreram os prazos sem impugnação.\n\n"
            f"[COMPLETAR: o que dos autos comprova o tempo e a natureza da "
            f"posse, e por que a modalidade invocada é a cabível.]\n\n"
            f"Do exposto, RECONHEÇO a usucapião e DETERMINO o registro da "
            f"aquisição em nome de {requerente}, procedendo-se à abertura de "
            f"matrícula, se for o caso.\n\n{fecho}"),
        "IMPROCEDENTE": (
            f"DECISÃO. Processo de usucapião extrajudicial n. {numero}, "
            f"requerido por {requerente}.\n\n"
            f"[COMPLETAR: o que dos autos impede o reconhecimento, com o "
            f"dispositivo. Fundamento genérico não serve — a parte tem direito "
            f"de saber o que exatamente faltou.]\n\n"
            f"Do exposto, INDEFIRO o pedido de reconhecimento extrajudicial da "
            f"usucapião, ressalvada a via judicial e a renovação do pedido uma "
            f"vez suprido o que aqui se apontou.\n\n{fecho}"),
        "EXIGENCIA": (
            f"NOTA DE EXIGÊNCIA. Processo de usucapião extrajudicial n. "
            f"{numero}, requerido por {requerente}.\n\n"
            f"Para o prosseguimento, cumpre satisfazer:\n\n"
            f"[COMPLETAR: uma exigência por item, com o dispositivo de cada "
            f"uma, e dizendo o que satisfaz cada uma.]\n\n"
            f"O processo aguarda o cumprimento, mantida a prenotação nos termos "
            f"do Código de Normas.\n\n{fecho}"),
        "REMESSA_JUIZO": (
            f"DECISÃO. Processo de usucapião extrajudicial n. {numero}, "
            f"requerido por {requerente}.\n\n"
            f"Houve impugnação [COMPLETAR: de quem, e em que data]. Nos termos "
            f"do art. 216-A, § 10, da Lei 6.015/1973, o oficial não julga a "
            f"impugnação: os autos são remetidos ao juízo competente.\n\n"
            f"REMETAM-SE os autos ao Juízo da Comarca, dando-se ciência ao "
            f"requerente.\n\n{fecho}"),
    }


def decidir(con: sqlite3.Connection, processo_id: int, *, sentido: str,
            fundamento: str, teor: str, agora: str, modelo: str | None = None,
            analise_id: int | None = None,
            usuario: str | None = None) -> int:
    """Lavra a decisão do oficial. ESCREVE. Devolve o id.

    TRES TRAVAS, e cada uma existe por um motivo:

    1. **Fundamento escrito.** Decisao sem fundamento e o que a inspecao
       aponta, e no usucapiao ela desfaz o registro.
    2. **Nada pendente no checklist** para decidir PROCEDENTE. Reconhecer
       usucapiao com item do rito em aberto e fazer nascer registro nulo — e o
       item pode ser dispensado, com motivo, o que e diferente de ignorado.
    3. **Parecer conferido.** Se a decisao aponta para um parecer, ele
       tem de ter sido lida por gente. A decisao e ato do delegatario, e ato de
       delegatario nao se delega a ferramenta.
    """
    p = _exigir(con, processo_id)
    if sentido not in SENTIDOS:
        raise UsucapiaoError(
            f"Sentido de decisão desconhecido: {sentido!r}. Os que existem: "
            f"{', '.join(SENTIDOS)}.")
    if p["situacao"] in SITUACOES_FINAIS:
        raise UsucapiaoError(
            f"O processo está {p['situacao']} — já foi decidido.")
    if len(_texto(fundamento) or "") < 20:
        raise UsucapiaoError(
            "Escreva o fundamento da decisão. Decisão de usucapião sem "
            "fundamento não se sustenta, e é o que desfaz o registro depois.")
    if not _texto(teor):
        raise UsucapiaoError("A decisão precisa do teor que sai impresso.")

    if sentido == "PROCEDENTE":
        conf = conferir(con, processo_id)
        if conf["pendentes"]:
            faltam = ", ".join(x["rotulo"] for x in conf["pendentes"][:4])
            raise UsucapiaoError(
                f"Não dá para reconhecer a usucapião com {len(conf['pendentes'])} "
                f"item(ns) do rito pendente(s): {faltam}. Cumpra ou dispense "
                f"com motivo — dispensar é decisão, ignorar não é.")

    if analise_id is not None:
        a = con.execute("SELECT * FROM us_analises WHERE id=? AND processo_id=?",
                        (int(analise_id), int(processo_id))).fetchone()
        if not a:
            raise UsucapiaoError(
                f"A análise {analise_id} não é deste processo.")
        if not a["conferida_por_humano"]:
            raise UsucapiaoError(
                "Esta análise ainda não foi conferida. A decisão é ato do "
                "oficial: confira a análise antes de decidir apoiado nela.")

    cur = con.execute(
        """INSERT INTO us_decisoes(processo_id, sentido, modelo, fundamento,
               teor, decidida_em, decidida_por)
           VALUES (?,?,?,?,?,?,?)""",
        (int(processo_id), sentido, _texto(modelo), _texto(fundamento),
         _texto(teor), agora, usuario))
    decisao_id = int(cur.lastrowid)

    nova_situacao = {"PROCEDENTE": "EM_ANDAMENTO",     # falta registrar
                     "IMPROCEDENTE": "REJEITADO",
                     "EXIGENCIA": "EM_ANDAMENTO",
                     "REMESSA_JUIZO": "REMETIDO_AO_JUIZO"}[sentido]
    nova_etapa = "DECISAO" if sentido == "PROCEDENTE" else p["etapa"]
    con.execute(
        "UPDATE us_processos SET situacao=?, etapa=?, atualizado_em=? WHERE id=?",
        (nova_situacao, nova_etapa, agora, int(processo_id)))
    _mover(con, processo_id, tipo="DECISAO", etapa=nova_etapa,
           descricao=f"Decisão: {SENTIDOS[sentido]}",
           data_movimento=agora, agora=agora, usuario=usuario)
    return decisao_id


def registrar_reconhecimento(con: sqlite3.Connection, processo_id: int, *,
                             ato_id: int, agora: str, selo: str | None = None,
                             usuario: str | None = None) -> None:
    """Amarra o registro feito à decisão que o determinou. ESCREVE.

    Só depois disto o processo fica REGISTRADO. Antes, uma decisão procedente
    deixa o processo em andamento — decidir não é registrar.
    """
    _exigir(con, processo_id)          # só para recusar processo que não existe
    ultima = con.execute(
        """SELECT * FROM us_decisoes WHERE processo_id=?
            ORDER BY id DESC LIMIT 1""", (int(processo_id),)).fetchone()
    if not ultima or ultima["sentido"] != "PROCEDENTE":
        raise UsucapiaoError(
            "Só se registra depois de decisão procedente. A última decisão "
            "deste processo não é procedente.")
    # O ATO TEM DE EXISTIR, e a conferencia e aqui.
    #
    # Sem ela o INSERT bate na chave estrangeira e sobe `IntegrityError` —
    # HTTP 500 na cara do escrevente, no fim de um processo de meses. Quem
    # achou isto foi o teste de TELA: o de dominio rodava com a trava de FK
    # desligada, e passava.
    if not con.execute("SELECT 1 FROM ri_atos WHERE id=?",
                       (int(ato_id),)).fetchone():
        raise UsucapiaoError(
            f"Não existe ato {ato_id} no Registro de Imóveis. Lavre o registro "
            f"na matrícula primeiro, e depois informe aqui o número do ato — é "
            f"ele que amarra o processo ao que ficou na ficha.")
    con.execute("UPDATE us_decisoes SET ato_id=?, selo=? WHERE id=?",
                (int(ato_id), _texto(selo), int(ultima["id"])))
    con.execute(
        """UPDATE us_processos SET situacao='REGISTRADO', etapa='REGISTRO',
               encerrado_em=?, atualizado_em=? WHERE id=?""",
        (agora, agora, int(processo_id)))
    _mover(con, processo_id, tipo="OUTRO", etapa="REGISTRO",
           descricao=f"Registrado o reconhecimento da usucapião (ato {ato_id}).",
           data_movimento=agora, agora=agora, usuario=usuario)
