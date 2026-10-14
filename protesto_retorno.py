"""
O retorno a CRA — o arquivo que devolve ao apresentante o que a casa fez.

O QUE FALTAVA
    `protesto_arquivo` ja lia e ja ESCREVIA o arquivo de 600 posicoes, e a
    prova disso e o ida e volta: dos 572 arquivos reais, 558 voltam identicos
    byte a byte. O que faltava era a ponte — ligar o `montar_retorno()` ao que
    foi LAVRADO nesta casa, em vez de a um arquivo que se acabou de ler.

    93% dos titulos entram pela CRA. Sem o retorno, eles entram e nunca
    voltam: a Central fica sem saber o que aconteceu com o titulo que mandou.

A OCORRENCIA SAI DO ATO, e ela foi medida
    | Ato lavrado   | Ocorrencia | Onde se mediu |
    |---------------|-----------|---------------|
    | PROTESTO      | `C`       | 287 dos 383 registros de retorno REAIS, e 1.106 dos 1.107 `C` do acervo estao com `snProtestado` e com livro e folha |
    | PAGAMENTO     | `1`       | "Pago" no contrato da CRA; 133 titulos do acervo, todos com `strTipoPG` de pagamento ('12' e '0') |
    | DESISTENCIA   | `3`       | "Retirado" no contrato; 46 do acervo, todos com `strTipoPG` '2' e '4' |
    | CANCELAMENTO  | `A`       | "Protesto cancelado" no contrato |

    O `C` NAO ESTA NO CONTRATO OFICIAL, e sai assim mesmo — porque e o que
    esta casa mandou e a Central aceitou, 287 vezes em 383. E a regra do
    oficial, de 24/08/2026: na duvida, faca como o E-Oficio fazia.

O QUE O RETORNO LEVA DE CADA TITULO
    Nosso numero, valor, saldo, protocolo, a ocorrencia, a data de entrada
    (a do apontamento) e a data da ocorrencia (a do ato). O resto do registro
    vem em branco, e isso e medido: nos 383 reais, especie, cedente e devedor
    estao sempre vazios — o apresentante ja sabe o que mandou.

NADA SAI DUAS VEZES
    Ato informado ganha `retorno_id`, e a lista de pendentes so mostra o que
    ainda nao foi. Mandar o mesmo protesto duas vezes faz a Central registrar
    dois — e desfazer isso e trabalho de carta.

O ARQUIVO INTEIRO FICA GRAVADO
    Nao so o nome: o que saiu daqui e o que a Central recebeu, e quando ela
    reclamar de um titulo e este teor que se le. Mesma razao do teor congelado
    da certidao.

FUNDAMENTO
    Lei 9.492/1997. Layout medido em `LAYOUT_RETORNO_MEDIDO.md`, sobre 443
    retornos reais de dois lotes.
"""
from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

import protesto_arquivo as PA

# Que ocorrencia cada ato desta casa vira no arquivo. Ver o cabecalho.
#
#   CONFERIDO CONTRA OS ARQUIVOS DE 2026 em 31/08/2026, e as quatro batem:
#   C sai 45 vezes, 1 sai 11, 3 sai 4 e A sai 2. (O `2` do contrato tambem
#   aparece, 2 vezes — e o codigo oficial de «protestado», que esta casa
#   escreve como `C`; os dois convivem nos arquivos reais.)
OCORRENCIA_DO_ATO: dict[str, str] = {
    "PROTESTO": "C",
    "PAGAMENTO": "1",
    "DESISTENCIA": "3",
    "CANCELAMENTO": "A",
}

# O ANDAMENTO LEVA SEMPRE `0` — APONTAMENTO —, e nao a ocorrencia do ato.
#
#   MEDIDO em 31/08/2026 nos 25 andamentos que esta casa mandou em 2026:
#   **`0` em 103 de 103 registros**, sem uma excecao.
#
#   O SISTEMA COPIAVA A DO RETORNO, e o comentario de `gerar` dizia que era «o
#   que se quer». Metade daquilo estava certa — os dois arquivos levam quase os
#   mesmos titulos (42 dos 47 aparecem nos dois) —, e a outra metade nao: e o
#   mesmo movimento contado de outro jeito, e o «outro jeito» inclui a
#   ocorrencia.
#
#   O ESTRAGO QUE ISSO EVITA: um andamento dizendo `C` afirma um PROTESTO que o
#   retorno do mesmo dia ja afirmou. A Central registraria o mesmo protesto
#   duas vezes, por dois arquivos — que e o estrago que a marcacao dos atos
#   existe para impedir, entrando pela porta do lado.
OCORRENCIA_DO_ANDAMENTO = "0"

# Os atos que a CRA precisa saber. Apontamento NAO entra: a Central ja sabe
# que o titulo chegou — foi ela que o mandou — e o apontamento e o recibo
# disso, que vai na CONFIRMACAO e nao no retorno.
ATOS_QUE_VOLTAM = tuple(OCORRENCIA_DO_ATO)

# O QUE VAI EM CADA ARQUIVO, e sao conjuntos DIFERENTES.
#
# Correcao do oficial em 31/08/2026: «sempre que recebe remessa, precisa gerar
# o andamento para atualizar a CRA sobre o andamento». Ate aqui o andamento
# saia com OS MESMOS ATOS do retorno — dizendo «Apontamento» sobre um titulo
# que acabava de ser protestado.
#
# Medido nos 125 arquivos de 2026: o andamento leva `0` (Apontamento) em 103
# de 103 linhas; **38 dos 39** titulos recebidos por remessa aparecem num
# andamento; ele vem na data da remessa ou depois em **38 de 38**, e na data
# do retorno ou antes em **42 de 42**. A ordem e remessa -> andamento ->
# retorno.
ATOS_POR_TIPO_DE_ARQUIVO: dict[str, tuple[str, ...]] = {
    # O retorno conta O QUE ACONTECEU com o titulo.
    "SDTBFORTP": ATOS_QUE_VOLTAM,
    # O andamento conta QUE ELE ENTROU.
    "SDTBFOAND": ("APONTAMENTO",),
}


class RetornoError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcao."""


def _data_arquivo(data: Any) -> str:
    """`2026-08-25` -> `25082026`, que e como o arquivo escreve data."""
    s = str(data or "")[:10]
    if len(s) == 10 and s[4] == "-":
        return f"{s[8:10]}{s[5:7]}{s[:4]}"
    return s


# ---------------------------------------------------------------- pendentes


def pendentes(con: sqlite3.Connection, *,
              apresentante_codigo: str | None = None,
              tipo: str = "SDTBFORTP") -> list[dict]:
    """Os atos lavrados que a CRA ainda nao sabe. So LE.

    So entra titulo que VEIO DA CRA — o digitado no balcao nao tem para onde
    voltar. E so ato do tipo que AQUELE ARQUIVO carrega.

    `tipo` NAO E DETALHE: o retorno leva os atos finais (protesto, pagamento,
    desistencia, cancelamento) e o andamento leva **o apontamento**. Ate
    31/08/2026 os dois liam a mesma lista, e o andamento saia dizendo
    «Apontamento» sobre um titulo que acabara de ser protestado. Ver
    `ATOS_POR_TIPO_DE_ARQUIVO`, com a medicao ao lado.
    """
    quais = ATOS_POR_TIPO_DE_ARQUIVO.get(str(tipo), ATOS_QUE_VOLTAM)
    onde = ["a.retorno_id IS NULL",
            f"a.tipo IN ({','.join('?' * len(quais))})",
            "t.origem IN ('CRA', 'CENPROT')"]
    params: list[Any] = list(quais)
    if apresentante_codigo:
        onde.append("t.apresentante_codigo = ?")
        params.append(str(apresentante_codigo).strip())

    linhas = con.execute(
        f"""SELECT a.id ato_id, a.tipo, a.data_ato, t.id titulo_id,
                   t.numero_titulo, t.nosso_numero, t.valor_centavos,
                   t.saldo_centavos, t.protocolo, t.apresentante_codigo,
                   t.apresentante_nome, t.situacao,
                   (SELECT data_ato FROM pt_atos e
                     WHERE e.titulo_id = t.id AND e.tipo = 'APONTAMENTO'
                     ORDER BY e.id LIMIT 1) data_entrada
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
             WHERE {' AND '.join(onde)}
             ORDER BY t.apresentante_codigo, a.data_ato, a.id""",
        params).fetchall()
    return [dict(r) for r in linhas]


def apresentantes_pendentes(con: sqlite3.Connection) -> list[dict]:
    """Quantos atos esperam retorno, por apresentante. So LE."""
    grupos: dict[str, dict] = {}
    for a in pendentes(con):
        codigo = (a["apresentante_codigo"] or "").strip()
        g = grupos.setdefault(codigo, {
            "apresentante_codigo": codigo,
            "apresentante_nome": a["apresentante_nome"],
            "atos": 0,
            "marca": PA.marca_do_apresentante(codigo) if codigo else None,
        })
        g["atos"] += 1
    return sorted(grupos.values(), key=lambda g: -g["atos"])


# ------------------------------------------------------------------ montar


def _titulo_completo(con: sqlite3.Connection, a: dict) -> dict:
    """Os campos da REMESSA do titulo, para o andamento e a confirmacao.

    O andamento nao tem layout proprio: e o da remessa mais o bloco do
    retorno. Por isso ele leva o titulo inteiro — cedente, devedor, endereco,
    especie —, e nao so a chave como o retorno.
    """
    t = con.execute(
        """SELECT * FROM pt_titulos WHERE id=?""", (int(a["titulo_id"]),)
        ).fetchone()
    d = con.execute(
        """SELECT * FROM pt_devedores WHERE titulo_id=? ORDER BY id LIMIT 1""",
        (int(a["titulo_id"]),)).fetchone()
    devedor = dict(d) if d else {}
    return {
        "cedente_nome": t["cedente_nome"] or "",
        "cedente_documento": t["cedente_documento"] or "",
        "cedente_endereco": t["cedente_endereco"] or "",
        "cedente_cep": t["cedente_cep"] or "",
        "cedente_cidade": t["cedente_cidade"] or "",
        "cedente_uf": t["cedente_uf"] or "",
        "especie": t["especie"] or "",
        "numero_do_titulo": t["numero_titulo"] or "",
        "data_de_emissao": _data_arquivo(t["data_emissao"]),
        "data_de_vencimento": _data_arquivo(t["data_vencimento"]),
        "tipo_de_moeda": t["tipo_moeda"] or "1",
        "praca_de_protesto": t["praca_protesto"] or "",
        "tipo_de_endosso": t["tipo_endosso"] or "",
        "aceite": t["aceite"] or "",
        "motivo_do_protesto": t["motivo_protesto"] or "",
        "devedor_nome": devedor.get("nome") or "",
        "devedor_tipo_de_documento": ("002" if devedor.get("documento_tipo")
                                      == "CNPJ" else "001"),
        "devedor_documento": devedor.get("documento_numero") or "",
        "devedor_endereco": devedor.get("endereco") or "",
        "devedor_cep": devedor.get("cep") or "",
        "devedor_cidade": devedor.get("cidade") or "",
        "devedor_uf": devedor.get("uf") or "",
        "devedor_bairro": devedor.get("bairro") or "",
    }


def montar(con: sqlite3.Connection, *, apresentante_codigo: str, dia: str,
           marca: str | None = None, numero_da_remessa: Any = 1,
           tipo: str = "SDTBFORTP") -> dict:
    """Monta o arquivo de saida do apresentante, com o que falta informar.

    So LE — quem grava e `gerar()`. Devolve o arquivo escrito e os atos que
    entraram nele, para a tela mostrar antes de mandar.

    `tipo` escolhe entre o RETORNO (so a chave e o resultado) e o ANDAMENTO
    (o titulo inteiro, no layout da remessa mais o bloco do retorno).
    """
    codigo = str(apresentante_codigo or "").strip()
    if not codigo:
        raise RetornoError(
            "Informe o apresentante: o retorno volta para quem mandou, e sem o "
            "código dele não há nem cabeçalho nem a letra da posição 566.")
    atos = pendentes(con, apresentante_codigo=codigo, tipo=tipo)
    if not atos:
        qual = ("apontamento" if tipo == "SDTBFOAND" else "ato")
        raise RetornoError(
            f"Não há {qual} novo para informar ao apresentante {codigo}. Tudo "
            f"o que foi lavrado para ele já entrou num arquivo anterior.")

    faltando = [a for a in atos if not (a["protocolo"] or "").strip()]
    if faltando:
        raise RetornoError(
            f"{len(faltando)} título(s) deste apresentante estão sem número de "
            f"protocolo, e ele é o que volta na posição 448 do arquivo. Os "
            f"títulos vindos do acervo antigo podem estar assim; confira o "
            f"protocolo no livro e informe antes de gerar o retorno.")

    titulos = []
    for a in atos:
        extra = (_titulo_completo(con, a) if tipo != "SDTBFORTP" else {})
        titulos.append({
            **extra,
            "codigo_do_apresentante": codigo,
            "identificacao_do_apresentante": a["apresentante_nome"] or "",
            "nosso_numero": a["nosso_numero"] or "",
            "valor_do_titulo": int(a["valor_centavos"] or 0),
            "saldo_a_protestar": int(a["saldo_centavos"] or 0),
            "protocolo": (a["protocolo"] or "").strip(),
            # O ANDAMENTO DIZ «APONTADO»; O RETORNO DIZ O QUE ACONTECEU.
            #
            # Agora as duas coisas se sustentam sozinhas: o andamento so leva
            # ato de APONTAMENTO, e a ocorrencia dele e `0` — que e o que o
            # contrato chama de «Apontamento» e o que esta casa mandou em 103
            # de 103 linhas. Ate 31/08/2026 este `if` era a UNICA coisa que
            # separava os dois arquivos, e os titulos eram os mesmos.
            "ocorrencia": (OCORRENCIA_DO_ANDAMENTO if tipo == "SDTBFOAND"
                           else OCORRENCIA_DO_ATO[a["tipo"]]),
            "data_entrada": _data_arquivo(a["data_entrada"] or a["data_ato"]),
            "data_ocorrencia": _data_arquivo(a["data_ato"]),
        })

    # O NOME DO APRESENTANTE VEM DO CABEÇALHO DA REMESSA — correção de
    # 13/10/2026. `pt_titulos.apresentante_nome` guarda o campo 005/019 do
    # registro do título («Agência / Código do Cedente», no layout da P21), e
    # o cabeçalho do andamento saía com `h03 = 537681502381151` no lugar de
    # «BRADESCO SA» (medido no ensaio da homologação). O título continua
    # levando aquele código no lugar dele; só o cabeçalho e o rodapé mudam.
    linha = con.execute(
        """SELECT apresentante_nome FROM pt_remessas
            WHERE apresentante_codigo = ? AND COALESCE(apresentante_nome, '') <> ''
            ORDER BY id DESC LIMIT 1""", (codigo,)).fetchone()
    nome = ((linha[0] if linha else "") or atos[0]["apresentante_nome"] or "").strip()
    monta = {"SDTBFORTP": PA.montar_retorno,
             "SDTBFOAND": PA.montar_andamento,
             "SDTBFOCRT": PA.montar_confirmacao}.get(tipo)
    if not monta:
        raise RetornoError(
            f"Tipo de arquivo desconhecido: {tipo!r}. Os que esta casa manda "
            f"são o retorno (SDTBFORTP), o andamento (SDTBFOAND) e a "
            f"confirmação (SDTBFOCRT).")
    arquivo = monta(
        apresentante_codigo=codigo, apresentante_nome=nome,
        dia=_data_arquivo(dia), titulos=titulos,
        numero_da_remessa=numero_da_remessa, marca=marca)
    conteudo = _como_o_eoficio_mandava(
        con, PA.escrever(arquivo, renumerar_sequencial=True), tipo, codigo,
        len(titulos))
    return {
        "tipo": tipo,
        "apresentante_codigo": codigo,
        "apresentante_nome": nome,
        "dia": str(dia)[:10],
        "marca": (titulos[0].get("reservado_566") if titulos else None),
        "atos": atos,
        "arquivo": arquivo,
        "conteudo": conteudo,
        "soma_centavos": sum(int(t["saldo_a_protestar"]) for t in titulos),
        "nome_arquivo": nome_do_arquivo(tipo, codigo, dia, numero_da_remessa, con=con),
    }


def _como_o_eoficio_mandava(con: sqlite3.Connection, conteudo: str, tipo: str,
                            codigo: str, quantos: int) -> str:
    """Preenche o que o escritor deixa em branco, como o E-Ofício preenchia. SÓ CALCULA.

    MEDIDO EM 13/10/2026 nos 67 lotes de retorno de 2026 da pasta da CRA (os 67
    iguais) e nos 53 andamentos, depois que a CRA de homologação respondeu
    «9999» ao retorno do sistema — que saía com:
      - cabeçalho 68–100 em branco: o E-Ofício manda h09 = quantos títulos
        (no andamento, «0000» em 49 de 53), h10–h12 em zeros, h13 = a agência
        centralizadora da remessa (ou «000000») e h14+h15 = «043» + o IBGE;
      - rodapé 58–60 em branco: a soma é de 18 posições (58–75, layout da P21)
        e o leitor desta casa a parte em `reservado_58` + 15 — escrito em
        branco, o XML sem espaços levava um número de 15 dígitos;
      - título 508–517 (t40) e 568–577 (t50) em branco: zeros em 87 de 87.
    O leitor e o escritor (`protesto_arquivo`) não mudam: o ajuste é do que SAI.
    """
    ultima = con.execute(
        """SELECT conteudo FROM pt_remessas WHERE apresentante_codigo = ?
            ORDER BY id DESC LIMIT 1""", (codigo,)).fetchone()
    cab_remessa = ((ultima[0] if ultima else "") or "").replace("\r", "").split("\n")[0]
    agencia = cab_remessa[83:89] if len(cab_remessa) == 600 else ""
    portador = cab_remessa[89:100] if len(cab_remessa) == 600 else ""
    if not portador.strip():
        # A régua da casa (ri_ctp): `ri_codigo_ibge`, ou UF + município.
        from ri_ctp import codigo_ibge_da_casa

        def _config(chave, padrao=""):
            try:
                r = con.execute("SELECT value FROM settings WHERE key=?",
                                (chave,)).fetchone()
            except sqlite3.Error:
                r = None
            return (r[0] if r else None) or padrao
        portador = "043" + codigo_ibge_da_casa(_config)
    h09 = "0000" if tipo == "SDTBFOAND" else f"{quantos:04d}"
    saida = []
    for linha in [x for x in conteudo.replace("\r", "").split("\n") if x.strip()]:
        if linha[:1] == "0":
            linha = (linha[:67] + h09 + "0" * 12 + (agencia.strip() or "000000").ljust(6)
                     + portador.ljust(11)[:11] + linha[100:])
        elif linha[:1] == "1":
            for a, b in ((507, 517), (567, 577)):
                # NO ANDAMENTO, NENHUM DOS DOIS: t40 é «não preencher» (layout da
                # P21), e 546–596 o leitor da casa lê como UM campo de texto —
                # zeros em 568–577 se deslocam no ida e volta
                # (test_o_que_a_casa_escreve_a_casa_le_de_volta). O E-Ofício
                # mandava zeros ali (170 de 170): A CONFERIR quando o andamento
                # tiver caminho de envio e o leitor partir aquele bloco.
                if tipo == "SDTBFOAND":
                    continue
                if not linha[a:b].strip():
                    linha = linha[:a] + "0" * (b - a) + linha[b:]
        elif linha[:1] == "9" and not linha[57:60].strip():
            linha = linha[:57] + "000" + linha[60:]
        saida.append(linha)
    return "\r\n".join(saida) + "\r\n"


#: A letra do nome FEBRABAN de cada arquivo que sai.
LETRA_DO_ARQUIVO = {"SDTBFOCRT": "C", "SDTBFORTP": "R", "SDTBFOAND": "M"}


def nome_do_arquivo(tipo: str, apresentante_codigo: str, dia: str,
                    numero_da_remessa: Any = 1, *, con: sqlite3.Connection | None = None,
                    sequencia: int | None = None) -> str:
    """O nome FEBRABAN: `<letra><apresentante><DDMM>.<AA><sequência>`.

    CORREÇÃO DE 13/10/2026. Até aqui o nome era `<tipo>-<apresentante>-<AAAAMMDD>-
    <remessa>.txt`, e este comentário dizia que «o E-Ofício nomeava de outro jeito
    em cada pasta, e não há padrão a imitar». HÁ, e a CRA o exige: medido nos 125
    arquivos de 2026 da pasta `8. CRA` (C9871007.261, M3410408.261, R1LV1809.261…),
    e é o que o manual da CRA21 e o layout do andamento da P21 descrevem. Nome fora
    dele a CRA recusa (código 0002, medido em 12/09); com ele, a confirmação
    `C2371609.263` voltou «0000» na homologação em 13/10/2026.

    `dia` é a data que o nome carrega: a da REMESSA na confirmação (a confirmação
    de `B2371609.263` é `C2371609.263`) e a do envio no andamento e no retorno.
    A sequência conta os arquivos do mesmo tipo, apresentante e dia que já
    existem — o terceiro lote do Bradesco de 16/09 é `.263`. `numero_da_remessa`
    fica na assinatura pelos chamadores antigos e não entra no nome.
    """
    letra = LETRA_DO_ARQUIVO.get(str(tipo or "").strip())
    if not letra:
        raise RetornoError(f"Tipo de arquivo desconhecido para nomear: {tipo!r}.")
    d = str(dia)[:10]
    base = f"{letra}{str(apresentante_codigo).strip()}{d[8:10]}{d[5:7]}.{d[2:4]}"
    if sequencia is None:
        sequencia = 1
        if con is not None:
            sequencia += con.execute(
                "SELECT COUNT(*) FROM pt_retornos WHERE nome_arquivo LIKE ?",
                (base + "_",)).fetchone()[0]
    if not 1 <= int(sequencia) <= 9:
        raise RetornoError(
            f"Já há {int(sequencia) - 1} arquivos «{base}?» — o nome FEBRABAN só "
            f"tem um dígito de sequência. Confira na Central antes de gerar outro.")
    return f"{base}{int(sequencia)}"


def hash_retorno(conteudo: str) -> str:
    """Impressao digital do arquivo que saiu."""
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ gerar


def gerar(con: sqlite3.Connection, *, apresentante_codigo: str, dia: str,
          agora: str, marca: str | None = None, numero_da_remessa: Any = 1,
          usuario: str | None = None,
          tipos: tuple[str, ...] = ("SDTBFORTP", "SDTBFOAND")) -> dict:
    """Gera o RETORNO e o ANDAMENTO e marca os atos de cada um. ESCREVE.

    OS DOIS SAEM JUNTOS, E ISSO E REGRA DA CASA. O roteiro do protesto que o
    oficial trouxe da serventia em que trabalhou diz, em maiuscula: "SEMPRE
    QUE GERAR RETORNO (FINAL), GERAR ANDAMENTO".

    E O ANDAMENTO SAI TAMBEM AO RECEBER A REMESSA — correcao do oficial em
    31/08/2026: *«sempre que recebe remessa, precisa gerar o andamento para
    atualizar a CRA sobre o andamento»*. Para isso serve `tipos`: a tela da
    remessa pede so `("SDTBFOAND",)`.

    CADA ARQUIVO LEVA OS SEUS ATOS, e ate 31/08/2026 nao era assim: os dois
    saiam do mesmo conjunto, e o andamento dizia «Apontamento» sobre um titulo
    que acabara de ser protestado. Agora o retorno leva os atos finais e o
    andamento leva os apontamentos. Ver `ATOS_POR_TIPO_DE_ARQUIVO`.

    A MARCACAO E O QUE IMPEDE MANDAR DUAS VEZES, e agora ela e DE CADA UM.
    Sao atos diferentes — o APONTAMENTO vai no andamento, o PROTESTO vai no
    retorno —, e um nao marca o outro. Sem marcacao, o mesmo protesto sai
    amanha outra vez e a Central registra dois; desfazer isso e trabalho de
    carta.

    UM ARQUIVO SEM CONTEUDO NAO DERRUBA O OUTRO. Ha dia em que chega remessa e
    nao se lavra ato final nenhum — e ha dia em que e o contrario. Recusar os
    dois porque um esta vazio faria o balcao deixar de mandar o que tem.
    """
    def grava(montado: dict, par_id: int | None) -> int:
        conteudo = montado["conteudo"]
        cur = con.execute(
            """INSERT INTO pt_retornos(tipo, par_id, apresentante_codigo,
                   apresentante_nome, dia, numero_da_remessa, marca, titulos,
                   soma_centavos, nome_arquivo, conteudo, hash_arquivo,
                   gerado_em, gerado_por)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (montado["tipo"], par_id, montado["apresentante_codigo"],
             montado["apresentante_nome"], montado["dia"],
             int(numero_da_remessa or 1), montado["marca"],
             len(montado["atos"]), montado["soma_centavos"],
             montado["nome_arquivo"], conteudo, hash_retorno(conteudo), agora,
             usuario))
        return int(cur.lastrowid)

    feitos: dict[str, dict] = {}
    recusas: dict[str, str] = {}
    for qual in tipos:
        try:
            feitos[qual] = montar(con,
                                  apresentante_codigo=apresentante_codigo,
                                  dia=dia, marca=marca,
                                  numero_da_remessa=numero_da_remessa,
                                  tipo=qual)
        except RetornoError as erro:
            # Vazio nao e erro: e o dia em que nao havia aquilo para informar.
            # Guarda-se o motivo para a tela contar, em vez de calar.
            recusas[qual] = str(erro)

    if not feitos:
        raise RetornoError(" ".join(recusas.values()) or
                           "Não há nada a informar a este apresentante.")

    retorno_montado = feitos.get("SDTBFORTP")
    andamento_montado = feitos.get("SDTBFOAND")
    retorno_id = grava(retorno_montado, None) if retorno_montado else None
    andamento_id = (grava(andamento_montado, retorno_id)
                    if andamento_montado else None)
    if retorno_id and andamento_id:
        con.execute("UPDATE pt_retornos SET par_id=? WHERE id=?",
                    (andamento_id, retorno_id))

    # A marcacao vem por ULTIMO: enquanto ela nao acontece, `montar` continua
    # achando os mesmos atos — e e assim que o andamento sai com os mesmos
    # TITULOS do retorno, que e o que se quer.
    #
    #   MESMOS TITULOS, OCORRENCIA DIFERENTE — correcao de 31/08/2026. Este
    #   comentario dizia so «os mesmos», e o codigo copiava tambem a
    #   ocorrencia: o andamento saia dizendo `C`, `1`, `3` ou `A`. Medido nos
    #   arquivos reais, ele leva `0` (Apontamento) em 103 de 103.
    # A MARCACAO VEM POR ULTIMO, e agora e de CADA arquivo: enquanto ela nao
    # acontece, `montar` continua achando os mesmos atos — e e por isso que os
    # dois se montam antes de qualquer `UPDATE`.
    for montado, quem in ((retorno_montado, retorno_id),
                          (andamento_montado, andamento_id)):
        if not montado:
            continue
        for a in montado["atos"]:
            con.execute("UPDATE pt_atos SET retorno_id=? WHERE id=?",
                        (quem, int(a["ato_id"])))

    principal = retorno_montado or andamento_montado
    return {**principal, "retorno_id": retorno_id,
            "andamento_id": andamento_id,
            "retorno": retorno_montado,
            "andamento": andamento_montado,
            "recusas": recusas,
            "hash": hash_retorno(principal["conteudo"])}


def gerar_andamento(con: sqlite3.Connection, *, apresentante_codigo: str,
                    dia: str, agora: str, marca: str | None = None,
                    numero_da_remessa: Any = 1,
                    usuario: str | None = None) -> dict:
    """So o ANDAMENTO — o aviso de que os titulos entraram e foram apontados.

    Pedido do oficial em 31/08/2026: *«sempre que recebe remessa, precisa
    gerar o andamento para atualizar a CRA sobre o andamento»*.

    Ate aqui o andamento so nascia preso ao retorno, e o momento em que ele
    existe para ser mandado — logo depois do apontamento — nao tinha por onde.
    Medido: **38 dos 39** titulos recebidos por remessa aparecem num andamento,
    e ele vem na data da remessa ou depois em **38 de 38**.
    """
    return gerar(con, apresentante_codigo=apresentante_codigo, dia=dia,
                 agora=agora, marca=marca,
                 numero_da_remessa=numero_da_remessa, usuario=usuario,
                 tipos=("SDTBFOAND",))


# --------------------------------------------------------------- consultas


def retorno(con: sqlite3.Connection, retorno_id: int) -> sqlite3.Row | None:
    """O retorno gerado, com o arquivo inteiro. So LE."""
    return con.execute("SELECT * FROM pt_retornos WHERE id=?",
                       (int(retorno_id),)).fetchone()


def listar(con: sqlite3.Connection, limite: int = 100) -> list[sqlite3.Row]:
    """Os retornos gerados, do mais novo para o mais velho. So LE."""
    return list(con.execute(
        """SELECT id, tipo, par_id, apresentante_codigo, apresentante_nome,
                  dia, numero_da_remessa, titulos, soma_centavos, nome_arquivo,
                  hash_arquivo, gerado_em, gerado_por
             FROM pt_retornos ORDER BY id DESC LIMIT ?""", (int(limite),)))


def atos_do_retorno(con: sqlite3.Connection, retorno_id: int) -> list[dict]:
    """Que atos entraram naquele retorno. So LE."""
    return [dict(r) for r in con.execute(
        """SELECT a.id ato_id, a.tipo, a.data_ato, t.numero_titulo,
                  t.nosso_numero, t.protocolo, t.saldo_centavos
             FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.retorno_id = ? ORDER BY a.id""", (int(retorno_id),))]
