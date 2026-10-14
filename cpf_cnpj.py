# -*- coding: utf-8 -*-
"""CPF/CNPJ: digito verificador, formatacao e aviso de duplicidade.

Helper central do balcao. Quem cadastra pessoa (cartao, parte, indicador)
passa por aqui — um so lugar para a regra, e testes cobrindo o digito.
"""
from __future__ import annotations

from typing import Any


def so_digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def cpf_valido(valor: Any) -> bool:
    """True so quando o CPF tem 11 digitos e o digito verificador fecha."""
    n = so_digitos(valor)
    if len(n) != 11 or n == n[0] * 11:
        return False
    for corte in (9, 10):
        soma = sum(int(n[i]) * (corte + 1 - i) for i in range(corte))
        resto = (soma * 10) % 11 % 10
        if resto != int(n[corte]):
            return False
    return True


def cnpj_valido(valor: Any) -> bool:
    n = so_digitos(valor)
    if len(n) != 14 or n == n[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, corte in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(n[i]) * pesos[i] for i in range(corte))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != int(n[corte]):
            return False
    return True


def documento_valido(valor: Any) -> bool | None:
    """Confere CPF (11) ou CNPJ (14).

    None = vazio (ausencia nao e erro). False = numero que nao existe.
    """
    n = so_digitos(valor)
    if not n:
        return None
    if len(n) == 11:
        return cpf_valido(n)
    if len(n) == 14:
        return cnpj_valido(n)
    return False


def formatar_cpf(valor: Any) -> str:
    n = so_digitos(valor)
    if len(n) != 11:
        return str(valor or "")
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"


def formatar_cnpj(valor: Any) -> str:
    n = so_digitos(valor)
    if len(n) != 14:
        return str(valor or "")
    return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"


def formatar_documento(valor: Any) -> str:
    n = so_digitos(valor)
    if len(n) == 11:
        return formatar_cpf(n)
    if len(n) == 14:
        return formatar_cnpj(n)
    return str(valor or "")


def mensagem_documento_invalido(valor: Any) -> str:
    n = so_digitos(valor)
    if len(n) == 11:
        return (f"O CPF {formatar_cpf(n)} nao passa no digito verificador. "
                f"Confira os numeros — um digito trocado passa no tamanho "
                f"e nao na conta.")
    if len(n) == 14:
        return (f"O CNPJ {formatar_cnpj(n)} nao passa no digito verificador. "
                f"Confira os numeros.")
    return ("Informe um CPF (11 digitos) ou CNPJ (14 digitos) valido.")


def buscar_duplicatas_por_documento(con, tabela: str, coluna: str,
                                   documento: Any, *,
                                   excluir_id: Any = None,
                                   limite: int = 5) -> list[dict]:
    """Aviso de duplicidade: mesmo CPF/CNPJ ja cadastrado na tabela."""
    digitos = so_digitos(documento)
    if not digitos:
        return []
    sql = f"SELECT * FROM {tabela} WHERE {coluna} = ?"
    params: list[Any] = [digitos]
    if excluir_id is not None:
        sql += " AND id <> ?"
        params.append(int(excluir_id))
    sql += f" LIMIT {int(limite)}"
    try:
        con.row_factory = __import__("sqlite3").Row
    except Exception:
        pass
    return [dict(r) for r in con.execute(sql, params).fetchall()]
