# A linha em branco que sumia em todos os papéis da casa

Achado em **31/08/2026**, medindo o relato **#27** do oficial. É o defeito mais
espalhado que este projeto encontrou por acidente: **80 linhas em branco, em
sete módulos, nenhuma chegando ao papel.**

---

## Como ele apareceu

O relato #27, inteiro:

> *"a ficha de assinatura do reconhecimento de firma nao vai assinada pelo
> oficial. A ficha de assinatura só vai assinada pelo cliente, **precisa de
> mais espaço livre para desenvolver a assinatura**, algo como dois campos em
> aberto para assinatura livre e um campo para rubrica"*

A primeira metade eu já tinha lido ao contrário, e o oficial me corrigiu:
*"você entendeu errado, o oficial não assina a ficha de assinatura, só o
cliente"*. A segunda metade — **o espaço** — ficou por fazer, e a razão é que
eu a tinha dado por respondida pelos três campos que já existiam.

Fui atender o pedido: o corpo da ficha punha **três linhas em branco** entre o
rótulo de cada autógrafo e a linha de assinar, e passei para cinco. Escrevi o
teste, rodei, e ele disse **zero**.

Fui atrás do teste, achando que era ele. **Era a ficha.** As três nunca tinham
saído.

---

## O defeito

`ri_odt.html_para_odf` descarta o parágrafo cujo texto fica vazio depois do
`.strip()`:

```python
def _fecha(self):
    texto = "".join(self._buf).strip()
    self._buf.clear()
    if texto:                                  # ← e se não houver texto, nada
        self.saida.append(f'<text:p …>{texto}</text:p>')
```

Para **HTML colado de fora** isso é limpeza justa: um teor copiado de um editor
vem cheio de parágrafos vazios que ninguém escreveu.

Para **`<p></p>` escrito à mão no código** é a perda silenciosa da única coisa
que aquela linha faz.

### Medido: quantos dependiam disso

| módulo | `<p></p>` |
|---|---|
| `notas_web.py` | 30 |
| `atribuicoes_web.py` | 17 |
| `habilitacao_web.py` | 13 |
| `ri_odt.py` | 11 |
| `caixa_web.py` | 4 |
| `nucleo_web.py` | 3 |
| `ri_web.py` | 2 |
| **total** | **80** |

São os papéis que a serventia imprime e entrega: ficha do cartão de autógrafo,
termos de livro, certidões, recibos do caixa, comprovante de prenotação,
traslado, habilitação de casamento.

---

## O conserto, e o que ele exigiu de precisão

A tentação é fazer `_fecha()` emitir um parágrafo vazio quando não há texto.
**Não funciona**, e a razão é que `_fecha()` é chamado nos dois momentos —
na abertura do `<p>` (para fechar o anterior) e no fecho dele. Nos dois o
buffer está vazio, e ali não há como distinguir um do outro.

A segunda ideia — *"emitir quando qualquer bloco fechar vazio"* — produz uma
linha solta em `<div><p>a</p></div>`: o `</div>` chega com o buffer já
esvaziado pelo `</p>`, e viraria um branco que ninguém pediu. **E o teor das
matrículas do acervo vem cheio de `div`.**

A marca que decide é **o fecho de `</p>`, e só dele**:

```python
if tag in self.BLOCO:
    if tag == "p" and not self._buf:
        self._linha_em_branco()      # <text:p/>
        self._centro = False
    else:
        self._fecha()
```

E o parágrafo vazio **não leva estilo**: `P-just` justificaria o nada e
`P-centro` o centraria. O que se quer ali é altura de linha.

> **`_centro` é estado, e estado que não se limpa contamina o vizinho.** A
> linha em branco entre dois parágrafos faria o seguinte nascer centralizado.
> Há teste.

---

## E ELE VALE PARA O `<p></p>` DA CASA, E NÃO PARA TODO PARÁGRAFO VAZIO

Foi a medição contra a produção que impôs esse limite, e ela foi feita **antes
de decidir**:

| | |
|---|---|
| matrículas do RI com teor | 1.508 |
| **ganhariam linha em branco** | **1.057** |
| linhas em branco novas, ao todo | 1.757 (pior caso: 15 numa ficha) |
| crescimento médio | **11,8% dos parágrafos** |
| atos das Notas afetados | **0** |

E as do RI não são `<p></p>`. São
`<p lang="pt-BR" style="text-align:justify;text-indent:0pt;margin-left:0pt">` —
**a exportação do editor do E-Ofício**, que é exatamente o caso para o qual a
limpeza do conversor foi feita.

### Por que isto não se decide sozinho

Se o E-Ofício desenhava aqueles parágrafos como linha em branco, repô-las é
**reproduzir o livro**, que é o que uma certidão de inteiro teor faz. Se eram
sobra do editor, é **esticar 1.057 certidões sem motivo**.

**Não dá para medir**: das 369 certidões do acervo, uma só guarda o corpo.

Então o conserto ficou no que é inequívoco — `<p></p>` **sem atributo**, que é
a forma que o código desta casa escreve, nas 80 ocorrências — e a outra metade
virou pergunta ao oficial, com o número medido ao lado. Trocar de volta é uma
linha, no dia em que ele responder.

> **Mudar a cara de 1.057 papéis que a serventia assina, calado e por
> suposição, é o contrário do que esta casa faz.** Conferido depois do escopo:
> as 1.508 fichas de produção ganham **zero** linhas.

---

## Três lições, e as três já têm nome neste projeto

### 1. O teste que mede espaço não pode colapsar espaço

O primeiro teste que escrevi lia o `.odt` com o extrator que já existia:

```python
return " ".join(re.sub(r"<[^>]+>", " ", bruto).split())
```

Ele responde bem à pergunta *"o texto está lá?"* — e é para isso que existe.
Para medir **espaço** ele não serve: `split()` colapsa exatamente o branco que
se quer contar. **O branco é o conteúdo aqui, e tinha de sobreviver à
leitura.** `_paragrafos_do_odt` é o par dele.

### 2. Defeito de papel não grita

Ninguém abre o XML de dentro do `.odt`; olha-se a folha impressa. E na folha,
*"faltam duas linhas em branco"* não chama atenção de ninguém — o papel sai,
parece um papel, e se arquiva. **O oficial percebeu porque é ele quem vê o
cliente assinando**, e a assinatura não cabia.

É a mesma forma dos sete defeitos de 27/08 que chegaram pela janela da ajuda e
nenhum por teste: **quem está no balcão vê o que a suíte não vê**.

### 3. Meia leitura de um pedido é pior que nenhuma

O relato #27 tinha duas metades — *quem assina* e *quanto espaço* — e eu tratei
a primeira, errei nela, fui corrigido, consertei, e **dei o relato por
entendido**. A segunda metade continuou lá, escrita na mesma frase.

A nota do desenvolvimento chegou a dizer que faltava *"a assinatura do
oficial"*, que é justamente o que ele mandou tirar. **Nota que envelhece é
carimbo que mente**, e esta mentia sobre uma correção que ele mesmo tinha
feito.

---

## O que fica

- `ri_odt.py` — o conserto, com o porquê ao lado
- `tests/test_linha_em_branco_no_odt.py` — sete testes: o vazio sai, a `div`
  não vira branco, o centro não escorrega, e a ficha tem o espaço
- `tests/test_cartao_assinatura.py` — os dois testes do relato #27: cinco
  linhas de espaço por autógrafo, e um **teto de crescimento** da ficha

---

## E EU QUASE GRAVEI AQUI UMA AFIRMAÇÃO QUE NÃO TINHA MEDIDO

Escrevi, nesta mesma passada, que o guarda de tamanho *"impede o conserto de
virar outro problema: ficha de duas páginas se arquiva com a segunda solta"*.
Batizei o teste de **«a ficha continua cabendo numa folha»** — e ele contava
**parágrafos**, com teto de 90. Parágrafo não é folha.

O LibreOffice está nesta máquina. Convertido e contado:

| linhas em branco por autógrafo | páginas |
|---|---|
| 0 | **2** |
| 3 | **2** |
| 5 | **2** |

**A ficha já eram duas páginas, e o espaço não custou folha nenhuma.** Ela não
cabe numa por causa da tabela de qualificação, dos quadros de foto e digital e
do fecho — nada disso tem a ver com este conserto.

Duas coisas ficaram erradas por um instante, e as duas eram minhas: um teste
cujo **nome afirmava o que ele não media**, e um documento justificando o
conserto por um risco que não existia. **Carimbo que mente, dentro do arquivo
que fala sobre carimbo que mente.**

> Pôr o cartão numa folha só é **decisão de layout do oficial** — sairia
> tirando linhas da qualificação ou diminuindo o corpo da letra —, e não
> consequência deste conserto. Fica dito, com o número medido ao lado.
