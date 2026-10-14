"""
O TRANSPORTE DA CENTRAL ONRTDPJ — a API Cartórios da RTDPJBrasil.

    «ou encaminhamento pela ONRTDPJ para os eletrônicos» — o oficial,
    03/09/2026

**E EU QUASE DECLAREI QUE NÃO HAVIA CONTRATO A MEDIR.** No mesmo dia, medindo o
acervo do E-Ofício, achei o que está registrado em `RCPJ_RTD_O_TITULO_MEDIDO.md`:
**zero** tabelas e **zero** colunas de RTDPJ ou de Central naquelas 229 tabelas —
o único ONR que existe lá é o do Registro de Imóveis. Aquela conclusão continua
verdadeira, e eu tirei dela a errada: escrevi que, sem precedente, escrever
endereço ou formato «seria inventar número».

**O E-Ofício não tinha o que ensinar; o mundo tinha.** O contrato da Central
está **público**, exatamente como o WSDL da CRA estava:

    https://centralinside.rtdbrasil.org.br/           a documentação (Swagger UI)
    https://centralinside.rtdbrasil.org.br/swagger/docs/v1   o contrato

É a lição deste projeto pela sexta vez, e desta vez pelo lado da fonte: **não
achar onde eu procurei não prova que não existe.** Guardado em
`FONTES_EXTERNAS/onrtdpj/swagger_v1.json`, e os testes **abrem esse arquivo e
comparam** — a lição da CENPROT, em que seis defeitos meus só apareceram quando
o teste abriu o `swagger.yaml`.

O QUE O CONTRATO DECLARA, MEDIDO EM 03/09/2026
    Swagger **2.0** · `host: centralinside.rtdbrasil.org.br` · `schemes: [https]`
    · sem `basePath` · **81 caminhos** e **100 definições**.

    **A AUTENTICAÇÃO É UM TOKEN NO CABEÇALHO**, e não usuário e senha:
    `securityDefinitions.Token` é `apiKey`, `in: header`, `name: Authorization`.
    A própria página diz de onde ele sai: *«O cartório deve utilizar o token
    gerado na própria Central RTDPJBrasil, no menu Serviços > Envio Extrato
    SINTER. O token é o mesmo utilizado nessa outra API do SINTER.»*

    > **E O NOME DESSE MENU CONFUNDE, porque o SINTER foi desligado.** A
    > Receita Federal comunicou em **24/08/2023** que desabilitou o recebimento
    > de informações pelo SINTER no formato de então, e que os cartórios não
    > devem mais enviar. **O que foi desligado é o ENVIO; o token continua
    > existindo naquele menu e continua servindo a esta API** — conferido pelo
    > oficial em 03/09/2026, que o encontrou lá.
    >
    > Fica escrito porque **quem souber da notícia e não desta distinção
    > concluiria que o token morreu junto** — e não iria procurá-lo.

    > **E O CONTRATO DECLARA O ESQUEMA SEM APLICÁ-LO A OPERAÇÃO NENHUMA.**
    > Medido: não há `security` no documento nem em nenhuma das 81 operações.
    > Logo **quais chamadas exigem o token não está no contrato** — está na
    > prosa. O módulo manda o cabeçalho em todas, que é o que a prosa diz; se
    > alguma não o quisesse, mandá-lo não estraga nada.

    **E NENHUM CORPO DECLARA CAMPO OBRIGATÓRIO**: `required` vem **vazio** nas
    cem definições. É a mesma situação dos `/v2` da CENPROT — e a resposta é a
    mesma: **não se inventa obrigação que o contrato não declara.** O que este
    módulo recusa é a chamada que não pode funcionar (pedido sem protocolo age
    sobre nada), e diz que é regra da casa, não do contrato.

    **HÁ UM AMBIENTE SÓ.** O contrato declara **um** host. Inventar um endereço
    de homologação seria o pior tipo de número inventado: quem o usasse acharia
    que está testando enquanto fala com a Central de verdade.

O QUE ESTE MÓDULO NÃO FAZ
    **Não lavra ato, não numera, não sela e não cobra** — pela quinta vez neste
    projeto, depois do usucapião, das fraudes, do CNIB e da CENPROT. Ele fala
    com a Central; quem registra é `rg_titulo`, na ficha do título, com o livro,
    a folha e a numeração da casa. Há teste que varre os nomes públicos.

    **E ele recebe `db`, e não `con`** — como `ato_selado.obter_selo` e
    `cenprot_api`, e pelo mesmo motivo: assim não há como chamá-lo de dentro de
    uma transação sem reparar. Uma chamada de rede de trinta segundos segurando
    o `BEGIN IMMEDIATE` poria a casa inteira no `busy_timeout`.

    Aqui ele nem `db` recebe: **não toca no banco.** Quem guarda é a rota.
"""
from __future__ import annotations

import http.client
import json
import ssl
import time
import urllib.parse
from typing import Any

import centrais_cred as CRED

# O ENDEREÇO, MEDIDO NO CONTRATO — `host` mais `schemes: ["https"]`, e o
# contrato não declara `basePath`. **Um ambiente só**: ver o cabeçalho.
BASE = "https://centralinside.rtdbrasil.org.br"

# Onde o contrato mora, para o teste o abrir. Fora de
# `SERVIDOR/INSTALAR_CARTORIO_GESTAO`, logo **não viaja no `.cgu`** — como a
# biblioteca do Gentil e os XSDs da CRA.
CONTRATO_NO_PROJETO = "FONTES_EXTERNAS/onrtdpj/swagger_v1.json"

# O CABEÇALHO DA AUTENTICAÇÃO, medido em `securityDefinitions.Token`:
# `apiKey`, `in: header`, `name: Authorization`.
#
#   **E ELE VAI COM `Bearer ` NA FRENTE — e o contrato mente nisso.**
#   Escrevi aqui, ao ler só o `securityDefinitions`, que ia sem o prefixo,
#   porque o tipo declarado é `apiKey` e não `oauth2`/`bearer`. **Estava
#   errado**: testado contra a Central de verdade em 12/09/2026, com o token
#   real do oficial — sem `Bearer ` ela devolve 401 «Não foi possível validar
#   seu acesso»; com `Bearer ` devolve 200 com os dados da serventia (CNS
#   000000). O contrato descreve o TIPO do campo (é uma string, não um fluxo
#   OAuth completo); não descreve o FORMATO do valor que a Central espera
#   dentro dele — e são perguntas diferentes.
CABECALHO_DO_TOKEN = "Authorization"
PREFIXO_DO_TOKEN = "Bearer "

PRAZO_PADRAO = 30       # segundos
TENTATIVAS_DE_REDE = 2

# OS CAMINHOS QUE ESTE MÓDULO USA, copiados do contrato **um a um**.
#
#   São 10 dos 81. Os outros 71 servem coisas que esta serventia não faz por
#   aqui — busca e apreensão, viabilidade, DBE, CDT, condomínio. Declarar os 81
#   daria oitenta e uma funções sem chamador, que é o defeito mais repetido
#   deste projeto.
#
#   **O teste abre o contrato e confere que os dez existem lá**, com o método
#   certo: caminho escrito à mão que a Central não conhece devolve 404, e 404
#   numa integração nova parece «não há nada hoje».
CAMINHO: dict[str, str] = {
    "pendentes": "/api/pedido/pendentes",
    "pedido": "/api/pedido/{protocolo}",
    "registrar": "/api/pedido/registrar",
    "orcamento": "/api/pedido/orcamento",
    "cancelar": "/api/pedido/cancelar",
    "nota_devolutiva": "/api/notadevolutiva",
    "notas_do_protocolo": "/api/v2/notadevolutiva/{protocolo}",
    # OS DOIS ABAIXO FICAM DECLARADOS E **NAO TEM FUNCAO**, de proposito.
    #
    #   **`/api/arquivo`** sobe um arquivo e devolve o id que o
    #   `RegistrarPedido` aceita em `ArquivoId`. Este sistema **nao tem o que
    #   subir**: nao ha molde `.odt` do registro do RCPJ/RTD, e portanto nao ha
    #   documento registrado para mandar de volta. Escrever a funcao seria a
    #   peca pronta que ninguem chama — o defeito mais repetido deste projeto.
    #
    #   **`/api/pedido/tiposregistro`** e o catalogo de tipos da Central.
    #   Nenhuma tela o pede hoje, e copia-lo para dentro do codigo seria pior:
    #   ele muda la, e a copia divergiria sem ninguem ver.
    #
    #   **O caminho fica escrito para ninguem o reinventar achando que sumiu.**
    #   E o precedente de `cenprot_api.renegociacoes`, apagada em 02/09/2026
    #   com o caminho mantido em `CAMINHO`.
    "arquivo": "/api/arquivo",
    "tipos_de_registro": "/api/pedido/tiposregistro",
    "cartorio": "/api/cartorio/{cns}",
}

METODO_DO_CAMINHO: dict[str, str] = {
    "pendentes": "GET", "pedido": "GET", "tipos_de_registro": "GET",
    "registrar": "POST", "orcamento": "POST", "cancelar": "POST",
    "nota_devolutiva": "POST", "notas_do_protocolo": "GET",
    "arquivo": "POST", "cartorio": "GET",
}

# OS CAMPOS DE `RegistrarPedido`, na grafia do contrato — **maiúscula inicial**.
#
#   JSON é sensível a caixa, e a Central ignora o que não conhece: mandar
#   `protocolo` em vez de `Protocolo` faria o registro subir **vazio**, com
#   HTTP 200 e nada acontecendo do lado de lá. É o defeito calado, que é o pior.
CAMPOS_DO_REGISTRO: tuple[str, ...] = (
    "Protocolo", "ArquivoId", "SeloDigital", "NumeroRegistro",
    "CodigoAutenticidade", "CodigoSeguranca", "ValoresRegistro", "DataRegistro")

CAMPOS_DA_NOTA: tuple[str, ...] = ("Protocolo", "Descricao", "ArquivoId")


class OnrtdpjError(RuntimeError):
    """Falha de transporte ou de credencial, com a frase para o balcão."""


class OnrtdpjRecusou(OnrtdpjError):
    """A Central respondeu, e respondeu não. O motivo dela vem junto."""


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _partes(base: str) -> tuple[str, int, str]:
    p = urllib.parse.urlsplit(base)
    if p.scheme != "https":
        # **HTTPS NÃO É OPCIONAL.** O token viaja nesta conexão; em texto puro,
        # quem estiver na rede o lê — e com ele fala pela serventia.
        raise OnrtdpjError(f"A base da ONRTDPJ tem de ser https, e veio «{base}».")
    return p.hostname or "", p.port or 443, (p.path or "").rstrip("/")


def token(*, pasta=None) -> str:
    """O token do cartório, lido do disco. Só LÊ.

    **Lido a cada chamada, e não guardado na memória.** Ao contrário do JWT da
    CENPROT, este não expira e não se pede à Central: é digitado pelo oficial.
    Guardá-lo em memória faria o token trocado só valer depois de reiniciar o
    servidor — e quem o trocou acabou de ir à Central justamente porque o
    antigo parou de funcionar.
    """
    return CRED.token_guardado(CRED.ONRTDPJ, pasta=pasta)


def tem_credencial(*, pasta=None) -> bool:
    """A tela pergunta isto antes de oferecer botão. **Não devolve o token.**"""
    return CRED.tem(CRED.ONRTDPJ, CRED.ambientes_de(CRED.ONRTDPJ)[0], pasta)


# ------------------------------------------------------------- o transporte


def _bater(metodo: str, caminho: str, *, corpo: bytes | None = None,
           cabecalhos: dict | None = None, prazo: int = PRAZO_PADRAO,
           pasta=None) -> dict:
    """Uma requisição. Devolve `{status, json, texto}` — nunca estoura por 4xx.

    **Quem decide o que fazer com um 404 é quem chamou**, e não este módulo:
    protocolo que não existe mais é caso normal numa Central que trabalha o dia
    inteiro.
    """
    hospedeiro, porta, prefixo = _partes(BASE)
    cabecas = {"Accept": "application/json",
               "User-Agent": "CartorioGestao",
               CABECALHO_DO_TOKEN: PREFIXO_DO_TOKEN + token(pasta=pasta)}
    cabecas.update(cabecalhos or {})

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
            # **RETENTAR SÓ O QUE NÃO CHEGOU.** Um `POST` que a Central pode ter
            # recebido não se repete sozinho: registrar o mesmo pedido duas
            # vezes é um ato a mais na Central que ninguém pediu.
            if metodo != "GET" or tentativa >= TENTATIVAS_DE_REDE:
                break
            time.sleep(1 + tentativa)
        finally:
            if conexao is not None:
                conexao.close()
    raise OnrtdpjError(
        f"Não consegui falar com a Central ONRTDPJ em {hospedeiro}: {ultimo}. "
        f"Confira a internet da serventia e tente de novo; nada foi enviado.")


def _resposta_ou_erro(r: dict, o_que: str) -> Any:
    """Traduz o código da Central numa resposta ou numa frase de balcão."""
    if r["status"] in (200, 201):
        return r["json"]
    if r["status"] in (401, 403):
        raise OnrtdpjError(
            f"A Central ONRTDPJ recusou o token ao {o_que}. Ele pode ter sido "
            f"trocado: entre em rtdbrasil.org.br, vá em Serviços → Envio "
            f"Extrato SINTER, copie o token e informe-o de novo em "
            f"Administrativo → Configurações.")
    if r["status"] == 404:
        raise OnrtdpjRecusou(
            f"A Central ONRTDPJ não encontrou o que se pediu ao {o_que}. Isso "
            f"é normal quando o pedido já foi tratado por lá ou por outra "
            f"pessoa.")
    detalhe = ""
    if isinstance(r["json"], dict):
        detalhe = _texto(r["json"].get("Message") or r["json"].get("message")
                         or r["json"].get("erro"))
    raise OnrtdpjRecusou(
        f"A Central ONRTDPJ respondeu {r['status']} ao {o_que}"
        + (f": {detalhe}" if detalhe else f". Resposta: {r['texto'][:200]}"))


def _protocolo(valor: Any, o_que: str) -> str:
    """O protocolo da Central, e a recusa de agir sobre nada.

    **ESTA RECUSA É REGRA DA CASA, E NÃO DO CONTRATO** — e a diferença fica
    dita porque ela importa: o contrato declara `required: []` em todos os cem
    esquemas, e não exige nada. Mas pedido sem protocolo age **sobre nada**: a
    Central responderia 200 e nenhum protocolo teria mudado, que é o defeito
    calado. A viagem até lá custa mais que a recusa aqui.
    """
    p = _texto(valor)
    if not p:
        raise OnrtdpjError(
            f"Sem o número do protocolo da Central não dá para {o_que} — ele é "
            f"o que diz de qual pedido se está falando.")
    return p


# --------------------------------------------------------------- o que se LÊ


def diagnostico(cns: str, *, pasta=None) -> dict:
    """Prova a ligação e o token, sem afirmar nada sobre pedido nenhum.

    **O TESTE DE CONEXÃO NÃO PODE MEXER EM PEDIDO.** `GET /api/cartorio/{cns}`
    é busca pura, por um número que a casa já tem — o CNS. É a mesma escolha do
    `BuscarApresentante` na CRA: a operação que prova a credencial sem afirmar
    coisa nenhuma sobre arquivo ou protocolo.
    """
    numero = _texto(cns)
    if not numero:
        raise OnrtdpjError(
            "Informe o CNS da serventia para testar a ligação — ele está em "
            "Administrativo → Configurações.")
    r = _bater("GET", CAMINHO["cartorio"].format(cns=urllib.parse.quote(numero)),
               pasta=pasta)
    return {"ok": r["status"] in (200, 201), "status": r["status"],
            "cartorio": r["json"] if isinstance(r["json"], dict) else None,
            "resposta": r["texto"][:400]}


def pendentes(*, servico_id: int | None = None, situacao_id: int | None = None,
              pasta=None) -> list[dict]:
    """Os pedidos que esperam o cartório. Só LÊ.

    **É POR AQUI QUE O TÍTULO ELETRÔNICO CHEGA** — é a metade do pedido do
    oficial que a Central atende.

    **O teto é da Central, e não deste módulo**: o contrato declara «limite de
    1200 registros» no próprio resumo da operação. Quem chegar perto disso está
    com fila acumulada, e é bom que apareça.
    """
    consulta = {}
    if servico_id is not None:
        consulta["servicoId"] = int(servico_id)
    if situacao_id is not None:
        consulta["situacaoId"] = int(situacao_id)
    caminho = CAMINHO["pendentes"]
    if consulta:
        caminho += "?" + urllib.parse.urlencode(consulta)
    resposta = _resposta_ou_erro(_bater("GET", caminho, pasta=pasta),
                                 "buscar os pedidos pendentes")
    if isinstance(resposta, list):
        return resposta
    # Resposta que não é lista (ex.: sim confundindo pedido com notas v2) não
    # pode virar list(dict) — isso quebrava rcpj_rtd_titulo.html.
    return []



def pedido(protocolo: str, *, pasta=None) -> dict:
    """A situação de um pedido. Só LÊ."""
    p = _protocolo(protocolo, "consultar o pedido")
    resposta = _resposta_ou_erro(
        _bater("GET", CAMINHO["pedido"].format(protocolo=urllib.parse.quote(p)),
               pasta=pasta), f"consultar o pedido {p}")
    return dict(resposta or {})


def notas_devolutivas(protocolo: str, *, pasta=None) -> list[dict]:
    """As notas devolutivas daquele protocolo, com link e nome do arquivo.

    **A `v2`, e não a `v1`** — medido: a diferença declarada no contrato é que
    ela devolve «arquivos com link e nome». Sem o link, a nota que a Central
    guarda não se lê daqui.
    """
    p = _protocolo(protocolo, "listar as notas devolutivas")
    resposta = _resposta_ou_erro(
        _bater("GET", CAMINHO["notas_do_protocolo"].format(
            protocolo=urllib.parse.quote(p)), pasta=pasta),
        f"listar as notas devolutivas de {p}")
    if isinstance(resposta, list):
        return resposta
    return []


# ------------------------------------------------------------ o que SOBE


def _mandar_json(chave: str, corpo: dict, o_que: str, *, pasta=None) -> Any:
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    r = _bater(METODO_DO_CAMINHO[chave], CAMINHO[chave], corpo=dados,
               cabecalhos={"Content-Type": "application/json"}, pasta=pasta)
    return _resposta_ou_erro(r, o_que)


def informar_orcamento(protocolo: str, valor, *, pasta=None) -> Any:
    """Informa à Central quanto custa aquele pedido."""
    p = _protocolo(protocolo, "informar o orçamento")
    try:
        quanto = float(str(valor).replace(",", "."))
    except (TypeError, ValueError) as erro:
        raise OnrtdpjError(
            f"«{valor}» não é um valor de orçamento. Escreva em reais, com "
            f"vírgula ou ponto.") from erro
    return _mandar_json("orcamento", {"Protocolo": p, "ValorOrcamento": quanto},
                        f"informar o orçamento de {p}", pasta=pasta)


def cadastrar_nota_devolutiva(protocolo: str, descricao: str, *,
                              arquivo_id: int | None = None,
                              pasta=None) -> int:
    """Manda a nota devolutiva à Central, e devolve o **id** dela.

    **É a qualificação NEGATIVA chegando a quem apresentou.** No título de
    papel, ela sai impressa e volta na mão; no eletrônico, é por aqui.

    A descrição vazia é recusada **por regra da casa**: o contrato não a exige,
    e nota devolutiva sem o que fazer é devolver o título sem dizer o que
    fazer — a mesma régua de `rg_titulo.qualificar`.
    """
    p = _protocolo(protocolo, "cadastrar a nota devolutiva")
    texto = _texto(descricao)
    if not texto:
        raise OnrtdpjError(
            "Escreva as exigências da nota devolutiva — nota sem o que cumprir "
            "devolve o título sem dizer o que fazer.")
    corpo: dict[str, Any] = {"Protocolo": p, "Descricao": texto}
    if arquivo_id is not None:
        corpo["ArquivoId"] = int(arquivo_id)
    resposta = _mandar_json("nota_devolutiva", corpo,
                            f"cadastrar a nota devolutiva de {p}", pasta=pasta)
    identidade = (resposta or {}).get("id") if isinstance(resposta, dict) else None
    return int(identidade) if identidade is not None else 0


def registrar_pedido(protocolo: str, *, numero_registro: str = "",
                     selo_digital: str = "", arquivo_id: int | None = None,
                     codigo_autenticidade: str = "",
                     codigo_seguranca: str = "", data_registro: str = "",
                     valores: list[dict] | None = None, pasta=None) -> Any:
    """Informa à Central que o pedido foi REGISTRADO nesta serventia.

    **ESTE MÓDULO NÃO LAVRA O REGISTRO — ele o COMUNICA.** Quem lavra é
    `rg_titulo.registrar`, com o livro, a folha e a numeração da casa; aqui só
    sobe o que já foi lavrado. Um atalho que registrasse na Central sem lavrar
    aqui poria no mundo um registro que o livro não tem.

    **Os nomes dos campos vão na grafia do contrato, com maiúscula inicial.**
    JSON é sensível a caixa e a Central ignora o que não conhece: `protocolo`
    em vez de `Protocolo` subiria um registro **vazio**, com HTTP 200 e nada
    acontecendo lá — o defeito calado, que é o pior.
    """
    p = _protocolo(protocolo, "informar o registro")
    corpo: dict[str, Any] = {"Protocolo": p}
    if _texto(numero_registro):
        corpo["NumeroRegistro"] = _texto(numero_registro)
    if _texto(selo_digital):
        corpo["SeloDigital"] = _texto(selo_digital)
    if arquivo_id is not None:
        corpo["ArquivoId"] = int(arquivo_id)
    if _texto(codigo_autenticidade):
        corpo["CodigoAutenticidade"] = _texto(codigo_autenticidade)
    if _texto(codigo_seguranca):
        corpo["CodigoSeguranca"] = _texto(codigo_seguranca)
    if _texto(data_registro):
        corpo["DataRegistro"] = _texto(data_registro)
    if valores:
        corpo["ValoresRegistro"] = list(valores)
    # **CAMPO FORA DO CONTRATO NÃO SOBE.** A Central ignora o que não conhece,
    # e ignorar em silêncio é como um erro de digitação vira um registro
    # incompleto que ninguém percebe. Aqui ele estoura antes de sair.
    sobrando = sorted(set(corpo) - set(CAMPOS_DO_REGISTRO))
    if sobrando:
        raise OnrtdpjError(
            f"Estes campos não existem no contrato da Central e não vão subir: "
            f"{', '.join(sobrando)}.")
    return _mandar_json("registrar", corpo, f"informar o registro de {p}",
                        pasta=pasta)


def cancelar_pedido(protocolo: str, motivo: str, *, pasta=None) -> Any:
    """Cancela o pedido na Central, com o motivo escrito.

    O motivo é exigido **por regra da casa** — o contrato não o exige. Pedido
    cancelado sem motivo é o que ninguém consegue explicar seis meses depois; é
    a mesma régua de `caixa_protocolo` e de `rg_titulo.encerrar`.
    """
    p = _protocolo(protocolo, "cancelar o pedido")
    razao = _texto(motivo)
    if len(razao) < 10:
        raise OnrtdpjError(
            "Escreva o motivo do cancelamento com pelo menos dez letras — «ok» "
            "não explica nada a quem ler daqui a dois anos.")
    return _mandar_json("cancelar",
                        {"Protocolo": p, "MotivoCancelamento": razao},
                        f"cancelar o pedido {p}", pasta=pasta)
