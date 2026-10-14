"""
Sugerir a natureza da escritura a partir do que ela diz de si mesma.

O PROBLEMA
    As 45 escrituras do acervo vieram do E-Oficio com um unico modelo generico
    chamado "Escritura", que aponta para a natureza 1 — ACORDO EXTRAJUDICIAL.
    Nenhuma delas e acordo extrajudicial. Mandar as 45 assim para a CEP seria
    declarar errado 45 vezes a uma central nacional.

    Classificar a mao, uma a uma, e trabalho do tabeliao. Este modulo nao tira
    esse trabalho dele: torna-o rapido.

DE ONDE VEM A SUGESTAO
    Do proprio teor. Toda escritura da serventia comeca se apresentando:

        REPUBLICA FEDERATIVA DO BRASIL ... LIVRO n°027 (Notas) FLS.182
        ESCRITURA PUBLICA DE COMPRA E VENDA, tendo como OUTORGANTE VENDEDOR...

    O titulo esta ali, escrito pelo proprio escrevente. Ler o que o ato diz e
    melhor do que adivinhar pelo modelo que o sistema antigo usava.

    So foi possivel depois de consertar o `rtf_para_texto`: antes, os primeiros
    dezenove mil caracteres do teor eram tabela de fontes e imagem em
    hexadecimal, e o titulo ficava soterrado.

O QUE ESTE MODULO NAO FAZ
    Nao grava nada, nao decide nada e nao classifica sozinho. Devolve a
    sugestao COM A EVIDENCIA — o trecho do teor que a produziu — para o
    registrador confirmar ou recusar olhando a mesma coisa que o sistema olhou.

    Sem evidencia, sugestao vira palpite com cara de autoridade, e ninguem
    confere o que parece seguro.
"""
from __future__ import annotations

import re
import unicodedata

# ------------------------------------------------------- pistas do titulo

# (padrao no titulo, natureza da CEP, o que ela contempla no dominio oficial)
#
# A ordem importa: a primeira que casar vence. As mais especificas vem antes —
# "COMPRA E VENDA DE IMOVEL RURAL" tem de casar antes de "COMPRA E VENDA", e
# "PROMESSA DE COMPRA E VENDA" antes das duas.
# OS PADROES SAO ESCRITOS SEM ACENTO E EM CAIXA ALTA, DE PROPOSITO.
#
# A primeira versao guardava os padroes com acento e os normalizava na hora de
# usar — `_sem_acento(padrao).upper()`. Isso transformava `\b` em `\B`, que e a
# asserção OPOSTA: todo padrao com limite de palavra parou de casar, calado.
# "doação" nao virava natureza 22 e ninguem sabia por que.
#
# Normalizar o ALVO e barato e seguro. Normalizar o PADRAO mexe na sintaxe da
# propria expressao.
PISTAS_CEP: tuple[tuple[str, int, str], ...] = (
    (r"PROMESSA DE COMPRA E VENDA", 80, "Promessa de compra e venda"),
    (r"PROMESSA DE CESSAO", 33, "Promessa de cessão de direitos aquisitivos"),
    (r"COMPRA E VENDA|VENDA E COMPRA", 6, "Compra e venda"),
    (r"\bPERMUTA\b", 6, "Compra e venda — a tabela contempla permuta"),
    (r"DESMEMBRAMENTO|DESDOBRO|ESTREMACAO|DIVISAO AMIGAVEL",
     53, "Divisão — contempla desdobro e estremação"),
    (r"RECONHECIMENTO DE PATERNIDADE|PERFILHACAO",
     36, "Reconhecimento de paternidade"),
    (r"DOACAO EM ADIANTAMENTO|ADIANTAMENTO DA LEGITIMA", 22, "Doação"),
    (r"\bDOACAO\b", 22, "Doação"),
    (r"CESSAO DE DIREITOS HEREDITARIOS", 5, "Cessão"),
    (r"CESSAO DE DIREITOS", 5, "Cessão"),
    (r"RENUNCIA DE DIREITOS HEREDITARIOS", 62,
     "Renúncia de direitos hereditários"),
    (r"USUFRUTO", 46, "Usufruto — reserva, instituição e renúncia"),
    (r"SERVIDAO", 45, "Servidão"),
    (r"HIPOTECA", 24, "Hipoteca"),
    (r"ALIENACAO FIDUCIARIA", 4, "Alienação fiduciária"),
    (r"CONFISSAO DE DIVIDA|DACAO EM PAGAMENTO", 10,
     "Confissão de dívida ou dação em pagamento"),
    (r"\bQUITACAO\b", 34, "Quitação"),
    (r"\bDISTRATO\b", 21, "Distrato"),
    (r"PACTO ANTENUPCIAL", 30, "Pacto antenupcial"),
    (r"EMANCIPACAO", 23, "Emancipação"),
    (r"UNIAO ESTAVEL HOMOAFETIVA", 16,
     "Declaratória de união estável homoafetiva"),
    (r"DISSOLUCAO DE UNIAO ESTAVEL|EXTINCAO DE UNIAO ESTAVEL",
     20, "Dissolução de união estável"),
    (r"UNIAO ESTAVEL", 15, "Declaratória de união estável"),
    (r"DIRETIVAS ANTECIPADAS", 55, "Diretivas antecipadas de vontade"),
    (r"AUTOCURATELA", 78, "Autocuratela"),
    (r"RERRATIFICACAO|RETIFICACAO E RATIFICACAO", 35,
     "Rerratificação"),
    (r"BEM DE FAMILIA", 26, "Bem de família"),
    (r"COMODATO|MUTUO", 63, "Comodato ou mútuo"),
    (r"SEM VALOR DECLARADO|SEM CONTEUDO FINANCEIRO", 43, "Sem valor declarado"),
)

# Titulos que NAO sao natureza de escritura: sao outro tipo de ato da CEP, ou
# ato de outra central. Sugerir natureza para eles seria classificar errado com
# ar de acerto.
PISTAS_OUTRO_ATO: tuple[tuple[str, str, str], ...] = (
    (r"REVOGACAO DE MANDATO|REVOGACAO DE PROCURACAO",
     "REVOGACAO_PROCURACAO",
     "não é escritura: é revogação de mandato, tipo 6 da CEP"),
    (r"RENUNCIA DE MANDATO|RENUNCIA DE PROCURACAO",
     "RENUNCIA_PROCURACAO",
     "não é escritura: é renúncia de mandato, tipo 5 da CEP"),
    (r"SUBSTABELECIMENTO", "SUBSTABELECIMENTO",
     "não é escritura: é substabelecimento, tipo 7 da CEP"),
    (r"\bPROCURACAO\b", "PROCURACAO",
     "não é escritura: é procuração, tipo 2 da CEP"),
    (r"ATA NOTARIAL", "ATA_NOTARIAL",
     "não é escritura: é ata notarial, tipo 8 da CEP"),
    (r"\bTESTAMENTO\b", "TESTAMENTO",
     "não é escritura: é testamento, e vai ao RCTO, não à CEP"),
)

# Atos que pertencem a CESDI, e nao a CEP.
PISTAS_CESDI: tuple[tuple[str, int, str], ...] = (
    (r"CONVERSAO DE SEPARACAO EM DIVORCIO", 3,
     "Conversão de separação em divórcio"),
    (r"DIVORCIO DIRETO|DIVORCIO CONSENSUAL", 4, "Divórcio direto"),
    (r"SEPARACAO CONSENSUAL", 1, "Separação"),
    (r"RESTABELECIMENTO DA SOCIEDADE CONJUGAL|RECONCILIACAO", 2,
     "Reconciliação"),
    (r"SOBREPARTILHA", 6, "Sobrepartilha"),
    (r"INVENTARIO E PARTILHA|INVENTARIO EXTRAJUDICIAL", 5, "Inventário"),
    (r"NOMEACAO DE INVENTARIANTE", 8, "Nomeação de inventariante"),
    (r"\bPARTILHA\b", 9, "Partilha"),
)


def _sem_acento(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def titulo_do_teor(teor: str | None) -> str | None:
    """A frase com que o ato se apresenta.

    Procura "ESCRITURA PUBLICA DE ...". Nao achando, devolve as primeiras
    palavras uteis, para a tela ao menos mostrar de que ato se trata.
    """
    if not teor:
        return None
    limpo = re.sub(r"<[^>]+>", " ", teor)
    limpo = re.sub(r"\s+", " ", limpo).strip()
    m = re.search(r"ESCRITURA\s+(?:P[ÚU]BLICA\s+)?DE\s+(.{3,120}?)(?:,|\.|;|\bSAIBAM\b|\bLIVRO\b|$)", limpo, re.I)
    if m:
        return m.group(1).strip()
    # Sem o cabeçalho padrao: devolve o comeco, pulando o timbre da Republica.
    corte = re.sub(r"^.*?FLS?\.?\s*\d+\s*", "", limpo, flags=re.I)[:160]
    return corte.strip() or limpo[:160] or None


def sugerir(teor: str | None, titulo: str | None = None) -> dict:
    """Devolve a sugestao, a evidencia e o quanto ela merece confianca.

    A resposta e sempre um dicionario, e sempre com `evidencia`: e o trecho que
    o registrador vai reler para decidir. Sugestao sem evidencia e palpite com
    cara de autoridade.

    `certeza`:
        "alta"   o titulo diz textualmente o que o ato e
        "nenhuma" nao ha titulo reconhecivel — o registrador classifica do zero
    """
    achado = titulo or titulo_do_teor(teor)
    if not achado:
        return {"natureza_censec": None, "tipo_cesdi": None, "outro_tipo": None,
                "descricao": None, "evidencia": None, "certeza": "nenhuma",
                "titulo": None}

    alvo = _sem_acento(achado).upper()

    for padrao, tipo, explicacao in PISTAS_OUTRO_ATO:
        if re.search(padrao, alvo):
            return {"natureza_censec": None, "tipo_cesdi": None,
                    "outro_tipo": tipo, "descricao": explicacao,
                    "evidencia": achado, "certeza": "alta", "titulo": achado}

    for padrao, tipo, explicacao in PISTAS_CESDI:
        if re.search(padrao, alvo):
            return {"natureza_censec": None, "tipo_cesdi": tipo,
                    "outro_tipo": None, "descricao": explicacao,
                    "evidencia": achado, "certeza": "alta", "titulo": achado}

    for padrao, natureza, explicacao in PISTAS_CEP:
        if re.search(padrao, alvo):
            return {"natureza_censec": natureza, "tipo_cesdi": None,
                    "outro_tipo": None, "descricao": explicacao,
                    "evidencia": achado, "certeza": "alta", "titulo": achado}

    return {"natureza_censec": None, "tipo_cesdi": None, "outro_tipo": None,
            "descricao": None, "evidencia": achado, "certeza": "nenhuma",
            "titulo": achado}


def resumo(sugestoes: list[dict]) -> list[dict]:
    """Agrupa para a tela: quantos atos por sugestao.

    Vinte e quatro compras e vendas viram uma linha, e o registrador confirma
    o lote inteiro depois de conferir duas ou tres.
    """
    contas: dict[tuple, int] = {}
    for s in sugestoes:
        chave = (s.get("natureza_censec"), s.get("tipo_cesdi"),
                 s.get("outro_tipo"), s.get("descricao"))
        contas[chave] = contas.get(chave, 0) + 1
    saida = []
    for (natureza, cesdi, outro, descricao), n in sorted(
            contas.items(), key=lambda x: -x[1]):
        saida.append({"natureza_censec": natureza, "tipo_cesdi": cesdi,
                      "outro_tipo": outro, "descricao": descricao, "atos": n})
    return saida
