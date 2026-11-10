"""Semente da casa de ensaio: gestao. Ver `layout_casa.py`.

A ÁREA É TUDO O QUE NÃO É DAS OUTRAS: o balcão (caixa, protocolo geral, cobrança, NFS-e), as
tarefas e os expedientes, a ouvidoria e o PLD, as despesas, os livros do núcleo, os modelos, o
painel de senhas, o WhatsApp, a automação, os robôs e o agente.

O PROTOCOLO DO CAIXA É A FICHA EM ABAS, e vale por estado: aberto, a pagar, pago, encerrado e com
exigência, mais o de mero cálculo e o do RI, que mudam quais abas existem. Os ids ficam em
`casa.ids["gestao_protocolo_<estado>"]`, e `test_layout_fichas_gestao` os abre. Toda chave que a
semente deixa em `casa.ids` leva `gestao_` na frente, porque o dicionário é de todas as áreas.

O QUE ESTA SEMENTE NÃO FAZ: rede, programa, nada na pasta de uma instalação real. Onde o caminho
natural pede isso (modelo de linguagem, banco, emissor de NFS-e, assinatura A3, impressão em PDF),
a linha entra pela função de domínio com o que o serviço devolveria, ou pela rota que não precisa
dele (`?formato=odt`, `?formato=html`).
"""
from __future__ import annotations

import base64
import io
import re
import traceback
from datetime import date, datetime, timedelta

import layout_ensaio as E

#: Rota com número que não tem como abrir aqui: endpoint -> o motivo.
SEM_SEMENTE: dict[str, str] = {
    "cobranca_boleto_pdf": (
        "o PDF do boleto mora em `centrais_cred.pasta_de_dados()`, que é `%PROGRAMDATA%\\CartorioGestao`, a pasta da "
        "instalação real: a trava barra ler e gravar ali, e a semente não pode pôr arquivo na pasta da produção. "
        "Sem o arquivo, a rota só devolve o aviso «ainda não foi baixado»."),
}

ESTADOS_DO_PROTOCOLO = ("aberto", "a_pagar", "pago", "encerrado", "com_exigencia", "orcamento", "ri")

ANA, JOAO, CARLA, BEATRIZ, MARIO = ("Ana Exemplo", "João Modelo", "Carla Exemplo", "Beatriz Exemplo",
                                    "Mario Exemplo")
CPF = "00000000191"
PIX_DA_CARLA = "carla@example.com"
VIGENCIA = 99001
#: (código interno, código TJ, descrição, emolumentos, FERC, FADEP, FEMP, FERRFIS) — valores de ensaio.
SERVICOS = (
    (990101, "13.18", "Autenticação de cópia de documento, por página", "5,50", "0,22", "0,17", "0,16", "0,16"),
    (990102, "14.5.1", "Certidão do registro civil em breve relato", "40,00", "1,60", "1,20", "1,28", "1,28"),
    (990103, "16.24.1", "Certidão negativa de propriedade de imóvel", "35,00", "1,40", "1,05", "1,12", "1,12"),
    (990105, "16.24.4", "Certidão de inteiro teor da matrícula", "45,00", "1,80", "1,35", "1,44", "1,44"),
)
PDF_MINIMO = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
PNG_1X1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


# ------------------------------------------------------------------ os ajudantes

def _centavos(valor: str) -> int:
    return int(valor.replace(".", "").replace(",", ""))


def _reais(centavos: int) -> str:
    inteiro, resto = divmod(int(centavos), 100)
    return f"{inteiro:,}".replace(",", ".") + f",{resto:02d}"


def _daqui_a(casa, dias: int) -> str:
    return (date.fromisoformat(casa.hoje) + timedelta(days=dias)).isoformat()


def _agora(casa) -> str:
    return f"{casa.hoje}T09:00:00"


def _postar(casa, endereco: str, esperado: str = "", **campos):
    """Manda o formulário e exige o redirecionamento que a tela daria quando dá certo.

    Quando não dá, o recado da tela (o `flash`) vai na falha: ele é o que diz o que faltou."""
    c = casa.cliente("ADMIN", "novo")
    r = casa.postar(endereco, _cliente=c, **campos)
    destino = r.headers.get("Location", "")
    if not (r.status_code == 302 and re.search(esperado, destino)):
        pagina = c.get(destino) if r.status_code == 302 and destino else r
        recados = E.ler_pagina(pagina.get_data(as_text=True)).flashes
        raise AssertionError(f"{endereco}: esperava ir a /{esperado}/, veio {r.status_code} {destino!r}; "
                             f"a tela diz: {recados}")
    return r


def _numero_no_fim(r, antes: str = "/") -> int:
    achado = re.search(rf"{re.escape(antes)}(\d+)(?:[/?#][^/]*)?$", r.headers["Location"])
    assert achado, f"sem número no destino: {r.headers['Location']!r}"
    return int(achado.group(1))


def _arquivo(nome: str, conteudo: bytes):
    return io.BytesIO(conteudo), nome


def _anotar(casa, **ids) -> None:
    """O que uma parte conta às outras e aos testes: `gestao_` na frente, porque `casa.ids` é de todas as áreas."""
    casa.ids.update({f"gestao_{nome}": valor for nome, valor in ids.items()})


def _um(casa, comando: str, parametros=()):
    linha = casa.um(comando, parametros)
    assert linha, f"a linha não nasceu: {comando} {parametros}"
    return linha


# ------------------------------------------------------------------ a tabela de emolumentos

def _tabela_de_emolumentos(casa) -> None:
    """Só uma vigência vale. Se outra semente já pôs a dela, os serviços entram nela."""
    atual = casa.um("SELECT codigo FROM cx_vigencias WHERE vigente = 1 ORDER BY codigo DESC LIMIT 1")
    vigencia = int(atual["codigo"]) if atual else VIGENCIA
    if not atual:
        casa.sql("INSERT INTO cx_vigencias (codigo, descricao, vigente, servicos, faixas, importado_em) "
                 "VALUES (%s, %s, 1, %s, 0, %s) ON CONFLICT (codigo) DO NOTHING",
                 (vigencia, "Vigência de ensaio do layout novo", len(SERVICOS), casa.hoje))
    for codigo, tj, descricao, *fundos in SERVICOS:
        casa.sql("INSERT INTO cx_servicos (codigo, codigo_tj, descricao, descricao_norm, ativo) "
                 "VALUES (%s, %s, %s, %s, 1) ON CONFLICT (codigo) DO NOTHING",
                 (codigo, tj, descricao, descricao.lower()))
        casa.sql("INSERT INTO cx_servico_valores (servico, vigencia, emolumentos, ferc, fadep, femp, ferrfis, "
                 "total) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (servico, vigencia) DO NOTHING",
                 (codigo, vigencia, *fundos, _reais(sum(_centavos(v) for v in fundos))))


# ------------------------------------------------------------------ o balcão

def _abrir_protocolo(casa, interessado: str, *, atribuicao: str, assunto: str, tipo: str = "SERVICO") -> int:
    r = _postar(casa, "/caixa/protocolos", r"^/caixa/protocolos/\d+$", acao="novo", interessado=interessado,
                interessado_documento=CPF, telefone="(00) 90000-0000", email="exemplo@exemplo.invalid",
                atribuicao=atribuicao, assunto=assunto, tipo=tipo, previsao_entrega=casa.hoje,
                documento_descricao="Requerimento assinado")
    pid = _numero_no_fim(r)
    linha = _um(casa, "SELECT situacao, tipo, atribuicao FROM cx_protocolos WHERE id = %s", (pid,))
    assert linha["situacao"] == "ABERTO" and linha["atribuicao"] == atribuicao, linha
    return pid


def _acrescentar(casa, pid: int, servico: int, quantidade: int = 1) -> None:
    antes = casa.um("SELECT count(*) AS n FROM cx_protocolo_atos WHERE protocolo_id = %s", (pid,))["n"]
    _postar(casa, f"/caixa/protocolos/{pid}/itens", rf"^/caixa/protocolos/{pid}$", acao="acrescentar",
            servico=str(servico), quantidade=str(quantidade))
    depois = casa.um("SELECT count(*) AS n FROM cx_protocolo_atos WHERE protocolo_id = %s", (pid,))["n"]
    assert depois == antes + 1, f"o item {servico} não entrou no protocolo {pid}"


def _situacao(casa, pid: int) -> str:
    return _um(casa, "SELECT situacao FROM cx_protocolos WHERE id = %s", (pid,))["situacao"]


def _exigencia(casa, pid: int, texto: str, atribuicao: str) -> int:
    r = _postar(casa, f"/caixa/protocolos/{pid}/exigencias", r"/exigencias#exigencia-\d+$", texto=texto,
                atribuicao=atribuicao, fundamento="", prazo_ate="", revisei_o_texto="")
    return _numero_no_fim(r, "#exigencia-")


def _balcao(casa) -> None:
    _tabela_de_emolumentos(casa)
    ids = casa.ids

    def abrir(estado: str, interessado: str, **campos) -> int:
        ids[f"gestao_protocolo_{estado}"] = novo = _abrir_protocolo(casa, interessado, **campos)
        return novo

    abrir("aberto", ANA, atribuicao="NOTAS", assunto="Pedido de certidão")
    assert _situacao(casa, ids["gestao_protocolo_aberto"]) == "ABERTO"

    pid = abrir("a_pagar", JOAO, atribuicao="RCPN", assunto="Segunda via")
    _acrescentar(casa, pid, 990101, quantidade=2)
    _acrescentar(casa, pid, 990102)
    assert _situacao(casa, pid) == "A_PAGAR"

    pid = abrir("pago", CARLA, atribuicao="RCPN", assunto="Certidão de nascimento")
    _acrescentar(casa, pid, 990102)
    _acrescentar(casa, pid, 990101)
    _postar(casa, f"/caixa/protocolos/{pid}/itens", rf"^/caixa/protocolos/{pid}$", acao="quitar_todos",
            forma_pagamento="PIX")
    assert _situacao(casa, pid) == "PAGO"
    r = _postar(casa, f"/caixa/protocolos/{pid}/recibo", r"^/caixa/recibo/\d+/odt$")
    ids["gestao_recibo_do_protocolo_pago"] = int(re.search(r"/recibo/(\d+)/odt", r.headers["Location"]).group(1))

    pid = abrir("com_exigencia", MARIO, atribuicao="OUTROS", assunto="Autenticação de cópias")
    _acrescentar(casa, pid, 990101)
    aberta = _exigencia(casa, pid, "trazer o documento de identidade do requerente\nassinar o requerimento",
                        "OUTROS")
    cumprida = _exigencia(casa, pid, "apresentar a procuração com firma reconhecida", "OUTROS")
    _postar(casa, f"/caixa/protocolos/{pid}/exigencias/{cumprida}/cumprida", rf"/exigencias#exigencia-{cumprida}$",
            observacao="Trouxe o documento no balcão.")
    cancelada = _exigencia(casa, pid, "apresentar o comprovante de residência", "OUTROS")
    _postar(casa, f"/caixa/protocolos/{pid}/exigencias/{cancelada}/cancelar", rf"/exigencias#exigencia-{cancelada}$",
            motivo="A exigência foi aberta por engano no balcão.")
    _anotar(casa, exigencia_aberta=aberta, exigencia_cumprida=cumprida, exigencia_cancelada=cancelada)
    import protocolo_documentos as PDOC
    _postar(casa, f"/caixa/protocolos/{pid}/documentos", rf"^/caixa/protocolos/{pid}",
            documento=_arquivo("identidade.pdf", PDF_MINIMO), tipo=PDOC.TIPOS_DE_DOCUMENTO[0][0],
            descricao="Documento de identidade do requerente")
    numero = _um(casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (pid,))["numero"]
    _postar(casa, "/tarefas", rf"^/caixa/protocolos/{pid}", title=f"Protocolo {numero} — {MARIO}", sector="",
            priority="MEDIA", description="Conferir o protocolo com o requerente.", vincular_tabela="cx_protocolos",
            vincular_referencia=numero, voltar=f"/caixa/protocolos/{pid}#tarefas")

    pid = abrir("encerrado", BEATRIZ, atribuicao="FIRMAS", assunto="Reconhecimento de firma")
    _acrescentar(casa, pid, 990101)
    _exigencia(casa, pid, "trazer o documento original para conferência", "FIRMAS")
    _postar(casa, f"/caixa/protocolos/{pid}", rf"^/caixa/protocolos/{pid}$", acao="encerrar",
            encerramento="ENTREGUE", motivo="O cliente retirou o documento e o atendimento foi resolvido.")
    assert _situacao(casa, pid) == "ENTREGUE"

    pid = abrir("orcamento", ANA, atribuicao="NOTAS", assunto="Cálculo de emolumentos", tipo="ORCAMENTO")
    _acrescentar(casa, pid, 990103)

    # O cálculo já quitado e o que virou serviço: as duas formas da ficha, e a tela de corrigir com gente.
    pid = abrir("calculo_quitado", ANA, atribuicao="NOTAS", assunto="Serviço aberto como cálculo", tipo="ORCAMENTO")
    _acrescentar(casa, pid, 990103)
    _postar(casa, f"/caixa/protocolos/{pid}/itens", rf"^/caixa/protocolos/{pid}$", acao="quitar_todos",
            forma_pagamento="PIX")
    casa.pagina("caixa_protocolo", protocolo_id=pid)
    pid = abrir("calculo_virou_servico", ANA, atribuicao="NOTAS", assunto="Cálculo que virou serviço", tipo="ORCAMENTO")
    _postar(casa, f"/caixa/protocolos/{pid}/virar-servico", rf"^/caixa/protocolos/{pid}$", servico_desde=casa.hoje, motivo="")
    casa.pagina("caixa_protocolo", protocolo_id=pid)
    casa.pagina("caixa_calculos_quitados")

    pid = abrir("ri", JOAO, atribuicao="RI", assunto="Certidão de inteiro teor")
    _acrescentar(casa, pid, 990105)

    for estado in ESTADOS_DO_PROTOCOLO:
        casa.pagina("caixa_protocolo", protocolo_id=ids[f"gestao_protocolo_{estado}"])
    documento = _um(casa, "SELECT id FROM attachments WHERE entity_type = 'PROTOCOLO' AND entity_id = %s",
                    (ids["gestao_protocolo_com_exigencia"],))["id"]
    _anotar(casa, documento_do_protocolo=documento)
    casa.pagina("attachment_view", attachment_id=documento)
    casa.pagina("attachment_download", attachment_id=documento)
    casa.pagina("caixa_protocolo_atos_da_tabela", protocolo_id=ids["gestao_protocolo_a_pagar"])
    casa.pagina("caixa_protocolo_atos_da_tabela", {"busca": "certid"}, protocolo_id=ids["gestao_protocolo_a_pagar"])
    casa.pagina("caixa_exigencias", protocolo_id=ids["gestao_protocolo_com_exigencia"])
    casa.pagina("caixa_exigencias", protocolo_id=ids["gestao_protocolo_aberto"])
    # O PDF do papel pede o LibreOffice; o `.odt` é o mesmo papel, sem programa.
    for exigencia in (aberta, cumprida, cancelada):
        casa.pagina("caixa_exigencia_papel", {"formato": "odt"}, protocolo_id=ids["gestao_protocolo_com_exigencia"],
                    exigencia_id=exigencia)
    casa.pagina("caixa_orcamento", protocolo_id=ids["gestao_protocolo_a_pagar"])
    casa.pagina("caixa_orcamento", protocolo_id=ids["gestao_protocolo_orcamento"])
    casa.pagina("caixa_recibo_odt", recibo_id=ids["gestao_recibo_do_protocolo_pago"])


def _andamento_e_inacabados(casa) -> None:
    ids = casa.ids
    a_pagar, pago, aberto = ids["gestao_protocolo_a_pagar"], ids["gestao_protocolo_pago"], ids["gestao_protocolo_aberto"]
    _postar(casa, f"/andamento/protocolo-geral/{a_pagar}", rf"/andamento/protocolo-geral/{a_pagar}$",
            acao="consentir", canal="EMAIL")
    _postar(casa, f"/andamento/protocolo-geral/{pago}", rf"/andamento/protocolo-geral/{pago}$", acao="pronto")
    _um(casa, "SELECT id FROM av_consentimentos WHERE origem_id = %s AND ativo = 1", (a_pagar,))
    assert _um(casa, "SELECT pronto_retirar_em FROM cx_protocolos WHERE id = %s", (pago,))["pronto_retirar_em"]
    casa.pagina("andamento_protocolo_geral", protocolo_id=a_pagar)
    casa.pagina("andamento_protocolo_geral", protocolo_id=pago)
    casa.pagina("andamento_protocolo_geral", protocolo_id=aberto)

    _postar(casa, f"/inacabados/anotar/cx_protocolos/{aberto}", r"^/inacabados$",
            texto="Aguardando o cliente trazer o documento.", responsavel=BEATRIZ, ate=_daqui_a(casa, 7))
    _um(casa, "SELECT id FROM ex_anotacoes WHERE tabela = 'cx_protocolos' AND item_id = %s", (aberto,))
    casa.pagina("inacabados_anotar", tabela="cx_protocolos", item_id=aberto)
    casa.pagina("inacabados_anotar", tabela="cx_protocolos", item_id=a_pagar)


def _cobranca(casa) -> None:
    """Três boletos de um protocolo à parte: o depósito prévio da cobrança lançada é movimento de caixa, e
    no protocolo «a pagar» ele faria a ficha deixar de ser o estado que a semente promete."""
    import cobranca as CB
    pid = _abrir_protocolo(casa, JOAO, atribuicao="RCPN", assunto="Segunda via, com boleto")
    _acrescentar(casa, pid, 990102)
    _anotar(casa, protocolo_da_cobranca=pid)
    campos = dict(protocolo_id=str(pid), valor="100,00", vencimento=_daqui_a(casa, 5), nome=JOAO, documento=CPF,
                  email="exemplo@exemplo.invalid", logradouro="Rua da Demonstração", numero="100",
                  complemento="", bairro="Centro", cidade="Cidade Exemplo", uf="MA", cep="00000000",
                  mensagem=f"Protocolo {pid}")
    novas = []
    for _ in range(3):
        r = _postar(casa, "/caixa/cobranca/nova", r"^/caixa/cobranca/\d+$", **campos)
        novas.append(_numero_no_fim(r))
    a_emitir, aberta, lancada = novas
    quando = datetime.now().astimezone().replace(microsecond=0)

    def do_banco(cobranca: int, **extra) -> dict:
        return {"banco_id": f"ensaio-{cobranca:04d}", "nosso_numero": f"{cobranca:08d}", "linha_digitavel": "0" * 47,
                "codigo_barras": "0" * 44, "pix_copia_e_cola": "00020126ENSAIO", "banco_status": "EMABERTO", **extra}

    with casa.transacao() as con:
        CB.gravar_resposta(con, aberta, {"situacao": CB.ABERTA, **do_banco(aberta)}, por="Mario Exemplo",
                           agora=quando)
        CB.gravar_resposta(con, lancada, {"situacao": CB.RECEBIDA, **do_banco(
            lancada, banco_status="RECEBIDO", valor_recebido=10000, data_pagamento=casa.hoje,
            forma_recebida="PIX")}, por="Mario Exemplo", agora=quando)
    _postar(casa, f"/caixa/cobranca/{lancada}/lancar", rf"^/caixa/cobranca/{lancada}$")
    assert _um(casa, "SELECT situacao FROM cb_cobrancas WHERE id = %s", (lancada,))["situacao"] == "LANCADA"
    assert _um(casa, "SELECT situacao FROM cb_cobrancas WHERE id = %s", (aberta,))["situacao"] == "ABERTA"
    _anotar(casa, cobranca_a_emitir=a_emitir, cobranca_aberta=aberta, cobranca_lancada=lancada)
    for cobranca in novas:
        casa.pagina("cobranca_ficha", cobranca_id=cobranca)


NFSE_ENSAIO = """<?xml version="1.0" encoding="UTF-8"?>
<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01"><infNFSe Id="NFS{chave}">
<xLocEmi>Cidade Exemplo</xLocEmi><xLocPrestacao>Cidade Exemplo</xLocPrestacao><nNFSe>1</nNFSe>
<cLocIncid>0000000</cLocIncid><xLocIncid>Cidade Exemplo</xLocIncid>
<xTribNac>Serviços de registros públicos, cartorários e notariais.</xTribNac>
<verAplic>Ensaio_1.01</verAplic><ambGer>2</ambGer><tpEmis>1</tpEmis><procEmi>1</procEmi><cStat>100</cStat>
<dhProc>{quando}-03:00</dhProc><nDFSe>1</nDFSe>
<emit><CNPJ>00000001000155</CNPJ><xNome>SERVENTIA DE ENSAIO</xNome></emit>
<valores><vBC>46.67</vBC><pAliqAplic>5.00</pAliqAplic><vISSQN>2.33</vISSQN><vTotalRet>0.00</vTotalRet><vLiq>46.67</vLiq></valores>
</infNFSe></NFSe>"""


def _nfse(casa) -> None:
    ids = casa.ids
    recibo = ids["gestao_recibo_do_protocolo_pago"]
    chave = "0000000200000000000000000000000000000000000000001"
    xml = NFSE_ENSAIO.format(chave=chave, quando=f"{casa.hoje}T09:00:00")
    nota = casa.inserir("nfse_notas", recibo_id=recibo, provedor="nacional", ambiente="homologacao",
                        situacao="EMITIDA", serie="1", numero_dps=1, id_dps="DPS00000000000000000000000000000000000001",
                        tomador_documento=CPF, tomador_nome=CARLA, valor_servico=4667, aliquota="5,00",
                        valor_iss=233, xml_dps="<DPS/>", chave=chave, numero_nfse="1", xml_nfse=xml,
                        criado_em=_agora(casa), criado_por="Mario Exemplo", emitida_em=_agora(casa))
    chave_cancelada = "0000000200000000000000000000000000000000000000002"
    cancelada = casa.inserir("nfse_notas", recibo_id=recibo, provedor="nacional", ambiente="homologacao",
                             situacao="CANCELADA", serie="1", numero_dps=2,
                             id_dps="DPS00000000000000000000000000000000000002", tomador_documento=CPF,
                             tomador_nome=CARLA, valor_servico=4667, aliquota="5,00", valor_iss=233,
                             xml_dps="<DPS/>", chave=chave_cancelada, numero_nfse="2",
                             xml_nfse=NFSE_ENSAIO.format(chave=chave_cancelada, quando=f"{casa.hoje}T09:00:00"),
                             criado_em=_agora(casa), criado_por="Mario Exemplo", emitida_em=_agora(casa),
                             cancelada_em=_agora(casa), cancelada_por="Mario Exemplo", motivo_cancelamento="1")
    _anotar(casa, nota_fiscal=nota, nota_fiscal_cancelada=cancelada)
    casa.pagina("nfse_recibo", recibo_id=recibo)
    casa.pagina("nfse_xml", nota_id=nota)
    # O DANFSe em PDF sai pelo Chrome; o mesmo papel em HTML não precisa de programa.
    for n in (nota, cancelada):
        casa.pagina("nfse_danfse", {"formato": "html"}, nota_id=n)


# ------------------------------------------------------------------ o dia a dia (app.py)

def _tarefas(casa) -> None:
    ids = casa.ids

    def nova(titulo: str, **extra) -> int:
        r = _postar(casa, "/tarefas", r"^/tarefas/\d+$", title=titulo, description=f"{titulo}.", sector="",
                    system_name="", priority="MEDIA", due_date=_daqui_a(casa, 10), legal_ref="", **extra)
        return _numero_no_fim(r)

    aberta = nova("Conferir o livro de visitas", andamento="Início da conferência.", evidence_required="1")
    _postar(casa, f"/tarefas/{aberta}/evidence", rf"^/tarefas/{aberta}$", description="Foto do livro",
            file=_arquivo("evidencia.pdf", PDF_MINIMO))
    anexo = _um(casa, "SELECT id FROM attachments WHERE entity_type = 'TASK' AND entity_id = %s", (aberta,))["id"]

    suspensa = nova("Aguardar a certidão do cliente")
    _postar(casa, f"/tarefas/{suspensa}", rf"^/tarefas/{suspensa}$", action="suspender", modo="PRAZO",
            motivo="Aguardando o cliente trazer a certidão.", ate=_daqui_a(casa, 5), condicao="")
    concluida = nova("Arquivar os documentos do mês")
    _postar(casa, f"/tarefas/{concluida}", rf"^/tarefas/{concluida}$", action="concluir")
    assert _um(casa, "SELECT status FROM tasks WHERE id = %s", (concluida,))["status"] == "CONCLUIDA"
    _anotar(casa, tarefa_aberta=aberta, tarefa_suspensa=suspensa, tarefa_concluida=concluida, anexo=anexo)
    for tarefa in (aberta, suspensa, concluida):
        casa.pagina("task_detail", task_id=tarefa)
    casa.pagina("task_dossier", task_id=aberta)
    casa.pagina("attachment_download", attachment_id=anexo)
    casa.pagina("attachment_view", attachment_id=anexo)


def _expedientes(casa) -> None:
    ids = casa.ids

    def novo(assunto: str) -> int:
        r = _postar(casa, "/expedientes", r"^/expedientes/\d+$", source="Malote", external_reference="Ofício 1/2026",
                    sender="Juízo de Cidade Exemplo", subject=assunto, category="Para cumprimento", sector="",
                    received_at=casa.hoje, deadline_start=casa.hoje, deadline_days="10", priority="ALTA",
                    assigned_user_id="", backup_user_id="", notes="Ofício de exemplo.")
        return _numero_no_fim(r)

    aberto = novo("Ofício para cumprimento")
    _postar(casa, f"/expedientes/{aberto}/evidence", rf"^/expedientes/{aberto}$", description="Ofício digitalizado",
            file=_arquivo("oficio.pdf", PDF_MINIMO))
    respondido = novo("Pedido de informação ao cartório")
    _postar(casa, f"/expedientes/{respondido}/stage", rf"^/expedientes/{respondido}$", stage="RESPONDIDO",
            response_reference="Resposta 1/2026")
    assert _um(casa, "SELECT completed_at FROM expedientes WHERE id = %s", (respondido,))["completed_at"]
    _anotar(casa, expediente_aberto=aberto, expediente_respondido=respondido)
    casa.pagina("expediente_detail", expediente_id=aberto)
    casa.pagina("expediente_detail", expediente_id=respondido)


def _rotinas(casa) -> None:
    """Recorrência, checklist, item de TI, LGPD e a inspeção, cada um pela tela do seu cadastro."""
    ids = casa.ids
    _postar(casa, "/recorrencias", r"^/recorrencias$", title="Conferir os selos do mês", system_name="Selos",
            sector="", frequency="MONTHLY", due_day="10", due_month="", lead_days="5",
            next_due_date=_daqui_a(casa, 15), notes="Conferência mensal.")
    ids["gestao_recorrencia"] = _um(casa, "SELECT id FROM recurring_obligations WHERE title = %s",
                             ("Conferir os selos do mês",))["id"]
    casa.pagina("recurrence_detail", recurrence_id=ids["gestao_recorrencia"])

    _postar(casa, "/checklists", r"^/checklists$", name="Abertura do balcão", sector="",
            items="Ligar os computadores\nConferir o caixa\nAbrir o painel de senhas")
    modelo = _um(casa, "SELECT id FROM checklist_templates WHERE name = %s", ("Abertura do balcão",))["id"]
    em_andamento = _numero_no_fim(_postar(casa, f"/checklists/{modelo}/start", r"^/checklists/run/\d+$",
                                          reference="Balcão do dia"), "/run/")
    _, itens = casa.db.get_checklist_run(em_andamento)
    r = casa.postar(f"/checklists/run/{em_andamento}", checked=str(itens[0]["id"]), action="save")
    assert r.status_code == 200, r.status_code      # salvar sem concluir fica na própria tela
    concluido = _numero_no_fim(_postar(casa, f"/checklists/{modelo}/start", r"^/checklists/run/\d+$",
                                       reference="Balcão da véspera"), "/run/")
    _, itens = casa.db.get_checklist_run(concluido)
    _postar(casa, f"/checklists/run/{concluido}", r"^/checklists$", checked=[str(i["id"]) for i in itens],
            action="finish")
    _anotar(casa, checklist_em_andamento=em_andamento, checklist_concluido=concluido)
    casa.pagina("checklist_run", run_id=em_andamento)
    casa.pagina("checklist_run", run_id=concluido)

    _postar(casa, "/ti", r"^/ti$", kind="Certificado digital", name="Certificado A3 do oficial", identifier="A3-0001",
            location="Cofre", status="ATENCAO", expiry_date=_daqui_a(casa, 30), last_check_date=casa.hoje,
            notes="Renovar antes do vencimento.")
    ids["gestao_ativo_ti"] = _um(casa, "SELECT id FROM assets WHERE name = %s", ("Certificado A3 do oficial",))["id"]
    casa.pagina("asset_detail", asset_id=ids["gestao_ativo_ti"])

    _postar(casa, "/lgpd", r"^/lgpd$", item_type="Inventário de dados", title="Inventário dos dados do balcão",
            status="EM_REVISAO", review_date=_daqui_a(casa, 60), notes="Revisão semestral.")
    ids["gestao_lgpd"] = _um(casa, "SELECT id FROM lgpd_items WHERE title = %s", ("Inventário dos dados do balcão",))["id"]
    casa.pagina("lgpd_detail", item_id=ids["gestao_lgpd"])

    inspecao = casa.inserir("inspections", title="Inspeção ordinária de exemplo", report_date=casa.hoje, active=1,
                            created_at=_agora(casa))
    for i, titulo in enumerate(("Atualizar o livro de visitas", "Conferir o depósito prévio", "Revisar os modelos"), 1):
        casa.db.create_task({"source_type": "INSPECAO", "inspection_id": inspecao, "title": titulo,
                             "sector": "Notas", "priority": "ALTA", "status": "ABERTA", "due_days": 10 * i},
                            ids["admin"])
    _postar(casa, f"/inspecoes/{inspecao}", rf"^/inspecoes/{inspecao}$", start_date=casa.hoje)
    ids["gestao_inspecao"] = inspecao
    casa.pagina("inspection_detail", inspection_id=inspecao)


def _avisos(casa) -> None:
    ids = casa.ids
    _postar(casa, "/admin/avisos/novo", r"^/avisos$", titulo="Conferir o caixa antes de sair",
            corpo="Feche o caixa e confira o dinheiro antes de ir embora.")
    _postar(casa, "/admin/avisos/novo", r"^/avisos$", titulo="Vencimento da guia mensal",
            corpo="A guia vence no dia indicado.", barra_campos="1", modo="BARRA", barra_dia_mes="5",
            barra_papeis=["ADMIN", "USER"])
    ids["gestao_aviso"] = _um(casa, "SELECT id FROM nu_avisos WHERE titulo = %s", ("Conferir o caixa antes de sair",))["id"]
    ids["gestao_aviso_da_barra"] = _um(casa, "SELECT id FROM nu_avisos WHERE titulo = %s", ("Vencimento da guia mensal",))["id"]
    for aviso in casa.ler("SELECT id FROM nu_avisos WHERE ativo = 1 ORDER BY id"):
        casa.pagina("nu_avisos_detalhe", aviso_id=aviso["id"])
        casa.pagina("nu_avisos_admin_editar", aviso_id=aviso["id"])


def _senhas(casa) -> None:
    import cofre_cred as COFRE
    ids = casa.ids
    normal = _postar(casa, "/atendimento", r"^/atendimento/\d+/imprimir$", action="new", service_type="Geral",
                     imprimir="1")
    preferencial = _postar(casa, "/atendimento", r"^/atendimento/\d+/imprimir$", action="new", service_type="Geral",
                           priority="1", imprimir="1")
    ids["gestao_senha_normal"] = _numero_no_fim(normal, "/atendimento/")
    ids["gestao_senha_preferencial"] = _numero_no_fim(preferencial, "/atendimento/")
    for senha in (ids["gestao_senha_normal"], ids["gestao_senha_preferencial"]):
        casa.pagina("senhas_imprimir", ticket_id=senha)
    _postar(casa, "/atendimento/painel-da-tv", r"/atendimento/painel-da-tv$", acao="gerar")
    with casa.con() as con:
        chave = COFRE.ler_segredo(con, COFRE.SENHAS, "chave_tv")
    assert chave, "a chave da TV não foi gravada"
    casa.pagina("senhas_tv", chave=chave)
    casa.pagina("senhas_tv_estado", chave=chave)


def _ouvidoria(casa) -> None:
    ids = casa.ids
    base = dict(canal="BALCAO", setor="GERAL", responsavel_id=str(ids["admin"]), recebida_em=casa.hoje,
                relato="A pessoa disse que esperou muito tempo na fila do balcão e não foi avisada.")

    def registrar(**campos) -> int:
        r = _postar(casa, "/administrativo/ouvidoria", r"^/administrativo/ouvidoria/\d+$", **{**base, **campos})
        return _numero_no_fim(r)

    reclamacao = registrar(tipo="RECLAMACAO", assunto="Demora no atendimento", nome=ANA, contato="(00) 90000-0000")
    em_analise = registrar(tipo="DENUNCIA", assunto="Cobrança indevida", anonima="1")
    _postar(casa, f"/administrativo/ouvidoria/{em_analise}/analise", rf"/ouvidoria/{em_analise}$")
    respondida = registrar(tipo="SUGESTAO", assunto="Painel de senhas na recepção", nome=JOAO)
    _postar(casa, f"/administrativo/ouvidoria/{respondida}/responder", rf"/ouvidoria/{respondida}$",
            resposta="Agradecemos a sugestão: o painel de senhas já está em uso na recepção.")
    encerrada = registrar(tipo="ELOGIO", assunto="Atendimento no balcão", nome=CARLA)
    _postar(casa, f"/administrativo/ouvidoria/{encerrada}/encerrar", rf"/ouvidoria/{encerrada}$",
            motivo="Elogio registrado e repassado à equipe.")
    situacoes = {m: _um(casa, "SELECT situacao FROM ou_manifestacoes WHERE id = %s", (m,))["situacao"]
                 for m in (reclamacao, em_analise, respondida, encerrada)}
    assert list(situacoes.values()) == ["ABERTA", "EM_ANALISE", "RESPONDIDA", "ENCERRADA"], situacoes
    for manifestacao in situacoes:
        casa.pagina("ouvidoria_ficha", manifestacao_id=manifestacao)


def _pld(casa) -> None:
    ids = casa.ids
    casos = []
    for i in range(3):
        r = _postar(casa, "/administrativo/pld/abrir", r"^/administrativo/pld/caso/\d+$",
                    referencia=f"selo AVERBA000000PLD000000000{i + 1}", data=casa.hoje, atribuicao="NOTAS",
                    valor="250.000,00", motivo="reanálise pedida pela inspeção de exemplo")
        casos.append(_numero_no_fim(r, "/caso/"))
    a_analisar, a_comunicar, comunicada = casos
    fundamentacao = "Valor incompatível com a renda declarada, pagamento sem origem identificada."
    for caso in (a_comunicar, comunicada):
        _postar(casa, f"/administrativo/pld/caso/{caso}/analise", rf"/caso/{caso}$", conclusao="COMUNICAR",
                fundamentacao=fundamentacao)
    _postar(casa, f"/administrativo/pld/caso/{comunicada}/enviado", rf"/caso/{comunicada}$", numero_coaf="987654",
            data_envio=casa.hoje, recibo=_arquivo("recibo.pdf", PDF_MINIMO))
    estados = [_um(casa, "SELECT situacao FROM pld_casos WHERE id = %s", (c,))["situacao"] for c in casos]
    assert estados == ["A_ANALISAR", "A_COMUNICAR", "COMUNICADA"], estados
    _anotar(casa, pld_a_analisar=a_analisar, pld_a_comunicar=a_comunicar, pld_comunicada=comunicada)
    for caso in casos:
        casa.pagina("pld_caso", caso_id=caso)
    casa.pagina("pld_nao_ocorrencia", ano=date.fromisoformat(casa.hoje).year - 1)


def _correcoes(casa) -> None:
    """Quatro propostas, uma em cada fim: espera, executada, recusada e falha."""
    ids = casa.ids
    motivo = "O pagamento foi lançado no título errado; a Central confirma o outro título pago desde agosto."
    afirmacao = ("Afirmo, sob minha responsabilidade, que conferi a prova juntada e que esta correção de "
                 "ofício deve ser executada como proposta.")

    def titulo(numero: str) -> int:
        t = casa.inserir("pt_titulos", especie="DMI", numero_titulo=numero, protocolo="2610310001",
                         valor_centavos=10000, saldo_centavos=10000, situacao="PAGO", origem="CRA",
                         origem_chave=f"layout:gestao:{numero}", apresentante_codigo="237",
                         cedente_nome="Credora Exemplo", cedente_uf="MA", criado_em=_agora(casa))
        for tipo, cancelado in (("APONTAMENTO", 0), ("PAGAMENTO", 1)):
            casa.inserir("pt_atos", titulo_id=t, tipo=tipo, data_ato=casa.hoje, detalhe_json="{}", origem="MANUAL",
                         cancelado=cancelado, motivo_cancelamento="Selo não emitido: ensaio." if cancelado else None,
                         criado_em=_agora(casa), criado_por=MARIO)
        return t

    def propor(t: int) -> int:
        r = _postar(casa, "/administrativo/correcoes-de-oficio/propor", r"^/administrativo/correcoes-de-oficio/\d+$",
                    tipo="PT_SITUACAO_SUSTENTADA", titulo_ids=str(t), motivo=motivo, acao="propor")
        return _numero_no_fim(r)

    base = "/administrativo/correcoes-de-oficio"
    t1, t2, t3, t4 = (titulo(f"GESTAO/{i}") for i in range(1, 5))
    proposta, executada, recusada, falhou = propor(t1), propor(t2), propor(t3), propor(t4)
    _postar(casa, f"{base}/{executada}/aprovar", rf"{base}/{executada}$", afirmo="1", afirmacao=afirmacao)
    _postar(casa, f"{base}/{recusada}/recusar", rf"{base}/{recusada}$",
            motivo_da_recusa="o pagamento vai ser relançado pela ficha do título")
    casa.inserir("pt_atos", titulo_id=t4, tipo="PAGAMENTO", data_ato=casa.hoje, detalhe_json="{}", origem="MANUAL",
                 cancelado=0, criado_em=_agora(casa), criado_por=MARIO)
    _postar(casa, f"{base}/{falhou}/aprovar", rf"{base}/{falhou}$", afirmo="1", afirmacao=afirmacao)
    situacoes = [_um(casa, "SELECT situacao FROM correcoes_de_oficio WHERE id = %s", (c,))["situacao"]
                 for c in (proposta, executada, recusada, falhou)]
    assert situacoes == ["PROPOSTA", "APROVADA_EXECUTADA", "RECUSADA", "FALHOU"], situacoes
    _anotar(casa, correcao_proposta=proposta, correcao_executada=executada, correcao_recusada=recusada,
            correcao_falhou=falhou)
    for correcao in (proposta, executada, recusada, falhou):
        casa.pagina("correcoes_de_oficio_ficha", correcao_id=correcao)


def _despesas(casa) -> None:
    """As despesas são do titular (`titular_privado`), e o ADMIN do ensaio leva o nome dele
    (`layout_casa.preparar_sessao`): é por isso que as fichas abrem aqui, e não com 403."""
    import despesas as DP
    ids = casa.ids
    base = "/administrativo/despesas"

    def cadastrar(descricao: str, valor: str) -> int:
        _postar(casa, f"{base}/nova", rf"^{base}/\d+$", beneficiario_nome=CARLA, beneficiario_documento=CPF,
                valor=valor, vencimento=_daqui_a(casa, 5), forma=DP.PIX_CHAVE, codigo=PIX_DA_CARLA,
                descricao=descricao, categoria="PESSOAL", documento_especie="Recibo de pagamento",
                documento_numero="1", contato_email=PIX_DA_CARLA, contato_whatsapp="")
        return _um(casa, "SELECT max(id) AS id FROM dp_despesas")["id"]

    aguardando = cadastrar("Salário líquido da escrevente, competência do mês", "1.500,00")
    autorizada = cadastrar("Salário líquido da escrevente, adiantamento do mês", "800,00")
    # A AUTORIZAÇÃO CONFERE A REVISÃO (#317, 04/11/2026): a ficha manda o hash dos dados que o
    # oficial viu; sem ele, a tela recusa «os dados mudaram» e a despesa fica aguardando.
    import despesas_fluxo as DF
    revisao = DF.revisao(dict(_um(casa, "SELECT * FROM dp_despesas WHERE id = %s", (autorizada,))))
    # E A CONFERÊNCIA DO DESTINATÁRIO (#384, 10/11/2026): antes de autorizar, o ordenador confere no
    # banco o nome e o CPF de quem recebe, diz de onde conferiu e marca a ciência — como na ficha.
    _postar(casa, f"{base}/{autorizada}/autorizar", rf"^{base}/{autorizada}$", revisao=revisao,
            destino_nome=CARLA, destino_documento=CPF, destino_ciencia="1",
            destino_fonte="Conferido no aplicativo do banco, pela chave Pix cadastrada.")
    paga = cadastrar("Salário líquido da escrevente, competência anterior", "1.935,32")
    casa.sql("UPDATE dp_despesas SET situacao = %s, data_pagamento = %s, banco_e2e = %s WHERE id = %s",
             (DP.PAGA, casa.hoje, "E00000000202610301200abcdefghijk", paga))
    cancelada = cadastrar("Material de escritório comprado em duplicidade", "120,00")
    _postar(casa, f"{base}/{cancelada}/cancelar", rf"^{base}/{cancelada}$", motivo="Compra em duplicidade.")
    estados = [_um(casa, "SELECT situacao FROM dp_despesas WHERE id = %s", (d,))["situacao"]
               for d in (aguardando, autorizada, paga, cancelada)]
    assert estados == [DP.AGUARDANDO, DP.AUTORIZADA, DP.PAGA, DP.CANCELADA], estados
    _anotar(casa, despesa_aguardando=aguardando, despesa_autorizada=autorizada, despesa_paga=paga,
            despesa_cancelada=cancelada)
    for despesa in (aguardando, autorizada, paga, cancelada):
        casa.pagina("despesas_ficha", despesa_id=despesa)
    casa.pagina("despesas_demonstrativo", despesa_id=paga)

    _postar(casa, f"{base}/recorrentes/nova", rf"^{base}/recorrentes$", descricao="Salário líquido da escrevente",
            categoria="PESSOAL", beneficiario_nome=CARLA, beneficiario_documento=CPF, forma=DP.PIX_CHAVE,
            chave_pix=PIX_DA_CARLA, valor="2.000,00", dia_vencimento="10", antecedencia_dias="5",
            documento_especie="Recibo de pagamento", primeiro_mes=casa.hoje[:7], ultimo_mes="")
    ids["gestao_despesa_recorrente"] = _um(casa, "SELECT max(id) AS id FROM dp_recorrentes")["id"]
    casa.pagina("despesas_recorrente", recorrente_id=ids["gestao_despesa_recorrente"])


def _livros(casa) -> None:
    """O Diário do mês que acabou: uma despesa lançada e a fotografia gerada."""
    ids = casa.ids
    primeiro = date.fromisoformat(casa.hoje[:8] + "01")
    anterior = (primeiro - timedelta(days=1)).isoformat()[:7]
    _postar(casa, "/livros-obrigatorios/diario/despesas", r"^/livros-obrigatorios/diario", data=f"{anterior}-10",
            descricao="Energia elétrica da sede, conta do mês", documento_especie="Fatura",
            documento_numero="0001", valor="45,00")
    r = _postar(casa, "/livros-obrigatorios/diario/gerar", r"/livros-obrigatorios/diario/versao/\d+$", mes=anterior)
    ids["gestao_diario"] = _numero_no_fim(r, "/versao/")
    casa.pagina("livro_diario_versao", geracao_id=ids["gestao_diario"])
    ids["gestao_mes_anterior"] = anterior


def _nucleo(casa) -> None:
    """Um livro aberto e outro encerrado, e o mês de termos diários juntado e assinado."""
    import encerramento_mensal as EM
    import escrituracao as ESC
    from ri_schema import eh_dia_util, ler_feriados_locais
    from ri_web import data_por_extenso
    from serventia import dados as dados_serventia
    ids = casa.ids

    serie = "NT_TESTAMENTO_CERRADO"
    velho = _um(casa, "SELECT id FROM nu_livros WHERE serie = %s AND encerrado = 0 ORDER BY id DESC LIMIT 1",
                (serie,))["id"]
    _postar(casa, f"/nucleo/livros/{velho}/encerrar", rf"^/nucleo/livros/{velho}$", motivo="Livro encerrado no ensaio.")
    r = _postar(casa, "/nucleo/livros/abrir", r"^/nucleo/livros/\d+$", serie=serie, folhas="200",
                descricao="Livro novo do ensaio")
    ids["gestao_livro_aberto"], ids["gestao_livro_encerrado"] = _numero_no_fim(r), velho
    # Cada série tem a sua regra de folha, e a ficha confere o livro por ela: abrem-se todos os da carga.
    for livro in casa.ler("SELECT id FROM nu_livros ORDER BY id"):
        casa.pagina("nucleo_livro", livro_id=livro["id"])
    casa.pagina("nucleo_livro_termo", livro_id=ids["gestao_livro_aberto"], qual="abertura")
    casa.pagina("nucleo_livro_termo", livro_id=ids["gestao_livro_encerrado"], qual="abertura")
    casa.pagina("nucleo_livro_termo", livro_id=ids["gestao_livro_encerrado"], qual="encerramento")

    comp = EM.mes_anterior(casa.hoje)
    locais = ler_feriados_locais(casa.db.get_setting("ri_feriados_locais", ""))
    with casa.con() as con:
        faltam = EM.pendencias(con, comp, series_do_mes=EM.series(casa.db.get_setting),
                               e_dia_util=lambda d: eh_dia_util(d, locais), hoje=casa.hoje)
    # Os termos do mês vão pela função de domínio, numa transação só: pela tela são uns quarenta
    # envios, e o que se prova aqui é o PDF do mês, que é o que vem depois deles.
    with casa.transacao() as con:
        for pendencia in faltam:
            dia = date.fromisoformat(pendencia["dia"])
            ESC.encerrar_o_dia(con, pendencia["serie"], pendencia["dia"], sv=dados_serventia(casa.db.get_settings),
                               agora=f"{pendencia['dia']}T18:00:00", dia_extenso=data_por_extenso(dia),
                               usuario=MARIO)
    _postar(casa, "/nucleo/encerramento-mensal/juntar", r"^/nucleo/encerramento-diario", mes=comp)
    with casa.con() as con:
        mensal = EM.mensal(con, comp)
    assert mensal, "o mês não foi juntado"
    # A assinatura é do A3, na máquina do oficial: o pacote entra como o serviço o devolveria.
    pasta = casa.pasta_temporaria / "gestao_mensal"
    pasta.mkdir(parents=True, exist_ok=True)
    pdf, p7s = pasta / f"encerramentos-diarios-{comp}.pdf", pasta / f"encerramentos-diarios-{comp}.p7s"
    pdf.write_bytes(PDF_MINIMO)
    p7s.write_bytes(b"0\x80\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x07\x02")
    casa.sql("UPDATE as_documentos SET caminho_documento = %s, tamanho_documento = %s, caminho_assinado = %s, "
             "sha256_assinado = %s, assinado_em = %s, assinado_por_nome = %s WHERE entidade = %s AND entidade_id = %s",
             (str(pdf), len(PDF_MINIMO), str(p7s), "0" * 64, _agora(casa), MARIO, EM.ENTIDADE, mensal["id"]))
    ids["gestao_encerramento_mensal"] = int(mensal["id"])
    casa.pagina("nucleo_encerramento_mensal_pdf", mensal_id=mensal["id"])
    casa.pagina("nucleo_encerramento_mensal_assinado", mensal_id=mensal["id"])


def _modelos(casa) -> None:
    import modelos_editor as ED
    with casa.con() as con:
        modelos = ED.listar_modelos_rcpn(con)
    termo = next(m["template_id"] for m in modelos if m["tipo"] == "termo")
    moldes = [m["template_id"] for m in modelos if m["tipo"] == "molde"]
    assert moldes, "o editor não lista molde nenhum"
    casa.pagina("modelos_editor_editar", area="RCPN", template_id=termo)
    for molde in moldes:
        casa.pagina("modelos_editor_editar", area="RCPN", template_id=molde)
        casa.pagina("modelos_editor_api_molde_baixar", template_id=molde)
        casa.pagina("modelos_molde_baixar", chave=molde)


def _robos(casa) -> None:
    ids = casa.ids
    for nome, ativo in (("Robô de triagem de exemplo", "1"), ("Robô de rascunho parado", "")):
        _postar(casa, "/robos/novo", r"^/robos/\d+$", nome=nome, ato="nascimento", provedor="grok",
                prompt="Resuma o pedido em uma frase.", ativo=ativo)
    robos = casa.ler("SELECT id FROM robo ORDER BY id DESC LIMIT 2")
    assert len(robos) == 2, robos
    robo = robos[1]["id"]
    _postar(casa, f"/robos/{robo}/exemplos", rf"^/robos/{robo}$", entrada="Preciso de uma certidão de nascimento.",
            saida_esperada="certidão de nascimento", peso="1")
    ids["gestao_robo"], ids["gestao_robo_parado"] = robo, robos[0]["id"]
    for r in (ids["gestao_robo"], ids["gestao_robo_parado"]):
        casa.pagina("robos_editar", robo_id=r)


def _desenvolvimento(casa) -> None:
    import dev_projetos as DEV
    with casa.transacao() as con:
        DEV.seed_sandbox_exemplo(con)
    projetos = casa.ler("SELECT id FROM dev_projetos ORDER BY id")
    assert projetos, "o projeto de exemplo não nasceu"
    for projeto in projetos[:2]:
        casa.pagina("dev_projetos_detalhe", projeto_id=projeto["id"])


def _automacao(casa) -> None:
    import automacao as AU
    import automacao_schema as SCH
    ids = casa.ids
    with casa.transacao() as con:
        AU.semear(con)
    processo = _um(casa, "SELECT id FROM au_processos WHERE codigo = %s", ("CASA_BACKUP",))["id"]
    quando = datetime.now()
    with casa.transacao() as con:
        execucao = AU._criar_execucao(con, AU.obter(con, processo), disparo=SCH.MANUAL, agendada_para=None,
                                      quem="Mario Exemplo", agora=quando)
    AU.finalizar(casa.db, execucao, {"situacao": SCH.AVISO, "relato": "O backup rodou, com um aviso.",
                                     "achados": [{"item": "disco", "detalhe": "2 GB livres"}],
                                     "acoes": [{"acao": "conferir", "resultado": "ok"}]},
                 agora=quando, pasta_dados=casa.pasta_temporaria)
    execucoes = [execucao]
    for situacao, relato, erro in ((SCH.OK, "O backup rodou e não achou nada a dizer.", ""),
                                   (SCH.ERRO, "O backup falhou.", "A pasta de destino não respondeu.")):
        quando += timedelta(minutes=1)
        with casa.transacao() as con:
            outra = AU._criar_execucao(con, AU.obter(con, processo), disparo=SCH.MANUAL, agendada_para=None,
                                       quem="Mario Exemplo", agora=quando)
        AU.finalizar(casa.db, outra, {"situacao": situacao, "relato": relato, "erro": erro}, agora=quando,
                     pasta_dados=casa.pasta_temporaria)
        execucoes.append(outra)
    _anotar(casa, processo_de_automacao=processo, execucao_de_automacao=execucao)
    # Um processo de cada tipo: função, script e o que mais a fábrica cadastrar.
    for p in casa.ler("SELECT DISTINCT ON (tipo) id FROM au_processos ORDER BY tipo, id"):
        casa.pagina("automacao_processo", processo_id=p["id"])
    casa.pagina("automacao_processo", processo_id=processo)
    for e in execucoes:
        casa.pagina("automacao_execucao", execucao_id=e)


def _agente(casa) -> None:
    import agente_schema as AGS
    ids = casa.ids
    agora = _agora(casa)
    with casa.transacao() as con:
        concluida = AGS.abrir_sessao(con, titulo="o selo não responde", pedido="o selo não responde",
                                     provedor="deepseek", modelo="deepseek-chat", agora=agora, criada_por=MARIO)
        AGS.registrar_passo(con, concluida, ordem=1, tipo=AGS.PEDIDO, conteudo="o selo não responde", agora=agora)
        AGS.registrar_passo(con, concluida, ordem=2, tipo=AGS.FERRAMENTA, ferramenta="estado_do_sistema",
                            chamada_id="call_1", argumentos='{"o_que": "selo"}', agora=agora)
        AGS.registrar_passo(con, concluida, ordem=3, tipo=AGS.RESULTADO, ferramenta="estado_do_sistema",
                            chamada_id="call_1", conteudo="o selador respondeu pela última vez às 09:58",
                            agora=agora)
        AGS.registrar_mudanca(con, concluida, ferramenta="anotar_no_problema", alvo="problema 12", antes="aberto",
                              depois="com nota", agora=agora, criada_por=MARIO)
        AGS.atualizar_sessao(con, concluida, estado=AGS.CONCLUIDA, turnos=3, tokens_de_entrada=1200,
                             tokens_de_saida=340, erro="", agora=agora)
        com_erro = AGS.abrir_sessao(con, titulo="conferir o caixa", pedido="conferir o caixa de ontem",
                                    provedor="deepseek", modelo="deepseek-chat", agora=agora, criada_por=MARIO)
        AGS.registrar_passo(con, com_erro, ordem=1, tipo=AGS.PEDIDO, conteudo="conferir o caixa de ontem",
                            agora=agora)
        AGS.atualizar_sessao(con, com_erro, estado=AGS.ERRO, turnos=1, tokens_de_entrada=300, tokens_de_saida=0,
                             erro="O provedor não respondeu no prazo.", agora=agora)
    _anotar(casa, agente_concluida=concluida, agente_com_erro=com_erro)
    for sessao in (concluida, com_erro):
        casa.pagina("agente_sessao", sessao_id=sessao)
        casa.pagina("agente_andamento", sessao_id=sessao)


def _ajuda(casa) -> None:
    import agente_provedores as PROV
    import ajuda as AJ
    original = PROV.conversar
    PROV.conversar = lambda *a, **k: {"texto": "A irregularidade 33 é falta de data de vencimento.",
                                      "modelo": "claude-sonnet-5", "entrada": 120, "saida": 40}
    try:
        r = AJ.consultar(casa.db, pergunta="o que é a irregularidade 33?", assunto="USO",
                         pasta_de_dados=casa.pasta_temporaria, agora=_agora(casa), papel="ADMIN",
                         usuario=MARIO, login="ensaio_admin_novo")
    finally:
        PROV.conversar = original
    casa.ids["gestao_ajuda_consulta"] = r["consulta_id"]
    casa.pagina("ajuda_consulta", consulta_id=r["consulta_id"])


def _selos(casa) -> None:
    ids = casa.ids
    cancelado = ("Poder Judiciário – TJMA. Selo: {n}, 15/10/2026 10:00:00, Ato: 14.5.1, Total R$ 53,58, "
                 "Consulte em https://selo.tjma.jus.br")
    isento = ("Poder Judiciário – TJMA. Selo: {n}, 15/10/2026 10:00:00, Ato: 14.4.1, Total R$ 0,00 Selo Isento, "
              "Consulte em https://selo.tjma.jus.br")

    def selo(numero: str, texto: str, **extra) -> int:
        return casa.inserir("sd_selos", numero=numero, texto=texto.format(n=numero), atribuicao="RCPN",
                            obtido_em=_agora(casa), obtido_por=BEATRIZ, ambiente="PRODUCAO", **extra)

    selo("AVERBA000000GEST00000001", cancelado, cancelado_em=_agora(casa), motivo_cancelamento="Ato refeito.")
    periodo = dict(inicio=casa.hoje, fim=casa.hoje)
    comunicado = _numero_no_fim(_postar(casa, "/selos/cancelamentos/oficio", r"^/selos/portal/remessa/\d+$", **periodo),
                                "/remessa/")
    _postar(casa, f"/selos/portal/remessa/{comunicado}/comunicado", rf"^/selos/portal/remessa/{comunicado}$",
            protocolo="MALOTE 123")
    selo("AVERBA000000GEST00000002", cancelado, cancelado_em=_agora(casa), motivo_cancelamento="Ato cancelado.")
    rascunho = _numero_no_fim(_postar(casa, "/selos/cancelamentos/oficio", r"^/selos/portal/remessa/\d+$", **periodo),
                              "/remessa/")
    gratuito = selo("AVERBA000000GEST00000003", isento)
    for peca in ("COMPROVANTE", "CERTIDAO"):
        _postar(casa, f"/selos/gratuidades-portal/{gratuito}/peca", r"^/selos/gratuidades-portal",
                arquivo=_arquivo(f"{peca.lower()}.pdf", PDF_MINIMO), peca=peca, tipo="DECLARACAO_POBREZA")
    pacote = _numero_no_fim(_postar(casa, "/selos/gratuidades-portal/pacote", r"^/selos/portal/remessa/\d+$",
                                    **periodo), "/remessa/")
    _anotar(casa, remessa_comunicada=comunicado, remessa_rascunho=rascunho, remessa_de_gratuidade=pacote)
    for remessa in (comunicado, rascunho, pacote):
        casa.pagina("selo_portal_remessa", remessa_id=remessa)
        casa.pagina("selo_portal_remessa_csv", remessa_id=remessa)


def _whatsapp(casa) -> None:
    import wa_balcao as WA
    import wa_midia as MIDIA
    import wa_schema as SCH
    ids = casa.ids
    agora = _agora(casa)

    def entrada(wa_id: str, meta_id: str, mensagem: dict) -> int:
        corpo = {"from": wa_id, "id": meta_id, **mensagem}
        with casa.transacao() as con:
            r = WA.aplicar_entrada(con, {"messages": [corpo]}, agora=agora)
        return int(r["conversa_ids"][0])

    aberta = entrada("5500900000001", "wamid.gestao-1", {"type": "text", "text": {"body": "Bom dia, preciso de uma "
                                                                                     "certidão de nascimento."}})
    entrada("5500900000001", "wamid.gestao-2", {"type": "image", "image": {"id": "midia-gestao-1"}})
    foto = _um(casa, "SELECT id FROM wa_mensagem WHERE conversa_id = %s AND midia_id IS NOT NULL", (aberta,))["id"]
    salvo = MIDIA.guardar(MIDIA.pasta_do_mes(casa.pasta_temporaria / "whatsapp_gestao", agora), "foto.png", PNG_1X1)
    casa.sql("UPDATE wa_mensagem SET midia_situacao = %s, arquivo_nome = %s, arquivo_caminho = %s, arquivo_mime = %s, "
             "arquivo_bytes = %s, arquivo_sha256 = %s WHERE id = %s",
             (SCH.MIDIA_OK, salvo["nome"], salvo["caminho"], "image/png", salvo["bytes"], salvo["sha256"], foto))
    with casa.transacao() as con:
        WA.gravar_saida(con, aberta, "Bom dia! Já vamos verificar o seu pedido.", "wamid.gestao-saida-1",
                        autor=BEATRIZ, agora=agora)
    _postar(casa, f"/whatsapp/{aberta}/assumir", rf"/whatsapp/{aberta}$")
    resolvida = entrada("5500900000002", "wamid.gestao-3", {"type": "text", "text": {"body": "Obrigado pela ajuda."}})
    _postar(casa, f"/whatsapp/{resolvida}/resolver", r"^/whatsapp$")
    _anotar(casa, whatsapp_aberta=aberta, whatsapp_resolvida=resolvida, whatsapp_foto=foto)
    for conversa in (aberta, resolvida):
        casa.pagina("whatsapp_conversa", conversa_id=conversa)
        casa.pagina("whatsapp_novas", conversa_id=conversa)
    casa.pagina("whatsapp_midia", mensagem_id=foto)


PARTES = (_balcao, _andamento_e_inacabados, _cobranca, _nfse, _tarefas, _expedientes, _rotinas, _avisos, _senhas,
          _ouvidoria, _pld, _correcoes, _despesas, _livros, _nucleo, _modelos, _robos, _desenvolvimento,
          _automacao, _agente, _ajuda, _selos, _whatsapp)


def _atendimento_e_treinamento(casa) -> None:
    """O atendimento do protocolo e as aulas do treinamento (#368). As aulas e as trilhas são do
    código (`treinamento_roteiros`), e não do banco: a semente só anota os endereços."""
    casa.pagina("at_ficha", protocolo_id=casa.ids["gestao_protocolo_pago"])
    casa.pagina("tr_trilha", trilha="primeiro-dia")
    casa.pagina("tr_aula", chave="roteiro-atendimento")
    casa.pagina("tr_orientacao", chave="roteiro-atendimento")


PARTES = PARTES + (_atendimento_e_treinamento,)


def semear(casa) -> None:
    """Cada parte roda sozinha: uma que falha não esconde as outras, mas o conjunto falha."""
    falhas = []
    for parte in PARTES:
        try:
            parte(casa)
        except Exception as erro:                                  # noqa: BLE001 - junta e relata no fim
            falhas.append(f"{parte.__name__}: {type(erro).__name__}: {erro}\n{traceback.format_exc()[-1800:]}")
    assert not falhas, "a semente da gestão falhou em " + str(len(falhas)) + " parte(s):\n" + "\n".join(falhas)
