"""AS PARTES DO REGISTRO DO LIVRO 3 — e sem elas o selo não sai.

    «fui tentar selar o ato do 1243 e deu isso: O ato ficou SEM SELO: Os
     nomes das partes devem ser informados. nao tem campo para partes»
                                        — o oficial, 21/09/2026

**E A FRASE É DO APARELHO, e não deste sistema.** É o selador que recusa o
envelope sem `parteAto` — a mesma recusa que derrubou o selo da AV-05 da
matrícula 3.110 em 15/09, no Livro 2. **Eu havia escrito o contrário**, em
comentário, ao construir o selo do Livro 3 em 20/09: «a lista vazia não impede
o selo, e o envelope do Livro 2 já manda `parteAto: []`». Ele manda — e o
aparelho devolve erro. Medição vale mais que dedução, e esta veio do balcão.

**POR QUE NÃO HAVIA CAMPO, medido em 21/09/2026.** A tabela `ra_partes` existe
desde que o Livro 3 nasceu, com nome, documento e papel — e está **vazia nos
14 registros**: nenhuma tela jamais escreveu nela. É o defeito de costume desta
casa pelo avesso — não é função sem tela, é **tabela sem tela**.

**E A CARGA DO ACERVO NÃO RESOLVE O 1.243**, e isso também foi medido: o
`LivroAuxiliar` do E-Ofício tem 14 registros — 1315, 1332, 1409, 1468, 1531,
1549 a 1554, 1560, 1628 e 1636 — e **o 1.243 não está entre eles**. Ele entrou
pela importação dos documentos, em 14/09/2026. Para ele, as partes se digitam:
elas estão escritas no teor e no campo «condições», que a ficha passa a mostrar
ao lado do formulário justamente para não se digitar de cabeça.


OS PAPÉIS SÃO OS DA CASA, e não uma lista inventada

Medidos nas **25 partes** que o E-Ofício guardou no Livro 3
(`LivroAuxiliarPartes` cruzada com `tbQualificacaoPartes`):

| papel | quantas |
|---|---|
| Emitente/Creditado | **14** |
| CREDOR(A) | **9** |
| Proprietário(a) | **2** |

Os outros da lista abaixo **não aparecem nessas 25** e vêm do catálogo do
próprio E-Ofício (`tbQualificacaoPartes`) — avalista, anuente, devedor,
interveniente. Eles entram porque o teor do 1.243 nomeia «AVALISTAS/ANUENTES»
e porque catálogo da casa não é invenção; **os três medidos vêm primeiro**.
"""
from __future__ import annotations

from typing import Any

from bd_nativo import banco

# OS TRÊS MEDIDOS, na ordem de uso, e depois o resto do catálogo da casa.
PAPEIS: tuple[tuple[str, str], ...] = (
    ("EMITENTE", "Emitente/Creditado — 14 das 25 partes do acervo"),
    ("CREDOR", "Credor(a) — 9 das 25"),
    ("PROPRIETARIO", "Proprietário(a) — 2 das 25"),
    ("AVALISTA", "Avalista — do catálogo da casa; não aparece nas 25"),
    ("ANUENTE", "Anuente — do catálogo da casa; não aparece nas 25"),
    ("DEVEDOR", "Devedor(a) — do catálogo da casa; não aparece nas 25"),
    ("INTERVENIENTE", "Interveniente — do catálogo da casa; não aparece nas 25"),
    # 19/10/2026 — pedido do oficial («adicionar mais partes no ato»). O
    # registro 9.005 (cédula bancária) tem garantidor e cônjuge que outorga;
    # sem esses papéis, a tela antiga gravava o papel em texto livre.
    ("GARANTIDOR", "Garantidor(a) — garante a dívida sem ser o emitente"),
    ("OUTORGANTE", "Outorgante/Cônjuge anuente — consente no ato"),
)

NOMES_DOS_PAPEIS: dict[str, str] = {c: r.split(" — ")[0] for c, r in PAPEIS}

CPF, CNPJ = "CPF", "CNPJ"


class ParteError(ValueError):
    """Erro de regra, com frase pronta para o balcão — vira `flash(danger)`."""


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def so_digitos(valor: Any) -> str:
    """O documento sem máscara. **O selo quer só os dígitos.**"""
    return "".join(c for c in _texto(valor) if c.isdigit())


def tipo_do_documento(numero: Any) -> str | None:
    """CPF, CNPJ, ou `None` quando não dá para dizer.

    **Pelo TAMANHO, e não pelo que alguém escolheu numa caixa** — onze dígitos
    é CPF e catorze é CNPJ, e essa é a única leitura que o número sustenta.
    Documento de outro tamanho fica sem tipo, e não vira um palpite.
    """
    d = so_digitos(numero)
    if len(d) == 11:
        return CPF
    if len(d) == 14:
        return CNPJ
    return None


def listar(con: Any, registro_id: int) -> list[dict]:
    """As partes daquele registro, na ordem em que entraram. Só lê."""
    linhas = banco(con).ler(
        "SELECT * FROM ra_partes WHERE registro_id=%s ORDER BY id",
        (int(registro_id),))
    return [dict(x) for x in linhas]


def para_o_selo(con: Any, registro_id: int) -> list[dict]:
    """As partes na forma que o envelope do selo quer: `{nome, documento}`.

    **Sem documento também vai**, e isso é medido: a casa mandou `{nome}`
    sozinho em 46 dos 236 blocos de parte do Livro 2, e o montador do envelope
    só inclui `documento` quando ele existe. O que o aparelho recusa é a lista
    **vazia**.
    """
    return [{"nome": p["nome"], "documento": p["documento_numero"]}
            for p in listar(con, registro_id) if _texto(p["nome"])]


def acrescentar(con: Any, *, registro_id: int, nome: str,
                papel: str, documento: Any = None, ato_id=None,
                origem: str = "MANUAL") -> int:
    """Põe uma parte no registro. ESCREVE. Devolve o `id`."""
    nome = _texto(nome)
    if len(nome) < 3:
        raise ParteError(
            "Escreva o nome da parte — é ele que vai dentro do selo, e é por "
            "ele que a pesquisa nacional de bens acha a pessoa.")
    papel = _papel_valido(papel)
    bd = banco(con)
    if bd.um("SELECT 1 FROM ra_registros WHERE id=%s",
             (int(registro_id),)) is None:
        raise ParteError("Registro do Livro 3 não encontrado.")
    documento = so_digitos(documento)
    return int(bd.escrever(
        """INSERT INTO ra_partes(registro_id, ato_id, nome, documento_tipo,
                                 documento_numero, papel, origem)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(registro_id), ato_id, nome, tipo_do_documento(documento),
         documento or None, papel, origem))[0]["id"])


def _papel_valido(papel: Any, *, atual: Any = None) -> str:
    """O código do papel, ou `ParteError`.

    **O papel antigo, em texto livre, continua valendo enquanto não se
    mexe nele** — a tela de registro novo gravava o que se digitasse
    («Emitente principal / devedor:» no 9.005), e editar o nome de uma parte
    dessas não pode obrigar a trocar o papel junto.
    """
    bruto = _texto(papel)
    codigo = bruto.upper()
    if codigo in NOMES_DOS_PAPEIS:
        return codigo
    if atual is not None and bruto and bruto == _texto(atual):
        return bruto
    raise ParteError(
        f"Papel desconhecido: {bruto!r}. Os desta casa estão na caixa — "
        f"emitente, credor, proprietário, avalista, anuente, devedor, "
        f"interveniente, garantidor e outorgante.")


def partes_do_formulario(nomes: list, tipos: list, numeros: list,
                         papeis: list) -> list[dict]:
    """As linhas «+ Adicionar parte» do registro novo, já conferidas.

    Quantas vierem — **não há mais limite de duas**. Linha sem nome é linha
    em branco e não conta; linha com nome passa pela mesma regra de
    `acrescentar` (nome de 3 letras, papel do catálogo, documento só com os
    dígitos). Só lê; quem grava é `ra_registro.registrar`.
    """
    def em(lista: list, i: int) -> str:
        return _texto(lista[i]) if i < len(lista) else ""

    partes: list[dict] = []
    for i, nome in enumerate(nomes or []):
        nome = _texto(nome)
        if not nome:
            continue
        if len(nome) < 3:
            raise ParteError(f"Parte {i + 1}: escreva o nome inteiro.")
        try:
            papel = _papel_valido(em(papeis, i))
        except ParteError as erro:
            raise ParteError(f"Parte {i + 1} ({nome}): {erro}") from None
        documento = so_digitos(em(numeros, i))
        tipo = tipo_do_documento(documento) or (
            em(tipos, i).upper() if documento and em(tipos, i) else None)
        partes.append({"nome": nome, "documento_tipo": tipo,
                       "documento_numero": documento or None,
                       "papel": papel})
    return partes


def editar(con: Any, parte_id: int, *, nome: str, papel: str,
           documento: Any = None) -> dict:
    """Corrige uma parte do registro. ESCREVE. Devolve `{registro_id, antes,
    depois}` — o `antes` vai para a auditoria inteiro.

    **Não toca no teor nem no selo**: a parte é da ficha (`ra_partes`), e o
    ato selado continua como foi lavrado. A regra antiga — «tira e põe de
    novo» — continua valendo para quem preferir; esta é para o nome com uma
    letra trocada, sem perder a ordem das partes.

    **A LINHA FICA PRESA (`FOR UPDATE`) entre ler e gravar**: o papel antigo
    só vale se for o que está gravado, e o `antes` da auditoria tem de ser o
    que esta correção substituiu — duas correções ao mesmo tempo na mesma
    parte, sem a trava, deixariam a segunda auditando um `antes` que já não
    existia.
    """
    bd = banco(con)
    bd._escrita()
    linha = bd.um(
        """SELECT registro_id, nome, documento_tipo, documento_numero, papel
             FROM ra_partes WHERE id=%s FOR UPDATE""", (int(parte_id),))
    if not linha:
        raise ParteError("Parte não encontrada.")
    registro_id = int(linha["registro_id"])
    antes = {"nome": linha["nome"], "documento_tipo": linha["documento_tipo"],
             "documento_numero": linha["documento_numero"],
             "papel": linha["papel"]}
    nome = _texto(nome)
    if len(nome) < 3:
        raise ParteError("Escreva o nome da parte — é ele que vai dentro do "
                         "selo.")
    papel = _papel_valido(papel, atual=linha["papel"])
    documento = so_digitos(documento)
    depois = {"nome": nome, "documento_tipo": tipo_do_documento(documento),
              "documento_numero": documento or None, "papel": papel}
    bd.escrever(
        """UPDATE ra_partes SET nome=%s, documento_tipo=%s,
                  documento_numero=%s, papel=%s WHERE id=%s""",
        (depois["nome"], depois["documento_tipo"], depois["documento_numero"],
         depois["papel"], int(parte_id)))
    return {"registro_id": registro_id, "antes": antes, "depois": depois}


def remover(con: Any, parte_id: int) -> int:
    """Tira uma parte do registro. ESCREVE. Devolve o `registro_id`.

    **Parte se tira, e não se corrige por cima**: quem digitou o nome errado
    tira e põe de novo, e assim o que ficou gravado é sempre o que alguém
    escreveu inteiro — e não a metade de duas digitações.
    """
    bd = banco(con)
    linha = bd.um("SELECT registro_id FROM ra_partes WHERE id=%s",
                  (int(parte_id),))
    if not linha:
        raise ParteError("Parte não encontrada.")
    bd.escrever("DELETE FROM ra_partes WHERE id=%s", (int(parte_id),))
    return int(linha["registro_id"])
