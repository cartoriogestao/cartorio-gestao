# A pesquisa de satisfação na VPS

Ao lado do portal do cliente (`vps/portal/`), com o mesmo desenho: o servidor
da serventia **não fica na internet**. Ele EMPURRA os convites para cá e PUXA as
respostas de volta, sempre de saída, em HTTPS, com o token do portal.

## O que este serviço guarda

| guarda | não guarda |
|---|---|
| a chave do convite (sha256 do código do link) | o código (só existe no link do e-mail) |
| a atribuição (em branco no Protesto) | nome, e-mail, telefone |
| o dia do convite e até quando ele vale | número do protocolo, atendente |
| a nota, o comentário e o DIA da resposta | a hora, o IP (só na trava de erros, por 15 min) |

A resposta sai daqui quando o servidor confirma que a gravou. O convite fica,
marcado como respondido, até vencer (30 dias), e então sai também.

## Instalar (TI da serventia — não há deploy automático)

1. Usuário e pastas:
   `useradd --system --home /opt/cartorio-pesquisa cartorio-pesquisa`;
   `/opt/cartorio-pesquisa` (o programa), `/var/lib/cartorio-pesquisa` (o banco,
   dono `cartorio-pesquisa`, 700) e `/etc/cartorio-pesquisa`.
2. Copiar `pesquisa_vps.py` para `/opt/cartorio-pesquisa/`.
3. O token: o **mesmo conteúdo** de `/etc/cartorio-portal/token` (o servidor da
   casa usa o token do portal para os dois serviços), num arquivo deste serviço:
   `/etc/cartorio-pesquisa/token`, dono `cartorio-pesquisa`, permissão 600.
4. `pesquisa.env.exemplo` → `/etc/cartorio-pesquisa/pesquisa.env` (preencher o
   nome da serventia).
5. `cartorio-pesquisa.service` → `/etc/systemd/system/`; `systemctl daemon-reload`;
   `systemctl enable --now cartorio-pesquisa`.
6. O trecho de `apache-pesquisa.conf` dentro do `<VirtualHost *:443>` do site
   que já serve o portal; `apachectl configtest` e `systemctl reload apache2`.

## Ligar do lado da casa (o oficial)

1. Administrativo → Pesquisa de satisfação: o endereço público da página
   (`https://<o mesmo site do portal>/pesquisa`). O endereço é configuração:
   não está escrito em código nenhum.
2. O e-mail da automação configurado (Administrativo → Automação → Configuração),
   o mesmo dos avisos de andamento.
3. Ligar o processo **Convites da pesquisa de satisfação** na central da
   automação. Ele nasce DESLIGADO.

## Conferir

`curl -H "Authorization: Bearer $(cat /etc/cartorio-pesquisa/token)"
https://<site>/pesquisa/api/saude` devolve quantos convites e respostas há.
Sem o token, 401. Sem HTTPS (o cabeçalho do Apache), 403.
