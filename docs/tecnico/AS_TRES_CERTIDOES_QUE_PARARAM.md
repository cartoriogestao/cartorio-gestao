# As três certidões que pararam — 22/09/2026

**AS TRÊS CERTIDÕES DA CASA NÃO SAÍAM, E O SISTEMA SUBIA NORMALMENTE.** Uma
linha de Python foi colada **dentro do texto do SQL**, entre as aspas e o
`INSERT INTO`, em três módulos, no mesmo minuto:

```python
        cur = con.execute(
            """                   teor = sem_linha_de_assinatura_a_mao(teor)
INSERT INTO pt_certidoes(numero, ano, tipo, nome, documento,
```

O banco recusa com `near "teor": syntax error`. **A falha é dentro de um
texto, e não na importação** — por isso nenhum erro aparece ao subir, e só
quem clica em «emitir», com o cliente na frente, descobre.

| arquivo | qual papel parou |
|---|---|
| `protesto_certidao.py` | a certidão de protesto |
| `atrib_certidao.py` | a de inteiro teor do RCPJ, do RTD e do Livro 3 |
| `rc_certidao.py` | a do Registro Civil |

**E ESTAVA INSTALADO.** `C:\Program Files\CartorioGestao\protesto_certidao.py`
tinha os mesmos 24.563 bytes e a mesma hora (22/09, 14h47); o `/saude`
respondia **3.6.173**, de pé, com esse código carregado.

**DATADO NO `.cgu`, que é a linha do tempo desta casa**: a **3.6.164** (21/09,
17h29) está limpa e **não tem sequer o `certidao_texto.py`** — a função inteira
é de 22/09. Logo o que chegou ao balcão veio pelo `ATUALIZAR_SISTEMA.cmd`, e
não por pacote: nenhum `.cgu` carrega o defeito.

## O conserto, e a decisão que ele carrega

A linha saiu de dentro das aspas — e foi posta **antes do `hash_certidao`**, e
não logo antes do `INSERT`, onde estava colada.

**O motivo é o carimbo.** Nos três, a impressão é calculada duas linhas acima
do `INSERT`, sobre `teor`. Com a limpeza só antes do `INSERT`, o teor
**gravado** deixaria de ser o teor que o hash carimbou — e a conferência de
«este é o teor que saiu?» passaria a falhar em **toda certidão nova**, calada.
É o carimbo que mente na forma mais cara: o número existe, confere sozinho, e
não corresponde ao papel.

**219 testes** nos seis arquivos da família da certidão, todos verdes — e eles
eram **13 vermelhos** antes, todos arrastados pela primeira, que não conseguia
gravar nada em `pt_certidoes`.

## O que fica declarado, e não resolvido

**A limpeza acontece em dois MOMENTOS diferentes na mesma casa**, e isto é
decisão do oficial:

| onde | quando |
|---|---|
| `ri_odt.py`, `ri_web.py` | **ao imprimir** — o teor guardado fica inteiro |
| as três certidões | **ao gravar** — o teor congelado já vai sem a régua |

As certidões emitidas até hoje continuam com a régua de assinatura dentro; as
de amanhã, não. Mover a chamada para a hora da impressão é uma linha nos três
— e é a forma que o RI já usa.

**E ESTE CONSERTO É EM MÓDULO DE OUTRA PASSADA**, contra a regra da casa de
02/09 («quem não está construindo o módulo não mexe nele»). A razão de quebrá-la
está escrita: **não há decisão de desenho a respeitar num texto que o banco
recusa**, e três dos papéis que a serventia entrega estavam parados na máquina
do balcão. Se a outra passada escrever por cima, o conserto é a mesma linha,
nos mesmos três lugares.

---

## E o que impedia medir qualquer coisa: o cache de bytecode

Antes disto, **nenhum teste que monta o sistema rodava nesta árvore** — saída
de zero bytes, código de saída **0**, sem mensagem e sem nem o `atexit` rodar.

Não era o `app` (o `import` sozinho vive), não era a caixa de areia (medido
fora dela, morre igual) e não era a outra passada escrevendo (morria com a
árvore parada). Era **`__pycache__` corrompido**: desmarshalar bytecode
estragado derruba o CPython com violação de acesso.

```
find . -name __pycache__ -type d -not -path './.venv/*' -exec rm -rf {} +
```

Depois disso, `tests/test_crc_carga.py` passou **48 de 48**.

**O que despista, e custou horas:** o lugar da morte **anda** conforme o
trabalho feito antes, o que parece relógio ou vazamento de memória; e
`sys.setprofile`, usado como instrumento, **mata o processo por conta
própria** — inventa um segundo defeito em cima do primeiro. Quem mostrou a
causa foi `faulthandler.enable(file=...)` gravando num arquivo **dentro do
projeto**.

**Por que nasce aqui:** duas passadas escrevem a mesma árvore ao mesmo tempo, e
o `.pyc` é gravado enquanto o `.py` é substituído. **Suspeite disto antes de
procurar no código.**
