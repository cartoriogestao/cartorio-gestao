# O arquivo XML do CENPROT, medido — e por que ele NÃO se constrói

Medido em **26/08/2026**, no acervo da CRA que o oficial trouxe da serventia de
Sergipe: **903 arquivos XML e 17.270 títulos**.

O passo do roteiro que ele serve:

```
*** TARDE: 2) gerar protesto, assinar instrumento eletrônico do protesto na
    CENPROT; 3) enviar e aprovar arquivos CENPROT (xml)
```

> **E o CENPROT é desta casa também**, não só de Sergipe. Medido no acervo de
> Cidade Exemplo: **1.194 dos 1.370 títulos têm `strChaveUnicaCENPROT`**, e as
> chaves começam com `2198765` — o código IBGE de Cidade Exemplo. Os arquivos
> `.p7s` de `C:\ARPNET\CRA` têm exatamente esses nomes: são os instrumentos
> assinados.
>
> Isto importa porque a lição do Banese ensinou a perguntar. Aqui a resposta é
> sim: **o passo se aplica**.

---

## O nome do arquivo

`SE-2801405-01-A-20200407-01.xml` — e a forma é:

`UF` - `IBGE da comarca` - `código do cartório` - **letra** - `AAAAMMDD` - `sequencial`

Para Cidade Exemplo seria `MA-2198765-…`.

### As quatro letras, medidas

| Letra | Arquivos | Versão do esquema | Ocorrências que ele leva |
|---|---|---|---|
| **A** | 283 | `1.22-apontamento` | `0` — apontamento |
| **P** | 213 | `1.22-geral` | `2` — protestado (1.651 títulos) |
| **D** | 306 | `1.22-geral` | `1` pago, `3` retirado, `A` cancelado |
| **H** | 101 | `1.22-geral` e `1.20` | **tudo misturado** — `A`,`1`,`2`,`3`,`4` |

**O que a letra `H` é não se sabe.** Ela leva todas as ocorrências juntas e é a
única que aparece também na versão 1.20. Fica `A CONFERIR`; as três primeiras
bastam para o dia.

**As ocorrências batem com o contrato que o sistema já tem.**
`protesto_cra.OCORRENCIAS`, gerado dos XSDs oficiais em `C:\ARPNET\CRA\Remessa`,
explica todas — inclusive a `5` (2.704 títulos), que é *"Devolvido por
irregularidade"*.

---

## A estrutura, e ela é a que o sistema já valida

O XML declara `versao="1.22-apontamento"` ou `versao="1.22-geral"` — **as mesmas
versões que `protesto_cra.py` carrega**. O contrato já existe; o que nunca
existiu foi escrever o arquivo.

```
estados[total,versao]
  estado[uf]
    cartorios[total]
      cartorio[codigo,comarca]
        apresentantes[total]
          apresentante[codigo]
            nome, CNPJ|CPF, tipo_apresentante, enderecos
            titulos[total]
              titulo[id]   ← a chave única de 23 dígitos
                cedente, sacador, devedores
                especie, numero_titulo, nosso_numero
                data_emissao, data_vencimento, data_apresentacao,
                data_protocolo, data_ocorrencia
                valor, saldo, protocolo, ocorrencia
                num_livro, num_folha, tipo_livro
                tipo_protesto, motivo_protesto, tipo_moeda,
                tipo_endosso, endosso, aceite
                acervo_herdado, anuencia
                instrumento_eletronico    (só em 520 de 17.270)
```

UTF-8, quebra de linha CRLF, dois espaços de indentação, datas `AAAA-MM-DD`.

### Os valores que a casa preencheu, medidos nos 17.270

| Campo | O que veio |
|---|---|
| `acervo_herdado` | `false` em **17.270 de 17.270** |
| `anuencia` | **vazio** em todos |
| `tipo_livro` | **vazio** em todos |
| `tipo_moeda` | `1` em todos |
| `motivo_protesto` | `1` (falta de pagamento) em todos |
| `tipo_protesto` | `C` comum em 17.236; `F` falimentar em 34 |
| `tipo_endosso` | `S` 10.480 · `M` 6.632 · `T` 158 |
| `endosso` | `G` 16.356 · `H` 914 |
| `aceite` | `N` 17.179 · `A` 91 |
| `num_livro` | `0` em 10.495 (61%) — só se preenche quando há protesto lavrado |
| `nosso_numero` | ausente em 114 de 17.270 |

**`instrumento_eletronico` é o PDF assinado, em base64, dentro do XML** — e
aparece em **520 de 17.270**. É o passo *"assinar instrumento eletrônico do
protesto na CENPROT"*.

---

## A CHAVE ÚNICA, e por que ela não se compõe aqui

Ela tem **23 dígitos**, em 17.270 de 17.270. E a estrutura se leu:

| Posições | Tam. | O que é | Conferido |
|---|---|---|---|
| 1–7 | 7 | **IBGE da comarca** | 2.376 de 2.376 |
| 8–14 | 7 | **protocolo**, com zeros à esquerda | |
| 15 | 1 | **um dígito verificador** | |
| 16–17 | 2 | **código do cartório** | 2.376 de 2.376 |
| 18–23 | 6 | **data**, `AAMMDD` | 2.376 de 2.376 |

Exemplo: `2801405` `0005640` `2` `01` `200330` — comarca de Carira, protocolo
5.640, verificador 2, cartório 01, 30/03/2020.

> **METADE DISTO SE RESOLVEU EM 01/09/2026, e não por engenhosidade.** O
> oficial gerou um arquivo pelo E-Ofício, e **os seis últimos dígitos são a
> data do protocolo** — conferido contra o `<data_protocolo>` do próprio XML em
> **175 de 175**. O que segue continua valendo para o bloco do meio.
>
> **E deixou de importar**, porque o mesmo arquivo mostrou que o XML devolve a
> chave **ao lado do nosso protocolo**, em 175 de 175: a serventia não compõe a
> chave, e não precisa. Ver `CENPROT_OS_DOIS_ARQUIVOS_MEDIDOS.md` e
> `protesto_cenprot.py`.

### O verificador não se explica

Testado contra **3.083 chaves distintas**:

- **módulo 11** com pesos 2–9 e com pesos 2–7, nas duas convenções de resto;
- **módulo 10** de dobra (o da FEBRABAN);
- **Luhn**;
- sobre o protocolo de 7 dígitos e sobre o prefixo de 14.

**Nenhuma acertou mais de 90%.** É a mesma parede do verificador do boleto do
aviso de intimação, e a resposta honesta é a mesma: **não se sabe**.

### A consequência, e ela decide o que dá para construir

**Sem a regra do verificador, o sistema não compõe a chave única de um título
NOVO.** E sem a chave, não há elemento `titulo id` — que é obrigatório em
17.270 de 17.270.

Isso divide o trabalho em dois:

| | |
|---|---|
| Títulos que **vieram do acervo** | 1.194 de 1.370 já têm a chave. Para eles o XML sairia. |
| Títulos **novos** | não têm chave, e o sistema não sabe compor uma. |

Construir só a primeira metade seria entregar uma funcionalidade que **quebra
no primeiro título novo** — e o balcão descobriria isso sozinho, no pior
momento.

---

## A RESPOSTA DO OFICIAL, em 26/08/2026 — e ela fecha o assunto

Perguntei de onde vem a chave única de um título novo. Ele respondeu:

> *"Serventia não gera chave única. No protesto apenas trabalhamos com os
> arquivos da CRA: recebe, manda, atualiza, e geramos os protocolos, as
> intimações e os registros de protesto com base nos requisitos legais. Não
> consta na Lei chave única de um título novo, deve vir da remessa da CRA."*

**Isso é uma definição de escopo, e não só uma resposta.** O trabalho do
Protesto desta casa é:

| O que é da casa | O que não é |
|---|---|
| receber, mandar e atualizar os arquivos da CRA | compor chave única |
| gerar o **protocolo** | gerar o arquivo do CENPROT |
| gerar as **intimações** | |
| lavrar os **registros de protesto** | |

E a Lei 9.492/1997 não conhece "chave única de título novo": o que ela exige é
protocolo, intimação e registro — que é exatamente o que o sistema faz.

### E a chave não está na remessa de 600 posições

Conferi antes de aceitar a explicação inteira, e o resultado tem de ficar
escrito: **das 1.163 chaves do acervo desta casa, ZERO aparecem nos 1.311
registros de título dos arquivos de 600 posições** que temos. Não há sequer uma
sequência de 23 dígitos começando com `2198765` dentro deles.

Então a chave chega por outro caminho — a plataforma do CENPROT, e não o
arquivo da CRA que esta casa recebe. Para o sistema, a consequência é simples:
**ele guarda a chave quando ela vier, e nunca a inventa.**

> A coluna `pt_titulos.chave_cenprot` existe desde o começo e **nunca é
> preenchida** — `para_apontamento()` não a traz, porque não há de onde. Fica
> como está, e agora está explicado por quê.

### E EM 31/08/2026 A MEDIÇÃO FOI REFEITA MAIS LARGA — e o resultado é o mesmo

A de 26/08, acima, olhou **o registro de título** dos arquivos de **2022–23**.
Ficaram dois buracos nela, e os dois importam: o lote é antigo, e olhar só os
campos que o leitor conhece não veria a chave se ela viesse num campo que o
layout não nomeia.

Refeita sobre os arquivos de **2026** — que são como a casa trabalha hoje —,
nos **quatro tipos**, e lendo o **arquivo inteiro byte a byte**:

| | |
|---|---|
| arquivos lidos | **125** — 27 remessas, 40 retornos, 29 confirmações, 25 andamentos, 2 desistências, 2 soltos |
| com a chave (`2198765` + 16 dígitos) | **0** |
| com qualquer corrida de exatamente 23 dígitos | 21 — **e são todas `00000000000000000000000`**, que é preenchimento |

Do outro lado, para o zero acima querer dizer alguma coisa: o acervo tem
**1.194 chaves preenchidas e 1.163 distintas**, em
`tbAvisoProtesto.strChaveUnicaCENPROT`.

**Isto elimina a hipótese 2 do fim deste documento** — a de que a serventia
compõe a chave e falta só o verificador — pelo lado que interessa: se ela se
compusesse aqui, não haveria por que 176 títulos do acervo estarem sem ela. E
elimina também, com dado de hoje, o *"deve vir da remessa da CRA"* da resposta
do oficial: **não vem, nem pela remessa nem por nenhum dos outros três
arquivos.** A resposta dele continua certa no que decide — *a serventia não
gera a chave* —, e o caminho por onde ela chega é a plataforma do CENPROT.

> **A coluna certa não foi a que eu procurei.** Escrevi `strChaveUnica` e o
> acervo respondeu «no such column». Quem achou foi procurar pelo **formato do
> dado** — varrer as 229 tabelas atrás de um valor `2198765` mais dezesseis
> dígitos — em vez de pelo nome que eu imaginava. **Sexta vez neste projeto**:
> não achar a coluna que procurei não prova que o dado não existe; prova que
> procurei pelo nome errado.

### O que sobra deste documento

A medição continua valendo, e é por isso que ele fica: se um dia o CENPROT
mandar a chave por um caminho que esta casa receba, a estrutura do XML está
inteira aqui, e o contrato dela já vive em `protesto_cra.py`.

**O que era "pergunta pendente" virou "fora do escopo", por decisão de quem
opera.**

---

## O que ficou medido e não se usa hoje

**De onde vem a chave única de um título novo?** São duas hipóteses, e elas
levam a construções diferentes:

1. **O CENPROT a devolve.** A serventia manda o apontamento, o CENPROT
   responde com a chave, e ela se grava no título — o que explicaria por que
   176 títulos do acervo não têm chave (nunca subiram). Nesse caso o sistema
   precisa da **integração**, e não da fórmula.
2. **A serventia a compõe.** Aí falta só a regra do verificador, e ela está
   escrita em algum manual do CENPROT/IEPTB.

**A pergunta foi feita e respondida no mesmo dia**, e a resposta está acima:
não se constrói porque não é trabalho desta casa.

> **Trabalho pendente se faz; pergunta pendente se pergunta.** Esta era
> pergunta — e perguntar custou uma conversa, enquanto construir teria custado
> dias e entregado o que ninguém usa.
