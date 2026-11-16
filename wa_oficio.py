"""O ofício que o WhatsApp conhece de cor: o que o cartório faz e como o escrevente trabalha.

Decisão do oficial em 10/11/2026: o atendimento do WhatsApp responde com
linguagem natural, sem uma pessoa na conversa, e quando o cliente quer o
serviço feito deixa o trabalho para o escrevente. Este módulo é a parte que
não depende de busca: o fluxo do balcão e a lista de serviços. Não tem número
de lei, de prazo nem de valor — número só entra pelo texto-base da casa ou
pelo artigo que a base normativa devolveu naquela pergunta (`wa_conhecimento`).

A IA não lavra, não sela, não qualifica e não recusa. Isso continua sendo do
delegatário, ou de quem ele autorizou (regras da casa, seção 1).
"""
from __future__ import annotations

# id, setor de destino, nome que o escrevente lê, quando a IA escolhe este serviço.
SERVICOS: tuple[dict, ...] = (
    {"id": "orientacao", "setor": "ATENDIMENTO", "nome": "Orientação de balcão",
     "quando": "a pessoa ainda não disse o serviço, ou a pergunta é geral"},
    {"id": "certidao_civil", "setor": "RCPN", "nome": "Certidão do registro civil",
     "quando": "certidão de nascimento, de casamento ou de óbito"},
    {"id": "registro_civil", "setor": "RCPN", "nome": "Registro civil",
     "quando": "registrar nascimento, casamento, óbito ou fazer habilitação"},
    {"id": "certidao_imovel", "setor": "RI", "nome": "Certidão de imóvel",
     "quando": "certidão de matrícula, de ônus ou de propriedade"},
    {"id": "registro_imovel", "setor": "RI", "nome": "Registro de imóvel",
     "quando": "registrar, averbar, retificar ou prenotar imóvel"},
    {"id": "escritura", "setor": "NOTAS", "nome": "Escritura",
     "quando": "escritura de compra e venda, doação, inventário, partilha ou divórcio"},
    {"id": "procuracao", "setor": "NOTAS", "nome": "Procuração ou ata notarial",
     "quando": "procuração, substabelecimento, testamento ou ata notarial"},
    {"id": "firma", "setor": "NOTAS", "nome": "Firma e autenticação",
     "quando": "reconhecer firma, abrir cartão de firma ou autenticar cópia"},
    {"id": "protesto", "setor": "PROTESTO", "nome": "Protesto",
     "quando": "apontar título, intimação, pagamento, cancelamento ou instrumento"},
    {"id": "certidao_protesto", "setor": "PROTESTO", "nome": "Certidão de protesto",
     "quando": "certidão de protesto ou certidão negativa"},
    {"id": "rtd_rcpj", "setor": "RCPJ_RTD", "nome": "Títulos e documentos",
     "quando": "notificação ou registro de título ou documento"},
    {"id": "manifestacao", "setor": "GESTAO", "nome": "Manifestação",
     "quando": "reclamação, ouvidoria ou elogio sobre o atendimento"},
    # 15/11/2026: pedir o tabelião era «orientação» na gestão, e a tarefa não
    # dizia o que era. O serviço próprio põe o nome certo no título dela.
    {"id": "tabeliao", "setor": "GESTAO", "nome": "Falar com o tabelião",
     "quando": "a pessoa pede o tabelião, o oficial ou a substituta"},
    {"id": "conferir_arquivo", "setor": "ATENDIMENTO", "nome": "Conferir arquivo",
     "quando": "a pessoa mandou foto, PDF ou documento"},
    {"id": "conferir_no_balcao", "setor": "ATENDIMENTO", "nome": "Conferir no balcão",
     "quando": "dado pessoal, assunto protegido, ou o que não deu para responder"},
)

_POR_ID = {s["id"]: s for s in SERVICOS}
_POR_SETOR = {
    "RCPN": "registro_civil",
    "RI": "registro_imovel",
    "NOTAS": "firma",
    "PROTESTO": "protesto",
    "RCPJ_RTD": "rtd_rcpj",
    "GESTAO": "manifestacao",
    "ATENDIMENTO": "orientacao",
}


def servico_valido(valor: object) -> str:
    """O id da lista, ou vazio se o modelo inventou um. Só calcula."""
    chave = str(valor or "").strip().lower()
    return chave if chave in _POR_ID else ""


def setor_do_servico(valor: object) -> str:
    """O setor que recebe aquele serviço; o balcão, se o id é desconhecido."""
    chave = servico_valido(valor)
    return _POR_ID[chave]["setor"] if chave else "ATENDIMENTO"


def nome_do_servico(valor: object) -> str:
    """O nome que a tela mostra. Id desconhecido volta como veio, curto."""
    chave = servico_valido(valor)
    if chave:
        return _POR_ID[chave]["nome"]
    bruto = str(valor or "").strip()
    return bruto[:40] or "Pedido"


def servico_de(setor: str, razao: str = "") -> str:
    """O serviço quando a regra decide, sem o modelo. Só calcula."""
    if razao == "arquivo":
        return "conferir_arquivo"
    if razao == "dado_protegido":
        return "conferir_no_balcao"
    if razao == "reclamacao":
        return "manifestacao"
    return _POR_SETOR.get(str(setor or "").strip(), "orientacao")


def texto_do_oficio() -> str:
    """O que o cartório faz e como o escrevente trabalha. Sem número. Só calcula."""
    linhas = [
        "=== O OFÍCIO DESTA SERVENTIA ===",
        "Isto é para você saber o caminho. Não leia este texto para o cliente. "
        "Fale como a pessoa do atendimento: frase curta, e diga que vai passar "
        "ao escrevente.",
        "1. Entende o que a pessoa precisa (certidão, registro, escritura, firma, "
        "protesto ou título).",
        "2. Diz o caminho e os documentos de forma geral. Não promete o ato pronto.",
        "3. Quando a pessoa quer o serviço feito, diga que vai passar ao escrevente.",
        "4. O oficial, ou quem ele autorizou, decide o ato. Esta conversa não "
        "decide o ato.",
        "Atribuições: Registro Civil (nascimento, casamento, óbito, habilitação e "
        "as certidões); Registro de Imóveis (matrícula, registro, averbação, "
        "certidão); Tabelionato de Notas (escritura, procuração, testamento, ata "
        "notarial, reconhecimento de firma e autenticação); Protesto (apontamento, "
        "intimação, pagamento, cancelamento, instrumento e certidão); Títulos e "
        "Documentos (notificação e registro de título ou documento). Esta "
        "serventia não registra empresa nem pessoa jurídica.",
        "O valor em dinheiro só sai da tabela de emolumentos da casa, como "
        "estimativa, e só para o item da lista aprovada. Prazo, selo, livro e "
        "matrícula não se inventam: ou estão no texto-base, ou no trecho de norma "
        "desta pergunta, ou não se dizem.",
        "A norma da atividade é a que está na base normativa da casa (Lei de "
        "Registros Públicos, Lei dos Cartórios, Lei de Protesto, Código de Normas "
        "do TJMA, Código Nacional de Normas e as demais carregadas). Cite o artigo "
        "só quando o trecho veio nesta pergunta, com a citação como ela veio.",
        "Serviços que o escrevente recebe:",
    ]
    for s in SERVICOS:
        linhas.append(f"- {s['id']} ({s['setor']}): {s['nome']} — {s['quando']}.")
    return "\n".join(linhas)
