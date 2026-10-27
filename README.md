# Cartório Gestão

Sistema de gestão para **serventias extrajudiciais brasileiras** (cartórios),
nas seis atribuições: Registro de Imóveis (com o Livro 3 — Registro Auxiliar),
Tabelionato de Notas, Tabelionato de Protesto, Registro Civil das Pessoas
Naturais, Registro Civil das Pessoas Jurídicas e Registro de Títulos e
Documentos — mais o caixa e o protocolo geral, o selo eletrônico, as remessas
às Centrais e a gestão interna da serventia.

Roda numa máquina Windows da própria serventia, servindo os computadores do
balcão pela rede local. Não depende de nuvem: o banco, os documentos e os
backups ficam na casa.

> **Licença: GNU Affero General Public License v3.0** (`LICENSE`). Quem usar,
> modificar ou oferecer este sistema como serviço pela rede tem de disponibilizar
> o código-fonte das suas modificações, sob a mesma licença.

## O que ele faz

- **O ato, no livro certo.** Lavra, averba, anota, retifica e cancela com o
  lugar certo no livro certo e numeração que não se repete — a regra mora no
  banco (`UNIQUE`), e não só no código.
- **O selo eletrônico.** Pede o selo ao aparelho selador da rede local quando o
  ato é praticado, guarda o razão dos selos e imprime o carimbo com os
  emolumentos, os fundos e o QR de consulta.
- **Custas e caixa.** Calcula emolumentos e fundos pela tabela vigente na data
  do ato; o protocolo geral e o caixa são a mesma coisa — quitar um item lança
  no caixa, com recibo do atendimento inteiro.
- **As Centrais.** Gera, confere e (onde há API) envia as remessas e
  comunicações: CRA e CENPROT (Protesto), ONR (Registro de Imóveis), ON-RCPN e
  CRC (Registro Civil), SIRC, IBGE, ONRTDPJ, CENSEC, entre outras.
- **Certidões e papéis.** Certidões, termos, recibos e traslados saem em `.odt`
  (editável) ou PDF, a partir de modelos que a serventia ajusta na própria tela.
- **Gestão interna.** Expedientes e malote, tarefas e prazos, plano de ação de
  inspeção, LGPD, atendimento, relatórios, usuários e auditoria.
- **Ajuda que lê a instalação.** Uma janela de ajuda em toda tela, que pode
  consultar um provedor de IA escolhido pela serventia — com máscara de dados
  pessoais por padrão e sem poder de praticar ato.
- **Agente de minutas (RI e Notas).** Lê os documentos do título e prepara o
  primeiro texto do ato, marcando com `[COMPLETAR: …]` o que não consegue
  afirmar. Não lavra, não numera, não sela e não cobra: quem pratica o ato é a
  pessoa.
- **Máquina não assina ato.** Ato feito em sessão de robô fica com o autor
  «pendente», e quem selar assina — o sistema nunca põe no ato o nome de quem
  não o praticou.

O que cada versão trouxe está em [`docs/NOVIDADES.md`](docs/NOVIDADES.md).

## Requisitos

- Um computador **Windows 10/11** como servidor (Windows PowerShell 5.1).
- **Python 3.11 ou superior** no servidor — o instalador tenta instalar o
  Python 3.12 pelo `winget` quando ele não existe.
- **PostgreSQL** no servidor — o banco de dados desde a versão 3.7.0 (o
  instalador ainda não o instala; ver
  [`docs/REQUISITOS.md`](docs/REQUISITOS.md#o-banco-de-dados-postgresql)).
- Os computadores do balcão só precisam de um navegador.
- LibreOffice no servidor, para os papéis saírem em PDF, e Chrome ou Edge,
  para alguns papéis desenhados em HTML.
- Para funções específicas: o aparelho selador do Tribunal, impressora térmica
  de etiquetas, token A3 com o programa do fabricante, a extensão do CCN e as
  credenciais de cada Central.

A lista completa, com o motivo de cada item, está em
[`docs/REQUISITOS.md`](docs/REQUISITOS.md), e o
**[manual geral](docs/MANUAL.md)** cobre instalação, configuração e o
panorama de todas as telas.

Para quem vai implantar ou consertar: a documentação técnica da construção —
formatos das Centrais medidos, decisões de desenho e o roteiro de cada versão —
está em [`docs/tecnico/`](docs/tecnico/README.md).

## Instalação rápida

1. Copie esta pasta para o servidor.
2. Execute `INSTALAR_SERVIDOR.cmd` e confirme a permissão de Administrador.
3. O navegador abre o sistema; crie o primeiro **administrador**.
4. Em **Configurações → Serventia**, informe os dados da sua serventia (nome,
   CNS, CNPJ, endereço, titular, cidade e UF). O código não traz dado de
   serventia nenhuma.
5. Nos computadores do balcão, execute `INSTALAR_CLIENTE.cmd` uma vez.

O passo a passo completo, a rede, as atualizações e as credenciais das
Centrais estão em [`docs/INSTALACAO.md`](docs/INSTALACAO.md); o que o servidor
e a casa configuram para a instalação ficar segura (pastas, banco, firewall,
rotinas, chave das atualizações, backup e papéis), em
[`docs/SEGURANCA_IMPLANTACAO.md`](docs/SEGURANCA_IMPLANTACAO.md).

## Onde ficam as coisas

| | |
|---|---|
| Programa | `C:\Program Files\CartorioGestao` |
| Dados (banco, documentos, backups) | `C:\ProgramData\CartorioGestao` — ou a pasta em `CARTORIO_GESTAO_DATA` |
| Senhas e chaves das Centrais | arquivos `*.cred` na pasta de dados — **nunca no banco** |

O banco viaja nos backups, e os backups saem da serventia; por isso nenhuma
credencial é guardada nele.

## Para quem vai mexer no código

```bat
rem os testes (pytest), com a suíte em paralelo
"%PROGRAMDATA%\CartorioGestao\runtime\Scripts\python.exe" -m pytest tests -n 4 --dist loadfile

rem só os rápidos
RODAR_SUITE_RAPIDA.cmd
```

- A arquitetura, as regras da casa e o mapa dos módulos estão em
  [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).
- Quem programa com IA (Claude Code, Cursor, Codex, ChatGPT) começa por
  [`docs/AGENTES.md`](docs/AGENTES.md): o fluxo por pull request, os dados
  fictícios e o que costuma quebrar.
- As decisões que moldaram o sistema (regras de domínio com o fundamento
  legal, armadilhas das Centrais, o que o sistema não faz) estão em
  [`docs/decisoes/`](docs/decisoes/README.md), por atribuição.
- **Nenhum dado real entra no repositório.** Os testes usam uma serventia
  fictícia (CNS `000000`, «Cidade Exemplo»), e o varredor
  `ci/anti_vazamento.py` recusa CPF, CNPJ, CNS e selo que não estejam
  declarados como fictícios em `tests/fixtures/anti_vazamento/`. Ele roda na
  CI e deve rodar antes de cada contribuição.
- Atualizações para uma instalação em uso são pacotes `.cgu`, gerados por
  `tools/criar_atualizacao.py` e aplicados pela tela **Atualizações** — com
  backup antes, conferência de SHA-256 de cada arquivo e volta automática se o
  servidor não responder.

## Dúvidas e contato

Dúvidas sobre o sistema, a implantação ou a licença:
**[cartoriogestao.dev@proton.me](mailto:cartoriogestao.dev@proton.me)**.

Para relatar defeito ou propor mudança no código, prefira abrir uma *issue* ou
um *pull request* aqui no GitHub — sem dado real de serventia ou de pessoa.

**Falha de segurança não vai em *issue* pública**: relate em particular, como
diz a [política de segurança](SECURITY.md).

## Estado

Em uso de produção numa serventia de ofício único. A publicação do código é
recente: a documentação pública está sendo escrita, e o histórico de
desenvolvimento (que traz dados da serventia de origem) não faz parte deste
repositório.
