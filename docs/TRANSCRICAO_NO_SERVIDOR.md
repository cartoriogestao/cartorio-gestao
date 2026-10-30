# Transcrever os áudios do WhatsApp neste servidor

Plano do oficial, 30/10/2026: na troca de servidor do fim do ano, os áudios passam a ser transcritos
dentro da casa, com o modelo grande, habilitado pelo próprio sistema. **Enquanto ninguém mudar a
escolha, nada muda:** o áudio vai à OpenAI, como hoje.

## Como ligar, no servidor novo

1. **Instale o programa no Python do sistema.** Ele fica fora do pacote de atualização:

   ```bash
   C:\ProgramData\CartorioGestao\runtime\Scripts\python.exe -m pip install faster-whisper==1.2.1
   ```

2. **Abra WhatsApp → Atendente com IA → Onde transcrever os áudios.** Quem grava é o ADMIN.
3. **Baixe o modelo.** São uns 3 GB, uma vez só, para a pasta de dados. O download roda sozinho, e a tela diz
   quando termina.
4. **Faça a conferência com um áudio de verdade.** A tela mede a memória livre, transcreve e mostra o texto
   e o tempo. Se não couber ou ficar lento, ela recusa e diz o motivo. O texto não fica guardado.
5. **Escolha «Neste servidor» e guarde.** Sem a conferência aprovada, o sistema recusa.

Para voltar à OpenAI, use a mesma escolha.

## O que foi medido

Em 29/10/2026, na máquina de hoje (15,7 GB, 3,1 GB livres), faster-whisper 1.2.1, CPU, int8, beam 5, em dois
áudios de 3,7 s e 2,8 s:

| Modelo | Tempo | Resultado |
|---|---|---|
| medium | 43 s e 38 s | errou um |
| large-v3-turbo | 64 s e 60 s | acertou os dois |
| large-v3 | | não carregou (`mkl_malloc: failed to allocate memory`) |

**Por isso a conferência existe, e por isso se mede de novo na máquina nova.**

## Como funciona

- **Processo separado:** `wa_transcricao_trabalhador.py` nasce para um áudio e morre. Ele não abre banco nem
  carrega o Flask, e roda abaixo da prioridade normal. O modelo só ocupa memória enquanto há áudio.
- **O áudio não sai da casa.** O arquivo de trabalho fica na pasta de dados e se apaga no fim, com erro ou sem.
- **Quem falha vai para uma pessoa,** como já acontece: mesma `TranscricaoErro`.
- **O teto do dia continua valendo:** a linha de `ia_uso` é gravada com o provedor `este-servidor`.

## O que ainda precisa ser visto na máquina nova

- **A rodada espera o áudio.** Com a IA ligada, a resposta depende da transcrição na mesma passada; por isso é um
  áudio por rodada, com prazo de 3 minutos. A busca de mensagens corre em outra linha do vigia e não para, mas
  cada áudio segura, por até esses 3 minutos, os downloads, a IA das outras conversas e o aviso de fora do horário.
  Se a máquina nova levar dezenas de segundos por áudio, é nessas respostas que isso se nota no balcão.
- **O programa de verdade não rodou no desenvolvimento.** Os testes usam um `faster_whisper` falso; os parâmetros
  são os da medição de 29/10. A conferência é o primeiro teste real.
