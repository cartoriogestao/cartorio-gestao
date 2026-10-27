"""O agente do Protesto — regularidade dos atos, prazos, intimações, protestos devidos e indevidos.

    «Agente de protesto: verificara a regularidade dos atos, cumprimento de
     prazos, fiscalizacao de intimacoes, protestos devidos e indevidos.»
                                                       — o oficial, 09/10/2026

SÃO DUAS FONTES, E A PRIMEIRA É A QUE HOJE TEM O DIA DE VERDADE
    Medido em 09/10/2026 na produção (só leitura):

    | fonte                                   | o que tem                                  |
    |-----------------------------------------|--------------------------------------------|
    | `pt_*` do banco do sistema              | só o acervo do E-Ofício: 1.374 títulos,    |
    |                                         | último ato em **10/09/2026**, nenhuma      |
    |                                         | remessa, aviso ou edital lançado aqui      |
    | a pasta da CRA da serventia            | **remessas, confirmações e andamentos de   |
    |                                         | 07/10/2026** — o protesto segue vivo, e    |
    |                                         | é praticado fora do sistema                |

    Por isso o agente lê **os arquivos da CRA** — que são o rastro oficial do
    que a casa recebeu e respondeu — e o banco. Fiscalizar só o banco daria a
    casa por quieta enquanto 18 títulos apontados entre 01 e 07/10 esperam
    resposta (medido no mesmo dia).

AS RÉGUAS, E DE ONDE CADA UMA VEIO
    O prazo **não** é palpite do programa: é o texto que a própria inspeção
    0000524 citou ao fiscalizar esta casa (relatório, anexo II, protesto):

    - **protocolização** em até 24 horas úteis da apresentação (CN-MA art. 907);
    - **intimação** expedida até o primeiro dia útil após o apontamento
      (CN-MA art. 919);
    - **protesto** registrado em três dias úteis da protocolização, excluído o
      dia do protocolo (Lei 9.492/1997, art. 12, caput e § 1º) — e foi «intimação
      por edital expedida fora do tríduo legal» um dos achados da inspeção;
    - revogada a sustação, protesto até o primeiro dia útil seguinte ao
      **recebimento** da revogação (art. 17, § 2º);
    - o retorno à CRA até as 11h30 do dia útil seguinte (Roteiro das Centrais,
      `protesto_roteiro`).

    A decisão do oficial de 24/08/2026 — «só registrar, sem contar prazo» — vale
    para as funções que LAVRAM (`protesto.py`): nenhuma delas protesta sozinha
    por causa de uma conta. Este agente não lavra nada: **ele conta e aponta**,
    e quem decide o que fazer é quem assina. Foi o pedido de 09/10/2026.

O QUE É «PROTESTO INDEVIDO» PARA ESTE AGENTE — só o que é objetivo
    - protestado depois de pago, retirado ou desistido;
    - protestado com sustação judicial em vigor;
    - protestado antes do vencimento do título;
    - protestado no mesmo dia do apontamento ou da intimação (o devedor não
      teve o prazo da lei para pagar);
    - protestado sem intimação registrada;
    - protestado duas vezes.
    E, do outro lado, o **protesto devido não lavrado**: tríduo vencido, sem
    pagamento, retirada ou sustação, e nenhuma resposta à Central.

    Mérito do título (prescrição, causa da dívida, aceite) não é objetivo, e
    não está aqui: é qualificação do tabelião.

O CORTE DE 10/09/2026 VALE AQUI COMO NO RESTO DO GESTOR
    Ato anterior à implantação não vira tarefa (ordem do oficial). O que é
    anterior e continua errado aparece num achado só, de resumo, sem tarefa.

O QUE NÃO FAZ
    Não lavra, não sela, não cobra, não manda arquivo à Central e não mexe em
    título. Só lê.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import gestor_conferencia as GC
from bd_nativo import banco

SETOR = "PROTESTO"

#: A pasta onde o balcão guarda os arquivos que troca com a CRA. Configuração
#: (`settings`) ganha do código: trocar de pasta não pode exigir versão nova.
CHAVE_PASTA_CRA = "protesto_pasta_cra"
# SEM PADRÃO NO CÓDIGO desde 09/10/2026 (sanitização para o código aberto): a
#   pasta é desta instalação, e o valor da casa vai para `settings` pelo perfil
#   local (`tools/migrar_settings_serventia_b0.py`). Vazio = não configurada.
PASTA_CRA_PADRAO = ""
#: Só o que é deste exercício e do anterior se lê — o resto é acervo.
ANOS_LIDOS = 2

#: As ocorrências do retorno que encerram o título na Central (protesto_cra).
#: `C` é o «protestado» que o E-Ofício desta casa escreve (1.106 de 1.107).
PROTESTADO = frozenset({"2", "C"})
PAGO_OU_RETIRADO = frozenset({"1", "3", "7"})
ENCERRA = PROTESTADO | PAGO_OU_RETIRADO | frozenset({"5", "A"})
SUSTADO = "4"

#: A conta é a que a inspeção fez no protocolo 2603190001: protocolizado numa
#: quinta, o tríduo começa no dia útil seguinte e termina no terceiro.
ART_12 = ("Lei 9.492/1997, art. 12, caput e § 1º, e CN-MA art. 913, I (três dias úteis "
          "da protocolização, excluído o dia do protocolo)")
ART_907 = "CN-MA art. 907 (protocolização em até 24 horas úteis da apresentação)"
ART_919 = "CN-MA art. 919 (intimação até o primeiro dia útil após o apontamento)"
ROTEIRO = "Roteiro das Centrais de Protesto (retorno à CRA até 11h30)"

#: As regras que são medidas e relatadas, mas não viram tarefa: ato já
#: praticado fora do prazo (não há como desfazer), decisão do oficial, ou o
#: rastro do E-Ofício anterior ao corte.
REGRAS_SEM_TAREFA = frozenset({
    "PROTESTO_PROTOCOLO_TARDIO", "PROTESTO_FORA_DO_TRIDUO",
    "PROTESTO_RETORNO_TARDIO", "PROTESTO_INTIMACAO_TARDIA",
    "PROTESTO_FORA_DO_SISTEMA", "PROTESTO_MODELO_DO_TERMO",
    "PROTESTO_ANTES_DO_CORTE", "PROTESTO_PAGAMENTO_SEM_LIVRO",
})

ROTULOS = {
    "PROTESTO_SEM_RESPOSTA": "Protesto — títulos com o tríduo vencido e sem resposta à CRA",
    "PROTESTO_REMESSA_SEM_CONFIRMACAO": "Protesto — títulos recebidos da CRA e não apontados",
    "PROTESTO_DESISTENCIA_SEM_BAIXA": "Protesto — desistências recebidas sem baixa na Central",
    "PROTESTO_INDEVIDO": "Protesto — protestos que não deviam ter saído",
    "PROTESTO_DOCUMENTO_DO_DEVEDOR": "Protesto — devedor com CPF/CNPJ que não fecha",
    "PROTESTO_EDITAL_SEM_DILIGENCIA": "Protesto — edital sem tentativa de entrega registrada",
    "PROTESTO_TITULO_PARADO": "Protesto — títulos parados no sistema depois do tríduo",
    "PROTESTO_SUSTACAO_REVOGADA": "Protesto — sustação revogada e protesto não lavrado",
    "PROTESTO_CERTIDAO_NEGATIVA_INDEVIDA": "Protesto — certidão negativa sobre quem tinha protesto",
    "PROTESTO_PROTOCOLO_TARDIO": "Protesto — protocolização fora das 24 horas úteis",
    "PROTESTO_FORA_DO_TRIDUO": "Protesto — protestos lavrados depois do tríduo",
    "PROTESTO_RETORNO_TARDIO": "Protesto — retornos enviados depois do dia útil seguinte",
    "PROTESTO_INTIMACAO_TARDIA": "Protesto — intimações expedidas depois do 1º dia útil",
    "PROTESTO_FORA_DO_SISTEMA": "Protesto — o protesto está sendo praticado fora do sistema",
    "PROTESTO_MODELO_DO_TERMO": "Protesto — o modelo do termo traz o motivo que a inspeção vedou",
    "PROTESTO_ANTES_DO_CORTE": "Protesto — pendências anteriores a 10/09/2026",
    "PROTESTO_PAGAMENTO_SEM_LIVRO": "Protesto — pagamentos sem lugar no Livro de Pagamentos",
    "PROTESTO_PASTA_CRA": "Protesto — pasta dos arquivos da CRA inacessível",
}


# ---------------------------------------------------------------- miúdos

def _tem_tabela(con, nome: str) -> bool:
    return banco(con).tem_tabela(nome)


def _configuracao(con, chave: str, padrao: str = "") -> str:
    if not _tem_tabela(con, "settings"):
        return padrao
    r = banco(con).um("SELECT value FROM settings WHERE key=%s", (chave,))
    return (r["value"] or "").strip() if r and (r["value"] or "").strip() else padrao


def _feriados(con) -> set[date]:
    """Os feriados locais que o RI já usa — a casa tem uma lista só."""
    from ri_schema import ler_feriados_locais
    return ler_feriados_locais(_configuracao(con, "ri_feriados_locais", ""))


def _uteis(inicio: date, dias: int, feriados) -> date:
    from ri_schema import soma_dias_uteis
    return soma_dias_uteis(inicio, dias, feriados)


def _d(valor) -> date | None:
    return GC._dia(valor)


def _br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _data_do_protocolo(protocolo, reserva=None) -> date | None:
    """O protocolo desta casa é AAMMDD + sequencial do dia (928 de 931 medidos).
    Sem ele legível, vale a data de entrada que o arquivo traz."""
    s = "".join(ch for ch in str(protocolo or "") if ch.isdigit())
    if len(s) >= 6:
        try:
            return date(2000 + int(s[:2]), int(s[2:4]), int(s[4:6]))
        except ValueError:
            pass
    return _d(reserva)


# ------------------------------------------------- 1. o fluxo da CRA, lido

def _pasta_cra(con) -> Path | None:
    # VAZIO NÃO É «A PASTA ATUAL»: `Path("")` é `.`, e o agente leria a pasta
    #   do sistema como se fosse a da CRA.
    valor = _configuracao(con, CHAVE_PASTA_CRA, PASTA_CRA_PADRAO)
    return Path(valor) if valor else None


_EXTENSAO_DA_CRA = re.compile(r"\.\d{3}$")


def ler_fluxo_da_cra(pasta: Path, hoje: date) -> dict:
    """Lê os arquivos da CRA da pasta. SÓ LÊ. Devolve os títulos por chave.

    Remessa (B), confirmação (C), retorno (R) e desistência (DP). A extensão
    `.AAs` diz o ano (261 = 2026, lote 1); lê-se este ano e o anterior. O mesmo
    arquivo salvo duas vezes («B9010510 (1).261») conta uma vez: o que se junta
    é o título, e não o arquivo.
    """
    import protesto_arquivo as PA
    import protesto_desistencia as PD
    import protesto_remessa as PR

    anos = {str((hoje.year - k) % 100).zfill(2) for k in range(ANOS_LIDOS)}
    fluxo = {"remessa": {}, "confirmado": {}, "retorno": defaultdict(list),
             "desistencia": {}, "respondido": set(), "arquivos": 0, "ilegiveis": []}
    for f in sorted(pasta.rglob("*")):
        if not f.is_file() or not _EXTENSAO_DA_CRA.search(f.name):
            continue
        if f.suffix[1:3] not in anos or f.stat().st_size == 0:
            continue
        try:
            bruto = f.read_bytes()
        except OSError as erro:
            fluxo["ilegiveis"].append(f"{f.name}: {erro}")
            continue
        fluxo["arquivos"] += 1
        mtime = datetime.fromtimestamp(f.stat().st_mtime).date()
        # A DESISTÊNCIA TEM 127 POSIÇÕES, e não 600: o tamanho da primeira linha
        # decide o leitor — o de 600 recusaria o arquivo inteiro.
        primeira = bruto.replace(b"\r", b"").split(b"\n", 1)[0]
        if len(primeira) == PD.TAMANHO_DO_REGISTRO:
            try:
                d = PD.ler(bruto)
            except Exception as erro:                   # noqa: BLE001
                fluxo["ilegiveis"].append(f"{f.name}: {erro}")
                continue
            dia = _d((d.get("cabecalho") or {}).get("dia")) or mtime
            for t in d.get("titulos", []):
                p = str(t.get("protocolo") or "").strip()
                if p:
                    fluxo["desistencia"].setdefault(p, {"dia": dia, "arquivo": f.name})
            continue
        try:
            lotes = PR.separar(bruto)
        except Exception as erro:                       # noqa: BLE001
            fluxo["ilegiveis"].append(f"{f.name}: {erro}")
            continue
        for lote in lotes:
            try:
                a = PA.ler(lote)
            except Exception as erro:                   # noqa: BLE001
                fluxo["ilegiveis"].append(f"{f.name}: {erro}")
                continue
            cab = a.cabecalho
            apres = str(cab.get("codigo_do_apresentante") or "").strip()
            dia = _d(cab.get("data_do_movimento")) or mtime
            for t in a.titulos:
                nosso = str(t.get("nosso_numero") or "").strip()
                prot = str(t.get("protocolo") or "").strip()
                base = {"apresentante": apres, "nosso_numero": nosso,
                        "numero_do_titulo": t.get("numero_do_titulo"),
                        "devedor": t.get("devedor_nome"),
                        "documento": t.get("devedor_documento"),
                        "tipo_documento": t.get("devedor_tipo_de_documento"),
                        "vencimento": _d(t.get("data_de_vencimento")),
                        "especie": t.get("especie"), "arquivo": f.name}
                if a.tipo == "BFOSDTTPR":
                    fluxo["remessa"].setdefault((apres, nosso), {**base, "dia": dia})
                elif a.tipo == "SDTBFOCRT" and prot:
                    fluxo["confirmado"].setdefault(prot, {
                        **base, "dia_remessa": dia, "gerado_em": mtime,
                        "apontado": _data_do_protocolo(prot, t.get("data_entrada")),
                        "ocorrencia": str(t.get("ocorrencia") or "").strip()})
                elif a.tipo == "SDTBFORTP" and prot:
                    oc = str(t.get("ocorrencia") or "").strip()
                    quando = _d(t.get("data_ocorrencia"))
                    ja = fluxo["retorno"][prot]
                    if not any(r["ocorrencia"] == oc and r["data"] == quando for r in ja):
                        ja.append({"ocorrencia": oc, "data": quando, "enviado": dia,
                                   "arquivo": f.name, "apresentante": apres,
                                   "apontado": _data_do_protocolo(prot, t.get("data_entrada"))})
                # QUALQUER ARQUIVO QUE A CASA DEVOLVEU PROVA QUE O TÍTULO FOI
                # APONTADO — a confirmação nem sempre fica salva na pasta (medido:
                # a remessa 987 de 10/09 só aparece no andamento e no retorno).
                if a.tipo in ("SDTBFOCRT", "SDTBFORTP", "SDTBFOAND"):
                    fluxo["respondido"].add((apres, nosso))
                    fluxo["respondido"].add((apres, str(t.get("numero_do_titulo") or "").strip()))
    return fluxo


def _titulo_curto(t: dict, prot: str = "") -> str:
    partes = [f"protocolo {prot}" if prot else "",
              f"título {t.get('numero_do_titulo') or t.get('nosso_numero') or '?'}",
              f"apresentante {t.get('apresentante') or '?'}",
              (t.get("devedor") or "").strip()]
    return " · ".join(p for p in partes if p)


def _regras_do_fluxo(con, fluxo: dict, hoje: date, feriados) -> list[dict]:
    saida: list[dict] = []
    antigos: list[str] = []
    conf, ret = fluxo["confirmado"], fluxo["retorno"]

    # 1.a  TRÍDUO VENCIDO E NENHUMA RESPOSTA — o protesto devido não lavrado
    #      (ou lavrado e não informado: para o apresentante dá no mesmo).
    for prot, t in sorted(conf.items()):
        if t["ocorrencia"] not in ("", "0"):
            continue                         # devolvido já na confirmação
        rets = ret.get(prot, [])
        if any(r["ocorrencia"] in ENCERRA or r["ocorrencia"] == SUSTADO for r in rets):
            continue
        apontado = t["apontado"]
        if apontado is None:
            continue
        limite = _uteis(apontado, 3, feriados)
        resposta = _uteis(limite, 1, feriados)
        if hoje <= limite:
            continue
        if GC.antes_do_corte(apontado):
            antigos.append(f"{prot} (sem resposta desde {_br(apontado)})")
            continue
        gravidade = "VENCIDO" if hoje > resposta else "PRAZO"
        saida.append(GC._achado(
            f"PT_RESPOSTA:{prot}", "PROTESTO_SEM_RESPOSTA", gravidade, SETOR,
            f"Tríduo vencido em {_br(limite)} e nenhuma resposta à CRA — {_titulo_curto(t, prot)}",
            f"Apontado em {_br(apontado)} ({t['arquivo']}). Pago, retirado, sustado ou "
            f"protestado: o retorno à CRA saía até {_br(resposta)}, 11h30, e não há "
            "retorno deste protocolo na pasta da CRA. Se o protesto já foi lavrado, "
            "falta só o retorno; se não foi, o protesto é devido.",
            resposta, f"{ART_12}; {ROTEIRO}"))

    # 1.b  RECEBIDO DA CRA E NÃO APONTADO — nenhum protocolo para o título.
    respondido = fluxo["respondido"]
    for chave, t in sorted(fluxo["remessa"].items(), key=lambda x: x[1]["dia"]):
        if chave in respondido or (chave[0], str(t.get("numero_do_titulo") or "").strip()) \
                in respondido:
            continue
        limite = _uteis(t["dia"], 1, feriados)
        if hoje <= limite:
            continue
        if GC.antes_do_corte(t["dia"]):
            antigos.append(f"{t['nosso_numero']} (recebido em {_br(t['dia'])}, sem confirmação)")
            continue
        saida.append(GC._achado(
            f"PT_REMESSA:{chave[0]}:{chave[1]}", "PROTESTO_REMESSA_SEM_CONFIRMACAO",
            "VENCIDO", SETOR,
            f"Título recebido em {_br(t['dia'])} sem apontamento nem confirmação — "
            f"{_titulo_curto(t)}",
            f"Está na remessa {t['arquivo']} e em nenhuma confirmação da pasta. "
            "Apontar (ou devolver por irregularidade) e confirmar à CRA até 14h10.",
            limite, f"{ART_907}; Lei 9.492/1997, art. 5º"))

    # 1.c  PROTOCOLIZAÇÃO FORA DAS 24 HORAS ÚTEIS — ato já praticado, sem tarefa.
    tardios = []
    remessas = fluxo["remessa"]
    for prot, t in conf.items():
        r = remessas.get((t["apresentante"], t["nosso_numero"]))
        recebido = r["dia"] if r else t["dia_remessa"]
        if not (recebido and t["apontado"]) or GC.antes_do_corte(t["apontado"]):
            continue
        if t["apontado"] > _uteis(recebido, 1, feriados):
            tardios.append((t["apontado"], prot, recebido))
    if tardios:
        tardios.sort()
        exemplos = "; ".join(f"{p} (remessa {_br(r)}, apontado {_br(a)})"
                             for a, p, r in tardios[-8:])
        saida.append(GC._achado(
            "PT_PROTOCOLO_TARDIO", "PROTESTO_PROTOCOLO_TARDIO", "ATENCAO", SETOR,
            f"{len(tardios)} título(s) apontado(s) depois do primeiro dia útil da remessa",
            f"Os mais recentes: {exemplos}. A data do apontamento é a do protocolo "
            "(AAMMDD); a da remessa, a do cabeçalho do arquivo da CRA.",
            None, ART_907))

    # 1.d  PROTESTO INDEVIDO E PROTESTO FORA DO TRÍDUO, pelos retornos.
    fora_do_triduo = []
    for prot, rets in ret.items():
        protestos = sorted({r["data"] for r in rets if r["ocorrencia"] in PROTESTADO
                            and r["data"]})
        if not protestos:
            continue
        quando = protestos[0]
        t = conf.get(prot, {})
        apontado = t.get("apontado") or next((r["apontado"] for r in rets if r["apontado"]),
                                             None)
        motivos = []
        for r in rets:
            if r["ocorrencia"] in PAGO_OU_RETIRADO and r["data"] and r["data"] <= quando:
                motivos.append(f"a CRA recebeu «{r['ocorrencia']}» (pago/retirado) em "
                               f"{_br(r['data'])}, no arquivo {r['arquivo']}")
        desist = fluxo["desistencia"].get(prot)
        if desist and desist["dia"] <= quando:
            motivos.append(f"o credor desistiu em {_br(desist['dia'])} ({desist['arquivo']})")
        venc = t.get("vencimento")
        if venc and venc > quando:
            motivos.append(f"o título vencia em {_br(venc)}, depois do protesto")
        if apontado and quando <= apontado:
            motivos.append(f"protestado no dia do apontamento ({_br(apontado)}): o devedor "
                           "não teve o prazo da lei para pagar")
        if len(protestos) > 1:
            motivos.append(f"protestado {len(protestos)} vezes "
                           f"({', '.join(_br(p) for p in protestos)})")
        if motivos and not GC.antes_do_corte(quando):
            saida.append(GC._achado(
                f"PT_INDEVIDO:{prot}", "PROTESTO_INDEVIDO", "CRITICO", SETOR,
                f"Protesto de {_br(quando)} que não devia ter saído — "
                f"{_titulo_curto(t, prot) if t else 'protocolo ' + prot}",
                "; ".join(motivos).capitalize() + ". Se confirmado, o caminho é o "
                "cancelamento — pela anuência do apresentante (CN-MA art. 942, § 2º) "
                "ou por ordem judicial (art. 943) — e a comunicação à Central: "
                "protesto indevido é dano a terceiro.",
                None, "Lei 9.492/1997, arts. 12, 16, 17 e 26"))
        elif motivos:
            antigos.append(f"{prot} (protesto de {_br(quando)}: {motivos[0]})")
        # O DIA ÚTIL SEGUINTE AO PRAZO-LIMITE AINDA É NO PRAZO (27/10/2026,
        # decisão do oficial: «no dia útil seguinte»). Até essa data a conta
        # acusava todo protesto depois do 3º dia útil — e o protesto certo,
        # agora, é justamente o do 4º. O arquivo da CRA não diz a data da
        # intimação; a intimação tardia continua aparecendo aqui, e a ficha
        # do título diz a conta inteira.
        if apontado and quando > _uteis(apontado, 4, feriados) \
                and not GC.antes_do_corte(quando):
            fora_do_triduo.append((quando, prot, apontado))
        tipo_doc = str(t.get("tipo_documento") or "")
        ruim = GC._documento_invalido(t.get("documento"),
                                      {"1": "CNPJ", "2": "CPF"}.get(tipo_doc, ""))
        if ruim and not GC.antes_do_corte(quando):
            saida.append(GC._achado(
                f"PT_DOC:{prot}", "PROTESTO_DOCUMENTO_DO_DEVEDOR", "ATENCAO", SETOR,
                f"Protesto de {_br(quando)} contra {ruim} que não fecha o dígito — "
                f"{_titulo_curto(t, prot)}",
                f"O documento do devedor no arquivo é «{t.get('documento')}». Protesto "
                "contra documento errado aparece na certidão de outra pessoa.",
                None, "Lei 9.492/1997, art. 22, III"))
    if fora_do_triduo:
        fora_do_triduo.sort()
        exemplos = "; ".join(f"{p} (apontado {_br(a)}, protestado {_br(q)})"
                             for q, p, a in fora_do_triduo[-8:])
        saida.append(GC._achado(
            "PT_FORA_DO_TRIDUO", "PROTESTO_FORA_DO_TRIDUO", "ATENCAO", SETOR,
            f"{len(fora_do_triduo)} protesto(s) lavrado(s) depois do tríduo",
            f"Os mais recentes: {exemplos}. A inspeção 0000524 apontou «intimação por "
            "edital expedida fora do tríduo legal»; é a mesma conta.",
            None, ART_12))

    # 1.e  DESISTÊNCIA RECEBIDA SEM BAIXA.
    for prot, d in fluxo["desistencia"].items():
        rets = ret.get(prot, [])
        if any(r["ocorrencia"] in ENCERRA for r in rets):
            continue
        limite = _uteis(d["dia"], 1, feriados)
        if hoje <= limite:
            continue
        if GC.antes_do_corte(d["dia"]):
            antigos.append(f"{prot} (desistência de {_br(d['dia'])} sem baixa)")
            continue
        saida.append(GC._achado(
            f"PT_DESIST:{prot}", "PROTESTO_DESISTENCIA_SEM_BAIXA", "VENCIDO", SETOR,
            f"Desistência de {_br(d['dia'])} sem retorno de retirada — protocolo {prot}",
            f"Chegou no arquivo {d['arquivo']}. Sem a baixa, o título continua na fila "
            "e pode ser protestado contra quem o credor desistiu de protestar.",
            limite, "Lei 9.492/1997, art. 16; Roteiro das Centrais"))

    # 1.f  RETORNO ENVIADO DEPOIS DO DIA ÚTIL SEGUINTE — sem tarefa.
    tardios = []
    for prot, rets in ret.items():
        for r in rets:
            if r["data"] and r["enviado"] and not GC.antes_do_corte(r["data"]) \
                    and r["enviado"] > _uteis(r["data"], 1, feriados):
                tardios.append((r["enviado"], prot, r["data"]))
    if tardios:
        tardios.sort()
        exemplos = "; ".join(f"{p} (ocorrência {_br(o)}, retorno {_br(e)})"
                             for e, p, o in tardios[-8:])
        saida.append(GC._achado(
            "PT_RETORNO_TARDIO", "PROTESTO_RETORNO_TARDIO", "ATENCAO", SETOR,
            f"{len(tardios)} retorno(s) à CRA enviado(s) depois do dia útil seguinte",
            f"Os mais recentes: {exemplos}.", None, ROTEIRO))

    # 1.g  O QUE A PASTA TEM E O SISTEMA NÃO — protesto praticado por fora.
    if _tem_tabela(con, "pt_titulos"):
        no_sistema = {str(r["protocolo"]) for r in banco(con).ler(
            "SELECT protocolo FROM pt_titulos WHERE protocolo IS NOT NULL ORDER BY id")}
        fora = sorted(p for p, t in conf.items()
                      if p not in no_sistema and t["apontado"]
                      and not GC.antes_do_corte(t["apontado"]))
        if fora:
            primeiro = min(conf[p]["apontado"] for p in fora)
            saida.append(GC._achado(
                "PT_FORA_DO_SISTEMA", "PROTESTO_FORA_DO_SISTEMA", "ATENCAO", "GESTAO",
                f"{len(fora)} título(s) apontado(s) desde {_br(primeiro)} que não estão "
                "no sistema",
                "Estão nas confirmações da pasta da CRA e não em `pt_titulos`: o protesto "
                "está sendo praticado no sistema antigo. A inspeção 0000524 deu 30 dias para o "
                "Livro de Protocolo e o Livro de Registro de Pagamentos (recomendação 5), "
                "e esses livros só saem do sistema quando o ato é lavrado nele. "
                f"Protocolos: {', '.join(fora[:12])}{'…' if len(fora) > 12 else ''}.",
                None, "Relatório da inspeção 0000524, recomendação 5"))

    if antigos:
        saida.append(GC._achado(
            "PT_ANTES_DO_CORTE:CRA", "PROTESTO_ANTES_DO_CORTE", "ATENCAO", SETOR,
            f"{len(antigos)} pendência(s) do protesto anteriores a 10/09/2026 (arquivos da CRA)",
            "Não viram tarefa pela ordem do corte. " + "; ".join(antigos[:10])
            + ("…" if len(antigos) > 10 else ""), None, ""))
    return saida


# ----------------------------------------------- 2. os atos lavrados aqui

def _atos(con) -> dict[int, list[dict]]:
    if not _tem_tabela(con, "pt_atos"):
        return {}
    por_titulo: dict[int, list[dict]] = defaultdict(list)
    for r in banco(con).ler("""SELECT id, titulo_id, tipo, data_ato, detalhe_json, cancelado,
                                   livro_id, folha, origem
                              FROM pt_atos ORDER BY id"""):
        d = dict(r)
        try:
            d["detalhe"] = json.loads(d.get("detalhe_json") or "{}")
        except (TypeError, ValueError):
            d["detalhe"] = {}
        d["dia"] = _d(d["data_ato"])
        por_titulo[d["titulo_id"]].append(d)
    return por_titulo


def _sustado_em(atos: list[dict], ate_id: int) -> dict | None:
    """A sustação em vigor imediatamente antes do ato `ate_id` — vale a última
    palavra do juízo (protesto._ordem_em_vigor)."""
    ultima = None
    for a in atos:
        if a["id"] >= ate_id or a["cancelado"]:
            continue
        if a["tipo"] in ("SUSTACAO", "REVOGACAO_SUSTACAO"):
            ultima = a
    return ultima if ultima and ultima["tipo"] == "SUSTACAO" else None


def _regras_do_sistema(con, hoje: date, feriados,
                       respondidos: frozenset = frozenset()) -> list[dict]:
    if not _tem_tabela(con, "pt_titulos"):
        return []
    saida: list[dict] = []
    titulos = {r["id"]: dict(r) for r in banco(con).ler(
        """SELECT id, numero_titulo, protocolo, especie, situacao, data_vencimento,
                  apresentante_codigo, criado_em FROM pt_titulos ORDER BY id""")}
    atos = _atos(con)
    tem_avisos = _tem_tabela(con, "pt_avisos")

    for tid, lista in atos.items():
        t = titulos.get(tid) or {}
        rot = (f"protocolo {t.get('protocolo') or '?'} · título "
               f"{t.get('numero_titulo') or tid}")
        apont = next((a for a in lista if a["tipo"] == "APONTAMENTO" and not a["cancelado"]),
                     None)
        intims = [a for a in lista if a["tipo"] == "INTIMACAO" and not a["cancelado"]]
        for p in (a for a in lista if a["tipo"] == "PROTESTO" and not a["cancelado"]):
            if GC.antes_do_corte(p["dia"]):
                continue
            motivos = []
            antes = [i for i in intims if i["id"] < p["id"]]
            if not antes:
                motivos.append("não há intimação lavrada antes dele")
            elif p["dia"] and all(i["dia"] and p["dia"] <= i["dia"] for i in antes):
                motivos.append(f"lavrado no dia da intimação ({_br(antes[-1]['dia'])})")
            quit = [a for a in lista if a["tipo"] in ("PAGAMENTO", "DESISTENCIA", "RETIRADA")
                    and not a["cancelado"] and a["id"] < p["id"]]
            if quit:
                motivos.append(f"o título já tinha {quit[0]['tipo'].lower()} em "
                               f"{_br(quit[0]['dia'])}")
            ordem = _sustado_em(lista, p["id"])
            if ordem:
                motivos.append(f"havia sustação judicial em vigor desde {_br(ordem['dia'])}")
            venc = _d(t.get("data_vencimento"))
            if venc and p["dia"] and venc > p["dia"]:
                motivos.append(f"o título vencia em {_br(venc)}")
            if apont and apont["dia"] and p["dia"] and p["dia"] <= apont["dia"]:
                motivos.append("lavrado no dia do apontamento")
            if sum(1 for a in lista if a["tipo"] == "PROTESTO" and not a["cancelado"]) > 1:
                motivos.append("o título tem mais de um protesto vivo")
            if motivos:
                saida.append(GC._achado(
                    f"PT_INDEVIDO_ATO:{p['id']}", "PROTESTO_INDEVIDO", "CRITICO", SETOR,
                    f"Protesto lavrado em {_br(p['dia'])} que não devia ter saído — {rot}",
                    "; ".join(motivos).capitalize() + ".", None,
                    "Lei 9.492/1997, arts. 12, 14, 17 e 26"))
            # O PROTESTO NO DIA ÚTIL SEGUINTE AO PRAZO-LIMITE É NO PRAZO
            # (27/10/2026, decisão do oficial). Até essa data a conta acusava
            # todo protesto depois do 3º dia útil, que agora é o dia certo de
            # protestar. Quando o ato gravou a conta do tríduo
            # (`protesto_triduo`, no `detalhe_json`), vale ela — que já sabe da
            # intimação tardia, do edital e da sustação revogada; sem ela, o
            # prazo-limite é o maior entre o 3º dia útil e o 1º dia útil
            # depois da última intimação, e o protesto, o dia útil seguinte.
            conta = (p.get("detalhe") or {}).get("triduo") or {}
            if conta.get("situacao"):
                fora = conta["situacao"] == "ATRASADO"
            elif apont and apont["dia"] and p["dia"]:
                prazo = _uteis(apont["dia"], 3, feriados)
                intim = [i for i in antes if i["dia"]]
                if intim:
                    prazo = max(prazo, _uteis(intim[-1]["dia"], 1, feriados))
                fora = p["dia"] > _uteis(prazo, 1, feriados)
            else:
                fora = False
            if fora and apont and apont["dia"] and p["dia"]:
                saida.append(GC._achado(
                    f"PT_TRIDUO_ATO:{p['id']}", "PROTESTO_FORA_DO_TRIDUO", "ATENCAO", SETOR,
                    f"Protesto lavrado depois do tríduo — {rot}",
                    f"Apontado em {_br(apont['dia'])}, protestado em {_br(p['dia'])}.",
                    None, ART_12))

        for i in intims:
            if GC.antes_do_corte(i["dia"]) or not (apont and apont["dia"] and i["dia"]):
                continue
            if i["dia"] > _uteis(apont["dia"], 1, feriados):
                saida.append(GC._achado(
                    f"PT_INTIM_ATO:{i['id']}", "PROTESTO_INTIMACAO_TARDIA", "ATENCAO", SETOR,
                    f"Intimação de {_br(i['dia'])} depois do 1º dia útil — {rot}",
                    f"Apontado em {_br(apont['dia'])}.", None, ART_919))
            if (i["detalhe"].get("modo") or "").upper() == "EDITAL" and tem_avisos:
                tentou = banco(con).valor(
                    """SELECT COUNT(*) AS n FROM pt_avisos WHERE titulo_id=%s
                          AND situacao IN ('NAO_ENTREGUE','EDITAL')""", (tid,))
                if not tentou:
                    saida.append(GC._achado(
                        f"PT_EDITAL:{i['id']}", "PROTESTO_EDITAL_SEM_DILIGENCIA", "ATENCAO",
                        SETOR, f"Intimação por edital sem tentativa de entrega registrada — {rot}",
                        "O edital substitui a intimação pessoal só quando ela não foi "
                        "possível; sem o aviso não entregue, o protesto que vier dele fica "
                        "sem a prova que o sustenta.", None, "Lei 9.492/1997, art. 15"))

        # o título parado no sistema depois do tríduo. O QUE A CRA JÁ RECEBEU
        # COMO RESOLVIDO NÃO ESTÁ PARADO: o ato foi praticado no E-Ofício e não
        # chegou ao banco — e quem diz isso é o achado PROTESTO_FORA_DO_SISTEMA.
        if t.get("situacao") in ("APONTADO", "INTIMADO") and apont and apont["dia"] \
                and str(t.get("protocolo") or "") not in respondidos \
                and not GC.antes_do_corte(apont["dia"]) and not _sustado_em(lista, 10 ** 12):
            limite = _uteis(apont["dia"], 3, feriados)
            if hoje > limite:
                saida.append(GC._achado(
                    f"PT_PARADO:{tid}", "PROTESTO_TITULO_PARADO",
                    "VENCIDO" if hoje > _uteis(limite, 1, feriados) else "PRAZO", SETOR,
                    f"Título {t.get('situacao', '').lower()} desde {_br(apont['dia'])}, "
                    f"tríduo vencido em {_br(limite)} — {rot}",
                    "Sem pagamento, desistência nem sustação: o protesto é devido, ou falta "
                    "lançar o que aconteceu com o título.", limite, ART_12))

        for a in lista:
            if a["tipo"] == "PAGAMENTO" and not a["cancelado"] and not \
                    GC.antes_do_corte(a["dia"]) and not (a["livro_id"] and a["folha"]):
                saida.append(GC._achado(
                    f"PT_PAGTO_LIVRO:{a['id']}", "PROTESTO_PAGAMENTO_SEM_LIVRO", "ATENCAO",
                    SETOR,
                    f"Pagamento de {_br(a['dia'])} sem lugar no Livro de Registro de "
                    f"Pagamentos — {rot}",
                    "A inspeção 0000524 cobrou o Livro de Registro de Pagamento "
                    "(recomendação 5, 30 dias).", None, "CN-MA art. 737, IV"))

    # a sustação revogada: um dia útil do RECEBIMENTO da revogação
    try:
        import protesto as P
        for s in P.sustacao_revogada(con, hoje=hoje.isoformat()):
            dia = _d(s.get("data_da_revogacao"))
            if not dia or GC.antes_do_corte(dia):
                continue
            limite = _uteis(dia, 1, feriados)
            if hoje > limite:
                saida.append(GC._achado(
                    f"PT_REVOGADA:{s['id']}", "PROTESTO_SUSTACAO_REVOGADA", "VENCIDO", SETOR,
                    f"Sustação revogada em {_br(dia)} e protesto não lavrado — protocolo "
                    f"{s.get('protocolo') or '?'}",
                    f"Juízo {s.get('juizo') or '?'}, processo {s.get('processo') or '?'}. "
                    "Sem nova intimação.", limite, "Lei 9.492/1997, art. 17, § 2º"))
    except Exception as erro:                           # noqa: BLE001 — vira NAO_MEDIU
        saida.append(GC._achado("NAO_MEDIU:PROTESTO_SUSTACAO_REVOGADA",
                                "PROTESTO_SUSTACAO_REVOGADA", "NAO_MEDIU", "TI",
                                "A conferência da sustação revogada não mediu",
                                f"{type(erro).__name__}: {erro}"))

    saida.extend(_certidoes_negativas(con, titulos, atos))
    return saida


def _certidoes_negativas(con, titulos: dict, atos: dict) -> list[dict]:
    """Certidão NEGATIVA emitida sobre documento que tinha protesto vivo no dia.
    É o papel que faz o banco emprestar para quem não devia."""
    if not (_tem_tabela(con, "pt_certidoes") and _tem_tabela(con, "pt_devedores")):
        return []
    so = lambda x: "".join(ch for ch in str(x or "") if ch.isdigit())  # noqa: E731
    protestos_do_doc: dict[str, list[tuple]] = defaultdict(list)
    for r in banco(con).ler("SELECT titulo_id, documento_numero FROM pt_devedores ORDER BY id"):
        doc = so(r["documento_numero"])
        if len(doc) not in (11, 14):
            continue
        lista = atos.get(r["titulo_id"], [])
        for p in (a for a in lista if a["tipo"] == "PROTESTO" and not a["cancelado"]):
            fim = next((a["dia"] for a in lista if a["tipo"] == "CANCELAMENTO"
                        and not a["cancelado"] and a["id"] > p["id"]), None)
            protestos_do_doc[doc].append((p["dia"], fim, r["titulo_id"]))
    saida = []
    for c in banco(con).ler("""SELECT id, numero, ano, documento, nome, emitida_em
                              FROM pt_certidoes WHERE tipo='NEGATIVA' AND cancelada=0
                              ORDER BY id"""):
        dia = _d(c["emitida_em"])
        if not dia or GC.antes_do_corte(dia):
            continue
        vivos = [x for x in protestos_do_doc.get(so(c["documento"]), [])
                 if x[0] and x[0] <= dia and (x[1] is None or x[1] > dia)]
        if vivos:
            t = titulos.get(vivos[0][2]) or {}
            saida.append(GC._achado(
                f"PT_CERT_NEG:{c['id']}", "PROTESTO_CERTIDAO_NEGATIVA_INDEVIDA", "CRITICO",
                SETOR, f"Certidão negativa {c['numero']}/{c['ano']} de {_br(dia)} sobre quem "
                f"tinha protesto — {c['nome']}",
                f"Protesto de {_br(vivos[0][0])}, protocolo {t.get('protocolo') or '?'}. "
                "Cancelar a certidão e emitir a positiva.", None, "Lei 9.492/1997, art. 27"))
    return saida


def _modelo_do_termo(con) -> list[dict]:
    """A recomendação 2 da inspeção: «abster-se de utilizar a expressão 'protesto
    para fins art. 9º da Lei 9.430/1996' no campo de motivo». O padrão do termo
    desta casa ainda a traz — e é o oficial quem muda o modelo (catálogo)."""
    import protesto_termo as PT
    try:
        import modelos_da_casa as MC
        texto = MC.corpo_de(con, PT.CHAVE_NO_CATALOGO)
    except Exception:                                   # noqa: BLE001 — cai no padrão
        # O PADRÃO DA BASE (LF06A): o `TEXTO_BASE` de antes era o começo dele,
        # e saiu do código com o resto do termo. Sem banco nem pasta, não há
        # texto a conferir — e o alerta cala, como calava.
        try:
            texto = MC.padrao_de(PT.CHAVE_NO_CATALOGO)
        except Exception:                               # noqa: BLE001
            texto = ""
    if "9.430" not in (texto or ""):
        return []
    return [GC._achado(
        "PT_MODELO_9430", "PROTESTO_MODELO_DO_TERMO", "ATENCAO", "GESTAO",
        "O termo de protesto do sistema ainda afirma «art. 9º-A da Lei 9.430/1996»",
        "A inspeção 0000524 mandou abster-se da expressão no motivo e indicar o tipo e "
        "o motivo de cada protesto (recomendação 2, prazo de 15 dias). O modelo está "
        f"no catálogo ({PT.CHAVE_NO_CATALOGO}); o próximo protesto lavrado aqui sai "
        "com ela.", None, "Lei 9.492/1997, art. 23; Prov. 23/2026, art. 914, IX")]


# --------------------------------------------------------------- a regra

def conferir(con, hoje: date, *, pasta_cra: Path | None = None) -> list[dict]:
    """Tudo o que o agente do Protesto aponta. SÓ LÊ. Cada parte que quebra
    vira NAO_MEDIU, e as outras continuam."""
    feriados = _feriados(con)
    achados: list[dict] = []
    pasta = Path(pasta_cra) if pasta_cra else _pasta_cra(con)
    respondidos: frozenset = frozenset()
    if pasta is None or not pasta.is_dir():
        achados.append(GC._achado(
            "PT_PASTA_CRA", "PROTESTO_PASTA_CRA", "NAO_MEDIU", SETOR,
            "A pasta dos arquivos da CRA não foi encontrada — prazos da Central não medidos",
            (f"Procurada em «{pasta}». " if pasta is not None else
             "A pasta não está configurada. ")
            + f"Ajuste em configurações ({CHAVE_PASTA_CRA}).", None, ""))
    else:
        try:
            fluxo = ler_fluxo_da_cra(pasta, hoje)
            respondidos = frozenset(p for p, rs in fluxo["retorno"].items()
                                    if any(r["ocorrencia"] in ENCERRA for r in rs))
            achados.extend(_regras_do_fluxo(con, fluxo, hoje, feriados))
            if fluxo["ilegiveis"]:
                achados.append(GC._achado(
                    "PT_PASTA_CRA:ILEGIVEIS", "PROTESTO_PASTA_CRA", "NAO_MEDIU", SETOR,
                    f"{len(fluxo['ilegiveis'])} arquivo(s) da CRA não se leram",
                    "; ".join(fluxo["ilegiveis"][:5]), None, ""))
        except Exception as erro:                       # noqa: BLE001
            achados.append(GC._achado(
                "NAO_MEDIU:PROTESTO_CRA", "PROTESTO_PASTA_CRA", "NAO_MEDIU", "TI",
                "A leitura dos arquivos da CRA quebrou", f"{type(erro).__name__}: {erro}"))
    for nome, parte in (("PROTESTO_SISTEMA", lambda: _regras_do_sistema(con, hoje, feriados, respondidos)),
                        ("PROTESTO_MODELO_DO_TERMO", lambda: _modelo_do_termo(con))):
        try:
            achados.extend(parte())
        except Exception as erro:                       # noqa: BLE001
            achados.append(GC._achado(
                f"NAO_MEDIU:{nome}", nome, "NAO_MEDIU", "TI",
                f"A conferência «{nome}» não conseguiu medir",
                f"{type(erro).__name__}: {erro}"))
    return achados
