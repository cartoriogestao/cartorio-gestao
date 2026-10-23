"""
A certidao de protesto — buscar pelo nome, dizer o que ha, e assinar.

E O QUE O BALCAO MAIS PEDE, e por muito tempo nao teve como responder: ate
25/08/2026 a carga do acervo trazia os 1.366 titulos e NENHUM devedor, e
certidao de protesto se pede pelo nome e pelo CPF de quem foi protestado.

OS TEXTOS SAO OS DA CASA, e nao redacao nova
    Medidos nas 65 certidoes de `tbProtesto_Certidao`: 46 negativas, 12 de
    cancelamento e 7 positivas. As frases abaixo sao as que sairam desta
    serventia por anos — a regra do oficial, de 24/08/2026: na duvida, faca
    como o E-Oficio fazia.

    Duas coisas foram escolhidas, e ficam ditas:

    1. "a requerimento VERBAL de parte interessada" e o que as 44 negativas
       dizem, e e o que sai quando ninguem informa o requerente. Informado o
       requerente, sai "a requerimento de FULANO" — dizer "verbal" quando o
       pedido foi escrito e assinado seria certificar o que nao houve.
    2. O fecho do cancelamento existe no acervo em duas formas, singular e
       plural ("no referido livro e folha consta a BAIXA" / "nos referidos
       livros e folhas constam as BAIXAS"). Sai a que couber na quantidade.
       A grafia e a da forma mais nova — "acordo", e nao "acôrdo".

O QUE ENTRA NA BUSCA
    So titulo que CHEGOU A PROTESTO: o que tem ato de PROTESTO lavrado.
    Apontamento nao e protesto — titulo apontado e pago no triduo nunca foi
    protestado, e certidao que o mostrasse seria certidao que mente contra a
    pessoa. Medido no acervo: dos 189 titulos pagos, so 4 tinham chegado a
    protesto.

A CERTIDAO NAO E ATO DE UM TITULO
    Por isso ela nao mora em `pt_atos`, cujo `titulo_id` e NOT NULL: a
    negativa nao tem titulo nenhum. Certidao e ato da SERVENTIA sobre uma
    pessoa. Numeracao por exercicio, teor congelado e hash — a mesma forma do
    recibo do caixa, que ja roda nesta casa.

O TEOR CONGELA NA EMISSAO
    Depois de emitida, a certidao nao se recalcula: o que ela disse e o que
    fica, com o sha256 para provar que a segunda via e a mesma folha. Protesto
    novo lavrado amanha nao muda a certidao de hoje — mudar seria reescrever o
    que a serventia ja afirmou.

FUNDAMENTO
    Lei 9.492/1997, arts. 27 e 31 (certidao), art. 26 (cancelamento).
    Codigo de Normas do Foro Extrajudicial do Maranhao — Prov. TJMA 28/2026.
"""
from __future__ import annotations
from certidao_texto import sem_linha_de_assinatura_a_mao

import hashlib
import json
import sqlite3
from typing import Any

import cancelamento_certidao as CANC
import protesto as PT
import protesto_pecas as PECAS
from bd_nativo import banco
from caixa_schema import reais
from pt_schema import normalizar_nome

TIPOS = ("NEGATIVA", "POSITIVA", "CANCELAMENTO")

# OS TRÊS TEXTOS DA CERTIDÃO SAÍRAM DAQUI NO LF06A (19/10/2026): moram em
# `modelos_padrao/protesto/PT_CERTIDAO_{NEGATIVA,POSITIVA,CANCELAMENTO}.txt`,
# com os MESMOS bytes, e chegam pela base dos padrões. Os nomes antigos
# (`MODELO_CERTIDAO_NEGATIVA`...) continuam respondendo — ver `__getattr__` no
# fim deste módulo.
#
# E AS FRASES QUE A REGRA ESCOLHE SAÍRAM NO LF06E (19/10/2026): o pedido
# (verbal, do requerente, do devedor, judicial), o nome com o documento, a
# abertura da positiva e do cancelamento («CERTIFICO … neles encontrei
# protesto contra …») e o fecho do art. 26 (um × vários) moram em
# `modelos_padrao/protesto/PT_CERTIDAO_*.txt`, e o oficial os edita na tela de
# Modelos. QUAL frase entra continua decidido aqui — ver `protesto_pecas`.
CHAVE_POR_TIPO = {"NEGATIVA": "PT_CERTIDAO_NEGATIVA",
                  "POSITIVA": "PT_CERTIDAO_POSITIVA",
                  "CANCELAMENTO": "PT_CERTIDAO_CANCELAMENTO"}


def _padrao(tipo: str) -> str:
    import modelos_da_casa as CASA
    return CASA.padrao_de(CHAVE_POR_TIPO[tipo])


def _frase(con: Any, chave: str, **claros: Any) -> str:
    """A peça da certidão, com o ajuste da casa (com `con`) ou o padrão."""
    return PECAS.montar(con, chave, CertidaoError, **claros)

# "Período de Busca: 5 Anos" — o que as negativas do acervo dizem, todas.
PERIODO_PADRAO_ANOS = 5

# O ENDOSSO QUE A CERTIDÃO DIZ (LD08): os códigos do leiaute da CRA que são
# endosso de fato — M mandato, T translativo (`protesto_cra.TIPOS_DE_ENDOSSO`).
# O «S» é «sem endosso», e não tem tipo. A palavra de cada um é a peça
# `PT_CERTIDAO_LINHA` (`endosso_M`, `endosso_T`), que o oficial edita.
ENDOSSOS_NA_CERTIDAO = ("M", "T")

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


class CertidaoError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcao."""


# --------------------------------------------------------------- utilidades


def _digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def tipo_do_documento(documento: Any) -> str | None:
    """CPF, CNPJ ou None — pelo tamanho, que aqui e definicao e nao chute.

    CPF tem 11 digitos e CNPJ tem 14; nao ha terceiro caso. Medido nos 1.366
    devedores do acervo: 980 com 11 e 386 com 14, nenhum com outro tamanho.
    """
    d = _digitos(documento)
    return "CPF" if len(d) == 11 else "CNPJ" if len(d) == 14 else None


def formatar_documento(documento: Any) -> str:
    """`04785512388` -> `047.855.123-88`. Sem tamanho conhecido, devolve como veio."""
    d = _digitos(documento)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return str(documento or "").strip()


def _por_extenso_ano(ano: int) -> str:
    """`2020` -> `dois mil e vinte`. So os anos que uma certidao alcanca."""
    unidades = ("", "um", "dois", "três", "quatro", "cinco", "seis", "sete",
                "oito", "nove")
    dez_a_dezenove = ("dez", "onze", "doze", "treze", "catorze", "quinze",
                      "dezesseis", "dezessete", "dezoito", "dezenove")
    dezenas = ("", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta",
               "setenta", "oitenta", "noventa")
    n = int(ano)
    if not 2000 <= n <= 2099:
        return str(n)
    resto = n - 2000
    if resto == 0:
        return "dois mil"
    if resto < 10:
        return f"dois mil e {unidades[resto]}"
    if resto < 20:
        return f"dois mil e {dez_a_dezenove[resto - 10]}"
    d, u = divmod(resto, 10)
    return (f"dois mil e {dezenas[d]}" if not u
            else f"dois mil e {dezenas[d]} e {unidades[u]}")


def data_limite(hoje: str, anos: int = PERIODO_PADRAO_ANOS) -> str:
    """A data a partir da qual se busca. `2026-08-25`, 5 anos -> `2021-08-25`.

    Nao usa `datetime`: a data vem de quem chama, como no resto da casa, e
    subtrair ano de texto ISO e conta de inteiro.
    """
    ano, mes, dia = str(hoje)[:10].split("-")
    return f"{int(ano) - int(anos):04d}-{mes}-{dia}"


# ----------------------------------------------------------------- a busca


# O CANCELADO E O SUSPENSO NÃO ENTRAM NA CERTIDÃO — decisão do oficial em
# 14/10/2026, que é a letra da lei: Lei 9.492/1997, art. 27, § 2º, e Código de
# Normas do TJMA (Prov. 28/2026), arts. 944 e 948 — «não serão expedidas
# certidões relativas a registros cujo cancelamento já tenha sido averbado,
# salvo quando houver requerimento escrito do próprio devedor ou determinação
# judicial expressa». O protesto com efeitos suspensos pelo juiz também sai
# (Gentil, cap. 7, [p. 2693]): a ordem para a publicidade dele.
#
# CORREÇÃO, e ela é grande: até 14/10 a busca trazia os cancelados, e com tudo
# cancelado saía SOZINHA a «certidão de cancelamento» a requerimento verbal —
# exatamente o papel que a lei só admite a pedido escrito do devedor ou por
# ordem judicial.
#
# E O SUSPENSO POR DECISÃO PROVISÓRIA VOLTOU À CERTIDÃO EM 21/10/2026 (LH13,
# pergunta 18, letra a): o oficial passou a seguir o CNN art. 263-K (Prov. CN
# 253/2026), que prevalece sobre o CN-MA. A decisão PROVISÓRIA sai como
# «CONSTA COM SUSTAÇÃO JUDICIAL PRECÁRIA», com os dados do registro, o número
# da ação, o caráter provisório e o fecho «Resultado emitido em cumprimento à
# decisão judicial — Processo nº …» (III); a DEFINITIVA continua fora (I); a
# que manda expressamente emitir negativa cumpre-se nos limites, e fica fora;
# no segredo de justiça, só a sustação e o número do processo (§ 1º). A marca
# é da ordem (`protesto.CARATER_DA_ORDEM`); a ordem lançada antes, SEM a
# marca, continua fora até alguém marcá-la (`protesto.ordens_sem_marca`).
AUTORIZACOES = {
    "DEVEDOR_ESCRITO": "requerimento escrito do próprio devedor",
    "ORDEM_JUDICIAL": "determinação judicial expressa",
}


def sustacao_precaria(suspenso: dict | None) -> bool:
    """Se a ordem em vigor faz o protesto sair como «CONSTA COM SUSTAÇÃO
    JUDICIAL PRECÁRIA» (CNN art. 263-K, III). Só calcula.

    É a decisão PROVISÓRIA que não manda expressamente emitir negativa. A
    definitiva, a que manda a negativa e a ordem ainda sem marca ficam fora da
    certidão a terceiro — a regra de antes de 21/10/2026 para as duas últimas.
    """
    if not suspenso:
        return False
    return (str(suspenso.get("ordem_carater") or "").upper() == "PROVISORIA"
            and not int(suspenso.get("ordem_manda_negativa") or 0))


def autorizacao_valida(autorizacao: Any) -> str | None:
    """A chave de `AUTORIZACOES`, ou None. Palavra desconhecida recusa."""
    a = str(autorizacao or "").strip().upper()
    if not a:
        return None
    if a not in AUTORIZACOES:
        raise CertidaoError(
            f"Autorização desconhecida: {a!r}. As que a lei admite para "
            f"certificar protesto cancelado são o requerimento escrito do "
            f"devedor e a ordem judicial.")
    return a


def _sem_curinga(texto: str) -> str:
    """O texto como LETRAS no `ILIKE ... ESCAPE '\\'`: `\\`, `%` e `_` escapados."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# O DEVEDOR GRAVADO SEM CPF/CNPJ (LD12): `documento_numero` nulo, vazio ou sem
# um dígito sequer. A coluna aceita nulo na produção migrada, e o devedor do
# acervo e do cadastro antigo não passou pela conferência da CRA, que hoje
# exige o documento no balcão.
DEVEDOR_SEM_DOCUMENTO = "COALESCE(d.documento_numero, '') !~ '[0-9]'"


def onde_casa_o_devedor(nome: Any, documento: Any) -> tuple[str, list]:
    """O pedaço do WHERE que acha a pessoa pedida em `pt_devedores d`. Só calcula.

    É A MESMA REGRA NA CERTIDÃO E NO LIVRO DE PROTOCOLO
    (`protesto_livros.protocolo_do_devedor`), escrita uma vez para as duas não
    divergirem (LD11, 21/10/2026, ressalva da revisão do LD04):

    - COM O CPF/CNPJ, CASA PELO DOCUMENTO, e o nome não traz homônimo. Era
      documento OU nome: quem trazia o CPF certo e um nome parcial («SILVA»)
      levava o protesto e o protocolo dos homônimos — a positiva que mente
      contra a pessoa, e o Livro de Protocolo de terceiros, que só se
      certifica ao próprio devedor ou por ordem judicial (CN-MA art. 906,
      § 2º). O documento casa pelos DÍGITOS: no acervo ele está sem pontuação,
      e quem pede traz o CPF com ponto e traço. Quem traz o CPF certo e o nome
      com um acento a menos continua aparecendo pelo documento.
    - MAS O DEVEDOR GRAVADO SEM DOCUMENTO CASA PELO NOME (LD12, 21/10/2026,
      ressalva da revisão do LD11). Só pelo documento, o título cujo devedor
      foi apontado sem CPF/CNPJ sumia da certidão pedida com o CPF dele, e ela
      saía NEGATIVA para quem tem protesto — certidão que não acha por causa
      de grafia é certidão que mente. O nome tem de ser IGUAL ao gravado, sem
      acento, sem caixa e sem espaço a mais (`nome_norm`), e não só estar
      contido nele: com o CPF na mão, «SILVA» traria à positiva de quem pediu
      todos os SILVA sem documento. O homônimo que tem OUTRO documento
      continua de fora. Quem casa assim sai marcado (`so_pelo_nome`), para o
      escrevente conferir a identidade.
    - SEM DOCUMENTO NO PEDIDO, PELO NOME contido no gravado, sem acento e sem
      caixa (`nome_norm`: o `UPPER()` do SQLite era ASCII, e 'josé' não
      achava 'JOSÉ DA SILVA').

    Nos dois casos o que se digitou é TEXTO, e não padrão: `%`, `_` e `\\` vão
    escapados, ou o nome «%» casaria com todos os devedores da casa.

    Sem nome nem documento devolve `("", [])`: quem chama decide se recusa.
    """
    doc = _digitos(documento)
    termo = normalizar_nome(nome)
    pelo_documento = ("REPLACE(REPLACE(REPLACE(COALESCE(d.documento_numero,''),"
                      "'.',''),'-',''),'/','') = %s")
    if doc and termo:
        return (f"({pelo_documento} OR ({DEVEDOR_SEM_DOCUMENTO}"
                " AND d.nome_norm ILIKE %s ESCAPE '\\'))",
                [doc, _sem_curinga(termo)])
    if doc:
        return pelo_documento, [doc]
    if termo:
        return "d.nome_norm ILIKE %s ESCAPE '\\'", [f"%{_sem_curinga(termo)}%"]
    return "", []


def buscar(con: Any, *, nome: str | None = None,
           documento: str | None = None, desde: str | None = None,
           autorizacao: str | None = None) -> list[dict]:
    """Os protestos de uma pessoa, no periodo. So LE.

    SO ENTRA TITULO QUE CHEGOU A PROTESTO — o que tem ato de PROTESTO. O
    apontamento nao basta: titulo apontado e pago no triduo nunca foi
    protestado, e certidao que o mostrasse mentiria contra a pessoa.

    QUEM E A PESSOA: com o CPF/CNPJ, o documento, pelos DIGITOS, e o nome
    inteiro so acha o devedor gravado sem documento (LD12); sem o documento,
    o nome (LD11) — ver `onde_casa_o_devedor`. O achado que so o nome liga a
    pessoa vem com `so_pelo_nome`.
    """
    termo = (nome or "").strip()
    doc = _digitos(documento)
    if not termo and not doc:
        raise CertidaoError(
            "Informe o nome ou o CPF/CNPJ de quem se quer a certidão — sem um "
            "dos dois não há o que buscar.")

    filtro, params = onde_casa_o_devedor(termo, doc)
    if desde:
        filtro = f"({filtro}) AND a.data_ato >= %s"
        params.append(str(desde)[:10])

    # O ATO ANULADO NÃO CONTA (LT04, 20/10/2026): o protesto ou a baixa que
    # se lavrou e foi desfeito porque o selo não saiu (`cancelado = 1`) não
    # existiu. Sem o filtro, o protesto anulado saía na positiva, e a baixa
    # anulada tirava da certidão um protesto em pé — a negativa sobre quem
    # tem protesto. É o mesmo filtro da relação diária, do XML da CENPROT e
    # do repasse.
    #
    # O NÚMERO DO LIVRO MORA EM `nu_livros`, que é do núcleo: banco só com o
    # esquema do protesto não a tem, e aí o livro é o do acervo (detalhe).
    bd = banco(con)
    tem_livros = bd.tem_tabela("nu_livros")
    livro_sql = ("(SELECT v.numero FROM nu_livros v WHERE v.id = a.livro_id)"
                 if tem_livros else "NULL")
    linhas = bd.ler(
        f"""SELECT t.id AS titulo_id, t.numero_titulo, t.especie, t.situacao,
                   t.valor_centavos, t.saldo_centavos, t.data_emissao,
                   t.data_vencimento, t.cedente_nome, t.cedente_documento,
                   t.protocolo, t.apresentante_nome, t.motivo_protesto,
                   t.tipo_protesto, t.tipo_endosso,
                   d.nome devedor_nome, d.documento_tipo, d.documento_numero,
                   a.id ato_id, a.data_ato, a.folha, a.numero_ordem,
                   a.detalhe_json, a.selo, a.rotulo,
                   {livro_sql} livro_numero,
                   (SELECT ap.data_ato FROM pt_atos ap
                     WHERE ap.titulo_id = t.id AND ap.tipo = 'APONTAMENTO'
                       AND ap.cancelado = 0
                     ORDER BY ap.id LIMIT 1) AS data_apontamento
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
              JOIN pt_devedores d ON d.titulo_id = t.id
             WHERE a.tipo = 'PROTESTO' AND a.cancelado = 0 AND ({filtro})
             ORDER BY a.data_ato, t.id, a.id""", params)

    achados = []
    for r in linhas:
        detalhe = json.loads(r["detalhe_json"] or "{}")
        baixa = bd.um(
            """SELECT data_ato, motivo_cancelamento FROM pt_atos
                WHERE titulo_id = %s AND tipo = 'CANCELAMENTO' AND cancelado = 0
                ORDER BY id DESC LIMIT 1""", (r["titulo_id"],))
        # OS EFEITOS SUSPENSOS POR ORDEM JUDICIAL — e a certidao tem de
        # dizer, porque ela e o papel que faz o banco negar credito.
        #
        # **O PROTESTO NAO SOME DA CERTIDAO**, e isso seria mentir do outro
        # lado: ele existe e esta no livro, e certidao negativa sobre quem tem
        # protesto e o erro que nao se desfaz. O que a ordem faz e parar a
        # PUBLICIDADE dele — e a forma de cumpri-la, recebida depois da
        # lavratura, e a averbacao no proprio registro consignando que os
        # efeitos estao suspensos.
        suspenso = PT.efeito_suspensivo_em_vigor(con, int(r["titulo_id"]))
        achados.append({
            "titulo_id": int(r["titulo_id"]),
            "numero_titulo": r["numero_titulo"],
            "especie": r["especie"],
            "situacao": r["situacao"],
            "devedor": r["devedor_nome"],
            "devedor_documento": formatar_documento(r["documento_numero"]),
            # O DEVEDOR GRAVADO SEM CPF/CNPJ (LD12): só o nome o liga a quem
            # pediu, e a certidão vai sair com o documento do pedido. A marca
            # é para a tela avisar o escrevente — o teor não a lê.
            "so_pelo_nome": not _digitos(r["documento_numero"]),
            "cedente": r["cedente_nome"],
            "cedente_documento": formatar_documento(r["cedente_documento"])
            if r["cedente_documento"] else "",
            "protocolo": r["protocolo"],
            # A DATA DA PROTOCOLIZAÇÃO É A DO APONTAMENTO (LD08) — o mesmo
            # ato que o instrumento e o registro leem (`protesto_instrumento.
            # dados`). Título do acervo sem o ato vem sem ela.
            "data_protocolo": r["data_apontamento"],
            "apresentante": r["apresentante_nome"],
            "motivo_protesto": r["motivo_protesto"],
            "tipo_protesto": r["tipo_protesto"],
            "tipo_endosso": r["tipo_endosso"],
            "valor": reais(int(r["valor_centavos"] or 0)),
            "saldo": reais(int(r["saldo_centavos"] or 0)),
            "data_emissao": r["data_emissao"],
            "data_vencimento": r["data_vencimento"],
            "data_protesto": r["data_ato"],
            "efeitos_suspensos": bool(suspenso),
            "suspensao_juizo": (suspenso or {}).get("juizo", ""),
            "suspensao_processo": (suspenso or {}).get("processo", ""),
            "suspensao_em": (suspenso or {}).get("data_ato", ""),
            # A MARCA DA ORDEM (LH13, CNN art. 263-K): vazia na ordem lançada
            # antes de 21/10/2026, que ninguém marcou ainda.
            "suspensao_carater": (suspenso or {}).get("ordem_carater") or "",
            "suspensao_segredo": bool(int(
                (suspenso or {}).get("ordem_segredo_de_justica") or 0)),
            "sustacao_precaria": sustacao_precaria(suspenso),
            # O livro do ato lavrado aqui mora em `nu_livros`; o do acervo, no
            # detalhe que a carga gravou.
            "livro": r["livro_numero"] or detalhe.get("livro_do_acervo"),
            "folha": r["rotulo"] or r["folha"],
            "numero_ordem": r["numero_ordem"],
            "selo": r["selo"],
            "cancelado": bool(baixa),
            "data_cancelamento": baixa["data_ato"] if baixa else None,
            "motivo_cancelamento": (baixa["motivo_cancelamento"]
                                    if baixa else None),
        })
    # O QUE A LEI DEIXA CERTIFICAR. Sem autorização, o cancelado e o suspenso
    # ficam de fora — e então a negativa é o que cabe se não sobrar nada. A
    # sustação precária (LH13) é a exceção: ela SAI, e é a certidão positiva
    # que a diz (`_linha_do_protesto`).
    if not autorizacao_valida(autorizacao):
        achados = [a for a in achados if _certifica_sem_autorizacao(a)]
    return achados


def _certifica_sem_autorizacao(achado: dict) -> bool:
    """Se o protesto achado sai na certidão a terceiro, sem o pedido escrito
    do devedor nem a ordem judicial. Só calcula."""
    if achado.get("cancelado"):
        return False
    return (not achado.get("efeitos_suspensos")
            or bool(achado.get("sustacao_precaria")))


def tipo_para(achados: list[dict]) -> str:
    """Que certidao cabe no que se achou.

    Nada achado, NEGATIVA. Tudo cancelado, CANCELAMENTO — que e a positiva
    mais o fecho do art. 26. Sobrando protesto em pe, POSITIVA.
    """
    if not achados:
        return "NEGATIVA"
    if all(a["cancelado"] for a in achados):
        return "CANCELAMENTO"
    return "POSITIVA"


def protocolo_a_certificar(con: Any, *, nome: str | None,
                           documento: str | None, desde: str | None,
                           achados: list[dict],
                           autorizacao: str | None) -> list[dict]:
    """As linhas do Livro de Protocolo que a certidão também certifica. Só LÊ.

    Sem a autorização, nenhuma (CN-MA art. 906, § 2º; LD04); com ela, as de
    `protesto_livros.protocolo_do_devedor`, menos o título que já está nos
    achados — o protesto não se repete. É A MESMA CONTA NA EMISSÃO E NA TELA
    QUE A ANTECEDE (LD12): o aviso de quem entrou só pelo nome tem de falar do
    que vai sair no papel.
    """
    if not autorizacao_valida(autorizacao):
        return []
    import protesto_livros as PLIV
    ja = {int(a["titulo_id"]) for a in achados if a.get("titulo_id")}
    return [l for l in PLIV.protocolo_do_devedor(
        con, nome=nome, documento=documento, desde=desde)
        if int(l["titulo_id"]) not in ja]


def titulos_so_pelo_nome(*listas: list[dict]) -> int:
    """Quantos títulos entraram SÓ PELO NOME (LD12): os achados e as linhas do
    Livro de Protocolo marcados com `so_pelo_nome`. Só calcula."""
    return len({int(x["titulo_id"]) for lista in listas for x in lista
                if x.get("so_pelo_nome") and x.get("titulo_id")})


def aviso_so_pelo_nome(quantos: int) -> str:
    """O recado ao escrevente quando a busca casou alguém só pelo nome (LD12).

    FICA FORA DO TEOR, de propósito: a certidão diz o que o livro tem, com o
    nome e o documento de quem pediu, como sempre disse. O que o escrevente
    precisa saber é que ali o banco não conferiu o documento — o devedor foi
    gravado sem ele —, e que a identidade se confere no título antes de o
    papel sair do balcão.
    """
    um = int(quantos) == 1
    return (f"Confira a identidade: {quantos} "
            f"{'título entrou' if um else 'títulos entraram'} só pelo NOME — "
            f"o devedor foi gravado sem CPF/CNPJ, e nada além do nome o liga "
            f"a quem pediu. Veja no título (o endereço, o papel apresentado) "
            f"se é a mesma pessoa antes de entregar a certidão.")


# ------------------------------------------------------------------ o teor


def _dia(data: Any) -> str:
    """`2022-02-26` -> `26/02/2022`. E como as 19 certidoes do acervo escrevem.

    Data em ISO na certidao seria data que o cliente le errado — e a certidao
    e papel de balcao, nao tela de sistema.
    """
    s = str(data or "")[:10]
    if len(s) == 10 and s[4] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}"
    return s


def _mes_e_ano(data: str) -> str:
    ano, mes = str(data)[:4], int(str(data)[5:7])
    return f"{MESES[mes - 1].capitalize()} de {ano}"


def _linha_do_protesto(a: dict, i: int, con: Any = None) -> str:
    """Uma linha por protesto, com o que a casa punha na certidao.

    As colunas sao as de `tbProtesto_Certidao_Itens`, conferidas uma a uma
    contra `tbAvisoProtesto` em 25/08/2026 — os 19 itens do acervo casaram
    todos: livro, folha, numero do titulo, valor, emissao, vencimento e as
    datas do protesto e da baixa.

    QUAIS pedaços entram é daqui; o texto de cada pedaço é a peça
    `PT_CERTIDAO_LINHA` (LF06E), que o oficial edita — e o «; » que os junta
    e o ponto do fim são juntura.
    """
    rotulo = PECAS.vocabulario(con, "PT_CERTIDAO_LINHA")

    def _p(nome: str, **claros: Any) -> str:
        return PECAS.preencher(rotulo[nome], "PT_CERTIDAO_LINHA",
                               CertidaoError, **claros)

    # A SUSTAÇÃO PRECÁRIA EM SEGREDO DE JUSTIÇA (LH13 — CNN art. 263-K, § 1º):
    # a certidão informa só a sustação e o número do processo. Nada do título,
    # do credor nem do registro — é isso que o segredo guarda.
    if a.get("sustacao_precaria") and a.get("suspensao_segredo"):
        return _p("sustacao_precaria_em_segredo", ordem=i,
                  processo=a.get("suspensao_processo") or "") + "."

    onde = []
    if a.get("livro"):
        onde.append(_p("livro", livro=a["livro"]))
    if a.get("folha"):
        onde.append(_p("folha", folha=a["folha"]))
    if a.get("numero_ordem"):
        onde.append(_p("numero_de_ordem", numero_ordem=a["numero_ordem"]))
    lugar = ", ".join(onde) or _p("sem_lugar")
    # O CEDENTE SO SAI SE FOR OUTRA PESSOA. Em 28 dos 1.366 titulos o acervo
    # traz o mesmo codigo como cedente e como devedor — o que nao acontece na
    # vida real, e provavelmente e digitacao do comeco do E-Oficio. Certificar
    # que fulano apresentou protesto contra fulano seria pôr no papel um
    # engano que a carga so copiou.
    cedente = (a.get("cedente") or "").strip()
    if cedente and cedente.upper() == (a.get("devedor") or "").strip().upper():
        cedente = ""
    # O QUE A CERTIDÃO DIZ DE CADA PROTESTO — Prov. CNJ 134, art. 51 (Gentil,
    # cap. 7, [p. 2693]): protocolo, apresentante, credor, valor protestado,
    # tipo e motivo. Até 14/10/2026 o cedente saía como «apresentado por», e
    # quem apresenta é o apresentante (o banco, a CRA): o credor é outro papel.
    import protesto_termo as TERMO
    motivo = TERMO.motivo_no_livro(a.get("motivo_protesto"), con)
    tipo = TERMO.tipo_no_livro(a.get("tipo_protesto"), con) if motivo else ""
    credor = None
    if cedente and a.get("cedente_documento"):
        credor = _p("credor_com_documento", credor=cedente,
                    documento=a["cedente_documento"])
    elif cedente:
        credor = _p("credor", credor=cedente)
    # A DATA DO PROTOCOLO E O TIPO DO ENDOSSO (LD08, 21/10/2026) — CNN art.
    # 259, parágrafo único, VII («data e número do protocolo») e V («tipo do
    # endosso»). A linha trazia o número sem a data, e o endosso, que está no
    # título desde a CRA, não saía. A data é a do apontamento (`buscar`); o
    # endosso, o código do leiaute: M mandato, T translativo. Sem endosso (S,
    # ou vazio no acervo) não há tipo a certificar — LD08.perguntas, 3.
    protocolo = None
    if a.get("protocolo"):
        protocolo = (_p("protocolo_com_data", protocolo=a["protocolo"],
                        data=_dia(a["data_protocolo"]))
                     if a.get("data_protocolo")
                     else _p("protocolo", protocolo=a["protocolo"]))
    codigo_do_endosso = str(a.get("tipo_endosso") or "").strip().upper()[:1]
    endosso = (_p("endosso", tipo=_p(f"endosso_{codigo_do_endosso}"))
               if codigo_do_endosso in ENDOSSOS_NA_CERTIDAO else None)
    partes = [
        _p("titulo", ordem=i, numero_titulo=a["numero_titulo"]),
        _p("especie", especie=a["especie"]) if a.get("especie") else None,
        protocolo,
        _p("valor", valor=a["valor"]),
        (_p("valor_protestado", valor=a["saldo"])
         if a.get("saldo") and a.get("saldo") != a.get("valor") else None),
        (_p("emissao", data=_dia(a["data_emissao"]))
         if a.get("data_emissao") else None),
        (_p("vencimento", data=_dia(a["data_vencimento"]))
         if a.get("data_vencimento") else None),
        (_p("apresentante", apresentante=a["apresentante"])
         if a.get("apresentante") else None),
        endosso,
        credor,
        (_p("protesto", tipo=tipo.lower(), motivo=motivo.lower())
         if motivo else None),
        _p("protestado", data=_dia(a["data_protesto"])),
        lugar,
    ]
    if a.get("sustacao_precaria"):
        # CNN art. 263-K, III (LH13): os dados do registro ficam acima, e
        # aqui vão a sustação, o caráter provisório e o número da ação; o
        # fecho do inciso vem depois das linhas (`_fecho_da_precaria`).
        partes.append(_p("sustacao_precaria",
                         juizo=a.get("suspensao_juizo") or "",
                         processo=a.get("suspensao_processo") or ""))
    elif a.get("efeitos_suspensos"):
        juizo = " ".join(x for x in (a.get("suspensao_juizo"),
                                    a.get("suspensao_processo")) if x)
        partes.append(_p("suspenso_com_juizo", juizo=juizo) if juizo
                      else _p("suspenso"))
    if a.get("cancelado"):
        quando = _dia(a["data_cancelamento"])
        partes.append(
            _p("cancelado_com_motivo", data=quando,
               motivo=a["motivo_cancelamento"])
            if a.get("motivo_cancelamento") else _p("cancelado", data=quando))
    return "; ".join(p for p in partes if p) + "."


def _fecho_da_precaria(achados: list[dict], con: Any = None) -> str:
    """O fecho do CNN art. 263-K, III — «Resultado emitido em cumprimento à
    decisão judicial — Processo nº …» —, um por processo, na ordem das
    linhas. Só calcula; sem sustação precária, vazio.

    VEM DEPOIS DE TODAS AS LINHAS, e não dentro de cada uma: é o fecho da
    resposta, que diz por que a certidão fala de um protesto cujos efeitos o
    juiz suspendeu. Dois protestos da mesma ação não repetem o fecho.
    """
    processos: list[str] = []
    for a in achados:
        processo = str(a.get("suspensao_processo") or "").strip()
        if a.get("sustacao_precaria") and processo and processo not in processos:
            processos.append(processo)
    if not processos:
        return ""
    rotulo = PECAS.vocabulario(con, "PT_CERTIDAO_LINHA")
    return " ".join(PECAS.preencher(rotulo["fecho_precaria"], "PT_CERTIDAO_LINHA",
                                    CertidaoError, processo=p)
                    for p in processos)


def paragrafo_do_protocolo(do_protocolo: list[dict], con: Any = None) -> str:
    """O que consta do Livro de Protocolo, para a certidão a pedido escrito.
    Só calcula; lista vazia devolve vazio.

    CN-MA art. 906, § 2º: «Informações e certidões extraídas do Livro de
    Protocolo somente serão fornecidas mediante requerimento escrito do
    próprio devedor ou por determinação judicial» (e art. 905, parágrafo
    único). QUEM DECIDE se a autorização existe é `emitir`; as linhas são as
    do próprio livro (`protesto_livros.protocolo_do_devedor`), com as
    ocorrências averbadas (art. 908, §§ 1º e 5º). O texto de cada pedaço é a
    peça `PT_CERTIDAO_LINHA`, que o oficial edita.
    """
    if not do_protocolo:
        return ""
    rotulo = PECAS.vocabulario(con, "PT_CERTIDAO_LINHA")

    def _p(nome: str, **claros: Any) -> str:
        return PECAS.preencher(rotulo[nome], "PT_CERTIDAO_LINHA",
                               CertidaoError, **claros)

    linhas = []
    for i, l in enumerate(do_protocolo, 1):
        partes = [
            _p("apontamento", ordem=i, protocolo=l["protocolo"], data=l["data"]),
            (_p("titulo_apontado", numero_titulo=l["titulo"])
             if l.get("titulo") else None),
            _p("especie", especie=l["natureza"]) if l.get("natureza") else None,
            _p("valor", valor=l["valor"]) if l.get("valor") else None,
            (_p("apresentante", apresentante=l["apresentante"])
             if l.get("apresentante") else None),
            _p("ocorrencias", ocorrencias=l["ocorrencias"]),
        ]
        linhas.append("; ".join(p for p in partes if p) + ".")
    return " ".join([_p("protocolo_abertura"), *linhas])


def montar_teor(*, tipo: str, nome: str, documento: str | None,
                achados: list[dict], desde: str, hoje: str,
                periodo_anos: int = PERIODO_PADRAO_ANOS,
                requerente: str | None = None, modelo: str | None = None,
                autorizacao: str | None = None,
                autorizacao_ref: str | None = None, con: Any = None,
                do_protocolo: list[dict] | None = None) -> str:
    """O teor da certidao, nas palavras que esta casa usa.

    Nao grava nada: recebe o que a busca achou e devolve texto. Com `con`, as
    frases (pedido, abertura, fecho) saem com o ajuste da casa; sem ele, com o
    padrao da base — ver `protesto_pecas`.

    `do_protocolo` (LD04) são as linhas do Livro de Protocolo que a certidão
    a pedido escrito do devedor, ou por ordem judicial, também certifica
    (CN-MA art. 906, § 2º): o título só apontado, pago ou retirado antes do
    protesto. Elas vêm DEPOIS do texto do tipo — a negativa continua dizendo
    que protesto não há, porque não há —, e sem autorização não entram.
    """
    texto = _teor_do_tipo(tipo=tipo, nome=nome, documento=documento,
                          achados=achados, desde=desde, periodo_anos=periodo_anos,
                          requerente=requerente, modelo=modelo,
                          autorizacao=autorizacao,
                          autorizacao_ref=autorizacao_ref, con=con)
    if do_protocolo and autorizacao_valida(autorizacao):
        texto = texto.rstrip() + " " + paragrafo_do_protocolo(do_protocolo, con)
    return texto


def _teor_do_tipo(*, tipo: str, nome: str, documento: str | None,
                  achados: list[dict], desde: str, periodo_anos: int,
                  requerente: str | None, modelo: str | None,
                  autorizacao: str | None, autorizacao_ref: str | None,
                  con: Any) -> str:
    """O teor da negativa, da positiva ou do cancelamento. Só calcula."""
    if tipo not in TIPOS:
        raise CertidaoError(
            f"Tipo de certidão desconhecido: {tipo!r}. Os que existem são: "
            f"{', '.join(TIPOS)}.")
    quem = (requerente or "").strip()
    # "a requerimento VERBAL de parte interessada" e o que as 44 negativas do
    # acervo dizem. Dizer "verbal" quando o pedido foi escrito e assinado
    # seria certificar o que nao houve — por isso, informado o requerente, ele
    # e quem aparece.
    #
    # CANCELADO OU SUSPENSO SÓ ENTRA COM A AUTORIZAÇÃO, E A CERTIDÃO DIZ QUAL
    # (CN TJMA arts. 944 e 948): é ela que justifica o papel mostrar o que a
    # regra manda calar.
    #
    # A ESCOLHA É DAQUI; O TEXTO DE CADA PEDIDO É DO OFICIAL (LF06E) — a
    # vírgula antes do nome e os parênteses da ordem são juntura, e ficam.
    aut = autorizacao_valida(autorizacao)
    if aut == "DEVEDOR_ESCRITO":
        pedido = (_frase(con, "PT_CERTIDAO_PEDIDO_DEVEDOR")
                  + (f", {quem}" if quem else ""))
    elif aut == "ORDEM_JUDICIAL":
        ref = (autorizacao_ref or "").strip()
        pedido = (_frase(con, "PT_CERTIDAO_PEDIDO_JUDICIAL")
                  + (f" ({ref})" if ref else ""))
    elif quem:
        pedido = _frase(con, "PT_CERTIDAO_PEDIDO_REQUERENTE", requerente=quem)
    else:
        pedido = _frase(con, "PT_CERTIDAO_PEDIDO_VERBAL")
    doc_tipo = tipo_do_documento(documento)
    documento_claros = {"tipo_documento": doc_tipo or "documento",
                        "documento": formatar_documento(documento)}

    if tipo == "NEGATIVA":
        identificacao = nome.strip()
        if documento:
            identificacao = _frase(con, "PT_CERTIDAO_IDENTIFICACAO",
                                   nome=nome.strip(), **documento_claros)
        try:
            return (modelo or _padrao("NEGATIVA")).format(
                pedido=pedido, desde=_mes_e_ano(desde),
                identificacao=identificacao, periodo_anos=periodo_anos,
                nome=nome.strip())
        except (KeyError, ValueError) as erro:
            raise CertidaoError(f"O modelo da certidão negativa está incompleto: {erro}.") from erro

    if not achados:
        raise CertidaoError(
            f"Não há protesto a certificar: a busca não achou nada, e a "
            f"certidão que cabe é a NEGATIVA, não a {tipo}.")

    # A ABERTURA DA POSITIVA E DO CANCELAMENTO era uma f-string daqui, e o
    # oficial abria a tela e via só «{cabeca} {corpo}» (LF06A,
    # `ESQUELETO_EM_VEZ_DE_TEXTO`). Desde o LF06E ela é a peça
    # `PT_CERTIDAO_CABECA`, editável; o espaço antes da inscrição é juntura.
    inscrito = (" " + _frase(con, "PT_CERTIDAO_INSCRITO", **documento_claros)
                if documento else "")
    cabeca = _frase(con, "PT_CERTIDAO_CABECA", pedido=pedido,
                    ano_por_extenso=_por_extenso_ano(int(str(desde)[:4])),
                    nome=nome.strip(), inscrito=inscrito)
    corpo = " ".join(_linha_do_protesto(a, i, con)
                     for i, a in enumerate(achados, 1))
    fecho_da_precaria = _fecho_da_precaria(achados, con)
    if fecho_da_precaria:
        corpo = f"{corpo} {fecho_da_precaria}"

    if tipo == "POSITIVA":
        try:
            return (modelo or _padrao("POSITIVA")).format(
                cabeca=cabeca, corpo=corpo, nome=nome.strip(), pedido=pedido)
        except (KeyError, ValueError) as erro:
            raise CertidaoError(f"O modelo da certidão positiva está incompleto: {erro}.") from erro

    # CANCELAMENTO: a positiva mais o fecho do art. 26. O acervo tem as duas
    # formas — singular e plural —, e sai a que couber na quantidade. A
    # quantidade decide aqui; o texto de cada forma é peça (LF06E).
    fecho = _frase(con, "PT_CERTIDAO_FECHO_UM" if len(achados) == 1
                   else "PT_CERTIDAO_FECHO_VARIOS")
    try:
        return (modelo or _padrao("CANCELAMENTO")).format(
            cabeca=cabeca, corpo=corpo, fecho=fecho, nome=nome.strip(),
            pedido=pedido)
    except (KeyError, ValueError) as erro:
        raise CertidaoError(f"O modelo da certidão de cancelamento está incompleto: {erro}.") from erro


def hash_certidao(numero: int, ano: int, nome: str, teor: str,
                  emitida_em: str) -> str:
    """Impressao digital da certidao, para provar que a segunda via e a mesma."""
    bruto = f"{numero}|{ano}|{nome}|{emitida_em}|{teor}"
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- emitir


def proximo_numero(con: Any, ano: int) -> int:
    """O proximo numero do exercicio. So LE — nao consome nada.

    GET nao abre transacao de escrita: a tela de conferencia chama isto, e
    contador consumido num GET fica preso no `busy_timeout` enquanto outro
    balcao lavra.
    """
    linha = banco(con).um(
        "SELECT max(numero) AS n FROM pt_certidoes WHERE ano = %s",
        (int(ano),))
    return int(linha["n"] if linha and linha["n"] else 0) + 1


def emitir(con: Any, *, nome: str, documento: str | None,
           achados: list[dict], hoje: str, agora: str, tipo: str | None = None,
           periodo_anos: int = PERIODO_PADRAO_ANOS, desde: str | None = None,
           requerente: str | None = None, finalidade: str | None = None,
           usuario: str | None = None, autorizacao: str | None = None,
           autorizacao_ref: str | None = None) -> dict:
    """Emite a certidao, com numero do exercicio, teor congelado e hash. ESCREVE.

    O TIPO SAI DO QUE SE ACHOU, e nao de quem pede: `tipo_para(achados)`.
    Deixar escolher deixaria sair negativa sobre quem tem protesto — que e a
    certidao que faz o banco emprestar para quem nao devia.

    Passar `tipo` serve para o caso em que o oficial quer a POSITIVA de quem
    tem tudo cancelado; pedir tipo que o achado nao comporta e recusado.
    """
    if not (nome or "").strip():
        raise CertidaoError("A certidão precisa do nome de quem ela é.")
    # O CPF/CNPJ É OBRIGATÓRIO — CN TJMA (Prov. 28/2026), art. 906: ele
    # consta de todos os registros e certidões. Certidão só pelo nome não
    # separa homônimos, e homônimo é a regra.
    if not tipo_do_documento(documento):
        raise CertidaoError(
            "Informe o CPF (11 dígitos) ou o CNPJ (14 dígitos) de quem se quer "
            "a certidão — o Código de Normas (art. 906) manda que ele conste "
            "de toda certidão de protesto.")
    aut = autorizacao_valida(autorizacao)
    if aut == "ORDEM_JUDICIAL" and not (autorizacao_ref or "").strip():
        raise CertidaoError(
            "Para certificar protesto cancelado por determinação judicial, "
            "informe o juízo e o processo da ordem.")
    if not aut:
        # A busca já deixa de fora o cancelado e o suspenso (menos a
        # sustação precária, LH13); quem passar os achados de outro jeito não
        # fura a regra.
        achados = [a for a in achados if _certifica_sem_autorizacao(a)]
    cabivel = tipo_para(achados)
    escolhido = (tipo or cabivel).strip().upper()
    if escolhido not in TIPOS:
        raise CertidaoError(
            f"Tipo de certidão desconhecido: {escolhido!r}. Os que existem "
            f"são: {', '.join(TIPOS)}.")
    if escolhido == "NEGATIVA" and achados:
        raise CertidaoError(
            f"Não se emite certidão negativa: a busca achou "
            f"{len(achados)} protesto(s) contra {nome.strip()}. Negativa "
            f"sobre quem tem protesto é o que faz o banco emprestar para quem "
            f"não devia.")
    if escolhido != "NEGATIVA" and not achados:
        raise CertidaoError(
            "A busca não achou protesto nenhum — a certidão que cabe é a "
            "NEGATIVA.")

    limite = desde or data_limite(hoje, periodo_anos)
    try:
        import modelos_da_casa as MODELOS
        chave = {"NEGATIVA": "PT_CERTIDAO_NEGATIVA",
                 "POSITIVA": "PT_CERTIDAO_POSITIVA",
                 "CANCELAMENTO": "PT_CERTIDAO_CANCELAMENTO"}[escolhido]
        modelo = MODELOS.corpo_de(con, chave)
    except Exception:
        modelo = None
    # A PEDIDO ESCRITO DO DEVEDOR, OU POR ORDEM JUDICIAL, A CERTIDÃO TAMBÉM
    # DIZ O QUE CONSTA DO LIVRO DE PROTOCOLO (LD04, 21/10/2026) — CN-MA art.
    # 906, § 2º, e art. 905, parágrafo único. Até aqui o título só apontado
    # saía NEGATIVA mesmo a pedido do devedor, e a informação que a norma
    # manda dar a ele não saía em papel nenhum. O título que já está nos
    # achados (o protesto, cancelado ou não) não se repete.
    do_protocolo = protocolo_a_certificar(
        con, nome=nome, documento=documento, desde=limite, achados=achados,
        autorizacao=aut)
    teor = montar_teor(tipo=escolhido, nome=nome, documento=documento,
                       achados=achados, desde=limite, hoje=hoje,
                       periodo_anos=periodo_anos, requerente=requerente,
                       modelo=modelo, autorizacao=autorizacao,
                       autorizacao_ref=autorizacao_ref, con=con,
                       do_protocolo=do_protocolo)
    ano = int(str(hoje)[:4])
    # Trava por assunto ANTES de ler o maior numero: dois balcoes emitindo
    # juntos leriam o mesmo `max(numero)+1`, e um deles cairia na UNIQUE sem
    # a certidao sair. `proximo_numero` continua so lendo, para a tela de
    # conferencia nao travar nada.
    banco(con).travar("pt_certidoes.numero")
    numero = proximo_numero(con, ano)
    # A LINHA DA ASSINATURA A MAO SAI ANTES DO HASH, E NAO ANTES DO
    # INSERT. Esta chamada estava DENTRO do texto do SQL — colada entre
    # as aspas e o `INSERT INTO`, de modo que o banco recusava com
    # «near "teor": syntax error» e a certidao NAO SAIA. Posta so antes
    # do `bd.escrever`, o teor gravado deixaria de ser o teor que o
    # `hash_certidao` carimbou, e a conferencia de «este e o teor que
    # saiu?» passaria a falhar em toda certidao nova.
    teor = sem_linha_de_assinatura_a_mao(teor)
    impressao = hash_certidao(numero, ano, nome.strip(), teor, agora)
    try:
        novo = banco(con).escrever(
            """INSERT INTO pt_certidoes(numero, ano, tipo, nome, documento,
                   documento_tipo, requerente, finalidade, periodo_anos, desde,
                   achados, achados_json, teor, hash_certidao, emitida_em,
                   emitida_por)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (numero, ano, escolhido, nome.strip(), _digitos(documento) or None,
             tipo_do_documento(documento), (requerente or "").strip() or None,
             ("; ".join(x for x in ((finalidade or "").strip(),
                                    (f"{AUTORIZACOES[aut]}"
                                     + (f": {autorizacao_ref.strip()}"
                                        if (autorizacao_ref or "").strip()
                                        else "")) if aut else "") if x)
              or None), int(periodo_anos), limite,
             len(achados), json.dumps(achados, ensure_ascii=False), teor,
             impressao, agora, usuario))[0]["id"]
    except sqlite3.IntegrityError as erro:
        raise CertidaoError(
            f"A certidão n. {numero}/{ano} já existe. Nada foi emitido — "
            f"tente de novo. ({erro})") from erro
    # QUANTOS ENTRARAM SÓ PELO NOME (LD12) vai para quem emitiu, e não para o
    # teor: é a tela que avisa o escrevente (`aviso_so_pelo_nome`).
    return {"certidao_id": int(novo), "numero": numero, "ano": ano,
            "tipo": escolhido, "teor": teor, "hash": impressao,
            "achados": len(achados), "desde": limite,
            "so_pelo_nome": titulos_so_pelo_nome(achados, do_protocolo)}


# --------------------------------------------------------------- consultas


def certidao(con: Any, certidao_id: int) -> dict | None:
    """A certidao, como foi emitida. So LE."""
    return banco(con).um("SELECT * FROM pt_certidoes WHERE id = %s",
                         (int(certidao_id),))


def listar(con: Any, *, termo: str = "",
           limite: int = 100) -> list[dict]:
    """As certidoes emitidas, da mais nova para a mais velha. So LE."""
    t = (termo or "").strip()
    if not t:
        return banco(con).ler(
            "SELECT * FROM pt_certidoes ORDER BY ano DESC, numero DESC, id DESC LIMIT %s",
            (int(limite),))
    return banco(con).ler(
        """SELECT * FROM pt_certidoes
            WHERE nome ILIKE %s OR documento ILIKE %s
                  OR numero::text = %s
            ORDER BY ano DESC, numero DESC, id DESC LIMIT %s""",
        (f"%{t}%", f"%{_digitos(t) or t}%", t, int(limite)))


def cancelar(con: Any, certidao_id: int, *, motivo: str,
             agora: str, usuario: str | None = None,
             selo_cancelado_tjma: Any = False) -> dict:
    """Cancela a certidao emitida. ESCREVE. O teor fica — o que saiu, saiu.

    Certidao errada nao se apaga: apaga-la deixaria a via que o cliente levou
    sem par no banco, e e justamente essa via que alguem vai conferir.
    """
    linha = certidao(con, certidao_id)
    if not linha:
        raise CertidaoError("Certidão não encontrada.")
    if int(linha["cancelada"] or 0):
        raise CertidaoError(
            f"A certidão n. {linha['numero']}/{linha['ano']} já está cancelada "
            f"desde {linha['cancelada_em']}.")
    razao = (motivo or "").strip()
    if len(razao) < 10:
        raise CertidaoError(
            "Escreva por que a certidão está sendo cancelada, com pelo menos "
            "dez letras — é o que fica no lugar dela.")
    if not CANC.declaracao_confirmada(selo_cancelado_tjma):
        raise CertidaoError(CANC.MENSAGEM_DECLARACAO_OBRIGATORIA)
    banco(con).escrever(
        """UPDATE pt_certidoes SET cancelada=1, motivo_cancelamento=%s,
                                   cancelada_em=%s, cancelada_por=%s,
                                   declaracao_selo_tjma_em=%s,
                                   declaracao_selo_tjma_por=%s
            WHERE id=%s""", (razao, agora, usuario, agora, usuario,
                              int(certidao_id)))
    return CANC.concluir(
        con, tabela="pt_certidoes", ato_id=int(certidao_id), motivo=razao,
        agora=agora, usuario=usuario)


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
