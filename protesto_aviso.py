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
from pathlib import Path
from typing import Any

import protesto as PT
import protesto_prova as PROVA
from bd_nativo import banco
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
        for linha in banco(con).ler(
                "SELECT key, value FROM settings WHERE key IN "
                "('ibge_uf', 'ibge_municipio') ORDER BY key"):
            valores[linha["key"]] = str(linha["value"] or "").strip()
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
    linha = banco(con).um("SELECT MAX(numero) AS n FROM pt_avisos WHERE ano=%s",
                          (int(ano),))
    return int(linha["n"] if linha and linha["n"] else 0) + 1


def _devedor(con: sqlite3.Connection, titulo_id: int) -> dict | None:
    return banco(con).um(
        """SELECT nome, documento_tipo, documento_numero, endereco, bairro,
                  cep, cidade, uf
             FROM pt_devedores WHERE titulo_id=%s ORDER BY id LIMIT 1""",
        (int(titulo_id),))


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
    bd = banco(con)
    tit = PT.titulo_para_gravar(bd, titulo_id)
    if not tit:
        raise AvisoError(f"Título {titulo_id} não encontrado.")
    if tit["situacao"] not in SITUACOES_QUE_ACEITAM_AVISO:
        raise AvisoError(
            f"O título {tit['numero_titulo']} está com situação "
            f"{tit['situacao']} — só se emite aviso de título apontado. O "
            f"apontamento é o primeiro ato, e é ele que dá o protocolo que vai "
            f"no aviso.")

    dev = _devedor(bd, titulo_id)
    if dev is None:
        raise AvisoError(
            f"O título {tit['numero_titulo']} está sem devedor cadastrado, e "
            f"o aviso é o papel que vai até ele. Confira a ficha do título.")
    fonte = {**dict(dev), **(endereco or {})}
    if not str(fonte.get("nome") or "").strip():
        raise AvisoError("O devedor está sem nome, e o aviso é endereçado a ele.")

    ano = int(str(hoje)[:4])
    bd.travar("pt_avisos.numero")
    numero = proximo_numero(bd, ano)
    try:
        aviso_id = int(bd.escrever(
            """INSERT INTO pt_avisos(titulo_id, numero, ano, devedor_nome,
                   devedor_documento, endereco, bairro, cep, cidade, uf,
                   situacao, emitido_em, emitido_por, criado_em)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'EMITIDO',%s,%s,%s)
               RETURNING id""",
            (int(titulo_id), numero, ano, fonte.get("nome"),
             fonte.get("documento_numero"), fonte.get("endereco"),
             fonte.get("bairro"), fonte.get("cep"), fonte.get("cidade"),
             fonte.get("uf"), agora, usuario, agora))[0]["id"])
    except sqlite3.IntegrityError as erro:
        # A trava e `UNIQUE(numero, ano)`, e ela existe porque dois balcoes
        # podem emitir no mesmo segundo. Quem perde a corrida tenta de novo
        # com o numero seguinte — a mensagem diz isso em portugues, e nao em
        # tela branca.
        raise AvisoError(
            f"O número {numero}/{ano} acabou de ser usado por outro "
            f"atendimento. Emita de novo — o próximo número sai livre."
        ) from erro
    return {"aviso_id": aviso_id, "numero": numero, "ano": ano,
            "titulo_id": int(titulo_id), "situacao": "EMITIDO",
            "devedor_nome": fonte.get("nome")}


# --------------------------------------------------------------- a entrega


def registrar_entrega(con: sqlite3.Connection, aviso_id: int, *,
                      entregue: bool, agora: str, quando: str | None = None,
                      entregador: str = ENTREGADOR_DA_CASA,
                      motivo: Any = None, recebido_por: str | None = None,
                      observacao: str | None = None,
                      usuario: str | None = None,
                      comprovante_nome: Any = None,
                      comprovante_conteudo: bytes | None = None,
                      pasta_de_arquivos: Any = None,
                      usuario_id: int | None = None,
                      afirmacao: str | None = None) -> dict:
    """Registra o que aconteceu com o aviso. ESCREVE.

    ENTREGA COM EXITO LAVRA A INTIMACAO PESSOAL. E o unico lugar em que os
    dois se juntam, e e o certo: o devedor recebeu o papel na mao, e isso e a
    intimacao pessoal do art. 14 da Lei 9.492/1997. Quem lavra e
    `protesto.lancar_intimacao` — a regra nao se repete aqui.

    A ENTREGA SÓ SE REGISTRA COM O COMPROVANTE E COM QUEM RECEBEU, NO MESMO
    ATO (ordem do oficial, 29/10/2026). Até aqui o comprovante podia vir
    depois, e em outubro quatro avisos foram dados por entregues e
    protestados minutos depois, com canhotos sem a assinatura de quem
    recebeu. Sem os dois, a entrega só se registra com a `afirmacao` expressa
    (regra `ENTREGA_SEM_COMPROVANTE`); o arquivo suspeito — o mesmo já
    anexado a outro aviso, ou com o protocolo de outro título no nome — também
    (`COMPROVANTE_DE_OUTRO_TITULO`/`_AVISO`). As afirmações voltam em
    `afirmacoes`, e a rota grava a auditoria fora da transação.

    O COMPROVANTE DEPOIS CONTINUA EXISTINDO PARA A TENTATIVA (o aviso NÃO
    entregue), de propósito: o canhoto com as tentativas anotadas volta ao
    cartório depois, e é ele que fundamenta o edital (`guardar_comprovante`).

    ENTREGA SEM EXITO NAO LAVRA NADA. E tentativa, e o titulo continua
    apontado. O que ela produz e o caminho do edital.

    CADA TENTATIVA FICA GUARDADA, e a ultima nao apaga a anterior. Medido:
    39 dos 1.093 titulos com controle de entrega tiveram mais de uma tentativa
    — 3,6%, e sao os que mais importam, porque e o rastro delas que JUSTIFICA
    o edital. "Tentou-se duas vezes e nao havia ninguem" e o que a inspecao le;
    "entregue" sozinho nao conta essa historia.
    """
    bd = banco(con)
    aviso = _aviso_para_gravar(bd, aviso_id)
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

    afirmacoes: list[dict] = []
    conferido = None
    if entregue:
        # A CONFERÊNCIA VEM ANTES DE QUALQUER GRAVAÇÃO: a intimação lavrada e
        # o comprovante recusado depois deixariam meia operação para trás.
        faltas_da_entrega = []
        if not str(recebido_por or "").strip():
            faltas_da_entrega.append(
                "falta o nome de quem recebeu o aviso — é quem assinou o "
                "canhoto")
        if not comprovante_conteudo:
            faltas_da_entrega.append(
                "falta o comprovante assinado — o canhoto do aviso, escaneado "
                "ou fotografado, anexado neste mesmo registro")
        faltas = ([(PROVA.REGRA_ENTREGA, "; ".join(faltas_da_entrega))]
                  if faltas_da_entrega else [])
        if comprovante_conteudo:
            if pasta_de_arquivos is None:
                raise AvisoError("O comprovante veio, e o sistema não sabe em "
                                 "que pasta guardá-lo. Avise o administrador.")
            conferido = _conferir_comprovante(bd, aviso, nome=comprovante_nome,
                                              conteudo=comprovante_conteudo)
            faltas += conferido["suspeitas"]
        afirmacoes = PROVA.vencer_todas(
            faltas, afirmacao, erro=AvisoError,
            abertura=(f"A entrega do aviso {aviso['numero']}/{aviso['ano']} "
                      f"não se registra assim"))

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

    bd.escrever(
        """INSERT INTO pt_tentativas(aviso_id, titulo_id, quando, entregador,
               entregue, motivo, recebido_por, observacao, criado_em,
               criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (int(aviso_id), int(aviso["titulo_id"]), (quando or agora), entregador,
         1 if entregue else 0, (None if entregue else _inteiro(motivo)),
         recebido_por, observacao, agora, usuario))

    # O AVISO GUARDA O DESFECHO; a tabela acima guarda o caminho ate ele. E a
    # mesma divisao do acervo: `tbBoletoApto.bitEntregue` ao lado de
    # `tbBoletoControleNEntrega`.
    bd.escrever(
        """UPDATE pt_avisos SET situacao=%s, entregue=%s, entrega_em=%s,
               entregador=%s, motivo=%s, recebido_por=%s, observacao=%s, ato_id=%s
            WHERE id=%s""",
        (situacao, 1 if entregue else 0, (quando or agora), entregador,
         (None if entregue else _inteiro(motivo)), recebido_por, observacao,
         ato_id, int(aviso_id)))
    anexo = None
    if conferido is not None:
        anexo = _gravar_comprovante(bd, {**dict(aviso), "situacao": situacao},
                                    conferido,
                                    pasta_de_arquivos=pasta_de_arquivos,
                                    agora=agora, usuario_id=usuario_id)
    return {"aviso_id": int(aviso_id), "situacao": situacao, "ato_id": ato_id,
            "vai_para_edital": (not entregue),
            "tentativas": len(tentativas(bd, aviso_id)),
            "anexo_id": (anexo or {}).get("anexo_id"),
            "afirmacoes": afirmacoes}


# ----------------------------------------------------------------- o edital


# ------------------------------------------------------- o papel do aviso
#
# O AVISO NÃO TINHA PAPEL — a tela dizia «imprima e mande entregar» e não havia
# o que imprimir (conferência de 14/10/2026). O conteúdo é o que o Código de
# Normas do TJMA (Prov. 28/2026) manda, lido no texto:
#
#   art. 920 — «o número do protocolo; o nome e o endereço do devedor, bem como
#   o número de seu documento de identificação; a espécie do título, por
#   extenso, seu número, valor e data de vencimento; a indicação da existência,
#   ou não, de aceite; o nome do sacador ou do favorecido e o do apresentante;
#   o prazo-limite para pagamento; e o endereço e horário de funcionamento do
#   tabelionato»;
#   art. 923 — mais os nomes do credor e do apresentante com CPF/CNPJ, e o
#   telefone do tabelionato;
#   art. 925, § 4º — «o prazo-limite para pagamento é o dia previsto para a
#   lavratura do protesto»: o terceiro dia útil depois da protocolização
#   (Lei 9.492/1997, art. 12; CN art. 913, I), a mesma conta que o gestor do
#   protesto já faz (`gestor_protesto.ART_12`).
#
# O HORÁRIO DE FUNCIONAMENTO NÃO EXISTE EM LUGAR NENHUM — nem em `settings`,
# nem no E-Ofício (`tbSetupBoleto.strHorarioAtendimento` vazio). Ele é
# configuração (`serventia_horario`), e sem ele o aviso RECUSA: papel oficial
# com um claro no lugar do horário é o que o artigo existe para impedir.

CHAVE_DO_HORARIO = "serventia_horario"

# O aceite que a remessa informa: «A» com, «N» sem. Como cada um se escreve no
# papel é a peça `PT_AVISO_ROTULOS` (LF06E); outro código é «não informado».
ACEITES = ("A", "N")


def prazo_limite(con: sqlite3.Connection, titulo: Any) -> str | None:
    """O dia previsto para a lavratura — 3 dias úteis da protocolização. Só LÊ.

    `None` quando o protocolo não diz a data: prazo inventado num papel que
    vai ao devedor é pior que a recusa.
    """
    from datetime import date as _date
    from ri_schema import soma_dias_uteis
    s = "".join(c for c in str(dict(titulo).get("protocolo") or "") if c.isdigit())
    if len(s) < 6:
        return None
    try:
        dia = _date(2000 + int(s[:2]), int(s[2:4]), int(s[4:6]))
    except ValueError:
        return None
    return soma_dias_uteis(dia, 3, _feriados(con)).isoformat()


def _feriados(con: Any) -> set:
    """Os feriados locais da casa (`ri_feriados_locais`). Só LÊ."""
    from ri_schema import ler_feriados_locais
    linha = banco(con).um("SELECT value FROM settings WHERE key='ri_feriados_locais'")
    return ler_feriados_locais((linha["value"] if linha else "") or "")


def dia_util_seguinte(con: Any, hoje: str) -> str:
    """O primeiro dia útil depois de `hoje`. Só LÊ.

    É O PRAZO-LIMITE DO EDITAL (27/10/2026): CN-MA art. 922, § 1º — o protesto
    só se lavra «do final do primeiro dia útil subsequente da publicação» — e
    § 3º, que manda o edital dizer esse prazo.
    """
    from datetime import date as _date
    from ri_schema import soma_dias_uteis
    return soma_dias_uteis(_date.fromisoformat(str(hoje)[:10]), 1,
                           _feriados(con)).isoformat()


def prazo_de_pagamento(con: Any, titulo: Any, depois_de: Any) -> str | None:
    """O prazo-limite que o papel imprime: o MAIOR entre o 3º dia útil da
    protocolização e o 1º dia útil depois de `depois_de`. Só LÊ.

    É a mesma conta do tríduo (`protesto_triduo.contar`): o prazo-limite é o
    dia previsto para a lavratura (CN-MA art. 925, § 4º), e quando a
    intimação chega no último dia do tríduo ou depois dele o protesto só se
    lavra no primeiro dia útil seguinte (art. 913, II e III, e art. 924; para
    o edital, art. 922, § 1º). Ordem do oficial em 27/10/2026: «prazo 1 dia
    útil depois da entrega». Sem a data da protocolização devolve `None`.
    """
    legal = prazo_limite(con, titulo)
    if not legal:
        return None
    if not str(depois_de or "").strip():
        return legal
    return max(legal, dia_util_seguinte(con, depois_de))


def _br(iso: Any) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) == 10 and s[4] == "-" else s


def montar_teor_do_aviso(con: sqlite3.Connection, aviso: Any, *,
                         sv: dict) -> str:
    """O texto do aviso de intimação, com os itens dos arts. 920 e 923. Só calcula.

    O endereço é o que CONGELOU no aviso, e não o do cadastro de hoje.
    """
    import protesto_pecas as PECAS
    av = dict(aviso)
    bd = banco(con)
    tit = PT.titulo(bd, int(av["titulo_id"]))
    if not tit:
        raise AvisoError("O título deste aviso não foi encontrado.")
    t = dict(tit)
    horario = bd.valor("SELECT value FROM settings WHERE key=%s",
                       (CHAVE_DO_HORARIO,)) or ""
    if not horario.strip():
        raise AvisoError(
            "O aviso precisa do horário de funcionamento do tabelionato "
            "(Código de Normas, art. 920), e ele não está configurado. "
            "Informe-o em Administrativo → Configurações "
            f"(«{CHAVE_DO_HORARIO}»).")
    # O AVISO EMITIDO TARDE NÃO IMPRIME PRAZO VENCIDO (27/10/2026, ordem do
    # oficial: «prazo 1 dia útil depois da entrega»). Na hora de imprimir a
    # entrega ainda não aconteceu; o dia mais cedo em que ela pode acontecer é
    # o da emissão, e é dele que se conta. Se a entrega vier depois, quem
    # segura o protesto é o tríduo, que conta da intimação lavrada.
    limite = prazo_de_pagamento(bd, t, av.get("emitido_em"))
    if not limite:
        raise AvisoError(
            f"O protocolo do título ({t.get('protocolo') or 'vazio'}) não diz a "
            f"data da protocolização, e sem ela não há prazo-limite — o aviso "
            f"não sai sem o prazo (Código de Normas, art. 920).")
    especie = PECAS.vocabulario(con, "PT_ESPECIES").get(
        str(t.get("especie") or "").upper(), t.get("especie") or "")
    # O TEXTO DO AVISO É O PAPEL `PT_AVISO_INTIMACAO` (LF06E, 19/10/2026), e os
    # rótulos dos dados são a peça `PT_AVISO_ROTULOS` — o oficial edita os dois
    # na tela de Modelos. Daqui saem os VALORES dos claros, a decisão de o
    # pedaço opcional entrar (o documento, o vencimento) e a juntura dele.
    rotulo = PECAS.vocabulario(con, "PT_AVISO_ROTULOS")

    def _r(nome: str, **claros: Any) -> str:
        return PECAS.preencher(rotulo[nome], "PT_AVISO_ROTULOS", AvisoError,
                               **claros)

    codigo_do_aceite = str(t.get("aceite") or "").upper()[:1]
    aceite = (rotulo[codigo_do_aceite] if codigo_do_aceite in ACEITES
              else _r("sem_aceite"))
    endereco = ", ".join(x for x in (av.get("endereco"), av.get("bairro"),
                                     av.get("cidade") and (
                                         f"{av['cidade']}/{av.get('uf') or ''}"),
                                     av.get("cep") and f"CEP {av['cep']}") if x)
    credor = (t.get("cedente_nome") or "").strip()
    if credor and t.get("cedente_documento"):
        credor += ", " + _r("documento", documento=formatar_documento(
            t["cedente_documento"]))
    # O APRESENTANTE «COM RESPECTIVOS CPF E/OU CNPJ» — CN-MA art. 923; CNN art.
    # 356, § 4º (LD08, 21/10/2026). O nome é o do título, e o documento vem do
    # título (balcão) ou do cadastro dos apresentantes, pelo código da CRA:
    # `protesto.apresentante_do_titulo`. Sem documento o claro vem vazio, como
    # o do devedor, e a linha diz só o nome.
    ap = PT.apresentante_do_titulo(bd, t)
    apresentante = ap["nome"]
    return _papel(con, "PT_AVISO_INTIMACAO",
                  numero=av["numero"], ano=av["ano"],
                  protocolo=t.get("protocolo"), prazo_limite=_br(limite),
                  devedor=av.get("devedor_nome") or "",
                  documento_do_devedor=(
                      ", " + _r("documento", documento=formatar_documento(
                          av["devedor_documento"]))
                      if av.get("devedor_documento") else ""),
                  endereco=endereco or _r("sem_endereco"),
                  especie=especie,
                  numero_titulo=t.get("numero_titulo") or _r("sem_numero"),
                  valor=_reais(t.get("saldo_centavos") or t.get("valor_centavos")),
                  vencimento=(" — " + _r("vencimento",
                                         data=_br(t["data_vencimento"]))
                              if t.get("data_vencimento") else ""),
                  aceite=aceite, credor=credor or _r("nao_informado"),
                  apresentante=apresentante or _r("nao_informado"),
                  documento_do_apresentante=(
                      ", " + _r("documento", documento=formatar_documento(
                          ap["documento"]))
                      if apresentante and ap["documento"] else ""),
                  serventia=str(sv.get("unit_name") or "").strip(),
                  endereco_da_serventia=sv.get("endereco_completo") or "",
                  telefone=(sv.get("serventia_telefone") or sv.get("telefone")
                            or ""),
                  horario=horario.strip())


def _papel(con: Any, chave: str, **claros: Any) -> str:
    """O papel (ou a peça) do aviso, com o ajuste da casa ou o padrão."""
    import protesto_pecas as PECAS
    return PECAS.montar(con, chave, AvisoError, **claros)


def montar_teor_do_edital(*, aviso: dict, titulo: dict,
                          sv: dict, hoje: str,
                          data_extenso: str | None = None,
                          limite: str | None = None, con: Any = None) -> str:
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
    # O TEXTO DO EDITAL É O PAPEL `PT_EDITAL_INTIMACAO` (LF06E, 19/10/2026),
    # que o oficial edita na tela de Modelos; ele CONGELA na publicação, e o
    # já publicado não muda. O EDITAL SE LIMITA AO QUE O CN-MA, art. 922, § 3º,
    # MANDA: devedor, identificação do título, valor, PRAZO-LIMITE e o
    # tabelionato com endereço e telefone. Até 14/10/2026 ele dizia «no prazo
    # legal» sem data e trazia apresentante e credor, que o parágrafo não pede.
    #
    # SEM PRAZO-LIMITE (protocolo que não diz a data), a linha que o traz sai
    # EM BRANCO — a regra é daqui, e não do texto.
    import protesto_pecas as PECAS
    rotulo = PECAS.vocabulario(con, "PT_EDITAL_ROTULOS")

    def _r(nome: str, **claros: Any) -> str:
        return PECAS.preencher(rotulo[nome], "PT_EDITAL_ROTULOS", AvisoError,
                               **claros)

    modelo = PECAS.texto(con, "PT_EDITAL_INTIMACAO")
    if not limite:
        modelo = "\n".join("" if "{prazo_limite}" in linha else linha
                           for linha in modelo.split("\n"))
    return PECAS.preencher(
        modelo, "PT_EDITAL_INTIMACAO", AvisoError,
        serventia=casa, devedor=devedor,
        documento_do_devedor=(
            ", " + _r("inscrito", documento=documento) if documento else ""),
        ate_quando=_br(limite) if limite else _r("sem_prazo"),
        protocolo=protocolo or _r("sem_protocolo"),
        numero_titulo=titulo["numero_titulo"] or _r("sem_numero"),
        especie=(" — " + _r("especie", especie=titulo["especie"])
                 if titulo["especie"] else ""),
        valor=valor, prazo_limite=_br(limite),
        endereco_da_serventia=sv.get("endereco_completo") or "",
        telefone=sv.get("serventia_telefone") or sv.get("telefone") or "",
        # A DATA POR EXTENSO, como em todo papel que esta casa assina.
        # `2026-08-25` e formato de banco de dados, e nao de edital afixado.
        local_e_data=f"{cidade}/{uf}, {quando}" if cidade else quando)


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
    linha = banco(con).um("SELECT MAX(numero) AS n FROM pt_editais WHERE ano=%s",
                          (int(ano),))
    return int(linha["n"] if linha and linha["n"] else 0) + 1


def publicar_edital(con: sqlite3.Connection, aviso_id: int, *, sv: dict,
                    hoje: str, agora: str, data_extenso: str | None = None,
                    usuario: str | None = None,
                    justificativa: str | None = None) -> dict:
    """Publica o edital do aviso que nao foi entregue. ESCREVE.

    E ELE QUE LAVRA A INTIMACAO POR EDITAL — modo `EDITAL`, com o codigo do
    edital, que e `protesto.lancar_intimacao` quem grava. Antes disto, o
    codigo do edital era digitado a mao na ficha, e edital que so existe como
    texto num campo nao se confere depois.

    O TEOR CONGELA. Edital publicado nao se redige de novo: e o papel que
    substitui a intimacao pessoal, e se ele mudar depois ninguem sabe o que
    foi afixado.
    """
    bd = banco(con)
    aviso = _aviso_para_gravar(bd, aviso_id)
    if not aviso:
        raise AvisoError(f"Aviso {aviso_id} não encontrado.")
    if aviso["situacao"] != "NAO_ENTREGUE":
        raise AvisoError(
            f"O aviso {aviso['numero']}/{aviso['ano']} está "
            f"{aviso['situacao']}. Só vai a edital o aviso que saiu e não foi "
            f"entregue — o edital substitui a intimação pessoal que não deu "
            f"certo, e não a que nem se tentou.")

    # O EDITAL VEM DEPOIS DA RESOLVE (15/10/2026): CN-MA art. 922, «após
    # esgotados todos os meios de localização razoavelmente disponíveis». Onde
    # a Intimação Digital cabe e não foi tentada, ou ainda está correndo, o
    # edital pede o motivo escrito; onde ela confirmou, o edital não cabe.
    caminho = depois_da_nao_entrega(bd, aviso)
    if caminho["edital"] == "RECUSADO":
        raise AvisoError(caminho["frase"])
    porque = " ".join(str(justificativa or "").split())
    if caminho["edital"] == "JUSTIFICAR" and len(porque) < 10:
        raise AvisoError(
            caminho["frase"] + " Para publicar o edital agora, escreva o "
            "motivo (pelo menos dez letras) — ele fica no ato da intimação.")
    sobre_a_resolve = caminho["resumo"] + (f"; motivo: {porque}" if porque
                                           else "")

    tit = PT.titulo(bd, int(aviso["titulo_id"]))
    if not tit:
        raise AvisoError(f"Título {aviso['titulo_id']} não encontrado.")

    ano = int(str(hoje)[:4])
    bd.travar("pt_editais.numero")
    numero = proximo_numero_do_edital(bd, ano)
    # O PRAZO-LIMITE DO EDITAL NUNCA CAI ANTES DO 1º DIA ÚTIL DEPOIS DA
    # PUBLICAÇÃO (CN-MA art. 922, §§ 1º e 3º) — 27/10/2026. Até aqui o edital
    # imprimia só o 3º dia útil da protocolização, que no edital publicado
    # tarde já estava vencido. Os 13 editais regularizados em 27/10 só saíram
    # com o prazo certo porque o script de regularização trocou este cálculo.
    teor = montar_teor_do_edital(aviso=aviso, titulo=tit, sv=sv, hoje=hoje,
                                 limite=prazo_de_pagamento(bd, tit, hoje),
                                 data_extenso=data_extenso, con=bd)
    codigo = f"ED-{ano}-{numero:04d}"

    lavrado = PT.lancar_intimacao(
        con, int(aviso["titulo_id"]), modo="EDITAL", agora=agora,
        usuario=usuario, codigo_edital=codigo,
        comprovante=(f"Aviso {aviso['numero']}/{aviso['ano']} não entregue: "
                     f"{motivo_rotulo(aviso['motivo'])}; Intimação Digital: "
                     f"{sobre_a_resolve}"))
    try:
        edital_id = int(bd.escrever(
            """INSERT INTO pt_editais(numero, ano, aviso_id, titulo_id,
                   publicado_em, publicado_por, cidade_ibge, teor, hash_teor,
                   ato_id, criado_em)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (numero, ano, int(aviso_id), int(aviso["titulo_id"]), hoje,
             usuario, cidade_ibge(bd), teor,
             hash_edital(numero, ano, teor, agora), lavrado["ato_id"], agora))[0]["id"])
    except sqlite3.IntegrityError as erro:
        raise AvisoError(
            f"O edital {numero}/{ano} acabou de ser usado por outro "
            f"atendimento. Publique de novo — o próximo número sai livre."
        ) from erro
    bd.escrever("UPDATE pt_avisos SET situacao='EDITAL', edital_id=%s WHERE id=%s",
                (edital_id, int(aviso_id)))
    return {"edital_id": edital_id, "numero": numero, "ano": ano,
            "codigo": codigo, "teor": teor, "ato_id": lavrado["ato_id"],
            "aviso_id": int(aviso_id)}


# --------------------------------------------------------------- consultas


def ler(con: sqlite3.Connection, aviso_id: int) -> dict | None:
    """O aviso. So LE."""
    return banco(con).um("SELECT * FROM pt_avisos WHERE id=%s",
                         (int(aviso_id),))


def _aviso_para_gravar(con: sqlite3.Connection, aviso_id: int) -> dict | None:
    """O aviso, com a linha PRESA ate o fim da transacao (FOR UPDATE).

    Para quem confere a situacao do aviso e grava em cima dela. Sem a linha
    presa, duas entregas do mesmo aviso ao mesmo tempo lavrariam duas
    intimacoes, e a entrega e o edital juntos deixariam o aviso publicado em
    cima de uma entrega. Com ela, o segundo espera o primeiro e le a situacao
    ja gravada. `ler` continua so lendo, para as telas.
    """
    bd = banco(con)
    bd._escrita()
    return bd.um("SELECT * FROM pt_avisos WHERE id=%s FOR UPDATE",
                 (int(aviso_id),))


def tentativas(con: sqlite3.Connection, aviso_id: int) -> list[dict]:
    """As tentativas de entrega daquele aviso, na ordem. So LE.

    E o rastro que justifica o edital. Sem ele, "publicou-se edital" fica sem
    o "porque" — e o porque e o que a inspecao pergunta.
    """
    return [dict(r) for r in banco(con).ler(
        """SELECT * FROM pt_tentativas WHERE aviso_id=%s ORDER BY id""",
        (int(aviso_id),))]


def do_titulo(con: sqlite3.Connection, titulo_id: int) -> list[dict]:
    """Os avisos daquele titulo, do mais novo para o mais velho. So LE.

    LISTA, e nao um so: 255 titulos do acervo tem mais de um aviso.
    """
    return [dict(r) for r in banco(con).ler(
        """SELECT a.*, e.numero AS edital_numero, e.publicado_em AS edital_em
             FROM pt_avisos a LEFT JOIN pt_editais e ON e.id = a.edital_id
            WHERE a.titulo_id=%s ORDER BY a.id DESC""", (int(titulo_id),))]


def esperando_entrega(con: sqlite3.Connection, limite: int = 200, *,
                      hoje: str | None = None) -> list[dict]:
    """Avisos que sairam e ainda nao tiveram desfecho. So LE.

    Com `hoje`, deixa de fora o aviso de titulo APONTADO HA MAIS DE
    `ANTIGO_DIAS` — esse vai para «apontados antigos», porque aviso de 2022
    sem desfecho nao esta na rua: e pendencia velha a decidir (21/10/2026).
    """
    bd = banco(con)
    linhas = [dict(r) for r in bd.ler(
        """SELECT a.*, t.numero_titulo, t.protocolo, t.saldo_centavos
             FROM pt_avisos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.situacao='EMITIDO' ORDER BY a.id LIMIT %s""",
        (int(limite),))]
    if hoje is None:
        return linhas
    corte = _corte_dos_antigos(hoje)
    antigos = {t["titulo_id"] for t in _apontados(bd)
               if (t["apontado_em"] or "") < corte}
    return [a for a in linhas if a["titulo_id"] not in antigos]


# APONTADO HA MAIS DE SEIS MESES NAO E INTIMACAO A FAZER: e pendencia velha.
# Medido em 21/10/2026: dos 29 titulos apontados trazidos do E-Oficio, 18
# entraram entre 02/10 e 13/10 (e um em 03/08) e 10 entre 2020 e 2022 — esses
# nunca foram baixados la. Decisao do oficial: ficam separados, «apontados
# antigos — decidir», para conferir no papel se foram pagos, retirados ou
# devolvidos. O prazo e regua de tela, e nao de lei.
ANTIGO_DIAS = 180


def _corte_dos_antigos(hoje: str) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(str(hoje)[:10])
            - timedelta(days=ANTIGO_DIAS)).isoformat()


def _apontados(con: sqlite3.Connection) -> list[dict]:
    """Os titulos APONTADOS, com a data do apontamento e os avisos. So LE.

    O titulo sem apontamento valido (`apontado_em` vazio) vem PRIMEIRO, como
    vinha no SQLite — o NULL do PostgreSQL iria para o fim sem o NULLS FIRST.
    """
    saida = []
    for t in banco(con).ler(
            """SELECT t.id AS titulo_id, t.protocolo, t.numero_titulo,
                      t.saldo_centavos, t.origem,
                      (SELECT MIN(x.data_ato) FROM pt_atos x
                        WHERE x.titulo_id = t.id AND x.tipo = 'APONTAMENTO'
                          AND x.cancelado = 0) AS apontado_em,
                      (SELECT d.nome FROM pt_devedores d
                        WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1)
                          AS devedor_nome,
                      (SELECT COUNT(*) FROM pt_avisos a
                        WHERE a.titulo_id = t.id AND a.situacao <> 'CANCELADO')
                          AS avisos_vivos,
                      (SELECT COUNT(*) FROM pt_avisos a
                        WHERE a.titulo_id = t.id) AS avisos
                 FROM pt_titulos t
                WHERE t.situacao = 'APONTADO'
                ORDER BY apontado_em NULLS FIRST, t.id"""):
        linha = dict(t)
        # `pt_atos.data_ato` e TEXTO, aqui e na producao: `AAAA-MM-DD` da
        # carga do E-Oficio, `AAAA-MM-DDTHH:MM:SS` do balcao — e o corte dos
        # antigos compara texto. O `str()` mantem a conta certa se a coluna um
        # dia virar `date`: o psycopg devolveria `datetime.date`, e `[:10]`
        # nele estoura (revisao do LH06, conferida no LH08).
        linha["apontado_em"] = str(linha["apontado_em"] or "")[:10] or None
        linha["avisos_vivos"] = int(linha["avisos_vivos"])
        linha["avisos"] = int(linha["avisos"])
        saida.append(linha)
    return saida


def apontados_sem_aviso(con: sqlite3.Connection, hoje: str) -> list[dict]:
    """Apontados recentes SEM aviso vivo — a lista que faltava (21/10/2026).

    Antes dela, titulo apontado sem aviso so aparecia na propria ficha, e os
    que vieram do E-Oficio sumiram da vista. So LE.
    """
    corte = _corte_dos_antigos(hoje)
    return [t for t in _apontados(con)
            if not t["avisos_vivos"] and (t["apontado_em"] or "") >= corte]


def apontados_antigos(con: sqlite3.Connection, hoje: str) -> list[dict]:
    """Apontados ha mais de `ANTIGO_DIAS` — a decidir, nao a intimar. So LE."""
    corte = _corte_dos_antigos(hoje)
    return [t for t in _apontados(con) if (t["apontado_em"] or "") < corte]


def esperando_edital(con: sqlite3.Connection, limite: int = 200) -> list[dict]:
    """Avisos nao entregues que ainda nao foram a edital. So LE.

    E A LISTA QUE MAIS ENCHE nesta casa: 1.092 dos 1.618 avisos do acervo
    terminaram em edital, e 94% das nao-entregas sao "Ausente".

    SO TITULO AINDA APONTADO (15/10/2026): o que ja foi intimado por outro
    caminho — a Intimacao Digital confirmada, ou um segundo aviso entregue —
    nao espera edital, e ficar na lista convidaria a publicar um edital que
    nao cabe.
    """
    return [dict(r) for r in banco(con).ler(
        """SELECT a.*, t.numero_titulo, t.protocolo, t.saldo_centavos
             FROM pt_avisos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.situacao='NAO_ENTREGUE' AND t.situacao='APONTADO'
            ORDER BY a.entrega_em NULLS FIRST, a.id
            LIMIT %s""", (int(limite),))]


def editais_do_dia(con: sqlite3.Connection, dia: str) -> list[dict]:
    """Os editais publicados naquele dia, para a folha da parede e o arquivo da
    CENPROT. So LE. Edital de ato tornado sem efeito nao sai em nenhum dos dois;
    o do acervo, sem `ato_id`, continua (`_SQL_EDITAL_DE_ATO_VIVO`)."""
    return [dict(r) for r in banco(con).ler(
        f"""SELECT e.*, t.numero_titulo, t.protocolo
             FROM pt_editais e JOIN pt_titulos t ON t.id = e.titulo_id
            WHERE e.publicado_em = %s AND {_SQL_EDITAL_DE_ATO_VIVO}
            ORDER BY e.numero, e.id""", (str(dia)[:10],))]


# ------------------------------- o comprovante do envio do edital à CENPROT
#
# PEDIDO DO OFICIAL, 26/10/2026 (problema #142): «vamos criar um campo para
# anexar o comprovante de envio do edital». O CN-MA art. 922, § 1º, manda
# AFIXAR e PUBLICAR no site da CENPROT; a API dela não tem consulta de edital,
# e o arquivo do dia sobe pelo portal. A prova de que subiu é o comprovante
# (a tela do portal, salva em PDF ou imagem), e até aqui ela não tinha lugar.
#
# O ARQUIVO É UM POR DIA, e o comprovante vai para CADA edital daquele dia —
# uma linha em `attachments` por edital, apontando para o mesmo arquivo em
# disco. É assim que a pergunta da correição («este edital foi publicado na
# CENPROT?») se responde edital a edital, e que o dia sem comprovante aparece.
ENTIDADE_DO_ENVIO_DO_EDITAL = "PT_EDITAL_CENPROT"
DIAS_DO_QUADRO_DE_ENVIO = 30

# O EDITAL DE ATO TORNADO SEM EFEITO NÃO COBRA COMPROVANTE — medido em
# 30/10/2026: o dia 07/10 aparecia como «0 de 5» para sempre, e os 5 têm o ato
# de intimação cancelado; os títulos foram para edital novo. O edital do acervo
# não tem `ato_id` e continua contando. O roteiro lê este mesmo quadro
# (`protesto_roteiro._cobrar_editais`), e por isso a tela e ele não discordam.
_SQL_EDITAL_DE_ATO_VIVO = (
    "(e.ato_id IS NULL OR NOT EXISTS (SELECT 1 FROM pt_atos x "
    "WHERE x.id = e.ato_id AND COALESCE(x.cancelado, 0) <> 0))")


def envios_do_edital(con: sqlite3.Connection, hoje: str,
                     dias: int = DIAS_DO_QUADRO_DE_ENVIO) -> list[dict]:
    """Os dias com edital publicado, e se o envio à CENPROT tem comprovante.
    Só LÊ. O mais recente primeiro; os dias sem comprovante, no alto. Só conta
    edital de ato vivo: o dia sem nenhum vivo não aparece."""
    from datetime import date as _date, timedelta as _td
    desde = (_date.fromisoformat(str(hoje)[:10]) - _td(days=int(dias))).isoformat()
    bd = banco(con)
    linhas = bd.ler(
        f"""SELECT e.publicado_em AS dia, COUNT(*) AS editais,
                  SUM(CASE WHEN EXISTS (
                        SELECT 1 FROM attachments a
                         WHERE a.entity_type = %s AND a.entity_id = e.id)
                      THEN 1 ELSE 0 END) AS com_comprovante
             FROM pt_editais e
            WHERE e.publicado_em >= %s AND {_SQL_EDITAL_DE_ATO_VIVO}
            GROUP BY e.publicado_em
            ORDER BY e.publicado_em DESC""",
        (ENTIDADE_DO_ENVIO_DO_EDITAL, desde))
    saida = []
    for r in linhas:
        d = {"dia": str(r["dia"])[:10], "editais": int(r["editais"]),
             "com_comprovante": int(r["com_comprovante"] or 0)}
        d["completo"] = d["com_comprovante"] == d["editais"]
        d["anexos"] = [dict(a) for a in bd.ler(
            f"""SELECT MIN(a.id) AS id, a.original_name, MIN(a.uploaded_at) AS uploaded_at
                 FROM attachments a JOIN pt_editais e ON e.id = a.entity_id
                WHERE a.entity_type = %s AND e.publicado_em = %s
                  AND {_SQL_EDITAL_DE_ATO_VIVO}
                GROUP BY a.sha256, a.original_name ORDER BY MIN(a.id)""",
            (ENTIDADE_DO_ENVIO_DO_EDITAL, d["dia"]))]
        saida.append(d)
    # A consulta já vem do mais recente; a ordenação é estável, então os dias
    # sem comprovante sobem sem perder essa ordem.
    saida.sort(key=lambda d: d["completo"])
    return saida


def guardar_comprovante_do_envio(con: sqlite3.Connection, dia: str, *,
                                 nome: Any, conteudo: bytes,
                                 pasta_de_arquivos: Any, agora: str,
                                 usuario_id: int | None = None) -> dict:
    """Anexa a cada edital do dia o comprovante do envio à CENPROT. ESCREVE,
    e grava o arquivo em disco uma vez.

    Recusa o dia sem edital publicado (o comprovante afirmaria o envio de
    nada), o arquivo que não é PDF/PNG/JPG de verdade e o mesmo arquivo
    duas vezes. Não sobrescreve: um segundo comprovante é outro anexo. O edital
    de ato tornado sem efeito não recebe o anexo: ele não vai no arquivo do dia.
    """
    dia = str(dia or "")[:10]
    bd = banco(con)
    editais = [int(r["id"]) for r in bd.ler(
        f"""SELECT e.id FROM pt_editais e
             WHERE e.publicado_em = %s AND {_SQL_EDITAL_DE_ATO_VIVO}
             ORDER BY e.id""", (dia,))]
    if not editais:
        if bd.um("SELECT id FROM pt_editais WHERE publicado_em = %s LIMIT 1",
                 (dia,)):
            raise AvisoError(
                f"Os editais de {dia} são todos de ato tornado sem efeito, e por "
                f"isso não há envio a comprovar neste dia.")
        raise AvisoError(
            f"Nenhum edital foi publicado em {dia}. O comprovante é do envio "
            f"do arquivo dos editais do dia — publique o edital primeiro.")
    nome_limpo = Path(str(nome or "")).name.strip()
    ext = Path(nome_limpo).suffix.lower()
    if ext not in ASSINATURA_DO_COMPROVANTE:
        raise AvisoError(
            "O comprovante tem de ser PDF, PNG ou JPG — a tela do portal da "
            "CENPROT salva em PDF, ou uma captura dela.")
    conteudo = bytes(conteudo or b"")
    if not conteudo:
        raise AvisoError("O arquivo do comprovante está vazio.")
    if len(conteudo) > LIMITE_DO_COMPROVANTE:
        raise AvisoError(
            f"O comprovante passa de "
            f"{LIMITE_DO_COMPROVANTE // 1024 // 1024} MB.")
    if not conteudo.startswith(ASSINATURA_DO_COMPROVANTE[ext]):
        raise AvisoError(
            f"O arquivo diz ser {ext} e não é — o conteúdo não começa como um "
            f"{ext[1:].upper()}. Salve de novo e anexe.")
    sha = hashlib.sha256(conteudo).hexdigest()
    ja = {int(r["entity_id"]) for r in bd.ler(
        """SELECT entity_id FROM attachments
            WHERE entity_type = %s AND sha256 = %s""",
        (ENTIDADE_DO_ENVIO_DO_EDITAL, sha))}
    faltam = [e for e in editais if e not in ja]
    if not faltam:
        raise AvisoError(
            f"Este arquivo já está anexado aos editais de {dia}.")

    destino = Path(pasta_de_arquivos) / "Protesto" / "Editais" / "CENPROT"
    destino.mkdir(parents=True, exist_ok=True)
    n = 1
    arquivo = destino / f"envio-edital-{dia}-{n}{ext}"
    while arquivo.exists():
        n += 1
        arquivo = destino / f"envio-edital-{dia}-{n}{ext}"
    arquivo.write_bytes(conteudo)
    anexos = []
    for edital_id in faltam:
        anexos.append(int(bd.escrever(
            """INSERT INTO attachments(entity_type, entity_id, original_name,
                   stored_name, stored_path, sha256, size_bytes, description,
                   uploaded_by, uploaded_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (ENTIDADE_DO_ENVIO_DO_EDITAL, edital_id, nome_limpo or arquivo.name,
             arquivo.name, str(arquivo), sha, len(conteudo),
             f"Comprovante do envio à CENPROT dos editais de {dia}",
             usuario_id, agora))[0]["id"]))
    return {"dia": dia, "editais": len(faltam), "anexos": anexos,
            "nome": arquivo.name}


def edital(con: sqlite3.Connection, edital_id: int) -> dict | None:
    """O edital, com o teor congelado. So LE."""
    return banco(con).um("SELECT * FROM pt_editais WHERE id=%s",
                         (int(edital_id),))


def contagens(con: sqlite3.Connection) -> dict:
    """Quantos avisos em cada situacao. So LE — para o alto da tela."""
    achado = {r["situacao"]: r["n"] for r in banco(con).ler(
        "SELECT situacao, COUNT(*) AS n FROM pt_avisos GROUP BY situacao "
        "ORDER BY situacao")}
    return {s: int(achado.get(s, 0)) for s in SITUACOES}


# ------------------------------------- o que vem depois da não-entrega
#
# PEDIDO DO OFICIAL, 15/10/2026: «botão para avisar que não pode ser entregue
# (seja por ser fora da zona de entrega ou por negativa em receber),
# possibilitando mandar para intimação pela Resolve e, não rolando pela
# Resolve, por edital». É a ordem do Código de Normas (Prov. 28/2026):
#
#   art. 919, § 1º — a intimação pode ir por meio eletrônico quando houver os
#   dados do devedor;
#   art. 921, § 6º, II — a intimação digital se cumpre «quando comprovado o
#   seu recebimento por meio de confirmação de recebimento da plataforma»;
#   art. 922 — o edital vem quando ninguém se dispõe a receber, ou o devedor
#   não é localizado, «após esgotados todos os meios de localização
#   razoavelmente disponíveis ao tabelionato».
#
# OS DOIS MOTIVOS DO PEDIDO JÁ ESTÃO NO CATÁLOGO DA CASA: «Fora do perímetro»
# (14) é a zona de entrega, e «Recusou-se a receber» (3). O rótulo do catálogo
# fica como foi transcrito; a tela os põe primeiro, com o nome do pedido.
MOTIVO_FORA_DA_ZONA = 14
MOTIVO_RECUSOU = 3
MOTIVOS_EM_DESTAQUE = (MOTIVO_FORA_DA_ZONA, MOTIVO_RECUSOU)
ROTULO_DO_DESTAQUE = {
    MOTIVO_FORA_DA_ZONA: "Fora da zona de entrega",
    MOTIVO_RECUSOU: "Recusou-se a receber",
}

# OS ESTADOS DA RESOLVE, lidos do lado desta casa. Os doze são do contrato
# (`resolve_api.ESTADOS`); o que se decide aqui é o que cada um quer dizer
# para o edital.
#
#   confirmou — a plataforma considera o devedor cientificado (art. 921,
#   § 6º, II): lavra-se a intimação digital, e edital não cabe;
#   pagou — o devedor pagou pela plataforma: o caminho é a baixa na ficha;
#   não deu — terminou sem intimar: o edital está liberado;
#   entregue — a mensagem chegou e o devedor não a abriu (27/10/2026): os dois
#   caminhos ficam abertos, e quem escolhe é o oficial — ver abaixo;
#   o resto — está correndo: o edital espera, ou vai com o motivo escrito.
RESOLVE_CONFIRMOU = frozenset({"INTIMADO"})
RESOLVE_PAGOU = frozenset({"PAGO"})
RESOLVE_NAO_DEU = frozenset({"NAO_ENRIQUECIDO", "SEM_RESPOSTA", "REJEITADO",
                             "CANCELADO"})
# A ENTREGA SEM LEITURA NÃO ESPERA PARA SEMPRE — 27/10/2026. Relato do oficial:
# «não consegui mandar um título que foi pra intimação digital para edital».
# `ENTREGUE` caía no «está correndo», e o edital ficava escondido atrás do
# motivo escrito. O CN-MA, art. 919, § 1º, considera a intimação eletrônica
# «cumprida quando comprovada por esse mesmo meio a entrega no referido
# endereço» — então lavrar a digital é possível; mas a casa pode não ter a
# entrega sem leitura por suficiente, e mandar ao edital. Os dois botões
# aparecem lado a lado; o sistema não escolhe.
#
# E O § 2º NÃO VIROU REGRA AQUI, de propósito: ele fala da intimação «feita na
# forma do caput» e manda refazê-la pelo art. 14 da Lei 9.492 — não diz que a
# mensagem digital sem resposta em três dias libera o edital. Ler isso nele
# seria a máquina decidindo o que a norma não decide.
RESOLVE_ENTREGUE = frozenset({"ENTREGUE"})


def _ultima_na_resolve(con: sqlite3.Connection, titulo_id: int) -> dict | None:
    """A última Intimação Digital deste título, em PRODUÇÃO. Só LÊ."""
    bd = banco(con)
    if not bd.tem_tabela("rs_intimacoes"):
        return None
    import centrais_cred as CRED
    linha = bd.um(
        """SELECT id, identificador, intimacao_id, estado, estado_em,
                  enviada_em
             FROM rs_intimacoes
            WHERE titulo_id = %s AND ambiente = %s
            ORDER BY id DESC LIMIT 1""",
        (int(titulo_id), CRED.PRODUCAO))
    return dict(linha) if linha else None


def depois_da_nao_entrega(con: sqlite3.Connection, aviso: Any) -> dict:
    """O próximo passo do aviso que não foi entregue. Só LÊ.

    Devolve `passo` (RESOLVE, AGUARDAR, LAVRAR_DIGITAL, ENTREGUE, PAGO ou
    EDITAL),
    `edital` (LIBERADO, JUSTIFICAR ou RECUSADO), a `frase` para a tela e o
    `resumo` que vai escrito no ato da intimação por edital.

    **NÃO JULGA PRAZO.** Quando a Resolve ainda está correndo, o edital não é
    recusado: ele pede o motivo escrito. Quem decide se dá para esperar a
    plataforma dentro do tríduo é o oficial — a regra de 24/08/2026.
    """
    import resolve_intimacao as RS
    titulo_id = int(aviso["titulo_id"])
    bd = banco(con)
    tit = bd.um(
        """SELECT t.id, t.situacao, t.chave_cenprot,
                  (SELECT d.nome FROM pt_devedores d
                    WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1)
                      AS devedor_nome
             FROM pt_titulos t WHERE t.id = %s""", (titulo_id,))
    classe = (RS.situacao_do_titulo(dict(tit)) if tit
              else {"pode_ir": False, "porque_nao": "o título não existe"})
    ultima = _ultima_na_resolve(bd, titulo_id)
    estado = str((ultima or {}).get("estado") or "").strip().upper()

    if ultima is None and classe["pode_ir"]:
        passo, edital = "RESOLVE", "JUSTIFICAR"
        frase = ("A Intimação Digital (Resolve) ainda não foi tentada. O "
                 "edital vem depois de esgotados os meios disponíveis "
                 "(CN-MA art. 922): mande pela Resolve primeiro.")
        resumo = "não tentada"
    elif ultima is None:
        passo, edital = "EDITAL", "LIBERADO"
        frase = (f"A Intimação Digital não serve a este título — "
                 f"{classe['porque_nao']}. O caminho é o edital.")
        resumo = f"não se aplica ({classe['porque_nao']})"
    elif estado in RESOLVE_CONFIRMOU:
        passo, edital = "LAVRAR_DIGITAL", "RECUSADO"
        frase = ("A Resolve confirmou a intimação do devedor (CN-MA art. "
                 "921, § 6º, II). Lavre a intimação digital — o edital não "
                 "cabe.")
        resumo = f"confirmada ({ultima['identificador']})"
    elif estado in RESOLVE_PAGOU:
        passo, edital = "PAGO", "RECUSADO"
        frase = ("A Resolve informa que o título foi PAGO. Confira e lance o "
                 "pagamento na ficha do título — o edital não cabe.")
        resumo = f"pago ({ultima['identificador']})"
    elif estado in RESOLVE_NAO_DEU:
        passo, edital = "EDITAL", "LIBERADO"
        frase = (f"A Intimação Digital não deu certo (a Resolve diz "
                 f"«{estado}»). O caminho é o edital.")
        resumo = f"não deu ({ultima['identificador']}, {estado})"
    elif estado in RESOLVE_ENTREGUE:
        passo, edital = "ENTREGUE", "LIBERADO"
        frase = ("A Resolve ENTREGOU a mensagem ao devedor, mas ele não a "
                 "abriu. Pelo CN-MA art. 919, § 1º, a intimação eletrônica se "
                 "considera cumprida com a entrega comprovada pelo mesmo meio "
                 "— dá para lavrar a intimação digital. Se a casa não tiver a "
                 "entrega sem leitura por suficiente, publique o edital. A "
                 "escolha é do oficial.")
        resumo = f"entregue sem leitura ({ultima['identificador']})"
    else:
        passo, edital = "AGUARDAR", "JUSTIFICAR"
        enviada = str(ultima.get("enviada_em") or "")[:10]
        frase = (f"A Intimação Digital foi enviada em {_br(enviada)} e está "
                 f"«{estado or 'sem resposta ainda'}». Espere a confirmação "
                 f"(atualize os estados) — se ela não vier a tempo, publique "
                 f"o edital dizendo por quê.")
        resumo = (f"em curso ({ultima['identificador']}, "
                  f"{estado or 'sem resposta'})")
    return {"passo": passo, "edital": edital, "frase": frase,
            "resumo": resumo, "resolve": ultima, "estado": estado,
            "pode_ir": bool(classe.get("pode_ir")),
            "porque_nao": classe.get("porque_nao") or ""}


def lavrar_intimacao_digital(con: sqlite3.Connection, aviso_id: int, *,
                             agora: str, usuario: str | None = None) -> dict:
    """Lavra a intimação que a Resolve confirmou. ESCREVE.

    **SÓ COM A CONFIRMAÇÃO DA PLATAFORMA** (CN-MA art. 921, § 6º, II): o
    estado tem de ser o que a Resolve chama de INTIMADO. Antes dele, o que há
    é mensagem enviada, e mensagem enviada não é intimação. Quem lavra é
    `protesto.lancar_intimacao`, modo pessoal **digital** — é a marca que faz o
    termo do protesto dizer «intimado por meio eletrônico».
    """
    bd = banco(con)
    aviso = _aviso_para_gravar(bd, aviso_id)
    if not aviso:
        raise AvisoError(f"Aviso {aviso_id} não encontrado.")
    if aviso["situacao"] != "NAO_ENTREGUE":
        raise AvisoError(
            f"O aviso {aviso['numero']}/{aviso['ano']} está "
            f"{aviso['situacao']}. A intimação digital entra no lugar do "
            f"aviso que não foi entregue.")
    caminho = depois_da_nao_entrega(bd, aviso)
    # A ENTREGA SEM LEITURA TAMBÉM LAVRA (27/10/2026), quando o oficial a tem
    # por suficiente — CN-MA art. 919, § 1º. O comprovante diz qual das duas
    # foi, porque o termo e a certidão vão ser lidos por quem não estava aqui.
    if caminho["passo"] not in ("LAVRAR_DIGITAL", "ENTREGUE"):
        raise AvisoError(
            "A Resolve ainda não confirmou a intimação deste devedor. "
            + caminho["frase"])
    so_entregue = caminho["passo"] == "ENTREGUE"
    ultima = caminho["resolve"] or {}
    quando = str(ultima.get("estado_em") or "")[:10]
    if so_entregue:
        como = (", entregue no endereço eletrônico do devedor pela plataforma"
                + (f" em {_br(quando)}" if quando else "")
                + ", sem leitura (CN-MA art. 919, § 1º)")
    else:
        como = (", confirmada pela plataforma"
                + (f" em {_br(quando)}" if quando else "")
                + " (CN-MA art. 921, § 6º, II)")
    lavrado = PT.lancar_intimacao(
        con, int(aviso["titulo_id"]), modo="PESSOAL", digital=True,
        agora=agora, usuario=usuario,
        comprovante=(f"Intimação Digital (Resolve) {ultima.get('identificador')}"
                     + como + f"; aviso {aviso['numero']}/{aviso['ano']} não "
                       f"entregue: {motivo_rotulo(aviso['motivo'])}"))
    bd.escrever("UPDATE pt_avisos SET ato_id=%s WHERE id=%s",
                (lavrado["ato_id"], int(aviso_id)))
    return {"aviso_id": int(aviso_id), "ato_id": lavrado["ato_id"],
            "identificador": ultima.get("identificador"),
            "so_entregue": so_entregue}


# --------------------------------------- o comprovante da intimação entregue
#
# PEDIDO DO OFICIAL, 15/10/2026: «lugar de upload das intimações dos títulos
# entregues». É o que o CN-MA exige: a intimação se comprova «mediante
# protocolo, aviso de recebimento — AR, ou documento equivalente» (art. 921)
# e se considera cumprida quando comprovado o recebimento no endereço do
# devedor (art. 921, § 6º, I). Até aqui o sistema guardava só o nome de quem
# recebeu; o papel assinado ficava na gaveta.
#
# MORA EM `attachments`, como a imagem do título — a tabela geral da casa —,
# com dono próprio: o AVISO, e não o título. Um título tem vários avisos
# (255 no acervo), e o comprovante é daquele que chegou.
ENTIDADE_DO_COMPROVANTE = "PT_AVISO"
# De que situações o aviso aceita comprovante: a entrega e a tentativa (que
# segue valendo depois do edital, porque é ela que o fundamenta).
SITUACOES_COM_COMPROVANTE = ("ENTREGUE", "NAO_ENTREGUE", "EDITAL")


def ja_tem_este_comprovante(con: sqlite3.Connection, aviso_id: int,
                            conteudo: bytes) -> bool:
    """Se este mesmo arquivo já está anexado a este aviso. Só LÊ."""
    return banco(con).um(
        """SELECT 1 AS um FROM attachments
            WHERE entity_type=%s AND entity_id=%s AND sha256=%s""",
        (ENTIDADE_DO_COMPROVANTE, int(aviso_id),
         hashlib.sha256(bytes(conteudo or b"")).hexdigest())) \
        is not None
# O que se aceita, e a assinatura de cada tipo nos primeiros bytes: a lista é
# curta porque o arquivo abre NA TELA (`/arquivo/<id>/ver`), e arquivo de fora
# servido em linha roda na origem do sistema — a régua de `arquivo_visivel`.
ASSINATURA_DO_COMPROVANTE = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG",),
    ".jpg": (b"\xff\xd8",),
    ".jpeg": (b"\xff\xd8",),
}
LIMITE_DO_COMPROVANTE = 25 * 1024 * 1024     # 25 MB, o da imagem do título


def guardar_comprovante(con: sqlite3.Connection, aviso_id: int, *, nome: Any,
                        conteudo: bytes, pasta_de_arquivos: Any, agora: str,
                        usuario_id: int | None = None,
                        afirmacao: str | None = None) -> dict:
    """Anexa ao aviso o comprovante da intimação entregue. ESCREVE, e grava
    arquivo em disco.

    **SÓ AVISO ENTREGUE.** O comprovante prova uma entrega; anexá-lo a um
    aviso sem entrega registrada faria o papel dizer uma coisa e o sistema
    outra. **E NÃO SE SOBRESCREVE**: o segundo arquivo do mesmo aviso é outro
    anexo — a frente e o verso, ou a via corrigida —, e o mesmo arquivo duas
    vezes é recusado pelo conteúdo.

    **O ARQUIVO SUSPEITO SÓ ENTRA COM AFIRMAÇÃO EXPRESSA** (29/10/2026): o
    mesmo arquivo já anexado a outro aviso, ou o nome que cita o protocolo de
    outro título — foi o «2610070012.pdf» anexado ao aviso do 2610070007, em
    outubro. As afirmações voltam em `afirmacoes`, para a auditoria.
    """
    bd = banco(con)
    aviso = _aviso_para_gravar(bd, aviso_id)
    if not aviso:
        raise AvisoError(f"Aviso {aviso_id} não encontrado.")
    # A TENTATIVA TAMBÉM SE PROVA (15/10/2026, pedido do oficial: «um campo de
    # tentativa, onde se coloca quando tentou, para fundamentar a expedição de
    # edital»). O canhoto que volta com as tentativas anotadas é a prova de
    # que se tentou — CN-MA art. 922, «esgotados todos os meios» —, e fica
    # anexado ao aviso não entregue, inclusive depois do edital.
    if aviso["situacao"] not in SITUACOES_COM_COMPROVANTE:
        raise AvisoError(
            f"O aviso {aviso['numero']}/{aviso['ano']} está "
            f"{aviso['situacao']}. O comprovante é da entrega ou da tentativa "
            f"— registre o desfecho do aviso primeiro.")
    conferido = _conferir_comprovante(bd, aviso, nome=nome, conteudo=conteudo)
    afirmacoes = PROVA.vencer_todas(
        conferido["suspeitas"], afirmacao, erro=AvisoError,
        abertura=(f"O comprovante não se anexa ao aviso "
                  f"{aviso['numero']}/{aviso['ano']} assim"))
    anexo = _gravar_comprovante(bd, aviso, conferido,
                                pasta_de_arquivos=pasta_de_arquivos,
                                agora=agora, usuario_id=usuario_id)
    return {**anexo, "afirmacoes": afirmacoes}


def _conferir_comprovante(bd: Any, aviso: dict, *, nome: Any,
                          conteudo: bytes) -> dict:
    """O arquivo é um comprovante que se possa anexar a ESTE aviso? Só LÊ.

    Recusa na hora o que não é arquivo de verdade (tipo, tamanho, assinatura
    dos primeiros bytes, repetido no mesmo aviso). O SUSPEITO não se recusa
    aqui: volta em `suspeitas`, e quem chama decide com a afirmação.
    """
    nome_limpo = Path(str(nome or "")).name.strip()
    ext = Path(nome_limpo).suffix.lower()
    if ext not in ASSINATURA_DO_COMPROVANTE:
        raise AvisoError(
            "O comprovante tem de ser PDF, PNG ou JPG — o papel assinado, "
            "escaneado ou fotografado.")
    conteudo = bytes(conteudo or b"")
    if not conteudo:
        raise AvisoError("O arquivo do comprovante está vazio.")
    if len(conteudo) > LIMITE_DO_COMPROVANTE:
        raise AvisoError(
            f"O comprovante passa de "
            f"{LIMITE_DO_COMPROVANTE // 1024 // 1024} MB. Escaneie com "
            f"resolução menor.")
    if not conteudo.startswith(ASSINATURA_DO_COMPROVANTE[ext]):
        raise AvisoError(
            f"O arquivo diz ser {ext} e não é — o conteúdo não começa como um "
            f"{ext[1:].upper()}. Salve de novo do scanner e anexe.")
    sha = hashlib.sha256(conteudo).hexdigest()
    if bd.um(
            """SELECT id FROM attachments
                WHERE entity_type=%s AND entity_id=%s AND sha256=%s
                ORDER BY id LIMIT 1""",
            (ENTIDADE_DO_COMPROVANTE, int(aviso["id"]), sha)):
        raise AvisoError("Este arquivo já está anexado a este aviso.")
    return {"nome_limpo": nome_limpo, "ext": ext, "conteudo": conteudo,
            "sha256": sha,
            "suspeitas": PROVA.suspeitas_do_comprovante(
                bd, aviso, nome=nome_limpo, sha256=sha)}


def _gravar_comprovante(bd: Any, aviso: dict, conferido: dict, *,
                        pasta_de_arquivos: Any, agora: str,
                        usuario_id: int | None = None) -> dict:
    """Grava em disco e em `attachments` o comprovante já conferido.
    ESCREVE."""
    aviso_id = int(aviso["id"])
    nome_limpo, ext = conferido["nome_limpo"], conferido["ext"]
    conteudo, sha = conferido["conteudo"], conferido["sha256"]
    destino = (Path(pasta_de_arquivos) / "Protesto" / "Intimacoes"
               / str(int(aviso["titulo_id"])))
    destino.mkdir(parents=True, exist_ok=True)
    n = len(comprovantes(bd, aviso_id)) + 1
    arquivo = destino / f"aviso-{aviso['numero']}-{aviso['ano']}-{n}{ext}"
    while arquivo.exists():
        n += 1
        arquivo = destino / f"aviso-{aviso['numero']}-{aviso['ano']}-{n}{ext}"
    arquivo.write_bytes(conteudo)
    anexo_id = int(bd.escrever(
        """INSERT INTO attachments(entity_type, entity_id, original_name,
               stored_name, stored_path, sha256, size_bytes, description,
               uploaded_by, uploaded_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (ENTIDADE_DO_COMPROVANTE, int(aviso_id), nome_limpo or arquivo.name,
         arquivo.name, str(arquivo), sha, len(conteudo),
         (f"Comprovante da intimação — aviso {aviso['numero']}/{aviso['ano']}"
          if aviso["situacao"] == "ENTREGUE" else
          f"Comprovante da tentativa de entrega — aviso "
          f"{aviso['numero']}/{aviso['ano']}"),
         usuario_id, agora))[0]["id"])
    return {"anexo_id": anexo_id, "aviso_id": int(aviso_id),
            "nome": arquivo.name}


def comprovantes(con: sqlite3.Connection, aviso_id: int) -> list[dict]:
    """Os comprovantes daquele aviso. Só LÊ."""
    return [dict(r) for r in banco(con).ler(
        """SELECT id, original_name, size_bytes, uploaded_at
             FROM attachments WHERE entity_type=%s AND entity_id=%s
            ORDER BY id""", (ENTIDADE_DO_COMPROVANTE, int(aviso_id)))]


def entregues(con: sqlite3.Connection, limite: int = 100) -> list[dict]:
    """Os avisos entregues, os SEM comprovante primeiro. Só LÊ.

    A lista de trabalho do upload: o que foi entregue e ainda não tem o papel
    anexado vem no alto, porque é o que a correição pergunta.
    """
    bd = banco(con)
    # O AVISO TRAZIDO DO E-OFÍCIO NÃO É TRABALHO DE UPLOAD (21/10/2026): o
    # papel dele é do arquivo do E-Ofício, e os 68 entregues em mãos viriam ao
    # alto como «falta o comprovante». A coluna `origem` chega ao esquema com
    # a carga dos avisos do E-Ofício (LH07); antes dela não há aviso dessa
    # origem, e a lista é a de sempre.
    #
    # MAS A ENTREGA REGISTRADA AQUI É TRABALHO DAQUI (29/10/2026): o aviso
    # que veio do E-Ofício e teve a entrega lançada NESTE sistema (a intimação
    # é ato daqui) volta à lista — foi o caso do 2610070003, entregue em
    # 22/10 sem o nome de quem recebeu e sem o comprovante, e invisível nesta
    # lista por causa da origem do aviso.
    fora_o_eoficio = (
        "AND (COALESCE(a.origem, '') <> 'EOFICIO' OR EXISTS ("
        "SELECT 1 FROM pt_atos i WHERE i.id = a.ato_id "
        "AND COALESCE(i.origem, '') <> 'EOFICIO'))"
        if bd.tem_coluna("pt_avisos", "origem") else "")
    linhas = [dict(r) for r in bd.ler(
        f"""SELECT a.*, t.numero_titulo, t.protocolo,
                  (SELECT COUNT(*) FROM attachments x
                    WHERE x.entity_type = %s AND x.entity_id = a.id)
                      AS n_comprovantes
             FROM pt_avisos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.situacao = 'ENTREGUE'
              {fora_o_eoficio}
            ORDER BY CASE WHEN (SELECT COUNT(*) FROM attachments x
                                 WHERE x.entity_type = %s
                                   AND x.entity_id = a.id) = 0
                            OR COALESCE(a.recebido_por, '') = ''
                          THEN 0 ELSE 1 END,
                     a.entrega_em DESC NULLS LAST, a.id DESC
            LIMIT %s""",
        (ENTIDADE_DO_COMPROVANTE, ENTIDADE_DO_COMPROVANTE, int(limite)))]
    for linha in linhas:
        linha["n_comprovantes"] = int(linha["n_comprovantes"])
        linha["comprovantes"] = comprovantes(bd, linha["id"])
    return linhas


# ------------------------------------------- quem recebeu, completado depois
#
# DECISÃO DO OFICIAL, 29/10/2026: «canhoto de entrega precisa ter o campo pra
# botar o nome de quem recebeu. se faltar, avisar escrevente pra completar».
# A entrega sem o nome só entra com afirmação expressa (`registrar_entrega`);
# quando entra assim — ou quando veio de antes da regra —, o nome se completa
# DEPOIS, lido do canhoto anexado, e a tarefa que avisou a escrevente fecha.
# O nome que já existe não se sobrescreve: corrigir exige afirmação expressa.

#: A origem da tarefa que avisa a escrevente — uma por aviso.
TAREFA_SEM_RECEBEDOR = "PT_AVISO_SEM_RECEBEDOR"
#: Quantas letras, no mínimo, o nome de quem recebeu tem de ter.
PISO_DO_NOME = 3


def _sem_nome(aviso: Any) -> bool:
    return not str((aviso or {}).get("recebido_por") or "").strip()


def tarefa_para_completar(con: sqlite3.Connection, aviso_id: int, *,
                          hoje: str, dono: int | None) -> dict | None:
    """A tarefa que avisa, NA HORA, que falta o nome de quem recebeu. Só LÊ.

    Devolve os dados para `db.create_task` (que abre transação própria e por
    isso a rota chama fora do `with`), ou `None` quando não falta nada. A
    tarefa é de quem registrou a entrega (`dono`) e do setor do Protesto; é
    painel e tarefa, sem e-mail por evento (decisão de 28/10/2026). Fecha
    sozinha quando o nome é completado (`completar_quem_recebeu`).
    """
    bd = banco(con)
    aviso = ler(bd, aviso_id)
    if not aviso or aviso["situacao"] != "ENTREGUE" or not _sem_nome(aviso):
        return None
    tit = bd.um("SELECT numero_titulo, protocolo FROM pt_titulos WHERE id = %s",
                (int(aviso["titulo_id"]),)) or {}
    nome = f"{aviso['numero']}/{aviso['ano']}"
    return {
        "source_type": TAREFA_SEM_RECEBEDOR,
        "source_ref": f"pt_avisos:{int(aviso_id)}",
        "title": f"[Protesto] Completar quem recebeu o aviso {nome}",
        "description": (
            f"O aviso {nome} (título {tit.get('numero_titulo') or '—'}, "
            f"protocolo {tit.get('protocolo') or '—'}) foi registrado como "
            f"ENTREGUE sem o nome de quem recebeu. Leia o nome no canhoto "
            f"assinado e complete em Protesto → Avisos e editais, lista "
            f"«Entregues — comprovante da intimação», aviso {nome}. Sem o "
            f"nome, o protesto deste título só sai com afirmação expressa."),
        "sector": "PROTESTO", "system_name": "Protesto", "priority": "ALTA",
        "status": "ABERTA", "start_date": str(hoje)[:10],
        "due_date": str(hoje)[:10], "assigned_user_id": dono,
        "evidence_required": 0}


def completar_quem_recebeu(con: sqlite3.Connection, aviso_id: int, *,
                           recebido_por: Any, agora: str,
                           afirmacao: str | None = None) -> dict:
    """Completa (ou corrige) o nome de quem recebeu um aviso ENTREGUE. ESCREVE.

    **SÓ COM O COMPROVANTE ANEXADO**: o nome se lê no canhoto assinado, e
    completar de memória seria pôr no sistema o que nenhum papel diz. **O
    NOME QUE JÁ EXISTE NÃO SE SOBRESCREVE**: corrigir exige a afirmação
    expressa (regra `CORRECAO_DE_QUEM_RECEBEU`). A intimação lavrada não se
    reescreve — o que muda é o aviso, e a auditoria (que a rota grava, fora
    da transação) diz quem completou e quando. A tarefa que avisava fecha.
    """
    bd = banco(con)
    aviso = _aviso_para_gravar(bd, aviso_id)
    if not aviso:
        raise AvisoError(f"Aviso {aviso_id} não encontrado.")
    nome_do_aviso = f"{aviso['numero']}/{aviso['ano']}"
    if aviso["situacao"] != "ENTREGUE":
        raise AvisoError(
            f"O aviso {nome_do_aviso} está {aviso['situacao']}. Quem recebeu "
            f"se completa no aviso ENTREGUE.")
    nome = " ".join(str(recebido_por or "").split())
    if sum(1 for c in nome if c.isalpha()) < PISO_DO_NOME:
        raise AvisoError("Escreva o nome de quem recebeu, como está no canhoto "
                         "assinado.")
    if not comprovantes(bd, aviso_id):
        raise AvisoError(
            f"O aviso {nome_do_aviso} não tem o comprovante anexado. Anexe "
            f"primeiro o canhoto assinado — o nome de quem recebeu se lê nele.")
    antes = " ".join(str(aviso["recebido_por"] or "").split())
    afirmacoes: list[dict] = []
    if antes:
        if antes.casefold() == nome.casefold():
            raise AvisoError(f"O aviso {nome_do_aviso} já diz que quem recebeu "
                             f"foi {antes}.")
        afirmacoes.append(PROVA.vencer_ou_recusar(
            PROVA.REGRA_CORRECAO_DO_RECEBEDOR,
            f"O aviso {nome_do_aviso} já diz que quem recebeu foi «{antes}»; "
            f"trocar o nome registrado exige afirmação expressa.",
            afirmacao, erro=AvisoError))
    bd.escrever("UPDATE pt_avisos SET recebido_por = %s WHERE id = %s",
                (nome, int(aviso_id)))
    fechadas = []
    if bd.tem_tabela("tasks"):
        for t in bd.ler(
                """SELECT id, status FROM tasks
                    WHERE source_type = %s AND source_ref = %s
                      AND status NOT IN ('CONCLUIDA', 'CANCELADA')
                    ORDER BY id""",
                (TAREFA_SEM_RECEBEDOR, f"pt_avisos:{int(aviso_id)}")):
            bd.escrever("""UPDATE tasks SET status = 'CONCLUIDA',
                                  completed_at = %s, updated_at = %s
                            WHERE id = %s""", (agora, agora, t["id"]))
            if bd.tem_tabela("task_history"):
                bd.escrever(
                    """INSERT INTO task_history (task_id, ts, user_id, action,
                           old_value, new_value, note)
                       VALUES (%s, %s, NULL, 'ALTEROU_STATUS', %s,
                               'CONCLUIDA', %s)""",
                    (t["id"], agora, t["status"],
                     f"Nome de quem recebeu completado no aviso "
                     f"{nome_do_aviso} — fechada sozinha."))
            fechadas.append(int(t["id"]))
    return {"aviso_id": int(aviso_id), "recebido_por": nome,
            "antes": antes or None, "afirmacoes": afirmacoes,
            "tarefas_fechadas": fechadas}


# ------------------------------------------- o canhoto que volta ao cartório
#
# PEDIDO DO OFICIAL, 15/10/2026: «ter uma parte destacável para o cartório
# levar apenas a confirmação de recebimento, com a assinatura, e não precisar
# imprimir duas vezes todas as folhas». O aviso fica com o devedor; o canhoto,
# destacado, volta assinado — e é ELE que se escaneia no PDF com várias
# intimações. Por isso o QR do aviso mora no canhoto, e não no alto da folha.
#
# O QUE ELE LEVA é o que prova o recebimento no endereço (CN-MA art. 921,
# § 6º, I): de que aviso é, de que título, e quem recebeu, quando e com que
# assinatura. O nome e o documento de quem recebeu ficam no PAPEL — o sistema
# não os digita (decisão do oficial, 15/10/2026: «acho que não precisa»).


def canhoto_do_aviso(con: sqlite3.Connection, aviso: Any) -> dict:
    """O comprovante destacável do aviso. Só calcula."""
    import protesto_pecas as PECAS
    av = dict(aviso)
    tit = PT.titulo(banco(con), int(av["titulo_id"]))
    if not tit:
        raise AvisoError("O título deste aviso não foi encontrado.")
    t = dict(tit)
    especie = PECAS.vocabulario(con, "PT_ESPECIES").get(
        str(t.get("especie") or "").upper(), t.get("especie") or "")
    # O TEXTO DO CANHOTO SÃO AS PEÇAS `PT_AVISO_CANHOTO_*` (LF06E, 19/10/2026),
    # que o oficial edita na tela de Modelos: uma linha do papel por linha da
    # peça. Daqui saem os valores e QUANTAS tentativas o papel traz.
    rotulo = PECAS.vocabulario(con, "PT_AVISO_ROTULOS")
    return {
        "titulo": _papel(con, "PT_AVISO_CANHOTO_TITULO"),
        "identificacao": _papel(
            con, "PT_AVISO_CANHOTO_IDENTIFICACAO", numero=av["numero"],
            ano=av["ano"], protocolo=t.get("protocolo") or rotulo["sem_protocolo"],
            devedor=av.get("devedor_nome") or "", especie=especie,
            numero_titulo=t.get("numero_titulo") or rotulo["sem_numero"],
            valor=_reais(t.get("saldo_centavos") or t.get("valor_centavos")),
        ).split("\n"),
        # TRÊS LINHAS, E CURTAS: o canhoto cabe no pé da MESMA folha do aviso
        # (medido no PDF do LibreOffice: com cinco linhas ele passava para a
        # segunda folha, que é exatamente o que o pedido quer evitar).
        "campos": _papel(con, "PT_AVISO_CANHOTO_CAMPOS").split("\n"),
        # AS TENTATIVAS (15/10/2026): «um campo de tentativa, onde se coloca
        # quando tentou, para fundamentar a expedição de edital». São o
        # rastro que o art. 922 pede — «esgotados todos os meios» — escrito
        # por quem foi ao endereço, no mesmo papel que volta ao cartório.
        "tentativas_titulo": _papel(con, "PT_AVISO_CANHOTO_TENTATIVAS_TITULO"),
        "tentativas": [_papel(con, "PT_AVISO_CANHOTO_TENTATIVA", n=n)
                       for n in (1, 2)],
    }


def __getattr__(nome: str):
    """Os nomes do texto de fábrica do aviso, lidos da base dos padrões.

    O TEXTO DO AVISO, DO EDITAL E DO CANHOTO SAIU DESTE MÓDULO NO LF06E
    (19/10/2026) e mora em `modelos_padrao/protesto/`. Quem pede o nome dele
    (`AVISO_DE_INTIMACAO`, `EDITAL_DE_INTIMACAO`...) recebe o padrão da base — o
    MESMO que o papel imprime. Nome que não é de papel continua sendo
    `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
