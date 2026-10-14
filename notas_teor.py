"""
Montagem do teor do ato notarial.

O QUE EU DESCOBRI LENDO OS 301 MODELOS IMPORTADOS
    Eles nao sao a procuracao inteira. Sao so a clausula de PODERES — comecam
    em "com amplos poderes para assinar contrato de compra de imovel..." e
    terminam ali. O comparecimento, a qualificacao das partes e o fecho o
    E-Oficio montava por fora, a partir do cadastro.

    Isso muda o desenho para melhor: a qualificacao nao precisa ser digitada,
    porque ja esta nas partes do ato, que por sua vez vieram da ficha de firma.
    O modelo entra so onde ele e insubstituivel — no que a procuracao autoriza.

A ESTRUTURA QUE ESTE MODULO MONTA
    1. epigrafe        LIVRO, FOLHA, natureza do ato
    2. comparecimento  "Saibam quantos este virem que, aos X dias..."
    3. qualificacao    uma parte por vez, na forma do art. 215, § 1º, do
                       Codigo Civil: nome, nacionalidade, estado civil,
                       profissao, documento e domicilio
    4. objeto          a clausula de poderes, que vem do modelo
    5. fecho           "Assim o disse, do que dou fe" e as assinaturas

O QUE ELE NAO FAZ
    Nao inventa clausula. O que o modelo nao disser, nao aparece; o que faltar
    na qualificacao aparece marcado, para o escrevente ver e completar. Texto
    de escritura montado por adivinhacao e defeito, nao comodidade.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime
from typing import Any

# A epigrafe e o fecho mudam conforme o ato. Testamento tem forma propria e
# nao entra aqui: e ato de forma vinculada, e montar por template seria
# temerario — o modulo devolve so a moldura e o tabeliao escreve.
ABERTURAS = {
    "PROCURACAO": ("SAIBAM quantos este público instrumento de procuração bastante "
                   "virem que, aos {data_extenso}, nesta cidade de {cidade}, "
                   "Estado {uf_extenso}, nesta Serventia Extrajudicial, perante mim, "
                   "Tabelião, compareceu como OUTORGANTE:"),
    "ESCRITURA": ("SAIBAM quantos este público instrumento virem que, aos "
                  "{data_extenso}, nesta cidade de {cidade}, Estado {uf_extenso}, "
                  "nesta Serventia Extrajudicial, perante mim, Tabelião, "
                  "compareceram as partes entre si justas e contratadas, a saber:"),
    "SUBSTABELECIMENTO": ("SAIBAM quantos este público instrumento de substabelecimento "
                          "virem que, aos {data_extenso}, nesta cidade de {cidade}, "
                          "Estado {uf_extenso}, perante mim, Tabelião, compareceu:"),
    "REVOGACAO": ("SAIBAM quantos este público instrumento de revogação virem que, "
                  "aos {data_extenso}, nesta cidade de {cidade}, Estado {uf_extenso}, "
                  "perante mim, Tabelião, compareceu:"),
    "ATA": ("ATA NOTARIAL. Aos {data_extenso}, nesta cidade de {cidade}, Estado "
            "{uf_extenso}, a pedido da parte adiante qualificada, eu, Tabelião, "
            "compareci e constatei os fatos que adiante narro:"),
}

FECHOS = {
    "PROCURACAO": ("E, de como assim o disse, do que dou fé, pediu-me e lhe lavrei "
                   "este instrumento, que lhe foi lido em voz alta, achou conforme, "
                   "aceitou e assina."),
    "ESCRITURA": ('Nada mais. O presente assento foi lido e achado conforme em todos os seus termos por todos comparecentes. Emolumentos e selo de fiscalização ao final do ato. Assinam o ato [ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]. Dou fé dos fatos constatados e dos documentos apresentados e após redigir, subscrever, assino em público e raso, encerrando o presente ato. Traslado emitido e entregue às partes após as assinaturas.'),
    "SUBSTABELECIMENTO": ("E, de como assim o disse, do que dou fé, pediu-me e lhe "
                          "lavrei este instrumento, que lhe foi lido, achou conforme "
                          "e assina."),
    "REVOGACAO": ("E, de como assim o disse, do que dou fé, pediu-me e lhe lavrei "
                  "este instrumento, que lhe foi lido, achou conforme e assina."),
    "ATA": ("Do que, para constar, lavrei a presente ata notarial, que vai por mim "
            "assinada. Dou fé."),
}

# O que falta na qualificacao aparece assim, e nao em branco: campo vazio passa
# despercebido na revisao, marcador nao.
def _falta(rotulo: str) -> str:
    return f"[{rotulo.upper()}]"


UF_EXTENSO = {
    "MA": "do Maranhão", "PI": "do Piauí", "TO": "do Tocantins",
    "PA": "do Pará", "CE": "do Ceará", "BA": "da Bahia", "GO": "de Goiás",
    "SP": "de São Paulo", "RJ": "do Rio de Janeiro", "MG": "de Minas Gerais",
    "DF": "do Distrito Federal",
}


def qualificar(parte: dict | Any) -> str:
    """A qualificação de uma parte, na forma do art. 215, § 1º, do Código Civil.

    Ordem consagrada: nome, nacionalidade, estado civil, profissão, documento
    e domicílio. O que faltar sai marcado entre colchetes.
    """
    p = dict(parte)
    nome = (p.get("nome") or "").strip().upper() or _falta("nome")
    pedacos = [f"<b>{nome}</b>"]

    if (p.get("tipo_pessoa") or "F").upper() == "J":
        doc = (p.get("documento") or "").strip()
        pedacos.append("pessoa jurídica de direito privado")
        pedacos.append(f"inscrita no CNPJ sob o nº {doc}" if doc
                       else f"inscrita no CNPJ sob o nº {_falta('cnpj')}")
        if p.get("endereco"):
            pedacos.append(f"com sede em {p['endereco']}")
        else:
            pedacos.append(f"com sede em {_falta('endereço')}")
        return ", ".join(pedacos)

    pedacos.append((p.get("nacionalidade") or "").strip().lower()
                   or _falta("nacionalidade"))
    pedacos.append((p.get("estado_civil") or "").strip().lower()
                   or _falta("estado civil"))
    pedacos.append((p.get("profissao") or "").strip().lower()
                   or _falta("profissão"))
    doc = (p.get("documento") or "").strip()
    pedacos.append(f"inscrito(a) no CPF sob o nº {doc}" if doc
                   else f"inscrito(a) no CPF sob o nº {_falta('cpf')}")
    endereco = (p.get("endereco") or "").strip()
    pedacos.append(f"residente e domiciliado(a) em {endereco}" if endereco
                   else f"residente e domiciliado(a) em {_falta('endereço')}")
    return ", ".join(pedacos)


def _escapar(texto: Any) -> str:
    return (str(texto or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))



# Marca gravada no teor quando o bloco de assinaturas foi montado por cá —
# o traslado e o termo do livro a usam para não imprimir as linhas duas
# vezes (uma no @@TEOR@@ e outra em @@ASSINATURAS@@). Texto literal, não
# comentário HTML: o conversor ODF descarta comentário.
MARCA_ASSINATURAS = "@@FIM_DO_TEOR_ANTES_DAS_ASSINATURAS@@"


def _norm_titulo(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


def _texto_paragrafo(paragrafo: str) -> str:
    t = re.sub(r"</?[biu]>", "", paragrafo)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _resto_apos_titulo(plain: str, titulo: str) -> str | None:
    """None se o parágrafo inteiro é o título; plain inalterado se não casar."""
    tit_n = _norm_titulo(titulo)
    plain_n = _norm_titulo(plain)
    if not tit_n or not plain_n:
        return plain
    if plain_n == tit_n:
        return None
    if not plain_n.startswith(tit_n):
        return plain
    for k in range(1, len(plain) + 1):
        if _norm_titulo(plain[:k]) == tit_n:
            resto = plain[k:].lstrip(" .-–—:;")
            return resto if resto.strip() else None
    return plain


def teor_sem_titulo_duplicado(teor: str | None, titulo: str | None) -> str:
    """Tira do início do teor o nome do ato que o cabeçalho já imprime.

    Minutas importadas ou editadas no LibreOffice costumam trazer uma linha
    «ESCRITURA PÚBLICA DE …» (sozinha ou colada antes do «Saibam quantos…»).
    O traslado, o termo do livro e o `.odt` de rascunho já repetem o título
    no cabeçalho — o mesmo defeito que `rc_certidao.teor_sem_titulo` evita
    nas certidões do RCPN.
    """
    import notas_teor_arquivo as TA

    if not teor or not str(titulo or "").strip():
        return teor or ""
    paragrafos = TA.paragrafos_do_html(teor)
    if not paragrafos:
        return teor
    plain0 = _texto_paragrafo(paragrafos[0])
    resto = _resto_apos_titulo(plain0, str(titulo))
    if resto == plain0:
        return teor
    if resto is None:
        paragrafos = paragrafos[1:]
    else:
        paragrafos[0] = resto
    return TA.html_dos_paragrafos(paragrafos) if paragrafos else ""


def teor_sem_titulos_duplicados(teor: str | None, titulos: list[str]) -> str:
    """Aplica `teor_sem_titulo_duplicado` para cada título, do mais longo ao curto."""
    vistos: set[str] = set()
    saida = teor or ""
    ordenados = sorted(
        (t.strip() for t in titulos if str(t or "").strip()),
        key=len,
        reverse=True,
    )
    for titulo in ordenados:
        chave = _norm_titulo(titulo)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida = teor_sem_titulo_duplicado(saida, titulo)
    return saida


CHAVE_ASSINANTES = "assinantes_do_ato_e_a_condicao_em_que_assinam"


def texto_dos_assinantes(partes: list) -> str:
    """Nome e condição de quem assina o ato, tirados da qualificação do formulário.

    Serve o campo `[ASSINANTES DO ATO E A CONDIÇÃO EM QUE ASSINAM]` do fecho
    das escrituras: o balcão já cadastrou as partes; não pede de novo. Ordem
    do formulário — principais e depois testemunhas. Quem lavrou assina no
    fecho próprio ("…assino em público e raso"), não nesta lista.
    """
    principais = [p for p in partes if not dict(p).get("testemunha")]
    testemunhas = [p for p in partes if dict(p).get("testemunha")]
    pedacos: list[str] = []
    for p in principais:
        d = dict(p)
        nome = (d.get("nome") or "").strip().upper()
        if not nome:
            continue
        qual = (d.get("qualificacao") or "").strip()
        pedacos.append(f"{nome}, {qual}" if qual else nome)
    for t in testemunhas:
        d = dict(t)
        nome = (d.get("nome") or "").strip().upper()
        if not nome:
            continue
        pedacos.append(f"{nome}, Testemunha")
    return "; ".join(pedacos)


def bloco_de_assinaturas(partes: list, lavrado_nome: str | None = None,
                         lavrado_titulo: str | None = None) -> str:
    """Linhas de assinatura do instrumento: comparecentes, testemunhas e lavrado.

    O FECHO DIZ QUE TODOS ASSINAM; estas linhas são onde a caneta passa. O
    traslado, o termo do livro e o teor montado por `montar` usam o MESMO
    bloco — 1º traslado e termo do livro ficam alinhados nas assinaturas.
    """
    principais = [p for p in partes if not dict(p).get("testemunha")]
    testemunhas = [p for p in partes if dict(p).get("testemunha")]
    blocos: list[str] = []

    def _linha(nome: str, condicao: str | None = None) -> None:
        blocos.append("<p></p>")
        blocos.append("<p></p>")
        blocos.append('<p align="center">_________________________________</p>')
        blocos.append(f'<p align="center">{_escapar(nome)}</p>')
        if condicao:
            blocos.append(f'<p align="center">{_escapar(condicao)}</p>')

    for p in principais:
        d = dict(p)
        nome = (d.get("nome") or "").strip().upper() or _falta("nome")
        qual = (d.get("qualificacao") or "").strip()
        _linha(nome, qual or None)

    for t in testemunhas:
        d = dict(t)
        nome = (d.get("nome") or "").strip().upper() or _falta("nome")
        _linha(nome, "Testemunha")

    quem = (lavrado_nome or "").strip()
    if quem:
        _linha(quem, (lavrado_titulo or "").strip() or None)
    elif not principais and not testemunhas:
        # Sem partes e sem lavrado: ainda assim deixa a linha do tabelião,
        # senão o papel sai sem onde assinar.
        _linha(_falta("quem lavrou"), None)

    return "\n".join(blocos)


def sem_bloco_de_assinaturas(teor: str | None) -> str:
    """O teor sem o bloco que `montar` acrescentou ao final. Só corta."""
    texto = teor or ""
    if MARCA_ASSINATURAS in texto:
        return texto.split(MARCA_ASSINATURAS, 1)[0].rstrip()
    return texto



def montar(tipo: str, partes: list, poderes: str | None,
           data_extenso: str, cidade: str = "", uf: str = "MA",
           objeto: str | None = None,
           lavrado_nome: str | None = None,
           lavrado_titulo: str | None = None) -> str:
    """Monta o teor completo em HTML.

    `poderes` e o corpo do modelo — a parte que o E-Oficio guardava e que aqui
    entra tal como esta. `objeto` substitui os poderes quando o ato nao usa
    modelo, para a escritura de teor livre.
    """
    abertura = ABERTURAS.get(tipo)
    if not abertura:
        # Testamento e testamento cerrado tem forma vinculada: nao se monta por
        # template. Devolve so a qualificacao, para o tabeliao construir em volta.
        blocos = ["<p><b>PARTES</b></p>"]
        blocos += [f"<p>{qualificar(p)}.</p>" for p in partes]
        return "\n".join(blocos)

    uf_extenso = UF_EXTENSO.get((uf or "").upper(), f"de {uf}")
    blocos = [f"<p>{abertura.format(data_extenso=data_extenso, cidade=cidade, uf_extenso=uf_extenso)}</p>"]

    principais = [p for p in partes if not dict(p).get("testemunha")]
    testemunhas = [p for p in partes if dict(p).get("testemunha")]

    if not principais:
        blocos.append(f"<p>{_falta('nenhuma parte cadastrada no ato')}</p>")
    for p in principais:
        d = dict(p)
        rotulo = (d.get("qualificacao") or "").strip().upper()
        texto = qualificar(d)
        blocos.append(f"<p>{texto}{f' — na qualidade de {rotulo}' if rotulo else ''}.</p>")

    corpo = (poderes or objeto or "").strip()
    if corpo:
        # O modelo ja vem em HTML da importacao; texto solto vira paragrafo.
        blocos.append(corpo if corpo.lstrip().startswith("<")
                      else f"<p>{_escapar(corpo)}</p>")
    else:
        blocos.append(f"<p>{_falta('objeto do ato — escolha um modelo ou escreva aqui')}</p>")

    if testemunhas:
        nomes = "; ".join((dict(t).get("nome") or "").strip().upper() for t in testemunhas)
        blocos.append(f"<p>Presentes as testemunhas: {nomes}.</p>")

    blocos.append(f"<p>{FECHOS.get(tipo, FECHOS['ESCRITURA'])}</p>")
    # AS LINHAS DE ASSINATURA — mesmo bloco do traslado (pedido 18/09/2026).
    # A marca separa o teor narrativo do bloco, para o traslado nao duplicar.
    blocos.append(MARCA_ASSINATURAS)
    blocos.append(bloco_de_assinaturas(
        partes, lavrado_nome=lavrado_nome, lavrado_titulo=lavrado_titulo))
    return "\n".join(blocos)


# A SEGUNDA METADE DO ATO — quem RECEBE (comprador, donatário, procurador).
# Achada de 07/09/2026: os modelos de `notas_modelos.py` usam
# `{{ outorgantes }}` e `{{ outorgados }}`, e nada no sistema os montava —
# a tela de "Preencher a partir do modelo" só troca `[CAMPO]`, `{ESCOLHA}` e
# `«SE»`, nunca Jinja. O ato sairia com as chaves duplas escritas por cima do
# nome das partes, no documento que a serventia assina.
#
# A REGRA E A QUALIFICAÇÃO QUE O ESCREVENTE JÁ DIGITOU, e não uma lista fechada
# de papéis: bater em uma destas palavras manda a parte para a segunda metade;
# o resto — vendedor, doador, outorgante, substabelecente, renunciante, ou
# parte sem qualificação — fica na primeira. Testemunha não entra em nenhuma
# das duas: nenhum destes modelos as cita dentro do corpo.
_SEGUNDA_PARTE = ("OUTORGADO", "COMPRADOR", "DONATARIO", "PROCURADOR")


def _sem_acento_maiusculo(texto) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(texto or "").upper())
    return "".join(c for c in s if not unicodedata.combining(c))


def partes_por_lado(partes: list) -> tuple[str, str]:
    """Monta `outorgantes` e `outorgados` para os modelos de `notas_modelos.py`.

    O QUE FALTAR FICA MARCADO, E NÃO EM BRANCO — a mesma regra de `_falta()`:
    lado sem parte nenhuma sairia sem ninguém notar, e quem confere o teor
    precisa ver que falta qualificar alguém, não uma lacuna muda.
    """
    primeira, segunda = [], []
    for p in partes:
        d = dict(p)
        if d.get("testemunha"):
            continue
        alvo = (segunda if any(x in _sem_acento_maiusculo(d.get("qualificacao"))
                               for x in _SEGUNDA_PARTE) else primeira)
        alvo.append(qualificar(d))
    outorgantes = ("; ".join(primeira) or
                   _falta("outorgante(s) — qualifique a parte no ato"))
    outorgados = ("; ".join(segunda) or
                  _falta("outorgado(s) — qualifique a parte no ato"))
    return outorgantes, outorgados


def testemunhas_qualificadas(partes: list) -> str:
    """Texto Jinja `{{ testemunhas }}` nos modelos de ata e testamento."""
    ts = [p for p in partes if dict(p).get("testemunha")]
    if not ts:
        return _falta("testemunha(s) — cadastre no ato se houver")
    return "; ".join(qualificar(t) for t in ts)


def contexto_jinja_partes(partes: list) -> dict[str, str]:
    """Variáveis Jinja comuns aos modelos de `notas_modelos.py`."""
    outorgantes, outorgados = partes_por_lado(partes)
    return {
        "outorgantes": outorgantes,
        "outorgados": outorgados,
        "testemunhas": testemunhas_qualificadas(partes),
    }


def pendencias_da_qualificacao(partes: list) -> list[str]:
    """Diz quem está incompleto, com nome, antes de o ato ser lavrado."""
    faltas = []
    for p in partes:
        d = dict(p)
        if d.get("testemunha"):
            continue
        exigidos = ("documento",) if (d.get("tipo_pessoa") or "F").upper() == "J" else \
                   ("documento", "nacionalidade", "estado_civil", "profissao", "endereco")
        vazios = [c.replace("_", " ") for c in exigidos if not str(d.get(c) or "").strip()]
        if vazios:
            faltas.append(f"{d.get('nome') or 'parte sem nome'}: {', '.join(vazios)}")
    return faltas


def valores_campos_data_lavratura(quando: datetime) -> dict[str, str]:
    """Campos `[DIA POR EXTENSO]` etc. dos modelos SISTEMA, para a data do selo."""
    from notas_livro import por_extenso
    from ri_web import MESES

    d = quando.date()
    h, m = quando.hour, quando.minute
    hora_alg = str(h) if m == 0 else f"{h:02d}:{m:02d}"
    hora_ext = por_extenso(h)
    if m:
        hora_ext = f"{hora_ext} e {por_extenso(m)}"
    return {
        "dia_por_extenso": por_extenso(d.day),
        "dia_em_algarismos": str(d.day),
        "mes_por_extenso": MESES[d.month - 1],
        "ano_por_extenso": por_extenso(d.year),
        "ano_em_algarismos": str(d.year),
        "hora_por_extenso": hora_ext,
        "hora_em_algarismos": hora_alg,
    }


def atualizar_teor_para_data_de_selo(
    con: sqlite3.Connection,
    ato_id: int,
    *,
    quando: datetime,
    sv: dict,
    lavrado_nome: str,
    lavrado_titulo: str,
) -> dict[str, Any]:
    """Alinha `data`, `hora` e datas no teor com o dia em que o selo sai.

    Relato #116: o teor costuma ser montado dias antes; traslado/termo já usam
    «hoje» na exportação, mas o HTML gravado no ato ficava com a data antiga.
    """
    from jinja2.sandbox import SandboxedEnvironment
    from ri_modelos_atos import preencher as preencher_modelo
    from ri_web import data_por_extenso

    row = con.execute("SELECT * FROM nt_atos WHERE id=?", (int(ato_id),)).fetchone()
    if not row:
        return {"ok": False, "motivo": "ato inexistente"}
    ato = dict(row)
    data_iso = quando.date().isoformat()
    hora = quando.strftime("%H:%M")
    teor = ato.get("teor") or ""
    teor_novo: str | None = None
    modelo_valores_json: str | None = None

    partes = [
        dict(p)
        for p in con.execute(
            "SELECT * FROM nt_ato_partes WHERE ato_id=? ORDER BY testemunha, ordem",
            (int(ato_id),),
        ).fetchall()
    ]
    modelo = None
    if ato.get("modelo_codigo"):
        m = con.execute(
            "SELECT * FROM nt_modelos WHERE codigo=?", (ato["modelo_codigo"],)
        ).fetchone()
        if m:
            modelo = dict(m)

    if modelo and (modelo.get("origem") or "") == "SISTEMA":
        try:
            valores = json.loads(ato.get("modelo_valores") or "{}") or {}
        except (TypeError, ValueError):
            valores = {}
        valores.update(valores_campos_data_lavratura(quando))
        env = SandboxedEnvironment(autoescape=False)
        ctx = contexto_jinja_partes(partes)
        corpo_jinja = env.from_string(modelo["corpo"]).render(
            sv=sv,
            lavrado_nome=lavrado_nome,
            lavrado_titulo=lavrado_titulo,
            **ctx,
        )
        teor_novo = preencher_modelo({"corpo": corpo_jinja}, valores)
        modelo_valores_json = json.dumps(valores, ensure_ascii=False)
    elif modelo and (modelo.get("origem") or "") != "SISTEMA":
        teor_novo = montar(
            ato["tipo"],
            partes,
            modelo.get("corpo"),
            data_extenso=data_por_extenso(quando.date()),
            cidade=sv.get("ri_cidade", ""),
            uf=sv.get("ri_uf", "MA"),
            lavrado_nome=lavrado_nome,
            lavrado_titulo=lavrado_titulo,
        )
    elif ato.get("data") and data_iso != ato["data"] and teor.strip():
        try:
            velho = data_por_extenso(date.fromisoformat(ato["data"]))
            novo = data_por_extenso(quando.date())
            if velho in teor:
                teor_novo = teor.replace(velho, novo)
        except ValueError:
            pass

    if teor_novo is None and data_iso == (ato.get("data") or ""):
        return {"ok": True, "alterou_teor": False, "data": data_iso}

    if modelo_valores_json is not None:
        con.execute(
            """UPDATE nt_atos SET data=?, hora=?, teor=?, modelo_valores=?
               WHERE id=?""",
            (data_iso, hora, teor_novo, modelo_valores_json, int(ato_id)),
        )
    elif teor_novo is not None:
        con.execute(
            "UPDATE nt_atos SET data=?, hora=?, teor=? WHERE id=?",
            (data_iso, hora, teor_novo, int(ato_id)),
        )
    else:
        con.execute(
            "UPDATE nt_atos SET data=?, hora=? WHERE id=?",
            (data_iso, hora, int(ato_id)),
        )
    return {"ok": True, "alterou_teor": teor_novo is not None, "data": data_iso}
