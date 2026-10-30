"""A fila do WhatsApp mora DENTRO do Cartorio Gestao.

Decisao do oficial em 02/09/2026: o balcao do WhatsApp nao e Chatwoot,
nem n8n, nem Evolution, nem WhatsApp Web. E o mesmo login, o mesmo Flask
e o mesmo SQLite. BSP (360dialog/Twilio) fica de fora desta fatia.

TABELA NOVA VAI NO SCHEMA, nao em MIGRACAO. MIGRACOES so ALTER TABLE ADD
COLUMN. Indice de coluna nova iria em INDICES_DEPOIS_DA_MIGRACAO.

Nenhum segredo da Meta entra no codigo: verify_token, app_secret,
phone_number_id, access_token, caixa_url e caixa_segredo comecam vazios.

E NENHUM MORA MAIS NO BANCO (LX14, 19/10/2026; A8 e B1 do LS03). O token, o
`app_secret`, o `verify_token` e o segredo da caixa-postal iam em `wa_config`,
em texto claro, em todo backup. Agora moram no cofre (`whatsapp.cred`,
cifrado, na pasta de dados — ver `cofre_cred`); a linha da tabela fica, vazia.
`phone_number_id` e `caixa_url` nao sao segredo e continuam no banco. A subida
move o que ainda estiver na coluna (`init_wa_schema`).

A serventia NAO expoe a porta 8765. Nao ha tunel no SERVIDOR do Cartorio
Gestao. A Meta entrega o inbound numa caixa-postal na VPS Hostinger
(Apache em https://equipetextual.com.br; o nome srv750938.hstgr.cloud
NAO tem TLS). Worker em 127.0.0.1 na VPS; CG puxa. Sem tunel no Windows.

O ATENDENTE COM IA, AS ETIQUETAS, O SETOR E O PRAZO (26/10/2026)
    Decisao do oficial em 26/10/2026: «é importante». A IA pode responder
    sozinha em QUATRO casos — andamento do protocolo (so depois da
    identificacao por numero + codigo de acompanhamento), duvidas gerais pelo
    texto-base aprovado, valores pela tabela (sempre ESTIMATIVA) e a
    transcricao do audio. Tudo o mais passa para uma pessoa, com a conversa
    marcada para o setor. O dominio mora em `wa_atendente.py`; a fila (varias
    etiquetas, setor, responsavel, transferencia e o painel do prazo) em
    `wa_fila.py`. Aqui so as tabelas e as chaves.

    - `wa_etiqueta`: VARIAS por conversa. A coluna `wa_conversa.etiqueta`
      continua sendo a do assunto que escolhe o rascunho (`classificar`).
    - `wa_evento`: o rastro do que se fez com a conversa — transferencia,
      passagem para pessoa, devolucao a IA, etiqueta posta e tirada.
    - `wa_ia_registro`: UMA linha por resposta automatica (ou tentativa): o que
      a IA leu (ja mascarado), o que respondeu, se saiu, provedor, modelo,
      tokens, segundos de audio e custo. E o registro que a decisao pede.
"""
from __future__ import annotations

import re

import cofre_cred as COFRE
from bd_nativo import banco

ABERTA = "aberta"
AGUARDANDO = "aguardando"
RESOLVIDA = "resolvida"
STATUS = (ABERTA, AGUARDANDO, RESOLVIDA)

# OS SETORES DA CONVERSA (26/10/2026). As chaves sao as do gestor
# (`gestor_rotina.NOME_DO_SETOR`) onde o setor existe la; ATENDIMENTO e o
# balcao geral, onde cai a conversa que ninguem marcou. Sem setor = ATENDIMENTO.
SETOR_PADRAO = "ATENDIMENTO"
SETORES = {
    "ATENDIMENTO": "Atendimento (balcão)",
    "RCPN": "Registro Civil",
    "RI": "Registro de Imóveis",
    "NOTAS": "Notas",
    "RCPJ_RTD": "RTD/PJ",
    "PROTESTO": "Protesto",
    "GESTAO": "Gestão (reclamações)",
}
# O QUE CADA SETOR FAZ (30/10/2026): é o que a IA lê para escolher o setor. Um lugar só.
DESCRICAO_DOS_SETORES = {
    "ATENDIMENTO": "quando não der para saber o assunto",
    "RCPN": "nascimento, casamento, óbito, habilitação de casamento, união estável",
    "RI": "matrícula, imóvel, averbação, usucapião, certidão de imóvel",
    "NOTAS": "escritura, procuração, testamento, ata notarial, reconhecimento de firma, "
             "autenticação",
    "RCPJ_RTD": "contrato social, estatuto, ata de assembleia, títulos e documentos",
    "PROTESTO": "título, intimação, cancelamento de protesto",
    "GESTAO": "reclamação sobre o atendimento ou o cartório",
}

# QUEM ATENDE A CONVERSA AGORA. `ia` e o padrao: a IA so responde se o
# interruptor geral estiver ligado (`CHAVE_IA_LIGADA`). `pessoa` e a conversa
# passada a uma pessoa: a IA nao responde mais nela ate alguem devolver.
MODO_IA = "ia"
MODO_PESSOA = "pessoa"

# A situacao da mensagem que chegou, para o atendente (`wa_mensagem.ia_situacao`).
# NULL = ainda nao vista. `processando` e a trava de quem a pegou.
IA_PROCESSANDO = "processando"
IA_RESPONDIDA = "respondida"
IA_PASSADA = "passada"
IA_FORA = "fora"            # IA desligada, conversa com pessoa, ou anterior ao liga
IA_ERRO = "erro"
# A CORTESIA (30/10/2026): «bom dia» e «obrigado» não são pedido. A mensagem não abre
# espera, e por isso `wa_fila._ESPERANDO_DESDE` não a conta, nem tira do alerta uma
# pergunta de antes.
IA_CORTESIA = "cortesia"

ETIQUETAS = (
    "horario", "endereco", "documentos", "certidao",
    "firma", "protesto", "outros",
)

CHAVE_VERIFY = "verify_token"
CHAVE_APP_SECRET = "app_secret"
CHAVE_PHONE = "phone_number_id"
CHAVE_TOKEN = "access_token"
CHAVE_CAIXA_URL = "caixa_url"
CHAVE_CAIXA_SEGREDO = "caixa_segredo"
# O MODO DE TESTE DO WEBHOOK (M6 do LS01, lote LX11): só com ele LIGADO o
# `X-Wa-Test: 1` entra sem assinatura. Nasce vazio = desligado.
CHAVE_MODO_TESTE = "modo_teste"

# URL publica documentada da caixa-postal (TLS do site, nao hstgr.cloud).
# Path /pendentes e o GET que o CG puxa. Alternativa: prefixo /wa-caixa.
CAIXA_URL_DOCUMENTADA = "https://equipetextual.com.br/pendentes"
WEBHOOK_PUBLICO_DOCUMENTADO = "https://equipetextual.com.br/whatsapp/webhook"

# Token de desenvolvimento. Nao e segredo de producao: so libera o GET de
# verify e o POST de teste (X-Wa-Test) enquanto a casa ainda nao gravou o
# verify_token da Meta. Documentado em DOCUMENTACAO/PROJETO_BALCAO_WHATSAPP.md.
VERIFY_TOKEN_DEV = "cartorio-teste"

# O ATENDENTE COM IA (26/10/2026). Nada disto e segredo: a chave do provedor
# mora em `agente.cred` (`agente_provedores`), fora do banco, como sempre.
# TUDO NASCE VAZIO = DESLIGADO. Quem liga e o ADMIN, na tela do atendente.
CHAVE_IA_LIGADA = "ia_ligada"                  # "1" = responde sozinha
CHAVE_IA_LIGADA_EM = "ia_ligada_em"            # so responde o que chegou depois
CHAVE_IA_LIGADA_POR = "ia_ligada_por"
CHAVE_AUDIO_LIGADO = "ia_audio_ligado"         # "1" = transcreve o audio
CHAVE_IA_AVISO_PASSAGEM = "ia_aviso_passagem"  # "1" = avisa o cliente da passagem
CHAVE_IA_PROVEDOR = "ia_provedor"
CHAVE_IA_MODELO = "ia_modelo"
CHAVE_IA_PRECO_ENTRADA = "ia_preco_entrada"    # US$ por milhao de tokens
CHAVE_IA_PRECO_SAIDA = "ia_preco_saida"
CHAVE_AUDIO_MODELO = "ia_audio_modelo"
CHAVE_AUDIO_PRECO_MINUTO = "ia_audio_preco_minuto"   # US$ por minuto
CHAVE_AUDIO_ONDE = "ia_audio_onde"             # vazio = OpenAI (`wa_transcricao_local`)
CHAVE_AUDIO_CONFERENCIA = "ia_audio_conferencia"  # a última, sem o texto do áudio
CHAVE_TEXTO_BASE = "ia_texto_base"
CHAVE_TEXTO_BASE_POR = "ia_texto_base_aprovado_por"
CHAVE_TEXTO_BASE_EM = "ia_texto_base_aprovado_em"
CHAVE_VALORES = "ia_valores"                   # "codigo_tj | nome", um por linha
CHAVE_PRAZO_MINUTOS = "prazo_resposta_minutos"

# OS MODELOS DA META (27/10/2026, `wa_modelos`). Nada disto e segredo. O
# interruptor nasce VAZIO = desligado: enquanto a Meta nao aprovar, tudo
# continua como era. Nome de modelo vazio = o padrao de `wa_modelos.MODELOS`.
CHAVE_MODELOS_APROVADOS = "modelos_aprovados"    # "1" = a Meta aprovou, pode usar
CHAVE_NOME_NO_MODELO = "nome_no_modelo"          # o {{1}}: «de Exemplo»
CHAVE_MODELO_EXIGENCIA = "modelo_exigencia"
CHAVE_MODELO_PRONTO = "modelo_pronto_retirar"
CHAVE_MODELO_PRAZO = "modelo_prenotacao_vencendo"
CHAVE_MODELO_PESQUISA = "modelo_pesquisa_satisfacao"
CHAVE_MODELO_RETOMAR = "modelo_retomar_atendimento"

# O BALCÃO QUE FUNCIONA SOZINHO (29/10/2026). Pedido do oficial: «preciso que
# o whatsapp seja mais funcional, preciso que atualize em tempo real (se nao
# possivel com frequencia de 30s […]), receba arquivos enviados na conversa,
# configure a IA para fazer o primeiro atendimento, passando para atendente
# quando houver justo motivo». Nada disto é segredo.
#   - `vigia_segundos`: de quantos em quantos segundos o servidor busca na
#     caixa-postal (`wa_vigia`). Vazio = o padrão (20 s); «0» = desligada.
#   - `horario_atendimento`: «seg-sex 08:00-17:00», uma faixa por linha
#     (`wa_horario`). Vazio = sem horário: nada de aviso de fora do horário.
#   - `fora_horario_ligado` / `fora_horario_texto`: o aviso automático a quem
#     escreve com o balcão fechado — uma vez por período fechado.
#   - `respostas_prontas`: «atalho | texto», uma por linha, para quem atende.
#   - `encerrar_aguardando_dias`: a conversa respondida em que o cliente não
#     voltou se resolve sozinha depois de N dias. Vazio = o padrão; «0» = nunca.
CHAVE_VIGIA_SEGUNDOS = "vigia_segundos"
CHAVE_HORARIO = "horario_atendimento"
CHAVE_FORA_HORARIO_LIGADO = "fora_horario_ligado"
CHAVE_FORA_HORARIO_TEXTO = "fora_horario_texto"
CHAVE_RESPOSTAS_PRONTAS = "respostas_prontas"
CHAVE_ENCERRAR_DIAS = "encerrar_aguardando_dias"

# A SITUAÇÃO DO ARQUIVO QUE O CLIENTE MANDOU (`wa_mensagem.midia_situacao`).
# NULL = ainda não baixado; «baixando» é a trava de quem o pegou.
MIDIA_BAIXANDO = "baixando"
MIDIA_OK = "ok"
MIDIA_ERRO = "erro"

CHAVES_CONFIG = (
    CHAVE_VERIFY, CHAVE_APP_SECRET, CHAVE_PHONE, CHAVE_TOKEN,
    CHAVE_CAIXA_URL, CHAVE_CAIXA_SEGREDO, CHAVE_MODO_TESTE,
    CHAVE_IA_LIGADA, CHAVE_IA_LIGADA_EM, CHAVE_IA_LIGADA_POR,
    CHAVE_AUDIO_LIGADO, CHAVE_IA_AVISO_PASSAGEM, CHAVE_IA_PROVEDOR,
    CHAVE_IA_MODELO, CHAVE_IA_PRECO_ENTRADA, CHAVE_IA_PRECO_SAIDA,
    CHAVE_AUDIO_MODELO, CHAVE_AUDIO_PRECO_MINUTO, CHAVE_TEXTO_BASE,
    CHAVE_TEXTO_BASE_POR, CHAVE_TEXTO_BASE_EM, CHAVE_VALORES,
    CHAVE_PRAZO_MINUTOS,
    CHAVE_MODELOS_APROVADOS, CHAVE_NOME_NO_MODELO, CHAVE_MODELO_EXIGENCIA,
    CHAVE_MODELO_PRONTO, CHAVE_MODELO_PRAZO, CHAVE_MODELO_PESQUISA,
    CHAVE_MODELO_RETOMAR,
    CHAVE_VIGIA_SEGUNDOS, CHAVE_HORARIO, CHAVE_FORA_HORARIO_LIGADO,
    CHAVE_FORA_HORARIO_TEXTO, CHAVE_RESPOSTAS_PRONTAS, CHAVE_ENCERRAR_DIAS,
)

# O QUE E SEGREDO, e por isso mora no cofre e nao em `wa_config` (LX14). O
# `verify_token` entra: e ele que a Meta repete para provar que e ela, e quem o
# lesse na tela (B1) respondia ao desafio do webhook no lugar da casa.
SEGREDOS = frozenset({
    CHAVE_VERIFY, CHAVE_APP_SECRET, CHAVE_TOKEN, CHAVE_CAIXA_SEGREDO,
})

SCHEMA = """
CREATE TABLE IF NOT EXISTS wa_conversa (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    wa_id TEXT NOT NULL,
    nome TEXT,
    etiqueta TEXT,
    status TEXT NOT NULL DEFAULT 'aberta',
    rascunho TEXT,
    auto_ok INTEGER NOT NULL DEFAULT 0,
    atualizado_em TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_wa_conversa_wa_id
    ON wa_conversa(wa_id);
CREATE INDEX IF NOT EXISTS idx_wa_conversa_atualizado
    ON wa_conversa(atualizado_em);

CREATE TABLE IF NOT EXISTS wa_mensagem (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    conversa_id INTEGER NOT NULL REFERENCES wa_conversa(id),
    direcao TEXT NOT NULL,
    texto TEXT,
    bruto_json TEXT,
    criado_em TEXT,
    meta_id TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_wa_mensagem_meta_id
    ON wa_mensagem(meta_id) WHERE meta_id IS NOT NULL AND meta_id != '';
CREATE INDEX IF NOT EXISTS idx_wa_mensagem_conversa
    ON wa_mensagem(conversa_id, criado_em);

CREATE TABLE IF NOT EXISTS wa_config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS wa_etiqueta (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    conversa_id bigint NOT NULL REFERENCES wa_conversa(id),
    etiqueta TEXT NOT NULL,
    origem TEXT NOT NULL DEFAULT 'manual',
    criado_em TEXT,
    criado_por TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_wa_etiqueta
    ON wa_etiqueta(conversa_id, etiqueta);

CREATE TABLE IF NOT EXISTS wa_evento (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    conversa_id bigint NOT NULL REFERENCES wa_conversa(id),
    quando TEXT NOT NULL,
    tipo TEXT NOT NULL,
    de_setor TEXT,
    para_setor TEXT,
    responsavel_id bigint,
    por TEXT,
    nota TEXT
);
CREATE INDEX IF NOT EXISTS idx_wa_evento_conversa
    ON wa_evento(conversa_id, id);

CREATE TABLE IF NOT EXISTS wa_ia_registro (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    conversa_id bigint NOT NULL REFERENCES wa_conversa(id),
    wa_id TEXT NOT NULL,
    quando TEXT NOT NULL,
    caso TEXT NOT NULL,
    lido TEXT,
    respondido TEXT,
    enviado INTEGER NOT NULL DEFAULT 0,
    meta_id TEXT,
    passou_para TEXT,
    motivo TEXT,
    provedor TEXT,
    modelo TEXT,
    tokens_entrada bigint NOT NULL DEFAULT 0,
    tokens_saida bigint NOT NULL DEFAULT 0,
    segundos_audio double precision NOT NULL DEFAULT 0,
    custo_usd double precision,
    erro TEXT
);
CREATE INDEX IF NOT EXISTS idx_wa_ia_registro_quando
    ON wa_ia_registro(quando, id);
CREATE INDEX IF NOT EXISTS idx_wa_ia_registro_wa_id
    ON wa_ia_registro(wa_id, caso, quando);

CREATE TABLE IF NOT EXISTS wa_entrega_pendente (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    meta_id TEXT NOT NULL,
    situacao TEXT NOT NULL,
    erro TEXT,
    quando TEXT,
    recebido_em TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_wa_entrega_pendente
    ON wa_entrega_pendente(meta_id, situacao);
"""

# AS COLUNAS DO ATENDENTE E DA FILA (26/10/2026). Todas aceitam NULL: a
# conversa e a mensagem de antes continuam valendo como eram — sem setor e o
# ATENDIMENTO, sem modo e a IA, sem tipo e texto, sem autor e quem respondeu
# pelo botao antes do registro do autor.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    ("wa_conversa", "setor", "TEXT"),
    ("wa_conversa", "responsavel_id", "bigint"),
    ("wa_conversa", "modo", "TEXT"),
    ("wa_conversa", "passagem_motivo", "TEXT"),
    ("wa_mensagem", "tipo", "TEXT"),
    ("wa_mensagem", "midia_id", "TEXT"),
    ("wa_mensagem", "transcricao", "TEXT"),
    ("wa_mensagem", "autor", "TEXT"),
    ("wa_mensagem", "ia_situacao", "TEXT"),
    ("wa_mensagem", "ia_desde", "TEXT"),
    # POR QUE PASSOU PARA PESSOA (30/10/2026): o vocabulário é `wa_atendente.RAZOES`.
    # Vazio é registro de antes desta versão.
    ("wa_ia_registro", "razao", "TEXT"),
    # A RESOLVIDA FICA GUARDADA E VOLTA COM O HISTÓRICO OCULTO (27/10/2026).
    # Nada se apaga: `resolvida_em` diz quando ela saiu das abas de trabalho
    # (e conta os 7 dias do responsável na volta), e `atendimento_desde_id` é
    # o id da primeira mensagem do atendimento atual — a tela mostra dali em
    # diante e guarda o resto atrás de «Ver histórico». As resolvidas de antes
    # desta versão ficam com `resolvida_em` vazio e contam pelo `atualizado_em`;
    # sem `atendimento_desde_id`, a conversa mostra tudo, como antes.
    ("wa_conversa", "resolvida_em", "TEXT"),
    ("wa_conversa", "atendimento_desde_id", "bigint"),
    # O ARQUIVO QUE O CLIENTE MANDA (29/10/2026): até aqui só o tipo e o id da
    # mídia ficavam gravados, e a foto ou o PDF nunca chegavam ao balcão. Agora
    # `wa_midia` baixa da Meta e guarda o arquivo na pasta da casa; estas
    # colunas dizem onde ele está, o nome, o tipo, o tamanho e o sha256. O
    # arquivo que SAI (enviado por quem atende) usa as mesmas colunas.
    ("wa_mensagem", "midia_situacao", "TEXT"),
    ("wa_mensagem", "midia_desde", "TEXT"),
    ("wa_mensagem", "arquivo_nome", "TEXT"),
    ("wa_mensagem", "arquivo_caminho", "TEXT"),
    ("wa_mensagem", "arquivo_mime", "TEXT"),
    ("wa_mensagem", "arquivo_bytes", "bigint"),
    ("wa_mensagem", "arquivo_sha256", "TEXT"),
    ("wa_mensagem", "arquivo_erro", "TEXT"),
    # A ENTREGA DO QUE SAIU (29/10/2026): a Meta devolve «sent», «delivered»,
    # «read» ou «failed» para cada mensagem enviada, e isso era jogado fora.
    # O ERRO PASSAGEIRO VOLTA À FILA (29/10/2026): a rede que caiu, o tempo
    # esgotado e a Graph com 5xx ou 429 não viram erro na hora; contam aqui, e a
    # mensagem tenta de novo sozinha até `wa_midia.TENTATIVAS_DA_MIDIA` vezes.
    ("wa_mensagem", "midia_tentativas", "INTEGER"),
    ("wa_mensagem", "entrega", "TEXT"),
    ("wa_mensagem", "entrega_em", "TEXT"),
    ("wa_mensagem", "entrega_erro", "TEXT"),
    # O AVISO DE FORA DO HORÁRIO sai uma vez por período fechado (`wa_rotina`).
    ("wa_conversa", "fora_horario_avisado_em", "TEXT"),
    # A SUGESTÃO NÃO É TEXTO ESCRITO (30/10/2026): o texto automático mora aqui,
    # e o `rascunho` é só o que uma pessoa guardou.
    ("wa_conversa", "sugestao", "TEXT"),
    # O ENVIO SEM DUPLICAR (30/10/2026): o token que o navegador gerou para esta
    # mensagem. O mesmo token de novo devolve a já gravada, sem postar outra vez.
    ("wa_mensagem", "envio_token", "TEXT"),
)
INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_wa_mensagem_ia "
    "ON wa_mensagem(direcao, ia_situacao, id)",
    "CREATE INDEX IF NOT EXISTS idx_wa_conversa_setor "
    "ON wa_conversa(setor, status)",
    # A aba «Resolvidas» ordena pela data de resolver (27/10/2026).
    "CREATE INDEX IF NOT EXISTS idx_wa_conversa_resolvida "
    "ON wa_conversa(status, resolvida_em)",
    # O vigia procura, a cada volta, o arquivo que ainda não foi baixado.
    "CREATE INDEX IF NOT EXISTS idx_wa_mensagem_midia "
    "ON wa_mensagem(midia_situacao, id) WHERE midia_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_wa_mensagem_envio_token "
    "ON wa_mensagem(conversa_id, envio_token) WHERE envio_token IS NOT NULL",
    # O `/novas` roda de 2 em 2 s (30/10/2026): só o que veio depois, e as últimas
    # enviadas, sem passar pela conversa inteira.
    "CREATE INDEX IF NOT EXISTS idx_wa_mensagem_conversa_id "
    "ON wa_mensagem(conversa_id, id)",
    "CREATE INDEX IF NOT EXISTS idx_wa_mensagem_conversa_direcao "
    "ON wa_mensagem(conversa_id, direcao, id)",
)


def _passar_rascunhos_antigos(bd) -> None:
    """AS LINHAS DE ANTES DA COLUNA `sugestao` (30/10/2026), uma vez só. O
    `rascunho` era quase sempre texto automático, ou o que já tinha sido enviado:
    o já enviado some, e o resto vira sugestão. Assim nada aparece escrito
    sozinho, e um rascunho humano antigo ainda fica acessível pelo TAB."""
    bd.escrever(
        """UPDATE wa_conversa c SET rascunho=NULL
            WHERE btrim(COALESCE(c.rascunho, '')) = btrim(COALESCE(
                  (SELECT m.texto FROM wa_mensagem m
                    WHERE m.conversa_id = c.id AND m.direcao = 'out'
                    ORDER BY m.id DESC LIMIT 1), ''))""")
    bd.escrever(
        """UPDATE wa_conversa SET sugestao=rascunho, rascunho=NULL
            WHERE btrim(COALESCE(rascunho, '')) <> ''""")


def init_wa_schema(con) -> None:
    """Cria as tabelas da fila do WhatsApp. Idempotente."""
    bd = banco(con)
    for comando in re.split(r";[ \t]*\n", SCHEMA):
        if re.sub(r"--[^\n]*", "", comando).strip():
            bd.escrever(comando)
    # Só a subida que CRIA a coluna passa as linhas antigas: depois dela, o
    # `rascunho` é de uma pessoa e não se mexe mais.
    sem_sugestao = not bd.tem_coluna("wa_conversa", "sugestao")
    for tabela, coluna, tipo in MIGRACOES:
        if not bd.tem_coluna(tabela, coluna):
            bd.escrever(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    if sem_sugestao:
        _passar_rascunhos_antigos(bd)
    for comando in INDICES_DEPOIS_DA_MIGRACAO:
        bd.escrever(comando)
    for chave in CHAVES_CONFIG:
        bd.escrever(
            "INSERT INTO wa_config(chave, valor) VALUES (%s, '') "
            "ON CONFLICT DO NOTHING",
            (chave,),
        )
    # O SEGREDO QUE AINDA ESTA NA COLUNA VAI PARA O COFRE — o da instalacao de
    # antes do LX14, ou o de um backup antigo restaurado. Idempotente.
    COFRE.migrar_da_tabela(bd, "wa_config", sorted(SEGREDOS), COFRE.WHATSAPP)
