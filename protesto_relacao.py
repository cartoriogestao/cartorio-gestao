"""A CERTIDÃO DIÁRIA EM FORMA DE RELAÇÃO — o que a casa conta às entidades de crédito.

Lote LG05 (19/10/2026). Lei 9.492/1997, art. 29, e o Código de Normas do
Maranhão (Prov. COGEX 28/2026), art. 949: os tabelionatos «fornecerão, quando
solicitadas, certidões diárias, em forma de relação, às entidades
representativas da indústria e do comércio ou às instituições vinculadas à
proteção do crédito, contendo os protestos lavrados e os cancelamentos
efetuados, com a observação de tratar-se de informação reservada».

O CAMINHO ESCOLHIDO — E POR QUÊ
    O texto que manda aqui é o do Maranhão (o PDF em `referencia/`), e ele põe
    a relação **entidade por entidade**: só recebe quem se habilitou antes
    (§ 1º), a casa suspende quem descumprir o sigilo (§ 3º), cada registro
    incluído é emolumento (§ 4º) e o dia sem nada gera certidão negativa
    (§ 5º). Por isso o controle é por entidade — Serasa, Boa Vista, a
    associação comercial que pedir —, e cada entidade diz o seu CANAL:

      DIRETO   a casa entrega à entidade (balcão, e-mail, portal dela) e
               registra a entrega com o comprovante;
      CENPROT  a relação sobe pela Central, quando a entidade estiver
               habilitada lá. O Código Nacional de Normas (Prov. CNJ 149/2023)
               trata da CENPROT como canal das informações do protesto —
               dispositivo exato: «conferir no texto oficial».

    O ENVIO PELA CENPROT ESTÁ DESLIGADO, e fica assim até haver credencial e o
    serviço medido. A configuração (`protesto_relacao_envio`) é do ADMIN, nasce
    DESLIGADO, e tem HOMOLOGACAO — que envia e NÃO conta como entrega — e
    PRODUCAO. O transporte de verdade (`TransporteCenprot`) confere a
    credencial no cofre das Centrais (`centrais_cred`, fora do banco e fora do
    log) e recusa com frase de balcão: o endereço do serviço não está medido,
    e inventá-lo seria a casa achar que entregou. O teste usa o
    `TransporteFalso`, sem rede.

A RELAÇÃO É DO DIA QUE JÁ FECHOU
    Gerar hoje a relação de hoje perderia o protesto lavrado à tarde — e a
    relação congela. Só se gera de dia anterior a hoje, e uma por entidade e
    dia (UNIQUE): a segunda pedida devolve a primeira, com o mesmo teor.

O QUE NÃO ENTRA
    Ato cancelado (o selo que não saiu desfez o ato) e o protesto com os
    efeitos suspensos por ordem judicial na hora de gerar: a publicidade dele
    está parada, e a relação é publicidade (§ 2º). A relação diz quantos
    ficaram de fora por isso.

O QUE NÃO FAZ
    Não cobra. O § 4º manda cobrar por registro incluído, e `registros` está
    na linha; o item da tabela é escolha do caixa, como em toda certidão.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Any

import protesto as PT
from bd_nativo import banco
from caixa_schema import reais
from cpf_cnpj import cnpj_valido, so_digitos
from ri_schema import eh_dia_util

CANAIS = {"DIRETO": "entrega direta à entidade",
          "CENPROT": "pela CENPROT, com a entidade habilitada lá"}

FORMAS_DE_ENTREGA = {
    "PRESENCIAL": "em mãos, no balcão",
    "EMAIL": "por e-mail",
    "PORTAL": "pelo portal da entidade",
    "CENPROT": "pela CENPROT",
}

CHAVE_DO_ENVIO = "protesto_relacao_envio"
MODOS_DE_ENVIO = ("DESLIGADO", "HOMOLOGACAO", "PRODUCAO")
ENVIO_DE_FABRICA = "DESLIGADO"

TRAVA_DO_NUMERO = "pt_relacoes_diarias.numero"

AVISO_DE_RESERVA = ("INFORMAÇÃO RESERVADA — vedada a sua divulgação pela "
                    "imprensa, ainda que parcial (CN-MA art. 949, caput).")
FUNDAMENTO = "Lei 9.492/1997, art. 29; CN-MA (Prov. COGEX 28/2026), art. 949"


class RelacaoError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcão."""


def _br(dia: Any) -> str:
    try:
        return date.fromisoformat(str(dia or "")[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(dia or "—")


def _dia(valor: Any, rotulo: str) -> str:
    try:
        return date.fromisoformat(str(valor or "")[:10]).isoformat()
    except ValueError:
        raise RelacaoError(f"Informe {rotulo} (AAAA-MM-DD).") from None


# -------------------------------------------------------------- as entidades


def habilitar_entidade(con, *, nome: str, documento: str, canal: str,
                       habilitacao: str, habilitada_em: str, agora: str,
                       contato: str | None = None,
                       usuario: str | None = None) -> int:
    """Cadastra a entidade habilitada a receber a relação (§ 1º). ESCREVE.

    O CNPJ é conferido pelo dígito, e a habilitação — o pedido ou o processo
    em que ela se deu — é obrigatória: é a prova do § 1º, e a primeira coisa
    que a Corregedoria pergunta quando uma entidade publica o que não devia.
    """
    quem = " ".join(str(nome or "").split())
    if len(quem) < 3:
        raise RelacaoError("Informe o nome da entidade.")
    cnpj = so_digitos(documento)
    if not cnpj_valido(cnpj):
        raise RelacaoError(f"O CNPJ {documento!r} não confere pelo dígito.")
    via = str(canal or "").strip().upper()
    if via not in CANAIS:
        raise RelacaoError(
            f"Canal desconhecido: {canal!r}. Os que existem: {', '.join(CANAIS)}.")
    prova = " ".join(str(habilitacao or "").split())
    if len(prova) < 5:
        raise RelacaoError(
            "Informe o pedido ou o processo da habilitação (CN-MA art. 949, "
            "§ 1º): a entidade só recebe se se habilitou antes.")
    desde = _dia(habilitada_em, "o dia da habilitação")
    bd = banco(con)
    novo = bd.escrever(
        """INSERT INTO pt_relacao_entidades(nome, documento, canal, habilitacao,
               habilitada_em, contato, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (documento) DO NOTHING RETURNING id""",
        (quem, cnpj, via, prova, desde, (contato or "").strip() or None, agora,
         usuario))
    if not novo:
        raise RelacaoError(f"O CNPJ {cnpj} já está cadastrado.")
    return int(novo[0]["id"])


def suspender_entidade(con, entidade_id: int, *, motivo: str, agora: str,
                       usuario: str | None = None) -> dict:
    """Suspende o fornecimento à entidade (§ 3º). ESCREVE.

    A suspensão não apaga nada: as relações que já foram para ela continuam
    sendo dela, e o § 3º manda comunicar o juiz corregedor — o que a tela
    lembra, e o sistema não faz sozinho.
    """
    razao = " ".join(str(motivo or "").split())
    if len(razao) < 10:
        raise RelacaoError(
            "Escreva o motivo da suspensão — sigilo descumprido ou protesto "
            "cancelado divulgado (CN-MA art. 949, § 3º).")
    bd = banco(con)
    bd._escrita()
    ent = bd.um("SELECT * FROM pt_relacao_entidades WHERE id=%s FOR UPDATE",
                (int(entidade_id),))
    if not ent:
        raise RelacaoError(f"Entidade {entidade_id} não encontrada.")
    if ent["situacao"] == "SUSPENSA":
        raise RelacaoError(f"A entidade {ent['nome']} já está suspensa.")
    bd.escrever(
        """UPDATE pt_relacao_entidades
              SET situacao='SUSPENSA', motivo_suspensao=%s, suspensa_em=%s,
                  suspensa_por=%s
            WHERE id=%s""", (razao, agora, usuario, int(entidade_id)))
    return {"entidade_id": int(entidade_id), "nome": ent["nome"]}


def entidades(con) -> list[dict]:
    """As entidades, as habilitadas primeiro. Só LÊ."""
    return banco(con).ler(
        """SELECT * FROM pt_relacao_entidades
            ORDER BY (situacao = 'HABILITADA') DESC, nome, id""")


# -------------------------------------------------------------- a relação


def itens_do_dia(con, dia: str) -> dict:
    """Os protestos lavrados e os cancelamentos efetuados no dia. Só LÊ.

    Uma linha por DEVEDOR: a restrição é da pessoa, e o título com dois
    devedores restringe os dois. Devolve também `suspensos` — os protestos que
    ficaram de fora por ordem judicial.
    """
    d = _dia(dia, "o dia")
    seguinte = (date.fromisoformat(d) + timedelta(days=1)).isoformat()
    bd = banco(con)
    atos = bd.ler(
        """SELECT a.id AS ato_id, a.tipo, a.data_ato, a.rotulo, a.numero_ordem,
                  t.id AS titulo_id, t.protocolo, t.especie, t.numero_titulo,
                  t.valor_centavos, t.saldo_centavos, t.data_vencimento
             FROM pt_atos a
             JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.tipo IN ('PROTESTO','CANCELAMENTO') AND a.cancelado = 0
              AND a.data_ato >= %s AND a.data_ato < %s
            ORDER BY a.data_ato, a.id""", (d, seguinte))
    itens, suspensos = [], 0
    protestos = cancelamentos = 0
    for a in atos:
        if a["tipo"] == "PROTESTO" and PT.efeito_suspensivo_em_vigor(bd, a["titulo_id"]):
            suspensos += 1
            continue
        if a["tipo"] == "PROTESTO":
            protestos += 1
        else:
            cancelamentos += 1
        valor = int(a["saldo_centavos"] or 0) or int(a["valor_centavos"] or 0)
        devedores = bd.ler(
            """SELECT nome, documento_numero FROM pt_devedores
                WHERE titulo_id=%s ORDER BY id""", (a["titulo_id"],))
        for dev in devedores:
            itens.append({
                "letra": "P" if a["tipo"] == "PROTESTO" else "C",
                "ato_id": int(a["ato_id"]), "titulo_id": int(a["titulo_id"]),
                "dia": d, "protocolo": a["protocolo"] or "",
                "especie": a["especie"] or "",
                "numero_titulo": a["numero_titulo"] or "",
                "vencimento": str(a["data_vencimento"] or "")[:10],
                "valor_centavos": valor, "nome": dev["nome"] or "",
                "documento": so_digitos(dev["documento_numero"]),
            })
    return {"dia": d, "itens": itens, "protestos": protestos,
            "cancelamentos": cancelamentos, "suspensos": suspensos}


def _teor(*, numero: int, ano: int, dia: str, entidade: dict, sv: dict,
          achado: dict) -> str:
    linhas = [
        f"CERTIDÃO DIÁRIA EM FORMA DE RELAÇÃO Nº {numero}/{ano}",
        FUNDAMENTO,
        str(sv.get("unit_name") or "Serventia"),
        f"Dia: {_br(dia)}",
        f"Entidade: {entidade['nome']} — CNPJ {entidade['documento']}",
        AVISO_DE_RESERVA,
    ]
    if not achado["itens"]:
        linhas.append("CERTIDÃO NEGATIVA: não houve protesto lavrado nem "
                      "cancelamento efetuado neste dia (CN-MA art. 949, § 5º).")
    else:
        # A DATA DO VENCIMENTO É COLUNA DA RELAÇÃO (LD04) — CNN art. 130: a
        # certidão em forma de relação traz «espécie do título ou documento de
        # dívida, data do vencimento da dívida, data do protesto da dívida e
        # valor protestado». Até 21/10/2026 o vencimento não saía. Título sem
        # vencimento (à vista) sai com a coluna vazia, e não com data inventada.
        #
        # E ELE VAI NO FIM (LD11, revisão do LD04): a entidade que lê a relação
        # por posição continua achando as oito colunas de antes no mesmo lugar.
        # No meio, ela passava a ler a data do vencimento como o valor.
        linhas.append("TIPO;DIA;PROTOCOLO;ESPECIE;TITULO;VALOR;DEVEDOR;"
                      "DOCUMENTO;VENCIMENTO")
        for i in achado["itens"]:
            linhas.append(";".join([
                i["letra"], _br(i["dia"]), i["protocolo"], i["especie"],
                i["numero_titulo"], reais(i["valor_centavos"]), i["nome"],
                i["documento"],
                _br(i["vencimento"]) if i.get("vencimento") else ""]))
        linhas.append(f"P = protesto lavrado ({achado['protestos']}); "
                      f"C = cancelamento efetuado ({achado['cancelamentos']}).")
    if achado["suspensos"]:
        linhas.append(f"{achado['suspensos']} protesto(s) com os efeitos "
                      f"suspensos por ordem judicial não entram nesta relação.")
    return "\n".join(linhas) + "\n"


def gerar_relacao(con, *, dia: str, entidade_id: int, hoje: str, agora: str,
                  sv: dict, usuario: str | None = None) -> dict:
    """Gera a relação do dia para a entidade. ESCREVE (ou devolve a que já há).

    A TRAVA VEM ANTES DA CONFERÊNCIA: duas pessoas gerando a mesma relação
    leriam as duas «não há» e numerariam duas. Com ela, a segunda acha a
    primeira e a devolve com `ja_existia`.
    """
    d = _dia(dia, "o dia da relação")
    if d >= str(hoje)[:10]:
        raise RelacaoError(
            "A relação é do dia que já fechou: gerar hoje a de hoje perderia o "
            "protesto lavrado depois, e a relação congela.")
    bd = banco(con)
    bd.travar(TRAVA_DO_NUMERO)
    ent = bd.um("SELECT * FROM pt_relacao_entidades WHERE id=%s",
                (int(entidade_id),))
    if not ent:
        raise RelacaoError(f"Entidade {entidade_id} não encontrada.")
    ja = bd.um(
        "SELECT * FROM pt_relacoes_diarias WHERE dia=%s AND entidade_id=%s",
        (d, int(entidade_id)))
    if ja:
        return {**ja, "relacao_id": int(ja["id"]), "ja_existia": True}
    if ent["situacao"] != "HABILITADA":
        raise RelacaoError(
            f"A entidade {ent['nome']} está {ent['situacao']} — o fornecimento "
            f"está suspenso (CN-MA art. 949, § 3º).")
    if d < str(ent["habilitada_em"])[:10]:
        raise RelacaoError(
            f"A entidade {ent['nome']} se habilitou em "
            f"{_br(ent['habilitada_em'])}: a relação de dia anterior não é dela "
            f"(CN-MA art. 949, § 1º).")
    achado = itens_do_dia(bd, d)
    ano = int(str(hoje)[:4])
    numero = int(bd.valor(
        "SELECT coalesce(max(numero), 0) + 1 AS n FROM pt_relacoes_diarias "
        "WHERE ano=%s", (ano,)))
    teor = _teor(numero=numero, ano=ano, dia=d, entidade=ent, sv=sv,
                 achado=achado)
    registros = achado["protestos"] + achado["cancelamentos"]
    relacao_id = int(bd.escrever(
        """INSERT INTO pt_relacoes_diarias(numero, ano, dia, entidade_id,
               protestos, cancelamentos, registros, negativa, itens_json, teor,
               hash_teor, gerada_em, gerada_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (numero, ano, d, int(entidade_id), achado["protestos"],
         achado["cancelamentos"], registros, int(not achado["itens"]),
         json.dumps(achado["itens"], ensure_ascii=False), teor,
         hashlib.sha256(teor.encode("utf-8")).hexdigest(), agora,
         usuario))[0]["id"])
    return {"relacao_id": relacao_id, "numero": numero, "ano": ano, "dia": d,
            "registros": registros, "negativa": not achado["itens"],
            "suspensos": achado["suspensos"], "ja_existia": False}


def relacao(con, relacao_id: int) -> dict | None:
    """A relação e a entidade dela. Só LÊ."""
    return banco(con).um(
        """SELECT r.*, e.nome AS entidade_nome, e.documento AS entidade_documento,
                  e.canal AS entidade_canal
             FROM pt_relacoes_diarias r
             JOIN pt_relacao_entidades e ON e.id = r.entidade_id
            WHERE r.id=%s""", (int(relacao_id),))


def relacoes(con, limite: int = 60) -> list[dict]:
    """As relações, da mais nova para a mais velha. Só LÊ."""
    return banco(con).ler(
        """SELECT r.*, e.nome AS entidade_nome, e.canal AS entidade_canal
             FROM pt_relacoes_diarias r
             JOIN pt_relacao_entidades e ON e.id = r.entidade_id
            ORDER BY r.dia DESC, r.id DESC LIMIT %s""", (int(limite),))


def registrar_entrega(con, relacao_id: int, *, forma: str, comprovante: str,
                      entregue_em: str, agora: str,
                      usuario: str | None = None) -> dict:
    """Registra que a relação chegou à entidade. ESCREVE.

    Entrega sem comprovante é entrega que ninguém prova — o recibo, o e-mail
    enviado, o protocolo do portal. E não se entrega duas vezes: a segunda
    apagaria a prova da primeira.
    """
    via = str(forma or "").strip().upper()
    if via not in FORMAS_DE_ENTREGA:
        raise RelacaoError(
            f"Forma de entrega desconhecida: {forma!r}. As que existem: "
            f"{', '.join(FORMAS_DE_ENTREGA.values())}.")
    prova = " ".join(str(comprovante or "").split())
    if len(prova) < 3:
        raise RelacaoError("Informe o comprovante da entrega.")
    quando = _dia(entregue_em, "o dia da entrega")
    bd = banco(con)
    bd._escrita()
    r = bd.um("SELECT * FROM pt_relacoes_diarias WHERE id=%s FOR UPDATE",
              (int(relacao_id),))
    if not r:
        raise RelacaoError(f"Relação {relacao_id} não encontrada.")
    if r["entregue_em"]:
        raise RelacaoError(
            f"A relação {r['numero']}/{r['ano']} já foi entregue em "
            f"{_br(r['entregue_em'])}.")
    if quando < str(r["gerada_em"])[:10]:
        raise RelacaoError("A entrega não pode ser anterior à geração.")
    bd.escrever(
        """UPDATE pt_relacoes_diarias
              SET forma_entrega=%s, comprovante_entrega=%s, entregue_em=%s,
                  entregue_por=%s
            WHERE id=%s""", (via, prova, quando, usuario, int(relacao_id)))
    return {"relacao_id": int(relacao_id), "numero": r["numero"], "forma": via}


def a_entregar(con) -> list[dict]:
    """As relações geradas e ainda não entregues, da mais velha. Só LÊ."""
    return banco(con).ler(
        """SELECT r.*, e.nome AS entidade_nome, e.canal AS entidade_canal
             FROM pt_relacoes_diarias r
             JOIN pt_relacao_entidades e ON e.id = r.entidade_id
            WHERE r.entregue_em IS NULL
            ORDER BY r.dia, r.id""")


def dias_sem_relacao(con, *, hoje: str, feriados: set[date] | None = None,
                     janela: int = 30) -> list[dict]:
    """Os dias úteis já fechados sem relação gerada, por entidade habilitada.

    Só LÊ. A janela é dos últimos `janela` dias — o controle diário cobra o
    que está para trás, e não o ano inteiro de antes da implantação.
    """
    bd = banco(con)
    hoje_d = date.fromisoformat(str(hoje)[:10])
    inicio = hoje_d - timedelta(days=janela)
    saida = []
    for ent in bd.ler(
            """SELECT * FROM pt_relacao_entidades WHERE situacao='HABILITADA'
                ORDER BY nome, id"""):
        desde = max(inicio, date.fromisoformat(str(ent["habilitada_em"])[:10]))
        feitos = {str(r["dia"])[:10] for r in bd.ler(
            "SELECT dia FROM pt_relacoes_diarias WHERE entidade_id=%s ORDER BY dia",
            (int(ent["id"]),))}
        faltam = []
        d = desde
        while d < hoje_d:
            if eh_dia_util(d, feriados or set()) and d.isoformat() not in feitos:
                faltam.append(d.isoformat())
            d += timedelta(days=1)
        if faltam:
            saida.append({"entidade_id": int(ent["id"]), "nome": ent["nome"],
                          "dias": faltam})
    return saida


# ------------------------------------------------------------------ o envio


def modo_de_envio(con) -> str:
    """O que a configuração diz do envio pela CENPROT. Só LÊ.

    Valor que não se reconhece vale DESLIGADO: é o lado seguro, porque
    configuração estragada não pode LIGAR um envio que ninguém ligou.
    """
    bd = banco(con)
    if not bd.tem_tabela("settings"):
        return ENVIO_DE_FABRICA
    linha = bd.um("SELECT value FROM settings WHERE key=%s", (CHAVE_DO_ENVIO,))
    valor = str((linha or {}).get("value") or "").strip().upper()
    return valor if valor in MODOS_DE_ENVIO else ENVIO_DE_FABRICA


class TransporteFalso:
    """A CENPROT de mentira, para teste — sem rede, e guarda o que recebeu."""

    def __init__(self, *, recusar: str | None = None):
        self.enviados: list[dict] = []
        self.recusar = recusar

    def enviar(self, *, ambiente: str, nome_arquivo: str, conteudo: bytes,
               entidade: dict) -> dict:
        if self.recusar:
            raise RelacaoError(self.recusar)
        self.enviados.append({"ambiente": ambiente, "nome_arquivo": nome_arquivo,
                              "conteudo": conteudo,
                              "entidade": entidade.get("documento")})
        return {"protocolo": f"FALSO-{len(self.enviados)}",
                "mensagem": "recebido pelo serviço falso"}


class TransporteCenprot:
    """O envio de verdade — que hoje RECUSA, de propósito.

    Confere a credencial no cofre das Centrais (fora do banco e do log) e para
    aí: o serviço da CENPROT para a certidão em relação não está medido nesta
    casa, e um envio a endereço suposto faria o sistema registrar entrega que
    não houve. No dia em que o contrato for medido, o pedido entra aqui.
    """

    def enviar(self, *, ambiente: str, nome_arquivo: str, conteudo: bytes,
               entidade: dict) -> dict:
        import centrais_cred as CENTCRED
        # A HOMOLOGAÇÃO DA CENPROT NÃO SE USA DESDE 14/10/2026 — ordem do
        # oficial, guardada em `centrais_cred.ambiente_de_uso`. O modo existe
        # aqui para o serviço falso; contra a Central, a régua da casa recusa.
        try:
            CENTCRED.ambiente_de_uso("CENPROT", ambiente)
        except CENTCRED.CredencialError as erro:
            raise RelacaoError(str(erro)) from None
        if not CENTCRED.tem("CENPROT", ambiente):
            raise RelacaoError(
                f"Sem credencial da CENPROT para {ambiente.lower()} — cadastre "
                f"em Configurações → Centrais, ou entregue a relação à mão e "
                f"registre a entrega.")
        raise RelacaoError(
            "O serviço da CENPROT para a certidão em relação ainda não está "
            "medido nesta casa, e o envio não sai. Entregue a relação pelo "
            "canal da entidade e registre a entrega.")


def enviar(con, relacao_id: int, *, transporte, agora: str,
           usuario: str | None = None) -> dict:
    """Manda a relação pela CENPROT, se o envio estiver ligado. ESCREVE.

    DESLIGADO recusa sem tocar no transporte. HOMOLOGACAO envia e guarda a
    resposta, mas NÃO conta como entrega — a entidade não recebeu nada de
    verdade. PRODUCAO envia e registra a entrega com o protocolo da Central.
    O que se guarda da resposta é o protocolo e a mensagem, e mais nada.
    """
    modo = modo_de_envio(con)
    if modo == "DESLIGADO":
        raise RelacaoError(
            "O envio pela CENPROT está desligado (Configurações do Protesto → "
            "certidão em relação). Entregue a relação pelo canal da entidade "
            "e registre a entrega.")
    bd = banco(con)
    bd._escrita()
    r = bd.um("SELECT * FROM pt_relacoes_diarias WHERE id=%s FOR UPDATE",
              (int(relacao_id),))
    if not r:
        raise RelacaoError(f"Relação {relacao_id} não encontrada.")
    ent = bd.um("SELECT * FROM pt_relacao_entidades WHERE id=%s",
                (int(r["entidade_id"]),))
    if ent["canal"] != "CENPROT":
        raise RelacaoError(
            f"A entidade {ent['nome']} recebe direto, e não pela CENPROT.")
    if r["entregue_em"]:
        raise RelacaoError(
            f"A relação {r['numero']}/{r['ano']} já foi entregue em "
            f"{_br(r['entregue_em'])}.")
    resposta = transporte.enviar(
        ambiente=modo, nome_arquivo=f"relacao_{r['dia']}_{ent['documento']}.txt",
        conteudo=str(r["teor"]).encode("utf-8"), entidade=dict(ent))
    guardado = {k: str(resposta.get(k) or "") for k in ("protocolo", "mensagem")}
    if modo == "PRODUCAO":
        bd.escrever(
            """UPDATE pt_relacoes_diarias
                  SET envio_ambiente=%s, envio_resposta=%s, envio_erro=NULL,
                      forma_entrega='CENPROT', comprovante_entrega=%s,
                      entregue_em=%s, entregue_por=%s
                WHERE id=%s""",
            (modo, json.dumps(guardado, ensure_ascii=False),
             guardado["protocolo"] or "sem protocolo", str(agora)[:10], usuario,
             int(relacao_id)))
    else:
        bd.escrever(
            """UPDATE pt_relacoes_diarias
                  SET envio_ambiente=%s, envio_resposta=%s, envio_erro=NULL
                WHERE id=%s""",
            (modo, json.dumps(guardado, ensure_ascii=False), int(relacao_id)))
    return {"relacao_id": int(relacao_id), "ambiente": modo,
            "entregue": modo == "PRODUCAO", **guardado}
