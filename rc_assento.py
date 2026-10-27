"""
RCPN — lavrar o assento, averbar, anotar, retificar.

COMO SE USA
    with db.transaction() as con:
        r = lavrar_assento(con, especie="NASCIMENTO", nome="JOÃO DA SILVA",
                           sv=sv, agora=agora, data_extenso=hoje,
                           data_fato="2026-08-20", dados={"sexo": "M"})
    audit(...)                      # FORA da transação, como no resto da casa

A ESPECIE MANDA NA SERIE, E NAO O CONTRARIO
    Nascimento vai no Livro A, casamento no B, óbito no C, proclamas no D.
    Quem escolhe é `SERIE_DA_ESPECIE`, e não o chamador — deixar o balcão
    escolher a série é deixar o balcão lançar um óbito no livro de
    nascimentos. As duas séries auxiliares (casamento religioso, natimortos)
    têm espécie própria por isso mesmo.

A DIVISAO TRIPARTITE
    `averbar()`, `anotar()` e `retificar()` são a mesma mecânica com tipos
    diferentes, e existem separadas porque a inspeção de 12/08/2026 cobra os
    três blocos distintos no assento — e porque são coisas juridicamente
    diferentes: a averbação altera o conteúdo do assento (Lei 6.015/1973,
    art. 97), a anotação remete a outro assento (art. 106), e a retificação
    corrige erro (art. 109).

    NENHUM DOS TRES OCUPA FOLHA NOVA. As séries RC_* são folha_nova para o
    ASSENTO — um registro por folha, como `tbPropriedadeRCPN` mede —, e a
    averbação se lança no espaço do próprio assento, inclusive no verso. É o
    oposto do RCPJ/RTD, onde cada ato é escritura nova. Por isso estes três
    NÃO chamam `escrituracao.reservar()`.

O QUE NAO ENTRA AINDA
    SIRC, CRC, IBGE, DNV, Unidade Interligada, matrícula de 32 dígitos
    gerada e validada, papel de segurança. Ver o cabeçalho de `rc_schema.py`.

FUNDAMENTO
    Lei 6.015/1973: art. 97 (averbação), art. 106 (anotação),
        art. 109 (retificação), arts. 50 a 88 (as espécies).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any
import unicodedata

from bd_nativo import banco
import escrituracao as ESC
# A BUSCA DE MUNICIPIO E' REAPROVEITADA, E NAO REESCRITA — a mesma que a
# remessa do IBGE e a carga da CRC ja' usam. Ela recusa escolher municipio
# parecido, e e' essa recusa que faz a derivacao da naturalidade ser segura.
import ibge_geracao as IBGEG
import ibge_remessa as IBGE

# A NORMALIZACAO DO NOME E A DA CASA, E SE IMPORTA — nao se copia.
#
#   `rc_pessoas.nome_norm` e preenchida pela carga do acervo com esta mesma
#   funcao. Escrever aqui uma «igual» e como este projeto ja errou duas vezes
#   no modulo de fraudes: a copia divergiu, e a busca por nome deixou de achar
#   metade das pessoas — caladamente. Onde a igualdade importa, ela se
#   constroi, e a forma de construi-la e importar.
from pt_schema import normalizar_nome


class RcError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


class ConferenciaError(RcError):
    """A lavratura recusada pela conferência dos dados (11/10/2026).

    Leva a lista dos problemas, e não só a frase: a tela usa a lista para abrir
    SÓ os campos que travaram — pedido do oficial, «ao recusar, permitir apenas
    arrumar o problema» — em vez de devolver o formulário inteiro.
    """

    def __init__(self, mensagem: str, problemas: list[dict]):
        super().__init__(mensagem)
        self.problemas = problemas


# Qual livro recebe cada espécie. De `tbPropriedadeRCPN` e da Lei 6.015/1973.
#
# O LIVRO E SE PARTIU EM SEIS EM 27/08/2026, e a razão veio de fora: o contrato
# do selador tem uma família de caminhos para CADA UMA das seis coisas que o
# Livro E registra — ausência, interdição, tutela, emancipação, união estável e
# opção de nacionalidade —, com registro, averbação, anotação, retificação e
# segunda via em todas.
#
# Enquanto as seis se chamavam «OUTRO», o sistema não tinha como pedir selo para
# nenhuma delas: `OUTRO` não diz qual. E não era só o selo — a Lei 6.015/1973,
# art. 33, V, manda o Livro E registrar coisas juridicamente distintas, e
# chamá-las pelo mesmo nome era o sistema sabendo menos que o livro de papel.
#
# `OUTRO` FICA, e fica de propósito: é o que recebe o que não é nenhuma das
# seis, e é o que impede que um assento já lavrado como «OUTRO» perca o nome.
# Ele não tem caminho de selo, e é honesto que não tenha.
def nome_e_livro(especie: Any) -> tuple[str, str]:
    """`NASCIMENTO` -> `("Nascimento", "Livro A")`. Só calcula.

    POR QUE ISTO EXISTE — relato #37, item 1, de 31/08/2026.

        `NOME_DA_ESPECIE` guarda um rótulo COMPOSTO: "Nascimento — Livro A". A
        tela escrevia `{{ nome_especie | lower }}` para caber no meio de uma
        frase, e o filtro derrubava a letra do livro junto: saía **"somente de
        nascimento — livro a"**.

        Não é detalhe de estilo. `A` é o nome do livro — o mesmo que vai no
        termo, na certidão e na matrícula de 32 dígitos —, e livro não tem
        minúscula. O oficial reparou na tela antes de qualquer teste.

        A correção não é escrever o rótulo de novo à mão em cada lugar: é
        **separar as duas partes**, para que a frase possa baixar a caixa da
        espécie sem alcançar o livro.
    """
    rotulo = NOME_DA_ESPECIE.get(str(especie or "").upper(), str(especie or ""))
    if "—" in rotulo:
        nome, livro = rotulo.split("—", 1)
        return (nome.strip(), livro.strip())
    return (rotulo.strip(), "")


SERIE_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "RC_A",
    "CASAMENTO": "RC_B",
    "CASAMENTO_RELIGIOSO": "RC_B_AUXILIAR",
    "OBITO": "RC_C",
    "NATIMORTO": "RC_C_AUXILIAR",
    "PROCLAMAS": "RC_D",
    # As seis do Livro E, cada uma com o seu nome.
    "AUSENCIA": "RC_E",
    "INTERDICAO": "RC_E",
    "TUTELA": "RC_E",
    "EMANCIPACAO": "RC_E",
    "UNIAO_ESTAVEL": "RC_E",
    "OPCAO_NACIONALIDADE": "RC_E",
    "OUTRO": "RC_E",
}

# COMO CADA ESPÉCIE SE ESCREVE NA TELA. Sem isto o balcão leria
# `OPCAO_NACIONALIDADE` num menu suspenso — que é nome de programador, e não o
# que está escrito no livro.
NOME_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "Nascimento — Livro A",
    "CASAMENTO": "Casamento — Livro B",
    "CASAMENTO_RELIGIOSO": "Casamento religioso com efeito civil — Livro B-Auxiliar",
    "OBITO": "Óbito — Livro C",
    "NATIMORTO": "Natimorto — Livro C-Auxiliar",
    "PROCLAMAS": "Proclamas (habilitação de casamento) — Livro D",
    "AUSENCIA": "Ausência — Livro E",
    "INTERDICAO": "Interdição — Livro E",
    "TUTELA": "Tutela — Livro E",
    "EMANCIPACAO": "Emancipação — Livro E",
    "UNIAO_ESTAVEL": "União estável — Livro E",
    "OPCAO_NACIONALIDADE": "Opção de nacionalidade — Livro E",
    # O TRAVESSÃO NÃO É ENFEITE: é o que separa a espécie do livro, e as
    # treze seguem a mesma forma. Este era o único escrito "do Livro E", e por
    # isso escapava da separação e voltava a escrever "livro e" na frase da
    # tela — o mesmo defeito do relato #37, item 1, num rótulo só.
    "OUTRO": "Outro registro — Livro E",
}

ESPECIES = tuple(SERIE_DA_ESPECIE)

# Os três blocos que a inspeção cobra, mais o registro que os precede.
TIPOS_ATO = ("REGISTRO", "AVERBACAO", "ANOTACAO", "RETIFICACAO")

# Os três que se lançam no espaço do próprio assento, sem folha nova.
TIPOS_NO_PROPRIO_ASSENTO = ("AVERBACAO", "ANOTACAO", "RETIFICACAO")

SITUACOES = ("ATIVO", "CANCELADO")


# --------------------------------------------------------------- consultas


def assento(con: Any, assento_id: int) -> dict | None:
    """O assento, com tudo que foi lavrado. Só LÊ."""
    return banco(con).um(
        "SELECT * FROM rc_assentos WHERE id = %s", (int(assento_id),))


def atos_do(con: Any, assento_id: int) -> list[dict]:
    """Os atos do assento, na ordem em que aconteceram. Só LÊ."""
    return banco(con).ler(
        "SELECT * FROM rc_atos WHERE assento_id = %s ORDER BY id",
        (int(assento_id),))


def blocos_do(con: Any, assento_id: int) -> dict[str, list[dict]]:
    """Os atos separados por bloco — a divisão tripartite, para a ficha. Só LÊ.

    É o que a inspeção pede que apareça em campos próprios: as averbações
    num bloco, as anotações noutro, as retificações noutro.
    """
    saida: dict[str, list[dict]] = {t: [] for t in TIPOS_ATO}
    for ato in atos_do(con, assento_id):
        saida.setdefault(ato["tipo"], []).append(ato)
    return saida


def assento_por_origem(con: Any, origem: str,
                       origem_chave: str) -> dict | None:
    """O assento de uma chave de origem, ou None. Só LÊ."""
    return banco(con).um(
        "SELECT * FROM rc_assentos WHERE origem = %s AND origem_chave = %s "
        "ORDER BY id LIMIT 1",
        (origem, origem_chave))


# ----------------------------------------------------------- lavrar assento


# AS ESPECIES QUE SAO CASAMENTO, e que por isso podem vir de habilitacao de
# outra serventia. `PROCLAMAS` nao entra: ele e o edital, e nao o casamento.
ESPECIES_DE_CASAMENTO: frozenset[str] = frozenset(
    {"CASAMENTO", "CASAMENTO_RELIGIOSO"})


# ------------------------------------------ o que a remessa do IBGE pede
#
# POR QUE ESTES CAMPOS SAO DO ASSENTO, E NAO DERIVADOS
#     A remessa trimestral (Lei 6.015/1973, art. 49) pede coisas que nao estao
#     em lugar nenhum do assento e nao se deduzem de nada:
#
#       LOCAL-NASC  onde a crianca nasceu — hospital, outro estabelecimento de
#                   saude, domicilio, outros. Catalogo medido em
#                   `ibge_remessa.LOCAL_DO_NASCIMENTO`.
#       GEMEO       parto unico, gemeo, trigemeo ou mais.
#       DNV / DO    o numero da Declaracao de Nascido Vivo e o da Declaracao
#                   de Obito. Numero de documento: nao tem catalogo.
#
#     O RESTO DO LAYOUT JA EXISTE e por isso NAO virou campo: o lugar do
#     nascimento e a naturalidade do registrado, a residencia da mae e o
#     endereco dela, e a idade da genitora se calcula da data de nascimento
#     dela. Campo para dado que ja existe e a segunda fonte que diverge da
#     primeira — foi assim que a numeracao errou em 18/08.
#
# O CODIGO SE CONFERE CONTRA O CATALOGO, e nao se aceita qualquer numero:
#     mandar `4` em LOCAL-NASC (que nao existe: o catalogo pula do 3 para o 5)
#     faria o IBGE recusar o trimestre inteiro, meses depois, sem dizer qual
#     linha. Recusar aqui custa uma frase; recusar la custa o trimestre.
CAMPOS_DO_IBGE_POR_ESPECIE: dict[str, tuple[str, ...]] = {
    "NASCIMENTO": ("ibge_local_nascimento", "ibge_gemeo", "dnv"),
    "OBITO": ("numero_do", "ibge_natureza_obito", "ibge_local_obito"),
    "NATIMORTO": ("numero_do", "ibge_natureza_obito", "ibge_local_obito"),
}


# O QUE O TERMO PEDE E A CERTIDAO IMPRIME — a lista fechada da cor ou raca.
#
#   E a MESMA da CRC (`crc_carga.COR_PELE`), e por isso a chave e escrita aqui
#   sem acento e em caixa alta: a Central so aceita estes seis, e uma setima
#   palavra digitada no balcao volta como recusa da carga inteira, meses
#   depois, sem dizer qual linha.
CORES_E_RACAS: dict[str, str] = {
    "BRANCA": "Branca",
    "PRETA": "Preta",
    "PARDA": "Parda",
    "AMARELA": "Amarela",
    "INDIGENA": "Indígena",
    "IGNORADA": "Ignorada",
}

# OS CAMPOS QUE O TERMO PEDE, por especie.
#
#   **ELES EXISTIAM NO BANCO E NINGUEM OS PREENCHIA.** Foram criados em
#   29/08/2026 para o termo e as remessas; em 30/08 se mediu que o formulario
#   de lavratura nao perguntava nenhum deles e que `lavrar_assento` nao os
#   lia. Coluna que nada preenche e coluna que mente: a remessa acusa «falta o
#   dado» e ninguem sabe onde informa-lo.
CAMPOS_DO_TERMO_POR_ESPECIE: dict[str, tuple[str, ...]] = {
    # O MUNICÍPIO DO LOCAL (LD01, 21/10/2026) vai com o nome e o endereço: é
    # ele que a certidão imprime na célula MUNICÍPIO, e o endereço não é.
    "NASCIMENTO": ("cor_raca", "hora_fato", "local_fato_nome",
                   "local_fato_endereco", "local_fato_municipio",
                   "naturalidade_declarada"),
    # Natimorto (art. 53) tem lugar do fato no papel, como o nascimento e o obito.
    "NATIMORTO": ("cor_raca", "hora_fato", "local_fato_nome",
                   "local_fato_endereco", "local_fato_municipio",
                   "naturalidade_declarada"),
    "OBITO": ("cor_raca", "hora_fato", "local_fato_nome",
              "local_fato_endereco", "local_fato_municipio",
              "naturalidade_declarada",
              "causa_morte", "atestante", "atestante_documento",
              "local_sepultamento", "testamento"),
    "CASAMENTO": ("hora_fato", "local_fato_nome", "local_fato_endereco"),
    "CASAMENTO_RELIGIOSO": (
        "hora_fato", "local_fato_nome", "local_fato_endereco"),
}

#: As espécies cujo termo diz o lugar do fato e cuja certidão imprime o
#: MUNICÍPIO dele (LRP art. 54, 1º; art. 80, 2º) — LD01, 21/10/2026.
ESPECIES_COM_MUNICIPIO_DO_LOCAL: frozenset[str] = frozenset(
    {"NASCIMENTO", "NATIMORTO", "OBITO"})


def municipio_do_local_padrao(sv: dict | None) -> str:
    """O município do local do fato que a tela já traz escrito: o da
    serventia, «Município/UF». Só calcula.

    **É O CASO COMUM, E FICA À VISTA PARA SER TROCADO.** O nascimento e o
    óbito se registram no lugar do fato ou no da residência (LRP arts. 50 e
    77), e o que acontece noutro município o escrevente escreve por cima — a
    tela mostra o campo preenchido, e a conferência o repete. Quem lavra sem
    a tela (robô, integração, a importação do arquivo) recebe o mesmo valor
    que a tela daria, e não um vazio: célula vazia de município numa certidão
    de nascimento é o defeito que o LD01 consertou. A carga do acervo não
    passa por aqui — o assento antigo traz o município no blob.
    """
    s = sv or {}
    cidade = str(s.get("ri_cidade") or s.get("cidade") or "").strip()
    uf = str(s.get("ri_uf") or s.get("uf") or "").strip()
    return f"{cidade}/{uf}" if cidade and uf else cidade


#: O QUE A LEI PEDE E NÃO TINHA ONDE SER INFORMADO — 13/10/2026. Texto livre,
#: opcional e condicional (a tela só pergunta quando a situação existe); por
#: isso entra por `anotar_do_termo` como os demais, e o termo só traz a frase
#: quando há dado. As colunas estão em `rc_schema.MIGRACOES`.
CAMPOS_DA_LEI_POR_ESPECIE: dict[str, tuple[str, ...]] = {
    "OBITO": ("obito_conjuge_nome", "obito_conjuge_situacao",
              "obito_conjuge_cartorio", "obito_filhos",
              "obito_herdeiros_menores"),
    "CASAMENTO": ("nubente1_conjuge_anterior", "nubente1_dissolucao_data",
                  "nubente2_conjuge_anterior", "nubente2_dissolucao_data",
                  "proclamas_data", "documentos_apresentados",
                  "pacto_data", "pacto_serventia"),
    "NASCIMENTO": ("pais_casamento_lugar", "pais_casamento_cartorio",
                   # O REGISTRO TARDIO (art. 249) — a marca e o número do
                   # requerimento autuado. 21/10/2026.
                   "registro_tardio", "tardio_requerimento"),
}
CAMPOS_DA_LEI_POR_ESPECIE["CASAMENTO_RELIGIOSO"] = CAMPOS_DA_LEI_POR_ESPECIE["CASAMENTO"]
# O JUIZ DE PAZ QUE PRESIDIU — 15/10/2026, decisão do oficial (relato #124):
# entra só no casamento CIVIL, DEPOIS da linha acima, para o religioso não o
# herdar (lá quem presidiu foi o celebrante). Opcional: sem o nome, a linha de
# assinatura da folha sai só com o rótulo «Juiz(a) de Paz».
CAMPOS_DA_LEI_POR_ESPECIE["CASAMENTO"] = (
    CAMPOS_DA_LEI_POR_ESPECIE["CASAMENTO"] + ("juiz_de_paz",))
# O LIVRO E — 13/10/2026. O título (sentença, escritura ou termo) e a
# referência ao registro de nascimento valem para as seis espécies; o resto é
# o que o artigo de cada uma pede. O «OUTRO» fica sem: não se sabe o que é.
_TITULO_DO_LIVRO_E = (
    "livro_e_titulo", "livro_e_titulo_data", "livro_e_juizo", "livro_e_juiz",
    "livro_e_processo", "livro_e_transito", "livro_e_escritura_livro",
    "livro_e_escritura_folha", "livro_e_tabelionato",
    "livro_e_registro_nascimento")
CAMPOS_DA_LEI_POR_ESPECIE.update({
    "EMANCIPACAO": _TITULO_DO_LIVRO_E,                                 # art. 90
    "INTERDICAO": _TITULO_DO_LIVRO_E + (                               # art. 92
        "livro_e_registro_casamento", "livro_e_conjuge", "livro_e_causa",
        "livro_e_limites", "livro_e_internacao"),
    "AUSENCIA": _TITULO_DO_LIVRO_E + (                                 # art. 94
        "livro_e_registro_casamento", "livro_e_conjuge",
        "livro_e_ausencia_tempo", "livro_e_limites"),
    "TUTELA": _TITULO_DO_LIVRO_E,                    # por analogia ao art. 92
    "UNIAO_ESTAVEL": _TITULO_DO_LIVRO_E + (                         # art. 94-A
        "livro_e_registro_casamento", "livro_e_uniao_inicio"),
    "OPCAO_NACIONALIDADE": _TITULO_DO_LIVRO_E,              # art. 32, § 4º
})
for _esp, _campos in CAMPOS_DA_LEI_POR_ESPECIE.items():
    CAMPOS_DO_TERMO_POR_ESPECIE[_esp] = (
        CAMPOS_DO_TERMO_POR_ESPECIE.get(_esp, ()) + _campos)
#: Todos os nomes, para a rota e para `anotar_do_termo` saberem o que é seu.
CAMPOS_DA_LEI: tuple[str, ...] = tuple(dict.fromkeys(
    c for cs in CAMPOS_DA_LEI_POR_ESPECIE.values() for c in cs))


# De qual pessoa e' a naturalidade que o termo declara. Nascimento e natimorto
# falam do REGISTRADO; obito, do FALECIDO. Casamento nem tem o campo.
TITULAR_DA_NATURALIDADE: dict[str, str] = {
    "NASCIMENTO": "REGISTRADO",
    "NATIMORTO": "REGISTRADO",
    "OBITO": "FALECIDO",
}


def municipio_da_naturalidade(declarada: Any) -> tuple[str, str]:
    """Separa a naturalidade declarada em (municipio, UF). **So le.**

    O balcao escreve a naturalidade como ela sai da boca do declarante, e o
    povoado vem junto. Medido nos 19 assentos que a CRC reteve em 22/09/2026:

        «Cidade Exemplo-MA»                        -> ("Cidade Exemplo", "MA")
        «Imperatriz/MA»                          -> ("Imperatriz", "MA")
        «VÃO DA POSSE, Cidade Exemplo-MA»          -> ("Cidade Exemplo", "MA")
        «Povoado Passagem Boa, Cidade Exemplo-MA»  -> ("Cidade Exemplo", "MA")
        «Tocantinópolis-TO»                      -> ("Tocantinópolis", "TO")

    **O MUNICIPIO E' O QUE VEM DEPOIS DA ULTIMA VIRGULA.** O povoado e' onde a
    pessoa nasceu; o municipio e' o que o IBGE e a CRC conhecem. Ficar com o
    povoado faria a busca nao achar nada — e, pior, poderia achar um municipio
    homonimo noutro estado.

    **E A UF SO SE CORTA QUANDO TEM DUAS LETRAS.** Ha municipio com hifen no
    nome (Mogi-Mirim, Embu-Guacu): cortar no ultimo hifen sem conferir o
    tamanho transformaria «Mogi-Mirim» em «Mogi». Com a regra das duas letras,
    «Mogi-Mirim» fica inteiro e «Mogi-Mirim-SP» perde so' a UF.

    Devolve `("", "")` quando nao ha texto — e **nao inventa UF nenhuma**:
    quem nao escreveu o estado nao disse «MA».
    """
    texto = ("" if declarada is None else str(declarada)).strip()
    if not texto:
        return "", ""
    # Depois da ultima virgula: «povoado, municipio-UF» -> «municipio-UF».
    texto = texto.rsplit(",", 1)[-1].strip()
    uf = ""
    for separador in ("/", "-"):
        if separador in texto:
            cabeca, cauda = texto.rsplit(separador, 1)
            cauda = cauda.strip(" .")
            if len(cauda) == 2 and cauda.isalpha() and cabeca.strip():
                texto, uf = cabeca.strip(), cauda.upper()
                break
    return texto.strip(" ."), uf


def _tem_municipios(con: Any) -> bool:
    """Se `ib_municipios` existe E tem linha. **So le.**

    As duas perguntas numa so' de proposito: a tabela **faltar** (instalacao
    que nao rodou a carga do acervo) e estar **vazia** levam a mesma decisao —
    nao ha' com que conferir o municipio, entao nao se deriva. `crc_carga` tem
    a irma desta e so' pergunta a segunda, porque la' o esquema inteiro ja'
    existe; aqui o assento se lavra em banco que pode nao ter nem a tabela.
    """
    bd = banco(con)
    if not bd.tem_tabela("ib_municipios"):
        return False
    return bd.um("SELECT 1 AS um FROM ib_municipios LIMIT 1") is not None


def _naturalidade_do_titular(con: Any, assento_id: int,
                             especie: str, declarada: Any) -> dict:
    """Preenche a naturalidade da PESSOA a partir do que o termo declara.

    **O DEFEITO QUE ISTO FECHA — 22/09/2026.** A CRC reteve 19 dos 47
    nascimentos pendentes, e **17 pelo mesmo motivo**: «o municipio de
    nascimento do registrado nao esta na ficha». A naturalidade estava escrita
    — no campo do ASSENTO —, e a carga le a da PESSOA. Dois campos para a
    mesma coisa, e o balcao preenchia so' um: **todo assento novo saia
    retido**, um por dia, de 16 a 22/09.

    **SO' GRAVA O QUE O CADASTRO DO IBGE CONFIRMA**, e e' esta a guarda que
    torna isto defensavel: `ibge_geracao.lugar` recusa escolher municipio
    parecido, e o que ele nao acha fica vazio — a carga entao retem com a
    mensagem de grafia, que e' a rede que ja' existia. Gravar o nome cru faria
    o sistema afirmar um municipio que ninguem conferiu, **no campo que sobe
    para uma Central nacional**.

    **E NAO SOBRESCREVE O QUE ALGUEM ESCREVEU.** Campo ja' preenchido e'
    resposta de uma pessoa; derivar por cima dele apagaria a correcao que ela
    fez justamente porque a derivacao estava errada.
    """
    papel = TITULAR_DA_NATURALIDADE.get(especie)
    if not papel:
        return {"gravou": False, "motivo": "a espécie não tem naturalidade"}
    cidade, uf = municipio_da_naturalidade(declarada)
    if not cidade:
        return {"gravou": False, "motivo": "a naturalidade declarada está vazia"}
    bd = banco(con)
    pessoa = bd.um(
        """SELECT id, naturalidade_cidade FROM rc_pessoas
           WHERE assento_id = %s AND papel = %s ORDER BY id LIMIT 1""",
        (int(assento_id), papel))
    if not pessoa:
        return {"gravou": False, "motivo": f"o assento não tem {papel.lower()}"}
    if ("" if pessoa["naturalidade_cidade"] is None
            else str(pessoa["naturalidade_cidade"]).strip()):
        return {"gravou": False, "motivo": "a pessoa já tem naturalidade"}
    # **SEM O CADASTRO DO IBGE NAO SE DERIVA NADA, e isso nao e' zelo: e' a
    # regra «instalacao nova nasce funcionando».** `ib_municipios` so' se
    # popula pela carga do acervo; num banco que ainda nao a rodou a consulta
    # estoura com «no such table», e lavrar assento passaria a derrubar a
    # transacao inteira por causa de uma tabela de estatistica. Foram os testes
    # do proprio modulo que pegaram isto — eles montam o banco so' com o nucleo
    # e o Registro Civil, que e' o que uma casa recem-instalada tem.
    if not _tem_municipios(bd):
        return {"gravou": False, "cidade": cidade, "uf": uf,
                "motivo": "o cadastro de municípios do IBGE não foi carregado"}
    achado = IBGEG.lugar(con, cidade, uf)
    if not achado.get("achou"):
        return {"gravou": False, "cidade": cidade, "uf": uf,
                "motivo": "o município não está no cadastro do IBGE"}
    bd.escrever(
        """UPDATE rc_pessoas SET naturalidade_cidade = %s, naturalidade_uf = %s
           WHERE id = %s""", (cidade, uf or achado.get("uf") or None,
                              int(pessoa["id"])))
    return {"gravou": True, "cidade": cidade, "uf": uf,
            "codigo_ibge": achado.get("codigo_ibge")}


def anotar_do_termo(con: Any, assento_id: int, *,
                    especie: str | None = None,
                    cor_raca: Any = None, hora_fato: Any = None,
                    local_fato_nome: Any = None,
                    local_fato_endereco: Any = None,
                    local_fato_municipio: Any = None,
                    naturalidade_declarada: Any = None,
                    causa_morte: Any = None, atestante: Any = None,
                    atestante_documento: Any = None,
                    local_sepultamento: Any = None,
                    testamento: Any = None,
                    **da_lei: Any) -> dict:
    """Grava o que o TERMO pede e a certidao imprime. ESCREVE.

    `da_lei` são os campos de `CAMPOS_DA_LEI` (13/10/2026); outro nome é
    recusado, como a coluna que não cabe na espécie.

    E a irma de `anotar_para_o_ibge`, e a diferenca entre as duas e o
    destino: o que entra la serve a estatistica e **nao sai no papel que o
    cliente leva**; o que entra aqui sai — esta no teor do termo e na certidao.

    A COR OU RACA E LISTA FECHADA (`CORES_E_RACAS`), e a razao e a CRC: ela
    aceita seis palavras e recusa a carga inteira por causa de uma setima,
    meses depois, sem dizer qual linha. Recusar aqui, com o declarante na
    frente, custa uma pergunta; recusar la custa um trimestre.

    O QUE NAO SE INFORMA FICA NULO. Preencher «ignorada» por conta propria
    seria afirmar que se perguntou — e «ignorada» e uma resposta legitima que
    alguem pode ter dado.
    """
    bd = banco(con)
    linha = bd.um("SELECT especie FROM rc_assentos WHERE id = %s",
                  (int(assento_id),))
    if not linha:
        raise RcError(f"O assento {assento_id} não existe.")
    especie = (especie or linha["especie"] or "").strip().upper()
    permitidos = CAMPOS_DO_TERMO_POR_ESPECIE.get(especie, ())

    valores: dict[str, Any] = {}
    if cor_raca not in (None, ""):
        chave = str(cor_raca).strip().upper()
        if chave not in CORES_E_RACAS:
            raise RcError(
                f"A cor ou raça «{cor_raca}» não está entre as que a Central "
                f"aceita: " + ", ".join(CORES_E_RACAS.values()) + ".")
        valores["cor_raca"] = chave
    for nome, valor in (("hora_fato", hora_fato),
                        ("local_fato_nome", local_fato_nome),
                        ("local_fato_endereco", local_fato_endereco),
                        ("local_fato_municipio", local_fato_municipio),
                        ("naturalidade_declarada", naturalidade_declarada),
                        ("causa_morte", causa_morte),
                        ("atestante", atestante),
                        ("atestante_documento", atestante_documento),
                        ("local_sepultamento", local_sepultamento),
                        ("testamento", testamento),
                        *da_lei.items()):
        if nome not in CAMPOS_DA_LEI and nome in da_lei:
            raise RcError(f"Campo desconhecido no termo: {nome}.")
        texto = ("" if valor is None else str(valor)).strip()
        if texto:
            valores[nome] = texto

    fora = [c for c in valores if c not in permitidos]
    if fora:
        raise RcError(
            f"Estes campos não cabem num assento de "
            f"{especie.lower()}: {', '.join(sorted(fora))}.")
    if valores:
        bd.escrever(
            "UPDATE rc_assentos SET "
            + ", ".join(f"{c} = %s" for c in valores)
            + " WHERE id = %s", (*valores.values(), int(assento_id)))
    # A NATURALIDADE DA PESSOA SAI DA DECLARADA, e isso mora aqui — no
    # dominio — e nao na rota: o campo que a CRC le e' o da PESSOA, e quem
    # digita preenche o do ASSENTO. Ver `_naturalidade_do_titular`.
    naturalidade = {"gravou": False, "motivo": "não foi informada"}
    if "naturalidade_declarada" in valores:
        naturalidade = _naturalidade_do_titular(
            con, assento_id, especie, valores["naturalidade_declarada"])
    return {"gravados": sorted(valores), "quantos": len(valores),
            "naturalidade": naturalidade}


def anotar_para_o_ibge(con: Any, assento_id: int, *,
                       especie: str | None = None,
                       local_nascimento: Any = None, gemeo: Any = None,
                       dnv: Any = None, numero_do: Any = None,
                       natureza_obito: Any = None, local_obito: Any = None,
                       usuario: str | None = None) -> dict:
    """Grava no assento o que so a remessa do IBGE usa. ESCREVE.

    NAO E CAMPO DE CERTIDAO, e por isso mora a parte do resto: nada do que
    entra aqui sai no papel que o cliente leva. Serve a estatistica, e a
    estatistica e obrigacao da serventia (Lei 6.015/1973, art. 49).

    RECUSA CODIGO FORA DO CATALOGO. O catalogo de `LOCAL-NASC` pula do 3 para
    o 5, e o de `GEMEO` do 3 para o 9 — quem digitar 4 acerta o tipo do campo
    e erra o conteudo. Sem esta conferencia, o IBGE recusaria o trimestre
    inteiro meses depois, sem dizer qual linha.

    O QUE NAO SE INFORMA FICA NULO, e a remessa mostra o que falta. Preencher
    com «ignorado» por conta propria seria afirmar que se perguntou.
    """
    bd = banco(con)
    linha = bd.um("SELECT especie FROM rc_assentos WHERE id = %s",
                  (int(assento_id),))
    if not linha:
        raise RcError(f"O assento {assento_id} não existe.")
    especie = (especie or linha["especie"] or "").strip().upper()
    permitidos = CAMPOS_DO_IBGE_POR_ESPECIE.get(especie, ())

    valores: dict[str, Any] = {}
    if local_nascimento not in (None, ""):
        codigo = _codigo_do_ibge(local_nascimento, IBGE.LOCAL_DO_NASCIMENTO,
                                 "o local do nascimento")
        valores["ibge_local_nascimento"] = codigo
    if gemeo not in (None, ""):
        valores["ibge_gemeo"] = _codigo_do_ibge(gemeo, IBGE.GEMEO,
                                                "o parto gemelar")
    if (dnv or "").strip() if isinstance(dnv, str) else dnv:
        valores["dnv"] = str(dnv).strip()
    if (numero_do or "").strip() if isinstance(numero_do, str) else numero_do:
        valores["numero_do"] = str(numero_do).strip()
    # O CATALOGO DO OBITO NAO E O DO NASCIMENTO, e a diferenca e o `4`: o obito
    # tem «via publica» e o nascimento nao. Usar um pelo outro mandaria
    # «outros» onde o IBGE espera «via publica» — que e a informacao que ele
    # mais quer, porque e onde a morte violenta acontece.
    if natureza_obito not in (None, ""):
        valores["ibge_natureza_obito"] = _codigo_do_ibge(
            natureza_obito, IBGE.NATUREZA_DO_OBITO, "a natureza do óbito")
    if local_obito not in (None, ""):
        valores["ibge_local_obito"] = _codigo_do_ibge(
            local_obito, IBGE.LOCAL_DO_OBITO, "o local do óbito")

    fora = [c for c in valores if c not in permitidos]
    if fora:
        raise RcError(
            f"Assento de {NOME_DA_ESPECIE.get(especie, especie).lower()} não "
            f"tem esses dados do IBGE. O que ele tem é: "
            f"{', '.join(permitidos) or 'nada'}.")
    if not valores:
        return {}
    bd.escrever(
        f"UPDATE rc_assentos SET {','.join(f'{c} = %s' for c in valores)} "
        f"WHERE id = %s", (*valores.values(), int(assento_id)))
    return valores


def _codigo_do_ibge(valor: Any, catalogo: dict, o_que: str) -> int:
    try:
        codigo = int(valor)
    except (TypeError, ValueError):
        raise RcError(f"Código do IBGE inválido para {o_que}: {valor!r}.") from None
    if codigo not in catalogo:
        opcoes = ", ".join(f"{k} = {v}" for k, v in sorted(catalogo.items()))
        raise RcError(
            f"{codigo} não é código do IBGE para {o_que}. Os que existem são: "
            f"{opcoes}.")
    return codigo


# ---------------------------------- a pessoa de quem o assento e
#
# ATE 28/08/2026 `rc_pessoas` guardava PAI, MAE e AVOS — que a carga do acervo
# trouxe porque a certidao de nascimento os cobrou — e nao guardava o
# registrado, os nubentes nem o falecido. O assento tinha o NOME deles e mais
# nada, e isso travava duas coisas ao mesmo tempo: a certidao de casamento e a
# de obito, que DESCREVEM essas pessoas, e a remessa do IBGE, que pede sexo,
# data de nascimento, naturalidade, residencia e estado civil delas.
#
# O PAPEL SAI DA ESPECIE, e nao do chamador. E a mesma regra da serie: deixar o
# balcao escolher o papel e deixar gravar um NUBENTE num assento de obito.
PAPEIS_DA_ESPECIE: dict[str, tuple[str, ...]] = {
    # A FILIACAO ENTROU EM 30/08/2026, E A FALTA DELA ERA UM BURACO NO BALCAO.
    #
    #   Medido na producao: a carga do acervo gravou **235 PAI, 218 MAE, 631
    #   avos, 117 DECLARANTE e 20 TESTEMUNHA** — e esta lista, que governa a
    #   lavratura NOVA, so permitia o registrado. Ou seja: o acervo tinha
    #   filiacao e o ato novo nao conseguia ter.
    #
    #   **Sem filiacao nao ha certidao de nascimento**: ela e o que a certidao
    #   diz depois do nome, e o termo desta casa a escreve como «filho de ...»,
    #   com os avos logo em seguida.
    "NASCIMENTO": ("REGISTRADO", "PAI", "MAE",
                   "AVO_PATERNO", "AVO_PATERNA",
                   "AVO_MATERNO", "AVO_MATERNA",
                   "DECLARANTE", "TESTEMUNHA",
                   # A SEGUNDA TESTEMUNHA É DO REGISTRO TARDIO (art. 249, II):
                   # o requerimento é assinado por duas. 21/10/2026. A
                   # segunda do parto sem assistência médica (LD01) também.
                   "TESTEMUNHA2"),
    "NATIMORTO": ("REGISTRADO", "PAI", "MAE", "DECLARANTE", "TESTEMUNHA"),
    # NO CASAMENTO A FILIACAO E DOS DOIS, E SAO QUATRO PESSOAS.
    #
    #   **Ate 31/08/2026 esta linha declarava so os nubentes e as testemunhas**,
    #   e `acervo_carga.papeis_da_filiacao` ja devolvia os quatro papeis abaixo
    #   — a carga gravava o que a especie nao reconhecia, e **a tela de lavrar
    #   casamento nao oferecia filiacao nenhuma**. O art. 70 da Lei 6.015/1973 a
    #   exige, e o termo desta casa a marca como campo exigido.
    #
    #   E o mesmo defeito que o nascimento teve, no casamento: peca pronta de um
    #   lado, e o outro lado sem saber dela.
    "CASAMENTO": ("NUBENTE1", "NUBENTE2",
                  "PAI_NUBENTE1", "MAE_NUBENTE1",
                  "PAI_NUBENTE2", "MAE_NUBENTE2", "TESTEMUNHA"),
    # O RELIGIOSO E O MESMO ATO, NOUTRO LIVRO — os papeis sao os mesmos.
    "CASAMENTO_RELIGIOSO": ("NUBENTE1", "NUBENTE2",
                            "PAI_NUBENTE1", "MAE_NUBENTE1",
                            "PAI_NUBENTE2", "MAE_NUBENTE2", "TESTEMUNHA"),
    "OBITO": ("FALECIDO", "PAI", "MAE", "DECLARANTE", "TESTEMUNHA"),
    # O LIVRO E — 13/10/2026, ordem do oficial («preparemos o ambiente para
    # viabilizar o próximo registro e todos os modelos, nos moldes da casa»).
    # Até aqui as sete espécies não tinham papel nenhum: o registro do Livro E
    # guardava só o NOME, e o termo dizia «lavrou-se o registro referente a
    # Fulano» sem curador, sem sentença, sem nada do que a lei manda constar.
    #
    #   Os papéis são os que a Lei 6.015/1973 nomeia: os pais ou o TUTOR na
    #   emancipação (art. 90, 3º); o CURADOR e o REQUERENTE na interdição
    #   (art. 92, 4º e 5º) e na ausência (art. 94, 4º e 6º); os COMPANHEIROS e
    #   os pais deles na união estável (art. 94-A, II e III). **Não há
    #   declarante nem testemunha**: o registro se faz pelo traslado do título,
    #   «sem dependência da presença de testemunhas» (art. 90, caput).
    #
    #   A TUTELA NÃO TEM LISTA PRÓPRIA NA LEI — os papéis seguem a interdição
    #   por analogia (art. 92), e isso fica dito no modelo.
    "EMANCIPACAO": ("REGISTRADO", "MAE", "PAI", "TUTOR"),
    "INTERDICAO": ("REGISTRADO", "CURADOR", "REQUERENTE"),
    "AUSENCIA": ("REGISTRADO", "CURADOR", "REQUERENTE"),
    "TUTELA": ("REGISTRADO", "MAE", "PAI", "TUTOR"),
    "UNIAO_ESTAVEL": ("COMPANHEIRO1", "COMPANHEIRO2",
                      "MAE_COMPANHEIRO1", "PAI_COMPANHEIRO1",
                      "MAE_COMPANHEIRO2", "PAI_COMPANHEIRO2"),
    "OPCAO_NACIONALIDADE": ("REGISTRADO", "MAE", "PAI"),
    "OUTRO": ("REGISTRADO",),
}

#: O QUE SE REGISTRA NO LIVRO E — o título que o balcão tem na mão. A lista é
#: da lei, por espécie: a interdição, a ausência, a tutela e a opção de
#: nacionalidade só entram por sentença (arts. 92, 94; art. 32, § 4º); a
#: emancipação, por sentença ou por escritura de outorga dos pais (art. 90;
#: CN art. 329); a união estável, pelos três (art. 94-A).
TITULOS_DO_LIVRO_E: dict[str, tuple[str, ...]] = {
    "EMANCIPACAO": ("SENTENCA", "ESCRITURA"),
    "INTERDICAO": ("SENTENCA",),
    "AUSENCIA": ("SENTENCA",),
    "TUTELA": ("SENTENCA",),
    "UNIAO_ESTAVEL": ("ESCRITURA", "TERMO", "SENTENCA"),
    "OPCAO_NACIONALIDADE": ("SENTENCA",),
}
NOME_DO_TITULO: dict[str, str] = {
    "SENTENCA": "Sentença (mandado ou ofício judicial)",
    "ESCRITURA": "Escritura pública",
    "TERMO": "Termo declaratório lavrado nesta serventia",
}

# O ROTULO DE CADA PAPEL NA TELA.
#
#   **O E-OFICIO NAO ESCREVE «PAI» E «MAE»**: escreve `Filiação 1` e
#   `Filiação 2`, com o **sexo** como campo a parte, e chama os avos de
#   `Progenitores`. E o vocabulario correto — ha assentos de casais do mesmo
#   sexo, e «pai»/«mae» nao os descreve.
#
#   AS CHAVES CONTINUAM `PAI`/`MAE` PORQUE O ACERVO TEM 453 REGISTROS ASSIM, e
#   trocar a chave renomearia o passado. O que muda e o que se LE na tela.
#   **Se o oficial preferir trocar as chaves tambem, e decisao dele** — e
#   custaria uma migracao, nao uma reescrita.
#   **A FILIACAO 1 E A MAE — decisao do oficial em 30/08/2026:**
#
#       «Chaves melhor deixar em filiacao 1 e 2, indicando a 1 para mae entre
#        parenteses (mera indicacao).»
#
#   O PARENTESE E INDICACAO, E NAO REGRA. Ele diz a quem preenche qual costuma
#   ser cada uma, sem impor: ha assentos de casais do mesmo sexo — seis medidos
#   nesta casa —, e ali «(mae)» e so uma dica de onde a maioria escreve.
#
#   **E O CONTRARIO DO E-OFICIO**, o que vale registrar: la a filiacao 1 e o
#   PAI (medido no acervo bruto: 162 masculinas contra 30 femininas na 1). A
#   escolha aqui foi do oficial, e e dele que vale.
#
#   AS CHAVES GRAVADAS continuam `MAE` e `PAI`. Troca-las exigiria migrar 453
#   registros e mexer, de uma vez, na certidao, na carga do acervo e no que ja
#   foi para a CRC — e a casa nao tem mecanismo de migracao de DADOS, so de
#   coluna nova. **Ninguem ve essas chaves**: o que se le na tela e no termo e
#   o rotulo abaixo. Se o oficial quiser a troca no banco tambem, e um trabalho
#   proprio, com backup e conferencia, e nao um efeito colateral deste.
ROTULO_DO_PAPEL: dict[str, str] = {
    "REGISTRADO": "Registrado",
    "FALECIDO": "Falecido",
    "NUBENTE1": "Primeiro nubente",
    "NUBENTE2": "Segundo nubente",
    # OS QUATRO DO CASAMENTO. A convencao e a que o oficial escolheu em
    # 30/08/2026 — «filiacao 1 e 2, indicando a 1 para mae entre parenteses
    # (mera indicacao)» —, e aqui ela se aplica a cada nubente.
    "MAE_NUBENTE1": "Filiação 1 do primeiro nubente (mãe)",
    "PAI_NUBENTE1": "Filiação 2 do primeiro nubente (pai)",
    "MAE_NUBENTE2": "Filiação 1 do segundo nubente (mãe)",
    "PAI_NUBENTE2": "Filiação 2 do segundo nubente (pai)",
    "MAE": "Filiação 1 (mãe)",
    "PAI": "Filiação 2 (pai)",
    "AVO_MATERNO": "Progenitor 1 da filiação 1",
    "AVO_MATERNA": "Progenitor 2 da filiação 1",
    "AVO_PATERNO": "Progenitor 1 da filiação 2",
    "AVO_PATERNA": "Progenitor 2 da filiação 2",
    "DECLARANTE": "Declarante",
    "TESTEMUNHA": "Testemunha",
    # Sem «(registro tardio)» no rótulo: no NASCIMENTO a segunda gaveta grava
    # este papel também no parto sem assistência médica (LD01).
    "TESTEMUNHA2": "Segunda testemunha",
    # O LIVRO E — 13/10/2026. Os companheiros seguem a convenção do casamento
    # («filiação 1 e 2, indicando a 1 para mãe entre parênteses»).
    "TUTOR": "Tutor(a)",
    "CURADOR": "Curador(a)",
    "REQUERENTE": "Requerente (quem promoveu o processo)",
    "COMPANHEIRO1": "Primeiro(a) companheiro(a)",
    "COMPANHEIRO2": "Segundo(a) companheiro(a)",
    "MAE_COMPANHEIRO1": "Filiação 1 do primeiro companheiro (mãe)",
    "PAI_COMPANHEIRO1": "Filiação 2 do primeiro companheiro (pai)",
    "MAE_COMPANHEIRO2": "Filiação 1 do segundo companheiro (mãe)",
    "PAI_COMPANHEIRO2": "Filiação 2 do segundo companheiro (pai)",
}

# O PREFIXO DE CADA PAPEL NO FORMULARIO.
#
#   **A TELA E O MODULO PRECISAM DO MESMO PREFIXO, E POR ISSO ELE MORA AQUI.**
#   Ate 30/08/2026 a rota deduzia o prefixo pelo NUMERO de papeis — «se for um
#   so, chama-se pessoa; se forem dois, nubente1 e nubente2» —, e essa deducao
#   quebrava no instante em que a especie passasse a ter tres. Passou a ter
#   nove no mesmo dia.
#
#   `pessoa` fica para o registrado e o falecido porque a macro da tela ja usa
#   esse nome, e renomea-lo nao acrescenta nada.
def idade_na_data(data_nascimento: Any, data_do_fato: Any) -> int | None:
    """Quantos anos a pessoa tinha naquele dia. Só calcula.

    RELATO #37, ITEM 5, de 31/08/2026 — e ela reverte uma decisão que estava
    escrita neste projeto. A macro da tela dizia que a idade **não** se
    calcula, porque «onde a data de nascimento falta, o cálculo erraria num
    papel assinado». A objeção era sobre o campo FALTAR; o oficial tornou as
    duas datas obrigatórias no nascimento, e ali ela deixa de valer.

    **DESCONTA O ANIVERSÁRIO**, e isso não é detalhe: o E-Ofício fazia
    `ano − ano` e mandava ao IBGE a idade de 3 dos 11 falecidos com um ano a
    mais (medido em 28/08/2026, ver `REMESSA_IBGE_CONFERIDA.md`). É o mesmo
    erro que este projeto já pagou uma vez.

    Devolve None quando falta uma das datas ou quando elas não fazem sentido
    juntas — data do fato anterior ao nascimento é dado errado, e devolver um
    número negativo o esconderia dentro de um papel assinado.
    """
    nasceu = _data_iso(data_nascimento)
    fato = _data_iso(data_do_fato)
    if not nasceu or not fato or fato < nasceu:
        return None
    anos = fato.year - nasceu.year
    if (fato.month, fato.day) < (nasceu.month, nasceu.day):
        anos -= 1
    return anos if anos >= 0 else None


def _data_iso(valor: Any) -> date | None:
    """`2026-08-31` -> `date`. Devolve None para o que não é data."""
    try:
        return date.fromisoformat(str(valor or "").strip()[:10])
    except ValueError:
        return None


PREFIXO_DO_PAPEL: dict[str, str] = {
    "REGISTRADO": "pessoa", "FALECIDO": "pessoa",
    "NUBENTE1": "nubente1", "NUBENTE2": "nubente2",
    # A FILIACAO 1 E A MAE — por isso `filiacao1` aponta para `MAE`.
    "MAE_NUBENTE1": "filiacao1n1",
    "PAI_NUBENTE1": "filiacao2n1",
    "MAE_NUBENTE2": "filiacao1n2",
    "PAI_NUBENTE2": "filiacao2n2",
    "MAE": "filiacao1", "PAI": "filiacao2",
    "AVO_MATERNO": "prog1f1", "AVO_MATERNA": "prog2f1",
    "AVO_PATERNO": "prog1f2", "AVO_PATERNA": "prog2f2",
    "DECLARANTE": "declarante", "TESTEMUNHA": "testemunha",
    "TESTEMUNHA2": "testemunha2",
    # O LIVRO E — 13/10/2026.
    "TUTOR": "tutor", "CURADOR": "curador", "REQUERENTE": "requerente",
    "COMPANHEIRO1": "companheiro1", "COMPANHEIRO2": "companheiro2",
    "MAE_COMPANHEIRO1": "filiacao1c1", "PAI_COMPANHEIRO1": "filiacao2c1",
    "MAE_COMPANHEIRO2": "filiacao1c2", "PAI_COMPANHEIRO2": "filiacao2c2",
}

# O PAPEL QUE A TELA PERGUNTA MAIS DE UMA VEZ — LD01, 21/10/2026. O casamento
# se celebra com duas testemunhas pelo menos (CC art. 1.534; LRP art. 70, 6º),
# e o parto sem assistência médica pede duas no assento (LRP art. 54, 9º); a
# tela tinha uma gaveta só. A segunda gaveta tem prefixo próprio e grava o
# MESMO papel: quem lê o assento conta as testemunhas pelo papel.
PREFIXOS_A_MAIS_DO_PAPEL: dict[str, tuple[str, ...]] = {
    "TESTEMUNHA": ("testemunha2",),
}


def prefixos_do_papel(papel: str, especie: Any = "") -> tuple[str, ...]:
    """As gavetas da tela que gravam aquele papel, na ordem. Só calcula.

    **A GAVETA A MAIS CEDE O LUGAR AO PAPEL PRÓPRIO.** No NASCIMENTO a segunda
    testemunha é papel seu, `TESTEMUNHA2` (o registro tardio, art. 249, II —
    21/10/2026, hotfix do servidor), e a gaveta `testemunha2` grava ESSE
    papel; nas outras espécies ela continua sendo a segunda `TESTEMUNHA` do
    LD01. Sem a espécie, as gavetas são as de sempre."""
    proprios = {PREFIXO_DO_PAPEL[p] for p in PAPEIS_DA_ESPECIE.get(
        str(especie or "").strip().upper(), ()) if p != papel}
    return (PREFIXO_DO_PAPEL[papel],
            *(g for g in PREFIXOS_A_MAIS_DO_PAPEL.get(papel, ())
              if g not in proprios))


# A ORDEM EM QUE ELES APARECEM na ficha e na certidao.
#
#   E a ordem do TERMO, e nao a alfabetica: primeiro de quem e o assento,
#   depois a filiacao, depois os avos, e por fim quem declarou e quem
#   testemunhou — que e como o texto do livro os apresenta.
ORDEM_DO_PAPEL: dict[str, int] = {
    "REGISTRADO": 0, "FALECIDO": 0, "NUBENTE1": 0, "NUBENTE2": 1,
    # A FILIACAO 1 VEM PRIMEIRO, e a 1 e a mae.
    "MAE_NUBENTE1": 2,
    "PAI_NUBENTE1": 3,
    "MAE_NUBENTE2": 4,
    "PAI_NUBENTE2": 5,
    "MAE": 2, "PAI": 3,
    "AVO_MATERNO": 4, "AVO_MATERNA": 5,
    "AVO_PATERNO": 6, "AVO_PATERNA": 7,
    "DECLARANTE": 8, "TESTEMUNHA": 9, "TESTEMUNHA2": 10,
    # O LIVRO E: o titular, a filiação, e depois quem a lei põe ao lado dele.
    "COMPANHEIRO1": 0, "COMPANHEIRO2": 1,
    "MAE_COMPANHEIRO1": 2, "PAI_COMPANHEIRO1": 3,
    "MAE_COMPANHEIRO2": 4, "PAI_COMPANHEIRO2": 5,
    "TUTOR": 6, "CURADOR": 6, "REQUERENTE": 7,
}

# O QUE SE GUARDA DE CADA UMA. Sao as colunas de `rc_pessoas` que a certidao e
# o IBGE usam — e nao todas: quem grava o que nao se pergunta grava vazio.
CAMPOS_DA_PESSOA: tuple[str, ...] = (
    "nome", "nome_pos", "sexo", "documento_tipo", "documento_numero",
    # O ORGAO EMISSOR. A coluna existia e nao estava nesta lista, o que a
    # deixava inalcancavel: `_pessoas_do_formulario` le exatamente estes nomes.
    "documento_orgao",
    "profissao", "nacionalidade", "naturalidade_cidade", "naturalidade_uf",
    "naturalidade_pais", "data_nascimento", "estado_civil", "endereco",
    "bairro", "cidade", "uf", "cep",
    # A IDADE NA OCASIAO DO FATO — **perguntada, e nao calculada**.
    #
    #   Ela esta no termo desta casa: «A genitora na ocasiao do parto contava
    #   29 anos de idade» (termo nº 8.369). E esta no print do obito do
    #   E-Oficio, como campo proprio ao lado da data de nascimento.
    #
    #   CALCULA-LA SERIA PIOR QUE PERGUNTA-LA: onde a data de nascimento falta
    #   — e ela falta em muito assento antigo — o calculo daria idade errada
    #   num papel assinado. O E-Oficio tambem deixa digitar.
    "idade_no_fato",
)


# TESTEMUNHA_FANTASMA_20261009: so o TITULAR pode herdar o nome do
# assento (o assento leva o nome dele). Qualquer outro papel sem nome e
# recusado - antes virava uma testemunha com o nome do registrado.
PAPEIS_TITULARES: frozenset = frozenset({"REGISTRADO", "FALECIDO"})


def registrar_pessoa(con: Any, assento_id: int, *,
                     papel: str, especie: Any = None, agora: str,
                     usuario: str | None = None, **campos: Any) -> int:
    """Grava a pessoa de quem o assento e. ESCREVE.

    O PAPEL TEM DE CABER NA ESPECIE, e a recusa e por dever: gravar um NUBENTE
    num assento de obito nao daria erro nenhum na hora — daria uma certidao
    errada meses depois.

    NAO SE INVENTA DATA IMPOSSIVEL. Ninguem nasce depois do ato que o registra,
    e no acervo desta casa 21 das 244 pessoas «nasciam» — o campo em branco
    pegava a data da digitacao. Aqui a recusa e no balcao, onde ainda da para
    perguntar ao declarante.
    """
    papel = str(papel or "").strip().upper()
    bd = banco(con)
    linha = bd.um(
        "SELECT especie, nome, data_ato, data_fato FROM rc_assentos WHERE id = %s",
        (int(assento_id),))
    if not linha:
        raise RcError(f"O assento {assento_id} não existe.")
    especie = str(especie or linha["especie"] or "").strip().upper()
    permitidos = PAPEIS_DA_ESPECIE.get(especie, ())
    if papel not in permitidos:
        raise RcError(
            f"Assento de {NOME_DA_ESPECIE.get(especie, especie).lower()} não "
            f"tem {papel or 'esse papel'}. Os que ele tem são: "
            f"{', '.join(permitidos) or 'nenhum'}.")

    valores = {c: (str(campos.get(c)).strip() if campos.get(c) not in
                   (None, "") else None) for c in CAMPOS_DA_PESSOA}
    nome = valores.get("nome") or (
        (linha["nome"] or "").strip() if papel in PAPEIS_TITULARES
        else "")
    if not nome:
        raise RcError(
            f"A pessoa não entra sem nome "
            f"({ROTULO_DO_PAPEL.get(papel, papel).lower()}). "
            "Linha sem nome numa certidão é pior "
            "que ausência: afirma que há alguém e não diz quem.")
    valores["nome"] = nome

    nascimento = valores.get("data_nascimento")
    limite = min([d for d in (linha["data_fato"], linha["data_ato"]) if d],
                 default=None)
    if nascimento and limite and str(nascimento)[:10] > str(limite)[:10]:
        raise RcError(
            f"A data de nascimento ({nascimento}) é posterior ao próprio ato "
            f"({str(limite)[:10]}). Confira com quem está no balcão — data "
            f"errada na certidão não se desfaz depois.")

    # O INSERT SE MONTA DE `CAMPOS_DA_PESSOA`, E NAO A MAO.
    #
    #   **DUAS LISTAS DIVERGEM NO PRIMEIRO CONSERTO**, e esta divergiu: ate
    #   30/08/2026 as colunas eram escritas uma a uma aqui, e `documento_orgao`
    #   e `idade_no_fato` existiam no banco, existiam na tela, e nao entravam
    #   no INSERT. O dado era digitado pelo escrevente e sumia sem erro nenhum
    #   — que e o pior jeito de um dado sumir.
    #
    #   Montando daqui, acrescentar campo passa a ser uma linha na lista, e o
    #   INSERT acompanha por construcao.
    valores["sexo"] = _sexo_da_pessoa(valores["sexo"])
    valores["data_nascimento"] = nascimento
    colunas = list(CAMPOS_DA_PESSOA)
    return int(bd.escrever(
        "INSERT INTO rc_pessoas(assento_id, papel, nome_norm, ordem, origem,"
        " criado_em, " + ", ".join(colunas) + ")"
        " VALUES (%s, %s, %s, %s, 'MANUAL', %s, "
        + ", ".join(["%s"] * len(colunas)) + ") RETURNING id",
        (int(assento_id), papel, normalizar_nome(nome),
         ORDEM_DO_PAPEL.get(papel, 0), agora,
         *[valores[c] for c in colunas]))[0]["id"])


def _sexo_da_pessoa(v: Any) -> str | None:
    """`Masculino`, `M`, `m` -> `M`. O que nao for M nem F fica vazio.

    O SISTEMA GUARDA `M`/`F` — medido no banco de producao —, e o acervo guarda
    `Masculino`/`Feminino`. Guardar as duas formas faria a busca achar metade.
    """
    letra = str(v or "").strip().upper()[:1]
    return letra if letra in ("M", "F") else None


def pessoas_do_assento(con: Any, assento_id: int,
                       papeis: Any = None) -> list[dict]:
    """As pessoas daquele assento, na ordem da certidao. So LE."""
    if papeis:
        return banco(con).ler(
            "SELECT * FROM rc_pessoas WHERE assento_id = %s "
            "AND papel = ANY(%s) ORDER BY ordem, id",
            (int(assento_id), list(papeis)))
    return banco(con).ler(
        "SELECT * FROM rc_pessoas WHERE assento_id = %s ORDER BY ordem, id",
        (int(assento_id),))



# -------------------------------- os requisitos da Lei 6.015/1973
#
# EM 01/09/2026 o oficial mandou: o servidor recusa assento sem cumprimento
# aos requisitos legais. Permitir no formulario DECLARAR que nao tem a
# informacao; nao lavrar em branco o que a lei dispoe.
#
# Branco nao e «ignorado». Branco e o defeito. IGNORADO / «nao tem» e
# declaracao — a mesma palavra que o IBGE desta casa ja usa.
#
# A CONFERENCIA MORA AQUI, e nao na tela: GET nao chama isto. Carga do
# acervo (origem que nao e MANUAL) traz o que o papel ja tem, e nao se
# recusa o passado por falta de um campo que o livro antigo nao trouxe.

PALAVRAS_DE_AUSENCIA = frozenset({
    "ignorado", "ignorada", "ignorados", "ignoradas",
    "nao tem", "nao tem a informacao", "nao tem informacao",
})


def e_declarado_ausente(valor: Any) -> bool:
    """IGNORADO / «não tem» é declaração, não é campo em branco."""
    t = " ".join(str(valor or "").strip().lower().split())
    t = "".join(c for c in unicodedata.normalize("NFD", t)
                if unicodedata.category(c) != "Mn")
    return t in PALAVRAS_DE_AUSENCIA


def _texto_preenchido(valor: Any, *, aceita_ignorado: bool = True) -> bool:
    t = str(valor or "").strip()
    if not t:
        return False
    if aceita_ignorado:
        return True
    return not e_declarado_ausente(t)


def _pessoa_do_papel(pessoas: list | None, papel: str) -> dict | None:
    alvo = str(papel or "").strip().upper()
    for p in pessoas or []:
        if str((p or {}).get("papel") or "").strip().upper() == alvo:
            return p
    return None


def _nome_do_papel(pessoas: list | None, papel: str) -> str:
    p = _pessoa_do_papel(pessoas, papel)
    return str((p or {}).get("nome") or "").strip()


def _falta_nome(pessoas: list | None, papel: str, rotulo: str,
                faltas: list[str]) -> None:
    if not _texto_preenchido(_nome_do_papel(pessoas, papel)):
        faltas.append(rotulo)


#: O artigo que cada espécie do Livro E cumpre — vai na recusa e no modelo.
ARTIGO_DO_LIVRO_E: dict[str, str] = {
    "EMANCIPACAO": "art. 90 da Lei nº 6.015/1973 e art. 329 do Código de Normas",
    "INTERDICAO": "art. 92 da Lei nº 6.015/1973 e art. 328 do Código de Normas",
    "AUSENCIA": "art. 94 da Lei nº 6.015/1973 e art. 328 do Código de Normas",
    "TUTELA": "art. 92 da Lei nº 6.015/1973, por analogia",
    "UNIAO_ESTAVEL": "art. 94-A da Lei nº 6.015/1973",
    "OPCAO_NACIONALIDADE": "art. 32, § 4º, da Lei nº 6.015/1973 e art. 327 "
                           "do Código de Normas",
}


def _conferir_o_livro_e(especie: str, assento: dict,
                        pessoas: list) -> None:
    """Recusa lavrar no Livro E sem o que o artigo da espécie exige. SÓ LÊ.

    **O QUE SE EXIGE É O QUE O REGISTRO NÃO EXISTE SEM**: quem é o titular, o
    título que se registra (sentença, escritura ou termo, com a data) e de
    onde ele veio — o juízo na sentença, o tabelionato na escritura —, e a
    pessoa que a sentença nomeou (curador, tutor). O resto do artigo — causa,
    limites, internação, tempo de ausência, os registros anteriores — é
    **condicional**: aparece no termo quando informado, e não trava.
    """
    faltas: list[str] = []
    if especie == "UNIAO_ESTAVEL":
        _falta_nome(pessoas, "COMPANHEIRO1", "primeiro(a) companheiro(a)", faltas)
        _falta_nome(pessoas, "COMPANHEIRO2", "segundo(a) companheiro(a)", faltas)
        if not _texto_preenchido(assento.get("regime_bens"),
                                 aceita_ignorado=False):
            faltas.append("regime de bens (art. 94-A, VII)")
    elif not (_texto_preenchido(_nome_do_papel(pessoas, "REGISTRADO"))
              or _texto_preenchido(assento.get("nome"))):
        faltas.append("nome de quem é o registro")

    titulo = str(assento.get("livro_e_titulo") or "").strip().upper()
    aceitos = TITULOS_DO_LIVRO_E[especie]
    if titulo not in aceitos:
        faltas.append("o título que se registra — "
                      + " ou ".join(NOME_DO_TITULO[t].lower() for t in aceitos))
    if not _texto_preenchido(assento.get("livro_e_titulo_data"),
                             aceita_ignorado=False):
        faltas.append("a data do título")
    if titulo == "SENTENCA" and not _texto_preenchido(
            assento.get("livro_e_juizo"), aceita_ignorado=False):
        faltas.append("o juízo (vara) que proferiu a sentença")
    if titulo == "ESCRITURA" and not _texto_preenchido(
            assento.get("livro_e_tabelionato"), aceita_ignorado=False):
        faltas.append("o tabelionato em que a escritura foi lavrada")

    if especie in ("INTERDICAO", "AUSENCIA"):
        _falta_nome(pessoas, "CURADOR", "o curador nomeado", faltas)
    elif especie == "TUTELA":
        _falta_nome(pessoas, "TUTOR", "o tutor nomeado", faltas)
    elif especie == "EMANCIPACAO" and not any(
            _texto_preenchido(_nome_do_papel(pessoas, p))
            for p in ("MAE", "PAI", "TUTOR")):
        faltas.append("os pais ou o tutor (art. 90, 3º)")

    if faltas:
        raise RcError(
            f"Não se lavra o registro em branco "
            f"({ARTIGO_DO_LIVRO_E[especie]}). Falta: "
            f"{'; '.join(faltas)}.")


def e_tardio(valor: Any) -> bool:
    """A marca do registro tardio, como a tela e o banco a escrevem. Só lê."""
    return str(valor or "").strip().upper() in ("1", "SIM", "TRUE", "ON")


def regra_das_testemunhas_do_tardio(assento: dict, pessoas: list | None) -> dict:
    """Se o tardio dispensa as testemunhas — art. 249, II. Só calcula.

    A régua é a de `rc_registro_tardio.dispensa_testemunhas` (menor de 12 anos
    **e** DNV, cumulativos); aqui só se tira a idade e a DNV do que a tela
    mandou. A idade é a do dia do registro, e **sem data de nascimento não há
    idade — e idade desconhecida não dispensa**.
    """
    import rc_registro_tardio as TARDIO
    titular = _pessoa_do_papel(pessoas, "REGISTRADO") or {}
    nasceu = titular.get("data_nascimento") or assento.get("data_fato")
    hoje = str(assento.get("data_ato") or date.today().isoformat())
    idade = idade_na_data(nasceu, hoje)
    tem_dnv = _texto_preenchido(assento.get("dnv"), aceita_ignorado=False)
    return {**TARDIO.dispensa_testemunhas(idade=idade, tem_dnv=tem_dnv),
            "idade": idade, "tem_dnv": tem_dnv}


def conferir_requisitos_legais(especie: Any, assento: dict | None = None,
                               pessoas: list | None = None) -> None:
    """Recusa lavrar em branco o que a Lei nº 6.015/1973 exige.

    IGNORADO / «não tem» conta como preenchido. Campo vazio não conta.
    Devolve None quando está em ordem; levanta RcError com a lista do
    que falta, em português de balcão.
    """
    especie = str(especie or "").strip().upper()
    assento = dict(assento or {})
    pessoas = list(pessoas or [])
    if especie in TITULOS_DO_LIVRO_E:
        return _conferir_o_livro_e(especie, assento, pessoas)
    if especie not in {"NASCIMENTO", "NATIMORTO", "CASAMENTO",
                       "CASAMENTO_RELIGIOSO", "OBITO"}:
        return

    faltas: list[str] = []
    data_fato = assento.get("data_fato")
    local = (assento.get("local_fato_nome")
             or assento.get("local_fato_endereco"))
    sexo = assento.get("sexo")
    if not _texto_preenchido(sexo):
        dados = assento.get("dados")
        if isinstance(dados, dict):
            sexo = dados.get("sexo")
        titular = (_pessoa_do_papel(pessoas, "REGISTRADO")
                   or _pessoa_do_papel(pessoas, "FALECIDO"))
        if titular and not _texto_preenchido(sexo):
            sexo = titular.get("sexo")

    def titular_ok(*papeis: str) -> bool:
        for papel in papeis:
            if _texto_preenchido(_nome_do_papel(pessoas, papel)):
                return True
        return _texto_preenchido(assento.get("nome"))

    if especie in {"NASCIMENTO", "NATIMORTO"}:
        artigo = ("art. 54 da Lei nº 6.015/1973" if especie == "NASCIMENTO"
                  else "art. 53 da Lei nº 6.015/1973")
        if not titular_ok("REGISTRADO"):
            faltas.append("nome de quem é o registro")
        if not _texto_preenchido(data_fato, aceita_ignorado=False):
            faltas.append("data do nascimento")
        if not _texto_preenchido(local):
            faltas.append("lugar do nascimento")
        if not _texto_preenchido(sexo):
            faltas.append("sexo")
        _falta_nome(pessoas, "MAE",
                    "filiação 1 (mãe) — preencha ou declare ignorado",
                    faltas)
        _falta_nome(pessoas, "PAI",
                    "filiação 2 (pai) — preencha ou declare ignorado",
                    faltas)
        _falta_nome(pessoas, "DECLARANTE", "declarante", faltas)
        if especie == "NASCIMENTO" and e_tardio(assento.get("registro_tardio")):
            artigo += " e art. 249 do Código de Normas (registro tardio)"
            regra = regra_das_testemunhas_do_tardio(assento, pessoas)
            if not regra["dispensada"]:
                _falta_nome(pessoas, "TESTEMUNHA",
                            "a primeira testemunha do requerimento (art. 249, II)",
                            faltas)
                _falta_nome(pessoas, "TESTEMUNHA2",
                            "a segunda testemunha do requerimento (art. 249, II)",
                            faltas)
        if especie == "NATIMORTO" and not _texto_preenchido(
                assento.get("numero_do"), aceita_ignorado=False):
            faltas.append("Declaração de Óbito (número da DO)")
    elif especie in ESPECIES_DE_CASAMENTO:
        artigo = ("art. 70 da Lei nº 6.015/1973" if especie == "CASAMENTO"
                  else "arts. 71 a 75 da Lei nº 6.015/1973")
        if not _texto_preenchido(data_fato, aceita_ignorado=False):
            faltas.append("data da celebração")
        _falta_nome(pessoas, "NUBENTE1", "primeiro nubente", faltas)
        _falta_nome(pessoas, "NUBENTE2", "segundo nubente", faltas)
        _falta_nome(pessoas, "MAE_NUBENTE1",
                    "filiação 1 do primeiro nubente — preencha ou declare ignorado",
                    faltas)
        _falta_nome(pessoas, "PAI_NUBENTE1",
                    "filiação 2 do primeiro nubente — preencha ou declare ignorado",
                    faltas)
        _falta_nome(pessoas, "MAE_NUBENTE2",
                    "filiação 1 do segundo nubente — preencha ou declare ignorado",
                    faltas)
        _falta_nome(pessoas, "PAI_NUBENTE2",
                    "filiação 2 do segundo nubente — preencha ou declare ignorado",
                    faltas)
        _falta_nome(pessoas, "TESTEMUNHA", "testemunha", faltas)
        if not _texto_preenchido(assento.get("regime_bens"),
                                 aceita_ignorado=False):
            faltas.append("regime de bens")
    else:
        artigo = "arts. 80 e 83 da Lei nº 6.015/1973"
        if not titular_ok("FALECIDO"):
            faltas.append("nome de quem é o registro")
        if not _texto_preenchido(data_fato, aceita_ignorado=False):
            faltas.append("data do falecimento")
        if not _texto_preenchido(local):
            faltas.append("lugar do falecimento")
        _falta_nome(pessoas, "DECLARANTE", "declarante", faltas)
        _falta_nome(pessoas, "MAE",
                    "filiação 1 (mãe) — preencha ou declare ignorado",
                    faltas)
        _falta_nome(pessoas, "PAI",
                    "filiação 2 (pai) — preencha ou declare ignorado",
                    faltas)
        if not _texto_preenchido(assento.get("numero_do"),
                                 aceita_ignorado=False):
            faltas.append("Declaração de Óbito (número da DO)")

    if not faltas:
        return
    lista = "; ".join(faltas)
    raise RcError(
        f"Não se lavra o assento em branco. {artigo} exige, e falta: {lista}. "
        f"O que não existir se declara ignorado no formulário — vazio não é "
        f"declaração.")


def numero_sem_dono(con: Any, serie: str) -> None:
    """Recusa lavrar numa série cujo próximo número ninguém informou. SÓ LÊ.

    13/10/2026, o oficial, sobre o Livro E: «deixe em aberto o próximo
    registro, mas preparemos o ambiente para viabilizar o próximo registro».
    Sem linha em `nu_numeracao`, `escrituracao.proximo_numero` começa do **1**
    — o defeito de 18/08 que a pendência de numeração existe para impedir.
    Com a pendência aberta e sem contador, a lavratura para aqui e diz onde
    informar; informado o número (`implantacao.resolver_numero`), passa.

    **SÉRIE COM CONTADOR NÃO É ALCANÇADA**, mesmo com a pendência aberta: o
    Livro A e o Livro B lavram todo dia com o contador semeado do acervo.
    """
    bd = banco(con)
    if not (bd.tem_tabela("nu_numeracao") and bd.tem_tabela("nu_implantacao")):
        return                       # instalação sem as tabelas do núcleo
    tem_contador = bd.um(
        "SELECT 1 AS um FROM nu_numeracao WHERE serie = %s LIMIT 1", (serie,))
    pendente = bd.um(
        "SELECT titulo FROM nu_implantacao WHERE chave = %s AND situacao='ABERTA'"
        " LIMIT 1",
        (f"numeracao:{serie}",))
    if pendente and not tem_contador:
        raise RcError(
            f"{pendente['titulo']}: ainda não foi informado, e sem ele o primeiro ato "
            f"nasceria com o número 1. Informe-o em Livros e acervo → O que "
            f"falta informar (confira no livro de papel) e lavre em seguida.")


def lavrar_assento(con: Any, *, especie: str, nome: str,
                   sv: dict, agora: str, data_extenso: str,
                   data_fato: str | None = None,
                   matricula: str | None = None,
                   dados: dict | None = None,
                   teor: str | None = None,
                   teor_formato: str = "texto",
                   usuario: str | None = None, origem: str = "MANUAL",
                   origem_chave: str | None = None,
                   importacao_id: int | None = None,
                   ibge: dict | None = None,
                   habilitacao_serventia: str | None = None,
                   habilitacao_selo: str | None = None,
                   regime_bens: str | None = None,
                   termo_dados: dict | None = None,
                   pessoas: list[dict] | None = None,
                   forcar_motivo: str | None = None,
                   marcas_do_obito: dict | None = None,
                   paternidade: dict | None = None) -> dict:
    """Lavra o assento e o ato de REGISTRO. ESCREVE.

    `paternidade` é o termo que o nascimento sem o pai exige — de alegação ou
    negativo (`rc_paternidade`, 23/10/2026). Ele é conferido ANTES de qualquer
    gravação e lavrado depois do lugar no livro, porque o texto cita o livro,
    a folha e o número.

    `marcas_do_obito` são as respostas do balcão às perguntas do óbito (era
    eleitor, deixou bens...). Entram AQUI, antes da conferência das centrais,
    porque a CRC recusa o óbito sem «deixou bens» — gravadas depois, a
    conferência as acharia sempre vazias (relato #130, 14/10/2026).

    `forcar_motivo` é a saída de emergência: com ele, o que a conferência dos
    dados travaria entra mesmo assim, e a trava fica gravada em
    `rc_lavraturas_forcadas` com o motivo e o nome de quem forçou. Quem pode
    forçar é decisão da rota (`rc_conferencia_dados.PAPEIS_QUE_FORCAM`).

    A série vem da espécie (`SERIE_DA_ESPECIE`), nunca de parâmetro: deixar
    o balcão escolher o livro é deixar lançar óbito no livro de nascimentos.

    Carga repetível por construção: a mesma (origem, origem_chave) devolve o
    id que já existe.
    """
    if especie not in SERIE_DA_ESPECIE:
        raise RcError(
            f"Espécie de assento desconhecida: {especie!r}. As que existem "
            f"são: {', '.join(ESPECIES)}.")
    # A LAVRATURA DO BALCAO (origem MANUAL) recusa o que a lei exige e veio
    # em branco. Carga / E-Oficio / SISTEMA trazem o papel que ja existe.
    if (origem or "MANUAL").strip().upper() == "MANUAL":
        conferir_requisitos_legais(
            especie,
            {"nome": nome, "data_fato": data_fato,
             "sexo": (dados or {}).get("sexo") if isinstance(dados, dict) else None,
             "dados": dados or {},
             "local_fato_nome": (termo_dados or {}).get("local_fato_nome"),
             "local_fato_endereco": (termo_dados or {}).get("local_fato_endereco"),
             "regime_bens": regime_bens,
             "numero_do": (ibge or {}).get("numero_do"),
             # O LIVRO E confere o título com os campos dele (13/10/2026).
             **{k: v for k, v in (termo_dados or {}).items()
                if k.startswith("livro_e_")
                or k in ("registro_tardio", "tardio_requerimento")},
             "dnv": (ibge or {}).get("dnv")},
            pessoas)
    if not (nome or "").strip():
        raise RcError("O assento precisa do nome de quem é o registro.")
    # O NASCIMENTO SEM O PAI EXIGE O TERMO (23/10/2026), de alegação ou
    # negativo — Lei nº 8.560/1992, art. 2º. Confere aqui, antes de gravar.
    import rc_paternidade as RP
    try:
        pedido_paternidade = RP.conferir(especie, pessoas, origem, paternidade)
    except RP.PaternidadeError as erro:
        raise RcError(str(erro)) from None
    serie = SERIE_DA_ESPECIE[especie]
    bd = banco(con)
    if (origem or "MANUAL").strip().upper() == "MANUAL":
        numero_sem_dono(bd, serie)
    chave = (origem_chave or "").strip() or None
    if origem == "EOFICIO" and not chave:
        raise RcError(
            "Assento de origem EOFICIO precisa de uma chave de origem, para "
            "a carga poder ser repetida sem duplicar.")
    if chave:
        existente = assento_por_origem(bd, origem, chave)
        if existente:
            return {"assento_id": int(existente["id"]), "reaproveitado": True}

    assento_id = int(bd.escrever(
        """INSERT INTO rc_assentos(serie, especie, matricula, nome, data_ato,
               data_fato, dados_json, teor, teor_formato, situacao, origem,
               origem_chave, importacao_id, criado_em, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (serie, especie, (matricula or "").strip() or None, nome.strip(),
         agora, data_fato, json.dumps(dados or {}, ensure_ascii=False), teor,
         teor_formato, "ATIVO", origem, chave, importacao_id, agora,
         usuario))[0]["id"])

    # O QUE A REMESSA DO IBGE PEDE, quando o balcão já sabe.
    #
    #   Entra AQUI e não num passo seguinte porque o declarante está na frente
    #   do escrevente neste momento, com a DNV na mão. Perguntar depois é
    #   telefonar para a família.
    #
    #   E entra OPCIONAL, porque nem sempre se sabe: assento tardio, óbito de
    #   pessoa achada. `anotar_para_o_ibge` completa depois, e a remessa
    #   mostra o que falta em vez de mandar campo inventado.
    # A PESSOA DE QUEM O ASSENTO E, com o que a certidao e o IBGE pedem.
    #
    #   Ate 28/08/2026 o assento guardava so o NOME dela. A certidao de
    #   casamento e a de obito descrevem essa pessoa, e a remessa do IBGE pede
    #   sexo, data de nascimento, naturalidade, residencia e estado civil —
    #   nada disso existia.
    if pessoas:
        for pessoa in pessoas:
            registrar_pessoa(bd, assento_id, especie=especie, agora=agora,
                             **pessoa)

    if ibge:
        anotar_para_o_ibge(bd, assento_id, especie=especie, **ibge)

    # O QUE O TERMO PEDE — cor ou raça, hora, hospital, naturalidade.
    #
    #   Entra aqui pelo mesmo motivo do bloco do IBGE: o declarante está na
    #   frente do escrevente AGORA. E entrou tarde — as colunas nasceram em
    #   29/08/2026 e ficaram um dia inteiro sem nada que as preenchesse, o que
    #   as fazia mentir: a remessa acusava «falta o dado» e não havia onde
    #   informá-lo.
    if termo_dados:
        anotar_do_termo(con, assento_id, especie=especie,
                        **{k: v for k, v in termo_dados.items()
                           if v not in (None, "")})

    # A HABILITAÇÃO DE OUTRA SERVENTIA — item 14.1.6 da tabela.
    #
    #   Isto não é cadastro: é o que decide se este assento COMPRA selo ou
    #   REAPROVEITA o da habilitação. Preenchido quer dizer «veio de fora, e
    #   aqui não há selo a reaproveitar»; vazio quer dizer «é daqui».
    #
    #   Só faz sentido no casamento, e por isso as outras espécies recusam: um
    #   óbito com «habilitação de outra serventia» é dado que confunde quem ler
    #   depois — e, pior, poderia fazer o sistema comprar selo onde não deve.
    # O REGIME DE BENS — campo obrigatório da certidão de casamento (Lei
    # 6.015/1973, art. 70, item 6). Só o casamento o tem: pôr regime de bens
    # num óbito é dado que confunde quem ler depois.
    # A UNIÃO ESTÁVEL TAMBÉM TEM (art. 94-A, VII) — 13/10/2026.
    regime = (regime_bens or "").strip()
    if regime:
        if especie not in ESPECIES_DE_CASAMENTO | {"UNIAO_ESTAVEL"}:
            raise RcError(
                f"Só o casamento e a união estável têm regime de bens — e este assento é de "
                f"{NOME_DA_ESPECIE.get(especie, especie).lower()}.")
        bd.escrever("UPDATE rc_assentos SET regime_bens = %s WHERE id = %s",
                    (regime, assento_id))

    de_fora = (habilitacao_serventia or "").strip()
    selo_de_fora = (habilitacao_selo or "").strip()
    if de_fora or selo_de_fora:
        if especie not in ESPECIES_DE_CASAMENTO:
            raise RcError(
                f"Só o casamento se lavra à vista de habilitação — e este "
                f"assento é de {NOME_DA_ESPECIE.get(especie, especie).lower()}.")
        if selo_de_fora and not de_fora:
            raise RcError(
                "Diga de que serventia é a habilitação. O selo de fora sozinho "
                "não diz de onde veio, e é isso que vai no papel e no selo.")
        bd.escrever(
            "UPDATE rc_assentos SET habilitacao_serventia = %s, "
            "habilitacao_selo = %s WHERE id = %s",
            (de_fora, selo_de_fora or None, assento_id))

    ato_id = int(bd.escrever(
        """INSERT INTO rc_atos(assento_id, tipo, data_ato, teor, teor_formato,
               origem, criado_em, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (assento_id, "REGISTRO", agora, teor, teor_formato, origem, agora,
         usuario))[0]["id"])

    lugar = ESC.reservar(con, serie, "rc_atos", ato_id, sv=sv, agora=agora,
                         data_extenso=data_extenso, paginas=1, usuario=usuario)
    bd.escrever(
        """UPDATE rc_atos SET livro_id = %s, folha = %s, verso = %s,
                              numero_ordem = %s, rotulo = %s WHERE id = %s""",
        (lugar["livro_id"], lugar["folha"], int(lugar["verso"]),
         lugar["numero_ordem"], lugar["rotulo"], ato_id))
    bd.escrever("UPDATE rc_assentos SET numero = %s WHERE id = %s",
                (lugar["numero_ordem"], assento_id))

    # A MATRICULA DE 32 DIGITOS — COMPOSTA AQUI, E NAO ANTES.
    #
    #   ELA SO PODE SER FEITA DEPOIS DESTA LINHA, e isso nao e detalhe de
    #   implementacao: a matricula CONTEM o livro, a folha e o numero de ordem,
    #   que sao justamente o que `ESC.reservar` acabou de atribuir. Antes daqui
    #   nao ha o que compor. E por isso que na tela do E-Oficio o Termo, o Livro
    #   e a Folha ficam em 00000 ate se clicar em «Registrar».
    #
    #   ATE 30/08/2026 ESTE SISTEMA NAO A GERAVA, e o motivo estava escrito na
    #   rota: «o algoritmo oficial nao foi medido, e numero de matricula
    #   inventado e pior que campo em branco». O motivo era bom e deixou de
    #   valer: a regra esta no **Anexo IV do manual de carga da CRC**, conferida
    #   contra 255 casos reais.
    #
    #   A DIGITADA MANDA. Se o escrevente informou uma matricula — assento
    #   antigo sendo cadastrado, registro transportado —, ela fica como veio.
    #   Sobrescreve-la seria trocar o numero nacional de um assento que ja
    #   existe, e o art. 372 do provimento faz dela unica e imutavel.
    #
    #   E FALHAR AQUI NAO DERRUBA A LAVRATURA. O assento e o essencial; a
    #   matricula se completa depois. Mas **a falha nao fica calada**: volta no
    #   retorno com o motivo, para a tela dizer.
    matricula_composta = (matricula or "").strip()
    matricula_porque_nao = ""
    if not matricula_composta:
        import rc_matricula as MATR
        try:
            matricula_composta = MATR.compor(
                cns=(sv or {}).get("ri_cns"),
                ano=str(agora)[:4],
                livro_tipo=MATR.LIVRO_DA_ESPECIE[especie.strip().upper()],
                livro=lugar.get("livro_numero"),
                folha=lugar.get("folha"),
                termo=lugar.get("numero_ordem"))
            bd.escrever("UPDATE rc_assentos SET matricula = %s WHERE id = %s",
                        (matricula_composta, assento_id))
        except (MATR.MatriculaError, KeyError) as erro:
            matricula_composta = ""
            matricula_porque_nao = (
                f"O assento foi lavrado, mas a matrícula de 32 dígitos não "
                f"pôde ser composta: {erro}")

    # AS ANOTACOES QUE ESTE ATO OBRIGA — art. 372 do Codigo de Normas do TJMA.
    #
    #   Casamento e obito obrigam a anotar nos assentos ANTERIORES da pessoa: o
    #   casamento no nascimento e nos casamentos anteriores; o obito no
    #   nascimento e no casamento. As tres do Livro E — interdicao, emancipacao
    #   e ausencia — tambem, pelo art. 328, § 2o.
    #
    #   DECLARA-SE AQUI, E NAO DEPOIS. O prazo do art. 367 e de **cinco dias
    #   contados do ato**; abrir a pendencia mais tarde faria o relogio comecar
    #   atrasado, que e o mesmo que nao ter relogio.
    #
    #   E o terceiro prazo desta casa que ninguem de fora cobra — depois do
    #   SIGEF (30 dias) e da relacao da Junta Militar (mensal). Este e o mais
    #   curto e o mais frequente.
    import rc_anotacao as ANOT
    ANOT.declarar(con, assento_id, agora=agora, usuario=usuario)

    # O TERMO DE PATERNIDADE NASCE COM O ASSENTO, na mesma transação: ato sem
    # termo não existe, e termo sem ato também não.
    if pedido_paternidade:
        mae = RP.nome_do_papel(pessoas, "MAE")
        RP.lavrar_termo(
            con, assento_id, pedido_paternidade,
            teor=RP.montar_teor(
                pedido_paternidade, registrado=nome.strip(), mae=mae,
                data_nascimento=data_fato or "", livro=lugar.get("livro_numero"),
                folha=lugar.get("rotulo") or lugar.get("folha"),
                numero=lugar.get("numero_ordem"), data_extenso=data_extenso,
                sv=sv or {}),
            registrado=nome.strip(), mae=mae, agora=agora, usuario=usuario)

    # A CONFERÊNCIA DOS DADOS — termo × campos × pessoas (11/10/2026).
    #
    #   Roda AQUI, no fim e ainda dentro da transação de quem chama, porque é
    #   aqui que existe o que vai ao livro: as pessoas já gravadas (a
    #   testemunha fantasma nascia em `registrar_pessoa`), o número e a
    #   matrícula já compostos. O que trava desfaz tudo — o lugar no livro, o
    #   número, as pessoas — e nada fica pela metade. O que só avisa volta no
    #   retorno, para a tela dizer.
    #
    #   VALE PARA QUEM CHAMAR ESTA FUNÇÃO, e é de propósito: o robô que monta
    #   assento a partir das digitalizações lavra por script, chamando-a
    #   direto, e a trava na tela não o alcançaria.
    if marcas_do_obito and especie == "OBITO":
        import rc_marcas_do_obito as MARCA
        MARCA.responder(con, assento_id, marcas_do_obito)

    avisos_da_conferencia: list[dict] = []
    lavratura_forcada = False
    if (origem or "MANUAL").strip().upper() == "MANUAL":
        import rc_conferencia_dados as CONF
        import rc_centrais_na_lavratura as CENT
        problemas = CONF.conferir_assento(con, assento_id)
        # O QUE A CRC E O SIRC EXIGEM (relato #130, 14/10/2026) — as MESMAS
        # réguas da carga (`crc_carga.o_que_falta`, `sirc_remessa.o_que_falta`),
        # rodadas aqui, antes do commit: o que faltar recusa e a transação
        # desfaz número, folha e pessoas. Antes, a falta só aparecia na carga,
        # com o assento já no livro.
        faltas_centrais = CENT.o_que_falta(con, assento_id, para_lavratura=True)
        travas_centrais = CENT.problemas(faltas_centrais)
        problemas = problemas + travas_centrais

        def _recusa(extra: str = "") -> ConferenciaError:
            contradicoes = [p for p in CONF.bloqueios(problemas)
                            if p not in travas_centrais]
            partes = []
            if contradicoes:
                partes.append(CONF.mensagem_de_recusa(
                    [p for p in problemas if p not in travas_centrais]))
            if faltas_centrais:
                partes.append(CENT.mensagem_de_recusa(faltas_centrais))
            if extra:
                partes.append(extra)
            classe = (CENT.FaltaParaAsCentraisError if faltas_centrais
                      else ConferenciaError)
            return classe(" ".join(partes), problemas)

        travas = CONF.bloqueios(problemas)
        if travas:
            # A SAÍDA DE EMERGÊNCIA (11/10/2026): só com motivo que basta e com
            # o nome de quem força. Sem os dois, é a recusa de sempre. Ela vale
            # também para a falta das centrais — o óbito tem de ser lavrado
            # para o sepultamento mesmo quando o declarante não sabe responder
            # o que a CRC exige —, e as travas forçadas ficam gravadas.
            if forcar_motivo is None:
                raise _recusa()
            falta = CONF.motivo_insuficiente(forcar_motivo)
            if not falta and not (usuario or "").strip():
                falta = "Lavrar por cima da trava exige o nome de quem força."
            if falta:
                raise _recusa(falta)
            bd.escrever(
                """INSERT INTO rc_lavraturas_forcadas
                       (assento_id, forcado_em, forcado_por, motivo, travas_json)
                   VALUES (%s, %s, %s, %s, %s)""",
                (assento_id, agora, usuario.strip(), forcar_motivo.strip(),
                 json.dumps(travas, ensure_ascii=False)))
            lavratura_forcada = True
        avisos_da_conferencia = travas + CONF.avisos(problemas)

    return {"assento_id": assento_id, "ato_id": ato_id, "serie": serie,
           "reaproveitado": False, "matricula": matricula_composta,
           "matricula_porque_nao": matricula_porque_nao,
           "avisos_da_conferencia": avisos_da_conferencia,
           "lavratura_forcada": lavratura_forcada, **lugar}


#: A trava do termo lavrado (`corrigir_informacoes`). Configuração ganha do
#: código: se o balcão precisar, o oficial a desliga numa tarde.
CHAVE_TERMO_TRANCADO = "rcpn_termo_lavrado_trancado"


def termo_lavrado_trancado(con: Any, assento_id: int) -> bool:
    """O assento foi lavrado nesta casa (origem MANUAL) e o registro tem selo?
    Então o termo, o número, a folha e a data são o livro. SÓ LÊ."""
    bd = banco(con)
    r = bd.um("SELECT value FROM settings WHERE key = %s",
              (CHAVE_TERMO_TRANCADO,)) if bd.tem_tabela("settings") else None
    if r and str(r["value"] or "").strip().upper() == "DESLIGADO":
        return False
    a = bd.um("SELECT origem FROM rc_assentos WHERE id = %s",
              (int(assento_id),))
    if not a or str(a["origem"] or "").upper() != "MANUAL":
        return False
    return bd.um(
        "SELECT 1 AS um FROM rc_atos WHERE assento_id = %s AND tipo='REGISTRO' "
        "AND COALESCE(TRIM(selo),'') <> '' LIMIT 1",
        (int(assento_id),)) is not None


# ------------------------------------------------- a divisao tripartite


def _lancar_no_assento(con: Any, assento_id: int, tipo: str, *,
                       teor: str, agora: str, fundamento: str | None,
                       teor_formato: str, usuario: str | None,
                       origem: str) -> dict:
    """A mecânica comum dos três blocos. ESCREVE. Não ocupa folha nova.

    Averbação, anotação e retificação se lançam no espaço do PRÓPRIO
    assento, inclusive no verso da folha dele — é assim no livro físico, e é
    isso que a divisão tripartite significa. Chamar `reservar()` aqui daria
    folha nova a cada averbação e faria o Livro A encher em um ano.
    """
    # A SITUAÇÃO SE CONFERE COM A LINHA PRESA (FOR UPDATE), e não por
    # `assento`, que só lê: sem a ponte, um cancelamento ao mesmo tempo
    # passaria pela conferência e o lançamento entraria em assento cancelado.
    bd = banco(con)
    bd._escrita()
    ass = bd.um("SELECT * FROM rc_assentos WHERE id = %s FOR UPDATE",
                (int(assento_id),))
    if not ass:
        raise RcError(f"Assento {assento_id} não encontrado.")
    if ass["situacao"] != "ATIVO":
        raise RcError(
            f"O assento está com situação {ass['situacao']} — não recebe "
            f"mais lançamento.")
    razao = (teor or "").strip()
    if len(razao) < 10:
        raise RcError(
            f"O teor da {tipo.lower()} precisa de pelo menos dez letras — ele "
            f"sai impresso na certidão.")
    # QUEM LAVROU SAI NO TEOR: a inspecao exige ver o escrevente na averbacao
    # (e na etiqueta da margem). O selo entra depois, em
    # rc_etiqueta_averbacao.sincronizar_teor_do_ato, quando existir.
    import rc_etiqueta_averbacao as ETIQ
    razao = ETIQ.teor_com_lavratura(razao, usuario)

    ato_id = int(bd.escrever(
        """INSERT INTO rc_atos(assento_id, tipo, data_ato, teor, teor_formato,
               fundamento, origem, criado_em, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (assento_id, tipo, agora, razao, teor_formato,
         (fundamento or "").strip() or None, origem, agora, usuario))[0]["id"])
    return {"assento_id": assento_id, "ato_id": ato_id,
           "tipo": tipo, "teor": razao}


def averbar(con: Any, assento_id: int, *, teor: str,
            agora: str, fundamento: str | None = None,
            teor_formato: str = "texto", usuario: str | None = None,
            origem: str = "MANUAL") -> dict:
    """Averba — altera o conteúdo do assento. Lei 6.015/1973, art. 97."""
    return _lancar_no_assento(con, assento_id, "AVERBACAO", teor=teor,
                              agora=agora, fundamento=fundamento,
                              teor_formato=teor_formato, usuario=usuario,
                              origem=origem)


def anotar(con: Any, assento_id: int, *, teor: str,
           agora: str, fundamento: str | None = None,
           teor_formato: str = "texto", usuario: str | None = None,
           origem: str = "MANUAL") -> dict:
    """Anota — remete a outro assento. Lei 6.015/1973, art. 106."""
    return _lancar_no_assento(con, assento_id, "ANOTACAO", teor=teor,
                              agora=agora, fundamento=fundamento,
                              teor_formato=teor_formato, usuario=usuario,
                              origem=origem)


def retificar(con: Any, assento_id: int, *, teor: str,
              fundamento: str, agora: str, teor_formato: str = "texto",
              usuario: str | None = None, origem: str = "MANUAL") -> dict:
    """Retifica — corrige erro. Lei 6.015/1973, art. 109.

    `fundamento` é obrigatório aqui, e não nos outros dois: retificação sem
    dizer com base em quê é o que faz o livro não explicar por que mudou.
    """
    if not (fundamento or "").strip():
        raise RcError(
            "A retificação exige o fundamento — a ordem, o pedido ou a lei "
            "que autoriza corrigir o assento.")
    return _lancar_no_assento(con, assento_id, "RETIFICACAO", teor=teor,
                              agora=agora, fundamento=fundamento,
                              teor_formato=teor_formato, usuario=usuario,
                              origem=origem)


# ---------------------------------------------------- corrigir a ficha
#
# A FICHA ERA SO LEITURA. Assentos do acervo (origem EOFICIO) chegam com
# nome, filiacao, datas, livro/folha/termo e teor que as vezes precisam
# de correção pontual no balcão — typo na carga, campo vazio, livro
# confuso. Isto NAO e a retificação do art. 109 (que lança ato com
# fundamento): e a correção direta dos CAMPOS da ficha, com motivo e
# auditoria de quem alterou. criado_por do assento NAO muda.

def corrigir_informacoes(con: Any, assento_id: int, *,
                         motivo: str, agora: str,
                         usuario: str | None = None,
                         nome: Any = None,
                         data_ato: Any = None,
                         data_fato: Any = None,
                         matricula: Any = None,
                         teor: Any = None,
                         livro_volume: Any = None,
                         numero: Any = None,
                         folha: Any = None,
                         sexo: Any = None,
                         termo: dict | None = None,
                         pessoas: list[dict] | None = None,
                         regime_bens: Any = None) -> dict:
    """Corrige campos da ficha do assento. ESCREVE.

    Serve sobretudo aos assentos do acervo (EOFICIO), cujos campos vieram
    travados na ficha. Nao inventa dado: so grava o que o escrevente
    informou. `motivo` e obrigatorio (auditoria). `criado_por` NAO muda —
    quem corrigiu fica no audit e em `usuario` da mudanca.

    Campo None = nao mexer. String vazia em texto opcional = limpar.
    `nome` nao pode ficar em branco.
    """
    motivo_limpo = (motivo or "").strip()
    if len(motivo_limpo) < 10:
        raise RcError(
            "Escreva o motivo da correção com pelo menos dez letras — "
            "quem abrir o assento depois precisa entender por que mudou.")

    # Linha presa (FOR UPDATE): a situação e o que se compara com a ficha
    # valem até o fim da transação, e não só até a leitura.
    bd = banco(con)
    bd._escrita()
    linha = bd.um("SELECT * FROM rc_assentos WHERE id = %s FOR UPDATE",
                  (int(assento_id),))
    if not linha:
        raise RcError(f"O assento {assento_id} não existe.")
    if (linha["situacao"] or "").strip().upper() != "ATIVO":
        raise RcError(
            "Só é possível corrigir informações em assento ativo.")

    mudancas: dict[str, dict[str, Any]] = {}
    sets: dict[str, Any] = {}

    def _txt(v: Any) -> str | None:
        if v is None:
            return None
        t = str(v).strip()
        return t if t else None

    if nome is not None:
        novo = (str(nome) or "").strip()
        if not novo:
            raise RcError("O nome do assento não pode ficar em branco.")
        if novo != (linha["nome"] or ""):
            sets["nome"] = novo
            mudancas["nome"] = {"de": linha["nome"], "para": novo}

    for col, valor in (("data_ato", data_ato), ("data_fato", data_fato),
                       ("matricula", matricula), ("livro_volume", livro_volume)):
        if valor is None:
            continue
        novo = _txt(valor)
        antigo = linha[col]
        # A TELA MOSTRA SÓ O DIA, e o banco guarda dia e hora — 13/10/2026.
        # Sem isto, salvar a ficha sem tocar na data contava como «mudar a
        # data do registro», e a trava do termo selado recusava TODA
        # correção de assento lavrado nesta casa.
        if (col in ("data_ato", "data_fato") and novo and antigo
                and len(novo) == 10 and str(antigo)[:10] == novo):
            continue
        if (novo or None) != (antigo or None):
            sets[col] = novo
            mudancas[col] = {"de": antigo, "para": novo}

    if numero is not None:
        bruto = str(numero).strip() if numero not in (None, "") else ""
        if bruto == "":
            novo_num = None
        else:
            try:
                novo_num = int(bruto)
            except (TypeError, ValueError) as exc:
                raise RcError(
                    f"O número do termo tem de ser um inteiro — veio "
                    f"«{numero}».") from exc
        antigo_num = linha["numero"]
        if novo_num != antigo_num:
            sets["numero"] = novo_num
            mudancas["numero"] = {"de": antigo_num, "para": novo_num}

    if teor is not None:
        novo_teor = str(teor).strip()
        antigo_teor = (linha["teor"] or "")
        if novo_teor != antigo_teor.strip():
            sets["teor"] = novo_teor or None
            mudancas["teor"] = {
                "de": ((antigo_teor[:80] + "…") if len(antigo_teor) > 80
                       else antigo_teor) or None,
                "para": ((novo_teor[:80] + "…") if len(novo_teor) > 80
                         else novo_teor) or None,
            }

    if sexo is not None:
        letra = _sexo_da_pessoa(sexo) if str(sexo).strip() else None
        dados = json.loads(linha["dados_json"] or "{}")
        if not isinstance(dados, dict):
            dados = {}
        antigo = dados.get("sexo")
        if letra != antigo:
            if letra:
                dados["sexo"] = letra
            elif "sexo" in dados:
                del dados["sexo"]
            sets["dados_json"] = json.dumps(dados, ensure_ascii=False)
            mudancas["sexo"] = {"de": antigo, "para": letra}

    # O REGIME DE BENS — casamento (art. 70, 7º) e união estável (art. 94-A,
    # VII). 13/10/2026: a tela de corrigir passou a mostrá-lo.
    if regime_bens is not None:
        novo_reg = _txt(regime_bens)
        esp = (linha["especie"] or "").strip().upper()
        if novo_reg and esp not in ESPECIES_DE_CASAMENTO | {"UNIAO_ESTAVEL"}:
            raise RcError("Só o casamento e a união estável têm regime de bens.")
        if (novo_reg or None) != (linha["regime_bens"] or None):
            sets["regime_bens"] = novo_reg
            mudancas["regime_bens"] = {"de": linha["regime_bens"], "para": novo_reg}

    # O TERMO LAVRADO E SELADO NESTA CASA NÃO SE CORRIGE POR FICHA — pedido do
    # oficial em 11/10/2026 («mecanismos que orientem e bloqueiem introduções
    # deficitárias ou erradas»). Medido no mesmo dia: termos assinados
    # reescritos depois do selo, por esta função e por script. O termo é o
    # papel que o declarante assinou; corrigir é averbar ou retificar ao lado
    # (a regra que `rc_termo.congelar` já escrevia). O acervo continua
    # corrigível — ali a ficha é transcrição, e o livro é o de papel.
    trancados = [c for c in ("teor", "numero", "data_ato") if c in mudancas]
    if folha is not None:
        ato_reg = bd.um(
            "SELECT folha FROM rc_atos WHERE assento_id = %s AND tipo='REGISTRO' "
            "ORDER BY id DESC LIMIT 1", (int(assento_id),))
        if ato_reg and str(ato_reg["folha"] or "") != str(folha).strip():
            trancados.append("folha")
    if trancados and termo_lavrado_trancado(bd, int(assento_id)):
        nomes = {"teor": "o termo", "numero": "o número do termo",
                 "data_ato": "a data do registro", "folha": "a folha"}
        raise RcError(
            "Este assento foi lavrado e selado nesta casa: "
            + ", ".join(nomes[c] for c in trancados)
            + " é o que está no livro e não se corrige pela ficha. Para "
            "corrigir, lavre a retificação ou a averbação na ficha do assento "
            "(Lei 6.015/1973, arts. 97 e 110). Os dados das pessoas e os "
            "campos que não estão no termo continuam corrigíveis aqui.")

    if sets:
        bd.escrever(
            "UPDATE rc_assentos SET "
            + ", ".join(f"{c} = %s" for c in sets)
            + " WHERE id = %s",
            (*sets.values(), int(assento_id)))

    if termo:
        permitidos_termo = CAMPOS_DO_TERMO_POR_ESPECIE.get(
            (linha["especie"] or "").strip().upper(), ())
        kwargs = {k: v for k, v in termo.items()
                  if v is not None and k in permitidos_termo}
        if kwargs:
            limpar = [k for k, v in kwargs.items()
                      if str(v).strip() == ""]
            preencher = {k: v for k, v in kwargs.items() if k not in limpar}
            if preencher:
                r = anotar_do_termo(con, assento_id,
                                    especie=linha["especie"], **preencher)
                for c in r.get("gravados") or []:
                    mudancas[c] = {
                        "de": linha[c] if c in linha.keys() else None,
                        "para": preencher.get(c),
                    }
            if limpar:
                bd.escrever(
                    "UPDATE rc_assentos SET "
                    + ", ".join(f"{c}=NULL" for c in limpar)
                    + " WHERE id = %s",
                    (int(assento_id),))
                for c in limpar:
                    antigo = linha[c] if c in linha.keys() else None
                    if antigo not in (None, ""):
                        mudancas[c] = {"de": antigo, "para": None}

    def _parse_folha(valor: Any) -> tuple[Any, Any]:
        """Devolve (folha_int|None, rotulo|None)."""
        bruto_f = str(valor).strip() if valor not in (None, "") else ""
        if bruto_f == "":
            return None, None
        try:
            nova_folha = int(bruto_f)
            return nova_folha, str(nova_folha)
        except (TypeError, ValueError):
            digitos = "".join(ch for ch in bruto_f if ch.isdigit())
            if not digitos:
                raise RcError(
                    f"A folha tem de ser um número — veio «{folha}».")
            return int(digitos), bruto_f.upper()

    if folha is not None or ("numero" in mudancas):
        ato = bd.um(
            "SELECT id, folha, numero_ordem, rotulo FROM rc_atos "
            "WHERE assento_id = %s AND tipo='REGISTRO' ORDER BY id LIMIT 1",
            (int(assento_id),))
        if ato:
            ato_sets: dict[str, Any] = {}
            if folha is not None:
                nova_folha, rotulo = _parse_folha(folha)
                if nova_folha != ato["folha"]:
                    ato_sets["folha"] = nova_folha
                    ato_sets["rotulo"] = rotulo
                    mudancas["folha"] = {"de": ato["folha"], "para": nova_folha}
            if "numero" in mudancas:
                novo_n = mudancas["numero"]["para"]
                if novo_n != ato["numero_ordem"]:
                    ato_sets["numero_ordem"] = novo_n
            if ato_sets:
                bd.escrever(
                    "UPDATE rc_atos SET "
                    + ", ".join(f"{c} = %s" for c in ato_sets)
                    + " WHERE id = %s",
                    (*ato_sets.values(), int(ato["id"])))
        elif folha is not None:
            # Acervo sem ato REGISTRO: a folha não tem linha em rc_atos.
            # Registra a mudança para sincronizar dados_json abaixo.
            try:
                dj0 = json.loads(linha["dados_json"] or "{}")
            except (TypeError, ValueError):
                dj0 = {}
            if not isinstance(dj0, dict):
                dj0 = {}
            antiga = dj0.get("folha")
            try:
                antiga_n = int(antiga) if antiga not in (None, "") else None
            except (TypeError, ValueError):
                dig = "".join(ch for ch in str(antiga) if ch.isdigit())
                antiga_n = int(dig) if dig else None
            nova_folha, _rot = _parse_folha(folha)
            if nova_folha != antiga_n:
                mudancas["folha"] = {"de": antiga_n, "para": nova_folha}

    # Certidões de acervo leem livro/folha/termo de dados_json quando não há
    # ato REGISTRO — manter alinhado ao que o escrevente acabou de corrigir.
    if any(k in mudancas for k in ("livro_volume", "numero", "folha")):
        if "dados_json" in sets:
            try:
                dados_sync = json.loads(sets["dados_json"] or "{}")
            except (TypeError, ValueError):
                dados_sync = {}
        else:
            try:
                dados_sync = json.loads(linha["dados_json"] or "{}")
            except (TypeError, ValueError):
                dados_sync = {}
        if not isinstance(dados_sync, dict):
            dados_sync = {}
        if "livro_volume" in mudancas:
            dados_sync["livro"] = mudancas["livro_volume"]["para"]
        elif linha["livro_volume"] and not dados_sync.get("livro"):
            dados_sync["livro"] = linha["livro_volume"]
        if "folha" in mudancas:
            dados_sync["folha"] = mudancas["folha"]["para"]
        if "numero" in mudancas:
            dados_sync["termo"] = mudancas["numero"]["para"]
        novo_dj = json.dumps(dados_sync, ensure_ascii=False)
        bd.escrever(
            "UPDATE rc_assentos SET dados_json = %s WHERE id = %s",
            (novo_dj, int(assento_id)))
        sets["dados_json"] = novo_dj

    if pessoas:
        # A SEGUNDA PESSOA DO MESMO PAPEL É A SEGUNDA LINHA — termo 1214,
        # 23/10/2026. Eu procurava «a» testemunha com `LIMIT 1`, e as duas
        # gavetas gravavam na mesma linha: a segunda testemunha ficou por cima
        # da primeira, e o assento passou a ter a mesma pessoa duas vezes. A
        # n-ésima do formulário é a n-ésima gravada (ordem do `id`).
        vistas: dict[str, int] = {}
        for p in pessoas:
            papel = str(p.get("papel") or "").strip().upper()
            if not papel:
                continue
            campos = {c: p.get(c) for c in CAMPOS_DA_PESSOA if c in p}
            if not any(v not in (None, "") for v in campos.values()):
                continue
            n = vistas.get(papel, 0)
            vistas[papel] = n + 1
            chave = f"pessoa:{papel}" + (f"#{n + 1}" if n else "")
            existente = bd.um(
                "SELECT * FROM rc_pessoas WHERE assento_id = %s AND papel = %s "
                "ORDER BY id LIMIT 1 OFFSET %s",
                (int(assento_id), papel, n))
            if existente:
                upd: dict[str, Any] = {}
                for c, v in campos.items():
                    if v is None:
                        continue
                    novo = str(v).strip() or None
                    if c == "sexo":
                        novo = _sexo_da_pessoa(novo)
                    antigo = existente[c]
                    if (novo or None) != (antigo or None):
                        upd[c] = novo
                if "nome" in upd and upd["nome"]:
                    upd["nome_norm"] = normalizar_nome(upd["nome"])
                if upd:
                    bd.escrever(
                        "UPDATE rc_pessoas SET "
                        + ", ".join(f"{c} = %s" for c in upd)
                        + " WHERE id = %s",
                        (*upd.values(), int(existente["id"])))
                    mudancas[chave] = {
                        k: {"de": existente[k] if k in existente.keys()
                            else None, "para": v}
                        for k, v in upd.items() if k != "nome_norm"}
            else:
                if not (campos.get("nome") or "").strip():
                    continue
                registrar_pessoa(
                    bd, int(assento_id), papel=papel,
                    especie=linha["especie"], agora=agora,
                    usuario=usuario,
                    **{c: v for c, v in campos.items()
                       if v not in (None, "")})
                mudancas[chave] = {
                    "de": None, "para": campos.get("nome")}

    if "nome" in mudancas and not any(
            k.startswith("pessoa:") for k in mudancas):
        titular_papel = {
            "NASCIMENTO": "REGISTRADO", "NATIMORTO": "REGISTRADO",
            "OBITO": "FALECIDO",
        }.get((linha["especie"] or "").upper())
        if titular_papel:
            t = bd.um(
                "SELECT id, nome FROM rc_pessoas "
                "WHERE assento_id = %s AND papel = %s ORDER BY id LIMIT 1",
                (int(assento_id), titular_papel))
            if t and t["nome"] != mudancas["nome"]["para"]:
                bd.escrever(
                    "UPDATE rc_pessoas SET nome = %s, nome_norm = %s WHERE id = %s",
                    (mudancas["nome"]["para"],
                     normalizar_nome(mudancas["nome"]["para"]),
                     int(t["id"])))
                mudancas[f"pessoa:{titular_papel}"] = {
                    "nome": {"de": t["nome"],
                             "para": mudancas["nome"]["para"]}}

    if not mudancas:
        raise RcError(
            "Nada foi alterado — confira os campos e tente de novo.")

    if "teor" in mudancas and "teor" in sets:
        bd.escrever(
            "UPDATE rc_atos SET teor = %s "
            "WHERE assento_id = %s AND tipo='REGISTRO'",
            (sets.get("teor"), int(assento_id)))

    return {
        "assento_id": int(assento_id),
        "motivo": motivo_limpo,
        "usuario": usuario,
        "agora": agora,
        "origem": linha["origem"],
        "mudancas": mudancas,
        "campos": sorted(mudancas),
    }
