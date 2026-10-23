# Relatório de qualidade — lote de matrículas do Registro de Imóveis

Serventia Extrajudicial de Cidade Exemplo/MA — CNS 000000 — Livro 2, Registro Geral

- **429 matrículas** no lote
- **0** com erro que impede o envio
- **0** duplicadas
- **672** partes extraídas, 506 com CPF/CNPJ validado
- **678** atos (registros e averbações) identificados

## Preenchimento por campo

| Campo | Preenchido | Observação |
|---|---|---|
| `matricula_numero` | 429/429 (100%) | CNM recalculado e conferido pelo dígito verificador |
| `data_registro` | 429/429 (100%) | primeira data legível da ficha |
| `partes_envolvidas` | 417/429 (97%) | extraídas do OCR — conferir antes de considerar definitivas |
| `area` | 397/429 (92%) | ha para imóvel rural, m² para lote urbano |
| `endereco` | 407/429 (94%) | descrição do bloco IMÓVEL |
| `documento_imovel` | 377/429 (87%) | ORIGEM ou REGISTRO ANTERIOR |
| `dados_registro_averbacao` | 338/429 (78%) | atos R- e AV- reconhecidos no texto |
| `teor` | 429/429 (100%) | texto integral, sem corte |
| `folha` | não se aplica | Livro 2 em sistema de fichas: o assento é identificado pela matrícula, não por folha |

## Alertas mais frequentes

- `partes_envolvidas` — 162 matrícula(s)
- `dados_registro_averbacao` — 91 matrícula(s)
- `segmentacao` — 49 matrícula(s)
- `area` — 32 matrícula(s)
- `endereco` — 22 matrícula(s)
- `data_registro` — 10 matrícula(s)
- `teor` — 1 matrícula(s)

## Matrículas que pedem conferência manual antes do envio

| Matrícula | Partes lidas | Segmentação | Páginas |
|---|---|---|---|
| `000000.2.0003442-57` | 1 | 33% | 4 |
| `000000.2.0003444-51` | 3 | 20% | 6 |
| `000000.2.0003446-45` | 2 | 33% | 4 |
| `000000.2.0003447-42` | 3 | 10% | 13 |
| `000000.2.0003449-36` | 1 | 25% | 5 |
| `000000.2.0003451-30` | 4 | 22% | 11 |
| `000000.2.0003455-18` | 1 | 33% | 4 |
| `000000.2.0003456-15` | 4 | 11% | 12 |
| `000000.2.0003457-12` | 2 | 14% | 9 |
| `000000.2.0003458-09` | 3 | 13% | 18 |
| `000000.2.0003459-06` | 1 | 33% | 4 |
| `000000.2.0003463-91` | 0 | 25% | 5 |
| `000000.2.0003464-88` | 0 | 33% | 4 |
| `000000.2.0003466-82` | 3 | 40% | 5 |
| `000000.2.0003467-79` | 0 | 50% | 5 |
| `000000.2.0003469-73` | 1 | 25% | 4 |
| `000000.2.0003479-43` | 1 | 25% | 4 |
| `000000.2.0003483-31` | 2 | 40% | 5 |
| `000000.2.0003484-28` | 5 | 17% | 12 |
| `000000.2.0003489-13` | 1 | 25% | 5 |
| `000000.2.0003495-92` | 1 | 25% | 6 |
| `000000.2.0003504-65` | 4 | 44% | 19 |
| `000000.2.0003505-62` | 1 | 20% | 6 |
| `000000.2.0003507-56` | 0 | 100% | 2 |
| `000000.2.0003508-53` | 3 | 25% | 9 |
| `000000.2.0003510-47` | 1 | 33% | 4 |
| `000000.2.0003511-44` | 1 | 33% | 4 |
| `000000.2.0003512-41` | 2 | 14% | 9 |
| `000000.2.0003513-38` | 1 | 33% | 4 |
| `000000.2.0003515-32` | 1 | 33% | 4 |
| `000000.2.0003516-29` | 0 | 50% | 4 |
| `000000.2.0003517-26` | 2 | 9% | 15 |
| `000000.2.0003527-93` | 1 | 33% | 3 |
| `000000.2.0003529-87` | 0 | 100% | 1 |
| `000000.2.0003533-75` | 2 | 28% | 9 |
| `000000.2.0003534-72` | 1 | 33% | 4 |
| `000000.2.0003540-54` | 3 | 28% | 7 |
| `000000.2.0003542-48` | 2 | 33% | 4 |
| `000000.2.0003547-33` | 3 | 33% | 6 |
| `000000.2.0003548-30` | 3 | 40% | 5 |
| `000000.2.0003549-27` | 3 | 20% | 6 |
| `000000.2.0003550-24` | 0 | 100% | 2 |
| `000000.2.0003556-06` | 5 | 20% | 10 |
| `000000.2.0003567-70` | 3 | 33% | 4 |
| `000000.2.0003582-25` | 0 | 100% | 2 |
| `000000.2.0003589-04` | 0 | 100% | 1 |
| `000000.2.0003591-95` | 3 | 43% | 8 |
| `000000.2.0003633-66` | 2 | 33% | 4 |
| `000000.2.0003646-27` | 3 | 25% | 4 |
| `000000.2.0003683-13` | 4 | 40% | 5 |
| `000000.2.0003699-62` | 0 | 100% | 1 |
| `000000.2.0003802-44` | 0 | 100% | 4 |
| `000000.2.0003923-69` | 0 | 100% | 2 |
