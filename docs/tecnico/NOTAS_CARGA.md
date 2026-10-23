# Notas — carga do acervo e cadastro de partes

**14/08/2026.** Importador pronto e testado. Cinco segundos para o acervo inteiro.

---

## O que a carga traz

| | Entrou |
|---|---:|
| Cartões de autógrafo | **4.060** |
| Imagens de assinatura | **3.637** |
| Reconhecimentos de firma | **13.209** |
| Partes dos reconhecimentos | **13.198** |
| Termos de presença | **1.836** |
| Autenticações de cópia | **3.539** |
| Procurações | **213** |
| Escrituras | **45** |
| Partes dos atos | **483** |
| Modelos de texto | **301** |
| Livros | **4** |
| Domínios das centrais | 139 (CENSEC e DOI) |

**Rodar duas vezes não duplica nada** — provado: a segunda carga reconheceu 26.844 linhas já
existentes e não inseriu nenhuma. Um cartão digitado à mão entre as duas cargas sobreviveu
intacto. Chave estrangeira ligada nos dois testes, sem violação.

**Dez linhas foram para a quarentena**, com o motivo e o conteúdo original: um cartão sem nome,
quatro modelos de procuração cadastrados só com o título e sem texto (IMÓVEL, CAUSA PRÓPRIA,
COMPRA E VENDA DE IMOVEIS e uma ad judicia), e as repetições da segunda rodada.

---

## Dois erros que apareceram no teste, e como ficaram

**Cinco escrituras sumiam em silêncio.** Eu tinha escolhido o número do protocolo como chave
de importação, e um mesmo protocolo gera várias escrituras em sequência — o `2020.08.219`
rendeu quatro, nas folhas 48, 53, 58 e 63 do livro 28. O `INSERT OR IGNORE` descartava as
repetidas sem avisar. Chave trocada para o identificador da escritura; as 45 entram.

**Meus contadores mentiam.** A segunda carga relatava "4.060 cartões importados" tendo inserido
zero, porque eu contava por `total_changes`, que é cumulativo na conexão. Agora conta pelo
`rowcount` do próprio comando. Relatório de carga que não bate com a realidade torna a carga
incremental impossível de conferir.

---

## Cadastro de partes: aproveitar a ficha ou cadastrar do zero

É o que você pediu, e resolve um problema concreto: são 4.061 fichas de firma com o cadastro
completo — CPF, RG, filiação, estado civil, profissão, endereço. Quem comparece para uma
escritura quase sempre já assinou aqui antes. Redigitar é trabalho perdido e, pior, é fonte de
divergência: o mesmo José vira "JOSE", "José" e "Jose da Silva" em três atos, e o indicador
pessoal deixa de encontrá-lo.

**Aproveitar a ficha** — busca por nome ou por CPF e traz tudo preenchido, com a assinatura
digitalizada ao lado para conferência visual. A busca por nome casa por início de palavra:
quem digita "silva" acha "JOSÉ DA SILVA". Menos de três letras não busca, para não varrer as
4.061 fichas à toa. CPF acha com ou sem pontuação.

**Cadastrar do zero** — e o sistema avisa antes se já existe ficha com aquele CPF ou aquele
nome exato, porque cartão duplicado é o começo de um acervo que não se consulta: metade dos
atos aponta para uma ficha e metade para a outra.

**O que o sistema avisa ao trazer uma ficha**, sem impedir nada — quem decide é o tabelião:

- cartão bloqueado, com o motivo
- pessoa politicamente exposta (Provimento CNJ 88/2019, art. 20)
- restrição por terrorismo (Lei 13.810/2019)
- cartão que só admite reconhecimento por autenticidade
- CPF ou CNPJ que não passa na conferência do dígito verificador
- o que ainda falta para qualificar a parte no ato, na exigência do art. 215, § 1º, do Código
  Civil: nacionalidade, estado civil, profissão, domicílio e documento

---

## Dois cartões com CPF que não existe

A conferência do dígito verificador rodou sobre os 4.061 cartões. Dois não passam:

| CPF cadastrado | Nome |
|---|---|
| 000.000.000-00 | PESSOA EXEMPLO |
| 000.000.001-91 | PESSOA EXEMPLO |

O primeiro é preenchimento de quem precisava passar da tela. O segundo pode ser erro de
digitação de um dígito. Vale conferir os dois no documento original — o sistema vai avisar
toda vez que alguém usar essas fichas.

---

## O que falta no módulo

As telas. O esquema, o importador e o cadastro de partes estão prontos e testados; o que ainda
não existe é a interface do balcão para reconhecimento, autenticação e lavratura, e as remessas
à CENSEC, ao e-Notariado e à DOI.

O backup de hoje está em `backup_banco_2026-08-14_223349.zip`, na pasta de backups do sistema.
