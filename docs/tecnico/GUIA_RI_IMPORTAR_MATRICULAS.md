# Relato escrevente — permissão para importar matrículas no RI

Data: 14/09/2026.

## O relato

A usuária escrevente, com perfil `USER`, não conseguia importar matrículas no
módulo do Registro de Imóveis.

## O que foi encontrado

O cadastro da escrevente usa o perfil operacional `USER`, mas algumas rotas de
acervo do RI ainda estavam restritas a `ADMIN` ou `ADMIN/MANAGER`.

As principais travas encontradas foram:

1. `/registro-imoveis/importar` — carga do acervo do E-Ofício — aceitava só
   `ADMIN`.
2. `/registro-imoveis/matriculas-doc` — matrículas digitadas em Word — aceitava
   só `ADMIN/MANAGER`.
3. `/registro-imoveis/importacoes` — histórico e painel das importações —
   aceitava `ADMIN/MANAGER/AUDITOR`, mas não `USER`.
4. As telas de fichas digitalizadas (`/registro-imoveis/imagens/...`) também
   não aceitavam `USER`, apesar de serem trabalho operacional de digitalização
   e cópia para o acervo do sistema.
5. O importador padrão (`/importar-padrao`) aceitava só `ADMIN`, embora também
   seja usado para `RI_MATRICULA`.

## O que foi liberado para `USER`

1. Importar carga do RI:
   - rota: `/registro-imoveis/importar`;
   - perfis: `ADMIN`, `MANAGER`, `USER`.

2. Ver painel de importações:
   - rota: `/registro-imoveis/importacoes`;
   - perfis: `ADMIN`, `MANAGER`, `USER`, `AUDITOR`.

3. Importar/completar matrículas digitadas em Word:
   - rota: `/registro-imoveis/matriculas-doc`;
   - perfis: `ADMIN`, `MANAGER`, `USER`.

4. Localizar, trazer e copiar fichas digitalizadas:
   - rotas: `/registro-imoveis/imagens/resolver`,
     `/registro-imoveis/imagens/do-disco`,
     `/registro-imoveis/imagens/do-disco/trazer`,
     `/registro-imoveis/imagens/do-disco/escolher`,
     `/registro-imoveis/imagens/copiar`;
   - perfis: `ADMIN`, `MANAGER`, `USER`.

5. Importador padrão para matrícula do RI:
   - rota: `/importar-padrao`;
   - `USER` pode acessar quando a espécie for `RI_MATRICULA`.

6. Correção do efeito colateral no Registro Civil:
   - o importador padrão também precisa continuar aceitando `RCPN_ASSENTO`
     para `USER`;
   - o download `/importar-padrao/manual` foi liberado para `USER`, porque o
     manual aparece nas telas de importação e não é ato decisório;
   - o menu geral voltou a mostrar “Importar de outro sistema” para `USER`.

## O que continua restrito

1. Substituir carga anterior do E-Ofício continua restrito a `ADMIN` ou
   `MANAGER`.
   - Motivo: essa opção apaga a carga anterior do E-Ofício antes de reimportar.
   - Usuário `USER` pode importar, mas não marcar “substituir carga anterior”.

2. Rotas de decisão, configuração, delegatários, obrigações externas e atos
   sensíveis permanecem fora do perfil `USER`, quando já eram restritas.

## Ajuste visual

Além das rotas, o menu também foi ajustado:

1. `USER` passa a ver “Fichas digitalizadas” e “Matrículas em Word” no menu do
   Registro de Imóveis.
2. No painel de importações, `USER` passa a ver “Carregar acervo” e
   “Matrículas em Word”.
3. No menu geral de livros/acervo, `USER` vê “Importar de outro sistema”.
4. No mesmo menu, `USER` também vê “Importar matrícula do RI”, já abrindo o
   importador padrão na espécie correta para o Registro de Imóveis.

## Regra aprendida

Permissão de rota e botão de tela precisam andar juntos. Se a rota é liberada,
mas o menu continua escondendo o link, para o usuário o sistema continua
“sem permissão”.

Também ficou separado:

- importar/completar/cópia operacional de acervo pode ser feita por `USER`;
- substituir carga anterior, configurar base e praticar ato decisório continua
  com perfil superior.

## Validação feita

- `ri_web.py` e `atribuicoes_web.py` compilam com `py_compile`.
- A suíte completa de tela não pôde ser rodada neste ambiente porque a `.venv`
  local está incompatível com o Python disponível: `lxml.etree` falha em
  `crc_soap.py` antes de o Flask terminar de montar o app.
