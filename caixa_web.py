"""
Fluxo de caixa, recibo e protocolo geral — rotas.

Registrado a partir de create_app(), no mesmo padrao do modulo de RI: recebe
os decoradores e utilitarios que ja existem, para nao duplicar autenticacao
nem auditoria.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from flask import Response, abort, flash, redirect, render_template, request, url_for

import emolumentos as EMOL
import fraude as FR
import caixa_depositos as DEP
import caixa_protocolo as CXP
# O PORTAL DO CLIENTE (26/10/2026): o código de acompanhamento no recibo e na
# recepção, e o envio do retrato dos protocolos para a VPS.
import acompanhamento_cliente as ACOMP
import portal_cliente as PORTAL
import contato_do_cliente as CONTATO
import protocolo_documentos as PDOC
import modelos_da_casa as MODELOS
from bd_nativo import banco
from caixa_import import importar as importar_caixa
from caixa_schema import (FORMAS_PAGAMENTO, FUNCOES, NATUREZAS,
                          PECA_DO_AVISO_ORCAMENTO,
                          TIPOS_DOCUMENTO, TIPOS_PROTOCOLO, CaixaError,
                          centavos, cobrar_item_do_protocolo, hash_lancamento,
                          hash_recibo, por_extenso, reais, resumo_caixa)
from ri_odt import gerar_odt, html_para_odf
import seguranca_web as SEGWEB  # B2 (LX11): exceção inesperada não vai para a tela
# O número que a tela mandou (LD13): o que não é número de id vira None, e o
# `WHERE id=%s` com None não acha nada — no PostgreSQL o texto cru («abc», 30
# dígitos) comparado com a coluna `bigint` derrubava a consulta.
from seguranca_web import MAIOR_INTEGER, PAGINA_MAIS_ALTA, numero_digitado
from serventia import (dados as dados_serventia, mascarar_documento,
                       mascarar_email, mascarar_telefone, mascarar_texto)

POR_PAGINA = 50

# QUANTOS ATOS DA TABELA A BUSCA DEVOLVE, NUM SO LUGAR.
#
# A lista aparece em dois caminhos — a pagina do protocolo, que ja abre com o
# resultado quando se recarrega com `?busca_ato=`, e o fragmento que a busca
# enquanto se digita pede (RELATO #53). Com o numero escrito duas vezes, um
# deles mostraria trinta e o outro sessenta no dia em que alguem mexesse num so.
LIMITE_DA_BUSCA_DE_ATOS = 30

# AS DUAS ULTIMAS ESTAVAM AQUI DESDE SEMPRE, E NADA AS PRODUZIA. Medido em
# 28/08/2026: em 21.348 protocolos so existem `ABERTO`, `A_PAGAR` e `PAGO`. O
# comentario do `SCHEMA` as declarava, o rotulo as nomeava, e `_atualizar_
# situacao` ja tinha uma guarda para nao sobrescreve-las — havia uma trava
# esperando um estado que nenhuma rota criava. Agora `caixa_protocolo.encerrar`
# as escreve, e o texto delas diz o que cada uma quer dizer no balcao.
SITUACOES = {
    "ABERTO": "Aberto — nada cobrado ainda",
    "A_PAGAR": "Custas lançadas, aguardando pagamento",
    "PAGO": "Pago",
    **CXP.ENCERRAMENTOS,
}

# `MODELO_RECIBO` — o texto de fábrica do papel CAIXA_RECIBO — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/caixa/CAIXA_RECIBO.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

# `MODELO_ORCAMENTO` — o texto de fábrica do papel CAIXA_ORCAMENTO — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/caixa/CAIXA_ORCAMENTO.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

# `MODELO_RECEPCAO` — o texto de fábrica do papel CAIXA_RECEPCAO — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/caixa/CAIXA_RECEPCAO.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.


def html_do_recibo(con, r, *, settings, emitido_por, funcao, data_extenso,
                   agora, acompanhamento=None) -> str:
    """O recibo como ele sai no papel, em HTML. SÓ LÊ.

    SAIU DE DENTRO DA ROTA (26/10/2026) porque passou a ter dois chamadores: a
    reimpressão do balcão (`caixa_recibo_odt`) e o PDF que sobe para o portal do
    cliente (`portal_cliente.pdf_do_recibo`), que roda fora de requisição. Dois
    jeitos de montar o mesmo recibo divergiriam no primeiro conserto, e o
    cliente baixaria no portal um papel diferente do que levou do balcão.

    `acompanhamento` é o bloco do código (`acompanhamento_cliente.
    codigo_para_o_papel`) — None no PDF do portal, onde o código não pode ir.
    """
    from jinja2.sandbox import SandboxedEnvironment
    dados = json.loads(r["discriminacao"] or "{}")
    env = SandboxedEnvironment(autoescape=False)
    fundos = dados.get("fundos", {})
    tem_fundos = any(centavos(v) for v in fundos.values())
    modelo = MODELOS.corpo_de(con, "CAIXA_RECIBO")
    # O recibo sai do cartorio com o cliente: CPF e telefone vao mascarados,
    # na forma do art. 6, VII e VIII da Lei 13.709/2018 — o que identifica o
    # titular basta, o resto nao precisa viajar no papel.
    html = env.from_string(modelo).render(
        r=dict(r), itens=dados.get("itens", []), fundos=fundos,
        tem_fundos=tem_fundos, lancamento=dados.get("lancamento"),
        # a discriminação do recibo do depósito prévio é ORÇAMENTO (art. 197)
        orcamento=bool(dados.get("orcamento")),
        sv=dados_serventia(settings),
        documento=mascarar_documento(dados.get("documento")),
        telefone=mascarar_telefone(dados.get("telefone")),
        observacao=mascarar_texto(r["observacao"]),
        data_extenso=data_extenso,
        emitido_por=emitido_por, funcao=funcao, agora=agora,
        acompanhamento=acompanhamento)
    # O AJUSTE DA CASA SAI SEM O QUE EXECUTA (22/10/2026, A7); o padrão,
    # como saía.
    return MODELOS.sem_o_que_executa(modelo, html)


def _atos_da_tabela(db, busca, limite=LIMITE_DA_BUSCA_DE_ATOS):
    """Os atos da tabela do tribunal que casam com a busca. **SO LE.**

    E' a MESMA consulta para os dois caminhos que mostram a lista: a pagina do
    protocolo, que ja abre com o resultado quando se recarrega com
    `?busca_ato=`, e o fragmento que a busca enquanto se digita pede (RELATO
    #53). Duas consultas parecidas divergiriam no primeiro conserto, e a lista
    que aparece ao digitar deixaria de ser a que aparece ao clicar.

    `None`/vazio devolve lista vazia, e nao a tabela inteira: quem quer a
    tabela inteira sao 1.317 atos, e isso o balcao nao pede ao abrir a tela.
    """
    termo = (busca or "").strip()
    if not termo:
        return []
    with db.connect() as con:
        return EMOL.buscar(con, termo, limite=limite)


def segunda_assinatura_do_estorno(db, *, papel: str, usuario_id: int,
                                  aprovador: str | None, senha: str | None) -> str:
    """O estorno de lançamento de caixa JÁ FECHADO é de duas pessoas. Só lê.

    Revisão de segurança da 3.7.0 (22/10/2026, M2): qualquer USER estornava
    lançamento de caixa fechado — e até conferido — com um motivo de uma
    palavra, e o item estornado voltava a poder ser quitado: o laço
    quitar/estornar/quitar sem segunda assinatura. Agora quem estorna é
    oficial ou gerente, e OUTRA pessoa com o mesmo papel aprova com a senha
    dela, na hora. Devolve "" quando pode, ou a frase da recusa.
    """
    if str(papel or "").upper() not in ("ADMIN", "MANAGER"):
        return ("Estorno de lançamento de caixa já fechado é do oficial ou do "
                "gerente, com a aprovação de outra pessoa.")
    nome = str(aprovador or "").strip()
    if not nome or not senha:
        return ("Estorno de caixa fechado precisa da aprovação de OUTRA pessoa: "
                "informe o usuário e a senha do aprovador (oficial ou gerente).")
    quem = db.authenticate(nome, str(senha))
    if not quem or str(quem["role"] or "").upper() not in ("ADMIN", "MANAGER"):
        return "Aprovador não reconhecido, ou sem perfil de oficial ou gerente."
    if int(quem["id"]) == int(usuario_id or 0):
        return "O aprovador tem de ser outra pessoa — não quem está estornando."
    return ""


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    """Pendura as rotas do caixa no app ja construido."""

    # Vem do modulo de RI: procura o arquivo nas pastas de trabalho das contas
    # da maquina, e nao a partir de Path.home() — no servico, que roda como
    # SYSTEM, home() devolve o perfil do sistema, onde nunca ha exportacao.
    from ri_web import procurar_arquivos

    def q(sql, params=()):
        with db.connect() as con:
            return banco(con).ler(sql, params)

    def q1(sql, params=()):
        linhas = q(sql, params)
        return linhas[0] if linhas else None

    # Quem emitiu e em que qualidade — implementacao unica, em `app.py`.
    #
    # Quem assina por delegacao tem de dizer em que qualidade o faz. A copia
    # que vivia aqui lia `getattr(request, "usuario_nome", None)`, atributo
    # que nada no sistema definia: todo recibo, orcamento e protocolo de
    # recepcao saia com o nome da substituta do registro de imoveis e a funcao
    # "Escrevente", qualquer que fosse quem estivesse no caixa.
    usuario_nome = app.extensions["usuario_nome"]
    usuario_funcao = app.extensions["usuario_funcao"]
    # QUEM É, e não só como se chama: `fechado_por` e `conferido_por` são
    # chaves para `users(id)`, e o nome não serve para elas.
    usuario_id = app.extensions["usuario_id"]

    # O PAPEL, para o que a tela oferece e o servidor recusa. É implementação
    # única em `app.py`, como `usuario_nome` logo acima — a mesma que
    # `notas_web` e `ri_web` usam.
    usuario_papel = app.extensions["usuario_papel"]

    def bloco_serventia() -> dict:
        return dados_serventia(db.get_settings)

    def caixa_aberto(operador: str):
        return q1("""SELECT * FROM cx_caixas
                     WHERE operador_nome=%s AND situacao='ABERTO'
                     ORDER BY data DESC LIMIT 1""", (operador,))

    def lancamentos_do_caixa(caixa_id):
        return [dict(r) for r in
                q("""SELECT l.*, p.numero protocolo_numero
                     FROM cx_lancamentos l
                     LEFT JOIN cx_protocolos p ON p.id = l.protocolo_id
                     WHERE l.caixa_id=%s ORDER BY l.id""", (caixa_id,))]

    # ------------------------------------------------------------- caixa

    @app.route("/caixa", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def caixa():
        """O caixa do dia de quem está usando o sistema."""
        operador = usuario_nome()
        aberto = caixa_aberto(operador)

        if request.method == "POST":
            acao = request.form.get("acao")

            if acao == "abrir":
                if aberto:
                    flash("Já existe um caixa aberto para você.", "warning")
                    return redirect(url_for("caixa"))
                hoje = date.today().isoformat()
                with db.transaction() as con:
                    banco(con).escrever(
                        """INSERT INTO cx_caixas
                           (data, operador_nome, saldo_inicial, aberto_em, situacao)
                           VALUES (%s,%s,%s,%s, 'ABERTO')
                           ON CONFLICT DO NOTHING""",
                        (hoje, operador,
                         reais(centavos(request.form.get("saldo_inicial"))), db.now()))
                audit("CAIXA_ABERTO", "CAIXA", None, {"operador": operador, "data": hoje})
                flash("Caixa aberto.", "success")
                return redirect(url_for("caixa"))

            if acao == "conferir":
                # A CONFERÊNCIA DO CAIXA FECHADO — um ato que não existia.
                #
                #   `conferido_por` e `conferido_em` estavam no esquema desde o
                #   começo e **nunca foram escritos**: NULL em 2.758 de 2.758.
                #   Não era esquecimento de preencher um campo — era um ato que
                #   o sistema não tinha.
                #
                #   FECHAR NÃO É CONFERIR, e são duas pessoas: quem atende
                #   fecha o próprio caixa e conta o próprio dinheiro; quem
                #   confere é o oficial ou o gerente, depois. Se fossem a mesma
                #   coisa, a conferência não valeria nada.
                #
                #   E por isso ela **não pode ser do próprio operador**: o
                #   sistema recusa, com a frase que diz por quê.
                alvo = q1("SELECT * FROM cx_caixas WHERE id=%s",
                          (numero_digitado(request.form.get("caixa_id")),))
                if not alvo:
                    flash("Não achei esse caixa.", "danger")
                    return redirect(url_for("caixa"))
                if str(alvo["situacao"] or "") != "FECHADO":
                    flash("Só se confere caixa fechado — este ainda está "
                          "aberto.", "danger")
                    return redirect(url_for("caixa"))
                if (alvo["operador_nome"] or "") == usuario_nome():
                    flash("Quem atendeu não confere o próprio caixa. A "
                          "conferência é do oficial ou do gerente — se fosse "
                          "da mesma pessoa, não valeria nada.", "danger")
                    return redirect(url_for("caixa"))
                # QUEM CONFERE É O OFICIAL OU O GERENTE (revisão de segurança
                # de 22/10/2026, M2): a regra estava escrita no texto acima e
                # não na rota — qualquer USER conferia o caixa do colega. Vem
                # depois da recusa do próprio caixa, que é a que fala de quem
                # clicou.
                if usuario_papel() not in ("ADMIN", "MANAGER"):
                    flash("A conferência do caixa é do oficial ou do gerente.",
                          "danger")
                    return redirect(url_for("caixa"))
                with db.transaction() as con:
                    banco(con).escrever(
                        """UPDATE cx_caixas SET conferido_por=%s, conferido_em=%s
                           WHERE id=%s AND conferido_em IS NULL""",
                        (usuario_id(), db.now(), alvo["id"]))
                audit("CAIXA_CONFERIDO", "CAIXA", alvo["id"],
                      {"data": alvo["data"], "operador": alvo["operador_nome"],
                       "diferenca": alvo["diferenca"]})
                flash(f"Caixa de {alvo['data']} conferido. Fica registrado "
                      f"quem conferiu e quando — é o que a correição pergunta.",
                      "success")
                return redirect(url_for("caixa"))

            # A CONFERÊNCIA VEM ANTES DESTA GUARDA, e é de propósito: ela é do
            # caixa de OUTRA pessoa, e quem confere não precisa ter caixa
            # aberto. O oficial que chega no fim do dia para conferir não abriu
            # caixa nenhum — e, com a guarda na frente, a tela mandava ele
            # abrir um para poder conferir o dos outros.
            if not aberto:
                flash("Abra o caixa antes de lançar.", "danger")
                return redirect(url_for("caixa"))

            if acao == "lancar":
                natureza = request.form.get("natureza") or "RECEBIMENTO"
                sentido = NATUREZAS.get(natureza, ("ENTRADA", ""))[0]
                valor = centavos(request.form.get("valor"))
                if valor <= 0:
                    flash("Informe um valor maior que zero.", "danger")
                    return redirect(url_for("caixa"))
                # Duas coisas diferentes que ja se chamaram "numero" aqui: o do
                # protocolo, que o usuario digita, e o de ordem do lancamento,
                # que o sistema gera. Nomes distintos para nao trocar um pelo outro.
                numero_protocolo = (request.form.get("protocolo") or "").strip()
                prot = (q1("SELECT id FROM cx_protocolos WHERE numero=%s",
                           (numero_protocolo,)) if numero_protocolo else None)
                if numero_protocolo and not prot:
                    flash(f"O protocolo {numero_protocolo} não existe. "
                          f"Lançamento não feito.", "danger")
                    return redirect(url_for("caixa"))
                with db.transaction() as con:
                    bd = banco(con)
                    bd.travar("cx_lancamentos.numero")
                    # O anterior se lê DEPOIS da trava: lido antes, dois
                    # lançamentos ao mesmo tempo encadeavam no mesmo hash.
                    anterior = bd.um(
                        """SELECT hash_lancamento FROM cx_lancamentos
                           WHERE caixa_id=%s ORDER BY id DESC LIMIT 1""",
                        (aberto["id"],))
                    h = hash_lancamento(aberto["id"], date.today().isoformat(), natureza,
                                        reais(valor), request.form.get("descricao") or "",
                                        anterior["hash_lancamento"] if anterior else None)
                    ano = date.today().year
                    ultimo = bd.valor(
                        "SELECT MAX(numero) AS n FROM cx_lancamentos WHERE ano=%s",
                        (ano,))
                    numero_ordem = int((ultimo or 0)) + 1
                    bd.escrever(
                        """INSERT INTO cx_lancamentos
                           (numero, ano, caixa_id, protocolo_id, data, hora,
                            natureza, sentido,
                            forma_pagamento, descricao, pagador, pagador_documento,
                            valor, emolumentos, ferc, fadep, femp, ferrfis, selo,
                            hash_lancamento, criado_em)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (numero_ordem, ano, aberto["id"], prot["id"] if prot else None,
                         date.today().isoformat(), datetime.now().strftime("%H:%M"),
                         natureza, sentido,
                         request.form.get("forma_pagamento"),
                         (request.form.get("descricao") or "").strip() or None,
                         (request.form.get("pagador") or "").strip() or None,
                         (request.form.get("pagador_documento") or "").strip() or None,
                         reais(valor),
                         *[reais(centavos(request.form.get(f))) if request.form.get(f)
                           else None
                           for f in ("emolumentos", "ferc", "fadep", "femp", "ferrfis")],
                         (request.form.get("selo") or "").strip() or None,
                         h, db.now()))
                audit("CAIXA_LANCAMENTO", "CAIXA", aberto["id"],
                      {"numero": f"{numero_ordem}/{ano}", "natureza": natureza,
                       "valor": reais(valor)})
                flash(f"Lançamento nº {numero_ordem}/{ano} — R$ {reais(valor)}.", "success")
                return redirect(url_for("caixa"))

            if acao == "estornar":
                lid = numero_digitado(request.form.get("lancamento_id"))
                motivo = (request.form.get("motivo") or "").strip()
                if not motivo:
                    flash("O estorno precisa de motivo.", "danger")
                    return redirect(url_for("caixa"))
                with db.transaction() as con:
                    bd = banco(con)
                    # A marca `estornado` se lê e se grava aqui dentro, com a
                    # linha presa: lida antes, dois cliques estornavam o mesmo
                    # lançamento duas vezes.
                    bd._escrita()
                    orig = bd.um("SELECT * FROM cx_lancamentos WHERE id=%s FOR UPDATE",
                                 (lid,))
                    if not orig or orig["estornado"]:
                        flash("Lançamento não encontrado ou já estornado.", "danger")
                        return redirect(url_for("caixa"))
                    # ESTORNO DE CAIXA JÁ FECHADO É DE DUAS PESSOAS (22/10/2026,
                    # M2) — ver `segunda_assinatura_do_estorno`.
                    if int(orig["caixa_id"] or 0) != int(aberto["id"]):
                        recusa = segunda_assinatura_do_estorno(
                            db, papel=usuario_papel(), usuario_id=usuario_id(),
                            aprovador=request.form.get("aprovador"),
                            senha=request.form.get("aprovador_senha"))
                        if recusa:
                            flash(recusa, "danger")
                            return redirect(url_for("caixa"))
                    estorno_id = bd.escrever(
                        """INSERT INTO cx_lancamentos
                           (caixa_id, protocolo_id, data, hora, natureza, sentido,
                            descricao, valor, estorna_id, motivo_estorno, criado_em)
                           VALUES (%s,%s,%s,%s, 'ESTORNO','ESTORNO', %s,%s,%s,%s,%s)
                           RETURNING id""",
                        (aberto["id"], orig["protocolo_id"], date.today().isoformat(),
                         datetime.now().strftime("%H:%M"),
                         f"Estorno do lançamento {lid}: {motivo}",
                         orig["valor"], lid, motivo, db.now()))[0]["id"]
                    bd.escrever(
                        """UPDATE cx_lancamentos SET estornado=1, estornado_por_id=%s,
                           motivo_estorno=%s WHERE id=%s""",
                        (int(estorno_id), motivo, lid))
                    # F13: o estorno desfaz a quitacao do item e devolve o
                    # protocolo a A_PAGAR quando ainda houver item em aberto.
                    bd.escrever(
                        """UPDATE cx_protocolo_atos
                              SET quitado=0, quitado_em=NULL, quitado_por=NULL,
                                  lancamento_id=NULL
                            WHERE lancamento_id=%s""",
                        (lid,))
                    if orig["protocolo_id"]:
                        pendente = bd.um(
                            """SELECT COUNT(*) AS n FROM cx_protocolo_atos
                               WHERE protocolo_id=%s AND COALESCE(quitado,0)=0""",
                            (orig["protocolo_id"],))
                        n_pend = int((pendente["n"] if pendente else 0) or 0)
                        if n_pend > 0:
                            bd.escrever(
                                """UPDATE cx_protocolos SET situacao='A_PAGAR'
                                   WHERE id=%s AND situacao='PAGO'""",
                                (orig["protocolo_id"],))
                audit("CAIXA_ESTORNO", "CAIXA", aberto["id"],
                      {"lancamento": lid, "motivo": motivo,
                       "caixa_do_lancamento": orig["caixa_id"],
                       "aprovador": (request.form.get("aprovador") or "").strip() or None})
                flash("Estornado. A quitação do item foi desfeita; o lançamento "
                      "original continua na lista, marcado.",
                      "success")
                return redirect(url_for("caixa"))

            if acao == "editar":
                lid = numero_digitado(request.form.get("lancamento_id"))
                l = q1("SELECT * FROM cx_lancamentos WHERE id=%s", (lid,))
                if not l or l["excluido"] or l["estornado"]:
                    flash("Lançamento não encontrado, já excluído ou estornado.", "danger")
                    return redirect(url_for("caixa"))
                if l["caixa_id"] != aberto["id"]:
                    flash("Só se edita lançamento do caixa aberto. Em caixa fechado, "
                          "a correção é por estorno.", "danger")
                    return redirect(url_for("caixa"))
                # O que havia antes fica guardado. Editar sem historico e o
                # mesmo que apagar.
                antes = {c: l[c] for c in ("valor", "natureza", "forma_pagamento",
                                           "descricao", "pagador", "pagador_documento",
                                           "emolumentos", "ferc", "fadep", "femp",
                                           "ferrfis", "selo")}
                historico = json.loads(l["historico"] or "[]")
                historico.append({"em": db.now(), "por": usuario_nome(), "antes": antes})
                novo_valor = centavos(request.form.get("valor"))
                if novo_valor <= 0:
                    flash("Informe um valor maior que zero.", "danger")
                    return redirect(url_for("caixa"))
                natureza = request.form.get("natureza") or l["natureza"]
                with db.transaction() as con:
                    banco(con).escrever(
                        """UPDATE cx_lancamentos SET valor=%s, natureza=%s, sentido=%s,
                           forma_pagamento=%s, descricao=%s, pagador=%s,
                           pagador_documento=%s, emolumentos=%s, ferc=%s, fadep=%s,
                           femp=%s, ferrfis=%s, selo=%s, editado_em=%s, editado_por=%s,
                           historico=%s WHERE id=%s""",
                        (reais(novo_valor), natureza,
                         NATUREZAS.get(natureza, (l["sentido"], ""))[0],
                         request.form.get("forma_pagamento") or l["forma_pagamento"],
                         (request.form.get("descricao") or "").strip() or None,
                         (request.form.get("pagador") or "").strip() or None,
                         (request.form.get("pagador_documento") or "").strip() or None,
                         *[reais(centavos(request.form.get(f))) if request.form.get(f)
                           else None
                           for f in ("emolumentos", "ferc", "fadep", "femp", "ferrfis")],
                         (request.form.get("selo") or "").strip() or None,
                         db.now(), usuario_nome(),
                         json.dumps(historico, ensure_ascii=False), lid))
                audit("CAIXA_LANCAMENTO_EDITADO", "CAIXA", aberto["id"],
                      {"lancamento": lid, "antes": antes,
                       "depois": reais(novo_valor)})
                flash("Lançamento alterado. O valor anterior ficou guardado no "
                      "histórico do próprio lançamento.", "success")
                return redirect(url_for("caixa"))

            if acao == "excluir":
                lid = numero_digitado(request.form.get("lancamento_id"))
                motivo = (request.form.get("motivo") or "").strip()
                if not motivo:
                    flash("A exclusão precisa de motivo.", "danger")
                    return redirect(url_for("caixa"))
                l = q1("SELECT * FROM cx_lancamentos WHERE id=%s", (lid,))
                if not l or l["excluido"]:
                    flash("Lançamento não encontrado ou já excluído.", "danger")
                    return redirect(url_for("caixa"))
                if l["caixa_id"] != aberto["id"]:
                    flash("Só se exclui lançamento do caixa aberto. Em caixa fechado, "
                          "a correção é por estorno.", "danger")
                    return redirect(url_for("caixa"))
                if l["recibo_id"]:
                    flash("Este lançamento tem recibo emitido. Cancele o recibo antes — "
                          "o cliente tem uma via na mão.", "danger")
                    return redirect(url_for("caixa"))
                with db.transaction() as con:
                    banco(con).escrever(
                        """UPDATE cx_lancamentos SET excluido=1, motivo_exclusao=%s,
                           excluido_em=%s, excluido_por=%s WHERE id=%s""",
                        (motivo, db.now(), usuario_nome(), lid))
                audit("CAIXA_LANCAMENTO_EXCLUIDO", "CAIXA", aberto["id"],
                      {"lancamento": lid, "valor": l["valor"], "motivo": motivo})
                flash("Lançamento excluído. Sai das contas e some da lista, mas o "
                      "registro fica guardado com o motivo — caixa que perde linha "
                      "sem rastro não se explica em correição.", "success")
                return redirect(url_for("caixa"))

            if acao == "fechar":
                lanc = lancamentos_do_caixa(aberto["id"])
                res = resumo_caixa(lanc, aberto["saldo_inicial"])
                contado = centavos(request.form.get("valor_contado"))
                diferenca = contado - res["em_especie"]
                justificativa = (request.form.get("justificativa") or "").strip()
                if diferenca and not justificativa:
                    flash(f"Há diferença de R$ {reais(abs(diferenca))}. "
                          f"Explique antes de fechar.", "danger")
                    return redirect(url_for("caixa"))
                with db.transaction() as con:
                    # QUEM FECHOU, E NÃO SÓ QUANDO — a coluna existia desde
                    # sempre e ninguém a preenchia. Medido: `fechado_por` NULL
                    # em 2.755 de 2.755 caixas fechados.
                    #
                    #   Fechamento de caixa é ato de dinheiro, e a pergunta que
                    #   a correição faz é «quem fechou este dia». A auditoria
                    #   guardava o nome, mas quem lê o caixa não abre a
                    #   auditoria: lê o caixa.
                    banco(con).escrever(
                        """UPDATE cx_caixas SET situacao='FECHADO', valor_esperado=%s,
                           valor_contado=%s, diferenca=%s, justificativa=%s,
                           fechado_em=%s, fechado_por=%s WHERE id=%s""",
                        (reais(res["em_especie"]), reais(contado), reais(diferenca),
                         justificativa or None, db.now(), usuario_id(),
                         aberto["id"]))
                audit("CAIXA_FECHADO", "CAIXA", aberto["id"],
                      {"esperado": reais(res["em_especie"]), "contado": reais(contado),
                       "diferenca": reais(diferenca)})
                flash(f"Caixa fechado. Esperado R$ {reais(res['em_especie'])}, "
                      f"contado R$ {reais(contado)}, diferença R$ {reais(diferenca)}.",
                      "warning" if diferenca else "success")
                return redirect(url_for("caixa"))

        lanc = lancamentos_do_caixa(aberto["id"]) if aberto else []
        res = resumo_caixa(lanc, aberto["saldo_inicial"] if aberto else 0)
        anteriores = q("""SELECT * FROM cx_caixas WHERE operador_nome=%s
                          ORDER BY data DESC LIMIT 15""", (operador,))
        # O QUE ESPERA CONFERÊNCIA — e nunca o do próprio operador.
        #
        #   Quem atende fecha o próprio caixa e conta o próprio dinheiro; quem
        #   confere é outro. Mostrar aqui o caixa de quem está olhando faria a
        #   tela oferecer o que a rota recusa.
        #
        #   E a lista é dos **não conferidos**: caixa já conferido sai dela, ou
        #   ela cresce até ninguém olhar mais — a lição do alarme que soa
        #   sempre.
        a_conferir = q("""SELECT * FROM cx_caixas
                           WHERE situacao='FECHADO' AND conferido_em IS NULL
                             AND operador_nome <> %s
                           ORDER BY data DESC, id DESC LIMIT 30""", (operador,))
        return render_template("caixa.html", aberto=aberto, lancamentos=lanc,
                               resumo=res, anteriores=anteriores,
                               a_conferir=a_conferir, operador=operador,
                               FORMAS=FORMAS_PAGAMENTO, NATUREZAS=NATUREZAS,
                               reais=reais, hoje=date.today().isoformat())

    # -------------------------------------------------- depósito prévio

    @app.route("/caixa/depositos", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def caixa_depositos():
        """Dinheiro que entra antes do ato e vai sendo consumido.

        O saldo é sempre recalculado a partir do que entrou menos o que foi
        usado — nunca guardado como número solto que alguém edita. Assim ele
        não pode divergir do movimento que o sustenta.

        O TIPO DO SERVIÇO — a segunda metade do relato #50, «informações do
        tipo de serviço». A data do depósito foi a primeira, feita em 15/09.
        São DOIS campos, porque são duas perguntas: a **atribuição** («de que
        cartório é este dinheiro», o que se soma num relatório) e o **serviço**
        (qual item do catálogo da casa ele adianta, o que se confere contra o
        que foi cobrado).

        Os dois são OPCIONAIS, e isso é decisão do oficial em 17/09/2026:
        medido, **8 dos 14 depósitos não têm vínculo nenhum**, e o dinheiro
        deixado «para quando o título chegar» é legítimo. A lista declara
        quantos estão sem tipo em vez de recusar o que a casa sempre fez.

        E eles não se perguntam quando o vínculo já responde: o protocolo do
        balcão grava a própria atribuição, a prenotação é do Registro de
        Imóveis e o ato de livro é das Notas. Por isso as telas que criam
        depósito com vínculo não têm campo nenhum — só esta, onde o dinheiro
        costuma chegar solto.
        """
        operador = usuario_nome()

        if request.method == "POST":
            acao = request.form.get("acao")

            if acao == "novo":
                valor = centavos(request.form.get("valor"))
                depositante = (request.form.get("depositante") or "").strip()
                if valor <= 0 or not depositante:
                    flash("Informe o depositante e um valor maior que zero.", "danger")
                    return redirect(url_for("caixa_depositos"))
                aberto = caixa_aberto(operador)
                # RELATO #50: a data do depósito é a do PAPEL, e pode não ser
                # hoje — dinheiro deixado na sexta e registrado na segunda.
                #
                # Ela vale só para `cx_depositos.data`. A numeração e o
                # lançamento no caixa continuam de hoje, porque a gaveta conta
                # o dinheiro quando ele entra; lançar com a data do papel
                # mexeria no caixa de um dia já conferido, que é o defeito que
                # a conferência do caixa existe para impedir.
                informada = (request.form.get("data") or "").strip()
                try:
                    data_do_deposito = (date.fromisoformat(informada)
                                        if informada else None)
                except ValueError:
                    flash("A data do depósito não é uma data válida.",
                          "danger")
                    return redirect(url_for("caixa_depositos"))
                # O PROTOCOLO DO ORÇAMENTO (LD06; CN-MA art. 198, I e VI). O
                # orçamento de mais de um ato se monta no protocolo — o «mero
                # cálculo» é um protocolo —, e o depósito que aponta para ele
                # guarda os itens com os fundos. Número que não existe é
                # recusado antes de gravar: depósito apontado para o nada é a
                # coluna I vazia que o livro acusa.
                numero_protocolo = (request.form.get("protocolo") or "").strip()
                protocolo_id = None
                if numero_protocolo:
                    achado = q1("""SELECT id FROM cx_protocolos WHERE numero=%s
                                   ORDER BY id LIMIT 1""", (numero_protocolo,))
                    if not achado:
                        flash(f"O protocolo {numero_protocolo} não existe.", "danger")
                        return redirect(url_for("caixa_depositos"))
                    protocolo_id = int(achado["id"])
                # A CRIAÇÃO DO DEPÓSITO VIVE EM `caixa_depositos.py`, e não aqui.
                #
                #   Ela passou a ser chamada também pela tela do título do
                #   Registro de Imóveis — é lá que o apresentante deixa o
                #   adiantamento. Copiar as trinta linhas para o `ri_web` seria
                #   a mesma armadilha que produziu o defeito da função do
                #   usuário: a mesma regra em dois arquivos, e um deles
                #   divergindo em silêncio.
                with db.transaction() as con:
                    try:
                        feito = DEP.criar(
                            con, valor_centavos=valor, depositante=depositante,
                            agora=db.now(),
                            documento=request.form.get("depositante_documento"),
                            observacao=request.form.get("observacao"),
                            forma_pagamento=request.form.get("forma_pagamento"),
                            caixa_id=aberto["id"] if aberto else None,
                            protocolo_id=protocolo_id,
                            # O TIPO DO SERVIÇO — relato #50, segunda metade.
                            # Opcional, e o que vier é conferido lá dentro: uma
                            # atribuição fora do vocabulário ou um serviço que
                            # não está no catálogo viram uma linha que nenhum
                            # filtro acha depois, que é justamente o que o
                            # relato pediu para poder achar.
                            atribuicao=request.form.get("atribuicao"),
                            servico_codigo=(request.form.get("servico_codigo")
                                            or None),
                            data_do_deposito=data_do_deposito)
                    except ValueError as erro:
                        flash(str(erro), "danger")
                        return redirect(url_for("caixa_depositos"))
                audit("DEPOSITO_PREVIO_CRIADO", "DEPOSITO", feito["id"],
                      {"numero": feito["numero"], "depositante": depositante,
                       "valor": feito["valor"], "data": feito["data"],
                       "atribuicao": feito["atribuicao"],
                       "servico": feito["servico_codigo"]})
                # A data informada aparece na frase: quem registra o papel de
                # sexta na segunda precisa ver que o sistema entendeu, e não
                # que gravou a data de hoje.
                quando = (f" com a data de {feito['data'][8:10]}/{feito['data'][5:7]}"
                          f"/{feito['data'][:4]}"
                          if data_do_deposito
                          and data_do_deposito != date.today() else "")
                # E o tipo sai na frase pelo mesmo motivo: quem escolheu precisa
                # ver que foi entendido, e não descobrir na lista depois.
                de_que = (f" — {DEP.ATRIBUICOES[feito['atribuicao']]}"
                          if feito["atribuicao"] else "")
                orcamento = feito.get("orcamento")
                flash(f"Depósito {feito['numero']} — R$ {feito['valor']} registrado"
                      f"{quando}{de_que}"
                      + (" e lançado no caixa." if feito["lancado_no_caixa"]
                         else ". Abra o caixa para que ele entre no movimento do dia.")
                      + (f" Orçamento de R$ {orcamento['soma']['total']} guardado, "
                         f"pelos valores de {orcamento['de_onde']}."
                         if orcamento else ""),
                      "success")
                # SEM ORÇAMENTO O DEPÓSITO ENTRA — o oficial decidiu em
                # 17/09/2026 que o tipo é opcional —, mas a tela diz o que o
                # livro vai cobrar (art. 198, VI) e o recibo não vai trazer
                # (art. 197).
                if not orcamento:
                    flash("Este depósito ficou sem orçamento: informe o serviço ou o "
                          "protocolo do orçamento, senão o recibo sai sem a "
                          "discriminação dos valores previstos (CN-MA art. 197) e o "
                          "livro aponta a falta (art. 198, VI).", "warning")
                # A DIVERGÊNCIA SAI DEPOIS, e em aviso: o depósito foi
                # registrado — o vínculo manda —, mas alguém precisa conferir
                # qual dos dois está certo. Some-la seria gravar dinheiro
                # classificado de um jeito que a tela não mostrou.
                if feito.get("aviso"):
                    flash(feito["aviso"], "warning")
                return redirect(url_for("caixa_depositos"))

            if acao == "gravar_tipos":
                # RELATO #50: preencher o tipo dos depósitos ANTIGOS que têm
                # vínculo. É fato lido do protocolo/prenotação, não palpite —
                # decisão do oficial em 17/09/2026 —, e por isso o botão não
                # pergunta nada: o que não tem vínculo fica sem tipo, e a lista
                # declara isso em vez de inventar um.
                #
                # Só ADMIN e MANAGER: muda a classificação de dinheiro que já
                # entrou, e é o tipo de coisa que se faz uma vez, com o número
                # do que mudou na tela.
                if usuario_papel() not in ("ADMIN", "MANAGER"):
                    flash("Preencher o tipo dos depósitos antigos é do oficial "
                          "ou do gerente.", "danger")
                    return redirect(url_for("caixa_depositos"))
                with db.transaction() as con:
                    feito = DEP.gravar_tipos_do_vinculo(con)
                if feito["gravados"]:
                    audit("DEPOSITO_PREVIO_TIPO_DO_VINCULO", "DEPOSITO", 0, feito)
                flash(f"Tipo preenchido pelo vínculo em {feito['gravados']} "
                      f"depósito(s)"
                      + (f", {feito['com_servico']} também com o serviço do "
                         f"protocolo" if feito["com_servico"] else "")
                      + f". {feito['sem_tipo']} continuam sem tipo — o vínculo "
                        f"não os declara, e é um a um.",
                      "success" if feito["gravados"] else "warning")
                return redirect(url_for("caixa_depositos"))

            if acao == "usar":
                did = numero_digitado(request.form.get("deposito_id"))
                usar = centavos(request.form.get("valor_usar"))
                numero = (request.form.get("protocolo") or "").strip()
                aberto = caixa_aberto(operador)
                with db.transaction() as con:
                    bd = banco(con)
                    bd._escrita()
                    prot = bd.um("""SELECT id FROM cx_protocolos WHERE numero=%s
                                    ORDER BY id LIMIT 1""",
                                 (numero,)) if numero else None
                    if numero and not prot:
                        flash(f"O protocolo {numero} não existe.", "danger")
                        return redirect(url_for("caixa_depositos"))
                    # OS ITENS A PAGAR DO PROTOCOLO SE PRENDEM ANTES DO
                    # DEPÓSITO (LD06), na ordem do selo (item → depósito): o
                    # «usar» passou a quitá-los, e o selo do mesmo protocolo
                    # prende nessa ordem.
                    a_pagar = DEP.prender_itens_a_pagar(bd, prot["id"]) if prot else []
                    # O SALDO SE LÊ AQUI DENTRO, COM A LINHA PRESA (FOR
                    # UPDATE): lido antes da transação, dois cliques no mesmo
                    # depósito gastavam o mesmo saldo duas vezes.
                    d = bd.um("SELECT * FROM cx_depositos WHERE id=%s FOR UPDATE",
                              (did,))
                    if not d or d["encerrado"]:
                        flash("Depósito não encontrado ou já encerrado.", "danger")
                        return redirect(url_for("caixa_depositos"))
                    saldo = centavos(d["saldo"])
                    if usar <= 0 or usar > saldo:
                        flash(f"O depósito tem saldo de R$ {reais(saldo)}. "
                              f"Não dá para usar R$ {reais(usar)}.", "danger")
                        return redirect(url_for("caixa_depositos"))
                    # «USAR» NO PROTOCOLO QUITA O ITEM (LD06; CN-MA art. 202).
                    # Baixava o saldo e deixava o item a pagar: a trava do selo
                    # pedia o pagamento de novo e o caixa o cobrava em dinheiro.
                    # Agora o valor quita os itens inteiros que ele cobre, pelo
                    # mesmo débito do quadro «Selo e caixa».
                    quitados = DEP.quitar_itens_com_o_deposito(
                        bd, int(d["id"]), a_pagar, usar, agora=db.now(),
                        quem=operador)
                    pelos_itens = sum(int(f["valor_centavos"]) for f in quitados)
                    novo = saldo - usar
                    bd.escrever(
                        """UPDATE cx_depositos SET saldo=%s, encerrado=%s,
                           protocolo_id=COALESCE(%s, protocolo_id), atualizado_em=%s
                           WHERE id=%s""",
                        (reais(novo), 1 if novo == 0 else 0,
                         prot["id"] if prot else None, db.now(), did))
                    if aberto:
                        # Consumir depósito NÃO é entrada nova de dinheiro: o
                        # valor já entrou quando foi depositado. Lança-se o uso
                        # para deixar rastro, sem mexer no saldo em espécie.
                        bd.escrever(
                            """INSERT INTO cx_lancamentos
                               (caixa_id, protocolo_id, data, hora, natureza,
                                sentido, forma_pagamento, descricao, pagador,
                                valor, criado_em)
                               VALUES (%s,%s,%s,%s, 'RECEBIMENTO','ENTRADA',
                                       'DEPOSITO_PREVIO', %s,%s,%s,%s)""",
                            (aberto["id"], prot["id"] if prot else None,
                             date.today().isoformat(), datetime.now().strftime("%H:%M"),
                             f"Uso do depósito prévio nº {did}"
                             + (f" no protocolo {numero}" if numero else ""),
                             d["depositante"], reais(usar), db.now()))
                # O RASTRO DE CADA PARTE NUM LUGAR SÓ. O que quitou item já
                # está em `cx_deposito_usos`, com o item — é de lá que o livro
                # lê a conversão com o ato (art. 198, IV); só o resto vai como
                # uso solto. Escrito nos dois, o livro contaria o mesmo
                # dinheiro duas vezes.
                resto = usar - pelos_itens
                if quitados:
                    audit("DEPOSITO_PREVIO_ITENS_QUITADOS", "DEPOSITO", did,
                          {"protocolo": numero, "valor": reais(pelos_itens),
                           "itens": [{"item": int(f["item"]["id"]),
                                      "codigo": f["item"]["codigo_ato"],
                                      "valor": reais(f["valor_centavos"])}
                                     for f in quitados]})
                if resto:
                    audit("DEPOSITO_PREVIO_USADO", "DEPOSITO", did,
                          {"usado": reais(resto), "saldo": reais(novo),
                           "protocolo": numero})
                quais = ", ".join(str(f["item"]["codigo_ato"] or f["item"]["id"])
                                  for f in quitados)
                flash(f"R$ {reais(usar)} consumidos. Saldo do depósito: R$ {reais(novo)}."
                      + (f" Quitado(s) com o depósito no protocolo {numero}: {quais}"
                         f" — R$ {reais(pelos_itens)}." if quitados else "")
                      + (" Depósito encerrado." if novo == 0 else ""), "success")
                # O ITEM QUE O VALOR NÃO COBRE CONTINUA A PAGAR, e a tela diz:
                # é o item que o balcão cobraria de novo sem saber que parte do
                # dinheiro do cliente já foi usada neste protocolo.
                if a_pagar and len(quitados) < len(a_pagar):
                    flash(f"{len(a_pagar) - len(quitados)} item(ns) do protocolo "
                          f"{numero} continua(m) a pagar: o valor usado não cobre "
                          f"o preço inteiro dele(s).", "warning")
                return redirect(url_for("caixa_depositos"))

            if acao == "devolver":
                did = numero_digitado(request.form.get("deposito_id"))
                motivo = (request.form.get("motivo") or "").strip()
                aberto = caixa_aberto(operador)
                with db.transaction() as con:
                    bd = banco(con)
                    # FOR UPDATE, como no `usar`: o que se devolve é o saldo
                    # de agora, e não o de antes de outro clique gastar parte.
                    bd._escrita()
                    d = bd.um("SELECT * FROM cx_depositos WHERE id=%s FOR UPDATE",
                              (did,))
                    if not d or d["encerrado"]:
                        flash("Depósito não encontrado ou já encerrado.", "danger")
                        return redirect(url_for("caixa_depositos"))
                    saldo = centavos(d["saldo"])
                    if not aberto:
                        flash("Abra o caixa para devolver: o dinheiro sai da gaveta.", "danger")
                        return redirect(url_for("caixa_depositos"))
                    bd.escrever(
                        """UPDATE cx_depositos SET saldo='0,00', encerrado=1,
                           observacao=COALESCE(observacao,'') || %s, atualizado_em=%s
                           WHERE id=%s""",
                        (f" | Devolvido em {date.today().isoformat()}: {motivo}",
                         db.now(), did))
                    bd.escrever(
                        """INSERT INTO cx_lancamentos
                           (caixa_id, data, hora, natureza, sentido, descricao,
                            pagador, valor, criado_em)
                           VALUES (%s,%s,%s, 'DEVOLUCAO','SAIDA', %s,%s,%s,%s)""",
                        (aberto["id"], date.today().isoformat(),
                         datetime.now().strftime("%H:%M"),
                         f"Devolução do depósito prévio nº {did}: {motivo}",
                         d["depositante"], reais(saldo), db.now()))
                audit("DEPOSITO_PREVIO_DEVOLVIDO", "DEPOSITO", did,
                      {"valor": reais(saldo), "motivo": motivo})
                flash(f"R$ {reais(saldo)} devolvidos ao depositante.", "success")
                return redirect(url_for("caixa_depositos"))

        busca = (request.args.get("busca") or "").strip()
        mostrar = (request.args.get("mostrar") or "ABERTOS").upper()
        # O FILTRO POR TIPO — a segunda metade do relato #50, e a razão de os
        # dois campos existirem: «régua que erra o endereço acusa quem está
        # certo», e aqui é a régua que não somava. O `SEM` é o que faz a lista
        # prestar contas: sem ele, os 8 depósitos sem tipo sumiriam de qualquer
        # filtro e ninguém saberia que faltam.
        filtro = (request.args.get("atribuicao") or "").strip().upper()
        if filtro and filtro != "SEM" and filtro not in DEP.ATRIBUICOES:
            filtro = ""
        # As colunas vão qualificadas com `d.` desde aqui: a consulta agora tem
        # quatro tabelas, e `encerrado` sem dono é ambíguo para o SQLite no dia
        # em que outra delas ganhar uma coluna de mesmo nome.
        onde, params = ["1=1"], []
        if mostrar == "ABERTOS":
            onde.append("d.encerrado=0")
        if busca:
            onde.append("(d.depositante ILIKE %s OR d.depositante_documento ILIKE %s)")
            params += [f"%{busca}%", f"%{busca}%"]
        if filtro == "SEM":
            onde.append("d.atribuicao IS NULL")
        elif filtro:
            onde.append("d.atribuicao=%s")
            params.append(filtro)

        # O ESPELHO: cada depósito diz a que título ou ato pertence, e leva até
        # ele. Nascendo em três telas diferentes, sem isto o dinheiro ficaria no
        # caixa sem dizer a que veio — e quem confere no fim do dia não teria
        # como saber.
        rows = [dict(r) for r in
                q(f"""{DEP.SQL_COM_VINCULO}
                      WHERE {' AND '.join(onde)}
                      ORDER BY d.encerrado, d.data DESC, d.id LIMIT 300""", params)]
        # A BUSCA DO SERVIÇO É DO SERVIDOR, e não do navegador. A do protocolo
        # (relato #53) é instantânea porque o formulário dela não recarrega ao
        # digitar; aqui o formulário **é** o cadastro do depósito, e uma busca
        # que sequestrasse o Enter faria o balcão registrar depósito sem querer.
        # Então quem não lembra o código escreve uma palavra, manda procurar, e
        # escolhe da lista — que é a mesma promessa sem depender de JavaScript.
        termo_servico = (request.args.get("servico_termo") or "").strip()
        servico_escolhido = (request.args.get("servico_codigo") or "").strip()
        achados_servico = []
        # UMA CONEXÃO DE LEITURA PARA A TELA INTEIRA — abrir uma por depósito
        # faria trezentas conexões para desenhar uma lista.
        with db.connect() as con_leitura:
            if termo_servico:
                achados_servico = DEP.buscar_servicos(con_leitura, termo_servico)
            # A SUGESTÃO DO FORMULÁRIO é a mesma régua do cadastro: com o
            # serviço já escolhido, o grupo dele pode declarar a atribuição — e
            # é isso que a tela mostra antes de a pessoa gravar. Um segundo
            # caminho para responder a mesma pergunta seria a segunda régua.
            sugestao = DEP.sugerir_tipo(
                con_leitura, servico_codigo=(servico_escolhido or None))
            for d in rows:
                d["vinculo"] = DEP.vinculo(d)
                # O TIPO DE CADA LINHA. **O que está gravado manda**; o que não
                # estiver é lido do vínculo e mostrado com a procedência — assim
                # quem confere sabe se aquilo alguém escolheu ou o sistema
                # deduziu. A leitura só toca o banco nos depósitos com vínculo e
                # sem tipo gravado, que são os seis antigos até o botão da tela
                # ser apertado uma vez.
                d["tipo"] = DEP.tipo_do_deposito(con_leitura, d)
                # O ORÇAMENTO CONGELADO (LD06): o total à vista na lista, e o
                # «sem orçamento» do depósito que o livro vai cobrar.
                orcamento = DEP.orcamento_gravado(d)
                d["orcamento_total"] = (orcamento["soma"].get("total")
                                        if orcamento else None)
        total = q1("""SELECT COUNT(*) n,
                      COALESCE(SUM(COALESCE(substring(
                          replace(replace(saldo,'.',''),',','.')
                          FROM '^[+-]{0,1}[0-9]*[.]{0,1}[0-9]+')::float8, 0)),0) AS s
                      FROM cx_depositos WHERE encerrado=0""")
        # QUANTOS ESTÃO SEM TIPO — é a lista que se declara, e não a que se
        # esconde: são os que o vínculo não respondeu, e o número fica à vista
        # ao lado do botão que preenche os que têm vínculo.
        sem_tipo = q1("""SELECT COUNT(*) n FROM cx_depositos
                          WHERE atribuicao IS NULL""")["n"]
        por_atribuicao = [dict(r) for r in q(
            """SELECT atribuicao, COUNT(*) n FROM cx_depositos
                WHERE atribuicao IS NOT NULL GROUP BY atribuicao
                ORDER BY n DESC, atribuicao""")]
        return render_template("caixa_depositos.html", rows=rows, busca=busca,
                               mostrar=mostrar, total=total, FORMAS=FORMAS_PAGAMENTO,
                               ATRIBUICOES=DEP.ATRIBUICOES, filtro=filtro,
                               sem_tipo=sem_tipo, por_atribuicao=por_atribuicao,
                               # Quem pode preencher o tipo dos antigos vê o
                               # botão; a rota recusa de novo, porque o menu não
                               # oferece o que o operador não pode fazer e é a
                               # rota que faz.
                               pode_gravar_tipos=usuario_papel() in ("ADMIN", "MANAGER"),
                               # A busca do serviço: o que se procurou, o que se
                               # achou e o código já escolhido — que volta
                               # preenchido no campo, para o caminho sem
                               # JavaScript terminar em um clique.
                               termo_servico=termo_servico,
                               achados_servico=achados_servico,
                               servico_escolhido=servico_escolhido,
                               sugestao=sugestao,
                               # A data de hoje abre o campo da data do depósito:
                               # quem registra o papel de hoje não digita nada.
                               hoje=date.today().isoformat())

    # ----------------------------------------------------------- recibos

    @app.route("/caixa/recibo/<int:lancamento_id>", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def caixa_recibo(lancamento_id):
        """Emite o recibo de um lançamento. Numeração própria por exercício."""
        l = q1("""SELECT l.*, p.numero protocolo_numero, p.interessado,
                         p.interessado_documento, p.telefone, p.tipo tipo_protocolo
                  FROM cx_lancamentos l
                  LEFT JOIN cx_protocolos p ON p.id = l.protocolo_id
                  WHERE l.id=%s""", (lancamento_id,))
        if not l:
            abort(404)

        ano = date.today().year
        # SÓ OS ITENS QUE ESTE LANÇAMENTO PAGOU (LT06, 20/10/2026). A lista era
        # a do protocolo inteiro, pagos ou não, e os fundos somavam todos: o
        # recibo dizia «R$ 6,21» e discriminava R$ 51,57. Recibo é prova de
        # pagamento — a frase de `caixa_recibo_do_protocolo` —, e o do
        # atendimento inteiro continua sendo aquele. Lançamento que não quitou
        # item (o do ato, o avulso) fica sem lista, e os fundos saem dele.
        itens = [dict(r) for r in
                 q("""SELECT * FROM cx_protocolo_atos
                       WHERE protocolo_id=%s AND lancamento_id=%s ORDER BY id""",
                   (l["protocolo_id"], lancamento_id))] if l["protocolo_id"] else []
        fundos = {f: reais(sum(centavos(i.get(f)) for i in itens) or centavos(l[f]))
                  for f in ("emolumentos", "ferc", "fadep", "femp", "ferrfis")}
        # O RECIBO DO DEPÓSITO PRÉVIO TRAZ O ORÇAMENTO (LD06). «A escrituração
        # do Livro de Controle de Depósito Prévio não exime o delegatário da
        # obrigação de fornecer ao usuário o respectivo recibo, que deverá
        # incluir a discriminação orçamentária de todos os valores previstos
        # para o serviço requerido» (CN-MA art. 197). A discriminação é a do
        # orçamento congelado no depósito, com os fundos, e a observação diz
        # com todas as letras que é ORÇAMENTO: o dinheiro é adiantamento, e só
        # vira emolumento quando o ato for praticado (art. 202).
        observacao = None  # recibo de pagamento: sem aviso de orçamento
        deposito = (q1("""SELECT numero, orcamento FROM cx_depositos
                           WHERE lancamento_id=%s ORDER BY id LIMIT 1""",
                       (lancamento_id,))
                    if l["natureza"] == "DEPOSITO_PREVIO" else None)
        orcamento = DEP.orcamento_gravado(deposito) if deposito else None
        if deposito:
            observacao = (f"Depósito prévio nº {deposito['numero']}: adiantamento "
                          f"para a prática futura do ato (CN-MA art. 195).")
        if orcamento:
            itens = list(orcamento["itens"])
            fundos = {f: orcamento["soma"].get(f) or "0,00"
                      for f in ("emolumentos", "ferc", "fadep", "femp", "ferrfis")}
            observacao += (" A discriminação acima é o ORÇAMENTO de todos os valores "
                           "previstos para o serviço requerido (CN-MA art. 197), no "
                           f"total de R$ {orcamento['soma'].get('total')}, e não "
                           "recibo de emolumentos de ato praticado: o depósito se "
                           "converte em emolumentos quando o ato for praticado "
                           "(art. 202), e o que sobrar é devolvido.")
        pagador = (l["pagador"] or l["interessado"] or "").strip() or "Não informado"

        with db.transaction() as con:
            bd = banco(con)
            bd.travar("cx_recibos.numero")
            # A MARCA DO RECIBO SE CONFERE DEPOIS DA TRAVA: lida antes, dois
            # cliques passavam juntos e o mesmo lançamento saía em dois recibos.
            marca = bd.um("SELECT recibo_id FROM cx_lancamentos WHERE id=%s FOR UPDATE",
                          (lancamento_id,))
            if marca and marca["recibo_id"]:
                flash("Este lançamento já tem recibo.", "warning")
                return redirect(url_for("caixa"))
            ultimo = bd.valor("SELECT MAX(numero) AS n FROM cx_recibos WHERE ano=%s",
                              (ano,))
            numero = int((ultimo or 0)) + 1
            r = {"numero": numero, "ano": ano, "pagador": pagador,
                 "pagador_documento": l["pagador_documento"],
                 "protocolo_numero": l["protocolo_numero"],
                 "valor_total": l["valor"], "valor_extenso": por_extenso(centavos(l["valor"])),
                 "forma_pagamento": FORMAS_PAGAMENTO.get(l["forma_pagamento"] or "", ""),
                 "observacao": observacao}
            # O contato do cliente fica gravado inteiro no recibo (e prova de
            # quem pagou); a mascara so acontece na hora de imprimir.
            corpo = json.dumps(
                {"itens": itens, "fundos": fundos,
                 "documento": l["pagador_documento"] or l["interessado_documento"],
                 "telefone": l["telefone"],
                 "lancamento": f"{l['numero']}/{l['ano']}" if l["numero"] else None,
                 **({"orcamento": True} if orcamento else {})},
                ensure_ascii=False)
            h = hash_recibo(numero, ano, pagador, l["valor"],
                            date.today().isoformat(), corpo)
            recibo_id = int(bd.escrever(
                """INSERT INTO cx_recibos
                   (numero, ano, data_emissao, protocolo_id, protocolo_numero,
                    pagador, pagador_documento, valor_total, valor_extenso,
                    forma_pagamento, discriminacao, corpo, observacao,
                    hash_recibo, criado_em)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                (numero, ano, date.today().isoformat(), l["protocolo_id"],
                 l["protocolo_numero"], pagador,
                 l["pagador_documento"] or l["interessado_documento"],
                 l["valor"], r["valor_extenso"], r["forma_pagamento"],
                 corpo, corpo, r["observacao"], h, db.now()))[0]["id"])
            bd.escrever("UPDATE cx_lancamentos SET recibo_id=%s WHERE id=%s",
                        (recibo_id, lancamento_id))
            # O CÓDIGO DE ACOMPANHAMENTO NASCE AQUI, no POST que emite o
            # recibo (portal do cliente, 26/10/2026): a impressão logo abaixo
            # é um GET, e GET não abre transação de escrita. Lançamento sem
            # protocolo não tem o que acompanhar; protesto não ganha código.
            if l["protocolo_id"]:
                ACOMP.codigo_para_o_papel(con, l["protocolo_id"])

        audit("RECIBO_EMITIDO", "RECIBO", recibo_id,
              {"numero": numero, "ano": ano, "valor": l["valor"]})
        return redirect(url_for("caixa_recibo_odt", recibo_id=recibo_id))

    @app.route("/caixa/protocolos/<int:protocolo_id>/recibo", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def caixa_recibo_do_protocolo(protocolo_id):
        """Um recibo só, do atendimento inteiro. ESCREVE.

        A DECISÃO DO OFICIAL, EM 27/08/2026: quando o cliente pede três cópias
        autenticadas e uma certidão na mesma ida ao balcão, ele espera **um
        papel**, e não quatro.

        O RECIBO É DO QUE JÁ ENTROU NO CAIXA, e não do que foi orçado. Item
        que ainda não foi quitado não entra: recibo é prova de pagamento, e
        dizer que se recebeu o que não se recebeu é o tipo de papel que volta.

        A FORMA É A DO RECIBO QUE JÁ EXISTE — numeração por exercício, teor
        congelado e hash. Duas formas de recibo na mesma casa seria uma a mais
        para conferir.
        """
        p = q1("SELECT * FROM cx_protocolos WHERE id=%s", (protocolo_id,))
        if not p:
            abort(404)
        itens = [i for i in q(
            """SELECT a.*, l.forma_pagamento, l.pagador, l.pagador_documento,
                      l.recibo_id
                 FROM cx_protocolo_atos a
                 JOIN cx_lancamentos l ON l.id = a.lancamento_id
                WHERE a.protocolo_id=%s AND COALESCE(l.excluido, 0) = 0
                ORDER BY a.id""", (protocolo_id,))]
        if not itens:
            flash("Nenhum serviço deste protocolo entrou no caixa ainda. "
                  "Recibo é prova de pagamento — quite os itens primeiro.",
                  "warning")
            return redirect(url_for("caixa_protocolo",
                                    protocolo_id=protocolo_id))

        ano = date.today().year
        total = sum(centavos(i["valor_total"]) for i in itens)
        fundos = {f: reais(sum(centavos(i[f]) for i in itens))
                  for f in ("emolumentos", "ferc", "fadep", "femp", "ferrfis")}
        pagador = ((itens[0]["pagador"] or p["interessado"] or "").strip()
                   or "Não informado")
        documento = (itens[0]["pagador_documento"]
                     or p["interessado_documento"])
        forma = FORMAS_PAGAMENTO.get(itens[0]["forma_pagamento"] or "", "")

        with db.transaction() as con:
            bd = banco(con)
            bd.travar("cx_recibos.numero")
            # A MARCA DO RECIBO SE CONFERE DEPOIS DA TRAVA, como no recibo do
            # lançamento: lida antes, dois cliques passavam juntos e o mesmo
            # dinheiro saía em dois recibos.
            com_recibo = {r["id"] for r in bd.ler(
                """SELECT id, recibo_id FROM cx_lancamentos
                    WHERE id = ANY(%s) ORDER BY id FOR UPDATE""",
                ([int(i["lancamento_id"]) for i in itens],)) if r["recibo_id"]}
            ja = [i for i in itens if i["lancamento_id"] in com_recibo]
            if ja:
                flash(f"{len(ja)} serviço(s) deste protocolo já estão num recibo. "
                      f"Dois recibos do mesmo dinheiro é o que ninguém consegue "
                      f"conferir depois.", "danger")
                return redirect(url_for("caixa_protocolo",
                                        protocolo_id=protocolo_id))
            ultimo = bd.valor(
                "SELECT MAX(numero) AS n FROM cx_recibos WHERE ano=%s",
                (ano,))
            numero = int(ultimo or 0) + 1
            extenso = por_extenso(total)
            corpo = json.dumps(
                {"itens": [dict(i) for i in itens], "fundos": fundos,
                 "documento": documento, "telefone": p["telefone"],
                 "protocolo": p["numero"], "de_protocolo": True},
                ensure_ascii=False, default=str)
            h = hash_recibo(numero, ano, pagador, reais(total),
                            date.today().isoformat(), corpo)
            recibo_id = int(bd.escrever(
                """INSERT INTO cx_recibos
                   (numero, ano, data_emissao, protocolo_id, protocolo_numero,
                    pagador, pagador_documento, valor_total, valor_extenso,
                    forma_pagamento, discriminacao, corpo, observacao,
                    hash_recibo, criado_em)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                (numero, ano, date.today().isoformat(), protocolo_id,
                 p["numero"], pagador, documento, reais(total), extenso, forma,
                 corpo, corpo,
                 None,  # recibo quitado: sem aviso de mero cálculo
                 h, db.now()))[0]["id"])
            # TODOS OS LANÇAMENTOS DO RECIBO FICAM MARCADOS. Sem isso, o mesmo
            # dinheiro sairia num segundo recibo — e dois recibos do mesmo
            # pagamento é o que ninguém consegue conferir depois.
            for i in itens:
                bd.escrever("UPDATE cx_lancamentos SET recibo_id=%s WHERE id=%s",
                            (recibo_id, i["lancamento_id"]))
            # O código de acompanhamento nasce no POST, como no recibo do
            # lançamento — a impressão é o GET seguinte.
            ACOMP.codigo_para_o_papel(con, protocolo_id)

        audit("RECIBO_DO_PROTOCOLO", "RECIBO", recibo_id,
              {"numero": numero, "ano": ano, "protocolo": p["numero"],
               "itens": len(itens), "valor": reais(total)})
        return redirect(url_for("caixa_recibo_odt", recibo_id=recibo_id))

    @app.route("/caixa/recibo/<int:recibo_id>/odt")
    @roles_required("ADMIN", "MANAGER", "USER")
    def caixa_recibo_odt(recibo_id):
        r = q1("SELECT * FROM cx_recibos WHERE id=%s", (recibo_id,))
        if not r:
            abort(404)
        s = db.get_settings()
        with db.connect() as _c:
            # O CÓDIGO DE ACOMPANHAMENTO, SÓ LIDO: a impressão é GET, e o
            # código nasceu no POST que emitiu o recibo. Recibo de antes do
            # portal sai sem ele — o botão da ficha do protocolo o cria.
            acompanhamento = ACOMP.codigo_para_o_papel(
                _c, r["protocolo_id"], endereco_do_portal=s.get(PORTAL.CHAVE_URL),
                criar=False)
            html = html_do_recibo(
                _c, r, settings=s, emitido_por=usuario_nome(),
                funcao=usuario_funcao(), data_extenso=fmt_date(r["data_emissao"]),
                agora=datetime.now().strftime("%d/%m/%Y %H:%M"),
                acompanhamento=acompanhamento)
        arquivo = gerar_odt(html_para_odf(html), titulo=f"Recibo {r['numero']}/{r['ano']}")
        audit("RECIBO_IMPRESSO", "RECIBO", recibo_id, {"numero": r["numero"]})
        return Response(arquivo, mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="recibo-{r["numero"]}-{r["ano"]}.odt"'})

    @app.route("/caixa/recibos")
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    def caixa_recibos():
        busca = (request.args.get("busca") or "").strip()
        onde, params = ["1=1"], []
        if busca:
            onde.append("(pagador ILIKE %s OR protocolo_numero ILIKE %s OR numero::text ILIKE %s)")
            params += [f"%{busca}%", f"%{busca}%", f"%{busca}%"]
        rows = q(f"""SELECT * FROM cx_recibos WHERE {' AND '.join(onde)}
                     ORDER BY ano DESC, numero DESC LIMIT 200""", params)
        return render_template("caixa_recibos.html", rows=rows, busca=busca)

    # -------------------------------------------------------- protocolos

    @app.route("/caixa/protocolos", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    # O AUDITOR ve a tela; o que ela GRAVA (POST) exige papel que pratica ato.
    @roles_required("ADMIN", "MANAGER", "USER", metodos=("POST",))
    def caixa_protocolos():
        """Protocolo geral. Por padrão mostra o que continua em aberto."""
        if request.method == "POST" and request.form.get("acao") == "novo":
            interessado = (request.form.get("interessado") or "").strip()
            if not interessado:
                flash("Informe o interessado.", "danger")
                return redirect(url_for("caixa_protocolos"))
            # TELEFONE OU E-MAIL, PELO MENOS UM — ordem do oficial, 10/10/2026.
            # Só ao ABRIR: a edição da ficha antiga não trava por isso.
            try:
                CONTATO.exigir(request.form.get("telefone"), request.form.get("email"))
            except CONTATO.ContatoError as e:
                flash(str(e), "danger")
                return redirect(url_for("caixa_protocolos"))
            hoje = date.today()
            # Numeracao no formato do E-Oficio: AAAA.MM.sequencial do mes.
            # Manter o mesmo padrao evita ter dois jeitos de citar protocolo
            # na mesma serventia.
            prefixo = f"{hoje.year}.{hoje.month:02d}."
            try:
                with db.transaction() as con:
                    bd = banco(con)
                    bd.travar("cx_protocolos.numero")
                    # O sufixo e' lido pelo prefixo numerico, como o CAST do
                    # SQLite lia (sem numero nenhum, conta como zero).
                    ultimo = bd.um(
                        """SELECT numero FROM cx_protocolos
                            WHERE starts_with(numero, %(prefixo)s)
                            ORDER BY COALESCE(substring(substring(numero FROM %(inicio)s)
                                                        FROM '^[0-9]+')::bigint, 0) DESC
                            LIMIT 1""",
                        {"prefixo": prefixo, "inicio": len(prefixo) + 1})
                    seq = (int(ultimo["numero"].split(".")[-1]) + 1) if ultimo else 1
                    numero = f"{prefixo}{seq}"
                    novo = bd.escrever(
                        """INSERT INTO cx_protocolos
                           (numero, data_abertura, hora, atribuicao, interessado,
                            interessado_documento, telefone, email, assunto,
                            observacao, previsao_entrega, tipo,
                            documento_tipo, documento_numero, documento_descricao,
                            situacao, criado_em)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, 'ABERTO', %s)
                           RETURNING id""",
                        (numero, hoje.isoformat(), datetime.now().strftime("%H:%M"),
                         request.form.get("atribuicao") or "OUTROS", interessado,
                         (request.form.get("interessado_documento") or "").strip() or None,
                         (request.form.get("telefone") or "").strip() or None,
                         (request.form.get("email") or "").strip() or None,
                         (request.form.get("assunto") or "").strip() or None,
                         (request.form.get("observacao") or "").strip() or None,
                         (request.form.get("previsao_entrega") or "").strip() or None,
                         "ORCAMENTO" if request.form.get("tipo") == "ORCAMENTO"
                         else "SERVICO",
                         (request.form.get("documento_tipo") or "").strip() or None,
                         (request.form.get("documento_numero") or "").strip() or None,
                         (request.form.get("documento_descricao") or "").strip() or None,
                         db.now()))
                    pid = int(novo[0]["id"])
                    # Ponte com a prenotacao do RI: so quando o balcao escolheu.
                    # Sem escolha, a coluna fica vazia — lavrar nao adivinha.
                    ri_pid = (request.form.get("ri_protocolo_id") or "").strip()
                    atrib = (request.form.get("atribuicao") or "").strip().upper()
                    ligacao = None
                    if atrib == "RI" and ri_pid.isdigit():
                        # Número que não é de prenotação nenhuma («²», dígitos
                        # demais) é o mesmo «não achei» do número que não existe.
                        ri_numero = numero_digitado(ri_pid)
                        if ri_numero is None:
                            raise CXP.ProtocoloError(
                                f"Não achei a prenotação {ri_pid[:20]}. Confira o "
                                f"número no Livro 1 antes de vincular.")
                        ligacao = CXP.vincular_ri(con, pid, ri_numero)
            except CXP.ProtocoloError as e:
                flash(str(e), "danger")
                return redirect(url_for("caixa_protocolos"))
            audit("PROTOCOLO_ABERTO", "PROTOCOLO", pid,
                  {"numero": numero, "interessado": interessado,
                   "ri_protocolo_id": (ligacao or {}).get("ri_protocolo_id")})
            if ligacao:
                flash(f"Protocolo {numero} aberto e vinculado à prenotação "
                      f"{ligacao['prenotacao_numero']}/"
                      f"{ligacao.get('prenotacao_livro') or '1A'}.", "success")
            else:
                flash(f"Protocolo {numero} aberto.", "success")
            return redirect(url_for("caixa_protocolo", protocolo_id=pid))

        # Por padrao: o que AINDA anda no balcao — ABERTO e A_PAGAR.
        # So ABERTO escondia OP com custas lancadas (ex.: 2026.09.23 Edilson,
        # situacao A_PAGAR): a busca por nome na lista padrao devolvia zero,
        # e o balcao achava que o protocolo nao existia.
        situacao = (request.args.get("situacao") or "ANDAMENTO").strip().upper()
        atribuicao = (request.args.get("atribuicao") or "").strip().upper()
        busca = (request.args.get("busca") or "").strip()
        # A página que não é número, ou que o OFFSET não aguenta, é a primeira.
        pagina = max(1, numero_digitado(request.args.get("pagina"),
                                        maximo=PAGINA_MAIS_ALTA) or 1)

        onde, params = ["1=1"], []
        if situacao == "ANDAMENTO":
            onde.append("situacao IN ('ABERTO', 'A_PAGAR')")
        elif situacao and situacao != "TODAS":
            onde.append("situacao=%s")
            params.append(situacao)
        if atribuicao:
            onde.append("atribuicao=%s")
            params.append(atribuicao)
        if busca:
            onde.append("(numero ILIKE %s OR interessado ILIKE %s OR assunto ILIKE %s)")
            params += [f"%{busca}%", f"%{busca}%", f"%{busca}%"]
        filtro = " AND ".join(onde)

        total = q1(f"SELECT COUNT(*) n FROM cx_protocolos WHERE {filtro}", params)["n"]
        rows = q(f"""SELECT * FROM cx_protocolos WHERE {filtro}
                     ORDER BY data_abertura DESC, numero DESC
                     LIMIT %s OFFSET %s""", params + [POR_PAGINA, (pagina - 1) * POR_PAGINA])
        resumo = q("""SELECT situacao, COUNT(*) n FROM cx_protocolos
                      GROUP BY situacao ORDER BY n DESC, situacao""")
        por_atrib = q("""SELECT atribuicao, COUNT(*) n FROM cx_protocolos
                         WHERE situacao IN ('ABERTO', 'A_PAGAR')
                         GROUP BY atribuicao ORDER BY n DESC, atribuicao""")
        with db.connect() as con_ri:
            prenotacoes_ri = CXP.prenotacoes_abertas(con_ri)
        return render_template("caixa_protocolos.html", rows=rows, resumo=resumo,
                               por_atrib=por_atrib, situacao=situacao,
                               atribuicao=atribuicao, busca=busca, total=total,
                               pagina=pagina,
                               paginas=max(1, (total + POR_PAGINA - 1) // POR_PAGINA),
                               SITUACOES=SITUACOES,
                               TIPOS_DOCUMENTO=TIPOS_DOCUMENTO,
                               prenotacoes_ri=prenotacoes_ri)

    def _rotulo_do_consumidor(con, tabela: str | None, ato_id) -> str:
        """Quem consumiu este item do protocolo, em texto para a ficha.

        `tabela` (`rg_atos` ou `at_certidoes`) veio de `usado_por_tabela`,
        gravada por `atribuicoes_web._marcar_itens_do_protocolo_como_usados`
        — sem ela, os dois IDs colidem (há `rg_atos` id=2 e `at_certidoes`
        id=2 sem relação nenhuma), e mostrar "ato nº 2" sem saber de qual
        tabela apontaria para o registro errado com a mesma confiança do
        certo. Item marcado antes desta coluna existir (sem `tabela`) sai
        com um rótulo genérico, em vez de arriscar a tabela errada.
        """
        if not ato_id:
            return ""
        if tabela == "rg_atos":
            linha = banco(con).um(
                """SELECT tipo, numero_ordem, rotulo FROM rg_atos
                    WHERE id=%s""", (int(ato_id),))
            if not linha:
                return ""
            tipo = str(linha["tipo"] or "").strip().upper()
            numero = linha["numero_ordem"] or linha["rotulo"] or ""
            nomes = {"AVERBACAO": "Averbação", "REGISTRO": "Registro",
                     "CANCELAMENTO": "Cancelamento"}
            return f"{nomes.get(tipo, tipo.title())} nº {numero}".strip()
        if tabela == "at_certidoes":
            linha = banco(con).um(
                """SELECT numero, ano FROM at_certidoes
                    WHERE id=%s""", (int(ato_id),))
            if not linha:
                return ""
            return f"Certidão nº {linha['numero']}/{linha['ano']}"
        return "já consumido em outro ato"

    @app.route("/caixa/protocolos/<int:protocolo_id>", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    # O AUDITOR ve a tela; o que ela GRAVA (POST) exige papel que pratica ato.
    @roles_required("ADMIN", "MANAGER", "USER", metodos=("POST",))
    def caixa_protocolo(protocolo_id):
        if request.method == "POST" and request.form.get("acao") == "contato":
            # Telefone e e-mail mudam com frequencia e nao sao ato: podem ser
            # corrigidos direto, com registro na auditoria.
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE cx_protocolos SET telefone=%s, email=%s,
                       interessado_documento=%s, previsao_entrega=%s,
                       documento_tipo=%s, documento_numero=%s,
                       documento_descricao=%s WHERE id=%s""",
                    ((request.form.get("telefone") or "").strip() or None,
                     (request.form.get("email") or "").strip() or None,
                     (request.form.get("interessado_documento") or "").strip() or None,
                     (request.form.get("previsao_entrega") or "").strip() or None,
                     (request.form.get("documento_tipo") or "").strip() or None,
                     (request.form.get("documento_numero") or "").strip() or None,
                     (request.form.get("documento_descricao") or "").strip() or None,
                     protocolo_id))
            audit("PROTOCOLO_CONTATO_ATUALIZADO", "PROTOCOLO", protocolo_id,
                  {"telefone": request.form.get("telefone"),
                   "email": request.form.get("email")})
            flash("Contato atualizado.", "success")
            return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))

        # O CÓDIGO DE ACOMPANHAMENTO — portal do cliente, 26/10/2026. «Gerar»
        # cria o código do protocolo que ainda não tem (o de antes do portal,
        # ou o que só teve orçamento); «trocar» faz um novo e o de antes deixa
        # de valer — o cliente perdeu o papel, ou o código foi visto por quem
        # não devia. A regra mora em `acompanhamento_cliente`.
        if request.method == "POST" and request.form.get("acao") in (
                "acompanhamento_gerar", "acompanhamento_trocar"):
            acao = request.form.get("acao")
            try:
                with db.transaction() as con:
                    if acao == "acompanhamento_trocar":
                        ACOMP.trocar_codigo(con, protocolo_id)
                    else:
                        ACOMP.codigo_do_protocolo(con, protocolo_id)
            except (ACOMP.AcompanhamentoError, ValueError, RuntimeError) as e:
                flash(f"O código de acompanhamento não foi gravado: {e}", "danger")
                return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))
            # Sem o código na auditoria: ele é a senha do cliente.
            audit("PROTOCOLO_ACOMPANHAMENTO_" + ("TROCADO" if acao.endswith("trocar")
                                                 else "GERADO"),
                  "PROTOCOLO", protocolo_id, {})
            flash("Código novo gravado. O de antes deixou de valer — imprima o "
                  "recibo ou a recepção de novo para o cliente."
                  if acao.endswith("trocar") else
                  "Código de acompanhamento gravado. Ele sai no recibo e no "
                  "protocolo de recepção.", "success")
            return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))

        # ENCERRAR E REABRIR — o débito «encerrar protocolo», de agosto.
        #
        # A regra inteira mora em `caixa_protocolo`, e a rota só liga os fios:
        # é ele quem recusa encerrar protocolo com dinheiro dentro, quem exige
        # o motivo escrito e quem recalcula a situação na volta.
        if request.method == "POST" and request.form.get("acao") in (
                "encerrar", "reabrir"):
            acao = request.form.get("acao")
            try:
                with db.transaction() as con:
                    if acao == "encerrar":
                        feito = CXP.encerrar(
                            con, protocolo_id,
                            situacao=request.form.get("encerramento"),
                            motivo=request.form.get("motivo"),
                            quem=_quem_esta_no_balcao(), agora=db.now())
                    else:
                        feito = CXP.reabrir(
                            con, protocolo_id,
                            motivo=request.form.get("motivo"),
                            quem=_quem_esta_no_balcao(), agora=db.now())
            except CXP.ProtocoloError as e:
                flash(str(e), "danger")
                return redirect(url_for("caixa_protocolo",
                                        protocolo_id=protocolo_id))
            audit(f"PROTOCOLO_{acao.upper()}", "PROTOCOLO", protocolo_id, feito)
            flash(
                f"Protocolo {feito['numero']} encerrado como "
                f"{CXP.ENCERRAMENTOS[feito['situacao']].split(' —')[0].lower()}."
                if acao == "encerrar" else
                f"Protocolo {feito['numero']} reaberto. A situação voltou a "
                f"sair dos itens, e o encerramento anterior ficou registrado.",
                "success")
            return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))

        # VINCULAR / DESVINCULAR A PRENOTACAO DO RI — o debito «faca o vinculo».
        #
        # A ponte `cx_protocolos.ri_protocolo_id` e o que faz o lavrar do RI
        # achar sozinho os itens do caixa. Sem ela, 0 de ~21 mil protocolos
        # tem ligacao; o escrevente precisa apontar a prenotacao na tela.
        if request.method == "POST" and request.form.get("acao") in (
                "vincular_ri", "desvincular_ri"):
            acao = request.form.get("acao")
            try:
                with db.transaction() as con:
                    if acao == "vincular_ri":
                        ri_pid = (request.form.get("ri_protocolo_id") or "").strip()
                        if not ri_pid.isdigit():
                            raise CXP.ProtocoloError(
                                "Escolha a prenotação do Livro 1 para vincular.")
                        ri_numero = numero_digitado(ri_pid)
                        if ri_numero is None:
                            raise CXP.ProtocoloError(
                                f"Não achei a prenotação {ri_pid[:20]}. Confira o "
                                f"número no Livro 1 antes de vincular.")
                        feito = CXP.vincular_ri(con, protocolo_id, ri_numero)
                    else:
                        feito = CXP.desvincular_ri(con, protocolo_id)
            except CXP.ProtocoloError as e:
                flash(str(e), "danger")
                return redirect(url_for("caixa_protocolo",
                                        protocolo_id=protocolo_id))
            audit(f"PROTOCOLO_{acao.upper()}", "PROTOCOLO", protocolo_id, feito)
            if acao == "vincular_ri":
                flash(
                    f"Protocolo {feito['protocolo_numero']} vinculado à "
                    f"prenotação {feito['prenotacao_numero']}/"
                    f"{feito.get('prenotacao_livro') or '1A'}.", "success")
            else:
                flash(
                    f"Protocolo {feito['protocolo_numero']}: vínculo com a "
                    f"prenotação removido.", "success")
            return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))

        p = q1("SELECT * FROM cx_protocolos WHERE id=%s", (protocolo_id,))
        if not p:
            abort(404)
        atos = [dict(r) for r in
                q("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s ORDER BY id",
                  (protocolo_id,))]
        lanc = q("""SELECT * FROM cx_lancamentos WHERE protocolo_id=%s
                    ORDER BY data, id""", (protocolo_id,))
        soma = EMOL.somar_itens(atos)
        pendente = EMOL.somar_itens([a for a in atos if not a["quitado"]])
        busca = (request.args.get("busca_ato") or "").strip()
        achados = _atos_da_tabela(db, busca)
        # O TETO DO ART. 37 SOBRE OS REGISTROS DE GARANTIA (item 16.31).
        # **Só mede.** Como o teto se conta — por tipo de garantia ou pela soma
        # de todos os registros do título — está em disputa entre os colegas,
        # com ofício na corregedoria; quem decide é quem assina.
        with db.connect() as con:
            acima_do_teto = EMOL.garantias_acima_do_teto(
                atos, EMOL.teto_geral(con))
        # QUANTOS FALTAM QUITAR — RELATO #52. A contagem vem daqui, e nao de uma
        # conta no modelo: o botao de quitar tudo diz o numero no proprio rotulo,
        # e rotulo que conta errado e' pior que rotulo nenhum.
        faltam = len([a for a in atos if not a["quitado"]])
        with db.connect() as con:
            # **O QUE JÁ FOI LAVRADO COM ESTE ITEM** — achado do oficial em
            # 12/09/2026: «por que eu não vejo no protocolo menção às
            # averbações feitas?». O item marcava `usado_em`/
            # `usado_por_ato_id` desde que um ato o consome (RCPJ/RTD), mas
            # a ficha do protocolo nunca lia essas duas colunas — o
            # escrevente via o item como "quitado" ou não, sem saber que
            # ele já tinha virado a averbação nº 378. `usado_por_tabela`
            # (rg_atos ou at_certidoes) diz onde procurar; sem ela (item
            # marcado antes desta correção) o rótulo fica genérico.
            for a in atos:
                a["usado_rotulo"] = (
                    _rotulo_do_consumidor(con, a.get("usado_por_tabela"),
                                          a.get("usado_por_ato_id"))
                    if a.get("usado_em") else "")
            # A LISTA DE ATENCAO PARA FRAUDES, sobre o interessado.
            #
            # O PROTOCOLO E O "ATO REQUERIDO" do pedido do oficial: e aqui que
            # o cliente chega, da o nome e pede o ato. Avisar so quando o ato
            # for lavrado seria avisar depois de a casa ter trabalhado.
            #
            # So LE: o rastro se grava quando o operador reconhece o alerta.
            fraudes = FR.conferir_pessoas(con, [
                {"nome": p["interessado"],
                 "documento": p["interessado_documento"],
                 "papel_no_ato": "interessado"},
            ])
        prenotacao_ligada = None
        prenotacoes_ri = []
        atrib_p = (p["atribuicao"] or "") if "atribuicao" in p.keys() else ""
        ri_fk = p["ri_protocolo_id"] if "ri_protocolo_id" in p.keys() else None
        if atrib_p.upper() == "RI" or ri_fk:
            with db.connect() as con_ri:
                if ri_fk:
                    prenotacao_ligada = CXP.prenotacao_por_id(con_ri, int(ri_fk))
                prenotacoes_ri = CXP.prenotacoes_abertas(con_ri)
                # Se a ligada ja nao esta aberta, ainda assim aparece na lista
                # para o balcao ver o que esta gravado (e poder trocar).
                if prenotacao_ligada and all(
                        int(x["id"]) != int(prenotacao_ligada["id"])
                        for x in prenotacoes_ri):
                    prenotacoes_ri = [prenotacao_ligada] + prenotacoes_ri
        # OS DOCUMENTOS PARA QUALIFICACAO — relato #135, 15/10/2026. Os
        # retirados vêm junto, com o motivo: sumir da tela seria o DELETE
        # com outra cara.
        with db.connect() as con_doc:
            docs_qualificacao = PDOC.documentos(con_doc, protocolo_id)
            # O código só aparece para quem pratica ato (o AUDITOR vê a ficha,
            # mas o código é a senha do cliente). SÓ LÊ: a ficha é GET.
            acompanhamento = {
                "elegivel": ACOMP.elegivel(dict(p)),
                "codigo": (ACOMP.formatar_codigo(ACOMP.codigo_ja_gravado(
                    con_doc, protocolo_id) or "") or None)
                if usuario_papel() in ("ADMIN", "MANAGER", "USER") else None,
                "tem": bool(p["acompanhamento_hash"]),
                "situacao": ACOMP.situacao_publica(con_doc, dict(p)),
            }
        return render_template("caixa_protocolo.html", p=p, atos=atos,
                               docs_qualificacao=docs_qualificacao,
                               TIPOS_DE_DOCUMENTO=PDOC.TIPOS_DE_DOCUMENTO,
                               PAPEIS_QUE_ANEXAM=PDOC.PAPEIS_QUE_ANEXAM,
                               fraudes=fraudes,
                               lancamentos=lanc, SITUACOES=SITUACOES,
                               soma=soma, pendente=pendente, busca_ato=busca,
                               achados=achados, TABELAS=EMOL.TABELAS_FAIXA,
                               # RELATO #52: o rótulo do botão diz quantos
                               # faltam, e a forma de pagamento do lote é
                               # escolhida uma vez só — o pagamento é um.
                               faltam=faltam, FORMAS=FORMAS_PAGAMENTO,
                               TIPOS=TIPOS_PROTOCOLO,
                               ENCERRAMENTOS=CXP.ENCERRAMENTOS,
                               encerrado=CXP.esta_encerrado(p["situacao"]),
                               TIPOS_DOCUMENTO=TIPOS_DOCUMENTO,
                               prenotacao_ligada=prenotacao_ligada,
                               prenotacoes_ri=prenotacoes_ri,
                               acima_do_teto=acima_do_teto,
                               acompanhamento=acompanhamento)

    # ---------------------------------------- documentos para qualificação
    #
    # RELATO #135, 15/10/2026, aberto da tarefa 386: «criar no protocolo geral
    # ou em notas aba de anexar documentos para fim de qualificação». A tarefa
    # guardava os papéis numa pasta sincronizada, fora do backup e fora da
    # tela de quem qualifica. A regra mora em `protocolo_documentos`; aqui só
    # se ligam os fios.

    def _pasta_dos_documentos_do_protocolo(numero) -> Path:
        """Dentro da pasta de arquivos que o backup varre — a régua da prenotação."""
        raiz = Path(db.get_setting("archive_root", "").strip()
                    or (Path(db.db_path).parent / "arquivos"))
        seguro = "".join(c if (c.isalnum() or c in "-_.") else "_"
                         for c in str(numero or "sem-numero"))[:60] or "sem-numero"
        return raiz / "protocolo" / seguro / "qualificacao"

    @app.route("/caixa/protocolos/<int:protocolo_id>/documentos", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def caixa_protocolo_documentos(protocolo_id):
        """Anexa um ou mais documentos para qualificação ao protocolo. ESCREVE."""
        from storage import save_upload
        volta = url_for("caixa_protocolo", protocolo_id=protocolo_id) + "#documentos-qualificacao"
        p = q1("SELECT * FROM cx_protocolos WHERE id=%s", (protocolo_id,))
        if not p:
            abort(404)
        enviados = [f for f in request.files.getlist("documento") if f and f.filename]
        if not enviados:
            flash("Escolha o arquivo antes de anexar.", "danger")
            return redirect(volta)
        tipo = request.form.get("tipo") or ""
        descricao = request.form.get("descricao") or ""
        # O LOTE INTEIRO SE CONFERE ANTES DE UM BYTE IR AO DISCO: um arquivo
        # ruim no meio de cinco não deixa os quatro bons gravados pela metade.
        try:
            for f in enviados:
                PDOC.conferir_arquivo(*PDOC.medir_envio(f))
        except PDOC.DocumentoError as e:
            flash(str(e), "danger")
            return redirect(volta)
        pasta = _pasta_dos_documentos_do_protocolo(p["numero"])
        salvos = [save_upload(f, pasta) for f in enviados]
        ids = []
        try:
            with db.transaction() as con:
                for info in salvos:
                    ids.append(PDOC.registrar(
                        con, protocolo_id, info, tipo=tipo, descricao=descricao,
                        usuario_id=usuario_id(), agora=db.now()))
        except PDOC.DocumentoError as e:
            # A transação voltou atrás; os arquivos gravados há pouco saem do
            # disco junto, senão ficariam órfãos sem linha nenhuma que os cite.
            for info in salvos:
                try:
                    Path(info["stored_path"]).unlink()
                except OSError:
                    pass
            flash(str(e), "danger")
            return redirect(volta)
        audit("PROTOCOLO_DOCUMENTO_ANEXADO", "PROTOCOLO", protocolo_id,
              {"anexos": ids, "tipo": tipo,
               "arquivos": [i["original_name"] for i in salvos],
               "sha256": [i["sha256"] for i in salvos]})
        flash(f"{len(ids)} documento(s) anexado(s) ao protocolo {p['numero']}.",
              "success")
        return redirect(volta)

    @app.route("/caixa/protocolos/<int:protocolo_id>/documentos/<int:anexo_id>/retirar",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def caixa_protocolo_documento_retirar(protocolo_id, anexo_id):
        """Retira o documento da lista, com motivo. Não apaga nada. ESCREVE."""
        volta = url_for("caixa_protocolo", protocolo_id=protocolo_id) + "#documentos-qualificacao"
        if not q1("SELECT id FROM cx_protocolos WHERE id=%s", (protocolo_id,)):
            abort(404)
        try:
            with db.transaction() as con:
                r = PDOC.retirar(con, protocolo_id, anexo_id,
                                 motivo=request.form.get("motivo") or "",
                                 por=usuario_nome(), agora=db.now())
        except PDOC.DocumentoError as e:
            flash(str(e), "danger")
            return redirect(volta)
        audit("PROTOCOLO_DOCUMENTO_RETIRADO", "PROTOCOLO", protocolo_id,
              {"anexo": anexo_id, "arquivo": r["original_name"],
               "sha256": r["sha256"], "motivo": r["retirado_motivo"]})
        flash(f"«{r['original_name']}» retirado da lista. O arquivo continua "
              "guardado, e o motivo fica registrado.", "success")
        return redirect(volta)

    @app.route("/caixa/protocolos/novo", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def caixa_protocolos_novo():
        """Atalho: o formulário de abrir protocolo mora em /caixa/protocolos.

        Robôs e links antigos pediam /caixa/protocolos/novo e levavam 404.
        """
        if request.method == "POST":
            # Reaproveita o mesmo POST da lista (acao=novo).
            return caixa_protocolos()
        return redirect(url_for("caixa_protocolos") + "#novo")

    @app.route("/caixa/emolumentos/buscar")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def caixa_emolumentos_buscar():
        """Busca de atos da tabela — JSON para quem digita na hora.

        Era 404: a busca sempre existiu em /caixa/emolumentos?busca=, mas o
        atalho /buscar é o que a tela e os testes esperam.
        """
        termo = (request.args.get("q") or request.args.get("busca") or "").strip()
        limite = 30
        try:
            limite = min(100, max(1, int(request.args.get("limite") or 30)))
        except (TypeError, ValueError):
            limite = 30
        with db.connect() as con:
            linhas = EMOL.buscar(con, termo, limite=limite) if termo else []
        if request.args.get("formato") == "html":
            return render_template("_atos_da_tabela_fragmento.html",
                                   achados=linhas, busca=termo, protocolo_id=None)
        return {
            "ok": True,
            "busca": termo,
            "total": len(linhas),
            "itens": [dict(r) if hasattr(r, "keys") else r for r in linhas],
        }

    @app.route("/caixa/protocolos/<int:protocolo_id>/atos-da-tabela")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def caixa_protocolo_atos_da_tabela(protocolo_id):
        """A lista de atos da tabela, sozinha — para a busca que não recarrega.

        RELATO #53 do oficial: «itens da tabela ao procurar o ato poderiam ser
        listados automaticamente — para procurar um item para acrescentar da
        tabela no protocolo precisa clicar em pesquisar, daí recarrega a página
        e vai lá pra cima, fazendo perder tempo».

        **SÓ LÊ.** Não grava, não muda situação e não lança nada: é a mesma
        consulta que a tela do protocolo já faz ao abrir com `?busca_ato=`.

        E devolve o fragmento do **mesmo** `_atos_da_tabela.html` que a tela
        usa — duas montagens da mesma lista divergiriam no primeiro conserto, e
        a lista que aparece ao digitar deixaria de ser a que aparece ao clicar.
        """
        if not q1("SELECT id FROM cx_protocolos WHERE id=%s", (protocolo_id,)):
            abort(404)
        busca = (request.args.get("busca") or "").strip()
        achados = _atos_da_tabela(db, busca) if busca else []
        # Sem termo: devolve fragmento explicito (antes saiam ~5 bytes vazios).
        return render_template("_atos_da_tabela_fragmento.html",
                               achados=achados,
                               busca=busca, protocolo_id=protocolo_id,
                               vazio_sem_busca=not bool(busca))

    def _quem_esta_no_balcao() -> str | None:
        """O nome de quem esta logado, pelo mesmo caminho da auditoria.

        Nao se digita: campo que o operador tem de preencher para o rastro
        ficar bom e campo que fica vazio.
        """
        uid = usuario_id()
        if not uid:
            return None
        u = db.get_user(int(uid))
        return (u["username"] if u else None)

    @app.route("/caixa/protocolos-parados")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def caixa_protocolos_parados():
        """Os protocolos abertos que nunca ganharam item — os de encerrar.

        SEM ESTA TELA A FUNCAO NAO EXISTIRIA NA PRATICA: sao 640 no acervo
        desta casa, perdidos numa lista de 21.348. Procurar um a um seria o
        mesmo que nao ter por onde encerrar.
        """
        with db.connect() as con:
            parados = CXP.abertos_sem_item(con)
            total = CXP.quantos_abertos_sem_item(con)
        return render_template("caixa_protocolos_parados.html",
                               parados=parados, total=total)

    @app.route("/caixa/protocolos/<int:protocolo_id>/recepcao", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def caixa_recepcao(protocolo_id):
        """Protocolo de recepção: o comprovante que fica com o cliente.

        É o documento que prova o que entrou no balcão — quem trouxe, o que
        trouxe e para quê. Sai do cartório, então CPF, telefone e e-mail vão
        mascarados (Lei 13.709/2018, art. 6º, III — só o necessário).

        POST COM O TOKEN (M8 do LS01, lote LX11). Era GET, e GET que grava
        não passa pelo CSRF da casa: o `SameSite=Lax` manda o cookie em link
        vindo de fora, e bastava um link ou `<img>` com o id para gravar em
        nome de quem estivesse logado. O botão da tela manda o formulário. Aqui grava a
        hora da recepção (`recepcao_em`).
        """
        p = q1("SELECT * FROM cx_protocolos WHERE id=%s", (protocolo_id,))
        if not p:
            abort(404)
        itens = [dict(r) for r in
                 q("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s ORDER BY id",
                   (protocolo_id,))]
        soma = EMOL.somar_itens(itens)
        pendente = EMOL.somar_itens([i for i in itens if not i["quitado"]])

        from jinja2.sandbox import SandboxedEnvironment
        env = SandboxedEnvironment(autoescape=False)
        # O CÓDIGO DE ACOMPANHAMENTO no comprovante de abertura (portal do
        # cliente, 26/10/2026). Esta rota é POST e já grava a hora da
        # recepção: o código nasce aqui na primeira vez, e nas outras é lido.
        endereco_do_portal = db.get_setting(PORTAL.CHAVE_URL, "")
        with db.transaction() as _t:
            acompanhamento = ACOMP.codigo_para_o_papel(
                _t, protocolo_id, endereco_do_portal=endereco_do_portal)
        with db.connect() as _c:
            _modelo = MODELOS.corpo_de(_c, "CAIXA_RECEPCAO")
        html = env.from_string(_modelo).render(
            p=dict(p), itens=itens, soma=soma, pendente=pendente,
            acompanhamento=acompanhamento,
            sv=bloco_serventia(),
            documento=mascarar_documento(p["interessado_documento"]),
            telefone=mascarar_telefone(p["telefone"]),
            email=mascarar_email(p["email"]),
            observacao=mascarar_texto(p["observacao"]),
            data=fmt_date(p["data_abertura"]),
            previsao=fmt_date(p["previsao_entrega"]) if p["previsao_entrega"] else "",
            emitido_por=usuario_nome(), funcao=usuario_funcao())
        arquivo = gerar_odt(html_para_odf(html),
                            titulo=f"Protocolo de recepção {p['numero']}")
        with db.transaction() as con:
            banco(con).escrever("UPDATE cx_protocolos SET recepcao_em=%s WHERE id=%s",
                        (db.now(), protocolo_id))
        audit("RECEPCAO_EMITIDA", "PROTOCOLO", protocolo_id, {"numero": p["numero"]})
        return Response(arquivo, mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="recepcao-{p["numero"]}.odt"'})

    # ------------------------------------------------- portal do cliente
    #
    # «Portal do cliente para acompanhar o pedido e baixar o recibo», no VPS
    # do WhatsApp — o oficial, 26/10/2026. O servidor EMPURRA o retrato para a
    # VPS (saída, HTTPS, token no cofre); a VPS não alcança a casa. A regra
    # mora em `portal_cliente`; aqui só se ligam os fios.

    @app.route("/caixa/portal-do-cliente", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER")
    def caixa_portal_cliente():
        if request.method == "POST":
            # GRAVAR É SÓ DO ADMIN: a tela grava o endereço para onde o token
            # vai. Aberta a mais gente, trocar o endereço pelo de fora
            # entregaria o token no próximo envio — a regra do WhatsApp (LS01).
            if usuario_papel() != "ADMIN":
                abort(403)
            acao = request.form.get("acao") or "gravar"
            if acao == "enviar":
                resumo = PORTAL.enviar(db)
                audit("PORTAL_CLIENTE_ENVIO", "PORTAL", None, resumo)
                if resumo.get("ok"):
                    flash(f"Portal atualizado: {resumo['enviados']} protocolo(s) "
                          f"enviado(s), {resumo['removidos']} retirado(s)"
                          + (f", {resumo['incompletos']} sem o PDF do recibo "
                             f"(sobe na próxima rodada)" if resumo["incompletos"]
                             else "") + ".", "success")
                else:
                    flash(f"Nada subiu: {resumo.get('motivo')}.", "warning")
                return redirect(url_for("caixa_portal_cliente"))
            try:
                with db.transaction() as con:
                    PORTAL.gravar_configuracao(
                        con, url=request.form.get("url"),
                        ligado=bool(request.form.get("ligado")),
                        token=request.form.get("token"),
                        apagar_token=bool(request.form.get("apagar_token")))
            except (PORTAL.PortalError, ValueError, RuntimeError) as e:
                flash(f"A configuração não foi gravada: {e}", "danger")
                return redirect(url_for("caixa_portal_cliente"))
            # O token não vai para a auditoria — só se ele mudou.
            audit("PORTAL_CLIENTE_CONFIG", "PORTAL", None,
                  {"url": (request.form.get("url") or "").strip(),
                   "ligado": bool(request.form.get("ligado")),
                   "token_trocado": bool((request.form.get("token") or "").strip()),
                   "token_apagado": bool(request.form.get("apagar_token"))})
            flash("Configuração do portal gravada. O token não aparece na tela "
                  "nem no log.", "success")
            return redirect(url_for("caixa_portal_cliente"))
        with db.connect() as con:
            cfg = PORTAL.configuracao(con)
        return render_template("caixa_portal_cliente.html", cfg=cfg,
                               pode_gravar=usuario_papel() == "ADMIN",
                               DIAS_DEPOIS_DE_ENCERRADO=PORTAL.DIAS_DEPOIS_DE_ENCERRADO,
                               DIAS_DO_ABERTO=PORTAL.DIAS_DO_ABERTO,
                               SEM_RECIBO=sorted(PORTAL.SEM_RECIBO_NO_PORTAL),
                               LIBERADO=sorted(PORTAL.RECIBO_LIBERADO_NO_PORTAL),
                               FORA=sorted(ACOMP.FORA_DO_ACOMPANHAMENTO))

    # ------------------------------------------------- itens e orçamento

    @app.route("/caixa/protocolos/<int:protocolo_id>/itens", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def caixa_protocolo_itens(protocolo_id):
        """Acrescenta, quita ou remove um item do protocolo.

        O valor NÃO é digitado: vem da tabela do tribunal. Ou o ato tem valor
        fixo, e se escolhe pelo código; ou depende do valor do negócio, e se
        informa a base para achar a faixa.
        """
        p = q1("SELECT * FROM cx_protocolos WHERE id=%s", (protocolo_id,))
        if not p:
            abort(404)
        acao = request.form.get("acao")

        if acao == "acrescentar":
            servico = (request.form.get("servico") or "").strip()
            tabela = (request.form.get("tabela") or "").strip()
            base = (request.form.get("base_calculo") or "").strip()
            # Sem base, faixa_por_valor(0) cai na PRIMEIRA faixa do RI (16.3.1) —
            # errado para 2ª via / certidão e para qualquer ato que não dependa
            # do valor do negócio. Exige a base quando o caminho é a faixa.
            if tabela and not servico and not base:
                flash(
                    "Informe o valor do negócio para acrescentar pela faixa. "
                    "Sem valor, o sistema cairia na primeira faixa do RI "
                    "(errada para certidão / 2ª via).",
                    "danger",
                )
                return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))
            # A QUANTIDADE VAI PARA `cx_protocolo_atos.quantidade` (`integer`):
            # o número que não cabe nela derrubava o INSERT (LD13).
            quantidade = numero_digitado(request.form.get("quantidade") or "1",
                                         maximo=MAIOR_INTEGER)
            if quantidade is None:
                flash("A quantidade precisa ser um numero inteiro.", "danger")
                return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))
            # O ITEM 16.31: a MESMA garantia estipulada em mais de um imóvel.
            # A base de cada registro é o valor do negócio dividido por eles, e
            # são N registros. Quem informa é quem leu a cédula — o sistema não
            # tem como contar os imóveis de um título que não está aqui dentro.
            try:
                imoveis = int(request.form.get("imoveis") or 1)
            except (TypeError, ValueError):
                flash("O numero de imoveis precisa ser um numero inteiro.", "danger")
                return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))
            with db.connect() as con:
                item = EMOL.calcular_item(
                    con, servico=numero_digitado(servico),
                    tabela=numero_digitado(tabela),
                    base=base, quantidade=quantidade, imoveis=imoveis)
            if not item:
                flash("Não encontrei esse ato na tabela vigente. "
                      "Confira o código ou o valor do negócio.", "danger")
                return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))
            # No 16.31 a quantidade é multiplicada pelos imóveis: cada um cabe,
            # e o produto pode não caber na coluna (LD13).
            if int(item["quantidade"]) > MAIOR_INTEGER:
                flash("A quantidade vezes o número de imóveis passa do que o "
                      "protocolo guarda. Confira os dois campos.", "danger")
                return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))
            with db.transaction() as con:
                bd = banco(con)
                bd.escrever(
                    """INSERT INTO cx_protocolo_atos
                       (protocolo_id, descricao, codigo_ato, quantidade,
                        valor_total, emolumentos, ferc, fadep, femp, ferrfis,
                        servico_codigo, base_calculo, origem_valor)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (protocolo_id, item["descricao"], item["codigo_tj"],
                     item["quantidade"], item["total"], item["emolumentos"],
                     item["ferc"], item["fadep"], item["femp"], item["ferrfis"],
                     item["servico_codigo"], item["base_calculo"],
                     item["origem_valor"]))
                _atualizar_total(bd, protocolo_id)
            audit("PROTOCOLO_ITEM_ACRESCENTADO", "PROTOCOLO", protocolo_id,
                  {"codigo_tj": item["codigo_tj"], "total": item["total"],
                   "imoveis": item.get("imoveis"),
                   "base_do_negocio": item.get("base_do_negocio")})
            aviso = (" O valor ficou acima do teto da tabela: confira, porque daí "
                     "em diante o cálculo costuma ter regra própria."
                     if item.get("acima_do_teto") else "")
            # A DIVISÃO APARECE NA FRASE, e não só na coluna da tabela: quem
            # acabou de digitar «3 imóveis» precisa ver que a base que valeu foi
            # um terço, para conferir antes de fechar o orçamento.
            if item.get("imoveis", 1) > 1:
                aviso += (f" A base de cada registro é R$ {item['base_calculo']}"
                          f" — o negócio de R$ {item['base_do_negocio']}"
                          f" dividido por {item['imoveis']} imóveis (item 16.31).")
                if item.get("sobra_centavos"):
                    aviso += (f" A divisão deixou {item['sobra_centavos']} centavo(s)"
                              " de sobra, que não entraram em registro nenhum.")
            flash(f"Item {item['codigo_tj']} acrescentado — R$ {item['total']}.{aviso}",
                  "warning" if item.get("acima_do_teto") else "success")
            return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))

        if acao == "quitar":
            # QUITAR PASSOU A LANÇAR NO CAIXA — decisão do oficial em
            # 27/08/2026: «juntemos protocolo geral com o caixa».
            #
            # Antes, quitar só marcava uma bandeira, e o dinheiro entrava por
            # outro caminho — o botão «cobrar» da ficha do ato. Dois trilhos
            # para o mesmo dinheiro é como eles divergem: o protocolo dizia que
            # o cliente pagou e o caixa não tinha o lançamento.
            item_id = numero_digitado(request.form.get("item_id"))
            aberto = caixa_aberto(usuario_nome())
            agora = db.now()
            try:
                if item_id is None:
                    raise CaixaError("Escolha o item do protocolo a quitar.")
                with db.transaction() as con:
                    r = cobrar_item_do_protocolo(
                        con, item_id,
                        caixa_id=int(aberto["id"]) if aberto else 0,
                        agora=agora, hoje=agora[:10], hora=agora[11:16],
                        forma_pagamento=request.form.get("forma_pagamento"),
                        usuario=usuario_nome())
                    _atualizar_situacao(con, protocolo_id)
            except CaixaError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("caixa_protocolo",
                                        protocolo_id=protocolo_id))
            audit("PROTOCOLO_ITEM_QUITADO", "PROTOCOLO", protocolo_id,
                  {"item": item_id, "lancamento": r["lancamento_id"]})
            flash(f"Item quitado e lançado no caixa: R$ {r['valor']}.",
                  "success")
            return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))

        if acao == "quitar_todos":
            # RELATO #52 do oficial: «caixa, permitir que um botao quite todos os
            # itens — permitir quitar tudo com um botao so».
            #
            # MEDIDO antes de construir: nesta casa ha protocolo em `A_PAGAR`
            # com 37 itens, e cada um deles e' um clique mais uma ida e volta de
            # pagina. Quem atende cinco pedidos de uma vez no mesmo balcao
            # pagava esse preco cinco vezes.
            #
            # O QUE ESTE BOTAO NAO E': nao e' um INSERT em lote. Cada item passa
            # por `cobrar_item_do_protocolo`, que e' a MESMA funcao do botao de
            # um item — e' ela que monta o lancamento com os quatro fundos
            # separados, que recusa cobrar duas vezes e que exige o caixa
            # aberto. **Um caminho so para o dinheiro**: se este botao montasse
            # os lancamentos por conta propria, os dois divergiriam no primeiro
            # conserto, e a conferencia de fundos deixaria de fechar sem
            # ninguem saber qual dos dois estava certo.
            #
            # **CADA ITEM NA SUA PROPRIA TRANSACAO**, como o lote do protesto:
            # um que falhe nao desfaz os outros, e a resposta diz quais ficaram.
            # Quitar em lote que volta atras inteira faria o balcao nao saber o
            # que foi cobrado — e o cliente ja foi embora com o papel na mao.
            #
            # A FORMA DE PAGAMENTO DO LOTE VALE PARA TODOS OS ITENS: o pagamento
            # e' um so. Em branco, grava em branco como no botao de um item —
            # nao se adivinha como o cliente pagou.
            pendentes_id = [int(r["id"]) for r in q(
                """SELECT id FROM cx_protocolo_atos
                   WHERE protocolo_id=%s AND quitado=0 ORDER BY id""",
                (protocolo_id,))]
            aberto = caixa_aberto(usuario_nome())
            if not pendentes_id:
                # Rodar de novo nao cobra de novo, e a frase diz isso em vez de
                # repetir 37 recusas iguais: quem clica duas vezes por duvida
                # precisa saber que nada foi cobrado a mais.
                flash("Não há item a quitar neste protocolo — os que existem já "
                      "foram quitados.", "warning")
            elif not aberto:
                # A RECUSA VEM ANTES DE TENTAR. O mesmo erro repetido N vezes nao
                # ensina nada a mais: enche a tela de avisos iguais e esconde a
                # unica coisa que resolve — abrir o caixa.
                flash("Você não tem caixa aberto, e sem caixa o lançamento não "
                      "aparece na conferência do dia. Abra o caixa em "
                      "Administrativo → Caixa.", "danger")
            else:
                agora = db.now()
                forma = request.form.get("forma_pagamento")
                quitados, soma_quitada, recusados = 0, 0, []
                for item_id in pendentes_id:
                    try:
                        with db.transaction() as con:
                            r = cobrar_item_do_protocolo(
                                con, item_id,
                                caixa_id=int(aberto["id"]),
                                agora=agora, hoje=agora[:10], hora=agora[11:16],
                                forma_pagamento=forma, usuario=usuario_nome())
                            _atualizar_situacao(con, protocolo_id)
                    except CaixaError as erro:
                        recusados.append((item_id, str(erro)))
                        continue
                    except sqlite3.IntegrityError:
                        # O ITEM JÁ TEM LANÇAMENTO PELA CHAVE DE ORIGEM, e a
                        # marca `lancamento_id` ficou para trás — é o estado que
                        # a carga repetida do E-Ofício deixa. A frase é a do
                        # domínio, e não o texto cru do SQLite: «UNIQUE
                        # constraint failed» na cara de quem atende não diz o
                        # que fazer, e num lote ela interromperia os itens
                        # seguintes por causa de um.
                        recusados.append((item_id,
                                          "Este item já entrou no caixa — "
                                          "confira o lançamento dele antes de "
                                          "quitar de novo."))
                        continue
                    # A AUDITORIA DO LOTE E' A DO ITEM, com a marca de que veio
                    # num lote: quem for ler o rastro depois precisa achar cada
                    # item quitado pelo mesmo caminho de sempre, e saber por que
                    # ele entrou sem um clique proprio.
                    audit("PROTOCOLO_ITEM_QUITADO", "PROTOCOLO", protocolo_id,
                          {"item": item_id, "lancamento": r["lancamento_id"],
                           "em_lote": True})
                    quitados += 1
                    soma_quitada += centavos(r["valor"])
                if quitados:
                    flash(f"{quitados} "
                          f"{'item quitado' if quitados == 1 else 'itens quitados'}"
                          f" e lançado{'s' if quitados > 1 else ''} no caixa — "
                          f"R$ {reais(soma_quitada)}.", "success")
                # O QUE NAO ENTROU APARECE COM O MOTIVO, e nao como uma lista de
                # numeros soltos: e' o motivo que diz o que fazer.
                for item_id, motivo in recusados[:5]:
                    flash(f"Item {item_id} não foi quitado: {motivo}", "danger")
                if len(recusados) > 5:
                    flash(f"Mais {len(recusados) - 5} itens não foram quitados, "
                          f"pelo mesmo motivo — confira a lista antes de tentar "
                          f"de novo.", "danger")
            return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))

        if acao == "desquitar":
            # DESQUITAR NAO APAGA O LANCAMENTO. Dinheiro que entrou no caixa
            # sai por ESTORNO, que deixa rastro — apagar a linha faria a
            # conferência do dia fechar sem que ninguém soubesse por quê. Aqui
            # se desfaz só a marca; o estorno é na tela do caixa.
            item_id = numero_digitado(request.form.get("item_id"))
            with db.transaction() as con:
                bd = banco(con)
                # A CONFERÊNCIA SE FAZ COM A LINHA PRESA (LD06): lida fora da
                # transação, o «usar» do depósito ou a quitação em dinheiro do
                # outro balcão cabiam entre a leitura e a gravação, e o item
                # pago se reabria — o cliente pagaria de novo.
                bd._escrita()
                ja = bd.um("""SELECT lancamento_id, quitado_por FROM cx_protocolo_atos
                               WHERE id=%s FOR UPDATE""", (item_id,))
                if ja and ja["lancamento_id"]:
                    flash("Este item já entrou no caixa. Para desfazer, estorne o "
                          f"lançamento {ja['lancamento_id']} na tela do caixa — "
                          "dinheiro que entrou sai por estorno, e não apagando.",
                          "danger")
                    return redirect(url_for("caixa_protocolo",
                                            protocolo_id=protocolo_id))
                # O ITEM PAGO PELO DEPÓSITO PRÉVIO NÃO SE REABRE AQUI (LD06):
                # reabrir só a marca deixaria o dinheiro gasto no depósito e o
                # item a pagar — e o cliente pagaria duas vezes o mesmo serviço.
                if ja and str(ja["quitado_por"] or "").startswith("DEPÓSITO PRÉVIO"):
                    qual = ja["quitado_por"][len("DEPÓSITO PRÉVIO"):].strip()
                    flash(f"Este item foi pago com o depósito prévio {qual}. "
                          "Reabrir a quitação deixaria o valor gasto no depósito e "
                          "o item a pagar de novo; se o uso do depósito foi engano, "
                          "leve ao oficial — a correção é no depósito, com o rastro.",
                          "danger")
                    return redirect(url_for("caixa_protocolo",
                                            protocolo_id=protocolo_id))
                bd.escrever(
                    """UPDATE cx_protocolo_atos SET quitado=0, quitado_em=NULL,
                       quitado_por=NULL WHERE id=%s AND protocolo_id=%s""",
                    (item_id, protocolo_id))
                _atualizar_situacao(bd, protocolo_id)
            audit("PROTOCOLO_ITEM_DESQUITADO", "PROTOCOLO", protocolo_id,
                  {"item": item_id})
            flash("Item marcado como não quitado.", "warning")
            return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))

        if acao == "remover":
            item_id = numero_digitado(request.form.get("item_id"))
            with db.transaction() as con:
                bd = banco(con)
                bd.escrever("""DELETE FROM cx_protocolo_atos
                               WHERE id=%s AND protocolo_id=%s AND quitado=0""",
                            (item_id, protocolo_id))
                _atualizar_total(bd, protocolo_id)
            audit("PROTOCOLO_ITEM_REMOVIDO", "PROTOCOLO", protocolo_id, {"item": item_id})
            flash("Item removido. Item já quitado não se remove.", "success")
            return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))

        return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))

    def _atualizar_total(con, protocolo_id):
        """Recalcula o total do protocolo a partir dos itens."""
        bd = banco(con)
        itens = bd.ler("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s ORDER BY id",
                       (protocolo_id,))
        soma = EMOL.somar_itens(itens)
        bd.escrever("UPDATE cx_protocolos SET valor_total=%s WHERE id=%s",
                    (soma["total"], protocolo_id))
        _atualizar_situacao(bd, protocolo_id)

    def _atualizar_situacao(con, protocolo_id):
        """A situação vem dos itens: todos quitados, protocolo pago.

        É a mesma regra da carga do E-Ofício — a situação se deduz do que
        aconteceu, não de um campo que alguém marca à mão e esquece.
        """
        bd = banco(con)
        linha = bd.um(
            """SELECT COUNT(*) AS total, COALESCE(SUM(quitado),0)::bigint AS quitados
               FROM cx_protocolo_atos WHERE protocolo_id=%s""",
            (protocolo_id,))
        atual = bd.um("SELECT situacao, tipo FROM cx_protocolos WHERE id=%s",
                      (protocolo_id,))
        if atual and atual["situacao"] in ("CANCELADO", "ENTREGUE"):
            return
        if not linha["total"]:
            nova = "ABERTO"
        elif linha["quitados"] >= linha["total"]:
            nova = "PAGO"
        else:
            nova = "A_PAGAR"
        bd.escrever("UPDATE cx_protocolos SET situacao=%s, finalizado=%s WHERE id=%s",
                    (nova, 1 if nova == "PAGO" else 0, protocolo_id))

    @app.route("/caixa/protocolos/<int:protocolo_id>/orcamento")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def caixa_orcamento(protocolo_id):
        """Gera o orçamento em .odt, com os itens e a composição dos fundos."""
        p = q1("SELECT * FROM cx_protocolos WHERE id=%s", (protocolo_id,))
        if not p:
            abort(404)
        itens = [dict(r) for r in
                 q("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s ORDER BY id",
                   (protocolo_id,))]
        if not itens:
            flash("O protocolo não tem itens para orçar.", "warning")
            return redirect(url_for("caixa_protocolo", protocolo_id=protocolo_id))
        soma = EMOL.somar_itens(itens)
        s = db.get_settings()
        vig = q1("SELECT codigo FROM cx_vigencias WHERE vigente=1 ORDER BY codigo")

        from jinja2.sandbox import SandboxedEnvironment
        env = SandboxedEnvironment(autoescape=False)
        with db.connect() as _c:
            _modelo = MODELOS.corpo_de(_c, "CAIXA_ORCAMENTO")
            # o aviso de «mero cálculo» é peça do orçamento desde o LF06F
            _aviso = MODELOS.texto_do_papel(_c, PECA_DO_AVISO_ORCAMENTO)
        html = env.from_string(_modelo).render(
            p=dict(p), itens=itens, soma=soma,
            extenso=por_extenso(soma["total_centavos"]),
            orcamento=(p["tipo"] == "ORCAMENTO"), aviso=_aviso,
            vigencia=vig["codigo"] if vig else "—",
            sv=bloco_serventia(),
            documento=mascarar_documento(p["interessado_documento"]),
            telefone=mascarar_telefone(p["telefone"]),
            email=mascarar_email(p["email"]),
            data=fmt_date(date.today().isoformat()),
            emitido_por=usuario_nome(), funcao=usuario_funcao())
        arquivo = gerar_odt(html_para_odf(html),
                            titulo=f"Orçamento {p['numero']}")
        audit("ORCAMENTO_EMITIDO", "PROTOCOLO", protocolo_id,
              {"numero": p["numero"], "total": soma["total"]})
        return Response(arquivo, mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="orcamento-{p["numero"]}.odt"'})

    # ------------------------------------------------------ emolumentos

    @app.route("/caixa/emolumentos", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    # O AUDITOR ve a tela; o que ela GRAVA (POST) exige papel que pratica ato.
    @roles_required("ADMIN", "MANAGER", "USER", metodos=("POST",))
    def caixa_emolumentos():
        """Consulta da tabela do TJMA, importada do E-Ofício."""
        with db.connect() as con:
            if request.method == "POST" and request.form.get("acao") == "importar":
                # A pasta e a do arquivo achado, nao a pasta de trabalho.
                achados = procurar_arquivos("dom_servico.jsonl")
                caixa_dir = achados[0].parent if achados else None
                faixas = procurar_arquivos("dom_tabelas.jsonl")
                ri_dir = faixas[0].parent if faixas else None
                if not caixa_dir:
                    flash("Não encontrei a pasta EXPORT_CAIXA_EOFICIO. "
                          "Rode o EXPORTAR_CAIXA.cmd.", "danger")
                    return redirect(url_for("caixa_emolumentos"))
                with db.transaction() as tcon:
                    rel = EMOL.importar(tcon, caixa_dir, ri_dir)
                audit("EMOLUMENTOS_IMPORTADOS", "EMOLUMENTO", None, rel)
                conf = rel.get("conferencia", {})
                flash(f"Tabela importada: {rel['servicos']} atos, {rel['valores']} "
                      f"valores e {rel['faixas']} faixas. Vigência atual: "
                      f"{rel['vigente']}. Conferência dos fundos: "
                      f"{conf.get('divergentes', 0)} divergência(s) em "
                      f"{conf.get('conferidos', 0)}.", "success")
                return redirect(url_for("caixa_emolumentos"))

            vigencias = [dict(r) for r in
                         banco(con).ler("SELECT * FROM cx_vigencias ORDER BY codigo DESC")]
            vigente = next((v["codigo"] for v in vigencias if v["vigente"]), None)
            busca = (request.args.get("busca") or "").strip()
            resultados = EMOL.buscar(con, busca) if busca else []
            valor = (request.args.get("valor") or "").strip()
            tabela = numero_digitado(request.args.get("tabela"))
            if tabela is None:      # vazio ou que não é número: a tabela do RI
                tabela = EMOL.TABELA_RI
            faixa = EMOL.faixa_por_valor(con, valor, tabela) if valor else None

        return render_template("caixa_emolumentos.html", vigencias=vigencias,
                               vigente=vigente, busca=busca, resultados=resultados,
                               valor=valor, tabela=tabela, faixa=faixa,
                               TABELAS=EMOL.TABELAS_FAIXA,
                               PERCENTUAIS=EMOL.PERCENTUAIS)

    # --------------------------------------------------------- importar

    @app.route("/caixa/importar", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def caixa_importar():
        # O marcador e um arquivo que so a exportacao do caixa produz.
        achados = procurar_arquivos("protocolo_geral.jsonl")
        pasta = achados[0].parent if achados else None

        if request.method == "POST" and pasta:
            # Copia de seguranca antes de mexer, como na carga do RI.
            # Fora da pasta do banco — ordem do oficial em 11/10/2026.
            import pasta_das_copias
            marca = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            copia = pasta_das_copias.destino_da_copia(Path(f"antes_carga_caixa_{marca}.sqlite3"), Path(db.db_path))
            with db.connect() as origem_con:
                alvo = sqlite3.connect(copia)
                origem_con.backup(alvo)
                alvo.close()
            try:
                with db.transaction() as con:
                    rel = importar_caixa(con, pasta, None)
            except Exception as erro:
                flash(SEGWEB.recado_de_erro(
                    erro, "caixa_importar", "A importação falhou e nada foi "
                    "gravado; o detalhe ficou no registro do servidor.")
                      + f" Cópia de segurança em {copia.name}.", "danger")
                return redirect(url_for("caixa_importar"))
            audit("CAIXA_IMPORTADO", "CAIXA", None, rel)
            ja = (rel.get("protocolos_ja_existentes", 0)
                  + rel.get("custas_ja_existentes", 0)
                  + rel.get("lancamentos_ja_existentes", 0))
            flash(f"Entraram agora: {rel['protocolos']} protocolo(s), "
                  f"{rel['custas']} custa(s) e {rel['lancamentos']} movimento(s) de caixa. "
                  + (f"{ja} registro(s) já estavam no sistema e foram ignorados. "
                     if ja else "")
                  + f"{rel['quarentena']} em quarentena. "
                  f"Cópia de segurança: {copia.name}.", "success")
            return redirect(url_for("caixa_protocolos"))

        ja = q1("SELECT COUNT(*) AS n FROM cx_protocolos")["n"]
        return render_template("caixa_importar.html", pasta=str(pasta) if pasta else None,
                               ja_importado=ja)


def __getattr__(nome: str):
    """Os nomes antigos do texto de fábrica, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06A (19/10/2026) e mora em `modelos_padrao/`.
    Quem ainda importa o nome antigo recebe o padrão da base — o MESMO que o
    papel imprime, e não uma cópia que ficou para trás. Nome que não é de papel
    continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
