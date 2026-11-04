"""O ensaio de atos do RTD e do RCPJ: as SEQUÊNCIAS no mesmo registro, e a mesma pessoa jurídica duas vezes.

O PEDIDO, do oficial (01/11/2026): «um teste que usasse todos botões e formulários do sistema para
simular todos atos possíveis previstos em lei ou nos códigos de normas […] e fizesse uma análise
crítica apurada sobre o resultado de saída.» O RTD/RCPJ é o último da ordem do BRIEFING.

O QUE ESTE TESTE FAZ
    `test_fluxo_rtd_rcpj` já leva cada ato (registro nos cinco livros, averbação, cancelamento,
    notificação, autenticação de livro, certidões) do protocolo pago ao termo e à certidão, cada um num
    registro limpo. Este pratica, pelas mesmas telas e com os mesmos auxiliares de lá, o que vem depois:
    a averbação sobre o registro cancelado, o breve relato da associação dissolvida, e a segunda
    associação com a mesma denominação; na segunda leva, a mudança de denominação e a notificação do
    registro cancelado. O inventário está em `docs/ensaio_de_atos/inventario_rtd_rcpj.md`,
    e o relatório em `relatorio_rtd_rcpj.md`.

OS DEFEITOS FICAM À VISTA: a asserção é a da lei; o defeito aberto fica em `xfail(strict=True)`.

Pessoas e documentos fictícios (os de `test_fluxo_rtd_rcpj`).
"""
from __future__ import annotations

import io

import pytest

import test_fluxo_rtd_rcpj as F
from navegador_de_teste import postar_e_seguir
from test_fluxo_rtd_rcpj import casa  # noqa: F401 — a serventia do RTD/RCPJ (fixture)

pytestmark = pytest.mark.lento

ASSOCIACAO = "ASSOCIAÇÃO DE EXEMPLO"
ESTATUTO = "Estatuto de associação civil"
ELEICAO = "Ata de eleição da diretoria"


def _defeito(motivo: str):
    return pytest.mark.xfail(strict=True, reason=f"DEFEITO: {motivo}")


def _associacao(b, *, documento: str = F.CNPJ) -> dict:
    """A associação inscrita no Livro A, pelo caminho inteiro do balcão."""
    return F._lavrar_pelo_titulo(b, atribuicao=3, serie="PJ_A", item="15.5.1", natureza=ESTATUTO,
                                 apresentante=ASSOCIACAO, documento=documento,
                                 teor=f"ESTATUTO DA {ASSOCIACAO}.")


def _dados_da_pj(b, ficha: str):
    """Quem leu o estatuto grava a sede, o objeto e a diretoria na ficha (o que o breve relato lê)."""
    r = b.post(f"{ficha}/dados-pj", ficha, pj_sede=F.SEDE_DE_EXEMPLO, pj_objeto=F.OBJETO_DE_EXEMPLO,
               pj_diretoria=F.DIRETORIA_DE_EXEMPLO)
    assert "Dados da pessoa jurídica gravados" in F._avisos(r), F._avisos(r)


def _dissolvida(b, ficha: str) -> None:
    pid = b.protocolo("RCPJ", ASSOCIACAO, "15.9.1")
    r = b.post(f"{ficha}/lancar", ficha, tipo="CANCELAMENTO",
               motivo="Ata da assembleia geral que dissolveu a associação, de 01/10/2026.",
               protocolo_id=str(pid))
    assert "Cancelamento lançada" in F._avisos(r), F._avisos(r)


def _breve_relato(b, registro_id: int, ficha: str):
    pid = b.protocolo("RCPJ", "FULANA REQUERENTE DE EXEMPLO", "15.10.1")
    return b.post(f"/atribuicoes/certidoes/RCPJ_RTD/{registro_id}", ficha, forma="BREVE_RELATO",
                  requerente="FULANA REQUERENTE DE EXEMPLO", protocolo_id=str(pid))


# ------------------------------------------------------------------ o registro cancelado

def test_o_registro_cancelado_nao_recebe_averbacao(casa):  # noqa: F811
    """LRP arts. 128 e 164 a 166: a averbação se faz à margem do registro que produz efeito; dissolvida a
    associação e cancelado o registro, a ata de eleição de diretoria não se averba."""
    b = F.Balcao(casa)
    b.abrir_caixa()
    registro = _associacao(b)["registro"]
    ficha = f"/rcpj-rtd/{registro['id']}"
    _dissolvida(b, ficha)
    titulo = b.receber_titulo(3, serie="PJ_A", natureza=ELEICAO, apresentante=ASSOCIACAO, documento=F.CNPJ)
    b.pagar(titulo["protocolo_geral_id"], "15.9.1")
    b.qualificar(titulo["id"], resultado="POSITIVA")
    r = postar_e_seguir(b.c, f"{ficha}/lancar", {
        "csrf_token": F._token(b.c, ficha), "tipo": "AVERBACAO", "natureza_ato": ELEICAO,
        "data_assinatura": "01/10/2026", "protocolo_id": str(titulo["protocolo_geral_id"]),
        "novo_arquivo": (io.BytesIO(F._png()), "averbacao.png"), **F._campos_da_lista("PJ_A", ELEICAO)})
    assert "só se averba registro ativo" in F._avisos(r), F._avisos(r)
    assert not b.ler("SELECT id FROM rg_atos WHERE registro_id=%s AND tipo='AVERBACAO'", (registro["id"],))


def test_o_breve_relato_da_associacao_dissolvida_diz_o_cancelamento(casa):  # noqa: F811
    """CN-MA art. 420, II (a situação ATUAL) e LRP art. 165: o breve relato pedido depois da dissolução
    é recusado enquanto a leitura da ficha for de antes dela; relida a ficha, ele sai, e diz que o
    registro está CANCELADO."""
    b = F.Balcao(casa)
    b.abrir_caixa()
    registro = _associacao(b)["registro"]
    ficha = f"/rcpj-rtd/{registro['id']}"
    _dados_da_pj(b, ficha)
    # NO MESMO SEGUNDO, DE PROPÓSITO: a leitura e a dissolução quase sempre caem juntas aqui. Até a
    # observação O4 a régua comparava as horas, e o empate contava como leitura atual; agora é a ordem.
    _dissolvida(b, ficha)
    r = _breve_relato(b, registro["id"], ficha)
    assert "O breve relato é da situação ATUAL" in F._avisos(r), F._avisos(r)
    _dados_da_pj(b, ficha)
    r = _breve_relato(b, registro["id"], ficha)
    assert "emitida" in F._avisos(r), F._avisos(r)
    cert = b.um("SELECT * FROM at_certidoes ORDER BY id DESC LIMIT 1")
    assert "encontra-se CANCELADO" in cert["teor"] and "(cancelamento n." in cert["teor"], cert["teor"]


# ------------------------------------------------------------------ a mesma denominação

def _segunda_associacao(b, nome: str, **campos):
    """Outro estatuto, de outra associação, até o botão «Registrar» do Livro A."""
    titulo = b.receber_titulo(3, serie="PJ_A", natureza=ESTATUTO, apresentante=nome, documento=F.CPF)
    url = f"/rcpj-rtd/titulo/{titulo['id']}"
    b.pagar(titulo["protocolo_geral_id"], "15.5.1")
    b.qualificar(titulo["id"], resultado="POSITIVA", fundamentacao="Título em ordem para registro.")
    tela = b.c.get(url).get_data(as_text=True)
    r = postar_e_seguir(b.c, f"{url}/registrar", {
        "csrf_token": F._token(b.c, url), "serie": "PJ_A", "teor": f"ESTATUTO DA {nome}.",
        "protocolo_id": str(titulo["protocolo_geral_id"]), **F._campos_da_lista("PJ_A", ESTATUTO), **campos})
    return tela, F._avisos(r), b.ler("SELECT id FROM rg_registros WHERE serie='PJ_A' AND requerente_nome=%s", (nome,))


def test_a_segunda_associacao_com_a_mesma_denominacao_nao_se_inscreve(casa):  # noqa: F811
    """CC art. 1.155, parágrafo único (a denominação das associações e fundações equipara-se ao nome
    empresarial) e art. 1.163 (o nome distingue-se de qualquer outro já inscrito no mesmo registro). Decisão
    do oficial, 03/11/2026 («m»; CONSERTADO): o nome IDÊNTICO não se inscreve, e a ficha do título avisa
    antes do clique."""
    b = F.Balcao(casa)
    b.abrir_caixa()
    _associacao(b)
    tela, avisos, inscritas = _segunda_associacao(b, ASSOCIACAO)
    assert "Já há pessoa jurídica com esta denominação" in tela, "a ficha do título não avisa"
    assert len(inscritas) == 1, avisos
    assert "Já há pessoa jurídica com esta denominação" in avisos and "1.163" in avisos, avisos


def test_a_denominacao_parecida_se_inscreve_com_a_fundamentacao(casa):  # noqa: F811
    """A outra metade de «m»: o nome PARECIDO (as mesmas palavras, tirado o tipo e as de ligação) pede por
    que se distingue; sem isso não se inscreve, e com isso a fundamentação vai à auditoria."""
    b = F.Balcao(casa)
    b.abrir_caixa()
    _associacao(b)
    parecido = "EXEMPLO ASSOCIAÇÃO"
    _, avisos, inscritas = _segunda_associacao(b, parecido)
    assert not inscritas and "parecida" in avisos, avisos
    titulo = b.um("SELECT id, protocolo_geral_id FROM rg_titulos WHERE apresentante=%s", (parecido,))
    url = f"/rcpj-rtd/titulo/{titulo['id']}"
    postar_e_seguir(b.c, f"{url}/registrar", {
        "csrf_token": F._token(b.c, url), "serie": "PJ_A", "teor": f"ESTATUTO DA {parecido}.",
        "protocolo_id": str(titulo["protocolo_geral_id"]), **F._campos_da_lista("PJ_A", ESTATUTO),
        "fundamentacao_denominacao": "Outra sede e outro objeto; a ordem das palavras é a do estatuto."})
    registro = b.um("SELECT id FROM rg_registros WHERE requerente_nome=%s", (parecido,))
    assert registro, "a parecida, fundamentada, não se inscreveu"
    log = b.um("SELECT details FROM audit_logs WHERE action='RG_DENOMINACAO_PARECIDA' AND entity_id=%s",
               (registro["id"],))
    assert log and "Outra sede" in str(log["details"]), log

# ------------------------------------------------------------------ a mudança de denominação

NOVA_DENOMINACAO = "ASSOCIAÇÃO CULTURAL DE EXEMPLO"
ALTERACAO = "Ata de alteração estatutária: nova denominação"


def test_a_associacao_que_muda_de_nome_sai_com_o_nome_novo_no_breve_relato(casa):  # noqa: F811
    """CN-MA art. 420, II (a denominação na situação ATUAL) e LRP art. 128 (a alteração se averba): averbada
    a ata que muda a denominação, corrigido o cadastro pela tela própria («uma pj mudou de nome», o oficial,
    12/09/2026) e relida a ficha, o breve relato sai com o nome novo — e não com o antigo."""
    b = F.Balcao(casa)
    b.abrir_caixa()
    registro = _associacao(b)["registro"]
    ficha = f"/rcpj-rtd/{registro['id']}"
    _dados_da_pj(b, ficha)
    titulo = b.receber_titulo(3, serie="PJ_A", natureza=ALTERACAO, apresentante=ASSOCIACAO, documento=F.CNPJ)
    b.pagar(titulo["protocolo_geral_id"], "15.9.1")
    b.qualificar(titulo["id"], resultado="POSITIVA")
    postar_e_seguir(b.c, f"{ficha}/lancar", {
        "csrf_token": F._token(b.c, ficha), "tipo": "AVERBACAO", "natureza_ato": ALTERACAO,
        "data_assinatura": "01/10/2026", "protocolo_id": str(titulo["protocolo_geral_id"]),
        "novo_arquivo": (io.BytesIO(F._png()), "averbacao.png"), **F._campos_da_lista("PJ_A", ALTERACAO)})
    assert b.ler("SELECT id FROM rg_atos WHERE registro_id=%s AND tipo='AVERBACAO'", (registro["id"],))
    r = b.post(f"{ficha}/corrigir-requerente", ficha, requerente_nome=NOVA_DENOMINACAO,
               requerente_documento=F.CNPJ, motivo="Nova denominação averbada (AV-2), ata de 01/10/2026.")
    assert "Dados do requerente corrigidos" in F._avisos(r), F._avisos(r)
    _dados_da_pj(b, ficha)
    r = _breve_relato(b, registro["id"], ficha)
    assert "emitida" in F._avisos(r), F._avisos(r)
    cert = b.um("SELECT * FROM at_certidoes ORDER BY id DESC LIMIT 1")
    assert f"Denominação: {NOVA_DENOMINACAO}" in cert["teor"], cert["teor"]
    assert f"Denominação: {ASSOCIACAO}\n" not in cert["teor"], cert["teor"]


# ------------------------------------------------------------------ a notificação do registro cancelado

def test_o_registro_cancelado_nao_abre_notificacao(casa):  # noqa: F811
    """LRP arts. 160 e 164 a 166: a notificação extrajudicial é a do documento registrado; cancelado o
    registro (lavrado por engano, por exemplo), ele não produz efeito, e não se abre notificação dele."""
    b = F.Balcao(casa)
    b.abrir_caixa()
    titulo = b.receber_titulo(4, serie="TD_B", natureza="Notificação extrajudicial",
                              apresentante="EMPRESA DE EXEMPLO LTDA", documento=F.CNPJ)
    b.pagar(titulo["protocolo_geral_id"], "15.8")
    b.qualificar(titulo["id"], resultado="POSITIVA")
    url = f"/rcpj-rtd/titulo/{titulo['id']}"
    postar_e_seguir(b.c, f"{url}/registrar", {
        "csrf_token": F._token(b.c, url), "serie": "TD_B",
        "teor": "NOTIFICAÇÃO EXTRAJUDICIAL DE EXEMPLO, para pagamento de aluguel.",
        "protocolo_id": str(titulo["protocolo_geral_id"])})
    registro = b.um("SELECT * FROM rg_registros ORDER BY id DESC LIMIT 1")
    ficha = f"/rcpj-rtd/{registro['id']}"
    pid = b.protocolo("RTD", "EMPRESA DE EXEMPLO LTDA", "15.9.1")
    r = b.post(f"{ficha}/lancar", ficha, tipo="CANCELAMENTO",
               motivo="Registro lavrado por engano, a requerimento do apresentante.", protocolo_id=str(pid))
    assert "Cancelamento lançada" in F._avisos(r), F._avisos(r)
    b.protocolo("RTD", "EMPRESA DE EXEMPLO LTDA", "15.8.1", "15.8.2")
    nova = f"/rcpj-rtd/notificacoes/nova?titulo_id={titulo['id']}"
    r = b.post(nova, nova, destinatario_nome="CICLANO DE EXEMPLO", destinatario_documento=F.CPF,
               endereco="Rua de Exemplo, 100, Centro, Cidade Exemplo/MA", zona="URBANA")
    assert "Notificação aberta" not in F._avisos(r), F._avisos(r)
    assert not b.ler("SELECT id FROM rg_notificacoes"), F._avisos(r)
    # O RECADO DIZ POR QUÊ, e qual ato cancelou (CONSERTADO em 03/11/2026, defeito 2 do relatório).
    assert "situação CANCELADO, pelo ato n. 2" in F._avisos(r) and "art. 160" in F._avisos(r), F._avisos(r)


def test_a_releitura_pergunta_a_denominacao_e_o_breve_relato_certifica_a_lida(casa):  # noqa: F811
    """A resposta do oficial à observação O5 (03/11/2026): «a releitura da ficha passa a perguntar a
    denominação, já preenchida com a do cadastro». A tela a traz preenchida; quem relê escreve a nova
    denominação, averbada; o breve relato certifica a lida, e a tela avisa que o cadastro (o da busca)
    continua com a antiga até a «Corrigir requerente»."""
    b = F.Balcao(casa)
    b.abrir_caixa()
    registro = _associacao(b)["registro"]
    ficha = f"/rcpj-rtd/{registro['id']}"
    tela = b.c.get(ficha).get_data(as_text=True)
    assert 'name="pj_denominacao"' in tela and f'value="{ASSOCIACAO}"' in tela
    r = b.post(f"{ficha}/dados-pj", ficha, pj_denominacao=NOVA_DENOMINACAO, pj_sede=F.SEDE_DE_EXEMPLO,
               pj_objeto=F.OBJETO_DE_EXEMPLO, pj_diretoria=F.DIRETORIA_DE_EXEMPLO)
    assert "Dados da pessoa jurídica gravados" in F._avisos(r), F._avisos(r)
    assert "não é a do cadastro" in F._avisos(r) and "Corrigir requerente" in F._avisos(r), F._avisos(r)
    r = _breve_relato(b, registro["id"], ficha)
    assert "emitida" in F._avisos(r), F._avisos(r)
    cert = b.um("SELECT * FROM at_certidoes ORDER BY id DESC LIMIT 1")
    assert f"Denominação: {NOVA_DENOMINACAO}" in cert["teor"], cert["teor"]
    # a leitura com a denominação apagada não se grava
    r = b.post(f"{ficha}/dados-pj", ficha, pj_denominacao="", pj_sede=F.SEDE_DE_EXEMPLO,
               pj_objeto=F.OBJETO_DE_EXEMPLO, pj_diretoria=F.DIRETORIA_DE_EXEMPLO)
    assert "a denominação" in F._avisos(r) and "gravados" not in F._avisos(r), F._avisos(r)
