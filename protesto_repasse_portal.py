"""O ROBÔ DO BOLETO DE REPASSE — emite no portal da CRA, registra a guia, e
deixa o pagamento para o oficial.

Ordem do oficial (29/10/2026): «as guias, configure para a automação emitir.
Posso colocar as senhas no cofre pra entrar.» O boleto de repasse do título
da CRA SÓ sai do portal (menu Retorno → «Boletos de repasse»), e nasce do
RETORNO com a ocorrência «pago», um por data de retorno e conta. O transporte
e a leitura da página moram em `cra_portal`; aqui mora o que se decide e o
que se grava.

O PROCESSO — PROTESTO_REPASSE_BOLETO_CRA (central de automação)
    Nasce DESLIGADO. A agenda de fábrica é 14:30 nos dias úteis — depois do
    retorno do dia (11:30) e da confirmação (14:10); o boleto do retorno
    costuma aparecer em «Boletos pendentes de geração» no dia útil seguinte
    ao envio (o lido em 29/10/2026: retorno enviado numa sexta, boleto com
    retorno da segunda), e a rodada diária o apanha.

    Sem «pode agir», ele ENTRA E LÊ: diz o que está pendente de geração, que
    boleto não tem guia e qual foi pago — e não clica nem grava nada. É assim
    que se confere, na primeira vez, que a leitura do portal está certa.

    Com «pode agir»:
      1. clica «GERAR BOLETO» para cada conta com movimento pendente — e ANTES
         do clique grava a marca da geração em curso. Gerou e não confirmou
         (o boleto novo não apareceu na lista)? A marca fica, e o robô NUNCA
         gera de novo sozinho para aquela conta: diz para conferir no portal
         e gerar à mão. O boleto que aparecer depois resolve a marca;
      2. para cada boleto «AGUARDANDO PAGAMENTO» que ainda não é guia no
         sistema: baixa o PDF, lê a linha digitável (a régua da casa,
         `despesas.ler_codigo_de_barras`), confere o valor do PDF contra o da
         lista, acha os pagamentos daquele retorno e confere a soma. Bateu: a
         guia nasce REGISTRADA, com o nosso número de identificador e o PDF
         anexado, e o boleto vai às despesas AGUARDANDO A AUTORIZAÇÃO do
         oficial. Não bateu: ERRO com o motivo, e nada se registra;
      3. para cada boleto que o portal mostra «PAGO» e é guia no sistema:
         marca a guia paga (prova: a situação no portal; o dia é o da despesa
         paga, quando há) e a concilia pelo valor do portal.

O ROBÔ NUNCA PAGA. Não importa nada do banco, e há teste que confere. O
pagamento é o clique do oficial na despesa — o mesmo de toda despesa.

AS PARADAS
    - CAPTCHA ou segundo fator: para, e a guia vira pendência «emita à mão»;
    - login recusado: para, sem tentar de novo (senha errada repetida
      bloqueia a conta);
    - cofre trancado ou sem o item: AVISO, e a rodada seguinte retoma;
    - sandbox: não entra — o portal não tem simulador;
    - página que mudou: ERRO, com o que faltou.

CADA PASSO VAI A `centrais_log` (central CRA), sem senha e sem corpo de
página; e cada gravação vai à auditoria com `agente` e `a_mando_de`.

A CENPROT FICA DESENHADA, E NÃO FEITA. `PORTAIS` é a mesa dos portais; a
liquidação da CENPROT entra quando se souber onde ela sai (o título liquidado
em 27/10/2026 o foi por TED pelo próprio portal). Só a CRA está aqui.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import cra_portal as CRA
import protesto_repasse as REP
from bd_nativo import banco
from caixa_schema import reais

CODIGO = "PROTESTO_REPASSE_BOLETO_CRA"
OPERACAO = "PORTAL_BOLETOS_REPASSE"
AGENTE = "automação — boleto de repasse da CRA"
QUEM = "automação (boleto de repasse da CRA)"
ORIGEM_DA_DESPESA = "AUTOMACAO:CRA_REPASSE"
CATEGORIA_DA_DESPESA = "REPASSE_APRESENTANTE"
ENTIDADE_DO_ANEXO = "pt_repasse_guias"
#: Do envio do retorno à data de retorno que o boleto mostra: o lido em
#: 29/10/2026 foi de sexta a segunda. Quatro dias cobrem fim de semana e
#: feriado; além disso, não se casa.
JANELA_DO_RETORNO_DIAS = 4
CHAVE_DO_ESTADO = "geracao_incerta"

#: OS PORTAIS. Hoje um. Cada um diz onde fica, qual item do cofre usa e qual
#: módulo fala com ele. A CENPROT entra aqui quando se souber onde sai a
#: liquidação do título pago no cartório — e com o seu próprio módulo, porque
#: não é a mesma página.
PORTAIS: dict[str, dict[str, Any]] = {
    "CRA": {"modulo": "cra_portal", "cofre": CRA.NOME_NO_COFRE,
            "onde": "portal da CRA-MA, menu Retorno → «Boletos de repasse»",
            "url": CRA.URL_DO_PORTAL},
}

CATALOGO = (
    {"codigo": CODIGO,
     "nome": "Protesto — emitir o boleto de repasse no portal da CRA",
     "setor": "PROTESTO",
     "funcao": "protesto_repasse_portal.emitir_boletos_da_cra",
     "timeout_s": 300,
     "agenda": {"dias": [0, 1, 2, 3, 4], "horarios": ["14:30"]},
     "descricao": (
         "Entra no portal da CRA-MA com o usuário e a senha do cofre (item "
         "«cra_portal»), abre Retorno → «Boletos de repasse», gera o boleto de "
         "cada conta pendente, baixa o PDF, registra a guia e lança o boleto "
         "nas despesas para o oficial autorizar. NUNCA paga. Sem «pode agir», "
         "só entra e lê. CAPTCHA ou segundo fator: para.")},
)


class BoletoNaoConfere(ValueError):
    """O boleto não bate com o sistema — a frase diz onde."""


# ------------------------------------------------------------------ o banco


def guias_por_nosso_numero(con) -> dict[str, dict]:
    """As guias vivas, pelo nosso número que as identifica. Só LÊ.

    O identificador pode trazer mais de um nosso número (separados por
    vírgula, espaço ou ponto e vírgula): cada um aponta para a guia.
    """
    saida: dict[str, dict] = {}
    for g in banco(con).ler(
            """SELECT id, numero, ano, situacao, identificador, total_centavos
                 FROM pt_repasse_guias
                WHERE situacao <> 'CANCELADA' AND identificador IS NOT NULL"""):
        for parte in re.split(r"[,;\s]+", str(g["identificador"] or "")):
            digitos = CRA.so_digitos(parte)
            if len(digitos) >= 5:
                saida[digitos] = dict(g)
    return saida


def candidatos_da_cra(con, *, hoje: str) -> list[dict]:
    """Os pagamentos da CRA que um boleto pode pagar. Só LÊ.

    São os da CRA com o retorno do «pago» aceito, ainda sem guia registrada:
    os pendentes e os que estão numa relação GERADA. Cada um com o dia em que
    o retorno foi aceito (`retorno_em`) — é por ele que se casa com a data de
    retorno do boleto.
    """
    feriados = REP.feriados_da_casa(con)
    linhas: dict[int, dict] = {}
    for p in REP.pendentes(con, hoje=hoje, feriados=feriados, canal="IEPTB"):
        if REP.central_do_titulo(p["origem"]) == "CRA" and p["retorno_aceito"]:
            linhas[int(p["ato_id"])] = {
                "ato_id": int(p["ato_id"]), "titulo_id": int(p["titulo_id"]),
                "numero_titulo": p["numero_titulo"], "protocolo": p["protocolo"],
                "valor_centavos": int(p["valor_centavos"]), "guia_id": None}
    for p in REP.em_guia_sem_pagamento(con, hoje=hoje):
        if (p["central"] == "CRA" and p["situacao_da_guia"] == "GERADA"
                and not p["desfeito"]):
            linhas[int(p["ato_id"])] = {
                "ato_id": int(p["ato_id"]), "titulo_id": int(p["titulo_id"]),
                "numero_titulo": p["numero_titulo"], "protocolo": p["protocolo"],
                "valor_centavos": int(p["valor_centavos"]),
                "guia_id": int(p["guia_id"])}
    if not linhas:
        return []
    for d in banco(con).ler(
            """SELECT a.id AS ato_id,
                      ret.cra_enviado_em AS enviado, ret.cra_recusado_em AS recusado,
                      rj.cra_enviado_em AS enviado_antes
                 FROM pt_atos a
                 LEFT JOIN pt_retornos ret ON ret.id = a.retorno_id
                 LEFT JOIN pt_retornos rj ON rj.id = a.cra_ja_informado_retorno_id
                WHERE a.id = ANY(%s)""", (sorted(linhas),)):
        aceito = d["enviado"] if (d["enviado"] and not d["recusado"]) else d["enviado_antes"]
        linhas[int(d["ato_id"])]["retorno_em"] = str(aceito or "")[:10] or None
    return sorted(linhas.values(), key=lambda x: x["ato_id"])


def titulos_do_boleto(candidatos: list[dict], *, retorno_em: str,
                      repasse_centavos: int) -> list[dict]:
    """Os pagamentos que o boleto paga: os de um retorno aceito até quatro dias
    antes da data de retorno do boleto, cuja soma é EXATAMENTE o repasse.

    Um retorno que soma o valor: é ele. Mais de um: o robô não escolhe. Nenhum
    sozinho, mas todos os da janela juntos: são eles. Nenhuma das três:
    `BoletoNaoConfere`, com o que se achou.
    """
    try:
        limite = date.fromisoformat(str(retorno_em)[:10])
    except ValueError:
        raise BoletoNaoConfere("O boleto não traz a data do retorno.") from None
    grupos: dict[str, list[dict]] = {}
    for c in candidatos:
        if not c.get("retorno_em"):
            continue
        dia = date.fromisoformat(c["retorno_em"])
        if timedelta(0) <= limite - dia <= timedelta(days=JANELA_DO_RETORNO_DIAS):
            grupos.setdefault(c["retorno_em"], []).append(c)

    def soma(lista: list[dict]) -> int:
        return sum(int(x["valor_centavos"]) for x in lista)

    iguais = [g for g in grupos.values() if soma(g) == int(repasse_centavos)]
    if len(iguais) == 1:
        return iguais[0]
    if len(iguais) > 1:
        raise BoletoNaoConfere(
            f"Mais de um retorno soma R$ {reais(int(repasse_centavos))}: o robô não "
            f"escolhe — registre a guia à mão.")
    todos = [c for g in grupos.values() for c in g]
    if len(grupos) > 1 and soma(todos) == int(repasse_centavos):
        return todos
    inicio = limite - timedelta(days=JANELA_DO_RETORNO_DIAS)
    raise BoletoNaoConfere(
        f"O boleto diz R$ {reais(int(repasse_centavos))} do retorno de "
        f"{limite.strftime('%d/%m/%Y')}, e os pagamentos da CRA com retorno aceito "
        f"de {inicio.strftime('%d/%m/%Y')} a {limite.strftime('%d/%m/%Y')} somam "
        f"R$ {reais(soma(todos))} ({len(todos)} título(s)). Confira o retorno e os "
        f"pagamentos antes de registrar.")


def registrar_boleto(con, *, atos: list[dict], nosso_numero: str,
                     vencimento: str | None, valor_centavos: int, hoje: str,
                     agora: str, usuario: str) -> dict:
    """A guia do boleto, REGISTRADA com o nosso número. ESCREVE.

    Os pagamentos sem relação ganham uma (`gerar_guia`, só da CRA, só eles);
    os que já estão numa relação GERADA usam a dela — desde que ela tenha
    exatamente estes pagamentos. Relação misturada é recusa: ela não se emite
    como está, e quem a desfaz é gente.
    """
    ids = sorted(int(a["ato_id"]) for a in atos)
    guias = {a.get("guia_id") for a in atos}
    if guias == {None}:
        guia_id = int(REP.gerar_guia(con, hoje=hoje, agora=agora, usuario=usuario,
                                     origem="CRA", ato_ids=ids)["guia_id"])
    elif len(guias) == 1:
        guia_id = int(next(iter(guias)))
        na_guia = sorted(int(r["ato_id"]) for r in banco(con).ler(
            "SELECT ato_id FROM pt_repasses WHERE guia_id=%s AND situacao='EM_GUIA'",
            (guia_id,)))
        if na_guia != ids:
            raise BoletoNaoConfere(
                "A relação gerada para estes pagamentos tem títulos que não são "
                "deste boleto: cancele-a e o robô gera a certa na rodada seguinte.")
    else:
        raise BoletoNaoConfere(
            "Parte dos pagamentos deste boleto já está numa relação e parte não: "
            "cancele a relação e o robô gera a certa na rodada seguinte.")
    guia = REP.guia(con, guia_id)
    if int(guia["total_centavos"]) != int(valor_centavos):
        raise BoletoNaoConfere(
            f"A relação soma R$ {reais(int(guia['total_centavos']))} e o boleto "
            f"R$ {reais(int(valor_centavos))}.")
    REP.registrar_guia(con, guia_id, identificador=nosso_numero,
                       vencimento=vencimento, agora=agora, usuario=usuario)
    return {"guia_id": guia_id, "numero": guia["numero"], "ano": guia["ano"],
            "titulos": len(ids), "total_centavos": int(guia["total_centavos"])}


def anexos(con, guia_id: int) -> list[dict]:
    """Os PDFs de boleto anexados à guia, para a ficha dela. Só LÊ."""
    return banco(con).ler(
        "SELECT * FROM attachments WHERE entity_type = %s AND entity_id = %s "
        "ORDER BY id", (ENTIDADE_DO_ANEXO, int(guia_id)))


def anexar_pdf(con, guia_id: int, conteudo: bytes, *, pasta: Path,
               nosso_numero: str, agora: str) -> int:
    """O PDF do boleto, anexado à guia. ESCREVE (arquivo e `attachments`).

    O arquivo se chama pelo sha256 — nunca por nome que veio de fora.
    """
    sha = hashlib.sha256(conteudo).hexdigest()
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{sha}.pdf"
    if not destino.exists():
        destino.write_bytes(conteudo)
    bd = banco(con)
    ja = bd.um("SELECT id FROM attachments WHERE entity_type=%s AND entity_id=%s "
               "AND sha256=%s", (ENTIDADE_DO_ANEXO, int(guia_id), sha))
    if ja:
        return int(ja["id"])
    return int(bd.escrever(
        "INSERT INTO attachments(entity_type, entity_id, original_name, stored_name, "
        "stored_path, sha256, size_bytes, description, uploaded_by, uploaded_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (ENTIDADE_DO_ANEXO, int(guia_id),
         f"boleto_repasse_cra_{CRA.so_digitos(nosso_numero)}.pdf", destino.name,
         str(destino), sha, len(conteudo),
         "Boleto de repasse da CRA-MA, baixado do portal pelo robô", None,
         agora))[0]["id"])


def _despesa_do_boleto(con, nosso_numero: str) -> dict | None:
    bd = banco(con)
    if not bd.tem_tabela("dp_despesas"):
        return None
    return bd.um("SELECT id, situacao, paga_em FROM dp_despesas WHERE origem=%s "
                 "AND chave_origem=%s", (ORIGEM_DA_DESPESA, f"CRA:{nosso_numero}"))


def conciliar_pelo_portal(con, guia: dict, boleto: dict, *, hoje: str, agora: str,
                          usuario: str) -> dict:
    """O boleto que o portal mostra pago: a guia paga e conciliada. ESCREVE.

    A prova é a situação no portal (`prova="PORTAL"`). O dia do pagamento é o
    da despesa paga, quando o banco já o disse; senão, o dia em que o robô viu
    — e o comprovante diz qual dos dois.
    """
    nosso = boleto["nosso_numero"]
    situacao = boleto.get("situacao") or "PAGO"
    if guia["situacao"] == "REGISTRADA":
        despesa = _despesa_do_boleto(con, nosso)
        paga_em, de_onde = hoje, "dia em que o robô viu"
        if despesa and despesa.get("paga_em"):
            dia = str(despesa["paga_em"])[:10]
            ficha = REP.guia(con, int(guia["id"]))
            if dia >= str(ficha["dia"])[:10]:
                paga_em, de_onde = dia, f"dia do pagamento da despesa {despesa['id']}"
        REP.pagar_guia(con, int(guia["id"]), paga_em=paga_em, prova="PORTAL",
                       comprovante=(f"{situacao} — nosso número {nosso}, lido no "
                                    f"portal da CRA-MA em {agora[:16]} ({de_onde})"),
                       agora=agora, usuario=usuario)
    REP.conciliar_guia(con, int(guia["id"]),
                       valor_confirmado=reais(int(boleto["valor_centavos"] or 0)),
                       referencia=f"portal da CRA-MA: {situacao}, nosso número {nosso}",
                       agora=agora, usuario=usuario)
    return {"guia_id": int(guia["id"]), "numero": guia["numero"], "ano": guia["ano"]}


# ------------------------------------------------------------------ a rodada


def _credencial(contexto) -> dict:
    """O usuário e a senha do portal, do cofre da automação. Só no despachante."""
    import automacao_cofre as COFRE
    return COFRE.ler(CRA.NOME_NO_COFRE,
                     caminho=COFRE.caminho_do_cofre(getattr(contexto, "pasta_dados", None)),
                     quem="despachante", processo=CODIGO)


def _log(db, evento: str, mensagem: str, *, nivel: str = "INFO",
         detalhe: Any = None) -> None:
    """Um passo em `centrais_log`. Log que falha não derruba a rodada."""
    try:
        import centrais_log as CLOG
        with db.transaction() as con:
            CLOG.registrar(con, "CRA", OPERACAO, evento, nivel=nivel,
                           ambiente="PRODUCAO", mensagem=mensagem, detalhe=detalhe)
    except Exception:  # noqa: BLE001 — o relato da rodada continua dizendo
        pass


def _auditar(contexto, acao: str, tabela: str, ident: int, detalhes: dict) -> None:
    """A gravação do robô em `audit_logs`, fora de transação, identificada."""
    log = getattr(contexto.db, "log", None)
    if log is None:
        return
    import identidade_do_robo as IDR
    processo = getattr(contexto, "processo", None) or {}
    mandante = (str(processo.get("alterado_por") or processo.get("criado_por") or "").strip()
                or IDR.PELO_RESPONSAVEL)
    log(None, "automação", acao, tabela, int(ident), {**detalhes, "processo": CODIGO},
        agente=AGENTE, a_mando_de=mandante)


def _gravar_estado(db, estado: dict) -> None:
    """A marca da geração em curso, gravada ANTES do clique."""
    with db.transaction() as con:
        if banco(con).tem_tabela("au_processos"):
            banco(con).escrever("UPDATE au_processos SET estado=%s WHERE codigo=%s",
                                (json.dumps(estado, ensure_ascii=False), CODIGO))


def _pasta_dos_arquivos(contexto) -> Path:
    leitor = getattr(contexto, "setting", None)
    raiz = (leitor("archive_root", "") if callable(leitor)
            else contexto.db.get_setting("archive_root", "")) or ""
    base = Path(str(raiz).strip()).expanduser() if str(raiz).strip() else \
        Path(getattr(contexto, "pasta_dados", ".")) / "arquivos"
    return base


def _vencimento(lido: dict, boleto: dict) -> str | None:
    opcoes = list(lido.get("vencimentos") or [])
    if lido.get("vencimento_impresso") in opcoes:
        return lido["vencimento_impresso"]
    if len(opcoes) == 1:
        return opcoes[0]
    depois = [v for v in opcoes if v >= (boleto.get("geracao_em") or "")]
    return depois[0] if depois else None


def _conferir_pdf(boleto: dict, lido: dict) -> None:
    """O PDF contra a lista do portal. Divergiu: `BoletoNaoConfere`."""
    valor = boleto.get("valor_centavos")
    repasse = boleto.get("repasse_centavos")
    taxa = boleto.get("taxa_centavos") or 0
    if valor is None or repasse is None:
        raise BoletoNaoConfere("A lista do portal não traz o valor e o repasse do boleto.")
    if taxa:
        raise BoletoNaoConfere(
            f"O boleto tem taxa de R$ {reais(int(taxa))}: a regra entre repasse, taxa "
            f"e valor não está medida — registre à mão.")
    if int(valor) != int(repasse):
        raise BoletoNaoConfere(f"O valor do boleto (R$ {reais(int(valor))}) não é o "
                               f"repasse (R$ {reais(int(repasse))}).")
    if lido["valor_centavos"] != int(valor):
        raise BoletoNaoConfere(
            f"A linha digitável do PDF diz R$ {reais(int(lido['valor_centavos'] or 0))} "
            f"e a lista do portal R$ {reais(int(valor))}.")
    if lido.get("valor_impresso_centavos") not in (None, int(valor)):
        raise BoletoNaoConfere("O valor impresso no PDF não é o da linha digitável.")
    nosso, do_pdf = boleto["nosso_numero"], lido.get("nosso_numero") or ""
    if do_pdf and not (nosso in do_pdf or do_pdf in nosso):
        raise BoletoNaoConfere(f"O PDF traz o nosso número {do_pdf} e a lista {nosso}.")


def _registrar_um(contexto, nav, boleto: dict, *, hoje: str, agora: str) -> dict:
    """Baixa, lê, confere e registra um boleto. Devolve o que fez."""
    import despesas as DP
    nosso = boleto["nosso_numero"]
    link = CRA.link_do_pdf(boleto)
    if not link:
        raise BoletoNaoConfere("Não achei o link do PDF na linha do boleto.")
    pdf = nav.abrir(link)
    if not pdf.e_pdf:
        raise BoletoNaoConfere("O link do boleto não devolveu um PDF.")
    lido = CRA.ler_boleto_pdf(pdf.corpo)
    _conferir_pdf(boleto, lido)
    _log(contexto.db, "PDF_LIDO", f"nosso número {nosso}: linha digitável conferida",
         detalhe={"valor": reais(int(lido["valor_centavos"]))})
    retorno_em = boleto.get("retorno_em") or boleto.get("geracao_em")
    vencimento = _vencimento(lido, boleto)
    with contexto.db.transaction() as con:
        atos = titulos_do_boleto(candidatos_da_cra(con, hoje=hoje),
                                 retorno_em=retorno_em,
                                 repasse_centavos=int(boleto["repasse_centavos"]))
        g = registrar_boleto(con, atos=atos, nosso_numero=nosso, vencimento=vencimento,
                             valor_centavos=int(boleto["valor_centavos"]), hoje=hoje,
                             agora=agora, usuario=QUEM)
        anexar_pdf(con, g["guia_id"], pdf.corpo,
                   pasta=_pasta_dos_arquivos(contexto) / "protesto" / "repasses",
                   nosso_numero=nosso, agora=agora)
    _auditar(contexto, "PROTESTO_REPASSE_BOLETO_REGISTRADO", "pt_repasse_guias",
             g["guia_id"], {"numero": g["numero"], "ano": g["ano"], "nosso_numero": nosso,
                            "titulos": g["titulos"], "total_centavos": g["total_centavos"]})
    _log(contexto.db, "GUIA_REGISTRADA",
         f"guia {g['numero']}/{g['ano']}: nosso número {nosso}, {g['titulos']} título(s)")
    feito = {"acao": "registrou a guia do boleto", "guia": f"{g['numero']}/{g['ano']}",
             "nosso_numero": nosso, "titulos": g["titulos"],
             "total": reais(g["total_centavos"]), "vencimento": vencimento}
    try:
        with contexto.db.transaction() as con:
            despesa_id = DP.cadastrar(
                con, agora=contexto.agora, por=QUEM, origem=ORIGEM_DA_DESPESA,
                chave_origem=f"CRA:{nosso}",
                beneficiario_nome=lido.get("beneficiario") or "IEPTB-MA (CRA-MA)",
                beneficiario_documento="", valor_centavos=int(boleto["valor_centavos"]),
                vencimento=vencimento, forma=DP.BOLETO, codigo=lido["linha_digitavel"],
                descricao=(f"Repasse ao apresentante dos títulos pagos — boleto da "
                           f"CRA-MA, guia {g['numero']}/{g['ano']}, nosso número {nosso}"),
                categoria=CATEGORIA_DA_DESPESA,
                documento_especie="Boleto de repasse (CRA-MA)", documento_numero=nosso,
                valor_esperado_centavos=int(g["total_centavos"]),
                anexo=(f"boleto_repasse_cra_{nosso}.pdf", pdf.corpo),
                pasta_anexos=_pasta_dos_arquivos(contexto) / "despesas")
        _auditar(contexto, "DESPESA_CADASTRADA_PELO_ROBO", "dp_despesas", despesa_id,
                 {"nosso_numero": nosso, "guia": feito["guia"]})
        feito["despesa_id"] = int(despesa_id)
    except (DP.DespesaError, ValueError) as erro:
        feito["despesa_erro"] = f"a despesa não foi lançada: {erro} — lance à mão"
    return feito


def _resultado(situacao: str, relato: str, achados=(), acoes=(), **extra) -> dict:
    return {"situacao": situacao, "relato": relato[:3500], "achados": list(achados),
            "acoes": list(acoes), **extra}


def emitir_boletos_da_cra(contexto) -> dict:
    """O processo PROTESTO_REPASSE_BOLETO_CRA. Ver o docstring do módulo."""
    import centrais_trava_sandbox as TRAVA
    agora_dt: datetime = contexto.agora
    hoje = agora_dt.date().isoformat()
    agora = agora_dt.isoformat(timespec="seconds")
    processo = getattr(contexto, "processo", None) or {}
    pode_agir = bool(processo.get("pode_agir"))
    if TRAVA.e_sandbox():
        return _resultado("AVISO", "No sandbox o robô não entra no portal da CRA: o "
                                   "portal não tem simulador. Nada foi feito.")
    try:
        cred = _credencial(contexto)
    except Exception as erro:  # noqa: BLE001 — cofre trancado, sem o item, canal fora
        if getattr(erro, "cofre_trancado", False):
            return _resultado("AVISO", "O cofre da automação está trancado: o robô não "
                                       "tem a senha do portal da CRA. Destranque o cofre "
                                       "(Automação → Cofre); a rodada seguinte retoma.")
        return _resultado("AVISO", f"Sem a credencial do portal da CRA ({erro}). "
                                   f"Cadastre em Automação → Cofre o item "
                                   f"«{CRA.NOME_NO_COFRE}», do tipo usuário e senha, com "
                                   f"os campos «usuario» e «senha».")
    nav = getattr(contexto, "navegador", None) or CRA.Navegador()
    try:
        inicio = CRA.entrar(nav, cred.get("usuario", ""), cred.get("senha", ""))
        cred = {}
        _log(contexto.db, "ENTROU", "sessão aberta no portal da CRA")
        pagina = CRA.abrir_boletos_de_repasse(nav, inicio)
        quadro = CRA.ler_boletos(pagina)
    except CRA.DesafioNoLogin as erro:
        _log(contexto.db, "DESAFIO_NO_LOGIN", str(erro), nivel="AVISO")
        return _resultado("AVISO", f"{erro} Os boletos de repasse ficam para emitir à "
                                   f"mão no portal.",
                          [{"tipo": "EMITA_A_MAO", "motivo": str(erro)}])
    except CRA.LoginRecusado as erro:
        _log(contexto.db, "LOGIN_RECUSADO", str(erro), nivel="AVISO")
        return _resultado("AVISO", str(erro), [{"tipo": "EMITA_A_MAO", "motivo": str(erro)}])
    except CRA.PortalError as erro:
        _log(contexto.db, "PORTAL_NAO_RESPONDEU", str(erro), nivel="ERRO")
        return _resultado("ERRO", f"O robô não chegou aos boletos de repasse: {erro}",
                          erro=str(erro)[:500])
    finally:
        cred = {}
    _log(contexto.db, "LEU_BOLETOS",
         f"{len(quadro[CRA.BOLETOS])} boleto(s), {len(quadro[CRA.PENDENTES])} "
         f"pendente(s) de geração, {len(quadro[CRA.EXCLUIDOS])} excluído(s)")

    acoes: list[dict] = []
    achados: list[dict] = []
    erros: list[str] = []
    avisos: list[str] = []
    estado = dict(processo.get("estado") or {})
    incertas: dict[str, dict] = dict(estado.get(CHAVE_DO_ESTADO) or {})

    def da_conta(conta: str) -> set[str]:
        alvo = CRA.normalizar(conta)
        return {b["nosso_numero"] for b in quadro[CRA.BOLETOS]
                if b["nosso_numero"] and CRA.normalizar(b.get("conta")) == alvo}

    # 1. A MARCA DA GERAÇÃO INCERTA SE RESOLVE QUANDO O BOLETO APARECE.
    for conta, marca in list(incertas.items()):
        if da_conta(conta) - set(marca.get("nossos_antes") or []):
            incertas.pop(conta)
            _log(contexto.db, "GERACAO_CONFIRMADA", f"conta {conta}: o boleto apareceu")

    # 2. GERAR — uma vez por conta, com a marca gravada antes do clique.
    for pendente in quadro[CRA.PENDENTES]:
        conta = pendente.get("conta") or ""
        if conta in incertas:
            avisos.append(
                f"A geração do boleto da conta {conta} em {incertas[conta]['desde'][:16]} "
                f"não se confirmou: o robô não gera de novo sozinho. Confira no portal e, "
                f"se não saiu, gere à mão — o robô registra o boleto na rodada seguinte.")
            achados.append({"tipo": "GERACAO_INCERTA", "conta": conta,
                            "desde": incertas[conta]["desde"]})
            continue
        if not pode_agir:
            achados.append({"tipo": "PENDENTE_DE_GERACAO", "conta": conta,
                            "movimento": pendente.get("movimento_em"),
                            "repasse": reais(int(pendente.get("repasse_centavos") or 0))})
            continue
        antes = da_conta(conta)
        incertas[conta] = {"desde": agora, "movimento": pendente.get("movimento_em"),
                           "repasse_centavos": pendente.get("repasse_centavos"),
                           "nossos_antes": sorted(antes)}
        estado[CHAVE_DO_ESTADO] = incertas
        _gravar_estado(contexto.db, estado)
        try:
            CRA.gerar_boleto(nav, pagina, conta=conta)
            _log(contexto.db, "GERAR_BOLETO",
                 f"conta {conta}, movimento {pendente.get('movimento') or '—'}, "
                 f"repasse {pendente.get('repasse') or '—'}")
            pagina = CRA.abrir_boletos_de_repasse(nav, inicio)
            quadro = CRA.ler_boletos(pagina)
        except CRA.PortalError as erro:
            erros.append(f"Ao gerar o boleto da conta {conta}: {erro} A marca fica — o "
                         f"robô não gera de novo sozinho.")
            _log(contexto.db, "GERAR_BOLETO_FALHOU", str(erro), nivel="ERRO")
            break
        novos = da_conta(conta) - antes
        if novos:
            incertas.pop(conta)
            acoes.append({"acao": "gerou o boleto no portal", "conta": conta,
                          "nosso_numero": sorted(novos)[0]})
            _log(contexto.db, "GERACAO_CONFIRMADA", f"conta {conta}: boleto novo na lista")
        else:
            avisos.append(f"Cliquei em «GERAR BOLETO» para a conta {conta} e o boleto não "
                          f"apareceu na lista: o robô não gera de novo sozinho. Confira no "
                          f"portal.")
            _log(contexto.db, "GERACAO_NAO_CONFIRMADA", f"conta {conta}", nivel="AVISO")
        estado[CHAVE_DO_ESTADO] = incertas
        _gravar_estado(contexto.db, estado)

    # 3. REGISTRAR o boleto em aberto que ainda não é guia.
    with contexto.db.connect() as con:
        registradas = guias_por_nosso_numero(con)
    esperando_pagamento = 0
    for boleto in quadro[CRA.BOLETOS]:
        nosso = boleto["nosso_numero"]
        if not nosso or not CRA.em_aberto(boleto):
            continue
        if nosso in registradas:
            esperando_pagamento += 1
            continue
        if not pode_agir:
            achados.append({"tipo": "BOLETO_SEM_GUIA", "nosso_numero": nosso,
                            "conta": boleto.get("conta"), "retorno": boleto.get("retorno_em"),
                            "valor": reais(int(boleto.get("valor_centavos") or 0))})
            continue
        try:
            feito = _registrar_um(contexto, nav, boleto, hoje=hoje, agora=agora)
        except (BoletoNaoConfere, CRA.PortalError, REP.RepasseError) as erro:
            erros.append(f"Boleto {nosso}: {erro} O boleto NÃO foi registrado.")
            achados.append({"tipo": "BOLETO_NAO_CONFERE", "nosso_numero": nosso,
                            "motivo": str(erro)[:300]})
            _log(contexto.db, "BOLETO_NAO_CONFERE", f"nosso número {nosso}: {erro}",
                 nivel="ERRO")
            continue
        acoes.append(feito)
        esperando_pagamento += 1
        if feito.get("despesa_erro"):
            avisos.append(f"Boleto {nosso}: {feito['despesa_erro']}.")

    # 4. CONCILIAR o boleto que o portal mostra pago.
    for boleto in quadro[CRA.BOLETOS]:
        nosso = boleto["nosso_numero"]
        if not nosso or not CRA.pago(boleto):
            continue
        guia = registradas.get(nosso)
        if not guia:
            avisos.append(f"O boleto {nosso} está pago no portal e não é guia no sistema: "
                          f"confira os títulos dele e registre a guia à mão.")
            achados.append({"tipo": "PAGO_SEM_GUIA", "nosso_numero": nosso})
            continue
        if guia["situacao"] not in ("REGISTRADA", "PAGA"):
            continue
        if not pode_agir:
            achados.append({"tipo": "PAGO_A_CONCILIAR", "nosso_numero": nosso,
                            "guia": f"{guia['numero']}/{guia['ano']}"})
            continue
        try:
            with contexto.db.transaction() as con:
                r = conciliar_pelo_portal(con, guia, boleto, hoje=hoje, agora=agora,
                                          usuario=QUEM)
        except (REP.RepasseError, ValueError) as erro:
            erros.append(f"Guia {guia['numero']}/{guia['ano']} (boleto {nosso}): {erro}")
            _log(contexto.db, "CONCILIACAO_FALHOU", f"nosso número {nosso}: {erro}",
                 nivel="ERRO")
            continue
        _auditar(contexto, "PROTESTO_REPASSE_GUIA_CONCILIADA_PELO_ROBO",
                 "pt_repasse_guias", r["guia_id"], {"nosso_numero": nosso})
        _log(contexto.db, "GUIA_CONCILIADA", f"guia {r['numero']}/{r['ano']}: {nosso}")
        acoes.append({"acao": "conciliou a guia pelo portal",
                      "guia": f"{r['numero']}/{r['ano']}", "nosso_numero": nosso})

    if esperando_pagamento:
        avisos.append(f"{esperando_pagamento} boleto(s) de repasse esperando o pagamento: "
                      f"a despesa de cada um espera a sua autorização em Despesas.")
    partes = []
    if acoes:
        partes.append("Feito: " + "; ".join(
            f"{a['acao']} {a.get('guia') or ''} {a.get('nosso_numero') or ''}".strip()
            for a in acoes) + ".")
    if not pode_agir and achados:
        partes.append("«pode agir» está desligado: o robô entrou, leu e não clicou nem "
                      "gravou nada.")
    partes += erros + avisos
    if not partes:
        partes.append("Nenhum boleto de repasse pendente no portal da CRA.")
    situacao = "ERRO" if erros else ("AVISO" if (avisos or achados) else "OK")
    if incertas or CHAVE_DO_ESTADO in estado:
        estado[CHAVE_DO_ESTADO] = incertas
    return _resultado(situacao, " ".join(partes), achados, acoes,
                      estado=estado if CHAVE_DO_ESTADO in estado else None,
                      erro=(erros[0][:500] if erros else None))


# A MESA DOS PORTAIS GUARDA A FUNÇÃO DE CADA UM. O catálogo da automação chama
# a da CRA pelo nome (`CATALOGO`); a da CENPROT entra aqui quando existir.
PORTAIS["CRA"]["emitir"] = emitir_boletos_da_cra
