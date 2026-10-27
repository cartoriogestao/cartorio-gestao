"""
O leitor de digital da casa — HID DigitalPersona, pelo navegador.

O QUE ESTE MÓDULO DECIDE (26/10/2026, decisão do oficial)
    A casa tem o leitor no padrão do e-Notariado, da família HID
    DigitalPersona U.are.U. O pedido falava em «DigitalPersona U 7500», e a
    decisão de 31/08/2026 do projeto do relato #39 em U.are.U 4500/4000b;
    perguntado, o oficial respondeu «esse mesmo» (26/10/2026): O MODELO É O
    HID DigitalPersona U.are.U 4500 (`MODELO_ESPERADO`). Nesta máquina de
    desenvolvimento não há driver, serviço nem programa da HID (medido só
    leitura); a confirmação é a decisão dele, e não a etiqueta lida aqui.

    O SDK/driver que este ramo usa para o U.are.U 4500 é o do próprio
    fabricante: o cliente local «HID DigitalPersona Lite Client» (também
    chamado «Authentication Device Client», que traz o driver do aparelho) e o
    DigitalPersona WebSDK — os dois arquivos JavaScript de `ARQUIVOS_DO_SDK`
    (`SDK_DO_LEITOR`). Nenhuma DLL do fabricante é carregada por processo nosso.

O CAMINHO ESCOLHIDO: O SDK WEB DO FABRICANTE, NO PRÓPRIO NAVEGADOR
    O fabricante instala no Windows do balcão o cliente local dele («HID
    DigitalPersona Lite Client» / «Authentication Device Client»), que fala
    com o aparelho pelo driver e abre um canal só em 127.0.0.1 para o
    navegador. O JavaScript do SDK web conversa com esse cliente; a tela
    recebe a imagem PNG do dedo e a envia pelo MESMO formulário do envio
    manual. Por que este caminho e não um serviço local nosso (o modelo do
    `a3_servico_local.py`):

      - o cliente do fabricante já é o «ajudante local» que o projeto do #39
        pedia, e é o mesmo que o e-Notariado exige no balcão: não se instala
        um segundo programa para o mesmo aparelho;
      - a DLL nativa do SDK carregada por processo nosso é o risco que o A3 já
        mostrou nesta casa (segfault mata o processo inteiro); no navegador,
        se o cliente cair, cai a captura — não o servidor;
      - nenhuma porta nova nossa para vigiar, nenhuma trava de origem nossa
        para manter.

    O preço, declarado: o SDK web NÃO entrega template no padrão ISO/ANSI
    (FMD). Os formatos dele são imagem crua, WSQ, PNG e o «intermediário»
    proprietário da DigitalPersona. A casa guarda o PNG e NÃO guarda o
    intermediário — dado biométrico se colhe no mínimo que a finalidade pede
    (LGPD art. 6º, III), e um formato que só o fabricante lê não serve ao CCN.

    E OS ARQUIVOS DO SDK NÃO VÊM NO REPOSITÓRIO. São do fabricante; quem os
    instala é o TI, copiando-os do pacote do SDK para a pasta que
    `pasta_do_sdk` diz. Sem eles a tela diz isso, e o envio manual continua.

O QUE ELE NÃO FAZ
    Não fala com o aparelho (quem fala é o cliente do fabricante, pelo
    navegador). Não compara digitais: a comparação 1:1 no reconhecimento de
    firma é a PRÓXIMA ETAPA, porque o SDK web não traz comparador — e quando
    vier, entra como ALERTA, nunca como trava (regra da casa: alerta não é
    trava). Não escreve nada: quem grava é `cadastro_biometria`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# O MODELO DO LEITOR — decisão do oficial em 26/10/2026 («esse mesmo»). Até
# então a tela dizia só a família («HID DigitalPersona (família U.are.U)»),
# porque o modelo não estava confirmado; agora está, e é o que a tela mostra.
MODELO_ESPERADO = "HID DigitalPersona U.are.U 4500"
NOME_DO_LEITOR = MODELO_ESPERADO
# O que o TI instala no computador do balcão para este modelo, como a tela e
# a documentação o dizem: o cliente do fabricante (com o driver) e o WebSDK.
CLIENTE_DO_FABRICANTE = "HID DigitalPersona Lite Client (Authentication Device Client)"
SDK_DO_LEITOR = "DigitalPersona WebSDK (JavaScript)"

# Os dois arquivos do SDK web do fabricante, na ordem em que carregam: o
# primeiro é o canal com o cliente local (o objeto `WebSdk`), o segundo é a
# API de captura (`Fingerprint.WebApi`). São os nomes que o pacote do SDK
# traz na amostra JavaScript. A lista é FECHADA: a rota que os serve não
# entrega outro arquivo daquela pasta.
ARQUIVOS_DO_SDK: tuple[str, ...] = (
    "websdk.client.bundle.min.js",
    "fingerprint.sdk.min.js",
)

# A configuração que muda a pasta, se o TI preferir outro lugar. Sem ela, a
# pasta é `<pasta de dados>\terceiros\digitalpersona`.
CHAVE_DA_PASTA = "leitor_digital_sdk_pasta"

# De onde veio a imagem do dedo. Fica gravado na linha, porque a conferência
# pergunta: «isto saiu do leitor no balcão, ou alguém mandou um arquivo?»
#
# E O QUE A LINHA PROVA TEM LIMITE — correção de segurança de 26/10/2026
# (revisão do PR #31). A origem é DECLARADA PELO NAVEGADOR: é um campo do
# formulário, e quem edita o campo manda um PNG qualquer como «do leitor».
# Sem canal assinado com o cliente do fabricante não há como provar a origem.
# O que o servidor faz: (1) recusa `LEITOR` quando o SDK nem está instalado
# nele — sem SDK, nenhuma tela poderia ter colhido no leitor; (2) a auditoria
# grava que a origem foi declarada pelo navegador; (3) a tela diz «informada
# como do leitor», e não «do leitor» como fato.
ORIGEM_LEITOR = "LEITOR"
ORIGEM_ARQUIVO = "ARQUIVO"
ORIGENS = (ORIGEM_LEITOR, ORIGEM_ARQUIVO)

# A FINALIDADE, como a tela a mostra e a documentação a repete. Dado
# biométrico é dado pessoal SENSÍVEL (LGPD art. 5º, II, e art. 11): a pessoa
# tem de saber para que ele serve antes de pôr o dedo no leitor.
FINALIDADE = (
    "Finalidade da coleta (LGPD, art. 11, II, «g» — prevenção à fraude e "
    "segurança do titular na identificação e na autenticação de cadastro): as "
    "digitais servem para identificar quem abre a ficha de firma neste cartório "
    "e quem volta para reconhecer firma, e para compor o Cadastro de Clientes "
    "do Notariado (CCN). Dado biométrico é dado pessoal sensível: fica só no "
    "cadastro desta serventia, não vai para relatório, auditoria nem para a "
    "ajuda, e não se usa para outra finalidade."
)

# A HIPÓTESE LEGAL — DECISÃO DO OFICIAL EM 26/10/2026, por recomendação;
# conferir com o encarregado de dados. A coleta se apoia na LGPD, art. 11,
# II, «g»: garantia da prevenção à fraude e da segurança do titular nos
# processos de identificação e autenticação de cadastro. DEIXOU DE SER
# CONSENTIMENTO (art. 11, I), que era a opção mais fechada enquanto a
# hipótese estava A CONFERIR (correção de segurança de 26/10/2026, revisão do
# PR #31).
#
# A CIÊNCIA DO TITULAR CONTINUA OBRIGATÓRIA ANTES DE COLHER — agora como
# TRANSPARÊNCIA (LGPD, art. 9º: o titular tem direito à informação clara
# sobre a finalidade), e não como consentimento: a marca no cartão
# (`nt_cartoes.biometria_ciencia_em/_por`) registra que a finalidade foi lida
# para a pessoa, por quem e quando. Sem ela NENHUMA DIGITAL SE COLHE — nem do
# leitor, nem de arquivo. A marca não é pedido de licença: a recusa da pessoa
# não se registra aqui, e o que fazer com ela é do balcão.
BASE_LEGAL = {
    "data": "26/10/2026",
    "hipotese": ("LGPD, art. 11, II, «g» — garantia da prevenção à fraude e da "
                 "segurança do titular nos processos de identificação e "
                 "autenticação de cadastro"),
    "decisao": ("decisão do oficial em 26/10/2026, por recomendação; conferir com o "
                "encarregado de dados"),
    "situacao": ("A ciência do titular é obrigatória antes de colher, como "
                 "transparência (art. 9º), e não como consentimento: nenhuma digital "
                 "se colhe sem ela registrada no cartão (quem informou e quando)."),
}

# O texto da caixa que o balcão marca, com a pessoa na frente. É o que fica
# provado: que a finalidade foi lida para ela — TRANSPARÊNCIA, e não
# consentimento (decisão de 26/10/2026, acima).
TEXTO_DA_CIENCIA = (
    "Li para a pessoa a finalidade acima e a informei de que as suas digitais "
    "serão colhidas para este cadastro, para a prevenção à fraude e a segurança "
    "dela na identificação."
)

# A IMAGEM DA DIGITAL NO DISCO: não cifrar a imagem da digital, decisão do
# oficial em 26/10/2026. O PNG fica em claro na pasta de arquivos (a pendência
# estava em `docs/tecnico/PROJETO_39_CADASTRO_CCN.md`, fatia 2b); o que
# protege a cópia externa é a cifra do backup (`backup.cred`).
IMAGEM_CIFRADA_NO_DISCO = False

# A assinatura do PNG. O SDK entrega PNG quando se pede `PngImage`; o que
# chegar marcado como do leitor e não for PNG não veio do leitor.
_ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"


def pasta_do_sdk(configurada: Any, pasta_de_dados: Any) -> Path:
    """Onde o TI põe os arquivos do SDK web. Só calcula; não cria.

    A configuração gravada manda; sem ela, `<pasta de dados>\\terceiros\\
    digitalpersona` — fora da pasta do programa, para a atualização do
    sistema não apagar o que o TI instalou.
    """
    escolhida = str(configurada or "").strip()
    if escolhida:
        return Path(escolhida)
    return Path(pasta_de_dados) / "terceiros" / "digitalpersona"


def estado_do_sdk(pasta: Any) -> dict:
    """O que está e o que falta na pasta do SDK. Só LÊ.

    `instalado` só é verdadeiro com OS DOIS arquivos: com um só, a tela
    carregaria metade da API e falharia no clique, que é o pior momento.
    """
    raiz = Path(pasta)
    presentes = [n for n in ARQUIVOS_DO_SDK if (raiz / n).is_file()]
    faltando = [n for n in ARQUIVOS_DO_SDK if n not in presentes]
    return {
        "pasta": str(raiz),
        "instalado": not faltando,
        "presentes": presentes,
        "faltando": faltando,
    }


def arquivo_do_sdk(pasta: Any, nome: str) -> Path | None:
    """O arquivo do SDK pedido, se for da lista e existir. Senão `None`.

    O nome que vem da URL nunca vira caminho: só se aceita um dos nomes de
    `ARQUIVOS_DO_SDK`, e por isso `..` ou barra não chegam ao disco.
    """
    if nome not in ARQUIVOS_DO_SDK:
        return None
    caminho = Path(pasta) / nome
    return caminho if caminho.is_file() else None


def recusa_da_origem(origem: Any, sdk_instalado: bool) -> str | None:
    """A frase de recusa quando a origem declarada não pode ser verdade; senão
    `None`. Só calcula.

    `LEITOR` sem o SDK instalado no servidor é impossível: a tela não teria
    como ter falado com o aparelho. O que sobra (o SDK instalado e o campo
    editado à mão) não se distingue daqui — ver `ORIGEM_LEITOR`.
    """
    if str(origem or "").strip().upper() == ORIGEM_LEITOR and not sdk_instalado:
        return ("A digital veio marcada como colhida no leitor, mas o SDK do "
                "leitor não está instalado neste servidor — nenhuma tela poderia "
                "ter falado com o aparelho. Nada foi gravado. Envie a imagem pelo "
                "campo de arquivo do dedo.")
    return None


def e_png(dados: bytes) -> bool:
    """Os bytes começam com a assinatura do PNG?"""
    return bytes(dados[:8]) == _ASSINATURA_PNG
