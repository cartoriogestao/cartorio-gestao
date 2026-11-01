"""O QUE É SÓ DO TITULAR — despesas, balanço e livro-caixa.

Ordem do oficial (31/10/2026): «usuários devem poder abastecer despesas, mas não ver os dados
de despesas. O balanço deve ser privado do usuário administrador».

QUEM É O TITULAR
    O ADMIN cujo nome completo é o de `serventia_titular`, a configuração que sai nos atos.
    Ser ADMIN não basta: a casa tem mais de uma conta de administrador. Se nenhum ADMIN tiver
    esse nome (instalação nova, nome escrito de outro jeito), vale todo ADMIN, porque trancar
    o oficial fora das próprias contas seria pior, e o menu continuaria igual.

A SENHA DO OFICIAL (01/11/2026): «manter apenas no perfil, com possibilidade de cadastrar senha»
    Opcional. Cadastrada, o livro-caixa, o Livro Diário, o backup e o quadro do mês pedem a senha
    a mais, além do login, e ficam abertos por `MINUTOS_ABERTO` naquela sessão. Só o hash fica em
    `settings`; trocar ou tirar pede a senha atual. Esquecida, só se limpa direto no banco.

O QUE ISTO NÃO FAZ
    É guarda de tela. Quem tem o banco ou muda `serventia_titular` passa por ela, e a mudança
    fica na auditoria. O que protege o dado fora da tela é a cifra do titular no backup.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from functools import wraps

from flask import abort, flash, redirect, render_template, request, session, url_for

import seguranca_web as SEGWEB
import serventia as SERV
from bd_nativo import banco


CHAVE_DA_SENHA = "titular_senha_hash"
MINIMO_DA_SENHA = 8
MINUTOS_ABERTO = 30
TENTATIVAS = 5
MINUTOS_DE_ESPERA = 5
_erros: dict[str, tuple[int, float]] = {}


class SenhaDoTitularError(ValueError):
    """Impedimento de regra, com a frase pronta para a tela."""


def _hash(senha: str, sal: bytes) -> str:
    return hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=2 ** 14, r=8, p=1, dklen=32).hex()


def gerar_hash(senha: str) -> str:
    sal = os.urandom(16)
    return f"scrypt${sal.hex()}${_hash(senha, sal)}"


def confere_hash(guardado: str, senha: str) -> bool:
    try:
        _, sal, valor = str(guardado).split("$")
        return hmac.compare_digest(_hash(str(senha or ""), bytes.fromhex(sal)), valor)
    except ValueError:
        return False


def tem_senha(db) -> bool:
    return bool(db.get_setting(CHAVE_DA_SENHA, ""))


def esta_aberto(db) -> bool:
    """Sem senha cadastrada, nada a abrir. Com ela, vale o carimbo desta sessão."""
    guardado = db.get_setting(CHAVE_DA_SENHA, "")
    if not guardado:
        return True
    marca = session.get("titular_aberto") or ()
    return len(marca) == 2 and marca[0] == guardado[-16:] and float(marca[1]) > time.time()


def _abrir_a_sessao(db) -> None:
    session["titular_aberto"] = (db.get_setting(CHAVE_DA_SENHA, "")[-16:], time.time() + MINUTOS_ABERTO * 60)


def conferir_tentativa(db, quem: str, senha: str) -> None:
    """Confere a senha digitada, com espera depois de `TENTATIVAS` erros. Recusa com a frase."""
    erros, ate = _erros.get(quem, (0, 0.0))
    if erros >= TENTATIVAS and ate > time.time():
        raise SenhaDoTitularError(f"Muitas tentativas erradas. Espere {MINUTOS_DE_ESPERA} minutos.")
    if not confere_hash(db.get_setting(CHAVE_DA_SENHA, ""), senha):
        erros = 1 if ate and ate <= time.time() else erros + 1
        _erros[quem] = (erros, time.time() + MINUTOS_DE_ESPERA * 60)
        raise SenhaDoTitularError("Senha errada.")
    _erros.pop(quem, None)


def volta_segura(valor) -> str:
    """Só caminho desta casa: «//fora» e endereço completo levariam para outro site.

    A régua é a de `seguranca_web.destino_interno`, a do login: a conta daqui deixava
    passar caractere de controle («/<TAB>/fora» o navegador lê como «//fora»), e o
    CodeQL (alerta #294) não a dava por conferida."""
    return SEGWEB.destino_interno(valor, "/")


def _nome(valor) -> str:
    return " ".join(str(valor or "").split()).casefold()


def e_o_titular(db, nome_de_quem_pede: str, papel: str) -> bool:
    """Quem pede é o titular? Só LÊ."""
    if papel != "ADMIN":
        return False
    titular = _nome(SERV.dados(db.get_settings).get("serventia_titular"))
    with db.connect() as con:
        admins = {_nome(u["full_name"]) for u in banco(con).ler(
            "SELECT full_name FROM users WHERE role = 'ADMIN' AND active = 1")}
    if not titular or titular not in admins:
        return True
    return _nome(nome_de_quem_pede) == titular


def guarda(app, db):
    """O decorador das rotas do titular, e a pergunta que as telas fazem."""
    def pergunta() -> bool:
        return e_o_titular(db, app.extensions["usuario_nome"](), app.extensions["usuario_papel"]())

    def so_o_titular(rota):
        @wraps(rota)
        def embrulhada(*args, **kwargs):
            if not pergunta():
                abort(403)
            return rota(*args, **kwargs)
        return embrulhada

    return so_o_titular, pergunta


def com_senha(app, db):
    """O decorador do que, além de ser do titular, pede a senha dele quando há uma."""
    so_o_titular, _ = guarda(app, db)

    def exige(rota):
        @wraps(rota)
        @so_o_titular
        def embrulhada(*args, **kwargs):
            if not esta_aberto(db):
                volta = request.full_path.rstrip("?") if request.method == "GET" else "/"
                return redirect(url_for("titular_senha", volta=volta))
            return rota(*args, **kwargs)
        return embrulhada

    return exige


def registrar_rotas(app, db, login_required, roles_required, audit) -> None:
    so_o_titular, _ = guarda(app, db)

    @app.route("/administrativo/senha-do-oficial", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    @so_o_titular
    def titular_senha():
        volta = volta_segura(request.values.get("volta"))
        if request.method == "POST":
            f, quem = request.form, app.extensions["usuario_nome"]()
            acao = f.get("acao")
            try:
                if acao == "abrir":
                    conferir_tentativa(db, quem, f.get("senha") or "")
                    _abrir_a_sessao(db)
                    audit("TITULAR_SENHA_ABERTA", "settings", None, {})
                    return redirect(volta)
                if tem_senha(db):
                    conferir_tentativa(db, quem, f.get("atual") or "")
                if acao == "remover":
                    db.set_settings({CHAVE_DA_SENHA: ""})
                    session.pop("titular_aberto", None)
                    audit("TITULAR_SENHA_REMOVIDA", "settings", None, {})
                    flash("Senha removida.", "success")
                elif acao == "gravar":
                    nova = f.get("nova") or ""
                    if len(nova) < MINIMO_DA_SENHA:
                        raise SenhaDoTitularError(f"A senha precisa de ao menos {MINIMO_DA_SENHA} caracteres.")
                    if nova != (f.get("confirmacao") or ""):
                        raise SenhaDoTitularError("As duas senhas não são iguais.")
                    db.set_settings({CHAVE_DA_SENHA: gerar_hash(nova)})
                    _abrir_a_sessao(db)
                    audit("TITULAR_SENHA_GRAVADA", "settings", None, {})
                    flash("Senha gravada. Guarde-a: esquecida, só se limpa direto no banco.", "success")
                else:
                    abort(400)
            except SenhaDoTitularError as erro:
                audit("TITULAR_SENHA_RECUSADA", "settings", None, {"acao": str(acao)[:10]})
                flash(str(erro), "danger")
            return redirect(url_for("titular_senha", volta=volta))
        return render_template("titular_senha.html", tem=tem_senha(db), aberto=esta_aberto(db), volta=volta,
                               minimo=MINIMO_DA_SENHA, minutos=MINUTOS_ABERTO)
