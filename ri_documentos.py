"""Os documentos do protocolo, e o ato que precisa vê-los para ser lavrado.

O RELATO #25 DO OFICIAL:

    «protocolo geral e do RI precisa ter mais funções, como anexar documentos.
     protocolo precisa permitir anexar documentos e visualizar esses
     documentos. E o ato em que se vincula a esse determinado protocolo precisa
     poder visualizar os documentos anexos ao protocolo, **até para facilitar a
     lavratura do ato**»

A SEGUNDA FRASE É QUE MANDA NO DESENHO. Guardar arquivo no protocolo é a parte
fácil — a tabela `attachments` já existe e já serve expediente e tarefa, com 20
arquivos guardados. O que ele pediu é que o **título apresentado** esteja à
vista de quem está escrevendo a averbação, e não numa outra tela.

    Quem lavra tem o papel na mão e o teor em branco na frente. Ir a outra tela
    buscar a escritura é largar o que está escrevendo.

O QUE SE MEDIU EM 29/08/2026
    `attachments` é genérica (`entity_type` + `entity_id`) e está em uso:
    **20 arquivos**, todos de `EXPEDIENTE`. A prenotação do RI **não tinha
    anexo nenhum** — nem tabela própria, nem uso da genérica.

    E a ponte entre o ato e a prenotação já existe: `ri_protocolos.ato_id`,
    construída em 28/08/2026 quando se descobriu que ela estava vazia em 784
    de 784. É por ela que este módulo acha os documentos.

POR QUE DUAS PONTES, E NÃO UMA
    `ri_protocolos.ato_id` só existe nos atos lavrados **depois** de 28/08. Nos
    784 do acervo ela é nula, e o que liga o ato à prenotação é o texto de
    `ri_atos.prenotacao`. Usar só a primeira deixaria o acervo inteiro sem
    documento; usar só a segunda ignoraria a amarração boa que passou a existir.

    A ordem importa: **a ligação gravada vem primeiro**, e o texto é a reserva.
    O texto pode ter sido digitado errado; o `ato_id` foi gravado pelo sistema
    ao lavrar.
"""
from __future__ import annotations

from typing import Any

from bd_nativo import banco

# Os dois protocolos desta casa, e eles sao coisas diferentes:
#
#   `PROTOCOLO`    — o protocolo geral do balcao (`cx_protocolos`), que e o
#                    atendimento e o dinheiro;
#   `RI_PROTOCOLO` — a prenotacao (`ri_protocolos`), que e a PRIORIDADE do
#                    titulo (Lei 6.015/1973, art. 186).
#
# O documento que interessa a quem lavra e o do segundo: e o titulo
# apresentado. Mas o primeiro tambem recebe anexo, porque e por ele que o
# cliente entrega papel no balcao.
ENTIDADE_GERAL = "PROTOCOLO"
ENTIDADE_RI = "RI_PROTOCOLO"

ENTIDADES: dict[str, str] = {
    ENTIDADE_GERAL: "Protocolo do balcão",
    ENTIDADE_RI: "Prenotação do Registro de Imóveis",
}


class DocumentoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


def prenotacao_do_ato(con: Any, ato_id: int) -> dict | None:
    """A prenotacao de que aquele ato saiu, se der para saber. So LE.

    DUAS PONTES, NESTA ORDEM:

    1. `ri_protocolos.ato_id` — a amarracao que o sistema grava ao lavrar. Ela
       e a boa: foi escrita pela maquina, no momento do ato.
    2. `ri_atos.prenotacao` — o numero digitado no ato. E a reserva, e serve
       para os 784 atos do acervo, em que a primeira e nula.

    Invertida, a ordem daria a resposta errada no dia em que alguem digitasse
    um numero de prenotacao trocado num ato que ja tem amarracao boa.
    """
    bd = banco(con)
    p = bd.um("SELECT * FROM ri_protocolos WHERE ato_id = %s ORDER BY id",
              (int(ato_id),))
    if p:
        return dict(p) | {"ligacao": "gravada"}

    a = bd.um("SELECT prenotacao FROM ri_atos WHERE id = %s", (int(ato_id),))
    # SO OS DIGITOS, E COMPARADO COMO NUMERO. Medido em 29/08/2026:
    # `ri_protocolos.numero` e **INTEGER** (`10595`) e `ri_atos.prenotacao` e
    # **TEXT** (`'11534'`). A comparacao direta acha 8 dos 12 atos com
    # prenotacao escrita — e perde `'11.534'`, digitado com ponto de milhar.
    #
    # E `'0'` NAO E PRENOTACAO: aparece em 3 atos, e e o campo em branco que
    # alguem preencheu com zero. Tratado como numero, ele acharia o protocolo
    # zero se algum dia existisse um.
    #
    # A conversao e em Python, e nao no SQL: recorte de texto no banco tem teto
    # por modulo nesta casa, e modulo novo entra com zero.
    digitos = "".join(c for c in str((a["prenotacao"] if a else "") or "")
                      if c.isdigit()).lstrip("0")
    if not digitos:
        return None
    p = bd.um("SELECT * FROM ri_protocolos WHERE numero = %s ORDER BY id",
              (int(digitos),))
    # `ligacao: "pelo numero"` NAO E DETALHE DE PROGRAMA: a tela diz isso a
    # quem lavra, porque documento achado por um numero digitado merece um
    # segundo olhar antes de virar fundamento de registro.
    return dict(p) | {"ligacao": "pelo número"} if p else None


def documentos_para_lavrar(con: Any, ato_id: int) -> dict:
    """Os documentos da prenotacao daquele ato, para a tela de lavrar. So LE.

    Devolve `{prenotacao, documentos, ligacao}` — ou tudo vazio quando o ato
    nao veio de prenotacao nenhuma, que e o caso da maioria dos atos do
    acervo. **Tela que fala de prenotacao para ato que nao tem uma e ruido**, e
    ruido e o que faz ninguem ler o aviso que importa.
    """
    p = prenotacao_do_ato(con, ato_id)
    if not p:
        return {"prenotacao": None, "documentos": [], "ligacao": None}
    # OS DOCUMENTOS PARA QUALIFICACAO DO PROTOCOLO GERAL ligado a prenotacao —
    # relato #135, decisao do oficial em 15/10/2026. Ficam numa chave PROPRIA,
    # e nao misturados em `documentos`: estes sao o titulo apresentado na
    # prenotacao, aqueles o que o cliente entregou no balcao. A leitura e a de
    # `protocolo_documentos.da_prenotacao`, a mesma da tela de lavrar.
    import protocolo_documentos as PDOC
    return {"prenotacao": p, "ligacao": p.get("ligacao"),
            "documentos": documentos_de(con, ENTIDADE_RI, p["id"]),
            "do_protocolo_geral": PDOC.da_prenotacao(con, p["id"])["ativos"]}


def documentos_de(con: Any, entidade: str,
                  entidade_id: int) -> list[dict]:
    """Os anexos daquela entidade, do mais novo para o mais velho. So LE.

    Le a MESMA tabela `attachments` do expediente e da tarefa. Uma segunda
    tabela de anexo faria dois lugares para procurar o mesmo papel — e no dia
    em que alguem pedisse «todos os documentos deste cliente», seriam duas
    consultas que ninguem lembraria de somar.
    """
    if entidade not in ENTIDADES:
        raise DocumentoError(
            f"«{entidade}» não é um lugar onde eu saiba guardar documento. "
            f"São dois: {', '.join(ENTIDADES)}.")
    return banco(con).ler(
        """SELECT a.*, u.full_name enviado_por_nome
             FROM attachments a LEFT JOIN users u ON u.id = a.uploaded_by
            WHERE a.entity_type = %s AND a.entity_id = %s
            ORDER BY a.id DESC""", (entidade, int(entidade_id)))


def quantos_documentos(con: Any, entidade: str,
                       entidade_id: int) -> int:
    """Quantos anexos, para a tela dizer o numero sem carregar a lista."""
    return int(banco(con).valor(
        """SELECT COUNT(*) AS n FROM attachments
            WHERE entity_type = %s AND entity_id = %s""",
        (entidade, int(entidade_id))))


def e_imagem(nome) -> bool:
    """Se o navegador mostra o arquivo na propria tela.

    QUEM LAVRA PRECISA VER, E NAO BAIXAR. Um `.pdf` ou um `.jpg` do titulo
    aberto ao lado do teor poupa a ida a outra tela; um `.docx` nao abre no
    navegador e continua sendo botao de baixar. A lista de extensoes e curta de
    proposito — o que nao estiver nela vira link, que funciona sempre.
    """
    fim = str(nome or "").lower().rsplit(".", 1)
    return len(fim) == 2 and fim[1] in (
        "pdf", "png", "jpg", "jpeg", "gif", "webp", "bmp")
