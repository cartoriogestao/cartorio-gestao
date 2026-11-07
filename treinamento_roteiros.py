"""Conteúdo operacional revisável. Regras do título vêm das fontes normativas."""
from __future__ import annotations

# objetivo; preparação; execução; conferência final; quando encaminhar.
ROTEIROS = {
    "aprendizagem": (
        "Aprender as rotinas do sistema e acompanhar a prática na versão estudada.",
        "Escolha a trilha da sua função e confira a orientação do responsável sobre o que você poderá executar.",
        "Abra a aula, estude os pontos importantes e os campos da rotina e responda às situações fictícias. Confira as explicações e refaça a atividade quando precisar.",
        "Consulte o progresso da trilha e as atualizações de conteúdo. A gestão acompanha o aprendizado; o ADMIN publica orientações revisadas com fontes e motivo.",
        "Dúvidas sobre o ato, divergências nas fontes e necessidade de supervisão devem ser encaminhadas ao responsável; a prática de treinamento não libera permissões."),
    "atendimento": (
        "Receber um pedido, identificar o serviço e permitir que a equipe acompanhe seu destino.",
        "Ouça o que o interessado pretende; identifique a atribuição, contato e documentos entregues. Separe orçamento de serviço apresentado.",
        "Pesquise o atendimento existente antes de abrir outro. Registre o serviço e classifique os documentos. No RI, faça o ingresso pela prenotação quando aplicável, mantendo o vínculo com o atendimento.",
        "Confira o comprovante de recepção, os números relacionados, o responsável e o próximo passo informado ao interessado.",
        "Encaminhe ao responsável dúvidas sobre apresentação, prioridade, prazo, gratuidade ou procedimento adequado."),
    "prenotacao": (
        "Registrar a apresentação do título ao RI e acompanhar seu andamento legal.",
        "Identifique o título apresentado, apresentante, natureza, matrícula quando conhecida e documentos. Orçamento e exame/cálculo têm trilha própria.",
        "Abra Protocolo / prenotação; use o atendimento já aberto quando houver. Confira o título e a data real de apresentação. Confirme pela ação Prenotar e consulte a ficha gerada.",
        "Confira número e livro, data/hora, prazo com a regra aplicável e vínculo ao atendimento. Uma nota emitida mantém o acompanhamento da vigência; o sistema não decide o caso pelo pagamento.",
        "Dúvida sobre prioridade, exceção, suspensão, prorrogação ou vencimento depende de conferência e decisão do responsável."),
    "qualificacao": (
        "Examinar título, registro e documentos e documentar a decisão humana.",
        "Reúna a versão atual do título, matrícula/registro, documentos, atos anteriores pertinentes e fontes normativas. Identifique contradições e informações ausentes.",
        "Assuma a análise na ficha. Confira partes, representação, objeto, título e requisitos do caso. Se usar a IA, examine as fontes e os documentos usados. Positiva segue para preparação do ato; negativa segue para a nota.",
        "Registre responsável, data e fundamento. Confira se nenhum documento relevante foi alterado após a análise. A sugestão da IA só passa a decisão quando o usuário autorizado a registra.",
        "Encaminhe dúvida jurídica, fundamento não conferido ou divergência documental que ultrapasse sua autorização."),
    "nota": (
        "Comunicar a qualificação negativa de forma clara e acompanhar seu cumprimento.",
        "Conclua a análise do conjunto documental e reúna as exigências identificadas. Confira o fundamento de cada item e o padrão de documento da casa.",
        "Na análise do pedido, prepare a nota. Para cada item, explique o problema, como cumprir e o fundamento. Revise a prévia e emita pela rotina da atribuição, com responsável e formalidades aplicáveis. Nota já assinada em DOCX/PDF pode ser cadastrada pela ação própria.",
        "Confira número, data, protocolo, conteúdo, versão emitida e ciência/entrega. A nota deve permitir que o interessado compreenda a providência e a via aplicável em caso de discordância.",
        "Nova exigência após nota emitida, retificação de nota, cancelamento ou discordância requerem exame do responsável e histórico preservado."),
    "reingresso": (
        "Receber documentos de cumprimento e conduzir o título à reconferência adequada.",
        "Localize a nota aberta no atendimento correto e confira a situação da prenotação. Identifique os documentos novos e sua data real de apresentação.",
        "Anexe e classifique o complemento na rotina do protocolo. Na ficha do atendimento, marque quais itens foram apresentados e vincule a evidência. O qualificador confere cada item. Use Registrar reingresso na nota para a ocorrência formal, com suas validações de data e vigência.",
        "Confirme o aproveitamento ou a necessidade de nova prenotação indicada pelo procedimento. O título recebido volta à análise; documento apresentado e exigência aceita são fatos diferentes.",
        "Data passada, vigência encerrada, suspensão ou controvérsia sobre o retorno exigem decisão autorizada e prova da ocorrência."),
    "caixa": (
        "Receber e conciliar valores com identificação do serviço e rastreabilidade.",
        "Abra o caixa do operador e localize o atendimento. Confira cálculo, itens, meio de pagamento, depósito disponível e eventual benefício autorizado.",
        "Registre o recebimento efetivo na ação adequada. Depósito prévio entra uma vez; sua aplicação aos itens é vinculada ao movimento existente. Para a diferença, use o saldo mostrado após conferência.",
        "Confira valor, pagador, vínculo, forma de pagamento e recibo. No fechamento, compare o esperado com o contado/conciliado por meio e registre diferenças.",
        "Estorno, restituição, pagamento sem identificação e divergência de caixa seguem autorização, motivo e prova; não esconda a diferença com outro lançamento."),
    "certidao": (
        "Expedir o documento adequado ao registro e à espécie solicitada.",
        "Identifique a atribuição, registro de origem e espécie solicitada. Confira a situação atual, atos, averbações e anotações pertinentes.",
        "Abra a ficha ou a lista de certidões da atribuição. Selecione a espécie, confirme os dados e use a prévia. Faça a emissão e a selagem pelo fluxo próprio, conferindo as mensagens do sistema.",
        "Revise a versão final, identificadores, teor, assinatura, selo e entrega. Segunda via é emissão sobre o registro existente, sem criar outro assento.",
        "Divergência com o original, acesso restrito, cancelamento ou ausência de dado essencial exigem exame do responsável."),
    "ri_ato": (
        "Preparar e praticar registro ou averbação vinculado ao título e à matrícula corretos.",
        "Confira a prenotação, qualificação, matrícula, titularidade, descrição do imóvel, título e documentos de suporte. Escolha a natureza adequada do modelo.",
        "Prepare o rascunho na matrícula. Preencha os dados comprovados, revise cláusulas e referências e confira a prévia. Resolva marcadores e divergências antes de usar a ação nativa de lavratura/selagem.",
        "Confira número e espécie do ato, teor final, selo, autoria e vínculo ao título. Complete arquivamento e entrega conforme o caso.",
        "Continuidade, disponibilidade, descrição divergente, restrições ou competência controvertida precisam de decisão jurídica; modelos são instrumentos de trabalho."),
    "livro3": (
        "Trabalhar com registro auxiliar, seus atos e certidões no Livro 3.",
        "Identifique o título, a espécie e o registro auxiliar correto. Reúna partes, objeto e documentos; confira análise e vínculo ao atendimento.",
        "No Livro 3, abra ou localize a minuta. Confira campos, partes e teor; gere prévia e encaminhe à revisão. A prática e a selagem usam as ações da ficha do registro auxiliar.",
        "Confira registro principal, atos posteriores, numeração, selo e certidão correspondente. Preserve a distinção entre Livro 2 e Livro 3.",
        "Renumeração, desfazimento, ato selado ou divergência histórica seguem a rotina autorizada e seu registro de ocorrência."),
    "notas_ato": (
        "Preparar instrumento notarial, conferir sua adequação ao caso e concluir o fluxo do livro.",
        "Escolha a espécie e o modelo adequados. Identifique partes, capacidade, representação, vontade declarada, objeto, documentos e condições do ato.",
        "Abra a minuta na família correta. Preencha partes e dados comprovados; revise todas as cláusulas e a prévia. Confira as pendências do sistema e do responsável. Somente o preposto autorizado conclui lavratura, assinatura, selo e traslado pelas ações próprias.",
        "Confira livro, folhas, termo, teor, assinaturas e selo. Complete PDF assinado, entrega e comunicações aplicáveis à espécie, conservando as confirmações.",
        "Capacidade, representação, forma, restrições, tributação ou conteúdo jurídico controvertido devem ser submetidos ao tabelião/responsável."),
    "procuracao": (
        "Preparar mandato com identificação das partes e poderes compatíveis com a vontade declarada.",
        "Identifique outorgante e outorgado, capacidade, representação, finalidade, poderes, prazo e objeto quando aplicável.",
        "Em Atos de livro, escolha procuração ou a espécie correta de substabelecimento/revogação/renúncia. Cadastre todas as partes e confira o teor com o cadastro. Revise poderes e campos pendentes antes da prévia e da lavratura autorizada.",
        "Confira identificação, poderes expressos quando exigíveis, limites, livro, folhas, assinatura, selo e traslado. O texto e as partes cadastradas devem concordar.",
        "Poderes insuficientes, incapacidade, representação duvidosa ou espécie inadequada exigem decisão do responsável."),
    "ata": (
        "Documentar fatos constatados pelo tabelião, com evidências e limites da constatação.",
        "Identifique solicitante, finalidade, fatos, local/data e evidências que serão examinadas. Defina o objeto da constatação com o responsável.",
        "Abra Atas notariais, escolha o modelo aplicável e cadastre partes e documentos. Descreva o que foi efetivamente constatado, distinguindo declarações e evidências. Revise a minuta e as referências aos anexos antes da formalização autorizada.",
        "Confira fidelidade da narrativa, identificação das evidências, datas, livro, assinaturas, selo e traslado.",
        "Pedido de conclusão jurídica, prova inacessível ou conteúdo fora da constatação deve ser examinado pelo responsável."),
    "firma": (
        "Reconhecer firma pela modalidade adequada e registrar corretamente a etiqueta e o selo.",
        "Localize o cartão de autógrafo e confirme identidade, documento e modalidade aplicável. Confira a assinatura e a presença/procedimento exigidos para o caso.",
        "Abra Reconhecer firma, selecione o cartão e a modalidade e preencha os dados solicitados. Confira quantidade, cobrança e destino da etiqueta. Pratique o ato somente pela ação autorizada após a conferência.",
        "Confira pessoa, modalidade, documento, quantidade, etiqueta e selo do próprio ato. A lista de reconhecimentos permite recuperar o que já foi praticado.",
        "Assinatura divergente, documento irregular, identidade não comprovada ou dúvida sobre modalidade devem ser submetidos ao responsável."),
    "autenticacao": (
        "Conferir a cópia com o documento apresentado e praticar a autenticação adequada.",
        "Examine o original e a cópia, integridade, legibilidade e quantidade de páginas/documentos. Confira as condições do procedimento aplicável.",
        "Abra Autenticar cópia; informe os dados e a quantidade. Confira o cálculo e os campos da etiqueta. A emissão e selagem ocorrem pela ação nativa autorizada.",
        "Confira a correspondência entre cada cópia, etiqueta e selo, sem reaproveitar selo de outro ato.",
        "Suspeita de adulteração, ausência de original adequado ou modalidade especial exige conferência do responsável."),
    "nascimento": (
        "Preparar o assento de nascimento a partir da declaração e da documentação do caso.",
        "Identifique declarante, registrando, filiação, nascimento, local e documentos de suporte, inclusive DNV quando aplicável. Confira hipóteses especiais com o responsável.",
        "Abra novo nascimento no Registro Civil. A leitura de documentos pode ajudar a preencher; confronte cada dado com o original. Cadastre as pessoas e informações nos campos do assento e revise o termo gerado antes da lavratura autorizada.",
        "Confira termo, livro, folhas, matrícula nacional, nomes, filiação, datas, CPF quando aplicável, certidão e comunicações próprias.",
        "Registro tardio, filiação controvertida, ausência documental ou situação especial seguem procedimento próprio; não complete dado por suposição."),
    "casamento": (
        "Acompanhar habilitação, celebração e assento conforme a modalidade aplicável.",
        "Reúna requerimento, identificação, estado civil, documentos e regime de bens. Confira impedimentos, representação e hipóteses especiais com o responsável.",
        "Abra a habilitação, registre documentos e etapas do procedimento. Confira proclamas, manifestações e aptidão nas rotinas próprias. Após a celebração ou modalidade correspondente, use o fluxo que leva ao assento de casamento.",
        "Confira nomes adotados, regime, datas, celebrante, testemunhas, livro, termo, matrícula, certidão e comunicações.",
        "Dispensa, urgência, impedimento, conversão ou registro religioso têm requisitos próprios e dependem da análise autorizada."),
    "obito": (
        "Preparar o assento de óbito com fidelidade à declaração e aos documentos.",
        "Identifique declarante, falecido, declaração de óbito e demais documentos. Confira datas, local, filiação e informações disponíveis, observando situações especiais.",
        "Abra novo óbito no Registro Civil. Se usar leitura assistida, confronte os campos com os originais. Revise o termo e os campos indicados pelo sistema antes da lavratura autorizada.",
        "Confira identificação, datas, registro, livro/folhas/termo, matrícula nacional, certidão e comunicações próprias.",
        "Ausência de declaração adequada, identidade incerta, registro tardio ou divergência essencial exige procedimento e decisão do responsável."),
    "rcpn": (
        "Manter o registro civil e suas anotações, averbações, certidões e comunicações.",
        "Localize o assento correto e o documento que fundamenta a providência. Confira competência, espécie e autorização aplicáveis.",
        "Abra a ficha do assento ou o fluxo específico. Cadastre a informação comprovada e revise a prévia/termo. Use a ação própria de averbação, anotação, Livro E ou comunicação, conservando o fundamento.",
        "Confira texto, vínculo ao assento, datas, autoria, certidão atualizada quando cabível e confirmação das comunicações.",
        "Alteração de nome, filiação, estado civil, cancelamento ou retificação com dúvida seguem o procedimento específico e a decisão competente."),
    "protesto": (
        "Conduzir o título apresentado, acompanhar intimação e registrar o desfecho correto.",
        "Confira arquivo/título, apresentante, devedor, dados, valores e duplicidades antes de confirmar a entrada.",
        "Receba pela rotina de títulos ou remessa e examine as rejeições. Acompanhe a intimação e os comprovantes. Registre pagamento, retirada, sustação ou protesto na função específica, conforme o procedimento e a autorização.",
        "Confira o desfecho de cada título, documentos, selos, retornos à central e conciliação de valores. Arquivo gerado e envio confirmado devem ser distinguidos.",
        "Intimação inviável, prazo controvertido, ordem judicial, cancelamento ou divergência de valor exigem conferência do responsável."),
    "rtd_rpj": (
        "Receber, qualificar e registrar título no registro competente.",
        "Identifique a atribuição, finalidade, título, partes, representação e competência. Vincule o atendimento e reúna documentos.",
        "Abra o título em RCPJ ou RTD, confira documentos e registre a qualificação. Exigência segue a negativa própria do título. Estando apto e autorizado, prepare e pratique o registro pela ficha correspondente.",
        "Confira espécie, livro/número, partes, teor, selo, arquivamento, certidão e entrega. Mantenha o histórico das qualificações e retornos.",
        "Competência, representação, alteração de pessoa jurídica, conteúdo restrito ou procedimento de notificação controvertido dependem da decisão do responsável."),
    "especial_ri": (
        "Organizar procedimento especial do RI e suas fases antes da prática dos atos resultantes.",
        "Identifique a espécie: usucapião, retificação, REURB ou outra. Reúna requerimento e documentos e confira legitimidade, competência e disciplina específica.",
        "Abra o procedimento próprio, vincule título/matrícula e organize suas fases, exigências, notificações, publicações e decisões. Revise as evidências de cada etapa com o responsável antes de preparar atos de conclusão.",
        "Confira o histórico do procedimento, a decisão, os documentos que fundamentam cada ato e os registros e comunicações efetivamente realizados.",
        "Conflito, impugnação, ausência de requisito ou dúvida sobre notificações e prazos requer análise jurídica. O roteiro não autoriza pular fases."),
    "acervo": (
        "Localizar e conferir informação histórica, preservando sua origem e fidelidade.",
        "Identifique livro, registro, imagem e origem. Separe o que já existia do que será praticado agora.",
        "Use a pesquisa e as telas de conferência. Em importação, examine prévia, rejeições, correspondências e duplicidades antes de qualquer confirmação autorizada. Na ficha, compare o teor com a imagem/original.",
        "Confira número, livro, vínculos, conteúdo, origem e resultado nas consultas/certidões. Preserve o documento histórico.",
        "Divergência, renumeração, duplicidade e correção de ato praticado exigem a função autorizada e decisão do responsável."),
    "gestao": (
        "Acompanhar trabalho, obrigações e exceções com responsabilidade identificada.",
        "Identifique a rotina, seu período, fonte de dados, prazo e autoridade responsável. Confira as permissões da sua conta.",
        "Abra a fila ou cadastro correspondente. Examine pendências e documentos antes de registrar a ocorrência, atribuir responsabilidade ou confirmar a ação da tela.",
        "Confira o histórico, autor, data, resultado e comprovante. Para comunicações e arquivos externos, conserve a confirmação do envio/retorno.",
        "Configuração, alteração de acesso, correção financeira, comunicação sigilosa ou exceção normativa devem seguir o perfil e a autorização próprios."),
}

def familia(endpoint, nome="", grupo=""):
    s = (endpoint + " " + nome).lower()
    if endpoint.startswith("tr_"): return "aprendizagem"
    if any(x in s for x in ("reingresso", "cumprimento")): return "reingresso"
    if any(x in s for x in ("qualifica", "revisao_previa")): return "qualificacao"
    if any(x in s for x in ("devolutiva", "ri_nota", "exigencia")): return "nota"
    if any(x in s for x in ("procurac", "procuração", "substabelec", "mandato")): return "procuracao"
    if "notas_ata" in s or "ata notarial" in s: return "ata"
    if any(x in s for x in ("autentica", "pública forma")): return "autenticacao"
    if any(x in s for x in ("reconhecimento", "reconhecer", "autógrafo", "cartoes", "sinais")): return "firma"
    if "certid" in s or "traslado" in s: return "certidao"
    if "nascimento" in s: return "nascimento"
    if any(x in s for x in ("casamento", "habilitac", "proclama")): return "casamento"
    if "obito" in s or "óbito" in s: return "obito"
    if any(x in s for x in ("usucap", "retificacao", "reurb")): return "especial_ri"
    if any(x in s for x in ("livro3", "livro 3", "registro auxiliar")): return "livro3"
    if any(x in s for x in ("prenota", "ri_protocolo")): return "prenotacao"
    if "caixa_protocolo" in s or "atendimento" in s or endpoint.startswith("at_"): return "atendimento"
    if "caixa" in s or "depósito" in s or "deposito" in s or "recibo" in s: return "caixa"
    if any(x in s for x in ("import", "acervo", "digitaliza", "imagem")): return "acervo"
    if endpoint.startswith(("notas_", "nt_")) or "Tabelionato" in grupo: return "notas_ato"
    if endpoint.startswith(("rcpn", "rc_")) or "Civil" in grupo: return "rcpn"
    if endpoint.startswith("protesto") or "Protesto" in grupo: return "protesto"
    if endpoint.startswith(("rcpj", "rtd", "rg_")) or "RCPJ" in grupo or "RTD" in grupo: return "rtd_rpj"
    if endpoint.startswith("ri_") or "Imóveis" in grupo: return "ri_ato"
    return "gestao"

ESPECIFICOS = {
    "compra e venda": "Confira adquirentes e transmitentes, representação, objeto, título, preço, condições, documentos e tributos aplicáveis; confronte o instrumento com a situação do imóvel.",
    "doação": "Confira doador, donatário, aceitação e eventuais encargos, cláusulas e reserva de direitos. Submeta capacidade, disponibilidade, tributo e limites jurídicos ao responsável.",
    "inventário": "Identifique autor da herança, sucessores, cônjuge/companheiro, representação, bens e partilha. A admissibilidade da via e as condições jurídicas devem ser conferidas no caso concreto.",
    "divórcio": "Confira identidade, vínculo, regime, representação, vontade e questões de partilha. A admissibilidade e as condições do procedimento dependem da regra vigente e do responsável.",
    "união estável": "Confira declarantes, finalidade, período e regime/condições declaradas; examine documentos e a espécie adequada sem presumir fatos não comprovados.",
    "testamento": "Submeta a preparação ao tabelião/responsável e observe o sigilo, a manifestação pessoal de vontade e as formalidades específicas da espécie.",
    "hipoteca": "Identifique a garantia, obrigação, imóvel, partes e limites do título; confira a matrícula e o consentimento/representação aplicáveis antes de preparar o texto.",
    "alienação fiduciária": "Confira título, obrigação, partes, imóvel, condições da garantia e documentos; atos posteriores usam o procedimento específico da garantia.",
    "apostil": "Confira origem e espécie do documento, qualidade da assinatura/sinal e o procedimento próprio da apostila. Não confunda conferência formal com validação do conteúdo do documento.",
}
