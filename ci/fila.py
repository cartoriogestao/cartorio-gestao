"""A FILA DE MERGE — um PR por vez, testado exatamente como vai entrar (10/11/2026).

Decisão do proprietário: todo PR aberto pela conta proprietária, pronto (não
rascunho), com a suíte e o anti-leak verdes **e atualizado com o main** entra
sozinho, em squash. O repositório é de conta pessoal e não tem a «merge queue»
do GitHub; esta é a versão dela que cabe aqui.

COMO ANDA (cada rodada faz no máximo UM passo e sai — a próxima rodada vem do
fim da suíte, do horário de 10 em 10 minutos, ou de um PR novo):

  1. PR elegível, verde e atualizado      → merge em squash (e repete o 1)
  2. alguma suíte ainda correndo          → espera
  3. o mais antigo elegível ainda não testado:
       atrás do main  → atualiza a branch e pede a suíte e o anti-leak
       sem resultado  → pede a suíte e o anti-leak
  PR com suíte vermelha ou com conflito fica parado até alguém mexer nele.

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


def elegivel(pr: Pr, dono: str) -> bool:
    return (not pr.rascunho and pr.autor == dono and pr.mesmo_repositorio
            and ROTULO_FORA_DA_FILA not in pr.rotulos)


def verde(pr: Pr) -> bool:
    return pr.suite == "success" and pr.anti_leak == "success"


def decidir(prs: list[Pr], dono: str) -> list[tuple]:
    """O próximo passo da fila. Só calcula — quem age é `executar`.

    Devolve uma lista de ações: ("mesclar", n), ("atualizar", n), ("disparar", n),
    ("marcar_conflito", n). Vazia: nada a fazer agora.
    """
    fila = sorted((p for p in prs if elegivel(p, dono)), key=lambda p: (p.criado_em, p.numero))
    for pr in fila:
        if verde(pr) and pr.estado_merge == "clean":
            return [("mesclar", pr.numero)]
    if any(p.suite == "pending" or p.anti_leak == "pending" for p in fila):
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
        corridas = self.pedir("GET", f"/commits/{pr.head}/check-runs?check_name={VERIFICACAO_ANTI_LEAK}")
        if corridas["check_runs"]:
            c = corridas["check_runs"][0]
            pr.anti_leak = "pending" if c["status"] != "completed" else (
                "success" if c["conclusion"] == "success" else "failure")

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


def executar(gh: GitHub, dono: str, *, ensaio: bool = False, limite_de_merges: int = 5) -> list[tuple]:
    feito: list[tuple] = []
    for _ in range(limite_de_merges + 1):
        prs = gh.prs()
        for pr in prs:
            if elegivel(pr, dono):
                gh.completar(pr)
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
