# O Next Cloud SAS do ONR — dá para integrar?

    «verifique a possibilidade de integrar o next claud sas da onr no nosso
     sistema»                                     — o oficial, 04/09/2026

**Dá, e é a modalidade certa para esta casa.** O que segue é medido: o manual
do ONR, os dez documentos que ele cita, e o disco e o banco desta serventia.

---

## Antes de tudo: o manual estava na casa, e eu não o tinha lido para isto

`FONTES_EXTERNAS/onr_ri/manual_integracao_cartorios.pdf`, versão 3.7, 27
páginas, na casa desde 03/09/2026 — quando se construiu a API do ONR. **Ele
traz «Next Cloud SAS» em 10 das 27 páginas**, e a apresentação da página 2 é
sobre isso e mais nada.

> **É «não achar onde procurei não prova que não existe» pela oitava vez —
> e a pior delas.** As sete anteriores foram coluna do acervo, ou fonte que eu
> não sabia existir. Esta era um documento **que eu mesmo tinha baixado**, e
> que eu li procurando endpoints. **Ler um documento para uma pergunta não é
> tê-lo lido.**

E há uma correção de conteúdo junto. Em 04/09 eu escrevi que a digitalização
**não sobe pela API do ONR**, porque `POST /v1/protocolo` diz «onde não deve
possuir anexo». A conclusão estava certa e a razão, curta demais:

| o que eu disse | o que está medido |
|---|---|
| «o único binário da API é o XML do indicador» | **`POST /v1/protocolo/lote` aceita anexo** — e o campo `arquivos` é `{nome, url}`: o ONR **não recebe o arquivo, recebe um LINK** e vai buscar |
| — | e as imagens das matrículas **têm canal próprio**, que não é a API: ou o Web Service da serventia, ou o **Bucket** do Next Cloud SAS |

---

## O que o Next Cloud SAS é

**Não é uma API para o nosso sistema falar.** É **infraestrutura no Google
Cloud Platform** que o ONR abre por serventia:

| | |
|---|---|
| **Bucket** (Cloud Storage) | as **imagens do Livro 2** |
| **Firestore em modo Datastore** | o **Indicador Pessoal Simplificado (IPS)**, o antigo BDL |

O projeto é dedicado e exclusivo desta serventia, em território brasileiro. **O
oficial é o controlador** (LGPD, art. 5º, VI) e gerencia o acesso no Console do
Google Cloud — **inclusive o acesso do próprio ONR, que é restrito a LEITURA e
só por API**.

**E quem sobe os dados são DOIS PROGRAMAS QUE O ONR INSTALA AQUI:**

| programa | o que sobe | para onde |
|---|---|---|
| **IPS** | Indicador Pessoal Simplificado (Livro 5) | Firestore |
| **CSL2** | imagens das matrículas (Livro 2) | Bucket |

Carga completa primeiro, e depois **carga incremental diária**, com
criptografia ponta a ponta. **O monitoramento é do ONR**, e a serventia recebe
e-mail diário com as ocorrências.

> **ISSO MUDA A NATUREZA DA PERGUNTA.** «Integrar o Next Cloud SAS no nosso
> sistema» não é escrever um cliente de API — é o nosso sistema **alimentar**
> o que aqueles dois programas leem. E, medido abaixo, **a pasta que o CSL2 lê
> é a que esta casa já tem**.

---

## São duas modalidades, e o ONR recomenda a outra — mas ela não cabe aqui

| | |
|---|---|
| **(a) Web Service próprio** | `[recomendado]` pelo ONR |
| **(b) Next Cloud SAS** | para quem «não dispõe de infraestrutura suficiente» |

O que a (a) exige, do próprio manual (item 8.1):

- link **dedicado**, mínimo 512 kbps;
- **servidor virtual ou dedicado em Data Center no território nacional**, com o
  endereço físico e o IP comunicados ao ONR;
- quad-core ou 8 vCPU, 8 GB de RAM, 2 × 250 GB em RAID, backup diário com
  retenção de 7 dias;
- **VPN**;
- **em operação 24×7×365**, «não podendo ser desligado em períodos fora do
  expediente, de feriados e finais de semana».

**Esta casa não tem nada disso, e não é falta de zelo: o servidor é a máquina
do balcão.** Um web service 24×7 exposto a partir dela seria pôr o banco da
serventia atrás de um link comum — e é justamente o que a modalidade (b) existe
para evitar.

**A integração é sem despesa** — o manual diz «mediante simples solicitação, sem
nenhuma despesa». Ele **não diz quem paga o Google Cloud**, e eu não vou supor:
é uma das perguntas ao ONR.

---

## O formato das imagens é EXATAMENTE o que esta casa já tem

O que o ONR manda (`instrucoes_imagens_livro2.pdf`, versão 2.2):

- **TIFF, 200 × 200 dpi**, sem compressão ou com compressão **sem perdas** —
  CCITT G3 1D, G3 2D, **T.6 (Group 4)** ou LZW;
- pastas de **8 dígitos**, agrupando **de mil em mil**: `00000000` guarda as
  matrículas 1 a 999, `00000001` guarda 1000 a 1999;
- Single-TIFF: `99999999.9999` — uma página por arquivo.

O que está no disco desta serventia, medido em 04/09/2026 em
`C:\ARPNET\C11\ONR\IMAGENS` — **a pasta já se chama ONR**:

| | |
|---|---|
| arquivos | **10.227** |
| no padrão `99999999.9999` | **10.227 de 10.227** — 100% |
| pastas de 1º nível | **4**, todas de 8 dígitos (`00000000`…`00000003`) |
| na regra do milhar | **10.223 de 10.223** conferidos, **zero** fora |
| resolução (amostra de 120) | **200 × 200 dpi, unidade polegada — 120 de 120** |
| compressão | **CCITT T.6 / Group 4 — 120 de 120** |
| bits por amostra | **1 — 120 de 120** |

**Não há uma imagem para converter.** O E-Ofício já as deixou no formato do
ONR, e é por isso que a pasta tem o nome que tem.

> **QUATRO ARQUIVOS FICAM DE FORA, e é bom que fiquem.**
> `00000000.0001` a `.0004` estão **na raiz, fora de pasta**, e o número deles
> é **zero** — matrícula 0 não existe. Eles não seguem o padrão de diretório do
> ONR e não casam com matrícula nenhuma do banco; o nosso varredor já os põe em
> «arquivo com número que não existe em matrícula nenhuma».

---

## O que bloqueia hoje — e é o que decide o prazo

O ONR é explícito, e em maiúsculas no manual:

> **«Não serão aceitas base de dados ou de imagens parciais ou incompletas.»**
> A base deve abranger desde **1º/01/1976**, ou desde o início das atividades.

Medido contra a produção, **só leitura**:

| | | |
|---|---|---|
| **74 das 1.701 matrículas não têm imagem nenhuma no disco** | 4,4% | **bloqueia** |
| **2.819 das 3.992 pessoas do Indicador Pessoal não têm CPF/CNPJ** | 70,6% | **bloqueia o IPS** |
| 1.203 fichas incompletas (6.508 páginas no disco fora do banco) | — | não bloqueia o ONR; bloqueia **a nossa tela** |
| a base alcança 1976? | matrícula mais antiga de **1951**, ato de **1948** | **alcança** |

**O SEGUNDO É O MAIOR, e é o que mais surpreende.** O XML do IPS traz, em
comentário no próprio modelo do ONR:

    <CNPJCPF>00000000000</CNPJCPF>
    <!-- CAMPO OBRIGATORIO - DOCUMENTO (CPF ou CNPJ)
         - A INFORMACAO DEVE SER MAIOR QUE ZERO -->

Sete em cada dez proprietários do nosso Livro 5 **não têm documento gravado** —
1.015 com CPF e 158 com CNPJ, contra 2.819 sem nada. É acervo antigo, em que a
escritura trazia o nome e não o número. **O IPS serve à Pesquisa de Bens
nacional**: quem não entra nele é como se não tivesse imóvel nenhum no país.

> **E o primeiro dos dois é o que a ferramenta desta semana já mede.** A tela
> «Páginas que faltam nas fichas» conta exatamente isso, e agora sabe também
> resolver as 48 páginas de número repetido.

---

## O que eu posso construir, e o que não posso

**Posso, e está medido:**

1. **Gerar o XML do Indicador Pessoal Simplificado** de `ri_partes` +
   `ri_atos` — o modelo tem seis campos, e eles estão transcritos do exemplo
   do ONR. Com a conferência que **diz quantas pessoas ficariam de fora por
   falta de documento**, antes de gerar: mandar 1.173 de 3.992 calado seria a
   base incompleta que o ONR recusa.
2. **Um varredor da pasta de imagens contra o padrão do ONR** — a conta do
   milhar, o nome do arquivo, a resolução e a compressão. É o que rodei à mão
   para escrever este documento, e vira tela.
3. **A lista das 74 matrículas sem imagem**, que é o trabalho de digitalização
   que falta.

**Não posso, e é bom que não:**

- **Escrever direto no Bucket e no Firestore.** Quem escreve são o **IPS** e o
  **CSL2**, programas do ONR instalados aqui — e eu não instalo nada no
  ambiente sem a sua palavra. Inventar um caminho paralelo daria duas coisas
  gravando o mesmo fato, que é como elas divergem.
- **Afirmar que a nossa base é completa.** As 1.701 matrículas são o que o
  E-Ofício tinha; **se isso é o Livro 2 inteiro desta serventia, quem sabe é
  quem tem a estante na frente.** É exatamente para esse caso que existe a
  `declaracao_base_incompleta.pdf`, assinada com e-CPF.

---

## O que espera você

1. **Escolher a modalidade.** A medição aponta para a **(b) Next Cloud SAS** —
   a (a) exige data center próprio.
2. **Mandar o formulário** para `integrar-onr@onr.org.br`, assunto
   «Opção 2 – Cartório de Registro de Imóveis de Cidade Exemplo/MA»:
   `FONTES_EXTERNAS/onr_nextcloud/formulario_solicitacao_backup.pdf`.
3. **Decidir sobre as 74 matrículas sem imagem e sobre os 2.819 sem
   documento** — digitalizar e completar antes, ou mandar a declaração de base
   incompleta e integrar o que há.
4. **Agendar a instalação do IPS e do CSL2** com o suporte do ONR (o manual
   traz o link da agenda). **E o ONR tem um módulo contra golpe**: antes de
   deixar alguém mexer, confira o código de segurança no Ofício Eletrônico,
   menu «Cartórios» → «Validação Atendimento» — o analista tem de dizer o mesmo
   código que aparece na sua tela.
5. **Homologação primeiro.** O manual insiste: só peça o GoLive quando a equipe
   estiver familiarizada.

---

## As fontes

Todas em `FONTES_EXTERNAS/onr_nextcloud/`, baixadas de `ridigital.org.br` em
04/09/2026 — **públicas, HTTP 200 sem credencial**, como o WSDL da CRA e o
swagger da ONRTDPJ. Ver o `LEIA-ME.md` de lá, que registra também que o
`Modelos_XML_XSD.zip` **não traz XSD nenhum**, apesar do nome: são 894 bytes e
um XML de exemplo.
