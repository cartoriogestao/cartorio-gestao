"""O transporte da CENSEC — a carga da CEP, da CESDI e do RCTO por API.

    «preciso integrar a censec via api no sistema do cartorio» — o oficial,
    09/10/2026

O CONTRATO FOI MEDIDO, E É PÚBLICO
    `https://censec.org.br/swagger/api/swagger.json` — «CENSEC API», OpenAPI
    3.0.1, versão **2.71.0 RTM**, lido em 09/10/2026 sem login. Em 15/08/2026
    estava escrito em `notas_censec` que os nomes das listas do envelope «só
    aparecem no Postman e no Swagger, que pedem login»: **o Swagger não pede**.
    É «não achar onde procurei não prova que não existe» outra vez — e desta
    vez a correção derrubou três nomes que o gerador vinha escrevendo.

    | | |
    |---|---|
    | caminho | `POST /api/cargas/upload-json` — «Informe os atos de todas as centrais; para cada central será criada uma carga» |
    | chave | cabeçalho `X-Api-Key` (`security: [{ApiKey}]`, o documento inteiro) |
    | homologação | `https://hml.censec.org.br` (artigo 43000708963 do suporte do CNB, v3.1, 08/07/2025) |
    | produção | `https://censec.org.br` |
    | corpo | `UploadCargaRequest`: `cns`, `quinzena`, `atosCep`, `atosCesdi`, `testamentos`, `declaracoes` |
    | resposta 200 | `CargaResults`: `cepResult`, `cesdiResult`, `testamentoResult`, `doiResult` |

O QUE O GERADOR ESCREVIA E A API NÃO ACEITARIA (medido contra o contrato)
    1. As listas eram `cep`, `cesdi` e `rcto`; são `atosCep`, `atosCesdi` e
       `testamentos`. A API ignoraria os atos e responderia carga vazia.
    2. Os vocabulários do contrato são **nomes** (`enum` de texto):
       `Cpf` e não `CPF`, `Usufrutuario` sem acento, `DivorcioDireto` e não
       `4`, `CompraEVenda` e não `6`, `Marco` — **sem cedilha** — e não
       `Março`. Este módulo traduz; os nomes estão transcritos abaixo do
       próprio `swagger.json`, e há teste que confere a tradução.
    3. `valor` é `number` no contrato, e ia como texto.

O QUE ELE NÃO FAZ
    Não lavra, não altera ato, não fecha quinzena (fechamento, inclusive o
    negativo, é na tela da CENSEC) e **não repete envio sozinho**: um POST que a
    Central pode ter recebido não sai de novo, porque carga repetida é ato
    duplicado na central nacional. Envio em HOMOLOGAÇÃO não marca ato nenhum
    como enviado — senão o ato que só foi testado sumiria da fila da produção.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import sqlite3
import ssl
import time
import unicodedata
import urllib.parse
from datetime import datetime
from typing import Any

import centrais_cred as CRED
import centrais_trava_sandbox as TRAVA
import notas_censec as NC


class CensecError(RuntimeError):
    """Não deu para falar com a CENSEC, ou ela recusou."""


class CensecRecusou(CensecError):
    """A Central respondeu, e a resposta é uma recusa dela."""


BASE_DO_AMBIENTE: dict[str, str] = {
    CRED.HOMOLOGACAO: "https://hml.censec.org.br",
    CRED.PRODUCAO: "https://censec.org.br",
}

CAMINHO: dict[str, str] = {
    "carga_json": "/api/cargas/upload-json",
}
CAMINHOS_QUE_ESCREVEM: frozenset[str] = frozenset({"carga_json"})

# A TRAVA DO SANDBOX: a produção nunca sai daqui num teste; a homologação, sim.
TRAVA.registrar_host_producao("censec.org.br")
TRAVA.registrar_host_homolog("hml.censec.org.br")

PRAZO_PADRAO = 60
CONTRATO = "CENSEC API 2.71.0 RTM — censec.org.br/swagger/api/swagger.json, lido em 09/10/2026"

# ------------------------------------------------- os vocabulários do contrato
#
# TRANSCRITOS DO `swagger.json` (enum de cada campo), na ordem dele. São a régua
# da conferência antes da rede: valor fora destas listas a API recusa com 400,
# e a recusa dela não diz qual ato.

TIPO_ATO_CEP = ("Escritura", "Procuracao", "ProcuracaoParaFinsPrevidenciarios",
                "RenunciaDeProcuracao", "RevogacaoDeProcuracao", "Substabelecimento",
                "AtaNotarial", "AtaNotarialDeUsucapiao", "ProcuracaoPrivada",
                "ProcuracaoAutoridadeEstrangeira")
NATUREZA_ESCRITURA = (
    "AcordoExtrajudicial", "AlienacaoFiduciaria", "Cessao", "CompraEVenda",
    "ConfissaoDeDividaOuDacaoEmPagamento", "Declaracao", "DeclaratoriaDeUniaoEstavel",
    "DeclaratoriaDeUniaoEstavelHomoafetiva", "Desapropriacao", "DissolucaoDeUniaoEstavel",
    "Distrato", "Doacao", "Emancipacao", "Hipoteca", "Incorporacao", "BemDeFamilia",
    "Locacao", "PactoAnteNupcial", "Penhor", "PromessaDeCessaoDeDireitosAquisitivos",
    "Quitacao", "Rerratificacao", "ReconhecimentoDePaternidade",
    "RegistroDeChancelaMecanica", "RemissaoDeForoELaudemios", "SemValorDeclarado",
    "Servidao", "Usufruto", "Condominio", "Parcelamento", "SociedadeEFundacoes",
    "Transacao", "DireitoDeUsoOuSuperficie", "Divisao", "Fianca",
    "DiretivasAntecipadasDeVontade", "ConferenciaDeBens", "Novacao",
    "CreditoComGarantia", "EmissaoDeCedula", "EmissaoDeDebentures", "Revogacao",
    "RenunciaDeDireitosHereditarios", "ComodatoOuMutuo", "PrestacaoDeServico",
    "ArrendamentoMercantil", "ConcessaoDeDominio", "ContratoDeNamoro", "Conciliacao",
    "Mediacao", "Afetacao", "Autocuratela", "DeclaratoriaComDiretivasDeCuratela",
    "PromessaDeCompraEVenda")
NATUREZA_USUCAPIAO = ("Ordinaria", "Extraordinaria", "EspecialRural",
                      "EspecialUrbana", "EspecialFamiliar")
REGIME_BENS = ("ComunhaoParcial", "ComunhaoUniversal", "ParticipacaoFinalNosAquestos",
               "SeparacaoTotal", "SeparacaoObrigatoria",
               "RegimeEspecificoAtribuidoEmPactoAntenupcial")
QUALIDADE_CEP = ("Outorgado", "Outorgante", "Interveniente", "Usufrutuario",
                 "Requerente", "Requerido", "Conciliador", "Mediador")
TIPO_DOCUMENTO_CEP = ("Cpf", "Cnpj", "Desconhecido", "Rnm", "Cin", "Rg", "Rne",
                      "Passaporte", "Cnh", "Ctps", "CarteiraIdentidadeMilitar",
                      "Crnm", "Dprnm")
TIPO_ATO_CESDI = ("Separacao", "Reconciliacao", "ConversaoDeSeparacaoEmDivorcio",
                  "DivorcioDireto", "Inventario", "Sobrepartilha", "Retificacao",
                  "NomeacaoDeInventariante", "Partilha", "InventarioComMenorOuIncapaz",
                  "RetificacaoAtoNaoNotarial")
QUALIDADE_CESDI = ("Separando", "Advogado", "CessionarioAdjudicatarios", "Cedente",
                   "Interveniente", "Anuente", "Reconciliando", "Divorciando",
                   "Falecido", "Viuvo", "Herdeiro", "Inventariante", "Companheiro")
RESPONSAVEL_CESDI = ("Conjuge1", "Conjuge2", "AmbosConjuges", "Outros", "SemDeclaracao")
TIPO_DOCUMENTO_CESDI = ("Cpf", "Cnpj", "Oab", "Rg", "Outros", "Desconhecido", "Rnm",
                        "Cin", "Rne", "Passaporte", "Cnh", "Ctps",
                        "CarteiraIdentidadeMilitar", "Crnm", "Dprnm")
TIPO_TESTAMENTO = ("Aditamento", "Cerrado", "Revogacao", "Testamento",
                   "TestamentoComRevogacao", "TestamentoSemConteudoPatrimonial")
MESES = ("", "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")
SITUACOES_DA_CARGA = ("AguardandoValidacao", "Finalizado", "Reprovado", "Excluido",
                      "AguardandoFechamento")

# O código numérico que o gerador guarda → o nome do contrato. As tabelas do
# CNB (artigos 43000536374/5/3) e o enum do swagger estão NA MESMA ORDEM — a
# correspondência abaixo foi conferida item a item (há teste).
_COD_NATUREZA = (1, 4, 5, 6, 10, 14, 15, 16, 17, 20, 21, 22, 23, 24, 25, 26, 28, 30,
                 31, 33, 34, 35, 36, 38, 39, 43, 45, 46, 48, 49, 50, 51, 52, 53, 54,
                 55, 56, 57, 58, 59, 60, 61, 62, 63, 70, 71, 72, 74, 75, 76, 77, 78,
                 79, 80)
NATUREZA_DO_CODIGO: dict[int, str] = dict(zip(_COD_NATUREZA, NATUREZA_ESCRITURA))
TIPO_ATO_CESDI_DO_CODIGO: dict[int, str] = dict(zip(range(1, 12), TIPO_ATO_CESDI))
NATUREZA_USUCAPIAO_DO_CODIGO: dict[int, str] = dict(zip(range(1, 6), NATUREZA_USUCAPIAO))
TIPO_TESTAMENTO_DO_CODIGO: dict[int, str] = dict(zip(range(1, 7), TIPO_TESTAMENTO))


def _sem_acento(t: Any) -> str:
    s = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in s if not unicodedata.combining(c))


def _do_vocabulario(valor: Any, vocabulario: tuple[str, ...]) -> str | None:
    """O nome do contrato com a grafia dele — sem acento e sem caixa errada."""
    alvo = _sem_acento(valor).replace(" ", "").lower()
    for nome in vocabulario:
        if nome.lower() == alvo:
            return nome
    return None


def _numero(texto_ou_centavos: Any) -> float | None:
    """`valor` é `number` no contrato. O gerador dá «1234.56»; vira 1234.56."""
    if texto_ou_centavos in (None, ""):
        return None
    try:
        return round(float(str(texto_ou_centavos).replace(",", ".")), 2)
    except ValueError:
        return None


def _responsavel(texto: Any) -> str | None:
    """O responsável pelos filhos menores, no vocabulário da CESDI.

    A coluna da casa é texto livre; só passa o que se reconhece sem dúvida.
    O resto vira impedimento — chutar «Outros» declararia à central quem
    ninguém declarou.
    """
    direto = _do_vocabulario(texto, RESPONSAVEL_CESDI)
    if direto:
        return direto
    t = _sem_acento(texto).upper()
    if "AMBOS" in t:
        return "AmbosConjuges"
    if "SEM DECLARA" in t or t.strip() in ("NAO HA", "NENHUM", "SEM FILHOS"):
        return "SemDeclaracao"
    return None


# ------------------------------------------------- do gerador para o contrato

def ato_cep(linha: dict) -> dict:
    """A linha de `notas_censec.montar_cep`, no formato de `AtoCepData`."""
    saida = {k: v for k, v in linha.items()
             if k in ("mne", "data", "livro", "livroComplemento", "folha",
                      "folhaComplemento", "dataValidade")}
    saida["tipoAtoCep"] = NC.TIPO_ATO_CEP.get(int(linha["tipoAtoCep"]))
    if linha.get("valor") is not None:
        saida["valor"] = _numero(linha["valor"])
    if "naturezaEscritura" in linha:
        saida["naturezaEscritura"] = NATUREZA_DO_CODIGO.get(int(linha["naturezaEscritura"]))
    if "naturezaAtaNotarialDeUsucapiao" in linha:
        saida["naturezaAtaNotarialDeUsucapiao"] = NATUREZA_USUCAPIAO_DO_CODIGO.get(
            int(linha["naturezaAtaNotarialDeUsucapiao"]))
    if linha.get("regimeBens"):
        saida["regimeBens"] = linha["regimeBens"]
    if linha.get("referentes"):
        saida["referentes"] = [{
            k: v for k, v in {
                "tipoAtoCep": NC.TIPO_ATO_CEP.get(int(r.get("tipoAtoCep") or 2)),
                "cns": int(r["cns"]) if str(r.get("cns") or "").isdigit() else None,
                "livro": r.get("livro"), "livroComplemento": r.get("livroComplemento"),
                "folha": r.get("folha"), "folhaComplemento": r.get("folhaComplemento"),
            }.items() if v is not None} for r in linha["referentes"]]
    saida["partes"] = [{
        k: v for k, v in {
            "nome": p.get("nome"),
            "tipoDocumento": _do_vocabulario(p.get("tipoDocumento"), TIPO_DOCUMENTO_CEP),
            "numeroDocumento": p.get("numeroDocumento"),
            "identidade": p.get("identidade"),
            "orgaoEmissor": p.get("orgaoEmissor"),
            "qualidade": _do_vocabulario(p.get("qualidade"), QUALIDADE_CEP),
            "estrangeiro": bool(p.get("estrangeiro")),
        }.items() if v is not None} for p in linha.get("partes", [])]
    return saida


def ato_cesdi(linha: dict) -> dict:
    """A linha de `notas_censec.montar_cesdi`, no formato de `AtoCesdiData`."""
    saida = {k: v for k, v in linha.items()
             if k in ("mne", "data", "livro", "livroComplemento", "folha",
                      "folhaComplemento", "dataCasamento", "regimeBens",
                      "quantidadeFilhosMaiores", "quantidadeFilhosMenores")
             and v is not None}
    saida["tipoAtoCesdi"] = TIPO_ATO_CESDI_DO_CODIGO.get(int(linha["tipoAtoCesdi"]))
    if linha.get("responsavel") is not None:
        saida["responsavel"] = _responsavel(linha["responsavel"])
    partes = []
    for p in linha.get("partes", []):
        item = {
            "nome": p.get("nome"),
            "qualidade": _do_vocabulario(p.get("qualidade"), QUALIDADE_CESDI),
            "estrangeiro": bool(p.get("estrangeiro")),
            "documentos": [{
                k: v for k, v in {
                    "documentoTipo": _do_vocabulario(d.get("documentoTipo"),
                                                     TIPO_DOCUMENTO_CESDI),
                    "prioridade": d.get("prioridade"),
                    "documento": d.get("documento"),
                    "uf": d.get("uf"),
                }.items() if v is not None} for d in p.get("documentos", [])],
            "conjugeTipo": p.get("conjugeTipo"),
            "dataNascimento": p.get("dataNascimento"),
            "localNascimentoPais": p.get("localNascimentoPais"),
            "localNascimentoUf": p.get("localNascimentoUF"),
            "localResidenciaPais": p.get("localResidenciaPais"),
            "localResidenciaMunicipio": p.get("localResidenciaMunicipio"),
            "localResidenciaUf": p.get("localResidenciaUF"),
            "sexo": (str(p["sexo"]).upper()[:1] if p.get("sexo") else None),
        }
        partes.append({k: v for k, v in item.items() if v is not None})
    saida["partes"] = partes
    return saida


def testamento(linha: dict) -> dict:
    """A linha de `notas_censec.montar_rcto`, no formato de `TestamentoData`."""
    saida = {k: v for k, v in linha.items() if k != "tipoTestamento" and v is not None}
    saida["tipoTestamento"] = TIPO_TESTAMENTO_DO_CODIGO.get(int(linha["tipoTestamento"]))
    if "revogacaoCartorioCns" in saida:
        cns = str(saida["revogacaoCartorioCns"])
        saida["revogacaoCartorioCns"] = int(cns) if cns.isdigit() else None
    return {k: v for k, v in saida.items() if v is not None}


TRADUTOR = {"CEP": ("atosCep", ato_cep), "CESDI": ("atosCesdi", ato_cesdi),
            "RCTO": ("testamentos", testamento)}


def cabecalho(cns: Any, ano: int, mes: int, quinzena: int) -> dict:
    """`cns` e `quinzena` — os dois obrigatórios de `UploadCargaRequest`."""
    return {"cns": int(NC.so_digitos(cns) or 0),
            "quinzena": {"anoReferencia": int(ano), "quinzenaReferencia": int(quinzena),
                         "mesReferencia": MESES[int(mes)]}}


def montar_envio(con, ano: int, mes: int, quinzena: int, cns: Any) -> dict:
    """O corpo da quinzena com as três centrais, pela mesma conta da tela.

    `notas_censec.separar` decide quem está apto — a conta é uma só, para a
    tela não dizer uma coisa e a carga levar outra. Volta o corpo, os atos de
    cada central (para registrar a remessa) e os impedidos (para a tela).
    """
    corpo = cabecalho(cns, ano, mes, quinzena)
    atos: dict[str, list[dict]] = {}
    impedidos: dict[str, list[dict]] = {}
    for central, (chave, traduzir) in TRADUTOR.items():
        sep = NC.separar(con, central, ano, mes, quinzena)
        impedidos[central] = sep["impedidos"]
        if sep["aptos"]:
            corpo[chave] = [traduzir(x["linha"]) for x in sep["aptos"]]
            atos[central] = [x["ato"] for x in sep["aptos"]]
    return {"corpo": corpo, "atos": atos, "impedidos": impedidos,
            "prazo": NC.prazo_de_fechamento(ano, mes, quinzena)}


def conferir_corpo(corpo: dict) -> list[str]:
    """O que a API recusaria, dito ANTES da rede. Lista vazia: pode ir.

    São os `required` e os `enum` do contrato. A recusa dela (400) não diz
    qual ato nem qual campo; aqui cada problema sai com o livro e a folha.
    """
    p: list[str] = []
    if not corpo.get("cns"):
        p.append("sem o CNS da serventia")
    q = corpo.get("quinzena") or {}
    if q.get("mesReferencia") not in MESES[1:] or q.get("quinzenaReferencia") not in (1, 2):
        p.append("quinzena de referência inválida")
    if not any(corpo.get(k) for k in ("atosCep", "atosCesdi", "testamentos")):
        p.append("nenhum ato apto nesta quinzena — nada a enviar")

    def onde(a):
        return f"livro {a.get('livro', '?')}, fl. {a.get('folha', '?')}"

    regras = {
        "atosCep": (("data", "folha", "livro", "partes", "tipoAtoCep"),
                    {"tipoAtoCep": TIPO_ATO_CEP, "naturezaEscritura": NATUREZA_ESCRITURA,
                     "naturezaAtaNotarialDeUsucapiao": NATUREZA_USUCAPIAO,
                     "regimeBens": REGIME_BENS},
                    ("nome", "qualidade", "tipoDocumento"),
                    {"qualidade": QUALIDADE_CEP, "tipoDocumento": TIPO_DOCUMENTO_CEP}),
        "atosCesdi": (("data", "folha", "livro", "partes", "tipoAtoCesdi"),
                      {"tipoAtoCesdi": TIPO_ATO_CESDI, "regimeBens": REGIME_BENS,
                       "responsavel": RESPONSAVEL_CESDI},
                      ("documentos", "nome", "qualidade"),
                      {"qualidade": QUALIDADE_CESDI}),
        "testamentos": (("cpf", "dataNascimento", "dataTestamento", "folha", "livro",
                         "nome", "tipoTestamento"),
                        {"tipoTestamento": TIPO_TESTAMENTO}, (), {}),
    }
    for lista, (obrig, vocab, obrig_parte, vocab_parte) in regras.items():
        for a in corpo.get(lista) or []:
            for campo in obrig:
                if a.get(campo) in (None, "", []):
                    p.append(f"{lista}, {onde(a)}: falta «{campo}»")
            for campo, nomes in vocab.items():
                if campo in a and a[campo] not in nomes:
                    p.append(f"{lista}, {onde(a)}: «{campo}» fora do vocabulário da CENSEC")
            for parte in a.get("partes") or []:
                for campo in obrig_parte:
                    if parte.get(campo) in (None, "", []):
                        p.append(f"{lista}, {onde(a)}, {parte.get('nome') or 'parte'}: "
                                 f"falta «{campo}»")
                for campo, nomes in vocab_parte.items():
                    if campo in parte and parte[campo] not in nomes:
                        p.append(f"{lista}, {onde(a)}, {parte.get('nome') or 'parte'}: "
                                 f"«{campo}» fora do vocabulário da CENSEC")
    return p


# ------------------------------------------------------------- o transporte

def base_do_ambiente(ambiente: Any) -> str:
    qual = str(ambiente or CRED.HOMOLOGACAO).strip().upper()
    if qual not in BASE_DO_AMBIENTE:
        raise CensecError(f"Não conheço o ambiente «{qual}» da CENSEC. Os que existem: "
                          + ", ".join(BASE_DO_AMBIENTE) + ".")
    return BASE_DO_AMBIENTE[qual]


def chave(ambiente: Any, *, pasta=None) -> str:
    """A `X-Api-Key` daquele ambiente — pela porta do token, a única que a dá."""
    qual = str(ambiente or CRED.HOMOLOGACAO).strip().upper()
    if not CRED.tem(CRED.CENSEC, qual, pasta):
        raise CensecError(
            f"A chave de integração da CENSEC ainda não foi informada para "
            f"{'a homologação' if qual == CRED.HOMOLOGACAO else 'a produção'}. "
            f"Ela se gera dentro da CENSEC e se cadastra em Administrativo → "
            f"Configurações, na tabela das Centrais. "
            + CRED.ONDE_SE_OBTEM_O_TOKEN[CRED.CENSEC])
    return CRED.token_guardado(CRED.CENSEC, qual, pasta)


def _bater(ambiente: str, metodo: str, caminho: str, *, corpo: bytes | None = None,
           prazo: int = PRAZO_PADRAO, pasta=None) -> dict:
    """Uma requisição. Devolve `{status, json, texto}` — não estoura por 4xx.

    **SÓ UMA TENTATIVA.** O único caminho daqui é um POST de carga, e POST que
    a Central pode ter recebido não se repete sozinho.
    """
    p = urllib.parse.urlsplit(base_do_ambiente(ambiente))
    if p.scheme != "https":
        raise CensecError(f"A base da CENSEC tem de ser https, e veio «{p.geturl()}».")
    try:
        hospedeiro, porta = TRAVA.destino_seguro(p.hostname or "", p.port or 443)
    except TRAVA.SandboxTravaRecusou as erro:
        raise CensecError(str(erro)) from erro
    cabecas = {"Accept": "application/json",
               "Content-Type": "application/json; charset=utf-8",
               "User-Agent": "CartorioGestao",
               "X-Api-Key": chave(ambiente, pasta=pasta)}
    conexao = None
    inicio = time.monotonic()
    try:
        conexao = http.client.HTTPSConnection(
            hospedeiro, porta, timeout=prazo, context=ssl.create_default_context())
        conexao.request(metodo, caminho, body=corpo, headers=cabecas)
        r = conexao.getresponse()
        texto = r.read().decode("utf-8", errors="replace")
    except (OSError, ssl.SSLError, http.client.HTTPException) as erro:
        decorrido = time.monotonic() - inicio
        raise CensecError(
            f"Não consegui falar com a CENSEC em {hospedeiro} ({erro}). "
            + ("Se a conexão caiu depois de mandar, a carga PODE ter chegado: "
               "confira na tela da CENSEC antes de mandar de novo."
               if decorrido > 2 else "Nada foi enviado; tente de novo.")) from erro
    finally:
        if conexao is not None:
            conexao.close()
    try:
        como_json = json.loads(texto) if texto.strip() else None
    except ValueError:
        como_json = None
    return {"status": r.status, "json": como_json, "texto": texto}


def resumir_resposta(resposta: Any) -> dict:
    """`CargaResults` por central: deu certo?, situação, carga, recusas.

    **HTTP 200 NÃO QUER DIZER QUE OS ATOS ENTRARAM** — é a lição do
    e-Proclamas. Cada central volta com `success`, `exception` e
    `validationResults` (com livro e folha de cada ato que teve erro). E
    `AguardandoValidacao` quer dizer que o arquivo foi importado e ainda vai
    passar por outras validações (artigo 43000708963): só a tela da CENSEC
    diz se ficou apto para fechar.
    """
    mapa = {"CEP": "cepResult", "CESDI": "cesdiResult", "RCTO": "testamentoResult",
            "CTP": "doiResult"}
    saida: dict[str, dict] = {}
    if not isinstance(resposta, dict):
        return saida
    for central, chave_ in mapa.items():
        r = resposta.get(chave_)
        if not isinstance(r, dict):
            continue
        carga = r.get("carga") or {}
        excecao = r.get("exception") or {}
        recusas, avisos = [], []
        for v in r.get("validationResults") or []:
            mensagens = [str(e.get("message") or e.get("code") or "").strip()
                         for e in (v.get("Errors") or v.get("errors") or [])
                         if (e.get("level") or "Error") == "Error"]
            alertas = [str(e.get("message") or e.get("code") or "").strip()
                       for e in (v.get("validations") or [])
                       if e.get("level") == "Warning"]
            item = {"livro": v.get("livro"), "folha": v.get("folha"),
                    "livroComplemento": v.get("livroComplemento"),
                    "folhaComplemento": v.get("folhaComplemento")}
            if v.get("hasError") or mensagens:
                recusas.append({**item, "mensagens": [m for m in mensagens if m]})
            elif v.get("hasWarning") or alertas:
                avisos.append({**item, "mensagens": [m for m in alertas if m]})
        saida[central] = {
            "sucesso": bool(r.get("success")) and not excecao.get("occurred"),
            "situacao": carga.get("status"),
            "carga_id": carga.get("id"),
            "erro": excecao.get("message") if excecao.get("occurred") else
                    (r.get("fileFormatError") or None),
            "recusas": recusas, "avisos": avisos,
        }
    return saida


def enviar_carga(corpo: dict, ambiente: Any, *, pasta=None) -> dict:
    """Manda a carga. Confere antes; recusa da Central vira `CensecRecusou`."""
    problemas = conferir_corpo(corpo)
    if problemas:
        raise CensecError("A carga não foi enviada — a CENSEC recusaria: "
                          + "; ".join(problemas[:12]))
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")   # UTF-8 sem BOM
    r = _bater(str(ambiente or CRED.HOMOLOGACAO).upper(), "POST", CAMINHO["carga_json"],
               corpo=dados, pasta=pasta)
    if 200 <= int(r["status"]) < 300:
        return {"status": r["status"], "resposta": r["json"],
                "por_central": resumir_resposta(r["json"])}
    detalhe = ""
    if isinstance(r["json"], dict):
        detalhe = str(r["json"].get("title") or r["json"].get("message")
                      or r["json"].get("detail") or "")
        erros = r["json"].get("errors")
        if isinstance(erros, dict):
            detalhe += " " + "; ".join(f"{k}: {', '.join(map(str, v))}"
                                       for k, v in list(erros.items())[:8])
    detalhe = (detalhe or r["texto"][:400]).strip()
    motivo = {401: "chave de integração inválida ou ausente",
              403: "esta chave não tem permissão de carga"}.get(int(r["status"]), "")
    raise CensecRecusou(f"A CENSEC recusou a carga (HTTP {r['status']}): "
                        f"{motivo or detalhe or 'sem motivo informado'}.")


# ------------------------------------------------- a quinzena, de ponta a ponta

def _situacao_da_remessa(resumo: dict) -> str:
    if not resumo.get("sucesso"):
        return "REJEITADA"
    return "CONFIRMADA" if resumo.get("situacao") in ("Finalizado",) else "ENVIADA"


def enviar_quinzena(db, ano: int, mes: int, quinzena: int, *, cns: Any,
                    ambiente: Any = CRED.HOMOLOGACAO, por: str = "",
                    pasta=None) -> dict:
    """Monta, confere, envia e — na PRODUÇÃO — registra a remessa.

    Recebe `db`, e não `con`, pela regra de `ato_selado.obter_selo`: a chamada
    de rede (até um minuto) nunca acontece dentro de `db.transaction()`, que é
    `BEGIN IMMEDIATE` e poria o balcão inteiro no `busy_timeout`.

    **Em homologação nada se grava em `nt_remessas`.** Marcar o ato como
    ENVIADO depois de um teste o tiraria da fila da produção, e a quinzena
    real fecharia sem ele.
    """
    qual = str(ambiente or CRED.HOMOLOGACAO).upper()
    with db.connect() as con:
        con.row_factory = sqlite3.Row
        envio = montar_envio(con, ano, mes, quinzena, cns)
    resultado = enviar_carga(envio["corpo"], qual, pasta=pasta)
    resultado.update({"ambiente": qual, "atos": envio["atos"],
                      "impedidos": envio["impedidos"], "remessas": []})
    if qual != CRED.PRODUCAO:
        return resultado

    agora = datetime.now().isoformat(timespec="seconds")
    sha = hashlib.sha256(
        json.dumps(envio["corpo"], ensure_ascii=False).encode("utf-8")).hexdigest()
    inicio, fim = NC.periodo_da_quinzena(ano, mes, quinzena)
    with db.transaction() as con:
        for central, atos in envio["atos"].items():
            resumo = resultado["por_central"].get(central, {"sucesso": False,
                                                            "erro": "sem resultado"})
            situacao = _situacao_da_remessa(resumo)
            mensagem = "; ".join(filter(None, [
                f"API ({CONTRATO.split(' — ')[0]}): {resumo.get('situacao') or '?'}",
                resumo.get("erro"),
                f"{len(resumo.get('recusas') or [])} ato(s) recusado(s)"
                if resumo.get("recusas") else ""]))
            cur = con.execute(
                """INSERT INTO nt_remessas(central, competencia, ano_referencia,
                       mes_referencia, quinzena, periodo_inicio, periodo_fim, situacao,
                       quantidade, arquivo_nome, arquivo_sha256, protocolo_central,
                       mensagem, gerada_em, gerada_por, enviada_em, enviada_por,
                       criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (central, f"{ano:04d}-{mes:02d}", ano, mes, quinzena, inicio, fim,
                 situacao, len(atos), f"API {CAMINHO['carga_json']}", sha,
                 resumo.get("carga_id"), mensagem, agora, por,
                 agora if situacao != "REJEITADA" else None,
                 por if situacao != "REJEITADA" else None, agora))
            remessa_id = cur.lastrowid
            recusados = {(str(x.get("livro") or ""), str(x.get("folha") or "")): x
                         for x in resumo.get("recusas") or []}
            for a in atos:
                rec = recusados.get((str(a.get("livro") or ""), str(a.get("folha") or "")))
                item_sit = "REJEITADA" if (rec or situacao == "REJEITADA") else situacao
                con.execute(
                    """INSERT INTO nt_remessa_itens(remessa_id, ato_id, situacao,
                           mensagem, criado_em) VALUES (?,?,?,?,?)""",
                    (remessa_id, a["id"], item_sit,
                     "; ".join(rec["mensagens"]) if rec else None, agora))
            resultado["remessas"].append({"central": central, "id": remessa_id,
                                          "situacao": situacao})
    return resultado
