"""Os dados cadastrais dos assentos antigos — art. 347.

    «Nos assentos de nascimento, casamento e óbito lavrados em data anterior à
     vigência do Provimento nº 63, de 14 de novembro de 2017 (…) serão
     **averbados**, quando possível, de forma **gratuita** e mediante
     **conferência**, o número do CPF, e **anotados** os números do Documento
     Nacional de Identificação Digital (DNI) ou do Registro Geral (RG), do
     título de eleitor e de outro dado cadastral público relativo à pessoa
     natural.»

O CPF SE AVERBA; O RESTO SE ANOTA — E SÃO ATOS DIFERENTES
    O artigo usa dois verbos, e não é descuido de redação: **averbar** e
    **anotar** são os dois atos que a inspeção de 12/08/2026 cobra separados, e
    que `rc_assento` já modela como espécies distintas. Pôr o CPF numa anotação
    (ou o RG numa averbação) seria lavrar o ato errado num assento — e ninguém
    percebe, porque os dois aparecem à margem.

E ELE ALCANÇA AS TRÊS ESPÉCIES, e não só o nascimento
    Nascimento, casamento **e óbito**. Medido no acervo: **135 nascimentos, 17
    casamentos e 2 óbitos** anteriores a 14/11/2017 — 154 ao todo.

    **E o acervo é 1% do livro desta casa.** Os 193 nascimentos que vieram são
    de 19.552 registrados; o número real do mutirão é muito maior, e ele só
    aparece à medida que os assentos entrarem no sistema.

TRÊS CONDIÇÕES QUE O ARTIGO IMPÕE, E NENHUMA É ENFEITE
    **«quando possível»** — não é obrigação de resultado: onde o dado não existe
    ou não se confere, não se averba, e isso não é pendência eterna.
    **«de forma gratuita»** — e ato gratuito lança com zero, e não deixa de
    lançar: o valor que *teria* é o que a serventia compensa junto ao fundo.
    **«mediante conferência»** — o número não se copia do que o interessado diz:
    confere-se. Por isso este módulo **não busca CPF em lugar nenhum** e **não
    lavra ato**: ele mostra o que falta e prepara o texto; conferir e assinar é
    de quem responde pela serventia.

O CASAMENTO TEM DOIS PRINCIPAIS, E A CONTA SÓ SOUBE DISSO EM 09/09/2026
    Pedido do oficial: *"precisamos averbar o cpf dos noivos (...) mas o
    sistema só tem a opção de averbar 1 CPF"*. `o_que_falta` perguntava
    «alguma pessoa deste assento tem CPF?» — certo para o nascimento e o
    óbito, onde só há um principal —, e errado para o casamento: assim que
    UM dos dois nubentes tinha o CPF, o assento inteiro saía do mutirão,
    escondendo que o outro ainda precisava. Agora `especie` liga a régua
    certa (`rc_cpf.PRINCIPAIS_DA_ESPECIE`), pessoa a pessoa, no casamento; nas
    outras duas espécies o comportamento continua sendo o de sempre. Ver
    `rc_cpf.py`, que ganhou o mesmo ajuste para a averbação em si — o texto
    do ato passou a dizer de qual cônjuge é o número.
"""
from __future__ import annotations

import sqlite3
from typing import Any


class DadosCadastraisError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


ARTIGO = "art. 347 do Código de Normas do TJMA"

# A DATA QUE SEPARA. O Provimento no 63 do CNJ entrou em vigor em 14/11/2017 —
# e foi depois REVOGADO, o que nao muda o corte: o artigo se refere a vigencia
# dele como marco no tempo, e nao como norma viva.
PROVIMENTO_63 = "2017-11-14"
POR_QUE_ESSA_DATA = (
    "é a vigência do Provimento nº 63/2017 do CNJ — revogado depois, o que não "
    "muda o corte: o artigo o cita como marco no tempo, e não como norma viva. "
    "De lá para cá o CPF já entra no assento; antes, não entrava")

ESPECIES = ("NASCIMENTO", "CASAMENTO", "OBITO")

# **DOIS VERBOS, DOIS ATOS.** O CPF se AVERBA; o resto se ANOTA. Por-los no
# mesmo ato seria lavrar o ato errado num assento — e ninguem percebe, porque os
# dois aparecem a margem.
O_QUE_SE_AVERBA: tuple[dict, ...] = (
    {"chave": "CPF", "nome": "CPF",
     "tipo_de_ato": "AVERBACAO",
     "documento_tipo": "CPF"},
)

O_QUE_SE_ANOTA: tuple[dict, ...] = (
    {"chave": "DNI", "nome": "Documento Nacional de Identificação Digital",
     "tipo_de_ato": "ANOTACAO", "documento_tipo": "DNI"},
    {"chave": "RG", "nome": "Registro Geral", "tipo_de_ato": "ANOTACAO",
     "documento_tipo": "RG"},
    {"chave": "TITULO_ELEITOR", "nome": "título de eleitor",
     "tipo_de_ato": "ANOTACAO", "documento_tipo": "TITULO_ELEITOR"},
    {"chave": "OUTRO", "nome": "outro dado cadastral público",
     "tipo_de_ato": "ANOTACAO", "documento_tipo": ""},
)

# O DNI **OU** O RG — o artigo escreve «do Documento Nacional de Identificacao
# Digital (DNI) **ou** do Registro Geral (RG)». Ter um dos dois basta; exigir os
# dois poria em pendencia quem ja esta em ordem.
UM_OU_OUTRO = ("DNI", "RG")

CONDICOES: tuple[dict, ...] = (
    {"chave": "QUANDO_POSSIVEL",
     "texto": "quando possível",
     "o_que_quer_dizer": "não é obrigação de resultado: onde o dado não existe "
                         "ou não se confere, não se averba — e isso não vira "
                         "pendência eterna"},
    {"chave": "GRATUITA",
     "texto": "de forma gratuita",
     "o_que_quer_dizer": "e ato gratuito **lança com zero**, e não deixa de "
                         "lançar: o valor que teria é o que a serventia "
                         "compensa junto ao fundo"},
    {"chave": "CONFERENCIA",
     "texto": "mediante conferência",
     "o_que_quer_dizer": "o número não se copia do que o interessado diz: "
                         "confere-se. É por isso que este sistema não busca CPF "
                         "em lugar nenhum"},
)


def _texto(v: Any) -> str:
    """O valor como texto, e vazio quando não há. Nunca `str(v or "")`."""
    if v is None:
        return ""
    return str(v).strip()


def alcanca(data_ato: Any) -> bool:
    """Se o assento é dos que o art. 347 alcança. Só calcula.

    **DATA ILEGÍVEL NÃO ENTRA**, e isso é deliberado: entrar por não saber poria
    na lista assentos que já têm o CPF, e a lista existe para o mutirão. Assento
    sem data já aparece noutra lista — a da carga, que avisa com o número.
    """
    bruto = _texto(data_ato)[:10]
    if len(bruto) != 10 or bruto[4] != "-" or bruto[7] != "-":
        return False
    return bruto < PROVIMENTO_63


def o_que_falta(pessoas: list[dict], atos: list[dict],
               cpf_registrado: Any = None, especie: Any = None) -> dict:
    """O que ainda falta averbar e anotar naquele assento. Só calcula.

    **OLHA OS ATOS TAMBÉM, E NÃO SÓ AS PESSOAS.** O CPF pode ter sido averbado
    sem estar na linha da pessoa — e um assento que já recebeu a averbação não
    volta para a lista do mutirão.

    **E HONRA `cpf_registrado`.** A coluna do assento é onde o número entra
    quando se grava pelo balcão; ignorá-la poria de volta na lista quem já
    tem o CPF no próprio assento.

    **NO CASAMENTO SÃO DUAS PESSOAS, E A CONTA MUDA** — achado em 09/09/2026,
    pedido do oficial: «o sistema só tem a opção de averbar 1 CPF». A conta de
    baixo pergunta «alguma pessoa tem CPF?», e isso é certo para o nascimento
    e o óbito — só há um principal —, mas no casamento dava por resolvido o
    assento inteiro assim que UM dos dois nubentes tivesse o dele, escondendo
    que o outro ainda precisava. `especie` liga a régua certa; sem ela (ou
    fora do casamento), o comportamento é o de sempre, pessoa a pessoa junto.
    """
    import rc_cpf as _CPF
    principais = _CPF.PRINCIPAIS_DA_ESPECIE.get(str(especie or "").strip().upper())
    if not principais or len(principais) <= 1:
        tipos_da_pessoa = {_texto(p.get("documento_tipo")).upper()
                          for p in pessoas
                          if _texto(p.get("documento_numero"))}
        ja_averbado = any(_texto(a.get("tipo")).upper() == "AVERBACAO"
                          and "CPF" in _texto(a.get("teor")).upper()
                          for a in atos)
        ja_no_assento = bool(
            "".join(c for c in _texto(cpf_registrado) if c.isdigit()))
        falta_averbar = [] if (ja_averbado or ja_no_assento
                               or "CPF" in tipos_da_pessoa) else ["CPF"]
        falta_anotar = []
        if not (tipos_da_pessoa & set(UM_OU_OUTRO)):
            # O ARTIGO DIZ «DNI **OU** RG» — ter um dos dois basta.
            falta_anotar.append("DNI ou RG")
        if "TITULO_ELEITOR" not in tipos_da_pessoa:
            falta_anotar.append("título de eleitor")
        return {"averbar": falta_averbar, "anotar": falta_anotar,
                "completo": not falta_averbar and not falta_anotar}

    # MAIS DE UM PRINCIPAL: cada um responde pelo seu próprio documento.
    falta_averbar = []
    falta_anotar = []
    for papel, rotulo in principais:
        tipos = {_texto(p.get("documento_tipo")).upper()
                for p in pessoas
                if _texto(p.get("papel")).upper() == papel
                and _texto(p.get("documento_numero"))}
        sufixo = f" ({rotulo.lower()})" if rotulo else ""
        if "CPF" not in tipos:
            falta_averbar.append(f"CPF{sufixo}")
        if not (tipos & set(UM_OU_OUTRO)):
            falta_anotar.append(f"DNI ou RG{sufixo}")
        if "TITULO_ELEITOR" not in tipos:
            falta_anotar.append(f"título de eleitor{sufixo}")
    return {"averbar": falta_averbar, "anotar": falta_anotar,
            "completo": not falta_averbar and not falta_anotar}


def pendentes(con: sqlite3.Connection, limite: int = 500) -> list[dict]:
    """Os assentos que o art. 347 alcança e ainda têm o que averbar. Só lê.

    **DO MAIS ANTIGO PARA O MAIS NOVO**: o mutirão começa pelos que estão há mais
    tempo sem, que são os que mais chance têm de a pessoa precisar da certidão.

    O corte da data é feito em Python, e não no SQL: a comparação de texto no
    SQLite acertaria aqui por sorte do formato ISO, mas assento com data em
    branco ou com lixo entraria — e a régua de quem entra tem de ser uma só.
    """
    con.row_factory = sqlite3.Row
    assentos = con.execute(
        """SELECT id, especie, numero, nome, data_ato, livro_volume,
                  cpf_registrado
             FROM rc_assentos
            WHERE COALESCE(situacao,'ATIVO') <> 'CANCELADO'
              AND especie IN ('NASCIMENTO','CASAMENTO','OBITO')
         ORDER BY data_ato IS NULL, data_ato, id""").fetchall()
    saida: list[dict] = []
    for a in assentos:
        if not alcanca(a["data_ato"]):
            continue
        pessoas = [dict(x) for x in con.execute(
            "SELECT * FROM rc_pessoas WHERE assento_id=?", (a["id"],))]
        try:
            atos = [dict(x) for x in con.execute(
                "SELECT * FROM rc_atos WHERE assento_id=?", (a["id"],))]
        except sqlite3.Error:
            # MEIA LISTA E MELHOR QUE LISTA NENHUMA, e a falta fica visivel.
            atos = []
        falta = o_que_falta(pessoas, atos, a["cpf_registrado"],
                           especie=a["especie"])
        if falta["completo"]:
            continue
        saida.append(dict(a, **falta))
        if len(saida) >= limite:
            break
    return saida


def quantas_pendentes(con: sqlite3.Connection) -> int:
    """Quantos assentos esperam. Só lê."""
    return len(pendentes(con, limite=100000))


def resumo(con: sqlite3.Connection) -> dict:
    """O tamanho do mutirão, por espécie. Só lê — é o alto da tela."""
    lista = pendentes(con, limite=100000)
    por_especie = {e: 0 for e in ESPECIES}
    for x in lista:
        chave = _texto(x["especie"]).upper()
        if chave in por_especie:
            por_especie[chave] += 1
    return {"total": len(lista), "por_especie": por_especie,
            "so_cpf": sum(1 for x in lista if x["averbar"] and not x["anotar"])}
