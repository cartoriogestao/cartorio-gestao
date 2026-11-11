"""Os avisos da automação — quem fica sabendo quando um processo dá problema.

    «painel e sino, tarefa para o responsável, WhatsApp e e-mail; sem spam a
     cada minuto» — as decisões do oficial (24/10/2026)

OS QUATRO CANAIS
    PAINEL    um aviso da gestão (`nu_avisos_gestao`) e o contador no painel
              inicial. Some quando o processo volta ao normal.
    TAREFA    UMA tarefa por processo para o responsável (`source_type =
              'AUTOMACAO'`), que se FECHA SOZINHA quando o processo volta a
              rodar bem. O pedido repetido vira nota na mesma tarefa
              (`create_task` já desduplica) — é o lembrete.
    EMAIL     pelo SMTP configurado na tela; a SENHA mora em `avisos.cred`
              (`cofre_cred`: cifrado, fora do banco, só o sistema lê), nunca
              em `au_config` — e não no cofre da senha-mestra, que trancado
              calaria o e-mail que avisa que ele está trancado.
    WHATSAPP  declarado e NÃO configurado: nesta fase não existe envio de
              WhatsApp, e inventar uma API seria pior que esperar. O aviso que
              iria fica registrado como PENDENTE_CONFIG — ninguém conclui que
              mandou o que não mandou.

SEM SPAM — A REGRA DA TRANSIÇÃO
    Avisa quando o processo PASSA de bem para problema (ALERTA), quando o
    problema PIORA (aviso → erro), e lembra no máximo a cada N horas
    (LEMBRETE; N na tela, por processo ou geral). Quando volta a rodar bem,
    fecha a tarefa, apaga o aviso do painel e diz por e-mail que normalizou.
    Um processo que falha a cada minuto manda UM e-mail, e não sessenta.

UM E-MAIL POR DIA, E NÃO UM POR AVISO — 28/10/2026
    «não gostei de receber tantos e-mails dos robôs; não precisa me avisar
     cada detalhe» — o oficial, no primeiro dia com a automação ligada.
    Medido na produção: **21 e-mails em 13 horas**, de 13 processos. A regra
    da transição segurava cada processo; o que ela não segurava era a SOMA:
    vinte processos, cada um com o seu alerta, lembrete e normalizou. Desde
    então o processo NOVO nasce sem o canal e-mail (`CANAIS_PADRAO`), e o que
    sai é o RESUMO DO DIA (`enviar_resumo`): um e-mail, a partir da hora da
    tela, com tudo o que segue com problema — e nenhum quando nada está. O
    painel e a tarefa continuam avisando na hora. Quem quiser o e-mail na hora
    de um processo marca o canal nele.

O RESUMO DIZ O QUE PAROU, E NÃO QUE TUDO QUEBROU — 11/11/2026
    O e-mail único virou outra parede: cada aviso aberto, lado a lado, com o
    mesmo peso. Falta de credencial, caminho não configurado e cofre trancado
    saíam como «N processos pedem atenção», e a leitura era «está tudo errado
    e nada funcionando». O resumo agora separa quatro coisas e agrupa pelo
    robô (`automacao_processos.robo_que_responde`):
      parou        ERRO, prazo estourado ou parou no meio — isto não funcionou;
      pede gente   AVISO de trabalho do dia (remessa, pendência, disco);
      cofre        o processo não mediu porque a senha-mestra não foi digitada;
      sem arranjo  credencial ou caminho ainda não cadastrados.
    Sem arranjo NÃO entra no e-mail: alarme todo dia deixa de ser alarme. Fica
    na central. Cofre sozinho vira um assunto só («o cofre está trancado»),
    e não uma lista de panes.

O QUE VAI NA MENSAGEM
    O relato, que fala em números («3 comunicações vencidas»), o nome do
    processo e onde ver o relatório. **Nome de parte, CPF e teor não vão** —
    ficam nos achados, dentro do sistema. O e-mail sai da casa.
"""
from __future__ import annotations

import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any

import automacao_schema as SCH
from bd_nativo import banco

SOURCE_TYPE = "AUTOMACAO"
PRAZO_DO_SMTP_S = 20


def _iso(quando: datetime) -> str:
    return quando.replace(microsecond=0).isoformat()


def _dt(texto: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(texto)[:19]) if texto else None
    except ValueError:
        return None


# ------------------------------------------------------------------ a decisão


def decidir(processo: dict, execucao: dict, *, agora: datetime, lembrar_h: int) -> str | None:
    """O motivo do aviso desta rodada, ou None (nada a avisar). **SÓ DECIDE.**"""
    situacao = execucao.get("situacao")
    if situacao in (SCH.PULADA, SCH.RODANDO):
        return None
    if situacao in SCH.PROBLEMAS:
        if not processo.get("alerta_desde"):
            return SCH.ALERTA
        if SCH.PESO.get(situacao, 0) > SCH.PESO.get(processo.get("alerta_situacao"), 0):
            return SCH.PIOROU
        ultimo = _dt(processo.get("alertado_em"))
        if ultimo is None or agora - ultimo >= timedelta(hours=lembrar_h):
            return SCH.LEMBRETE
        return None
    return SCH.NORMALIZOU if processo.get("alerta_desde") else None


def responsavel(con, processo: dict) -> int | None:
    """O responsável do processo, ou o oficial: o titular da Gestão, senão o 1º ADMIN."""
    if processo.get("responsavel_user_id"):
        return int(processo["responsavel_user_id"])
    bd = banco(con)
    if bd.tem_tabela("ge_responsaveis"):
        linha = bd.um("SELECT user_id FROM ge_responsaveis WHERE setor='GESTAO' LIMIT 1")
        if linha and linha["user_id"]:
            return int(linha["user_id"])
    robo = "AND COALESCE(eh_robo,0)=0" if bd.tem_coluna("users", "eh_robo") else ""
    linha = bd.um(f"SELECT id FROM users WHERE role='ADMIN' AND active=1 {robo} ORDER BY id LIMIT 1")
    return int(linha["id"]) if linha else None


def _registrar(db, *, execucao_id, processo_id, canal, motivo, destino, situacao, agora, erro=None):
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO au_avisos (execucao_id, processo_id, canal, motivo, destino, situacao,
                   criado_em, enviado_em, erro) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (execucao_id, processo_id, canal, motivo, destino, situacao, _iso(agora),
             _iso(agora) if situacao == SCH.ENVIADO else None, (erro or None) and str(erro)[:500]))
    return {"canal": canal, "situacao": situacao, "destino": destino, "erro": erro}


def _texto(processo: dict, execucao: dict, motivo: str) -> tuple[str, str]:
    selo = SCH.selo(execucao.get("situacao"))
    cabeca = {SCH.ALERTA: "deu problema", SCH.PIOROU: "piorou", SCH.LEMBRETE: "continua com problema",
              SCH.NORMALIZOU: "voltou ao normal", SCH.TESTE: "teste"}[motivo]
    assunto = f"[Automação] {processo['nome']}: {cabeca}"
    corpo = (f"Processo: {processo['nome']} ({processo['codigo']})\n"
             f"Situação da rodada #{execucao['id']}: {selo['texto']}\n"
             f"Quando: {str(execucao.get('terminada_em') or execucao.get('iniciada_em'))[:16].replace('T', ' ')}\n\n"
             f"{execucao.get('relato') or '(sem relato)'}\n\n"
             "O relatório completo está no sistema, em Administrativo → Automação"
             + (f" (/automacao/execucoes/{execucao['id']})." if execucao.get("id") else "."))
    return assunto, corpo


# ------------------------------------------------------------------ o e-mail


def configuracao_de_email(con) -> dict:
    return {"host": SCH.ler_config(con, SCH.CHAVE_SMTP_HOST).strip(),
            "porta": SCH.ler_config(con, SCH.CHAVE_SMTP_PORTA).strip(),
            "usuario": SCH.ler_config(con, SCH.CHAVE_SMTP_USUARIO).strip(),
            "remetente": SCH.ler_config(con, SCH.CHAVE_SMTP_REMETENTE).strip(),
            "seguranca": SCH.ler_config(con, SCH.CHAVE_SMTP_SEGURANCA).strip().upper() or "STARTTLS",
            "destinos": [d.strip() for d in SCH.ler_config(con, SCH.CHAVE_EMAIL_DESTINO).replace(";", ",").split(",")
                         if d.strip()]}


def remetente(cfg: dict) -> Any:
    """O cabeçalho From. Só calcula.

    O CAMPO «REMETENTE» ACEITA UM NOME — 27/10/2026, na configuração da
    produção: o oficial escreveu ali o nome da serventia (com acento e sem
    «@»), o sistema o usou como ENDEREÇO, e o Proton recusou com
    `SMTPNotSupportedError` (endereço com caractere fora do ASCII). Sem «@», o
    campo é o NOME a mostrar, e o endereço é o do usuário do SMTP.
    """
    from email.headerregistry import Address
    nome = str(cfg.get("remetente") or "").strip()
    usuario = str(cfg.get("usuario") or "").strip()
    if "@" in nome or not nome:
        return nome or usuario
    if not usuario:
        raise ValueError("O remetente é um nome, e falta o endereço: preencha o "
                         "usuário do SMTP (o e-mail que envia).")
    return Address(display_name=nome, addr_spec=usuario)


def mandar_email(cfg: dict, senha: str, *, assunto: str, corpo: str,
                 smtp_classe: Any = None, anexos: Any = ()) -> None:
    """Manda pelo SMTP. Levanta em falha — quem chama registra FALHOU."""
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = remetente(cfg)
    msg["To"] = ", ".join(cfg["destinos"])
    msg.set_content(corpo)
    for nome, dados, mime in anexos:
        principal, _, secundario = mime.partition("/")
        msg.add_attachment(dados, maintype=principal, subtype=secundario, filename=nome)
    porta = int(cfg["porta"] or (465 if cfg["seguranca"] == "SSL" else 587))
    if smtp_classe is None:
        smtp_classe = smtplib.SMTP_SSL if cfg["seguranca"] == "SSL" else smtplib.SMTP
    kwargs = {"timeout": PRAZO_DO_SMTP_S}
    if cfg["seguranca"] == "SSL" and smtp_classe is smtplib.SMTP_SSL:
        kwargs["context"] = ssl.create_default_context()
    with smtp_classe(cfg["host"], porta, **kwargs) as smtp:
        if cfg["seguranca"] == "STARTTLS":
            smtp.starttls(context=ssl.create_default_context())
        if cfg["usuario"]:
            smtp.login(cfg["usuario"], senha)
        smtp.send_message(msg)


def _pasta(pasta_dados: Any):
    from pathlib import Path

    import automacao_cofre as AC
    return Path(pasta_dados or AC.pasta_de_dados())


def _senha_do_smtp(pasta_dados: Any, cfg: dict) -> str:
    if not cfg["usuario"]:
        return ""
    import cofre_cred
    return cofre_cred.ler(_pasta(pasta_dados), SCH.ARQUIVO_SMTP).get(SCH.CHAVE_SENHA_SMTP, "")


def tem_senha_do_smtp(pasta_dados: Any) -> bool:
    """Se há senha do SMTP guardada — para a tela dizer, sem devolvê-la."""
    import cofre_cred
    return bool(cofre_cred.ler(_pasta(pasta_dados), SCH.ARQUIVO_SMTP).get(SCH.CHAVE_SENHA_SMTP))


def gravar_senha_do_smtp(pasta_dados: Any, senha: str) -> None:
    """Grava a senha do SMTP em `avisos.cred`. ESCREVE EM DISCO. Vazio não grava."""
    if not (senha or "").strip():
        return
    import cofre_cred
    cofre_cred.gravar(_pasta(pasta_dados), SCH.ARQUIVO_SMTP, {SCH.CHAVE_SENHA_SMTP: senha})


#: Quem manda o e-mail. O teste troca por um falso.
ENVIO = {"email": mandar_email}


def _enviar_email(db, assunto, corpo, *, motivo, execucao_id, processo_id, agora, pasta_dados) -> dict:
    """Manda um e-mail e registra o que houve em `au_avisos`. Não levanta."""
    with db.connect() as con:
        cfg = configuracao_de_email(con)
    destino = ", ".join(cfg["destinos"])
    if not cfg["host"] or not cfg["destinos"]:
        return _registrar(db, execucao_id=execucao_id, processo_id=processo_id, canal=SCH.EMAIL,
                          motivo=motivo, destino=destino or None, situacao=SCH.PENDENTE_CONFIG,
                          agora=agora, erro="o e-mail não está configurado (servidor SMTP e destino)")
    try:
        senha = _senha_do_smtp(pasta_dados, cfg)
        ENVIO["email"](cfg, senha, assunto=assunto, corpo=corpo)
    except Exception as erro:                 # noqa: BLE001 — registra e segue
        return _registrar(db, execucao_id=execucao_id, processo_id=processo_id, canal=SCH.EMAIL,
                          motivo=motivo, destino=destino, situacao=SCH.FALHOU, agora=agora,
                          erro=f"{type(erro).__name__}: {erro}")
    return _registrar(db, execucao_id=execucao_id, processo_id=processo_id, canal=SCH.EMAIL,
                      motivo=motivo, destino=destino, situacao=SCH.ENVIADO, agora=agora)


def _canal_email(db, processo, execucao, motivo, *, agora, pasta_dados) -> dict:
    assunto, corpo = _texto(processo, execucao, motivo)
    return _enviar_email(db, assunto, corpo, motivo=motivo, execucao_id=execucao.get("id"),
                         processo_id=processo.get("id"), agora=agora, pasta_dados=pasta_dados)


# ------------------------------------------------------------------ o resumo do dia

#: Quanto do relato de cada processo vai no resumo. O relato fala em números;
#: o teto é para um relato comprido não virar um e-mail de dez páginas.
TETO_DO_RELATO_NO_RESUMO = 300

PAROU, PEDE_GENTE, COFRE, SEM_ARRANJO = "parou", "pede_gente", "cofre", "sem_arranjo"
CLASSES = (PAROU, PEDE_GENTE, COFRE, SEM_ARRANJO)

#: Frases que a verificação já usa quando o que falta é cadastro, e não uma pane.
#: «não está configurad» pega configurado e configurada.
_MARCAS_DE_SEM_ARRANJO = (
    "credencial não está cadastrada",
    "credencial não cadastrada",
    "credencial indisponível",
    "não está configurad",
    "caminho não configurado",
    "caminho fora das pastas",
)


def classe_do_alerta(situacao: Any, relato: Any, erro: Any) -> str:
    """parou, pede gente, cofre ou sem arranjo. **SÓ CLASSIFICA.**

    Erro, prazo estourado e parada no meio são pane mesmo que o texto fale em
    credencial. Cofre vem antes de «sem arranjo»: a senha-mestra destrava
    vários processos de uma vez, e não é um defeito de cada um.
    """
    if str(situacao or "").upper() in (SCH.ERRO, SCH.TEMPO_ESGOTADO, SCH.INTERROMPIDA):
        return PAROU
    texto = f"{erro or ''}\n{relato or ''}".casefold()
    if "cofre trancado" in texto or "cofre está trancado" in texto:
        return COFRE
    if any(marca in texto for marca in _MARCAS_DE_SEM_ARRANJO):
        return SEM_ARRANJO
    return PEDE_GENTE


def _relato_curto(texto: Any) -> str:
    relato = " ".join(str(texto or "(sem relato)").split())
    if len(relato) > TETO_DO_RELATO_NO_RESUMO:
        return relato[:TETO_DO_RELATO_NO_RESUMO - 1].rstrip() + "…"
    return relato


def quadros(con, *, so_ligados: bool = False) -> dict[str, list[dict]]:
    """Os alertas abertos, separados e agrupáveis pelo robô. **SÓ LÊ.**

    Cada item traz o processo, a classe, o robô, o relato da última rodada
    que não está rodando e o id dela (para o link). A ordem é a do quadro
    dos robôs, e dentro do robô o pior primeiro.
    """
    import automacao_processos as PROC
    filtro = "AND ativo = 1" if so_ligados else ""
    bd = banco(con)
    abertos = bd.ler(
        f"""SELECT id, codigo, nome, robo_oficial, alerta_situacao, alerta_desde, ativo
              FROM au_processos WHERE alerta_desde IS NOT NULL {filtro}""")
    saida: dict[str, list[dict]] = {classe: [] for classe in CLASSES}
    for p in abertos:
        ultima = bd.um("""SELECT id, relato, erro FROM au_execucoes WHERE processo_id = %s
                           AND situacao <> %s ORDER BY id DESC LIMIT 1""", (p["id"], SCH.RODANDO)) or {}
        robo = PROC.robo_que_responde(p)
        classe = classe_do_alerta(p.get("alerta_situacao"), ultima.get("relato"), ultima.get("erro"))
        saida[classe].append({
            "id": p["id"], "codigo": p["codigo"], "nome": p["nome"],
            "robo": robo, "robo_nome": PROC.nome_do_robo(robo),
            "situacao": p.get("alerta_situacao"),
            "selo": SCH.selo(p.get("alerta_situacao"))["texto"],
            "desde": str(p.get("alerta_desde") or "")[:16].replace("T", " "),
            "relato": _relato_curto(ultima.get("relato")),
            "execucao_id": ultima.get("id"),
            "ordem": PROC.ordem_do_robo(robo),
            "peso": SCH.PESO.get(p.get("alerta_situacao"), 0),
        })
    for classe in CLASSES:
        saida[classe].sort(key=lambda item: (item["ordem"], -item["peso"], item["nome"]))
    return saida


def _bloco(titulo: str, itens: list[dict]) -> str:
    if not itens:
        return ""
    linhas = [titulo]
    robo = None
    for item in itens:
        if item["robo_nome"] != robo:
            robo = item["robo_nome"]
            linhas.append(f"\n{robo}")
        linha = (f"• {item['nome']} — {item['selo']}, desde {item['desde']}\n"
                 f"  {item['relato']}")
        if item.get("execucao_id"):
            linha += f"\n  /automacao/execucoes/{item['execucao_id']}"
        linhas.append(linha)
    return "\n".join(linhas)


def _assunto(agora: datetime, q: dict[str, list[dict]]) -> str:
    data = f"{agora:%d/%m}"
    n_parou, n_gente, n_cofre = len(q[PAROU]), len(q[PEDE_GENTE]), len(q[COFRE])
    if not n_parou and not n_gente and n_cofre:
        return (f"[Automação] Resumo de {data}: o cofre está trancado"
                + (f" ({n_cofre} processos esperando)" if n_cofre != 1 else ""))
    pedacos = []
    if n_parou:
        pedacos.append("1 parou" if n_parou == 1 else f"{n_parou} pararam")
    if n_gente:
        pedacos.append("1 pendência" if n_gente == 1 else f"{n_gente} pendências")
    if n_cofre:
        pedacos.append("cofre trancado")
    return f"[Automação] Resumo de {data}: " + ", ".join(pedacos)


def resumo_do_dia(con, *, agora: datetime) -> tuple[str, str] | None:
    """O assunto e o corpo do resumo, ou None quando o e-mail não tem o que dizer. **SÓ MONTA.**

    Entra quem está LIGADO e com alerta aberto. Quem rodou bem não aparece.
    Quem só está sem credencial ou sem caminho também não: isso fica na central.
    """
    q = quadros(con, so_ligados=True)
    if not q[PAROU] and not q[PEDE_GENTE] and not q[COFRE]:
        return None
    partes = [f"Resumo dos robôs em {agora:%d/%m/%Y, %H:%M}."]
    bloco = _bloco("Parou — isto não funcionou", q[PAROU])
    if bloco:
        partes.append(bloco)
    bloco = _bloco("Pede gente hoje — o robô rodou e achou trabalho", q[PEDE_GENTE])
    if bloco:
        partes.append(bloco)
    if q[COFRE]:
        nomes = "\n".join(f"• {item['robo_nome']} — {item['nome']}" for item in q[COFRE])
        partes.append("O cofre está trancado. Estes processos não mediram; "
                      "não é uma pane de cada um. Abra o cofre na máquina do servidor "
                      "(Automação → Cofre → Desbloquear).\n" + nomes)
    if q[SEM_ARRANJO]:
        n = len(q[SEM_ARRANJO])
        fora = ("1 processo ainda sem credencial ou caminho não entra neste e-mail."
                if n == 1 else
                f"{n} processos ainda sem credencial ou caminho não entram neste e-mail.")
        partes.append(fora + " Estão em Administrativo → Automação.")
    partes.append("Os que rodaram bem não aparecem. Este é o único e-mail da automação no dia; "
                  "o painel e as tarefas continuam mostrando cada problema na hora.")
    return _assunto(agora, q), "\n\n".join(partes)


def enviar_resumo(db, *, agora: datetime | None = None, pasta_dados: Any = None) -> dict | None:
    """Manda o resumo do dia, se houver o que dizer. None = nada com problema, nada sai."""
    agora = agora or datetime.now()
    with db.connect() as con:
        montado = resumo_do_dia(con, agora=agora)
    if montado is None:
        return None
    assunto, corpo = montado
    return _enviar_email(db, assunto, corpo, motivo=SCH.RESUMO, execucao_id=None, processo_id=None,
                         agora=agora, pasta_dados=pasta_dados)


def _canal_whatsapp(db, processo, execucao, motivo, *, agora) -> dict:
    with db.connect() as con:
        destino = SCH.ler_config(con, SCH.CHAVE_WHATSAPP_DESTINO).strip()
    return _registrar(db, execucao_id=execucao.get("id"), processo_id=processo.get("id"),
                      canal=SCH.WHATSAPP, motivo=motivo, destino=destino or None,
                      situacao=SCH.PENDENTE_CONFIG, agora=agora,
                      erro="o envio de WhatsApp ainda não existe nesta instalação (fase 2)")


# ------------------------------------------------------------------ painel e tarefa


def _canal_painel(db, processo, execucao, motivo, *, agora) -> tuple[dict, int | None]:
    import nu_avisos_gestao as NU
    assunto, corpo = _texto(processo, execucao, motivo)
    with db.transaction() as con:
        if processo.get("aviso_id") and motivo == SCH.PIOROU:
            try:
                NU.desativar(con, int(processo["aviso_id"]), agora=_iso(agora))
            except NU.AvisoGestaoError:
                pass
        if processo.get("aviso_id") and motivo == SCH.LEMBRETE:
            aviso_id = int(processo["aviso_id"])
        else:
            aviso_id = NU.criar(con, titulo=assunto[:150], corpo=corpo[:2000], ativo=True, prioridade=0,
                                vigencia_inicio=agora.date().isoformat(), vigencia_fim=None,
                                agora=_iso(agora), criado_por=SOURCE_TYPE)
    return (_registrar(db, execucao_id=execucao.get("id"), processo_id=processo.get("id"),
                       canal=SCH.PAINEL, motivo=motivo, destino="painel",
                       situacao=SCH.ENVIADO, agora=agora), aviso_id)


def _canal_tarefa(db, processo, execucao, motivo, *, agora, dono) -> tuple[dict, int | None]:
    if dono is None:
        return (_registrar(db, execucao_id=execucao.get("id"), processo_id=processo.get("id"),
                           canal=SCH.TAREFA, motivo=motivo, destino=None, situacao=SCH.FALHOU,
                           agora=agora, erro="não há responsável nem ADMIN ativo para receber a tarefa"),
                None)
    _assunto, corpo = _texto(processo, execucao, motivo)
    grave = execucao.get("situacao") in (SCH.ERRO, SCH.TEMPO_ESGOTADO, SCH.INTERROMPIDA)
    tarefa_id = db.create_task({
        "source_type": SOURCE_TYPE, "source_ref": f"{SOURCE_TYPE}:{processo['codigo']}",
        # O TÍTULO NÃO MUDA COM A SITUAÇÃO: é por ele (mais a referência e o
        # responsável) que `create_task` reconhece a MESMA tarefa e põe nota
        # nela em vez de abrir outra.
        "title": f"[Automação] {processo['nome']}"[:200],
        "description": corpo, "sector": processo.get("setor") or "GESTAO",
        "system_name": "Automação", "priority": "ALTA" if grave else "MEDIA",
        "status": "ABERTA", "start_date": agora.date().isoformat(),
        "due_date": agora.date().isoformat(), "assigned_user_id": dono,
        "evidence_required": 0}, None)
    return (_registrar(db, execucao_id=execucao.get("id"), processo_id=processo.get("id"),
                       canal=SCH.TAREFA, motivo=motivo, destino=f"tarefa #{tarefa_id}",
                       situacao=SCH.ENVIADO, agora=agora), tarefa_id)


def _fechar_tarefas(db, processo, *, agora) -> list[int]:
    """Fecha as tarefas abertas da automação deste processo. O problema acabou."""
    ref = f"{SOURCE_TYPE}:{processo['codigo']}"
    fechadas = []
    with db.transaction() as con:
        bd = banco(con)
        for t in bd.ler("""SELECT id, status FROM tasks WHERE source_type=%s AND source_ref=%s
                            AND status NOT IN ('CONCLUIDA','CANCELADA') ORDER BY id""",
                        (SOURCE_TYPE, ref)):
            bd.escrever("UPDATE tasks SET status='CONCLUIDA', completed_at=%s, updated_at=%s WHERE id=%s",
                        (_iso(agora), _iso(agora), t["id"]))
            bd.escrever("""INSERT INTO task_history (task_id, ts, user_id, action, old_value, new_value, note)
                           VALUES (%s,%s,NULL,'ALTEROU_STATUS',%s,'CONCLUIDA',%s)""",
                        (t["id"], _iso(agora), t["status"],
                         "O processo da automação voltou a rodar bem — fechada sozinha."))
            fechadas.append(int(t["id"]))
    return fechadas


# ------------------------------------------------------------------ o que o corredor chama


def tratar(db, processo: dict, execucao: dict, *, agora: datetime | None = None,
           pasta_dados: Any = None) -> dict:
    """Decide e manda os avisos desta rodada. Devolve o motivo e o que saiu por canal."""
    agora = agora or datetime.now()
    with db.connect() as con:
        geral = SCH.lembrar_a_cada_h(con)
    lembrar = int(processo.get("lembrar_a_cada_h") or geral)
    motivo = decidir(processo, execucao, agora=agora, lembrar_h=lembrar)
    if not motivo:
        return {"motivo": None, "canais": []}
    canais_marcados = processo.get("canais") or {}
    usar = (lambda c: bool(canais_marcados.get(c))) if canais_marcados else (lambda c: True)
    saidas, aviso_id, tarefa_id = [], processo.get("aviso_id"), processo.get("tarefa_id")
    if motivo == SCH.NORMALIZOU:
        fechadas = _fechar_tarefas(db, processo, agora=agora)
        if fechadas:
            saidas.append(_registrar(db, execucao_id=execucao["id"], processo_id=processo["id"],
                                     canal=SCH.TAREFA, motivo=motivo,
                                     destino=", ".join(f"#{t}" for t in fechadas),
                                     situacao=SCH.ENVIADO, agora=agora))
        if aviso_id:
            import nu_avisos_gestao as NU
            with db.transaction() as con:
                try:
                    NU.desativar(con, int(aviso_id), agora=_iso(agora))
                except NU.AvisoGestaoError:
                    pass
        if usar(SCH.EMAIL):
            saidas.append(_canal_email(db, processo, execucao, motivo, agora=agora, pasta_dados=pasta_dados))
        with db.transaction() as con:
            banco(con).escrever(
                """UPDATE au_processos SET alerta_desde=NULL, alerta_situacao=NULL, alertado_em=NULL,
                       aviso_id=NULL, tarefa_id=NULL WHERE id=%s""", (processo["id"],))
        return {"motivo": motivo, "canais": saidas}
    with db.connect() as con:
        dono = responsavel(con, processo)
    if usar(SCH.PAINEL):
        registro, aviso_id = _canal_painel(db, processo, execucao, motivo, agora=agora)
        saidas.append(registro)
    if usar(SCH.TAREFA):
        registro, novo = _canal_tarefa(db, processo, execucao, motivo, agora=agora, dono=dono)
        tarefa_id = novo or tarefa_id
        saidas.append(registro)
    if usar(SCH.EMAIL):
        saidas.append(_canal_email(db, processo, execucao, motivo, agora=agora, pasta_dados=pasta_dados))
    if usar(SCH.WHATSAPP):
        saidas.append(_canal_whatsapp(db, processo, execucao, motivo, agora=agora))
    pior = execucao["situacao"]
    if processo.get("alerta_situacao") and SCH.PESO.get(processo["alerta_situacao"], 0) > SCH.PESO.get(pior, 0):
        pior = processo["alerta_situacao"]
    with db.transaction() as con:
        banco(con).escrever(
            """UPDATE au_processos SET alerta_desde=COALESCE(alerta_desde, %s), alerta_situacao=%s,
                   alertado_em=%s, aviso_id=%s, tarefa_id=%s WHERE id=%s""",
            (_iso(agora), pior, _iso(agora), aviso_id, tarefa_id, processo["id"]))
    return {"motivo": motivo, "canais": saidas}


def enviar_teste(db, *, agora: datetime | None = None, pasta_dados: Any = None,
                 pedido_por: str = "") -> dict:
    """O e-mail de teste pedido na tela de configuração (roda no despachante)."""
    agora = agora or datetime.now()
    processo = {"id": None, "nome": "Teste do e-mail", "codigo": "TESTE"}
    execucao = {"id": None, "situacao": SCH.OK, "terminada_em": _iso(agora),
                "relato": f"E-mail de teste da automação, pedido por {pedido_por or 'alguém'} na tela "
                          "de configuração. Se chegou, o envio funciona."}
    return _canal_email(db, processo, execucao, SCH.TESTE, agora=agora, pasta_dados=pasta_dados)
