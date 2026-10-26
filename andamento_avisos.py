"""Os avisos de andamento ao cliente — exigência, pronto para retirar, prazo.

    «quero que implementemos o acompanhamento de protocolo com notificacao
     automatica para o cliente por whatsapp e email para saber do andamento do
     protocolo, caso deseje» — o oficial, 25/10/2026; escolhido para começar
     em 26/10/2026.

OS TRÊS ANDAMENTOS, E SÓ O STATUS
    EXIGENCIA  a prenotação do RI recebeu nota devolutiva (`ri_notas_devolutivas`
               ABERTA) e ainda está correndo;
    PRONTO     o protocolo geral foi marcado «pronto para retirar»
               (`cx_protocolos.pronto_retirar_em`) e não foi entregue;
    PRAZO      a prenotação vence em N dias úteis ou menos (N no processo da
               automação; 5 de fábrica), fora de suspensão.
    A mensagem diz o número do protocolo e o andamento. **Não leva CPF, nome,
    valor nem o teor do ato ou da nota** — a regra da casa para o que sai
    sozinho (docs/decisoes/02_modelos_ia_privacidade.md). O cliente sabe o que
    falta no balcão, onde quem fala com ele confere quem ele é.

O PROTESTO FICA DE FORA
    O protesto tem sigilo próprio: protocolo geral da atribuição PROTESTO não
    aceita consentimento e nunca gera aviso.

SEM O SIM DO CLIENTE, NADA SAI
    O consentimento é por canal, gravado com data e quem registrou
    (`av_consentimentos`), no protocolo geral ou na prenotação. Vale também
    para o registro ligado: quem disse sim no protocolo geral ligado a uma
    prenotação recebe os andamentos da prenotação, e vice-versa — é o mesmo
    serviço, e pedir o sim duas vezes faria o balcão esquecer uma.

QUEM DISPARA É O DESPACHANTE, E NÃO A TELA — o desenho mais simples
    Um processo só da automação (`AVISOS_ANDAMENTO`, trazido por este módulo
    pelo `CATALOGO`) faz as três coisas a cada rodada: MEDE quais andamentos
    estão vigentes, ENFILEIRA um aviso por evento, canal e destino (o índice
    único faz o «uma vez só»), e ENVIA o que está na fila. Por quê:
      - o prazo que vence não tem evento nenhum — precisa de rodada de
        qualquer jeito, e uma rodada serve os três;
      - a tela não fala com a rede: o SMTP tem prazo de 20 s, e isso dentro da
        requisição seguraria o balcão (e dentro de `db.transaction()`, a
        casa inteira);
      - a nota devolutiva continua sendo emitida pela rota de sempre, sem
        gancho novo: a rodada a LÊ;
      - o que não saiu (SMTP fora, sem configuração) fica na fila e sai na
        próxima rodada, se o andamento ainda for verdade — e é DESCARTADO se
        não for mais (nota cumprida, protocolo entregue, prenotação vencida,
        cliente que desmarcou). Aviso atrasado sobre fato que passou é pior que
        aviso nenhum.
    O processo nasce DESLIGADO, como todo processo da central. Ligar é do
    oficial.

OS CANAIS
    EMAIL     pelo envio da automação (`automacao_avisos.mandar_email`, com a
              senha em `avisos.cred`) — o mesmo SMTP, outro destino. Sem SMTP
              configurado, o aviso fica PENDENTE_CONFIG.
    WHATSAPP  o registro e a fila existem, e o envio NÃO: fora da janela de 24 h
              a Meta só deixa a serventia iniciar conversa por MODELO aprovado
              por ela, e esta casa não tem nenhum. Texto livre automático é
              recusado pela Meta e contraria a regra da casa (autoenvio
              desligado). Fica PENDENTE_CONFIG — ninguém conclui que mandou o
              que não mandou.

OS TEXTOS SÃO DA CASA
    Papel CAIXA_AVISO_ANDAMENTO do catálogo (`modelos_padrao/caixa/`), uma
    parte por andamento, editável em Administrativo → Modelos. O ajuste torto
    não cala o aviso: sai o padrão, e o log diz por quê.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Iterable

import andamento_schema as AS
from bd_nativo import banco

_LOG = logging.getLogger(__name__)

MODELO = "CAIXA_AVISO_ANDAMENTO"
PARTES = ("ASSINATURA", "EXIGENCIA_ASSUNTO", "EXIGENCIA", "PRONTO_ASSUNTO", "PRONTO",
          "PRAZO_ASSUNTO", "PRAZO")
_CLAROS_DO_EVENTO = ("numero", "serventia", "data_limite", "dias", "assinatura")
#: Os claros de cada parte. Nenhum deles é dado de pessoa — de propósito.
CLAROS = {"ASSINATURA": ("serventia", "telefone", "email"),
          **{p: _CLAROS_DO_EVENTO for p in PARTES[1:]}}

#: Quantos dias úteis antes do vencimento da prenotação o cliente é avisado.
DIAS_ANTES_PADRAO = 5
DIAS_ANTES_LIMITES = (1, 30)
#: Quantas vezes um e-mail que falhou é tentado de novo, uma por rodada.
MAX_TENTATIVAS_PADRAO = 3

#: As situações da prenotação em que ela ainda corre. DEVOLVIDO corre: a nota
#: devolutiva não suspende o prazo (ri_web, «a prenotação continua correndo»).
PRENOTACAO_CORRENDO = ("ABERTO", "DEVOLVIDO")
#: As do protocolo geral em que o serviço já terminou.
PROTOCOLO_ENCERRADO = ("ENTREGUE", "CANCELADO")

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: Por que o WhatsApp não sai — a frase que a fila e a tela mostram.
SEM_MODELO_DA_META = ("WhatsApp sem modelo aprovado pela Meta: o envio automático fica "
                      "desligado até a casa ter o modelo (texto livre fora da janela de 24 h "
                      "a Meta recusa).")
SEM_SMTP = "o e-mail não está configurado (Administrativo → Automação → Configuração)"


class AndamentoError(ValueError):
    """Erro de regra, com a frase pronta para o balcão."""


def _iso(quando: datetime) -> str:
    return quando.replace(microsecond=0).isoformat()


def _digitos(v: Any) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


# ------------------------------------------------------------------ o registro


def registro(con, origem: str, origem_id: int) -> dict:
    """O protocolo geral ou a prenotação, com o contato. Recusa o que não existe."""
    bd = banco(con)
    if origem == AS.PROTOCOLO_GERAL:
        pronto = ("pronto_retirar_em, pronto_retirar_por"
                  if bd.tem_coluna("cx_protocolos", "pronto_retirar_em")
                  else "NULL AS pronto_retirar_em, NULL AS pronto_retirar_por")
        linha = bd.um(f"""SELECT id, numero, telefone, email, atribuicao, situacao,
                                 ri_protocolo_id, {pronto}
                            FROM cx_protocolos WHERE id=%s""", (int(origem_id),))
    elif origem == AS.PRENOTACAO:
        linha = bd.um("""SELECT id, numero, livro, telefone, email, situacao, data_limite
                           FROM ri_protocolos WHERE id=%s""", (int(origem_id),))
    else:
        raise AndamentoError("Origem desconhecida para o aviso de andamento.")
    if not linha:
        raise AndamentoError(f"O {AS.NOME_DA_ORIGEM[origem]} nº {origem_id} não existe.")
    return {**dict(linha), "origem": origem}


def e_protesto(reg: dict) -> bool:
    return (reg.get("origem") == AS.PROTOCOLO_GERAL
            and str(reg.get("atribuicao") or "").strip().upper() == "PROTESTO")


def destino_do_canal(reg: dict, canal: str) -> str:
    """O endereço do cadastro para aquele canal, conferido. Recusa o que não serve."""
    if canal == AS.EMAIL:
        mail = str(reg.get("email") or "").strip()
        if not mail:
            raise AndamentoError("Este registro não tem e-mail. Corrija o contato antes de "
                                 "marcar o aviso por e-mail.")
        if not _EMAIL.match(mail):
            raise AndamentoError(f"O e-mail «{mail}» não está completo (ex.: nome@provedor.com).")
        return mail
    if canal == AS.WHATSAPP:
        tel = _digitos(reg.get("telefone"))
        if not tel:
            raise AndamentoError("Este registro não tem telefone. Corrija o contato antes de "
                                 "marcar o aviso por WhatsApp.")
        if not 10 <= len(tel) <= 13:
            raise AndamentoError("O telefone precisa do DDD (10 a 13 dígitos) para o WhatsApp.")
        return tel
    raise AndamentoError("Canal desconhecido.")


# ------------------------------------------------------------------ o consentimento


def consentimentos(con, origem: str, origem_id: int) -> list[dict]:
    """Todos os consentimentos do registro, os ativos e os revogados, mais novo primeiro."""
    return banco(con).ler("""SELECT * FROM av_consentimentos WHERE origem=%s AND origem_id=%s
                              ORDER BY id DESC""", (origem, int(origem_id)))


def ativos(con, origem: str, origem_id: int) -> dict[str, dict]:
    """O consentimento ativo de cada canal, ou nada."""
    return {c["canal"]: c for c in consentimentos(con, origem, origem_id) if c["ativo"]}


def consentir(con, origem: str, origem_id: int, canal: str, *, quem: str,
              agora: datetime) -> dict:
    """Grava o SIM do cliente naquele canal, para o endereço do cadastro. ESCREVE.

    Já havendo sim para o mesmo endereço, não grava outro (o clique repetido
    não é um segundo consentimento). Para endereço diferente, o antigo é
    revogado e o novo gravado: o sim vale para o endereço que ele deu."""
    if canal not in AS.CANAIS:
        raise AndamentoError("Canal desconhecido.")
    reg = registro(con, origem, origem_id)
    if e_protesto(reg):
        raise AndamentoError("Protocolo do Protesto não recebe aviso de andamento: o protesto "
                             "tem sigilo próprio.")
    destino = destino_do_canal(reg, canal)
    atual = ativos(con, origem, origem_id).get(canal)
    if atual and atual["destino"] == destino:
        return atual
    bd = banco(con)
    if atual:
        _revogar_linha(bd, atual, quem=quem, agora=agora,
                       motivo="o endereço do cliente mudou; vale o novo consentimento")
    return bd.escrever(
        """INSERT INTO av_consentimentos (origem, origem_id, canal, destino, ativo,
               registrado_em, registrado_por) VALUES (%s,%s,%s,%s,1,%s,%s) RETURNING *""",
        (origem, int(origem_id), canal, destino, _iso(agora), (quem or "").strip() or None))[0]


def _revogar_linha(bd, linha: dict, *, quem: str, agora: datetime, motivo: str) -> None:
    bd.escrever("""UPDATE av_consentimentos SET ativo=0, revogado_em=%s, revogado_por=%s
                    WHERE id=%s""", (_iso(agora), (quem or "").strip() or None, linha["id"]))
    # O que estava na fila para este sim não sai mais.
    bd.escrever("""UPDATE av_avisos SET situacao=%s, erro=%s
                    WHERE consentimento_id=%s AND situacao IN (%s,%s,%s)""",
                (AS.DESCARTADO, motivo, linha["id"], AS.PENDENTE, AS.FALHOU, AS.PENDENTE_CONFIG))


def revogar(con, origem: str, origem_id: int, canal: str, *, quem: str,
            agora: datetime) -> dict | None:
    """Desmarca o canal. NÃO APAGA: grava quando e quem. ESCREVE."""
    atual = ativos(con, origem, origem_id).get(canal)
    if not atual:
        return None
    _revogar_linha(banco(con), atual, quem=quem, agora=agora,
                   motivo="o cliente desmarcou o aviso antes de ele sair")
    return atual


# ------------------------------------------------------------------ pronto para retirar


def marcar_pronto(con, protocolo_id: int, *, quem: str, agora: datetime) -> dict:
    """Marca o protocolo geral como pronto para retirar. ESCREVE."""
    reg = registro(con, AS.PROTOCOLO_GERAL, protocolo_id)
    if str(reg.get("situacao") or "").upper() in PROTOCOLO_ENCERRADO:
        raise AndamentoError("Protocolo encerrado não se marca como pronto: reabra-o antes.")
    if reg.get("pronto_retirar_em"):
        raise AndamentoError(f"O protocolo {reg['numero']} já está pronto para retirar desde "
                             f"{str(reg['pronto_retirar_em'])[:16].replace('T', ' ')}.")
    banco(con).escrever("""UPDATE cx_protocolos SET pronto_retirar_em=%s, pronto_retirar_por=%s
                            WHERE id=%s""", (_iso(agora), (quem or "").strip() or None,
                                             int(protocolo_id)))
    return {**reg, "pronto_retirar_em": _iso(agora), "pronto_retirar_por": quem}


def desmarcar_pronto(con, protocolo_id: int) -> dict:
    """Tira a marca (engano no clique). O aviso que já saiu, saiu. ESCREVE."""
    reg = registro(con, AS.PROTOCOLO_GERAL, protocolo_id)
    if not reg.get("pronto_retirar_em"):
        raise AndamentoError("Este protocolo não está marcado como pronto para retirar.")
    banco(con).escrever("""UPDATE cx_protocolos SET pronto_retirar_em=NULL,
                                  pronto_retirar_por=NULL WHERE id=%s""", (int(protocolo_id),))
    return reg


# ------------------------------------------------------------------ o que está vigente


def _vencimento(texto: Any) -> date | None:
    try:
        return date.fromisoformat(str(texto)[:10]) if texto else None
    except ValueError:
        return None


def eventos_vigentes(con, *, hoje: date, feriados: set | None = None,
                     dias_antes: int = DIAS_ANTES_PADRAO,
                     eventos: Iterable[str] = AS.EVENTOS) -> dict[str, dict]:
    """Os andamentos que são verdade HOJE, por chave. **SÓ LÊ.**

    A chave diz o evento e o que o identifica — é ela que faz o aviso sair uma
    vez só. A da exigência leva a nota (uma segunda nota é outro aviso); a do
    prazo leva a data-limite (a prenotação que retomou o prazo ganhou outra).
    """
    from ri_schema import dias_uteis_entre
    bd = banco(con)
    eventos = set(eventos)
    hoje_txt = hoje.isoformat()
    vig: dict[str, dict] = {}
    correndo = ",".join(["%s"] * len(PRENOTACAO_CORRENDO))
    if AS.EXIGENCIA in eventos:
        for n in bd.ler(f"""SELECT n.id AS nota_id, p.id, p.numero, p.data_limite
                              FROM ri_notas_devolutivas n
                              JOIN ri_protocolos p ON p.id = n.protocolo_id
                             WHERE n.situacao = 'ABERTA' AND p.situacao IN ({correndo})
                               AND (p.data_limite IS NULL OR p.data_limite >= %s)
                             ORDER BY n.id""", (*PRENOTACAO_CORRENDO, hoje_txt)):
            chave = f"{AS.EXIGENCIA}:{AS.PRENOTACAO}:{n['id']}:NOTA:{n['nota_id']}"
            vig[chave] = {"evento": AS.EXIGENCIA, "origem": AS.PRENOTACAO,
                          "origem_id": int(n["id"]), "numero": str(n["numero"]),
                          "data_limite": n["data_limite"], "dias": None}
    if AS.PRONTO in eventos and bd.tem_coluna("cx_protocolos", "pronto_retirar_em"):
        encerrado = ",".join(["%s"] * len(PROTOCOLO_ENCERRADO))
        for p in bd.ler(f"""SELECT id, numero FROM cx_protocolos
                             WHERE pronto_retirar_em IS NOT NULL
                               AND situacao NOT IN ({encerrado})
                               AND UPPER(COALESCE(atribuicao, '')) <> 'PROTESTO'
                             ORDER BY id""", PROTOCOLO_ENCERRADO):
            chave = f"{AS.PRONTO}:{AS.PROTOCOLO_GERAL}:{p['id']}"
            vig[chave] = {"evento": AS.PRONTO, "origem": AS.PROTOCOLO_GERAL,
                          "origem_id": int(p["id"]), "numero": str(p["numero"]),
                          "data_limite": None, "dias": None}
    if AS.PRAZO in eventos:
        suspensa = ("AND prazo_suspenso_desde IS NULL"
                    if bd.tem_coluna("ri_protocolos", "prazo_suspenso_desde") else "")
        for p in bd.ler(f"""SELECT id, numero, data_limite FROM ri_protocolos
                             WHERE situacao IN ({correndo}) AND data_limite IS NOT NULL
                               AND data_limite >= %s {suspensa}
                             ORDER BY id""", (*PRENOTACAO_CORRENDO, hoje_txt)):
            limite = _vencimento(p["data_limite"])
            if limite is None:
                continue
            dias = dias_uteis_entre(hoje, limite, feriados)
            if not 0 <= dias <= int(dias_antes):
                continue
            chave = f"{AS.PRAZO}:{AS.PRENOTACAO}:{p['id']}:{limite.isoformat()}"
            vig[chave] = {"evento": AS.PRAZO, "origem": AS.PRENOTACAO,
                          "origem_id": int(p["id"]), "numero": str(p["numero"]),
                          "data_limite": limite.isoformat(), "dias": dias}
    return vig


def destinatarios(con, origem: str, origem_id: int) -> list[dict]:
    """Os consentimentos ativos do registro e do registro LIGADO a ele."""
    bd = banco(con)
    alvos = [(origem, int(origem_id))]
    if origem == AS.PRENOTACAO:
        for cx in bd.ler("""SELECT id, atribuicao FROM cx_protocolos WHERE ri_protocolo_id=%s""",
                         (int(origem_id),)):
            if str(cx["atribuicao"] or "").strip().upper() != "PROTESTO":
                alvos.append((AS.PROTOCOLO_GERAL, int(cx["id"])))
    else:
        cx = bd.um("SELECT ri_protocolo_id FROM cx_protocolos WHERE id=%s", (int(origem_id),))
        if cx and cx["ri_protocolo_id"]:
            alvos.append((AS.PRENOTACAO, int(cx["ri_protocolo_id"])))
    saida = []
    for o, i in alvos:
        saida.extend(ativos(con, o, i).values())
    return saida


def enfileirar(con, vigentes: dict[str, dict], *, agora: datetime) -> int:
    """Um aviso por evento, canal e destino — o índice único faz o «uma vez». ESCREVE."""
    bd = banco(con)
    novos = 0
    for chave, ev in vigentes.items():
        for c in destinatarios(con, ev["origem"], ev["origem_id"]):
            whats = c["canal"] == AS.WHATSAPP
            bd.escrever(
                """INSERT INTO av_avisos (evento, chave, origem, origem_id, canal, destino,
                       consentimento_id, situacao, criado_em, erro)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (chave, canal, destino) DO NOTHING""",
                (ev["evento"], chave, ev["origem"], ev["origem_id"], c["canal"], c["destino"],
                 c["id"], AS.PENDENTE_CONFIG if whats else AS.PENDENTE, _iso(agora),
                 SEM_MODELO_DA_META if whats else None))
            novos += max(0, int(getattr(bd, "linhas_afetadas", 0) or 0))
    return novos


# ------------------------------------------------------------------ os textos


def _partir(corpo: str) -> dict[str, str]:
    marca = re.compile(r"===(" + "|".join(PARTES) + r")===[ \t]*\n?", re.IGNORECASE)
    pedacos = marca.split(corpo or "")
    return {nome.upper(): re.split(r"\n===", valor, maxsplit=1)[0].strip("\n")
            for nome, valor in zip(pedacos[1::2], pedacos[2::2])}


# O QUE NÃO PODE ESTAR NO TEXTO QUE SAI SOZINHO — revisão de segurança de
# 26/10/2026 (PR #26, achado M1).
#
#   O e-mail do aviso sai do remetente da serventia sem ninguém ler antes. Um
#   ajuste que trouxesse «pague antes R$ X no PIX <chave>» seria o golpe com o
#   nome da casa em cima. O aviso só diz o andamento: endereço de internet,
#   pedido de pagamento, valor, telefone e e-mail escritos à mão não cabem
#   nele — o telefone e o e-mail da serventia entram pelos claros {telefone} e
#   {email}, que vêm da configuração, e não do texto. A comparação é sem acento
#   e sem caixa, para «depósito» e «deposito» serem a mesma palavra.
_PROIBIDO_NO_AVISO = (
    (re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(?:com|net|org|br|io|me|ly|app)\b"),
     "endereço de internet"),
    (re.compile(r"\bpix\b"), "a palavra «pix»"),
    (re.compile(r"\bpag(?:ar|ue|uem|amento|amentos|to)\b"), "pedido de pagamento"),
    (re.compile(r"r\$"), "valor em reais («R$»)"),
    (re.compile(r"\bboleto"), "a palavra «boleto»"),
    (re.compile(r"\bdeposit"), "a palavra «depósito»"),
    (re.compile(r"\btransfer"), "a palavra «transferência»"),
    (re.compile(r"[^\s@{}]+@[^\s@{}]+\.[^\s@{}]+"), "endereço de e-mail escrito à mão"),
)
_TELEFONE_A_MAO = re.compile(r"\+?\d[\d\s().-]{6,}\d")


def _sem_acento(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto or "").lower())
                   if not unicodedata.combining(c))


def _torto(texto: str) -> str:
    """O que o texto traz que não pode ir sozinho ao cliente, ou ``""``. Só calcula."""
    limpo = _sem_acento(texto)
    for padrao, o_que in _PROIBIDO_NO_AVISO:
        if padrao.search(limpo):
            return o_que
    for achado in _TELEFONE_A_MAO.finditer(limpo):
        if sum(c.isdigit() for c in achado.group(0)) >= 8:
            return "número de telefone escrito à mão"
    return ""


def _claros_ruins(parte: str, texto: str) -> str:
    """Claro que a parte não tem, ou claro com atributo/índice (`{numero.x}`). Só calcula.

    B3 da revisão de 26/10/2026: o `str.format` resolve `{numero.__class__}`, e
    a régua da casa (`modelos_da_casa.conferir_claros`, LF06G) só aceita NOME.
    """
    import modelos_da_casa as CASA
    return CASA.conferir_claros(texto, CLAROS.get(parte, ()))


def _montar(parte: str, claros: dict, con: Any = None) -> str:
    import modelos_da_casa as CASA
    padrao = _partir(CASA.padrao_de(MODELO))
    texto = padrao.get(parte, "")
    if con is not None:
        try:
            texto = _partir(CASA.texto_do_papel(con, MODELO)).get(parte) or texto
        except Exception as erro:                    # noqa: BLE001 — vai ao log
            _LOG.warning("Aviso de andamento sem o ajuste da casa: %s", erro)
    # O AJUSTE TORTO NÃO SAI (26/10/2026): o que já estava gravado antes desta
    # régua, ou o que entrou pelo encerramento/rodapé da atribuição — que a
    # tela não confere com `conferir` —, é medido aqui, na hora de mandar.
    ruim = _torto(texto) or _claros_ruins(parte, texto)
    if ruim:
        _LOG.warning("A parte ===%s=== do %s ajustado foi descartada (%s); saiu o padrão.",
                     parte, MODELO, ruim)
        texto = padrao.get(parte, "")
    try:
        return texto.format(**claros)
    except (KeyError, ValueError, IndexError, AttributeError) as erro:
        _LOG.warning("A parte ===%s=== do %s ajustado usa um claro que não existe (%s); "
                     "saiu o padrão.", parte, MODELO, erro)
        return padrao.get(parte, "").format(**claros)


def _br(iso: Any) -> str:
    d = _vencimento(iso)
    return d.strftime("%d/%m/%Y") if d else ""


def textos(evento: str, info: dict, serventia: dict, con: Any = None) -> tuple[str, str]:
    """O assunto e o corpo de um aviso. Só lê."""
    nome = str(serventia.get("unit_name") or "").strip() or "A serventia"
    assinatura = _montar("ASSINATURA", {
        "serventia": nome,
        "telefone": str(serventia.get("serventia_telefone") or "").strip() or "—",
        "email": str(serventia.get("serventia_email") or "").strip() or "—"}, con)
    claros = {"numero": info.get("numero") or "", "serventia": nome,
              "data_limite": _br(info.get("data_limite")),
              "dias": "" if info.get("dias") is None else str(info["dias"]),
              "assinatura": assinatura}
    return (_montar(f"{evento}_ASSUNTO", claros, con).strip(),
            _montar(evento, claros, con))


def conferir(corpo: str) -> str:
    """O papel que a tela de Modelos vai gravar monta? Devolve o erro, ou ``""``."""
    for parte, texto in _partir(corpo).items():
        try:
            texto.format(**dict.fromkeys(CLAROS[parte], ""))
        except (KeyError, ValueError, IndexError, AttributeError) as erro:
            return (f"A parte ==={parte}=== usa um claro que o aviso não tem ({erro}). Os que "
                    "ela tem: " + ", ".join("{" + c + "}" for c in CLAROS[parte]) + ".")
        ruim = _claros_ruins(parte, texto)
        if ruim:
            return f"A parte ==={parte}===: {ruim}"
        # 26/10/2026 (PR #26, M1): o texto sai sozinho ao cliente — ver
        # `_PROIBIDO_NO_AVISO`.
        o_que = _torto(texto)
        if o_que:
            return (f"A parte ==={parte}=== traz {o_que}. Este e-mail sai sozinho ao "
                    "cliente, sem ninguém conferir: ele só diz o andamento do "
                    "protocolo. Telefone e e-mail da serventia entram pelos claros "
                    "{telefone} e {email}; pagamento, valor e endereço de internet não "
                    "cabem nele.")
    return ""


# ------------------------------------------------------------------ o envio


def pendentes(con, *, max_tentativas: int = MAX_TENTATIVAS_PADRAO) -> list[dict]:
    """O que está na fila: na fila, sem configuração, ou falhou e ainda se tenta."""
    return banco(con).ler(
        """SELECT a.*, COALESCE(c.ativo, 0) AS consentimento_ativo
             FROM av_avisos a LEFT JOIN av_consentimentos c ON c.id = a.consentimento_id
            WHERE a.situacao IN (%s, %s) OR (a.situacao = %s AND a.tentativas < %s)
            ORDER BY a.id""",
        (AS.PENDENTE, AS.PENDENTE_CONFIG, AS.FALHOU, int(max_tentativas)))


def _gravar(db, aviso_id: int, *, situacao: str, agora: datetime, erro: str | None = None,
            assunto: str | None = None, tentou: bool = False) -> None:
    with db.transaction() as con:
        banco(con).escrever(
            """UPDATE av_avisos SET situacao=%s, erro=%s,
                   assunto=COALESCE(%s, assunto),
                   tentativas = tentativas + %s,
                   tentado_em = CASE WHEN %s THEN %s ELSE tentado_em END,
                   enviado_em = CASE WHEN %s THEN %s ELSE enviado_em END
             WHERE id=%s""",
            (situacao, (erro or None) and str(erro)[:500], assunto, 1 if tentou else 0,
             tentou, _iso(agora), situacao == AS.ENVIADO, _iso(agora), int(aviso_id)))


def enviar_pendentes(db, *, agora: datetime, pasta_dados: Any, vigentes: dict[str, dict],
                     max_tentativas: int = MAX_TENTATIVAS_PADRAO) -> dict:
    """Manda o que está na fila. **A rede fica fora de toda transação.**

    Devolve a contagem por situação final desta rodada."""
    import automacao_avisos as AV
    import serventia as SERV
    with db.connect() as con:
        fila = pendentes(con, max_tentativas=max_tentativas)
        cfg = AV.configuracao_de_email(con)
    conta = {AS.ENVIADO: 0, AS.FALHOU: 0, AS.PENDENTE_CONFIG: 0, AS.DESCARTADO: 0}
    if not fila:
        return conta
    serventia = SERV.dados(db.get_settings)
    senha: list[str] = []
    for a in fila:
        if not a["consentimento_ativo"]:
            _gravar(db, a["id"], situacao=AS.DESCARTADO, agora=agora,
                    erro="o cliente desmarcou o aviso antes de ele sair")
            conta[AS.DESCARTADO] += 1
            continue
        if a["chave"] not in vigentes:
            _gravar(db, a["id"], situacao=AS.DESCARTADO, agora=agora,
                    erro="o andamento não é mais verdade (nota cumprida, protocolo entregue, "
                         "prazo vencido ou evento desligado) — não sai atrasado")
            conta[AS.DESCARTADO] += 1
            continue
        if a["canal"] == AS.WHATSAPP:
            if a["situacao"] != AS.PENDENTE_CONFIG or a["erro"] != SEM_MODELO_DA_META:
                _gravar(db, a["id"], situacao=AS.PENDENTE_CONFIG, agora=agora,
                        erro=SEM_MODELO_DA_META)
            conta[AS.PENDENTE_CONFIG] += 1
            continue
        if not cfg["host"]:
            if a["situacao"] != AS.PENDENTE_CONFIG:
                _gravar(db, a["id"], situacao=AS.PENDENTE_CONFIG, agora=agora, erro=SEM_SMTP)
            conta[AS.PENDENTE_CONFIG] += 1
            continue
        with db.connect() as con:
            assunto, corpo = textos(a["evento"], vigentes[a["chave"]], serventia, con)
        try:
            if not senha:
                senha.append(AV._senha_do_smtp(pasta_dados, cfg))
            AV.ENVIO["email"](dict(cfg, destinos=[a["destino"]]), senha[0],
                              assunto=assunto, corpo=corpo)
        except Exception as erro:                 # noqa: BLE001 — registra e segue
            _gravar(db, a["id"], situacao=AS.FALHOU, agora=agora, assunto=assunto,
                    erro=f"{type(erro).__name__}: {erro}", tentou=True)
            conta[AS.FALHOU] += 1
            continue
        _gravar(db, a["id"], situacao=AS.ENVIADO, agora=agora, assunto=assunto, tentou=True)
        conta[AS.ENVIADO] += 1
    return conta


# ------------------------------------------------------------------ o processo da automação


def _parametros(p: dict) -> tuple[int, int, tuple[str, ...]]:
    try:
        dias = int(p.get("dias_antes", DIAS_ANTES_PADRAO))
    except (TypeError, ValueError):
        dias = DIAS_ANTES_PADRAO
    dias = max(DIAS_ANTES_LIMITES[0], min(DIAS_ANTES_LIMITES[1], dias))
    try:
        tent = max(1, min(10, int(p.get("max_tentativas", MAX_TENTATIVAS_PADRAO))))
    except (TypeError, ValueError):
        tent = MAX_TENTATIVAS_PADRAO
    pedidos = p.get("eventos")
    eventos = tuple(e for e in AS.EVENTOS if pedidos is None or e in pedidos)
    return dias, tent, eventos


def rodar(ctx) -> dict:
    """O processo AVISOS_ANDAMENTO: mede, enfileira e manda. Relato em números."""
    import automacao_processos as PROC
    import automacao_schema as SCH
    with ctx.db.transaction() as con:
        AS.init_andamento_schema(con)
    dias, tentativas, eventos = _parametros(ctx.parametros)
    with ctx.db.connect() as con:
        vigentes = eventos_vigentes(con, hoje=ctx.hoje, feriados=ctx.feriados(),
                                    dias_antes=dias, eventos=eventos)
    with ctx.db.transaction() as con:
        novos = enfileirar(con, vigentes, agora=ctx.agora)
    conta = enviar_pendentes(ctx.db, agora=ctx.agora, pasta_dados=ctx.pasta_dados,
                             vigentes=vigentes, max_tentativas=tentativas)
    with ctx.db.connect() as con:
        email_sem_config = int(banco(con).valor(
            "SELECT COUNT(*) FROM av_avisos WHERE canal=%s AND situacao=%s",
            (AS.EMAIL, AS.PENDENTE_CONFIG)) or 0)
        whats = int(banco(con).valor(
            "SELECT COUNT(*) FROM av_avisos WHERE canal=%s AND situacao=%s",
            (AS.WHATSAPP, AS.PENDENTE_CONFIG)) or 0)
    por_evento = {e: sum(1 for v in vigentes.values() if v["evento"] == e) for e in eventos}
    relato = (f"Andamentos vigentes: {por_evento.get(AS.EXIGENCIA, 0)} exigência(s), "
              f"{por_evento.get(AS.PRONTO, 0)} pronto(s) para retirar, "
              f"{por_evento.get(AS.PRAZO, 0)} prenotação(ões) a até {dias} dia(s) útil(eis) do "
              f"vencimento. Avisos novos na fila: {novos}. Nesta rodada: "
              f"{conta[AS.ENVIADO]} enviado(s), {conta[AS.FALHOU]} falha(s), "
              f"{conta[AS.DESCARTADO]} descartado(s). Esperando configuração: "
              f"{email_sem_config} por e-mail, {whats} por WhatsApp (sem modelo da Meta).")
    achados = [{"vigentes": por_evento, "novos": novos, **{k.lower(): v for k, v in conta.items()},
                "email_sem_config": email_sem_config, "whatsapp_sem_modelo": whats}]
    acoes = ([{"acao": "mandou avisos de andamento por e-mail", "quantos": conta[AS.ENVIADO]}]
             if conta[AS.ENVIADO] else [])
    if conta[AS.FALHOU]:
        return PROC.resultado(SCH.AVISO, relato + " Veja as falhas em Avisos ao cliente.",
                              achados, acoes)
    if email_sem_config:
        return PROC.resultado(SCH.AVISO, relato + " Configure o SMTP em Automação → Configuração.",
                              achados, acoes)
    return PROC.resultado(SCH.OK, relato, achados, acoes)


_UTEIS = [0, 1, 2, 3, 4]

#: O processo que este módulo traz para a central (`automacao_processos.
#: MODULOS_COM_PROCESSOS`). Nasce DESLIGADO, como todos.
CATALOGO = (
    {"codigo": "AVISOS_ANDAMENTO", "nome": "Avisos de andamento ao cliente", "setor": "GESTAO",
     "funcao": "andamento_avisos.rodar", "timeout_s": 600,
     "agenda": {"dias": _UTEIS, "intervalo_min": 15, "janela": ["08:00", "18:00"]},
     "parametros": {"dias_antes": DIAS_ANTES_PADRAO, "max_tentativas": MAX_TENTATIVAS_PADRAO,
                    "eventos": list(AS.EVENTOS)},
     "descricao": "De 15 em 15 minutos, em dia útil: avisa o cliente que pediu (consentimento "
                  "gravado no protocolo) da exigência na prenotação, do protocolo pronto para "
                  "retirar e da prenotação a N dias úteis de vencer. Só o status — sem CPF, "
                  "valor nem teor. E-mail pelo SMTP da automação; WhatsApp fica registrado e "
                  "PENDENTE_CONFIG até haver modelo aprovado pela Meta. Protesto fica de fora."},
)


def __getattr__(nome: str):
    """`MODELO_AVISO_ANDAMENTO`, o nome do papel no catálogo, lido da base. Só lê."""
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
