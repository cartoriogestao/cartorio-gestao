"""O CARNÊ-LEÃO E O LIVRO-CAIXA DO TITULAR — o imposto de renda mensal do delegatário.

POR QUE EXISTE (26/10/2026)
    O levantamento das lacunas de 17/10/2026 (C10) achou «exportação para
    carnê-leão e livro-caixa do IRPF do titular: NÃO EXISTE», e a agenda do
    oficial (`oficial_obrigacoes.A_CONFIRMAR`) tinha o carnê-leão como pergunta
    sem prazo. O Livro Diário Auxiliar (`livro_diario`) e as despesas
    (`despesas`, PR #12) já existiam; faltava a outra conta, que é PESSOAL do
    titular e não da serventia: quanto ele recebeu no mês, quanto pagou do que
    pode deduzir, e o imposto pela tabela progressiva.

DADO FISCAL PESSOAL — SÓ O ADMIN
    A rota é `roles_required("ADMIN")` inteira: nem o gerente nem o auditor da
    casa veem a renda do titular.

O QUE ESTE MÓDULO NÃO AFIRMA (e a tela diz o mesmo)
    Nenhuma regra fiscal foi conferida em documento desta casa: não há aqui a
    lei, a instrução normativa da Receita nem o leiaute do Carnê-Leão Web
    (procurado em FONTES_EXTERNAS/ e docs/ em 26/10/2026 — nada). Por isso:
    - a lista de categorias DEDUTÍVEIS é SUGESTÃO, «a conferir com o contador»,
      e quem marca cada despesa é o oficial;
    - a TABELA PROGRESSIVA não está escrita no código: é cadastrada na tela, com
      a vigência e a fonte. Sem tabela cadastrada não há imposto calculado — e a
      tela diz isso em vez de mostrar zero;
    - o PRAZO do carnê-leão só entra na agenda do oficial quando ele cadastra a
      regra e a fonte (configuração). Até lá continua a pergunta de sempre;
    - a EXPORTAÇÃO é CSV legível, e não o arquivo de importação do Carnê-Leão
      Web, cujo leiaute falta nesta casa. O DARF sai pelo Carnê-Leão Web ou pelo
      Sicalc — este módulo NÃO gera código de barras.

AS DUAS RECEITAS DO MÊS, E POR QUE ELAS DIFEREM
    O Livro Diário lança a receita PELO SELO, no dia da prática do ato (CN-MA
    art. 190, I): é a competência do ato. O livro-caixa do imposto de renda é
    apurado no REGIME DE CAIXA: o que efetivamente entrou no mês. As duas
    contas mudam de mês em dois casos, e a tela mostra os dois números lado a
    lado com a diferença:
    - o DEPÓSITO PRÉVIO entra antes do ato. O CN-MA art. 202 manda baixá-lo e
      lançá-lo «como receita» quando o ato é praticado — é a regra do Livro
      Diário, e é o PADRÃO desta conta (`NO_USO`). Se o contador entender que,
      para o imposto, ele conta no mês em que o dinheiro entrou, a configuração
      muda para `NO_RECEBIMENTO`. Os dois números aparecem sempre.
    - o emolumento DIFERIDO: o ato sai no mês (o selo marca «Diferido» e o
      Livro Diário não o soma), e o dinheiro entra quando o interessado paga —
      no caixa, num mês seguinte.

DE ONDE SAI CADA NÚMERO
    - Recebido no caixa: `cx_lancamentos` de natureza RECEBIMENTO, sem troco,
      sem estorno, sem excluído, sem gratuidade (valor zero) e sem o USO de
      depósito (aquele dinheiro entrou antes, e quem o conta é o livro do
      depósito). Só o EMOLUMENTO é receita do titular: os fundos são repasse
      (CN-MA art. 191). Quando o lançamento não discrimina os fundos — e no
      lançamento manual quase nunca discrimina (`gestor_financeiro`, medido em
      06/10/2026) —, o valor inteiro entra e a linha fica MARCADA «sem
      discriminação», com a soma à vista: ninguém inventa a parte dos fundos.
    - Depósito prévio: o Livro de Controle de Depósito Prévio
      (`livro_deposito_previo.livro`) — depósitos do mês, conversões e
      devoluções pelas datas do rastro. O valor convertido inclui os fundos, e
      fica marcado como tal.
    - «Outra entrada» do caixa não entra na conta: aparece à parte, para o
      contador dizer o que é.
    - Lançamento avulso do livro-caixa (`cl_lancamentos`): o que entrou ou saiu
      fora do sistema (ressarcimento de gratuidade, despesa paga do bolso),
      lançado pelo oficial com documento.
    - Despesas: as do Livro Diário (`ld_despesas`, no dia do pagamento), que já
      incluem as do módulo de despesas conferidas no extrato. A GUIA DE FUNDO
      NÃO É DESPESA (decisão do oficial, 24/10/2026) e não chega aqui — fundo
      não é receita, e repassá-lo não é gasto do titular.

O EXCESSO DE DESPESA NÃO É LEVADO SOZINHO AO MÊS SEGUINTE
    Quando as despesas dedutíveis passam da receita, a base do mês é zero e o
    excesso aparece escrito. Se ele se compensa nos meses seguintes é regra
    fiscal que não está nesta casa: a conferir com o contador.

PostgreSQL nativo, pelo `bd_nativo`. Dinheiro em centavos, `bigint`. Data e
hora se calculam no Python (regra da casa).
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date
from typing import Any

import livro_diario as LD
from bd_nativo import banco
from caixa_schema import centavos, reais

# ------------------------------------------------- as categorias do imposto
#
# A CATEGORIA FISCAL É PRÓPRIA, e não a do Livro Diário nem a das despesas:
# a mesma conta de luz é «Energia» para o pagamento e «custeio» para o
# imposto, e a pergunta que se faz a ela é outra (deduz ou não deduz).
#
# `sugestao` é True, False ou None (sem sugestão). TODA a coluna é SUGESTÃO,
# a conferir com o contador: nenhuma linha aqui foi lida em norma desta casa.

CATEGORIAS_FISCAIS: dict[str, tuple[str, bool | None]] = {
    "PESSOAL": ("Remuneração dos prepostos com vínculo empregatício", True),
    "ENCARGOS": ("Encargos trabalhistas e previdenciários dos prepostos", True),
    "CUSTEIO": (("Custeio da serventia (aluguel, energia, água, telefone, internet, "
                 "material de expediente, limpeza, segurança, tarifas, sistemas)"), True),
    "SERVICOS_TERCEIROS": (("Serviços de terceiros sem vínculo (assessoria contábil, "
                            "jurídica, manutenção, digitalização)"), True),
    "TRIBUTOS_DA_ATIVIDADE": ("Tributos da atividade (ISS sobre os emolumentos)", True),
    "BENEFICIOS": ("Benefícios dos prepostos (plano de saúde coletivo e outros)", None),
    "CURSOS": ("Cursos e treinamento", None),
    "BENS_DURAVEIS": ("Compra de bens duráveis e obras (móveis, equipamentos, reformas)",
                      False),
    "PESSOAL_DO_TITULAR": ("Despesa pessoal do titular ou alheia à atividade", False),
    "OUTRAS": ("Outras — decidir com o contador", None),
}

#: A categoria fiscal SUGERIDA a partir da categoria da despesa (`despesas`).
#: Só sugere: a marcação é do oficial, despesa por despesa.
SUGESTAO_POR_CATEGORIA: dict[str, str] = {
    "LOCACAO": "CUSTEIO", "CONCESSIONARIAS": "CUSTEIO", "PESSOAL": "PESSOAL",
    "ENCARGOS": "ENCARGOS", "PLANO_SAUDE": "BENEFICIOS", "MATERIAIS": "CUSTEIO",
    "INFORMATICA": "CUSTEIO", "MOVEIS_EQUIPAMENTOS": "BENS_DURAVEIS",
    "OBRAS": "BENS_DURAVEIS", "LIMPEZA_SEGURANCA": "CUSTEIO",
    "ARQUIVO_SEGURANCA": "SERVICOS_TERCEIROS", "CURSOS": "CURSOS",
    "ASSESSORIA": "SERVICOS_TERCEIROS", "ISS": "TRIBUTOS_DA_ATIVIDADE",
    "TARIFAS": "CUSTEIO", "OUTRAS": "OUTRAS",
}

AVISO_DA_LISTA = ("A lista de categorias dedutíveis é SUGESTÃO do sistema e não foi "
                  "conferida em norma desta casa: a conferir com o contador antes de "
                  "usar o número no Carnê-Leão Web.")

AVISO_DO_LEIAUTE = ("O leiaute de importação do Carnê-Leão Web não está nesta casa "
                    "(procurado em FONTES_EXTERNAS/ e docs/ em 26/10/2026). Este arquivo "
                    "é uma planilha legível para lançar à mão ou entregar ao contador. "
                    "O DARF sai pelo Carnê-Leão Web ou pelo Sicalc — não por aqui.")

# --------------------------------------------------------- a configuração

NO_USO, NO_RECEBIMENTO = "NO_USO", "NO_RECEBIMENTO"
MODOS_DO_DEPOSITO = {
    NO_USO: "No mês em que o ato é praticado e o depósito é convertido (CN-MA art. 202 "
            "— a regra do Livro Diário)",
    NO_RECEBIMENTO: "No mês em que o dinheiro do depósito entrou (menos as devoluções do mês)",
}

ULTIMO_DIA_UTIL, DIA_DO_MES = "ULTIMO_DIA_UTIL", "DIA_DO_MES"
REGRAS_DO_PRAZO = {
    "": "Não cadastrado — o carnê-leão continua como pergunta na agenda",
    ULTIMO_DIA_UTIL: "Último dia útil do mês seguinte ao do recebimento",
    DIA_DO_MES: "Um dia fixo do mês seguinte ao do recebimento",
}

PADRAO: dict[str, str] = {
    "carne_leao_deposito_previo": NO_USO,
    "carne_leao_prazo_regra": "",
    "carne_leao_prazo_dia": "",
    "carne_leao_prazo_fonte": "",
    "carne_leao_lista_conferida": "",
}

MINIMO_DO_TEXTO = 10
LIMITE = 300
_DIGITOS_DO_MES = re.compile(r"([0-9]{4})-([0-9]{2})")
_PERCENTUAL = re.compile(r"[0-9]{1,3}(,[0-9]{1,2})?")


class CarneLeaoError(ValueError):
    """Impedimento de regra, com a frase pronta para a tela."""


# ---------------------------------------------------------------- esquema

SCHEMA: tuple[tuple[str, str], ...] = (
    # A MARCAÇÃO DE CADA DESPESA DO LIVRO DIÁRIO. Remarcar não apaga: a
    # anterior ganha `substituida_em`, e a que vale é a única sem ela.
    ("cl_marcacoes", """
        CREATE TABLE IF NOT EXISTS cl_marcacoes (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            ld_despesa_id bigint NOT NULL REFERENCES ld_despesas(id),
            categoria_fiscal TEXT NOT NULL,
            dedutivel integer NOT NULL CHECK (dedutivel IN (0, 1)),
            observacao TEXT NOT NULL DEFAULT '',
            marcado_em TEXT NOT NULL,
            marcado_por TEXT NOT NULL,
            substituida_em TEXT
        )"""),
    ("ux_cl_marcacoes_vigente", """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_cl_marcacoes_vigente
            ON cl_marcacoes (ld_despesa_id) WHERE substituida_em IS NULL"""),
    # O QUE ENTROU OU SAIU FORA DO SISTEMA. Não se edita nem se apaga: anula-se
    # com o motivo, como a despesa do Livro Diário.
    ("cl_lancamentos", """
        CREATE TABLE IF NOT EXISTS cl_lancamentos (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            data TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('RECEITA', 'DESPESA')),
            descricao TEXT NOT NULL,
            documento TEXT NOT NULL DEFAULT '',
            valor bigint NOT NULL CHECK (valor > 0),
            categoria_fiscal TEXT NOT NULL DEFAULT '',
            dedutivel integer NOT NULL DEFAULT 0 CHECK (dedutivel IN (0, 1)),
            lancado_em TEXT NOT NULL,
            lancado_por TEXT NOT NULL,
            anulado_em TEXT,
            anulado_por TEXT NOT NULL DEFAULT '',
            motivo_anulacao TEXT NOT NULL DEFAULT ''
        )"""),
    ("ix_cl_lancamentos_data",
     "CREATE INDEX IF NOT EXISTS ix_cl_lancamentos_data ON cl_lancamentos (data, id)"),
    # A TABELA PROGRESSIVA MENSAL, cadastrada pelo oficial, com a vigência e a
    # fonte. As faixas vão dentro dela (JSON) e não mudam: tabela errada se
    # anula com o motivo, e cadastra-se outra.
    ("cl_tabelas", """
        CREATE TABLE IF NOT EXISTS cl_tabelas (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            vigencia_inicio TEXT NOT NULL,
            descricao TEXT NOT NULL,
            fonte TEXT NOT NULL,
            faixas TEXT NOT NULL,
            cadastrada_em TEXT NOT NULL,
            cadastrada_por TEXT NOT NULL,
            anulada_em TEXT,
            anulada_por TEXT NOT NULL DEFAULT '',
            motivo_anulacao TEXT NOT NULL DEFAULT ''
        )"""),
    ("ux_cl_tabelas_vigencia", """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_cl_tabelas_vigencia
            ON cl_tabelas (vigencia_inicio) WHERE anulada_em IS NULL"""),
)


def init_carne_leao_schema(con) -> None:
    """Cria as tabelas e os índices que faltarem. Idempotente."""
    bd = banco(con)
    for nome, comando in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(comando)


# ------------------------------------------------------------- auxiliares

def _texto(valor: Any, limite: int = LIMITE) -> str:
    limpo = re.sub(r"[\x00-\x1f\x7f]", " ", str(valor or ""))
    return " ".join(limpo.split())[:limite]


def competencia(valor: Any) -> str:
    """'AAAA-MM' conferido (dígito ASCII, mês de 1 a 12)."""
    m = _DIGITOS_DO_MES.fullmatch(str(valor or "").strip()[:7])
    if not m or not 1 <= int(m.group(2)) <= 12 or int(m.group(1)) < 1:
        raise CarneLeaoError("Informe o mês no formato AAAA-MM.")
    return m.group(0)


def _limites(comp: str) -> tuple[str, str]:
    ano, mes = int(comp[:4]), int(comp[5:7])
    seguinte = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return f"{comp}-01", f"{seguinte[0]:04d}-{seguinte[1]:02d}-01"


def _no_mes(dia: Any, comp: str) -> bool:
    return str(dia or "")[:7] == comp


def _data(valor: Any, *, hoje: str) -> str:
    texto = str(valor or "").strip()[:10]
    try:
        dia = date.fromisoformat(texto)
    except ValueError as erro:
        raise CarneLeaoError("A data não é uma data válida (AAAA-MM-DD).") from erro
    if dia.isoformat() > hoje:
        raise CarneLeaoError("A data está no futuro: o livro-caixa lança o que já "
                             "entrou ou já foi pago.")
    return dia.isoformat()


def _centavos_da_tela(valor: Any) -> int:
    import despesas as DP
    try:
        return DP.centavos_da_tela(valor)
    except DP.DespesaError as erro:
        raise CarneLeaoError(str(erro)) from erro


def _percentual_em_bp(valor: Any) -> int:
    """«7,5» → 750 (centésimos de ponto percentual). Recusa o que não é número."""
    texto = str(valor or "").strip().replace("%", "").strip() or "0"
    if not _PERCENTUAL.fullmatch(texto):
        raise CarneLeaoError(f"Alíquota ilegível: «{valor}». Use 7,5 para 7,5%.")
    inteiro, _, frac = texto.partition(",")
    bp = int(inteiro) * 100 + int((frac + "00")[:2])
    if bp > 10000:
        raise CarneLeaoError("Alíquota acima de 100%.")
    return bp


def percentual(bp: int) -> str:
    """750 → «7,5»; 1500 → «15»."""
    inteiro, resto = divmod(int(bp), 100)
    return f"{inteiro}" + (f",{resto:02d}".rstrip("0") if resto else "")


# ----------------------------------------------------------- a configuração

def configuracao(con) -> dict[str, str]:
    """O que está gravado, sobre o padrão. Só LÊ."""
    gravado = {r["key"]: r["value"] for r in banco(con).ler(
        "SELECT key, value FROM settings WHERE key = ANY(%s) ORDER BY key", (list(PADRAO),))}
    return {k: (gravado[k] if gravado.get(k) is not None else v) for k, v in PADRAO.items()}


def _gravar(bd, valores: Mapping[str, str]) -> None:
    for chave, valor in valores.items():
        bd.escrever("INSERT INTO settings (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (chave, valor))


def gravar_configuracao(con, valores: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    """O modo do depósito prévio e a regra do prazo. ESCREVE. Devolve o que mudou.

    O PRAZO SÓ ENTRA COM A FONTE: «último dia útil do mês seguinte» sem dizer
    onde se leu seria o prazo escrito de memória que a agenda recusa.
    """
    modo = str(valores.get("carne_leao_deposito_previo") or NO_USO)
    if modo not in MODOS_DO_DEPOSITO:
        raise CarneLeaoError("Escolha quando o depósito prévio conta como receita.")
    regra = str(valores.get("carne_leao_prazo_regra") or "")
    if regra not in REGRAS_DO_PRAZO:
        raise CarneLeaoError("Regra de prazo desconhecida.")
    dia, fonte = "", _texto(valores.get("carne_leao_prazo_fonte"), 500)
    if regra == DIA_DO_MES:
        texto = str(valores.get("carne_leao_prazo_dia") or "").strip()
        if not texto.isascii() or not texto.isdigit() or not 1 <= int(texto) <= 31:
            raise CarneLeaoError("Informe o dia do mês do prazo (1 a 31).")
        dia = str(int(texto))
    if regra and len(fonte) < MINIMO_DO_TEXTO:
        raise CarneLeaoError(
            "Diga de onde vem a regra do prazo (a norma da Receita, ou a orientação "
            "escrita do contador): prazo sem fonte não entra na agenda do oficial.")
    novo = {"carne_leao_deposito_previo": modo, "carne_leao_prazo_regra": regra,
            "carne_leao_prazo_dia": dia, "carne_leao_prazo_fonte": fonte if regra else ""}
    bd = banco(con)
    antes = configuracao(bd)
    _gravar(bd, novo)
    return {k: (antes[k], v) for k, v in novo.items() if antes[k] != v}


def registrar_lista_conferida(con, *, por: str, quando: str, contador: Any) -> str:
    """O oficial registra que conferiu a lista de dedutíveis com o contador. ESCREVE."""
    quem = _texto(contador, 150)
    if len(quem) < 3:
        raise CarneLeaoError("Diga com quem a lista foi conferida (o contador).")
    texto = f"Conferida com {quem}, registrado por {_texto(por, 120)} em {quando[:10]}."
    _gravar(banco(con), {"carne_leao_lista_conferida": texto})
    return texto


# ------------------------------------------------------- a agenda do oficial

def obrigacao_da_agenda(con) -> dict | None:
    """A obrigação do carnê-leão no formato de `oficial_obrigacoes`, ou None
    enquanto o oficial não cadastrou a regra do prazo com a fonte. Só LÊ."""
    cfg = configuracao(con)
    regra, fonte = cfg["carne_leao_prazo_regra"], cfg["carne_leao_prazo_fonte"]
    if regra not in (ULTIMO_DIA_UTIL, DIA_DO_MES) or len(fonte) < MINIMO_DO_TEXTO:
        return None
    ob = {
        "codigo": "CARNE_LEAO",
        "titulo": "Carnê-leão: conferir o livro-caixa do mês anterior e pagar o DARF "
                  "(Carnê-Leão Web ou Sicalc)",
        "periodicidade": "MENSAL",
        "fundamento": "regra cadastrada pelo oficial em Administrativo → Carnê-leão",
        "fonte": fonte,
        "confirmada": True,
        "antecedencia_dias": 10,
        "nota": "O sistema apura receita, despesas dedutíveis e o imposto pela tabela "
                "cadastrada; o DARF não sai daqui.",
    }
    if regra == ULTIMO_DIA_UTIL:
        ob["ultimo_dia_util"] = True
    else:
        ob["dia"] = int(cfg["carne_leao_prazo_dia"] or 0)
    return ob


# ---------------------------------------------------------------- despesas

def _despesas_do_mes(con, comp: str) -> list[dict]:
    """As despesas do Livro Diário no mês, com a marcação vigente e a sugestão."""
    bd = banco(con)
    linhas = LD.despesas_do_mes(bd, comp)
    if not linhas:
        return []
    ids = [int(d["id"]) for d in linhas]
    marcas = {int(m["ld_despesa_id"]): m for m in bd.ler(
        """SELECT * FROM cl_marcacoes WHERE substituida_em IS NULL
              AND ld_despesa_id = ANY(%s) ORDER BY id""", (ids,))}
    categoria = {}
    if bd.tem_tabela("dp_despesas"):
        categoria = {int(r["ld_despesa_id"]): r["categoria"] for r in bd.ler(
            """SELECT ld_despesa_id, categoria FROM dp_despesas
                WHERE ld_despesa_id = ANY(%s) ORDER BY id""", (ids,))}
    saida = []
    for d in linhas:
        i = int(d["id"])
        sugerida = SUGESTAO_POR_CATEGORIA.get(categoria.get(i, ""), "")
        m = marcas.get(i)
        saida.append({
            "id": i, "dia": d["data"], "descricao": d["descricao"],
            "documento": " ".join(x for x in (d["documento_especie"],
                                              d["documento_numero"]) if x),
            "valor": int(d["valor"]), "origem": "Livro Diário",
            "categoria_despesa": categoria.get(i, ""),
            "sugerida": sugerida,
            "sugere_dedutivel": CATEGORIAS_FISCAIS.get(sugerida, ("", None))[1],
            "categoria_fiscal": m["categoria_fiscal"] if m else "",
            "dedutivel": (bool(int(m["dedutivel"])) if m else None),
            "marcado_por": m["marcado_por"] if m else "",
            "marcado_em": m["marcado_em"] if m else "",
        })
    return saida


def marcar_despesa(con, ld_despesa_id: int, *, categoria_fiscal: str, dedutivel: Any,
                   por: str, agora: str, observacao: Any = "") -> dict:
    """Marca a despesa do Livro Diário como dedutível ou não. ESCREVE.

    Remarcar guarda a anterior (`substituida_em`). Despesa anulada não se
    marca: ela não está mais no livro.
    """
    if categoria_fiscal not in CATEGORIAS_FISCAIS:
        raise CarneLeaoError("Escolha a categoria fiscal da despesa.")
    if str(dedutivel) not in ("0", "1"):
        raise CarneLeaoError("Diga se a despesa é dedutível ou não.")
    bd = banco(con)
    bd._escrita()
    d = bd.um("SELECT id, anulada_em FROM ld_despesas WHERE id = %s FOR UPDATE",
              (int(ld_despesa_id),))
    if not d:
        raise CarneLeaoError("Despesa não encontrada no Livro Diário.")
    if d["anulada_em"]:
        raise CarneLeaoError("Esta despesa foi anulada no Livro Diário e não conta.")
    bd.escrever("""UPDATE cl_marcacoes SET substituida_em = %s
                    WHERE ld_despesa_id = %s AND substituida_em IS NULL""",
                (agora, int(ld_despesa_id)))
    novo = bd.escrever(
        """INSERT INTO cl_marcacoes (ld_despesa_id, categoria_fiscal, dedutivel,
               observacao, marcado_em, marcado_por)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (int(ld_despesa_id), categoria_fiscal, int(str(dedutivel)),
         _texto(observacao, 500), agora, _texto(por, 120) or "?"))
    return {"id": int(novo[0]["id"]), "ld_despesa_id": int(ld_despesa_id)}


# ------------------------------------------------------------ os avulsos

def lancar_avulso(con, *, tipo: str, data: Any, descricao: Any, valor: Any,
                  documento: Any = "", categoria_fiscal: str = "", dedutivel: Any = "0",
                  hoje: str, agora: str, por: str) -> int:
    """O que entrou ou saiu fora do sistema, no livro-caixa do titular. ESCREVE."""
    if tipo not in ("RECEITA", "DESPESA"):
        raise CarneLeaoError("Escolha se é receita ou despesa.")
    descricao = _texto(descricao)
    if len(descricao) < MINIMO_DO_TEXTO:
        raise CarneLeaoError("Descreva o lançamento: o que entrou ou o que foi pago, "
                             "e a quem.")
    cent = _centavos_da_tela(valor)
    if cent <= 0:
        raise CarneLeaoError("Informe um valor maior que zero.")
    dedu = 0
    if tipo == "DESPESA":
        if categoria_fiscal not in CATEGORIAS_FISCAIS:
            raise CarneLeaoError("Escolha a categoria fiscal da despesa.")
        if str(dedutivel) not in ("0", "1"):
            raise CarneLeaoError("Diga se a despesa é dedutível ou não.")
        dedu = int(str(dedutivel))
    else:
        categoria_fiscal = ""
    novo = banco(con).escrever(
        """INSERT INTO cl_lancamentos (data, tipo, descricao, documento, valor,
               categoria_fiscal, dedutivel, lancado_em, lancado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (_data(data, hoje=hoje), tipo, descricao, _texto(documento, 120), cent,
         categoria_fiscal, dedu, agora, _texto(por, 120) or "?"))
    return int(novo[0]["id"])


def anular_avulso(con, lancamento_id: int, *, motivo: Any, por: str, agora: str) -> None:
    """Anula o lançamento avulso, com o motivo. A linha fica. ESCREVE."""
    motivo = _texto(motivo, 1000)
    if len(motivo) < MINIMO_DO_TEXTO:
        raise CarneLeaoError("Diga por que o lançamento está sendo anulado.")
    bd = banco(con)
    bd._escrita()
    linha = bd.um("SELECT id, anulado_em FROM cl_lancamentos WHERE id = %s FOR UPDATE",
                  (int(lancamento_id),))
    if not linha:
        raise CarneLeaoError("Lançamento não encontrado.")
    if linha["anulado_em"]:
        raise CarneLeaoError("Este lançamento já está anulado.")
    bd.escrever("""UPDATE cl_lancamentos SET anulado_em = %s, anulado_por = %s,
                          motivo_anulacao = %s WHERE id = %s""",
                (agora, _texto(por, 120) or "?", motivo, int(lancamento_id)))


def _avulsos_do_mes(bd, comp: str) -> list[dict]:
    inicio, fim = _limites(comp)
    return bd.ler("""SELECT * FROM cl_lancamentos WHERE data >= %s AND data < %s
                       AND anulado_em IS NULL ORDER BY data, id""", (inicio, fim))


# ------------------------------------------------- a tabela progressiva

def ler_faixas(texto: Any) -> list[dict]:
    """As faixas digitadas, uma por linha: «até; alíquota %; parcela a deduzir».

    A última linha tem o «até» vazio (acima da faixa anterior). Confere que os
    limites sobem e que só a última é aberta. Só calcula.
    """
    faixas = []
    for n, linha in enumerate(str(texto or "").splitlines(), start=1):
        if not linha.strip():
            continue
        partes = [p.strip() for p in linha.split(";")]
        if len(partes) != 3:
            raise CarneLeaoError(f"Linha {n}: use «até; alíquota; parcela a deduzir».")
        ate = _centavos_da_tela(partes[0]) if partes[0] else None
        faixas.append({"ate": ate, "aliquota_bp": _percentual_em_bp(partes[1]),
                       "deduzir": _centavos_da_tela(partes[2] or "0")})
    if not faixas:
        raise CarneLeaoError("Informe ao menos uma faixa.")
    for i, f in enumerate(faixas):
        ultima = i == len(faixas) - 1
        if f["ate"] is None and not ultima:
            raise CarneLeaoError(f"Faixa {i + 1}: só a última fica sem o «até».")
        if f["ate"] is not None and ultima:
            raise CarneLeaoError("A última faixa fica com o «até» vazio (acima da anterior).")
        if i and f["ate"] is not None and f["ate"] <= faixas[i - 1]["ate"]:
            raise CarneLeaoError(f"Faixa {i + 1}: o «até» tem de ser maior que o da anterior.")
    return faixas


def cadastrar_tabela(con, *, vigencia_inicio: Any, descricao: Any, fonte: Any,
                     faixas_texto: Any, por: str, agora: str) -> int:
    """Cadastra a tabela progressiva mensal com a vigência e a fonte. ESCREVE."""
    try:
        vigencia = date.fromisoformat(str(vigencia_inicio or "").strip()[:10]).isoformat()
    except ValueError as erro:
        raise CarneLeaoError("Informe o início da vigência (AAAA-MM-DD).") from erro
    descricao, fonte = _texto(descricao, 200), _texto(fonte, 500)
    if len(descricao) < 3:
        raise CarneLeaoError("Dê um nome à tabela.")
    if len(fonte) < MINIMO_DO_TEXTO:
        raise CarneLeaoError("Diga de onde vem a tabela (a norma e a data de publicação): "
                             "tabela sem fonte não calcula imposto de ninguém.")
    faixas = ler_faixas(faixas_texto)
    bd = banco(con)
    bd.travar("cl_tabelas.vigencia")
    if bd.um("SELECT id FROM cl_tabelas WHERE vigencia_inicio = %s AND anulada_em IS NULL",
             (vigencia,)):
        raise CarneLeaoError("Já há tabela com esta vigência. Anule a anterior, com o "
                             "motivo, antes de cadastrar outra no lugar dela.")
    novo = bd.escrever(
        """INSERT INTO cl_tabelas (vigencia_inicio, descricao, fonte, faixas,
               cadastrada_em, cadastrada_por)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (vigencia, descricao, fonte, json.dumps(faixas), agora, _texto(por, 120) or "?"))
    return int(novo[0]["id"])


def anular_tabela(con, tabela_id: int, *, motivo: Any, por: str, agora: str) -> None:
    """Anula a tabela cadastrada errada, com o motivo. A linha fica. ESCREVE."""
    motivo = _texto(motivo, 1000)
    if len(motivo) < MINIMO_DO_TEXTO:
        raise CarneLeaoError("Diga por que a tabela está sendo anulada.")
    bd = banco(con)
    bd._escrita()
    linha = bd.um("SELECT id, anulada_em FROM cl_tabelas WHERE id = %s FOR UPDATE",
                  (int(tabela_id),))
    if not linha or linha["anulada_em"]:
        raise CarneLeaoError("Tabela não encontrada, ou já anulada.")
    bd.escrever("""UPDATE cl_tabelas SET anulada_em = %s, anulada_por = %s,
                          motivo_anulacao = %s WHERE id = %s""",
                (agora, _texto(por, 120) or "?", motivo, int(tabela_id)))


def tabelas(con) -> list[dict]:
    """As tabelas cadastradas, a mais nova primeiro, com as faixas lidas. Só LÊ."""
    saida = []
    for t in banco(con).ler("SELECT * FROM cl_tabelas ORDER BY vigencia_inicio DESC, id DESC"):
        t["faixas"] = json.loads(t["faixas"])
        saida.append(t)
    return saida


def _tabela_do_mes(lista: list[dict], comp: str) -> tuple[dict | None, list[str]]:
    """A tabela vigente no 1º dia do mês, e o aviso quando outra começa no meio dele."""
    inicio, fim = _limites(comp)
    ativas = [t for t in lista if not t["anulada_em"]]
    vigente = next((t for t in ativas if t["vigencia_inicio"] <= inicio), None)
    avisos = [f"A tabela «{t['descricao']}» começa em {t['vigencia_inicio']}, no meio "
              f"do mês: a conta usou a vigente no dia 1º — a conferir com o contador."
              for t in ativas if inicio < t["vigencia_inicio"] < fim]
    return vigente, avisos


def calcular_imposto(base: int, faixas: list[dict]) -> dict:
    """O imposto da base pela tabela: base × alíquota − parcela a deduzir, nunca
    negativo, arredondado ao centavo (meio para cima). Só calcula."""
    base = max(0, int(base))
    for n, f in enumerate(faixas, start=1):
        if f["ate"] is None or base <= f["ate"]:
            bruto = (base * int(f["aliquota_bp"]) + 5000) // 10000
            return {"faixa": n, "aliquota_bp": int(f["aliquota_bp"]),
                    "deduzir": int(f["deduzir"]),
                    "imposto": max(0, bruto - int(f["deduzir"]))}
    raise CarneLeaoError("A tabela não tem faixa para esta base.")


# ---------------------------------------------------------------- receitas

_TROCO = ("SALDO INICIAL",)
_FUNDOS_DO_LANCAMENTO = ("ferc", "fadep", "femp", "ferrfis", "fermoju")


def _recebido_no_caixa(bd, comp: str) -> tuple[list[dict], list[dict]]:
    """Os recebimentos do caixa no mês (só o emolumento), e as «outras entradas»."""
    inicio, fim = _limites(comp)
    recebidos, outras = [], []
    for lan in bd.ler(
            """SELECT id, data, natureza, sentido, forma_pagamento, descricao, valor,
                      emolumentos, ferc, fadep, femp, ferrfis, fermoju, estornado,
                      COALESCE(excluido, 0) AS excluido
                 FROM cx_lancamentos WHERE data >= %s AND data < %s
                ORDER BY data, id""", (inicio, fim)):
        if int(lan["excluido"] or 0) or int(lan["estornado"] or 0) \
                or lan["sentido"] != "ENTRADA":
            continue
        valor = centavos(lan["valor"])
        if valor <= 0:
            continue                      # gratuidade: valor zero
        descricao = str(lan["descricao"] or "")
        if lan["natureza"] == "OUTRA_ENTRADA":
            outras.append({"dia": str(lan["data"])[:10], "descricao": descricao,
                           "valor": valor})
            continue
        if lan["natureza"] != "RECEBIMENTO" or any(t in descricao.upper() for t in _TROCO):
            continue                      # depósito (o livro dele conta), troco, saída
        if (lan["forma_pagamento"] or "").upper() == "DEPOSITO_PREVIO" \
                or descricao.startswith("Uso do depósito prévio"):
            continue                      # o dinheiro entrou antes, no depósito
        emol = centavos(lan["emolumentos"])
        fundos = sum(centavos(lan[f]) for f in _FUNDOS_DO_LANCAMENTO)
        if emol > 0:
            receita, discriminado = emol, True
        elif fundos > 0:
            receita, discriminado = max(0, valor - fundos), True
        else:
            receita, discriminado = valor, False
        recebidos.append({"dia": str(lan["data"])[:10], "bruto": valor,
                          "receita": receita, "discriminado": discriminado})
    return recebidos, outras


def _deposito_do_mes(livro: dict, comp: str) -> dict:
    """Depositado, convertido e devolvido no mês, pelo livro do depósito prévio."""
    recebido = convertido = devolvido = 0
    por_dia: dict[str, dict[str, int]] = {}
    for x in livro["linhas"]:
        if _no_mes(x["data"], comp):
            recebido += x["valor"]
            por_dia.setdefault(str(x["data"])[:10], {"recebido": 0, "convertido": 0,
                                                     "devolvido": 0})["recebido"] += x["valor"]
        for chave, movs in (("convertido", x["conversoes"]), ("devolvido", x["devolucoes"])):
            for m in movs:
                if _no_mes(m["data"], comp):
                    por_dia.setdefault(m["data"], {"recebido": 0, "convertido": 0,
                                                   "devolvido": 0})[chave] += m["valor"]
                    if chave == "convertido":
                        convertido += m["valor"]
                    else:
                        devolvido += m["valor"]
    return {"recebido": recebido, "convertido": convertido, "devolvido": devolvido,
            "por_dia": dict(sorted(por_dia.items()))}


def _livro_do_deposito(bd) -> dict:
    import livro_deposito_previo as LDP
    if not bd.tem_tabela("cx_depositos"):
        return {"linhas": []}
    return LDP.livro(bd)


# --------------------------------------------------------------- apuração

def _apurar(bd, comp: str, cfg: Mapping[str, str], livro_dep: dict,
            lista_tabelas: list[dict]) -> dict:
    modo = cfg.get("carne_leao_deposito_previo") or NO_USO
    recebidos, outras = _recebido_no_caixa(bd, comp)
    dep = _deposito_do_mes(livro_dep, comp)
    avulsos = _avulsos_do_mes(bd, comp)

    receitas: list[dict] = []
    por_dia: dict[str, dict] = {}
    for r in recebidos:
        dia = por_dia.setdefault(r["dia"], {"receita": 0, "bruto": 0, "n": 0,
                                            "sem_discriminacao": 0})
        dia["receita"] += r["receita"]
        dia["bruto"] += r["bruto"]
        dia["n"] += 1
        dia["sem_discriminacao"] += 0 if r["discriminado"] else r["receita"]
    for dia, v in sorted(por_dia.items()):
        receitas.append({"dia": dia, "origem": "Caixa",
                         "descricao": f"Emolumentos recebidos no caixa ({v['n']} lançamento(s))",
                         "valor": v["receita"], "sem_discriminacao": v["sem_discriminacao"]})
    chave_dep = "convertido" if modo == NO_USO else None
    for dia, v in dep["por_dia"].items():
        if chave_dep:
            valor = v["convertido"]
            texto = "Depósito prévio convertido em emolumentos (inclui fundos)"
        else:
            valor = v["recebido"] - v["devolvido"]
            texto = "Depósito prévio recebido, menos devoluções (inclui fundos)"
        if valor:
            receitas.append({"dia": dia, "origem": "Depósito prévio", "descricao": texto,
                             "valor": valor, "sem_discriminacao": valor})
    for a in avulsos:
        if a["tipo"] == "RECEITA":
            receitas.append({"dia": a["data"], "origem": "Avulso", "id": int(a["id"]),
                             "descricao": a["descricao"], "documento": a["documento"],
                             "valor": int(a["valor"]), "sem_discriminacao": 0})
    receitas.sort(key=lambda x: (x["dia"], x["origem"]))
    total_receita = sum(x["valor"] for x in receitas)

    despesas = _despesas_do_mes(bd, comp)
    for a in avulsos:
        if a["tipo"] == "DESPESA":
            despesas.append({"id": int(a["id"]), "dia": a["data"], "origem": "Avulso",
                             "descricao": a["descricao"], "documento": a["documento"],
                             "valor": int(a["valor"]), "categoria_fiscal": a["categoria_fiscal"],
                             "dedutivel": bool(int(a["dedutivel"])), "sugerida": "",
                             "sugere_dedutivel": None, "categoria_despesa": "",
                             "marcado_por": a["lancado_por"], "marcado_em": a["lancado_em"]})
    despesas.sort(key=lambda x: (x["dia"], x["origem"], x["id"]))
    dedutiveis = sum(d["valor"] for d in despesas if d["dedutivel"] is True)
    nao_dedutiveis = sum(d["valor"] for d in despesas if d["dedutivel"] is False)
    a_classificar = [d for d in despesas if d["dedutivel"] is None]

    selo = LD.apurar(bd, comp)
    base = max(0, total_receita - dedutiveis)
    tabela, avisos = _tabela_do_mes(lista_tabelas, comp)
    calculo = calcular_imposto(base, tabela["faixas"]) if tabela else None
    if a_classificar:
        avisos.append(f"{len(a_classificar)} despesa(s) do mês ainda sem marcação "
                      f"(R$ {reais(sum(d['valor'] for d in a_classificar))}): não foram "
                      f"deduzidas.")
    sem_disc = sum(x["sem_discriminacao"] for x in receitas)
    if sem_disc:
        avisos.append(f"R$ {reais(sem_disc)} da receita vieram sem a separação dos fundos "
                      f"e entraram inteiros como emolumento: conferir com o contador.")
    if outras:
        avisos.append(f"{len(outras)} «outra entrada» no caixa (R$ "
                      f"{reais(sum(o['valor'] for o in outras))}) ficou fora da conta: "
                      f"o contador diz se é receita.")
    if not tabela:
        avisos.append("Não há tabela progressiva cadastrada para este mês: o imposto não "
                      "foi calculado.")
    caixa = sum(r["receita"] for r in recebidos)
    deposito = sum(x["valor"] for x in receitas if x["origem"] == "Depósito prévio")
    return {
        "competencia": comp, "modo_deposito": modo,
        "receitas": receitas, "outras_entradas": outras,
        "caixa": caixa, "deposito_na_conta": deposito,
        "avulsas": sum(x["valor"] for x in receitas if x["origem"] == "Avulso"),
        "receita": total_receita, "sem_discriminacao": sem_disc,
        "deposito": {k: dep[k] for k in ("recebido", "convertido", "devolvido")},
        "selo": {"receita": int(selo["receita_bruta"]), "atos": selo["atos"],
                 "diferidos": selo["diferidos"], "isentos": selo["isentos"],
                 "sem_valor": selo["sem_valor"]},
        "despesas": despesas, "dedutiveis": dedutiveis, "nao_dedutiveis": nao_dedutiveis,
        "a_classificar": sum(d["valor"] for d in a_classificar),
        "base": base, "excesso": max(0, dedutiveis - total_receita),
        "tabela": ({"id": int(tabela["id"]), "descricao": tabela["descricao"],
                    "vigencia_inicio": tabela["vigencia_inicio"], "fonte": tabela["fonte"]}
                   if tabela else None),
        "calculo": calculo,
        "imposto": calculo["imposto"] if calculo else None,
        "avisos": avisos,
    }


def apurar(con, comp: Any) -> dict:
    """O livro-caixa do mês: receita no regime de caixa, despesas dedutíveis
    pagas, a base e o imposto pela tabela cadastrada. Só LÊ."""
    comp = competencia(comp)
    bd = banco(con)
    return _apurar(bd, comp, configuracao(bd), _livro_do_deposito(bd), tabelas(bd))


def resumo_do_ano(con, ano: int, *, ate: str) -> list[dict]:
    """Os meses do ano até `ate` (AAAA-MM), com os totais de cada um. Só LÊ.

    Lê o livro do depósito e as tabelas uma vez só, para os doze meses.
    """
    bd = banco(con)
    cfg, livro_dep, lista = configuracao(bd), _livro_do_deposito(bd), tabelas(bd)
    saida = []
    for mes in range(1, 13):
        comp = f"{int(ano):04d}-{mes:02d}"
        if comp > ate:
            break
        a = _apurar(bd, comp, cfg, livro_dep, lista)
        saida.append({"competencia": comp, "receita": a["receita"],
                      "selo": a["selo"]["receita"], "dedutiveis": a["dedutiveis"],
                      "a_classificar": a["a_classificar"], "base": a["base"],
                      "imposto": a["imposto"]})
    return saida


# --------------------------------------------------------------- exportação

def livro_caixa_csv(a: Mapping[str, Any]) -> str:
    """O livro-caixa do mês em CSV («;» e vírgula decimal), legível.

    NÃO é o leiaute de importação do Carnê-Leão Web (que falta nesta casa): as
    três primeiras linhas dizem isso, e as últimas trazem os totais.
    """
    def campo(x: Any) -> str:
        return " ".join(str(x if x is not None else "").replace(";", ",").split())

    linhas = [f"# Livro-caixa do titular — {a['competencia']} — regime de caixa",
              f"# {AVISO_DO_LEIAUTE}",
              f"# {AVISO_DA_LISTA}",
              "data;tipo;origem;descricao;documento;valor;dedutivel;categoria_fiscal;observacao"]
    for r in a["receitas"]:
        obs = "sem separação dos fundos" if r.get("sem_discriminacao") else ""
        linhas.append(";".join(campo(x) for x in (
            r["dia"], "RECEITA", r["origem"], r["descricao"], r.get("documento", ""),
            reais(r["valor"]).replace(".", ""), "", "", obs)))
    for d in a["despesas"]:
        marca = {True: "SIM", False: "NAO", None: "A CLASSIFICAR"}[d["dedutivel"]]
        rotulo = CATEGORIAS_FISCAIS.get(d["categoria_fiscal"], ("",))[0]
        linhas.append(";".join(campo(x) for x in (
            d["dia"], "DESPESA", d["origem"], d["descricao"], d["documento"],
            reais(d["valor"]).replace(".", ""), marca, rotulo, "")))
    imposto = "" if a["imposto"] is None else reais(a["imposto"]).replace(".", "")
    for rotulo, valor in (("TOTAL RECEITA", reais(a["receita"])),
                          ("TOTAL DESPESAS DEDUTIVEIS", reais(a["dedutiveis"])),
                          ("BASE", reais(a["base"])),
                          ("IMPOSTO PELA TABELA CADASTRADA", imposto or "sem tabela")):
        linhas.append(f"# {rotulo};{valor.replace('.', '') if valor[:1].isdigit() else valor}")
    return "\r\n".join(linhas) + "\r\n"
