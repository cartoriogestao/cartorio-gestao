# Arquitetura do Cartório Gestão

Python 3.11 · Flask · SQLite (modo WAL) · waitress · Jinja2. Um processo só,
num servidor Windows da serventia, atendendo os navegadores da rede local.

## As regras da casa

Elas não são estilo: cada uma existe porque a violação dela já custou um
defeito real.

- **`db.transaction()` é `BEGIN IMMEDIATE`** — um escritor por vez. É o que faz
  as outras travas valerem.
- **`audit()` abre transação própria**: chame-o **fora** de
  `with db.transaction()`, senão ele trava contra a transação de fora. `q` e
  `q1` também abrem conexão própria.
- **Módulo de domínio primeiro, com `con` recebido; a rota só liga os fios.**
  O que se testa é o domínio. As telas desabilitam o que não cabe por
  educação; o domínio recusa por dever.
- **Erro de regra é subclasse de `ValueError`, com a frase pronta para o
  balcão** (em português, dizendo o que fazer). A rota mostra com `flash`; erro
  de regra não é HTTP 500.
- **Onde a regra pode morar no banco, ela mora no banco.** A numeração dos
  livros é protegida por `UNIQUE(livro_id, folha, verso, ordem)`, e não só por
  código.
- **Migração só acrescenta** (`ALTER TABLE ADD COLUMN`). Tabela nova vai no
  esquema como `CREATE TABLE IF NOT EXISTS`; índice sobre coluna de migração
  vai **depois** da migração (`tests/test_esquemas.py` guarda isso).
- **GET não escreve.** Tela de leitura que consumisse contador ficaria presa
  esperando a trava de quem está lavrando.
- **Chamada de rede nunca dentro de transação.** O pedido de selo tem prazo de
  20 s; por isso `obter_selo()` recebe `db`, e não `con`, e abre a sua própria
  transação curta.
- **Credencial nunca no banco.** O banco viaja no backup; senhas e chaves
  ficam em `*.cred` na pasta de dados.
- **Não se aumenta o acoplamento ao SQLite.** Data calculada no SQL, recorte
  de texto no SQL e `PRAGMA` fora dos esquemas têm teto por módulo
  (`tests/test_portabilidade.py`); módulo novo entra com zero.

## O núcleo — serve as seis atribuições

| Módulo | O que é |
|---|---|
| `livro_nucleo.py` | a geometria dos livros (atos por face, faces por folha) |
| `nucleo_schema.py` · `escrituracao.py` | abrir livro, achar lugar, lançar, inutilizar, encerrar livro e o dia |
| `custas.py` | emolumentos e fundos, gratuidade, vigência **pela data do ato** |
| `ato_selado.py` | onde custas, selo e ato se encontram, na ordem certa (custas → selo → vínculo) |
| `selo.py` · `selador.py` · `selador_cliente.py` · `selador_config.py` | o selo eletrônico: leitura do código, o contrato do aparelho, o transporte com certificado fixado, a configuração e o razão `sd_selos` |
| `serventia.py` | os dados da serventia — lidos de `settings`, nunca escritos no código |
| `implantacao.py` | o que só o titular pode informar (próximos números, livros), com aviso em toda tela |
| `modulos.py` · `modulos_ligados.py` | qual módulo é cada tela, e quem alcança cada módulo |
| `inacabados.py` | o que começou e não terminou, medido na hora nas tabelas onde os atos moram |
| `fraude.py` | a lista de atenção para fraudes — alerta, e nunca trava |

## As atribuições

| Atribuição | Onde mora |
|---|---|
| Registro de Imóveis | `ri_*.py` (matrículas, atos, prenotação, certidões, CNIB, usucapião, retificação, minutas), `ra_*.py` (Livro 3) |
| Tabelionato de Notas | `notas_*.py` (escrituras, procurações, firmas, autenticações, cartões de assinatura, CENSEC, DOI) |
| Protesto | `protesto*.py`, `pt_schema.py`, `cra21_api.py`, `cenprot_api.py`, `resolve_*.py` |
| Registro Civil (RCPN) | `rc_*.py`, `habilitacao*.py`, `proclamas*.py`, `sirc_*.py`, `crc_*.py`, `ibge_*.py`, `onrcpn_*.py` |
| RCPJ e RTD | `rg_*.py`, `onrtdpj_api.py` |
| Caixa e protocolo geral | `caixa_*.py` |

## O selo, em uma frase por regra

- O selo sai **quando o ato é praticado**, pelo caminho que o aparelho conhece
  para aquele ato — e **não se sela por caminho que a casa nunca usou**.
- O SID (a referência do pedido) é determinístico: pedir de novo devolve o
  mesmo selo, em vez de comprar outro.
- A chave de um selo no razão é **tabela + id do ato**: o id sozinho repete
  entre tabelas.
- O papel imprime o que o selo declara (emolumentos, fundos, marcas como
  «isento»), e a tela e o papel pedem o conteúdo à mesma função.

## Papéis e modelos

- Certidões, termos e recibos saem em **`.odt`**; o PDF é o LibreOffice
  convertendo o mesmo `.odt` (`impressao_pdf.py`), para o papel não ser
  redesenhado por outro motor.
- **O código é o piso; a tabela é o ajuste.** Os modelos de texto têm padrão no
  código (`modelos_da_casa.py` e os módulos de cada atribuição) e a serventia
  ajusta na tela; sem ajuste, sai o padrão — e «voltar ao padrão» é apagar a
  linha.
- As certidões do RCPN usam moldes `.odt` em `modelos/`, que a serventia pode
  redesenhar no LibreOffice.

## As Centrais

Cada integração tem um módulo de **transporte** (`*_api.py`), medido contra o
contrato público da Central (Swagger, WSDL ou XSD guardado ao lado dos testes),
e um módulo de **domínio** que decide o que sobe. Princípios comuns:

- **conferir e enviar são dois passos** — o que sobe muda coisa do lado de lá;
- **HTTP 200 não quer dizer aceito**: lê-se o corpo, item por item;
- **o `https` se força**, mesmo quando o contrato da Central declara `http`;
- homologação e produção são credenciais e registros diferentes.

## A ajuda e o agente

- `ajuda*.py` — a janela de ajuda de toda tela. Consulta um provedor de IA
  escolhido em `aj_config` (`agente_provedores.py`), lê a instalação por
  ferramentas **só de leitura** e passa tudo por `ajuda_privacidade.py`, que
  mascara dados pessoais antes de qualquer coisa sair da serventia.
- `agente*.py` — o console do administrador. Pode anotar e configurar (com
  desfazer para cada mudança, e desligado por padrão); **não pratica ato**, não
  executa código e não lê fora da pasta do sistema.

## Testes

- `tests/` — pytest, com uma serventia **fictícia** montada pelo `conftest.py`
  (CNS `000000`, «Cidade Exemplo»). Rode com `-n 4 --dist loadfile`: vários
  arquivos têm testes que dependem da ordem.
- Há **varredores** que guardam regras estruturais: toda tela que grava manda
  `csrf_token`; toda rota que grava tem uma tela que a chama; toda tela abre
  numa instalação nova; o acoplamento ao SQLite não cresce.
- `tools/pytest_guard.py` impede duas suítes na mesma árvore ao mesmo tempo.

## O que vai para este repositório

A árvore pública é montada por `tools/exportar_publico.py`, **por lista do que
entra** (o que o `app.py` alcança pelos imports, as pastas de código e os
arquivos de projeto), e não por lista do que sai. Antes de publicar, o
varredor `ci/anti_vazamento.py` tem de dar **zero**: CPF, CNPJ, CNS e selo só
entram se declarados como fictícios, e os moldes `.odt` são abertos e lidos
por dentro. O diário de desenvolvimento da serventia de origem não faz parte
do repositório.
