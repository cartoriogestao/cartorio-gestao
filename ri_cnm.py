"""O Código Nacional de Matrícula — o CNM, medido e fechado.

O QUE ELE É
    O identificador nacional da matrícula, no padrão do CNJ/ONR. Ele mora em
    `ri_matriculas.cnm` desde a carga do acervo e **nunca foi gerado nem
    conferido** por este sistema: era item do backlog do balcão desde agosto.

A ESTRUTURA, MEDIDA NOS 1.656 CNM REAIS DESTA CASA

        000000 . 2 . 0000001 - 27
        ──┬───   ┬   ───┬───   ─┬
          │      │      │       └── dígito verificador, 2 posições
          │      │      └────────── número da matrícula, 7 posições
          │      └───────────────── o LIVRO (2 = Registro Geral, 3 = Auxiliar)
          └──────────────────────── o CNS da serventia, 6 posições

    E o sequencial **É** o número da matrícula: conferido em **1.656 de
    1.656**, sem uma exceção. O dígito do livro é o número do livro, e não a
    letra do volume — `2A`, `2S` e `2C` são todos `2`.

O VERIFICADOR SE EXPLICA, E É ISSO QUE MUDA TUDO
    **ISO 7064 MOD 97-10** — o mesmo algoritmo do IBAN:

        DV = 98 − (base × 100) mod 97

    Testado contra os **1.656** CNM reais: **1.656 certos, zero errados.**

    ISSO É O OPOSTO DA MATRÍCULA DE 32 DÍGITOS DO RCPN, e a diferença é o que
    autoriza gerar aqui e proíbe lá. Naquela, 243 amostras foram testadas
    contra módulo 11 em quatro conjuntos de pesos, duas convenções, dez
    mapeamentos, mais módulo 97 e Luhn — e o melhor acertou 46 de 243, que é
    nível de acaso. Por isso o RCPN **recebe** a matrícula e não a gera, e há
    teste que fica vermelho se alguém escrever uma função que a gere.

    Aqui não é palpite: é um algoritmo público que reproduz **todos** os
    números que esta casa já emitiu. Gerar é reproduzir o que já existe, e não
    inventar o que falta.

O QUE ISSO CONSERTA
    Medido em 28/08/2026: das 1.701 matrículas, **45 não têm CNM** — 43 vieram
    assim do E-Ofício e **2 foram lavradas por este sistema**, que nunca gerou
    nenhum. Toda matrícula nova nascia sem o seu código nacional.
"""
from __future__ import annotations

import re
from typing import Any

# O formato exato, medido: seis, um, sete e dois, com os separadores da casa.
FORMA = re.compile(r"^(\d{6})\.(\d)\.(\d{7})-(\d{2})$")

# O LIVRO EM UM DÍGITO. `2A`, `2S`, `2-C` são todos o Livro 2 — o volume é de
# papel, e o CNM identifica o LIVRO. Medido: o dígito é `2` nos 1.656.
LIVRO_DO_REGISTRO_GERAL = "2"
LIVRO_AUXILIAR = "3"


class CnmError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcão."""


def digito(base: str) -> str:
    """O verificador de duas posições — ISO 7064 MOD 97-10. Só calcula.

    A MESMA CONTA DO IBAN, e ela foi conferida contra os 1.656 CNM que esta
    casa emitiu: 1.656 certos, zero errados.
    """
    limpo = "".join(c for c in str(base or "") if c.isdigit())
    if not limpo:
        raise CnmError("Não dá para calcular o dígito de um código vazio.")
    return f"{98 - (int(limpo) * 100) % 97:02d}"


def numero_do_livro(livro: Any) -> str:
    """`2A`, `2-S`, `2` -> `2`. O CNM identifica o livro, não o volume.

    O VOLUME É DE PAPEL, e o dígito do CNM é do LIVRO — medido: as matrículas
    dos volumes `2A`, `2S`, `2C` e mais dezesseis outros levam todas o dígito
    `2`. Pôr a letra ali seria dizer ao país que há vinte livros de registro
    geral nesta serventia, quando há um.
    """
    texto = str(livro or "").strip()
    for c in texto:
        if c.isdigit():
            return c
    raise CnmError(
        f"Não achei o número do livro em {livro!r}. O CNM precisa dele — "
        f"2 para o Registro Geral, 3 para o Registro Auxiliar.")


def montar(cns: Any, livro: Any, numero: Any) -> str:
    """O CNM daquela matrícula. Só calcula.

    NÃO INVENTA NADA: o CNS é o da serventia, o livro é o livro, o sequencial é
    o próprio número da matrícula (conferido em 1.656 de 1.656) e o verificador
    é a conta pública que reproduz todos eles.
    """
    digitos_cns = "".join(c for c in str(cns or "") if c.isdigit())
    if len(digitos_cns) != 6:
        raise CnmError(
            f"O CNS da serventia precisa ter seis dígitos para montar o CNM, e "
            f"veio {cns!r}. Ele se informa em Administrativo → Configurações.")
    try:
        sequencial = int(str(numero).strip())
    except (TypeError, ValueError):
        raise CnmError(
            f"O CNM sai do número da matrícula, e {numero!r} não é um número. "
            f"Matrícula sem número não tem código nacional.") from None
    if not 0 < sequencial <= 9_999_999:
        raise CnmError(
            f"O número da matrícula não cabe nas sete posições do CNM: "
            f"{sequencial}.")
    lv = numero_do_livro(livro)
    base = f"{digitos_cns}{lv}{sequencial:07d}"
    return f"{digitos_cns}.{lv}.{sequencial:07d}-{digito(base)}"


def conferir(texto: Any) -> dict:
    """Lê um CNM e diz se ele fecha. Só calcula.

    RECUSA COM A FRASE PRONTA, e diz qual seria o certo: quem digitou um
    dígito trocado precisa saber qual é, e não que «o código é inválido».
    """
    limpo = str(texto or "").strip()
    achado = FORMA.match(limpo)
    if not achado:
        raise CnmError(
            f"{limpo!r} não tem a forma de um CNM. Ele é assim: "
            f"000000.2.0000001-27 — o CNS, o livro, o número da matrícula com "
            f"sete casas, e o dígito.")
    cns, livro, sequencial, dv = achado.groups()
    certo = digito(cns + livro + sequencial)
    if dv != certo:
        raise CnmError(
            f"O dígito do CNM {limpo} não fecha: deveria ser {certo}, e veio "
            f"{dv}. Confira o que foi digitado — um dígito trocado faz o "
            f"código apontar para outra matrícula.")
    return {"cns": cns, "livro": livro, "numero": int(sequencial),
            "digito": dv, "cnm": limpo}


def confere(texto: Any) -> bool:
    """Só diz se fecha, sem levantar — para a tela pintar de verde ou vermelho."""
    try:
        conferir(texto)
        return True
    except CnmError:
        return False
