"""O guardião do cofre — o processo que guarda a chave do cofre SÓ EM MEMÓRIA.

    «o cofre abre com uma senha-mestra, digitada por mim quando o Windows liga»
    — o oficial, 24/10/2026

COMO FUNCIONA
    Iniciado no logon (`tools/automacao_guardiao.py`), ele abre um canal LOCAL
    — 127.0.0.1, porta escolhida pelo sistema — e grava ao lado do cofre um
    arquivo `guardiao.json` com a porta e um TOKEN DE SESSÃO aleatório, com
    permissão restrita (ACL no Windows, 600 no macOS). Só quem lê esse arquivo
    fala com ele. A cada logon o token muda.

    A senha chega de dois jeitos, e nenhum a grava: a janelinha local (tkinter)
    ou a tela `/automacao/cofre/desbloquear` (só ADMIN, só de 127.0.0.1), que a
    repassa por este canal. Dela sai a chave (KDF memory-hard), que fica numa
    variável deste processo — nunca em disco, log, banco ou relato.

    Cinco senhas erradas seguidas BLOQUEIAM as tentativas por 15 minutos.
    «Trancar agora» apaga a chave da memória. Cada leitura fica registrada em
    `leituras.log` (quando, quem, qual item, para qual processo) — sem o valor.

O QUE ELE RESPONDE
    estado · desbloquear · trancar · ler · gravar · remover — um pedido JSON
    por linha, assinado com o token. Pedido sem a assinatura certa é recusado.

    O TOKEN NÃO VIAJA (revisão de segurança de 26/10/2026, PR #11, M1). Antes
    de qualquer pedido, o guardião prova que tem o token devolvendo
    HMAC(token, «guardiao|desafio de quem pede»); quem pede só manda a ação
    depois de conferir essa prova, e a assina com HMAC(token, «cliente|desafio
    do guardião|corpo»). Um processo que ocupe a porta de um `guardiao.json`
    velho (guardião caído) não prova nada e não recebe nada — nem a
    senha-mestra, nem o segredo, nem o token.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import socketserver
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import automacao_cofre as C

TENTATIVAS_ANTES_DE_BLOQUEAR = 5
BLOQUEIO = timedelta(minutes=15)


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Guardiao:
    """A chave em memória e as regras de quem pode pedir o quê."""

    def __init__(self, caminho: Any = None, *, kdf_novo: dict | None = None, conta_extra: str = ""):
        self.caminho = Path(caminho) if caminho else C.caminho_do_cofre()
        self.kdf_novo = kdf_novo
        self.conta_extra = conta_extra
        self._chave: bytes | None = None
        self._lock = threading.Lock()
        self.desde = _agora()                # trancado desde a partida
        self.erradas = 0
        self.bloqueado_ate: datetime | None = None
        self.token = secrets.token_urlsafe(32)
        self.servidor: socketserver.ThreadingTCPServer | None = None

    # -------------------------------------------------- o estado
    @property
    def aberto(self) -> bool:
        return self._chave is not None

    def estado(self) -> dict:
        return {"aberto": self.aberto, "desde": self.desde, "existe": self.caminho.is_file(),
                "bloqueado_ate": self.bloqueado_ate.isoformat(timespec="seconds") if self.bloqueado_ate else None,
                "erradas": self.erradas}

    # -------------------------------------------------- abrir e trancar
    def desbloquear(self, senha: str, confirmacao: str | None = None) -> dict:
        with self._lock:
            if self.bloqueado_ate and datetime.now() < self.bloqueado_ate:
                raise C.CofreError(f"Senha errada {TENTATIVAS_ANTES_DE_BLOQUEAR} vezes: novas tentativas "
                                   f"só depois das {self.bloqueado_ate:%H:%M}.")
            if not self.caminho.is_file():
                if confirmacao is None or confirmacao != senha:
                    raise C.CofreError("O cofre ainda não existe: digite a nova senha-mestra duas vezes, iguais.")
                chave = C.criar(self.caminho, senha, kdf=self.kdf_novo, conta_extra=self.conta_extra)
            else:
                try:
                    chave = C.conferir_senha(self.caminho, senha)
                except C.SenhaErrada:
                    self.erradas += 1
                    if self.erradas >= TENTATIVAS_ANTES_DE_BLOQUEAR:
                        self.bloqueado_ate = datetime.now() + BLOQUEIO
                        self.erradas = 0
                    raise
            self._chave, self.erradas, self.bloqueado_ate, self.desde = chave, 0, None, _agora()
            return self.estado()

    def trancar(self) -> dict:
        with self._lock:
            self._chave = None
            self.desde = _agora()
            return self.estado()

    def _exigir_aberto(self) -> bytes:
        if self._chave is None:
            raise C.CofreTrancado("O cofre está trancado: a senha-mestra ainda não foi digitada "
                                  "desde que a máquina ligou.")
        return self._chave

    # -------------------------------------------------- os segredos
    def ler(self, nome: str, *, quem: str = "", processo: str = "") -> dict:
        campos = C.ler_com_chave(self.caminho, self._exigir_aberto(), nome)
        self._registrar_leitura(nome, quem, processo)
        return campos

    def gravar(self, nome: str, campos: dict, *, tipo: str, validade: Any = None, por: str) -> dict:
        chave = self._exigir_aberto()
        with self._lock:
            return C.gravar_com_chave(self.caminho, chave, nome, campos, tipo=tipo, validade=validade,
                                      por=por, conta_extra=self.conta_extra)

    def remover(self, nome: str, *, por: str) -> bool:
        chave = self._exigir_aberto()
        with self._lock:
            removido = C.remover_com_chave(self.caminho, chave, nome)
        if removido:
            self._registrar_leitura(nome, por, "REMOVIDO")
        return removido

    def _registrar_leitura(self, nome: str, quem: str, processo: str) -> None:
        linha = json.dumps({"quando": _agora(), "item": nome, "quem": quem or "?",
                            "processo": processo or "?"}, ensure_ascii=False)
        alvo = self.caminho.parent / C.NOME_DAS_LEITURAS
        try:
            with alvo.open("a", encoding="utf-8") as f:
                f.write(linha + "\n")
        except OSError:
            pass

    # -------------------------------------------------- o canal
    def prova(self, desafio: str) -> str:
        """A prova de que ESTE processo tem o token (o primeiro passo do canal)."""
        return C.prova_do_canal(self.token, C.PAPEL_DO_GUARDIAO, desafio)

    def atender(self, mensagem: dict, desafio: str) -> dict:
        """Um pedido do canal, assinado contra o desafio que este guardião mandou.
        Nunca devolve a senha nem a chave.

        Desde 26/10/2026 (revisão de segurança, PR #11, M1) o token não viaja:
        quem pede assina o pedido inteiro com HMAC(token, «cliente|desafio|corpo»),
        e o desafio é deste guardião e desta conexão — a assinatura não se
        reaproveita noutra.
        """
        if not isinstance(mensagem, dict) or not desafio:
            return {"ok": False, "tipo": "recusado", "erro": "Pedido sem a prova desta sessão."}
        corpo = str(mensagem.get("corpo") or "")
        esperada = C.prova_do_canal(self.token, C.PAPEL_DE_QUEM_PEDE, desafio, corpo)
        if not hmac.compare_digest(str(mensagem.get("prova") or ""), esperada):
            return {"ok": False, "tipo": "recusado", "erro": "Pedido sem a prova desta sessão."}
        try:
            pedido = json.loads(corpo)
        except ValueError:
            pedido = None
        if not isinstance(pedido, dict):
            return {"ok": False, "tipo": "erro", "erro": "Pedido ilegível."}
        return self._executar(pedido)

    def _executar(self, pedido: dict) -> dict:
        acao = pedido.get("acao")
        try:
            if acao == "estado":
                return {"ok": True, **self.estado()}
            if acao == "desbloquear":
                return {"ok": True, **self.desbloquear(str(pedido.get("senha") or ""), pedido.get("confirmacao"))}
            if acao == "trancar":
                return {"ok": True, **self.trancar()}
            if acao == "ler":
                return {"ok": True, "campos": self.ler(pedido.get("nome"), quem=pedido.get("quem") or "",
                                                       processo=pedido.get("processo") or "")}
            if acao == "gravar":
                return {"ok": True, "metadados": self.gravar(
                    pedido.get("nome"), pedido.get("campos") or {}, tipo=pedido.get("tipo"),
                    validade=pedido.get("validade"), por=pedido.get("por") or "")}
            if acao == "remover":
                return {"ok": True, "removido": self.remover(pedido.get("nome"), por=pedido.get("por") or "")}
        except C.CofreError as erro:
            return {"ok": False, "tipo": C.TIPO_DA_EXCECAO.get(type(erro), "erro"), "erro": str(erro)}
        return {"ok": False, "tipo": "erro", "erro": f"Ação desconhecida: {acao!r}."}

    def iniciar(self) -> int:
        """Abre o canal em 127.0.0.1 numa thread e grava o arquivo do canal. Devolve a porta."""
        guardiao = self

        class _Atendente(socketserver.StreamRequestHandler):
            timeout = C.PRAZO_DO_CANAL_S * 12          # quem conecta e não fala não prende a thread

            def _escrever(self, dados: dict) -> None:
                self.wfile.write((json.dumps(dados, ensure_ascii=False) + "\n").encode("utf-8"))

            def handle(self):
                # 1º passo: o desafio de quem pede, e a prova deste guardião.
                try:
                    ola = json.loads(self.rfile.readline(4096).decode("utf-8") or "{}")
                    desafio_de_la = str(ola.get("desafio") or "") if isinstance(ola, dict) else ""
                except (ValueError, OSError):
                    return
                if not 16 <= len(desafio_de_la) <= 128:
                    return
                desafio_daqui = secrets.token_hex(16)
                self._escrever({"prova": guardiao.prova(desafio_de_la), "desafio": desafio_daqui})
                # 2º passo: o pedido, assinado contra o desafio daqui.
                try:
                    mensagem = json.loads(self.rfile.readline(C.TETO_DA_LINHA_DO_CANAL).decode("utf-8") or "{}")
                except (ValueError, OSError):
                    mensagem = {}
                self._escrever(guardiao.atender(mensagem, desafio_daqui))

        socketserver.ThreadingTCPServer.allow_reuse_address = False
        self.servidor = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Atendente)
        self.servidor.daemon_threads = True
        porta = self.servidor.server_address[1]
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        C.gravar_restrito(C.caminho_do_canal(self.caminho),
                          json.dumps({"porta": porta, "token": self.token, "pid": os.getpid(),
                                      "iniciado_em": _agora()}), conta_extra=self.conta_extra)
        C.restringir(C.caminho_do_canal(self.caminho), conta_extra=self.conta_extra)
        return porta

    def parar(self) -> None:
        self.trancar()
        if self.servidor:
            self.servidor.shutdown()
            self.servidor.server_close()
        try:
            C.caminho_do_canal(self.caminho).unlink()
        except OSError:
            pass


# ------------------------------------------------------------------ a janela e a linha de comando


def _janela(g: Guardiao) -> None:
    """A janelinha local: senha (duas vezes, se o cofre ainda não existe) e «trancar agora».

    A senha digitada vai direto para `g.desbloquear` e a caixa é limpa em
    seguida; ela não é gravada em lugar nenhum.
    """
    import tkinter as tk
    raiz = tk.Tk()
    raiz.title("Cartório Gestão — cofre da automação")
    raiz.resizable(False, False)
    situacao = tk.StringVar()
    tk.Label(raiz, textvariable=situacao, width=60, anchor="w").grid(row=0, column=0, columnspan=3, padx=8, pady=6)
    tk.Label(raiz, text="Senha-mestra:").grid(row=1, column=0, sticky="e", padx=8)
    senha = tk.Entry(raiz, show="*", width=32)
    senha.grid(row=1, column=1, padx=4, pady=2)
    rotulo2 = tk.Label(raiz, text="Repita (cofre novo):")
    confirma = tk.Entry(raiz, show="*", width=32)
    recado = tk.StringVar()
    tk.Label(raiz, textvariable=recado, fg="#b42318", width=60, anchor="w").grid(row=3, column=0, columnspan=3, padx=8)

    def atualizar():
        e = g.estado()
        situacao.set(("ABERTO" if e["aberto"] else "TRANCADO") + f" desde {e['desde'][:16].replace('T', ' ')}")
        if not e["existe"]:
            rotulo2.grid(row=2, column=0, sticky="e", padx=8)
            confirma.grid(row=2, column=1, padx=4, pady=2)
        else:
            rotulo2.grid_remove()
            confirma.grid_remove()
        raiz.after(2000, atualizar)

    def abrir(_evento=None):
        try:
            g.desbloquear(senha.get(), confirma.get() if not g.caminho.is_file() else None)
            recado.set("")
        except C.CofreError as erro:
            recado.set(str(erro)[:120])
        finally:
            senha.delete(0, "end")
            confirma.delete(0, "end")

    tk.Button(raiz, text="Desbloquear", command=abrir).grid(row=1, column=2, padx=8)
    tk.Button(raiz, text="Trancar agora", command=g.trancar).grid(row=4, column=2, padx=8, pady=8)
    senha.bind("<Return>", abrir)
    atualizar()
    raiz.protocol("WM_DELETE_WINDOW", raiz.iconify)      # fechar a janela não derruba o guardião
    raiz.mainloop()


def main(argv: list[str] | None = None) -> int:
    """`tools/automacao_guardiao.py` — no logon. `--sem-janela`: só a tela local desbloqueia."""
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    g = Guardiao(conta_extra=os.environ.get("CG_COFRE_CONTA_EXTRA", ""))
    g.iniciar()
    try:
        if "--sem-janela" in argv:
            threading.Event().wait()
        else:
            try:
                _janela(g)
            except Exception:                      # noqa: BLE001 — sem tela (serviço, SSH): segue sem janela
                threading.Event().wait()
    finally:
        g.parar()
    return 0
