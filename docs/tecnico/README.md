# Documentação técnica do Cartório Gestão

Estes documentos são o diário técnico da construção do sistema: como cada
formato das Centrais foi medido (CRA, CENPROT, IBGE, CRC, SIRC, ONR, ON-RCPN),
por que cada regra existe, o que se tentou e não deu certo, e os roteiros de
cada versão. Servem a quem vai **implantar** o sistema em outra serventia ou
**consertar** um defeito e precisa saber por que o código é como é.

## Como ler

- **Comece pelo assunto, não pela data.** Os nomes dos arquivos dizem o tema:
  `LAYOUT_*` e `*_MEDIDO` são formatos de arquivo medidos em dados reais;
  `O_*_CONSTRUIDO` e `A_*_CONSTRUIDA` explicam um módulo; `ROTEIRO_3.x.y` é o
  que cada versão trouxe e como foi conferida.
- **Muita coisa foi escrita para uma serventia do Maranhão** (Código de Normas
  do TJMA, selo eletrônico do TJMA, CRA-MA). O que é norma estadual vale para
  o MA; a lógica de medição e as decisões de desenho valem para qualquer casa.
- As decisões que valem para qualquer cartório estão resumidas em
  [`../decisoes/`](../decisoes/); o manual de uso em [`../MANUAL.md`](../MANUAL.md).

## O que foi trocado nesta cópia

A documentação original tem dado real da serventia que a escreveu. Antes de
publicar, ela passou por uma troca automática e por leitura humana:

| No original | Aqui |
|---|---|
| nomes de clientes, partes, falecidos, devedores | `Pessoa Exemplo` / `PESSOA EXEMPLO` |
| nomes da equipe | o papel (`o oficial`, `a escrevente`) ou um login fictício |
| oficiais anteriores | `titular anterior` |
| cidade da serventia | `Cidade Exemplo` |
| CNS, CPF, CNPJ, telefone, e-mail, endereço | fictícios (`000000`, `000.000.001-91`, `00.000.001/0000-55`, `contato@exemplo.invalid`) |
| caminhos de perfil do Windows, servidores | `<usuario>`, `exemplo.invalid` |

**Os números (de matrícula, protocolo, selo, quantidades medidas) ficaram**,
porque são eles que sustentam as conclusões. Os códigos de selo trazem o CNS
trocado e por isso não abrem consulta nenhuma. Ficou de fora o diário da
conferência diária, que é dado e não documento, e as planilhas, textos de OCR
e arquivos de teste da Central.

Por causa das trocas, uma ou outra frase que falava de um caractere ou de um
dígito do dado real pode ter perdido o exemplo. Se algo não fizer sentido,
abra uma *issue*.
