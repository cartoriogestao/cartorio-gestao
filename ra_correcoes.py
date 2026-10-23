"""AS CORREÇÕES DO REGISTRO DO LIVRO 3 — editar, descancelar e renumerar.

Itens 4, 5 e 7 da fila que o oficial mandou fazer: *«termine o desenvolvimento
do livro 3, falta várias coisas que temos no livro 2»* (21/09/2026).

**O QUE ELAS CONSERTAM É O CADASTRO, E NÃO O ATO.** Ato errado se desfaz por
averbação, ou volta para a minuta (`ra_minuta.voltar_do_ato`) — não é aqui.
Aqui se conserta o que o registro **diz de si mesmo**: o número do título, a
data, o valor, a garantia, as condições e o teor.

**POR QUE ELAS FALTAVAM, e o caso é real.** O que a carga trouxe do acervo e o
que a importação dos documentos escreveu **não tinham por onde ser
corrigidos**: a ficha do registro 1.243 carrega, dentro do próprio campo de
condições, uma divergência de data que o importador **declarou e mandou
conferir contra o livro de papel** — «o cabeçalho traz DATA: 10.01.2010, mas o
corpo diz datada de 04 de janeiro de 2011». Até hoje não havia tela que
deixasse resolver isso.
"""
from __future__ import annotations

import sqlite3

from bd_nativo import banco
from typing import Any

ATIVO, CANCELADO = "ATIVO", "CANCELADO"

# O QUE SE PODE CORRIGIR, E É LISTA DECLARADA. Campo fora dela não entra: sem
# a lista, um nome de coluna vindo do formulário escreveria em `situacao` ou
# em `origem` — e o `UPDATE` sairia montado com o que o navegador mandou.
CAMPOS_EDITAVEIS: dict[str, str] = {
    "titulo_tipo": "Tipo do título",
    "titulo_numero": "Número do título",
    "data_titulo": "Data do título",
    "valor_centavos": "Valor",
    "vencimento_inicial": "Primeiro vencimento",
    "vencimento_final": "Vencimento final",
    "parcelas": "Parcelas",
    "juros": "Juros",
    "garantia": "Garantia",
    "condicoes": "Condições",
    "prenotacao": "Prenotação",
    "folha": "Folha",
    "teor": "Teor",
}

# O PISO DO MOTIVO — dez letras, o mesmo do descarte da minuta, da baixa da
# nota de revisão e da reabertura da matrícula no Livro 2.
MINIMO_DO_MOTIVO = 10


class CorrecaoError(ValueError):
    """Erro de regra, com frase pronta para o balcão — vira `flash(danger)`."""


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def editar(con: sqlite3.Connection, registro_id: int, *, campos: dict,
           agora: str, usuario=None) -> dict:
    """Corrige o cadastro do registro. ESCREVE. Devolve o que mudou.

    **DEVOLVE O ANTES E O DEPOIS**, e não só «pronto»: quem chama grava isso
    na auditoria, e é essa linha que responde, meses depois, o que foi
    corrigido e por quem. Correção sem rastro é correção que ninguém confere.

    **CAMPO QUE NÃO VEIO NÃO SE APAGA** — só entra no `UPDATE` o que o
    formulário mandou, e o que veio vazio vira `NULL` de propósito: apagar um
    campo é uma correção como outra qualquer, e às vezes é a correção certa.
    """
    bd = banco(con)
    # FOR UPDATE: o «antes» que vai para a auditoria sai desta leitura, e a
    # correção de outro balcão no meio faria a linha contar um antes que não
    # era mais o do livro.
    bd._escrita()
    linha = bd.um("SELECT * FROM ra_registros WHERE id=%s FOR UPDATE",
                  (int(registro_id),))
    if not linha:
        raise CorrecaoError("Registro do Livro 3 não encontrado.")
    antes = dict(linha)

    desconhecidos = [c for c in campos if c not in CAMPOS_EDITAVEIS]
    if desconhecidos:
        raise CorrecaoError(
            f"Campo que não se corrige por aqui: {', '.join(desconhecidos)}. "
            f"O número do registro, o livro, a situação e a origem não se "
            f"editam — eles dizem onde o ato está no livro.")
    mudou: dict[str, dict] = {}
    for campo, novo in campos.items():
        velho = antes.get(campo)
        novo = novo if novo not in ("", None) else None
        if _texto(velho) == _texto(novo):
            continue
        # O NOME DA COLUNA VEM DE `CAMPOS_EDITAVEIS`, e nunca do formulario
        # — e por isso a interpolacao aqui e segura: o que o navegador
        # manda ja foi recusado por `desconhecidos`, acima.
        bd.escrever(f"UPDATE ra_registros SET {campo}=%s WHERE id=%s",
                    (novo, int(registro_id)))
        mudou[campo] = {"antes": velho, "depois": novo}
    return mudou


def descancelar(con: sqlite3.Connection, registro_id: int, *, motivo: str,
                agora: str, usuario=None) -> None:
    """Devolve o registro a ATIVO, **com o motivo escrito**. ESCREVE.

    É o «reabrir» do Livro 2 aplicado a este livro: lá a matrícula se encerra,
    aqui o registro se cancela — e os dois se desfazem por engano do mesmo
    jeito, porque engano de quem atende existe em qualquer livro.

    **O QUE ELA NÃO FAZ: apagar a averbação que cancelou.** Aquela está no
    livro e fica; o que se desfaz é a marca da ficha. Quem precisa tirar o ato
    usa `ra_minuta.voltar_do_ato`, que tem as três recusas — e ele, sozinho,
    já devolve a ficha a ATIVO quando o ato que volta é o que a cancelou.
    """
    motivo = _texto(motivo)
    if len(motivo) < MINIMO_DO_MOTIVO:
        raise CorrecaoError(
            f"Escreva o motivo com pelo menos {MINIMO_DO_MOTIVO} letras — "
            f"descancelar um registro é decisão, e decisão sem motivo escrito "
            f"é decisão que ninguém confere depois.")
    bd = banco(con)
    # FOR UPDATE: dois descancelamentos ao mesmo tempo passariam os dois pela
    # conferência da situação, e a auditoria ficaria com dois motivos para
    # uma decisão só.
    bd._escrita()
    linha = bd.um("SELECT situacao FROM ra_registros WHERE id=%s FOR UPDATE",
                  (int(registro_id),))
    if not linha:
        raise CorrecaoError("Registro do Livro 3 não encontrado.")
    if _texto(linha["situacao"]).upper() != CANCELADO:
        raise CorrecaoError(
            "Este registro não está cancelado — não há o que descancelar.")
    bd.escrever("UPDATE ra_registros SET situacao=%s WHERE id=%s",
                (ATIVO, int(registro_id)))


def numeracao_dos_atos(con: sqlite3.Connection, registro_id: int) -> list[dict]:
    """Como os atos estão numerados hoje, e como ficariam. Só lê.

    A numeração do Livro 3 é **contínua com o registro** — depois do R-1 vem o
    AV-2 —, e a ordem certa é a de lavratura, que é a do `id`.
    """
    fora = []
    for posicao, a in enumerate(banco(con).ler(
            "SELECT id, tipo, numero, selo FROM ra_atos WHERE registro_id=%s "
            "ORDER BY id", (int(registro_id),)), start=1):
        fora.append({"id": a["id"], "tipo": a["tipo"], "numero": a["numero"],
                     "selo": a["selo"], "deveria_ser": posicao,
                     "fora_do_lugar": int(a["numero"]) != posicao})
    return fora


def renumerar(con: sqlite3.Connection, registro_id: int, *, agora: str,
              usuario=None) -> list[dict]:
    """Põe os atos do registro na numeração contínua. ESCREVE.

    **ATO COM SELO NÃO SE RENUMERA, e esta é a recusa que mais importa.** O
    selo do Livro 3 leva, no campo que o Tribunal chama de «matrícula», a
    frase `AV - 1 do Registro 1243` — renumerar o ato faria o selo já emitido
    **passar a dizer outra coisa** do que está no livro, e o selo não se
    reescreve.

    **E ELA NÃO INVENTA A ORDEM**: a ordem é a do `id`, que é a de lavratura.
    Se a ordem certa for outra, quem sabe disso é quem tem o livro de papel na
    mão — e aí o caminho é a averbação, e não o `UPDATE`.
    """
    # A MESMA TRAVA DA LAVRATURA (`ra_registro._proximo_ato`), e antes de ler:
    # um ato lavrado no meio ficaria fora da conta, com o número que a
    # lavratura lhe deu, e a numeração sairia furada do mesmo jeito.
    bd = banco(con)
    bd.travar(f"ra_atos.numero:{int(registro_id)}")
    atos = numeracao_dos_atos(bd, registro_id)
    fora = [a for a in atos if a["fora_do_lugar"]]
    if not fora:
        raise CorrecaoError(
            "A numeração deste registro já está contínua — não há o que "
            "renumerar.")
    com_selo = [a for a in fora if _texto(a["selo"])]
    if com_selo:
        quais = ", ".join(f"{a['tipo']}-{a['numero']}" for a in com_selo)
        raise CorrecaoError(
            f"Não dá para renumerar: {quais} já tem selo, e o selo carrega o "
            f"número do ato dentro dele. Renumerar faria o selo emitido dizer "
            f"outra coisa do que está no livro.")
    # A TROCA PASSA POR NÚMEROS NEGATIVOS porque `UNIQUE(registro_id, tipo,
    # numero)` bate no meio do caminho: trocar 2 e 3 direto esbarraria no 3
    # que ainda existe. O negativo é território que nenhum ato ocupa.
    for a in fora:
        bd.escrever("UPDATE ra_atos SET numero=%s WHERE id=%s",
                    (-a["id"], a["id"]))
    for a in fora:
        bd.escrever("UPDATE ra_atos SET numero=%s WHERE id=%s",
                    (a["deveria_ser"], a["id"]))
    return fora


def conferir(con: sqlite3.Connection, registro_id: int, *, conferido: bool,
             agora: str, usuario=None, nota: str = "") -> None:
    """Marca que alguém **leu a ficha contra o livro de papel**. ESCREVE.

    É o `ri_conferir_ficha` do Livro 2, e aqui ela vale mais: dos registros
    deste livro uns vieram da carga do acervo e outros da importação dos
    documentos, e **um deles carrega uma divergência que o próprio importador
    declarou** — o 1.243, cujo campo de condições diz que o cabeçalho traz
    2010 e o corpo, 2011, e manda conferir contra o papel.

    **A MARCA GUARDA QUEM E QUANDO**, e não só um `1`: a pergunta que a
    correição faz é «quem conferiu isto?», e um booleano não responde. A nota
    é opcional — quem achou divergência escreve o que achou.

    **E ELA SE DESMARCA.** Ficha conferida que depois se corrige volta a
    precisar de conferência, e travar isso obrigaria a mentir para consertar.
    """
    bd = banco(con)
    linha = bd.um("SELECT 1 AS um FROM ra_registros WHERE id=%s",
                  (int(registro_id),))
    if not linha:
        raise CorrecaoError("Registro do Livro 3 não encontrado.")
    if conferido:
        bd.escrever(
            """UPDATE ra_registros SET conferido=1, conferido_em=%s,
                   conferido_por=%s, conferido_nota=%s WHERE id=%s""",
            (agora, _texto(usuario) or None, _texto(nota) or None,
             int(registro_id)))
    else:
        # O CARIMBO ANTERIOR NÃO SE APAGA quando alguém desmarca: quem leu
        # naquele dia leu, e isso é fato do passado. O que muda é a marca.
        bd.escrever("UPDATE ra_registros SET conferido=0 WHERE id=%s",
                    (int(registro_id),))


def por_conferir(con: sqlite3.Connection) -> list[dict]:
    """Os registros que ninguém conferiu ainda. Só lê.

    **O acervo não vira atraso**: esta lista responde «o que falta ler contra
    o papel», e é dela que sai o número que a ficha mostra. Quem decide a
    ordem é quem tem o livro na mão.
    """
    return banco(con).ler(
        """SELECT id, numero, situacao, origem, conferido
             FROM ra_registros
            WHERE COALESCE(conferido, 0) = 0
            ORDER BY numero, id""")
