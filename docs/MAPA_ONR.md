# O Mapa do Registro de Imóveis do ONR

A serventia vai entregar ao ONR o mapa dos imóveis que registra. Este documento
diz o que o ONR pede, o que o Cartório Gestão já entrega (lote LF02, 19/10/2026),
como usar com o plugin de referência do QGIS e **o que falta**.

## O que o ONR pede

Um arquivo **Shapefile** (`.shp`) ou **GeoPackage** (`.gpkg`) com, por imóvel:

| atributo | o que é |
|---|---|
| geometria | o polígono do imóvel |
| `MATRICULA` | o número da matrícula |
| `CNS` | o Código Nacional de Serventia desta casa |
| `PROPRIETAR` | o proprietário atual (quem tem vários, juntos) |
| `AREA_HA` | a área em hectares, geodésica, calculada no elipsoide do projeto |

Os nomes têm no máximo dez letras porque o Shapefile não aceita mais.

## O plugin de referência

[em-rezende/qgis-registro-onr-plugin](https://github.com/em-rezende/qgis-registro-onr-plugin),
licença MIT. Há uma cópia do `main.py` dele na pasta da migração
(`referencia/qgis-registro-onr-main.py`). O que ele faz, lido no código:

1. Lê uma camada de polígonos (ou linhas, que ele fecha em polígono) do
   projeto do QGIS, e o campo dela que tem a matrícula.
2. Para cada feição marcada, procura no banco
   `SELECT cns, proprietario, area_ha FROM imoveis WHERE matricula = %s`
   — originalmente num **MySQL** (`mysql.connector`).
3. Calcula a área geodésica no elipsoide do projeto (`QgsDistanceArea`).
4. Grava o `.shp` ou o `.gpkg` com os quatro atributos.

> **Atenção à regra do passo 4, que é do plugin e não desta casa:** se o banco
> devolve `area_ha`, **é ela que vai** para o `AREA_HA`; a geodésica só entra
> quando o banco não tem área. O ONR pede a geodésica. Decidir qual das duas
> vai é do oficial — ver «Decisões pendentes».

## O que o Gestão entrega

O Gestão **não guarda geometria**. Ele entrega os quatro atributos, de dois
jeitos, e os dois saem da mesma regra (`ri_mapa_onr.py`):

### A VIEW `onr_mapa_imoveis`

| coluna | de onde vem |
|---|---|
| `matricula` | `ri_matriculas.numero`, com `-complemento` quando há (`4015`, `4015-A`) |
| `cns` | `settings.ri_cns` (Configurações), ou `serventia_cns` se a primeira não tem dígito; só os dígitos |
| `proprietario` | as partes com `proprietario_ativo = 1` — **o dono de hoje, e não quem já foi** —, juntas por `; ` |
| `area_ha` | `ri_matriculas.area_valor` + `area_unidade`, lidas pela régua da casa (`onr_api.area_em_metros`) e divididas por 10.000; quatro casas |

- **Fica de fora** a matrícula encerrada (`encerrada = 1` ou situação
  `ENCERRADA`) e as anuladas, canceladas e inexistentes. A reaberta fica.
- **Sem dono ou sem CNS, a coluna vem vazia (`''`)**, e não nula: o plugin
  escreveria a palavra «None» no arquivo.
- **Área vazia quer dizer «não se sabe»**: a ficha não tem área, ou a escreve
  de um jeito que a régua não decide (`3808` em hectare tanto é 38,08 ha
  quanto 3.808 m²). Sem área do banco, o plugin usa a geodésica.

**A área da VIEW se recalcula a cada subida do sistema.** A régua é Python e a
VIEW é SQL; por isso a subida grava o resultado da régua num de-para
(`ri_mapa_onr_areas`), e a VIEW o junta. Uma área escrita **depois** da subida
com um texto que a casa ainda não tinha usado aparece vazia na VIEW até a
próxima subida — vazia, nunca errada. O CSV não tem esse atraso.

### O CSV `/ri/mapa-onr.csv`

Só o **ADMIN** baixa, e o download fica na auditoria
(`RI_MAPA_ONR_EXPORTADO`): o arquivo leva o nome de cada proprietário.

- Colunas com os nomes do ONR: `MATRICULA;CNS;PROPRIETAR;AREA_HA`.
- Separador `;`, codificação UTF-8 com a marca do início (BOM), como os outros
  CSV da casa; área com **ponto** decimal (`231.0233`).
- Ordem pelo número da matrícula.

## Como usar

### Caminho 1 — o plugin lendo a VIEW direto

Trocar, no `main.py` do plugin, o MySQL pelo PostgreSQL. São três pontos:

```python
# no topo, no lugar do `import mysql.connector`
import psycopg
from psycopg.rows import dict_row

# em processar_dados, no lugar do mysql.connector.connect(...)
conn = psycopg.connect(host=db_host, dbname=db_name,
                       user=self.dialog.txt_user.text().strip(),
                       password=self.dialog.txt_pass.text().strip())
cursor = conn.cursor(row_factory=dict_row)

# e a consulta, com o nome da VIEW
cursor.execute("SELECT cns, proprietario, area_ha FROM onr_mapa_imoveis "
               "WHERE matricula = %s", (mat_val,))
```

O `HAS_MYSQL` vira a pergunta «o `psycopg` importou?». O resto do plugin não
muda. O `area_ha` chega como `Decimal`, e o `float(...)` do plugin o aceita.

**O acesso do QGIS é só à VIEW.** Ela tem nome de pessoa (LGPD): o QGIS entra
com um usuário próprio, que lê a VIEW e nada mais — a VIEW roda com os
direitos de quem a criou, e o usuário não precisa (nem deve) ver as tabelas:

```sql
CREATE ROLE qgis_onr LOGIN PASSWORD '...';          -- a senha fica com o oficial
GRANT USAGE ON SCHEMA producao TO qgis_onr;          -- o schema do banco da casa
GRANT SELECT ON producao.onr_mapa_imoveis TO qgis_onr;
ALTER ROLE qgis_onr SET search_path = producao;
```

E o `pg_hba.conf` do servidor libera esse usuário só a partir da máquina do
QGIS. A subida do sistema recria a VIEW com `CREATE OR REPLACE`, que **mantém**
o `GRANT`.

### Caminho 2 — o CSV juntado à mão

1. Baixar `/ri/mapa-onr.csv` (logado como ADMIN).
2. No QGIS: *Camada → Adicionar camada → Texto delimitado*; formato
   personalizado com `;`; codificação UTF-8; **sem geometria**. Em «tipos de
   campo», deixar `MATRICULA` como **texto** — detectada como número, ela não
   junta com o campo de texto da camada.
3. Na camada dos polígonos: *Propriedades → Uniões*, campo `MATRICULA` dos
   dois lados, prefixo vazio.
4. Onde `AREA_HA` vier vazia, a geodésica sai na calculadora de campo:
   `$area` respeita o elipsoide **e a unidade de área** do projeto — com a
   unidade em hectares, `$area` já é a resposta; em metros quadrados,
   `$area / 10000`.
5. Salvar como Shapefile ou GeoPackage.

## Decisões pendentes

- **Área registrada ou geodésica no `AREA_HA`.** O plugin dá preferência à do
  banco (a registrada); o ONR fala da geodésica. Se a resposta for «sempre a
  geodésica», basta o plugin ignorar o `area_ha` da VIEW.
  **Desde o RI011 a tela do mapa pergunta e guarda a escolha**
  (`ri_mapa_area_regra`): ver «O polígono dentro do sistema».
- **A mesma matrícula em dois livros.** A VIEW traz as duas fichas com o mesmo
  `matricula`, e o plugin pega uma qualquer (`fetchone`). Não foi medido na
  produção quantas há.

## Atenção para quem mexer no banco

A VIEW prende as colunas que lê (`ri_matriculas`: `numero`, `complemento`,
`situacao`, `encerrada`, `area_valor`, `area_unidade`; `ri_partes`:
`matricula_id`, `nome`, `proprietario_ativo`; `settings`). O PostgreSQL recusa
`ALTER COLUMN ... TYPE` e `DROP COLUMN` numa delas enquanto a VIEW existir:
quem precisar, faz `DROP VIEW onr_mapa_imoveis`, muda a coluna e sobe o
sistema, que a recria — e refaz o `GRANT` do QGIS, que o `DROP` apaga.

O contrário também vale: a ponte apaga tabela com `CASCADE` (como o SQLite,
que apagava mesmo com outra apontando), e apagar uma dessas três leva a VIEW
junto, em silêncio. A subida seguinte a recria; o `GRANT`, não.

## O passo do georreferenciamento no ato (RI011, S8)

O art. 343-F, II, do Código Nacional de Normas (Prov. CNJ 195/2025) manda o
oficial, ao **abrir matrícula** ou **atualizar, corrigir ou alterar a descrição
perimetral**, analisar o mosaico no SIG-RI: erro de fechamento do polígono e
sobreposição com outros imóveis.

O sistema não consulta o SIG-RI. O que ele faz é **o passo**, em
`ri_georref.py`: o formulário de abrir matrícula e o de lavrar ato trazem a
pergunta «conferiu o mosaico?» (conferi sem ocorrência · conferi, há ocorrência ·
imóvel sem coordenadas · conferirei depois), e a resposta fica gravada com o
**nome de quem respondeu e a hora**, ao lado do ato — como a consulta à CNIB.

- **Avisa, não bloqueia.** Em branco, «depois» ou sessão de robô, o ato sai e a
  conferência fica **PENDENTE**, com aviso na tela. A pendente aparece na ficha
  («Georreferenciamento — mosaico no SIG-RI») e em
  *Registro de Imóveis → Georreferenciamento — a conferir*, e se resolve depois
  por uma linha nova; a antiga não se reescreve.
- **Quais atos pedem o passo:** a abertura de matrícula (ficha de acervo não) e as
  naturezas que mexem no perímetro — loteamento, usucapião, desmembramento,
  unificação, remembramento, atualização de confrontação, retificação de área,
  novas divisas — e os modelos de georreferenciamento e de unificação. A lista
  é `ri_georref.CODIGOS_QUE_PEDEM`, **do oficial**: qualquer outro ato também
  pode ser conferido, o campo está em todos.
- **Conferência é de pessoa.** Conta de robô não confere (como na afirmação
  expressa): a linha nasce PENDENTE, sem nome de máquina.
- **O que ficou de fora:** o inciso III do mesmo artigo (em *qualquer* ato,
  averiguar especialidade, disponibilidade e unicidade pelo SIG-RI) e o inciso I
  (alimentar o SIG-RI com os perímetros).

## O polígono dentro do sistema (RI011, S9)

Desde o RI011 o Gestão **guarda a geometria**. A tela está em *Registro de
Imóveis → Mapa do ONR — polígonos* (`/registro-imoveis/mapa`); o código, em
`geo_geodesia.py` (as contas), `geo_formatos.py` (os arquivos), `ri_geo.py` (o
banco e a conferência) e `ri_geo_web.py` (a tela).

**O que faz**

1. **Importa** GeoPackage (`.gpkg`), Shapefile (`.zip` com `.shp`, `.dbf` e
   `.prj`), GeoJSON e a parcela baixada do SIGEF (marca-se «é a parcela do
   SIGEF»; o formato continua sendo o do arquivo). Aceita SIRGAS 2000
   geográfico e UTM SIRGAS 2000 (EPSG:31965 a 31985); WGS 84 entra **com aviso**;
   SAD 69 e Córrego Alegre são **recusados** (a passagem depende de parâmetros
   que o sistema não tem — converta no QGIS).
2. **Guarda cada polígono com a origem**: arquivo e SHA-256, camada, sistema de
   coordenadas, de que levantamento é, quem o desenhou, quem importou e quando,
   e os atributos como vieram.
3. **Nunca adota sozinho.** O polígono entra PENDENTE; o atributo `MATRICULA` do
   arquivo só **sugere** a ficha. Quem adota é a pessoa (um por vez ou em lote,
   para as sugestões sem erro). Um polígono **vigente** por matrícula — o banco
   recusa o segundo —, e trocar o vigente não apaga o antigo (fica SUBSTITUÍDO).
4. **Mede a área no elipsoide** (GRS 1980, o do SIRGAS 2000) e a mostra **ao lado
   da registrada**, com a diferença; «não bate» quando passa da tolerância.
5. **Confere**: erro de fechamento (o último vértice longe do primeiro), anel que
   se cruza, poucos vértices, coordenadas fora do Brasil, **sobreposição** com
   os outros vigentes (área, % de cada um) e **matrícula aberta** (a mesma regra
   do CSV). ERRO deixa o polígono fora do arquivo; AVISO vai no arquivo e é lido
   por quem decide.
6. **Gera o arquivo** com os atributos do ONR (`MATRICULA`, `CNS`, `PROPRIETAR`,
   `AREA_HA`): `.gpkg` e Shapefile (`.zip` com `.shp .shx .dbf .prj .cpg`). Só o
   ADMIN baixa (leva o nome dos proprietários), e a baixa fica na auditoria.
   **O sistema não envia ao ONR.**

**A área do arquivo é decisão do oficial.** O plugin de referência manda a
registrada quando a ficha a tem; o ONR descreve a geodésica. A tela pergunta, e
**sem a escolha o arquivo não se gera**: «a registrada, e a geodésica só no
vazio» (a regra do plugin), «sempre a geodésica» ou «sempre a registrada»
(chave `ri_mapa_area_regra`).

**As tolerâncias são desta casa, não do ONR.** Fechamento (0,05 m), sobreposição
que importa (1 m²) e diferença de área que «não bate» (1 %) são valores de
trabalho, editáveis na tela: o art. 343-D, § 2º, V, remete as tolerâncias
posicionais a um manual técnico do ONR que a casa não tem.

**Atenção ao Shapefile:** `PROPRIETAR` cabe em 254 bytes (o teto do dBase). O que
passar é cortado, e a geração diz qual matrícula foi cortada; o GeoPackage não
tem esse limite.

### Dependência: uma só

`geographiclib` (MIT, pura em Python, 390 KB, roda `py3-none-any`): a conta de
área de polígono de arestas geodésicas, a mesma do QGIS. GDAL, Fiona, PyProj e
Shapely **não** entram — são rodas nativas de dezenas de MB. O Shapefile e o
GeoPackage são lidos e escritos à mão (o GeoPackage é um SQLite, e o `sqlite3`
já vem no Python), e a sobreposição é conta de plano escrita no sistema. Tudo foi
**conferido contra o GDAL, o PROJ e o GEOS** na bancada do desenvolvedor; nada
disso é instalado na produção. Sem a biblioteca, a tela diz o que instalar e o
resto do sistema segue.

### O memorial da matrícula vira polígono PENDENTE

Muitas fichas trazem, no teor, o memorial no formato do SIGEF: «… até o vértice
XXXX-M-0002, de coordenadas (Longitude: -47°12'00,425", Latitude -05°50'53,691" e
Altitude …)». A tela do mapa tem a seção **«Extrair do memorial da matrícula»**
(um número de matrícula, ou o botão para todas as abertas que têm memorial). O
código é `geo_formatos.ler_memorial` (a leitura do texto), `ri_geo.extrair_memorial`
(medir e guardar) e `ri_geo.adotar_memoriais_sem_aviso` (o lote).

**O que a leitura faz**

1. Tira a marcação HTML do teor, desescapa (`&#x27;`, `&quot;`, até duas vezes) e lê
   os vértices **na ordem do texto**: nome (o que vem depois de «vértice», «ponto»
   ou «marco»), Longitude e Latitude em graus, minutos e segundos — sinal negativo,
   hemisfério em letra (N S L O W E) ou por extenso (Norte, Sul, Leste, Oeste),
   vírgula ou ponto decimal, aspas e apóstrofos de qualquer tipo, Longitude antes
   ou depois da Latitude. O anel se fecha no primeiro vértice.
2. **Rodapé de página no meio da coordenada** (o teor vem de PDF) é lido e marcado:
   o vértice sai, e a conferência avisa «texto no meio da coordenada».
3. **SIRGAS 2000.** O texto que diz **SAD 69 ou Córrego Alegre é recusado**, com a
   frase do motivo (a passagem de datum precisa de parâmetros que o sistema não
   tem); o que cita um deles **e** o SIRGAS também (não dá para saber a qual valem
   as coordenadas) é recusado do mesmo jeito. WGS 84 entra com aviso. O texto que
   **não diz o sistema** entra tratado como SIRGAS 2000, **com aviso**.
4. **Mais de uma gleba no texto:** cada «Inicia-se a descrição deste perímetro»
   abre uma gleba; sem essa frase, o anel que volta ao primeiro vértice (pelo nome
   ou pela coordenada) fecha a gleba e o que vem depois abre outra. Cada gleba é
   **um polígono**, e todos levam o aviso «CONFERIR» com a **soma das áreas** ao
   lado da registrada. Vértices de glebas diferentes nunca entram no mesmo anel.
5. O que não se lê **não some em silêncio**: coordenada com minuto ou segundo que
   não existe, rótulo «Longitude» sem a coordenada, ou coordenada sem sinal e sem
   hemisfério viram **ERRO** no polígono (fica guardado, não se adota). O texto
   que não é graus-minutos-segundos (grau decimal, UTM) **não é lido**: a recusa
   diz isso.

**O que fica guardado:** um polígono **PENDENTE** por gleba, com origem «Memorial da
matrícula» (`ri_geo_importacoes.formato = MEMORIAL`, nome «memorial da matrícula
N», SHA-256 do texto lido) e, em `origem_atributos`, o **texto-fonte da gleba** e os
**vértices como vieram** (nome, coordenada escrita e valor). A matrícula fica só
como **sugestão** (`matricula_id` com a situação PENDENTE). Extrair de novo o mesmo
texto é recusado (já está guardado, mesmo descartado); texto que mudou extrai de
novo. A ficha de leitura é o `teor`; se ele não tem o memorial, a descrição do
perímetro.

**A conferência é a que já existia**, mais os achados do memorial: área medida ao
lado da registrada (na lista de pendentes e na página do polígono), fechamento,
cruzamento, coordenadas fora do Brasil, sobreposição com os vigentes (quando
adotado), e — só do memorial — «várias glebas», «o texto não volta ao primeiro
vértice» (o sistema fechou o anel), «texto no meio da coordenada», «coordenadas
fora de qualquer descrição», «ato com coordenadas no teor» (outra descrição pode
estar em vigor) e «o texto não diz o sistema».

**Adoção é ato da pessoa.** Um a um, pela tela do polígono. Em lote existe **só o
botão «Adotar os memoriais sem aviso»**: leva o polígono que não tem achado
nenhum (nem aviso), de matrícula aberta e sem vigente, com a área que **bate** com
a registrada (tolerância da casa), sem sobreposição com polígono vigente e que não
é uma de várias glebas. O lote antigo (sugestões do atributo do arquivo) **não**
adota memorial. Adotar uma gleba substitui o vigente da matrícula (o Mapa guarda
um polígono por matrícula), e a tela avisa.

**O que foi medido (26/11/2026, só leitura, sem copiar texto):** das 467 matrículas
abertas que citam «Longitude» no teor ou na descrição do perímetro, 310 viram ao
menos um polígono; 154 não têm vértices em graus-minutos-segundos (em 20 delas há coordenada em grau
decimal; nas demais, o rótulo «Longitude» aparece de outro jeito, e **ainda não se
olhou o que é**) e 3 foram recusadas por SAD 69. Das
302 que trazem pelo menos 3 vértices com nome de SIGEF (a contagem da RI007 foi 269,
com outro critério), 299 viram polígono e 209 sem erro; dessas, 127 têm área
registrada legível e **92 estão dentro de ±5%** (60 dentro de ±1%). Só **9** não têm
nenhum aviso — quase sempre por causa do «o texto não diz o sistema» —, e é isso
que o lote adota (descontada a sobreposição).

**O que o lote não faz, de propósito:** adotar o que o texto não diz que é SIRGAS;
assumir hemisfério onde não há sinal (59 matrículas têm coordenada sem sinal: ficam
ERRO, e quem decide é o oficial se «sem sinal, no Brasil, é Oeste/Sul» serve); ler
grau decimal; somar glebas num polígono só (multipolígono por matrícula).

## O que ainda FALTA

- **O Manual 2 do Book C (topografia) não está disponível**, e o formato exato que
  o Mapa do ONR espera para a carga (nomes de campo, sistema, geometria) segue
  sendo o do plugin de referência — de terceiro, e não de documento do ONR.
- **Desenho do polígono dentro do sistema** (digitar coordenadas) e **importar o
  memorial em planilha** do SIGEF. O memorial **em texto, do teor da matrícula**,
  já entra (ver acima); **baixar do SIGEF** e **enviar ao ONR** seguem de fora (o
  primeiro depende de decisão do oficial sobre chamada externa).
- **Memorial em grau decimal ou UTM**, e a **matrícula com várias glebas num só
  polígono** (multipolígono): hoje só graus-minutos-segundos, e uma gleba por vez.
- **O nome dos atributos da camada do SIGEF/Acervo Fundiário não foi achado em fonte
  oficial**: o sistema só usa um punhado de nomes prováveis para **preencher** o
  código da parcela, que a pessoa confere.
- **A área nova chegar à VIEW `onr_mapa_imoveis` sem esperar a subida** (item 5
  antigo): segue como estava.
- **A mesma matrícula em dois livros**: a tela recusa adotar e pede ao oficial que
  confira a numeração.
