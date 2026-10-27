"""A NOTA DE EXIGÊNCIA GERAL, no protocolo do balcão — para toda atribuição.

    «precisamos que todas as atribuições tenham nota de exigência»
                                                  — o oficial, 26/10/2026

O QUE SE MEDIU ANTES DE ESCREVER (no código do `main`, 26/10/2026)
    · REGISTRO DE IMÓVEIS — tem a sua: `ri_notas_devolutivas`, presa à
      prenotação (`ri_protocolos`), com número por prenotação, exigências em
      lista, fundamentação, situação ABERTA → CUMPRIDA/FORA_DO_PRAZO (pelo
      reingresso) e o papel `RI_NOTA` no catálogo. Fica como está.
    · RCPJ e RTD — têm a sua: a qualificação NEGATIVA do título
      (`rg_qualificacoes.exigencias`, obrigatória nela), que põe o título em
      `EXIGENCIA`, e o papel `RCPJ_RTD_NOTA`. O título se liga ao balcão por
      `rg_titulos.protocolo_geral_id`. Fica como está.
    · TABELIONATO DE NOTAS, REGISTRO CIVIL e PROTESTO — NENHUMA. Procurado por
      «exigência», «devolutiva» e «nota de exigência» em todos os módulos
      deles: o que existe é a PALAVRA na linha do tempo da tarefa
      (`tarefa_processo.TIPOS_ANDAMENTO`, «Emitida nota de exigência», texto
      livre de andamento) e a suspensão da tarefa à espera do cliente
      (`tarefa_suspensao`). Nada grava o que o interessado tem de trazer, e
      por isso o portal do cliente e os avisos de andamento só sabiam dizer
      «procure o cartório» fora do RI.
    · A usucapião e a retificação do RI têm fase «exigência» no rito delas
      (`us_*`, `rr_*`); são processos do RI, e não entram aqui.

O DESENHO
    UMA TABELA NOVA, `cx_exigencias`, presa ao PROTOCOLO GERAL
    (`cx_protocolos`), que é a porta das seis atribuições. Ela serve só às
    atribuições que não têm a sua (`ATRIBUICOES_DA_EXIGENCIA`); o RI e o
    RCPJ/RTD continuam com as delas, e abrir aqui uma exigência de protocolo
    do RI ou do RCPJ/RTD é RECUSADO com a frase de onde ela se faz — duas
    notas para o mesmo título seriam duas verdades.

    Uma linha é UMA NOTA, com uma ou mais exigências (uma por linha do texto),
    como a do RI: é o papel que se entrega ao interessado. Ela NÃO SE APAGA:
    nasce ABERTA e sai CUMPRIDA (com quem e quando) ou CANCELADA (com motivo
    escrito). Nota emitida errada se cancela e se emite outra.

A LEITURA ÚNICA — `exigencias_abertas_do_protocolo`
    Devolve as exigências ABERTAS de QUALQUER atribuição daquele protocolo
    geral: a geral daqui, a nota devolutiva do RI (pela ponte
    `cx_protocolos.ri_protocolo_id`) e a qualificação negativa do RCPJ/RTD
    (pela ponte `rg_titulos.protocolo_geral_id`). É ela que a ficha do
    protocolo mostra, e é ela que o portal do cliente e os avisos de andamento
    chamam — um lugar só que responde «o que falta o cliente trazer».

A REGRA DO BALCÃO (o oficial, 26/10/2026)
    O texto da exigência NÃO LEVA NOME DE TERCEIROS: «falta a anuência do
    cônjuge», e não o nome da pessoa. O texto pode subir ao portal. A tela
    mostra a orientação junto do campo, e `avisos_do_texto` AVISA (não recusa)
    quando o texto traz CPF/CNPJ ou o que parece nome próprio em maiúsculas —
    quem escreveu confere e confirma.

O MÓDULO NÃO FALA COM A REDE E NÃO AUDITA: a rota audita, porque é ela que
sabe quem está no balcão.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

import caixa_protocolo as CXP
import modelos_da_casa as MODELOS
from bd_nativo import banco

# ------------------------------------------------------------------ as palavras

ABERTA = "ABERTA"
CUMPRIDA = "CUMPRIDA"
CANCELADA = "CANCELADA"
SITUACOES: dict[str, str] = {
    ABERTA: "Aguardando cumprimento",
    CUMPRIDA: "Cumprida",
    CANCELADA: "Cancelada",
}

#: As atribuições que recebem a nota GERAL — as que não têm nota própria.
#: O código é o de `cx_protocolos.atribuicao` (medido em 17/09/2026:
#: FIRMAS · RCPN · RI · NOTAS · PROTESTO · RTD · OUTROS · RCPJ).
ATRIBUICOES_DA_EXIGENCIA: dict[str, str] = {
    "NOTAS": "Tabelionato de Notas",
    "FIRMAS": "Tabelionato de Notas — firmas e autenticações",
    "RCPN": "Registro Civil das Pessoas Naturais",
    "PROTESTO": "Tabelionato de Protesto",
    "OUTROS": "Outros serviços da serventia",
}

#: As que TÊM nota própria, e onde ela se faz. Abrir a geral nelas é recusado:
#: duas notas para o mesmo título seriam duas verdades.
ATRIBUICOES_COM_NOTA_PROPRIA: dict[str, str] = {
    "RI": ("No Registro de Imóveis a exigência é a NOTA DEVOLUTIVA da "
           "prenotação: abra-a pela prenotação ligada a este protocolo "
           "(Livro 1 → protocolo → «Nota devolutiva»)."),
    "RTD": ("No RTD a exigência é a QUALIFICAÇÃO NEGATIVA do título: "
            "qualifique o título ligado a este protocolo (RCPJ e RTD → "
            "Títulos)."),
    "RCPJ": ("No RCPJ a exigência é a QUALIFICAÇÃO NEGATIVA do título: "
             "qualifique o título ligado a este protocolo (RCPJ e RTD → "
             "Títulos)."),
}

# A mesma régua de dez letras do resto da casa (`rg_titulo.MINIMO_DO_TEXTO`,
# `caixa_protocolo` no motivo): «trazer doc» não diz ao interessado o que
# trazer, e ele volta ao balcão para perguntar.
MINIMO_DO_TEXTO = 10
MOTIVO_MINIMO = 10

# O PAPEL — no catálogo da casa, para o oficial editar em Modelos.
CHAVE_DO_PAPEL = "CAIXA_EXIGENCIA"


class ExigenciaError(ValueError):
    """Recusa de regra, com a frase pronta para o balcão."""


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


# ------------------------------------------------------------- o texto

_ENUMERACAO = re.compile(r"^\s*(?:\d{1,3}\s*[.)\-–]|[-•*])\s*")


def itens_do_texto(texto: Any) -> list[str]:
    """«1. trazer X\\n2) trazer Y» → ["trazer X", "trazer Y"]. Só calcula.

    Uma exigência por linha, como na nota devolutiva do RI. A numeração que o
    balcão digitou sai: quem numera é o papel, e número duplicado («1. 1.»)
    confunde quem lê.
    """
    itens = []
    for linha in str(texto or "").splitlines():
        limpa = _ENUMERACAO.sub("", linha).strip()
        if limpa:
            itens.append(limpa)
    return itens


_RE_DOCUMENTO = re.compile(
    r"(?<!\d)(?:\d{3}\.?\d{3}\.?\d{3}-?\d{2}|\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)")
_MAIUSCULA = "A-ZÀ-ÖØ-Þ"
_RE_NOME_EM_MAIUSCULAS = re.compile(
    rf"(?<![\w])[{_MAIUSCULA}]{{2,}}"
    rf"(?:\s+(?:(?:DE|DA|DO|DOS|DAS|E)\s+)?[{_MAIUSCULA}]{{2,}})+(?![\w])")
_PARTICULAS = frozenset({"DE", "DA", "DO", "DOS", "DAS", "E"})

#: Palavras em maiúsculas que o balcão escreve todo dia e que NÃO são nome de
#: gente — siglas de documento, de tributo, de órgão. Comparadas sem acento.
#: Sequência só delas não gera aviso; uma palavra fora da lista, sim.
TERMOS_DO_BALCAO = frozenset("""
    CPF CNPJ RG CNH CTPS RNE CRNM NIS PIS PASEP TITULO ELEITOR ELEITORAL
    ITBI ITCMD ITCD IPTU ITR CCIR CAR NIRF INCRA SIGEF SNCR CIB DITR DIAC DIAT
    DNV DO DUT CRV CRLV DETRAN RENAVAM CND CNDT CPEN CRF FGTS INSS RFB
    RECEITA FEDERAL ESTADUAL MUNICIPAL SEFAZ PREFEITURA CARTORIO SERVENTIA
    CERTIDAO CERTIDOES NASCIMENTO CASAMENTO OBITO INTEIRO TEOR BREVE RELATO
    ESCRITURA PUBLICA PROCURACAO SUBSTABELECIMENTO TESTAMENTO ATA NOTARIAL
    MATRICULA IMOVEL IMOVEIS RURAL URBANO PLANTA MEMORIAL DESCRITIVO ART RRT
    CONTRATO SOCIAL ESTATUTO ALTERACAO REQUERIMENTO DECLARACAO FORMAL PARTILHA
    ORIGINAL COPIA AUTENTICADA ATUALIZADA NEGATIVA POSITIVA DEBITOS DEBITO
    LEI CPC CC CN CGJ TJMA MA ONR CENSEC CRC SIRC CRA CENPROT OAB PJ PF ME EPP
    MEI LTDA SA EIRELI NIRE JUCEMA CNAE IBGE RG/CPF CPF/CNPJ ITBI/ITCMD
    PROTESTO TITULOS DOCUMENTOS PESSOAS NATURAIS JURIDICAS REGISTRO CIVIL
    NOTAS FIRMA FIRMAS SINAL PUBLICO AUTENTICACAO RECONHECIMENTO VIA VIAS
    PRAZO DIAS UTEIS CORRIDOS NOTA EXIGENCIA EXIGENCIAS PROTOCOLO
""".split())


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def avisos_do_texto(texto: Any) -> list[str]:
    """O que no texto parece dado de terceiro. Só calcula — AVISA, não recusa.

    Duas coisas: o que tem forma de CPF ou CNPJ, e a sequência de duas ou
    mais palavras em MAIÚSCULAS que não são termo do balcão (o jeito como o
    acervo desta casa escreve nome de gente). Falso positivo é aceitável —
    quem escreveu confere e confirma; nome que passa sem aviso é o que a regra
    quer evitar, e por isso a lista de termos é curta.
    """
    t = str(texto or "")
    avisos: list[str] = []
    documentos = _RE_DOCUMENTO.findall(t)
    if documentos:
        avisos.append(
            f"O texto tem o que parece CPF ou CNPJ («{documentos[0]}»). "
            "Documento de pessoa não vai na exigência: escreva o papel dela "
            "(«do vendedor», «do cônjuge»).")
    for achado in _RE_NOME_EM_MAIUSCULAS.finditer(t):
        palavras = [_sem_acento(p).upper() for p in achado.group(0).split()]
        miolo = [p for p in palavras if p not in _PARTICULAS]
        if all(p in TERMOS_DO_BALCAO for p in miolo):
            continue
        avisos.append(
            f"O texto tem o que parece nome de pessoa em maiúsculas "
            f"(«{achado.group(0)}»). Escreva o papel da pessoa, e não o nome: "
            "«falta a anuência do cônjuge».")
        break
    return avisos


# ------------------------------------------------------------- ler


def protocolo(con, protocolo_id) -> dict | None:
    """O protocolo do balcão, ou None. Só LÊ."""
    return banco(con).um("SELECT * FROM cx_protocolos WHERE id = %s",
                         (int(protocolo_id),))


def _enfeitar(e: dict) -> dict:
    e = dict(e)
    e["itens"] = itens_do_texto(e.get("texto"))
    e["situacao_rotulo"] = SITUACOES.get(e.get("situacao") or "", e.get("situacao"))
    e["atribuicao_nome"] = ATRIBUICOES_DA_EXIGENCIA.get(
        e.get("atribuicao") or "", e.get("atribuicao") or "")
    return e


def uma(con, exigencia_id) -> dict | None:
    """Uma nota de exigência geral, com os itens. Só LÊ."""
    e = banco(con).um("SELECT * FROM cx_exigencias WHERE id = %s",
                      (int(exigencia_id),))
    return _enfeitar(e) if e else None


def do_protocolo(con, protocolo_id) -> list[dict]:
    """TODAS as notas gerais do protocolo — abertas, cumpridas e canceladas,
    da mais nova à mais velha. Só LÊ. É a lista da tela: a cancelada continua
    à vista, com o motivo — sumir seria o `DELETE` com outra cara."""
    return [_enfeitar(e) for e in banco(con).ler(
        """SELECT * FROM cx_exigencias WHERE protocolo_id = %s
            ORDER BY numero DESC, id DESC""", (int(protocolo_id),))]


def atribuicao_sugerida(p: dict | None) -> str:
    """A atribuição que a tela já traz escolhida: a do protocolo, se ela
    recebe a nota geral. Só calcula."""
    a = _texto((p or {}).get("atribuicao")).upper()
    return a if a in ATRIBUICOES_DA_EXIGENCIA else ""


# ------------------------------------------------------------- escrever


def _data_valida(valor: Any, rotulo: str) -> str | None:
    texto = _texto(valor)
    if not texto:
        return None
    try:
        return date.fromisoformat(texto[:10]).isoformat()
    except ValueError:
        raise ExigenciaError(f"{rotulo} «{texto[:20]}» não é data. Use o "
                             "calendário do campo.") from None


def abrir(con, protocolo_id, *, texto: Any, agora: str,
          atribuicao: Any = None, fundamento: Any = None,
          prazo_ate: Any = None, quem: str | None = None,
          usuario_id: Any = None) -> dict:
    """Abre a nota de exigência no protocolo. ESCREVE. Devolve a linha.

    Chamar dentro da transação da rota. Recusa (com a frase do balcão):
      · protocolo encerrado — exigência nova é sinal de que o atendimento não
        terminou, e o caminho é reabrir, que deixa o motivo;
      · atribuição com nota própria (RI, RCPJ, RTD) — a frase diz onde fazer;
      · texto sem exigência que se leia (menos de dez letras);
      · prazo que não é data, ou que já passou.
    """
    bd = banco(con)
    p = protocolo(bd, protocolo_id)
    if not p:
        raise ExigenciaError("Protocolo não encontrado.")
    if CXP.esta_encerrado(p.get("situacao")):
        raise ExigenciaError(
            f"O protocolo {p['numero']} está encerrado. Reabra-o (com o motivo) "
            "antes de abrir nota de exigência.")
    escolhida = _texto(atribuicao).upper() or atribuicao_sugerida(p)
    if not escolhida:
        do_protocolo_ = _texto(p.get("atribuicao")).upper()
        if do_protocolo_ in ATRIBUICOES_COM_NOTA_PROPRIA:
            raise ExigenciaError(ATRIBUICOES_COM_NOTA_PROPRIA[do_protocolo_])
        raise ExigenciaError("Escolha a atribuição da exigência.")
    if escolhida in ATRIBUICOES_COM_NOTA_PROPRIA:
        raise ExigenciaError(ATRIBUICOES_COM_NOTA_PROPRIA[escolhida])
    if escolhida not in ATRIBUICOES_DA_EXIGENCIA:
        raise ExigenciaError(
            f"«{escolhida[:20]}» não é atribuição da nota de exigência. São: "
            f"{', '.join(ATRIBUICOES_DA_EXIGENCIA)}.")
    itens = itens_do_texto(texto)
    if sum(len(i) for i in itens) < MINIMO_DO_TEXTO:
        raise ExigenciaError(
            "Escreva o que falta o interessado trazer ou fazer — uma exigência "
            "por linha, com pelo menos dez letras. Nota sem exigência devolve "
            "o pedido sem dizer o que fazer.")
    prazo = _data_valida(prazo_ate, "O prazo")
    hoje = str(agora)[:10]
    if prazo and prazo < hoje:
        raise ExigenciaError(
            "O prazo para cumprir já passou. Escolha uma data de hoje em "
            "diante, ou deixe em branco — prazo em branco não se inventa.")
    bd.travar("cx_exigencias.numero")
    numero = int(bd.valor(
        "SELECT COALESCE(MAX(numero), 0) + 1 AS n FROM cx_exigencias "
        "WHERE protocolo_id = %s", (int(p["id"]),)))
    nova = bd.escrever(
        """INSERT INTO cx_exigencias (protocolo_id, numero, atribuicao, texto,
               fundamento, prazo_ate, situacao, aberta_em, aberta_por,
               aberta_por_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING *""",
        (int(p["id"]), numero, escolhida, "\n".join(itens),
         _texto(fundamento) or None, prazo, ABERTA, agora, quem or None,
         int(usuario_id) if usuario_id else None))
    return _enfeitar(nova[0]) | {"protocolo_numero": p["numero"]}


def _aberta_do_protocolo(bd, protocolo_id, exigencia_id) -> dict:
    bd._escrita()
    e = bd.um("SELECT * FROM cx_exigencias WHERE id = %s FOR UPDATE",
              (int(exigencia_id),))
    if not e or int(e["protocolo_id"]) != int(protocolo_id):
        raise ExigenciaError("Esta nota de exigência não é deste protocolo.")
    if e["situacao"] != ABERTA:
        raise ExigenciaError(
            f"A nota de exigência nº {e['numero']} já está "
            f"{SITUACOES.get(e['situacao'], e['situacao']).lower()} — só a "
            "aberta se dá por cumprida ou se cancela.")
    return e


def dar_por_cumprida(con, protocolo_id, exigencia_id, *, agora: str,
                     quem: str | None = None, observacao: Any = None) -> dict:
    """Marca a nota CUMPRIDA: quem e quando. ESCREVE. Devolve a linha."""
    bd = banco(con)
    _aberta_do_protocolo(bd, protocolo_id, exigencia_id)
    linha = bd.escrever(
        """UPDATE cx_exigencias SET situacao = %s, cumprida_em = %s,
                  cumprida_por = %s, cumprida_observacao = %s
            WHERE id = %s RETURNING *""",
        (CUMPRIDA, agora, quem or None, _texto(observacao) or None,
         int(exigencia_id)))
    return _enfeitar(linha[0])


def cancelar(con, protocolo_id, exigencia_id, *, motivo: Any, agora: str,
             quem: str | None = None) -> dict:
    """Cancela a nota, com motivo escrito. ESCREVE. Não apaga nada."""
    motivo = _texto(motivo)
    if len(motivo) < MOTIVO_MINIMO:
        raise ExigenciaError(
            "Diga por que a nota se cancela (pelo menos dez letras) — por "
            "exemplo «emitida no protocolo errado» ou «exigência indevida, "
            "documento já estava no processo».")
    bd = banco(con)
    _aberta_do_protocolo(bd, protocolo_id, exigencia_id)
    linha = bd.escrever(
        """UPDATE cx_exigencias SET situacao = %s, cancelada_em = %s,
                  cancelada_por = %s, cancelada_motivo = %s
            WHERE id = %s RETURNING *""",
        (CANCELADA, agora, quem or None, motivo, int(exigencia_id)))
    return _enfeitar(linha[0])


# ------------------------------------------------------------- a leitura única


def _lista_do_ri(valor: Any) -> list[str]:
    """`ri_notas_devolutivas.exigencias` é JSON (lista); o que não for, é
    texto de uma exigência só."""
    import json
    try:
        lista = json.loads(valor or "[]")
    except (TypeError, ValueError):
        lista = [valor]
    if not isinstance(lista, list):
        lista = [lista]
    return [_texto(x) for x in lista if _texto(x)]


def exigencias_abertas_do_protocolo(con, protocolo_id) -> list[dict]:
    """O QUE FALTA O INTERESSADO TRAZER, em QUALQUER atribuição. SÓ LÊ.

    A leitura única: a ficha do protocolo, o portal do cliente e os avisos de
    andamento perguntam aqui. Junta, do protocolo geral `protocolo_id`:

      · GERAL     — `cx_exigencias` ABERTA deste protocolo;
      · RI        — `ri_notas_devolutivas` ABERTA da prenotação ligada
                    (`cx_protocolos.ri_protocolo_id`);
      · RCPJ_RTD  — o título ligado (`rg_titulos.protocolo_geral_id`) que está
                    em `EXIGENCIA`, com a qualificação NEGATIVA mais recente.

    Cada item é um dicionário, sempre com as mesmas chaves:

        origem          "GERAL" | "RI" | "RCPJ_RTD"
        id              id da linha na tabela de origem (cx_exigencias,
                        ri_notas_devolutivas ou rg_qualificacoes)
        chave           "<origem>:<id>" — estável; uma nota nova é outra chave
        atribuicao      "NOTAS" | "FIRMAS" | "RCPN" | "PROTESTO" | "OUTROS" |
                        "RI" | "RCPJ" | "RTD"
        numero          nº da nota (no protocolo, na prenotação) ou a ordem da
                        qualificação do título
        itens           [str, ...] — as exigências, uma por item, como o
                        balcão escreveu (quem publica limpa)
        fundamento      str | None
        prazo_ate       "AAAA-MM-DD" | None
        aberta_em       "AAAA-MM-DD" | None
        onde            frase curta para a tela («Nota devolutiva nº 2 da
                        prenotação 1234/1A»)
        prenotacao_id   int | None — só no RI
        titulo_id       int | None — só no RCPJ_RTD

    Em ordem de abertura (a mais velha primeiro). Protocolo inexistente
    devolve lista vazia.
    """
    bd = banco(con)
    p = protocolo(bd, protocolo_id)
    if not p:
        return []
    saida: list[dict] = []

    for e in bd.ler(
            """SELECT * FROM cx_exigencias
                WHERE protocolo_id = %s AND situacao = %s ORDER BY id""",
            (int(p["id"]), ABERTA)):
        saida.append({
            "origem": "GERAL", "id": int(e["id"]), "chave": f"GERAL:{e['id']}",
            "atribuicao": e["atribuicao"], "numero": int(e["numero"]),
            "itens": itens_do_texto(e["texto"]),
            "fundamento": e["fundamento"] or None,
            "prazo_ate": e["prazo_ate"] or None,
            "aberta_em": str(e["aberta_em"] or "")[:10] or None,
            "onde": f"Nota de exigência nº {e['numero']} do protocolo {p['numero']}",
            "prenotacao_id": None, "titulo_id": None})

    if p.get("ri_protocolo_id") and bd.tem_tabela("ri_notas_devolutivas"):
        for n in bd.ler(
                """SELECT n.*, r.numero AS prenotacao_numero, r.livro
                     FROM ri_notas_devolutivas n
                     JOIN ri_protocolos r ON r.id = n.protocolo_id
                    WHERE n.protocolo_id = %s AND n.situacao = 'ABERTA'
                    ORDER BY n.id""", (int(p["ri_protocolo_id"]),)):
            saida.append({
                "origem": "RI", "id": int(n["id"]), "chave": f"RI:{n['id']}",
                "atribuicao": "RI", "numero": int(n["numero"]),
                "itens": _lista_do_ri(n["exigencias"]),
                "fundamento": n["fundamentacao"] or None,
                "prazo_ate": n["prazo_ate"] or None,
                "aberta_em": str(n["data_nota"] or "")[:10] or None,
                "onde": (f"Nota devolutiva nº {n['numero']} da prenotação "
                         f"{n['prenotacao_numero']}/{n['livro'] or '1A'}"),
                "prenotacao_id": int(n["protocolo_id"]), "titulo_id": None})

    if bd.tem_tabela("rg_titulos"):
        import rg_titulo as TIT
        for t in bd.ler(
                """SELECT id, atribuicao, numero FROM rg_titulos
                    WHERE protocolo_geral_id = %s AND situacao = %s
                    ORDER BY id""", (int(p["id"]), TIT.EXIGENCIA)):
            q = TIT.ultima_qualificacao(bd, int(t["id"]))
            if not q or q["resultado"] != TIT.NEGATIVA:
                continue
            sigla = "RCPJ" if int(t["atribuicao"]) == TIT.RCPJ else "RTD"
            saida.append({
                "origem": "RCPJ_RTD", "id": int(q["id"]),
                "chave": f"RCPJ_RTD:{q['id']}", "atribuicao": sigla,
                "numero": int(q["ordem"]),
                "itens": itens_do_texto(q["exigencias"]),
                "fundamento": q["fundamentacao"] or None,
                "prazo_ate": q["prazo_ate"] or None,
                "aberta_em": str(q["data_qualificacao"] or "")[:10] or None,
                "onde": (f"Qualificação negativa do título {sigla} nº "
                         f"{t['numero'] or t['id']}"),
                "prenotacao_id": None, "titulo_id": int(t["id"])})

    saida.sort(key=lambda x: (x["aberta_em"] or "", x["origem"], x["id"]))
    return saida


# ------------------------------------------------------------- o papel

#: Os claros que o papel recebe, com um exemplo de cada, para a tela de
#: Modelos conferir o ajuste da casa (o boneco geral só tem `hoje`, `agora`
#: e `sv`). Sem dado de ninguém.
CLAROS_DE_EXEMPLO: dict[str, Any] = {
    "sv": {"unit_name": "SERVENTIA DE EXEMPLO", "serventia_endereco": "Rua de Exemplo, 1",
           "serventia_cep": "00000-000", "cidade_uf": "Cidade Exemplo/UF",
           "ri_cns": "000000", "serventia_cnpj": "00.000.000/0000-00",
           "serventia_telefone": "(99) 0000-0000",
           "serventia_email": "contato@exemplo.invalid",
           "ri_cidade": "Cidade Exemplo", "ri_uf": "UF"},
    "p": {"numero": "2026.10.1", "interessado": "FULANO DE EXEMPLO"},
    "e": {"numero": 1, "fundamento": "Fundamento de exemplo."},
    "documento": "***.000.000-**",
    "itens": ["Trazer a certidão de casamento atualizada.",
              "Falta a anuência do cônjuge."],
    "nome_da_atribuicao": "Tabelionato de Notas",
    "aberto_em": "26/10/2026", "emitida_em": "26/10/2026",
    "prazo_ate": "09/11/2026", "data_extenso": "26 de outubro de 2026",
    "emitido_por": "FULANO DE EXEMPLO", "funcao": "Escrevente",
}


def montar_papel(*, modelo: str | None = None, **claros: Any) -> str:
    """O papel da nota de exigência, em HTML. Só calcula.

    **COM AUTOESCAPE**: a exigência e o fundamento são texto do balcão, e um
    «<» neles não pode virar marcação no papel. O ajuste da casa sai sem o
    que executa (`MODELOS.sem_o_que_executa`); o de fábrica, como está.
    """
    from jinja2.sandbox import SandboxedEnvironment
    texto = modelo if modelo is not None else MODELOS.padrao_de(CHAVE_DO_PAPEL)
    papel = SandboxedEnvironment(autoescape=True).from_string(texto).render(**claros)
    return MODELOS.sem_o_que_executa(texto, papel)


def conferir_modelo(corpo: str) -> str:
    """O ajuste da casa monta? `""` quando sim; a frase do erro quando não.

    O boneco da tela de Modelos não tem os claros deste papel e reprovaria
    todo ajuste; aqui ele se monta com o caso de exemplo, sem claro inventado.
    """
    from jinja2 import StrictUndefined
    from jinja2.sandbox import SandboxedEnvironment
    try:
        SandboxedEnvironment(autoescape=True, undefined=StrictUndefined
                             ).from_string(corpo or "").render(**CLAROS_DE_EXEMPLO)
    except Exception as erro:                              # noqa: BLE001
        return f"O modelo da nota de exigência não monta: {erro}"
    return ""


def __getattr__(nome: str):
    """`MODELO_NOTA_DE_EXIGENCIA` — o nome do papel no catálogo —, lido da base.

    O TEXTO NUNCA MOROU AQUI: nasceu em `modelos_padrao/caixa/` (26/10/2026).
    O catálogo pede um nome por papel, e por isso ele não existe no módulo e
    responde por aqui, com o MESMO texto que a nota imprime. Nome que não é de
    papel continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    return MODELOS.constante_antiga(__name__, nome)
