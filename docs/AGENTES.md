# Para quem programa com IA neste repositório

Vale para pessoas e para assistentes de código (Claude Code, Cursor, Codex,
ChatGPT e outros). Leia antes de propor mudança. As regras de arquitetura
estão em [`ARQUITETURA.md`](ARQUITETURA.md); aqui fica o que costuma dar
errado quando quem escreve não conhece a casa.

## O fluxo

1. Trabalhe num ramo seu e abra um *pull request*. Ninguém envia direto para
   o ramo principal.
2. Na revisão, a CI roda o varredor anti-vazamento, o gitleaks e os testes.
   PR com a CI vermelha não entra.
3. Entrar no ramo principal **não** atualiza nenhuma serventia. Quem leva o
   código a uma instalação em uso é o titular, com um pacote `.cgu` assinado
   (`tools/criar_atualizacao.py --assinar`). A instalação recusa pacote sem
   assinatura de chave cadastrada em `assinatura_da_atualizacao.py`.
   Nenhuma IA gera, guarda ou usa a chave privada.

## Dado real não entra — nem nos testes

Este é o código de um cartório em uso. O que mais pode dar errado num PR é
dado de gente real.

- **Use só os fictícios da casa:**
  - pessoas: «Mario Exemplo dos Santos», «Beatriz Exemplo de Souza», «Carla
    Exemplo», «Pedro Exemplo dos Santos»;
  - lugar: «Cidade Exemplo»;
  - serventia: CNS `000000` (ou `999999` onde o zero perde o sentido);
  - documentos: os CPF/CNPJ de `tests/fixtures/anti_vazamento/documentos_ficticios.txt`.
- Precisando de outro documento com dígito verificador válido, acrescente-o a
  essa lista com base zerada (`000.000.0xx-yy`). Nunca use número de gerador
  da internet: ele é de alguém.
- Nada de nome de pessoa real, nem em comentário: cliente, parte, escrevente,
  usuário do sistema. Comentário fala do papel («o oficial», «a escrevente»),
  e o login vem de configuração (`settings`), nunca escrito no código.
- Rode antes de abrir o PR:

  ```bash
  python ci/anti_vazamento.py --modo git
  ```

  Ele recusa CPF, CNPJ, CNS, selo e matrícula que não estejam declarados como
  fictícios.

## Testes

```bash
python -m pytest tests -n 4 --dist loadfile      # a suíte, em paralelo
python -m pytest tests -m "not lento"            # só os rápidos
python -m pytest tests/test_x.py                 # um arquivo
```

- **A suíte não roda duas vezes na mesma árvore.** O `conftest` recusa uma
  segunda rodada. Ele também invalida o resultado se um arquivo mudar no meio
  da rodada.
- Teste que precisa do acervo ou da produção de uma serventia se protege
  sozinho (`pytest.skip` quando o arquivo não existe). Fora dela, ele é
  pulado, e isso é esperado.
- Um teste que não imprime nada e sai com código 0 é sinal de cache `.pyc`
  corrompido. Apague os `__pycache__` e rode de novo.
- Mudou uma regra? Ajuste o teste que a guarda **e diga no PR por quê**.
  Teste vermelho de outro assunto se declara no PR; não se conserta por cima.

## O que costuma quebrar

- **Fim de linha.** A maior parte dos arquivos é LF, mas alguns são CRLF.
  Preserve o que o arquivo já tem. Em Python, leia e grave em bytes, ou com
  `newline=""`. `Path.read_text()`/`write_text()` trocam CRLF por LF em
  silêncio.
- **Transação.** `db.transaction()` é `BEGIN IMMEDIATE`. `audit()`, `q()` e
  `q1()` abrem conexão própria e vão **fora** do `with`. Chamada de rede
  (selo, Centrais) nunca vai dentro de transação.
- **GET não escreve.** Tela de leitura não consome contador nem grava nada.
- **Migração só acrescenta.** Use `ALTER TABLE ADD COLUMN` e
  `CREATE TABLE IF NOT EXISTS`. Não se apaga nem renomeia coluna.
- **Credencial nunca no banco nem no código.** Ela fica em `*.cred` na pasta
  de dados.
- **Texto de tela em português, tratando por «você».** Erro de regra é
  subclasse de `ValueError`, com a frase pronta para o balcão.
- **Selo e ato.** A chave de um selo no razão é `tabela + ato_id`; o id
  sozinho repete entre tabelas. Não se inventa caminho de selo que a serventia
  nunca usou.
- **Na dúvida sobre como um ato se escreve, siga o precedente real** (o
  sistema anterior, o Código de Normas, o ato já lavrado). Sem precedente,
  pergunte no PR em vez de supor.

## O que não fazer

- Não enviar nada para fora: e-mail, Central, tribunal, nuvem. Os módulos que
  enviam exigem credencial que só existe na serventia.
- Não acrescentar dependência sem dizer por quê no PR. O servidor roda
  Windows sem acesso garantido à internet.
- Não mexer em `assinatura_da_atualizacao.py` (chaves confiáveis), em
  `.github/workflows/` nem em `ci/` sem pedido explícito.
