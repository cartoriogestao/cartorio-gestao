"""O PAPEL DA NOTIFICAÇÃO DO CONFRONTANTE — retificação de área e
georreferenciamento.

    «faça ser possível imprimir as notificações da usucapião e da
     georreferenciamento em pdf»            — o oficial, 21/09/2026

**AQUI NÃO HAVIA PAPEL NENHUM, e é essa a diferença para a usucapião.** Lá
`us_notificacao.montar` compõe o teor e o movimento o congela desde sempre; na
retificação o sistema **registrava que notificou** — `notificado_em`, `forma`,
`prazo_ate` — e o texto entregue ao confrontante era escrito fora do sistema,
à mão. Medido em 21/09/2026: `rt_confrontantes` não tinha uma coluna de teor, e
`retificacao.notificar` não recebia nem devolvia texto.

    Registro de que se notificou, sem o papel que sustenta a notificação, é
    uma linha dizendo que a serventia notificou alguém — e a prova do que foi
    dito não existe em lugar nenhum. É a mesma régua que a usucapião já seguia.

**O TEOR SAI DA NORMA, E CADA FRASE LEVA O ARTIGO.** As regras estão medidas no
Código de Normas do TJMA (`rt_tjma`), lido do PDF que está na casa:

  * **art. 598** — quem se notifica, e as quatro formas, nesta ordem;
  * **art. 598, § 1º** — onde se notifica;
  * **art. 599** — quinze dias ÚTEIS para impugnar, contados
    **individualmente** do recebimento;
  * **art. 599, § 1º** — *o silêncio presume a anuência*, e é por isso que ele
    tem de estar escrito no papel: quem não responde precisa saber, antes, o
    que o seu silêncio vale;
  * **art. 599, § 3º** — a impugnação fora do prazo, mas **antes da
    averbação**, ainda é recebida. Calar isso faria o papel afirmar um prazo
    mais duro que o da norma.

**ESTE MÓDULO SÓ MONTA TEXTO.** Não grava, não notifica, não conta prazo e não
decide nada — quem conta dia útil é o núcleo, que conhece os feriados desta
comarca, e quem decide é quem assina. Há teste que varre os nomes públicos.

**O TEXTO NÃO MORA MAIS AQUI — LF06G, 19/10/2026.** O papel inteiro e cada
frase que o processo decide (a divisa, a planta, o prazo, o silêncio) foram
para `modelos_padrao/retificacao/`, com os mesmos bytes: o papel é
`RT_NOTIFICACAO_CONFRONTANTE.txt`, e as frases são as peças dele
(`RT_NOTIFICACAO_CONFRONTANTE__divisa.txt`…). **A REGRA ficou** — qual frase
entra, com que dado, em que ordem —, e é ela que este módulo guarda.
"""
from __future__ import annotations

from typing import Any

import cpf_cnpj as CPFDOC
import modelos_da_casa as _MODELOS
import rt_tjma as NORMA


class NotificacaoError(ValueError):
    """Impedimento de regra, com frase pronta para o balcão."""


# O PRAZO QUE O PAPEL ANUNCIA É O DE IMPUGNAR (art. 599), e não o de
# «manifestar-se» do art. 598: é o da impugnação que corre individualmente e é
# ele que o silêncio consome.
PRAZO_DO_PAPEL = "IMPUGNAR"

# `MODELO` — o texto de fábrica do papel RT_NOTIFICACAO_CONFRONTANTE — saiu
# daqui no LF06G (19/10/2026): mora em
# `modelos_padrao/retificacao/RT_NOTIFICACAO_CONFRONTANTE.txt`, com os mesmos
# bytes, e chega pela busca única (`modelos_da_casa.texto_do_papel`): o ajuste
# da casa, se houver, e senão o padrão da base. O nome antigo continua
# respondendo — ver `__getattr__` no fim deste módulo.
PAPEL = "RT_NOTIFICACAO_CONFRONTANTE"

# OS CLAROS QUE `montar` PREENCHE, e é contra eles que a tela confere o ajuste
# da casa (`conferir_modelo`). Claro fora desta lista estouraria na hora de
# notificar — com o confrontante esperando o papel.
CLAROS: tuple[str, ...] = (
    "serventia", "numero", "do_ano", "sobre_matricula", "nome", "qualidade",
    "endereco", "requerente", "imovel", "sobre_a_planta", "prazo_texto",
    "silencio", "silencio_artigo", "atrasada_artigo", "lugar_e_data",
    "oficial", "cargo")


def _texto(v: Any) -> str:
    return str(v or "").strip()


def _modelo(con, chave: str) -> str:
    """O texto que vale hoje para o papel ou a peça. Só lê.

    Com `con`, a busca única — o ajuste da casa e, sem ele, o padrão da base.
    Sem `con` (quem monta fora de uma rota, um teste), o padrão da base. O
    papel que não carregou vira a recusa deste módulo, com a frase do
    `modelos_da_casa` dizendo qual arquivo faltou.
    """
    try:
        return (_MODELOS.texto_do_papel(con, chave) if con is not None
                else _MODELOS.padrao_de(chave))
    except _MODELOS.ModeloError as erro:
        raise NotificacaoError(str(erro)) from erro


def _peca(con, peca: str, **valores: Any) -> str:
    """Uma frase do papel, preenchida — `RT_NOTIFICACAO_CONFRONTANTE__<peca>`."""
    chave = f"{PAPEL}__{peca}"
    try:
        return _MODELOS.preencher(chave, _modelo(con, chave), valores)
    except _MODELOS.ModeloError as erro:
        raise NotificacaoError(str(erro)) from erro


def conferir_modelo(texto: str) -> str:
    """O ajuste da casa serve como notificação? Devolve o erro, ou ``""``.

    É a régua que a tela de Modelos usa para gravar e a que `montar` usa para
    preencher — conferir com uma e emitir com outra é como a tela passa a
    aprovar o papel que a notificação não sabe montar.
    """
    return _MODELOS.conferir_claros(texto, CLAROS)


def _por_extenso(n: int) -> str:
    """Quinze vira «quinze». Só os números que os prazos desta seção usam."""
    nomes = {5: "cinco", 10: "dez", 15: "quinze", 30: "trinta"}
    return nomes.get(int(n), str(int(n)))


def _documento(valor: Any) -> str:
    """«CPF 000.000.000-00» ou «CNPJ 00.000.000/0000-00», formatado pelo
    `cpf_cnpj`, que é o que o balcão usa.

    O tipo sai do tamanho — 11 dígitos é CPF, 14 é CNPJ. O campo da tela é
    «Documento», livre: fora desses tamanhos o número sai como foi escrito,
    com o rótulo «documento», porque chamar de CPF o que não tem tamanho de
    CPF seria o papel afirmando o que não sabe.
    """
    texto = _texto(valor)
    if not texto:
        return ""
    tipo = {11: "CPF", 14: "CNPJ"}.get(len(CPFDOC.so_digitos(texto)),
                                       "documento")
    return f"{tipo} {CPFDOC.formatar_documento(texto)}"


def _quem_faz_a_divisa(confrontante: dict, con=None) -> str:
    """O que vem depois de «Divisa que toca o imóvel de V. S.ª:» — quem é o
    confrontante e qual imóvel dele faz a divisa. Vazio, a linha não sai.

    **ANTES SAÍA «1».** `divisa_afetada` é a marca SIM/NÃO do art. 596
    (`rt_schema`, INTEGER 0/1), e não a descrição da divisa; a linha copiava a
    marca, e o papel dizia «Divisa que toca o imóvel de V. S.ª: 1». O oficial
    decidiu que a frase fica — é o padrão das intimações — e que depois dos
    dois-pontos vêm os dados do confrontante, só os que existirem.

    **O ENDEREÇO NÃO ENTRA:** o do art. 598, § 1º pode ser a residência, e não
    o imóvel que faz a divisa. **A SERVENTIA SÓ ENTRA COM A MATRÍCULA:** «do
    Registro de Imóveis de …» diz onde a matrícula está; sozinha, depois de uma
    vírgula, ela não diz qual imóvel é.

    As duas formas da matrícula são peças do papel (`__divisa_matricula` e
    `__divisa_matricula_serventia`); a regra de qual sai fica aqui.
    """
    if not confrontante.get("divisa_afetada"):
        return ""
    dados = [_texto(confrontante.get("nome")),
             _documento(confrontante.get("documento"))]
    matricula = _texto(confrontante.get("matricula_contigua"))
    if matricula:
        serventia = _texto(confrontante.get("serventia_contigua"))
        dados.append(
            _peca(con, "divisa_matricula_serventia", matricula=matricula,
                  serventia=serventia) if serventia
            else _peca(con, "divisa_matricula", matricula=matricula))
    return ", ".join(x for x in dados if x)


def prazo_para_impugnar() -> dict:
    """O prazo que o papel anuncia, lido da norma — e não escrito aqui."""
    return NORMA.prazo(PRAZO_DO_PAPEL)


def conferir(*, processo: dict, confrontante: dict) -> list[str]:
    """O que falta para o papel poder sair. SÓ LÊ — devolve as faltas.

    **A CONFERÊNCIA VEM ANTES DE O MOVIMENTO EXISTIR**, como na usucapião:
    notificação registrada sem papel que a sustente é pior que notificação
    nenhuma, porque ela consome o prazo de alguém que não foi avisado.
    """
    faltas = []
    if not _texto(confrontante.get("nome")):
        faltas.append("o nome do confrontante")
    if not _texto(confrontante.get("endereco")):
        faltas.append(
            "o endereço do confrontante — art. 598, § 1º: o indicado pelo "
            "requerente, o que consta da matrícula contígua, ou o do próprio "
            "imóvel que faz divisa")
    if not _texto(processo.get("numero")):
        faltas.append("o número do processo")
    if not _texto(processo.get("requerente_nome")):
        faltas.append("o requerente")
    return faltas


def montar(*, processo: dict, confrontante: dict, serventia: dict,
           hoje_extenso: str = "", con=None) -> str:
    """O teor da notificação do confrontante. SÓ MONTA — não grava nada.

    O texto que sair daqui é **congelado** pelo movimento que o expede: o que
    o confrontante leu é o de então, e remontá-lo depois traria o processo
    como ele está hoje. Mesma regra do termo do Registro Civil, da certidão do
    Protesto e da notificação da usucapião.

    **COM `con`, O AJUSTE DA CASA VALE** (LF06G): o papel e as frases saem da
    busca única. O ajuste novo vale para a PRÓXIMA notificação; a que já saiu
    continua congelada como foi entregue.
    """
    faltas = conferir(processo=processo, confrontante=confrontante)
    if faltas:
        raise NotificacaoError(
            "A notificação não sai sem: " + "; ".join(faltas) + ".")

    p = prazo_para_impugnar()
    dias = int(p["dias"])
    prazo_texto = _peca(con, "prazo_uteis" if p.get("uteis") else "prazo_corridos",
                        dias=dias, extenso=_por_extenso(dias))

    partes: list[str] = []
    for peca, chave in (("imovel_matricula", "matricula_numero"),
                        ("imovel_area_na_matricula", "area_na_matricula"),
                        ("imovel_area_pretendida", "area_pretendida"),
                        ("imovel_perimetro", "perimetro")):
        if _texto(processo.get(chave)):
            partes.append(_peca(con, peca, valor=_texto(processo[chave])))
    divisa = _quem_faz_a_divisa(confrontante, con=con)
    if divisa:
        partes.append(_peca(con, "divisa", quem=divisa))
    #  COM A DIVISA, A MATRICULA JA SAIU NELA — e a linha de baixo a repetiria.
    #  Sem divisa afetada, a linha de baixo continua saindo como antes.
    contigua = _texto(confrontante.get("matricula_contigua"))
    if contigua and not divisa:
        partes.append(_peca(con, "contigua", matricula=contigua))
    if not partes:
        partes.append(_peca(con, "sem_descricao"))

    profissional = _texto(processo.get("profissional_nome"))
    conselho = _texto(processo.get("profissional_conselho"))
    art = _texto(processo.get("art_numero"))
    sobre_a_planta = ""
    if profissional:
        registro = _texto(processo.get("profissional_registro"))
        credencial = " ".join(x for x in (conselho, registro) if x)
        sobre_a_planta = _peca(
            con, "planta", profissional=profissional,
            credencial=(_peca(con, "planta_credencial", credencial=credencial)
                        if credencial else ""),
            art=_peca(con, "planta_art", art=art) if art else "") + "\n\n"

    #  O ANO SO ENTRA SE O NUMERO NAO O TROUXER — nesta seccao o processo se
    #  numera «9/2026», e repetir daria «9/2026/2026». Na usucapiao e o
    #  contrario (o numero e «2026.001» e o ano vem separado), e por isso a
    #  regra e olhar o numero em vez de copiar o vizinho.
    ano = processo.get("ano")
    numero = _texto(processo.get("numero"))
    if ano and str(ano) in numero:
        ano = None
    matricula = _texto(processo.get("matricula_numero"))
    qualidade = _texto(confrontante.get("papel"))
    valores = {
        "serventia": _texto(serventia.get("nome")),
        "numero": numero,
        "do_ano": f"/{ano}" if ano else "",
        "sobre_matricula": (_peca(con, "sobre_matricula", matricula=matricula)
                            if matricula else ""),
        "nome": _texto(confrontante.get("nome")),
        "qualidade": f", {qualidade.lower()}" if qualidade else "",
        "endereco": _texto(confrontante.get("endereco")),
        "requerente": _texto(processo.get("requerente_nome")),
        "imovel": "\n".join(partes),
        "sobre_a_planta": sobre_a_planta,
        "prazo_texto": prazo_texto,
        # O SILÊNCIO DO PAPEL É PEÇA, E O DA NORMA CONTINUA NA NORMA: a tela
        # das normas mostra `rt_tjma.SILENCIO_VALE_ANUENCIA`, que é a lei; a
        # frase entregue ao confrontante é texto da casa. O artigo vem da norma.
        "silencio": _peca(con, "silencio"),
        "silencio_artigo": _texto(NORMA.SILENCIO_VALE_ANUENCIA["artigo"]),
        "atrasada_artigo": _texto(NORMA.IMPUGNACAO_ATRASADA_ENTRA["artigo"]),
        "lugar_e_data": _texto(hoje_extenso),
        "oficial": _texto(serventia.get("oficial")) or "____________",
        "cargo": _texto(serventia.get("cargo")) or "Oficial",
    }
    try:
        return _MODELOS.preencher(PAPEL, _modelo(con, PAPEL), valores)
    except _MODELOS.ModeloError as erro:
        raise NotificacaoError(str(erro)) from erro


def __getattr__(nome: str):
    """Os nomes antigos do texto de fábrica, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06G (19/10/2026) e mora em `modelos_padrao/`.
    Quem ainda importa o nome antigo recebe o padrão da base — o MESMO que o
    papel imprime, e não uma cópia que ficou para trás. Nome que não é de papel
    continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    return _MODELOS.constante_antiga(__name__, nome)
