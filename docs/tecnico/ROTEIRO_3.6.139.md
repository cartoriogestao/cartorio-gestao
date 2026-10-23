# ROTEIRO 3.6.139 — a certidão da matrícula que saía só com o cabeçalho

**Data:** 17/09/2026 · **Versão:** 3.6.139 (projeto) · **Servidor:** 3.6.138

> **Este roteiro existe por causa de um relato do balcão, e a correção é de uma
> linha.** O que ele traz, além do conserto, são os números que dizem **quanto
> isso pesava** — seis matrículas, e a certidão que já saiu errada — e a medição
> que me impediu de consertar o que não estava quebrado.

---

## 1. O PEDIDO, nas palavras dele

Relato **#79**, na tela da ficha `/registro-imoveis/5378`, por **escrevente**, em **17/09/2026 às 11h18**, na versão 3.6.138:

> «NÃO ESTÁ GERANDO O TEOR DA MATRICULA NA CERTIDÃO APENAS OS CABEÇARIO»

Ele está falando da **certidão de inteiro teor** da matrícula **4016** (número
4.016, ficha 5.378 no banco) — a ficha que a averbação de encerramento da 3.110
abriu pelo transporte, com a descrição perimétrica inteira da Fazenda Boa
Lembrança.

---

## 2. O QUE ESTAVA ACONTECENDO

O molde da certidão pedia **o tipo da ficha**, e não o teor:

```jinja
{% if m.tipo_ficha == "ACERVO" %}{{ teor_odf }}{% endif %}
```

A ficha 4.016 é **ESTRUTURADA**, e por isso o molde pulava o teor inteiro e
imprimia só a introdução e o fecho. **O texto estava no banco, inteiro, o tempo
todo** — quem não o levava ao papel era a condição do molde.

**A PROVA ESTÁ EMITIDA, E É DA CASA.** A certidão **10/2026**, da matrícula
**4016**, `INTEIRO_TEOR`, está gravada com **674 caracteres** e **sem o teor
dentro** (conferido procurando «BOA LEMBRANÇA» no texto congelado — não acha).

> **E os dois números desse caso não se contradizem**, embora pareçam:
> **509** é o corpo que o molde monta sem teor, medido agora nas seis;
> **674** é o corpo **congelado** na certidão 10/2026, que leva também o
> requerente e o bloco de validade. Lidos como se fossem a mesma medida, um
> deles pareceria erro de conta.

### 2.1 O tamanho, medido contra a produção

Seis fichas da casa são `ESTRUTURADA` **e têm teor**. Nas seis o papel saía com
**509 caracteres** e passa a sair com o teor inteiro:

| matrícula | caracteres de teor | papel antes | papel agora |
|---|---|---|---|
| **4016** | 5.294 | 509 | **5.804** |
| **4017** | 8.101 | 509 | **8.611** |
| **4018** | 11.500 | 509 | **12.010** |
| **4019** | 10.510 | 509 | **10.964** |
| **4020** | 13.123 | 509 | **13.557** |
| **4021** | 9.118 | 509 | **9.565** |

**São seis, e não uma** — a escrevente topou com a 4016 e as outras cinco estavam
esperando a próxima pessoa pedir certidão delas.

---

## 3. O CONSERTO

### 3.1 O molde — `ri_odt.py`

A pergunta passou a ser pelo **teor**, que é o que se quer imprimir:

```jinja
{% if teor_odf %}{{ teor_odf }}{% endif %}
```

### 3.2 A segunda metade — `ri_web.py`

O teor indo ao papel tem uma consequência: **o ato que o teor já conta não pode
aparecer duas vezes** na certidão. A conta que decide isso já existia
(`ri_numeros_do_teor.atos_fora_do_teor`), e o que mudou foi a pergunta que a
liga:

```python
teor_vai_ao_papel = (m["tipo_ficha"] == "ACERVO") or not para_odt
```

**Ela é uma linha, e serve a dois papéis que não imprimem a mesma coisa:**

- a **FICHA** (`para_odt=True`) imprime o teor **só quando é acervo** — decisão
  de 16/09/2026, com teste próprio. Na ficha estruturada o teor não sai; tirar
  da lista o ato que ele conta **apagaria o ato do papel**, e ato que some do
  papel é pior que ato repetido;
- a **CERTIDÃO** (`para_odt=False`) imprime o teor **sempre que ele existe** — é
  o relato #79. Aqui a regra vale inteira.

---

## 4. O QUE EU QUASE CONSERTEI SEM MOTIVO — e a medição que me parou

O teor da 4.016 **já traz, dentro dele, uma linha de assinatura**. Eu escrevi, na
primeira versão deste conserto, que a certidão sairia com **duas** linhas de
assinar, e comecei a construir uma guarda contra isso.

**Fui ler o molde, e o papel não existe.** `MODELO_CERTIDAO_PADRAO` fecha com
«Era o que nela continha.», com o «Dou fe.» da validade e com o bloco de quem
assina a certidão — e **nunca chama `abertura_fecho` nem `abertura_assinatura`**.
A via da digitalização monta outro corpo e também não. Quem imprime esses dois
pedaços é **o molde da FICHA, e só ele**.

**Todo o medo era de uma coluna, e não de um papel.** Deduzi do campo
`abertura_*` que a certidão os imprimia — «dado cru não é resposta; a resposta é
o que a função devolve». O que ficou escrito no código é a **medição**, e há
teste que fica vermelho se o molde da certidão passar a chamar os dois pedaços.

---

## 5. O QUE MUDA NO PAPEL DA CASA — medido, e o que NÃO muda

A promessa de que o conserto não mexe em nada além do defeito **se mede, e não se
afirma**. Passei **todas as 1.985 fichas** da casa pelos dois moldes, o de antes
e o de agora:

| | |
|---|---|
| fichas que mudam de papel | **6** |
| todas elas | `ESTRUTURADA` com teor |
| **as 1.979 do acervo** | **idênticas, uma a uma** |

**Zero certificados de acervo mudam.** É o outro lado do conserto: o que o
balcão imprime todo dia continua saindo exatamente como saía.

---

## 6. O EMPACOTADOR NÃO LEVA MAIS O MATERIAL DE TRABALHO

Não é do relato #79, e entrou no mesmo pacote porque é o pacote.

O empacotador levava **tudo** que estivesse na pasta do programa — inclusive o
material de rascunho de quem edita o sistema. Medido agora: **280 arquivos e
0,55 MB** de coisa assim (`_crops_matricula/`, `_preview_fichas/`,
`_patch_*.py`, `_pub_sem_numero.ps1`, restos de medição) iriam para a máquina do
balcão a cada atualização.

**E não é hipótese: já chegou.** Comparando a instalação com a árvore, há **49
arquivos que existem só na máquina do servidor** e são exatamente isso —
`_patch_ficha_qr.py`, `_sim_3110/`, `_sim_teor.json`, `*.bak-selo-20260915-*`.
São inertes, não quebram nada, e têm cara de resposta para quem os abrir.

A regra nova (`EXCLUDE_UNDERSCORE_NA_RAIZ`) tira **o que começa com `_` no nível
de cima**. É de nível de cima de propósito: `templates/_cobrar.html` e
`templates/_fraude.html` são **macros do sistema**, começam com `_`, e continuam
viajando — a regra é da raiz, não do nome.

### 6.1 O QUE AINDA VAI, E EU NÃO TIREI — declarado, e medido

A regra do underscore pega **280 dos ~318** arquivos de trabalho da raiz. **Os
outros 34 continuam viajando**, e eles não começam com `_`:

| | |
|---|---|
| 40 `.py` de raiz que **ninguém importa** | **88,5 KB** |
| destes, chamados por `.cmd`/`.bat` | **2** (`admin_cli.py`, `migrar_v2.py`) — **não são lixo** |
| destes, com `_` | 4 — já saem pela regra nova |
| **os que continuam indo** | **34** |

São `fix_*.py` (8), `patch_*.py` (5), `invest_*.py` (3), `scan_*.py` (3),
`verify_*.py` (3), `check_*.py` (2), `map_*.py` (2), `export_*.py` (2), e
`tmp_fix_insert3.py`, `dump_modelo_cert.py`, `previa_inteiro_teor_exemplo.py`,
`apply_cab_compacto.py`, `aplicar_natureza_averbacao.py`, `inspect_layout2.py`,
`ler_pdfs_mat.py`, `mats_meta.py`, `ocr_check_pares.py`, `varrer_ocr_lote.py`,
`hot_publish_selo_averbacao_arquiv.py`.

**Eu não os tirei, e a razão é a regra da casa.** Excluir por **padrão de nome**
(`fix_*`, `patch_*`) é adivinhação: no dia em que um `patch_*.py` for de
verdade, ele some do pacote sem ninguém ver — e a instalação fica sem o
conserto. O caminho certo é uma **lista declarada**, com a mesma forma de
`FORA_DA_VARREDURA`: nome por nome, datada, e o teste que a guarda. **É decisão
sua**, e ela é pequena: 88,5 KB, e nenhum deles é importado por ninguém.

> **E o que isso mostra é o limite da minha regra.** Eu tirei os que tinham uma
> marca visível (o `_`); os que não têm marca continuam indo. **Marcar o óbvio e
> calar sobre o resto seria carimbo que mente por omissão** — quem lesse «o
> pacote não leva mais material de trabalho» acharia que está limpo, e não está.

---

## 7. O QUE CONFERIR DEPOIS DE APLICAR

1. **Abra a ficha `/registro-imoveis/5378` e emita a certidão de inteiro
   teor.** O teor tem de estar lá: a descrição perimétrica da Fazenda Boa
   Lembrança, ~5.800 caracteres no lugar dos 509 do cabeçalho.
2. **Emita uma certidão de matrícula de acervo** (abaixo de **4.015**) e
   compare com uma que já tenha saído: tem de ser **a mesma coisa**.
3. **O carimbo da versão** tem de dizer **3.6.139** (no rodapé da tela ou em
   Administrativo → Saúde). Se ainda disser 3.6.138, **a atualização não
   subiu** — e o teor continuará faltando na certidão.

---

## 8. O QUE ESTE PACOTE LEVA

Quatro arquivos de programa, e nada mais:

| arquivo | o que é |
|---|---|
| `ri_odt.py` | o molde da certidão — a correção do #79 |
| `ri_web.py` | o teor indo ao papel, e os comentários que registram a medição |
| `tools/criar_atualizacao.py` | a regra do material de trabalho |
| `notas_do_desenvolvimento.py` | a nota do #79, com a prova de cada afirmação |

Mais o **`CLAUDE.md`** e este roteiro, que viajam por caminho próprio.

**Os outros 1.201 arquivos de programa da árvore estão byte a byte iguais aos da
instalação** — conferido por SHA-256 antes de empacotar. O que o oficial aplica
não vai mexer em nada que já está funcionando.
