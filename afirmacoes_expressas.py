"""AS AFIRMAÇÕES EXPRESSAS — quando a escrevente insiste no que a regra diz que é erro.

ORDEM DO OFICIAL, 29/10/2026: *«trabalhamos com mao de obra muito propensa a
erros e precisamos revisar os processos para nao permitir que a mao de obra
erre. [...] se insistir em algo que eh erro, precisa afirmar expressamente e
deixar log.»*

O CONTRATO É UM SÓ, e quem trava escreve por ele — a rota, logo depois da
transação, porque `audit` abre a sua própria:

    audit("AFIRMACAO_EXPRESSA", entity_type, entity_id,
          {"regra": "...", "afirmacao": "...", "o_que_faltava": "..."})

`regra` é o nome curto da trava (o que se filtra na tela); `afirmacao` é o que
a pessoa escreveu ao insistir; `o_que_faltava` é o que a regra cobrava e não
estava lá. Uma linha só em `audit_logs`, e não tabela própria: a auditoria já
guarda quem, quando e de onde, e uma segunda tabela seria a segunda versão do
mesmo fato.

ESTE MÓDULO SÓ LÊ. Ele não decide o que é erro (quem decide é a trava de cada
módulo) nem apaga afirmação nenhuma: o que se afirmou fica, e é isso que o
oficial confere.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from typing import Any

from bd_nativo import banco

ACAO = "AFIRMACAO_EXPRESSA"

#: O contador do painel do roteiro conta a última semana.
DIAS_DO_CONTADOR = 7
#: A tela abre nos últimos trinta dias, e o filtro muda isso.
DIAS_DA_TELA = 30
#: O teto da tela. Passou dele, a tela diz — e não esconde que cortou.
LIMITE = 1000

SEM_REGRA = "(sem regra declarada)"

# ------------------------------------------------ a régua — UMA SÓ NA CASA
#
# INTEGRAÇÃO DO PROTESTO, 29/10/2026. Havia SEIS cópias desta régua, e elas
# já divergiam: `protesto_prova`, `cenprot_conferencia` e `config_de_cobranca`
# tiravam a frase de abertura da conta das 30 letras; `protesto_selo_previo`,
# o roteiro e a versão anterior DESTE arquivo a contavam — e a frase sozinha
# tem 33 letras, de modo que «Afirmo, sob minha responsabilidade, que.»
# passava como afirmação. `protesto_titulos_irmaos` tirava a frase pelas
# letras, e não pela grafia. Ficou a regra mais rígida das seis, aqui; as
# outras chamam esta.

#: O PISO DA AFIRMACAO: LETRAS, e nao caracteres — «.......» nao e afirmacao
#: de ninguem — e ALÉM da frase de abertura, que sozinha já passaria dele.
MINIMO_DE_LETRAS = 30
#: A frase que a tela mostra fixa, antes da caixa de texto. Vai inteira no que
#: se grava, e quem a digitar de novo não a vê repetida.
MODELO = "Afirmo, sob minha responsabilidade, que"
FRASE = MODELO

#: A afirmação é de PESSOA: conta de robô não afirma «sob minha
#: responsabilidade» (26/10/2026, «todo robô se identifica»).
ROBO_NAO_AFIRMA = ("Afirmação expressa é de pessoa: conta de robô não afirma "
                   "«sob minha responsabilidade». Lance este ato com o usuário "
                   "de quem conferiu.")


class AfirmacaoError(ValueError):
    """A afirmacao nao cumpre o contrato — a frase diz o que falta."""


class AfirmacoesSeparadasError(AfirmacaoError):
    """Mais de uma trava no mesmo ato, e as afirmações não vieram separadas.

    `travas` é a lista `[{trava, regra, o_que_faltava}]` das que pediram, para
    a tela desenhar um campo para cada uma.
    """

    def __init__(self, texto: str, *, travas: list[dict] | None = None):
        super().__init__(texto)
        self.travas = list(travas or [])


def letras(texto: Any) -> int:
    """Quantas letras o texto tem. Espaco, pontuacao e numero nao contam."""
    return sum(1 for ch in str(texto or "") if ch.isalpha())


def sem_a_frase(texto: Any) -> str:
    """O texto corrido, sem a frase de abertura se ela vier no começo. Só
    calcula.

    A FRASE SE RECONHECE PELAS LETRAS, e não pela grafia: «Afirmo sob minha
    responsabilidade que», sem as vírgulas, é a mesma frase — e, comparada
    pela grafia, as 33 letras dela contariam no piso.
    """
    corrido = " ".join(str(texto or "").split())
    alvo = [c.lower() for c in MODELO if c.isalpha()]
    achadas = 0
    corte = None
    for i, ch in enumerate(corrido):
        if not ch.isalpha():
            continue
        if ch.lower() != alvo[achadas]:
            return corrido
        achadas += 1
        if achadas == len(alvo):
            corte = i + 1
            break
    if corte is None:
        return corrido
    return corrido[corte:].lstrip(" ,:;-—–….")


def letras_alem_da_frase(texto: Any) -> int:
    """Quantas letras a afirmação tem além da frase de abertura."""
    return letras(sem_a_frase(texto))


def texto_valido(texto: Any) -> str | None:
    """O texto inteiro da afirmação, já com a frase de abertura — ou `None`
    se ele não tem as 30 letras além dela. Só calcula. Não confere a caixa
    nem quem afirma: isso é de `validar`."""
    corrido = sem_a_frase(texto)
    if letras(corrido) < MINIMO_DE_LETRAS:
        return None
    return f"{MODELO} {corrido}"


def validar(afirmo: Any, afirmacao: Any, *, por_que: str = "",
            robo: bool = False,
            erro: type[Exception] = AfirmacaoError) -> str:
    """O contrato comum: pessoa (não robô), a caixa «Afirmo» marcada E pelo
    menos 30 letras ALÉM da frase de abertura.

    Devolve o texto inteiro, com a frase, ou recusa com `erro` dizendo o que
    falta. Quem grava a auditoria é a rota, depois da transação (`audit`
    abre a sua).
    """
    abertura = (por_que + " ") if por_que else ""
    if robo:
        raise erro(abertura + ROBO_NAO_AFIRMA)
    texto = texto_valido(afirmacao) if afirmo else None
    if texto:
        return texto
    falta = []
    if not afirmo:
        falta.append("marque a caixa «Afirmo»")
    tem = letras_alem_da_frase(afirmacao)
    if tem < MINIMO_DE_LETRAS:
        falta.append(f"escreva a afirmação com pelo menos {MINIMO_DE_LETRAS} "
                     f"letras além de «{MODELO}» (vieram {tem})")
    raise erro(
        abertura + "Para seguir, " + " e ".join(falta)
        + f", começando por «{MODELO}…». Ela fica gravada com o seu nome.")


# ----------------------------------------- uma afirmação POR TRAVA no ato

def _chave_do_texto(texto: Any) -> str:
    """O que se compara para dizer que dois textos são o mesmo: as letras e
    os algarismos, sem a frase, sem caixa. Pontuação e espaço não fazem de
    um texto colado um texto novo."""
    return "".join(c.lower() for c in sem_a_frase(texto) if c.isalnum())


def uma_por_trava(vencidas: list[dict]) -> None:
    """Confere as travas vencidas NUM MESMO ATO. Só calcula; recusa com
    `AfirmacoesSeparadasError`.

    DECISÃO DO OFICIAL, 29/10/2026: cada erro é afirmado expressamente. Até
    a integração, uma caixa só (`afirmo` + `afirmacao`) vencia ao mesmo tempo
    a prova da intimação, o item do selo, o irmão e a CENPROT, e cada trava
    gravava a sua linha com o MESMO texto. Agora:

    - a caixa comum vale para UMA trava só. Quando mais de uma pede, cada
      uma tem o seu campo (`afirmo_<trava>` + `afirmacao_<trava>`) — e a
      recusa diz quais, para a tela desenhá-los;
    - o mesmo texto em duas travas é recusado, ainda que venha em dois campos.

    `vencidas`: `[{trava, regra, afirmacao, o_que_faltava, campo_comum}]` —
    só as que a afirmação de fato venceu.
    """
    vencidas = [v for v in vencidas if v]
    if len(vencidas) < 2:
        return
    pedidas = [{"trava": v.get("trava"), "regra": v.get("regra"),
                "o_que_faltava": v.get("o_que_faltava")} for v in vencidas]
    lista = "; ".join(f"{v.get('regra')} — {v.get('o_que_faltava')}"
                      for v in vencidas)
    if any(v.get("campo_comum") for v in vencidas):
        raise AfirmacoesSeparadasError(
            f"Nada foi lançado: {len(vencidas)} regras pedem afirmação "
            f"expressa neste ato, e cada uma pede a SUA ({lista}). Escreva uma "
            f"afirmação para cada regra, no campo dela — a mesma caixa não "
            f"vale para duas.", travas=pedidas)
    vistos: dict[str, str] = {}
    for v in vencidas:
        chave = _chave_do_texto(v.get("afirmacao"))
        if chave in vistos:
            raise AfirmacoesSeparadasError(
                f"Nada foi lançado: o mesmo texto foi escrito para duas regras "
                f"({vistos[chave]} e {v.get('regra')}). Cada erro se afirma "
                f"por si: diga, em cada campo, o que você conferiu NAQUELA "
                f"regra.", travas=pedidas)
        vistos[chave] = str(v.get("regra") or "")


def _detalhes(texto: Any) -> dict:
    """Os detalhes gravados. Linha fora do contrato não some: vira afirmação."""
    try:
        lido = json.loads(texto or "{}")
    except (TypeError, ValueError):
        return {"afirmacao": str(texto or "")}
    return lido if isinstance(lido, dict) else {"afirmacao": str(lido)}


def periodo_padrao(hoje: str) -> tuple[str, str]:
    """De trinta dias atrás até hoje, em AAAA-MM-DD."""
    fim = date.fromisoformat(str(hoje)[:10])
    return (fim - timedelta(days=DIAS_DA_TELA)).isoformat(), fim.isoformat()


def _data(texto: Any, padrao: str) -> str:
    """O dia do filtro, ou o padrão quando o que veio não é data."""
    try:
        return date.fromisoformat(str(texto or "").strip()[:10]).isoformat()
    except ValueError:
        return padrao


def listar(con: sqlite3.Connection, *, hoje: str, de: Any = None,
           ate: Any = None, regra: Any = None) -> dict:
    """As afirmações do período, da mais nova para a mais antiga. Só LÊ.

    O período é por TEXTO, como no resto da casa: `ts` guarda
    `2026-10-29T11:00:00`, e `ate + '~'` apanha o dia inteiro (`~` vem depois
    de todo dígito e do `T`). A regra se filtra depois de ler, em Python — ela
    mora dentro do JSON, e operador de JSON no SQL seria acoplamento ao banco.
    """
    padrao_de, padrao_ate = periodo_padrao(hoje)
    de, ate = _data(de, padrao_de), _data(ate, padrao_ate)
    if de > ate:
        de, ate = ate, de
    regra = str(regra or "").strip()
    saida = {"de": de, "ate": ate, "regra": regra, "linhas": [],
             "regras": [], "cortado": False, "total": 0}
    if not banco(con).tem_tabela("audit_logs"):
        saida["total"] = None
        return saida
    lidas = banco(con).ler(
        """SELECT id, ts, username_snapshot, entity_type, entity_id, details
             FROM audit_logs
            WHERE action = %s AND ts >= %s AND ts < %s
            ORDER BY id DESC LIMIT %s""", (ACAO, de, ate + "~", LIMITE + 1))
    saida["cortado"] = len(lidas) > LIMITE
    regras = set()
    for linha in lidas[:LIMITE]:
        d = _detalhes(linha["details"])
        nome = str(d.get("regra") or "").strip() or SEM_REGRA
        regras.add(nome)
        if regra and nome != regra:
            continue
        saida["linhas"].append({
            "id": linha["id"], "ts": str(linha["ts"] or ""),
            "quem": linha["username_snapshot"] or "sistema",
            "regra": nome,
            "entidade": linha["entity_type"] or "",
            "entidade_id": (linha["entity_id"]
                            if linha["entity_id"] is not None
                            else d.get("entidade", "")),
            "afirmacao": str(d.get("afirmacao") or ""),
            "o_que_faltava": str(d.get("o_que_faltava") or "")})
    saida["regras"] = sorted(regras)
    saida["total"] = len(saida["linhas"])
    return saida


def contar(con: sqlite3.Connection, *, hoje: str) -> int | None:
    """Quantas afirmações nos últimos sete dias. `None` sem a tabela."""
    if not banco(con).tem_tabela("audit_logs"):
        return None
    desde = (date.fromisoformat(str(hoje)[:10])
             - timedelta(days=DIAS_DO_CONTADOR)).isoformat()
    return int(banco(con).valor(
        "SELECT COUNT(*) FROM audit_logs WHERE action = %s AND ts >= %s",
        (ACAO, desde)) or 0)
