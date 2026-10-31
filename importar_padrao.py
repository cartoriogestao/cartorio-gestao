"""O padrão de importação da casa — relato #31 do oficial, 30/08/2026.

    «criar manual e padrão de importação de acervo antigo e preenchimento de
     atos novos, possivelmente por json ou XML (...) para importar atos de
     outros sistemas ou preenchimento de formulários de cadastramento de partes
     ou objeto, seja no RI (matrículas), seja no RCPN (nascimentos, etc)»

O QUE JÁ EXISTIA, E POR QUE NÃO SERVIA COMO PADRÃO
    Esta casa tem **três** importadores que leem JSONL — `ri_import`,
    `notas_import` e `caixa_import` —, e eles funcionaram: foi por eles que
    entraram as 1.701 matrículas, os 4.061 cartões de autógrafo e os 18.396
    lançamentos de caixa.

    **Mas nenhum dos três é um padrão**, e por três motivos medidos:

    1. **Os nomes dos campos são os do E-Ofício.** Quem exporta de outro
       sistema não tem como adivinhar `strNomeConjuge1` nem
       `intCodigoLocalNascimento`.
    2. **Cada um tem o seu conjunto de arquivos**, com nomes próprios —
       `matriculas.jsonl`, `firma_cartao.jsonl`, `protocolo_custas.jsonl` —,
       e nenhuma lista diz quais são nem o que vai dentro.
    3. **Dois dos três não têm tela.** `caixa_import` tem; `ri_import` e
       `notas_import` são função pronta que nenhuma tela chama — o defeito que
       mais se repetiu neste projeto.

    Eles **ficam**, porque leem o que já foi exportado do E-Ofício e essa
    exportação existe. O que este módulo acrescenta é o caminho para **os
    outros sistemas**, que é o que o oficial pediu.

AS DECISÕES DE FORMA, E POR QUÊ

    **JSON, e não XML.** O oficial ofereceu os dois. Os três importadores desta
    casa já usam JSON, e o precedente da casa desempata — mais: um JSON se abre
    no Bloco de Notas e se confere a olho, e um XML de registro civil vem com
    espaços de nome que quem o produz erra na primeira tentativa. **A carga da
    CRC continua em XML**, porque lá quem manda no formato é a Central.

    **Um arquivo só, e não um por tabela.** Sete arquivos JSONL são sete
    chances de mandar seis.

    **Os campos são os NOMES DAS COLUNAS**, sem camada de tradução. Nesta casa
    as colunas já se chamam `nome`, `data_ato`, `cor_raca`,
    `naturalidade_declarada` — traduzir de novo criaria duas listas para
    divergirem no primeiro conserto, que é a `normalizar_nome` pela quarta vez.

    **E A LISTA DOS CAMPOS É MEDIDA DO ESQUEMA, não escrita aqui.** Lista de
    campo escrita à mão noutro arquivo envelhece na tarde em que se escreve —
    foi assim com o menu, com as cargas e com o teste que devia guardar as
    duas. Coluna nova aparece no manual sozinha, no dia em que nasce.

O QUE ESTE MÓDULO NÃO FAZ
    **Não lavra ato, não numera, não sela e não cobra.** Ele traz acervo: o
    registro que chega já tem número, livro e folha, vindos do livro de papel de
    outra serventia ou de outro sistema. Mandar o núcleo achar lugar
    reescreveria a história — é a mesma regra de `acervo_carga`.

    **Não conserta o que vem errado.** Data impossível, campo desconhecido e
    chave repetida são recusados **com o número da linha**, e o resto entra.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from bd_nativo import banco

FORMATO = "CARTORIO_GESTAO_IMPORTACAO"
VERSAO = 1

# O QUE SE PODE IMPORTAR. A tabela é declarada aqui — os CAMPOS são medidos
# do esquema, e não escritos.
#
#   **DOIS DOS DOIS `tela` APONTAVAM PARA ROTA QUE NÃO EXISTE** — achado em
#   07/09/2026 ao atender o relato #40. `atrib_rcpn_ficha` e `ri_matricula`
#   não são endpoints deste sistema; os reais são `rcpn_assento` e `ri_ficha`.
#
#   **Não estourava, porque ninguém lia o campo** — e é isso que o torna
#   perigoso: é valor errado num cadastro que tem cara de autoridade, esperando
#   quem for ligar «depois de importar, abra a ficha». É o mesmo defeito que o
#   `inacabados` teve em duas das nove fontes, e agora tem a mesma guarda:
#   `test_importar_padrao_modelos.py` confere endpoint, template e tabela dos
#   seis.
#
#   **E A LISTA DEIXOU DE SER CURTA POR PEDIDO DO OFICIAL** — relato #40,
#   01/09/2026: «ampliar o importação de outro sistema para demais
#   atribuições — fornecer documentação para importação também do RTD, RCPJ,
#   notas e protesto». A razão de ela ser curta continua escrita para quem
#   chegar: espécie entra quando alguém tem o arquivo, e não «para o caso de».
#   Aqui quem tem o caso é ele.
MODELOS: dict[str, dict] = {
    "RCPN_ASSENTO": {
        "tabela": "rc_assentos",
        "nome": "Assento do Registro Civil (nascimento, casamento, óbito)",
        "tela": "rcpn_assento",
        # O FORMULARIO DO ATO NOVO — segunda metade do relato #31. Ele nao e a
        # mesma coisa que `tela`: aquela e a ficha do que ja existe.
        "formulario": "rcpn_assento_novo",
        "modelo_da_tela": "atrib_rcpn_novo.html",
        # AS PESSOAS DO ASSENTO VIAJAM DENTRO DO REGISTRO — 12/09/2026.
        #
        #   **ATE AQUI O PADRAO GRAVAVA UMA TABELA SO, e isso deixava o assento
        #   entrar ja reprovado pela CRC.** Medido ao construir a importacao do
        #   acervo em `.docx`: a Central le o **sexo** e o **municipio de
        #   nascimento** do REGISTRADO, e a filiacao e o PAI e a MAE de
        #   `rc_pessoas` — nenhum dos tres mora em `rc_assentos`. Sem as
        #   pessoas, todo registro importado cairia em `crc_carga.o_que_falta`
        #   com «o sexo do registrado» e «o municipio de nascimento», que sao
        #   faltas que **retem** o registro.
        #
        #   **E o caminho e este, e nao um segundo arquivo**, por decisao do
        #   oficial: importar o assento sem as pessoas e importa-las depois
        #   seriam dois passos para um fato so, e o dia em que alguem fizesse
        #   o primeiro e esquecesse o segundo ficaria com o livro pela metade.
        "pessoas": {
            "tabela": "rc_pessoas",
            "chave_estrangeira": "assento_id",
            "campo": "pessoas",
            "nome": "as pessoas do assento (registrado, pai, mãe, avós, "
                    "declarante, testemunhas)",
        },
    },
    "RI_MATRICULA": {
        "tabela": "ri_matriculas",
        "nome": "Matrícula do Registro de Imóveis",
        "tela": "ri_ficha",
        "formulario": "ri_nova_matricula",
        "modelo_da_tela": "ri_nova.html",
    },
    # ------------------------------------------------ relato #40
    "RCPJ_RTD_REGISTRO": {
        "tabela": "rg_registros",
        "nome": "Registro do RCPJ ou do RTD",
        "tela": "rcpj_rtd_registro",
        "formulario": "rcpj_rtd_registro_novo",
        "modelo_da_tela": "atrib_registro_novo.html",
    },
    "NOTAS_ATO": {
        "tabela": "nt_atos",
        "nome": "Ato do Tabelionato de Notas (escritura, procuração, ata)",
        "tela": "notas_ato",
        "formulario": "notas_ato_novo",
        "modelo_da_tela": "notas_ato_novo.html",
    },
    "PROTESTO_TITULO": {
        "tabela": "pt_titulos",
        "nome": "Título de protesto",
        "tela": "protesto_titulo",
        "formulario": "protesto_titulo_novo",
        "modelo_da_tela": "atrib_protesto_novo.html",
    },
    "LIVRO3_REGISTRO": {
        "tabela": "ra_registros",
        "nome": "Registro do Livro 3 — Registro Auxiliar",
        "tela": "livro3_registro",
        "formulario": "livro3_registro_novo",
        "modelo_da_tela": "atrib_livro3_novo.html",
    },
}

# O QUE A MÁQUINA CONTROLA, e por isso nunca vem do arquivo.
#
#   Aceitar `id` deixaria o arquivo escolher o número da linha e passar por
#   cima de registro alheio; aceitar `criado_em` deixaria o acervo dizer que
#   entrou ontem. E `origem`/`origem_chave` são o que impede importar duas
#   vezes — quem as escreve é este módulo.
DA_MAQUINA: frozenset[str] = frozenset({
    "id", "criado_em", "criado_por", "atualizado_em", "atualizado_por",
    "importacao_id", "origem", "origem_chave",
})
# E os calculados, que o sistema deriva do que foi gravado. Escrevê-los
# permitiria um `nome_norm` que não corresponde ao `nome` — e a busca por nome
# deixaria de achar a pessoa, calada.
SUFIXOS_DA_MAQUINA: tuple[str, ...] = ("_norm",)

# A CHAVE DE ORIGEM mora numa palavra que não é coluna de nenhuma tabela
# importável — há teste que confere isso, porque no dia em que uma tabela
# ganhasse a coluna `chave` o campo do arquivo passaria a ter dois donos.
CAMPO_DA_CHAVE = "chave"

MARCA_DA_ORIGEM = "IMPORTACAO"

# ONDE O PREENCHIMENTO VINDO DE ARQUIVO ESPERA a tela do ato novo.
#
#   **Uma palavra, num lugar so.** Ela e escrita pela rota que preenche e lida
#   pelas duas telas de ato novo — tres pontas. Escrita a mao em cada uma, uma
#   divergiria num conserto e o preenchimento sumiria **sem ninguem ver**: a
#   tela abriria em branco, que e exatamente como ela abre quando esta certa.
NA_SESSAO = "preencher_de_arquivo"

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")


class ImportacaoError(ValueError):
    """Erro de regra, em português de balcão."""


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


# ------------------------------------------------------------- os campos


def _e_da_maquina(coluna: str) -> bool:
    return (coluna in DA_MAQUINA
            or any(coluna.endswith(s) for s in SUFIXOS_DA_MAQUINA))


def _criado_por_e_fk_de_usuario(con, tabela: str) -> bool:
    """`criado_por` é FK para `users(id)` nesta tabela? Só `ri_matriculas` é.

    **`por` É NOME DE EXIBIÇÃO, NÃO ID** — é `usuario_nome()`, uma string. Em
    `rc_assentos`, `rg_registros`, `nt_atos`, `pt_titulos` e `ra_registros`
    `criado_por` é INTEGER sem FK, e o SQLite guarda a string sem reclamar.
    Só em `ri_matriculas` a coluna tem `FOREIGN KEY(criado_por) REFERENCES
    users(id))`, e ali gravar o nome quebra com `IntegrityError` — achado ao
    importar a matrícula 3110 pela primeira vez nesta casa: toda outra rota
    que grava nessa tabela deixa `criado_por` em `NULL` de propósito, e este
    módulo era o único que tentava outra coisa. Sem essa checagem o defeito
    esperaria o primeiro RI_MATRICULA importado pela tela de verdade.
    """
    return bool(banco(con).valor(
        """SELECT EXISTS (
               SELECT 1 FROM pg_constraint k
                WHERE k.conrelid = to_regclass(%s) AND k.contype = 'f'
                  AND k.confrelid = to_regclass('users')
                  AND (SELECT a.attname FROM pg_attribute a
                        WHERE a.attrelid = k.conrelid
                          AND a.attnum = k.conkey[1]) = 'criado_por') AS fk""",
        (tabela,)))


def _colunas(con, tabela: str) -> list[tuple]:
    """As colunas da tabela, com o que decide obrigatoriedade. Só lê.

    **A ÚNICA CONSULTA AO ESQUEMA DESTE MÓDULO, e ela é a razão de ele
    existir.** A lista de campos que o arquivo aceita é **medida do esquema**, e
    não escrita — escrita à mão, ela envelheceria na tarde em que fosse escrita,
    e o operador prepararia um arquivo com o campo que a tela não lê mais.

    (O nome do comando não se escreve por extenso nesta frase de propósito: o
    varredor de portabilidade conta a palavra onde quer que ela apareça, e já
    bateu na prosa de comentários cinco vezes neste projeto. Aqui não dá para
    ensiná-lo a pular texto sem que ele passe a pular também o SQL que mora em
    aspas triplas — que é onde o acoplamento de verdade se esconde.)

    `SELECT * LIMIT 0` seria portável e não serve: `cursor.description` dá o
    **nome** da coluna e não diz se ela é obrigatória — e é o obrigatório que
    faz a conferência valer. A conta que se paga ao migrar é conhecida:
    `information_schema.columns` responde o mesmo nos dois outros bancos.
    """
    return [(r["nome"], r["obrigatoria"], r["padrao"], r["pk"])
            for r in banco(con).ler(
                """SELECT a.attname AS nome, a.attnotnull AS obrigatoria,
                          pg_get_expr(d.adbin, d.adrelid) AS padrao,
                          EXISTS (SELECT 1 FROM pg_index i
                                   WHERE i.indrelid = a.attrelid
                                     AND i.indisprimary
                                     AND a.attnum = ANY(i.indkey)) AS pk
                     FROM pg_attribute a
                     LEFT JOIN pg_attrdef d
                            ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                    WHERE a.attrelid = to_regclass(%s)
                      AND a.attnum > 0 AND NOT a.attisdropped
                    ORDER BY a.attnum""", (tabela,))]



# No RCPN o acervo antigo veio com poucos campos. A lista do esquema marca
# NOT NULL (serie, especie, nome…), mas exigir tudo na importação manual
# impede abastecer o livro velho. Obrigatório de verdade no arquivo:
# identidade mínima. serie, se faltar, deriva da espécie ao gravar.
RCPN_OBRIGATORIOS_MINIMOS: frozenset[str] = frozenset({"nome", "especie"})
RCPN_PESSOA_OBRIGATORIOS_MINIMOS: frozenset[str] = frozenset({"nome", "papel"})


def campos(con, especie: str) -> list[dict]:
    """Os campos que aquela espécie aceita — **medidos do esquema**. Só lê.

    Cada um diz se é obrigatório e se é data, que são as duas coisas que quem
    prepara o arquivo precisa saber antes de preenchê-lo.
    """
    modelo = MODELOS.get(especie)
    if modelo is None:
        raise ImportacaoError(
            f"Não sei importar «{especie}». Sei importar: "
            + ", ".join(MODELOS) + ".")
    saida = []
    for nome, notnull, padrao, pk in _colunas(con, modelo["tabela"]):
        if _e_da_maquina(nome):
            continue
        do_esquema = bool(notnull) and not pk and padrao is None
        if especie == "RCPN_ASSENTO":
            obrigatorio = nome in RCPN_OBRIGATORIOS_MINIMOS
        else:
            obrigatorio = do_esquema
        saida.append({
            "nome": nome,
            "obrigatorio": obrigatorio,
            "data": nome.startswith("data_") or nome.endswith("_em"),
        })
    return saida


# A ORDEM DA PESSOA É POSICIONAL, e por isso não vem do arquivo: ela já está
# dita pela posição na lista. Aceitá-la daria **duas fontes para o mesmo fato**,
# e no dia em que discordassem quem ganharia seria o acaso.
DA_MAQUINA_NA_PESSOA: frozenset[str] = frozenset({"ordem"})


def campos_da_pessoa(con, especie: str) -> list[dict]:
    """Os campos que cada pessoa aceita — **medidos do esquema**, como os do
    registro. Só lê. Devolve lista vazia para espécie que não tem pessoas."""
    modelo = MODELOS.get(especie)
    if modelo is None:
        raise ImportacaoError(
            f"Não sei importar «{especie}». Sei importar: "
            + ", ".join(MODELOS) + ".")
    quadro = modelo.get("pessoas")
    if not quadro:
        return []
    saida = []
    for nome, notnull, padrao, pk in _colunas(con, quadro["tabela"]):
        if _e_da_maquina(nome) or nome in DA_MAQUINA_NA_PESSOA:
            continue
        if nome == quadro["chave_estrangeira"]:
            continue          # quem a preenche é este módulo, ao gravar
        do_esquema = bool(notnull) and not pk and padrao is None
        if especie == "RCPN_ASSENTO":
            obrigatorio = nome in RCPN_PESSOA_OBRIGATORIOS_MINIMOS
        else:
            obrigatorio = do_esquema
        saida.append({
            "nome": nome,
            "obrigatorio": obrigatorio,
            "data": nome.startswith("data_") or nome.endswith("_em"),
        })
    return saida


def papeis_aceitos(especie_do_ato: Any) -> tuple[str, ...]:
    """Os papéis que aquela espécie de ato admite.

    **A RÉGUA É A DE `rc_assento.PAPEIS_DA_ESPECIE`, E NÃO UMA CÓPIA AQUI.**
    Uma segunda lista divergiria no primeiro conserto — é a `normalizar_nome`
    pela enésima vez —, e a consequência seria dura: o arquivo aceitaria gravar
    um NUBENTE num assento de óbito, e o defeito só apareceria na certidão,
    meses depois. É a mesma razão de o papel sair da espécie, e não do
    formulário.

    Espécie desconhecida devolve tupla vazia, e a conferência recusa dizendo
    quais existem.
    """
    import rc_assento  # local: o padrão não depende do civil para as outras

    return rc_assento.PAPEIS_DA_ESPECIE.get(
        _texto(especie_do_ato).upper(), ())


def _normalizar_nome_da_casa(nome: Any) -> str:
    """A MESMA `normalizar_nome` da casa — importada, e não copiada.

    Ela mora em `pt_schema`, e é de lá que `rc_assento` a importa para lavrar.
    **Copiá-la é o defeito que este projeto já pagou duas vezes**: a cópia
    devolvia MAIÚSCULAS onde a da casa devolve minúsculas, e a busca deixou de
    achar pelo nome sem erro em lugar nenhum. Há teste que confere que as duas
    são **o mesmo objeto**, e não duas parecidas.
    """
    from pt_schema import normalizar_nome

    return normalizar_nome(nome)


# ------------------------------------------------- as colunas que a casa calcula
#
# **A COLUNA QUE A BUSCA CONSULTA NÃO VEM DO ARQUIVO — QUEM A ESCREVE É ESTE
# MÓDULO, E ELE NÃO A ESTAVA ESCREVENDO.** O sufixo `_norm` está em
# `SUFIXOS_DA_MAQUINA` por isso mesmo. Só que «é da máquina» não é o mesmo que
# «a máquina a preenche»: até 15/09/2026 este módulo derivava **só** o
# `nome_norm` das pessoas, e a matrícula do RI que ele importou ficou com
# `livro_norm` **vazio**.
#
# O estrago é o pior tipo, porque é calado e do lado da busca: a ficha existia,
# abria pelo número, e **nenhum filtro de livro a achava** — o filtro compara com
# essa coluna. Medido na produção em 15/09/2026: **1 de 1.982** matrículas sem
# `livro_norm`, e ela é justamente esta — a que este módulo importou (relato
# #55, do balcão, no dia seguinte à importação).
#
# A régua é a mesma do `nome_norm`, e vale para todas: **a função é a da casa,
# importada, e não uma cópia parecida.** `norm_livro` mora em `ri_schema` — é de
# lá que o RI inteiro a tira para gravar, contar e filtrar —, e
# `normalizar_busca` é a que a ficha do imóvel usa ao editar o cadastro. E as
# duas normalizações de nome desta casa **convivem de propósito**
# (`pt_schema.normalizar_nome` devolve minúsculas, `ri_schema.normalizar_busca`
# maiúsculas, cada uma com a sua busca) — por isso a derivação é declarada **por
# tabela**, e não com uma função só para tudo.
#
# **A LISTA É CURTA PORQUE FOI MEDIDA — E ELA NÃO É SÓ DAS TABELAS QUE ESTE
# MÓDULO GRAVA.** Medida na produção em 15/09/2026, coluna por coluna: das
# tabelas do importador, só `ri_matriculas` e `rc_pessoas` têm sufixo `_norm`; e
# a mesma varredura achou `ri_partes.nome_norm` **vazia em 6 de 3.992 partes**
# que têm nome — outro caminho escrevendo a linha sem derivar a coluna. Elas
# entram aqui porque esta tabela é **a única régua** de «como esta casa deriva
# esta coluna», e é dela que sai o conserto do que já está gravado
# (`tools/preencher_colunas_norm.py`), além da entrada nova. Há teste que
# confere a lista contra o esquema e fica vermelho no dia em que outra coluna
# `_norm` nascer sem derivador — em vez de a busca deixar de achar em silêncio,
# que foi como este defeito apareceu.
#
# Cada entrada diz **de que campos** a coluna se compõe e **com que função**.
# Os campos são os mesmos que o resto da casa lê: `imovel_norm` é
# `logradouro + bairro + cidade + descricao_perimetro`, exatamente como em
# `ri_web.ri_editar_matricula` e no preenchimento de `ri_schema`.
def _normalizar_livro_da_casa(livro: Any) -> str:
    """A MESMA `norm_livro` da casa — importada, e não copiada.

    '2-F' e '2F' são o mesmo livro, e é essa função que sabe disso.
    """
    from ri_schema import norm_livro

    return norm_livro(livro)


def _normalizar_busca_da_casa(*campos: Any) -> str:
    """A MESMA `normalizar_busca` da casa — a que a busca do RI compara depois.

    Ela serve às duas formas de nome que o RI guarda normalizado: o do imóvel,
    que se compõe de quatro campos, e o da parte, que é um só. `normalizar_busca`
    devolve MAIÚSCULAS, e é assim que `ri_partes.nome_norm` está gravada — usar
    aqui a `pt_schema.normalizar_nome`, que devolve minúsculas, deixaria a parte
    existindo e não achada pela busca por nome do balcão.
    """
    from ri_schema import normalizar_busca

    return normalizar_busca(" ".join(_texto(c) for c in campos))


DERIVACOES: dict[tuple[str, str], tuple[tuple[str, ...], Any]] = {
    ("ri_matriculas", "livro_norm"): (("livro",), _normalizar_livro_da_casa),
    ("ri_matriculas", "imovel_norm"): (
        ("logradouro", "bairro", "cidade", "descricao_perimetro"),
        _normalizar_busca_da_casa),
    ("ri_partes", "nome_norm"): (("nome",), _normalizar_busca_da_casa),
    ("rc_pessoas", "nome_norm"): (("nome",), _normalizar_nome_da_casa),
}


def _derivar(tabela: str, colunas_da_tabela: Any, linha: dict[str, Any]) -> list[str]:
    """Escreve, no que vai ser gravado, as colunas `_norm` daquela tabela.

    **SEM FONTE NÃO SE ESCREVE NADA.** Coluna derivada de quatro campos vazios
    seria um vazio disfarçado de cálculo: o `NULL` e o `""` se comportam igual
    na busca (nenhum dos dois casa com um padrão que tenha conteúdo), e o `NULL`
    é o que a linha já tinha. O que não se pode é **deixar de derivar quando há
    conteúdo** — e é isso que devolve a lista do que foi escrito, para o teste
    poder mostrar o que o importador calculou.
    """
    existentes = ({c[0] if isinstance(c, (tuple, list)) else c
                   for c in colunas_da_tabela})
    escritas: list[str] = []
    for (t, coluna), (fontes, funcao) in DERIVACOES.items():
        if t != tabela or coluna not in existentes:
            continue
        valores = [_texto(linha.get(c)) for c in fontes]
        if not any(valores):
            continue
        linha[coluna] = funcao(*valores)
        escritas.append(coluna)
    return escritas


def preencher_colunas_derivadas(con) -> dict[str, int]:
    """Preenche as colunas `_norm` VAZIAS cuja fonte está preenchida.

    **É O CONSERTO DO QUE JÁ ESTÁ GRAVADO, e ele não podia ser só do
    importador.** Consertar quem grava impede a próxima ficha de nascer cega;
    não devolve a vista às que já nasceram — e é o balcão que paga por essas,
    procurando uma ficha que o sistema jura que não existe. O relato **#55** é
    exatamente isso: a ficha 3.110 existe, abre pelo número, e **todo filtro de
    livro devolve lista vazia**.

    O QUE ELA NÃO FAZ, E IMPORTA

      · **Não sobrescreve coluna que já tem valor.** Divergir da função da casa
        pode ser ajuste a mão ou a função que mudou: nos dois casos é assunto do
        oficial, e sobrescrever calado apagaria o que alguém decidiu.
      · **Não inventa valor onde não há fonte** — `_derivar` devolve nada com os
        campos de origem vazios, e a linha fica como está.
      · Não toca em data, número, situação nem em nenhuma outra coluna.

    E **É IDEMPOTENTE**, como as outras passadas de abertura do banco
    (`recuperar_cancelados_existentes`, `recuperar_sessoes_interrompidas`):
    coluna já preenchida não se move de novo. Por isso ela roda a cada subida
    sem marcador de «já rodei» — e assim alcança também a linha que alguém
    inserir à mão amanhã, que era como o defeito aparecia.

    A RÉGUA É A DE CIMA, E NÃO UMA CÓPIA. Ela chama a mesma `_derivar` e lê a
    mesma `DERIVACOES`; duas réguas divergiriam no primeiro conserto.

    Devolve `{«tabela.coluna»: quantas linhas foram preenchidas}`, e a lista sai
    inteira (mesmo as de zero) porque quem a lê é uma tela ou um relatório que
    precisa dizer **o que foi conferido**, e não só o que mudou.
    """
    feito: dict[str, int] = {}
    for (tabela, coluna), (fontes, _funcao) in DERIVACOES.items():
        try:
            colunas = _colunas(con, tabela)
        except sqlite3.Error:
            # Tabela que não existe nesta instalação não é defeito: as do
            # importador nascem com os esquemas dos módulos, e a passada roda
            # uma vez por subida, não uma vez por módulo.
            continue
        existentes = {c[0] if isinstance(c, (tuple, list)) else c for c in colunas}
        if coluna not in existentes:
            continue
        chave = f"{tabela}.{coluna}"
        feito[chave] = 0
        if "id" not in existentes:
            continue
        campos = ", ".join(f'"{c}"' for c in fontes)
        bd = banco(con)
        for linha in bd.ler(
                f'SELECT "id", {campos} FROM "{tabela}" '
                f"WHERE COALESCE(\"{coluna}\", '') = '' ORDER BY \"id\""):
            valores = {f: linha[f] for f in fontes}
            if not any(_texto(v) for v in valores.values()):
                continue
            nova = _derivar(tabela, colunas, valores)
            if coluna not in nova:
                continue
            bd.escrever(f'UPDATE "{tabela}" SET "{coluna}"=%s WHERE id=%s',
                        (valores[coluna], linha["id"]))
            feito[chave] += 1
    return feito


def modelo_em_branco(con, especie: str) -> str:
    """Um arquivo de exemplo, com um registro e todos os campos. Só lê.

    **É O MANUAL QUE NÃO ENVELHECE.** Um exemplo escrito à mão num documento
    fica velho no dia em que a coluna nasce; este se monta do esquema de hoje.
    """
    lista = campos(con, especie)
    registro: dict[str, Any] = {CAMPO_DA_CHAVE: "o número deste registro no "
                                                "sistema de onde ele veio"}
    for c in lista:
        registro[c["nome"]] = (
            "AAAA-MM-DD" if c["data"]
            else ("OBRIGATÓRIO" if c["obrigatorio"] else ""))
    # **O EXEMPLO MOSTRA AS PESSOAS, senão ninguém sabe que elas cabem.** O
    # manual que não envelhece vale para elas também: quem prepara o arquivo lê
    # este exemplo, e o que não aparece aqui não é mandado.
    das_pessoas = campos_da_pessoa(con, especie)
    if das_pessoas:
        quadro = MODELOS[especie]["pessoas"]
        pessoa: dict[str, Any] = {}
        for c in das_pessoas:
            pessoa[c["nome"]] = (
                "AAAA-MM-DD" if c["data"]
                else ("OBRIGATÓRIO" if c["obrigatorio"] else ""))
        if "papel" in pessoa:
            pessoa["papel"] = ("OBRIGATÓRIO — um dos papéis que a espécie "
                               "deste ato admite")
        registro[quadro["campo"]] = [pessoa]
    return json.dumps({
        "formato": FORMATO,
        "versao": VERSAO,
        "especie": especie,
        "de_onde_veio": "o nome do sistema ou da serventia de origem",
        "registros": [registro],
    }, ensure_ascii=False, indent=2)


# ------------------------------------------------------------- conferir


def _abrir(texto: str) -> dict:
    try:
        dados = json.loads(texto)
    except (json.JSONDecodeError, TypeError) as erro:
        raise ImportacaoError(
            f"O arquivo não é um JSON válido: {erro}. Abra-o no Bloco de Notas "
            f"e confira se ele começa com «{{» e termina com «}}».") from erro
    if not isinstance(dados, dict):
        raise ImportacaoError(
            "O arquivo tem de ser um objeto JSON, com «formato», «espécie» e "
            "«registros» dentro.")
    if _texto(dados.get("formato")) != FORMATO:
        raise ImportacaoError(
            f"Este arquivo não diz ser do formato «{FORMATO}». Sem isso não dá "
            f"para saber o que ele é — e importar às cegas é como o dado de "
            f"outro sistema entra errado sem ninguém ver.")
    versao = dados.get("versao")
    if versao != VERSAO:
        raise ImportacaoError(
            f"Este arquivo é da versão {versao} do padrão, e este sistema lê a "
            f"versão {VERSAO}.")
    return dados


def _conferir_pessoas(das_pessoas: Any, campos_delas: list[dict],
                      valores: dict) -> tuple[list[dict], str]:
    """As pessoas de um registro. Devolve `(lidas, porque_recusar)`. Só lê.

    **PESSOA RUIM RECUSA O REGISTRO INTEIRO, e isso é deliberado.** No resto
    deste módulo o que não passa é a linha, e as boas entram; aqui não: um
    assento gravado **sem** a filiação que o arquivo trazia é pior que assento
    nenhum, porque ele fica com cara de completo. Quem for corrigir o arquivo
    conserta a pessoa e manda o registro de novo — e o `origem_chave` impede
    que ele entre duas vezes.
    """
    if das_pessoas is None:
        return [], ""
    if not isinstance(das_pessoas, list):
        return [], "o campo «pessoas» não é uma lista"
    if not campos_delas:
        return [], "esta espécie não recebe pessoas"

    conhecidos = {c["nome"] for c in campos_delas}
    obrigatorios = {c["nome"] for c in campos_delas if c["obrigatorio"]}
    aceitos = papeis_aceitos(valores.get("especie"))

    lidas: list[dict] = []
    for i, bruta in enumerate(das_pessoas, start=1):
        if not isinstance(bruta, dict):
            return [], f"a pessoa {i} não é um objeto JSON"
        estranhos = sorted(set(bruta) - conhecidos)
        if estranhos:
            return [], (f"a pessoa {i} tem campo que não existe em pessoa: "
                        + ", ".join(estranhos))
        faltando = sorted(o for o in obrigatorios if not _texto(bruta.get(o)))
        if faltando:
            return [], f"a pessoa {i} está sem: " + ", ".join(faltando)
        papel = _texto(bruta.get("papel")).upper()
        if not aceitos:
            return [], (f"não sei que papéis cabem num ato de "
                        f"«{_texto(valores.get('especie'))}» — confira a "
                        f"espécie do registro")
        if papel not in aceitos:
            return [], (f"a pessoa {i} tem papel «{papel}», que um ato de "
                        f"{_texto(valores.get('especie'))} não admite. "
                        f"Cabem: " + ", ".join(aceitos))
        lidas.append({k: v for k, v in bruta.items() if _texto(v)}
                     | {"papel": papel})
    return lidas, ""


def conferir(con, texto: str, *,
             dispensar: frozenset[str] = frozenset()) -> dict:
    """O que o arquivo traria — **e não grava nada**. Só lê.

    **CONFERIR E IMPORTAR SÃO DOIS PASSOS**, como na remessa da CRA. Cinquenta
    registros que entram sem ninguém olhar são cinquenta linhas para desfazer à
    mão — e aqui não há como desfazer, porque acervo importado vira o livro.
    """
    dados = _abrir(texto)
    especie = _texto(dados.get("especie"))
    modelo = MODELOS.get(especie)
    if modelo is None:
        raise ImportacaoError(
            f"Não sei importar «{especie}». Sei importar: "
            + ", ".join(MODELOS) + ".")

    lista = campos(con, especie)
    conhecidos = {c["nome"] for c in lista}
    obrigatorios = {c["nome"] for c in lista if c["obrigatorio"]}
    de_data = {c["nome"] for c in lista if c["data"]}
    quadro_das_pessoas = modelo.get("pessoas")
    das_pessoas_campos = campos_da_pessoa(con, especie)

    registros = dados.get("registros")
    if not isinstance(registros, list) or not registros:
        raise ImportacaoError(
            "O arquivo não tem nenhum registro em «registros».")

    ja_estao = {r["origem_chave"] for r in banco(con).ler(
        f'SELECT origem_chave FROM "{modelo["tabela"]}" WHERE origem = %s',
        (MARCA_DA_ORIGEM,))}

    entram: list[dict] = []
    recusados: list[dict] = []
    repetidos: list[dict] = []
    vistas: set[str] = set()

    for n, bruto in enumerate(registros, start=1):
        def _recusa(porque: str) -> None:
            recusados.append({"linha": n, "porque": porque,
                              "chave": _texto((bruto or {}).get(
                                  CAMPO_DA_CHAVE) if isinstance(bruto, dict)
                                  else "")})

        if not isinstance(bruto, dict):
            _recusa("não é um objeto JSON")
            continue
        chave = _texto(bruto.get(CAMPO_DA_CHAVE))
        if not chave:
            _recusa(f"está sem «{CAMPO_DA_CHAVE}» — é ela que impede o mesmo "
                    f"registro entrar duas vezes")
            continue
        if chave in vistas:
            _recusa(f"a chave «{chave}» aparece mais de uma vez no arquivo")
            continue
        vistas.add(chave)
        if chave in ja_estao:
            repetidos.append({"linha": n, "chave": chave})
            continue

        valores = {k: v for k, v in bruto.items() if k != CAMPO_DA_CHAVE}
        # AS PESSOAS SAEM DOS VALORES ANTES DA CONFERÊNCIA DOS CAMPOS — elas
        # não são coluna da tabela do registro, e ficariam entre os «campos que
        # esta espécie não conhece».
        das_pessoas = None
        if quadro_das_pessoas:
            das_pessoas = valores.pop(quadro_das_pessoas["campo"], None)
        # CAMPO DESCONHECIDO NAO PASSA CALADO: quem prepara o arquivo acha que
        # mandou o dado, e ele nao entrou em lugar nenhum. Errar o nome de um
        # campo e o erro mais facil de cometer e o mais dificil de perceber.
        estranhos = sorted(set(valores) - conhecidos)
        if estranhos:
            _recusa("tem campo que esta espécie não conhece: "
                    + ", ".join(estranhos))
            continue
        # `dispensar` — 21/10/2026: só a leitura do registro TARDIO o usa,
        # para o «nome» do registrando, que não está em documento nenhum e
        # se digita na tela. Quem lavra continua exigindo.
        faltando = sorted(o for o in obrigatorios - set(dispensar) if not _texto(
            valores.get(o)))
        if faltando:
            _recusa("está sem: " + ", ".join(faltando))
            continue
        datas_ruins = sorted(
            c for c in de_data
            if _texto(valores.get(c)) and not _ISO.match(_texto(valores[c])))
        if datas_ruins:
            _recusa("tem data fora do formato AAAA-MM-DD: "
                    + ", ".join(datas_ruins))
            continue

        pessoas_lidas, porque = _conferir_pessoas(
            das_pessoas, das_pessoas_campos, valores)
        if porque:
            _recusa(porque)
            continue

        entram.append({"linha": n, "chave": chave,
                       "valores": {k: v for k, v in valores.items()
                                   if _texto(v)},
                       "pessoas": pessoas_lidas})

    return {
        "especie": especie,
        "o_que_e": modelo["nome"],
        "tabela": modelo["tabela"],
        "de_onde_veio": _texto(dados.get("de_onde_veio")),
        "lidos": len(registros),
        "entram": entram,
        "recusados": recusados,
        "repetidos": repetidos,
    }


# ------------------------------------------------------------- importar


def importar(con, texto: str, *, agora: str,
             por: str = "") -> dict:
    """Grava o que a conferência aprovou. GRAVA.

    **O QUE FOI RECUSADO NÃO DERRUBA O QUE PASSOU** — é a regra da remessa da
    CRA e da carga do acervo: título ruim não impede os bons de entrar, e o
    motivo de cada recusa fica escrito para quem for corrigir o arquivo.
    """
    quadro = conferir(con, texto)
    tabela = quadro["tabela"]
    colunas_do_registro = _colunas(con, tabela)
    das_pessoas = MODELOS[quadro["especie"]].get("pessoas")
    colunas_da_pessoa = (
        {c[0] for c in _colunas(con, das_pessoas["tabela"])}
        if das_pessoas else set())
    entraram = 0
    pessoas_entraram = 0
    for item in quadro["entram"]:
        valores = dict(item["valores"])
        valores["origem"] = MARCA_DA_ORIGEM
        valores["origem_chave"] = item["chave"]
        valores["criado_em"] = agora
        # Acervo RCPN: serie pode faltar no arquivo antigo — deriva da espécie.
        if (quadro["especie"] == "RCPN_ASSENTO"
                and not _texto(valores.get("serie"))
                and _texto(valores.get("especie"))):
            try:
                import rc_assento as _RC
                serie = _RC.SERIE_DA_ESPECIE.get(
                    _texto(valores.get("especie")).upper())
                if serie:
                    valores["serie"] = serie
            except Exception:
                pass
        if (_texto(por) and "criado_por" in {c[0] for c in
                                            colunas_do_registro}
                and not _criado_por_e_fk_de_usuario(con, tabela)):
            valores["criado_por"] = por
        # **AS COLUNAS QUE A BUSCA CONSULTA SE DERIVAM AQUI** — e não se espera
        # que alguém repare que faltam. É o conserto do relato #55: a matrícula
        # importada entrava com `livro_norm` vazio e sumia de todo filtro de
        # livro, calada.
        _derivar(tabela, colunas_do_registro, valores)
        nomes = list(valores)
        novo_id = banco(con).escrever(
            f'INSERT INTO "{tabela}" ({", ".join(nomes)}) '
            f'VALUES ({", ".join("%s" for _ in nomes)}) RETURNING id',
            [valores[n] for n in nomes])[0]["id"]
        entraram += 1

        for ordem, pessoa in enumerate(item.get("pessoas") or [], start=1):
            linha = dict(pessoa)
            linha[das_pessoas["chave_estrangeira"]] = novo_id
            linha["ordem"] = ordem
            linha["origem"] = MARCA_DA_ORIGEM
            # **A CHAVE DE ORIGEM É DA PESSOA, E NÃO DO ASSENTO** — a lição
            # está escrita neste projeto e custou uma carga inteira: com a
            # chave do assento, os dois nubentes colidiriam no
            # `UNIQUE(origem, origem_chave)` de `rc_pessoas`, **o segundo não
            # entraria, e o contador diria que entrou**.
            linha["origem_chave"] = (
                f'{item["chave"]}:{linha["papel"]}:{ordem}')
            if "criado_em" in colunas_da_pessoa:
                linha["criado_em"] = agora
            # **`nome_norm` SE DERIVA AQUI, COM A FUNÇÃO DA CASA — e deixá-lo
            # vazio seria a falha mais calada deste módulo.** Ele é a coluna
            # que a busca por nome consulta (há índice sobre ela em
            # `rc_schema`), e tanto a lavratura quanto a carga do acervo o
            # preenchem. Pessoa importada sem ele **existe e não é achada por
            # nome** — e ninguém desconfia de uma busca que volta vazia.
            #
            # O arquivo não o manda (o sufixo `_norm` é da máquina, e com razão:
            # um `nome_norm` que não corresponde ao `nome` faria a busca achar
            # outra pessoa). **Quem o escreve é a mesma função do balcão**, e
            # não uma cópia parecida — a lição da `normalizar_nome`, que neste
            # projeto já divergiu e custou a busca inteira.
            #
            # **E DESDE 15/09/2026 ELE NÃO É MAIS UM CASO À PARTE**: as pessoas
            # usam a mesma derivação declarada do registro, para a próxima
            # coluna `_norm` que nascer não depender de alguém lembrar desta
            # linha — foi exatamente assim que o `livro_norm` ficou vazio.
            _derivar(das_pessoas["tabela"], colunas_da_pessoa, linha)
            de_pessoa = [c for c in linha if c in colunas_da_pessoa]
            banco(con).escrever(
                f'INSERT INTO "{das_pessoas["tabela"]}" '
                f'({", ".join(de_pessoa)}) '
                f'VALUES ({", ".join("%s" for _ in de_pessoa)})',
                [linha[c] for c in de_pessoa])
            pessoas_entraram += 1
    quadro["entraram"] = entraram
    quadro["pessoas_entraram"] = pessoas_entraram
    return quadro


# ------------------------------------------------------------- o manual


NOME_DO_MANUAL = "PADRAO_DE_IMPORTACAO.md"


def manual(con, *, pasta: Any = None) -> str:
    """O manual inteiro, para o oficial entregar a quem vai gerar o arquivo.

    **E ELE LEVA A LISTA DE CAMPOS JUNTO, e o documento em disco nao a tem.**
    O documento diz, de proposito, que a lista «esta na tela, sempre atual» —
    porque escrita la dentro ela envelheceria. Isso vale para quem esta AQUI;
    **quem recebe o arquivo esta fora da serventia e nao tem tela nenhuma**, e
    receberia um manual que manda consultar uma coisa que ele nao alcanca.

    Entao o que se baixa e o documento **mais** o que so o banco de hoje sabe:
    os campos de cada especie, com o que e obrigatorio, e um exemplo pronto.

    Sem o documento em disco a funcao **nao devolve meio manual**: ela diz que
    ele falta. Meio manual e pior que nenhum — quem o recebesse prepararia o
    arquivo sem as regras de recusa, e descobriria no dia da importacao.
    """
    from pathlib import Path as _Path

    # A DOCUMENTACAO da casa vem primeiro; a instalação feita do GitHub não a
    # tem e traz a cópia pública em `docs/tecnico/` (23/10/2026) — sem esta
    # segunda porta o manual de importação não saía em instalação nova.
    raiz = _Path(__file__).resolve().parent
    bases = [_Path(pasta)] if pasta else [raiz / "DOCUMENTACAO", raiz / "docs" / "tecnico"]
    caminho = next((b / NOME_DO_MANUAL for b in bases if (b / NOME_DO_MANUAL).is_file()),
                   bases[0] / NOME_DO_MANUAL)
    if not caminho.is_file():
        raise ImportacaoError(
            f"Nao achei o manual em {caminho}. Ele viaja com o sistema, na "
            f"pasta DOCUMENTACAO (ou docs/tecnico) — se ele sumiu, a "
            f"atualizacao nao subiu inteira.")
    partes = [caminho.read_text(encoding="utf-8").rstrip("\n")]

    partes.append("\n\n---\n\n## Os campos de cada especie\n")
    partes.append(
        "**Esta parte e montada do banco desta serventia no momento em que "
        "voce baixou o manual** — por isso ela nao esta escrita no documento, "
        "e por isso este arquivo e mais completo que ele.\n")
    for chave, modelo in MODELOS.items():
        partes.append(f"\n### {chave} — {modelo['nome']}\n")
        partes.append("| campo | e obrigatorio? | forma |")
        partes.append("|---|---|---|")
        for c in campos(con, chave):
            obrig = "**sim**" if c["obrigatorio"] else "nao"
            forma = "data, em AAAA-MM-DD" if c["data"] else "texto"
            partes.append(f"| `{c['nome']}` | {obrig} | {forma} |")
        partes.append(f"\n**Exemplo pronto de {chave}:**\n")
        partes.append("```json")
        partes.append(modelo_em_branco(con, chave))
        partes.append("```")
    return "\n".join(partes) + "\n"


# ------------------------------------------- preencher o FORMULARIO do ato


def campos_da_tela(modelo_da_tela: str, pasta: Any = None) -> set[str]:
    """Os campos que aquele formulário realmente pergunta — **medidos**.

    Lidos do `name=` do próprio modelo de tela, e não escritos numa lista: uma
    lista aqui envelheceria no dia em que a tela ganhasse um campo, e o
    preenchimento passaria a **calar** justamente o campo novo.
    """
    from pathlib import Path as _Path

    base = _Path(pasta) if pasta else _Path(__file__).resolve().parent / "templates"
    caminho = base / modelo_da_tela
    if not caminho.is_file():
        return set()
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r'name="([a-z0-9_]+)"', texto))


def para_formulario(con, texto: str,
                    pasta_das_telas: Any = None) -> dict:
    """Um registro do arquivo, pronto para **preencher a tela**. NÃO GRAVA.

    Segunda metade do relato #31, na opção que o oficial escolheu: o mesmo
    padrão, jogando os dados no formulário em vez de gravar direto.

    **AQUI O ATO NASCE NOVO**, e por isso isto não é importação: ele vai tomar
    número, ocupar folha, selar e cobrar. O arquivo **adianta a digitação** e
    não decide nada — quem lavra confere e assina.

    **UM REGISTRO DE CADA VEZ, e a recusa é deliberada.** Um arquivo com trinta
    preencheria a tela com o primeiro e calaria os vinte e nove; quem mandou
    acharia que os trinta entraram. Para vários, o caminho é a importação.

    **E O QUE NÃO TEM CAMPO NA TELA É DITO**, nunca descartado em silêncio: a
    tela do assento não pergunta tudo o que a tabela guarda, e quem preparou o
    arquivo precisa saber o que ficou de fora — senão ele assina achando que
    aquele dado está lá.
    """
    quadro = conferir(con, texto)
    modelo = MODELOS[quadro["especie"]]

    if quadro["lidos"] > 1:
        raise ImportacaoError(
            f"Este arquivo tem {quadro['lidos']} registros, e preencher "
            f"formulário é um ato de cada vez — com vários, a tela ficaria com o "
            f"primeiro e os outros sumiriam sem ninguém ver. Para trazer todos "
            f"de uma vez, use a importação.")
    if not quadro["entram"]:
        motivo = (quadro["recusados"][0]["porque"] if quadro["recusados"]
                  else "esse registro já está no sistema")
        raise ImportacaoError(f"Não dá para preencher: {motivo}.")

    valores = dict(quadro["entram"][0]["valores"])
    da_tela = campos_da_tela(modelo["modelo_da_tela"], pasta_das_telas)
    sem_campo = sorted(k for k in valores if k not in da_tela) if da_tela else []
    return {
        "especie": quadro["especie"],
        "o_que_e": modelo["nome"],
        "formulario": modelo["formulario"],
        "chave": quadro["entram"][0]["chave"],
        "de_onde_veio": quadro["de_onde_veio"],
        "valores": {k: v for k, v in valores.items()
                    if not da_tela or k in da_tela},
        "sem_campo_na_tela": sem_campo,
    }


# ----------------------------------------------- a fila de pré-cadastros
#
# «queremos dar celeridade no preenchimento dos formularios de registros e
#  importacoes… qual o caminho mais seguro e rapido para importar, sem ser
#  mandar pro robo continuar fazendo o que tem feito?» — o oficial, 11/10/2026
#
# O QUE O ROBÔ FAZIA, E POR QUE ISTO O SUBSTITUI. O robô das digitalizações
# gravava rascunho com o TERMO JÁ REDIGIDO e, depois, lavrava e consertava por
# script, direto no banco. A porta oficial (`para_formulario`) não servia a
# ele: levava à tela só os campos do assento — as pessoas ficavam de fora — e
# um registro por vez.
#
# A FILA RESOLVE AS DUAS COISAS SEM DAR A NINGUÉM A CANETA DO LIVRO:
#   - o arquivo é o padrão da casa (o mesmo do manual), com as PESSOAS dentro
#     e quantos registros houver;
#   - cada registro vira um RASCUNHO da tela de assento novo, com cada pessoa
#     na gaveta dela — e a conferência dos dados já feita;
#   - o TERMO QUE VIER NO ARQUIVO É DESCARTADO: o texto que vai ao livro sai
#     dos campos, pelo modelo da casa, na lavratura (`rc_termo.congelar`);
#   - quem lavra é o balcão, pela tela, com as travas de sempre.
# Quem gera o arquivo — robô, outro sistema, alguém digitando — não lavra,
# não sela, não numera e não toca no banco.

#: Colunas cujo campo na tela tem outro nome (medido em `atrib_rcpn_novo.html`).
CAMPO_DA_TELA_DA_COLUNA = {
    "ibge_local_nascimento": "ibge_local",
    "ibge_natureza_obito": "natureza_obito",
    "ibge_local_obito": "local_obito",
}

#: O que o arquivo pode trazer e a fila não leva à tela, e por quê.
DESCARTADOS_NA_FILA = {
    "teor": "o termo sai do modelo da casa, a partir dos campos, na lavratura",
    "numero": "o número do termo é o livro que dá, na lavratura",
    "matricula": "a matrícula se compõe na lavratura",
    "data_ato": "a data do registro é o dia da lavratura",
    "serie": "a série sai da espécie",
    "situacao": "o assento nasce ativo",
    "livro_volume": "o livro é o aberto no dia da lavratura",
}


def _valores_da_tela(valores: dict, pessoas: list[dict]) -> tuple[dict, list[str]]:
    """O registro do arquivo nos NOMES DOS CAMPOS da tela. Devolve
    `(valores, o_que_ficou_de_fora)`. Só calcula."""
    import rc_assento as RC
    fora: list[str] = []
    tela: dict[str, str] = {}
    for coluna, valor in valores.items():
        if coluna in DESCARTADOS_NA_FILA:
            fora.append(f"{coluna} ({DESCARTADOS_NA_FILA[coluna]})")
            continue
        tela[CAMPO_DA_TELA_DA_COLUNA.get(coluna, coluna)] = _texto(valor)
    usados: set[str] = set()
    for p in pessoas:
        papel = _texto(p.get("papel")).upper()
        prefixo = RC.PREFIXO_DO_PAPEL.get(papel)
        if not prefixo:
            fora.append(f"pessoa {p.get('nome')} (papel {papel} sem gaveta na tela)")
            continue
        if prefixo in usados:
            fora.append(f"pessoa {p.get('nome')} (a tela tem uma gaveta só de "
                        f"{papel.lower()}; ela entra pela ficha depois de lavrar)")
            continue
        usados.add(prefixo)
        for campo in RC.CAMPOS_DA_PESSOA:
            if _texto(p.get(campo)):
                tela[f"{prefixo}_{campo}"] = _texto(p.get(campo))
    return tela, fora


def para_rascunhos(con, texto: str, *, agora: str,
                   por: str = "", dispensar: frozenset[str] = frozenset()) -> dict:
    """Cada registro de assento do arquivo vira um RASCUNHO da tela de assento
    novo, já conferido. ESCREVE — só `rascunhos_de_tela`.

    Não lavra, não numera, não sela, não cobra e não grava assento: o rascunho
    não é ato. O mesmo registro não entra duas vezes (a chave do arquivo vira
    a chave do rascunho), nem depois de lavrado (`RASC.chave_ja_recebida`). O que
    o arquivo trazia e a tela não leva é dito.
    """
    import rascunho_de_tela as RASC
    quadro, itens = _itens_da_fila(con, texto, dispensar=dispensar)
    RASC.init_rascunho_schema(con)
    criados, ja_na_fila = [], []
    for it in itens:
        if RASC.chave_ja_recebida(con, it["chave_rascunho"]):
            ja_na_fila.append(it["chave"])
            continue
        r = RASC.salvar(con, tela="rcpn_assento_novo", dados=it["valores"],
                        titulo=it["titulo"], agora=agora,
                        chave=it["chave_rascunho"], por=por)
        travas = [p for p in r.get("conferencia") or [] if p["gravidade"] == "BLOQUEIA"]
        avisos = [p for p in r.get("conferencia") or [] if p["gravidade"] != "BLOQUEIA"]
        criados.append({"rascunho_id": r["id"], "chave": it["chave"],
                        "nome": it["nome"], "travas": travas, "avisos": avisos,
                        "ficou_de_fora": it["ficou_de_fora"]})
    return {"criados": criados, "ja_na_fila": ja_na_fila,
            "recusados": quadro["recusados"], "repetidos": quadro["repetidos"],
            "de_onde_veio": quadro["de_onde_veio"]}


def _itens_da_fila(con, texto: str, *,
                   dispensar: frozenset[str] = frozenset()) -> tuple[dict, list[dict]]:
    """O arquivo, conferido e traduzido para a tela — o que a fila e a prévia
    têm em comum. SÓ LÊ. Uma função só, para a prévia mostrar exatamente o que
    a fila vai gravar."""
    import rc_assento as RC
    quadro = conferir(con, texto, dispensar=dispensar)
    if quadro["especie"] != "RCPN_ASSENTO":
        raise ImportacaoError(
            "A fila de pré-cadastros é do Registro Civil: o arquivo tem de ser "
            "de «RCPN_ASSENTO».")
    itens = []
    for e in quadro["entram"]:
        pessoas = e.get("pessoas") or []
        valores, fora = _valores_da_tela(e["valores"], pessoas)
        especie = _texto(valores.get("especie")).upper()
        nome = (_texto(valores.get("pessoa_nome")) or _texto(valores.get("nome"))
                or " e ".join(x for x in (_texto(valores.get("nubente1_nome")),
                                          _texto(valores.get("nubente2_nome"))) if x))
        titulo = (f"{RC.NOME_DA_ESPECIE.get(especie, especie)} — {nome} "
                  f"(do arquivo{': ' + quadro['de_onde_veio'] if quadro['de_onde_veio'] else ''})")
        itens.append({"chave": e["chave"], "chave_rascunho": f"arquivo:{e['chave']}",
                      "linha": e.get("linha"), "especie": especie,
                      "nome_especie": RC.NOME_DA_ESPECIE.get(especie, especie),
                      "nome": nome, "titulo": titulo, "valores": valores,
                      "pessoas": [{"papel": _texto(p.get("papel")).upper(),
                                   "nome": _texto(p.get("nome"))} for p in pessoas],
                      "ficou_de_fora": fora})
    return quadro, itens


def previa_da_fila(con, texto: str, *, agora: str) -> dict:
    """O que a fila de pré-cadastros faria com o arquivo — **e não grava
    nada**. SÓ LÊ. Cada registro vem com as pessoas por papel, o que travaria
    a lavratura, o que só avisa e o que ficou de fora.

    A conferência é a mesma que o rascunho faz ao ser salvo
    (`rascunho_de_tela.salvar`), com quem assina posto depois."""
    import rascunho_de_tela as RASC
    import rc_conferencia_dados as CONF
    quadro, itens = _itens_da_fila(con, texto)
    for it in itens:
        try:
            probs = CONF.conferir(CONF.dados_do_formulario(
                it["valores"], data_ato=agora, assina_depois=True))
        except Exception:                               # noqa: BLE001
            probs = []
        it["travas"] = CONF.bloqueios(probs)
        it["avisos"] = CONF.avisos(probs)
        it["ja_na_fila"] = RASC.chave_ja_recebida(con, it["chave_rascunho"])
    return {"itens": itens, "recusados": quadro["recusados"],
            "repetidos": quadro["repetidos"], "lidos": quadro["lidos"],
            "de_onde_veio": quadro["de_onde_veio"]}


# ------------------------------------------- o manual das PARTES do RCPN
#
# «precisamos uma forma facil de baixar o manual de preenchimento desse
#  arquivo, principalmente relativo a dados das partes» — o oficial, 11/10/2026
#
# O manual geral (`manual`) lista as colunas de todas as espécies; quem prepara
# o arquivo do Registro Civil precisa de outra coisa: QUEM é cada papel, em que
# espécie ele cabe, o que vai em cada campo da pessoa e o que faz a lavratura
# recusar. Os papéis, os campos e as gavetas da tela são MEDIDOS (de
# `rc_assento` e do esquema); o que está escrito à mão aqui é só a explicação
# de cada um, e o que não tiver explicação aparece assim mesmo, sem ela.

#: Quem é cada papel, em português de balcão.
QUEM_E_O_PAPEL: dict[str, str] = {
    "REGISTRADO": "a pessoa de quem é o registro de nascimento (ou o natimorto)",
    "FALECIDO": "a pessoa de quem é o registro de óbito",
    "NUBENTE1": "o primeiro cônjuge",
    "NUBENTE2": "o segundo cônjuge",
    "MAE": "a mãe do registrado / falecido (filiação 1)",
    "PAI": "o pai do registrado / falecido (filiação 2)",
    "AVO_MATERNO": "o pai da MÃE",
    "AVO_MATERNA": "a mãe da MÃE",
    "AVO_PATERNO": "o pai do PAI",
    "AVO_PATERNA": "a mãe do PAI",
    "MAE_NUBENTE1": "a mãe do primeiro cônjuge",
    "PAI_NUBENTE1": "o pai do primeiro cônjuge",
    "MAE_NUBENTE2": "a mãe do segundo cônjuge",
    "PAI_NUBENTE2": "o pai do segundo cônjuge",
    "DECLARANTE": "quem declarou o fato no balcão",
    # No NASCIMENTO a segunda testemunha é papel próprio — a do registro
    # tardio e, desde o LD01, também a do parto sem assistência médica.
    "TESTEMUNHA2": "a segunda testemunha do registro tardio (art. 249, II) ou "
                   "do parto sem assistência médica — nunca o próprio registrado",
    "TESTEMUNHA": "testemunha do ato — nunca o próprio registrado, falecido ou "
                  "cônjuge",
    # O LIVRO E — 13/10/2026. No Livro E o REGISTRADO é o emancipado, o
    # interdito, o ausente, o tutelado ou o optante.
    "TUTOR": "o tutor (na emancipação, quando não são os pais; na tutela, o "
             "nomeado)",
    "CURADOR": "o curador nomeado na interdição ou na ausência",
    "REQUERENTE": "quem requereu a interdição ou promoveu o processo de "
                  "ausência",
    "COMPANHEIRO1": "o primeiro companheiro da união estável",
    "COMPANHEIRO2": "o segundo companheiro da união estável",
    "MAE_COMPANHEIRO1": "a mãe do primeiro companheiro",
    "PAI_COMPANHEIRO1": "o pai do primeiro companheiro",
    "MAE_COMPANHEIRO2": "a mãe do segundo companheiro",
    "PAI_COMPANHEIRO2": "o pai do segundo companheiro",
}

#: O que vai em cada campo da pessoa.
O_QUE_VAI_NO_CAMPO: dict[str, str] = {
    "papel": "um dos papéis da tabela da espécie, em MAIÚSCULAS",
    "nome": "o nome completo, como está no documento",
    "nome_pos": "o nome depois do ato (o de casado, no casamento)",
    "sexo": "F, M ou IGNORADO",
    "documento_tipo": "CPF, RG, CNH, CTPS ou PASSAPORTE",
    "documento_numero": "o número; CPF com o dígito certo (o sistema confere)",
    "documento_orgao": "o órgão emissor do RG (ex.: SSP/MA)",
    "profissao": "a profissão declarada",
    "nacionalidade": "ex.: brasileira",
    "naturalidade_cidade": "a cidade onde a pessoa nasceu",
    "naturalidade_uf": "a UF da cidade de nascimento, duas letras",
    "naturalidade_pais": "só se nasceu fora do Brasil",
    "data_nascimento": "AAAA-MM-DD; não pode ser depois do fato",
    "estado_civil": "ex.: solteira, casado, união estável",
    "endereco": "rua e número da residência",
    "bairro": "bairro da residência",
    "cidade": "cidade da residência",
    "uf": "UF da residência",
    "cep": "CEP da residência",
    "idade_no_fato": "a idade NA DATA DO FATO, como declarada (não se calcula)",
}

#: O que faz a lavratura recusar — o código da conferência e a explicação.
O_QUE_TRAVA: tuple[tuple[str, str], ...] = (
    ("TESTEMUNHA_FANTASMA", "a testemunha é o próprio registrado, falecido ou "
                            "cônjuge"),
    ("PAPEL_REPETIDO", "o mesmo papel duas vezes (duas mães, dois registrados); "
                       "só TESTEMUNHA e DECLARANTE podem se repetir"),
    ("SEXO_DO_PAPEL", "mãe com sexo M e pai com sexo F ao mesmo tempo (trocados)"),
    ("CPF_INVALIDO", "CPF cujo dígito verificador não fecha"),
    ("FATO_DEPOIS_DO_ATO", "a data do fato é depois da data do registro"),
    ("NASCEU_DEPOIS_DO_FATO", "a pessoa nasceu depois do fato que se registra"),
    ("DNV_DIFERENTE", "a DNV do campo não é a que está no termo"),
    ("HORA_DIFERENTE", "a hora do campo não é a que está no termo"),
    ("NOME_FORA_DO_TERMO", "o nome do registrado não aparece no termo"),
    ("MARCA_DE_RASCUNHO", "sobrou «[A CONFIRMAR]», «XXX» ou traço de "
                          "preencher no texto"),
)


def _espec_dos_campos_rcpn(con) -> list[str]:
    """As colunas do assento que a tela pergunta — medidas (tela ∩ esquema)."""
    da_tela = campos_da_tela(MODELOS["RCPN_ASSENTO"]["modelo_da_tela"])
    saida = []
    for c in campos(con, "RCPN_ASSENTO"):
        if c["nome"] in DESCARTADOS_NA_FILA:
            continue
        if not da_tela or CAMPO_DA_TELA_DA_COLUNA.get(c["nome"], c["nome"]) in da_tela:
            saida.append(c["nome"])
    if "especie" not in saida:
        saida.insert(0, "especie")
    return saida


def modelo_rcpn(con, especie_do_ato: str) -> str:
    """Um arquivo para PREENCHER, de uma espécie do Registro Civil: um
    registro com os campos que a tela pergunta e **uma pessoa por papel que a
    espécie admite**, todos em branco. SÓ LÊ.

    Campo deixado em branco é ignorado na importação — quem preenche apaga o
    que não usar ou deixa vazio. É o modelo que o robô e quem digita devem
    seguir."""
    import rc_assento as RC
    esp = _texto(especie_do_ato).upper()
    papeis = papeis_aceitos(esp)
    if not papeis:
        raise ImportacaoError(
            f"Não há modelo para «{especie_do_ato}». Há para: "
            + ", ".join(RC.PAPEIS_DA_ESPECIE) + ".")
    registro: dict[str, Any] = {CAMPO_DA_CHAVE: "", "especie": esp}
    for nome in _espec_dos_campos_rcpn(con):
        registro.setdefault(nome, "")
    registro["especie"] = esp
    campos_p = [c["nome"] for c in campos_da_pessoa(con, "RCPN_ASSENTO")]
    registro["pessoas"] = [
        {"papel": p, **{c: "" for c in campos_p if c != "papel"}} for p in papeis]
    return json.dumps({"formato": FORMATO, "versao": VERSAO,
                       "especie": "RCPN_ASSENTO",
                       "de_onde_veio": "",
                       "registros": [registro]}, ensure_ascii=False, indent=2)


def manual_das_partes(con) -> str:
    """O manual de preenchimento do arquivo do Registro Civil, com o foco nas
    PARTES. SÓ LÊ. Montado na hora: os papéis, os campos e as gavetas saem do
    sistema de hoje."""
    import rc_assento as RC
    campos_p = [c["nome"] for c in campos_da_pessoa(con, "RCPN_ASSENTO")]
    L: list[str] = []
    L.append("# Manual de preenchimento — Registro Civil (as partes)\n")
    L.append("Este manual explica como montar o arquivo que entra pela tela "
             "**Registro Civil → Importar pré-cadastros**. Ele é montado pelo "
             "sistema no momento em que é baixado: os papéis e os campos são os "
             "de hoje.\n")
    L.append("## Como o arquivo entra\n")
    L.append("1. O arquivo é um **JSON** (abre no Bloco de Notas), no formato "
             f"`{FORMATO}`, versão {VERSAO}, espécie `RCPN_ASSENTO`.")
    L.append("2. Cada registro vira um **rascunho** do assento novo, já "
             "conferido, com cada pessoa no lugar dela. **Nada é lavrado** pela "
             "importação: o balcão abre o rascunho, confere com o declarante e "
             "lavra pela tela, com as travas de sempre.")
    L.append("3. **Não escreva o termo.** O texto que vai ao livro sai do modelo "
             "da casa, a partir dos campos, na lavratura. Também são ignorados: "
             + "; ".join(f"`{k}` ({v})" for k, v in DESCARTADOS_NA_FILA.items())
             + ".")
    L.append("4. Cada registro precisa de uma `chave` própria (o número da DNV, "
             "do documento digitalizado ou do outro sistema). É ela que impede o "
             "mesmo registro de entrar duas vezes.")
    L.append("5. Campo em branco é ignorado. Datas em **AAAA-MM-DD**; hora em "
             "**HH:MM**.\n")

    L.append("## Os papéis de cada espécie\n")
    L.append("Cada pessoa vai na lista `pessoas` do registro, com o `papel` "
             "dela. A tela tem **uma gaveta por papel**: se vierem duas pessoas "
             "com o mesmo papel (duas testemunhas, por exemplo), a primeira "
             "entra no rascunho e a segunda é avisada para ser lançada na ficha "
             "depois de lavrar.\n")
    for esp, papeis in RC.PAPEIS_DA_ESPECIE.items():
        L.append(f"### {RC.NOME_DA_ESPECIE.get(esp, esp)} — `{esp}`\n")
        L.append("| papel | quem é | campo da tela |")
        L.append("|---|---|---|")
        for p in papeis:
            L.append(f"| `{p}` | {QUEM_E_O_PAPEL.get(p, '')} | "
                     f"`{RC.PREFIXO_DO_PAPEL.get(p, '—')}_…` |")
        L.append("")

    L.append("## Os campos de cada pessoa\n")
    L.append("Obrigatórios: **`nome`** e **`papel`**. Os outros entram quando "
             "o documento os traz — quanto mais completo, menos o balcão digita.\n")
    L.append("| campo | o que vai |")
    L.append("|---|---|")
    for c in campos_p:
        L.append(f"| `{c}` | {O_QUE_VAI_NO_CAMPO.get(c, '')} |")
    L.append("")

    L.append("## Os campos do registro\n")
    L.append("Os que a tela do assento novo pergunta (os demais não precisam "
             "vir):\n")
    L.append(", ".join(f"`{c}`" for c in _espec_dos_campos_rcpn(con)) + ".\n")

    L.append("## O que faz a lavratura recusar\n")
    L.append("O rascunho é aceito mesmo com estes problemas — mas a lavratura "
             "recusa, e o balcão terá de arrumar com o declarante na frente. "
             "Confira antes de mandar:\n")
    for cod, txt in O_QUE_TRAVA:
        L.append(f"- **{txt}** (`{cod}`)")
    L.append("\nE estes só avisam: idade que não bate com as datas, CPF ou "
             "pessoa que o termo não menciona, avô do lado errado (o avô "
             "materno é pai da **mãe**).\n")

    L.append("## Um exemplo preenchido (nascimento, nomes fictícios)\n")
    exemplo = {
        "formato": FORMATO, "versao": VERSAO, "especie": "RCPN_ASSENTO",
        "de_onde_veio": "DNVs digitalizadas — lote de outubro",
        "registros": [{
            "chave": "DNV-30-12345678-9", "especie": "NASCIMENTO",
            "nome": "FULANO EXEMPLO DE TAL", "data_fato": "2026-10-01",
            "hora_fato": "08:30", "dnv": "30-12345678-9",
            "pessoas": [
                {"papel": "REGISTRADO", "nome": "FULANO EXEMPLO DE TAL",
                 "sexo": "M"},
                {"papel": "MAE", "nome": "MARIA EXEMPLO DE TAL", "sexo": "F",
                 "data_nascimento": "1998-03-15", "documento_tipo": "CPF",
                 "documento_numero": "000.000.001-91"},
                {"papel": "PAI", "nome": "JOSE EXEMPLO DE TAL", "sexo": "M"},
                {"papel": "AVO_MATERNA", "nome": "ANA EXEMPLO", "sexo": "F"},
                {"papel": "DECLARANTE", "nome": "MARIA EXEMPLO DE TAL"},
            ],
        }],
    }
    L.append("```json")
    L.append(json.dumps(exemplo, ensure_ascii=False, indent=2))
    L.append("```\n")
    L.append("Os modelos em branco de cada espécie, com uma pessoa por papel, "
             "baixam-se na mesma tela.")
    return "\n".join(L) + "\n"
