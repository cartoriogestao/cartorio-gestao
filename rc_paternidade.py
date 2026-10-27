"""O termo de alegação de paternidade — e o negativo — no nascimento sem o pai.

    «No caso de recusa da declarante em fornecer o nome do suposto pai, o
     oficial deverá lavrar termo negativo de alegação de paternidade, que será
     arquivado em pasta própria na serventia» — Código de Normas da CGJ-MA,
     art. 247, § 7º (o § 2º trata do termo de alegação; o § 3º manda remetê-lo
     ao juiz em até 30 dias)

A REGRA, E DE ONDE ELA VEM
    A Lei nº 8.560/1992, art. 2º, é nacional: no registro de nascimento só com
    a maternidade estabelecida, o oficial remete ao juiz a certidão integral do
    registro e o nome, a profissão, a identidade e a residência do suposto pai,
    para a averiguação oficiosa. Os códigos de normas estaduais dão a forma — o
    termo de alegação, e o termo negativo quando a mãe não quer indicar.

A TRAVA VALE PARA TODOS — decisão do oficial em 23/10/2026
    Nascimento lavrado no balcão (origem MANUAL) com a mãe declarada e o pai
    declarado IGNORADO não se lavra sem um dos dois termos (ou, desde
    27/10/2026, sem a anotação de que a mãe não compareceu — abaixo). Eles são gerados e
    guardados NA MESMA TRANSAÇÃO do assento: ato sem termo não existe, e termo
    sem ato também não. Carga e acervo (outras origens) trazem o papel que já
    existe e não são alcançados.

A TERCEIRA SAÍDA: A MÃE NÃO COMPARECEU — decisão do oficial em 27/10/2026
    Os dois termos supõem a mãe no balcão: na alegação ela indica, no negativo
    ela se recusa. Quando quem declara é a avó, o hospital, o próprio
    registrado no registro tardio — mãe ausente ou falecida —, nenhum dos dois
    é verdadeiro, e escolher um deles faria o livro afirmar uma fala que a mãe
    não teve. `MAE_AUSENTE` registra o fato como ele é: a mãe não compareceu e
    a averiguação não foi iniciada, com o MOTIVO escrito por quem atende.
    Não há termo para assinar (o `.odt` não sai), não há remessa ao juiz (não
    há suposto pai a indicar) e não entra no painel do que falta remeter. A
    redação da anotação é sugestão para o oficial conferir.

O QUE ELE NÃO FAZ
    Não remete nada ao juiz — a remessa é do balcão, pelo PJe. O que o sistema
    guarda é QUANDO foi remetido e em que processo, e o termo de alegação sem
    remessa aparece no painel do que ficou pelo caminho até ser remetido. Não
    julga a alegação nem a investiga.
"""
from __future__ import annotations

import hashlib
from typing import Any

from bd_nativo import banco

ALEGACAO = "ALEGACAO"
NEGATIVO = "NEGATIVO"
MAE_AUSENTE = "MAE_AUSENTE"
TIPOS = {ALEGACAO: "Termo de alegação de paternidade",
         NEGATIVO: "Termo negativo de alegação de paternidade",
         MAE_AUSENTE: "Mãe não compareceu — averiguação não iniciada"}

#: Os tipos que têm PAPEL para a mãe e o oficial assinarem. O `MAE_AUSENTE`
#: é só a anotação do fato: a mãe não estava, e não há o que ela assine.
TIPOS_COM_TERMO = frozenset({ALEGACAO, NEGATIVO})

#: O motivo da ausência é texto curto, mas não pode ser um traço: é ele que
#: explica, anos depois, por que a averiguação não começou.
MOTIVO_MINIMO_LETRAS = 5
MOTIVO_MAXIMO_LETRAS = 300

#: Dias que a casa tem para remeter o termo de alegação ao juiz. O painel
#: avisa antes (`inacabados`), para a remessa não sair no último dia.
PRAZO_DA_REMESSA = 30

# A TABELA MORA EM `rc_schema.SCHEMA` (rc_termos_paternidade), com as outras do
# RCPN: duas declarações da mesma tabela divergiriam no primeiro conserto.


class PaternidadeError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


def _texto(v: Any) -> str:
    return "" if v is None else " ".join(str(v).split())


def nome_do_papel(pessoas: list | None, papel: str) -> str:
    """O nome da pessoa daquele papel, na lista que a tela mandou."""
    for p in pessoas or []:
        if _texto((p or {}).get("papel")).upper() == papel:
            return _texto((p or {}).get("nome"))
    return ""


def data_do_balcao(iso: Any) -> str:
    """«2026-10-20» → «20/10/2026»; o que não for data volta como veio."""
    t = _texto(iso)[:10]
    if len(t) == 10 and t[4] == "-" and t[7] == "-":
        return f"{t[8:10]}/{t[5:7]}/{t[:4]}"
    return t


def exige_termo(especie: Any, pessoas: list | None, origem: Any) -> bool:
    """Nascimento do balcão com a mãe declarada e o pai declarado ignorado."""
    from rc_assento import e_declarado_ausente
    if _texto(especie).upper() != "NASCIMENTO":
        return False
    if (_texto(origem) or "MANUAL").upper() != "MANUAL":
        return False
    mae, pai = nome_do_papel(pessoas, "MAE"), nome_do_papel(pessoas, "PAI")
    return bool(mae) and not e_declarado_ausente(mae) and e_declarado_ausente(pai)


def conferir(especie: Any, pessoas: list | None, origem: Any,
             paternidade: dict | None) -> dict | None:
    """O termo que este nascimento exige, conferido. SÓ CONFERE.

    Devolve o pedido limpo, ou None quando o nascimento não exige termo.
    Recusa quando exige e ele não veio, ou veio sem o que a lei pede.
    """
    p = {k: _texto(v) for k, v in (paternidade or {}).items()}
    # A tela manda `paternidade_tipo` (o nome do campo no formulário); quem
    # chama por script manda `tipo`. Os dois valem.
    tipo = (p.pop("paternidade_tipo", "") or p.get("tipo", "")).upper()
    if not exige_termo(especie, pessoas, origem):
        if tipo:
            raise PaternidadeError(
                "O termo de alegação de paternidade só se lavra no nascimento "
                "em que o pai foi declarado ignorado. Neste, o pai está "
                "declarado — desmarque o termo.")
        return None
    if tipo not in TIPOS:
        raise PaternidadeError(
            "Nascimento com o pai declarado ignorado: antes de lavrar, escolha "
            "o termo de alegação de paternidade (a mãe indica o suposto pai), "
            "o termo negativo (a mãe se recusa a indicar) ou, se a mãe não "
            "está no balcão, «a mãe não compareceu», com o motivo — Lei nº "
            "8.560/1992, art. 2º. O que se escolher é gravado junto com o "
            "assento.")
    if tipo == ALEGACAO and not p.get("suposto_pai_nome"):
        raise PaternidadeError(
            "O termo de alegação de paternidade precisa do nome do suposto pai. "
            "Se a mãe não quiser indicá-lo, o termo é o negativo.")
    if tipo != ALEGACAO:
        # Nem o negativo nem a mãe ausente guardam suposto pai: no primeiro a
        # mãe se recusou a indicar, no segundo ela não estava para indicar.
        for campo in ("suposto_pai_nome", "suposto_pai_profissao",
                      "suposto_pai_documento", "suposto_pai_residencia"):
            p.pop(campo, None)
    if tipo == MAE_AUSENTE:
        motivo = p.get("motivo_ausencia_mae", "")
        if len(motivo) < MOTIVO_MINIMO_LETRAS:
            raise PaternidadeError(
                "«A mãe não compareceu» precisa do motivo: diga por que a mãe "
                "não está no balcão — por exemplo, falecida, ausente, ou "
                "registro tardio pelo próprio registrado.")
        if len(motivo) > MOTIVO_MAXIMO_LETRAS:
            raise PaternidadeError(
                f"O motivo da ausência da mãe é texto curto: até "
                f"{MOTIVO_MAXIMO_LETRAS} letras.")
        # SE A MÃE É A DECLARANTE, ELA ESTÁ NO BALCÃO — e então a escolha é
        # entre a alegação e o negativo. Gravar «não compareceu» com ela na
        # frente seria o livro afirmando o contrário do que aconteceu.
        mae = nome_do_papel(pessoas, "MAE").upper()
        declarante = nome_do_papel(pessoas, "DECLARANTE")
        if mae and declarante and declarante.upper() == mae:
            raise PaternidadeError(
                "A declarante é a própria mãe — ela está no balcão. Escolha o "
                "termo de alegação (ela indica o suposto pai) ou o negativo "
                "(ela se recusa a indicar).")
        p["declarante"] = declarante
    else:
        p.pop("motivo_ausencia_mae", None)
    p["tipo"] = tipo
    return p


def _qualificacao(p: dict) -> str:
    partes = []
    if p.get("suposto_pai_profissao"):
        partes.append(f"profissão {p['suposto_pai_profissao']}")
    if p.get("suposto_pai_documento"):
        partes.append(f"documento de identidade {p['suposto_pai_documento']}")
    if p.get("suposto_pai_residencia"):
        partes.append(f"residente em {p['suposto_pai_residencia']}")
    return (", " + ", ".join(partes)) if partes else (
        ", sem que a declarante soubesse informar profissão, identidade ou "
        "residência")


def montar_teor(p: dict, *, registrado: str, mae: str, data_nascimento: str,
                livro: Any, folha: Any, numero: Any, data_extenso: str,
                sv: dict) -> str:
    """O texto do termo. A forma segue o pedido da lei, e não inventa fato."""
    registro = (f"cujo registro de nascimento foi lavrado nesta data no Livro A "
                f"n.º {livro}, folha {folha}, sob o n.º {numero}")
    nascido = (f"{registrado}, nascido(a) em "
               f"{data_do_balcao(data_nascimento) or 'data não informada'}")
    lugar = ", ".join(x for x in (_texto(sv.get("ri_cidade")),
                                  _texto(sv.get("ri_uf"))) if x)
    if p["tipo"] == MAE_AUSENTE:
        # NÃO É TERMO: não há quem assine, e por isso não termina com «assina
        # com o oficial». É a anotação do fato, com o motivo e quem declarou.
        # A REDAÇÃO É SUGESTÃO para o oficial conferir (Lei 8.560/1992, art. 2º).
        declarante = _texto(p.get("declarante"))
        return (
            f"MÃE NÃO COMPARECEU — AVERIGUAÇÃO NÃO INICIADA. Em {data_extenso}, "
            f"nesta serventia, no assento de {nascido}, {registro}, com o pai "
            f"declarado ignorado, a mãe, {mae or 'não identificada'}, não "
            f"compareceu a esta serventia. Motivo informado: "
            f"{_texto(p.get('motivo_ausencia_mae'))}."
            f"{f' Declarante: {declarante}.' if declarante else ''} Por isso "
            f"não se lavrou termo de alegação de paternidade nem termo "
            f"negativo, e a averiguação oficiosa da paternidade (Lei nº "
            f"8.560/1992, art. 2º) não foi iniciada.")
    if p["tipo"] == ALEGACAO:
        corpo = (
            f"TERMO DE ALEGAÇÃO DE PATERNIDADE. Em {data_extenso}, nesta "
            f"serventia, {mae}, mãe de {nascido}, {registro}, declarou que o pai "
            f"da criança é {p['suposto_pai_nome']}{_qualificacao(p)}. A "
            f"declarante foi informada de que este termo, com a certidão "
            f"integral do registro, será remetido ao juiz competente para a "
            f"averiguação oficiosa da paternidade (Lei nº 8.560/1992, art. 2º), "
            f"e de que a falsa declaração sujeita quem a faz às sanções da lei.")
    else:
        corpo = (
            f"TERMO NEGATIVO DE ALEGAÇÃO DE PATERNIDADE. Em {data_extenso}, "
            f"nesta serventia, {mae}, mãe de {nascido}, {registro}, informada da "
            f"faculdade de indicar o suposto pai para a averiguação oficiosa da "
            f"paternidade (Lei nº 8.560/1992, art. 2º), recusou-se a fazê-lo. "
            f"Este termo é arquivado em pasta própria da serventia.")
    return (f"{corpo} E, por ser verdade, assina com o oficial. "
            f"{lugar + ', ' if lugar else ''}{data_extenso}.")


def lavrar_termo(con: Any, assento_id: int, p: dict, *, teor: str,
                 registrado: str, mae: str, agora: str,
                 usuario: str | None = None) -> int:
    """Guarda o termo, amarrado ao assento. ESCREVE — na transação do assento."""
    bd = banco(con)
    impressao = hashlib.sha256(f"{assento_id}\n{teor}".encode("utf-8")).hexdigest()
    return int(bd.escrever(
        """INSERT INTO rc_termos_paternidade(
               assento_id, tipo, registrado_nome, mae_nome, suposto_pai_nome,
               suposto_pai_profissao, suposto_pai_documento,
               suposto_pai_residencia, motivo_ausencia_mae, teor, hash_teor,
               criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(assento_id), p["tipo"], registrado, mae,
         p.get("suposto_pai_nome") or None, p.get("suposto_pai_profissao") or None,
         p.get("suposto_pai_documento") or None,
         p.get("suposto_pai_residencia") or None,
         p.get("motivo_ausencia_mae") or None, teor, impressao, agora,
         usuario))[0]["id"])


def do_assento(con: Any, assento_id: int) -> dict | None:
    """O termo do assento, se houver. SÓ LÊ."""
    bd = banco(con)
    if not bd.tem_tabela("rc_termos_paternidade"):
        return None
    linha = bd.um("SELECT * FROM rc_termos_paternidade WHERE assento_id=%s",
                  (int(assento_id),))
    if not linha:
        return None
    d = dict(linha)
    d["nome_do_tipo"] = TIPOS.get(d["tipo"], d["tipo"])
    d["tem_termo"] = d["tipo"] in TIPOS_COM_TERMO
    d["anotacao"] = anotacao(d)
    return d


def anotacao(termo: dict | None) -> str:
    """A linha curta que a ficha mostra para o `MAE_AUSENTE`; vazia nos outros."""
    if not termo or termo.get("tipo") != MAE_AUSENTE:
        return ""
    motivo = _texto(termo.get("motivo_ausencia_mae")) or "motivo não informado"
    return f"mãe não compareceu — averiguação não iniciada: {motivo}"


def registrar_remessa(con: Any, assento_id: int, *, processo: str, data: str,
                      agora: str, usuario: str | None = None) -> dict:
    """Grava que o termo de alegação foi remetido ao juiz. ESCREVE.

    Só o de alegação se remete; o negativo fica arquivado na serventia. E a
    remessa não se regrava: o dia em que ela aconteceu é fato.
    """
    termo = do_assento(con, assento_id)
    if not termo:
        raise PaternidadeError("Este assento não tem termo de paternidade.")
    if termo["tipo"] == MAE_AUSENTE:
        raise PaternidadeError(
            "Neste assento a mãe não compareceu e a averiguação não foi "
            "iniciada: não há suposto pai indicado nem termo a remeter ao juiz.")
    if termo["tipo"] != ALEGACAO:
        raise PaternidadeError(
            "O termo negativo não se remete ao juiz: ele fica arquivado em "
            "pasta própria da serventia.")
    if termo.get("remetido_em"):
        raise PaternidadeError(
            f"O termo já foi remetido em {termo['remetido_em']} "
            f"(processo {termo.get('remessa_processo') or 'não informado'}).")
    processo, data = _texto(processo), _texto(data)[:10]
    if not processo:
        raise PaternidadeError("Informe o número do processo no PJe.")
    if len(data) != 10:
        raise PaternidadeError("Informe a data da remessa.")
    banco(con).escrever(
        """UPDATE rc_termos_paternidade
              SET remetido_em=%s, remessa_processo=%s, remetido_por=%s
            WHERE assento_id=%s""",
        (data, processo, usuario, int(assento_id)))
    return {"assento_id": int(assento_id), "remetido_em": data,
            "processo": processo, "registrado_em": agora}
