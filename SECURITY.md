# Política de segurança

O Cartório Gestão guarda atos registrais e notariais, dados de pessoas e o
caixa de uma serventia. Uma falha de segurança aqui pode expor quem foi ao
balcão. Por isso, falha de segurança **não** se relata em *issue* pública.

## Como relatar uma falha

1. **Em particular.** Use o botão **«Report a vulnerability»** da aba
   **Security** deste repositório, ou escreva para
   **[cartoriogestao.dev@proton.me](mailto:cartoriogestao.dev@proton.me)**
   com o assunto «Segurança».
2. **Diga o que precisamos para reproduzir:** a versão (`VERSAO.txt`), a
   tela ou o módulo, o passo a passo e o que acontece. Uma prova de conceito
   ajuda.
3. **Nunca mande dado real** de serventia ou de pessoa: nome, CPF, CNS,
   matrícula, selo, senha, chave ou cópia de banco. Use dados fictícios.

Não abra *issue* nem *pull request* público sobre a falha antes de ela estar
corrigida.

## O que acontece depois

- Confirmamos o recebimento assim que lermos a mensagem.
- Conferimos se a falha existe e o quanto ela alcança.
- A correção entra por *pull request*, e a instalação a recebe num pacote de
  atualização assinado.
- Combinamos com você quando a falha pode ser contada em público. Se quiser,
  seu nome vai no registro da correção.

Este projeto é mantido por uma serventia, e não por uma empresa: não há plantão
nem prazo garantido. Falha que exponha dado de pessoa ou permita praticar ato
passa à frente de todo o resto.

## Versões que recebem correção

| Versão | Correção de segurança |
|---|---|
| A última publicada (etiqueta `vX.Y.Z` mais recente) | sim |
| Anteriores | não — atualize para a última |

O ramo `main` traz o que já foi juntado e ainda não virou versão.

## O que está no alcance

- O código deste repositório: telas, módulos, rotinas, instalador e ferramentas.
- A forma como o sistema guarda e usa credenciais das Centrais, do selador e da
  IA (sempre fora do banco).
- A conferência da assinatura dos pacotes de atualização.

Fora do alcance: os sistemas das Centrais, do Tribunal e dos provedores (relate
a eles), e a configuração de uma instalação que não siga
[`docs/SEGURANCA_IMPLANTACAO.md`](docs/SEGURANCA_IMPLANTACAO.md).

## Como as atualizações se protegem

Todo pacote de atualização (`.cgu`) traz o SHA-256 de cada arquivo e é assinado
com uma chave Ed25519. A instalação só aceita o pacote assinado por uma chave
cadastrada **nela** (`chaves_de_atualizacao.json`, na pasta do programa).
O código público não traz chave de serventia nenhuma. A chave privada fica com
quem responde pela instalação, fora do servidor e de pasta compartilhada. Ver
[`docs/SEGURANCA_IMPLANTACAO.md`](docs/SEGURANCA_IMPLANTACAO.md), §5.
