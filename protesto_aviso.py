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


def prazo_limite(con: sqlite3.Connection, titulo: Any) -> str | None:
    """O dia previsto para a lavratura — 3 dias úteis da protocolização. Só LÊ.

    `None` quando o protocolo não diz a data: prazo inventado num papel que
    vai ao devedor é pior que a recusa.
    """
    from datetime import date as _date
    from ri_schema import ler_feriados_locais, soma_dias_uteis
    s = "".join(c for c in str(dict(titulo).get("protocolo") or "") if c.isdigit())
    if len(s) < 6:
        return None
    try:
        dia = _date(2000 + int(s[:2]), int(s[2:4]), int(s[4:6]))
    except ValueError:
        return None
    linha = con.execute("SELECT value FROM settings WHERE key='ri_feriados_locais'"
                        ).fetchone()
    feriados = ler_feriados_locais((linha[0] if linha else "") or "")
    return soma_dias_uteis(dia, 3, feriados).isoformat()


def _br(iso: Any) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) == 10 and s[4] == "-" else s


def montar_teor_do_aviso(con: sqlite3.Connection, aviso: Any, *,
                         sv: dict) -> str:
    """O texto do aviso de intimação, com os itens dos arts. 920 e 923. Só calcula.

    O endereço é o que CONGELOU no aviso, e não o do cadastro de hoje.
    """
    import protesto_cra as CRA
    av = dict(aviso)
    tit = PT.titulo(con, int(av["titulo_id"]))
    if not tit:
        raise AvisoError("O título deste aviso não foi encontrado.")
    t = dict(tit)
    horario = (con.execute("SELECT value FROM settings WHERE key=?",
                           (CHAVE_DO_HORARIO,)).fetchone() or [""])[0] or ""
    if not horario.strip():
        raise AvisoError(
            "O aviso precisa do horário de funcionamento do tabelionato "
            "(Código de Normas, art. 920), e ele não está configurado. "
            "Informe-o em Administrativo → Configurações "
            f"(«{CHAVE_DO_HORARIO}»).")
    limite = prazo_limite(con, t)
    if not limite:
        raise AvisoError(
            f"O protocolo do título ({t.get('protocolo') or 'vazio'}) não diz a "
            f"data da protocolização, e sem ela não há prazo-limite — o aviso "
            f"não sai sem o prazo (Código de Normas, art. 920).")
    especie = CRA.ESPECIES.get(str(t.get("especie") or "").upper(),
                               t.get("especie") or "")
    aceite = {"A": "com aceite", "N": "sem aceite"}.get(
        str(t.get("aceite") or "").upper()[:1], "aceite não informado")
    endereco = ", ".join(x for x in (av.get("endereco"), av.get("bairro"),
                                     av.get("cidade") and (
                                         f"{av['cidade']}/{av.get('uf') or ''}"),
                                     av.get("cep") and f"CEP {av['cep']}") if x)
    credor = (t.get("cedente_nome") or "").strip()
    if credor and t.get("cedente_documento"):
        credor += f", CPF/CNPJ {formatar_documento(t['cedente_documento'])}"
    apresentante = (t.get("apresentante_nome") or t.get("apresentante_codigo")
                    or "").strip()
    casa = str(sv.get("unit_name") or "").strip()
    linhas = [
        "AVISO DE INTIMAÇÃO PARA PAGAMENTO",
        "",
        f"Aviso n. {av['numero']}/{av['ano']} — Protocolo n. {t.get('protocolo')}",
        "",
        (f"Fica V. Sa. INTIMADO(A) a pagar, ou a apresentar as razões que tiver, "
         f"até {_br(limite)}, o título abaixo apresentado para protesto neste "
         f"tabelionato. Não havendo pagamento nem manifestação até essa data, "
         f"o título será protestado na forma da Lei nº 9.492/1997."),
        "",
        f"Devedor: {av.get('devedor_nome') or ''}"
        + (f", CPF/CNPJ {formatar_documento(av['devedor_documento'])}"
           if av.get("devedor_documento") else ""),
        f"Endereço: {endereco or 'não informado pelo apresentante'}",
        f"Título: {especie}, n. {t.get('numero_titulo') or 'sem número'}",
        f"Valor: R$ {_reais(t.get('saldo_centavos') or t.get('valor_centavos'))}"
        + (f" — vencimento em {_br(t['data_vencimento'])}"
           if t.get("data_vencimento") else ""),
        f"Aceite: {aceite}",
        f"Credor (sacador/favorecido): {credor or 'não informado'}",
        f"Apresentante: {apresentante or 'não informado'}",
        f"Prazo-limite para pagamento: {_br(limite)}",
        "",
        (f"{casa} — {sv.get('endereco_completo') or ''}. Telefone "
         f"{sv.get('serventia_telefone') or sv.get('telefone') or ''}. "
         f"Horário de funcionamento: {horario.strip()}."),
    ]
    return "\n".join(linhas)


def montar_teor_do_edital(*, aviso: sqlite3.Row | dict, titulo: sqlite3.Row,
                          sv: dict, hoje: str,
                          data_extenso: str | None = None,
                          limite: str | None = None) -> str:
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
        # O EDITAL SE LIMITA AO QUE O CN-MA, art. 922, § 3º, MANDA: devedor,
        # identificação do título, valor, PRAZO-LIMITE e o tabelionato com
        # endereço e telefone. Até 14/10/2026 ele dizia «no prazo legal» sem
        # data e trazia apresentante e credor, que o parágrafo não pede.
        ("do apontamento para protesto do título abaixo, para que, até "
         f"{_br(limite) if limite else 'o prazo legal'}, compareça a esta "
         "Serventia a fim de pagá-lo, ou, querendo, apresente as razões que "
         "tiver:"),
        "",
        f"Protocolo: {protocolo or 'A CONFERIR'}",
        f"Título: {titulo['numero_titulo'] or 'sem número'}"
        + (f" — espécie {titulo['especie']}" if titulo["especie"] else ""),
        f"Valor: R$ {valor}",
        f"Prazo-limite para pagamento: {_br(limite)}" if limite else "",
        "",
        ("Decorrido o prazo sem manifestação, o título será protestado na "
         "forma da Lei nº 9.492, de 10 de setembro de 1997."),
        "",
        (f"{casa} — {sv.get('endereco_completo') or ''}. Telefone "
         f"{sv.get('serventia_telefone') or sv.get('telefone') or ''}."),
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
    aviso = ler(con, aviso_id)
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
    caminho = depois_da_nao_entrega(con, aviso)
    if caminho["edital"] == "RECUSADO":
        raise AvisoError(caminho["frase"])
    porque = " ".join(str(justificativa or "").split())
    if caminho["edital"] == "JUSTIFICAR" and len(porque) < 10:
        raise AvisoError(
            caminho["frase"] + " Para publicar o edital agora, escreva o "
            "motivo (pelo menos dez letras) — ele fica no ato da intimação.")
    sobre_a_resolve = caminho["resumo"] + (f"; motivo: {porque}" if porque
                                           else "")

    tit = PT.titulo(con, int(aviso["titulo_id"]))
    if not tit:
        raise AvisoError(f"Título {aviso['titulo_id']} não encontrado.")

    ano = int(str(hoje)[:4])
    numero = proximo_numero_do_edital(con, ano)
    teor = montar_teor_do_edital(aviso=aviso, titulo=tit, sv=sv, hoje=hoje,
                                 limite=prazo_limite(con, tit),
                                 data_extenso=data_extenso)
    codigo = f"ED-{ano}-{numero:04d}"

    lavrado = PT.lancar_intimacao(
        con, int(aviso["titulo_id"]), modo="EDITAL", agora=agora,
        usuario=usuario, codigo_edital=codigo,
        comprovante=(f"Aviso {aviso['numero']}/{aviso['ano']} não entregue: "
                     f"{motivo_rotulo(aviso['motivo'])}; Intimação Digital: "
                     f"{sobre_a_resolve}"))
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

    SO TITULO AINDA APONTADO (15/10/2026): o que ja foi intimado por outro
    caminho — a Intimacao Digital confirmada, ou um segundo aviso entregue —
    nao espera edital, e ficar na lista convidaria a publicar um edital que
    nao cabe.
    """
    return [dict(r) for r in con.execute(
        """SELECT a.*, t.numero_titulo, t.protocolo, t.saldo_centavos
             FROM pt_avisos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.situacao='NAO_ENTREGUE' AND t.situacao='APONTADO'
            ORDER BY a.entrega_em, a.id
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
#   o resto — está correndo: o edital espera, ou vai com o motivo escrito.
RESOLVE_CONFIRMOU = frozenset({"INTIMADO"})
RESOLVE_PAGOU = frozenset({"PAGO"})
RESOLVE_NAO_DEU = frozenset({"NAO_ENRIQUECIDO", "SEM_RESPOSTA", "REJEITADO",
                             "CANCELADO"})


def _ultima_na_resolve(con: sqlite3.Connection, titulo_id: int) -> dict | None:
    """A última Intimação Digital deste título, em PRODUÇÃO. Só LÊ."""
    if not con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='rs_intimacoes'").fetchone():
        return None
    import centrais_cred as CRED
    linha = con.execute(
        """SELECT id, identificador, intimacao_id, estado, estado_em,
                  enviada_em
             FROM rs_intimacoes
            WHERE titulo_id = ? AND ambiente = ?
            ORDER BY id DESC LIMIT 1""",
        (int(titulo_id), CRED.PRODUCAO)).fetchone()
    return dict(linha) if linha else None


def depois_da_nao_entrega(con: sqlite3.Connection, aviso: Any) -> dict:
    """O próximo passo do aviso que não foi entregue. Só LÊ.

    Devolve `passo` (RESOLVE, AGUARDAR, LAVRAR_DIGITAL, PAGO ou EDITAL),
    `edital` (LIBERADO, JUSTIFICAR ou RECUSADO), a `frase` para a tela e o
    `resumo` que vai escrito no ato da intimação por edital.

    **NÃO JULGA PRAZO.** Quando a Resolve ainda está correndo, o edital não é
    recusado: ele pede o motivo escrito. Quem decide se dá para esperar a
    plataforma dentro do tríduo é o oficial — a regra de 24/08/2026.
    """
    import resolve_intimacao as RS
    titulo_id = int(aviso["titulo_id"])
    tit = con.execute(
        """SELECT t.id, t.situacao, t.chave_cenprot,
                  (SELECT d.nome FROM pt_devedores d
                    WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1)
                      AS devedor_nome
             FROM pt_titulos t WHERE t.id = ?""", (titulo_id,)).fetchone()
    classe = (RS.situacao_do_titulo(dict(tit)) if tit
              else {"pode_ir": False, "porque_nao": "o título não existe"})
    ultima = _ultima_na_resolve(con, titulo_id)
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
    aviso = ler(con, aviso_id)
    if not aviso:
        raise AvisoError(f"Aviso {aviso_id} não encontrado.")
    if aviso["situacao"] != "NAO_ENTREGUE":
        raise AvisoError(
            f"O aviso {aviso['numero']}/{aviso['ano']} está "
            f"{aviso['situacao']}. A intimação digital entra no lugar do "
            f"aviso que não foi entregue.")
    caminho = depois_da_nao_entrega(con, aviso)
    if caminho["passo"] != "LAVRAR_DIGITAL":
        raise AvisoError(
            "A Resolve ainda não confirmou a intimação deste devedor. "
            + caminho["frase"])
    ultima = caminho["resolve"] or {}
    quando = str(ultima.get("estado_em") or "")[:10]
    lavrado = PT.lancar_intimacao(
        con, int(aviso["titulo_id"]), modo="PESSOAL", digital=True,
        agora=agora, usuario=usuario,
        comprovante=(f"Intimação Digital (Resolve) {ultima.get('identificador')}"
                     f", confirmada pela plataforma"
                     + (f" em {_br(quando)}" if quando else "")
                     + f" (CN-MA art. 921, § 6º, II); aviso "
                       f"{aviso['numero']}/{aviso['ano']} não entregue: "
                       f"{motivo_rotulo(aviso['motivo'])}"))
    con.execute("UPDATE pt_avisos SET ato_id=? WHERE id=?",
                (lavrado["ato_id"], int(aviso_id)))
    return {"aviso_id": int(aviso_id), "ato_id": lavrado["ato_id"],
            "identificador": ultima.get("identificador")}


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
    return con.execute(
        """SELECT 1 FROM attachments
            WHERE entity_type=? AND entity_id=? AND sha256=?""",
        (ENTIDADE_DO_COMPROVANTE, int(aviso_id),
         hashlib.sha256(bytes(conteudo or b"")).hexdigest())).fetchone() \
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
                        usuario_id: int | None = None) -> dict:
    """Anexa ao aviso o comprovante da intimação entregue. ESCREVE, e grava
    arquivo em disco.

    **SÓ AVISO ENTREGUE.** O comprovante prova uma entrega; anexá-lo a um
    aviso sem entrega registrada faria o papel dizer uma coisa e o sistema
    outra. **E NÃO SE SOBRESCREVE**: o segundo arquivo do mesmo aviso é outro
    anexo — a frente e o verso, ou a via corrigida —, e o mesmo arquivo duas
    vezes é recusado pelo conteúdo.
    """
    aviso = ler(con, aviso_id)
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
    if con.execute(
            """SELECT id FROM attachments
                WHERE entity_type=? AND entity_id=? AND sha256=?""",
            (ENTIDADE_DO_COMPROVANTE, int(aviso_id), sha)).fetchone():
        raise AvisoError("Este arquivo já está anexado a este aviso.")

    destino = (Path(pasta_de_arquivos) / "Protesto" / "Intimacoes"
               / str(int(aviso["titulo_id"])))
    destino.mkdir(parents=True, exist_ok=True)
    n = len(comprovantes(con, aviso_id)) + 1
    arquivo = destino / f"aviso-{aviso['numero']}-{aviso['ano']}-{n}{ext}"
    while arquivo.exists():
        n += 1
        arquivo = destino / f"aviso-{aviso['numero']}-{aviso['ano']}-{n}{ext}"
    arquivo.write_bytes(conteudo)
    cur = con.execute(
        """INSERT INTO attachments(entity_type, entity_id, original_name,
               stored_name, stored_path, sha256, size_bytes, description,
               uploaded_by, uploaded_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (ENTIDADE_DO_COMPROVANTE, int(aviso_id), nome_limpo or arquivo.name,
         arquivo.name, str(arquivo), sha, len(conteudo),
         (f"Comprovante da intimação — aviso {aviso['numero']}/{aviso['ano']}"
          if aviso["situacao"] == "ENTREGUE" else
          f"Comprovante da tentativa de entrega — aviso "
          f"{aviso['numero']}/{aviso['ano']}"),
         usuario_id, agora))
    return {"anexo_id": int(cur.lastrowid), "aviso_id": int(aviso_id),
            "nome": arquivo.name}


def comprovantes(con: sqlite3.Connection, aviso_id: int) -> list[dict]:
    """Os comprovantes daquele aviso. Só LÊ."""
    return [dict(r) for r in con.execute(
        """SELECT id, original_name, size_bytes, uploaded_at
             FROM attachments WHERE entity_type=? AND entity_id=?
            ORDER BY id""", (ENTIDADE_DO_COMPROVANTE, int(aviso_id)))]


def entregues(con: sqlite3.Connection, limite: int = 100) -> list[dict]:
    """Os avisos entregues, os SEM comprovante primeiro. Só LÊ.

    A lista de trabalho do upload: o que foi entregue e ainda não tem o papel
    anexado vem no alto, porque é o que a correição pergunta.
    """
    linhas = [dict(r) for r in con.execute(
        """SELECT a.*, t.numero_titulo, t.protocolo,
                  (SELECT COUNT(*) FROM attachments x
                    WHERE x.entity_type = ? AND x.entity_id = a.id)
                      AS n_comprovantes
             FROM pt_avisos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.situacao = 'ENTREGUE'
            ORDER BY CASE WHEN (SELECT COUNT(*) FROM attachments x
                                 WHERE x.entity_type = ?
                                   AND x.entity_id = a.id) = 0
                          THEN 0 ELSE 1 END,
                     a.entrega_em DESC, a.id DESC
            LIMIT ?""",
        (ENTIDADE_DO_COMPROVANTE, ENTIDADE_DO_COMPROVANTE, int(limite)))]
    for linha in linhas:
        linha["comprovantes"] = comprovantes(con, linha["id"])
    return linhas


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
    import protesto_cra as CRA
    av = dict(aviso)
    tit = PT.titulo(con, int(av["titulo_id"]))
    if not tit:
        raise AvisoError("O título deste aviso não foi encontrado.")
    t = dict(tit)
    especie = CRA.ESPECIES.get(str(t.get("especie") or "").upper(),
                               t.get("especie") or "")
    return {
        "titulo": "COMPROVANTE DE RECEBIMENTO DA INTIMAÇÃO",
        "identificacao": [
            f"Aviso n. {av['numero']}/{av['ano']} — Protocolo n. "
            f"{t.get('protocolo') or '—'}",
            f"Devedor: {av.get('devedor_nome') or ''}",
            f"Título: {especie}, n. {t.get('numero_titulo') or 'sem número'} "
            f"— R$ {_reais(t.get('saldo_centavos') or t.get('valor_centavos'))}",
        ],
        # TRÊS LINHAS, E CURTAS: o canhoto cabe no pé da MESMA folha do aviso
        # (medido no PDF do LibreOffice: com cinco linhas ele passava para a
        # segunda folha, que é exatamente o que o pedido quer evitar).
        "campos": [
            "Recebido em ___/___/______ às ___:___   Assinatura: "
            "__________________________",
            "Nome legível: _____________________________   Documento: "
            "_______________",
            "Relação com o devedor: ( ) o próprio ( ) outra: ___________   "
            "Entregador: _______________",
        ],
        # AS TENTATIVAS (15/10/2026): «um campo de tentativa, onde se coloca
        # quando tentou, para fundamentar a expedição de edital». São o
        # rastro que o art. 922 pede — «esgotados todos os meios» — escrito
        # por quem foi ao endereço, no mesmo papel que volta ao cartório.
        "tentativas_titulo": ("TENTATIVAS DE ENTREGA — preencha se não "
                              "entregou (fundamenta o edital)"),
        "tentativas": [
            f"{n}ª: ___/___/___ ___:___ ( ) ausente ( ) recusou ( ) fora da "
            f"zona ( ) outro ________ Entregador: _________"
            for n in (1, 2)
        ],
    }
