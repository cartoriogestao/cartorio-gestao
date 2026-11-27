# O servidor no Linux — o caminho facilitado

> Pedido do oficial em 27/11/2026: o GitHub passa a dizer que o sistema roda também no macOS, e
> oferece um caminho facilitado para operar em Linux. Este roteiro é esse caminho.

## Onde o sistema roda hoje

| sistema | papel | situação |
|---|---|---|
| **Windows 10/11** | servidor principal | em produção; instalador `INSTALAR_SERVIDOR.cmd` |
| **macOS** | servidor reserva (réplica do banco, só consulta) que **assume** se o principal cair | em uso desde 11/2026 (`docs/SERVIDOR_RESERVA_MACOS.md`); é também onde roda o executor da CI |
| **Linux (Debian/Ubuntu)** | servidor (ensaio, treinamento, desenvolvimento; produção com as ressalvas abaixo) | **caminho preparado**: `installer/linux/instalar_servidor.sh`. A suíte inteira de testes roda em Linux a cada PR (Debian 12, PostgreSQL 18, LibreOffice: `ci/suite/Dockerfile`). Ainda não há serventia em produção no Linux. |

O núcleo já é portátil: Python, Flask, waitress e PostgreSQL. O que prende ao Windows está medido,
item por item, em [`MIGRAR_PARA_MACOS.md`](MIGRAR_PARA_MACOS.md), e o Linux herda o mesmo inventário.
Veja a seção [«O que ainda é só do Windows»](#o-que-ainda-é-só-do-windows) antes de escolher o
Linux para uma serventia.

## Requisitos

- **Debian 12 ou mais novo, ou Ubuntu 24.04 ou mais novo**, com systemd e acesso de administrador
  (`sudo`). O sistema pede **Python 3.11+**: o Ubuntu 22.04 tem 3.10 e não serve sem um Python à parte.
- Rede na hora de instalar (apt e pip). Depois, só a rede local.
- Os computadores do balcão continuam só com o navegador.

## Instalar

Copie o código para o servidor (um `git clone` ou a pasta de uma versão) e, de dentro dela:

```bash
sudo bash installer/linux/instalar_servidor.sh
```

O script faz, nesta ordem (e pode rodar de novo sem estragar nada):

1. **Pacotes pelo apt:** Python, PostgreSQL (com o `contrib`, que traz `pg_trgm` e `unaccent`),
   LibreOffice sem interface, as fontes e o que o `PyKCS11` precisa para compilar. São os mesmos
   pacotes da imagem da CI.
2. **A conta de sistema `cartorio`**, sem login. Ela roda o serviço e é a dona da pasta de dados.
3. **O código** em `/opt/cartorio-gestao/sistema` e o **venv** em `/opt/cartorio-gestao/venv`, com
   o `requirements.txt`.
4. **O banco:** o papel `cg` (senha sorteada, SCRAM, **sem superusuário**) e o banco `cartorio`,
   no PostgreSQL local, **só em localhost** (o padrão do Debian). A senha vai **só** para
   `/var/lib/cartorio-gestao/.pgpass`, com `chmod 600` e dono `cartorio`. Ela não aparece na tela,
   no log nem no `CG_PG_DSN`. O schema `producao` e as extensões nascem na primeira subida do sistema.
5. **A configuração** em `/etc/cartorio-gestao/servidor.env` (veja `installer/linux/servidor.env.exemplo`)
   e o **serviço** `cartorio-gestao` do systemd. O serviço sobe junto com a máquina, depois do
   PostgreSQL, e volta sozinho se cair.

Ao final, o script espera o sistema responder em `http://127.0.0.1:8765/` e mostra o endereço da
rede. Daí em diante, os passos são os mesmos do Windows (`README.md`, «Instalação rápida», passos 3 a 5):

- criar o administrador;
- informar os dados em **Configurações → Serventia**;
- apontar os balcões para o servidor.

## Onde ficam as coisas

| | Linux | (no Windows) |
|---|---|---|
| Programa | `/opt/cartorio-gestao/sistema` | `C:\Program Files\CartorioGestao` |
| Dados (documentos, backups, chaves, `*.cred`) | `/var/lib/cartorio-gestao` (`CARTORIO_GESTAO_DATA`) | `C:\ProgramData\CartorioGestao` |
| Configuração do serviço | `/etc/cartorio-gestao/servidor.env` | `iniciar_servidor_servico.cmd` |
| Senha do banco | `/var/lib/cartorio-gestao/.pgpass` | `pgpass.conf` na pasta de dados |
| Log do servidor | `journalctl -u cartorio-gestao` | o log da pasta de dados |

## O dia a dia

```bash
systemctl status cartorio-gestao
```

```bash
journalctl -u cartorio-gestao -f
```

```bash
sudo systemctl restart cartorio-gestao
```

- **Firewall.** O banco não escuta a rede. Os balcões precisam da **TCP 8765** (o sistema) e da
  **UDP 8766** (a descoberta automática), liberadas só para a rede local. Com o `ufw` ligado, o
  script mostra os comandos, mas não os roda: a faixa da rede é a da casa. **Não exponha a 8765 à
  internet**; para acesso de fora, use VPN (como o Tailscale da reserva).
- **Atualizar.** Traga o código da versão nova (`git pull` da etiqueta, ou a pasta nova) e rode o
  instalador de novo. Ele recopia o código, atualiza o venv e reinicia o serviço, sem tocar no banco,
  na senha nem no `servidor.env`. O pacote `.cgu` da tela **Atualizações** ainda é aplicado pelo
  PowerShell (`installer/aplicar_atualizacao.ps1`): no Linux, a atualização é por este caminho.
- **Backup.** O `pg_dump` vem do `CG_PG_BIN` do `servidor.env`. A rotina agendada do backup e da
  conferência ainda não tem um *timer* do systemd: até lá, o backup é o da tela do sistema, ou um
  `pg_dump` no `cron` da casa, sempre para fora da máquina (`docs/BACKUP.md`).
- **Segurança.** Valem as recomendações de [`SEGURANCA_IMPLANTACAO.md`](SEGURANCA_IMPLANTACAO.md) e
  de [`SEGURANCA_REDE.md`](SEGURANCA_REDE.md). Já saem prontos do instalador: papel sem superusuário,
  SCRAM, senha só no `.pgpass`, banco só em localhost, e serviço com `ProtectSystem=full` e escrita
  só na pasta de dados.

## O que ainda é só do Windows

É o mesmo inventário do macOS (`MIGRAR_PARA_MACOS.md`). No Linux pesam estes itens:

| o quê | no Linux, hoje |
|---|---|
| **Token A3** (assinatura com certificado ICP-Brasil) | os drivers da casa são `.dll`. No Linux é preciso o driver PKCS#11 do fabricante (`.so`) e apontá-lo na configuração. **Não ensaiado.** |
| **Repositório de certificados do Windows** (ONR WS-Ofício) | não existe: use o `.pfx` do cofre |
| **Agendador de Tarefas** (rotinas da automação, conferência, compliance) | sem *timers* do systemd ainda. O despachante da automação já é portátil (`automacao.py`), mas falta a unidade que o agende. |
| **Atualização pela tela** (`.cgu`) | por enquanto, reinstalar a versão nova (acima) |
| **Aparelho selador e impressora térmica** | dependem do driver do fabricante para Linux |
| **Atalhos e instalador do balcão** | os balcões usam só o navegador; o `INSTALAR_CLIENTE.cmd` é do Windows |

Hoje o Linux é a máquina certa para **ensaio, treinamento e desenvolvimento**. A suíte prova no
Linux, a cada PR, o banco, as telas e os papéis em PDF. Para a **produção**, o caminho é fechar os itens
acima, um a um, com PR e teste, a começar pelo que a serventia usa no servidor (em geral, o token
A3 e as rotinas agendadas).

## Para quem desenvolve

A suíte roda no Linux exatamente como na CI (veja `docs/CI_EXECUTOR.md`):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-test.txt
```

```bash
CG_TEST_BACKEND=pg CG_PG_DSN="host=127.0.0.1 port=5432 user=<papel de teste> dbname=<banco de teste>" .venv/bin/python -m pytest tests -n 4 --dist loadfile
```

Use sempre um banco **descartável**, e nunca o da casa.
