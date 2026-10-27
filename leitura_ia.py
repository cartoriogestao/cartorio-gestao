"""O MOTOR DA LEITURA DE DOCUMENTOS POR IA — comum ao Registro Civil e às Notas.

«autorizo ia sem mascara. trabalharemos com o prazo de retencao de 30 dias da
 api» — o oficial, 26/10/2026, ao pedir a leitura de RG/CIN/CNH e de documento
de veículo (CRLV, CRV, ATPV) no balcão das Notas, «como o Registro Civil já
faz com DNV e DO».

DE ONDE ISTO SAIU, E POR QUÊ (26/10/2026)
    Até aqui o motor morava dentro de `rc_leitura_documentos`: a triagem pelo
    modelo barato, a leitura de cada página pelo modelo certo, o teto de
    páginas, o custo, a recusa do simulador do SANDBOX e os validadores (data,
    CPF, nome parecido). As Notas precisavam do MESMO motor, e copiar daria
    duas versões da parte que decide o que sobe à Anthropic — e elas
    divergiriam no primeiro conserto. Ele veio para cá INTEIRO, linha por linha,
    e o Registro Civil passou a importá-lo com os mesmos nomes de antes:
    `rc_leitura_documentos.ler`, `.triar`, `.custo`, `.LeituraError`... — os
    testes do RCPN continuam chamando os nomes antigos, e é isso que prova que
    o comportamento não mudou.

    O QUE NÃO VEIO, de propósito: os moldes de cada tipo de documento e as
    instruções de triagem e de leitura. Eles dizem «cartório de registro
    civil» ou «tabelionato de notas», e são de cada atribuição. O motor recebe
    os moldes e as instruções de quem o chama.

O QUE SAI DA CASA, E QUANTO TEMPO FICA LÁ — `RETENCAO_DIAS` e
`ZERO_DATA_RETENTION`
    - a página inteira, sem máscara: decisão do oficial em 12/10/2026 para o
      Registro Civil e em 26/10/2026 para as Notas;
    - a Anthropic apaga entradas e saídas da API em até 30 dias (retenção
      padrão da API, conferida no Privacy Center em 12/10/2026), salvo
      conteúdo marcado por violação da política de uso (até 2 anos) ou
      obrigação legal; os documentos não treinam modelos (termos comerciais);
    - cada envio fica registrado por quem chama: que arquivo, que página, a
      que modelo, quanto custou.

ESTE MÓDULO NÃO LAVRA, NÃO NUMERA, NÃO SELA E NÃO COBRA. Ele lê e devolve o
que leu; quem decide o que fazer com isso é a tela, e quem confere é gente.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

import tetos_de_entrada as TETO
from bd_nativo import banco

PROVEDOR = "claude"

#: O TETO DE PÁGINAS POR LEITURA (M4 do LS02 = M12 do LS03; LX13, 19/10/2026).
#: Sem ele, um PDF de mil folhas eram ~125 triagens e mil leituras pagas, pedidas
#: por qualquer login. Quarenta é a régua que o oficial deu aos anexos da revisão
#: («aviso quando passar de 40 páginas», 07/10/2026), e sobra: o registro mais
#: cheio desta tela, a habilitação, junta requerimento, certidões e identidades
#: dos nubentes e das testemunhas em menos de vinte. Aqui não se corta: «tudo que
#: é preenchido precisa ser lido» (12/10/2026), e por isso, acima do teto, a
#: leitura inteira é RECUSADA antes de qualquer página subir.
MAXIMO_DE_PAGINAS = 40

#: OS TRÊS MODELOS, E O QUE CADA UM FAZ. São o PISO; a configuração ajusta
#: sem versão nova (`settings`), porque nome de modelo envelhece.
#:
#: AS CHAVES CONTINUAM `rcpn_leitura_modelo_*` (26/10/2026): elas já estão
#: gravadas na produção, e renomeá-las apagaria o ajuste sem avisar. As Notas
#: leem as MESMAS — um lugar só para trocar o modelo das duas leituras.
MODELOS_PADRAO: dict[str, str] = {
    "triagem": "claude-haiku-4-5-20251001",
    "manuscrito": "claude-opus-5-5",
    "impresso": "claude-sonnet-5",
}
CHAVE_DO_MODELO: dict[str, str] = {
    "triagem": "rcpn_leitura_modelo_triagem",
    "manuscrito": "rcpn_leitura_modelo_manuscrito",
    "impresso": "rcpn_leitura_modelo_impresso",
}

#: Preço em dólares por MILHÃO de tokens (entrada, saída) — tabela da Anthropic
#: conferida em 11/10/2026. Serve para a tela dizer quanto custou; quem cobra é
#: a Anthropic, e o número aqui é estimativa.
PRECO_POR_MILHAO: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}

#: A RETENÇÃO PELA ANTHROPIC, EM DIAS — a padrão da API. O oficial, 26/10/2026:
#: «trabalharemos com o prazo de retencao de 30 dias da api». Fica gravada em
#: cada leitura das Notas (`nt_leituras.retencao_dias`), para a pergunta «quanto
#: tempo isto ficou lá fora?» ter resposta na própria linha.
RETENCAO_DIAS = 30

#: O PEDIDO DE «ZERO DATA RETENTION» À ANTHROPIC — ordem do oficial em 12/10/2026:
#: «quero o pedido de zero data retention, registrado no código». É o acordo pelo
#: qual a Anthropic não guarda o que recebe pela API depois de responder. Ele se
#: pede à Anthropic (não é botão da API) e quem o pede e assina é o oficial; o
#: texto do pedido está em DOCUMENTACAO/LGPD_LEITURA_DE_DOCUMENTOS.md. A
#: SITUAÇÃO aqui é o que a tela mostra — e muda quando a resposta chegar, com a
#: data e o número do acordo. Enquanto não houver acordo, a tela diz isso: dizer
#: «sem retenção» antes da hora seria o carimbo que mente.
#:
#: NEGADO EM 12/10/2026 — a Anthropic respondeu ao oficial que a casa não tem
#: volume suficiente para o acordo. Vale a RETENÇÃO PADRÃO DA API, conferida no
#: Privacy Center no mesmo dia: entradas e saídas apagadas em até 30 dias, com
#: as exceções que a própria Anthropic declara (escritas abaixo, e não omitidas:
#: dizer «só 30 dias» sem elas seria afirmar mais do que a regra diz).
#:
#: (Veio de `rc_leitura_documentos` em 26/10/2026, sem mudar uma palavra; o
#: Registro Civil o reexporta com o mesmo nome.)
ZERO_DATA_RETENTION: dict[str, str] = {
    "situacao": "NEGADO",           # A PEDIR | PEDIDO | ACORDADO | NEGADO
    "pedido_em": "12/10/2026",
    "acordo": "",
    "retencao_padrao_dias": str(RETENCAO_DIAS),
    "fonte": "https://privacy.claude.com/en/articles/7996866",
    "observacao": ("Vale a retenção padrão da API: as imagens e as "
                   "respostas são apagadas dos servidores da Anthropic em até 30 "
                   "dias — salvo se o conteúdo for marcado por violação da política "
                   "de uso (até 2 anos) ou se a lei obrigar a guardar. Nada fica "
                   "guardado indefinidamente, e os documentos não são usados para "
                   "treinar modelos (termos comerciais da API)."),
}

#: O MOLDE DO DOCUMENTO DE IDENTIDADE — o mesmo para as duas atribuições. Veio
#: de `rc_leitura_documentos.TIPOS["IDENTIDADE"]` em 26/10/2026, sem mudar uma
#: palavra: o RG que o Registro Civil lê para a filiação é o RG que as Notas
#: leem para o cartão de autógrafo, e duas instruções para o mesmo papel dariam
#: dois CPFs diferentes da mesma pessoa.
TIPO_IDENTIDADE: dict[str, Any] = {
    "nome": "Documento de identidade (RG, CIN, CNH, CPF)",
    # LIDA PELO MODELO FORTE — ordem do oficial em 12/10/2026, depois do
    # ensaio do termo 19581: o Sonnet leu «Gilton Fedro» onde o RG diz
    # «Gilton Pedro». «É bem importante»: dela saem CPF, filiação e avós.
    "manuscrito": True,
    "campos": (
        "pessoas: uma lista com UM item por documento na página (a página pode "
        "trazer dois documentos), cada um com tipo_documento (RG/CIN/CNH/CPF), "
        "nome, numero_documento, orgao_emissor, cpf, data_nascimento, "
        "naturalidade (município e UF), filiacao_pai, filiacao_mae, "
        "data_expedicao, documento_origem, titulo_eleitor, numero_cnh, "
        "nacionalidade, sexo"),
}

#: «TUDO QUE É PREENCHIDO PRECISA SER LIDO» — o oficial, 12/10/2026. A página
#: que a triagem não reconhece também é transcrita, pelo modelo médio, campo a
#: campo; ela aparece na conferência para quem atende decidir se importa.
TIPO_OUTRO: dict[str, Any] = {
    "nome": "Outro documento",
    "manuscrito": False,
    "campos": ("tipo_do_documento (o que o documento é, em poucas palavras), "
               "e cada campo preenchido, com o rótulo do documento como chave"),
}


class LeituraError(ValueError):
    """Erro de regra, em português de balcão."""


# ------------------------------------------------------------ configuração

def _ler_config(con, chave: str) -> str:
    try:
        valor = banco(con).valor("SELECT value FROM settings WHERE key = %s", (chave,))
    except sqlite3.OperationalError:
        return ""
    return str(valor).strip() if valor else ""


def modelos(con) -> dict[str, str]:
    """Os três modelos em uso: o da configuração, ou o piso. SÓ LÊ."""
    return {papel: _ler_config(con, CHAVE_DO_MODELO[papel]) or padrao
            for papel, padrao in MODELOS_PADRAO.items()}


def custo(modelo: str, entrada: int, saida: int) -> float:
    """Dólares estimados de uma chamada. Modelo fora da tabela custa zero NA
    TELA, e a tela diz que não sabe — nunca um número inventado."""
    preco = PRECO_POR_MILHAO.get(modelo)
    if not preco:
        return 0.0
    return (int(entrada or 0) * preco[0] + int(saida or 0) * preco[1]) / 1_000_000


def custo_dos_envios(envios: list[dict]) -> float:
    """A soma estimada de uma leitura inteira, em dólares. SÓ CALCULA."""
    return round(sum(custo(e.get("modelo", ""), e.get("entrada") or 0, e.get("saida") or 0)
                     for e in envios or []), 4)


# ------------------------------------------------------------- as páginas

#: O que a frase do teto manda anexar, quando quem chama não diz — a do RCPN,
#: que é de onde a frase veio.
O_QUE_ANEXAR_PADRAO = "a DNV, a DO, os documentos de identidade"


def paginas_dos_arquivos(arquivos: list[dict], *,
                         o_que_anexar: str = O_QUE_ANEXAR_PADRAO) -> list[dict]:
    """[{arquivo, nome, n, imagem()}] na ordem em que foram anexados. SÓ LÊ.

    A página do PDF que já tem texto digital também vai como IMAGEM: a DNV e a
    DO são formulários de caixinhas, e o texto extraído perde o que está
    marcado.

    O NÚMERO DE PÁGINAS TEM TETO, E A RECUSA VEM ANTES DE QUALQUER CHAMADA
    (LX12, LS02 M4, 19/10/2026). Cada página é uma chamada PAGA ao provedor —
    duas, contando a triagem —, e a rota é de qualquer login: um PDF de mil
    páginas eram mil chamadas pagas, sem ninguém ver o custo antes. O teto é
    `tetos_de_entrada.valor("ia_paginas")` (50, ajustável); a frase diz por
    quê, para quem a recebe separar só os documentos do ato."""
    import revisao_anexos as RA
    saida = []
    for a in arquivos:
        try:
            paginas = RA.paginas_do_arquivo(Path(a["caminho"]), a["nome"])
        except RA.AnexoIlegivel as erro:
            raise LeituraError(f"«{a['nome']}»: {erro}.") from erro
        for n, p in enumerate(paginas, start=1):
            if p.get("imagem") is None:
                continue
            saida.append({"arquivo": a["nome"], "attachment_id": a.get("attachment_id"),
                          "n": n, "imagem": p["imagem"]})
    if not saida:
        raise LeituraError("Nenhuma página com imagem nos arquivos anexados — "
                           "anexe o PDF digitalizado ou as fotos dos documentos.")
    teto = TETO.valor("ia_paginas")
    if len(saida) > teto:
        raise LeituraError(
            f"Os anexos somam {len(saida)} páginas, e a leitura vai até {teto} "
            f"por vez: cada página é uma chamada paga à IA (mais a triagem), e "
            f"nada foi enviado. Anexe só os documentos deste ato — "
            f"{o_que_anexar} — e não o processo inteiro.")
    return saida


def _json(texto: str) -> dict:
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


#: O simulado de IA do SANDBOX responde com esta marca e não lê nada. Sem a
#: recusa, a triagem voltava vazia e a tela dizia «não há uma DNV» — a culpa
#: caía no documento, que estava certo (12/10/2026, primeira leitura no SANDBOX).
MARCA_DO_SIMULADOR = "[SIMULADOR DO SANDBOX]"


def _pedir(conversar, pasta: Path, modelo: str, instrucao: str, texto: str,
           imagens: list[str], maximo: int = 4000) -> dict:
    r = conversar(pasta, provedor=PROVEDOR, sistema=instrucao,
                  conversa=[{"tipo": "user", "texto": texto,
                             "imagens": [{"mime": "image/jpeg", "base64": b}
                                         for b in imagens]}],
                  ferramentas=[], modelo=modelo, maximo_de_saida=maximo)
    if MARCA_DO_SIMULADOR in str((r or {}).get("texto") or ""):
        raise LeituraError(
            "Este é o sistema de teste: a IA daqui é um simulador e não lê "
            "documentos. O caminho até ela funcionou; a leitura de verdade "
            "acontece na produção, depois da atualização.")
    return r


#: A TRIAGEM VÊ MINIATURAS, EM LOTES — e isso foi medido no primeiro óbito
#: real (12/10/2026): o PDF com a DO, os documentos e a certidão passou de 2 MB
#: numa chamada só, e o transporte recusa conversa desse tamanho. Para dizer «é
#: uma DNV» basta a página pequena; quem precisa da página inteira é a leitura.
LADO_DA_MINIATURA_PX = 700
PAGINAS_POR_LOTE_DA_TRIAGEM = 8


def _miniatura(imagem_b64: str) -> str:
    import base64
    import io
    from PIL import Image
    with Image.open(io.BytesIO(base64.b64decode(imagem_b64))) as im:
        im = im.convert("L")
        fator = LADO_DA_MINIATURA_PX / max(im.size)
        if fator < 1:
            im = im.resize((int(im.size[0] * fator), int(im.size[1] * fator)))
        saida = io.BytesIO()
        im.save(saida, format="JPEG", quality=60)
    return base64.b64encode(saida.getvalue()).decode("ascii")


def triar(conversar, pasta: Path, modelo: str, paginas: list[dict], *,
          instrucao: str, tipos: dict[str, dict]) -> tuple[list[str], list[dict]]:
    """O tipo de cada página, pelo modelo barato, em lotes. FALA COM A REDE.

    O que o modelo não souber dizer vira OUTRO — e OUTRO também é lido."""
    escolhidos: list[str] = []
    envios: list[dict] = []
    for inicio in range(0, len(paginas), PAGINAS_POR_LOTE_DA_TRIAGEM):
        lote = paginas[inicio:inicio + PAGINAS_POR_LOTE_DA_TRIAGEM]
        imagens = [_miniatura(p["imagem"]()) for p in lote]
        texto = "\n".join(f"Página {i}: arquivo {p['arquivo']}, folha {p['n']}"
                          for i, p in enumerate(lote, start=1))
        r = _pedir(conversar, pasta, modelo, instrucao, texto, imagens, 1500)
        por_n = {}
        for item in _json(r.get("texto") or "").get("paginas") or []:
            try:
                por_n[int(item.get("n"))] = str(item.get("tipo") or "").upper()
            except (TypeError, ValueError):
                continue
        escolhidos += [por_n.get(i) if por_n.get(i) in tipos else "OUTRO"
                       for i in range(1, len(lote) + 1)]
        envios.append({"etapa": "triagem", "modelo": r.get("modelo") or modelo,
                       "paginas": [f"{p['arquivo']} p{p['n']}" for p in lote],
                       "entrada": r.get("entrada"), "saida": r.get("saida")})
    return escolhidos, envios


def ler_pagina(conversar, pasta: Path, modelos_em_uso: dict, pagina: dict,
               tipo: str, *, tipos: dict[str, dict], instrucao: str) -> tuple[dict, dict]:
    """O que UMA página diz, pelo molde do tipo dela. FALA COM A REDE.

    `instrucao` tem os marcadores `{nome}` e `{campos}`, preenchidos pelo
    molde do tipo."""
    molde = tipos[tipo]
    modelo = modelos_em_uso["manuscrito" if molde["manuscrito"] else "impresso"]
    texto_da_instrucao = instrucao.format(nome=molde["nome"], campos=molde["campos"])
    r = _pedir(conversar, pasta, modelo, texto_da_instrucao,
               f"Transcreva: {pagina['arquivo']}, folha {pagina['n']}.",
               [pagina["imagem"]()], 4000)
    dados = _json(r.get("texto") or "")
    envio = {"etapa": "leitura", "tipo": tipo, "modelo": r.get("modelo") or modelo,
             "paginas": [f"{pagina['arquivo']} p{pagina['n']}"],
             "entrada": r.get("entrada"), "saida": r.get("saida")}
    return dados, envio


def ler_paginas(conversar, pasta: Path, modelos_em_uso: dict, paginas: list[dict], *,
                tipos: dict[str, dict], instrucao_triagem: str,
                instrucao_leitura: str) -> dict:
    """Triar e ler as páginas JÁ abertas e JÁ conferidas contra o teto.
    FALA COM A REDE — e por isso NÃO RECEBE `con`: um minuto de rede segurando o
    banco poria a casa no `busy_timeout`.

    Devolve {paginas, tipos, documentos, envios}; `tipos` vem à parte para quem
    chama poder corrigi-los (a rede de segurança da DNV, no RCPN)."""
    escolhidos, envios = triar(conversar, pasta, modelos_em_uso["triagem"], paginas,
                               instrucao=instrucao_triagem, tipos=tipos)
    a_ler = list(zip(paginas, escolhidos))

    def uma(par):
        pagina, tipo = par
        return ler_pagina(conversar, pasta, modelos_em_uso, pagina, tipo,
                          tipos=tipos, instrucao=instrucao_leitura)

    with ThreadPoolExecutor(max_workers=4) as ex:
        resultados = list(ex.map(uma, a_ler))
    documentos = []
    for (pagina, tipo), (dados, envio) in zip(a_ler, resultados):
        documentos.append({"arquivo": pagina["arquivo"], "n": pagina["n"],
                           "attachment_id": pagina.get("attachment_id"),
                           "tipo": tipo, "dados": dados})
        envios.append(envio)
    return {"paginas": paginas, "tipos": escolhidos, "documentos": documentos,
            "envios": envios}


def paginas_para_gravar(paginas: list[dict], tipos: list[str]) -> list[dict]:
    """O que se grava de cada página: arquivo, folha, anexo e tipo — a imagem
    não (ela é o próprio anexo). SÓ CALCULA."""
    return [{"arquivo": p["arquivo"], "n": p["n"],
             "attachment_id": p.get("attachment_id"), "tipo": t}
            for p, t in zip(paginas, tipos)]


# ----------------------------------------------- os validadores (sem rede)

DUVIDA = " (?)"


def _valor(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(_valor(x) for x in v if _valor(x))
    texto = str(v).strip()
    return "" if texto.lower() in ("null", "none", "-") else texto


def _limpo(v: Any) -> str:
    texto = _valor(v)
    return texto[:-len(DUVIDA)].strip() if texto.endswith(DUVIDA) else texto.replace("(?)", "").strip()


def _duvidoso(v: Any) -> bool:
    return "(?)" in _valor(v)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "")
                   if unicodedata.category(c) != "Mn").upper()


def _palavras(nome: str) -> list[str]:
    return [p for p in re.split(r"[^A-Z]+", _sem_acento(nome))
            if p and p not in ("DE", "DA", "DO", "DOS", "DAS", "E")]


def mesmo_nome(a: str, b: str) -> float:
    """Quanto dois nomes coincidem, de 0 a 1, pelas palavras sem acento e sem
    «de/da/dos». SÓ CALCULA. A grafia do RG e a da DNV raramente batem letra a
    letra (D'Avila × D'Arilar, Alcântara × Alcantara)."""
    pa, pb = set(_palavras(a)), set(_palavras(b))
    if not pa or not pb:
        return 0.0
    # UMA LETRA TROCADA NÃO FAZ OUTRA PESSOA — «Izaias» e «Isaias» são o mesmo
    # falecido em dois documentos do mesmo óbito (medido em 12/10/2026). Palavra
    # de SEIS letras ou mais, do mesmo tamanho, vale como igual se só UMA letra
    # difere. Com cinco, «Maria» e «Mario» seriam a mesma pessoa — e não são.
    def casa(w: str) -> bool:
        return w in pb or (len(w) >= 6 and any(
            len(x) == len(w) and sum(1 for i, j in zip(w, x) if i != j) == 1
            for x in pb))
    return sum(1 for w in pa if casa(w)) / max(len(pa), len(pb))


def data_iso(texto: Any) -> str:
    """DD/MM/AAAA (ou com hífen, ou só dígitos) → AAAA-MM-DD; vazio se não é data."""
    t = _limpo(texto)
    m = re.match(r"^\s*(\d{1,2})\s*[/.\-]?\s*(\d{1,2})\s*[/.\-]?\s*(\d{4})\s*$", t)
    if not m:
        m2 = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", t)
        return t if m2 else ""
    d, mes, a = (int(x) for x in m.groups())
    try:
        return date(a, mes, d).isoformat()
    except ValueError:
        return ""


def so_digitos(texto: Any) -> str:
    return re.sub(r"\D", "", _limpo(texto))


def cpf_valido(numero: Any) -> bool:
    import cpf_cnpj
    return bool(cpf_cnpj.cpf_valido(so_digitos(numero)))


def cns_valido(numero: Any) -> bool:
    """O Cartão Nacional de Saúde: 15 dígitos, soma ponderada (15..1) múltipla
    de 11. SÓ CALCULA.

    E NÃO SE FILTRA PELO PRIMEIRO DÍGITO — eu filtrava por 1/2/7/8/9 e a DNV
    real de 01/10/2026 trouxe um cartão começando por 5, que passa na soma."""
    d = so_digitos(numero)
    if len(d) != 15:
        return False
    return sum(int(c) * (15 - i) for i, c in enumerate(d)) % 11 == 0


PARTICULAS = frozenset({"de", "da", "do", "dos", "das", "e"})


def _capitalizar(texto: str) -> str:
    """«CIDADE EXEMPLO» → «Cidade Exemplo», «ANA DE SOUSA» → «Ana de Sousa». Texto que
    já vem com maiúsculas e minúsculas fica como veio: a grafia é de quem escreveu."""
    texto = (texto or "").strip()
    if not texto or not texto.isupper():
        return texto
    palavras = texto.lower().split()
    # «D'AVILA» é «D'Avila», como o termo da casa escreve: cada pedaço do
    # apóstrofo ganha a maiúscula.
    return " ".join(w if (i and w in PARTICULAS)
                    else "'".join(s[:1].upper() + s[1:] for s in w.split("'"))
                    for i, w in enumerate(palavras))


def _uf_e_cidade(texto: Any) -> tuple[str, str]:
    """«Imperatriz-MA», «Cidade Exemplo MA», «TUCUMA - PA» → (cidade, UF)."""
    t = _limpo(texto)
    m = re.match(r"^(.*?)[\s\-/,]+([A-Za-z]{2})\.?$", t)
    if m:
        return _capitalizar(m.group(1).strip(" -/,")), m.group(2).upper()
    return _capitalizar(t), ""

