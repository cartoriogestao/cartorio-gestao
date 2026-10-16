# As decisões do sistema

Este diretório reúne as decisões que moldaram o Cartório Gestão e que valem
para qualquer serventia que o instale e para quem programar nele. São regras de
domínio, com o fundamento legal; regras de desenho que evitam defeitos já
vistos; as armadilhas conhecidas dos contratos com as Centrais nacionais; e o
que o sistema deliberadamente não faz.

Ficou de fora o diário da serventia de origem: dados reais, contagens do
acervo, incidentes e decisões que só valem para ela.

Cada decisão tem o mesmo formato: **Regra** (o que o sistema faz), **Por quê**
(o risco que ela evita), **Fundamento** (a norma, quando houver) e **No
código** (onde ela mora).

> **Normas estaduais.** O sistema nasceu no Maranhão. Regras que vêm do Código
> de Normas da Corregedoria do TJMA, da tabela de emolumentos ou do selador
> daquele estado estão marcadas como *norma estadual*. Em outro estado,
> confira a norma local antes de usar.

| Documento | Decisões | O que cobre |
|---|---:|---|
| [Arquitetura e método](08_arquitetura_e_metodo.md) | 33 | Transação e banco, telas e domínio, fonte única, atos e papéis assinados, testes de guarda, como medir antes de decidir, atualização segura |
| [Núcleo: livros, selo, caixa](01_nucleo_selo_caixa.md) | 28 | Livros e numeração, custas e gratuidade, selo eletrônico, carimbo e QR, protocolo e caixa, assinatura digital |
| [Modelos, IA e privacidade](02_modelos_ia_privacidade.md) | 30 | Papéis e modelos, telas e menu, processos, importação de acervo, ajuda com IA, LGPD e alerta de fraude |
| [Registro de Imóveis](03_registro_de_imoveis.md) | 38 | Matrícula e atos, prenotação, CNIB, usucapião, retificação, certidões, emolumentos, DOI |
| [ONR e Tabelionato de Notas](04_onr_e_notas.md) | 50 | API do ONR, Indicador Real, Next Cloud SAS; livro de Notas, selo da escritura, CCN |
| [Tabelionato de Protesto](05_protesto.md) | 38 | Ciclo do título, sustação, certidão, arquivos da CRA, CENPROT e Resolve |
| [Registro Civil](06_registro_civil.md) | 44 | Assento, termo e certidão, selo do civil, habilitação, retificação, comunicações obrigatórias, IBGE |
| [Centrais do Registro Civil e RTD/PJ](07_centrais_rcpn_rtdpj.md) | 46 | Base comum das integrações, SIRC, CRC, ON-RCPN, ONRTDPJ, migração de acervo |

Para começar a programar, veja também [`../ARQUITETURA.md`](../ARQUITETURA.md) e
[`../AGENTES.md`](../AGENTES.md).
