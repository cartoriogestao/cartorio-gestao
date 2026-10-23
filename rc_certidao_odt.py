"""Certidão RCPN: preenche o ODT da casa.

O molde guarda o desenho. Os valores são @ da casa. Nada é redesenhado.
Anotações de cadastro: um campo pequeno, por extenso, sem tabela.
"""
from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

PASTA_DOS_MOLDES = Path(__file__).resolve().parent / "modelos"

# O MOLDE DE CADA ESPECIE. Sao cinco arquivos (eram tres ate o LD01), e nao um
# com condicoes dentro: quem os edita e o oficial, no LibreOffice, e um papel
# por especie e o que ele consegue abrir e ajustar. Os de casamento, obito,
# natimorto e Livro E nasceram do de nascimento — mesma geometria, mesmas
# cores, mesmas caixas de selo —, e o script que os deriva mora em
# `tools/moldes_do_civil.py`.
MOLDE_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "certidao_nascimento_modelo.odt",
    "CASAMENTO": "certidao_casamento_modelo.odt",
    "CASAMENTO_RELIGIOSO": "certidao_casamento_modelo.odt",
    "OBITO": "certidao_obito_modelo.odt",
    # O NATIMORTO E O LIVRO E — LD01, 21/10/2026, derivados do de nascimento
    # pela mesma ferramenta. O Livro E é UM papel para as seis espécies, como
    # é um termo só; o título dele é marcador (`@titulolivroe`).
    "NATIMORTO": "certidao_natimorto_modelo.odt",
    "EMANCIPACAO": "certidao_livro_e_modelo.odt",
    "INTERDICAO": "certidao_livro_e_modelo.odt",
    "AUSENCIA": "certidao_livro_e_modelo.odt",
    "TUTELA": "certidao_livro_e_modelo.odt",
    "UNIAO_ESTAVEL": "certidao_livro_e_modelo.odt",
    "OPCAO_NACIONALIDADE": "certidao_livro_e_modelo.odt",
}

# O de nascimento continua alcancavel pelo nome antigo — ha codigo e teste que
# o citam, e a certidao sem especie declarada cai nele.
MOLDE = PASTA_DOS_MOLDES / MOLDE_DA_ESPECIE["NASCIMENTO"]


def molde_da_especie(especie) -> Path:
    """O arquivo do molde daquela especie. So calcula."""
    nome = str(especie or "").strip().upper()
    return PASTA_DOS_MOLDES / MOLDE_DA_ESPECIE.get(
        nome, MOLDE_DA_ESPECIE["NASCIMENTO"])

# A QUE ESPECIE ESTE MOLDE SERVE — e ele serve UMA.
#
# **ACHADO EM 01/09/2026, revisando as certidoes a pedido do oficial: ha um
# molde so, e as TRES especies imprimiam nele.** O titulo dele e texto fixo,
# «CERTIDAO DE NASCIMENTO», e nao um marcador — de modo que uma certidao de
# obito saia com o cabecalho de nascimento, com caixa de DNV e de gemeos.
#
# `rc_certidao_quadro` monta os dados das tres especies certos; era so o
# PAPEL que era de uma. E a producao tem **uma certidao, de nascimento** —
# ninguem foi atingido, e este e o momento de fechar a porta.
#
# **PAPEL QUE AFIRMA A ESPECIE ERRADA E PIOR QUE PAPEL NENHUM**: campo vazio
# nao afirma nada, e um cabecalho errado afirma. E a mesma regra do selo —
# «nao se sela por caminho que a casa nunca usou» —, e a do instrumento de
# protesto, que recusa sem o ato lavrado.
#
# Sai desta lista o dia em que os moldes de casamento e obito existirem
# (Anexos V e VI do provimento).
#
# **E ELAS PASSARAM DE UMA PARA TRES EM 01/09/2026**, quando o oficial mandou
# aplicar as correcoes «nas outras certidoes de registro civil tambem». Ate
# entao casamento e obito nao imprimiam nada: a guarda os recusava, e com
# razao — mas isso deixava o balcao sem papel para as duas.
#
# **O NATIMORTO E O LIVRO E FICARAM DE FORA ATÉ O LD01 (21/10/2026)**, e não
# por esquecimento: o natimorto tem campos próprios (a certidão dele não
# afirma nascimento com vida) e o Livro E registra seis coisas diferentes
# entre si. Papel derivado no chute seria o defeito que esta guarda existe
# para impedir — e por isso os dois ganharam molde PRÓPRIO, com as caixas do
# que o assento deles tem, e não o de nascimento: o 1º de natimorto sai
# gratuito (LRP art. 30) e não tinha o que imprimir. O «OUTRO» continua
# recusado: não se sabe o que ele registra.
ESPECIES_QUE_O_MOLDE_SERVE: frozenset[str] = frozenset(MOLDE_DA_ESPECIE)


class MoldeError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""

# As duas imagens do molde (QR do Antônio). Troca-se o PNG quando há selo.
_QR_SELO1 = "Pictures/100000000000007D0000007D115A0E1F.png"
_QR_SELO2 = "Pictures/100000000000007D0000007DE6389898.png"


def _xml(v) -> str:
    t = str(v or "").strip()
    return escape(t) if t else " "


def _cidade_uf(cidade, uf) -> str:
    a, b = str(cidade or "").strip(), str(uf or "").strip()
    if a and b:
        return f"{a}/{b}"
    return a or b


def _up(v) -> str:
    t = str(v or "").strip()
    return t.upper() if t else " "


def _txt(v) -> str:
    t = str(v or "").strip()
    return t if t else " "


def _rs(v) -> str:
    """Moeda do selo, no jeito brasileiro: 53,58."""
    if v is None or v == "":
        return " "
    try:
        n = float(v)
    except (TypeError, ValueError):
        t = str(v).strip()
        return t if t else " "
    s = f"{n:.2f}".replace(".", ",")
    return s


def _nome_de(pessoa) -> str:
    if isinstance(pessoa, dict):
        return str(pessoa.get("nome") or "").strip()
    return str(pessoa or "").strip()


def _selos_da_certidao(certidao: dict) -> list[dict]:
    """Até dois selos: os do sistema, não os números do Antônio."""
    lista = []
    brutos = certidao.get("selos") if isinstance(certidao.get("selos"), list) else []
    for item in brutos:
        if isinstance(item, dict):
            n = str(item.get("numero") or item.get("selo") or "").strip()
            t = str(item.get("texto") or "").strip()
        else:
            n, t = str(item or "").strip(), ""
        if n or t:
            lista.append({"numero": n, "texto": t})
    if not lista:
        n = str(certidao.get("selo") or "").strip()
        t = str(certidao.get("selo_texto") or "").strip()
        if n or t:
            lista.append({"numero": n, "texto": t})
    return lista[:2]


# A REGUA DOS VALORES SAIU DAQUI EM 01/09/2026, e mora em `selo_no_papel`.
#
# Ela nasceu neste arquivo, para o molde desta certidao; quando o oficial
# mandou aplicar «também para todos demais atos do cartório, inclusive etiqueta
# de reconhecimento de firma e autenticação de cópia», deixar a copia aqui
# daria **seis versoes divergentes** do pedaco que imprime dinheiro num papel
# assinado. E a licao do nucleo, e a da `normalizar_nome` pela quinta vez.
#
# O que ficou aqui e so o que e DESTE molde: os marcadores `@`, as caixas do
# selo e as somas gerais.
import selo_no_papel as SNP

_FUNDOS_DO_PAPEL = SNP.FUNDOS_DO_PAPEL
ROTULO_NO_PAPEL = SNP.ROTULO_NO_PAPEL


def _valores_do_selo(item: dict) -> dict[str, str]:
    """O selo daquele quadro, no vocabulario do molde. So calcula.

    **A composicao e de `selo_no_papel`** — uma regua para os papeis das seis
    atribuicoes. Aqui so se traduz para os nomes que o molde usa, e se poe o
    espaco em branco onde o molde nao pode receber vazio.
    """
    d = SNP.do_papel(item)
    # **AS LINHAS SAO AS DO CARIMBO DAS OUTRAS CERTIDOES** — 17/09/2026,
    # `selo_no_papel.linhas_do_carimbo`, feitio de certidao. Ate aqui este
    # molde montava as dele por conta propria e o `.odt` do RI montava as
    # dele: duas montagens do mesmo carimbo, e a divergencia seria entre duas
    # certidoes assinadas que falam do mesmo selo.
    #
    #   `ato` e `valores` sao a segunda e a ultima linha do carimbo; o
    #   requerente e a do meio, e sai vazio quando o selo nao declara parte.
    #   **A linha de valores leva as marcas do selo** (`Selo Isento`,
    #   `Diferido`) coladas nela, porque e o numero ao lado que elas
    #   qualificam.
    #
    #   **CADA PEDACO PELO NOME, e nao pela posicao na lista**: o molde tem um
    #   marcador por linha, e pedir `linhas[1]` faria o papel do oficial
    #   depender da ordem de uma lista de outro modulo — no dia em que o
    #   carimbo ganhasse uma linha, a certidao sairia com o requerente no
    #   lugar do ato, sem erro em lugar nenhum.
    texto_do_selo = (item or {}).get("texto") if isinstance(item, dict) else item
    return {
        "numero": d["numero"] or " ",
        "detalhe": d["detalhe"] or " ",
        "ato": SNP.ato_e_data(texto_do_selo, SNP.CERTIDAO) or " ",
        "requerente": SNP.requerente(texto_do_selo) or " ",
        "consulta": SNP.link_de_consulta(d["numero"], texto_do_selo) or " ",
        "valores": SNP.valores_com_marcas(texto_do_selo) or " ",
        "total": d["total"],
        "emol": d["emol"],
        "ferc": d["ferc"],
        "fadep": d["fadep"],       # o rotulo do papel; a sigla e `FADP`
        "femp": d["femp"],
        "ferrfis": d["ferrfis"],
        "_total_n": d["_total_n"],
        "_emol_n": d["_emol_n"],
        "_ferc_n": d["_ferc_n"],
        "_fadep_n": d["_fadep_n"],
        "_femp_n": d["_femp_n"],
        "_ferrfis_n": d["_ferrfis_n"],
    }


def _soma(vals: list[dict], chave: str) -> str:
    nums = [v.get(chave) for v in vals if v.get(chave) is not None]
    if not nums:
        return " "
    try:
        return _rs(sum(float(n) for n in nums))
    except (TypeError, ValueError):
        return " "


def valores(quadro: dict, certidao: dict, sv: dict) -> dict[str, str]:
    """O VOCABULÁRIO que o molde pode usar — e não a lista do que ele usa.

    **Sobra aqui não é código morto**, e a distinção importa: o `.odt` é
    editado pelo oficial no LibreOffice, e ele pode repor amanhã um campo que
    hoje tirei do papel (os valores por selo, por exemplo). Se o mapeamento
    tivesse sido apagado junto, o campo reposto sairia impresso como
    `@selo1_total` numa certidão assinada.

    **A direção que dói é a outra** — marcador no molde sem mapeamento aqui —,
    e essa `tests/test_rc_certidao_molde.py` varre.
    """
    q = quadro or {}
    sv = sv or {}
    certidao = certidao or {}
    dma = q.get("dma_fato") or {}
    dma_reg = q.get("dma_registro") or {}
    gemeo = str(q.get("gemeo") or "").strip()
    local = str(q.get("local_nascimento") or "").strip()
    mun = _cidade_uf(q.get("municipio_nascimento"),
                     q.get("municipio_nascimento_uf"))
    # `local_cheio` e a caixa unica «LOCAL, MUNICIPIO DE NASCIMENTO E UF» do
    # molde antigo, e continua sendo `@nomelocalnascimento`. O Anexo IV tem
    # TRES caixas ali — local, municipio e UF —, e para elas entraram
    # `@local_nascimento`, `@municipio_nascimento` e `@uf_nascimento`. O
    # antigo fica porque o oficial edita o molde: se ele repuser a caixa
    # unica, o marcador continua sabendo montar a frase.
    local_cheio = ", ".join(x for x in (local, mun) if x)

    # Filiação da casa: 1 = mãe, 2 = pai.
    nome_mae = _nome_de(q.get("mae"))
    nome_pai = _nome_de(q.get("pai"))
    if not (nome_mae or nome_pai):
        fil = str(q.get("filiacao") or "")
        partes = [p.strip() for p in fil.split(" e ") if p.strip()]
        if len(partes) >= 2:
            nome_mae, nome_pai = partes[0], partes[1]
        elif partes:
            nome_mae = partes[0]

    cadastro = str(q.get("anotacoes_cadastro") or "").strip() or "Não há."
    averb = str(q.get("anotacoes") or "").strip() or "Não há."

    titular = (str(q.get("oficial") or "").strip()
               or str(sv.get("serventia_titular") or "").strip())
    escrevente = (str(certidao.get("emitida_por") or "").strip() or titular)

    # **SAO DUAS FUNCOES, E HAVIA UM MARCADOR SO — relato do oficial em
    # 10/09/2026: «fomos emitir uma certidao de nascimento e o oficial estava
    # com nome de escrevente».**
    #
    # O rodape do Anexo IV tem duas colunas com um nome e um cargo em cada: a
    # da esquerda e o DELEGATARIO (o «Nome do Oficial / Oficial de Registro
    # Civil» do modelo) e a da direita e QUEM ASSINA aquela via («Nome do
    # Oficial/Escrevente / Cargo»). O molde usava `@funcaoregistrador` nas
    # duas.
    #
    # Em 09/09 ele foi apontado para `emitida_funcao` para consertar a
    # DIREITA — ali saia «Tabeliao e Oficial de Registro» sob o nome da
    # Elisa, e o oficial relatou. Com um marcador so, consertar um lado
    # estragava o outro: medido na certidao 21 da producao (10/09/2026 09:12,
    # emitida pela Elisa), o papel saiu com «MARIO EXEMPLO DOS SANTOS /
    # Escrevente Autorizado».
    #
    # Agora sao dois, um por coluna. **Cargo errado debaixo do nome do
    # delegatario e afirmacao falsa em papel assinado** — pior que campo
    # vazio, que nao afirma nada.
    cargo_do_titular = (
        str(sv.get("serventia_titulo") or "").strip()
        # `q["cargo"]` tambem prefere `emitida_funcao` (ver
        # `rc_certidao_quadro`), e por isso vem DEPOIS da serventia: ele so
        # alcanca quem chamar `valores()` sem o bloco da serventia.
        or str(q.get("cargo") or "").strip()
    )
    cargo_de_quem_assina = (
        str(certidao.get("emitida_funcao") or "").strip()
        or str(q.get("cargo") or "").strip()
        or str(sv.get("serventia_titulo") or "").strip()
    )

    # O MODELO DO CNJ DESCREVE CADA GENITOR NUM BLOCO — nome, o municipio de
    # nascimento DELE, a UF e os avos respectivos. Medido na certidao real
    # desta casa (CNS 000000, 12/02/2026, no modelo nacional): o bloco aparece
    # duas vezes, uma por genitor.
    #
    # **`rc_certidao_quadro` JA MONTAVA ISSO, e o molde jogava fora**: usava
    # `@nomefiliacao1 e @nomefiliacao2` numa linha so, e com isso **o municipio
    # de nascimento de cada genitor nao chegava ao papel** — dado que o assento
    # tem e a certidao do CNJ pede.
    blocos = q.get("genitores") if isinstance(q.get("genitores"), list) else []

    def _genitor(i, campo, vazio=" "):
        if i < len(blocos) and isinstance(blocos[i], dict):
            return str(blocos[i].get(campo) or "").strip() or vazio
        return vazio

    selos = [_valores_do_selo(s) for s in _selos_da_certidao(certidao)]
    s1 = selos[0] if len(selos) > 0 else None
    s2 = selos[1] if len(selos) > 1 else None

    def _slot(s, campo, vazio=" "):
        return s[campo] if s else vazio

    # ------------------------------------------ o casamento e o obito
    #
    # OS CAMPOS SAO OS QUE `rc_certidao` JA ESCREVE, e nao uma lista nova: eles
    # foram medidos nas **145 certidoes reais desta casa** (18 de casamento, 3
    # de obito) e nos requisitos da Lei 6.015/1973. Inventar campo aqui seria
    # inventar conteudo de papel assinado; o que se acrescenta e o MOLDE, e nao
    # o que ele diz.
    conjuges = q.get("conjuges") if isinstance(q.get("conjuges"), list) else []

    def _conj(i: int, campo: str, vazio: str = " ") -> str:
        if i < len(conjuges):
            valor = conjuges[i].get(campo)
            if campo == "dma":
                return " "
            return str(valor or "").strip() or vazio
        return vazio

    def _conj_nasc(i: int) -> str:
        """A data de nascimento do conjuge, do jeito que o quadro a monta."""
        if i >= len(conjuges):
            return " "
        d = conjuges[i].get("dma") or {}
        pedacos = [str(d.get(k) or "").strip() for k in ("dia", "mes", "ano")]
        return "/".join(x for x in pedacos if x) or " "

    def _conj_nasc_parte(i: int, parte: str) -> str:
        """Dia, mes ou ano da data de nascimento do conjuge, separados —
        o Anexo V do Provimento CNJ 182/2024 pede caixas de Dia/Mes/Ano, e
        nao a data por extenso. Achado em 09/09/2026 ao medir o molde de
        casamento contra o Anexo V: so existia a versao junta."""
        if i >= len(conjuges):
            return " "
        d = conjuges[i].get("dma") or {}
        return str(d.get(parte) or "").strip() or " "

    def _conj_lugar(i: int) -> str:
        if i >= len(conjuges):
            return " "
        return _cidade_uf(conjuges[i].get("naturalidade"),
                          conjuges[i].get("naturalidade_uf")) or " "

    def _conj_lugar_parte(i: int, campo: str) -> str:
        """Cidade ou UF da naturalidade do conjuge, separadas — mesmo motivo
        de `_conj_nasc_parte`: o Anexo V tem uma caixa para o municipio e
        outra, menor, so para a UF."""
        if i >= len(conjuges):
            return " "
        return str(conjuges[i].get(campo) or "").strip() or " "

    nomes_conjuges = " e ".join(
        _conj(i, "nome_habilitacao", "") for i in (0, 1)
        if _conj(i, "nome_habilitacao", ""))
    nomes_pos = " e ".join(
        _conj(i, "nome_pos", "") for i in (0, 1) if _conj(i, "nome_pos", ""))

    lugar_obito = ", ".join(x for x in (
        str(q.get("local_falecimento") or "").strip(),
        _cidade_uf(q.get("municipio_falecimento"),
                   q.get("municipio_falecimento_uf"))) if x)
    atestou = " — ".join(x for x in (str(q.get("medico") or "").strip(),
                                     str(q.get("crm") or "").strip()) if x)
    sepultado = ", ".join(x for x in (
        str(q.get("sepultamento") or "").strip(),
        str(q.get("sepultamento_mun") or "").strip()) if x)
    dma_nasc = q.get("dma_nascimento") or {}
    nasc_falecido = "/".join(x for x in (
        str(dma_nasc.get("dia") or "").strip(),
        str(dma_nasc.get("mes") or "").strip(),
        str(dma_nasc.get("ano") or "").strip()) if x)

    return {
        "@nomenascido": _up(q.get("nome")),

        # --- CASAMENTO ---
        "@nomesconjuges": _up(nomes_conjuges),
        "@datacelebracaoextenso": _up(q.get("data_fato_extenso")),
        "@regimebens": _txt(q.get("regime")),
        "@nomespos": _up(nomes_pos),
        "@conj1_nome": _up(_conj(0, "nome_habilitacao")),
        "@conj1_datanascimento": _conj_nasc(0),
        "@conj1_dia": _conj_nasc_parte(0, "dia"),
        "@conj1_mes": _conj_nasc_parte(0, "mes"),
        "@conj1_ano": _conj_nasc_parte(0, "ano"),
        "@conj1_naturalidade": _conj_lugar(0),
        "@conj1_naturalidade_cidade": _conj_lugar_parte(0, "naturalidade"),
        "@conj1_naturalidade_uf": _conj_lugar_parte(0, "naturalidade_uf"),
        "@conj1_nacionalidade": _conj(0, "nacionalidade"),
        "@conj1_estadocivil": _conj(0, "estado_civil"),
        "@conj1_filiacao": _conj(0, "genitores"),
        "@conj1_cpf": _conj(0, "cpf"),
        "@conj1_nomepos": _up(_conj(0, "nome_pos")),
        "@conj2_nome": _up(_conj(1, "nome_habilitacao")),
        "@conj2_datanascimento": _conj_nasc(1),
        "@conj2_dia": _conj_nasc_parte(1, "dia"),
        "@conj2_mes": _conj_nasc_parte(1, "mes"),
        "@conj2_ano": _conj_nasc_parte(1, "ano"),
        "@conj2_naturalidade": _conj_lugar(1),
        "@conj2_naturalidade_cidade": _conj_lugar_parte(1, "naturalidade"),
        "@conj2_naturalidade_uf": _conj_lugar_parte(1, "naturalidade_uf"),
        "@conj2_nacionalidade": _conj(1, "nacionalidade"),
        "@conj2_estadocivil": _conj(1, "estado_civil"),
        "@conj2_filiacao": _conj(1, "genitores"),
        "@conj2_cpf": _conj(1, "cpf"),
        "@conj2_nomepos": _up(_conj(1, "nome_pos")),

        # --- OBITO ---
        "@nomefalecido": _up(q.get("nome")),
        "@dataobitoextenso": _up(q.get("data_fato_extenso")),
        "@horaobito": _txt(q.get("hora")),
        "@sexofalecido": _txt(q.get("sexo")),
        "@idadefalecido": _txt(q.get("idade")),
        "@datanascimentofalecido": nasc_falecido or " ",
        "@estadocivilfalecido": _txt(q.get("estado_civil")),
        "@conjugefalecido": _txt(q.get("conjuge")),
        "@naturalidadefalecido": _cidade_uf(q.get("naturalidade"),
                                            q.get("naturalidade_uf")) or " ",
        "@localobito": lugar_obito or " ",
        "@causamorte": _txt(q.get("causa")),
        "@atestouobito": atestou or " ",
        "@filiacaofalecido": _txt(q.get("genitores")),
        "@declarantefalecido": _txt(q.get("declarante")),
        "@sepultamento": sepultado or " ",
        # **O ANEXO VI SEPARA O QUE OS QUATRO MARCADORES ACIMA JUNTAM** —
        # 10/09/2026. Ele da uma caixa ao local, outra ao municipio e outra,
        # menor, a UF; e uma ao medico e outra ao numero do documento dele.
        # Juntos, saiam «HOSPITAL X, IMPERATRIZ/MA» e «DR. PAULO — CRM/MA
        # 12345» num campo so.
        #
        # **O QUADRO JA TRAZIA TODOS SEPARADOS** (`_quadro_obito`), e o molde
        # jogava fora — a mesma coisa que acontecia com o municipio de
        # nascimento de cada genitor no de nascimento. Os quatro juntos ficam
        # no vocabulario: o oficial edita o molde, e quem repuser a caixa
        # unica continua com o marcador que a monta.
        "@localfalecimento": _txt(q.get("local_falecimento")),
        "@municipio_falecimento": _txt(q.get("municipio_falecimento")),
        "@uf_falecimento": _txt(q.get("municipio_falecimento_uf")),
        "@municipio_naturalidade": _txt(q.get("naturalidade")),
        "@uf_naturalidade": _txt(q.get("naturalidade_uf")),
        "@medicoobito": _txt(q.get("medico")),
        "@crmobito": _txt(q.get("crm")),
        "@localsepultamento": _txt(q.get("sepultamento")),
        "@municipio_sepultamento": _txt(q.get("sepultamento_mun")),
        "@uf_sepultamento": _txt(q.get("sepultamento_uf")),
        # As caixas de Dia/Mes/Ano do Anexo VI — duas datas as pedem: a do
        # falecimento e a de nascimento do falecido. E a de REGISTRO, que o
        # molde de obito nao tinha em campo nenhum, usa os marcadores que
        # nasceram no casamento (`@diaregistro` e companhia).
        "@diaobito": str(dma.get("dia") or "").strip() or " ",
        "@mesobito": str(dma.get("mes") or "").strip() or " ",
        "@anoobito": str(dma.get("ano") or "").strip() or " ",
        "@dianascfalecido": str(dma_nasc.get("dia") or "").strip() or " ",
        "@mesnascfalecido": str(dma_nasc.get("mes") or "").strip() or " ",
        "@anonascfalecido": str(dma_nasc.get("ano") or "").strip() or " ",
        "@deixoubens": _txt(q.get("bens")),
        "@deixoufilhos": _txt(q.get("filhos")),
        # --- NATIMORTO E LIVRO E (LD01) ---
        "@numerodo": _txt(q.get("numero_do")),
        "@titulolivroe": _up(q.get("titulo_livro_e") or "CERTIDÃO"),
        "@livroe_especie": _txt(q.get("livro_e_especie")),
        "@livroe_titulo": _txt(q.get("livro_e_titulo")),
        "@livroe_indicacoes": _txt(q.get("livro_e_indicacoes")),
        # **CINCO MARCADORES MEUS NOMEAVAM CAMPO QUE O QUADRO NAO TEM** —
        # `profissao`, `cor_raca`, `domicilio`, `numero_do` e `eleitor`.
        # Escritos assim, o molde traria rotulo que nunca preenche, e rotulo
        # sem valor num papel assinado e ruido — a mesma regra da linha do
        # selo. Conferido em `rc_certidao_quadro._quadro_obito`, que devolve
        # `bens`, `filhos` e `declarante` no lugar deles.
        #
        # A certidao de OBITO em texto (`rc_certidao`) escreve profissao, cor
        # e domicilio porque os le direto das pessoas; o quadro do MOLDE ainda
        # nao os traz. Quando trouxer, entram aqui e no papel.

        # --- comuns as tres, com nome proprio de cada molde ---
        "@matriculacasamento": str(q.get("matricula") or "").strip() or " ",
        "@matriculaobito": str(q.get("matricula") or "").strip() or " ",
        "@cpffalecido": str(q.get("cpf") or "").strip() or " ",
        "@cpfnascido": str(q.get("cpf") or "").strip() or " ",
        "@matriculanascido": str(q.get("matricula") or "").strip() or " ",
        "@datanascimentoextensoCN": _up(q.get("data_fato_extenso")),
        "@dianascimento": str((dma.get("dia") or "")).strip() or " ",
        "@mesnascimento": str((dma.get("mes") or "")).strip() or " ",
        "@anonascimento": str((dma.get("ano") or "")).strip() or " ",
        "@horanascimento": str(q.get("hora") or "").strip() or " ",
        "@naturalidade": _cidade_uf(q.get("naturalidade"),
                                    q.get("naturalidade_uf")) or " ",
        # O ANEXO IV DA UMA CAIXA AO MUNICIPIO E OUTRA, MENOR, A UF — nas
        # duas linhas: a da naturalidade e a do local de nascimento. Juntos
        # num campo so eles saiam «IMPERATRIZ/MA», que e a repeticao que o
        # oficial mandou tirar do rodape, aqui dentro da caixa.
        "@naturalidade_cidade": str(q.get("naturalidade") or "").strip() or " ",
        "@naturalidade_uf": str(q.get("naturalidade_uf") or "").strip() or " ",
        "@sexonascido": _up(q.get("sexo")),
        "@municipio_registro_nascimento": str(
            q.get("municipio_registro") or "").strip() or " ",
        "@nomelocalnascimento": local_cheio or " ",
        "@local_nascimento": local or " ",
        "@municipio_nascimento": str(
            q.get("municipio_nascimento") or "").strip() or " ",
        "@uf_nascimento": str(
            q.get("municipio_nascimento_uf") or "").strip() or " ",
        "@nomefiliacao1": nome_mae or " ",
        "@nomefiliacao2": nome_pai or " ",
        "@avosfiliacao1": str(q.get("avos_paternos") or "").strip() or " ",
        "@avosfiliacao2": str(q.get("avos_maternos") or "").strip() or " ",
        # Um bloco por genitor, na ordem do quadro: mae e depois pai.
        "@genitor1_nome": _genitor(0, "nome"),
        "@genitor1_municipio": _genitor(0, "municipio"),
        "@genitor1_uf": _genitor(0, "uf"),
        "@genitor1_avos": _genitor(0, "avos"),
        "@genitor2_nome": _genitor(1, "nome"),
        "@genitor2_municipio": _genitor(1, "municipio"),
        "@genitor2_uf": _genitor(1, "uf"),
        "@genitor2_avos": _genitor(1, "avos"),
        "@possuigemeos": "SIM" if gemeo else "NÃO",
        "@nomegemeos": (gemeo if gemeo and gemeo.upper() not in ("SIM", "S")
                        else "---------------------------------------------"),
        "@DATAREGISTROEXTENSOSN": _up(q.get("data_registro_extenso")),
        # As caixas de Dia/Mes/Ano do Anexo V — a mesma razao de
        # `_conj_nasc_parte`: so existia a data de registro por extenso.
        "@diaregistro": str((dma_reg.get("dia") or "")).strip() or " ",
        "@mesregistro": str((dma_reg.get("mes") or "")).strip() or " ",
        "@anoregistro": str((dma_reg.get("ano") or "")).strip() or " ",
        "@declaracaonascidovivo": str(q.get("dnv") or "").strip() or "**********",
        "@averbacoes": averb,
        "@anotacoes_cadastro": cadastro,
        "@dataatual": str(q.get("data_comercial") or "").strip() or " ",
        # Rodapé (pedido oficial 08/09/2026): titular na linha de cargo;
        # quem imprime em @escrevente (sem rotulo); linha de assinatura
        # própria para a assinatura do usuário da impressão.
        "@registrador": titular or " ",
        # A FUNCAO DO REGISTRADOR E A DELE — ver a nota acima de
        # `cargo_do_titular`. Quem assina a via leva `@funcaoescrevente`.
        "@funcaoregistrador": cargo_do_titular or " ",
        "@escrevente": escrevente or " ",
        "@funcaoescrevente": cargo_de_quem_assina or " ",
        "@titular_serventia": titular or " ",
        "@linha_assinatura": "",  # sem rotulo acima do nome — 09/09/2026
        "@unit_name": _txt(sv.get("unit_name") or q.get("casa")),
        "@ri_cidade": _txt(sv.get("ri_cidade") or q.get("cidade")),
        "@ri_uf": _txt(sv.get("ri_uf") or q.get("uf")),
        "@cidade_uf": _txt(sv.get("cidade_uf") or _cidade_uf(
            sv.get("ri_cidade") or q.get("cidade"),
            sv.get("ri_uf") or q.get("uf"))),
        "@serventia_endereco": _txt(sv.get("serventia_endereco") or q.get("rua")),
        "@serventia_cep": _txt(sv.get("serventia_cep") or q.get("cep")),
        "@serventia_email": _txt(sv.get("serventia_email") or q.get("email")),
        "@serventia_telefone": _txt(sv.get("serventia_telefone") or q.get("telefone")),
        "@ri_cns": _txt(sv.get("ri_cns") or q.get("cns")),
        "@serventia_cnpj": _txt(sv.get("serventia_cnpj")),
        "@ri_substituta": _txt(sv.get("ri_substituta")),
        "@total": _soma(selos, "_total_n"),
        "@emol": _soma(selos, "_emol_n"),
        "@ferc": _soma(selos, "_ferc_n"),
        "@fadep": _soma(selos, "_fadep_n"),
        "@femp": _soma(selos, "_femp_n"),
        # FERRFIS ESTAVA FALTANDO NA LINHA DE VALORES, e a certidao real desta
        # casa o traz: «FEMP R$ 2,93 FERRFIS R$ 0,73». Medido no acervo, ele
        # aparece em 4 dos 39 textos de selo — raro, e real.
        "@ferrfis": _soma(selos, "_ferrfis_n"),
        "@selo1": _slot(s1, "numero"),
        "@selo1_detalhe": _slot(s1, "detalhe"),
        # As tres linhas do carimbo aprovado em 17/09/2026. `detalhe` fica no
        # vocabulario porque o molde e do oficial: reposto por ele amanha, ele
        # imprime o que sempre imprimiu, em vez de sair `@selo1_detalhe`
        # escrito numa certidao assinada.
        "@selo1_ato": _slot(s1, "ato"),
        "@selo1_requerente": _slot(s1, "requerente"),
        "@selo1_consulta": _slot(s1, "consulta"),
        "@selo1_total": _slot(s1, "total"),
        "@selo1_emol": _slot(s1, "emol"),
        "@selo1_ferc": _slot(s1, "ferc"),
        "@selo1_fadep": _slot(s1, "fadep"),
        "@selo1_femp": _slot(s1, "femp"),
        "@selo1_ferrfis": _slot(s1, "ferrfis"),
        # O que o molde usa hoje: uma linha só, montada do que o selo traz.
        "@selo1_valores": _slot(s1, "valores"),
        "@selo2": _slot(s2, "numero"),
        "@selo2_detalhe": _slot(s2, "detalhe"),
        "@selo2_ato": _slot(s2, "ato"),
        "@selo2_requerente": _slot(s2, "requerente"),
        "@selo2_consulta": _slot(s2, "consulta"),
        "@selo2_total": _slot(s2, "total"),
        "@selo2_emol": _slot(s2, "emol"),
        "@selo2_ferc": _slot(s2, "ferc"),
        "@selo2_fadep": _slot(s2, "fadep"),
        "@selo2_femp": _slot(s2, "femp"),
        "@selo2_ferrfis": _slot(s2, "ferrfis"),
        "@selo2_valores": _slot(s2, "valores"),
    }


def _escapa_valores(vals: dict[str, str]) -> dict[str, str]:
    out = {}
    for k, v in vals.items():
        if k.startswith("@"):
            out[k] = escape(str(v))
        else:
            out[k] = v
    return out


def _png_do_qr(selo: str) -> bytes | None:
    """PNG do QR do selo. Vazio se a casa não tiver segno — o ODT sai mesmo assim."""
    selo = (selo or "").strip()
    if not selo or selo == " ":
        return None
    try:
        import segno
        import notas_selo as NSELO
    except ImportError:
        return None
    texto = NSELO.conteudo(NSELO.MODELO_PADRAO, selo)
    if not texto:
        return None
    try:
        qr = segno.make(texto, error="m")
        buf = BytesIO()
        qr.save(buf, kind="png", scale=6, border=0)
        return buf.getvalue() or None
    except Exception:
        return None


def _celulas_por_caixa(celulas: list[str], vagas: int) -> int:
    """Quantas células o molde gasta por selo. Medido no próprio molde."""
    return len(celulas) // vagas if vagas else len(celulas)


def caixas_do_selo(xml: str, quantos: int) -> str:
    """Deixa no papel **tantas caixas quantos selos a certidão usou**.

    Ordem do oficial em 01/09/2026: *«controle para sair quantas caixas quanto
    os selos utilizados, ali tem duas sempre, permanentes»*.

    **AS DUAS CAIXAS ESTAVAM DESENHADAS NO MOLDE**, e por isso saíam sempre —
    com um selo, que é o caso normal desta casa (medido: a única certidão da
    produção tem um), o papel mostrava uma caixa preenchida e outra vazia, com
    a palavra «Selo:» e nada depois. Caixa vazia num papel assinado parece
    campo que ninguém preencheu.

    COMO ELA MEXE NO MOLDE, E POR QUE ANTES DA TROCA DOS `@`
        A tabela dos selos é **uma linha com duas células por selo** — o texto
        e o QR —, e o que a identifica é o marcador `@selo1`. Depois da troca
        ele já não existe: **podar tem de vir antes**.

    A BORDA SE FECHA NA ÚLTIMA CÉLULA QUE FICA
        As bordas pontilhadas do molde estão repartidas: a primeira célula tem
        a da esquerda e a última tem a da direita. Cortando as de trás sem
        mais nada, **a caixa ficaria aberta do lado direito**. A última que
        sobra herda o estilo da última original, que é onde aquela borda mora.
    """
    quantos = max(quantos, 0)
    i = xml.find("@selo1")
    if i < 0:
        return xml
    ini = xml.rfind("<table:table ", 0, i)
    if ini < 0:
        return xml
    fim = xml.find("</table:table>", i)
    if fim < 0:
        return xml
    fim += len("</table:table>")
    tabela = xml[ini:fim]

    vagas = sum(1 for n in range(1, 9) if f"@selo{n}" in tabela)
    celulas = re.findall(
        r"<table:table-cell[ >].*?</table:table-cell>", tabela, re.DOTALL)
    if not vagas or not celulas:
        return xml
    if quantos >= vagas:
        return xml
    if quantos == 0:
        # SEM SELO NÃO HÁ CAIXA. O ato sem selo existe nesta casa (ele aparece
        # em `atos_sem_selo`), e uma caixa vazia afirmaria menos que o
        # silêncio: o papel simplesmente não traz o quadro.
        return xml[:ini] + xml[fim:]

    por_caixa = _celulas_por_caixa(celulas, vagas)
    ficam = celulas[:quantos * por_caixa]
    estilo_final = re.search(r'table:style-name="([^"]+)"', celulas[-1])
    if estilo_final and ficam:
        ficam[-1] = re.sub(r'table:style-name="[^"]+"',
                           f'table:style-name="{estilo_final.group(1)}"',
                           ficam[-1], count=1)
    novo = tabela
    for fora in celulas[len(ficam):]:
        novo = novo.replace(fora, "", 1)
    novo = novo.replace(celulas[len(ficam) - 1], ficam[-1], 1)
    # A tabela declara uma coluna por célula; sobrando declaração, o
    # LibreOffice desenha coluna vazia depois do que ficou.
    colunas = re.findall(r"<table:table-column[ >][^>]*/>", novo)
    for sobra in colunas[len(ficam):]:
        novo = novo.replace(sobra, "", 1)
    return xml[:ini] + novo + xml[fim:]


def arquivo_da_certidao(quadro: dict, certidao: dict, sv: dict,
                        molde_bytes: bytes | None = None) -> bytes:
    """Cópia do molde ODT, com os @ trocados.

    **RECUSA A ESPÉCIE QUE O MOLDE NÃO SERVE**, em vez de imprimir o papel
    errado — ver `ESPECIES_QUE_O_MOLDE_SERVE`.

    `molde_bytes` é o papel AJUSTADO pela casa, quando há um (`mo_moldes`, ver
    `modelos_moldes.py`). Sem ele, vale o `.odt` do pacote — **o código é o
    piso; a tabela é o ajuste**, a mesma regra dos modelos de texto. Ele entra
    por parâmetro e não por consulta aqui dentro porque **esta função não abre
    banco**: quem tem a conexão é a rota, e um `db.connect()` no meio da
    montagem do papel poria uma leitura de banco dentro de quem só desenha.
    """
    especie = str((quadro or {}).get("especie") or "").strip().upper()
    if especie and especie not in ESPECIES_QUE_O_MOLDE_SERVE:
        raise MoldeError(
            f"Esta casa tem molde de certidão para nascimento, casamento, "
            f"óbito, natimorto e as espécies do Livro E, e esta é de "
            f"{especie}: no molde de outra espécie sairia "
            f"um papel com o cabeçalho errado e com campos que não existem "
            f"neste assento. O teor está na ficha da certidão e pode ser "
            f"conferido ali; o molde desta espécie ainda não foi construído.")
    if molde_bytes:
        molde = BytesIO(molde_bytes)
    else:
        molde = molde_da_especie(especie)
        if not molde.exists():
            raise FileNotFoundError(f"molde da certidão ausente: {molde}")
    vals = _escapa_valores(valores(quadro, certidao, sv))
    chaves = sorted(vals, key=len, reverse=True)
    qr = {
        _QR_SELO1: _png_do_qr(vals.get("@selo1", "")),
        _QR_SELO2: _png_do_qr(vals.get("@selo2", "")),
    }
    buf = BytesIO()
    with zipfile.ZipFile(molde) as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith(".xml"):
                texto = data.decode("utf-8")
                if item.filename == "content.xml":
                    texto = caixas_do_selo(texto, len(_selos_da_certidao(certidao)))
                for chave in chaves:
                    texto = texto.replace(chave, vals[chave])
                data = texto.encode("utf-8")
            elif item.filename in qr and qr[item.filename]:
                data = qr[item.filename]
            info = zipfile.ZipInfo(filename=item.filename, date_time=item.date_time)
            info.compress_type = (
                zipfile.ZIP_STORED if item.filename == "mimetype"
                else zipfile.ZIP_DEFLATED)
            zout.writestr(info, data)
    return buf.getvalue()


# compat: a rota antiga montava HTML; o nome ficou
def html_odt_da_certidao(quadro, certidao, sv) -> str:
    return ""
