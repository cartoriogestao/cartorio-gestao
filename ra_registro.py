"""
Registro Auxiliar (Livro 3 do RI) — registrar, averbar, cancelar.

COMO SE USA
    with db.transaction() as con:
        r = registrar(con, natureza="CEDULA_CREDITO_RURAL",
                      titulo_tipo="Cédula Rural Pignoratícia e Hipotecária",
                      titulo_numero="40/01800-8", agora=agora,
                      valor="299809.50", parcelas=6, juros="9,00")
    audit(...)                      # FORA da transação, como no resto da casa

O NUMERO VEM DO CONTADOR DO RI, E NAO DO NUCLEO
    `ri_correcoes.proximo_numero(con, 3)` — o mesmo caminho da matrícula do
    Livro 2. O Livro 3 é série distinta e conta separado, mas pelo mesmo
    mecanismo. Duas fontes de verdade para o mesmo número é o defeito de
    18/08/2026; ver o cabeçalho de `ra_schema.py`.

    Como os registros do Livro 3 não moram em `ri_matriculas`, o contador em
    `ri_numeracao` é ATUALIZADO a cada registro — senão
    `maior_numero_da_serie` continuaria devolvendo o mesmo número, e o
    segundo registro nasceria com o número do primeiro.

O ATO E NUMERADO DENTRO DO REGISTRO
    R-1, AV-2, AV-3 — como a matrícula do RI faz, e por isso a numeração é
    contínua entre registro e averbação, não uma série para cada.

QUEM PRATICOU O ATO VAI NO ATO — LH13, 21/10/2026
    O oficial respondeu «15 a»: o Livro 3 como o Livro 2. Cada lavratura
    (`registrar`, `averbar`, `cancelar`) grava em `ra_atos.lavrado_*` o nome,
    a função e o artigo de quem está logado — a rota os pega de
    `quem_pratica_o_ato`, a mesma do Livro 2 —, e a ficha impressa fecha o ato
    com eles (CN-MA art. 458: «datado e subscrito»). Congelados: a função
    trocada amanhã não muda o ato de hoje. Quem não os passa (a carga do
    acervo) grava vazio, e o ato sai sem fecho — não se deduz quem foi.

O QUE NAO ENTRA AINDA
    Selo, custas, protocolo e ficha impressa — mesmo estágio das outras
    atribuições novas.

FUNDAMENTO
    Lei 6.015/1973, arts. 177 e 178.
"""
from __future__ import annotations

import sqlite3
from typing import Any

import ri_correcoes as RC
import ri_frases
from bd_nativo import banco
from caixa_schema import centavos
from ri_schema import gerar_cnm, LIVRO_REGISTRO_AUXILIAR

LIVRO = "3"


class RaError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


# O que a lei manda no Livro 3 (art. 178) e o que esta casa realmente
# registrou (medido em `LivroAuxiliar` e `tbRI_Auxiliar`: 1.273 linhas, na
# imensa maioria cédula de crédito rural).
NATUREZAS: dict[str, str] = {
    "HIPOTECA": "Hipoteca",
    "CEDULA_CREDITO_RURAL": "Cédula de crédito rural",
    "CEDULA_CREDITO_INDUSTRIAL": "Cédula de crédito industrial",
    "CEDULA_CREDITO_COMERCIAL": "Cédula de crédito comercial",
    "CEDULA_CREDITO_BANCARIO": "Cédula de crédito bancário",
    "CONVENCAO_CONDOMINIO": "Convenção de condomínio",
    "CONTRATO_PENHOR_RURAL": "Contrato de penhor rural",
    "CAUCAO_DIREITOS_HEREDITARIOS": "Caução de direitos hereditários",
    "CONTRATO_LOCACAO": "Contrato de locação com cláusula de vigência",
    "PACTO_ANTENUPCIAL": "Pacto antenupcial",
    "OUTRO": "Outro título do art. 178",
}

TIPOS_ATO = ("R", "AV")
SITUACOES = ("ATIVO", "CANCELADO")


# --------------------------------------------------------------- consultas


def registro(con: Any, registro_id: int) -> dict | None:
    """O registro do Livro 3, ou None. Só LÊ."""
    return banco(con).um(
        "SELECT * FROM ra_registros WHERE id = %s", (int(registro_id),))


def por_numero(con: Any, numero: Any) -> dict | None:
    """O registro de um número do Livro 3, ou None. Só LÊ."""
    return banco(con).um(
        "SELECT * FROM ra_registros WHERE livro = %s AND numero = %s "
        "ORDER BY id LIMIT 1",
        (LIVRO, int(numero)))


def atos_do(con: Any, registro_id: int) -> list[dict]:
    """Os atos do registro, na ordem. Só LÊ."""
    return banco(con).ler(
        "SELECT * FROM ra_atos WHERE registro_id = %s ORDER BY numero, id",
        (int(registro_id),))


def partes_do(con: Any, registro_id: int) -> list[dict]:
    """As partes do registro. Só LÊ."""
    return banco(con).ler(
        "SELECT * FROM ra_partes WHERE registro_id = %s ORDER BY id",
        (int(registro_id),))


def registro_por_origem(con: Any, origem: str,
                        origem_chave: str) -> dict | None:
    """O registro de uma chave de origem, ou None. Só LÊ."""
    return banco(con).um(
        "SELECT * FROM ra_registros WHERE origem = %s AND origem_chave = %s "
        "ORDER BY id LIMIT 1",
        (origem, origem_chave))


# ------------------------------------------------------------- a numeracao


def proximo_numero(con: Any) -> int:
    """O próximo número do Livro 3. Só LÊ.

    Olha as três fontes: o contador do RI, o maior número já gravado aqui, e
    o que `ri_correcoes` sabe da série. Nunca anda para trás — repetir
    número de registro é o defeito de 18/08/2026.
    """
    do_ri = RC.proximo_numero(con, LIVRO)
    n = banco(con).valor(
        "SELECT MAX(numero) AS n FROM ra_registros WHERE livro = %s",
        (LIVRO,))
    daqui = int(n or 0) + 1
    return max(do_ri, daqui)


def _consumir_numero(con: Any, numero: int, agora: str) -> None:
    """Anda o contador do RI. ESCREVE.

    Preciso porque os registros do Livro 3 não moram em `ri_matriculas`, de
    onde `ri_correcoes.maior_numero_da_serie` lê. Sem isto o contador ficaria
    parado e o segundo registro nasceria com o número do primeiro.
    """
    banco(con).escrever(
        """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso,
               fixado_em, observacao)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT(livro) DO UPDATE SET
             proximo_numero=GREATEST(excluded.proximo_numero,
                                     ri_numeracao.proximo_numero),
             maior_em_uso=GREATEST(excluded.maior_em_uso,
                                   COALESCE(ri_numeracao.maior_em_uso, 0)),
             fixado_em=excluded.fixado_em""",
        (LIVRO, numero + 1, numero, agora,
         "consumido pelo Registro Auxiliar"))


# -------------------------------------------------------------- registrar


def registrar(con: Any, *, natureza: str, agora: str,
              titulo_tipo: str | None = None,
              titulo_numero: str | None = None,
              data_titulo: str | None = None,
              valor: Any = None, parcelas: Any = None,
              vencimento_inicial: str | None = None,
              vencimento_final: str | None = None,
              juros: str | None = None, garantia: str | None = None,
              condicoes: str | None = None, teor: str | None = None,
              teor_formato: str = "texto", folha: str | None = None,
              partes: list[dict] | None = None,
              usuario: str | None = None, origem: str = "MANUAL",
              origem_chave: str | None = None,
              importacao_id: int | None = None,
              lavrado_nome: str | None = None,
              lavrado_titulo: str | None = None,
              lavrado_tratamento: str | None = None) -> dict:
    """Registra um título no Livro 3 e lavra o ato R-1. ESCREVE.

    Carga repetível por construção: a mesma (origem, origem_chave) devolve o
    id que já existe.
    """
    if natureza not in NATUREZAS:
        raise RaError(
            f"Natureza {natureza!r} não é do Livro 3. As que existem são: "
            f"{', '.join(NATUREZAS)}.")
    chave = (origem_chave or "").strip() or None
    if origem == "EOFICIO" and not chave:
        raise RaError(
            "Registro de origem EOFICIO precisa de uma chave de origem, para "
            "a carga poder ser repetida sem duplicar.")
    bd = banco(con)
    if chave:
        existente = registro_por_origem(bd, origem, chave)
        if existente:
            return {"registro_id": int(existente["id"]),
                   "numero": int(existente["numero"]), "reaproveitado": True}

    bd.travar("ra_registros.numero")
    numero = proximo_numero(con)
    # CNM do Registro Auxiliar (CNS + livro 3 + numero) — mesma regra do RI.
    # Banco sem `settings` (o de um teste de domínio, ou uma carga isolada)
    # registra sem CNM, em vez de derrubar o registro: o CNM se grava depois.
    cns = ""
    if bd.tem_tabela("settings"):
        cns = bd.valor(
            "SELECT value FROM settings WHERE key = %s", ("ri_cns",)) or ""
    cnm = gerar_cnm(cns, numero, LIVRO_REGISTRO_AUXILIAR) or None
    try:
        registro_id = int(bd.escrever(
            """INSERT INTO ra_registros(numero, livro, folha, natureza,
                   titulo_tipo, titulo_numero, data_titulo, valor_centavos,
                   parcelas, vencimento_inicial, vencimento_final, juros,
                   garantia, condicoes, teor, teor_formato, situacao, origem,
                   origem_chave, importacao_id, criado_em, criado_por, cnm)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (numero, LIVRO, folha, natureza, titulo_tipo, titulo_numero,
             data_titulo, centavos(valor) if valor is not None else None,
             int(parcelas) if parcelas else None, vencimento_inicial,
             vencimento_final, juros, garantia, condicoes, teor, teor_formato,
             "ATIVO", origem, chave, importacao_id, agora, usuario,
             cnm))[0]["id"])
    except sqlite3.IntegrityError as erro:
        raise RaError(
            f"O número {numero} do Livro 3 já está em uso. Nada foi "
            f"lançado. ({erro})") from erro
    _consumir_numero(bd, numero, agora)

    bd.escrever(
        """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato, teor,
               teor_formato, natureza, origem, criado_em, criado_por,
               lavrado_nome, lavrado_titulo, lavrado_tratamento)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (registro_id, "R", 1, agora, teor, teor_formato, natureza, origem,
         agora, usuario, lavrado_nome, lavrado_titulo, lavrado_tratamento))

    for parte in partes or []:
        bd.escrever(
            """INSERT INTO ra_partes(registro_id, nome, documento_tipo,
                   documento_numero, papel, origem)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (registro_id, parte.get("nome"), parte.get("documento_tipo"),
             parte.get("documento_numero"), parte.get("papel"), origem))

    return {"registro_id": registro_id, "numero": numero, "rotulo": "R-1",
           "reaproveitado": False}


# -------------------------------------------------------------- averbar


def _registro_preso(con: Any, registro_id: int) -> dict | None:
    """O registro, com a linha presa até o fim da transação. ESCREVE.

    Quem confere a situação e lança em seguida (averbar, cancelar) lê por
    aqui, e não por `registro`: sem a ponte, dois cancelamentos ao mesmo
    tempo passariam os dois pela conferência, porque a trava do número do ato
    vem depois dela. É o mesmo FOR UPDATE de `ra_correcoes.descancelar`.
    """
    bd = banco(con)
    bd._escrita()
    return bd.um("SELECT * FROM ra_registros WHERE id = %s FOR UPDATE",
                 (int(registro_id),))


def _proximo_ato(con: Any, registro_id: int) -> int:
    """O próximo número de ato do registro. Contínuo entre R e AV."""
    bd = banco(con)
    bd.travar(f"ra_atos.numero:{int(registro_id)}")
    n = bd.valor(
        "SELECT MAX(numero) AS n FROM ra_atos WHERE registro_id = %s",
        (int(registro_id),))
    return int(n or 0) + 1


def averbar(con: Any, registro_id: int, *, teor: str,
            agora: str, natureza: str | None = None,
            teor_formato: str = "texto", usuario: str | None = None,
            origem: str = "MANUAL", lavrado_nome: str | None = None,
            lavrado_titulo: str | None = None,
            lavrado_tratamento: str | None = None) -> dict:
    """Averba no registro do Livro 3. ESCREVE.

    A numeração do ato é contínua com o registro: depois do R-1 vem o AV-2.
    """
    bd = banco(con)
    reg = _registro_preso(bd, registro_id)
    if not reg:
        raise RaError(f"Registro {registro_id} do Livro 3 não encontrado.")
    if reg["situacao"] != "ATIVO":
        raise RaError(
            f"O registro está com situação {reg['situacao']} — só se averba "
            f"registro ativo.")
    razao = (teor or "").strip()
    if len(razao) < 10:
        raise RaError("O teor da averbação precisa de pelo menos dez letras.")
    if natureza is not None and natureza not in NATUREZAS:
        raise RaError(
            f"Natureza {natureza!r} não é do Livro 3. As que existem são: "
            f"{', '.join(NATUREZAS)}.")

    numero = _proximo_ato(bd, registro_id)
    ato_id = int(bd.escrever(
        """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato, teor,
               teor_formato, natureza, origem, criado_em, criado_por,
               lavrado_nome, lavrado_titulo, lavrado_tratamento)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (registro_id, "AV", numero, agora, razao, teor_formato, natureza,
         origem, agora, usuario, lavrado_nome, lavrado_titulo,
         lavrado_tratamento))[0]["id"])
    return {"registro_id": registro_id, "ato_id": ato_id,
           "numero": numero, "rotulo": f"AV-{numero}"}


# ---------------------------------------------------------- o cancelamento


def cancelar(con: Any, registro_id: int, *, motivo: str,
             agora: str, usuario: str | None = None,
             origem: str = "MANUAL", lavrado_nome: str | None = None,
             lavrado_titulo: str | None = None,
             lavrado_tratamento: str | None = None) -> dict:
    """Cancela o registro do Livro 3, por averbação de cancelamento. ESCREVE.

    O cancelamento é uma averbação, e não um apagamento: o registro fica na
    ficha, com a averbação dizendo que foi cancelado e por quê.
    """
    bd = banco(con)
    reg = _registro_preso(bd, registro_id)
    if not reg:
        raise RaError(f"Registro {registro_id} do Livro 3 não encontrado.")
    if reg["situacao"] != "ATIVO":
        raise RaError(f"O registro já está com situação {reg['situacao']}.")
    razao = (motivo or "").strip()
    if len(razao) < 10:
        raise RaError(
            "Escreva o motivo do cancelamento com pelo menos dez letras.")

    numero = _proximo_ato(bd, registro_id)
    # O TEXTO SAIU DAQUI — LF06B: o teor da averbação é o papel
    # RI_LIVRO3_CANCELAMENTO, editável na tela de Modelos. Vai ao livro e lá
    # fica: editar o modelo muda só os cancelamentos novos.
    teor = ri_frases.frase("RI_LIVRO3_CANCELAMENTO", con, motivo=razao)
    ato_id = int(bd.escrever(
        """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato, teor,
               motivo_cancelamento, origem, criado_em, criado_por,
               lavrado_nome, lavrado_titulo, lavrado_tratamento)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (registro_id, "AV", numero, agora,
         teor, razao, origem, agora,
         usuario, lavrado_nome, lavrado_titulo, lavrado_tratamento))[0]["id"])
    bd.escrever("UPDATE ra_registros SET situacao='CANCELADO' WHERE id = %s",
                (registro_id,))
    # Indicadores (Livros 4 e 5): lancamento proprio de cancelamento,
    # alem da averbacao neste Livro 3 (pedido 18/09/2026).
    import ri_indicador_lancamentos as RILANC
    RILANC.registrar_cancelamento_livro3(
        con, registro=reg, averbacao_id=ato_id, averbacao_numero=numero,
        motivo=razao, usuario=usuario, agora=agora)
    return {"registro_id": registro_id, "ato_id": ato_id,
           "numero": numero, "rotulo": f"AV-{numero}", "motivo": razao}
