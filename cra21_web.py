"""A tela da API da CRA — testar, e trazer o arquivo pelo nome.

Ordem do oficial em 02/09/2026: *«vamos integrar a api da cra21»*.

**ESTA TELA É MENOS DO QUE ELA PODERIA SER, E ISSO É DELIBERADO.** O contrato
da CRA está medido no WSDL — 21 operações, os parâmetros de cada uma —, mas
**duas coisas não estão**: o que vai em `userDados` e o que exatamente volta no
`return`. O manual não descreve nem uma nem outra, e o exemplo em PHP passa um
argumento só.

**Construir a corrente inteira em cima disso seria inventar o meio dela.** Um
botão «baixar a remessa e apontar tudo» que lesse errado o que a Central manda
apontaria títulos que ninguém apresentou — e apontamento não se desfaz.

**Então esta tela faz o que dá para fazer com verdade, e é bastante:** ela
testa a conexão e **traz o arquivo cru**, para o oficial ver o que a Central
responde. É exatamente isso que vai permitir medir as duas coisas que faltam —
e a P21 ofereceu liberar a homologação para isso. **No dia em que o formato
estiver medido, o resto se liga em poucas linhas**, porque
`protesto_arquivo`, `protesto_remessa` e `protesto_desistencia` já leem os
cinco layouts.

**O TESTE DE CONEXÃO USA A ÚNICA OPERAÇÃO SEM PARÂMETRO NENHUM** —
`BuscarApresentante`. Um teste que pedisse uma remessa **marcaria a remessa
como baixada** do lado de lá, e o dia seguinte começaria com o arquivo
faltando.
"""
from __future__ import annotations

from flask import Response, flash, redirect, render_template, request, url_for

import centrais_cred as CENTCRED
import cra21_api as CRA

# QUEM ENTRA. Falar com a CRA é ato de quem responde pela serventia — o balcão
# baixa arquivo pela tela de remessa, que já existe; **aqui se fala direto com
# a Central**, e a operação de consulta pode MARCAR coisa lá dentro.
#
# 21/10/2026 — ORDEM DO OFICIAL: «dar acesso às escreventes operarem todo o
# protesto, em especial operar as API, CRA etc.». Era ("ADMIN", "MANAGER").
# A consulta de autorização continua NÃO marcando como baixada por padrão
# (ver `consultar`), que é o que protegia a Central do clique de olhar.
QUEM_FALA_COM_A_CRA = ("ADMIN", "MANAGER", "USER")

# O QUE VOLTA COMO FRASE, E NÃO COMO HTTP 500. A falta de credencial estoura
# `centrais_cred.CredencialError`, que não é `CraError` — foi assim que a
# tela da CENPROT devolveu 500 na cara do escrevente antes do teste pegar.
RECUSAS_DO_BALCAO = (CRA.CraError, CENTCRED.CredencialError)

# AS OPERAÇÕES QUE ESTA TELA OFERECE, e **só as que têm sentido medido**. As
# dez que dependem de `userDados` ficam de fora até alguém medir o que vai
# nele — elas existem em `cra21_api.OPERACOES` e se alcançam por `chamar()`.
O_QUE_SE_TRAZ: tuple[tuple[str, str, str], ...] = (
    ("pendentes", "Todas as remessas disponíveis",
     "não precisa informar nome nem número; traz todas as pendentes"),
    ("remessa", "Remessa de uma data (mais as pendentes anteriores)",
     "o nome do arquivo, no formato FEBRABAN — ex.: B2370508.261"),
    ("desistencias", "Desistências do dia e as pendentes",
     "o nome começa com DP"),
    ("cancelamentos", "Cancelamentos do dia e os pendentes", "o nome do arquivo"),
    ("autorizacoes", "Autorizações de retirada e de cancelamento",
     "o nome começa com AC ou AD"),
    ("ordem", "Ordem de cancelamento", "o nome do arquivo"),
    ("apresentantes", "A lista de apresentantes", "não precisa de nome"),
)


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura a tela da CRA no app já construído."""

    def ambiente_pedido() -> str:
        """**Sempre PRODUÇÃO, desde 14/10/2026** — ordem do oficial: «tire a
        opção de funcionar na homologação, agora é tudo produção». Até 13/10
        a tela lia `ambiente` do pedido e caía na homologação por padrão; o
        que vier no endereço agora não muda nada."""
        return CENTCRED.PRODUCAO

    @app.route("/protesto/cra/api")
    @roles_required(*QUEM_FALA_COM_A_CRA)
    def protesto_cra_api():
        """O estado da ligação com a CRA, e o que dá para trazer."""
        ambiente = ambiente_pedido()
        return render_template(
            "protesto_cra_api.html",
            ambiente=ambiente,
            fora_de_uso=CENTCRED.fora_de_uso(CENTCRED.CRA),
            tem_credencial=CENTCRED.tem(CENTCRED.CRA, ambiente),
            usuario=CENTCRED.usuario(CENTCRED.CRA, ambiente),
            endereco=CRA.endereco_do_ambiente(ambiente),
            o_que_se_traz=O_QUE_SE_TRAZ,
            operacoes=sorted(CRA.OPERACOES),
            sem_sentido_medido=sorted(CRA.OPERACOES_SEM_SENTIDO_MEDIDO))

    @app.route("/protesto/cra/api/testar", methods=["POST"])
    @roles_required(*QUEM_FALA_COM_A_CRA)
    def protesto_cra_api_testar():
        """Fala com a CRA e diz o que aconteceu. **Não baixa nem envia nada.**"""
        ambiente = ambiente_pedido()
        try:
            # SÓ PRODUÇÃO, E DIRETO (14/10/2026). Até 13/10 a homologação
            # passava pela fila comum das Centrais (marco b, 05/10/2026), que
            # não fala com produção; com a homologação fora da tela, o teste
            # é o `BuscarApresentante` de produção, direto, como já era.
            d = CRA.diagnostico(ambiente)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_cra_api", ambiente=ambiente))
        audit("cra_diagnostico", None, None,
              {"ambiente": ambiente, "ok": d["ok"],
               "fila_id": d.get("fila_id")})
        flash(d["motivo"], "success" if d["ok"] else "danger")
        return redirect(url_for("protesto_cra_api", ambiente=ambiente))

    @app.route("/protesto/cra/api/baixar", methods=["POST"])
    @roles_required(*QUEM_FALA_COM_A_CRA)
    def protesto_cra_api_baixar():
        """Traz o arquivo da CRA e entrega **cru**, como ela mandou.

        **NÃO SE APONTA NADA A PARTIR DAQUI**, e é a decisão de fundo desta
        tela: o formato exato do que a Central devolve não está medido, e
        alimentar o leitor com um palpite apontaria títulos que ninguém
        apresentou. O arquivo baixa; quem o recebe é o escrevente, que o
        confere na tela de remessa que já existe.

        **E BAIXAR MARCA DO LADO DE LÁ.** O manual diz que a `Remessa` traz a
        do dia mais as pendentes; pedir duas vezes não é o mesmo que pedir uma.
        Por isso este botão não é automático e não roda por relógio.
        """
        ambiente = ambiente_pedido()
        qual = str(request.values.get("o_que") or "").strip()
        nome = str(request.values.get("nome") or "").strip()
        com_imagem = str(request.values.get("com_imagem") or "") == "1"
        try:
            texto = _trazer(qual, nome, ambiente, com_imagem=com_imagem)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_cra_api", ambiente=ambiente))
        audit("cra_baixar", None, None,
              {"ambiente": ambiente, "o_que": qual, "nome": nome,
               "tamanho": len(texto)})
        # **O NOME DO ARQUIVO QUE BAIXA DIZ DE ONDE ELE VEIO** — arquivo de
        # homologação com nome de arquivo de produção é o carimbo que mente na
        # pasta de downloads de alguém.
        rotulo = f"cra-{ambiente.lower()}-{qual}-{nome or 'sem-nome'}.txt"
        return Response(
            texto.encode("utf-8"),
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{rotulo}"'})

    @app.route("/protesto/cra/api/consultar", methods=["POST"])
    @roles_required(*QUEM_FALA_COM_A_CRA)
    def protesto_cra_api_consultar():
        """As quatro consultas do contrato. Devolve a resposta crua.

        **UMA DELAS MUDA COISA DO LADO DE LA, e por isso tem caixa propria:**
        o manual diz que consultar autorizacao **marca como baixada salvo se
        se disser que nao**. O padrao aqui e NAO marcar — uma consulta que
        muda o estado da Central nao pode ser o comportamento silencioso de um
        botao de olhar.
        """
        ambiente = ambiente_pedido()
        qual = str(request.values.get("consulta") or "").strip()
        v = request.values
        try:
            if qual == "slip":
                texto = CRA.consultar_slip(
                    v.get("protocolo", ""), v.get("data_protocolo", ""),
                    ambiente)
            elif qual == "autorizacao":
                texto = CRA.consultar_autorizacao(
                    v.get("nome", ""), v.get("protocolo", ""),
                    v.get("data_protocolo", ""), ambiente,
                    marcar_baixado=(v.get("marcar_baixado") == "1"))
            elif qual == "imagem":
                texto = CRA.consultar_imagem(
                    nosso_numero=v.get("nosso_numero", ""),
                    numero_titulo=v.get("numero_titulo", ""),
                    documento_devedor=v.get("documento_devedor", ""),
                    saldo=v.get("saldo", ""), vencimento=v.get("vencimento", ""),
                    remessa_=v.get("remessa", ""), ambiente=ambiente)
            elif qual == "autorizacoes_periodo":
                texto = CRA.autorizacoes_do_periodo(
                    solicitacao_de=v.get("solicitacao_de", ""),
                    solicitacao_ate=v.get("solicitacao_ate", ""),
                    remessa_de=v.get("remessa_de", ""),
                    remessa_ate=v.get("remessa_ate", ""), ambiente=ambiente)
            else:
                raise CRA.CraError(
                    "Escolha o que consultar. As quatro consultas do contrato "
                    "sao o slip, a autorizacao, a imagem de um titulo e as "
                    "autorizacoes de um periodo.")
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_cra_api", ambiente=ambiente))
        audit("cra_consultar", None, None,
              {"ambiente": ambiente, "consulta": qual,
               "marcou_baixado": (qual == "autorizacao"
                                  and v.get("marcar_baixado") == "1"),
               "tamanho": len(texto)})
        return Response(
            texto.encode("utf-8"),
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="cra-{ambiente.lower()}-'
                     f'consulta-{qual}.txt"'})


# `_quem_esta` e `_nota_da_fila` FORAM APAGADAS EM 14/10/2026, e não
# desligadas: só serviam ao teste de homologação pela fila comum das
# Centrais, que saiu da tela com a ordem «agora é tudo produção». Função sem
# chamador é a peça que alguém religa sem saber por que existia.


def _trazer(qual: str, nome: str, ambiente: str, *, com_imagem: bool) -> str:
    """Chama a operação escolhida. **Uma linha por opção, e nenhuma inventada.**"""
    if qual == "remessa":
        return CRA.remessa(nome, ambiente, com_imagem=com_imagem)
    if qual == "pendentes":
        return CRA.remessas_pendentes(nome, ambiente, com_imagem=com_imagem)
    if qual == "desistencias":
        return CRA.desistencias(nome, ambiente)
    if qual == "cancelamentos":
        return CRA.cancelamentos(nome, ambiente, com_imagem=com_imagem)
    if qual == "autorizacoes":
        return CRA.autorizacoes(nome, ambiente, com_imagem=com_imagem)
    if qual == "ordem":
        return CRA.ordem_de_cancelamento(nome, ambiente)
    if qual == "apresentantes":
        return CRA.apresentantes(ambiente)
    raise CRA.CraError(
        "Escolha o que trazer da CRA. As opções são as da lista — e as demais "
        "operações do contrato ainda não têm sentido medido: o manual não diz "
        "o que vai em `userDados`.")
