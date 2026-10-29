"""A PROVA DA INTIMAÇÃO — e a trava que não deixa protestar sem ela.

ORDEM DO OFICIAL, 29/10/2026: «nao deixar protestar sem aviso de que foi
intimado (com comprovante juntado) ou comprovacao do envio do edital na
cenprot. vincular cada obrigacao a uma conduta, nao deixando a escrevente
cometer erros. se insistir em algo que eh erro, precisa afirmar
expressamente e deixar log».

O QUE ACONTECEU EM OUTUBRO DE 2026, medido na produção (29/10/2026):

    - protestos por edital lavrados ANTES de o edital estar publicado no site
      da CENPROT — o CN-MA art. 922, § 1º, exige o edital afixado E publicado
      na CENPROT, e o protesto só do final do primeiro dia útil seguinte. O
      arquivo do edital de 22/10 só foi gerado em 26/10, e os protestos
      saíram em 23/10;
    - quatro avisos registrados como «entregues» e protestados minutos
      depois, com canhotos sem a assinatura de quem recebeu — e num deles o
      arquivo anexado era de OUTRO título (o nome do arquivo era o protocolo
      do outro);
    - dos 21 protestos que este sistema lavrou (todos em outubro), NENHUM
      teria passado nesta trava: 18 por edital sem comprovante do envio à
      CENPROT (nenhum edital da casa tinha esse comprovante) e 3 pessoais sem
      o comprovante anexado ao aviso (um deles também sem quem recebeu).

A PROVA É DA ÚLTIMA INTIMAÇÃO VÁLIDA (`INTIMACAO`, `cancelado = 0`), e o que
conta como prova depende de como ela foi feita:

    PESSOAL, EM PAPEL — o aviso que a lavrou (`pt_avisos.ato_id`) está
        ENTREGUE, diz quem recebeu, e tem ao menos um comprovante anexado A
        ELE (`attachments`, `PT_AVISO`). Intimação pessoal lançada à mão na
        ficha, sem aviso, não tem papel que a prove.
    DIGITAL (Resolve) — a plataforma confirmou (estado INTIMADO), ou entregou
        e o oficial aceitou a entrega pela tela dos avisos (estado ENTREGUE,
        com o aviso amarrado ao ato — é `lavrar_intimacao_digital` quem faz
        isso); e o HISTÓRICO da Resolve está guardado (`rs_intimacoes.
        historico`). O PDF não se guarda — a Central devolve um link, e a
        casa decidiu não pôr no backup o que já está lá (`resolve_web`); a
        prova que fica do lado de cá é o histórico, com canal, destinatário,
        data e assinatura de cada tentativa.
    EDITAL — o edital publicado no sistema (`pt_editais`, amarrado ao ato) E
        o comprovante do ENVIO do arquivo daquele dia à CENPROT anexado a ele
        (`PT_EDITAL_CENPROT`, o PR #19). O tríduo continua sendo de
        `protesto_triduo`; o que se soma aqui é a data do comprovante: se ele
        foi juntado DEPOIS do dia do edital, a publicação na CENPROT só está
        provada desde esse dia, e o protesto só do segundo dia útil depois
        dele — a mesma conta do tríduo, contada da publicação provada.

A RECUSA DIZ O QUE FALTA E ONDE SE RESOLVE, com o nome da tela. Recusar sem
dizer o caminho faria o balcão procurar o defeito no lugar errado.

A AFIRMAÇÃO EXPRESSA — O CONTRATO COMUM DA CASA (o mesmo das outras travas
desta reestruturação, 29/10/2026). Toda trava pode ser vencida SÓ por
afirmação expressa de quem está no balcão: a caixa `afirmo` marcada E o texto
`afirmacao`, com pelo menos 30 letras, que a tela mostra começando com
«Afirmo, sob minha responsabilidade, que». No domínio, a função recebe
`afirmacao: str | None` (a rota só a passa com a caixa marcada) e só vence a
trava com ela válida; o texto vai no `detalhe_json` do ato, e a rota grava
`audit("AFIRMACAO_EXPRESSA", ...)` FORA da transação (`audit` abre a sua).
Quem insiste no que é erro tem de dizer que insiste, e com o nome dele.

Este módulo LÊ e decide; quem grava o ato é `protesto.lancar_protesto` e
`protesto_aviso.registrar_entrega`/`guardar_comprovante`.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

import protesto as PT
import protesto_triduo as TRIDUO
from bd_nativo import banco
from ri_schema import soma_dias_uteis

# ------------------------------------------- o contrato da afirmação expressa

#: A frase com que a afirmação começa — a tela a mostra fixa, antes da caixa
#: de texto, e quem a digitar de novo não a vê repetida no registro.
FRASE_DA_AFIRMACAO = "Afirmo, sob minha responsabilidade, que"
#: Quantas LETRAS o texto precisa ter, além da frase. Letras, e não
#: caracteres: «............» não diz nada.
PISO_DA_AFIRMACAO = 30
#: A ação da auditoria — a mesma em toda trava desta reestruturação.
ACAO_DA_AUDITORIA = "AFIRMACAO_EXPRESSA"

#: Os códigos das regras desta trava (MAIÚSCULAS, como o contrato pede).
REGRA_PROTESTO = "PROTESTO_SEM_PROVA_DA_INTIMACAO"
REGRA_ENTREGA = "ENTREGA_SEM_COMPROVANTE"
REGRA_OUTRO_TITULO = "COMPROVANTE_DE_OUTRO_TITULO"
REGRA_OUTRO_AVISO = "COMPROVANTE_DE_OUTRO_AVISO"
#: Trocar o nome de quem recebeu, já registrado no aviso (29/10/2026).
REGRA_CORRECAO_DO_RECEBEDOR = "CORRECAO_DE_QUEM_RECEBEU"

COMO_AFIRMAR = (
    f"Se você tem certeza de que isto não é erro, marque «Afirmo» e escreva "
    f"a afirmação expressa — «{FRASE_DA_AFIRMACAO} …», com pelo menos "
    f"{PISO_DA_AFIRMACAO} letras. Ela fica gravada no ato e na auditoria, com "
    f"o seu nome.")


class ProvaError(PT.ProtestoError):
    """A intimação não está provada, e ninguém afirmou expressamente."""


def _letras(texto: str) -> int:
    return sum(1 for c in texto if c.isalpha())


def afirmacao_valida(texto: Any) -> str | None:
    """O texto inteiro da afirmação, já com a frase de abertura — ou `None`
    se ela não vale. Só calcula.

    A FRASE NÃO CONTA NO PISO: ela tem mais de trinta letras sozinha, e
    contá-la deixaria passar a afirmação que não diz nada além dela.
    """
    corrido = " ".join(str(texto or "").split())
    if corrido.lower().startswith(FRASE_DA_AFIRMACAO.lower()):
        corrido = corrido[len(FRASE_DA_AFIRMACAO):].lstrip(" ,:;-—")
    if _letras(corrido) < PISO_DA_AFIRMACAO:
        return None
    return f"{FRASE_DA_AFIRMACAO} {corrido}"


def vencer_ou_recusar(regra: str, o_que_faltava: str, afirmacao: Any, *,
                      erro: type[Exception] = ProvaError) -> dict:
    """A trava: com afirmação válida, devolve o registro dela para gravar no
    ato e na auditoria; sem ela, recusa com `erro`, dizendo o que falta e
    como afirmar. Só calcula."""
    texto = afirmacao_valida(afirmacao)
    if texto is None:
        recado = ""
        if str(afirmacao or "").strip():
            recado = (f" A afirmação escrita é curta demais: precisa de pelo "
                      f"menos {PISO_DA_AFIRMACAO} letras além de "
                      f"«{FRASE_DA_AFIRMACAO}».")
        raise erro(f"{o_que_faltava}{recado} {COMO_AFIRMAR}")
    return {"regra": regra, "afirmacao": texto, "o_que_faltava": o_que_faltava}


def vencer_todas(faltas: list[tuple[str, str]], afirmacao: Any, *,
                 abertura: str, erro: type[Exception] = ProvaError
                 ) -> list[dict]:
    """Várias travas no mesmo ato, cada uma com a sua regra. Só calcula.

    A RECUSA DIZ TODAS DE UMA VEZ — quem afirma tem de ter lido tudo o que
    está afirmando; recusar uma por vez faria a segunda aparecer depois de a
    afirmação já estar escrita para a primeira. Com a afirmação válida, cada
    regra vencida vira um registro próprio (e uma linha própria de
    auditoria), com a mesma afirmação.
    """
    if not faltas:
        return []
    frase = f"{abertura}: {'; '.join(f for _, f in faltas)}."
    vencer_ou_recusar(faltas[0][0], frase, afirmacao, erro=erro)
    texto = afirmacao_valida(afirmacao)
    return [{"regra": regra, "afirmacao": texto,
             "o_que_faltava": f"{abertura}: {f}."}
            for regra, f in faltas]


def para_a_auditoria(registro: dict) -> dict:
    """O que vai em `audit("AFIRMACAO_EXPRESSA", ...)` — as três chaves do
    contrato, e só elas."""
    return {"regra": registro["regra"], "afirmacao": registro["afirmacao"],
            "o_que_faltava": registro["o_que_faltava"]}


# ------------------------------------------------- a prova da intimação

TELA_DOS_AVISOS = "Protesto → Avisos e editais"
TELA_DA_RESOLVE = "Protesto → Intimação Digital"


def _br(iso: Any) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) == 10 and s[4] == "-" else s


def _dia(valor: Any) -> date | None:
    try:
        return date.fromisoformat(str(valor or "")[:10])
    except ValueError:
        return None


def _anexos(bd, entidade: str, entity_id: int) -> list[dict]:
    """Os anexos vivos daquela entidade (o retirado não prova nada). Só LÊ."""
    if not bd.tem_tabela("attachments"):
        return []
    vivo = (" AND retirado_em IS NULL"
            if bd.tem_coluna("attachments", "retirado_em") else "")
    return [dict(r) for r in bd.ler(
        f"""SELECT id, uploaded_at FROM attachments
             WHERE entity_type = %s AND entity_id = %s{vivo}
             ORDER BY id""", (entidade, int(entity_id)))]


def _prova_pessoal(bd, intimacao_id: int) -> tuple[list[str], list[str], str]:
    import protesto_aviso as AV
    aviso = bd.um(
        """SELECT id, numero, ano, situacao, recebido_por FROM pt_avisos
            WHERE ato_id = %s ORDER BY id DESC LIMIT 1""", (int(intimacao_id),))
    if not aviso:
        return ([
            "a intimação pessoal foi lançada à mão, sem aviso entregue — não "
            "há aviso, nem quem recebeu, nem comprovante que a provem"],
            [], f"{TELA_DOS_AVISOS}: emita o aviso na ficha do título, mande "
                "entregar e registre a entrega com o comprovante e o nome de "
                "quem recebeu")
    nome = f"{aviso['numero']}/{aviso['ano']}"
    faltas, tem = [], []
    if aviso["situacao"] != "ENTREGUE":
        faltas.append(f"o aviso {nome} não está registrado como entregue "
                      f"(está {str(aviso['situacao']).lower()})")
    if not str(aviso["recebido_por"] or "").strip():
        # SE FALTAR, AVISAR A ESCREVENTE PARA COMPLETAR (decisão do oficial,
        # 29/10/2026) — a frase diz onde, e completado o nome a prova fecha.
        faltas.append(f"falta o nome de quem recebeu o aviso {nome} — complete "
                      f"em {TELA_DOS_AVISOS}, lista «Entregues», «Completar "
                      f"quem recebeu»")
    else:
        tem.append(f"aviso {nome} entregue, recebido por quem assinou")
    comprovantes = _anexos(bd, AV.ENTIDADE_DO_COMPROVANTE, aviso["id"])
    if comprovantes:
        tem.append(f"{len(comprovantes)} comprovante(s) anexado(s) ao aviso "
                   f"{nome}")
    else:
        faltas.append(f"o aviso {nome} não tem o comprovante anexado (o "
                      f"canhoto assinado por quem recebeu, escaneado)")
    onde = (f"{TELA_DOS_AVISOS}, lista «Entregues — comprovante da "
            f"intimação», aviso {nome}")
    return faltas, tem, onde


def _prova_digital(bd, titulo_id: int,
                   intimacao_id: int) -> tuple[list[str], list[str], str]:
    import protesto_aviso as AV
    onde = (f"{TELA_DA_RESOLVE}: abra a intimação deste título e clique "
            f"«Trazer o histórico»; a entrega sem leitura se aceita em "
            f"{TELA_DOS_AVISOS}, «Lavrar a intimação digital pela entrega»")
    ultima = AV._ultima_na_resolve(bd, titulo_id)
    if not ultima:
        return (["a intimação foi lançada como eletrônica, e não há Intimação "
                 "Digital (Resolve) deste título em produção que a prove"],
                [], onde)
    faltas, tem = [], []
    estado = str(ultima.get("estado") or "").strip().upper()
    if estado in AV.RESOLVE_CONFIRMOU:
        tem.append(f"a Resolve confirmou a intimação ({ultima['identificador']})")
    elif estado in AV.RESOLVE_ENTREGUE:
        aceita = bd.um("SELECT id FROM pt_avisos WHERE ato_id = %s LIMIT 1",
                       (int(intimacao_id),))
        if aceita:
            tem.append(f"a Resolve entregou, e a entrega foi aceita "
                       f"({ultima['identificador']})")
        else:
            faltas.append("a Resolve só ENTREGOU a mensagem (sem leitura), e "
                          "a entrega não foi aceita pela tela dos avisos")
    else:
        faltas.append(f"a Resolve não confirmou a intimação (ela diz "
                      f"«{estado or 'sem resposta'}»)")
    linha = bd.um("SELECT historico FROM rs_intimacoes WHERE id = %s",
                  (int(ultima["id"]),))
    if str((linha or {}).get("historico") or "").strip():
        tem.append("o histórico da Resolve está guardado")
    else:
        faltas.append("o histórico da Resolve (canal, destinatário, data e "
                      "assinatura de cada tentativa) não está guardado")
    return faltas, tem, onde


_CODIGO_DO_EDITAL = re.compile(r"ED-(\d{4})-(\d+)", re.IGNORECASE)


def _edital_da_intimacao(bd, titulo_id: int, intimacao_id: int,
                         detalhe: dict) -> dict | None:
    edital = bd.um(
        """SELECT id, numero, ano, publicado_em FROM pt_editais
            WHERE ato_id = %s ORDER BY id DESC LIMIT 1""", (int(intimacao_id),))
    if edital:
        return dict(edital)
    # A INTIMAÇÃO POR EDITAL LANÇADA À MÃO NA FICHA guarda só o código
    # digitado; se ele for o de um edital publicado DESTE título, é ele.
    achado = _CODIGO_DO_EDITAL.search(str(detalhe.get("codigo_edital") or ""))
    if not achado:
        return None
    edital = bd.um(
        """SELECT id, numero, ano, publicado_em FROM pt_editais
            WHERE titulo_id = %s AND ano = %s AND numero = %s
            ORDER BY id DESC LIMIT 1""",
        (int(titulo_id), int(achado.group(1)), int(achado.group(2))))
    return dict(edital) if edital else None


def _prova_do_edital(bd, titulo_id: int, intimacao_id: int, detalhe: dict, *,
                     hoje: Any, feriados: set[date] | None
                     ) -> tuple[list[str], list[str], str]:
    import protesto_aviso as AV
    edital = _edital_da_intimacao(bd, titulo_id, intimacao_id, detalhe)
    if not edital:
        codigo = str(detalhe.get("codigo_edital") or "").strip()
        return ([f"a intimação por edital não tem edital publicado no sistema"
                 + (f" (o código «{codigo}» foi digitado à mão)" if codigo
                    else "")],
                [], f"{TELA_DOS_AVISOS}: «Não entregues — Resolve, e depois "
                    f"edital» → «Publicar edital»")
    dia = str(edital["publicado_em"] or "")[:10]
    nome = f"ED-{edital['ano']}-{int(edital['numero']):04d}"
    onde = (f"{TELA_DOS_AVISOS}, quadro «Envio do edital à CENPROT — "
            f"comprovantes», dia {_br(dia)}")
    faltas, tem = [], [f"edital {nome} publicado em {_br(dia)}"]
    comprovantes = _anexos(bd, AV.ENTIDADE_DO_ENVIO_DO_EDITAL, edital["id"])
    if not comprovantes:
        faltas.append(
            f"falta o comprovante do envio do arquivo dos editais de "
            f"{_br(dia)} à CENPROT (CN-MA art. 922, § 1º: o edital é afixado "
            f"E publicado no site da CENPROT)")
        return faltas, tem, onde
    tem.append("o comprovante do envio à CENPROT está anexado")
    # A PUBLICAÇÃO NA CENPROT SÓ ESTÁ PROVADA DESDE O DIA DO COMPROVANTE. Foi
    # o caso de outubro: o arquivo do edital de 22/10 só subiu em 26/10, e
    # o protesto por edital se lavra do final do 1º dia útil seguinte à
    # publicação (art. 922, § 1º) — a mesma conta de `protesto_triduo`,
    # contada do dia em que a publicação ficou provada.
    juntado = min((_dia(c["uploaded_at"]) for c in comprovantes
                   if _dia(c["uploaded_at"])), default=None)
    publicado = _dia(dia)
    agora = _dia(hoje)
    if juntado and publicado and agora and juntado > publicado:
        if feriados is None:
            feriados = TRIDUO.feriados_da_casa(bd)
        a_partir = soma_dias_uteis(juntado, 2, feriados)
        if agora < a_partir:
            faltas.append(
                f"o comprovante do envio à CENPROT só foi juntado em "
                f"{_br(juntado.isoformat())}, depois do edital "
                f"({_br(dia)}): a publicação na CENPROT só está provada desde "
                f"esse dia, e o protesto por edital só se lavra a partir de "
                f"{_br(a_partir.isoformat())} (CN-MA art. 922, § 1º). Se o "
                f"arquivo foi enviado antes e o comprovante só foi juntado "
                f"depois, diga isso na afirmação")
    return faltas, tem, onde


def conferir(con, titulo_id: int, *, hoje: Any,
             feriados: set[date] | None = None) -> dict:
    """A prova da última intimação válida do título. Só LÊ.

    Devolve `completa`, `modo` (PESSOAL, DIGITAL, EDITAL ou None), o
    `intimacao_id`, as `faltas` e o que `tem`, `onde` se resolve e a `frase`
    pronta da recusa.
    """
    bd = banco(con)
    intim = bd.um(
        """SELECT id, data_ato, detalhe_json FROM pt_atos
            WHERE titulo_id = %s AND tipo = 'INTIMACAO' AND cancelado = 0
            ORDER BY id DESC LIMIT 1""", (int(titulo_id),))
    if not intim:
        faltas, tem, modo, onde = (
            ["o título não tem intimação lavrada"], [], None,
            "a ficha do título: intime pelo aviso ou pelo edital")
        intimacao_id = None
    else:
        intimacao_id = int(intim["id"])
        try:
            detalhe = json.loads(intim["detalhe_json"] or "{}") or {}
        except (TypeError, ValueError):
            detalhe = {}
        modo = str(detalhe.get("modo") or "PESSOAL").upper()
        if modo == "EDITAL":
            faltas, tem, onde = _prova_do_edital(
                bd, titulo_id, intimacao_id, detalhe, hoje=hoje,
                feriados=feriados)
        elif detalhe.get("digital"):
            modo = "DIGITAL"
            faltas, tem, onde = _prova_digital(bd, titulo_id, intimacao_id)
        else:
            modo = "PESSOAL"
            faltas, tem, onde = _prova_pessoal(bd, intimacao_id)
    frase = ""
    if faltas:
        frase = (f"Não se protesta sem a prova da intimação: "
                 f"{'; '.join(faltas)}. Onde se resolve: {onde}.")
    # O AVISO QUE LAVROU A INTIMAÇÃO, para a tela apontar a ação certa (o
    # «Completar quem recebeu», 29/10/2026). `None` quando não há.
    aviso = (bd.um("SELECT id, recebido_por FROM pt_avisos WHERE ato_id = %s "
                   "ORDER BY id DESC LIMIT 1", (intimacao_id,))
             if intimacao_id else None)
    return {"completa": not faltas, "modo": modo,
            "intimacao_id": intimacao_id, "faltas": faltas, "tem": tem,
            "onde": onde, "frase": frase,
            "aviso_id": int(aviso["id"]) if aviso else None,
            "falta_quem_recebeu": bool(
                aviso and modo == "PESSOAL"
                and not str(aviso["recebido_por"] or "").strip())}


def exigir(con, titulo_id: int, *, hoje: Any,
           afirmacao: str | None = None) -> dict:
    """A trava do protesto. Só LÊ; recusa com `ProvaError`.

    Devolve a conferência, com `afirmacao_expressa` preenchida quando a
    prova estava incompleta e a afirmação venceu a trava.
    """
    prova = conferir(con, titulo_id, hoje=hoje)
    prova["afirmacao_expressa"] = None
    if not prova["completa"]:
        prova["afirmacao_expressa"] = vencer_ou_recusar(
            REGRA_PROTESTO, prova["frase"], afirmacao)
    return prova


def resumo_para_o_ato(prova: dict) -> dict:
    """O que fica no `detalhe_json` do protesto sobre a prova."""
    return {"modo": prova.get("modo"), "completa": bool(prova.get("completa")),
            "intimacao_id": prova.get("intimacao_id"),
            "tem": list(prova.get("tem") or []),
            "faltas": list(prova.get("faltas") or [])}


def para_a_lista(con, linhas: list[dict], *, hoje: Any) -> list[dict]:
    """Acrescenta a prova a cada linha da tela «A protestar». Só LÊ."""
    feriados = TRIDUO.feriados_da_casa(con)
    for linha in linhas:
        linha["prova"] = conferir(con, int(linha["id"]), hoje=hoje,
                                  feriados=feriados)
    return linhas


def intimacoes_sem_prova(con, *, hoje: Any = None) -> list[dict]:
    """Os títulos INTIMADOS cuja intimação NÃO tem a prova que o protesto
    exige — a pendência que o roteiro do Protesto lê. Só LÊ.

    A RÉGUA É A MESMA DO PROTESTO: cada título passa por `conferir` (por
    `para_a_lista`), e não por uma consulta parecida — duas réguas para «esta
    intimação está provada?» divergiriam no primeiro conserto, e a lista
    mandaria resolver o que a trava não pede (ou calaria o que ela recusa).

    Cada linha leva `titulo_id`, `numero_titulo`, `protocolo`, `explicacao`
    (o que falta, curto), `onde` (a tela que resolve), `modo` e `origem` — e
    `aviso_id` e `link`, o endereço da linha do aviso na tela dos avisos,
    onde se completa quem recebeu e se anexa o comprovante (29/10/2026: «se
    faltar, avisar escrevente pra completar»).
    A INTIMAÇÃO VINDA DO E-OFÍCIO sai com `origem = "ACERVO"`: o papel dela é
    do arquivo do E-Ofício, e o acervo não vira atraso — quem lê a lista
    (o roteiro) a deixa de fora; ela continua aqui para quem quiser contar.
    """
    dia = str(hoje or date.today().isoformat())[:10]
    linhas = [dict(r) for r in banco(con).ler(
        """SELECT t.id, t.numero_titulo, t.protocolo,
                  (SELECT a.origem FROM pt_atos a
                    WHERE a.titulo_id = t.id AND a.tipo = 'INTIMACAO'
                      AND a.cancelado = 0
                    ORDER BY a.id DESC LIMIT 1) AS origem_da_intimacao
             FROM pt_titulos t
            WHERE t.situacao = 'INTIMADO'
            ORDER BY t.id""")]
    saida = []
    for linha in para_a_lista(con, linhas, hoje=dia):
        prova = linha["prova"]
        if prova["completa"]:
            continue
        saida.append({
            "titulo_id": int(linha["id"]),
            "numero_titulo": linha["numero_titulo"],
            "protocolo": linha["protocolo"],
            "explicacao": "; ".join(prova["faltas"]),
            "onde": prova["onde"],
            "modo": prova["modo"],
            "origem": ("ACERVO" if linha["origem_da_intimacao"] == "EOFICIO"
                       else "SISTEMA"),
            "aviso_id": prova.get("aviso_id"),
            "falta_quem_recebeu": bool(prova.get("falta_quem_recebeu")),
            "link": (f"/protesto/avisos#aviso-{prova['aviso_id']}"
                     if prova.get("aviso_id") else
                     f"/protesto/{int(linha['id'])}"),
        })
    return saida


# ------------------------------------- o comprovante suspeito, no aviso

_PROTOCOLO_NO_NOME = re.compile(r"(?<!\d)(\d{10})(?!\d)")


def _parece_protocolo(numero: str) -> bool:
    """Dez dígitos que COMEÇAM COM UMA DATA (AAMMDD) — a forma do protocolo
    desta casa (928 de 931 títulos de 2024 em diante). Telefone e outros
    números de dez dígitos não começam com data válida."""
    try:
        date(2000 + int(numero[:2]), int(numero[2:4]), int(numero[4:6]))
    except ValueError:
        return False
    return True


def protocolos_no_nome(nome: Any) -> list[str]:
    """Os protocolos que o nome do arquivo cita. Só calcula."""
    return [n for n in _PROTOCOLO_NO_NOME.findall(str(nome or ""))
            if _parece_protocolo(n)]


def suspeitas_do_comprovante(con, aviso: dict, *, nome: Any,
                             sha256: str) -> list[tuple[str, str]]:
    """O que torna o comprovante suspeito, como (regra, frase). Só LÊ.

    (a) O MESMO ARQUIVO (sha256) já anexado a OUTRO aviso — o papel prova um
        aviso só;
    (b) O NOME DO ARQUIVO cita um protocolo de dez dígitos que não é o do
        título deste aviso — foi o caso de outubro: «2610070012.pdf» anexado
        ao aviso do protocolo 2610070007.
    """
    import protesto_aviso as AV
    bd = banco(con)
    tit = bd.um("SELECT protocolo FROM pt_titulos WHERE id = %s",
                (int(aviso["titulo_id"]),))
    protocolo = "".join(c for c in str((tit or {}).get("protocolo") or "")
                        if c.isdigit())
    saida: list[tuple[str, str]] = []
    if bd.tem_tabela("attachments"):
        vivo = (" AND x.retirado_em IS NULL"
                if bd.tem_coluna("attachments", "retirado_em") else "")
        outros = bd.ler(
            f"""SELECT DISTINCT a.id, a.numero, a.ano, a.titulo_id, t.protocolo
                  FROM attachments x
                  JOIN pt_avisos a ON a.id = x.entity_id
                  JOIN pt_titulos t ON t.id = a.titulo_id
                 WHERE x.entity_type = %s AND x.sha256 = %s
                   AND x.entity_id <> %s{vivo}
                 ORDER BY a.id""",
            (AV.ENTIDADE_DO_COMPROVANTE, str(sha256), int(aviso["id"])))
        for o in outros:
            if int(o["titulo_id"]) != int(aviso["titulo_id"]):
                saida.append((REGRA_OUTRO_TITULO,
                              f"este mesmo arquivo já está anexado ao aviso "
                              f"{o['numero']}/{o['ano']}, de OUTRO título "
                              f"(protocolo {o['protocolo'] or 'sem protocolo'})"))
            else:
                saida.append((REGRA_OUTRO_AVISO,
                              f"este mesmo arquivo já está anexado ao aviso "
                              f"{o['numero']}/{o['ano']}, deste mesmo título "
                              f"— o comprovante prova um aviso só"))
    citados = [p for p in protocolos_no_nome(nome) if p != protocolo]
    if citados:
        saida.append((REGRA_OUTRO_TITULO,
                      f"o nome do arquivo cita o protocolo "
                      f"{', '.join(sorted(set(citados)))}, e o título deste "
                      f"aviso é o protocolo {protocolo or '(sem protocolo)'} — "
                      f"confira se o arquivo é mesmo deste título"))
    return saida
