"""
O AVISO DE INTIMACAO, a entrega e o edital.

O PASSO DO ROTEIRO DO OFICIAL que ele serve:

    - EMITIR AVISO INTIMACAO
    - gera intimacao, edital, arquivo edital no cenprot e impresso na parede.

E o terceiro item do meio-dia: "recebimento de remessa, confirmacao e emissao
do aviso". Os dois primeiros ja tem tela (`protesto_remessa.py`); este e o
terceiro.

O QUE A MEDICAO ENSINOU, e esta inteira em `AVISO_DE_INTIMACAO_MEDIDO.md`

    **O aviso nao e um por titulo.** Em `tbBoletoApto`, 1.618 avisos para 1.361
    titulos: **255 titulos tem mais de um**. Endereco que muda, entrega que nao
    deu certo, aviso que se refaz. Por isso ele e tabela com uma linha por
    emissao, e nao coluna do titulo.

    **Quem entrega e o proprio cartorio.** O cadastro tem dois — CARTORIO e
    CORREIROS — e os Correios estao DESLIGADOS: as 1.618 entregas sairam pela
    mao da casa. E por isso que `curTaxaEntrega` e `curTaxaAR` sao zero nas
    1.618.

    **O EDITAL E ROTINA, E NAO EXCECAO.** 1.092 dos 1.618 avisos foram
    publicados em edital, e **1.068 dos 1.139 controles de nao-entrega dizem
    "Ausente"** — 94%. O caminho comum da intimacao nesta casa e a tentativa
    que nao acha ninguem em casa, seguida de edital. Quem trata edital como
    excecao desenha a tela errada.

O QUE ESTE MODULO NAO FAZ, E POR QUE

    **Nao emite boleto.** O aviso desta casa era tambem o boleto — codigo de
    barras FEBRABAN de 44 posicoes, com banco `000`, porque a cedente e a
    propria serventia. Duas coisas dele nao se explicam: o verificador do nosso
    numero (busca exaustiva feita, nada bate) e a origem do fator de vencimento
    (bate com `dtmVenc` em 776 de 1.618). **Codigo de barras errado e boleto que
    o leitor aceita e o dinheiro cai no lugar errado** — nao se chuta.

    O que este modulo faz e o REGISTRO: quem foi intimado, quando, por quem, e
    se foi por edital. E o que a inspecao cobra, e e o que o sistema nao tinha.

    **Nao calcula prazo.** Decisao do oficial de 24/08/2026, e vale aqui como
    no resto do Protesto: o acervo nunca controlou data de intimacao, e contar
    o triduo e decisao juridica ainda nao tomada.

O AVISO E O INSTRUMENTO; A INTIMACAO E O ATO
    O ato continua em `pt_atos`, lavrado por `protesto.lancar_intimacao`. O
    aviso guarda o papel que circulou. Juntar os dois faria a tentativa que nao
    achou ninguem virar intimacao — e nao e: e justamente o contrario, e o que
    leva ao edital.
"""
from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

import protesto as PT
from protesto_certidao import formatar_documento

# OS MOTIVOS DE NAO-ENTREGA, do catalogo desta casa — `tbMotivoNEntrega`, 13
# linhas. As duas marcas sao do proprio cadastro e valem regra:
#
#   `edital`   — motivo que manda o aviso DIRETO para o edital. Sao dois:
#                mudou-se e numero errado. Faz sentido: nos dois o endereco
#                deixou de servir, e insistir nele e perder tempo.
#   `contador` — motivo que conta como TENTATIVA, e pede outra. Sao dois:
#                ausente e fechado. Nos dois a pessoa mora ali, so nao estava.
#
# A terceira coluna e o que a casa de fato usou, medido em 1.139 controles de
# nao-entrega. Ela ordena a lista da tela: motivo de um uso em mil nao pode
# ficar na frente do que responde por 94%.
MOTIVOS_NAO_ENTREGA: dict[int, dict] = {
    11: {"motivo": "Ausente", "edital": False, "contador": True, "usos": 1068},
    2: {"motivo": "Endereço não encontrado", "edital": False,
        "contador": False, "usos": 13},
    3: {"motivo": "Recusou-se a receber", "edital": False,
        "contador": False, "usos": 6},
    12: {"motivo": "Fechado", "edital": False, "contador": True, "usos": 4},
    4: {"motivo": "Falecido", "edital": False, "contador": False, "usos": 4},
    8: {"motivo": "Destinatário desconhecido", "edital": False,
        "contador": False, "usos": 1},
    1: {"motivo": "Mudou-se", "edital": True, "contador": False, "usos": 0},
    5: {"motivo": "Não é o número indicado", "edital": True,
        "contador": False, "usos": 0},
    9: {"motivo": "Endereço incompleto", "edital": False,
        "contador": False, "usos": 0},
    10: {"motivo": "Informação fornecida pelo porteiro/síndico",
         "edital": False, "contador": False, "usos": 0},
    13: {"motivo": "Não procurado", "edital": False, "contador": False,
         "usos": 0},
    14: {"motivo": "Fora do perímetro", "edital": False, "contador": False,
         "usos": 0},
}

# O motivo 7, "Não existe o número indicado", esta no cadastro com
# `bitAtivo = 0` e zero usos. Fica de fora da lista da tela — mas nao do
# catalogo, para aviso antigo que o traga continuar sendo lido.
MOTIVOS_INATIVOS: dict[int, dict] = {
    7: {"motivo": "Não existe o número indicado", "edital": False,
        "contador": False, "usos": 0},
}

TODOS_OS_MOTIVOS = {**MOTIVOS_NAO_ENTREGA, **MOTIVOS_INATIVOS}

# Quem entrega. `CORREIROS` esta no cadastro do E-Oficio com `bitAtivo = 0` e
# zero usos — a grafia com dois erres e a do cadastro, e nao se conserta o que
# se transcreve. Fica registrado; a lista da tela traz so o que a casa usa.
ENTREGADOR_DA_CASA = "CARTORIO"
ENTREGADORES = (ENTREGADOR_DA_CASA,)

# O CODIGO IBGE DO MUNICIPIO DA SERVENTIA vai em cada edital (era o que o
# E-Oficio gravava nas 1.086 linhas de `tbEdital`). Ate 11/10/2026 ele estava
# escrito aqui, com o municipio desta casa; agora sai da configuracao do IBGE
# que a casa ja tem — `ibge_uf` mais `ibge_municipio`, a mesma soma que
# `protesto_cenprot.identidade_da_casa` usa para a comarca (sanitizacao B2).


def cidade_ibge(con: sqlite3.Connection) -> str:
    """`ibge_uf` (2) + `ibge_municipio` (5) = o codigo de sete digitos.

    Sem a configuracao devolve vazio, e o edital sai assim mesmo: o codigo e
    informacao do registro, e nao condicao para publicar.
    """
    valores = {}
    try:
        for chave, valor in con.execute(
                "SELECT key, value FROM settings WHERE key IN "
                "('ibge_uf', 'ibge_municipio')"):
            valores[chave] = str(valor or "").strip()
    except sqlite3.OperationalError:
        return ""
    if not valores.get("ibge_uf") or not valores.get("ibge_municipio"):
        return ""
    return valores["ibge_uf"].zfill(2) + valores["ibge_municipio"].zfill(5)

SITUACOES = ("EMITIDO", "ENTREGUE", "NAO_ENTREGUE", "EDITAL", "CANCELADO")

# Situacoes do TITULO em que cabe emitir aviso. Apontado e o caso normal;
# intimado tambem, porque reemitir e rotina — 255 titulos do acervo tem mais
# de um aviso.
SITUACOES_QUE_ACEITAM_AVISO = ("APONTADO", "INTIMADO")


class AvisoError(ValueError):
    """Erro de regra do aviso, com a mensagem pronta para o balcao."""


def motivo_rotulo(codigo: Any) -> str:
    """O nome do motivo, ou o codigo cru quando ele nao esta no catalogo."""
    achado = TODOS_OS_MOTIVOS.get(_inteiro(codigo))
    return achado["motivo"] if achado else f"motivo {codigo}"


def motivos_para_escolher() -> list[dict]:
    """Os motivos ativos, na ordem em que a casa os usou. So calcula."""
    return [{"codigo": k, **v} for k, v in
            sorted(MOTIVOS_NAO_ENTREGA.items(),
                   key=lambda x: (-x[1]["usos"], x[1]["motivo"]))]


def vai_direto_para_edital(codigo: Any) -> bool:
    """Este motivo manda o aviso direto ao edital? So calcula."""
    achado = TODOS_OS_MOTIVOS.get(_inteiro(codigo))
    return bool(achado and achado["edital"])


def _inteiro(valor: Any) -> int:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return -1


# ---------------------------------------------------------- emitir o aviso


def proximo_numero(con: sqlite3.Connection, ano: int) -> int:
    """O proximo numero do exercicio. So LE — nao consome nada.

    GET nao abre transacao de escrita: a tela que mostra "o proximo sera o N"
    chama isto, e contador consumido num GET fica preso no `busy_timeout`
    enquanto outro balcao lavra. E a mesma forma de `protesto_certidao`.
    """
    linha = con.execute("SELECT MAX(numero) n FROM pt_avisos WHERE ano=?",
                        (int(ano),)).fetchone()
    return int(linha["n"] if linha and linha["n"] else 0) + 1


def _devedor(con: sqlite3.Connection, titulo_id: int) -> sqlite3.Row | None:
    return con.execute(
        """SELECT nome, documento_tipo, documento_numero, endereco, bairro,
                  cep, cidade, uf
             FROM pt_devedores WHERE titulo_id=? ORDER BY id LIMIT 1""",
        (int(titulo_id),)).fetchone()


def emitir(con: sqlite3.Connection, titulo_id: int, *, hoje: str, agora: str,
           usuario: str | None = None, endereco: dict | None = None) -> dict:
    """Emite o aviso de intimacao do titulo. ESCREVE.

    O ENDERECO CONGELA NO AVISO, e nao se le do cadastro depois. O papel foi
    para um lugar; se o cadastro mudar amanha, o que se tentou continua sendo
    o de hoje — e a segunda tentativa e outro aviso, com o endereco novo. E
    exatamente o que os 255 titulos com mais de um aviso mostram.

    `endereco` sobrepoe o do cadastro, para o caso de o balcao ter recebido um
    endereco melhor no guiche.
    """
    tit = PT.titulo(con, titulo_id)
    if not tit:
        raise AvisoError(f"Título {titulo_id} não encontrado.")
    if tit["situacao"] not in SITUACOES_QUE_ACEITAM_AVISO:
        raise AvisoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — só se emite aviso de título apontado. O "
            f"apontamento é o primeiro ato, e é ele que dá o protocolo que vai "
            f"no aviso.")

    dev = _devedor(con, titulo_id)
    if dev is None:
        raise AvisoError(
            f"O título {tit['numero_titulo']} está sem devedor cadastrado, e "
            f"o aviso é o papel que vai até ele. Confira a ficha do título.")
    fonte = {**dict(dev), **(endereco or {})}
    if not str(fonte.get("nome") or "").strip():
        raise AvisoError("O devedor está sem nome, e o aviso é endereçado a ele.")

    ano = int(str(hoje)[:4])
    numero = proximo_numero(con, ano)
    try:
        cur = con.execute(
            """INSERT INTO pt_avisos(titulo_id, numero, ano, devedor_nome,
                   devedor_documento, endereco, bairro, cep, cidade, uf,
                   situacao, emitido_em, emitido_por, criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,'EMITIDO',?,?,?)""",
            (int(titulo_id), numero, ano, fonte.get("nome"),
             fonte.get("documento_numero"), fonte.get("endereco"),
             fonte.get("bairro"), fonte.get("cep"), fonte.get("cidade"),
             fonte.get("uf"), agora, usuario, agora))
    except sqlite3.IntegrityError as erro:
        # A trava e `UNIQUE(numero, ano)`, e ela existe porque dois balcoes
        # podem emitir no mesmo segundo. Quem perde a corrida tenta de novo
        # com o numero seguinte — a mensagem diz isso em portugues, e nao em
        # tela branca.
        raise AvisoError(
            f"O número {numero}/{ano} acabou de ser usado por outro "
            f"atendimento. Emita de novo — o próximo número sai livre."
        ) from erro
    return {"aviso_id": int(cur.lastrowid), "numero": numero, "ano": ano,
            "titulo_id": int(titulo_id), "situacao": "EMITIDO",
            "devedor_nome": fonte.get("nome")}


# --------------------------------------------------------------- a entrega


def registrar_entrega(con: sqlite3.Connection, aviso_id: int, *,
                      entregue: bool, agora: str, quando: str | None = None,
                      entregador: str = ENTREGADOR_DA_CASA,
                      motivo: Any = None, recebido_por: str | None = None,
                      observacao: str | None = None,
                      usuario: str | None = None) -> dict:
    """Registra o que aconteceu com o aviso. ESCREVE.

    ENTREGA COM EXITO LAVRA A INTIMACAO PESSOAL. E o unico lugar em que os
    dois se juntam, e e o certo: o devedor recebeu o papel na mao, e isso e a
    intimacao pessoal do art. 14 da Lei 9.492/1997. Quem lavra e
    `protesto.lancar_intimacao` — a regra nao se repete aqui.

    ENTREGA SEM EXITO NAO LAVRA NADA. E tentativa, e o titulo continua
    apontado. O que ela produz e o caminho do edital.

    CADA TENTATIVA FICA GUARDADA, e a ultima nao apaga a anterior. Medido:
    39 dos 1.093 titulos com controle de entrega tiveram mais de uma tentativa
    — 3,6%, e sao os que mais importam, porque e o rastro delas que JUSTIFICA
    o edital. "Tentou-se duas vezes e nao havia ninguem" e o que a inspecao le;
    "entregue" sozinho nao conta essa historia.
    """
    aviso = ler(con, aviso_id)
    if not aviso:
        raise AvisoError(f"Aviso {aviso_id} não encontrado.")
    if aviso["situacao"] not in ("EMITIDO", "NAO_ENTREGUE"):
        raise AvisoError(
            f"O aviso {aviso['numero']}/{aviso['ano']} está "
            f"{aviso['situacao']} — a entrega já foi registrada.")

    if not entregue:
        codigo = _inteiro(motivo)
        if codigo not in TODOS_OS_MOTIVOS:
            raise AvisoError(
                f"Motivo de não-entrega desconhecido: {motivo!r}. Os do "
                f"catálogo desta casa são: " +
                "; ".join(f"{k} — {v['motivo']}"
                          for k, v in sorted(MOTIVOS_NAO_ENTREGA.items())) +
                ". Sem o motivo não se sabe se o caso vai a edital.")

    ato_id = None
    situacao = "ENTREGUE" if entregue else "NAO_ENTREGUE"
    if entregue:
        lavrado = PT.lancar_intimacao(
            con, int(aviso["titulo_id"]), modo="PESSOAL", agora=agora,
            usuario=usuario,
            comprovante=(f"Aviso {aviso['numero']}/{aviso['ano']}, entregue por "
                         f"{entregador}" +
                         (f", recebido por {recebido_por}" if recebido_por
                          else "")))
        ato_id = lavrado["ato_id"]

    con.execute(
        """INSERT INTO pt_tentativas(aviso_id, titulo_id, quando, entregador,
               entregue, motivo, recebido_por, observacao, criado_em,
               criado_por)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (int(aviso_id), int(aviso["titulo_id"]), (quando or agora), entregador,
         1 if entregue else 0, (None if entregue else _inteiro(motivo)),
         recebido_por, observacao, agora, usuario))

    # O AVISO GUARDA O DESFECHO; a tabela acima guarda o caminho ate ele. E a
    # mesma divisao do acervo: `tbBoletoApto.bitEntregue` ao lado de
    # `tbBoletoControleNEntrega`.
    con.execute(
        """UPDATE pt_avisos SET situacao=?, entregue=?, entrega_em=?,
               entregador=?, motivo=?, recebido_por=?, observacao=?, ato_id=?
            WHERE id=?""",
        (situacao, 1 if entregue else 0, (quando or agora), entregador,
         (None if entregue else _inteiro(motivo)), recebido_por, observacao,
         ato_id, int(aviso_id)))
    return {"aviso_id": int(aviso_id), "situacao": situacao, "ato_id": ato_id,
            "vai_para_edital": (not entregue),
            "tentativas": len(tentativas(con, aviso_id))}


# ----------------------------------------------------------------- o edital


def montar_teor_do_edital(*, aviso: sqlite3.Row | dict, titulo: sqlite3.Row,
                          sv: dict, hoje: str,
                          data_extenso: str | None = None) -> str:
    """O teor do edital. So calcula.

    O ACERVO NAO GUARDA O TEXTO — `tbEdital` tem a data, quem publicou e o
    numero de controle, e mais nada. Este texto e escrito do que a Lei
    9.492/1997 manda constar no edital (art. 15) e do que o proprio aviso ja
    tem; nao ha teor anterior desta casa para imitar.

    Por isso ele e CURTO e diz so o que se sabe: quem, qual titulo, quanto, e
    o que acontece se ninguem aparecer. Texto comprido inventado seria pior
    que texto curto medido.
    """
    casa = str(sv.get("unit_name") or "").strip()
    cidade = str(sv.get("ri_cidade") or "").strip()
    uf = str(sv.get("ri_uf") or "").strip()
    devedor = str(aviso["devedor_nome"] or "").strip()
    # O DOCUMENTO SAI PONTUADO, e nao cru. O edital vai na parede para a pessoa
    # se reconhecer nele; `04785512388` nao se le, `047.855.123-88` se le. A
    # funcao e a mesma da certidao — duas formas de pontuar CPF na mesma casa
    # seriam uma a mais.
    documento = formatar_documento(aviso["devedor_documento"])
    protocolo = str(titulo["protocolo"] or "").strip()
    valor = _reais(titulo["saldo_centavos"])
    quando = (data_extenso or "").strip() or str(hoje)
    linhas = [
        "EDITAL DE INTIMAÇÃO",
        "",
        (f"{casa}, na forma da lei, FAZ SABER a quem interessar possa que, "
         "tendo sido infrutífera a tentativa de intimação pessoal, fica pelo "
         "presente edital INTIMADO(A):"),
        "",
        f"{devedor}" + (f", inscrito(a) no CPF/CNPJ sob o nº {documento}"
                        if documento else ""),
        "",
        ("do apontamento para protesto do título abaixo, para que, no prazo "
         "legal, compareça a esta Serventia a fim de pagá-lo, ou, querendo, "
         "apresente as razões que tiver:"),
        "",
        f"Protocolo: {protocolo or 'A CONFERIR'}",
        f"Título: {titulo['numero_titulo'] or 'sem número'}"
        + (f" — espécie {titulo['especie']}" if titulo["especie"] else ""),
        f"Apresentante: {titulo['apresentante_nome'] or titulo['apresentante_codigo'] or '—'}",
        f"Credor: {titulo['cedente_nome'] or '—'}",
        f"Valor: R$ {valor}",
        "",
        ("Decorrido o prazo sem manifestação, o título será protestado na "
         "forma da Lei nº 9.492, de 10 de setembro de 1997."),
        "",
        # A DATA POR EXTENSO, como em todo papel que esta casa assina.
        # `2026-08-25` e formato de banco de dados, e nao de edital afixado.
        f"{cidade}/{uf}, {quando}." if cidade else f"{quando}.",
    ]
    return "\n".join(linhas)


def _reais(centavos: Any) -> str:
    try:
        v = int(centavos or 0)
    except (TypeError, ValueError):
        v = 0
    return f"{v // 100:,}".replace(",", ".") + f",{v % 100:02d}"


def hash_edital(numero: int, ano: int, teor: str, agora: str) -> str:
    """Impressao digital do que foi afixado."""
    return hashlib.sha256(
        f"{numero}|{ano}|{teor}|{agora}".encode()).hexdigest()


def proximo_numero_do_edital(con: sqlite3.Connection, ano: int) -> int:
    """O proximo numero de edital do exercicio. So LE."""
    linha = con.execute("SELECT MAX(numero) n FROM pt_editais WHERE ano=?",
                        (int(ano),)).fetchone()
    return int(linha["n"] if linha and linha["n"] else 0) + 1


def publicar_edital(con: sqlite3.Connection, aviso_id: int, *, sv: dict,
                    hoje: str, agora: str, data_extenso: str | None = None,
                    usuario: str | None = None) -> dict:
    """Publica o edital do aviso que nao foi entregue. ESCREVE.

    E ELE QUE LAVRA A INTIMACAO POR EDITAL — modo `EDITAL`, com o codigo do
    edital, que e `protesto.lancar_intimacao` quem grava. Antes disto, o
    codigo do edital era digitado a mao na ficha, e edital que so existe como
    texto num campo nao se confere depois.

    O TEOR CONGELA. Edital publicado nao se redige de novo: e o papel que
    substitui a intimacao pessoal, e se ele mudar depois ninguem sabe o que
    foi afixado.
    """
    aviso = ler(con, aviso_id)
    if not aviso:
        raise AvisoError(f"Aviso {aviso_id} não encontrado.")
    if aviso["situacao"] != "NAO_ENTREGUE":
        raise AvisoError(
            f"O aviso {aviso['numero']}/{aviso['ano']} está "
            f"{aviso['situacao']}. Só vai a edital o aviso que saiu e não foi "
            f"entregue — o edital substitui a intimação pessoal que não deu "
            f"certo, e não a que nem se tentou.")

    tit = PT.titulo(con, int(aviso["titulo_id"]))
    if not tit:
        raise AvisoError(f"Título {aviso['titulo_id']} não encontrado.")

    ano = int(str(hoje)[:4])
    numero = proximo_numero_do_edital(con, ano)
    teor = montar_teor_do_edital(aviso=aviso, titulo=tit, sv=sv, hoje=hoje,
                                 data_extenso=data_extenso)
    codigo = f"ED-{ano}-{numero:04d}"

    lavrado = PT.lancar_intimacao(
        con, int(aviso["titulo_id"]), modo="EDITAL", agora=agora,
        usuario=usuario, codigo_edital=codigo,
        comprovante=(f"Aviso {aviso['numero']}/{aviso['ano']} não entregue: "
                     f"{motivo_rotulo(aviso['motivo'])}"))
    try:
        cur = con.execute(
            """INSERT INTO pt_editais(numero, ano, aviso_id, titulo_id,
                   publicado_em, publicado_por, cidade_ibge, teor, hash_teor,
                   ato_id, criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (numero, ano, int(aviso_id), int(aviso["titulo_id"]), hoje,
             usuario, cidade_ibge(con), teor,
             hash_edital(numero, ano, teor, agora), lavrado["ato_id"], agora))
    except sqlite3.IntegrityError as erro:
        raise AvisoError(
            f"O edital {numero}/{ano} acabou de ser usado por outro "
            f"atendimento. Publique de novo — o próximo número sai livre."
        ) from erro
    edital_id = int(cur.lastrowid)
    con.execute("UPDATE pt_avisos SET situacao='EDITAL', edital_id=? WHERE id=?",
                (edital_id, int(aviso_id)))
    return {"edital_id": edital_id, "numero": numero, "ano": ano,
            "codigo": codigo, "teor": teor, "ato_id": lavrado["ato_id"],
            "aviso_id": int(aviso_id)}


# --------------------------------------------------------------- consultas


def ler(con: sqlite3.Connection, aviso_id: int) -> sqlite3.Row | None:
    """O aviso. So LE."""
    return con.execute("SELECT * FROM pt_avisos WHERE id=?",
                       (int(aviso_id),)).fetchone()


def tentativas(con: sqlite3.Connection, aviso_id: int) -> list[dict]:
    """As tentativas de entrega daquele aviso, na ordem. So LE.

    E o rastro que justifica o edital. Sem ele, "publicou-se edital" fica sem
    o "porque" — e o porque e o que a inspecao pergunta.
    """
    return [dict(r) for r in con.execute(
        """SELECT * FROM pt_tentativas WHERE aviso_id=? ORDER BY id""",
        (int(aviso_id),))]


def do_titulo(con: sqlite3.Connection, titulo_id: int) -> list[dict]:
    """Os avisos daquele titulo, do mais novo para o mais velho. So LE.

    LISTA, e nao um so: 255 titulos do acervo tem mais de um aviso.
    """
    return [dict(r) for r in con.execute(
        """SELECT a.*, e.numero edital_numero, e.publicado_em edital_em
             FROM pt_avisos a LEFT JOIN pt_editais e ON e.id = a.edital_id
            WHERE a.titulo_id=? ORDER BY a.id DESC""", (int(titulo_id),))]


def esperando_entrega(con: sqlite3.Connection, limite: int = 200) -> list[dict]:
    """Avisos que sairam e ainda nao tiveram desfecho. So LE."""
    return [dict(r) for r in con.execute(
        """SELECT a.*, t.numero_titulo, t.protocolo, t.saldo_centavos
             FROM pt_avisos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.situacao='EMITIDO' ORDER BY a.id LIMIT ?""",
        (int(limite),))]


def esperando_edital(con: sqlite3.Connection, limite: int = 200) -> list[dict]:
    """Avisos nao entregues que ainda nao foram a edital. So LE.

    E A LISTA QUE MAIS ENCHE nesta casa: 1.092 dos 1.618 avisos do acervo
    terminaram em edital, e 94% das nao-entregas sao "Ausente".
    """
    return [dict(r) for r in con.execute(
        """SELECT a.*, t.numero_titulo, t.protocolo, t.saldo_centavos
             FROM pt_avisos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.situacao='NAO_ENTREGUE' ORDER BY a.entrega_em, a.id
            LIMIT ?""", (int(limite),))]


def editais_do_dia(con: sqlite3.Connection, dia: str) -> list[dict]:
    """Os editais publicados naquele dia, para a folha da parede. So LE."""
    return [dict(r) for r in con.execute(
        """SELECT e.*, t.numero_titulo, t.protocolo
             FROM pt_editais e JOIN pt_titulos t ON t.id = e.titulo_id
            WHERE e.publicado_em = ? ORDER BY e.numero""", (str(dia)[:10],))]


def edital(con: sqlite3.Connection, edital_id: int) -> sqlite3.Row | None:
    """O edital, com o teor congelado. So LE."""
    return con.execute("SELECT * FROM pt_editais WHERE id=?",
                       (int(edital_id),)).fetchone()


def contagens(con: sqlite3.Connection) -> dict:
    """Quantos avisos em cada situacao. So LE — para o alto da tela."""
    achado = {r["situacao"]: r["n"] for r in con.execute(
        "SELECT situacao, COUNT(*) n FROM pt_avisos GROUP BY situacao")}
    return {s: int(achado.get(s, 0)) for s in SITUACOES}
