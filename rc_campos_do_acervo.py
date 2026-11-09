# -*- coding: utf-8 -*-
"""O que o acervo já trouxe, e a ficha ainda não mostra.

Medido em 07/09/2026 (`O_MODULO_DE_MODELOS_DO_EOFICIO.md`): dos 244 assentos
do E-Ofício, `hora_fato`, `cor_raca`, `causa_morte`, `local_sepultamento`,
`atestante`, `cpf_registrado` e outras colunas estavam em 0/244. O valor
estava em `rc_assentos.dados_json`, com o nome da coluna de lá
(`strHoraNascimento` em 192/192, `strCausaMorte` em 31/31, `bitEleitor` e
`bitPossuiBens` em 31/31). A carga grava o pacote e só depois copia um
pedaço para as colunas. `ON CONFLICT DO NOTHING` não volta para preencher
o que a primeira rodada deixou vazio.

A certidão de breve relato lê a coluna e, em alguns campos, o pacote. A
CRC lê a coluna. Sem a coluna, a hora não sai, a cor vira ignorada, o
óbito fica retido porque `POSSUIBENS` não tem S nem N, e o eleitor sobe
como ignorado mesmo com a resposta no pacote.

ESTE MÓDULO NÃO INVENTA E NÃO REESCREVE
    Coluna que já tem valor fica. Avô e avó não se separam de um texto
    «JOÃO e MARIA». CPF não ganha dígito. O código do local de nascimento
    do E-Ofício não vira código do IBGE — esse de-para mora noutra tabela.
    O município do parto não é a naturalidade: `strCidade` é onde a pessoa
    nasceu; `strMunicipioNascimento` é o do estabelecimento.

`completar` só calcula, para a carga e a quarentena enxergarem o pacote
antes de alguém gravar. `gravar` escreve o que falta, na abertura do banco
e no fim da carga do acervo, para a ficha mostrar o mesmo.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from bd_nativo import banco

# O que pode sair do pacote para a coluna. Fora daqui não se copia:
# nome, teor, matrícula, datas e número já entraram na carga, e um
# `acervo_transcrito` com avós em texto não é coluna.
COLUNAS = (
    "hora_fato", "local_fato_nome", "local_fato_endereco",
    "local_fato_municipio", "cor_raca", "dnv", "cpf_registrado",
    "regime_bens", "causa_morte", "local_sepultamento", "atestante",
    "atestante_documento", "numero_do", "titulo_eleitor",
    "beneficio_social", "juiz_de_paz", "naturalidade_declarada",
    "obito_eleitor", "obito_possui_bens", "ibge_gemeo",
    "ibge_local_obito", "ibge_natureza_obito", "registro_tardio",
    "gemeo_ordem",
)

# Chaves medidas em `rc_modelos_livres` e em `CRC_DE_PARA_MEDIDO.md`.
# A primeira que tiver texto ganha. Não se mistura espécie: a hora do
# óbito não preenche um nascimento.
_CHAVES = {
    "NASCIMENTO": {
        "hora_fato": ("strHoraNascimento", "tmHoraNascimento"),
        "local_fato_nome": ("strNomeLocal",),
        "local_fato_endereco": ("strLN_endereco",),
        "local_fato_municipio": ("strMunicipioNascimento",),
        "cor_raca": ("strRacaCor",),
        "dnv": ("strDeclaracaoNascidoVivo",),
        "cpf_registrado": ("strCPF", "strCPFNascido"),
    },
    "NATIMORTO": {
        "hora_fato": ("strHoraNascimento", "tmHoraNascimento", "strHoraObito"),
        "local_fato_nome": ("strNomeLocal", "strNomeLocalObito"),
        "local_fato_endereco": ("strLN_endereco", "strLogradouroFalecimento"),
        "local_fato_municipio": ("strMunicipioNascimento",
                                 "strMunicipioFalecimento"),
        "cor_raca": ("strRacaCor",),
        "dnv": ("strDeclaracaoNascidoVivo",),
        "causa_morte": ("strCausaMorte",),
        "local_sepultamento": ("strLocalSepultamento",),
        "numero_do": ("strNumeroDeclaracaoObito",),
        "atestante": ("strAtestantePrimario", "strNomeMedico"),
        "atestante_documento": ("strCRMAtestantePrimario", "strCRM",
                                "strDocumentoMedico"),
    },
    "CASAMENTO": {
        "hora_fato": ("strHoraCelebracao",),
        "local_fato_nome": ("strDescricaoLocal",),
        "regime_bens": ("strRegimeCasamento",),
        "juiz_de_paz": ("strNomeCelebrante",),
    },
    "OBITO": {
        "hora_fato": ("strHoraObito", "tmHoraObito"),
        "local_fato_nome": ("strNomeLocalObito",),
        "local_fato_endereco": ("strLogradouroFalecimento",),
        "local_fato_municipio": ("strMunicipioFalecimento",),
        "cor_raca": ("strRacaCor",),
        "causa_morte": ("strCausaMorte",),
        "local_sepultamento": ("strLocalSepultamento",),
        "atestante": ("strAtestantePrimario", "strNomeMedico"),
        "atestante_documento": ("strCRMAtestantePrimario", "strCRM",
                                "strDocumentoMedico"),
        "numero_do": ("strNumeroDeclaracaoObito",),
        "titulo_eleitor": ("strTituloEleitor",),
        "beneficio_social": ("strBeneficioSocial",),
        "cpf_registrado": ("strCPF",),
    },
}
_CHAVES["CASAMENTO_RELIGIOSO"] = _CHAVES["CASAMENTO"]

_ESPECIE_DA_PESSOA = {
    "NATIMORTO": "NASCIMENTO",
    "CASAMENTO_RELIGIOSO": "CASAMENTO",
}

_CPF_EXTRA = {
    "REGISTRADO": ("strCPF", "strCPFNascido"),
    "FALECIDO": ("strCPF",),
}

_CAMPOS_DA_PESSOA = (
    "sexo", "data_nascimento", "profissao", "nacionalidade",
    "naturalidade_cidade", "naturalidade_uf", "naturalidade_pais",
    "estado_civil", "endereco", "bairro", "cidade", "uf", "nome_pos",
    "documento_tipo", "documento_numero", "idade_no_fato",
)


def _texto(v: Any) -> str:
    if v is None or isinstance(v, (dict, list, bool)):
        return ""
    s = str(v).strip()
    if s.lower() in ("none", "null"):
        return ""
    return s


def _vazio(v: Any) -> bool:
    """Vazio é ausência. Zero não é vazio: código 0 e «não» são resposta."""
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def _presente(dados: dict, chave: str) -> bool:
    if chave not in dados:
        return False
    v = dados[chave]
    if v is None:
        return False
    if isinstance(v, str) and not v.strip():
        return False
    return True


def _pacote(assento: dict) -> tuple[dict | None, str]:
    bruto = assento.get("dados_json")
    if isinstance(bruto, dict):
        return bruto, ""
    if _vazio(bruto):
        dados = assento.get("dados")
        if isinstance(dados, dict):
            return dados, ""
        return {}, ""
    try:
        dados = json.loads(bruto)
    except (TypeError, ValueError):
        return None, "json"
    if not isinstance(dados, dict):
        return None, "json"
    return dados, ""


def _primeira(dados: dict, chaves: tuple[str, ...]) -> str:
    for chave in chaves:
        if not _presente(dados, chave):
            continue
        texto = _texto(dados.get(chave))
        if texto:
            return texto
    return ""


def _marca(valor: Any) -> str:
    """`1`/`0`/`true` do E-Ofício viram SIM/NAO. O resto não se grava.

    `False` é `int` em Python, e `0.0` vindo de JSON não é o texto «0».
    Os dois se resolvem antes da régua, senão «não» do acervo ficaria
    como «não perguntado».
    """
    from rc_marcas_do_obito import NAO, SIM, normalizar
    if isinstance(valor, bool):
        valor = int(valor)
    elif isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    elif isinstance(valor, str):
        cru = valor.strip()
        if cru in ("0.0", "1.0"):
            valor = int(float(cru))
    estado = normalizar(valor)
    if estado in (SIM, NAO):
        return estado
    return ""


def codigo_ibge_do_local_escrito(texto: Any) -> int | None:
    """O código do IBGE quando o texto diz o tipo do lugar. Só calcula.

    Hospital e maternidade são 1. Posto de saúde é 2. Domicílio é 3.
    Aldeia e «lugar» rural são 5 (outros, fora de unidade de saúde).
    Cidade sem o tipo, vazio e «ignorado» ficam sem código: o SIRC não
    tem marcador de ignorado, e escolher um lado afirmaria o que ninguém
    escreveu. Vale o lugar escrito no campo, não o termo inteiro: no termo,
    «avós maternos» e o endereço do cartório não são o lugar do nascimento.
    """
    from ibge_schema import normalizar_nome
    t = normalizar_nome(texto)
    if not t or "ignorad" in t:
        return None
    unidade = (
        r"(?:^|[^a-z0-9])(?:"
        r"hospital|hosp(?:ital|\.|(?=\s))|maternidade|matern(?:\.|(?=\s))|"
        r"clinica|h\.?\s*r\.?\s*m\.?\s*i"
        r")(?:[^a-z0-9]|$)"
    )
    if re.search(unidade, t) or "alivio do sofrimento" in t \
            or "aluvio do sofrimento" in t or "casa pontificia" in t \
            or "casa de saude" in t:
        return 1
    if "posto de saude" in t or "posto saude" in t:
        return 2
    domicilio = (
        r"(?:^|[^a-z0-9])(?:"
        r"domicilio|domic(?:\.|(?=\s))|residencia|resid(?:\.|(?=\s))|em casa"
        r")(?:[^a-z0-9]|$)"
    )
    if re.search(domicilio, t):
        return 3
    rural = (
        r"(?:^|[^a-z0-9])(?:"
        r"aldeia|lugar|povoado|fazenda|faz(?:\.|(?=\s))"
        r")(?:[^a-z0-9]|$)"
    )
    if re.search(rural, t):
        return 5
    # «Sítio Novo» é município. O nome da cidade, sozinho, não diz o tipo.
    if re.search(r"(?:^|[^a-z0-9])sitio(?:[^a-z0-9]|$)", t) and "sitio novo" not in t:
        return 5
    return None


def _hora(valor: Any) -> str:
    from crc_carga import _hora as hora_crc
    return hora_crc(valor)


def completar(assento: dict, pessoas: dict | None = None,
              ) -> tuple[dict, dict]:
    """O assento e as pessoas com o que o pacote já tinha. Só calcula.

    Não muda os dicionários que recebeu. JSON que não abre devolve as
    cópias como chegaram — uma linha ruim não completa as outras com
    chute.
    """
    a = dict(assento)
    pessoas_saida = {k: dict(v) for k, v in (pessoas or {}).items()}
    dados, erro = _pacote(a)
    if erro or dados is None:
        return a, pessoas_saida
    _preencher_assento(a, dados)
    _preencher_pessoas(a, dados, pessoas_saida)
    return a, pessoas_saida


def _preencher_assento(a: dict, dados: dict) -> None:
    especie = _texto(a.get("especie")).upper()
    for coluna, chaves in _CHAVES.get(especie, {}).items():
        if not _vazio(a.get(coluna)):
            continue
        valor = _primeira(dados, chaves)
        if coluna == "hora_fato":
            valor = _hora(valor)
        if valor:
            a[coluna] = valor
    if especie == "OBITO":
        for coluna, chave in (("obito_eleitor", "bitEleitor"),
                              ("obito_possui_bens", "bitPossuiBens")):
            if _vazio(a.get(coluna)) and _presente(dados, chave):
                marca = _marca(dados.get(chave))
                if marca:
                    a[coluna] = marca
        if _vazio(a.get("ibge_local_obito")) and _presente(
                dados, "strTipoLocalObito"):
            from acervo_carga import _local_do_obito
            codigo = _local_do_obito(dados.get("strTipoLocalObito"))
            if codigo:
                a["ibge_local_obito"] = codigo
        if _vazio(a.get("ibge_natureza_obito")) and _presente(
                dados, "strTipoMorte"):
            from acervo_carga import (
                NATUREZA_DO_OBITO_POR_PALAVRA, _norm_ibge)
            codigo = NATUREZA_DO_OBITO_POR_PALAVRA.get(
                _norm_ibge(dados.get("strTipoMorte")))
            if codigo:
                a["ibge_natureza_obito"] = codigo
    if especie in ("NASCIMENTO", "NATIMORTO") and _vazio(a.get("ibge_local_nascimento")):
        codigo = codigo_ibge_do_local_escrito(a.get("local_fato_nome"))
        if codigo:
            a["ibge_local_nascimento"] = codigo
    if especie in ("NASCIMENTO", "NATIMORTO") and a.get("ibge_gemeo") is None:
        if _presente(dados, "bitGemeos") or _presente(
                dados, "intQuantidadeGemeos"):
            from acervo_carga import _gemeo_do_ibge
            a["ibge_gemeo"] = _gemeo_do_ibge(
                dados.get("bitGemeos"), dados.get("intQuantidadeGemeos"))
    if (_vazio(a.get("registro_tardio"))
            and _presente(dados, "bitRegistroTardio")
            and _marca(dados.get("bitRegistroTardio")) == "SIM"):
        a["registro_tardio"] = 1
    transcrito = dados.get("acervo_transcrito")
    if isinstance(transcrito, dict):
        _do_transcrito(a, transcrito)


def _do_transcrito(a: dict, transcrito: dict) -> None:
    """O lote transcrito guarda o par de avós em texto. Isso fica texto.

    Só entra chave que já é coluna desta lista. `avos_paternos` e
    `duvidas` não são, e não viram pessoa.
    """
    for coluna in COLUNAS:
        if coluna not in transcrito or not _vazio(a.get(coluna)):
            continue
        bruto = transcrito[coluna]
        if coluna in ("obito_eleitor", "obito_possui_bens"):
            marca = _marca(bruto)
            if marca:
                a[coluna] = marca
            continue
        if coluna == "hora_fato":
            hora = _hora(bruto)
            if hora:
                a[coluna] = hora
            continue
        if coluna == "registro_tardio":
            if _marca(bruto) == "SIM" or bruto == 1:
                a[coluna] = 1
            continue
        if coluna == "ibge_gemeo":
            try:
                codigo = int(bruto)
            except (TypeError, ValueError):
                continue
            if codigo in (1, 2, 3):
                a[coluna] = codigo
            continue
        if coluna in ("ibge_local_obito", "ibge_natureza_obito",
                      "gemeo_ordem"):
            try:
                a[coluna] = int(bruto)
            except (TypeError, ValueError):
                continue
            continue
        texto = _texto(bruto)
        if texto:
            a[coluna] = texto


def _preencher_pessoas(a: dict, dados: dict, pessoas: dict) -> None:
    from acervo_carga import O_PROPRIO_ASSENTO, _data, _sexo
    from acervo_carga import _nascimento_possivel

    especie = _texto(a.get("especie")).upper()
    mapa = _ESPECIE_DA_PESSOA.get(especie, especie)
    papeis = {papel: de_para
              for papel, _tabela, de_para in O_PROPRIO_ASSENTO.get(mapa, ())}
    for papel, nome in _quem_falta(especie, a, dados, pessoas):
        pessoas[papel] = {"papel": papel, "nome": nome}
    for papel, pessoa in pessoas.items():
        de_para = papeis.get(papel)
        if not de_para:
            continue
        for campo, chave in de_para.items():
            if campo == "nome" or not _vazio(pessoa.get(campo)):
                continue
            if not _presente(dados, chave):
                continue
            if campo == "sexo":
                sexo = _sexo(dados.get(chave))
                if sexo:
                    pessoa["sexo"] = sexo
                continue
            if campo == "data_nascimento":
                nascimento = _data(dados.get(chave))
                if nascimento and _data_cabe(a, nascimento,
                                             _nascimento_possivel):
                    pessoa["data_nascimento"] = nascimento
                continue
            if campo == "documento_numero":
                _por_cpf(pessoa, _texto(dados.get(chave)))
                continue
            texto = _texto(dados.get(chave))
            if texto:
                pessoa[campo] = texto
        for chave in _CPF_EXTRA.get(papel, ()):
            if _presente(dados, chave):
                _por_cpf(pessoa, _texto(dados.get(chave)))
                break
        if (papel == "FALECIDO" and _vazio(pessoa.get("idade_no_fato"))
                and _presente(dados, "intIdade")):
            from acervo_carga import _inteiro
            idade = _inteiro(dados.get("intIdade"))
            if idade is not None and idade >= 0:
                pessoa["idade_no_fato"] = str(idade)


def _data_cabe(assento: dict, nascimento: str, cabe) -> bool:
    datas = [d for d in (_texto(assento.get("data_fato"))[:10],
                         _texto(assento.get("data_ato"))[:10])
             if len(d) == 10]
    if not datas:
        return True
    return cabe(nascimento, min(datas))


def _por_cpf(pessoa: dict, numero: str) -> None:
    if not numero or not _vazio(pessoa.get("documento_numero")):
        return
    tipo = _texto(pessoa.get("documento_tipo")).upper()
    if tipo not in ("", "CPF"):
        return
    pessoa["documento_numero"] = numero
    if not tipo:
        pessoa["documento_tipo"] = "CPF"


def _quem_falta(especie: str, assento: dict, dados: dict,
                pessoas: dict) -> list[tuple[str, str]]:
    """O titular e os nubentes que o pacote nomeia e a ficha não tem.

    Pai, mãe e avós não entram por aqui. A filiação mora em outra tabela
    do acervo, e um texto «JOÃO e MARIA» não diz quem é o avô.
    """
    faltam: list[tuple[str, str]] = []
    if especie in ("NASCIMENTO", "NATIMORTO"):
        nome = _texto(assento.get("nome"))
        if nome and "REGISTRADO" not in pessoas:
            faltam.append(("REGISTRADO", nome))
    elif especie == "OBITO":
        nome = _texto(assento.get("nome"))
        if nome and "FALECIDO" not in pessoas:
            faltam.append(("FALECIDO", nome))
    elif especie in ("CASAMENTO", "CASAMENTO_RELIGIOSO"):
        for i, papel in ((1, "NUBENTE1"), (2, "NUBENTE2")):
            nome = _primeira(dados, (f"strNomeConjuge{i}",))
            if nome and papel not in pessoas:
                faltam.append((papel, nome))
    return faltam


def gravar_local_do_nascimento(con: sqlite3.Connection) -> int:
    """Grava o código do IBGE do lugar, quando o texto do assento já o diz.

    Não mexe em 1, 2, 3, 5 nem em 9 (ignorado). Um número de município
    parado nessa coluna não é código de tipo: o texto, se disser o tipo,
    substitui. Não preenche o que o texto não diz.
    ESCREVE. Devolve quantos nascimentos ganharam o código.
    """
    bd = banco(con)
    if not bd.tem_coluna("rc_assentos", "ibge_local_nascimento"):
        return 0
    linhas = bd.ler(
        """SELECT id, local_fato_nome FROM rc_assentos
            WHERE especie IN ('NASCIMENTO', 'NATIMORTO')
              AND (ibge_local_nascimento IS NULL
                   OR ibge_local_nascimento NOT IN (1, 2, 3, 5, 9))
            ORDER BY id""")
    n = 0
    for linha in linhas:
        codigo = codigo_ibge_do_local_escrito(linha["local_fato_nome"])
        if codigo is None:
            continue
        bd.escrever(
            "UPDATE rc_assentos SET ibge_local_nascimento=%s WHERE id=%s "
            "AND (ibge_local_nascimento IS NULL "
            "OR ibge_local_nascimento NOT IN (1, 2, 3, 5, 9))",
            (codigo, int(linha["id"])))
        n += 1
    return n


def gravar(con: sqlite3.Connection, *, agora: str | None = None) -> dict:
    """Copia para as colunas o que ainda falta. Não apaga o pacote.

    Idempotente: a segunda rodada não muda linha nenhuma. Assento cujo
    JSON não abre é pulado e contado em `erros`.

    No fim, a naturalidade que está no assento e falta na pessoa passa pela
    mesma função da tela (`rc_assento._naturalidade_do_titular`). Ela só
    grava município que o cadastro do IBGE confirma, e não mexe em pessoa
    que já tem cidade. É o que tirava da quarentena, em 22/09/2026, os
    nascimentos cuja naturalidade estava escrita no termo.
    """
    from datetime import datetime
    bd = banco(con)
    quando = agora or datetime.now().replace(microsecond=0).isoformat(
        timespec="seconds")
    assentos = pessoas_atualizadas = pessoas_novas = erros = 0
    linhas = bd.ler(
        """SELECT * FROM rc_assentos
            WHERE dados_json IS NOT NULL AND TRIM(dados_json) NOT IN ('', '{}')
            ORDER BY id""")
    for linha in linhas:
        a = dict(linha)
        dados, erro = _pacote(a)
        if erro or dados is None:
            erros += 1
            continue
        pessoas = _pessoas(bd, a["id"])
        novo, pessoas_novas_mapa = completar(a, pessoas)
        if _gravar_assento(bd, a, novo):
            assentos += 1
        atualizadas, novas = _gravar_pessoas(
            bd, a, pessoas, pessoas_novas_mapa, quando)
        pessoas_atualizadas += atualizadas
        pessoas_novas += novas
    pessoas_atualizadas += _gravar_naturalidade_declarada(con, bd)
    locais = gravar_local_do_nascimento(con)
    return {"assentos": assentos, "locais_de_nascimento": locais,
            "pessoas_atualizadas": pessoas_atualizadas,
            "pessoas_novas": pessoas_novas,
            "erros": erros}


def _gravar_naturalidade_declarada(con: sqlite3.Connection, bd) -> int:
    """Copia a naturalidade do termo para a pessoa, quando o IBGE confirma.

    A decisão de gravar não mora aqui: é `rc_assento._naturalidade_do_titular`,
    a mesma da tela e do script `tools/naturalidade_dos_assentos_do_rcpn.py`.
    Município parecido não entra. Pessoa que já tem cidade não é tocada.
    """
    import rc_assento as RC
    especies = tuple(RC.TITULAR_DA_NATURALIDADE)
    marcas = ", ".join("%s" for _ in especies)
    linhas = bd.ler(
        f"""SELECT id, especie, naturalidade_declarada FROM rc_assentos
            WHERE especie IN ({marcas})
              AND TRIM(COALESCE(naturalidade_declarada, '')) <> ''
            ORDER BY id""", especies)
    gravadas = 0
    for a in linhas:
        r = RC._naturalidade_do_titular(
            con, int(a["id"]), str(a["especie"] or "").upper(),
            a["naturalidade_declarada"])
        if r.get("gravou"):
            gravadas += 1
    return gravadas


def _pessoas(bd, assento_id: int) -> dict:
    saida: dict[str, dict] = {}
    for linha in bd.ler(
            "SELECT * FROM rc_pessoas WHERE assento_id=%s ORDER BY ordem, id",
            (int(assento_id),)):
        papel = _texto(linha["papel"]).upper()
        if papel and papel not in saida:
            saida[papel] = dict(linha)
    return saida


def _gravar_assento(bd, antes: dict, depois: dict) -> bool:
    pares = []
    for coluna in COLUNAS:
        if _vazio(antes.get(coluna)) and not _vazio(depois.get(coluna)):
            pares.append((coluna, depois[coluna]))
    if not pares:
        return False
    conjuntos = ", ".join(f"{coluna}=%s" for coluna, _ in pares)
    bd.escrever(
        f"UPDATE rc_assentos SET {conjuntos} WHERE id=%s",
        tuple(valor for _, valor in pares) + (antes["id"],))
    return True


def _gravar_pessoas(bd, assento: dict, antes: dict, depois: dict,
                    agora: str) -> tuple[int, int]:
    from acervo_carga import ORDEM_DO_PAPEL
    from pt_schema import normalizar_nome
    atualizadas = novas = 0
    for papel, pessoa in depois.items():
        antiga = antes.get(papel)
        if antiga is None:
            nome = _texto(pessoa.get("nome"))
            if not nome or assento.get("id") is None:
                continue
            origem = _texto(assento.get("origem")) or "EOFICIO"
            valores: dict[str, Any] = {
                "assento_id": assento["id"],
                "papel": papel,
                "nome": nome,
                "nome_norm": normalizar_nome(nome),
                "ordem": ORDEM_DO_PAPEL.get(papel, 0),
                "origem": origem,
                "origem_chave": f"dados_json:{assento['id']}:{papel}",
                "criado_em": agora,
            }
            for campo in _CAMPOS_DA_PESSOA:
                if not _vazio(pessoa.get(campo)):
                    valores[campo] = pessoa[campo]
            colunas = list(valores)
            marcas = ", ".join("%s" for _ in colunas)
            entrou = bd.valor(
                f"INSERT INTO rc_pessoas ({', '.join(colunas)}) "
                f"VALUES ({marcas}) ON CONFLICT DO NOTHING RETURNING id",
                tuple(valores[c] for c in colunas))
            if entrou:
                novas += 1
            continue
        pares = []
        for campo in _CAMPOS_DA_PESSOA:
            if _vazio(antiga.get(campo)) and not _vazio(pessoa.get(campo)):
                pares.append((campo, pessoa[campo]))
        if not pares:
            continue
        conjuntos = ", ".join(f"{campo}=%s" for campo, _ in pares)
        bd.escrever(
            f"UPDATE rc_pessoas SET {conjuntos} WHERE id=%s",
            tuple(valor for _, valor in pares) + (antiga["id"],))
        atualizadas += 1
    return atualizadas, novas
