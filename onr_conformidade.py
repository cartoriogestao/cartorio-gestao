"""O PAINEL DE CONFORMIDADE DO ONR — o declarado, o que existe, o que foi entregue e o que falta.

    «Painel ADPF 743 não aparece no login da serventia, por isso o sistema
     precisa mostrar o que foi declarado e o que foi de fato entregue.»
                                              — tarefa RI010, 23/11/2026

POR QUE EXISTE
    A Circular COGEX 243/2026 aponta a serventia no Provimento CNJ 143 (Livros 2,
    4 e 5), na ITN 003 (matrículas, acervo e atos) e a dá em dia no Provimento
    195 (polígonos no Mapa). Os números do painel do ONR **não são a entrega**:
    o do Provimento 143 é a soma do que a própria serventia digitou no
    «Cronograma de Dados – CNJ» (RI006 §8.1, RI007 §1). Um painel que mostrasse
    só o declarado daria por cumprido o que nunca subiu.

QUATRO COLUNAS, LADO A LADO, PARA CADA NÚMERO
    | coluna                   | de onde sai                                       |
    |--------------------------|---------------------------------------------------|
    | declarado ao ONR         | DIGITADO por alguém (`onr_declaracoes`), com a    |
    |                          | data da leitura, a origem e quem lançou           |
    | existe no sistema        | contado agora nas tabelas do RI                   |
    | entregue com prova       | `ri_onr_envios` (só ACEITO, em PRODUCAO),         |
    |                          | `ge_onr_cargas` (o que o IPS levou), a marca do   |
    |                          | CSL2 e a importação INFORMADA no portal           |
    |                          | (`onr_provas_informadas`, só IMPORTADO)           |
    | falta                    | a referência menos o que foi entregue com prova   |

O QUE NUNCA SE FAZ AQUI
    * **Declarado sem lastro não é cumprido.** Vira DIVERGÊNCIA: soma acima do
      total, Livro 4 declarado sem entrega, Livro 2 «disponível» sem a prova do
      CSL2. A obrigação com divergência nunca fica «em dia».
    * **O que o sistema não mede não vira zero nem vira verde.** Polígono do
      Mapa e as colunas da ITN 003 não têm canal nesta casa: o número do painel
      é do ONR, e a tela diz «lastro fora do sistema» em vez de acusar.
    * **«Enviado» não é «entregue».** Só ACEITO (indicador real) e IMPORTADO
      (importação informada) contam. PROCESSANDO e NAO_IMPORTADO aparecem à
      parte.
    * **Não envia nada, não entra no ONR e não chama a API.** SÓ LÊ; o que grava
      é o que a pessoa digitou.

AS REGRAS DO PAINEL DO ONR (RI006 §3.2 — observadas em 100% das linhas do anexo,
NÃO são norma: a tela as chama de «regra observada», e não promete que cumprem)
    Provimento 143: inadimplente quando o menor entre digitadas, digitalizadas,
    Livro 4 e Livro 5 é menor que o acervo declarado. ITN 003: adimplente com
    ao menos 1 matrícula. Provimento 195: adimplente com ao menos 1 polígono.

O SEMÁFORO (`conformidade.py`, PR 466) NÃO GANHA REGRA NOVA: o painel entrega
achados ao gestor (`achados_para_o_gestor`, chamado por `gestor_cargas_ri.
conferir`), e o semáforo continua medindo `ge_achados`. Ver `achados_para_o_gestor`
para o que cada coisa vira e por que a obrigação sem declaração não acende nada.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from bd_nativo import banco

# ------------------------------------------------------------------ o catálogo

PROV143, PROV195, ITN003 = "PROV143", "PROV195", "ITN003"
OBRIGACOES: tuple[tuple[str, str], ...] = (
    (PROV143, "Provimento CNJ 143/2023 — Livros 2, 4 e 5"),
    (PROV195, "Provimento CNJ 195/2025 — polígonos no Mapa (SIG-RI)"),
    (ITN003, "ITN 003 — matrículas, acervo e atos no Mapa"),
)
NOME_DA_OBRIGACAO = dict(OBRIGACOES)

NUMERO, SIMNAO = "NUMERO", "SIMNAO"
SERVENTIA, ONR = "SERVENTIA", "ONR"

#: As colunas: código → (obrigação, rótulo, tipo, quem produz o declarado,
#: origem sugerida). `SERVENTIA`: a própria casa digitou no Cronograma (não é
#: evidência de entrega). `ONR`: é o que o painel do ONR mostra da casa.
COLUNAS: dict[str, dict[str, Any]] = {
    "TOTAL": dict(obrigacao=PROV143, rotulo="Acervo declarado (total de matrículas)", tipo=NUMERO,
                  declarado_por=SERVENTIA, origem="Cronograma de Dados – CNJ (Ofício Eletrônico), linha Total"),
    "L2_DIGITADAS": dict(obrigacao=PROV143, rotulo="Livro 2 — digitadas", tipo=NUMERO,
                         declarado_por=SERVENTIA, origem="Cronograma de Dados – CNJ, coluna Digitadas, linha Total"),
    "L2_DIGITALIZADAS": dict(obrigacao=PROV143, rotulo="Livro 2 — digitalizadas (imagens)", tipo=NUMERO,
                             declarado_por=SERVENTIA, origem="Cronograma de Dados – CNJ, coluna Digitalizadas, linha Total"),
    "L4": dict(obrigacao=PROV143, rotulo="Livro 4 — Indicador Real", tipo=NUMERO,
               declarado_por=SERVENTIA, origem="Cronograma de Dados – CNJ, coluna Livro 4, linha Total"),
    "L5": dict(obrigacao=PROV143, rotulo="Livro 5 — Indicador Pessoal", tipo=NUMERO,
               declarado_por=SERVENTIA, origem="Cronograma de Dados – CNJ, coluna Livro 5, linha Total"),
    "DISP_L2": dict(obrigacao=PROV143, rotulo="«Imagens do Livro 2 disponíveis no SAEC/ONR?»", tipo=SIMNAO,
                    declarado_por=SERVENTIA, origem="Cronograma de Dados – CNJ, pergunta de disponibilidade"),
    "DISP_L4": dict(obrigacao=PROV143, rotulo="«Indicador Real (Livro 4) disponível no SAEC/ONR?»", tipo=SIMNAO,
                    declarado_por=SERVENTIA, origem="Cronograma de Dados – CNJ, pergunta de disponibilidade"),
    "DISP_L5": dict(obrigacao=PROV143, rotulo="«Indicador Pessoal (Livro 5) disponível no SAEC/ONR?»", tipo=SIMNAO,
                    declarado_por=SERVENTIA, origem="Cronograma de Dados – CNJ, pergunta de disponibilidade"),
    "POLIGONOS": dict(obrigacao=PROV195, rotulo="Polígonos no Mapa (SIG-RI)", tipo=NUMERO,
                      declarado_por=ONR, origem="Painel ADPF 743, aba Provimento 195 (anexo da Circular)"),
    "ITN_MATRICULAS": dict(obrigacao=ITN003, rotulo="Matrículas recebidas", tipo=NUMERO,
                           declarado_por=ONR, origem="Painel ADPF 743, aba ITN 003 (anexo da Circular)"),
    "ITN_ACERVO": dict(obrigacao=ITN003, rotulo="Acervo recebido", tipo=NUMERO,
                       declarado_por=ONR, origem="Painel ADPF 743, aba ITN 003 (anexo da Circular)"),
    "ITN_ATOS": dict(obrigacao=ITN003, rotulo="Atos recebidos", tipo=NUMERO,
                     declarado_por=ONR, origem="Painel ADPF 743, aba ITN 003 (anexo da Circular)"),
}
CODIGOS = tuple(COLUNAS)

#: As colunas que a casa leva ao ONR por canal próprio — só nelas «declarado
#: acima do entregue» é divergência. Nas outras o número é do ONR (ou o
#: sistema não tem canal), e a tela diz «lastro fora do sistema».
CANAL_PROPRIO = frozenset({"L2_DIGITALIZADAS", "L4", "L5"})
#: As perguntas Sim/Não e a coluna que as prova.
DISPONIBILIDADE = {"DISP_L2": "L2_DIGITALIZADAS", "DISP_L4": "L4", "DISP_L5": "L5"}
#: Onde a pessoa pode informar uma importação feita no portal.
COM_PROVA_INFORMADA = tuple(c for c, d in COLUNAS.items()
                            if d["tipo"] == NUMERO and c != "TOTAL")

SITUACOES_DA_PROVA = {"PROCESSANDO": "Processando", "IMPORTADO": "Importado",
                      "NAO_IMPORTADO": "Não importado"}
IMPORTADO = "IMPORTADO"
ENTIDADE_DO_ANEXO = "ONR_PENDENCIA"

ABERTA, CONCLUIDA, CANCELADA = "ABERTA", "CONCLUIDA", "CANCELADA"

#: A declaração lida há mais que isto (em dias) pede nova leitura no portal.
DECLARACAO_ANTIGA_DIAS = 7

# Vereditos de cada obrigação.
SEM_DECLARACAO, INCOMPLETO, DIVERGENTE, FALTA, EM_DIA, EM_DIA_NO_PAINEL = (
    "SEM_DECLARACAO", "INCOMPLETO", "DIVERGENTE", "FALTA", "EM_DIA", "EM_DIA_NO_PAINEL")
ROTULO_DO_VEREDITO = {
    SEM_DECLARACAO: "Sem declaração lançada",
    INCOMPLETO: "Faltam números a lançar",
    DIVERGENTE: "Declarado sem lastro",
    FALTA: "Falta entregar",
    EM_DIA: "Entregue com prova",
    EM_DIA_NO_PAINEL: "Em dia no painel — o lastro está fora deste sistema",
}

# As regras do gestor (ver `achados_para_o_gestor`).
REGRA_DIVERGENCIA = "ONR_PAINEL_DIVERGENCIA"
REGRA_OBRIGACAO = "ONR_PAINEL_OBRIGACAO"
REGRA_PENDENCIA = "ONR_PAINEL_PENDENCIA"
ROTULOS = {
    REGRA_DIVERGENCIA: "ONR — número declarado ao ONR sem lastro no sistema",
    REGRA_OBRIGACAO: "ONR — obrigação do painel sem responsável e prazo registrados",
    REGRA_PENDENCIA: "ONR — pendência do painel de conformidade",
}
FUNDAMENTO = ("Circular COGEX 243/2026 (ADPF 743): o número do painel do ONR é o declarado, "
              "e a Corregedoria exige a prova da entrega e o protocolo do ONR para alegar "
              "impedimento. Conferência do painel de conformidade (RI010).")


class PainelOnrError(ValueError):
    """O lançamento que não se grava, com o motivo para a tela."""


# --------------------------------------------------------------------- miúdos

def _agora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _dia(texto) -> date | None:
    bruto = str(texto or "")[:10]
    try:
        return date(int(bruto[:4]), int(bruto[5:7]), int(bruto[8:10]))
    except (ValueError, IndexError):
        return None


def _inteiro(valor, nome: str, *, maximo: int = 10_000_000) -> int:
    texto = str(valor if valor is not None else "").strip().replace(".", "")
    if not re.fullmatch(r"\d{1,9}", texto):
        raise PainelOnrError(f"{nome}: digite um número inteiro, sem sinal.")
    n = int(texto)
    if n > maximo:
        raise PainelOnrError(f"{nome}: número grande demais.")
    return n


def _data(valor, nome: str, hoje: date, *, futura: bool = False) -> str:
    d = _dia(valor)
    if d is None or len(str(valor).strip()) < 10:
        raise PainelOnrError(f"{nome}: informe a data (dia/mês/ano).")
    if d.year < 2023 or (not futura and d > hoje):
        raise PainelOnrError(f"{nome}: data fora do que cabe (de 2023 até hoje).")
    return d.isoformat()


def _texto(valor, nome: str, *, obrigatorio: bool, limite: int) -> str | None:
    t = re.sub(r"\s+", " ", str(valor or "")).strip()
    if not t:
        if obrigatorio:
            raise PainelOnrError(f"{nome}: preencha.")
        return None
    if len(t) > limite:
        raise PainelOnrError(f"{nome}: no máximo {limite} caracteres.")
    return t


def _tabela(bd, nome: str) -> bool:
    try:
        return bd.tem_tabela(nome)
    except Exception:                                   # noqa: BLE001
        return False


def _numero(texto) -> int | None:
    m = re.match(r"\s*(\d+)\s*$", str(texto or ""))
    return int(m.group(1)) if m else None


#: A ficha arquivada (9040xx) é casca que saiu da sequência: não é matrícula.
LIMITE_DA_FICHA_ARQUIVADA = 900000


# --------------------------------------------------- o que existe no sistema

def _fichas(con) -> list[dict]:
    bd = banco(con)
    if not _tabela(bd, "ri_matriculas"):
        return []
    saida = []
    for r in bd.ler(
            """SELECT id, numero, encerrada, tipo_ficha, rural_urbano, sigef, criado_em,
                      digi_sha256, digi_onr_pendente,
                      (teor IS NOT NULL AND TRIM(teor) <> '') AS tem_teor
                 FROM ri_matriculas"""):
        n = _numero(r["numero"])
        if n is None or n >= LIMITE_DA_FICHA_ARQUIVADA:
            continue
        saida.append({**r, "n": n, "vigente": not int(r["encerrada"] or 0)})
    return saida


def medir_sistema(con) -> dict[str, dict]:
    """O que existe no sistema, por coluna: {valor, nota, fonte}. SÓ LÊ.

    `valor` None quer dizer «o sistema não mede isto» — nunca zero.
    """
    bd = banco(con)
    fichas = _fichas(con)
    fonte = "contagem agora em ri_matriculas"
    sem_tabela = {"valor": None, "nota": "tabela do Registro de Imóveis ausente neste banco", "fonte": fonte}
    if not fichas and not _tabela(bd, "ri_matriculas"):
        return {c: dict(sem_tabela) for c in CODIGOS}
    vigentes = [f for f in fichas if f["vigente"]]
    com_teor = [f for f in fichas if f["tem_teor"]]
    com_pdf = [f for f in fichas if f["digi_sha256"]]
    acervo = [f for f in vigentes if str(f["tipo_ficha"] or "").upper() == "ACERVO"]
    ids_vigentes = {f["id"] for f in vigentes}
    com_parte = 0
    if _tabela(bd, "ri_partes"):
        com_parte = len({r["matricula_id"] for r in bd.ler(
            "SELECT DISTINCT matricula_id FROM ri_partes WHERE TRIM(COALESCE(nome,'')) <> ''")}
            & ids_vigentes)
    atos = lavrados = None
    if _tabela(bd, "ri_atos"):
        atos = int(bd.valor("SELECT COUNT(*) FROM ri_atos WHERE COALESCE(cancelado,0) = 0") or 0)
        if bd.tem_coluna("ri_atos", "acervo"):
            lavrados = int(bd.valor(
                "SELECT COUNT(*) FROM ri_atos WHERE COALESCE(cancelado,0) = 0 "
                "AND COALESCE(acervo,0) = 0") or 0)
    rurais_sigef = sum(1 for f in vigentes if str(f["rural_urbano"] or "").upper().startswith("R")
                       and str(f["sigef"] or "").strip())
    achados_incompletos = 0
    if _tabela(bd, "ge_achados"):
        achados_incompletos = int(bd.valor(
            "SELECT COUNT(*) FROM ge_achados WHERE regra = 'ONR_INDICADOR_INCOMPLETO' "
            "AND resolvido_em IS NULL") or 0)

    def m(valor, nota, fonte_=fonte):
        return {"valor": valor, "nota": nota, "fonte": fonte_}

    return {
        "TOTAL": m(len(fichas), f"fichas numeradas (inclui {len(fichas) - len(vigentes)} encerradas); "
                                f"{len(vigentes)} vigentes. O oficial decide qual número declarar."),
        "L2_DIGITADAS": m(len(com_teor), "fichas numeradas com o teor digitado"),
        "L2_DIGITALIZADAS": m(len(com_pdf), "fichas numeradas com o PDF digitalizado assinado "
                                            "(existir aqui não é estar no ONR)"),
        "L4": m(len(vigentes), "fichas vigentes, o universo do Indicador Real; "
                               f"{achados_incompletos} delas com achado aberto de indicador que não monta"),
        "L5": m(com_parte, "fichas vigentes com ao menos uma parte lançada"),
        "DISP_L2": m(None, "pergunta Sim/Não: o que a prova é a coluna «digitalizadas»"),
        "DISP_L4": m(None, "pergunta Sim/Não: o que a prova é a coluna do Livro 4"),
        "DISP_L5": m(None, "pergunta Sim/Não: o que a prova é a coluna do Livro 5"),
        "POLIGONOS": m(None, "o sistema não guarda polígono (a geometria vive no Mapa do ONR); "
                             f"há {rurais_sigef} matrícula(s) rural(is) vigente(s) com SIGEF informado, "
                             "só como indício de quantos imóveis já são georreferenciados"),
        "ITN_MATRICULAS": m(len(vigentes), "fichas vigentes: o que a ITN 003 pede, no limite"),
        "ITN_ACERVO": m(len(acervo), "fichas vigentes herdadas do sistema antigo (tipo ACERVO)"),
        "ITN_ATOS": m(atos, "atos não cancelados" + (f"; {lavrados} lavrados por esta casa" if lavrados is not None else "")
                      + ". Atenção: o ato ainda não tem data do instrumento, que o envio exige"
                      if atos is not None else "tabela de atos ausente"),
    }


# ----------------------------------------------- o que foi entregue, com prova

def _provas_informadas(con) -> list[dict]:
    bd = banco(con)
    if not _tabela(bd, "onr_provas_informadas"):
        return []
    return bd.ler("""SELECT * FROM onr_provas_informadas WHERE anulado_em IS NULL ORDER BY id""")


def medir_entregas(con) -> dict[str, dict]:
    """O entregue COM PROVA, por coluna: {valor, fontes, nota, em_andamento}. SÓ LÊ.

    `valor` é o MAIOR entre as fontes, e não a soma: as fontes podem contar as
    mesmas matrículas, e somar poderia afirmar entrega que não houve.
    """
    bd = banco(con)
    por_coluna: dict[str, dict] = {c: {"valor": None, "fontes": [], "nota": "", "em_andamento": 0,
                                       "nao_importado": 0} for c in CODIGOS}

    def fonte(coluna, rotulo, valor, onde, data=""):
        por_coluna[coluna]["fontes"].append({"rotulo": rotulo, "valor": valor, "onde": onde,
                                             "data": str(data or "")[:10]})

    # Indicador Real (Livro 4) pela API: só o ACEITO, em PRODUCAO.
    if _tabela(bd, "ri_onr_envios"):
        aceitos = bd.um(
            """SELECT COUNT(DISTINCT matricula_id) AS n, MAX(COALESCE(fila_conferida_em, enviado_em)) AS ate
                 FROM ri_onr_envios WHERE especie = 'INDICADOR' AND ambiente = 'PRODUCAO'
                  AND situacao = 'ACEITO'""") or {}
        fonte("L4", "Indicador Real aceito pela fila do ONR (produção)", int(aceitos.get("n") or 0),
              "ri_onr_envios, situação ACEITO", aceitos.get("ate"))
        sem_aceite = int(bd.valor(
            """SELECT COUNT(DISTINCT matricula_id) FROM ri_onr_envios WHERE especie = 'INDICADOR'
                AND ambiente = 'PRODUCAO' AND situacao = 'ENVIADO'""") or 0)
        por_coluna["L4"]["em_andamento"] += sem_aceite
    else:
        fonte("L4", "Indicador Real aceito pela fila do ONR (produção)", 0,
              "ri_onr_envios (tabela ausente)")

    # Indicador Pessoal (Livro 5): o que o programa IPS levou.
    if _tabela(bd, "ge_onr_cargas"):
        completa = bd.um(
            """SELECT id, quantos, COALESCE(processado_em, gerado_em) AS em FROM ge_onr_cargas
                WHERE canal = 'PESSOAL' AND tipo = 'COMPLETA' AND situacao = 'PROCESSADO'
                ORDER BY id DESC LIMIT 1""")
        if completa:
            corte = str(completa["em"] or "")[:19]
            ids_com_parte = set()
            if _tabela(bd, "ri_partes"):
                ids_com_parte = {r["matricula_id"] for r in bd.ler(
                    "SELECT DISTINCT matricula_id FROM ri_partes WHERE TRIM(COALESCE(nome,'')) <> ''")}
            cobertas = sum(1 for f in _fichas(con)
                           if f["id"] in ids_com_parte and str(f["criado_em"] or "")[:19] <= corte)
            fonte("L5", f"Indicador Pessoal: carga completa que o IPS levou ({completa['quantos']} vínculos)",
                  cobertas, "ge_onr_cargas, COMPLETA/PROCESSADO — fichas com parte já existentes na data da carga",
                  completa["em"])
            por_coluna["L5"]["nota"] = ("«Levado pelo IPS» não é «aceito pelo ONR»: a aceitação de cada vínculo "
                                        "só o ONR confirma. Fichas abertas depois da carga contam só quando "
                                        "uma importação informada as cobrir.")
        else:
            fonte("L5", "Indicador Pessoal: carga completa que o IPS levou", 0,
                  "ge_onr_cargas, nenhuma carga completa em PROCESSADO")
        parado = int(bd.valor(
            """SELECT COUNT(*) FROM ge_onr_cargas WHERE canal = 'PESSOAL'
                AND situacao IN ('PREPARADO', 'NA_PASTA')""") or 0)
        por_coluna["L5"]["em_andamento"] += parado
    else:
        fonte("L5", "Indicador Pessoal: carga completa que o IPS levou", 0, "ge_onr_cargas (tabela ausente)")

    # Imagens do Livro 2: a marca só baixa depois que o CSL2 lê a pasta.
    csl2 = ""
    if _tabela(bd, "settings"):
        csl2 = str(bd.valor("SELECT value FROM settings WHERE key = 'onr_csl2_desde'") or "").strip()
    if csl2:
        baixadas = sum(1 for f in _fichas(con) if f["digi_sha256"] and not int(f["digi_onr_pendente"] or 0))
        fonte("L2_DIGITALIZADAS", "Imagens com a marca de entrega baixada (CSL2 em uso)", baixadas,
              "ri_matriculas.digi_onr_pendente = 0, com onr_csl2_desde informado", csl2)
    else:
        fonte("L2_DIGITALIZADAS", "Imagens com a marca de entrega baixada (CSL2 em uso)", 0,
              "sem prova do CSL2: «onr_csl2_desde» não está informado nas configurações")
        por_coluna["L2_DIGITALIZADAS"]["nota"] = (
            "Sem a prova do CSL2, estar na pasta de conversão não é estar no ONR. "
            "Informe a data do CSL2 nas configurações ou uma importação no portal.")

    # O que a pessoa informou do portal.
    for p in _provas_informadas(con):
        c = por_coluna.get(p["coluna"])
        if c is None:
            continue
        if p["situacao"] == IMPORTADO:
            fonte(p["coluna"], "Importação informada no portal" + (f" — protocolo {p['protocolo_onr']}"
                                                                   if p.get("protocolo_onr") else ""),
                  int(p["quantos"]), f"onr_provas_informadas #{p['id']}, lançada por {p['lancado_por']}",
                  p["visto_em"])
        elif p["situacao"] == "PROCESSANDO":
            c["em_andamento"] += int(p["quantos"])
        else:
            c["nao_importado"] += int(p["quantos"])

    for c in por_coluna.values():
        valores = [f["valor"] for f in c["fontes"]]
        c["valor"] = max(valores) if valores else None
    return por_coluna


# ---------------------------------------------------------- o que se declarou

def declaracoes_vigentes(con) -> dict[str, dict]:
    """A declaração vigente de cada coluna: a última não anulada. SÓ LÊ."""
    bd = banco(con)
    if not _tabela(bd, "onr_declaracoes"):
        return {}
    saida: dict[str, dict] = {}
    for r in bd.ler("SELECT * FROM onr_declaracoes WHERE anulado_em IS NULL ORDER BY id"):
        saida[r["coluna"]] = r
    return saida


def historico_de_declaracoes(con, limite: int = 60) -> list[dict]:
    bd = banco(con)
    if not _tabela(bd, "onr_declaracoes"):
        return []
    return bd.ler("SELECT * FROM onr_declaracoes ORDER BY id DESC LIMIT %s", (limite,))


def historico_de_provas(con, limite: int = 60) -> list[dict]:
    bd = banco(con)
    if not _tabela(bd, "onr_provas_informadas"):
        return []
    return bd.ler("SELECT * FROM onr_provas_informadas ORDER BY id DESC LIMIT %s", (limite,))


# ----------------------------------------------------------------- a medição

def _celula(codigo, decl, sis, ent, total_decl, sistema_total, hoje) -> dict:
    d = COLUNAS[codigo]
    valor = decl["valor"] if decl else None
    referencia = total_decl if total_decl is not None else sistema_total
    entregue = ent["valor"]
    falta = None
    nota_falta = ""
    if codigo == "L2_DIGITADAS" and referencia is not None and sis["valor"] is not None:
        falta = max(0, referencia - sis["valor"])
        nota_falta = "referência menos as fichas com teor digitado"
    elif codigo in CANAL_PROPRIO and referencia is not None:
        falta = max(0, referencia - (entregue or 0))
        nota_falta = "referência menos o entregue com prova"
    elif codigo in ("ITN_MATRICULAS", "ITN_ACERVO") and sis["valor"] is not None:
        visto = max(entregue or 0, valor or 0)
        falta = max(0, sis["valor"] - visto)
        nota_falta = "o que o sistema tem menos o maior entre o provado e o que o painel mostra"

    situacao = "NAO_DECLARADO"
    if decl is not None:
        if d["tipo"] == SIMNAO:
            situacao = "DECLARADO"
        elif d["declarado_por"] == ONR:
            situacao = "NO_PAINEL" if valor else "ZERO_NO_PAINEL"
        elif codigo == "TOTAL":
            situacao = "CONFERE" if sistema_total is None or valor == sistema_total else "DIFERE_DO_SISTEMA"
        elif codigo == "L2_DIGITADAS":
            situacao = ("ACIMA_DO_SISTEMA" if sis["valor"] is not None and valor > sis["valor"]
                        else "CONFERE")
        else:
            base = entregue or 0
            situacao = ("SEM_LASTRO" if valor > base else
                        "ABAIXO_DA_ENTREGA" if valor < base else "CONFERE")
        if (d["tipo"] == NUMERO and d["declarado_por"] == SERVENTIA and codigo != "TOTAL"
                and total_decl is not None and valor > total_decl):
            situacao = "ACIMA_DO_TOTAL"
    return {"codigo": codigo, "rotulo": d["rotulo"], "tipo": d["tipo"], "declarado_por": d["declarado_por"],
            "declarado": decl, "sistema": sis, "entregue": ent, "referencia": referencia,
            "falta": falta, "nota_da_falta": nota_falta, "situacao": situacao,
            "origem_sugerida": d["origem"], "canal_proprio": codigo in CANAL_PROPRIO}


def _divergencias(celulas: dict[str, dict], hoje: date) -> list[dict]:
    """O declarado sem lastro (gravidade DIVERGENCIA) e o que só pede ajuste (AJUSTE)."""
    saida: list[dict] = []

    def add(codigo, coluna, gravidade, titulo, detalhe):
        saida.append({"codigo": codigo, "coluna": coluna, "obrigacao": COLUNAS[coluna]["obrigacao"],
                      "gravidade": gravidade, "titulo": titulo, "detalhe": detalhe})

    def n(v):
        return f"{int(v):,}".replace(",", ".")

    total = celulas["TOTAL"]["declarado"]
    for c in ("L2_DIGITADAS", "L2_DIGITALIZADAS", "L4", "L5"):
        cel = celulas[c]
        decl = cel["declarado"]
        if decl is None:
            continue
        v, rot = decl["valor"], COLUNAS[c]["rotulo"]
        ent, sis = cel["entregue"]["valor"] or 0, cel["sistema"]["valor"]
        if cel["situacao"] == "ACIMA_DO_TOTAL":
            add("SOMA_ACIMA_DO_TOTAL", c, "DIVERGENCIA",
                f"{rot}: declarado {n(v)}, acima do total declarado de {n(total['valor'])}",
                "A soma dos lançamentos mensais passa do acervo: o mesmo acervo foi provavelmente contado "
                "duas vezes. Corrija o Cronograma depois de conferir a tela.")
        elif cel["situacao"] == "ACIMA_DO_SISTEMA":
            add("DECLARADO_ACIMA_DO_SISTEMA", c, "DIVERGENCIA",
                f"{rot}: declarado {n(v)}, o sistema tem {n(sis)}",
                "O sistema não tem as fichas que sustentem o que foi declarado.")
        if c in CANAL_PROPRIO and v > ent:
            if ent == 0:
                add("SEM_ENTREGA", c, "DIVERGENCIA",
                    f"{rot}: declarado {n(v)}, entregue com prova 0",
                    "Nada foi entregue com prova por nenhum canal (API aceita, IPS, CSL2 ou importação "
                    "informada). Declarar sem entrega é declarar o que o ONR não recebeu.")
            else:
                add("DECLARADO_ACIMA_DA_ENTREGA", c, "DIVERGENCIA",
                    f"{rot}: declarado {n(v)}, entregue com prova {n(ent)}",
                    "A entrega provada é menor que a declarada.")
        elif c == "L5" and v < ent:
            add("DECLARADO_ABAIXO_DA_ENTREGA", c, "AJUSTE",
                f"{rot}: declarado {n(v)}, o IPS já levou {n(ent)}",
                "A declaração está abaixo do que foi levado. Confirmar com o ONR o que ele recebeu antes "
                "de corrigir o Cronograma.")
    for pergunta, coluna in DISPONIBILIDADE.items():
        decl = celulas[pergunta]["declarado"]
        if decl is None:
            continue
        ent = celulas[coluna]["entregue"]["valor"] or 0
        if decl["valor"] == 1 and ent == 0:
            codigo = "LIVRO2_DISPONIVEL_SEM_CSL2" if pergunta == "DISP_L2" else "DISPONIVEL_SEM_PROVA"
            add(codigo, pergunta, "DIVERGENCIA",
                f"{COLUNAS[pergunta]['rotulo']}: declarado «Sim», sem prova" +
                (" do CSL2" if pergunta == "DISP_L2" else ""),
                "A resposta «Sim» não tem entrega provada por trás." if pergunta != "DISP_L2" else
                "O Livro 2 só está disponível no ONR com a prova do CSL2 (data informada ou importação "
                "informada). A pasta de conversão não prova.")
        elif decl["valor"] == 0 and ent > 0:
            add("PERGUNTA_ABAIXO_DA_ENTREGA", pergunta, "AJUSTE",
                f"{COLUNAS[pergunta]['rotulo']}: declarado «Não», mas há {n(ent)} entregue(s) com prova",
                "Confirmar com o ONR e corrigir o Cronograma depois.")
    t = celulas["TOTAL"]
    if t["declarado"] is not None and t["situacao"] == "DIFERE_DO_SISTEMA":
        add("TOTAL_DIFERENTE_DO_SISTEMA", "TOTAL", "AJUSTE",
            f"Acervo declarado {n(t['declarado']['valor'])}, o sistema tem {n(t['sistema']['valor'])} fichas numeradas",
            t["sistema"]["nota"])
    for codigo, cel in celulas.items():
        decl = cel["declarado"]
        lido = _dia(decl["lido_em"]) if decl else None
        if lido and (hoje - lido).days > DECLARACAO_ANTIGA_DIAS:
            add("DECLARACAO_ANTIGA", codigo, "AJUSTE",
                f"{COLUNAS[codigo]['rotulo']}: lido em {lido.strftime('%d/%m/%Y')}, há {(hoje - lido).days} dias",
                "Reler a tela do ONR antes de usar este número numa resposta.")
    return saida


def _regra_do_painel(obrigacao: str, celulas: dict[str, dict]) -> dict:
    """O que o painel do ONR mostraria, pela regra OBSERVADA (não é norma)."""
    def v(c):
        d = celulas[c]["declarado"]
        return None if d is None else d["valor"]

    if obrigacao == PROV143:
        total = v("TOTAL")
        cols = [v("L2_DIGITADAS"), v("L2_DIGITALIZADAS"), v("L4"), v("L5")]
        if total is None or any(x is None for x in cols):
            return {"situacao": None, "texto": "faltam números declarados para aplicar a regra"}
        menor = min(min(x, total) for x in cols)
        ok = menor >= total
        return {"situacao": "ADIMPLENTE" if ok else "INADIMPLENTE",
                "texto": f"o menor entre digitadas, digitalizadas, Livro 4 e Livro 5 é {menor:,}".replace(",", ".")
                         + f", contra o acervo declarado de {total:,}".replace(",", ".")}
    if obrigacao == ITN003:
        m = v("ITN_MATRICULAS")
        if m is None:
            return {"situacao": None, "texto": "falta lançar o que o painel mostra"}
        return {"situacao": "ADIMPLENTE" if m > 0 else "INADIMPLENTE",
                "texto": "o painel dá adimplente com ao menos 1 matrícula recebida; a norma ou a Nota "
                         "Técnica podem exigir o acervo inteiro — não prometer que 1 matrícula regulariza"}
    p = v("POLIGONOS")
    if p is None:
        return {"situacao": None, "texto": "falta lançar o que o painel mostra"}
    return {"situacao": "ADIMPLENTE" if p > 0 else "INADIMPLENTE",
            "texto": "o painel dá adimplente com ao menos 1 polígono no Mapa"}


# --------------------------------------------------------------- as pendências

def pendencias(con, hoje: date | None = None, *, todas: bool = False) -> list[dict]:
    """As pendências, com o que falta em cada uma. SÓ LÊ."""
    hoje = hoje or date.today()
    bd = banco(con)
    if not _tabela(bd, "onr_pendencias"):
        return []
    anexos: dict[int, list[dict]] = {}
    if _tabela(bd, "attachments"):
        for a in bd.ler("""SELECT id, entity_id, original_name, sha256, size_bytes, uploaded_at
                             FROM attachments WHERE entity_type = %s ORDER BY id""", (ENTIDADE_DO_ANEXO,)):
            anexos.setdefault(int(a["entity_id"]), []).append(a)
    filtro = "" if todas else "WHERE situacao = 'ABERTA'"
    saida = []
    for r in bd.ler(f"SELECT * FROM onr_pendencias {filtro} ORDER BY (prazo IS NULL), prazo, id"):
        prazo = _dia(r["prazo"])
        aberta = r["situacao"] == ABERTA
        saida.append({
            **r, "anexos": anexos.get(int(r["id"]), []),
            "sem_responsavel": not (r["responsavel"] or "").strip(),
            "sem_prazo": prazo is None,
            "sem_protocolo": not (r["protocolo_onr"] or "").strip(),
            "sem_comprovante": not anexos.get(int(r["id"])),
            "vencida": bool(aberta and prazo and prazo < hoje),
            "dias_para_o_prazo": (prazo - hoje).days if prazo else None,
            "rotulo_da_obrigacao": NOME_DA_OBRIGACAO.get(r["obrigacao"], r["obrigacao"]),
        })
    return saida


def medir(con, hoje: date | None = None, agora: datetime | None = None) -> dict:
    """O painel inteiro: quatro colunas por número, divergências e pendências. SÓ LÊ."""
    hoje = hoje or date.today()
    agora = agora or _agora()
    declaradas = declaracoes_vigentes(con)
    erros: list[str] = []
    try:
        sistema = medir_sistema(con)
    except Exception as erro:                           # noqa: BLE001
        erros.append(f"o sistema não mediu o que existe: {erro}")
        sistema = {c: {"valor": None, "nota": "não deu para medir", "fonte": ""} for c in CODIGOS}
    try:
        entregas = medir_entregas(con)
    except Exception as erro:                           # noqa: BLE001
        erros.append(f"o sistema não mediu o que foi entregue: {erro}")
        entregas = {c: {"valor": None, "fontes": [], "nota": "não deu para medir", "em_andamento": 0,
                        "nao_importado": 0} for c in CODIGOS}
    total_decl = declaradas["TOTAL"]["valor"] if "TOTAL" in declaradas else None
    celulas = {c: _celula(c, declaradas.get(c), sistema[c], entregas[c], total_decl,
                          sistema["TOTAL"]["valor"], hoje) for c in CODIGOS}
    divergencias = _divergencias(celulas, hoje)
    abertas = pendencias(con, hoje)
    obrigacoes = []
    for codigo, nome in OBRIGACOES:
        cols = [celulas[c] for c, d in COLUNAS.items() if d["obrigacao"] == codigo]
        regra = _regra_do_painel(codigo, celulas)
        divs = [d for d in divergencias if d["obrigacao"] == codigo]
        com_declaracao = any(c["declarado"] is not None for c in cols)
        faltas_declaradas = [c for c in cols if c["falta"] and c["declarado"] is not None]
        if not com_declaracao:
            veredito = SEM_DECLARACAO
        elif any(d["gravidade"] == "DIVERGENCIA" for d in divs):
            veredito = DIVERGENTE
        elif regra["situacao"] == "INADIMPLENTE":
            veredito = FALTA
        elif regra["situacao"] is None:
            # a regra do painel não se aplica com número faltando: não acusa e não dá por cumprido
            veredito = INCOMPLETO
        elif faltas_declaradas:
            veredito = FALTA
        elif codigo == PROV195:
            veredito = EM_DIA_NO_PAINEL
        else:
            veredito = EM_DIA
        obrigacoes.append({
            "codigo": codigo, "nome": nome, "colunas": cols, "painel": regra,
            "divergencias": divs, "veredito": veredito, "rotulo_do_veredito": ROTULO_DO_VEREDITO[veredito],
            "pendencias": [p for p in abertas if p["obrigacao"] == codigo],
        })
    return {
        "hoje": hoje.isoformat(), "medido_em": agora.isoformat(sep=" "),
        "obrigacoes": obrigacoes, "pendencias": abertas, "erros": erros,
        "divergencias": divergencias,
        "resumo": {
            "divergencias": sum(1 for d in divergencias if d["gravidade"] == "DIVERGENCIA"),
            "ajustes": sum(1 for d in divergencias if d["gravidade"] == "AJUSTE"),
            "pendencias_abertas": len(abertas),
            "pendencias_vencidas": sum(1 for p in abertas if p["vencida"]),
            "pendencias_incompletas": sum(1 for p in abertas if p["sem_responsavel"] or p["sem_prazo"]
                                          or p["sem_protocolo"] or p["sem_comprovante"]),
            "sem_declaracao": sum(1 for o in obrigacoes if o["veredito"] == SEM_DECLARACAO),
        },
    }


# ------------------------------------------------------------ para o gestor

def _prazo_do_dia(prazo, hoje: date) -> str:
    d = _dia(prazo)
    if d is None:
        return "ATENCAO"
    return "VENCIDO" if d < hoje else "PRAZO"


def achados_para_o_gestor(con, hoje: date) -> list[dict]:
    """O que o painel entrega ao gestor — e, por ele, ao semáforo. SÓ LÊ.

    SEM ALARME FALSO, e sem falso verde:
      * obrigação SEM_DECLARACAO não gera achado: ninguém lançou número, e
        acusar sem número seria inventar. A checklist mostra «sem declaração».
      * DIVERGÊNCIA (declarado sem lastro) → ATENCAO: aparece no número e no
        despacho do oficial, mas não pinta a área. Corrigir o Cronograma é
        decisão dele, não prazo vencido.
      * obrigação em FALTA ou DIVERGENTE **sem nenhuma pendência aberta** → PRAZO
        sem data: o semáforo lê «prazo que não se lê» e deixa a área AMARELA, até
        alguém registrar responsável e prazo.
      * pendência aberta → PRAZO com a data dela; passada a data, VENCIDO
        (vermelho); sem data, ATENCAO.
      * ajustes (declaração abaixo da entrega, total diferente, leitura antiga)
        só aparecem na tela.
    O que o oficial resolve fecha o achado na conferência seguinte, sozinho.
    """
    if not _tabela(banco(con), "onr_declaracoes"):
        return []
    painel = medir(con, hoje)
    achados: list[dict] = []

    def a(chave, regra, gravidade, titulo, detalhe="", prazo=None):
        achados.append({"chave": chave, "regra": regra, "gravidade": gravidade, "setor": "RI",
                        "titulo": titulo, "detalhe": detalhe, "prazo": prazo, "fundamento": FUNDAMENTO})

    for d in painel["divergencias"]:
        if d["gravidade"] == "DIVERGENCIA":
            a(f"ONR_PAINEL_DIV:{d['codigo']}:{d['coluna']}", REGRA_DIVERGENCIA, "ATENCAO",
              f"ONR — {d['titulo']}", d["detalhe"])
    for o in painel["obrigacoes"]:
        if o["veredito"] in (FALTA, DIVERGENTE) and not o["pendencias"]:
            a(f"ONR_PAINEL_OBR:{o['codigo']}", REGRA_OBRIGACAO, "PRAZO",
              f"ONR — {o['nome']}: {o['rotulo_do_veredito'].lower()}, e ninguém tem prazo registrado",
              "Abra uma pendência com responsável, prazo e protocolo do ONR no painel de conformidade.")
    for p in painel["pendencias"]:
        gravidade = _prazo_do_dia(p["prazo"], hoje)
        faltam = [x for x, falta in (("responsável", p["sem_responsavel"]), ("protocolo do ONR", p["sem_protocolo"]),
                                     ("comprovante", p["sem_comprovante"])) if falta]
        a(f"ONR_PAINEL_PEND:{p['id']}", REGRA_PENDENCIA, gravidade,
          f"ONR — pendência: {p['titulo']}" + ("" if p["prazo"] else " (sem prazo)"),
          ("Falta registrar: " + ", ".join(faltam) + ".") if faltam else "", p["prazo"])
    return achados


def contagem_para_a_checklist(con, hoje: date) -> dict:
    """O que a linha «Painel ONR» da checklist mostra: {n, texto}. SÓ LÊ."""
    painel = medir(con, hoje)
    r = painel["resumo"]
    if r["sem_declaracao"] == len(OBRIGACOES):
        return {"n": 0, "texto": "nenhum número lançado ainda: o painel do ONR não aparece no login da "
                                 "serventia, e o que foi declarado precisa ser digitado aqui"}
    n = r["divergencias"] + r["pendencias_vencidas"]
    return {"n": n, "texto": f"{r['divergencias']} número(s) declarado(s) sem lastro, "
                             f"{r['pendencias_abertas']} pendência(s) aberta(s), "
                             f"{r['pendencias_vencidas']} vencida(s)"}


# ------------------------------------------------------------------ lançamentos

def _por(por: str) -> str:
    return _texto(por, "quem lança", obrigatorio=True, limite=120) or ""


def lancar_declaracao(con, *, coluna: str, valor, lido_em: str, origem: str, observacao: str = "",
                      por: str, hoje: date | None = None, agora: datetime | None = None) -> int:
    """Lança o que foi declarado (ou o que o painel mostra). Só acrescenta."""
    hoje, agora = hoje or date.today(), agora or _agora()
    d = COLUNAS.get(str(coluna or "").upper())
    if d is None:
        raise PainelOnrError("Escolha o número a lançar.")
    coluna = str(coluna).upper()
    if d["tipo"] == SIMNAO:
        t = str(valor or "").strip().upper()
        if t not in ("SIM", "NAO", "NÃO", "1", "0"):
            raise PainelOnrError(f"{d['rotulo']}: responda Sim ou Não.")
        n = 1 if t in ("SIM", "1") else 0
    else:
        n = _inteiro(valor, d["rotulo"])
    novo = banco(con).escrever(
        """INSERT INTO onr_declaracoes(obrigacao, coluna, valor, lido_em, origem, observacao,
                                       lancado_em, lancado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (d["obrigacao"], coluna, n, _data(lido_em, "Data em que o número foi lido", hoje),
         _texto(origem, "De onde saiu o número", obrigatorio=True, limite=200),
         _texto(observacao, "Observação", obrigatorio=False, limite=500),
         agora.isoformat(), _por(por)))
    return int(novo[0]["id"])


def anular_declaracao(con, declaracao_id: int, *, motivo: str, por: str,
                      agora: datetime | None = None) -> None:
    agora = agora or _agora()
    bd = banco(con)
    bd.escrever("""UPDATE onr_declaracoes SET anulado_em=%s, anulado_por=%s, anulado_motivo=%s
                    WHERE id=%s AND anulado_em IS NULL""",
                (agora.isoformat(), _por(por),
                 _texto(motivo, "Motivo", obrigatorio=True, limite=300), int(declaracao_id)))
    if not bd.linhas_afetadas:
        raise PainelOnrError("Lançamento não encontrado, ou já anulado.")


def lancar_prova(con, *, coluna: str, quantos, situacao: str, visto_em: str, protocolo_onr: str = "",
                 descricao: str = "", por: str, hoje: date | None = None,
                 agora: datetime | None = None) -> int:
    """Lança uma importação feita no portal. Só IMPORTADO conta como prova."""
    hoje, agora = hoje or date.today(), agora or _agora()
    coluna = str(coluna or "").upper()
    if coluna not in COM_PROVA_INFORMADA:
        raise PainelOnrError("Escolha a coluna a que a importação se refere.")
    situacao = str(situacao or "").upper()
    if situacao not in SITUACOES_DA_PROVA:
        raise PainelOnrError("Escolha a situação que o portal mostra: Processando, Importado ou Não importado.")
    novo = banco(con).escrever(
        """INSERT INTO onr_provas_informadas(obrigacao, coluna, quantos, situacao, visto_em,
                                            protocolo_onr, descricao, lancado_em, lancado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (COLUNAS[coluna]["obrigacao"], coluna, _inteiro(quantos, "Quantos"), situacao,
         _data(visto_em, "Data em que a situação foi vista no portal", hoje),
         _texto(protocolo_onr, "Protocolo do ONR", obrigatorio=False, limite=60),
         _texto(descricao, "Descrição", obrigatorio=False, limite=300), agora.isoformat(), _por(por)))
    return int(novo[0]["id"])


def anular_prova(con, prova_id: int, *, motivo: str, por: str, agora: datetime | None = None) -> None:
    agora = agora or _agora()
    bd = banco(con)
    bd.escrever("""UPDATE onr_provas_informadas SET anulado_em=%s, anulado_por=%s, anulado_motivo=%s
                    WHERE id=%s AND anulado_em IS NULL""",
                (agora.isoformat(), _por(por),
                 _texto(motivo, "Motivo", obrigatorio=True, limite=300), int(prova_id)))
    if not bd.linhas_afetadas:
        raise PainelOnrError("Lançamento não encontrado, ou já anulado.")


def abrir_pendencia(con, *, obrigacao: str, coluna: str = "", titulo: str, responsavel: str = "",
                    prazo: str = "", protocolo_onr: str = "", observacao: str = "", por: str,
                    hoje: date | None = None, agora: datetime | None = None) -> int:
    hoje, agora = hoje or date.today(), agora or _agora()
    obrigacao = str(obrigacao or "").upper()
    if obrigacao not in NOME_DA_OBRIGACAO:
        raise PainelOnrError("Escolha a obrigação da pendência.")
    coluna = str(coluna or "").upper()
    if coluna and (coluna not in COLUNAS or COLUNAS[coluna]["obrigacao"] != obrigacao):
        raise PainelOnrError("A coluna não é desta obrigação.")
    novo = banco(con).escrever(
        """INSERT INTO onr_pendencias(obrigacao, coluna, titulo, responsavel, prazo, protocolo_onr,
                                      observacao, situacao, criada_em, criada_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,'ABERTA',%s,%s) RETURNING id""",
        (obrigacao, coluna or None, _texto(titulo, "O que falta fazer", obrigatorio=True, limite=200),
         _texto(responsavel, "Responsável", obrigatorio=False, limite=120),
         _data(prazo, "Prazo", hoje, futura=True) if str(prazo or "").strip() else None,
         _texto(protocolo_onr, "Protocolo do ONR", obrigatorio=False, limite=60),
         _texto(observacao, "Observação", obrigatorio=False, limite=500), agora.isoformat(), _por(por)))
    return int(novo[0]["id"])


def atualizar_pendencia(con, pendencia_id: int, *, responsavel: str, prazo: str, protocolo_onr: str,
                        observacao: str = "", hoje: date | None = None) -> None:
    """Completa o responsável, o prazo, o protocolo e a observação de uma pendência ABERTA."""
    hoje = hoje or date.today()
    bd = banco(con)
    bd.escrever(
        """UPDATE onr_pendencias SET responsavel=%s, prazo=%s, protocolo_onr=%s, observacao=%s
            WHERE id=%s AND situacao='ABERTA'""",
        (_texto(responsavel, "Responsável", obrigatorio=False, limite=120),
         _data(prazo, "Prazo", hoje, futura=True) if str(prazo or "").strip() else None,
         _texto(protocolo_onr, "Protocolo do ONR", obrigatorio=False, limite=60),
         _texto(observacao, "Observação", obrigatorio=False, limite=500), int(pendencia_id)))
    if not bd.linhas_afetadas:
        raise PainelOnrError("Pendência não encontrada, ou já encerrada.")


def encerrar_pendencia(con, pendencia_id: int, *, situacao: str, motivo: str, por: str,
                       agora: datetime | None = None) -> None:
    agora = agora or _agora()
    situacao = str(situacao or "").upper()
    if situacao not in (CONCLUIDA, CANCELADA):
        raise PainelOnrError("Diga se a pendência foi concluída ou cancelada.")
    bd = banco(con)
    bd.escrever(
        """UPDATE onr_pendencias SET situacao=%s, encerrada_em=%s, encerrada_por=%s, encerrada_motivo=%s
            WHERE id=%s AND situacao='ABERTA'""",
        (situacao, agora.isoformat(), _por(por),
         _texto(motivo, "Motivo", obrigatorio=True, limite=300), int(pendencia_id)))
    if not bd.linhas_afetadas:
        raise PainelOnrError("Pendência não encontrada, ou já encerrada.")


# ----------------------------------------------------------------- comprovantes

EXTENSOES_DO_COMPROVANTE = (".pdf", ".jpg", ".jpeg", ".png")
TAMANHO_MAXIMO_DO_COMPROVANTE = 20 * 1024 * 1024


def guardar_comprovante(con, pendencia_id: int, *, nome_arquivo: str, conteudo: bytes, pasta,
                        usuario_id: int | None, agora: datetime | None = None) -> int:
    """Guarda o comprovante (protocolo, tela do ONR, e-mail do ONR) amarrado à pendência.

    O nome em disco sai do número da pendência e do sha-256: nada do que a
    pessoa digitou vira caminho (só a extensão, de uma lista curta).
    """
    import hashlib
    from pathlib import Path
    agora = agora or _agora()
    bd = banco(con)
    if not bd.um("SELECT 1 AS x FROM onr_pendencias WHERE id = %s", (int(pendencia_id),)):
        raise PainelOnrError("Pendência não encontrada.")
    nome = Path(nome_arquivo or "").name
    extensao = Path(nome).suffix.lower()
    if extensao not in EXTENSOES_DO_COMPROVANTE:
        raise PainelOnrError("Comprovante em PDF ou imagem (JPG, PNG).")
    if not conteudo:
        raise PainelOnrError("O arquivo veio vazio.")
    if len(conteudo) > TAMANHO_MAXIMO_DO_COMPROVANTE:
        raise PainelOnrError("O arquivo passa de 20 MB.")
    sha = hashlib.sha256(conteudo).hexdigest()
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{int(pendencia_id)}_{sha[:16]}{extensao}"
    destino.write_bytes(conteudo)
    novo = bd.escrever(
        "INSERT INTO attachments(entity_type, entity_id, original_name, stored_name, stored_path, "
        "sha256, size_bytes, description, uploaded_by, uploaded_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (ENTIDADE_DO_ANEXO, int(pendencia_id), nome, destino.name, str(destino), sha, len(conteudo),
         "Comprovante de pendência do painel de conformidade do ONR", usuario_id, agora.isoformat()))
    return int(novo[0]["id"])
