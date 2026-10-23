"""Os robôs da casa, e se cada um rodou e rodou bem.

    «robo responsavel por operacionalizar os outros robos» — o oficial, 09/10/2026

O QUE É «OPERACIONALIZAR» AQUI
    Não é rodar a regra de cada robô por cima dele: cada um tem o seu dono, o seu
    horário e a sua passada (os de número 1 a 9 estavam sendo construídos em
    paralelo, em 09/10/2026, cada um na sua sessão). É saber, todo dia, três
    coisas sobre cada um — **existe?** **rodou?** **rodou bem?** — e transformar
    a resposta em providência com dono, em vez de deixar numa linha de log.

O CONTRATO, E ELE É DE UMA LINHA SÓ
    Robô que quiser ser acompanhado chama, ao terminar a passada dele,

        oficial_robos.bater(con, "CARGAS_RCPN", situacao="OK", resumo={...})

    e pronto. Quem não bate é medido pelo que deixa no banco (o gestor, por
    exemplo, já tem `ge_execucoes` e `ge_leituras`, e é por elas que se lê). Robô
    que ainda não existe aparece como «ainda não ligado» — e não como erro:
    alarme que soa sempre é alarme que ninguém ouve.

O QUE ESTE MÓDULO NÃO FAZ
    Não conserta robô, não muda configuração, não lavra, não sela, não envia. Ele
    mede e diz o que fazer. Em 09/10/2026 a correção do modelo da IA (o defeito
    que justificou este módulo) foi recusada à máquina e ficou com quem
    configura — que é como deve ser.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from bd_nativo import banco
from oficial_schema import init_oficial_schema

#: Os robôs da casa. `setores` liga o robô às tarefas que ele deixa na mesa de
#: alguém; `medido_por` diz de onde vem a batida quando o robô não chama
#: `bater` (o gestor existia antes deste contrato). `horas` é o intervalo em que
#: se espera ao menos uma batida — `None` quando o robô ainda não tem horário.
ROBOS: tuple[dict, ...] = (
    {"codigo": "GESTOR", "nome": "Gestor (conferência diária)",
     "missao": "confere a casa às 07:30, 14:00 e 14:30; abre, fecha e cobra tarefas",
     "medido_por": "ge_execucoes", "horas": 26, "setores": ()},
    {"codigo": "LEITURA_IA", "nome": "Leitura dos textos pela IA (parte do gestor)",
     "missao": "lê minutas e atos novos procurando erro objetivo",
     "medido_por": "ge_leituras", "horas": 26, "setores": ()},
    {"codigo": "CARGAS_RCPN", "nome": "1. Cargas do RCPN",
     "missao": "mantém em dia as cargas do Registro Civil (SIRC, CRC, IBGE, FUNAI, óbitos)",
     "medido_por": None, "horas": 26, "setores": ("RCPN",)},
    {"codigo": "CARGAS_RI", "nome": "2. Cargas do RI",
     "missao": "mantém em dia as cargas do RI e das Notas (DOI, ONR, SAEC, CENSEC)",
     "medido_por": None, "horas": 26, "setores": ("RI",)},
    {"codigo": "COMPLIANCE", "nome": "3. Compliance",
     "missao": "fiscaliza os outros robôs e a regularidade dos atos e informações",
     "medido_por": None, "horas": 26, "setores": ("COMPLIANCE",)},
    {"codigo": "FINANCEIRO", "nome": "4. Financeiro e gratuidades",
     "missao": "caixa, fundos, gratuidades e o fechamento do mês",
     "medido_por": None, "horas": 26, "setores": ("CAIXA",)},
    {"codigo": "PROTESTO", "nome": "5. Protesto",
     "missao": "verificação dos atos do Protesto e das Centrais (CRA, CENPROT)",
     "medido_por": None, "horas": 26, "setores": ("PROTESTO",)},
    {"codigo": "RCPN", "nome": "6. Registro Civil",
     "missao": "fiscalização e resolução no Registro Civil",
     "medido_por": None, "horas": 26, "setores": ("RCPN",)},
    {"codigo": "RI", "nome": "7. Registro de Imóveis",
     "missao": "fiscalização e resolução no Registro de Imóveis",
     "medido_por": None, "horas": 26, "setores": ("RI",)},
    {"codigo": "NOTAS", "nome": "8. Notas",
     "missao": "fiscalização e resolução no Tabelionato de Notas",
     "medido_por": None, "horas": 26, "setores": ("NOTAS",)},
    {"codigo": "RTDPJ", "nome": "9. RTD e RCPJ",
     "missao": "fiscalização e resolução no RTD e no RCPJ",
     "medido_por": None, "horas": 26, "setores": ("RTD", "RCPJ")},
    {"codigo": "OFICIAL", "nome": "10. Robô oficial",
     "missao": "opera os outros robôs e cuida da mesa do oficial",
     "medido_por": "of_batidas", "horas": 26, "setores": ("GESTAO",)},
)

NOME_DO_ROBO = {r["codigo"]: r["nome"] for r in ROBOS}

#: A gravidade dos achados de saúde. NAO_MEDIU é a regra do gestor: o que
#: quebrou ao medir não vira zero.
GRAVIDADES = ("CRITICO", "ATENCAO", "NAO_MEDIU", "INFO")


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _tem_tabela(con: sqlite3.Connection, nome: str) -> bool:
    return banco(con).tem_tabela(nome)


def bater(con: sqlite3.Connection, robo: str, *, situacao: str = "OK",
          resumo: dict | None = None, erro: str | None = None,
          iniciada_em: str | None = None, quem_rodou: str = "PROPRIO") -> int:
    """Registra que um robô terminou uma passada. É o contrato inteiro."""
    situacao = (situacao or "OK").upper()
    if situacao not in ("OK", "AVISO", "ERRO"):
        raise ValueError(f"Situação de batida desconhecida: {situacao!r}. "
                         "Use OK, AVISO ou ERRO.")
    init_oficial_schema(con)
    agora = _agora()
    novo = banco(con).escrever(
        """INSERT INTO of_batidas (robo, iniciada_em, terminada_em, situacao,
               resumo_json, erro, quem_rodou) VALUES (%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (robo, iniciada_em or agora, agora, situacao,
         json.dumps(resumo or {}, ensure_ascii=False, default=str), erro, quem_rodou))
    return int(novo[0]["id"])


def ultima_batida(con: sqlite3.Connection, robo: str) -> dict | None:
    if not _tem_tabela(con, "of_batidas"):
        return None
    linha = banco(con).um(
        """SELECT robo, iniciada_em, terminada_em, situacao, resumo_json, erro
             FROM of_batidas WHERE robo = %s ORDER BY id DESC LIMIT 1""", (robo,))
    if not linha:
        return None
    return {"robo": linha["robo"], "iniciada_em": linha["iniciada_em"],
            "terminada_em": linha["terminada_em"], "situacao": linha["situacao"],
            "resumo": json.loads(linha["resumo_json"] or "{}"), "erro": linha["erro"]}


def _achado(regra, gravidade, robo, titulo, detalhe="", como_resolver="", chave=None):
    return {"regra": regra, "gravidade": gravidade, "robo": robo,
            "robo_nome": NOME_DO_ROBO.get(robo, robo), "titulo": titulo,
            "detalhe": detalhe, "como_resolver": como_resolver,
            "chave": chave or f"{regra}:{robo}"}


def _horas_desde(texto: str | None, agora: datetime) -> float | None:
    if not texto:
        return None
    try:
        quando = datetime.fromisoformat(texto[:19].replace(" ", "T"))
    except ValueError:
        return None
    return (agora - quando).total_seconds() / 3600


# --------------------------------------------------------------------------
# Cada robô medido pelo que ele deixa no banco
# --------------------------------------------------------------------------

def _saude_do_gestor(con, agora: datetime) -> list[dict]:
    if not _tem_tabela(con, "ge_execucoes"):
        return [_achado("ROBO_NUNCA_RODOU", "ATENCAO", "GESTOR",
                        "O gestor nunca rodou neste banco",
                        "A tabela ge_execucoes não existe.",
                        "Ligar a conferência diária (FERRAMENTAS/GESTOR) no Agendador.")]
    linha = banco(con).um(
        """SELECT iniciada_em, terminada_em, erro, achados, novos, nao_mediu
             FROM ge_execucoes ORDER BY id DESC LIMIT 1""")
    if not linha:
        return [_achado("ROBO_NUNCA_RODOU", "ATENCAO", "GESTOR",
                        "O gestor nunca rodou neste banco")]
    fora = []
    horas = _horas_desde(linha["iniciada_em"], agora)
    if horas is not None and horas > 26:
        fora.append(_achado(
            "ROBO_PARADO", "CRITICO", "GESTOR",
            f"O gestor não roda há {horas:.0f} horas",
            f"Última rodada: {linha['iniciada_em']}. O Agendador o chama às 07:30, 14:00 e 14:30.",
            "Conferir a tarefa «CartorioGestao-Conferencia-Diaria» no Agendador do "
            "Windows e o arquivo FERRAMENTAS/GESTOR/CONFERENCIA_DIARIA.log."))
    if linha["erro"]:
        fora.append(_achado(
            "ROBO_TERMINOU_COM_ERRO", "CRITICO", "GESTOR",
            "A última rodada do gestor terminou com erro — nada dela foi gravado",
            linha["erro"][:400],
            "Ler o fim de FERRAMENTAS/GESTOR/CONFERENCIA_DIARIA.log; o erro diz o arquivo e a linha."))
    elif linha["terminada_em"] is None and horas is not None and horas > 1:
        fora.append(_achado(
            "ROBO_NAO_TERMINOU", "CRITICO", "GESTOR",
            "A última rodada do gestor começou e não terminou",
            f"Começou em {linha['iniciada_em']} e não gravou fim nem erro — o processo morreu no meio.",
            "Ver o log da conferência diária e o espaço livre do disco C:."))
    if linha["nao_mediu"]:
        fora.append(_achado(
            "ROBO_NAO_MEDIU", "ATENCAO", "GESTOR",
            f"{linha['nao_mediu']} regra(s) do gestor não conseguiram medir na última rodada",
            "Regra que quebra vira NAO_MEDIU, e não zero — mas fica sem conferir.",
            "Abrir o relatório da conferência do dia e procurar «não mediu»."))
    return fora


#: A frase com que `agente_provedores` recusa nome de modelo que a API não
#: conhece. Medido em 09/10/2026: «Opus 5.5» (nome de vitrine) recusado, e
#: «claude-opus-5-5» aceito na mesma chave, no mesmo minuto.
_MODELO_DESCONHECIDO = "não conhece o modelo"


def _saude_da_leitura(con, agora: datetime) -> list[dict]:
    """A IA do gestor — o caso que fez este módulo nascer.

    MEDIDO NA PRODUÇÃO EM 09/10/2026: desde 08/10 08:28, **todas** as leituras
    falharam (0 lidas, 13 erros), todas com a mesma frase. A rodada do gestor
    seguia «com sucesso», porque leitura que falha não derruba conferência — e
    era isso que a escondia.
    """
    if not _tem_tabela(con, "ge_leituras"):
        return []
    desde = (agora - timedelta(hours=72)).isoformat(timespec="seconds")
    linhas = banco(con).ler(
        "SELECT lido_em, modelo, erro FROM ge_leituras WHERE lido_em >= %s ORDER BY lido_em, id",
        (desde,))
    if not linhas:
        return []
    erros = [r for r in linhas if r["erro"]]
    certas = [r for r in linhas if not r["erro"]]
    if not erros:
        return []
    ultima_certa = certas[-1]["lido_em"] if certas else None
    falhando_desde = next((r["lido_em"] for r in erros if ultima_certa is None or r["lido_em"] > ultima_certa), None)
    if falhando_desde is None:
        return []
    seguidas = sum(1 for r in erros if r["lido_em"] >= falhando_desde)
    if seguidas < 3:
        return []
    frase = erros[-1]["erro"]
    modelo = erros[-1]["modelo"]
    como = ("Abrir a tela de configuração do agente (Administrativo → Agente) e conferir "
            "o provedor e a chave.")
    if _MODELO_DESCONHECIDO in (frase or ""):
        como = (f"O modelo configurado é «{modelo}», que é nome de vitrine e a API recusa. "
                "Na tela de configuração do agente (Administrativo → Agente), trocar o "
                "modelo pelo nome da API — «claude-opus-5-5» foi aceito na conferência de "
                "09/10/2026. A leitura volta na rodada seguinte.")
    return [_achado(
        "IA_PARADA", "CRITICO", "LEITURA_IA",
        f"A leitura dos textos pela IA está parada: {seguidas} falha(s) seguidas desde "
        f"{falhando_desde[:16].replace('T', ' ')}",
        f"Última resposta do provedor: {frase[:300]}. A conferência do gestor continua "
        "rodando, e por isso o defeito não aparecia: os atos novos simplesmente não estão "
        "sendo lidos.",
        como)]


def _saude_por_batida(con, robo: dict, agora: datetime) -> list[dict]:
    batida = ultima_batida(con, robo["codigo"])
    if batida is None:
        return [_achado("ROBO_AINDA_NAO_LIGADO", "INFO", robo["codigo"],
                        f"{robo['nome']}: ainda não bate ponto",
                        "Nenhuma passada registrada. Robô em construção, ou construído sem "
                        "chamar oficial_robos.bater ao terminar.",
                        "Quem constrói o robô acrescenta a chamada de uma linha ao fim da passada.")]
    fora = []
    if batida["situacao"] == "ERRO":
        fora.append(_achado("ROBO_TERMINOU_COM_ERRO", "CRITICO", robo["codigo"],
                            f"{robo['nome']}: a última passada terminou com erro",
                            (batida["erro"] or "")[:400]))
    horas = _horas_desde(batida["terminada_em"], agora)
    if robo.get("horas") and horas is not None and horas > robo["horas"]:
        fora.append(_achado("ROBO_PARADO", "ATENCAO", robo["codigo"],
                            f"{robo['nome']}: sem passada há {horas:.0f} horas",
                            f"Última: {batida['terminada_em']}."))
    return fora


def saude(con: sqlite3.Connection, agora: datetime | None = None) -> list[dict]:
    """Um achado por robô que precisa de alguém. Lista vazia é a casa em ordem."""
    agora = agora or datetime.now()
    fora: list[dict] = []
    for robo in ROBOS:
        try:
            if robo["codigo"] == "GESTOR":
                fora += _saude_do_gestor(con, agora)
            elif robo["codigo"] == "LEITURA_IA":
                fora += _saude_da_leitura(con, agora)
            elif robo["codigo"] == "OFICIAL":
                continue                     # quem mede não se mede
            else:
                fora += _saude_por_batida(con, robo, agora)
        except sqlite3.Error as erro:
            fora.append(_achado("NAO_MEDIU", "NAO_MEDIU", robo["codigo"],
                                f"{robo['nome']}: não deu para medir",
                                f"{type(erro).__name__}: {erro}"))
    return fora


def quadro(con: sqlite3.Connection, agora: datetime | None = None) -> list[dict]:
    """Uma linha por robô para o painel: a última batida e o que se achou."""
    agora = agora or datetime.now()
    achados = saude(con, agora)
    por_robo: dict[str, list[dict]] = {}
    for a in achados:
        por_robo.setdefault(a["robo"], []).append(a)
    linhas = []
    for robo in ROBOS:
        batida = ultima_batida(con, robo["codigo"])
        meus = por_robo.get(robo["codigo"], [])
        pior = min((GRAVIDADES.index(a["gravidade"]) for a in meus), default=None)
        linhas.append({
            "codigo": robo["codigo"], "nome": robo["nome"], "missao": robo["missao"],
            "ultima": (batida or {}).get("terminada_em"),
            "situacao": ("SEM_PONTO" if batida is None and robo["medido_por"] is None
                         else (batida or {}).get("situacao") or "MEDIDO_PELO_BANCO"),
            "pior": GRAVIDADES[pior] if pior is not None else "OK",
            "achados": meus,
        })
    return linhas


def ler_agendador_do_windows() -> list[dict]:
    """As tarefas `CartorioGestao-*` do Agendador: o último resultado de cada uma.

    `schtasks` em CSV, sem acentos no que se lê (os nomes das colunas variam
    com a língua do Windows; lê-se pela posição do cabeçalho em inglês OU em
    português). Fora do Windows, ou se o comando falhar, devolve lista vazia — e
    quem chama diz «não deu para medir».
    """
    import csv
    import io
    import subprocess
    try:
        saida = subprocess.run(["schtasks", "/query", "/fo", "CSV", "/v"],
                               capture_output=True, timeout=60, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    texto = saida.decode("cp850", errors="replace")
    fora = []
    leitor = csv.reader(io.StringIO(texto))
    cabecalho = None
    for linha in leitor:
        if not linha:
            continue
        if linha[0] in ("HostName", "Nome do host"):
            cabecalho = linha
            continue
        if cabecalho is None or len(linha) != len(cabecalho):
            continue
        nome = linha[1].lstrip("\\")
        if not nome.startswith("CartorioGestao-"):
            continue
        fora.append({"tarefa": nome, "proxima": linha[2], "situacao": linha[3],
                     "ultima_execucao": linha[5], "ultimo_resultado": linha[6]})
    return fora


def saude_do_agendador(tarefas: list[dict]) -> list[dict]:
    """Tarefa do Agendador cujo último resultado não é zero."""
    fora = []
    vistas = set()
    for t in tarefas:
        if t["tarefa"] in vistas:
            continue
        vistas.add(t["tarefa"])
        resultado = (t.get("ultimo_resultado") or "").strip()
        if resultado in ("0", "", "267009", "267011"):   # ok · em execução · nunca rodou
            continue
        fora.append(_achado(
            "AGENDADOR_FALHOU", "ATENCAO", "OFICIAL",
            f"A tarefa «{t['tarefa']}» do Agendador terminou com código {resultado}",
            f"Última execução: {t.get('ultima_execucao')}.",
            "Abrir o Agendador de Tarefas do Windows e ver o histórico da tarefa.",
            chave=f"AGENDADOR_FALHOU:{t['tarefa']}"))
    return fora

