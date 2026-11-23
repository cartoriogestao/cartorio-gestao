# -*- coding: utf-8 -*-
"""A fila de conferência que leva as fichas à prontidão dos Livros 4 e 5.

**A MÁQUINA SUGERE, E SÓ UMA PESSOA GRAVA.** Estes dados vão a um índice
nacional. `gerar` lê as fichas e escreve apenas nas tabelas `ri_ff_*`. As únicas
funções que escrevem em `ri_matriculas` ou `ri_partes` são `aceitar`, `corrigir`,
`aceitar_lote` e `desfazer`, e todas recebem quem confirmou.

**A LEITURA NÃO É NOVA.** O endereço vem de `onr_endereco_do_teor.propor` e de
`onr_indicador_xml.completar_ficha`; o que falta para subir, de
`ri_onr_central.montar_indicador`. Aqui se decide só de onde veio cada valor.

**A REGRA DA CASA NASCE DESLIGADA.** Bairro «Zona Rural», número «0», CEP geral,
tipo pelo padrão e semelhantes não são leitura do livro. Enquanto o titular não
ligar `ri_fila_regra_casa`, esses valores não aparecem como opção nem são
aceitos, ainda que alguém os envie no formulário. **Na dúvida sobre a origem, o
valor conta como regra da casa.**

**ENCERRAR NÃO É CORREÇÃO DE CADASTRO.** A ficha cujo teor cita encerramento, e a
que tem situação incoerente, fica `SINALIZADA` para o oficial: a fila não aceita
nada nela e não muda a situação de matrícula nenhuma.

**LOTE SÓ NO LIVRO 4, SÓ EM CONFIANÇA ALTA, SÓ DEPOIS DE AMOSTRA SEM ERRO, E SÓ
EM CAMPO VAZIO.** Documento de pessoa não entra em lote.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Iterable, Mapping

from bd_nativo import banco
import cpf_cnpj as CC
import onr_api as API
import onr_endereco_do_teor as E
import onr_indicador_xml as XML
import onr_ir_inteiro as IR
import ri_correcoes as COR
import ri_onr_central as ONR

CHAVE_REGRA_CASA = "ri_fila_regra_casa"
TAMANHO_DA_AMOSTRA = 100

LIVRO_REAL = "4"
LIVRO_PESSOAL = "5"

# Classes
PRONTA = "PRONTA"
TEOR = "TEOR"
REGRA_CASA = "REGRA_CASA"
PESSOA = "PESSOA"
DOC_TEOR = "DOC_TEOR"
NOME_DA_CLASSE = {
    PRONTA: "Prontas",
    TEOR: "Corrigíveis pelo teor",
    REGRA_CASA: "Corrigíveis pela regra da casa",
    PESSOA: "Precisam de pessoa",
    DOC_TEOR: "CPF/CNPJ sugerido pelo teor",
}

# Situações
A_CONFERIR = "A_CONFERIR"
ACEITA = "ACEITA"
CORRIGIDA = "CORRIGIDA"
PULADA = "PULADA"
SINALIZADA = "SINALIZADA"
JA_PRONTA = "JA_PRONTA"
FORA = "FORA"
NOME_DA_SITUACAO = {
    A_CONFERIR: "A conferir",
    ACEITA: "Aceita",
    CORRIGIDA: "Corrigida",
    PULADA: "Pulada",
    SINALIZADA: "Só o oficial",
    JA_PRONTA: "Já pronta",
    FORA: "Saiu do universo",
}
ABERTAS = (A_CONFERIR, PULADA)
DECIDIDAS = (ACEITA, CORRIGIDA)

# Prioridade do RI007
P_CONFLITO_UR = 1
P_MUNICIPIO = 2
P_ENCERRAMENTO = 3
P_DEMAIS = 4
NOME_DA_PRIORIDADE = {
    P_CONFLITO_UR: "1 · Urbano/rural em conflito",
    P_MUNICIPIO: "2 · Município divergente",
    P_ENCERRAMENTO: "3 · Cita encerramento (só o oficial)",
    P_DEMAIS: "4 · Demais",
}

# Origem do valor
ORIGEM_TEOR = "TEOR"
ORIGEM_REGRA = "REGRA_CASA"
ORIGEM_MANUAL = "MANUAL"
ORIGEM_DESFAZER = "DESFAZER"

CAMPOS_DA_PARTE = ("documento_numero", "documento_tipo", "documento_valido")
ROTULO_DO_CAMPO = {**E.ROTULO_DO_CAMPO, "documento_numero": "CPF/CNPJ"}

CITA_ENCERRAMENTO = re.compile(
    r"matr[ií]cula fica encerrada|fica encerrada a presente|"
    r"encerrad[ao] (?:esta )?matr[ií]cula|"
    r"encerramento (?:da presente |desta )?matr[ií]cula|"
    r"matr[ií]cula (?:fica )?(?:unificada|esgotada)", re.IGNORECASE)
RE_DOCUMENTO = re.compile(
    r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
JANELA_DO_DOCUMENTO = 300
MENOR_NOME = 6
MOTIVO_MINIMO = 10


class FilaError(ValueError):
    """Recusa de regra, com a frase pronta para a tela."""


def _txt(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _json(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _de_json(v: Any, padrao: Any) -> Any:
    try:
        return json.loads(v) if v else padrao
    except (TypeError, ValueError):
        return padrao


def regra_ligada(settings: Mapping[str, Any]) -> bool:
    """Só o valor exato «1» liga. Ausente ou qualquer outro é desligado."""
    return _txt(settings.get(CHAVE_REGRA_CASA)) == "1"


def cns_da_casa(settings: Mapping[str, Any]) -> str:
    return _txt(settings.get("ri_cns")) or _txt(settings.get("serventia_cns"))


# ═══════════════════════════════════════════════════════════ de onde veio


def _origem_do_campo(campo: str, de_onde: str, marca_completar: str,
                     cidade_da_casa: bool) -> str:
    """TEOR só quando a frase prova que é leitura. O resto é regra da casa."""
    d = _txt(de_onde)
    if marca_completar == "regra" or not d:
        return ORIGEM_REGRA
    if campo in ("cep", "tipo_imovel"):
        return ORIGEM_REGRA
    if campo == "uf":
        # O teor quase nunca escreve a UF: ela vale pela cidade da circunscrição.
        return ORIGEM_TEOR if cidade_da_casa else ORIGEM_REGRA
    if campo == "numero_predial":
        return ORIGEM_REGRA if "«0»" in d else ORIGEM_TEOR
    if campo == "bairro":
        return ORIGEM_REGRA if d.startswith("imóvel rural") else ORIGEM_TEOR
    if campo == "cidade":
        return ORIGEM_TEOR if d.startswith("teor:") else ORIGEM_REGRA
    if campo == "area_valor":
        return (ORIGEM_TEOR if d.startswith("teor:") and "a casa lê" not in d
                else ORIGEM_REGRA)
    if campo == "area_unidade":
        return ORIGEM_REGRA if "a casa lê" in d or d.startswith("unidade da coluna") \
            else ORIGEM_TEOR
    if campo == "rural_urbano":
        return ORIGEM_TEOR if d.startswith("teor:") else ORIGEM_REGRA
    if campo == "logradouro":
        return ORIGEM_TEOR
    return ORIGEM_REGRA


def _iguais(campo: str, a: str, b: str, m: Mapping[str, Any]) -> bool:
    if campo == "rural_urbano":
        return a.upper()[:1] == b.upper()[:1]
    if campo == "cep":
        return re.sub(r"\D", "", a) == re.sub(r"\D", "", b)
    if campo == "area_valor":
        return API.area_em_metros(a, m.get("area_unidade")) == API.area_em_metros(b, "m2")
    if campo == "area_unidade":
        # A unidade só diverge de verdade quando a área diverge.
        return True
    return API.sem_acento(a) == API.sem_acento(b)


def _campos_da_ficha(m: Mapping[str, Any], p: Mapping[str, Any] | None,
                     ficha: Mapping[str, Any], marcas_completar: Mapping[str, str],
                     padrao: Mapping[str, Any]) -> list[dict]:
    """Uma linha por campo: atual × sugerido × origem × trecho."""
    lidos = dict((p or {}).get("campos") or {})
    de_onde = dict((p or {}).get("de_onde") or {})
    if "maior" in _txt(((p or {}).get("area") or {}).get("de_onde")).lower():
        # «Área maior» é a da gleba de origem, e não a deste imóvel.
        lidos.pop("area_valor", None)
        lidos.pop("area_unidade", None)
    conhecidas = {API.sem_acento(c) for c in (padrao.get("ceps") or {})}
    cidade_final = _txt(ficha.get("cidade"))
    cidade_da_casa = bool(cidade_final) and API.sem_acento(cidade_final) in conhecidas and (
        bool(_txt(m.get("cidade"))) or _txt(de_onde.get("cidade")).startswith("teor:"))
    linhas = []
    for campo in E.CAMPOS:
        atual = _txt(m.get(campo))
        final = _txt(ficha.get(campo))
        lido = _txt(lidos.get(campo))
        marca = _txt(marcas_completar.get(campo))
        conflito = False
        if not atual:
            sugerido = final if not marca.startswith("fora") else ""
        elif final and final != atual:
            sugerido, conflito = final, True  # trocaria o que a ficha já tem
        elif lido and not _iguais(campo, atual, lido, m):
            sugerido, conflito = lido, True
        else:
            sugerido = ""
        origem = (_origem_do_campo(campo, _txt(de_onde.get(campo)), marca, cidade_da_casa)
                  if sugerido else "")
        if campo == "area_valor" and marca == "limpo":
            origem = ORIGEM_REGRA  # número limpo pela máquina, na unidade que a ficha já tem
        trecho = _txt(de_onde.get(campo)) if sugerido else ""
        if campo == "uf" and origem == ORIGEM_TEOR:
            trecho = f"UF da serventia, pela cidade: {cidade_final}"
        linhas.append({"campo": campo, "atual": atual, "sugerido": sugerido,
                       "origem": origem, "trecho": trecho, "conflito": conflito})
    _amarrar_a_area(linhas, limpa=_txt(marcas_completar.get("area_valor")) == "limpo",
                    origem_da_unidade=_origem_do_campo(
                        "area_unidade", _txt(de_onde.get("area_unidade")), "", cidade_da_casa))
    return linhas


def _amarrar_a_area(linhas: list[dict], *, limpa: bool, origem_da_unidade: str) -> None:
    """Número e unidade são um dado só.

    A leitura sai em m². Gravar esse número numa ficha que continua dizendo «ha»
    multiplicaria a área por dez mil. Por isso a sugestão traz os dois, com a
    mesma origem, ou não traz nenhum.
    """
    valor = next(c for c in linhas if c["campo"] == "area_valor")
    unidade = next(c for c in linhas if c["campo"] == "area_unidade")
    if limpa:
        unidade.update(sugerido="", origem="", trecho="", conflito=False)
        return
    if not valor["sugerido"]:
        unidade.update(sugerido="", origem="", trecho="", conflito=False)
        return
    origem = ORIGEM_REGRA if ORIGEM_REGRA in (valor["origem"], origem_da_unidade) else ORIGEM_TEOR
    troca_unidade = bool(unidade["atual"]) and unidade["atual"].lower() != "m2"
    unidade.update(sugerido="m2", origem=origem,
                   trecho=unidade["trecho"] or "a leitura da área sai em m²",
                   conflito=valor["conflito"] or troca_unidade)
    valor["origem"] = origem
    valor["conflito"] = valor["conflito"] or troca_unidade


# ═══════════════════════════════════════════════════════════ a classe


def _marcas_dos_avisos(avisos: Iterable[str], conhecidas: set[str]) -> set[str]:
    fl: set[str] = set()
    for a in avisos:
        if a.startswith("A ficha diz «"):
            achado = re.search(r"«\s*(?:munic[ií]pio|cidade)\s*de\s+([^»]*)»", a, re.I)
            nome = API.sem_acento(re.sub(r"\s+", " ", achado.group(1) if achado else "").strip())
            truncado = len(nome) >= 3 and any(c.startswith(nome) for c in conhecidas)
            fl.add("MUNICIPIO_TRUNCADO" if truncado else "MUNICIPIO_FORA")
        elif a.startswith("**O teor diz"):
            fl.add("UR_DIVERGE")
        elif a.startswith("O nome do imóvel saiu da frase mais fraca"):
            fl.add("NOME_FRACO")
        elif a.startswith("**O teor não diz o nome"):
            fl.add("SEM_NOME_IMOVEL")
        elif a.startswith("A ficha mede a área em **alqueire"):
            fl.add("AREA_ALQUEIRE")
        elif a.startswith("A ficha não diz a via"):
            fl.add("SEM_VIA")
    return fl


MARCAS_DE_PESSOA = frozenset({
    "UR_INDEFINIDO", "UR_DIVERGE", "MUNICIPIO_FORA", "SEM_NOME_IMOVEL", "CONFIANCA_BAIXA",
    "SEM_TEOR", "BLOCO_NAO_ACHADO", "SITUACAO_INCOERENTE", "CITA_ENCERRAMENTO", "SEM_DONO",
    "SEM_VIA"})
MARCAS_DE_REGRA = frozenset({
    "REGRA_BAIRRO", "REGRA_LOGRADOURO", "REGRA_NUMERO", "REGRA_URBANO_RURAL", "NOME_FRACO",
    "AREA_ALQUEIRE"})


def classificar(m: Mapping[str, Any], p: Mapping[str, Any] | None,
                marcas_completar: Mapping[str, str], *, pronta: bool, sem_dono: bool,
                padrao: Mapping[str, Any]) -> tuple[str, int, list[str]]:
    """Classe, prioridade e marcas, com as réguas do RI007. SÓ CALCULA."""
    conhecidas = {API.sem_acento(c) for c in (padrao.get("ceps") or {})}
    fl = _marcas_dos_avisos((p or {}).get("avisos") or [], conhecidas)
    for campo, marca in (("bairro", "REGRA_BAIRRO"), ("logradouro", "REGRA_LOGRADOURO"),
                         ("numero_predial", "REGRA_NUMERO"),
                         ("rural_urbano", "REGRA_URBANO_RURAL")):
        if marcas_completar.get(campo) == "regra":
            fl.add(marca)
    if (p or {}).get("confianca") == "baixa":
        fl.add("CONFIANCA_BAIXA")
    if (p or {}).get("divergente"):
        fl.add("UR_DIVERGE")
    coluna = _txt(m.get("rural_urbano")).upper()[:1]
    letra = coluna if coluna in ("R", "U") else ((p or {}).get("localizacao") or {}).get("letra")
    if letra is None:
        fl.add("UR_INDEFINIDO")
    teor = _txt(m.get("teor"))
    if not teor:
        fl.add("SEM_TEOR")
    elif not (p or {}).get("achou_a_marca"):
        fl.add("BLOCO_NAO_ACHADO")
    incoerente = _txt(m.get("situacao")).upper() == "ENCERRADA"
    if incoerente:
        fl.add("SITUACAO_INCOERENTE")
    elif CITA_ENCERRAMENTO.search(teor):
        fl.add("CITA_ENCERRAMENTO")
    if sem_dono:
        fl.add("SEM_DONO")

    if pronta:
        classe = PRONTA
    elif fl & MARCAS_DE_PESSOA:
        classe = PESSOA
    elif fl & MARCAS_DE_REGRA:
        classe = REGRA_CASA
    else:
        classe = TEOR

    if fl & {"CITA_ENCERRAMENTO", "SITUACAO_INCOERENTE"}:
        prioridade = P_ENCERRAMENTO
    elif "UR_DIVERGE" in fl:
        prioridade = P_CONFLITO_UR
    elif "MUNICIPIO_FORA" in fl:
        prioridade = P_MUNICIPIO
    else:
        prioridade = P_DEMAIS
    return classe, prioridade, sorted(fl)


def _confianca_do_item(classe: str, p: Mapping[str, Any] | None, campos: list[dict]) -> str:
    """`alta` quer dizer «não há o que olhar»: nenhum conflito, nenhuma ressalva."""
    if classe == PESSOA or not p:
        return "baixa"
    confianca = p.get("confianca") or "media"
    if confianca == "alta" and any(c["conflito"] for c in campos):
        return "media"
    return confianca


def _fatia(classe: str, ficha: Mapping[str, Any], m: Mapping[str, Any]) -> str:
    """Amostra-se por classe, zona e estilo: o teor do E-Ofício não é o da transcrição."""
    zona = _txt(ficha.get("rural_urbano")).upper()[:1] or "?"
    estilo = "EOFICIO" if _txt(m.get("origem")).upper().startswith("EOFICIO") else "OUTRAS"
    return f"{classe}|{zona}|{estilo}"


def nome_da_fatia(fatia: str) -> str:
    partes = (fatia.split("|") + ["", ""])[:3]
    zona = {"R": "rural", "U": "urbana"}.get(partes[1], "sem zona")
    estilo = "E-Ofício" if partes[2] == "EOFICIO" else "outras origens"
    return f"{NOME_DA_CLASSE.get(partes[0], partes[0])} · {zona} · {estilo}"


# ═══════════════════════════════════════════════════════════ o documento


def _norm(s: Any) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or ""))
                   if unicodedata.category(c) != "Mn").lower()


def _norm_com_mapa(texto: str) -> tuple[str, list[int]]:
    """O texto sem acento e, para cada letra, a posição no original."""
    saida: list[str] = []
    mapa: list[int] = []
    for i, ch in enumerate(texto):
        for x in _norm(ch):
            saida.append(x)
            mapa.append(i)
    mapa.append(len(texto))
    return "".join(saida), mapa


def sugerir_documento(teor: str, nome: Any, *, texto_norm: str | None = None,
                      mapa: list[int] | None = None) -> dict | None:
    """O primeiro CPF/CNPJ válido logo depois do nome. SÓ CALCULA."""
    alvo = _norm(nome).strip()
    if len(alvo) < MENOR_NOME or not teor:
        return None
    if texto_norm is None or mapa is None:
        texto_norm, mapa = _norm_com_mapa(teor)
    for achado in re.finditer(re.escape(alvo), texto_norm):
        inicio, fim = mapa[achado.start()], mapa[achado.end()]
        janela = teor[fim: fim + JANELA_DO_DOCUMENTO]
        for d in RE_DOCUMENTO.finditer(janela):
            digitos = CC.so_digitos(d.group(0))
            if CC.documento_valido(digitos) is True:
                return {"documento": digitos,
                        "trecho": " ".join(teor[max(inicio - 40, 0): fim + d.end() + 30].split()),
                        "entre": janela[:d.start()]}
    return None


def _outra_pessoa(nome: str, outro: str) -> bool:
    """Grafia diferente da mesma pessoa mantém o primeiro e o último nome."""
    a, b = nome.split(), outro.split()
    return not (a[:1] == b[:1] and a[-1:] == b[-1:])


def avaliar_documento(sug: Mapping[str, Any], parte: Mapping[str, Any],
                      da_ficha: list[dict], donos_do_doc: Mapping[str, set]
                      ) -> tuple[str, list[str]]:
    """A confiança da sugestão e o alerta. O erro típico é pegar o CPF do cônjuge.

    O sinal forte é o número já gravado para **outra pessoa**. Outra parte escrita
    entre o nome e o número, sozinha, é comum e não indica erro; junto do sinal
    forte, indica. A confiança ordena a fila: **documento nunca vai em lote**.
    """
    nome = _norm(parte.get("nome")).strip()
    entre = _norm(sug["entre"])
    outra_no_meio = None
    for outra in da_ficha:
        outro = _norm(outra.get("nome")).strip()
        if outra.get("id") != parte.get("id") and outro != nome \
                and len(outro) >= MENOR_NOME and outro in entre:
            outra_no_meio = outra.get("nome")
            break
    de_outro = any(_outra_pessoa(nome, n) for n in donos_do_doc.get(sug["documento"], set())
                   if n != nome)
    if not de_outro:
        return "alta", []
    alertas = ["Este número já está gravado para outra pessoa no sistema. Confira no teor "
               "de quem ele é."]
    if outra_no_meio:
        alertas.append(f"Entre o nome e o número aparece outra parte: {outra_no_meio}. "
                       "O número provavelmente é dela.")
        return "baixa", alertas
    return "media", alertas


# ═══════════════════════════════════════════════════════════ gerar


def _assinatura(item: Mapping[str, Any]) -> str:
    base = {k: item[k] for k in ("classe", "prioridade", "confianca", "fatia", "marcas",
                                 "campos", "avisos")}
    return hashlib.sha256(_json(base).encode("utf-8")).hexdigest()


def _situacao_inicial(classe: str, marcas: list[str]) -> str:
    if set(marcas) & {"CITA_ENCERRAMENTO", "SITUACAO_INCOERENTE"}:
        return SINALIZADA
    return JA_PRONTA if classe == PRONTA else A_CONFERIR


def _guardar(bd: Any, item: dict, agora: str, ligada: bool) -> str:
    """Grava a sugestão. **Decisão de pessoa não é apagada por uma nova leitura.**"""
    item["assinatura"] = _assinatura(item)
    ja = bd.um("SELECT id, situacao, assinatura FROM ri_ff_itens "
               "WHERE livro=%s AND matricula_id=%s AND parte_id=%s FOR UPDATE",
               (item["livro"], item["matricula_id"], item["parte_id"]))
    situacao = _situacao_inicial(item["classe"], item["marcas"])
    valores = (item["classe"], item["prioridade"], item["confianca"], item["fatia"],
               _json(item["marcas"]), _json(item["campos"]), _json(item["avisos"]),
               item["bloco"], item["assinatura"], int(item["pronta"]))
    if not ja:
        bd.escrever(
            "INSERT INTO ri_ff_itens (classe, prioridade, confianca, fatia, marcas, campos, "
            " avisos, bloco, assinatura, pronta, livro, matricula_id, parte_id, situacao, "
            " calculado_em) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (*valores, item["livro"], item["matricula_id"], item["parte_id"], situacao, agora))
        return "novo"
    if ja["situacao"] in DECIDIDAS:
        falta_regra = ligada and not item["pronta"] and any(
            not c["atual"] and c["sugerido"] and c["origem"] == ORIGEM_REGRA
            for c in item["campos"])
        if not falta_regra:
            bd.escrever("UPDATE ri_ff_itens SET pronta=%s WHERE id=%s",
                        (int(item["pronta"]), ja["id"]))
            return "decidido"
        situacao = A_CONFERIR  # a regra foi ligada: resta o que antes estava oculto
    elif ja["assinatura"] == item["assinatura"] and ja["situacao"] != FORA:
        return "igual"
    elif ja["situacao"] == PULADA and situacao == A_CONFERIR:
        situacao = PULADA
    bd.escrever(
        "UPDATE ri_ff_itens SET classe=%s, prioridade=%s, confianca=%s, fatia=%s, marcas=%s, "
        " campos=%s, avisos=%s, bloco=%s, assinatura=%s, pronta=%s, situacao=%s, "
        " amostra_id=NULL, calculado_em=%s WHERE id=%s",
        (*valores, situacao, agora, ja["id"]))
    return "atualizado"


def _item_do_livro4(con: Any, m: dict, partes: list[dict], atos: dict, informados: list[dict],
                    padrao: dict, settings: dict, cns: str) -> dict:
    proposta = None
    if _txt(m.get("teor")):
        try:
            proposta = E.propor(m, settings=settings, padrao=padrao)
        except Exception:  # noqa: BLE001 — uma ficha ilegível vira «pessoa», e não derruba a fila
            proposta = None
    ficha, marcas_completar = XML.completar_ficha(m, proposta, padrao)
    com_informados = list(partes)
    nomes = {_txt(p.get("nome")) for p in partes}
    for d in informados:
        if d["nome"] not in nomes:
            com_informados.append({"nome": d["nome"], "documento_numero": d["documento"],
                                   "papel": "proprietario", "proprietario": 1,
                                   "proprietario_ativo": 1})
    donos, _ = XML.donos_presumidos(com_informados, atos)
    pronta = bool(ONR.montar_indicador(con, m["id"], cns=cns)["pronto"])
    classe, prioridade, marcas = classificar(m, proposta, marcas_completar, pronta=pronta,
                                             sem_dono=not donos, padrao=padrao)
    campos = _campos_da_ficha(m, proposta, ficha, marcas_completar, padrao)
    return {"livro": LIVRO_REAL, "matricula_id": int(m["id"]), "parte_id": 0, "classe": classe,
            "prioridade": prioridade, "confianca": _confianca_do_item(classe, proposta, campos),
            "fatia": _fatia(classe, ficha, m), "marcas": marcas, "campos": campos,
            "avisos": list((proposta or {}).get("avisos") or []),
            "bloco": _txt((proposta or {}).get("bloco")), "pronta": pronta}


def gerar(con: Any, *, agora: str, settings: Mapping[str, Any]) -> dict:
    """Monta ou atualiza a fila. **Só escreve em `ri_ff_itens`.**"""
    from gestor_cargas_ri import NUMERO_DE_FICHA_ARQUIVADA

    s = dict(settings)
    cns = cns_da_casa(s)
    if not cns:
        raise FilaError("O CNS da serventia não está configurado.")
    bd = banco(con)
    padrao = IR.padrao_do_arquivo(s)
    ligada = regra_ligada(s)

    partes_por_ficha: dict[int, list[dict]] = {}
    donos_do_doc: dict[str, set] = {}
    for p in bd.ler("SELECT * FROM ri_partes ORDER BY id"):
        p = dict(p)
        if _txt(p.get("nome")):
            partes_por_ficha.setdefault(int(p["matricula_id"]), []).append(p)
        d = CC.so_digitos(p.get("documento_numero"))
        if len(d) in (11, 14):
            donos_do_doc.setdefault(d, set()).add(_norm(p.get("nome")).strip())
    atos_por_ficha: dict[int, dict] = {}
    for a in bd.ler("SELECT id, matricula_id, tipo, numero FROM ri_atos"):
        atos_por_ficha.setdefault(int(a["matricula_id"]), {})[int(a["id"])] = (
            _txt(a["tipo"]).upper(), int(a["numero"] or 0))
    informados: dict[str, list[dict]] = {}
    for d in IR.donos_informados(con):
        informados.setdefault(_txt(d["numero"]), []).append(dict(d))

    feito = {"fichas": 0, "partes": 0, "novos": 0, "atualizados": 0, "preservados": 0}
    vistos: set[tuple[str, int, int]] = set()

    def conta(resultado: str) -> None:
        chave = {"novo": "novos", "atualizado": "atualizados", "decidido": "preservados"}.get(
            resultado)
        if chave:
            feito[chave] += 1

    for linha in bd.ler("SELECT * FROM ri_matriculas WHERE COALESCE(encerrada, 0) = 0 "
                        "ORDER BY id"):
        m = dict(linha)
        digitos = CC.so_digitos(m.get("numero"))
        if not digitos or int(digitos) >= NUMERO_DE_FICHA_ARQUIVADA:
            continue
        mid = int(m["id"])
        partes = partes_por_ficha.get(mid, [])
        item = _item_do_livro4(con, m, partes, atos_por_ficha.get(mid, {}),
                               informados.get(digitos, []), padrao, s, cns)
        conta(_guardar(bd, item, agora, ligada))
        vistos.add((LIVRO_REAL, mid, 0))
        feito["fichas"] += 1

        teor = _txt(m.get("teor"))
        sem_doc = [p for p in partes
                   if len(CC.so_digitos(p.get("documento_numero"))) not in (11, 14)]
        if not teor or not sem_doc:
            continue
        texto_norm, mapa = _norm_com_mapa(teor)
        for parte in sem_doc:
            sug = sugerir_documento(teor, parte.get("nome"), texto_norm=texto_norm, mapa=mapa)
            if not sug:
                continue
            confianca, alertas = avaliar_documento(sug, parte, partes, donos_do_doc)
            item5 = {"livro": LIVRO_PESSOAL, "matricula_id": mid, "parte_id": int(parte["id"]),
                     "classe": DOC_TEOR, "prioridade": P_DEMAIS, "confianca": confianca,
                     "fatia": DOC_TEOR, "marcas": ["DOC_SUSPEITO"] if alertas else [],
                     "campos": [{"campo": "documento_numero",
                                 "atual": _txt(parte.get("documento_numero")),
                                 "sugerido": sug["documento"], "origem": ORIGEM_TEOR,
                                 "trecho": sug["trecho"], "conflito": False}],
                     "avisos": alertas, "bloco": "", "pronta": False}
            conta(_guardar(bd, item5, agora, ligada))
            vistos.add((LIVRO_PESSOAL, mid, int(parte["id"])))
            feito["partes"] += 1

    for r in bd.ler("SELECT id, livro, matricula_id, parte_id FROM ri_ff_itens "
                    "WHERE situacao IN (%s, %s, %s, %s)",
                    (A_CONFERIR, PULADA, SINALIZADA, JA_PRONTA)):
        if (r["livro"], int(r["matricula_id"]), int(r["parte_id"])) not in vistos:
            bd.escrever("UPDATE ri_ff_itens SET situacao=%s, amostra_id=NULL WHERE id=%s",
                        (FORA, r["id"]))
    return feito


# ═══════════════════════════════════════════════════════════ ler


def _abrir(r: Mapping[str, Any]) -> dict:
    d = dict(r)
    d["campos"] = _de_json(d.get("campos"), [])
    d["marcas"] = _de_json(d.get("marcas"), [])
    d["avisos"] = _de_json(d.get("avisos"), [])
    return d


def ler(con: Any, item_id: int) -> dict | None:
    r = banco(con).um(
        "SELECT i.*, m.numero AS matricula_numero, m.livro AS livro_da_ficha, "
        "       p.nome AS parte_nome, p.papel AS parte_papel "
        "  FROM ri_ff_itens i JOIN ri_matriculas m ON m.id = i.matricula_id "
        "  LEFT JOIN ri_partes p ON p.id = i.parte_id WHERE i.id=%s", (int(item_id),))
    return _abrir(r) if r else None


def campos_visiveis(item: Mapping[str, Any], ligada: bool) -> list[dict]:
    """O que a tela pode mostrar. **O valor da regra desligada não sai daqui.**"""
    saida = []
    for c in item.get("campos") or []:
        c = dict(c)
        c["rotulo"] = ROTULO_DO_CAMPO.get(c["campo"], c["campo"])
        c["oculta_regra"] = c.get("origem") == ORIGEM_REGRA and not ligada
        if c["oculta_regra"]:
            c.update(sugerido="", trecho="", origem="", conflito=False)
        saida.append(c)
    return saida


def avisos_visiveis(item: Mapping[str, Any], ligada: bool) -> list[str]:
    """Os avisos em texto limpo. **Com a regra desligada, sem o valor dela.**"""
    saida = []
    for aviso in item.get("avisos") or []:
        texto = str(aviso).replace("**", "")
        if not ligada:
            if texto.startswith("O tipo do imóvel vai como"):
                continue
            texto = re.sub(r" Vai o padrão \([^)]*\), e confira:", " Confira:", texto)
            texto = texto.replace(" — o número vai como «0».", ".")
        saida.append(texto)
    return saida


def _filtros(livro: str, classe: str | None, situacao: str | None, confianca: str | None,
             prioridade: int | None, amostra_id: int | None) -> tuple[str, list]:
    onde, args = ["i.livro=%s"], [livro]
    for coluna, valor in (("i.classe", classe), ("i.situacao", situacao),
                          ("i.confianca", confianca), ("i.prioridade", prioridade),
                          ("i.amostra_id", amostra_id)):
        if valor not in (None, ""):
            onde.append(f"{coluna}=%s")
            args.append(valor)
    return " AND ".join(onde), args


ORDEM_DA_FILA = ("i.prioridade, CASE i.confianca WHEN 'alta' THEN 1 WHEN 'media' THEN 2 "
                 "ELSE 3 END, i.matricula_id, i.id")


def listar(con: Any, *, livro: str = LIVRO_REAL, classe: str | None = None,
           situacao: str | None = A_CONFERIR, confianca: str | None = None,
           prioridade: int | None = None, amostra_id: int | None = None,
           limite: int = 100, deslocamento: int = 0) -> dict:
    onde, args = _filtros(livro, classe, situacao, confianca, prioridade, amostra_id)
    bd = banco(con)
    total = int(bd.valor(f"SELECT COUNT(*) FROM ri_ff_itens i WHERE {onde}", args))
    linhas = bd.ler(
        "SELECT i.id, i.livro, i.classe, i.prioridade, i.confianca, i.fatia, i.situacao, "
        "       i.marcas, i.pronta, i.amostra_id, i.decidido_por, i.decidido_em, "
        "       m.numero AS matricula_numero, p.nome AS parte_nome "
        "  FROM ri_ff_itens i JOIN ri_matriculas m ON m.id = i.matricula_id "
        "  LEFT JOIN ri_partes p ON p.id = i.parte_id "
        f" WHERE {onde} ORDER BY {ORDEM_DA_FILA} LIMIT %s OFFSET %s",
        [*args, int(limite), int(deslocamento)])
    itens = []
    for r in linhas:
        d = dict(r)
        d["marcas"] = _de_json(d.get("marcas"), [])
        itens.append(d)
    return {"total": total, "itens": itens}


def proximo(con: Any, item: Mapping[str, Any]) -> int | None:
    """O próximo a conferir da mesma classe, para a pessoa não voltar à lista."""
    r = banco(con).um(
        "SELECT i.id FROM ri_ff_itens i WHERE i.livro=%s AND i.classe=%s AND i.situacao=%s "
        f"AND i.id <> %s ORDER BY {ORDEM_DA_FILA} LIMIT 1",
        (item["livro"], item["classe"], A_CONFERIR, int(item["id"])))
    return int(r["id"]) if r else None


def contar(con: Any) -> dict:
    """O progresso por classe. «Conferida» e «pronta» são contas diferentes."""
    bd = banco(con)
    classes: dict[tuple[str, str], dict] = {}
    for r in bd.ler("SELECT livro, classe, situacao, pronta, COUNT(*) AS n FROM ri_ff_itens "
                    "WHERE situacao <> %s GROUP BY livro, classe, situacao, pronta", (FORA,)):
        c = classes.setdefault((r["livro"], r["classe"]), {
            "livro": r["livro"], "classe": r["classe"],
            "nome": NOME_DA_CLASSE.get(r["classe"], r["classe"]), "total": 0, "a_conferir": 0,
            "puladas": 0, "aceitas": 0, "corrigidas": 0, "sinalizadas": 0, "prontas": 0})
        n = int(r["n"])
        c["total"] += n
        chave = {A_CONFERIR: "a_conferir", PULADA: "puladas", ACEITA: "aceitas",
                 CORRIGIDA: "corrigidas", SINALIZADA: "sinalizadas"}.get(r["situacao"])
        if chave:
            c[chave] += n
        if int(r["pronta"] or 0):
            c["prontas"] += n
    ordem = {PRONTA: 0, TEOR: 1, REGRA_CASA: 2, PESSOA: 3, DOC_TEOR: 4}
    linhas = sorted(classes.values(), key=lambda c: (c["livro"], ordem.get(c["classe"], 9)))
    for c in linhas:
        c["conferidas"] = c["aceitas"] + c["corrigidas"]
        base = c["total"] - c["sinalizadas"] if c["classe"] != PRONTA else 0
        c["percentual"] = round(100 * c["conferidas"] / base) if base else 0
    prioridades = {int(r["prioridade"]): int(r["n"]) for r in bd.ler(
        "SELECT prioridade, COUNT(*) AS n FROM ri_ff_itens WHERE livro=%s AND situacao IN "
        "(%s, %s, %s) GROUP BY prioridade", (LIVRO_REAL, A_CONFERIR, PULADA, SINALIZADA))}
    return {"classes": linhas, "prioridades": prioridades}


def alteracoes(con: Any, *, item_id: int | None = None, limite: int = 300) -> list[dict]:
    """O rastro, do mais novo para o mais antigo."""
    onde, args = "", []
    if item_id is not None:
        onde, args = "WHERE a.item_id=%s", [int(item_id)]
    return [dict(r) for r in banco(con).ler(
        "SELECT a.*, m.numero AS matricula_numero, "
        "       EXISTS (SELECT 1 FROM ri_ff_alteracoes d WHERE d.desfaz_id = a.id) AS desfeita "
        "  FROM ri_ff_alteracoes a JOIN ri_matriculas m ON m.id = a.matricula_id "
        f"{onde} ORDER BY a.id DESC LIMIT %s", [*args, int(limite)])]


# ═══════════════════════════════════════════════════════════ validar


def validar_campo(campo: str, valor: Any) -> str:
    """O valor limpo, ou a recusa. Vale para o que a pessoa digita."""
    v = _txt(valor)
    rotulo = ROTULO_DO_CAMPO.get(campo, campo)
    if campo not in E.CAMPOS:
        raise FilaError(f"O campo «{campo}» não se corrige por esta fila.")
    if not v:
        raise FilaError(f"«{rotulo}» não pode ficar em branco.")
    if len(v) > 150:
        raise FilaError(f"«{rotulo}»: use até 150 letras.")
    if campo == "cep":
        d = CC.so_digitos(v)
        if len(d) != 8:
            raise FilaError("O CEP tem 8 dígitos.")
        return d
    if campo == "uf":
        if not re.fullmatch(r"[A-Za-z]{2}", v):
            raise FilaError("A UF tem duas letras.")
        return v.upper()
    if campo == "rural_urbano":
        letra = v.upper()[:1]
        if API.sem_acento(v) not in ONR.LOCALIZACAO_POR_NOME:
            raise FilaError("Escolha urbano ou rural.")
        return letra
    if campo == "tipo_imovel" and API.sem_acento(v) not in API.CODIGO_DO_IMOVEL:
        raise FilaError("O tipo tem de ser um dos dez que o ONR aceita.")
    if campo == "logradouro" and ONR.partir_logradouro(v)["tipo_codigo"] is None:
        raise FilaError("O logradouro tem de começar por um tipo que o ONR conheça, "
                        "como «Rua» ou «Fazenda».")
    if campo == "area_unidade" and v not in ("m2", "ha"):
        raise FilaError("A unidade da área é m2 ou ha.")
    if campo == "area_valor" and not re.search(r"\d", v):
        raise FilaError("A área precisa de um número.")
    return v


def validar_documento(valor: Any) -> str:
    d = CC.so_digitos(valor)
    if len(d) not in (11, 14):
        raise FilaError(f"O documento tem {len(d)} dígitos. CPF tem 11 e CNPJ tem 14.")
    if CC.documento_valido(d) is not True:
        raise FilaError("Os dígitos verificadores deste CPF/CNPJ não conferem.")
    return d


# ═══════════════════════════════════════════════════════════ gravar


def _item_para_decidir(bd: Any, item_id: int) -> dict:
    r = bd.um("SELECT * FROM ri_ff_itens WHERE id=%s FOR UPDATE", (int(item_id),))
    if not r:
        raise FilaError("Este item da fila não existe.")
    item = _abrir(r)
    if item["situacao"] == SINALIZADA:
        raise FilaError("Esta ficha está só com o oficial: encerrar matrícula não é correção "
                        "de cadastro, e a fila não grava nada nela.")
    if item["situacao"] not in ABERTAS:
        raise FilaError("Este item já foi decidido ou saiu da fila. Para refazer, desfaça.")
    return item


def _registrar(bd: Any, item: Mapping[str, Any], campo: str, antes: Any, depois: Any,
               origem: str, motivo: str, usuario: str, agora: str,
               amostra_id: int | None = None, desfaz_id: int | None = None) -> None:
    bd.escrever(
        "INSERT INTO ri_ff_alteracoes (item_id, matricula_id, parte_id, campo, valor_anterior, "
        " valor_novo, origem, motivo, confirmado_por, confirmado_em, amostra_id, desfaz_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (int(item["id"]), int(item["matricula_id"]), int(item["parte_id"]), campo,
         None if antes is None else str(antes), None if depois is None else str(depois),
         origem, motivo, usuario, agora, amostra_id, desfaz_id))


def _pronta_agora(con: Any, item: Mapping[str, Any], cns: str) -> bool:
    if item["livro"] == LIVRO_PESSOAL:
        return True
    return bool(cns) and bool(ONR.montar_indicador(con, int(item["matricula_id"]), cns=cns)["pronto"])


def _gravar_na_ficha(con: Any, bd: Any, item: dict, novos: dict[str, tuple[str, str]],
                     motivo: str, usuario: str, agora: str, situacao: str, cns: str,
                     amostra_id: int | None = None) -> None:
    """Grava os campos, o rastro e a decisão, na mesma transação."""
    m = bd.um("SELECT * FROM ri_matriculas WHERE id=%s FOR UPDATE", (int(item["matricula_id"]),))
    if not m or int(m.get("encerrada") or 0):
        raise FilaError("Esta matrícula não está mais vigente.")
    fotografia = {c["campo"]: c["atual"] for c in item["campos"]}
    mudaram = [c for c in novos if _txt(m.get(c)) != fotografia.get(c, "")]
    if mudaram:
        nomes = ", ".join(ROTULO_DO_CAMPO.get(c, c) for c in mudaram)
        raise FilaError(f"A ficha mudou depois da leitura ({nomes}). Atualize a fila "
                        "antes de decidir, para não gravar por cima de quem editou.")
    sobrescreve = [c for c in novos if _txt(m.get(c))]
    if sobrescreve and len(_txt(motivo)) < MOTIVO_MINIMO:
        nomes = ", ".join(ROTULO_DO_CAMPO.get(c, c) for c in sobrescreve)
        raise FilaError(f"Trocar um valor que a ficha já tem ({nomes}) exige o motivo escrito, "
                        f"com pelo menos {MOTIVO_MINIMO} letras.")
    # Os nomes das colunas vêm de `E.CAMPOS`, nunca do formulário.
    colunas = [c for c in E.CAMPOS if c in novos]
    conjuntos = ", ".join(f"{c}=%s" for c in colunas)
    bd.escrever(f"UPDATE ri_matriculas SET {conjuntos}, atualizado_em=%s WHERE id=%s",
                [*(novos[c][0] for c in colunas), agora, int(item["matricula_id"])])
    for c in colunas:
        _registrar(bd, item, c, m.get(c), novos[c][0], novos[c][1], _txt(motivo), usuario,
                   agora, amostra_id)
    bd.escrever("UPDATE ri_ff_itens SET situacao=%s, decidido_em=%s, decidido_por=%s, pronta=%s "
                "WHERE id=%s", (situacao, agora, usuario,
                                int(_pronta_agora(con, item, cns)), int(item["id"])))


def _gravar_documento(con: Any, bd: Any, item: dict, documento: str, origem: str, motivo: str,
                      usuario: str, agora: str, situacao: str,
                      mesma_pessoa: bool = False) -> None:
    antes = bd.um("SELECT * FROM ri_partes WHERE id=%s FOR UPDATE", (int(item["parte_id"]),))
    if not antes:
        raise FilaError("Esta parte não existe mais.")
    # Confere na hora de gravar: o cônjuge pode ter recebido este número há um minuto.
    nome = _norm(antes.get("nome")).strip()
    de_outro = [r["nome"] for r in bd.ler(
        "SELECT nome FROM ri_partes WHERE documento_numero=%s AND id<>%s",
        (documento, int(item["parte_id"]))) if _outra_pessoa(nome, _norm(r["nome"]).strip())]
    if de_outro and not mesma_pessoa:
        raise FilaError(f"Este número já está gravado para {de_outro[0]}. Só grave se conferiu "
                        "que é a mesma pessoa, e marque a caixa que diz isso.")
    if de_outro:
        motivo = (_txt(motivo) + " · conferido: mesma pessoa de outro registro").strip(" ·")
    if len(CC.so_digitos(antes.get("documento_numero"))) in (11, 14):
        raise FilaError("Esta parte já tem documento gravado. Atualize a fila.")
    fotografia = next((c["atual"] for c in item["campos"]
                       if c["campo"] == "documento_numero"), "")
    if _txt(antes.get("documento_numero")) != fotografia:
        raise FilaError("O documento desta parte mudou depois da leitura. Atualize a fila.")
    # `titular` vai explícito para a correção do documento não mexer em quem é dono.
    COR.corrigir_parte(con, int(item["parte_id"]),
                       motivo=_txt(motivo) or "Documento conferido na fila do Livro 5",
                       agora=agora, documento=documento,
                       titular=bool(int(antes.get("proprietario_ativo") or 0)), usuario=usuario)
    depois = bd.um("SELECT * FROM ri_partes WHERE id=%s", (int(item["parte_id"]),))
    for campo in CAMPOS_DA_PARTE:
        _registrar(bd, item, campo, antes.get(campo), depois.get(campo), origem, _txt(motivo),
                   usuario, agora)
    bd.escrever("UPDATE ri_ff_itens SET situacao=%s, decidido_em=%s, decidido_por=%s, pronta=1 "
                "WHERE id=%s", (situacao, agora, usuario, int(item["id"])))


def _exigir_usuario(usuario: Any) -> str:
    quem = _txt(usuario)
    if not quem:
        raise FilaError("Nada se grava sem saber quem confirmou.")
    return quem


def aceitar(con: Any, item_id: int, *, campos: Iterable[str], agora: str, usuario: str,
            ligada: bool, cns: str, motivo: str = "", mesma_pessoa: bool = False) -> dict:
    """Grava as sugestões que a pessoa marcou. Regra desligada é recusada aqui."""
    quem = _exigir_usuario(usuario)
    bd = banco(con)
    item = _item_para_decidir(bd, item_id)
    marcados = {c for c in campos if c}
    if not marcados:
        raise FilaError("Marque ao menos um campo para aceitar.")
    disponiveis = {c["campo"]: c for c in item["campos"] if c.get("sugerido")}
    if item["livro"] == LIVRO_PESSOAL:
        linha = disponiveis.get("documento_numero")
        if not linha or "documento_numero" not in marcados:
            raise FilaError("Marque o documento para aceitar.")
        documento = validar_documento(linha["sugerido"])
        _gravar_documento(con, bd, item, documento, ORIGEM_TEOR, motivo, quem, agora, ACEITA,
                          mesma_pessoa=mesma_pessoa)
        return {"item": item, "gravados": ["documento_numero"]}
    if marcados & {"area_valor", "area_unidade"}:
        marcados |= {c for c in ("area_valor", "area_unidade") if c in disponiveis}
    novos: dict[str, tuple[str, str]] = {}
    for campo in marcados:
        linha = disponiveis.get(campo)
        if not linha:
            raise FilaError(f"O campo «{ROTULO_DO_CAMPO.get(campo, campo)}» não tem sugestão.")
        if linha["origem"] == ORIGEM_REGRA and not ligada:
            raise FilaError("A regra da casa está desligada: este valor não pode ser aceito. "
                            "Quem liga é o titular.")
        novos[campo] = (linha["sugerido"], linha["origem"])
    _gravar_na_ficha(con, bd, item, novos, motivo, quem, agora, ACEITA, cns)
    return {"item": item, "gravados": sorted(novos)}


def corrigir(con: Any, item_id: int, *, valores: Mapping[str, Any], agora: str, usuario: str,
             cns: str, motivo: str = "", mesma_pessoa: bool = False) -> dict:
    """Grava o que a pessoa digitou. A origem fica MANUAL."""
    quem = _exigir_usuario(usuario)
    bd = banco(con)
    item = _item_para_decidir(bd, item_id)
    preenchidos = {c: v for c, v in valores.items() if _txt(v)}
    if not preenchidos:
        raise FilaError("Escreva ao menos um valor para corrigir.")
    if item["livro"] == LIVRO_PESSOAL:
        documento = validar_documento(preenchidos.get("documento_numero"))
        _gravar_documento(con, bd, item, documento, ORIGEM_MANUAL, motivo, quem, agora, CORRIGIDA,
                          mesma_pessoa=mesma_pessoa)
        return {"item": item, "gravados": ["documento_numero"]}
    novos = {c: (validar_campo(c, v), ORIGEM_MANUAL) for c, v in preenchidos.items()}
    if {"area_valor", "area_unidade"} & set(novos):
        if not {"area_valor", "area_unidade"} <= set(novos):
            raise FilaError("Escreva a área e a unidade juntas: o número sozinho muda de "
                            "tamanho conforme a unidade.")
        if API.area_em_metros(novos["area_valor"][0], novos["area_unidade"][0]) is None:
            raise FilaError("Esta área não dá para ler com segurança. Use a vírgula: "
                            "«38,08» ou «3.808,00».")
    _gravar_na_ficha(con, bd, item, novos, motivo, quem, agora, CORRIGIDA, cns)
    return {"item": item, "gravados": sorted(novos)}


def pular(con: Any, item_id: int, *, agora: str, usuario: str) -> dict:
    """Deixa para depois. Não grava na ficha."""
    quem = _exigir_usuario(usuario)
    bd = banco(con)
    item = _item_para_decidir(bd, item_id)
    bd.escrever("UPDATE ri_ff_itens SET situacao=%s, decidido_em=%s, decidido_por=%s WHERE id=%s",
                (PULADA, agora, quem, int(item["id"])))
    return {"item": item}


def _valor_da_coluna(campo: str, valor: Any) -> Any:
    if valor is None:
        return None
    return int(valor) if campo == "documento_valido" else valor


def _desfazer_item(con: Any, bd: Any, item: Mapping[str, Any], motivo: str, usuario: str,
                   agora: str, cns: str, amostra_id: int | None = None) -> list[str]:
    linhas = [dict(r) for r in bd.ler(
        "SELECT a.* FROM ri_ff_alteracoes a WHERE a.item_id=%s AND a.origem <> %s "
        "AND NOT EXISTS (SELECT 1 FROM ri_ff_alteracoes d WHERE d.desfaz_id = a.id) "
        "ORDER BY a.id DESC", (int(item["id"]), ORIGEM_DESFAZER))]
    if not linhas:
        raise FilaError("Não há alteração a desfazer neste item.")
    # Só a ÚLTIMA decisão: a ficha reaberta pode ter uma conferência anterior que continua valendo.
    ultima = linhas[0]
    linhas = [a for a in linhas if (a["confirmado_em"], a["confirmado_por"], a["amostra_id"])
              == (ultima["confirmado_em"], ultima["confirmado_por"], ultima["amostra_id"])]
    if amostra_id is not None and ultima["amostra_id"] != amostra_id:
        raise FilaError("Esta ficha teve outra decisão depois do lote.")
    if item["livro"] == LIVRO_PESSOAL:
        tabela, chave, permitidos = "ri_partes", int(item["parte_id"]), CAMPOS_DA_PARTE
    else:
        tabela, chave, permitidos = "ri_matriculas", int(item["matricula_id"]), E.CAMPOS
    atual = bd.um(f"SELECT * FROM {tabela} WHERE id=%s FOR UPDATE", (chave,))
    if not atual:
        raise FilaError("O registro desta alteração não existe mais.")
    mexidos = [a["campo"] for a in linhas if _txt(atual.get(a["campo"])) != _txt(a["valor_novo"])]
    if mexidos:
        nomes = ", ".join(ROTULO_DO_CAMPO.get(c, c) for c in mexidos)
        raise FilaError(f"Alguém mudou {nomes} depois desta confirmação. Desfazer apagaria o "
                        "trabalho dessa pessoa: corrija na própria ficha.")
    for a in linhas:
        campo = a["campo"]
        if campo not in permitidos:
            raise FilaError(f"O campo «{campo}» não se desfaz por esta fila.")
        bd.escrever(f"UPDATE {tabela} SET {campo}=%s WHERE id=%s",
                    (_valor_da_coluna(campo, a["valor_anterior"]), chave))
        _registrar(bd, item, campo, a["valor_novo"], a["valor_anterior"], ORIGEM_DESFAZER,
                   motivo, usuario, agora, desfaz_id=int(a["id"]))
    bd.escrever("UPDATE ri_matriculas SET atualizado_em=%s WHERE id=%s",
                (agora, int(item["matricula_id"])))
    pronta = False if item["livro"] == LIVRO_PESSOAL else _pronta_agora(con, item, cns)
    bd.escrever("UPDATE ri_ff_itens SET situacao=%s, decidido_em=NULL, decidido_por=NULL, "
                "pronta=%s WHERE id=%s", (A_CONFERIR, int(pronta), int(item["id"])))
    return [a["campo"] for a in linhas]


def desfazer(con: Any, item_id: int, *, motivo: str, agora: str, usuario: str, cns: str) -> dict:
    """Volta os campos ao valor anterior e devolve o item à fila."""
    quem = _exigir_usuario(usuario)
    if len(_txt(motivo)) < MOTIVO_MINIMO:
        raise FilaError(f"Desfazer exige o motivo escrito, com pelo menos {MOTIVO_MINIMO} letras.")
    bd = banco(con)
    r = bd.um("SELECT * FROM ri_ff_itens WHERE id=%s FOR UPDATE", (int(item_id),))
    if not r:
        raise FilaError("Este item da fila não existe.")
    item = _abrir(r)
    if item["situacao"] not in DECIDIDAS:
        raise FilaError("Só se desfaz o que foi aceito ou corrigido.")
    return {"item": item, "campos": _desfazer_item(con, bd, item, _txt(motivo), quem, agora, cns)}


# ═══════════════════════════════════════════════════════════ amostra e lote


def _pode_lote(fatia: str) -> bool:
    return fatia.split("|")[0] in (TEOR, REGRA_CASA)


def _elegiveis_sql() -> str:
    return ("livro=%s AND fatia=%s AND situacao=%s AND confianca='alta' "
            "AND amostra_id IS NULL")


def estado_da_amostra(con: Any, amostra_id: int) -> dict | None:
    """ABERTA, LIMPA (libera o lote), REPROVADA ou USADA."""
    bd = banco(con)
    a = bd.um("SELECT * FROM ri_ff_amostras WHERE id=%s", (int(amostra_id),))
    if not a:
        return None
    d = dict(a)
    n = {r["situacao"]: int(r["n"]) for r in bd.ler(
        "SELECT situacao, COUNT(*) AS n FROM ri_ff_itens WHERE amostra_id=%s GROUP BY situacao",
        (int(amostra_id),))}
    d["aceitas"] = n.get(ACEITA, 0)
    d["corrigidas"] = n.get(CORRIGIDA, 0)
    d["pendentes"] = sum(v for k, v in n.items() if k not in DECIDIDAS)
    if d.get("lote_em"):
        d["estado"] = "USADA"
    elif d["corrigidas"]:
        d["estado"] = "REPROVADA"
    elif d["pendentes"] or not d["aceitas"]:
        d["estado"] = "ABERTA"
    else:
        d["estado"] = "LIMPA"
    d["nome_da_fatia"] = nome_da_fatia(d["fatia"])
    return d


def fatias_de_lote(con: Any, ligada: bool) -> list[dict]:
    """As fatias que podem ir em lote, com a amostra mais recente de cada uma."""
    bd = banco(con)
    saida = []
    for r in bd.ler("SELECT fatia, COUNT(*) AS n FROM ri_ff_itens WHERE livro=%s AND situacao=%s "
                    "AND confianca='alta' AND amostra_id IS NULL GROUP BY fatia ORDER BY fatia",
                    (LIVRO_REAL, A_CONFERIR)):
        if not _pode_lote(r["fatia"]):
            continue
        if r["fatia"].startswith(REGRA_CASA) and not ligada:
            continue
        ultima = bd.um("SELECT id FROM ri_ff_amostras WHERE fatia=%s ORDER BY id DESC LIMIT 1",
                       (r["fatia"],))
        amostra = estado_da_amostra(con, int(ultima["id"])) if ultima else None
        saida.append({"fatia": r["fatia"], "nome": nome_da_fatia(r["fatia"]),
                      "elegiveis": int(r["n"]), "amostra": amostra})
    return saida


def sortear_amostra(con: Any, fatia: str, *, agora: str, usuario: str, ligada: bool,
                    tamanho: int = TAMANHO_DA_AMOSTRA) -> dict:
    """Sorteia a amostra. Cada item dela será conferido um a um."""
    quem = _exigir_usuario(usuario)
    if not _pode_lote(fatia):
        raise FilaError("Esta fatia não vai em lote: confere-se uma a uma.")
    if fatia.startswith(REGRA_CASA) and not ligada:
        raise FilaError("A regra da casa está desligada.")
    bd = banco(con)
    bd.travar(f"ri_ff_amostra.{fatia}")
    ultima = bd.um("SELECT id FROM ri_ff_amostras WHERE fatia=%s ORDER BY id DESC LIMIT 1",
                   (fatia,))
    if ultima:
        anterior = estado_da_amostra(con, int(ultima["id"]))
        if anterior and anterior["estado"] in ("ABERTA", "LIMPA"):
            raise FilaError("Esta fatia já tem amostra em andamento ou liberada.")
    ids = [int(r["id"]) for r in bd.ler(
        f"SELECT id FROM ri_ff_itens WHERE {_elegiveis_sql()} ORDER BY random() LIMIT %s",
        (LIVRO_REAL, fatia, A_CONFERIR, int(tamanho)))]
    if not ids:
        raise FilaError("Não há ficha de confiança alta para sortear nesta fatia.")
    linha = bd.escrever(
        "INSERT INTO ri_ff_amostras (fatia, regra_casa, tamanho, criada_por, criada_em) "
        "VALUES (%s,%s,%s,%s,%s) RETURNING id", (fatia, int(ligada), len(ids), quem, agora))
    amostra_id = int(linha[0]["id"])
    bd.escrever("UPDATE ri_ff_itens SET amostra_id=%s WHERE id = ANY(%s)", (amostra_id, ids))
    return {"amostra_id": amostra_id, "tamanho": len(ids)}


def aceitar_lote(con: Any, amostra_id: int, *, quantidade: Any, agora: str, usuario: str,
                 ligada: bool, cns: str) -> dict:
    """Aceita a fatia depois da amostra limpa. **Só preenche campo vazio.**

    `quantidade` é o número que a pessoa digitou: tem de bater com os elegíveis.
    """
    quem = _exigir_usuario(usuario)
    bd = banco(con)
    trava = bd.um("SELECT fatia FROM ri_ff_amostras WHERE id=%s", (int(amostra_id),))
    if not trava:
        raise FilaError("Esta amostra não existe.")
    bd.travar(f"ri_ff_amostra.{trava['fatia']}")
    a = estado_da_amostra(con, amostra_id)
    if not a:
        raise FilaError("Esta amostra não existe.")
    if a["estado"] != "LIMPA":
        raise FilaError("O lote só abre com a amostra inteira conferida e sem nenhuma correção.")
    if not _pode_lote(a["fatia"]):
        raise FilaError("Esta fatia não vai em lote.")
    if bool(a["regra_casa"]) != bool(ligada):
        raise FilaError("A regra da casa mudou depois desta amostra. Sorteie outra.")
    linhas = bd.ler(f"SELECT * FROM ri_ff_itens WHERE {_elegiveis_sql()} "
                    "AND calculado_em <= %s ORDER BY id FOR UPDATE",
                    (LIVRO_REAL, a["fatia"], A_CONFERIR, a["criada_em"]))
    try:
        digitado = int(CC.so_digitos(quantidade) or -1)
    except ValueError:
        digitado = -1
    if digitado != len(linhas):
        raise FilaError(f"Para confirmar, digite o número exato de fichas do lote: {len(linhas)}.")
    gravados = sem_campo = mudaram = 0
    for r in linhas:
        item = _abrir(r)
        novos = {c["campo"]: (c["sugerido"], c["origem"]) for c in item["campos"]
                 if not c["atual"] and c["sugerido"] and not c["conflito"]
                 and (c["origem"] == ORIGEM_TEOR or (ligada and c["origem"] == ORIGEM_REGRA))}
        if len({"area_valor", "area_unidade"} & set(novos)) == 1:
            novos.pop("area_valor", None)
            novos.pop("area_unidade", None)
        if not novos:
            sem_campo += 1
            continue
        try:
            with bd.ponto_de_retorno("ri_ff_lote"):
                _gravar_na_ficha(con, bd, item, novos, "", quem, agora, ACEITA, cns,
                                 amostra_id=int(amostra_id))
        except FilaError:
            mudaram += 1  # a ficha foi editada: fica na fila para alguém olhar
            continue
        gravados += 1
    bd.escrever("UPDATE ri_ff_amostras SET lote_por=%s, lote_em=%s, lote_qtd=%s WHERE id=%s",
                (quem, agora, gravados, int(amostra_id)))
    return {"gravados": gravados, "sem_campo": sem_campo, "mudaram": mudaram}


def desfazer_lote(con: Any, amostra_id: int, *, motivo: str, agora: str, usuario: str,
                  cns: str) -> dict:
    """Desfaz o lote inteiro. A ficha editada depois fica como está, e é contada."""
    quem = _exigir_usuario(usuario)
    if len(_txt(motivo)) < MOTIVO_MINIMO:
        raise FilaError(f"Desfazer exige o motivo escrito, com pelo menos {MOTIVO_MINIMO} letras.")
    bd = banco(con)
    ids = [int(r["item_id"]) for r in bd.ler(
        "SELECT DISTINCT a.item_id FROM ri_ff_alteracoes a WHERE a.amostra_id=%s AND a.origem<>%s "
        "AND NOT EXISTS (SELECT 1 FROM ri_ff_alteracoes d WHERE d.desfaz_id=a.id) ORDER BY 1",
        (int(amostra_id), ORIGEM_DESFAZER))]
    if not ids:
        raise FilaError("Este lote não tem alteração a desfazer.")
    desfeitos = ficaram = 0
    for item_id in ids:
        r = bd.um("SELECT * FROM ri_ff_itens WHERE id=%s FOR UPDATE", (item_id,))
        try:
            with bd.ponto_de_retorno("ri_ff_desfaz_lote"):
                _desfazer_item(con, bd, _abrir(r), _txt(motivo), quem, agora, cns,
                               amostra_id=int(amostra_id))
            desfeitos += 1
        except FilaError:
            ficaram += 1
    return {"desfeitos": desfeitos, "ficaram": ficaram}
