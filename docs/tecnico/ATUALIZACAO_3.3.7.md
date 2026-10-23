# Atualização 3.3.7 — depósito espelhado, QR sem internet, duas fichas de uma vez

**17/08/2026.** Nada vale enquanto o `SERVIDOR\ATUALIZAR_SISTEMA.cmd` não rodar.

---

## 1. Como instalar o segno (o QR do selo)

**A resposta curta:** rode o `SERVIDOR\ATUALIZAR_SISTEMA.cmd`. Ele já instala.

**A resposta que importa:** ele agora instala **sem precisar de internet**.

O `pip` busca na internet. Servidor de serventia nem sempre tem, e quando tem, a rede às vezes
bloqueia — e nesses casos a atualização terminava sem erro visível e o recurso simplesmente não
funcionava. A etiqueta saía sem QR e ninguém sabia por quê.

Por isso a pasta nova **`SERVIDOR\DEPENDENCIAS`**, com as bibliotecas já baixadas:

| Arquivo | Para quê |
|---|---|
| `segno-1.6.6-py3-none-any.whl` | desenha o QR do selo na etiqueta |
| `pypdfium2-4.30.0-...win_amd64.whl` | converte ficha de firma em PDF para imagem |

O `ATUALIZAR_SISTEMA.cmd` instala **daqui primeiro** e só recorre à internet se faltar algo. A
internet virou plano B, não plano único.

### Se quiser instalar só o QR, sem atualizar o resto

**`FERRAMENTAS\INSTALAR_QRCODE.cmd`** — pede Administrador, não precisa de internet, e ao
terminar diz como reiniciar o servidor.

### À mão, se preferir

```
"%PROGRAMDATA%\CartorioGestao\runtime\Scripts\python.exe" -m pip install ^
   --no-index --find-links "C:\...\CartorioGestao\SERVIDOR\DEPENDENCIAS" segno
```

Depois reinicie o servidor:

```
schtasks /End /TN CartorioGestaoServidor
schtasks /Run /TN CartorioGestaoServidor
```

### Conferir

**`FERRAMENTAS\DIAGNOSTICAR_ETIQUETA.cmd`** responde em dez segundos, separando os três casos que
têm o mesmo sintoma: o código não instalado, a biblioteca faltando, ou nenhum ato com selo.

**Se não der de jeito nenhum**, a etiqueta continua saindo com o **número do selo impresso**. Só
o QR fica de fora. Nenhum ato deixa de ser praticado por causa disso.

---

## 2. O depósito prévio, espelhado

O mesmo depósito, visto de onde fizer sentido — **um registro só**, não uma cópia em cada tela.
Duas anotações do mesmo dinheiro divergem no dia em que uma for corrigida e a outra não.

**Onde se lança agora:**

- **Caixa → Depósito prévio** (como antes)
- **Registro de Imóveis → o título**, na tela da prenotação
- **Tabelionato de Notas → o ato de livro**, onde a escritura está

**Onde aparece:** na tela do caixa, cada depósito agora diz **a que título ou ato pertence**, com
link para lá. Antes, um depósito lançado no balcão ficava no caixa sem dizer a que veio — e quem
conferia no fim do dia não tinha como saber. Sem vínculo nenhum, a tela diz "sem vínculo", porque
dinheiro deixado *para quando o título chegar* existe e não é defeito.

**Uma implementação só.** A criação do depósito vive em `caixa_depositos.py`, e as três telas
chamam a mesma função. Havia um teste que impedia duas cópias; agora ele cobre as três. É a mesma
armadilha que produziu o defeito da função do usuário nesta semana — a mesma regra escrita em três
arquivos, e um deles divergindo em silêncio.

---

## 3. Duas fichas de uma vez — e um defeito sério que isso revelou

**O que você pediu:** facilitar o envio de dois arquivos no cadastro de fichas (frente e verso).

**O que eu encontrei ao mexer:** a versão anterior aceitava vários arquivos mas só sabia trabalhar
com um. Escolhendo frente e verso e **girando qualquer um dos dois**, o envio descartava a lista e
mandava um blob só — **o outro arquivo sumia**. Sem erro, sem aviso, sem nada na tela.

Isso é pior do que recusar o segundo arquivo: quem enviou viu os dois na tela, apertou Guardar,
leu "ficha guardada" e foi embora. O verso do cartão simplesmente não existia.

**Como ficou:**

- **Fila de arquivos** com miniaturas. Dois arquivos ficam rotulados **frente** e **verso**.
- **Escolher de novo acrescenta**, não substitui — digitalizar a frente, escolher, digitalizar o
  verso e escolher outra vez é o caminho normal, porque o scanner faz uma folha por vez.
- **Cada ficha tem o seu próprio giro, ângulo e corte.** A que está selecionada é a que o editor
  mostra; as outras guardam os seus ajustes.
- **O envio percorre a fila inteira**: o que foi ajustado vai ajustado, o que não foi vai como
  veio, e nada some.
- Tirar da lista com o × ; o botão diz quantas vão (`Guardar 2 fichas no cartão`).
- Arquivo de tipo não aceito fica marcado na fila e **não é enviado**, sem derrubar os outros.

**Mais um defeito mudo, encontrado no teste:** se o painel fosse ligado duas vezes, nasciam duas
filas rivais — as duas escutando o mesmo arrastar, e a última a desenhar apagava a tela da outra.
O operador soltaria frente e verso, veria um arquivo só, e não teria como saber que o outro estava
preso numa fila invisível. Agora o painel se recusa a ser ligado duas vezes.

---

## Na ordem

1. **`SERVIDOR\ATUALIZAR_SISTEMA.cmd`** — leva o código e instala o segno da pasta local.
2. **`FERRAMENTAS\DIAGNOSTICAR_ETIQUETA.cmd`** — confirma que o QR está de pé.
3. Imprima uma etiqueta e **aponte o celular para o QR**. É o teste que nenhum script faz.
4. Menu → **Usuários** — preencher a Função de cada um, se ainda não foi feito (v3.3.3).

---

## Arquivos alterados

| Arquivo | O que mudou |
|---|---|
| `SERVIDOR\DEPENDENCIAS\` | **nova** — os `.whl` do segno e do pypdfium2, com LEIA-ME |
| `FERRAMENTAS\INSTALAR_QRCODE.cmd` | **novo** — instala só o QR, sem internet |
| `SERVIDOR\ATUALIZAR_SISTEMA.cmd` | instala da pasta local antes de tentar a internet |
| `caixa_depositos.py` | vínculo com ato de notas; a consulta do espelho num lugar só |
| `caixa_schema.py` | `cx_depositos.nt_ato_id` |
| `caixa_web.py` | a tela do caixa mostra a que título/ato cada depósito pertence |
| `notas_web.py` | depósito prévio no ato de livro |
| `templates/notas_ato.html` | painel do depósito |
| `templates/caixa_depositos.html` | a coluna do vínculo, com link |
| `static/ficha-envio.js` | **reescrito** — fila de arquivos, cada um com os seus ajustes |
| `static/app.css`, `templates/notas_cartao.html` | a fila na tela |
| `tests/test_envio_da_ficha.py`, `tests/test_protocolo_reabrir.py` | testes novos |
| `app.py`, `VERSAO.txt` | 3.3.6 → 3.3.7 |

---

## Conferência

- **287 testes passando** (191 que já existiam, mais 96 desta semana)
- **Instalação offline do segno provada**: num ambiente limpo, sem rede, instalando do `.whl` da
  pasta — `segno 1.6.6 instalado sem rede`
- **O defeito dos dois arquivos foi reproduzido e corrigido**, com 15 verificações na tela: dois
  arquivos entrando, rótulo frente/verso, escolher acrescentando, ajuste isolado por ficha, e o
  ponto central — **as três enviadas** quando só uma foi editada
- Espelho conferido nos dois sentidos: depósito lançado no título aparece no caixa com link, e
  depósito lançado no ato de notas aparece nas duas telas sendo **um registro só**
