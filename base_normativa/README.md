# A base normativa

Os textos das normas que a atividade desta casa aplica: o Código de Normas do
TJMA, o Código Nacional de Normas do CNJ e as leis federais e estaduais
pertinentes ao Registro Civil, às Notas, ao Registro de Imóveis, ao Protesto,
ao RTD e ao RCPJ.

Pedido do oficial (05/11/2026): abastecer os agentes de IA com a documentação
pertinente, e fazer disso parte do repositório que é clonado («vamos fazer
parte do repositório do github que é clonado»). Esta pasta é a primeira
etapa — **a seleção e a ingestão**. O índice e a ferramenta `consultar_norma`
permitem ler artigos completos. A ligação comum aos dois transportes de IA e
a retomada da qualificação foram acrescentadas em 06/11/2026, a pedido do oficial.
O acervo instalado contém 40 normas e 7.003 artigos; isso não representa toda
a legislação brasileira nem certifica atualização permanente das fontes.

As análises recebem somente os artigos pertinentes, com limite de contexto.
OCR e transcrição continuam literais, sem inserir interpretação jurídica no
documento. A qualificação confere a existência e o trecho das referências;
fonte ausente, redação original ou transcrição não localizada exige confirmação
humana na fonte oficial. O rascunho negativo usa o modelo `RI_NOTA` da própria
instalação, sem reservar número, assinar ou alterar a prenotação.

Em 06/11/2026 também entraram as Leis 8.629/1993, 4.504/1964, 5.868/1972,
10.267/2001, 8.009/1990 e 11.441/2007, do mesmo commit do ctresb/leis.
`ingestao_20261106.json` registra a origem, o commit e o SHA-256 desses arquivos.

**Um arquivo por norma**, e não por artigo: o pacote de atualização tem teto
de arquivos (`update_manager.MAX_FILES`), e o índice por artigo se monta na
memória.

## Os textos não são protegidos por direito autoral

Texto de lei, de decreto e de provimento é ato oficial (Lei 9.610/1998, art.
8º, I). As leis vêm do repositório público
[ctresb/leis](https://github.com/ctresb/leis) (scripts sob licença MIT), que
converte as publicações oficiais para Markdown. Cada arquivo traz no cabeçalho
o link da fonte oficial.

**Antes de citar, confira na fonte oficial.** A conversão é automática; as
conferências feitas estão abaixo.

## O que está aqui

### Códigos de normas

| Arquivo | Norma | Origem |
|---|---|---|
| `estadual_ma/codigo_de_normas_tjma.md` | Código de Normas da Corregedoria Geral do Foro Extrajudicial do Maranhão — Provimento COGEX/TJMA nº 28/2026 (arts. 1º a 1.020) | PDF publicado no DJe do TJMA, convertido em 05/11/2026 |
| `nacional/codigo_nacional_de_normas_cnj.md` | Código Nacional de Normas — Foro Extrajudicial, Provimento CNJ nº 149/2023, texto compilado sem a redação revogada | <https://atos.cnj.jus.br/atos/detalhar/5243>, convertido em 05/11/2026 |

O que se fez nos dois, sem mexer no texto das normas:

- **TJMA:** saiu o sumário (que a conversão escrevera como títulos, repetindo
  a estrutura inteira antes do texto) e saíram as 243 marcas «Página N de 248»
  que caíam no meio dos artigos. A capa do Malote Digital e o rodapé do DJe já
  tinham saído na conversão.
- **Os dois:** o texto do provimento que institui o código ficou sob título
  próprio, e os artigos do provimento perderam a marca de artigo («Art. 1º
  (do Provimento)»). Sem isso, o «Art. 1º» do provimento e o «Art. 1º» do
  código seriam dois artigos com o mesmo número.
- **CNN:** a lista de provimentos que alteraram o código e da legislação
  citada, que abre a página do CNJ, ficou sob o título «Alterações e
  legislação citada».

### Leis federais (`federal/`)

Vindas do ctresb/leis, commit `c9f21b4` (02/11/2026). «Compilado» é o texto
vigente, com as alterações; «original» é o texto como foi publicado, **sem as
alterações posteriores** — para a redação vigente, confira a fonte.

| Arquivo | Norma | Texto |
|---|---|---|
| `lei-6015-1973-12-31.md` | Lei 6.015/1973 — Registros Públicos (LRP) | compilado |
| `lei-8935-1994-11-18.md` | Lei 8.935/1994 — Lei dos Notários e Registradores | compilado |
| `lei-9492-1997-09-10.md` | Lei 9.492/1997 — Protesto | compilado |
| `lei-7433-1985-12-18.md` | Lei 7.433/1985 — Requisitos da escritura pública | compilado |
| `dec-93240-1986-09-09.md` | Decreto 93.240/1986 — Regulamenta a Lei 7.433 | original |
| `lei-10169-2000-12-29.md` | Lei 10.169/2000 — Normas gerais de emolumentos | compilado |
| `lei-14382-2022-06-27.md` | Lei 14.382/2022 — SERP | original |
| `lei-13465-2017-07-11.md` | Lei 13.465/2017 — REURB | compilado |
| `lei-9514-1997-11-20.md` | Lei 9.514/1997 — Alienação fiduciária de imóvel | compilado |
| `lei-6766-1979-12-19.md` | Lei 6.766/1979 — Parcelamento do solo urbano | compilado |
| `lei-4591-1964-12-16.md` | Lei 4.591/1964 — Condomínio e incorporação | compilado |
| `del-167-1967-02-14.md` | Decreto-Lei 167/1967 — Cédulas de crédito rural | compilado |
| `del-413-1969-01-09.md` | Decreto-Lei 413/1969 — Cédulas de crédito industrial | original |
| `lei-6840-1980-11-03.md` | Lei 6.840/1980 — Cédulas de crédito comercial e à exportação | original |
| `lei-10931-2004-08-02.md` | Lei 10.931/2004 — CCB, CCI, patrimônio de afetação | compilado |
| `lei-8929-1994-08-22.md` | Lei 8.929/1994 — Cédula de Produto Rural (CPR) | compilado |
| `lei-13986-2020-04-07.md` | Lei 13.986/2020 — Fundo Garantidor Solidário, CPR, cédula imobiliária rural | compilado |
| `lei-10406-2002-01-10.md` | Lei 10.406/2002 — Código Civil | compilado |
| `lei-13105-2015-03-16.md` | Lei 13.105/2015 — Código de Processo Civil | compilado |
| `lei-13709-2018-08-14.md` | Lei 13.709/2018 — LGPD | compilado |
| `lei-14711-2023-10-30.md` | Lei 14.711/2023 — Marco das garantias | original |
| `lei-7357-1985-09-02.md` | Lei 7.357/1985 — Cheque | original |
| `lei-5474-1968-07-18.md` | Lei 5.474/1968 — Duplicatas | compilado |
| `lei-13775-2018-12-20.md` | Lei 13.775/2018 — Duplicata escritural | original |
| `lei-11101-2005-02-09.md` | Lei 11.101/2005 — Recuperação e falência | compilado |
| `lei-9265-1996-02-12.md` | Lei 9.265/1996 — Gratuidade dos atos necessários à cidadania | compilado |
| `lei-9534-1997-12-10.md` | Lei 9.534/1997 — Gratuidade do registro civil de nascimento e óbito | original |
| `lei-8560-1992-12-29.md` | Lei 8.560/1992 — Investigação e reconhecimento de paternidade | compilado |
| `lei-14063-2020-09-23.md` | Lei 14.063/2020 — Assinaturas eletrônicas | original |
| `mpv-2200-2-2001-08-24.md` | Medida Provisória 2.200-2/2001 — ICP-Brasil | compilado |
| `lei-13140-2015-06-26.md` | Lei 13.140/2015 — Mediação | compilado |

As leis que só alteram outras (14.382/2022, 9.534/1997, 13.775/2018) têm a
redação nova já incorporada no texto compilado da lei alterada (LRP, Lei
9.492): o texto original delas serve para saber o que mudou e quando.

### Lei estadual (`estadual_ma/`)

| Arquivo | Norma | Texto |
|---|---|---|
| `lei-9109-2009.md` | Lei estadual 9.109/2009 do Maranhão — Custas e emolumentos | original, convertido do PDF do GED da Assembleia Legislativa |

**Os valores das tabelas desta lei são os de 2009.** Os emolumentos se
corrigem todo ano, e o valor que vale é o da tabela em vigor carregada no
sistema. Esta lei serve para a regra (o que se cobra, a isenção, o
fundamento), e nunca para o valor.

## O que não está aqui

- **Decreto 57.663/1966** (Lei Uniforme de letra de câmbio e nota
  promissória): não está no ctresb/leis (a pasta de 1966 tem o 57.662 e o
  57.664, e não ele). Não foi buscado noutra fonte.
- **Provimento CNJ 149/2023 no ctresb/leis:** não há pasta do CNJ em
  `reguladores/`. O texto veio direto da página do CNJ.

## As conferências feitas (05/11/2026)

- **Código do TJMA contra o PDF oficial:** os 1.036 artigos marcados, todos,
  em pedaços de 60 caracteres, ignorando só espaços, travessões e o cabeçalho
  e o rodapé que se repetem em cada página: **nenhuma diferença**.
- **Código Nacional contra a página do CNJ** (com o texto riscado tirado): os
  906 artigos marcados, do mesmo jeito: **nenhuma diferença**.
- **Leis federais e a lei estadual: AINDA NÃO conferidas contra a fonte
  oficial.** O Planalto e o texto do normas.leg.br não responderam a esta
  máquina. Cada arquivo traz o link da fonte no cabeçalho; até a conferência,
  cite pela fonte, e não por aqui.
