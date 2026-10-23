# O QR que abre a consulta do selo — 24/09/2026

> «precisamos implementar um gerador de qr code para substituir o qr code do
> selo por um que leve direto a consulta do selo, nao apenas ao site do
> tribunal. eh so colocar o gerador pra fazer o qr para o
> `https://selo.tjma.jus.br/?selo=`(numero do selo)»
>
> — o oficial

É o **relato #16**, aberto desde 27/08/2026, e ele estava parado esperando uma
coisa: *para qual endereço o QR deve apontar*. A nota do desenvolvimento dizia
«diga o endereço e eu ajusto».

## O endereço que ele passou é o que não funciona

Medido no próprio portal, hoje:

| endereço | o que abre |
|---|---|
| `https://selo.tjma.jus.br/?selo=<SELO>` | **a tela de digitar, vazia** — a URL volta nua |
| `https://selo.tjma.jus.br/#/resumo/<SELO>` | **a consulta pronta** |

**E o porquê está no próprio portal.** Ele é uma aplicação AngularJS que
declara `html5Mode(false)` com `hashPrefix("")`: as rotas são de **hash**, e
são quatro —

```
#/resumo/:selo      #/agregador/:selo/      #/invalido/:selo      #/tabela-custas
```

— e o controlador `ResumoSeloValidadoCtrl` lê `$routeParams.selo` e chama
`consultaSelo(...)`. Query que venha **fora** do hash a aplicação descarta.
Era a **forma** que estava errada, e não a ideia.

## Conferido em dois selos reais desta casa

| selo | o que a consulta abriu |
|---|---|
| `CERTID000000MLF3KFMARL4M5E98` — certidão de casamento, RCPN, hoje às 14h04, pela escrevente | item **14.5.1**, Livro B-6, termo 621, folha 37, as partes, e o total de **R$ 53,58** |
| `MATRIC000000FQ2IF3MJ7KUI7600` — matrícula **4020** do RI, hoje às 14h55, pela escrevente | item **16.2**, protocolo 11.565, e o total de **R$ 102,15** |

As duas trazem também o cartório e o delegatário. É isso que quem recebe o
papel vê ao apontar a câmera.

## Uma conclusão desta casa caiu — e a medição que a sustentava fica

Em 27/08 a outra passada fez um trabalho bonito: **decodificou à mão** um QR
real do E-Ofício (grade lida da imagem, máscara 3, nível Q, blocos de correção
desintercalados) e achou `MDGaPtZuqUKD4FtmC82CK5al` — um **token de 24
caracteres**, igual ao `strvalorQRCode` que o acervo guarda em **25.642 dos
26.130** selos. **Isso é verdade e continua valendo**: é o que explica o QR do
E-Ofício.

**O que não se sustentou foi a conclusão tirada dali** — «o portal não procura
pelo número, procura pelo token; inventar `?selo=` nunca ia funcionar». O
portal procura pelo número, e a prova está na tabela acima.

E há um segundo argumento, que nem depende do portal: **token cru dentro de um
QR não é link**. A câmera lê vinte e quatro caracteres e não tem o que abrir. O
QR do E-Ofício nunca levou ninguém à consulta; ele servia ao leitor do próprio
Tribunal.

## O que mudou no sistema

| | |
|---|---|
| `notas_selo.MODELO_PADRAO` | passou de `?selo={selo}` para `#/resumo/{selo}`, com a medição no cabeçalho |
| `notas_selo.marca_do_selo` | deixou de preferir o token |
| `notas_selo.token_do_qr` | **apagada** — e a coluna `sd_selos.qr_token` fica, porque dado do acervo é dado |
| `notas_web`, `rg_web`, `atribuicoes_web`, `rc_certidao_inteiro_teor` | as **seis** chamadas que punham o token no QR |
| `settings.etiqueta_qr_url` (produção) | trocada: ela guardava a forma antiga, e **a configuração ganha do padrão** |

**Hoje nada muda no papel por causa do token, e isso está medido**:
`sd_selos.qr_token` está vazia em **26.464 de 26.464** — o caminho do token
nunca chegou a rodar nesta casa. O que se fecha é a porta de amanhã: no dia em
que a carga o trouxesse, **todos** os papéis passariam a imprimir um QR que a
câmera lê e não abre.

**E a configuração precisava ser trocada à mão**, porque o código é o piso e a
tabela é o ajuste: sem isso, a etiqueta continuaria com o endereço velho mesmo
depois de a versão subir. `tools/atualizar_endereco_do_qr.py` faz isso — só
mede por padrão, e **recusa** se o valor gravado não for exatamente a forma
antiga, porque escolha de gente não se apaga por descuido.

## Onde o QR aparece, e todos passam pelo mesmo gerador

| papel | de onde sai o QR |
|---|---|
| etiqueta de reconhecimento de firma e de autenticação | `notas_selo.marca_do_selo` (SVG) |
| etiqueta do RCPJ/RTD, e a dos selos externos | `notas_selo.marca_do_selo` |
| carimbo das quatro certidões | `ri_odt.png_do_qr_do_selo` → `selo_no_papel.link_de_consulta` |
| certidão do RCPN nas três espécies (molde `.odt`) | `rc_certidao_odt._png_do_qr` |
| certidão de inteiro teor do RCPN | `rc_certidao_inteiro_teor._png_do_qr` |
| teor do livro do RTDPJ (imagem) | `notas_selo.png` |

Todos leem `notas_selo.MODELO_PADRAO` — direta ou indiretamente. **Um gerador
só na casa** era o que já existia; o que mudou foi para onde ele aponta.

## A prova é decodificar, e ela já existia

`tests/test_etiqueta_reconhecimento.py` desenha o QR do SVG numa grade,
amplia para **203 e 300 DPI** (as duas resoluções da térmica) e **decodifica
com o OpenCV**, exigindo que saia exatamente o endereço esperado. É a prova
de que o papel leva o que se diz que ele leva — e agora ela cobra o endereço
da consulta.

E `tests/test_qr_do_selo.py` ganhou a varredura que fecha a porta: **nenhuma
tela pode voltar a pôr o token dentro do QR**. Sem ela, o defeito só
apareceria no balcão, com o papel na mão.
