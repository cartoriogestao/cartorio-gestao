"""O ensaio de atos do RTD e do RCPJ: as SEQUÊNCIAS no mesmo registro, e a mesma pessoa jurídica duas vezes.

O PEDIDO, do oficial (01/11/2026): «um teste que usasse todos botões e formulários do sistema para
simular todos atos possíveis previstos em lei ou nos códigos de normas […] e fizesse uma análise
crítica apurada sobre o resultado de saída.» O RTD/RCPJ é o último da ordem do BRIEFING.

O QUE ESTE TESTE FAZ
    `test_fluxo_rtd_rcpj` já leva cada ato (registro nos cinco livros, averbação, cancelamento,
    notificação, autenticação de livro, certidões) do protocolo pago ao termo e à certidão, cada um num
    registro limpo. Este pratica, pelas mesmas telas e com os mesmos auxiliares de lá, o que vem depois:
    a averbação sobre o registro cancelado, o breve relato da associação dissolvida, e a segunda
    associação com a mesma denominação. O inventário está em `docs/ensaio_de_atos/inventario_rtd_rcpj.md`,
    e o relatório em `relatorio_rtd_rcpj.md`.

OS DEFEITOS FICAM À VISTA: a asserção é a da lei; o defeito aberto fica em `xfail(strict=True)`.

Pessoas e documentos fictícios (os de `test_fluxo_rtd_rcpj`).
"""
from __future__ import annotations

import io
import time

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
    # UM SEGUNDO ENTRE A LEITURA E A DISSOLUÇÃO, como no balcão: a régua compara as horas ao segundo, e no
    # mesmo segundo a leitura conta como atual (observação O4 do relatório) — o teste caía uma vez em duas.
    time.sleep(1.1)
    _dissolvida(b, ficha)
    r = _breve_relato(b, registro["id"], ficha)
    assert "O breve relato é da situação ATUAL" in F._avisos(r), F._avisos(r)
    _dados_da_pj(b, ficha)
    r = _breve_relato(b, registro["id"], ficha)
    assert "emitida" in F._avisos(r), F._avisos(r)
    cert = b.um("SELECT * FROM at_certidoes ORDER BY id DESC LIMIT 1")
    assert "encontra-se CANCELADO" in cert["teor"] and "(cancelamento n." in cert["teor"], cert["teor"]


# ------------------------------------------------------------------ a mesma denominação

@_defeito("a segunda associação com a mesma denominação se inscreve no Livro A sem aviso nenhum — nem no "
          "recebimento, nem na qualificação, nem no registro")
def test_a_segunda_associacao_com_a_mesma_denominacao_nao_se_inscreve_sem_aviso(casa):  # noqa: F811
    """CC art. 1.155, parágrafo único (a denominação das associações e fundações equipara-se ao nome
    empresarial, para a proteção da lei) e art. 1.163 (o nome deve distinguir-se de qualquer outro já
    inscrito no mesmo registro); o CN-MA tem regra própria da homonímia no RCPJ (conferir). Inscrita a
    ASSOCIAÇÃO DE EXEMPLO, a segunda com a mesma denominação não vai ao livro sem a tela dizê-lo."""
    b = F.Balcao(casa)
    b.abrir_caixa()
    _associacao(b)
    titulo = b.receber_titulo(3, serie="PJ_A", natureza=ESTATUTO, apresentante=ASSOCIACAO, documento=F.CPF)
    url = f"/rcpj-rtd/titulo/{titulo['id']}"
    avisos = [F._avisos(b.c.get(url))]
    b.pagar(titulo["protocolo_geral_id"], "15.5.1")
    avisos.append(F._avisos(b.qualificar(titulo["id"], resultado="POSITIVA",
                                         fundamentacao="Título em ordem para registro.")))
    r = postar_e_seguir(b.c, f"{url}/registrar", {
        "csrf_token": F._token(b.c, url), "serie": "PJ_A", "teor": f"ESTATUTO DA {ASSOCIACAO} (a segunda).",
        "protocolo_id": str(titulo["protocolo_geral_id"]), **F._campos_da_lista("PJ_A", ESTATUTO)})
    avisos.append(F._avisos(r))
    inscritas = b.ler("SELECT id FROM rg_registros WHERE serie='PJ_A' AND requerente_nome=%s", (ASSOCIACAO,))
    avisou = any("denomina" in a.lower() or "mesmo nome" in a.lower() for a in avisos)
    assert len(inscritas) == 1 or avisou, avisos
