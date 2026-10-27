"""
A escrituracao — abrir livro, achar lugar, lancar, inutilizar o que sobrou,
encerrar o livro e encerrar o dia. Para as SEIS atribuicoes, com um codigo so.

O QUE ESTE MODULO E
    O par de `livro_nucleo`. Aquele diz COMO o livro e (folhas, verso, folha
    nova, paginas pares); este diz ONDE o ato cai e grava o lugar.

COMO SE USA, DO LADO DA ATRIBUICAO
    A atribuicao abre a transacao, chama `reservar(...)` e grava o proprio ato
    com o livro, a folha e o numero que voltaram:

        with db.transaction() as con:
            bd = banco(con)
            ato_id = bd.escrever("INSERT INTO rc_atos ... RETURNING id")[0]["id"]
            lugar = escrituracao.reservar(
                con, "RC_A", "rc_atos", ato_id,
                sv=sv, agora=agora, data_extenso=hoje, paginas=1)
            bd.escrever("UPDATE rc_atos SET livro_id=%s, folha=%s, numero=%s WHERE id=%s",
                        (lugar["livro_id"], lugar["folha"], lugar["numero_ordem"], ato_id))
        audit(...)                      # FORA da transacao, como no resto da casa

    Repare em duas coisas:

    1. O ato entra PRIMEIRO e o lugar depois. Assim, se a reserva falhar por
       falta de folha, a transacao inteira volta atras e nao sobra ato sem
       lugar nem numero consumido.
    2. `audit()` fica fora. `audit()` abre transacao propria; chamado dentro,
       trava contra o `BEGIN IMMEDIATE` de fora. Ja aconteceu nesta casa.

O QUE ESTE MODULO NAO FAZ
    Nao emite selo, nao calcula emolumento, nao escreve teor de ato. Nao sabe
    o que e uma matricula nem uma certidao de nascimento. So livro, folha,
    ordem e termo.

FUNDAMENTO
    Lei 8.935/1994, art. 30, I; art. 46.
    Lei 6.015/1973, arts. 3o a 6o.
    Lei 9.492/1997, arts. 33 e 34.
    Codigo de Normas do Foro Extrajudicial do Maranhao — Provimento TJMA n. 28,
        de 23/04/2026 — Secao "Dos Livros e da sua Escrituracao".
"""
from __future__ import annotations

import sqlite3
from typing import Any

import livro_nucleo as LN
from bd_nativo import banco
from livro_nucleo import LivroError, Serie, com_algarismos, rotulo_folha


# --------------------------------------------------------------- utilidades


def _inteiro(valor: Any) -> int | None:
    """Numero inteiro de um campo de formulario, ou None. Nunca levanta."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, int):
        return valor
    try:
        texto = str(valor).strip()
        return int(float(texto.replace(",", "."))) if texto else None
    except (TypeError, ValueError):
        return None


def _face(rotulo: str) -> tuple[int, int]:
    """'14v' -> (14, 1). Inverso de `rotulo_folha`."""
    texto = str(rotulo or "").strip().lower()
    verso = 1 if texto.endswith("v") else 0
    numero = _inteiro(texto[:-1] if verso else texto)
    if numero is None:
        raise LivroError(f"Folha inválida: {rotulo!r}.")
    return numero, verso


def serie_de(codigo: str) -> Serie:
    """A serie, com mensagem de balcao quando o codigo nao existe."""
    try:
        return LN.serie(codigo)
    except Exception:
        raise LivroError(
            f"A série {codigo!r} não existe no núcleo. As séries conhecidas "
            f"estão em livro_nucleo.SERIES.") from None


# --------------------------------------------------------- numero de ordem
#
# Continuo por serie e por serventia. Semeado do que ja existe, porque comecar
# do 1 sobre acervo importado repetiria numero de 1985.


def _semente(con, serie: str) -> int:
    """O maior numero de ordem ja gravado na serie. So LE."""
    linha = banco(con).um(
        "SELECT MAX(COALESCE(numero_ordem, 0)) m FROM nu_lugares WHERE serie=%s",
        (serie,))
    return int((linha["m"] if linha and linha["m"] is not None else 0) or 0)


def _proximo_do_dia(con, serie: str, dia: str) -> int:
    """O proximo numero num livro de numeracao DIARIA. So LE.

    O protocolo do protesto reinicia todo dia: `tbProtocoloProtesto` guarda um
    `intProtocolo_Ultimo` por data, com valores de 1 a 6. Por isso nao ha
    contador em `nu_numeracao` para estas series — o numero sai do proprio
    livro do dia, e um dia sem movimento comeca no 1 sem precisar que alguem
    zere nada.

    Nao ha corrida aqui porque a casa grava sob `BEGIN IMMEDIATE`: um escritor
    por vez. E, se algum dia houver, `ux_nu_lugares_ordem` recusa no banco.
    """
    if not dia:
        s = serie_de(serie)
        raise LivroError(
            f"{s.nome} é de numeração diária; informe o dia (AAAA-MM-DD).")
    linha = banco(con).um(
        """SELECT MAX(l.numero_ordem) m FROM nu_lugares l
             JOIN nu_livros v ON v.id = l.livro_id
            WHERE l.serie = %s AND v.dia = %s""", (serie, dia))
    return int((linha["m"] if linha and linha["m"] is not None else 0) or 0) + 1


def proximo_numero(con, serie: str,
                   consumir: bool = True, dia: str | None = None) -> int:
    """O proximo numero de ordem da serie.

    Com `consumir=False` NAO ESCREVE NADA — nem o UPDATE, nem a criacao da
    linha do contador. A tela de conferencia chama isto num GET, e GET que
    abre transacao de escrita fica preso no `busy_timeout` e devolve 500
    enquanto outro balcao lavra. Tela de leitura le.

    Em serie de numeracao DIARIA nunca escreve: o numero sai do livro do dia.
    """
    bd = banco(con)
    if serie_de(serie).numeracao_diaria:
        return _proximo_do_dia(bd, serie, dia or "")
    if not consumir:
        linha = bd.um("SELECT * FROM nu_numeracao WHERE serie=%s", (serie,))
        return int(linha["proximo"]) if linha else _semente(bd, serie) + 1
    # Le e grava o contador: trava o assunto (a linha pode ainda nao existir)
    # e a linha, antes de ler.
    bd.travar("nu_numeracao.proximo")
    linha = bd.um("SELECT * FROM nu_numeracao WHERE serie=%s FOR UPDATE", (serie,))
    if not linha:
        # Semeia a linha e CAI no consumo abaixo. Devolver `base + 1` aqui e
        # sair era um defeito: a linha nascia com `proximo = base + 1`, o
        # numero devolvido era esse mesmo, e a chamada seguinte devolvia o
        # numero de novo. Dois atos com o mesmo numero de ordem — exatamente o
        # que este modulo existe para nao deixar acontecer.
        base = _semente(bd, serie)
        bd.escrever(
            """INSERT INTO nu_numeracao(serie, proximo, maior_em_uso, semeado_de,
                                        observacao)
               VALUES (%s,%s,%s,%s,%s)""",
            (serie, base + 1, base, "nu_lugares",
             "semeado do maior número de ordem já gravado na série"))
        linha = bd.um("SELECT * FROM nu_numeracao WHERE serie=%s FOR UPDATE",
                      (serie,))
    numero = int(linha["proximo"])
    bd.escrever(
        """UPDATE nu_numeracao
              SET proximo=%s, maior_em_uso=GREATEST(COALESCE(maior_em_uso, 0), %s)
            WHERE serie=%s""", (numero + 1, numero, serie))
    return numero


def fixar_numeracao(con, serie: str, proximo: Any,
                    *, usuario: str | None, motivo: str | None,
                    agora: str) -> int:
    """Corrige o contador a mao, como a tela de numeracao do RI faz.

    Recusa numero igual ou menor que o maior ja usado — isso repetiria numero
    de ordem, e repetir numero de ordem e o defeito de 18/08 outra vez.
    """
    s = serie_de(serie)
    if s.numeracao_diaria:
        raise LivroError(
            f"{s.nome} tem numeração diária — ela reinicia sozinha a cada dia "
            f"e não há contador a corrigir.")
    novo = _inteiro(proximo)
    if novo is None or novo < 1:
        raise LivroError("Informe o próximo número, inteiro e maior que zero.")
    bd = banco(con)
    proximo_numero(bd, serie, consumir=False)
    # Le o maior e grava o contador: a mesma trava de quem consome.
    bd.travar("nu_numeracao.proximo")
    linha = bd.um("SELECT * FROM nu_numeracao WHERE serie=%s FOR UPDATE", (serie,))
    maior = int((linha["maior_em_uso"] if linha else None) or _semente(bd, serie))
    if novo <= maior:
        raise LivroError(
            f"O número {novo} é igual ou menor que o maior já usado nesta série "
            f"({maior}). Isso repetiria número de ordem.")
    if linha:
        bd.escrever(
            """UPDATE nu_numeracao SET proximo=%s, fixado_em=%s, fixado_por=%s,
                                       observacao=%s WHERE serie=%s""",
            (novo, agora, usuario, (motivo or "").strip() or None, serie))
    else:
        bd.escrever(
            """INSERT INTO nu_numeracao(serie, proximo, maior_em_uso, semeado_de,
                                        fixado_em, fixado_por, observacao)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (serie, novo, maior, "nu_lugares", agora, usuario,
             (motivo or "").strip() or None))
    return novo


# ---------------------------------------------------------------- os termos


def texto_termo_abertura(serie: str, numero: Any, folhas: int, sv: dict,
                         data_extenso: str, folha_inicial: int = 1,
                         dia: str | None = None) -> str:
    """O termo de abertura, na forma do art. 30, I, da Lei 8.935/1994."""
    s = serie_de(serie)
    ultima = int(folha_inicial) + int(folhas) - 1
    cabeca = (
        f"TERMO DE ABERTURA. Este Livro n. {numero}, de {s.nome}, contém "
        f"{com_algarismos(folhas, feminino=True)} folhas, numeradas de "
        f"{com_algarismos(folha_inicial, feminino=True)} a "
        f"{com_algarismos(ultima, feminino=True)}, todas por mim rubricadas, e "
        f"servirá para a escrituração dos atos de sua espécie nesta "
        f"{sv.get('unit_name', '')}, CNS {sv.get('ri_cns', '')}, "
        f"{sv.get('ri_cidade', '')}-{sv.get('ri_uf', '')}.")
    if dia:
        cabeca += f" Escrituração do dia {dia}."
    return (
        f"{cabeca} {sv.get('ri_cidade', '')}-{sv.get('ri_uf', '')}, "
        f"{data_extenso}. {sv.get('serventia_titular', '')} — "
        f"{sv.get('serventia_titulo', '')}.")


def texto_termo_encerramento(serie: str, numero: Any, folhas: int,
                             ultima_usada: int | None,
                             primeiro: int | None, ultimo: int | None,
                             sv: dict, data_extenso: str,
                             folha_inicial: int = 1,
                             motivo: str | None = None,
                             inutilizadas: int = 0) -> str:
    """O termo de encerramento, com o que foi usado e o que ficou inutilizado.

    A parte que costuma faltar e a ultima: dizer o que sobrou em branco. Folha
    em branco em livro encerrado e a porta aberta do art. 795, par. 2o.
    """
    s = serie_de(serie)
    limite = int(folha_inicial) + int(folhas) - 1
    usada = _inteiro(ultima_usada)
    partes = [
        f"TERMO DE ENCERRAMENTO. Fica encerrado o presente Livro n. {numero}, "
        f"de {s.nome}, com {com_algarismos(folhas, feminino=True)} folhas."]
    if usada:
        partes.append(
            f"Foram utilizadas as folhas de "
            f"{com_algarismos(folha_inicial, feminino=True)} a "
            f"{com_algarismos(usada, feminino=True)}.")
    else:
        partes.append("Nenhuma folha foi utilizada.")
    if primeiro and ultimo:
        partes.append(
            f"Nele foram escriturados os atos de n. {com_algarismos(primeiro)} "
            f"a n. {com_algarismos(ultimo)}.")
    if inutilizadas:
        partes.append(
            f"{com_algarismos(inutilizadas, feminino=True)} faces foram "
            f"inutilizadas por termo próprio no curso da escrituração.")
    if usada is not None and usada < limite:
        partes.append(
            f"As folhas de {com_algarismos(usada + 1, feminino=True)} a "
            f"{com_algarismos(limite, feminino=True)} ficam INUTILIZADAS por "
            f"este termo, nada mais podendo nelas ser lançado.")
    if motivo:
        partes.append(f"Motivo do encerramento: {motivo.strip()}.")
    partes.append(
        f"{sv.get('ri_cidade', '')}-{sv.get('ri_uf', '')}, {data_extenso}. "
        f"{sv.get('serventia_titular', '')} — {sv.get('serventia_titulo', '')}.")
    return " ".join(partes)


def texto_termo_inutilizacao(serie: str, numero_livro: Any, rotulo: str,
                             motivo: str, sv: dict, data_extenso: str) -> str:
    """O termo que se lanca NA face inutilizada, atravessado."""
    s = serie_de(serie)
    return (
        f"FOLHA INUTILIZADA. Fica inutilizada a folha {rotulo} do Livro n. "
        f"{numero_livro}, de {s.nome}, nada nela podendo ser lançado. "
        f"Motivo: {motivo.strip()}. "
        f"{sv.get('ri_cidade', '')}-{sv.get('ri_uf', '')}, {data_extenso}. "
        f"{sv.get('serventia_titular', '')} — {sv.get('serventia_titulo', '')}.")


def texto_encerramento_diario(serie: str, dia_extenso: str, quantidade: int,
                              primeiro: int | None, ultimo: int | None,
                              sv: dict) -> str:
    """O termo de encerramento do dia, no livro de protocolo.

    A inspecao de 12/08/2026 cobrou isto de Protesto e de RCPJ. Dia sem
    movimento tambem se encerra: o silencio tem de estar escrito, senao nao se
    distingue de folha nao escriturada.
    """
    s = serie_de(serie)
    if not s.diario:
        raise LivroError(
            f"A série {s.codigo} ({s.nome}) não é de livro diário — ela se "
            f"encerra quando enche, não no fim do dia.")
    if quantidade and primeiro and ultimo:
        corpo = (
            f"Foram protocolados {com_algarismos(quantidade)} títulos ou "
            f"documentos, sob os n. {com_algarismos(primeiro)} a "
            f"n. {com_algarismos(ultimo)}.")
    else:
        corpo = "Não houve movimento neste dia."
    return (
        f"ENCERRAMENTO DO DIA. Encerra-se a escrituração do {s.nome} em "
        f"{dia_extenso}. {corpo} "
        f"{sv.get('ri_cidade', '')}-{sv.get('ri_uf', '')}, {dia_extenso}. "
        f"{sv.get('serventia_titular', '')} — {sv.get('serventia_titulo', '')}.")


# ---------------------------------------------------------------- os livros


def numero_do_proximo_livro(con, serie: str) -> str:
    """O numero do proximo livro da serie: 1 se nao ha nenhum, senao maior+1.

    Le `numero` como texto e converte, porque o acervo trouxe '1', '01' e
    '2S-3'. O que nao converte e ignorado na conta do maximo, e nao derruba a
    abertura.
    """
    serie_de(serie)
    maior = 0
    for linha in banco(con).ler(
            "SELECT numero FROM nu_livros WHERE serie=%s ORDER BY id", (serie,)):
        n = _inteiro(str(linha["numero"]).split("-")[-1])
        if n and n > maior:
            maior = n
    return str(maior + 1)


def livro_da_vez(con, serie: str,
                 dia: str | None = None) -> dict | None:
    """O livro aberto da serie, ou None. So LE.

    Em serie diaria o livro da vez e o DO DIA: o protocolo de ontem esta
    encerrado, e lancar no de ontem seria antedatar.
    """
    s = serie_de(serie)
    if s.diario:
        if not dia:
            raise LivroError(
                f"A série {s.codigo} é de livro diário; informe o dia.")
        return banco(con).um(
            """SELECT * FROM nu_livros
                WHERE serie=%s AND dia=%s AND encerrado=0 AND ativo=1
                ORDER BY id DESC LIMIT 1""", (serie, dia))
    return banco(con).um(
        """SELECT * FROM nu_livros
            WHERE serie=%s AND encerrado=0 AND ativo=1
            ORDER BY id DESC LIMIT 1""", (serie,))


def abrir_livro(con, serie: str, *, sv: dict, agora: str,
                data_extenso: str, folhas: int | None = None,
                complemento: str = "", descricao: str | None = None,
                dia: str | None = None, usuario: str | None = None,
                folha_inicial: int = 1) -> int:
    """Abre livro novo da serie, com termo de abertura. ESCREVE.

    Recusa abrir um segundo livro aberto na mesma serie: dois livros abertos
    e a receita para o mesmo numero de ordem sair em dois lugares.
    """
    s = serie_de(serie)
    if s.diario and not dia:
        raise LivroError(
            f"A série {s.codigo} é de livro diário; informe o dia (AAAA-MM-DD).")
    bd = banco(con)
    # Le o livro aberto e o maior numero para numerar o novo: trava antes.
    bd.travar("nu_livros.numero")
    if livro_da_vez(bd, serie, dia=dia):
        onde = f" do dia {dia}" if dia else ""
        raise LivroError(
            f"Já existe livro aberto de {s.nome}{onde}. Encerre-o antes de "
            f"abrir outro — dois livros abertos na mesma série fazem o mesmo "
            f"número de ordem sair em dois lugares.")
    quantas = _inteiro(folhas) or s.folhas
    if quantas < 1:
        raise LivroError("O livro precisa de pelo menos uma folha.")
    numero = numero_do_proximo_livro(bd, serie)
    termo = texto_termo_abertura(serie, numero, quantas, sv, data_extenso,
                                 folha_inicial=folha_inicial, dia=dia)
    novo = bd.escrever(
        """INSERT INTO nu_livros(serie, atribuicao, numero, complemento, descricao,
                                 folhas, folha_inicial, folha_atual, dia, abertura,
                                 termo_abertura, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (serie, s.atribuicao, numero, complemento or "", descricao, quantas,
         int(folha_inicial), int(folha_inicial), dia, agora, termo, agora, usuario))
    return int(novo[0]["id"])


def ultima_folha(livro: dict) -> int:
    """A ultima folha do livro."""
    return int(livro["folha_inicial"] or 1) + int(livro["folhas"] or 1) - 1


def faces_ocupadas(con, livro_id: int) -> set[tuple[int, int]]:
    """As faces do livro que ja tem algo — ato ou inutilizacao. So LE."""
    bd = banco(con)
    ocupadas = {
        (int(r["folha"]), int(r["verso"]))
        for r in bd.ler(
            "SELECT folha, verso FROM nu_lugares WHERE livro_id=%s ORDER BY id",
            (livro_id,))}
    ocupadas |= {
        (int(r["folha"]), int(r["verso"]))
        for r in bd.ler(
            "SELECT folha, verso FROM nu_inutilizacoes WHERE livro_id=%s ORDER BY id",
            (livro_id,))}
    return ocupadas


def folha_livre(con, livro: dict) -> int:
    """A primeira folha inteiramente livre do livro. So LE.

    Nao confia em `folha_atual`: os livros importados do acervo nasceram com
    `folha_atual = 1` e ficaram em 1 mesmo com atos lavrados. Conta o que
    esta gravado; usa `folha_atual` apenas como piso.
    """
    ocupadas = faces_ocupadas(con, int(livro["id"]))
    inicio = int(livro["folha_inicial"] or 1)
    piso = max(inicio, _inteiro(livro["folha_atual"]) or inicio)
    if not ocupadas:
        return piso
    maior = max(f for f, _ in ocupadas)
    return max(piso, maior + 1)


def _proxima_posicao(con, s: Serie,
                     livro: dict) -> tuple[int, int, int]:
    """(folha, verso, ordem) do proximo lugar livre, conforme a serie.

    Serie de folha nova comeca sempre em folha limpa. Serie de varios por
    folha — apontamento, protocolo, pagamento — enche a face antes de virar.
    """
    bd = banco(con)
    if s.folha_nova:
        return folha_livre(bd, livro), 0, 1
    inicio = int(livro["folha_inicial"] or 1)
    limite = ultima_folha(livro)
    inutilizadas = {
        (int(r["folha"]), int(r["verso"]))
        for r in bd.ler(
            "SELECT folha, verso FROM nu_inutilizacoes WHERE livro_id=%s ORDER BY id",
            (int(livro["id"]),))}
    folha = max(inicio, _inteiro(livro["folha_atual"]) or inicio)
    while folha <= limite:
        for verso in (0, 1) if s.usa_verso else (0,):
            if (folha, verso) in inutilizadas:
                continue
            usados = bd.valor(
                """SELECT COUNT(*) n FROM nu_lugares
                    WHERE livro_id=%s AND folha=%s AND verso=%s""",
                (int(livro["id"]), folha, verso))
            if int(usados) < s.por_face:
                return folha, verso, int(usados) + 1
        folha += 1
    return limite + 1, 0, 1


def reservar(con, serie: str, tabela: str, referencia: int,
             *, sv: dict, agora: str, data_extenso: str, paginas: Any = 1,
             dia: str | None = None, usuario: str | None = None,
             abrir_se_faltar: bool = True) -> dict:
    """Reserva o lugar do ato no livro da serie. ESCREVE. Dentro da transacao.

    Devolve o que a atribuicao precisa gravar no proprio ato:

        livro_id, livro_numero, folha, verso, rotulo, faces, sobra,
        numero_ordem, paginas

    `sobra` sao as faces que ficaram em branco por causa da regra de folha
    inteira. Elas NAO sao inutilizadas aqui: inutilizar e ato do oficial, com
    motivo, e vem por `inutilizar_sobra()` logo depois do fecho. Devolver a
    sobra sem inutilizar de proprio arbitrio e deliberado.
    """
    s = serie_de(serie)
    n_paginas = max(1, _inteiro(paginas) or 1)
    bd = banco(con)
    # Le o livro, a folha livre e o numero do dia para gravar o lugar: trava
    # o assunto antes de ler (a ponte ja da um escritor por vez; isto fica
    # para quando ela sair).
    bd.travar("nu_lugares.lugar")
    ja = lugar_de(bd, tabela, referencia)
    if ja:
        onde = bd.um("SELECT numero FROM nu_livros WHERE id=%s",
                     (int(ja["livro_id"]),))
        raise LivroError(
            f"Este ato já está escriturado no Livro n. "
            f"{onde['numero'] if onde else '?'}, folha {ja['rotulo']}, sob o "
            f"n. {ja['numero_ordem']}. Um ato tem um lugar e não dois.")
    livro = livro_da_vez(bd, serie, dia=dia)
    if not livro:
        if not abrir_se_faltar:
            raise LivroError(f"Não há livro aberto de {s.nome}.")
        abrir_livro(bd, serie, sv=sv, agora=agora, data_extenso=data_extenso,
                    dia=dia, usuario=usuario)
        livro = livro_da_vez(bd, serie, dia=dia)
    assert livro is not None

    folha, verso, ordem = _proxima_posicao(bd, s, livro)
    precisa = LN.folhas_para(s, n_paginas) if s.folha_nova else 1
    limite = ultima_folha(livro)

    if folha + precisa - 1 > limite:
        if s.transborda:
            # Livro A do RCPJ, B/C/F do RTD: o ultimo registro passa do fim do
            # livro em vez de ser cortado no meio. Quem transborda nao abre
            # livro novo no meio do ato.
            pass
        elif s.diario:
            raise LivroError(
                f"O {s.nome} do dia {dia} não tem mais folha livre. Livro "
                f"diário não se substitui no meio do dia — abra o do dia "
                f"seguinte ou amplie este.")
        else:
            encerrar_livro(bd, int(livro["id"]), sv=sv, agora=agora,
                           data_extenso=data_extenso, usuario=usuario,
                           motivo="livro esgotado")
            abrir_livro(bd, serie, sv=sv, agora=agora,
                        data_extenso=data_extenso, dia=dia, usuario=usuario)
            livro = livro_da_vez(bd, serie, dia=dia)
            assert livro is not None
            folha, verso, ordem = _proxima_posicao(bd, s, livro)

    numero = proximo_numero(bd, serie, dia=dia)
    faces = (LN.faces_de(s, folha, n_paginas) if s.folha_nova
             else [rotulo_folha(folha, verso=bool(verso))])
    sobra = LN.sobra_de(s, folha, n_paginas) if s.folha_nova else []

    for i, face in enumerate(faces):
        f, v = _face(face)
        try:
            bd.escrever(
                """INSERT INTO nu_lugares(livro_id, serie, folha, verso, ordem,
                       rotulo, inicio, paginas, numero_ordem, tabela, referencia,
                       ocupado_em, ocupado_por)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (int(livro["id"]), serie, f, v, ordem if i == 0 else 1, face,
                 1 if i == 0 else 0, n_paginas if i == 0 else 1, numero,
                 tabela, int(referencia), agora, usuario))
        except sqlite3.IntegrityError as erro:
            raise LivroError(
                f"A folha {face} do Livro n. {livro['numero']} de {s.nome} já "
                f"está ocupada. Nada foi lançado. ({erro})") from erro

    ultima = max(_face(f)[0] for f in faces)
    bd.escrever("UPDATE nu_livros SET folha_atual=%s WHERE id=%s",
                (ultima if not s.folha_nova else ultima + 1, int(livro["id"])))
    return {
        "livro_id": int(livro["id"]),
        "livro_numero": livro["numero"],
        "serie": serie,
        "folha": folha,
        "verso": bool(verso),
        "ordem": ordem,
        "rotulo": faces[0],
        "faces": faces,
        "sobra": sobra,
        "numero_ordem": numero,
        "paginas": n_paginas,
    }


def lugar_de(con, tabela: str,
             referencia: int) -> dict | None:
    """O lugar de inicio de um ato, ou None. So LE."""
    return banco(con).um(
        """SELECT * FROM nu_lugares
            WHERE tabela=%s AND referencia=%s AND inicio=1""",
        (tabela, int(referencia)))


def liberar(con, tabela: str, referencia: int) -> int:
    """Solta o lugar de um ato. ESCREVE. Devolve quantas faces soltou.

    Serve ao EXPURGO — o ato lavrado em teste que nunca existiu. NAO serve a
    cancelamento: ato cancelado continua ocupando a folha, riscado, porque
    aconteceu. Quem apaga o lugar de ato que existiu apaga o rastro.

    Nao devolve o numero de ordem ao contador, de proposito: numero de ordem
    consumido nao volta, senao o proximo ato nasce com numero que ja apareceu
    em ata de ocorrencia.
    """
    bd = banco(con)
    lugar = lugar_de(bd, tabela, referencia)
    quantas = len(bd.escrever(
        "DELETE FROM nu_lugares WHERE tabela=%s AND referencia=%s RETURNING id",
        (tabela, int(referencia))))
    if lugar:
        _recompor_folha_atual(bd, int(lugar["livro_id"]))
    return quantas


def _recompor_folha_atual(con, livro_id: int) -> int:
    """Reajusta `folha_atual` ao que sobrou no livro. Nunca AUMENTA.

    Serve ao expurgo do ultimo ato: soltar o lugar sem baixar `folha_atual`
    deixaria a folha livre e, ainda assim, inalcancavel — o proximo ato
    pularia para a folha seguinte e a do meio ficaria em branco dentro de
    livro escriturado, que e justamente o que a inspecao cobra.

    Nunca aumenta de proposito: se o buraco esta no MEIO, `folha_atual` fica
    onde esta e o buraco aparece na conferencia, para o oficial decidir entre
    reaproveitar e inutilizar. Voltar sozinho ao meio do livro poria o ato de
    n. 5 fisicamente antes do de n. 3.
    """
    bd = banco(con)
    livro = bd.um("SELECT * FROM nu_livros WHERE id=%s", (livro_id,))
    if not livro:
        return 0
    s = serie_de(livro["serie"])
    inicio = int(livro["folha_inicial"] or 1)
    marcas = [int(r["f"]) for r in bd.ler(
        """SELECT MAX(folha) f FROM nu_lugares WHERE livro_id=%s
           UNION ALL
           SELECT MAX(folha) f FROM nu_inutilizacoes WHERE livro_id=%s""",
        (livro_id, livro_id)) if r["f"] is not None]
    if marcas:
        alvo = max(marcas) + (1 if s.folha_nova else 0)
    else:
        alvo = inicio
    alvo = max(inicio, alvo)
    atual = int(livro["folha_atual"] or inicio)
    if alvo < atual:
        bd.escrever("UPDATE nu_livros SET folha_atual=%s WHERE id=%s",
                    (alvo, livro_id))
        return alvo
    return atual


# ------------------------------------------------------------ inutilizacao


def inutilizar(con, livro_id: int, rotulo: str, *,
               motivo: str, sv: dict, agora: str, data_extenso: str,
               usuario: str | None = None, origem: str = "MANUAL") -> int:
    """Inutiliza uma face em branco, com motivo e termo. ESCREVE.

    Recusa inutilizar face ocupada: a face escriturada nao se inutiliza, o ato
    nela se cancela. Sao coisas diferentes e confundi-las apaga ato bom.
    """
    bd = banco(con)
    # Confere a face livre e grava nela: a mesma trava de quem reserva o
    # lugar, senao o ato reservado ao mesmo tempo cai na face inutilizada.
    bd.travar("nu_lugares.lugar")
    livro = bd.um("SELECT * FROM nu_livros WHERE id=%s", (livro_id,))
    if not livro:
        raise LivroError("Livro não encontrado.")
    razao = (motivo or "").strip()
    if len(razao) < 10:
        raise LivroError(
            "Escreva o motivo da inutilização com pelo menos dez letras — ele "
            "sai impresso no termo e é o que a inspeção lê.")
    folha, verso = _face(rotulo)
    inicio, limite = int(livro["folha_inicial"] or 1), ultima_folha(livro)
    if not (inicio <= folha <= limite):
        raise LivroError(
            f"A folha {rotulo} está fora do Livro n. {livro['numero']}, que vai "
            f"da folha {inicio} à {limite}.")
    s = serie_de(livro["serie"])
    if verso and not s.usa_verso:
        raise LivroError(
            f"{s.nome} não escritura o verso — não há verso a inutilizar.")
    if bd.um(
            """SELECT 1 FROM nu_lugares
                WHERE livro_id=%s AND folha=%s AND verso=%s LIMIT 1""",
            (livro_id, folha, verso)):
        raise LivroError(
            f"A folha {rotulo} está escriturada. Folha escriturada não se "
            f"inutiliza — o ato nela é que se cancela.")
    teor = texto_termo_inutilizacao(livro["serie"], livro["numero"],
                                    rotulo_folha(folha, verso=bool(verso)),
                                    razao, sv, data_extenso)
    try:
        novo = bd.escrever(
            """INSERT INTO nu_inutilizacoes(livro_id, serie, folha, verso, rotulo,
                   motivo, teor, origem, inutilizado_em, inutilizado_por)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (livro_id, livro["serie"], folha, verso,
             rotulo_folha(folha, verso=bool(verso)), razao, teor, origem,
             agora, usuario))
    except sqlite3.IntegrityError:
        raise LivroError(f"A folha {rotulo} já está inutilizada.") from None
    return int(novo[0]["id"])


def inutilizar_sobra(con, tabela: str, referencia: int, *,
                     sv: dict, agora: str, data_extenso: str,
                     usuario: str | None = None) -> list[str]:
    """Inutiliza o que sobrou em branco por causa do ato. ESCREVE.

    A serie de folha inteira — as notas — deixa o verso da ultima folha em
    branco quando o teor da um numero impar de paginas. E essa a face que a
    inspecao cobra. Chamada depois do fecho, com o teor final ja conhecido.
    """
    bd = banco(con)
    lugar = lugar_de(bd, tabela, referencia)
    if not lugar:
        return []
    s = serie_de(lugar["serie"])
    sobra = LN.sobra_de(s, int(lugar["folha"]), int(lugar["paginas"] or 1))
    feitas = []
    for face in sobra:
        folha, verso = _face(face)
        if bd.um(
                """SELECT 1 FROM nu_inutilizacoes
                    WHERE livro_id=%s AND folha=%s AND verso=%s LIMIT 1""",
                (int(lugar["livro_id"]), folha, verso)):
            continue
        inutilizar(bd, int(lugar["livro_id"]), face,
                   motivo=(f"face em branco remanescente do ato de ordem "
                           f"n. {lugar['numero_ordem']}, que ocupou folhas "
                           f"inteiras"),
                   sv=sv, agora=agora, data_extenso=data_extenso,
                   usuario=usuario, origem="SOBRA")
        feitas.append(face)
    return feitas


# -------------------------------------------------------------- encerramento


def _faixa_do_livro(con,
                    livro_id: int) -> tuple[int | None, int | None, int | None]:
    """(primeiro numero, ultimo numero, ultima folha usada) do livro."""
    bd = banco(con)
    linha = bd.um(
        """SELECT MIN(numero_ordem) a, MAX(numero_ordem) b, MAX(folha) f
             FROM nu_lugares WHERE livro_id=%s""", (livro_id,))
    inut = bd.um(
        "SELECT MAX(folha) f FROM nu_inutilizacoes WHERE livro_id=%s",
        (livro_id,))
    folhas = [x for x in ((linha["f"] if linha else None),
                          (inut["f"] if inut else None)) if x is not None]
    return ((linha["a"] if linha else None), (linha["b"] if linha else None),
            max(folhas) if folhas else None)


def encerrar_livro(con, livro_id: int, *, sv: dict,
                   agora: str, data_extenso: str, usuario: str | None = None,
                   motivo: str | None = None) -> str:
    """Encerra o livro com termo. ESCREVE. Devolve o teor do termo."""
    bd = banco(con)
    # Confere "ja encerrado", conta os atos e fecha: a mesma trava de quem
    # reserva o lugar, senao o ato reservado ao mesmo tempo fica fora do termo.
    bd.travar("nu_lugares.lugar")
    livro = bd.um("SELECT * FROM nu_livros WHERE id=%s", (livro_id,))
    if not livro:
        raise LivroError("Livro não encontrado.")
    if int(livro["encerrado"] or 0):
        raise LivroError(
            f"O Livro n. {livro['numero']} já está encerrado desde "
            f"{livro['encerramento'] or 'data não gravada'}.")
    primeiro, ultimo, ultima_usada = _faixa_do_livro(bd, livro_id)
    inutilizadas = int(bd.valor(
        "SELECT COUNT(*) n FROM nu_inutilizacoes WHERE livro_id=%s",
        (livro_id,)))
    teor = texto_termo_encerramento(
        livro["serie"], livro["numero"], int(livro["folhas"] or 1),
        ultima_usada, primeiro, ultimo, sv, data_extenso,
        folha_inicial=int(livro["folha_inicial"] or 1), motivo=motivo,
        inutilizadas=inutilizadas)
    bd.escrever(
        """UPDATE nu_livros SET encerrado=1, encerramento=%s, termo_encerramento=%s,
                                motivo_encerramento=%s WHERE id=%s""",
        (agora, teor, (motivo or "").strip() or None, livro_id))
    return teor


def encerrar_o_dia(con, serie: str, dia: str, *, sv: dict,
                   agora: str, dia_extenso: str,
                   usuario: str | None = None) -> dict:
    """Encerra o dia no livro diario — protocolo de Protesto, RCPJ e RTD.

    Dia sem movimento tambem se encerra: o termo diz "nao houve movimento", e
    isso e o que distingue dia parado de dia nao escriturado.
    """
    s = serie_de(serie)
    if not s.diario:
        raise LivroError(
            f"{s.nome} não é livro diário — encerra quando enche, não no fim "
            f"do dia.")
    bd = banco(con)
    # Confere "ja encerrado", conta os protocolos do dia e fecha: a mesma trava
    # de quem reserva o lugar, senao o protocolo do mesmo dia fica fora do termo.
    bd.travar("nu_lugares.lugar")
    ja = bd.um(
        "SELECT * FROM nu_encerramentos_diarios WHERE serie=%s AND dia=%s",
        (serie, dia))
    if ja:
        raise LivroError(
            f"O dia {dia} de {s.nome} já foi encerrado em {ja['encerrado_em']}.")
    # O MÊS ASSINADO FECHA (23/10/2026): um termo lavrado depois da assinatura
    # ficaria ao lado dos que o delegatário assinou sem ter sido assinado.
    import encerramento_mensal as EM
    assinado = EM.mes_assinado(bd, serie, dia)
    if assinado:
        raise LivroError(
            f"Os termos de {EM.nome_do_mes(assinado)} de {s.nome} já foram "
            f"juntados e assinados pelo delegatário. O dia {dia} não recebe "
            f"mais termo.")
    livro = bd.um(
        """SELECT * FROM nu_livros WHERE serie=%s AND dia=%s
            ORDER BY id DESC LIMIT 1""", (serie, dia))
    livro_id = int(livro["id"]) if livro else None
    if livro_id:
        primeiro, ultimo, _ = _faixa_do_livro(bd, livro_id)
        quantos = int(bd.valor(
            "SELECT COUNT(*) n FROM nu_lugares WHERE livro_id=%s AND inicio=1",
            (livro_id,)))
    else:
        primeiro = ultimo = None
        quantos = 0
    teor = texto_encerramento_diario(serie, dia_extenso, quantos, primeiro,
                                     ultimo, sv)
    bd.escrever(
        """INSERT INTO nu_encerramentos_diarios(serie, dia, livro_id, primeiro,
               ultimo, quantidade, teor, encerrado_em, encerrado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (serie, dia, livro_id, primeiro, ultimo, quantos, teor, agora, usuario))
    if livro_id and not int(livro["encerrado"] or 0):
        bd.escrever(
            """UPDATE nu_livros SET encerrado=1, encerramento=%s,
                                    termo_encerramento=%s,
                                    motivo_encerramento=%s WHERE id=%s""",
            (agora, teor, "encerramento diário", livro_id))
    return {"dia": dia, "serie": serie, "livro_id": livro_id,
            "quantidade": quantos, "primeiro": primeiro, "ultimo": ultimo,
            "teor": teor}


def dias_sem_encerrar(con, serie: str) -> list[str]:
    """Os dias com movimento e sem termo de encerramento. So LE.

    E a tela que a inspecao pede: nao basta encerrar, tem de dar para provar
    que nao ficou dia aberto atras.
    """
    s = serie_de(serie)
    if not s.diario:
        return []
    return [r["dia"] for r in banco(con).ler(
        """SELECT DISTINCT l.dia dia FROM nu_livros l
            WHERE l.serie=%s AND l.dia IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM nu_encerramentos_diarios e
                               WHERE e.serie=l.serie AND e.dia=l.dia)
            ORDER BY l.dia""", (serie,))]


# ------------------------------------------------------------- conferencia


def conferir_livro(con, livro_id: int) -> dict:
    """O que esta errado no livro, em linguagem de balcao. So LE.

    Devolve `achados`: lista de frases. Lista vazia e livro em ordem.
    """
    bd = banco(con)
    livro = bd.um("SELECT * FROM nu_livros WHERE id=%s", (livro_id,))
    if not livro:
        raise LivroError("Livro não encontrado.")
    s = serie_de(livro["serie"])
    achados: list[str] = []

    if not (livro["termo_abertura"] or "").strip():
        achados.append("O livro não tem termo de abertura (art. 30, I, da Lei 8.935/1994).")
    if int(livro["encerrado"] or 0) and not (livro["termo_encerramento"] or "").strip():
        achados.append("O livro está encerrado sem termo de encerramento.")

    inicio, limite = int(livro["folha_inicial"] or 1), ultima_folha(livro)
    ocupadas = faces_ocupadas(bd, livro_id)
    usadas = {f for f, _ in ocupadas}
    if usadas:
        buracos = [f for f in range(inicio, max(usadas)) if f not in usadas]
        if buracos:
            achados.append(
                f"{len(buracos)} folha(s) em branco no meio do livro, sem termo "
                f"de inutilização: "
                f"{', '.join(str(x) for x in buracos[:10])}"
                f"{' …' if len(buracos) > 10 else ''}.")
        if s.usa_verso and s.folha_nova:
            versos = {f for f, v in ocupadas if v}
            frentes = {f for f, v in ocupadas if not v}
            soltos = sorted(f for f in frentes
                            if f not in versos and f < max(usadas))
            if soltos:
                achados.append(
                    f"{len(soltos)} verso(s) em branco entre folhas escrituradas: "
                    f"{', '.join(f'{x}v' for x in soltos[:10])}"
                    f"{' …' if len(soltos) > 10 else ''}.")
    if int(livro["encerrado"] or 0):
        sobrando = [f for f in range(inicio, limite + 1) if f not in usadas]
        if sobrando and not (livro["termo_encerramento"] or "").strip():
            achados.append(
                f"{len(sobrando)} folha(s) ficaram em branco em livro encerrado.")

    repetidos = [r["numero_ordem"] for r in bd.ler(
        """SELECT numero_ordem FROM nu_lugares
            WHERE livro_id=%s AND inicio=1 AND numero_ordem IS NOT NULL
            GROUP BY numero_ordem HAVING COUNT(*) > 1
            ORDER BY numero_ordem""", (livro_id,))]
    if repetidos:
        achados.append(
            f"Número de ordem repetido no livro: "
            f"{', '.join(str(x) for x in repetidos[:10])}.")

    if s.diario and livro["dia"] and not bd.um(
            "SELECT 1 FROM nu_encerramentos_diarios WHERE serie=%s AND dia=%s",
            (livro["serie"], livro["dia"])):
        achados.append(f"O dia {livro['dia']} não tem termo de encerramento diário.")

    return {
        "livro_id": livro_id,
        "serie": livro["serie"],
        "serie_nome": s.nome,
        "numero": livro["numero"],
        "folhas": int(livro["folhas"] or 0),
        "faces_ocupadas": len(ocupadas),
        "inutilizadas": int(bd.valor(
            "SELECT COUNT(*) n FROM nu_inutilizacoes WHERE livro_id=%s",
            (livro_id,))),
        "atos": int(bd.valor(
            "SELECT COUNT(*) n FROM nu_lugares WHERE livro_id=%s AND inicio=1",
            (livro_id,))),
        "encerrado": bool(int(livro["encerrado"] or 0)),
        "achados": achados,
    }


def panorama(con,
             atribuicao: int | str | None = None) -> list[dict]:
    """Uma linha por serie: livro aberto, folha livre, proximo numero. So LE.

    E a tela de onde o oficial ve as seis atribuicoes de uma vez.
    """
    series = (LN.series_da(atribuicao) if atribuicao is not None else LN.SERIES)
    bd = banco(con)
    linhas = []
    for codigo, s in series.items():
        aberto = bd.um(
            """SELECT * FROM nu_livros WHERE serie=%s AND encerrado=0 AND ativo=1
                ORDER BY id DESC LIMIT 1""", (codigo,))
        linhas.append({
            "serie": codigo,
            "atribuicao": s.atribuicao,
            "nome": s.nome,
            "diario": s.diario,
            "livro_id": int(aberto["id"]) if aberto else None,
            "livro_numero": aberto["numero"] if aberto else None,
            "dia": aberto["dia"] if aberto else None,
            "folha_livre": folha_livre(bd, aberto) if aberto else None,
            "folhas": int(aberto["folhas"]) if aberto else s.folhas,
            "proximo_numero": (
                proximo_numero(bd, codigo, consumir=False,
                               dia=(aberto["dia"] if aberto else None))
                if not (s.numeracao_diaria and not aberto) else 1),
            "livros": int(bd.valor(
                "SELECT COUNT(*) n FROM nu_livros WHERE serie=%s",
                (codigo,))),
            "atos": int(bd.valor(
                "SELECT COUNT(*) n FROM nu_lugares WHERE serie=%s AND inicio=1",
                (codigo,))),
        })
    return linhas
