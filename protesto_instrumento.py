"""O INSTRUMENTO DE PROTESTO — o papel que a casa entrega ao apresentante.

Nasceu da pergunta do oficial em 01/09/2026: *«onde emitir o instrumento
eletronico do protesto?»* — e a resposta era **em lugar nenhum**. O sistema
lavrava o protesto, escrevia o termo no livro (`protesto_termo`) e parava ali.
O art. 20 da Lei 9.492/1997 manda entregar o instrumento ao apresentante, e
ele nao existia.

**O ACERVO NAO TEM UMA TABELA SEQUER DE INSTRUMENTO** — procurado nas 229 do
E-Oficio, zero com «instrum» no nome. Nao ha, aqui, precedente de forma a
imitar; e por isso **o que se imita e a LEI**, como na habilitacao de
casamento. O texto vai ao catalogo de modelos, e o oficial o edita.

OS DEZ ITENS DO ART. 22, E O QUE O SISTEMA TEM PARA CADA UM
    Lidos na doutrina que esta na casa — Gentil (coord.), *Registros
    Publicos*, Metodo, 2023, cap. 7, **[p. 2587]** —, que enumera os dez do
    art. 22 da Lei 9.492/1997. Cada um esta em `ITENS_DO_ART_22`, com o
    numero do inciso ao lado, e `conferir()` diz quais este titulo preenche.

    **O ITEM II NAO TEM FONTE NESTA CASA, e isto foi medido, nao suposto.**
    Ele pede «nome do apresentante **e endereco**»:

      - o arquivo da CRA, por onde entram 93% dos titulos, traz
        `codigo_do_apresentante` (3) e `nome_do_apresentante` (40) no
        cabecalho, e **nenhuma posicao de endereco**;
      - o acervo do E-Oficio nao tem cadastro de apresentante: `tbCedente`
        tem endereco em 156 de 307 linhas, e e o **cedente** — outro papel,
        que `pt_titulos` ja guarda em `cedente_endereco`.

    Entao o endereco do apresentante **nao se inventa e nao se cala**: ele
    aparece na conferencia como item que falta, com o motivo. Papel que a
    serventia assina omitindo item que a lei exige e defeito que so aparece
    quando alguem o contesta.

    **DESDE O LD08 (21/10/2026) ELE TEM FONTE**, e nao no arquivo: o balcao
    pede o endereco a quem traz o titulo (CN-MA art. 884, I), e o banco que
    manda pela CRA tem o seu no cadastro dos apresentantes (`pt_apresentantes`,
    o mesmo do CNPJ do XML da CENPROT), pelo codigo — um por banco, e nao um
    por titulo. Quem le e `protesto.apresentante_do_titulo`. O que continua
    valendo: sem endereco em nenhum dos dois, o papel diz so o nome, e a
    conferencia mostra o item II em falta.

O § UNICO E UMA DISPENSA CONDICIONAL, E A CONDICAO SE MEDE
    O item III pede a reproducao ou transcricao do documento. O paragrafo
    unico dispensa isso se a serventia conservar copia — «do que se deve
    fazer **mencao expressa** no registro e no instrumento» (Gentil, cap. 7,
    [p. 2594]).

    Sao **duas** obrigacoes, e nao uma: conservar a copia, e dizer que a
    conserva. `protesto_imagens` guarda a imagem do titulo em `attachments`,
    e por isso a condicao **se pergunta ao banco** — nunca se afirma. Sem
    imagem arquivada a dispensa nao vale, e o instrumento tem de transcrever;
    escrever a mencao sem ter a copia seria o «carimbo que mente» num papel
    que vai ao credor.

O TEOR CONGELA, E AQUI A RAZAO E MAIS DURA QUE NO TERMO
    O termo congela porque foi o que se escreveu no livro. **O instrumento
    congela porque vai ser ASSINADO** — a assinatura digital e sobre bytes
    determinados, e teor que se remonta faz a firma deixar de conferir sem
    ninguem ter mexido em nada. Ver `assinatura_digital` e
    `DOCUMENTACAO/ASSINATURA_DIGITAL_A3.md`.

    Por isso, tambem, o instrumento entra na fila de assinatura assim que e
    emitido: `as_documentos`, com `entidade='pt_instrumentos'`.

SEGUNDA VIA E OUTRO INSTRUMENTO, E NAO O MESMO REEMITIDO
    Cada emissao toma o seu numero do exercicio e o seu teor. Reaproveitar a
    linha faria a segunda via sobrescrever o teor que a primeira levou
    assinado — e a firma da primeira passaria a nao conferir.
"""
from __future__ import annotations

CHAVE_NO_CATALOGO = "PT_INSTRUMENTO_PROTESTO"

import hashlib
import json
from typing import Any

from bd_nativo import banco

# A ENTIDADE NA FILA DE ASSINATURA. E o nome da tabela, como manda `as_schema`.
ENTIDADE_DA_ASSINATURA = "pt_instrumentos"

# OS DEZ ITENS DO ART. 22 DA LEI 9.492/1997, na ordem da lei.
#
# `de_onde` diz de que campo do sistema o item sai, e e o que a conferencia
# le. Item sem fonte tem `de_onde=None` e um `porque` que diz o motivo — a
# lista serve para o oficial saber o que falta, e nao so para o programa.
ITENS_DO_ART_22: tuple[dict[str, Any], ...] = (
    {"inciso": "I", "o_que": "data e número de protocolização",
     "de_onde": ("titulo", "protocolo")},
    {"inciso": "II", "o_que": "nome do apresentante e endereço",
     "de_onde": ("apresentante", "endereco"),
     # MEDIDO EM 01/09/2026: o cabeçalho da remessa da CRA tem código (3) e
     # nome (40) do apresentante, e nenhuma posição de endereço. Desde o LD08
     # o endereço vem do título (o balcão o pede) ou do cadastro dos
     # apresentantes, pelo código — `protesto.apresentante_do_titulo`.
     "falta": "endereço do apresentante",
     "porque": ("o arquivo da CRA traz só o código e o nome do apresentante, e "
                "este não tem endereço nem no título nem no cadastro dos "
                "apresentantes — o da CRA se cadastra em Protesto → XML da "
                "CENPROT, «Cadastro dos apresentantes»; o do balcão se informa "
                "ao cadastrar o título")},
    {"inciso": "III",
     "o_que": ("reprodução ou transcrição do documento, ou menção à cópia "
               "arquivada (§ único)"),
     "de_onde": ("imagem", "quantas")},
    {"inciso": "IV", "o_que": "certidão das intimações feitas e das respostas",
     "de_onde": ("intimacao", "data_ato")},
    {"inciso": "V", "o_que": "indicação dos intervenientes voluntários",
     # SO CABE NA LETRA DE CAMBIO — aceite por intervencao, arts. 56 a 58 da
     # LUG. Nao ha campo, e nao ha caso nesta casa; o item fica declarado
     # para quem for procurar nao concluir que foi esquecido.
     "de_onde": None,
     "so_se": "houver aceite por intervenção (letra de câmbio)"},
    {"inciso": "VI", "o_que": "a aquiescência do portador ao aceite por honra",
     "de_onde": None,
     "so_se": "houver aceite por intervenção (letra de câmbio)"},
    {"inciso": "VII",
     "o_que": "nome, número do documento de identificação e endereço do devedor",
     "de_onde": ("devedores", "nome")},
    {"inciso": "VIII", "o_que": "data e assinatura do Tabelião",
     "de_onde": ("assinatura", "fila")},
    {"inciso": "IX", "o_que": "tipo do protesto",
     "de_onde": ("titulo", "tipo_protesto")},
    {"inciso": "X", "o_que": "motivo do protesto",
     "de_onde": ("titulo", "motivo_protesto")},
)

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")

# O TEXTO BASE, MONTADO DOS ITENS DA LEI — e não copiado de outra serventia.
#
# Os seis instrumentos reais que o oficial subiu são de Carira/SE, e o papel
# de lá cita a **Lei estadual 6.310/2007** e o **Selo TJSE**. Vale a regra
# desta casa: **layout, sim; convenção, não.** O que se imita é a forma
# nacional; o que é de lá fica lá.
#
# É `CHAVES` (`{marcador}`, do `str.format`) e não Jinja, pela mesma razão do
# termo: monta-se de frases inteiras, e quem escreve o texto não deveria
# precisar de `{% if %}` para dizer que houve intimação por edital.
#
# O texto-base («O {serventia}, Tabelionato de Protesto de Títulos, DECLARA
# PROTESTADO …») era a constante `TEXTO_BASE`, e saiu daqui no LF06A
# (19/10/2026) junto com o instrumento inteiro — ver `INSTRUMENTO_DE_PROTESTO`.

# A MENÇÃO DO § ÚNICO — e ela só se escreve quando a cópia existe de verdade.
# O TEXTO era a constante `MENCAO_DA_COPIA_ARQUIVADA` e saiu daqui no LF06E
# (19/10/2026), junto com a frase de quando não há cópia, as três certidões da
# intimação e o «desta praça»: moram em `modelos_padrao/protesto/
# PT_INSTRUMENTO_*.txt`, e o oficial os edita na tela de Modelos. QUAL frase
# entra continua decidido aqui (`montar_teor`, `emitir`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

# **TEXTO CORRIDO, SEM CLAROS** — art. 795, § 2º do Código de Normas, a mesma
# regra de `notas_modelos.py`. Até 07/09/2026 as três partes eram separadas
# por `"\n\n"` — linha em branco de propósito —, e isso ia inteiro para o
# papel que o tabelião assina e entrega ao apresentante.
#
# O TEXTO MORA EM `modelos_padrao/protesto/PT_INSTRUMENTO_PROTESTO.txt` desde o
# LF06A (19/10/2026), com os MESMOS bytes de quando era `TEXTO_BASE + "
# {descricao} {copia} {intimacao}"`, e chega pela base dos padrões. O nome
# antigo `INSTRUMENTO_DE_PROTESTO` continua respondendo — ver `__getattr__` no
# fim deste módulo.

# «O DOCUMENTO ABAIXO DESCRITO» NÃO ERA DESCRITO — conferência dos modelos de
# 14/10/2026: o texto dizia isso e nada vinha depois. `{descricao}` é o que o
# Código de Normas do TJMA (Prov. 28/2026), art. 914, manda o registro e o
# instrumento conterem: número de ordem e data do registro, data e número da
# protocolização, apresentante, o título (espécie, número, valor, emissão e
# vencimento), o devedor com documento e endereço, o credor, o tipo e o motivo.
# Montado dos FATOS do ato e do título — nada escrito à mão.


class InstrumentoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _data_br(iso: Any) -> str:
    """`2026-09-01` vira `01/09/2026`. Vazio continua vazio."""
    s = _texto(iso)[:10]
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s


def _por_extenso(iso: Any) -> str:
    """`2026-09-01` vira `1 de setembro de 2026`. Vazio continua vazio."""
    s = _texto(iso)[:10]
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return s
    try:
        ano, mes, dia = int(s[0:4]), int(s[5:7]), int(s[8:10])
    except ValueError:
        return s
    if not 1 <= mes <= 12:
        return s
    return f"{dia} de {MESES[mes - 1]} de {ano}"


def _reais(centavos: Any) -> str:
    """Centavos viram `1.234,56`. O instrumento afirma valor, e valor errado
    num papel assinado é o erro que o credor cobra depois."""
    try:
        n = int(centavos or 0)
    except (TypeError, ValueError):
        return ""
    inteiro, resto = divmod(abs(n), 100)
    corpo = f"{inteiro:,}".replace(",", ".")
    return ("-" if n < 0 else "") + f"{corpo},{resto:02d}"


# ------------------------------------------------------------- os fatos


def dados(con, titulo_id: int) -> dict:
    """Tudo o que o instrumento afirma, lido do que foi lavrado. Só LÊ.

    **O INSTRUMENTO SAI DO ATO, E NÃO DO TÍTULO.** Um título apontado e não
    protestado não tem instrumento — e é `protesto` do PROTESTO que carrega
    livro, folha, número de ordem e a data que o papel declara.
    """
    bd = banco(con)
    titulo = bd.um(
        """SELECT * FROM pt_titulos WHERE id = %s""", (int(titulo_id),))
    if titulo is None:
        raise InstrumentoError(
            f"Não há título com o número interno {titulo_id} neste sistema.")

    tem_livros = bd.tem_tabela("nu_livros")
    livro_sql = ("(SELECT v.numero FROM nu_livros v WHERE v.id = a.livro_id)"
                 if tem_livros else "NULL")
    protesto = bd.um(
        f"""SELECT a.*, {livro_sql} AS livro_numero
             FROM pt_atos a
            WHERE a.titulo_id = %s AND a.tipo = 'PROTESTO' AND a.cancelado = 0
            ORDER BY a.id DESC LIMIT 1""", (int(titulo_id),))

    apontamento = bd.um(
        """SELECT data_ato FROM pt_atos
            WHERE titulo_id = %s AND tipo = 'APONTAMENTO' AND cancelado = 0
            ORDER BY id LIMIT 1""", (int(titulo_id),))

    # A ÚLTIMA INTIMAÇÃO É A QUE CONTA — o aviso não é um por título, e
    # reemitir é rotina. É a mesma regra de `protesto_termo.dados_do_titulo`.
    intimacao = bd.um(
        """SELECT data_ato, detalhe_json FROM pt_atos
            WHERE titulo_id = %s AND tipo = 'INTIMACAO' AND cancelado = 0
            ORDER BY id DESC LIMIT 1""", (int(titulo_id),))
    modo, motivo_nao_entrega, digital = None, None, False
    if intimacao is not None:
        try:
            detalhe = json.loads(intimacao["detalhe_json"] or "{}")
        except (TypeError, ValueError):
            detalhe = {}
        modo = _texto(detalhe.get("modo")).upper() or None
        motivo_nao_entrega = (detalhe.get("motivo_nao_entrega")
                              or detalhe.get("motivo") or None)
        # A MARCA `digital` É A DA INTIMAÇÃO POR MEIO ELETRÔNICO (LD04) — CN-MA
        # art. 919, § 1º, cumprida pela confirmação da plataforma (art. 921,
        # § 6º, II). O modo dela é PESSOAL, e até 21/10/2026 este papel lia só o
        # modo: o termo dizia «por meio eletrônico» e o instrumento do MESMO
        # protesto certificava a entrega em mãos (`PT_INSTRUMENTO_INTIMACAO_
        # ENTREGUE`). A regra é a
        # de `protesto_termo.dados_do_titulo`.
        digital = bool(detalhe.get("digital")) and modo != "EDITAL"

    devedores = bd.ler(
        """SELECT nome, documento_tipo, documento_numero, endereco, bairro,
                  cep, cidade, uf
             FROM pt_devedores WHERE titulo_id = %s ORDER BY id""",
        (int(titulo_id),))

    # O § ÚNICO SE PERGUNTA AO BANCO. `protesto_imagens` guarda a imagem do
    # título na `attachments` da casa; contar aqui evita importar o módulo só
    # para uma contagem — e a entidade é a dele, medida e não escrita.
    copias = bd.um(
        """SELECT COUNT(*) AS c FROM attachments
            WHERE entity_type = 'pt_titulos' AND entity_id = %s""",
        (int(titulo_id),))

    # O APRESENTANTE COM O ENDEREÇO (LD08) — do título ou do cadastro.
    import protesto as PT
    return {"titulo": dict(titulo),
            "apresentante": PT.apresentante_do_titulo(bd, titulo),
            "protesto": dict(protesto) if protesto is not None else None,
            "apontado_em": (apontamento["data_ato"]
                            if apontamento is not None else None),
            "intimacao": ({"data": intimacao["data_ato"], "modo": modo,
                           "motivo_nao_entrega": motivo_nao_entrega,
                           "digital": digital}
                          if intimacao is not None else None),
            "devedores": devedores,
            "copias_arquivadas": int(copias["c"] if copias else 0)}


# ------------------------------------------------------------- conferir


def conferir(con, titulo_id: int) -> dict:
    """Os dez itens do art. 22, um a um: quais este título preenche. Só LÊ.

    **NÃO GRAVA E NÃO RECUSA A EMISSÃO** — quem recusa é `emitir`, e só pelo
    que impede o papel de existir (protesto não lavrado). Item que falta
    aparece aqui, à vista, antes de o oficial assinar: é o momento em que
    ainda dá para consertar.
    """
    d = dados(con, titulo_id)
    t, prot = d["titulo"], d["protesto"]
    achados = []
    for item in ITENS_DO_ART_22:
        de_onde = item.get("de_onde")
        if de_onde is None:
            achados.append({**item, "tem": None,
                            "nota": f"só cabe se {item['so_se']}"})
            continue
        fonte, campo = de_onde
        if fonte == "titulo":
            tem = bool(_texto(t.get(campo)))
        elif fonte == "apresentante":
            # o nome E o campo pedido: o inciso II é «nome e endereço»
            tem = bool(_texto(d["apresentante"].get("nome"))
                       and _texto(d["apresentante"].get(campo)))
        elif fonte == "imagem":
            tem = d["copias_arquivadas"] > 0
        elif fonte == "intimacao":
            tem = d["intimacao"] is not None
        elif fonte == "devedores":
            tem = bool(d["devedores"])
        elif fonte == "assinatura":
            # A ASSINATURA NÃO É DESTE MÓDULO, e dizer que ela existe antes de
            # o papel voltar assinado seria afirmar o que não aconteceu.
            tem = None
        else:  # fonte nova sem tratamento é defeito, não caso (sem cobertura)
            raise InstrumentoError(
                f"O item {item['inciso']} aponta para a fonte {fonte!r}, que "
                f"este módulo não sabe ler.")
        achados.append({**item, "tem": tem})

    faltando = [a for a in achados if a["tem"] is False]
    return {"titulo_id": int(titulo_id),
            "protestado": prot is not None,
            "itens": achados,
            "faltando": faltando,
            "copias_arquivadas": d["copias_arquivadas"],
            "pode_emitir": prot is not None}


def por_que_nao_esta_completo(conferido: dict) -> str:
    """Uma frase para o balcão, juntando os itens que faltam. Só LÊ."""
    partes = []
    for a in conferido.get("faltando") or []:
        falta = a.get("falta") or a["o_que"]
        porque = a.get("porque")
        partes.append(f"art. 22, {a['inciso']} — {falta}"
                      + (f" ({porque})" if porque else ""))
    return "; ".join(partes)


# ------------------------------------------------------------- o teor


def descricao_do_documento(d: dict, con: Any = None) -> str:
    """O «documento abaixo descrito», item a item do art. 914. Só calcula.

    QUAIS pedaços entram é daqui; o texto de cada um é a peça
    `PT_INSTRUMENTO_DESCRICAO` (LF06E), e o nome da espécie é o do papel
    (`PT_ESPECIES`) — com `con`, os da casa; sem ele, o padrão.
    """
    p = pedacos_da_descricao(d, con)
    partes = [p["registro"], p["protocolo"], p["titulo"], p["apresentante"],
              p["credor"], *p["devedores"], p["tipo_e_motivo"]]
    return " ".join(x for x in partes if x)


def pedacos_da_descricao(d: dict, con: Any = None) -> dict:
    """Os pedaços da descrição do art. 914, cada um já escrito. Só calcula.

    O REGISTRO DO PROTESTO E O INSTRUMENTO DIZEM O MESMO (LD04, 21/10/2026):
    Lei 9.492/1997, art. 22, e CN-MA art. 914 — «o registro do protesto e a
    sua consequente certidão do instrumento» contêm os mesmos itens. O termo
    lavrado (`protesto_termo.montar`) usa ESTES pedaços, e não outra redação:
    duas redações do mesmo fato divergiriam no primeiro conserto. Pedaço que
    o título não tem vem vazio (`""`), e quem junta o deixa de fora.
    """
    import protesto_pecas as PECAS
    import protesto_termo as TERMO
    rotulo = PECAS.vocabulario(con, "PT_INSTRUMENTO_DESCRICAO")

    def _p(nome: str, **claros: Any) -> str:
        return PECAS.preencher(rotulo[nome], "PT_INSTRUMENTO_DESCRICAO",
                               InstrumentoError, **claros)

    t, prot = d["titulo"], d["protesto"] or {}
    especie = PECAS.vocabulario(con, "PT_ESPECIES").get(
        _texto(t.get("especie")).upper(), _texto(t.get("especie")))
    pedacos: dict[str, Any] = {"lugar": "", "data_registro": "", "registro": "",
                               "protocolo": "", "apresentante": "", "credor": "",
                               "tipo_e_motivo": ""}
    if prot:
        lugar = []
        if prot.get("livro_numero"):
            lugar.append(_p("livro", livro=prot["livro_numero"]))
        if prot.get("rotulo") or prot.get("folha"):
            lugar.append(_p("folha", folha=prot.get("rotulo") or prot.get("folha")))
        if prot.get("numero_ordem"):
            lugar.append(_p("numero_de_ordem", numero_ordem=prot["numero_ordem"]))
        pedacos["lugar"] = ", ".join(lugar) or _p("sem_lugar")
        pedacos["data_registro"] = _data_br(prot.get("data_ato"))
        pedacos["registro"] = _p("registro", lugar=pedacos["lugar"],
                                 data=pedacos["data_registro"])
    if _texto(t.get("protocolo")):
        pedacos["protocolo"] = (
            _p("protocolo_com_data", protocolo=t["protocolo"],
               data=_data_br(d.get("apontado_em")))
            if d.get("apontado_em") else _p("protocolo", protocolo=t["protocolo"]))
    do_titulo = [
        _p("titulo", especie=especie or _p("sem_especie"),
           numero_titulo=_texto(t.get("numero_titulo")) or _p("sem_numero")),
        (_p("emissao", data=_data_br(t["data_emissao"]))
         if t.get("data_emissao") else None),
        (_p("vencimento", data=_data_br(t["data_vencimento"]))
         if t.get("data_vencimento") else None),
        _p("valor", valor=_reais(t.get("valor_centavos"))),
        (_p("valor_protestado", valor=_reais(t.get("saldo_centavos")))
         if t.get("saldo_centavos") and t.get("saldo_centavos") != t.get("valor_centavos")
         else None)]
    pedacos["titulo"] = ", ".join(x for x in do_titulo if x) + "."
    # O NOME E O ENDEREÇO DO APRESENTANTE — Lei 9.492/1997, art. 22, II; CN-MA
    # art. 914, III (LD08, 21/10/2026). O endereço vem em `d["apresentante"]`,
    # que quem lê os fatos monta (`dados`, `protesto_termo.fatos_da_qualificacao`
    # — o título ou o cadastro dos apresentantes); sem ele, o pedaço de antes.
    ap = d.get("apresentante") or {}
    nome_ap = (_texto(t.get("apresentante_nome")) or _texto(ap.get("nome"))
               or _texto(t.get("apresentante_codigo")))
    endereco_ap = _texto(ap.get("endereco")) or _texto(t.get("apresentante_endereco"))
    if nome_ap:
        pedacos["apresentante"] = (
            _p("apresentante_endereco", apresentante=nome_ap, endereco=endereco_ap)
            if endereco_ap else _p("apresentante", apresentante=nome_ap))
    if _texto(t.get("cedente_nome")):
        doc = _texto(t.get("cedente_documento"))
        pedacos["credor"] = (_p("credor_com_documento", credor=t["cedente_nome"],
                                documento=doc)
                             if doc else _p("credor", credor=t["cedente_nome"]))
    pedacos["devedores"] = []
    for dev in d.get("devedores") or []:
        end = ", ".join(x for x in (_texto(dev.get("endereco")), _texto(dev.get("bairro")),
                                    _texto(dev.get("cidade")) and
                                    f"{_texto(dev.get('cidade'))}/{_texto(dev.get('uf'))}") if x)
        do_devedor = [
            _p("devedor", devedor=_texto(dev.get("nome"))),
            (_p("devedor_documento",
                tipo_documento=dev.get("documento_tipo") or _p("sem_tipo_de_documento"),
                documento=_texto(dev.get("documento_numero")))
             if _texto(dev.get("documento_numero")) else None),
            _p("devedor_endereco", endereco=end) if end else None]
        pedacos["devedores"].append(", ".join(x for x in do_devedor if x) + ".")
    motivo = TERMO.motivo_no_livro(t.get("motivo_protesto"), con)
    if motivo:
        pedacos["tipo_e_motivo"] = _p(
            "tipo_e_motivo",
            tipo=TERMO.tipo_no_livro(t.get("tipo_protesto"), con).lower(),
            motivo=motivo.lower())
    return pedacos


def _frase(con: Any, chave: str, **claros: Any) -> str:
    """A peça do instrumento, com o ajuste da casa (com `con`) ou o padrão."""
    import protesto_pecas as PECAS
    return PECAS.montar(con, chave, InstrumentoError, **claros)


def montar_teor(*, modelo: str | None = None, serventia: str, praca: str,
                motivo: str, copia_arquivada: bool,
                intimacao: dict | None, descricao: str = "",
                con: Any = None, atraso: dict | None = None) -> str:
    """O corpo do instrumento. Não grava.

    `copia_arquivada` decide a **menção do § único**, e por isso é obrigatório
    e não tem padrão: quem chama tem de ter ido perguntar. Um padrão `True`
    faria o papel afirmar um arquivo que ninguém conferiu.

    Com `con`, as frases (cópia, certidão da intimação) saem com o ajuste da
    casa; sem ele, com o padrão da base — ver `protesto_pecas`.
    """
    if not modelo:
        import modelos_da_casa as CASA
        modelo = CASA.padrao_de(CHAVE_NO_CATALOGO)
    texto = modelo
    if copia_arquivada:
        copia = _frase(con, "PT_INSTRUMENTO_COPIA_ARQUIVADA")
    else:
        # SEM CÓPIA A DISPENSA NÃO VALE, e o sistema não tem a transcrição do
        # título — ela está na imagem que a CRA entrega. O papel diz o que é
        # verdade, e a conferência já mostrou o item III em falta.
        copia = _frase(con, "PT_INSTRUMENTO_SEM_COPIA")
    if intimacao is None:
        certidao = _frase(con, "PT_INSTRUMENTO_SEM_INTIMACAO")
    elif (intimacao.get("modo") or "").upper() == "EDITAL":
        quando = _data_br(intimacao.get("data"))
        motivo_ne = _texto(intimacao.get("motivo_nao_entrega"))
        certidao = (_frase(con, "PT_INSTRUMENTO_INTIMACAO_EDITAL",
                           data=quando, motivo=motivo_ne) if motivo_ne
                    else _frase(con, "PT_INSTRUMENTO_INTIMACAO_EDITAL_SEM_MOTIVO",
                                data=quando))
    elif intimacao.get("digital"):
        # A ELETRÔNICA TEM A SUA CERTIDÃO, a mesma que o termo lavra (LD04).
        certidao = _frase(con, "PT_INSTRUMENTO_INTIMACAO_DIGITAL",
                          data=_data_br(intimacao.get("data")))
    else:
        certidao = _frase(con, "PT_INSTRUMENTO_INTIMACAO_ENTREGUE",
                          data=_data_br(intimacao.get("data")))
    try:
        pronto = texto.format(serventia=serventia, praca=praca, motivo=motivo,
                              copia=copia, intimacao=certidao,
                              descricao=descricao)
    except (KeyError, IndexError) as erro:
        raise InstrumentoError(
            f"O modelo do instrumento pede um campo que o sistema não sabe "
            f"preencher: {erro}. Confira o texto em Modelos da casa.") from erro
    # O ATRASO DO TRÍDUO VAI NO FIM (tarefa 56, 23/10/2026): CN-MA art. 913,
    # § 1º — «o tabelião deverá mencionar no instrumento a circunstância do
    # atraso, indicando, de forma sucinta, o motivo». Sai depois do corpo, e
    # não como claro do modelo: o modelo que o oficial já ajustou continua
    # servindo, e a frase só aparece no protesto lavrado fora do tríduo.
    if atraso:
        pronto += " " + _frase(con, "PT_INSTRUMENTO_ATRASO",
                               termo_final=_data_br(atraso.get("termo_final")),
                               data=_data_br(atraso.get("lavrado_em")),
                               motivo=_texto(atraso.get("motivo")))
    # SEM CLARO NENHUM NO QUE SAI — inclusive se o modelo que o oficial editar
    # no catálogo trouxer quebra de linha ou espaço duplo por engano.
    return " ".join(pronto.split())


def hash_instrumento(numero: int, ano: int, titulo_id: int, teor: str) -> str:
    """A impressão do que saiu — a forma do recibo do caixa e da certidão."""
    base = f"{int(numero)}|{int(ano)}|{int(titulo_id)}|{teor}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def proximo_numero(con, ano: int) -> int:
    """O próximo do exercício. Só LÊ — quem consome é o `INSERT` de `emitir`."""
    m = banco(con).valor(
        "SELECT MAX(numero) AS m FROM pt_instrumentos WHERE ano = %s",
        (int(ano),))
    return int((m or 0) + 1)


# ------------------------------------------------------------- emitir


def emitir(con, titulo_id: int, *, serventia: str,
           agora: str, modelo: str | None = None,
           usuario: str | None = None) -> dict:
    """Emite o instrumento, com número do exercício, teor congelado e hash.
    ESCREVE — chame dentro de `db.transaction()`.

    **SEM PROTESTO LAVRADO NÃO HÁ INSTRUMENTO DE PROTESTO.** É a única recusa
    deste módulo, e ela protege o que mais importa: um papel com este nome
    afirma que o ato existe, e ele vai assinado para o credor.

    Ele **entra na fila de assinatura** ao ser emitido (`as_documentos`), com
    o sha256 do teor. Quem assina é o delegatário, fora do sistema — ver
    `assinatura_digital`.
    """
    bd = banco(con)
    d = dados(bd, titulo_id)
    t, prot = d["titulo"], d["protesto"]
    if prot is None:
        raise InstrumentoError(
            "Este título não tem protesto lavrado, e o instrumento de "
            "protesto afirma que o ato existe. Lavre o protesto primeiro.")

    data_do_ato = _texto(prot.get("data_ato")) or _texto(agora)[:10]
    ano = int(data_do_ato[:4]) if len(data_do_ato) >= 4 else 0
    if not ano:
        raise InstrumentoError(
            "O ato de protesto está sem data, e o instrumento a declara. "
            "Corrija a data do ato antes de emitir.")

    # SEM MOTIVO NÃO HÁ INSTRUMENTO — até 14/10/2026 faltando o motivo saía
    # «FALTA DE PAGAMENTO» por conta própria. O termo recusa; o instrumento,
    # que é a cópia que vai ao credor, recusa igual (CN-MA art. 914, X).
    import protesto_termo as TERMO
    import protesto_triduo as TRIDUO
    motivo = TERMO.motivo_no_livro(t.get("motivo_protesto"), bd)
    if not motivo:
        raise InstrumentoError(
            "O título não diz o motivo do protesto (falta de pagamento, de "
            "aceite ou de devolução), e o instrumento o declara. Informe-o na "
            "ficha do título.")
    teor = montar_teor(
        modelo=modelo, serventia=serventia,
        praca=(_texto(t.get("praca_protesto"))
               or _frase(bd, "PT_INSTRUMENTO_PRACA")),
        motivo=motivo,
        copia_arquivada=d["copias_arquivadas"] > 0,
        intimacao=d["intimacao"],
        descricao=descricao_do_documento(d, bd), con=bd,
        atraso=TRIDUO.mencao_no_instrumento(prot.get("detalhe_json")))

    bd.travar("pt_instrumentos.numero")
    numero = proximo_numero(bd, ano)
    corpo = json.dumps(
        {"titulo": {k: t.get(k) for k in (
            "especie", "numero_titulo", "nosso_numero", "chave_cenprot",
            "data_emissao", "data_vencimento", "valor_centavos",
            "saldo_centavos", "tipo_protesto", "motivo_protesto",
            "tipo_endosso", "aceite", "praca_protesto", "protocolo",
            "apresentante_codigo", "apresentante_nome", "cedente_nome",
            "cedente_documento")},
         "valor": _reais(t.get("valor_centavos")),
         "protesto": {k: prot.get(k) for k in (
             "data_ato", "livro_id", "folha", "verso", "numero_ordem",
             "rotulo", "selo")},
         "apontado_em": d["apontado_em"],
         "apresentante": d["apresentante"],
         "intimacao": d["intimacao"],
         "devedores": d["devedores"],
         "copias_arquivadas": d["copias_arquivadas"]},
        ensure_ascii=False, sort_keys=True)
    impressao = hash_instrumento(numero, ano, int(titulo_id), teor + corpo)

    instrumento_id = int(bd.escrever(
        """INSERT INTO pt_instrumentos(
               numero, ano, titulo_id, ato_id, teor, corpo_json,
               hash_instrumento, emitido_em, emitido_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (numero, ano, int(titulo_id), int(prot["id"]), teor, corpo,
         impressao, agora, usuario))[0]["id"])

    # A FILA DA ASSINATURA É A DA CASA INTEIRA, e o instrumento é só mais um
    # papel nela. `as_documentos` tem `UNIQUE(entidade, entidade_id)`, e cada
    # emissão é a sua própria linha — segunda via é outro documento.
    bd.escrever(
        """INSERT INTO as_documentos(
               entidade, entidade_id, titulo, sha256_documento, criado_em,
               criado_por)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (ENTIDADE_DA_ASSINATURA, instrumento_id,
         f"Instrumento de protesto n.º {numero}/{ano}",
         impressao, agora, usuario))

    return {"id": instrumento_id, "numero": numero, "ano": ano,
            "teor": teor, "hash_instrumento": impressao,
            "data_do_protesto": data_do_ato,
            "data_por_extenso": _por_extenso(data_do_ato)}


# ------------------------------------------------------------- consultar


def instrumento(con, instrumento_id: int) -> dict | None:
    """Um instrumento pelo `id`, com o corpo já aberto. Só LÊ."""
    linha = banco(con).um(
        "SELECT * FROM pt_instrumentos WHERE id = %s",
        (int(instrumento_id),))
    if linha is None:
        return None
    d = dict(linha)
    try:
        d["corpo"] = json.loads(d.get("corpo_json") or "{}")
    except (TypeError, ValueError):
        d["corpo"] = {}
    d["data_por_extenso"] = _por_extenso(
        (d["corpo"].get("protesto") or {}).get("data_ato"))
    return d


def do_titulo(con, titulo_id: int) -> list[dict]:
    """Os instrumentos emitidos daquele título, do mais novo. Só LÊ.

    São vários quando houve segunda via, e a ficha os mostra todos: quem
    conferir precisa saber quantas vias saíram e quando.
    """
    return banco(con).ler(
        """SELECT id, numero, ano, teor, hash_instrumento, emitido_em,
                  emitido_por
             FROM pt_instrumentos WHERE titulo_id = %s ORDER BY id DESC""",
        (int(titulo_id),))


def a_entregar(con, limite: int = 200) -> list[dict]:
    """Os protestos lavrados que ainda não têm instrumento. Só LÊ.

    **CONTA, E NÃO JULGA** — a mesma regra do roteiro das Centrais. O art. 20
    põe o instrumento à disposição do apresentante no primeiro dia útil
    seguinte ao registro; quem diz se o prazo correu é quem tem o calendário
    do balcão, e não uma lista.
    """
    return banco(con).ler(
        """SELECT a.titulo_id, a.data_ato, t.protocolo, t.numero_titulo,
                  t.apresentante_nome
             FROM pt_atos a
             JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.tipo = 'PROTESTO' AND a.cancelado = 0
              AND NOT EXISTS (SELECT 1 FROM pt_instrumentos i
                               WHERE i.titulo_id = a.titulo_id)
            ORDER BY a.data_ato DESC, a.id DESC LIMIT %s""", (int(limite),))


def contagens(con) -> dict:
    """Quantos protestos há, quantos com instrumento e quantos sem. Só LÊ."""
    bd = banco(con)
    lavrados = bd.um(
        """SELECT COUNT(*) AS c FROM pt_atos
            WHERE tipo = 'PROTESTO' AND cancelado = 0""")
    com = bd.um(
        """SELECT COUNT(DISTINCT titulo_id) AS c FROM pt_instrumentos""")
    n_lavrados = int(lavrados["c"] if lavrados else 0)
    n_com = int(com["c"] if com else 0)
    return {"protestos": n_lavrados, "com_instrumento": n_com,
            "sem_instrumento": max(n_lavrados - n_com, 0)}


# ------------------------------------- o instrumento assinado com o A3
#
# Pedido do oficial, 15/10/2026: «vamos criar o gerador de arquivo e assinar
# com o certificado». O instrumento sai em PDF, o serviço local de assinatura
# (`a3_servico_local`, com o token do oficial plugado e o PIN digitado por ele)
# devolve o PKCS#7 com o PDF dentro — o formato medido nos 44 instrumentos que
# esta casa mandou à CENPROT —, e ele fica guardado na fila da casa
# (`as_documentos`), que até aqui esperava um arquivo que nada recebia.


def guardar_assinatura(con, instrumento_id: int, *,
                       pdf: bytes, p7s: bytes, pasta_de_arquivos: Any,
                       agora: str, usuario: str | None = None) -> dict:
    """Guarda o instrumento assinado. ESCREVE, e grava os dois arquivos.

    **CONFERE ANTES DE GUARDAR** (`assinatura_digital.conferir`): o PDF de
    dentro do pacote tem de ser, byte a byte, o PDF que a casa acabou de gerar.
    Assinatura que embrulha outro papel não serve, e não entra.
    """
    from pathlib import Path

    import assinatura_digital as ASD
    bd = banco(con)
    ins = instrumento(bd, instrumento_id)
    if not ins:
        raise InstrumentoError(f"Instrumento {instrumento_id} não encontrado.")
    resultado = ASD.conferir(bytes(p7s), documento=bytes(pdf))
    if not resultado.get("serve"):
        raise InstrumentoError(
            "A assinatura não confere com o instrumento: "
            + (ASD.por_que_nao_serve(resultado) or "motivo não identificado")
            + ". Nada foi guardado.")
    quem = resultado.get("quem_assinou") or {}
    destino = Path(pasta_de_arquivos) / "Protesto" / "Instrumentos"
    destino.mkdir(parents=True, exist_ok=True)
    base = destino / f"instrumento-{ins['numero']}-{ins['ano']}"
    base.with_suffix(".pdf").write_bytes(bytes(pdf))
    base.with_suffix(".p7s").write_bytes(bytes(p7s))
    import hashlib
    bd.escrever(
        """UPDATE as_documentos
              SET caminho_documento=%s, tamanho_documento=%s,
                  caminho_assinado=%s, sha256_assinado=%s, assinado_em=%s,
                  assinado_por_nome=%s, assinado_por_cpf=%s, recebido_por=%s
            WHERE entidade=%s AND entidade_id=%s""",
        (str(base.with_suffix(".pdf")), len(pdf), str(base.with_suffix(".p7s")),
         hashlib.sha256(bytes(p7s)).hexdigest(), agora, quem.get("nome"),
         quem.get("cpf"), usuario, ENTIDADE_DA_ASSINATURA, int(instrumento_id)))
    if not bd.linhas_afetadas:
        raise InstrumentoError(
            "Este instrumento não está na fila de assinatura da casa — emita-o "
            "de novo pela ficha do título.")
    return {"instrumento_id": int(instrumento_id),
            "assinado_por": quem.get("nome"), "numero": ins["numero"],
            "ano": ins["ano"]}


def assinado_do_titulo(con, titulo_id: int) -> bytes | None:
    """O `.p7s` do instrumento mais recente e ASSINADO do título. Só LÊ."""
    from pathlib import Path
    caminho = banco(con).valor(
        """SELECT d.caminho_assinado FROM pt_instrumentos i
             JOIN as_documentos d ON d.entidade=%s AND d.entidade_id=i.id
            WHERE i.titulo_id=%s AND d.caminho_assinado IS NOT NULL
            ORDER BY i.id DESC LIMIT 1""",
        (ENTIDADE_DA_ASSINATURA, int(titulo_id)))
    if not caminho or not Path(caminho).exists():
        return None
    return Path(caminho).read_bytes()


def __getattr__(nome: str):
    """Os nomes antigos do texto de fábrica, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06A (19/10/2026) e mora em `modelos_padrao/`.
    Quem ainda importa o nome antigo recebe o padrão da base — o MESMO que o
    papel imprime, e não uma cópia que ficou para trás. Nome que não é de papel
    continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
