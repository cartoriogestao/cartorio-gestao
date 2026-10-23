"""A matrícula de 32 dígitos do registro civil — compor, conferir, explicar.

DE ONDE VEIO ESTA REGRA
    Do **Anexo IV do manual de carga da CRC** (`carga_registros_webservice`,
    versão 2.7), que traz o cálculo com um exemplo trabalhado passo a passo. Não
    é dedução minha: é a fonte normativa.

    Antes de encontrá-la eu tentei deduzir a regra dos dados, e falhei — vale
    registrar por quê, porque o motivo é instrutivo. Procurei pesos **cíclicos**
    (2-9, como no CPF) e resolvi o sistema linear em GF(11) supondo
    `dígito = 11 − resto`. A regra real usa pesos **decrescentes de 31 a 2**, o
    resto **é** o dígito, e há um passo que eu jamais adivinharia: **a soma é
    multiplicada por 10** antes da divisão. Três suposições razoáveis, e as três
    erradas.

    **O que se mede não substitui o que está escrito na norma.** A medição
    chegou perto — apontou o módulo 11 e o «resto 10 vira 1» —, mas quem fecha é
    o texto.

CONFERIDA CONTRA 255 CASOS REAIS, e acertou 255:
    o exemplo do próprio Anexo IV, os 243 assentos do acervo desta serventia, o
    óbito nº 1978 e onze consultas ao serviço oficial da ARPEN-SP.

    O 255º merece nota: **um assento do acervo tinha a matrícula errada** — o
    nascimento nº 19132, cuja matrícula veio do E-Ofício terminando em `55`
    quando a regra dá `91`. Não foi a fórmula que falhou; foi o dado. O serviço
    da ARPEN, consultado, concordou com a fórmula.
"""
from __future__ import annotations

from typing import Any

from bd_nativo import banco

# ------------------------------------------------------------------ a norma

TAMANHO = 32
TAMANHO_SEM_DV = 30

FONTE = ("Anexo IV do manual de carga da CRC "
         "(carga_registros_webservice, versão 2.7)")

# OS CAMPOS, NA ORDEM, COM O TAMANHO DE CADA UM. A soma dá 30; o DV são os 2
# últimos. Esta tabela é o que separa «compor a matrícula» de «concatenar
# números na esperança de que caibam».
CAMPOS: tuple[dict, ...] = (
    {"chave": "cns",     "digitos": 6, "titulo": "Código do cartório",
     "de_onde": "o CNS desta serventia"},
    {"chave": "acervo",  "digitos": 2, "titulo": "Acervo",
     "de_onde": "**01** é o acervo próprio; 02 a 99 são os incorporados"},
    {"chave": "servico", "digitos": 2, "titulo": "RCPN",
     "de_onde": "sempre **55** — registro civil das pessoas naturais"},
    {"chave": "ano",     "digitos": 4, "titulo": "Ano do registro",
     "de_onde": "o ano do REGISTRO, e não o do fato"},
    {"chave": "livro_tipo", "digitos": 1, "titulo": "Ato",
     "de_onde": "o tipo de livro — ver `TIPOS_DE_LIVRO`"},
    {"chave": "livro",   "digitos": 5, "titulo": "Nº do Livro",
     "de_onde": "o número do livro"},
    {"chave": "folha",   "digitos": 3, "titulo": "Nº da Folha",
     "de_onde": "a folha em que o termo foi lavrado"},
    {"chave": "termo",   "digitos": 7, "titulo": "Nº do Registro",
     "de_onde": "o número de ordem do termo no livro"},
)

# O TIPO DE LIVRO, COM A PROCEDÊNCIA DE CADA UM AO LADO.
#
#   **A procedência não é enfeite: ela diz o que se pode afirmar.** É a mesma
#   decisão do envelope do selo do civil, onde `MEDIDO` e `TABELA` ficam
#   marcados — quem lê precisa saber se o número saiu do dado desta casa, de
#   uma norma, ou de um exemplo de contrato.
ACERVO = "medido nos assentos desta casa"
SIRC = "guia do SIRC para cartórios"
EXEMPLO_DO_EPROCLAMAS = "exemplo do contrato da API e-Proclamas (ON-RCPN)"
PROVIMENTO_182 = ("art. 473, V, do Código Nacional de Normas (Prov. CNJ "
                  "149/2023, redação do Prov. CNJ 182/2024)")

TIPOS_DE_LIVRO: dict[str, dict] = {
    "1": {"livro": "A",           "e": "nascimento",
          "fonte": ACERVO},
    "2": {"livro": "B",           "e": "casamento",
          "fonte": SIRC},
    "3": {"livro": "B-Auxiliar",  "e": "casamento religioso com efeitos civis",
          "fonte": SIRC},
    "4": {"livro": "C",           "e": "óbito",
          "fonte": ACERVO},
    "5": {"livro": "C-Auxiliar",  "e": "natimorto",
          "fonte": SIRC},
    # O LIVRO D ENTROU EM 03/09/2026, E A FONTE DELE É MAIS FRACA QUE AS OUTRAS
    # — por isso ela fica escrita, e não misturada com as demais.
    #
    #   **O guia do SIRC não tem o Livro D, e a razão é boa: o SIRC não recebe
    #   proclamas.** Ele recebe nascimento, casamento e óbito. Procurado nos
    #   dois manuais que esta casa guarda (`SIRC_manual.txt` e
    #   `CRC_manual.txt`), o Livro D não aparece em nenhum.
    #
    #   **O que existe é o exemplo do contrato do e-Proclamas**, cuja matrícula
    #   de exemplo — `11111101552025600001102000001541` — traz `6` exatamente
    #   na posição do tipo de livro. É a Central do Registro Civil dizendo,
    #   num contrato de proclamas, com que dígito um proclama se identifica.
    #
    #   **E o exemplo é FABRICADO, o que é preciso dizer**: o CNS dele é
    #   `111111`, que não existe, e o dígito verificador não confere com a
    #   regra do Anexo IV (dá 20, e está escrito 41). Logo ele **não prova a
    #   conta**; o que ele mostra é a POSIÇÃO, que é outra coisa e é o que se
    #   está usando aqui.
    #
    #   **A tela mostra a procedência ao lado da matrícula composta**, para
    #   quem assinar o registro ver de onde veio o dígito antes de assinar.
    "6": {"livro": "D",           "e": "proclamas",
          "fonte": EXEMPLO_DO_EPROCLAMAS},
    # O LIVRO E É UM SÓ DÍGITO PARA TODOS OS SEUS ATOS — 13/10/2026, ordem do
    # oficial: «matrícula do livro E segue a regra, pesquisar qual é; se não
    # tiver, aplica a mesma pra tudo». A regra existe e está na casa
    # (`FONTES_EXTERNAS/cnj_provimento_182`): «7: Livro E (Demais atos
    # relativos ao registro civil)». O desdobramento antigo (8 emancipações,
    # 9 interdições, Prov. 3/2009 e 63/2017) **saiu da redação de 2024** —
    # e esta casa tem um Livro E só.
    "7": {"livro": "E",           "e": "demais atos relativos ao registro civil "
                                       "(e as transcrições do exterior)",
          "fonte": PROVIMENTO_182},
}

# A espécie do nosso sistema para o tipo de livro da matrícula.
LIVRO_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "1",
    "CASAMENTO": "2",
    "CASAMENTO_RELIGIOSO": "3",
    "OBITO": "4",
    "NATIMORTO": "5",
    "PROCLAMAS": "6",
    "EXTERIOR": "7",
    # As sete espécies do Livro E — ver o «7» em `TIPOS_DE_LIVRO`.
    **{e: "7" for e in ("AUSENCIA", "INTERDICAO", "TUTELA", "EMANCIPACAO",
                        "UNIAO_ESTAVEL", "OPCAO_NACIONALIDADE", "OUTRO")},
}


def procedencia_do_livro(livro_tipo: Any) -> str:
    """De onde veio o dígito daquele tipo de livro. Só lê.

    A tela do proclama mostra isto ao lado da matrícula: **quem assina precisa
    saber que o `6` saiu do exemplo de um contrato, e não do guia do SIRC**.
    """
    return str((TIPOS_DE_LIVRO.get(str(livro_tipo)) or {}).get("fonte") or "")

ACERVO_PROPRIO = "01"
SERVICO_RCPN = "55"


class MatriculaError(ValueError):
    """Erro de matrícula, em português de balcão."""


# --------------------------------------------------------- o dígito, a regra


def _fase(digitos: str, peso_inicial: int) -> int:
    """Uma fase do cálculo do Anexo IV.

    Multiplica cada dígito por um peso que **decresce** a partir de
    `peso_inicial` até 2, soma, **multiplica a soma por 10** e tira o resto de
    11. O resto É o dígito — e não `11 - resto`, que é o costume de outros
    documentos e foi o que me despistou.

    O «vezes 10» não é enfeite: sem ele o resultado é outro. Está no Anexo IV
    com todas as letras — «soma-se todos os resultados das multiplicações acima
    e depois multiplica-se por 10».
    """
    soma = sum(int(d) * p
               for d, p in zip(digitos, range(peso_inicial, 1, -1)))
    resto = (soma * 10) % 11
    # «Se o resto for 10, então o dígito será 1» — a letra do Anexo IV. Esta
    # linha é a que eu tinha adivinhado medindo, e a única que acertei.
    return 1 if resto == 10 else resto


def digito_verificador(base30: str) -> str:
    """Os dois dígitos, a partir dos 30 primeiros.

    A segunda fase inclui o **primeiro dígito já calculado** — são 31 dígitos
    com pesos de 32 a 2. Calcular as duas fases sobre a mesma base daria outro
    número, e daria calado.
    """
    base30 = _so_digitos(base30, "a base da matrícula")
    if len(base30) != TAMANHO_SEM_DV:
        raise MatriculaError(
            f"A base da matrícula tem de ter {TAMANHO_SEM_DV} dígitos, e esta "
            f"tem {len(base30)}.")
    d1 = _fase(base30, 31)
    d2 = _fase(base30 + str(d1), 32)
    return f"{d1}{d2}"


def _so_digitos(valor: Any, o_que: str) -> str:
    texto = "" if valor is None else str(valor)
    limpo = "".join(c for c in texto if c.isdigit())
    if not limpo:
        raise MatriculaError(f"Faltou {o_que}.")
    return limpo


# ------------------------------------------------------------------ compor


def compor(*, cns: Any, ano: Any, livro_tipo: str, livro: Any, folha: Any,
           termo: Any, acervo: str = ACERVO_PROPRIO) -> str:
    """A matrícula inteira, com o dígito calculado.

    **Cada campo é preenchido com zeros à ESQUERDA até o seu tamanho.** Folha 57
    é `057`; termo 1978 é `0001978`. Encaixar à direita trocaria o número por
    outro que também tem 32 dígitos — e um número errado com o tamanho certo
    passa em qualquer conferência de formato.
    """
    if str(livro_tipo) not in TIPOS_DE_LIVRO:
        raise MatriculaError(
            f"Tipo de livro «{livro_tipo}» não existe. Os que existem: "
            + ", ".join(f"{k} = Livro {v['livro']} ({v['e']})"
                        for k, v in TIPOS_DE_LIVRO.items()) + ".")
    valores = {"cns": cns, "acervo": acervo, "servico": SERVICO_RCPN,
               "ano": ano, "livro_tipo": livro_tipo, "livro": livro,
               "folha": folha, "termo": termo}
    partes = []
    for campo in CAMPOS:
        bruto = _so_digitos(valores[campo["chave"]], campo["titulo"].lower())
        if len(bruto) > campo["digitos"]:
            raise MatriculaError(
                f"{campo['titulo']} tem {len(bruto)} dígitos e só cabem "
                f"{campo['digitos']}: «{bruto}».")
        partes.append(bruto.zfill(campo["digitos"]))
    base = "".join(partes)
    return base + digito_verificador(base)


def compor_do_assento(assento: dict, *, cns: Any,
                      acervo: str = ACERVO_PROPRIO) -> str:
    """A matrícula a partir de um assento nosso. Só lê o dicionário."""
    especie = str(assento.get("especie") or "").strip().upper()
    tipo = LIVRO_DA_ESPECIE.get(especie)
    if not tipo:
        raise MatriculaError(
            f"Não sei em que livro entra a espécie «{especie or '(vazia)'}». "
            f"As que sei: " + ", ".join(sorted(LIVRO_DA_ESPECIE)) + ".")
    data = str(assento.get("data_ato") or "")
    ano = data[:4]
    if len(ano) != 4 or not ano.isdigit():
        raise MatriculaError(
            "A matrícula leva o ano do registro, e este assento não tem data "
            "de ato em que dê para lê-lo.")
    return compor(cns=cns, ano=ano, livro_tipo=tipo,
                  livro=assento.get("livro"), folha=assento.get("folha"),
                  termo=assento.get("numero"), acervo=acervo)


# ----------------------------------------------------------------- conferir


def partes(matricula: Any) -> dict:
    """Abre a matrícula nos campos que a compõem. Só lê."""
    m = _so_digitos(matricula, "a matrícula")
    if len(m) != TAMANHO:
        raise MatriculaError(
            f"A matrícula tem {TAMANHO} dígitos, e esta tem {len(m)}.")
    fora: dict[str, Any] = {}
    i = 0
    for campo in CAMPOS:
        fora[campo["chave"]] = m[i:i + campo["digitos"]]
        i += campo["digitos"]
    fora["dv"] = m[i:]
    livro = TIPOS_DE_LIVRO.get(fora["livro_tipo"])
    fora["livro_nome"] = livro["livro"] if livro else ""
    fora["livro_e"] = livro["e"] if livro else ""
    return fora


def confere(matricula: Any) -> dict:
    """Confere o dígito. **Nunca levanta erro por dígito errado.**

    Devolve o que achou, com o motivo escrito. Matrícula errada não é exceção
    de programa: é um fato do acervo que alguém precisa ler e decidir — e
    quebrar a tela na cara do escrevente esconderia justamente o que ele
    precisa ver.
    """
    try:
        p = partes(matricula)
    except MatriculaError as erro:
        return {"ok": False, "motivo": str(erro), "esperado": "", "achado": ""}
    base = _so_digitos(matricula, "a matrícula")[:TAMANHO_SEM_DV]
    esperado = digito_verificador(base)
    if esperado == p["dv"]:
        return {"ok": True, "motivo": "", "esperado": esperado,
                "achado": p["dv"], "partes": p}
    return {
        "ok": False,
        "esperado": esperado,
        "achado": p["dv"],
        "partes": p,
        "motivo": (f"O dígito verificador devia ser **{esperado}** e está "
                   f"**{p['dv']}**. Pela regra do {FONTE}."),
    }


def explicar(matricula: Any) -> list[str]:
    """A matrícula em português, campo a campo — para a tela mostrar.

    Existe porque **32 dígitos seguidos não se conferem a olho**, e o balcão
    precisa saber o que cada pedaço quer dizer para desconfiar quando estiver
    errado.
    """
    p = partes(matricula)
    linhas = []
    for campo in CAMPOS:
        v = p[campo["chave"]]
        extra = ""
        if campo["chave"] == "livro_tipo" and p["livro_nome"]:
            extra = f" — Livro {p['livro_nome']} ({p['livro_e']})"
        linhas.append(f"{campo['titulo']}: {v}{extra}")
    r = confere(matricula)
    linhas.append("Dígito verificador: " + p["dv"]
                  + (" (confere)" if r["ok"] else f" — {r['motivo']}"))
    return linhas


# -------------------------------------------------- o varredor do acervo


def matriculas_com_digito_errado(con,
                                 limite: int = 500) -> list[dict]:
    """Os assentos cuja matrícula não fecha. **Só lê — não conserta nada.**

    NÃO CONSERTO POR DECISÃO, E NÃO POR CAUTELA GENÉRICA. A matrícula é o
    identificador nacional do assento, e ela já pode ter saído em certidão, ter
    ido para a CRC e para o SIRC com o número errado. Trocar o número no banco
    calaria o problema sem resolver nenhuma dessas pontas — e a decisão sobre
    o que fazer é do oficial, não do programa.

    Esta lista achou **um** caso no acervo desta casa: o nascimento nº 19132.
    """
    achados = []
    for linha in banco(con).ler(
            "SELECT id, especie, numero, nome, data_ato, matricula, origem "
            "FROM rc_assentos "
            "WHERE TRIM(COALESCE(matricula,'')) <> '' "
            "ORDER BY id LIMIT %s", (limite,)):
        d = dict(linha)
        r = confere(d["matricula"])
        if not r["ok"]:
            d["esperado"] = r["esperado"]
            d["achado"] = r["achado"]
            d["motivo"] = r["motivo"]
            achados.append(d)
    return achados


def quantas_sem_matricula(con) -> int:
    return int(banco(con).valor(
        "SELECT COUNT(*) AS n FROM rc_assentos "
        "WHERE TRIM(COALESCE(matricula,'')) = ''"))
