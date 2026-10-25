# Migrar o servidor para macOS — o inventário medido

> Pedido do oficial em 24/10/2026: «prepare uma migração facilitada para, no
> futuro, o servidor rodar em macOS». Este documento é o **inventário medido**
> do que hoje prende o sistema ao Windows, e não um plano executado. A única
> parte já pronta para os dois sistemas é o **módulo de automação** (o
> despachante, o guardião do cofre e o cofre).

## Como foi medido

`git grep` sobre os arquivos versionados do `main` (v3.7.4), **fora de
`tests/`**, em 24/10/2026, antes do ramo da automação. Os números contam
arquivos `.py` (e, onde dito, os `.ps1`/`.cmd`). Nenhum dado da serventia está
aqui: só nomes de arquivo do repositório.

| busca | arquivos | ocorrências |
|---|---|---|
| `.ps1` versionados | 12 | — |
| `.cmd`/`.bat` versionados | 13 | — |
| `powershell` em `.py` | 10 | 22 |
| `schtasks` em `.py` | 1 (`oficial_robos.py`) | 2 |
| `ctypes.windll` | 3 (`a3_assinador_filho.py`, `crc_a3_assinador.py`, `recursos_da_maquina.py`) | 6 |
| `pywin32` / `win32com` / `winreg` | 0 | 0 |
| `msvcrt` | 1 (`tools/pytest_guard.py`) | 4 |
| `icacls` | 2 (`permissao_local.py`, `pasta_das_copias.py`) | 11 |
| `.dll` (drivers PKCS#11 do A3) | 6 (`a3_windows.py`, `a3_servico_local.py`, `assinatura_digital.py`, `crc_a3.py`, `crc_a3_assinador.py`, `atribuicoes_web.py`) | 22 |
| `pkcs11` | 5 | 88 |
| `soffice` / LibreOffice | 26 (os maiores: `impressao_pdf.py`, `notas_web.py`, `ri_odt.py`, `notas_teor_arquivo.py`, `ri_doc_extrair.py`) | 115 |
| literais `C:\` | 40 (os maiores: `impressao_pdf.py`, `pastas_da_casa.py`, `pasta_das_copias.py`, `gestor_cargas_ri.py`) | 77 |
| `ProgramData` / `PROGRAMDATA` | 34 | 65 |
| `os.name == "nt"` / `sys.platform == "win32"` (já com ramo) | 4 | 5 |
| `creationflags` / `CREATE_NEW_PROCESS_GROUP` | 2 | 4 |
| `shell=True` | 0 | 0 |
| `waitress` | 11 | 14 |

Para medir de novo: `git grep -c -i -e "<padrão>" -- '*.py' ':!tests/'`.

## Item por item — o equivalente no macOS e o esforço

Esforço: **P** (horas), **M** (dias), **G** (semanas).

| # | o que prende ao Windows | equivalente no macOS | esforço |
|---|---|---|---|
| 1 | **Instalador e atualização** — `installer/*.ps1` (8), `installer/client/*.ps1` (4+), os `.cmd` da raiz; registro no Agendador (`Register-ScheduledTask`), Firewall (`New-NetFirewallRule`/`netsh`), atalhos `.lnk`, chave de desinstalação no registro | instalador em `sh` + `launchd` (LaunchDaemon para o servidor, LaunchAgent para a sessão); firewall do macOS (`socketfilterfw`) ou nenhum na rede local; atalho = `.webloc`/app no Dock | **G** |
| 2 | **Agendamento** — tarefas do Agendador: servidor (`ONSTART`, SYSTEM, prioridade 3), backup, conferência, compliance, CENSEC, minutas do CNIB; `oficial_robos.ler_agendador_do_windows` lê `schtasks /query` | `launchd` com `StartCalendarInterval`; a leitura da saúde vira `launchctl print` | **M** (a automação já está pronta: ver abaixo) |
| 3 | **Caminhos `C:\` e `ProgramData`** — 40 arquivos com literal `C:\`, 34 com `ProgramData` | a pasta de dados vem de `CARTORIO_GESTAO_DATA`; o padrão no macOS é `~/Library/Application Support/CartorioGestao` (já é o de `automacao_cofre.pasta_de_dados`) | **M** — trocar literal por configuração, arquivo a arquivo |
| 4 | **LibreOffice e PDF** — `impressao_pdf.py` procura `soffice.exe` em caminhos do Windows; 26 módulos geram `.odt` | LibreOffice para macOS (`/Applications/LibreOffice.app/Contents/MacOS/soffice`), mesma linha de comando `--convert-to pdf`; o `.odt` não muda | **P** a **M** |
| 5 | **A3 (PKCS#11)** — os drivers são `.dll` (`eTPKCS11.dll`, `IDPrimePKCS1164.dll`); a assinatura roda fora do Flask (`a3_servico_local`, `a3_assinador_filho`) porque o driver dá segfault no processo do servidor | o driver do token para macOS é uma `.dylib` do fabricante (SafeNet/Thales, Gemalto/IDPrime); `PyKCS11` funciona igual; a arquitetura «assinar fora do processo» continua | **M**, com **risco** (ver abaixo) |
| 6 | **`ctypes.windll`** — prioridade do processo (`recursos_da_maquina.py`) e o A3 | `os.nice`/`setpriority`; o A3 pela `.dylib` | **P** |
| 7 | **`icacls` / ACL** — `permissao_local.py` restringe `*.cred`, `secret.key`, logs | `chmod 600`/`700` e o dono do arquivo | **P** (o cofre da automação já tem os dois ramos) |
| 8 | **PostgreSQL** — binários em pasta do Windows (`CG_PG_BIN`), serviço do Windows | PostgreSQL do Homebrew (`brew services`) ou Postgres.app; `pg_dump`/`pg_restore` iguais; `CG_PG_DSN` igual | **P** — **já é portátil** no código (`banco_pg`, `bd_nativo`) |
| 9 | **waitress como serviço** — o servidor é uma tarefa `ONSTART` como SYSTEM | LaunchDaemon com `KeepAlive`; o `app.py --service` é o mesmo | **P** — Flask e waitress **já são portáteis** |
| 10 | **`msvcrt`** em `tools/pytest_guard.py` (a trava da suíte) | `fcntl.flock` | **P** |
| 11 | **Certificados do Windows** — `onr_wsoficio.certificados_do_windows` lê o repositório de certificados pelo PowerShell | Keychain (`security find-certificate`) ou o `.pfx` do cofre | **M** |

## O que já é portátil

- **PostgreSQL** (`banco_pg`, `bd_nativo`): só o DSN e a pasta dos binários mudam.
- **Flask e waitress**: o servidor não tem código de Windows; só a forma de subir.
- **O cofre da automação** (`automacao_cofre.py`): AES-256-GCM com chave por
  Argon2id/scrypt, formato JSON versionado igual nos dois sistemas — o arquivo
  copiado de um servidor para o outro abre com a mesma senha-mestra. A
  permissão restrita tem os dois ramos (ACL no Windows, `chmod 600` no macOS).
- **O guardião do cofre** (`automacao_guardiao.py`): Python puro, canal local em
  127.0.0.1, janela em tkinter (vem com o Python do macOS e do Homebrew).
- **O despachante** (`automacao.py`): `pathlib`, sem `shell=True`; o que é do
  sistema está isolado em funções de dois ramos (`processo_vivo`,
  `matar_arvore`, `lancar_corredor`, `rodar_com_prazo`, `_comando_de_script`).
- **O instalador da tarefa** (`automacao_agendador.py`): gera o `.ps1` e os
  `.cmd` do Agendador do Windows **e** os dois LaunchAgents (`.plist`) do macOS,
  sem executar nenhum (`tools/gerar_instalador_automacao.py`).

## Riscos a conferir antes de decidir

1. **O token A3 no macOS (fase 3, o robô do Portal do Selo).** O robô depende
   do driver PKCS#11 do token **para macOS** — uma `.dylib` do fabricante, na
   versão do macOS e do processador (Apple Silicon) da máquina. **Conferir com
   o fabricante do token** que há driver assinado e atual; sem ele, o A3 não
   assina no macOS e o robô não roda. Conferir também se o Portal do Selo
   aceita o navegador/assinador usado no macOS.
2. **O LibreOffice** gera o mesmo PDF? Medir com os moldes da casa (o tempo e o
   resultado byte a byte), como foi feito no Windows com a impressora gravada no molde.
3. **Os programas do ONR** (IPS, CSL2) e outros instaladores de Central que hoje
   são executáveis do Windows: conferir se há versão para macOS.
4. **As fontes** dos moldes (`.odt`): instalar as mesmas no macOS, senão o
   papel muda de paginação.

## A ordem sugerida, se a migração for decidida

1. Itens 3, 6, 7 e 10 (configuração no lugar de literal; sem mudança de comportamento no Windows).
2. Itens 8 e 9 (banco e servidor no macOS, num ensaio com cópia).
3. Item 4 (LibreOffice) e item 11 (certificados).
4. Itens 1 e 2 (instalador e agendamento) — a automação serve de modelo.
5. Item 5 (A3), só depois da resposta do fabricante do token.
