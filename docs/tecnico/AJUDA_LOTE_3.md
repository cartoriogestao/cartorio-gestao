# Ajuda do sistema — Lote 3

## Correção assistida, aprovação humana e aplicação recuperável

Este lote liga o diagnóstico produzido pela Ajuda ao canal de atualização do
Cartório Gestão. A autonomia é deliberadamente dividida: a Ajuda investiga e
organiza evidências; o ambiente de desenvolvimento produz e testa a correção;
o administrador da serventia decide se a versão pode ser aplicada.

O Lote 3 **não transforma a IA em administradora da máquina**. A Ajuda não
edita arquivos da instalação ativa, não executa comandos, não instala
dependências e não aplica uma resposta textual como código.

## Fluxo implantado

### 1. Preparar

Somente o perfil `ADMIN` recebe o pacote `.cgu`. O SHA-256 é obrigatório e deve
ser obtido por canal separado. Antes de aceitar o pacote, o sistema confere:

- produto e versão do formato;
- versão de destino e versão mínima;
- limite do pacote, número de arquivos e tamanho descompactado;
- caminhos relativos, duplicidades e tentativas de sair da pasta autorizada;
- relação exata entre manifesto e conteúdo;
- SHA-256 do pacote e de cada arquivo;
- lista de exclusões e conflito entre excluir e substituir o mesmo caminho.

O conteúdo é montado em uma **cópia candidata isolada**. A instalação ativa não
é alterada, nenhum backup é necessário nessa etapa e nenhum código recebido é
executado.

### 2. Inspecionar e aprovar

Na cópia candidata, o sistema calcula o impacto por arquivo (`NOVO`, `ALTERADO`,
`IGUAL` ou `EXCLUIDO`), destaca componentes críticos e faz verificações
estruturais:

- sintaxe de arquivos Python por análise da árvore sintática, sem importá-los;
- estrutura de JSON;
- UTF-8 dos arquivos textuais;
- equilíbrio básico dos delimitadores de templates;
- coerência entre o manifesto, `VERSAO.txt` e a constante `VERSION` de
  `app.py`;
- presença de `requirements.txt` quando o pacote pede sincronização de
  dependências.

Erros deixam a preparação em `REJECTED`. Uma preparação válida fica em
`READY_FOR_APPROVAL` e exibe seu impacto na tela.

Para aprovar, o administrador precisa, na mesma operação:

1. repetir o SHA-256 completo;
2. digitar `APLICAR <versão>` exatamente;
3. informar novamente a própria senha;
4. declarar que revisou componentes críticos, avisos e rollback.

Antes de registrar a aprovação, o sistema relê o pacote e todos os arquivos
preparados. Qualquer alteração posterior à inspeção cancela a operação. A
aprovação não pode ser reutilizada.

### 3. Aplicar, verificar e recuperar

Depois da aprovação, o sistema gera um backup completo dos dados e documentos.
O aplicador do Windows volta a conferir:

- estado `APPROVED`;
- identidade do aprovador;
- existência do backup obrigatório;
- SHA-256 do pacote original;
- SHA-256 e caminho seguro de cada arquivo preparado.

Em seguida cria uma cópia integral dos arquivos atuais para rollback, troca os
arquivos e reinicia o serviço. A nova versão precisa responder ao teste local
de saúde. Falha durante a cópia, dependências, reinício ou teste de saúde aciona
o rollback. Os estados `APPLIED`, `ROLLED_BACK`, `ROLLBACK_FAILED` e `ERROR`
ficam registrados nos metadados, e o resultado aparece na tela.

## LGPD e circulação de dados

O canal de atualização é local e recebe **código do produto**, não dados do
acervo. Ele não envia banco, documentos, nomes, CPFs ou conteúdo de atos para
fora da serventia.

Quando um problema ou arquivo precisa ser analisado externamente, continuam
valendo as barreiras dos Lotes 1 e 2:

- o arquivo original permanece na serventia;
- somente texto necessário pode integrar a consulta;
- dados pessoais, dados pessoais sensíveis, credenciais e segredos são
  mascarados ou anonimizados obrigatoriamente;
- a prévia permite ver o conteúdo sanitizado antes do envio;
- o evento é auditado com hashes e metadados, sem duplicar o dado protegido.

Uma correção nunca deve conter cópia de banco de produção, relatório não
sanitizado, documento de usuário ou credencial. Se o manifesto declarar algum
desses artefatos, o pacote deve ser recusado no processo de desenvolvimento,
antes de chegar à serventia.

## Evidência de testes e seu limite

O gerador de `.cgu` agora aceita registrar resumo, comando e quantidade de
testes executados no ambiente confiável de desenvolvimento. Essa informação é
mostrada como **declaração do desenvolvedor**, não como teste executado pelo
servidor da serventia.

Essa distinção impede que um pacote faça o servidor executar código ainda não
aprovado. Testes funcionais completos devem ocorrer no desenvolvimento ou em
ambiente de homologação sem dados reais. A serventia faz inspeção estática,
confere integridade e, depois da aprovação, executa apenas o teste de saúde da
instalação.

## Estados auditáveis

`STAGED` → `READY_FOR_APPROVAL` ou `REJECTED` → `APPROVED` → `APPLYING` →
`APPLIED`, `ROLLED_BACK`, `ROLLBACK_FAILED` ou `ERROR`.

Os principais eventos também entram na auditoria geral: pacote preparado,
preparação rejeitada, aprovação negada, aprovação concedida e falha de
aprovação.

## Limites atuais e evolução recomendada

- O SHA-256 por canal separado detecta alteração ou troca do arquivo, mas não
  substitui assinatura criptográfica do fornecedor. Assinatura de pacotes com
  chave pública fixada no produto é a próxima evolução recomendada.
- A análise de Python, JSON e templates é estrutural; não prova a correção da
  regra de negócio.
- O rollback de arquivos e o backup do acervo reduzem impacto, mas uma migração
  destrutiva de banco exige estratégia própria e deve ser evitada em pacotes
  automáticos.
- `ROLLBACK_FAILED` exige atendimento técnico imediato e preservação dos logs,
  do backup e das duas cópias de arquivos.
- A IA pode produzir hipótese, plano ou proposta de alteração no ambiente de
  desenvolvimento. Ela não recebe credencial permanente nem autorização para
  contornar a aprovação do administrador da serventia.

## Arquivos principais

- `update_manager.py`: recebimento, integridade, cópia candidata, inspeção e
  estados de aprovação;
- `app.py` e `templates/updates.html`: duas etapas, reautenticação e auditoria;
- `installer/aplicar_atualizacao.ps1`: conferência final, troca, saúde e
  rollback;
- `tools/criar_atualizacao.py`: geração do pacote e declaração de validação;
- `tests/test_update_network.py` e `tests/test_update_approval.py`: segurança do
  pacote e governança da tela.
