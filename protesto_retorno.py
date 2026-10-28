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

from bd_nativo import banco
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
    # TÍTULO QUE VEIO DA CENPROT NÃO VOLTA PELA CRA — 21/10/2026. Até aqui
    # entrava `t.origem IN ('CRA', 'CENPROT')`, e o retorno do 900001/2
    # (pedido 9000002 da Gestão de Pedidos) foi recusado três vezes:
    # «APRESENTANTE: TAB - SEQUENCIAL REMESSA: 000077 NÃO FOI ENCONTRADO NA
    # CRA» (código 2154) — a remessa nunca passou por ela. O pagamento entrou
    # na CENPROT pelo XML «D» (aceito no mesmo dia). Esses atos vão pela tela
    # «XML do CENPROT»; `pendentes_da_cenprot` os conta para a tela dizer isso.
    #
    # ATO DESFEITO NÃO VAI À CRA — 28/10/2026. Até aqui a lista não olhava
    # `cancelado`, e o ato que se lavrou e foi desfeito (o selo não saiu, ou
    # foi tornado sem efeito) entrava no retorno como se existisse. Caso
    # real: no título 1353 o CANCELAMENTO (ato 4104) foi desfeito às 13h57
    # por falta de selo, o retorno R3412810.261 saiu às 14h32 dizendo «A —
    # protesto cancelado», a CRA aceitou — e hoje a Central diz «cancelado»
    # enquanto o livro diz «protestado». Medido na produção nesse dia: 19
    # atos desfeitos já tinham sido informados (16 protestos, 2
    # cancelamentos, 1 pagamento). É o filtro que a certidão, o XML da
    # CENPROT e `pendentes_da_cenprot` já faziam.
    onde = ["a.retorno_id IS NULL",
            "COALESCE(a.cancelado, 0) = 0",
            f"a.tipo IN ({','.join(['%s'] * len(quais))})",
            "t.origem = 'CRA'"]
    params: list[Any] = list(quais)
    if apresentante_codigo:
        onde.append("t.apresentante_codigo = %s")
        params.append(str(apresentante_codigo).strip())

    linhas = banco(con).ler(
        f"""SELECT a.id ato_id, a.tipo, a.data_ato, t.id titulo_id,
                   t.numero_titulo, t.nosso_numero, t.valor_centavos,
                   t.saldo_centavos, t.protocolo, t.apresentante_codigo,
                   t.apresentante_nome, t.cra_identificacao, t.situacao,
                   (SELECT data_ato FROM pt_atos e
                     WHERE e.titulo_id = t.id AND e.tipo = 'APONTAMENTO'
                       AND COALESCE(e.cancelado, 0) = 0
                     ORDER BY e.id LIMIT 1) data_entrada
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
             WHERE {' AND '.join(onde)}
             ORDER BY t.apresentante_codigo, a.data_ato, a.id""",
        params)
    return linhas


def pendentes_da_cenprot(con: sqlite3.Connection, *,
                         apresentante_codigo: str | None = None) -> int:
    """Quantos atos de título VINDO DA CENPROT esperam ser informados. Só LÊ.

    Eles não entram no retorno à CRA (ver `pendentes`); a conta existe para a
    tela dizer onde eles vão, em vez de o apresentante parecer em dia.
    """
    onde = ["a.retorno_id IS NULL", "a.cenprot_xml_id IS NULL",
            "COALESCE(a.cancelado, 0) = 0",
            f"a.tipo IN ({','.join(['%s'] * len(ATOS_QUE_VOLTAM))})",
            "t.origem = 'CENPROT'"]
    params: list[Any] = list(ATOS_QUE_VOLTAM)
    if apresentante_codigo:
        onde.append("t.apresentante_codigo = %s")
        params.append(str(apresentante_codigo).strip())
    return int(banco(con).valor(
        f"""SELECT count(*) AS n FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
             WHERE {' AND '.join(onde)}""", params) or 0)


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
    bd = banco(con)
    t = bd.um(
        """SELECT * FROM pt_titulos WHERE id=%s""", (int(a["titulo_id"]),))
    d = bd.um(
        """SELECT * FROM pt_devedores WHERE titulo_id=%s ORDER BY id LIMIT 1""",
        (int(a["titulo_id"]),))
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
        da_cenprot = (pendentes_da_cenprot(con, apresentante_codigo=codigo)
                      if tipo == "SDTBFORTP" else 0)
        if da_cenprot:
            raise RetornoError(
                f"Não há {qual} para a CRA do apresentante {codigo}, mas "
                f"{da_cenprot} ato(s) de título que veio pela CENPROT esperam ser "
                f"informados — esses vão no arquivo XML da CENPROT (Protesto → "
                f"XML do CENPROT), e não no retorno à CRA.")
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
            # A identificação do título na Central, quando a carga a trouxe
            # (`tbSDT.Campo03`); senão o que o título recebido aqui guardou nas
            # posições 005/019 — que, no título da remessa, é ela mesma.
            "identificacao_do_apresentante": (a.get("cra_identificacao")
                                              or a["apresentante_nome"] or ""),
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

    # UMA LINHA POR PROTOCOLO — 23/10/2026. Título com dois devedores entra
    # como duas linhas da remessa e dois títulos aqui, com o MESMO protocolo
    # (35 no acervo; o E-Ofício fazia igual). No arquivo que volta, a CRA
    # recusa o lote inteiro com 9999 «MESMO PROTOCOLO… ARQUIVO NÃO FOI
    # ENVIADO» (medido no retorno de um banco, 23/10). Vai a primeira linha de
    # cada protocolo; os atos das duas continuam em `atos` e são marcados
    # juntos como informados.
    #
    # SÓ O IRMÃO COM A MESMA OCORRÊNCIA VAI JUNTO — correção de 27/10/2026.
    # O corte valia para QUALQUER segundo ato do protocolo, e `gerar` marcava
    # todos como informados: um protesto (`C`) e um cancelamento (`A`) do mesmo
    # protocolo no mesmo dia saíam só com o `C`, e o `A` ficava marcado sem ter
    # ido — a CRA continuaria dando o título por protestado. Agora o ato com
    # outra ocorrência fica FORA de `atos` (continua pendente e entra no
    # arquivo seguinte), e só o irmão do título com dois devedores, que diz a
    # mesma coisa, é marcado junto.
    ocorrencia_do_protocolo: dict[str, str] = {}
    unicos, atos_no_arquivo, adiados = [], [], []
    for a, t in zip(atos, titulos):
        prot = t["protocolo"]
        if prot not in ocorrencia_do_protocolo:
            ocorrencia_do_protocolo[prot] = t["ocorrencia"]
            unicos.append(t)
            atos_no_arquivo.append(a)
        elif ocorrencia_do_protocolo[prot] == t["ocorrencia"]:
            atos_no_arquivo.append(a)
        else:
            adiados.append(a)
    titulos = unicos
    atos = atos_no_arquivo

    # O NOME DO APRESENTANTE VEM DO CABEÇALHO DA REMESSA — correção de
    # 13/10/2026. `pt_titulos.apresentante_nome` guarda o campo 005/019 do
    # registro do título («Agência / Código do Cedente», no layout da P21), e
    # o cabeçalho do andamento saía com `h03 = 537681502381151` no lugar de
    # «BRADESCO SA» (medido no ensaio da homologação). O título continua
    # levando aquele código no lugar dele; só o cabeçalho e o rodapé mudam.
    linha = banco(con).um(
        """SELECT apresentante_nome FROM pt_remessas
            WHERE apresentante_codigo = %s AND COALESCE(apresentante_nome, '') <> ''
            ORDER BY id DESC LIMIT 1""", (codigo,))
    nome = ((linha["apresentante_nome"] if linha else "") or atos[0]["apresentante_nome"] or "").strip()
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
        # Os atos do mesmo protocolo com outra ocorrência: não entram neste
        # arquivo e continuam pendentes para o próximo.
        "adiados": adiados,
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
    bd = banco(con)
    ultima = bd.um(
        """SELECT conteudo FROM pt_remessas WHERE apresentante_codigo = %s
            ORDER BY id DESC LIMIT 1""", (codigo,))
    cab_remessa = ((ultima["conteudo"] if ultima else "") or "").replace("\r", "").split("\n")[0]
    agencia = cab_remessa[83:89] if len(cab_remessa) == 600 else ""
    portador = cab_remessa[89:100] if len(cab_remessa) == 600 else ""
    if not portador.strip():
        # A régua da casa (ri_ctp): `ri_codigo_ibge`, ou UF + município.
        from ri_ctp import codigo_ibge_da_casa

        def _config(chave, padrao=""):
            try:
                r = bd.um("SELECT value FROM settings WHERE key=%s",
                          (chave,))
            except sqlite3.Error:
                r = None
            return (r["value"] if r else None) or padrao
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
    arquivos de 2026 da pasta da CRA (C9871007.261, M3410408.261, R1LV1809.261…),
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
            sequencia += int(banco(con).valor(
                "SELECT COUNT(*) FROM pt_retornos WHERE nome_arquivo ILIKE %s",
                (base + "_",)))
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
        return int(banco(con).escrever(
            """INSERT INTO pt_retornos(tipo, par_id, apresentante_codigo,
                   apresentante_nome, dia, numero_da_remessa, marca, titulos,
                   soma_centavos, nome_arquivo, conteudo, hash_arquivo,
                   gerado_em, gerado_por)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (montado["tipo"], par_id, montado["apresentante_codigo"],
             montado["apresentante_nome"], montado["dia"],
             int(numero_da_remessa or 1), montado["marca"],
             len(montado["atos"]), montado["soma_centavos"],
             montado["nome_arquivo"], conteudo, hash_retorno(conteudo), agora,
             usuario))[0]["id"])

    # A TRAVA VEM ANTES DE `montar`, porque é ele que lê as duas coisas que
    # dois `gerar` ao mesmo tempo disputariam: os PENDENTES — o mesmo protesto
    # sairia em dois arquivos, e a Central registraria dois — e a SEQUÊNCIA DO
    # NOME, que `nome_do_arquivo` conta em `pt_retornos` (os dois sairiam com
    # o mesmo `…1`). No SQLite a escrita era uma por vez; no PostgreSQL só
    # espera quem trava com a MESMA chave. `montar` e `nome_do_arquivo` só
    # leem, e a tela que mostra antes de gerar não espera por ninguém.
    banco(con).travar("pt_retornos.nome_arquivo")
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
        banco(con).escrever("UPDATE pt_retornos SET par_id=%s WHERE id=%s",
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
            banco(con).escrever("UPDATE pt_atos SET retorno_id=%s WHERE id=%s",
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


def retorno(con: sqlite3.Connection, retorno_id: int) -> dict | None:
    """O retorno gerado, com o arquivo inteiro. So LE."""
    return banco(con).um("SELECT * FROM pt_retornos WHERE id=%s",
                         (int(retorno_id),))


def listar(con: sqlite3.Connection, limite: int = 100) -> list[dict]:
    """Os retornos gerados, do mais novo para o mais velho. So LE."""
    return banco(con).ler(
        """SELECT id, tipo, par_id, apresentante_codigo, apresentante_nome,
                  dia, numero_da_remessa, titulos, soma_centavos, nome_arquivo,
                  hash_arquivo, gerado_em, gerado_por, cra_enviado_em,
                  cra_enviado_ambiente, cra_envio_erro, cra_enviado_por
             FROM pt_retornos ORDER BY id DESC LIMIT %s""", (int(limite),))


def atos_do_retorno(con: sqlite3.Connection, retorno_id: int) -> list[dict]:
    """Que atos entraram naquele retorno. So LE."""
    return banco(con).ler(
        """SELECT a.id ato_id, a.tipo, a.data_ato, t.numero_titulo,
                  t.nosso_numero, t.protocolo, t.saldo_centavos
             FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.retorno_id = %s ORDER BY a.id""", (int(retorno_id),))


def informados_e_desfeitos(con: sqlite3.Connection, *,
                           apresentante_codigo: str | None = None
                           ) -> list[dict]:
    """Os atos que entraram num arquivo à CRA e hoje estão DESFEITOS. Só LÊ.

    O QUE A CENTRAL OUVIU NÃO É O QUE O LIVRO DIZ, e a tela tem de mostrar
    isso. Medido na produção em 28/10/2026: **19** atos com `retorno_id` e
    `cancelado = 1`, todos em retornos já enviados à CRA de produção — 16
    protestos tornados sem efeito, 2 cancelamentos e 1 pagamento desfeitos
    porque o selo não saiu. Em 17 deles há outro ato válido do mesmo tipo no
    título; em 2 (o cancelamento do título 1353 e um pagamento) não há, e ali
    a Central afirma o que não aconteceu.

    NÃO SE REENVIA NADA SOZINHO. O contrato da CRA não tem ocorrência medida
    para «desfaça o que eu disse», e qual providência cabe (carta, contato
    com a Central, novo ato) é decisão do oficial. Esta função só junta os
    fatos — o arquivo em que o ato foi, se ele já subiu, o motivo de ter sido
    desfeito e se o título tem outro ato válido do mesmo tipo — para a tela
    avisar. Os arquivos da virada (o E-Ofício) entram também: o que ele
    informou a Central ouviu do mesmo jeito.
    """
    onde = ["a.retorno_id IS NOT NULL", "COALESCE(a.cancelado, 0) = 1"]
    params: list[Any] = []
    if apresentante_codigo:
        onde.append("t.apresentante_codigo = %s")
        params.append(str(apresentante_codigo).strip())
    return banco(con).ler(
        f"""SELECT a.id ato_id, a.tipo, a.data_ato, a.motivo_cancelamento,
                   a.retorno_id, t.id titulo_id, t.numero_titulo,
                   t.protocolo, t.situacao, t.apresentante_codigo,
                   r.tipo tipo_arquivo, r.nome_arquivo, r.gerado_em,
                   r.cra_enviado_em, r.cra_enviado_ambiente,
                   (SELECT v.id FROM pt_atos v
                     WHERE v.titulo_id = a.titulo_id AND v.tipo = a.tipo
                       AND COALESCE(v.cancelado, 0) = 0
                     ORDER BY v.id DESC LIMIT 1) ato_valido_id,
                   (SELECT v.retorno_id FROM pt_atos v
                     WHERE v.titulo_id = a.titulo_id AND v.tipo = a.tipo
                       AND COALESCE(v.cancelado, 0) = 0
                     ORDER BY v.id DESC LIMIT 1) ato_valido_retorno_id
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
              LEFT JOIN pt_retornos r ON r.id = a.retorno_id
             WHERE {' AND '.join(onde)}
             ORDER BY a.id DESC""",
        params)


# ------------------------------------------ o que o E-Ofício já mandou à CRA
#
# A VIRADA DO PROTESTO (13/10/2026). Os atos trazidos do E-Ofício não têm
# `retorno_id`, e `pendentes()` os oferecia de volta: a tela da CRA mandaria
# reenviar mais de mil atos que o E-Ofício já informou. Marcar TODOS seria o
# erro do outro lado — o que o E-Ofício lavrou e ainda não retornou ficaria
# calado. Marca-se só o que aparece nos ARQUIVOS que ele gerou (a pasta da
# CRA), e o que é anterior a esses arquivos todos.
NOME_DO_INFORMADO_PELO_EOFICIO = {
    "SDTBFORTP": "E-OFICIO-RETORNOS-ANTES-DA-VIRADA",
    "SDTBFOAND": "E-OFICIO-ANDAMENTOS-ANTES-DA-VIRADA",
}
#: Que ocorrência do retorno prova cada ato final (`protesto_cra.OCORRENCIAS`;
#: «C» é o protesto como o E-Ofício o escrevia, 1.106 de 1.107 no acervo).
OCORRENCIA_QUE_PROVA = {"PROTESTO": {"2", "C"}, "PAGAMENTO": {"1"},
                        "DESISTENCIA": {"3"}, "CANCELAMENTO": {"A"}}


def _registro_do_eoficio(con: sqlite3.Connection, tipo: str, agora: str) -> int:
    nome = NOME_DO_INFORMADO_PELO_EOFICIO[tipo]
    bd = banco(con)
    linha = bd.um("SELECT id FROM pt_retornos WHERE nome_arquivo=%s",
                  (nome,))
    if linha:
        return int(linha["id"])
    return int(bd.escrever(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, apresentante_nome,
               dia, numero_da_remessa, titulos, soma_centavos, nome_arquivo,
               conteudo, gerado_em, gerado_por, cra_enviado_em,
               cra_enviado_ambiente, cra_envio_resumo)
           VALUES (%s, '', 'E-Ofício', %s, 1, 0, 0, %s, '', %s, 'virada do protesto',
                   %s, 'EOFICIO', %s)
           RETURNING id""",
        (tipo, agora[:10], nome, agora, agora,
         "Não é arquivo deste sistema: marca os atos que o E-Ofício já "
         "informou à CRA antes da virada (13/10/2026)."))[0]["id"])


def marcar_o_que_o_eoficio_ja_informou(con: sqlite3.Connection, fluxo: dict,
                                       *, agora: str) -> dict:
    """Marca como informados os atos do E-Ofício que os arquivos provam. ESCREVE.

    `fluxo` é `gestor_protesto.ler_fluxo_da_cra` da pasta da CRA. Ato final
    entra se o retorno do mesmo protocolo traz a ocorrência dele; apontamento
    entra se o título aparece em qualquer arquivo devolvido. Ato anterior ao
    primeiro arquivo da pasta entra também: o E-Ofício era o único sistema, e
    ato pendente de retorno há mais tempo que a pasta alcança não existe. O que
    sobra fica pendente — e sai no primeiro retorno do Cartório Gestão.
    """
    datas = [r["enviado"] for v in fluxo.get("retorno", {}).values() for r in v
             if r.get("enviado")]
    desde = min(datas).isoformat() if datas else None
    contagem = {"retorno": 0, "andamento": 0, "anterior_aos_arquivos": 0,
                "fica_pendente": 0, "desde": desde}
    reg_ret = reg_and = None
    # A MESMA TRAVA DE `gerar`, e antes da lista: os dois marcam os mesmos
    # atos (`retorno_id IS NULL`), e `_registro_do_eoficio` confere se a linha
    # da virada já existe antes de inserir — duas passadas ao mesmo tempo
    # gravariam duas.
    banco(con).travar("pt_retornos.nome_arquivo")
    linhas = banco(con).ler(
        """SELECT a.id, a.tipo, a.data_ato, t.protocolo, t.apresentante_codigo,
                  t.nosso_numero, t.numero_titulo
             FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.retorno_id IS NULL AND a.origem = 'EOFICIO'
              AND t.origem IN ('CRA', 'CENPROT')
            ORDER BY a.id""")
    for a in linhas:
        tipo, prot = a["tipo"], str(a["protocolo"] or "").strip()
        if tipo == "APONTAMENTO":
            apres = str(a["apresentante_codigo"] or "").strip()
            provado = ((apres, str(a["nosso_numero"] or "").strip())
                       in fluxo.get("respondido", set())
                       or (apres, str(a["numero_titulo"] or "").strip())
                       in fluxo.get("respondido", set()))
            arquivo = "SDTBFOAND"
        elif tipo in OCORRENCIA_QUE_PROVA:
            provado = any(str(r.get("ocorrencia") or "").upper()
                          in OCORRENCIA_QUE_PROVA[tipo]
                          for r in fluxo.get("retorno", {}).get(prot, []))
            arquivo = "SDTBFORTP"
        else:
            continue
        antigo = bool(desde and str(a["data_ato"] or "")[:10] < desde)
        if not (provado or antigo):
            contagem["fica_pendente"] += 1
            continue
        if arquivo == "SDTBFORTP":
            reg_ret = reg_ret or _registro_do_eoficio(con, arquivo, agora)
            alvo = reg_ret
            contagem["retorno"] += 1
        else:
            reg_and = reg_and or _registro_do_eoficio(con, arquivo, agora)
            alvo = reg_and
            contagem["andamento"] += 1
        if antigo and not provado:
            contagem["anterior_aos_arquivos"] += 1
        banco(con).escrever("UPDATE pt_atos SET retorno_id=%s WHERE id=%s",
                            (alvo, a["id"]))
    return contagem
