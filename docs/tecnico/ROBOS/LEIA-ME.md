# Documentação-base dos Robôs — Ofício Único de Cidade Exemplo/MA (CNS 000000)

**Para quem:** qualquer operador do Cartório Gestão (oficial, escrevente, auxiliar) e qualquer robô Grok Bot da casa.

**Onde mora (canônico):**
`SERVIDOR\INSTALAR_CARTORIO_GESTAO\DOCUMENTACAO\ROBOS\`

A pasta `Downloads\CartorioGestao\DOCUMENTACAO\` antiga aponta para cá — use sempre a canônica.

**Como usar**
1. Operador: abra o arquivo do ato na tabela abaixo (Markdown ou pelo explorador).
2. Robô: leia primeiro `REGRAS_COMUNS.md`, depois o guia do seu ato, antes de orientar ou operar.
3. Atualização: quem descobrir mudança no sistema ou na prática da casa **edita este guia** (ou pede ao robô do ato para atualizar) e anota a data no rodapé do arquivo.

**Projeto dos robôs:** ver `../PROJETO_ROBOS_CARTORIO.md` (arquitetura, LAN, humano no loop).

---

## Índice por ato

| Ato / tema | Guia operacional | Robô responsável |
|---|---|---|
| Abertura e reconhecimento de firmas | [ABERTURA_E_RECONHECIMENTO_DE_FIRMAS.md](ABERTURA_E_RECONHECIMENTO_DE_FIRMAS.md) | Robô Abertura de Firmas |
| Biometria / foto no cadastro (#39) | (ver guia de firmas § Biometria + Robô Firmas) | Robô Firmas |
| Regras comuns a todos os robôs | [REGRAS_COMUNS.md](REGRAS_COMUNS.md) | todos |

Guias dos demais atos (certidão, nascimento, casamento, óbito, proclamas, protesto, procurações, escrituras, RI, RCPJ/RTD, WhatsApp) entram nesta pasta no mesmo formato, um arquivo por ato, quando o robô respectivo estiver treinado.

---

## Manutenção

- **Sempre que** mudar rota, selo, etiqueta, regra da casa ou decisão do oficial → atualizar o guia do ato + data em «Histórico».
- **Não** gravar dados pessoais reais de clientes nestes arquivos.
- **Não** copiar `Program Files` nem rodar `ATUALIZAR_SISTEMA` só porque a documentação mudou — doc é fonte; instalação ao vivo é outra ordem.
- Versão do sistema referida nos guias: conferir `VERSAO.txt` na fonte / Program Files.

---

*Criado 2026-09-07 · Ofício Único de Cidade Exemplo/MA*
