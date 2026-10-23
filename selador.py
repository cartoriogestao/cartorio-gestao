"""
O contrato do Selador API do TJMA.

DE ONDE VEM ESTE ARQUIVO
    Da documentacao OFICIAL do Selador, encontrada na maquina do E-Oficio em
    arquivos\\eoficio\\Selo Eletronico\\selador-doc — seis arquivos HTML, um por
    atribuicao, gerados pelo proprio Tribunal e datados de 08/10/2017.

    Os enderecos, os nomes dos campos e os codigos de resposta abaixo NAO
    foram inferidos: foram extraidos daquela documentacao. Onde algo continua
    desconhecido, esta dito que continua.

O QUE FICOU SABIDO, E QUE ESTAVA EM DUVIDA
    ENDERECOS (achados dentro do proprio e-oficio-ma.exe):
      producao  https://selador.ma.portalselo.com.br:9443
      auth      https://ma.portalselo.com.br:9443/auth
      ha tambem um ambiente de HOMOLOGACAO, com botao proprio na tela do
      E-Oficio; a forma exata da URL nao ficou legivel e NAO esta chutada aqui.

    AUTENTICACAO: OAuth2 password grant, no molde Keycloak.
      POST /auth, application/x-www-form-urlencoded, com
      username, password, client_id=selador (fixo), grant_type=password (fixo).
      A resposta traz access_token, expires_in, refresh_token, token_type.
      Depois: cabecalho Authorization: Bearer <token> em toda requisicao.

    SID — e a peca que explica um numero que me incomodou no acervo.
      Todo endpoint aceita ?sid=<codigo>. O selador guarda o vinculo entre o
      SID e o selo gerado: repetindo a requisicao com o MESMO SID depois de
      uma falha de comunicacao, ele devolve o selo que ja existe em vez de
      gerar outro.

      No acervo desta serventia ha 1.304 selos obtidos e NUNCA usados — 5% de
      tudo, quinhentos so em 2025, e apenas 5 deles cancelados. E exatamente a
      marca de quem repete a chamada sem chave de idempotencia: a primeira
      resposta se perde, o ato e refeito, e o selo da tentativa perdida fica
      orfao. Com SID isso nao acontece.

      A documentacao adverte, e a advertencia e severa: SID JAMAIS SE REUSA
      PARA ATO DIFERENTE. Reusado, o selador pode devolver o selo do ato
      anterior. E recomenda que o SID seja unico no universo de cartorios,
      porque ele aparece tambem no Portal do Selo.

O QUE ESTE MODULO NAO FAZ
    Nao fala com a rede. Ele e o CONTRATO: enderecos, forma do pedido, forma
    da resposta, forma do erro, e a geracao de SID. A chamada em si depende de
    credencial, e a credencial esta na tela "Selador - Propriedades" do
    E-Oficio, com os campos URL Selador, Username e Password.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


class SeladorError(ValueError):
    """Impedimento de contrato, com mensagem pronta para a tela."""


# --------------------------------------------------------- os enderecos

# Os enderecos que estao COMPILADOS no e-oficio-ma.exe. Sao o padrao de
# fabrica, e nao necessariamente o que esta serventia usa — ver abaixo.
BASE_PRODUCAO = "https://selador.ma.portalselo.com.br:9443"
AUTH_PRODUCAO = "https://ma.portalselo.com.br:9443/auth"

# CORRECAO DE 21/08/2026, e ela muda a arquitetura do modulo.
#
# Eu havia concluido que o sistema deveria chamar `BASE_PRODUCAO` direto. A
# tabela `tbSeladorConfiguracao` do acervo diz outra coisa:
#
#     strUrlSelador = https://192.168.0.200:443   (o IP real desta casa fica no perfil local)
#
# E um endereco de REDE LOCAL. Esta serventia nao fala com o Tribunal pela
# internet: fala com um Selador instalado numa maquina do escritorio, que e
# quem guarda o estoque de selo e conversa com o TJMA. Os dois enderecos
# acima sao o que veio de fabrica no programa; o que vale e o configurado.
#
# Por isso NADA neste modulo assume a base: `endpoint()` e `montar_pedido()`
# recebem a base de quem chama, e o padrao de fabrica so entra se ninguem
# disser o contrario. Apontar para a nuvem uma casa que sela num appliance
# local e pedir 401 no meio do atendimento — ou, pior, selar em duplicidade.
BASE_OBSERVADA_NA_SERVENTIA = "https://192.168.0.200:443"

# O E-Oficio tem botao de "URL de Homologacao", entao o ambiente existe. A URL
# exata nao ficou legivel no binario nem esta em `tbSeladorConfiguracao`, que
# tem tres colunas apenas — URL, usuario e senha. Chutar endereco de
# homologacao e pedir para selar de verdade achando que era teste.
BASE_HOMOLOGACAO: str | None = None

# As credenciais existem e estao gravadas: em `tbSeladorConfiguracao` o usuario
# tem 16 caracteres e a senha 8. NAO foram extraidas, nem estao em nenhum
# arquivo deste projeto — elas entram pela tela de configuracao da serventia,
# como qualquer outra senha, e ficam no banco da casa.
CLIENT_ID = "selador"
GRANT_TYPE = "password"


# ------------------------------------------------------------ os endpoints
#
# 181 servicos de selo, extraidos da documentacao oficial. `campo` e o nome
# do atributo que embrulha o corpo do pedido, e `schema` o nome do modelo na
# documentacao — os dois variam de endpoint para endpoint, e errar o nome do
# embrulho devolve 400 com "Informe todos os dados obrigatorios".

ENDPOINTS: dict[str, dict[str, Any]] = {
    "/selo/civil/apostila-haia": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosAtoApostilamentoHaia",
        "descricao": "Serviço utilizado para gerar o selo para ato de apostilamento de Haia."},
    "/selo/civil/atos-em-geral": {"atribuicao": "civil", "campo": "dados", "schema": "DadosAtosEmGeral",
        "descricao": "Serviço utilizado para gerar selo para atos em geral."},
    "/selo/civil/ausencia": {"atribuicao": "civil", "campo": "dadosSeloAusencia", "schema": "DadosSeloPrimeiraViaCertidoesLivroE",
        "descricao": "Serviço utilizado para gerar o selo de ausência."},
    "/selo/civil/ausencia/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de ausência."},
    "/selo/civil/ausencia/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoAusencia", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para averbação de ausência."},
    "/selo/civil/ausencia/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de ausência."},
    "/selo/civil/ausencia/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para retificação de ausência."},
    "/selo/civil/ausencia/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de ausência."},
    "/selo/civil/autenticacao": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParteReferencia",
        "descricao": "Serviço utilizado para gerar o selo de autenticação de algum ato de registro civil."},
    "/selo/civil/casamento": {"atribuicao": "civil", "campo": "dadosSeloCasamento", "schema": "DadosSeloCasamento",
        "descricao": "Serviço utilizado para gerar o selo para registro e certidão de casamento."},
    "/selo/civil/casamento/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de casamento."},
    "/selo/civil/casamento/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoCasamento", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para averbação do registro e certidão de casamento."},
    "/selo/civil/casamento/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de casamento."},
    "/selo/civil/casamento/conversao": {"atribuicao": "civil", "campo": "dadosSeloCasamentoConversao", "schema": "DadosSeloHabilitacaoCasamentoConversao",
        "descricao": "Serviço utilizado para gerar o selo para habilitação de conversão de união estável em casamento."},
    "/selo/civil/casamento/habilitacao": {"atribuicao": "civil", "campo": "dadosSeloCasamento", "schema": "DadosSeloHabilitacaoCasamento",
        "descricao": "Serviço utilizado para gerar o selo para habilitação de casamento."},
    "/selo/civil/casamento/habilitacao/certidao": {"atribuicao": "civil", "campo": "dadosSeloCasamento", "schema": "DadosSeloHabilitacaoCertidaoCasamento",
        "descricao": "Serviço utilizado para gerar o selo de certidão de habilitação de casamento."},
    "/selo/civil/casamento/habilitacao/conversao": {"atribuicao": "civil", "campo": "dadosSeloCasamentoConversao", "schema": "DadosSeloHabilitacaoCasamentoConversao",
        "descricao": "Serviço utilizado para gerar o selo para habilitação de conversão de união estável em casamento."},
    "/selo/civil/casamento/reconhecimento-firma": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParteReferencia",
        "descricao": "Serviço utilizado para gerar o selo de reconhecimento de firma para um ato de casamento."},
    "/selo/civil/casamento/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para retificação de casamento."},
    "/selo/civil/casamento/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de casamento."},
    "/selo/civil/casamento/transcricao": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "AtoSeloComParte",
        "descricao": "Serviço utilizado para gerar os selos para o registro e certidão de transcrição."},
    "/selo/civil/casamento/transcricao/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de transcrição de casamento."},
    "/selo/civil/casamento/transcricao/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoObito", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de averbação de transcrição de casamento."},
    "/selo/civil/casamento/transcricao/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de transcrição de casamento."},
    "/selo/civil/casamento/transcricao/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar os selos para retificação de transcrição de casamento."},
    "/selo/civil/casamento/transcricao/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de transcrição de casamento."},
    "/selo/civil/certidao": {"atribuicao": "civil", "campo": "dadosSeloRCPN", "schema": "DadosSeloRCPNRegistroCivil",
        "descricao": "Serviço utilizado para outras certidões do RCPN."},
    "/selo/civil/certidao/materializacao": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloCertidaoMaterializacao",
        "descricao": "Serviço utilizado para gerar o selo de materialização de Certidão (CRC)."},
    "/selo/civil/curatela": {"atribuicao": "civil", "campo": "dadosSeloCuratela", "schema": "DadosSeloPrimeiraViaCertidoesLivroE",
        "descricao": "Serviço utilizado para gerar o selo de curatela."},
    "/selo/civil/curatela/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de curatela."},
    "/selo/civil/curatela/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoCuratela", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de averbação de curatela."},
    "/selo/civil/curatela/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de curatela."},
    "/selo/civil/curatela/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para retificação de curatela."},
    "/selo/civil/curatela/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de curatela."},
    "/selo/civil/emancipacao": {"atribuicao": "civil", "campo": "dadosSeloCertidaoEmancipacao", "schema": "DadosSeloCertidaoEmancipacao",
        "descricao": "Serviço utilizado para gerar o selo para a primeira via de certidão de emancipação."},
    "/selo/civil/emancipacao/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de certidão de emancipação."},
    "/selo/civil/emancipacao/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoEmancipacao", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de averbação de emancipação."},
    "/selo/civil/emancipacao/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de emancipacao."},
    "/selo/civil/emancipacao/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para a retificação de certidão de emancipação."},
    "/selo/civil/emancipacao/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de certidão de emancipação."},
    "/selo/civil/interdicao": {"atribuicao": "civil", "campo": "dadosSeloInterdicao", "schema": "DadosSeloPrimeiraViaCertidoesLivroE",
        "descricao": "Serviço utilizado para gerar o selo de Interdição."},
    "/selo/civil/interdicao/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de interdição."},
    "/selo/civil/interdicao/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoInterdicao", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de averbação de interdição."},
    "/selo/civil/interdicao/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de interdição."},
    "/selo/civil/interdicao/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para retificação de interdição."},
    "/selo/civil/interdicao/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de interdição."},
    "/selo/civil/nascimento": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloNascimento",
        "descricao": "Serviço utilizado para gerar o selo de registro e certidão de nascimento."},
    "/selo/civil/nascimento/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de anotação de determinação judicial de nascimento."},
    "/selo/civil/nascimento/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoNascimento", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de averbação de registro e certidão de nascimento."},
    "/selo/civil/nascimento/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de nascimento."},
    "/selo/civil/nascimento/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de retificação de nascimento."},
    "/selo/civil/nascimento/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo de segunda via de nascimento."},
    "/selo/civil/nascimento/transcricao": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "AtoSeloComParte",
        "descricao": "Serviço utilizado para gerar os selos para o registro e certidão de transcrição."},
    "/selo/civil/nascimento/transcricao/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de transcrição de nascimento."},
    "/selo/civil/nascimento/transcricao/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoCasamento", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para averbação de transcrição de nascimento."},
    "/selo/civil/nascimento/transcricao/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de transcrição de nascimento."},
    "/selo/civil/nascimento/transcricao/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar os selos para retificação de transcrição de nascimento."},
    "/selo/civil/nascimento/transcricao/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de transcrição de nascimento."},
    "/selo/civil/natimorto": {"atribuicao": "civil", "campo": "dadosSeloRegistroNatimorto", "schema": "DadosSeloNatimorto",
        "descricao": "Serviço utilizado para gerar o selo para o registro e certidão de natimorto."},
    "/selo/civil/natimorto/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de natimorto."},
    "/selo/civil/natimorto/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoNatimorto", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para averbação de registro e certidão de natimorto."},
    "/selo/civil/natimorto/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de natimorto."},
    "/selo/civil/natimorto/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de retificação de natimorto."},
    "/selo/civil/natimorto/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de natimorto."},
    "/selo/civil/obito": {"atribuicao": "civil", "campo": "dadosSeloRegistroObito", "schema": "DadosSeloObito",
        "descricao": "Serviço utilizado para gerar o selo de registro e certidão de óbito."},
    "/selo/civil/obito/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar os selos de anotação de determinação judicial de óbito."},
    "/selo/civil/obito/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoObito", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de averbação do registro e certidão de óbito."},
    "/selo/civil/obito/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de óbito."},
    "/selo/civil/obito/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para retificação de óbito."},
    "/selo/civil/obito/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de óbito"},
    "/selo/civil/obito/transcricao": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "AtoSeloComParte",
        "descricao": "Serviço utilizado para gerar os selos para o registro e certidão de transcrição."},
    "/selo/civil/obito/transcricao/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de transcrição de óbito."},
    "/selo/civil/obito/transcricao/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoTranscricaoObito", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de averbação de transcrição de óbito."},
    "/selo/civil/obito/transcricao/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de transcrição de óbito."},
    "/selo/civil/obito/transcricao/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para retificação de transcrição de óbito."},
    "/selo/civil/obito/transcricao/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de transcrição de óbito."},
    "/selo/civil/opcao-nacionalidade": {"atribuicao": "civil", "campo": "dadosSeloOpcaoNacionalidade", "schema": "DadosSeloPrimeiraViaCertidoesLivroE",
        "descricao": "Serviço utilizado para gerar o selo de Opção de Nacionalidade."},
    "/selo/civil/opcao-nacionalidade/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de nacionalidade."},
    "/selo/civil/opcao-nacionalidade/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoNacionalidade", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de averbação de nacionalidade."},
    "/selo/civil/opcao-nacionalidade/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de nacionalidade."},
    "/selo/civil/opcao-nacionalidade/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selos para retificação de nacionalidade."},
    "/selo/civil/opcao-nacionalidade/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de nacionalidade"},
    "/selo/civil/separacao-divorcio": {"atribuicao": "civil", "campo": "dadosSeloSeparacaoJudicial", "schema": "DadosSeloPrimeiraViaCertidoesLivroE",
        "descricao": "Serviço utilizado para gerar o selo de Separação Judicial."},
    "/selo/civil/separacao-divorcio/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de sentença."},
    "/selo/civil/separacao-divorcio/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoSeparacao", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de averbação de separação."},
    "/selo/civil/separacao-divorcio/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de separação."},
    "/selo/civil/separacao-divorcio/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para retificação de sentença."},
    "/selo/civil/separacao-divorcio/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de separação."},
    "/selo/civil/tutela": {"atribuicao": "civil", "campo": "dadosSeloTutela", "schema": "DadosSeloPrimeiraViaCertidoesLivroE",
        "descricao": "Serviço utilizado para gerar o selo de tutela."},
    "/selo/civil/tutela/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de tutela."},
    "/selo/civil/tutela/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacaoTutela", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de averbação de tutela."},
    "/selo/civil/tutela/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de tutela."},
    "/selo/civil/tutela/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para retificação de tutela."},
    "/selo/civil/tutela/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de tutela."},
    "/selo/civil/uniao-estavel": {"atribuicao": "civil", "campo": "dadosSeloUniaoEstavel", "schema": "DadosSeloPrimeiraViaCertidoesLivroE",
        "descricao": "Serviço utilizado para gerar o selo de União Estável."},
    "/selo/civil/uniao-estavel/anotacao": {"atribuicao": "civil", "campo": "dadosSeloAnotacao", "schema": "DadosSeloAnotacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo para anotação de determinação judicial de União Estável."},
    "/selo/civil/uniao-estavel/averbacao": {"atribuicao": "civil", "campo": "dadosSeloAverbacao", "schema": "DadosSeloAverbacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selo de averbação de União Estável."},
    "/selo/civil/uniao-estavel/certidao-negativa": {"atribuicao": "civil", "campo": "dadosSelo", "schema": "DadosSeloParte",
        "descricao": "Serviço utilizado para gerar o selo de certidão negativa de União Estável."},
    "/selo/civil/uniao-estavel/retificacao": {"atribuicao": "civil", "campo": "dadosSeloRetificacao", "schema": "DadosSeloRetificacaoRegistroCivil",
        "descricao": "Serviço utilizado para gerar o selos para retificação de União Estável."},
    "/selo/civil/uniao-estavel/segunda-via": {"atribuicao": "civil", "campo": "dadosSegundaViaCertidao", "schema": "DadosSegundaViaCertidao",
        "descricao": "Serviço utilizado para gerar o selo para a segunda via de União Estável"},
    "/selo/imovel/apostila-haia": {"atribuicao": "imovel", "campo": "dados", "schema": "ApostilamentoHaia",
        "descricao": "Serviço utilizado para gerar selo para ato de apostila de haia."},
    "/selo/imovel/ato-declarado/com-valor": {"atribuicao": "imovel", "campo": "dadosSeloAtoDeclarado", "schema": "DadosSeloAtoComValorDeclaradoRI",
        "descricao": "Serviço utilizado para gerar o selo de registro/averbação de imóvel para o ato com valor declarado."},
    "/selo/imovel/ato-declarado/sem-valor": {"atribuicao": "imovel", "campo": "dadosSeloAtoDeclarado", "schema": "DadosSeloAtoSemValorDeclaradoRI",
        "descricao": "Serviço utilizado para gerar o selo de registro/averbação de imóvel para o ato sem valor declarado."},
    "/selo/imovel/atos-em-geral": {"atribuicao": "imovel", "campo": "dados", "schema": "AtosEmGeral",
        "descricao": "Serviço utilizado para gerar selo para atos em geral."},
    "/selo/imovel/cancelamento": {"atribuicao": "imovel", "campo": "dadosSeloAtoSemValorDeclaradoRI", "schema": "DadosSeloAtoSemValorDeclaradoRI",
        "descricao": "Serviço utilizado para gerar selos de baixa ou cancelamento."},
    "/selo/imovel/certidao": {"atribuicao": "imovel", "campo": "dadosSeloCertidao", "schema": "DadosSeloCertidaoRI",
        "descricao": "Serviço utilizado para gerar o selo de registro de imóvel para o ato de Certidão."},
    "/selo/imovel/condominio/constituicao": {"atribuicao": "imovel", "campo": "dadosSeloConstCondominioRI", "schema": "DadosSeloConstCondominioRI",
        "descricao": "Serviço utilizado para gerar selos de contituição, incorporação ou instituição de condominio."},
    "/selo/imovel/condominio/convencao": {"atribuicao": "imovel", "campo": "dadosSeloConvensao", "schema": "DadosSeloConvencaoCondominioPorConvencaoRI",
        "descricao": "Serviço utilizado para gerar o selo de registro de imóvel para o ato de convenção de condomínio."},
    "/selo/imovel/condominio/unidade": {"atribuicao": "imovel", "campo": "dadosSeloConvencaoCondominioPorUnidadeRI", "schema": "DadosSeloConvencaoCondominioPorUnidadeRI",
        "descricao": "Serviço utilizado para gerar o selo de unidades de condominio."},
    "/selo/imovel/lote/remembramento": {"atribuicao": "imovel", "campo": "dadosSeloRemembramento", "schema": "DadosSeloRemembramentoLoteRI",
        "descricao": "Serviço utilizado para gerar o selo de registro de imóvel para o ato de remembramento de lote."},
    "/selo/imovel/lote/subdivisao": {"atribuicao": "imovel", "campo": "dadosSeloSubdivisao", "schema": "DadosSeloSubdivisaoLoteRI",
        "descricao": "Serviço utilizado para gerar o selo de registro de imóvel para o ato de subdivisão de lote."},
    "/selo/imovel/loteamento/rural": {"atribuicao": "imovel", "campo": "dadosSeloRural", "schema": "DadosSeloRural",
        "descricao": "Serviço utilizado para gerar o selo de Loteamento Rural."},
    "/selo/imovel/loteamento/urbano": {"atribuicao": "imovel", "campo": "dadosSeloAtoSemValorDeclarado", "schema": "DadosSeloAtoSemValorDeclaradoRI",
        "descricao": "Serviço utilizado para gerar o selo de Loteamento Urbano."},
    "/selo/imovel/pagamento-prestacao": {"atribuicao": "imovel", "campo": "dados", "schema": "DadosSeloCertidaoRI",
        "descricao": "Serviço utilizado para gerar selo para ato de pagamento de prestação."},
    "/selo/imovel/prenotacao": {"atribuicao": "imovel", "campo": "dadosSeloPrenotacao", "schema": "DadosSeloPrenotacaoRI",
        "descricao": "Serviço utilizado para gerar o selo de registro de imóvel para o ato de prenotação."},
    "/selo/maritimo/apostila-haia": {"atribuicao": "maritimo", "campo": "dados", "schema": "ApostilamentoHaia",
        "descricao": "Serviço utilizado para gerar selo para ato de apostila de haia."},
    "/selo/maritimo/atos-em-geral": {"atribuicao": "maritimo", "campo": "dados", "schema": "AtosEmGeral",
        "descricao": "Serviço utilizado para gerar selo para atos em geral."},
    "/selo/maritimo/notarial/ato-declarado/com-valor": {"atribuicao": "maritimo", "campo": "dadosSelo", "schema": "NotasComValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Escritura com valor declarado."},
    "/selo/maritimo/notarial/ato-declarado/sem-valor": {"atribuicao": "maritimo", "campo": "dadosSelo", "schema": "NotasSemValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Escritura sem valor declarado."},
    "/selo/maritimo/notarial/autenticacao": {"atribuicao": "maritimo", "campo": "dadosSelo", "schema": "Autenticacao",
        "descricao": "Serviço notarial utilizado para gerar selo marítimo de autenticação."},
    "/selo/maritimo/notarial/certidao": {"atribuicao": "maritimo", "campo": "dadosSelo", "schema": "NotasSemValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo certidão de marítimo notarial."},
    "/selo/maritimo/notarial/escritura-declaratoria": {"atribuicao": "maritimo", "campo": "dadosSelo", "schema": "MaritimoEscrituraDeclaratoria",
        "descricao": "Serviço notarial utilizado para gerar selo marítimo de escritura declaratória."},
    "/selo/maritimo/notarial/reconhecimento-firma": {"atribuicao": "maritimo", "campo": "dadosSelo", "schema": "ReconhecimentoFirma",
        "descricao": "Serviço notarial utilizado para gerar selo marítimo de reconhecimento de firma."},
    "/selo/maritimo/notarial/substabelecimento": {"atribuicao": "maritimo", "campo": "dadosSelo", "schema": "SubstabelecimentoRevogacaoNotas",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Substabelecimento."},
    "/selo/maritimo/notarial/venda-embarcacao": {"atribuicao": "maritimo", "campo": "dadosSelo", "schema": "ProcuracaoNotas",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Procuração Venda de Qualquer Espécie."},
    "/selo/maritimo/registral/ato-declarado/com-valor": {"atribuicao": "maritimo", "campo": "dadosSelo", "schema": "MaritimoComValorDeclaradoRegistral",
        "descricao": "Serviço utilizado para gerar o selo de registro/averbação de marítimo para o ato com valor declarado."},
    "/selo/maritimo/registral/ato-declarado/sem-valor": {"atribuicao": "maritimo", "campo": "dadosSelo", "schema": "MaritimoSemValorDeclaradoRegistral",
        "descricao": "Serviço utilizado para gerar o selo de registro/averbação de marítimo para o ato sem valor declarado."},
    "/selo/maritimo/registral/certidao": {"atribuicao": "maritimo", "campo": "dadosSelo", "schema": "MaritimoCertidaoRegistral",
        "descricao": "Serviço utilizado para gerar selo de registro marítimo para Certidão."},
    "/selo/maritimo/registral/prenotacao": {"atribuicao": "maritimo", "campo": "dadosSelo", "schema": "MaritimoPrenotacaoRegistral",
        "descricao": "Serviço utilizado para gerar selo de registro marítimo para Prenotação."},
    "/selo/notas/apostila-haia": {"atribuicao": "notas", "campo": "dados", "schema": "ApostilamentoHaia",
        "descricao": "Serviço utilizado para gerar selo para ato de apostila de haia."},
    "/selo/notas/ato-declarado/com-valor": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "NotasComValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Escritura com valor declarado."},
    "/selo/notas/ato-declarado/sem-valor": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "NotasSemValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Escritura sem valor declarado."},
    "/selo/notas/atos-em-geral": {"atribuicao": "notas", "campo": "dados", "schema": "AtosEmGeral",
        "descricao": "Serviço utilizado para gerar selo para atos em geral."},
    "/selo/notas/autenticacao": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "Autenticacao",
        "descricao": "Serviço utilizado para gerar selo de autenticação."},
    "/selo/notas/averbacao": {"atribuicao": "notas", "campo": "dados", "schema": "Averbacao",
        "descricao": "Serviço utilizado para gerar selo para ato de averbação."},
    "/selo/notas/cartao-assinatura": {"atribuicao": "notas", "campo": "dados", "schema": "AberturaCartao",
        "descricao": "Serviço utilizado para gerar selo para ato de abertura de cartão."},
    "/selo/notas/certidao": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "NotasCertidao",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Certidão."},
    "/selo/notas/comunicacao-transferencia-veiculo": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "ComunicacaoTransferenciaVeiculo",
        "descricao": "Serviço utilizado para gerar selo de comunicação eletrônica de transferência de veículo."},
    "/selo/notas/procuracao/inss": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "ProcuracaoNotas",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Procuração INSS."},
    "/selo/notas/procuracao/poderes-especificos": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "ProcuracaoNotas",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Procuração Poderes Específicos."},
    "/selo/notas/procuracao/simples": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "ProcuracaoNotas",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Procuração Simples."},
    "/selo/notas/procuracao/venda": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "ProcuracaoNotas",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Procuração Venda de Qualquer Espécie."},
    "/selo/notas/publica-forma": {"atribuicao": "notas", "campo": "dados", "schema": "PublicaForma",
        "descricao": "Serviço utilizado para gerar selo para ato de publica forma de documento."},
    "/selo/notas/reconhecimento-firma": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "ReconhecimentoFirma",
        "descricao": "Serviço utilizado para gerar selo de reconhecimento de firma."},
    "/selo/notas/revogacao-procuracao": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "SubstabelecimentoRevogacaoNotas",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Revogação de Procuração."},
    "/selo/notas/substabelecimento": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "SubstabelecimentoRevogacaoNotas",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Substabelecimento."},
    "/selo/notas/testamento": {"atribuicao": "notas", "campo": "dadosSelo", "schema": "TestamentoNotas",
        "descricao": "Serviço utilizado para gerar selo de registro de notas para Testamento."},
    "/selo/protesto/apostila-haia": {"atribuicao": "protesto", "campo": "dados", "schema": "ApostilamentoHaia",
        "descricao": "Serviço utilizado para gerar selo para ato de apostila de haia."},
    "/selo/protesto/atos-em-geral": {"atribuicao": "protesto", "campo": "dados", "schema": "AtosEmGeral",
        "descricao": "Serviço utilizado para gerar selo para atos em geral."},
    "/selo/protesto/averbacao-pagamento": {"atribuicao": "protesto", "campo": "dadosSelo", "schema": "AverbacaoProtesto",
        "descricao": "Serviço utilizado para gerar selo de averbação de pagamento de título."},
    "/selo/protesto/baixa-cancelamento": {"atribuicao": "protesto", "campo": "dadosSelo", "schema": "BaixaCancelamentoProtesto",
        "descricao": "Serviço utilizado para gerar selo de registro para Baixa ou Cancelamento de Protesto."},
    "/selo/protesto/certidao": {"atribuicao": "protesto", "campo": "dadosSelo", "schema": "CertidaoProtesto",
        "descricao": "Serviço utilizado para gerar selo de certidão de protestos."},
    "/selo/protesto/certidao-unificada": {"atribuicao": "protesto", "campo": "dados", "schema": "DadosSeloCertidaoUnificada",
        "descricao": "Serviço utilizado para gerar selo para certidão unificada de protesto."},
    "/selo/protesto/intimacao": {"atribuicao": "protesto", "campo": "dadosSelo", "schema": "IntimacaoProtesto",
        "descricao": "Serviço utilizado para gerar selo de registro de protesto para Intimação"},
    "/selo/protesto/pagamento": {"atribuicao": "protesto", "campo": "dadosSelo", "schema": "PagamentoRetiradaProtesto",
        "descricao": "Serviço utilizado para gerar selo de pagamento de título."},
    "/selo/protesto/retirada": {"atribuicao": "protesto", "campo": "dadosSelo", "schema": "PagamentoRetiradaProtesto",
        "descricao": "Serviço utilizado para gerar selo de retirada de título."},
    "/selo/protesto/titulo": {"atribuicao": "protesto", "campo": "dadosSelo", "schema": "TituloProtesto",
        "descricao": "Serviço utilizado para gerar selo de registro de protesto de Título."},
    "/selo/rtdpj/acima-tres-diligencias": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjAcimaTresDiligencia",
        "descricao": "Serviço utilizado para gerar selo Acima de 3 diligências."},
    "/selo/rtdpj/apostila-haia": {"atribuicao": "rtdpj", "campo": "dados", "schema": "ApostilamentoHaia",
        "descricao": "Serviço utilizado para gerar selo para ato de apostila de haia."},
    "/selo/rtdpj/ato-declarado/averbacao/integral/sem-valor": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjSemValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo de Averbação Integral de Título, Documento ou Papel sem Valor Declarado."},
    "/selo/rtdpj/ato-declarado/integral/com-valor": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjComValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo de Registro Integral de Títulos e Documentos com Valor Declarado."},
    "/selo/rtdpj/ato-declarado/integral/sem-valor": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjSemValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo de Registro Integral de Títulos e Documentos sem Valor Declarado."},
    "/selo/rtdpj/ato-declarado/resumido/com-valor": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjComValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo de Registro Resumido de Títulos e Documentos com Valor Declarado."},
    "/selo/rtdpj/ato-declarado/resumido/sem-valor": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjSemValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo de Registro Resumido de Títulos e Documentos sem Valor Declarado."},
    "/selo/rtdpj/atos-em-geral": {"atribuicao": "rtdpj", "campo": "dados", "schema": "AtosEmGeral",
        "descricao": "Serviço utilizado para gerar selo para atos em geral."},
    "/selo/rtdpj/autenticacao-contabil": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjAutenticacaoLivrosContabeis",
        "descricao": "Serviço utilizado para gerar selo de Autenticação de Livros Contábeis."},
    "/selo/rtdpj/averbacao/com-valor": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjAverbacaoComValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo de Averbação de Títulos e Documentos Quando o Ato Tiver seu Próprio Valor."},
    "/selo/rtdpj/busca-acima-dez-anos": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjComMatriculaRegistroAverbacao",
        "descricao": "Serviço utilizado para gerar selo para buscas em livros ou papéis arquivados acima de dez anos por ano, até o máximo de R$ 230,78."},
    "/selo/rtdpj/busca-ate-dez-anos": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjComMatriculaRegistroAverbacao",
        "descricao": "Serviço utilizado para gerar selo para Busca em Livros ou Papéis Arquivados."},
    "/selo/rtdpj/cancelamento": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjCancelamento",
        "descricao": "Serviço utilizado para gerar selo de cancelamento, inclusive busca e certidão."},
    "/selo/rtdpj/certidao-negativa-pessoa-juridica": {"atribuicao": "rtdpj", "campo": "dados", "schema": "RtdpjCertidaoNegativa",
        "descricao": "Serviço utilizado para gerar selo para ato de Certidão Negativa para Pessoas Jurídicas."},
    "/selo/rtdpj/certidao-negativa-titulo-documento": {"atribuicao": "rtdpj", "campo": "dados", "schema": "RtdpjCertidaoNegativa",
        "descricao": "Serviço utilizado para gerar selo para ato de Certidão Negativa para Títulos e Documentos."},
    "/selo/rtdpj/certidao-notificacao": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjComMatriculaRegistroAverbacao",
        "descricao": "Serviço utilizado para gerar selo de Certidão Notificação."},
    "/selo/rtdpj/diligencia/fora-zona-urbana": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjDiligencia",
        "descricao": "Serviço utilizado para gerar selo de Registro de Diligências Fora da Zona Urbana."},
    "/selo/rtdpj/diligencia/zona-urbana": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjDiligencia",
        "descricao": "Serviço utilizado para gerar selo de Registro de Diligências Zona Urbana."},
    "/selo/rtdpj/matricula": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjMatricula",
        "descricao": "Serviço utilizado para gerar selo de matrícula de oficina impressora, jornal e outros periódicos, inclusive a certidão."},
    "/selo/rtdpj/pessoa-juridica/averbacao": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjSemValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo de Averbação de Pessoas Jurídicas, incluíndo os atos do processo, registro e arquivamento."},
    "/selo/rtdpj/pessoa-juridica/certidao": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjComMatriculaRegistroAverbacao",
        "descricao": "Serviço utilizado para gerar selo de Certidão de Atos de Processo de Pessoa Jurídica."},
    "/selo/rtdpj/pessoa-juridica/certidao/por-peca": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjComMatriculaRegistroAverbacao",
        "descricao": "Serviço utilizado para gerar selo de certidão por peça reproduzida e/ ou folha (Pessoa Jurídica)."},
    "/selo/rtdpj/pessoa-juridica/inscricao": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjSemValorDeclarado",
        "descricao": "Serviço utilizado para gerar selo de Inscrição de Pessoa Jurídica Incluindo os atos do processo, Registro e Arquivamento."},
    "/selo/rtdpj/titulo-documento/certidao/por-peca": {"atribuicao": "rtdpj", "campo": "dadosSelo", "schema": "RtdpjComMatriculaRegistroAverbacao",
        "descricao": "Serviço utilizado para gerar selo de certidão por peça reproduzida e/ ou folha (títulos e documentos)."},
}

ESPACOS = ("notas", "protesto", "civil", "imovel", "rtdpj", "maritimo")


# ------------------------------- o que o acervo mostrou ALEM da documentacao
#
# A documentacao e de 08/10/2017. Comparando os 26.123 pedidos reais desta
# serventia contra os 115 schemas dela: 86,2% batem exatamente, e NENHUM pedido
# jamais deixou de enviar um campo obrigatorio — o que da confianca no contrato.
#
# O resto sao cinco coisas que a API passou a aceitar DEPOIS de 2017. Ficam
# registradas porque, sem isto, alguem vai reescrever este modulo pela
# documentacao e remover o que estava funcionando.

ALEM_DA_DOCUMENTACAO: tuple[dict, ...] = (
    {"onde": "/selo/rtdpj/atos-em-geral-com-livro", "tipo": "endpoint",
     "usos_no_acervo": 46,
     "observacao": "endpoint que não consta da documentação de 2017"},
    {"onde": "AtosEmGeral.quantidade", "tipo": "campo", "usos_no_acervo": 1649,
     "observacao": "quantidade em atos em geral"},
    {"onde": "DadosAtosEmGeral.quantidade", "tipo": "campo", "usos_no_acervo": 1238,
     "observacao": "quantidade em atos em geral do registro civil"},
    {"onde": "DadosSeloCertidaoRI.isento", "tipo": "campo", "usos_no_acervo": 667,
     "observacao": "isenção na certidão de imóvel"},
    {"onde": "AtosEmGeral.convenio", "tipo": "campo", "usos_no_acervo": 18,
     "observacao": "convênio em atos em geral"},
)


# --------------------------------------------------- modelos comuns do pedido
#
# Os nomes sao os da documentacao, e nao se traduzem: e o que vai no JSON.

CAMPOS_DADOS_ATO = ("codigo", "codigoTabelaCusta", "desconto")
CAMPOS_DESCONTO = ("descontoLegal", "descontoProvimento279", "percentualDesconto")
CAMPOS_ISENTO = ("value", "motivo")
CAMPOS_PARTE = ("nome", "documento")
CAMPOS_REGISTRO_ANTERIOR = ("cartorioAnterior", "dataRegistroAnterior",
                            "folhaAnterior", "livroAnterior")

# `descontoProvimento279` e do PROVIMENTO 279/2016 DA CGJ DO AMAZONAS — 50% nos
# emolumentos e no ISS para atos de Registro de Imoveis e Notas. O Selador e um
# produto compartilhado entre estados, e este campo NAO e regra do Maranhao.
# Mandar `true` aqui seria conceder desconto que a norma local nao previu.
DESCONTO_DE_OUTRO_ESTADO = "descontoProvimento279"

# Natureza do reconhecimento de firma, da documentacao:
NATUREZA_FIRMA = {0: "Reconhecimento de firma por autenticidade",
                  1: "Reconhecimento de firma por semelhança"}


# ------------------------------------------------------------- a resposta

@dataclass(frozen=True)
class SeloGerado:
    """Um selo devolvido pelo selador — o modelo ResumoSeloGerado."""

    numero: str
    texto: str
    data_geracao: str | None = None
    saldo_remanescente: float | None = None


def ler_resposta(corpo: Any) -> list[SeloGerado]:
    """Le o RetornoResumoSeloGerado: uma LISTA de selos, nao um selo.

    Um pedido pode devolver mais de um selo — e o caso de `quantidade`, em que
    os valores sao multiplicados e sai um selo por unidade. Tratar a resposta
    como um selo so perderia os demais em silencio.
    """
    if not isinstance(corpo, dict):
        raise SeladorError("A resposta do selador não veio como objeto JSON.")
    resumos = corpo.get("resumos")
    if resumos is None:
        raise SeladorError(
            "A resposta do selador não trouxe «resumos». Se veio «status» e "
            "«message», é erro: use ler_erro().")
    if not isinstance(resumos, list) or not resumos:
        raise SeladorError("O selador respondeu sem nenhum selo em «resumos».")
    selos = []
    for r in resumos:
        numero = str((r or {}).get("numeroSelo") or "").strip()
        if not numero:
            raise SeladorError("O selador devolveu um resumo sem «numeroSelo».")
        saldo = (r or {}).get("saldoRemanescente")
        selos.append(SeloGerado(
            numero=numero,
            texto=str((r or {}).get("textoSelo") or "").strip(),
            data_geracao=(str(r.get("dataGeracao")) if r.get("dataGeracao") else None),
            saldo_remanescente=(float(saldo) if saldo is not None else None),
        ))
    return selos


@dataclass(frozen=True)
class ErroDoSelador:
    """O modelo ExceptionMessage."""

    status: int | None
    erro: str
    mensagem: str
    detalhes: tuple[str, ...] = ()

    def __str__(self) -> str:
        base = self.mensagem or self.erro or "O selador recusou o pedido."
        if self.detalhes:
            return f"{base} O Tribunal apontou: " + "; ".join(self.detalhes) + "."
        return base


def ler_erro(corpo: Any) -> ErroDoSelador:
    """Le a recusa do selador, com os detalhes campo a campo que ela traz."""
    if not isinstance(corpo, dict):
        return ErroDoSelador(status=None, erro="", mensagem=str(corpo or "")[:400])
    detalhes = corpo.get("details") or []
    if isinstance(detalhes, str):
        detalhes = [detalhes]
    return ErroDoSelador(
        status=(int(corpo["status"]) if str(corpo.get("status") or "").isdigit() else None),
        erro=str(corpo.get("error") or ""),
        mensagem=str(corpo.get("message") or ""),
        detalhes=tuple(str(d) for d in detalhes),
    )


# ------------------------------------------------------------------- o SID
#
# A chave de idempotencia. Tem de ser unica no universo de cartorios, porque
# aparece tambem no Portal do Selo — e tem de ser DETERMINISTICA a partir do
# ato, para que a repeticao de uma chamada que falhou gere o MESMO SID e o
# selador devolva o selo que ja existe em vez de gerar outro.

def sid(cns: Any, atribuicao: Any, referencia: Any, tentativa: int = 1) -> str:
    """O SID de um ato: CNS + atribuicao + referencia do ato, resumidos.

    `referencia` e o que identifica o ato DENTRO da serventia e nao muda entre
    tentativas — o id do ato no banco, ou livro/folha/termo. `tentativa` existe
    para o caso, e SO para o caso, em que se queira deliberadamente um selo
    novo: incrementar a tentativa muda o SID.

    NAO use data e hora aqui. Se o SID mudar a cada chamada, ele deixa de
    proteger contra a falha de comunicacao — que e a unica razao de existir.
    """
    cns = "".join(c for c in str(cns or "") if c.isdigit())
    if not cns:
        raise SeladorError("O SID precisa do CNS da serventia.")
    ref = str(referencia or "").strip()
    if not ref:
        raise SeladorError(
            "O SID precisa de uma referência do ato que não mude entre tentativas.")
    atr = str(atribuicao or "").strip().upper()
    semente = f"{cns}|{atr}|{ref}|{int(tentativa)}"
    resumo = hashlib.sha256(semente.encode("utf-8")).hexdigest()[:24].upper()
    return f"{cns}{atr[:2]}{resumo}"


# ---------------------------------------------------------------- o pedido

def endpoint(caminho: str) -> dict[str, Any]:
    """O endpoint pelo caminho, com o nome do embrulho e do schema."""
    c = str(caminho or "").strip()
    if c not in ENDPOINTS:
        raise SeladorError(
            f"«{c}» não é um serviço do selador. São {len(ENDPOINTS)} caminhos, "
            f"nos espaços {', '.join(ESPACOS)}.")
    return dict(ENDPOINTS[c], caminho=c)


def endpoints_de(espaco: str) -> dict[str, dict]:
    """Todos os endpoints de uma atribuicao."""
    e = str(espaco or "").strip().lower()
    if e not in ESPACOS:
        raise SeladorError(f"«{espaco}» não é um espaço do selador. São: {ESPACOS}.")
    return {k: v for k, v in ENDPOINTS.items() if v["atribuicao"] == e}


def montar_pedido(caminho: str, dados: dict, *, sid_do_ato: str | None = None,
                  base: str | None = None) -> dict[str, Any]:
    """Monta a requisicao — url, corpo e query — sem despachar nada.

    Devolve o que quem tiver credencial precisa para fazer o POST. Separado de
    proposito: assim o pedido inteiro se testa, e se confere contra os 26.130
    pedidos reais do acervo, sem tocar no Tribunal.
    """
    alvo = endpoint(caminho)
    if not isinstance(dados, dict) or not dados:
        raise SeladorError(f"O pedido para {caminho} veio sem dados.")
    if DESCONTO_DE_OUTRO_ESTADO in dados and dados[DESCONTO_DE_OUTRO_ESTADO]:
        raise SeladorError(
            f"«{DESCONTO_DE_OUTRO_ESTADO}» é o Provimento 279/2016 da Corregedoria "
            f"do AMAZONAS, e não regra do Maranhão. Enviar verdadeiro aqui seria "
            f"conceder desconto que a norma local não previu.")
    # O CORPO E O PROPRIO OBJETO, E NAO UM EMBRULHO — correcao de 27/08/2026,
    # e ela e a maior deste projeto: sem ela NENHUM selo automatico sairia, em
    # atribuicao nenhuma.
    #
    # O QUE EU TINHA ESCRITO, E POR QUE ESTAVA ERRADO
    #     Eu mandava `{alvo["campo"]: dados}` — `{"dadosSelo": {...}}`. A
    #     documentacao lista, na tabela de parametros, `Type: Body | Name:
    #     dadosSelo | Schema: ReconhecimentoFirma`, e eu li o "Name" como se
    #     fosse o nome de um campo do JSON. **Em Swagger, parametro `in: body`
    #     nao tem nome no corpo**: o corpo E o schema. O "Name" e rotulo da
    #     documentacao.
    #
    # QUEM DESEMPATOU FOI O ACERVO, e nao a minha leitura: dos **26.123**
    #     envelopes que esta casa mandou, **ZERO** vao embrulhados. Os campos
    #     estao na raiz.
    #
    # E `dadosSelo` EXISTE MESMO — como campo DE DENTRO de alguns esquemas: no
    #     civil e no imovel o corpo e `{codigoAto, dadosSelo: {escrevente,
    #     versaoTabelaDeCustas, ...}, nomesPartes, quantidade}`. Foi essa
    #     coincidencia de nome que sustentou o erro: eu via `dadosSelo` no
    #     envelope real e achava que era o meu embrulho aparecendo.
    #
    # O DEFEITO CHEGOU PELO BALCAO, e nao por teste: em 27/08/2026 o oficial
    #     selou um reconhecimento de firma e o aparelho respondeu «O campo
    #     "nomesReconhecido" e obrigatorio; O campo "escrevente" e
    #     obrigatorio» — os dois campos que nos mandavamos, um nivel abaixo de
    #     onde ele os procurava. Nenhum teste pegou porque todos comparavam o
    #     pedido com a minha propria ideia do pedido.
    #
    # `campo` FICA em `ENDPOINTS`: ele e o que a documentacao diz, e apagar a
    #     medicao para caber na correcao seria perder a procedencia.
    return {
        "metodo": "POST",
        "url": (base or BASE_PRODUCAO).rstrip("/") + alvo["caminho"],
        "query": ({"sid": sid_do_ato} if sid_do_ato else {}),
        "cabecalhos": {"Content-Type": "application/json",
                       "Accept": "application/json"},
        "corpo": dict(dados),
        "schema": alvo["schema"],
    }


def montar_autenticacao(usuario: str, senha: str, *,
                        url: str | None = None) -> dict[str, Any]:
    """Monta o pedido de token. Nao guarda nem registra a senha em lugar algum."""
    if not str(usuario or "").strip():
        raise SeladorError("O selador exige usuário.")
    if not str(senha or ""):
        raise SeladorError("O selador exige senha.")
    return {
        "metodo": "POST",
        "url": (url or AUTH_PRODUCAO),
        "cabecalhos": {"Content-Type": "application/x-www-form-urlencoded"},
        "formulario": {"username": usuario, "password": senha,
                       "client_id": CLIENT_ID, "grant_type": GRANT_TYPE},
    }
