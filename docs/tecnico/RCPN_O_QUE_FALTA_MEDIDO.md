# O RCPN maduro: o que falta, medido no Código de Normas

*29/08/2026 — levantamento completo, a pedido do oficial:*

> «vamos seguir no desenvolvimento do nosso módulo maduro e completo de RCPN»
> «o cartório está precisando do sistema pronto e amadurecido para o quanto
> antes»

Este documento é o **roteiro**: cada linha é uma obrigação medida, com o artigo,
o prazo e o tamanho do que está em aberto. Nada aqui é suposição.

---

## Feito nesta sessão

| | onde |
|---|---|
| **o TERMO do livro** — os três modelos, lidos dos treze do E-Ofício | `rc_termo.py`, versão 3.6.35 |
| **as ANOTAÇÕES devidas** — arts. 367 a 372, prazo de 5 dias | `rc_anotacao.py` |
| oito colunas que o termo cobra, cada uma também numa remessa | `rc_schema.py` |
| a divergência do contador de casamento, declarada em vez de calada | `acervo_carga.py` |

---

## Escrito, esperando a suíte fechar

**As nove comunicações** — `rc_comunicacoes.py`. Ver
`RCPN_COMUNICACOES_MENSAIS.md`.

---

## O que falta, em ordem de urgência medida

### 1. O SIRC — e é o prazo mais apertado do sistema inteiro

**Art. 225: UM DIA ÚTIL.** Cobre nascimentos, natimortos, casamentos, óbitos,
**averbações, anotações e retificações**. Mês sem movimento **também se
comunica** (§ 3º). Descumprir sujeita ao art. 92 da Lei 8.212/1991 **e a ação
regressiva do INSS**.

O layout está medido em `SIRC_MEDIDO.md`: web service com WSDL, XML UTF-8 de no
máximo 1024 KB e **250 registros**, GZIP, um minuto entre envios. **Falta o XSD**,
que fecha os enumerados.

### 2. A CRC — é o canal que a norma manda usar primeiro

Três obrigações distintas, e só a primeira eu conhecia:

| | artigo |
|---|---|
| **carga** dos registros | Provimento 46/2015 do CNJ |
| **comunicação** entre serventias, «preferencialmente» por ela | art. 243 |
| **consulta obrigatória** antes de decidir restauração ou suprimento | art. 348, § 2º |

O layout está medido em `CRC_DE_PARA_MEDIDO.md`: 49 tags no nascimento, 55 no
casamento, 78 no óbito, com os anexos de órgão emissor (37) e motivo de
alteração (6).

### 3. Retificação, restauração e suprimento — arts. 348 a 354

Procedimento administrativo com **10 dias úteis**, consulta obrigatória à CRC, e
o **art. 353 com dinheiro dentro**: erro da serventia torna o ato gratuito,
comunica-se ao FERC e ao FERJ, e o FERJ cobra do delegatário da época. Ver
`RCPN_RETIFICACAO_E_SUPRIMENTO.md`.

### 4. O prazo do IBGE, que o sistema não conhecia

`ibge_geracao.py` monta o mapa e foi conferido posição por posição — **mas não
sabe que existe prazo**. Art. 224: **dia 8** de janeiro, abril, julho e outubro,
com **multa de 1 a 5 salários mínimos** «sem prejuízo da ação penal», e o § 3º
exige o **número da DNV** no mapa.

### 5. A FUNAI, que é imediata

Art. 253, § 2º. **Quatro nascimentos indígenas** no acervo, todos Krikati,
**três de 2026**. E eles só se veem porque alguém preencheu a cor — que está em
branco em **178 dos 193**.

### 6. O cancelamento e a duplicidade — arts. 364 a 366

- **art. 365**: constatada **duplicidade de assentos** do mesmo fato, comunicar
  **imediatamente** ao juiz corregedor; vale o **mais antigo**, e o mais recente
  fica com **bloqueio cautelar** até decisão;
- **art. 366**: efetivado o cancelamento, **5 dias** para anotar nos demais atos
  da casa e comunicar às outras serventias — **pela CRC**, e a comunicação «se
  estenderá aos órgãos de identificação oficiais do Maranhão, a fim de evitar
  fraudes documentais».

> **O art. 366 liga o cancelamento à lista de atenção para fraudes** que esta
> casa já tem. Não é coincidência: registro cancelado que continua circulando é
> exatamente o documento com que se frauda.

### 7. O mutirão do CPF — art. 347, e é gratuito

> «Nos assentos de nascimento, casamento e óbito lavrados **em data anterior à
> vigência do Provimento nº 63, de 14/11/2017**, serão averbados, **quando
> possível, de forma gratuita** e mediante conferência, o número do **CPF**, e
> anotados os números do **DNI ou RG**, do **título de eleitor** e de outro dado
> cadastral público.»

**Medido no acervo**: dos 193 nascimentos, **135 são anteriores a 2017**, e
**86 desses estão sem CPF**. E o acervo é 1% do livro — a casa tem **19.552**
nascimentos.

É trabalho de mutirão, gratuito, e o sistema pode listá-lo: **quem é anterior a
14/11/2017 e não tem CPF**. Mesma forma do mutirão das assinaturas
digitalizadas, que já existe nas Notas.

### 8. Os modelos que faltam do E-Ofício

Registro tardio, termo de gêmeos, alegação de paternidade e a comunicação de
casamento ao registro de nascimento. Os textos estão extraídos em
`FONTES_EXTERNAS/modelos_rcpn_eoficio/`.

---

## O que depende de você, e não me impede de seguir

| | |
|---|---|
| o **endereço** de cada um dos nove destinos | |
| o **cadastro no INFODIP**, no TRE | formulário assinado, digitalizado; senha volta em 3 dias úteis |
| o **usuário e a senha** do SIRC | são da serventia |
| o **certificado A3** da ICP-Brasil | é token físico — decisão sua |
| se há **caminho eletrônico** para Economia, Receita e Identificação/MA | ou se é ofício em papel |
| o valor da CRC para **morte violenta** | ela só enumera «Natural ou Acidental» |
| o **próximo número do casamento** | a carga semearia 1012; o E-Ofício diz 39 |

**Nenhuma dessas para o trabalho.** Cada uma vira pendência declarada, e eu sigo
pela frente seguinte — que é a sua ordem de 29/08: *«sempre continue, nunca fique
sem fazer nada»*.
