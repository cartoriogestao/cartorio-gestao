# Relatório do ensaio de atos — Registro Civil das Pessoas Naturais (02/11/2026)

Pedido do oficial (01/11/2026): «antecipar esses problemas e processar antes de encontrar na prática».
Foram praticados **46 casos** pela tela, sobre a casa de ensaio e com a trava ligada (o inventário está em
`inventario_rcpn.md`). Cada caso foi do formulário de lavrar ao termo, à folha do livro, ao breve relato,
ao papel e ao inteiro teor, e cada documento foi lido contra a lei e contra o padrão da casa.

- **O teste**: `tests/test_ensaio_de_atos_rcpn.py` (marcado `lento`): 299 conferências verdes e 41 `xfail` — cada
  defeito abaixo com o motivo. Para ler os documentos: `CG_ENSAIO_SAIDA=1`.
- **O padrão da casa**: os modelos de `modelos_padrao/rcpn/` e, só para estrutura e redação, a
  transcrição do acervo (9.472 termos de nascimento dos livros A-11 a A-13), lida em contagens agregadas.
  Nenhum dado real entrou aqui.
- **As fontes**: ver `inventario_rcpn.md`. Os textos do CNN e do CN-MA não estão nesta máquina; o artigo
  deles só aparece quando `docs/REQUISITOS_LEGAIS.md` já o citava.

Legenda: **LEGAL** problema legal · **FORMA** formatação ou redação · **SEM TELA** o ato não tem como
ser praticado · **DECISÃO** é do oficial. Ordem: o que mais cai no balcão primeiro.

## Consertos já enviados (#225, #226 e #227 já juntados; #228 aberto)

| PR | O que conserta | Norma |
|---|---|---|
| #225 | O casamento em **comunhão universal sem pacto** lavrava calado; o de **nubente de 15 anos** também; o de **76 anos em comunhão parcial** sem aviso. A conferência trava os dois primeiros e avisa o terceiro e o de 16-17 anos. | CC arts. 1.640, par. ún., 1.653, 1.520, 1.517 e 1.641, II; STF Tema 1.236 |
| #226 | O **nascimento tardio** era recusado quando a testemunha é mais nova que a registrada, e o **óbito antigo declarado pelo neto** também. | LRP arts. 46 e 54, 9º; CN-MA art. 249 |
| #227 | O **nubente estrangeiro** saía sem documento e sem país («italiano, lavrador, natural de Roma»); a opção de nacionalidade de quem nasceu em Portugal dizia «natural de Cidade Exemplo/MA». | LRP art. 70, 1º; CC art. 1.536, I |
| #228 | A **certidão de natimorto** dizia «SEXO ND» (e o papel, em branco) com o sexo declarado no termo. | LRP art. 53, § 1º, e art. 54, 2º |

## Problemas abertos

### 1. Reconhecimento de paternidade: a certidão sai desatualizada e revela o reconhecimento — LEGAL
Caso `av_paternidade`: nascimento só com a mãe, depois a averbação do reconhecimento pelo pai.
- O breve relato continua com `NOME: ANA EXEMPLO DE SOUZA` (o nome antigo), `FILIAÇÃO: IGNORADO e
  Beatriz Exemplo` e `AVÓS PATERNOS: ND`; o papel imprime `GENITOR(A): IGNORADO`.
- E o mesmo breve relato transcreve a averbação: «… que MARIO EXEMPLO DOS SANTOS **reconhece como sua
  filha** a registrada …».
- O inteiro teor saiu sem pedir nada.

Norma: Lei 8.560/1992, art. 6º («Das certidões de nascimento não constarão indícios…»; § 1º, «a natureza
da filiação»; § 2º, o inteiro teor só por autorização judicial) e LRP art. 19, § 3º.
Proposta: a natureza «reconhecimento de filiação» (que já existe no lançamento) atualiza as pessoas do
assento (pai, avós, o nome) e entra na lista das averbações que o breve relato menciona sem transcrever
(a inscrição do art. 21 resolve a menção); o inteiro teor desse assento pede a decisão judicial. O mesmo
vale para a alteração de prenome (caso `av_nome`: a certidão continua com o prenome antigo no NOME).

### 2. O termo de nascimento escreve o casamento dos pais — LEGAL · DECISÃO
Todo nascimento de pais casados: «… casados entre si em Cidade Exemplo/MA, com registro em Ofício Único de
Cidade Exemplo …», no termo e, por reprodução, no inteiro teor.
Norma: Lei 8.560/1992, art. 5º («No registro de nascimento não se fará qualquer referência à natureza da
filiação, à sua ordem em relação a outros irmãos do mesmo prenome, exceto gêmeos, ao lugar e cartório do
casamento dos pais e ao estado civil destes») e art. 6º, § 1º, para a certidão. É lei posterior e especial
ao LRP art. 54, 7º, que `docs/REQUISITOS_LEGAIS.md` (conflito nº 1) põe só contra o CN-MA art. 233, § 1º.
Padrão da casa: no acervo, a frase está em 1.984 dos 2.778 termos dos anos 1990 e em 4.131 dos 4.359 dos
2000; em **17 dos 1.537 dos 2010 e em nenhum dos 562 dos 2020**. A casa já deixou de escrevê-la.
Proposta: tirar as peças `RC_TERMO_NASCIMENTO__pais_casados_*` do termo (os campos podem continuar para a
CRC). Hoje a frase é proposital (testes do LT01) — por isso é decisão.

### 3. O breve relato do casamento diz «CPF SEM INFORMAÇÃO» — LEGAL
Todo casamento lavrado aqui: os dois CPF estão no termo e no papel, e o teor da certidão diz `CPF SEM
INFORMAÇÃO`. `rc_certidao._documento` só lê o blob do acervo do E-Ofício.
Norma: CNN art. 477 (o CPF na certidão), como citado em REQUISITOS_LEGAIS.
Proposta: ler o CPF das pessoas NUBENTE1/NUBENTE2, como o papel já faz (`_cpf_da_pessoa`).

### 4. O óbito sem testamento: o termo cala, ou diz «Deixou testamento conhecido: NAO» — LEGAL · FORMA
Todo óbito. O testamento é texto livre («se houver»): em branco, o termo não diz nada; com «não», sai
«Deixou testamento conhecido: NAO». Eleitor, bens e filhos são perguntas SIM/NÃO com frase própria.
Norma: LRP art. 80, 6º («se faleceu com testamento conhecido» — a pergunta é para toda morte); CN-MA art.
255, VII.
Proposta: o testamento vira marca como as outras (SIM/NÃO/não perguntado) e a identificação dele, campo
à parte; com NÃO, «Não deixou testamento conhecido.»

### 5. O termo de casamento não diz quem presidiu o ato — FORMA · DECISÃO
Todo casamento: «… foram declarados casados …» e «assinam comigo, que escrevi, os nubentes e as
testemunhas …». O juiz de paz digitado só aparece na linha de assinatura da folha («PAULO EXEMPLO JUIZ DE
PAZ, Juiz(a) de Paz»).
Norma: CC art. 1.536, caput, e LRP art. 70, caput (o assento «assinado pelo presidente do ato»). A
assinatura existe; falta o texto nomeá-lo, como o termo nomeia as testemunhas.
Proposta: «… foram declarados casados por PAULO …, Juiz de Paz, …» e «assinam comigo o presidente do
ato, os nubentes e as testemunhas». Mexe no modelo da casa — por isso é decisão.

### 6. Gêmeo sem a ordem de nascimento — LEGAL · SEM TELA
Caso `nasc_gemeo`: o termo diz só «gêmea». A tela de lavrar não tem o campo da ordem: ela só se grava
depois, em `/rcpn/gemeos` (`rc_gemeos.amarrar`), que escreve `gemeo_ordem` quando o termo já está
congelado — o livro fica sem a ordem.
Norma: LRP art. 54, 3º, e art. 63 («será declarada no assento especial de cada um a ordem de
nascimento»); CN-MA art. 234, como `rc_gemeos` o cita.
Proposta: o campo da ordem na tela de lavrar, exigido quando o parto é múltiplo.

### 7. Natimorto — LEGAL · FORMA · CONSERTADO (decisão do oficial, 02/11/2026)
- Sem nome, a tela recusa («falta: nome de quem é o registro»); o nome é facultativo, a critério dos pais
  (LRP art. 53, § 3º; CNN art. 479-A, como em REQUISITOS_LEGAIS — já lá como «conferir»). DECISÃO.
- O breve relato usa o quadro do óbito: `ESTADO CIVIL ND`, `PROFISSÃO ND`, `TESTAMENTO CONHECIDO ND`,
  `NATUREZA E CAUSA DA MORTE ND` de quem nasceu morto. O papel (molde próprio) não tem esses campos.
- A tela não tem o lugar do sepultamento nem a causa, e o papel imprime a caixa do sepultamento vazia.
Proposta: breve relato próprio do natimorto, com os campos do papel; sepultamento e causa na tela.

### 8. Óbito de pessoa não identificada — LEGAL · DECISÃO
O termo afirma «Não deixou filhos. Não deixou bens. Não era eleitor» de quem ninguém conhece, e não tem
onde dizer os sinais. Deixar as perguntas em branco não se pode: a trava da CRC exige S ou N («sem opção
de ignorado»).
Norma: LRP art. 81 (estatura, cor, sinais aparentes, idade presumida, vestuário); CN-MA art. 255, § 1º
(«que fez a pergunta e o declarante ignorava») × a exigência da CRC.
Proposta: para o desconhecido, o termo diz que se ignora e a CRC recebe N; campos dos sinais na tela.

### 9. A naturalidade sem o IBGE sai «ND» sem aviso — FORMA (risco)
Na casa de ensaio, antes de semear o município no cadastro do IBGE, a certidão de nascimento saiu
`NATURALIDADE ND` e o papel com a caixa em branco, com a naturalidade declarada no termo. Na serventia o
cadastro está cheio, mas um nome que ele não confirma (grafia) leva ao mesmo resultado em silêncio.
Proposta: a emissão avisa quando a naturalidade do termo não chegou à pessoa.

### 10. «sendo filho de» para a registrada — FORMA · DECISÃO
Toda registrada: «nasceu uma criança do sexo Feminino … sendo **filho** de …». O motor da prévia
(`modelos_motor_termo`) troca para «filha», mas o termo congelado — a folha do livro e o inteiro teor —
não. O acervo da casa escreve «filho de» para menina na maioria dos termos (cerca de 3.000 contra 600):
o modelo segue a casa, e a prévia diverge do papel. Decisão: o termo concorda, ou a prévia volta a dizer
«filho».

### 11. Pequenos de forma — FORMA
- «o(a) declarante assina», «tendo sido casado(a) com», «MM. Juiz(a)», «a identidade do(a)
  registrado(a)»: o sexo de cada um é conhecido.
- O fecho do breve relato repete a cidade: «Ofício Único de Cidade Exemplo/MA, Cidade Exemplo/MA, 2 de
  novembro de 2026.»
- O breve relato de nascimento põe o pai antes da mãe (`FILIAÇÃO: Mario Exemplo e Beatriz Exemplo`) e o
  papel, a mãe antes; o CPF sai sem pontos no teor e com eles no papel.

### 12. Atos sem tela — SEM TELA
Casamento por procuração (CC art. 1.542), nuncupativo (CC arts. 1.540 e 1.541), alteração de prenome e
gênero (Prov. CNJ 73/2018, sigilosa — o breve relato a transcreveria, como no item 1), adoção (ECA art.
47), traslado de assento do exterior (LRP art. 32), tomada de decisão apoiada (CC art. 1.783-A), morte
presumida (LRP art. 88), certidão negativa (CNN art. 238), e a autorização do nubente de 16 ou 17 anos
(CC art. 1.517), que a tela não tem onde dizer.

## O que saiu certo

- A data do ato por extenso com o algarismo, em todo termo (LRP art. 35; CN-MA art. 212, II).
- A matrícula de 32 dígitos com o dígito fechando, em toda certidão (CNN art. 473).
- O papel com o CNS, o selo, o endereço de consulta e a fé, em toda certidão (CN-MA arts. 130 a 132).
- O inteiro teor reproduz o termo palavra por palavra, com o que foi lançado à margem.
- As averbações, anotações e retificações aparecem no breve relato e no papel (LRP art. 21).
- O pacto (data e serventia) no termo do regime convencional; o cônjuge anterior e a dissolução; a morte
  violenta declarada; o bebê «com menos de um ano de idade»; as duas testemunhas do parto em domicílio,
  qualificadas; o fundamento e as testemunhas do tardio; a alegação de paternidade fora do termo.
- Os termos do Livro E trazem o título, quem ele nomeia e os limites (LRP arts. 90, 92, 94, 94-A).

## Não ensaiado nesta rodada

O casamento pela habilitação desta casa, o edital e a certidão de habilitação (praticados por
`tests/test_fluxo_rcpn.py`), o religioso com efeito civil, a conversão de união estável, as comunicações
(CRC, SIRC, IBGE), a certidão eletrônica (precisa da rede, que a trava barra) e os emolumentos e o FERJ
contra a lei de emolumentos do MA (o selo é digitado no ensaio, e o valor vem do texto do selo do TJMA).
