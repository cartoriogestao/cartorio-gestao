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
import sqlite3
from typing import Any

import protesto_cra as CRA

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
     "de_onde": ("titulo", "apresentante_nome"),
     # MEDIDO EM 01/09/2026: o cabeçalho da remessa da CRA tem código (3) e
     # nome (40) do apresentante, e nenhuma posição de endereço; e o acervo
     # não tem cadastro de apresentante — `tbCedente` é o CEDENTE.
     "falta": "endereço do apresentante",
     "porque": ("o arquivo da CRA traz só o código e o nome do apresentante, "
                "e o acervo do E-Ofício não tem cadastro dele — o endereço "
                "não está em fonte nenhuma que se tenha medido")},
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
TEXTO_BASE = (
    "O {serventia}, Tabelionato de Protesto de Títulos, DECLARA PROTESTADO o "
    "documento abaixo descrito, pagável na praça de {praca}, em virtude do "
    "que se fez a intimação devida, na forma da Lei, para que o devedor se "
    "manifestasse a respeito; pelo que, para garantia do credor, foi lavrado "
    "este Protesto, por motivo de {motivo}.")

# A MENÇÃO DO § ÚNICO — e ela só se escreve quando a cópia existe de verdade.
MENCAO_DA_COPIA_ARQUIVADA = (
    "Fica dispensada a transcrição literal do documento, na forma do parágrafo "
    "único do art. 22 da Lei n.º 9.492/1997, por conservar esta serventia "
    "cópia digital do título, arquivada sob este protesto.")

# **TEXTO CORRIDO, SEM CLAROS** — art. 795, § 2º do Código de Normas, a mesma
# regra de `notas_modelos.py`. Até 07/09/2026 as três partes eram separadas
# por `"\n\n"` — linha em branco de propósito —, e isso ia inteiro para o
# papel que o tabelião assina e entrega ao apresentante.
INSTRUMENTO_DE_PROTESTO = TEXTO_BASE + " {descricao} {copia} {intimacao}"

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


def dados(con: sqlite3.Connection, titulo_id: int) -> dict:
    """Tudo o que o instrumento afirma, lido do que foi lavrado. Só LÊ.

    **O INSTRUMENTO SAI DO ATO, E NÃO DO TÍTULO.** Um título apontado e não
    protestado não tem instrumento — e é `protesto` do PROTESTO que carrega
    livro, folha, número de ordem e a data que o papel declara.
    """
    titulo = con.execute(
        """SELECT * FROM pt_titulos WHERE id = ?""", (int(titulo_id),)).fetchone()
    if titulo is None:
        raise InstrumentoError(
            f"Não há título com o número interno {titulo_id} neste sistema.")

    tem_livros = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='nu_livros'"
    ).fetchone() is not None
    livro_sql = ("(SELECT v.numero FROM nu_livros v WHERE v.id = a.livro_id)"
                 if tem_livros else "NULL")
    protesto = con.execute(
        f"""SELECT a.*, {livro_sql} livro_numero
             FROM pt_atos a
            WHERE a.titulo_id = ? AND a.tipo = 'PROTESTO' AND a.cancelado = 0
            ORDER BY a.id DESC LIMIT 1""", (int(titulo_id),)).fetchone()

    apontamento = con.execute(
        """SELECT data_ato FROM pt_atos
            WHERE titulo_id = ? AND tipo = 'APONTAMENTO' AND cancelado = 0
            ORDER BY id LIMIT 1""", (int(titulo_id),)).fetchone()

    # A ÚLTIMA INTIMAÇÃO É A QUE CONTA — o aviso não é um por título, e
    # reemitir é rotina. É a mesma regra de `protesto_termo.dados_do_titulo`.
    intimacao = con.execute(
        """SELECT data_ato, detalhe_json FROM pt_atos
            WHERE titulo_id = ? AND tipo = 'INTIMACAO' AND cancelado = 0
            ORDER BY id DESC LIMIT 1""", (int(titulo_id),)).fetchone()
    modo, motivo_nao_entrega = None, None
    if intimacao is not None:
        try:
            detalhe = json.loads(intimacao["detalhe_json"] or "{}")
        except (TypeError, ValueError):
            detalhe = {}
        modo = _texto(detalhe.get("modo")).upper() or None
        motivo_nao_entrega = (detalhe.get("motivo_nao_entrega")
                              or detalhe.get("motivo") or None)

    devedores = [dict(r) for r in con.execute(
        """SELECT nome, documento_tipo, documento_numero, endereco, bairro,
                  cep, cidade, uf
             FROM pt_devedores WHERE titulo_id = ? ORDER BY id""",
        (int(titulo_id),))]

    # O § ÚNICO SE PERGUNTA AO BANCO. `protesto_imagens` guarda a imagem do
    # título na `attachments` da casa; contar aqui evita importar o módulo só
    # para uma contagem — e a entidade é a dele, medida e não escrita.
    copias = con.execute(
        """SELECT COUNT(*) c FROM attachments
            WHERE entity_type = 'pt_titulos' AND entity_id = ?""",
        (int(titulo_id),)).fetchone()

    return {"titulo": dict(titulo),
            "protesto": dict(protesto) if protesto is not None else None,
            "apontado_em": (apontamento["data_ato"]
                            if apontamento is not None else None),
            "intimacao": ({"data": intimacao["data_ato"], "modo": modo,
                           "motivo_nao_entrega": motivo_nao_entrega}
                          if intimacao is not None else None),
            "devedores": devedores,
            "copias_arquivadas": int(copias["c"] if copias else 0)}


# ------------------------------------------------------------- conferir


def conferir(con: sqlite3.Connection, titulo_id: int) -> dict:
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
        else:  # pragma: no cover - fonte nova sem tratamento é defeito, não caso
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


def descricao_do_documento(d: dict) -> str:
    """O «documento abaixo descrito», item a item do art. 914. Só calcula."""
    import protesto_termo as TERMO
    t, prot = d["titulo"], d["protesto"] or {}
    especie = CRA.ESPECIES.get(_texto(t.get("especie")).upper(),
                               _texto(t.get("especie")))
    partes = []
    if prot:
        lugar = []
        if prot.get("livro_numero"):
            lugar.append(f"Livro {prot['livro_numero']}")
        if prot.get("rotulo") or prot.get("folha"):
            lugar.append(f"folha {prot.get('rotulo') or prot.get('folha')}")
        if prot.get("numero_ordem"):
            lugar.append(f"sob o n.º {prot['numero_ordem']}")
        partes.append("Registro do protesto: " + (", ".join(lugar) or
                      "livro e folha não constam") +
                      f", em {_data_br(prot.get('data_ato'))}.")
    if _texto(t.get("protocolo")):
        partes.append(f"Protocolo n.º {t['protocolo']}"
                      + (f", de {_data_br(d.get('apontado_em'))}"
                         if d.get("apontado_em") else "") + ".")
    partes.append(
        f"Título: {especie or 'espécie não informada'}, n.º "
        f"{_texto(t.get('numero_titulo')) or 'sem número'}"
        + (f", emitido em {_data_br(t['data_emissao'])}" if t.get("data_emissao") else "")
        + (f", vencido em {_data_br(t['data_vencimento'])}" if t.get("data_vencimento") else "")
        + f", valor R$ {_reais(t.get('valor_centavos'))}"
        + (f", valor protestado R$ {_reais(t.get('saldo_centavos'))}"
           if t.get("saldo_centavos") and t.get("saldo_centavos") != t.get("valor_centavos")
           else "") + ".")
    if _texto(t.get("apresentante_nome")) or _texto(t.get("apresentante_codigo")):
        partes.append(f"Apresentante: {_texto(t.get('apresentante_nome')) or _texto(t.get('apresentante_codigo'))}.")
    if _texto(t.get("cedente_nome")):
        doc = _texto(t.get("cedente_documento"))
        partes.append(f"Credor (sacador/favorecido): {t['cedente_nome']}"
                      + (f", CPF/CNPJ {doc}" if doc else "") + ".")
    for dev in d.get("devedores") or []:
        end = ", ".join(x for x in (_texto(dev.get("endereco")), _texto(dev.get("bairro")),
                                    _texto(dev.get("cidade")) and
                                    f"{_texto(dev.get('cidade'))}/{_texto(dev.get('uf'))}") if x)
        partes.append(f"Devedor: {_texto(dev.get('nome'))}"
                      + (f", {dev.get('documento_tipo') or 'documento'} "
                         f"{_texto(dev.get('documento_numero'))}"
                         if _texto(dev.get("documento_numero")) else "")
                      + (f", endereço {end}" if end else "") + ".")
    motivo = TERMO.motivo_no_livro(t.get("motivo_protesto"))
    if motivo:
        partes.append(f"Tipo: protesto {TERMO.tipo_no_livro(t.get('tipo_protesto')).lower()}. "
                      f"Motivo: {motivo.lower()}.")
    return " ".join(partes)


def montar_teor(*, modelo: str | None = None, serventia: str, praca: str,
                motivo: str, copia_arquivada: bool,
                intimacao: dict | None, descricao: str = "") -> str:
    """O corpo do instrumento. Não lê banco e não grava.

    `copia_arquivada` decide a **menção do § único**, e por isso é obrigatório
    e não tem padrão: quem chama tem de ter ido perguntar. Um padrão `True`
    faria o papel afirmar um arquivo que ninguém conferiu.
    """
    texto = (modelo or INSTRUMENTO_DE_PROTESTO)
    if copia_arquivada:
        copia = MENCAO_DA_COPIA_ARQUIVADA
    else:
        # SEM CÓPIA A DISPENSA NÃO VALE, e o sistema não tem a transcrição do
        # título — ela está na imagem que a CRA entrega. O papel diz o que é
        # verdade, e a conferência já mostrou o item III em falta.
        copia = ("Não consta desta serventia cópia arquivada do título, pelo "
                 "que não se aplica a dispensa do parágrafo único do art. 22 "
                 "da Lei n.º 9.492/1997.")
    if intimacao is None:
        certidao = ("CERTIFICO que não consta ato de intimação lavrado para "
                    "este título.")
    elif (intimacao.get("modo") or "").upper() == "EDITAL":
        certidao = ("CERTIFICO que a intimação foi feita por EDITAL, publicado "
                    f"em {_data_br(intimacao.get('data'))}")
        motivo_ne = _texto(intimacao.get("motivo_nao_entrega"))
        certidao += f", pelo motivo {motivo_ne}." if motivo_ne else "."
    else:
        certidao = ("CERTIFICO que a intimação foi entregue no endereço do "
                    f"devedor em {_data_br(intimacao.get('data'))}.")
    try:
        pronto = texto.format(serventia=serventia, praca=praca, motivo=motivo,
                              copia=copia, intimacao=certidao,
                              descricao=descricao)
    except (KeyError, IndexError) as erro:
        raise InstrumentoError(
            f"O modelo do instrumento pede um campo que o sistema não sabe "
            f"preencher: {erro}. Confira o texto em Modelos da casa.") from erro
    # SEM CLARO NENHUM NO QUE SAI — inclusive se o modelo que o oficial editar
    # no catálogo trouxer quebra de linha ou espaço duplo por engano.
    return " ".join(pronto.split())


def hash_instrumento(numero: int, ano: int, titulo_id: int, teor: str) -> str:
    """A impressão do que saiu — a forma do recibo do caixa e da certidão."""
    base = f"{int(numero)}|{int(ano)}|{int(titulo_id)}|{teor}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def proximo_numero(con: sqlite3.Connection, ano: int) -> int:
    """O próximo do exercício. Só LÊ — quem consome é o `INSERT` de `emitir`."""
    linha = con.execute(
        "SELECT MAX(numero) m FROM pt_instrumentos WHERE ano = ?",
        (int(ano),)).fetchone()
    return int((linha["m"] or 0) + 1) if linha else 1


# ------------------------------------------------------------- emitir


def emitir(con: sqlite3.Connection, titulo_id: int, *, serventia: str,
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
    d = dados(con, titulo_id)
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
    motivo = TERMO.motivo_no_livro(t.get("motivo_protesto"))
    if not motivo:
        raise InstrumentoError(
            "O título não diz o motivo do protesto (falta de pagamento, de "
            "aceite ou de devolução), e o instrumento o declara. Informe-o na "
            "ficha do título.")
    teor = montar_teor(
        modelo=modelo, serventia=serventia,
        praca=_texto(t.get("praca_protesto")) or "desta praça",
        motivo=motivo,
        copia_arquivada=d["copias_arquivadas"] > 0,
        intimacao=d["intimacao"],
        descricao=descricao_do_documento(d))

    numero = proximo_numero(con, ano)
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
         "intimacao": d["intimacao"],
         "devedores": d["devedores"],
         "copias_arquivadas": d["copias_arquivadas"]},
        ensure_ascii=False, sort_keys=True)
    impressao = hash_instrumento(numero, ano, int(titulo_id), teor + corpo)

    cur = con.execute(
        """INSERT INTO pt_instrumentos(
               numero, ano, titulo_id, ato_id, teor, corpo_json,
               hash_instrumento, emitido_em, emitido_por)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (numero, ano, int(titulo_id), int(prot["id"]), teor, corpo,
         impressao, agora, usuario))
    instrumento_id = int(cur.lastrowid)

    # A FILA DA ASSINATURA É A DA CASA INTEIRA, e o instrumento é só mais um
    # papel nela. `as_documentos` tem `UNIQUE(entidade, entidade_id)`, e cada
    # emissão é a sua própria linha — segunda via é outro documento.
    con.execute(
        """INSERT INTO as_documentos(
               entidade, entidade_id, titulo, sha256_documento, criado_em,
               criado_por)
           VALUES (?,?,?,?,?,?)""",
        (ENTIDADE_DA_ASSINATURA, instrumento_id,
         f"Instrumento de protesto n.º {numero}/{ano}",
         impressao, agora, usuario))

    return {"id": instrumento_id, "numero": numero, "ano": ano,
            "teor": teor, "hash_instrumento": impressao,
            "data_do_protesto": data_do_ato,
            "data_por_extenso": _por_extenso(data_do_ato)}


# ------------------------------------------------------------- consultar


def instrumento(con: sqlite3.Connection, instrumento_id: int) -> dict | None:
    """Um instrumento pelo `id`, com o corpo já aberto. Só LÊ."""
    linha = con.execute(
        "SELECT * FROM pt_instrumentos WHERE id = ?",
        (int(instrumento_id),)).fetchone()
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


def do_titulo(con: sqlite3.Connection, titulo_id: int) -> list[dict]:
    """Os instrumentos emitidos daquele título, do mais novo. Só LÊ.

    São vários quando houve segunda via, e a ficha os mostra todos: quem
    conferir precisa saber quantas vias saíram e quando.
    """
    return [dict(r) for r in con.execute(
        """SELECT id, numero, ano, teor, hash_instrumento, emitido_em,
                  emitido_por
             FROM pt_instrumentos WHERE titulo_id = ? ORDER BY id DESC""",
        (int(titulo_id),))]


def a_entregar(con: sqlite3.Connection, limite: int = 200) -> list[dict]:
    """Os protestos lavrados que ainda não têm instrumento. Só LÊ.

    **CONTA, E NÃO JULGA** — a mesma regra do roteiro das Centrais. O art. 20
    põe o instrumento à disposição do apresentante no primeiro dia útil
    seguinte ao registro; quem diz se o prazo correu é quem tem o calendário
    do balcão, e não uma lista.
    """
    return [dict(r) for r in con.execute(
        """SELECT a.titulo_id, a.data_ato, t.protocolo, t.numero_titulo,
                  t.apresentante_nome
             FROM pt_atos a
             JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.tipo = 'PROTESTO' AND a.cancelado = 0
              AND NOT EXISTS (SELECT 1 FROM pt_instrumentos i
                               WHERE i.titulo_id = a.titulo_id)
            ORDER BY a.data_ato DESC, a.id DESC LIMIT ?""", (int(limite),))]


def contagens(con: sqlite3.Connection) -> dict:
    """Quantos protestos há, quantos com instrumento e quantos sem. Só LÊ."""
    lavrados = con.execute(
        """SELECT COUNT(*) c FROM pt_atos
            WHERE tipo = 'PROTESTO' AND cancelado = 0""").fetchone()
    com = con.execute(
        """SELECT COUNT(DISTINCT titulo_id) c FROM pt_instrumentos""").fetchone()
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


def guardar_assinatura(con: sqlite3.Connection, instrumento_id: int, *,
                       pdf: bytes, p7s: bytes, pasta_de_arquivos: Any,
                       agora: str, usuario: str | None = None) -> dict:
    """Guarda o instrumento assinado. ESCREVE, e grava os dois arquivos.

    **CONFERE ANTES DE GUARDAR** (`assinatura_digital.conferir`): o PDF de
    dentro do pacote tem de ser, byte a byte, o PDF que a casa acabou de gerar.
    Assinatura que embrulha outro papel não serve, e não entra.
    """
    from pathlib import Path

    import assinatura_digital as ASD
    ins = instrumento(con, instrumento_id)
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
    cur = con.execute(
        """UPDATE as_documentos
              SET caminho_documento=?, tamanho_documento=?,
                  caminho_assinado=?, sha256_assinado=?, assinado_em=?,
                  assinado_por_nome=?, assinado_por_cpf=?, recebido_por=?
            WHERE entidade=? AND entidade_id=?""",
        (str(base.with_suffix(".pdf")), len(pdf), str(base.with_suffix(".p7s")),
         hashlib.sha256(bytes(p7s)).hexdigest(), agora, quem.get("nome"),
         quem.get("cpf"), usuario, ENTIDADE_DA_ASSINATURA, int(instrumento_id)))
    if not cur.rowcount:
        raise InstrumentoError(
            "Este instrumento não está na fila de assinatura da casa — emita-o "
            "de novo pela ficha do título.")
    return {"instrumento_id": int(instrumento_id),
            "assinado_por": quem.get("nome"), "numero": ins["numero"],
            "ano": ins["ano"]}


def assinado_do_titulo(con: sqlite3.Connection, titulo_id: int) -> bytes | None:
    """O `.p7s` do instrumento mais recente e ASSINADO do título. Só LÊ."""
    from pathlib import Path
    linha = con.execute(
        """SELECT d.caminho_assinado FROM pt_instrumentos i
             JOIN as_documentos d ON d.entidade=? AND d.entidade_id=i.id
            WHERE i.titulo_id=? AND d.caminho_assinado IS NOT NULL
            ORDER BY i.id DESC LIMIT 1""",
        (ENTIDADE_DA_ASSINATURA, int(titulo_id))).fetchone()
    if not linha or not linha[0] or not Path(linha[0]).exists():
        return None
    return Path(linha[0]).read_bytes()
