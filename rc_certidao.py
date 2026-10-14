"""
A CERTIDÃO DO REGISTRO CIVIL, no modelo nacional do CNJ.

POR QUE ELA ESPEROU — e por que agora
    O oficial decidiu em 25/08/2026: as certidões do Protesto e do RCPJ/RTD
    primeiro, e o RCPN **numa passada própria**. Esta é a passada.

    O motivo da separação está no dado: os **244 assentos do acervo não têm
    teor nenhum** — as três colunas de texto estão vazias nas três tabelas de
    origem. No RCPJ/RTD a certidão *reproduz* o livro; aqui ela se **monta dos
    campos**, e são coisas diferentes.

O MODELO É MEDIDO, e não inventado
    `tbCertidaoRCPN` guarda **145 certidões reais** desta casa, com o texto
    inteiro: 126 de nascimento, 18 de casamento e 3 de óbito. O desenho abaixo
    saiu delas — os rótulos, a ordem dos blocos, e o que vai em cada um.

    É a mesma disciplina das 65 do Protesto e das 44 do RCPJ/RTD: o papel que
    esta casa entrega é o que ela já entregava.

SEM FILIAÇÃO NÃO HÁ CERTIDÃO DE NASCIMENTO
    A filiação e a avoenga são o corpo da certidão de nascimento — não é um
    campo a mais. O módulo recusa emitir sem elas, dizendo que o assento
    **existe no livro** e que falta trazer a filiação.

    E foi esta certidão que descobriu que a carga não as trazia: `tbFiliacao`
    (os pais) e `tbProgenitor` (os avós) estavam no acervo e nunca tinham sido
    abertas. **Terceira vez que a certidão cobra da carga** — antes foram o
    devedor do Protesto e o ato de registro do RCPJ/RTD.

A MATRÍCULA SAI COMO ESTÁ
    Os 32 dígitos do CNJ vêm do assento e não se geram aqui. A estrutura está
    medida — CNS (6) + acervo (2) + serviço (2) + ano (4) + tipo de livro (1) +
    livro (5) + folha (3) + termo (7) + verificador (2) —, mas o **verificador
    não se explica**: testado contra 243 matrículas reais, nenhuma família
    padrão de módulo 11 ou 97 acerta. Gerar matrícula com dígito chutado seria
    pôr número errado no documento mais definitivo que esta casa emite.

O TEOR CONGELA, e a certidão tem número do exercício e hash
    É a forma da casa, a mesma do recibo do caixa e das outras duas certidões:
    assento averbado amanhã não muda a certidão de hoje.
"""
from __future__ import annotations
from certidao_texto import sem_linha_de_assinatura_a_mao

import hashlib
import json
import sqlite3
from typing import Any

import cancelamento_certidao as CANC
from livro_nucleo import por_extenso
from pt_schema import normalizar_nome
import rc_matricula as MAT

# OS MODELOS, um por espécie, medidos nas 145 certidões reais.
#
# `tbCertidaoRCPN.intTipoRegistro`: 1 = nascimento (126), 2 = casamento (18),
# 3 = óbito (3). O título de cada uma é o que está escrito nelas.
MODELOS: dict[str, dict] = {
    "NASCIMENTO": {"titulo": "CERTIDÃO DE NASCIMENTO", "acervo": 1},
    "CASAMENTO": {"titulo": "CERTIDÃO DE CASAMENTO DE:", "acervo": 2},
    "CASAMENTO_RELIGIOSO": {"titulo": "CERTIDÃO DE CASAMENTO DE:", "acervo": 2},
    "OBITO": {"titulo": "CERTIDÃO DE ÓBITO", "acervo": 3},
    "NATIMORTO": {"titulo": "CERTIDÃO DE NATIMORTO", "acervo": 3},
    "PROCLAMAS": {"titulo": "CERTIDÃO DE PROCLAMAS", "acervo": None},
    "OUTRO": {"titulo": "CERTIDÃO", "acervo": None},
}

# Os papéis das pessoas do assento, como a carga os grava.
PAPEIS_DA_FILIACAO = ("PAI", "MAE")
PAPEIS_DOS_AVOS = ("AVO_PATERNO", "AVO_PATERNA", "AVO_MATERNO", "AVO_MATERNA")

# O que a certidão escreve quando o campo não veio. É o que o acervo escreve:
# `ND` nas anotações de cadastro e `SEM INFORMAÇÃO` no CPF do casamento.
SEM_DADO = "ND"
SEM_INFORMACAO = "SEM INFORMAÇÃO"


class CertidaoRCPNError(ValueError):
    """Erro de regra da certidão, com a mensagem pronta para o balcão."""


# ------------------------------------------------------------- o esquema

SCHEMA = """
-- A CERTIDAO DO REGISTRO CIVIL. Tabela propria, e nao `rc_atos`: certidao nao
-- e ato do assento — ela nao ocupa folha, nao entra na divisao tripartite, e
-- pode sair muitas vezes do mesmo assento sem que o assento mude.
--
-- Numeracao por exercicio, teor congelado e hash: a mesma forma de
-- `pt_certidoes`, `at_certidoes` e `cx_recibos`. Quatro formas para o papel
-- que o cliente leva para casa seriam tres a mais.
CREATE TABLE IF NOT EXISTS rc_certidoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,
    ano INTEGER NOT NULL,

    assento_id INTEGER NOT NULL REFERENCES rc_assentos(id),
    especie TEXT NOT NULL,
    nome TEXT NOT NULL,                     -- de quem e o assento
    matricula TEXT,                         -- os 32 digitos, como estao

    requerente TEXT,
    finalidade TEXT,

    -- QUANTOS ATOS O ASSENTO TINHA quando a certidao saiu. Quem conferir
    -- depois sabe se ele andou — a mesma coluna da certidao do RCPJ/RTD.
    atos_no_assento INTEGER NOT NULL DEFAULT 0,

    teor TEXT NOT NULL,                     -- congelado
    hash_teor TEXT,

    selo TEXT,
    lancamento_id INTEGER,
    cancelada_em TEXT,
    cancelada_por TEXT,
    cancelada_motivo TEXT,
    declaracao_selo_tjma_em TEXT,
    declaracao_selo_tjma_por TEXT,

    emitida_em TEXT NOT NULL,
    emitida_por TEXT,
    UNIQUE(numero, ano)
);

CREATE INDEX IF NOT EXISTS ix_rc_certidoes_assento
    ON rc_certidoes(assento_id);
"""


def init_rc_certidao_schema(con: sqlite3.Connection) -> None:
    """Cria a tabela da certidão do Registro Civil. Idempotente."""
    con.executescript(SCHEMA)
    # Colunas da certidão de inteiro teor (texto / reprográfica).
    try:
        import rc_certidao_inteiro_teor as _IT
        migracoes = tuple(_IT.MIGRACOES_CERTIDAO)
    except ImportError:
        migracoes = (
            ("modalidade", "TEXT NOT NULL DEFAULT 'RESUMO'"),
            ("teor_colado", "TEXT"),
            ("imagem_caminho", "TEXT"),
            ("imagem_largura_cm", "REAL"),
            ("imagem_altura_cm", "REAL"),
            ("imagem_margem_esq_cm", "REAL"),
            ("imagem_margem_sup_cm", "REAL"),
        )
    migracoes += (
        ("declaracao_selo_tjma_em", "TEXT"),
        ("declaracao_selo_tjma_por", "TEXT"),
        # A VIA REPROGRÁFICA QUE SAIU DO TERMO DIGITALIZADO (problema #121):
        # o sha256 do arquivo congelado. Vazia = a via antiga, de uma imagem
        # enviada na hora. Ver `rc_digitalizacao.odt_da_certidao`.
        ("digitalizacao_sha256", "TEXT"),
    )
    existentes = {linha[1] for linha in con.execute("PRAGMA table_info(rc_certidoes)")}
    for coluna, tipo in migracoes:
        if coluna not in existentes:
            con.execute(f"ALTER TABLE rc_certidoes ADD COLUMN {coluna} {tipo}")


# ------------------------------------------------------------- as pessoas


def pessoas(con: sqlite3.Connection, assento_id: int) -> list[dict]:
    """As pessoas do assento, na ordem. Só LÊ."""
    return [dict(r) for r in con.execute(
        """SELECT * FROM rc_pessoas WHERE assento_id=?
            ORDER BY ordem, id""", (int(assento_id),))]


MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")


def data_por_extenso(iso: Any) -> str:
    """`1987-05-28` -> `VINTE E OITO DE MAIO DE MIL NOVECENTOS E OITENTA E SETE`.

    A FORMA É A DAS 145 CERTIDÕES REAIS, e não uma escolha: elas escrevem o
    dia e o ano inteiros em palavras, com o dia 1 virando `PRIMEIRO`.

    Eu havia deixado a data ISO sair sob o rótulo `POR EXTENSO` — o rótulo
    prometia uma coisa e a linha entregava outra. Quem pegou foi imprimir a
    certidão de uma pessoa de verdade; nenhum dos 31 testes de domínio via,
    porque neles a data já entrava pronta.
    """
    texto = str(iso or "").strip()[:10]
    partes = texto.split("-")
    if len(partes) != 3:
        return texto
    try:
        ano, mes, dia = (int(x) for x in partes)
        nome_do_mes = MESES[mes - 1]
    except (ValueError, IndexError):
        return texto
    diz_o_dia = "primeiro" if dia == 1 else por_extenso(dia)
    return f"{diz_o_dia} de {nome_do_mes} de {por_extenso(ano)}".upper()


def lugar_do_assento(con: sqlite3.Connection, assento_id: int) -> dict:
    """Livro, folha e termo do assento. Só LÊ.

    ELES MORAM NO ATO DE REGISTRO, e não no assento — e isso não é detalhe de
    arrumação: quem ocupa face do livro é o ATO. O assento guarda só o número
    de ordem, e as averbações que vierem depois não ganham folha nova.

    O número do livro é `numero` mais `complemento` (`A` + `-3` = `A-3`), que é
    como o livro de papel está escrito na capa.

    ASSENTO DE ACERVO/ARQUIVO SEM ATO REGISTRO — o lugar ainda existe: está no
    `livro_volume` do assento e na matrícula (folha/termo). Sem esse recurso a
    certidão sai com LIVRO/FOLHA em ND e o envelope do selo recusa a folha.
    """
    linha = con.execute(
        """SELECT a.folha, a.rotulo, a.numero_ordem,
                  l.numero, l.complemento, s.livro_volume
             FROM rc_atos a
             JOIN rc_assentos s ON s.id = a.assento_id
             LEFT JOIN nu_livros l ON l.id = a.livro_id
            WHERE a.assento_id=? AND a.tipo='REGISTRO'
            ORDER BY a.id LIMIT 1""", (int(assento_id),)).fetchone()
    if linha:
        # O LIVRO ABERTO NO SISTEMA VEM PRIMEIRO; o volume do assento é o do livro
        # de PAPEL, e serve os 244 que vieram do acervo — eles não têm livro aberto
        # aqui, e não deveriam ter: o livro deles já foi escriturado e encerrado.
        livro = (f"{linha['numero'] or ''}{linha['complemento'] or ''}".strip()
                 or (linha["livro_volume"] or ""))
        return {"livro": livro,
                "folha": linha["rotulo"] or linha["folha"],
                "termo": linha["numero_ordem"]}
    return _lugar_pelo_assento(con, assento_id)


def _numero_sem_zero(valor) -> str:
    """`0141` -> `141`. Vazio fica vazio."""
    s = str(valor or "").strip()
    if not s:
        return ""
    try:
        return str(int(s))
    except ValueError:
        return s


def _lugar_pelo_assento(con: sqlite3.Connection, assento_id: int) -> dict:
    """Recurso do acervo/ARQUIVO: livro_volume + matrícula. Só LÊ."""
    assento = con.execute(
        """SELECT numero, livro_volume, matricula
             FROM rc_assentos WHERE id=?""", (int(assento_id),)).fetchone()
    if not assento:
        return {}
    livro = str(assento["livro_volume"] or "").strip()
    termo = assento["numero"]
    folha = ""
    matricula = assento["matricula"]
    if matricula:
        try:
            p = MAT.partes(matricula)
        except MAT.MatriculaError:
            p = None
        if p:
            folha = _numero_sem_zero(p.get("folha"))
            if not termo:
                termo = _numero_sem_zero(p.get("termo")) or termo
            if not livro:
                num = _numero_sem_zero(p.get("livro"))
                letra = str(p.get("livro_nome") or "").strip()
                livro = f"{letra}-{num}" if letra and num else (num or "")
    if not (livro or folha or termo):
        return {}
    return {"livro": livro, "folha": folha or None, "termo": termo}

def _por_papel(lista: list[dict]) -> dict[str, dict]:
    return {p["papel"]: p for p in lista if p.get("papel")}


def _nome(p: dict | None) -> str:
    return str((p or {}).get("nome") or "").strip()


def _e_junta(nomes: list[str]) -> str:
    """`A e B`, `A, B e C`. Vazio quando não há ninguém.

    A certidão escreve "FULANO e SICRANA", e não "FULANO, SICRANA" — é como as
    145 do acervo escrevem.
    """
    limpos = [n for n in nomes if n]
    if not limpos:
        return ""
    if len(limpos) == 1:
        return limpos[0]
    return ", ".join(limpos[:-1]) + " e " + limpos[-1]


# --------------------------------------------------------------- o teor


def _de(quem: dict, papel: str, campo: str,
        dados: dict, chave_do_acervo: str = "") -> str:
    """Um campo da pessoa, ou o que o blob do acervo tinha. So calcula.

    A PESSOA VEM PRIMEIRO, E O BLOB E O RECURSO — e ate 28/08/2026 era so o
    blob. Isso funcionava para os 244 assentos do acervo, que trazem o
    `dados_json` inteiro do E-Oficio, e **nao funcionava para nada que esta
    casa lavrasse**: os nomes de coluna do E-Oficio nao existem no ato novo.
    Medido: a certidao de um casamento lavrado aqui saia com o
    «NOME QUE CADA CONJUGE PASSOU A UTILIZAR» em branco — que e o campo pelo
    qual a certidao de casamento existe.

    NAO E DUAS FONTES PARA A MESMA COISA, que e o defeito que este projeto ja
    pagou duas vezes: e uma fonte (a pessoa) com um LEGADO atras. Quando a
    carga do acervo tiver enchido `rc_pessoas` de todos, o blob para de ser
    lido sozinho — mas so quando isso for medido, e nao por suposicao.
    """
    p = quem.get(papel) or {}
    valor = str(p.get(campo) or "").strip()
    if valor:
        return valor
    return str(dados.get(chave_do_acervo) or "").strip() if chave_do_acervo else ""


def _cpf_da_pessoa(quem: dict, papel: str) -> str:
    """O CPF da pessoa principal, sem chamar RG de CPF. Só calcula."""
    p = quem.get(papel) or {}
    tipo = str(p.get("documento_tipo") or "").strip().upper()
    numero = str(p.get("documento_numero") or "").strip()
    digitos = "".join(c for c in numero if c.isdigit())
    if numero and (tipo == "CPF" or (not tipo and len(digitos) == 11)):
        return numero
    return ""


def _local_do_assento(a: dict, dados: dict, *, nascimento: bool) -> str:
    """O local digitado no ato novo; o blob fica como legado."""
    partes = [str(a.get(k) or "").strip()
              for k in ("local_fato_nome", "local_fato_endereco")]
    partes = list(dict.fromkeys(p for p in partes if p))
    if partes:
        return ", ".join(partes)
    if nascimento:
        return _local_do_nascimento(dados)
    return str(dados.get("strNomeLocalObito") or "").strip()


def _lugar_da_pessoa(quem: dict, papel: str, cidade: str, uf: str,
                     dados: dict, c_acervo: str = "", u_acervo: str = "") -> str:
    """A naturalidade ou a residencia de alguem, na forma «CIDADE/UF»."""
    p = quem.get(papel) or {}
    return _lugar(p.get(cidade) or dados.get(c_acervo),
                  p.get(uf) or dados.get(u_acervo))


def regime_da_certidao(valor: Any) -> str:
    """O regime de bens como a certidao o imprime. So calcula.

    A tela de lavrar e a habilitacao gravam o CODIGO de `hc_schema.REGIMES`
    («COMUNHAO_PARCIAL»), e a certidao do casamento 8366 saia com ele cru
    (08/10/2026). A traducao e a MESMA do termo — `regime_por_extenso`, de
    `rc_modelos_do_livro` —, e nao uma segunda tabela. Codigo traduzido sai em
    maiusculas, como o acervo grava («COMUNHÃO PARCIAL DE BENS»); texto livre
    do acervo passa como veio.
    """
    bruto = str(valor or "").strip()
    if not bruto:
        return ""
    from rc_modelos_do_livro import regime_por_extenso
    extenso = regime_por_extenso(bruto)
    return extenso.upper() if extenso != bruto else bruto


def _linha(rotulo: str, valor: Any) -> list[str]:
    """Rótulo em cima, valor embaixo — a forma das 145 certidões do acervo."""
    return [rotulo, str(valor or "").strip() or SEM_DADO]


def montar_teor(*, assento: sqlite3.Row | dict, pessoas_do_assento: list[dict],
                atos: list[dict], sv: dict, hoje: str,
                lugar: dict | None = None,
                data_extenso: str | None = None,
                data_fato_extenso: str | None = None) -> str:
    """Monta o teor no modelo do CNJ. Só calcula — não grava nada.

    A ORDEM DOS BLOCOS É A DAS 145 CERTIDÕES REAIS. Ela não é arbitrária: é a
    ordem em que quem lê a certidão procura as coisas, e mudá-la faria o
    escrevente conferir na diagonal.
    """
    a = dict(assento)
    especie = str(a.get("especie") or "OUTRO").upper()
    modelo = MODELOS.get(especie, MODELOS["OUTRO"])
    dados = a.get("dados") if isinstance(a.get("dados"), dict) else {}
    if not dados:
        try:
            dados = json.loads(a.get("dados_json") or "{}")
        except (TypeError, ValueError):
            dados = {}

    quem = _por_papel(pessoas_do_assento)
    linhas: list[str] = [modelo["titulo"], ""]

    # --------------------------------------------------- quem, e a matrícula
    linhas += _linha("NOME:", a.get("nome"))
    papel_principal = ({"NASCIMENTO": "REGISTRADO", "NATIMORTO": "REGISTRADO",
                        "OBITO": "FALECIDO"}.get(especie, ""))
    linhas += _linha("CPF", _cpf_da_pessoa(quem, papel_principal)
                     or _documento(dados))
    # A MATRÍCULA SAI COMO ESTÁ. Os 32 dígitos vêm do assento; o sistema não
    # os gera, porque o verificador deles não se explica.
    linhas += _linha("MATRÍCULA Nº", a.get("matricula"))
    linhas.append("")

    # ------------------------------------------------------ o fato e o lugar
    # AS DATAS DO FATO E DO REGISTRO SÃO AS DO ASSENTO, e nunca a de hoje.
    #
    # Eu havia posto aqui o `data_extenso` que a rota passa — que é a data da
    # EMISSÃO. A certidão de um registro de 1957 saía dizendo
    # "DATA DO REGISTRO: vinte e seis de agosto de dois mil e vinte e seis":
    # uma afirmação FALSA, no documento mais definitivo que esta casa emite,
    # sem erro nenhum em lugar nenhum. Só o ensaio contra o acervo real mostrou.
    #
    # `data_extenso` ficou servindo ao FECHO — lá ele é a data de hoje mesmo.
    do_fato = data_fato_extenso or data_por_extenso(a.get("data_fato"))
    do_registro = data_por_extenso(a.get("data_ato"))

    if especie == "NASCIMENTO":
        linhas += _linha("DATA DE NASCIMENTO POR EXTENSO", do_fato)
        linhas += _linha("HORA DE NASCIMENTO",
                         a.get("hora_fato") or dados.get("strHoraNascimento"))
        linhas += _linha("NATURALIDADE", _lugar_da_pessoa(
            quem, "REGISTRADO", "naturalidade_cidade", "naturalidade_uf",
            dados, "strCidade", "strUF"))
        linhas += _linha("SEXO", _sexo_por_extenso(
            _de(quem, "REGISTRADO", "sexo", dados, "strSexo")))
        linhas += _linha("MUNICÍPIO DE REGISTRO E UNIDADE DA FEDERAÇÃO",
                         _lugar(sv.get("ri_cidade"), sv.get("ri_uf")))
        linhas += _linha("LOCAL DE NASCIMENTO",
                         _local_do_assento(a, dados, nascimento=True))
        linhas.append("")
        # A FILIAÇÃO E A AVOENGA — o corpo da certidão de nascimento.
        linhas += _linha("FILIAÇÃO:", _e_junta(
            [_nome(quem.get("PAI")), _nome(quem.get("MAE"))]))
        linhas.append("AVÓS:")
        linhas += _linha("PATERNOS:", _e_junta(
            [_nome(quem.get("AVO_PATERNO")), _nome(quem.get("AVO_PATERNA"))]))
        linhas += _linha("MATERNOS:", _e_junta(
            [_nome(quem.get("AVO_MATERNO")), _nome(quem.get("AVO_MATERNA"))]))
        linhas.append("")
        # O GEMEO E A DNV SAO COLUNAS DO ASSENTO desde 28/08/2026 — antes
        # so existiam dentro do blob do acervo.
        gemeo = a.get("ibge_gemeo")
        linhas += _linha("GÊMEO",
                         ("SIM" if int(gemeo) > 1 else "NÃO")
                         if gemeo not in (None, "") else
                         ("SIM" if dados.get("bitGemeos") else "NÃO"))
        linhas += _linha("NÚMERO DA DECLARAÇÃO DE NASCIDO VIVO",
                         a.get("dnv") or dados.get("strDeclaracaoNascidoVivo"))

    elif especie in ("CASAMENTO", "CASAMENTO_RELIGIOSO"):
        # OS NUBENTES SAO PESSOAS DO ASSENTO desde 28/08/2026. Ate entao a
        # certidao de casamento saia inteira do blob do acervo — e por isso
        # saia VAZIA em qualquer casamento que esta casa lavrasse.
        n1 = _de(quem, "NUBENTE1", "nome", dados, "strNomeConjuge1") \
            or str(a.get("nome") or "").strip()
        n2 = _de(quem, "NUBENTE2", "nome", dados, "strNomeConjuge2")
        linhas += _linha("NOMES", _e_junta([n1, n2]))
        linhas += _linha("DATA DA CELEBRAÇÃO POR EXTENSO", do_fato)

        # O REGIME DE BENS E CAMPO OBRIGATORIO DA CERTIDAO — Lei 6.015/1973,
        # art. 70, item 6. Ele nao estava em lugar nenhum do ato novo, e por
        # isso ganhou coluna: `rc_assentos.regime_bens`.
        linhas += _linha("REGIME DE BENS DO CASAMENTO",
                         regime_da_certidao(a.get("regime_bens")
                                            or dados.get("strRegimeCasamento")))

        # E ESTE E O CAMPO PELO QUAL A CERTIDAO DE CASAMENTO EXISTE: e ele que
        # prova a mudanca de nome. Medido no acervo, o segundo conjuge muda de
        # nome em 17 dos 20 casamentos desta casa.
        linhas += _linha("NOME QUE CADA CÔNJUGE PASSOU A UTILIZAR", _e_junta([
            _de(quem, "NUBENTE1", "nome_pos", dados,
                "strNomePosCasamentoConjuge1") or n1,
            _de(quem, "NUBENTE2", "nome_pos", dados,
                "strNomePosCasamentoConjuge2") or n2]))
        linhas.append("")
        for rotulo, papel in (("PRIMEIRO CÔNJUGE", "NUBENTE1"),
                              ("SEGUNDO CÔNJUGE", "NUBENTE2")):
            if not (quem.get(papel) or {}).get("nome"):
                continue
            linhas.append(f"{rotulo}:")
            linhas += _linha("  DATA DE NASCIMENTO", data_por_extenso(
                _de(quem, papel, "data_nascimento", dados)))
            linhas += _linha("  NATURALIDADE", _lugar_da_pessoa(
                quem, papel, "naturalidade_cidade", "naturalidade_uf", dados))
            linhas += _linha("  ESTADO CIVIL ANTERIOR",
                             _de(quem, papel, "estado_civil", dados))
            linhas += _linha("  PROFISSÃO", _de(quem, papel, "profissao", dados))
            # A FILIAÇÃO DE CADA CÔNJUGE, e não uma só.
            #
            #   O acervo guarda QUATRO filiações no casamento — 1 e 2 são os
            #   pais do primeiro cônjuge, 3 e 4 os do segundo, conferido pelos
            #   sobrenomes. O sistema lia só duas, e a certidão mostrava a
            #   filiação de um deles **como se fosse «a» filiação**: quem
            #   lesse concluiria que aqueles eram os pais dos dois.
            n_conjuge = papel[-1]
            linhas += _linha("  FILIAÇÃO", _e_junta([
                _nome(quem.get(f"PAI_NUBENTE{n_conjuge}")),
                _nome(quem.get(f"MAE_NUBENTE{n_conjuge}"))]))
        # A FILIAÇÃO SOLTA só aparece quando o assento não tem a de cada
        # cônjuge — é o caso do acervo antigo, em que ela veio sem dizer de
        # quem era. Repetir as duas coisas faria a certidão dizer a mesma
        # filiação duas vezes.
        if not any(quem.get(f"{q}_NUBENTE{n}")
                   for q in ("PAI", "MAE") for n in ("1", "2")):
            linhas.append("")
            linhas += _linha("FILIAÇÃO:", _e_junta(
                [_nome(quem.get("PAI")), _nome(quem.get("MAE"))]))

    elif especie in ("OBITO", "NATIMORTO"):
        # O FALECIDO E PESSOA DO ASSENTO desde 28/08/2026, pelo mesmo motivo
        # dos nubentes: sem ele, a certidao de obito de um ato lavrado aqui
        # saia com sexo, idade, estado civil e naturalidade em branco.
        linhas += _linha("DATA DO ÓBITO POR EXTENSO", do_fato)
        linhas += _linha("HORA DO ÓBITO",
                         a.get("hora_fato") or dados.get("strHoraObito"))
        linhas += _linha("SEXO", _sexo_por_extenso(
            _de(quem, "FALECIDO", "sexo", dados, "strSexo")))
        # A IDADE SE CALCULA, e nao se guarda: guardada, ela envelheceria
        # junto com o banco. O que se guarda e a data, que nao muda.
        linhas += _linha("IDADE", _idade_no_obito(
            _de(quem, "FALECIDO", "data_nascimento", dados),
            a.get("data_fato")) or dados.get("intIdade"))
        linhas += _linha("DATA DE NASCIMENTO", data_por_extenso(
            _de(quem, "FALECIDO", "data_nascimento", dados)))
        linhas += _linha("ESTADO CIVIL",
                         _de(quem, "FALECIDO", "estado_civil", dados,
                             "strEstadoCivil"))
        linhas += _linha("PROFISSÃO",
                         _de(quem, "FALECIDO", "profissao", dados,
                             "strProfissao"))
        linhas += _linha("COR OU RAÇA",
                         a.get("cor_raca") or dados.get("strRacaCor"))
        linhas += _linha("NATURALIDADE", _lugar_da_pessoa(
            quem, "FALECIDO", "naturalidade_cidade", "naturalidade_uf", dados,
            "strMunicipioNaturalidade", "strUFNaturalidade"))
        linhas += _linha("ÚLTIMO DOMICÍLIO", _lugar_da_pessoa(
            quem, "FALECIDO", "cidade", "uf", dados,
            "strMunicipioFalecido", "strUFFalecido"))
        linhas += _linha("LOCAL DO ÓBITO",
                         _local_do_assento(a, dados, nascimento=False))
        linhas += _linha("NÚMERO DA DECLARAÇÃO DE ÓBITO",
                         a.get("numero_do")
                         or dados.get("strNumeroDeclaracaoObito"))
        linhas += _linha("NATUREZA E CAUSA DA MORTE",
                         a.get("causa_morte") or dados.get("strCausaMorte"))
        linhas += _linha("ATESTOU O ÓBITO", " — ".join(
            x for x in (str(a.get("atestante") or dados.get("strNomeMedico")
                               or "").strip(),
                        str(a.get("atestante_documento")
                            or dados.get("strCRM")
                            or dados.get("strDocumentoMedico") or "").strip())
            if x))
        linhas += _linha("SEPULTAMENTO OU CREMAÇÃO",
                         a.get("local_sepultamento")
                         or dados.get("strLocalSepultamento"))
        linhas += _linha("TESTAMENTO CONHECIDO",
                         a.get("testamento") or dados.get("strTestamento"))
        linhas.append("")
        linhas += _linha("FILIAÇÃO:", _e_junta(
            [_nome(quem.get("PAI")), _nome(quem.get("MAE"))]))

    # ------------------------------------------------- o registro e o resto
    linhas.append("")
    linhas += _linha("DATA DO REGISTRO POR EXTENSO", do_registro)
    onde = lugar or {}
    linhas += _linha("LIVRO", onde.get("livro"))
    linhas += _linha("FOLHA", onde.get("folha"))
    linhas += _linha("TERMO", onde.get("termo") or a.get("numero"))

    # AS AVERBAÇÕES E ANOTAÇÕES ENTRAM INTEIRAS. É o bloco que a inspeção
    # confere: certidão que esconde averbação é certidão que engana.
    linhas.append("")
    linhas.append("OBSERVAÇÕES/AVERBAÇÕES A ACRESCER:")
    acrescer = [x for x in atos
                if str(x.get("tipo") or "") in ("AVERBACAO", "ANOTACAO",
                                                "RETIFICACAO")]
    if not acrescer:
        linhas.append("NADA CONSTA.")
    for x in acrescer:
        rotulo = str(x.get("tipo") or "").capitalize()
        texto = str(x.get("teor") or "").strip()
        # Fallback: atos antigos sem lavrou/selo no teor ainda mostram nas
        # colunas — a certidão nova não esconde o que a inspeção cobra.
        lavrou = str(x.get("lavrou") or x.get("criado_por") or "").strip()
        selo = str(x.get("selo") or "").strip()
        if lavrou and "Lavrado por:" not in texto and lavrou not in texto:
            texto = f"{texto}\nLavrado por: {lavrou}.".strip()
        if selo and selo not in texto and "Selo:" not in texto:
            texto = f"{texto}\nSelo: {selo}.".strip()
        linhas.append(f"{rotulo}: {texto}".strip())

    # ASSENTO CANCELADO TAMBÉM SE CERTIFICA, e a certidão diz que ele foi.
    # Recusar seria esconder o que existe; calar seria mentir — e é a mesma
    # regra que `atrib_certidao` já aplica ao registro do RCPJ/RTD.
    #
    # O ensaio contra o acervo não podia mostrar esta falta: os 244 assentos
    # estão todos ATIVOS.
    if str(a.get("situacao") or "").upper() == "CANCELADO":
        linhas.append("")
        linhas.append("CERTIFICO ainda que o referido assento encontra-se "
                      "CANCELADO nesta Serventia.")

    # O FECHO, com a serventia e a data.
    linhas.append("")
    casa = str(sv.get("unit_name") or "").strip()
    onde = _lugar(sv.get("ri_cidade"), sv.get("ri_uf"))
    linhas.append(
        f"O referido é verdade e dou fé. {casa}, "
        f"{onde}, {data_extenso or hoje}.")
    return "\n".join(linhas)


def _sexo_por_extenso(valor: Any) -> str:
    """`M` -> MASCULINO. A certidao escreve a palavra, e nao a letra.

    O sistema guarda `M`/`F` (medido no banco de producao) e o acervo guarda
    «Masculino»/«Feminino». A certidao mostra os dois do mesmo jeito.
    """
    texto = str(valor or "").strip()
    if not texto:
        return ""
    letra = texto[0].upper()
    return {"M": "MASCULINO", "F": "FEMININO"}.get(letra, texto.upper())


def _idade_no_obito(nascimento: Any, quando: Any) -> str:
    """Quantos anos o falecido tinha. So calcula.

    DESCONTA O ANIVERSARIO QUE NAO CHEGOU, e isso nao e detalhe: medido nos
    arquivos que esta casa mandou ao IBGE, **3 dos 11 obitos** iam com um ano a
    mais, porque a conta era `ano do obito menos ano do nascimento`.
    """
    n, q = str(nascimento or "")[:10], str(quando or "")[:10]
    if len(n) != 10 or len(q) != 10:
        return ""
    anos = int(q[:4]) - int(n[:4]) - (q[5:10] < n[5:10])
    if anos < 0:
        return ""
    return f"{anos} ano" + ("s" if anos != 1 else "")


def _documento(dados: dict) -> str:
    for chave in ("strCPF", "strCPFNascido", "strDocumento"):
        valor = str(dados.get(chave) or "").strip()
        if valor:
            return valor
    return SEM_INFORMACAO


def _lugar(cidade: Any, uf: Any) -> str:
    """`Imperatriz` + `MA` -> `Imperatriz/MA`. E NÃO DOBRA A UF.

    Medido: 193 dos nascimentos do acervo trazem a cidade em `strCidade`, e
    algumas já vêm com o estado dentro — `IMPERATRIZ/MA.`. Somar `strUF` a
    isso dava `IMPERATRIZ/MA./MA` na certidão.

    Não se conserta o dado do acervo: ele é o que a casa escreveu, e a certidão
    reproduz. O que se conserta é não acrescentar o que já está lá.
    """
    c = str(cidade or "").strip()
    u = str(uf or "").strip()
    if not c:
        return u
    if not u or "/" in c or c.upper().endswith(u.upper()):
        return c
    return f"{c}/{u}"


def _local_do_nascimento(dados: dict) -> str:
    """O lugar do parto, como o acervo o descreve — hospital, domicílio…"""
    partes = [str(dados.get(k) or "").strip() for k in
              ("strNomeLocal", "strLN_endereco", "strLN_bairro")]
    partes = [p for p in partes if p]
    lugar = _lugar(dados.get("strCidade"), dados.get("strUF"))
    if lugar:
        partes.append(lugar)
    return ", ".join(partes)


# ------------------------------------------------------------- emitir


def proximo_numero(con: sqlite3.Connection, ano: int) -> int:
    """O próximo número do exercício. Só LÊ — não consome nada.

    GET não abre transação de escrita: a ficha do assento mostra "a próxima
    será a N", e contador consumido num GET fica preso no `busy_timeout`.
    """
    linha = con.execute("SELECT MAX(numero) n FROM rc_certidoes WHERE ano=?",
                        (int(ano),)).fetchone()
    return int(linha["n"] if linha and linha["n"] else 0) + 1


def hash_certidao(numero: int, ano: int, nome: str, teor: str,
                  agora: str) -> str:
    """Impressão digital do que saiu."""
    return hashlib.sha256(
        f"{numero}|{ano}|{nome}|{teor}|{agora}".encode()).hexdigest()


# ------------------------------------------------ 1a certidao do registro
# Pedido do oficial 09/09/2026: a primeira certidao do nascimento (e do
# obito/natimorto) e gratuita e usa o selo do REGISTRO (REGNAS/REGOBI...),
# nao compra CERTID em /segunda-via. Item 14.a / 14.c / 14.d — "registro ...
# bem como pela primeira certidao respectiva. Isento".


def especies_com_primeira_certidao_no_registro() -> tuple[str, ...]:
    return ("NASCIMENTO", "OBITO", "NATIMORTO")


def origens_importadas_sem_selo_de_registro() -> tuple[str, ...]:
    """Origens em que o assento veio de fora e o REGISTRO local pode nao ter selo.

    Pedido do oficial 09/09/2026: nesses casos, sem selo do REGISTRO,
    a certidao se presume segunda via (compra CERTID) — nao 1a via gratuita.
    """
    return ("EOFICIO", "ARQUIVO", "IMPORTACAO")


def eh_primeira_certidao_do_registro(
        con: sqlite3.Connection, assento_id: int, *,
        certidao_id: int | None = None,
        especie: str | None = None) -> bool:
    """True se esta emissao e a 1a certidao ativa coberta pelo selo do registro.

    Conta so certidoes NAO canceladas. Se a unica ativa e a que estamos
    emitindo agora (`certidao_id`), ainda e a primeira.

    Assento IMPORTADO (EOFICIO/ARQUIVO) SEM selo do REGISTRO: nao e 1a via —
    presume-se segunda via (oficial 09/09/2026).
    """
    esp = str(especie or "").strip().upper()
    row_a = con.execute(
        "SELECT especie, COALESCE(origem,'') FROM rc_assentos WHERE id=?",
        (int(assento_id),)).fetchone()
    if not esp:
        esp = str((row_a[0] if row_a else "") or "").strip().upper()
    if esp not in especies_com_primeira_certidao_no_registro():
        return False
    origem = str((row_a[1] if row_a else "") or "").strip().upper()
    if origem in origens_importadas_sem_selo_de_registro():
        if not selo_do_registro(con, assento_id):
            return False
    if certidao_id is None:
        n = con.execute(
            """SELECT COUNT(*) FROM rc_certidoes
                WHERE assento_id=? AND cancelada_em IS NULL""",
            (int(assento_id),)).fetchone()[0]
        return int(n) == 0
    n = con.execute(
        """SELECT COUNT(*) FROM rc_certidoes
            WHERE assento_id=? AND cancelada_em IS NULL AND id<>?""",
        (int(assento_id), int(certidao_id))).fetchone()[0]
    return int(n) == 0


def selo_do_registro(con: sqlite3.Connection, assento_id: int) -> str:
    """Numero do selo do ato REGISTRO do assento, ou ''."""
    row = con.execute(
        """SELECT selo FROM rc_atos
            WHERE assento_id=? AND tipo='REGISTRO'
              AND IFNULL(TRIM(selo),'') != ''
         ORDER BY id DESC LIMIT 1""",
        (int(assento_id),)).fetchone()
    return str((row[0] if row else "") or "").strip()


def espelhar_selo_do_registro_na_certidao(
        con: sqlite3.Connection, certidao_id: int, assento_id: int) -> str:
    """Copia o selo do REGISTRO para a certidao. ESCREVE. Nao fala com a rede.

    Nao reinsere em sd_selos — o numero ja existe no razao (ato do registro).
    So preenche rc_certidoes.selo para o papel imprimir o REGNAS.
    Nao sobrescreve se a certidao ja tiver selo proprio.
    """
    atual = con.execute(
        "SELECT COALESCE(selo,'') FROM rc_certidoes WHERE id=?",
        (int(certidao_id),)).fetchone()
    if atual and str(atual[0] or "").strip():
        return str(atual[0]).strip()
    selo = selo_do_registro(con, assento_id)
    if not selo:
        return ""
    con.execute(
        "UPDATE rc_certidoes SET selo=? WHERE id=?",
        (selo, int(certidao_id)))
    return selo


def como_vai_selar(con: sqlite3.Connection, assento_id: int, *,
                   especie: str | None = None) -> dict:
    """Como esta certidão vai ser selada, ANTES de emitir. Só lê.

    **ISTO EXISTE PORQUE A TELA COBROU CALADA — relato do oficial em
    10/09/2026: «na ultima o selo que era pra ser gratuito foi pago».**

    Medido na produção: o assento 1233 (Braulio Galvao Oliveira Ribeiro,
    nascimento de 1996) veio do ARQUIVO e **não tem selo de registro**. A regra
    que o oficial deu em 09/09 presume segunda via nesse caso — e a tela,
    obedecendo-a, comprou um `CERTID` **pago** sem dizer que ia comprar. O
    escrevente só descobriu ao ler o selo.

    **A PRESUNÇÃO FICA, e a decisão é do oficial em 10/09/2026 («resolva»).**
    O sistema não tem como saber se a pessoa já tirou a primeira via em 1996:
    ela não passou por aqui. Das duas hipóteses, cobrar por engano se desfaz
    (cancela e reemite) e **deixar de cobrar o que era devido não** — a
    serventia absorve, e a correição pergunta. O que muda é que agora a tela
    **diz** antes.

    O que resolve o caso legítimo continua sendo a mão de quem sabe: a caixa
    «Selo gratuito / isento», com o motivo escrito, que vai impresso no selo.

    Devolve `{"via", "cobra", "selo_do_registro", "porque", "avisar"}`.
    `avisar` é **True só no caso que custou dinheiro**: espécie que teria 1ª
    via gratuita, assento importado e sem selo de registro.
    """
    esp = str(especie or "").strip().upper()
    linha = con.execute(
        "SELECT especie, COALESCE(origem,'') FROM rc_assentos WHERE id=?",
        (int(assento_id),)).fetchone()
    if not esp:
        esp = str((linha[0] if linha else "") or "").strip().upper()
    origem = str((linha[1] if linha else "") or "").strip().upper()

    # **A REGRA É LIDA DA MESMA FUNÇÃO QUE SELA, e não copiada para cá.** Duas
    # cópias divergiriam no primeiro conserto, e a tela passaria a prometer uma
    # coisa enquanto o selo faz outra — que é o defeito que este aviso existe
    # para não cometer.
    primeira = eh_primeira_certidao_do_registro(
        con, int(assento_id), certidao_id=None, especie=esp)
    selo_reg = selo_do_registro(con, int(assento_id))

    if primeira:
        return {"via": "PRIMEIRA", "cobra": False, "selo_do_registro": selo_reg,
                "avisar": False,
                "porque": ("1ª certidão: é gratuita e usa o selo do registro "
                           f"{selo_reg} — não compra selo novo."
                           if selo_reg else
                           "1ª certidão: é gratuita e usa o selo do registro "
                           "— mas o registro ainda não tem selo. Sele o "
                           "registro primeiro.")}

    tem_1a_via = esp in especies_com_primeira_certidao_no_registro()
    importado_sem_selo = (tem_1a_via
                          and origem in origens_importadas_sem_selo_de_registro()
                          and not selo_reg)
    if importado_sem_selo:
        return {
            "via": "SEGUNDA", "cobra": True, "selo_do_registro": "",
            "avisar": True,
            "porque": (
                f"Este assento veio de fora ({origem.title()}) e o registro "
                "não tem selo desta serventia — então a certidão é tratada "
                "como SEGUNDA VIA, e o selo será COBRADO. Se ela é gratuita "
                "neste caso, marque «Selo gratuito / isento» e escreva o "
                "motivo: sem a marcação o selo sai pago."),
        }
    return {"via": "SEGUNDA", "cobra": True, "selo_do_registro": selo_reg,
            "avisar": False,
            "porque": ("Segunda via: o selo será cobrado. Se houver "
                       "gratuidade, marque «Selo gratuito / isento».")}


def emitir(con: sqlite3.Connection, assento_id: int, *, sv: dict, hoje: str,
           agora: str, data_extenso: str | None = None,
           data_fato_extenso: str | None = None,
           requerente: str | None = None, finalidade: str | None = None,
           usuario: str | None = None,
           modalidade: str | None = None,
           teor_colado: str | None = None,
           imagem_caminho: str | None = None,
           imagem_largura_cm: float | None = None,
           imagem_altura_cm: float | None = None,
           imagem_margem_esq_cm: float | None = None,
           imagem_margem_sup_cm: float | None = None) -> dict:
    """Emite a certidão do assento. ESCREVE.

    SEM FILIAÇÃO NÃO HÁ CERTIDÃO DE NASCIMENTO, e a recusa diz o que fazer: o
    assento existe no livro, e o que falta é trazer a filiação — pela carga do
    acervo, ou lançando à mão na ficha.

    modalidade escolhe o papel: RESUMO (quadro CNJ), INTEIRO_TEXTO (teor
    colado entre aspas) ou INTEIRO_REPRO (imagem do livro). Inteiro teor **não
    inventa** o texto do registro.
    """
    assento = con.execute("SELECT * FROM rc_assentos WHERE id=?",
                          (int(assento_id),)).fetchone()
    if not assento:
        raise CertidaoRCPNError(f"Assento {assento_id} não encontrado.")

    do_assento = pessoas(con, assento_id)
    especie = str(assento["especie"] or "").upper()
    quem = _por_papel(do_assento)
    if especie == "NASCIMENTO" and not (quem.get("PAI") or quem.get("MAE")):
        raise CertidaoRCPNError(
            f"O assento de {assento['nome']} está sem filiação, e a filiação é "
            f"o corpo da certidão de nascimento — sem ela o papel sai "
            f"incompleto. O assento existe no livro; o que falta é trazer a "
            f"filiação, pela carga do acervo ou lançando à mão na ficha.")

    atos = [dict(r) for r in con.execute(
        "SELECT * FROM rc_atos WHERE assento_id=? ORDER BY id",
        (int(assento_id),))]

    import rc_certidao_inteiro_teor as IT
    modo = IT.normalizar_modalidade(modalidade)
    lugar = lugar_do_assento(con, assento_id)
    teor_colado_limpo = (teor_colado or "").strip() or None
    img_caminho = (imagem_caminho or "").strip() or None
    try:
        if modo == IT.INTEIRO_TEXTO:
            intro = IT.introducao(
                especie=especie, nome=assento["nome"],
                matricula=assento["matricula"],
                livro=lugar.get("livro") or lugar.get("livro_numero")
                      or assento["livro_volume"],
                folha=lugar.get("folha"),
                termo=lugar.get("termo") or assento["numero"],
                cns=(sv or {}).get("ri_cns"),
                cidade=(sv or {}).get("ri_cidade"),
                uf=(sv or {}).get("ri_uf"),
                modo=IT.INTEIRO_TEXTO)
            # Inteiro teor em texto: cola o livro e acresce rc_atos que
            # ainda não estão no colado (CPF, casamento, retificação…).
            teor_colado_limpo = IT.completar_teor_colado_com_atos(
                teor_colado_limpo, atos) or None
            teor = IT.montar_teor_texto(introducao_txt=intro,
                                       teor_colado=teor_colado_limpo)
        elif modo == IT.INTEIRO_REPRO:
            if not img_caminho:
                raise IT.InteiroTeorError(
                    "Envie ou escolha a imagem do assento. A certidão de "
                    "inteiro teor por cópia reprográfica é a fotografia do "
                    "livro — sem ela o papel promete o que não entrega.")
            intro = IT.introducao(
                especie=especie, nome=assento["nome"],
                matricula=assento["matricula"],
                livro=lugar.get("livro") or lugar.get("livro_numero")
                      or assento["livro_volume"],
                folha=lugar.get("folha"),
                termo=lugar.get("termo") or assento["numero"],
                cns=(sv or {}).get("ri_cns"),
                cidade=(sv or {}).get("ri_cidade"),
                uf=(sv or {}).get("ri_uf"),
                modo=IT.INTEIRO_REPRO)
            teor = IT.montar_teor_repro(introducao_txt=intro)
        else:
            teor = montar_teor(assento=assento, pessoas_do_assento=do_assento,
                               atos=atos, sv=sv, hoje=hoje,
                               lugar=lugar,
                               data_extenso=data_extenso,
                               data_fato_extenso=data_fato_extenso)
            teor_colado_limpo = None
            img_caminho = None
    except IT.InteiroTeorError as erro:
        raise CertidaoRCPNError(str(erro)) from erro

    ano = int(str(hoje)[:4])
    numero = proximo_numero(con, ano)
    # A LINHA DA ASSINATURA A MAO SAI ANTES DO HASH, E NAO ANTES DO
    # INSERT. Esta chamada estava DENTRO do texto do SQL — colada entre
    # as aspas e o `INSERT INTO`, de modo que o banco recusava com
    # «near "teor": syntax error» e a certidao NAO SAIA. Posta so antes
    # do `con.execute`, o teor gravado deixaria de ser o teor que o
    # `hash_certidao` carimbou, e a conferencia de «este e o teor que
    # saiu?» passaria a falhar em toda certidao nova.
    teor = sem_linha_de_assinatura_a_mao(teor)
    impressao = hash_certidao(numero, ano, str(assento["nome"]), teor, agora)
    try:
        cur = con.execute(
            """INSERT INTO rc_certidoes(numero, ano, assento_id, especie,
                   nome, matricula, requerente, finalidade, atos_no_assento,
                   teor, hash_teor, emitida_em, emitida_por,
                   modalidade, teor_colado, imagem_caminho,
                   imagem_largura_cm, imagem_altura_cm,
                   imagem_margem_esq_cm, imagem_margem_sup_cm)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (numero, ano, int(assento_id), especie, assento["nome"],
             assento["matricula"], (requerente or "").strip() or None,
             (finalidade or "").strip() or None, len(atos), teor, impressao,
             agora, usuario, modo, teor_colado_limpo, img_caminho,
             imagem_largura_cm, imagem_altura_cm,
             imagem_margem_esq_cm, imagem_margem_sup_cm))
    except sqlite3.IntegrityError as erro:
        raise CertidaoRCPNError(
            f"A certidão {numero}/{ano} acabou de ser emitida por outro "
            f"atendimento. Emita de novo — o próximo número sai livre."
        ) from erro
    return {"certidao_id": int(cur.lastrowid), "numero": numero, "ano": ano,
            "teor": teor, "hash": impressao, "atos_no_assento": len(atos),
            "modalidade": modo}


def cancelar(con: sqlite3.Connection, certidao_id: int, *, motivo: str,
             agora: str, usuario: str | None = None,
             selo_cancelado_tjma: Any = False) -> dict:
    """Cancela a certidão, com motivo escrito. ESCREVE. O teor FICA.

    Certidão que saiu da casa não se apaga: ela está na mão de alguém. O que
    se registra é que esta serventia a cancelou, e por quê.
    """
    linha = ler(con, certidao_id)
    if not linha:
        raise CertidaoRCPNError(f"Certidão {certidao_id} não encontrada.")
    if linha["cancelada_em"]:
        raise CertidaoRCPNError(
            f"A certidão {linha['numero']}/{linha['ano']} já está cancelada "
            f"desde {linha['cancelada_em']}.")
    texto = (motivo or "").strip()
    if len(texto) < 10:
        raise CertidaoRCPNError(
            "Escreva por que a certidão foi cancelada. Ela está na mão de "
            "alguém, e o motivo é o que explica a segunda via.")
    if not CANC.declaracao_confirmada(selo_cancelado_tjma):
        raise CertidaoRCPNError(CANC.MENSAGEM_DECLARACAO_OBRIGATORIA)
    con.execute(
        """UPDATE rc_certidoes SET cancelada_em=?, cancelada_por=?,
               cancelada_motivo=?, declaracao_selo_tjma_em=?,
               declaracao_selo_tjma_por=? WHERE id=?""",
        (agora, usuario, texto, agora, usuario, int(certidao_id)))
    suportes = CANC.concluir(
        con, tabela="rc_certidoes", ato_id=int(certidao_id), motivo=texto,
        agora=agora, usuario=usuario)
    return {"certidao_id": int(certidao_id), "motivo": texto, **suportes}


# --------------------------------------------------------------- consultas


def ler(con: sqlite3.Connection, certidao_id: int) -> sqlite3.Row | None:
    """A certidão, com o teor congelado. Só LÊ."""
    return con.execute("SELECT * FROM rc_certidoes WHERE id=?",
                       (int(certidao_id),)).fetchone()


def do_assento(con: sqlite3.Connection, assento_id: int) -> list[dict]:
    """As certidões daquele assento, da mais nova. Só LÊ."""
    return [dict(r) for r in con.execute(
        """SELECT id, numero, ano, requerente, finalidade, atos_no_assento,
                  hash_teor, selo, cancelada_em, emitida_em, emitida_por
             FROM rc_certidoes WHERE assento_id=? ORDER BY id DESC""",
        (int(assento_id),))]


def listar(con: sqlite3.Connection, limite: int = 100) -> list[dict]:
    """As certidões emitidas, da mais nova. Só LÊ."""
    return [dict(r) for r in con.execute(
        """SELECT id, numero, ano, especie, nome, matricula, requerente,
                  cancelada_em, emitida_em, emitida_por
             FROM rc_certidoes ORDER BY id DESC LIMIT ?""", (int(limite),))]


def buscar(con: sqlite3.Connection, texto: str, limite: int = 50) -> list[dict]:
    """Acha o assento por nome, sem acento e sem caixa, ou por matrícula.

    A pergunta do guichê é "a certidão de fulano", e não "o assento 84 do
    Livro A-3". A busca por nome usa a forma normalizada da casa — `UPPER()`
    do SQLite é ASCII, e no Registro Civil quase todo nome tem acento.
    """
    alvo = (texto or "").strip()
    if not alvo:
        return []
    n = normalizar_nome(alvo) or ""
    so_digitos = "".join(c for c in alvo if c.isdigit())
    con.create_function("nome_da_casa", 1, lambda v: normalizar_nome(v) or "")
    condicoes = ["nome_da_casa(nome) LIKE ?"]
    valores: list[Any] = [f"%{n}%"]
    if so_digitos:
        condicoes.append("REPLACE(REPLACE(matricula,' ',''),'.','') LIKE ?")
        valores.append(f"%{so_digitos}%")
    return [dict(r) for r in con.execute(
        f"""SELECT id, especie, nome, matricula, numero, data_ato, situacao
              FROM rc_assentos WHERE {' OR '.join(condicoes)}
             ORDER BY nome LIMIT ?""", (*valores, int(limite)))]


def titulo_do_modelo(especie) -> str:
    """O titulo da certidao, o das 145 reais. So consulta."""
    e = str(especie or "OUTRO").upper()
    return MODELOS.get(e, MODELOS["OUTRO"])["titulo"]


def teor_sem_titulo(teor: str, titulo: str) -> str:
    """Tira o titulo da primeira linha do teor congelado, se ele estiver la.

    O papel da certidao ja poe o titulo no cabecalho; repetir a mesma linha
    como primeiro campo faria o documento parecer ter dois comecos.
    """
    texto = teor or ""
    linhas = texto.splitlines()
    if not linhas:
        return texto
    if linhas[0].strip() == (titulo or "").strip():
        i = 1
        if i < len(linhas) and not linhas[i].strip():
            i += 1
        return "\n".join(linhas[i:])
    return texto
