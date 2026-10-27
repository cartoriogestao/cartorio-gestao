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
    - a TABELA PROGRESSIVA é nacional, e por ordem do oficial (26/10/2026,
      «pegue a tabela progressiva na internet, é nacional») o sistema a traz
      pronta em `TABELAS_NACIONAIS`, lida na página da Receita Federal em
      26/10/2026. Ela entra com um clique na configuração, com a vigência e a
      fonte, e se anula como qualquer outra. Sem tabela cadastrada não há
      imposto calculado — e a tela diz isso em vez de mostrar zero;
    - o PRAZO é o último dia (útil) do mês seguinte ao do recebimento, decisão
      do oficial em 26/10/2026, e já vem na configuração;
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
      lançá-lo «como receita» quando o ato é praticado, e é assim que esta
      conta o trata (`NO_USO`): decisão do oficial em 26/10/2026, «depósito só
      vira receita quando pratica o ato». A opção de contá-lo no recebimento
      saiu; o recebido, o convertido e o devolvido continuam à vista.
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
      06/10/2026) —, a parte dos fundos sai da CONFIGURAÇÃO DO DELEGATÁRIO
      (percentual e forma de cálculo; o padrão é a soma dos fundos cobrados em
      `custas.PERCENTUAIS`, sobre o emolumento). Ordem do oficial em
      26/10/2026: «precisa tirar a parte dos fundos, mas a configuração da
      retirada varia conforme configuração do delegatário». A linha fica
      marcada «sem discriminação», com os fundos estimados à vista.
    - Depósito prévio: o Livro de Controle de Depósito Prévio
      (`livro_deposito_previo.livro`) — depósitos do mês, conversões e
      devoluções pelas datas do rastro. O valor convertido inclui os fundos; a
      parte deles sai pela mesma configuração.
    - «Outra entrada» do caixa: quem a lança responde, no caixa, se ela é
      receita do titular (ordem do oficial, 26/10/2026: «pergunta pra quem
      cadastra dizer se é ou não»). «Sim» entra inteira; «não» fica fora; a
      antiga, sem resposta, aparece à parte para o ADMIN responder.
    - Lançamento avulso do livro-caixa (`cl_lancamentos`): o que entrou ou saiu
      fora do sistema (ressarcimento de gratuidade, despesa paga do bolso),
      lançado pelo oficial com documento.
    - Despesas: as do Livro Diário (`ld_despesas`, no dia do pagamento), que já
      incluem as do módulo de despesas conferidas no extrato. A GUIA DE FUNDO
      NÃO É DESPESA (decisão do oficial, 24/10/2026) e não chega aqui — fundo
      não é receita, e repassá-lo não é gasto do titular.

O EXCESSO DE DESPESA VAI PARA O MÊS SEGUINTE, ATÉ DEZEMBRO
    Decisão do oficial em 26/10/2026. Quando as despesas dedutíveis passam da
    receita, a base do mês é zero e o excesso se soma às deduções do mês
    seguinte (Lei 8.134/1990, art. 6º, § 3º: «até dezembro»). Em janeiro a
    conta recomeça: o que sobrar em dezembro não passa para o ano seguinte.

PostgreSQL nativo, pelo `bd_nativo`. Dinheiro em centavos, `bigint`. Data e
hora se calculam no Python (regra da casa).
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date
from typing import Any

import custas
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

AVISO_DA_LISTA = ("A lista de categorias dedutíveis foi aprovada pelo oficial em "
                  "26/10/2026 («parece estar certa»); a marcação continua sendo "
                  "despesa por despesa, e a conferência com o contador pode ser "
                  "registrada na configuração.")

AVISO_DO_LEIAUTE = ("O leiaute de importação do Carnê-Leão Web não está nesta casa "
                    "(procurado em FONTES_EXTERNAS/ e docs/ em 26/10/2026). Este arquivo "
                    "é uma planilha legível para lançar à mão ou entregar ao contador. "
                    "O DARF sai pelo Carnê-Leão Web ou pelo Sicalc — não por aqui.")

# --------------------------------------------------------- a configuração

NO_USO = "NO_USO"
MODOS_DO_DEPOSITO = {
    NO_USO: "No mês em que o ato é praticado e o depósito é convertido (decisão do "
            "oficial em 26/10/2026; CN-MA art. 202)",
}

ULTIMO_DIA_UTIL, DIA_DO_MES = "ULTIMO_DIA_UTIL", "DIA_DO_MES"
REGRAS_DO_PRAZO = {
    "": "Não cadastrado — o carnê-leão continua como pergunta na agenda",
    ULTIMO_DIA_UTIL: "Último dia útil do mês seguinte ao do recebimento",
    DIA_DO_MES: "Um dia fixo do mês seguinte ao do recebimento",
}

FONTE_DO_PRAZO = ("Decisão do oficial em 26/10/2026: o carnê-leão vence no último dia do "
                  "mês seguinte ao do recebimento (o DARF vence no último dia ÚTIL).")

# A PARTE DOS FUNDOS NO LANÇAMENTO SEM SEPARAÇÃO — configuração do delegatário
# (26/10/2026). Sobre o emolumento: valor = emolumento × (1 + percentual). Dentro
# do valor: fundos = valor × percentual.
FUNDOS_SOBRE_O_EMOLUMENTO, FUNDOS_DENTRO_DO_VALOR = "SOBRE_O_EMOLUMENTO", "DENTRO_DO_VALOR"
FORMAS_DOS_FUNDOS = {
    FUNDOS_SOBRE_O_EMOLUMENTO: "Os fundos são calculados sobre o emolumento (o valor "
                               "recebido é o emolumento mais o percentual)",
    FUNDOS_DENTRO_DO_VALOR: "Os fundos são um percentual do valor recebido",
}


def _percentual_padrao_dos_fundos() -> str:
    """A soma dos fundos COBRADOS da tabela da casa (o ISS fica: é tributo do
    titular, e entra como despesa quando pago)."""
    bp = sum(int(custas.PERCENTUAIS.get(c, 0)) * 100 for c in custas.CAMPOS_NO_TOTAL)
    inteiro, resto = divmod(bp, 100)
    return f"{inteiro}" + (f",{resto:02d}".rstrip("0") if resto else "")


PADRAO: dict[str, str] = {
    "carne_leao_prazo_regra": "ULTIMO_DIA_UTIL",
    "carne_leao_prazo_dia": "",
    "carne_leao_prazo_fonte": FONTE_DO_PRAZO,
    "carne_leao_lista_conferida": "",
    "carne_leao_fundos_forma": FUNDOS_SOBRE_O_EMOLUMENTO,
    "carne_leao_fundos_percentual": _percentual_padrao_dos_fundos(),
}

# A TABELA NACIONAL, lida em 26/10/2026 na página da Receita Federal
# (gov.br/receitafederal → Meu Imposto de Renda → Tabelas → 2026). As faixas
# são as da MP 1.294/2025, convertida na Lei 15.191/2025 (desde maio de 2025);
# a de 2026 traz a REDUÇÃO MENSAL da Lei 15.270/2025: até R$ 312,89 para
# rendimentos até R$ 5.000,00, e R$ 978,62 − 0,133145 × rendimentos entre
# R$ 5.000,01 e R$ 7.350,00 — sempre limitada ao imposto da tabela.
_FAIXAS_DESDE_MAIO_2025 = (
    {"ate": 242880, "aliquota_bp": 0, "deduzir": 0},
    {"ate": 282665, "aliquota_bp": 750, "deduzir": 18216},
    {"ate": 375105, "aliquota_bp": 1500, "deduzir": 39416},
    {"ate": 466468, "aliquota_bp": 2250, "deduzir": 67549},
    {"ate": None, "aliquota_bp": 2750, "deduzir": 90873},
)
REDUCAO_LEI_15270 = {"isento_ate": 500000, "reducao_maxima": 31289, "teto": 735000,
                     "constante": 97862, "coeficiente_milionesimos": 133145}
_PAGINA_DA_RECEITA = ("tabela publicada pela Receita Federal em gov.br/receitafederal "
                      "(Meu Imposto de Renda → Tabelas), lida em 26/10/2026")
TABELAS_NACIONAIS: tuple[dict, ...] = (
    {"vigencia_inicio": "2025-05-01",
     "descricao": "Tabela progressiva mensal — MP 1.294/2025 e Lei 15.191/2025",
     "fonte": f"MP nº 1.294/2025, convertida na Lei nº 15.191, de 11/08/2025; {_PAGINA_DA_RECEITA}",
     "faixas": _FAIXAS_DESDE_MAIO_2025, "reducao": None},
    {"vigencia_inicio": "2026-01-01",
     "descricao": "Tabela progressiva mensal de 2026, com a redução da Lei 15.270/2025",
     "fonte": (f"Lei nº 15.191, de 11/08/2025 (faixas) e Lei nº 15.270, de 26/11/2025 "
               f"(redução mensal); {_PAGINA_DA_RECEITA}"),
     "faixas": _FAIXAS_DESDE_MAIO_2025, "reducao": REDUCAO_LEI_15270},
)

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
    """A regra do prazo e a parte dos fundos. ESCREVE. Devolve o que mudou.

    Chave que não veio continua como está. O PRAZO SÓ ENTRA COM A FONTE:
    «último dia útil do mês seguinte» sem dizer onde se leu seria o prazo
    escrito de memória que a agenda recusa.
    """
    bd = banco(con)
    antes = configuracao(bd)

    def valor(chave: str) -> str:
        return str(valores[chave]) if valores.get(chave) is not None else antes[chave]

    regra = valor("carne_leao_prazo_regra")
    if regra not in REGRAS_DO_PRAZO:
        raise CarneLeaoError("Regra de prazo desconhecida.")
    dia, fonte = "", _texto(valor("carne_leao_prazo_fonte"), 500)
    if regra == DIA_DO_MES:
        texto = valor("carne_leao_prazo_dia").strip()
        if not texto.isascii() or not texto.isdigit() or not 1 <= int(texto) <= 31:
            raise CarneLeaoError("Informe o dia do mês do prazo (1 a 31).")
        dia = str(int(texto))
    if regra and len(fonte) < MINIMO_DO_TEXTO:
        raise CarneLeaoError(
            "Diga de onde vem a regra do prazo (a norma da Receita, ou a orientação "
            "escrita do contador): prazo sem fonte não entra na agenda do oficial.")
    forma = valor("carne_leao_fundos_forma")
    if forma not in FORMAS_DOS_FUNDOS:
        raise CarneLeaoError("Escolha como os fundos são calculados no lançamento sem "
                             "separação.")
    bp = _percentual_em_bp(valor("carne_leao_fundos_percentual"))
    if bp >= 10000:
        raise CarneLeaoError("O percentual dos fundos tem de ser menor que 100%.")
    novo = {"carne_leao_prazo_regra": regra, "carne_leao_prazo_dia": dia,
            "carne_leao_prazo_fonte": fonte if regra else "",
            "carne_leao_fundos_forma": forma, "carne_leao_fundos_percentual": percentual(bp)}
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


def cadastrar_tabelas_nacionais(con, *, por: str, agora: str) -> list[str]:
    """Cadastra as `TABELAS_NACIONAIS` que faltam. ESCREVE. Devolve o que fez.

    Vigência que já tem tabela ativa não é tocada: quem a cadastrou à mão
    decide, anulando-a, se quer a nacional no lugar.
    """
    bd = banco(con)
    bd.travar("cl_tabelas.vigencia")
    feito = []
    for t in TABELAS_NACIONAIS:
        if bd.um("SELECT id FROM cl_tabelas WHERE vigencia_inicio = %s AND anulada_em IS NULL",
                 (t["vigencia_inicio"],)):
            feito.append(f"{t['vigencia_inicio']}: já havia tabela ativa — não mexi.")
            continue
        faixas = [dict(f) for f in t["faixas"]]
        guardar = {"faixas": faixas, "reducao": dict(t["reducao"])} if t["reducao"] else faixas
        bd.escrever(
            """INSERT INTO cl_tabelas (vigencia_inicio, descricao, fonte, faixas,
                   cadastrada_em, cadastrada_por) VALUES (%s, %s, %s, %s, %s, %s)""",
            (t["vigencia_inicio"], t["descricao"], t["fonte"], json.dumps(guardar), agora,
             _texto(por, 120) or "?"))
        feito.append(f"{t['vigencia_inicio']}: «{t['descricao']}» cadastrada.")
    return feito


def tabelas(con) -> list[dict]:
    """As tabelas cadastradas, a mais nova primeiro, com as faixas lidas. Só LÊ.

    A coluna `faixas` guarda a lista das faixas ou, quando a tabela tem a
    redução da Lei 15.270/2025, `{"faixas": [...], "reducao": {...}}`.
    """
    saida = []
    for t in banco(con).ler("SELECT * FROM cl_tabelas ORDER BY vigencia_inicio DESC, id DESC"):
        bruto = json.loads(t["faixas"])
        if isinstance(bruto, dict):
            t["faixas"], t["reducao"] = bruto["faixas"], bruto.get("reducao")
        else:
            t["faixas"], t["reducao"] = bruto, None
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


def reducao_mensal(rendimentos: int, imposto: int, regra: Mapping[str, Any] | None) -> int:
    """A redução da Lei 15.270/2025 sobre o imposto da tabela. Só calcula.

    Até `isento_ate`, até `reducao_maxima`; até `teto`, `constante` menos
    `coeficiente` × rendimentos; acima, nada. Nunca passa do imposto.
    OS RENDIMENTOS SÃO A RECEITA DO MÊS, antes das despesas do livro-caixa: é
    a leitura literal de «rendimentos tributáveis sujeitos à incidência
    mensal» — a conferir com o contador (a tela avisa).
    """
    if not regra or imposto <= 0:
        return 0
    rend = max(0, int(rendimentos))
    if rend <= int(regra["isento_ate"]):
        valor = int(regra["reducao_maxima"])
    elif rend <= int(regra["teto"]):
        valor = int(regra["constante"]) - (
            rend * int(regra["coeficiente_milionesimos"]) + 500000) // 1000000
    else:
        valor = 0
    return max(0, min(int(imposto), valor))


def tirar_os_fundos(valor: int, forma: str, bp: int) -> int:
    """O emolumento contido no `valor` de um lançamento sem a separação dos
    fundos, pela configuração do delegatário. Só calcula."""
    valor = max(0, int(valor))
    if bp <= 0:
        return valor
    if forma == FUNDOS_DENTRO_DO_VALOR:
        return valor - (valor * bp + 5000) // 10000
    return (valor * 10000 + (10000 + bp) // 2) // (10000 + bp)


def _fundos_da_configuracao(cfg: Mapping[str, str]) -> tuple[str, int]:
    forma = cfg.get("carne_leao_fundos_forma") or FUNDOS_SOBRE_O_EMOLUMENTO
    try:
        bp = _percentual_em_bp(cfg.get("carne_leao_fundos_percentual") or "0")
    except CarneLeaoError:
        bp = 0
    return forma, min(bp, 9999)


# ------------------------------------------------- a outra entrada do caixa

def marcar_outra_entrada(con, lancamento_id: int, *, receita: Any) -> None:
    """Responde, pelo ADMIN, se a «outra entrada» antiga é receita do titular.
    ESCREVE. As novas já nascem com a resposta de quem as lançou no caixa."""
    if str(receita) not in ("0", "1"):
        raise CarneLeaoError("Diga se esta entrada é receita do titular ou não.")
    bd = banco(con)
    bd._escrita()
    lan = bd.um("SELECT id, natureza FROM cx_lancamentos WHERE id = %s FOR UPDATE",
                (int(lancamento_id),))
    if not lan or lan["natureza"] != "OUTRA_ENTRADA":
        raise CarneLeaoError("Lançamento não encontrado, ou não é «outra entrada».")
    bd.escrever("UPDATE cx_lancamentos SET receita_do_titular = %s WHERE id = %s",
                (int(str(receita)), int(lancamento_id)))


# ---------------------------------------------------------------- receitas

_TROCO = ("SALDO INICIAL",)
_FUNDOS_DO_LANCAMENTO = ("ferc", "fadep", "femp", "ferrfis", "fermoju")


def _recebido_no_caixa(bd, comp: str, forma: str, bp: int
                       ) -> tuple[list[dict], list[dict], list[dict]]:
    """Os recebimentos do caixa no mês (só o emolumento), as «outras entradas»
    que quem lançou disse serem receita do titular, e as sem resposta."""
    inicio, fim = _limites(comp)
    recebidos, outras, outras_receitas = [], [], []
    resposta = ("receita_do_titular" if bd.tem_coluna("cx_lancamentos", "receita_do_titular")
                else "NULL AS receita_do_titular")
    for lan in bd.ler(
            f"""SELECT id, data, natureza, sentido, forma_pagamento, descricao, valor,
                      emolumentos, ferc, fadep, femp, ferrfis, fermoju, estornado,
                      COALESCE(excluido, 0) AS excluido, {resposta}
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
            item = {"id": int(lan["id"]), "dia": str(lan["data"])[:10],
                    "descricao": descricao, "valor": valor}
            if lan["receita_do_titular"] is None:
                outras.append(item)
            elif int(lan["receita_do_titular"]):
                outras_receitas.append(item)
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
            receita, discriminado = tirar_os_fundos(valor, forma, bp), False
        recebidos.append({"dia": str(lan["data"])[:10], "bruto": valor,
                          "receita": receita, "discriminado": discriminado})
    return recebidos, outras, outras_receitas


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
            lista_tabelas: list[dict], excesso_anterior: int = 0) -> dict:
    modo = NO_USO
    forma, bp = _fundos_da_configuracao(cfg)
    recebidos, outras, outras_receitas = _recebido_no_caixa(bd, comp, forma, bp)
    dep = _deposito_do_mes(livro_dep, comp)
    avulsos = _avulsos_do_mes(bd, comp)

    receitas: list[dict] = []
    por_dia: dict[str, dict] = {}
    for r in recebidos:
        dia = por_dia.setdefault(r["dia"], {"receita": 0, "bruto": 0, "n": 0,
                                            "sem_discriminacao": 0, "fundos_estimados": 0})
        dia["receita"] += r["receita"]
        dia["bruto"] += r["bruto"]
        dia["n"] += 1
        if not r["discriminado"]:
            dia["sem_discriminacao"] += r["bruto"]
            dia["fundos_estimados"] += r["bruto"] - r["receita"]
    for dia, v in sorted(por_dia.items()):
        receitas.append({"dia": dia, "origem": "Caixa",
                         "descricao": f"Emolumentos recebidos no caixa ({v['n']} lançamento(s))",
                         "valor": v["receita"], "sem_discriminacao": v["sem_discriminacao"],
                         "fundos_estimados": v["fundos_estimados"]})
    for o in outras_receitas:
        receitas.append({"dia": o["dia"], "origem": "Outra entrada",
                         "descricao": o["descricao"] or "Outra entrada do caixa",
                         "valor": o["valor"], "sem_discriminacao": 0, "fundos_estimados": 0})
    for dia, v in dep["por_dia"].items():
        bruto = v["convertido"]
        if bruto:
            valor = tirar_os_fundos(bruto, forma, bp)
            receitas.append({"dia": dia, "origem": "Depósito prévio",
                             "descricao": "Depósito prévio convertido em emolumentos",
                             "valor": valor, "sem_discriminacao": bruto,
                             "fundos_estimados": bruto - valor})
    for a in avulsos:
        if a["tipo"] == "RECEITA":
            receitas.append({"dia": a["data"], "origem": "Avulso", "id": int(a["id"]),
                             "descricao": a["descricao"], "documento": a["documento"],
                             "valor": int(a["valor"]), "sem_discriminacao": 0,
                             "fundos_estimados": 0})
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
    deducoes = dedutiveis + int(excesso_anterior)
    base = max(0, total_receita - deducoes)
    tabela, avisos = _tabela_do_mes(lista_tabelas, comp)
    calculo = calcular_imposto(base, tabela["faixas"]) if tabela else None
    if calculo:
        calculo["imposto_da_tabela"] = calculo["imposto"]
        calculo["reducao"] = reducao_mensal(total_receita, calculo["imposto"],
                                            tabela.get("reducao"))
        calculo["imposto"] -= calculo["reducao"]
        if tabela.get("reducao") and total_receita <= int(tabela["reducao"]["teto"]):
            avisos.append("A redução da Lei 15.270/2025 foi calculada sobre a receita do mês, "
                          "antes das despesas do livro-caixa — a conferir com o contador.")
    if a_classificar:
        avisos.append(f"{len(a_classificar)} despesa(s) do mês ainda sem marcação "
                      f"(R$ {reais(sum(d['valor'] for d in a_classificar))}): não foram "
                      f"deduzidas.")
    sem_disc = sum(x["sem_discriminacao"] for x in receitas)
    fundos_est = sum(x["fundos_estimados"] for x in receitas)
    if sem_disc:
        avisos.append(f"R$ {reais(sem_disc)} da receita vieram sem a separação dos fundos: "
                      f"R$ {reais(fundos_est)} saíram como fundos pela configuração "
                      f"({percentual(bp)}%, {FORMAS_DOS_FUNDOS[forma].lower()}).")
    if outras:
        avisos.append(f"{len(outras)} «outra entrada» no caixa (R$ "
                      f"{reais(sum(o['valor'] for o in outras))}) sem a resposta de quem a "
                      f"lançou: ficou fora da conta até alguém dizer se é receita do titular.")
    if excesso_anterior:
        avisos.append(f"R$ {reais(int(excesso_anterior))} de despesas que passaram da receita "
                      f"nos meses anteriores do ano foram somados às deduções deste mês.")
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
        "fundos_estimados": fundos_est,
        "fundos": {"forma": forma, "percentual": percentual(bp)},
        "deposito": {k: dep[k] for k in ("recebido", "convertido", "devolvido")},
        "selo": {"receita": int(selo["receita_bruta"]), "atos": selo["atos"],
                 "diferidos": selo["diferidos"], "isentos": selo["isentos"],
                 "sem_valor": selo["sem_valor"]},
        "despesas": despesas, "dedutiveis": dedutiveis, "nao_dedutiveis": nao_dedutiveis,
        "a_classificar": sum(d["valor"] for d in a_classificar),
        "excesso_anterior": int(excesso_anterior),
        "base": base, "excesso": max(0, deducoes - total_receita),
        "tabela": ({"id": int(tabela["id"]), "descricao": tabela["descricao"],
                    "vigencia_inicio": tabela["vigencia_inicio"], "fonte": tabela["fonte"]}
                   if tabela else None),
        "calculo": calculo,
        "imposto": calculo["imposto"] if calculo else None,
        "avisos": avisos,
    }


def _meses_do_ano(bd, ano: int, ate: str) -> list[dict]:
    """Janeiro até `ate` (AAAA-MM), levando o excesso de despesa de um mês para o
    seguinte. Lê o livro do depósito e as tabelas uma vez só."""
    cfg, livro_dep, lista = configuracao(bd), _livro_do_deposito(bd), tabelas(bd)
    saida, excesso = [], 0
    for mes in range(1, 13):
        comp = f"{int(ano):04d}-{mes:02d}"
        if comp > ate:
            break
        a = _apurar(bd, comp, cfg, livro_dep, lista, excesso_anterior=excesso)
        excesso = a["excesso"]
        saida.append(a)
    return saida


def _resumo(a: Mapping[str, Any]) -> dict:
    return {"competencia": a["competencia"], "receita": a["receita"],
            "selo": a["selo"]["receita"], "dedutiveis": a["dedutiveis"],
            "excesso_anterior": a["excesso_anterior"], "a_classificar": a["a_classificar"],
            "base": a["base"], "excesso": a["excesso"], "imposto": a["imposto"]}


def apurar(con, comp: Any) -> dict:
    """O livro-caixa do mês: receita no regime de caixa, despesas dedutíveis
    pagas (mais o excesso que veio dos meses anteriores do ano), a base e o
    imposto pela tabela cadastrada. Só LÊ."""
    comp = competencia(comp)
    return _meses_do_ano(banco(con), int(comp[:4]), comp)[-1]


def apurar_com_o_ano(con, comp: Any, *, ate: str) -> tuple[dict, list[dict]]:
    """O mês e o resumo do ano numa passada só — é o que a tela pede. Só LÊ."""
    comp = competencia(comp)
    meses = _meses_do_ano(banco(con), int(comp[:4]), max(comp, ate))
    mes = next(a for a in meses if a["competencia"] == comp)
    return mes, [_resumo(a) for a in meses]


# --------------------------------------------------------------- exportação

def livro_caixa_linhas(a: Mapping[str, Any]) -> list[list[str]]:
    """O livro-caixa do mês, linha a linha, para o CSV («;» e vírgula decimal).

    NÃO é o leiaute de importação do Carnê-Leão Web (que falta nesta casa): as
    três primeiras linhas dizem isso, e as últimas trazem os totais. A tela
    entrega pelo `csv_seguro` (tudo entre aspas, fórmula desarmada): o «;»
    dentro do campo já não precisa virar vírgula.
    """
    def campo(x: Any) -> str:
        return " ".join(str(x if x is not None else "").split())

    linhas = [[f"# Livro-caixa do titular — {a['competencia']} — regime de caixa"],
              [f"# {AVISO_DO_LEIAUTE}"],
              [f"# {AVISO_DA_LISTA}"],
              ["data", "tipo", "origem", "descricao", "documento", "valor", "dedutivel",
               "categoria_fiscal", "observacao"]]
    for r in a["receitas"]:
        obs = (f"sem separação dos fundos; R$ {reais(r['fundos_estimados'])} de fundos "
               f"tirados pela configuração" if r.get("sem_discriminacao") else "")
        linhas.append([campo(x) for x in (
            r["dia"], "RECEITA", r["origem"], r["descricao"], r.get("documento", ""),
            reais(r["valor"]).replace(".", ""), "", "", obs)])
    for d in a["despesas"]:
        marca = {True: "SIM", False: "NAO", None: "A CLASSIFICAR"}[d["dedutivel"]]
        rotulo = CATEGORIAS_FISCAIS.get(d["categoria_fiscal"], ("",))[0]
        linhas.append([campo(x) for x in (
            d["dia"], "DESPESA", d["origem"], d["descricao"], d["documento"],
            reais(d["valor"]).replace(".", ""), marca, rotulo, "")])
    imposto = "" if a["imposto"] is None else reais(a["imposto"]).replace(".", "")
    for rotulo, valor in (("TOTAL RECEITA", reais(a["receita"])),
                          ("TOTAL DESPESAS DEDUTIVEIS", reais(a["dedutiveis"])),
                          ("EXCESSO DOS MESES ANTERIORES", reais(a["excesso_anterior"])),
                          ("BASE", reais(a["base"])),
                          ("IMPOSTO PELA TABELA CADASTRADA", imposto or "sem tabela")):
        linhas.append([f"# {rotulo}", valor.replace(".", "") if valor[:1].isdigit() else valor])
    return linhas
