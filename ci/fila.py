"""A FILA DE MERGE — um PR por vez, testado exatamente como vai entrar (10/11/2026).

Decisão do proprietário: todo PR aberto pela conta proprietária, pronto (não
rascunho), com a suíte e o anti-leak verdes **e atualizado com o main** entra
sozinho, em squash. O repositório é de conta pessoal e não tem a «merge queue»
do GitHub; esta é a versão dela que cabe aqui.

COMO ANDA (cada rodada faz no máximo UM passo e sai — a próxima rodada vem do
fim da suíte, do horário de 10 em 10 minutos, ou de um PR novo):

  1. PR elegível e verde, cujo teste ainda vale → merge em squash (e repete o 1)
  2. alguma suíte ainda correndo, ou na fila do executor → espera
  3. o mais antigo elegível ainda não testado:
       teste vencido  → pede a suíte de novo, sem mexer na branch
       branch atrás («behind», só com o `strict`) → atualiza e pede a suíte e o anti-leak
       sem resultado  → pede a suíte e o anti-leak
  PR com suíte vermelha ou com conflito fica parado até alguém mexer nele.

QUANDO O TESTE AINDA VALE (11/11/2026). A suíte testa o PR mesclado com o main
daquele instante e grava esse main no status `suite-main`. Se o main andou depois,
o teste continua valendo quando o que entrou no main não toca em arquivo do PR nem
em arquivo de base (`ARQUIVOS_DE_BASE`). Se toca, a fila pede a suíte de novo: ela
junta o PR com o main da hora, e a branch não precisa mudar. Antes, todo merge obrigava cada PR verde a rodar a suíte inteira outra vez
(no 11/11, um PR ficou verde três vezes sem entrar). Para isso valer, a regra do
main não pode exigir a branch em dia (`strict`); com ela ligada, o GitHub responde
«behind» e a fila atualiza e testa de novo, como antes.

SUÍTE NA FILA DO EXECUTOR NÃO É «SEM RESULTADO» (11/11/2026). Com o executor
ocupado, a rodada de um PR espera sem ter postado nem o status pendente. A fila
via o PR sem suíte, pedia outra, e a nova cancelava a que esperava (o mesmo grupo
de concorrência). Agora a fila olha as rodadas da suíte que estão na fila ou
correndo (o nome delas é `suite #N`) e espera.

O QUE O TOKEN DESTA RODADA FAZ NÃO DISPARA OUTRO WORKFLOW (regra do GitHub):
por isso a suíte e o anti-leak são pedidos por `workflow_dispatch`, que é a
exceção permitida.

    python ci/fila.py            (no GitHub Actions, com GITHUB_TOKEN e GITHUB_REPOSITORY)
    python ci/fila.py --ensaio   (só diz o que faria)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

ROTULO_FORA_DA_FILA = "nao-mesclar"
ROTULO_CONFLITO = "conflito"
CONTEXTO_DA_SUITE = "suite"
CONTEXTO_DO_MAIN_TESTADO = "suite-main"
# O que muda tudo: se o main mexeu nisto depois do teste, o teste do PR venceu.
# `ci/suite/` é o ambiente da suíte (imagem, script); a fila e os workflows não mudam
# o resultado dos testes de um PR, e não entram aqui.
ARQUIVOS_DE_BASE = ("requirements", "tests/conftest.py", "banco_pg.py", "bd_nativo.py",
                    "app.py", "ci/suite/")
# O GitHub corta a lista de arquivos de uma comparação em 300: passou disso, não se sabe.
LIMITE_DA_COMPARACAO = 300
VERIFICACAO_ANTI_LEAK = "anti-leak"


@dataclass
class Pr:
    numero: int
    criado_em: str
    rascunho: bool
    autor: str
    mesmo_repositorio: bool
    rotulos: set[str] = field(default_factory=set)
    estado_merge: str = "unknown"      # clean | behind | dirty | blocked | unstable | unknown
    suite: str | None = None           # success | failure | error | pending | None
    anti_leak: str | None = None       # success | failure | pending | None
    head: str = ""
    branch: str = ""
    suite_na_fila: bool = False        # rodada da suíte na fila do executor ou correndo
    teste_vencido: bool = False        # o main mudou, depois do teste, no que o PR toca


def sobrepoe(do_main: list[str] | None, do_pr: list[str] | None) -> bool:
    """O que entrou no main depois do teste toca no PR? Lista `None` é lista cortada:
    não dá para saber, então toca."""
    if do_main is None or do_pr is None:
        return True
    if any(a.startswith(ARQUIVOS_DE_BASE) for a in do_main):
        return True
    return bool(set(do_main) & set(do_pr))


def elegivel(pr: Pr, dono: str) -> bool:
    return (not pr.rascunho and pr.autor == dono and pr.mesmo_repositorio
            and ROTULO_FORA_DA_FILA not in pr.rotulos)


def verde(pr: Pr) -> bool:
    return pr.suite == "success" and pr.anti_leak == "success"


def correndo(pr: Pr) -> bool:
    return pr.suite == "pending" or pr.anti_leak == "pending" or pr.suite_na_fila


def decidir(prs: list[Pr], dono: str) -> list[tuple]:
    """O próximo passo da fila. Só calcula — quem age é `executar`.

    Devolve uma lista de ações: ("mesclar", n), ("atualizar", n), ("disparar", n),
    ("marcar_conflito", n). Vazia: nada a fazer agora.
    """
    fila = sorted((p for p in prs if elegivel(p, dono)), key=lambda p: (p.criado_em, p.numero))
    for pr in fila:
        if verde(pr) and pr.estado_merge == "clean" and not pr.teste_vencido and not pr.suite_na_fila:
            return [("mesclar", pr.numero)]
    if any(correndo(p) for p in fila):
        return []
    acoes: list[tuple] = []
    for pr in fila:
        if pr.estado_merge == "dirty":
            if ROTULO_CONFLITO not in pr.rotulos:
                acoes.append(("marcar_conflito", pr.numero))
            continue
        if pr.suite in ("failure", "error") or pr.anti_leak == "failure":
            continue  # parado até um push novo
        if pr.estado_merge == "behind":
            return acoes + [("atualizar", pr.numero), ("disparar", pr.numero)]
        if pr.teste_vencido:
            # Sem atualizar a branch (12/11/2026): o commit de junção da fila sai em nome do
            # github-actions[bot], e o GitHub deixa o `pull_request` do anti-leak nele
            # esperando aprovação manual. A regra do main olha essa rodada parada, e o PR
            # verde não entra (#408, #424). A suíte já testa o PR junto com o main atual.
            return acoes + [("disparar", pr.numero)]
        if pr.suite is None or pr.anti_leak is None:
            return acoes + [("disparar", pr.numero)]
    return acoes


# ----------------------------------------------------------------- o GitHub


class GitHub:
    def __init__(self, repositorio: str, token: str):
        self.repo, self.token = repositorio, token

    def pedir(self, metodo: str, caminho: str, corpo: dict | None = None):
        url = caminho if caminho.startswith("https://") else f"https://api.github.com/repos/{self.repo}{caminho}"
        pedido = urllib.request.Request(url, method=metodo,
                                        data=json.dumps(corpo).encode() if corpo is not None else None,
                                        headers={"Authorization": f"Bearer {self.token}",
                                                 "Accept": "application/vnd.github+json",
                                                 "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(pedido, timeout=60) as r:
            texto = r.read()
        return json.loads(texto) if texto else None

    def prs(self) -> list[Pr]:
        lista = []
        for p in self.pedir("GET", "/pulls?state=open&base=main&per_page=100"):
            pr = Pr(numero=p["number"], criado_em=p["created_at"], rascunho=p["draft"],
                    autor=p["user"]["login"], head=p["head"]["sha"], branch=p["head"]["ref"],
                    mesmo_repositorio=(p["head"]["repo"] or {}).get("full_name") == self.repo,
                    rotulos={r["name"] for r in p.get("labels", [])})
            lista.append(pr)
        return lista

    def suites_na_fila(self) -> list[dict]:
        """As rodadas da suíte que ainda não terminaram (na fila do executor ou correndo)."""
        rodadas = []
        for estado in ("queued", "in_progress", "waiting", "pending", "requested"):
            rodadas += self.pedir(
                "GET", f"/actions/workflows/suite.yml/runs?status={estado}&per_page=100")["workflow_runs"]
        return rodadas

    def arquivos_do_pr(self, pr: Pr) -> list[str] | None:
        arquivos: list[str] = []
        for pagina in range(1, 31):
            lote = self.pedir("GET", f"/pulls/{pr.numero}/files?per_page=100&page={pagina}")
            arquivos += [a["filename"] for a in lote]
            if len(lote) < 100:
                return arquivos
        return None

    def julgar_o_teste(self, pr: Pr, main_testado: str | None) -> None:
        """O main andou depois do teste, no que o PR toca? Sem o `suite-main` (rodada de
        antes desta regra), a referência é o ponto em que a branch saiu do main."""
        if main_testado is None:
            main_testado = self.pedir("GET", f"/compare/main...{pr.head}")["merge_base_commit"]["sha"]
        depois = self.pedir("GET", f"/compare/{main_testado}...main")
        if not depois.get("ahead_by"):
            pr.teste_vencido = False
            return
        do_main = [a["filename"] for a in depois.get("files") or []]
        if len(do_main) >= LIMITE_DA_COMPARACAO:
            do_main = None
        pr.teste_vencido = sobrepoe(do_main, self.arquivos_do_pr(pr))

    def completar(self, pr: Pr) -> None:
        detalhe = self.pedir("GET", f"/pulls/{pr.numero}")
        # O GitHub calcula o estado de merge em segundo plano: «unknown» na primeira vez.
        for _ in range(5):
            if detalhe.get("mergeable_state") not in (None, "unknown"):
                break
            time.sleep(3)
            detalhe = self.pedir("GET", f"/pulls/{pr.numero}")
        pr.estado_merge = detalhe.get("mergeable_state") or "unknown"
        pr.head = detalhe["head"]["sha"]
        estados = self.pedir("GET", f"/commits/{pr.head}/statuses?per_page=100")
        da_suite = [s for s in estados if s["context"] == CONTEXTO_DA_SUITE]
        pr.suite = da_suite[0]["state"] if da_suite else None   # o mais recente vem primeiro
        do_main = [s for s in estados if s["context"] == CONTEXTO_DO_MAIN_TESTADO]
        main_testado = (do_main[0].get("description") or "").strip() if do_main else ""
        corridas = self.pedir("GET", f"/commits/{pr.head}/check-runs?check_name={VERIFICACAO_ANTI_LEAK}")
        if corridas["check_runs"]:
            c = corridas["check_runs"][0]
            pr.anti_leak = "pending" if c["status"] != "completed" else (
                "success" if c["conclusion"] == "success" else "failure")
        if pr.suite == "success" and pr.estado_merge == "clean":
            self.julgar_o_teste(pr, main_testado if len(main_testado) == 40 else None)

    def mesclar(self, pr: Pr) -> None:
        self.pedir("PUT", f"/pulls/{pr.numero}/merge",
                   {"merge_method": "squash", "sha": pr.head})

    def atualizar(self, pr: Pr) -> None:
        self.pedir("PUT", f"/pulls/{pr.numero}/update-branch", {"expected_head_sha": pr.head})
        # Espera o novo head, para o anti-leak não conferir o commit antigo.
        for _ in range(20):
            time.sleep(3)
            novo = self.pedir("GET", f"/pulls/{pr.numero}")["head"]["sha"]
            if novo != pr.head:
                pr.head = novo
                return

    def disparar(self, pr: Pr) -> None:
        self.pedir("POST", "/actions/workflows/suite.yml/dispatches",
                   {"ref": "main", "inputs": {"pr": str(pr.numero)}})
        self.pedir("POST", "/actions/workflows/anti-leak.yml/dispatches", {"ref": pr.branch})

    def marcar_conflito(self, pr: Pr) -> None:
        self.pedir("POST", f"/issues/{pr.numero}/labels", {"labels": [ROTULO_CONFLITO]})
        self.pedir("POST", f"/issues/{pr.numero}/comments", {"body": (
            "A fila de merge parou este PR: ele **conflita com o `main`**. Resolva o conflito "
            "(o rótulo `conflito` sai quando você o tirar) e a fila o retoma.")})


def na_fila(pr: Pr, rodadas: list[dict]) -> bool:
    """Há rodada da suíte deste PR ainda por terminar? Pelo nome (`suite #N`, os dois
    gatilhos) ou, nas rodadas de antes do nome, pela branch do `pull_request_target`."""
    for r in rodadas:
        if (r.get("display_title") or "").strip() == f"suite #{pr.numero}":
            return True
        if r.get("event") == "pull_request_target" and r.get("head_branch") == pr.branch:
            return True
    return False


def executar(gh: GitHub, dono: str, *, ensaio: bool = False, limite_de_merges: int = 5) -> list[tuple]:
    feito: list[tuple] = []
    for _ in range(limite_de_merges + 1):
        prs = gh.prs()
        rodadas = gh.suites_na_fila()
        for pr in prs:
            if elegivel(pr, dono):
                gh.completar(pr)
                pr.suite_na_fila = na_fila(pr, rodadas)
        acoes = decidir(prs, dono)
        por_numero = {p.numero: p for p in prs}
        for acao, numero in acoes:
            print(f"{acao} #{numero}")
            feito.append((acao, numero))
            if not ensaio:
                getattr(gh, acao)(por_numero[numero])
        if ensaio or not acoes or acoes[0][0] != "mesclar":
            return feito
        time.sleep(5)  # o main mudou: a próxima volta vê os outros atrás dele
    return feito


if __name__ == "__main__":
    repositorio = os.environ["GITHUB_REPOSITORY"]
    dono = os.environ.get("CG_FILA_DONO") or repositorio.split("/")[0]
    try:
        executar(GitHub(repositorio, os.environ["GITHUB_TOKEN"]), dono, ensaio="--ensaio" in sys.argv)
    except urllib.error.HTTPError as erro:
        print(f"GitHub respondeu {erro.code}: {erro.read()[:500]!r}")
        sys.exit(1)
