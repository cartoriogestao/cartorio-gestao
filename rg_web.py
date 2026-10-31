"""
AS TELAS DO TÍTULO APRESENTADO no RCPJ e no RTD.

    «Preciso que o sistema receba o título em protocolo, esteja disponível para
     analisar no visualizador de pdf direto no sistema, disponível para baixar,
     se positiva a qualificação possa imprimir a etiqueta de registro para o
     título apresentado em papel, ou encaminhamento pela ONRTDPJ para os
     eletrônicos.» — o oficial, 03/09/2026

**MÓDULO PRÓPRIO, e não mais um pedaço de `atribuicoes_web`.** Aquele arquivo já
passa de quatro mil e seiscentas linhas e serve as telas das quatro atribuições;
este serve **um caminho** — do protocolo ao registro —, com a sua fila, o seu
visualizador e a sua etiqueta. É a razão pela qual `nucleo_web` e `cenprot_web`
também nasceram à parte.

**O NOME DAS ROTAS COMEÇA COM `rcpj_rtd`, E ISSO NÃO É ESTILO.** A guarda de
módulo do sistema inteiro pergunta a `modulos.modulo_da_tela(request.endpoint)`
de que módulo é a tela, e ela decide pelo prefixo. Rota que fugisse do prefixo
sairia da cor, do menu e do alcance do módulo — e ninguém veria.

**UMA PORTA NO MENU, E AS DUAS ATRIBUIÇÕES NO MESMO LUGAR.** RCPJ e RTD dividem
livro, controlador e protocolo desde o E-Ofício; duas filas separadas fariam o
escrevente escolher a atribuição antes de saber qual é — e quem chega ao balcão
com um papel na mão nem sempre sabe.

**A TELA NÃO REPETE A REGRA DO DOMÍNIO.** Ela só oferece o que cabe na situação;
quem recusa é `rg_titulo`. Repetir a regra nos dois lugares é como os dois
divergem — a tela esconde o botão por educação, o domínio recusa por dever.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import arquivo_visivel as ARQVIS
import atrib_certidao as CE
import ato_selado as AS
import caixa_protocolo as CXP
import centrais_cred as CENTCRED
import etiqueta as ETQ
import livro_nucleo as LN
import modelos_da_casa as MODELOS
import notas_selo as NSELO
import onrtdpj_api as ONR
import rascunho_de_tela as RASC
import rg_registro as RG
import rg_titulo as TIT
import rg_teor_rtdpj as RGTEOR
from bd_nativo import banco
import selo as SELO
import selo_no_papel as SNPAPEL
import selos_emitidos as SEM
from ri_web import data_por_extenso
# O número que a tela mandou (LD13): «abc», «²» e 5.000 dígitos não viram 500.
from seguranca_web import MAIOR_INTEGER, numero_digitado
from serventia import dados as dados_serventia
from storage import safe_component, save_upload

# QUEM ENTRA. O mesmo trio das telas das atribuições — quem lavra ato no
# balcão. `AUDITOR` fica de fora de propósito: ele consulta pela lista.
QUEM_OPERA = ("ADMIN", "MANAGER", "USER")

# QUEM QUALIFICA E QUEM ENCERRA. **Qualificar é ato registral**, e o registro é
# efeito dela — não é do balcão. É a mesma separação da ajuda do Claude e do
# envio às Centrais: consultar abre, decidir não.
QUEM_QUALIFICA = ("ADMIN", "MANAGER")

# O QUE VOLTA COMO FRASE, E NÃO COMO HTTP 500. Erro de regra não é erro de
# programa — a regra da casa, e ela já foi quebrada por mim em cinco rotas de
# uma vez no `cenprot_web`.
# **E AS DA CENTRAL ENTRAM AQUI TAMBEM.** No `cenprot_web` eu esqueci a
# terceira classe e cinco rotas devolveram HTTP 500 ao escrevente que ainda nao
# tinha configurado a senha. Sao quatro agora: as duas de regra da casa, a do
# transporte da Central e a da credencial que falta.
RECUSAS_DO_BALCAO = (TIT.TituloError, RG.RgError, LN.LivroError,
                     CXP.ProtocoloError, ONR.OnrtdpjError,
                     CENTCRED.CredencialError,
                     AS.AtoError)


# OS PAPÉIS DESTAS TELAS SÃO DO CATÁLOGO desde o LF06F (19/10/2026) — a nota
# devolutiva e as duas etiquetas eram templates, e a casa não as alcançava na
# tela de Modelos. O template ficou com a página (estilo, botões, avisos); o
# papel — o que vai para a folha ou para a tira — é montado por `papel_html`.
CHAVE_NOTA = "RCPJ_RTD_NOTA"
CHAVE_ETIQUETA = "RCPJ_RTD_ETIQUETA"
CHAVE_ETIQUETA_EXTERNA = "RCPJ_RTD_ETIQUETA_SELO_EXTERNO"


# O lugar do QR do selo enquanto o ajuste da casa passa pelo filtro (ver
# `papel_html`). Texto sem nada que o filtro escape ou tire.
_MARCA_DO_QR = "@@QR-DO-SELO@@"


def papel_html(modelo: str, contexto: dict, *, chave: str | None = None) -> str:
    """O papel do catálogo montado para ir DENTRO de uma página HTML. Só calcula.

    **COM AUTOESCAPE, COMO O TEMPLATE QUE ELE ERA**: o nome do apresentante, a
    exigência e a natureza são texto livre, e um «<» neles não pode virar
    marcação na folha. No ambiente restrito (`SandboxedEnvironment`), o mesmo
    do resto dos modelos da casa.

    **O AJUSTE DA CASA SAI SEM O QUE EXECUTA** (`html_sem_script`, o filtro do
    LS02). Enquanto era template do programa, ninguém escrevia nesta página;
    papel do catálogo, ela é gravada na tela de Modelos — que aceita o papel
    USER — e abre no navegador de quem imprime: um `<script>` no modelo, ou um
    `|safe` no meio dele, rodaria na sessão do oficial. O PADRÃO do programa
    (`chave` dada e o modelo igual a ele) sai como saía, byte a byte. O QR do
    selo é SVG, que o filtro tira inteiro: no ajuste, ele entra DEPOIS do
    filtro, no lugar de uma marca — é o sistema que o desenha, e não a casa.
    """
    from jinja2.sandbox import SandboxedEnvironment
    ambiente = SandboxedEnvironment(autoescape=True)
    if chave is not None and modelo == MODELOS.padrao_de(chave):
        return ambiente.from_string(modelo).render(**contexto)
    import html_sem_script as HSS
    tira = contexto.get("e")
    qr = str(tira.get("qr") or "") if isinstance(tira, dict) else ""
    if qr:
        contexto = {**contexto, "e": {**tira, "qr": _MARCA_DO_QR}}
    papel = HSS.limpar(ambiente.from_string(modelo).render(**contexto))
    return papel.replace(_MARCA_DO_QR, qr) if qr else papel


# O QUE A TELA DE MODELOS CONFERE ANTES DE GRAVAR estes papéis (LF06F). O
# boneco geral não tem `t`, `q` nem `e`, e recusaria todo ajuste que usasse um
# claro — o papel ficaria editável só no nome. Aqui é a MESMA montagem da
# tela (`papel_html`), com um caso de exemplo, sem dado de ninguém.
_SERVENTIA_DE_EXEMPLO = {"unit_name": "SERVENTIA DE EXEMPLO", "ri_cns": "000000",
                         "ri_cidade": "Cidade Exemplo", "ri_uf": "UF"}
_TIRA_DE_EXEMPLO = {"cartorio": "SERVENTIA DE EXEMPLO", "tipo": "REGISTRO",
                    "serie": "TD_B", "livro": 1, "folha": 1, "numero": 1,
                    "titulo": "RCPJ E RTD", "detalhe": "Registro de exemplo.",
                    "data": "08/09/2026", "selo": "SELO000000EXEMPLO01",
                    "valores": "", "qr": "", "oficial": "FULANO DE EXEMPLO"}
EXEMPLOS_DE_PAPEL = {
    CHAVE_NOTA: lambda: {
        "t": {"id": 1, "numero": 1, "data_apresentacao": "2026-09-03",
              "apresentante": "ASSOCIAÇÃO DE EXEMPLO"},
        "q": {"exigencias": "Exigência de exemplo.", "prazo_ate": "2026-09-20",
              "data_qualificacao": "2026-09-08"},
        "sv": _SERVENTIA_DE_EXEMPLO, "data_extenso": "8 de setembro de 2026",
        "oficial": "FULANO DE EXEMPLO", "funcao": "Escrevente",
        "nome_da_atribuicao": "RTD — Registro de Títulos e Documentos",
        "apresentado_em": "03/09/2026", "qualificado_em": "08/09/2026",
        "prazo_ate": "20/09/2026", "fmt_date": str},
    CHAVE_ETIQUETA: lambda: {"e": _TIRA_DE_EXEMPLO, "m": {}, "vez": 1},
    CHAVE_ETIQUETA_EXTERNA: lambda: {"e": _TIRA_DE_EXEMPLO, "m": {},
                                     "serventia": _SERVENTIA_DE_EXEMPLO},
}


def conferir_papel_html(chave: str, corpo: str) -> str:
    """O papel em HTML monta? Devolve o erro, ou ``""``. Só calcula."""
    try:
        papel_html(corpo, EXEMPLOS_DE_PAPEL[chave]())
    except Exception as erro:                      # noqa: BLE001 — é o recado
        return f"{type(erro).__name__}: {erro}"
    return ""


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas do título do RCPJ/RTD no app já construído."""

    # UM RELÓGIO SÓ PARA O MÓDULO INTEIRO — `db.now()`, o mesmo que grava o
    # resto da casa. Ler a hora de dois lugares faria o título e o lugar dele no
    # Livro de Protocolo discordarem por um segundo.
    def agora() -> str:
        return db.now()

    def hoje() -> str:
        return agora()[:10]

    # Os conferidores dos papéis do RCPJ/RTD que saíram do código (LF06F).
    conferidores = app.extensions.setdefault("conferidores_de_modelo", {})
    for _chave in EXEMPLOS_DE_PAPEL:
        conferidores[_chave] = (
            lambda corpo, _k=_chave: conferir_papel_html(_k, corpo))
    conferidores[CE.CHAVE_PAPEL_POR_TEXTO] = CE.conferir_papel_por_texto
    conferidores[CE.CHAVE_SO_AVERBACOES] = CE.conferir_so_averbacoes
    conferidores[CE.CHAVE_NEGATIVA] = CE.conferir_negativa      # LD05
    conferidores[CE.CHAVE_BREVE_RELATO] = CE.conferir_breve_relato  # LD05
    conferidores[RGTEOR.CHAVE_MOLDURA] = RGTEOR.conferir_moldura
    # os termos do cancelamento (LD05, 21/10/2026), pela montagem do termo
    termos_do_cancelamento = tuple(
        chave for (_, tipo), chave in RGTEOR.CHAVES_MODELO.items()
        if tipo == RGTEOR.TIPO_CANCELAMENTO)
    for _chave in termos_do_cancelamento:
        conferidores[_chave] = RGTEOR.conferir_teor
    # e quem grava (`modelos_elementos.salvar`) confere com a mesma régua
    import modelos_elementos as ELEM
    for _chave in (*EXEMPLOS_DE_PAPEL, CE.CHAVE_PAPEL_POR_TEXTO,
                   CE.CHAVE_SO_AVERBACOES, RGTEOR.CHAVE_MOLDURA,
                   CE.CHAVE_NEGATIVA, CE.CHAVE_BREVE_RELATO,
                   *termos_do_cancelamento):
        ELEM.CONFERIDORES[_chave] = conferidores[_chave]

    def hoje_extenso() -> str:
        return data_por_extenso(date.fromisoformat(hoje()))

    def sv() -> dict:
        return dados_serventia(db.get_settings)

    usuario_nome = app.extensions["usuario_nome"]
    usuario_funcao = app.extensions["usuario_funcao"]
    usuario_id_do_sistema = app.extensions["usuario_id"]
    pasta_dos_arquivos = app.extensions["archive_root"]

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()


    def _caixa_aberto(con) -> dict | None:
        """O caixa aberto de quem está usando o sistema. Só LÊ.

        Espelho enxuto do de `atribuicoes_web`: este módulo é próprio, e
        importar helper de lá amarraria as telas do título ao arquivo das
        quatro atribuições — o contrário da razão de `rg_web` existir.
        """
        return banco(con).um(
            """SELECT * FROM cx_caixas
                WHERE operador_nome=%s AND situacao='ABERTO'
                ORDER BY data DESC, id LIMIT 1""", (usuario_nome(),))

    def _protocolos_abertos(con) -> list[dict]:
        """Os protocolos em aberto, para amarrar a cobrança a um deles. Só LÊ."""
        return banco(con).ler(
            """SELECT id, numero, interessado FROM cx_protocolos
                WHERE situacao NOT IN ('ENTREGUE','CANCELADO')
                ORDER BY id DESC LIMIT 60""")

    def _para_cobrar(con) -> dict:
        """Receita + caixa + protocolos do REGISTRO do RCPJ/RTD. Só LÊ.

        O caminho é o medido em `ato_selado.CAMINHO_DO_ATO` para
        (`rg_atos`, `REGISTRO`) — a tela não inventa código TJ.
        """
        caminho = AS.caminho_do_ato("rg_atos", "REGISTRO")
        receita = AS.receita_de_custas(con, caminho) if caminho else None
        return {"receita": receita, "caixa": _caixa_aberto(con),
                "protocolos": _protocolos_abertos(con)}

    def _sigla_da_atribuicao(codigo: int) -> str:
        """A sigla curta que o selo grava — 3→RCPJ, 4→RTD. Só calcula.

        Não hardcode «RTD»: o mesmo formulário serve as duas atribuições, e
        selo gravado com a sigla errada é o ato falando mentira na conferência.
        """
        return "RCPJ" if int(codigo) == TIT.RCPJ else "RTD"


    def _itens_para_selar(con) -> list[str]:
        """Itens da tabela de emolumentos que viram selo. Só LÊ.

        Mesma regra de `atribuicoes_web._itens_para_selar`: origem no
        protocolo (um selo por unidade); sem protocolo, o que foi marcado
        para cobrar.

        **SÓ OS ITENS DESTE ATO, E SÓ O QUE AINDA SOBRA** (LD05, 21/10/2026).
        Eram todos os itens do protocolo do título, gastos ou não: no
        protocolo único que o oficial pediu (11/09/2026), o registro da
        notificação selava também a diligência e a certidão, e gastava as
        unidades que o cliente pagou por elas — e o item que outro ato já
        tinha gasto era pedido de novo (CN-MA art. 130: um selo por ato).
        Agora, como na ficha do registro: os itens marcados na tela
        (`protocolo_item_id`); sem marcação, os do registro
        (`rg_registro.item_e_do_registro`). Em qualquer caso, pelo saldo
        (`caixa_protocolo.itens_disponiveis`) — a régua do caixa.
        """
        bd = banco(con)
        # O NÚMERO QUE NÃO É NÚMERO (LD13). Isto roda DEPOIS de o registro
        # estar lavrado, e a tela de erro escondia que ele tinha saído. O
        # protocolo que não é número é nenhum; o item marcado que passa pelo
        # `isdigit()` e não é id do banco vira -1, o id de ninguém — o «não
        # achei» que o de 30 dígitos já dava. Tirá-lo deixaria a lista vazia,
        # e vazia aqui quer dizer «os itens do registro».
        protocolo = numero_digitado(_campo("protocolo_id"))
        if protocolo is not None:
            marcados = {numero_digitado(x) or -1
                        for x in request.form.getlist("protocolo_item_id")
                        if str(x).strip().isdigit()}
            itens: list[str] = []
            for r in CXP.itens_disponiveis(bd, protocolo):
                if marcados and int(r["id"]) not in marcados:
                    continue
                if not marcados and not RG.item_e_do_registro(r["codigo_ato"]):
                    continue
                itens += [str(r["codigo_ato"]).strip()] * int(r["saldo"])
            if itens:
                return itens
        servicos = [n for n in (numero_digitado(x)
                                for x in request.form.getlist("cobrar"))
                    if n is not None]
        if not servicos:
            return []
        lugares = ",".join(["%s"] * len(servicos))
        return [r["codigo_tj"] for r in bd.ler(
            f"""SELECT codigo_tj FROM cx_servicos WHERE codigo IN ({lugares})
                 AND codigo_tj IS NOT NULL AND TRIM(codigo_tj) <> ''
               ORDER BY codigo""",
            servicos)]

    def _selar_o_ato_automatico(ato_id: int, tipo: str, atribuicao_sigla: str,
                                serie: str, ja_dito: str,
                                gratuidade: str = "") -> str:
        """Pede o selo ao aparelho DEPOIS do ato. FALA COM A REDE.

        Espelho do `_selar_o_ato` / `_selar_o_rtdpj` de `atribuicoes_web`: se
        o escrevente já digitou selo, não pede outro; se a máquina cair, o
        ato fica sem selo — nunca com número inventado.

        `gratuidade` é o fundamento do ato gratuito (LD05, 21/10/2026): o selo
        sai ISENTO, com o motivo dentro (CN-MA art. 133), e a trava do selo
        pago o deixa passar sem protocolo pago — a regra do oficial de
        19/10/2026, «a gratuidade NÃO trava»; o comprovante é cobrado depois,
        da pessoa (`gratuidade_comprovante`). Sem item no protocolo — o ato
        gratuito não passa pelo caixa —, o item é o do livro
        (`rg_registro.ITEM_DO_REGISTRO_POR_SERIE`), ou o que a tela disser.
        """
        if ja_dito:
            return ja_dito
        with db.connect() as con:
            itens = _itens_para_selar(con)
        if not itens and gratuidade:
            item = (_campo("item_gratuito")
                    or RG.ITEM_DO_REGISTRO_POR_SERIE.get(
                        str(serie or "").strip().upper(), ""))
            itens = [item] if item else []
        if not itens:
            return (" O ato foi lavrado SEM SELO: o selo sai pelos itens da "
                    "tabela de emolumentos, e este ato não tem protocolo nem "
                    "item marcado para cobrança.")
        saiu, faltou = [], []
        selos_por_codigo: list[tuple[str, str]] = []
        for codigo_tj in itens:
            try:
                with db.connect() as con:
                    bd = banco(con)
                    linha = bd.um(
                        """SELECT a.*, r.serie, r.natureza, r.requerente_nome,
                                  r.requerente_documento,
                                  r.numero AS registro_numero, r.titulo_id,
                                  (SELECT numero FROM nu_livros
                                    WHERE id = a.livro_id) AS livro_numero
                             FROM rg_atos a
                             JOIN rg_registros r ON r.id = a.registro_id
                            WHERE a.id=%s""", (int(ato_id),))
                    protocolo = None
                    pid = numero_digitado(_campo("protocolo_id"))   # LD13
                    if pid is not None:
                        ach = bd.um(
                            "SELECT numero FROM cx_protocolos WHERE id=%s",
                            (pid,))
                        if ach and ach["numero"]:
                            protocolo = str(ach["numero"]).strip()
                    if not protocolo and linha and linha["titulo_id"]:
                        tit = bd.um(
                            "SELECT numero FROM rg_titulos WHERE id=%s",
                            (int(linha["titulo_id"]),))
                        if tit and tit["numero"] is not None:
                            protocolo = str(tit["numero"]).strip()
                if not linha:
                    raise AS.AtoError("Não achei o ato para montar o selo.")
                serie_u = str(serie or linha["serie"] or "").strip().upper()
                caminho = AS.caminho_do_rtdpj(tipo, serie_u)
                if (caminho != AS.CAMINHO_RTDPJ_GERAL
                        and not str(protocolo or "").strip()):
                    caminho = AS.CAMINHO_RTDPJ_GERAL
                versao = AS.versao_da_tabela_de_custas(
                    caminho, db.get_setting("selo_tabela_custas_em", ""))
                if not versao:
                    raise AS.AtoError(
                        "Falta dizer de que data é a tabela de custas em "
                        "vigor, em Administrativo → Configurações.")
                partes = []
                nome = (linha["requerente_nome"] or "").strip()
                if nome:
                    partes.append({
                        "nome": nome,
                        "documento": linha["requerente_documento"] or ""})
                envelope = AS.envelope_do_rtdpj(
                    caminho=caminho, codigo_tj=codigo_tj,
                    escrevente=usuario_nome(), versao_tabela=versao,
                    partes=partes,
                    natureza_descricao=linha["natureza"] or tipo,
                    livro=linha["livro_numero"] or "",
                    folha=linha["folha"], protocolo=protocolo,
                    registro_averbacao=(linha["numero_ordem"]
                                        if linha["numero_ordem"] is not None
                                        else linha["registro_numero"]),
                    isento=bool(gratuidade), motivo_isencao=gratuidade)
            except (AS.AtoError, sqlite3.Error) as erro:
                faltou.append(str(erro))
                continue
            r = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]), tabela="rg_atos",
                ato_id=ato_id, tipo=tipo, atribuicao=atribuicao_sigla,
                agora=agora(), cns=sv().get("ri_cns"),
                usuario=usuario_nome(), especie=serie_u, dados=envelope,
                caminho=caminho,
                referencia=f"rg_atos:{int(ato_id)}:{codigo_tj}")
            (saiu if r["selado"] else faltou).append(
                r["numero"] if r["selado"] else r["motivo"])
            if r["selado"]:
                selos_por_codigo.append((str(codigo_tj), r["numero"]))
        # CADA `selar_o_ato_lavrado` GRAVA A SUA RESPOSTA EM `rg_atos.selo`, e
        # o último a sair ganhava — com a prenotação (15.1) e o arquivamento
        # (15.22) no protocolo, a coluna ficava com qualquer um dos dois, menos
        # o do registro. É a mesma correção de `atribuicoes_web._selar_o_rtdpj`
        # (09/10/2026), pela mesma régua: `rg_registro.papel_dos_selos`.
        principal, arquivamento = RG.papel_dos_selos(selos_por_codigo)
        if principal or arquivamento:
            with db.transaction() as con:
                bd = banco(con)
                if principal:
                    bd.escrever("UPDATE rg_atos SET selo=%s WHERE id=%s",
                                (principal, int(ato_id)))
                if arquivamento:
                    bd.escrever(
                        "UPDATE rg_atos SET selo_arquivamento=%s WHERE id=%s",
                        (arquivamento, int(ato_id)))
        if not saiu:
            return f" O ato foi lavrado SEM SELO: {faltou[0] if faltou else ''}"
        recado = f" {len(saiu)} selo(s): {', '.join(saiu)}."
        if faltou:
            recado += f" ({len(faltou)} item(ns) sem selo: {faltou[0]})"
        return recado

    def _selar_se_pedido(con, ato_id: int, atribuicao_sigla: str) -> str:
        """Grava o selo que o escrevente digitou, se digitou. ESCREVE.

        Opcional de propósito: o selador é máquina da rede local e cai. Ato
        sem selo entra e aparece em `atos_sem_selo` — melhor que balcão
        parado, e melhor que ato lavrado com selo inventado.
        """
        numero = _campo("selo")
        if not numero:
            return ""
        AS.registrar_selo_obtido_a_mao(
            con, numero, tabela="rg_atos", ato_id=ato_id,
            atribuicao=atribuicao_sigla, agora=agora(),
            cns=sv().get("ri_cns"), usuario=usuario_nome())
        return f" Selo {numero} gravado."

    def _cobrar_se_pedido(con, ato_id: int) -> str:
        """Lança no caixa os itens que o operador marcou. ESCREVE.

        Sem caixa aberto não se cobra — lançamento sem caixa não aparece na
        gaveta de ninguém. A frase é a mesma de `atribuicoes_web`, porque o
        balcão ouve a mesma regra nas duas telas.
        """
        # o que não é número não foi marcado (LD13 — «abc» era a tela de erro
        # no meio do registro)
        servicos = [n for n in (numero_digitado(s)
                                for s in request.form.getlist("cobrar"))
                    if n is not None]
        if not servicos:
            return ""
        caixa = _caixa_aberto(con)
        if not caixa:
            raise AS.AtoError(
                "Você não tem caixa aberto, e sem caixa o lançamento não "
                "aparece na conferência do dia. Abra o caixa em "
                "Administrativo → Caixa e lance o ato de novo — ou lance sem "
                "marcar cobrança, e cobre depois.")
        # o protocolo que não é número é nenhum; o id que passa do `integer`
        # não é de protocolo nenhum, e estourava a gravação (LD13)
        protocolo = numero_digitado(_campo("protocolo_id"), maximo=MAIOR_INTEGER)
        total = 0
        for servico in servicos:
            r = AS.cobrar(con, tabela="rg_atos", ato_id=ato_id,
                          servico=servico, agora=agora(),
                          hoje=hoje(),
                          hora=agora()[11:16],
                          caixa_id=int(caixa["id"]),
                          protocolo_id=protocolo,
                          pagador=_campo("pagador") or None,
                          forma_pagamento=_campo("forma_pagamento") or None,
                          descricao="REGISTRO — rg_atos",
                          usuario_id=None)
            total += r["total_centavos"]
        from caixa_schema import reais
        return f" Lançado no caixa: R$ {reais(total)}."

    def _atribuicao_pedida(do_rascunho=None) -> int:
        """Qual atribuição a tela está olhando.

        **`request.values`, e não `request.form`** — o filtro chega por query
        string e o redirecionamento depois de gravar também. Este defeito
        apareceu duas vezes na mesma noite no IBGE e na FUNAI, espelhado.

        **O rascunho reaberto diz a dele**: a lista o abre sem dizer a atribuição,
        e o título guardado do RCPJ abriria como se fosse do RTD.
        """
        bruto = str(do_rascunho or request.values.get("atribuicao") or "").strip()
        try:
            codigo = int(bruto)
        except (TypeError, ValueError):
            return TIT.RTD
        return codigo if codigo in TIT.ATRIBUICOES else TIT.RTD

    def _series_da(atribuicao: int) -> list[dict]:
        """Os livros daquela atribuição, para a caixa de seleção. Só calcula."""
        return [{"codigo": c, "nome": LN.serie(c).nome}
                for c in RG.SERIES_CONHECIDAS
                if LN.serie(c).atribuicao == int(atribuicao)]

    def _anexos(con, titulo_id: int) -> list[dict]:
        """Os arquivos daquele título, do mais novo para o mais velho. Só LÊ.

        Lê a MESMA tabela `attachments` do expediente, da tarefa, da prenotação
        do RI e do termo do RCPN. **Não se cria a quinta** — `entity_type` é o
        que distingue, e uma tabela nova seria o mesmo papel em dois lugares.
        """
        return banco(con).ler(
            """SELECT a.*, u.full_name AS enviado_por_nome
                 FROM attachments a LEFT JOIN users u ON u.id = a.uploaded_by
                WHERE a.entity_type = %s AND a.entity_id = %s
                ORDER BY a.id DESC""", (TIT.ANEXO_DO_TITULO, int(titulo_id)))

    def _titulo_ou_lista(con, titulo_id: int) -> dict | None:
        t = TIT.um(con, titulo_id)
        if not t:
            flash("Esse título não existe.", "danger")
        return t

    # ------------------------------------------------------- a fila do dia

    @app.route("/rcpj-rtd/titulos")
    @login_required
    def rcpj_rtd_titulos():
        """Os títulos apresentados, e em que ponto cada um está.

        **A LISTA NÃO JULGA PRAZO**, e é a mesma regra do roteiro do Protesto:
        um zero aqui pode ser «hoje não veio nada» ou «ainda não lancei», e o
        sistema não tem como saber qual. Ela conta e mostra a data.
        """
        atribuicao = _atribuicao_pedida()
        situacao = str(request.values.get("situacao") or "").strip().upper()
        if situacao not in TIT.SITUACOES:
            situacao = ""
        with db.connect() as con:
            fila = TIT.fila(con, atribuicao=atribuicao,
                            situacao=situacao or None)
            quadro = TIT.painel(con)
        return render_template(
            "rcpj_rtd_titulos.html", fila=fila, quadro=quadro,
            atribuicao=atribuicao, situacao=situacao,
            nome_da_atribuicao=TIT.NOME_DA_ATRIBUICAO[atribuicao],
            atribuicoes=[{"codigo": c, "nome": TIT.NOME_DA_ATRIBUICAO[c]}
                         for c in TIT.ATRIBUICOES],
            situacoes=TIT.SITUACOES, formas=TIT.FORMAS, fmt_date=fmt_date)

    # -------------------------------------------------- receber o título

    @app.route("/rcpj-rtd/titulos/novo", methods=["GET", "POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_titulo_novo():
        """Recebe o título e o lança no Livro de Protocolo. ESCREVE.

        **O TÍTULO ENTRA ANTES DE QUALQUER EXIGÊNCIA** — Lei 6.015/1973, art.
        12. A natureza, o livro pretendido e até o apresentante podem faltar; o
        protocolo se lança do mesmo jeito, porque é ele que marca a ordem de
        chegada, e a ordem de chegada é o que o título perde se esperar.
        """
        form, rascunho_id = RASC.para_a_tela(
            db, "rcpj_rtd_titulo_novo", "Este rascunho não é de um título do RCPJ ou do RTD.")
        atribuicao = _atribuicao_pedida(
            form.get("atribuicao") if rascunho_id and request.method == "GET" else None)

        def tela():
            return render_template(
                "rcpj_rtd_titulo_novo.html", form=form, rascunho_id=rascunho_id,
                atribuicao=atribuicao,
                nome_da_atribuicao=TIT.NOME_DA_ATRIBUICAO[atribuicao],
                atribuicoes=[{"codigo": c, "nome": TIT.NOME_DA_ATRIBUICAO[c]}
                             for c in TIT.ATRIBUICOES],
                series=_series_da(atribuicao), formas=TIT.FORMAS, hoje=hoje())

        if request.method != "POST":
            return tela()

        try:
            with db.transaction() as con:
                protocolo_geral = CXP.abrir(
                    con,
                    data_abertura=_campo("data_apresentacao") or hoje(),
                    hora=_campo("hora") or agora()[11:19], agora=agora(),
                    atribuicao=_sigla_da_atribuicao(atribuicao),
                    interessado=_campo("apresentante"),
                    interessado_documento=_campo("apresentante_documento"),
                    telefone=_campo("telefone"), email=_campo("email"),
                    assunto=_campo("natureza") or "Título apresentado",
                    observacao=_campo("observacao"),
                    documento_numero=_campo("apresentante_documento"),
                    documento_descricao=_campo("natureza"),
                    criado_por=usuario_id_do_sistema())
                feito = TIT.receber(
                    con, atribuicao=atribuicao, sv=sv(), agora=agora(),
                    data_extenso=hoje_extenso(),
                    data_apresentacao=_campo("data_apresentacao") or hoje(),
                    hora=_campo("hora") or agora()[11:19],
                    apresentante=_campo("apresentante"),
                    apresentante_documento=_campo("apresentante_documento"),
                    telefone=_campo("telefone"), email=_campo("email"),
                    natureza=_campo("natureza"), serie=_campo("serie"),
                    valor_declarado=_campo("valor_declarado"),
                    vias=_campo("vias") or 1, forma=_campo("forma") or TIT.PAPEL,
                    observacao=_campo("observacao"),
                    protocolo_geral_id=protocolo_geral["protocolo_id"],
                    usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return tela()
        except ValueError as erro:
            # `vias` digitado como texto chega aqui. Erro de digitação não é
            # erro de programa.
            flash(f"Confira os campos numéricos: {erro}", "danger")
            return tela()

        audit("RG_TITULO_RECEBIDO", "rg_titulos", feito["titulo_id"],
              {"atribuicao": atribuicao, "protocolo": feito.get("numero_ordem")})
        flash(f"Atendimento {protocolo_geral['numero']}; título recebido sob "
              f"o protocolo n. {feito.get('numero_ordem')}, "
              f"no Livro de Protocolo n. {feito.get('livro_numero')}, "
              f"fl. {feito.get('rotulo')}. Anexe agora o arquivo do título.",
              "success")
        return redirect(url_for("rcpj_rtd_titulo",
                                titulo_id=feito["titulo_id"]))

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/editar", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_titulo_editar(titulo_id: int):
        """Completa os dados que puderam faltar na apresentação. ESCREVE."""
        voltar = redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        try:
            with db.transaction() as con:
                feito = TIT.atualizar(
                    con, titulo_id,
                    apresentante=_campo("apresentante"),
                    apresentante_documento=_campo("apresentante_documento"),
                    telefone=_campo("telefone"), email=_campo("email"),
                    natureza=_campo("natureza"), serie=_campo("serie"),
                    valor_declarado=_campo("valor_declarado"),
                    vias=_campo("vias") or 1,
                    forma=_campo("forma") or TIT.PAPEL,
                    observacao=_campo("observacao"))
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return voltar
        audit("RG_TITULO_EDITADO", "rg_titulos", titulo_id,
              {"serie": feito["serie"], "forma": feito["forma"]})
        flash("Dados do título atualizados; o protocolo geral foi mantido "
              "sincronizado.", "success")
        return voltar

    # --------------------------------------------------------- a ficha

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>")
    @login_required
    def rcpj_rtd_titulo(titulo_id: int):
        """A ficha do título: o papel à vista, a decisão e o que saiu dela.

        **É AQUI QUE O TÍTULO SE LÊ.** O pedido do oficial foi «analisar no
        visualizador de pdf direto no sistema» — o arquivo abre nesta tela, ao
        lado dos campos, e não noutra. Quem qualifica tem o papel na mão e a
        decisão em branco na frente; ir a outra tela buscar o documento é largar
        o que se está decidindo. É o relato #25, na atribuição vizinha.
        """
        receita = caixa = protocolos = None
        protocolo_geral_id = None
        protocolo_geral = None
        with db.connect() as con:
            titulo = _titulo_ou_lista(con, titulo_id)
            if not titulo:
                return redirect(url_for("rcpj_rtd_titulos"))
            anexos = _anexos(con, titulo_id)
            qualificacoes = TIT.qualificacoes_de(con, titulo_id)
            encaminhamentos = TIT.encaminhamentos_de(con, titulo_id)
            protocolo_central = TIT.protocolo_na_central(con, titulo_id)
            registro = atos = None
            if titulo["registro_id"]:
                registro = RG.registro(con, int(titulo["registro_id"]))
                atos = [dict(a) for a in RG.atos_do(con,
                                                    int(titulo["registro_id"]))]
            # SELO E CUSTAS SÓ QUANDO DÁ PARA REGISTRAR — a ficha QUALIFICADA
            # é a que oferece o formulário. Pedir receita nas outras situações
            # seria cálculo à toa.
            receita = caixa = protocolos = None
            para_concluir = []
            if titulo and titulo["situacao"] == TIT.QUALIFICADO:
                cob = _para_cobrar(con)
                receita, caixa, protocolos = (cob["receita"], cob["caixa"],
                                             cob["protocolos"])
                # O TÍTULO QUE VIROU AVERBAÇÃO num registro que já existia —
                # a saída que faltava (09/10/2026, título n. 1 do RCPJ).
                para_concluir = TIT.atos_para_concluir(con, titulo_id)
            protocolo_geral_id = (
                int(titulo["protocolo_geral_id"])
                if titulo and titulo.get("protocolo_geral_id") else None)
            if protocolo_geral_id:
                protocolo_geral = banco(con).um(
                    "SELECT * FROM cx_protocolos WHERE id=%s",
                    (protocolo_geral_id,))
            # OS ITENS DO PROTOCOLO DO TÍTULO, PARA MARCAR OS DO REGISTRO (LD05,
            # 21/10/2026) — como a ficha do registro já fazia. Vêm marcados os
            # do registro (`rg_registro.item_e_do_registro`); a diligência, a
            # certidão e a averbação do mesmo atendimento ficam desmarcadas,
            # para o ato delas. Só os que ainda têm saldo.
            itens_do_protocolo = []
            if titulo["situacao"] == TIT.QUALIFICADO and protocolo_geral_id:
                itens_do_protocolo = [
                    r | {"marcado": RG.item_e_do_registro(r["codigo_ato"])}
                    for r in CXP.itens_disponiveis(con, protocolo_geral_id)]

        # AS NOTAS QUE A CENTRAL GUARDA — e a chamada de rede vem **DEPOIS de a
        # conexão fechar**, que é a regra da casa: quem fala com fora não segura
        # conexão de banco.
        #
        #   **A FALHA NÃO DERRUBA A FICHA.** Se a Central estiver fora do ar,
        #   quem qualifica continua precisando ver o título — e a lista vazia
        #   diria «não há nota», que é afirmação. O aviso aparece no lugar.
        tem_token = ONR.tem_credencial()
        notas_da_central, falha_da_central = [], ""
        if protocolo_central and tem_token:
            try:
                notas_da_central = ONR.notas_devolutivas(protocolo_central)
            except RECUSAS_DO_BALCAO as erro:
                falha_da_central = str(erro)


        # O ARQUIVO QUE ABRE PRIMEIRO É O MAIS RECENTE QUE O NAVEGADOR DESENHA.
        # Sem isto, um título com o PDF e depois um `.docx` de anotação abriria
        # a tela com o quadro vazio, porque o `.docx` é o mais novo.
        para_ver = next((a for a in anexos
                         if ARQVIS.abre_na_tela(a["original_name"])), None)
        for a in atos or []:
            a["lista_presenca_texto"] = RG.texto_da_lista_presenca(
                a.get("declaracoes"))
        return render_template(
            "rcpj_rtd_titulo.html", t=titulo, anexos=anexos, para_ver=para_ver,
            qualificacoes=qualificacoes, encaminhamentos=encaminhamentos,
            registro=dict(registro) if registro else None, atos=atos or [],
            para_concluir=para_concluir,
            series=_series_da(int(titulo["atribuicao"])),
            nome_da_atribuicao=TIT.NOME_DA_ATRIBUICAO[int(titulo["atribuicao"])],
            situacoes=TIT.SITUACOES, formas=TIT.FORMAS,
            resultados=TIT.RESULTADOS, sentidos=TIT.SENTIDOS,
            protocolo_central=protocolo_central,
            tem_token_da_central=tem_token,
            notas_da_central=notas_da_central,
            falha_da_central=falha_da_central,
            abre_na_tela=ARQVIS.abre_na_tela, e_pdf=ARQVIS.e_pdf,
            pode_qualificar=titulo["situacao"] not in TIT.SITUACOES_TERMINAIS,
            receita=receita, caixa=caixa, protocolos=protocolos,
            protocolo_geral_id=protocolo_geral_id,
            protocolo_geral=protocolo_geral,
            itens_do_protocolo=itens_do_protocolo,
            item_gratuito=RG.ITEM_DO_REGISTRO_POR_SERIE.get(
                str(titulo.get("serie") or "").upper(), ""),
            # os quadros das declarações do termo, por livro (LD09)
            declaracoes_do_termo=RG.DECLARACOES_POR_SERIE,
            enquadramento_sugerido=RG.sugerir_enquadramento(
                titulo.get("natureza")),
            rotulos_enquadramento=RG.ROTULO_DO_ENQUADRAMENTO,
            sugestao_lista=(RG.FRASE_DA_EXIGENCIA_LISTA
                            if int(titulo["atribuicao"]) == TIT.RCPJ
                            and RG.sugerir_enquadramento(titulo.get("natureza"))
                            else ""),
            fmt_date=fmt_date)

    # ------------------------------------------- o arquivo do título

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/arquivo", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_titulo_arquivo(titulo_id: int):
        """Anexa o arquivo do título apresentado. ESCREVE.

        **O E-OFÍCIO NÃO TINHA ONDE GUARDAR ISTO**, e é a maior lacuna que este
        módulo fecha. Medido em 03/09/2026: as 155 imagens de `tbTD_Img` estão
        amarradas ao REGISTRO, e são a digitalização do livro **depois** do ato;
        as duas colunas do documento do apresentante — `strPet` e `strPetImg` —
        estão vazias em **72 de 72**. O título como entrou não era guardado.

        **E O ARQUIVO VAI PARA A PASTA DA CASA.** No E-Ofício os caminhos de
        `tbTD_Img` apontam para `\\\\servidor\\C11\\RTD_RPJ\\` numas e para
        `C:\\Users\\<usuario>\\Desktop\\` noutras — a Área de Trabalho de alguém.
        Aqui é `archive_root`, que é a mesma de todos os anexos da casa e a
        única que o backup alcança.
        """
        voltar = redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        with db.connect() as con:
            titulo = _titulo_ou_lista(con, titulo_id)
        if not titulo:
            return redirect(url_for("rcpj_rtd_titulos"))
        arquivo = request.files.get("arquivo")
        if not arquivo or not arquivo.filename:
            flash("Escolha o arquivo do título — o PDF ou a digitalização.",
                  "danger")
            return voltar
        destino = (pasta_dos_arquivos() / "RCPJ_RTD" / "Titulos"
                   / safe_component(str(titulo["atribuicao"])))
        info = save_upload(arquivo, destino)
        anexo = db.add_attachment(
            TIT.ANEXO_DO_TITULO, titulo_id, info, usuario_id_do_sistema(),
            request.form.get("descricao") or "Título apresentado")
        audit("RG_TITULO_ARQUIVO", "rg_titulos", titulo_id,
              {"anexo": anexo, "sha256": info["sha256"]})
        flash("Arquivo anexado ao título.", "success")
        return voltar

    # ------------------------------------------------------ qualificar

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/qualificar", methods=["POST"])
    @roles_required(*QUEM_QUALIFICA)
    def rcpj_rtd_titulo_qualificar(titulo_id: int):
        """Decide sobre o título: positiva, ou negativa com exigências.

        **A QUALIFICAÇÃO NÃO REGISTRA.** Ela diz que o título pode ser
        registrado; quem toma o número do livro é o botão seguinte. Juntar as
        duas faria um clique valer por um ato definitivo — a mesma razão pela
        qual o Protesto separa cadastrar de apontar.
        """
        voltar = redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        try:
            with db.transaction() as con:
                titulo = TIT.um(con, titulo_id)
                exigencias = _campo("exigencias")
                if titulo and int(titulo["atribuicao"]) == TIT.RCPJ:
                    exigencias = RG.completar_exigencia_com_lista(
                        exigencias, titulo.get("natureza"))
                feito = TIT.qualificar(
                    con, titulo_id, resultado=_campo("resultado"),
                    agora=agora(), fundamentacao=_campo("fundamentacao"),
                    exigencias=exigencias,
                    prazo_ate=_campo("prazo_ate"),
                    data_qualificacao=_campo("data_qualificacao") or hoje(),
                    qualificada_por=usuario_nome(), usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return voltar
        audit("RG_TITULO_QUALIFICADO", "rg_titulos", titulo_id,
              {"resultado": feito["resultado"], "ordem": feito["ordem"]})
        if feito["resultado"] == TIT.POSITIVA:
            flash("Qualificação positiva registrada. O título já pode ser "
                  "registrado — escolha o livro abaixo.", "success")
        else:
            flash("Qualificação negativa registrada, com as exigências. "
                  "Imprima a nota devolutiva para entregar ao apresentante.",
                  "warning")
        return voltar

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/nota")
    @login_required
    def rcpj_rtd_titulo_nota(titulo_id: int):
        """A nota devolutiva — o papel que volta com o título.

        **Devolver um título dizendo apenas «não pode» é devolver sem dizer o
        que fazer**, e o apresentante volta ao balcão para perguntar. Este papel
        é a decisão escrita, com as exigências e o prazo.

        SÓ LÊ. Imprimir não muda nada no banco.
        """
        with db.connect() as con:
            titulo = _titulo_ou_lista(con, titulo_id)
            if not titulo:
                return redirect(url_for("rcpj_rtd_titulos"))
            decisao = TIT.ultima_qualificacao(con, titulo_id)
            modelo = MODELOS.texto_do_papel(con, CHAVE_NOTA)
        if not decisao or decisao["resultado"] != TIT.NEGATIVA:
            flash("Este título não tem qualificação negativa — a nota "
                  "devolutiva é o papel da exigência.", "warning")
            return redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        # AS DATAS VÃO PRONTAS PARA O PAPEL — formatar data é do código, e a
        # prévia da tela de Modelos não teria a função para chamar.
        contexto = dict(
            t=titulo, q=decisao, sv=sv(),
            data_extenso=hoje_extenso(), oficial=usuario_nome(),
            funcao=usuario_funcao(),
            nome_da_atribuicao=TIT.NOME_DA_ATRIBUICAO[int(titulo["atribuicao"])],
            apresentado_em=fmt_date(titulo["data_apresentacao"]),
            qualificado_em=fmt_date(decisao["data_qualificacao"]),
            prazo_ate=(fmt_date(decisao["prazo_ate"]) if decisao["prazo_ate"]
                       else ""),
            fmt_date=fmt_date)
        return render_template("rcpj_rtd_nota.html",
                               papel=papel_html(modelo, contexto, chave=CHAVE_NOTA),
                               **contexto)

    # -------------------------------------------------------- registrar


    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/teor/previa", methods=["GET", "POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_titulo_teor_previa(titulo_id: int):
        """Prévia do teor RTDPJ com REGISTRADO. NÃO grava ato nem sela.

        Usa o número do registro já lavrado e as imagens anexadas ao título
        (ou ao registro). O modelo vem de `modelos_da_casa` (piso em código).
        """
        import io
        voltar = redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        with db.connect() as con:
            titulo = _titulo_ou_lista(con, titulo_id)
            if not titulo:
                return redirect(url_for("rcpj_rtd_titulos"))
            if not titulo.get("registro_id"):
                flash(
                    "Lavre o registro antes de gerar a prévia do teor "
                    "(é preciso o número do Registro).",
                    "danger")
                return voltar
            registro = RG.registro(con, int(titulo["registro_id"]))
            anexos_t = _anexos(con, titulo_id)
        if not registro or not registro.get("numero"):
            flash("Registro sem número — não dá para montar o teor.", "danger")
            return voltar
        anexos_r = [dict(x) for x in db.get_attachments(
            "RG_REGISTRO", int(titulo["registro_id"]))]
        # Prefer anexos do título; se vazios, usa os do registro.
        anexos = anexos_t or anexos_r
        escolhidos = request.values.getlist("anexo_id")
        if escolhidos:
            # o «²» e os 5.000 dígitos passam pelo `isdigit()`: -1, o anexo
            # de ninguém, como o de 30 dígitos já era (LD13)
            ids = {numero_digitado(x) or -1 for x in escolhidos if str(x).isdigit()}
            anexos = [a for a in anexos if int(a["id"]) in ids]
        caminhos = []
        for a in anexos:
            caminho = Path(a["stored_path"])
            if not caminho.is_file():
                continue
            ext = caminho.suffix.lower()
            if ext in RGTEOR.EXTENSOES_IMAGEM or ext in RGTEOR.EXTENSOES_PDF:
                caminhos.append(caminho)
        if not caminhos:
            flash(
                "Anexe ao menos uma imagem ou PDF do título antes da prévia.",
                "danger")
            return voltar
        s = sv()
        try:
            with db.connect() as con:
                # o que o termo do registro declara (LD09): o protocolo deste
                # título e as declarações do livro, gravadas no ato
                ato_do_registro = banco(con).um(
                    """SELECT * FROM rg_atos WHERE registro_id=%s AND tipo='REGISTRO'
                        ORDER BY id LIMIT 1""", (int(titulo["registro_id"]),))
                declarado = (RG.dados_do_termo(con, ato_do_registro, registro)
                             if ato_do_registro else {})
                # a natureza e a data da assinatura pela régua do termo
                # (`rcpj_rtd_ato_teor`, LT05): o teor, e na falta a natureza
                # do registro — a prévia saía sem «Tipo do ato», e a prévia
                # tem de dizer o que o termo vai dizer
                nat_teor, data_teor = RGTEOR.parse_campos_do_teor(
                    (ato_do_registro or {}).get("teor"))
                pdf = RGTEOR.gerar_pdf(
                    numero_registro=registro["numero"],
                    imagens=caminhos,
                    lavrante_nome=usuario_nome(),
                    lavrante_funcao=usuario_funcao(),
                    natureza_ato=(nat_teor
                                  or (registro.get("natureza") or "").strip()),
                    data_assinatura=data_teor,
                    **declarado,
                    cns=s.get("ri_cns") or "",
                    # O NOME DA SERVENTIA NO CABEÇALHO (LT05, 20/10/2026): o
                    # papel abre com «{unit_short} — CNS {cns}», e sem ele o
                    # teor saía «— CNS 000000».
                    unit_short=s.get("unit_name") or "",
                    cidade=s.get("ri_cidade") or "",
                    uf=s.get("ri_uf") or "MA",
                    serie=registro.get("serie") or titulo.get("serie"),
                    atribuicao=titulo.get("atribuicao"),
                    tipo_ato="REGISTRO",
                    con=con,
                )
        except RGTEOR.TeorRtdpjError as erro:
            flash(str(erro), "danger")
            return voltar
        nome = f"teor-registro-titulo-{titulo_id}-reg-{registro['numero']}.pdf"
        return send_file(
            io.BytesIO(pdf), mimetype="application/pdf",
            as_attachment=False, download_name=nome)


    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/registrar", methods=["POST"])
    @roles_required(*QUEM_QUALIFICA)
    def rcpj_rtd_titulo_registrar(titulo_id: int):
        """Lavra o registro do título qualificado. ESCREVE.

        O registro é o do `rg_registro` — o mesmo livro, a mesma numeração e a
        mesma regra de folha nova do título que veio do acervo. Uma segunda
        versão dele aqui divergiria da primeira no primeiro conserto.
        """
        voltar = redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        # O ATO GRATUITO DIZ O FUNDAMENTO ANTES DE LAVRAR (LD05, 21/10/2026):
        # sem ele o selo isento não sai (CN-MA art. 133), e o registro ficaria
        # no livro sem selo. A recusa vem antes de gastar número de livro.
        gratuidade = (_campo("fundamento_gratuidade")
                      if _campo("gratuito") == "1" else "")
        if _campo("gratuito") == "1" and not gratuidade:
            flash("Ato gratuito precisa do fundamento escrito (a lei ou a "
                  "decisão que o dispensa dos emolumentos) — é ele que vai no "
                  "selo isento. Nada foi lavrado.", "danger")
            return voltar
        try:
            with db.transaction() as con:
                # A atribuição do título manda na sigla do selo — ler ANTES
                # de registrar também serve, mas depois do UPDATE o campo
                # continua; o que importa é não hardcodar «RTD».
                titulo = TIT.um(con, titulo_id)
                # as declarações do termo do livro (LD09): conferidas contra o
                # livro escolhido antes do número, e gravadas no ato.
                # No RCPJ, a lista de presença entra na mesma lavratura.
                serie_pedida = _campo("serie")
                lista = (RG.lista_presenca_do_formulario(
                    request.form,
                    arquivos=request.files.getlist("novo_arquivo"))
                    if serie_pedida in RG.SERIES_RCPJ else None)
                feito = TIT.registrar(
                    con, titulo_id, serie=serie_pedida, sv=sv(),
                    agora=agora(), data_extenso=hoje_extenso(),
                    teor=_campo("teor") or None, usuario=usuario_nome(),
                    declaracoes=RG.declaracoes_do_formulario(request.form),
                    lista_presenca=lista)
                # SELO E CUSTAS NA MESMA TRANSAÇÃO do registro — regra da
                # casa: domínio não sela/cobra; a TELA faz (opcional). Se o
                # selo for de outra serventia ou não houver caixa com cobrar
                # marcado, AtoError desfaz o registro inteiro.
                aviso = ""
                cob_msg = ""
                serie_reg = serie_pedida
                if feito.get("ato_id") and not feito.get("reaproveitado"):
                    sigla = _sigla_da_atribuicao(int(titulo["atribuicao"]))
                    aviso = _selar_se_pedido(con, feito["ato_id"], sigla)
                    cob_msg = _cobrar_se_pedido(con, feito["ato_id"])
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return voltar
        # Selo automático depois da lavratura (fora da transação do ato).
        if feito.get("ato_id") and not feito.get("reaproveitado"):
            sigla = _sigla_da_atribuicao(int(titulo["atribuicao"]))
            aviso = _selar_o_ato_automatico(
                feito["ato_id"], "REGISTRO", sigla,
                serie=serie_reg or "", ja_dito=aviso, gratuidade=gratuidade)
            aviso = (aviso or "") + cob_msg
        if (serie_reg in RG.SERIES_RCPJ and feito.get("ato_id")
                and not feito.get("reaproveitado")):
            from atribuicoes_web import (
                _anexar_novos_arquivos_ao_registro,
                _vincular_anexos_rg_ato,
            )
            novos_ids = _anexar_novos_arquivos_ao_registro(
                db, registro_id=int(feito["registro_id"]), serie=serie_reg,
                numero=feito.get("numero_ordem"),
                arquivos=request.files.getlist("novo_arquivo"),
                descricao="Lista de presença ou certidão de não apresentação",
                user_id=usuario_id_do_sistema(),
                pasta_dos_arquivos=pasta_dos_arquivos)
            if novos_ids:
                _vincular_anexos_rg_ato(
                    db, ato_id=int(feito["ato_id"]),
                    registro_id=int(feito["registro_id"]),
                    anexo_ids=[str(i) for i in novos_ids],
                    user_id=usuario_id_do_sistema())
                with db.transaction() as con:
                    RG.acrescentar_anexos_da_lista(
                        con, int(feito["ato_id"]), novos_ids)
        audit("RG_TITULO_REGISTRADO", "rg_titulos", titulo_id,
              {"registro_id": feito["registro_id"],
               "numero_ordem": feito.get("numero_ordem"),
               **({"gratuidade": gratuidade} if gratuidade else {}),
               **RG.resumo_auditoria_lista(feito.get("cnma_lista_presenca"))})
        flash(f"Registro lavrado no Livro {feito.get('livro_numero')}, "
              f"fl. {feito.get('rotulo')}, sob o n. "
              f"{feito.get('numero_ordem')}. Se o título veio em papel, "
              f"imprima a etiqueta de registro para colar nele.{aviso}",
              "success")
        # «gerar também uma etiqueta para colar no título original, que será
        # devolvido, dizendo que foi averbado/registrado» — pedido do oficial
        # em 11/09/2026: em vez de só lembrar na frase acima, leva direto à
        # etiqueta pronta para imprimir. Sem selo (aparelho caiu), não há o
        # que declarar nela — volta ao título, como sempre.
        if feito.get("ato_id"):
            with db.connect() as con:
                tem_selo = banco(con).um(
                    "SELECT 1 AS tem FROM rg_atos WHERE id=%s AND COALESCE(selo,'')<>''",
                    (int(feito["ato_id"]),))
            if tem_selo:
                # 307: a etiqueta é POST (M8, LX11); o 307 leva este POST,
                # com o token, até ela.
                return redirect(url_for("rcpj_rtd_etiqueta",
                                        ato_id=int(feito["ato_id"])), code=307)
        return voltar

    # ----------------------------------- concluir pelo ato já lavrado

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/concluir", methods=["POST"])
    @roles_required(*QUEM_QUALIFICA)
    def rcpj_rtd_titulo_concluir(titulo_id: int):
        """Fecha o título que virou averbação ou cancelamento. ESCREVE.

        Não lavra nada: o ato já está no livro, lavrado na ficha do registro
        que existia. Sem esta rota o título de averbação ficava «Qualificado»
        para sempre — `registrar` abre registro novo, e `encerrar` só sabe
        dizer «devolvido» ou «cancelado».
        """
        voltar = redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        try:
            ato_id = int(_campo("ato_id") or 0)
        except ValueError:
            ato_id = 0
        try:
            with db.transaction() as con:
                feito = TIT.concluir_pelo_ato(
                    con, titulo_id, ato_id=ato_id, agora=agora(),
                    usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return voltar
        audit("RG_TITULO_CONCLUIDO_PELO_ATO", "rg_titulos", titulo_id,
              {"ato_id": feito["ato_id"], "registro_id": feito["registro_id"],
               "pelo_protocolo": feito["pelo_protocolo"]})
        flash(f"Título concluído. {feito['nota']}", "success")
        return voltar

    # ------------------------------------------------------ encerrar

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/encerrar", methods=["POST"])
    @roles_required(*QUEM_QUALIFICA)
    def rcpj_rtd_titulo_encerrar(titulo_id: int):
        """Fecha o título sem registro: devolvido, ou cancelado. ESCREVE.

        **A SITUAÇÃO TERMINAL PRECISA DE QUEM A PRODUZA**, e essa é a lição
        medida do E-Ofício: lá havia cinco situações declaradas e **21.360 de
        21.360** protocolos na primeira, com `bitFinalizado = 0` em todos. Um
        protocolo que só abre é um diário, e não um protocolo.
        """
        voltar = redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        try:
            with db.transaction() as con:
                feito = TIT.encerrar(
                    con, titulo_id, situacao=_campo("situacao"),
                    motivo=_campo("motivo"), agora=agora(),
                    usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return voltar
        audit("RG_TITULO_ENCERRADO", "rg_titulos", titulo_id,
              {"situacao": feito["situacao"]})
        flash(f"Título encerrado como {TIT.SITUACOES[feito['situacao']]}.",
              "success")
        return voltar

    # ------------------------------- o encaminhamento pela Central

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/encaminhar", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_titulo_encaminhar(titulo_id: int):
        """Guarda À MÃO que o título passou pela Central. ESCREVE — e não envia.

        **ESTA ROTA NÃO É A DA API, E CONTINUA NECESSÁRIA.** O que passa pela
        integração já se grava sozinho — ver `rcpj_rtd_onrtdpj_trazer`,
        `..._nota` e `..._registro`. Esta é para **o que se fez pelo portal**:
        nem tudo acontece pela API, e o que ficou de fora dela precisa ficar
        escrito do mesmo jeito, senão a correição vê um título que sumiu por
        semanas.
        """
        voltar = redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        try:
            with db.transaction() as con:
                feito = TIT.registrar_encaminhamento(
                    con, titulo_id, sentido=_campo("sentido"), agora=agora(),
                    data_encaminhamento=_campo("data_encaminhamento") or hoje(),
                    protocolo_central=_campo("protocolo_central"),
                    observacao=_campo("observacao"), usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return voltar
        audit("RG_TITULO_ENCAMINHADO", "rg_titulos", titulo_id,
              {"sentido": feito["sentido"]})
        flash(f"Passagem pela Central registrada: "
              f"{TIT.SENTIDOS[feito['sentido']]}. Este é o registro do que foi "
              f"feito pelo portal — o sistema não transmitiu nada agora.",
              "success")
        return voltar

    # ------------------------------------------- a etiqueta de registro

    @app.route("/rcpj-rtd/etiquetas/selos-externos", methods=["GET", "POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_etiquetas_selos_externos():
        """Imprime etiquetas de selos RTDPJ emitidos fora deste sistema.

        A etiqueta pode ser montada pela digitação do selo e do texto do
        registro ou a partir dos selos trazidos do E-Ofício para ``sd_selos``.
        Nenhum dos caminhos cria ou altera ato.
        """
        if request.method == "POST":
            medidas = ETQ.medidas_registro_rtdpj(db.get_settings)
            etiquetas = []
            numero_manual = _campo("selo_manual").upper()
            texto_manual = _campo("texto_registro")

            if numero_manual or texto_manual:
                try:
                    codigo = SELO.ler_codigo(numero_manual)
                except SELO.SeloError as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("rcpj_rtd_etiquetas_selos_externos"))
                if not texto_manual:
                    flash("Escreva o texto do registro que deve sair na etiqueta.",
                          "danger")
                    return redirect(url_for("rcpj_rtd_etiquetas_selos_externos"))
                if len(texto_manual) > 700:
                    flash("O texto do registro ultrapassa 700 caracteres. "
                          "Resuma o teor para ele caber na etiqueta.", "danger")
                    return redirect(url_for("rcpj_rtd_etiquetas_selos_externos"))
                if (not codigo.antigo and sv().get("ri_cns")
                        and not SELO.do_nosso_cns(codigo.inteiro,
                                                 sv().get("ri_cns"))):
                    flash("Este selo não pertence ao CNS desta serventia.",
                          "danger")
                    return redirect(url_for("rcpj_rtd_etiquetas_selos_externos"))

                with db.connect() as con:
                    conhecido = banco(con).um(
                        "SELECT * FROM sd_selos WHERE numero=%s ORDER BY id LIMIT 1",
                        (codigo.inteiro,))
                    # o título da tira é peça do papel (LF06F); a regra —
                    # selo digitado ou trazido do razão — é esta rota
                    titulo_da_tira = MODELOS.texto_do_papel(
                        con, f"{CHAVE_ETIQUETA_EXTERNA}__manual")
                conhecido = conhecido or {}
                if conhecido.get("cancelado_em"):
                    flash(f"O selo {codigo.inteiro} está cancelado.", "danger")
                    return redirect(url_for("rcpj_rtd_etiquetas_selos_externos"))
                if conhecido.get("tabela") or conhecido.get("ato_id") is not None:
                    flash(f"O selo {codigo.inteiro} já está vinculado a um ato "
                          "interno. Use a etiqueta da ficha do registro.", "danger")
                    return redirect(url_for("rcpj_rtd_etiquetas_selos_externos"))

                papel = SNPAPEL.do_papel(conhecido) if conhecido else {
                    "valores": ""}
                marca = NSELO.marca_do_selo(
                    codigo.inteiro, tamanho_mm=medidas["etiqueta_qr_mm"])
                etiquetas.append({
                    "numero": codigo.inteiro,
                    "titulo": titulo_da_tira,
                    "detalhe": texto_manual,
                    "valores": papel["valores"],
                    "qr": marca["qr"],
                    "qr_possivel": marca["qr_possivel"],
                })
                modo = "MANUAL"
            else:
                try:
                    with db.connect() as con:
                        selos = SEM.externos_rtdpj_para_etiqueta(
                            con, request.form.getlist("selo"))
                        titulo_da_tira = MODELOS.texto_do_papel(
                            con, f"{CHAVE_ETIQUETA_EXTERNA}__razao")
                except SEM.SeloEmitidoError as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("rcpj_rtd_etiquetas_selos_externos"))

                for selo in selos:
                    numero = str(selo.get("numero") or "").strip()
                    papel = SNPAPEL.do_papel(selo)
                    marca = NSELO.marca_do_selo(
                        numero, tamanho_mm=medidas["etiqueta_qr_mm"])
                    etiquetas.append({
                        "numero": numero,
                        "titulo": titulo_da_tira,
                        "detalhe": papel["detalhe"],
                        "valores": papel["valores"],
                        "qr": marca["qr"],
                        "qr_possivel": marca["qr_possivel"],
                    })
                modo = "RAZAO"

            audit("RG_ETIQUETAS_SELOS_EXTERNOS", "sd_selos", None,
                  {"quantidade": len(etiquetas),
                   "modo": modo,
                   "selos": [e["numero"] for e in etiquetas]})
            serventia = sv()
            with db.connect() as con:
                modelo = MODELOS.texto_do_papel(con, CHAVE_ETIQUETA_EXTERNA)
            for e in etiquetas:
                e["papel"] = papel_html(modelo, {"e": e, "m": medidas,
                                                 "serventia": serventia},
                                         chave=CHAVE_ETIQUETA_EXTERNA)
            return render_template(
                "rcpj_rtd_etiquetas_selos_externos_imprimir.html",
                etiquetas=etiquetas, m=medidas, serventia=serventia)

        filtros = {
            "inicio": (request.args.get("inicio") or "").strip(),
            "fim": (request.args.get("fim") or "").strip(),
            "busca": (request.args.get("busca") or "").strip(),
        }
        with db.connect() as con:
            disponiveis = SEM.procurar_externos_rtdpj(con, **filtros)
        for selo in disponiveis:
            selo["detalhe"] = SNPAPEL.detalhe(selo.get("texto"))
        return render_template(
            "rcpj_rtd_etiquetas_selos_externos.html",
            selos=disponiveis, f=filtros)

    def _texto_do_selo(selo: str) -> str:
        """O texto que o aparelho devolveu para aquele selo. SÓ LÊ.

        Sai de `sd_selos`, o razão dos selos — **não se remonta aqui o que o
        selador escreveu**: o valor impresso no papel tem de ser o que o selo
        declara, e não uma conta parecida feita depois. É a mesma regra da
        etiqueta de firma.
        """
        if not selo:
            return ""
        try:
            with db.connect() as con:
                linha = banco(con).um(
                    "SELECT texto FROM sd_selos WHERE numero=%s ORDER BY id LIMIT 1",
                    (selo,))
        except sqlite3.Error:
            # Só a tabela que falta se perdoa, e devolvendo vazio — que aqui
            # quer dizer «não há linha», e não «os valores são zero».
            return ""
        return str((linha["texto"] if linha else "") or "").strip()

    # `_token_do_qr` FOI APAGADA EM 24/09/2026 — o QR leva o endereco da
    # consulta pelo NUMERO, medido no portal. Ver `notas_selo`.

    @app.route("/rcpj-rtd/ato/<int:ato_id>/etiqueta", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_etiqueta(ato_id: int):
        """A etiqueta de registro, no tamanho exato, pronta para imprimir.

        **É A ETIQUETA QUE SE COLA NO TÍTULO DE PAPEL** — o pedido do oficial.
        Ela declara onde o registro ficou: livro, folha, número de ordem e data,
        mais o selo com o QR.

        A tira é a mesma de **100 × 30 mm** usada no reconhecimento de firma.
        A geometria e a calibração da impressora são compartilhadas; corpo,
        entrelinha e QR são próprios do registro para acomodar o teor.

        POR QUE HTML E NÃO ESC/POS: a mesma razão da etiqueta de firma —
        impressora térmica se instala no Windows como impressora comum, e
        `@page { size: 100mm 30mm }` sai pelo mesmo driver sem instalar nada.

        **A CONTAGEM SOBE AQUI**, e não num botão de «marcar impressa»: abrir
        esta tela é a única forma de imprimir, e contar onde a coisa acontece é
        o que faz a segunda via aparecer na conferência.

        POST COM O TOKEN (M8 do LS01, lote LX11). Era GET, e GET que grava
        não passa pelo CSRF da casa: o `SameSite=Lax` manda o cookie em link
        vindo de fora, e bastava um link ou `<img>` com o id para gravar em
        nome de quem estivesse logado. O botão da tela manda o formulário.
        """
        with db.connect() as con:
            bd = banco(con)
            ato = bd.um("SELECT * FROM rg_atos WHERE id=%s", (ato_id,))
            if not ato:
                abort(404)
            registro = RG.registro(con, int(ato["registro_id"]))
            livro = bd.um("SELECT numero FROM nu_livros WHERE id=%s",
                          (ato["livro_id"],)) \
                if ato["livro_id"] else None
            # PELO ATO, E SÓ DEPOIS PELO REGISTRO: a averbação não carrega
            # `rg_registros.titulo_id`, e a etiqueta dela saía sem protocolo.
            titulo = TIT.titulo_do_ato(con, int(ato["id"]))

        if registro and registro["situacao"] == "CANCELADO":
            # Etiqueta de registro cancelado colada num título é o ato valendo
            # no mundo depois de ter sido desfeito no livro. É a regra da
            # etiqueta de firma de ato cancelado.
            flash("Este registro está cancelado — não se imprime etiqueta de "
                  "registro cancelado.", "danger")
            destino = (url_for("rcpj_rtd_titulo", titulo_id=titulo["id"])
                       if titulo else url_for("rcpj_rtd_titulos"))
            return redirect(destino)

        with db.transaction() as con:
            banco(con).escrever(
                """UPDATE rg_atos SET etiqueta_impressa_em=%s,
                       etiqueta_impressoes=COALESCE(etiqueta_impressoes,0)+1
                    WHERE id=%s""", (db.now(), ato_id))
        vez = int(ato["etiqueta_impressoes"] or 0) + 1
        audit("RG_ETIQUETA_IMPRESSA", "rg_atos", ato_id,
              {"vez": vez, "selo": ato["selo"]})

        medidas = ETQ.medidas_registro_rtdpj(db.get_settings)
        selo = str(ato["selo"] or "").strip()
        marca = NSELO.marca_do_selo(
            selo, tamanho_mm=medidas["etiqueta_qr_mm"])
        serventia = sv()
        atribuicao = int(registro["atribuicao"]) if registro else TIT.RTD
        etiqueta = {
            "atribuicao": TIT.NOME_DA_ATRIBUICAO.get(atribuicao, ""),
            # `unit_name` é o nome da serventia em `serventia.PADRAO` — conferido
            # ali, e não adivinhado: `ri_nome` não existe naquele dicionário, e
            # um `.get` de chave inexistente sairia vazio no papel sem erro
            # nenhum. Nome de campo plausível é o que mais se parece com
            # medição sem ser.
            "cartorio": serventia.get("unit_name") or "",
            "cidade": serventia.get("ri_cidade") or "",
            "uf": serventia.get("ri_uf") or "",
            "cidade_uf": serventia.get("cidade_uf") or "",
            "tipo": ato["tipo"],
            "livro": (livro["numero"] if livro else None),
            "serie": registro["serie"] if registro else "",
            "folha": ato["rotulo"] or ato["folha"],
            "numero": ato["numero_ordem"],
            "data": fmt_date(str(ato["data_ato"] or "")[:10]),
            "natureza": (registro["natureza"] if registro else "") or "",
            "requerente": (registro["requerente_nome"] if registro else "") or "",
            "protocolo": (titulo or {}).get("numero"),
            "selo": selo,
            "oficial": usuario_nome(),
            "funcao": usuario_funcao(),
            "qr": marca["qr"],
            "qr_texto": marca["qr_texto"],
            "qr_possivel": marca["qr_possivel"],
            # O QUE O SELO DECLARA, impresso na etiqueta — a mesma régua dos
            # outros papéis da casa, e não uma conta feita aqui.
            "valores": SNPAPEL.linha_de_valores(_texto_do_selo(selo)),
        }
        voltar = (url_for("rcpj_rtd_titulo", titulo_id=titulo["id"]) if titulo
                  else url_for("rcpj_rtd_registro",
                               registro_id=int(ato["registro_id"])))
        with db.connect() as con:
            modelo = MODELOS.texto_do_papel(con, CHAVE_ETIQUETA)
        return render_template(
            "rcpj_rtd_etiqueta.html", e=etiqueta, m=medidas, vez=vez,
            voltar=voltar,
            papel=papel_html(modelo, {"e": etiqueta, "m": medidas, "vez": vez},
                             chave=CHAVE_ETIQUETA))

    # ============================================ a fila da Central ONRTDPJ

    @app.route("/rcpj-rtd/onrtdpj")
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_onrtdpj():
        """O que a Central ONRTDPJ tem esperando o cartório.

        **É POR AQUI QUE O TÍTULO ELETRÔNICO CHEGA** — a metade do pedido do
        oficial que a Central atende. O que a tela mostra é a fila de lá; o que
        entra na casa é o que o escrevente **traz** para o protocolo.

        **A LISTA NÃO JULGA PRAZO**, como a do roteiro do Protesto: um zero
        aqui pode ser «hoje não veio nada» ou «a Central está fora do ar», e o
        sistema não tem como saber qual — por isso a falha aparece escrita.
        """
        atribuicao = _atribuicao_pedida()
        tem_token = ONR.tem_credencial()
        fila, falha = [], ""
        if tem_token:
            try:
                fila = ONR.pendentes()
            except RECUSAS_DO_BALCAO as erro:
                falha = str(erro)
        with db.connect() as con:
            ja_na_casa = {
                str(r["origem_chave"]): {
                    "titulo_id": int(r["id"]),
                    "numero": r["numero"],
                }
                for r in banco(con).ler(
                    "SELECT id, origem_chave, numero FROM rg_titulos "
                    "WHERE origem=%s ORDER BY id",
                    (TIT.ORIGEM_DA_CENTRAL,))}
        return render_template(
            "rcpj_rtd_onrtdpj.html", fila=fila, falha=falha,
            tem_token=tem_token, ja_na_casa=ja_na_casa, atribuicao=atribuicao,
            nome_da_atribuicao=TIT.NOME_DA_ATRIBUICAO[atribuicao],
            atribuicoes=[{"codigo": c, "nome": TIT.NOME_DA_ATRIBUICAO[c]}
                         for c in TIT.ATRIBUICOES],
            base=ONR.BASE, fmt_date=fmt_date)

    @app.route("/rcpj-rtd/onrtdpj/testar", methods=["POST"])
    @roles_required(*QUEM_QUALIFICA)
    def rcpj_rtd_onrtdpj_testar():
        """Prova a ligação e o token, sem mexer em pedido nenhum.

        **O TESTE NÃO PODE MEXER EM PEDIDO.** `GET /api/cartorio/{cns}` é busca
        pura, pelo CNS que a casa já tem — a mesma escolha do
        `BuscarApresentante` na CRA, e pela mesma razão: um teste que baixasse
        a fila marcaria coisa do lado de lá.
        """
        try:
            r = ONR.diagnostico(sv().get("ri_cns") or "")
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpj_rtd_onrtdpj"))
        if r["ok"]:
            nome = (r.get("cartorio") or {}).get("nome") or "a serventia"
            flash(f"Ligação com a Central ONRTDPJ em ordem — ela respondeu "
                  f"sobre «{nome}».", "success")
        else:
            flash(f"A Central respondeu {r['status']}. {r['resposta'][:200]}",
                  "warning")
        return redirect(url_for("rcpj_rtd_onrtdpj"))

    @app.route("/rcpj-rtd/onrtdpj/trazer", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_onrtdpj_trazer():
        """Traz um pedido da Central para o protocolo da casa. ESCREVE.

        **A CHAMADA DE REDE FICA FORA DA TRANSAÇÃO**, e isso é a regra da casa:
        `db.transaction()` é `BEGIN IMMEDIATE`, e segurá-lo durante uma
        chamada de trinta segundos poria todo outro balcão no `busy_timeout`.
        Primeiro se pergunta à Central; depois se grava.
        """
        atribuicao = _atribuicao_pedida()
        protocolo = _campo("protocolo")
        voltar = redirect(url_for("rcpj_rtd_onrtdpj", atribuicao=atribuicao))
        try:
            pedido = ONR.pedido(protocolo)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return voltar
        try:
            with db.transaction() as con:
                feito = TIT.receber_da_central(
                    con, pedido, atribuicao=atribuicao, sv=sv(), agora=agora(),
                    data_extenso=hoje_extenso(), usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return voltar
        if feito.get("reaproveitado"):
            flash(f"O pedido {protocolo} já estava no protocolo desta casa.",
                  "warning")
        else:
            audit("RG_TITULO_DA_CENTRAL", "rg_titulos", feito["titulo_id"],
                  {"protocolo_central": protocolo, "atribuicao": atribuicao})
            flash(f"Pedido {protocolo} recebido sob o protocolo n. "
                  f"{feito.get('numero_ordem')}.", "success")
        return redirect(url_for("rcpj_rtd_titulo", titulo_id=feito["titulo_id"]))

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/onrtdpj/nota", methods=["POST"])
    @roles_required(*QUEM_QUALIFICA)
    def rcpj_rtd_onrtdpj_nota(titulo_id: int):
        """Sobe à Central a nota devolutiva daquele título.

        **É A QUALIFICAÇÃO NEGATIVA CHEGANDO A QUEM APRESENTOU.** No título de
        papel ela sai impressa e volta na mão; no eletrônico, é por aqui.

        **O que sobe é o que já foi decidido aqui**, e não um texto digitado de
        novo: dois textos para a mesma exigência divergiriam, e o que a Central
        mostrasse não seria o que a serventia lavrou.
        """
        voltar = redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        with db.connect() as con:
            titulo = _titulo_ou_lista(con, titulo_id)
            if not titulo:
                return redirect(url_for("rcpj_rtd_titulos"))
            decisao = TIT.ultima_qualificacao(con, titulo_id)
            protocolo = TIT.protocolo_na_central(con, titulo_id)
        if not protocolo:
            flash("Este título não tem protocolo na Central — ele não veio de "
                  "lá. Registre a passagem antes, com o número que a Central "
                  "deu.", "warning")
            return voltar
        if not decisao or decisao["resultado"] != TIT.NEGATIVA:
            flash("Só sobe nota devolutiva de título com qualificação negativa "
                  "— e é o texto dela que vai.", "warning")
            return voltar
        try:
            identidade = ONR.cadastrar_nota_devolutiva(
                protocolo, decisao["exigencias"] or "")
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return voltar
        with db.transaction() as con:
            TIT.registrar_encaminhamento(
                con, titulo_id, sentido=TIT.ENVIADO, agora=agora(),
                data_encaminhamento=hoje(), protocolo_central=protocolo,
                observacao=f"Nota devolutiva enviada à Central (id {identidade}).",
                usuario=usuario_nome())
        audit("RG_ONRTDPJ_NOTA", "rg_titulos", titulo_id,
              {"protocolo_central": protocolo, "nota": identidade})
        flash(f"Nota devolutiva enviada à Central, sob o id {identidade}.",
              "success")
        return voltar

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/onrtdpj/orcamento",
               methods=["POST"])
    @roles_required(*QUEM_QUALIFICA)
    def rcpj_rtd_onrtdpj_orcamento(titulo_id: int):
        """Informa à Central quanto custa aquele pedido.

        **O VALOR É DIGITADO, e não calculado** — e isso é declarado em vez de
        escondido: as custas do RCPJ/RTD ainda não estão amarradas ao ato nesta
        casa (ver `rg_registro`), e um número somado por aproximação num campo
        de dinheiro que sai para o cliente é pior que um campo em branco.
        """
        voltar = redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        with db.connect() as con:
            if not _titulo_ou_lista(con, titulo_id):
                return redirect(url_for("rcpj_rtd_titulos"))
            protocolo = TIT.protocolo_na_central(con, titulo_id)
        if not protocolo:
            flash("Este título não tem protocolo na Central.", "warning")
            return voltar
        try:
            ONR.informar_orcamento(protocolo, _campo("valor"))
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return voltar
        with db.transaction() as con:
            TIT.registrar_encaminhamento(
                con, titulo_id, sentido=TIT.ENVIADO, agora=agora(),
                data_encaminhamento=hoje(), protocolo_central=protocolo,
                observacao=f"Orçamento de R$ {_campo('valor')} informado à "
                           f"Central.", usuario=usuario_nome())
        audit("RG_ONRTDPJ_ORCAMENTO", "rg_titulos", titulo_id,
              {"protocolo_central": protocolo, "valor": _campo("valor")})
        flash("Orçamento informado à Central.", "success")
        return voltar

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/onrtdpj/cancelar",
               methods=["POST"])
    @roles_required(*QUEM_QUALIFICA)
    def rcpj_rtd_onrtdpj_cancelar(titulo_id: int):
        """Cancela na Central o pedido que já foi encerrado aqui.

        **SÓ DEPOIS DE ENCERRADO NESTA CASA.** Cancelar lá e deixar o título
        vivo aqui faria a Central e o livro discordarem — e quem consulta a
        Central acreditaria nela.
        """
        voltar = redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        with db.connect() as con:
            titulo = _titulo_ou_lista(con, titulo_id)
            if not titulo:
                return redirect(url_for("rcpj_rtd_titulos"))
            protocolo = TIT.protocolo_na_central(con, titulo_id)
        if not protocolo:
            flash("Este título não tem protocolo na Central.", "warning")
            return voltar
        if titulo["situacao"] not in (TIT.CANCELADO, TIT.DEVOLVIDO):
            flash("Encerre o título aqui primeiro — cancelar na Central um "
                  "título que continua vivo aqui faria os dois discordarem.",
                  "warning")
            return voltar
        try:
            ONR.cancelar_pedido(protocolo, _campo("motivo"))
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return voltar
        with db.transaction() as con:
            TIT.registrar_encaminhamento(
                con, titulo_id, sentido=TIT.ENVIADO, agora=agora(),
                data_encaminhamento=hoje(), protocolo_central=protocolo,
                observacao="Cancelamento informado à Central.",
                usuario=usuario_nome())
        audit("RG_ONRTDPJ_CANCELAR", "rg_titulos", titulo_id,
              {"protocolo_central": protocolo})
        flash("Cancelamento informado à Central.", "success")
        return voltar

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/onrtdpj/registro",
               methods=["POST"])
    @roles_required(*QUEM_QUALIFICA)
    def rcpj_rtd_onrtdpj_registro(titulo_id: int):
        """Informa à Central que o título foi REGISTRADO nesta serventia.

        **O SISTEMA NÃO REGISTRA NA CENTRAL: ELE COMUNICA O QUE JÁ LAVROU.** O
        registro é o do livro desta casa, com a folha e a numeração dela; um
        botão que informasse a Central sem o ato lavrado poria no mundo um
        registro que o livro não tem.
        """
        voltar = redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        with db.connect() as con:
            titulo = _titulo_ou_lista(con, titulo_id)
            if not titulo:
                return redirect(url_for("rcpj_rtd_titulos"))
            protocolo = TIT.protocolo_na_central(con, titulo_id)
            ato = None
            if titulo["registro_id"]:
                atos = RG.atos_do(con, int(titulo["registro_id"]))
                ato = dict(atos[0]) if atos else None
        if not protocolo:
            flash("Este título não tem protocolo na Central — ele não veio de "
                  "lá.", "warning")
            return voltar
        if titulo["situacao"] != TIT.REGISTRADO or not ato:
            flash("Só se informa à Central o registro que já foi lavrado aqui. "
                  "Lavre primeiro.", "warning")
            return voltar
        try:
            ONR.registrar_pedido(
                protocolo, numero_registro=str(ato.get("numero_ordem") or ""),
                selo_digital=str(ato.get("selo") or ""),
                data_registro=str(ato.get("data_ato") or "")[:10])
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return voltar
        with db.transaction() as con:
            TIT.registrar_encaminhamento(
                con, titulo_id, sentido=TIT.ENVIADO, agora=agora(),
                data_encaminhamento=hoje(), protocolo_central=protocolo,
                observacao=f"Registro n. {ato.get('numero_ordem')} informado à "
                           f"Central.", usuario=usuario_nome())
        audit("RG_ONRTDPJ_REGISTRO", "rg_titulos", titulo_id,
              {"protocolo_central": protocolo,
               "numero_ordem": ato.get("numero_ordem")})
        flash("Registro informado à Central ONRTDPJ.", "success")
        return voltar

    @app.route("/rcpj-rtd/etiqueta/ajuste", methods=["GET", "POST"])
    @roles_required(*QUEM_QUALIFICA)
    def rcpj_rtd_etiqueta_ajuste():
        """Acertar o encaixe da etiqueta de registro na térmica.

        A tira é a mesma de 100 × 30 mm do reconhecimento de firma. Largura,
        altura, margem e deslocamento usam a calibração comum da bobina; corpo,
        entrelinha e QR continuam próprios do RTDPJ para caber o teor registral.

        **O QUE NÃO SE DUPLICA É A MÁQUINA.** A leitura das medidas, o padrão
        como rede e o nome com que cada uma se grava moram em `etiqueta.py`, e
        as duas telas os usam. O que cada uma tem de seu é o formulário — e
        formulário divergente não estraga papel.

        **E O AJUSTE MORA NAS CONFIGURAÇÕES, e não no código**: impressora
        térmica nunca encaixa de primeira, e no código cada meio milímetro
        seria uma atualização do sistema.
        """
        configuracao = ETQ.REGISTRO_RTDPJ
        padrao = {
            ETQ.chave_registro_rtdpj(medida): valor
            for medida, valor in ETQ.PADROES[configuracao].items()
        }

        if request.method == "POST":
            # CAMPO QUE NÃO VEIO FICA COMO ESTÁ — não vira erro nem zero. É a
            # lição da tela irmã: ao acrescentar o tamanho do QR, os formulários
            # já abertos no navegador do balcão passaram a não conseguir salvar
            # nada, porque `float("")` levantava e a tela recusava a gravação
            # inteira sem dizer de qual campo.
            novo = {}
            for chave in padrao:
                if chave not in request.form:
                    continue
                bruto = (request.form.get(chave) or "").replace(",", ".").strip()
                try:
                    float(bruto)
                except ValueError:
                    flash(f"'{bruto}' não é um número — corrija {chave}.",
                          "danger")
                    return redirect(url_for("rcpj_rtd_etiqueta_ajuste"))
                novo[chave] = bruto
            if not novo:
                flash("Nenhuma medida foi enviada.", "warning")
                return redirect(url_for("rcpj_rtd_etiqueta_ajuste"))
            db.set_settings(novo)
            audit("RG_ETIQUETA_AJUSTADA", None, None, novo)
            flash("Medidas guardadas. Imprima uma etiqueta e confira.",
                  "success")
            return redirect(url_for("rcpj_rtd_etiqueta_ajuste"))

        return render_template(
            "rcpj_rtd_etiqueta_ajuste.html",
            m=ETQ.medidas_registro_rtdpj(db.get_settings),
            padrao=ETQ.PADROES[configuracao],
            chave=ETQ.chave_registro_rtdpj,
            nome=ETQ.NOME_DA_CONFIGURACAO[configuracao])

    # ----------------------------------- o arquivo do título, servido

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/arquivo/<int:anexo_id>")
    @login_required
    def rcpj_rtd_titulo_ver(titulo_id: int, anexo_id: int):
        """O arquivo daquele título, aberto na tela. SÓ LÊ.

        **POR QUE UMA ROTA AQUI, SE `/arquivo/<id>/ver` JÁ EXISTE.** Porque esta
        confere que o anexo é **daquele título** antes de servir. A geral serve
        qualquer anexo a quem tem login — o que está certo para ela —, e o
        quadro do visualizador desta tela monta o endereço a partir do título:
        sem a conferência, um número trocado na barra mostraria o documento de
        outro protocolo dentro da ficha deste, e ninguém desconfia de um
        documento que abre.
        """
        anexo = db.get_attachment(anexo_id)
        if not anexo or anexo["entity_type"] != TIT.ANEXO_DO_TITULO \
                or int(anexo["entity_id"]) != int(titulo_id):
            abort(404)
        caminho = Path(anexo["stored_path"])
        if not caminho.exists():
            abort(404)
        if not ARQVIS.abre_na_tela(anexo["original_name"]):
            return redirect(url_for("attachment_download",
                                    attachment_id=anexo_id))
        audit("RG_TITULO_ARQUIVO_VISTO", "rg_titulos", titulo_id,
              {"anexo": anexo_id})
        resposta = send_file(
            caminho, as_attachment=False,
            download_name=anexo["original_name"],
            mimetype=ARQVIS.tipo_do_arquivo(anexo["original_name"]))
        for chave, valor in ARQVIS.cabecalhos_para_mostrar().items():
            resposta.headers[chave] = valor
        return resposta


def __getattr__(nome: str):
    """Os nomes antigos dos papéis destas telas, lidos da base dos padrões.

    A nota devolutiva e as etiquetas eram templates até o LF06F (19/10/2026);
    os nomes `MODELO_*` são os do catálogo (`modelos_papeis/rcpj_rtd.py`) e
    devolvem o MESMO texto que a tela imprime. Nome que não é de papel
    continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    return MODELOS.constante_antiga(__name__, nome)
