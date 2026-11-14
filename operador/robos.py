"""OS ROBÔS E A AUTOMAÇÃO, para o superusuário — ver tudo de uma vez e arrumar
o acesso de cada robô sem ver segredo nenhum.

POR QUE EXISTE — 14/11/2026, o oficial: «preciso também que o superusuário
gerencie e configure todos os outros robôs. Quero que, com um pedido simples,
ele configure o acesso de toda a automação e deixe tudo funcionando — a de
hoje e as futuras».

A casa já tem as peças, e este módulo NÃO as reescreve: lê e chama as mesmas
funções que as telas usam.

    as rotinas ........ `automacao.py` (o cadastro, o despachante, as rodadas)
    as credenciais .... `automacao_cofre.py` (o cofre, atrás da senha-mestra)
    o quadro .......... `oficial_robos.py` (cada robô: existe? rodou? rodou bem?)
    as contas ......... `users.eh_robo`, com responsável (`identidade_do_robo.py`)

    python operador/robos.py quadro                       tudo, numa tela, e O QUE FALTA
    python operador/robos.py conta <login> --cofre <item> cria a conta de robô, ou troca a senha dela
    python operador/robos.py responsavel <login>          define quem responde pelo robô (sem mexer na senha)
    python operador/robos.py ligar|desligar|rodar <código do processo>
    python operador/robos.py semear                       cadastra os processos de fábrica novos

AS TRÊS REGRAS, QUE SÃO AS DA CASA
    1. O SEGREDO NUNCA VAI AO MODELO (`automacao_cofre`, regra 2). Por isso
       este módulo nunca chama `cofre.ler`, e a senha da conta de robô é
       SORTEADA aqui e guardada direto — no cofre ou num `.cred` — sem
       aparecer na tela, no registro nem na resposta. A senha de FORA (Central,
       banco, portal) só o oficial conhece: quem a digita é ele, em Automação →
       Cofre. O `quadro` diz exatamente qual falta.
    2. O COFRE SÓ O OFICIAL ABRE. A senha-mestra é dele. Com o cofre trancado,
       a conta não é mexida (a senha nova não teria onde ficar).
    3. ROBÔ TEM CONTA PRÓPRIA, DE ROBÔ, COM RESPONSÁVEL, e só USER ou AUDITOR
       (`docs/IDENTIDADE_DOS_ROBOS.md`). Conta de pessoa não se toca aqui.

Só a biblioteca padrão; os módulos da casa são importados na hora de usar.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bandeja as BANDEJA  # noqa: E402
import intervencao as INT  # noqa: E402

Recusa = INT.Recusa
PAPEIS_DE_ROBO = ("USER", "AUDITOR")
#: A credencial que vence em até tantos dias já entra no «o que falta».
DIAS_DE_AVISO = 15
ONDE_SE_DIGITA = "Automação → Cofre, na máquina do servidor"


# ------------------------------------------------------------------ a casa

def _casa() -> dict:
    """Os módulos da casa que tratam de robô e de automação."""
    raiz = str(INT.raiz_do_sistema())
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    import automacao as AU
    import automacao_cofre as COFRE
    import identidade_do_robo as IDR
    import oficial_robos as QUADRO
    from bd_nativo import banco
    return {"AU": AU, "COFRE": COFRE, "IDR": IDR, "QUADRO": QUADRO, "banco": banco}


def _db():
    """O banco da casa, do jeito leve do despachante (sem subir o esquema)."""
    casa = _casa()
    import banco_pg
    try:
        return casa["AU"].database_leve(INT.pasta_de_dados() / banco_pg.NOME_DO_BANCO_PRINCIPAL)
    except casa["AU"].AutomacaoError as falha:
        raise Recusa(str(falha)) from falha


def _cofre() -> tuple[Any, Path]:
    """O cofre da automação e o arquivo dele. Os testes trocam esta função."""
    COFRE = _casa()["COFRE"]
    return COFRE, COFRE.caminho_do_cofre(str(INT.pasta_de_dados()))


def _auditar(db, acao: str, entidade: str, entidade_id: Any, detalhes: dict) -> None:
    """Uma linha na auditoria, com a conta do superusuário (ou, sem ela, como
    agente a mando do responsável pelas rotinas)."""
    casa = _casa()
    with db.connect() as con:
        conta = casa["banco"](con).um(
            "SELECT id FROM users WHERE username=%s AND active=1", (INT.LOGIN,))
    if conta:
        db.log(int(conta["id"]), INT.LOGIN, acao, entidade, entidade_id, detalhes)
    else:
        db.log(None, INT.AGENTE, acao, entidade, entidade_id, detalhes,
               agente=INT.AGENTE, a_mando_de=casa["IDR"].PELO_RESPONSAVEL)


def _curto(texto: Any, tamanho: int = 160) -> str:
    return " ".join(str(texto or "").split())[:tamanho]


def _quando(texto: Any) -> str:
    return str(texto or "")[:16].replace("T", " ")


# ------------------------------------------------------------------- o quadro

def quadro(db=None, agora: datetime | None = None) -> str:
    """Toda a automação numa tela: o despachante, o cofre, as rotinas por
    robô, o quadro dos robôs, as contas — e, no fim, O QUE FALTA, separado em
    o que o superusuário resolve e o que só o oficial pode fazer. **SÓ LÊ.**

    «Não mediu» não é «zero» (regra da casa): a parte que não deu para medir
    diz que não deu, com o motivo."""
    casa = _casa()
    AU, QUADRO, banco = casa["AU"], casa["QUADRO"], casa["banco"]
    db = db or _db()
    agora = agora or datetime.now()  # noqa: DTZ005 — hora local, como o resto da casa
    meu: list[str] = []          # o que o superusuário resolve
    dele: list[str] = []         # o que só o oficial pode fazer
    partes = [f"# A automação e os robôs — servidor {INT.servidor().upper()}, "
              f"{agora.strftime('%d/%m/%Y %H:%M')}", ""]

    def secao(titulo: str, medir) -> None:
        partes.append(f"## {titulo}")
        try:
            partes.extend(medir() or ["(nada)"])
        except Exception as falha:  # noqa: BLE001 — «não mediu» se diz, não se esconde
            partes.append(f"NÃO DEU PARA MEDIR: {type(falha).__name__}: {_curto(falha, 200)}")
            meu.append(f"descobrir por que «{titulo}» não deu para medir")
        partes.append("")

    def do_despachante() -> list[str]:
        with db.connect() as con:
            batida = AU.batida_do_despachante(con, agora)
        if batida["nunca"]:
            meu.append("o despachante nunca rodou neste banco: gerar o instalador "
                       "(`op rodar -- python tools/gerar_instalador_automacao.py`) e registrar a tarefa")
            return ["NUNCA rodou neste banco. Sem ele, nenhuma rotina roda."]
        if batida["parado"]:
            meu.append(f"o despachante está parado (último tique {batida['hora']}): ver a tarefa "
                       "do Agendador (ou o launchd) e por que ela parou")
            return [f"PARADO: o último tique foi {batida['hora']}."]
        return [f"No ar: último tique {batida['hora']}."]

    cofre_itens: dict[str, dict] = {}
    cofre_medido = {"ok": False, "aberto": False}

    def do_cofre() -> list[str]:
        COFRE, caminho = _cofre()
        estado = COFRE.estado(caminho=caminho)
        for item in COFRE.listar(caminho=caminho):
            cofre_itens[item["nome"]] = item
        cofre_medido.update(ok=True, aberto=bool(estado.get("aberto")))
        if not estado.get("existe"):
            linhas = ["O cofre ainda NÃO EXISTE neste servidor."]
            dele.append(f"criar o cofre e a senha-mestra ({ONDE_SE_DIGITA})")
        elif estado.get("aberto"):
            linhas = [f"ABERTO desde {_quando(estado.get('desde'))}."]
        elif not estado.get("guardiao"):
            linhas = ["TRANCADO, e o guardião não está no ar (ele inicia no logon do servidor)."]
            meu.append("o guardião do cofre não está no ar: ver por que não iniciou "
                       "(`tools/automacao_guardiao.py`; o lançador vem do instalador da automação)")
            dele.append(f"desbloquear o cofre com a senha-mestra ({ONDE_SE_DIGITA}, Desbloquear)")
        else:
            linhas = ["TRANCADO (o guardião está no ar)."]
            dele.append(f"desbloquear o cofre com a senha-mestra ({ONDE_SE_DIGITA}, Desbloquear)")
        for nome, item in cofre_itens.items():
            dias = item.get("dias_para_vencer")
            validade = ("sem validade" if dias is None else
                        "VENCIDA" if dias < 0 else f"vence em {dias} dia(s)")
            linhas.append(f"- «{nome}» ({item.get('nome_do_tipo') or item.get('tipo')}; campos: "
                          f"{', '.join(item.get('campos_presentes') or []) or '—'}; {validade})")
            if dias is not None and dias <= DIAS_DE_AVISO:
                dele.append(f"renovar a credencial «{nome}» do cofre ({validade}) em {ONDE_SE_DIGITA}")
        if not cofre_itens:
            linhas.append("- nenhuma credencial cadastrada.")
        return linhas

    def das_rotinas() -> list[str]:
        with db.connect() as con:
            linhas_do_painel = AU.painel(con, agora)
            faltas = {p["id"]: p["falta"] for grupo in AU.arranjo_dos_robos(con)
                      for p in grupo["processos"] if p.get("falta")}
        if not linhas_do_painel:
            meu.append("nenhum processo cadastrado: rodar `op robos semear`")
            return ["Nenhum processo cadastrado."]
        linhas, robo_atual = [], None
        for p in linhas_do_painel:
            if p["robo_nome"] != robo_atual:
                robo_atual = p["robo_nome"]
                linhas.append(f"### {robo_atual}")
            ultima = p.get("ultima") or {}
            situacao = ("rodando agora" if p.get("rodando") else
                        f"{_quando(ultima.get('terminada_em') or ultima.get('iniciada_em'))} "
                        f"{ultima.get('situacao')} — {_curto(ultima.get('relato'))}" if ultima
                        else "nunca rodou")
            credencial = str(p.get("usa_credencial") or "").strip()
            pedacos = [f"- {p['codigo']} «{p['nome']}» — {'LIGADA' if p['ativo'] else 'desligada'}",
                       p.get("agenda_texto") or "sem agenda", f"última: {situacao}"]
            if credencial:
                tem = credencial in cofre_itens
                pedacos.append(f"credencial «{credencial}»: "
                               + ("no cofre" if tem else "NÃO ESTÁ NO COFRE" if cofre_medido["ok"]
                                  else "cofre não medido"))
                if p["ativo"] and cofre_medido["ok"] and not tem:
                    dele.append(
                        f"cadastrar a credencial «{credencial}», que a rotina {p['codigo']} usa, em "
                        f"{ONDE_SE_DIGITA} — se for a conta de um robô DESTE sistema, eu mesmo crio "
                        f"com `op robos conta <login> --cofre {credencial}` (com o cofre aberto)")
            if faltas.get(p["id"]):
                pedacos.append(f"FALTA: {_curto(faltas[p['id']], 200)}")
            linhas.append("; ".join(pedacos))
            if p["ativo"] and not p.get("rodando") and ultima and \
                    ultima.get("situacao") in ("ERRO", "TEMPO_ESGOTADO", "INTERROMPIDA"):
                meu.append(f"a rotina {p['codigo']} terminou em {ultima.get('situacao')}: "
                           f"{_curto(ultima.get('relato') or ultima.get('erro'), 200)}")
        return linhas

    def do_quadro() -> list[str]:
        with db.connect() as con:
            robos = QUADRO.quadro(con, agora)
        linhas = []
        for r in robos:
            # INFO («ainda não ligado») não vira achado nem pendência: alarme
            # que soa sempre é alarme que ninguém ouve
            graves = [a for a in r.get("achados") or []
                      if a.get("gravidade") in ("CRITICO", "ATENCAO", "NAO_MEDIU")]
            achados = "; ".join(_curto(a.get("titulo"), 120) for a in graves)
            if r["situacao"] == "SEM_PONTO":
                ponto = "ainda não bate ponto"
            elif r["situacao"] == "MEDIDO_PELO_BANCO":
                ponto = "medido pelo que deixa no banco"
            else:
                ponto = f"última batida {_quando(r.get('ultima')) or '—'} ({r['situacao']})"
            linhas.append(f"- {r['nome']} — {ponto}" + (f"; ACHADOS: {achados}" if achados else ""))
            for a in graves:
                meu.append(f"o robô «{r['nome']}»: {_curto(a.get('titulo'), 140)}"
                           + (f" — {_curto(a.get('como_resolver'), 160)}"
                              if a.get("como_resolver") else ""))
        return linhas

    def das_contas() -> list[str]:
        with db.connect() as con:
            bd = banco(con)
            contas = bd.ler(
                """SELECT u.username, u.role, u.active, u.robo_responsavel_id,
                          r.username AS responsavel, r.active AS responsavel_ativo
                     FROM users u LEFT JOIN users r ON r.id = u.robo_responsavel_id
                    WHERE COALESCE(u.eh_robo, 0) = 1 ORDER BY u.username""")
            das_rotinas_automaticas = casa["IDR"].responsavel_das_rotinas(con)
        linhas = []
        for c in contas:
            if not c["robo_responsavel_id"]:
                responde = "SEM RESPONSÁVEL"
                if int(c["active"] or 0):
                    meu.append(f"a conta de robô «{c['username']}» está sem responsável: "
                               f"`op robos responsavel {c['username']}` define (por padrão, o oficial)")
            elif not int(c["responsavel_ativo"] or 0):
                responde = f"responsável {c['responsavel']} está INATIVO"
                meu.append(f"o responsável da conta de robô «{c['username']}» está inativo: "
                           f"trocar com `op robos responsavel {c['username']} --responsavel <login>`")
            else:
                responde = f"responsável: {c['responsavel']}"
            linhas.append(f"- {c['username']} ({c['role']}) — "
                          f"{'ativa' if int(c['active'] or 0) else 'inativa'}; {responde}")
        if not contas:
            linhas.append("- nenhuma conta de robô.")
        if das_rotinas_automaticas:
            linhas.append("- responde pelas rotinas automáticas: "
                          f"{das_rotinas_automaticas.get('nome')}"
                          + ("" if das_rotinas_automaticas.get("configurado")
                             else " (não configurado: vale o primeiro ADMIN)"))
        return linhas

    def do_agendador() -> list[str]:
        tarefas = QUADRO.ler_agendador_do_windows()
        if not tarefas:
            return ["Não deu para ler o Agendador (ou não há tarefa CartorioGestao-*)."]
        ruins = {a.get("chave"): a for a in QUADRO.saude_do_agendador(tarefas)}
        linhas, vistas = [], set()
        for t in tarefas:
            if t["tarefa"] in vistas:
                continue
            vistas.add(t["tarefa"])
            linhas.append(f"- {t['tarefa']} — {t.get('situacao')}; última {t.get('ultima_execucao')}; "
                          f"resultado {t.get('ultimo_resultado')}")
            if f"AGENDADOR_FALHOU:{t['tarefa']}" in ruins:
                meu.append(f"a tarefa «{t['tarefa']}» do Agendador terminou com código "
                           f"{t.get('ultimo_resultado')}: ver o histórico dela")
        return linhas

    secao("O despachante (roda as rotinas, a cada minuto)", do_despachante)
    secao("O cofre das credenciais", do_cofre)
    secao("As rotinas, por robô", das_rotinas)
    secao("O quadro dos robôs da casa", do_quadro)
    secao("As contas de robô", das_contas)
    if os.name == "nt":
        secao("As tarefas do Agendador do Windows", do_agendador)
    partes.append("## O que falta")
    if not meu and not dele:
        partes.append("Nada: tudo o que este quadro mede está em ordem.")
    if meu:
        partes += ["Você (superusuário) resolve:"] + [f"- {item}" for item in meu]
    if dele:
        partes += ["Só o oficial pode (diga a ele, em lista curta):"] + [f"- {item}" for item in dele]
    return "\n".join(partes)


# ------------------------------------------------------------- a conta do robô

def _quem_responde(bd, responsavel: str) -> tuple[dict | None, str]:
    """A pessoa que vai responder pelo robô. Sem nome dito, é quem responde
    pelo superusuário: o oficial."""
    responsavel = str(responsavel or "").strip()
    if not responsavel:
        dono = bd.um("SELECT r.username FROM users u JOIN users r ON r.id = u.robo_responsavel_id "
                     "WHERE u.username=%s", (INT.LOGIN,))
        responsavel = (dono or {}).get("username") or ""
    pessoa = bd.um("SELECT id FROM users WHERE username=%s AND active=1 "
                   "AND COALESCE(eh_robo,0)=0", (responsavel,)) if responsavel else None
    return pessoa, responsavel


def responsavel(login: str, *, responsavel: str = "", db=None) -> str:  # noqa: A002
    """Define quem responde por uma conta de robô que já existe. NÃO mexe na
    senha: é o conserto do robô que roda, mas não diz a mando de quem."""
    login = str(login or "").strip()
    if INT.no_reserva():
        raise Recusa("Conta se acerta no servidor principal; chega ao reserva pela réplica.")
    casa = _casa()
    db = db or _db()
    with db.connect() as con:
        bd = casa["banco"](con)
        pessoa, quem = _quem_responde(bd, responsavel)
        robo = bd.um("SELECT id, COALESCE(eh_robo,0) AS eh_robo FROM users WHERE username=%s",
                     (login,))
    if not robo or not int(robo["eh_robo"] or 0):
        raise Recusa(f"«{login}» não é conta de robô. Só conta de robô tem responsável.")
    if not pessoa:
        raise Recusa("Diga quem responde pelo robô (--responsavel <login>): uma pessoa com "
                     "cadastro ativo, que não seja AUDITOR.")
    try:
        with db.transaction() as con:
            casa["IDR"].definir_responsavel_do_robo(con, int(robo["id"]), int(pessoa["id"]))
    except ValueError as falha:
        raise Recusa(str(falha)) from falha
    _auditar(db, "USER_ROBO_RESPONSAVEL_ALTERADO", "USER", int(robo["id"]),
             {"username": login, "eh_robo": 1, "responsavel": quem})
    return f"Robô «{login}»: quem responde por ele agora é {quem}. A senha não foi mexida."


def conta(login: str, *, nome: str = "", responsavel: str = "", papel: str = "USER",
          cofre: str = "", arquivo: str = "", db=None) -> str:
    """Cria a conta de robô — ou, se ela já existe, troca a senha dela — e
    guarda a senha SORTEADA onde o robô a lê: no cofre da automação (`cofre`,
    o nome do item) ou em `<dados>/<arquivo>.cred`. A senha não aparece em
    lugar nenhum. Devolve a frase do que foi feito."""
    login = str(login or "").strip()
    papel = str(papel or "USER").strip().upper()
    if not login:
        raise Recusa("Diga o login da conta de robô.")
    if login == INT.LOGIN:
        raise Recusa("A conta do superusuário se cria com `intervencao.py criar-conta`, "
                     "e a senha dela não se troca por aqui.")
    if papel not in PAPEIS_DE_ROBO:
        raise Recusa("Conta de robô só tem perfil USER ou AUDITOR "
                     "(docs/IDENTIDADE_DOS_ROBOS.md). Nenhum outro robô administra.")
    if bool(cofre) == bool(arquivo):
        raise Recusa("Diga onde a senha do robô fica: --cofre <item> (o cofre da automação) "
                     "ou --arquivo <nome> (vira <dados>/<nome>.cred). Um dos dois.")
    if INT.no_reserva():
        raise Recusa("Conta se cria no servidor principal; ela chega ao reserva pela réplica.")
    casa = _casa()
    banco, IDR = casa["banco"], casa["IDR"]
    db = db or _db()
    COFRE, caminho = _cofre()
    if cofre and not COFRE.estado(caminho=caminho).get("aberto"):
        raise Recusa("O cofre está trancado, e a senha nova não teria onde ficar: não mexi na "
                     f"conta. Só o oficial o abre ({ONDE_SE_DIGITA}, Desbloquear).")
    with db.connect() as con:
        bd = banco(con)
        pessoa, responsavel = _quem_responde(bd, responsavel)
        existente = bd.um("SELECT id, COALESCE(eh_robo,0) AS eh_robo, active FROM users "
                          "WHERE username=%s", (login,))
    if not pessoa:
        raise Recusa("Diga quem responde pelo robô (--responsavel <login>): uma pessoa com "
                     "cadastro ativo, que não seja AUDITOR.")
    if existente and not int(existente["eh_robo"] or 0):
        raise Recusa(f"«{login}» é conta de PESSOA. Robô não usa a senha de uma pessoa, e eu "
                     "não troco a senha de ninguém.")
    senha = secrets.token_urlsafe(24) + "aA1#"
    try:
        if existente:
            uid = int(existente["id"])
            db.reset_password(uid, senha)
            acao, feito = "PASSWORD_RESET", "senha trocada"
        else:
            uid = db.create_user(login, nome.strip() or login, senha, papel,
                                 int(pessoa["id"]), eh_robo=1)
            acao, feito = "USER_CREATED", f"conta criada (perfil {papel})"
        with db.transaction() as con:
            IDR.definir_responsavel_do_robo(con, uid, int(pessoa["id"]))
    except ValueError as falha:
        raise Recusa(str(falha)) from falha
    try:
        if cofre:
            COFRE.gravar(cofre, {"usuario": login, "senha": senha}, tipo=COFRE.SENHA,
                         por=INT.LOGIN, caminho=caminho)
            onde = f"no cofre, item «{cofre}»"
        else:
            alvo = INT.pasta_de_dados() / f"{BANDEJA.nome_seguro(arquivo)}.cred"
            COFRE.gravar_restrito(alvo, f"USUARIO={login}\nSENHA={senha}\n")
            onde = f"em {alvo}"
    except Exception as falha:  # noqa: BLE001 — a conta já mudou: diga como consertar
        raise Recusa(f"A {feito}, mas a senha NÃO ficou guardada ({type(falha).__name__}: "
                     f"{_curto(falha, 200)}). Rode o mesmo comando de novo: ele sorteia outra "
                     "senha e guarda.") from falha
    _auditar(db, acao, "USER", uid, {"username": login, "eh_robo": 1, "responsavel": responsavel,
                                     "senha_guardada": "cofre" if cofre else "arquivo .cred"})
    aviso = "" if not existente or int(existente["active"] or 0) else " A conta está INATIVA."
    return (f"Robô «{login}»: {feito}; responsável: {responsavel}; a senha foi sorteada e "
            f"guardada {onde} — ninguém a viu.{aviso}")


# ------------------------------------------------------------------ as rotinas

def processo(acao: str, codigo: str, *, db=None) -> str:
    """Liga, desliga ou pede a rodada de um processo, pelas funções da casa."""
    casa = _casa()
    AU = casa["AU"]
    if INT.no_reserva():
        raise Recusa("As rotinas rodam no servidor principal: o reserva só lê.")
    db = db or _db()
    with db.transaction() as con:
        p = AU.por_codigo(con, str(codigo or "").strip())
        if not p:
            raise Recusa(f"Não há processo com o código «{codigo}». Veja os códigos no `quadro`.")
        if acao == "rodar":
            AU.pedir_rodada(con, p["id"], usuario=INT.LOGIN)
            frase, auditoria = "rodada pedida: o despachante a pega no próximo minuto", \
                "AUTOMACAO_RODAR_AGORA"
        else:
            AU.definir_ativo(con, p["id"], acao == "ligar", usuario=INT.LOGIN)
            frase, auditoria = ("ligado" if acao == "ligar" else "desligado"), "AUTOMACAO_ALTERADO"
    _auditar(db, auditoria, "au_processos", int(p["id"]), {"codigo": p["codigo"], "acao": acao})
    aviso = ""
    credencial = str(p.get("usa_credencial") or "").strip()
    if acao != "desligar" and credencial:
        COFRE, caminho = _cofre()
        if not COFRE.tem(credencial, caminho=caminho):
            aviso = (f" ATENÇÃO: ele usa a credencial «{credencial}», que não está no cofre: "
                     "a rodada vai dar AVISO até ela ser cadastrada.")
    return f"{p['codigo']} «{p['nome']}»: {frase}.{aviso}"


def semear(*, db=None) -> str:
    """Cadastra os processos de fábrica que ainda não estão no banco (os de
    uma versão nova chegam assim). Todos nascem DESLIGADOS."""
    AU = _casa()["AU"]
    if INT.no_reserva():
        raise Recusa("As rotinas se cadastram no servidor principal.")
    db = db or _db()
    with db.transaction() as con:
        novos = AU.semear(con)
    if novos:
        _auditar(db, "AUTOMACAO_ALTERADO", "au_processos", None, {"semeados": int(novos)})
    return (f"{novos} processo(s) de fábrica cadastrado(s), todos desligados: ligue os que a casa usa."
            if novos else "Nenhum processo novo: o cadastro já tem todos os de fábrica.")


# ------------------------------------------------------------- linha de comando

def main(argv: list[str] | None = None) -> int:
    for saida in (sys.stdout, sys.stderr):
        try:
            saida.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    ap = argparse.ArgumentParser(prog="operador/robos.py",
                                 description="Os robôs e a automação, para o superusuário.")
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("quadro")
    co = sub.add_parser("conta")
    co.add_argument("login")
    co.add_argument("--nome", default="")
    co.add_argument("--responsavel", default="")
    co.add_argument("--papel", default="USER")
    co.add_argument("--cofre", default="")
    co.add_argument("--arquivo", default="")
    re = sub.add_parser("responsavel")
    re.add_argument("login")
    re.add_argument("--responsavel", default="")
    for nome in ("ligar", "desligar", "rodar"):
        sub.add_parser(nome).add_argument("codigo")
    sub.add_parser("semear")
    a = ap.parse_args(argv)
    INT.carregar_ambiente()
    try:
        if a.comando == "quadro":
            print(quadro())
        elif a.comando == "conta":
            print(conta(a.login, nome=a.nome, responsavel=a.responsavel, papel=a.papel,
                        cofre=a.cofre, arquivo=a.arquivo))
        elif a.comando == "responsavel":
            print(responsavel(a.login, responsavel=a.responsavel))
        elif a.comando == "semear":
            print(semear())
        else:
            print(processo(a.comando, a.codigo))
    except Recusa as recusa:
        print(f"RECUSADO: {recusa}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
