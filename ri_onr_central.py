"""O que esta casa manda À CENTRAL do ONR — o indicador real e o edital.

    «siga no desenvolvimento das integrações até terminar de todas» — o
    oficial, 03/09/2026

**NÃO CONFUNDIR COM `ri_onr.py`, E O NOME DOS DOIS DIZ POR QUÊ.** Aquele gera
os **arquivos** do ONR — o Indicador Pessoal em XML e o Indicador Real em JSON
—, e o formato dele **foi levantado dos arquivos que esta serventia realmente
enviou**, em `arquivos\\eoficio\\ONR`. Este fala com a **API**.

> **E EU ESCREVI POR CIMA DAQUELE MÓDULO, em 03/09/2026.** Dei ao meu o nome
> `ri_onr.py` sem conferir se ele existia — e existia, com `TIPO_IMOVEL_ONR`,
> `gerar_indicador_pessoal`, `gerar_indicador_real` e `nome_arquivo`, os quatro
> importados por `ri_web`. Quem avisou foi o `ImportError` ao carregar o `app`;
> o original voltou do `.cgu` da 3.6.65. **A regra que fica: antes de criar
> arquivo, veja se o nome está livre** — e a ferramenta diz «atualizado» em vez
> de «criado» quando não está.

**E OS DOIS TÊM TABELAS DE TIPO DE IMÓVEL DIFERENTES, o que é o achado que
importa.** O arquivo usa `TIPO_IMOVEL_ONR`, com os códigos **0 a 9** do
`tbRI_TipoImovel.onr_id` do E-Ofício; a API usa **64 = Casa, 65 = Apto,
15 = Loja, 71 = Terreno/Fração**… Elas **não são a mesma tabela**, e usar uma
pela outra poria «Loja» onde é «Casa» no índice que o país consulta. É a lição
da «mesma palavra em dois lugares», agora entre dois canais da mesma Central.

Fica entre o **livro desta casa** e a Central do Registro de Imóveis:

    matrícula  →  indicador real  →  fila do ONR  →  aceito
    usucapião  →  edital          →  número       →  o prazo começa a correr

**A RECUSA DIZ QUAL CAMPO FALTA E ONDE ELE SE PREENCHE**, porque o conserto de
cada um é numa tela diferente: o endereço se completa na ficha da matrícula, o
CNS em Configurações, e o tipo do imóvel é uma escolha do balcão.

**ESTE MÓDULO NÃO LAVRA ATO, PELA SEXTA VEZ** — depois do usucapião, das
fraudes, do CNIB, da CENPROT e da Central de Certidões. O que ele faz é **dar
publicidade** ao que já está no livro: o indicador real é o índice, e o edital
é a publicação. Excluir um indicador **no ONR** não apaga matrícula nenhuma
aqui, e cancelar um edital não desfaz o processo de usucapião.

**ENVIAR NÃO É SER ACEITO.** O ONR recebe e processa **depois**, numa fila
própria. `ENVIADO` e `ACEITO` são duas situações, e confundi-las seria o defeito
do e-Proclamas noutra forma — lá HTTP 200 foi lido como publicação feita.

**A CHAMADA DE REDE NUNCA ACONTECE DENTRO DE `db.transaction()`.** As funções
que falam com o ONR recebem `db`, e não `con`.

O QUE O CONTRATO EXIGE E A CASA NÃO TEM
    De doze campos obrigatórios do indicador real, **onze** saem da ficha da
    matrícula. O décimo segundo é `situacaoConstrucao`, e **esta casa não o
    guarda em coluna nenhuma** — medido nas 50 colunas de `ri_matriculas`.

    Ele vai como **«Não se aplica»**, que é o menos afirmativo dos três, **e a
    tela diz isso antes de enviar**, com a caixa para trocar. Não dava para
    deixar em branco: o contrato o declara obrigatório, e uma tela que exigisse
    a escolha em cada uma das 1.701 matrículas não seria usada.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from collections import Counter
from typing import Any

import onr_api as API
import ri_onr_central_schema as ESQ
from bd_nativo import banco

# **OS VOCABULÁRIOS MORAM EM `onr_api`, E NÃO AQUI.** Eles são transcritos do
# contrato por `tools/gerar_logradouros.py`, e uma segunda cópia neste módulo
# divergiria no primeiro conserto — é a lição da `normalizar_nome` pela quinta
# vez. O que este módulo faz é **casar o texto da casa** com eles, pelo nome,
# sem acento e sem caixa; e o que não casar **fica declarado**, porque não se
# inventa código.

# A LOCALIZAÇÃO: o `rural_urbano` da casa para o 1/3 do ONR. **O catálogo pula
# o 2** — ver `onr_api.LOCALIZACOES`.
LOCALIZACAO_POR_NOME: dict[str, int] = {
    "urbano": 1, "urbana": 1, "u": 1,
    "rural": 3, "r": 3,
}

# O QUE VAI EM `situacaoConstrucao` QUANDO NINGUÉM ESCOLHEU. Ver o cabeçalho.
SITUACAO_DE_CONSTRUCAO_PADRAO = 2   # «Não se aplica»

# O TIPO DE REGISTRO. A casa escritura em Livro 2 (matrícula); transcrição é
# livro antigo. **Não se deduz do que não se mediu**: o que não for livro 2
# vira aviso, e continua indo como matrícula, que é o que o livro desta casa é.
TIPO_DE_REGISTRO_PADRAO = 1   # «Matrícula»


class OnrRIError(ValueError):
    """Recusa de regra, com a frase pronta para o balcão."""


def ambiente() -> str:
    """O ambiente em que esta casa fala com o ONR."""
    return API.ambiente_da_casa()


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _digitos(v: Any) -> str:
    return re.sub(r"\D", "", _texto(v))


def _hash(corpo: dict) -> str:
    return hashlib.sha256(
        json.dumps(corpo, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _sem_vazios(d: dict) -> dict:
    """Tira do corpo o que ficou em branco. **Campo ausente não afirma nada.**"""
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


# ------------------------------------------------------------- o endereço


def partir_logradouro(texto: Any) -> dict:
    """`"Rua das Flores"` → `{tipo_codigo: 81, tipo_nome: "Rua",
    logradouro: "das Flores"}`.

    **O tipo é a primeira palavra, e só vale se estiver no catálogo do ONR.**
    Quando não estiver, `tipo_codigo` volta `None` e o logradouro vai inteiro —
    e a conferência diz que falta, porque os dois lados do contrato o exigem.

    > **Isto NÃO é partir endereço em seis campos**, que é o que o e-Proclamas
    > se recusou a fazer. Ali a casa tinha **um** campo de texto livre com o
    > endereço todo, e cortar por vírgulas poria o bairro no logradouro. Aqui a
    > casa já guarda `logradouro`, `numero_predial`, `bairro`, `cidade`, `uf` e
    > `cep` **em colunas separadas**, e o que falta é só a primeira palavra do
    > logradouro — que é o próprio tipo, e está no catálogo medido.

    O catálogo tem nomes de duas palavras («Via Expressa», «Rua de Pedestre»),
    e por isso se tenta **da maior para a menor**: pegar só a primeira palavra
    faria «Via Expressa Norte» virar tipo «Via» com logradouro «Expressa Norte».
    """
    cru = _texto(texto)
    if not cru:
        return {"tipo_codigo": None, "tipo_nome": "", "logradouro": ""}
    palavras = cru.split()
    for quantas in (3, 2, 1):
        if len(palavras) <= quantas:
            continue
        tentativa = " ".join(palavras[:quantas])
        codigo = API.CODIGO_DO_LOGRADOURO.get(API.sem_acento(tentativa))
        if codigo is not None:
            return {"tipo_codigo": codigo,
                    "tipo_nome": API.TIPOS_DE_LOGRADOURO[codigo],
                    "logradouro": " ".join(palavras[quantas:])}
    return {"tipo_codigo": None, "tipo_nome": "", "logradouro": cru}


def _endereco_do_edital(fonte: dict, avisos: list[str], de_quem: str) -> dict:
    """O bloco de endereço do **edital** — ali o tipo é o NOME, e não o código.

    Mesmo nome de campo, dois tipos, no mesmo contrato: `string max=16` aqui e
    `integer` no indicador real.
    """
    partido = partir_logradouro(fonte.get("logradouro"))
    if not partido["tipo_nome"]:
        avisos.append(
            f"O logradouro {de_quem} («{fonte.get('logradouro') or 'vazio'}») "
            f"não começa por um tipo que o ONR conheça, e o edital exige o "
            f"tipo. Escreva-o à frente — «Rua», «Avenida», «Travessa».")
    return _sem_vazios({
        "cep": _digitos(fonte.get("cep"))[:8],
        "tipoLogradouro": partido["tipo_nome"][:16],
        "logradouro": partido["logradouro"][:150],
        "numero": _texto(fonte.get("numero"))[:10],
        "bairro": _texto(fonte.get("bairro"))[:100],
        "cidade": _texto(fonte.get("cidade"))[:100],
        "estado": _texto(fonte.get("uf"))[:2].upper(),
    })


# ------------------------------------------------------- o indicador real


def montar_indicador(con: sqlite3.Connection, matricula_id: int, *, cns: Any,
                     situacao_construcao: Any = None,
                     tipo_imovel: Any = None) -> dict:
    """Monta o corpo do indicador real. **SÓ CALCULA — não grava nem manda.**

    Devolve `{corpo, avisos, impedem, matricula}`.
    """
    bd = banco(con)
    linha = bd.um("SELECT * FROM ri_matriculas WHERE id=%s",
                  (int(matricula_id),))
    if not linha:
        raise OnrRIError(f"A matrícula {matricula_id} não existe.")
    m = dict(linha)
    avisos: list[str] = []
    impedem: list[str] = []

    partido = partir_logradouro(m.get("logradouro"))
    if partido["tipo_codigo"] is None:
        impedem.append(
            f"O logradouro («{m.get('logradouro') or 'vazio'}») não começa por "
            f"um tipo que o ONR conheça, e ele é obrigatório. Escreva-o à "
            f"frente na ficha da matrícula — «Rua», «Avenida», «Travessa».")

    codigo_imovel = _codigo_do_imovel(tipo_imovel or m.get("tipo_imovel"))
    if codigo_imovel is None:
        impedem.append(
            f"O tipo do imóvel («{tipo_imovel or m.get('tipo_imovel') or ''}») "
            f"não é um dos dez que o ONR aceita: "
            + ", ".join(sorted(API.TIPOS_DE_IMOVEL.values())) + ".")

    localizacao = LOCALIZACAO_POR_NOME.get(
        API.sem_acento(m.get("rural_urbano")))
    if localizacao is None:
        impedem.append(
            "A matrícula não diz se o imóvel é urbano ou rural, e o ONR exige. "
            "Preencha na ficha.")

    for campo, rotulo in (("cep", "CEP"), ("bairro", "bairro"),
                          ("cidade", "cidade"), ("uf", "UF"),
                          ("numero_predial", "número")):
        if not _texto(m.get(campo)):
            impedem.append(
                f"Falta o {rotulo} na ficha da matrícula, e o ONR o exige.")

    if not _digitos(cns):
        impedem.append(
            "O CNS da serventia não está configurado. Informe em "
            "Administrativo → Configurações.")

    situacao = situacao_construcao
    if situacao in (None, ""):
        situacao = SITUACAO_DE_CONSTRUCAO_PADRAO
        avisos.append(
            "Vai como «Não se aplica» na situação da construção: **esta casa "
            "não guarda isso em coluna nenhuma**, e o ONR o exige. É o menos "
            "afirmativo dos três; troque acima se souber.")
    situacao = int(situacao)
    if situacao not in API.SITUACOES_DE_CONSTRUCAO:
        impedem.append(
            "A situação da construção tem de ser uma das três: "
            + ", ".join(f"{c} = {n}"
                        for c, n in API.SITUACOES_DE_CONSTRUCAO.items()) + ".")

    if _texto(m.get("livro_norm")) and not _texto(
            m.get("livro_norm")).startswith("2"):
        avisos.append(
            f"Esta ficha está no livro «{m.get('livro')}», e vai como "
            f"«Matrícula». Transcrição e Torrens têm código próprio no ONR — "
            f"se for o caso, é aqui que se conserta.")

    proprietarios, atos = _proprietarios(bd, matricula_id), []
    if not proprietarios:
        avisos.append(
            "Nenhum proprietário ativo está gravado nesta matrícula, e o "
            "indicador vai sem eles — que é justamente o que o índice real "
            "existe para publicar.")
    atos, sem_codigo, sem_dados = _atos(bd, matricula_id)
    if sem_codigo:
        avisos.append(
            "Estes atos **não vão**, porque a natureza deles não casa com "
            "nenhum dos códigos do ONR: " + ", ".join(sem_codigo) + ".")
    if sem_dados:
        avisos.append(
            "Estes atos **não vão**, porque o ONR exige a data do título e o "
            "valor declarado de cada ato, e a ficha não os tem: "
            + ", ".join(sem_dados) + ". O indicador sobe sem eles, como o "
            "sistema antigo mandava.")
    if _texto(m.get("registro_anterior")):
        avisos.append(
            "O registro anterior está gravado como texto («"
            + _texto(m.get("registro_anterior"))[:60]
            + "…»), e o ONR o quer repartido em número, tipo e CNS. **Ele não "
              "vai** — repartir por conta própria poria o número de um livro "
              "no lugar do outro.")

    # **A ÁREA DO CONTRATO É EM METROS QUADRADOS, E A FICHA GUARDA HECTARE** — e
    # este campo ia com o **número cru** até 15/09/2026. Medido nas 1.387
    # matrículas com unidade de hectare: a 2580 tem `63 ha` e ia ao índice
    # nacional como **63 m²**, dez mil vezes menos, num número que diz de quem é
    # o imóvel e de que tamanho ele é. `API.area_em_metros` é a **mesma** função
    # que a proposta do endereço usa — **uma definição só na casa**, e era ela que
    # faltava ser chamada aqui.
    area = API.area_em_metros(m.get("area_valor"), m.get("area_unidade"))
    if _texto(m.get("area_valor")) and area is None:
        avisos.append(
            f"A área da ficha («{_texto(m.get('area_valor'))} "
            f"{_texto(m.get('area_unidade'))}») **não vai**: são quatro ou cinco "
            f"dígitos sem separação, e ali não dá para saber se é hectares ou "
            f"metros quadrados — chutar erra por cem vezes. Escreva a vírgula na "
            f"ficha («38,08» ou «3.808,00») e ela sobe.")

    corpo = _sem_vazios({
        "cns": _digitos(cns),
        "cnm": _texto(m.get("cnm")),
        "numeroRegistro": _inteiro(m.get("numero")),
        "tipoRegistro": TIPO_DE_REGISTRO_PADRAO,
        "dataAbertura": _texto(m.get("data_abertura")),
        "cep": _digitos(m.get("cep"))[:8],
        "tipoLogradouro": partido["tipo_codigo"],
        "logradouro": partido["logradouro"],
        "numero": _texto(m.get("numero_predial")),
        "complemento": _texto(m.get("complemento_endereco")),
        "tipoImovel": codigo_imovel,
        "bairro": _texto(m.get("bairro")),
        "cidade": _texto(m.get("cidade")),
        "uf": _texto(m.get("uf")).upper(),
        "inscricaoMunicipal": _texto(m.get("inscricao_municipal")),
        "nirf": _texto(m.get("nirf")),
        "sncrCcir": _texto(m.get("ccir")),
        "car": _texto(m.get("car")),
        "area": area,
        "localizacao": localizacao,
        "proprietarios": proprietarios,
        "atos": atos,
    })
    # **O ZERO É RESPOSTA.** «Construção averbada» é o código 0, e
    # `_sem_vazios` o tiraria.
    corpo["situacaoConstrucao"] = situacao
    return {"corpo": corpo, "avisos": avisos, "impedem": impedem,
            "matricula": m, "pronto": not impedem}


def _codigo_do_imovel(texto: Any) -> int | None:
    """Do texto que a casa guarda para um dos dez códigos. `None` se não casa."""
    chave = API.sem_acento(texto)
    return API.CODIGO_DO_IMOVEL.get(chave) if chave else None


def _inteiro(v: Any) -> int | None:
    digitos = _digitos(v)
    return int(digitos) if digitos else None


def _proprietarios(con: sqlite3.Connection, matricula_id: int) -> list[dict]:
    """Quem é dono hoje. **`proprietario_ativo`, e não `proprietario`.**

    A segunda diz que a pessoa já foi dona; a primeira diz que ela é. Mandar as
    duas publicaria como proprietário quem vendeu — e o índice real é o que o
    país consulta para saber de quem é o imóvel.
    """
    return [
        _sem_vazios({"nome": _texto(r["nome"]),
                     "documento": _digitos(r["documento_numero"])})
        for r in banco(con).ler(
            "SELECT nome, documento_numero FROM ri_partes "
            "WHERE matricula_id=%s AND proprietario_ativo=1 ORDER BY id",
            (int(matricula_id),))
        if _texto(r["nome"])]


def _atos(con: sqlite3.Connection,
          matricula_id: int) -> tuple[list[dict], list[str]]:
    """Os atos que o ONR sabe nomear, e a lista dos que ele não sabe.

    **Ato que não casa não vai calado.** Sumir com ele faria o índice mostrar
    uma cadeia com buraco — e ninguém desconfia de uma lista que abre.
    """
    vao: list[dict] = []
    ficam: list[str] = []
    sem_dados: list[str] = []
    # `SELECT *` e `dict(r).get`, e não a coluna nomeada: `data_instrumento`
    # ainda NÃO EXISTE em `ri_atos` (medido em 10/10/2026), e quando o RI a
    # criar ela passa a valer sem mexer aqui.
    for r in banco(con).ler(
            "SELECT * FROM ri_atos WHERE matricula_id=%s AND COALESCE(cancelado,0)=0 "
            "ORDER BY id", (int(matricula_id),)):
        r = dict(r)
        rotulo = f"{_texto(r.get('tipo'))}-{_texto(r.get('numero'))}"
        natureza = _texto(r.get("natureza_titulo"))
        codigo = _codigo_do_ato(natureza)
        if codigo is None:
            ficam.append(rotulo + (f" ({natureza})" if natureza else ""))
            continue
        # O MANUAL DO ONR EXIGE A DATA DO TÍTULO E O VALOR DECLARADO EM CADA ATO
        # — lido em 10/10/2026 no «Manual de Integração com a API do Indicador
        # Real» (V.1, 20/07/2023, [RFI-01]: `dataInstrumento` e `valorDeclarado`
        # obrigatórios), e o `indicadorRealAtoRequest` do contrato diz o mesmo.
        # Até aqui o ato ia SEM os dois, e o ONR recusaria a matrícula inteira.
        # Data do título esta casa não guarda; valor, em 8 de 1.280 atos.
        # Inventar qualquer um dos dois poria no índice nacional um negócio que
        # não aconteceu — o ato fica de fora, e o aviso diz por quê. A lista de
        # atos é OPCIONAL, e o E-Ofício mandou o indicador sem ato nenhum.
        data_titulo = _texto(r.get("data_instrumento"))
        centavos = r.get("base_calculo_centavos")
        if not data_titulo or centavos is None:
            sem_dados.append(rotulo)
            continue
        vao.append(_sem_vazios({
            "tipo": codigo,
            "descricao": (_texto(r.get("teor"))[:500] or natureza),
            "dataInstrumento": data_titulo,
            "valorDeclarado": round(int(centavos) / 100, 2),
            "dataRegistro": _texto(r.get("data_ato")),
            "numero": _inteiro(r.get("numero")),
        }))
    return vao, ficam, sem_dados


def _codigo_do_ato(natureza: Any) -> int | None:
    """Da natureza do título para um dos 23 códigos. `None` se não casa."""
    chave = API.sem_acento(natureza)
    return API.CODIGO_DO_ATO.get(chave) if chave else None


def corpos_para_o_arquivo(con: sqlite3.Connection, matriculas: list[dict], *,
                          cns: Any) -> dict:
    """O que vai no XML do indicador, e o que fica de fora e por quê. SÓ LÊ.

    **O CORPO É O DE `montar_indicador`**, o mesmo da API: duas montagens
    divergiriam no primeiro conserto. Vai só a ficha pronta: a que não tem o que o
    ONR exige seria recusada lá, e aqui a tela diz o que falta.

    **TAMBÉM FICAM DE FORA** a ficha encerrada e a arquivada, que não são imóvel
    ativo, e o número que está em duas fichas: ele sairia repetido no índice, e
    qual das duas vale é de quem lê o livro.

    **A REGRA DA CASA NÃO ENTRA AQUI.** `onr_indicador_xml.completar_ficha` preenche
    os brancos para o arquivo inteiro do acervo, que é outra decisão; aqui sai o que
    a ficha diz.
    """
    from gestor_cargas_ri import NUMERO_DE_FICHA_ARQUIVADA
    vezes = Counter(_texto(m.get("numero")) for m in matriculas)
    corpos: list[dict] = []
    de_fora: list[dict] = []
    for m in matriculas:
        numero = _texto(m.get("numero"))
        if int(m.get("encerrada") or 0):
            motivos = ["A ficha está encerrada: não é imóvel ativo."]
        elif (_inteiro(numero) or 0) >= NUMERO_DE_FICHA_ARQUIVADA:
            motivos = ["É ficha arquivada, fora da sequência do livro."]
        elif vezes[numero] > 1:
            motivos = [f"O número {numero} está em {vezes[numero]} fichas, e sairia "
                       f"repetido no índice. Confira qual delas vale."]
        else:
            # A FICHA QUE NÃO SE MONTA NÃO DERRUBA AS OUTRAS, nem a tela.
            try:
                montado = montar_indicador(con, int(m["id"]), cns=cns)
            except Exception:                              # noqa: BLE001
                logging.getLogger(__name__).exception(
                    "indicador da matrícula %s", m.get("id"))
                motivos = ["Não deu para montar o indicador desta ficha. Abra-a e "
                           "confira o cadastro."]
            else:
                motivos = montado["impedem"]
                if not motivos:
                    corpos.append(montado["corpo"])
        if motivos:
            de_fora.append({"id": int(m["id"]), "numero": numero, "motivos": motivos})
    return {"corpos": corpos, "de_fora": de_fora}


# ---------------------------------------------------------------- o envio


def enviar_indicador(db, matricula_id: int, *, cns: Any, agora: str,
                     usuario: str | None = None, pasta=None, **campos) -> dict:
    """Manda o indicador real ao ONR e **grava o que se mandou**.

    A ordem é a de `proclamas.enviar`: conferir (leitura) → mandar (fora de
    transação) → gravar (transação curta).
    """
    with db.connect() as con:
        montado = montar_indicador(con, matricula_id, cns=cns, **campos)
    if montado["impedem"]:
        raise OnrRIError(" ".join(montado["impedem"]))

    feito = API.enviar_indicador(montado["corpo"], pasta=pasta)
    with db.transaction() as con:
        novo = banco(con).escrever(
            """INSERT INTO ri_onr_envios(especie, ambiente, matricula_id,
                   identificador, corpo_enviado, corpo_hash, resposta,
                   situacao, enviado_em, enviado_por)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (ESQ.INDICADOR, ambiente(), int(matricula_id),
             feito["hash"] or None,
             json.dumps(montado["corpo"], ensure_ascii=False),
             _hash(montado["corpo"]),
             json.dumps(feito.get("bruto"), ensure_ascii=False),
             ESQ.ENVIADO, agora, usuario))[0]["id"]
    return {"envio_id": int(novo), "identificador": feito["hash"],
            "hash": _hash(montado["corpo"])}


def atualizar_indicador(db, envio_id: int, *, cns: Any, agora: str,
                        usuario: str | None = None, pasta=None,
                        **campos) -> dict:
    """Corrige no ONR um indicador ja enviado. **Nao queima o identificador.**

    O caminho oposto e pior: excluir e mandar de novo daria um `hash` novo, e
    quem consultou o indice ficaria com um numero que nao aponta para nada.
    E a mesma razao do «Corrigir na Central» da certidao eletronica.
    """
    with db.connect() as con:
        envio = ler_envio(con, envio_id)
        if not envio:
            raise OnrRIError(f"O envio {envio_id} nao existe.")
        if envio["especie"] != ESQ.INDICADOR:
            raise OnrRIError("Este envio nao e um indicador real.")
        if not _texto(envio.get("identificador")):
            raise OnrRIError(
                "Este indicador nao tem identificador do ONR, e e por ele que "
                "se corrige.")
        montado = montar_indicador(con, int(envio["matricula_id"]), cns=cns,
                                   **campos)
    if montado["impedem"]:
        raise OnrRIError(" ".join(montado["impedem"]))

    resposta = API.atualizar_indicador(envio["identificador"],
                                       montado["corpo"], pasta=pasta)
    with db.transaction() as con:
        banco(con).escrever(
            "UPDATE ri_onr_envios SET corpo_enviado=%s, corpo_hash=%s, "
            "resposta=%s, situacao=%s WHERE id=%s",
            (json.dumps(montado["corpo"], ensure_ascii=False),
             _hash(montado["corpo"]),
             json.dumps(resposta, ensure_ascii=False),
             ESQ.ENVIADO, int(envio_id)))
    return {"envio_id": int(envio_id),
            "identificador": envio["identificador"],
            "hash": _hash(montado["corpo"])}


def o_que_o_onr_tem(*, pasta=None) -> Any:
    """A lista dos indicadores como **o ONR** os tem. So LE.

    Ela responde a pergunta que o rastro daqui nao responde: o que esta LA. Se
    as duas divergirem, quem manda e a de la — e e por isso que a tela mostra
    as duas.
    """
    return API.indicadores(pasta=pasta)


def porque_a_fila_recusou(envio: dict, *, pasta=None) -> Any:
    """O detalhe da linha da fila — inclusive o motivo da recusa. So LE."""
    chave = _texto(envio.get("fila_hash"))
    if not chave:
        raise OnrRIError(
            "Esta linha ainda nao passou pela fila do ONR — clique em "
            "«Conferir a fila» antes.")
    return API.detalhes_da_fila(chave, pasta=pasta)


# ---------------------------------------------------------------- o edital


def montar_edital(con: sqlite3.Connection, processo_id: int, *, sv: dict,
                  tipo_edital: Any, texto: Any = None) -> dict:
    """Monta o corpo do edital do usucapião. **SÓ CALCULA.**

    **`tipoEdital` NÃO SE ESCREVE AQUI**: a lista vem da própria Central
    (`/v1/edital/tipo`), e escrevê-la no código seria a lista à mão que
    envelhece na tarde em que se escreve.
    """
    bd = banco(con)
    linha = bd.um("SELECT * FROM us_processos WHERE id=%s",
                  (int(processo_id),))
    if not linha:
        raise OnrRIError(f"O processo de usucapião {processo_id} não existe.")
    p = dict(linha)
    avisos: list[str] = []
    impedem: list[str] = []

    if not _digitos(tipo_edital):
        impedem.append(
            "Escolha o tipo de edital. A lista vem da própria Central — o "
            "botão «Trazer os tipos» a busca.")

    cns = _digitos(sv.get("ri_cns"))
    if not cns:
        impedem.append(
            "O CNS da serventia não está configurado, e o edital o exige.")

    serventia = {
        "nomeOficial": _texto(sv.get("serventia_titular"))[:200],
        "cns": int(cns) if cns else None,
        "denominacao": _texto(sv.get("unit_name"))[:200],
        "endereco": _endereco_do_edital(
            {"logradouro": sv.get("serventia_endereco"),
             "cep": sv.get("serventia_cep"),
             "cidade": sv.get("ri_cidade"), "uf": sv.get("ri_uf"),
             "bairro": sv.get("serventia_bairro")},
            avisos, "da serventia"),
    }

    intimados, sem_documento = _intimados(bd, processo_id, avisos)
    if not intimados:
        impedem.append(
            "O edital não tem ninguém a intimar. Ele existe para chamar quem "
            "não foi encontrado — registre as notificações no processo antes.")
    if sem_documento:
        avisos.append(
            "Estes não vão, porque o ONR exige o documento de cada intimado: "
            + ", ".join(sem_documento) + ".")

    corpo = _sem_vazios({
        "tipoEdital": _inteiro(tipo_edital),
        "numeroMatricula": _texto(p.get("matricula_id") and
                                  _numero_da_matricula(bd, p["matricula_id"]))[:7],
        "numeroProtocolo": _texto(p.get("prenotacao"))[:20],
        "textoEdital": (_texto(texto) or _texto(p.get("imovel_descricao")))[:10000],
        "intimados": intimados,
        "primeiroRequerente": _sem_vazios({
            "nome": _texto(p.get("requerente_nome")),
            "documento": _digitos(p.get("requerente_documento"))}),
        "dadosServentia": _sem_vazios(serventia),
        "imovel": _endereco_do_edital(
            {"logradouro": p.get("imovel_endereco"),
             "cidade": p.get("imovel_municipio"), "uf": p.get("imovel_uf")},
            avisos, "do imóvel"),
    })
    return {"corpo": corpo, "avisos": avisos, "impedem": impedem,
            "processo": p, "pronto": not impedem}


def _numero_da_matricula(con: sqlite3.Connection, matricula_id: Any) -> str:
    linha = banco(con).um("SELECT numero FROM ri_matriculas WHERE id=%s",
                          (int(matricula_id),))
    return _texto(linha["numero"]) if linha else ""


def _intimados(con: sqlite3.Connection, processo_id: int,
               avisos: list[str]) -> tuple[list[dict], list[str]]:
    """Quem o edital chama. **Sai dos movimentos do processo.**

    O edital só cabe «caso frustradas as tentativas anteriores» — e é
    `us_movimentos` que guarda a tentativa, a forma e o resultado. Quem não
    tiver documento **não entra**, porque o ONR o declara obrigatório; e a
    lista dos que ficaram de fora sobe para a tela.
    """
    vao: list[dict] = []
    fora: list[str] = []
    vistos: set[str] = set()
    for r in banco(con).ler(
            "SELECT destinatario, destinatario_papel, endereco FROM "
            "us_movimentos WHERE processo_id=%s AND destinatario IS NOT NULL "
            "ORDER BY id", (int(processo_id),)):
        nome = _texto(r["destinatario"])
        if not nome or nome.casefold() in vistos:
            continue
        vistos.add(nome.casefold())
        # **O DOCUMENTO NÃO ESTÁ EM COLUNA PRÓPRIA** nos movimentos: o que há é
        # o nome e o endereço. Enquanto for assim, o intimado sem documento
        # fica de fora **e aparece na tela** — inventar um número seria pior.
        fora.append(nome)
    if fora:
        avisos.append(
            "Os intimados saem dos movimentos do processo, e ali **não há "
            "coluna de documento** — o ONR o exige em cada um. Enquanto ela "
            "não existir, o edital não sobe por esta tela.")
    return vao, fora


def publicar_edital(db, processo_id: int, *, sv: dict, tipo_edital: Any,
                    agora: str, texto: Any = None, usuario: str | None = None,
                    pasta=None) -> dict:
    """Publica o edital na Central. **É a chamada que faz o prazo correr.**

    Art. 755, § 1º do Código de Normas do TJMA: a data da publicação é o
    primeiro dia útil **depois da disponibilização na Central**, e os prazos
    contam do primeiro dia útil depois dessa data. O sistema já calculava esse
    prazo; **o que faltava era a disponibilização**.
    """
    with db.connect() as con:
        montado = montar_edital(con, processo_id, sv=sv,
                                tipo_edital=tipo_edital, texto=texto)
    if montado["impedem"]:
        raise OnrRIError(" ".join(montado["impedem"]))

    feito = API.gerar_edital(montado["corpo"], pasta=pasta)
    with db.transaction() as con:
        novo = banco(con).escrever(
            """INSERT INTO ri_onr_envios(especie, ambiente, processo_id,
                   identificador, corpo_enviado, corpo_hash, resposta,
                   situacao, enviado_em, enviado_por)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (ESQ.EDITAL, ambiente(), int(processo_id), feito["numero"] or None,
             json.dumps(montado["corpo"], ensure_ascii=False),
             _hash(montado["corpo"]),
             json.dumps(feito.get("bruto"), ensure_ascii=False),
             ESQ.ENVIADO, agora, usuario))[0]["id"]
    return {"envio_id": int(novo), "numero": feito["numero"]}


def cancelar_edital(db, envio_id: int, *, motivo: str, agora: str,
                    usuario: str | None = None, pasta=None) -> dict:
    """Cancela o edital **na Central**. Não desfaz o processo de usucapião."""
    texto = _texto(motivo)
    if len(texto) < 10:
        raise OnrRIError(
            "Escreva por que o edital foi cancelado. Ele foi publicado, e o "
            "prazo correu para quem o leu.")
    with db.connect() as con:
        envio = ler_envio(con, envio_id)
    if not envio:
        raise OnrRIError(f"O envio {envio_id} não existe.")
    if envio["especie"] != ESQ.EDITAL:
        raise OnrRIError("Este envio não é um edital.")
    if not _texto(envio.get("identificador")):
        raise OnrRIError(
            "Este edital não tem número da Central, e é por ele que se "
            "cancela.")
    API.cancelar_edital(envio["identificador"], pasta=pasta)
    with db.transaction() as con:
        banco(con).escrever(
            "UPDATE ri_onr_envios SET situacao=%s, cancelado_em=%s, "
            "cancelado_por=%s, cancelado_motivo=%s WHERE id=%s",
            (ESQ.CANCELADO, agora, usuario, texto, int(envio_id)))
    return {"envio_id": int(envio_id), "motivo": texto}


# ----------------------------------------------------------------- a fila


def conferir_a_fila(db, *, agora: str, pasta=None) -> dict:
    """Pergunta ao ONR o que aconteceu com o que subiu. **Rede fora da
    transação.**

    **Enviar não é ser aceito**, e é esta chamada que separa as duas. Sem ela,
    `ENVIADO` ficaria para sempre com cara de resolvido.
    """
    linhas = API.fila(pasta=pasta)
    if not isinstance(linhas, list):
        linhas = [linhas] if linhas else []
    conferidos, mudaram = 0, 0
    with db.transaction() as con:
        bd = banco(con)
        for item in linhas:
            if not isinstance(item, dict):
                continue
            ident = _texto(item.get("hash") or item.get("hashFila"))
            situacao = _texto(item.get("situacao") or item.get("status"))
            conferidos += 1
            nova = _situacao_da_fila(situacao)
            bd.escrever(
                "UPDATE ri_onr_envios SET fila_hash=%s, fila_situacao=%s, "
                "fila_conferida_em=%s, fila_resposta=%s, situacao=%s "
                "WHERE ambiente=%s AND identificador=%s AND situacao=%s",
                (ident or None, situacao or None, agora,
                 json.dumps(item, ensure_ascii=False), nova,
                 ambiente(),
                 _texto(item.get("identificador") or item.get("protocolo")
                        or ident),
                 ESQ.ENVIADO))
            mudaram += bd.linhas_afetadas
    return {"conferidos": conferidos, "mudaram": mudaram}


def _situacao_da_fila(texto: Any) -> str:
    """Traduz o que a fila diz. **O que não se reconhece continua `ENVIADO`.**

    Chutar «aceito» sobre uma palavra que não se conhece faria a casa dar por
    publicado o que o ONR recusou.
    """
    chave = API.sem_acento(texto)
    if not chave:
        return ESQ.ENVIADO
    if any(p in chave for p in ("erro", "recus", "rejeit", "falha", "invalid")):
        return ESQ.RECUSADO
    if any(p in chave for p in ("conclu", "aceit", "process", "sucesso",
                                "finaliz")):
        return ESQ.ACEITO
    return ESQ.ENVIADO


# -------------------------------------------------------------- consultas


def ler_envio(con: sqlite3.Connection, envio_id: int) -> dict | None:
    """Um envio ao ONR. Só LÊ."""
    return banco(con).um("SELECT * FROM ri_onr_envios WHERE id=%s",
                         (int(envio_id),))


def envios(con: sqlite3.Connection, *, especie: str | None = None,
           situacao: str | None = None, limite: int = 200) -> list[dict]:
    """O que já subiu, do mais novo. Só LÊ."""
    onde = ["ambiente=%s"]
    valores: list[Any] = [ambiente()]
    if especie:
        onde.append("especie=%s")
        valores.append(especie)
    if situacao:
        onde.append("situacao=%s")
        valores.append(situacao)
    valores.append(int(limite))
    return banco(con).ler(
        "SELECT * FROM ri_onr_envios WHERE " + " AND ".join(onde)
        + " ORDER BY id DESC LIMIT %s", valores)


def envios_da_matricula(con: sqlite3.Connection,
                        matricula_id: int) -> list[dict]:
    """O que já subiu daquela matrícula, do mais novo. Só LÊ."""
    return banco(con).ler(
        "SELECT * FROM ri_onr_envios WHERE matricula_id=%s ORDER BY id DESC",
        (int(matricula_id),))


def a_enviar(con: sqlite3.Connection, *, limite: int = 200) -> list[dict]:
    """As matrículas cujo indicador o ONR ainda não tem. Só LÊ.

    **Só as desta casa.** O acervo do E-Ofício veio de um sistema que já
    respondia ao ONR — e mandar setenta anos de livro como novidade encheria a
    fila deles com o que já está lá. É a regra «o acervo não vira atraso».
    """
    return banco(con).ler(
        """SELECT m.id, m.numero, m.cnm, m.livro, m.cidade, m.uf,
                  m.tipo_imovel, m.rural_urbano
             FROM ri_matriculas m
            WHERE m.tipo_ficha <> 'ACERVO'
              AND NOT EXISTS (SELECT 1 FROM ri_onr_envios e
                               WHERE e.matricula_id = m.id
                                 AND e.especie = %s
                                 AND e.ambiente = %s
                                 AND e.situacao <> %s)
            ORDER BY m.id DESC LIMIT %s""",
        (ESQ.INDICADOR, ambiente(), ESQ.RECUSADO, int(limite)))
