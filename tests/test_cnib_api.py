"""O transporte do CNIB, provado contra as respostas que a Central mandou.

**O que este arquivo NÃO faz: inventar resposta.** Tudo o que ele serve ao
módulo vem de `brutos_do_cnib.py`, que é transcrição dos brutos de 18/09/2026 —
inclusive as duas formas que não estão em contrato nenhum (a vazia, embrulhada
duas vezes; e a da consulta, que traz `protocolos` no lugar de `ordens`). Um
teste que montasse a resposta "parecida" provaria que o programa entende o que
eu imaginei, e foi assim que o `dadosSelo` embrulhado passou por 37 testes.

Ele está em quatro partes, e a ordem delas é a do risco:

1. **as três formas** — o que se lê, e o que acontece quando não é nenhuma;
2. **o laço e a paginação** — inclusive o freio, e o que a resposta diz quando
   ele é alcançado;
3. **o que vai no pedido** — a flag que consome a fila, o CPF de quem pergunta
   e o teto de 500;
4. **os rótulos e os protocolos** — as três grafias do mesmo estado, e os dois
   protocolos da linha de cancelamento.

E duas provas de coerência no fim: a de que o vocabulário declarado no módulo
cobre **exatamente** o que a Central manda, e a de que este módulo **não
escreve**.
"""

import ast
import json
from pathlib import Path

import pytest

import cnib_api
import centrais_cred as CRED

from brutos_do_cnib import (
    ENVELOPE_CONSULTA,
    ENVELOPE_VAZIA,
    ORDEM_DE_CANCELAMENTO,
    ORDEM_DE_CANCELAMENTO_ANTIGA,
    ORDEM_DE_PEDIDO,
    PAGINACAO_COM_PROXIMA,
    PAGINACAO_SEM_PROXIMA,
    envelope,
)


# ============================================================== a bancada
#
# A Central de mentira **grava o que se pediu**, e é isso que permite conferir
# o corpo do pedido — que é onde moram a flag da fila e o CPF de quem pergunta.
# Sem isso, o teste provaria que o módulo lê bem e não que ele pede o certo.
#
# `token` também é trocado: sem ele, a primeira chamada sairia pela rede. É a
# diferença entre um teste que roda em 0,2 s e um que depende da internet da
# serventia — e o segundo não roda no balcão.

class Central:
    """Serve as respostas na ordem e guarda cada pedido."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.corpos: list = []
        self.caminhos: list = []

    def __call__(self, metodo, caminho, **kw):
        bruto = kw.get("corpo")
        self.corpos.append(json.loads(bruto.decode("utf-8")) if bruto else None)
        self.caminhos.append(caminho)
        # A última resposta se repete: é o que deixa o teste do freio rodar as
        # 200 páginas sem montar 200 objetos à mão.
        r = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        return {"status": 200, "json": r, "texto": "", "bytes": b""}


def ligar(monkeypatch, respostas) -> Central:
    central = Central(respostas)
    monkeypatch.setattr(cnib_api, "token", lambda *a, **k: "TOKEN-DE-MENTIRA")
    monkeypatch.setattr(cnib_api, "_bater_cru", central)
    return central


CPF_DE_EXEMPLO = "000.000.000-00"


# =================================================== 1. as três formas


def test_a_forma_normal_traz_as_ordens():
    """`data.ordens` — a primeira forma, e a que a casa recebe quase sempre."""
    resposta = envelope([ORDEM_DE_PEDIDO], PAGINACAO_SEM_PROXIMA)
    assert cnib_api.forma_da_resposta(resposta) == "ordens"
    assert cnib_api.ordens_da_resposta(resposta) == [ORDEM_DE_PEDIDO]


def test_a_forma_vazia_vem_embrulhada_duas_vezes_e_em_camel_case():
    """`data.data.orders` — a segunda forma, e a que ninguém adivinharia.

    Ela não está em contrato nenhum: o contrato descreve a resposta com
    `data.ordens` e `paginação` com til. Quem escrevesse o leitor pelo contrato
    leria esta resposta como «não entendi» — e a Central usa esta forma para
    dizer que não há ordens na janela.
    """
    assert cnib_api.forma_da_resposta(ENVELOPE_VAZIA) == "vazia"
    assert cnib_api.ordens_da_resposta(ENVELOPE_VAZIA) == []


def test_a_consulta_por_documento_nao_traz_ordens():
    """`data.protocolos` — a terceira forma. **Não é lista de ordens.**

    Devolver `protocolos` como se fossem ordens faria o atualizador tentar
    gravar, em `ri_cnib_ordens`, uma lista de strings — e o erro só apareceria
    na primeira consulta de balcão.
    """
    assert cnib_api.forma_da_resposta(ENVELOPE_CONSULTA) == "documento"
    assert cnib_api.ordens_da_resposta(ENVELOPE_CONSULTA) == []


def test_o_que_nao_e_nenhuma_das_tres_e_dito_como_outra():
    """O contrato declara `VisualizationOrder`/`CustomVisualizationResponse`.

    **Nenhuma das três formas medidas é esse objeto.** O dia em que a Central
    responder o que o contrato promete, este teste fica vermelho — e é para
    isso que ele existe: para a quarta forma ser **vista**, e não lida como
    «não há ordens».
    """
    da_contrato = {"data": {"paginacao": {"pageIndex": 1, "totalRows": 0}}}
    assert cnib_api.forma_da_resposta(da_contrato) == "outra"
    assert cnib_api.ordens_da_resposta(da_contrato) == []


def test_a_frase_da_central_e_achada_nas_duas_profundidades():
    """A vazia guarda a frase em `data.message`, e não em `data.data.message`."""
    assert cnib_api.mensagem_da_resposta(ENVELOPE_VAZIA) == (
        "Não há ordens para os critérios informados.")
    assert cnib_api.mensagem_da_resposta(envelope([], PAGINACAO_SEM_PROXIMA)) == ""


def test_a_paginacao_tem_os_nomes_dela_e_nao_os_do_contrato():
    """**Zero nomes em comum** — e é isto que o contrato esconde.

    O contrato declara `paginação` (com til), `pageIndex`, `totalRows`,
    `pageSize` e `pageForward`. A resposta manda `paginacao`,
    `pagina_atual`, `total_ordens_encontradas`,
    `total_ordens_retornadas_por_pagina`, `ordens_restantes` e
    `tem_proxima_pagina`.
    """
    p = cnib_api.paginacao_da_resposta(
        envelope([ORDEM_DE_PEDIDO], PAGINACAO_COM_PROXIMA))
    assert p == PAGINACAO_COM_PROXIMA
    assert set(p) == set(cnib_api.PAGINACAO_REAL)
    # E a consulta por documento **não tem paginação**, porque não tem lista.
    assert cnib_api.paginacao_da_resposta(ENVELOPE_CONSULTA) == {}


def test_a_resposta_vazia_da_consulta_nao_e_paginacao_vazia():
    """`{}` da consulta é «não se aplica»; `{}` do laço seria «acabou».

    Os dois são o mesmo objeto, e significam coisas diferentes — por isso o
    laço pergunta a **forma** antes de perguntar se há próxima página.
    """
    assert cnib_api.paginacao_da_resposta(ENVELOPE_CONSULTA) == {}
    assert cnib_api.paginacao_da_resposta(ENVELOPE_VAZIA) == {}


# ================================================= 2. o laço e a paginação


def test_o_laco_anda_de_pagina_e_para_quando_a_central_diz_que_acabou(monkeypatch):
    """**O laço anda por `pagina_inicial`**, e para em `tem_proxima_pagina`.

    O `proxima_pagina` do pedido nunca foi usado com `true` pela casa — quem
    diz se há mais é o booleano da **resposta**. Este teste guarda as duas
    metades: a página pedida em cada volta, e a parada.
    """
    central = ligar(monkeypatch, [
        envelope([ORDEM_DE_PEDIDO], PAGINACAO_COM_PROXIMA),
        envelope([ORDEM_DE_CANCELAMENTO], PAGINACAO_SEM_PROXIMA),
    ])
    r = cnib_api.ordens_na_janela("2026-09-01", "2026-09-18",
                                  cpf_usuario=CPF_DE_EXEMPLO)
    assert r["paginas"] == 2
    assert r["lidas"] == 2
    assert [o["status"] for o in r["ordens"]] == ["INDISPONIBILIDADE", "CANCELAMENTO"]
    assert [c["pagina_inicial"] for c in central.corpos] == [1, 2]
    assert r["parou_no_teto"] is False


def test_o_total_e_o_que_a_central_declarou_e_nao_o_que_veio(monkeypatch):
    """1.757 declarados, 500 nesta página, 2 ordens lidas — e `total` é 1.757.

    Ler o total da resposta como «o que chegou agora» é o defeito que o fixture
    existe para impedir: gravar 1.257 ordens que nunca vieram.
    """
    ligar(monkeypatch, [
        envelope([ORDEM_DE_PEDIDO], PAGINACAO_COM_PROXIMA),
        envelope([ORDEM_DE_CANCELAMENTO], PAGINACAO_SEM_PROXIMA),
    ])
    r = cnib_api.ordens_na_janela("2026-06-01", "2026-06-30",
                                  cpf_usuario=CPF_DE_EXEMPLO)
    assert r["total"] == 1757
    assert r["lidas"] == 2


def test_a_pagina_que_nao_se_entende_nao_vira_fim_da_lista(monkeypatch):
    """**A defesa mais estreita deste módulo, e a mais fácil de perder.**

    Esta resposta tem `paginacao.tem_proxima_pagina: true` e **não tem ordens
    em nenhuma das três formas**. Sem a parada explícita na forma `outra`, o
    laço leria o `tem_proxima_pagina` que está lá, não acharia lista nenhuma e
    continuaria — 200 vezes, contra a Central de verdade.

    E, pior que girar: `lidas == 0` com `vazio == False`, porque ela **não é**
    a forma vazia. Quem olhasse só o número concluiria «nada mudou» sobre uma
    resposta que o programa não sabe ler.
    """
    desconhecida = {"data": {"paginacao": {"tem_proxima_pagina": True}},
                    "success": True}
    central = ligar(monkeypatch, [desconhecida])
    r = cnib_api.ordens_na_janela("2026-09-01", "2026-09-18",
                                  cpf_usuario=CPF_DE_EXEMPLO)
    assert r["forma"] == "outra"
    assert r["forma_estranha"] is True
    assert r["lidas"] == 0
    # **As duas coisas que se confundiriam**:
    assert r["vazio"] is False
    assert len(central.corpos) == 1
    assert r["paginas"] == 1


def test_a_forma_vazia_e_vazio_com_a_frase_da_central(monkeypatch):
    """O outro zero: a Central dizendo que não há ordens nesta janela.

    **E ele não é prova de ausência.** Medido em 18/09/2026: esta mesma
    resposta, com esta mesma frase, veio para dias que tinham ordens — e horas
    depois as ordens apareceram. O módulo devolve a frase e o rótulo, e **não
    conclui**: quem decide o que fazer com o zero é o atualizador, com janela
    sobreposta.
    """
    ligar(monkeypatch, [ENVELOPE_VAZIA])
    r = cnib_api.ordens_na_janela("2026-09-12", "2026-09-12",
                                  cpf_usuario=CPF_DE_EXEMPLO)
    assert r["vazio"] is True
    assert r["forma_estranha"] is False
    assert r["lidas"] == 0
    assert r["mensagem"] == "Não há ordens para os critérios informados."


def test_o_freio_do_laco_avisa_que_parou_nele(monkeypatch):
    """Freio calado é pior que freio nenhum: quem lê acha que veio tudo.

    Uma Central que respondesse `tem_proxima_pagina: true` para sempre faria o
    servidor da serventia varrer o país. O teto é declarado, e a resposta
    **diz** que parou nele.
    """
    central = ligar(monkeypatch, [
        envelope([ORDEM_DE_PEDIDO], PAGINACAO_COM_PROXIMA)])
    r = cnib_api.ordens_na_janela("2020-01-01", "2026-09-18",
                                  cpf_usuario=CPF_DE_EXEMPLO)
    assert r["parou_no_teto"] is True
    assert r["paginas"] == cnib_api.MAXIMO_DE_PAGINAS
    assert len(central.corpos) == cnib_api.MAXIMO_DE_PAGINAS


def test_as_paginas_podem_repetir_ordem_e_o_transporte_nao_deduplica(monkeypatch):
    """**Medido: 3.000 lidas, 2.996 distintas** — quatro repetiram entre páginas.

    O transporte devolve o que veio, na ordem em que veio. Quem tira a
    repetição é o `UPSERT` pela chave, no atualizador — e é por isso que ele
    **não pode** ser escrito confiando em página como se fosse lote. Se este
    teste ficasse vermelho por alguém «limpando» a lista aqui, a deduplicação
    teria mudado de lugar sem que o lugar novo soubesse.
    """
    ligar(monkeypatch, [
        envelope([ORDEM_DE_PEDIDO], PAGINACAO_COM_PROXIMA),
        envelope([ORDEM_DE_PEDIDO], PAGINACAO_SEM_PROXIMA),
    ])
    r = cnib_api.ordens_na_janela("2026-06-01", "2026-06-30",
                                  cpf_usuario=CPF_DE_EXEMPLO)
    assert r["lidas"] == 2


# ================================================ 3. o que vai no pedido


def test_o_pedido_leva_os_sete_campos_que_a_casa_ja_mandou(monkeypatch):
    """Os quatro obrigatórios do contrato estão aqui, e três a mais.

    `data_inicial` e `data_final` são **opcionais para o contrato** — e é
    justamente por isso que uma requisição sem eles devolve a fila inteira. A
    casa sempre os manda.
    """
    central = ligar(monkeypatch, [
        envelope([ORDEM_DE_PEDIDO], PAGINACAO_SEM_PROXIMA)])
    cnib_api.uma_pagina("2026-09-01", "2026-09-18", cpf_usuario=CPF_DE_EXEMPLO)
    corpo = central.corpos[0]
    assert set(corpo) == {"cpf_usuario", "ordens_visualizadas", "data_inicial",
                          "data_final", "pagina_inicial", "tamanho_pagina",
                          "proxima_pagina"}
    assert corpo["data_inicial"] == "2026-09-01"
    assert corpo["data_final"] == "2026-09-18"
    assert corpo["pagina_inicial"] == 1
    assert corpo["tamanho_pagina"] == cnib_api.TAMANHO_DA_PAGINA
    # **`proxima_pagina` vai presente e FALSO, e é medido, não descuido.**
    assert corpo["proxima_pagina"] is False


def test_a_leitura_nao_consome_a_fila_por_padrao(monkeypatch):
    """**A medição que governa o desenho: 341.697 → 341.497 com `false`.**

    Com `ordens_visualizadas: false` a leitura **tira ordem da fila** de quem
    está esperando; com `true` ela não mexe (341.496 antes e depois). Por isso
    o padrão deste módulo é `true`: conferir a ligação e clicar duas vezes não
    podem consumir ordem de ninguém.
    """
    central = ligar(monkeypatch, [
        envelope([ORDEM_DE_PEDIDO], PAGINACAO_SEM_PROXIMA)])
    cnib_api.uma_pagina("2026-09-01", "2026-09-18", cpf_usuario=CPF_DE_EXEMPLO)
    assert central.corpos[0]["ordens_visualizadas"] is True

    # E quem quiser consumir, pede por escrito.
    central2 = ligar(monkeypatch, [
        envelope([ORDEM_DE_PEDIDO], PAGINACAO_SEM_PROXIMA)])
    cnib_api.uma_pagina("2026-09-01", "2026-09-18", cpf_usuario=CPF_DE_EXEMPLO,
                        visualizadas=False)
    assert central2.corpos[0]["ordens_visualizadas"] is False


def test_sem_o_cpf_de_quem_pergunta_o_pedido_nem_sai(monkeypatch):
    """`cpf_usuario` é obrigatório no contrato, e é o recibo de quem pediu.

    A recusa é **local e com o caminho**: mandar sem ele faria a Central
    responder 400 com o nome do campo, e o escrevente procuraria em
    Configurações sem saber qual seção.
    """
    ligar(monkeypatch, [envelope([], PAGINACAO_SEM_PROXIMA)])
    with pytest.raises(cnib_api.CnibError) as erro:
        cnib_api.uma_pagina("2026-09-01", "2026-09-18", cpf_usuario="")
    assert "Configurações" in str(erro.value)


def test_o_tamanho_da_pagina_e_o_que_esta_casa_mediu(monkeypatch):
    """500 é o que a casa mandou e o que voltou (`retornadas_por_pagina: 500`).

    **Não é o do contrato**: ele declara `tamanho_pagina` como inteiro sem
    máximo nenhum. Subir este número sem medir seria pedir à Central o que ela
    não prometeu.
    """
    central = ligar(monkeypatch, [
        envelope([ORDEM_DE_PEDIDO], PAGINACAO_SEM_PROXIMA)])
    cnib_api.uma_pagina("2026-09-01", "2026-09-18", cpf_usuario=CPF_DE_EXEMPLO)
    assert cnib_api.TAMANHO_DA_PAGINA == 500
    assert central.corpos[0]["tamanho_pagina"] == 500


def test_a_consulta_por_documento_devolve_o_retrato_de_agora(monkeypatch):
    """A outra pergunta, e ela **não tem janela de data**: é o agora.

    `indisponivel: false` aqui **é resposta** — ao contrário do zero da janela,
    que pode ser defasagem. São dois zeros, e o nome do campo diz qual se está
    lendo.
    """
    central = ligar(monkeypatch, [ENVELOPE_CONSULTA])
    r = cnib_api.consultar_por_documento("00.000.000/0000-00",
                                         cpf_usuario=CPF_DE_EXEMPLO)
    assert r["respondeu"] is True
    assert r["indisponivel"] is False
    assert r["quantas"] == 0
    assert r["protocolos"] == []
    assert r["nome"] == "EMPRESA DE EXEMPLO LTDA"
    assert r["documento"] == "00.000.000/0000-00"
    assert r["forma"] == "documento"
    assert central.caminhos == ["/api/ordem/consultar"]
    # O documento vai **como veio do balcão**: medido em nove scripts, é assim
    # que a casa manda, e é assim que a Central o ecoa de volta.
    assert central.corpos[0] == {"cpf_usuario": CPF_DE_EXEMPLO,
                                "documento": "00.000.000/0000-00"}


def test_resposta_sem_o_campo_nao_vira_zero(monkeypatch):
    """Sem `indisponivel`, a Central não disse que não há ordem. A tela lê `respondeu`."""
    ligar(monkeypatch, [{"success": True, "data": {"protocolos": []}}])
    r = cnib_api.consultar_por_documento("00.000.000/0000-00",
                                         cpf_usuario=CPF_DE_EXEMPLO)
    assert r["respondeu"] is False


def test_a_consulta_sem_documento_recusa_antes_da_rede(monkeypatch):
    central = ligar(monkeypatch, [ENVELOPE_CONSULTA])
    with pytest.raises(cnib_api.CnibError):
        cnib_api.consultar_por_documento("", cpf_usuario=CPF_DE_EXEMPLO)
    assert central.corpos == []


# ============================================ 4. os rótulos e os protocolos


def test_as_tres_grafias_do_mesmo_estado_sao_reconhecidas(monkeypatch):
    """`CONCLUÍDO` (6.213), `Concluído` (2) e `Cancelamento total - Concluido` (3).

    **A terceira é a que derrubou a régua.** Eu havia escrito
    `startswith("concluido")`, e ela **não começa** com a palavra: as três
    ordens assim seriam lidas como não concluídas — contra o que o comentário
    do próprio módulo dizia. Quem apontou foi este teste.
    """
    assert cnib_api.e_concluida({"ordemstatus": "CONCLUÍDO"}) is True
    assert cnib_api.e_concluida({"ordemstatus": "Concluído"}) is True
    assert cnib_api.e_concluida(ORDEM_DE_CANCELAMENTO_ANTIGA) is True


def test_o_que_esta_fora_do_vocabulario_nao_se_adivinha():
    """A tentação é `endswith`, e ela tem uma armadilha pior que a `startswith`.

    `NÃO CONCLUÍDO` normalizado é `nao concluido`, que **termina** com a
    palavra: por semelhança, o sistema trataria como terminado justamente o que
    está dizendo o contrário. Igualdade contra o que se mediu.
    """
    assert cnib_api.e_concluida({"ordemstatus": "NÃO CONCLUÍDO"}) is False
    assert cnib_api.e_concluida({"ordemstatus": "Pendente"}) is False
    assert cnib_api.e_concluida({}) is False
    assert cnib_api.e_concluida({"ordemstatus": None}) is False


def test_e_cancelamento_le_o_status_e_nao_o_ordemstatus():
    """São duas colunas diferentes, e a vida da ordem está no `status`."""
    assert cnib_api.e_cancelamento(ORDEM_DE_CANCELAMENTO) is True
    assert cnib_api.e_cancelamento(ORDEM_DE_CANCELAMENTO_ANTIGA) is True
    assert cnib_api.e_cancelamento(ORDEM_DE_PEDIDO) is False


def test_a_linha_de_cancelamento_traz_os_dois_protocolos():
    """**É a peça que faz o atualizador desativar sem adivinhar.**

    Na linha de `CANCELAMENTO`, `protocoloindisponibilidade` é o da ordem
    **cancelada** (`201210...-IA-300`, de 2012) e
    `cancelamentodeindisponibilidade` é o do **próprio cancelamento**
    (`202609...-TA-819`, de 15/09/2026). Trocar os dois desativaria a ordem
    errada — e o estrago apareceria na ficha do imóvel de um terceiro.
    """
    o = ORDEM_DE_CANCELAMENTO
    assert cnib_api.protocolo_cancelado(o) == "201210.2318.00002883-IA-300"
    assert cnib_api.protocolo_do_cancelamento(o) == "202609.1516.00002883-TA-819"
    assert cnib_api.protocolo_cancelado(o) != cnib_api.protocolo_do_cancelamento(o)


def test_quem_nao_cancela_nao_tem_alvo():
    """`""` e não a própria chave: devolver a chave da ordem faria o
    atualizador desativar exatamente a ordem que acabou de chegar."""
    assert cnib_api.protocolo_cancelado(ORDEM_DE_PEDIDO) == ""
    assert cnib_api.protocolo_da_ordem(ORDEM_DE_PEDIDO) == (
        "202606.0116.04723776-IA-912")


def test_a_janela_filtra_pela_data_da_atividade():
    """O cancelamento é de 15/09/2026 e o pedido dele, de 23/10/2012.

    É por isso que a janela da casa serve para receber **o cancelamento de
    ordem antiga** — o caso que o atualizador mais precisa pegar. Uma janela
    lida como «data do pedido» perderia esta ordem inteira.
    """
    o = ORDEM_DE_CANCELAMENTO
    assert o["datapedido"].startswith("23/10/2012")
    assert o["cancelamentodata"].startswith("15/09/2026")
    # E as duas datas são `dd/mm/aaaa hh:mm:ss` — **não ISO**, e é o que mais
    # se erra: `ano()` sobre isto devolve lixo, e não estoura.
    assert len(o["datapedido"]) == 19
    assert len(o["cancelamentodata"]) == 19


# ============================================ as provas de coerência
#
# As duas daqui não testam função nenhuma: **testam o módulo contra o dado que
# ele vai receber**, e contra o que ele não pode fazer. São as que ficam
# vermelhas quando alguém mexe na lista de campos por conveniência.

def test_o_vocabulario_do_modulo_cobre_exatamente_o_que_a_central_manda():
    """**A transcrição e o código amarrados um no outro.**

    Toda chave que a Central manda está declarada em `CAMPOS_DA_ORDEM`, e toda
    chave declarada aparece em pelo menos uma das duas formas de ordem. Campo
    novo da Central fica vermelho **aqui** — em vez de ser lido por engano ou
    descartado em silêncio —, e nome declarado a mais também: vocabulário que
    promete campo que não existe é o «teto que mente», na forma de dicionário.

    Os mesmos dois sentidos para a paginação, contra `PAGINACAO_REAL`.
    """
    da_central = set(ORDEM_DE_PEDIDO) | set(ORDEM_DE_CANCELAMENTO)
    assert da_central == set(cnib_api.CAMPOS_DA_ORDEM)

    assert set(PAGINACAO_COM_PROXIMA) == set(cnib_api.PAGINACAO_REAL)
    assert set(PAGINACAO_SEM_PROXIMA) == set(cnib_api.PAGINACAO_REAL)


def test_a_ordem_de_cancelamento_e_a_de_pedido_mais_tres_campos():
    """13 campos na que pede, 16 na que desfaz — e a diferença é **exata**.

    Se um dia a Central mandar um campo a mais só na linha de cancelamento,
    este teste fica vermelho antes de o atualizador gravar com uma coluna que
    ninguém conferiu.
    """
    tres = {"cancelamentodeindisponibilidade", "cancelamentotipo",
            "cancelamentodata"}
    assert len(ORDEM_DE_PEDIDO) == 13
    assert len(ORDEM_DE_CANCELAMENTO) == 16
    assert set(ORDEM_DE_CANCELAMENTO) - set(ORDEM_DE_PEDIDO) == tres
    assert set(ORDEM_DE_PEDIDO) - set(ORDEM_DE_CANCELAMENTO) == set()


def test_o_documento_da_parte_vem_com_e_sem_mascara():
    """**Os dois formatos saem da mesma API.** Medido no mesmo dia.

    Quem gravar o que veio guarda as duas formas, e quem comparar por
    igualdade não acha — é a armadilha que a casa já pagou no CNIB, quando a
    busca por nome devolvia zero para todo mundo.
    """
    com_mascara = ORDEM_DE_PEDIDO["partes"][0]["cpfcnpj"]
    sem_mascara = ORDEM_DE_CANCELAMENTO_ANTIGA["partes"][0]["cpfcnpj"]
    assert "." in com_mascara and "-" in com_mascara
    assert "." not in sem_mascara and sem_mascara.isdigit()


def test_a_matricula_vem_como_lista_e_vazia():
    """O campo que ligaria a ordem ao imóvel existe, é lista, e não veio
    preenchido em nenhuma das 6.218. **É lista e não texto** — quem escrever o
    leitor esperando string vai tratar uma lista como endereço."""
    for ordem in (ORDEM_DE_PEDIDO, ORDEM_DE_CANCELAMENTO,
                  ORDEM_DE_CANCELAMENTO_ANTIGA):
        for parte in ordem["partes"]:
            assert parte["matricula"] == []


def test_o_nulo_e_o_falso_sao_coisas_diferentes_nas_ordens_antigas():
    """`ordemprioritaria` é `False` em 2026 e `None` em 2012 e 2013.

    Um portão que tratasse os dois como falso passaria nos dois **sem nunca ter
    medido a diferença** — e `None` aqui provavelmente quer dizer «este campo
    não existia no pedido», que não é «não é prioritária».
    """
    assert ORDEM_DE_PEDIDO["ordemprioritaria"] is False
    assert ORDEM_DE_CANCELAMENTO["ordemprioritaria"] is None
    assert ORDEM_DE_CANCELAMENTO["segredodejustica"] is None


def _docstrings(arvore) -> set:
    """Os NÓS que são docstring — para excluí-los da varredura pelo objeto.

    **Pelo nó, e não pelo texto**: `ast.get_docstring` limpa a indentação, e o
    texto limpo nunca bate com o literal cru da árvore — comparar os dois
    deixaria todo docstring passando como se fosse código.
    """
    marca: set = set()
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if not isinstance(corpo, list) or not corpo:
            continue
        primeiro = corpo[0]
        if (isinstance(primeiro, ast.Expr)
                and isinstance(primeiro.value, ast.Constant)
                and isinstance(primeiro.value.value, str)):
            marca.add(id(primeiro.value))
    return marca


def test_este_modulo_nao_escreve_e_nao_toca_no_banco():
    """**Ele fala; quem grava é o atualizador.**

    O dia em que alguém puser um `INSERT` aqui dentro, o transporte vira duas
    coisas — e a regra da casa é que só o domínio grava, com `con` recebido.

    **E A PRIMEIRA VERSÃO DESTE TESTE BATEU NA PRÓPRIA PROSA — décima segunda
    vez neste projeto.** Ela procurava as palavras no arquivo inteiro, e o
    `ri_cnib` das seis linhas que explicam a fronteira («o espelho é
    `ri_cnib_ordens`; quem grava é o atualizador») acusou o módulo de tocar no
    espelho. **A explicação da regra parecia a violação dela.**

    Agora ele lê com `ast` e olha o que a regra quer dizer: o que se importa, o
    que se escreve em literal e **como se chama o que se define**. Prosa não
    chega em nenhum dos três.
    """
    arvore = ast.parse(Path(cnib_api.__file__).read_text(encoding="utf-8"))
    # 1. O QUE SE IMPORTA. Não se alcança o banco sem importá-lo.
    importados: set = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados |= {a.name.split(".")[0] for a in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module.split(".")[0])
    assert not importados & {"sqlite3", "database", "ri_cnib"}, importados

    # 2. O QUE SE ESCREVE. SQL em literal continua SQL — mesmo sem importar
    #    nada, se alguém receber a conexão de fora.
    docstrings = _docstrings(arvore)
    literais = [n.value for n in ast.walk(arvore)
                if isinstance(n, ast.Constant)
                and isinstance(n.value, str) and id(n) not in docstrings]
    for proibido in ("INSERT", "UPDATE", "DELETE"):
        sujos = [t for t in literais if proibido in t]
        assert not sujos, f"{proibido} em literal: {sujos[:2]}"

    # 3. COMO SE CHAMA O QUE SE DEFINE. É a régua do usucapião, das fraudes e do
    #    CNIB: o módulo que não decide não tem função que decida.
    nomes = {n.name for n in ast.walk(arvore)
             if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    for proibido in ("gravar", "registrar", "averbar", "decidir", "lavrar"):
        culpados = [n for n in nomes if proibido in n]
        assert not culpados, f"nome de decisão em cnib_api: {culpados}"


def test_o_caminho_medido_e_o_ligado_sao_os_mesmos():
    """Sete caminhos declarados, dois ligados — e os ligados são os medidos.

    Os outros cinco **ficam declarados de propósito**: caminho que some da
    lista é caminho que alguém reinventa. E `_bater` recusa quem não estiver em
    `CAMINHOS_LIGADOS` — oferecer caminho que a casa nunca usou seria assinar
    por quem o usou.
    """
    assert cnib_api.CAMINHOS_LIGADOS == {"visualizar_v2", "consultar"}
    assert cnib_api.CAMINHOS_LIGADOS <= set(cnib_api.CAMINHO)
    assert cnib_api.CAMINHO["visualizar_v2"] == "/api/v2/ordem/visualizar"
    assert cnib_api.CAMINHO["consultar"] == "/api/ordem/consultar"
    assert cnib_api.METODO_DO_CAMINHO["visualizar_v2"] == "POST"

    with pytest.raises(cnib_api.CnibError) as erro:
        cnib_api._bater("responder", corpo={})
    # A frase diz onde conferir — e é ela que o balcão lê.
    assert "não está ligado" in str(erro.value)


def test_o_cnib_tem_um_ambiente_so_e_o_modulo_concorda_com_a_credencial():
    """O contrato declara `servers: null`, e as variantes de homologação
    **não resolvem** em DNS — medido: `serventia-api-hml`, `-homolog`, `-teste`
    e `.sandbox` não existem.

    As duas listas são a mesma coisa escrita em dois arquivos, e é assim que
    elas divergem: por isso o teste compara as duas em vez de conferir cada uma
    contra uma constante escrita aqui dentro.
    """
    assert set(cnib_api.BASE_POR_AMBIENTE) == set(
        CRED.AMBIENTES_DA_CENTRAL[CRED.CNIB])
    assert CRED.AMBIENTES_DA_CENTRAL[CRED.CNIB] == (CRED.PRODUCAO,)
    assert cnib_api.BASE_POR_AMBIENTE[CRED.PRODUCAO] == (
        "https://serventia-api.onr.org.br")


def test_o_https_e_forcado_na_base():
    """Aqui viaja o `client_secret` e viaja o que a serventia publica sobre os
    bens de alguém. É a decisão do selador: **quando a rede é o meio, quem
    decide o transporte é a casa** — e não o arquivo de quem publica o
    contrato (foi assim que o WSDL de homologação da CRA declarou `http://`)."""
    assert cnib_api.partes("https://serventia-api.onr.org.br") == (
        "serventia-api.onr.org.br", 443, "")
    with pytest.raises(cnib_api.CnibError):
        cnib_api.partes("http://serventia-api.onr.org.br")


def test_a_recusa_de_dado_e_value_error_e_a_de_rede_nao():
    """Regra da casa: erro de regra é subclasse de `ValueError`, com mensagem
    pronta para o balcão — a rota faz `flash(..., 'danger')`. Erro de rede não
    é regra: é «não chegou lá».

    **E quem tratar só `CnibError` apanha as duas**, que é o que a hierarquia
    promete.
    """
    assert issubclass(cnib_api.CnibRecusou, ValueError)
    assert issubclass(cnib_api.CnibRecusou, cnib_api.CnibError)
    assert issubclass(cnib_api.CnibError, RuntimeError)


def test_o_token_vai_para_o_host_do_provedor_de_identidade(monkeypatch):
    """**NENHUM TOKEN SAIA DAQUI, e os 35 testes passavam** — 20/09/2026.

    Relato do oficial na primeira leitura de verdade: *«fui tentar baixar a
    09/2026 da cnib e deu: A base do CNIB tem de ser https, e veio «»»*.

    A causa era uma palavra: `token` chamava `_bater_cru` **sem
    `url_absoluta=True`**, e o endereço da autenticação é um endereço
    INTEIRO, de outro host. Sem ela, o ramo relativo pedia `partes("")` e
    estourava antes de abrir a conexão.

    **O PARÂMETRO EXISTIA, DOCUMENTADO, PARA ESTA ÚNICA CHAMADA** — e nenhuma
    chamada o passava. Não é função sem chamador: é **argumento sem quem o
    passe**, e nenhum varredor desta casa acusa isso.

    E ELE ESCAPAVA DOS TESTES POR CONSTRUÇÃO: a bancada troca `token`
    justamente para a primeira chamada não sair pela rede, de modo que o único
    caminho que a troca escondia era o que estava quebrado. Este teste
    exercita `token` **de verdade**, trocando só o transporte.
    """
    vistos = []

    def transporte(metodo, caminho, **kw):
        vistos.append({"metodo": metodo, "caminho": caminho,
                       "url_absoluta": kw.get("url_absoluta"),
                       "base": kw.get("base"), "tipo": kw.get("tipo")})
        return {"status": 200, "bytes": b"",
                "json": {"access_token": "TOKEN-DE-MENTIRA",
                         "expires_in": 3600, "token_type": "Bearer"},
                "texto": ""}

    monkeypatch.setattr(cnib_api, "credencial",
                        lambda *a, **k: ("cns-000000", "segredo-de-mentira"))
    monkeypatch.setattr(cnib_api, "_bater_cru", transporte)
    cnib_api.esquecer_o_token()

    assert cnib_api.token() == "TOKEN-DE-MENTIRA"
    assert len(vistos) == 1
    pedido = vistos[0]
    # O ENDEREÇO VAI INTEIRO, e a base não é usada.
    assert pedido["url_absoluta"] is True
    assert pedido["caminho"] == cnib_api.AUTENTICACAO
    assert pedido["base"] is None
    # E ELE É FORMULÁRIO, e não JSON — é o que o provedor de identidade quer.
    assert pedido["tipo"] == cnib_api.TIPO_DO_FORMULARIO
    cnib_api.esquecer_o_token()
