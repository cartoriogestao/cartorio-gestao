"""As palavras do balcão não são nome de gente.

A máscara da casa (`ajuda_privacidade`) trata palavra com inicial maiúscula como
possível nome de pessoa — é o lado seguro, e está certo para a ajuda. No WhatsApp
ele custava a conversa: «Boa tarde! Gostaria de saber sobre Registro de Imóveis,
tenho um Título de Domínio do INCRA» subia como «Gostaria de saber sobre
[PESSOA_01], tenho um [PESSOA_02] do INCRA», e a IA não tinha como saber o que a
pessoa queria (medido em 15/11/2026). Quem escreve tudo em maiúsculas subia
inteiro como marca.

O QUE ESTE MÓDULO FAZ
    Antes da máscara, põe em minúscula as palavras que são do vocabulário do
    cartório e da conversa comum («Certidão», «Nascimento», «Registro», «Bom»).
    Nome de gente não está no vocabulário, continua com a maiúscula e continua
    mascarado. Não mexe na máscara: o que ela esconde sem depender de maiúscula
    (CPF, telefone, e-mail, endereço, «meu nome é ...») segue igual.

O SOBRENOME QUE TAMBÉM É PALAVRA
    «Maria do Nascimento», «João Rocha Campos». A palavra do vocabulário fica
    como veio quando há nome antes dela (pulando «de», «da», «do») ou logo
    depois: aí ela é sobrenome, e vai mascarada junto. O preço é a frase
    «certidão da Maria Nascimento» perder o «Nascimento» — a IA pergunta qual
    certidão, e não fica sabendo o sobrenome de ninguém.

«MEU PAI FALECEU ONTEM» NÃO É «PAI: FULANO»
    A máscara também esconde o que vem depois de um rótulo de ficha — pai, mãe,
    falecido, titular, credor, devedor — até a pontuação: é como o nome aparece
    num documento colado. Na conversa, «meu pai faleceu ontem, como faço o
    registro de óbito?» subia «meu pai [PESSOA_01], como faço o registro de
    óbito?», e a frase mais delicada do balcão chegava sem o fato. `desrotular`
    põe uma vírgula depois do rótulo quando a palavra seguinte é do vocabulário
    («meu pai, faleceu ontem»): a regra da máscara não casa, e o texto sobe.
    Seguido de nome («minha mãe maria aparecida»), de «é» ou de «se chama», o
    rótulo fica como está, e o nome continua escondido mesmo em minúscula. A
    palavra «nome» nunca se desrotula.

Só calcula. Não fala com rede nem com banco.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Iterable
from unicodedata import normalize

import ajuda_privacidade as PRIV

# A conversa comum: o que não é do ofício e aparece em toda mensagem.
COMUNS = """
oi ola opa bom boa dia tarde noite tudo bem obrigado obrigada valeu por favor gentileza
quero queria preciso precisava gostaria tenho tinha posso pode poderia consigo vou vai
fazer tirar saber levar trazer pegar buscar pagar mandar enviar falar pedir dar ver
resolver passar assinar retirar receber informar confirmar marcar agendar comprar vender
como quando onde quanto quanta qual quais quem que porque pois para com sem sobre entre
ate desde ja ainda agora hoje ontem amanha depois antes cedo semana mes ano hora horas
segunda terca quarta quinta sexta sabado domingo feira janeiro fevereiro marco abril maio
junho julho agosto setembro outubro novembro dezembro
meu minha meus minhas seu sua seus suas nosso nossa dele dela este esta esse essa isso isto
aquele aquela um uma uns umas o a os as de da do das dos e ou mas se nao sim tambem so
pai mae filho filha filhos irmao irma esposa esposo marido mulher avo tio tia sogro sogra
neto neta primo prima cunhado cunhada namorado namorada companheiro companheira falecido
falecida faleceu morreu nasceu casou separou vendeu comprou herdou doou morador moradora
senhor senhora sr sra dona doutor doutora dr dra amigo amiga cliente pessoa pessoas
casa terreno lote sitio fazenda chacara roca sede zona rural urbana cidade bairro centro
povoado assentamento aldeia hospital maternidade banco prefeitura forum juiz juiza
advogado advogada delegacia igreja escola empresa loja firma carro moto veiculo placa
documento documentos papel papeis copia original foto fotos pdf arquivo audio mensagem
numero codigo recibo comprovante boleto pix conta valor preco custo taxa gratis gratuito
urgente urgencia rapido prazo data vencimento pronto pronta atrasado andamento situacao
duvida informacao ajuda atendimento atendente escrevente tabeliao tabelia oficial titular
substituta cartorio whatsapp telefone celular email endereco horario aberto fechado
incra iterma inss detran cpf cnpj rg cnh dut crv crlv atpv itbi itr ccir car iptu onr
crc cenprot serasa spc sus funai rani dnv
"""

_PALAVRA = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+")
_LIGAS = frozenset({"de", "da", "do", "das", "dos", "e"})
# Os rótulos de ficha que a máscara conhece (`ajuda_privacidade._NOME_ROTULADO`),
# menos «nome»: depois de «meu nome é» vem nome, com ou sem maiúscula.
_ROTULO = re.compile(
    r"\b(pai|m[aã]e|falecid[oa]|titular|devedor(?:a)?|credor(?:a)?|requerente|"
    r"interessad[oa]|outorgante|outorgad[oa]|testemunha|c[oô]njuge|companheir[oa]|"
    r"registrand[oa]|registrad[oa]|nubente|filia[cç][aã]o)\b(?=(\s+)([A-Za-zÀ-ÖØ-öø-ÿ]+)"
    r"(?:\s+([A-Za-zÀ-ÖØ-öø-ÿ]+))?)", re.I)
# Antes de nome: «meu pai é joão», «minha mãe se chama rosa».
_ANTES_DE_NOME = frozenset({"e", "era", "se", "chama", "chamava", "chamado", "chamada"})


def _chave(palavra: str) -> str:
    n = normalize("NFD", palavra)
    return "".join(c for c in n if not 0x300 <= ord(c) <= 0x36F).lower()


@lru_cache(maxsize=1)
def palavras() -> frozenset[str]:
    """O vocabulário: o manual de fábrica, o ofício e a conversa comum."""
    import wa_manual as MANUAL
    import wa_oficio as OFICIO
    fonte = "\n".join((MANUAL.PADRAO, OFICIO.texto_do_oficio(), COMUNS))
    return frozenset(_chave(p) for p in _PALAVRA.findall(fonte) if len(p) >= 2)


def baixar(texto: Any, extras: Iterable[str] = ()) -> str:
    """O texto com as palavras do balcão em minúscula; o resto, como veio.

    `extras` são palavras desta casa que também não são nome de cliente — o nome
    da cidade, por exemplo."""
    bruto = str(texto or "")
    vocabulario = palavras() | {_chave(p) for e in extras for p in _PALAVRA.findall(str(e))}
    achados = list(_PALAVRA.finditer(bruto))

    def e_nome(m: re.Match | None) -> bool:
        return bool(m) and m.group(0)[0].isupper() and _chave(m.group(0)) not in vocabulario

    saida, fim = [], 0
    for i, m in enumerate(achados):
        palavra = m.group(0)
        if not palavra[0].isupper() or _chave(palavra) not in vocabulario:
            continue
        antes = i - 1
        while antes >= 0 and achados[antes].group(0).lower() in _LIGAS:
            antes -= 1
        depois = achados[i + 1] if i + 1 < len(achados) else None
        colado = depois is not None and not bruto[m.end():depois.start()].strip(" ")
        if e_nome(achados[antes] if antes >= 0 else None) or (colado and e_nome(depois)):
            continue                       # é sobrenome: fica, e vai mascarado
        saida.append(bruto[fim:m.start()] + palavra.lower())
        fim = m.end()
    return "".join(saida) + bruto[fim:]


def desrotular(texto: Any) -> str:
    """Põe a vírgula que separa o rótulo de ficha da frase que o segue. Só calcula."""
    vocabulario = palavras()

    def troca(m: re.Match) -> str:
        seguinte, outra = _chave(m.group(3)), _chave(m.group(4) or "")
        if seguinte == "e" and m.group(3) != "e":          # «é», e não a liga «e»
            return m.group(0)
        if seguinte in _LIGAS:
            seguinte = outra
        if not seguinte or seguinte in _ANTES_DE_NOME or seguinte not in vocabulario:
            return m.group(0)
        return m.group(0) + ","

    return _ROTULO.sub(troca, str(texto or ""))


def mascarar(texto: Any, extras: Iterable[str] = ()) -> str:
    """O texto como pode subir ao provedor. Levanta `PrivacidadeError` como a máscara."""
    limpo = " ".join(desrotular(baixar(texto, extras)).split())
    if not limpo:
        return ""
    return PRIV.preparar_saida(instrucao="", pergunta=limpo).pergunta
