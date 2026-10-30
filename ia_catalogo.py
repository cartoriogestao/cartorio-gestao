"""O CATÁLOGO DOS SISTEMAS DE IA DESTA CASA — código, e não tabela.

POR QUE CÓDIGO (LF01, 19/10/2026)
    O relatório anual à COGEX (Código de Normas do MA, art. 170, § 4º) começa
    por «sistemas e finalidades». Uma tabela que alguém preenche na tela diria
    o que a pessoa lembrou; este catálogo diz o que o CÓDIGO faz — e há teste
    (`tests/test_ia_uso.py`) que varre o sistema e falha se aparecer chamada a
    um transporte de IA sem entrada aqui, ou entrada aqui sem chamada no
    código. **O catálogo que mente é pego no mesmo dia.**

    Cada entrada foi MEDIDA no chamador em 19/10/2026: o que sobe ao provedor,
    se passa pela máscara, onde a pessoa revisa e o que a IA não faz. Mudou o
    chamador, muda a entrada — e o teste aponta qual.

O ENQUADRAMENTO NO ART. 171 É PROPOSTA, E NÃO DECISÃO
    O MA autoriza IA só nos usos do art. 171. A base que o sistema tem é um
    RESUMO de terceiro, com os cinco usos sem a redação oficial dos incisos; a
    numeração abaixo segue a ordem do resumo. **Quem enquadra é o oficial**, e
    cada tela diz para conferir o texto oficial (`AVISO_DO_TEXTO_OFICIAL`).
"""
from __future__ import annotations

import importlib
from typing import Any

# A FRASE QUE TODA TELA E TODO RELATÓRIO REPETEM enquanto a base for o resumo.
AVISO_DO_TEXTO_OFICIAL = (
    "Base normativa: resumo de terceiro do Código de Normas do Foro "
    "Extrajudicial do Maranhão (Provimento COGEX 28/2026, arts. 167–179), com "
    "data de corte de 25/08/2026 — conferir o texto oficial do Código de Normas.")

NORMA_DO_RELATORIO = ("Código de Normas do Foro Extrajudicial do MA (Provimento "
                      "COGEX 28/2026), art. 170, § 4º")

# OS USOS DO ART. 171, na ordem do resumo (`ia-por-uf.md`): «redação/análise/
# revisão, triagem, indexação, atendimento com escalonamento humano e análise
# preditiva». O inciso I está confirmado no próprio sistema (`agente_notas`);
# os demais seguem a ordem do resumo.
INCISOS_DO_ART_171 = {
    "I": "redação, análise e revisão",
    "II": "triagem de documentos",
    "III": "indexação",
    "IV": "atendimento, com escalonamento para pessoa",
    "V": "análise preditiva",
}

# O REQUISITO DO MA PARA O FORNECEDOR, nas palavras do resumo. O relatório
# compara os dados que o oficial preencheu com ele (`ia_uso.pendencias`).
REQUISITO_DO_FORNECEDOR = ("solução desenvolvida ou armazenada no Brasil, banco "
                           "no servidor da serventia, ISO 27001")

LEMBRETE_FEDERAL = (
    "A declaração anual federal do Provimento CN 213/2026 (art. 17 — campo "
    "próprio no Sistema Justiça Aberta, com a síntese do dossiê técnico) é OUTRA "
    "obrigação: este relatório não a substitui, e ela não substitui este.")

# OS TRANSPORTES — os dois únicos lugares do sistema que falam com provedor
# de IA. `rascunhar` entra porque é a porta do `chamar_provedor` para a tela.
# O TERCEIRO (26/10/2026): `wa_transcricao.transcrever`, a transcrição do áudio
# do WhatsApp pela OpenAI — o único provedor da casa que recebe áudio. Ele grava
# a própria linha de `ia_uso`, como os outros dois.
# O QUARTO (30/10/2026): `wa_transcricao_local.transcrever`, a mesma transcrição dentro da
# casa. Não fala com provedor nenhum, e entra aqui porque grava a própria linha de `ia_uso`,
# e quem o pega tem de dizer a finalidade, como nos outros.
TRANSPORTES = {
    "agente_provedores": ("conversar",),
    "robo_llm": ("chamar_provedor", "rascunhar"),
    "wa_transcricao": ("transcrever",),
    "wa_transcricao_local": ("transcrever",),
}

CHAVE_FORA_DO_BANCO = "agente.cred, na pasta de dados — fora do banco"

# O TETO DE USO POR DIA DOS SISTEMAS QUE NÃO TINHAM TETO (B5 do LS03; LX13,
# 19/10/2026). Revisão prévia, ônus, leitura do RCPN e robôs tinham `teto:
# None`: um laço, um clique repetido ou um PDF de mil folhas (M12) iam ao
# provedor sem parar, e a conta só aparecia no fim do mês.
#
# CONTA CHAMADAS AO PROVEDOR, e não cliques, porque é o que o registro
# (`ia_uso`) sabe contar: uma leitura do RCPN são várias chamadas (a triagem e
# uma por página), uma revisão prévia é uma. Os números são a casa vezes uma
# folga larga — o teto existe para parar o que fugiu do normal, e não para
# racionar o balcão:
#   - revisão prévia: uma chamada por revisão; a casa lavra dezenas de atos
#     num dia cheio;
#   - ônus: um clique por certidão de matrícula;
#   - leitura do RCPN: até 40 páginas por leitura (`rc_leitura_documentos.
#     MAXIMO_DE_PAGINAS`), dez leituras grandes num dia;
#   - robôs: é a tela de TESTAR o robô, e não atendimento.
# Quem confere é `ia_uso.passou_do_teto`, chamado ANTES da rede por quem chama
# o transporte; passou, a chamada não sai e a tela diz o porquê.
#
# E DESDE 26/10/2026 QUEM TRAVA É O TRANSPORTE (achado transversal 3 da
# revisão de segurança): `ia_uso.reservar` toma a vaga antes da rede, em
# `agente_provedores.conversar` e em `robo_llm.chamar_provedor`, e a chamada
# que falha a devolve. A conferência de quem chama ficou como cortesia — recusa
# cedo, antes de abrir linha ou ler documento.
CHAMADAS_POR_DIA = {
    "revisao_previa": 200,
    "ri_onus_ia": 100,
    "rc_leitura": 400,
    # A LEITURA DO BALCÃO DAS NOTAS (26/10/2026): um RG ou um CRV são duas a
    # quatro chamadas (a triagem e uma por página); duzentas por dia são
    # cinquenta leituras, mais do que o balcão de firmas atende com documento.
    "nt_leitura": 200,
    "robo_rascunho": 50,
    # O AGENTE DE MINUTAS (23/10/2026): cada pedido é UMA chamada ao Opus, com
    # os documentos inteiros — sessenta minutas e revisões por dia é mais do que
    # o balcão produz, e segura um laço que engasgue.
    "minuta_ia": 60,
    # O ATENDENTE DO WHATSAPP (26/10/2026): uma chamada por conversa atendida
    # (as mensagens seguidas do mesmo cliente vão juntas). Quatrocentas por dia
    # é várias vezes o movimento do balcão; o que passar disso vai para pessoa.
    "wa_atendente": 400,
    # A TRANSCRIÇÃO: uma chamada por áudio.
    "wa_audio": 200,
    # A QUALIFICAÇÃO ASSISTIDA DO RI (26/10/2026): uma chamada ao Opus por
    # pedido, com o título e o ITBI inteiros. VINTE POR DIA — decisão do oficial
    # em 26/10/2026 (a proposta era 40). É o PADRÃO DE FÁBRICA: o ADMIN muda o
    # número na configuração da qualificação assistida, com auditoria
    # (`ri_qualificacao_ia.teto_do_dia`, `settings.qualificacao_ia_teto_dia`).
    "ri_qualificacao_ia": 20,
}

# ------------------------------------------------------------------ o catálogo
#
# `codigo` é a FINALIDADE que o chamador passa ao transporte e que fica em
# `ia_uso.finalidade`. `modulo` é onde ela é declarada. `teto` aponta para a
# constante do módulo — o relatório lê o número de lá, e não de uma cópia.

CATALOGO: tuple[dict[str, Any], ...] = (
    {
        "codigo": "revisao_previa",
        "nome": "Revisão prévia do ato (RI e Notas)",
        "modulo": "revisao_previa",
        "onde": "botão «Revisar» na matrícula (RI) e no ato de Notas",
        "finalidade": "revisar o ato antes da lavratura e apontar o que está "
                      "faltando ou errado, separando o grave do que é atenção",
        "inciso": "I",
        "enquadramento": "revisão de ato",
        "dado": "a matrícula com os atos e o ato a registrar (RI); as fichas das "
                "partes e o texto do ato (Notas); a transcrição dos anexos",
        "mascara": "só com a máscara da revisão ligada (Configurações, "
                   "revisao_mascara); o padrão da casa é sem máscara",
        "mascarado": None,
        "revisao_humana": "apontamento GRAVE impede lavrar sem justificativa "
                          "escrita; só ADMIN ou MANAGER dá o grave por suprido",
        "nao_faz": "não decide, não lavra, não sela",
        "teto": ("ia_catalogo", "CHAMADAS_POR_DIA", "chamadas ao provedor por dia",
                 "revisao_previa"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        "codigo": "revisao_anexos",
        "nome": "Leitura dos anexos na revisão prévia",
        "modulo": "revisao_anexos",
        "onde": "dentro da revisão prévia, quando o ato tem anexos digitalizados",
        "finalidade": "separar os anexos que importam e transcrever as páginas "
                      "deles para o dossiê da revisão",
        "inciso": "II",
        "enquadramento": "triagem de documentos",
        "dado": "as páginas digitalizadas (imagem) e o texto das primeiras "
                "páginas (até três, na triagem)",
        "mascara": "não: documento digitalizado não se mascara — com a máscara "
                   "da revisão ligada, os anexos não sobem",
        "mascarado": False,
        "revisao_humana": "a transcrição entra no dossiê da revisão prévia, e a "
                          "tela mostra o que foi lido e o que ficou de fora",
        "nao_faz": "não decide nada do ato",
        "teto": ("revisao_anexos", "TETO_DE_PAGINAS", "páginas por ato"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        # LH11, 21/10/2026: «colocar IA pra revisar as certidões transcritas
        # (principalmente as de livros antigos) do RI».
        "codigo": "revisao_transcricao",
        "nome": "Revisão das transcrições do RI contra a página escaneada",
        "modulo": "revisao_transcricao",
        "onde": "botão «Revisar a transcrição com IA» no quadro da certidão de "
                "inteiro teor da matrícula, e Registro de Imóveis → Revisar "
                "transcrições em lote (só ADMIN e MANAGER)",
        "finalidade": "comparar o texto transcrito da ficha antiga com a página "
                      "escaneada do livro e apontar as divergências, separando a "
                      "grave da leve",
        "inciso": "I",
        "enquadramento": "revisão de ato (conferência de transcrição)",
        "dado": "o texto transcrito da ficha, o cadastro dela e as imagens das "
                "páginas escaneadas (duas por chamada, até 40 por ficha)",
        "mascara": "não: a imagem da página vai ao provedor por decisão do oficial "
                   "de 21/10/2026, só nesta revisão (página não se mascara); com "
                   "revisao_transcricao_manda_imagem = '0' a imagem não sobe e o "
                   "texto segue a máscara da revisão (revisao_mascara)",
        "mascarado": None,
        "revisao_humana": "divergência GRAVE não resolvida pede justificativa escrita "
                          "para emitir a certidão; só ADMIN ou MANAGER dá a divergência "
                          "por conferida no livro",
        "nao_faz": "não corrige o teor, não emite, não sela; com a IA fora do ar a "
                   "certidão sai e a tela diz que saiu sem revisão",
        "teto": ("revisao_transcricao", "TETO_DE_PAGINAS_POR_RODADA",
                 "páginas por rodada do lote (o padrão; a configuração muda), e "
                 "40 por ficha"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        "codigo": "gestor_leitura",
        "nome": "Leitura dos textos pelo gestor",
        "modulo": "gestor_leitura",
        "onde": "rotina diária do gestor (07:30); os apontamentos ficam em "
                "Administrativo → Leitura dos textos (IA)",
        "finalidade": "ler minutas e atos do RI e do Livro 3 e escrituras e "
                      "procurações das Notas, e apontar o que conferir",
        "inciso": "I",
        "enquadramento": "análise e revisão de ato",
        "dado": "o texto do ato e os dados do dossiê (nas procurações, a "
                "qualificação das partes)",
        "mascara": "no Claude, só com a máscara da revisão ligada — o padrão "
                   "é sem máscara (decisão do oficial, 06/10/2026, tomada com o "
                   "Claude como provedor); quando a leitura cai noutro provedor "
                   "(o reserva, sem chave do Claude), vai SEMPRE com máscara, "
                   "salvo a configuração ia_reserva_sem_mascara = '1', que nasce "
                   "desligada (LX13)",
        "mascarado": None,
        "revisao_humana": "quem qualifica confere cada apontamento e clica "
                          "«conferi» — só então ele sai da lista e da tarefa",
        "nao_faz": "não decide, não lavra, não corrige o ato",
        "teto": ("gestor_leitura", "TETO_POR_DIA", "textos por dia"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        "codigo": "gestor_expedientes",
        "nome": "Triagem dos expedientes",
        "modulo": "gestor_expedientes",
        "onde": "rotina diária do gestor e a rodada do malote (--triar)",
        "finalidade": "classificar ofícios e expedientes recebidos (ciência ou "
                      "providência, prazo, setor) e rascunhar a resposta",
        "inciso": "II",
        "enquadramento": "triagem de documentos",
        "dado": "os dados do expediente e o texto dos PDFs anexos (até 8 "
                "páginas)",
        "mascara": "sim: nomes e números viram marcas antes de subir "
                   "(gestor_expedientes.mascarar) e voltam só na resposta",
        "mascarado": True,
        "revisao_humana": "vira tarefa do responsável do setor, com o rascunho "
                          "marcado «revisar antes de mandar»; o que a IA lê como "
                          "ciência vai ao despacho do oficial E vira item «só "
                          "ciência — confira» na fila dele (LX13)",
        "nao_faz": "não responde ao juízo, não arquiva, não muda a etapa do "
                   "expediente",
        "teto": ("gestor_expedientes", "TETO_POR_DIA", "expedientes por dia"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        "codigo": "malote_fraudes",
        "nome": "Avisos de fraude no malote",
        "modulo": "malote_fraudes",
        "onde": "rodada do malote (malote_agente --confirmar)",
        "finalidade": "reconhecer aviso de fraude no malote e tirar dele as "
                      "pessoas citadas",
        "inciso": "II",
        "enquadramento": "triagem de documentos",
        "dado": "o texto dos PDFs do malote, o assunto e o remetente",
        "mascara": "parcial: CPF, CNPJ, telefone, e-mail e IP viram marcas; os "
                   "nomes vão em claro (decisão de 13/10/2026), porque são o "
                   "que se procura",
        "mascarado": True,
        "revisao_humana": "a pessoa achada entra ATIVA em Fraudes, marcada «entrado "
                          "pela IA» na observação, e é revisada DEPOIS: o despacho "
                          "diário do oficial lista as entradas pela IA desde a "
                          "rodada anterior, e na tela de fraudes desativar exige "
                          "motivo — revisão posterior, e não prévia. CPF só entra "
                          "se os dígitos estão no texto do PDF, e ENVOLVIDO só com "
                          "o trecho do texto que o diga (LX13)",
        "nao_faz": "não cadastra o expediente, não apaga o aviso, não bloqueia "
                   "ato",
        "teto": ("malote_fraudes", "TETO_POR_RODADA", "avisos por rodada"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        "codigo": "ri_onus_ia",
        "nome": "Sugestão de ônus para a certidão (RI)",
        "modulo": "ri_onus_ia",
        "onde": "botão na matrícula, antes de emitir a certidão",
        "finalidade": "ler a matrícula e sugerir se a certidão sai positiva ou "
                      "negativa de ônus, e quem é o proprietário atual",
        "inciso": "I",
        "enquadramento": "análise de ato",
        "dado": "o texto da matrícula e dos atos",
        "mascara": "só com a máscara da revisão ligada; o padrão da casa é sem "
                   "máscara",
        "mascarado": None,
        "revisao_humana": "quem emite decide; contrariar a sugestão ou o "
                          "proprietário exige justificativa escrita",
        "nao_faz": "não emite, não numera, não sela e não cobra",
        "teto": ("ia_catalogo", "CHAMADAS_POR_DIA", "chamadas ao provedor por dia",
                 "ri_onus_ia"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        "codigo": "rc_leitura",
        "nome": "Leitura de documentos do Registro Civil",
        "modulo": "rc_leitura_web",
        "onde": "tela do assento e da habilitação (RCPN)",
        "finalidade": "ler DNV, declaração de óbito, documentos de identidade e "
                      "certidões anexados e preencher o rascunho do assento",
        "inciso": "II e III",
        "enquadramento": "triagem e indexação de documentos",
        "dado": "as imagens das páginas anexadas, inteiras, até o teto de "
                "páginas por leitura (rc_leitura_documentos.MAXIMO_DE_PAGINAS); "
                "acima dele a leitura é recusada antes de subir",
        "mascara": "não: documento digitalizado não se mascara; o que subiu fica "
                   "anotado na própria leitura",
        "mascarado": False,
        "revisao_humana": "a leitura vira rascunho na tela do assento, com o "
                          "aviso de conferir cada campo com os originais antes "
                          "de lavrar",
        "nao_faz": "não lavra, não numera, não sela e não cobra",
        "teto": ("ia_catalogo", "CHAMADAS_POR_DIA", "chamadas ao provedor por dia",
                 "rc_leitura"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        # 26/10/2026, o oficial: «autorizo ia sem mascara. trabalharemos com o
        # prazo de retencao de 30 dias da api».
        "codigo": "nt_leitura",
        "nome": "Leitura de documentos do balcão das Notas",
        "modulo": "nt_leitura_web",
        "onde": "botão «Ler documento por IA» no cartão de autógrafo, no "
                "reconhecimento de firma e na comunicação de venda de veículo",
        "finalidade": "ler RG, CIN, CNH, CRLV, CRV e ATPV anexados e preencher, "
                      "como rascunho, os campos do cartão de autógrafo e os dados "
                      "do veículo e da venda",
        "inciso": "II e III",
        "enquadramento": "triagem e indexação de documentos",
        "dado": "as imagens das páginas anexadas, inteiras, até o teto de "
                "páginas por leitura (leitura_ia.MAXIMO_DE_PAGINAS); acima dele "
                "a leitura é recusada antes de subir",
        "mascara": "não, por decisão do oficial em 26/10/2026; retenção padrão "
                   "da API, de 30 dias, gravada em cada leitura (nt_leituras)",
        "mascarado": False,
        "revisao_humana": "a tela volta preenchida como rascunho, com as dúvidas "
                          "marcadas, e só grava com a caixa «conferi com o "
                          "documento original» marcada",
        "nao_faz": "não abre cartão, não reconhece firma, não comunica, não "
                   "sela e não cobra",
        "teto": ("ia_catalogo", "CHAMADAS_POR_DIA", "chamadas ao provedor por dia",
                 "nt_leitura"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        # 23/10/2026, o oficial: «um agente para preparar as minutas dos atos do
        # RI e do Notas (...) em opus high».
        "codigo": "minuta_ia",
        "nome": "Agente de minutas (RI e Notas)",
        "modulo": "minuta_ia",
        "onde": "quadro «Agente de minutas» na ficha da matrícula (RI) e na tela "
                "do ato em lavratura (escritura, procuração e ata notarial)",
        "finalidade": "ler os documentos escolhidos (prenotação, protocolo geral, "
                      "anexos do ato) e redigir a minuta do ato, com as partes e a "
                      "lista do que não se pôde afirmar; revisar a minuta pelas "
                      "instruções da serventia",
        "inciso": "I",
        "enquadramento": "redação",
        "dado": "os documentos marcados, inteiros (PDF e imagem), a ficha da "
                "matrícula ou o ato com as partes cadastradas, dois atos da casa "
                "como exemplo de redação e as instruções digitadas",
        "mascara": "não: documento digitalizado não se mascara (decisão do oficial "
                   "de 12/10/2026, a mesma da leitura do RCPN)",
        "mascarado": False,
        "revisao_humana": "a minuta pousa como minuta A REVISAR (RI) ou como teor do "
                          "ato em lavratura (Notas), com [COMPLETAR] no que falta; "
                          "quem confere com os originais e lavra é a pessoa",
        "nao_faz": "não lavra, não numera, não sela, não cobra e não lança no livro",
        "teto": ("ia_catalogo", "CHAMADAS_POR_DIA", "chamadas ao provedor por dia",
                 "minuta_ia"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        # 26/10/2026, o oficial: a IA cruza o título, a guia do ITBI e a
        # matrícula e RASCUNHA a nota devolutiva, para o oficial revisar.
        "codigo": "ri_qualificacao_ia",
        "nome": "Qualificação assistida do RI (rascunho da nota devolutiva)",
        "modulo": "ri_qualificacao_ia",
        "onde": "quadro «Qualificação assistida» na tela da nota devolutiva da "
                "prenotação (Registro de Imóveis)",
        "finalidade": "cruzar o título apresentado, a guia ou certidão de ITBI e a "
                      "matrícula e rascunhar as exigências, cada uma com fundamento "
                      "e com o trecho do documento de onde saiu",
        "inciso": "I",
        "enquadramento": "análise — apoio à qualificação, que continua sendo do "
                         "oficial; enquadramento a conferir",
        "dado": "os documentos marcados da prenotação e do protocolo geral ligado, "
                "inteiros (PDF e imagem), a ficha da matrícula com os atos e os "
                "proprietários, a lista de conferência da espécie e as instruções",
        "mascara": "não: documento digitalizado não se mascara (decisão do oficial "
                   "de 12/10/2026, a mesma do agente de minutas)",
        "mascarado": False,
        "revisao_humana": "o resultado nasce como rascunho; a pessoa marca e edita as "
                          "exigências, leva ao formulário da nota e emite pela rota "
                          "de sempre; cada trecho citado é conferido letra por letra "
                          "contra o texto do documento",
        "nao_faz": "não decide a qualificação, não emite a nota devolutiva, não "
                   "devolve o título e não muda a situação da prenotação",
        "teto": ("ia_catalogo", "CHAMADAS_POR_DIA", "chamadas ao provedor por dia",
                 "ri_qualificacao_ia"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        "codigo": "agente",
        "nome": "Agente do sistema",
        "modulo": "agente",
        "onde": "Administrativo → Agente do sistema (só ADMIN)",
        "finalidade": "diagnosticar problemas do sistema lendo o banco, o código "
                      "e a documentação e, se o oficial ligar a escrita, fazer "
                      "correções reversíveis",
        "inciso": "I",
        "enquadramento": "análise — manutenção do sistema, e não ato; "
                         "enquadramento a conferir",
        "dado": "o pedido do oficial e o que as ferramentas leram (banco, código, "
                "documentação)",
        "mascara": "sim: barreira de privacidade antes de subir "
                   "(ajuda_privacidade); o que ela não sabe mascarar é recusado",
        "mascarado": True,
        "revisao_humana": "a escrita nasce desligada; cada mudança fica guardada "
                          "e se desfaz com um clique",
        "nao_faz": "não toca em ato, não lavra, não sela, não decide o que é "
                   "grave",
        "teto": ("agente_schema", "TETO_MAXIMO_DE_SESSOES",
                 "sessões por dia, no máximo (a configuração pode ser menor)"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        "codigo": "ajuda",
        "nome": "Ajuda do sistema",
        "modulo": "ajuda",
        "onde": "Ajuda e a janela de ajuda (todos); leitura de problema "
                "relatado (ADMIN e MANAGER)",
        "finalidade": "responder dúvidas da equipe sobre o uso do sistema e "
                      "diagnosticar problemas relatados",
        "inciso": "IV",
        "enquadramento": "atendimento à equipe, com escalonamento para pessoa; "
                         "enquadramento a conferir",
        "dado": "a pergunta e o contexto da tela (até 40.000 caracteres), "
                "mascarados",
        "mascara": "sim, obrigatória (preparar_saida): pedido com resíduo de "
                   "dado de pessoa não sai",
        "mascarado": True,
        "revisao_humana": "a resposta é orientação; a pessoa avalia e decide, e "
                          "nada se grava em ato",
        "nao_faz": "não lavra, não numera, não sela, não cobra, não cancela",
        "teto": ("ajuda", "TETO_DE_CONSULTAS_POR_DIA", "consultas por dia"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        "codigo": "robo_rascunho",
        "nome": "Robôs de rascunho",
        "modulo": "robo_web",
        "onde": "Atendimento → Robôs (testar o robô)",
        "finalidade": "rascunhar texto a partir do prompt e dos exemplos do robô",
        "inciso": "I",
        "enquadramento": "redação",
        "dado": "o prompt do robô, os exemplos e o pedido digitado",
        "mascara": "sim (LX13): o pedido e os exemplos passam pela barreira da "
                   "ajuda antes de subir, e o registro do teste guarda só a "
                   "forma mascarada; pedido com resíduo não sobe",
        "mascarado": True,
        "revisao_humana": "o rascunho só aparece na tela de quem testou",
        "nao_faz": "não grava no livro, não envia WhatsApp",
        "teto": ("ia_catalogo", "CHAMADAS_POR_DIA", "chamadas ao provedor por dia",
                 "robo_rascunho"),
        # A EXCEÇÃO, DITA EM VOZ ALTA: os robôs guardam a chave em
        # `robo_config`, dentro do banco — que vai no backup.
        "chave": "robo_config, DENTRO do banco (exceção à regra da casa)",
    },
)

# O ATENDENTE DO WHATSAPP (26/10/2026) — entradas acrescentadas fora da tupla
# para o diff ficar só nelas. Decisão do oficial de 26/10/2026: a IA responde
# sozinha em quatro casos e passa o resto a uma pessoa (ver `wa_atendente`).
CATALOGO = CATALOGO + (
    {
        "codigo": "wa_atendente",
        "nome": "Atendente com IA do WhatsApp",
        "modulo": "wa_atendente",
        "onde": "fila do WhatsApp, com o interruptor «atendente ligado» (só o "
                "ADMIN liga, e nasce desligado)",
        "finalidade": "responder sozinho ao cliente dúvidas gerais pelo texto-base "
                      "aprovado pelo oficial e escolher o item da lista de valores "
                      "(o valor é calculado pela tabela da casa, como ESTIMATIVA); "
                      "o andamento do protocolo é respondido pelo sistema, sem IA, "
                      "depois da identificação por número e código",
        "inciso": "IV",
        "enquadramento": "atendimento, com escalonamento para pessoa",
        "dado": "a mensagem do cliente, mascarada; o texto-base e a lista de "
                "valores da casa",
        "mascara": "sim (preparar_saida): mensagem em que a máscara acha dado "
                   "pessoal (fora o nome) não sobe — passa para uma pessoa",
        "mascarado": True,
        "revisao_humana": "protesto, registro civil, dado pessoal, reclamação, "
                          "pedido de pessoa e tudo o que a IA não sabe passam a uma "
                          "pessoa, com a conversa marcada para o setor; a resposta "
                          "que escreve número fora do texto-base não sai; cada "
                          "resposta fica registrada (wa_ia_registro)",
        "nao_faz": "não lavra, não numera, não sela, não cobra, não informa valor "
                   "que não venha do cálculo da casa",
        "teto": ("ia_catalogo", "CHAMADAS_POR_DIA", "chamadas ao provedor por dia",
                 "wa_atendente"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
    {
        "codigo": "wa_audio",
        "nome": "Transcrição do áudio do WhatsApp",
        "modulo": "wa_atendente",
        "onde": "fila do WhatsApp, com o interruptor «transcrever áudio» (só o "
                "ADMIN liga, e nasce desligado)",
        "finalidade": "transcrever o áudio que o cliente manda, para o atendente "
                      "e para quem atende",
        "inciso": "II",
        "enquadramento": "triagem de documentos (transcrição)",
        "dado": "o áudio inteiro, como chegou da Meta",
        "mascara": "não: áudio não se mascara; a transcrição passa pela máscara "
                   "antes de ir ao modelo que responde",
        "mascarado": False,
        "revisao_humana": "a transcrição aparece na conversa ao lado da mensagem, "
                          "para quem atende conferir; ela não vira ato",
        "nao_faz": "não responde sozinha, não lavra, não cobra",
        "teto": ("ia_catalogo", "CHAMADAS_POR_DIA", "chamadas ao provedor por dia",
                 "wa_audio"),
        "chave": CHAVE_FORA_DO_BANCO,
    },
)

POR_CODIGO = {e["codigo"]: e for e in CATALOGO}


def entrada(codigo: Any) -> dict | None:
    """A entrada do catálogo daquela finalidade, ou None. SÓ LÊ."""
    return POR_CODIGO.get(str(codigo or ""))


def nome_da_finalidade(codigo: Any) -> str:
    """O nome para a tela; finalidade fora do catálogo aparece como veio."""
    achada = entrada(codigo)
    if achada:
        return achada["nome"]
    return f"fora do catálogo: {codigo}" if codigo else "finalidade não informada"


def teto_de(item: dict) -> str:
    """O teto daquela entrada, lido da constante do módulo. SÓ LÊ.

    Ler de lá, e não copiar o número, é o que impede o relatório de dizer um
    teto que o código já não tem. O quarto elemento, quando há, é a chave
    dentro da constante (`CHAMADAS_POR_DIA`, uma tabela só para os tetos que
    nasceram no LX13).
    """
    teto = item.get("teto")
    if not teto:
        return "sem teto diário"
    modulo, constante, unidade, *chave = teto
    try:
        valor = getattr(importlib.import_module(modulo), constante)
        if chave:
            valor = valor[chave[0]]
    except (ImportError, AttributeError, KeyError):
        return f"{constante} não encontrado em {modulo}"
    return f"{valor} {unidade}"


def teto_diario(codigo: Any) -> int | None:
    """Quantas chamadas ao provedor aquela finalidade faz por dia, no máximo,
    pela tabela `CHAMADAS_POR_DIA`; None quando o teto dela é de outra forma
    (por rodada, por ato, por sessão) e mora no próprio módulo. SÓ LÊ."""
    valor = CHAMADAS_POR_DIA.get(str(codigo or ""))
    return int(valor) if valor is not None else None
