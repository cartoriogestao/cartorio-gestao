# Atualização 3.3.3 — fichas de firma e a função de cada usuário

**17/08/2026.** Construído e testado fora do ar. Nada vale no sistema enquanto o
`ATUALIZAR_SISTEMA.cmd` não rodar.

Três coisas nesta rodada. A terceira é a mais séria.

---

## 1. A lupa das assinaturas

Toda assinatura digitalizada abre com um clique, ampliável. Ver
`LUPA_DAS_ASSINATURAS.md` — está tudo lá.

---

## 2. Enviar a ficha de firma digitalizada

**O que faltava.** As 3.637 assinaturas do acervo vieram do E-Ofício. Para as firmas
**novas** não havia botão nenhum: a ficha era assinada no balcão, digitalizada, e não tinha por
onde entrar. Cartão de autógrafo sem autógrafo não reconhece nada por semelhança, que é o motivo
de o cartão existir.

**Por onde entra agora** — na tela do cartão, e também no formulário de abrir cartão novo, para
que seja um gesto só no balcão:

- escolher o arquivo
- arrastar para a área tracejada
- **colar com `Ctrl`+`V`** — digitaliza, recorta na Ferramenta de Captura, cola

**Antes de guardar**, a tela deixa girar 90°, endireitar em ângulo fino (a digitalização sai
torta) e cortar só a área da assinatura. O arquivo que você escolheu não é alterado; o ajuste
vale para a cópia que fica no cartão.

**Depois de guardada**, por baixo de cada via: escolher qual aparece no balcão, anotar a data em
que a firma foi colhida (que é outra coisa que a data em que foi digitalizada) e retirar do
cartão.

**Retirar não apaga o arquivo.** A linha sai da tela, o arquivo continua no acervo, e a auditoria
registra quem retirou e de onde. Errar o cartão ao enviar é comum e precisa ter conserto; apagar
do disco a digitalização de uma assinatura não tem conserto nenhum.

Detalhes que importam:

- **Onde fica:** dentro do acervo (`arquivos\notas\firmas\<cartão>`), que é a pasta que o backup
  já varre. Digitalização fora do backup é digitalização que se perde na primeira troca de disco.
- **Duplicata é pelo conteúdo, não pelo nome.** `digitalizar001.jpg` é o nome que todo scanner
  dá: conferir pelo nome deixaria passar a mesma ficha duas vezes e recusaria duas fichas
  diferentes.
- **PDF vira imagem** na entrada, para poder ampliar e comparar como as outras. Depende do
  `pypdfium2`, que o `ATUALIZAR_SISTEMA.cmd` agora instala. Faltando, o PDF é guardado como veio
  e a tela diz o que instalar — o envio não para por causa disso.
- **TIFF é aceito** porque é o que o scanner de mesa grava sem avisar. O servidor converte na
  hora de mostrar.
- **Um arquivo ruim não derruba os outros.** Enviando três vias e errando numa, as duas boas
  entram e a recusa diz qual foi.
- **Sem JavaScript continua funcionando** — escolher o arquivo e enviar. Perde o endireitar e o
  cortar, não perde a função.

---

## 3. Por que os atos não saíam com a função de cada usuário

Isto não era configuração. Era defeito, e estava em três lugares.

### O que estava acontecendo

Os três módulos — notas, caixa e registro de imóveis — descobriam quem estava atendendo assim:

```python
getattr(request, "usuario_nome", None) or get_setting("ri_substituta")
```

**Nada no sistema jamais definiu `request.usuario_nome`.** Não é uma linha que quebrou: é uma
linha que nunca existiu. O `getattr` devolvia vazio em toda requisição, sempre, e caía na
substituta do registro de imóveis.

Todo ato novo saía assinado por **ESCREVENTE**, qualquer que fosse quem
estivesse logado, e com a função **"Escrevente"** — porque a busca seguinte procurava no cadastro
pelo nome dela e caía no padrão.

Atingia: reconhecimento de firma, autenticação de cópia, ato de livro, recibo, orçamento,
protocolo de recepção, comprovante de prenotação e o rodapé da ficha da matrícula.

**Cadastrar a função na tela Usuários não mudava nada, e não tinha como mudar** — o nome que
chegava lá nunca era o da pessoa. Quem tentou preencher e viu que não adiantou estava certo: não
adiantava mesmo.

### O que mudou

- O nome e a função vêm da **sessão, pelo id** — não de um atributo que ninguém definia, nem de
  uma busca por nome. Nome não identifica pessoa: dois escreventes homônimos casavam na mesma
  linha, e um nome com um acento a mais não casava em nenhuma.
- **Uma implementação só**, em `app.py`, usada pelos três módulos. Eram três cópias da mesma
  regra com o mesmo defeito — e três cópias de uma regra é a garantia de que uma vai divergir.
- `get_user` passou a trazer a função junto. Faltando ali, quem monta o ato tinha de ir buscá-la
  por conta própria, e foi indo pelo nome que isto começou.
- A tela **Usuários** agora avisa, no topo, quem está ativo sem função cadastrada.

### O que NÃO se corrige sozinho

**Os atos já lavrados ficam como estão.** Já foram praticados. A correção vale para os atos
novos.

Rode o `FERRAMENTAS\DIAGNOSTICAR_FUNCOES.cmd` para saber quantos são, por módulo. Se algum
precisar ser retificado, isso é ato a ato e com a formalidade que o caso pedir — não por
atualização de sistema.

### E uma coisa que nenhum código resolve

Usuário compartilhado faz o ato sair com o nome de quem emprestou o login. Cada pessoa precisa
entrar com o seu.

---

## Na ordem

1. **`SERVIDOR\ATUALIZAR_SISTEMA.cmd`** — pede Administrador; confirme **Sim**.
2. **Menu → Usuários** — preencher a **Função** de cada um. O aviso no topo mostra quem falta.
   As opções seguem a Lei 8.935/94, arts. 20 e 21.
3. **`FERRAMENTAS\DIAGNOSTICAR_FUNCOES.cmd`** — confere se a correção chegou e quantos atos
   antigos carregam o nome errado.
4. Lavre um reconhecimento de teste e confira o rodapé.
5. **Menu → Tabelionato de Notas → Trazer notas do E-Ofício** — ainda pendente. Sem essa carga o
   banco continua com 0 cartões, e por isso nenhuma assinatura antiga abre.

---

## Arquivos alterados nesta rodada

| Arquivo | O que mudou |
|---|---|
| `static/ficha-envio.js` | **novo** — arrastar, colar, endireitar, cortar |
| `static/app.css` | aparência da área de envio e da gestão das vias |
| `templates/notas_cartao.html` | painel de envio e as ações por via |
| `templates/users.html` | aviso de quem está sem função |
| `notas_web.py` | rotas de envio, favorita, data e remoção; conversão de PDF; correção do "não encontrada nesta máquina" |
| `app.py` | `usuario_nome` e `usuario_funcao` únicos, pela sessão |
| `caixa_web.py`, `ri_web.py` | removidas as cópias defeituosas |
| `database.py` | `get_user` traz a função |
| `requirements.txt`, `SERVIDOR\ATUALIZAR_SISTEMA.cmd` | `pypdfium2` |
| `FERRAMENTAS\DIAGNOSTICAR_FUNCOES.cmd` e `.py` | **novos** |
| `tests/test_envio_da_ficha.py` | **novo** — 17 testes |
| `tests/test_funcao_do_usuario.py` | **novo** — 11 testes |
| `app.py`, `VERSAO.txt` | 3.3.2 → 3.3.3 |

---

## Conferência

- **230 testes passando** (191 que já existiam, mais 39 novos nesta e na rodada da lupa)
- O defeito da função foi **reproduzido antes de ser corrigido**: com o código antigo restaurado
  numa cópia, o teste falha dizendo
  `assert 'ESCREVENTE' == 'PESSOA EXEMPLO'` — PESSOA EXEMPLO reconheceu a
  firma, e o livro registrou ESCREVENTE. Com o código corrigido, passa.
- Envio conferido de ponta a ponta com o sistema no ar: JPG, PNG, PDF, TIFF, arquivo grande
  demais, tipo recusado, duplicata pelo hash, três vias de uma vez com uma ruim no meio, troca de
  favorita, remoção mantendo o arquivo, e a ficha enviada aparecendo na tela e abrindo na lupa
- Tela de envio conferida em 18 verificações: arrastar, colar, recusar o que não é ficha, abrir o
  editor, endireitar, girar, e deixar o PDF passar direto
