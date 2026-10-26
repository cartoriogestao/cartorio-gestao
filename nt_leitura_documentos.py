"""A LEITURA DE DOCUMENTOS NO BALCÃO DAS NOTAS — RG, CIN, CNH e documento de veículo.

    «autorizo ia sem mascara. trabalharemos com o prazo de retencao de 30 dias
     da api» — o oficial, 26/10/2026.

O pedido foi levar ao balcão das Notas o que o Registro Civil já faz com a DNV
e a DO: anexar o documento, a IA lê, e a tela de sempre volta PREENCHIDA, como
rascunho, para quem atende conferir com o original. São três telas:

  - o CARTÃO DE AUTÓGRAFO — do RG, da CIN ou da CNH saem nome, CPF, RG, órgão,
    data de emissão, nascimento, filiação, nacionalidade e título de eleitor;
  - o RECONHECIMENTO DE FIRMA DE VEÍCULO — do CRV ou do ATPV saem o documento,
    a placa e a descrição (RENAVAM, chassi), e o nome de quem vende vai para a
    busca do cartão;
  - a COMUNICAÇÃO DE VENDA AO DETRAN — do CRV, do ATPV e do CRLV saem placa,
    RENAVAM, vendedor, comprador, valor, data e município.

O MOTOR É O DO REGISTRO CIVIL (`leitura_ia`): a mesma triagem pelo modelo
barato, a mesma leitura de cada página pelo modelo certo, o mesmo teto de
páginas, a mesma recusa do simulador do SANDBOX, o mesmo preço. O que é das
Notas mora aqui: os moldes do CRLV, do CRV e do ATPV, a instrução que fala de
tabelionato, e o JUNTAR, que transforma o que se leu nos campos de cada tela.

ESTE MÓDULO NÃO ABRE CARTÃO, NÃO RECONHECE FIRMA, NÃO SELA E NÃO COBRA. Ele
devolve um RASCUNHO. A tela que grava continua sendo a de sempre, com as
recusas de sempre (o RENAVAM sem dígito, o CPF que não fecha, a firma de
veículo por semelhança), e mais uma: quem usa a leitura marca que conferiu os
campos com o documento original, ou a tela não grava (`recusa_sem_conferencia`).

A IA ERRA, E A TELA DIZ ONDE. O que o modelo leu com dúvida volta marcado
(« (?)» no fim do valor), o campo vem destacado na tela, e a conferência
aponta o que não fecha: o RENAVAM sem dígito, o CPF sem dígito, a placa fora
do padrão, o chassi que não tem 17 caracteres, o vendedor que não é o
proprietário do CRLV, duas pessoas diferentes nos documentos de um cartão só.
Não se corrige sozinho: aponta.

O QUE SAI DA CASA, E QUANTO TEMPO FICA LÁ — `BASE_LEGAL`, `O_QUE_SAI`,
`AVISO_DA_RETENCAO`
  - a página inteira, sem máscara, por decisão do oficial em 26/10/2026;
  - a Anthropic guarda pela retenção padrão da API: até 30 dias
    (`leitura_ia.RETENCAO_DIAS`), e o número fica gravado em cada leitura;
  - cada envio fica em `nt_leituras.envios_json` — que arquivo, que página, a
    que modelo, quanto custou —, com quem pediu e quando.
"""
from __future__ import annotations

import json
import re
from typing import Any

import leitura_ia as LIA
from bd_nativo import banco
from leitura_ia import (LeituraError, _duvidoso, _limpo, data_iso, mesmo_nome,
                        so_digitos)

#: As três telas que a leitura preenche, e a frase de cada uma.
DESTINOS: dict[str, str] = {
    "CARTAO": "Cartão de autógrafo",
    "RECONHECIMENTO": "Reconhecimento de firma de veículo",
    "VEICULO": "Comunicação de venda de veículo",
}
#: Os documentos que cada tela espera — vão para a frase da recusa e para a
#: frase do teto de páginas.
O_QUE_ANEXAR: dict[str, str] = {
    "CARTAO": "o RG, a CIN ou a CNH da pessoa",
    "RECONHECIMENTO": "o CRV ou o ATPV, frente e verso",
    "VEICULO": "o CRV ou o ATPV, e o CRLV se houver",
}

#: A DECISÃO, COM A DATA E AS PALAVRAS DELE — a tela a repete ao lado do
#: botão de ler, e a documentação (docs/tecnico/LGPD_LEITURA_DE_DOCUMENTOS.md,
#: parte 3) a transcreve.
DECISAO_DO_OFICIAL = {
    "data": "26/10/2026",
    "texto": "autorizo ia sem mascara. trabalharemos com o prazo de retencao "
             "de 30 dias da api",
}

BASE_LEGAL = (
    "Tratamento para o exercício da atribuição notarial (Lei 13.709/2018, art. 7º, "
    "II e III, e art. 23, § 4º; Lei 8.935/1994, arts. 6º e 7º), com a Anthropic "
    "como operadora. Os documentos vão sem máscara e ficam com a Anthropic pela "
    "retenção padrão da API, de 30 dias — decisão do oficial em 26/10/2026.")
O_QUE_SAI = (
    "Vão à Anthropic as imagens das páginas anexadas: todas na triagem, em tamanho "
    "reduzido, e todas na leitura, inteiras, sem máscara. Nada mais do banco sai "
    "junto.")
AVISO_DA_RETENCAO = (
    f"Os documentos sobem à Anthropic SEM MÁSCARA e ficam lá por até "
    f"{LIA.RETENCAO_DIAS} dias (retenção padrão da API), salvo conteúdo marcado "
    f"por violação da política de uso (até 2 anos) ou obrigação legal; não "
    f"treinam modelos. Decisão do oficial em {DECISAO_DO_OFICIAL['data']}.")

# ----------------------------------------------------------------- os moldes

#: OS MOLDES DO VEÍCULO (26/10/2026). Os nomes dos campos seguem o
#: formulário de cada documento, e as três famílias são as que a casa recebe:
#: o CRLV (o licenciamento, que NÃO transfere — serve para conferir placa,
#: RENAVAM e proprietário), o CRV (o «DUT», com a autorização de
#: transferência preenchida À MÃO no verso) e o ATPV (a autorização de
#: transferência, em papel ou eletrônica). O CRV e o ATPV vão ao modelo forte:
#: são eles que trazem comprador, valor e data escritos por gente.
TIPOS: dict[str, dict[str, Any]] = {
    "IDENTIDADE": LIA.TIPO_IDENTIDADE,
    "CRLV": {
        "nome": "Certificado de Registro e Licenciamento de Veículo (CRLV ou CRLV-e)",
        "manuscrito": False,
        "campos": (
            "placa, renavam, chassi, marca_modelo, ano_fabricacao, ano_modelo, cor, "
            "especie_tipo, combustivel, proprietario_nome, proprietario_cpf_cnpj, "
            "municipio, uf, exercicio, data_emissao"),
    },
    "CRV": {
        "nome": ("Certificado de Registro de Veículo (CRV, o «DUT»), frente e o "
                 "verso com a autorização para transferência"),
        "manuscrito": True,
        "campos": (
            "numero_crv, placa, renavam, chassi, marca_modelo, ano_fabricacao, "
            "ano_modelo, cor, proprietario_nome, proprietario_cpf_cnpj, municipio, "
            "uf, data_emissao; e, do verso, comprador_nome, comprador_cpf_cnpj, "
            "comprador_endereco, comprador_municipio, comprador_uf, valor_venda, "
            "data_venda, local_venda"),
    },
    "ATPV": {
        "nome": ("Autorização para Transferência de Propriedade de Veículo (ATPV, em "
                 "papel, ou ATPV-e, a eletrônica)"),
        "manuscrito": True,
        "campos": (
            "eletronica (sim se for ATPV-e, não se for o formulário em papel), "
            "numero_atpv, placa, renavam, chassi, marca_modelo, ano_fabricacao, "
            "ano_modelo, cor, municipio, uf, vendedor_nome, vendedor_cpf_cnpj, "
            "comprador_nome, comprador_cpf_cnpj, comprador_endereco, "
            "comprador_municipio, comprador_uf, valor_venda, data_venda"),
    },
    "OUTRO": LIA.TIPO_OUTRO,
}

INSTRUCAO_TRIAGEM = (
    "Você classifica páginas de documentos entregues no balcão de um tabelionato de "
    "notas brasileiro. As páginas vêm numeradas na ordem. Para cada uma, diga o "
    "tipo, escolhendo exatamente um destes códigos: IDENTIDADE (RG, CIN, CNH ou "
    "cartão do CPF — mesmo dois numa página), CRLV (Certificado de Registro e "
    "Licenciamento de Veículo, inclusive o CRLV-e impresso), CRV (Certificado de "
    "Registro de Veículo, o «DUT», frente ou verso com a autorização para "
    "transferência), ATPV (Autorização para Transferência de Propriedade de "
    "Veículo, em papel ou a ATPV-e), OUTRO. "
    "Responda SÓ com JSON: {\"paginas\": [{\"n\": 1, \"tipo\": \"IDENTIDADE\"}, ...]}.")

INSTRUCAO_LEITURA = (
    "Você transcreve documentos para o balcão de um tabelionato de notas brasileiro. "
    "Leia o documento da imagem ({nome}) e devolva SÓ um JSON, sem texto em volta, "
    "com estas chaves: {campos}. Datas em DD/MM/AAAA. Campo em branco ou ausente = "
    "null. Nas caixas de marcar, devolva o texto da opção marcada. Se a letra for "
    "duvidosa, transcreva o mais provável e acrescente ' (?)' no fim do valor. "
    "TUDO o que estiver preenchido no documento precisa voltar: o que não couber "
    "nas chaves pedidas vai em \"outros_campos\", um objeto com o rótulo do "
    "documento como chave. Não invente: o que não está escrito é null.")


# ----------------------------------------------------------------- o esquema

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS nt_leituras (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    destino TEXT NOT NULL,                   -- CARTAO | RECONHECIMENTO | VEICULO
    situacao TEXT NOT NULL DEFAULT 'LENDO',  -- LENDO | LIDA | FALHOU | USADA
    arquivos_json TEXT NOT NULL DEFAULT '[]',
    paginas_json TEXT,                       -- triagem: [{arquivo, n, tipo}]
    documentos_json TEXT,                    -- o que cada página disse
    sugestao_json TEXT,                      -- os campos da tela (RASCUNHO)
    conferencia_json TEXT,                   -- o que não fecha, e onde
    envios_json TEXT,                        -- o que saiu, a que modelo, quanto
    custo_estimado double precision,
    sem_mascara integer NOT NULL DEFAULT 1,  -- decisão do oficial, 26/10/2026
    retencao_dias integer NOT NULL DEFAULT 30,
    erro TEXT,
    criada_em TEXT NOT NULL,
    criada_por TEXT,
    criada_por_id bigint,
    usada_tabela TEXT,                       -- onde a leitura entrou, conferida
    usada_id bigint,
    usada_em TEXT,
    usada_por TEXT
)""",
    "CREATE INDEX IF NOT EXISTS ix_nt_leituras_quem ON nt_leituras(criada_por_id, id)",
)


def init_nt_leitura_schema(con) -> None:
    """Cria a tabela, se faltar. Idempotente — roda em toda subida."""
    bd = banco(con)
    for comando in SCHEMA:
        bd.escrever(comando)


# ------------------------------------------------------------------- a rede

def ler(conversar, pasta, modelos_em_uso: dict, arquivos: list[dict], *,
        destino: str) -> dict:
    """Triar e ler os anexos com os moldes das Notas. FALA COM A REDE — e por
    isso NÃO RECEBE `con`. Acima do teto de páginas recusa ANTES de qualquer
    chamada: nada sobe. Devolve {paginas, documentos, envios}."""
    paginas = LIA.paginas_dos_arquivos(arquivos, o_que_anexar=O_QUE_ANEXAR.get(destino, ""))
    if len(paginas) > LIA.MAXIMO_DE_PAGINAS:
        raise LeituraError(
            f"Os anexos somam {len(paginas)} páginas, acima do teto de "
            f"{LIA.MAXIMO_DE_PAGINAS} por leitura — nada foi enviado à IA. Anexe só "
            f"{O_QUE_ANEXAR.get(destino, 'os documentos deste ato')}.")
    lido = LIA.ler_paginas(conversar, pasta, modelos_em_uso, paginas, tipos=TIPOS,
                           instrucao_triagem=INSTRUCAO_TRIAGEM,
                           instrucao_leitura=INSTRUCAO_LEITURA)
    return {"paginas": LIA.paginas_para_gravar(paginas, lido["tipos"]),
            "documentos": lido["documentos"], "envios": lido["envios"]}


# --------------------------------------------------------- juntar (sem rede)

def _aviso(lista: list, gravidade: str, texto: str, onde: str = "") -> None:
    lista.append({"gravidade": gravidade, "texto": texto, "onde": onde})


def _onde(doc: dict) -> str:
    return f"{doc['arquivo']} p{doc['n']}"


def _pegar(campos: dict, duvidas: set, de_onde: dict, campo: str, valor: Any,
           onde: str, limpo: str | None = None) -> None:
    """Põe o valor no campo da tela se ele ainda está vazio, lembrando de onde
    veio e se a leitura ficou em dúvida. SÓ CALCULA."""
    texto = limpo if limpo is not None else _limpo(valor)
    if not texto or campos.get(campo):
        return
    campos[campo] = texto
    de_onde[campo] = onde
    if _duvidoso(valor):
        duvidas.add(campo)


def _identidades(documentos: list[dict]) -> list[dict]:
    """Cada documento de identidade lido, com o arquivo e a página. SÓ CALCULA.
    A página pode trazer dois documentos (a lista `pessoas`) ou um só."""
    saida = []
    for d in documentos:
        if d.get("tipo") != "IDENTIDADE":
            continue
        dados = d.get("dados") or {}
        pessoas = dados.get("pessoas") if isinstance(dados.get("pessoas"), list) else [dados]
        for p in pessoas:
            if isinstance(p, dict) and _limpo(p.get("nome")):
                saida.append({**p, "_onde": _onde(d)})
    return saida


def _mesma_pessoa(a: dict, b: dict) -> bool:
    ca, cb = so_digitos(a.get("cpf")), so_digitos(b.get("cpf"))
    if ca and cb:
        return ca == cb
    return mesmo_nome(_limpo(a.get("nome")), _limpo(b.get("nome"))) >= 0.6


#: Os campos do cartão que a leitura preenche, e a ordem de quem manda: o RG
#: e a CIN trazem órgão e data de emissão da IDENTIDADE; a da CNH é a da
#: habilitação, e não vai para «Emissão do RG».
ROTULOS_DO_CARTAO = {
    "nome": "Nome", "documento": "CPF", "rg": "RG", "rg_orgao": "Órgão emissor",
    "rg_emissao": "Emissão do RG", "nascimento": "Nascimento",
    "titulo_eleitor": "Título eleitoral", "nacionalidade": "Nacionalidade",
    "pai": "Pai", "mae": "Mãe",
}


def juntar_cartao(documentos: list[dict]) -> dict:
    """Os documentos de identidade viram os campos do CARTÃO DE AUTÓGRAFO.
    SÓ CALCULA. Devolve {campos, duvidas, de_onde, conferencia, lidos}.

    O CARTÃO É DE UMA PESSOA SÓ: documentos de duas pessoas (o RG do vendedor
    e o do comprador na mesma digitalização) não se misturam — vale a primeira,
    e a conferência diz quem ficou de fora."""
    ids = _identidades(documentos)
    if not ids:
        raise LeituraError("A leitura não achou documento de identidade (RG, CIN ou CNH) "
                           "nos anexos — confira se a página está legível e anexe de novo.")
    avisos: list[dict] = []
    grupo = [ids[0]] + [p for p in ids[1:] if _mesma_pessoa(ids[0], p)]
    fora = [p for p in ids if p not in grupo]
    if fora:
        _aviso(avisos, "CONFERIR",
               "Os anexos trazem documentos de mais de uma pessoa ("
               + "; ".join(sorted({_limpo(p.get("nome")) for p in fora}))
               + f"). O cartão é de uma pessoa só: os campos vieram de "
               f"{_limpo(ids[0].get('nome'))}.")
    # O RG E A CIN PRIMEIRO: são eles que dão órgão e emissão da identidade.
    def ordem(p: dict) -> int:
        return 0 if _limpo(p.get("tipo_documento")).upper() in ("RG", "CIN") else 1
    grupo.sort(key=ordem)
    campos: dict[str, str] = {"tipo_pessoa": "F"}
    duvidas: set[str] = set()
    de_onde: dict[str, str] = {}
    for p in grupo:
        onde, tipo = p["_onde"], _limpo(p.get("tipo_documento")).upper()
        _pegar(campos, duvidas, de_onde, "nome", p.get("nome"), onde)
        cpf = so_digitos(p.get("cpf"))
        _pegar(campos, duvidas, de_onde, "documento", p.get("cpf"), onde, cpf)
        if tipo != "CNH" or not campos.get("rg"):
            _pegar(campos, duvidas, de_onde, "rg", p.get("numero_documento"), onde)
            _pegar(campos, duvidas, de_onde, "rg_orgao", p.get("orgao_emissor"), onde)
        if tipo in ("RG", "CIN"):
            _pegar(campos, duvidas, de_onde, "rg_emissao", p.get("data_expedicao"), onde,
                   data_iso(p.get("data_expedicao")))
        _pegar(campos, duvidas, de_onde, "nascimento", p.get("data_nascimento"), onde,
               data_iso(p.get("data_nascimento")))
        _pegar(campos, duvidas, de_onde, "titulo_eleitor", p.get("titulo_eleitor"), onde,
               so_digitos(p.get("titulo_eleitor")))
        _pegar(campos, duvidas, de_onde, "nacionalidade", p.get("nacionalidade"), onde,
               _limpo(p.get("nacionalidade")).upper())
        _pegar(campos, duvidas, de_onde, "pai", p.get("filiacao_pai"), onde)
        _pegar(campos, duvidas, de_onde, "mae", p.get("filiacao_mae"), onde)
    # O QUE NÃO FECHA ENTRE OS DOCUMENTOS DA MESMA PESSOA.
    for p in grupo[1:]:
        cpf = so_digitos(p.get("cpf"))
        if cpf and campos.get("documento") and cpf != campos["documento"]:
            _aviso(avisos, "CONFERIR", f"O CPF difere entre os documentos: "
                   f"{campos['documento']} e {cpf}.", p["_onde"])
        nasc = data_iso(p.get("data_nascimento"))
        if nasc and campos.get("nascimento") and nasc != campos["nascimento"]:
            _aviso(avisos, "CONFERIR", "A data de nascimento difere entre os documentos.",
                   p["_onde"])
        nome = _limpo(p.get("nome"))
        if nome and nome.upper() != (campos.get("nome") or "").upper():
            _aviso(avisos, "CONFERIR", f"O nome não é igual letra a letra nos documentos: "
                   f"«{campos.get('nome')}» e «{nome}».", p["_onde"])
    if campos.get("documento") and not LIA.cpf_valido(campos["documento"]):
        _aviso(avisos, "CONFERIR", f"O CPF lido ({campos['documento']}) não fecha o dígito "
               "verificador — confira no documento.", de_onde.get("documento", ""))
    if campos.get("documento") and len(campos["documento"]) != 11:
        _aviso(avisos, "CONFERIR", "O CPF lido não tem onze dígitos.",
               de_onde.get("documento", ""))
    if not campos.get("documento"):
        _aviso(avisos, "CONFERIR", "A leitura não achou CPF nos documentos.")
    for campo in sorted(duvidas):
        _aviso(avisos, "CONFERIR", f"{ROTULOS_DO_CARTAO.get(campo, campo)}: a leitura "
               f"ficou em dúvida — confira no documento.", de_onde.get(campo, ""))
    return {"campos": campos, "duvidas": sorted(duvidas), "de_onde": de_onde,
            "conferencia": avisos}


#: O veículo tem documento de TRANSFERÊNCIA (CRV, ATPV) e de LICENCIAMENTO
#: (CRLV). A transferência manda; o CRLV completa e confere.
ORDEM_DOS_DOCUMENTOS_DO_VEICULO = ("ATPV", "CRV", "CRLV")
ROTULOS_DO_VEICULO = {
    "placa": "Placa", "renavam": "RENAVAM", "chassi": "Chassi",
    "marca_modelo": "Marca/modelo", "ano_fabricacao": "Ano de fabricação",
    "ano_modelo": "Ano do modelo", "cor": "Cor", "proprietario_nome": "Proprietário",
    "proprietario_documento": "CPF/CNPJ do proprietário", "municipio": "Município",
    "uf": "UF", "vendedor_nome": "Vendedor", "vendedor_documento": "CPF/CNPJ do vendedor",
    "comprador_nome": "Comprador", "comprador_documento": "CPF/CNPJ do comprador",
    "valor": "Valor da venda", "data_venda": "Data da venda",
}
CHASSI = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def renavam_onze(valor: Any) -> str:
    """O RENAVAM em onze dígitos — o antigo, de nove, ganha dois zeros. SÓ
    CALCULA. A conferência do dígito é a de `nt_veiculo_detran.renavam_valido`,
    a mesma que a tela de comunicação aplica ao gravar."""
    d = so_digitos(valor)
    return "00" + d if len(d) == 9 else d


def _valor_em_reais(valor: Any) -> str:
    """«R$ 25.000,00» → «25.000,00», que é como a tela de comunicação pede.
    Número sem vírgula fica como veio. SÓ CALCULA."""
    texto = _limpo(valor).replace("R$", "").strip()
    return texto if re.fullmatch(r"[\d.]+(,\d{1,2})?", texto or "-") else ""


def juntar_veiculo(documentos: list[dict]) -> dict:
    """O CRV, o ATPV e o CRLV viram os dados do VEÍCULO e da venda. SÓ
    CALCULA. Devolve {valores, transferencia, duvidas, de_onde, conferencia}.

    O RENAVAM SE CONFERE PELO DÍGITO — a mesma regra que a comunicação ao
    DETRAN aplica ao gravar (`nt_veiculo_detran.renavam_valido`). Aqui ele
    entra assim mesmo, com o aviso: quem confere com o documento corrige o
    dígito; apagar o número faria digitar os onze de novo."""
    import cpf_cnpj as CPFDOC
    import nt_veiculo_detran as DET
    por_tipo = {t: [d for d in documentos if d.get("tipo") == t]
                for t in ORDEM_DOS_DOCUMENTOS_DO_VEICULO}
    lidos = [d for t in ORDEM_DOS_DOCUMENTOS_DO_VEICULO for d in por_tipo[t]]
    if not lidos:
        raise LeituraError("A leitura não achou documento de veículo (CRV, ATPV ou CRLV) "
                           "nos anexos — confira se a página está legível e anexe de novo.")
    avisos: list[dict] = []
    valores: dict[str, str] = {}
    duvidas: set[str] = set()
    de_onde: dict[str, str] = {}
    transferencia = ""
    if por_tipo["ATPV"]:
        eletronica = _limpo(por_tipo["ATPV"][0]["dados"].get("eletronica")).upper()
        transferencia = "ATPV_E" if eletronica.startswith("S") else "ATPV"
    elif por_tipo["CRV"]:
        transferencia = "CRV"
    else:
        _aviso(avisos, "CONFERIR", "Só veio o CRLV: ele é o licenciamento, e não transfere. "
               "A firma da venda se reconhece no CRV ou no ATPV — anexe-o.")
    for d in lidos:
        v, onde, tipo = d.get("dados") or {}, _onde(d), d["tipo"]
        def pega(campo, valor, limpo=None, onde=onde):
            _pegar(valores, duvidas, de_onde, campo, valor, onde, limpo)
        pega("placa", v.get("placa"), DET.placa_normal(_limpo(v.get("placa"))))
        pega("renavam", v.get("renavam"), renavam_onze(v.get("renavam")))
        pega("chassi", v.get("chassi"), re.sub(r"[^A-Z0-9]", "", _limpo(v.get("chassi")).upper()))
        for campo in ("marca_modelo", "ano_fabricacao", "ano_modelo", "cor"):
            pega(campo, v.get(campo))
        pega("municipio", v.get("municipio"))
        pega("uf", v.get("uf"), _limpo(v.get("uf")).upper()[:2])
        if tipo in ("CRV", "CRLV"):
            pega("proprietario_nome", v.get("proprietario_nome"))
            pega("proprietario_documento", v.get("proprietario_cpf_cnpj"),
                 so_digitos(v.get("proprietario_cpf_cnpj")))
        if tipo == "ATPV":
            pega("vendedor_nome", v.get("vendedor_nome"))
            pega("vendedor_documento", v.get("vendedor_cpf_cnpj"),
                 so_digitos(v.get("vendedor_cpf_cnpj")))
        if tipo in ("ATPV", "CRV"):
            pega("comprador_nome", v.get("comprador_nome"))
            pega("comprador_documento", v.get("comprador_cpf_cnpj"),
                 so_digitos(v.get("comprador_cpf_cnpj")))
            pega("valor", v.get("valor_venda"), _valor_em_reais(v.get("valor_venda")))
            pega("data_venda", v.get("data_venda"), data_iso(v.get("data_venda")))
        # O MESMO VEÍCULO EM TODOS OS DOCUMENTOS — placa, RENAVAM e chassi.
        for campo, conta in (("placa", DET.placa_normal), ("renavam", renavam_onze),
                             ("chassi", lambda x: re.sub(r"[^A-Z0-9]", "", str(x).upper()))):
            lido = conta(_limpo(v.get(campo)))
            if lido and valores.get(campo) and lido != valores[campo]:
                _aviso(avisos, "CONFERIR", f"{ROTULOS_DO_VEICULO[campo]} difere entre os "
                       f"documentos: {valores[campo]} e {lido}.", onde)
    # NO CRV, QUEM VENDE É O PROPRIETÁRIO — é ele quem assina a autorização.
    if not valores.get("vendedor_nome") and transferencia == "CRV":
        for campo in ("nome", "documento"):
            if valores.get(f"proprietario_{campo}"):
                valores[f"vendedor_{campo}"] = valores[f"proprietario_{campo}"]
                de_onde[f"vendedor_{campo}"] = de_onde.get(f"proprietario_{campo}", "")
                if f"proprietario_{campo}" in duvidas:
                    duvidas.add(f"vendedor_{campo}")
    elif (valores.get("vendedor_nome") and valores.get("proprietario_nome")
          and mesmo_nome(valores["vendedor_nome"], valores["proprietario_nome"]) < 0.6):
        _aviso(avisos, "CONFERIR", f"Quem vende no ATPV ({valores['vendedor_nome']}) não é "
               f"o proprietário no CRV/CRLV ({valores['proprietario_nome']}) — confira "
               "quem assina a venda.")
    # O QUE A TELA RECUSARIA AO GRAVAR, DITO ANTES.
    if valores.get("placa") and not DET.PLACA.match(valores["placa"]):
        _aviso(avisos, "CONFERIR", f"A placa lida ({valores['placa']}) não está no padrão "
               "ABC1234 nem ABC1D23.", de_onde.get("placa", ""))
    if valores.get("renavam") and not DET.renavam_valido(valores["renavam"]):
        _aviso(avisos, "CONFERIR", f"O RENAVAM lido ({valores['renavam']}) não fecha o "
               "dígito verificador — confira os onze dígitos no documento.",
               de_onde.get("renavam", ""))
    if valores.get("chassi") and not CHASSI.match(valores["chassi"]):
        _aviso(avisos, "CONFERIR", f"O chassi lido ({valores['chassi']}) não tem 17 "
               "caracteres válidos (sem I, O e Q).", de_onde.get("chassi", ""))
    for campo in ("proprietario_documento", "vendedor_documento", "comprador_documento"):
        doc = valores.get(campo)
        if doc and CPFDOC.documento_valido(doc) is not True:
            _aviso(avisos, "CONFERIR", f"{ROTULOS_DO_VEICULO[campo]}: "
                   f"{CPFDOC.mensagem_documento_invalido(doc)}", de_onde.get(campo, ""))
    if (valores.get("vendedor_documento") and valores.get("comprador_documento")
            and valores["vendedor_documento"] == valores["comprador_documento"]):
        _aviso(avisos, "CONFERIR", "Vendedor e comprador com o mesmo documento.")
    for campo in sorted(duvidas):
        _aviso(avisos, "CONFERIR", f"{ROTULOS_DO_VEICULO.get(campo, campo)}: a leitura "
               "ficou em dúvida — confira no documento.", de_onde.get(campo, ""))
    return {"valores": valores, "transferencia": transferencia,
            "duvidas": sorted(duvidas), "de_onde": de_onde, "conferencia": avisos}


def campos_do_reconhecimento(junto: dict) -> dict:
    """Os campos da tela de RECONHECIMENTO DE FIRMA a partir do veículo lido.
    SÓ CALCULA. A espécie vem AUTENTICIDADE porque é a única que serve à
    transferência (CN-MA art. 865, II) — e a tela continua recusando a outra.
    `busca` é o nome de quem vende, para achar o cartão dele."""
    v = junto["valores"]
    qual = {"ATPV": "ATPV", "ATPV_E": "ATPV", "CRV": "CRV"}.get(junto["transferencia"], "")
    descricao = ", ".join(x for x in (
        {"ATPV": "ATPV", "ATPV_E": "ATPV-e", "CRV": "CRV"}.get(junto["transferencia"], ""),
        v.get("marca_modelo") and f"veículo {v['marca_modelo']}",
        v.get("placa") and f"placa {v['placa']}",
        v.get("renavam") and f"RENAVAM {v['renavam']}",
        v.get("chassi") and f"chassi {v['chassi']}") if x)
    campos = {"veiculo": "1", "especie": "AUTENTICIDADE", "veiculo_documento": qual,
              "veiculo_placa": v.get("placa", ""), "documento_descricao": descricao,
              "busca": v.get("vendedor_nome", "")}
    duvidas = {"placa": "veiculo_placa", "vendedor_nome": "busca"}
    return {"campos": {k: x for k, x in campos.items() if x},
            "duvidas": sorted({duvidas[d] for d in junto["duvidas"] if d in duvidas}
                              | ({"documento_descricao"} if set(junto["duvidas"])
                                 & {"renavam", "chassi", "marca_modelo"} else set()))}


#: Da leitura do veículo para os campos da COMUNICAÇÃO DE VENDA — os nomes
#: são os do formulário de `notas_veiculos.html`.
CAMPOS_DA_COMUNICACAO = ("placa", "renavam", "data_venda", "vendedor_nome",
                         "vendedor_documento", "comprador_nome", "comprador_documento",
                         "valor", "municipio", "uf")


def campos_da_comunicacao(junto: dict) -> dict:
    """Os campos da tela de COMUNICAÇÃO DE VENDA a partir do veículo lido.
    SÓ CALCULA."""
    v = junto["valores"]
    campos = {c: v[c] for c in CAMPOS_DA_COMUNICACAO if v.get(c)}
    if junto["transferencia"]:
        campos["documento"] = junto["transferencia"]
    return {"campos": campos,
            "duvidas": [d for d in junto["duvidas"] if d in CAMPOS_DA_COMUNICACAO]}


def sugestao(destino: str, documentos: list[dict]) -> dict:
    """O RASCUNHO da tela: {campos, duvidas, de_onde, conferencia, lido}.
    SÓ CALCULA. `lido` é o que se leu do veículo inteiro (chassi, cor, ano),
    que a tela mostra embora não tenha campo para tudo."""
    if destino == "CARTAO":
        junto = juntar_cartao(documentos)
        return {**junto, "lido": junto["campos"]}
    junto = juntar_veiculo(documentos)
    tela = (campos_do_reconhecimento(junto) if destino == "RECONHECIMENTO"
            else campos_da_comunicacao(junto))
    return {"campos": tela["campos"], "duvidas": tela["duvidas"],
            "de_onde": junto["de_onde"], "conferencia": junto["conferencia"],
            "lido": junto["valores"]}


# ------------------------------------------------------------- gravar e ler

def abrir(con, *, destino: str, agora: str, por: str = "", por_id: int | None = None) -> int:
    """A linha da leitura, ANTES da rede — para os anexos terem a que se
    amarrar. ESCREVE. Situação LENDO até `concluir`. A retenção de 30 dias e o
    «sem máscara» entram aqui, na linha, e não só na tela."""
    destino = (destino or "").upper()
    if destino not in DESTINOS:
        raise LeituraError("A leitura de documentos das Notas preenche o cartão de "
                           "autógrafo, o reconhecimento de firma de veículo e a "
                           "comunicação de venda de veículo.")
    novo = banco(con).escrever(
        """INSERT INTO nt_leituras(destino, situacao, arquivos_json, sem_mascara,
               retencao_dias, criada_em, criada_por, criada_por_id)
           VALUES (%s, 'LENDO', '[]', 1, %s, %s, %s, %s) RETURNING id""",
        (destino, LIA.RETENCAO_DIAS, agora, por or None, int(por_id or 0) or None))
    return int(novo[0]["id"])


def concluir(con, leitura_id: int, *, arquivos: list[dict], lido: dict | None,
             erro: str = "") -> None:
    """Grava o que a leitura achou — a que deu certo e a que falhou. ESCREVE.

    A que falhou também fica: o que já tinha saído para a Anthropic fica dito,
    e um dia em que a rede caiu não pode parecer um dia em que ninguém leu."""
    bd = banco(con)
    linha = bd.um("SELECT destino FROM nt_leituras WHERE id = %s", (int(leitura_id),))
    if not linha:
        raise LeituraError(f"Não há leitura nº {leitura_id}.")
    lido = lido or {}
    envios = lido.get("envios") or []
    arqs = [{"attachment_id": a.get("attachment_id"), "nome": a["nome"],
             "sha256": a.get("sha256")} for a in arquivos]
    texto_sugestao, conferencia = None, None
    if not erro:
        try:
            feita = sugestao(linha["destino"], lido.get("documentos") or [])
            conferencia = json.dumps(feita.pop("conferencia"), ensure_ascii=False)
            texto_sugestao = json.dumps(feita, ensure_ascii=False)
        except LeituraError as recusa:
            erro = str(recusa)
    bd.escrever(
        """UPDATE nt_leituras SET situacao=%s, arquivos_json=%s, paginas_json=%s,
               documentos_json=%s, sugestao_json=%s, conferencia_json=%s,
               envios_json=%s, custo_estimado=%s, erro=%s WHERE id=%s""",
        ("FALHOU" if erro else "LIDA", json.dumps(arqs, ensure_ascii=False),
         json.dumps(lido.get("paginas") or [], ensure_ascii=False),
         json.dumps(lido.get("documentos") or [], ensure_ascii=False),
         texto_sugestao, conferencia, json.dumps(envios, ensure_ascii=False),
         LIA.custo_dos_envios(envios), erro or None, int(leitura_id)))


def _carregar(linha: dict) -> dict:
    d = dict(linha)
    for campo in ("arquivos_json", "paginas_json", "documentos_json", "conferencia_json",
                  "envios_json"):
        d[campo[:-5]] = json.loads(d.get(campo) or "[]")
    d["sugestao"] = json.loads(d.get("sugestao_json") or "{}")
    return d


def uma(con, leitura_id: Any) -> dict | None:
    """A leitura inteira, com os campos JSON abertos. SÓ LÊ. O número vem da
    tela: o que não é número é a leitura que não existe."""
    texto = str(leitura_id or "").strip()
    if not texto.isdigit() or len(texto) > 18:
        return None
    linha = banco(con).um("SELECT * FROM nt_leituras WHERE id = %s", (int(texto),))
    return _carregar(linha) if linha else None


def e_de(leitura: dict, *, user_id: int | None) -> bool:
    """A leitura é de quem está na tela? SÓ CALCULA. Pelo id de quem pediu —
    o nome sozinho é o da assinatura, e duas pessoas podem ter o mesmo."""
    return bool(user_id) and int(leitura.get("criada_por_id") or 0) == int(user_id)


def para_a_tela(con, leitura_id: Any, *, destino: str, user_id: int | None,
                ve_todas: bool) -> dict | None:
    """A leitura que a tela pediu pelo endereço (`?leitura_id=`), se ela é
    deste destino, deu certo e é de quem está na tela (ou quem vê é ADMIN ou
    MANAGER). SÓ LÊ. A de outra mesa responde como a que não existe: o
    documento é de outra pessoa."""
    leitura = uma(con, leitura_id)
    if (leitura is None or leitura["destino"] != destino
            or leitura["situacao"] not in ("LIDA", "USADA")
            or not (ve_todas or e_de(leitura, user_id=user_id))):
        return None
    return leitura


def lista(con, limite: int = 50, *, so_de: int | None = None) -> list[dict]:
    """As leituras mais recentes — todas, ou só as que a pessoa pediu. SÓ LÊ."""
    bd = banco(con)
    if so_de is None:
        linhas = bd.ler("SELECT * FROM nt_leituras ORDER BY id DESC LIMIT %s", (limite,))
    else:
        linhas = bd.ler("SELECT * FROM nt_leituras WHERE criada_por_id = %s "
                        "ORDER BY id DESC LIMIT %s", (int(so_de or 0), limite))
    return [_carregar(r) for r in linhas]


#: A FRASE DA CONFERÊNCIA — a caixa que a tela mostra quando o formulário veio
#: da leitura, e que a rota cobra.
FRASE_DA_CONFERENCIA = ("Conferi cada campo preenchido pela leitura com o documento "
                        "original apresentado")


def recusa_sem_conferencia(leitura_id: Any, conferi: Any) -> str | None:
    """Quando o formulário veio da leitura, quem atende tem de marcar que
    conferiu com o original — senão a frase da recusa. SÓ CALCULA. Sem
    leitura, não há o que cobrar: a tela é a de sempre."""
    if not str(leitura_id or "").strip():
        return None
    if str(conferi or "").strip() in ("1", "on", "SIM", "sim"):
        return None
    return ("Os campos vieram da leitura por IA e ainda não foram conferidos. "
            "Compare cada um com o documento original, corrija o que for preciso e "
            f"marque «{FRASE_DA_CONFERENCIA}» — a leitura adianta a digitação, e não "
            "decide nada.")


def marcar_usada(con, leitura_id: Any, *, tabela: str, ato_id: int, agora: str,
                 por: str = "") -> None:
    """A leitura entrou num cartão, num reconhecimento ou numa comunicação,
    conferida por quem gravou. ESCREVE só a marca nesta leitura."""
    texto = str(leitura_id or "").strip()
    if not texto.isdigit():
        return
    banco(con).escrever(
        """UPDATE nt_leituras SET situacao='USADA', usada_tabela=%s, usada_id=%s,
               usada_em=%s, usada_por=%s WHERE id=%s AND situacao IN ('LIDA', 'USADA')""",
        (tabela, int(ato_id), agora, por or None, int(texto)))

