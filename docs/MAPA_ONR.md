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

## O que FALTA (trabalho futuro)

O que está acima é a parte que já era do Gestão. Para o sistema gerar o
arquivo do ONR sozinho, faltam:

1. **Importar a geometria** — de Shapefile, GeoPackage ou do SIGEF/INCRA
   (parcelas certificadas) —, amarrada à matrícula, com a origem de cada
   polígono guardada (quem desenhou, de que levantamento).
2. **Calcular a área geodésica no sistema**, no elipsoide do SIRGAS 2000, e
   mostrar ao lado da área registrada quando as duas não baterem.
3. **Gerar o `.gpkg`/`.shp` final pelo sistema**, sem depender do QGIS, com
   conferência antes (polígono fechado, sem sobreposição, matrícula que existe
   e está aberta).
4. **Uma tela no menu do RI**, em vez do endereço do CSV.
5. **A área nova chegar à VIEW sem esperar a subida** — refazer o de-para ao
   gravar a ficha, ou numa rotina do Agendador.
