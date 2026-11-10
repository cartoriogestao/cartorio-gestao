# Malote: PDFs de fraude e execução pelo agente local

O navegador do Mac oferece cinco ferramentas fixas por MCP: `estado_malote`,
`consultar_malote`, `executar_malote`, `enviar_anexos_pendentes` e
`autenticar_sistema`. Os argumentos são vazios: o modelo não escolhe URLs,
arquivos, pessoas ou código. `tools/malote_local_worker.mjs` também funciona
sem modelo. O executor usa um perfil próprio do Chrome, sem exportar cookies
ou ler senhas. O operador conclui o primeiro login/2FA nesse perfil.

A rotina determinística continua no despachante do sistema:
`MALOTE_CIENCIA_DIARIA`. Ele acessa o portal com a credencial no cofre, dá
ciência, baixa PDFs e cadastra. A triagem pode ser ligada na tela
`/automacao/malote/agente`; nessa tela se escolhem os responsáveis e
substitutos para RI/Notas, trabalho manual, digitalização, RCPN e Protesto/
Livro E. Não se alteram outras distribuições da instalação. A triagem usa o
Claude já configurado no sistema, com a barreira de privacidade existente.
O Qwen local coordena as ferramentas e recebe apenas estado operacional.

Sem responsável válido, a rotina para antes de dar ciência. O modo de
consulta não pode acionar um processo autorizado a dar ciência. Pedidos de
execução exigem processo ligado, `pode_agir`, triagem e distribuição válidas.
Solicitar não executa na requisição web: marca a fila, que o despachante
consome. A interface exige ADMIN e CSRF, inclusive para respostas JSON.
A API não altera as autorizações de execução por conta própria.

## PDFs de comunicações já cadastradas

Em `/automacao/malote/documentos`, o titular pode juntar a circular e os
anexos a alertas existentes, sem expediente nem tarefa. O servidor lê a capa
real do PDF, exige o código principal e o código do anexo na procedência dos
mesmos alertas, calcula SHA-256 e guarda o original em
`archive_root/malote/fraudes/<codigo-principal>/`. O nome físico é o hash;
o cliente não fornece caminho. Limite de 16 MB. O modo `conferir=1` só lê.

Os links de ver e baixar aparecem na lista de atenção. A autorização de
leitura é a mesma da tela de fraudes. Um mesmo arquivo pode estar vinculado
a todas as pessoas da comunicação sem duplicar o binário. A repetição não
recria alertas, vínculos, expediente ou tarefa. Falha no banco após copiar
preserva o original para a retomada. Hash divergente no disco exige revisão.
O tratamento automático de novos avisos também inclui os vínculos aos PDFs.

## Execução e retomada

O agente local usa a sessão do Chrome e CSRF; não é criada uma chave de API
com privilégios gerais. O cofre e a sessão do portal permanecem no servidor.
O MFA do portal é informado na tela do Malote do sistema quando solicitado.
A sessão do Chrome do sistema e a do robô do portal são independentes.

A agenda aprovada é dias úteis às 08h, retomada a cada 30 minutos enquanto
houver pendência. O servidor mantém a rodada das 08h. O Mac acompanha essa
rodada e só pede outra se necessário; um resultado OK com triagem completa
encerra as retomadas do dia. A intenção de cada pedido é gravada no Mac antes
do POST, e a mesma chave no servidor recupera pedido de resposta perdida.
Rodada já em execução é acompanhada. A trava local impede dois executores
no mesmo perfil. Uma execução interrompida de forma abrupta pode exigir
conferência da trava; não se remove uma trava de processo vivo.

PDF com páginas sem texto legível, conteúdo truncado ou falha de leitura não
é apresentado como triagem concluída: fica pendente de OCR/conferência.
A classificação de ciência continua passando pela revisão do oficial já
prevista no sistema. A rotina não envia respostas nem pratica atos.

## Implantação

A instalação segue `docs/AGENTES.md`: revisão do PR, pacote `.cgu` assinado
pelo titular e instalação antes da ativação. O agente não usa chave privada
de assinatura. A configuração de exemplo mantém `producaoLiberada=false`.
A agenda do Mac só deve ser instalada depois da conferência dos anexos e de
uma rodada real. Nenhuma agenda de outro processo deve ser alterada.

A configuração privada contém `sistema`, `httpRedePrivada`, `playwrightMcp`,
`perfil`, `pastaDados`, `pastaDocumentos`, `producaoLiberada` e
`anexosPendentes` (grupo, arquivo e SHA-256 fixos). Arquivos e credenciais
reais ficam fora do repositório. HTTPS é preferível; HTTP só é aceito com
opção expressa e IP Tailscale. Redirecionamento a outra origem é recusado.
A opção de lembrar o dispositivo por 30 dias do sistema exige HTTPS.

Testes Python usam PostgreSQL isolado; testes Node simulam o transporte e
exercitam agenda, retomada, hash, diretório permitido e filas concorrentes.
Eles não substituem o teste autenticado após instalar a atualização.
