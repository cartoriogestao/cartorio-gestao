"""Monta a remessa trimestral do IBGE a partir do que a casa lavrou.

O QUE ESTE MÓDULO É, E O QUE ELE NÃO É
    `ibge_remessa.py` sabe o **formato** — as 25 posições do nascimento, as 29
    do casamento, as 23 do óbito, a largura de cada uma, o alinhamento.

    Este aqui sabe **de onde vem cada valor**: do assento, das pessoas, da
    tabela de municípios, dos catálogos. É a costura, e é onde moram as regras
    que o formato não expressa.

A REGRA QUE MANDA EM TUDO, e ela é do próprio IBGE (item 14 da especificação):

    «Quando não houver valor para qualquer campo numérico, então preenchê-lo
     com o valor 9 de acordo com o tamanho definido na estrutura do arquivo.»

    Ou seja: **o que não se sabe se declara como ignorado**, e não se inventa.
    Isso não é permissão para mandar tudo em 9 — é o contrário: é a forma
    honesta de dizer «não sei», e por isso `conferir` conta quantos 9 saíram e
    diz de quê. Remessa cheia de «ignorado» é remessa aceita e inútil.

O QUE AINDA NÃO SE PODE MONTAR DO ATO NOVO, E POR QUÊ (medido em 28/08/2026)
    O sistema lavra o assento com o NOME de quem é o registro, e mais nada
    sobre a pessoa. `rc_pessoas` guarda **pai, mãe e avós** — que a carga do
    acervo trouxe —, e não o registrado, os nubentes nem o falecido.

    O IBGE pede, dessas pessoas: sexo, data de nascimento, naturalidade (UF e
    município), residência (UF e município) e estado civil. Nada disso existe
    hoje.

    Então a remessa do ato NOVO sai com «ignorado» nesses campos, e
    `o_que_falta` diz exatamente quais e de quantos assentos. **É a lista do
    que o balcão precisa passar a perguntar** — e ela é medida, não suposta.

    A remessa dos assentos ANTIGOS sai do acervo, que é onde os dados estão.
"""
from __future__ import annotations

import sqlite3
from typing import Any

import ibge_remessa as IBGE
import ibge_schema as IB

# ------------------------------------------------- as regras de UF e país
#
# Item 15 da especificação, transcrito em regra:
#
#   UF = 98 (estrangeiro)  -> município 99999, país = o código dele ou 999
#   UF = 59 ou 99          -> município 99999, país 999
#   UF  qualquer outra     -> município = o código, país = 076 (Brasil)
#
# ISTO NÃO É DETALHE: mandar o município de São Luís com UF 98 diria que São
# Luís fica no estrangeiro. Os três campos andam juntos, e é por isso que uma
# função só devolve os três.
UF_ESTRANGEIRO = "98"
UF_IGNORADA = "99"
UF_SEM_DECLARACAO = "59"
MUNICIPIO_IGNORADO = "99999"
PAIS_IGNORADO = "999"


class IbgeError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcão."""


def _ignorado(largura: int) -> str:
    """O «sem valor» do IBGE: tantos noves quanto o campo tem posições."""
    return "9" * int(largura)


def lugar(con: sqlite3.Connection, cidade: Any, uf: Any) -> dict:
    """UF, município e país de um lugar escrito em texto. Só LÊ.

    OS TRÊS ANDAM JUNTOS, e por isso saem juntos: mandar o código do município
    com a UF de estrangeiro diria que aquela cidade fica fora do Brasil.

    NÃO ACHOU, NÃO INVENTA: devolve `99`/`99999`/`999`, que é o «ignorado» do
    IBGE — e marca `achou=False`, para a conferência poder contar. Escolher o
    município mais parecido seria assinar por quem lavrou.
    """
    nome = IB.normalizar_nome(cidade)
    sigla = str(uf or "").strip().upper()
    linha = None
    if nome:
        if sigla:
            linha = con.execute(
                "SELECT * FROM ib_municipios WHERE nome_norm=? AND uf=?",
                (nome, sigla)).fetchone()
        if linha is None:
            # SEM UF, SÓ VALE SE O NOME FOR ÚNICO NO BRASIL. Há dezenas de
            # «Bom Jesus»; escolher o primeiro poria a estatística no estado
            # errado, e ninguém notaria nunca.
            achados = con.execute(
                "SELECT * FROM ib_municipios WHERE nome_norm=? LIMIT 2",
                (nome,)).fetchall()
            linha = achados[0] if len(achados) == 1 else None
    if linha is None:
        return {"uf": UF_IGNORADA, "municipio": MUNICIPIO_IGNORADO,
                "pais": PAIS_IGNORADO, "codigo_ibge": "", "achou": False}
    # O `codigo_ibge` DE SETE DÍGITOS ENTROU EM 03/09/2026, e a razão é uma
    # segunda Central que pede o mesmo município noutra forma.
    #
    #   A remessa do IBGE quer o código **partido** — `21` e `98765`, em
    #   posições diferentes do arquivo. O e-Proclamas do ON-RCPN quer os
    #   **sete juntos**, `2198765`.
    #
    #   **É o mesmo município, achado pela mesma busca**, e por isso ele sai
    #   daqui em vez de uma segunda função com a mesma consulta dentro. Uma
    #   cópia divergiria no primeiro conserto — e o conserto que importa aqui
    #   é a regra de ambiguidade («sem UF, só vale se o nome for único no
    #   Brasil»), que é o que impede pôr o casal na cidade errada.
    return {"uf": f"{int(linha['codigo_uf']):02d}",
            "municipio": linha["codigo_mun"], "pais": IBGE.BRASIL,
            "codigo_ibge": f"{int(linha['codigo_ibge']):07d}",
            "achou": True}


def lugar_estrangeiro(codigo_do_pais: Any = None) -> dict:
    """O lugar de quem nasceu ou mora fora — regra 1 do item 15."""
    codigo = "".join(c for c in str(codigo_do_pais or "") if c.isdigit())
    return {"uf": UF_ESTRANGEIRO, "municipio": MUNICIPIO_IGNORADO,
            "pais": codigo.zfill(3) if codigo else PAIS_IGNORADO,
            "achou": bool(codigo)}


# --------------------------------------------------- o cabeçalho da casa


def cabecalho(config: dict) -> dict:
    """As quatro primeiras posições de toda linha: quem manda o arquivo.

    ELAS VÊM DA CARGA DO IBGE (`tbIBGE_Propriedades`) e viram configuração.
    Sem elas o arquivo não sai — e não sai mesmo: o IBGE não tem como saber de
    que cartório é a remessa, e recusa a remessa inteira. É por isso que a
    recusa aqui diz onde responder.
    """
    faltando = [rotulo for chave, rotulo in
                (("ibge_uf", "o código da UF"),
                 ("ibge_municipio", "o código do município"),
                 ("ibge_distrito", "o código do distrito"),
                 ("ibge_cartorio", "o código desta serventia junto ao IBGE"))
                if not str(config.get(chave) or "").strip()]
    if faltando:
        raise IbgeError(
            f"A remessa do IBGE não sai sem {', '.join(faltando)}. Isso vem da "
            f"carga do acervo (Livros e acervo → Trazer o acervo do E-Ofício) "
            f"ou se informa em Administrativo → Configurações.")
    return {
        "UF-PESQUISA": str(config["ibge_uf"]).strip().zfill(2),
        "MUN-PESQUISA": str(config["ibge_municipio"]).strip().zfill(5),
        "DIST-PESQUISA": str(config["ibge_distrito"]).strip().zfill(2),
        "COD_CARTORIO": str(config["ibge_cartorio"]).strip().zfill(2),
    }


# A LETRA DO LIVRO SAI DA ESPECIE, e o numero do volume sai do assento.
#
#   O arquivo real desta casa escreve `A24` e `C05` — letra colada ao numero,
#   com dois digitos e SEM hifen. O sistema guarda `A-24` no nascimento (que e
#   como o acervo escreve) e `5` no obito (onde o acervo nao tem coluna de
#   letra nenhuma).
#
#   Recortar isso na hora de montar a linha e o certo: `livro_volume` guarda o
#   que o LIVRO DE PAPEL diz, e a certidao imprime `Livro A-24` porque e assim
#   que ele se chama. Quem tem forma propria e o arquivo do IBGE, e a forma
#   dele mora aqui.
LETRA_DO_LIVRO: dict[str, str] = {
    "NASCIMENTO": "A", "NATIMORTO": "C",
    "CASAMENTO": "B", "CASAMENTO_RELIGIOSO": "B",
    "OBITO": "C",
}


def numero_do_livro(assento: Any) -> str:
    """`A-24` + nascimento -> `A24`; `5` + obito -> `C05`. So calcula.

    Medido no arquivo que esta casa exportou: `A24` nas 28 linhas de
    nascimento, `C05` nas 13 de obito e `B04` nas 2 de casamento.
    """
    letra = LETRA_DO_LIVRO.get(
        str(_valor(assento, "especie") or "").strip().upper(), "")
    bruto = str(_valor(assento, "livro_volume") or "").strip()
    digitos = "".join(c for c in bruto if c.isdigit())
    if not digitos:
        return bruto.replace("-", "")
    return f"{letra}{int(digitos):02d}"


def identificacao(assento: Any, ato: Any, *, ano: int, trimestre: int) -> dict:
    """Trimestre, ano, livro e número do registro — comuns aos três modelos.

    O ANO VAI COM DOIS DÍGITOS, e é o do REGISTRO, não o do fato: a remessa é
    do que a casa registrou naquele trimestre, e o registro tardio de um
    nascimento de 1990 entra no trimestre em que foi lavrado.
    """
    return {
        "TRIM-PESQUISA": str(int(trimestre)),
        "ANO-PESQUISA": f"{int(ano) % 100:02d}",
        "NUM-LIVRO": numero_do_livro(assento),
        "NUM-REGLIV": _numero(_valor(assento, "numero")),
        "DATAREGDIA": _dia_ou_mes(_valor(ato, "data_ato"), 8, 10),
        "DATAREGMES": _dia_ou_mes(_valor(ato, "data_ato"), 5, 7),
    }


def _valor(linha: Any, nome: str) -> Any:
    """Uma coluna que pode não existir — coluna de migração estoura com
    `IndexError` num `sqlite3.Row`, e um relatório não pode virar HTTP 500."""
    if linha is None:
        return None
    try:
        return linha[nome]
    except (IndexError, KeyError, TypeError):
        return None


def _numero(v: Any) -> str:
    try:
        return str(int(v))
    except (TypeError, ValueError):
        return ""


def _dia_ou_mes(data: Any, de: int, ate: int) -> str:
    s = str(data or "")
    pedaco = s[de:ate]
    return pedaco if pedaco.isdigit() else ""


def data_ddmmaaaa(data: Any) -> str:
    """`2026-08-28` -> `28082026`. Sem data, oito noves.

    O IBGE quer o dia primeiro; o banco guarda o ano primeiro. Inverter na hora
    de montar a linha, em vez de guardar invertido, é o que mantém o banco
    ordenável por data.
    """
    s = str(data or "")[:10]
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}{s[5:7]}{s[0:4]}"
    return _ignorado(8)


def sexo(v: Any) -> str:
    """`M`/`F` -> `1`/`2`. Sem sexo, `9`.

    NO CASAMENTO A TABELA NÃO TEM `9` — a especificação lista só masculino e
    feminino para os cônjuges —, e mesmo assim é `9` que sai quando não há
    valor: é o que a regra geral do item 14 manda fazer, e travar a remessa
    inteira por um cônjuge sem sexo custaria o trimestre.

    Eu tinha escrito isto com um parâmetro `aceita_ignorado` que **os dois
    lados devolviam a mesma coisa**. Parâmetro que não muda nada é pior que
    parâmetro nenhum: ele promete um comportamento que não existe, e o próximo
    a ler acredita.
    """
    letra = str(v or "").strip().upper()[:1]
    if letra == "M":
        return "1"
    if letra == "F":
        return "2"
    return "9"


# O ESTADO CIVIL DO CASAMENTO NÃO É O DO ÓBITO, e esta é a armadilha mais fácil
# deste módulo — a mesma palavra em dois lugares outra vez:
#
#     no CASAMENTO   1 solteiro, 2 VIÚVO,  3 divorciado, 9 ignorado
#     no ÓBITO       1 solteiro, 2 CASADO, 3 viúvo, 4 separado judicialmente,
#                    6 divorciado, 7 desquitado, 9 ignorado
#
# Usar um pelo outro faria o `2` dizer que a viúva era casada. São dois
# catálogos, e por isso são duas funções.
ESTADO_CIVIL_DO_NUBENTE: dict[int, str] = {
    1: "solteira(o)", 2: "viúva(o)", 3: "divorciada(o)", 9: "ignorado",
}

_NUBENTE_POR_PALAVRA = {
    "solteir": 1, "viuv": 2, "divorciad": 3,
}
_FALECIDO_POR_PALAVRA = {
    "solteir": 1, "casad": 2, "viuv": 3, "separad": 4,
    "divorciad": 6, "desquitad": 7,
}


def _por_palavra(texto: Any, tabela: dict[str, int]) -> str:
    """O código do estado civil escrito em português. Só calcula.

    O SISTEMA GUARDA TEXTO LIVRE («Solteiro(a)», «SOLTEIRA», «solteiro»), e por
    isso a comparação é pelo RADICAL sem acento — `viuv` acha «viúvo», «viúva»
    e «VIUVA». Comparar a palavra inteira acharia uma grafia e perderia as
    outras, caladamente.
    """
    norm = IB.normalizar_nome(texto)
    for radical, codigo in tabela.items():
        if radical in norm:
            return str(codigo)
    return "9"


def estado_civil_do_nubente(v: Any) -> str:
    return _por_palavra(v, _NUBENTE_POR_PALAVRA)


def estado_civil_do_falecido(v: Any) -> str:
    return _por_palavra(v, _FALECIDO_POR_PALAVRA)


def idade_em_anos(nascimento: Any, quando: Any) -> tuple[str, str]:
    """A idade e a unidade de tempo do falecido. Só calcula.

    DEVOLVE OS DOIS JUNTOS porque eles só fazem sentido juntos: `2` é dois anos
    ou dois dias conforme o campo ao lado — e o recém-nascido que morre tem
    idade em minutos. Separá-los seria deixar que um fosse preenchido sem o
    outro.
    """
    n, q = str(nascimento or "")[:10], str(quando or "")[:10]
    if len(n) != 10 or len(q) != 10:
        return str(IBGE.IDADE_DO_FALECIDO_IGNORADA), "9"
    # Ainda não fez aniversário no ano da morte -> um ano a menos. A comparação
    # é de texto `MM-DD`, que ordena igual a data porque tem largura fixa.
    anos = int(q[:4]) - int(n[:4]) - (q[5:10] < n[5:10])
    if anos < 0:
        return str(IBGE.IDADE_DO_FALECIDO_IGNORADA), "9"
    return f"{min(anos, 998):03d}", "4"      # 4 = anos


def idade_da_genitora(nascimento_da_mae: Any, nascimento_do_filho: Any) -> str:
    """A idade da mãe no parto, na faixa que o IBGE declara (10 a 69).

    FORA DA FAIXA VIRA `99`, e isso não é conserto: é o que o IBGE manda fazer
    com o que ele não aceita. Foi um caso desses que quase me fez descartar a
    leitura certa da posição — o arquivo dizia `01` porque o dado do acervo
    estava errado, e eu concluí que a posição não era a idade.
    """
    n, f = str(nascimento_da_mae or "")[:10], str(nascimento_do_filho or "")[:10]
    if len(n) != 10 or len(f) != 10:
        return str(IBGE.IDADE_IGNORADA)
    anos = int(f[:4]) - int(n[:4]) - (f[5:10] < n[5:10])
    if IBGE.IDADE_GENITORA_MINIMA <= anos <= IBGE.IDADE_GENITORA_MAXIMA:
        return f"{anos:02d}"
    return str(IBGE.IDADE_IGNORADA)


# ------------------------------------------------- a conferência do que falta


CAMPOS_QUE_O_BALCAO_AINDA_NAO_COLETA: dict[str, tuple[str, ...]] = {
    # Medido em 28/08/2026: `rc_pessoas` guarda pai, mãe e avós — trazidos pela
    # carga —, e NÃO o registrado, os nubentes nem o falecido. Estes são os
    # campos que o IBGE pede dessas pessoas e que o sistema ainda não tem onde
    # guardar. A lista existe para o balcão saber o que passar a perguntar.
    "NASCIMENTO": ("sexo do registrado", "município de nascimento",
                   "residência da mãe", "data de nascimento da mãe"),
    "CASAMENTO": ("sexo dos cônjuges", "estado civil dos cônjuges",
                  "data de nascimento dos cônjuges",
                  "naturalidade dos cônjuges", "residência dos cônjuges"),
    "OBITO": ("sexo do falecido", "data de nascimento do falecido",
              "estado civil do falecido", "naturalidade do falecido",
              "residência do falecido", "natureza do óbito",
              "local do óbito"),
}


def o_que_falta(con: sqlite3.Connection, especie: str) -> list[str]:
    """O que o balcão precisa passar a perguntar, para aquela espécie. Só LÊ.

    NÃO É DOCUMENTAÇÃO, É TELA: documentação não avisa ninguém. Esta lista sai
    na conferência da remessa, junto com quantos assentos ela alcança.
    """
    return list(CAMPOS_QUE_O_BALCAO_AINDA_NAO_COLETA.get(
        str(especie or "").strip().upper(), ()))


def conferir(linhas: list[str], layout) -> dict:
    """Quantas posições da remessa saíram como «ignorado». Só calcula.

    POR QUE ISTO EXISTE: a regra do item 14 permite mandar `9` onde não há
    valor, e uma remessa inteira de noves seria **aceita** pelo IBGE — e
    inútil. O número que esta função devolve é o que separa «cumpri a
    obrigação» de «mandei papel em branco».
    """
    pos = IBGE.posicoes(layout)
    total = ignorados = 0
    por_campo: dict[str, int] = {}
    for linha in linhas:
        for nome, (de, ate) in pos.items():
            pedaco = linha[de:ate]
            total += 1
            if pedaco and set(pedaco.strip() or "9") == {"9"}:
                ignorados += 1
                por_campo[nome] = por_campo.get(nome, 0) + 1
    return {"linhas": len(linhas), "campos": total, "ignorados": ignorados,
            "por_campo": dict(sorted(por_campo.items(),
                                     key=lambda p: -p[1]))}


# =====================================================================
# AS TRES LINHAS, E O ARQUIVO
#
# CADA UMA E UMA FUNCAO SO QUE COSTURA, e nao um metodo de classe: o que muda
# entre nascimento, casamento e obito nao e o comportamento — e QUAIS campos
# saem de onde. Uma classe com tres subclasses esconderia isso atras de heranca;
# tres funcoes deixam o de-para a vista, que e o que se confere depois.
# =====================================================================


def _pessoas_por_papel(con: sqlite3.Connection, assento_id: Any) -> dict:
    """As pessoas daquele assento, indexadas pelo papel. So LE."""
    saida: dict[str, Any] = {}
    for r in con.execute(
            "SELECT * FROM rc_pessoas WHERE assento_id=? ORDER BY ordem, id",
            (int(assento_id),)):
        saida.setdefault(r["papel"], r)
    return saida


def _lugar_da_pessoa(con: sqlite3.Connection, pessoa: Any,
                     cidade: str, uf: str) -> dict:
    """Um lugar de uma pessoa, ou «ignorado» quando ela nao existe."""
    if pessoa is None:
        return {"uf": UF_IGNORADA, "municipio": MUNICIPIO_IGNORADO,
                "pais": PAIS_IGNORADO, "achou": False}
    return lugar(con, _valor(pessoa, cidade), _valor(pessoa, uf))


def linha_do_nascimento(con: sqlite3.Connection, assento: Any, ato: Any, *,
                        cabeca: dict, ano: int, trimestre: int) -> str:
    """Uma linha de `CARTINF01.TXT`. So LE.

    O QUE SAI DE ONDE:
        o proprio assento   data do nascimento, local, gemeo, DNV
        o REGISTRADO        sexo e o municipio onde nasceu (a naturalidade dele)
        o PAI e a MAE       a UF de naturalidade de cada um
        a MAE              a residencia, e a data de nascimento — de onde sai a
                            idade dela no parto

    A IDADE DA GENITORA E CALCULADA, e nao guardada: guardar a idade faria ela
    envelhecer junto com o banco. O que se guarda e a data, que nao muda.
    """
    p = _pessoas_por_papel(con, assento["id"])
    registrado, pai, mae = p.get("REGISTRADO"), p.get("PAI"), p.get("MAE")
    nasceu = _lugar_da_pessoa(con, registrado,
                              "naturalidade_cidade", "naturalidade_uf")
    mora_a_mae = _lugar_da_pessoa(con, mae, "cidade", "uf")
    nat_pai = _lugar_da_pessoa(con, pai,
                               "naturalidade_cidade", "naturalidade_uf")
    nat_mae = _lugar_da_pessoa(con, mae,
                               "naturalidade_cidade", "naturalidade_uf")
    campos = {
        **cabeca,
        **identificacao(assento, ato, ano=ano, trimestre=trimestre),
        "DATA-NASC": data_ddmmaaaa(_valor(assento, "data_fato")),
        "LOCAL-NASC": _codigo(_valor(assento, "ibge_local_nascimento"), 1),
        "COD-UF-NASC": nasceu["uf"], "COD-MUNIC-NASC": nasceu["municipio"],
        "GEMEO": _codigo(_valor(assento, "ibge_gemeo"), 1),
        "SEXO": sexo(_valor(registrado, "sexo")),
        "COD-UF-NASC-PAI": nat_pai["uf"], "COD-PAIS-NASC-PAI": nat_pai["pais"],
        "COD-UF-NASC-MAE": nat_mae["uf"], "COD-PAIS-NASC-MAE": nat_mae["pais"],
        "COD-UF-RES-MAE": mora_a_mae["uf"],
        "COD-MUNIC-RES-MAE": mora_a_mae["municipio"],
        "COD-PAIS-RES-MAE": mora_a_mae["pais"],
        "IDADE-GENI": idade_da_genitora(_valor(mae, "data_nascimento"),
                                        _valor(assento, "data_fato")),
        "DN": str(_valor(assento, "dnv") or "").strip(),
    }
    return IBGE.montar_linha(IBGE.NASCIMENTO, campos)


def linha_do_casamento(con: sqlite3.Connection, assento: Any, ato: Any, *,
                       cabeca: dict, ano: int, trimestre: int) -> str:
    """Uma linha de `CARTINF02.TXT`. So LE.

    O ESTADO CIVIL DO CASAMENTO NAO E O DO OBITO — a armadilha deste arquivo.
    No casamento `2` e VIUVO; no obito `2` e CASADO. Trocar um pelo outro faria
    o sistema declarar que a viuva era casada, e o IBGE aceitaria calado.
    """
    p = _pessoas_por_papel(con, assento["id"])
    campos = {**cabeca,
              **identificacao(assento, ato, ano=ano, trimestre=trimestre),
              "DATA-CASAM": data_ddmmaaaa(_valor(assento, "data_fato"))}
    for n, papel in ((1, "NUBENTE1"), (2, "NUBENTE2")):
        quem = p.get(papel)
        nasceu = _lugar_da_pessoa(con, quem,
                                  "naturalidade_cidade", "naturalidade_uf")
        mora = _lugar_da_pessoa(con, quem, "cidade", "uf")
        campos.update({
            f"SEXO-CONJ{n}": sexo(_valor(quem, "sexo")),
            f"ESTCIV-CONJ{n}": estado_civil_do_nubente(
                _valor(quem, "estado_civil")),
            f"DT-NASC-CONJ{n}": data_ddmmaaaa(_valor(quem, "data_nascimento")),
            f"COD-UF-NASC-CONJ{n}": nasceu["uf"],
            f"COD-MUNIC-NASC-CONJ{n}": nasceu["municipio"],
            f"COD-PAIS-NASC-CONJ{n}": nasceu["pais"],
            f"COD-UF-RES-CONJ{n}": mora["uf"],
            f"COD-MUNIC-RES-CONJ{n}": mora["municipio"],
            f"COD-PAIS-RES-CONJ{n}": mora["pais"],
        })
    return IBGE.montar_linha(IBGE.CASAMENTO, campos)


def linha_do_obito(con: sqlite3.Connection, assento: Any, ato: Any, *,
                   cabeca: dict, ano: int, trimestre: int) -> str:
    """Uma linha de `CARTINF03.TXT`. So LE.

    A IDADE E A UNIDADE DE TEMPO SAEM JUNTAS, porque so fazem sentido juntas: o
    recem-nascido que morre tem idade em minutos, e `2` sozinho seria dois anos
    quando eram dois dias.
    """
    p = _pessoas_por_papel(con, assento["id"])
    falecido = p.get("FALECIDO")
    nasceu = _lugar_da_pessoa(con, falecido,
                              "naturalidade_cidade", "naturalidade_uf")
    mora = _lugar_da_pessoa(con, falecido, "cidade", "uf")
    idade, tempo = idade_em_anos(_valor(falecido, "data_nascimento"),
                                 _valor(assento, "data_fato"))
    campos = {
        **cabeca,
        **identificacao(assento, ato, ano=ano, trimestre=trimestre),
        "DATA-OBITO": data_ddmmaaaa(_valor(assento, "data_fato")),
        "NATUREZA": _codigo(_valor(assento, "ibge_natureza_obito"), 1),
        "LOCAL": _codigo(_valor(assento, "ibge_local_obito"), 1),
        "COD-UF-RES": mora["uf"], "COD-MUNIC-RES": mora["municipio"],
        "COD-PAIS-RES": mora["pais"],
        "SEXO": sexo(_valor(falecido, "sexo")),
        "IDADE": idade, "TIPO-TEMPO": tempo,
        "EST-CIV": estado_civil_do_falecido(_valor(falecido, "estado_civil")),
        "COD-UF-NASC": nasceu["uf"], "COD-PAIS-NASC": nasceu["pais"],
        "DO": str(_valor(assento, "numero_do") or "").strip(),
    }
    return IBGE.montar_linha(IBGE.OBITO, campos)


def _codigo(valor: Any, largura: int) -> str:
    """Um codigo do catalogo, ou o «sem valor» do IBGE se ele nao foi informado."""
    if valor in (None, ""):
        return _ignorado(largura)
    try:
        return str(int(valor))
    except (TypeError, ValueError):
        return _ignorado(largura)


# O QUE CADA ESPECIE MANDA, E PARA QUE ARQUIVO.
#
#   O casamento religioso vai no MESMO arquivo do civil: o que muda entre os
#   dois e o livro desta casa, e nao a estatistica que o IBGE recolhe.
MONTADOR_DA_ESPECIE: dict[str, tuple[str, Any]] = {
    "NASCIMENTO": ("CARTINF01.TXT", linha_do_nascimento),
    "CASAMENTO": ("CARTINF02.TXT", linha_do_casamento),
    "CASAMENTO_RELIGIOSO": ("CARTINF02.TXT", linha_do_casamento),
    "OBITO": ("CARTINF03.TXT", linha_do_obito),
}


def montar(con: sqlite3.Connection, *, ano: int, trimestre: int,
           config: dict) -> dict:
    """A remessa do trimestre, arquivo por arquivo. So LE.

    O QUE ENTRA E O QUE FOI REGISTRADO NO TRIMESTRE, e nao o que aconteceu
    nele: o registro tardio de um nascimento de 1990 e estatistica do trimestre
    em que foi lavrado. E o proprio IBGE que diz isso, ao pedir o trimestre e o
    ano da PESQUISA junto com o dia e o mes do REGISTRO.

    ELA SAI MESMO INCOMPLETA, e isso e deliberado: a remessa e obrigacao da
    serventia (Lei 6.015/1973, art. 49), e o IBGE tem codigo proprio para «nao
    sei» — nao mandar seria pior que mandar com lacuna. Mas `conferencia` conta
    quantas posicoes sairam como ignorado, porque remessa cheia de nove e
    remessa aceita e inutil, e quem manda precisa saber a diferenca.
    """
    cabeca = cabecalho(config)
    if not 1 <= int(trimestre) <= 4:
        raise IbgeError(
            f"Trimestre {trimestre!r} não existe. Os que existem são 1, 2, 3 e 4.")

    de, ate = _do_trimestre(ano, trimestre)
    arquivos: dict[str, list[str]] = {}
    fora: list[dict] = []
    for assento in con.execute(
            "SELECT a.*, t.data_ato, t.folha, t.rotulo, t.livro_id"
            "  FROM rc_assentos a"
            "  JOIN rc_atos t ON t.assento_id = a.id AND t.tipo = 'REGISTRO'"
            " WHERE t.data_ato >= ? AND t.data_ato <= ?"
            "   AND COALESCE(a.situacao,'ATIVO') <> 'CANCELADO'"
            " ORDER BY a.especie, a.numero", (de, ate)):
        especie = str(assento["especie"] or "").strip().upper()
        alvo = MONTADOR_DA_ESPECIE.get(especie)
        if not alvo:
            # ESPECIE QUE O IBGE NAO RECOLHE — o Livro E inteiro, e o
            # proclamas. Nao e defeito, e nao vira aviso: vira contagem.
            fora.append({"especie": especie, "numero": assento["numero"]})
            continue
        arquivo, monta = alvo
        arquivos.setdefault(arquivo, []).append(
            monta(con, assento, assento, cabeca=cabeca,
                  ano=ano, trimestre=trimestre))

    conferencia = {nome: conferir(linhas, IBGE.ARQUIVOS[nome])
                   for nome, linhas in arquivos.items()}
    return {"ano": int(ano), "trimestre": int(trimestre),
            "de": de, "ate": ate,
            "arquivos": arquivos, "conferencia": conferencia,
            "fora_da_pesquisa": fora,
            "linhas": sum(len(v) for v in arquivos.values())}


def _do_trimestre(ano: Any, trimestre: Any) -> tuple[str, str]:
    """O primeiro e o ultimo dia do trimestre. So calcula.

    EM PYTHON, E NAO NO SQL. `strftime` do SQLite resolveria em uma linha e
    aumentaria o acoplamento ao banco que o projeto conta e limita — e a conta
    aqui e de tres linhas.
    """
    t = int(trimestre)
    primeiro = 1 + 3 * (t - 1)
    ultimo = primeiro + 2
    dias = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    fim = dias[ultimo - 1]
    if ultimo == 2 and (int(ano) % 4 == 0 and
                        (int(ano) % 100 != 0 or int(ano) % 400 == 0)):
        fim = 29
    return f"{int(ano):04d}-{primeiro:02d}-01", f"{int(ano):04d}-{ultimo:02d}-{fim:02d}"


# ------------------------------------------------------- o que ja foi ao IBGE
#
# **ERA UM BURACO DECLARADO NO PAINEL DAS COMUNICACOES.** Este modulo monta o
# mapa desde 28/08/2026 e o sistema **nao guardava o que saiu** — de modo que a
# linha do IBGE mostrava so o prazo, e dizia com todas as letras que o envio nao
# era acompanhado. Buraco declarado e buraco que alguem pode fechar.

ARTIGO = "art. 224 do Código de Normas do TJMA"
PRAZO = "dia 8 de janeiro, abril, julho e outubro"
SANCAO = ("multa de 1 a 5 salários mínimos, «sem prejuízo da ação penal» "
          "(art. 224) — é o único destino desta casa com multa em dinheiro")


def _valor_texto(v: Any) -> str:
    """O valor como texto, e vazio quando não há.

    NUNCA `str(v or "")`: ele come o `0` junto com o `None`, porque zero é falso.
    Já custou dois defeitos neste projeto — a quantidade da remessa do SIRC e a
    fonte desligada dos inacabados.
    """
    if v is None:
        return ""
    return str(v).strip()


def trimestres_com_movimento(con: sqlite3.Connection) -> list[dict]:
    """Os trimestres em que houve ato de Registro Civil. Só lê.

    **A DATA É A DO ASSENTO, E NÃO A DO FATO.** O mapa do IBGE é do que se
    REGISTROU no trimestre — um nascimento de dezembro registrado em janeiro
    entra no mapa de janeiro. Usar a data do fato poria o registro tardio num
    trimestre que já foi entregue, e entrega refeita é conversa com o IBGE.
    """
    con.row_factory = sqlite3.Row
    por_trimestre: dict[tuple, dict] = {}
    for linha in con.execute(
            """SELECT data_ato, origem FROM rc_assentos
                WHERE data_ato IS NOT NULL AND TRIM(data_ato) <> ''
                  AND COALESCE(situacao,'ATIVO') <> 'CANCELADO'"""):
        bruto = _valor_texto(linha["data_ato"])[:10]
        if len(bruto) < 7 or not bruto[:4].isdigit() or not bruto[5:7].isdigit():
            continue
        ano, mes = int(bruto[:4]), int(bruto[5:7])
        if not 1 <= mes <= 12:
            continue
        chave = (ano, (mes + 2) // 3)
        alvo = por_trimestre.setdefault(
            chave, {"ano": chave[0], "trimestre": chave[1],
                    "quantos": 0, "do_sistema": 0})
        alvo["quantos"] += 1
        # DE QUEM E A OBRIGACAO: o que veio do acervo o E-Oficio ja entregou, e
        # afirmar que nao foi seria alarme falso sobre setenta anos de livro.
        if _valor_texto(linha["origem"]).upper() != "EOFICIO":
            alvo["do_sistema"] += 1
    return sorted(por_trimestre.values(),
                  key=lambda x: (x["ano"], x["trimestre"]))


def entregas(con: sqlite3.Connection) -> dict[tuple, dict]:
    """O que já foi ao IBGE, por trimestre. Só lê."""
    con.row_factory = sqlite3.Row
    return {(x["ano"], x["trimestre"]): dict(x)
            for x in con.execute("SELECT * FROM ib_entregas")}


def a_prestar(con: sqlite3.Connection, *, hoje: str) -> list[dict]:
    """Os trimestres que venceram, tiveram movimento desta casa e não têm
    entrega registrada. Só lê.

    **SÓ CONTA O QUE ESTE SISTEMA LAVROU** — ver acima. E **o trimestre que ainda
    está correndo não entra**: cobrar prazo que não venceu é alarme falso, e
    alarme que soa sempre é alarme que ninguém ouve.
    """
    from datetime import date
    bruto = _valor_texto(hoje)[:10]
    if len(bruto) != 10:
        raise ValueError("Diga a data de hoje no formato AAAA-MM-DD.")
    agora = date(int(bruto[:4]), int(bruto[5:7]), int(bruto[8:10]))
    ja = entregas(con)
    faltando = []
    for t in trimestres_com_movimento(con):
        if not t["do_sistema"] or (t["ano"], t["trimestre"]) in ja:
            continue
        # O VENCIMENTO E O DIA 8 DO MES SEGUINTE AO FIM DO TRIMESTRE: o 1o vence
        # em 8 de abril, e o 4o em 8 de JANEIRO DO ANO SEGUINTE.
        mes = t["trimestre"] * 3 + 1
        venc = date(t["ano"] + 1, 1, 8) if mes > 12 else date(t["ano"], mes, 8)
        # `>=`, E NAO `>`: o art. 224 diz «ate o dia 8», e ate o dia 8 inclui o
        # dia 8. Com `>` o trimestre apareceria como atrasado na manha do dia em
        # que ainda da para mandar — e quem le a lista age pelo que ela diz.
        if venc >= agora:
            continue
        faltando.append(dict(t, vencia_em=venc.isoformat(),
                             atrasado_ha=(agora - venc).days))
    return faltando


def quantas_pendentes(con: sqlite3.Connection) -> int:
    """Quantos trimestres devem mapa. Só lê — é o que o painel pergunta."""
    from datetime import date
    return len(a_prestar(con, hoje=date.today().isoformat()))


def registrar_entrega(con: sqlite3.Connection, *, ano: int, trimestre: int,
                      teor: str, quantos: int, agora: str, por: str,
                      canal: str = "", protocolo: str = "") -> int:
    """Registra que o mapa daquele trimestre foi ao IBGE. GRAVA.

    O TEOR CONGELA, com sha256 — é o arquivo que a serventia afirma ter mandado,
    e numa correição é ele que se mostra. O art. 224 pune com multa.
    """
    import hashlib
    if not 1 <= int(trimestre) <= 4:
        raise ValueError("O trimestre vai de 1 a 4.")
    if not _valor_texto(teor):
        raise ValueError("Não dá para registrar a entrega sem o arquivo.")
    ja = con.execute("SELECT id FROM ib_entregas WHERE ano=? AND trimestre=?",
                     (int(ano), int(trimestre))).fetchone()
    if ja:
        raise ValueError(
            f"O {trimestre}º trimestre de {ano} já está registrado como "
            "entregue. Se houve uma segunda remessa, ela é retificação — e essa "
            "conversa é com o IBGE.")
    cur = con.execute(
        """INSERT INTO ib_entregas (ano, trimestre, teor, hash_teor, quantos,
               enviada_em, canal, protocolo, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (int(ano), int(trimestre), teor,
         hashlib.sha256(teor.encode("utf-8")).hexdigest(), int(quantos or 0),
         agora, _valor_texto(canal), _valor_texto(protocolo), agora, por))
    return int(cur.lastrowid)
