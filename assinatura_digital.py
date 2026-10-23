"""A assinatura digital do delegatario — o que a casa CONFERE, e nunca assina.

Decisao do oficial em 01/09/2026: *«certificado e A3 do delegatario. Vamos
construir essa ferramenta, ela vai ser util em muitos modulos.»*

**ESTE MODULO NAO ASSINA, E NAO E POR ESCOLHA DE DESENHO: ELE NAO PODE.**

  1. **A3 quer dizer que a chave privada nao sai do token.** Nao ha como o
     servidor te-la, nem guardar, nem copiar.
  2. **E carregar o driver PKCS#11 DERRUBA O PROCESSO.** Medido nesta maquina,
     nos dois drivers instalados — `eTPKCS11.dll` e `IDPrimePKCS1164.dll` —,
     nos dois casos **segmentation fault no `load`**, codigo de saida 139,
     antes de qualquer saida.

     **Segfault nao se trata com `try/except`**: ele mata o processo. Se o
     Flask carregasse o driver, o waitress morreria e o balcao inteiro sairia
     do ar — nao uma tela: o sistema.

Entao a assinatura acontece **fora**: o delegatario assina no assinador que ja
usa, e devolve o `.p7s`. Ver `DOCUMENTACAO/ASSINATURA_DIGITAL_A3.md`.

O QUE O SISTEMA CONFERE, SEM CHAVE NENHUMA
    Medido no instrumento de protesto real de 09/06/2025 que o oficial subiu:

      - e PKCS#7 `signedData`;
      - **o documento vem DENTRO do `.p7s`** — 81.937 bytes, byte a byte
        iguais ao PDF. A assinatura e ANEXADA, e nao destacada: o PDF comeca
        no byte 68 do arquivo assinado;
      - quem assinou sai do certificado: `FELIPE BARRETTO ANUNCIACAO:
        02300046520` — nome e CPF, na forma do e-CPF da ICP-Brasil.

    **A conferencia que mais protege e a do meio**, e ela nao precisa de
    criptografia: o documento embrulhado tem de ser byte a byte o que a casa
    emitiu. E ela que pega o caso real — assinar o arquivo errado, ou o
    arquivo alterado depois de gerado.

O QUE ELE NAO CONFERE, E DIZ QUE NAO
    **A validade criptografica da firma e a cadeia ate a raiz da ICP-Brasil.**
    Conferir isso exige as ancoras de confianca e a lista de revogacao, que
    esta casa nao tem. **Dizer «assinatura valida» sem ter conferido a firma
    seria o carimbo que mente na sua forma mais cara** — num papel que a
    serventia poe no mundo.

    O que ele diz e o que mediu: «embrulha o documento que a casa emitiu, e
    quem assinou foi fulano». Quem valida a firma e o validador oficial, e o
    proprio papel traz o endereco dele.
"""
from __future__ import annotations

import hashlib
from typing import Any

from bd_nativo import banco

# O tipo de conteudo do PKCS#7 assinado — OID 1.2.840.113549.1.7.2.
TIPO_ASSINADO = "signed_data"

# A extensao que os assinadores da ICP-Brasil produzem.
EXTENSAO = ".p7s"

# Teto do arquivo assinado. O instrumento medido tem 88 KB; um papel de
# cinquenta paginas com a cadeia inteira nao passa disto, e o teto existe para
# um engano de arrasto nao virar um `INSERT` de duzentos megabytes.
LIMITE = 25 * 1024 * 1024


class AssinaturaError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


def sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


# --------------------------------------------------------------- ler o .p7s


def _cms():
    """`asn1crypto` chega tarde de proposito.

    Ele esta no runtime, mas um modulo do nucleo que estoura no `import` faria
    o sistema inteiro nao subir por causa de uma dependencia que so serve a
    esta tela. Faltando, a recusa e em portugues e diz o que instalar.
    """
    try:
        from asn1crypto import cms
    except ImportError as erro:
        raise AssinaturaError(
            "Falta a biblioteca `asn1crypto` para ler o arquivo assinado. "
            "Ela vem no pacote do sistema; se esta faltando, a instalacao "
            "esta incompleta.") from erro
    return cms


def ler(conteudo: bytes) -> dict:
    """Abre o `.p7s` e diz o que ha dentro. So LE, e nao valida a firma.

    **Nao estoura com arquivo torto**: quem chama esta lendo o que alguem
    subiu pela tela, e arquivo de fora vem de qualquer jeito.
    """
    if not conteudo:
        raise AssinaturaError("O arquivo assinado veio vazio.")
    if len(conteudo) > LIMITE:
        raise AssinaturaError(
            f"O arquivo assinado tem {len(conteudo) // 1024} KB, e o teto e "
            f"{LIMITE // 1024 // 1024} MB.")
    cms = _cms()
    try:
        info = cms.ContentInfo.load(conteudo)
        tipo = info["content_type"].native
    except Exception as erro:
        raise AssinaturaError(
            "Este arquivo nao e uma assinatura que o sistema saiba ler. O que "
            "se espera e o `.p7s` que o assinador gera — o mesmo arquivo que "
            "acompanha o PDF.") from erro
    if tipo != TIPO_ASSINADO:
        raise AssinaturaError(
            f"O arquivo e do tipo «{tipo}», e nao uma assinatura de documento.")

    assinado = info["content"]
    embrulhado = assinado["encap_content_info"]["content"].native
    if not embrulhado:
        # A ASSINATURA DESTACADA NAO SERVE AQUI, e a recusa diz por que: sem o
        # documento dentro, nao ha como conferir que e o nosso.
        raise AssinaturaError(
            "Esta assinatura veio SEM o documento dentro (assinatura "
            "destacada). O sistema precisa do arquivo que junta os dois — e o "
            "assinador do token produz assim: o PDF vai embrulhado no `.p7s`.")

    return {"documento": embrulhado,
            "sha256_do_documento": sha256(embrulhado),
            "quem_assinou": _quem_assinou(assinado),
            "algoritmos": [
                {"digest": si["digest_algorithm"]["algorithm"].native,
                 "assinatura": si["signature_algorithm"]["algorithm"].native}
                for si in assinado["signer_infos"]],
            "certificados": [
                str(c.chosen.subject.native.get("common_name") or "")
                for c in assinado["certificates"]]}


def _quem_assinou(assinado) -> dict:
    """O nome e o CPF de quem assinou, do certificado que esta no pacote.

    **O ASSINANTE SE ACHA PELO `sid`, e nao pelo primeiro certificado da
    lista.** O pacote medido traz TRES — a AC intermediaria, a pessoa e a AC
    de cima — e a pessoa e a do MEIO. Pegar o primeiro diria que quem assinou
    foi «AC SOLUTI v5», que e a autoridade e nao o tabeliao.

    O nome vem no formato do e-CPF da ICP-Brasil: `NOME COMPLETO:CPF`.
    """
    infos = assinado["signer_infos"]
    if not len(infos):
        return {"nome": "", "cpf": "", "comum": ""}
    sid = infos[0]["sid"]
    if sid.name != "issuer_and_serial_number":
        # Identificado pela chave, e nao pelo emissor+serie. Nao se adivinha
        # qual dos certificados e: melhor nao dizer que dizer errado.
        return {"nome": "", "cpf": "", "comum": "",
                "motivo": f"o assinante vem identificado por «{sid.name}», que "
                          f"este sistema nao sabe casar com o certificado"}
    alvo = sid.chosen
    for c in assinado["certificates"]:
        tbs = c.chosen["tbs_certificate"]
        if (tbs["issuer"] == alvo["issuer"]
                and tbs["serial_number"] == alvo["serial_number"]):
            comum = str(c.chosen.subject.native.get("common_name") or "")
            nome, _, cpf = comum.partition(":")
            return {"nome": nome.strip(), "cpf": cpf.strip(), "comum": comum}
    return {"nome": "", "cpf": "", "comum": "",
            "motivo": "o certificado de quem assinou nao veio no arquivo"}


# --------------------------------------------------------------- conferir


def conferir(conteudo: bytes, *, documento: bytes,
             cpf_esperado: str | None = None) -> dict:
    """O `.p7s` embrulha o documento que a casa emitiu? So LE.

    **ESTA E A CONFERENCIA QUE PROTEGE, e ela nao precisa de criptografia.**
    Comparar byte a byte pega o caso real: assinar o arquivo errado, ou o
    arquivo alterado depois de gerado. A validade da FIRMA e outra coisa, e
    este modulo **nao a afirma** — ver o cabecalho.

    `cpf_esperado` e opcional e serve a quem sabe de quem tem de ser a
    assinatura. **Sem ele o modulo nao inventa dono**: diz quem assinou e
    deixa a comparacao para quem sabe.
    """
    lido = ler(conteudo)
    nosso = sha256(documento)
    confere = lido["sha256_do_documento"] == nosso

    problemas = []
    if not confere:
        problemas.append(
            "o documento assinado NAO e o que a casa emitiu — o arquivo "
            "assinado embrulha outra coisa, ou o papel mudou depois de gerado")
    if cpf_esperado:
        so_do_cpf = "".join(ch for ch in str(cpf_esperado) if ch.isdigit())
        do_arquivo = "".join(ch for ch in lido["quem_assinou"]["cpf"]
                             if ch.isdigit())
        if so_do_cpf and do_arquivo and so_do_cpf != do_arquivo:
            problemas.append(
                f"quem assinou foi {lido['quem_assinou']['nome']} "
                f"(CPF {do_arquivo}), e o esperado era o CPF {so_do_cpf}")
        elif so_do_cpf and not do_arquivo:
            problemas.append(
                "nao deu para ler o CPF de quem assinou, e por isso nao da "
                "para conferir se foi quem devia")

    return {**lido, "sha256_esperado": nosso, "confere": confere,
            "problemas": problemas, "serve": confere and not problemas}


def por_que_nao_serve(resultado: dict) -> str:
    """Uma frase para o balcao, juntando o que houver. So LE."""
    return "; ".join(resultado.get("problemas") or [])


# --------------------------------------------------------------- a fila


def pendentes(con: Any, *, entidade: str | None = None,
              limite: int = 200) -> list[dict]:
    """Os papeis que esperam assinatura. So LE.

    A FILA E DE TODA A CASA, e nao do Protesto: hoje o sistema emite nove
    papeis e o instrumento de protesto e o decimo. O que muda de um para o
    outro e o documento, e nao a assinatura — por isso a fila e uma.
    """
    onde, args = "WHERE assinado_em IS NULL", []
    if entidade:
        onde += " AND entidade = %s"
        args.append(entidade)
    args.append(int(limite))
    return banco(con).ler(
        f"""SELECT id, entidade, entidade_id, titulo, sha256_documento,
                   criado_em
              FROM as_documentos {onde}
             ORDER BY id DESC LIMIT %s""", args)


def contagens(con: Any) -> dict:
    """Quantos esperam e quantos ja voltaram, por entidade. So LE."""
    linhas = banco(con).ler(
        """SELECT entidade,
                  SUM(CASE WHEN assinado_em IS NULL THEN 1 ELSE 0 END)::int AS espera,
                  SUM(CASE WHEN assinado_em IS NOT NULL THEN 1 ELSE 0 END)::int AS feito
             FROM as_documentos GROUP BY entidade ORDER BY entidade""")
    return {r["entidade"]: {"espera": int(r["espera"] or 0),
                            "assinados": int(r["feito"] or 0)}
            for r in linhas}
