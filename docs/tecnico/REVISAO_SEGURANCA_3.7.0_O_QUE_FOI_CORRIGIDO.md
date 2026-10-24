# Revisão de segurança da 3.7.0 — o que foi corrigido (22/10/2026)

Este é o consolidado, pedido pelo oficial, de **tudo o que a revisão de segurança
de 22/10/2026 achou e do que foi feito com cada achado**. O relatório inteiro, com
a medição de cada item, está em `DOCUMENTACAO\REVISAO_SEGURANCA_3.7.0_20261022.md`
(pasta do projeto). Aqui vai o que importa para quem opera o sistema: **o que
mudou, onde, como se prova, e o que ainda espera decisão dele.**

**Onde cada coisa está em 22/10/2026 à noite:**

| onde | o quê | situação |
|---|---|---|
| servidor da serventia | lotes 1 e 2 do endurecimento (permissões de pasta, PostgreSQL, cópias, Convidado, compartilhamentos, firewall) | **aplicados** às 17:39 e 18:10, com `COMO_VOLTAR.txt` |
| servidor da serventia | lote 3 (pasta do projeto, auditoria imutável, superusuário reserva, e quatro medições com instrução) | **escrito e medido; não aplicado** — ele roda quando quiser |
| `SANDBOX\sistema` e `SERVIDOR\INSTALAR_CARTORIO_GESTAO` | os consertos de código (levas 1 a 4), com 65 testes novos | **no SANDBOX e, desde 22/10 20:50, no INSTALAR** (o SANDBOX inteiro foi promovido, porque o INSTALAR estava atrás da produção); não empacotado, não instalado |

Códigos: **C** crítico, **A** alto, **M** médio — os mesmos do relatório.

---

## 1. O que está no SANDBOX, conserto a conserto

### Quem pode fazer o quê

| código | o achado | o conserto | prova |
|---|---|---|---|
| **A5** | o perfil AUDITOR gravava, praticava ato e gastava selo em 11 rotas (habilitação, RI, caixa, notas) | o decorador de dentro de cada rota recusa **só o POST** a quem não pratica ato (`roles_required(..., metodos=("POST",))`): o AUDITOR vê a tela e não grava | `test_auditor_nao_grava.py` |
| **A6** | o robô era um usuário comum com o papel inteiro, e o ato saía com nome «emprestado» do primeiro da lista | robô só nasce USER ou AUDITOR; 403 nas rotas de gente (usuários, configurações, caixa, atualizações, selador, modelos, agentes…); selo não sai em nome de máquina; o nome de recurso não vem mais do cadastro. **A produção não tem usuário robô** — nada muda hoje | `test_revisao_seguranca_leva2.py` |
| **M2** | qualquer USER estornava lançamento de caixa fechado e conferia o caixa do colega; a cadeia de hash do caixa não era conferida por ninguém | estorno de caixa fechado: ADMIN/MANAGER **com a senha de outra pessoa** do mesmo papel, na hora; conferência: só ADMIN/MANAGER (e nunca do próprio caixa); a conferência da casa recalcula a cadeia dos últimos 60 dias (`CAIXA_CADEIA`, CRÍTICO quando não fecha) | `test_revisao_seguranca_leva3.py` |
| **M14** | a lista de problemas mostrava o traceback a todo login | só quem gere vê o detalhe técnico | leva 2 |
| **M12** | qualquer USER troca o acervo-fonte da importação (RCPN, Livro 3, padrão) | **não aplicado.** A leva 3 fechou as quatro rotas a ADMIN/MANAGER e um teste da casa acusou a ordem dele de **11/10/2026: «manter abertas»** ao USER. Voltou no mesmo dia; o risco fica declarado para ele decidir | `test_livro3_importar_do_acervo.py` |
| **M13** | cancelar certidão não cancelava o selo no razão, e qualquer USER cancelava | o selo já é cancelado por outra passada (`cancelamento_certidao.concluir`); **o papel USER fica** — fechar travaria o balcão | — |

### O que entra na tela e no papel

| código | o achado | o conserto | prova |
|---|---|---|---|
| **A7** | modelo editável por USER saía sem escape na tela do oficial (XSS armazenado) | todo modelo **ajustado pela casa** passa pelo filtro `html_sem_script` antes da tela e do papel; o padrão de fábrica sai byte a byte (`modelos_da_casa.e_texto_de_fabrica`); três telas trocaram `\|safe` por `\|sem_script` | `test_modelos_editaveis_sem_script.py` |
| **A8 / M16** | o teor das Notas e o corpo das folhas do RI iam crus ao Chrome que roda como SYSTEM, com rede | o HTML passa pelo filtro antes do Chrome, e o Chrome sobe **sem rede** (`--proxy-server=127.0.0.1:1`, `--host-rules=MAP * ~NOTFOUND`) | leva 1 e leva 2 |
| **M7** | o filtro deixava `form`, `formaction` e `url(http://…)` no CSS | caem os três; no CSS só ficam imagem embutida (`data:image/…`) e endereço relativo | leva 2 |
| **M3** | caminho de programa e de pasta digitado na configuração virava execução ou escrita como SYSTEM | caminho de rede é recusado; Chrome e LibreOffice configurados só valem **dentro das pastas de programas e com o nome do programa** | leva 3 |
| **M10** | a triagem do malote por IA gravava tarefa a partir de documento de fora | a tarefa diz, no corpo, que resumo e providência foram escritos pela IA e não são ordem da casa | leva 3 |

### Selo, dinheiro e atos

| código | o achado | o conserto | prova |
|---|---|---|---|
| **A9** | o selo digitado à mão e o «isento» contornavam a trava do selo pago | `registrar_selo_obtido_a_mao` passa por `cobrir_o_selo` com a mesma régua do selo automático e confirma a reserva na mesma transação; a gratuidade vem do texto do selo («Selo Isento»); os isentos do dia viram relato ao oficial (`FISCAL_ISENTOS_DO_DIA`) | `test_selo_a_mao_passa_pela_cobertura.py`, `test_ri_selar_ato.py` |
| **M8** | o expurgo do RI apagava o ato e deixava o selo vivo no razão; `gestor_rtdpj.corrigir` escrevia na produção sem interruptor | o expurgo cancela o selo em `sd_selos`; a correção do RTD/PJ tem interruptor na tela de configurações (`rtdpj_corrigir_automatico`) | leva 2 e leva 3 |
| **A13** | o envio automático à CENSEC rodava sem clique | interruptor `censec_envio_automatico` na tela de configurações (ligado de fábrica, para não mudar o que ele decidiu); desligado, a rotina não olha nem o banco | leva 2 |

### Atualização, segredos e a auditoria

| código | o achado | o conserto | prova |
|---|---|---|---|
| **C1** | a preparação da atualização era forjável por usuário local, e a assinatura se conferia uma vez só | `update_manager.reconferir_contra_o_pacote` reabre o `.cgu` ao aprovar e ao aplicar: assinatura com as chaves de hoje, manifesto igual, hash de cada arquivo do payload, nenhum arquivo a mais; o `aplicar_atualizacao.ps1` recusa arquivo fora da lista **antes** de parar o serviço | `test_assinatura_reconferida_ao_aprovar.py` |
| **M6 / M17** | arquivo de credencial regravado perdia a permissão até o próximo reinício; `.pfx` fora da lista de segredos | toda gravação de `.cred` chama `permissao_local.restringir` na hora; `*.pfx` é segredo | leva 2 |
| **M9** | CPF e teor em claro na auditoria; exportação sem registro | `db.log` mascara CPF/CNPJ pelos campos com nome de documento; toda resposta que baixa `.csv/.xlsx/.zip` grava `EXPORTACAO` | leva 2 |
| **A10** (metade) | a auditoria não era encadeada: linha apagada não deixava rastro | cada linha de `audit_logs` leva `hash_anterior` e `hash_linha`, preenchidos por **gatilho no banco** (vale para os 31 arquivos que inserem por fora de `db.log`); `compliance.regra_cadeia_da_auditoria` recalcula os últimos 30 dias — apagada, editada ou sem hash é CRÍTICO. A outra metade (imutável; `cg` sem superusuário) é o lote 3 do servidor | `test_revisao_seguranca_leva4.py` |
| **M11** | o segredo do WhatsApp ia por `http`; o código da ponte do CCN valia para sempre | `wa_puxar` recusa URL sem `https`; o código do lote e o da consulta do CCN são de uso único e vencem em 24 h | leva 3 |
| **M5** | o instalador reaproveitava um `.venv` do perfil do usuário | não reaproveita mais | leva 3 |
| colateral | o Werkzeug 3.1 respondia 413 ao escrevente logado que colasse um teor longo (500 KB) | `MAX_FORM_MEMORY_SIZE` de 16 MB na configuração; o anônimo continua com 2 MB | leva 4 |

---

## 2. O que está no servidor (lotes 1 e 2, aplicados)

| código | o que foi feito |
|---|---|
| **C2, A2 (metade), A4 (metade), M6** | `C:\ProgramData\CartorioGestao` sem herança: SYSTEM e Administradores com controle total, Usuários só leitura, `usuario_exemplo` sem ACE própria — criar arquivo no `runtime`, em `updates\staged` e na raiz dos dados é **negado** a quem não é administrador (medido) |
| **A1** | binários do PostgreSQL (`C:\CartorioGestaoPG`) sem «Usuários autenticados» |
| **A2** | pasta das cópias (`C:\CartorioGestao_Copias`) só SYSTEM, Administradores e `usuario_exemplo`; conta Convidado inativa |
| **A3** (parte do sistema) | compartilhamentos `Users` e `MIGRACAO_PG` removidos |
| **M1** (parte) | as três regras de firewall do sistema só nos perfis Privado/Domínio; as duas regras genéricas `python.exe` do perfil de `usuario_exemplo` apagadas |
| — | tarefa órfã `TmpCartorioMJ2806` apagada |

**Decisões dele nesses lotes:** Tailscale fica aberto (ele e a escrevente usam o
sistema por ali); o worker do Cursor fica (é do desenvolvedor); `programas_onr`
(C3), `C:\Selador` e o ARPNET (A3) ficam **fora** — «só o que é do Cartório
Gestão», e os três vão a quem cuida de cada um.

## 3. O lote 3 do servidor — escrito, medido, esperando ele rodar

`SERVIDOR\ENDURECIMENTO_20261022\endurecer.ps1 -Lote 3` mede; com `-Confirmar`
aplica **dois** itens e só mede os outros. Medido em 22/10/2026 às 20:20:

| item | medido | o que `-Confirmar` faz |
|---|---|---|
| 11. pasta do projeto (`Downloads\CartorioGestao`) — **A12** | quatro SIDs sem nome e o grupo `CodexSandboxUsers` com Modificar na árvore inteira | tira os quatro SIDs sem nome (ACL salva antes); o grupo do Codex só sai com `-TirarCodexSandbox` (a sessão da TI deixa de escrever no projeto) |
| 12. auditoria da produção imutável — **A10** | `producao.audit_logs` com 38.310 linhas e nenhum gatilho; nenhum código do sistema faz UPDATE/DELETE nela (medido) | gatilho que recusa UPDATE, DELETE e TRUNCATE, e prova com um DELETE recusado |
| 13. `cg` superusuário — **A10** | `cg` é o único papel e é superusuário | só com `-RebaixarCg`: cria `cg_admin` (superusuário reserva, senha digitada na hora, com repetição e mínimo de 12) e tira o superusuário de `cg`, que continua dono do banco e dos schemas |
| 14. runtime no Python do perfil — **A4** | `pyvenv.cfg` aponta para `C:\Users\<usuario>\AppData\Local\Programs\Python\Python311` | só mede: o conserto é instalar o Python «para todos os usuários» e recriar o runtime numa janela de manutenção |
| 15. cifra do backup — **A2**; chave da atualização — **M4** | `cofre.key` não existe (a cópia sai sem cifra); `chave_cartorio.pem` está numa pasta **compartilhada** de nuvem | só mede: ligar a cifra exige decidir onde a chave fica guardada fora da máquina; a chave de assinatura tem de sair da pasta compartilhada |
| 16. rotinas — **A12** | as cinco tarefas (`Backup-Diario`, `CENSEC-Envio`, `Compliance`, `Conferencia-Diaria`, `Minutas-CNIB`) rodam como `usuario_exemplo`, sem elevação, de `Downloads\CartorioGestao\FERRAMENTAS` | só mede: a proposta é mover `FERRAMENTAS` para uma pasta que só administradores escrevem, **mantendo `usuario_exemplo` como conta** (a nuvem da serventia é montada no perfil dele) |

## 4. O que NÃO foi feito, e por quê

- **A11** (descoberta UDP do cliente): os balcões já têm o endereço do servidor
  fixado — informação dele; sem risco prático, fica.
- **M1** (sessão amarrada ao IP; TLS): derrubaria quem muda de IP pelo
  Tailscale; TLS por proxy local é obra à parte.
- **M12** e **M13**: ver a tabela da seção 1 — uma é ordem dele, a outra
  travaria o balcão.
- **C3** (serviços do ONR), **A3** no selador e no ARPNET: fora do escopo por
  ordem dele; comunicar ao ONR, ao TJMA e a quem cuida do sistema antigo.

## 5. O que pode travar a operação quando isto for instalado

1. **Estorno de lançamento de caixa fechado** exige ADMIN/MANAGER **e** a senha
   de outra pessoa com o mesmo papel. Com uma só pessoa nesses papéis o estorno
   de caixa fechado não sai (o de caixa aberto não mudou).
2. **Conferência do caixa** só por ADMIN/MANAGER.
3. **Caminho de programa configurado fora de `C:\Program Files`** passa a ser
   ignorado; caminho de rede nas pastas é recusado.
4. **Código da ponte do CCN** vence em 24 h e é de uso único.
5. **`-RebaixarCg`** (lote 3): se o sistema fizer alguma operação de
   superusuário que ninguém mediu, a próxima subida acusa; a volta é uma linha,
   como `cg_admin`.
6. **Gatilho da auditoria:** cada INSERT em `audit_logs` pega uma trava curta;
   `db.log` desiste em 800 ms e manda a linha ao log do servidor — nenhuma tela
   para.

## 6. Os testes

65 testes novos em sete arquivos (`test_auditor_nao_grava`,
`test_modelos_editaveis_sem_script`, `test_assinatura_reconferida_ao_aprovar`,
`test_selo_a_mao_passa_pela_cobertura`, `test_revisao_seguranca_leva2`,
`_leva3`, `_leva4`), mais os ajustados (`test_ri_selar_ato`,
`test_atualizacao_permissao`, `test_impressao_pdf`, `test_ccn_envio`,
`test_ccn_consulta`). Rodados no cluster de teste privado (PostgreSQL 18), com o
runtime do servidor: a rodada larga das levas 2 e 3 deu 224 verdes e 7
vermelhas, as 7 apuradas (6 minhas, 1 a ordem dele do M12) e consertadas; a
rodada da leva 4, 30 verdes; a regressão final (compliance, esquemas, caixa,
atualização, portabilidade, varredores), 316 verdes e 8 vermelhas que não são
destas levas. Na árvore do INSTALAR, em paralelo, a corrente da auditoria acusou
que o gatilho não entrava na gravação do banco novo (os schemas reproduzidos
nasciam sem ele): anotado em `init_schema`, 43 verdes depois. As vermelhas de
outra passada ou de ambiente estão nomeadas, uma a uma, no fim do relatório.

**A suíte inteira não rodou** — ela só roda quando ele pede. **Nada disto foi
empacotado nem instalado**: está em `SANDBOX\sistema` e no `INSTALAR` (promovido
por ordem dele em 22/10/2026 à noite); empacotar é decisão dele.
