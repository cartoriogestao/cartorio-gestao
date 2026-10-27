# Matriz de papéis da casa

> Gerada na Fase 0 do plano de modelos. Fonte de verdade: `modelos_da_casa.CATALOGO`. Não lista minutas (`nt_modelos`) nem documentos avulsos do E-Ofício (`/rcpn/modelos`).

Atualizado em 2026-09-19 10:40 (America/Fortaleza).
**34 papéis** no catálogo.

| chave | atribuição | nome | tipo | módulo.constante | formato |
|---|---|---|---|---|---|
| `RI_CABECALHO` | Registro de Imóveis | Cabeçalho dos documentos | TEXTO | `ri_odt.MODELO_CABECALHO_PADRAO` | JINJA |
| `RI_FICHA` | Registro de Imóveis | Ficha da matrícula | MOLDE_ODT — Ficha da matrícula em XML/ODT (ri_odt) | `ri_odt.MODELO_FICHA_PADRAO` | JINJA |
| `RI_CERTIDAO` | Registro de Imóveis | Certidão — o molde | MOLDE_ODT — Molde comum das certidões RI (ri_odt) | `ri_odt.MODELO_CERTIDAO_PADRAO` | JINJA |
| `RI_CERTIDAO_INTEIRO_TEOR` | Registro de Imóveis | Certidão — o miolo do inteiro teor | TEXTO — Miolo — não é o molde inteiro | `ri_odt.MIOLO_CERTIDAO_INTEIRO_TEOR` | JINJA |
| `RI_CERTIDAO_ONUS` | Registro de Imóveis | Certidão — o miolo dos ônus | TEXTO — Miolo — não é o molde inteiro | `ri_odt.MIOLO_CERTIDAO_ONUS` | JINJA |
| `RI_CERTIDAO_PROPRIEDADE` | Registro de Imóveis | Certidão — o miolo da propriedade | TEXTO — Miolo — não é o molde inteiro | `ri_odt.MIOLO_CERTIDAO_PROPRIEDADE` | JINJA |
| `RI_NOTA` | Registro de Imóveis | Nota devolutiva | TEXTO | `ri_odt.MODELO_NOTA_PADRAO` | JINJA |
| `RI_PRENOTACAO` | Registro de Imóveis | Comprovante de prenotação | TEXTO | `ri_web.MODELO_PRENOTACAO` | JINJA |
| `RI_LIVRO3_CERTIDAO` | Registro de Imóveis | Certidão do Livro 3 Auxiliar | TEXTO | `atrib_certidao.MODELO_CERTIDAO_LIVRO3` | CHAVES |
| `CAIXA_RECIBO` | Caixa e protocolo | Recibo | TEXTO | `caixa_web.MODELO_RECIBO` | JINJA |
| `CAIXA_ORCAMENTO` | Caixa e protocolo | Orçamento | TEXTO | `caixa_web.MODELO_ORCAMENTO` | JINJA |
| `CAIXA_RECEPCAO` | Caixa e protocolo | Comprovante de recepção | TEXTO | `caixa_web.MODELO_RECEPCAO` | JINJA |
| `CAIXA_EXIGENCIA` | Caixa e protocolo | Nota de exigência — protocolo geral | TEXTO | `caixa_exigencia.MODELO_NOTA_DE_EXIGENCIA` | JINJA |
| `NOTAS_TRASLADO` | Tabelionato de Notas | Traslado | TEXTO | `notas_web.MODELO_TRASLADO` | JINJA |
| `NOTAS_TERMO_LIVRO` | Tabelionato de Notas | Termo do livro | TEXTO | `notas_web.MODELO_TERMO_LIVRO` | JINJA |
| `NOTAS_CARTAO_FICHA` | Tabelionato de Notas | Cartão de autógrafo | TEXTO | `notas_web.MODELO_CARTAO_FICHA` | JINJA |
| `RCPJ_CERTIDAO` | RCPJ e RTD | Certidão de inteiro teor — RCPJ (texto congelado) | TEXTO — Texto congelado em at_certidoes na emissão | `atrib_certidao.MODELO_CERTIDAO_RCPJ_RTD` | CHAVES |
| `RTD_CERTIDAO` | RCPJ e RTD | Certidão de inteiro teor — RTD (texto congelado) | TEXTO — Texto congelado em at_certidoes na emissão | `atrib_certidao.MODELO_CERTIDAO_RCPJ_RTD` | CHAVES |
| `RCPJ_TEOR_AVERBACAO` | RCPJ e RTD | Teor de averbação — RCPJ | TEXTO | `rg_teor_rtdpj.MODELO_RCPJ_TEOR_AVERBACAO` | CHAVES |
| `RCPJ_TEOR_REGISTRO` | RCPJ e RTD | Teor de registro — RCPJ | TEXTO | `rg_teor_rtdpj.MODELO_RCPJ_TEOR_REGISTRO` | CHAVES |
| `RTD_TEOR_AVERBACAO` | RCPJ e RTD | Teor de averbação — RTD | TEXTO | `rg_teor_rtdpj.MODELO_RTD_TEOR_AVERBACAO` | CHAVES |
| `RTD_TEOR_REGISTRO` | RCPJ e RTD | Teor de registro — RTD | TEXTO | `rg_teor_rtdpj.MODELO_RTD_TEOR_REGISTRO` | CHAVES |
| `RCPJ_CERTIDAO_CAPA` | RCPJ e RTD | Certidão PDF — capa RCPJ | TEXTO — Fragmento de capa PDF | `rg_certidao_pdf.MODELO_RCPJ_CERTIDAO_CAPA` | CHAVES |
| `RTD_CERTIDAO_CAPA` | RCPJ e RTD | Certidão PDF — capa RTD | TEXTO — Fragmento de capa PDF | `rg_certidao_pdf.MODELO_RTD_CERTIDAO_CAPA` | CHAVES |
| `RCPJ_CERTIDAO_FAIXA` | RCPJ e RTD | Certidão PDF — faixa RCPJ | TEXTO — Fragmento de faixa PDF | `rg_certidao_pdf.MODELO_RCPJ_CERTIDAO_FAIXA` | CHAVES |
| `RTD_CERTIDAO_FAIXA` | RCPJ e RTD | Certidão PDF — faixa RTD | TEXTO — Fragmento de faixa PDF | `rg_certidao_pdf.MODELO_RTD_CERTIDAO_FAIXA` | CHAVES |
| `RC_TERMO_NASCIMENTO` | Registro Civil das Pessoas Naturais | Termo de nascimento | TEXTO — Marcadores {chave} do livro | `rc_modelos_do_livro.TERMO_NASCIMENTO` | CHAVES |
| `RC_TERMO_CASAMENTO` | Registro Civil das Pessoas Naturais | Termo de casamento | TEXTO — Marcadores {chave} do livro | `rc_modelos_do_livro.TERMO_CASAMENTO` | CHAVES |
| `PT_TERMO_PROTESTO` | Protesto | Termo do registro de protesto | TEXTO | `protesto_termo.TERMO_DO_PROTESTO` | CHAVES |
| `PT_INSTRUMENTO_PROTESTO` | Protesto | Instrumento de protesto | TEXTO | `protesto_instrumento.INSTRUMENTO_DE_PROTESTO` | CHAVES |
| `PT_CERTIDAO_NEGATIVA` | Protesto | Certidão negativa de protesto | TEXTO | `protesto_certidao.MODELO_CERTIDAO_NEGATIVA` | CHAVES |
| `PT_CERTIDAO_POSITIVA` | Protesto | Certidão positiva de protesto | TEXTO | `protesto_certidao.MODELO_CERTIDAO_POSITIVA` | CHAVES |
| `PT_CERTIDAO_CANCELAMENTO` | Protesto | Certidão de protestos cancelados | TEXTO | `protesto_certidao.MODELO_CERTIDAO_CANCELAMENTO` | CHAVES |
| `RC_TERMO_OBITO` | Registro Civil das Pessoas Naturais | Termo de óbito | TEXTO — Marcadores {chave} do livro | `rc_modelos_do_livro.TERMO_OBITO` | CHAVES |
| `RC_TERMO_LIVRO_E` | Registro Civil das Pessoas Naturais | Termo do Livro E | TEXTO — Marcadores {chave} do livro | `rc_modelos_do_livro.TERMO_LIVRO_E` | CHAVES |

## Fora deste catálogo (de propósito)

| o quê | onde | tipo |
|---|---|---|
| Minutas de escritura/procuração/ata | `nt_modelos` + `notas_modelos.py` | `MINUTA_ATO` |
| Modelos de atos do RI (índice) | `ri_modelos_atos` / tela `/registro-imoveis/modelos-atos` | `MINUTA_ATO` |
| Documentos avulsos RCPN (E-Ofício) | `/rcpn/modelos` (`rc_modelos_livres*`) | `DOC_AVULSO` |
| Cabeçalho RCPN (timbre normativo) | `rc_cabecalho.py` | `MONTADO_POR_CAMPO` (fora de texto livre, decisão do oficial) |

## Override maduro na produção (sagrado)

- `mo_elementos`: NOTAS / `NOTAS_CARTAO_FICHA` / CORPO — oficial, 07/09/2026.
- `mo_modelos` / `ri_modelos` / `mo_moldes`: 0 linhas nesta casa.

## Pendências e exclusões (Fase 1)

### Já cobertos fora do CATALOGO de texto (não duplicar)

| o quê | onde | tipo | status |
|---|---|---|---|
| Papel ODT certidão nascimento | `modelos_moldes.MOLDES` → `RC_MOLDE_NASCIMENTO` + `modelos/certidao_nascimento_modelo.odt` | `MOLDE_ODT` | Completo no submódulo de moldes (UI `/modelos`) |
| Papel ODT certidão casamento | `RC_MOLDE_CASAMENTO` | `MOLDE_ODT` | Completo |
| Papel ODT certidão óbito | `RC_MOLDE_OBITO` | `MOLDE_ODT` | Completo |

Os moldes ODT do RCPN **não entram** em `modelos_da_casa.CATALOGO` porque `padrao_de` exige texto editável; o armazém certo é `mo_moldes` / `modelos_moldes.py` (mesma tela `/modelos`).

### Constantes chamadas «MODELO» que NÃO são papel do catálogo

| constante | motivo da exclusão |
|---|---|
| `notas_selo.MODELO_PADRAO` | URL do QR do selo, não papel (já documentado nos testes) |
| `notas_web.MODELO_TRASLADO_CABECALHO` | Fragmento do traslado, não papel à parte |
| `rc_termo.MODELO_TERMO_*` | Legado; os termos vivos no catálogo são `rc_modelos_do_livro.TERMO_*` |
| `atrib_certidao.MODELO_CERTIDAO_RCPJ_RTD_SO_AVERBACOES` | Variante de emissão; chave pai já no catálogo |

### Minutas (`MINUTA_ATO`) — índice, não catálogo de papel

Ver [INDEX_MINUTAS_ATO.md](INDEX_MINUTAS_ATO.md). Contagens medidas na produção nesta data.

### Sem piso de texto/ODT encontrado (não inventar prosa)

| candidato | nota |
|---|---|
| Edital de habilitação / proclamas | Há montagem em `habilitacao_web._modelo_do_edital` — revisar se vira chave só quando houver constante estável de piso |
| Edital de protesto (CENPROT) | Cobertura por testes/`protesto_*`; sem constante `MODELO_*` órfã medida nesta passada |
| Firmas além do cartão | `NOTAS_CARTAO_FICHA` já no catálogo (+ override maduro em `mo_elementos`) |

## Legado (Fase 2) — já na casa

- /registro-imoveis/modelos → redirect para /modelos (não grava em 
i_modelos).
- Trabalho novo de ajuste: mo_elementos / mo_moldes apenas.
- Cabeçalho RCPN permanece em 
c_cabecalho.py (fora de texto livre).

## Aceite (Fases 2–4) — 19/09/2026

1. Papéis emitíveis no CATALOGO (34) ou exclusão/paralelo documentado nesta matriz (moldes ODT, minutas, avulsos).
2. Pergunta «onde mudo X?» → /modelos (papéis) ou módulo próprio (minuta/avulso), com rótulos distintos no menu RCPN.
3. Vírgula da casa sem pacote: override em mo_elementos/mo_moldes; versão só para mudar piso.
4. Docs alinhadas a len(CATALOGO) = 34 + inventário exit 0.
5. 	ests/test_modelos_tipagem_fase0.py + 	est_modelos_da_casa.py verdes; cartão NOTAS_CARTAO_FICHA intacto (oficial).

