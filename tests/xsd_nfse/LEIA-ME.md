# Esquemas oficiais da NFS-e — versão 1.01

Cópia, sem alteração, dos XSD do pacote **NFSe-ESQUEMAS_XSD-v1.01-20260209**,
publicado em gov.br/nfse → Biblioteca → Documentação técnica → Documentação atual
(baixado em 24/10/2026). Só entram os arquivos que a casa usa: a DPS, a NFS-e, o
pedido de registro de evento e os tipos de que eles dependem.

`tests/test_nfse.py` valida contra eles a DPS, o pedido de cancelamento e a NFS-e
devolvida pela Sefin falsa. A única adaptação acontece **na leitura**, numa cópia
temporária: os padrões escritos com `^` e `$` (53 em `tiposSimples_v1.01.xsd`) os
perdem, porque em XML Schema o padrão já casa a cadeia inteira e o libxml lê os
dois sinais como letras.

Quando sair leiaute novo, troque a pasta inteira por uma `v1.xx` nova e aponte
`PASTA_DOS_XSD` para ela — e o teste dirá o que o montador da DPS precisa mudar.
