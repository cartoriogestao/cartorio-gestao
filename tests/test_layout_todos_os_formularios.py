"""TODO FORMULÁRIO DE TODA TELA, MANDADO COMO O BALCÃO MANDARIA.

POR QUE ESTE TESTE EXISTE
    As «funções» da ordem do oficial são os formulários: é por eles que o balcão faz qualquer
    coisa. Os testes de cada módulo montam o POST na mão, com o que o autor sabia que a rota
    queria, e por isso provam a rota, e não a tela. Foi assim que dez formulários ficaram sem
    token em 27/08/2026, e ninguém viu. Aqui o envio sai do HTML que a pessoa recebe.

AS DUAS PASSADAS
    `como a tela vem`: sem mexer em nada, como quem clica sem preencher.
    `preenchido`: o que está vazio recebe um valor de ensaio pelo tipo e pelo nome do campo, e o
    envio chega mais fundo na rota.

    As duas cobram a mesma coisa: **erro de regra é aviso ao balcão, e não HTTP 500** (regra da
    casa). Aqui não se confere se o ato ficou certo: isso é dos testes de cada módulo.

O QUE A TRAVA BARRA NÃO É DEFEITO
    `layout_ensaio` barra rede, programa de fora e arquivo fora da pasta. Se a própria trava cai
    sem ninguém tratar, é o limite do teste, e fica fora da conta. Mas o erro que a rota levanta
    **por causa** da falta de rede é defeito: a Central fora do ar é coisa de todo dia.

CADA ENVIO PARTE DA CASA CONGELADA
    Sem isso, um «apagar» tiraria do lugar o que o formulário seguinte precisa, e o resultado
    dependeria da ordem.

`CG_LAYOUT_AREAS=ri` encurta a rodada de quem está mexendo numa área.
"""
from __future__ import annotations

import io
import os
import re
from collections import Counter

import flask
import pytest
from werkzeug.datastructures import MultiDict

import layout_ensaio as E
from layout_casa import AREAS, area_da_regra, areas_pedidas, casa  # noqa: F401

pytestmark = pytest.mark.lento

# Medido em 31/10/2026, com todas as áreas. Existe para pegar a semente que parou de semear.
PISO_DE_FORMULARIOS = 600

# Sair e trocar de layout mudam a sessão de quem está sendo testado, e têm testes próprios.
NAO_MANDAR = {"logout", "preferencia_layout", "preferencia_layout_padrao"}


def _de_trava(excecao: BaseException) -> bool:
    return isinstance(excecao, (E.AcaoBloqueada, FileNotFoundError)) and "barrado pela trava" in str(excecao)


def _chave(formulario: dict, botao: dict | None, regra) -> tuple:
    """A mesma rota com os mesmos campos é o mesmo formulário, em qualquer ficha. O que muda é a `acao`
    escondida: uma rota só faz vinte coisas nas Notas. Sem isto, trinta fichas viram seiscentos envios."""
    escondida = next((c["valor"] for c in formulario["campos"] if c["nome"] == "acao" and c["tipo"] == "hidden"), "")
    return (regra.rule, formulario["method"], tuple(sorted({c["nome"] for c in formulario["campos"]})),
            (botao or {}).get("nome", ""), (botao or {}).get("valor", ""), escondida)


@pytest.fixture(scope="module")
def formularios(casa):  # noqa: F811
    """Os formulários diferentes da casa, cada um uma vez. A casca sai de uma tela só."""
    c = casa.cliente("ADMIN", "novo")
    vistos: dict[tuple, dict] = {}
    for _endpoint, endereco in casa.enderecos(areas_pedidas()):
        resposta = c.get(endereco)
        if resposta.status_code != 200 or resposta.mimetype != "text/html":
            continue
        for f in E.ler_pagina(resposta.get_data(as_text=True)).formularios:
            if f["method"] != "post":
                continue
            acao = f["action"] or endereco
            for botao in [b for b in f["botoes"] if b["tipo"] != "button"] or [None]:
                alvo = (botao or {}).get("formaction") or acao
                regra = E.casar(casa.app, alvo, "POST")
                if regra in (None, "redireciona") or regra.endpoint in NAO_MANDAR:
                    continue
                vistos.setdefault(_chave(f, botao, regra), {"tela": endereco, "alvo": alvo, "regra": regra.rule,
                                                            "endpoint": regra.endpoint, "form": f, "botao": botao})
    return list(vistos.values())


def _valor_de_ensaio(c: dict, hoje: str) -> str:
    """O que um escrevente de ensaio digitaria, pelo tipo e pelo nome do campo."""
    nome, tipo = c["nome"].lower(), c["tipo"]
    if tipo == "date":
        return hoje
    if tipo == "time":
        return "10:00"
    if tipo == "datetime-local":
        return f"{hoje}T10:00"
    if tipo == "month":
        return hoje[:7]
    if tipo == "number":
        return c["min"] or "1"
    if tipo == "email" or "email" in nome:
        return "ana.exemplo@exemplo.invalid"
    if tipo == "url" or "url" in nome:
        return "https://exemplo.invalid/"
    if tipo == "tel" or "telefone" in nome or "celular" in nome:
        return "(00) 90000-0000"
    if "cnpj" in nome:
        return "00000000000191"
    if "cpf" in nome or "documento" in nome:
        return "00000000191"
    if "cep" in nome:
        return "65000000"
    if nome in ("uf", "estado") or nome.endswith("_uf"):
        return "MA"
    if nome.startswith("data") or nome.endswith("_data") or "vencimento" in nome or "competencia" in nome:
        return hoje[:7] if "competencia" in nome else hoje
    if "selo" in nome:
        return "AVESVD000000NARRKWVNJCRSVO11"
    if re.search(r"valor|preco|saldo|centavos|custas|base_calculo|emolumento", nome):
        return "100,00"
    if re.search(r"numero|quantidade|folha|livro|parcelas|vias|_id$|^id$|ano$|mes$|dia$", nome):
        return "1"
    if re.search(r"teor|texto|motivo|fundamento|observa|justific|detalhe|descri|mensagem|nota", nome):
        return "Texto de ensaio, com letras suficientes para passar do piso da casa."
    if "nome" in nome or "interessado" in nome or "requerente" in nome:
        return "Ana Exemplo"
    return "Ensaio"


def _preenchido(formulario: dict, botao: dict | None, hoje: str) -> tuple[MultiDict, bool]:
    pares = MultiDict()
    tem_arquivo = False
    for c in formulario["campos"]:
        if not c["nome"] or c["desligado"]:
            continue
        if c["tipo"] == "file":
            pares.add(c["nome"], (io.BytesIO(b"%PDF-1.4 ensaio do layout novo"), "ensaio.pdf"))
            tem_arquivo = True
        elif c["tipo"] in ("checkbox", "radio"):
            if c["marcado"] or c["obrigatorio"]:
                pares.add(c["nome"], c["valor"] or "on")
        elif c["tag"] == "select":
            valores = E.valor_do_select(c)
            if not any(valores):
                livres = [o["valor"] for o in c["opcoes"] if o["valor"] and not o["desligada"]]
                valores = livres[:1]
            for v in valores:
                pares.add(c["nome"], v)
        elif c["tipo"] == "hidden" or c["valor"]:
            pares.add(c["nome"], c["valor"])
        else:
            pares.add(c["nome"], _valor_de_ensaio(c, hoje))
    if botao is not None and botao["nome"]:
        pares.add(botao["nome"], botao["valor"])
    return pares, tem_arquivo


def _mandar_todos(casa, formularios, montar) -> list[str]:  # noqa: F811
    excecoes: list[BaseException] = []

    def anota(_remetente, exception, **_):
        excecoes.append(exception)

    flask.got_request_exception.connect(anota, casa.app, weak=False)
    ruins = []
    try:
        for item in formularios:
            casa.restaurar()
            excecoes.clear()
            c = casa.cliente("ADMIN", "novo")
            dados, multipart = montar(item)
            quem = f'{item["tela"]} -> {item["alvo"]} {[k for k in dados.keys() if k != "csrf_token"][:8]}'
            try:
                resposta = c.post(item["alvo"], data=dados,
                                  content_type="multipart/form-data" if multipart else None)
                if resposta.mimetype != "text/event-stream":
                    resposta.get_data()
                # A TELA DEPOIS DE GRAVAR é parte da função: é ela que traz o aviso, e a recusa volta por ela.
                destino = resposta.headers.get("Location", "") if resposta.status_code in (301, 302, 303) else ""
                if destino.startswith("/") and "/logout" not in destino:
                    depois = c.get(destino)
                    if depois.mimetype != "text/event-stream":
                        depois.get_data()
                    if depois.status_code == 500 and not excecoes:
                        ruins.append(f"{quem}: a tela depois de gravar ({destino}) dá 500")
            except Exception as erro:                              # noqa: BLE001
                ruins.append(f"{quem}: o cliente levantou {type(erro).__name__}: {str(erro)[:200]}")
                continue
            defeitos = [e for e in excecoes if not _de_trava(e)]
            if defeitos:
                e = defeitos[0]
                ruins.append(f"{quem}: {resposta.status_code} {type(e).__name__}: {str(e)[:240]}")
            elif resposta.status_code == 500 and not excecoes:
                ruins.append(f"{quem}: 500 sem exceção")
            elif resposta.status_code == 400 and b"Token CSRF" in resposta.get_data():
                ruins.append(f"{quem}: o formulário não manda o token que a rota exige")
    finally:
        flask.got_request_exception.disconnect(anota, casa.app)
    return ruins


def test_todo_filtro_de_lista_nao_da_erro(casa):  # noqa: F811
    """Formulário de consulta não grava: vai como a tela vem e preenchido, sem restaurar o banco."""
    c = casa.cliente("ADMIN", "novo")
    excecoes: list[BaseException] = []

    def anota(_remetente, exception, **_):
        excecoes.append(exception)

    flask.got_request_exception.connect(anota, casa.app, weak=False)
    vistos, ruins = set(), []
    try:
        for _endpoint, endereco in casa.enderecos(areas_pedidas()):
            resposta = c.get(endereco)
            if resposta.status_code != 200 or resposta.mimetype != "text/html":
                continue
            for f in E.ler_pagina(resposta.get_data(as_text=True)).formularios:
                # Sem endereço e fora do conteúdo: é da casca, e o script é quem o manda.
                if f["method"] != "get" or not (f["no_conteudo"] or f["action"]):
                    continue
                alvo = f["action"] or endereco
                chave = (alvo.split("?")[0], tuple(sorted({x["nome"] for x in f["campos"]})))
                if chave in vistos or E.casar(casa.app, alvo, "GET") in (None, "redireciona"):
                    continue
                vistos.add(chave)
                for pares in (MultiDict(E.como_o_navegador_manda(f)), _preenchido(f, None, casa.hoje)[0]):
                    excecoes.clear()
                    # Formulário de consulta troca a consulta do endereço pela dele, como no navegador.
                    r = c.get(alvo.split("?")[0], query_string=[(k, v) for k, v in pares.items(multi=True)
                                                                if not isinstance(v, tuple)])
                    if r.mimetype != "text/event-stream":
                        r.get_data()
                    defeitos = [e for e in excecoes if not _de_trava(e)]
                    if defeitos or (r.status_code == 500 and not excecoes):
                        ruins.append(f"{endereco} -> {alvo} {dict(pares)}: {[f'{type(e).__name__}: {str(e)[:200]}' for e in defeitos]}")
    finally:
        flask.got_request_exception.disconnect(anota, casa.app)
    assert not ruins, f"{len(ruins)} de {len(vistos)}:\n  " + "\n  ".join(ruins[:60])


def test_a_varredura_achou_os_formularios(formularios):
    if set(areas_pedidas()) != set(AREAS):
        pytest.skip("rodada de uma área só: o piso é da casa inteira")
    assert len(formularios) >= PISO_DE_FORMULARIOS, len(formularios)


def test_todo_formulario_como_a_tela_vem_nao_da_erro(casa, formularios):  # noqa: F811
    ruins = _mandar_todos(casa, formularios, lambda i: (MultiDict(E.como_o_navegador_manda(i["form"], i["botao"])), False))
    assert not ruins, f"{len(ruins)} de {len(formularios)}:\n  " + "\n  ".join(ruins[:80])


def test_todo_formulario_preenchido_nao_da_erro(casa, formularios):  # noqa: F811
    ruins = _mandar_todos(casa, formularios, lambda i: _preenchido(i["form"], i["botao"], casa.hoje))
    assert not ruins, f"{len(ruins)} de {len(formularios)}:\n  " + "\n  ".join(ruins[:80])


def test_quantas_rotas_que_gravam_a_varredura_alcanca(casa, formularios):  # noqa: F811
    """Só informa: rota que grava sem formulário numa tela semeada fica de fora desta varredura.

    Quem cobra que toda rota que grava tem tela é `test_debitos_do_balcao`. Aqui o número diz o
    alcance, e o piso de formulários impede que ele caia sem ninguém ver.
    """
    alcancadas = Counter(i["endpoint"] for i in formularios)
    areas = areas_pedidas()
    todas = [r for r in E.regras_que_gravam(casa.app) if area_da_regra(r.rule) in areas]
    fora = sorted(r.rule for r in todas if r.endpoint not in alcancadas)
    print(f"\nrotas que gravam: {len(todas)}; alcançadas: {len(todas) - len(fora)}; fora: {len(fora)}")
    print("\n".join(fora[:400]))
    if os.environ.get("CG_LAYOUT_LISTA_FORA"):
        with open(os.environ["CG_LAYOUT_LISTA_FORA"], "w", encoding="utf-8") as saida:
            saida.write("\n".join(fora))
