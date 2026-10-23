# Projeto — Registro de Nascimento no E-Ofício

**Documento de retomada.** Leia este arquivo por inteiro antes de começar: ele contém tudo o que já foi
descoberto, decidido e construído. O objetivo é que quem pegar o projeto do zero — pessoa ou assistente —
chegue ao mesmo ponto sem repetir investigação.

Escopo deste projeto: **nascimento em acervo** e **nascimento novo registro**. Casamento, óbito e Registro
de Imóveis ficam em projetos separados.

---

## 1. O contexto

| | |
|---|---|
| Serventia | Serventia Extrajudicial do Ofício Único de Cidade Exemplo/MA |
| CNS | 000000 |
| CNPJ | 00.000.001/0000-55 |
| Sistema | E-OFÍCIO — Automação Cartorária / MA, Versão 1.0 (Build 0.784) |
| Banco | SQL Server (SSMS instalado na máquina) |
| Acesso | a máquina Windows é operada por AnyDesk a partir de um macOS |

O problema de origem: lançar registros de nascimento no sistema interno exige digitar dezenas de campos a
partir de documentos digitalizados — DNV, documentos de identidade dos pais, entrevista com o declarante,
termo do livro. Trabalho lento e sujeito a erro de transcrição em registro público.

---

## 2. As duas telas

O E-Ofício tem **dois fluxos diferentes** para nascimento, e confundi-los é o erro mais caro possível.

### Acervo — botão vermelho "Cadastro em Acervo"

`Cadastro → Registros de Nascimento → Cadastro em Acervo`

Para **digitalizar assento que já existe no livro físico**. A numeração já existe e é **digitada**.

Cinco abas: Dados do Nascimento · Filiação 1 · Filiação 2 · Declarante · Testemunha.
Cabeçalho: Matrícula, CPF, Data Assento, Registro, Livro, Folha, Tipo Livro.

Mapa completo: `mapa_campos/nascimento.json`.

### Novo Registro — botão azul "Novo Registro"

`Cadastro → Registros de Nascimento → Novo Registro`

Para **ato lavrado agora**. A numeração é **gerada pelo sistema**.

Nove abas: Dados do Nascimento · Filiação 1 · Filiação 2 · Informações Adicionais · Declarante ·
Testemunhas · Papel Moeda · A rogo · Teor.

Mapa completo: `mapa_campos/nascimento_novo_registro.json` (59 campos).

---

## 3. O que NUNCA é preenchido pela automação

**Na tela de Novo Registro:**

- **Matrícula, Termo, Livro e Folha** — aparecem como `00000` em cinza. O sistema atribui no momento do
  registro. Digitar por cima é erro grave.
- **CPF do registrado** — emitido manualmente pela escrevente **no site do CRC** e lançado depois. O botão
  "Gerar CPF" existe na tela mas não é o fluxo desta serventia.
- **Papel Moeda** — grade de papéis de segurança numerados (série HA, fornecedor ARPENBRASIL). Escolha e
  baixa são ato da serventia.
- **Selecionar Certificado** e **Registro Tardio?** — juízo do escrevente.

**Em qualquer tela:**

- **Salvar e Registrar.** A automação nunca aciona. Ela digita; quem confere e salva é o operador.
  Registro público com erro exige averbação para corrigir — é mais caro desfazer do que digitar à mão.

---

## 4. Armadilhas descobertas em uso

Estas custaram tempo. Estão todas embutidas nos mapas, mas vale conhecer:

1. **Filiação 1 é a MÃE, Filiação 2 é o PAI.** É a convenção desta serventia — e é a ordem **inversa** à do
   termo do livro, que qualifica o pai primeiro. Quem confere lendo o termo de cima para baixo tende a
   inverter. Confira sempre o campo **Sexo** de cada aba: é a forma mais rápida de perceber a troca.
2. **Município vem pré-preenchido com CIDADE EXEMPLO** em quase todo campo, e **Nacionalidade com
   BRASILEIRA**. Quando o caso é outro, o campo precisa ser **limpo antes** (Ctrl+A + Delete) — senão o
   texto concatena e vira "CIDADE EXEMPLOIMPERATRIZ".
3. **Cada aba de filiação tem DOIS campos "Município"**: um é naturalidade, o outro é do endereço.
   Trocar um pelo outro passa despercebido na conferência.
4. **"Habilita Filiação"** precisa estar marcado para a aba aceitar dados (tela de Novo Registro).
5. **Campos de data têm calendário**: digitar por cima, não clicar no calendário. Vão **sem barras**
   (`25032021`), e a hora **sem dois pontos** (`1620`), porque os campos têm máscara própria.
6. **Na tela de acervo, "Registro" no cabeçalho é o nº do TERMO do livro**, não o protocolo. E o campo
   Livro recebe só o número (`22`); a letra vai no combo "Tipo Livro".
7. **Naturalidade por opção do art. 54, §4º da LRP**: não existe campo na tela de acervo — ficou como
   pendência. **Na tela de Novo Registro existe** campo "Naturalidade" próprio, separado do município de
   nascimento. Pergunta resolvida.

---

## 5. O pipeline

```
documentos digitalizados
        ↓  preparar.py            PDF → imagens + OCR
        ↓  leitura visual          Claude lê as imagens e escreve dados.json
        ↓  validar.py              CPF, datas, coerência entre documentos
        ↓  gerar_roteiro.py        dados + mapa da tela → roteiro.json
        ↓  gerar_pacote_registro.py  → pasta do registro com .ahk próprio
        ↓  operador                preenche na tela, confere e salva
```

### Regra que orienta tudo

**Nada é presumido.** Campo que não pôde ser lido com segurança fica vazio, com o trecho do documento
recortado para conferência humana — nunca preenchido por dedução. Divergência entre documentos não se
resolve automaticamente: registra-se em `divergencias_por_fonte` e a escolha é do escrevente.

### Os scripts

| Script | O que faz |
|---|---|
| `preparar.py` | PDF → PNG por página + OCR (tesseract). O OCR é só apoio: **os valores são lidos das imagens**, porque DNV é manuscrita e OCR erra muito |
| `validar.py` | dígito verificador de CPF, matrícula de 32 dígitos coerente com livro/folha/termo/ano, registro anterior ao nascimento, prazo legal, idade dos genitores, UF, hora, divergência entre fontes |
| `gerar_roteiro.py` | cruza `dados.json` com o mapa da tela e produz a sequência exata de digitação. **Não gera roteiro se houver ERRO na validação** |
| `folha_digitacao.py` | plano B: transforma o roteiro em folha de conferência para digitação manual |
| `gerar_pacote_registro.py` | monta a pasta fechada do registro, com `.ahk` carimbado |
| `gerar_csv_teclado.py` | versão avulsa do CSV, quando não se quer o pacote inteiro |

### O formato de `dados.json`

Cada campo carrega valor, fonte e confiança:

```json
"mae_nome": {"valor": "PESSOA EXEMPLO", "fonte": "dnv campo 14, rg_mae, termo", "confianca": "alta"}
```

- `alta` — lido com clareza em pelo menos dois documentos que concordam
- `media` — um documento só, ou manuscrito legível
- `baixa` — rasura, letra ambígua, ou fontes que discordam

Mais `divergencias_por_fonte`, `decisoes_do_escrevente` e `pendencias_humanas`.

Hierarquia das fontes: qualificação das partes → documento de identidade; dados do parto → DNV; dados do
ato → termo do livro.

---

## 6. O preenchedor (AutoHotkey)

### Por que assim

Tentei controlar o E-Ofício de fora e **não funciona** — a ferramenta de controle de aplicativo não
reconhece o programa, mesmo com ele aberto e com o nome exato que o próprio Windows sugere. Cinco
tentativas, todas recusadas.

A saída foi inverter a lógica: em vez de comandar o sistema, o script **digita no campo em que o cursor
já está**. Não clica em coordenada nenhuma, por isso não quebra quando a janela muda de posição ou
tamanho.

### Como funciona hoje

Um painel com botões (mouse é mais confiável que atalho no AnyDesk) e atalhos `Ctrl+Alt+letra`
(as teclas F viram teclas de mídia no macOS e não chegam ao Windows).

- **PREENCHER e avançar** — escreve no campo focado e passa ao próximo
- **PREENCHER TUDO** — depois de mapear a tela, preenche o formulário inteiro
- **Mapear a tela** — volta única pela tela; você clica em cada campo e ele anota a identificação interna
  em `mapa_controles.csv`. Vale para todos os registros seguintes
- **Testar digitação** / **Aprender janela** — diagnóstico

Combos e caixas de seleção são resolvidos por **controle**, escolhendo o item pela string —
não digitando a primeira letra e torcendo.

### Um pacote por registro

Cada registro tem pasta própria com `.ahk` carimbado com o nome do registrado. Três travas contra lançar
dado de um registro no assento de outro:

1. confirmação ao abrir, com nome, livro, folha e termo;
2. o `.ahk` guarda o identificador do registro e compara com o `registro.txt` da pasta — se alguém trocar
   os arquivos, ele **recusa abrir**;
3. lê apenas a própria pasta.

O `mapa_controles.csv` é a única coisa compartilhada, porque descreve o **sistema**, não o registro: o
script procura na pasta do registro e, não achando, usa o da pasta de cima.

### As abas continuam manuais, de propósito

Trocar de aba exigiria clicar em coordenada de tela. São poucos cliques por registro e o "PREENCHER TUDO"
**para sozinho** ao chegar num passo manual. Preferível a arriscar despejar a filiação do pai na aba da mãe.

---

## 7. Ambiente

- **AutoHotkey v2** (na v1 o script não abre). Há versão portátil, sem instalação e sem administrador.
- Se o E-Ofício rodar **como administrador**, o Windows bloqueia teclas vindas de programas comuns:
  abrir o AutoHotkey como administrador também. O botão "Testar digitação" diagnostica isso.
- OCR: `poppler-utils` (pdftoppm) e `tesseract-ocr`, de preferência com `tesseract-ocr-por`.
- Python 3.10+, sem bibliotecas externas além de Pillow para rotação de imagem.

---

## 8. O caso já trabalhado — PESSOA EXEMPLO

Registro de acervo, Livro A-22, folha 163, termo 18.940, matrícula
`000000 01 55 2021 1 00022 163 0018940 62`. Serve como exemplo completo e como caso de teste.

O pacote está em `preenchimento/a-22-163-18940-Pessoa Exemplo/`.

**Este registro tem divergência não resolvida** e é bom manter assim, porque exercita o que o sistema deve
fazer com conflito:

- termo do livro e DNV dizem **19/03/2021**; a certidão emitida diz **19/03/2020**;
- a idade da mãe declarada (26) só fecha com 2020; a idade do pai (40) só fecha com 2021;
- o próprio termo se contradiz: escreve "aos **três** (19) dias do mês de março";
- o ano da matrícula na certidão emitida (2020) não bate com a data do registro (25/03/2021).

Decisão registrada em 27/07/2026: adotar termo + DNV, descartar a certidão. Fica anotado que a certidão em
circulação está incorreta e provavelmente demanda retificação.

O comprovante de residência do processo está em nome de terceiro (PESSOA EXEMPLO) e com endereço
diferente do domicílio declarado.

---

## 9. Pendências

1. **Testar o preenchimento de ponta a ponta** e responder: o campo Livro aceita `22` ou `A-22`? O combo
   "Local de Nascimento" tem o rótulo exato `HOSPITAL`? A Nacionalidade do pai flexiona para BRASILEIRO?
2. **Mapear a tela de Novo Registro** com o modo de mapeamento (o mapa de campos já existe; falta a
   identificação interna dos controles).
3. **Três abas ainda não mapeadas**, porque não são formulário e precisam ser vistas em uso:
   - **Declarante** — lista com botões de adicionar/remover; parece puxar de quem já foi qualificado nas
     filiações;
   - **Papel Moeda** — grade de seleção de papel de segurança;
   - **Teor** — "Tipo de Teor = Termo" e um botão que gera o texto a partir do que foi preenchido.
4. **Confirmar se o E-Ofício em uso é produção ou homologação** antes de qualquer lançamento de teste.
   Registro público criado como teste não se apaga: exige averbação de cancelamento.
5. **Fluxo do CPF pelo CRC** — hoje é passo humano. Vale investigar se o CRC tem integração.

---

## 10. Como retomar

```bash
# 1. preparar os documentos digitalizados
python scripts/preparar.py "DNV.pdf" --id <identificacao>

# 2. ler as imagens em trabalho/<id>/ e escrever registros/<id>/dados.json
#    seguindo prompts/extracao_nascimento.md

# 3. validar
python scripts/validar.py registros/<id>/dados.json

# 4. gerar o roteiro (acervo ou novo registro)
python scripts/gerar_roteiro.py registros/<id>/dados.json --mapa mapa_campos/nascimento.json
python scripts/gerar_roteiro.py registros/<id>/dados.json --mapa mapa_campos/nascimento_novo_registro.json

# 5. montar o pacote com o .ahk próprio do registro
python scripts/gerar_pacote_registro.py registros/<id>/roteiro.json
```

---

## 11. Lições que valem repetir

**Diagnostique antes de reprocessar.** Num lote paralelo, atribuí 71 falhas à qualidade do OCR e refiz o
reconhecimento de 223 páginas. Ajudou, mas boa parte do problema era **código meu** — três bugs que uma
investigação de dez minutos teria encontrado antes de horas de reprocessamento.

**Filtro genérico derruba dado legítimo.** Bloqueei "FILHO" para evitar capturar "filha de Fulano", e com
isso descartei PESSOA EXEMPLO** oito vezes. Guarda amplo demais é tão ruim quanto
guarda nenhum.

**Compare em caixa normalizada.** Uma lista de termos proibidos em maiúsculas só funcionava quando o OCR
gravava em maiúsculas — metade dos filtros nunca disparava, e ninguém percebeu porque o resultado
"parecia" bom.

**Quando o formato tem dígito verificador, afrouxe o formato.** CPF com ponto no lugar do hífen, CNPJ
partido por traço de assinatura: aceitar a variação é seguro, porque o número só entra depois de passar
no próprio dígito verificador.

**O que a automação não consegue, ela deve localizar.** Onde a leitura não fechou, o sistema não adivinha:
recorta o trecho exato do documento e entrega ao escrevente. O trabalho humano deixa de ser procurar e
passa a ser conferir.
