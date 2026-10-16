"""AS CREDENCIAIS DAS CENTRAIS — fora do banco, como as outras.

(O título dizia «Centrais de Protesto», e deixou de ser verdade em
03/09/2026: a ONRTDPJ é do RCPJ e do RTD.)

Construído em 02/09/2026, quando o oficial cadastrou o usuário da API da
CENPROT e perguntou *«mando onde?»*.

**A RESPOSTA A ESSA PERGUNTA É: NÃO ME MANDE.** Senha que passa por uma
conversa fica na conversa; senha que entra no banco viaja no backup, e **o
backup desta serventia já saiu daqui**. Ela é digitada pelo oficial numa tela
e gravada num arquivo em `%PROGRAMDATA%\\CartorioGestao\\`, ao lado do
`selador.cred`, do `claude.cred` e do `secret.key` — os três lugares que o
backup não alcança.

**SÃO TRÊS CENTRAIS, E ELAS NÃO SE PARECEM:**

    cra.cred      usuário e senha  ·  HTTP Basic no cliente SOAP da CRA21
    cenprot.cred  usuário e senha  ·  POST /token na API do cartório da CENPROT
    onrtdpj.cred  **um token só**  ·  cabeçalho `Authorization` na Central RTDPJ

**E A TERCEIRA MUDOU A PREMISSA DESTE MÓDULO, em 03/09/2026.** Estava escrito
aqui que as Centrais «guardam a mesma forma — um par usuário/senha por
ambiente —, então elas moram juntas». **A ONRTDPJ não guarda um par**: o
contrato dela declara `apiKey` no cabeçalho `Authorization`, e o token é
gerado pelo próprio cartório na Central, em *Serviços > Envio Extrato
SINTER*.

**E O NOME DESSE MENU CONFUNDE, porque o SINTER foi desligado.** A Receita
Federal comunicou em **24/08/2023** que desabilitou o recebimento de
informações pelo SINTER no formato de então, e que os cartórios não devem
mais enviar. **O que foi desligado é o ENVIO; o token continua existindo
naquele menu e continua servindo à API da Central** — conferido pelo
oficial em 03/09/2026, que o encontrou lá. Fica escrito porque quem souber
da notícia e não desta distinção concluiria que o token morreu junto.

Ela continua morando aqui mesmo assim, e a razão é a mesma de antes pelo outro
lado: **o que não pode divergir é o pedaço que guarda segredo fora do banco** —
onde o arquivo fica, como se lê, como se apaga quando a Central troca a
credencial. Um quarto módulo com esse corpo seria a quarta versão divergente
dele. O que muda é a FORMA do que se guarda, e ela está declarada em
`FORMA_DA_CENTRAL`.

**E A ONRTDPJ TEM UM AMBIENTE SÓ, porque o contrato declara um host só.** O
`swagger` público traz `host: centralinside.rtdbrasil.org.br` e mais nenhum.
Inventar um endereço de homologação seria inventar número — e o pior tipo,
porque quem o usasse acharia que está testando enquanto fala com a Central de
verdade.

**E ESTE MÓDULO É UM, E NÃO TRÊS.** O selador e a ajuda do Claude têm cada um
o seu, e isso está certo — nasceram meses antes e guardam coisas diferentes.
Escrever aqui um quarto e um quinto arquivo com o mesmo corpo daria **cinco
versões divergentes do pedaço que guarda segredo**, e é o defeito que este
projeto já pagou quatro vezes com a `normalizar_nome`.

**O AMBIENTE FAZ PARTE DA CHAVE, E NÃO É DETALHE — onde há dois.** A CRA tem
homologação e produção, com credenciais diferentes, e o oficial vai começar pela
homologação — é o que a P21 ofereceu em 02/09/2026. Guardar uma credencial só
faria a troca de ambiente exigir redigitar a senha, e no dia da virada alguém
usaria a de teste contra a Central de verdade.

**E A VIRADA ACONTECEU EM 14/10/2026** — *«tire a opção de funcionar na
homologação, agora é tudo produção»*. A CRA, a CENPROT e a Resolve passaram a
ter uma linha só na tela, a de produção (`CENTRAIS_SO_EM_PRODUCAO`). A gaveta
de homologação continua no arquivo, intocada: o que mudou foi quem a oferece.

**ESTE MÓDULO NÃO FALA COM CENTRAL NENHUMA.** Ele só guarda e devolve. Quem
autentica é `cenprot_api`, `onrtdpj_api` e o cliente da CRA — e é por isso que
`credencial()` tem um nome que não se confunde: quem a chama está prestes a
autenticar, e qualquer outro uso é vazamento.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# LEITURA DOS `.cred` — `utf-8-sig` aceita arquivo com ou sem BOM. Espelhos
# feitos no Windows (PowerShell `Set-Content -Encoding utf8`, Notepad) trazem
# BOM; `json.loads` em texto lido só com `utf-8` falha e `tem()` devolve falso.
CODIFICACAO_DO_ARQUIVO = "utf-8-sig"

# AS OITO CENTRAIS, e o arquivo de cada uma.
#
#   **O comentário dizia «AS TRÊS» com quatro na linha de baixo**, e depois
#   «AS CINCO» com seis, e depois «AS SETE» com sete — o mesmo descuido, três
#   vezes. Carimbo que conta errado o tamanho da própria lista é o «carimbo que
#   mente» na sua forma mais barata — e a mais fácil de deixar passar; por isso
#   há teste que compara este número com a tupla de baixo.
#
#   **E o CNIB entrou em 18/09/2026 como CENTRAL PRÓPRIA, com par próprio** — e
#   não como um caminho a mais do ONR. Medido: o `client_id` que autentica
#   nela é `cns-000000`, que **não está em `onr.cred`** (arquivo que, aliás,
#   não existe nesta máquina), e o token sai de
#   `auth.id.onr.org.br/connect/token` com escopo `cnib-serventia-api`. O par
#   que esta casa usa hoje **veio do acervo**, de `tbCNIB_Propriedades` — duas
#   colunas: `Cliente_ID` e `Secret_Code`.
CRA, CENPROT, ONRTDPJ, ONRCPN, ONR, RESOLVE, SIRC, CNIB = (
    "CRA", "CENPROT", "ONRTDPJ", "ONRCPN", "ONR", "RESOLVE", "SIRC", "CNIB")
# A CENSEC (CNB-CF) — a carga das Notas por API, 09/10/2026. Ver `censec_api`.
CENSEC = "CENSEC"

ARQUIVO_DA_CENTRAL: dict[str, str] = {
    CRA: "cra.cred",
    CENPROT: "cenprot.cred",
    ONRTDPJ: "onrtdpj.cred",
    ONRCPN: "onrcpn.cred",
    ONR: "onr.cred",
    RESOLVE: "resolve.cred",
    SIRC: "sirc.cred",
    CNIB: "cnib.cred",
    CENSEC: "censec.cred",
}

# O QUE CADA UMA GUARDA. **`PAR` é usuário e senha; `TOKEN` é um segredo só.**
#
#   Sem esta declaração, `gravar` exigiria um usuário que a ONRTDPJ não tem, e
#   alguém preencheria o campo com o CNS para a tela deixar salvar — e aí o
#   arquivo passaria a guardar uma coisa dizendo que guarda outra.
PAR, TOKEN = "PAR", "TOKEN"
FORMA_DA_CENTRAL: dict[str, str] = {
    CRA: PAR,
    CENPROT: PAR,
    ONRTDPJ: TOKEN,
    # A ON-RCPN DEVOLVE UM PAR E CONTINUA `TOKEN`, DE PROPÓSITO — e o porquê
    # ficou MAIOR em 18/09/2026, quando o manual do IdRC chegou.
    #
    #   O cadastro devolve `clientID` + `client secret` (medido na tela de
    #   aprovação). Só que **`PAR` não a descreveria**: `PAR` faz o sistema
    #   MINAR o token sozinho, e o token que as APIs dela consomem é o do
    #   **usuário**, de **5 minutos**, que sai de um `authorization_code` —
    #   login de gente, com URL de redirecionamento. O caminho medido **não
    #   permite mineração**.
    #
    #   > Trocar `TOKEN` por `PAR` aqui seria um conserto que não conserta: a
    #   > tela passaria a pedir dois campos e o sistema continuaria incapaz de
    #   > obter o token. O que a casa precisaria, para valer, é de um endereço
    #   > de retorno no cadastro e de renovação pelo `refresh_token` — ou de a
    #   > Central aceitar o `client_credentials` que o reino declara, e isso
    #   > ainda não se mediu. Ver `FONTES_EXTERNAS/onrcpn/LEIA-ME.md` e o
    #   > item 4 do cabeçalho de `onrcpn_api`.
    ONRCPN: TOKEN,
    # O ONR É `PAR` PORQUE O CONTRATO DELE DECLARA O QUE FAZER COM O PAR.
    #
    #   `POST /v1/auth/token` recebe `client_id`, `client_secret` e
    #   `grant_type=client_credentials` e devolve um `access_token` com
    #   `expires_in`. **É a diferença que separa esta da ON-RCPN, e ela
    #   AUMENTOU**: lá o token é de usuário e de cinco minutos; aqui o
    #   contrato declara o endereço, o corpo e a resposta — logo esta guarda o
    #   par e mina o token sozinha, e aquela guarda o token que alguém colou.
    ONR: PAR,
    # A RESOLVE É `TOKEN`, E O SEGREDO SE CHAMA `x-api-key`.
    #
    #   O contrato declara três esquemas — `basicAuth`, `bearerAuth` e
    #   `apiKeyAuth` —, e **as operações usam o terceiro**: todas trazem
    #   `x-api-key` como parâmetro de cabeçalho obrigatório. Os outros dois
    #   estão declarados e não são aplicados a operação nenhuma. Guardar um
    #   par aqui faria a tela pedir um usuário que a Central não dá.
    RESOLVE: TOKEN,
    # O SIRC É `PAR`, E O PAR VAI DENTRO DO CORPO SOAP — não em HTTP Basic
    # como a CRA. Medido no WSDL público (`SircWs/Movimento?wsdl`,
    # 14/09/2026): toda operação de envio/validação recebe `{cns, usuario,
    # senha, conteudo}` como elementos do próprio XML. É a mesma FORMA da
    # CRA (par, e não token) por um TRANSPORTE diferente — a diferença fica
    # em `sirc_cliente.py`, e não aqui.
    SIRC: PAR,
    # O CNIB É `PAR` COMO O ONR, E PELO MESMO TESTE: o contrato dele declara
    # o endereço do token, o corpo e a resposta.
    #
    #   `POST https://auth.id.onr.org.br/connect/token`, corpo
    #   `client_id` + `client_secret` + `grant_type=client_credentials` +
    #   `scope=cnib-serventia-api`. Medido em 18/09/2026: a Central responde
    #   `{access_token, expires_in: 3600, token_type: Bearer}`, e o token
    #   decodificado traz `client_id: cns-000000` e o escopo `cnib-serventia-api`.
    #   **Declarar o fluxo é o que separa `PAR` de `TOKEN`** — a mesma régua
    #   que deixou a ON-RCPN em `TOKEN` por não permitir mineração.
    CNIB: PAR,
    # A CENSEC É `TOKEN`, E O SEGREDO SE CHAMA `X-Api-Key`.
    #
    #   Medido no contrato público (`censec.org.br/swagger/api/swagger.json`,
    #   «CENSEC API» 2.71.0, 09/10/2026): `security: [{ApiKey}]`, esquema
    #   `apiKey` no cabeçalho `X-Api-Key`, aplicado ao documento inteiro. O
    #   segundo esquema declarado (`AppToken`, no `Authorization`) não é o das
    #   cargas. A chave é gerada pelo próprio cartório, dentro da CENSEC.
    CENSEC: TOKEN,
}

# COMO SE CHAMAM AS DUAS METADES DO PAR, EM CADA CENTRAL.
#
#   **«usuário e senha» está errado no ONR**, e não é preciosismo: quem
#   procurar um «usuário» na Central não acha nada, e o que ela dá é um
#   `client_id`. Rótulo que não é o nome que a Central usa manda o oficial
#   procurar o que não existe — a lição da credencial do selador, que mandava
#   conferir «no E-Ofício» um cadastro que não a tem.
ROTULOS_DO_PAR: dict[str, tuple[str, str]] = {
    ONR: ("client_id", "client secret"),
    # O CNIB USA OS MESMOS DOIS RÓTULOS DO ONR, e eles não são coincidência:
    # as duas passam pelo mesmo provedor de identidade (`auth.id.onr.org.br`).
    # O par desta casa veio de `tbCNIB_Propriedades`, cujas colunas se chamam
    # **`Cliente_ID` e `Secret_Code`** — e é o mesmo nome em outra língua, o
    # que é justamente o que faz alguém preencher o campo errado.
    CNIB: ("client_id", "client secret"),
}
PAR_PADRAO: tuple[str, str] = ("usuário", "senha")


def rotulos_do_par(central: Any) -> tuple[str, str]:
    """Como aquela Central chama as duas metades do par. Só calcula."""
    return ROTULOS_DO_PAR.get(_central(central), PAR_PADRAO)


# DE ONDE SAI O TOKEN DE CADA CENTRAL QUE GUARDA UM — e não é do mesmo lugar.
#
#   **A RECUSA MANDAVA AS TRÊS PARA O SINTER, e só uma delas fica lá.**
#   Medido em 18/09/2026: `token_guardado` dizia, para qualquer Central que
#   guarda token, «entre em rtdbrasil.org.br e vá em Serviços → Envio Extrato
#   SINTER». São **três** nesta forma — ONRTDPJ, ON-RCPN e Resolve —, e a
#   frase está certa para **uma**. Quem seguisse a instrução com o ON-RCPN
#   entraria no rtdbrasil, não acharia nada, e concluiria que o sistema está
#   errado — quando o errado era o endereço que a tela deu.
#
#   É a lição da credencial do selador («conferir a credencial do E-Ofício»,
#   que mandava procurar num cadastro que não a tem) pela segunda vez, e a da
#   `normalizar_nome`: **uma frase só para três casos diferentes acerta um e
#   mente nos outros dois.** Cada uma com a sua, e há teste que exige entrada
#   para toda Central de forma `TOKEN`.
ONDE_SE_OBTEM_O_TOKEN: dict[str, str] = {
    ONRTDPJ: (
        "entre em https://www.rtdbrasil.org.br/autenticacao/login e vá em "
        "Serviços → Envio Extrato SINTER. **O nome do menu confunde**: a "
        "Receita Federal desligou o ENVIO ao SINTER em 24/08/2023, mas o "
        "TOKEN gerado ali continua sendo o da API da Central — conferido pelo "
        "oficial em 03/09/2026."
    ),
    ONRCPN: (
        "ele **não se copia de uma tela**: sai do IdRC, pelo fluxo "
        "`authorization_code`, **depois de uma pessoa se autenticar**. O "
        "client se cadastra em https://integracao.idrc.registrocivil.org.br, "
        "no botão «Novo Client» — e a página só abre para quem já tem usuário "
        "IdRC, que se cria em https://www.homeh.registrocivil.org.br. O "
        "cadastro exige uma URL de retorno, que **pode ser local**."
    ),
    RESOLVE: (
        "ela é a `x-api-key` que a plataforma entrega **depois da adesão à "
        "Intimação Digital**, e não um token de tela: não há `/token` nesta "
        "API — a chave vai em toda requisição, no cabeçalho `x-api-key`."
    ),
    CENSEC: (
        "ela é a «chave de integração» que o próprio cartório gera DENTRO da "
        "CENSEC (https://censec.org.br, com o login da serventia), conforme o "
        "artigo «CENSEC - Geração da chave de integração (API)» do suporte do "
        "CNB (suporte.notariado.org.br). **Homologação e produção têm chaves "
        "diferentes**: a de homologação se gera em https://hml.censec.org.br."
    ),
}

# OS AMBIENTES. `HOMOLOGACAO` primeiro de propósito: é onde se começa, e é o
# padrão de fábrica das Centrais que ainda estão nela — ver `onr_api`.
#
# **AS TRÊS DO PROTESTO SAÍRAM DESSA REGRA EM 14/10/2026**, primeiro dia do
# protesto operando no sistema. Ordem do oficial: *«tire a opção de funcionar
# na homologação, agora é tudo produção»*. Ver `CENTRAIS_SO_EM_PRODUCAO`.
HOMOLOGACAO, PRODUCAO = "HOMOLOGACAO", "PRODUCAO"

# **E HÁ UM TERCEIRO, QUE SÓ A RESOLVE TEM.** O contrato dela declara três
# `servers` — testes, homologação e produção —, e não dois. Encaixá-la nos
# dois de sempre faria a casa perder o ambiente onde se experimenta sem
# combinar nada com ninguém, ou — pior — usar o de homologação achando que é
# o de testes.
TESTES = "TESTES"
AMBIENTES: tuple[str, ...] = (HOMOLOGACAO, PRODUCAO)

# AS CENTRAIS DE PROTESTO FUNCIONAM SÓ EM PRODUÇÃO — ordem do oficial em
# 14/10/2026: *«tire a opção de funcionar na homologação, agora é tudo
# produção»*.
#
#   **O QUE ISTO MUDA:** nenhuma tela oferece mais homologação nem testes para
#   a CRA, a CENPROT e a Resolve; o padrão, e o único caminho que o sistema
#   usa, é `PRODUCAO`; a tabela de credenciais mostra só a linha de produção
#   delas; e o que estiver gravado em outro ambiente (pendência, intimação,
#   lote) **não se responde nem se envia** — `ambiente_de_uso` recusa, dizendo
#   por quê.
#
#   **O QUE ISTO NÃO MUDA:** nada se apaga. O `HOMOLOGACAO` e o `TESTES`
#   guardados em `cra.cred`, `cenprot.cred` e `resolve.cred` ficam no arquivo
#   (medido em 14/10/2026: os três têm as duas chaves), e os endereços de
#   homologação continuam declarados nos transportes — servem ao teste
#   automatizado, que os pede pelo nome. O que deixou de existir é a tela
#   oferecê-los, ou o sistema cair neles por omissão.
CENTRAIS_SO_EM_PRODUCAO: frozenset[str] = frozenset({CRA, CENPROT, RESOLVE,
                                                     CENSEC, ONR})

# A CENSEC E O ONR ENTRARAM NA MESMA REGRA EM 15/10/2026 — ordem do oficial:
# *«tira as telas e referências a homologação nas centrais que já configuramos
# a produção (deixa no código)»*. Medido no mesmo dia: `censec.cred` e
# `onr.cred` só tinham a chave de produção. Ficaram de fora o ON-RCPN (sem
# credencial nenhuma, e o contrato só publica homologação), a CRC (assinada
# com A3, sem `.cred`, e sem envio pela produção ainda) e o CCN (sem a chave
# do Colégio Notarial) — essas continuam oferecendo homologação.
#
# A DATA DA VIRADA É DE CADA UMA, e a frase da recusa a diz — com uma data só,
# a frase da CENSEC afirmaria uma ordem de 14/10 que foi dada em 15/10.
VIROU_PRODUCAO_EM: dict[str, str] = {
    CRA: "14/10/2026", CENPROT: "14/10/2026", RESOLVE: "14/10/2026",
    CENSEC: "15/10/2026", ONR: "15/10/2026",
}

NOME_DA_CENTRAL: dict[str, str] = {
    CRA: "CRA — Central de Remessa de Arquivos (IEPTB-MA)",
    # «Resolve» é o nome da Intimação Digital (a linha RESOLVE, abaixo) — com a
    # mesma palavra nas duas linhas, quem cadastra põe a chave de uma na outra.
    # Pedido do oficial em 13/10/2026: «tirar o resolve do usuário de cima».
    CENPROT: "CENPROT Nacional — API do cartório (anuências, certidões, cancelamentos)",
    ONRTDPJ: "Central ONRTDPJ — API Cartórios (RTDPJBrasil)",
    ONRCPN: "ON-RCPN — e-Proclamas e Certidão Eletrônica (IdRC)",
    ONR: "ONR — Registro de Imóveis do Brasil",
    RESOLVE: "Resolve — Intimação Digital (CENPROT)",
    SIRC: "SIRC — Sistema Nacional de Informação de Registro Civil (INSS)",
    CNIB: "CNIB — Central Nacional de Indisponibilidade de Bens (ONR)",
    CENSEC: "CENSEC — carga da CEP, CESDI e RCTO por API (CNB-CF)",
}

# OS AMBIENTES QUE CADA UMA TEM. A ONRTDPJ tem **um só**, e é o de verdade —
# ver o cabeçalho. Quem não estiver nesta tabela tem os dois.
AMBIENTES_DA_CENTRAL: dict[str, tuple[str, ...]] = {
    # O CNIB TEM UM AMBIENTE SÓ, E NÃO É ESCOLHA — é o que existe.
    #
    #   O contrato dele **não declara `servers`**: vem `null`, medido. Então
    #   não há de onde tirar o endereço de homologação, e o de produção foi
    #   medido em DNS. **E as variantes de homologação NÃO RESOLVEM** — medidas
    #   em 18/09/2026: `serventia-api-hml`, `serventia-api-homolog` e
    #   `serventia-api-teste` não existem em DNS, e `serventia-api.sandbox`
    #   também não. Só `serventia-api.onr.org.br` (2.18.20.134).
    #
    #   **Palpite aqui seria o pior tipo de número inventado**: um endereço de
    #   homologação inventado faz quem o use achar que está testando enquanto
    #   fala com a Central de verdade — e aqui o que sobe é indisponibilidade
    #   de bens, com o CNS desta serventia no cabeçalho.
    CNIB: (PRODUCAO,),
    ONRTDPJ: (PRODUCAO,),
    # AS TRÊS DO PROTESTO TÊM UM AMBIENTE SÓ DESDE 14/10/2026 — e não porque o
    # contrato declare um só: a CRA e a CENPROT declaram dois, e a Resolve
    # três (`TESTES`, homologação, produção, medidos em 03/09/2026 no
    # `/api/status`). É ORDEM do oficial, no primeiro dia operando o protesto:
    # «agora é tudo produção». Ver `CENTRAIS_SO_EM_PRODUCAO`.
    #
    #   Até 13/10/2026 a CRA e a CENPROT caíam na regra geral (os dois) e a
    #   Resolve estava aqui com `(HOMOLOGACAO, PRODUCAO)`. Os endereços dos
    #   outros ambientes continuam nos transportes, para o teste automatizado.
    CRA: (PRODUCAO,),
    CENPROT: (PRODUCAO,),
    RESOLVE: (PRODUCAO,),
    # A CENSEC E O ONR DESDE 15/10/2026, pela mesma razão (ordem do oficial,
    # com a produção já configurada). Os endereços de homologação continuam
    # em `censec_api.BASE_DO_AMBIENTE` e `onr_api`, pedidos pelo nome.
    CENSEC: (PRODUCAO,),
    ONR: (PRODUCAO,),
    # A ON-RCPN É O ESPELHO DA ONRTDPJ, E PELO MOTIVO OPOSTO. Ali o contrato
    # declara **só a produção**; aqui os dois contratos publicados declaram
    # **só a homologação** — `servicosh.` e `certidaoh.`, com o «h».
    #
    #   **A PRIMEIRA RAZÃO DESTA LINHA CAIU EM 18/09/2026, E FICA ESCRITA.**
    #   Ela dizia que o endereço de produção «não existe publicado em algum
    #   lugar que esta casa tenha lido», e que tirar o «h» seria palpite.
    #   **Medido agora: os dois hosts de produção existem e respondem** — o
    #   `health` do e-Proclamas devolve `200` com o mesmo corpo nos dois, e o
    #   `swagger.json` da Certidão é o mesmo contrato nos dois. A
    #   correspondência «h = homologação» estava certa; o que faltava era
    #   **quem a medisse**, e a lição é essa: palpite e medição podem coincidir,
    #   e só a segunda se pode citar.
    #
    #   **O AMBIENTE SÓ CONTINUA SENDO UM, e agora por uma razão só — a
    #   MEDIDA**: o campo «Ambiente de criação» do formulário tem dois valores,
    #   e escolhendo `producao` nasce um campo **obrigatório** — «Protocolo do
    #   client de homologação» —, com o texto «informe o protocolo da
    #   solicitação de criação do client em homologação **já existente para
    #   esta mesma plataforma/projeto**». Isso foi lido em 03/09/2026 **no
    #   código do próprio formulário do IdRC** — no chunk que desenha a tela de
    #   solicitação de client —, quando o oficial perguntou como preenchê-lo.
    #
    #   **O NOME DAQUELE ARQUIVO NÃO SE CITA, E A PROVA É ELE MESMO.** Ele mora
    #   em `assets/` com um **hash de build** no nome: em 03/09/2026 era
    #   `SolicitacaoView-CW64dNQw.js`; medido de novo em 18/09/2026, **o mesmo
    #   campo está noutro arquivo** — `SolicitacaoView-NmHChTmQ.js`. O hash
    #   mudou; o campo (`protocoloHomologacao`) e o rótulo («Protocolo do client
    #   de homologação») continuam os mesmos, conferidos hoje. Citar arquivo com
    #   hash é citar o que já não existe, então a citação é a que sobrevive a
    #   qualquer build: a tela, o campo e o rótulo. Quem for conferir procura o
    #   bundle de entrada e segue os nomes de chunk, não o hash.
    #
    #   **E A REGRA, LIDA NO MESMO CHUNK EM 18/09/2026, É LITERAL:**
    #   `ambiente && (ambiente !== "producao" || protocoloHomologacao)` — o
    #   protocolo só é exigido quando o ambiente é produção. Os **valores** do
    #   campo são `homologacao` e `producao`, sem acento (o rótulo é que tem:
    #   «Homologação» e «Produção»), e o payload inteiro do formulário tem dez
    #   campos, medidos: `name`, `baseUrl`, `redirectUrls[]`,
    #   `responsibleName`, `responsibleEmail`, `responsibleCpf`, `CPFs[]`,
    #   `ambiente`, `protocoloHomologacao` e `descricao`.
    #
    #   > **E O MANUAL DO IdRC NÃO MENCIONA ESSE CAMPO** — ele é o manual do
    #   > **caminho de homologação**, e só. Quem procurar os dois termos lá e
    #   > não os achar **não achou onde procurou**: os campos estão no
    #   > formulário, o fluxo está no manual. Isto fica registrado porque eu
    #   > mesmo quase apaguei a razão certa depois de ler o documento errado.
    ONRCPN: (HOMOLOGACAO,),
    # **O SIRC TAMBÉM TEM UM AMBIENTE SÓ** — o WSDL público declara um único
    # `<soap12:address>` (`sirc.dataprev.gov.br`), sem um segundo endereço de
    # homologação em lugar nenhum do contrato. Igual à ONRTDPJ, e pelo mesmo
    # motivo: não se inventa endereço que o contrato não publica.
    SIRC: (PRODUCAO,),
    # **O ONR FICOU FORA DESTA TABELA ATÉ 15/10/2026, E A RAZÃO SEGUE CERTA.**
    # Ele é a única das cinco cujo contrato declara **os dois** endereços em
    # `servers` — `api.` e `testes-api.` —, e os dois continuam no
    # transporte. O que mudou foi a ordem de usar só a produção (acima).
}


def ambientes_de(central: Any) -> tuple[str, ...]:
    """Os ambientes daquela Central. Só calcula."""
    return AMBIENTES_DA_CENTRAL.get(_central(central), AMBIENTES)

# O QUE A CENPROT EXIGE DA SENHA, do «Manual de Autenticação» dela: oito
# caracteres, com maiúscula, minúscula, número e caractere especial.
#
# **CONFERIR AQUI POUPA UMA VIAGEM ATÉ O 401.** A recusa da Central chega sem
# dizer o que está errado; a daqui diz. E é só para a CENPROT: a CRA não
# publica exigência nenhuma, e inventar uma faria o sistema recusar uma senha
# que a Central aceita.
MINIMO_DA_SENHA_CENPROT = 8


class CredencialError(ValueError):
    """Erro de regra, com a mensagem pronta para o balcão."""


def pasta_de_dados() -> Path:
    """Onde o backup não alcança. A mesma de `selador.cred`."""
    return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "CartorioGestao"


def _central(qual: Any) -> str:
    nome = str(qual or "").strip().upper()
    if nome not in ARQUIVO_DA_CENTRAL:
        raise CredencialError(
            f"Central desconhecida: «{qual}». As que existem são "
            f"{', '.join(sorted(ARQUIVO_DA_CENTRAL))}.")
    return nome


def _ambiente(qual: Any, central: Any = None) -> str:
    """O ambiente, validado contra os que AQUELA Central tem.

    **A RÉGUA ERA UMA SÓ, E ELA NÃO SERVIA À RESOLVE — corrigido em
    18/09/2026.** Ela validava contra `AMBIENTES` (dois) e devolvia
    `HOMOLOGACAO` para qualquer outra palavra. A Resolve declara **três**
    (`TESTES`, `HOMOLOGACAO`, `PRODUCAO`) na tabela logo acima — e por isso o
    `TESTES` dela era **dobrado para `HOMOLOGACAO` em silêncio**: medido, o
    token gravado escolhendo «TESTES» na tela ia para o arquivo como
    `{"HOMOLOGACAO": …}`, e `tem()` devolvia **True nos dois ambientes**.

    O estrago não é cosmético: são **duas réguas** decidindo a mesma coisa —
    a do depósito e a do transporte (`resolve_api._ambiente`, que devolve
    `TESTES` corretamente) —, e quando elas discordam, o **endereço** vem de
    uma e a **chave**, da outra. Chave de testes contra o host de homologação
    é exatamente o que aquele módulo foi escrito para evitar («começar na
    produção por omissão é o que esta escolha evita»).

    Sem `central`, o comportamento é o de antes — é o que a `onr_api` usa.

    **AS TRÊS DO PROTESTO, DESDE 14/10/2026:** vazio ou desconhecido é
    `PRODUCAO` — é o padrão e o único caminho que o sistema usa. Mas
    `HOMOLOGACAO` e `TESTES` **pedidos pelo nome** continuam lendo a gaveta
    deles: a credencial guardada não se apaga, e o teste automatizado que
    fala com o endereço de homologação tem de falar com a chave de
    homologação — o contrário seria endereço de um ambiente com a chave do
    outro. Quem impede que uma TELA ou um fluxo do balcão os use é
    `ambiente_de_uso`, e não esta régua.
    """
    nome = str(qual or "").strip().upper()
    validos = ambientes_de(central) if central is not None else AMBIENTES
    if central is not None and _central(central) in CENTRAIS_SO_EM_PRODUCAO:
        if nome in (HOMOLOGACAO, PRODUCAO, TESTES):
            return nome
        return PRODUCAO
    return nome if nome in validos else validos[0]


def ambiente_de_uso(central: Any, pedido: Any = None) -> str:
    """O ambiente em que o sistema fala com aquela Central. Só calcula.

    **Para as três do Protesto é sempre `PRODUCAO`** (ordem do oficial em
    14/10/2026). Vazio vira produção; homologação ou testes pedidos — porque
    vêm de uma pendência, de uma intimação ou de um lote gravado antes da
    virada — são **recusados com a frase**, e não trocados por produção em
    silêncio: a resposta a uma anuência de homologação mandada à produção
    falaria de um código que lá é de outra anuência (os dois ambientes
    devolvem códigos do mesmo intervalo).

    Para as outras Centrais, devolve a régua de sempre.
    """
    qual = _central(central)
    nome = str(pedido or "").strip().upper()
    if qual not in CENTRAIS_SO_EM_PRODUCAO:
        return _ambiente(nome, qual)
    if nome in ("", PRODUCAO):
        return PRODUCAO
    rotulo = {HOMOLOGACAO: "homologação", TESTES: "testes"}.get(nome, nome)
    raise CredencialError(
        f"Desde {VIROU_PRODUCAO_EM[qual]} o sistema fala com a {NOME_DA_CENTRAL[qual]} só "
        f"em produção — ordem do oficial. Isto é do ambiente de {rotulo}, "
        f"que não se usa mais: o que estiver gravado nele fica como "
        f"histórico, e nada se responde, envia ou grava nele por aqui.")


def _falta_a_de_producao(qual: str, guardado: dict) -> str:
    """A frase de quando a credencial de PRODUÇÃO de uma Central do Protesto
    não está gravada. Só calcula.

    **Ela diz que é a de produção que falta, com todas as letras** — pedido
    do oficial em 14/10/2026. E, se a de homologação estiver guardada, diz
    que ela continua lá e não serve: sem isso, quem a cadastrou meses atrás
    acharia que o sistema perdeu a senha.
    """
    sobra = [onde for onde in (HOMOLOGACAO, TESTES)
             if any(str(v or "").strip()
                    for v in (guardado.get(onde) or {}).values())]
    palavra = "o token" if FORMA_DA_CENTRAL[qual] == TOKEN else "a credencial"
    frase = (f"{palavra[0].upper()}{palavra[1:]} de PRODUÇÃO da "
             f"{NOME_DA_CENTRAL[qual]} ainda não foi informad"
             f"{'o' if palavra == 'o token' else 'a'}. Desde {VIROU_PRODUCAO_EM[qual]} o "
             f"sistema usa só a produção; informe-a em Administrativo → "
             f"Configurações, na seção «Centrais — credenciais das APIs», "
             f"onde ela fica gravada fora do banco.")
    if sobra:
        nomes = " e ".join({HOMOLOGACAO: "homologação",
                            TESTES: "testes"}[x] for x in sobra)
        frase += (f" A de {nomes} continua guardada, mas não é usada — ela "
                  f"não serve no lugar da de produção.")
    if FORMA_DA_CENTRAL[qual] == TOKEN and qual in ONDE_SE_OBTEM_O_TOKEN:
        frase += f" Para obtê-lo: {ONDE_SE_OBTEM_O_TOKEN[qual]}"
    return frase


def fora_de_uso(central: Any, pasta: Any = None) -> list[str]:
    """Os ambientes que têm credencial guardada e que o sistema não usa mais.

    Só para as três do Protesto. **Não devolve segredo** — só o nome do
    ambiente, para a tela dizer «a de homologação continua guardada, mas não
    é usada» em vez de deixar o oficial achar que perdeu alguma coisa.
    """
    qual = _central(central)
    if qual not in CENTRAIS_SO_EM_PRODUCAO:
        return []
    return [onde for onde in (HOMOLOGACAO, TESTES) if tem(qual, onde, pasta)]


def caminho(central: Any, pasta: Any = None) -> Path:
    """O arquivo daquela Central. Só calcula — não lê nada."""
    base = Path(pasta) if pasta else pasta_de_dados()
    return base / ARQUIVO_DA_CENTRAL[_central(central)]


def _conferir_senha_da_cenprot(senha: str) -> None:
    """As quatro exigências do manual da CENPROT, com a frase de cada uma."""
    faltam = []
    if len(senha) < MINIMO_DA_SENHA_CENPROT:
        faltam.append(f"ter pelo menos {MINIMO_DA_SENHA_CENPROT} caracteres")
    if not any(c.isupper() for c in senha):
        faltam.append("ter uma letra maiúscula")
    if not any(c.islower() for c in senha):
        faltam.append("ter uma letra minúscula")
    if not any(c.isdigit() for c in senha):
        faltam.append("ter um número")
    if not any(not c.isalnum() for c in senha):
        faltam.append("ter um caractere especial")
    if faltam:
        raise CredencialError(
            "A CENPROT exige que a senha da API " + ", ".join(faltam[:-1])
            + (" e " if len(faltam) > 1 else "") + faltam[-1]
            + ". Ela é a que você cadastrou em Cadastro → Cadastro do Cartório "
            "→ Informações de Autenticação da API.")


def gravar(central: Any, *, usuario: str, senha: str,
           ambiente: Any = None, pasta: Any = None) -> Path:
    """Guarda o par daquela Central e ambiente. ESCREVE EM DISCO, não no banco.

    Não apaga o outro ambiente: quem grava a produção continua com a
    homologação para testar, e vice-versa.

    **O PADRÃO SAI DA TABELA DA CENTRAL** (`None` → `_ambiente`), e não de um
    `HOMOLOGACAO` escrito na assinatura — mudado em 14/10/2026: com ele, a
    CRA e a CENPROT gravariam na gaveta de homologação quando ninguém
    dissesse o ambiente. Para as outras Centrais o resultado é o mesmo de
    antes, porque o primeiro da tabela delas é o mesmo.
    """
    qual = _central(central)
    onde = _ambiente(ambiente, qual)
    if FORMA_DA_CENTRAL[qual] == TOKEN:
        # **QUEM GUARDA TOKEN NÃO GUARDA PAR.** Deixar passar faria o arquivo
        # dizer que tem usuário e senha, e `token_guardado` devolveria vazio
        # sem erro nenhum — o segredo estaria lá e o sistema não o acharia.
        raise CredencialError(
            f"A {NOME_DA_CENTRAL[qual]} não usa usuário e senha: ela usa um "
            f"token. Use «gravar_token».")
    u, s = (usuario or "").strip(), (senha or "").strip()
    if not u or not s:
        raise CredencialError("Informe o usuário e a senha.")
    if qual == CENPROT:
        _conferir_senha_da_cenprot(s)

    destino = caminho(qual, pasta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    # LÊ O QUE JÁ ESTÁ LÁ ANTES DE ESCREVER — gravar a produção não pode apagar
    # a homologação, senão o dia da virada vira o dia em que se perde o teste.
    guardado: dict[str, Any] = {}
    if destino.is_file():
        try:
            guardado = json.loads(destino.read_text(encoding=CODIFICACAO_DO_ARQUIVO)) or {}
        except (OSError, ValueError):
            guardado = {}
    guardado[onde] = {"usuario": u, "senha": s}
    destino.write_text(json.dumps(guardado, ensure_ascii=False),
                       encoding="utf-8")
    return destino


def tem(central: Any, ambiente: Any = None, pasta: Any = None) -> bool:
    """Aquela credencial existe? **Não devolve a senha** — é o que a tela usa.

    A tela precisa saber se já foi informada, e não qual é. Devolver o segredo
    para desenhar um «✓» seria pô-lo no HTML.
    """
    caminho_ = caminho(central, pasta)
    if not caminho_.is_file():
        return False
    try:
        guardado = json.loads(caminho_.read_text(encoding=CODIFICACAO_DO_ARQUIVO)) or {}
    except (OSError, ValueError):
        return False
    guardado_do_ambiente = guardado.get(_ambiente(ambiente, central)) or {}
    if FORMA_DA_CENTRAL[_central(central)] == TOKEN:
        return bool(str(guardado_do_ambiente.get("token") or "").strip())
    return bool(str(guardado_do_ambiente.get("usuario") or "").strip()
                and str(guardado_do_ambiente.get("senha") or "").strip())


def usuario(central: Any, ambiente: Any = None,
            pasta: Any = None) -> str:
    """Só o usuário, para a tela mostrar quem está configurado. Sem a senha."""
    caminho_ = caminho(central, pasta)
    if not caminho_.is_file():
        return ""
    try:
        guardado = json.loads(caminho_.read_text(encoding=CODIFICACAO_DO_ARQUIVO)) or {}
    except (OSError, ValueError):
        return ""
    return str((guardado.get(_ambiente(ambiente, central)) or {}).get("usuario")
               or "")


def credencial(central: Any, ambiente: Any = None,
               pasta: Any = None) -> tuple[str, str]:
    """O par em claro. **É o único lugar do sistema que devolve a senha.**

    Quem chama isto está prestes a autenticar contra a Central; qualquer outro
    uso é vazamento. É a mesma regra de `agente_provedores.credencial`.
    """
    qual = _central(central)
    onde = _ambiente(ambiente, qual)
    caminho_ = caminho(qual, pasta)
    if not caminho_.is_file() and qual in CENTRAIS_SO_EM_PRODUCAO \
            and onde == PRODUCAO:
        raise CredencialError(_falta_a_de_producao(qual, {}))
    if not caminho_.is_file():
        raise CredencialError(
            f"A credencial da {NOME_DA_CENTRAL[qual]} ainda não foi "
            f"informada. Ela é gravada em «{caminho_}», fora do banco, e se "
            f"informa em Administrativo → Configurações, na seção "
            f"«Centrais — credenciais das APIs».")
    try:
        guardado = json.loads(caminho_.read_text(encoding=CODIFICACAO_DO_ARQUIVO)) or {}
    except (OSError, ValueError) as erro:
        raise CredencialError(
            f"Não consegui ler «{caminho_}»: {erro}. Informe a credencial de "
            f"novo na tela de configurações.") from erro
    par = guardado.get(onde) or {}
    u, s = str(par.get("usuario") or ""), str(par.get("senha") or "")
    if not (u and s):
        if qual in CENTRAIS_SO_EM_PRODUCAO and onde == PRODUCAO:
            raise CredencialError(_falta_a_de_producao(qual, guardado))
        outro = PRODUCAO if onde == HOMOLOGACAO else HOMOLOGACAO
        tem_outro = bool((guardado.get(outro) or {}).get("usuario"))
        extra = (f" A de {outro.lower()} está informada — confira se o "
                 f"ambiente escolhido é o certo." if tem_outro else "")
        raise CredencialError(
            f"A credencial da {NOME_DA_CENTRAL[qual]} para o ambiente "
            f"{onde.lower()} ainda não foi informada.{extra}")
    return u, s


def gravar_token(central: Any, *, token: str, ambiente: Any = None,
                 pasta: Any = None) -> Path:
    """Guarda o token daquela Central. ESCREVE EM DISCO, não no banco.

    **A ONRTDPJ não tem usuário e senha: tem um token**, gerado pelo próprio
    cartório na Central RTDPJBrasil, em *Serviços > Envio Extrato SINTER* — o
    mesmo token da API do SINTER, conforme a própria documentação dela declara.

    O `ambiente` vem em branco de propósito na chamada normal: quem tem um
    ambiente só não escolhe, e escolher errado aqui gravaria o token onde o
    sistema não vai procurá-lo.
    """
    qual = _central(central)
    if FORMA_DA_CENTRAL[qual] != TOKEN:
        raise CredencialError(
            f"A {NOME_DA_CENTRAL[qual]} usa usuário e senha, e não token. "
            f"Use «gravar».")
    onde = _ambiente(ambiente, qual)
    valor = (token or "").strip()
    if not valor:
        raise CredencialError("Informe o token da Central.")

    destino = caminho(qual, pasta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    guardado: dict[str, Any] = {}
    if destino.is_file():
        try:
            guardado = json.loads(destino.read_text(encoding=CODIFICACAO_DO_ARQUIVO)) or {}
        except (OSError, ValueError):
            guardado = {}
    guardado[onde] = {"token": valor}
    destino.write_text(json.dumps(guardado, ensure_ascii=False),
                       encoding="utf-8")
    return destino


def token_guardado(central: Any, ambiente: Any = None,
                   pasta: Any = None) -> str:
    """O token em claro. **É o único lugar do sistema que o devolve.**

    Quem chama isto está prestes a falar com a Central; qualquer outro uso é
    vazamento. É a mesma regra de `credencial` e de `agente_provedores`.
    """
    qual = _central(central)
    if FORMA_DA_CENTRAL[qual] != TOKEN:
        raise CredencialError(
            f"A {NOME_DA_CENTRAL[qual]} não guarda token. Use «credencial».")
    onde = _ambiente(ambiente, qual)
    caminho_ = caminho(qual, pasta)
    producao_do_protesto = (qual in CENTRAIS_SO_EM_PRODUCAO
                            and onde == PRODUCAO)
    if not caminho_.is_file() and producao_do_protesto:
        raise CredencialError(_falta_a_de_producao(qual, {}))
    if not caminho_.is_file():
        raise CredencialError(
            f"O token da {NOME_DA_CENTRAL[qual]} ainda não foi informado. Ele "
            f"é gravado em «{caminho_}», fora do banco, e se informa em "
            f"Administrativo → Configurações. Para obtê-lo: "
            f"{ONDE_SE_OBTEM_O_TOKEN[qual]}")
    try:
        guardado = json.loads(caminho_.read_text(encoding=CODIFICACAO_DO_ARQUIVO)) or {}
    except (OSError, ValueError) as erro:
        raise CredencialError(
            f"Não consegui ler «{caminho_}»: {erro}. Informe o token de novo "
            f"na tela de configurações.") from erro
    valor = str((guardado.get(onde) or {}).get("token") or "").strip()
    if not valor and producao_do_protesto:
        raise CredencialError(_falta_a_de_producao(qual, guardado))
    if not valor:
        raise CredencialError(
            f"O token da {NOME_DA_CENTRAL[qual]} ainda não foi informado.")
    return valor


def apagar(central: Any, ambiente: Any = None, pasta: Any = None) -> bool:
    """Tira aquela credencial do arquivo. Devolve se havia o que tirar.

    Existe porque credencial trocada pela Central tem de sair daqui: senha
    velha guardada é senha que alguém tenta e toma 401 sem entender.
    """
    caminho_ = caminho(central, pasta)
    if not caminho_.is_file():
        return False
    try:
        guardado = json.loads(caminho_.read_text(encoding=CODIFICACAO_DO_ARQUIVO)) or {}
    except (OSError, ValueError):
        return False
    if _ambiente(ambiente, central) not in guardado:
        return False
    guardado.pop(_ambiente(ambiente, central))
    caminho_.write_text(json.dumps(guardado, ensure_ascii=False),
                        encoding="utf-8")
    return True


def situacao(pasta: Any = None) -> list[dict]:
    """O que a tela de configurações mostra: quem está informado, sem segredo.

    **Nunca devolve senha** — nem mascarada. Senha mascarada no HTML continua
    dizendo o tamanho dela.
    """
    fora = []
    # **A LISTA SAI DA TABELA, E NAO DA MAO.** Ela era escrita a mao com as
    # duas de Protesto e os dois ambientes; assim a terceira nasceria fora da
    # tela sem ninguem ver, e a ONRTDPJ apareceria com um ambiente de
    # homologacao que nao existe. E a licao do menu, dentro do modulo — e por
    # causa dela o ONR, quinta Central, apareceu na tela sozinho.
    for qual in ARQUIVO_DA_CENTRAL:
        for onde in ambientes_de(qual):
            fora.append({
                "central": qual,
                "nome": NOME_DA_CENTRAL[qual],
                "ambiente": onde,
                "forma": FORMA_DA_CENTRAL[qual],
                "informada": tem(qual, onde, pasta),
                # TOKEN NAO TEM USUARIO, e devolver vazio aqui e o certo: a
                # tela mostra «informado» ou «falta», e nunca o segredo.
                "usuario": ("" if FORMA_DA_CENTRAL[qual] == TOKEN
                            else usuario(qual, onde, pasta)),
                # COMO AQUELA CENTRAL CHAMA AS DUAS METADES DO PAR. A tela
                # escrevia «usuário» e «senha» para todas, e no ONR o par é
                # `client_id` + `client secret`.
                "rotulos": rotulos_do_par(qual),
                # O QUE FICOU GUARDADO E NÃO SE USA MAIS (14/10/2026) — só as
                # três do Protesto, e só o nome do ambiente, nunca o segredo.
                # Sem esta marca, quem cadastrou a de homologação e não vê
                # mais a linha dela concluiria que o sistema a perdeu.
                "fora_de_uso": fora_de_uso(qual, pasta),
            })
    return fora
