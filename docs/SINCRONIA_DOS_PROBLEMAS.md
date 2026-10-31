# Sincronia dos problemas

> Para o oficial. Como ligar, conferir e parar a tarefa que leva os problemas
> registrados na serventia ao desenvolvimento, **mascarados**, e traz de volta a
> resposta de quem conserta. As ferramentas estão em
> `tools/problemas_sincronia.py`.

## 1. O que a sincronia faz

A cada 2 horas, das 7h às 20h, uma tarefa agendada do Windows (conta SYSTEM)
roda um ciclo num repositório Git **privado**, que só a serventia e o
desenvolvimento enxergam:

```
git pull  →  importar (o retorno)  →  exportar (os problemas)  →  git commit e push
                                                                  (só problemas/ e INDICE.md)
```

- **importar** grava, em cada problema, a nota que o desenvolvimento deixou em
  `retorno/` (a mesma nota da tela, «nota do desenvolvimento»);
- **exportar** escreve um arquivo por problema em `problemas/` e a lista em
  `INDICE.md`, já com a máscara de dados pessoais;
- o importar vem **antes** do exportar, para que o estado que acabou de voltar já
  saia no mesmo ciclo.

Cada lado só escreve na sua pasta: a serventia em `problemas/` e `INDICE.md`, o
desenvolvimento em `retorno/`. Por isso as duas pontas não brigam.

## 2. O que a sincronia NÃO faz

- **Não fecha problema.** Quem fecha é a serventia, na tela de problemas. A nota
  que volta não mexe na situação.
- **Não manda dado pessoal.** O texto passa pela mesma máscara do relatório para
  conserto e, depois, por uma passagem só da exportação, que troca referências
  de registro (folha, assento, ato, número de pasta, número de tabela). Problema
  que a máscara recusa não sai. Login e nome de quem usou o sistema nunca saem.
  Relato que ficou quase todo mascarado sai com a linha **«Texto muito mascarado:
  leia na tela do sistema antes de concluir.»**
- **Não mexe no código do sistema.** O repositório privado só tem os problemas e
  o retorno; atualização do sistema continua sendo pelo pacote assinado.
- **Não apaga arquivo** do repositório e não envia nada além de `problemas/` e
  `INDICE.md`.

## 3. Ligar a sincronia (parte B)

São passos de gente: o sistema não executa nenhum deles sozinho. Os caminhos
abaixo supõem a pasta de dados em `C:\ProgramData\CartorioGestao`; troque se a
sua for outra.

### B1. O repositório privado (no desenvolvimento)

```
gh repo create cartoriogestao/cartorio-problemas --private --add-readme --description "Problemas da serventia, mascarados, e o retorno do desenvolvimento"
```

### B2. O clone do desenvolvimento

Numa pasta **fora** do clone do sistema (para não mexer na trava da suíte de
testes):

```
git clone https://github.com/cartoriogestao/cartorio-problemas <pasta do desenvolvimento>\problemas
```

### B3. Na serventia

Depois de instalar a versão que traz a sincronia:

1. **Instale o Git for Windows**, se ainda não houver
   (`git --version` no Prompt de Comando responde).
2. **Gere a chave da sincronia**, só para este repositório. No **Prompt de
   Comando** (`cmd`), como administrador — **não no PowerShell**: o PowerShell
   5.1 descarta o `""` vazio e a chave sairia com outra senha ou o comando
   pararia:

   ```
   mkdir C:\ProgramData\CartorioGestao\sincronia
   icacls C:\ProgramData\CartorioGestao\sincronia /inheritance:r /grant:r *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F
   ssh-keygen -t ed25519 -N "" -C "serventia-sincronia" -f C:\ProgramData\CartorioGestao\sincronia\chave_da_sincronia
   ```

   O `icacls` vem **antes** do `ssh-keygen`, de propósito: deixa a pasta só
   para SYSTEM e Administradores, e a chave já nasce assim. Sem ele, a pasta
   herda as permissões do `ProgramData`, a chave privada nasce legível por
   qualquer usuário da máquina, e o OpenSSH a recusa («UNPROTECTED PRIVATE KEY
   FILE»), parando o ciclo.

   **Confira a permissão da chave depois de gerar.** O `ssh-keygen` pode
   acrescentar a conta que o rodou e deixá-la como dona do arquivo, mesmo com a
   pasta restrita:

   ```
   icacls C:\ProgramData\CartorioGestao\sincronia\chave_da_sincronia
   dir /q C:\ProgramData\CartorioGestao\sincronia\chave_da_sincronia
   ```

   Só podem aparecer SYSTEM e Administradores. Se aparecer outra conta
   (`<conta>`), remova-a; se ela for a dona, passe a posse aos Administradores:

   ```
   icacls C:\ProgramData\CartorioGestao\sincronia\chave_da_sincronia /remove:g <conta>
   icacls C:\ProgramData\CartorioGestao\sincronia\chave_da_sincronia /setowner *S-1-5-32-544
   ```

   Depois, rode os dois comandos de conferência de novo.

3. **Grave e confira a impressão do GitHub.** O ciclo só fala com servidor que
   esteja no `known_hosts` da sincronia (`StrictHostKeyChecking=yes`): nunca
   aceita um servidor novo sozinho. Use o `ssh-keyscan` do Git for Windows, porque
   o do Windows pode falhar com `choose_kex: unsupported KEX method`. Sempre no
   **Prompt de Comando**:

   ```
   "C:\Program Files\Git\usr\bin\ssh-keyscan.exe" github.com > C:\ProgramData\CartorioGestao\sincronia\known_hosts
   ssh-keygen -lf C:\ProgramData\CartorioGestao\sincronia\known_hosts
   ```

   Linhas começadas por `#` podem aparecer no `known_hosts`; elas são ignoradas.
   Compare **cada** impressão (`SHA256:...`) com as publicadas pelo GitHub na
   página «GitHub's SSH key fingerprints» (docs.github.com). Se alguma não bater,
   **pare**: apague o `known_hosts` e chame o suporte. Só siga se todas baterem.
4. **Cadastre a parte pública como chave de implantação**, com escrita **só neste
   repositório**:

   ```
   gh repo deploy-key add C:\ProgramData\CartorioGestao\sincronia\chave_da_sincronia.pub --repo cartoriogestao/cartorio-problemas --allow-write --title serventia
   ```

   Se a serventia não tiver o `gh`, o cadastro pode ser feito pelo computador de
   desenvolvimento, levando **só a linha do `.pub`**.

   **Nunca use token pessoal.** Um token daria acesso ao código do sistema e a
   todos os repositórios da conta; a chave de implantação só abre este. A chave
   **privada** (`chave_da_sincronia`, sem `.pub`) nunca sai da serventia.
5. **Clone o repositório pelo endereço SSH**, com a chave da sincronia. No Prompt
   de Comando:

   ```
   set GIT_SSH_COMMAND=ssh -i "C:/ProgramData/CartorioGestao/sincronia/chave_da_sincronia" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="C:/ProgramData/CartorioGestao/sincronia/known_hosts"
   git clone git@github.com:cartoriogestao/cartorio-problemas.git C:\ProgramData\CartorioGestao\problemas
   ```

   O endereço tem de começar por `git@github.com:`. O ciclo confere isso a cada
   vez e para se a origem for outra (um endereço `https://` pediria senha ou
   usaria a credencial de uma pessoa).
6. **Gere os arquivos da tarefa**, no console com o ambiente do servidor (o mesmo
   `CG_PG_DSN` e `CG_PG_SCHEMA` que o servidor usa), com **o mesmo Python do
   servidor**:

   ```
   "C:\ProgramData\CartorioGestao\runtime\Scripts\python.exe" "C:\Program Files\CartorioGestao\tools\problemas_sincronia.py" gerar-agendamento --repositorio C:\ProgramData\CartorioGestao\problemas --destino C:\ProgramData\CartorioGestao\sincronia
   ```

   O caminho do Python usado aqui **fica gravado no lançador**. Confira o
   resultado:

   ```
   findstr /c:"python.exe" C:\ProgramData\CartorioGestao\sincronia\sincronia_problemas.cmd
   ```

   O destino é a pasta `sincronia`, a restrita do passo 2, e não outra: o
   lançador roda como SYSTEM, e quem pudesse editá-lo rodaria os próprios
   comandos como SYSTEM. Na pasta restrita, só SYSTEM e Administradores mexem
   nele.

   Ele não abre o banco e não registra nada: só escreve
   `sincronia_problemas.cmd` (o lançador) e `registrar_sincronia.ps1`. Recusa se
   faltar `CG_PG_DSN` ou `CG_PG_SCHEMA`, e recusa se o `CG_PG_DSN` tiver senha: a
   senha vai no `pgpass` ([`SEGURANCA_REDE.md`](SEGURANCA_REDE.md), item 3).

   **`PGPASSFILE`:** ele pode não estar no `iniciar_servidor_servico.cmd`. Se
   estiver, repita a linha dele no console antes de gerar. Se não estiver, o
   gerador avisa que falta, mas a tarefa pode funcionar assim: ela roda como
   SYSTEM e pode usar o `pgpass` do perfil dessa conta. Confira se o arquivo
   existe, **sem abrir o conteúdo**:

   ```
   if exist "%SystemRoot%\System32\config\systemprofile\AppData\Roaming\postgresql\pgpass.conf" echo existe
   ```

   A prova é o log do primeiro ciclo (seção 4): `importar` e `exportar` com
   `codigo 0`.

   Na saída do gerador, os próximos passos ainda aparecem na ordem antiga. **Vale
   a ordem deste manual:** B4 primeiro, depois o passo 7.
7. **Registre a tarefa só depois do primeiro envio conferido (B4)**, no PowerShell
   **como administrador**. Assim, nenhum ciclo envia nada antes de alguém ler a
   exportação:

   ```
   powershell -ExecutionPolicy Bypass -File C:\ProgramData\CartorioGestao\sincronia\registrar_sincronia.ps1
   ```

   Ele restringe a pasta `sincronia` a SYSTEM e Administradores e registra a
   tarefa `CartorioGestao-Sincronia-Problemas`: SYSTEM, a cada 2 horas das 7h às
   20h, prioridade abaixo do servidor, no máximo 15 minutos por ciclo, sem ciclo
   em dobro, e recuperando o horário perdido se o computador estava desligado.
   Não mova o `sincronia_problemas.cmd` depois de registrar: a tarefa aponta
   para ele.

### B4. A primeira exportação, conferida a olho

Antes do primeiro envio e antes de registrar a tarefa (B3.7), no console com o
ambiente do servidor:

1. `... problemas_sincronia.py exportar --pasta C:\ProgramData\CartorioGestao\problemas --dry-run`
   — mostra o que escreveria e não escreve nada;
2. `... problemas_sincronia.py exportar --pasta C:\ProgramData\CartorioGestao\problemas`
   — e **leia** os arquivos de `problemas\` e o `INDICE.md`, procurando nome, CPF,
   matrícula, número de folha, de assento ou de ato, endereço ou qualquer coisa
   que identifique alguém. Achou? Não envie: avise o desenvolvimento;
3. só depois, o primeiro envio à mão (com o `GIT_SSH_COMMAND` do passo B3.5):

   ```
   git -C C:\ProgramData\CartorioGestao\problemas add -- problemas INDICE.md
   git -C C:\ProgramData\CartorioGestao\problemas -c user.name="Serventia (sincronia)" -c user.email=sincronia@cartorio-gestao.invalid commit -m "Sincronia: primeira exportação"
   git -C C:\ProgramData\CartorioGestao\problemas push
   ```

Agora registre a tarefa (B3.7). Ela assume dali em diante.

## 4. Ver se está funcionando

- **O log:** `C:\ProgramData\CartorioGestao\logs\sincronia_problemas.log`. Cada
  ciclo deixa a data e a hora de cada passo e o código de saída. Um ciclo bom
  termina em `ciclo: fim; codigo 0` (ou `ciclo: nada a enviar; codigo 0`, quando
  nada mudou), com `pull`, `importar`, `exportar` e `push` com `codigo 0`.
- **O repositório:**

  ```
  git -C C:\ProgramData\CartorioGestao\problemas log --oneline --stat -5
  ```

  Os commits da tarefa têm o autor «Serventia (sincronia)» e só arquivos de
  `problemas/` e o `INDICE.md`.
- Um ciclo que falha deixa `CICLO PARADO no passo ...` e o código. O passo que
  falha para o ciclo: se o `pull` falhar, nada se importa; se o `exportar` falhar,
  nada se envia. O próximo ciclo tenta de novo.
- `ERRO: o git nao esta instalado` → instale o Git for Windows (B3.1).
- `ERRO: a origem do repositorio nao comeca por git@github.com:` → o clone foi
  feito por `https://`; refaça o B3.5.

## 5. Parar a sincronia

No PowerShell como administrador:

```
Disable-ScheduledTask -TaskName CartorioGestao-Sincronia-Problemas
```

Para religar, `Enable-ScheduledTask` com o mesmo nome. Para tirar de vez,
`Unregister-ScheduledTask -TaskName CartorioGestao-Sincronia-Problemas` e, no
GitHub, apague a chave de implantação «serventia» do repositório privado.

## 6. Quando o log mostra `RECUSADO`

- **`RECUSADO of-0035.md: ...` depois de `importar`** — um arquivo de `retorno/`
  que o sistema não aceitou (fora do formato, com data no futuro, com algo que
  parece dado de pessoa). O ciclo **segue**: nada daquele arquivo foi
  gravado, e os outros foram. Mande ao desenvolvimento a linha do log; quem
  conserta reescreve o retorno.
- **`RECUSADO #35: ...` depois de `exportar`** — a máscara não conseguiu tirar o
  dado pessoal daquele problema, e **ele não saiu**. Os outros saíram. Abra o
  problema na tela e veja se dá para tirar do texto o que identifica alguém;
  senão, mande o caso ao desenvolvimento pelo relatório para conserto da tela.
