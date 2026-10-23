# Como testar o envio à CRC Nacional em homologação

**Por que este teste importa.** O sistema monta o XML da carga, assina com o
seu certificado A3 e manda pela rede — mas a forma exata do envelope SOAP
(`cargaRegistrosCompleto.cfc`) foi medida **por analogia**, num endpoint irmão
do mesmo servidor (`enviarCertidao.cfc`), porque o WSDL do endereço de carga
nunca foi arquivado publicamente. Só um envio de teste contra o servidor real
confirma se essa forma está certa. Ninguém mais pode confirmar isso — só
quem tem o certificado A3 e acesso à rede da serventia, e isso é a máquina
do balcão.

**Homologação existe exatamente para isto.** O manual da CRC diz, com todas
as letras: em homologação «não será feita a validação da assinatura do
arquivo como um usuário cadastrado». Ou seja: mesmo que a assinatura XML
(WS-Security) não esteja perfeita, a Central ainda deve aceitar a
conexão e responder — o que já prova que o **transporte** funciona, que é o
que falta confirmar.

## O que fazer, passo a passo

1. **Escolha um ou dois assentos de teste, sem importância.** Não precisa
   ser urgente — o objetivo é só ver a Central responder, e não entregar um
   registro de verdade ainda. Se tiver um assento de nascimento, casamento
   ou óbito qualquer, sem matrícula pendente, serve.

2. Abra **Registro Civil → Carga da CRC Nacional** (`/rcpn/crc`).

3. Marque o(s) assento(s) escolhido(s) e clique em **«Montar o arquivo»**.
   Confira que ele aparece sem ficar retido — se ficar, escolha outro.

4. No quadro **«Enviar direto pelo web service, assinado com o A3»**:
   - Em **Ambiente**, deixe **Homologação** (é a opção que já vem marcada,
     e é a certa para este teste — nunca comece por Produção).
   - Em **Driver do certificado A3**, escolha o que aparecer sem o aviso
     «não encontrado nesta máquina».
   - Digite o **PIN** do certificado.
   - Clique em **«Enviar à CRC agora»**.

5. **O que vai acontecer, e o que trazer de volta:**
   - **Se aparecer uma mensagem de sucesso**, com uma resposta da Central —
     ótimo, é exatamente o que este teste queria confirmar. Vá em **«ver o
     histórico de envios»** (link no topo da tela) e me traga o texto
     completo que está dentro de **«ver a resposta da Central»** daquele
     lote — mesmo que pareça só uma confirmação.
   - **Se aparecer uma mensagem dizendo que a CRC recusou** (algo como «A
     CRC recusou a carga: …»), me traga a frase inteira. É informação boa
     também — ela geralmente diz *o quê* recusou.
   - **Se aparecer «Não consegui falar com a CRC em …»**, é problema de
     rede ou de o endereço estar errado, e nada foi enviado; me avise para
     eu investigar o endereço.
   - **Se a tela travar, ficar em branco, ou aparecer um erro de sistema
     em vez das mensagens acima**, é o caso mais importante de todos:
     tire um print e me traga. É esse caso que este teste existe para
     evitar acontecer com um assento de verdade.

6. **Nada disso lavra ato nem consome número.** Montar e enviar não mudam
   nenhum assento no banco — o pior que pode acontecer é a Central recusar
   a carga, que é justamente o que se está testando.

## O que eu faço depois

Com a resposta real da Central (aceite, recusa, ou erro), eu confirmo se o
formato do envelope está certo e, se não estiver, corrijo com a informação
real em mãos — em vez de continuar por analogia. Essa é a diferença entre
"medido por analogia" e "confirmado contra a Central", que o próprio código
já registra (`crc_soap.py`, cabeçalho do módulo).
