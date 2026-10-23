# O selador liga — versão 3.5.1

**24 de agosto de 2026.** O uso do sistema segue suspenso; nada disto foi aplicado.

Faltava o transporte. O contrato (181 endpoints) estava pronto desde a 3.4.1, a
configuração desde a 3.5.0. Agora existe a peça que de fato fala com o selador — e ela
é pequena, porque quem decide um selo é o contrato e a configuração; o transporte só
leva.

## Sem dependência nova

`http.client` e `ssl`, da biblioteca padrão. O sistema é instalado por `.cmd` em
máquina de serventia, e uma dependência a mais é um jeito a mais de a instalação
falhar num sábado.

## A decisão que mudou tudo: fixar o certificado, não desligar a validação

O selador desta casa é `https://192.0.2.23:443` — máquina da rede local. Máquina de
rede local não tem certificado assinado por autoridade; tem certificado próprio.
Validar pela cadeia falha sempre.

O caminho fácil seria desligar a validação. Ele é ruim: qualquer máquina da rede
passaria a poder se passar pelo selador e **receber a senha da serventia**.

O caminho certo é **fixar** o certificado. Na primeira conexão o sistema mostra a
impressão digital, você confere com quem instalou o selador, confirma — e daí em diante
só aquele certificado serve. Isso é **mais forte** que validar cadeia, não menos: nem
uma autoridade certificadora comprometida abriria a porta.

**Sem certificado conferido, o sistema recusa conectar** e diz como conferir. A senha
não sai da máquina.

### E isto não é preciosismo — provou-se sozinho

Rodando o teste da tela **fora do cartório**, o endereço `192.0.2.23` **respondeu**.
Apresentou um certificado com `commonName=default.domain`, que não é o selador de
ninguém: é outra máquina, na rede onde o teste rodava.

Endereço de rede privada é assim — em cada rede ele é outro computador. Sem a fixação,
bastaria o computador estar na rede errada para a senha da serventia ir para um
estranho. Com ela, nada foi enviado.

## O bug que o teste pegou antes de existir

Eu havia deixado a autenticação apontada para o Keycloak do Tribunal, na internet.
Numa casa que sela num aparelho da rede local isso faz duas coisas ruins: **manda a
senha da serventia para fora** e **trava** esperando resposta de um servidor que aquela
máquina talvez nem alcance.

O teste travou. O selo nunca voltava.

Agora o endereço de autenticação é próprio: vazio significa "no mesmo lugar do selador,
em `/auth`" — o arranjo normal de appliance —, e o endereço de fábrica só entra quando
a própria base é a de fábrica. Há três testes guardando isso.

## O SID, funcionando

No acervo do E-Ofício há **1.304 selos que nunca foram usados** — 5% de todos — e
apenas **cinco** foram cancelados. É o rastro de quem repetiu a chamada depois de um
erro de rede: cada tentativa gerou selo novo, cobrado, e o anterior ficou órfão.

Duas coisas fecham esse buraco, e as duas estão aqui:

1. **O SID.** Determinístico a partir do ato, nunca da hora. O mesmo ato pedido duas
   vezes devolve o **mesmo selo** — e o segundo pedido nem chega a sair, porque o razão
   já o tem. Há teste.
2. **O razão `sd_selos`.** Todo selo obtido entra **na hora em que chega**, antes de o
   ato terminar. Se o ato falhar depois, o selo aparece na tela de **selo obtido e não
   usado** em vez de sumir. É a tela que faltava no E-Ofício — lá havia 1.304 desses e
   ninguém sabia, porque não havia onde olhar.

E o cancelamento de selo **exige motivo escrito**. Dos 79 cancelamentos do acervo
antigo, nenhum tem motivo gravado, e é por isso que hoje ninguém sabe explicá-los.

## O que mais o cliente protege

**O balcão.** Toda chamada tem prazo curto — 20 segundos — e prazo esgotado vira frase
de balcão ("se ele é uma máquina da rede local, confira se ela está ligada e se este
computador está na mesma rede"), não travamento nem *traceback*.

**A repetição segura.** Falha de rede repete; recusa não. Um 400 repetido dez vezes
continua 400, e cada tentativa seria uma chance de gerar selo. Como o SID vai na
consulta, repetir depois de falha de rede é seguro por construção.

**O token.** Guardado só em memória, e só enquanto vale, com dez segundos de folga —
token que vence entre o pedido e a chegada devolve 401 no meio do atendimento. Token em
disco é senha em disco com outro nome. Se vencer mesmo assim, o cliente reautentica
sozinho e o balcão não vê. Há teste para os três casos.

## O botão que responde "por que não está selando?"

A tela do selador ganhou **Testar a conexão**: confere rede, certificado e credencial,
em três passos, **sem selar nada** — e diz em qual passo parou. É o que responde a
pergunta antes de o balcão descobrir a resposta com a parte na frente.

## Como isto foi testado

Não com `mock`. O difícil aqui é o transporte, e `mock` não exercita aperto de mão TLS,
impressão digital, token vencido nem prazo esgotado.

Há um **selador de mentira com TLS de verdade** (`tests/selador_falso.py`): sobe numa
porta local com certificado próprio, devolve o mesmo selo para o mesmo SID, sabe
recusar com 400, sabe devolver 401 uma vez. São **27 testes** contra ele, mais 21 da
tela e 33 da configuração — 81 no transporte e na configuração, que se somam aos 172
do contrato: **253 no selador**, e **1.094 no sistema inteiro**.

## O que ainda falta, e continua sendo seu

| Falta | Onde você vê |
|---|---|
| **Usuário e senha** | já estão lá — o botão "importar do E-Ofício" traz sozinho |
| **URL de homologação** | E-Ofício, tela Selador — Propriedades |
| **Conferir a impressão digital** do certificado | tela do selador, botão "Ver a impressão digital" — e confirmar com quem instalou o selador |

O último item é o único que ninguém pode fazer por você: conferir que a máquina que
responde é mesmo a sua.

## Uma observação sobre o E-Ofício, e ela é de segurança

Procurei na máquina o certificado do selador — em `.cer`, `.crt`, `.pem`, em
*truststore* — e **não há nenhum**. Ao mesmo tempo, o `e-oficio-ma.exe` contém o gancho
`ServerCertificateValidationCallback`, que no .NET serve exatamente para substituir a
validação de certificado.

Não desmontei o programa, então isto é **leitura de indício e não prova**: sem
certificado guardado em lugar nenhum, com um selador de certificado próprio, e com esse
gancho presente, a conclusão quase inevitável é que **o E-Ofício aceita qualquer
certificado** que responda naquele endereço.

Se for isso, o sistema novo é mais rigoroso que o antigo justamente no ponto em que o
antigo é frouxo — e o preço disso é o passo a mais que você vai dar uma única vez:
conferir a impressão digital.
