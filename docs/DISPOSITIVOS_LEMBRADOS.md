# Lembrar este dispositivo por 30 dias

Na verificação em duas etapas, marque a opção apenas em computador próprio.
Após senha e código válido do aplicativo, os próximos logins neste navegador
continuam exigindo a senha, mas dispensam outro código por até 30 dias. O prazo
é absoluto: entrar de novo não o prorroga. As sessões mantêm os prazos normais
de inatividade e duração máxima. Limpar cookies ou usar janela anônima perde a
lembrança. Código de recuperação não autoriza lembrar o dispositivo.

Em Conta → Verificação em duas etapas, «Esquecer todos os dispositivos» exige
senha e código. Trocar senha, editar o cadastro, desativar a conta, zerar/reativar a
verificação ou gerar novos códigos de recuperação invalida as autorizações.
Bloqueio por tentativas de 2FA também impede o uso do comprovante. Esquecer
os dispositivos afeta o próximo login; não encerra sessões já abertas.

A opção só é emitida e aceita no servidor principal por HTTPS. A aplicação
precisa receber o esquema HTTPS de uma terminação TLS confiável. Não confie
indiscriminadamente em cabeçalhos Forwarded/X-Forwarded-Proto enviados por
clientes. Um acesso HTTP, mesmo em rede privada, continua pedindo código.
O servidor reserva continua com seu login de senha e TOTP, sem gravar tokens.

O navegador guarda um comprovante aleatório de 256 bits no cookie
`__Host-cg_dispositivo`, Secure, HttpOnly, SameSite=Lax, Path=/, sem Domain.
O banco guarda somente seu SHA-256, a conta, uma versão derivada das
credenciais e a expiração. Nenhum código ou segredo TOTP é guardado no Chrome.
A emissão e o uso ficam no rastro de auditoria sem o comprovante. No máximo dez
navegadores por conta; novas emissões retiram os mais antigos e os expirados.
O comprovante funciona como credencial de posse: quem copiar um cookie válido
junto com a senha pode utilizá-lo até sua expiração ou revogação.

Migração apenas aditiva, sem dependência nova. A entrega segue o pacote `.cgu`
assinado pelo titular. Criar ou mesclar o PR não instala a mudança.

Referências de implementação: [Flask](https://flask.palletsprojects.com/en/stable/web-security/)
e [OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
