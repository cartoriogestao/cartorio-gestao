"""A conferência dos dados do assento do RCPN — termo × campos × pessoas.

    «os ultimos atos de rcpn feitos no sistema sao praticamente todos importados
     por meio de um robo que analisa documentos digitalizadas, verifique se essas
     importacoes estao perfeitas e, nao sendo, vamos criar mecanismos que
     orientem e bloqueiem introducoes deficitarias ou erradas»
    — o oficial, 11/10/2026

DE ONDE VEIO
    O «robô» são scripts que leem a DNV e os documentos digitalizados e gravam
    um RASCUNHO da tela de assento novo (`rascunho_de_tela`) — com o termo já
    redigido — que o balcão abre e lavra. Medido na produção em 11/10/2026, os
    defeitos que chegaram ao livro foram da mesma família, e todos objetivos:

    - **TESTEMUNHA FANTASMA**: o nome do próprio registrado (ou de um genitor)
      gravado como testemunha — o rascunho levava a pessoa duas vezes;
    - **AVÓS DO LADO ERRADO ou com o sexo trocado**: avó paterna gravada como
      materna, avô com sexo F;
    - **O CPF NO CAMPO E FORA DO TERMO** (e o contrário);
    - **MARCA DE RASCUNHO** («[A CONFIRMAR: …]») que pode ir ao livro se o
      balcão lavrar sem resolver.

    E todos foram consertados DEPOIS DE LAVRADO E SELADO, por script que
    reescreve `rc_assentos.teor` e apaga linha de `rc_pessoas` — o termo
    assinado mudou sem averbação. A conferência existe para isso não precisar
    acontecer: o erro tem de parar **antes** da lavratura.

DUAS GRAVIDADES, E A FRONTEIRA É A OBJETIVIDADE
    BLOQUEIA — o dado contradiz a si mesmo e não há leitura em que esteja
      certo: marca de rascunho no termo, mãe com sexo masculino, testemunha que
      é o registrado, DNV do campo diferente da DNV do termo, CPF que não fecha
      o dígito, data de nascimento depois do fato. (A matrícula com dígito
      errado só avisa: a digitada manda, e a composta nunca erra.)
      `lavrar_assento` recusa, com a lista em português de balcão.
    AVISA — pode estar certo e merece olho humano: avós cujo sobrenome não
      aparece no genitor daquele lado, nome do genitor que não está no termo,
      idade declarada que não bate com as datas. Aparece na conferência antes
      de lavrar e na fiscalização diária (`gestor_rcpn`), e não trava.

    Registro de nascimento é imperativo legal (art. 250) e o balcão não pode
    parar por suspeita: só o que é objetivamente errado trava. É a mesma régua
    do `rc_checklist` e das fraudes — o que é julgamento fica com quem assina.

O QUE ELE NÃO FAZ
    Não corrige nada: só lê e devolve a lista. Não compara com a imagem do
    documento (isso é o robô, ou a pessoa); compara o que foi digitado com o
    próprio texto que vai ao livro, que é onde a contradição se vê.
"""
from __future__ import annotations

import re
import sqlite3

from bd_nativo import banco
import unicodedata
from datetime import date
from typing import Any

BLOQUEIA = "BLOQUEIA"
AVISA = "AVISA"

#: Marcas que só existem em rascunho, e que nunca podem ir ao livro.
MARCAS_DE_RASCUNHO = (
    re.compile(r"\[\s*A\s+CONFIRMAR", re.I),
    re.compile(r"\[\s*COMPLETAR", re.I),
    re.compile(r"\[\s*CONFERIR", re.I),
    re.compile(r"\[\s*PREENCHER", re.I),
    re.compile(r"\{\{|\}\}|\{[a-z_]{3,}\}"),
    re.compile(r"(?<![\w.])@[a-z_]{4,}", re.I),
    # O TRAÇO SÓ É MARCA QUANDO ESTÁ NO MEIO DA FRASE — «Eu, ____________,
    # Oficial», «neste Município de ____________». Sozinho na linha ele é o
    # lugar da assinatura à mão («Em testemunho da verdade.» e, na linha de
    # baixo, o traço), e é assim em 624 termos do acervo (medido em 15/09/2026).
    re.compile(r"(?<=[^\s.:;])[ \t]+_{5,}|_{5,}(?=[ \t]*[,;][ \t]*\w)"),
    re.compile(r"\bXXX+\b"),
)

#: O sexo que o papel pede. Quando o PAR inteiro está invertido, trava; um só
#: divergente avisa — ver «O PAR INVERTIDO TRAVA» em `conferir`.
SEXO_DO_PAPEL = {
    "MAE": "F", "PAI": "M",
    "AVO_MATERNA": "F", "AVO_PATERNA": "F",
    "AVO_MATERNO": "M", "AVO_PATERNO": "M",
    "MAE_NUBENTE1": "F", "MAE_NUBENTE2": "F",
    "PAI_NUBENTE1": "M", "PAI_NUBENTE2": "M",
}

#: Papéis que só podem aparecer uma vez no assento.
PAPEIS_UNICOS = ("REGISTRADO", "FALECIDO", "MAE", "PAI", "NUBENTE1", "NUBENTE2",
                 "AVO_MATERNA", "AVO_MATERNO", "AVO_PATERNA", "AVO_PATERNO",
                 "MAE_NUBENTE1", "MAE_NUBENTE2", "PAI_NUBENTE1", "PAI_NUBENTE2")

#: Quem não pode ser testemunha do próprio assento.
NAO_TESTEMUNHA = ("REGISTRADO", "FALECIDO", "NUBENTE1", "NUBENTE2", "MAE", "PAI",
                  "DECLARANTE")

#: O titular do assento: testemunha com o nome dele é a linha fantasma.
TITULARES = ("REGISTRADO", "FALECIDO", "NUBENTE1", "NUBENTE2")

#: De que lado cada avô está — o genitor cujo sobrenome se espera nele.
LADO_DO_AVO = {"AVO_MATERNA": "MAE", "AVO_MATERNO": "MAE",
               "AVO_PATERNA": "PAI", "AVO_PATERNO": "PAI"}

ROTULO = {
    "REGISTRADO": "registrado", "FALECIDO": "falecido", "MAE": "mãe",
    "PAI": "pai", "DECLARANTE": "declarante", "TESTEMUNHA": "testemunha",
    "TESTEMUNHA2": "segunda testemunha",
    "AVO_MATERNA": "avó materna", "AVO_MATERNO": "avô materno",
    "AVO_PATERNA": "avó paterna", "AVO_PATERNO": "avô paterno",
    "NUBENTE1": "1º cônjuge", "NUBENTE2": "2º cônjuge",
    "MAE_NUBENTE1": "mãe do 1º cônjuge", "PAI_NUBENTE1": "pai do 1º cônjuge",
    "MAE_NUBENTE2": "mãe do 2º cônjuge", "PAI_NUBENTE2": "pai do 2º cônjuge",
}

#: Partículas que não identificam família.
_PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "D", "DI", "DU", "JUNIOR",
               "JR", "FILHO", "FILHA", "NETO", "NETA", "SOBRINHO"}


# ------------------------------------------------------------------ miúdos

def _sem_acento(texto: Any) -> str:
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def _so_letras(texto: Any) -> str:
    """Para achar um nome no termo: sem acento, sem apóstrofo, sem pontuação —
    «Xu'Capric» e «Xu’Capric» são o mesmo nome."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", _sem_acento(texto))).strip()


def _digitos(v: Any) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def _vazio(v: Any) -> bool:
    return v is None or str(v).strip() == ""


def _ignorado(v: Any) -> bool:
    return _sem_acento(v) in ("IGNORADO", "IGNORADA", "NAO CONSTA", "NAO TEM",
                              "DESCONHECIDO", "DESCONHECIDA", "NAO DECLARADO")


def _dia(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def _sobrenomes(nome: Any) -> set[str]:
    partes = [p for p in re.split(r"[^A-Z]+", _sem_acento(nome)) if p]
    return {p for p in partes[1:] if p not in _PARTICULAS and len(p) > 2}


def _no_texto(nome: Any, texto_letras: str) -> bool:
    n = _so_letras(nome)
    return bool(n) and n in texto_letras


def _problema(gravidade: str, codigo: str, mensagem: str, campo: str = "") -> dict:
    return {"gravidade": gravidade, "codigo": codigo, "mensagem": mensagem,
            "campo": campo}


def _cpf_valido(v: Any) -> bool:
    import cpf_cnpj
    return cpf_cnpj.cpf_valido(v)


# ------------------------------------------------------------------ a régua

def conferir(dados: dict) -> list[dict]:
    """Confere um assento (novo ou lavrado) dado como dicionário. SÓ LÊ.

    `dados`: especie, nome, data_fato, data_ato, hora_fato, dnv,
    cpf_registrado, matricula, teor, numero, e `pessoas` — lista de dicts com
    papel, nome, sexo, documento_tipo, documento_numero, data_nascimento,
    idade_no_fato. Campo ausente não é erro aqui: a presença é de
    `rc_assento.conferir_requisitos_legais`, que já trava o que falta.
    """
    especie = str(dados.get("especie") or "").upper()
    teor = str(dados.get("teor") or "")
    teor_norm = _sem_acento(teor)
    teor_letras = _so_letras(teor)
    pessoas = [p for p in (dados.get("pessoas") or []) if not _vazio(p.get("nome"))]
    probs: list[dict] = []

    # 1. MARCA DE RASCUNHO NO TERMO — o que nunca pode ir ao livro.
    for marca in MARCAS_DE_RASCUNHO:
        m = marca.search(teor)
        if m:
            ini = max(0, m.start() - 40)
            probs.append(_problema(
                BLOQUEIA, "MARCA_DE_RASCUNHO",
                f"O termo ainda tem marca de rascunho: «…{teor[ini:m.end() + 60].strip()}…». "
                "Resolva com o declarante e reescreva o trecho antes de lavrar.", "teor"))
            break

    # 2. AS PESSOAS — papel, sexo, repetição, testemunha fantasma.
    por_papel: dict[str, list[dict]] = {}
    for p in pessoas:
        por_papel.setdefault(str(p.get("papel") or "").upper(), []).append(p)
    for papel in PAPEIS_UNICOS:
        if len(por_papel.get(papel, [])) > 1:
            nomes = ", ".join(str(p["nome"]) for p in por_papel[papel])
            probs.append(_problema(
                BLOQUEIA, "PAPEL_REPETIDO",
                f"Há {len(por_papel[papel])} pessoas como {ROTULO.get(papel, papel)}: "
                f"{nomes}. O assento tem uma só.", papel))
    # O PAR INVERTIDO TRAVA; UM SÓ DIVERGENTE AVISA. Mãe com sexo M e pai com
    # sexo F ao mesmo tempo é troca — não há leitura em que esteja certo. Um só
    # divergente pode ser dupla maternidade ou dupla paternidade (Provimento
    # CNJ 63/2017), que o assento guarda nos mesmos dois papéis.
    def _sexo(p):
        return str(p.get("sexo") or "").strip().upper()[:1]
    divergentes = []
    for papel, esperado in SEXO_DO_PAPEL.items():
        for p in por_papel.get(papel, []):
            if _sexo(p) in ("M", "F") and _sexo(p) != esperado and not _ignorado(p["nome"]):
                divergentes.append(papel)
    pares = (("MAE", "PAI"), ("AVO_MATERNA", "AVO_MATERNO"),
             ("AVO_PATERNA", "AVO_PATERNO"), ("MAE_NUBENTE1", "PAI_NUBENTE1"),
             ("MAE_NUBENTE2", "PAI_NUBENTE2"))
    trocados = set()
    for a, b in pares:
        if a in divergentes and b in divergentes:
            trocados |= {a, b}
            pa, pb = por_papel[a][0], por_papel[b][0]
            probs.append(_problema(
                BLOQUEIA, "SEXO_DO_PAPEL",
                f"{pa['nome']} ({ROTULO[a]}) está com sexo masculino e {pb['nome']} "
                f"({ROTULO[b]}) com sexo feminino: os papéis estão trocados.", a))
    for papel in divergentes:
        if papel in trocados:
            continue
        p = por_papel[papel][0]
        probs.append(_problema(
            AVISA, "SEXO_DO_PAPEL",
            f"{p['nome']} está como {ROTULO.get(papel, papel)} e com sexo "
            f"{'masculino' if _sexo(p) == 'M' else 'feminino'}. Confira: ou o papel "
            "ou o sexo está trocado (a não ser em dupla maternidade/paternidade).",
            papel))
    nomes_principais = {}
    for papel in NAO_TESTEMUNHA:
        for p in por_papel.get(papel, []):
            if not _ignorado(p["nome"]):
                nomes_principais[_sem_acento(p["nome"])] = papel
    if not _vazio(dados.get("nome")) and especie in ("NASCIMENTO", "OBITO", "NATIMORTO"):
        nomes_principais.setdefault(_sem_acento(dados["nome"]),
                                    "FALECIDO" if especie == "OBITO" else "REGISTRADO")
    # A SEGUNDA TESTEMUNHA DO NASCIMENTO é papel próprio, TESTEMUNHA2 (o
    # registro tardio, 21/10/2026 — LH05); antes ela era a segunda TESTEMUNHA
    # do LD01, e a régua continua a mesma.
    for papel_da_testemunha in ("TESTEMUNHA", "TESTEMUNHA2"):
        for p in por_papel.get(papel_da_testemunha, []):
            quem = nomes_principais.get(_sem_acento(p["nome"]))
            if quem:
                probs.append(_problema(
                    BLOQUEIA if quem in TITULARES else AVISA, "TESTEMUNHA_FANTASMA",
                    f"{p['nome']} está como testemunha e é o(a) "
                    f"{ROTULO.get(quem, quem)} do próprio assento. Tire a "
                    "testemunha ou ponha a pessoa certa.",
                    papel_da_testemunha))

    # 3. DOCUMENTOS E DATAS — o que tem resposta certa.
    cpf = _digitos(dados.get("cpf_registrado"))
    if cpf and not _cpf_valido(cpf):
        probs.append(_problema(BLOQUEIA, "CPF_INVALIDO",
                               f"O CPF do registrado ({dados['cpf_registrado']}) não "
                               "fecha o dígito verificador.", "cpf_registrado"))
    for p in pessoas:
        tipo = _sem_acento(p.get("documento_tipo"))
        num = _digitos(p.get("documento_numero"))
        if num and (tipo == "CPF" or (not tipo and len(num) == 11)) and not _cpf_valido(num):
            probs.append(_problema(
                BLOQUEIA, "CPF_INVALIDO",
                f"O CPF de {p['nome']} ({ROTULO.get(p.get('papel'), p.get('papel'))}: "
                f"{p['documento_numero']}) não fecha o dígito verificador.",
                str(p.get("papel") or "")))
    fato = _dia(dados.get("data_fato"))
    ato = _dia(dados.get("data_ato"))
    if fato and ato and fato > ato:
        probs.append(_problema(BLOQUEIA, "FATO_DEPOIS_DO_ATO",
                               f"A data do fato ({fato:%d/%m/%Y}) é posterior à do "
                               f"registro ({ato:%d/%m/%Y}).", "data_fato"))
    for p in pessoas:
        nasc = _dia(p.get("data_nascimento"))
        papel = str(p.get("papel") or "").upper()
        if nasc and fato and papel not in ("REGISTRADO",) and nasc > fato:
            probs.append(_problema(
                BLOQUEIA, "NASCEU_DEPOIS_DO_FATO",
                f"{p['nome']} ({ROTULO.get(papel, papel)}) nasceu em {nasc:%d/%m/%Y}, "
                f"depois do fato ({fato:%d/%m/%Y}).", papel))
        idade = p.get("idade_no_fato")
        if nasc and fato and not _vazio(idade) and str(idade).strip().isdigit():
            from rc_assento import idade_na_data
            calc = idade_na_data(nasc.isoformat(), fato.isoformat())
            if calc is not None and abs(calc - int(idade)) >= 1:
                probs.append(_problema(
                    AVISA, "IDADE_NAO_BATE",
                    f"{p['nome']}: idade declarada {idade}, mas as datas dão {calc} "
                    f"anos no dia do fato.", papel))
    # A MATRÍCULA AVISA, E NÃO TRAVA: a composta pelo sistema nunca erra o
    # dígito, e a DIGITADA manda (registro transportado, assento antigo) —
    # dígito errado nela é fato do acervo para o oficial ler, como diz
    # `rc_matricula.confere`. Travar aqui desfaria a regra da casa (o teste
    # `test_a_matricula_digitada_manda_e_nao_e_sobrescrita` pegou, 11/10/2026).
    matricula = _digitos(dados.get("matricula"))
    if matricula:
        import rc_matricula
        c = rc_matricula.confere(matricula)
        if not c["ok"]:
            probs.append(_problema(AVISA, "MATRICULA_DV",
                                   f"Matrícula com problema: {c['motivo']}".replace("**", ""),
                                   "matricula"))
        elif not _vazio(dados.get("numero")) and \
                int(c["partes"].get("termo") or 0) != int(_digitos(dados["numero"]) or 0):
            probs.append(_problema(
                AVISA, "MATRICULA_DE_OUTRO_TERMO",
                f"A matrícula aponta o termo {int(c['partes']['termo'])}, e o assento é o "
                f"nº {dados['numero']}.", "matricula"))

    # 4. O TERMO CONTRA OS CAMPOS — só quando há termo escrito.
    if teor_norm:
        dnv = _digitos(dados.get("dnv"))
        if especie == "NASCIMENTO" and dnv and len(dnv) >= 8:
            dnvs_do_termo = {_digitos(m) for m in re.findall(
                r"DNV[^0-9]{0,30}([0-9][0-9.\-/ ]{6,20}[0-9])", teor_norm)}
            if dnvs_do_termo and dnv not in dnvs_do_termo:
                probs.append(_problema(
                    BLOQUEIA, "DNV_DIFERENTE",
                    f"A DNV do campo ({dados['dnv']}) não é a que o termo escreve "
                    f"({', '.join(sorted(dnvs_do_termo))}).", "dnv"))
        if cpf and _cpf_valido(cpf):
            cpfs_do_termo = {_digitos(m) for m in re.findall(
                r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", teor)}
            if cpf not in cpfs_do_termo:
                probs.append(_problema(
                    AVISA, "CPF_FORA_DO_TERMO",
                    f"O CPF do registrado ({dados['cpf_registrado']}) está no campo e "
                    "não está no termo. Se ele foi apresentado no ato, o termo o "
                    "menciona.", "cpf_registrado"))
        hora = str(dados.get("hora_fato") or "").strip()
        if especie == "NASCIMENTO" and re.fullmatch(r"\d{1,2}:\d{2}", hora):
            horas_do_termo = set(re.findall(r"\b(\d{1,2}:\d{2})\b", teor))
            if horas_do_termo and hora not in horas_do_termo and \
                    hora.zfill(5) not in {h.zfill(5) for h in horas_do_termo}:
                probs.append(_problema(
                    BLOQUEIA, "HORA_DIFERENTE",
                    f"A hora do campo ({hora}) não é a que o termo escreve "
                    f"({', '.join(sorted(horas_do_termo))}).", "hora_fato"))
        titular = (_sem_acento(dados.get("nome")) if especie in
                   ("NASCIMENTO", "OBITO", "NATIMORTO") else "")
        if titular and _so_letras(titular) not in teor_letras:
            probs.append(_problema(
                BLOQUEIA, "NOME_FORA_DO_TERMO",
                f"O nome do assento ({dados['nome']}) não aparece no termo.", "nome"))
        for papel in ("MAE", "PAI", "DECLARANTE", "AVO_MATERNA", "AVO_MATERNO",
                      "AVO_PATERNA", "AVO_PATERNO", "NUBENTE1", "NUBENTE2"):
            for p in por_papel.get(papel, []):
                if not _ignorado(p["nome"]) and not _no_texto(p["nome"], teor_letras):
                    probs.append(_problema(
                        AVISA, "PESSOA_FORA_DO_TERMO",
                        f"{p['nome']} ({ROTULO.get(papel, papel)}) está nas pessoas e "
                        "não aparece no termo.", papel))

    # 5. OS AVÓS DO LADO CERTO — heurística, por isso só avisa.
    for papel, lado in LADO_DO_AVO.items():
        for avo in por_papel.get(papel, []):
            genitor = (por_papel.get(lado) or [None])[0]
            outro = (por_papel.get("PAI" if lado == "MAE" else "MAE") or [None])[0]
            if not genitor or _ignorado(avo["nome"]) or _ignorado(genitor["nome"]):
                continue
            s_avo, s_gen = _sobrenomes(avo["nome"]), _sobrenomes(genitor["nome"])
            s_outro = _sobrenomes(outro["nome"]) if outro else set()
            if s_avo and s_gen and not (s_avo & s_gen) and (s_avo & s_outro):
                probs.append(_problema(
                    AVISA, "AVO_DO_OUTRO_LADO",
                    f"{avo['nome']} está como {ROTULO[papel]}, mas o sobrenome é o do(a) "
                    f"{ROTULO['PAI' if lado == 'MAE' else 'MAE']} ({outro['nome']}), e "
                    f"não o do(a) {ROTULO[lado]} ({genitor['nome']}). Confira o lado.",
                    papel))
    return probs


def bloqueios(problemas: list[dict]) -> list[dict]:
    return [p for p in problemas if p["gravidade"] == BLOQUEIA]


def avisos(problemas: list[dict]) -> list[dict]:
    return [p for p in problemas if p["gravidade"] == AVISA]


# ------------------------------------------- a saída de emergência
#
# «permite, em caso de necessidade emergente, fazer no modo bruto» — o oficial,
# 11/10/2026. A trava continua sendo a regra; passar por cima dela é decisão de
# quem responde pela serventia, com o motivo escrito, e fica gravado em
# `rc_lavraturas_forcadas`. O balcão (USER) não força: para ele a saída é
# arrumar o campo ou chamar o oficial.

#: Quem pode lavrar por cima da trava. A guarda é da rota; o domínio exige o
#: motivo e o nome de quem força.
PAPEIS_QUE_FORCAM: tuple[str, ...] = ("ADMIN", "MANAGER")

#: O piso do motivo, em letras. Mais alto que o da recusa de certidão (dez):
#: aqui o motivo explica por que o livro vai receber um dado contraditório.
MOTIVO_MINIMO_LETRAS = 15


def motivo_insuficiente(motivo: Any) -> str:
    """Por que o motivo não basta — ou "" se basta. Só calcula."""
    letras = len(re.sub(r"[^A-Za-z]", "", _sem_acento(motivo or "")))
    if letras < MOTIVO_MINIMO_LETRAS:
        return (f"Para lavrar por cima da trava, escreva o motivo com pelo menos "
                f"{MOTIVO_MINIMO_LETRAS} letras: ele fica gravado ao lado do "
                f"assento e aparece na fiscalização do RCPN.")
    return ""


def mensagem_de_recusa(problemas: list[dict]) -> str:
    """O texto da recusa da lavratura, em português de balcão."""
    itens = bloqueios(problemas)
    linhas = "; ".join(p["mensagem"] for p in itens)
    return (f"O assento não foi lavrado: {len(itens)} dado(s) se contradizem — "
            f"{linhas} Corrija na tela (ou no rascunho) e lavre de novo. Nada foi "
            "gravado.")


# ------------------------------------------------------- os adaptadores

def dados_do_assento(con: sqlite3.Connection, assento_id: int) -> dict:
    """O dicionário de `conferir` a partir de um assento gravado. SÓ LÊ."""
    bd = banco(con)
    a = bd.um("SELECT * FROM rc_assentos WHERE id = %s", (assento_id,))
    if not a:
        return {}
    d = dict(a)
    d["pessoas"] = [dict(p) for p in bd.ler(
        "SELECT * FROM rc_pessoas WHERE assento_id = %s ORDER BY ordem, id", (assento_id,))]
    return d


def conferir_assento(con: sqlite3.Connection, assento_id: int) -> list[dict]:
    return conferir(dados_do_assento(con, assento_id))


def dados_do_formulario(valores: dict, *, especie: str = "", data_ato: Any = None,
                        assina_depois: bool = False) -> dict:
    """O dicionário de `conferir` a partir dos campos da tela de assento novo —
    o formulário enviado ou o rascunho guardado (os nomes são os mesmos).

    As pessoas saem pelos mesmos prefixos que `rc_assento.PREFIXO_DO_PAPEL`
    declara, e a gaveta só com o tipo de documento não conta como pessoa (o
    `<select>` manda «CPF» em toda gaveta — a causa da testemunha fantasma).

    `assina_depois`: o rascunho ainda não sabe quem assina — a TELA de lavrar
    põe o nome no traço «Eu, ____» (`_teor_com_quem_assina`). Ali o traço não
    é defeito do rascunho; quem lavra por script sem a tela, sim.
    """
    import rc_assento as RC
    v = {k: ("" if x is None else str(x)) for k, x in (valores or {}).items()}
    especie = (especie or v.get("especie") or "").strip().upper()
    pessoas = []
    for papel in RC.PAPEIS_DA_ESPECIE.get(especie, ()):
        # A SEGUNDA TESTEMUNHA tem gaveta própria e o mesmo papel (LD01) —
        # menos no NASCIMENTO, onde a gaveta grava TESTEMUNHA2 (o tardio).
        for prefixo in RC.prefixos_do_papel(papel, especie):
            campos = {c: v.get(f"{prefixo}_{c}", "").strip()
                      for c in RC.CAMPOS_DA_PESSOA}
            if not any(x for c, x in campos.items() if c != "documento_tipo"):
                continue
            pessoas.append({"papel": papel,
                            **{c: x for c, x in campos.items() if x}})
    nome = (v.get("nome") or v.get("pessoa_nome") or "").strip()
    if not nome and v.get("nubente1_nome"):
        nome = " e ".join(x for x in (v.get("nubente1_nome"), v.get("nubente2_nome")) if x)
    teor = v.get("teor") or ""
    if assina_depois:
        teor = re.sub(r"Eu,[ \t]*_{5,}", "Eu, QUEM ASSINA", teor)
    return {"especie": especie, "nome": nome, "data_fato": v.get("data_fato"),
            "data_ato": data_ato, "teor": teor, "matricula": v.get("matricula"),
            "dnv": v.get("dnv"), "hora_fato": v.get("hora_fato"),
            "cpf_registrado": v.get("cpf_registrado") or v.get("pessoa_documento_numero"),
            "pessoas": pessoas}


# ------------------------------------------------- arrumar só o que travou

#: O que se edita para resolver cada problema: (sufixo do campo da pessoa) ou
#: o nome do campo do formulário. O pedido do oficial (11/10/2026): «ao recusar
#: por bloqueio de lavratura, permitir apenas arrumar o problema».
_SUFIXO_DO_CODIGO = {
    "SEXO_DO_PAPEL": ("sexo",),
    "CPF_INVALIDO": ("documento_numero",),
    "PAPEL_REPETIDO": ("nome",),
    "TESTEMUNHA_FANTASMA": ("nome", "documento_numero"),
    "NASCEU_DEPOIS_DO_FATO": ("data_nascimento",),
    "IDADE_NAO_BATE": ("idade_no_fato", "data_nascimento"),
}
_CAMPOS_DO_CODIGO = {
    "MARCA_DE_RASCUNHO": ("teor",),
    "NOME_FORA_DO_TERMO": ("pessoa_nome", "teor"),
    "PESSOA_FORA_DO_TERMO": ("teor",),
    "DNV_DIFERENTE": ("dnv", "teor"),
    "HORA_DIFERENTE": ("hora_fato", "teor"),
    "FATO_DEPOIS_DO_ATO": ("data_fato",),
    "CPF_FORA_DO_TERMO": ("cpf_registrado", "teor"),
    "MATRICULA_DV": ("matricula",),
    "MATRICULA_DE_OUTRO_TERMO": ("matricula",),
}
_PAR_DO_PAPEL = {"MAE": "PAI", "PAI": "MAE", "AVO_MATERNA": "AVO_MATERNO",
                 "AVO_MATERNO": "AVO_MATERNA", "AVO_PATERNA": "AVO_PATERNO",
                 "AVO_PATERNO": "AVO_PATERNA", "MAE_NUBENTE1": "PAI_NUBENTE1",
                 "PAI_NUBENTE1": "MAE_NUBENTE1", "MAE_NUBENTE2": "PAI_NUBENTE2",
                 "PAI_NUBENTE2": "MAE_NUBENTE2"}
_ROTULO_DO_CAMPO = {"teor": "Teor do registro", "pessoa_nome": "Nome do registrado",
                    "dnv": "DNV", "hora_fato": "Hora do fato", "data_fato": "Data do fato",
                    "cpf_registrado": "CPF do registrado", "matricula": "Matrícula",
                    "sexo": "sexo", "documento_numero": "documento",
                    "nome": "nome", "data_nascimento": "data de nascimento",
                    "idade_no_fato": "idade na ocasião"}


def campos_para_corrigir(problemas: list[dict], *, so_os_que_travam: bool = True) -> list[dict]:
    """Os campos do formulário que resolvem os problemas, sem repetição, na
    ordem em que aparecem. SÓ CALCULA.

    Cada item: `campo` (o nome do campo da tela), `rotulo` e `por_que` (as
    mensagens que o pedem). Quem desenha a tela põe ESTES campos para editar e
    todos os outros escondidos, como estavam — arrumar não é redigitar.
    """
    import rc_assento as RC
    saida: dict[str, dict] = {}

    def pede(campo: str, rotulo: str, mensagem: str) -> None:
        item = saida.setdefault(campo, {"campo": campo, "rotulo": rotulo, "por_que": []})
        if mensagem not in item["por_que"]:
            item["por_que"].append(mensagem)

    for p in problemas:
        if so_os_que_travam and p["gravidade"] != BLOQUEIA:
            continue
        codigo, alvo = p["codigo"], str(p.get("campo") or "")
        if codigo in _SUFIXO_DO_CODIGO and alvo.upper() in RC.PREFIXO_DO_PAPEL:
            papeis = [alvo.upper()]
            if codigo == "SEXO_DO_PAPEL" and alvo.upper() in _PAR_DO_PAPEL:
                papeis.append(_PAR_DO_PAPEL[alvo.upper()])
            for papel in papeis:
                prefixo = RC.PREFIXO_DO_PAPEL[papel]
                for sufixo in _SUFIXO_DO_CODIGO[codigo]:
                    pede(f"{prefixo}_{sufixo}",
                         f"{ROTULO.get(papel, papel).capitalize()} — "
                         f"{_ROTULO_DO_CAMPO.get(sufixo, sufixo)}", p["mensagem"])
        elif codigo == "CPF_INVALIDO" and alvo == "cpf_registrado":
            pede("cpf_registrado", _ROTULO_DO_CAMPO["cpf_registrado"], p["mensagem"])
        else:
            for campo in _CAMPOS_DO_CODIGO.get(codigo, ()):
                pede(campo, _ROTULO_DO_CAMPO.get(campo, campo), p["mensagem"])
    return list(saida.values())
