"""O manual do atendimento: o que o escrevente do WhatsApp sabe de cada serviço.

Pedido do oficial em 14/11/2026: o WhatsApp tem de responder «com conhecimento
de causa e da rotina do cartório». O que havia era o texto-base da casa (horário,
endereço, telefone) e o ofício (`wa_oficio`), que diz o caminho e não diz o
conteúdo: nenhuma lista de documentos, nenhum prazo de lei, nada do que o balcão
responde vinte vezes por dia. A base da ajuda (`ajuda_base`) não serve a isso —
ela explica a tela para quem trabalha na casa, e foi ela que pôs na conversa as
frases que «explicam o cartório por dentro».

ESTE MÓDULO TRAZ O TEXTO DE FÁBRICA, E A IA NÃO O USA SOZINHA
    `PADRAO` é a orientação geral de um ofício único no Maranhão, escrita a
    partir da lei federal (Lei 6.015/1973, Lei 8.935/1994, Lei 9.492/1997, Código
    Civil) e conferível na base normativa da casa. É RASCUNHO: quem responde pelo
    que a casa diz ao público é o oficial. A IA só usa o texto que o ADMIN gravou
    na tela do atendente (`wa_schema.CHAVE_IA_MANUAL`) — gravar é aprovar, e fica
    quem aprovou e quando, como no texto-base.

    Linha entre colchetes (`[confirmar: ...]`) é lembrete para quem revisa, e não
    informação: a instrução manda a IA ignorá-la, e a tela avisa enquanto houver.

O QUE NÃO ENTRA AQUI
    Valor em dinheiro (sai do cálculo de custas, pela lista de valores), horário e
    endereço (texto-base), e o que é desta casa e eu não tinha como saber: forma de
    pagamento, prazo de entrega próprio, se faz apostila. Esses estão em colchete.
"""
from __future__ import annotations

import re
from typing import Any

import wa_balcao as BALCAO
import wa_schema as WA

TETO = 40_000          # caracteres; o manual inteiro vai no prefixo guardado do provedor

PADRAO = """\
MANUAL DO ATENDIMENTO — orientação geral ao público. O escrevente confirma no caso concreto.

=== COMO O CARTÓRIO TRABALHA ===
- O cartório é um ofício único: Registro Civil, Registro de Imóveis, Tabelionato de Notas, Protesto e Títulos e Documentos no mesmo balcão.
- Por mensagem dá para: tirar dúvida, saber os documentos, ter estimativa de valor, acompanhar protocolo, mandar documento para análise prévia e deixar o pedido encaminhado ao escrevente.
- Por mensagem NÃO dá para: reconhecer firma, autenticar cópia, lavrar ou assinar ato, nem registrar título. Esses pedem a presença da pessoa, o documento original ou o título eletrônico pelos canais oficiais.
- Foto ou PDF enviado na conversa serve para o escrevente conferir e adiantar o serviço. Não é o protocolo oficial do título (prenotação) e não garante prioridade de registro: isso só nasce quando o título original, ou o eletrônico, é apresentado e protocolado.
- Quem decide se o ato pode ser feito é o oficial ou o escrevente autorizado, depois de ver os documentos.
[confirmar: formas de pagamento aceitas no balcão]
[confirmar: prazos de entrega que a casa pratica para certidão e para procuração]

=== REGISTRO CIVIL ===
REGISTRO DE NASCIMENTO
- É gratuito, e a primeira certidão também (Lei 6.015/1973, art. 30).
- Onde: no cartório do lugar do parto ou da residência dos pais. Prazo: 15 dias; até 3 meses para quem mora a mais de 30 km da sede do cartório (Lei 6.015/1973, art. 50). Passado o prazo ainda se registra, por registro tardio: o escrevente orienta.
- Levar: a Declaração de Nascido Vivo (DNV, a via amarela dada pelo hospital ou pela parteira), documento de identidade com foto dos pais e, se forem casados, a certidão de casamento.
- Pais casados entre si: qualquer um dos dois registra sozinho. Pais não casados: o pai comparece para declarar a paternidade, ou manda declaração com firma reconhecida ou procuração; a mãe sozinha registra com o nome dela e pode indicar o suposto pai.
- Parto em casa sem DNV, criança indígena, pais menores de idade ou sem documento: há caminho para todos; passar ao escrevente.

RECONHECIMENTO DE PATERNIDADE
- Pode ser pedido em qualquer cartório de registro civil, a qualquer tempo. Filho menor: a mãe concorda. Filho maior: ele mesmo concorda. Levar documentos de identidade e a certidão de nascimento do filho.

CASAMENTO
- A habilitação é feita no cartório do domicílio de um dos noivos. Idade mínima: 16 anos, e entre 16 e 18 com autorização dos pais (Código Civil, art. 1.517).
- Documentos (a base é o Código Civil, art. 1.525): certidão de nascimento dos noivos (ou de casamento com a averbação do divórcio, se divorciado; de casamento e de óbito do cônjuge, se viúvo); documento de identidade e CPF; comprovante de endereço; duas testemunhas maiores, com documento, que conheçam os noivos.
- Aprovada a habilitação, ela vale por 90 dias para casar (Código Civil, art. 1.532).
- Regime de bens: sem pacto, vale a comunhão parcial. Outro regime pede pacto antenupcial por escritura pública, feito antes.
- Quem se declara pobre, sob as penas da lei, é isento na habilitação, no registro e na primeira certidão (Código Civil, art. 1.512).
- Casamento religioso com efeito civil e conversão de união estável em casamento: também se faz; o escrevente orienta.

ÓBITO
- O registro e a primeira certidão são gratuitos (Lei 6.015/1973, art. 30).
- Onde: no cartório do lugar do falecimento ou da residência do falecido. Prazo: 24 horas; não sendo possível, 15 dias, ou até 3 meses para quem mora a mais de 30 km da sede (Lei 6.015/1973, arts. 78 e 50). O sepultamento pede a certidão.
- Levar: a Declaração de Óbito assinada pelo médico, os documentos do falecido (identidade, CPF, certidão de nascimento ou de casamento, título de eleitor, cartão de benefício se houver) e o documento de quem declara.
- A pessoa que procura o cartório por um óbito está de luto: primeiro acolher, depois orientar, sem pressa.

SEGUNDA VIA DE CERTIDÃO (nascimento, casamento, óbito)
- Qualquer pessoa pode pedir. Informar: nome completo do registrado, data e cidade do registro, nome dos pais; se tiver, livro, folha e termo ou o número da matrícula da certidão antiga.
- Registro feito em outra cidade ou estado: dá para pedir por aqui, pela central do registro civil, ou direto em registrocivil.org.br.
- A segunda via é paga. Quem é reconhecidamente pobre é isento nas certidões do registro civil, mediante declaração (Lei 6.015/1973, art. 30).
- Certidão de inteiro teor traz dados reservados e pode pedir requerimento próprio: o escrevente orienta.

AVERBAÇÃO E RETIFICAÇÃO
- Divórcio, separação, reconhecimento de filho, mudança de nome: averbam-se à vista do documento (mandado, sentença ou escritura). Erro evidente no registro corrige-se no próprio cartório, com os documentos que provam o certo. Passar ao escrevente com o que a pessoa contou.

=== TABELIONATO DE NOTAS ===
RECONHECIMENTO DE FIRMA
- Por semelhança: o cartório compara a assinatura com o cartão que a pessoa tem arquivado. Quem ainda não tem cartão abre um, em pessoa, com documento de identidade original com foto e CPF.
- Por autenticidade: a pessoa assina na frente do escrevente. É o exigido na transferência de veículo e em alguns contratos.
- O documento vem preenchido, sem espaço em branco. Não se reconhece firma em documento incompleto.

AUTENTICAÇÃO DE CÓPIA
- Trazer o documento original junto com a cópia: a autenticação é a conferência da cópia com o original.
[confirmar: a casa autentica cópia tirada de cópia já autenticada?]

PROCURAÇÃO PÚBLICA
- Quem dá a procuração (outorgante) vem em pessoa, com documento de identidade e CPF, e informa estado civil, profissão e endereço. O procurador não precisa vir: bastam os dados dele (nome completo, estado civil, profissão, identidade, CPF e endereço).
- Dizer para que serve: quanto mais específico o poder, melhor. Para vender ou cuidar de imóvel, trazer os dados do imóvel (a matrícula).
- Quem não pode vir ao cartório (doente, idoso acamado): perguntar ao escrevente sobre diligência.
- Revogar procuração e substabelecer também se fazem no tabelionato.

ESCRITURA DE COMPRA E VENDA OU DOAÇÃO DE IMÓVEL
- A escritura pública é obrigatória para imóvel de valor acima de 30 salários mínimos (Código Civil, art. 108). A escritura sozinha não transfere a propriedade: depois dela vem o registro no Registro de Imóveis (Código Civil, art. 1.245).
- Das partes: identidade, CPF, certidão de casamento ou de nascimento, pacto antenupcial se houver, profissão e endereço.
- Do imóvel: certidão de matrícula com ônus e ações, que vale 30 dias para a escritura; prova de quitação do imposto de transmissão (ITBI na compra e venda; o imposto estadual na doação); e a situação do imposto do imóvel. Imóvel rural pede também CCIR, ITR e CAR.
- O valor depende do valor do negócio: dá-se por estimativa, pela tabela.

INVENTÁRIO, PARTILHA E DIVÓRCIO EM CARTÓRIO
- Fazem-se por escritura quando todos estão de acordo, e sempre com advogado. Havendo menor, incapaz ou testamento, há regra própria: o escrevente avalia.
- Inventário: certidão de óbito, documentos dos herdeiros e cônjuges, certidões dos bens e o imposto de transmissão pago. Divórcio: certidão de casamento, documentos do casal, pacto se houver, e a relação de bens.

OUTROS ATOS
- União estável: declara-se por escritura pública ou por termo no Registro Civil, com documentos pessoais e certidão de estado civil atualizada.
- Testamento público: a pessoa capaz declara a vontade ao tabelião, com duas testemunhas.
- Ata notarial: o tabelião constata um fato e o descreve com fé pública — conversa de celular, página de internet, estado de um imóvel. Serve de prova.
- Autorização de viagem de criança ou adolescente: os pais assinam a autorização e reconhecem firma.
[confirmar: esta serventia faz apostila de Haia?]
[confirmar: esta serventia faz atos por videoconferência pelo e-Notariado?]

=== REGISTRO DE IMÓVEIS ===
CERTIDÃO DA MATRÍCULA
- Qualquer pessoa pode pedir, sem dizer o motivo (Lei 6.015/1973, art. 17). Informar o número da matrícula; sem ele, o nome completo ou o CPF do dono e o endereço do imóvel, para a busca.
- Tipos mais pedidos: inteiro teor da matrícula; ônus e ações (diz se há hipoteca, penhora, alienação fiduciária); e a negativa de propriedade.
- Também se pede pela internet, em registradores.onr.org.br.

REGISTRAR ESCRITURA, CONTRATO OU FORMAL DE PARTILHA
- Apresenta-se o título original (o traslado da escritura, o contrato do banco, o formal de partilha, a carta de sentença) com a prova do imposto de transmissão pago.
- O título é protocolado e ganha um número de ordem, que garante a prioridade. O cartório analisa e registra, ou devolve com nota de exigência dizendo o que falta, em até 10 dias úteis (Lei 6.015/1973, art. 188). O protocolo vale 20 dias úteis: a exigência se cumpre dentro dele (Lei 6.015/1973, art. 205).
- O valor do registro depende do valor do negócio: estimativa pela tabela.

AVERBAÇÃO
- Construção (habite-se e a quitação da obra na Previdência), casamento ou divórcio do dono (a certidão), óbito, cancelamento de hipoteca ou de alienação fiduciária (o termo de quitação do credor, com firma reconhecida). Pede-se por requerimento com firma reconhecida.

TÍTULO DO INCRA, DO ESTADO OU DA PREFEITURA
- Título de domínio dado pelo INCRA, pelo órgão de terras do Estado ou pelo Município registra-se no Registro de Imóveis do lugar do imóvel. Trazer o título original e os documentos pessoais; em imóvel rural, também CCIR, ITR e CAR.
- Conforme a área, pode ser exigida planta e memorial georreferenciados com certificação do INCRA. O primeiro registro de título da reforma agrária pode ser gratuito. O escrevente do Registro de Imóveis confere as duas coisas à vista do título.

IMÓVEL SEM ESCRITURA OU SEM REGISTRO
- Recibo, contrato particular ou posse antiga não são registro. Os caminhos são: escritura e registro, quando o vendedor é o dono na matrícula; usucapião em cartório, que pede advogado, ata notarial, planta e memorial; ou a regularização fundiária feita pelo Município. O escrevente vê qual serve, à vista do que a pessoa tem.

=== PROTESTO ===
- Protestar um título (cheque, nota promissória, duplicata, contrato, sentença, certidão de dívida): o credor apresenta o título original, os seus documentos e o endereço do devedor. Em muitos casos quem apresenta não paga nada na entrada: o escrevente confirma.
- Recebi uma intimação: ela diz o valor e a data-limite. O prazo é curto — o protesto é lavrado em 3 dias úteis do protocolo do título (Lei 9.492/1997, art. 12). Pagando no cartório até a data, não há protesto.
- Cuidado com golpe: antes de pagar boleto ou Pix recebido por mensagem ou e-mail, confirme com o cartório. O cartório não manda cobrar em conta de pessoa física.
- Já fui protestado, como limpo o nome: pague a dívida a quem cobrou e traga ao cartório o título original protestado, ou a carta de anuência do credor com firma reconhecida; com isso e as custas do cancelamento, o protesto é cancelado (Lei 9.492/1997, art. 26).
- Certidão de protesto: pede-se com o nome completo e o CPF ou CNPJ, e cobre os últimos 5 anos (Lei 9.492/1997, art. 27).
- Consulta gratuita de protesto pelo CPF ou CNPJ: pesquisaprotesto.com.br.
- Por mensagem não se informa se uma pessoa tem protesto, nem valor de título: isso é certidão, ou atendimento do escrevente a quem é parte.

=== TÍTULOS E DOCUMENTOS ===
- Notificação extrajudicial: trazer a carta em vias (uma para cada destinatário e uma para o cartório) e o endereço completo de quem será notificado. O cartório entrega e certifica.
- Registro de contrato ou documento, para guardar e valer contra terceiros: trazer o original.
- Esta serventia não registra empresa nem pessoa jurídica.

=== CASOS QUE VÃO SEMPRE AO ESCREVENTE ===
- Análise de um documento ou de uma situação concreta; qualquer dúvida sobre se o ato pode ser feito.
- Adoção, mudança de nome ou de gênero, violência, medida protetiva e qualquer assunto reservado.
- Reclamação, elogio ou pedido de falar com o tabelião: vai para a gestão.
- Urgência (sepultamento, viagem marcada, prazo que vence hoje): avisar que é urgente ao encaminhar.
"""

# A LISTA DE VALORES SUGERIDA (15/11/2026). Os códigos foram conferidos na
# tabela de emolumentos importada da casa; os três últimos são atos de faixa — o
# valor depende do valor do negócio, e a IA só os estima quando o cliente o diz.
VALORES_SUGERIDOS = """\
13.17.2 | Reconhecimento de firma (por assinatura)
13.17.3 | Reconhecimento de firma em documento de veículo (por assinatura)
13.17.1 | Abertura do cartão de assinatura
13.18 | Autenticação de cópia (por página)
13.9.3 | Procuração pública
13.9.6 | Revogação de procuração
13.12.1 | Certidão ou traslado de escritura ou procuração (uma folha)
14.5.1 | Segunda via de certidão de nascimento, casamento ou óbito
14.5.6 | Certidão de inteiro teor do registro civil
14.1.1 | Habilitação e casamento civil
16.24.1 | Certidão do Registro de Imóveis (uma folha)
16.24.4 | Certidão de inteiro teor, ônus e ações da matrícula
17.5.1 | Certidão de protesto (uma folha)
15.8 | Notificação extrajudicial (por destinatário, sem a diligência)
13.1 | Escritura com valor declarado
16.3 | Registro de imóvel com valor declarado
17.4 | Cancelamento de protesto
"""

_LEMBRETE = re.compile(r"^\s*\[[^\]\n]*\]\s*$", re.M)


class ManualErro(ValueError):
    """Manual recusado. Mensagem pronta para a tela."""


def lembretes(texto: Any) -> list[str]:
    """As linhas entre colchetes que ainda esperam quem revisa. Só calcula."""
    return [m.group(0).strip() for m in _LEMBRETE.finditer(str(texto or ""))]


def sem_lembretes(texto: Any) -> str:
    """O manual como sobe ao modelo: sem as linhas entre colchetes. Só calcula."""
    limpo = _LEMBRETE.sub("", str(texto or ""))
    return re.sub(r"\n{3,}", "\n\n", limpo).strip()


def config(con: Any) -> dict:
    """O manual gravado, quem aprovou e quando. SÓ LÊ."""
    texto = BALCAO.ler_config(con, WA.CHAVE_IA_MANUAL)
    return {"texto": texto, "aprovado": bool(texto.strip()),
            "por": BALCAO.ler_config(con, WA.CHAVE_IA_MANUAL_POR),
            "em": BALCAO.ler_config(con, WA.CHAVE_IA_MANUAL_EM),
            "lembretes": lembretes(texto)}


def gravar(con: Any, texto: Any, *, por: str, agora: str) -> bool:
    """Grava o manual que o ADMIN aprovou. ESCREVE. Devolve se mudou.

    Texto vazio desaprova: a IA volta a responder só com o texto-base. O texto
    igual ao gravado não troca quem aprovou nem quando."""
    novo = str(texto or "").replace("\r\n", "\n").strip()
    if len(novo) > TETO:
        raise ManualErro(f"O manual passou de {TETO} caracteres ({len(novo)}). "
                         "Ele vai inteiro em cada conversa: encurte.")
    if novo == BALCAO.ler_config(con, WA.CHAVE_IA_MANUAL):
        return False
    BALCAO.gravar_config(con, WA.CHAVE_IA_MANUAL, novo)
    BALCAO.gravar_config(con, WA.CHAVE_IA_MANUAL_POR, por if novo else "")
    BALCAO.gravar_config(con, WA.CHAVE_IA_MANUAL_EM, agora if novo else "")
    return True
