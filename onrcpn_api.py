"""
O TRANSPORTE DO e-PROCLAMAS — a API do ON-RCPN, Registro Civil.

    «tem api no rcpn também» / «pesquise se ela não foi ampliada para mais
    atos» / «vamos seguir o cronograma recomendado» — o oficial, 03/09/2026

**ISTO FECHA UM BURACO QUE O PRÓPRIO SISTEMA DECLARAVA.** Desde 28/08/2026 o
`hc_schema` diz, no comentário das colunas `eproclamas_protocolo` e
`eproclamas_em`: *«O envio à Central é integração que este sistema ainda não
tem. Até tê-la, o escrevente publica no e-Proclamas e anota aqui o
protocolo.»* Era verdade, e a API existe desde **10/04/2025**.

O CONTRATO, MEDIDO EM 03/09/2026
    Swagger **2.0** · «API e-PROCLAMAS 1.0.0» ·
    `host: servicosh.registrocivil.org.br` · `basePath: /` ·
    `schemes: ["https"]` · **3 caminhos**.

    Guardado em `FONTES_EXTERNAS/onrcpn/proclama_swagger.json`, que fica fora
    de `SERVIDOR/INSTALAR_CARTORIO_GESTAO` e **não viaja no `.cgu`**. Os testes
    **abrem esse arquivo e comparam** — a lição da CENPROT, em que seis
    defeitos meus só apareceram quando o teste abriu o `swagger.yaml`.

    O contrato vem **embutido** na página do Swagger UI, no campo
    `"swaggerDoc"` do `swagger-ui-init.js`; não há um `.json` servido à parte.

**ELA ESTÁ NO AR, E ISSO FOI CONFERIDO E NÃO SUPOSTO.**
`GET /api/proclama/health` respondeu **HTTP 200** com o corpo
`Conexão com Oracle realizada com sucesso`, em 03/09/2026, **sem cabeçalho de
autenticação nenhum**. É por isso que `esta_no_ar()` não pede token: medido, e
não deduzido do fato de o contrato não declarar `security`.

O e-PROCLAMAS E O LIVRO D SÃO DOIS BOOLEANOS DO MESMO ENVIO
    `publicacao` publica o edital; `livro_eletronico` gera o **Livro D
    Eletrônico**. **Uma chamada faz as duas coisas** — e é isso que responde à
    pergunta do oficial sobre a ampliação, pelo lado desta API.

A AUTENTICAÇÃO É O TOKEN IdRC, E ELE **VAI COM `Bearer`**
    **E o próprio contrato diz, no campo, e não só na nota.** O parâmetro
    `authorization` traz, na `description`, duas coisas (medido em
    18/09/2026):

        «Token obtido via IDRC, conforme nota. Utilizar padrão **Bearer**
        <i>Token</i>.»

    Ou seja: **o prefixo deixou de ser derivado** — esta casa olhava o `type:
    string` do cabeçalho, não achava o formato ali e o deduzia da nota, sem
    ver que ele estava escrito na `description`, na linha ao lado. E a mesma
    `description` nomeia a origem do token: **é o IdRC**.

    A nota do contrato diz o resto: *«a autenticação da nova API e-Proclamas
    (...) utilizará o mesmo modelo de autenticação adotado no projeto das
    certidões»* — e o contrato das certidões declara
    `BearerAuth: {type: http, scheme: bearer, bearerFormat: JWT}`, o que
    confirma o mesmo formato por um segundo caminho.

    > **AS FONTES CONCORDAM, E AGORA SÃO TRÊS** — o campo, a nota e o contrato
    > da certidão. Continua não havendo uma chamada real desta serventia para
    > conferir; se a Central recusar com 401 tendo token válido, **é aqui que
    > se olha primeiro**, e `PREFIXO_DO_TOKEN` é uma linha só.

    > **E ELE É O CONTRÁRIO DA ONRTDPJ, que é a armadilha.** Lá o contrato
    > declara `apiKey` e o token vai **cru**, sem a palavra; aqui vai com ela.
    > Duas Centrais, dois cabeçalhos `Authorization`, dois formatos — copiar um
    > para o outro por hábito produz um 401 que não diz por quê.

    **O TOKEN SERVE ÀS DUAS APIs do ON-RCPN**, diz a mesma nota: *«sem
    necessidade de criação de um novo token ou credencial»*. Por isso ele mora
    numa credencial só, `onrcpn.cred`, e não numa por API.

O QUE SE FECHOU EM 18/09/2026, E O QUE FICOU ABERTO
    **1. O `/api/auth` — FECHADO, e ele não existe.** Não é caminho de API
    nenhuma: é o **IdRC**, o Keycloak do Registro Civil, com
    `authorization_endpoint` e `token_endpoint` próprios. O manual que os dois
    contratos apontavam chegou, e está na casa
    (`FONTES_EXTERNAS/onrcpn/manual_idrc_homologacao_certidao.txt`). O 404 nos
    dois endereços da API sempre disse isso — faltava o documento.

    **E ele trouxe a notícia que muda o desenho deste módulo.** O token que a
    API consome é o **do usuário**, com vida de **5 minutos**, e sai de um
    `authorization_code` — login de gente, com URL de redirecionamento. **Não
    é o par virando token sozinho.** Este módulo **continua não pedindo token a
    ninguém**: usa o que o oficial gravou. O que se sabe agora é que o gravado
    **vence**, e que renovar depende de alguém autenticar — a menos que o
    `client_credentials` que o reino declara seja aceito pelas APIs, e isso
    ainda não se mediu (item 4).

    **E O LOGIN DE GENTE É CONSTRUÍVEL AQUI, porque o manual admite retorno
    local** — palavras dele: «para ambientes de teste local e sistemas Desktop
    informe uma URL `localhost` com porta definida e path específico», exemplo
    `http://localhost:8081/rpc-portal/callback`. Este sistema atende na
    **8765** (`installer\reiniciar_servidor.ps1`), então o navegador desta
    própria máquina serve de cliente: renovar o token que vence não depende de
    servidor público. **O que falta é construir a tela do retorno; o que falta
    medir é o item 4** — e as duas coisas são diferentes.

    **E O FORMULÁRIO DO CADASTRO FOI MEDIDO CAMPO A CAMPO** (18/09/2026, no
    código do próprio portal do IdRC — **cujo nome de arquivo não se cita: ele
    tem hash de build no nome, e o hash muda**; a prova está em `centrais_cred`):
    são **dez** campos, e a lista fechada está em
    `DOCUMENTACAO/PEDIDO_DAS_CREDENCIAIS.md`. Dois deles importam aqui: o
    `ambiente` só aceita `homologacao` e `producao`, **sem acento**, e o
    `protocoloHomologacao` só é exigido em `producao` — a regra, literal:
    `ambiente !== "producao" || protocoloHomologacao`.

    **2. O endereço de PRODUÇÃO — FECHADO, e o `BASE` daqui não mudou.**
    Medido em 18/09/2026: `servicos.` responde, com o **mesmo** `health` de
    `servicosh.`. Esta constante continua a de homologação por outra razão —
    a que sobreviveu, e que é a ordem que o cadastro exige. Ver
    `centrais_cred.AMBIENTES_DA_CENTRAL`.

    **3. Quais campos são obrigatórios.** O contrato **não declara `required`
    em parâmetro nenhum** — nem no cabeçalho, nem no corpo. É a mesma situação
    dos `/v2` da CENPROT e do contrato da ONRTDPJ, pela terceira vez: **não se
    inventa obrigação que o contrato não declara.** O que este módulo recusa é
    a chamada que **não pode funcionar** — lote vazio, matrícula em branco —, e
    o código diz que isso é regra da casa.

    **4. O `client_credentials` do IdRC gera token aceito pelas APIs do
    ON-RCPN?** O reino declara esse `grant_type` entre os suportados (medido
    no `openid-configuration` dos dois hosts), e o manual só descreve o fluxo
    de usuário. **É a pergunta que decide se o sistema mina o token sozinho
    para sempre ou depende de alguém autenticar de tempo em tempo** — e é a
    primeira a fazer. Enquanto ela não se responder, este módulo não tenta
    renovar nada.

**MAS O VOCABULÁRIO SE CONFERE, E ISSO NÃO É INVENTAR.** Uma coisa é exigir
que um campo venha preenchido (o contrato não exige); outra é conferir que,
**vindo preenchido**, ele traga um dos valores que o contrato lista. A nota do
contrato enumera: sexo, estado civil, tipo de casamento. Mandar `SOLTEIRO(A)`
onde a Central espera `SOLTEIRO` é o defeito calado — ela aceita o lote e o
proclama sai errado.

ESTE MÓDULO NÃO LAVRA ATO, PELA QUINTA VEZ
    Depois do usucapião, das fraudes, do CNIB e da CENPROT. Ele **comunica o
    que a serventia já decidiu e lavrou**: o edital desta habilitação, com a
    matrícula deste assento do Livro D. Quem publica o edital e quem lança no
    livro é o RCPN — há teste que varre os nomes públicos.
"""
from __future__ import annotations

import http.client

import centrais_trava_sandbox as TRAVA
import json
import ssl
import time
import urllib.parse
from typing import Any

import centrais_cred as CRED

# O ENDEREÇO, MEDIDO NO CONTRATO — `host` + `basePath: /` + `schemes: [https]`.
#
# **É O DE HOMOLOGAÇÃO, E ISSO DEIXOU DE SER «PORQUE SÓ ELE ESTÁ PUBLICADO».**
# Medido em 18/09/2026: os dois hosts existem e respondem, com o mesmo `health`.
# O que segura esta linha em homologação é a **ordem que o próprio cadastro
# exige** — o formulário pede o protocolo do client de homologação para criar o
# de produção. Ver `centrais_cred.AMBIENTES_DA_CENTRAL`.
BASE = "https://servicosh.registrocivil.org.br"

CONTRATO_NO_PROJETO = "FONTES_EXTERNAS/onrcpn/proclama_swagger.json"
CONTRATO_DA_CERTIDAO = "FONTES_EXTERNAS/onrcpn/certidao_swagger.json"

# O CABEÇALHO E O PREFIXO. Ver a seção da autenticação no cabeçalho.
#
# **O prefixo agora é MEDIDO NO CAMPO.** A `description` do parâmetro
# `authorization` diz «Utilizar padrão Bearer <i>Token</i>» — medido em
# 18/09/2026. Antes disto esta casa o deduzia da nota do contrato: ficou o
# mesmo, e agora com a fonte citada. É a primeira coisa a conferir se a Central
# responder 401 com token válido.
CABECALHO_DO_TOKEN = "Authorization"
PREFIXO_DO_TOKEN = "Bearer "

PRAZO_PADRAO = 60       # segundos — o `enviar` é um LOTE, e não um registro
TENTATIVAS_DE_REDE = 2

# OS TRÊS CAMINHOS, copiados do contrato um a um. O teste abre o arquivo e
# confere que os três existem lá, com o método certo.
#
#   **O `recibo` usa `:matricula`, e não `{matricula}`.** O contrato foi escrito
#   no estilo do Express, e a diferença não é cosmética: quem trocasse a marca
#   pela chaveta faria o teste deixar de achar o caminho no contrato.
CAMINHO: dict[str, str] = {
    "health": "/api/proclama/health",
    "enviar": "/api/proclama/enviar",
    "recibo": "/api/proclama/recibo/:matricula",
}

METODO_DO_CAMINHO: dict[str, str] = {
    "health": "GET", "enviar": "POST", "recibo": "GET",
}

# O CORPO DE `/api/proclama/enviar`, na grafia do contrato — **minúscula com
# sublinhado**, ao contrário da ONRTDPJ, que usa maiúscula inicial.
#
#   JSON é sensível a caixa e a Central ignora o que não conhece: mandar
#   `Matricula` em vez de `matricula` faria o proclama subir **sem matrícula**,
#   com HTTP 200 e nada acontecendo do lado de lá.
CAMPOS_DO_LOTE: tuple[str, ...] = ("cns", "proclamas")

CAMPOS_DO_PROCLAMA: tuple[str, ...] = (
    "matricula", "publicacao", "livro_eletronico", "data_proclamas",
    "tipo_casamento", "cpf_fatura", "nome_fatura", "conjuge_1", "conjuge_2")

CAMPOS_DO_CONJUGE: tuple[str, ...] = (
    "cpf", "nome", "novo_nome", "sexo", "data_nascimento", "estado_civil",
    "ocupacao", "naturalidade_estrangeiro", "ibge_municipio_naturalidade",
    "descricao_naturalidade_estrangeiro", "pais_nascimento", "nacionalidade",
    "domicilio_estrangeiro", "endereco_residencia",
    "descricao_domicilio_estrangeiro", "filiacao")

CAMPOS_DO_ENDERECO: tuple[str, ...] = (
    "cep", "logradouro", "numero", "complemento", "bairro", "ibge_municipio")

CAMPOS_DA_FILIACAO: tuple[str, ...] = ("nome_genitor", "sexo_genitor")

# ---------------------------------------------------------- O QUE VOLTA
#
# **HTTP 200 NÃO QUER DIZER QUE O PROCLAMA SUBIU**, e este foi o defeito mais
# grave desta integração — achado pelo teste que abriu o contrato, depois de eu
# ter escrito o módulo inteiro achando que a resposta não era declarada.
#
#   Eu havia medido o contrato imprimindo só a `description` de cada resposta,
#   li «OK», e **concluí que não havia esquema**. Escrevi isso em três lugares e
#   fiz o código tratar todo 200 como sucesso. **O esquema está declarado**, e
#   diz o contrário:
#
#       200 → {status, message, proclamas: {batchId, success: [...], error: [...]}}
#
#   **São duas listas, por matrícula.** O lote pode voltar aceito pela metade —
#   com 200 —, e cada recusado traz `message`, `details` e uma lista `errors`
#   com `field` e a frase da Central. Tratar isso como sucesso faria a casa
#   dizer ao casal que o edital foi publicado quando ele não foi: **o defeito
#   calado, na sua forma mais cara.**
#
#   O exemplo do próprio contrato mostra que espécie de erro é: *«O campo sexo
#   do genitor cônjuge 2 se encontra inválido. Informar masculino ou feminino.
#   Foi informado M»* — exatamente o que `sexo_para_a_central` converte.
CAMPO_DO_LOTE = "proclamas"
CAMPO_DOS_ACEITOS = "success"
CAMPO_DOS_RECUSADOS = "error"
CAMPO_DO_NUMERO_DO_LOTE = "batchId"

# **E NÃO HÁ CAMPO `protocolo` EM LUGAR NENHUM DA RESPOSTA.** O que a Central
# devolve para identificar o envio é o `batchId` — o número do LOTE, e não um
# protocolo por proclama. Chamá-lo de protocolo seria batizar o que não se
# mediu; o que a casa guarda é o número do lote, e a tela diz que é isso.
CAMPO_DO_RECIBO = "recibo"

# O VOCABULÁRIO, literal da nota do contrato. Ver o cabeçalho: conferir o
# valor não é inventar obrigação — é ler o que está escrito.
SEXOS: tuple[str, ...] = ("masculino", "feminino")
ESTADOS_CIVIS: tuple[str, ...] = (
    "IGNORADO", "SOLTEIRO", "VIUVO", "DIVORCIADO", "SEPARADO", "OUTROS")
TIPOS_DE_CASAMENTO: tuple[str, ...] = (
    "civil", "religioso", "conversao", "afixacao")

# BRASIL NA LISTA M49 DA ONU, que é a que o contrato manda usar para país e
# nacionalidade. **Três dígitos, com o zero à frente** — `76` seria outro país.
BRASIL_M49 = "076"

# **O CPF VAI SEM PONTUAÇÃO E O CEP VAI COM HÍFEN, NA MESMA MENSAGEM.** Está
# escrito assim na nota do contrato, com exemplo de cada um: `22105769039` e
# `01227-200`. É o tipo de detalhe que, escrito de memória, sai errado num dos
# dois — e o errado não estoura: chega torto do lado de lá.
DIGITOS_DO_CPF = 11
DIGITOS_DO_CEP = 8
DIGITOS_DO_IBGE = 7


class OnrcpnError(RuntimeError):
    """Falha de transporte ou de credencial, com a frase para o balcão."""


class OnrcpnRecusou(OnrcpnError):
    """A Central respondeu, e respondeu não. O motivo dela vem junto."""


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _so_digitos(v: Any) -> str:
    return "".join(c for c in _texto(v) if c.isdigit())


# ------------------------------------------------------- as convenções dela


def cpf_para_a_central(valor: Any, de_quem: str = "") -> str:
    """O CPF como a Central o quer: **só dígitos**, sem ponto e sem traço."""
    d = _so_digitos(valor)
    if not d:
        return ""
    if len(d) != DIGITOS_DO_CPF:
        raise OnrcpnError(
            f"O CPF{' de ' + de_quem if de_quem else ''} tem {len(d)} dígitos "
            f"e o CPF tem {DIGITOS_DO_CPF}: «{_texto(valor)}».")
    return d


def cep_para_a_central(valor: Any) -> str:
    """O CEP como a Central o quer: **`xxxxx-xxx`, com o hífen**."""
    d = _so_digitos(valor)
    if not d:
        return ""
    if len(d) != DIGITOS_DO_CEP:
        raise OnrcpnError(
            f"O CEP tem {len(d)} dígitos e o CEP tem {DIGITOS_DO_CEP}: "
            f"«{_texto(valor)}».")
    return f"{d[:5]}-{d[5:]}"


def ibge_para_a_central(valor: Any, o_que: str = "o município") -> str:
    """O município como a Central o quer: **os 7 dígitos do IBGE**.

    É o mesmo código de `ib_municipios`, a tabela de 5.570 que a remessa do
    IBGE desta casa já usa — e o mesmo que o CENPROT lê no cabeçalho.
    """
    d = _so_digitos(valor)
    if not d:
        return ""
    if len(d) != DIGITOS_DO_IBGE:
        raise OnrcpnError(
            f"O código do IBGE de {o_que} tem {DIGITOS_DO_IBGE} dígitos, e "
            f"veio «{_texto(valor)}» com {len(d)}.")
    return d


def data_para_a_central(valor: Any) -> str:
    """A data como a Central a quer: **`dd/mm/aaaa`**.

    Aceita o `aaaa-mm-dd` do banco — que é como toda data mora aqui — e o
    `dd/mm/aaaa` já escrito, para a função poder ser chamada duas vezes sem
    estragar o valor.
    """
    v = _texto(valor)
    if not v:
        return ""
    v = v[:10]
    if len(v) == 10 and v[4] == "-" and v[7] == "-":
        return f"{v[8:10]}/{v[5:7]}/{v[0:4]}"
    if len(v) == 10 and v[2] == "/" and v[5] == "/":
        return v
    raise OnrcpnError(
        f"Não sei ler a data «{_texto(valor)}». A Central quer dd/mm/aaaa.")


def _do_vocabulario(valor: Any, aceitos: tuple[str, ...], o_que: str) -> str:
    """Confere contra a lista do contrato. **Vazio passa**, e isso é regra.

    O contrato não declara campo obrigatório nenhum; exigir presença aqui seria
    inventar obrigação. O que se confere é o VALOR de quem veio preenchido —
    porque a Central aceita o lote e escreve errado.
    """
    v = _texto(valor)
    if not v:
        return ""
    if v not in aceitos:
        raise OnrcpnError(
            f"A Central só aceita {', '.join(aceitos)} {o_que}, e veio "
            f"«{v}».")
    return v


def sexo_para_a_central(valor: Any) -> str:
    """`masculino` ou `feminino` — minúsculas, como o contrato escreve.

    O sistema guarda `M`/`F` e `MASCULINO`/`FEMININO` conforme a tela; as três
    formas entram, e o que sai é a do contrato.
    """
    v = _texto(valor).upper()
    if not v:
        return ""
    if v in ("M", "MASCULINO"):
        return "masculino"
    if v in ("F", "FEMININO"):
        return "feminino"
    raise OnrcpnError(
        f"A Central só aceita masculino ou feminino, e veio «{_texto(valor)}».")


def estado_civil_para_a_central(valor: Any) -> str:
    """Um dos seis do contrato, em MAIÚSCULAS.

    **`SOLTEIRO(A)` não passa, e é justamente o que o balcão digita.** A tela
    do civil escreve o gênero entre parênteses; a Central quer a palavra seca.
    """
    v = _texto(valor).upper().replace("(A)", "").replace("(O)", "").strip()
    trocas = {"VIÚVO": "VIUVO", "VIÚVA": "VIUVO", "VIUVA": "VIUVO",
              "SOLTEIRA": "SOLTEIRO", "DIVORCIADA": "DIVORCIADO",
              "SEPARADA": "SEPARADO", "OUTRO": "OUTROS", "": ""}
    v = trocas.get(v, v)
    return _do_vocabulario(v, ESTADOS_CIVIS, "no estado civil")


def tipo_de_casamento_para_a_central(valor: Any) -> str:
    """`civil`, `religioso`, `conversao` ou `afixacao`.

    O sistema guarda `CIVIL`, `RELIGIOSO` e `CONVERSAO` em
    `hc_habilitacoes.tipo`; a Central quer minúsculas e sem acento.
    """
    v = _texto(valor).lower()
    trocas = {"conversão": "conversao", "afixação": "afixacao",
              "uniao_estavel": "conversao", "união estável": "conversao"}
    v = trocas.get(v, v)
    return _do_vocabulario(v, TIPOS_DE_CASAMENTO, "no tipo de casamento")


# ------------------------------------------------------------- a credencial


def token(*, pasta=None) -> str:
    """O token IdRC do cartório, lido do disco. Só LÊ.

    **Lido a cada chamada, e não guardado na memória** — a mesma regra da
    ONRTDPJ: token trocado tem de valer sem reiniciar o servidor, porque quem
    o trocou foi à Central justamente porque o antigo parou.
    """
    return CRED.token_guardado(CRED.ONRCPN, pasta=pasta)


def tem_credencial(*, pasta=None) -> bool:
    """A tela pergunta isto antes de oferecer botão. **Não devolve o token.**"""
    return CRED.tem(CRED.ONRCPN, CRED.ambientes_de(CRED.ONRCPN)[0], pasta)


# ------------------------------------------------------------- o transporte


def partes(base: str) -> tuple[str, int, str]:
    """Parte o endereço, **forçando https**. Serve as DUAS APIs do ON-RCPN.

    **É PÚBLICA DE PROPÓSITO, e a razão é o que ela guarda.** A Central tem
    dois endereços — `servicosh` (e-Proclamas) e `certidaoh` (Certidão
    Eletrônica) — e um token só para os dois. Uma segunda cópia desta função
    em `onrcpn_certidao_api` divergiria no primeiro conserto, e o que
    divergiria é **a linha que impede o token de viajar em texto puro**.
    """
    p = urllib.parse.urlsplit(base)
    if p.scheme != "https":
        # **HTTPS NÃO É OPCIONAL.** O token viaja nesta conexão, e com ele
        # alguém publica edital de casamento em nome desta serventia.
        raise OnrcpnError(
            f"A base do ON-RCPN tem de ser https, e veio «{base}».")
    return p.hostname or "", p.port or 443, (p.path or "").rstrip("/")


def bater(metodo: str, caminho: str, *, corpo: bytes | None = None,
          com_token: bool = True, prazo: int = PRAZO_PADRAO,
          base: str | None = None, tipo: str = "application/json",
          pasta=None) -> dict:
    """Uma requisição. Devolve `{status, json, texto}` — nunca estoura por 4xx.

    **Quem decide o que fazer com um 4xx é quem chamou**, e não este módulo.

    **`base` EXISTE PORQUE A CENTRAL TEM DOIS ENDEREÇOS E UM TOKEN SÓ.** O
    e-Proclamas mora em `servicosh` e a Certidão Eletrônica em `certidaoh`; o
    token do IdRC serve às duas — está escrito na nota do contrato. O que **não
    pode divergir** entre elas são duas regras, e as duas moram aqui:

      * o **https forçado**, em `partes`;
      * o **«só GET se repete»** — um `POST` que a Central pode ter recebido
        não se manda de novo sozinho.

    Escrever isto duas vezes daria duas versões da linha que decide se um
    pedido de certidão sobe em duplicata.
    """
    hospedeiro, porta, prefixo = partes(base or BASE)
    # Trava sandbox: ON-RCPN so no simulador :8915 (ou recusa).
    hospedeiro, porta = TRAVA.destino_seguro(hospedeiro, porta)
    cabecas: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "CartorioGestao",
    }
    if com_token:
        cabecas[CABECALHO_DO_TOKEN] = PREFIXO_DO_TOKEN + token(pasta=pasta)
    if corpo is not None:
        cabecas["Content-Type"] = tipo

    contexto = ssl.create_default_context()
    ultimo = None
    for tentativa in range(TENTATIVAS_DE_REDE + 1):
        conexao = None
        try:
            conexao = http.client.HTTPSConnection(
                hospedeiro, porta, timeout=prazo, context=contexto)
            conexao.request(metodo, prefixo + caminho, body=corpo,
                            headers=cabecas)
            r = conexao.getresponse()
            texto = r.read().decode("utf-8", errors="replace")
            try:
                como_json = json.loads(texto) if texto.strip() else None
            except ValueError:
                como_json = None
            return {"status": r.status, "json": como_json, "texto": texto}
        except (OSError, ssl.SSLError, http.client.HTTPException) as erro:
            ultimo = erro
            # **RETENTAR SÓ O QUE NÃO CHEGOU.** Um `POST` que a Central pode
            # ter recebido não se repete sozinho: publicar o mesmo edital duas
            # vezes é uma publicação a mais, cobrada, que ninguém pediu.
            if metodo != "GET" or tentativa >= TENTATIVAS_DE_REDE:
                break
            time.sleep(1 + tentativa)
        finally:
            if conexao is not None:
                conexao.close()
    raise OnrcpnError(
        f"Não consegui falar com o e-Proclamas em {hospedeiro}: {ultimo}. "
        f"Confira a internet da serventia e tente de novo; nada foi enviado.")


def _detalhe(r: dict) -> str:
    """A frase da Central, se ela mandou uma."""
    corpo = r.get("json")
    if isinstance(corpo, dict):
        for chave in ("message", "mensagem", "erro", "error", "detail",
                      "errors"):
            valor = corpo.get(chave)
            if valor:
                return _texto(valor if isinstance(valor, str)
                              else json.dumps(valor, ensure_ascii=False))[:400]
    return ""


def _resposta_ou_erro(r: dict, o_que: str) -> Any:
    """Traduz o código da Central numa resposta ou numa frase de balcão."""
    if r["status"] in (200, 201):
        return r["json"] if r["json"] is not None else r["texto"]
    if r["status"] in (401, 403):
        raise OnrcpnError(
            f"O e-Proclamas recusou o token ao {o_que}. O token IdRC pode ter "
            f"expirado ou sido trocado: informe-o de novo em Administrativo → "
            f"Configurações, na seção «Centrais — credenciais das APIs».")
    if r["status"] == 422:
        # **422 É A RECUSA QUE DIZ O QUE ESTÁ ERRADO**, e é a que mais aparece
        # numa integração nova. O corpo dela vai inteiro para a tela: resumir
        # aqui esconderia justamente o campo que o escrevente precisa corrigir.
        raise OnrcpnRecusou(
            f"O e-Proclamas recusou os dados ao {o_que}: "
            f"{_detalhe(r) or r['texto'][:400]}")
    if r["status"] == 404:
        raise OnrcpnRecusou(
            f"O e-Proclamas não encontrou o que se pediu ao {o_que}.")
    detalhe = _detalhe(r)
    raise OnrcpnRecusou(
        f"O e-Proclamas respondeu {r['status']} ao {o_que}"
        + (f": {detalhe}" if detalhe
           else f". Resposta: {r['texto'][:300]}"))


# --------------------------------------------------------------- o que se LÊ


def esta_no_ar(*, pasta=None) -> dict:
    """O `health` da Central. **Não usa token — medido, e não suposto.**

    Em 03/09/2026 ele respondeu HTTP 200 com `Conexão com Oracle realizada com
    sucesso` a uma chamada **sem cabeçalho de autenticação**. Por isso ele
    serve de teste de ligação para uma casa que ainda não tem credencial: é a
    única coisa que se pode conferir antes do cadastro no IdRC.

    **E ele não afirma nada sobre a credencial**, justamente por não a usar —
    quem confunde as duas coisas conclui que o token está bom porque a Central
    respondeu.
    """
    r = bater("GET", CAMINHO["health"], com_token=False, prazo=20,
               pasta=pasta)
    return {"no_ar": r["status"] == 200,
            "status": r["status"],
            "resposta": _texto(r["texto"])[:200]}


def recibo(matricula: Any, *, pasta=None) -> dict:
    """O recibo do proclama. Devolve o que a Central mandou, sem interpretar.

    **O CONTRATO SE CONTRADIZ SOBRE O FORMATO, e isso fica dito em vez de
    resolvido por escolha.** A descrição do caminho diz «Gera recibo em pdf
    base64»; o esquema da resposta declara `recibo` como `string` com o exemplo
    `<<html string>>`. São duas afirmações do mesmo documento, e elas não
    combinam.

    Quem grava o arquivo é quem chamou, e é lá que se decide a extensão —
    **depois de olhar o que veio**. Escrever `.pdf` na fé da descrição faria a
    casa guardar um `.pdf` que é HTML, e o balcão descobriria ao tentar abrir.
    """
    m = _so_digitos(matricula)
    if not m:
        # REGRA DA CASA, e não do contrato: pedir recibo sem matrícula pede
        # sobre nada, e a viagem até lá custa mais que a recusa aqui.
        raise OnrcpnError(
            "Sem a matrícula não dá para pedir o recibo — ela é o que diz de "
            "qual proclama se está falando.")
    caminho = CAMINHO["recibo"].replace(":matricula", urllib.parse.quote(m))
    r = bater("GET", caminho, pasta=pasta)
    corpo = _resposta_ou_erro(r, "buscar o recibo do proclama")
    return corpo if isinstance(corpo, dict) else {"resposta": corpo}


# ------------------------------------------------------------ o que se MANDA


def conferir_proclama(p: dict) -> dict:
    """Um proclama na forma do contrato — **só os campos que ele declara**.

    Campo que a Central não conhece ela ignora em silêncio; campo nosso que
    vaze para o corpo não estoura nada e não faz nada. Por isso a montagem é
    por lista fechada, e não por `dict(p)`.
    """
    fora: dict[str, Any] = {}
    for campo in CAMPOS_DO_PROCLAMA:
        if campo in ("conjuge_1", "conjuge_2"):
            fora[campo] = _conjuge(p.get(campo) or {}, campo)
        elif campo in ("publicacao", "livro_eletronico"):
            fora[campo] = bool(p.get(campo))
        else:
            fora[campo] = _texto(p.get(campo))

    if not fora["matricula"]:
        # REGRA DA CASA. A matrícula é o que identifica o proclama na Central e
        # é por ela que o recibo se busca depois; sem ela, o envio sobe e o
        # recibo nunca mais é achado.
        raise OnrcpnError(
            "O proclama vai identificado pela matrícula de 32 dígitos do "
            "assento no Livro D, e ela veio em branco.")
    if not (fora["publicacao"] or fora["livro_eletronico"]):
        # **DOIS BOOLEANOS FALSOS SÃO UM ENVIO QUE NÃO FAZ NADA.** A Central
        # aceitaria; o escrevente sairia achando que publicou.
        raise OnrcpnError(
            "Marque ao menos uma coisa a fazer: publicar no e-Proclamas, "
            "gerar o Livro D Eletrônico, ou as duas.")
    fora["data_proclamas"] = data_para_a_central(fora["data_proclamas"])
    fora["tipo_casamento"] = tipo_de_casamento_para_a_central(
        fora["tipo_casamento"])
    fora["cpf_fatura"] = cpf_para_a_central(fora["cpf_fatura"],
                                            "quem paga a publicação")
    return fora


def _conjuge(c: dict, qual: str) -> dict:
    """Um cônjuge na forma do contrato, com as convenções aplicadas."""
    de_quem = ("o primeiro cônjuge" if qual.endswith("1")
               else "o segundo cônjuge")
    fora: dict[str, Any] = {}
    for campo in CAMPOS_DO_CONJUGE:
        if campo == "endereco_residencia":
            fora[campo] = _endereco(c.get(campo) or {})
        elif campo == "filiacao":
            fora[campo] = [_filiacao(f) for f in (c.get(campo) or [])]
        elif campo in ("naturalidade_estrangeiro", "domicilio_estrangeiro"):
            fora[campo] = bool(c.get(campo))
        else:
            fora[campo] = _texto(c.get(campo))

    fora["cpf"] = cpf_para_a_central(fora["cpf"], de_quem)
    fora["sexo"] = sexo_para_a_central(fora["sexo"])
    fora["data_nascimento"] = data_para_a_central(fora["data_nascimento"])
    fora["estado_civil"] = estado_civil_para_a_central(fora["estado_civil"])
    fora["ibge_municipio_naturalidade"] = ibge_para_a_central(
        fora["ibge_municipio_naturalidade"], "a naturalidade")
    return fora


def _endereco(e: dict) -> dict:
    fora = {campo: _texto(e.get(campo)) for campo in CAMPOS_DO_ENDERECO}
    fora["cep"] = cep_para_a_central(fora["cep"])
    fora["ibge_municipio"] = ibge_para_a_central(fora["ibge_municipio"],
                                                 "a residência")
    return fora


def _filiacao(f: dict) -> dict:
    fora = {campo: _texto(f.get(campo)) for campo in CAMPOS_DA_FILIACAO}
    fora["sexo_genitor"] = sexo_para_a_central(fora["sexo_genitor"])
    return fora


def enviar(cns: Any, proclamas: list[dict], *, pasta=None) -> dict:
    """Manda o lote ao e-Proclamas. **É a única função que publica.**

    `proclamas` já vem montado pelo domínio — este módulo não sabe o que é uma
    habilitação. Ele confere a forma contra o contrato, embrulha e manda.

    **NÃO SE MANDA LOTE VAZIO.** O contrato aceitaria, e a Central responderia
    200 sem publicar nada — o defeito calado, que é o pior. É regra da casa.
    """
    codigo = _so_digitos(cns)
    if not codigo:
        raise OnrcpnError(
            "O lote vai identificado pelo CNS da serventia, e ele veio vazio. "
            "Confira o cadastro em Administrativo → Serventia.")
    if not proclamas:
        raise OnrcpnError(
            "Não há proclama nenhum a enviar. Marque ao menos um.")

    corpo = {"cns": codigo,
             "proclamas": [conferir_proclama(p) for p in proclamas]}
    bruto = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    r = bater("POST", CAMINHO["enviar"], corpo=bruto, pasta=pasta)
    resposta = _resposta_ou_erro(r, "enviar os proclamas")
    lido = ler_o_lote(resposta)
    return {"enviados": len(corpo["proclamas"]),
            "corpo_enviado": corpo,
            "resposta": resposta,
            **lido}


def ler_o_lote(resposta: Any) -> dict:
    """Separa o que a Central ACEITOU do que ela RECUSOU. Só lê.

    **HTTP 200 NÃO QUER DIZER QUE O PROCLAMA SUBIU** — ver o bloco «O QUE
    VOLTA», acima. A resposta declara duas listas por matrícula, e o lote pode
    voltar aceito pela metade.

    Devolve `{lote, aceitos, recusados, entendi}`:

    - `aceitos` e `recusados` são listas de matrícula;
    - `recusados` traz, por matrícula, a frase da Central e a lista `errors`
      com `field` e `message` — que é o que o escrevente precisa para
      consertar o dado e mandar de novo;
    - **`entendi` é `False` quando a resposta não tem a forma declarada.**
      Nesse caso as duas listas vêm vazias, e quem chamou **não pode concluir
      que deu certo**: é a diferença entre «a Central recusou» e «eu não sei
      ler o que ela mandou», e tratá-las como a mesma coisa é o zero com cara
      de medição.
    """
    if not isinstance(resposta, dict):
        return {"lote": "", "aceitos": [], "recusados": [], "entendi": False}
    dentro = resposta.get(CAMPO_DO_LOTE)
    if not isinstance(dentro, dict):
        return {"lote": "", "aceitos": [], "recusados": [], "entendi": False}

    def matriculas(chave: str) -> list:
        lista = dentro.get(chave)
        return lista if isinstance(lista, list) else []

    aceitos = [_texto(i.get("matricula")) for i in matriculas(CAMPO_DOS_ACEITOS)
               if isinstance(i, dict)]
    recusados = []
    for item in matriculas(CAMPO_DOS_RECUSADOS):
        if not isinstance(item, dict):
            continue
        erros = item.get("errors")
        recusados.append({
            "matricula": _texto(item.get("matricula")),
            "message": _texto(item.get("message")),
            "details": _texto(item.get("details")),
            "errors": [{"field": _texto(e.get("field")),
                        "message": _texto(e.get("message"))}
                       for e in (erros if isinstance(erros, list) else [])
                       if isinstance(e, dict)],
        })
    return {"lote": _texto(dentro.get(CAMPO_DO_NUMERO_DO_LOTE)),
            "aceitos": aceitos, "recusados": recusados, "entendi": True}


def motivo_da_recusa(recusado: dict) -> str:
    """A recusa da Central em uma frase, para a tela. Só formata.

    A frase de fora (`message`) costuma ser genérica — «the procedure request
    failed» —, e **o que serve ao balcão é a lista `errors`**, que nomeia o
    campo. Mostrar só a de fora faria o escrevente reler o proclama inteiro
    procurando o que a Central já disse qual era.
    """
    partes = [p for p in (recusado.get("details"), recusado.get("message"))
              if _texto(p)]
    for erro in recusado.get("errors") or []:
        campo, frase = _texto(erro.get("field")), _texto(erro.get("message"))
        partes.append(f"{campo}: {frase}" if campo and frase else frase or campo)
    return " · ".join(p for p in partes if p)
