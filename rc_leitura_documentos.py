"""A LEITURA DOS DOCUMENTOS DO REGISTRO — o balcão anexa, a IA lê, o escrevente confere.

«qual seria o custo para implementarmos uma importacao para registros de
 nascimento, casamento (habilitacao) e obito direto dentro do sistema, lendo e
 transcrevendo e preenchendo todos os campos e documentos anexados?» e, depois
 das contas, «gostei da estrategia para gastar menos. vamos construir» — o
 oficial, 12/10/2026. E: «documentos vao para claude sem mascara».

O CAMINHO, EM QUATRO PASSOS, E SÓ O ÚLTIMO TOCA NO LIVRO — e quem o dá é gente:

  1. TRIAR — o modelo barato olha TODAS as páginas de uma vez e diz o que cada
     uma é (DNV, DO, documento de identidade, certidão, residência, outra).
  2. LER — cada página que importa vai ao modelo certo para ela: o FORTE para o
     que é escrito à mão (DNV, DO, certidão antiga), o MÉDIO para o impresso
     (RG, CNH, CPF, declaração). A estratégia foi medida em 12/10/2026 numa DNV
     real desta casa: o Sonnet trocou «Olivia» por «Alicia» e o peso de 2565 g
     por 2156 g; o Opus acertou os dois.
  3. JUNTAR — sem rede: os documentos viram UM registro no padrão da casa
     (`importar_padrao`), com as pessoas nas gavetas certas, e a CONFERÊNCIA
     cruza o que um documento diz com o que o outro diz.
  4. RASCUNHO — o registro entra na fila de pré-cadastros
     (`importar_padrao.para_rascunhos`) e abre a tela de lavrar, preenchida.

ESTE MÓDULO NÃO LAVRA, NÃO NUMERA, NÃO SELA E NÃO COBRA — a régua do CNIB, do
usucapião e das fraudes. A máquina adianta a digitação; quem lê o documento
original e assina é o escrevente. Há teste que varre os nomes públicos.

A IA ERRA, E A TELA DIZ ONDE. O que o modelo leu com dúvida volta marcado
(« (?)» no fim do valor), e a conferência aponta o que não fecha entre os
documentos — o nome da mãe na DNV contra o RG dela, a idade contra a data de
nascimento, o dígito do CPF e do Cartão SUS. Não se corrige sozinho: aponta.

O QUE SAI DA CASA, E POR QUÊ (LGPD) — `BASE_LEGAL` e `O_QUE_SAI`:
  - a página inteira, sem máscara, por decisão do oficial em 12/10/2026;
  - toda página anexada é lida — «tudo que é preenchido precisa ser lido», o
    oficial em 12/10/2026 — e a triagem só decide QUAL modelo a lê;
  - cada envio fica registrado em `rc_leituras.envios_json`: que arquivo, que
    página, a que modelo, quanto custou — a pergunta «o que foi mandado, e
    para quem?» tem resposta escrita.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import tetos_de_entrada as TETO
from bd_nativo import banco

PROVEDOR = "claude"

#: O TETO DE PÁGINAS POR LEITURA (M4 do LS02 = M12 do LS03; LX13, 19/10/2026).
#: Sem ele, um PDF de mil folhas eram ~125 triagens e mil leituras pagas, pedidas
#: por qualquer login. Quarenta é a régua que o oficial deu aos anexos da revisão
#: («aviso quando passar de 40 páginas», 07/10/2026), e sobra: o registro mais
#: cheio desta tela, a habilitação, junta requerimento, certidões e identidades
#: dos nubentes e das testemunhas em menos de vinte. Aqui não se corta: «tudo que
#: é preenchido precisa ser lido» (12/10/2026), e por isso, acima do teto, a
#: leitura inteira é RECUSADA antes de qualquer página subir.
MAXIMO_DE_PAGINAS = 40

#: OS TRÊS MODELOS, E O QUE CADA UM FAZ. São o PISO; a configuração ajusta
#: sem versão nova (`settings`), porque nome de modelo envelhece.
MODELOS_PADRAO: dict[str, str] = {
    "triagem": "claude-haiku-4-5-20251001",
    "manuscrito": "claude-opus-5-5",
    "impresso": "claude-sonnet-5",
}
CHAVE_DO_MODELO: dict[str, str] = {
    "triagem": "rcpn_leitura_modelo_triagem",
    "manuscrito": "rcpn_leitura_modelo_manuscrito",
    "impresso": "rcpn_leitura_modelo_impresso",
}

#: Preço em dólares por MILHÃO de tokens (entrada, saída) — tabela da Anthropic
#: conferida em 11/10/2026. Serve para a tela dizer quanto custou; quem cobra é
#: a Anthropic, e o número aqui é estimativa.
PRECO_POR_MILHAO: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}

#: O CASAMENTO ENTRA PELA HABILITAÇÃO (12/10/2026, «falta casamento»): o
#: casamento desta casa é processo, e a porta dele é a habilitação — a leitura
#: preenche «Abrir habilitação», e o assento sai dela depois, como sempre.
#:
#: E TAMBÉM PELA TELA DO ASSENTO (12/10/2026, o oficial: «segue sem importação
#: por api no casamento»). A leitura é a mesma da habilitação — requerimento,
#: certidões e documentos dos nubentes —, e `juntar_casamento` a devolve com os
#: papéis do assento (nubentes, as quatro filiações e as testemunhas).
ESPECIES_LIDAS: tuple[str, ...] = ("NASCIMENTO", "OBITO", "CASAMENTO", "HABILITACAO")
ROTULO_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "Nascimento", "OBITO": "Óbito", "CASAMENTO": "Casamento",
    "HABILITACAO": "Casamento (habilitação)",
}
#: A tela que o rascunho de cada espécie abre.
TELA_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "rcpn_assento_novo", "OBITO": "rcpn_assento_novo",
    "CASAMENTO": "rcpn_assento_novo",
    "HABILITACAO": "rcpn_habilitacao_nova",
}

BASE_LEGAL = (
    "Tratamento para o exercício da atribuição do registro civil (Lei 13.709/2018, "
    "art. 7º, II e III, e art. 23, § 4º; dados sensíveis pelo art. 11, II, «a» e «b»), "
    "com a Anthropic como operadora. Os documentos vão sem máscara por decisão do "
    "oficial em 12/10/2026.")
O_QUE_SAI = (
    "Vão à Anthropic as imagens das páginas anexadas: todas na triagem, em tamanho "
    "reduzido, e todas na leitura, inteiras. Nada mais do banco sai junto.")

#: O PEDIDO DE «ZERO DATA RETENTION» À ANTHROPIC — ordem do oficial em 12/10/2026:
#: «quero o pedido de zero data retention, registrado no código». É o acordo pelo
#: qual a Anthropic não guarda o que recebe pela API depois de responder. Ele se
#: pede à Anthropic (não é botão da API) e quem o pede e assina é o oficial; o
#: texto do pedido está em DOCUMENTACAO/LGPD_LEITURA_DE_DOCUMENTOS.md. A
#: SITUAÇÃO aqui é o que a tela mostra — e muda quando a resposta chegar, com a
#: data e o número do acordo. Enquanto não houver acordo, a tela diz isso: dizer
#: «sem retenção» antes da hora seria o carimbo que mente.
#:
#: NEGADO EM 12/10/2026 — a Anthropic respondeu ao oficial que a casa não tem
#: volume suficiente para o acordo. Vale a RETENÇÃO PADRÃO DA API, conferida no
#: Privacy Center no mesmo dia: entradas e saídas apagadas em até 30 dias, com
#: as exceções que a própria Anthropic declara (escritas abaixo, e não omitidas:
#: dizer «só 30 dias» sem elas seria afirmar mais do que a regra diz).
ZERO_DATA_RETENTION: dict[str, str] = {
    "situacao": "NEGADO",           # A PEDIR | PEDIDO | ACORDADO | NEGADO
    "pedido_em": "12/10/2026",
    "acordo": "",
    "retencao_padrao_dias": "30",
    "fonte": "https://privacy.claude.com/en/articles/7996866",
    "observacao": ("Vale a retenção padrão da API: as imagens e as "
                   "respostas são apagadas dos servidores da Anthropic em até 30 "
                   "dias — salvo se o conteúdo for marcado por violação da política "
                   "de uso (até 2 anos) ou se a lei obrigar a guardar. Nada fica "
                   "guardado indefinidamente, e os documentos não são usados para "
                   "treinar modelos (termos comerciais da API)."),
}

#: OS MOLDES — o que se lê de cada tipo de documento. `manuscrito` decide o
#: modelo; `campos` é a instrução do que tirar, na ordem em que o documento traz.
TIPOS: dict[str, dict[str, Any]] = {
    "DNV": {
        "nome": "Declaração de Nascido Vivo (DNV)",
        "manuscrito": True,
        "campos": (
            "numero_dnv, cartao_sus_rn, nome_rn, data_nascimento, hora_nascimento, "
            "sexo (Masculino/Feminino/Ignorado), raca_cor_rn, peso_gramas, "
            "tipo_gravidez (Única/Dupla/Tripla ou mais), local_ocorrencia (Hospital/"
            "Outros estabelecimentos de saúde/Domicílio/Outros/Aldeia indígena/Ignorado), "
            "estabelecimento, endereco_ocorrencia, numero_ocorrencia, bairro_ocorrencia, "
            "municipio_ocorrencia, uf_ocorrencia, nome_mae, cartao_sus_mae, "
            "escolaridade_mae, ocupacao_mae, nascimento_mae, idade_mae, "
            "naturalidade_mae (município e UF), situacao_conjugal_mae, raca_cor_mae, "
            "logradouro_residencia, numero_residencia, bairro_residencia, "
            "municipio_residencia, uf_residencia, nome_responsavel_legal, "
            "data_preenchimento, responsavel_preenchimento"),
    },
    "DO": {
        "nome": "Declaração de Óbito (DO)",
        "manuscrito": True,
        "campos": (
            "numero_do, nome_falecido, nome_pai, nome_mae, data_obito, hora_obito, "
            "sexo (Masculino/Feminino/Ignorado), raca_cor, data_nascimento, idade, "
            "estado_civil, escolaridade, ocupacao, naturalidade (município e UF), "
            "cartao_sus, logradouro_residencia, numero_residencia, bairro_residencia, "
            "municipio_residencia, uf_residencia, local_ocorrencia (Hospital/Outros "
            "estabelecimentos de saúde/Domicílio/Via pública/Outros/Aldeia indígena/"
            "Ignorado), estabelecimento, endereco_ocorrencia, municipio_ocorrencia, "
            "uf_ocorrencia, causa_a, causa_b, causa_c, causa_d, causa_parte_ii, "
            "tipo_morte (Natural/Acidente/Suicídio/Homicídio/Ignorado), medico_nome, "
            "medico_crm, data_atestado, local_sepultamento"),
    },
    "IDENTIDADE": {
        "nome": "Documento de identidade (RG, CIN, CNH, CPF)",
        # LIDA PELO MODELO FORTE — ordem do oficial em 12/10/2026, depois do
        # ensaio do termo 19581: o Sonnet leu «Gilton Fedro» onde o RG diz
        # «Gilton Pedro». «É bem importante»: dela saem CPF, filiação e avós.
        "manuscrito": True,
        "campos": (
            "pessoas: uma lista com UM item por documento na página (a página pode "
            "trazer dois documentos), cada um com tipo_documento (RG/CIN/CNH/CPF), "
            "nome, numero_documento, orgao_emissor, cpf, data_nascimento, "
            "naturalidade (município e UF), filiacao_pai, filiacao_mae, "
            "data_expedicao, documento_origem, titulo_eleitor, numero_cnh, "
            "nacionalidade, sexo"),
    },
    "CERTIDAO": {
        "nome": "Certidão de registro civil",
        "manuscrito": True,
        "campos": (
            "especie (nascimento/casamento/óbito), nomes (lista; na de nascimento o "
            "registrado primeiro), matricula, data_registro, livro, folha, termo, "
            "filiacao (lista), pai, mae, sexo, data_nascimento, naturalidade, "
            "cartorio, averbacoes (texto)"),
    },
    # O REQUERIMENTO DA HABILITAÇÃO é o único papel que diz profissão, nome
    # que se passa a usar e regime de bens — as certidões não dizem. Costuma
    # ser formulário impresso preenchido à mão, e por isso vai ao modelo forte.
    "HABILITACAO": {
        "nome": "Requerimento ou declaração de habilitação de casamento",
        "manuscrito": True,
        "campos": (
            "nubentes: lista com UM item por nubente, na ordem do documento, cada "
            "um com nome, nome_apos_casamento, cpf, data_nascimento, sexo, "
            "estado_civil, profissao, nacionalidade, naturalidade (município e "
            "UF), endereco, pai, mae; regime_bens; tipo_casamento (civil/religioso "
            "com efeito civil/conversão de união estável); data; testemunhas: "
            "lista com nome, cpf, endereco"),
    },
    # O REQUERIMENTO DO REGISTRO TARDIO — 21/10/2026. É o formulário que a
    # tela de conferência imprime (`_requerimento_tardio.html`), assinado e
    # digitalizado; ou outro requerimento do mesmo teor. Costuma voltar
    # preenchido à mão, e por isso vai ao modelo forte.
    "TARDIO": {
        "nome": "Requerimento de registro de nascimento tardio",
        "manuscrito": True,
        "campos": (
            "numero_requerimento; requerente: {nome, qualidade (o próprio "
            "registrando/mãe/pai/representante legal), cpf, rg, orgao_emissor, "
            "data_nascimento, sexo, nacionalidade, estado_civil, profissao, "
            "naturalidade (município e UF), endereco, bairro, municipio, uf}; "
            "registrando: {nome, sexo, data_nascimento, hora_nascimento, "
            "local_nascimento, endereco_nascimento, municipio_nascimento, "
            "uf_nascimento, gemeo (sim/não), raca_cor, numero_dnv}; mae e pai: "
            "cada um {nome, cpf, data_nascimento, naturalidade (município e UF), "
            "profissao, endereco}; avos_maternos e avos_paternos: listas de "
            "nomes; testemunhas: lista com nome, cpf, rg, data_nascimento, "
            "nacionalidade, estado_civil, profissao, endereco, municipio, uf; "
            "documentos_apresentados (lista); data_do_requerimento"),
    },
    "RESIDENCIA": {
        "nome": "Comprovante ou declaração de residência",
        "manuscrito": False,
        "campos": (
            "declarante, cpf_declarante, moradores (lista de nomes), cpf_morador, "
            "logradouro, numero, bairro, municipio, uf, cep, data"),
    },
    # «TUDO QUE É PREENCHIDO PRECISA SER LIDO» — o oficial, 12/10/2026. A página
    # que a triagem não reconhece também é transcrita, pelo modelo médio, campo
    # a campo; ela aparece na conferência para o escrevente decidir se importa.
    "OUTRO": {
        "nome": "Outro documento",
        "manuscrito": False,
        "campos": ("tipo_do_documento (o que o documento é, em poucas palavras), "
                   "e cada campo preenchido, com o rótulo do documento como chave"),
    },
}

INSTRUCAO_TRIAGEM = (
    "Você classifica páginas de documentos entregues no balcão de um cartório de "
    "registro civil brasileiro. As páginas vêm numeradas na ordem. Para cada uma, "
    "diga o tipo, escolhendo exatamente um destes códigos: DNV (Declaração de "
    "Nascido Vivo), DO (Declaração de Óbito), IDENTIDADE (RG, CIN, CNH ou cartão "
    "do CPF — mesmo dois numa página), CERTIDAO (certidão de nascimento, casamento "
    "ou óbito), TARDIO (requerimento de registro de nascimento tardio, fora "
    "do prazo — com o registrando, a filiação e as testemunhas), "
    "HABILITACAO (requerimento, memorial ou declaração de habilitação "
    "para casamento, inclusive a declaração das testemunhas), RESIDENCIA "
    "(comprovante ou declaração de residência), OUTRO. "
    "A DECLARAÇÃO DE NASCIDO VIVO É SEMPRE DNV, NUNCA IDENTIDADE — inclusive a "
    "«2ª via – Cartório», o formulário do Ministério da Saúde / SINASC, e a página "
    "que traz o número no formato NN-NNNNNNNN-N, os dados do recém-nascido e os da "
    "parturiente (a mãe), mesmo quando vem no mesmo PDF que um RG ou CIN. "
    "Responda SÓ com JSON: {\"paginas\": [{\"n\": 1, \"tipo\": \"DNV\"}, ...]}.")

INSTRUCAO_LEITURA = (
    "Você transcreve documentos para o registro civil de um cartório brasileiro. "
    "Leia o documento da imagem ({nome}) e devolva SÓ um JSON, sem texto em volta, "
    "com estas chaves: {campos}. Datas em DD/MM/AAAA. Campo em branco ou ausente = "
    "null. Nas caixas de marcar, devolva o texto da opção marcada. Se a letra for "
    "duvidosa, transcreva o mais provável e acrescente ' (?)' no fim do valor. "
    "TUDO o que estiver preenchido no documento precisa voltar: o que não couber "
    "nas chaves pedidas vai em \"outros_campos\", um objeto com o rótulo do "
    "documento como chave. Não invente: o que não está escrito é null.")


class LeituraError(ValueError):
    """Erro de regra, em português de balcão."""


# ----------------------------------------------------------------- o esquema

SCHEMA = """
CREATE TABLE IF NOT EXISTS rc_leituras (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    especie TEXT NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'LIDA',   -- LIDA | FALHOU | NO_RASCUNHO
    arquivos_json TEXT NOT NULL,             -- [{attachment_id, nome, sha256}]
    paginas_json TEXT,                       -- triagem: [{arquivo, n, tipo}]
    documentos_json TEXT,                    -- o que cada página disse
    registro_json TEXT,                      -- o registro no padrão da casa
    conferencia_json TEXT,                   -- o que não fecha, e onde
    envios_json TEXT,                        -- o que saiu, a que modelo, quanto
    custo_estimado double precision,
    erro TEXT,
    rascunho_id bigint,
    criada_em TEXT NOT NULL,
    criada_por TEXT,
    rascunho_em TEXT,
    rascunho_por TEXT
);
"""


def init_schema(con) -> None:
    bd = banco(con)
    for comando in SCHEMA.split(";"):
        if comando.strip():
            bd.escrever(comando)


def _ler_config(con, chave: str) -> str:
    try:
        valor = banco(con).valor("SELECT value FROM settings WHERE key = %s", (chave,))
    except sqlite3.OperationalError:
        return ""
    return str(valor).strip() if valor else ""


def modelos(con) -> dict[str, str]:
    """Os três modelos em uso: o da configuração, ou o piso. SÓ LÊ."""
    return {papel: _ler_config(con, CHAVE_DO_MODELO[papel]) or padrao
            for papel, padrao in MODELOS_PADRAO.items()}


def custo(modelo: str, entrada: int, saida: int) -> float:
    """Dólares estimados de uma chamada. Modelo fora da tabela custa zero NA
    TELA, e a tela diz que não sabe — nunca um número inventado."""
    preco = PRECO_POR_MILHAO.get(modelo)
    if not preco:
        return 0.0
    return (int(entrada or 0) * preco[0] + int(saida or 0) * preco[1]) / 1_000_000


# ------------------------------------------------------------- as páginas

def paginas_dos_arquivos(arquivos: list[dict]) -> list[dict]:
    """[{arquivo, nome, n, imagem()}] na ordem em que foram anexados. SÓ LÊ.

    A página do PDF que já tem texto digital também vai como IMAGEM: a DNV e a
    DO são formulários de caixinhas, e o texto extraído perde o que está
    marcado.

    O NÚMERO DE PÁGINAS TEM TETO, E A RECUSA VEM ANTES DE QUALQUER CHAMADA
    (LX12, LS02 M4, 19/10/2026). Cada página é uma chamada PAGA ao provedor —
    duas, contando a triagem —, e a rota é de qualquer login: um PDF de mil
    páginas eram mil chamadas pagas, sem ninguém ver o custo antes. O teto é
    `tetos_de_entrada.valor("ia_paginas")` (50, ajustável); a frase diz por
    quê, para quem a recebe separar só os documentos do ato."""
    import revisao_anexos as RA
    saida = []
    for a in arquivos:
        try:
            paginas = RA.paginas_do_arquivo(Path(a["caminho"]), a["nome"])
        except RA.AnexoIlegivel as erro:
            raise LeituraError(f"«{a['nome']}»: {erro}.") from erro
        for n, p in enumerate(paginas, start=1):
            if p.get("imagem") is None:
                continue
            saida.append({"arquivo": a["nome"], "attachment_id": a.get("attachment_id"),
                          "n": n, "imagem": p["imagem"]})
    if not saida:
        raise LeituraError("Nenhuma página com imagem nos arquivos anexados — "
                           "anexe o PDF digitalizado ou as fotos dos documentos.")
    teto = TETO.valor("ia_paginas")
    if len(saida) > teto:
        raise LeituraError(
            f"Os anexos somam {len(saida)} páginas, e a leitura vai até {teto} "
            f"por vez: cada página é uma chamada paga à IA (mais a triagem), e "
            f"nada foi enviado. Anexe só os documentos deste ato — a DNV, a DO, "
            f"os documentos de identidade — e não o processo inteiro.")
    return saida


def _json(texto: str) -> dict:
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


#: O simulado de IA do SANDBOX responde com esta marca e não lê nada. Sem a
#: recusa, a triagem voltava vazia e a tela dizia «não há uma DNV» — a culpa
#: caía no documento, que estava certo (12/10/2026, primeira leitura no SANDBOX).
MARCA_DO_SIMULADOR = "[SIMULADOR DO SANDBOX]"


def _pedir(conversar, pasta: Path, modelo: str, instrucao: str, texto: str,
           imagens: list[str], maximo: int = 4000) -> dict:
    r = conversar(pasta, provedor=PROVEDOR, sistema=instrucao,
                  conversa=[{"tipo": "user", "texto": texto,
                             "imagens": [{"mime": "image/jpeg", "base64": b}
                                         for b in imagens]}],
                  ferramentas=[], modelo=modelo, maximo_de_saida=maximo)
    if MARCA_DO_SIMULADOR in str((r or {}).get("texto") or ""):
        raise LeituraError(
            "Este é o sistema de teste: a IA daqui é um simulador e não lê "
            "documentos. O caminho até ela funcionou; a leitura de verdade "
            "acontece na produção, depois da atualização.")
    return r


#: A TRIAGEM VÊ MINIATURAS, EM LOTES — e isso foi medido no primeiro óbito
#: real (12/10/2026): o PDF com a DO, os documentos e a certidão passou de 2 MB
#: numa chamada só, e o transporte recusa conversa desse tamanho. Para dizer «é
#: uma DNV» basta a página pequena; quem precisa da página inteira é a leitura.
LADO_DA_MINIATURA_PX = 700
PAGINAS_POR_LOTE_DA_TRIAGEM = 8


def _miniatura(imagem_b64: str) -> str:
    import base64
    import io
    from PIL import Image
    with Image.open(io.BytesIO(base64.b64decode(imagem_b64))) as im:
        im = im.convert("L")
        fator = LADO_DA_MINIATURA_PX / max(im.size)
        if fator < 1:
            im = im.resize((int(im.size[0] * fator), int(im.size[1] * fator)))
        saida = io.BytesIO()
        im.save(saida, format="JPEG", quality=60)
    return base64.b64encode(saida.getvalue()).decode("ascii")


def triar(conversar, pasta: Path, modelo: str, paginas: list[dict]) -> tuple[list[str], list[dict]]:
    """O tipo de cada página, pelo modelo barato, em lotes. FALA COM A REDE.

    O que o modelo não souber dizer vira OUTRO — e OUTRO não é lido."""
    tipos: list[str] = []
    envios: list[dict] = []
    for inicio in range(0, len(paginas), PAGINAS_POR_LOTE_DA_TRIAGEM):
        lote = paginas[inicio:inicio + PAGINAS_POR_LOTE_DA_TRIAGEM]
        imagens = [_miniatura(p["imagem"]()) for p in lote]
        texto = "\n".join(f"Página {i}: arquivo {p['arquivo']}, folha {p['n']}"
                          for i, p in enumerate(lote, start=1))
        r = _pedir(conversar, pasta, modelo, INSTRUCAO_TRIAGEM, texto, imagens, 1500)
        por_n = {}
        for item in _json(r.get("texto") or "").get("paginas") or []:
            try:
                por_n[int(item.get("n"))] = str(item.get("tipo") or "").upper()
            except (TypeError, ValueError):
                continue
        tipos += [por_n.get(i) if por_n.get(i) in TIPOS else "OUTRO"
                  for i in range(1, len(lote) + 1)]
        envios.append({"etapa": "triagem", "modelo": r.get("modelo") or modelo,
                       "paginas": [f"{p['arquivo']} p{p['n']}" for p in lote],
                       "entrada": r.get("entrada"), "saida": r.get("saida")})
    return tipos, envios


def ler_pagina(conversar, pasta: Path, modelos_em_uso: dict, pagina: dict,
               tipo: str) -> tuple[dict, dict]:
    """O que UMA página diz, pelo molde do tipo dela. FALA COM A REDE."""
    molde = TIPOS[tipo]
    modelo = modelos_em_uso["manuscrito" if molde["manuscrito"] else "impresso"]
    instrucao = INSTRUCAO_LEITURA.format(nome=molde["nome"], campos=molde["campos"])
    r = _pedir(conversar, pasta, modelo, instrucao,
               f"Transcreva: {pagina['arquivo']}, folha {pagina['n']}.",
               [pagina["imagem"]()], 4000)
    dados = _json(r.get("texto") or "")
    envio = {"etapa": "leitura", "tipo": tipo, "modelo": r.get("modelo") or modelo,
             "paginas": [f"{pagina['arquivo']} p{pagina['n']}"],
             "entrada": r.get("entrada"), "saida": r.get("saida")}
    return dados, envio


def ler(conversar, pasta: Path, modelos_em_uso: dict, arquivos: list[dict],
        especie: str | None = None) -> dict:
    """Triar e ler tudo. FALA COM A REDE — e por isso NÃO RECEBE `con`: um
    minuto de rede segurando o banco poria a casa no `busy_timeout`.

    Devolve {paginas, documentos, envios}; quem grava é `guardar`.

    Acima de `MAXIMO_DE_PAGINAS` recusa ANTES da triagem: nada sobe."""
    paginas = paginas_dos_arquivos(arquivos)
    if len(paginas) > MAXIMO_DE_PAGINAS:
        raise LeituraError(
            f"Os anexos somam {len(paginas)} páginas, acima do teto de {MAXIMO_DE_PAGINAS} "
            "por leitura — nada foi enviado à IA. Anexe só os documentos do registro "
            "(DNV ou DO, identidades, comprovante de residência, certidões).")
    tipos, envios = triar(conversar, pasta, modelos_em_uso["triagem"], paginas)
    a_ler = list(zip(paginas, tipos))

    def uma(par):
        pagina, tipo = par
        return ler_pagina(conversar, pasta, modelos_em_uso, pagina, tipo)

    with ThreadPoolExecutor(max_workers=4) as ex:
        resultados = list(ex.map(uma, a_ler))
    documentos = []
    for (pagina, tipo), (dados, envio) in zip(a_ler, resultados):
        documentos.append({"arquivo": pagina["arquivo"], "n": pagina["n"],
                           "attachment_id": pagina.get("attachment_id"),
                           "tipo": tipo, "dados": dados})
        envios.append(envio)
    if str(especie or "").upper() == "NASCIMENTO":
        tipos = _rede_da_dnv(conversar, pasta, modelos_em_uso, paginas, tipos,
                             documentos, envios)
    return {"paginas": [{"arquivo": p["arquivo"], "n": p["n"],
                         "attachment_id": p.get("attachment_id"), "tipo": t}
                        for p, t in zip(paginas, tipos)],
            "documentos": documentos, "envios": envios}


# A REDE DE SEGURANÇA DA DNV — 21/10/2026, leituras 5, 6 e 7 da produção: um
# PDF com o RG da mãe e a DNV «2ª via – Cartório» (formulário MS/SINASC) teve
# AS DUAS páginas triadas como IDENTIDADE (miniatura de 700 px em cinza), e a
# própria transcrição da página 2 anotou «é uma Declaração de Nascido Vivo».
# Sem DNV, `juntar_nascimento` recusava. Aqui: no NASCIMENTO sem nenhuma página
# DNV, a página cuja transcrição traz os sinais da DNV é RELIDA pelo molde da
# DNV — e o que a triagem errou fica anotado no documento e vira aviso.
PADRAO_NUMERO_DNV = re.compile(r"(?<!\d)\d{2}-\d{8}-\d(?!\d)")


def sinais_de_dnv(dados: Any) -> list[str]:
    """Os sinais de DNV no que uma página já disse. SÓ CALCULA.

    Basta um sinal forte («Declaração de Nascido Vivo», SINASC ou o número
    NN-NNNNNNNN-N); os campos da parturiente só contam junto de um forte."""
    texto = _sem_acento(json.dumps(dados or {}, ensure_ascii=False)).lower()
    sinais = []
    if "nascido vivo" in texto:
        sinais.append("«Declaração de Nascido Vivo»")
    if "sinasc" in texto:
        sinais.append("SINASC")
    if PADRAO_NUMERO_DNV.search(texto):
        sinais.append("número no formato NN-NNNNNNNN-N")
    if "parturiente" in texto:
        sinais.append("campos da parturiente")
    fortes = [s for s in sinais if s != "campos da parturiente"]
    return sinais if fortes else []


def paginas_que_parecem_dnv(documentos: list[dict]) -> list[tuple[dict, list[str]]]:
    """As páginas (não DNV) cuja transcrição tem sinais de DNV, a com mais
    sinais primeiro. SÓ CALCULA."""
    achadas = [(d, sinais_de_dnv(d.get("dados"))) for d in documentos
               if d.get("tipo") != "DNV"]
    return sorted([(d, s) for d, s in achadas if s], key=lambda par: -len(par[1]))


def _rede_da_dnv(conversar, pasta: Path, modelos_em_uso: dict, paginas: list[dict],
                 tipos: list[str], documentos: list[dict], envios: list[dict]) -> list[str]:
    """Relê como DNV a página que parece DNV, quando nenhuma foi triada DNV.
    FALA COM A REDE (só a página suspeita). Devolve os tipos, corrigidos."""
    if any(d["tipo"] == "DNV" for d in documentos):
        return tipos
    tipos = list(tipos)
    for doc, sinais in paginas_que_parecem_dnv(documentos):
        i = documentos.index(doc)
        dados, envio = ler_pagina(conversar, pasta, modelos_em_uso, paginas[i], "DNV")
        envio["etapa"] = "releitura_dnv"
        envios.append(envio)
        if not (dados.get("nome_rn") or dados.get("numero_dnv") or dados.get("nome_mae")):
            continue   # a releitura não trouxe DNV: a página fica como estava
        doc.update({"tipo": "DNV", "dados": dados, "triada_como": tipos[i],
                    "relida_como_dnv_por": sinais})
        tipos[i] = "DNV"
        return tipos
    return tipos


# ----------------------------------------------------- juntar (sem rede)

DUVIDA = " (?)"


def _valor(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(_valor(x) for x in v if _valor(x))
    texto = str(v).strip()
    return "" if texto.lower() in ("null", "none", "-") else texto


def _limpo(v: Any) -> str:
    texto = _valor(v)
    return texto[:-len(DUVIDA)].strip() if texto.endswith(DUVIDA) else texto.replace("(?)", "").strip()


def _duvidoso(v: Any) -> bool:
    return "(?)" in _valor(v)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "")
                   if unicodedata.category(c) != "Mn").upper()


def _palavras(nome: str) -> list[str]:
    return [p for p in re.split(r"[^A-Z]+", _sem_acento(nome))
            if p and p not in ("DE", "DA", "DO", "DOS", "DAS", "E")]


def mesmo_nome(a: str, b: str) -> float:
    """Quanto dois nomes coincidem, de 0 a 1, pelas palavras sem acento e sem
    «de/da/dos». SÓ CALCULA. A grafia do RG e a da DNV raramente batem letra a
    letra (D'Avila × D'Arilar, Alcântara × Alcantara)."""
    pa, pb = set(_palavras(a)), set(_palavras(b))
    if not pa or not pb:
        return 0.0
    # UMA LETRA TROCADA NÃO FAZ OUTRA PESSOA — «Izaias» e «Isaias» são o mesmo
    # falecido em dois documentos do mesmo óbito (medido em 12/10/2026). Palavra
    # de SEIS letras ou mais, do mesmo tamanho, vale como igual se só UMA letra
    # difere. Com cinco, «Maria» e «Mario» seriam a mesma pessoa — e não são.
    def casa(w: str) -> bool:
        return w in pb or (len(w) >= 6 and any(
            len(x) == len(w) and sum(1 for i, j in zip(w, x) if i != j) == 1
            for x in pb))
    return sum(1 for w in pa if casa(w)) / max(len(pa), len(pb))


def data_iso(texto: Any) -> str:
    """DD/MM/AAAA (ou com hífen, ou só dígitos) → AAAA-MM-DD; vazio se não é data."""
    t = _limpo(texto)
    m = re.match(r"^\s*(\d{1,2})\s*[/.\-]?\s*(\d{1,2})\s*[/.\-]?\s*(\d{4})\s*$", t)
    if not m:
        m2 = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", t)
        return t if m2 else ""
    d, mes, a = (int(x) for x in m.groups())
    try:
        return date(a, mes, d).isoformat()
    except ValueError:
        return ""


def so_digitos(texto: Any) -> str:
    return re.sub(r"\D", "", _limpo(texto))


def cpf_valido(numero: Any) -> bool:
    import cpf_cnpj
    return bool(cpf_cnpj.cpf_valido(so_digitos(numero)))


def cns_valido(numero: Any) -> bool:
    """O Cartão Nacional de Saúde: 15 dígitos, soma ponderada (15..1) múltipla
    de 11. SÓ CALCULA.

    E NÃO SE FILTRA PELO PRIMEIRO DÍGITO — eu filtrava por 1/2/7/8/9 e a DNV
    real de 01/10/2026 trouxe um cartão começando por 5, que passa na soma."""
    d = so_digitos(numero)
    if len(d) != 15:
        return False
    return sum(int(c) * (15 - i) for i, c in enumerate(d)) % 11 == 0


PARTICULAS = frozenset({"de", "da", "do", "dos", "das", "e"})


def _capitalizar(texto: str) -> str:
    """«CIDADE EXEMPLO» → «Cidade Exemplo», «ANA DE SOUSA» → «Ana de Sousa». Texto que
    já vem com maiúsculas e minúsculas fica como veio: a grafia é de quem escreveu."""
    texto = (texto or "").strip()
    if not texto or not texto.isupper():
        return texto
    palavras = texto.lower().split()
    # «D'AVILA» é «D'Avila», como o termo da casa escreve: cada pedaço do
    # apóstrofo ganha a maiúscula.
    return " ".join(w if (i and w in PARTICULAS)
                    else "'".join(s[:1].upper() + s[1:] for s in w.split("'"))
                    for i, w in enumerate(palavras))


def _uf_e_cidade(texto: Any) -> tuple[str, str]:
    """«Imperatriz-MA», «Cidade Exemplo MA», «TUCUMA - PA» → (cidade, UF)."""
    t = _limpo(texto)
    m = re.match(r"^(.*?)[\s\-/,]+([A-Za-z]{2})\.?$", t)
    if m:
        return _capitalizar(m.group(1).strip(" -/,")), m.group(2).upper()
    return _capitalizar(t), ""


def _sexo(texto: Any) -> str:
    t = _sem_acento(_limpo(texto))
    if t.startswith("M"):
        return "M"
    if t.startswith("F"):
        return "F"
    return "IGNORADO" if t else ""


def _cor(texto: Any) -> str:
    t = _sem_acento(_limpo(texto))
    for chave in ("BRANCA", "PRETA", "PARDA", "AMARELA", "INDIGENA"):
        if t.startswith(chave[:4]):
            return chave
    return "IGNORADA" if t else ""


def _local_nascimento(texto: Any) -> str:
    t = _sem_acento(_limpo(texto))
    if not t:
        return ""
    if t.startswith("HOSP"):
        return "1"
    if "ESTAB" in t:
        return "2"
    if t.startswith("DOMIC"):
        return "3"
    if t.startswith("IGNOR"):
        return "9"
    return "5"


def _local_obito(texto: Any) -> str:
    t = _sem_acento(_limpo(texto))
    if "VIA" in t:
        return "4"
    return _local_nascimento(texto)


def _gemeo(texto: Any) -> str:
    t = _sem_acento(_limpo(texto))
    if not t:
        return ""
    if t.startswith("UNIC"):
        return "1"
    if t.startswith("DUPL"):
        return "2"
    if t.startswith("TRIP"):
        return "3"
    return "9"


def _natureza_obito(texto: Any) -> str:
    t = _sem_acento(_limpo(texto))
    if not t:
        return ""
    if t.startswith("NATUR"):
        return "1"
    if t.startswith("IGNOR"):
        return "9"
    return "2"


def _estado_civil(texto: Any, sexo: str) -> str:
    t = _sem_acento(_limpo(texto))
    fem = sexo == "F"
    for raiz, m, f in (("SOLT", "solteiro", "solteira"), ("CASAD", "casado", "casada"),
                       ("VIUV", "viúvo", "viúva"), ("DIVORC", "divorciado", "divorciada"),
                       ("SEPAR", "separado judicialmente", "separada judicialmente")):
        if t.startswith(raiz):
            return f if fem else m
    if "UNIAO" in t:
        return "em união estável"
    return ""


def _endereco(logradouro: Any, numero: Any) -> str:
    log, num = _limpo(logradouro), _limpo(numero)
    if log and num:
        return f"{log}, {num}"
    return log


def _documento(pessoa: dict, ident: dict | None) -> None:
    """CPF primeiro (é o que a CRC e o SIRC cruzam); sem ele, o RG com o órgão."""
    if not ident:
        return
    cpf = so_digitos(ident.get("cpf"))
    if len(cpf) == 11:
        pessoa.update(documento_tipo="CPF", documento_numero=cpf)
    elif _limpo(ident.get("numero_documento")):
        pessoa.update(documento_tipo="RG",
                      documento_numero=_limpo(ident.get("numero_documento")),
                      documento_orgao=_limpo(ident.get("orgao_emissor")))


def _identidades(documentos: list[dict]) -> list[dict]:
    """Todas as pessoas lidas dos documentos de identidade, cada uma com a
    página de onde veio."""
    saida = []
    for d in documentos:
        if d["tipo"] != "IDENTIDADE":
            continue
        pessoas = d["dados"].get("pessoas")
        if isinstance(pessoas, dict):
            pessoas = [pessoas]
        if not isinstance(pessoas, list):
            pessoas = [d["dados"]] if d["dados"].get("nome") else []
        for p in pessoas:
            if isinstance(p, dict) and _limpo(p.get("nome")):
                saida.append({**p, "_onde": f"{d['arquivo']} p{d['n']}"})
    return _agrupar(saida)


def _agrupar(pessoas: list[dict]) -> list[dict]:
    """A MESMA PESSOA EM VÁRIOS DOCUMENTOS É UMA SÓ — medido no primeiro óbito
    real (12/10/2026): o falecido veio no RG, no cartão do CPF e em mais duas
    páginas, e cada uma virava uma «pessoa a mais», escondendo o declarante.
    Junta por CPF igual ou nome que coincide em 3/4 das palavras; o primeiro
    valor lido de cada campo fica, e os seguintes só preenchem o que falta."""
    grupos: list[dict] = []
    for p in pessoas:
        cpf = so_digitos(p.get("cpf"))
        alvo = None
        for g in grupos:
            if (cpf and len(cpf) == 11 and cpf == so_digitos(g.get("cpf"))) or \
                    mesmo_nome(_limpo(p.get("nome")), _limpo(g.get("nome"))) >= 0.75:
                alvo = g
                break
        if alvo is None:
            grupos.append(dict(p))
            continue
        for chave, valor in p.items():
            if chave == "_onde":
                alvo["_onde"] = f"{alvo['_onde']}; {valor}"
            elif _limpo(valor) and not _limpo(alvo.get(chave)):
                alvo[chave] = valor
    return grupos


def _a_que_mais_se_parece(nome: str, pessoas: list[dict]) -> tuple[dict | None, float]:
    melhor, nota = None, 0.0
    for p in pessoas:
        n = mesmo_nome(nome, _limpo(p.get("nome")))
        if n > nota:
            melhor, nota = p, n
    return melhor, nota


def _aviso(lista: list, gravidade: str, texto: str, onde: str = "") -> None:
    lista.append({"gravidade": gravidade, "texto": texto, "onde": onde})


def _duvidas(lista: list, doc: dict, rotulos: dict[str, str]) -> None:
    for chave, rotulo in rotulos.items():
        if _duvidoso(doc["dados"].get(chave)):
            _aviso(lista, "CONFERIR",
                   f"{rotulo}: a leitura ficou em dúvida («{_valor(doc['dados'].get(chave))}»)",
                   f"{doc['arquivo']} p{doc['n']}")


def _idade_em(nascimento_iso: str, no_dia_iso: str) -> int | None:
    try:
        n, d = date.fromisoformat(nascimento_iso), date.fromisoformat(no_dia_iso)
    except ValueError:
        return None
    return d.year - n.year - ((d.month, d.day) < (n.month, n.day))


def _pais_de(pessoa: dict, ident: dict | None, onde_pai: str, onde_mae: str,
             pessoas: list[dict]) -> None:
    """Os pais de alguém, pela filiação do documento de identidade dele."""
    if not ident:
        return
    if _limpo(ident.get("filiacao_pai")):
        pessoas.append({"papel": onde_pai, "nome": _limpo(ident.get("filiacao_pai")),
                        "sexo": "M"})
    if _limpo(ident.get("filiacao_mae")):
        pessoas.append({"papel": onde_mae, "nome": _limpo(ident.get("filiacao_mae")),
                        "sexo": "F"})


def juntar_nascimento(documentos: list[dict], tardio: bool = False) -> dict:
    """O registro de nascimento que os documentos permitem montar. SÓ CALCULA.

    `tardio` é a marca «É registro tardio» da caixa de juntar os documentos
    (21/10/2026): sem DNV e sem requerimento, monta pelos documentos de
    identidade (`juntar_tardio_dos_documentos`); com DNV, marca o tardio e
    traz as testemunhas pelo nome do arquivo.

    A DNV é a espinha: dela saem o registrado, o fato e a mãe. Os documentos de
    identidade dão os números, a filiação dos pais (os avós) e — o que só se
    deduz — o PAI: a pessoa identificada que não é a mãe. Dedução vira aviso."""
    avisos: list[dict] = []
    dnvs = [d for d in documentos if d["tipo"] == "DNV"]
    tardios = [d for d in documentos if d["tipo"] == "TARDIO"]
    if not dnvs and tardios:
        return juntar_tardio(documentos)
    if not dnvs and tardio:
        return juntar_tardio_dos_documentos(documentos)
    if not dnvs:
        suspeitas = paginas_que_parecem_dnv(documentos)
        if suspeitas:
            d, sinais = suspeitas[0]
            raise LeituraError(
                f"Entre os documentos não há uma DNV lida como DNV — mas a página "
                f"{d['n']} de «{d['arquivo']}» parece ser a DNV ({', '.join(sinais)}) e "
                f"não foi lida como tal. Confira essa página (a imagem está legível? é a "
                f"DNV inteira?) e leia de novo, ou digite na tela.")
        raise LeituraError("Entre os documentos não há uma DNV — sem ela não se monta "
                           "o registro de nascimento. Anexe a DNV ou digite na tela. "
                           "Se é registro tardio, marque «É registro tardio» na "
                           "caixa de juntar os documentos: a leitura monta o "
                           "nascimento sem DNV e o requerimento sai preenchido "
                           "para assinar.")
    for d in dnvs:
        if d.get("triada_como"):
            _aviso(avisos, "CONFERIR",
                   f"A triagem disse {d['triada_como']} para a página {d['n']} de "
                   f"«{d['arquivo']}»; ela foi relida como DNV pelos sinais "
                   f"({', '.join(d.get('relida_como_dnv_por') or [])}). "
                   f"Confira com o original.",
                   f"{d['arquivo']} p{d['n']}")
    if len(dnvs) > 1:
        _aviso(avisos, "CONFERIR", "Há mais de uma DNV nos documentos — gêmeos? Só a "
               "primeira foi usada; os outros registros se fazem um a um.")
    dnv = dnvs[0]
    v = dnv["dados"]
    onde = f"{dnv['arquivo']} p{dnv['n']}"
    _duvidas(avisos, dnv, {"nome_rn": "Nome do registrado", "data_nascimento": "Data do nascimento",
                           "hora_nascimento": "Hora", "nome_mae": "Nome da mãe",
                           "nascimento_mae": "Nascimento da mãe", "numero_dnv": "Número da DNV",
                           "peso_gramas": "Peso", "estabelecimento": "Estabelecimento",
                           "endereco_ocorrencia": "Endereço do parto",
                           "logradouro_residencia": "Residência da mãe",
                           "bairro_residencia": "Bairro da mãe"})

    data_fato = data_iso(v.get("data_nascimento"))
    sexo = _sexo(v.get("sexo"))
    cidade_parto, uf_parto = _capitalizar(_limpo(v.get("municipio_ocorrencia"))), _limpo(v.get("uf_ocorrencia")).upper()
    local_end = ", ".join(x for x in (
        _endereco(v.get("endereco_ocorrencia"), v.get("numero_ocorrencia")),
        _capitalizar(_limpo(v.get("bairro_ocorrencia"))),
        f"{cidade_parto}/{uf_parto}" if cidade_parto and uf_parto else cidade_parto) if x)
    valores = {
        "especie": "NASCIMENTO",
        "nome": _limpo(v.get("nome_rn")),
        "data_fato": data_fato,
        "hora_fato": _limpo(v.get("hora_nascimento")),
        "dnv": _limpo(v.get("numero_dnv")),
        "cor_raca": _cor(v.get("raca_cor_rn")),
        "local_fato_nome": _limpo(v.get("estabelecimento")),
        "local_fato_endereco": local_end,
        "ibge_local_nascimento": _local_nascimento(v.get("local_ocorrencia")),
        "ibge_gemeo": _gemeo(v.get("tipo_gravidez")),
    }
    pessoas: list[dict] = [{"papel": "REGISTRADO", "nome": valores["nome"], "sexo": sexo,
                            "data_nascimento": data_fato}]

    nat_mae_cidade, nat_mae_uf = _uf_e_cidade(v.get("naturalidade_mae"))
    mae = {"papel": "MAE", "nome": _limpo(v.get("nome_mae")), "sexo": "F",
           "data_nascimento": data_iso(v.get("nascimento_mae")),
           "idade_no_fato": so_digitos(v.get("idade_mae")),
           "naturalidade_cidade": nat_mae_cidade, "naturalidade_uf": nat_mae_uf,
           "estado_civil": _estado_civil(v.get("situacao_conjugal_mae"), "F"),
           "profissao": _limpo(v.get("ocupacao_mae")).lower(),
           "endereco": _endereco(v.get("logradouro_residencia"), v.get("numero_residencia")),
           "bairro": _capitalizar(_limpo(v.get("bairro_residencia"))),
           "cidade": _capitalizar(_limpo(v.get("municipio_residencia"))),
           "uf": _limpo(v.get("uf_residencia")).upper()}

    ids = _identidades(documentos)
    id_mae, nota = _a_que_mais_se_parece(mae["nome"], ids)
    if id_mae is not None and nota < 0.5:
        id_mae = None
    if id_mae is not None:
        if _limpo(id_mae.get("nome")).upper() == mae["nome"].upper():
            pass
        elif _sem_acento(_limpo(id_mae.get("nome"))) == _sem_acento(mae["nome"]):
            mae["nome"] = _capitalizar(_limpo(id_mae.get("nome")))      # só o acento
        else:
            _aviso(avisos, "CONFERIR",
                   f"O nome da mãe na DNV («{mae['nome']}») e no documento dela "
                   f"(«{_limpo(id_mae.get('nome'))}») não são iguais letra a letra — "
                   f"vale o do documento de identidade, conferido no original.",
                   id_mae["_onde"])
            mae["nome"] = _capitalizar(_limpo(id_mae.get("nome")))
        _documento(mae, id_mae)
        nasc_rg = data_iso(id_mae.get("data_nascimento"))
        if nasc_rg and mae["data_nascimento"] and nasc_rg != mae["data_nascimento"]:
            _aviso(avisos, "CONFERIR",
                   f"A data de nascimento da mãe difere: {mae['data_nascimento']} na DNV, "
                   f"{nasc_rg} no documento.", id_mae["_onde"])
        mae["data_nascimento"] = nasc_rg or mae["data_nascimento"]
        if not mae["naturalidade_cidade"] and _limpo(id_mae.get("naturalidade")):
            mae["naturalidade_cidade"], mae["naturalidade_uf"] = _uf_e_cidade(id_mae.get("naturalidade"))
        _pais_de(mae, id_mae, "AVO_MATERNO", "AVO_MATERNA", pessoas)
    else:
        _aviso(avisos, "CONFERIR", "Não há documento de identidade da mãe entre os "
               "anexos — CPF e avós maternos ficam para digitar.")

    if mae["data_nascimento"] and data_fato:
        idade = _idade_em(mae["data_nascimento"], data_fato)
        if idade is not None and mae["idade_no_fato"] and str(idade) != mae["idade_no_fato"]:
            _aviso(avisos, "CONFERIR",
                   f"A idade da mãe no parto não fecha: a DNV diz {mae['idade_no_fato']} "
                   f"anos, e pela data de nascimento ela tinha {idade}.", onde)
        if idade is not None and not mae["idade_no_fato"]:
            mae["idade_no_fato"] = str(idade)
    pessoas.append(mae)

    outros = [p for p in ids if p is not id_mae]
    if len(outros) == 1:
        p = outros[0]
        pai = {"papel": "PAI", "nome": _limpo(p.get("nome")), "sexo": "M",
               "data_nascimento": data_iso(p.get("data_nascimento"))}
        pai["naturalidade_cidade"], pai["naturalidade_uf"] = _uf_e_cidade(p.get("naturalidade"))
        _documento(pai, p)
        pessoas.append(pai)
        _pais_de(pai, p, "AVO_PATERNO", "AVO_PATERNA", pessoas)
        _aviso(avisos, "CONFERIR",
               f"«{pai['nome']}» entrou como PAI porque é a outra pessoa identificada "
               f"nos documentos — confirme a paternidade e se é ele quem declara.", p["_onde"])
    elif len(outros) > 1:
        _aviso(avisos, "CONFERIR",
               "Há mais de uma pessoa identificada além da mãe ("
               + "; ".join(_limpo(p.get("nome")) for p in outros)
               + ") — o pai e o declarante ficam para escolher na tela.")
    else:
        _aviso(avisos, "CONFERIR", "Não há documento do pai entre os anexos — a filiação "
               "paterna fica para digitar (ou para o reconhecimento posterior).")

    _aviso(avisos, "CONFERIR",
           f"A naturalidade é escolha do declarante (Lei 6.015/1973, art. 54, § 4º): o "
           f"município do parto ({cidade_parto or '?'}) ou o da residência da mãe "
           f"({mae['cidade'] or '?'}). Ela NÃO foi preenchida.")
    _conferir_numeros(avisos, v, onde, {"cartao_sus_rn": "Cartão SUS do registrado",
                                        "cartao_sus_mae": "Cartão SUS da mãe"})
    _conferir_cpfs(avisos, pessoas)
    _conferir_residencia(avisos, documentos, mae)
    if tardios:
        # DNV E REQUERIMENTO JUNTOS: o fato sai da DNV, e do requerimento saem
        # a marca, o número e as testemunhas.
        req = tardios[0]["dados"]
        valores["registro_tardio"] = "1"
        valores["tardio_requerimento"] = _limpo(req.get("numero_requerimento"))
        pessoas += _testemunhas_do_requerimento(req, _identidades(documentos))
    elif tardio:
        # DNV SEM REQUERIMENTO: o requerimento ainda vai ser impresso. As
        # testemunhas e quem requer saem do nome do arquivo.
        valores["registro_tardio"] = "1"
        ja = {p["papel"] for p in pessoas}
        nomeados, _ = _pessoas_pelo_nome_do_arquivo(documentos, ids, avisos)
        for papel, ident in nomeados:
            if papel in ("TESTEMUNHA", "TESTEMUNHA2", "DECLARANTE") and papel not in ja:
                pessoas.append(_pessoa_da_identidade(ident, papel))
        _aviso(avisos, "CONFERIR", AVISO_DO_TARDIO)
    for p in pessoas:
        p["nome"] = _capitalizar(p.get("nome") or "")
    return {"valores": valores, "pessoas": [p for p in pessoas if p.get("nome")],
            "conferencia": avisos}


def _do_requerimento(v: Any, papel: str, ids: list[dict]) -> dict | None:
    """Uma pessoa do requerimento do tardio, com o documento conferido no RG
    lido, quando houver um do mesmo nome. Só calcula."""
    if not isinstance(v, dict) or not _limpo(v.get("nome")):
        return None
    sexo = _sexo(v.get("sexo"))
    cidade, uf = _uf_e_cidade(v.get("naturalidade"))
    p = {"papel": papel, "nome": _limpo(v.get("nome")), "sexo": sexo,
         "data_nascimento": data_iso(v.get("data_nascimento")),
         "nacionalidade": _limpo(v.get("nacionalidade")).lower(),
         "estado_civil": _estado_civil(v.get("estado_civil"), sexo),
         "profissao": _limpo(v.get("profissao")).lower(),
         "naturalidade_cidade": cidade, "naturalidade_uf": uf,
         "endereco": _limpo(v.get("endereco")),
         "bairro": _capitalizar(_limpo(v.get("bairro"))),
         "cidade": _capitalizar(_limpo(v.get("municipio"))),
         "uf": _limpo(v.get("uf")).upper()}
    cpf = so_digitos(v.get("cpf"))
    if len(cpf) == 11:
        p.update(documento_tipo="CPF", documento_numero=cpf)
    elif _limpo(v.get("rg")):
        p.update(documento_tipo="RG", documento_numero=_limpo(v.get("rg")),
                 documento_orgao=_limpo(v.get("orgao_emissor")))
    ident, nota = _a_que_mais_se_parece(p["nome"], ids)
    if ident is not None and nota >= 0.75:
        _documento(p, ident)
        p["data_nascimento"] = (data_iso(ident.get("data_nascimento"))
                                or p["data_nascimento"])
    return {k: x for k, x in p.items() if x}


def _testemunhas_do_requerimento(req: dict, ids: list[dict]) -> list[dict]:
    """As duas testemunhas do art. 249, II, na ordem do requerimento."""
    saida = []
    for papel, v in zip(("TESTEMUNHA", "TESTEMUNHA2"), _lista(req.get("testemunhas"))):
        p = _do_requerimento(v, papel, ids)
        if p:
            saida.append(p)
    return saida


def _nomes_da_lista(v: Any) -> list[str]:
    """Os nomes de uma lista lida — de textos, de objetos com `nome`, ou um
    texto só com os nomes separados por «e», «;» ou vírgula. Só calcula."""
    if isinstance(v, dict):
        v = [v]
    if isinstance(v, list):
        return [_limpo(x if isinstance(x, str) else (x or {}).get("nome"))
                for x in v if _limpo(x if isinstance(x, str) else (x or {}).get("nome"))]
    return [n.strip() for n in re.split(r";|,| e ", str(v or "")) if n.strip()]


def juntar_tardio(documentos: list[dict]) -> dict:
    """O registro de nascimento TARDIO montado do requerimento, sem DNV. SÓ
    CALCULA. 21/10/2026.

    É o caso para que o tardio existe: quem nunca foi registrado costuma não
    ter DNV (art. 236 a ressalva). O requerimento é a espinha — dele saem o
    registrando, a filiação, os avós, quem requer (o declarante) e as duas
    testemunhas; os documentos de identidade conferem os números. O que o
    escrevente precisa decidir vira aviso, e nada se deduz por ele.
    """
    avisos: list[dict] = []
    doc = [d for d in documentos if d["tipo"] == "TARDIO"][0]
    v = doc["dados"]
    onde = f"{doc['arquivo']} p{doc['n']}"
    ids = _identidades(documentos)
    r = v.get("registrando") if isinstance(v.get("registrando"), dict) else {}
    sexo = _sexo(r.get("sexo"))
    cidade, uf = (_capitalizar(_limpo(r.get("municipio_nascimento"))),
                  _limpo(r.get("uf_nascimento")).upper())
    local_end = ", ".join(x for x in (
        _limpo(r.get("endereco_nascimento")),
        f"{cidade}/{uf}" if cidade and uf else cidade) if x)
    data_fato = data_iso(r.get("data_nascimento"))
    valores = {
        "especie": "NASCIMENTO",
        "nome": _limpo(r.get("nome")),
        "data_fato": data_fato,
        "hora_fato": _limpo(r.get("hora_nascimento")),
        "dnv": _limpo(r.get("numero_dnv")),
        "cor_raca": _cor(r.get("raca_cor")),
        "local_fato_nome": _limpo(r.get("local_nascimento")),
        "local_fato_endereco": local_end,
        "ibge_gemeo": _gemeo(r.get("gemeo")),
        "registro_tardio": "1",
        "tardio_requerimento": _limpo(v.get("numero_requerimento")),
    }
    pessoas: list[dict] = []
    registrado = _do_requerimento({**r, "sexo": r.get("sexo")}, "REGISTRADO", ids) \
        or {"papel": "REGISTRADO", "nome": valores["nome"]}
    registrado["data_nascimento"] = data_fato or registrado.get("data_nascimento", "")
    pessoas.append(registrado)
    for chave, papel in (("mae", "MAE"), ("pai", "PAI")):
        p = _do_requerimento(v.get(chave), papel, ids)
        if p:
            pessoas.append(p)
        else:
            _aviso(avisos, "CONFERIR",
                   f"O requerimento não traz a {'mãe' if papel == 'MAE' else 'o pai'} — "
                   f"preencha ou declare ignorado (sem DNV, a filiação só entra por "
                   f"reconhecimento de quem comparece).", onde)
    for chave, papeis in (("avos_maternos", ("AVO_MATERNO", "AVO_MATERNA")),
                          ("avos_paternos", ("AVO_PATERNO", "AVO_PATERNA"))):
        nomes = _nomes_da_lista(v.get(chave))
        for papel, nome in zip(papeis, nomes):
            if _limpo(nome):
                pessoas.append({"papel": papel, "nome": _limpo(nome)})
    requerente = _do_requerimento(v.get("requerente"), "DECLARANTE", ids)
    if requerente:
        pessoas.append(requerente)
    else:
        _aviso(avisos, "CONFERIR", "O requerimento não diz quem requer — o "
               "declarante fica para preencher.", onde)
    testemunhas = _testemunhas_do_requerimento(v, ids)
    pessoas += testemunhas
    if len(testemunhas) < 2:
        _aviso(avisos, "CONFERIR",
               f"O requerimento traz {len(testemunhas)} testemunha(s); o art. 249, "
               f"II pede duas, salvo o registrando menor de 12 anos com DNV.", onde)
    _aviso(avisos, "CONFERIR",
           "Registro TARDIO montado do requerimento, sem DNV: confira cada dado com "
           "o requerente e as testemunhas na entrevista (art. 249, III), e anexe o "
           "requerimento assinado — ele fica arquivado por 20 anos (§ 1º).", onde)
    _aviso(avisos, "CONFERIR",
           "A naturalidade é escolha do declarante (Lei 6.015/1973, art. 54, § 4º) "
           "e NÃO foi preenchida.")
    _conferir_cpfs(avisos, pessoas)
    for p in pessoas:
        p["nome"] = _capitalizar(p.get("nome") or "")
    return {"valores": valores, "pessoas": [p for p in pessoas if p.get("nome")],
            "conferencia": avisos}


# O TARDIO SEM DNV E SEM REQUERIMENTO — 21/10/2026, leitura nº 10 da
# produção. O balcão juntou o documento do pai (que declara) e os das duas
# testemunhas para registrar fora do prazo, e a leitura recusava: não havia
# DNV nem requerimento — e o requerimento é justamente o papel que se imprime
# DEPOIS, preenchido, para os comparecentes assinarem. O oficial: «não tem
# opção de colocar que é registro tardio para receber a documentação e
# preencher o requerimento para imprimirmos».
#
# QUEM É QUEM SAI DO NOME DO ARQUIVO, E SÓ DELE. O documento de identidade
# não diz o papel da pessoa no registro; o balcão já nomeia os arquivos assim
# («PAI e DECLARANTE.pdf», «TESTEMUNHA 1.pdf»). Arquivo sem papel no nome
# vira aviso — escolher quem é testemunha e quem é pai seria a máquina
# qualificando o registro.
PAPEIS_NO_NOME_DO_ARQUIVO = (
    (re.compile(r"\bTESTEMUNHA\s*0?2\b|\bSEGUNDA\s+TESTEMUNHA\b|\b2\S?\s*TESTEMUNHA\b"),
     "TESTEMUNHA2"),
    (re.compile(r"\bTESTEMUNHA"), "TESTEMUNHA"),
    (re.compile(r"\bREGISTRAND[OA]\b|\bREGISTRAD[OA]\b"), "REGISTRADO"),
    (re.compile(r"\bMAE\b|\bGENITORA\b"), "MAE"),
    (re.compile(r"\bPAI\b|\bGENITOR\b"), "PAI"),
    (re.compile(r"\bDECLARANTE\b|\bREQUERENTE\b"), "DECLARANTE"),
)

AVISO_DO_TARDIO = (
    "Registro TARDIO (art. 249 do Código de Normas do TJMA; arts. 480 a 494 do "
    "Provimento CNJ 149/2023): confira cada dado na entrevista, imprima o "
    "requerimento preenchido (botão na caixa «Registro tardio») para o requerente "
    "e as duas testemunhas assinarem na presença do oficial, e anexe-o assinado "
    "— ele fica arquivado por 20 anos.")


def papeis_pelo_nome_do_arquivo(nome: str) -> list[str]:
    """Os papéis que o nome do arquivo declara, na ordem da tabela. SÓ CALCULA."""
    texto = _sem_acento(Path(nome or "").stem).upper()
    texto = re.sub(r"[_\-.]+", " ", texto)
    papeis: list[str] = []
    for padrao, papel in PAPEIS_NO_NOME_DO_ARQUIVO:
        if papel == "TESTEMUNHA" and "TESTEMUNHA2" in papeis:
            continue
        if padrao.search(texto):
            papeis.append(papel)
    return papeis


def _pessoas_pelo_nome_do_arquivo(documentos: list[dict], ids: list[dict],
                                  avisos: list) -> tuple[list[tuple[str, dict]], list[dict]]:
    """[(papel, identidade)] dos arquivos de identidade cujo nome diz o papel,
    e as identidades que ficaram sem papel. SÓ CALCULA.

    O papel só vale para o arquivo que traz UMA pessoa: com duas, o nome do
    arquivo não diz qual das duas é a testemunha."""
    por_arquivo: dict[str, list[str]] = {}
    for d in documentos:
        if d["tipo"] != "IDENTIDADE":
            continue
        pessoas = d["dados"].get("pessoas")
        if isinstance(pessoas, dict):
            pessoas = [pessoas]
        if not isinstance(pessoas, list):
            pessoas = [d["dados"]] if d["dados"].get("nome") else []
        nomes = por_arquivo.setdefault(d["arquivo"], [])
        for p in pessoas:
            nome = _limpo((p or {}).get("nome")) if isinstance(p, dict) else ""
            if nome and all(mesmo_nome(nome, n) < 0.75 for n in nomes):
                nomes.append(nome)
    saida: list[tuple[str, dict]] = []
    usados: set[int] = set()
    for arquivo, nomes in por_arquivo.items():
        papeis = papeis_pelo_nome_do_arquivo(arquivo)
        if not papeis or not nomes:
            continue
        if len(nomes) > 1:
            _aviso(avisos, "CONFERIR",
                   f"«{arquivo}» diz {' e '.join(papeis)} no nome, mas traz "
                   f"{len(nomes)} pessoas ({'; '.join(nomes)}) — escolha na tela "
                   f"quem é quem.", arquivo)
            continue
        ident, nota = _a_que_mais_se_parece(nomes[0], ids)
        if ident is None or nota < 0.75:
            continue
        usados.add(id(ident))
        saida += [(papel, ident) for papel in papeis]
    return saida, [p for p in ids if id(p) not in usados]


def _pessoa_da_identidade(ident: dict, papel: str) -> dict:
    """A pessoa do assento montada do documento de identidade lido. SÓ CALCULA."""
    sexo = _sexo(ident.get("sexo")) or {"PAI": "M", "MAE": "F"}.get(papel, "")
    p = {"papel": papel, "nome": _limpo(ident.get("nome")), "sexo": sexo,
         "data_nascimento": data_iso(ident.get("data_nascimento"))}
    p["naturalidade_cidade"], p["naturalidade_uf"] = _uf_e_cidade(ident.get("naturalidade"))
    _documento(p, ident)
    return {k: v for k, v in p.items() if v}


def juntar_tardio_dos_documentos(documentos: list[dict]) -> dict:
    """O nascimento TARDIO sem DNV e sem requerimento, pelos documentos de
    identidade. SÓ CALCULA. 21/10/2026.

    Os dados do registrando (nome, data, lugar do nascimento) não estão em
    documento nenhum — vêm da entrevista, e ficam para digitar: são eles que
    o requerimento impresso leva para assinatura."""
    avisos: list[dict] = []
    ids = _identidades(documentos)
    nomeados, sem_papel = _pessoas_pelo_nome_do_arquivo(documentos, ids, avisos)
    valores = {"especie": "NASCIMENTO", "nome": "", "data_fato": "", "dnv": "",
               "registro_tardio": "1"}
    pessoas: list[dict] = []
    ja: set[str] = set()
    for papel, ident in nomeados:
        if papel in ja:
            _aviso(avisos, "CONFERIR",
                   f"Mais de um arquivo diz {papel} no nome — ficou o primeiro "
                   f"(«{_limpo(ident.get('nome'))}» não entrou nesse papel).",
                   ident.get("_onde", ""))
            continue
        ja.add(papel)
        p = _pessoa_da_identidade(ident, papel)
        pessoas.append(p)
        if papel == "REGISTRADO":
            valores["nome"] = p["nome"]
            valores["data_fato"] = p.get("data_nascimento", "")
        elif papel == "MAE":
            _pais_de(p, ident, "AVO_MATERNO", "AVO_MATERNA", pessoas)
        elif papel == "PAI":
            _pais_de(p, ident, "AVO_PATERNO", "AVO_PATERNA", pessoas)
    if not nomeados and not ids:
        raise LeituraError(
            "Entre os documentos não há documento de identidade lido — sem ele o "
            "registro tardio não tem de quem preencher os dados. Junte os "
            "documentos do pai, da mãe, de quem requer e das testemunhas, ou digite "
            "na tela (o requerimento se imprime do mesmo jeito).")
    for p in sem_papel:
        _aviso(avisos, "CONFERIR",
               f"«{_limpo(p.get('nome'))}» foi lido, mas o nome do arquivo não diz o "
               f"papel dele (pai, mãe, declarante, testemunha 1 ou 2) — escolha na "
               f"tela.", p.get("_onde", ""))
    if "REGISTRADO" not in ja:
        _aviso(avisos, "CONFERIR",
               "Os dados do registrando — nome, sexo, data, hora e lugar do "
               "nascimento, gêmeo — não estão em documento: digite-os com o "
               "requerente (Provimento CNJ 149/2023, art. 482, a a d).")
    faltam = [r for r, papel in (("primeira testemunha", "TESTEMUNHA"),
                                  ("segunda testemunha", "TESTEMUNHA2"),
                                  ("quem requer (declarante)", "DECLARANTE"))
              if papel not in ja]
    if faltam:
        _aviso(avisos, "CONFERIR",
               f"Falta(m) {', '.join(faltam)} — art. 249, II do Código de Normas "
               f"(as duas testemunhas só se dispensam com o registrando menor de "
               f"12 anos e com DNV).")
    _aviso(avisos, "CONFERIR", AVISO_DO_TARDIO)
    _aviso(avisos, "CONFERIR",
           "A naturalidade é escolha do declarante (Lei 6.015/1973, art. 54, § 4º) "
           "e NÃO foi preenchida.")
    _conferir_cpfs(avisos, pessoas)
    for p in pessoas:
        p["nome"] = _capitalizar(p.get("nome") or "")
    return {"valores": valores, "pessoas": [p for p in pessoas if p.get("nome")],
            "conferencia": avisos}


def juntar_obito(documentos: list[dict]) -> dict:
    """O registro de óbito que os documentos permitem montar. SÓ CALCULA.

    A DO é a espinha; o documento do falecido dá o CPF, e a outra pessoa
    identificada é, provavelmente, quem declara — dedução, e por isso aviso."""
    avisos: list[dict] = []
    dos = [d for d in documentos if d["tipo"] == "DO"]
    if not dos:
        raise LeituraError("Entre os documentos não há uma Declaração de Óbito — sem "
                           "ela não se monta o registro. Anexe a DO ou digite na tela.")
    do = dos[0]
    v = do["dados"]
    onde = f"{do['arquivo']} p{do['n']}"
    _duvidas(avisos, do, {"nome_falecido": "Nome do falecido", "data_obito": "Data do óbito",
                          "hora_obito": "Hora", "causa_a": "Causa da morte",
                          "medico_nome": "Médico atestante", "numero_do": "Número da DO"})
    sexo = _sexo(v.get("sexo"))
    cidade, uf = _capitalizar(_limpo(v.get("municipio_ocorrencia"))), _limpo(v.get("uf_ocorrencia")).upper()
    causas = "; ".join(x for x in (_limpo(v.get(k)) for k in
                                   ("causa_a", "causa_b", "causa_c", "causa_d", "causa_parte_ii")) if x)
    valores = {
        "especie": "OBITO",
        "nome": _limpo(v.get("nome_falecido")),
        "data_fato": data_iso(v.get("data_obito")),
        "hora_fato": _limpo(v.get("hora_obito")),
        "numero_do": _limpo(v.get("numero_do")),
        "cor_raca": _cor(v.get("raca_cor")),
        "local_fato_nome": _limpo(v.get("estabelecimento")),
        "local_fato_endereco": ", ".join(x for x in (
            _limpo(v.get("endereco_ocorrencia")),
            f"{cidade}/{uf}" if cidade and uf else cidade) if x),
        "causa_morte": causas,
        "atestante": _limpo(v.get("medico_nome")),
        "atestante_documento": _limpo(v.get("medico_crm")),
        "local_sepultamento": _limpo(v.get("local_sepultamento")),
        "ibge_local_obito": _local_obito(v.get("local_ocorrencia")),
        "ibge_natureza_obito": _natureza_obito(v.get("tipo_morte")),
    }
    nat_c, nat_uf = _uf_e_cidade(v.get("naturalidade"))
    falecido = {"papel": "FALECIDO", "nome": valores["nome"], "sexo": sexo,
                "data_nascimento": data_iso(v.get("data_nascimento")),
                "idade_no_fato": so_digitos(v.get("idade")),
                "estado_civil": _estado_civil(v.get("estado_civil"), sexo),
                "profissao": _limpo(v.get("ocupacao")).lower(),
                "naturalidade_cidade": nat_c, "naturalidade_uf": nat_uf,
                "endereco": _endereco(v.get("logradouro_residencia"), v.get("numero_residencia")),
                "bairro": _capitalizar(_limpo(v.get("bairro_residencia"))),
                "cidade": _capitalizar(_limpo(v.get("municipio_residencia"))),
                "uf": _limpo(v.get("uf_residencia")).upper()}
    pessoas: list[dict] = [falecido]
    if _limpo(v.get("nome_pai")):
        pessoas.append({"papel": "PAI", "nome": _limpo(v.get("nome_pai")), "sexo": "M"})
    if _limpo(v.get("nome_mae")):
        pessoas.append({"papel": "MAE", "nome": _limpo(v.get("nome_mae")), "sexo": "F"})

    ids = _identidades(documentos)
    id_fal, nota = _a_que_mais_se_parece(falecido["nome"], ids)
    if id_fal is not None and nota >= 0.5:
        if _limpo(id_fal.get("nome")).upper() == falecido["nome"].upper():
            pass
        elif _sem_acento(_limpo(id_fal.get("nome"))) == _sem_acento(falecido["nome"]):
            falecido["nome"] = valores["nome"] = _capitalizar(_limpo(id_fal.get("nome")))
        else:
            _aviso(avisos, "CONFERIR",
                   f"O nome do falecido na DO («{falecido['nome']}») e no documento dele "
                   f"(«{_limpo(id_fal.get('nome'))}») não são iguais letra a letra — vale "
                   f"o do documento de identidade, conferido no original.", id_fal["_onde"])
            falecido["nome"] = _capitalizar(_limpo(id_fal.get("nome")))
            valores["nome"] = falecido["nome"]
        _documento(falecido, id_fal)
        nasc_rg = data_iso(id_fal.get("data_nascimento"))
        if nasc_rg and falecido["data_nascimento"] and nasc_rg != falecido["data_nascimento"]:
            _aviso(avisos, "CONFERIR",
                   f"A data de nascimento do falecido difere: {falecido['data_nascimento']} "
                   f"na DO, {nasc_rg} no documento.", id_fal["_onde"])
        falecido["data_nascimento"] = nasc_rg or falecido["data_nascimento"]
    else:
        id_fal = None
        _aviso(avisos, "CONFERIR", "Não há documento de identidade do falecido entre os "
               "anexos — o CPF dele fica para digitar.")
    if falecido["data_nascimento"] and valores["data_fato"]:
        idade = _idade_em(falecido["data_nascimento"], valores["data_fato"])
        if idade is not None and falecido["idade_no_fato"] and str(idade) != falecido["idade_no_fato"]:
            _aviso(avisos, "CONFERIR",
                   f"A idade não fecha: a DO diz {falecido['idade_no_fato']} anos, e pela "
                   f"data de nascimento eram {idade}.", onde)
        if idade is not None and not falecido["idade_no_fato"]:
            falecido["idade_no_fato"] = str(idade)

    outros = [p for p in ids if p is not id_fal]
    if len(outros) == 1:
        p = outros[0]
        decl = {"papel": "DECLARANTE", "nome": _limpo(p.get("nome")),
                "data_nascimento": data_iso(p.get("data_nascimento"))}
        _documento(decl, p)
        pessoas.append(decl)
        _aviso(avisos, "CONFERIR",
               f"«{decl['nome']}» entrou como DECLARANTE porque é a outra pessoa "
               f"identificada nos documentos — confirme.", p["_onde"])
    elif len(outros) > 1:
        _aviso(avisos, "CONFERIR", "Há mais de uma pessoa identificada além do falecido ("
               + "; ".join(_limpo(p.get("nome")) for p in outros)
               + ") — o declarante fica para escolher na tela.")
    if not causas:
        _aviso(avisos, "CONFERIR", "A causa da morte não foi lida na DO.", onde)
    _conferir_numeros(avisos, v, onde, {"cartao_sus": "Cartão SUS do falecido"})
    _conferir_cpfs(avisos, pessoas)
    for p in pessoas:
        p["nome"] = _capitalizar(p.get("nome") or "")
    return {"valores": valores, "pessoas": [p for p in pessoas if p.get("nome")],
            "conferencia": avisos}


#: Os campos de cada nubente na tela «Abrir habilitação» (`habilitacao.abrir`).
CAMPOS_DO_NUBENTE = ("nome", "nome_pos", "sexo", "nascimento", "documento",
                     "estado_civil", "profissao", "nacionalidade", "naturalidade",
                     "endereco", "pai", "mae")


def _lista(v: Any) -> list[dict]:
    if isinstance(v, dict):
        return [v]
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _estado_civil_da_habilitacao(texto: Any) -> str:
    """Os três da tela. Separado judicialmente não casa sem o divórcio, e por
    isso não vira nenhum deles — fica vazio, e quem decide é o oficial."""
    t = _sem_acento(_limpo(texto))
    if t.startswith("SOLT"):
        return "SOLTEIRO"
    if t.startswith("VIUV"):
        return "VIUVO"
    if t.startswith("DIVORC"):
        return "DIVORCIADO"
    return ""


def _regime(texto: Any) -> str:
    t = _sem_acento(_limpo(texto))
    if "AQUESTOS" in t or "PARTICIPACAO" in t:
        return "PARTICIPACAO_FINAL"
    if "OBRIGATORIA" in t or "LEGAL" in t:
        return "SEPARACAO_OBRIGATORIA"
    if "SEPARACAO" in t:
        return "SEPARACAO_TOTAL"
    if "UNIVERSAL" in t:
        return "COMUNHAO_UNIVERSAL"
    if "PARCIAL" in t:
        return "COMUNHAO_PARCIAL"
    return ""


def _tipo_de_casamento(texto: Any) -> str:
    t = _sem_acento(_limpo(texto))
    if "UNIAO" in t or "CONVERS" in t:
        return "CONVERSAO"
    if "RELIG" in t:
        return "RELIGIOSO"
    return "CIVIL" if t else ""


def _endereco_completo(v: dict) -> str:
    partes = [_endereco(v.get("logradouro"), v.get("numero")),
              _capitalizar(_limpo(v.get("bairro")))]
    cidade, uf = _capitalizar(_limpo(v.get("municipio"))), _limpo(v.get("uf")).upper()
    partes.append(f"{cidade}/{uf}" if cidade and uf else cidade)
    return ", ".join(p for p in partes if p)


def juntar_habilitacao(documentos: list[dict]) -> dict:
    """A habilitação de casamento que os documentos permitem abrir. SÓ CALCULA.

    QUEM SÃO OS NUBENTES vem, nesta ordem: do requerimento (que os nomeia e
    traz profissão, nome que passam a usar e regime — nada disso está em
    certidão), das certidões de nascimento (art. 1.525, I: uma de cada) e,
    só se faltar alguém, de um documento de identidade — e então é dedução, e
    vira aviso, porque os documentos da habilitação trazem também os das
    TESTEMUNHAS (inciso III), e uma testemunha não pode entrar como nubente sem
    ninguém conferir.

    O ESTADO CIVIL SAI DO PAPEL QUE O PROVA: certidão de casamento com o
    divórcio averbado faz divorciado; certidão de casamento SEM a averbação é
    impedimento (CC art. 1.521, VI) e vira aviso, nunca «divorciado» por
    dedução. O nome do documento de identidade prevalece, como no óbito."""
    avisos: list[dict] = []
    nubentes: list[dict] = []
    testemunhas: list[dict] = []
    regime = tipo = ""

    def achar(nome: str) -> dict | None:
        p, nota = _a_que_mais_se_parece(nome, nubentes)
        return p if nota >= 0.75 else None

    def preencher(p: dict, **campos: Any) -> None:
        for k, v in campos.items():
            if _valor(v) and not _valor(p.get(k)):
                p[k] = v

    for d in documentos:
        if d["tipo"] != "HABILITACAO":
            continue
        v, onde = d["dados"], f"{d['arquivo']} p{d['n']}"
        _duvidas(avisos, d, {"regime_bens": "Regime de bens"})
        regime = regime or _regime(v.get("regime_bens"))
        tipo = tipo or _tipo_de_casamento(v.get("tipo_casamento"))
        for n in _lista(v.get("nubentes")):
            nome = _limpo(n.get("nome"))
            if not nome:
                continue
            p = achar(nome)
            if p is None:
                p = {"nome": nome, "_onde": onde}
                nubentes.append(p)
            cidade, uf = _uf_e_cidade(n.get("naturalidade"))
            preencher(p, nome_pos=_limpo(n.get("nome_apos_casamento")),
                      sexo=_sexo(n.get("sexo")) if _sexo(n.get("sexo")) in ("M", "F") else "",
                      nascimento=data_iso(n.get("data_nascimento")),
                      documento=so_digitos(n.get("cpf")),
                      estado_civil=_estado_civil_da_habilitacao(n.get("estado_civil")),
                      profissao=_limpo(n.get("profissao")).lower(),
                      nacionalidade=_limpo(n.get("nacionalidade")).lower(),
                      naturalidade_cidade=cidade, naturalidade_uf=uf,
                      endereco=_limpo(n.get("endereco")),
                      pai=_limpo(n.get("pai")), mae=_limpo(n.get("mae")))
            if _sem_acento(_limpo(n.get("estado_civil"))).startswith("SEPAR"):
                _aviso(avisos, "CONFERIR",
                       f"{nome} declara-se separado(a) judicialmente — para casar é "
                       f"preciso o divórcio (CC art. 1.521, VI).", onde)
        for t in _lista(v.get("testemunhas")):
            if _limpo(t.get("nome")):
                testemunhas.append({"nome": _limpo(t.get("nome")),
                                    "documento": so_digitos(t.get("cpf")),
                                    "endereco": _limpo(t.get("endereco")), "_onde": onde})

    casamentos_anteriores = []
    for d in documentos:
        if d["tipo"] != "CERTIDAO":
            continue
        v, onde = d["dados"], f"{d['arquivo']} p{d['n']}"
        especie = _sem_acento(_limpo(v.get("especie")))
        nomes = [_limpo(x) for x in (v.get("nomes") or []) if _limpo(x)] \
            if isinstance(v.get("nomes"), list) else [_limpo(v.get("nomes"))]
        nomes = [n for n in nomes if n]
        if especie.startswith("NASC") and nomes:
            p = achar(nomes[0])
            if p is None:
                if len(nubentes) >= 2:
                    _aviso(avisos, "CONFERIR",
                           f"Há certidão de nascimento de «{nomes[0]}», que não é "
                           f"nenhum dos nubentes.", onde)
                    continue
                p = {"nome": nomes[0], "_onde": onde}
                nubentes.append(p)
            p["_certidao"] = onde
            cidade, uf = _uf_e_cidade(v.get("naturalidade"))
            preencher(p, nascimento=data_iso(v.get("data_nascimento")),
                      sexo=_sexo(v.get("sexo")) if _sexo(v.get("sexo")) in ("M", "F") else "",
                      naturalidade_cidade=cidade, naturalidade_uf=uf,
                      pai=_limpo(v.get("pai")), mae=_limpo(v.get("mae")))
            _duvidas(avisos, d, {"data_nascimento": f"Nascimento de {nomes[0]}"})
        elif especie.startswith("CASA"):
            casamentos_anteriores.append((nomes, _sem_acento(_valor(v.get("averbacoes"))), onde))
        elif especie.startswith("OBIT") and nomes:
            _aviso(avisos, "CONFERIR",
                   f"Há certidão de óbito de «{nomes[0]}» — se é do cônjuge anterior de "
                   f"um dos nubentes, ele(a) é viúvo(a): confirme o estado civil e a "
                   f"causa suspensiva do art. 1.523, I.", onde)

    for nomes, averbacoes, onde in casamentos_anteriores:
        for nome in nomes:
            p = achar(nome)
            if p is None:
                continue
            if "DIVORC" in averbacoes:
                if p.get("estado_civil") in ("", None, "SOLTEIRO"):
                    p["estado_civil"] = "DIVORCIADO"
                p["_dissolucao"] = onde
            else:
                _aviso(avisos, "IMPEDIMENTO",
                       f"Há certidão de casamento de {p['nome']} SEM divórcio averbado — "
                       f"casado(a) não pode casar (CC art. 1.521, VI). Confira se há "
                       f"averbação no verso ou certidão mais nova.", onde)

    ids = _identidades(documentos)
    usados = set()
    for p in nubentes:
        ident, nota = _a_que_mais_se_parece(p["nome"], ids)
        if ident is None or nota < 0.5:
            _aviso(avisos, "CONFERIR",
                   f"Não há documento de identidade de {p['nome']} entre os anexos — "
                   f"o CPF fica para digitar.")
            continue
        usados.add(id(ident))
        nome_id = _limpo(ident.get("nome"))
        if _sem_acento(nome_id) != _sem_acento(p["nome"]):
            _aviso(avisos, "CONFERIR",
                   f"O nome de um nubente difere entre os papéis («{p['nome']}» × "
                   f"«{nome_id}») — vale o do documento de identidade, conferido no "
                   f"original.", ident["_onde"])
            p["nome"] = nome_id
        cpf = so_digitos(ident.get("cpf"))
        if len(cpf) == 11:
            p["documento"] = cpf
        nasc = data_iso(ident.get("data_nascimento"))
        if nasc and p.get("nascimento") and nasc != p["nascimento"]:
            _aviso(avisos, "CONFERIR",
                   f"A data de nascimento de {p['nome']} difere: {p['nascimento']} "
                   f"num papel, {nasc} no documento de identidade.", ident["_onde"])
        cidade, uf = _uf_e_cidade(ident.get("naturalidade"))
        preencher(p, nascimento=nasc,
                  sexo=_sexo(ident.get("sexo")) if _sexo(ident.get("sexo")) in ("M", "F") else "",
                  naturalidade_cidade=cidade, naturalidade_uf=uf,
                  nacionalidade=_limpo(ident.get("nacionalidade")).lower(),
                  pai=_limpo(ident.get("filiacao_pai")), mae=_limpo(ident.get("filiacao_mae")))
    sobra = [i for i in ids if id(i) not in usados]
    while len(nubentes) < 2 and sobra:
        i = sobra.pop(0)
        p = {"nome": _limpo(i.get("nome")), "_onde": i["_onde"],
             "documento": so_digitos(i.get("cpf")) if len(so_digitos(i.get("cpf"))) == 11 else "",
             "nascimento": data_iso(i.get("data_nascimento")),
             "pai": _limpo(i.get("filiacao_pai")), "mae": _limpo(i.get("filiacao_mae"))}
        cidade, uf = _uf_e_cidade(i.get("naturalidade"))
        p.update(naturalidade_cidade=cidade, naturalidade_uf=uf)
        nubentes.append(p)
        _aviso(avisos, "CONFERIR",
               f"«{p['nome']}» entrou como NUBENTE só por ser pessoa identificada nos "
               f"documentos — sem requerimento nem certidão de nascimento dele(a). "
               f"Confirme: pode ser uma testemunha.", i["_onde"])
    for i in sobra:
        if not any(mesmo_nome(_limpo(i.get("nome")), t["nome"]) >= 0.75 for t in testemunhas):
            testemunhas.append({"nome": _limpo(i.get("nome")),
                                "documento": so_digitos(i.get("cpf")), "_onde": i["_onde"]})

    if not nubentes:
        raise LeituraError("Os documentos não dizem quem são os nubentes — sem "
                           "requerimento, certidão de nascimento nem documento de "
                           "identidade lido. Anexe-os ou digite na tela.")
    if len(nubentes) == 1:
        _aviso(avisos, "CONFERIR", "Só um nubente foi identificado — o outro fica "
               "para digitar.")
    if len(nubentes) > 2:
        _aviso(avisos, "CONFERIR", "Os documentos apontam mais de dois nubentes ("
               + "; ".join(p["nome"] for p in nubentes)
               + ") — entraram os dois primeiros; confira.")
        nubentes = nubentes[:2]

    for d in documentos:
        if d["tipo"] != "RESIDENCIA":
            continue
        v = d["dados"]
        nomes = [_limpo(x) for x in (v.get("moradores") or []) if _limpo(x)] \
            if isinstance(v.get("moradores"), list) else []
        nomes.append(_limpo(v.get("declarante")))
        for p in nubentes:
            if not p.get("endereco") and any(mesmo_nome(p["nome"], n) >= 0.75 for n in nomes if n):
                p["endereco"] = _endereco_completo(v)

    hoje = date.today().isoformat()
    pessoas = []
    for i, p in enumerate(nubentes, start=1):
        p["nome"] = _capitalizar(p["nome"])
        for k in ("pai", "mae", "nome_pos"):
            if p.get(k):
                p[k] = _capitalizar(p[k])
        if not p.get("estado_civil"):
            p["estado_civil"] = "SOLTEIRO"
            if not p.get("_certidao"):
                _aviso(avisos, "CONFERIR",
                       f"O estado civil de {p['nome']} não está em nenhum papel — "
                       f"entrou SOLTEIRO; confirme.")
        if p["estado_civil"] in ("DIVORCIADO", "VIUVO") and not p.get("_dissolucao"):
            _aviso(avisos, "CONFERIR",
                   f"{p['nome']} é {p['estado_civil'].lower()}: falta, entre os anexos, "
                   f"a prova da dissolução do casamento anterior (art. 1.525, V).")
        if not p.get("_certidao") and p["estado_civil"] == "SOLTEIRO":
            _aviso(avisos, "CONFERIR",
                   f"Não há certidão de nascimento de {p['nome']} entre os anexos "
                   f"(art. 1.525, I).")
        idade = _idade_em(p["nascimento"], hoje) if p.get("nascimento") else None
        if idade is not None and idade < 16:
            _aviso(avisos, "IMPEDIMENTO", f"{p['nome']} tem {idade} anos — menor de 16 "
                   f"não casa (CC art. 1.520).")
        elif idade is not None and idade < 18:
            _aviso(avisos, "CONFERIR", f"{p['nome']} tem {idade} anos — precisa da "
                   f"autorização dos pais ou representantes (CC art. 1.517).")
        if p.get("documento") and not cpf_valido(p["documento"]):
            _aviso(avisos, "CONFERIR", f"O CPF de {p['nome']} ({p['documento']}) não passa "
                   f"no dígito verificador — confira no documento original.")
        pessoas.append({"papel": f"NUBENTE{i}", "nome": p["nome"],
                        "documento_tipo": "CPF" if p.get("documento") else "",
                        "documento_numero": p.get("documento", ""),
                        "data_nascimento": p.get("nascimento", ""),
                        "naturalidade_cidade": p.get("naturalidade_cidade", ""),
                        "naturalidade_uf": p.get("naturalidade_uf", ""),
                        "endereco": p.get("endereco", "")})
    for t in testemunhas:
        t["nome"] = _capitalizar(t["nome"])
        pessoas.append({"papel": "TESTEMUNHA", "nome": t["nome"],
                        "documento_tipo": "CPF" if len(t.get("documento") or "") == 11 else "",
                        "documento_numero": t.get("documento", ""),
                        "endereco": t.get("endereco", "")})
    if len(testemunhas) < 2:
        _aviso(avisos, "CONFERIR", f"{'Uma testemunha' if testemunhas else 'Nenhuma testemunha'} "
               f"identificada — a habilitação pede a declaração de duas (art. 1.525, III).")

    valores: dict[str, str] = {"tipo": tipo or "CIVIL", "regime": regime}
    for i, p in enumerate(nubentes, start=1):
        for campo in CAMPOS_DO_NUBENTE:
            valores[f"nubente{i}_{campo}"] = _valor(p.get(campo))
    if testemunhas:
        valores["observacao"] = "Testemunhas nos documentos: " + "; ".join(
            t["nome"] + (f" (CPF {t['documento']})" if t.get("documento") else "")
            for t in testemunhas) + "."
    junto = {"valores": valores, "pessoas": pessoas, "conferencia": avisos}
    _naturalidades_nos_valores(junto)
    return junto


def juntar_casamento(documentos: list[dict]) -> dict:
    """O ASSENTO de casamento que os documentos permitem preencher. SÓ CALCULA.

    Quem são os nubentes, o estado civil, a filiação e as testemunhas saem da
    mesma régua da habilitação (`juntar_habilitacao`) — duas réguas para a mesma
    pergunta divergiriam no primeiro conserto. O que muda é a forma: aqui vão os
    papéis do assento (`rc_assento.PREFIXO_DO_PAPEL`), e não os campos da tela
    da habilitação.

    A DATA E O LUGAR DA CELEBRAÇÃO NÃO ESTÃO NOS DOCUMENTOS, e ficam para
    digitar. E se a habilitação foi feita nesta casa, o assento é lavrado por
    ela — é ela que leva o selo que o casamento reaproveita."""
    hab = juntar_habilitacao(documentos)
    v = hab["valores"]
    por_papel = {p["papel"]: p for p in hab["pessoas"]}
    pessoas: list[dict] = []
    nomes = []
    for i in (1, 2):
        nome = v.get(f"nubente{i}_nome") or ""
        if not nome:
            continue
        nomes.append(nome)
        base = por_papel.get(f"NUBENTE{i}", {})
        sexo = v.get(f"nubente{i}_sexo") or ""
        pessoas.append({
            "papel": f"NUBENTE{i}", "nome": nome,
            "nome_pos": v.get(f"nubente{i}_nome_pos") or "",
            "sexo": sexo,
            "documento_tipo": base.get("documento_tipo", ""),
            "documento_numero": base.get("documento_numero", ""),
            "data_nascimento": v.get(f"nubente{i}_nascimento") or "",
            "estado_civil": _estado_civil(v.get(f"nubente{i}_estado_civil"), sexo),
            "profissao": (v.get(f"nubente{i}_profissao") or "").lower(),
            "nacionalidade": v.get(f"nubente{i}_nacionalidade") or "",
            "naturalidade_cidade": base.get("naturalidade_cidade", ""),
            "naturalidade_uf": base.get("naturalidade_uf", ""),
            "endereco": base.get("endereco", ""),
        })
        # A FILIAÇÃO 1 É A MÃE, e a 2 é o pai — a ordem de `PREFIXO_DO_PAPEL`.
        if v.get(f"nubente{i}_mae"):
            pessoas.append({"papel": f"MAE_NUBENTE{i}", "nome": v[f"nubente{i}_mae"], "sexo": "F"})
        if v.get(f"nubente{i}_pai"):
            pessoas.append({"papel": f"PAI_NUBENTE{i}", "nome": v[f"nubente{i}_pai"], "sexo": "M"})
    pessoas += [p for p in hab["pessoas"] if p["papel"] == "TESTEMUNHA"]
    avisos = list(hab["conferencia"])
    _aviso(avisos, "CONFERIR", "A data, a hora e o local da celebração não estão nos "
           "documentos — preencha na tela.")
    _aviso(avisos, "CONFERIR", "Se a habilitação foi feita nesta serventia, lavre o casamento "
           "pela ficha da habilitação: é ela que tem o selo que o assento reaproveita. "
           "Habilitação de outra serventia: informe-a no quadro «Habilitação e regime de bens».")
    if v.get("tipo") in ("RELIGIOSO", "CONVERSAO"):
        _aviso(avisos, "CONFERIR", "O requerimento fala em casamento "
               + ("religioso com efeito civil" if v["tipo"] == "RELIGIOSO"
                  else "por conversão de união estável")
               + " — confira se esta é a tela certa.")
    valores = {"especie": "CASAMENTO", "nome": " e ".join(nomes),
               "regime_bens": v.get("regime") or ""}
    return {"valores": valores, "pessoas": pessoas, "conferencia": avisos}


def _naturalidades_nos_valores(junto: dict) -> None:
    """A naturalidade da tela é um campo só, «Cidade/UF» — refeita das pessoas,
    depois de o município ganhar o nome oficial. ALTERA `junto`."""
    for p in junto.get("pessoas") or []:
        papel = str(p.get("papel") or "")
        if not papel.startswith("NUBENTE"):
            continue
        cidade, uf = p.get("naturalidade_cidade") or "", p.get("naturalidade_uf") or ""
        junto["valores"][f"{papel.lower()}_naturalidade"] = \
            f"{cidade}/{uf}" if cidade and uf else cidade


def _conferir_numeros(avisos: list, v: dict, onde: str, rotulos: dict[str, str]) -> None:
    for chave, rotulo in rotulos.items():
        numero = so_digitos(v.get(chave))
        if numero and not cns_valido(numero):
            _aviso(avisos, "CONFERIR",
                   f"{rotulo} ({numero}): o dígito verificador não fecha — a leitura "
                   f"errou um algarismo, ou o número está errado no documento.", onde)


def _conferir_cpfs(avisos: list, pessoas: list[dict]) -> None:
    for p in pessoas:
        if p.get("documento_tipo") == "CPF" and not cpf_valido(p.get("documento_numero")):
            _aviso(avisos, "CONFERIR",
                   f"O CPF de {p['nome']} ({p['documento_numero']}) não passa no dígito "
                   f"verificador — confira no documento original.")


def _conferir_residencia(avisos: list, documentos: list[dict], mae: dict) -> None:
    for d in documentos:
        if d["tipo"] != "RESIDENCIA":
            continue
        log = _limpo(d["dados"].get("logradouro"))
        if log and mae.get("endereco") and mesmo_nome(log, mae["endereco"]) < 0.5:
            _aviso(avisos, "CONFERIR",
                   f"O endereço da declaração de residência («{log}») não é o da DNV "
                   f"(«{mae['endereco']}»).", f"{d['arquivo']} p{d['n']}")


def municipios_oficiais(con) -> Callable[[str, str], str]:
    """(cidade, UF) → o nome oficial do IBGE, com acento. SÓ LÊ.

    O RG impresso não tem acento («TUCUMA - PA»), e o termo desta casa escreve
    «Tucumã/PA». A tabela dos 5.570 municípios já está no banco (`ib_municipios`);
    o que não se acha nela volta como veio, e nunca é «corrigido» por parecença."""
    try:
        linhas = banco(con).ler("SELECT uf, nome FROM ib_municipios ORDER BY uf, nome")
    except sqlite3.OperationalError:
        linhas = []
    tabela = {(str(m["uf"]).upper(), _sem_acento(m["nome"])): m["nome"] for m in linhas}

    def oficial(cidade: str, uf: str) -> str:
        return tabela.get(((uf or "").upper(), _sem_acento(cidade or "")), cidade)
    return oficial


def corrigir_municipios(junto: dict, oficial: Callable[[str, str], str]) -> None:
    """Põe o nome oficial do município em cada pessoa. ALTERA `junto`."""
    for p in junto.get("pessoas") or []:
        for cidade, uf in (("naturalidade_cidade", "naturalidade_uf"), ("cidade", "uf")):
            if p.get(cidade) and p.get(uf):
                p[cidade] = oficial(p[cidade], p[uf])


JUNTAR: dict[str, Callable[[list[dict]], dict]] = {
    "NASCIMENTO": juntar_nascimento,
    "OBITO": juntar_obito,
    "CASAMENTO": juntar_casamento,
    "HABILITACAO": juntar_habilitacao,
}


def registro_padrao(leitura_id: int, especie: str, junto: dict, de_onde: str) -> str:
    """O registro no ARQUIVO PADRÃO DA CASA, pronto para a fila de
    pré-cadastros. SÓ CALCULA. Campo vazio não vai: vazio no arquivo é
    afirmação de que não há, e aqui só quer dizer que não se leu."""
    import importar_padrao as IMPP
    valores = {k: v for k, v in junto["valores"].items() if _valor(v)}
    pessoas = [{k: v for k, v in p.items() if _valor(v)} for p in junto["pessoas"]]
    registro = {IMPP.CAMPO_DA_CHAVE: f"leitura-{leitura_id}", **valores, "pessoas": pessoas}
    if especie == "HABILITACAO":
        # A HABILITAÇÃO NÃO É ASSENTO, e a fila de pré-cadastros só conhece
        # assento: o registro vai direto para o rascunho da tela dela, com os
        # nomes de campo da própria tela.
        return json.dumps({"tela": TELA_DA_ESPECIE[especie], "origem": de_onde,
                           "registros": [registro]}, ensure_ascii=False)
    return json.dumps({"formato": IMPP.FORMATO, "versao": IMPP.VERSAO,
                       "especie": "RCPN_ASSENTO", "origem": de_onde,
                       "registros": [registro]}, ensure_ascii=False)


# ------------------------------------------------------------- gravar e ler

def abrir(con, *, especie: str, agora: str, por: str = "") -> int:
    """A linha da leitura, ANTES da rede — para os anexos terem a que se
    amarrar. ESCREVE. Situação LENDO até `concluir`."""
    bd = banco(con)
    init_schema(bd)
    especie = (especie or "").upper()
    if especie not in ESPECIES_LIDAS:
        raise LeituraError(f"A leitura de documentos ainda não monta «{especie}». "
                           f"Monta: {', '.join(ESPECIES_LIDAS)}.")
    novo = bd.escrever(
        """INSERT INTO rc_leituras(especie, situacao, arquivos_json, criada_em, criada_por)
           VALUES (%s, 'LENDO', '[]', %s, %s) RETURNING id""", (especie, agora, por))
    return int(novo[0]["id"])


def concluir(con, leitura_id: int, *, arquivos: list[dict],
             lido: dict | None, erro: str = "", tardio: bool = False) -> None:
    """Grava o que a leitura achou — a que deu certo e a que falhou. ESCREVE.

    A que falhou também fica: um dia em que a rede caiu não pode parecer um dia
    em que ninguém leu, e o que já tinha saído para a Anthropic fica dito."""
    bd = banco(con)
    init_schema(bd)
    linha = bd.um("SELECT especie FROM rc_leituras WHERE id = %s", (leitura_id,))
    if not linha:
        raise LeituraError(f"Não há leitura nº {leitura_id}.")
    especie = linha["especie"]
    lido = lido or {}
    envios = lido.get("envios") or []
    total = round(sum(custo(e.get("modelo", ""), e.get("entrada") or 0, e.get("saida") or 0)
                      for e in envios), 4)
    arqs = [{"attachment_id": a.get("attachment_id"), "nome": a["nome"],
             "sha256": a.get("sha256")} for a in arquivos]
    bd.escrever(
        """UPDATE rc_leituras SET situacao=%s, arquivos_json=%s, paginas_json=%s,
               documentos_json=%s, envios_json=%s, custo_estimado=%s, erro=%s WHERE id=%s""",
        ("FALHOU" if erro else "LIDA", json.dumps(arqs, ensure_ascii=False),
         json.dumps(lido.get("paginas") or [], ensure_ascii=False),
         json.dumps(lido.get("documentos") or [], ensure_ascii=False),
         json.dumps(envios, ensure_ascii=False), total, erro or None, leitura_id))
    if not erro:
        try:
            if especie == "NASCIMENTO":
                junto = juntar_nascimento(lido.get("documentos") or [], tardio=tardio)
            else:
                junto = JUNTAR[especie](lido.get("documentos") or [])
            corrigir_municipios(junto, municipios_oficiais(bd))
            if especie == "HABILITACAO":
                _naturalidades_nos_valores(junto)
            texto = registro_padrao(leitura_id, especie, junto, f"leitura de documentos nº {leitura_id}")
            bd.escrever("UPDATE rc_leituras SET registro_json=%s, conferencia_json=%s WHERE id=%s",
                        (texto, json.dumps(junto["conferencia"], ensure_ascii=False), leitura_id))
        except LeituraError as recusa:
            bd.escrever("UPDATE rc_leituras SET situacao='FALHOU', erro=%s WHERE id=%s",
                        (str(recusa), leitura_id))


def _carregar(linha: dict) -> dict:
    d = dict(linha)
    for campo in ("arquivos_json", "paginas_json", "documentos_json", "conferencia_json",
                  "envios_json"):
        d[campo[:-5]] = json.loads(d.get(campo) or "[]")
    registro = json.loads(d.get("registro_json") or "{}")
    d["registro"] = (registro.get("registros") or [{}])[0] if registro else {}
    return d


def uma(con, leitura_id: int) -> dict | None:
    """A leitura inteira, com os campos JSON abertos. SÓ LÊ."""
    bd = banco(con)
    init_schema(bd)
    linha = bd.um("SELECT * FROM rc_leituras WHERE id = %s", (leitura_id,))
    return _carregar(linha) if linha else None


def lista(con, limite: int = 50, *, so_de: tuple[str, int] | None = None) -> list[dict]:
    """As leituras mais recentes. SÓ LÊ.

    `so_de` = (nome, id do usuário): só as que a pessoa abriu — ver `e_de`. É o
    histórico do balcão (M6 do LS03): a leitura traz DNV e DO inteiras, com
    causa da morte e CPF, e o colega de mesa não precisa da de outro."""
    bd = banco(con)
    init_schema(bd)
    if so_de is None:
        return [_carregar(r) for r in bd.ler(
            "SELECT * FROM rc_leituras ORDER BY id DESC LIMIT %s", (limite,))]
    nome, user_id = so_de
    # Nome vazio não casa com nada, como em `e_de` (LX20, observação da
    # revisão do LX13): sem isso, quem não tem nome via toda leitura gravada
    # com `criada_por = ''` — DNV e DO inteiras de outra mesa.
    return [_carregar(r) for r in bd.ler(
        """SELECT * FROM rc_leituras l
            WHERE (%s <> '' AND l.criada_por = %s)
               OR EXISTS (SELECT 1 FROM attachments a WHERE a.entity_type = 'RC_LEITURA'
                             AND a.entity_id = l.id AND a.uploaded_by = %s)
            ORDER BY l.id DESC LIMIT %s""",
        (nome or "", nome or "", int(user_id or 0), limite))]


def e_de(con, leitura: dict, *, nome: str, user_id: int) -> bool:
    """A leitura é de quem está na tela? SÓ LÊ.

    Pelo nome gravado em `criada_por` OU por ter anexado os arquivos dela: o
    nome sozinho é o da assinatura (`usuario_nome`), e duas pessoas podem ter o
    mesmo; o anexo guarda o id de quem enviou."""
    if nome and leitura.get("criada_por") == nome:
        return True
    return bool(banco(con).um(
        """SELECT 1 AS um FROM attachments WHERE entity_type = 'RC_LEITURA'
              AND entity_id = %s AND uploaded_by = %s ORDER BY id LIMIT 1""",
        (int(leitura["id"]), int(user_id or 0))))


def para_rascunho(con, leitura_id: int, *, agora: str,
                  por: str = "") -> int:
    """A leitura vira RASCUNHO da tela de assento novo, pela fila de
    pré-cadastros. ESCREVE — só o rascunho e a marca nesta leitura.

    A fila confere o registro como confere um arquivo vindo de fora: a máquina
    que leu os documentos não tem caminho mais curto até o livro que o de
    qualquer outro arquivo."""
    import importar_padrao as IMPP
    leitura = uma(con, leitura_id)
    if leitura is None:
        raise LeituraError(f"Não há leitura nº {leitura_id}.")
    if leitura["rascunho_id"]:
        return int(leitura["rascunho_id"])
    if not leitura.get("registro_json"):
        raise LeituraError("Esta leitura não montou registro — "
                           + (leitura.get("erro") or "nada foi lido") + ".")
    if leitura["especie"] == "HABILITACAO":
        import rascunho_de_tela as RASC
        RASC.init_rascunho_schema(con)
        reg = dict(leitura["registro"])
        dados = {k: v for k, v in reg.items()
                 if k not in ("pessoas", IMPP.CAMPO_DA_CHAVE)}
        nomes = " e ".join(x for x in (dados.get("nubente1_nome"),
                                        dados.get("nubente2_nome")) if x)
        r = RASC.salvar(con, tela=TELA_DA_ESPECIE["HABILITACAO"], dados=dados,
                        titulo=f"Habilitação — {nomes} (leitura nº {leitura_id})",
                        agora=agora, chave=f"leitura:{leitura_id}", por=por)
        rascunho_id = int(r["id"])
        banco(con).escrever("""UPDATE rc_leituras SET situacao='NO_RASCUNHO', rascunho_id=%s,
                           rascunho_em=%s, rascunho_por=%s WHERE id=%s""",
                    (rascunho_id, agora, por, leitura_id))
        return rascunho_id
    # O TARDIO SEM O NOME DO REGISTRANDO (21/10/2026): o nome vem da
    # entrevista, e não de documento; a fila o dispensa só aqui.
    reg = leitura.get("registro") or {}
    dispensar = (frozenset({"nome"}) if leitura["especie"] == "NASCIMENTO"
                 and str(reg.get("registro_tardio") or "") == "1" else frozenset())
    feito = IMPP.para_rascunhos(con, leitura["registro_json"], agora=agora, por=por,
                                dispensar=dispensar)
    criados = feito.get("criados") or []
    if criados:
        rascunho_id = int(criados[0]["rascunho_id"])
    else:
        linha = banco(con).um("SELECT id FROM rascunhos_de_tela WHERE chave = %s ORDER BY id",
                              (f"arquivo:leitura-{leitura_id}",))
        if not linha:
            motivo = "; ".join(str(r.get("motivo") or r) for r in feito.get("recusados") or [])
            raise LeituraError("A fila de pré-cadastros recusou o registro"
                               + (f": {motivo}" if motivo else "") + ".")
        rascunho_id = int(linha["id"])
    banco(con).escrever("""UPDATE rc_leituras SET situacao='NO_RASCUNHO', rascunho_id=%s,
                       rascunho_em=%s, rascunho_por=%s WHERE id=%s""",
                (rascunho_id, agora, por, leitura_id))
    return rascunho_id


def leitura_do_rascunho(con, rascunho_id: int | None) -> dict | None:
    """A leitura que deu origem a este rascunho, se houve uma. SÓ LÊ.

    É ela que a tela do assento usa para mostrar, ao lado dos campos, o que a
    conferência apontou — e para levar os documentos ao ato quando ele for
    lavrado (12/10/2026: «vamos deixar tudo na página de preenchimento»)."""
    if not rascunho_id:
        return None
    bd = banco(con)
    init_schema(bd)
    linha = bd.um("SELECT * FROM rc_leituras WHERE rascunho_id = %s ORDER BY id DESC",
                  (int(rascunho_id),))
    return _carregar(linha) if linha else None


def ligar_documentos(con, leitura_id: int, entidade: str, entidade_id: int, *,
                     agora: str, por_id: int | None) -> int:
    """Os documentos que a leitura recebeu passam a ser também do ato lavrado
    (`rc_assento`) ou da habilitação aberta. ESCREVE só linhas de `attachments`
    apontando para o MESMO arquivo — nada se copia em disco, nada se apaga da
    leitura. O mesmo arquivo (pelo sha256) não entra duas vezes no mesmo ato.

    Até 12/10/2026 eles ficavam só na leitura: a ficha do assento não os
    mostrava, e quem os procurasse depois teria de saber que houve uma leitura."""
    bd = banco(con)
    ja = {r["sha256"] for r in bd.ler(
        "SELECT sha256 FROM attachments WHERE entity_type=%s AND entity_id=%s ORDER BY id",
        (entidade, int(entidade_id)))}
    feitos = 0
    for a in bd.ler(
            "SELECT original_name, stored_name, stored_path, sha256, size_bytes FROM attachments "
            "WHERE entity_type='RC_LEITURA' AND entity_id=%s ORDER BY id", (int(leitura_id),)):
        if a["sha256"] in ja:
            continue
        bd.escrever(
            "INSERT INTO attachments(entity_type, entity_id, original_name, stored_name, stored_path, sha256, "
            "size_bytes, description, uploaded_by, uploaded_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (entidade, int(entidade_id), a["original_name"], a["stored_name"], a["stored_path"],
             a["sha256"], a["size_bytes"], f"documento da leitura nº {leitura_id}", por_id, agora))
        ja.add(a["sha256"])
        feitos += 1
    return feitos


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")
