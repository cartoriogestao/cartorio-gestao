# CRA-MA — estado da integração de remessa XML (24/09/2026)

## Resumo operacional

O arquivo de homologação da operação `RemessaPendente` já foi baixado uma vez
e preservado em pasta privada. O sistema-fonte consegue ler e conferir o XML
na tela **Protesto → Remessa da CRA**, mas **somente como prévia**. Nenhum lote
XML foi recebido, apontado, selado ou confirmado na CRA. A instalação em uso
continua na versão 3.6.197 e não recebeu estas alterações de código.

O relatório de medição, sem dados pessoais, está em
`CRA_HOMOLOGACAO_REMESSA_2026-09-23.md`. O XML bruto não deve ser copiado
para o pacote, repositório, Ajuda ou base do Agente.

## Componentes preparados

| Componente | Papel | Efeito externo |
|---|---|---|
| `protesto_cra_xml.py` | Valida `hd`/`tr`/`tl`, datas, larguras, sequências, contagens e saldos; calcula hash de cada lote original; projeta campos para prévia | Nenhum |
| `atribuicoes_web.py` | Encaminha XML à prévia e o recusa na rota de recebimento | Nenhum para XML |
| `templates/protesto_remessa_conferir.html` | Identifica a prévia e oculta o formulário de receber | Nenhum |
| `cra21_api.py` | Evita repetição automática de downloads após falha incerta | Pode reduzir chamadas repetidas; não efetua chamada por si só |
| `pt_schema.py` | Prepara colunas opcionais e índice único da chave XML em `pt_remessas` | Só altera o esquema numa futura instalação; não recebe lotes |

O leitor TXT de 600 posições e seu recebimento anterior permanecem separados.
A projeção de XML para 600 posições é **temporária e em memória**; não é
autorização para enviar esse texto à rota de recebimento.

## Identidade e duplicidade

O recebimento TXT já usa `UNIQUE(hash_arquivo)` por lote, calculado do texto
normalizado em Latin-1. Essa chave não é adequada, sozinha, para o XML: alguns
caracteres Unicode podem virar `?` na conversão, e dois conteúdos originais
distintos poderiam compartilhar a mesma projeção.

O leitor XML agora calcula `hashes_lotes` com SHA-256 dos nomes/valores dos
atributos `hd`, `tr`, `tl` **originais**, preservando Unicode e espaços dos
campos; só ignora a ordem dos atributos e a indentação XML. Recusa lotes
idênticos dentro do mesmo arquivo. A função `chave_idempotencia(ambiente,
hash_lote)` separa explicitamente `HOMOLOGACAO` de `PRODUCAO`.

O esquema do código-fonte já prepara `origem_xml_ambiente`,
`origem_xml_hash_lote` e `origem_xml_chave`, com índice `UNIQUE` na última.
A migração é aditiva; remessas TXT ficam com esses campos `NULL`. Isso passou
em testes de banco novo e legado. **Nenhum fluxo grava a chave ainda** e a
instalação em uso não recebeu a migração. Antes de habilitar importação XML,
gravá-la na **mesma transação** que cadastra a remessa e os títulos, e testar
concorrência/rollback no fluxo completo. Também é preciso definir o
tratamento de reenvio corrigido: igualdade exata é duplicidade; semelhança
por apresentante/nosso número é aviso para conferência humana, não recusa
automática, porque pode ser reapresentação legítima.

## Segurança da chamada SOAP

`RemessaPendente` e outros downloads podem marcar a remessa como baixada do
lado da CRA. Uma queda de conexão após o envio não prova que a operação
falhou. O cliente não repete automaticamente essas operações e informa que o
estado remoto é incerto. O operador deve conferir a situação na Central antes
de nova chamada. O diagnóstico da ligação usa `BuscarApresentante`, que não
baixa remessa. Homologação e produção usam credenciais e endereços distintos;
o transporte força HTTPS, mesmo com o WSDL de homologação declarando HTTP.

## Verificações executadas e limite atual

- 33 testes focados de leitura XML, transporte SOAP e migração passaram em
  24/09/2026.
- A bateria do recebimento TXT legado também passou: 24 testes de domínio,
  mais os 2 de migração executados junto (26 na execução). Assim, o total
  distinto verificado nesta etapa é 57 testes.
- Os testes usam remessa sintética baseada no fixture legado; não incluem
  dados pessoais da resposta privada. Cobrem trailers inválidos, DTD, aspas
  escapadas, lote duplicado e separação da identidade por ambiente.
- Os módulos Python modificados compilaram e os templates passaram pela
  análise de sintaxe Jinja.
- O arquivo privado já baixado foi relido **localmente, sem chamada à CRA**:
  3 lotes, 30 títulos, 3 hashes de lote distintos e 36 linhas de 600 posições
  na projeção temporária. Nenhum dado pessoal foi exibido ou copiado.
- Há teste de integração da tela para provar que XML não oferece recebimento
  e não grava em `pt_remessas`/`pt_titulos`, mas ele **não foi executado**:
  o venv local contém `lxml` binário para Python 3.11 e o interpretador de
  testes disponível é incompatível. Não tratar esta lacuna como teste verde.

## Portões antes de receber XML ou atualizar a instalação

1. Rodar o teste da tela e a suíte pertinente num Python 3.11 com todas as
   dependências do projeto, incluindo `lxml` funcional, sem árvore em edição.
2. Verificar a prévia do XML privado **somente em leitura** no ambiente de
   homologação, sem repetir `RemessaPendente` apenas para esse fim.
3. Ligar a chave XML `UNIQUE` à transação de recebimento e testar concorrência
   e rollback completo se algum título falhar; a migração isolada já passou.
4. Medir com a CRA o conteúdo de `userDados` para `Confirmacao` e a resposta
   efetiva da operação; o WSDL só comprova os nomes dos parâmetros. Testar
   primeiro com lote **novo e específico de homologação**, combinado com a
   Central. Não enviar uma confirmação presumida.
5. Só após os itens anteriores, criar fluxo de recebimento XML e submetê-lo
   a revisão operacional. Jamais misturar dados de homologação à base real.
6. Empacotar e atualizar pelo atualizador oficial, conferindo a versão e a
   saúde do serviço após a atualização. Não copiar arquivos soltos para a
   instalação em execução.

**Estado final deste trabalho (24/09/2026):** leitor e prévia preparados no
código-fonte; importação XML, confirmação SOAP e atualização da instalação
**não liberadas**.

**Atualização 30/09/2026 (3.6.271, slice 3):** recepção XML (slice 2) e envio
SOAP automático de confirmação + andamento pós-receber remessa — ver
`docs/cra-slice-3-upload-conf-retorno-20260930.md` e
`docs/cra-integracao-andamento-20260930.md`.
