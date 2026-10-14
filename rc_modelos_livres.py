"""Os modelos que o escrevente escreve — o módulo Modelos do E-Ofício, copiado.

    «copie o modulo de modelos do e-oficio e vamos implementar no nosso
     sistema» — o oficial, 07/09/2026.

O QUE O MÓDULO DO E-OFÍCIO É, MEDIDO
    Uma tabela (`tbModelosRCPN`, 13 linhas) e uma tela. Cada linha é um
    **documento avulso** que o balcão escreve em volta do ato — «Termo de
    Gêmeos», «Registro Tardio», «Comunicação de Casamento para o Registro de
    Nascimento», «Termo de Alegação de Paternidade» —, guardado em RTF, preso a
    uma espécie (1 nascimento, 2 casamento, 3 óbito), com **claros escritos
    `@nomedocampo`** que o programa troca pelo dado do assento na hora de
    imprimir.

    **São 153 claros distintos e 404 ocorrências nos 13 modelos.** Contados, e
    não somados: o texto de cada um foi extraído do RTF e varrido. Ver
    `DOCUMENTACAO/O_MODULO_DE_MODELOS_DO_EOFICIO.md`.

    > **E a contagem errou DUAS VEZES antes desse número, as duas por defeito
    > da minha própria ferramenta de medição — e as duas devolveram número
    > plausível.**
    >
    > A primeira deu **186**: o varredor de RTF trocava `\\par` por quebra de
    > linha **antes** de `\\pard`, e o `d` que sobrava grudava na palavra
    > seguinte — `@anonascimentodHORA` em vez de `@anonascimento`. **Trinta e um
    > claros que não existem.** Palavra de controle se corta por **fronteira**,
    > e não por prefixo.
    >
    > A segunda deu **155**: contava `@cartorio` e `@gmail`, que são a **cauda
    > dos endereços de e-mail** do rodapé — `cidadeexemplo@cartorio.ch` e
    > `cidadeexemplo.cartorio@gmail.com`. E essa errou mais do que um número: os
    > dois tinham entrado no de-para, e a conversão transformaria o e-mail da
    > serventia em `cidadeexemplo{cartorio}.ch`.
    >
    > **A lição das duas é a mesma: a medição que erra não avisa que errou.**
    > Ela devolve um número com a mesma cara do número certo, e as duas só
    > apareceram ao olhar o texto de um modelo real.

O QUE MUDA AQUI, E POR QUÊ

    **1. O claro é `{campo}`, e não `@campo`.** Esta casa já tem formato de
    claro, com conferidor e razão escrita (`modelos_da_casa.CHAVES`): é o do
    `str.format`, o mesmo dos três termos do livro. Um segundo formato para a
    mesma coisa daria duas conferências para divergirem — e quem escrevesse no
    formato errado descobriria pela recusa, e não antes dela. **Para não custar
    ao oficial os textos que ele já tem, `traduzir_do_eoficio` converte um
    texto colado do E-Ofício** e **diz quais claros não soube converter**, em
    vez de os apagar calado.

    **2. Não é RTF.** Lá o editor é o do Windows; aqui o modelo é texto, e o
    papel sai pelo mesmo caminho dos outros documentos da casa.

    **3. O claro que não tem dado aparece na conferência.** `montar` devolve o
    texto **e a lista do que saiu vazio**. No E-Ofício o claro sem dado vira
    espaço em branco no papel impresso, e ninguém fica sabendo. Aqui a tela
    mostra antes: **conferir e imprimir são dois botões.**

DE ONDE SAI CADA VALOR, E A ARMADILHA QUE ISSO TEM
    **A coluna do assento vem primeiro; o blob do acervo é o recurso.** É a
    regra que `rc_certidao._de` já paga desde 28/08/2026, e aqui ela é ainda
    mais necessária: medido na produção em 07/09/2026, os **244 assentos são
    todos do acervo**, e neles `hora_fato`, `cor_raca`, `causa_morte`,
    `local_sepultamento` e mais dezesseis colunas estão **vazias em 244 de
    244** — o valor está no `dados_json`, com o nome da coluna do E-Ofício
    (`strHoraNascimento`, `strCausaMorte`…).

    Um vocabulário que lesse só as colunas próprias funcionaria perfeitamente
    em todo ato novo e devolveria **documento em branco para o acervo inteiro**,
    que é justamente o que se certifica todo dia.

O QUE ESTE MÓDULO NÃO FAZ
    **Não lavra ato, e não é o termo do livro.** O termo tem lugar próprio
    (`rc_modelos_do_livro`), é montado dos requisitos legais e foi decisão do
    oficial em 30/08/2026 que ele **não** saísse dos modelos do E-Ofício —
    «não utilizaremos os modelos ruins do e-ofício, nem em papel». Isto aqui é
    o outro lado: os papéis avulsos, que é o que aqueles 13 eram.

    **Não seleciona nem numera.** O documento avulso não é ato; se um dia
    algum destes papéis passar a ser ato selado, quem sela é o módulo do selo.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from typing import Any

from rc_modelos_livres_schema import (
    CASAMENTO,
    ESPECIES,
    NASCIMENTO,
    NOME_DA_ESPECIE,
    OBITO,
    TAMANHO_DO_NOME,
)


class ModeloLivreError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


# =========================================================== o que se lê de onde

def _texto(valor: Any) -> str:
    return str(valor if valor is not None else "").strip()


def _dados_do_acervo(assento: dict) -> dict:
    """O blob que a carga guardou — os nomes de coluna do E-Ofício."""
    bruto = assento.get("dados")
    if isinstance(bruto, dict):
        return bruto
    try:
        d = json.loads(assento.get("dados_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _do_assento(ctx: dict, coluna: str, *acervo: str) -> str:
    """A coluna própria; e o blob do acervo como recurso. Só calcula.

    **A ORDEM NÃO É INDIFERENTE.** O ato novo tem a coluna e não tem o blob; o
    ato do acervo tem o blob e a coluna vazia. Ler o blob primeiro faria o
    conserto de um dado no ato importado não aparecer no papel — o escrevente
    corrigiria a hora do nascimento na tela e continuaria imprimindo a antiga.
    """
    valor = _texto(ctx["a"].get(coluna))
    if valor:
        return valor
    for chave in acervo:
        valor = _texto(ctx["d"].get(chave))
        if valor:
            return valor
    return ""


def _da_serventia(ctx: dict, *chaves: str) -> str:
    """Um dado da serventia, aceitando as DUAS grafias que a casa usa.

    `serventia.dados()` devolve `serventia_titular` e `ri_cidade`;
    `atribuicoes_web._servent()` devolve `nome` e `cidade`. As duas são
    chamadoras legítimas, e `rc_termo._como_as_pontes_leem` existe exatamente
    por causa disso. Aqui a tolerância é a mesma, e declarada.
    """
    for chave in chaves:
        valor = _texto(ctx["sv"].get(chave))
        if valor:
            return valor
    return ""


# ------------------------------------------------------------------ as datas

def _data_curta(iso: Any) -> str:
    """dd/mm/aaaa, ou o que veio se não for data."""
    s = _texto(iso)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s


def _parte_da_data(iso: Any, qual: str) -> str:
    s = _texto(iso)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return {"dia": s[8:10], "mes": s[5:7], "ano": s[0:4]}[qual]
    return ""


def _por_extenso(iso: Any) -> str:
    """A data por extenso, pela MESMA função do resto da casa.

    Uma segunda forma de escrever data faria o papel avulso e a certidão do
    mesmo assento discordarem — e os dois saem no mesmo balcão, no mesmo dia.
    """
    from rc_certidao import data_por_extenso
    return data_por_extenso(iso)


# ---------------------------------------------------------------- as pessoas

def _digitos(valor: Any) -> str:
    return re.sub(r"\D+", "", _texto(valor))


def _cpf_de(pessoa: dict) -> str:
    """O CPF, sem chamar RG de CPF. Só calcula.

    É a regra de `rc_certidao._cpf_da_pessoa`, e ela existe porque o acervo tem
    `documento_tipo` em branco: sem o teste dos onze dígitos, um RG de dez
    sairia impresso sob o rótulo CPF.
    """
    tipo = _texto(pessoa.get("documento_tipo")).upper()
    numero = _texto(pessoa.get("documento_numero"))
    if numero and (tipo == "CPF" or (not tipo and len(_digitos(numero)) == 11)):
        return numero
    return ""


def _rg_de(pessoa: dict) -> str:
    tipo = _texto(pessoa.get("documento_tipo")).upper()
    numero = _texto(pessoa.get("documento_numero"))
    if numero and (tipo == "RG" or (not tipo and len(_digitos(numero)) != 11)):
        return numero
    return ""


def _lugar(cidade: Any, uf: Any) -> str:
    c, u = _texto(cidade), _texto(uf)
    if c and u:
        return f"{c}/{u}"
    return c or u


def _sexo_por_extenso(valor: Any) -> str:
    """«masculino» / «feminino». O que não é nenhum dos dois SAI COMO VEIO.

    O acervo grava «Masculino» por extenso e o ato novo grava `M`. Devolver
    vazio para o que não reconheço apagaria o dado do acervo; devolver
    «ignorado» **inventaria uma declaração que ninguém fez** — é a regra de
    `rc_pedidos.SEXO_DA_CASA`.
    """
    v = _texto(valor)
    letra = v[:1].upper()
    if letra == "M" and (len(v) == 1 or v.lower().startswith("mas")):
        return "masculino"
    if letra == "F" and (len(v) == 1 or v.lower().startswith("fem")):
        return "feminino"
    return v


# ======================================================== o vocabulário de claros

def claro(nome: str, rotulo: str, vem_de: Callable[[dict], str], *,
          de_onde: str = "") -> dict:
    """Um claro do modelo: o nome que se escreve, o rótulo e DE ONDE ele sai."""
    return {"nome": nome, "rotulo": rotulo, "de_onde": de_onde,
            "vem_de": vem_de}


# ------------------------------------------------- os claros de uma pessoa
#
# **UM CAMPO POR COLUNA QUE EXISTE, E NENHUM A MAIS.** Cada linha desta tabela
# foi conferida contra o `PRAGMA table_info(rc_pessoas)` da producao em
# 07/09/2026 — nao ha aqui campo que eu tenha suposto.
#
# `idade_no_fato` e `documento_orgao` EXISTEM na tabela e estao **vazias em
# todas as 1.084 pessoas**. Elas entram assim mesmo, porque coluna vazia hoje e
# coluna que o ato novo preenche amanha — e o claro que sai vazio **aparece na
# conferencia**, que e o lugar onde isso se ve.
CAMPOS_DA_PESSOA: tuple[tuple[str, str, Callable[[dict], str]], ...] = (
    ("nome", "Nome", lambda p: _texto(p.get("nome"))),
    ("nome_pos", "Nome que passou a usar", lambda p: _texto(p.get("nome_pos"))),
    ("cpf", "CPF", _cpf_de),
    ("rg", "RG", _rg_de),
    ("orgao", "Órgão do documento", lambda p: _texto(p.get("documento_orgao"))),
    ("sexo", "Sexo", lambda p: _sexo_por_extenso(p.get("sexo"))),
    ("profissao", "Profissão", lambda p: _texto(p.get("profissao"))),
    ("nacionalidade", "Nacionalidade",
     lambda p: _texto(p.get("nacionalidade"))),
    ("naturalidade", "Naturalidade",
     lambda p: _lugar(p.get("naturalidade_cidade"), p.get("naturalidade_uf"))),
    # **A NATURALIDADE PARTIDA EXISTE PORQUE AS COLUNAS SÃO DUAS.** Os modelos
    # do E-Ofício pedem o município e a UF em campos separados do formulário
    # («NATURALIDADE» e «UF»), e converter os dois para o claro junto
    # imprimiria «Cidade Exemplo/MA» nas duas caixas.
    ("naturalidade_cidade", "Naturalidade — município",
     lambda p: _texto(p.get("naturalidade_cidade"))),
    ("naturalidade_uf", "Naturalidade — UF",
     lambda p: _texto(p.get("naturalidade_uf"))),
    ("pais", "País de naturalidade",
     lambda p: _texto(p.get("naturalidade_pais"))),
    ("data_nascimento", "Data de nascimento",
     lambda p: _data_curta(p.get("data_nascimento"))),
    ("data_nascimento_extenso", "Data de nascimento por extenso",
     lambda p: _por_extenso(p.get("data_nascimento"))),
    ("idade", "Idade no fato", lambda p: _texto(p.get("idade_no_fato"))),
    ("estado_civil", "Estado civil", lambda p: _texto(p.get("estado_civil"))),
    ("endereco", "Logradouro", lambda p: _texto(p.get("endereco"))),
    ("bairro", "Bairro", lambda p: _texto(p.get("bairro"))),
    ("cidade", "Cidade onde mora", lambda p: _texto(p.get("cidade"))),
    ("uf", "UF onde mora", lambda p: _texto(p.get("uf"))),
    ("cep", "CEP", lambda p: _texto(p.get("cep"))),
)

# **A QUALIFICACAO INTEIRA E A DA CASA**, e nao uma segunda montagem daqui.
# `rc_termo.qualificacao` e a que o termo do livro usa; escrever outra faria o
# papel avulso qualificar a mesma pessoa de um jeito e o termo de outro.
CAMPO_QUALIFICACAO = ("qualificacao", "Qualificação inteira")

# Os papeis que so tem NOME, medido: nas 631 linhas de avo da producao, todas
# as colunas de qualificacao estao vazias — o E-Oficio guardava so o nome
# deles (`tbProgenitor`). Oferecer «profissao do avo materno» seria oferecer um
# claro que sai vazio em 100% dos casos.
PAPEIS_SO_COM_NOME: frozenset[str] = frozenset(
    {"AVO_PATERNO", "AVO_PATERNA", "AVO_MATERNO", "AVO_MATERNA"})

# Os papeis de cada especie, com o prefixo que o claro usa.
PAPEIS_DA_ESPECIE: dict[str, tuple[tuple[str, str, str], ...]] = {
    # **OS RÓTULOS SÃO OS QUE O OFICIAL ESCOLHEU EM 30/08/2026** — «filiação 1
    # e 2, indicando a 1 para mãe entre parênteses (mera indicação)». Escrever
    # «o pai» aqui faria esta tela falar uma língua e as outras outra, no mesmo
    # assento; e há casais do mesmo sexo, para quem «pai»/«mãe» não descreve.
    # **As CHAVES continuam `pai_`/`mae_`**, porque são as gravadas.
    NASCIMENTO: (
        ("REGISTRADO", "registrado", "O registrado"),
        ("MAE", "mae", "Filiação 1 (mãe)"),
        ("PAI", "pai", "Filiação 2 (pai)"),
        ("DECLARANTE", "declarante", "O declarante"),
        ("AVO_PATERNO", "avo_paterno", "O avô paterno"),
        ("AVO_PATERNA", "avo_paterna", "A avó paterna"),
        ("AVO_MATERNO", "avo_materno", "O avô materno"),
        ("AVO_MATERNA", "avo_materna", "A avó materna"),
    ),
    # **A FILIAÇÃO DO CASAMENTO É DE CADA NUBENTE, e são quatro pessoas.** Os
    # papéis são os de `rc_assento.PAPEIS_DA_ESPECIE`, e a distinção importa:
    # os pais de um sob o rótulo do outro é o erro que a certidão de casamento
    # existe para não cometer.
    #
    #   **E NOS 20 CASAMENTOS DO ACERVO ELES NÃO EXISTEM** — medido em
    #   07/09/2026: lá há 12 `PAI` e 12 `MAE` avulsos, que **não dizem de qual
    #   nubente são**. Cair neles seria justamente atribuir errado, e por isso
    #   **não há queda**: nesses assentos os quatro claros saem vazios, e vazio
    #   aparece na conferência.
    CASAMENTO: (
        ("NUBENTE1", "nubente1", "O 1º nubente"),
        ("NUBENTE2", "nubente2", "O 2º nubente"),
        ("MAE_NUBENTE1", "mae_nubente1", "Filiação 1 do 1º nubente"),
        ("PAI_NUBENTE1", "pai_nubente1", "Filiação 2 do 1º nubente"),
        ("MAE_NUBENTE2", "mae_nubente2", "Filiação 1 do 2º nubente"),
        ("PAI_NUBENTE2", "pai_nubente2", "Filiação 2 do 2º nubente"),
    ),
    OBITO: (
        ("FALECIDO", "falecido", "O falecido"),
        ("DECLARANTE", "declarante", "O declarante"),
        ("MAE", "mae", "Filiação 1 (mãe)"),
        ("PAI", "pai", "Filiação 2 (pai)"),
    ),
}


def _pessoa(ctx: dict, papel: str) -> dict:
    return ctx["quem"].get(papel) or {}


# **A FÁBRICA É FUNÇÃO, E NÃO LAMBDA CHAMADA NA HORA.** O `lambda` escrito
# dentro do laço fecha sobre a VARIÁVEL do laço, e não sobre o valor dela: os
# oito papéis acabariam todos lendo o último. É o defeito que dá papel do avô
# materno no lugar do pai, sem erro em lugar nenhum.
def _ler_da_pessoa(papel: str, como_ler: Callable[[dict], str]):
    def vem_de(ctx: dict) -> str:
        return como_ler(_pessoa(ctx, papel))
    return vem_de


def _qualificacao_da_pessoa(papel: str):
    def vem_de(ctx: dict) -> str:
        return _qualificacao(_pessoa(ctx, papel))
    return vem_de


def _claros_das_pessoas(especie: str) -> tuple[dict, ...]:
    """Monta os claros de pessoa da espécie. Só calcula."""
    saida: list[dict] = []
    for papel, prefixo, rotulo_do_papel in PAPEIS_DA_ESPECIE[especie]:
        campos = CAMPOS_DA_PESSOA
        if papel in PAPEIS_SO_COM_NOME:
            campos = tuple(c for c in CAMPOS_DA_PESSOA if c[0] == "nome")
        for sufixo, rotulo, como_ler in campos:
            saida.append(claro(
                f"{prefixo}_{sufixo}", f"{rotulo_do_papel} — {rotulo}",
                _ler_da_pessoa(papel, como_ler),
                de_onde=f"`rc_pessoas` de papel {papel}"))
        if papel not in PAPEIS_SO_COM_NOME:
            sufixo, rotulo = CAMPO_QUALIFICACAO
            saida.append(claro(
                f"{prefixo}_{sufixo}", f"{rotulo_do_papel} — {rotulo}",
                _qualificacao_da_pessoa(papel),
                de_onde="montada por `rc_termo.qualificacao`"))
    return tuple(saida)


def _qualificacao(pessoa: dict) -> str:
    from rc_termo import qualificacao
    return _texto(qualificacao(pessoa) if pessoa else "")


def _juntar(ctx: dict, *papeis: str) -> str:
    """Os nomes daquelas pessoas, na ordem, separados por « e »."""
    nomes = [_texto(_pessoa(ctx, p).get("nome")) for p in papeis]
    nomes = [n for n in nomes if n]
    if len(nomes) <= 1:
        return nomes[0] if nomes else ""
    return " e ".join(nomes)


def _todos_de(ctx: dict, papel: str) -> str:
    """Todos os que têm aquele papel — testemunhas são mais de uma."""
    nomes = [_texto(p.get("nome")) for p in ctx["todas"] if p.get("papel") == papel]
    nomes = [n for n in nomes if n]
    if len(nomes) <= 1:
        return nomes[0] if nomes else ""
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


# --------------------------------------------------------- os claros comuns

CLAROS_COMUNS: tuple[dict, ...] = (
    claro("nome", "Nome de quem é o assento",
          lambda ctx: _texto(ctx["a"].get("nome")), de_onde="`rc_assentos.nome`"),
    claro("matricula", "Matrícula de 32 dígitos",
          lambda ctx: _matricula(ctx["a"].get("matricula")),
          de_onde="`rc_assentos.matricula`"),
    claro("livro", "Livro",
          lambda ctx: _do_assento(ctx, "livro_volume", "strLivro"),
          de_onde="`livro_volume`, ou `strLivro` do acervo"),
    claro("folha", "Folha",
          lambda ctx: _texto(ctx["ato"].get("folha")) or _texto(ctx["d"].get("intFolha")),
          de_onde="a folha do ato de REGISTRO"),
    claro("selo", "Selo do ato",
          lambda ctx: _texto(ctx["ato"].get("selo")),
          de_onde="`rc_atos.selo` do ato de REGISTRO"),
    claro("termo", "Número do termo",
          lambda ctx: _texto(ctx["a"].get("numero")) or _texto(ctx["d"].get("intNumeroRegistro")),
          de_onde="`rc_assentos.numero`"),
    claro("data_do_registro", "Data do registro",
          lambda ctx: _data_curta(ctx["a"].get("data_ato")),
          de_onde="`rc_assentos.data_ato`"),
    claro("data_do_registro_extenso", "Data do registro por extenso",
          lambda ctx: _por_extenso(ctx["a"].get("data_ato")),
          de_onde="`data_ato`, pela função da casa"),
    claro("data_de_hoje", "Data de hoje", lambda ctx: _data_curta(ctx["hoje"]),
          de_onde="o dia da emissão"),
    claro("data_de_hoje_extenso", "Data de hoje por extenso",
          lambda ctx: _por_extenso(ctx["hoje"]), de_onde="o dia da emissão"),
    claro("cartorio", "Nome da serventia",
          lambda ctx: _da_serventia(ctx, "serventia_titular", "nome"),
          de_onde="as configurações"),
    claro("cidade", "Município da serventia",
          lambda ctx: _da_serventia(ctx, "ri_cidade", "cidade"),
          de_onde="as configurações"),
    claro("uf", "UF da serventia",
          lambda ctx: _da_serventia(ctx, "ri_uf", "uf"),
          de_onde="as configurações"),
    claro("estado", "Estado da serventia por extenso",
          lambda ctx: _da_serventia(ctx, "ri_estado", "estado"),
          de_onde="as configurações"),
    claro("endereco_do_cartorio", "Endereço da serventia",
          lambda ctx: _da_serventia(ctx, "endereco_completo", "serventia_endereco"),
          de_onde="as configurações"),
    claro("telefone_do_cartorio", "Telefone da serventia",
          lambda ctx: _da_serventia(ctx, "serventia_telefone"),
          de_onde="as configurações"),
    claro("email_do_cartorio", "E-mail da serventia",
          lambda ctx: _da_serventia(ctx, "serventia_email"),
          de_onde="as configurações"),
    claro("registrador", "Quem assina",
          lambda ctx: _da_serventia(ctx, "registrador", "serventia_titular"),
          de_onde="a substituta se houver, senão o titular"),
    claro("funcao_do_registrador", "Em que qualidade assina",
          lambda ctx: _da_serventia(ctx, "titulo", "serventia_titulo"),
          de_onde="as configurações"),
)


def _matricula(valor: Any) -> str:
    """Os 32 dígitos na forma que a certidão desta casa já imprime."""
    from rc_certidao_quadro import formatar_matricula
    return formatar_matricula(valor)


# ------------------------------------------------------ os claros do NASCIMENTO
#
# As chaves do acervo sao as MEDIDAS em `dados_json` na producao, com a
# quantidade de assentos em que cada uma aparece anotada ao lado.
CLAROS_NASCIMENTO: tuple[dict, ...] = (
    claro("data_do_nascimento", "Data do nascimento",
          lambda ctx: _data_curta(ctx["a"].get("data_fato")),
          de_onde="`rc_assentos.data_fato`"),
    claro("data_do_nascimento_extenso", "Data do nascimento por extenso",
          lambda ctx: _por_extenso(ctx["a"].get("data_fato")),
          de_onde="`data_fato`, pela função da casa"),
    claro("dia_do_nascimento", "Dia",
          lambda ctx: _parte_da_data(ctx["a"].get("data_fato"), "dia"),
          de_onde="`data_fato`"),
    claro("mes_do_nascimento", "Mês",
          lambda ctx: _parte_da_data(ctx["a"].get("data_fato"), "mes"),
          de_onde="`data_fato`"),
    claro("ano_do_nascimento", "Ano",
          lambda ctx: _parte_da_data(ctx["a"].get("data_fato"), "ano"),
          de_onde="`data_fato`"),
    claro("hora_do_nascimento", "Hora do nascimento",
          lambda ctx: _do_assento(ctx, "hora_fato", "strHoraNascimento"),
          de_onde="`hora_fato`, ou `strHoraNascimento` do acervo (192/192)"),
    claro("local_do_nascimento", "Nome do local",
          lambda ctx: _do_assento(ctx, "local_fato_nome", "strNomeLocal"),
          de_onde="`local_fato_nome`, ou `strNomeLocal` do acervo (191/192)"),
    claro("endereco_do_nascimento", "Endereço do local",
          lambda ctx: _do_assento(ctx, "local_fato_endereco", "strLN_endereco"),
          de_onde="`local_fato_endereco`, ou `strLN_endereco` do acervo"),
    claro("cor_ou_raca", "Cor ou raça",
          lambda ctx: _do_assento(ctx, "cor_raca", "strRacaCor"),
          de_onde="`cor_raca`, ou `strRacaCor` do acervo"),
    claro("dnv", "Declaração de Nascido Vivo",
          lambda ctx: _do_assento(ctx, "dnv", "strDeclaracaoNascidoVivo"),
          de_onde="`dnv`, ou `strDeclaracaoNascidoVivo` do acervo (61/192)"),
    claro("cpf_do_registrado", "CPF do registrado",
          lambda ctx: (_cpf_de(_pessoa(ctx, "REGISTRADO"))
                       or _do_assento(ctx, "cpf_registrado", "strCPF")),
          de_onde="a pessoa, ou `strCPF` do acervo (103/192)"),
    claro("naturalidade_declarada", "Naturalidade declarada",
          lambda ctx: _do_assento(ctx, "naturalidade_declarada"),
          de_onde="`naturalidade_declarada` — art. 54, § 4º"),
    claro("ordem_de_gemeo", "Ordem de nascimento do gêmeo",
          lambda ctx: _texto(ctx["a"].get("gemeo_ordem")),
          de_onde="`gemeo_ordem` — art. 234"),
    claro("avos_paternos", "Avós paternos",
          lambda ctx: _juntar(ctx, "AVO_PATERNO", "AVO_PATERNA"),
          de_onde="as pessoas de papel AVO_PATERNO e AVO_PATERNA"),
    claro("avos_maternos", "Avós maternos",
          lambda ctx: _juntar(ctx, "AVO_MATERNO", "AVO_MATERNA"),
          de_onde="as pessoas de papel AVO_MATERNO e AVO_MATERNA"),
    claro("filiacao", "Filiação — os dois nomes",
          lambda ctx: _juntar(ctx, "PAI", "MAE"),
          de_onde="as pessoas de papel PAI e MAE"),
)

# -------------------------------------------------------- os claros do CASAMENTO
CLAROS_CASAMENTO: tuple[dict, ...] = (
    claro("data_do_casamento", "Data do casamento",
          lambda ctx: _data_curta(ctx["a"].get("data_fato")),
          de_onde="`rc_assentos.data_fato`"),
    claro("data_do_casamento_extenso", "Data do casamento por extenso",
          lambda ctx: _por_extenso(ctx["a"].get("data_fato")),
          de_onde="`data_fato`, pela função da casa"),
    claro("hora_do_casamento", "Hora da celebração",
          lambda ctx: _do_assento(ctx, "hora_fato", "strHoraCelebracao"),
          de_onde="`hora_fato`, ou `strHoraCelebracao` do acervo"),
    claro("regime_de_bens", "Regime de bens",
          lambda ctx: _do_assento(ctx, "regime_bens", "strRegimeCasamento"),
          de_onde="`regime_bens`, ou `strRegimeCasamento` do acervo (20/20)"),
    claro("local_da_celebracao", "Local da celebração",
          lambda ctx: _do_assento(ctx, "local_fato_nome", "strDescricaoLocal"),
          de_onde="`local_fato_nome`, ou `strDescricaoLocal` do acervo"),
    # **SÓ O ACERVO TEM O CELEBRANTE**, e isso está medido: não há coluna para
    # ele em `rc_assentos`. O claro existe para servir aos 20 casamentos
    # importados; num casamento lavrado aqui ele sai vazio — e vazio aparece na
    # conferência, que é onde o escrevente decide.
    claro("celebrante", "Quem celebrou",
          lambda ctx: _texto(ctx["d"].get("strNomeCelebrante")),
          de_onde="`strNomeCelebrante` do acervo — **não há coluna própria**"),
    claro("testemunhas", "Testemunhas",
          lambda ctx: _todos_de(ctx, "TESTEMUNHA"),
          de_onde="as pessoas de papel TESTEMUNHA"),
    claro("nubentes", "Os dois nubentes",
          lambda ctx: _juntar(ctx, "NUBENTE1", "NUBENTE2"),
          de_onde="as pessoas de papel NUBENTE1 e NUBENTE2"),
    claro("filiacao_nubente1", "Filiação do 1º nubente — os dois nomes",
          lambda ctx: _juntar(ctx, "MAE_NUBENTE1", "PAI_NUBENTE1"),
          de_onde="MAE_NUBENTE1 e PAI_NUBENTE1 — **vazio no acervo**"),
    claro("filiacao_nubente2", "Filiação do 2º nubente — os dois nomes",
          lambda ctx: _juntar(ctx, "MAE_NUBENTE2", "PAI_NUBENTE2"),
          de_onde="MAE_NUBENTE2 e PAI_NUBENTE2 — **vazio no acervo**"),
)

# ------------------------------------------------------------ os claros do ÓBITO
CLAROS_OBITO: tuple[dict, ...] = (
    claro("data_do_obito", "Data do óbito",
          lambda ctx: _data_curta(ctx["a"].get("data_fato")),
          de_onde="`rc_assentos.data_fato`"),
    claro("data_do_obito_extenso", "Data do óbito por extenso",
          lambda ctx: _por_extenso(ctx["a"].get("data_fato")),
          de_onde="`data_fato`, pela função da casa"),
    claro("hora_do_obito", "Hora do óbito",
          lambda ctx: _do_assento(ctx, "hora_fato", "strHoraObito"),
          de_onde="`hora_fato`, ou `strHoraObito` do acervo (31/31)"),
    claro("causa_da_morte", "Causa da morte",
          lambda ctx: _do_assento(ctx, "causa_morte", "strCausaMorte"),
          de_onde="`causa_morte`, ou `strCausaMorte` do acervo (31/31)"),
    claro("local_do_obito", "Local do óbito",
          lambda ctx: _do_assento(ctx, "local_fato_nome", "strNomeLocalObito"),
          de_onde="`local_fato_nome`, ou `strNomeLocalObito` do acervo (31/31)"),
    claro("municipio_do_obito", "Município do óbito",
          lambda ctx: _lugar(ctx["d"].get("strMunicipioFalecimento"),
                             ctx["d"].get("strUFFalecimento")),
          de_onde="`strMunicipioFalecimento` do acervo (31/31)"),
    claro("local_do_sepultamento", "Local do sepultamento",
          lambda ctx: _do_assento(ctx, "local_sepultamento", "strLocalSepultamento"),
          de_onde="`local_sepultamento`, ou o do acervo (15/31)"),
    claro("atestante", "Médico atestante",
          lambda ctx: _do_assento(ctx, "atestante", "strAtestantePrimario"),
          de_onde="`atestante`, ou `strAtestantePrimario` do acervo (25/31)"),
    claro("documento_do_atestante", "CRM do atestante",
          lambda ctx: _do_assento(ctx, "atestante_documento",
                                  "strCRMAtestantePrimario"),
          de_onde="`atestante_documento`, ou o CRM do acervo (8/31)"),
    claro("declaracao_de_obito", "Número da Declaração de Óbito",
          lambda ctx: _do_assento(ctx, "numero_do", "strNumeroDeclaracaoObito"),
          de_onde="`numero_do`, ou o do acervo (31/31)"),
    claro("titulo_de_eleitor", "Título de eleitor",
          lambda ctx: _do_assento(ctx, "titulo_eleitor", "strTituloEleitor"),
          de_onde="`titulo_eleitor`, ou o do acervo (18/31)"),
    claro("cor_ou_raca", "Cor ou raça",
          lambda ctx: _do_assento(ctx, "cor_raca", "strRacaCor"),
          de_onde="`cor_raca`, ou `strRacaCor` do acervo (31/31)"),
    claro("idade_do_falecido", "Idade do falecido",
          lambda ctx: (_texto(_pessoa(ctx, "FALECIDO").get("idade_no_fato"))
                       or _texto(ctx["d"].get("intIdade"))),
          de_onde="a pessoa, ou `intIdade` do acervo (31/31)"),
    claro("cpf_do_falecido", "CPF do falecido",
          lambda ctx: (_cpf_de(_pessoa(ctx, "FALECIDO"))
                       or _texto(ctx["d"].get("strCPF"))),
          de_onde="a pessoa, ou `strCPF` do acervo (31/31)"),
    claro("filiacao", "Filiação — os dois nomes",
          lambda ctx: _juntar(ctx, "PAI", "MAE"),
          de_onde="as pessoas de papel PAI e MAE"),
    claro("endereco_do_obito", "Endereço do óbito",
          lambda ctx: _do_assento(ctx, "local_fato_endereco",
                                  "strLogradouroFalecimento"),
          de_onde="`local_fato_endereco`, ou o logradouro do acervo (31/31)"),
    claro("uf_do_obito", "UF do óbito",
          lambda ctx: _texto(ctx["d"].get("strUFFalecimento")),
          de_onde="`strUFFalecimento` do acervo (31/31)"),
    claro("tipo_de_morte", "Tipo de morte",
          lambda ctx: _texto(ctx["d"].get("strTipoMorte")),
          de_onde="`strTipoMorte` do acervo (31/31)"),
    # AS QUATRO PERGUNTAS DO ÓBITO têm coluna própria e **não têm equivalente
    # no blob**: elas nasceram nesta casa (`rc_marcas_do_obito`, 30/08/2026).
    # Saem vazias no acervo, e vazio aparece na conferência.
    claro("possui_bens", "Deixou bens",
          lambda ctx: _texto(ctx["a"].get("obito_possui_bens")),
          de_onde="`obito_possui_bens` — art. 80, § 1º"),
    claro("possui_filho", "Deixou filhos",
          lambda ctx: _texto(ctx["a"].get("obito_possui_filho")),
          de_onde="`obito_possui_filho`"),
)

CLAROS_PROPRIOS: dict[str, tuple[dict, ...]] = {
    NASCIMENTO: CLAROS_NASCIMENTO,
    CASAMENTO: CLAROS_CASAMENTO,
    OBITO: CLAROS_OBITO,
}


def vocabulario(especie: str) -> tuple[dict, ...]:
    """Todos os claros que a espécie conhece, na ordem em que a tela os mostra."""
    esp = _especie_valida(especie)
    return CLAROS_COMUNS + CLAROS_PROPRIOS[esp] + _claros_das_pessoas(esp)


def nomes_dos_claros(especie: str) -> frozenset[str]:
    return frozenset(c["nome"] for c in vocabulario(especie))


def _especie_valida(especie: Any) -> str:
    esp = _texto(especie).upper()
    if esp not in ESPECIES:
        raise ModeloLivreError(
            f"«{especie}» não é espécie de modelo. As que existem: "
            + ", ".join(NOME_DA_ESPECIE[e] for e in ESPECIES) + ".")
    return esp


# ================================================== conferir o texto do modelo

# Os dois formatos que este projeto conhece. Um `{{ a.numero }}` ou um
# `{% if %}` aqui e engano de quem veio da tela dos papeis da casa, que e
# Jinja — e sem esta conferencia ele passaria por claro desconhecido, com uma
# mensagem que nao explica nada.
MARCA_DO_JINJA: tuple[str, ...] = ("{{", "{%")

CLARO_ESCRITO = re.compile(r"\{([^{}]*)\}")


def claros_do_texto(texto: str) -> tuple[str, ...]:
    """Os claros escritos no texto, na ordem, sem repetir. Só calcula."""
    vistos: list[str] = []
    for achado in CLARO_ESCRITO.findall(texto or ""):
        nome = achado.strip()
        if nome and nome not in vistos:
            vistos.append(nome)
    return tuple(vistos)


def conferir_corpo(especie: str, texto: str) -> str:
    """O que há de errado no modelo, ou `""`. Só calcula.

    **A CONFERÊNCIA VEM ANTES DE GRAVAR.** Gravar primeiro e avisar depois
    deixaria o modelo quebrado valendo até alguém voltar na tela — e quem
    descobre é o escrevente com o cliente na frente. Aqui o erro aparece para
    quem edita, que é quem sabe consertá-lo.
    """
    esp = _especie_valida(especie)
    corpo = texto or ""
    if not corpo.strip():
        return "O modelo está vazio."

    for marca in MARCA_DO_JINJA:
        if marca in corpo:
            return (f"Este modelo usa «{marca}», que é a marcação das outras "
                    "telas de modelo. Aqui o claro se escreve entre chaves "
                    "simples, assim: {nome}.")

    if corpo.count("{") != corpo.count("}"):
        return ("Há chave aberta sem fechar. Cada claro se escreve {assim}.")

    # **A MESMA GUARDA DO E-MAIL**, e pela mesma razao: sem ela um modelo com
    # `cidadeexemplo@cartorio.ch` no rodape seria recusado como «texto do
    # E-Oficio», e o oficial nao teria como gravar o rodape da casa.
    if "@" in corpo and CLARO_DO_EOFICIO.search(corpo):
        return ("Este texto ainda tem claros do E-Ofício, escritos com «@». "
                "Use o botão «Converter do E-Ofício» antes de gravar.")

    conhecidos = nomes_dos_claros(esp)
    desconhecidos = [c for c in claros_do_texto(corpo) if c not in conhecidos]
    if desconhecidos:
        return ("O sistema não sabe preencher: "
                + ", ".join("{" + c + "}" for c in desconhecidos)
                + ". Confira a lista de claros ao lado.")
    return ""


# ====================================================== o contexto de um assento

def contexto(con: sqlite3.Connection, assento_id: int, *, serventia: dict,
             hoje: str) -> dict:
    """Tudo o que o modelo precisa daquele assento. Só lê."""
    con.row_factory = sqlite3.Row
    linha = con.execute("SELECT * FROM rc_assentos WHERE id = ?",
                        (assento_id,)).fetchone()
    if not linha:
        raise ModeloLivreError(f"Não achei o assento nº {assento_id}.")
    a = dict(linha)

    todas = [dict(p) for p in con.execute(
        "SELECT * FROM rc_pessoas WHERE assento_id = ? ORDER BY ordem, id",
        (assento_id,))]
    # **A PRIMEIRA DE CADA PAPEL**, e não a última: a ordem é a do acervo, e o
    # pai vem antes da mãe por causa dela.
    quem: dict[str, dict] = {}
    for p in todas:
        quem.setdefault(_texto(p.get("papel")).upper(), p)

    ato = con.execute(
        """SELECT * FROM rc_atos WHERE assento_id = ? AND tipo = 'REGISTRO'
            ORDER BY id LIMIT 1""", (assento_id,)).fetchone()

    return {"a": a, "d": _dados_do_acervo(a), "quem": quem, "todas": todas,
            "ato": dict(ato) if ato else {}, "sv": dict(serventia or {}),
            "hoje": hoje}


def valores(ctx: dict, especie: str) -> dict[str, str]:
    """O valor de cada claro da espécie, para aquele assento. Só calcula."""
    saida: dict[str, str] = {}
    for c in vocabulario(especie):
        try:
            saida[c["nome"]] = _texto(c["vem_de"](ctx))
        except (KeyError, TypeError, ValueError, AttributeError):
            # **UM CLARO QUE ESTOURA NAO DERRUBA O DOCUMENTO INTEIRO.** Ele sai
            # vazio, e vazio APARECE NA CONFERENCIA — que e onde o escrevente
            # decide se imprime assim. Deixar a excecao subir tiraria do balcao
            # o papel todo por causa de um campo.
            saida[c["nome"]] = ""
    return saida


# =========================================================== montar o documento

def montar(con: sqlite3.Connection, modelo_id: int, assento_id: int, *,
           serventia: dict, hoje: str) -> dict:
    """O documento montado, e o que faltou. Só calcula — NÃO grava.

    Devolve `{"texto", "vazios", "modelo", "assento"}`. **`vazios` é a metade
    que o E-Ofício não tinha**: lá o claro sem dado virava espaço em branco no
    papel, e o escrevente só descobria depois de impresso.
    """
    m = ler(con, modelo_id)
    ctx = contexto(con, assento_id, serventia=serventia, hoje=hoje)
    esp_do_assento = _texto(ctx["a"].get("especie")).upper()
    if esp_do_assento != m["especie"]:
        raise ModeloLivreError(
            f"O modelo «{m['nome']}» é de {NOME_DA_ESPECIE[m['especie']]} e "
            f"este assento é de {NOME_DA_ESPECIE.get(esp_do_assento, esp_do_assento.title())}. "
            "Um claro que não existe na outra espécie sairia em branco no papel.")

    v = valores(ctx, m["especie"])

    escritos = claros_do_texto(m["corpo"])
    desconhecidos = [c for c in escritos if c not in v]
    if desconhecidos:
        raise ModeloLivreError(
            "O modelo tem claro que o sistema não sabe preencher: "
            + ", ".join("{" + c + "}" for c in desconhecidos) + ".")

    texto = m["corpo"]
    for nome in escritos:
        texto = texto.replace("{" + nome + "}", v[nome])

    return {"texto": texto,
            "vazios": [c for c in escritos if not v[c]],
            "modelo": m, "assento": ctx["a"]}


# ============================================ traduzir o texto vindo do E-Ofício

# **O DE-PARA, E ELE SÓ TEM O QUE ESTÁ MEDIDO DOS DOIS LADOS.**
#
#   Chave: o claro do E-Ofício, como ele aparece nos 13 modelos de
#   `tbModelosRCPN`. Valor: o claro desta casa, que existe no `vocabulario`.
#
#   **O que não está aqui não se converte, e não se apaga: fica escrito no
#   texto e é DEVOLVIDO NA LISTA.** Adivinhar o destino de um claro poria o
#   dado errado debaixo do rótulo certo, que é o pior lugar para um erro num
#   documento de registro civil — e apagá-lo em silêncio faria o oficial
#   descobrir o buraco no papel impresso.
#
#   A comparação é feita SEM MAIÚSCULA: medido nos 13 modelos, o mesmo claro
#   aparece como `@dataatual` e `@dataAtual`, e `@nomenascido` e `@NOMENASCIDO`.
DE_PARA_DO_EOFICIO: dict[str, str] = {
    # ------------------------------------------------------------- a serventia
    # **`@cartorio` E `@gmail` SAIRAM DAQUI, e a razao e uma medicao errada
    # minha.** Eu os tinha como claros porque o varredor achava `@cartorio` em
    # `cidadeexemplo@cartorio.ch` e `@gmail` em `cidadeexemplo.cartorio@gmail.com`
    # — os dois sao **cauda de endereco de e-mail**, e nao claro. Com a guarda
    # do `@` corrigida eles nao aparecem uma unica vez nos 13 modelos.
    #
    #   Manter a linha seria manter entrada com **um lado so medido**, que e
    #   justamente o que este de-para nao aceita. Se algum modelo do oficial
    #   usar `@cartorio` de verdade, ele volta na lista dos nao convertidos,
    #   com o nome — e ai se acrescenta com os dois lados medidos.
    "registrador": "registrador",
    "funcaoregistrador": "funcao_do_registrador",
    "dataatual": "data_de_hoje",
    "dataatualporextensocn": "data_de_hoje_extenso",
    # ------------------------------------------------------------- o assento
    "livro": "livro",
    "folha": "folha",
    "registro": "termo",
    "matricula": "matricula",
    "matriculanascido": "matricula",
    "matriculaobito": "matricula",
    "dataregistroextenso": "data_do_registro_extenso",
    "dataregistroextensocn": "data_do_registro_extenso",
    "dataregistroextensosn": "data_do_registro_extenso",
    "diaregistro": "data_do_registro",
    "mesregistro": "data_do_registro",
    "anoregistro": "data_do_registro",
    # ------------------------------------------------------------ o nascimento
    "nomenascido": "registrado_nome",
    "cpfnascido": "cpf_do_registrado",
    "sexonascido": "registrado_sexo",
    "cornascido": "cor_ou_raca",
    "naturalidadenascido": "registrado_naturalidade",
    "municipionascimento": "registrado_naturalidade_cidade",
    "ufnascimento": "registrado_naturalidade_uf",
    "municipio_naturalidade_nascimento": "registrado_naturalidade_cidade",
    "uf_naturalidade_nascimento": "registrado_naturalidade_uf",
    # O «município de registro» é o da serventia, e não o do nascimento.
    "municipio_registro_nascimento": "cidade",
    "selo": "selo",
    "datadonascimento": "data_do_nascimento",
    "datanascimento": "data_do_nascimento",
    "datanascimentoextenso": "data_do_nascimento_extenso",
    "datanascimentoextensocn": "data_do_nascimento_extenso",
    "datanascimentoextensosn": "data_do_nascimento_extenso",
    "dianascimento": "dia_do_nascimento",
    "mesnascimento": "mes_do_nascimento",
    "anonascimento": "ano_do_nascimento",
    "horanascimento": "hora_do_nascimento",
    "nomelocalnascimento": "local_do_nascimento",
    "localnascimento": "local_do_nascimento",
    "enderecolocalnascimento": "endereco_do_nascimento",
    "declaracaonascidovivo": "dnv",
    "possuigemeos": "ordem_de_gemeo",
    "avosfiliacao1": "avos_paternos",
    "avosfiliacao2": "avos_maternos",
    # ------------------------------------------------------------- a filiação
    "nomefiliacao1": "pai_nome",
    "nomefiliacao2": "mae_nome",
    "cpffiliacao1": "pai_cpf",
    "cpffiliacao2": "mae_cpf",
    "rgfiliacao1": "pai_rg",
    "rgfiliacao2": "mae_rg",
    "profissaofiliacao1": "pai_profissao",
    "profissaofiliacao2": "mae_profissao",
    "nacionalidadefiliacao1": "pai_nacionalidade",
    "nacionalidadefiliacao2": "mae_nacionalidade",
    "naturalidadefiliacao1": "pai_naturalidade",
    "municipionaturalidadefiliacao2": "mae_naturalidade_cidade",
    "ufnaturalidadefiliacao2": "mae_naturalidade_uf",
    "nascimentofiliacao1": "pai_data_nascimento",
    "nascimentofiliacao2": "mae_data_nascimento",
    "idadefiliacao1": "pai_idade",
    "idadefiliacao2": "mae_idade",
    "logradourofiliacao1": "pai_endereco",
    "logradourofiliacao2": "mae_endereco",
    "bairrofiliacao1": "pai_bairro",
    "bairrofiliacao2": "mae_bairro",
    "municipiofiliacao1": "pai_cidade",
    "municipiofiliacao2": "mae_cidade",
    "uffiliacao1": "pai_uf",
    "uffiliacao2": "mae_uf",
    # ------------------------------------------------------------ o declarante
    "nomedeclarante": "declarante_nome",
    "nomedeclarante1": "declarante_nome",
    "cpfdeclarante": "declarante_cpf",
    "cpfdeclarante1": "declarante_cpf",
    "rgdeclarante": "declarante_rg",
    "rgdeclarante1": "declarante_rg",
    "profissaodeclarante": "declarante_profissao",
    "profissaodeclarante1": "declarante_profissao",
    "nacionalidadedeclarante": "declarante_nacionalidade",
    "nacionalidadedeclarante1": "declarante_nacionalidade",
    "naturalidadedeclarante1": "declarante_naturalidade",
    "estadocivildeclarante1": "declarante_estado_civil",
    "logradourodeclarante": "declarante_endereco",
    "logradourodeclarante1": "declarante_endereco",
    "bairrodeclarante": "declarante_bairro",
    "bairrodeclarante1": "declarante_bairro",
    "municipiodeclarante": "declarante_cidade",
    "municipiodeclarante1": "declarante_cidade",
    "ufdeclarante": "declarante_uf",
    "ufdeclarante1": "declarante_uf",
    "orgaorgdeclarante1": "declarante_orgao",
    "municipionaturalidadedeclarante": "declarante_naturalidade_cidade",
    "ufnaturalidadedeclarante1": "declarante_naturalidade_uf",
    "datadeclarantenascimento1": "declarante_data_nascimento",
    # ------------------------------------------------------------- o casamento
    "nomeconjuge1": "nubente1_nome",
    "nomeconjuge2": "nubente2_nome",
    "cpfconjuge1": "nubente1_cpf",
    "cpfconjuge2": "nubente2_cpf",
    "novonomeconjuge1": "nubente1_nome_pos",
    "novonomeconjuge2": "nubente2_nome_pos",
    "ufnaturalidadeconjuge1": "nubente1_naturalidade_uf",
    "ufnaturalidadeconjuge2": "nubente2_naturalidade_uf",
    "datanascimentoconjuge1extensocn": "nubente1_data_nascimento_extenso",
    "datanascimentoconjuge2extensocn": "nubente2_data_nascimento_extenso",
    # **A FILIAÇÃO DOS NUBENTES CONVERTE, e o destino são os quatro papéis
    # próprios** — `PAI_NUBENTE1` e companhia, que esta casa grava desde
    # 31/08/2026. **Nos 20 casamentos do acervo eles saem vazios**, porque lá a
    # filiação foi gravada como `PAI`/`MAE` avulsos, sem dizer de qual nubente:
    # e vazio na conferência é melhor que o pai de um sob o nome do outro.
    #
    #   A ordem 3 = pai e 4 = mãe segue a do **próprio E-Ofício**, onde a
    #   filiação 1 é o pai (medido no acervo bruto: 162 masculinas contra 30
    #   femininas na 1) — a mesma leitura que faz `@nomefiliacao1` virar
    #   `{pai_nome}`.
    "filiacaoconjuge1": "filiacao_nubente1",
    "filiacaoconjuge2": "filiacao_nubente2",
    "nomefiliacao3": "pai_nubente2_nome",
    "nomefiliacao4": "mae_nubente2_nome",
    "regimebens": "regime_de_bens",
    "datacelebracaocasamento": "data_do_casamento",
    "descricaolocal": "local_da_celebracao",
    # ----------------------------------------------------------------- o óbito
    "nomefalecido": "falecido_nome",
    "cpffalecido": "falecido_cpf",
    "rgfalecido": "falecido_rg",
    "orgaorgfalecido": "falecido_orgao",
    "sexofalecido": "falecido_sexo",
    "corfalecido": "cor_ou_raca",
    "profissaofalecido": "falecido_profissao",
    "nacionalidadefalecido": "falecido_nacionalidade",
    "naturalidadefalecido": "falecido_naturalidade",
    "estadocivilfalecido": "falecido_estado_civil",
    "enderecofalecido": "falecido_endereco",
    "idadedofalecido": "idade_do_falecido",
    "causamorte": "causa_da_morte",
    "horafalecimento": "hora_do_obito",
    "datafalecimentoextenso": "data_do_obito_extenso",
    "datafalecimentoextensocn": "data_do_obito_extenso",
    "diafalecimento": "data_do_obito",
    "mesfalecimento": "data_do_obito",
    "anofalecimento": "data_do_obito",
    "nomedolocalfalecimento": "local_do_obito",
    "municipiofalecimento": "municipio_do_obito",
    "uffalecimento": "uf_do_obito",
    "logradourofalecimento": "endereco_do_obito",
    "enderecoobito": "endereco_do_obito",
    "tipomorte": "tipo_de_morte",
    "possuibens": "possui_bens",
    "localsepultamento": "local_do_sepultamento",
    "atestanteprimario": "atestante",
    "declaracaoobito": "declaracao_de_obito",
    "tituloeleitorfalecido": "titulo_de_eleitor",
    "filiacaofalecido": "filiacao",
    "nascimentodofalecidoextensocn": "falecido_data_nascimento",
}

# **O `@` DE UM CLARO NAO VEM DEPOIS DE LETRA OU DIGITO — senao e e-mail.**
#
#   Sem esta guarda, `cidadeexemplo@cartorio.ch` — que esta no rodape de varios
#   dos 13 modelos reais — virava `cidadeexemplo{cartorio}.ch` na conversao, e
#   `conferir_corpo` recusava qualquer modelo com endereco de e-mail dentro.
#
#   **O hifen e o ponto NAO desqualificam**: nos modelos reais ha
#   `@municipiofalecimento-@uffalecimento`, e um claro depois de hifen e claro.
#   Local de e-mail nao termina em hifen nem em ponto.
# **O MESMO CLARO NÃO QUER DIZER A MESMA COISA NAS TRÊS ESPÉCIES.**
#
#   `@nomefiliacao1` é o pai do registrado num modelo de nascimento e o pai do
#   **primeiro nubente** num modelo de casamento — e o E-Ofício numera de 1 a 4
#   ali, dois para cada nubente. Sem esta camada, converter o modelo nº 9
#   («Comunicação de Casamento para o Registro de Nascimento») produzia
#   `{pai_nome}`, que **não existe no vocabulário do casamento**: o texto era
#   convertido e recusado na conferência logo em seguida.
#
#   **Quem achou foi a conversão dos 13 modelos reais de ponta a ponta**, e não
#   a releitura do de-para: doze passavam, e o nono não.
DE_PARA_POR_ESPECIE: dict[str, dict[str, str]] = {
    CASAMENTO: {
        "nomefiliacao1": "pai_nubente1_nome",
        "nomefiliacao2": "mae_nubente1_nome",
        "nomefiliacao3": "pai_nubente2_nome",
        "nomefiliacao4": "mae_nubente2_nome",
    },
}

CLARO_DO_EOFICIO = re.compile(r"(?<![A-Za-z0-9])@([A-Za-z_][A-Za-z0-9_]*)")


def traduzir_do_eoficio(texto: str, especie: str = "") -> dict:
    """Troca os `@claros` do E-Ofício pelos `{claros}` desta casa.

    Devolve `{"texto", "convertidos", "nao_convertidos"}`.

    **A ESPÉCIE MUDA O DESTINO DE ALGUNS CLAROS** — `@nomefiliacao1` é o pai do
    registrado no nascimento e o pai do primeiro nubente no casamento. Sem ela
    a conversão usa só o de-para geral, que é o do nascimento e do óbito.

    **O QUE NÃO ESTÁ NO DE-PARA CONTINUA ESCRITO NO TEXTO** e volta na lista.
    Apagá-lo faria o oficial descobrir o buraco no papel impresso; adivinhá-lo
    poria o dado errado debaixo do rótulo certo.
    """
    bruto = texto or ""
    proprio = DE_PARA_POR_ESPECIE.get(_texto(especie).upper(), {})
    convertidos: list[tuple[str, str]] = []
    nao: list[str] = []

    def trocar(m: re.Match) -> str:
        achado = m.group(1)
        destino = (proprio.get(achado.lower())
                   or DE_PARA_DO_EOFICIO.get(achado.lower()))
        if not destino:
            if achado not in nao:
                nao.append(achado)
            return m.group(0)
        par = (achado, destino)
        if par not in convertidos:
            convertidos.append(par)
        return "{" + destino + "}"

    return {"texto": CLARO_DO_EOFICIO.sub(trocar, bruto),
            "convertidos": convertidos, "nao_convertidos": nao}


# ================================================================ o cadastro

def _nome_valido(nome: str) -> str:
    limpo = " ".join((nome or "").split())
    if not limpo:
        raise ModeloLivreError("O modelo precisa de um nome.")
    if len(limpo) > TAMANHO_DO_NOME:
        raise ModeloLivreError(
            f"O nome do modelo passa de {TAMANHO_DO_NOME} caracteres.")
    return limpo


def listar(con: sqlite3.Connection, *, especie: str = "",
           incluir_inativos: bool = True) -> list[dict]:
    """Os modelos cadastrados, na ordem em que a tela mostra."""
    con.row_factory = sqlite3.Row
    onde, args = [], []
    if especie:
        onde.append("especie = ?")
        args.append(_especie_valida(especie))
    if not incluir_inativos:
        onde.append("ativo = 1")
    sql = "SELECT * FROM rc_modelos_livres"
    if onde:
        sql += " WHERE " + " AND ".join(onde)
    sql += " ORDER BY especie, nome COLLATE NOCASE"
    return [dict(r) for r in con.execute(sql, args)]


def ler(con: sqlite3.Connection, modelo_id: int) -> dict:
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM rc_modelos_livres WHERE id = ?",
                    (modelo_id,)).fetchone()
    if not r:
        raise ModeloLivreError(f"Não achei o modelo nº {modelo_id}.")
    return dict(r)


def criar(con: sqlite3.Connection, *, especie: str, nome: str, corpo: str,
          quem: str | None, agora: str) -> int:
    """Cadastra um modelo novo. Confere ANTES de gravar."""
    esp = _especie_valida(especie)
    limpo = _nome_valido(nome)
    ruim = conferir_corpo(esp, corpo)
    if ruim:
        raise ModeloLivreError(ruim)
    try:
        cur = con.execute(
            """INSERT INTO rc_modelos_livres
                   (especie, nome, corpo, ativo, criado_em, criado_por)
               VALUES (?,?,?,1,?,?)""",
            (esp, limpo, corpo.strip(), agora, quem))
    except sqlite3.IntegrityError as erro:
        raise ModeloLivreError(
            f"Já existe um modelo de {NOME_DA_ESPECIE[esp]} chamado "
            f"«{limpo}».") from erro
    return int(cur.lastrowid)


def salvar(con: sqlite3.Connection, modelo_id: int, *, nome: str, corpo: str,
           quem: str | None, agora: str) -> None:
    """Regrava o modelo. A ESPÉCIE NÃO MUDA.

    Mudar a espécie de um modelo já escrito trocaria o vocabulário debaixo do
    texto: os claros de óbito viram desconhecidos num modelo de nascimento, e o
    documento sairia com buraco. Quem quer o mesmo texto na outra espécie
    cadastra outro modelo.
    """
    m = ler(con, modelo_id)
    limpo = _nome_valido(nome)
    ruim = conferir_corpo(m["especie"], corpo)
    if ruim:
        raise ModeloLivreError(ruim)
    try:
        con.execute(
            """UPDATE rc_modelos_livres
                  SET nome = ?, corpo = ?, atualizado_em = ?,
                      atualizado_por = ?
                WHERE id = ?""",
            (limpo, corpo.strip(), agora, quem, modelo_id))
    except sqlite3.IntegrityError as erro:
        raise ModeloLivreError(
            f"Já existe outro modelo de {NOME_DA_ESPECIE[m['especie']]} "
            f"chamado «{limpo}».") from erro


def ativar(con: sqlite3.Connection, modelo_id: int, *, ativo: bool,
           quem: str | None, agora: str) -> None:
    """Tira o modelo da lista de quem emite, ou o traz de volta.

    **DESATIVAR NÃO É APAGAR.** O modelo que já imprimiu documento é a forma do
    que a casa assinou; apagá-lo tiraria da serventia a explicação do papel que
    está na mão do cidadão.
    """
    ler(con, modelo_id)
    con.execute(
        """UPDATE rc_modelos_livres SET ativo = ?, atualizado_em = ?,
               atualizado_por = ? WHERE id = ?""",
        (1 if ativo else 0, agora, quem, modelo_id))


def para_o_assento(con: sqlite3.Connection, assento_id: int) -> list[dict]:
    """Os modelos ativos que servem àquele assento. Só lê."""
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT especie FROM rc_assentos WHERE id = ?",
                    (assento_id,)).fetchone()
    if not r:
        raise ModeloLivreError(f"Não achei o assento nº {assento_id}.")
    especie = _texto(r["especie"]).upper()
    if especie not in ESPECIES:
        return []
    return listar(con, especie=especie, incluir_inativos=False)


def quantos_por_especie(con: sqlite3.Connection) -> dict[str, int]:
    """Quantos modelos ativos há em cada espécie. Só lê — é o número da tela."""
    con.row_factory = sqlite3.Row
    saida = {e: 0 for e in ESPECIES}
    for r in con.execute(
            """SELECT especie, COUNT(*) n FROM rc_modelos_livres
                WHERE ativo = 1 GROUP BY especie"""):
        if r["especie"] in saida:
            saida[r["especie"]] = int(r["n"])
    return saida
