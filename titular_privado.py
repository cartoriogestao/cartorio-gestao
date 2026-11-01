"""O QUE É SÓ DO TITULAR — despesas, balanço e livro-caixa.

Ordem do oficial (31/10/2026): «usuários devem poder abastecer despesas, mas não ver os dados
de despesas. O balanço deve ser privado do usuário administrador».

QUEM É O TITULAR
    O ADMIN cujo nome completo é o de `serventia_titular`, a configuração que sai nos atos.
    Ser ADMIN não basta: a casa tem mais de uma conta de administrador. Se nenhum ADMIN tiver
    esse nome (instalação nova, nome escrito de outro jeito), vale todo ADMIN, porque trancar
    o oficial fora das próprias contas seria pior, e o menu continuaria igual.

O QUE ISTO NÃO FAZ
    É guarda de tela. Quem tem o banco ou muda `serventia_titular` passa por ela, e a mudança
    fica na auditoria. O que protege o dado fora da tela é a cifra do titular no backup.
"""
from __future__ import annotations

from functools import wraps

from flask import abort

import serventia as SERV
from bd_nativo import banco


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
